"""Build output/resolved_tickets.json from the database and the audit trail.

Every field is derived. Ticket status and notes come from the working database,
agent contributions come from the audit trail, and approvals come from the
approvals table with the name of the person who decided each one.

    python output/build_resolved.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "data" / "campus_customs.db"
WORKING = ROOT / "data" / "campus_customs_new.db"
AUDIT = ROOT / "output" / "audit_trail.json"
RUNS_MANIFEST = ROOT / "output" / "resolution_runs.json"
OUT = ROOT / "output" / "resolved_tickets.json"

AGENT_LABEL = {
    "boss": "Boss",
    "inventory": "Inventory",
    "accounting": "Accounting",
    "facilities": "Facilities",
    "customer_service": "Customer Service",
}


def rows(db: Path, sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def agent_name(raw: str) -> str:
    return AGENT_LABEL.get(raw, raw)


def contributions_for(ticket_id: int, runs: list[dict]) -> list[dict]:
    """Roll every audit step for one ticket into one entry per agent."""
    by: dict[str, dict] = {}
    for run in runs:
        for step in run["steps"]:
            # Older runs recorded ticket_id as a string, so compare loosely.
            raw = step.get("ticket_id")
            if raw is None or str(raw) != str(ticket_id) or not step.get("agent"):
                continue
            who = step["agent"]
            row = by.setdefault(
                who,
                {
                    "agent": who,
                    "display_name": agent_name(who),
                    "turns": 0,
                    "tools_used": [],
                    "delegated_to": [],
                    "contribution": "",
                },
            )
            kind = step["kind"]
            if kind == "model_response":
                row["turns"] += 1
            elif kind == "tool_call":
                tool = step.get("tool")
                if tool and tool not in row["tools_used"]:
                    row["tools_used"].append(tool)
            elif kind == "delegation_start":
                target = step.get("to_agent")
                if target and target not in row["delegated_to"]:
                    row["delegated_to"].append(target)
            elif kind == "answer":
                # Keep the latest answer, which is the agent's final word.
                row["contribution"] = step.get("answer", "")
    # Boss first, then whoever did the most work.
    return sorted(by.values(), key=lambda r: (r["agent"] != "boss", -r["turns"]))


def short_outcome(ticket: dict) -> str:
    """The last decision the team recorded, which is the outcome in its words."""
    notes = (ticket.get("notes") or "").split("|")
    entries = [n.strip() for n in notes if n.strip()]
    if len(entries) <= 1:
        return "No decision was recorded on this ticket."
    last = entries[-1]
    return last if len(last) <= 400 else last[:397] + "..."


def main() -> None:
    audit = json.loads(AUDIT.read_text()) if AUDIT.exists() else {"runs": []}
    runs = audit.get("runs", [])

    # Count only the runs that made up this resolution. The audit file keeps
    # every run ever made, and summing all of them would report turn counts
    # from runs against a completely different board state.
    if RUNS_MANIFEST.exists():
        wanted = set(json.loads(RUNS_MANIFEST.read_text())["run_ids"])
        runs = [r for r in runs if r["run_id"] in wanted]

    starting = rows(ORIGINAL, "SELECT balance FROM cash_accounts WHERE name='checking'")[0]["balance"]
    ending = rows(WORKING, "SELECT balance FROM cash_accounts WHERE name='checking'")[0]["balance"]
    payments = rows(WORKING, "SELECT * FROM payments ORDER BY id")
    approvals = rows(WORKING, "SELECT * FROM approvals ORDER BY id")
    tickets = rows(WORKING, "SELECT * FROM tickets ORDER BY id")

    def approvals_for(ticket_id: int) -> list[dict]:
        out = []
        for a in approvals:
            linked = a["ticket_id"] == ticket_id
            if not linked:
                # Fall back to the shop's own links when the agent did not
                # carry the ticket id onto the request.
                t = next((t for t in tickets if t["id"] == ticket_id), None)
                if t:
                    kind = (a["kind"] or "").lower()
                    linked = (kind == "invoice" and t["invoice_id"] == a["ref_id"]) or (
                        kind == "rent" and t["lease_id"] == a["ref_id"]
                    )
            if not linked:
                continue
            paid = next(
                (
                    p
                    for p in payments
                    if (p["kind"] or "").lower() == (a["kind"] or "").lower()
                    and p["ref_id"] == a["ref_id"]
                ),
                None,
            )
            out.append(
                {
                    "approval_id": a["id"],
                    "kind": a["kind"],
                    "ref_id": a["ref_id"],
                    "amount": a["amount"],
                    "reason": a["reason"],
                    "requested_by": a["requested_by"],
                    "status": a["status"],
                    "decided_by": a["decided_by"],
                    "decided_at": a["decided_at"],
                    "money_moved": bool(paid),
                    "paid_amount": paid["amount"] if paid else 0.0,
                }
            )
        return out

    out_tickets = []
    for t in tickets:
        linked_approvals = approvals_for(t["id"])
        spent = round(sum(a["paid_amount"] for a in linked_approvals), 2)
        out_tickets.append(
            {
                "ticket_id": t["id"],
                "subject": t["subject"],
                "requester": t["requester"],
                "type": t["type"],
                "final_status": t["status"],
                "resolved": t["status"].lower() in ("closed", "resolved"),
                "outcome": short_outcome(t),
                "cash_moved_usd": spent,
                "agents": contributions_for(t["id"], runs),
                "human_approvals": linked_approvals,
            }
        )

    total_paid = round(sum(p["amount"] for p in payments), 2)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shop_date": rows(WORKING, "SELECT date_today FROM desk LIMIT 1")[0]["date_today"],
        "database": "data/campus_customs_new.db",
        "cash": {
            "starting_checking": starting,
            "total_paid": total_paid,
            "ending_checking": ending,
            "reconciles": abs(round(starting - total_paid, 2) - ending) < 0.005,
        },
        "tickets_resolved": sum(1 for t in out_tickets if t["resolved"]),
        "tickets_total": len(out_tickets),
        "tickets": out_tickets,
    }

    if not payload["cash"]["reconciles"]:
        raise SystemExit("Cash does not reconcile. Refusing to write a file with wrong maths.")

    OUT.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  {payload['tickets_resolved']}/{payload['tickets_total']} resolved")
    print(f"  cash ${starting:,.2f} - ${total_paid:,.2f} = ${ending:,.2f}  (reconciles)")
    for t in out_tickets:
        agents = ", ".join(a["display_name"] for a in t["agents"]) or "none recorded"
        print(f"  #{t['ticket_id']} {t['final_status']:<9} ${t['cash_moved_usd']:>8,.2f}  {agents}")


if __name__ == "__main__":
    main()
