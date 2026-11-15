#!/usr/bin/env python3
"""Probe #67: inside the two feeds — Sovereign Scents' /api/products and Acordell's
WooCommerce Store API: where partials live, stock, prices, links, paging, pace."""
import gzip, json, re, time, urllib.error, urllib.request
from collections import Counter

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def get(url, timeout=20, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                               "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, data, hdr = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, "", dict(e.headers or {}), int((time.time() - t) * 1000)
    except Exception as e:
        return type(e).__name__, "", {}, int((time.time() - t) * 1000)
    if "gzip" in (hdr.get("Content-Encoding") or "").lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace"), hdr, int((time.time() - t) * 1000)


def short(x, n=160):
    s = json.dumps(x, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


print("==================== Sovereign Scents")
S = "https://www.sovereignscents.in"
code, body, hdr, ms = get(f"{S}/api/products")
print(f"/api/products -> {code} in {ms} ms, {len(body)} bytes, cache {hdr.get('Cache-Control')}, age {hdr.get('Age')}")
d = json.loads(body)
print("top-level keys:", list(d))
ps = d.get("products") or []
print("products:", len(ps), "| other top-level:", {k: short(v, 80) for k, v in d.items() if k != "products"})
keys = Counter(k for p in ps for k in p)
print("product keys:", keys.most_common())
if ps:
    p0 = ps[0]
    for k, v in p0.items():
        print(f"   {k}: {short(v, 220)}")
for k in keys:
    vals = Counter(json.dumps(p.get(k), ensure_ascii=False)[:40] for p in ps)
    if 1 < len(vals) <= 25:
        print(f"  values of {k}: {vals.most_common(12)}")
hit = [p for p in ps if "partial" in json.dumps(p, ensure_ascii=False).lower()]
print("products mentioning 'partial' anywhere:", len(hit))
for p in hit[:5]:
    print("   e.g.", short({k: v for k, v in p.items() if k not in ("description", "images", "archivedImages")}, 600))
code, html, hdr, ms = get(f"{S}/", accept="text/html")
paths = sorted(set(re.findall(r'href="(/[^"#?]*)', html)))
print("homepage links:", paths[:80])
for path in [p for p in paths if re.search(r"partial|decant|shop|collection|categor|product", p, re.I)][:8]:
    c2, h2, _, ms2 = get(S + path, accept="text/html")
    apis = sorted(set(re.findall(r'"(/api/[^"]+)"', h2)))
    print(f"  {path} -> {c2} in {ms2} ms; api refs {apis[:10]}; mentions partial {h2.lower().count('partial')}")
for q in ("?category=Partials", "?type=partial", "?search=partial", "?page=2", "?limit=1000"):
    c2, b2, _, ms2 = get(f"{S}/api/products{q}")
    try:
        n = len(json.loads(b2).get("products") or [])
    except Exception:
        n = "?"
    print(f"  /api/products{q} -> {c2} in {ms2} ms, {n} products")
codes = []
t0 = time.time()
for i in range(6):
    codes.append(get(f"{S}/api/products")[0])
    time.sleep(1)
print(f"  6 reads in {time.time()-t0:.0f} s: {codes}")

print("\n==================== Acordell")
A = "https://acordell.com"
code, body, hdr, ms = get(f"{A}/wp-json/wc/store/v1/products/categories?per_page=100")
cats = json.loads(body) if code == 200 else []
print(f"categories -> {code} in {ms} ms: {len(cats)}")
for c in cats:
    print(f"   {c.get('id')} {c.get('slug')!r} {c.get('name')!r} count {c.get('count')}")
code, body, hdr, ms = get(f"{A}/wp-json/wc/store/v1/products?per_page=100&page=1")
print(f"products page 1 -> {code} in {ms} ms; total {hdr.get('X-WP-Total') or hdr.get('x-wp-total')}, pages {hdr.get('X-WP-TotalPages') or hdr.get('x-wp-totalpages')}")
allp = json.loads(body) if code == 200 else []
pages = int(hdr.get('X-WP-TotalPages') or hdr.get('x-wp-totalpages') or 1)
for page in range(2, min(pages, 30) + 1):
    c2, b2, _, _ = get(f"{A}/wp-json/wc/store/v1/products?per_page=100&page={page}")
    if c2 != 200:
        print("  page", page, "->", c2)
        break
    allp += json.loads(b2)
    time.sleep(0.3)
print("all products read:", len(allp))
if allp:
    p0 = allp[0]
    for k, v in p0.items():
        print(f"   {k}: {short(v, 200)}")
print("types:", Counter(p.get("type") for p in allp), "| in stock:", Counter(p.get("is_in_stock") for p in allp),
      "| stock_availability:", Counter((p.get("stock_availability") or {}).get("class") for p in allp))
part = [p for p in allp if re.search(r"partial", p.get("name", "") + " " + " ".join(c.get("slug", "") for c in p.get("categories") or []), re.I)]
print("partials (name or category):", len(part), "in stock:", sum(1 for p in part if p.get("is_in_stock")))
for p in part[:8]:
    pr = p.get("prices") or {}
    print("   e.g.", p.get("name")[:60], "|", p.get("type"), "| in stock", p.get("is_in_stock"), "| price", pr.get("price"), "reg", pr.get("regular_price"),
          "sale", pr.get("sale_price"), "minor", pr.get("currency_minor_unit"), "|", [c.get("slug") for c in p.get("categories") or []], "|", p.get("permalink"))
var = [p for p in allp if p.get("type") == "variable"][:2]
for p in var:
    print("   variable e.g.", p.get("name")[:50], "| variations", short(p.get("variations"), 300), "| attributes", short(p.get("attributes"), 300))
c2, b2, h2, ms2 = get(f"{A}/wp-json/wc/store/v1/products?per_page=100&search=partial")
print(f"search=partial -> {c2} in {ms2} ms: {len(json.loads(b2)) if c2 == 200 else '-'} (total {h2.get('X-WP-Total') or h2.get('x-wp-total')})")
codes = []
t0 = time.time()
for i in range(6):
    codes.append(get(f"{A}/wp-json/wc/store/v1/products?per_page=100&page=1&_={int(time.time()*1000)}")[0])
    time.sleep(1)
print(f"  6 reads in {time.time()-t0:.0f} s: {codes}")
