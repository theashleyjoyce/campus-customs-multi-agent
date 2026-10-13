"""Exercise every Campus Customs MCP tool over the protocol, including refusals."""
import asyncio, json, sys
from fastmcp import Client

SERVER = "mcp/mcp_server.py"
results = []


def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


async def call(client, tool, **kw):
    r = await client.call_tool(tool, kw)
    return json.loads(r.content[0].text) if r.content else r.data


async def main():
    async with Client(SERVER) as client:
        print("\n### tool 1: check_stock")
        r = await call(client, "check_stock", sku="CC-TEE-WHITE", size="S", qty_wanted=1)
        check("ticket 101 tee is out of stock", r["on_hand"] == 0 and r["short_by"] == 1, f"short_by={r['short_by']}")
        r = await call(client, "check_stock", sku="CC-HOOD-NAVY", size="M", qty_wanted=20)
        check("ticket 103 hoodies short by 12", r["short_by"] == 12, f"on_hand={r['on_hand']}")
        r = await call(client, "check_stock", sku="CC-TEE-WHITE", size="XXL", qty_wanted=1)
        check("unknown size refused, lists real sizes", r["ok"] is False and "sizes_on_file" in r, str(r.get("sizes_on_file")))
        r = await call(client, "check_stock", sku="NOPE", size="S", qty_wanted=1)
        check("unknown sku refused", r["ok"] is False)

        print("\n### tool 2: check_vendor_for_restock")
        r = await call(client, "check_vendor_for_restock", sku="CC-TEE-WHITE")
        by = {v["name"]: v for v in r["vendors"]}
        check("uses shop date not real clock", r["today"] == "2026-08-31", r["today"])
        check("Bulldog Print Co blocked by open invoice", by["Bulldog Print Co"]["can_ship"] is False)
        check("blocking invoice is 501", by["Bulldog Print Co"]["open_invoices"][0]["id"] == 501)
        check("invoice aged 3 days overdue", by["Bulldog Print Co"]["open_invoices"][0]["days_overdue"] == 3)
        check("unblocked vendors report can_ship", by["QuickShip CT"]["can_ship"] is True)
        check("no invented sku-to-vendor match", "No column links a sku to a vendor" in r["note"])
        r = await call(client, "check_vendor_for_restock", sku="NOPE")
        check("unknown sku refused", r["ok"] is False)

        print("\n### tool 3: pay_bill (a name alone is not authorisation)")
        r = await call(client, "pay_bill", kind="invoice", ref_id=501, amount=840.0, approved_by="Ashley Joyce")
        check("REFUSES with no approval record at all", r["ok"] is False, "a typed name is not a human decision")
        seed = await call(client, "request_approval", kind="invoice", ref_id=501, amount=840.0,
                          reason="Unblock the apparel vendor", ticket_id=101)
        r = await call(client, "pay_bill", kind="invoice", ref_id=501, amount=840.0, approved_by="Ashley Joyce")
        check("REFUSES while the approval is still pending", r["ok"] is False, f"approval {seed['approval_id']}")
        await call(client, "decide_approval", approval_id=seed["approval_id"],
                   decision="approved", decided_by="Ashley Joyce")

        print("\n### tool 3: pay_bill (refusals first)")
        r = await call(client, "pay_bill", kind="invoice", ref_id=501, amount=840.0, approved_by="")
        check("REFUSES with no human approver", r["ok"] is False, "approval rule")
        r = await call(client, "pay_bill", kind="invoice", ref_id=501, amount=840.0, approved_by="   ")
        check("REFUSES whitespace-only approver", r["ok"] is False)
        big = await call(client, "request_approval", kind="purchase_order", ref_id=999,
                         amount=99999.0, reason="Deliberately unaffordable, to test the cash guard")
        await call(client, "decide_approval", approval_id=big["approval_id"],
                   decision="approved", decided_by="Ashley Joyce")
        r = await call(client, "pay_bill", kind="purchase_order", ref_id=999, amount=99999.0,
                       approved_by="Ashley Joyce")
        check("REFUSES overdraft even when approved", r["ok"] is False and r["short_by"] == 96599.0,
              "approval does not create money")
        r = await call(client, "pay_bill", kind="invoice", ref_id=9999, amount=10.0, approved_by="Ashley Joyce")
        check("REFUSES an invoice with no approval behind it", r["ok"] is False)
        r = await call(client, "pay_bill", kind="invoice", ref_id=501, amount=-5.0, approved_by="Ashley Joyce")
        check("REFUSES negative amount", r["ok"] is False)

        print("\n### tool 3: pay_bill (reference and amount must match what is owed)")
        r = await call(client, "pay_bill", kind="invoice", ref_id=501, amount=1.0, approved_by="Ashley Joyce")
        check("REFUSES underpaying an approved invoice", r["ok"] is False, "an $840 debt must not clear for $1")
        r = await call(client, "pay_bill", kind="invoice", ref_id=501, amount=900.0, approved_by="Ashley Joyce")
        check("REFUSES overpaying an invoice", r["ok"] is False)
        r = await call(client, "pay_bill", kind="rent", ref_id=9999, amount=2400.0, approved_by="Ashley Joyce")
        check("REFUSES rent on a lease that does not exist", r["ok"] is False)
        r = await call(client, "pay_bill", kind="Invoice", ref_id=501, amount=840.0, approved_by="Ashley Joyce")
        check("accepts kind regardless of casing", r["ok"] is True, "Invoice == invoice")
        r = await call(client, "check_vendor_for_restock", sku="NOPE")
        check("refusal cannot be flipped by splatted payload", r["ok"] is False, "the original bug")

        print("\n### tool 3: pay_bill (the real sequence)")
        r = await call(client, "pay_bill", kind="invoice", ref_id=501, amount=840.0, approved_by="Ashley Joyce")
        check("REFUSES double payment", r["ok"] is False, "501 was settled above")


        r = await call(client, "check_vendor_for_restock")
        by = {v["name"]: v for v in r["vendors"]}
        check("paying 501 UNBLOCKS the vendor", by["Bulldog Print Co"]["can_ship"] is True, "chokepoint clears")

        rent = await call(client, "request_approval", kind="rent", ref_id=1, amount=2400.0,
                          reason="Monthly rent on the Chapel Street lease", ticket_id=102)
        await call(client, "decide_approval", approval_id=rent["approval_id"],
                   decision="approved", decided_by="Ashley Joyce")
        r = await call(client, "pay_bill", kind="rent", ref_id=1, amount=2400.0, approved_by="Ashley Joyce")
        check("pays approved rent, balance $160", r["ok"] and r["balance_after"] == 160.0, f"${r.get('balance_after')}")
        po = await call(client, "request_approval", kind="purchase_order", ref_id=1, amount=264.0,
                        reason="Restock the 12 missing hoodies", ticket_id=103)
        await call(client, "decide_approval", approval_id=po["approval_id"],
                   decision="approved", decided_by="Ashley Joyce")
        r = await call(client, "pay_bill", kind="purchase_order", ref_id=1, amount=264.0, approved_by="Ashley Joyce")
        check("REFUSES approved restock it cannot afford", r["ok"] is False and r["short_by"] == 104.0,
              "approval does not create money")

        print("\n### approvals: one live request per obligation")
        # Invoice 501 and lease 1 are both settled by this point in the run, so
        # these use obligations that are still open.
        a = await call(client, "request_approval", kind="purchase_order", ref_id=777, amount=120.0,
                       reason="Restock run", ticket_id=101, requested_by="accounting")
        check("first request is created", a["ok"] and not a.get("duplicate"), f"id={a.get('approval_id')}")
        b = await call(client, "request_approval", kind="purchase_order", ref_id=777, amount=120.0,
                       reason="Same order, different agent", ticket_id=103, requested_by="inventory")
        check("second request for the same obligation is deduplicated",
              b.get("duplicate") is True and b["approval_id"] == a["approval_id"],
              "a human must not approve the same money twice")
        r = await call(client, "request_approval", kind="purchase_order", ref_id=778, amount=60.0,
                       reason="A different order", ticket_id=103)
        check("a different obligation still gets its own request", not r.get("duplicate"))
        q = await call(client, "list_approvals", status="pending")
        total = sum(x["amount"] for x in q["approvals"])
        check("queue totals the real obligation", total == 180.0,
              f"{q['count']} pending, ${total:,.2f}")
        d = await call(client, "decide_approval", approval_id=a["approval_id"],
                       decision="approved", decided_by="Ashley Joyce")
        check("a human can approve it", d["ok"] is True)
        d2 = await call(client, "decide_approval", approval_id=a["approval_id"],
                        decision="denied", decided_by="Ashley Joyce")
        check("REFUSES deciding the same request twice", d2["ok"] is False)
        e = await call(client, "decide_approval", approval_id=r["approval_id"],
                       decision="approved", decided_by="")
        check("REFUSES an unnamed decision", e["ok"] is False)
        again = await call(client, "request_approval", kind="invoice", ref_id=501, amount=840.0,
                           reason="Already settled earlier in this run", ticket_id=101)
        check("REFUSES a request for something already paid",
              again["ok"] is False and again.get("already_paid") is True,
              "a settled bill cannot be re-requested")

    passed = sum(1 for _, c, _ in results if c)
    print(f"\n=== {passed}/{len(results)} checks passed ===")
    if passed != len(results):
        print("FAILURES:", [n for n, c, _ in results if not c])
        sys.exit(1)

asyncio.run(main())
