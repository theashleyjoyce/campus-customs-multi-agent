"""Smoke-test the three Campus Customs MCP tools and save the evidence.

Connects to mcp_server/server.py as an MCP client over stdio, runs every case in
CASES, then checks the reported numbers against the database file with direct
SQL. Writes everything to output/mcp_smoke.json.

Run with the board reset first:
    python mcp_server/server.py --reset
    python mcp_server/smoke.py
"""

from __future__ import annotations

import asyncio
import json
import platform
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import Client

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SERVER = HERE / "server.py"
DB = ROOT / "data" / "campus_customs_new.db"
OUT = ROOT / "output" / "mcp_smoke.json"

# Each case is the prompt a person or agent would ask, the tool that answers
# it, the arguments, whether the tool should accept or refuse, and why that
# matters. They run in order, so the payment cases build on each other.
CASES: list[dict] = [
    # ---- board -----------------------------------------------------------
    {
        "prompt": "What is today for the shop? I do not want to use the real calendar.",
        "tool": "get_today",
        "args": {},
        "expect": "accept",
        "why": "Every overdue check hangs off desk.date_today, which is 2026-08-31, not the real date.",
    },
    {
        "prompt": "What is on the board right now?",
        "tool": "list_tickets",
        "args": {"status": "open"},
        "expect": "accept",
        "why": "Three open tickets: the tee, the rent and the hoodie discount.",
    },
    {
        "prompt": "Show me ticket 101 and everything it touches.",
        "tool": "get_ticket",
        "args": {"ticket_id": 101},
        "expect": "accept",
        "why": "One call returns the linked invoice, vendor, price and stock rows, which is where the real problem lives.",
    },
    {
        "prompt": "Show me ticket 999.",
        "tool": "get_ticket",
        "args": {"ticket_id": 999},
        "expect": "refuse",
        "why": "A ticket that is not in the database is refused rather than invented.",
    },

    # ---- inventory -------------------------------------------------------
    {
        "prompt": "Ticket 101: Tauhid Zaman wants one Bulldog tee in size S. Do we have it?",
        "tool": "check_stock",
        "args": {"sku": "CC-TEE-WHITE", "size": "S", "qty_wanted": 1},
        "expect": "accept",
        "why": "Stock is 0, so the shop is short by 1 and cannot fill it from the shelf.",
    },
    {
        "prompt": "Ticket 103: Yale AI Club wants 20 navy hoodies in size M. How many do we have?",
        "tool": "check_stock",
        "args": {"sku": "CC-HOOD-NAVY", "size": "M", "qty_wanted": 20},
        "expect": "accept",
        "why": "Stock is 8 against 20 requested, so the shop is short by 12.",
    },
    {
        "prompt": "Do we carry the Bulldog tee in XXL?",
        "tool": "check_stock",
        "args": {"sku": "CC-TEE-WHITE", "size": "XXL", "qty_wanted": 1},
        "expect": "refuse",
        "why": "A size the shop does not carry is refused, and the real sizes are listed back.",
    },
    {
        "prompt": "Ticket 101: the tee is out of stock. Who can reprint it, and will they ship?",
        "tool": "check_vendor_for_restock",
        "args": {"sku": "CC-TEE-WHITE"},
        "expect": "accept",
        "why": "Bulldog Print Co is the 5 day apparel reprinter but is blocked by open invoice 501, 3 days overdue.",
    },
    {
        "prompt": "Which vendor restocks sku NOPE?",
        "tool": "check_vendor_for_restock",
        "args": {"sku": "NOPE"},
        "expect": "refuse",
        "why": "An unknown sku is refused. This exact case caught a real bug on the first run.",
    },

    # ---- money -----------------------------------------------------------
    {
        "prompt": "How much can the shop actually spend?",
        "tool": "get_cash_balance",
        "args": {"account": "checking"},
        "expect": "accept",
        "why": "Checking holds $3,400 and nothing comes in, so this is the ceiling on everything.",
    },
    {
        "prompt": "What bills are open, and how late are they?",
        "tool": "list_invoices",
        "args": {"status": "open"},
        "expect": "accept",
        "why": "Invoice 501 for $840 is 3 days overdue, which is what freezes the apparel vendor.",
    },
    {
        "prompt": "What does a navy hoodie cost us and what do we sell it for?",
        "tool": "get_pricing",
        "args": {"sku": "CC-HOOD-NAVY"},
        "expect": "accept",
        "why": "$22 cost against $58 list, so $36 of margin a unit and a 62.1 percent break-even.",
    },
    {
        "prompt": "Ticket 103: what does 15 percent off 20 hoodies do to our margin?",
        "tool": "quote_discount",
        "args": {"sku": "CC-HOOD-NAVY", "qty": 20, "discount_pct": 15},
        "expect": "accept",
        "why": "Arithmetic from the tool rather than a guess, including how far it sits from break-even.",
    },
    {
        "prompt": "What if we gave them 70 percent off?",
        "tool": "quote_discount",
        "args": {"sku": "CC-HOOD-NAVY", "qty": 20, "discount_pct": 70},
        "expect": "accept",
        "why": "Past the 62.1 percent break-even, so below_cost comes back true. Volume multiplies a negative margin.",
    },

    # ---- space -----------------------------------------------------------
    {
        "prompt": "Ticket 102: the landlord says rent is due in two days. Is that right?",
        "tool": "get_lease",
        "args": {"lease_id": 1},
        "expect": "accept",
        "why": "Lease 1 confirms $2,400 due 2026-09-02, two days out. The email is a claim, the lease is the fact.",
    },
    {
        "prompt": "Show me lease 9999.",
        "tool": "get_lease",
        "args": {"lease_id": 9999},
        "expect": "refuse",
        "why": "A lease that does not exist is refused rather than assumed.",
    },

    # ---- approvals and payment ------------------------------------------
    {
        "prompt": "Just pay invoice 501 for $840 so the vendor unblocks.",
        "tool": "pay_bill",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 840.0, "approved_by": "Ashley Joyce"},
        "expect": "refuse",
        "why": "A typed name is not authorisation. There is no approval record, so no money moves.",
    },
    {
        "prompt": "Ask a human to approve paying invoice 501 so the tee can be reprinted.",
        "tool": "request_approval",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 840.0,
                 "reason": "Unblock Bulldog Print Co so the CC-TEE-WHITE reprint can ship",
                 "ticket_id": 101, "requested_by": "accounting"},
        "expect": "accept",
        "why": "Records a pending request and shows what the balance would be. Spends nothing.",
    },
    {
        "prompt": "Another agent reaches the same conclusion and asks again for the same bill.",
        "tool": "request_approval",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 840.0,
                 "reason": "Same bill, different agent", "ticket_id": 103, "requested_by": "inventory"},
        "expect": "accept",
        "why": "Returns the existing request with duplicate true. A human must not approve the same money twice.",
    },
    {
        "prompt": "What is waiting on a human right now?",
        "tool": "list_approvals",
        "args": {"status": "pending"},
        "expect": "accept",
        "why": "One request, not two, because the duplicate was folded into the first.",
    },
    {
        "prompt": "Pay it now, the approval exists.",
        "tool": "pay_bill",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 840.0, "approved_by": "Ashley Joyce"},
        "expect": "refuse",
        "why": "A pending request is not an approved one. A person still has to decide it.",
    },
    {
        "prompt": "Approve it, but without saying who approved it.",
        "tool": "decide_approval",
        "args": {"approval_id": 1, "decision": "approved", "decided_by": ""},
        "expect": "refuse",
        "why": "A decision needs the name of the person making it.",
    },
    {
        "prompt": "Ashley Joyce approves paying invoice 501.",
        "tool": "decide_approval",
        "args": {"approval_id": 1, "decision": "approved", "decided_by": "Ashley Joyce"},
        "expect": "accept",
        "why": "The human step. Still spends nothing, but now pay_bill has a real approver.",
    },
    {
        "prompt": "Pay just $1 toward invoice 501 now that it is approved.",
        "tool": "pay_bill",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 1.0, "approved_by": "Ashley Joyce"},
        "expect": "refuse",
        "why": "An $840 debt must not clear for $1, which would unblock the vendor for free.",
    },
    {
        "prompt": "Pay invoice 501 properly, approved by Ashley Joyce.",
        "tool": "pay_bill",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 840.0, "approved_by": "Ashley Joyce"},
        "expect": "accept",
        "why": "Balance $3,400 to $2,560, the invoice flips to paid, and the approval closes to paid.",
    },
    {
        "prompt": "Invoice 501 is paid now. Can Bulldog Print Co ship the tee reprint?",
        "tool": "check_vendor_for_restock",
        "args": {"sku": "CC-TEE-WHITE"},
        "expect": "accept",
        "why": "can_ship flips to true. One approved payment unblocks tickets 101 and 103 together.",
    },
    {
        "prompt": "Ask again for invoice 501 now that it is settled.",
        "tool": "request_approval",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 840.0,
                 "reason": "Already settled", "ticket_id": 101},
        "expect": "refuse",
        "why": "A paid bill cannot be re-requested. Without this an agent could get rent approved twice.",
    },

    # ---- receiving and the board ----------------------------------------
    {
        "prompt": "The tee reprint arrived. Put one back on the shelf.",
        "tool": "receive_stock",
        "args": {"sku": "CC-TEE-WHITE", "size": "S", "qty": 1, "note": "Reprint from Bulldog Print Co"},
        "expect": "accept",
        "why": "Stock goes 0 to 1. Only called when units are genuinely in hand, since ordering is not receiving.",
    },
    {
        "prompt": "Add minus five hoodies.",
        "tool": "receive_stock",
        "args": {"sku": "CC-HOOD-NAVY", "size": "M", "qty": -5},
        "expect": "refuse",
        "why": "A negative delivery is refused, so stock cannot be quietly written down through this path.",
    },
    {
        "prompt": "Write to Tauhid about his tee.",
        "tool": "draft_message",
        "args": {"ticket_id": 101, "to": "Tauhid Zaman", "subject": "Your Bulldog tee",
                 "body": "Your tee in size S is on its way to us and we will confirm as soon as it lands."},
        "expect": "accept",
        "why": "Comes back with sent false. The shop never emails anyone in this assignment.",
    },
    {
        "prompt": "Close ticket 101, the tee is ordered.",
        "tool": "update_ticket",
        "args": {"ticket_id": 101, "status": "closed", "note": "Smoke test: invoice paid, reprint ordered and received."},
        "expect": "accept",
        "why": "Moves the ticket on and appends to its notes, which is the decision record a human reads.",
    },
]


