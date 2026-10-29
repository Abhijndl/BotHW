#!/usr/bin/env python3
"""Probe #55: Karz & Dolls — how the shop's own JavaScript reads a visitor's
cart (which URL, which fields), updates and removes items. Read-only: only
downloads the shop's public scripts."""
import re
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
KD = "https://www.karzanddolls.com"
r = http.get(KD + "/", headers=H, timeout=25, **IMP)
build = re.search(r'"buildId":"([^"]+)"', r.text).group(1)
srcs = re.findall(r'<script[^>]+src="([^"]+\.js)"', r.text)
mf = http.get(f"{KD}/_next/static/{build}/_buildManifest.js", headers=H, timeout=25, **IMP).text
srcs += ["/_next/" + s for s in re.findall(r'"(static/chunks/[^"]+\.js)"', mf)]
for s in dict.fromkeys(srcs):
    f = s.rsplit("/", 1)[-1]
    if not any(k in f for k in ("_app", "viewcart", "Review", "Address", "8262")):
        continue
    js = http.get(s if s.startswith("http") else KD + s, headers=H, timeout=25, **IMP).text
    seen = set()
    for m in re.finditer(r'"/cart[^"]*"|/cart/[A-Za-z_\-]+', js):
        key = m.group(0)
        i = m.start()
        c = re.sub(r"\s+", " ", js[max(0, i - 350): i + 450])
        k2 = (key, c[:60])
        if k2 in seen:
            continue
        seen.add(k2)
        print(f"\n### [{f}] {key}\n{c}")
