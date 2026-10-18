#!/usr/bin/env python3
"""Probe #9: which FirstCry signal is right, and how fast does each one move?

Signals for one car:
  CAT  = catalogue listing CrntStock (fresh searchrank token)
  LIST = membership + CrntStock on the in-stock list (OutOfStock=1, fresh token)
  PDP  = product page CS, (a) as a phone/browser gets it from the CDN and
         (b) cache-busted so FirstCry renders it fresh.
Part A: cache behaviour of product pages (plain / ?query / other slug / mobile).
Part B: endpoints the product page uses (looking for a live stock API).
Part C: ~11-minute time series of CAT + LIST every ~15 s; every change gets a
        fresh product-page read immediately.
"""
import json, re, time, random, os, sys
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

T0 = time.time()
DUR = float(os.getenv("PROBE_SECONDS", "660"))
IMP = {"impersonate": "chrome124"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_M = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
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
FOCUS = {"24473731": "Road Runner", "24761909": "Mach Speeder"}
OUT = {"partA": [], "partB": {}, "rounds": [], "events": [], "pdp": []}


def el():
    return f"+{time.time() - T0:5.0f}s"


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
                j = r.json()
                return prods(unwrap(j)), ("TTL" in j)
            except Exception:
                time.sleep(0.5)
        return None, None
    allp, ok, stale = {}, True, 0
    with ThreadPoolExecutor(11) as ex:
        for ps, cached in ex.map(one, range(1, pages + 1)):
            if ps is None:
                ok = False
                continue
            stale += bool(cached)
            for p in ps:
                allp[str(p["PId"])] = p
    return allp, ok, stale


def _cs(p):
    try:
        return int(float(p.get("CrntStock") or 0))
    except Exception:
        return 0


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "x").lower()).strip("-")
    return s[:90] or "x"


def pdp(pid, name="", mode="bust", ua=UA):
    """mode: plain (what a phone gets), q (?query), slug (other slug)."""
    sl = slug(name)
    if mode == "plain":
        url = f"https://www.firstcry.com/hot-wheels/{sl}/{pid}/product-detail"
    elif mode == "q":
        url = f"https://www.firstcry.com/hot-wheels/{sl}/{pid}/product-detail?_cb={random.randint(10**8, 10**9)}"
    else:   # slug
        url = f"https://www.firstcry.com/hot-wheels/{sl}-{random.randint(10**5, 10**6)}/{pid}/product-detail"
    t = time.time()
    try:
        r = http.get(url, headers={**H, "User-Agent": ua}, cookies=COOK, timeout=25, **IMP)
    except Exception as e:
        return {"pid": pid, "mode": mode, "err": str(e)[:80]}
    txt = r.text
    m = re.search(r"CurrentProductDetailJSON\s*=\s*(\{.*?\})\s*[,;]\s*\w+\s*=", txt, re.S)
    info = None
    if m:
        try:
            info = json.loads(m.group(1)).get(pid)
        except Exception:
            info = None
    st = r.headers.get("server-timing") or ""
    cdn = re.search(r"cdn-cache; desc=(\w+)", st)
    org = re.search(r"origin; dur=(\d+)", st)
    cc = r.headers.get("cache-control") or ""
    ma = re.search(r"max-age=(\d+)", cc)
    oos_words = bool(re.search(r"out of stock|notify me|sold out", txt, re.I))
    return {"pid": pid, "mode": mode, "status": r.status_code, "final": str(r.url)[:120],
            "CS": (info or {}).get("CS") if isinstance(info, dict) else None,
            "Rqty": (info or {}).get("Rqty") if isinstance(info, dict) else None,
            "cdn": cdn.group(1) if cdn else None, "origin_ms": int(org.group(1)) if org else None,
            "max_age": int(ma.group(1)) if ma else None, "age": r.headers.get("age"),
            "len": len(txt), "ms": int((time.time() - t) * 1000), "oos_words": oos_words,
            "has_json": bool(m)}


def fmt(d):
    if "err" in d:
        return f"{d['mode']}: ERR {d['err']}"
    return (f"{d['mode']}: CS={d['CS']} [{d['cdn']}, origin {d['origin_ms']}ms, max-age {d['max_age']}, "
            f"{d['status']}{'' if d['final'].count('/') else ''}]")


# ── Part A ────────────────────────────────────────────────────────────────────
print("=" * 20, "PART A: product-page caching", "=" * 20)
cat, ok_c, st_c = listing()
inst, ok_i, st_i = listing(instock=True)
print(f"{el()} catalogue {len(cat)} (complete={ok_c}, cached pages={st_c}); in-stock list {len(inst)} "
      f"(complete={ok_i}, cached pages={st_i})")
