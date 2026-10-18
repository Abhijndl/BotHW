#!/usr/bin/env python3
"""Probe #13: can the bot check "orderable to 248001 right now" cheaply and reliably?

A. Every Hot Wheels group: one fresh product page per group -> live CS for every
   car in it (incl. cars the listing never shows). Then FirstCry's delivery check
   (tatapi/oam/checkdeliveryinfo) for 248001 for all of them, in batches of 40.
   Cross-table: page CS x delivery check x in-stock list x catalogue.
   Batch answers vs one-group-per-call answers (must agree).
   Cars with stock but "not deliverable" here: deliverable elsewhere? (regional)
B. The page script around groupserviceability (what the page does with it).
C. ~8 min time series on the cars most likely to move (low stock, disagreements):
   page CS, delivery check, in-stock list and catalogue every ~20 s.
"""
import json, re, time, random, collections, os
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

T0 = time.time()
DUR = float(os.getenv("PROBE_SECONDS", "690"))
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
OUT = {"timeline": collections.defaultdict(list)}
STATS = collections.defaultdict(list)


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


def listing(instock=False):
    tok = str(random.randint(10**8, 10**9))
    pages = 12 if instock else 22
    def one(p):
        over = dict(DEF, PageNo=str(p), searchrank=tok)
        if instock:
            over["OutOfStock"] = "1"
        u = FC_API + "?" + "&".join(f"{k}={quote(str(over.get(k, '')), safe='')}" for k in KEYS)
        for _ in range(2):
            try:
                r = http.get(u, headers=JH, cookies=COOK, timeout=20, **IMP)
                return prods(unwrap(r.json()))
            except Exception:
                time.sleep(0.5)
        return None
    allp, ok = {}, True
    with ThreadPoolExecutor(11) as ex:
        for ps in ex.map(one, range(1, pages + 1)):
            if ps is None:
                ok = False
                continue
            for p in ps:
                allp[str(p["PId"])] = p
    return allp, ok


