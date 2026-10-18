#!/usr/bin/env python3
"""Probe #10: the product page (PDP) as the final word on "buyable".

Facts so far: a FirstCry product page embeds CurrentProductDetailJSON for the
whole colour group; when the opened car is sold out the page switches to an
in-stock sibling (user screenshot: Road Runner URL -> Datsun 620 Purple).
Questions:
 1. What exactly is in that JSON (all siblings? fields per sibling?).
 2. For every car on the in-stock list right now: does a FRESH product page
    agree it is buyable? (one fresh page per colour group covers all siblings)
 3. How long does a fresh product-page read take (cost of verifying an alert)?
 4. TTData in the listing (sibling|size|colour|number) — is that number = CS?
 5. Which cache-buster gives a fresh render: ?query or a different slug?
"""
import json, re, time, random, os, collections
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
RR = "24473731"
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
        for _ in range(2):
            try:
                r = http.get(u, headers=JH, cookies=COOK, timeout=20, **IMP)
                return prods(unwrap(r.json()))
            except Exception:
                time.sleep(0.5)
        return None
    allp = {}
    with ThreadPoolExecutor(11) as ex:
        for ps in ex.map(one, range(1, pages + 1)):
            for p in ps or []:
                allp[str(p["PId"])] = p
    return allp


def _int(x):
    try:
        return int(float(x))
    except Exception:
        return None


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "x").lower()).strip("-")
    return s[:90] or "x"


def _json_after(txt, var):
    """Extract the JSON object assigned to `var` with a brace matcher."""
    m = re.search(var + r"\s*=\s*", txt)
    if not m:
        return None
    i = txt.find("{", m.end())
    if i < 0 or i - m.end() > 5:
        return None
    depth, j, ins, esc = 0, i, False, False
    while j < len(txt):
        c = txt[j]
        if ins:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                ins = False
        else:
            if c == '"':
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
        j += 1
    return None


def pdp(pid, name="", mode="q"):
    sl = slug(name)
    if mode == "plain":
        url = f"https://www.firstcry.com/hot-wheels/{sl}/{pid}/product-detail"
    elif mode == "q":
        url = f"https://www.firstcry.com/hot-wheels/{sl}/{pid}/product-detail?_cb={random.randint(10**8, 10**9)}"
    else:
        url = f"https://www.firstcry.com/hot-wheels/{sl}-{random.randint(10**5, 10**6)}/{pid}/product-detail"
    t = time.time()
    try:
        r = http.get(url, headers=H, cookies=COOK, timeout=25, **IMP)
    except Exception as e:
        return {"pid": pid, "err": str(e)[:80], "ms": int((time.time() - t) * 1000)}
    txt = r.text
    j = _json_after(txt, "CurrentProductDetailJSON")
    st = r.headers.get("server-timing") or ""
    cdn = re.search(r"cdn-cache; desc=(\w+)", st)
    org = re.search(r"origin; dur=(\d+)", st)
    cc = r.headers.get("cache-control") or ""
    ma = re.search(r"max-age=(\d+)", cc)
    other = {}
    for var in ("ProductDetailJSON", "pdpjson", "PDPJSON", "SizeChartJSON", "ColorJSON", "StyleJSON"):
        if var != "CurrentProductDetailJSON" and re.search(var + r"\s*=", txt):
            other[var] = True
    vars_found = sorted(set(re.findall(r"\b([A-Za-z_]*JSON[A-Za-z_]*)\s*=\s*[\[{]", txt)))[:40]
    return {"pid": pid, "status": r.status_code, "json": j, "cdn": cdn.group(1) if cdn else None,
            "origin_ms": int(org.group(1)) if org else None, "max_age": int(ma.group(1)) if ma else None,
            "ms": int((time.time() - t) * 1000), "len": len(txt), "vars": vars_found,
            "title": (re.search(r"<title>(.*?)</title>", txt, re.S) or [None, ""])[1][:90]}


