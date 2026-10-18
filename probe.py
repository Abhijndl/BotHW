#!/usr/bin/env python3
"""Research probe #2 (not part of the bot).
FirstCry: confirm which cache-key variants return the SAME full catalogue but
freshly computed, and measure how much earlier they see stock changes than the
cached request the bot uses today. Also: PDP embedded data.
Minifygram: table columns, payload size, cheap change-detection queries.
Karz & Dolls: __NEXT_DATA__ structure and the karzOffice API routes."""
import gzip, json, os, re, sys, time, random, traceback
from collections import Counter
from urllib.parse import quote, urljoin
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

IMP = {"impersonate": "chrome124"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
REPORT = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
ONLY = set(filter(None, os.getenv("PROBE_ONLY", "").split(",")))


def log(*a):
    print(*a, flush=True)


def section(name):
    def deco(fn):
        def run():
            if ONLY and name not in ONLY:
                return
            log(f"\n==================== {name} ====================")
            t0 = time.time()
            try:
                REPORT[name] = fn()
            except Exception as e:
                REPORT[name] = {"error": repr(e), "tb": traceback.format_exc()[-1500:]}
                log("ERROR", traceback.format_exc())
            log(f"[{name}] done in {time.time()-t0:.1f}s")
        return run
    return deco


FC_API = "https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging"
KEYS = ["PageNo","PageSize","SortExpression","OnSale","SearchString","SubCatId","BrandId","Price","Age","Color","OptionalFilter","OutOfStock","Type1","Type2","Type3","Type4","Type5","Type6","Type7","Type8","Type9","Type10","Type11","Type12","Type13","Type14","Type15","combo","discount","searchwithincat","ProductidQstr","searchrank","pmonths","cgen","PriceQstr","DiscountQstr","sorting","MasterBrand","Rating","Offer","skills","material","curatedcollections","measurement","gender","exclude","premium","pcode","isclub","deliverytype","authors","booktype","character","collections","format","genre","booklanguage","publication","skill"]
DEF = {"PageNo": "1", "PageSize": "20", "SortExpression": "Popularity", "OnSale": "5",
       "SearchString": "brand", "MasterBrand": "113", "pcode": "248001", "isclub": "0"}
REF = "https://www.firstcry.com/hotwheels/5/0/113"
JH = {**H, "Accept": "application/json, text/javascript, */*; q=0.01",
      "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
      "Referer": REF, "Cache-Control": "no-cache, no-store, max-age=0", "Pragma": "no-cache"}
SESS = http.Session(**IMP)
try:
    SESS.get(REF, headers=H, timeout=20)
except Exception as e:
    log("warm-up failed", e)
COOK = {c.name: c.value for c in getattr(SESS.cookies, "jar", SESS.cookies)}


def fc_url(over=None, extra=""):
    over = over or {}
    return FC_API + "?" + "&".join(f"{k}={quote(str(over.get(k, DEF.get(k, ''))), safe='')}" for k in KEYS) + extra


def unwrap(o):
    if isinstance(o, str):
        s = o.strip()
        if s[:1] in "[{":
            try:
                return unwrap(json.loads(s))
            except Exception:
                return o
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


def fc_get(over=None, extra=""):
    u = fc_url(over, extra)
    t0 = time.time()
    try:
        r = http.get(u, headers=JH, cookies=COOK, timeout=20, **IMP)
    except Exception as e:
        return {"err": type(e).__name__}
    st = r.headers.get("server-timing", "") or ""
    out = {"status": r.status_code, "ms": int((time.time() - t0) * 1000),
           "cdn": (re.findall(r"cdn-cache; desc=(\w+)", st) or [""])[0],
           "cc": r.headers.get("cache-control", "")}
    try:
        j = unwrap(r.json())
    except Exception:
        out["body"] = r.text[:200]
        return out
    ps = prods(j)
    out.update({"ttl": j.get("TTL") if isinstance(j, dict) else None, "n": len(ps),
                "stock": {str(p.get("PId")): p.get("CrntStock") for p in ps}})
    return out


def sweep(over, extra_fn=None, maxpages=22):
    """All pages in parallel. extra_fn(page) -> extra query string."""
    def one(p):
        o = dict(over or {}); o["PageNo"] = str(p)
        return p, fc_get(o, extra_fn(p) if extra_fn else "")
    with ThreadPoolExecutor(11) as ex:
        res = dict(ex.map(one, range(1, maxpages + 1)))
    stock = {}
    for p in sorted(res):
        stock.update(res[p].get("stock") or {})
    ttls = [res[p].get("ttl") for p in sorted(res)]
    cdns = Counter(res[p].get("cdn") for p in res)
    errs = [p for p in res if res[p].get("status") != 200]
    return {"stock": stock, "ttls": ttls, "cdns": dict(cdns), "errs": errs,
            "n": len(stock), "instock": sum(1 for v in stock.values() if str(v) not in ("0", "0.0"))}


def cmp(a, b):
    sa, sb = a["stock"], b["stock"]
    only_a = sorted(set(sa) - set(sb)); only_b = sorted(set(sb) - set(sa))
    diff = [(p, sa[p], sb[p]) for p in set(sa) & set(sb) if str(sa[p]) != str(sb[p])]
    return {"only_a": only_a[:20], "only_b": only_b[:20], "n_only_a": len(only_a),
            "n_only_b": len(only_b), "stock_diff": diff[:30], "n_stock_diff": len(diff)}


@section("fc_equiv")
def fc_equiv():
    res = {}
    r = random.randint(100000, 999999)
    variants = {
        "prod_style": ({}, lambda p: f"&_={int(time.time()*1000)}"),
        "searchrank": ({"searchrank": str(r)}, None),
        "sorting": ({"sorting": str(r)}, None),
        "isclub00": ({"isclub": "00"}, None),
        "searchrank_alpha": ({"searchrank": f"x{r}"}, None),
    }
    sw = {}
    with ThreadPoolExecutor(5) as ex:
        futs = {name: ex.submit(sweep, o, e) for name, (o, e) in variants.items()}
        for name, f in futs.items():
            sw[name] = f.result()
    for name, s in sw.items():
        res[name] = {k: s[k] for k in ("n", "instock", "ttls", "cdns", "errs")}
        log(name, res[name])
    for name in sw:
        if name != "prod_style":
            c = cmp(sw["prod_style"], sw[name]); res["cmp_" + name] = c
            log("prod_style vs", name, c)
    return res


@section("fc_lag")
def fc_lag():
    """Every 30 s for WATCH_SECONDS: cached (bot today) vs fresh (searchrank).
    Record when each stock change first shows up in each."""
    secs = float(os.getenv("WATCH_SECONDS", "360"))
    t_end = time.time() + secs
    first_seen = {"cached": {}, "fresh": {}}
    prev = {"cached": None, "fresh": None}
    rounds = []
    while time.time() < t_end:
        tag = time.strftime("%H:%M:%S", time.gmtime())
        with ThreadPoolExecutor(2) as ex:
            fc = ex.submit(sweep, {}, lambda p: f"&_={int(time.time()*1000)}", 12)
            ff = ex.submit(sweep, {"searchrank": str(random.randint(100000, 999999))}, None, 12)
            cur = {"cached": fc.result(), "fresh": ff.result()}
        row = {"t": tag}
        for k in ("cached", "fresh"):
            s = cur[k]
            row[k] = {"n": s["n"], "instock": s["instock"],
                      "ttl_min": min([t for t in s["ttls"] if isinstance(t, (int, float))] or [None]) if any(isinstance(t, (int, float)) for t in s["ttls"]) else None,
                      "ttl_none": sum(1 for t in s["ttls"] if t is None), "errs": s["errs"]}
            if prev[k] is not None:
                for pid, v in s["stock"].items():
                    pv = prev[k]["stock"].get(pid)
                    if pv is not None and str(pv) != str(v):
                        key = f"{pid}:{pv}->{v}"
                        first_seen[k].setdefault(key, tag)
            prev[k] = s
        rounds.append(row)
        log(row)
        time.sleep(max(0, 30 - (time.time() % 30)))
    log("first_seen cached:", first_seen["cached"])
    log("first_seen fresh :", first_seen["fresh"])
    return {"rounds": rounds, "first_seen": first_seen}


@section("fc_misc")
def fc_misc():
    res = {}
    for v in ["1", "0", "true"]:
        for p in (9, 10, 11, 12):
            x = fc_get({"OutOfStock": v, "PageNo": str(p), "searchrank": str(random.randint(1, 10**6))})
            zero = sum(1 for s in (x.get("stock") or {}).values() if str(s) in ("0", "0.0"))
            res[f"OOS={v} p{p}"] = {"n": x.get("n"), "zero": zero, "ttl": x.get("ttl"), "cdn": x.get("cdn")}
            log(f"OOS={v} p{p}", res[f"OOS={v} p{p}"])
    # PDP embedded data
    url = "https://www.firstcry.com/hot-wheels/hot-wheels-free-wheel-die-cast-mailed-it-168-250-toy-car-blue/23074884/product-detail"
    r = SESS.get(url, headers=H, timeout=25)
    t = r.text
    ctx = []
    for m in re.finditer(r"(CrntStock|crntstock|\"stock\"|StockQty|\"Rqty\"|instock|InStock|isoos|OutOfStock)", t):
        ctx.append(t[max(0, m.start() - 200): m.end() + 200].replace("\n", " "))
        if len(ctx) >= 8:
            break
    res["pdp_ctx"] = ctx
    for c in ctx:
        log("PDP:", c)
    m = re.search(r"23074884", t)
    if m:
        log("PDP first id ctx:", t[max(0, m.start() - 300): m.start() + 300].replace("\n", " "))
    scripts_inline = re.findall(r"<script[^>]*>(.*?)</script>", t, re.S)
    big = sorted(scripts_inline, key=len, reverse=True)[:3]
    for b in big:
        log("PDP inline script head:", b[:600].replace("\n", " "))
    return res


MG = "https://seoqlgtbygddyehugjwv.supabase.co"
MG_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNlb3FsZ3RieWdkZHllaHVnand2Iiwicm9sZSI6"
          "ImFub24iLCJpYXQiOjE3NzcxMzEwNzgsImV4cCI6MjA5MjcwNzA3OH0.TxGeE5sXW2zivw6xhJ7TIAWibGxiPzv4wcmaEihUsqY")
