#!/usr/bin/env python3
"""Blinkit probe #2: which Blinkit addresses does GitHub get blocked on, by whom
(response headers), and does any route give product data. Read-only."""
import json, re, time
from curl_cffi import requests

PRID = "1454828"
LAT, LON = "30.3165", "78.0322"
R = []

def hit(label, url, imp="chrome", headers=None, sess=None):
    t = time.time()
    try:
        g = (sess or requests).get(url, headers=headers or {}, impersonate=imp, timeout=20, allow_redirects=True)
        b = g.text
        row = {"label": label, "url": url, "status": g.status_code, "bytes": len(b), "secs": round(time.time() - t, 2),
               "server": g.headers.get("server"), "cf_ray": g.headers.get("cf-ray"), "akamai": g.headers.get("x-akamai-transformed") or g.headers.get("akamai-grn"),
               "via": g.headers.get("via"), "set_cookie_names": re.findall(r"(?:^|,\s*)([A-Za-z0-9_\-]+)=", g.headers.get("set-cookie", ""))[:8],
               "title": (re.search(r"<title>(.*?)</title>", b, re.S) or [None, None])[1],
               "blocked": bool(re.search(r"you have been blocked|access denied", b, re.I)),
               "words": {w: bool(re.search(w, b, re.I)) for w in ["coming soon", "notify", "out of stock", "add to cart", "Supra", PRID, "inventory", "unavailable"]},
               "head": re.sub(r"\s+", " ", b[:300])}
    except Exception as e:
        row = {"label": label, "url": url, "error": repr(e)[:200]}
    R.append(row); print(json.dumps(row, ensure_ascii=False)[:900], flush=True)
    return row

api_h = {"Accept": "application/json", "app_client": "consumer_web", "platform": "desktop_web", "lat": LAT, "lon": LON,
         "Origin": "https://blinkit.com", "Referer": f"https://blinkit.com/prn/x/prid/{PRID}"}
ip = requests.get("https://ipinfo.io/json", timeout=10).json()
print("runner ip:", {k: ip.get(k) for k in ("ip", "city", "country", "org")})
hit("home", "https://blinkit.com/")
hit("robots", "https://blinkit.com/robots.txt")
hit("page", f"https://blinkit.com/prn/x/prid/{PRID}")
hit("page_mobile_ua", f"https://blinkit.com/prn/x/prid/{PRID}", imp="safari_ios")
hit("api_v1_products", f"https://blinkit.com/v1/products/{PRID}", headers=api_h)
hit("api_layout_pdp", f"https://blinkit.com/v1/layout/product/{PRID}", headers=api_h)
hit("api_host_v2", f"https://api2.grofers.com/v1/products/{PRID}", headers=api_h)
hit("cdn_image_host", "https://cdn.grofers.com/")
hit("sitemap", "https://blinkit.com/sitemap.xml")
json.dump({"ip": {k: ip.get(k) for k in ("ip", "city", "country", "org")}, "rows": R}, open("probe_blinkit_report.json", "w"), indent=1, ensure_ascii=False)
