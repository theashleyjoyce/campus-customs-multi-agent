"""Campus Customs operations MCP — Homework 5.

Every agent on the team calls these tools. They read and write
../data/campus_customs_new.db and nothing else, so the original
campus_customs.db stays clean and a run can be reset from it.

The tools are grouped by who reaches for them most:
  board      get_today, list_tickets, get_ticket, update_ticket
  inventory  check_stock, check_vendor_for_restock, receive_stock
  money      get_cash_balance, list_invoices, get_pricing, quote_discount,
             pay_bill
  space      get_lease
  outbound   draft_message

Nothing here invents data. Every number comes out of a table. Where the
database has no answer, the tool says so instead of guessing.

The shop rules live in this layer rather than in agent prompts, so an agent
cannot talk its way past them:

  * "today" is desk.date_today, never the real clock
  * a vendor with an open invoice will not ship new product
  * a payment needs a named human approver
  * a payment that would overdraw the account is refused

Run from this folder (stdio):  python mcp_server.py
Run (HTTP):                    python mcp_server.py --http
Reset the working copy:        python mcp_server.py --reset
HTTP URL:                      http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
ORIGINAL_DB = DATA / "campus_customs.db"
DB_PATH = DATA / "campus_customs_new.db"

mcp = FastMCP("campus-customs-ops")


# --------------------------------------------------------------------------
# helpers (not tools)
# --------------------------------------------------------------------------


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(
            f"{DB_PATH.name} is missing. Copy campus_customs.db to campus_customs_new.db."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # The approval queue is the one table this assignment adds. It lives only
    # in the working copy, so --reset still restores the original board.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS approvals (
               id INTEGER PRIMARY KEY,
               ticket_id INTEGER,
               kind TEXT NOT NULL,
               ref_id INTEGER NOT NULL,
               amount REAL NOT NULL,
               reason TEXT NOT NULL,
               requested_by TEXT NOT NULL,
               requested_at TEXT NOT NULL,
               status TEXT NOT NULL DEFAULT 'pending',
               decided_by TEXT,
               decided_at TEXT
           )"""
    )
    conn.commit()
    return conn


def _query(sql: str, params: Any = ()) -> list[dict]:
    with closing(_connect()) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _one(sql: str, params: Any = ()) -> dict | None:
    rows = _query(sql, params)
    return rows[0] if rows else None


def _today() -> str:
    """The shop's today, from desk.date_today. Not the real calendar."""
    row = _one("SELECT date_today FROM desk LIMIT 1")
    if not row:
        raise RuntimeError("desk table is empty, so the shop has no date.")
    return row["date_today"]


def _days_late(due_date: str, today: str) -> int:
    """Whole days a due date is past the shop's today. Zero if not yet due."""
    row = _one("SELECT CAST(julianday(?) - julianday(?) AS INTEGER) AS d", (today, due_date))
    return max(int(row["d"]), 0) if row and row["d"] is not None else 0


def _refuse(reason: str, **extra: Any) -> dict:
    """A refusal. `ok` and `reason` are written last so extra cannot override them."""
    return {**extra, "ok": False, "reason": reason}


def reset_working_copy() -> dict:
    """Restore campus_customs_new.db from the untouched original."""
    if not ORIGINAL_DB.exists():
        raise RuntimeError(f"{ORIGINAL_DB.name} is missing, so there is nothing to restore from.")
    shutil.copyfile(ORIGINAL_DB, DB_PATH)
    return {
        "restored": DB_PATH.name,
        "from": ORIGINAL_DB.name,
        "today": _today(),
        "open_tickets": len(_query("SELECT id FROM tickets WHERE lower(status) = 'open'")),
    }


# --------------------------------------------------------------------------
# tool 1 of 3
# --------------------------------------------------------------------------


