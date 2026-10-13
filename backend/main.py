"""Campus Customs backend: routes only.

The dashboard talks to these routes. Everything underneath comes from the MCP
server over data/campus_customs_new.db, so there is no second path to the shop
data. The routes read through the same tools the agents use.

Run from this folder:
    uvicorn main:app --reload --port 8000

Frontend (Vite): http://127.0.0.1:5173
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for folder in (HERE, ROOT / "mcp_server"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import server as shop  # noqa: E402
from agents import run_board, run_ticket  # noqa: E402
from audit import AUDIT_PATH  # noqa: E402
from config import MODEL_NAME  # noqa: E402
from limits import (  # noqa: E402
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MAX_REQUESTS_PER_TICKET,
    MAX_SPEND_PER_RUN_USD,
)
from models import AGENT_NAMES, AGENT_ROLES  # noqa: E402

app = FastAPI(title="Campus Customs Multi-Agent Operations", version="1.0.0")
# The dashboard runs on the Vite dev server, a different origin from this API,
# so the browser needs that origin allowed before it will make the calls at
# all. Vite uses 5173 by default but moves to 5174 and upward when that port is
# busy, so any localhost port is allowed rather than one hard coded number.
# Still localhost only. Nothing off this machine can call these routes.
VITE_ORIGIN_PATTERN = r"http://(localhost|127\.0\.0\.1):\d+"

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=VITE_ORIGIN_PATTERN,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# request bodies
# --------------------------------------------------------------------------


class RunRequest(BaseModel):
    """Ask the team to work a ticket, or the whole board."""

    ticket_id: int | None = None
    dry_run: bool = False


class DecisionRequest(BaseModel):
    """A human deciding on a pending approval."""

    decision: str = Field(pattern="^(approved|denied)$")
    decided_by: str = Field(min_length=1)


class PayRequest(BaseModel):
    """Settle an approved request. Needs the approver's name."""

    approved_by: str = Field(min_length=1)


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    """Turn a tool refusal into a 400 so the dashboard sees a real error."""
    if not result.get("ok", True):
        raise HTTPException(status_code=400, detail=result.get("reason", "Refused."))
    return result


# --------------------------------------------------------------------------
# read routes
# --------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    """Is the shop reachable, and what is it running on."""
    try:
        today = shop.get_today()
        tickets = shop.list_tickets(status="open")
        cash = shop.get_cash_balance()
        return {
            "ok": True,
            "model": MODEL_NAME,
            "database": shop.DB_PATH.name,
            "today": today["date_today"],
            "open_tickets": tickets["count"],
            "cash": cash["balance"],
            "tools": 17,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "model": MODEL_NAME}


@app.get("/api/team")
def team() -> dict:
    """The roster the dashboard draws."""
    return {
        "agents": [{"name": n, "role": AGENT_ROLES[n]} for n in AGENT_NAMES],
        "limits": {
            "delegation_depth": MAX_DELEGATION_DEPTH,
            "delegations_per_ticket": MAX_DELEGATIONS_PER_TICKET,
            "requests_per_ticket": MAX_REQUESTS_PER_TICKET,
            "spend_cap_usd": MAX_SPEND_PER_RUN_USD,
        },
    }


@app.get("/api/tickets")
def tickets(status: str = "all") -> dict:
    """The board."""
    return _unwrap(shop.list_tickets(status=status))


@app.get("/api/tickets/{ticket_id}")
def ticket(ticket_id: int) -> dict:
    """One ticket with its linked lease, invoice, vendor, price and stock."""
    result = shop.get_ticket(ticket_id=ticket_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("reason", "Not found."))
    return result


@app.get("/api/cash")
def cash() -> dict:
    """Balance, invoices and every payment made. The money tab.

    Cash only goes out in this shop, so the payments list is the whole story.
    """
    balance = _unwrap(shop.get_cash_balance())
    invoices = _unwrap(shop.list_invoices(status="all"))
    payments = shop._query("SELECT * FROM payments ORDER BY id")
    return {
        "ok": True,
        "today": invoices["today"],
        "balance": balance["balance"],
        "as_of": balance["as_of"],
        "spent": round(sum(p["amount"] for p in payments), 2),
        "payments": payments,
        "invoices": invoices["invoices"],
    }


