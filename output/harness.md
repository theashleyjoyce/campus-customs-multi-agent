# Campus Customs Harness

Working notes for homework 5. This document grows as the assignment goes on.

---

## What this system is

Campus Customs is a small Yale apparel shop. Tickets land on a board and a team
of five agents works them. There are three pieces, and they talk to each other
in one direction only.

```
   React dashboard  ──HTTP──▶  FastAPI backend  ──in process──▶  MCP server
   frontend/                   backend/                          mcp/
   watch and approve           routes and agents                 the only way
                                                                 to the database
                                                                       │
                                                               data/campus_
                                                               customs_new.db
```

Everything the shop knows comes through the MCP server. The dashboard has no
database connection, the agents have no database connection, and there is no
second tools layer. That is what makes the shop rules enforceable: they live in
one place that both the humans and the agents have to go through.

What is in this document:

| Section | Covers |
|---|---|
| Problem 2 | The nine tables and what each one is for |
| Problem 3 | The first three MCP tools and which ticket each unlocks |
| Problem 4 | Connecting the server to the vibe coder and testing every tool |
| Problem 5 | All seventeen MCP tools, the five agents, safety and guardrails |
| Problem 7 | Every API route, one line each |
| Problem 8 | The dashboard |
| Problem 9 | The full run, the cash, and what the agents actually did |


## Problem 2: Study the Campus Customs database

`data/campus_customs.db` is a SQLite file with nine tables, about 53 KB and 23
rows in total. Nothing an agent says should be invented if it cannot be traced
back to one of these rows.

`data/campus_customs_new.db` is the working copy. The MCP server and the
backend both point at that file so the original stays clean and a run can be
reset by copying it back.

### `desk` (1 row)

Fields: `date_today`, `notes`

**Why it matters to the agents:** it holds the shop's today, `2026-08-31`, so
every overdue check uses this date instead of the real clock.

### `tickets` (3 rows)

Fields: `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`,
`lease_id`, `invoice_id`, `status`, `notes`, `created_at`

**Why it matters to the agents:** it is the board itself, and `type` is what
the Boss reads to decide which agent takes the work.

### `inventory` (10 rows)

Fields: `sku`, `name`, `size`, `qty`, `location`

**Why it matters to the agents:** it is the only stock truth, keyed on sku plus
size, so Inventory uses it to find shortfalls like the tee sitting at zero.

### `pricing` (4 rows)

Fields: `sku`, `unit_cost`, `list_price`

**Why it matters to the agents:** it gives Accounting the cost and list price
that set the floor on any discount request.

### `vendors` (3 rows)

Fields: `id`, `name`, `specialty`, `lead_days`

**Why it matters to the agents:** `specialty` picks the right vendor for a sku
and `lead_days` is the promised date Customer Service quotes.

### `leases` (1 row)

Fields: `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`

**Why it matters to the agents:** it is where Facilities confirms what rent is
owed and when, instead of trusting the wording of a rent ticket.

### `cash_accounts` (1 row)

Fields: `name`, `balance`, `date`

**Why it matters to the agents:** the $3,400 balance is the hard ceiling on
everything, and the pay tool must refuse rather than drive it negative.

### `payments` (0 rows)

Fields: `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`

**Why it matters to the agents:** it is the audit trail for the approval rule,
so `approved_by` is only ever filled in after a human says yes.

### `invoices` (1 row)

Fields: `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`

**Why it matters to the agents:** an open invoice freezes its vendor, which is
what blocks restocking until the bill is paid.

---

## How the three tickets interlock

Each ticket was traced through its foreign keys and its sku joins. The links
below are what an agent has to follow to answer the ticket honestly.

### Ticket 101, Bulldog tee, customer order

Requester Tauhid Zaman. Wants 1 of `CC-TEE-WHITE` in size `S`.

| Link | Path | What it says |
|---|---|---|
| Stock | `tickets.sku` + `tickets.size` into `inventory` | On hand is **0**. Short by 1. |
| Price | `tickets.sku` into `pricing` | Cost $8, lists for $28. |
| Bill | `tickets.invoice_id` into `invoices` | Invoice **501**, $840, status `open`, due `2026-08-28`. |
| Vendor | `invoices.vendor_id` into `vendors` | **Bulldog Print Co**, 5 day lead. |

The ticket carries `invoice_id = 501` directly, which is the assignment telling
you these two things are one problem. The tee is out of stock, the only vendor
who can reprint apparel is Bulldog Print Co, and that vendor is owed $840 on an
invoice that is **3 days overdue** as of the shop's today. By the shop rule
they will not ship until it is paid. So this ticket cannot close until a human
approves an $840 payment, and only then does the 5 day lead time start.

### Ticket 102, rent notice

Requester Elm City Properties, who is also the landlord on the lease.

| Link | Path | What it says |
|---|---|---|
| Lease | `tickets.lease_id` into `leases` | Lease **1**, Chapel Street shop, $2,400 a month. |
| Timing | `leases.next_due` against `desk.date_today` | Due `2026-09-02`, today `2026-08-31`, so **2 days out**. |

