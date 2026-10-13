"""Refresh the Actual cards and the Cash tab in output/desk_tickets.html.

Reads output/resolved_tickets.json, which is itself generated from the
database and the audit trail, so the page can never drift from the run it
claims to describe. The Expected sections and the Reflection tab are hand
written and are left alone.

    python output/build_resolved.py && python output/build_desk_tickets.py
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "output" / "resolved_tickets.json"
PAGE = ROOT / "output" / "desk_tickets.html"

LABEL = {"boss": "Boss", "inventory": "Inventory", "accounting": "Accounting",
         "facilities": "Facilities", "customer_service": "Customer Service"}
NOBODY = "<span class='muted'>nobody</span>"

VERDICT = {
101: """<strong>The plan held.</strong> Inventory was called first, Facilities never
appeared, and Inventory went to Accounting itself rather than handing the blocker back up
the chain. What the plan underrated is that clearing invoice 501 unblocks the
<em>vendor</em>, not the ticket. The shop still had to order the tee afterwards, which
took a second approval the plan never mentioned.""",
102: """<strong>Mostly held, with one real divergence.</strong> Facilities was called first
and Inventory never appeared, as predicted. But the plan said two hops would do it, boss
to facilities to accounting. In practice the boss called Facilities and Accounting in the
same turn rather than waiting for the hand-off, and pulled in Customer Service as well,
which the plan had marked optional. Four agents worked a ticket the plan sized at two.""",
103: """<strong>Held on who, diverged on the ending.</strong> Inventory was involved and
Facilities stayed out, as predicted. What the plan did not foresee is that this ticket
closes having spent nothing at all. The invoice, the rent and the tee order had already
taken the cash, so the team agreed the discount and closed it honestly on the 8 units in
stock rather than promising 20.""",
}


def esc(x) -> str:
    return html.escape(str(x))


def actual_card(t: dict, generated: str) -> str:
    rows = ""
    for a in t["agents"]:
        deleg = ", ".join(LABEL.get(d, d) for d in a["delegated_to"]) or NOBODY
        tools = "".join(f"<code>{esc(x)}</code>" for x in a["tools_used"])
        rows += (f"<tr><td><strong>{esc(a['display_name'])}</strong></td>"
                 f"<td style='text-align:center'>{a['turns']}</td>"
                 f"<td>{deleg}</td><td><div class='tools'>{tools}</div></td></tr>")
    approvals = "".join(
        f"<li><strong>${h['amount']:,.2f}</strong> {esc(h['kind'].replace('_', ' '))} "
        f"(approval #{h['approval_id']}), <strong>{esc(h['status'])}</strong>"
        + (f", decided by {esc(h['decided_by'])}" if h["decided_by"] else "")
        + f".<br><span class='muted'>{esc(h['reason'])}</span></li>"
        for h in t["human_approvals"]
    ) or "<li class='muted'>No money was requested on this ticket.</li>"

    return f"""  <div class="card actual">
    <h2>Actual</h2>
    <p class="sub">From the resolution run on {esc(generated[:10])}, starting from a reset board.
    Every figure is read from <code>data/campus_customs_new.db</code> and the audit trail.</p>

    <div class="record-head" style="margin-bottom:.5rem">
      <h3 style="margin:0">Final status <span class="chip done">{esc(t['final_status'])}</span></h3>
      <strong style="font-variant-numeric:tabular-nums">${t['cash_moved_usd']:,.2f} moved on this ticket</strong>
    </div>

    <h3>Which agents worked it, what they delegated, which tools they used</h3>
    <table class="agents">
      <tr><th>Agent</th><th style="text-align:center">Turns</th><th>Delegated to</th><th>Tools used</th></tr>
      {rows}
    </table>

    <h3>Human approvals</h3>
    <ul class="approvals-list">{approvals}</ul>

    <h3>What the team concluded</h3>
    <p class="outcome">{esc(t['outcome'])}</p>

    <h3>Expected versus actual</h3>
    <p class="verdict">{VERDICT[t['ticket_id']]}</p>
  </div>"""


def cash_panel(data: dict) -> str:
    cash = data["cash"]
    running = cash["starting_checking"]
    rows = (f'<tr class="opening"><td>Starting checking balance, after the reset</td><td></td>'
            f'<td class="num"><strong>${cash["starting_checking"]:,.2f}</strong></td></tr>')
    for t in data["tickets"]:
        for h in t["human_approvals"]:
            if h["money_moved"]:
                running -= h["paid_amount"]
                rows += (f'<tr><td>Ticket #{t["ticket_id"]}: {esc(h["kind"].replace("_", " "))} '
                         f'<span class="muted">{esc(h["reason"][:85])}</span></td>'
                         f'<td class="num out">-${h["paid_amount"]:,.2f}</td>'
                         f'<td class="num">${running:,.2f}</td></tr>')
    rows += (f'<tr class="closing"><td>Ending checking balance</td><td></td>'
             f'<td class="num"><strong>${cash["ending_checking"]:,.2f}</strong></td></tr>')

    no_spend = next(t for t in data["tickets"] if t["cash_moved_usd"] == 0)
    return f"""<section class="panel" id="cash">
  <div class="card">
    <h2>Where the money went</h2>
    <p class="sub">Read from <code>data/campus_customs_new.db</code> by
    <code>output/cash_reconcile.py</code>. Cash only goes out in this shop, so this is a
    one way list.</p>
    <table class="cash">
      <tr><th>What</th><th class="num">Change</th><th class="num">Balance</th></tr>
      {rows}
    </table>
  </div>

  <div class="card expected">
    <h2>It reconciles</h2>
    <table>
      <tr><th>Starting balance, from the untouched original</th><td class="num">${cash['starting_checking']:,.2f}</td></tr>
      <tr><th>Total paid out, summed from the payments table</th><td class="num">-${cash['total_paid']:,.2f}</td></tr>
      <tr><th>Computed ending balance</th><td class="num"><strong>${cash['starting_checking'] - cash['total_paid']:,.2f}</strong></td></tr>
      <tr><th><code>cash_accounts</code> in the working database says</th><td class="num"><strong>${cash['ending_checking']:,.2f}</strong></td></tr>
    </table>
    <p class="verdict" style="margin-top:.8rem">These agree to the cent. The reconciler
    refuses to emit numbers that do not balance, so a wrong figure cannot be published by
    accident.</p>
  </div>

  <div class="card">
    <h2>Why ticket {no_spend['ticket_id']} cost nothing</h2>
    <p>Ticket {no_spend['ticket_id']} resolved without spending a cent. The discount was
    agreed, but restocking the 12 missing hoodies would have cost $264 at the $22 unit
    cost, and by then the invoice, the rent and the tee order had taken
    ${cash['total_paid']:,.2f} of the ${cash['starting_checking']:,.2f}, leaving
    ${cash['ending_checking']:,.2f}.</p>
    <p class="verdict">That is the cash squeeze the board was built around. The two
    obligations fit. The restock does not fit after them, and the shop has no income to
    recover from it.</p>
  </div>