@app.get("/api/approvals")
def approvals(status: str = "all") -> dict:
    """The approval queue a human works from."""
    return _unwrap(shop.list_approvals(status=status))


@app.get("/api/audit")
def audit(run_id: str = "", limit: int = 200) -> dict:
    """Recent audit runs, or the steps of one run."""
    if not AUDIT_PATH.exists():
        return {"ok": True, "run_count": 0, "runs": []}
    data = json.loads(AUDIT_PATH.read_text())
    runs = data.get("runs", [])
    if run_id:
        match = next((r for r in runs if r["run_id"] == run_id), None)
        if not match:
            raise HTTPException(status_code=404, detail=f"No audit run {run_id}.")
        return {"ok": True, "run": {**match, "steps": match["steps"][-limit:]}}
    return {
        "ok": True,
        "run_count": len(runs),
        "runs": [
            {k: v for k, v in r.items() if k != "steps"} | {"step_count": len(r["steps"])}
            for r in runs
        ],
    }


# --------------------------------------------------------------------------
# human-in-the-loop routes
# --------------------------------------------------------------------------


@app.post("/api/approvals/{approval_id}/decide")
def decide(approval_id: int, body: DecisionRequest) -> dict:
    """A person approves or denies a pending request. Spends nothing."""
    return _unwrap(
        shop.decide_approval(
            approval_id=approval_id, decision=body.decision, decided_by=body.decided_by
        )
    )


@app.post("/api/approvals/{approval_id}/pay")
def pay(approval_id: int, body: PayRequest) -> dict:
    """Settle an approved request. This is the only route that moves money.

    The request has to be approved first, and the name on the payment is the
    name of the person who approved it.
    """
    queue = _unwrap(shop.list_approvals(status="all"))
    row = next((a for a in queue["approvals"] if a["id"] == approval_id), None)
    if not row:
        raise HTTPException(status_code=404, detail=f"No approval request {approval_id}.")
    if row["status"] != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Approval {approval_id} is {row['status']}, not approved. "
            "A human has to approve it before it can be paid.",
        )
    return _unwrap(
        shop.pay_bill(
            kind=row["kind"], ref_id=row["ref_id"], amount=row["amount"], approved_by=body.approved_by
        )
    )


@app.post("/api/reset")
def reset() -> dict:
    """Put the board back to its opening state before a fresh run."""
    return {"ok": True, **shop.reset_working_copy()}


@app.get("/api/events")
def events(run_id: str = "", since: int = 0, limit: int = 200) -> dict:
    """What each agent said and which tools it used, for the dashboard to poll.

    Defaults to the latest run. Pass `since` with the last seq you saw to get
    only what is new, so the dashboard can refresh without re-reading the run.
    """
    if not AUDIT_PATH.exists():
        return {"ok": True, "run_id": None, "events": [], "latest_seq": 0}

    runs = json.loads(AUDIT_PATH.read_text()).get("runs", [])
    if not runs:
        return {"ok": True, "run_id": None, "events": [], "latest_seq": 0}

    run = next((r for r in runs if r["run_id"] == run_id), None) if run_id else runs[-1]
    if run is None:
        raise HTTPException(status_code=404, detail=f"No audit run {run_id}.")

    feed = []
    for step in run["steps"]:
        if step["seq"] <= since:
            continue
        kind = step["kind"]
        entry = {
            "seq": step["seq"],
            "at": step["at"],
            "agent": step["agent"],
            "kind": kind,
            "ticket_id": step.get("ticket_id"),
            "said": "",
            "tools": [],
        }
        if kind == "model_response":
            entry["said"] = step.get("text") or ""
            entry["tools"] = [c["tool"] for c in step.get("tool_calls", []) or []]
        elif kind == "tool_call":
            entry["tools"] = [step.get("tool")]
            entry["said"] = f"called {step.get('tool')}"
        elif kind == "answer":
            entry["said"] = step.get("answer") or ""
        elif kind == "delegation_start":
            entry["said"] = f"asked {step.get('to_agent')}: {step.get('task', '')}"
            entry["to_agent"] = step.get("to_agent")
        elif kind == "delegation_end":
            entry["said"] = f"{step.get('to_agent')} replied"
            entry["to_agent"] = step.get("to_agent")
        elif kind in ("refusal", "error"):
            entry["said"] = step.get("detail") or step.get("error") or "refused"
        if entry["said"] or entry["tools"] or kind in ("run_start", "run_end"):
            feed.append(entry)

    return {
        "ok": True,
        "run_id": run["run_id"],
        "label": run["label"],
        "agents_involved": run["agents_involved"],
        "latest_seq": run["steps"][-1]["seq"] if run["steps"] else 0,
        "count": len(feed[-limit:]),
        "events": feed[-limit:],
    }