The cleanest of the three. Nothing blocks it except the approval rule and the
cash balance. The ticket note and the lease agree on the timing, so there is no
conflict to resolve.

### Ticket 103, bulk hoodie discount

Requester Yale AI Club. Wants 20 of `CC-HOOD-NAVY` in size `M`.

| Link | Path | What it says |
|---|---|---|
| Stock | `tickets.sku` + `tickets.size` into `inventory` | On hand is **8**. Short by **12**. |
| Price | `tickets.sku` into `pricing` | Cost $22, lists for $58, so **$36 margin** per unit. |
| Vendor | `pricing.sku` through `vendors.specialty` | Apparel again, so **Bulldog Print Co**, same blocked vendor. |

Two questions in one ticket. The discount is a margin decision, with $36 of
room per hoodie before the shop sells below cost, and 20 at list is $1,160. The
fulfilment is a stock problem, 12 short, and restocking costs $264 at unit cost
from the vendor that is still blocked by invoice 501.

### The shared chokepoint

Tickets 101 and 103 both depend on Bulldog Print Co, and that vendor is frozen
by one unpaid invoice. Paying invoice 501 unblocks both. That single $840
payment is the hinge of the whole board.

### The cash squeeze

| Item | Amount | Running balance |
|---|---|---|
| Opening checking | | $3,400 |
| Invoice 501 | $840 | $2,560 |
| Rent on lease 1 | $2,400 | **$160** |
| Purchase order, 12 hoodies at $22 | $264 | would be **-$104** |

Both required payments fit, with $160 left over. The hoodie restock does not
fit afterwards. So the rule that the pay tool must refuse rather than go
negative is reachable with the starting data, not a theoretical guard. Order
matters too, since cash only goes out and nothing comes back in.

---

## Problem 3: Build the MCP server

`mcp/mcp_server.py` is a FastMCP server pointed at
`data/campus_customs_new.db`. Every agent on the team calls these three tools.
No tool invents a value. Where the database has no answer the tool says so and
returns the rows it does have.

### Which tool answers which ticket

| Ticket | What it is stuck on | Tool that unsticks it | The answer that does it |
|---|---|---|---|
| **101** Bulldog tee | Is there a tee in S to send Tauhid Zaman? | `check_stock` | `on_hand: 0`, short by 1, so it cannot be filled from the shelf |
| **101** Bulldog tee | Then who can reprint it, and will they? | `check_vendor_for_restock` | Bulldog Print Co, 5 day lead, `can_ship: false`, blocked by invoice 501 |
| **101** Bulldog tee | How does that block clear? | `pay_bill` | Pays invoice 501 for $840 with a named approver, which flips the vendor to `can_ship: true` |
| **102** Rent notice | Is rent really due, and can the shop pay it? | `pay_bill` | Pays $2,400 on lease 1, balance $2,560 to $160, and writes the approver into `payments` |
| **103** Bulk hoodies | Are there 20 hoodies in M? | `check_stock` | `on_hand: 8`, short by 12 |
| **103** Bulk hoodies | Can the missing 12 be restocked? | `check_vendor_for_restock` | Same blocked vendor as 101, so the same $840 payment unblocks both |
| **103** Bulk hoodies | Can the shop afford that restock? | `pay_bill` | Refuses $264 against a $160 balance, short by $104 |

Read down that table and the board resolves in one order: check stock, find the
vendor is frozen, pay invoice 501, and only then does anything ship. Ticket 102
is independent but competes for the same $3,400.

### `check_stock(sku, size, qty_wanted)`

**Reads:** `inventory`, on the `(sku, size)` primary key.

**Unlocks:** ticket 101 (Bulldog tee) and the fulfilment half of ticket 103
(bulk hoodies).

**Why it is the right tool:** both tickets name a sku, a size and a quantity,
and `inventory` is the only table that knows how many units exist, so this is
the one lookup that turns "Tauhid wants a tee in S" into the fact that stock is
0 and the shop is short by 1, and "Yale AI Club wants 20 hoodies in M" into 8
on hand and short by 12.

Verified against the live database:

| Call | Result |
|---|---|
| `check_stock("CC-TEE-WHITE", "S", 1)` | `on_hand: 0`, `short_by: 1`, `can_fill_now: false` |
| `check_stock("CC-HOOD-NAVY", "M", 20)` | `on_hand: 8`, `short_by: 12`, `can_fill_now: false` |
| `check_stock("CC-TEE-WHITE", "XXL", 1)` | refused, and lists the sizes that do exist: S, M, L, XL |

### `check_vendor_for_restock(sku)`

**Reads:** `vendors` for name, specialty and `lead_days`; `invoices` filtered
to `status = 'open'` for the block; `desk.date_today` to age those invoices;
`inventory` only to look up the product's name.

**Unlocks:** the restock path for ticket 101 and ticket 103, which are the same
path.

