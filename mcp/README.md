# Campus Customs Operations MCP Server

## What it is for

This is the shared tool layer for the Campus Customs agent team. The Boss,
Inventory, Accounting, Facilities and Customer Service agents never touch the
database directly. They call the tools here, so every agent sees the same
numbers and the shop rules are enforced in one place instead of being repeated
in five prompts.

There is no second shop-tools layer. Every shop fact an agent uses comes
through this server.

Rules that live here rather than in a prompt, because a tool that refuses
cannot be argued with:

- A payment with no named human approver is refused.
- A payment larger than the cash balance is refused. The shop never runs a
  negative balance.
- A bill settles at the amount owed. An invoice cannot be cleared for less.
- Money cannot leave against an invoice or lease that is not in the database.
- Nothing is ever sent to a customer or a vendor.

No tool invents a value. Everything returned comes out of a table, and when the
database has no answer the tool says so instead of guessing.

## Which database it uses

`../data/campus_customs_new.db`, the working copy.

`../data/campus_customs.db` is the original and is never written to. It is read
only when restoring the working copy.

```bash
python mcp_server.py --reset
```

That puts the shop back to three open tickets, $3,400 in checking and invoice
501 unpaid.

## The seventeen tools

### Board

| Tool | What it does |
|---|---|
| `get_today()` | The shop's date from `desk.date_today`. Call this before judging what is late. The shop does not run on the real calendar. |
| `list_tickets(status)` | The board. Filter by status, or pass "all". |
| `get_ticket(ticket_id)` | One ticket plus the linked lease, invoice, vendor, price and stock rows. Usually the only call needed to see what a ticket touches. |
| `update_ticket(ticket_id, status, note)` | Moves a ticket along and appends to its notes. |

### Inventory

| Tool | What it does |
|---|---|
| `check_stock(sku, size, qty_wanted)` | Units on hand, and the shortfall when `qty_wanted` is given. Inventory is keyed on sku **and** size, so both are needed. |
| `check_vendor_for_restock(sku)` | Every vendor with its specialty, lead time and a `can_ship` flag. A vendor holding an open invoice will not ship, and this is where that rule is applied. It does not guess which vendor fits a product, because no column links a sku to a vendor. |
| `receive_stock(sku, size, qty, note)` | Adds units when a restock has actually arrived. Ordering is not receiving. |

### Money

| Tool | What it does |
|---|---|
| `get_cash_balance(account)` | What the shop can actually spend. |
| `list_invoices(status)` | Bills, aged against the shop's today, with the vendor name attached. |
| `get_pricing(sku)` | Unit cost, list price and the margin room. |
| `quote_discount(sku, qty, discount_pct)` | What a discount does to unit price, margin and total, plus the break-even discount. |
| `pay_bill(kind, ref_id, amount, approved_by, account)` | The only tool that moves money. Writes a `payments` row, lowers the balance, marks a paid invoice as paid and closes the matching approval, all in one transaction. Refuses without a named approver, over the balance, for the wrong amount, for a reference that does not exist, or for a bill already paid. |

### Space

| Tool | What it does |
|---|---|
| `get_lease(lease_id)` | Lease terms, the monthly rent, and days until the next due date. Pass 0 for every lease. |

### Approvals

| Tool | What it does |
|---|---|
| `request_approval(kind, ref_id, amount, reason, ticket_id, requested_by)` | Puts money in front of a human. Records a pending request and shows what the balance would be afterwards. Spends nothing. |
| `list_approvals(status)` | The approval queue. |
| `decide_approval(approval_id, decision, decided_by)` | Records a person's yes or no. Needs their name, refuses an empty one, and refuses to decide the same request twice. Spends nothing. |

### Outbound

| Tool | What it does |
|---|---|
| `draft_message(ticket_id, to, subject, body)` | Writes a draft and pins it to a ticket. Always returns `sent: false`. Nothing is ever sent. |

## The approval flow

Three steps, with a human in the middle:

1. An agent calls `request_approval`. Nothing is paid.
2. A person calls `decide_approval` with their name. Still nothing is paid.
3. Accounting calls `pay_bill` with that person's name. Money moves, and the
   approval closes to `paid`.

The `approvals` table is the one table this assignment adds. It exists only in
the working copy, so `--reset` still restores the original board and the table
is recreated empty on the next connection.

## Running it

```bash
python mcp_server.py           # stdio, for an agent to attach to
python mcp_server.py --http    # Streamable HTTP on http://127.0.0.1:8001/mcp
python mcp_server.py --reset   # restore the working copy, then exit
```

HTTP uses port 8001 so the FastAPI backend keeps 8000.

The backend attaches this server in-process, so no separate MCP terminal is
needed when running the agent team.

## Tests

```bash
python mcp_server.py --reset
python test_tools.py    # 26 checks over the protocol, including every refusal
python smoke.py         # writes ../output/mcp_smoke.json with full evidence
```
