#!/usr/bin/env python3
"""Probe #52: Karz & Dolls — which API calls does the shop's own JavaScript make
(add to cart, stock check, product details)? Lists endpoint paths and the code
around them, to find where a real unit count could come from. Read-only: it
only downloads the shop's public JavaScript files."""
import re, json
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9"}
KD = "https://www.karzanddolls.com"
pages = ["/", "/details/mini-gt-lancia-stratos-hf-stradale-rosso-arancio?pid=4lgO9nVLoQ", "/mini-gt/mini-gt"]
srcs = []
for p in pages:
    r = http.get(KD + p, headers=H, timeout=25, **IMP)
    for s in re.findall(r'<script[^>]+src="([^"]+\.js)"', r.text):
        if s not in srcs:
            srcs.append(s)
    m = re.search(r'"buildId":"([^"]+)"', r.text)
    if m:
        build = m.group(1)
print(len(srcs), "scripts; buildId", build)
# the build manifest lists every page's chunks
r = http.get(f"{KD}/_next/static/{build}/_buildManifest.js", headers=H, timeout=25, **IMP)
for s in re.findall(r'"(static/chunks/[^"]+\.js)"', r.text):
    s = "/_next/" + s
    if s not in srcs:
        srcs.append(s)
print(len(srcs), "scripts incl. the build manifest's")
hits = {}
for s in srcs:
    url = s if s.startswith("http") else KD + s
    try:
        js = http.get(url, headers=H, timeout=25, **IMP).text
    except Exception:
        continue
    for m in re.finditer(r'karzOffice/api[^"\'`\s]*|/api/[A-Za-z0-9_\-/]{3,60}|["\'`]([A-Za-z0-9_\-]*(?:cart|Cart|stock|Stock|qty|Qty|quantity|inventory)[A-Za-z0-9_\-]*)["\'`]', js):
        key = m.group(0)[:90]
        if key not in hits:
            i = m.start()
            hits[key] = (s.rsplit("/", 1)[-1], re.sub(r"\s+", " ", js[max(0, i - 160):i + 200]))
print(len(hits), "distinct hits")
for k, (f, ctx) in sorted(hits.items()):
    if any(w in k.lower() for w in ("api", "cart", "stock", "qty", "quant", "invent")):
        print(f"\n### {k}   [{f}]\n    {ctx[:360]}")