for pid, nm in FOCUS.items():
    c, i = cat.get(pid), inst.get(pid)
    print(f"  {nm}: catalogue CrntStock={_cs(c) if c else 'absent'} | in-stock list: "
          f"{('yes, ' + str(_cs(i))) if i else 'no'}")
names = {pid: p.get("PNm", "") for pid, p in {**cat, **inst}.items()}
test = list(FOCUS) + [pid for pid, p in inst.items() if 0 < _cs(p) <= 3][:3]
for pid in test:
    rows = [pdp(pid, names.get(pid, ""), m) for m in ("plain", "plain", "q", "slug")]
    rows.append(pdp(pid, names.get(pid, ""), "plain", ua=UA_M))
    rows[-1]["mode"] = "plain-mobile"
    OUT["partA"].append(rows)
    print(f"  {pid} {names.get(pid, '')[:44]}")
    for d in rows:
        print("     ", fmt(d), "| final", d.get("final", "")[-60:])

# ── Part B ────────────────────────────────────────────────────────────────────
print("\n" + "=" * 20, "PART B: endpoints used by the product page", "=" * 20)
try:
    pid0 = "24473731"
    r = http.get(f"https://www.firstcry.com/hot-wheels/{slug(names.get(pid0, ''))}/{pid0}/product-detail?_cb={random.randint(1, 10**9)}",
                 headers=H, cookies=COOK, timeout=25, **IMP)
    html = r.text
    svcs = sorted(set(re.findall(r"""/svcs/[A-Za-z0-9_]+\.svc/[A-Za-z0-9_]+""", html)))
    scripts = re.findall(r"""<script[^>]+src=["']([^"']+)["']""", html)
    print("svcs endpoints in HTML:", svcs[:60])
    print("scripts:", [s[-70:] for s in scripts][:40])
    js_hits = {}
    fp = [s for s in scripts if re.search(r"firstcry|fcglcdn", s) or s.startswith("/")][:14]
    for s in fp:
        u = s if s.startswith("http") else ("https:" + s if s.startswith("//") else "https://www.firstcry.com" + s)
        try:
            jr = http.get(u, headers=H, timeout=20, **IMP)
        except Exception:
            continue
        js = jr.text
        eps = sorted(set(re.findall(r"""/svcs/[A-Za-z0-9_]+\.svc/[A-Za-z0-9_]+""", js)))
        stockish = sorted(set(m for m in re.findall(r"""["'](/?[A-Za-z0-9_/.\-]*(?:[Ss]tock|[Pp]incode|[Dd]eliver|[Nn]otify|[Ii]nventory|[Aa]vail)[A-Za-z0-9_/.\-]*)["']""", js) if len(m) < 90))
        if eps or stockish:
            js_hits[u[-70:]] = {"svcs": eps[:80], "stockish": stockish[:60]}
    OUT["partB"] = {"svcs_html": svcs, "scripts": scripts, "js": js_hits}
    for k, v in js_hits.items():
        print(" JS", k)
        print("    svcs:", v["svcs"][:80])
        print("    stock-ish strings:", v["stockish"][:60])
    # context around stock-related calls in the HTML itself
    for kw in ("CheckPincode", "pincode", "GetStock", "stock", "Notify"):
        for m in list(re.finditer(kw, html))[:3]:
            print(f"  HTML …{html[max(0, m.start() - 120):m.start() + 160]!r}…".replace("\\n", " ")[:330])
except Exception as e:
    print("part B failed:", e)

# ── Part C ────────────────────────────────────────────────────────────────────
print("\n" + "=" * 20, "PART C: time series", "=" * 20)
state = {}      # pid -> (on_list, list_cs, cat_cs)
first_seen_disagree = {}
round_no = 0
pdp_pool = ThreadPoolExecutor(6)


def snap(cat, inst):
    s = {}
    for pid in set(cat) | set(inst):
        s[pid] = (pid in inst, _cs(inst[pid]) if pid in inst else None,
                  _cs(cat[pid]) if pid in cat else None)
    return s


def disagree(v):
    on, lc, cc = v
    return (on and (cc == 0 or cc is None)) or ((not on) and (cc or 0) > 0) or (on and cc is not None and lc != cc)


