#!/usr/bin/env python3
"""Probe #54: Karz & Dolls — how the shop calls /similar-products/ and
/cartrecommended_products (both GET, no login), then those calls for a few
in-stock cars: do they carry pro_stock (the field the shop's own wishlist uses
for OUT OF STOCK)? And how does the shop's code use qty / pro_stock / add_limit
around Add to Cart? Read-only: GETs only, nothing added to any cart."""
import re, json
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "application/json, text/plain, */*"}
KD = "https://www.karzanddolls.com"
API = KD + "/karzOffice/api"
r = http.get(KD + "/", headers=H, timeout=25, **IMP)
build = re.search(r'"buildId":"([^"]+)"', r.text).group(1)
srcs = re.findall(r'<script[^>]+src="([^"]+\.js)"', r.text)
mf = http.get(f"{KD}/_next/static/{build}/_buildManifest.js", headers=H, timeout=25, **IMP).text
srcs += ["/_next/" + s for s in re.findall(r'"(static/chunks/[^"]+\.js)"', mf)]
JS = {}
for s in dict.fromkeys(srcs):
    try:
        JS[s.rsplit("/", 1)[-1]] = http.get(s if s.startswith("http") else KD + s, headers=H, timeout=25, **IMP).text
    except Exception:
        pass
def ctx(word, n=3, before=300, after=500):
    out = []
    for f, js in JS.items():
        for m in re.finditer(re.escape(word), js):
            out.append((f, re.sub(r"\s+", " ", js[max(0, m.start() - before): m.end() + after])))
            if len(out) >= n:
                return out
    return out
for w in ("similar-products/", "cartrecommended_products", "pro_stock", "add_limit", "product_attr", ".qty", "visitor/add"):
    print(f"\n===== {w}")
    for f, c in ctx(w, n=4):
        print(f"--- [{f}] {c[:800]}")
# the details page's own data for one in-stock car, to get its numeric id
page = http.get(KD + "/details/mini-gt-lancia-stratos-hf-stradale-rosso-arancio?pid=4lgO9nVLoQ", headers=H, timeout=25, **IMP).text
d = json.loads(re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S).group(1))["props"]["pageProps"]["productdetails"]
print("\nproduct:", d.get("id"), d.get("pid"), d.get("slug"))
for p in (f"/similar-products/{d['id']}", f"/similar-products/{d['pid']}", f"/similar-products/{d['slug']}?pid={d['pid']}",
          "/cartrecommended_products", f"/cartrecommended_products?product_id={d['id']}"):
    try:
        rr = http.get(API + p, headers=H, timeout=20, **IMP)
        t = rr.text
        print(f"\nGET {p} → HTTP {rr.status_code} len={len(t)} pro_stock: {t.count('pro_stock')} qty: {t.count(chr(34)+'qty')}")
        print("   ", t[:700])
    except Exception as e:
        print(p, type(e).__name__)