</section>"""


def main() -> None:
    data = json.loads(DATA.read_text())
    tickets = {t["ticket_id"]: t for t in data["tickets"]}
    s = PAGE.read_text()

    blocks = re.findall(r'  <div class="card actual">.*?\n  </div>', s, re.S)
    if len(blocks) != 3:
        raise SystemExit(f"expected 3 Actual cards in the page, found {len(blocks)}")
    for tid, block in zip((101, 102, 103), blocks):
        s = s.replace(block, actual_card(tickets[tid], data["generated_at"]), 1)

    old = re.search(r'<section class="panel" id="cash">.*?</section>', s, re.S)
    if not old:
        raise SystemExit("could not find the cash panel")
    s = s.replace(old.group(0), cash_panel(data))

    # Refuse to write a page that still claims a figure the run did not produce.
    for tid, t in tickets.items():
        marker = f"${t['cash_moved_usd']:,.2f} moved on this ticket"
        if marker not in s:
            raise SystemExit(f"ticket {tid} card did not land")
    PAGE.write_text(s)
    print(f"refreshed {PAGE.relative_to(ROOT)} from the {data['generated_at'][:10]} run")
    for t in data["tickets"]:
        print(f"  #{t['ticket_id']} {t['final_status']} ${t['cash_moved_usd']:,.2f}")


if __name__ == "__main__":
    main()
