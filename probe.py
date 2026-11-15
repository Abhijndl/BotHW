#!/usr/bin/env python3
"""Probe #70: Sovereign Scents' partials list (partials=only) and product links; Acordell menus."""
import gzip, json, re, time, urllib.error, urllib.request
from collections import Counter

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            code, data, hdr = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, "", int((time.time() - t) * 1000)
    if "gzip" in (hdr.get("Content-Encoding") or "").lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace"), int((time.time() - t) * 1000)


S = "https://www.sovereignscents.in"
for q in ("partials=only", "partials=exclude", ""):
    code, b, ms = get(f"{S}/api/products?limit=1000&{q}")
    d = json.loads(b)
    print(f"/api/products?{q} -> {code} in {ms} ms: {len(d['products'])} products, {d.get('pagination')}")
code, b, ms = get(f"{S}/api/products?limit=1000&partials=only&sort=newest")
ps = json.loads(b)["products"]
print("partials:", len(ps), "| in stock:", Counter(p.get("inStock") for p in ps), "| disabled:", Counter(p.get("manuallyDisabled") for p in ps))
print("keys:", Counter(k for p in ps for k in p).most_common())
print("size labels:", Counter(s.get("size") for p in ps for s in p.get("sizes") or []).most_common(20))
print("types:", Counter(p.get("type") for p in ps), "| categories:", Counter(p.get("category") for p in ps))
for p in ps[:3]:
    print("  full e.g.:", json.dumps({k: v for k, v in p.items() if k not in ("description",)}, ensure_ascii=False)[:900])
for p in ps[:15]:
    print("  ", p.get("createdAt", "")[:16], "|", p.get("inStock"), "|", p["name"][:45], "|", p.get("brand"), "|",
          [(s.get("size"), s.get("price")) for s in p.get("sizes") or []], "| totalMl", p.get("totalMl"), "| upd", p.get("updatedAt", "")[:16])
ex = json.loads(get(f"{S}/api/products?limit=1000&partials=exclude")[1])["products"]
print("partial ids also in the normal list:", len({p['_id'] for p in ps} & {p['_id'] for p in ex}))
code, html, _ = get(f"{S}/shop?collection=partials", "text/html")
links = set()
for c in sorted(set(re.findall(r'(/_next/static/chunks/[^"\']+\.js)', html))):
    c2, js, _ = get(S + c, "*/*")
    links |= set(re.findall(r'href:`(/[a-z\-]+/)\$\{[^}]+\}`', js)) | set(re.findall(r'`(/product[s]?/)\$\{([^}]+)\}`', js))
    for m in re.finditer(r'"/product', js):
        print("   link code:", js[max(0, m.start() - 80): m.start() + 80].replace("\n", " "))
        break
print("product link patterns:", links)
for path in ("/product/" + ps[0]["_id"], "/products/" + ps[0]["_id"]) if ps else ():
    c2, h2, ms2 = get(S + path, "text/html")
    print(f"  {path} -> {c2} in {ms2} ms, name shown: {ps[0]['name'] in h2}")
codes = [get(f"{S}/api/products?limit=1000&partials=only")[0] for _ in range(5)]
print("5 quick reads:", codes)

A = "https://acordell.com"
for path in ("/", "/shop/"):
    c2, h2, ms2 = get(A + path, "text/html")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h2))
    hits = [text[max(0, m.start() - 100): m.end() + 100] for m in re.finditer(r"(?i)partial|decant", text)]
    print(f"Acordell {path} -> {c2} in {ms2} ms; mentions: {hits[:4]}")
    menu = sorted(set(re.findall(r'href="https://acordell\.com(/[^"#?]*)"', h2)))
    print("  links:", [m for m in menu if not m.startswith(("/wp-", "/product/"))][:40])
