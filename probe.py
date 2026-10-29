#!/usr/bin/env python3
"""Probe #49: Karz & Dolls — do the links the tracker actually sends open?
Every in-stock car's link as stored in seen.json (the tracker trims the slug's
trailing spaces, non-breaking ones too), against the page; for any that don't,
the slug exactly as the shelf gives it, and that slug written the new way
('?', '#', '%' encoded twice). Plus: the McLaren LB?WORKS in KND's search.
Read-only."""
import json, re, collections, time
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
KD = "https://www.karzanddolls.com"
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
SHELVES = ["/hot-wheels/mainlines", "/hot-wheels/pop-culture", "/hot-wheels/card-art-premiums", "/hot-wheels/gift-pack",
           "/hot-wheels/car-culture", "/hot-wheels/fast-and-furious", "/hot-wheels/boulevard-series", "/hot-wheels/team-transport",
           "/hot-wheels/character-cars", "/hot-wheels/disney-cars", "/hot-wheels/hot-wheels-accessories", "/mini-gt/mini-gt",
           "/mini-gt/mini-gt-blister-pack", "/mini-gt/kaido-house", "/pre-orders/pre-order-minigt", "/pre-orders/pre-order-special-stock",
           "/specials/chase-car", "/specials/special-stocks-64-43-scale", "/", "/hot-wheels/monster-trucks", "/matchbox/matchbox-basic-cars",
           "/matchbox/matchbox-moving-parts", "/matchbox/matchbox-superfast", "/majorette/premium-cars", "/majorette/basic-cars", "/majorette/majorette"]


def get(url):
    for i in range(2):
        try:
            r = http.get(url, headers=H, timeout=25, allow_redirects=True, **IMP)
            return r.status_code, r.text
        except Exception:
            time.sleep(1)
    return None, ""


def nd(page):
    m = NEXT.search(page or "")
    return json.loads(m.group(1)) if m else {}


def prods(page):
    pp = (nd(page).get("props") or {}).get("pageProps") or {}
    found, stack = [], [pp]
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            if "pid" in n and "pro_name" in n and "slug" in n:
                found.append(n)
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
    return found


def opens(url, pid):
    code, page = get(url)
    d = ((nd(page).get("props") or {}).get("pageProps") or {}).get("productdetails") or {}
    return code, str(d.get("pid")) == pid, d


def new_url(slug, pid):
    path = "".join(quote(quote(c, safe=""), safe="") if c in "?#%" else quote(c, safe="-_.~") for c in slug)
    return f"{KD}/details/{path}?pid={quote(pid, safe='')}"


raw = {}
with ThreadPoolExecutor(8) as ex:
    for s, (code, page) in zip(SHELVES, ex.map(lambda s: get(KD + s), SHELVES)):
        for p in prods(page):
            raw.setdefault(str(p["pid"]), p)
cars = json.load(open("kd_ins.json"))
print(f"{len(cars)} in-stock cars in seen.json; {len(raw)} products on the shelves now")
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(lambda c: (c, *opens(c["url"], c["pid"])), cars))
ok = [r for r in res if r[2]]
bad = [r for r in res if not r[2]]
print(f"the tracker's stored link opens the car: {len(ok)}; doesn't: {len(bad)}")
kinds = collections.Counter()
rows = []
for c, code, good, d in bad:
    p = raw.get(c["pid"])
    if not p:
        kinds["no longer on any shelf"] += 1
        rows.append({**c, "http": code, "why": "gone"})
        continue
    slug = str(p["slug"])
    tail = "trailing nbsp" if slug != slug.rstrip() else ("has ?#%" if re.search(r"[?#%]", slug) else "other")
    kinds[tail] += 1
    u2 = new_url(slug, c["pid"])
    code2, good2, _ = opens(u2, c["pid"])
    rows.append({**c, "http": code, "raw_slug": slug, "in_stock_now": p.get("in_stock"), "new_url": u2, "new_http": code2, "new_opens": good2})
    print(f"  ✗ {code} {c['url'][len(KD):][:90]!r}\n      raw slug {slug!r} in_stock={p.get('in_stock')} → new link HTTP {code2} opens: {good2}")
print("why the failures:", dict(kinds))
# the trimmed-vs-raw question for every in-stock car on the shelves whose slug ends in whitespace
trail = [p for p in raw.values() if str(p["slug"]) != str(p["slug"]).rstrip() and str(p.get("in_stock")) == "1"]
print(f"\n{len(trail)} in-stock shelf cars have a slug ending in (non-breaking) space; trimmed vs raw vs new:")
T = collections.Counter()
for p in trail[:40]:
    slug, pid = str(p["slug"]), str(p["pid"])
    a = opens(f"{KD}/details/{quote(slug.strip(), safe='-_.~')}?pid={pid}", pid)[1]
    b = opens(new_url(slug, pid), pid)[1]
    T[(a, b)] += 1
    if not (a and b):
        print(f"  trimmed opens: {a}  new opens: {b}  {slug!r}")
print("  (trimmed opens, new opens):", dict(T))
print("\n=== the McLaren in KND's search ===")
for term in ("boring concept", "720s", "lb works mclaren"):
    code, page = get(f"{KD}/search?term={quote(term)}")
    for p in prods(page):
        if "720" in str(p.get("pro_name")) or "BORING" in str(p.get("pro_name")).upper():
            print(f"  {term!r}: pid={p['pid']} in_stock={p.get('in_stock')} ₹{p.get('dis_price')} sku={str(p.get('sku')).strip()!r} name={str(p.get('pro_name')).strip()!r} slug={str(p.get('slug'))!r}")
json.dump({"bad": rows, "ok": len(ok), "trail": dict((str(k), v) for k, v in T.items())}, open("probe_report.json", "w"), indent=1, default=str)