@mcp.tool
def check_stock(sku: str, size: str, qty_wanted: int = 0) -> dict:
    """Check units on hand for a product and how many are short.

    Inventory is keyed on sku plus size, so both are needed for one answer.
    Pass qty_wanted to find out whether a ticket can be filled from stock.

    Args:
        sku: Product code exactly as it appears in the database, for example
            "CC-TEE-WHITE" or "CC-HOOD-NAVY".
        size: Size exactly as stored, for example "S", "M", "L", "XL", "OS".
        qty_wanted: How many units the ticket asks for. Leave at 0 to just
            read the stock level.
    """
    row = _one("SELECT * FROM inventory WHERE sku = ? AND size = ?", (sku, size))
    if not row:
        sizes = _query("SELECT size, qty FROM inventory WHERE sku = ? ORDER BY size", (sku,))
        if not sizes:
            return _refuse(f"The database has no product with sku {sku!r}.", sku=sku)
        return _refuse(
            f"{sku} has no row for size {size!r}.",
            sku=sku,
            sizes_on_file=[s["size"] for s in sizes],
        )

    on_hand = row["qty"]
    result = {
        "ok": True,
        "sku": sku,
        "product_name": row["name"],
        "size": size,
        "on_hand": on_hand,
        "location": row["location"],
        "in_stock": on_hand > 0,
    }
    if qty_wanted > 0:
        short_by = max(qty_wanted - on_hand, 0)
        result.update(
            qty_wanted=qty_wanted,
            short_by=short_by,
            can_fill_now=short_by == 0,
            note=(
                f"{on_hand} on hand covers the {qty_wanted} requested."
                if short_by == 0
                else f"{on_hand} on hand against {qty_wanted} requested, short by {short_by}."
            ),
        )
    return result


# --------------------------------------------------------------------------
# tool 2 of 3
# --------------------------------------------------------------------------


@mcp.tool
def check_vendor_for_restock(sku: str = "") -> dict:
    """List vendors and say which ones are free to ship right now.

    The database has no column linking a product to a vendor. The only signal
    on file is each vendor's `specialty` text, so this tool hands back every
    vendor with its specialty and lead time and leaves the choice to you. It
    does not guess a match.

    What it does decide, because the data says so, is whether a vendor is
    blocked: a vendor holding an open invoice will not ship new product until
    that invoice is paid.

    Args:
        sku: Optional product code. When given, the product's name is returned
            alongside the vendors to help you match it to a specialty.
    """
    today = _today()
    vendors = _query("SELECT * FROM vendors ORDER BY id")
    if not vendors:
        return _refuse("The vendors table is empty.")

    for vendor in vendors:
        open_invoices = _query(
            "SELECT * FROM invoices WHERE vendor_id = ? AND lower(status) = 'open' "
            "ORDER BY due_date, id",
            (vendor["id"],),
        )
        for invoice in open_invoices:
            invoice["days_overdue"] = _days_late(invoice["due_date"], today)
        vendor["open_invoices"] = open_invoices
        vendor["can_ship"] = not open_invoices
        vendor["blocked_reason"] = (
            None
            if not open_invoices
            else (
                f"{vendor['name']} holds open invoice(s) "
                f"{', '.join(str(i['id']) for i in open_invoices)} "
                f"totalling ${sum(i['amount'] for i in open_invoices):,.2f}. "
                "They will not ship new product until this is paid."
            )
        )

    payload: dict[str, Any] = {
        "today": today,
        "vendors": vendors,
        "note": (
            "No column links a sku to a vendor. Choose using each vendor's "
            "specialty, and only from vendors where can_ship is true."
        ),
    }

    if sku:
        product = _one("SELECT name FROM inventory WHERE sku = ? LIMIT 1", (sku,))
        if not product:
            return _refuse(f"The database has no product with sku {sku!r}.", sku=sku, **payload)
        payload["sku"] = sku
        payload["product_name"] = product["name"]
    return {**payload, "ok": True}


# --------------------------------------------------------------------------
# tool 3 of 3
# --------------------------------------------------------------------------