**Why it is the right tool:** neither ticket can be filled from stock, so both
need a vendor, and this is the only tool that applies the shop rule that a
vendor holding an open invoice will not ship, which is exactly what is standing
in the way. It reports that Bulldog Print Co, the 5 day apparel reprinter, is
blocked by invoice 501 for $840 that is 3 days overdue as of 2026-08-31.

The database has no column tying a sku to a vendor. The only signal on file is
the free text in `vendors.specialty`. Rather than invent a mapping, the tool
returns all three vendors with their specialty, lead time and ship status and
leaves the choice to the agent, which is what the scenario asks the Inventory
agent to do anyway.

Verified against the live database:

| Vendor | Specialty | Lead | Can ship |
|---|---|---|---|
| Bulldog Print Co | apparel reprint | 5 days | **no**, invoice 501 open, $840, 3 days overdue |
| Elm City Gifts | mugs and small goods | 3 days | yes |
| QuickShip CT | local courier | 1 day | yes |

### `pay_bill(kind, ref_id, amount, approved_by, account)`

**Reads:** `cash_accounts` for the balance, `invoices` when settling a bill,
`desk.date_today` for the payment date. **Writes:** a row into `payments`, a
lower balance in `cash_accounts`, and `status = 'paid'` on the invoice, all in
one transaction.

**Unlocks:** ticket 102 (rent) directly, and ticket 101 and 103 indirectly,
because paying invoice 501 is what lets Bulldog Print Co ship again.

**Why it is the right tool:** it is the only place money moves, so it is the
only place the two rules that carry point deductions can be enforced, and it
refuses rather than asking nicely: no `approved_by` means no payment, and a
payment larger than the balance is turned down instead of overdrawing the
account.

Verified against the live database, run in order from the opening $3,400:

| Call | Result |
|---|---|
| `pay_bill("invoice", 501, 840, "")` | **refused**, no named human approver |
| `pay_bill("rent", 1, 99999, "Ashley Joyce")` | **refused**, short by $96,599, no negative balance |
| `pay_bill("invoice", 501, 840, "Ashley Joyce")` | paid, balance $3,400 to $2,560, invoice 501 marked paid |
| `pay_bill("invoice", 501, 840, "Ashley Joyce")` again | **refused**, invoice already paid |
| `pay_bill("rent", 1, 2400, "Ashley Joyce")` | paid, balance $2,560 to $160 |
| `pay_bill("purchase_order", 1, 264, "Ashley Joyce")` | **refused**, holds $160 against $264, short by $104 |

After invoice 501 was paid, `check_vendor_for_restock` reported Bulldog Print
Co as `can_ship: true`, which confirms the chokepoint clears exactly as the
data predicted. The working copy was reset afterwards with
`python mcp/mcp_server.py --reset`, so the board is back to three open tickets
and $3,400.

---

## Problem 4: Add the MCP server to vibe coder and test each tool

### Connecting it

The server is registered for the whole project in `.mcp.json` at the repo root,
next to the lecture 9 server that was already there:

```json
{
  "mcpServers": {
    "campus-customs-ops": {
      "command": "homework/hw5/.venv/bin/python",
      "args": ["homework/hw5/mcp/mcp_server.py"]
    }
  }
}
```

Claude Code reads `.mcp.json` when a session starts, so the tools appear after
the session is restarted and the project server is approved.

### Testing

`mcp/test_tools.py` connects to the server as a real MCP client over stdio, so
the tools are exercised through the protocol rather than imported as Python
functions. The handshake advertises three tools, and `approved_by` is marked
required in the schema for `pay_bill`, so the approval rule is visible to any
agent before it even calls the tool.

Run it with the board reset first:

```bash
python mcp/mcp_server.py --reset
python mcp/test_tools.py
```

All 26 checks pass.

| Tool | Checks |
|---|---|
| `check_stock` | tee in S is 0 and short by 1; hoodies in M are 8 and short by 12; an unknown size is refused and the real sizes are listed; an unknown sku is refused |
| `check_vendor_for_restock` | uses `desk.date_today` of 2026-08-31 rather than the real clock; Bulldog Print Co reports `can_ship: false`; the blocker is invoice 501; that invoice is aged 3 days overdue; unblocked vendors report true; the response states that no column links a sku to a vendor; an unknown sku is refused |
| `pay_bill` | refuses an empty approver; refuses a whitespace-only approver; refuses an overdraft; refuses an unknown invoice; refuses a negative amount; pays invoice 501 and leaves $2,560; writes the approver into `payments`; stamps `paid_at` with the shop date; marks the invoice paid; refuses a second payment of the same invoice; pays rent and leaves $160; refuses the $264 hoodie restock, short by $104 |

The run also confirms the chokepoint end to end: after invoice 501 is paid,
`check_vendor_for_restock` flips Bulldog Print Co to `can_ship: true`, so
tickets 101 and 103 both become shippable off one approved payment.

### A bug the test found

The first pass scored 23 of 24. `check_vendor_for_restock("NOPE")` returned
`ok: true` for a sku that is not in the database.

