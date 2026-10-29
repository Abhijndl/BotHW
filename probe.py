#!/usr/bin/env python3
"""Probe #56: Karz & Dolls' guest cart — does it show the real unit count
(pro_stock, which the shop itself uses for "Only N items allowed")? Two fresh
guest carts (random visitor ids, no account), ordinary non-hyped Mini GT cars
only, one unit each; read the carts; check that cart B sees the same count
while the car sits in cart A (so a cart doesn't hold stock); then every item is
removed again. Nothing is ordered."""
import json, re, uuid, time
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "application/json", "Content-Type": "application/json",
     "Origin": "https://www.karzanddolls.com", "Referer": "https://www.karzanddolls.com/"}
KD = "https://www.karzanddolls.com"
API = KD + "/karzOffice/api"
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
HYPE = re.compile(r"LB[\s\-]*WORKS|LBWK|LIBERTY|PORSCHE|MCLAREN|LAMBORGHINI|FERRARI|SKYLINE|GT-?R|SUPRA|SILHOUETTE|KAIDO|NISMO|BUGATTI", re.I)


def page(path):
    r = http.get(KD + path, headers={**H, "Accept": "text/html"}, timeout=25, **IMP)
    m = NEXT.search(r.text)
    return json.loads(m.group(1)) if m else {}


def attr_qty(d):
    try:
        resp = json.loads(d.get("product_attr") or "{}").get("response") or []
        return resp[0].get("qty") if resp else None
    except Exception:
        return None


shelf = page("/mini-gt/mini-gt")
prods = []
stack = [shelf.get("props", {}).get("pageProps", {})]
while stack:
    n = stack.pop()
    if isinstance(n, list):
        stack.extend(n)
    elif isinstance(n, dict):
        if "pid" in n and "pro_name" in n and "slug" in n:
            prods.append(n)
        stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
plain = [p for p in prods if str(p.get("in_stock")) == "1" and not HYPE.search(str(p["pro_name"])) and int(p.get("add_limit") or 0) >= 3]
print(f"{len(prods)} on the Mini GT shelf, {len(plain)} ordinary ones in stock to choose from")
details = {}
for p in plain[:40]:
    d = page(f"/details/{p['slug'].strip()}?pid={p['pid']}").get("props", {}).get("pageProps", {}).get("productdetails") or {}
    if d.get("id"):
        details[d["id"]] = (p, attr_qty(d))
big = [i for i, (p, q) in details.items() if q not in (None, "") and int(q) >= 20][:2]
zero = [i for i, (p, q) in details.items() if q in ("0", 0)][:4]
none = [i for i, (p, q) in details.items() if q is None][:2]
small = [i for i, (p, q) in details.items() if q not in (None, "") and 1 <= int(q) <= 5][:2]
pick = big + zero + none + small
print("picked:", [(i, details[i][0]["pro_name"][:40], details[i][1]) for i in pick])


def cart(vid):
    r = http.get(f"{API}/cart/visitor?visitor_id={vid}", headers=H, timeout=20, **IMP)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}


def add(vid, pid_num):
    r = http.post(f"{API}/cart/visitor/add", headers=H, data=json.dumps({"visitor_id": vid, "product_id": pid_num, "quantity": 1}), timeout=20, **IMP)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}


def remove(vid, item_id):
    r = http.post(f"{API}/cart/visitor/remove", headers=H, data=json.dumps({"visitor_id": vid, "cart_item_id": item_id}), timeout=20, **IMP)
    return r.status_code, r.text[:160]


A, B = str(uuid.uuid4()), str(uuid.uuid4())
for i in pick:
    print("add to A:", i, add(A, i))
code, ca = cart(A)
items = (ca.get("data") or []) if isinstance(ca, dict) else []
print(f"\ncart A: HTTP {code}, {len(items)} items")
if items:
    it = items[0]
    print("  item keys:", sorted(it.keys()))
    print("  product keys:", sorted((it.get("product") or {}).keys()))
stockA = {}
for it in items:
    pr = it.get("product") or {}
    stockA[pr.get("id")] = pr.get("pro_stock")
    print(f"  id={pr.get('id')} pro_stock={pr.get('pro_stock')} add_limit={pr.get('add_limit')} in_stock={pr.get('in_stock')} "
          f"page qty={details.get(pr.get('id'), (None, '?'))[1]}  {str(pr.get('pro_name'))[:50]!r}")
# cart B sees the same count while the car is in cart A?
for i in big:
    print("add to B:", i, add(B, i))
code, cb = cart(B)
itemsB = (cb.get("data") or []) if isinstance(cb, dict) else []
for it in itemsB:
    pr = it.get("product") or {}
    print(f"  B: id={pr.get('id')} pro_stock={pr.get('pro_stock')} (A saw {stockA.get(pr.get('id'))})")
# clean up
for vid, its in ((A, items), (B, itemsB)):
    for it in its:
        print("remove", vid[:8], it.get("id"), remove(vid, it.get("id")))
print("after cleanup: A", cart(A)[1].get("data") if isinstance(cart(A)[1], dict) else "?", " B", cart(B)[1].get("data") if isinstance(cart(B)[1], dict) else "?")
