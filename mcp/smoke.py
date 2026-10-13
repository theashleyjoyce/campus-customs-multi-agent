"""Smoke-test the three Campus Customs MCP tools and save the evidence.

Connects to mcp/mcp_server.py as an MCP client over stdio, runs every case in
CASES, then checks the reported numbers against the database file with direct
SQL. Writes everything to output/mcp_smoke.json.

Run with the board reset first:
    python mcp/mcp_server.py --reset
    python mcp/smoke.py
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
SERVER = HERE / "mcp_server.py"
DB = ROOT / "data" / "campus_customs_new.db"
OUT = ROOT / "output" / "mcp_smoke.json"

# Each case is the prompt a person or agent would ask, the tool that answers
# it, the arguments, whether the tool should accept or refuse, and why that
# matters. They run in order, so the payment cases build on each other.
CASES: list[dict] = [
    {
        "prompt": "Ticket 101: Tauhid Zaman wants one Bulldog tee in size S. Do we have it?",
        "tool": "check_stock",
        "args": {"sku": "CC-TEE-WHITE", "size": "S", "qty_wanted": 1},
        "expect": "accept",
        "why": "Stock is 0, so the shop is short by 1 and the ticket cannot be filled from the shelf.",
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
        "prompt": "How many units of sku NOPE are in stock?",
        "tool": "check_stock",
        "args": {"sku": "NOPE", "size": "S", "qty_wanted": 1},
        "expect": "refuse",
        "why": "An unknown sku is refused rather than answered with an invented number.",
    },
    {
        "prompt": "Ticket 101: the tee is out of stock. Who can reprint it, and will they ship?",
        "tool": "check_vendor_for_restock",
        "args": {"sku": "CC-TEE-WHITE"},
        "expect": "accept",
        "why": "Bulldog Print Co is the 5 day apparel reprinter but is blocked by open invoice 501, 3 days overdue against the shop date of 2026-08-31.",
    },
    {
        "prompt": "Which vendor restocks sku NOPE?",
        "tool": "check_vendor_for_restock",
        "args": {"sku": "NOPE"},
        "expect": "refuse",
        "why": "An unknown sku is refused. This exact case caught a real bug on the first run.",
    },
    {
        "prompt": "Just pay invoice 501 for $840 so the vendor unblocks.",
        "tool": "pay_bill",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 840.0, "approved_by": ""},
        "expect": "refuse",
        "why": "Human approval rule: no named approver means no payment.",
    },
    {
        "prompt": "Ashley approved it, pay $99,999 against the lease.",
        "tool": "pay_bill",
        "args": {"kind": "rent", "ref_id": 1, "amount": 99999.0, "approved_by": "Ashley Joyce"},
        "expect": "refuse",
        "why": "No negative balances: $99,999 against a $3,400 account is turned down.",
    },
    {
        "prompt": "Pay just $1 toward invoice 501, Ashley approved it.",
        "tool": "pay_bill",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 1.0, "approved_by": "Ashley Joyce"},
        "expect": "refuse",
        "why": "An $840 debt must not clear for $1, which would unblock the vendor for free.",
    },
    {
        "prompt": "Pay the $2,400 rent on lease 9999, Ashley approved.",
        "tool": "pay_bill",
        "args": {"kind": "rent", "ref_id": 9999, "amount": 2400.0, "approved_by": "Ashley Joyce"},
        "expect": "refuse",
        "why": "Money must not leave against a lease that is not in the database.",
    },
    {
        "prompt": "Ashley Joyce approved paying invoice 501 for $840. Pay it.",
        "tool": "pay_bill",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 840.0, "approved_by": "Ashley Joyce"},
        "expect": "accept",
        "why": "With approval and the right amount, invoice 501 is paid. Balance $3,400 to $2,560 and the invoice flips to paid.",
    },
    {
        "prompt": "Pay invoice 501 for $840 again, approved by Ashley Joyce.",
        "tool": "pay_bill",
        "args": {"kind": "invoice", "ref_id": 501, "amount": 840.0, "approved_by": "Ashley Joyce"},
        "expect": "refuse",
        "why": "The same invoice cannot be paid twice.",
    },
    {
        "prompt": "Invoice 501 is paid now. Can Bulldog Print Co ship the tee reprint?",
        "tool": "check_vendor_for_restock",
        "args": {"sku": "CC-TEE-WHITE"},
        "expect": "accept",
        "why": "The vendor can ship again, so one approved payment unblocks tickets 101 and 103 together.",
    },
    {
        "prompt": "Ticket 102: Ashley Joyce approved the $2,400 rent on the Chapel Street lease. Pay it.",
        "tool": "pay_bill",
        "args": {"kind": "rent", "ref_id": 1, "amount": 2400.0, "approved_by": "Ashley Joyce"},
        "expect": "accept",
        "why": "Rent on ticket 102 is paid. Balance $2,560 to $160.",
    },
    {
        "prompt": "Ticket 103: Ashley approved a $264 purchase order for the 12 missing hoodies. Place it.",
        "tool": "pay_bill",
        "args": {"kind": "purchase_order", "ref_id": 1, "amount": 264.0, "approved_by": "Ashley Joyce"},
        "expect": "refuse",
        "why": "The restock costs $264 but only $160 is left, so it is refused rather than overdrawing.",
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

    stock = [c for c in calls if c["tool_name"] == "check_stock" and c["tool_output"]["ok"]]
    for call in stock:
        args = call["tool_arguments"]
        compare(
            f"{args['sku']} size {args['size']} on hand",
            "SELECT qty FROM inventory WHERE sku = ? AND size = ?",
            (args["sku"], args["size"]),
            call["tool_output"]["on_hand"],
            lambda r: r[0]["qty"],
        )

    paid = [c for c in calls if c["tool_name"] == "pay_bill" and c["tool_output"]["ok"]]
    compare(
        "invoice 501 status after the approved payment",
        "SELECT status FROM invoices WHERE id = ?",
        (501,),
        "paid",
        lambda r: r[0]["status"],
    )
    compare(
        "checking balance after both approved payments",
        "SELECT balance FROM cash_accounts WHERE name = 'checking'",
        (),
        paid[-1]["tool_output"]["balance_after"],
        lambda r: r[0]["balance"],
    )
    compare(
        "rows written to payments, one per approved payment",
        "SELECT COUNT(*) AS n FROM payments",
        (),
        len(paid),
        lambda r: r[0]["n"],
    )
    compare(
        "approver recorded in the audit trail",
        "SELECT DISTINCT approved_by FROM payments",
        (),
        ["Ashley Joyce"],
        lambda r: [x["approved_by"] for x in r],
    )
    compare(
        "Bulldog Print Co has no open invoices left",
        "SELECT COUNT(*) AS n FROM invoices WHERE vendor_id = 1 AND lower(status) = 'open'",
        (),
        0,
        lambda r: r[0]["n"],
    )
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
        c for c in reversed(calls) if c["tool_name"] == "check_vendor_for_restock" and c["tool_output"]["ok"]
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
            "Every call below went over the MCP protocol to mcp/mcp_server.py. The board "
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