# ── 0. page anatomy: which variant does the page show, and why? ─────────────
print("=" * 16, "0. page anatomy (Road Runner URL)", "=" * 16)
try:
    u = f"https://www.firstcry.com/hot-wheels/hot-wheels-1970-custom-plymouth-road-runner-die-cast-toy-car-orange/{RR}/product-detail"
    for label, url in (("plain", u), ("fresh", u + f"?fresh={random.randint(1000, 9999)}")):
        rr = http.get(url, headers=H, cookies=COOK, timeout=25, **IMP)
        txt = rr.text
        st = rr.headers.get("server-timing") or ""
        print(f"-- {label}: status {rr.status_code} len {len(txt)} cdn {re.findall(r'cdn-cache; desc=(\w+)', st)} "
              f"cc {rr.headers.get('cache-control')}")
        t = re.search(r"<title>(.*?)</title>", txt, re.S)
        print("   title:", (t.group(1).strip()[:100] if t else None))
        h1 = re.findall(r"<h1[^>]*>(.*?)</h1>", txt, re.S)
        print("   h1:", [re.sub(r"<[^>]+>", "", x).strip()[:90] for x in h1][:3])
        bc = re.findall(r'class="[^"]*breadcrumb[^"]*"[^>]*>(.*?)</(?:div|ul|nav)>', txt, re.S)
        print("   breadcrumb:", [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()[-120:] for x in bc][:2])
        for nm in ("Datsun 620", "Road Runner"):
            print(f"   occurrences of {nm!r}: {len(re.findall(re.escape(nm), txt))}")
        # every JSON-ish variable assignment
        vs = re.findall(r"\b(?:var\s+)?([A-Za-z_][A-Za-z0-9_]{2,40})\s*=\s*([\[{])", txt)
        print("   assignments:", sorted(set(v[0] for v in vs))[:60])
        if label == "fresh":
            cj = _json_after(txt, "CurrentProductDetailJSON") or {}
            print("   CurrentProductDetailJSON keys:", list(cj.keys())[:20])
            ent = cj.get(RR) or {}
            for kk in ("pid", "pn", "Gid", "col", "hashCols", "CS", "qty", "minQty", "Rqty", "SCF", "EC", "QueCount",
                       "ispreorder", "Ms", "Mc", "SOID", "ProductStyle", "pd"):
                print(f"      {kk} = {str(ent.get(kk))[:300]}")
            # swatch / colour list: objects that carry "pid" and "color"
            objs = re.findall(r'\{[^{}]*"pid":\s*\d{6,}[^{}]*"color"[^{}]*\}|\{[^{}]*"color"[^{}]*"pid":\s*\d{6,}[^{}]*\}', txt)
            print(f"   swatch-like objects: {len(objs)}")
            for o in objs[:16]:
                try:
                    oj = json.loads(o)
                    small = {k: v for k, v in oj.items() if not isinstance(v, (dict, list)) and len(str(v)) < 40}
                    print("     ", json.dumps(small, ensure_ascii=False)[:420])
                except Exception:
                    print("      (unparsed)", o[:300])
            # the HTML around the colour swatches
            for m in list(re.finditer(r"Out of Stock|outofstock|oos", txt))[:4]:
                print("   ctx:", re.sub(r"\s+", " ", txt[max(0, m.start() - 200):m.start() + 120])[:330])
            OUT["rr_html_len"] = len(txt)
            OUT["rr_page_html"] = txt
except Exception as e:
    print("anatomy failed:", e)

