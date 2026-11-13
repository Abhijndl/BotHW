#!/usr/bin/env python3
"""Probe #62: Whiff Culture (Shopify) partials from GitHub's runners: reachability,
the JSON endpoints, caching/freshness, rate behaviour. Read-only."""
import json, time, re
from curl_cffi import requests as cr
import urllib.request

BASE = "https://www.whiffculture.com"
COL = "partial-sale"
R = {"rows": []}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
HK = ("server", "cf-cache-status", "age", "cache-control", "x-cache", "x-shopify-stage", "x-shopid", "x-request-id",
      "x-shardid", "content-type", "date", "last-modified", "etag", "vary", "x-storefront-renderer-rendered",
      "server-timing", "retry-after", "x-ratelimit-remaining", "cf-ray", "set-cookie")


def hit(label, url, how="cffi", headers=None):
    t = time.time()
    try:
        if how == "cffi":
            r = cr.get(url, headers=headers or {}, impersonate="chrome", timeout=20)
            code, body, hd = r.status_code, r.text, {k.lower(): v for k, v in r.headers.items()}
        else:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    code, body, hd = r.status, r.read().decode("utf-8", "replace"), {k.lower(): v for k, v in r.headers.items()}
            except urllib.error.HTTPError as e:
                code, body, hd = e.code, e.read().decode("utf-8", "replace"), {k.lower(): v for k, v in e.headers.items()}
        row = {"label": label, "url": url, "how": how, "status": code, "bytes": len(body),
               "ms": int((time.time() - t) * 1000), "headers": {k: (hd.get(k) or "")[:160] for k in HK if hd.get(k)}}
    except Exception as e:
        row, body = {"label": label, "url": url, "how": how, "error": repr(e)[:200], "ms": int((time.time() - t) * 1000)}, ""
    R["rows"].append(row)
    print(json.dumps(row)[:700], flush=True)
    return row, body


ip = cr.get("https://ipinfo.io/json", timeout=10).json()
R["ip"] = {k: ip.get(k) for k in ("ip", "city", "country", "org")}
print("runner:", R["ip"])

row, body = hit("products.json", f"{BASE}/collections/{COL}/products.json?limit=250")
prods = []
if row.get("status") == 200:
    try:
        prods = json.loads(body)["products"]
    except Exception as e:
        print("not JSON", e, body[:300])
print("page1 products:", len(prods))
allp = list(prods)
for pg in range(2, 5):
    row, body = hit(f"products.json page {pg}", f"{BASE}/collections/{COL}/products.json?limit=250&page={pg}")
    try:
        more = json.loads(body)["products"]
    except Exception:
        more = []
    print(f"page {pg}: {len(more)}")
    if not more:
        break
    allp += more
R["n_products"] = len(allp)
avail = [p for p in allp if any(v.get("available") for v in p.get("variants", []))]
R["n_available"] = len(avail)
print(f"\nTOTAL {len(allp)} products, {len(avail)} available")
R["sample"] = []
for p in allp[:3] + avail[:4]:
    s = {k: p.get(k) for k in ("id", "title", "handle", "product_type", "vendor", "published_at", "created_at", "updated_at", "tags")}
    s["variants"] = [{k: v.get(k) for k in ("id", "title", "price", "compare_at_price", "available", "sku", "option1", "option2", "updated_at", "created_at")} for v in p.get("variants", [])]
    s["n_images"] = len(p.get("images") or [])
    s["image0"] = (p.get("images") or [{}])[0].get("src")
    s["body_text"] = re.sub(r"<[^>]+>", " ", p.get("body_html") or "")[:300]
    s["keys"] = sorted(p.keys())
    R["sample"].append(s)
    print(json.dumps(s, ensure_ascii=False)[:1500])
print("\norder of first 20 (published_at, available, title):")
for p in allp[:20]:
    print(" ", p.get("published_at"), p.get("updated_at"), any(v.get("available") for v in p["variants"]), p["title"][:70])
print("\nnewest by published_at:")
for p in sorted(allp, key=lambda p: p.get("published_at") or "", reverse=True)[:10]:
    print(" ", p.get("published_at"), any(v.get("available") for v in p["variants"]), p["title"][:70])
print("\nnewest by created_at:")
for p in sorted(allp, key=lambda p: p.get("created_at") or "", reverse=True)[:10]:
    print(" ", p.get("created_at"), p.get("published_at"), any(v.get("available") for v in p["variants"]), p["title"][:70])
print("\nmost recently updated:")
for p in sorted(allp, key=lambda p: p.get("updated_at") or "", reverse=True)[:12]:
    print(" ", p.get("updated_at"), any(v.get("available") for v in p["variants"]), [v.get("title") for v in p["variants"]][:3], p["title"][:60])
print("variant counts:", sorted({len(p["variants"]) for p in allp}))
print("titles not ending in Partial:", [p["title"] for p in allp if not p["title"].strip().lower().endswith("partial")][:15])

print("\n== other endpoints")
hit("products.json urllib", f"{BASE}/collections/{COL}/products.json?limit=250", how="urllib")
hit("collection html", f"{BASE}/collections/{COL}")
hit("collection atom", f"{BASE}/collections/{COL}.atom")
hit("sorted json", f"{BASE}/collections/{COL}/products.json?limit=250&sort_by=created-descending")
if allp:
    h = (avail or allp)[0]["handle"]
    row, body = hit("product .js", f"{BASE}/products/{h}.js")
    try:
        j = json.loads(body)
        print("  .js keys:", sorted(j.keys()))
        print("  .js variants:", [{k: v.get(k) for k in ("id", "title", "available", "inventory_quantity", "inventory_management", "inventory_policy", "price")} for v in j.get("variants", [])])
    except Exception as e:
        print("  .js not JSON", e)
    row, body = hit("product .json", f"{BASE}/products/{h}.json")
    row, body = hit("product page", f"{BASE}/products/{h}")
    m = re.findall(r'"inventory_quantity"\s*:\s*-?\d+|inventoryQuantity\W+-?\d+|"inventory"\s*:\s*-?\d+', body)
    print("  inventory hints on page:", m[:5])

print("\n== freshness / rate: 12 calls, 5 s apart, alternating plain and cache-busted")
seen_sig = []
for i in range(12):
    url = f"{BASE}/collections/{COL}/products.json?limit=250" + (f"&_={int(time.time()*1000)}" if i % 2 else "")
    row, body = hit(f"poll {i} {'bust' if i % 2 else 'plain'}", url)
    try:
        ps = json.loads(body)["products"]
        sig = (len(ps), max(p.get("updated_at") or "" for p in ps))
    except Exception:
        sig = None
    seen_sig.append(sig)
    time.sleep(5)
print("signatures:", seen_sig)
print("\n== burst: 8 calls back to back")
for i in range(8):
    hit(f"burst {i}", f"{BASE}/collections/{COL}/products.json?limit=250&_={time.time()}")
json.dump(R, open("probe_report.json", "w"), indent=1, ensure_ascii=False)
