#!/usr/bin/env python3
"""One-off research probe (not part of the bot). Measures how fresh FirstCry's
listing API is and which request variants defeat its 15-minute cache, finds the
product-page stock API, and inspects Karz & Dolls and Minifygram data feeds.
Writes probe_report.json + prints a readable report."""
import json, os, re, sys, time, random, traceback
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


# ───────────────────────────── FirstCry ─────────────────────────────
FC_API = "https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging"
KEYS = ["PageNo","PageSize","SortExpression","OnSale","SearchString","SubCatId","BrandId","Price","Age","Color","OptionalFilter","OutOfStock","Type1","Type2","Type3","Type4","Type5","Type6","Type7","Type8","Type9","Type10","Type11","Type12","Type13","Type14","Type15","combo","discount","searchwithincat","ProductidQstr","searchrank","pmonths","cgen","PriceQstr","DiscountQstr","sorting","MasterBrand","Rating","Offer","skills","material","curatedcollections","measurement","gender","exclude","premium","pcode","isclub","deliverytype","authors","booktype","character","collections","format","genre","booklanguage","publication","skill"]
DEF = {"PageNo": "1", "PageSize": "20", "SortExpression": "Popularity", "OnSale": "5",
       "SearchString": "brand", "MasterBrand": "113", "pcode": "248001", "isclub": "0"}
REF = "https://www.firstcry.com/hotwheels/5/0/113"
JH = {**H, "Accept": "application/json, text/javascript, */*; q=0.01",
      "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
      "Referer": REF}
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


def fc_get(over=None, extra="", nocache_headers=False):
    h = dict(JH)
    if nocache_headers:
        h.update({"Cache-Control": "no-cache, no-store, max-age=0", "Pragma": "no-cache"})
    u = fc_url(over, extra)
    t0 = time.time()
    try:
        r = http.get(u, headers=h, cookies=COOK, timeout=20, **IMP)
    except Exception as e:
        return {"err": type(e).__name__}
    ms = int((time.time() - t0) * 1000)
    st = r.headers.get("server-timing", "") or ""
    out = {"status": r.status_code, "ms": ms,
           "cdn": (re.findall(r"cdn-cache; desc=(\w+)", st) or [""])[0],
           "origin_ms": (re.findall(r"origin; dur=(\d+)", st) or [""])[0],
           "cc": r.headers.get("cache-control", ""), "age": r.headers.get("age", ""),
           "bytes": len(r.content)}
    try:
        j = unwrap(r.json())
    except Exception:
        out["body"] = r.text[:200]
        return out
    ps = prods(j)
    out.update({"ttl": j.get("TTL") if isinstance(j, dict) else None, "n": len(ps),
                "zero": sum(1 for p in ps if str(p.get("CrntStock")) in ("0", "0.0")),
                "pids": [str(p.get("PId")) for p in ps],
                "stock": {str(p.get("PId")): p.get("CrntStock") for p in ps},
                "keys": sorted(ps[0].keys()) if ps else [],
                "top": list(j.keys())[:10] if isinstance(j, dict) else []})
    if ps and not REPORT.get("_fc_sample"):
        REPORT["_fc_sample"] = {k: (str(v)[:200]) for k, v in ps[0].items()}
    return out


def brief(x):
    return {k: x.get(k) for k in ("status", "ms", "ttl", "cdn", "origin_ms", "cc", "n", "zero", "err", "body")}


