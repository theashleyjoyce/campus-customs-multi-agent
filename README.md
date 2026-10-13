# Campus Customs Multi-Agent Operations

Homework 5, MGT 409 AI Foundations for Managers.

Campus Customs is a small Yale apparel shop. Open tickets land on a board:
customer orders, rent notices, unpaid bills, discount requests. This project
builds the agent team that works that board, the MCP server it runs on, the
FastAPI backend in between, and the React dashboard a human watches it from.

**Repo:** https://github.com/theashleyjoyce/campus-customs-multi-agent

## How to run it

Everything below assumes you are in this folder.

### 0. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

Put your OpenAI key in a `.env` file. See `.env.example` for the shape. The
real `.env` is not in this repo.

### 1. Copy the original database to the working copy

`data/campus_customs.db` is the original and is never written to.
`data/campus_customs_new.db` is the working copy that the MCP server and the
backend actually use. Both are committed, so you can skip straight to step 2 if
you just want to look around.

To get a clean board:

```bash
python mcp_server/server.py --reset
```

That copies the original over the working copy. Do this **before any full
three-ticket run**, so every run starts from the same board: three open
tickets, $3,400.00 in checking, and invoice 501 unpaid.

You can also copy it by hand:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

### 2. Start the MCP server

```bash
python mcp_server/server.py          # stdio
python mcp_server/server.py --http   # or Streamable HTTP on port 8001
```

The backend attaches this server **in process**, so for the normal flow you do
not need to run it separately. Run it on its own when you want to attach a
vibe coder to it directly. `.mcp.json` in this folder registers it for Claude
Code.

### 3. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Check it with http://localhost:8000/api/health, or browse the routes at
http://localhost:8000/docs.

### 4. Start the React board

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The backend allows the Vite origin, so the browser
is permitted to call it.

### 5. Run the three tickets

Reset first, then either drive it from the dashboard or from the command line.

**From the dashboard.** Press *Run the team* on a ticket, watch the agents work,
and approve payments when the team asks. Cash only changes when you click
approve.

**From the command line.**

```bash
python mcp_server/server.py --reset     # always reset before a full run
python backend/agents.py --ticket 101   # one ticket
python backend/agents.py --board        # every unfinished ticket
python backend/agents.py --board --dry-run
```

**All the way to resolved.** The agents stop whenever money is needed, so a
full resolution takes several passes with a human deciding in between. This
script does the whole thing, resetting first and applying one policy on the
approval queue: approve what the shop can afford, deny what it cannot.

```bash
python output/resolve_board.py
```

### 6. Check the money

```bash
python output/cash_reconcile.py
```

It reads the starting balance from the untouched original, sums the payments
table, and compares that to `cash_accounts`. It refuses to print numbers that
do not balance.

## What is here

| Folder | What it holds |
|---|---|
| `mcp_server/` | The FastMCP server. Seventeen tools over the shop database. Every shop fact an agent uses comes through here |
| `backend/` | The five PydanticAI agents, their prompts, the typed models, the guardrails, the audit trail, and the API routes |
| `frontend/` | The React dashboard |
| `data/` | The original database and the working copy |
| `output/` | Working notes, the plan, the resolved board, the cash reconciliation and the audit trail |

## The agent team

Five agents, each with its own prompt in `backend/prompts/`:

- **Boss** reads each ticket, decides who works it, makes the final call
- **Inventory** checks stock by sku and size, spots shortfalls, finds vendors
- **Accounting** watches cash and invoices, checks margins, prepares payments
- **Facilities** handles the leases and rent
- **Customer Service** drafts the replies

**Full connectivity.** Every agent can delegate to every other agent. On the
recorded run, Inventory asked Accounting about a blocking invoice directly and
Customer Service checked both specialists before writing to the customer.
Neither went through the Boss.

## How the board fits together

The three starting tickets are deliberately interlocked.

Ticket 101 wants a tee that is out of stock. The only apparel vendor is frozen
by an $840 invoice three days overdue. Ticket 103 wants 20 hoodies and is 12
short, which routes to the same frozen vendor, so one payment unblocks both.
Ticket 102 is rent, $2,400, due in two days.

Checking holds $3,400. The invoice and the rent come to $3,240, which fits with
$160 left. A $264 hoodie restock afterwards does not fit. The refusal rules are
reachable from the starting data, not theoretical.

## Safety

The shop rules are enforced in the MCP server, not in the prompts. A prompt is
advice and a model can argue with advice. A tool that refuses cannot be argued
with.

- A payment needs a named human approver **and** an approval record that person
  actually decided
- The balance never goes negative
- A bill settles at the amount owed, so an $840 invoice cannot clear for $1
- Rent cannot be paid twice, and a settled bill cannot be re-requested
- Money cannot leave against a reference that is not in the database
- Nothing is ever sent to a customer or a vendor

On top of that, `backend/limits.py` adds what no single tool can see: a spend
cap for a whole run, separation of duties, a dry run mode, and limits on
delegation depth, cycles and token use.

## Tests

```bash
python mcp_server/server.py --reset
python mcp_server/test_tools.py    # 35 checks over the MCP protocol
python mcp_server/smoke.py         # writes output/mcp_smoke.json
```

Note that both of those reset the board, so re-run `output/resolve_board.py`
afterwards if you want the resolved state back.

## Output

| File | What it is |
|---|---|
| `output/harness.md` | Working notes across the whole assignment: tables, tools, agents, routes, dashboard, safety |
| `output/design.md` | Why the dashboard looks the way it does, including what changed and why |
| `output/desk_tickets.html` | The plan written before the backend existed, the actual run beside it, the cash, and the reflection. Double click to open |
| `output/resolved_board.html` | A screenshot of the dashboard for each resolved ticket. Double click to open |
| `output/resolved_tickets.json` | Per ticket: final status, outcome, what each agent contributed, every human approval |
| `output/mcp_smoke.json` | Evidence of every MCP tool being called, with the prompt, the tool and the output |
| `output/audit_trail.json` | Every agent run, appended, never wiped |

## A note on the model

The assignment specifies `gpt-6-luna` through Portkey. I have no Portkey key
and my OpenAI project has no access to that model, so this runs on my OpenAI
key with `gpt-5.6-luna`. The instructor is aware. It is one constant in
`backend/config.py` if that changes.
