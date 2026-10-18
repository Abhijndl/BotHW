#!/usr/bin/env python3
"""Probe #11: FirstCry's own delivery check — the live "can 248001 get it?" answer.

The product page script (pdprevamp.js) posts to
    https://www.firstcry.com/tatapi/oam/checkdeliveryinfo
with the car, its colour siblings ("groupproducts") and the visitor's pincode,
and if Result.groupserviceability[car] === 0 it silently switches the page to
the first sibling that is > 0. That is exactly what the user saw (Road Runner
URL -> Datsun 620). So this call decides what you can actually order.
Questions: response shape, speed, caching, does it agree with page CS / list,
pincode 248001 vs 0 vs others, one call per group?
"""
import json, re, time, random
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

T0 = time.time()
IMP = {"impersonate": "chrome124"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
FC_API = "https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging"
KEYS = ["PageNo","PageSize","SortExpression","OnSale","SearchString","SubCatId","BrandId","Price","Age","Color","OptionalFilter","OutOfStock","Type1","Type2","Type3","Type4","Type5","Type6","Type7","Type8","Type9","Type10","Type11","Type12","Type13","Type14","Type15","combo","discount","searchwithincat","ProductidQstr","searchrank","pmonths","cgen","PriceQstr","DiscountQstr","sorting","MasterBrand","Rating","Offer","skills","material","curatedcollections","measurement","gender","exclude","premium","pcode","isclub","deliverytype","authors","booktype","character","collections","format","genre","booklanguage","publication","skill"]
DEF = {"PageNo": "1", "PageSize": "20", "SortExpression": "Popularity", "OnSale": "5",
       "SearchString": "brand", "MasterBrand": "113", "pcode": "248001", "isclub": "0"}
REF = "https://www.firstcry.com/hotwheels/5/0/113"
JH = {**H, "Accept": "application/json, text/javascript, */*; q=0.01",
      "X-Requested-With": "XMLHttpRequest", "Referer": REF}
S = http.Session(**IMP)
S.get(REF, headers=H, timeout=20)
COOK = {c.name: c.value for c in getattr(S.cookies, "jar", S.cookies)}
TAT = "https://www.firstcry.com/tatapi/oam/checkdeliveryinfo"
OUT = {"calls": []}


def el():
    return f"+{time.time() - T0:4.0f}s"


def unwrap(o):
    if isinstance(o, str) and o.strip()[:1] in "[{":
        try:
            return unwrap(json.loads(o))
        except Exception:
            return o
    if isinstance(o, dict):
        return {k: unwrap(v) for k, v in o.items()}
    if isinstance(o, list):
        return [unwrap(v) for v in o]
    return o


def prods(j):
    out, st = [], [j]
    while st:
        n = st.pop()
        if isinstance(n, list):
            st.extend(n)
        elif isinstance(n, dict):
            if "PId" in n and "PNm" in n:
                out.append(n)
            else:
                st.extend(n.values())
    return out


def listing(instock=False, pages=None):
    tok = str(random.randint(10**8, 10**9))
    pages = pages or (12 if instock else 22)
    def one(p):
        over = dict(DEF, PageNo=str(p), searchrank=tok)
        if instock:
            over["OutOfStock"] = "1"
        u = FC_API + "?" + "&".join(f"{k}={quote(str(over.get(k, '')), safe='')}" for k in KEYS)
        try:
            r = http.get(u, headers=JH, cookies=COOK, timeout=20, **IMP)
            return prods(unwrap(r.json()))
        except Exception:
            return []
    allp = {}
    with ThreadPoolExecutor(11) as ex:
        for ps in ex.map(one, range(1, pages + 1)):
            for p in ps:
                allp[str(p["PId"])] = p
    return allp


def json_after(txt, pat):
    m = re.search(pat, txt)
    if not m:
        return None
    i = txt.find("{", m.end() - 1)
    depth, ins, esc = 0, False, False
    for j in range(i, min(len(txt), i + 3_000_000)):
        c = txt[j]
        if ins:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                ins = False
        elif c == '"':
            ins = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(txt[i:j + 1])
                except Exception:
                    return None
    return None


def page(pid):
    url = f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail?fresh={random.randint(10**6, 10**7)}"
    r = http.get(url, headers=H, cookies=COOK, timeout=25, **IMP)
    cur = json_after(r.text, r"CurrentProductDetailJSON\s*=\s*\{") or {}
    pdj = json_after(r.text, r"(?<![A-Za-z])ProductDetailJSON\s*=\s*\{") or {}
    return cur, pdj, str(r.url)


def tat(pid, group, pincode, cur, pinfo, ftk=""):
    ent = cur.get(str(pid)) or {}
    body = {"ProductIDs": str(pid), "Pincode": str(pincode), "ComboId": 0, "CheckTAT": True,
            "CheckDropShipment": str(pinfo.get("StockT", "")).lower() == "creditvendorstock",
            "CheckCOD": bool(pinfo.get("CODA", True)), "subCatID": pinfo.get("SCID", 94),
            "MRP": ent.get("mrp") or pinfo.get("MRP") or 0, "AddressType": "Home",
            "Discount": ent.get("Dis") or 0, "minQty": ent.get("minQty") or 1,
            "CatID": pinfo.get("PCID", 5), "ftk": ftk, "groupproducts": ",".join(str(g) for g in group)}
    hdr = {**H, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
           "Origin": "https://www.firstcry.com",
           "Referer": f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail"}
    t = time.time()
    try:
        r = http.post(TAT, data=json.dumps(body), headers=hdr, cookies=COOK, timeout=20, **IMP)
        ms = int((time.time() - t) * 1000)
        try:
            j = r.json()
        except Exception:
            j = None
        rec = {"pid": pid, "pincode": pincode, "status": r.status_code, "ms": ms, "json": j,
               "text": None if j is not None else r.text[:400],
               "cc": r.headers.get("cache-control"), "st": r.headers.get("server-timing"), "body": body}
    except Exception as e:
        rec = {"pid": pid, "pincode": pincode, "err": str(e)[:120]}
    OUT["calls"].append(rec)
    return rec


def gs(rec):
    j = rec.get("json") or {}
    res = j.get("Result") if isinstance(j, dict) else None
    if isinstance(res, dict):
        return res.get("groupserviceability"), res
    return None, res


cat = listing()
inst = listing(instock=True)
names = {pid: p.get("PNm", "") for pid, p in {**cat, **inst}.items()}
print(f"{el()} catalogue {len(cat)}, in-stock list {len(inst)}")
k0 = next(iter(cat.values()))
print("listing record fields:", sorted(k0.keys()))

TESTS = [("24473731", "Road Runner"), ("24503747", "El Segundo Coupe"), ("24761909", "Mach Speeder"),
         ("23074610", "Super Twin Mill (absent from listing, page CS 4)"),
         ("23346007", "Mercedes CLA (absent from listing, page CS 4)"),
         ("24314338", "NIGHTBURNERZ 5-pack (v13.1 phantom)"), ("24503746", "Batmobile (v13.1 phantom)"),
         ("24776024", "Mazda RX-7 FC3S (v13.1 phantom)")]

for pid, label in TESTS:
    try:
        cur, pdj, final = page(pid)
    except Exception as e:
        print(f"\n{pid} {label}: page failed {e}")
        continue
    pinfo = (pdj or {}).get("PInfo") or {}
    group = list(cur.keys()) or [pid]
    print(f"\n=== {pid} {label}  ({names.get(pid, '')[:50]}) list={'yes ' + str(inst[pid].get('CrntStock')) if pid in inst else 'no'} "
          f"cat={cat[pid].get('CrntStock') if pid in cat else 'absent'}")
    print(f"   page CS: { {k: v.get('CS') for k, v in cur.items()} }")
    print(f"   PInfo: { {k: pinfo.get(k) for k in ('SCID', 'PCID', 'CODA', 'StockT', 'CurSt', 'PinC', 'BID', 'Dis', 'MRP')} }")
    for pc in ("248001", "0", "110001"):
        rec = tat(pid, group, pc, cur, pinfo)
        g, res = gs(rec)
        if pc == "248001" and pid == "24473731":
            print("   FULL RESPONSE (248001):", json.dumps(rec.get("json"), ensure_ascii=False)[:2500])
            print("   headers: cache-control", rec.get("cc"), "| server-timing", (rec.get("st") or "")[:160])
        brief = {}
        if isinstance(res, dict):
            brief = {k: res.get(k) for k in ("IsServiceable", "Serviceable", "IsDeliverable", "TAT", "ExpectedDeliveryDate",
                                             "IsCODAvailable", "StockQty", "AvailableQty", "Message", "ErrorMessage") if k in res}
        print(f"   TAT pin {pc:6}: HTTP {rec.get('status')} {rec.get('ms')}ms | groupserviceability={g} | {brief}"
              + (f" | text={rec.get('text')}" if rec.get("text") else "") + (f" | err={rec.get('err')}" if rec.get("err") else ""))

# consistency + speed: the Road Runner group 4x in a row
try:
    cur, pdj, _ = page("24473512")
    pinfo = (pdj or {}).get("PInfo") or {}
    group = list(cur.keys())
    print(f"\n=== repeat: Datsun 620 group ({len(group)} cars), 4 calls")
    for i in range(4):
        rec = tat("24473512", group, "248001", cur, pinfo)
        g, res = gs(rec)
        print(f"   #{i + 1}: {rec.get('ms')}ms groupserviceability={g}")
    print("   page CS:", {k: v.get("CS") for k, v in cur.items()})
    print("   list   :", {k: (inst[k].get("CrntStock") if k in inst else None) for k in group})
    print("   catalog:", {k: (cat[k].get("CrntStock") if k in cat else None) for k in group})
    # all keys of Result once
    g, res = gs(OUT["calls"][-1])
    if isinstance(res, dict):
        print("   Result keys:", sorted(res.keys())[:80])
except Exception as e:
    print("repeat failed:", e)

json.dump(OUT, open("probe_report.json", "w"), indent=1, default=str)
print(f"done in {time.time() - T0:.0f}s")