The cause was in the refusal helper. It built its result as
`{"ok": False, "reason": reason, **extra}`, and that call site passed in a dict
that already held `"ok": True`. Later keys win in a dict literal, so the
refusal was silently flipped back into a success.

Fixed in two places. The helper now writes `ok` and `reason` last, so no caller
can override them, and the vendor tool builds its payload without an `ok` key
and stamps one on at return time. All 24 checks pass after the fix.

### Evidence file

`mcp/smoke.py` runs fifteen prompts through the three tools and writes
`output/mcp_smoke.json`. Each entry records the prompt asked, the tool name,
the arguments, and the tool output, plus whether the call was expected to be
accepted or refused.

The file also carries a `database_verification` section. After the run it
re-reads `data/campus_customs_new.db` with direct SQL and compares it to what
the tools reported, so the evidence is not just the server agreeing with
itself. All 7 comparisons match:

| Checked | Tool said | Database holds |
|---|---|---|
| CC-TEE-WHITE size S on hand | 0 | 0 |
| CC-HOOD-NAVY size M on hand | 8 | 8 |
| invoice 501 status after payment | paid | paid |
| checking balance after both payments | $160.00 | $160.00 |
| rows written to `payments` | 2 | 2 |
| approver in the audit trail | Ashley Joyce | Ashley Joyce |
| open invoices left for Bulldog Print Co | 0 | 0 |

### Three more bugs the hunt found

Beyond the refusal bug above, testing the payment paths adversarially turned up
three ways money could move wrongly. All are fixed and all three now have
regression tests.

**An invoice could be cleared for any amount.** `pay_bill("invoice", 501, 1.00,
"Ashley Joyce")` paid one dollar, marked invoice 501 as paid, and unblocked the
vendor. An $840 debt settled for $1. This was the worst of the three because it
breaks the economics of the whole board.

**Rent could be paid against a lease that does not exist.** `pay_bill("rent",
9999, 2400.00, ...)` took $2,400 out of checking for a lease id with no row.
Invoices were validated, leases were not.

**Rent could be paid for the wrong amount.** $1.00 was accepted as rent on a
$2,400 lease.

The fix is one rule in `pay_bill`: whatever is being settled has to exist in the
database, and the amount has to match what is owed, within a cent. Both invoice
and lease paths are checked now.

### Tested with Claude Code connected

After restarting the session, Claude Code loaded `campus-customs-ops` from
`.mcp.json` and the three tools became callable as
`mcp__campus-customs-ops__check_stock`,
`mcp__campus-customs-ops__check_vendor_for_restock` and
`mcp__campus-customs-ops__pay_bill`.

Each tool was then called by Claude Code directly, from a freshly reset board.
All 9 calls behaved as expected and all 7 database checks match. This run is
saved in `output/mcp_smoke.json` under `claude_code_run`.

| # | Prompt | Tool | Result |
|---|---|---|---|
| 1 | Does the shop have a tee in S for ticket 101? | `check_stock` | 0 on hand, short by 1 |
| 2 | How many hoodies in M for ticket 103? | `check_stock` | 8 on hand, short by 12 |
| 3 | Who reprints the tee, and will they ship? | `check_vendor_for_restock` | Bulldog Print Co, `can_ship: false`, invoice 501 is 3 days overdue |
| 4 | Just pay invoice 501 | `pay_bill` | **refused**, no human approver |
| 5 | Pay $1 toward invoice 501 | `pay_bill` | **refused**, the invoice is $840 |
| 6 | Ashley approved $840 on invoice 501 | `pay_bill` | paid, $3,400 to $2,560, invoice marked paid |
| 7 | Can the vendor ship now? | `check_vendor_for_restock` | `can_ship: true`, chokepoint cleared |
| 8 | Ashley approved $2,400 rent | `pay_bill` | paid, $2,560 to $160 |
| 9 | Place the $264 hoodie purchase order | `pay_bill` | **refused**, holds $160, short by $104 |

Reading the database afterwards confirms two payment rows, both stamped
`Ashley Joyce` and dated `2026-08-31` from `desk.date_today`, a $160 balance,
invoice 501 paid and no open invoices left against Bulldog Print Co.

---

## Problem 5: Build the agent team and grow the MCP tools

### Every MCP tool and the tables it uses

All seventeen tools read and write `data/campus_customs_new.db`. No agent
touches the database any other way, and there is no second tools layer that
bypasses MCP.

| Tool | Reads | Writes |
|---|---|---|
| `get_today` | `desk` | |
| `list_tickets` | `tickets`, `desk` | |
| `get_ticket` | `tickets`, `leases`, `invoices`, `vendors`, `pricing`, `inventory`, `desk` | |
| `update_ticket` | `tickets` | `tickets` |
| `check_stock` | `inventory` | |
| `check_vendor_for_restock` | `vendors`, `invoices`, `inventory`, `desk` | |
| `receive_stock` | `inventory` | `inventory` |
| `get_cash_balance` | `cash_accounts` | |
| `list_invoices` | `invoices`, `vendors`, `desk` | |
| `get_pricing` | `pricing` | |
| `quote_discount` | `pricing` | |
| `pay_bill` | `cash_accounts`, `invoices`, `leases`, `desk` | `payments`, `cash_accounts`, `invoices`, `approvals` |
| `get_lease` | `leases`, `desk` | |
| `draft_message` | `tickets` | |
| `request_approval` | `cash_accounts`, `desk` | `approvals` |
| `list_approvals` | `approvals`, `desk` | |
| `decide_approval` | `approvals`, `desk` | `approvals` |

