#!/usr/bin/env python3
"""Probe #46: Karz & Dolls — what does a SOLD-OUT car's page show (404, or the
page with "sold out")? Is the shelf page cached (stale stock)? Which product
does a page show when two share one slug? And the McLaren LB?WORKS once more.
Read-only."""
import json, re, html, collections, time
from urllib.parse import quote, unquote
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
KD = "https://www.karzanddolls.com"
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
CACHE_H = ("cache-control", "age", "x-nextjs-cache", "x-vercel-cache", "cf-cache-status", "x-cache", "server", "via", "x-powered-by", "etag", "last-modified", "date")


def get(url, **kw):
    try:
        t = time.time()
        r = http.get(url, headers={**H, **kw.pop("h", {})}, timeout=25, allow_redirects=True, **IMP, **kw)
        return r.status_code, r.text, {k: r.headers.get(k) for k in CACHE_H if r.headers.get(k)}, round(time.time() - t, 2)
    except Exception as e:
        return None, "", {"err": type(e).__name__}, 0


def nd(page):
    m = NEXT.search(page or "")
    return json.loads(m.group(1)) if m else {}


def prods(obj):
    found, stack = [], [obj]
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            if "pid" in n and ("pro_name" in n or "in_stock" in n):
                found.append(n)
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
    return found


def page_summary(code, page):
    d = nd(page)
    pp = (d.get("props") or {}).get("pageProps") or {}
    ps = prods(pp)
    main = ps[0] if ps else {}
    words = [w for w in ("Page not found", "Out of stock", "OUT OF STOCK", "Sold out", "SOLD OUT", "Notify", "NOTIFY", "Add to cart", "ADD TO CART", "Buy now", "BUY NOW") if w in (page or "")]
    return {"http": code, "page": d.get("page"), "props_keys": sorted(pp.keys())[:12], "n_products": len(ps),
            "main": {k: main.get(k) for k in ("pid", "pro_name", "in_stock", "is_approved", "qty", "stock", "quantity", "add_limit", "is_preorder") if k in main},
            "words": words, "notFound": pp.get("notFound") if isinstance(pp, dict) else None}


rep = {}
cases = json.load(open("kd_oos.json"))

print("=== A. sold-out cars (as the tracker last saw them) ===")
A = []
for c in cases["oos"]:
    code, page, hd, dt = get(c["url"])
    s = page_summary(code, page)
    A.append({**c, **s})
    print(f"  {s['http']}  {c['last_seen'][:16]}  words={s['words']}  main={s['main']}  {c['name'][:50]!r}")
print("=== A2. in-stock cars (controls) ===")
for c in cases["ins"]:
    code, page, hd, dt = get(c["url"])
    s = page_summary(code, page)
    A.append({**c, **s, "control": True})
    print(f"  {s['http']}  words={s['words']}  main={s['main']}  {c['name'][:50]!r}")
rep["A"] = A
cnt = collections.Counter((x.get("control", False), x["http"]) for x in A)
print("  counts (control?, http):", dict(cnt))

print("\n=== B. shelf pages: cached? sold-out cars listed? ===")
B = {}
build = None
for s in ["/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack", "/hot-wheels/mainlines", "/"]:
    out = []
    for i in range(2):
        code, page, hd, dt = get(KD + s)
        d = nd(page)
        build = build or d.get("buildId")
        ps = prods((d.get("props") or {}).get("pageProps") or {})
        inst = collections.Counter(str(p.get("in_stock")) for p in ps)
        out.append({"http": code, "headers": hd, "secs": dt, "n": len(ps), "in_stock": dict(inst)})
        print(f"  {s:32} try {i+1}: HTTP {code} {dt}s n={len(ps)} in_stock={dict(inst)} headers={hd}")
        time.sleep(2)
    B[s] = out
rep["B"] = B
print("  buildId:", build)

print("\n=== C. two products with one slug: which one does the page show? ===")
allp = {}
for s in ["/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack", "/mini-gt/kaido-house", "/pre-orders/pre-order-minigt", "/"]:
    code, page, hd, dt = get(KD + s)
    for p in prods((nd(page).get("props") or {}).get("pageProps") or {}):
        if p.get("slug"):
            allp[str(p["pid"])] = p
byslug = collections.defaultdict(list)
for p in allp.values():
    byslug[str(p["slug"])].append(p)