@section("fc_cache")
def fc_cache():
    res = {}
    base = fc_get()
    res["base1"] = brief(base); log("base1", res["base1"])
    time.sleep(3)
    b2 = fc_get(); res["base2"] = brief(b2); log("base2", res["base2"])
    bb = fc_get(extra=f"&_={int(time.time()*1000)}", nocache_headers=True)
    res["bot_style_buster"] = brief(bb); log("bot-style (_=ms + no-cache hdrs)", res["bot_style_buster"])
    variants = {
        "sort_lower": ({"SortExpression": "popularity"}, ""),
        "sort_upper": ({"SortExpression": "POPULARITY"}, ""),
        "sort_mixed": ({"SortExpression": "PoPuLaRiTy"}, ""),
        "sort_mixed2": ({"SortExpression": "pOpUlArItY"}, ""),
        "pcode_pad": ({"pcode": "0248001"}, ""),
        "pcode_pad2": ({"pcode": "00248001"}, ""),
        "extra_nc": ({}, f"&nc={random.randint(1, 10**9)}"),
        "searchrank": ({"searchrank": str(random.randint(1, 999))}, ""),
        "sorting": ({"sorting": str(random.randint(1, 999))}, ""),
        "pagesize21": ({"PageSize": "21"}, ""),
        "pagesize25": ({"PageSize": "25"}, ""),
        "pagesize19": ({"PageSize": "19"}, ""),
        "isclub_pad": ({"isclub": "00"}, ""),
        "onsale_pad": ({"OnSale": "05"}, ""),
        "masterbrand_pad": ({"MasterBrand": "0113"}, ""),
        "searchstring_Brand": ({"SearchString": "Brand"}, ""),
    }
    bset = set(base.get("pids") or [])
    for name, (over, extra) in variants.items():
        x = fc_get(over, extra)
        same = len(bset & set(x.get("pids") or []))
        diff_stock = sum(1 for p, s in (x.get("stock") or {}).items()
                         if p in (base.get("stock") or {}) and str(base["stock"][p]) != str(s))
        res[name] = {**brief(x), "overlap_with_base_p1": same, "stock_diff_vs_base": diff_stock}
        log(name, res[name])
        # repeat immediately: does the SAME variant now come back cached (ttl lower)?
        if name in ("sort_mixed", "extra_nc", "pcode_pad", "pagesize21"):
            time.sleep(2)
            y = fc_get(over, extra)
            res[name + "_repeat"] = brief(y); log(name + "_repeat", res[name + "_repeat"])
        time.sleep(0.4)
    return res


@section("fc_filters")
def fc_filters():
    res = {}
    for v in ["1", "0", "true", "false", "Y", "N", "2", "yes", "no"]:
        x = fc_get({"OutOfStock": v, "SortExpression": "pOPULARITY"})
        res["OutOfStock=" + v] = brief(x); log("OutOfStock=" + v, res["OutOfStock=" + v])
        time.sleep(0.3)
    for v in ["NewArrivals", "newarrivals", "New", "Latest", "NewArrival", "new", "Discount",
              "PriceLowToHigh", "PriceHighToLow", "Rating", "BestSeller", "Bestseller"]:
        x = fc_get({"SortExpression": v})
        res["sort=" + v] = {**brief(x), "first8": (x.get("pids") or [])[:8]}
        log("sort=" + v, res["sort=" + v])
        time.sleep(0.3)
    # ProductidQstr: can it fetch arbitrary ids?
    for v in ["23351189", "23351189,23353034,23353037", "23351189|23353034"]:
        x = fc_get({"ProductidQstr": v, "SortExpression": "PoPuLARITY"})
        res["ProductidQstr=" + v] = {**brief(x), "first8": (x.get("pids") or [])[:8]}
        log("ProductidQstr=" + v, res["ProductidQstr=" + v])
    return res


def sweep(over, label, size=20, maxpages=30):
    """Full catalogue sweep with a given variant; returns per-page stats."""
    pages = {}
    def one(p):
        o = dict(over); o["PageNo"] = str(p); o["PageSize"] = str(size)
        return p, fc_get(o)
    page = 1
    allp = {}
    while page <= maxpages:
        batch = list(range(page, min(page + 10, maxpages + 1)))
        with ThreadPoolExecutor(10) as ex:
            for p, x in ex.map(one, batch):
                pages[p] = x
        stop = False
        for p in batch:
            x = pages[p]
            for pid, s in (x.get("stock") or {}).items():
                allp.setdefault(pid, s)
            if (x.get("n") or 0) < size:
                stop = True
        if stop:
            break
        page += 10
    stats = {p: {"n": x.get("n"), "zero": x.get("zero"), "ttl": x.get("ttl"), "cdn": x.get("cdn"),
                 "ms": x.get("ms")} for p, x in sorted(pages.items())}
    return {"label": label, "unique": len(allp), "instock": sum(1 for s in allp.values() if str(s) not in ("0", "0.0")),
            "pages": stats, "stock": allp}


