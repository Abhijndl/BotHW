#!/usr/bin/env python3
"""Probe #25: get FirstCry's guest-cart call (GetCartV1) to read a product list —
a few request variants, full answers printed. Read only."""
import json, time
from urllib.parse import quote
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"), "Accept-Language": "en-IN,en;q=0.9"}
JH = {**H, "Accept": "application/json, text/javascript, */*; q=0.01", "Content-Type": "application/json; charset=utf-8",
      "Origin": "https://www.firstcry.com", "Referer": "https://www.firstcry.com/cart"}
URL = "https://csc.fcappservices.in/ShoppingCart/ShoppingCart.svc/json/"
S = http.Session(**IMP)
S.get("https://www.firstcry.com/", headers=H, timeout=20)
S.get("https://www.firstcry.com/hot-wheels/x/24473712/product-detail", headers=H, timeout=20)
print("cookies:", [c.name for c in getattr(S.cookies, "jar", [])])


def call(method, body, label):
    try:
        r = S.post(URL + method, data=json.dumps(body) if isinstance(body, dict) else body, headers=JH, timeout=20)
    except Exception as e:
        print(f"--- {label}: ERR {e}")
        return None
    t = r.text
    try:
        d = json.loads(t)
        if isinstance(d, str):
            d = json.loads(d)
    except Exception:
        d = None
    print(f"\n--- {label}: HTTP {r.status_code}, {len(t)} b")
    print(t[:2500])
    return d


P = "NO^24473712^1^0"
call("GetCartProductCount", {"ProCookie": P}, "count, plain")
call("GetCartProductCount", {"ProCookie": quote(P)}, "count, url-encoded")
for label, pro in (("plain", P), ("url-encoded", quote(P)), ("trailing *", P + "*"),
                   ("two cars", P + "*NO^24390967^1^0"), ("escaped ^", P.replace("^", "%5E"))):
    call("GetCartV1", {"pro": pro, "shipPin": "248001", "FC_AUTH": "", "AppVersion": "Desktop", "AssemblyMap": ""},
         f"GetCartV1 {label}")
    time.sleep(0.5)
call("GetCartV1", {"pro": P, "shipPin": "248001", "FC_AUTH": "", "AppVersion": "msite", "AssemblyMap": ""}, "GetCartV1 msite")
call("GetCart", {"pro": P, "shipPin": "248001", "FC_AUTH": "", "AppVersion": "Desktop", "AssemblyMap": ""}, "GetCart (v0)")
