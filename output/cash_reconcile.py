"""Build the cash itemisation for desk_tickets.html straight from the database.

Nothing here is typed by hand. The starting balance comes from the untouched
original, every movement comes from the payments table, and the ending balance
is read back from cash_accounts. If those three do not agree the script fails
loudly rather than printing a tidy number that is wrong.

    python output/cash_reconcile.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "data" / "campus_customs.db"
WORKING = ROOT / "data" / "campus_customs_new.db"


def rows(db: Path, sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def build() -> dict:
    starting = rows(ORIGINAL, "SELECT balance FROM cash_accounts WHERE name='checking'")[0][
        "balance"
    ]
    ending = rows(WORKING, "SELECT balance FROM cash_accounts WHERE name='checking'")[0]["balance"]

    # payments has no ticket_id, so attribution comes from the approval that
    # authorised each payment, matched on what was paid and which bill.
    # Read payments on their own. Joining to approvals here fans out when more
    # than one approval exists for the same bill, which double counts the money
    # and produces a total that does not match the account. Each payment is
    # matched to exactly one approval below instead.
    payments = rows(WORKING, "SELECT * FROM payments ORDER BY id")
    all_approvals = rows(WORKING, "SELECT * FROM approvals ORDER BY id")

    used_approvals: set[int] = set()
    for p in payments:
        match = next(
            (
                a
                for a in all_approvals
                if a["id"] not in used_approvals
                and (a["kind"] or "").lower() == (p["kind"] or "").lower()
                and a["ref_id"] == p["ref_id"]
                and (a["status"] or "").lower() == "paid"
            ),
            None,
        )
        if match:
            used_approvals.add(match["id"])
        p["approval_id"] = match["id"] if match else None
        p["ticket_id"] = match["ticket_id"] if match else None
        p["reason"] = match["reason"] if match else None
        p["requested_by"] = match["requested_by"] if match else None

    # An approval does not always carry its ticket_id. Fall back to the shop's
    # own links: an invoice payment belongs to the ticket that names that
    # invoice, and a rent payment belongs to the ticket on that lease.
    for p in payments:
        if p.get("ticket_id"):
            p["attribution"] = "approval record"
            continue
        kind = (p["kind"] or "").lower()
        found = []
        if kind == "invoice":
            found = rows(WORKING, "SELECT id FROM tickets WHERE invoice_id = ?", (p["ref_id"],))
        elif kind == "rent":
            found = rows(WORKING, "SELECT id FROM tickets WHERE lease_id = ?", (p["ref_id"],))
        if found:
            p["ticket_id"] = found[0]["id"]
            p["attribution"] = "matched on the ticket's own link"
        else:
            p["attribution"] = "unattributed"

    running = starting
    for p in payments:
        p["balance_before"] = round(running, 2)
        running = round(running - p["amount"], 2)
        p["balance_after"] = running

    # Belt and braces: the payment rows must be unique by id, or something has
    # fanned out again.
    ids = [p["id"] for p in payments]
    assert len(ids) == len(set(ids)), f"payment rows duplicated: {ids}"

    total_paid = round(sum(p["amount"] for p in payments), 2)
    computed = round(starting - total_paid, 2)

    unpaid = rows(
        WORKING,
        "SELECT id, kind, ref_id, amount, reason, status, ticket_id FROM approvals "
        "WHERE lower(status) IN ('pending','approved','denied') ORDER BY id",
    )
    tickets = rows(WORKING, "SELECT id, subject, status FROM tickets ORDER BY id")

    return {
        "starting": starting,
        "ending_in_db": ending,
        "total_paid": total_paid,
        "computed_ending": computed,
        "reconciles": abs(computed - ending) < 0.005,
        "payments": payments,
        "not_paid": unpaid,
        "tickets": tickets,
    }


def main() -> None:
    d = build()
    print(f"starting checking balance   ${d['starting']:>10,.2f}   (from the untouched original)")
    print()
    for p in d["payments"]:
        who = f"ticket #{p['ticket_id']}" if p["ticket_id"] else "no ticket linked"
        print(
            f"  payment {p['id']}  {p['kind']:<15} ref {p['ref_id']:<5} "
            f"-${p['amount']:>9,.2f}  ->  ${p['balance_after']:>9,.2f}   {who}, approved by {p['approved_by']}"
        )
    if not d["payments"]:
        print("  (no payments made)")
    print()
    print(f"total paid out              ${d['total_paid']:>10,.2f}")
    print(f"computed ending balance     ${d['computed_ending']:>10,.2f}")
    print(f"cash_accounts says          ${d['ending_in_db']:>10,.2f}")
    print()
    if d["reconciles"]:
        print("RECONCILES: starting minus payments equals the database balance.")
    else:
        print("DOES NOT RECONCILE. Do not publish these numbers.")
        sys.exit(1)

    if d["not_paid"]:
        print()
        print("approvals that did not become payments:")
        for a in d["not_paid"]:
            print(
                f"  approval {a['id']}  {a['kind']:<15} ${a['amount']:>9,.2f}  "
                f"{a['status']:<9} ticket #{a['ticket_id']}"
            )

    print()
    print("ticket statuses:")
    for t in d["tickets"]:
        print(f"  #{t['id']}  {t['subject']:<24} {t['status']}")


if __name__ == "__main__":
    main()