@section("fc_sweeps")
def fc_sweeps():
    res = {}
    a = sweep({"SortExpression": "pOpUlArItY"}, "fresh_variant")
    log("fresh sweep: unique", a["unique"], "instock", a["instock"])
    for p, s in a["pages"].items():
        log("  page", p, s)
    b = sweep({}, "baseline_cached")
    log("baseline sweep: unique", b["unique"], "instock", b["instock"])
    for p, s in b["pages"].items():
        log("  page", p, s)
    diffs = []
    for pid in set(a["stock"]) | set(b["stock"]):
        sa, sb = a["stock"].get(pid), b["stock"].get(pid)
        if str(sa) != str(sb):
            diffs.append((pid, sb, sa))
    log("stock differences baseline(cached) -> fresh:", len(diffs), diffs[:40])
    res["fresh"] = {k: v for k, v in a.items() if k != "stock"}
    res["baseline"] = {k: v for k, v in b.items() if k != "stock"}
    res["diffs"] = diffs
    # in-stock-first ordering check
    return res


@section("fc_watch")
def fc_watch():
    """Watch page 1-3 of a fresh variant vs the cached baseline for ~4 minutes."""
    res = []
    prev_f, prev_b = {}, {}
    t_end = time.time() + float(os.getenv("WATCH_SECONDS", "240"))
    i = 0
    while time.time() < t_end:
        i += 1
        variant = "".join(c.upper() if random.random() < 0.5 else c.lower() for c in "popularity")
        f = {}
        b = {}
        for p in (1, 2, 3):
            xf = fc_get({"SortExpression": variant, "PageNo": str(p)})
            xb = fc_get({"PageNo": str(p)})
            f.update(xf.get("stock") or {}); b.update(xb.get("stock") or {})
        ch_f = {k: (prev_f.get(k), v) for k, v in f.items() if k in prev_f and str(prev_f[k]) != str(v)}
        ch_b = {k: (prev_b.get(k), v) for k, v in b.items() if k in prev_b and str(prev_b[k]) != str(v)}
        row = {"t": time.strftime("%H:%M:%S", time.gmtime()), "fresh_changes": ch_f, "cached_changes": ch_b,
               "ttl_f": xf.get("ttl"), "ttl_b": xb.get("ttl")}
        res.append(row)
        log(row)
        prev_f, prev_b = f, b
        time.sleep(20)
    return res


@section("fc_pdp")
def fc_pdp():
    """Find the product page's stock API: fetch a PDP, list scripts/endpoints."""
    res = {}
    url = "https://www.firstcry.com/hot-wheels/hot-wheels-free-wheel-die-cast-mailed-it-168-250-toy-car-blue/23074884/product-detail"
    r = SESS.get(url, headers=H, timeout=25)
    t = r.text
    res["status"] = r.status_code; res["bytes"] = len(t)
    res["cc"] = r.headers.get("cache-control"); res["server_timing"] = r.headers.get("server-timing")
    res["has_add_to_cart"] = "ADD TO CART" in t.upper(); res["has_notify"] = "NOTIFY" in t.upper()
    res["mentions"] = sorted(set(re.findall(r"(/svcs/[A-Za-z0-9_./]+|/api/[A-Za-z0-9_./-]+|https?://[a-z0-9.-]*fcappservices\.in/[A-Za-z0-9_./-]+)", t)))[:80]
    res["stock_words"] = sorted(set(m.group(0)[:120] for m in re.finditer(r"[A-Za-z_]*(?:[Ss]tock|Qty|qty|Inventory)[A-Za-z_]*\W{0,4}[:=]\W{0,3}[^,;}\s]{0,40}", t)))[:60]
    res["product_id_hits"] = len(re.findall("23074884", t))
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', t)
    res["scripts"] = scripts[:60]
    eps = Counter()
    for s in scripts:
        u = urljoin(url, s)
        if not any(x in u for x in ("firstcry", "fcglcdn", "brainbees")):
            continue
        try:
            js = http.get(u, headers=H, timeout=20, **IMP).text
        except Exception:
            continue
        for m in re.finditer(r"""["'`]((?:https?://[a-z0-9.-]+)?/(?:svcs|api)/[A-Za-z0-9_./-]{3,120})""", js):
            eps[m.group(1)] += 1
        for m in re.finditer(r"""["'`](https?://[a-z0-9.-]*(?:fcappservices\.in|firstcry\.com)/[A-Za-z0-9_./-]{3,120})""", js):
            eps[m.group(1)] += 1
    res["endpoints_in_js"] = eps.most_common(150)
    for e, c in eps.most_common(150):
        log("  ep", c, e)
    for k in ("status", "bytes", "cc", "server_timing", "has_add_to_cart", "has_notify", "product_id_hits"):
        log(k, res[k])
    log("mentions", res["mentions"])
    log("stock_words", res["stock_words"])
    return res