while time.time() - T0 < DUR:
    t_round = time.time()
    with ThreadPoolExecutor(2) as ex:
        fc = ex.submit(listing)
        fi = ex.submit(listing, True)
        (cat, ok_c, st_c), (inst, ok_i, st_i) = fc.result(), fi.result()
    for pid, p in {**cat, **inst}.items():
        names.setdefault(pid, p.get("PNm", ""))
    if not (ok_c and ok_i) or st_c or st_i:
        print(f"{el()} round {round_no}: incomplete/cached (cat ok={ok_c} cached={st_c}, list ok={ok_i} cached={st_i}) — skipped")
        time.sleep(3)
        continue
    cur = snap(cat, inst)
    n_dis = sum(1 for v in cur.values() if disagree(v))
    OUT["rounds"].append({"t": round(time.time() - T0, 1), "cat": len(cat), "list": len(inst),
                          "cat_pos": sum(1 for p in cat.values() if _cs(p) > 0), "disagree": n_dis})
    checks = []
    if round_no == 0:
        for pid, v in cur.items():
            if disagree(v) or pid in FOCUS:
                checks.append((pid, "initial-disagree" if disagree(v) else "focus"))
        print(f"{el()} round 0: catalogue {len(cat)} ({OUT['rounds'][-1]['cat_pos']} with stock) | "
              f"in-stock list {len(inst)} | disagreements {n_dis}")
        for pid, why in checks:
            on, lc, cc = cur[pid]
            print(f"      {pid} {names.get(pid, '')[:46]:46} list={'yes' if on else 'no '} {lc} | cat {cc}")
    else:
        for pid in set(cur) | set(state):
            a, b = state.get(pid), cur.get(pid)
            if a != b:
                ev = {"t": round(time.time() - T0, 1), "pid": pid, "name": names.get(pid, "")[:50],
                      "before": a, "after": b}
                OUT["events"].append(ev)
                checks.append((pid, "change"))
                print(f"{el()} CHANGE {pid} {names.get(pid, '')[:44]:44} "
                      f"list {(a or (None,))[0]}/{(a or (None, None))[1]} -> {(b or (None,))[0]}/{(b or (None, None))[1]} | "
                      f"cat {(a or (None, None, None))[2]} -> {(b or (None, None, None))[2]}")
        if round_no % 4 == 0:
            for pid, v in cur.items():
                if disagree(v) and not any(c[0] == pid for c in checks):
                    checks.append((pid, "recheck-disagree"))
    # fresh product page for everything that needs a look (+ what a phone gets for changes)
    futs = []
    for pid, why in checks[:30]:
        futs.append((pid, why, pdp_pool.submit(pdp, pid, names.get(pid, ""), "q"),
                     pdp_pool.submit(pdp, pid, names.get(pid, ""), "plain") if why != "recheck-disagree" else None))
    for pid, why, fb, fp in futs:
        b = fb.result()
        pl = fp.result() if fp else None
        v = cur.get(pid, (None, None, None))
        OUT["pdp"].append({"t": round(time.time() - T0, 1), "pid": pid, "why": why, "sig": v,
                           "fresh": b, "plain": pl})
        print(f"{el()}   PDP {pid} ({why}) list={v[0]}/{v[1]} cat={v[2]} -> fresh {fmt(b)}"
              + (f" | phone gets {fmt(pl)}" if pl else ""))
    state = cur
    round_no += 1
    time.sleep(max(0.0, 15 - (time.time() - t_round)))

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 20, "SUMMARY", "=" * 20)
print(f"rounds: {round_no}; events: {len(OUT['events'])}; product-page reads: {len(OUT['pdp'])}")
agree_list = agree_cat = n = 0
for r in OUT["pdp"]:
    cs = (r["fresh"] or {}).get("CS")
    if not isinstance(cs, int) or (r["fresh"] or {}).get("cdn") == "HIT":
        continue
    on, lc, cc = r["sig"]
    n += 1
    agree_list += (bool(on) == (cs > 0))
    agree_cat += (((cc or 0) > 0) == (cs > 0))
print(f"fresh product-page reads usable: {n}; in-stock list agreed {agree_list}/{n}; catalogue agreed {agree_cat}/{n}")
stale_phone = [r for r in OUT["pdp"] if r.get("plain") and isinstance(r["plain"].get("CS"), int)
               and isinstance(r["fresh"].get("CS"), int) and (r["plain"]["CS"] > 0) != (r["fresh"]["CS"] > 0)]
print(f"times the page a phone gets disagreed with the fresh page: {len(stale_phone)}")
for r in stale_phone[:20]:
    print(f"   +{r['t']}s {r['pid']} {names.get(r['pid'], '')[:40]} phone CS={r['plain']['CS']} "
          f"[{r['plain']['cdn']}, max-age {r['plain']['max_age']}] vs fresh CS={r['fresh']['CS']}")
json.dump(OUT, open("probe_report.json", "w"), indent=1, default=str)
print(f"done in {time.time() - T0:.0f}s")
