#!/usr/bin/env python3
"""Probe #22: how does FirstCry's CART decide "Cannot be delivered to 248001"
when the product page and its delivery check say the car can ship? Read the
cart's and the product page's scripts (read only — nothing is added to any
cart) and print the code around their delivery / pincode / cart calls."""
import re, time
from curl_cffi import requests as http

IMP = {"impersonate": "chrome124"}
H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
     "Accept-Language": "en-IN,en;q=0.9"}
T0 = time.time()


def get(url):
    try:
        r = http.get(url, headers=H, timeout=25, **IMP)
        print(f"  {r.status_code} {len(r.text):7d} b {url}")
        return r.text if r.status_code == 200 else ""
    except Exception as e:
        print("  ERR", url, e)
        return ""


def scripts(page):
    out = []
    for j in re.findall(r"<script[^>]+src=[\"']([^\"']+)", page):
        j = "https:" + j if j.startswith("//") else ("https://www.firstcry.com" + j if j.startswith("/") else j)
        out.append(j)
    return out


KEYS = ["GetCartV1", "ShoppingCart.svc", "shoppingcart.svc", "checkdeliveryinfo", "tatpdp", "Serviceab",
        "serviceab", "Servicab", "servicab", "NonServ", "nonserv", "undeliver", "Undeliver", "deliverable",
        "Cannot be delivered", "cannot be delivered", "pincode", "Pincode", "AddToCart", "addtocart",
        "AddCart", "ValidateCart", "validatecart", "CheckOut", "IsDeliverable", "isDeliverable", "TATDetails"]


def show(name, txt, per=4, width=420):
    print(f"\n######## {name} ({len(txt)} bytes)")
    for k in KEYS:
        hits = [m.start() for m in re.finditer(re.escape(k), txt)]
        if not hits:
            continue
        print(f"\n--- '{k}': {len(hits)} hit(s)")
        last = -10**9
        n = 0
        for h in hits:
            if h - last < width:
                continue
            last = h
            n += 1
            print("   …" + txt[max(0, h - width // 2): h + width // 2].replace("\n", " ") + "…")
            if n >= per:
                break


cart = get("https://www.firstcry.com/cart")
show("cart page", cart, per=6)
for j in scripts(cart):
    if re.search(r"cart|common|checkout|master", j, re.I):
        show(j, get(j))
pdp = get("https://www.firstcry.com/hot-wheels/x/24390957/product-detail")
for j in scripts(pdp):
    if re.search(r"pdp|master-common", j, re.I):
        show(j, get(j), per=3)
for u in ("https://tatpdp.fcappservices.in/", "https://csc.fcappservices.in/ShoppingCart/ShoppingCart.svc/json/GetCartV1"):
    t = get(u)
    print("   ", t[:300].replace("\n", " "))
print(f"done in {time.time() - T0:.0f}s")
