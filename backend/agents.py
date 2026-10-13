"""The Campus Customs agent team: Boss, Inventory, Accounting, Facilities and
Customer Service, with full connectivity.

Every agent shares one MCP toolset over data/campus_customs_new.db, so all shop
facts come from the server and there is no second tools layer. Every agent also
gets a `delegate` tool, so any agent may hand work to any other.

Each loop step is appended to output/audit_trail.json as it happens.

CLI, named flags only:
    python backend/agents.py --ticket 101
    python backend/agents.py --board
    python backend/agents.py --board --dry-run
    python backend/agents.py --agent inventory --task "How many CC-TEE-WHITE in S?"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from pydantic_ai import Agent, RunContext  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    BaseToolCallPart,
    BaseToolReturnPart,
    ModelResponse,
    TextPart,
    ThinkingPart,
)
from pydantic_ai.usage import UsageLimits  # noqa: E402

from audit import AuditTrail  # noqa: E402
from config import MODEL_NAME, build_model, mcp_toolset, read_prompt  # noqa: E402
from limits import (  # noqa: E402
    MAX_REQUESTS_PER_AGENT,
    LimitReached,
    RunLimits,
)
from models import AGENT_NAMES, AGENT_ROLES, DelegationResult  # noqa: E402

ROOT = HERE.parent


@dataclass
class TeamDeps:
    """Shared state for one ticket. Passed down through every delegation."""

    audit: AuditTrail
    limits: RunLimits
    ticket_id: int | None = None
    delegations: list[DelegationResult] = field(default_factory=list)

    def child(self, agent_name: str) -> "TeamDeps":
        """Deps for a delegated call, with the chain extended by one."""
        child_limits = RunLimits(
            delegations_used=self.limits.delegations_used,
            requests_used=self.limits.requests_used,
            spend_used_usd=self.limits.spend_used_usd,
            dry_run=self.limits.dry_run,
            chain=[*self.limits.chain, agent_name],
        )
        return TeamDeps(
            audit=self.audit,
            limits=child_limits,
            ticket_id=self.ticket_id,
            delegations=self.delegations,
        )


_AGENTS: dict[str, Agent] = {}


def _roster_for(name: str) -> str:
    """The other four seats, so each agent knows who it can call."""
    others = [f"- **{n}** — {AGENT_ROLES[n]}" for n in AGENT_NAMES if n != name]
    return (
        "\n\n## Who you can delegate to\n\n"
        + "\n".join(others)
        + "\n\nUse the `delegate` tool. Any agent may call any other agent."
    )


def build_agent(name: str) -> Agent:
    """One agent: its prompt, the shared MCP toolset, and the delegate tool."""
    if name in _AGENTS:
        return _AGENTS[name]

    agent = Agent(
        build_model(),
        deps_type=TeamDeps,
        output_type=str,
        name=name,
        instructions=read_prompt(name) + _roster_for(name),
        toolsets=[mcp_toolset()],
    )

    @agent.tool
    async def delegate(
        ctx: RunContext[TeamDeps], to_agent: str, task: str, ticket_id: int = 0
    ) -> dict[str, Any]:
        """Hand a piece of work to a teammate and wait for their answer.

        Args:
            to_agent: One of inventory, accounting, facilities, customer_service, boss.
            task: A specific question or instruction. Name the sku, size,
                quantity, invoice id or lease id you mean.
            ticket_id: Which ticket this is about, if any.
        """
        deps = ctx.deps
        target = to_agent.strip().lower()

        if target not in AGENT_NAMES:
            return {
                "ok": False,
                "reason": f"There is no agent called {to_agent!r}. "
                f"The team is: {', '.join(AGENT_NAMES)}.",
            }
        if target == name:
            return {"ok": False, "reason": "An agent cannot delegate to itself."}

        try:
            deps.limits.check_delegation(target)
        except LimitReached as exc:
            deps.audit.record(
                "refusal", name, limit=exc.limit, detail=exc.detail, to_agent=target
            )
            return {
                "ok": False,
                "reason": f"Delegation refused ({exc.limit}): {exc.detail}. "
                "Answer with what you already have.",
            }

        deps.limits.delegations_used += 1
        deps.audit.record(
            "delegation_start",
            name,
            to_agent=target,
            task=task,
            ticket_id=ticket_id or deps.ticket_id,
            chain=[*deps.limits.chain, target],
        )

        try:
            reply = await _run_agent(
                target,
                task,
                deps.child(target),
                ticket_id=ticket_id or deps.ticket_id,
            )
            result = DelegationResult(
                from_agent=name,
                to_agent=target,
                task=task,
                ticket_id=ticket_id or deps.ticket_id,
                reply=reply,
                status="done",
            )
        except Exception as exc:
            result = DelegationResult(
                from_agent=name,
                to_agent=target,
                task=task,
                ticket_id=ticket_id or deps.ticket_id,
                reply=f"{target} could not finish: {exc}",
                status="error",
                error=str(exc),
            )

        deps.delegations.append(result)
        deps.audit.record(
            "delegation_end",
            name,
            to_agent=target,
            status=result.status,
            reply=result.reply,
            ticket_id=result.ticket_id,
        )
        return result.model_dump()

    _AGENTS[name] = agent
    return agent


async def _run_agent(
    name: str, task: str, deps: TeamDeps, ticket_id: int | None = None
) -> str:
    """Run one agent's loop, auditing every node as it goes."""
    agent = build_agent(name)
    deps.audit.record("prompt", name, task=task, ticket_id=ticket_id, chain=deps.limits.chain)

    step = 0
    async with agent.iter(
        task,
        deps=deps,
        usage_limits=UsageLimits(request_limit=MAX_REQUESTS_PER_AGENT),
    ) as run:
        async for node in run:
            step += 1

            if Agent.is_model_request_node(node):
                returns = [
                    {"tool": p.tool_name, "result": p.model_response_str()}
                    for p in node.request.parts
                    if isinstance(p, BaseToolReturnPart)
                ]
                if returns:
                    deps.audit.record(
                        "tool_result", name, step=step, ticket_id=ticket_id, results=returns
                    )

            elif Agent.is_call_tools_node(node):
                response: ModelResponse = node.model_response
                text = "".join(p.content for p in response.parts if isinstance(p, TextPart))
                thinking = "".join(
                    p.content for p in response.parts if isinstance(p, ThinkingPart)
                )
                calls = [
                    {"tool": p.tool_name, "args": p.args_as_dict()}
                    for p in response.parts
                    if isinstance(p, BaseToolCallPart)
                ]
                deps.limits.requests_used += 1
                deps.audit.record(
                    "model_response",
                    name,
                    step=step,
                    ticket_id=ticket_id,
                    text=text,
                    thinking=thinking,
                    tool_calls=calls,
                    usage={
                        "input_tokens": getattr(response.usage, "input_tokens", 0) or 0,
                        "output_tokens": getattr(response.usage, "output_tokens", 0) or 0,
                    },
                )
                for call in calls:
                    if call["tool"] != "delegate":
                        deps.audit.record(
                            "tool_call",
                            name,
                            step=step,
                            ticket_id=ticket_id,
                            tool=call["tool"],
                            args=call["args"],
                        )

            elif Agent.is_end_node(node):
                answer = str(node.data.output).strip()
                deps.audit.record("answer", name, ticket_id=ticket_id, answer=answer)
                return answer

    return str(run.result.output).strip() if run.result else ""


