"""Run the board to resolution, with a human deciding every payment.

The agents never move money. Between passes this script applies Ashley's
standing policy on the approval queue:

    approve a request the shop can afford, deny one it cannot

That is a human decision recorded under a human name, applied consistently so
the run can be repeated and checked. Nothing here bypasses the approval gate.
Each decision goes through decide_approval and pay_bill exactly as a click on
the dashboard would.

    python output/resolve_board.py
"""

from __future__ import annotations

import asyncio
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp"))

import mcp_server as shop  # noqa: E402

APPROVER = "Ashley Joyce"
MAX_PASSES = 4


def statuses() -> dict[int, str]:
    conn = sqlite3.connect(shop.DB_PATH)
    try:
        return {r[0]: r[1] for r in conn.execute("SELECT id, status FROM tickets ORDER BY id")}
    finally:
        conn.close()


def unfinished() -> list[int]:
    return [i for i, s in statuses().items() if s.lower() not in ("closed", "resolved")]


def decide_queue() -> list[str]:
    """Act as the human on everything pending. Returns what was done."""
    done = []
    for req in shop.list_approvals(status="pending")["approvals"]:
        balance = shop.get_cash_balance()["balance"]
        affordable = req["amount"] <= balance
        decision = "approved" if affordable else "denied"
        shop.decide_approval(
            approval_id=req["id"], decision=decision, decided_by=APPROVER
        )
        if affordable:
            paid = shop.pay_bill(
                kind=req["kind"],
                ref_id=req["ref_id"],
                amount=req["amount"],
                approved_by=APPROVER,
            )
            if paid.get("ok"):
                done.append(
                    f"approved and paid #{req['id']} {req['kind']} ${req['amount']:,.2f} "
                    f"-> balance ${paid['balance_after']:,.2f}"
                )
            else:
                done.append(f"approved #{req['id']} but payment refused: {paid['reason']}")
        else:
            done.append(
                f"denied #{req['id']} {req['kind']} ${req['amount']:,.2f}, "
                f"only ${balance:,.2f} available"
            )
    return done


def run_board() -> None:
    subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(ROOT / "backend/agents.py"), "--board"],
        cwd=ROOT,
        capture_output=True,
    )


def record_runs(before: set[str]) -> None:
    """Note which audit runs this resolution produced, for the reports."""
    import json as _json

    audit_path = ROOT / "output" / "audit_trail.json"
    if not audit_path.exists():
        return
    runs = _json.loads(audit_path.read_text()).get("runs", [])
    mine = [r["run_id"] for r in runs if r["run_id"] not in before]
    (ROOT / "output" / "resolution_runs.json").write_text(
        _json.dumps(
            {
                "note": "The audit runs that make up the resolution pass. Written by "
                "resolve_board.py so reports count this run only, not every run ever made.",
                "run_ids": mine,
            },
            indent=2,
        )
        + "\n"
    )


def main() -> None:
    import json as _json

    audit_path = ROOT / "output" / "audit_trail.json"
    before = set()
    if audit_path.exists():
        before = {r["run_id"] for r in _json.loads(audit_path.read_text()).get("runs", [])}

    print(shop.reset_working_copy())
    print(f"starting balance ${shop.get_cash_balance()['balance']:,.2f}")
    print()

    for n in range(1, MAX_PASSES + 1):
        left = unfinished()
        if not left:
            print(f"all tickets resolved after {n - 1} pass(es)")
            break
        print(f"--- pass {n}: working {left} ---")
        run_board()
        for line in decide_queue():
            print(f"    human: {line}")
        print(f"    statuses: {statuses()}")
        print()

    record_runs(before)
    print("final:", statuses())
    print(f"final balance ${shop.get_cash_balance()['balance']:,.2f}")


if __name__ == "__main__":
    main()
