#!/usr/bin/env python3
"""Probe #29: where does FirstCry's cart get "Cannot be delivered to 248001"?
Read only — nothing is added to any cart (a guest cart is just a cookie string).

A. Mobile + desktop cart / checkout / product pages: final URL, scripts, any
   API-looking strings.
B. Every script those pages load (FirstCry / fcglcdn hosts): cart and delivery
   endpoints, with the code around each call — saved in the report.
C. The delivery check's FULL answer for 248001 for the AAR Cuda (cart: not
   deliverable, 23 Oct 13:32) next to cars that are deliverable, field by field.
D. GetCartV1 again with every header/cookie a browser would send.
"""
import base64, gzip, json, re, time
from urllib.parse import urljoin
from curl_cffi import requests as http

T0 = time.time()
IMP = {"impersonate": "chrome124"}
UA_D = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_M = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
REPORT = {"pages": {}, "scripts": {}, "tat": {}, "cart": {}}
API_PAT = re.compile(r"""(https?:)?//[a-zA-Z0-9.-]*(firstcry|fcappservices|fcglcdn)[a-zA-Z0-9./_-]*|/[a-zA-Z0-9_/.-]*\.svc/[a-zA-Z0-9_/]*|/(api|apifc|capinet|svcs|shsercart)/[a-zA-Z0-9_/.-]+""")
KEYS = re.compile(r"GetCart|GenerateCart|MergeCart|undeliver|Undeliver|cannot be delivered|can\\?'t be delivered|"
                  r"IsDeliver|isDeliver|NonServ|nonserv|UnServ|unserv|DeliveryUnavailable|NotServiceable|"
                  r"notserviceable|ShipPin|shipPin|IsServicable|Serviceab", re.I)


def el():
    return f"+{time.time() - T0:4.0f}s"


def save(txt):
    return base64.b64encode(gzip.compress(txt.encode("utf-8", "replace"))).decode()