async def run_ticket(
    ticket_id: int,
    dry_run: bool = False,
    audit: AuditTrail | None = None,
    sink: Any = None,
) -> dict:
    """Work one ticket, boss first. Returns the outcome and the audit run id."""
    trail = audit or AuditTrail(f"ticket {ticket_id}", MODEL_NAME, sink=sink)
    limits = RunLimits(dry_run=dry_run, chain=["boss"])
    deps = TeamDeps(audit=trail, limits=limits, ticket_id=ticket_id)

    trail.record(
        "run_start",
        "boss",
        ticket_id=ticket_id,
        dry_run=dry_run,
        limits=limits.snapshot(),
    )
    task = (
        f"Work ticket {ticket_id}. Read it first with get_ticket, then delegate the "
        f"specialist parts to the right teammates, then decide and record what you decided."
    )
    if dry_run:
        task += (
            " This is a DRY RUN. Investigate and say what you would do, but do not call "
            "pay_bill, update_ticket, receive_stock or decide_approval."
        )

    try:
        answer = await _run_agent("boss", task, deps, ticket_id=ticket_id)
        status = "resolved"
    except LimitReached as exc:
        answer = f"Stopped on a limit ({exc.limit}): {exc.detail}"
        status = "blocked"
        trail.record("error", "boss", ticket_id=ticket_id, limit=exc.limit, detail=exc.detail)
    except Exception as exc:
        answer = f"The run failed: {exc}"
        status = "error"
        trail.record("error", "boss", ticket_id=ticket_id, error=str(exc))

    trail.record("run_end", "boss", ticket_id=ticket_id, status=status, limits=limits.snapshot())
    return {
        "ticket_id": ticket_id,
        "status": status,
        "answer": answer,
        "delegations": [d.model_dump() for d in deps.delegations],
        "limits": limits.snapshot(),
        "audit_run_id": trail.run_id,
    }


