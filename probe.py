#!/usr/bin/env python3
"""Probe #75: how FirstCry blocks GitHub's runners, what its cart knows about
new ids, Majorette/Matchbox names, Hamleys, Minifygram fields, KND pace, and
which other Indian stores can be read."""
import json, os, re, sys, threading, time, traceback, urllib.request

T0 = time.time()
LOCK = threading.Lock()


def log(*a):
    with LOCK:
        print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


src = urllib.request.urlopen("https://raw.githubusercontent.com/Abhijndl/BotHW/main/bot.py", timeout=30).read()
open("bot_main.py", "wb").write(src)
sys.path.insert(0, ".")
import bot_main as B  # noqa: E402
from curl_cffi import requests as http  # noqa: E402

IMP = {"impersonate": "chrome124"}
HW_IDS = ["24999461", "24999404", "24961445", "24854851", "19991402", "24194169", "23033009",
          "24961454", "24892560", "24963176"]


# ── D/E/F: other stores, in the background (no FirstCry requests) ──────────────
SHOPIFY = ["toymarche.com", "krazycaterpillar.com", "zoomsters.in", "funcorp.in", "torquetribe.in",
           "303diecastshop.in", "toycra.com", "jaimantoys.com", "urbanmacaw.com", "sarvamshop.in",
           "www.karzanddolls.com", "minifygram.com", "thetoystore.in", "kiddiekingdom.in",
           "www.scalemodelsindia.com", "www.hobbyshop.in", "diecastmania.in", "www.toyzone.in",
           "www.miniaturetoyshop.com", "miniaturetoyshop.in", "www.diecastbazaar.com", "racingrevolution.in"]
WANT = re.compile(r"hot\s*-?\s*wheels?|mini\s*-?\s*gt|majorette|match\s*-?\s*box|kaido|tarmac|inno\s*64|pop\s*race|"
                  r"tomica|bburago|maisto|greenlight|m2\s*machines|johnny\s*lightning|cm\s*model", re.I)
CHASE = re.compile(r"chase|treasure|\bsth\b|super\s*th|limited|chaser|\$th", re.I)


def store_probe(dom):
    out = {"dom": dom}
    try:
        r = http.get(f"https://{dom}/products.json?limit=250", headers=B.COMMON_HEADERS, timeout=20, **IMP)
        out["status"] = r.status_code
        out["server"] = r.headers.get("server", "")
        if r.status_code != 200:
            out["head"] = r.text[:120].replace("\n", " ")
            return out
        prods = (r.json() or {}).get("products") or []
        pages = 1
        while len(prods) == 250 * pages and pages < 8:
            pages += 1
            r2 = http.get(f"https://{dom}/products.json?limit=250&page={pages}", headers=B.COMMON_HEADERS,
                          timeout=20, **IMP)
            if r2.status_code != 200:
                break
            prods += (r2.json() or {}).get("products") or []
        out["products"] = len(prods)
        rel = [p for p in prods if WANT.search(" ".join([p.get("title", ""), p.get("vendor", ""),
                                                         p.get("product_type", ""), " ".join(p.get("tags") or [])]))]
        ins = [p for p in rel if any(v.get("available") for v in p.get("variants") or [])]
        out["diecast"] = len(rel)
        out["diecast_in"] = len(ins)
        by = {}
        for p in rel:
            k = (WANT.search(" ".join([p.get("title", ""), p.get("vendor", "")])) or WANT.search(p.get("product_type", "") or "x") )
            k = (k.group(0).lower().replace(" ", "") if k else "?")
            by[k] = by.get(k, 0) + 1
        out["by"] = by
        out["newest"] = sorted((p.get("published_at") or p.get("created_at") or "")[:16] for p in rel)[-3:]
        out["chase"] = [p.get("title", "")[:70] for p in rel if CHASE.search(p.get("title", ""))][:8]
        out["sample_in"] = [p.get("title", "")[:60] for p in ins[:5]]
        try:
            c = http.get(f"https://{dom}/collections.json?limit=250", headers=B.COMMON_HEADERS, timeout=20, **IMP)
            cols = (c.json() or {}).get("collections") or [] if c.status_code == 200 else []
            out["cols"] = [x.get("handle") for x in cols
                           if re.search(r"hot|wheel|mini|gt|majorette|matchbox|chase|pre|new|arriv|drop|diecast|kaido|premium|sth|treasure",
                                        x.get("handle", ""), re.I)][:30]
        except Exception as e:
            out["cols"] = f"err {type(e).__name__}"
    except Exception as e:
        out["err"] = type(e).__name__ + " " + str(e)[:80]
    return out