def cs_of(p):
    try:
        return int(float(p.get("CrntStock") or 0))
    except Exception:
        return 0


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
    """Fresh product page -> {pid: {CS, pn, ...}} for the whole colour group."""
    url = f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail?fresh={random.randint(10**6, 10**7)}"
    t = time.time()
    try:
        r = http.get(url, headers=H, cookies=COOK, timeout=25, **IMP)
    except Exception:
        return None
    STATS["page_ms"].append(int((time.time() - t) * 1000))
    STATS["page_kb"].append(len(r.content) // 1024)
    st = r.headers.get("server-timing") or ""
    if "desc=HIT" in st:
        STATS["page_hit"].append(pid)
    cur = json_after(r.text, r"CurrentProductDetailJSON\s*=\s*\{")
    pinfo = (json_after(r.text, r"(?<![A-Za-z])ProductDetailJSON\s*=\s*\{") or {}).get("PInfo") or {}
    if not isinstance(cur, dict):
        return None
    return {"cur": {str(k): v for k, v in cur.items() if isinstance(v, dict)}, "pinfo": pinfo}


def tat(main, pids, pincode="248001"):
    body = {"ProductIDs": str(main), "Pincode": str(pincode), "ComboId": 0, "CheckTAT": True,
            "CheckDropShipment": False, "CheckCOD": True, "subCatID": 94, "MRP": 179,
            "AddressType": "Home", "Discount": 0, "minQty": 1, "CatID": 5, "ftk": "",
            "groupproducts": ",".join(str(p) for p in pids)}
    hdr = {**H, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
           "Origin": "https://www.firstcry.com",
           "Referer": f"https://www.firstcry.com/hot-wheels/x/{main}/product-detail"}
    t = time.time()
    for _ in range(2):
        try:
            r = http.post(TAT, data=json.dumps(body), headers=hdr, cookies=COOK, timeout=20, **IMP)
            STATS["tat_ms"].append(int((time.time() - t) * 1000))
            j = r.json()
            res = (j or {}).get("Result") or {}
            g = res.get("groupserviceability") or {}
            return {str(k): v for k, v in g.items()}, res
        except Exception:
            time.sleep(0.5)
    return None, None


def tat_many(pids, pincode="248001", batch=40):
    pids = list(dict.fromkeys(pids))
    chunks = [pids[i:i + batch] for i in range(0, len(pids), batch)]
    out, bad = {}, 0
    with ThreadPoolExecutor(6) as ex:
        for (g, _), ch in zip(ex.map(lambda c: tat(c[0], c, pincode), chunks), chunks):
            if g is None:
                bad += 1
                continue
            for k in ch:
                if k in g:
                    out[k] = g[k]
    return out, bad, len(chunks)


# ── A. full picture ───────────────────────────────────────────────────────────
print("=" * 16, "A. every group: page CS + delivery check", "=" * 16)
cat, okc = listing()
inst, oki = listing(True)
recs = {**cat, **inst}
names = {k: p.get("PNm", "") for k, p in recs.items()}
print(f"{el()} catalogue {len(cat)} (ok={okc}), in-stock list {len(inst)} (ok={oki})")
grp_of = {}
todo, seen_g = [], set()
for k in sorted(recs):
    g = str(recs[k].get("P_Grp_ID") or k)
    grp_of[k] = g
    if g not in seen_g:
        seen_g.add(g)
        todo.append(k)
t = time.time()
with ThreadPoolExecutor(8) as ex:
    pages = dict(zip(todo, ex.map(page, todo)))
page_cs, group_members = {}, {}
for k, pg in pages.items():
    if not pg:
        continue
    mem = list(pg["cur"])
    for m, v in pg["cur"].items():
        page_cs[m] = v.get("CS")
        names.setdefault(m, v.get("pn", ""))
        group_members[m] = mem
fails = sum(1 for v in pages.values() if not v)
print(f"{el()} {len(todo)} groups (listing P_Grp_ID) -> {len(pages) - fails} pages read in {time.time() - t:.1f}s "
      f"({fails} failed); {len(page_cs)} cars with live CS; page median {sorted(STATS['page_ms'])[len(STATS['page_ms']) // 2]}ms, "
      f"~{sum(STATS['page_kb']) // max(1, len(STATS['page_kb']))} KB each; CDN hits {len(STATS['page_hit'])}")
# a car missing from every page we read (its listing group id was wrong) -> read its own page
missing = [k for k in recs if k not in page_cs]
if missing:
    with ThreadPoolExecutor(8) as ex:
        for k, pg in zip(missing, ex.map(page, missing)):
            for m, v in ((pg or {}).get("cur") or {}).items():
                page_cs.setdefault(m, v.get("CS"))
                names.setdefault(m, v.get("pn", ""))
                group_members.setdefault(m, list(pg["cur"]))
    print(f"{el()} {len(missing)} listing cars were not in their group's page -> read their own pages; "
          f"still missing {sum(1 for k in recs if k not in page_cs)}")
universe = list(page_cs)
t = time.time()
svc, bad, n = tat_many(universe)
print(f"{el()} delivery check 248001: {len(svc)}/{len(universe)} answered in {n} calls ({bad} failed) "
      f"in {time.time() - t:.1f}s; tat median {sorted(STATS['tat_ms'])[len(STATS['tat_ms']) // 2]}ms")

# batch vs per-group
agree = disagree = 0
ex_dis = []
for k in random.sample(todo, min(12, len(todo))):
    mem = group_members.get(k) or [k]
    g, _ = tat(k, mem)
    for m in mem:
        if g and m in g and m in svc:
            if g[m] == svc[m]:
                agree += 1
            else:
                disagree += 1
                ex_dis.append((m, g[m], svc[m]))
print(f"   per-group calls vs batched answers: agree {agree}, disagree {disagree} {ex_dis[:6]}")

# cross-table
tab = collections.Counter()
rows = []
for k in universe:
    c = page_cs.get(k)
    s = svc.get(k)
    on = k in inst
    cc = cs_of(cat[k]) if k in cat else None
    key = ("CS>0" if (c or 0) > 0 else "CS=0", f"svc={s}", "list" if on else "no-list",
           "cat>0" if (cc or 0) > 0 else ("cat=0" if cc is not None else "no-cat"))
    tab[key] += 1
    rows.append((k, c, s, on, cc))
print("\n   page CS | delivery 248001 | in-stock list | catalogue  ->  cars")
for key, nn in sorted(tab.items(), key=lambda kv: -kv[1]):
    print(f"   {key[0]:5} | {key[1]:6} | {key[2]:7} | {key[3]:6} -> {nn}")
OUT["A"] = {"rows": rows, "names": names, "groups": {k: group_members.get(k) for k in universe}}

# what each signal would call "orderable to 248001" vs the truth (CS>=2 and svc==1)
truth = {k for k, c, s, on, cc in rows if (c or 0) >= 2 and s == 1}
by_list = {k for k, c, s, on, cc in rows if on and cs_of(inst[k]) >= 2}
by_cat = {k for k, c, s, on, cc in rows if (cc or 0) >= 2}
print(f"\n   orderable to 248001 (page CS>=2 and delivery ok): {len(truth)}")
print(f"   in-stock list (>=2) says in stock: {len(by_list)}; of those NOT orderable: {len(by_list - truth)}; "
      f"orderable but not on list: {len(truth - by_list)}")
print(f"   catalogue (>=2) says in stock: {len(by_cat)}; of those NOT orderable: {len(by_cat - truth)}; "
      f"orderable but catalogue says no: {len(truth - by_cat)}")
for k in sorted(by_list - truth)[:25]:
    print(f"     list says yes, not orderable: {k} {names.get(k, '')[:48]:48} list {cs_of(inst[k])} page CS {page_cs.get(k)} svc {svc.get(k)}")
for k in sorted(truth - by_list - by_cat)[:40]:
    print(f"     orderable, invisible in listing: {k} {names.get(k, '')[:48]:48} page CS {page_cs.get(k)}")

# regional: stock but not deliverable here
nd = [k for k, c, s, on, cc in rows if (c or 0) >= 2 and s == 0]
print(f"\n   cars with page CS>=2 but NOT deliverable to 248001: {len(nd)}")
if nd:
    for pin in ("110001", "400001", "560001", "700001", "600001", "411001", "500001", "380001", "0"):
        g, bad, n = tat_many(nd[:120], pin)
        ones = sum(1 for k in nd[:120] if g.get(k) == 1)
        print(f"     pincode {pin:6}: deliverable {ones}/{min(len(nd), 120)}")
z1 = [k for k, c, s, on, cc in rows if (c or 0) == 0 and s == 1]
print(f"   cars with page CS=0 but delivery check says 1: {len(z1)}  e.g. {[(k, names.get(k, '')[:30]) for k in z1[:6]]}")
# main-product answer fields for a few kinds
for kind, lst in (("CS>=2 svc1", sorted(truth)[:1]), ("CS>=2 svc0", nd[:1]), ("CS0 svc1", z1[:1])):
    for k in lst:
        g, res = tat(k, group_members.get(k) or [k])
        brief = {kk: (res or {}).get(kk) for kk in ("IsServicable", "IsServiceable", "Serviceable", "ProductTAT",
                                                   "IsNDD", "NDDDate", "CODAvailable", "DispatchTAT", "Message", "Msg")}
        print(f"   main-product answer [{kind}] {k} {names.get(k, '')[:36]}: {brief}")

# ── B. page script ────────────────────────────────────────────────────────────
print("\n" + "=" * 16, "B. page script around the delivery check", "=" * 16)
try:
    r0 = http.get("https://www.firstcry.com/hot-wheels/x/24473731/product-detail?fresh=1", headers=H, cookies=COOK, timeout=25, **IMP)
    js_urls = [u for u in re.findall(r"""<script[^>]+src=["']([^"']+)["']""", r0.text) if "pdprevamp" in u]
    for u in js_urls[:1]:
        u = "https:" + u if u.startswith("//") else u
        js = http.get(u, headers=H, timeout=25, **IMP).text
        print("  script:", u[-60:], len(js), "chars")
        for kw in ("groupserviceability", "checkdeliveryinfo"):
            for m in list(re.finditer(kw, js))[:4]:
                print(f"  …{js[max(0, m.start() - 700):m.start() + 900]}…\n")
except Exception as e:
    print("  failed:", e)

# ── C. time series ────────────────────────────────────────────────────────────
print("\n" + "=" * 16, "C. time series", "=" * 16)
focus = [k for k, c, s, on, cc in rows if (c is not None and 0 < c <= 6) or (on and (c or 0) == 0)
         or ((cc or 0) > 0 and (c or 0) == 0) or (on and s == 0 and (c or 0) > 0)]
focus = list(dict.fromkeys(focus))[:160]
fgroups = []
for k in focus:
    g = group_members.get(k) or [k]
    if not any(k in fg for fg in fgroups):
        fgroups.append(g)
print(f"{el()} watching {len(focus)} cars in {len(fgroups)} groups")
last = {}
rnd = 0
while time.time() - T0 < DUR:
    t_r = time.time()
    with ThreadPoolExecutor(3) as ex:
        f_cat = ex.submit(listing)
        f_in = ex.submit(listing, True)
        f_svc = ex.submit(tat_many, focus)
        (c2, okc2), (i2, oki2), (svc2, bad2, _) = f_cat.result(), f_in.result(), f_svc.result()
    # pages for a slice of the focus groups each round (all of them every ~3 rounds)
    sl = fgroups[(rnd % 3)::3]
    with ThreadPoolExecutor(8) as ex:
        pgs = list(ex.map(lambda g: page(g[0]), sl))
    pcs = {}
    for pg in pgs:
        for m, v in ((pg or {}).get("cur") or {}).items():
            pcs[m] = v.get("CS")
    tt = round(time.time() - T0)
    for k in focus:
        prev = last.get(k) or {}
        cur = {"page": pcs[k] if k in pcs else prev.get("page", page_cs.get(k)),
               "svc": svc2[k] if k in svc2 else prev.get("svc", svc.get(k)),
               "list": (cs_of(i2[k]) if k in i2 else None) if oki2 else prev.get("list"),
               "cat": (cs_of(c2[k]) if k in c2 else None) if okc2 else prev.get("cat")}
        prev = last.get(k)
        if prev != cur:
            OUT["timeline"][k].append((tt, cur))
            if prev is not None:
                ch = {f: (prev.get(f), cur.get(f)) for f in cur if prev.get(f) != cur.get(f)}
                print(f"{el()} {k} {names.get(k, '')[:40]:40} " + " ".join(f"{f}:{a}->{b}" for f, (a, b) in ch.items()))
        last[k] = cur
    rnd += 1
    time.sleep(max(0, 20 - (time.time() - t_r)))
print(f"{el()} {rnd} rounds")

# who moved first
print("\n   per-car order of changes (first signal to show a new state):")
for k, tl in OUT["timeline"].items():
    if len(tl) < 2:
        continue
    seq = []
    for (t1, a), (t2, b) in zip(tl, tl[1:]):
        for f in ("page", "svc", "list", "cat"):
            if a.get(f) != b.get(f):
                seq.append(f"{t2}s {f} {a.get(f)}->{b.get(f)}")
    print(f"   {k} {names.get(k, '')[:40]:40} " + " | ".join(seq[:10]))
OUT["stats"] = {k: (sorted(v)[len(v) // 2] if v and isinstance(v[0], int) else len(v)) for k, v in STATS.items()}
print("\n   stats:", OUT["stats"])
json.dump(OUT, open("probe_report.json", "w"), indent=1, default=str)
print(f"done in {time.time() - T0:.0f}s")
