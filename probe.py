#!/usr/bin/env python3
"""Probe #68: are there partials under another name? Sovereign Scents: every size label,
types, the shop page's own code; Acordell: every 'Product Type' term, sale/tester stock."""
import gzip, json, re, time, urllib.error, urllib.request
from collections import Counter

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def get(url, timeout=25, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                               "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, data, hdr = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, "", {}
    except Exception as e:
        return type(e).__name__, "", {}
    if "gzip" in (hdr.get("Content-Encoding") or "").lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace"), hdr


print("==================== Sovereign Scents")
S = "https://www.sovereignscents.in"
ps = []
for page in (1, 2, 3):
    code, body, _ = get(f"{S}/api/products?limit=1000&page={page}")
    d = json.loads(body)
    ps += d["products"]
    print("page", page, code, len(d["products"]), d.get("pagination"))
    if not d.get("pagination", {}).get("hasMore"):
        break
print("products:", len(ps), "unique ids:", len({p["_id"] for p in ps}))
print("in stock:", Counter(p.get("inStock") for p in ps), "| disabled:", Counter(p.get("manuallyDisabled") for p in ps))
print("type:", Counter(p.get("type") for p in ps).most_common())
print("category:", Counter(p.get("category") for p in ps).most_common())
sizes = Counter(s.get("size") for p in ps for s in p.get("sizes") or [])
print("size labels:", sizes.most_common(40))
odd = [p for p in ps if any(not re.fullmatch(r"\d+(\.\d+)?\s?ml", str(s.get("size") or ""), re.I) for s in p.get("sizes") or [])]
print("products with an unusual size label:", len(odd))
for p in odd[:10]:
    print("   ", p["name"][:50], "|", p.get("brand"), "|", [(s.get("size"), s.get("price")) for s in p["sizes"]], "| totalMl", p.get("totalMl"), "| in stock", p.get("inStock"))
big = [p for p in ps if any(re.fullmatch(r"(\d+)\s?ml", str(s.get("size") or ""), re.I) and int(re.match(r"\d+", s["size"]).group()) > 20 for s in p.get("sizes") or [])]
print("products offering a size above 20 ml:", len(big))
for p in big[:8]:
    print("   ", p["name"][:50], "|", [(s.get("size"), s.get("price")) for s in p["sizes"]], "| totalMl", p.get("totalMl"), "| in stock", p.get("inStock"))
print("totalMl:", Counter(p.get("totalMl") for p in ps).most_common(15))
print("newest:", sorted((p.get("createdAt", "")[:16], p["name"][:40], p.get("inStock")) for p in ps)[-8:])
other = Counter(k for p in ps for k in p) 
print("all keys:", other.most_common())
code, html, _ = get(f"{S}/shop", accept="text/html")
chunks = sorted(set(re.findall(r'(/_next/static/chunks/[^"\']+\.js)', html)))
print("shop page chunks:", len(chunks))
found = Counter()
apis = set()
for c in chunks:
    c2, js, _ = get(S + c, accept="*/*")
    apis |= set(re.findall(r'["\'`](/api/[a-zA-Z0-9_/\-]+)', js))
    for w in re.findall(r'(?i)[^"\'`]{0,40}partial[^"\'`]{0,40}', js):
        found[w.strip()[:80]] += 1
print("api endpoints in the site's code:", sorted(apis))
print("'partial' in the site's code:", found.most_common(15))
for path in sorted(apis):
    if "{" in path or path in ("/api/products",):
        continue
    c2, b2, _ = get(S + path)
    print(f"   {path} -> {c2}: {b2[:160]!r}")

print("\n==================== Acordell")
A = "https://acordell.com"
code, body, _ = get(f"{A}/wp-json/wc/store/v1/products/attributes")
attrs = json.loads(body) if code == 200 else []
for a in attrs:
    c2, b2, _ = get(f"{A}/wp-json/wc/store/v1/products/attributes/{a['id']}/terms?per_page=100")
    terms = json.loads(b2) if c2 == 200 else []
    print(f"attribute {a['id']} {a.get('name')!r}: {[(t.get('name'), t.get('count')) for t in terms]}")
allp = []
for page in range(1, 6):
    c2, b2, h2 = get(f"{A}/wp-json/wc/store/v1/products?per_page=100&page={page}")
    if c2 != 200:
        break
    got = json.loads(b2)
    allp += got
    if len(got) < 100:
        break
print("products:", len(allp))
vt = Counter(at.get("value") for p in allp for v in p.get("variations") or [] for at in v.get("attributes") or [])
print("variation types:", vt.most_common(30))
sale = [p for p in allp if p.get("on_sale")]
print("on sale:", len(sale), "in stock", sum(1 for p in sale if p.get("is_in_stock")))
tester = [p for p in allp if any(c.get("slug") == "tester" for c in p.get("categories") or [])]
print("tester category:", len(tester), "in stock", sum(1 for p in tester if p.get("is_in_stock")))
print("stock texts:", Counter((p.get("stock_availability") or {}).get("text") for p in allp).most_common(12))
for p in sale[:5]:
    pr = p["prices"]
    print("   sale e.g.", p["name"][:55], pr.get("price"), pr.get("regular_price"), (pr.get("price_range") or {}), p.get("is_in_stock"))
c2, b2, h2 = get(f"{A}/wp-json/wc/store/v1/products?per_page=5&type=variation")
print("variation listing ->", c2, (b2[:300] if c2 == 200 else ""))
vid = next((v["id"] for p in allp for v in p.get("variations") or []), None)
if vid:
    c2, b2, _ = get(f"{A}/wp-json/wc/store/v1/products/{vid}")
    try:
        v = json.loads(b2)
        print("one variation ->", c2, {k: v.get(k) for k in ("id", "name", "type", "is_in_stock", "permalink")}, (v.get("prices") or {}).get("price"))
    except Exception:
        print("one variation ->", c2, b2[:200])