async def run_board(dry_run: bool = False, sink: Any = None) -> dict:
    """Work every open ticket in turn, sharing one audit run."""
    import sqlite3

    db = ROOT / "data" / "campus_customs_new.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    today = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"]
    # Anything not finished is still work. A ticket parked on 'waiting' for a
    # human decision has to be picked back up once that decision is made,
    # otherwise it can never reach resolved.
    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM tickets WHERE lower(status) NOT IN ('closed','resolved') ORDER BY id"
        )
    ]
    cash_start = conn.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()["balance"]
    conn.close()

    trail = AuditTrail(f"board run, {len(ids)} unfinished tickets", MODEL_NAME, sink=sink)
    trail.record("run_start", "boss", today=today, tickets=ids, dry_run=dry_run, cash=cash_start)

    outcomes = []
    for ticket_id in ids:
        outcomes.append(await run_ticket(ticket_id, dry_run=dry_run, audit=trail))

    conn = sqlite3.connect(db)
    cash_end = conn.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
    conn.close()

    trail.record("run_end", "boss", cash_at_end=cash_end, tickets_worked=len(outcomes))
    return {
        "today": today,
        "tickets_seen": ids,
        "cash_at_start": cash_start,
        "cash_at_end": cash_end,
        "outcomes": outcomes,
        "audit_run_id": trail.run_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Customs agent team")
    parser.add_argument("--ticket", type=int, help="Work one ticket by id, for example 101")
    parser.add_argument("--board", action="store_true", help="Work every open ticket")
    parser.add_argument("--agent", type=str, help="Run one agent directly")
    parser.add_argument("--task", type=str, default="", help="The task for --agent")
    parser.add_argument("--dry-run", action="store_true", help="Investigate but write nothing")
    args = parser.parse_args()

    if args.agent:
        if not args.task:
            parser.error("--agent needs --task")
        trail = AuditTrail(f"single agent: {args.agent}", MODEL_NAME)
        deps = TeamDeps(audit=trail, limits=RunLimits(dry_run=args.dry_run, chain=[args.agent]))
        result = asyncio.run(_run_agent(args.agent, args.task, deps))
        print(result)
    elif args.board:
        print(json.dumps(asyncio.run(run_board(dry_run=args.dry_run)), indent=2, default=str))
    elif args.ticket:
        print(json.dumps(asyncio.run(run_ticket(args.ticket, dry_run=args.dry_run)), indent=2, default=str))
    else:
        parser.error("pass --ticket, --board, or --agent with --task")


if __name__ == "__main__":
    main()
