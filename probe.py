#!/usr/bin/env python3
"""Probe #71: Sovereign Scents' product link format; Acordell searches for partial/decant."""
import gzip, json, re, urllib.error, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            code, data, hdr = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, ""
    if "gzip" in (hdr.get("Content-Encoding") or "").lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace")


S = "https://www.sovereignscents.in"
code, html = get(f"{S}/shop", "text/html")
for c in sorted(set(re.findall(r'(/_next/static/chunks/[^"\']+\.js)', html))):
    c2, js = get(S + c, "*/*")
    for m in re.finditer(r"/product/", js):
        print("link code:", js[max(0, m.start() - 120): m.start() + 120].replace("\n", " "))
p = json.loads(get(f"{S}/api/products?limit=3&sort=newest")[1])["products"][0]
print("newest:", p["_id"], p["name"], p.get("brand"))
for path in (f"/product/{p['_id']}", f"/api/products/{p['_id']}"):
    c2, h2 = get(S + path, "text/html" if not path.startswith("/api") else "application/json")
    print(f"{path} -> {c2}; shows the name: {p['name'] in h2}; {len(h2)} bytes; {h2[:200]!r}" if path.startswith("/api") else f"{path} -> {c2}; shows the name: {p['name'] in h2}; {len(h2)} bytes")

A = "https://acordell.com"
for q in ("partial", "decant", "sample", "partials", "decants"):
    c2, b = get(f"{A}/wp-json/wc/store/v1/products?per_page=100&search={q}")
    items = json.loads(b) if c2 == 200 else []
    print(f"Acordell search={q} -> {c2}: {len(items)}", [(i['name'][:40], i.get('is_in_stock')) for i in items[:5]])