### The approvals table

The shop rules require a human to approve any payment, but the original
database has nowhere to park a request while it waits. So the server creates an
`approvals` table if it is missing.

It lives only in the working copy. `campus_customs.db` is never touched, and
`--reset` restores the original board, after which the table is recreated empty
on the next connection.

The flow is three steps and a human sits in the middle of it:

1. **`request_approval`** records what the shop wants to pay and why, and shows
   what the balance would be afterwards. It spends nothing.
2. **`decide_approval`** records a person's yes or no. It needs their name, it
   refuses an empty name, and it refuses to decide the same request twice. It
   also spends nothing.
3. **`pay_bill`** is the only tool that moves money, and it needs the approver's
   name. When it runs it marks the matching approval as `paid`, so the queue
   cannot drift out of step with reality.

Verified end to end: request 1 went to `pending`, an unnamed decision was
refused, `Ashley Joyce` approved it, a second decision on the same request was
refused, the payment went through leaving $2,560, and the approval closed to
`paid`.

### Safety

The shop rules are enforced in the MCP server, not in the agent prompts. A
prompt is advice and a model can talk its way around advice. A tool that
refuses cannot be argued with.

**Money needs a named human.** `pay_bill` refuses an empty or whitespace
approver, so an agent cannot pay anything on its own say so. The name is
written into `payments.approved_by`, which is the audit trail for every dollar
that leaves.

**The shop never goes negative.** A payment larger than the balance is refused
with the shortfall named. Agents are told in their prompts not to retry with a
smaller amount, and the next rule stops that working anyway.

**Bills settle at face value.** An invoice can only be paid at its invoiced
amount and rent at the lease amount. Without this an $840 invoice could be
cleared for $1, which would unblock a vendor for free and break the shop's
economics. This was a real bug caught in testing, not a hypothetical.

**References must exist.** Paying rent on a lease id that is not in the
database is refused, so money cannot leave against a made up reference.

**Nothing is sent.** `draft_message` always returns `sent: false`. There is no
tool that emails a customer or contacts a vendor, so no agent can do it by
accident or by instruction.

**Approvals cannot be faked.** `decide_approval` needs a person's name and
refuses to decide the same request twice. Agents are told never to put their
own name in an approver field.

**A typed name is not authorisation.** `pay_bill` checks for an approval record
that a human actually decided, matched on kind and reference. A name in
`approved_by` with no approved request behind it is refused, and so is a name
against a request that is still pending. This was a real hole found while
auditing: rent was paid for $2,400 while its approval sat on `pending`, because
the tool trusted the name field. The dashboard route already guarded it, but
the tool did not, and the whole design rests on the tool being the thing that
cannot be argued with.

**No invented shop facts.** Every number comes from a table. Where the database
has no answer, tools refuse and say what is missing rather than guessing. The
clearest case is vendor choice: nothing links a sku to a vendor, so the tool
returns all vendors and makes the agent choose in the open instead of hiding a
guess inside a tool result.

**The clock is the shop's.** Every date check uses `desk.date_today`. Using the
real calendar would silently change which bills are overdue.

**Runs are repeatable.** The original database is never written to, so
`--reset` puts the board back to three open tickets, $3,400 and invoice 501
unpaid before any full run.

### Guardrails

Two kinds of limit, in two different places. The hard money rules live in the
MCP server because a tool that refuses cannot be argued with by a model.
Run-level ceilings live in `backend/limits.py`, because no single tool can see
the whole picture. One payment at a time looks fine. Five in a row empties the
account.

#### Money

| Guardrail | Where | What it stops |
|---|---|---|
| Named human approver required | `pay_bill` | An agent paying on its own say so |
| Least privilege | agent prompts and tools | Only accounting can reach `pay_bill`. The boss has no payment tool at all |
| Amount must match what is owed | `pay_bill` | An $840 invoice being cleared for $1, which would unblock a vendor for free |
| Reference must exist | `pay_bill` | Money leaving against a lease or invoice id that is not in the database |
| No negative balance | `pay_bill` | Overdrawing the shop |
| No double payment | `pay_bill` | The same invoice being settled twice |
| Approval queue | `request_approval`, `decide_approval` | Spending without a recorded decision. Requests hold until a person decides, and a decision needs their name |
| One decision per request | `decide_approval` | A denied request being re-decided into an approval |
| **Run spend cap** | `limits.py` | Collecting several separate approvals that each look reasonable and together drain the account. $3,400 ceiling per run |
| **Separation of duties** | `limits.py` | The agent that requested a payment approving it |
| Full audit trail | `payments.approved_by`, `output/audit_trail.json` | Any payment that cannot be traced to a person and a reason |