@mcp.tool
def pay_bill(
    kind: str, ref_id: int, amount: float, approved_by: str, account: str = "checking"
) -> dict:
    """Pay an invoice or rent, only with a human approver and only if cash covers it.

    This refuses unless a human has already approved the spend through
    request_approval and decide_approval. A name in `approved_by` is not enough
    on its own, because any agent could type one.

    It also refuses rather than overdrawing, because the shop never runs a
    negative balance, and refuses when the invoice or lease being settled is not
    in the database, or when the amount does not match what is actually owed,
    so a bill cannot be cleared for less than its value. On success it
    writes one payments row, lowers the account balance, and marks a paid
    invoice as paid, all in one transaction.

    Args:
        kind: What is being paid. Use "invoice" to settle a vendor bill, or
            "rent" to pay a lease.
        ref_id: The invoice id for an invoice, or the lease id for rent.
        amount: Dollars to pay.
        approved_by: Name of the human who approved this payment. Required.
            Never fill this in yourself. If no human has approved it, stop and
            ask for approval on the dashboard first.
        account: Which account pays. The shop only has "checking".
    """
    if not approved_by or not approved_by.strip():
        return _refuse(
            "Refused: this payment has no named human approver. "
            "Ask for approval on the dashboard, then call this again with that person's name."
        )
    if amount <= 0:
        return _refuse("Refused: amount must be greater than zero.", amount=amount)

    today = _today()
    with closing(_connect()) as conn:
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                acct = conn.execute(
                    "SELECT * FROM cash_accounts WHERE lower(name) = lower(?)", (account,)
                ).fetchone()
                if not acct:
                    return _refuse(f"The database has no cash account named {account!r}.")

                balance = acct["balance"]

                # A named approver is not enough on its own. There has to be a
                # real approval record that a human decided, or any agent could
                # put a plausible name in approved_by and move money.
                authorised = conn.execute(
                    """SELECT * FROM approvals
                       WHERE lower(kind) = ? AND ref_id = ?
                         AND lower(status) = 'approved'
                       ORDER BY id LIMIT 1""",
                    (kind.strip().lower(), ref_id),
                ).fetchone()
                if not authorised:
                    pending = conn.execute(
                        """SELECT * FROM approvals
                           WHERE lower(kind) = ? AND ref_id = ? AND lower(status) = 'pending'
                           ORDER BY id LIMIT 1""",
                        (kind.strip().lower(), ref_id),
                    ).fetchone()
                    if pending:
                        return _refuse(
                            f"Refused: approval {pending['id']} for this {kind} is still "
                            "pending. A human has to decide it before it can be paid.",
                            approval_id=pending["id"],
                            approval_status="pending",
                        )
                    return _refuse(
                        f"Refused: no approved request exists for {kind} {ref_id}. "
                        "Call request_approval first and wait for a human to approve it.",
                        approval_status="missing",
                    )

                # Whatever is being settled has to exist, and the amount has to
                # match what is owed. Without this an $840 invoice could be
                # cleared for $1 and the vendor would unblock for free.
                invoice = None
                what = kind.strip().lower()
                if what == "invoice":
                    invoice = conn.execute(
                        "SELECT * FROM invoices WHERE id = ?", (ref_id,)
                    ).fetchone()
                    if not invoice:
                        return _refuse(f"The database has no invoice with id {ref_id}.")
                    if invoice["status"].strip().lower() == "paid":
                        return _refuse(f"Invoice {ref_id} is already paid.")
                    if abs(amount - invoice["amount"]) > 0.005:
                        return _refuse(
                            f"Refused: invoice {ref_id} is for ${invoice['amount']:,.2f} "
                            f"but this payment is ${amount:,.2f}. Pay the invoiced amount.",
                            amount_owed=invoice["amount"],
                            amount_offered=amount,
                        )
                elif what == "rent":
                    lease = conn.execute(
                        "SELECT * FROM leases WHERE id = ?", (ref_id,)
                    ).fetchone()
                    if not lease:
                        return _refuse(f"The database has no lease with id {ref_id}.")
                    already = conn.execute(
                        """SELECT id, amount, paid_at FROM payments
                           WHERE lower(kind) = 'rent' AND ref_id = ? AND paid_at = ?""",
                        (ref_id, today),
                    ).fetchone()
                    if already:
                        return _refuse(
                            f"Refused: rent on lease {ref_id} was already paid on {today} "
                            f"as payment {already['id']}. It is not due twice.",
                            existing_payment_id=already["id"],
                        )
                    if abs(amount - lease["monthly_rent"]) > 0.005:
                        return _refuse(
                            f"Refused: rent on lease {ref_id} is "
                            f"${lease['monthly_rent']:,.2f} but this payment is "
                            f"${amount:,.2f}. Pay the amount on the lease.",
                            rent_due=lease["monthly_rent"],
                            amount_offered=amount,
                        )

                # Affordability is checked last. A payment that is unapproved,
                # already settled, or for the wrong amount should say so,
                # rather than blaming the balance for a different problem.
                if amount > balance:
                    return _refuse(
                        f"Refused: {acct['name']} holds ${balance:,.2f} but this payment is "
                        f"${amount:,.2f}. The shop does not run a negative balance.",
                        balance=balance,
                        amount=amount,
                        short_by=round(amount - balance, 2),
                    )

                cur = conn.execute(
                    """INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (kind, ref_id, amount, acct["name"], today, approved_by.strip()),
                )
                conn.execute(
                    "UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
                    (amount, today, acct["name"]),
                )
                if invoice is not None:
                    conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))

                # Close out the approval that authorised this payment.
                conn.execute(
                    "UPDATE approvals SET status = 'paid' WHERE id = ?", (authorised["id"],)
                )

                after = conn.execute(
                    "SELECT balance FROM cash_accounts WHERE name = ?", (acct["name"],)
                ).fetchone()["balance"]

                return {
                    "ok": True,
                    "payment_id": cur.lastrowid,
                    "kind": kind,
                    "ref_id": ref_id,
                    "amount": amount,
                    "account": acct["name"],
                    "paid_at": today,
                    "approved_by": approved_by.strip(),
                    "balance_before": balance,
                    "balance_after": after,
                    "invoice_marked_paid": invoice is not None,
                }
        except sqlite3.Error as exc:
            return _refuse(f"Database error, nothing was paid: {exc}")


# --------------------------------------------------------------------------
# board tools
# --------------------------------------------------------------------------


@mcp.tool
def get_today() -> dict:
    """The shop's current date, from desk.date_today.

    Call this before judging whether anything is late. The shop does not run on
    the real calendar, so using the system clock gives wrong answers.
    """
    return {"ok": True, "date_today": _today()}


@mcp.tool
def list_tickets(status: str = "open") -> dict:
    """List tickets on the board.

    Args:
        status: Filter such as "open" or "closed". Use "all" for every ticket.
    """
    if status.strip().lower() == "all":
        rows = _query("SELECT * FROM tickets ORDER BY created_at, id")
    else:
        rows = _query(
            "SELECT * FROM tickets WHERE lower(status) = lower(?) ORDER BY created_at, id",
            (status,),
        )
    return {
        "ok": True,
        "today": _today(),
        "count": len(rows),
        "tickets": rows,
        "note": f"No tickets with status {status!r}." if not rows else None,
    }


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """One ticket together with the rows it points at.

    Follows lease_id, invoice_id and sku so the caller sees the linked lease,
    bill, price and stock without extra round trips.

    Args:
        ticket_id: The ticket's id, for example 101.
    """
    ticket = _one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if not ticket:
        return _refuse(f"The database has no ticket with id {ticket_id}.")

    linked: dict[str, Any] = {}
    if ticket.get("lease_id"):
        linked["lease"] = _one("SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],))
    if ticket.get("invoice_id"):
        invoice = _one("SELECT * FROM invoices WHERE id = ?", (ticket["invoice_id"],))
        if invoice:
            invoice["days_overdue"] = _days_late(invoice["due_date"], _today())
            linked["invoice"] = invoice
            linked["invoice_vendor"] = _one(
                "SELECT * FROM vendors WHERE id = ?", (invoice["vendor_id"],)
            )
    if ticket.get("sku"):
        linked["pricing"] = _one("SELECT * FROM pricing WHERE sku = ?", (ticket["sku"],))
        if ticket.get("size"):
            linked["stock"] = _one(
                "SELECT * FROM inventory WHERE sku = ? AND size = ?",
                (ticket["sku"], ticket["size"]),
            )
    return {"ok": True, "today": _today(), "ticket": ticket, "linked": linked}


@mcp.tool
def update_ticket(ticket_id: int, status: str = "", note: str = "") -> dict:
    """Move a ticket along, or add a line to its notes.

    Args:
        ticket_id: The ticket to update.
        status: New status such as "open", "waiting", "closed". Optional.
        note: Text to append to the ticket's notes. Optional.
    """
    ticket = _one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if not ticket:
        return _refuse(f"The database has no ticket with id {ticket_id}.")
    if not status and not note:
        return _refuse("Nothing to update. Pass a status, a note, or both.")

    new_status = status.strip() or ticket["status"]
    notes = (ticket["notes"] or "").strip()
    if note:
        notes = f"{notes} | {note.strip()}".strip(" |")

    with closing(_connect()) as conn:
        with conn:
            conn.execute(
                "UPDATE tickets SET status = ?, notes = ? WHERE id = ?",
                (new_status, notes, ticket_id),
            )
    return {
        "ok": True,
        "ticket_id": ticket_id,
        "was_status": ticket["status"],
        "status": new_status,
        "notes": notes,
    }


# --------------------------------------------------------------------------
# inventory tools
# --------------------------------------------------------------------------


@mcp.tool
def receive_stock(sku: str, size: str, qty: int, note: str = "") -> dict:
    """Add units to inventory when a restock actually arrives.

    Only call this once stock is genuinely in hand. Ordering is not receiving.

    Args:
        sku: Product code.
        size: Size such as "M".
        qty: How many units arrived. Must be positive.
        note: Optional short reason, for example "PO from Bulldog Print Co".
    """
    if qty <= 0:
        return _refuse("Quantity must be greater than zero.", qty=qty)
    row = _one("SELECT * FROM inventory WHERE sku = ? AND size = ?", (sku, size))
    if not row:
        return _refuse(f"The database has no inventory row for {sku} in size {size}.")
    with closing(_connect()) as conn:
        with conn:
            conn.execute(
                "UPDATE inventory SET qty = qty + ? WHERE sku = ? AND size = ?", (qty, sku, size)
            )
    return {
        "ok": True,
        "sku": sku,
        "size": size,
        "was": row["qty"],
        "now": row["qty"] + qty,
        "received": qty,
        "note": note,
    }


# --------------------------------------------------------------------------
# money tools
# --------------------------------------------------------------------------


@mcp.tool
def get_cash_balance(account: str = "checking") -> dict:
    """What the shop can actually spend right now.

    Args:
        account: Account name. The shop only has "checking".
    """
    row = _one("SELECT * FROM cash_accounts WHERE lower(name) = lower(?)", (account,))
    if not row:
        return _refuse(f"The database has no cash account named {account!r}.")
    return {"ok": True, "account": row["name"], "balance": row["balance"], "as_of": row["date"]}


@mcp.tool
def list_invoices(status: str = "all") -> dict:
    """Vendor bills, aged against the shop's today.

    Args:
        status: "open", "paid", or "all".
    """
    if status.strip().lower() == "all":
        rows = _query("SELECT * FROM invoices ORDER BY due_date, id")
    else:
        rows = _query(
            "SELECT * FROM invoices WHERE lower(status) = lower(?) ORDER BY due_date, id",
            (status,),
        )
    today = _today()
    for row in rows:
        row["days_overdue"] = _days_late(row["due_date"], today)
        row["is_overdue"] = row["days_overdue"] > 0 and row["status"].lower() == "open"
        vendor = _one("SELECT name FROM vendors WHERE id = ?", (row["vendor_id"],))
        row["vendor_name"] = vendor["name"] if vendor else None
    return {"ok": True, "today": today, "count": len(rows), "invoices": rows}


@mcp.tool
def get_pricing(sku: str) -> dict:
    """Cost, list price and the margin room on a product.

    Args:
        sku: Product code such as "CC-HOOD-NAVY".
    """
    row = _one("SELECT * FROM pricing WHERE sku = ?", (sku,))
    if not row:
        return _refuse(f"The database has no pricing row for {sku}.", sku=sku)
    margin = row["list_price"] - row["unit_cost"]
    return {
        "ok": True,
        "sku": sku,
        "unit_cost": row["unit_cost"],
        "list_price": row["list_price"],
        "margin_per_unit": round(margin, 2),
        "margin_pct_of_list": round(100 * margin / row["list_price"], 1)
        if row["list_price"]
        else 0.0,
    }


@mcp.tool
def quote_discount(sku: str, qty: int, discount_pct: float) -> dict:
    """Work out what a proposed discount does to price, margin and total.

    Use this before agreeing any price override, so the answer is arithmetic
    rather than a guess. `max_discount_pct_at_cost` is the point where the shop
    breaks even and below which it loses money on every unit.

    Args:
        sku: Product code such as "CC-HOOD-NAVY".
        qty: How many units the customer wants.
        discount_pct: Percent off list, for example 15 for 15 percent off.
    """
    row = _one("SELECT * FROM pricing WHERE sku = ?", (sku,))
    if not row:
        return _refuse(f"The database has no pricing row for {sku}.", sku=sku)
    if qty <= 0:
        return _refuse("Quantity must be greater than zero.", qty=qty)

    list_price, unit_cost = row["list_price"], row["unit_cost"]
    unit_price = round(list_price * (1 - discount_pct / 100.0), 2)
    unit_margin = round(unit_price - unit_cost, 2)
    return {
        "ok": True,
        "sku": sku,
        "qty": qty,
        "discount_pct": discount_pct,
        "unit_cost": unit_cost,
        "list_price": list_price,
        "discounted_unit_price": unit_price,
        "margin_per_unit": unit_margin,
        "total_at_list": round(list_price * qty, 2),
        "total_discounted": round(unit_price * qty, 2),
        "total_margin": round(unit_margin * qty, 2),
        "below_cost": unit_margin < 0,
        "max_discount_pct_at_cost": round(100 * (list_price - unit_cost) / list_price, 1)
        if list_price
        else 0.0,
    }


# --------------------------------------------------------------------------
# space tools
# --------------------------------------------------------------------------


@mcp.tool
def get_lease(lease_id: int = 0) -> dict:
    """Lease terms and how soon the next rent is due.

    Args:
        lease_id: A lease id. Leave at 0 to list every lease.
    """
    if lease_id:
        row = _one("SELECT * FROM leases WHERE id = ?", (lease_id,))
        if not row:
            return _refuse(f"The database has no lease with id {lease_id}.")
        rows = [row]
    else:
        rows = _query("SELECT * FROM leases ORDER BY id")

    today = _today()
    for row in rows:
        due = _one(
            "SELECT CAST(julianday(?) - julianday(?) AS INTEGER) AS d", (row["next_due"], today)
        )
        row["days_until_due"] = int(due["d"]) if due and due["d"] is not None else 0
        row["is_overdue"] = row["days_until_due"] < 0
    return {"ok": True, "today": today, "count": len(rows), "leases": rows}


# --------------------------------------------------------------------------
# outbound tools
# --------------------------------------------------------------------------


@mcp.tool
def draft_message(ticket_id: int, to: str, subject: str, body: str) -> dict:
    """Write a draft reply and pin it to a ticket. Nothing is ever sent.

    The shop does not email customers or call vendors in this assignment.
    Drafts stay on the board for a human to read.

    Args:
        ticket_id: Which ticket this draft belongs to.
        to: Who the message is addressed to.
        subject: Subject line.
        body: The message text.
    """
    ticket = _one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if not ticket:
        return _refuse(f"The database has no ticket with id {ticket_id}.")
    if not body.strip():
        return _refuse("A draft needs a body.")
    return {
        "ok": True,
        "sent": False,
        "ticket_id": ticket_id,
        "to": to,
        "subject": subject,
        "body": body.strip(),
        "note": "Draft only. Nothing was sent to anyone.",
    }

# --------------------------------------------------------------------------
# approval tools
# --------------------------------------------------------------------------


@mcp.tool
def request_approval(
    kind: str,
    ref_id: int,
    amount: float,
    reason: str,
    ticket_id: int = 0,
    requested_by: str = "accounting",
) -> dict:
    """Put money in front of a human and wait. This spends nothing.

    Call this when the shop needs to pay something. It records a pending
    request that a person decides on the dashboard. Only once they approve it
    does anyone have a name to pass to pay_bill.

    There is one live request per obligation. If a request for the same bill is
    already pending or approved, that one is returned with `duplicate: true`
    rather than a second one being raised. A human should never be asked to
    approve the same money twice.

    Args:
        kind: "invoice", "rent" or "purchase_order".
        ref_id: The invoice id, lease id, or ticket id the money relates to.
        amount: Dollars requested.
        reason: Why the shop should pay this, in one line. A human reads it.
        ticket_id: Which ticket this came from, if any.
        requested_by: Which agent is asking.
    """
    if amount <= 0:
        return _refuse("An approval request needs an amount above zero.", amount=amount)
    if not reason.strip():
        return _refuse("An approval request needs a reason. A human has to read it.")

    today = _today()
    balance = _one("SELECT balance FROM cash_accounts WHERE name = 'checking'")

    # One live request per obligation. Several agents can reach the same
    # conclusion about the same bill, and a human seeing the same $840 three
    # times could approve it three times. Hand back the existing request
    # instead of stacking duplicates.
    settled = _one(
        """SELECT * FROM approvals
           WHERE lower(kind) = ? AND ref_id = ? AND lower(status) = 'paid'
           ORDER BY id LIMIT 1""",
        (kind.strip().lower(), ref_id),
    )
    if settled:
        return _refuse(
            f"This {kind} was already paid under approval {settled['id']}. "
            "There is nothing left to approve.",
            approval_id=settled["id"],
            already_paid=True,
        )

    existing = _one(
        """SELECT * FROM approvals
           WHERE lower(kind) = ? AND ref_id = ?
             AND lower(status) IN ('pending', 'approved')
           ORDER BY id LIMIT 1""",
        (kind.strip().lower(), ref_id),
    )
    if existing:
        return {
            "ok": True,
            "duplicate": True,
            "approval_id": existing["id"],
            "status": existing["status"],
            "kind": existing["kind"],
            "ref_id": existing["ref_id"],
            "amount": existing["amount"],
            "reason": existing["reason"],
            "ticket_id": existing["ticket_id"],
            "requested_by": existing["requested_by"],
            "requested_at": existing["requested_at"],
            "note": (
                f"A request for {existing['kind']} {existing['ref_id']} is already "
                f"{existing['status']} as approval {existing['id']}. Reusing it rather than "
                "asking a human to approve the same money twice."
            ),
        }

    with closing(_connect()) as conn:
        with conn:
            cur = conn.execute(
                """INSERT INTO approvals
                   (ticket_id, kind, ref_id, amount, reason, requested_by, requested_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (
                    ticket_id or None,
                    kind.strip().lower(),
                    ref_id,
                    amount,
                    reason.strip(),
                    requested_by,
                    today,
                ),
            )
    return {
        "ok": True,
        "approval_id": cur.lastrowid,
        "status": "pending",
        "kind": kind.strip().lower(),
        "ref_id": ref_id,
        "amount": amount,
        "reason": reason.strip(),
        "ticket_id": ticket_id or None,
        "requested_by": requested_by,
        "requested_at": today,
        "cash_if_approved": round(balance["balance"] - amount, 2) if balance else None,
        "note": "Nothing has been paid. A human decides this on the dashboard.",
    }


@mcp.tool
def list_approvals(status: str = "pending") -> dict:
    """The approval queue.

    Args:
        status: "pending", "approved", "denied", "paid", or "all".
    """
    if status.strip().lower() == "all":
        rows = _query("SELECT * FROM approvals ORDER BY id")
    else:
        rows = _query(
            "SELECT * FROM approvals WHERE lower(status) = lower(?) ORDER BY id", (status,)
        )
    return {"ok": True, "today": _today(), "count": len(rows), "approvals": rows}


@mcp.tool
def decide_approval(approval_id: int, decision: str, decided_by: str) -> dict:
    """Record a human's decision on a pending request. Still spends nothing.

    This is the human step. An agent must not call it on its own behalf. After
    an approval, the approver's name is what pay_bill needs.

    Args:
        approval_id: Which request is being decided.
        decision: "approved" or "denied".
        decided_by: The name of the person deciding. Required.
    """
    choice = decision.strip().lower()
    if choice not in ("approved", "denied"):
        return _refuse("Decision must be 'approved' or 'denied'.", decision=decision)
    if not decided_by or not decided_by.strip():
        return _refuse("A decision needs the name of the person making it.")

    row = _one("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    if not row:
        return _refuse(f"There is no approval request with id {approval_id}.")
    if row["status"] != "pending":
        return _refuse(
            f"Approval {approval_id} was already {row['status']}.", current_status=row["status"]
        )

    today = _today()
    with closing(_connect()) as conn:
        with conn:
            conn.execute(
                "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                (choice, decided_by.strip(), today, approval_id),
            )
    return {
        "ok": True,
        "approval_id": approval_id,
        "status": choice,
        "decided_by": decided_by.strip(),
        "decided_at": today,
        "kind": row["kind"],
        "ref_id": row["ref_id"],
        "amount": row["amount"],
        "note": (
            f"Approved. pay_bill can now be called with approved_by='{decided_by.strip()}'."
            if choice == "approved"
            else "Denied. No payment should be made."
        ),
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs operations MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve Streamable HTTP on port 8001 (keeps FastAPI free on 8000)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Restore data/campus_customs_new.db from the original, then exit",
    )
    args = parser.parse_args()
    if args.reset:
        print(reset_working_copy())
    elif args.http:
        mcp.run(transport="http", host="127.0.0.1", port=8001)
    else:
        mcp.run()