def db_rows(sql: str, params: tuple = ()) -> list[dict]:
    """Read the working database directly, bypassing the server."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def verify_against_db(calls: list[dict]) -> list[dict]:
    """Compare what the tools reported with what the database file actually holds."""
    checks: list[dict] = []

    def compare(what: str, sql: str, params: tuple, reported, pick) -> None:
        actual = pick(db_rows(sql, params))
        checks.append(
            {
                "what": what,
                "reported_by_tool": reported,
                "actual_in_database": actual,
                "matches": reported == actual,
                "sql": " ".join(sql.split()),
            }
        )

    hood = next(c for c in calls if c["tool_name"] == "check_stock"
                and c["tool_arguments"].get("sku") == "CC-HOOD-NAVY")
    compare("CC-HOOD-NAVY size M on hand", "SELECT qty FROM inventory WHERE sku=? AND size=?",
            ("CC-HOOD-NAVY", "M"), hood["tool_output"]["on_hand"], lambda r: r[0]["qty"])

    received = next(c for c in calls if c["tool_name"] == "receive_stock" and c["tool_output"]["ok"])
    compare("CC-TEE-WHITE size S after the delivery", "SELECT qty FROM inventory WHERE sku=? AND size=?",
            ("CC-TEE-WHITE", "S"), received["tool_output"]["now"], lambda r: r[0]["qty"])

    paid = next(c for c in calls if c["tool_name"] == "pay_bill" and c["tool_output"]["ok"])
    compare("checking balance after the approved payment",
            "SELECT balance FROM cash_accounts WHERE name='checking'", (),
            paid["tool_output"]["balance_after"], lambda r: r[0]["balance"])
    compare("invoice 501 status", "SELECT status FROM invoices WHERE id=?", (501,),
            "paid", lambda r: r[0]["status"])
    compare("rows written to payments", "SELECT COUNT(*) AS n FROM payments", (),
            1, lambda r: r[0]["n"])
    compare("approver recorded in the audit trail", "SELECT DISTINCT approved_by FROM payments", (),
            ["Ashley Joyce"], lambda r: [x["approved_by"] for x in r])
    compare("the approval closed to paid", "SELECT status FROM approvals WHERE id=1", (),
            "paid", lambda r: r[0]["status"])
    compare("open invoices left for Bulldog Print Co",
            "SELECT COUNT(*) AS n FROM invoices WHERE vendor_id=1 AND lower(status)='open'", (),
            0, lambda r: r[0]["n"])
    closed = next(c for c in calls if c["tool_name"] == "update_ticket" and c["tool_output"]["ok"])
    compare("ticket 101 status after update", "SELECT status FROM tickets WHERE id=101", (),
            closed["tool_output"]["status"], lambda r: r[0]["status"])
    return checks


async def main() -> None:
    calls: list[dict] = []

    async with Client(str(SERVER)) as client:
        tools = await client.list_tools()
        advertised = [
            {
                "name": t.name,
                "summary": (t.description or "").splitlines()[0],
                "parameters": list((t.input_schema or {}).get("properties", {})),
                "required": (t.input_schema or {}).get("required", []),
            }
            for t in tools
        ]

        for case in CASES:
            result = await client.call_tool(case["tool"], case["args"])
            payload = json.loads(result.content[0].text) if result.content else result.data
            ok = bool(payload.get("ok"))
            calls.append(
                {
                    "prompt_asked": case["prompt"],
                    "tool_name": case["tool"],
                    "tool_arguments": case["args"],
                    "tool_output": payload,
                    "expected": case["expect"],
                    "outcome": "accepted" if ok else "refused",
                    "passed": (case["expect"] == "accept") == ok,
                    "why_this_matters": case["why"],
                }
            )

    verification = verify_against_db(calls)
    passed = sum(1 for c in calls if c["passed"])
    matching = sum(1 for v in verification if v["matches"])
    unblocked = next(
        c for c in reversed(calls)
        if c["tool_name"] == "check_vendor_for_restock" and c["tool_output"]["ok"]
    )
    bulldog = next(v for v in unblocked["tool_output"]["vendors"] if v["name"] == "Bulldog Print Co")

    evidence = {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server": "campus-customs-ops",
        "registered_in": ".mcp.json at the project root",
        "transport": "stdio",
        "client": f"fastmcp Client, python {platform.python_version()}",
        "database": "data/campus_customs_new.db",
        "note": (
            "Every call below went over the MCP protocol to mcp_server/server.py. The board "
            "was reset first, so the run starts from three open tickets, $3,400 in "
            "checking and invoice 501 unpaid. The database_verification section re-reads "
            "the database file with direct SQL to confirm the tools reported real values."
        ),
        "tools_advertised": advertised,
        "summary": {
            "calls": len(calls),
            "passed": passed,
            "failed": len(calls) - passed,
            "tools_covered": sorted({c["tool_name"] for c in calls}),
            "chokepoint_cleared": bulldog["can_ship"],
            "database_checks": len(verification),
            "database_checks_matching": matching,
        },
        "calls": calls,
        "database_verification": verification,
    }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"{passed}/{len(calls)} calls behaved as expected")
    print(f"{matching}/{len(verification)} tool values match the database file")
    print(f"chokepoint cleared after paying invoice 501: {bulldog['can_ship']}")
    print(f"evidence written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