# ───────────────────────────── Minifygram ─────────────────────────────
MG = "https://seoqlgtbygddyehugjwv.supabase.co"
MG_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNlb3FsZ3RieWdkZHllaHVnand2Iiwicm9sZSI6"
          "ImFub24iLCJpYXQiOjE3NzcxMzEwNzgsImV4cCI6MjA5MjcwNzA3OH0.TxGeE5sXW2zivw6xhJ7TIAWibGxiPzv4wcmaEihUsqY")
MGH = {**H, "apikey": MG_KEY, "Authorization": f"Bearer {MG_KEY}", "Accept": "application/json"}


@section("mg")
def mg():
    res = {}
    for tbl, sel in (("categories", "id,name,slug,sort_order,is_visible"),
                     ("brands", "id,name,sort_order,display_label,is_visible,category_id")):
        r = http.get(f"{MG}/rest/v1/{tbl}?select={sel}", headers=MGH, timeout=20, **IMP)
        res[tbl] = r.json() if r.status_code == 200 else {"status": r.status_code, "body": r.text[:300]}
        log(tbl, json.dumps(res[tbl])[:3000])
    t0 = time.time()
    r = http.get(f"{MG}/rest/v1/products?select=id,slug,name,brand,scale,category,condition,price_inr,mrp_inr,"
                 f"booking_amount_inr,product_type,badge,arrival_date,preorder_close_at,preorder_status,"
                 f"is_active,updated_at,created_at,product_skus!product_skus_product_id_fkey(available)"
                 f"&is_active=eq.true&limit=2000", headers=MGH, timeout=30, **IMP)
    res["products_ms"] = int((time.time() - t0) * 1000)
    res["products_headers"] = {k: v for k, v in r.headers.items() if k.lower() in (
        "cache-control", "age", "x-cache", "cf-cache-status", "content-range", "content-type", "server", "date")}
    rows = r.json() if r.status_code == 200 else []
    if r.status_code != 200:
        log("products error", r.status_code, r.text[:300])
        # retry without created_at in case the column doesn't exist
        r = http.get(f"{MG}/rest/v1/products?select=id,slug,name,brand,scale,category,price_inr,mrp_inr,"
                     f"booking_amount_inr,product_type,badge,preorder_close_at,preorder_status,is_active,updated_at,"
                     f"product_skus!product_skus_product_id_fkey(available)&is_active=eq.true&limit=2000",
                     headers=MGH, timeout=30, **IMP)
        rows = r.json() if r.status_code == 200 else []
    res["n_active"] = len(rows)
    res["category"] = Counter(str(x.get("category")) for x in rows).most_common()
    res["brand"] = Counter(str(x.get("brand")) for x in rows).most_common()
    res["product_type"] = Counter(str(x.get("product_type")) for x in rows).most_common()
    res["preorder_status"] = Counter(str(x.get("preorder_status")) for x in rows).most_common()
    res["badge"] = Counter(str(x.get("badge")) for x in rows).most_common(20)
    cards = [x for x in rows if re.search(r"card|tcg|pok[eé]mon|booster|trading", " ".join(
        str(x.get(k) or "") for k in ("name", "category", "brand", "product_type", "slug")), re.I)]
    res["card_like"] = [{k: x.get(k) for k in ("name", "brand", "category", "product_type", "price_inr",
                                               "preorder_status", "badge", "slug", "product_skus")} for x in cards][:60]
    res["preorders"] = [{k: x.get(k) for k in ("name", "brand", "category", "product_type", "price_inr",
                                               "booking_amount_inr", "preorder_status", "preorder_close_at",
                                               "slug", "product_skus")} for x in rows
                        if str(x.get("product_type")) == "preorder"][:40]
    newest = sorted(rows, key=lambda x: str(x.get("created_at") or x.get("updated_at") or ""), reverse=True)[:25]
    res["newest"] = [{k: x.get(k) for k in ("name", "brand", "category", "product_type", "created_at",
                                            "updated_at", "product_skus")} for x in newest]
    for k in ("products_ms", "products_headers", "n_active", "category", "brand", "product_type",
              "preorder_status", "badge"):
        log(k, res[k])
    log("card_like", json.dumps(res["card_like"], ensure_ascii=False)[:4000])
    log("preorders", json.dumps(res["preorders"], ensure_ascii=False)[:3000])
    log("newest", json.dumps(res["newest"], ensure_ascii=False)[:3000])
    # inactive products: are sold-out items set inactive?
    r2 = http.get(f"{MG}/rest/v1/products?select=id,name,brand,category,product_type,is_active,updated_at"
                  f"&is_active=eq.false&limit=50&order=updated_at.desc", headers=MGH, timeout=20, **IMP)
    res["inactive_sample"] = r2.json() if r2.status_code == 200 else {"status": r2.status_code, "body": r2.text[:200]}
    log("inactive_sample", json.dumps(res["inactive_sample"], ensure_ascii=False)[:1500])
    return res


