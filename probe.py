#!/usr/bin/env python3
"""Probe #24: ask FirstCry's own cart (GetCartV1 — what the cart page calls for a
guest, cart = a cookie string, nothing is stored) whether the cars alerted today
can be delivered to 248001, next to what the product page and the delivery
check say. Several pincodes, twice, ~2 min apart."""
import json, re, time, random
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

T0 = time.time()
IMP = {"impersonate": "chrome124"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
S = http.Session(**IMP)
S.get("https://www.firstcry.com/cart", headers=H, timeout=20)
COOK = {c.name: c.value for c in getattr(S.cookies, "jar", S.cookies)}
print("cookies:", sorted(COOK)[:20])
CARS = {"24390957": "Tacoma TRD Pro (alerted 14:50)", "24390967": "Mercedes 300 SL (14:50)",
        "23973357": "Pantone Bronco (14:54)", "23345758": "Porsche 928S (yesterday)",
        "24473712": "Salt Streaker (control, 250+)", "24473713": "Buick Riviera"}
JH = {**H, "Accept": "application/json, text/javascript, */*; q=0.01", "Content-Type": "application/json; charset=utf-8",
      "X-Requested-With": "XMLHttpRequest", "Origin": "https://www.firstcry.com", "Referer": "https://www.firstcry.com/cart"}


def el():
    return f"+{time.time() - T0:4.0f}s"


def cart(pids, pin):
    pro = "*".join(f"NO^{p}^1^0" for p in pids)
    body = json.dumps({"pro": pro, "shipPin": pin, "FC_AUTH": "", "AppVersion": "Desktop", "AssemblyMap": ""})
    for url in ("https://www.firstcry.com/shsercart/shoppingcart.svc/json/GetCartV1",
                "https://csc.fcappservices.in/ShoppingCart/ShoppingCart.svc/json/GetCartV1"):
        try:
            r = http.post(url, data=body, headers=JH, cookies=COOK, timeout=20, **IMP)
        except Exception as e:
            print("  ", url, "ERR", e)
            continue
        print(f"  {el()} {url.split('/')[2]} → {r.status_code}, {len(r.text)} b")
        if r.status_code == 200 and r.text.strip().startswith("{"):
            return r.json()
        print("     ", r.text[:300])
    return None


def json_after(txt, pat):
    m = re.search(pat, txt)
    if not m:
        return None
    i = txt.find("{", m.end() - 1)
    depth, ins, esc = 0, False, False
    for j in range(i, min(len(txt), i + 3_000_000)):
        c = txt[j]
        if ins:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': ins = False
        elif c == '"': ins = True
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try: return json.loads(txt[i:j + 1])
                except Exception: return None
    return None


def page_cs(pid):
    r = http.get(f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail?fresh={random.randint(10**8, 10**9)}",
                 headers=H, cookies=COOK, timeout=20, **IMP)
    cur = json_after(r.text, r"CurrentProductDetailJSON\s*=\s*\{") or {}
    return (cur.get(pid) or {}).get("CS")


def tat(pid, pin="248001"):
    body = json.dumps({"ProductIDs": pid, "Pincode": pin, "ComboId": 0, "CheckTAT": True, "CheckDropShipment": False,
                       "CheckCOD": True, "subCatID": 94, "MRP": 179, "AddressType": "Home", "Discount": 0, "minQty": 1,
                       "CatID": 5, "ftk": "", "groupproducts": pid})
    try:
        r = http.post("https://www.firstcry.com/tatapi/oam/checkdeliveryinfo", data=body,
                      headers={**JH, "Referer": f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail"},
                      cookies=COOK, timeout=15, **IMP)
        res = (r.json() or {}).get("Result") or {}
        return {"grp": (res.get("groupserviceability") or {}).get(pid), "IsSv": res.get("IsServicable"),
                "TAT": res.get("ProductTAT"), "disp": res.get("DispatchHrs")}
    except Exception as e:
        return {"err": str(e)[:60]}


def dump_cart(res, label):
    print(f"\n==== GetCartV1 {label}: top-level keys {list(res)[:20]}")
    txt = json.dumps(res, ensure_ascii=False)
    print("   raw (first 3000):", txt[:3000])


for rnd in range(2):
    if rnd:
        time.sleep(max(0, 120 - (time.time() - T0)))
    print("\n" + "=" * 20, f"round {rnd + 1} {el()}", "=" * 20)
    for pin in ("248001", "110001", "560001"):
        res = cart(list(CARS), pin)
        if res is None:
            print("  no answer for", pin)
            continue
        if rnd == 0 and pin == "248001":
            dump_cart(res, pin)
        # find per-product entries wherever they are
        found = {}
        def walk(o, path=""):
            if isinstance(o, dict):
                pid = str(o.get("ProductID") or o.get("ProductId") or o.get("productid") or o.get("PID") or "")
                if pid in CARS:
                    found.setdefault(pid, o)
                for k, v in o.items():
                    walk(v, path + "/" + k)
            elif isinstance(o, list):
                for v in o:
                    walk(v, path)
        walk(res)
        print(f"\n  pincode {pin}: {len(found)} product entries")
        for pid, o in found.items():
            small = {k: v for k, v in o.items() if not isinstance(v, (dict, list)) and k.lower() not in ("productname", "imageurl", "image")}
            print(f"   {pid} {CARS[pid][:28]:28} {json.dumps(small, ensure_ascii=False)[:900]}")
    with ThreadPoolExecutor(6) as ex:
        cs = dict(zip(CARS, ex.map(page_cs, CARS)))
        tt = dict(zip(CARS, ex.map(tat, CARS)))
    print("\n  product page CS + delivery check (248001):")
    for pid in CARS:
        print(f"   {pid} {CARS[pid][:28]:28} CS={cs[pid]} {tt[pid]}")
print(f"done in {time.time() - T0:.0f}s")