def other_stores():
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(6) as ex:
            for o in ex.map(store_probe, SHOPIFY):
                log("[SHOP]", json.dumps(o, ensure_ascii=False))
        # WhipCrate (Odoo)
        for u in ("https://whipcrate1.odoo.com/shop", "https://www.whipcrate.com/shop", "https://whipcrate.com/shop"):
            try:
                r = http.get(u, headers=B.COMMON_HEADERS, timeout=20, **IMP)
                log("[ODOO]", u, r.status_code, len(r.text), len(re.findall(r"oe_product_cart", r.text)), "cards")
            except Exception as e:
                log("[ODOO]", u, type(e).__name__)
        # Hamleys
        for u in ("https://hamleys.in/", "https://www.hamleys.in/", "https://hamleys.in/brand/hot-wheels",
                  "https://hamleys.in/sitemap.xml", "https://hamleys.in/api/service/application/catalog/v1.0/products/?q=hot%20wheels",
                  "https://api.fynd.com/service/application/catalog/v1.0/products/?q=hot%20wheels"):
            try:
                r = http.get(u, headers=B.COMMON_HEADERS, timeout=20, **IMP)
                log("[HM]", u, r.status_code, r.headers.get("server", ""), r.headers.get("cf-ray", "")[:12],
                    r.text[:100].replace("\n", " "))
            except Exception as e:
                log("[HM]", u, type(e).__name__)
        # Minifygram row fields — and whether rows not yet live can be read
        try:
            h = B._mg_headers(B.MINIFYGRAM_ANON_KEY)
            base = f"{B.MINIFYGRAM_SUPABASE}/rest/v1/products"
            for q in ("select=*&order=created_at.desc&limit=3",
                      "select=id,name,brand,is_active,created_at,updated_at&is_active=eq.false&order=created_at.desc&limit=15",
                      "select=id,name,brand,is_active,created_at&order=created_at.desc&limit=15"):
                r = http.get(f"{base}?{q}", headers=h, timeout=20, **IMP)
                rows = r.json() if r.status_code == 200 else []
                if q.startswith("select=*"):
                    log("[MG] columns:", sorted(rows[0].keys()) if rows else r.text[:200])
                    for row in rows:
                        log("[MG] row:", json.dumps({k: v for k, v in row.items() if k not in ("description", "images",
                                                     "image_url", "gallery")}, ensure_ascii=False)[:700])
                else:
                    log(f"[MG] {q[:60]} → {r.status_code}:", json.dumps(rows, ensure_ascii=False)[:1500])
            for tbl in ("drops", "drop_schedule", "launches", "collections", "categories", "announcements", "banners"):
                r = http.get(f"{B.MINIFYGRAM_SUPABASE}/rest/v1/{tbl}?select=*&limit=3", headers=h, timeout=15, **IMP)
                log(f"[MG] table {tbl}: {r.status_code} {r.text[:300]}")
            t1 = time.time()
            wm = B.mg_watermark()
            log("[MG] watermark", wm, f"in {time.time() - t1:.2f}s")
        except Exception:
            log("[MG] failed", traceback.format_exc()[-400:])
        # KND pace: one fast shelf every 5 s, 6 times
        for i in range(6):
            t1 = time.time()
            try:
                r = http.get(B._KD + "/mini-gt/mini-gt", headers=B.COMMON_HEADERS, timeout=20, **IMP)
                log("[KD] shelf", i, r.status_code, len(r.text), f"{time.time() - t1:.2f}s")
            except Exception as e:
                log("[KD] shelf", i, type(e).__name__)
            time.sleep(max(0, 5 - (time.time() - t1)))
    except Exception:
        log("[OTHER] failed", traceback.format_exc()[-600:])


