#!/usr/bin/env python3
"""Probe #12: FirstCry's delivery check (tatapi/oam/checkdeliveryinfo) at scale.
 1. Can one call answer for MANY cars (groupproducts = any list of ids)? Limit?
 2. Does a car's answer depend on which car is the "main" ProductIDs?
 3. Stability over ~6 min (flips? do they line up with listing / page changes?)
 4. Coverage: cars deliverable to 248001 that the Hot Wheels listing never shows.
"""
import json, re, time, random, collections
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

T0 = time.time()
DUR = 360
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
OUT = {}


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
    try:
        r = http.get(url, headers=H, cookies=COOK, timeout=25, **IMP)
    except Exception:
        return {}
    return json_after(r.text, r"CurrentProductDetailJSON\s*=\s*\{") or {}


def tat(main, pids, pincode="248001", rec=None):
    rec = rec or {}
    body = {"ProductIDs": str(main), "Pincode": pincode, "ComboId": 0, "CheckTAT": True,
            "CheckDropShipment": False, "CheckCOD": True, "subCatID": int(rec.get("ScId") or 94),
            "MRP": int(float(rec.get("MRP") or 179)), "AddressType": "Home",
            "Discount": int(float(rec.get("Disc") or 0)), "minQty": 1,
            "CatID": int(rec.get("PcId") or 5), "ftk": "", "groupproducts": ",".join(str(p) for p in pids)}
    hdr = {**H, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
           "Origin": "https://www.firstcry.com",
           "Referer": f"https://www.firstcry.com/hot-wheels/x/{main}/product-detail"}
    t = time.time()
    try:
        r = http.post(TAT, data=json.dumps(body), headers=hdr, cookies=COOK, timeout=25, **IMP)
        j = r.json()
        res = (j or {}).get("Result") or {}
        g = res.get("groupserviceability") or {}
        return {str(k): v for k, v in g.items()}, int((time.time() - t) * 1000), r.status_code, res.get("IsServicable")
    except Exception as e:
        return None, int((time.time() - t) * 1000), str(e)[:60], None


cat = listing()
inst = listing(instock=True)
recs = {**cat, **inst}
names = {pid: p.get("PNm", "") for pid, p in recs.items()}
print(f"{el()} catalogue {len(cat)} (stock>0: {sum(1 for p in cat.values() if float(p.get('CrntStock') or 0) > 0)}), "
      f"in-stock list {len(inst)}")

# siblings (incl. cars the listing never shows) from ~20 fresh pages of distinct groups
groups_seen, sib_cs, sib_nm = set(), {}, {}
cands = sorted(inst, key=lambda p: recs[p].get("P_Grp_ID") or p)
todo = []
for p in cands:
    g = str(recs[p].get("P_Grp_ID") or p)
    if g not in groups_seen:
        groups_seen.add(g)
        todo.append(p)
with ThreadPoolExecutor(8) as ex:
    pages = list(ex.map(page, todo[:40]))
for cur in pages:
    for k, v in (cur or {}).items():
        if isinstance(v, dict):
            sib_cs[str(k)] = v.get("CS")
            sib_nm[str(k)] = v.get("pn", "")
names.update({k: v for k, v in sib_nm.items() if k not in names})
extra = [k for k in sib_cs if k not in recs]
print(f"{el()} read {len(todo[:40])} pages -> {len(sib_cs)} cars; {len(extra)} of them never appear in the listing")

# ── 1. batch size ─────────────────────────────────────────────────────────────
print("\n=== 1. one call, many cars ===")
universe = list(dict.fromkeys(list(inst) + [p for p in cat if float(cat[p].get("CrntStock") or 0) > 0] + extra))
main = universe[0]
for n in (10, 50, 100, 200, 400):
    ids = universe[:n]
    g, ms, st, iss = tat(main, ids, rec=recs.get(main))
    print(f"   {n:4} ids -> HTTP {st} {ms}ms, answered {len(g or {})} ids"
          + (f", missing {len(set(ids) - set(g or {}))}" if g is not None else ""))
    if g is None or len(g) < n:
        break

