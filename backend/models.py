"""Every typed object the Campus Customs agent team uses.

Nothing structured is declared inline in agents.py or team.py. When an agent
needs a new return shape it is added here.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# The five seats on the team. Any agent may delegate to any other, so this
# tuple is also the full set of valid delegation targets.
AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]

AGENT_NAMES: tuple[str, ...] = (
    "boss",
    "inventory",
    "accounting",
    "facilities",
    "customer_service",
)

AGENT_ROLES: dict[str, str] = {
    "boss": "Reads each ticket, decides who should work it, and makes the final call.",
    "inventory": "Checks stock by sku and size, spots shortfalls, works out which vendor can restock.",
    "accounting": "Watches cash and invoices, checks margins, prepares payments for human approval.",
    "facilities": "Handles the shop space, leases and rent.",
    "customer_service": "Drafts messages to customers and requesters.",
}


class DelegationRequest(BaseModel):
    """One agent asking another for help."""

    to_agent: AgentName
    task: str = Field(min_length=1)
    ticket_id: int | None = None


class DelegationResult(BaseModel):
    """What came back from a delegated task."""

    from_agent: str
    to_agent: str
    task: str
    ticket_id: int | None = None
    reply: str = ""
    status: Literal["done", "error"] = "done"
    error: str | None = None


class ApprovalRequest(BaseModel):
    """Money the team wants to spend, waiting on a human.

    Nothing is paid from this object alone. A human approves it on the
    dashboard, and only then does the payment tool get a named approver.
    """

    kind: Literal["invoice", "rent", "purchase_order"]
    ref_id: int
    amount: float = Field(gt=0)
    reason: str
    ticket_id: int | None = None
    requested_by: str = "accounting"
    status: Literal["pending", "approved", "denied", "paid"] = "pending"
    approved_by: str | None = None


class DraftMessage(BaseModel):
    """A customer reply that stays on the board. Never sent."""

    ticket_id: int
    to: str
    subject: str
    body: str
    sent: Literal[False] = False


class TicketPlan(BaseModel):
    """What the team intends to do about one ticket."""

    ticket_id: int
    summary: str
    blocked_by: str | None = None
    steps: list[str] = Field(default_factory=list)
    agents_involved: list[str] = Field(default_factory=list)
    approvals_needed: list[ApprovalRequest] = Field(default_factory=list)


class TicketOutcome(BaseModel):
    """The result of working one ticket end to end."""

    ticket_id: int
    status: Literal["resolved", "waiting_on_approval", "blocked", "error"]
    answer: str
    delegations: list[DelegationResult] = Field(default_factory=list)
    approvals: list[ApprovalRequest] = Field(default_factory=list)
    drafts: list[DraftMessage] = Field(default_factory=list)


class DeskRun(BaseModel):
    """A full pass over the board."""

    today: str
    tickets_seen: list[int] = Field(default_factory=list)
    outcomes: list[TicketOutcome] = Field(default_factory=list)
    cash_at_start: float | None = None
    cash_at_end: float | None = None
    notes: list[str] = Field(default_factory=list)


class AgentEvent(BaseModel):
    """One line of the live feed the dashboard renders."""

    seq: int = 0
    kind: str
    agent: str
    ticket_id: int | None = None
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
