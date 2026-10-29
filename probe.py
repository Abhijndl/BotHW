#!/usr/bin/env python3
"""Probe #53: Karz & Dolls — every karzOffice/api path the shop's JavaScript
calls, with the method and whether it sends a login token; then a plain GET of
the public-looking read endpoints (search, product, category — no cart, no
login, nothing written) to see which return a stock field (pro_stock / qty)."""
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
srcs = list(dict.fromkeys(srcs))
calls = {}
for s in srcs:
    try:
        js = http.get(s if s.startswith("http") else KD + s, headers=H, timeout=25, **IMP).text
    except Exception:
        continue
    for m in re.finditer(r'karzOffice/api"\s*,\s*"([^"]+)"|karzOffice/api(/[A-Za-z0-9_\-/]+)', js):
        path = m.group(1) or m.group(2)
        ctx = js[max(0, m.start() - 120): m.end() + 260]
        meth = "POST" if re.search(r'method:"POST"', ctx) else ("DELETE" if 'method:"DELETE"' in ctx else ("PUT" if 'method:"PUT"' in ctx else "GET"))
        auth = "Bearer" in ctx or "Authorization" in ctx
        calls.setdefault(path, set()).add((meth, auth, s.rsplit("/", 1)[-1][:30]))
print(f"{len(calls)} API paths in the shop's scripts:")
for p, v in sorted(calls.items()):
    print(f"  {p:45} {sorted(v)}")
# plain GETs of read-only looking paths
stock_words = ("pro_stock", "qty", "stock", "quantity", "inventory")
tried = []
for p in sorted(calls):
    if any(w in p.lower() for w in ("cart", "order", "address", "login", "logout", "register", "pay", "coupon", "wish", "user", "profile", "otp", "password", "review", "checkout")):
        continue
    for url in (API + p, API + p.rstrip("/") + "?term=mclaren", API + p.rstrip("/") + "/mini-gt-lancia-stratos-hf-stradale-rosso-arancio"):
        try:
            rr = http.get(url, headers=H, timeout=20, **IMP)
            body = rr.text[:4000]
        except Exception as e:
            continue
        found = [w for w in stock_words if f'"{w}' in body]
        tried.append(url)
        print(f"  GET {url[len(KD):][:80]:82} HTTP {rr.status_code} len={len(rr.text)} stock fields: {found} {body[:160]!r}")
for p in ("/products", "/product/mini-gt-lancia-stratos-hf-stradale-rosso-arancio", "/productdetails/mini-gt-lancia-stratos-hf-stradale-rosso-arancio",
          "/search?term=mclaren", "/search/mclaren", "/getproducts", "/category/mini-gt", "/home"):
    try:
        rr = http.get(API + p, headers=H, timeout=20, **IMP)
        print(f"  GET (guess) {p:70} HTTP {rr.status_code} len={len(rr.text)} {[w for w in stock_words if chr(34) + w in rr.text[:20000]]} {rr.text[:140]!r}")
    except Exception as e:
        print("  ", p, type(e).__name__)