# ── 2. does the main product change the answer? ──────────────────────────────
print("\n=== 2. same cars, different main product ===")
ids = universe[:60]
base, _, _, _ = tat(ids[0], ids, rec=recs.get(ids[0]))
diffs = 0
for m in ids[1:6]:
    g, ms, st, _ = tat(m, ids, rec=recs.get(m))
    d = [k for k in ids if (g or {}).get(k) != (base or {}).get(k)]
    diffs += len(d)
    print(f"   main {m}: {len(d)} answers differ" + (f" e.g. {d[:5]}" if d else ""))
# per-group call vs big batch for the Road Runner group
rr_grp = ["24473510", "24473511", "24473512", "24473513", "24473514", "24473515", "24473516",
          "24473712", "24473713", "24473723", "24473724", "24473731", "24537351"]
g1, _, _, _ = tat("24473731", rr_grp)
g2, _, _, _ = tat(universe[0], universe[:150] + rr_grp, rec=recs.get(universe[0]))
print("   RR group alone :", g1)
print("   RR in big batch:", {k: (g2 or {}).get(k) for k in rr_grp})

# ── 3/4. time series ──────────────────────────────────────────────────────────
print("\n=== 3. stability over time (every ~15 s) ===")
BATCH = 150
hist = collections.defaultdict(list)     # pid -> [(t, val)]
rounds = 0
while time.time() - T0 < DUR:
    t_r = time.time()
    chunks = [universe[i:i + BATCH] for i in range(0, len(universe), BATCH)]
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda ch: tat(ch[0], ch, rec=recs.get(ch[0])), chunks))
    ok = all(r[0] is not None for r in res)
    tt = round(time.time() - T0)
    for (g, ms, st, _), ch in zip(res, chunks):
        for k in ch:
            v = (g or {}).get(k)
            if v is not None and (not hist[k] or hist[k][-1][1] != v):
                hist[k].append((tt, v))
    rounds += 1
    if rounds == 1:
        ones = [k for k in universe if hist[k] and hist[k][-1][1] == 1]
        print(f"{el()} round 1: {len(chunks)} calls ({', '.join(str(r[1]) + 'ms' for r in res)}), "
              f"{len(ones)}/{len(universe)} deliverable to 248001")
    time.sleep(max(0, 15 - (time.time() - t_r)))
print(f"{el()} {rounds} rounds done")
flips = {k: h for k, h in hist.items() if len(h) > 1}
print(f"   cars whose answer changed: {len(flips)}")
for k, h in list(flips.items())[:30]:
    lc = inst[k].get("CrntStock") if k in inst else None
    cc = cat[k].get("CrntStock") if k in cat else None
    print(f"     {k} {names.get(k, '')[:44]:44} {h} | list {lc} cat {cc} page CS {sib_cs.get(k)}")

# ── 4. coverage + summary vs listing ──────────────────────────────────────────
print("\n=== 4. deliverable to 248001 vs what the listing says ===")
final = {k: h[-1][1] for k, h in hist.items() if h}
on_list = [k for k in inst]
print(f"   in-stock list cars: {len(on_list)}; deliverable: {sum(1 for k in on_list if final.get(k) == 1)}; "
      f"NOT deliverable: {sum(1 for k in on_list if final.get(k) == 0)}")
nd = [k for k in on_list if final.get(k) == 0]
for k in nd[:40]:
    print(f"     list says in stock, not deliverable: {k} {names.get(k, '')[:50]:50} list {inst[k].get('CrntStock')}")
gap = [k for k in extra if final.get(k) == 1 and (sib_cs.get(k) or 0) > 0]
print(f"   deliverable + in stock but NEVER in the Hot Wheels listing: {len(gap)}")
for k in gap[:40]:
    print(f"     {k} {names.get(k, '')[:60]:60} page CS {sib_cs.get(k)}")
OUT.update(final=final, flips=flips, extra=extra, sib_cs=sib_cs, names=names)
json.dump(OUT, open("probe_report.json", "w"), indent=1, default=str)
print(f"done in {time.time() - T0:.0f}s")