# the product-page script: how is the shown variant chosen?
try:
    js = http.get("https://cdn.fcglcdn.com/brainbees/php/js/pdprevamp.1.55.min.js", headers=H, timeout=25, **IMP).text
    print(f"\npdprevamp js: {len(js)} chars")
    pats = [r"CurrentProductDetailJSON", r"\.CS\b", r"\[.CS.\]", r"hashCols", r"minQty", r"location\.search",
            r"getParameterByName|getQueryString|getUrlParam", r"Out of Stock", r"selectedPid|selPid|defaultPid", r"\.Seq\b"]
    for pat in pats:
        ms = list(re.finditer(pat, js))
        print(f"  /{pat}/: {len(ms)} hit(s)")
        for m in ms[:4]:
            print("     …" + js[max(0, m.start() - 160):m.start() + 200].replace("\n", " ") + "…")
    OUT["pdprevamp_js"] = js
except Exception as e:
    print("js failed:", e)

# ── 1. the Road Runner page: full JSON ────────────────────────────────────────
print("=" * 16, "1. Road Runner page — full CurrentProductDetailJSON", "=" * 16)
cat = listing()
inst = listing(instock=True)
names = {pid: p.get("PNm", "") for pid, p in {**cat, **inst}.items()}
print(f"{el()} catalogue {len(cat)}, in-stock list {len(inst)}")
r = pdp(RR, names.get(RR, ""), "q")
j = r.get("json") or {}
print(f"{el()} RR page: status {r.get('status')} cdn {r.get('cdn')} origin {r.get('origin_ms')}ms "
      f"max-age {r.get('max_age')} took {r.get('ms')}ms title={r.get('title')!r}")
print("  JSON variables on the page:", r.get("vars"))
print("  CurrentProductDetailJSON top-level keys:", list(j.keys())[:30])
OUT["rr_json"] = j
for k, v in list(j.items())[:20]:
    if isinstance(v, dict):
        brief = {kk: v.get(kk) for kk in ("CS", "Rqty", "Gid", "SCF", "EC", "QueCount", "Ms", "Mc", "Dis", "sz", "SOID")}
        nm = v.get("PNm") or v.get("Pnm") or v.get("ProductName") or names.get(str(k), "")
        print(f"   {k}: {str(nm)[:46]:46} {brief} | list={'yes ' + str(_int(inst[k]['CrntStock'])) if k in inst else 'no'} "
              f"| cat={_int(cat[k]['CrntStock']) if k in cat else 'absent'}")
if isinstance(j.get(RR), dict):
    print("  all fields of the RR entry:")
    for kk, vv in j[RR].items():
        print(f"     {kk} = {str(vv)[:110]}")
ttd = (cat.get(RR) or inst.get(RR) or {}).get("TTData", "")
print("  TTData of RR in the listing:", ttd[:400])

# ── 5. cache-buster check on 4 cars (2 reads each mode) ──────────────────────
print("\n" + "=" * 16, "5. which cache-buster gives a fresh page", "=" * 16)
sample = [RR] + [pid for pid, p in inst.items() if (_int(p.get("CrntStock")) or 0) <= 3][:3]
for pid in sample:
    rows = []
    for mode in ("plain", "plain", "q", "q", "slug"):
        d = pdp(pid, names.get(pid, ""), mode)
        cs = ((d.get("json") or {}).get(pid) or {}).get("CS") if isinstance(d.get("json"), dict) else None
        rows.append(f"{mode}:{d.get('cdn')}/{d.get('origin_ms')}ms/age{d.get('max_age')}/CS={cs}")
    print(f"  {pid} {names.get(pid, '')[:36]:36} " + " | ".join(rows))

# ── 2. every in-stock-list car vs its fresh product page ─────────────────────
print("\n" + "=" * 16, "2. in-stock list vs fresh product pages (all groups)", "=" * 16)
inst = listing(instock=True)
cat = listing()
for pid, p in {**cat, **inst}.items():
    names.setdefault(pid, p.get("PNm", ""))