The run spend cap is the one a business would miss. Approval is per payment, so
a human approving three things one at a time never sees the total. The cap does.

#### Tokens and loops

Full connectivity means boss to inventory to accounting to boss is a legal
cycle that would never end. Four limits bound it.

| Limit | Value | Why |
|---|---|---|
| Delegation depth | 3 | Caps how deep one chain can nest |
| Cycle detection | current chain | An agent already working this chain cannot be called back into it |
| Delegations per ticket | 8 | Caps the whole tree, not just one branch |
| Model requests per agent | 8 | Stops one agent looping on its own tools |
| Model requests per ticket | 40 | Ceiling across every agent on one ticket |

Tool results are also trimmed to 1,200 characters before they enter the audit
file, and long results are summarised rather than pasted whole, so context stays
small on a long run.

Verified: a delegation back to an agent already in the chain is blocked as a
cycle, a fourth level is blocked on depth, and a $264 order on top of $3,240
already spent is blocked by the run cap even though each piece was approved.

#### Dry run

`RunLimits(dry_run=True)` rehearses a full board pass with every write
suppressed, so the team's intentions can be read before anything touches the
database. Useful before a real run, and the safest way to demo the system.

### The agent team

Five PydanticAI agents in `backend/agents.py`, all sharing one MCP toolset over
`data/campus_customs_new.db`. Each one loads its prompt from
`backend/prompts/<name>.md`. Every typed object is in `backend/models.py`.

| File | What it holds |
|---|---|
| `backend/agents.py` | The five agents, the `delegate` tool, the loop that audits every node, and the CLI |
| `backend/models.py` | Every typed object: delegations, approvals, drafts, ticket plans, outcomes, events |
| `backend/config.py` | Model choice and the in-process MCP toolset |
| `backend/limits.py` | Run-level guardrails for spend, delegation depth and token budget |
| `backend/audit.py` | The append-only audit trail |
| `backend/prompts/*.md` | One prompt per agent |

#### Full connectivity

Every agent carries a `delegate(to_agent, task, ticket_id)` tool and can reach
any of the other four. This is not just the boss fanning out. On a real run of
ticket 103 the edges were:

```
boss -> inventory          boss -> accounting
inventory -> accounting    boss -> customer_service
customer_service -> inventory
customer_service -> accounting
boss -> accounting
```

Inventory asked accounting about the blocking invoice without going through the
boss, and customer service checked both inventory and accounting before writing
to the customer. That is the point of full connectivity.

#### The audit trail

`output/audit_trail.json` is appended to, never wiped. Each run gets its own
record with a run id, so runs can sit side by side in one file. A damaged file
is moved aside rather than lost, and writes go through a temporary file so an
interrupted run cannot truncate it.

Every loop step is recorded: the prompt in, each model response with its token
counts and tool calls, every tool call with its arguments, every tool result,
both ends of every delegation, and the final answer. The ticket 103 run wrote
117 steps across four agents.

Tool results are trimmed to 1,200 characters, and structured data stays
structured rather than being flattened into a string.

#### A real run

`python backend/agents.py --ticket 103` from a reset board. The team found the
8 of 20 shortfall, quoted a 20 percent discount at $46.40 a unit leaving $488
of margin, traced the restock to Bulldog Print Co and found it blocked by
invoice 501, raised an approval request for the $840, drafted a customer reply,
and set the ticket to `waiting`.

The database afterwards confirms it behaved: **zero payments, $3,400 untouched,
invoice 501 still open**, one pending approval, and ticket 103 moved to
`waiting` with the decision in its notes. The team reached the correct stopping
point on its own, which is a human holding the money.

Limits used on that run: 4 of 8 delegations, 7 of 40 model requests, $0 of the
$3,400 spend cap.

#### A full board run, and the bug it found

Running all three tickets from a reset board is the real test, because tickets
101 and 102 together come to $3,240 against a $3,400 balance.

The team handled it correctly on the important axis. Across three tickets it
made **zero calls to `pay_bill`**, left the balance untouched at $3,400, set
every ticket to `waiting`, and parked the money with a human. Nine distinct
delegation edges appeared, including `facilities -> accounting` and
`customer_service -> facilities`, so agents were routing to each other rather
than through the boss.

But the approval queue came out wrong:

| id | ticket | kind | ref | amount |
|---|---|---|---|---|
| 1 | 101 | invoice | 501 | $840 |
| 2 | 101 | invoice | 501 | $840 |
| 3 | | rent | 1 | $2,400 |
| 4 | | rent | 1 | $2,400 |
| 5 | 103 | invoice | 501 | $840 |

Invoice 501 had three pending requests and rent had two. A human would have
been shown **five requests totalling $5,920 against $3,240 of real
obligations**. Approving them all would have tried to pay rent twice.

