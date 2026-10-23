#!/usr/bin/env python3
"""Probe #31: FirstCry's checkout cart (LoadCart, guest cookie cart — nothing is
stored or ordered) as the bot's final word on "can 248001 buy it right now?".
  A. Batch size: 10 / 25 / 50 / 100 cars in one call — time, bytes, cars back.
  B. Every car the bot currently holds "in stock": does the cart agree?
  C. Twice more, 60 s apart: how often does the cart's answer change?
"""
import collections, json, time, urllib.request, uuid
from curl_cffi import requests as http

T0 = time.time()
IMP = {"impersonate": "chrome124"}
UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
URL = "https://CSC.fcappservices.in/ShoppingCart/ShoppingCart.svc/json/LoadCart"
H = {"User-Agent": UA, "Accept": "application/json, text/javascript, */*; q=0.01",
     "Content-Type": "application/json; charset=utf-8", "Origin": "https://checkout.firstcry.com",
     "Referer": "https://checkout.firstcry.com/pay", "fcdid": str(uuid.uuid4()), "fingerprint": uuid.uuid4().hex}
with urllib.request.urlopen("https://raw.githubusercontent.com/Abhijndl/BotHW/main/seen.json", timeout=30) as r:
    seen = json.load(r)
fc = {k[3:]: v for k, v in seen.items() if k.startswith("fc_") and isinstance(v, dict) and k[3:].isdigit()}
held = [p for p, v in fc.items() if v.get("stock") == "in_stock"]
outs = [p for p, v in fc.items() if v.get("stock") != "in_stock"]
print(f"seen.json: {len(fc)} FirstCry cars, {len(held)} held in stock")


def body(pro):
    return {"pro": pro, "shipPin": "248001", "SiteType": 0, "LC": 0, "CR": 0, "Coupons": "", "FC_AUTH": "",
            "ShipMobile": "", "ShipPhone": "", "PayBack": "", "State": "", "PaymentType": "", "LPO": False,
            "LSD": False, "CCA": "", "LT": "N", "UA": UA + " Mobile", "AddressType": "Home", "AssemblyMap": "",
            "ptype": "", "pvalue": "", "FitKidChildIdMap": "", "CouponCodeToCheck": "", "GiftCodeToCheck": "",
            "BuyerType": "", "CardPar": "", "RemoveFreeErr": "", "redesign": True, "caller": "", "Ageid": "",
            "bmsm": "", "SegmentIDs": "", "latlong": "", "segmentcookie": "", "cardref": "",
            "savedCardBankCode": "", "savedCardIssuingBank": "", "cardtoken": ""}


def cart(pids):
    pro = "*".join(f"NO^{p}^1^0" for p in pids)
    t = time.time()
    try:
        r = http.post(URL, data=json.dumps(body(pro)), headers=H, timeout=30, **IMP)
    except Exception as e:
        return None, f"ERR {type(e).__name__}", time.time() - t, 0
    secs, size = time.time() - t, len(r.content)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}", secs, size
    d = r.json()
    x = d.get("LoadCartResult")
    while isinstance(x, str):
        x = json.loads(x)
    items = ((x or {}).get("pOrderSummary") or {}).get("PurchaseOrderItemList") or []
    out = {}
    for it in items:
        ok = ((it.get("CurrentStock") or 0) > 0 and (it.get("IsServicable") or 0) > 0
              and str(it.get("warehouseid") or "0") != "0"
              and not ((it.get("NoOfPinCodeToCheck") or 0) > 0 and not it.get("isValidPincodeForDropShipment")))
        out[str(it.get("ProductID"))] = {"ok": ok, "cs": it.get("CurrentStock"), "isv": it.get("IsServicable"),
                                         "wh": it.get("warehouseid"), "np": it.get("NoOfPinCodeToCheck"),
                                         "vd": it.get("isValidPincodeForDropShipment"), "st": it.get("StockType"),
                                         "ls": it.get("likelysoldout"), "q": it.get("isQwik"),
                                         "eta": it.get("EstimatedDeliveryDate"), "nm": (it.get("ProductName") or "")[:44]}
    return out, "ok", secs, size


print("\n" + "=" * 20, "A. batch sizes", "=" * 20)
pool = held + outs
for n in (10, 25, 50, 100):
    ps = pool[:n]
    res, err, secs, size = cart(ps)
    print(f"  {n:3} cars: {err}, {secs:.1f}s, {size/1024:.0f} KB, {len(res or {})} back")
    time.sleep(1)

print("\n" + "=" * 20, "B. cars the bot holds in stock vs the cart", "=" * 20)
B = 40
rounds = []
for rnd in range(3):
    ans = {}
    for i in range(0, len(held), B):
        res, err, secs, size = cart(held[i:i + B])
        if res is None:
            print(f"  round {rnd} batch {i}: {err}")
            continue
        for p in held[i:i + B]:
            ans[p] = res.get(p, {"ok": False, "gone": True})
        time.sleep(0.5)
    rounds.append(ans)
    c = collections.Counter("yes" if a.get("ok") else ("not in cart" if a.get("gone") else "no") for a in ans.values())
    print(f"{time.time()-T0:5.0f}s round {rnd}: {dict(c)}")
    if rnd == 0:
        for p, a in sorted(ans.items(), key=lambda x: x[1].get("ok")):
            if not a.get("ok"):
                v = fc[p]
                print(f"     NO  {p} {v.get('fc_live')}/{v.get('fc_lst')} {json.dumps({k: a.get(k) for k in ('cs','isv','wh','np','vd','st','ls','q','gone')})} {v.get('name','')[:46]}")
        yes = [p for p, a in ans.items() if a.get("ok")]
        for p in yes[:8]:
            a = ans[p]
            print(f"     yes {p} cs {a['cs']} wh {a['wh']} eta {a['eta']} {a['nm']}")
    if rnd < 2:
        time.sleep(max(0, 60 - (time.time() - T0) % 60))
flips = [p for p in held if len({bool(r.get(p, {}).get("ok")) for r in rounds if p in r}) > 1]
print(f"\nanswers that changed across the 3 rounds: {len(flips)}", flips[:20])
json.dump({"rounds": rounds}, open("probe_report.json", "w"))
print(f"done in {time.time()-T0:.0f}s")
