#!/usr/bin/env python3
"""Probe #6: listing-API stock vs product-page (PDP) availability.
Why: the bot alerted "Plymouth Road Runner — only 2 left" from FirstCry's live
listing data, but the product page showed out of stock a minute later while the
listing still reported 2 units. Compare, for several products, the listing's
CrntStock (pincode 248001) with everything the product page embeds about stock."""
import json, re, time, random
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

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


def listing(pcode="248001", instock=False):
    tok = str(random.randint(10**8, 10**9))
    def one(p):
        over = dict(DEF, PageNo=str(p), pcode=pcode, searchrank=tok)
        if instock:
            over["OutOfStock"] = "1"
        u = FC_API + "?" + "&".join(f"{k}={quote(str(over.get(k, '')), safe='')}" for k in KEYS)
        r = http.get(u, headers=JH, cookies=COOK, timeout=20, **IMP)
        return prods(unwrap(r.json()))
    allp = {}
    with ThreadPoolExecutor(11) as ex:
        for ps in ex.map(one, range(1, 23)):
            for p in ps:
                allp[str(p["PId"])] = p
    return allp


def pdp(p):
    pid = str(p["PId"])
    url = f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail"
    r = S.get(url, headers=H, timeout=25)
    txt = r.text
    m = re.search(r"CurrentProductDetailJSON\s*=\s*(\{.*?\})\s*[,;]\s*\w+\s*=", txt, re.S)
    info = None
    if m:
        try:
            j = json.loads(m.group(1))
            info = j.get(pid)
        except Exception as e:
            info = {"parse_error": str(e), "head": m.group(1)[:300]}
    flags = {k: (info or {}).get(k) for k in ("CS", "Rqty", "SCF", "EC", "QueCount", "StockT", "isOOS", "OOS",
                                                   "MLfb", "Ms", "Mc", "IsActive", "sz", "Dis")} if isinstance(info, dict) else None
    stock_like = {k: v for k, v in (info or {}).items()
                  if isinstance(info, dict) and re.search(r"stock|qty|oos|avail|cs$|^cs|notify|sell|inv", k, re.I)} if isinstance(info, dict) else None
    return {"pid": pid, "name": p["PNm"][:55], "listing_CrntStock": p.get("CrntStock"),
            "status": r.status_code, "pdp_fields": flags, "stock_like": stock_like,
            "keys": sorted(info.keys())[:80] if isinstance(info, dict) else None,
            "cc": r.headers.get("cache-control"), "st": r.headers.get("server-timing")}



lst = listing()
lin = listing(instock=True)
print(f"listing 248001: {len(lst)} products; in-stock filter: {len(lin)}")
pos = {pid: p for pid, p in lst.items() if int(p.get("CrntStock") or 0) > 0}
not_in = [p for pid, p in pos.items() if pid not in lin]
in_low = sorted([p for pid, p in pos.items() if pid in lin], key=lambda p: int(p["CrntStock"]))[:14]
extra = [p for pid, p in lin.items() if pid not in lst][:5]
print(f"stock>0 in catalogue: {len(pos)}; of those NOT on in-stock list: {len(not_in)}; on in-stock list but missing from catalogue: {len(extra)}")
sample = not_in[:24] + in_low + extra
with ThreadPoolExecutor(8) as ex:
    rows = list(ex.map(pdp, sample))
agree = disagree = 0
for row in rows:
    on = row["pid"] in lin
    cs = (row["pdp_fields"] or {}).get("CS")
    lc = (lin.get(row["pid"]) or {}).get("CrntStock")
    ok = (on and isinstance(cs, int) and cs > 0) or ((not on) and cs == 0)
    agree += ok; disagree += (not ok)
    print(("OK  " if ok else "DIFF"), "on_instock_list=", on, "| catalogue", row["listing_CrntStock"], "| instock-list", lc, "| page CS", cs, "|", row["name"])
print(f"\nagree={agree} disagree={disagree}")
json.dump(rows, open("probe_report.json", "w"), indent=1, default=str)
