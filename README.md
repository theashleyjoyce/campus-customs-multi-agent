# Campus Customs Multi-Agent Operations

Homework 5, MGT 409 AI Foundations for Managers.

Campus Customs is a small Yale apparel shop. Open tickets land on a board:
customer orders, rent notices, unpaid bills, discount requests. This project
builds the agent team that works that board, the MCP server it runs on, and the
guardrails that keep it from spending money it should not.

## What is here

| Folder | What it holds |
|---|---|
| `mcp/` | The FastMCP server. Seventeen tools over the shop database. Every shop fact an agent uses comes through here. |
| `backend/` | The five PydanticAI agents, their prompts, the typed models, the guardrails and the audit trail. |
| `data/` | `campus_customs.db` is the original and is never written to. `campus_customs_new.db` is the working copy. |
| `output/` | `harness.md` is the working notes, `mcp_smoke.json` is the tool evidence, `audit_trail.json` is every agent run. |

## The agent team

Five agents, each with its own prompt in `backend/prompts/`:

- **Boss** reads each ticket, decides who works it, makes the final call
- **Inventory** checks stock by sku and size, spots shortfalls, finds vendors
- **Accounting** watches cash and invoices, checks margins, prepares payments
- **Facilities** handles the leases and rent
- **Customer Service** drafts the replies

**Full connectivity.** Every agent can delegate to every other agent. On a real
run, inventory asked accounting about a blocking invoice directly, and customer
service checked both specialists before writing to the customer. Neither went
through the boss.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The OpenAI key is read from the single `.env` at the workspace root.

## Running it

```bash
# Always reset before a full run
python mcp/mcp_server.py --reset

# Work one ticket
python backend/agents.py --ticket 101

# Work the whole board
python backend/agents.py --board

# Rehearse without writing anything
python backend/agents.py --board --dry-run

# Run one agent on its own
python backend/agents.py --agent inventory --task "How many CC-TEE-WHITE in size S?"
```

## Tests

```bash
python mcp/mcp_server.py --reset
python mcp/test_tools.py    # 26 checks over the MCP protocol
python mcp/smoke.py         # writes output/mcp_smoke.json
```

## How the board fits together

The three starting tickets are deliberately interlocked.

Ticket 101 wants a tee that is out of stock. The only apparel vendor is frozen
by an $840 invoice that is three days overdue. Ticket 103 wants 20 hoodies and
is 12 short, which routes to the same frozen vendor. So one payment unblocks
both. Ticket 102 is rent, $2,400, due in two days.

Checking holds $3,400. The invoice and the rent come to $3,240 together, which
fits with $160 left. A $264 restock afterwards does not fit. The refusal rules
are reachable from the starting data, not theoretical.

## Safety

The shop rules are enforced in the MCP server, not in the prompts. A prompt is
advice and a model can argue with advice. A tool that refuses cannot be argued
with.

- A payment needs a named human approver
- The balance never goes negative
- A bill settles at the amount owed, so an $840 invoice cannot clear for $1
- Money cannot leave against a reference that is not in the database
- Nothing is ever sent to a customer or a vendor

On top of that, `backend/limits.py` adds what no single tool can see: a spend
cap for a whole run, separation of duties, a dry run mode, and limits on
delegation depth, cycles and token use.

See `output/harness.md` for the full write-up.

## A note on the model

The assignment specifies `gpt-6-luna` through Portkey. I have no Portkey key and
my OpenAI project has no access to that model, so this runs on my OpenAI key
with `gpt-5.6-luna`. The instructor is aware. It is one constant in
`backend/config.py` if that changes.