# ───────────────────────────── Karz & Dolls ─────────────────────────────
KD = "https://www.karzanddolls.com"


@section("kd")
def kd():
    res = {}
    for path in ("/", "/hot-wheels/mainlines", "/mini-gt/mini-gt", "/specials/chase-car",
                 "/specials/special-stocks-64-43-scale", "/hot-wheels/car-culture"):
        u = KD + path
        out = {}
        for attempt in (1, 2):
            t0 = time.time()
            r = http.get(u, headers=H, timeout=30, **IMP)
            t = r.text
            out[f"try{attempt}"] = {
                "status": r.status_code, "ms": int((time.time() - t0) * 1000), "bytes": len(t),
                "hdr": {k: v for k, v in r.headers.items() if k.lower() in (
                    "cache-control", "age", "x-nextjs-cache", "x-vercel-cache", "cf-cache-status", "x-cache",
                    "server", "x-powered-by", "etag", "last-modified", "x-nextjs-prerender", "vary")},
                "details_links": len(set(re.findall(r'/details/[^"\'\s<>]+', t))),
                "showing": (re.findall(r"Showing\s*\d+\s*out\s*of\s*\d+", t) or [""])[0],
                "next_data": "__NEXT_DATA__" in t, "rsc": "self.__next_f" in t,
                "new_arrival": t.upper().count("NEW ARRIVAL"),
                "sold_out": t.upper().count("SOLD OUT") + t.upper().count("OUT OF STOCK"),
            }
            time.sleep(4)
        if path == "/":
            apis = sorted(set(re.findall(r'https?://[a-z0-9.-]+\.[a-z]{2,}/[A-Za-z0-9_./-]*api[A-Za-z0-9_./-]*', t)))[:40]
            out["api_mentions"] = apis
            m = re.search(r'"buildId":"([^"]+)"', t)
            out["buildId"] = m.group(1) if m else None
            scripts = re.findall(r'<script[^>]+src="([^"]+)"', t)
            out["scripts"] = scripts[:40]
            eps = Counter()
            for s in scripts[:25]:
                try:
                    js = http.get(urljoin(KD, s), headers=H, timeout=20, **IMP).text
                except Exception:
                    continue
                for m2 in re.finditer(r"""["'`](https?://[a-z0-9.-]+(?:\.[a-z]{2,})+(?:/[A-Za-z0-9_./-]{0,100})?)""", js):
                    if any(x in m2.group(1) for x in ("karz", "api", "backend", "admin", "cms")):
                        eps[m2.group(1)] += 1
                for m2 in re.finditer(r"""["'`](/api/[A-Za-z0-9_./-]{2,100})""", js):
                    eps[m2.group(1)] += 1
            out["endpoints_in_js"] = eps.most_common(80)
            # stock signal inside RSC payload?
            out["rsc_stock_words"] = sorted(set(re.findall(r'\\?"(?:stock|qty|quantity|inStock|in_stock|available|stockStatus|stock_status)\\?":\s*\\?"?[A-Za-z0-9_.-]{0,20}', t)))[:30]
        res[path] = out
        log(path, json.dumps(out)[:3000])
    return res


if __name__ == "__main__":
    for fn in (fc_cache, fc_filters, fc_sweeps, fc_pdp, mg, kd, fc_watch):
        fn()
    REPORT["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("probe_report.json", "w") as f:
        json.dump(REPORT, f, indent=1, default=str)
    log("\nreport written")