bg = threading.Thread(target=other_stores, daemon=True)
bg.start()


# ── A: FirstCry's cart (CSC.fcappservices.in) ─────────────────────────────────
def cart(ids):
    t1 = time.time()
    res = B.fc_cart_check(ids)
    return res, time.time() - t1


try:
    res, dt = cart(HW_IDS)
    log("[CART] known ids:", len(res or {}), f"{dt:.2f}s",
        json.dumps({k: (v.get("ok"), v.get("n"), v.get("name", "")[:40]) for k, v in (res or {}).items()}, ensure_ascii=False)[:900])
except Exception:
    log("[CART] failed", traceback.format_exc()[-500:])


def raw_cart(ids):
    """The cart's own answer for these ids: what comes back for each."""
    hdr = {**B.COMMON_HEADERS, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "Origin": "https://checkout.firstcry.com",
           "Referer": "https://checkout.firstcry.com/pay", **B._FC_CART_DEV}
    body = {"pro": "*".join(f"NO^{p}^1^0" for p in ids), "shipPin": "248001", "SiteType": 0, "LC": 0, "CR": 0,
            "Coupons": "", "FC_AUTH": "", "ShipMobile": "", "ShipPhone": "", "PayBack": "", "State": "",
            "PaymentType": "", "LPO": False, "LSD": False, "CCA": "", "LT": "N", "UA": hdr.get("User-Agent", ""),
            "AddressType": "Home", "AssemblyMap": "", "ptype": "", "pvalue": "", "FitKidChildIdMap": "",
            "CouponCodeToCheck": "", "GiftCodeToCheck": "", "BuyerType": "", "CardPar": "", "RemoveFreeErr": "",
            "redesign": True, "caller": "", "Ageid": "", "bmsm": "", "SegmentIDs": "", "latlong": "",
            "segmentcookie": "", "cardref": "", "savedCardBankCode": "", "savedCardIssuingBank": "", "cardtoken": ""}
    r = http.post(B.FC_CART_URL, data=json.dumps(body), headers=hdr, timeout=15, **IMP)
    if r.status_code != 200:
        return r.status_code, []
    x = r.json().get("LoadCartResult")
    while isinstance(x, str):
        x = json.loads(x)
    items = ((x or {}).get("pOrderSummary") or {}).get("PurchaseOrderItemList") or []
    return 200, items


try:
    for start in (24999400, 25000000, 25010000, 25020000, 25030000, 25040000, 25050000, 25060000, 25080000, 25100000):
        ids = [str(i) for i in range(start, start + 75)]
        st, items = raw_cart(ids)
        names = [(it.get("ProductID"), (it.get("ProductName") or "")[:45], it.get("CurrentStock"), it.get("warehouseid"),
                  it.get("BrandName") or it.get("Brand") or "") for it in items]
        log(f"[CART-IDS] {start}: HTTP {st}, {len(items)} of 75 known to the cart;", json.dumps(names[:6], ensure_ascii=False))
        if start == 24999400 and items:
            log("[CART-IDS] keys of one item:", sorted(items[0].keys()))
        time.sleep(0.5)
except Exception:
    log("[CART-IDS] failed", traceback.format_exc()[-500:])

try:
    codes = []
    t1 = time.time()
    for i in range(20):
        st, items = raw_cart(HW_IDS * 7)
        codes.append((st, len(items)))
        time.sleep(0.6)
    log(f"[CART-RATE] 20 calls in {time.time() - t1:.1f}s:", codes)
except Exception:
    log("[CART-RATE] failed", traceback.format_exc()[-300:])


# ── B/C: FirstCry www ─────────────────────────────────────────────────────────
HDR = {**B.COMMON_HEADERS, **B._FC_NOCACHE, "Accept": "application/json, text/javascript, */*; q=0.01",
       "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
       "Referer": B._FC_API_REFERER}
N = {"www": 0}