dups = {k: v for k, v in byslug.items() if len({str(x["pid"]) for x in v}) > 1}
print(f"  {len(allp)} products, {len(dups)} slugs shared by 2+ products")
C = []
for slug, ps in list(dups.items())[:6]:
    for p in ps:
        url = f"{KD}/details/{quote(slug, safe='-_.~')}?pid={p['pid']}"
        code, page, hd, dt = get(url)
        s = page_summary(code, page)
        shown = s["main"].get("pid")
        C.append({"slug": slug, "pid": p["pid"], "price": p.get("dis_price"), "sku": p.get("sku"), "shows_pid": shown, "http": code})
        print(f"  slug={slug[:50]!r} pid={p['pid']} ₹{p.get('dis_price')} sku={str(p.get('sku'))[:26]!r} → HTTP {code}, page shows pid={shown} {'(the SAME)' if shown == p['pid'] else '(ANOTHER ONE)'}")
rep["C"] = C

print("\n=== D. the McLaren LB?WORKS (both pids) ===")
D = []
for pid in ["OyLoZkMNb2", "RnLjVk9Lm0"]:
    for label, url in [("tracker's link", f"{KD}/details/mclaren-720s-lb%3Fworks-the-boring-concept?pid={pid}"),
                       ("cut at '?'", f"{KD}/details/mclaren-720s-lb?works-the-boring-concept?pid={pid}"),
                       ("%253F", f"{KD}/details/mclaren-720s-lb%253Fworks-the-boring-concept?pid={pid}")]:
        code, page, hd, dt = get(url)
        s = page_summary(code, page)
        D.append({"pid": pid, "label": label, **s})
        print(f"  {pid} {label:15} HTTP {code} words={s['words']} main={s['main']}")
    if build:
        for label, url in [("data route", f"{KD}/_next/data/{build}/details/mclaren-720s-lb%3Fworks-the-boring-concept.json?pid={pid}&slug=mclaren-720s-lb%3Fworks-the-boring-concept")]:
            code, page, hd, dt = get(url, h={"x-nextjs-data": "1", "Accept": "*/*"})
            D.append({"pid": pid, "label": label, "http": code, "body": (page or "")[:400]})
            print(f"  {pid} {label:15} HTTP {code} {(page or '')[:300]!r}")
if build and cases["oos"]:
    c = cases["oos"][0]
    slug = c["url"].split("/details/")[1].split("?")[0]
    code, page, hd, dt = get(f"{KD}/_next/data/{build}/details/{slug}.json?pid={c['pid']}&slug={slug}", h={"x-nextjs-data": "1", "Accept": "*/*"})
    print(f"  (a sold-out car's data route) HTTP {code} {(page or '')[:300]!r}")
    c = cases["ins"][0]
    slug = c["url"].split("/details/")[1].split("?")[0]
    code, page, hd, dt = get(f"{KD}/_next/data/{build}/details/{slug}.json?pid={c['pid']}&slug={slug}", h={"x-nextjs-data": "1", "Accept": "*/*"})
    print(f"  (an in-stock car's data route) HTTP {code} {(page or '')[:300]!r}")
rep["D"] = D

print("\n=== E. where the shop's own search/API lives ===")
code, page, hd, dt = get(KD + "/")
for m in sorted(set(re.findall(r'https?://[a-zA-Z0-9.\-]*karzanddolls[a-zA-Z0-9.\-/]*', page or "")))[:20]:
    print("  ", m)
srcs = re.findall(r'<script[^>]+src="([^"]+_app[^"]*\.js)"', page or "") + re.findall(r'<script[^>]+src="([^"]+details[^"]*\.js)"', page or "")
print("  app scripts:", srcs[:4])
apis = set()
for src in srcs[:2]:
    c2, js, _, _ = get(src if src.startswith("http") else KD + src, h={"Accept": "*/*"})
    for m in re.findall(r'["\'](https?://[^"\']{6,80})["\']', js or ""):
        if "api" in m.lower() or "karz" in m.lower():
            apis.add(m)
    for m in re.findall(r'["\'](/api/[^"\']{2,60})["\']', js or ""):
        apis.add(m)
print("  API-ish strings:", sorted(apis)[:30])
rep["E"] = sorted(apis)[:60]
json.dump(rep, open("probe_report.json", "w"), indent=1, default=str)