This is the multi-agent failure mode that matters when money is involved.
Nothing misbehaved. Three agents independently reached the same correct
conclusion about the same bill, and each filed it. The flaw was that the tool
accepted every one.

The fix is one live request per obligation. `request_approval` now looks for a
pending or approved request for the same kind and reference, and hands that one
back with `duplicate: true` rather than raising a second. Agents still get a
sensible answer, and a human is never asked to approve the same money twice.

After the fix the queue holds two requests totalling exactly $3,240. The MCP
test suite covers it and now runs 33 checks.

---

## Problem 7: Backend routes

`backend/main.py` is routes only. Every shop fact it returns comes from the MCP
server over `data/campus_customs_new.db`, so the dashboard and the agents read
the same numbers through the same tools. There is no second path to the data.

Start it from the `backend/` folder:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### Every route, one line each

| Route | What it does |
|---|---|
| `GET /api/health` | Says whether the shop is reachable, and reports the model, the shop date, open ticket count and cash |
| `GET /api/team` | Returns the five agents with their roles, plus the run limits, for the dashboard roster |
| `GET /api/tickets` | Returns the tickets with the status of each, so the board shows open or resolved |
| `GET /api/tickets/{id}` | Returns one ticket with its linked lease, invoice, vendor, price and stock rows |
| `GET /api/cash` | Returns the current checking balance from `cash_accounts`, plus every payment made and the invoices |
| `GET /api/approvals` | Returns the approval queue a human works from, filtered by status |
| `GET /api/events` | Returns what each agent said and which tools it used, with a `since` parameter so the dashboard can poll for only what is new |
| `GET /api/audit` | Returns past audit runs, or the full step list of one run |
| `POST /api/run` | Takes a ticket id and runs the agent team on that ticket, or runs the whole board, and returns when it is done |
| `POST /api/run/stream` | Runs the same work but streams each step as an SSE event, so a human can watch the agents work |
| `POST /api/approvals/{id}/approve` | The human clicks approve and the money actually moves. Agents only prepare payments, this route is what changes cash |
| `POST /api/approvals/{id}/decide` | Records an approve or deny decision on its own, without paying |
| `POST /api/approvals/{id}/pay` | Settles an already approved request, refusing anything a human has not approved |
| `POST /api/reset` | Resets the database to the original values for a fresh run |

### Human in the loop

Agents never move money. They call `request_approval`, which records what the
shop wants to pay and stops. Cash only changes when a person clicks approve,
and that goes through `/api/approvals/{id}/approve`.

The amount is read from the approval record, never from the request body, so a
caller cannot approve $840 and then pay $8,400. The name on the payment is the
name of the person who approved it, and it lands in `payments.approved_by`.

Verified against the running server:

| Call | Result |
|---|---|
| Pay an approval still `pending` | **400**, "A human has to approve it before it can be paid" |
| Decide with an empty name | **422**, rejected before it reaches the shop |
| Agent prepares an $840 request | recorded as `pending`, cash still $3,400 |
| Human clicks approve | paid, $3,400 to $2,560, invoice 501 marked paid, `approved_by=Ashley Joyce` |

### Watching a run

Two ways, because a dashboard may want either.

`/api/run/stream` turns every audit step into an SSE event as it happens.
`/api/events` is a polling alternative that returns the same information in a
flatter shape, with `since` so a refresh only fetches what is new.

A sink that raises is swallowed, and if the client hangs up mid-run the task is
cancelled. A closed browser tab cannot break an agent run, and it cannot leave
one burning tokens either.

Streaming ticket 102 produced this in the first eighteen events:

```
run_start        boss
model_response   boss         ['get_ticket']
tool_call        boss         get_ticket
model_response   boss         ['get_today']
model_response   boss         ['delegate', 'delegate']
delegation_start boss         -> facilities
prompt           facilities
delegation_start boss         -> accounting
prompt           accounting
model_response   accounting   ['get_cash_balance', 'get_lease', 'get_today']
```

Worth noting against the problem 6 plan: the boss called facilities **and**
accounting in the same turn rather than waiting for facilities to hand off. The
plan predicted `boss -> facilities -> accounting`. That is a real divergence to
write up in the Actual section.

---

## Problem 8: The dashboard

`frontend/` is React, Vite and TypeScript. It calls the backend on
`http://localhost:8000`, which allows the Vite origins by name so the browser
will make the calls at all.

```bash
cd frontend
npm run dev          # http://localhost:5173
```

### What it does

| Requirement | How it is met |
|---|---|
| List the three tickets | The left column, one card each, with status |
| Pick one and run the team | Every card has its own run button |
| Show agents working live | The middle column streams `/api/run/stream` over SSE |
| Mark a ticket resolved | The card changes four ways at once: green rail, tinted background, tick in the chip, button becomes "Run again" |
| Summarise what each agent did | A card per agent after the run, with turns, tools used and who it delegated to |
| Let a human approve a payment | The approval card in the right column, one click |
| Show the checking balance | The biggest number in the top bar, which flashes when it changes |