@app.post("/api/approvals/{approval_id}/approve")
def approve_and_pay(approval_id: int, body: DecisionRequest) -> dict:
    """One click: a human approves, and the money actually moves.

    The agents only ever prepare a payment. This route is where cash changes.
    The amount comes from the approval record, never from the caller, so an
    $840 request cannot be paid as $8,400.
    """
    if body.decision != "approved":
        return _unwrap(
            shop.decide_approval(
                approval_id=approval_id, decision="denied", decided_by=body.decided_by
            )
        )

    decision = _unwrap(
        shop.decide_approval(
            approval_id=approval_id, decision="approved", decided_by=body.decided_by
        )
    )
    payment = _unwrap(
        shop.pay_bill(
            kind=decision["kind"],
            ref_id=decision["ref_id"],
            amount=decision["amount"],
            approved_by=body.decided_by,
        )
    )
    return {
        "ok": True,
        "approval_id": approval_id,
        "approved_by": body.decided_by,
        "paid": payment["amount"],
        "balance_before": payment["balance_before"],
        "balance_after": payment["balance_after"],
        "invoice_marked_paid": payment["invoice_marked_paid"],
    }

# --------------------------------------------------------------------------
# agent routes
# --------------------------------------------------------------------------


@app.post("/api/run")
async def run(body: RunRequest) -> dict:
    """Work a ticket, or the whole board, and return when it is done."""
    if body.ticket_id:
        return await run_ticket(body.ticket_id, dry_run=body.dry_run)
    return await run_board(dry_run=body.dry_run)


@app.post("/api/run/stream")
async def run_stream(body: RunRequest) -> StreamingResponse:
    """The same work, streamed step by step so a human can watch.

    Every audit step becomes an SSE event, so the dashboard sees each tool
    call, each delegation and each answer as it happens rather than at the end.
    """
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def sink(step: dict[str, Any]) -> None:
        # Called from the agent's thread of execution; hand it to the loop.
        loop.call_soon_threadsafe(queue.put_nowait, step)

    async def work() -> None:
        try:
            if body.ticket_id:
                result = await run_ticket(body.ticket_id, dry_run=body.dry_run, sink=sink)
            else:
                result = await run_board(dry_run=body.dry_run, sink=sink)
            await queue.put({"kind": "complete", "agent": "boss", "result": result})
        except Exception as exc:
            await queue.put({"kind": "failed", "agent": "boss", "error": str(exc)})
        finally:
            await queue.put(None)

    task = asyncio.create_task(work())

    async def events():
        try:
            while (step := await queue.get()) is not None:
                payload = json.dumps(step, ensure_ascii=False, default=str)
                yield f"event: {step.get('kind', 'step')}\ndata: {payload}\n\n"
        finally:
            if not task.done():
                # Dashboard hung up. Stop spending tokens.
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