todo = sorted(inst)
pdp_cs, page_of, reads, times = {}, {}, 0, []
groups = collections.Counter()
t_start = time.time()
while todo:
    batch = [pid for pid in todo if pid not in pdp_cs][:8]
    if not batch:
        break
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda pid: pdp(pid, names.get(pid, ""), "q"), batch))
    for d in res:
        reads += 1
        times.append(d.get("ms", 0))
        jj = d.get("json") if isinstance(d.get("json"), dict) else {}
        groups[len(jj)] += 1
        for k, v in jj.items():
            if isinstance(v, dict) and "CS" in v and str(k) not in pdp_cs:
                pdp_cs[str(k)] = _int(v.get("CS"))
                page_of[str(k)] = (d["pid"], d.get("cdn"), d.get("origin_ms"))
        if d["pid"] not in pdp_cs:
            pdp_cs[d["pid"]] = None
    todo = [pid for pid in todo if pid not in pdp_cs]
print(f"{el()} {reads} fresh page reads covered {sum(1 for p in inst if pdp_cs.get(p) is not None)}/{len(inst)} "
      f"in-stock-list cars in {time.time() - t_start:.1f}s; page read ms median "
      f"{sorted(times)[len(times) // 2] if times else '-'} max {max(times) if times else '-'}")
print("  siblings per page (JSON entries):", dict(sorted(groups.items())))
both = [p for p in inst if pdp_cs.get(p) is not None]
agree = [p for p in both if pdp_cs[p] > 0]
dis = [p for p in both if pdp_cs[p] == 0]
cnt_eq = [p for p in agree if pdp_cs[p] == _int(inst[p].get("CrntStock"))]
print(f"  on in-stock list: {len(inst)}; page says buyable: {len(agree)}; page says SOLD OUT: {len(dis)}; "
      f"counts equal for {len(cnt_eq)}/{len(agree)}")
for p in dis[:40]:
    pg = page_of.get(p)
    print(f"   SOLD OUT on page but on list: {p} {names.get(p, '')[:46]:46} list CrntStock {inst[p].get('CrntStock')} "
          f"| cat {cat[p].get('CrntStock') if p in cat else 'absent'} | page {pg}")
for p in [p for p in agree if pdp_cs[p] != _int(inst[p].get("CrntStock"))][:15]:
    print(f"   count differs: {p} {names.get(p, '')[:46]:46} list {inst[p].get('CrntStock')} page {pdp_cs[p]} "
          f"| cat {cat[p].get('CrntStock') if p in cat else 'absent'}")
# cars NOT on the list but buyable on a page we read anyway (siblings)
extra = [p for p, cs in pdp_cs.items() if cs and cs > 0 and p not in inst]
print(f"  buyable on a product page but NOT on the in-stock list: {len(extra)}")
for p in extra[:25]:
    print(f"   {p} {names.get(p, '')[:46]:46} page CS {pdp_cs[p]} | cat {cat[p].get('CrntStock') if p in cat else 'absent'}")
OUT["pdp_cs"] = pdp_cs

# ── 4. TTData numbers vs page CS ──────────────────────────────────────────────
print("\n" + "=" * 16, "4. TTData numbers vs page CS", "=" * 16)
tt_eq = tt_n = 0
rows = []
for pid, p in cat.items():
    for part in str(p.get("TTData") or "").split(","):
        f = part.split("|")
        if len(f) >= 4 and f[0].isdigit() and f[0] in pdp_cs and pdp_cs[f[0]] is not None:
            tt_n += 1
            n = _int(f[3])
            tt_eq += (n == pdp_cs[f[0]])
            if len(rows) < 12:
                rows.append(f"   via {pid}: sibling {f[0]} TTData#={f[3]} page CS={pdp_cs[f[0]]} "
                            f"list={'yes ' + str(inst[f[0]].get('CrntStock')) if f[0] in inst else 'no'}")
print(f"  TTData number == page CS for {tt_eq}/{tt_n} sibling mentions")
print("\n".join(rows))
json.dump(OUT, open("probe_report.json", "w"), indent=1, default=str)
print(f"done in {time.time() - T0:.0f}s")