### Layout

Three columns under a status bar. The board on the left, the live agent feed in
the middle as the widest column, the team roster and approval queue on the
right. The feed is the centre because watching the team work is the point of
the assignment.

The full design reasoning, including what changed after the first build and
why, is in `output/design.md`.

### How agents read apart from each other

Each agent owns a colour, used in three places: its dot in the roster, its name
in the feed, and its summary card. You can follow one agent down the page
without reading a word.

Agents speak in sentences rather than JSON. "Inventory called check_stock",
"Boss asked Accounting: can we cover an $840 invoice". Tool names appear as
small chips underneath, so the detail is there without being the main event.

### The human in the loop

The approval card is the one element designed to interrupt. Warm cream against
a cool page, amber rail, the amount set large. When nothing is pending it says
"Nothing to approve. Agents prepare payments, they never make them."

That sentence is enforced underneath, not just written. The dashboard cannot
pay anything a person has not approved, and neither can an agent.

---

## Problem 9: Resolve the tickets

The board was reset, then worked to resolution by `output/resolve_board.py`.
That script alternates agent passes with human decisions on the approval queue,
applying one standing policy: approve what the shop can afford, deny what it
cannot. Every decision goes through `decide_approval` and `pay_bill` exactly as
a click on the dashboard would. Nothing bypasses the approval gate.

### The run

| Pass | What the agents did | What the human decided |
|---|---|---|
| 1 | Worked 101, 102, 103. All parked on `waiting` | Approved invoice 501 for $840, approved rent for $2,400 |
| 2 | 102 and 103 closed. 101 still waiting on a restock order | Approved an $8 purchase order for the tee |
| 3 | 101 closed | Nothing left to decide |

Three passes, three tickets closed.

### The money

Every figure is read from the database by `output/cash_reconcile.py`, which
refuses to print numbers that do not balance.

| | Amount | Balance |
|---|---|---|
| Starting checking, after the reset | | **$3,400.00** |
| Ticket 101, invoice 501 to unfreeze the vendor | -$840.00 | $2,560.00 |
| Ticket 102, rent on the Chapel Street lease | -$2,400.00 | $160.00 |
| Ticket 101, purchase order for the tee | -$8.00 | **$152.00** |

$3,400.00 minus $3,248.00 is $152.00, and `cash_accounts` holds $152.00. They
agree to the cent.

Ticket 103 resolved having spent nothing. The 20 percent discount was agreed,
but by the time the 12-unit restock was considered there was $152 against a
$264 order, so it closed honestly as a discount on the 8 units in stock.

### What the plan got right and wrong

Written in problem 6 before any of this ran.

**Right on every roster.** Facilities stayed out of 101 and 103, Inventory
stayed out of 102, exactly as predicted. Inventory went to Accounting directly
on 101 rather than routing through the boss.

**Wrong on shape.** The plan said ticket 102 would need two hops. It took four
agents, and the boss called Facilities and Accounting in the same turn instead
of waiting for the hand-off.

**Missed entirely.** That clearing invoice 501 would not finish ticket 101. A
second approval was needed for the order itself, and the ticket took three
passes to close.

### Six bugs this problem found

Each is fixed with a regression test. The suite runs 35 checks.

1. **The reconciler double counted cash.** Two rent approvals against one lease
   made a join fan out, reporting $5,640 paid against $3,240 actually spent.
   Caught only because the script asserts rather than prints.
2. **Rent could be paid twice.** An invoice is protected by its status flipping
   to paid. Rent had no equivalent guard.
3. **`run_board` only picked up `open` tickets.** Anything parked on `waiting`
   for a human could never be revisited, so running to resolution was
   impossible.
4. **Refusals blamed the wrong thing.** Affordability was checked before
   authorisation, so an unapproved payment reported "insufficient funds".
5. **The audit trail stringified scalars.** An int `ticket_id` was written as
   `"101"`, so no report could match a step to its ticket.
6. **A report generator failed silently.** It looked for placeholders that were
   already gone, did nothing, and reported success. The Actual sections sat
   full of figures from an older run until the mismatch was spotted. Generators
   now assert that their output landed.

The behavioural fix mattered too. The boss was reading its own earlier note
saying "keep waiting" and repeating it rather than re-checking whether the
thing it was waiting for had happened. Ticket 101 stuck twice on that. The
prompt now says the notes are history, not current state.

### Artefacts

| File | What it holds |
|---|---|
| `output/resolved_tickets.json` | Per ticket: id, final status, outcome, what each agent contributed, and every human approval |
| `output/desk_tickets.html` | The problem 6 plan with the Actual sections and Cash tab filled in |
| `output/resolved_board.html` | A screenshot of the dashboard for each resolved ticket, images embedded so the file stands alone |
| `output/audit_trail.json` | Every run appended, 24 runs on file |
| `output/cash_reconcile.py` | Derives the cash and refuses to publish numbers that do not balance |
| `output/resolve_board.py` | Runs the board to resolution with a human in the loop |
