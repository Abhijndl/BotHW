#!/usr/bin/env python3
"""Probe #23: save FirstCry's cart + product-page scripts (to read how a guest
cart cookie is built and what GetCartV1 returns)."""
import base64, gzip, json
from curl_cffi import requests as http
H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"), "Accept-Language": "en-IN,en;q=0.9"}
out = {}
for k, u in (("cart.js", "https://cdn.fcglcdn.com/brainbees/php/js/cart-deployment-v2.16.min.js"),
             ("pdp.js", "https://cdn.fcglcdn.com/brainbees/php/js/pdprevamp.1.55.min.js"),
             ("common.js", "https://cdn.fcglcdn.com/brainbees/php/js/master-common.v2.24.min.js?20261021"),
             ("cart.html", "https://www.firstcry.com/cart")):
    r = http.get(u, headers=H, timeout=30, impersonate="chrome124")
    print(r.status_code, len(r.text), u)
    out[k] = base64.b64encode(gzip.compress(r.text.encode())).decode()
json.dump(out, open("probe_report.json", "w"))