MGH = {**H, "apikey": MG_KEY, "Authorization": f"Bearer {MG_KEY}", "Accept": "application/json"}


@section("mg2")
def mg2():
    res = {}
    for path in ("/rest/v1/products?select=*&limit=1&is_active=eq.true",
                 "/rest/v1/product_skus?select=*&limit=3",
                 "/rest/v1/product_skus?select=updated_at&order=updated_at.desc&limit=2",
                 "/rest/v1/products?select=id,updated_at&order=updated_at.desc&limit=2",
                 "/rest/v1/product_skus?select=product_id,available,updated_at&order=updated_at.desc&limit=5"):
        r = http.get(MG + path, headers=MGH, timeout=20, **IMP)
        res[path] = {"status": r.status_code, "bytes": len(r.content), "body": r.text[:1500]}
        log(path, r.status_code, r.text[:1500])
    sel = ("id,slug,name,brand,category,price_inr,mrp_inr,product_type,badge,preorder_close_at,"
           "preorder_status,updated_at,product_skus!product_skus_product_id_fkey(available)")
    for label, q in (("all", f"select={sel}&is_active=eq.true&limit=2000"),
                     ("filtered", f"select={sel}&is_active=eq.true&limit=2000&or=(brand.ilike.*hot*wheel*,brand.ilike.*mini*gt*,brand.ilike.*kaido*,category.ilike.*trading*card*,name.ilike.*tcg*)")):
        hdr = dict(MGH); hdr["Accept-Encoding"] = "gzip"
        t0 = time.time()
        r = http.get(f"{MG}/rest/v1/products?{q}", headers=hdr, timeout=30, **IMP)
        raw = r.content
        rows = r.json() if r.status_code == 200 else []
        res[label] = {"status": r.status_code, "ms": int((time.time() - t0) * 1000), "rows": len(rows),
                      "bytes": len(raw), "gzip_bytes": len(gzip.compress(raw)),
                      "brands": Counter(str(x.get("brand")) for x in rows).most_common(12),
                      "cats": Counter(str(x.get("category")) for x in rows).most_common()}
        log(label, res[label])
        if r.status_code != 200:
            log(r.text[:400])
    return res


