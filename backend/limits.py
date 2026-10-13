"""Guardrails for the Campus Customs team.

Two kinds of limit live here. One keeps money safe, the other keeps a
multi-agent run from burning tokens forever.

The hard money rules are in the MCP server, because a tool that refuses cannot
be argued with by a model. What is here is the run-level ceiling that no single
tool can see: one payment at a time looks fine, five in a row can empty the
account.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --- token and loop limits -------------------------------------------------

# Any agent may delegate to any other, so boss -> inventory -> accounting ->
# boss is a legal cycle. Depth plus cycle detection is what stops it.
MAX_DELEGATION_DEPTH = 3

# Total hand-offs allowed while working one ticket, across the whole tree.
MAX_DELEGATIONS_PER_TICKET = 8

# Model requests one agent may make inside a single run of its own loop.
MAX_REQUESTS_PER_AGENT = 8

# Model requests for a whole ticket, counted across every agent involved.
MAX_REQUESTS_PER_TICKET = 40


# --- money limits ----------------------------------------------------------

# The most the team may move in one run, no matter how many separate approvals
# it collects. A person approving three things one at a time cannot see the
# total; this can.
MAX_SPEND_PER_RUN_USD = 3_400.00

# An agent may not approve its own request. The requester and the decider must
# be different, and the decider must be a human.
ENFORCE_SEPARATION_OF_DUTIES = True


class LimitReached(Exception):
    """Raised when a run hits a ceiling. Stops the work, does not crash it."""

    def __init__(self, limit: str, detail: str) -> None:
        super().__init__(f"{limit}: {detail}")
        self.limit = limit
        self.detail = detail


@dataclass
class RunLimits:
    """Counters for one ticket or one full board run."""

    delegations_used: int = 0
    requests_used: int = 0
    spend_used_usd: float = 0.0
    dry_run: bool = False
    chain: list[str] = field(default_factory=list)

    def check_delegation(self, to_agent: str) -> None:
        """Depth, budget and cycle checks before one agent calls another."""
        if self.delegations_used >= MAX_DELEGATIONS_PER_TICKET:
            raise LimitReached(
                "delegation budget",
                f"{MAX_DELEGATIONS_PER_TICKET} hand-offs already used on this ticket",
            )
        if len(self.chain) >= MAX_DELEGATION_DEPTH:
            raise LimitReached(
                "delegation depth",
                f"chain is already {' -> '.join(self.chain)}, depth {MAX_DELEGATION_DEPTH}",
            )
        if to_agent in self.chain:
            raise LimitReached(
                "delegation cycle",
                f"{to_agent} is already working this chain: {' -> '.join(self.chain)}",
            )

    def check_requests(self) -> None:
        if self.requests_used >= MAX_REQUESTS_PER_TICKET:
            raise LimitReached(
                "model request budget",
                f"{MAX_REQUESTS_PER_TICKET} model requests already used on this ticket",
            )

    def check_spend(self, amount: float) -> None:
        """The ceiling a single approval cannot see."""
        if self.spend_used_usd + amount > MAX_SPEND_PER_RUN_USD:
            raise LimitReached(
                "run spend cap",
                f"${self.spend_used_usd:,.2f} already moved this run, "
                f"${amount:,.2f} more would pass the ${MAX_SPEND_PER_RUN_USD:,.2f} cap",
            )

    def snapshot(self) -> dict:
        return {
            "delegations_used": self.delegations_used,
            "delegations_allowed": MAX_DELEGATIONS_PER_TICKET,
            "requests_used": self.requests_used,
            "requests_allowed": MAX_REQUESTS_PER_TICKET,
            "spend_used_usd": round(self.spend_used_usd, 2),
            "spend_cap_usd": MAX_SPEND_PER_RUN_USD,
            "dry_run": self.dry_run,
            "chain": list(self.chain),
        }
