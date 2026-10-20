#!/usr/bin/env python3
"""Probe #15: what does FirstCry really say about the SF90 / Chevy Impala / Road
Runner, second by second? The bot alerted "SF90 155 left" at 11:10; the user's app
showed 1 and not deliverable a few minutes later. The delivery check flipped
between yes and no for the Impala 6 times in an hour.

A. Full answers once: product page JSON (every stock-ish field), PInfo, delivery
   check sent like the bot sends it vs. exactly like the product page sends it
   (real subCatID / MRP / discount / CatID / COD / drop-ship), all Result fields,
   and a few pincodes.
B. ~6 min time series every ~10 s: page CS, delivery check (both ways, plus the
   main-product IsServicable count) — what flips, how often, together or not.
"""
import json, re, time, random, os, collections
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

T0 = time.time()
DUR = float(os.getenv("PROBE_SECONDS", "380"))
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
FOCUS = {"23075648": "SF90", "23074613": "Impala", "24473731": "RoadRunner", "23074267": "LaLiebre"}
OUT = {"A": {}, "B": []}


def el():
    return f"+{time.time() - T0:4.0f}s"


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
    url = f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail?fresh={random.randint(10**8, 10**9)}"
    r = http.get(url, headers=H, cookies=COOK, timeout=20, **IMP)
    cur = json_after(r.text, r"CurrentProductDetailJSON\s*=\s*\{") or {}
    pdj = json_after(r.text, r"(?<![A-Za-z])ProductDetailJSON\s*=\s*\{") or {}
    return {str(k): v for k, v in cur.items() if isinstance(v, dict)}, (pdj.get("PInfo") or {}), r.text


def tat(main, group, pincode="248001", pinfo=None, ent=None, style="bot"):
    if style == "bot":
        body = {"ProductIDs": str(main), "Pincode": pincode, "ComboId": 0, "CheckTAT": True,
                "CheckDropShipment": False, "CheckCOD": True, "subCatID": 94, "MRP": 179,
                "AddressType": "Home", "Discount": 0, "minQty": 1, "CatID": 5, "ftk": "",
                "groupproducts": ",".join(group)}
    else:   # exactly what pdprevamp.js sends
        pinfo, ent = pinfo or {}, ent or {}
        pmrp = ent.get("mrp") or pinfo.get("MRP") or 0
        pdis = ent.get("Dis") if ent.get("Dis") not in ("", None, 0) else (pinfo.get("Dis") or 0)
        body = '{"ProductIDs":"%s","Pincode":"%s","ComboId":0,"CheckTAT":true,"CheckDropShipment":%s,"CheckCOD":%s,"subCatID":%s,"MRP":%s,"AddressType":"Home","Discount":%s,"minQty":%s,"CatID":%s, "ftk": "","groupproducts":"%s"}' % (
            main, pincode, "true" if str(pinfo.get("StockT", "")).lower() == "creditvendorstock" else "false",
            "true" if pinfo.get("CODA") else "false", pinfo.get("SCID") or 0, pmrp, pdis,
            ent.get("minQty") or 1, pinfo.get("PCID") or 0, ",".join(group))
    hdr = {**H, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
           "Origin": "https://www.firstcry.com", "Referer": f"https://www.firstcry.com/hot-wheels/x/{main}/product-detail"}
    t = time.time()
    try:
        r = http.post(TAT, data=body if isinstance(body, str) else json.dumps(body), headers=hdr,
                      cookies=COOK, timeout=15, **IMP)
        res = ((r.json() or {}).get("Result") or {})
    except Exception as e:
        return None, {"err": str(e)[:80]}, int((time.time() - t) * 1000)
    g = {str(k): v for k, v in (res.get("groupserviceability") or {}).items()}
    return g, res, int((time.time() - t) * 1000)


# ── A ──────────────────────────────────────────────────────────────────────────
print("=" * 14, "A. full answers", "=" * 14)
groups, pinfos = {}, {}
for pid, nm in FOCUS.items():
    cur, pinfo, txt = page(pid)
    groups[pid] = list(cur)
    pinfos[pid] = pinfo
    e = cur.get(pid) or {}
    print(f"\n{el()} {nm} {pid}: page lists {len(cur)} cars; this car: "
          + json.dumps({k: e.get(k) for k in ("pn", "CS", "qty", "minQty", "Rqty", "QueCount", "SCF", "EC", "SOID", "Gid", "mrp", "Dis", "ispreorder")}, ensure_ascii=False))
    print("   PInfo:", json.dumps({k: pinfo.get(k) for k in ("SCID", "PCID", "StockT", "CODA", "CurSt", "PinC", "MRP", "Dis", "BID", "PgID")}, ensure_ascii=False))
    print("   set CS:", {k: v.get("CS") for k, v in cur.items()})
    # anything else on the page that looks like stock / delivery for this car
    for kw in ("only 1 left", "Only 1 left", "not deliverable", "Not Deliverable", "notdeliverable", "outofstock", "soldout"):
        n = txt.count(kw)
        if n:
            print(f"   page text '{kw}': {n}x")
    for style in ("bot", "page"):
        g, res, ms = tat(pid, groups[pid], "248001", pinfo, e, style)
        print(f"   delivery check ({style}-style) {ms}ms: this car={(g or {}).get(pid)} set={g}")
        if style == "page":
            print("   full Result:", json.dumps({k: v for k, v in (res or {}).items() if k != "groupserviceability"}, ensure_ascii=False)[:1500])
    for pin in ("248002", "248006", "248007", "248171", "249201", "110001", "560001"):
        g, res, ms = tat(pid, groups[pid], pin, pinfo, e, "page")
        print(f"   pincode {pin}: this car={(g or {}).get(pid)} IsServicable={(res or {}).get('IsServicable')} TAT={(res or {}).get('ProductTAT')}")

# ── B ──────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 14, "B. time series", "=" * 14)
last = {}
flips = collections.Counter()
rnd = 0
while time.time() - T0 < DUR:
    t_r = time.time()
    with ThreadPoolExecutor(8) as ex:
        pg = dict(zip(FOCUS, ex.map(lambda p: page(p)[0], FOCUS)))
        tb = dict(zip(FOCUS, ex.map(lambda p: tat(p, groups[p], "248001", None, None, "bot"), FOCUS)))
        tp = dict(zip(FOCUS, ex.map(lambda p: tat(p, groups[p], "248001", pinfos[p], pg[p].get(p) or {}, "page"), FOCUS)))
    tt = round(time.time() - T0)
    for pid, nm in FOCUS.items():
        cur = {"CS": (pg[pid].get(pid) or {}).get("CS"),
               "svc_bot": (tb[pid][0] or {}).get(pid), "svc_page": (tp[pid][0] or {}).get(pid),
               "IsServicable": (tp[pid][1] or {}).get("IsServicable")}
        OUT["B"].append((tt, pid, cur))
        p = last.get(pid)
        if p is not None and p != cur:
            ch = {k: (p[k], cur[k]) for k in cur if p[k] != cur[k]}
            for k in ch:
                flips[(nm, k)] += 1
            print(f"{el()} {nm:10} " + " ".join(f"{k}:{a}->{b}" for k, (a, b) in ch.items()))
        elif p is None:
            print(f"{el()} {nm:10} start {cur}")
        last[pid] = cur
    rnd += 1
    time.sleep(max(0, 10 - (time.time() - t_r)))
print(f"\n{el()} {rnd} rounds; changes: {dict(flips)}")
json.dump(OUT, open("probe_report.json", "w"), indent=1, default=str)
print(f"done in {time.time() - T0:.0f}s")