def www(url, sess=None, cookies=None, imp=IMP, label=""):
    N["www"] += 1
    t1 = time.time()
    try:
        g = sess.get if sess else http.get
        kw = {} if sess else imp
        r = g(url, headers=HDR, cookies=cookies, timeout=15, **kw)
    except Exception as e:
        return None, f"{type(e).__name__}", time.time() - t1, None
    ttl = None
    data = None
    if r.status_code == 200:
        try:
            data = B._fc_unwrap(r.json())
            ttl = data.get("TTL") if isinstance(data, dict) else None
        except Exception:
            pass
    return r, ttl, time.time() - t1, data


def ids_of(data):
    return [str(B._ci(p, *B._ID_KEYS)) for p in B._fc_api_products(data)] if data is not None else []


try:
    cookies = B._fc_cookies()
    log("[WWW] warm-up cookies:", sorted(cookies.keys()))
    first = None
    for pg in range(1, 10):
        r, ttl, dt, data = www(B._fc_bust(B._fc_api_query(pg, 20, {"OutOfStock": "1"})), cookies=cookies)
        st = r.status_code if r is not None else ttl
        log(f"[WWW] in-stock page {pg}: {st} ttl={ttl} items={len(ids_of(data))} {dt:.2f}s")
        if pg == 1:
            first = ids_of(data)
        time.sleep(0.3)

    # C: Majorette's names, Matchbox's brand id
    old = B.FC_API_BRAND
    B.FC_API_BRAND = "1335"
    names = []
    for pg in range(1, 10):
        r, ttl, dt, data = www(B._fc_bust(B._fc_api_query(pg, 20, {})), cookies=cookies)
        prods = B._fc_api_products(data) if data is not None else []
        names += [(str(B._ci(p, *B._ID_KEYS)), B._fc_name(str(B._ci(p, *B._NAME_KEYS) or "")), B._fc_api_stock(p)[1])
                  for p in prods]
        if len(prods) < 20:
            break
        time.sleep(0.3)
    B.FC_API_BRAND = old
    log(f"[MJ] Majorette list: {len(names)} cars")
    for pid, nm, n in names:
        if re.search(r"chase|limited|premium|deluxe|dtm|gt3|gt 3|motorsport|racing|porsche|collection|edition", nm, re.I):
            log(f"[MJ]   {pid} n={n} {nm[:90]}")
    for term in ("matchbox", "mini gt", "kaido house"):
        q = B._fc_api_query(1, 20, {"SearchString": term, "MasterBrand": ""})
        r, ttl, dt, data = www(B._fc_bust(q), cookies=cookies)
        prods = B._fc_api_products(data) if data is not None else []
        log(f"[SEARCH] {term!r}: {r.status_code if r is not None else ttl}, {len(prods)} items;",
            json.dumps([(B._ci(p, 'BId', 'BrandId', 'MBId', 'MasterBrandId'), B._ci(p, 'BNm'),
                         B._fc_name(str(B._ci(p, *B._NAME_KEYS) or ""))[:50]) for p in prods[:8]], ensure_ascii=False))
        time.sleep(0.3)

    # B2: which query changes give a fresh (uncached) answer
    tok = lambda: str(int(time.time() * 1000) % 1_000_000_000)
    base = B._fc_api_query(1, 20, {"OutOfStock": "1"})
    variants = {
        "plain": base,
        "searchrank": B._fc_api_query(1, 20, {"OutOfStock": "1", "searchrank": tok()}),
        "sorting": B._fc_api_query(1, 20, {"OutOfStock": "1", "sorting": tok()}),
        "PageNo=01": base.replace("PageNo=1&", "PageNo=01&"),
        "MasterBrand=0113": base.replace("MasterBrand=113", "MasterBrand=0113"),
        "pcode=0248001": base.replace("pcode=248001", "pcode=0248001"),
        "lowercase pageno": base.replace("PageNo=", "pageno="),
        "unknown param": base + "&zq=" + tok(),
        "Rating=": B._fc_api_query(1, 20, {"OutOfStock": "1", "Rating": tok()}),
        "Offer=": B._fc_api_query(1, 20, {"OutOfStock": "1", "Offer": tok()}),
        "skills=": B._fc_api_query(1, 20, {"OutOfStock": "1", "skills": tok()}),
        "PageSize=19": B._fc_api_query(1, 19, {"OutOfStock": "1"}),
        "SortExpression=NewArrivals": B._fc_api_query(1, 20, {"OutOfStock": "1", "SortExpression": "NewArrivals"}),
    }
    for k, u in variants.items():
        r, ttl, dt, data = www(B._fc_bust(u), cookies=cookies)
        got = ids_of(data)
        same = len(set(got) & set(first or [])) if first else None
        log(f"[FRESH] {k:28s} {r.status_code if r is not None else ttl} ttl={ttl!r} items={len(got)} same_as_plain={same}")
        time.sleep(0.4)

    # B3: steady pace until FirstCry objects
    t_block, n_ok = None, 0
    for i in range(80):
        r, ttl, dt, data = www(B._fc_bust(B._fc_api_query(1 + i % 9, 20, {"OutOfStock": "1"})), cookies=cookies)
        st = r.status_code if r is not None else ttl
        if st != 200:
            t_block = time.time()
            log(f"[PACE] request #{N['www']} → {st} after {n_ok} ok at 1 per 1.5 s;",
                "server:", r.headers.get("server", "") if r is not None else "",
                "| body:", (r.text[:300].replace("\n", " ") if r is not None else ""))
            if r is not None:
                log("[PACE] 403 headers:", {k: v for k, v in r.headers.items()
                                             if k.lower() in ("server", "akamai-grn", "x-akamai-session-info",
                                                              "set-cookie", "x-cache", "x-reference-error", "content-type")})
            break
        n_ok += 1
        time.sleep(1.5)
    else:
        log(f"[PACE] 80 requests at 1 per 1.5 s, no block")

    if t_block:
        tests = []
        r, ttl, dt, data = www(B._fc_bust(base), cookies=cookies)
        tests.append(("same session again", r.status_code if r is not None else ttl))
        s2 = http.Session(**IMP)
        s2.get(B._fc_bust(B._FC_API_REFERER), headers=B.COMMON_HEADERS, timeout=15)
        r = s2.get(B._fc_bust(base), headers=HDR, timeout=15)
        tests.append(("fresh session + warm-up", r.status_code))
        r = http.get(B._fc_bust(base), headers=HDR, timeout=15, impersonate="chrome120")
        tests.append(("no cookies, chrome120", r.status_code))
        r = http.get(B._fc_bust(base), headers=HDR, timeout=15, impersonate="safari17_0")
        tests.append(("no cookies, safari17", r.status_code))
        r = http.get(B._fc_bust("https://www.firstcry.com/hot-wheels/x/24999461/product-detail?fresh=1"),
                     headers=B.COMMON_HEADERS, timeout=15, **IMP)
        tests.append(("product page", r.status_code))
        r = http.get(B._fc_bust(base.replace("https://www.firstcry.com", "https://firstcry.com")), headers=HDR, timeout=15, **IMP)
        tests.append(("non-www host", r.status_code))
        for u in ("https://m.firstcry.com/", "https://cdn.fcglcdn.com/brainbees/images/n/fc_logo.png"):
            try:
                r = http.get(u, headers=B.COMMON_HEADERS, timeout=15, **IMP)
                tests.append((u, r.status_code))
            except Exception as e:
                tests.append((u, type(e).__name__))
        st, items = raw_cart(HW_IDS)
        tests.append(("cart host", st))
        log("[BLOCKED] while blocked:", tests)
        # how long it lasts
        for k in range(12):
            time.sleep(20)
            r, ttl, dt, data = www(B._fc_bust(base), cookies=cookies)
            st = r.status_code if r is not None else ttl
            log(f"[UNBLOCK] +{time.time() - t_block:.0f}s → {st}")
            if st == 200:
                break
except Exception:
    log("[WWW] failed", traceback.format_exc()[-800:])

bg.join(timeout=120)
log("done; www requests:", N["www"])