def get(url, ua, **kw):
    try:
        r = http.get(url, headers={"User-Agent": ua, "Accept-Language": "en-IN,en;q=0.9",
                                   "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
                     timeout=25, allow_redirects=True, **IMP, **kw)
        return r
    except Exception as e:
        print(f"   {url}: {type(e).__name__} {e}")
        return None


print("=" * 20, "A. pages", "=" * 20)
S_M = http.Session(**IMP)
pages = [("m_home", "https://m.firstcry.com/", UA_M), ("m_cart", "https://m.firstcry.com/cart", UA_M),
         ("w_cart_mob", "https://www.firstcry.com/cart", UA_M), ("checkout", "https://checkout.firstcry.com/", UA_D),
         ("checkout_cart", "https://checkout.firstcry.com/cart", UA_D),
         ("m_pdp", "https://m.firstcry.com/hot-wheels/x/24783699/product-detail", UA_M),
         ("w_pdp_mob", "https://www.firstcry.com/hot-wheels/x/24783699/product-detail", UA_M)]
scripts = {}
for key, url, ua in pages:
    r = get(url, ua)
    if r is None:
        continue
    t = r.text
    srcs = re.findall(r"""<script[^>]+src=["']([^"']+)["']""", t)
    apis = sorted(set(m.group(0) for m in API_PAT.finditer(t)))
    print(f"{el()} {key}: HTTP {r.status_code} → {r.url[:90]} | {len(t)} b | {len(srcs)} scripts")
    for a in apis[:40]:
        print("      api:", a[:120])
    for m in KEYS.finditer(t):
        a, b = max(0, m.start() - 160), min(len(t), m.end() + 220)
        print("      key:", t[a:b].replace("\n", " ")[:380])
        break
    REPORT["pages"][key] = {"status": r.status_code, "url": r.url, "html": save(t), "scripts": srcs}
    for s in srcs:
        full = urljoin(r.url, s)
        if any(h in full for h in ("firstcry", "fcglcdn", "fcappservices")) and full not in scripts:
            scripts[full] = ua

print("\n" + "=" * 20, f"B. {len(scripts)} scripts", "=" * 20)
for url, ua in list(scripts.items())[:40]:
    r = get(url, ua)
    if r is None or r.status_code != 200:
        print(f"   {url[:100]}: {getattr(r, 'status_code', '-')}")
        continue
    t = r.text
    hits = sorted(set(m.group(0).lower() for m in KEYS.finditer(t)))
    apis = sorted(set(m.group(0) for m in API_PAT.finditer(t)))
    print(f"{el()} {url[:110]} | {len(t)} b | keys {hits[:12]}")
    for a in apis:
        if re.search(r"cart|deliver|tat|servic|pin|checkout", a, re.I):
            print("      api:", a[:140])
    if hits:
        REPORT["scripts"][url] = save(t)

print("\n" + "=" * 20, "C. delivery check, full answer for 248001", "=" * 20)
S = http.Session(**IMP)
S.get("https://www.firstcry.com/hotwheels/5/0/113", headers={"User-Agent": UA_D}, timeout=20)
COOK = {c.name: c.value for c in getattr(S.cookies, "jar", [])}
CARS = {"24783699": "AAR Cuda (cart: NOT deliverable 13:32)", "24473712": "Salt Streaker (common)",
        "24525296": "Silverado Driftcation", "24783759": "DB5 Safari", "24472644": "Audi TT Safari"}
H = {"User-Agent": UA_D, "Accept": "application/json, text/javascript, */*; q=0.01",
     "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
     "Origin": "https://www.firstcry.com"}
for pid, nm in CARS.items():
    for pin in ("248001", "110001"):
        body = {"ProductIDs": pid, "Pincode": pin, "ComboId": 0, "CheckTAT": True, "CheckDropShipment": False,
                "CheckCOD": True, "subCatID": 94, "MRP": 179, "AddressType": "Home", "Discount": 0, "minQty": 1,
                "CatID": 5, "ftk": "", "groupproducts": pid}
        try:
            r = http.post("https://www.firstcry.com/tatapi/oam/checkdeliveryinfo", data=json.dumps(body),
                          headers={**H, "Referer": f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail"},
                          cookies=COOK, timeout=20, **IMP)
            res = (r.json() or {}).get("Result") or {}
        except Exception as e:
            res = {"err": str(e)}
        REPORT["tat"][f"{pid}_{pin}"] = res
        flat = {k: v for k, v in res.items() if not isinstance(v, (dict, list))}
        print(f"   {nm[:34]:34} {pin}: {json.dumps(flat)[:900]}")
        for k, v in res.items():
            if isinstance(v, (dict, list)):
                print(f"        {k}: {json.dumps(v)[:400]}")
        time.sleep(0.3)

print("\n" + "=" * 20, "D. GetCartV1 like a browser", "=" * 20)
for pid in ("24783699", "24473712"):
    pro = f"NO^{pid}^1^0"
    for host in ("https://csc.fcappservices.in/ShoppingCart/ShoppingCart.svc/json/GetCartV1",
                 "https://www.firstcry.com/shsercart/shoppingcart.svc/json/GetCartV1"):
        ck = {**COOK, "_$FC$_cookies_for_cart_v2_": pro, "globalPincode": "248001"}
        body = json.dumps({"pro": pro, "shipPin": "248001", "FC_AUTH": "", "AppVersion": "Desktop", "AssemblyMap": ""})
        try:
            r = http.post(host, data=body, headers={**H, "Referer": "https://www.firstcry.com/cart"}, cookies=ck,
                          timeout=20, **IMP)
            t = r.text
        except Exception as e:
            t = f"ERR {e}"
        REPORT["cart"][f"{pid}_{host.split('/')[2]}"] = t[:20000]
        print(f"   {pid} {host.split('/')[2]}: {t[:700]}")
json.dump(REPORT, open("probe_report.json", "w"))
print(f"\ndone in {time.time() - T0:.0f}s")