KD = "https://www.karzanddolls.com"


def next_data(t):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def shape(o, depth=0, maxd=4):
    if depth > maxd:
        return "…"
    if isinstance(o, dict):
        return {k: shape(v, depth + 1, maxd) for k, v in list(o.items())[:40]}
    if isinstance(o, list):
        return [f"list[{len(o)}]", shape(o[0], depth + 1, maxd)] if o else "list[0]"
    if isinstance(o, str):
        return o[:60]
    return o


@section("kd2")
def kd2():
    res = {}
    for path in ("/hot-wheels/mainlines", "/", "/mini-gt/mini-gt"):
        r = http.get(KD + path, headers=H, timeout=30, **IMP)
        nd = next_data(r.text)
        if not nd:
            log(path, "no __NEXT_DATA__"); continue
        pp = (nd.get("props") or {}).get("pageProps") or {}
        res[path] = {"keys": list(nd.keys()), "page": nd.get("page"), "query": nd.get("query"),
                     "pageProps_shape": shape(pp, 0, 3)}
        log(path, json.dumps(res[path], ensure_ascii=False)[:5000])
        # find product-like dicts and print 2 full examples
        st, found = [pp], []
        while st and len(found) < 400:
            n = st.pop()
            if isinstance(n, list):
                st.extend(n)
            elif isinstance(n, dict):
                ks = {k.lower() for k in n}
                if ("pid" in ks or "product_id" in ks or "id" in ks) and any(k in ks for k in ("name", "product_name", "title")) and any("price" in k for k in ks):
                    found.append(n)
                else:
                    st.extend(n.values())
        res[path]["n_products"] = len(found)
        res[path]["examples"] = found[:3]
        res[path]["key_union"] = sorted({k for f in found for k in f})[:80]
        stock_keys = Counter()
        for f in found:
            for k, v in f.items():
                if any(s in k.lower() for s in ("stock", "qty", "quant", "avail", "sold", "status", "new", "pre")):
                    stock_keys[(k, str(v)[:20])] += 1
        res[path]["stock_values"] = stock_keys.most_common(40)
        log(path, "products:", len(found))
        log(path, "examples:", json.dumps(found[:2], ensure_ascii=False)[:3000])
        log(path, "stock-ish values:", stock_keys.most_common(40))
    # API routes from JS chunks
    r = http.get(KD + "/hot-wheels/mainlines", headers=H, timeout=30, **IMP)
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', r.text)
    routes = Counter()
    for s in scripts:
        try:
            js = http.get(urljoin(KD, s), headers=H, timeout=20, **IMP).text
        except Exception:
            continue
        for m in re.finditer(r"karzOffice/api([^\"'`\s]{0,120})", js):
            routes[m.group(1)] += 1
        for m in re.finditer(r"""["'`](/(?:api|v1|v2|category|products?|shop|catalog|listing)[A-Za-z0-9_/${}.?=&-]{2,120})["'`]""", js):
            routes[m.group(1)] += 1
        for m in re.finditer(r"""\.(?:get|post)\(\s*[`"']([^`"']{3,160})[`"']""", js):
            routes["CALL " + m.group(1)] += 1
    res["routes"] = routes.most_common(150)
    for k, v in routes.most_common(150):
        log("  route", v, k)
    return res


if __name__ == "__main__":
    for fn in (fc_equiv, fc_misc, mg2, kd2, fc_lag):
        fn()
    REPORT["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("probe_report.json", "w") as f:
        json.dump(REPORT, f, indent=1, default=str)
    log("\nreport written")
