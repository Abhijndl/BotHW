#!/usr/bin/env python3
"""Probe #34: chase lines beyond Hot Wheels mainline — Matchbox, Majorette and
Hot Wheels Monster Trucks. What each store lists, how chase pieces are named,
and FirstCry's brand ids for Matchbox / Majorette. Read-only: no Telegram, no
seen.json writes, nothing added to any cart."""
import collections, importlib.util, json, os, re, time, traceback
from urllib.parse import quote

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "FC_CART": "false"})
spec = importlib.util.spec_from_file_location("bot_v172", os.path.join(ROOT, "bot_v172.py"))
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)
http, IMP, H = bot.http, bot._IMPERSONATE, bot.COMMON_HEADERS
REPORT = {}
CHASE = re.compile(r"chase|super\s*chase|treasure|\bsth\b|\bth\b|limited|zamac|raw|gold|"
                   r"rubber|real riders|special edition|exclusive|premium|collector", re.I)


def get(url, **kw):
    kw.setdefault("headers", H)
    kw.setdefault("timeout", 25)
    return http.get(url, **kw, **IMP)


def section(name):
    def deco(fn):
        def run():
            print(f"\n{'=' * 20} {name} {'=' * 20}")
            t0 = time.time()
            try:
                fn()
            except Exception:
                traceback.print_exc()
            print(f"--- {name}: {time.time() - t0:.1f}s")
        run.__name__ = fn.__name__
        return run
    return deco


# ── FirstCry ──────────────────────────────────────────────────────────────────
def fc_api(extra, pages=40, label=""):
    hdr = {**H, **bot._FC_NOCACHE, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
           "Referer": bot._FC_API_REFERER}
    ck = bot._fc_cookies()
    prods, first_keys, errs = {}, None, []
    for pg in range(1, pages + 1):
        url = bot._fc_api_query(pg, 20, extra)
        try:
            r = http.get(bot._fc_bust(url), headers=hdr, cookies=ck, timeout=20, **IMP)
        except Exception as e:
            errs.append(f"{pg}:{type(e).__name__}")
            break
        if r.status_code != 200:
            errs.append(f"{pg}:HTTP {r.status_code}")
            break
        try:
            data = bot._fc_unwrap(r.json())
        except Exception:
            errs.append(f"{pg}:not json {r.text[:120]!r}")
            break
        its = bot._fc_api_products(data)
        if pg == 1 and its:
            first_keys = sorted(its[0].keys())
        for p in its:
            pid = str(bot._ci(p, *bot._ID_KEYS) or "")
            if pid:
                prods[pid] = p
        if len(its) < 20:
            break
    rows = []
    for pid, p in prods.items():
        st, cnt = bot._fc_api_stock(p)
        rows.append({"pid": pid, "name": bot._fc_name(str(bot._ci(p, *bot._NAME_KEYS) or "")),
                     "stock": st, "count": cnt, "bnm": str(bot._ci(p, "BNm") or ""),
                     "cat": f"{bot._ci(p, 'CNm') or ''} / {bot._ci(p, 'SCNm') or ''}",
                     "mrp": bot._ci(p, "MRP"), "brand_fields": {k: p[k] for k in p if "b" in k.lower()
                                                               and len(str(p[k])) < 40}})
    ins = sum(1 for x in rows if (x["count"] or 0) > 0)
    print(f"[FC-API {label}] {extra} → {len(rows)} products, {ins} with stock, errors {errs}")
    if first_keys:
        print(f"   record keys: {first_keys}")
    if rows:
        print(f"   brand names: {collections.Counter(x['bnm'] for x in rows).most_common(8)}")
        print(f"   categories: {collections.Counter(x['cat'] for x in rows).most_common(8)}")
        print(f"   brand fields of #1: {rows[0]['brand_fields']}")
    return rows


@section("FirstCry: find Matchbox / Majorette brand ids")
def fc_brands():
    found = collections.defaultdict(set)
    pages = {}
    for term in ("matchbox", "majorette", "hot wheels monster trucks", "monster trucks"):
        pages[f"search:{term}"] = bot._FC_SEARCH + quote(term)
    for slug in ("matchbox", "majorette"):
        pages[f"brand:{slug}"] = f"https://www.firstcry.com/{slug}"
    out = {}
    for label, u in pages.items():
        try:
            r = get(bot._fc_bust(u), headers={**H, **bot._FC_NOCACHE})
        except Exception as e:
            print(f"{label}: {type(e).__name__}")
            continue
        t = r.text
        print(f"\n{label}: HTTP {r.status_code}, {len(t)} bytes, final {getattr(r, 'url', '')}")
        links = set(re.findall(r"firstcry\.com/([a-z0-9\-]+)/(\d+)/(\d+)/(\d+)", t, re.I))
        rel = [l for l in links if any(k in l[0].lower() for k in ("matchbox", "majorette", "monster", "hot"))]
        print(f"   brand-style links: {sorted(rel)[:20]}")
        for l in rel:
            found[l[0].lower()].add(l[3])
        for pat in (r"MasterBrand=(\d+)", r"brand=(\d+)", r"[\"']?brandid[\"']?\s*[:=]\s*[\"']?(\d+)",
                    r"[\"']?bid[\"']?\s*[:=]\s*[\"']?(\d+)", r"masterbrand[\"']?\s*[:=]\s*[\"']?(\d+)"):
            ms = collections.Counter(re.findall(pat, t, re.I))
            if ms:
                print(f"   {pat}: {ms.most_common(8)}")
        for k in ("matchbox", "majorette"):
            for m in list(re.finditer(k, t, re.I))[:3]:
                s = t[max(0, m.start() - 150): m.end() + 150].replace("\n", " ")
                if re.search(r"\d{2,}", s):
                    print(f"   ctx[{k}]: …{s}…")
        cards = [(m.group(1), bot._fc_name(m.group(2))) for m in bot._FC_IMG.finditer(t)]
        cards += [(m.group(2), bot._fc_name(m.group(1))) for m in bot._FC_IMG_ALT.finditer(t)]
        print(f"   {len(cards)} product cards; first: {cards[:12]}")
        out[label] = {"status": r.status_code, "links": sorted(rel), "cards": cards[:60]}
    REPORT["fc_pages"] = out
    REPORT["fc_brand_ids"] = {k: sorted(v) for k, v in found.items()}
    print(f"\nbrand ids found: {REPORT['fc_brand_ids']}")


@section("FirstCry: listing API per brand + keyword search")
def fc_lines():
    ids = REPORT.get("fc_brand_ids") or {}
    cands = set()
    for k, v in ids.items():
        if "matchbox" in k or "majorette" in k:
            cands |= set(v)
    res = {}
    for bid in sorted(cands):
        rows = fc_api({"MasterBrand": bid}, label=f"brand {bid}")
        res[f"brand_{bid}"] = rows
        for x in rows:
            if CHASE.search(x["name"]):
                print(f"   ⛓ {x['pid']} {x['stock']}/{x['count']} {x['name'][:110]}")
        for x in sorted(rows, key=lambda x: -(x["count"] or 0))[:25]:
            print(f"   · {x['pid']} {x['count']} ₹{x['mrp']} {x['name'][:100]}")
    # keyword search through the same API (what the search page might call)
    for term in ("matchbox", "majorette"):
        for extra in ({"SearchString": term, "MasterBrand": ""},
                      {"SearchString": term, "MasterBrand": "", "searchwithincat": term}):
            rows = fc_api(extra, pages=3, label=f"search {term}")
            res[f"search_{term}_{len(extra)}"] = rows[:60]
            for x in rows[:10]:
                print(f"   · {x['pid']} {x['count']} {x['bnm']} {x['name'][:90]}")
    REPORT["fc_lines"] = res


@section("FirstCry: Hot Wheels (113) monster trucks and chase words")
def fc_hw():
    rows = fc_api({}, label="hot wheels 113")
    mon = [x for x in rows if "monster" in x["name"].lower()]
    print(f"monster names: {len(mon)} ({sum(1 for x in mon if (x['count'] or 0) > 0)} with stock)")
    print(f"   categories: {collections.Counter(x['cat'] for x in mon).most_common(6)}")
    for x in sorted(mon, key=lambda x: -(x["count"] or 0)):
        print(f"   🚚 {x['pid']} {x['count']} ₹{x['mrp']} excl={bot._fc_excluded(x['name'])} {x['name'][:105]}")
    ch = [x for x in rows if re.search(r"chase|treasure|\bsth\b|\bth\b|zamac", x["name"], re.I)]
    print(f"\nchase/TH words in 113 names: {len(ch)}")
    for x in ch:
        print(f"   ⛓ {x['pid']} {x['count']} {x['name'][:110]}")
    REPORT["fc_monster"] = mon
    REPORT["fc_hw_chase_words"] = ch


# ── Minifygram ────────────────────────────────────────────────────────────────
@section("Minifygram: brands, badges, Matchbox / Majorette / monster / chase")
def mg():
    sel = ("id,slug,name,brand,scale,category,price_inr,mrp_inr,product_type,badge,is_active,"
           "updated_at,preorder_status,product_skus!product_skus_product_id_fkey(available)")
    rows = []
    for active in ("&is_active=eq.true", ""):
        u = (f"{bot.MINIFYGRAM_SUPABASE}/rest/v1/products?select={quote(sel, safe=',!()')}"
             f"{active}&limit=5000")
        r = get(u, headers=bot._mg_headers(bot.MINIFYGRAM_ANON_KEY))
        print(f"products{active or ' (all)'}: HTTP {r.status_code}")
        if r.status_code == 200:
            rows = r.json()
            break
    print(f"{len(rows)} rows")
    for x in rows:
        sk = x.get("product_skus") or []
        x["avail"] = sum((s.get("available") or 0) for s in sk if isinstance(s, dict)) if sk else None
    print("brands:", collections.Counter(str(x.get("brand")) for x in rows).most_common(70))
    print("categories:", collections.Counter(str(x.get("category")) for x in rows).most_common(30))
    print("badges:", collections.Counter(str(x.get("badge")) for x in rows).most_common(30))
    print("types:", collections.Counter(str(x.get("product_type")) for x in rows).most_common(10))
    keep = {}
    for k in ("matchbox", "majorette", "monster"):
        hit = [x for x in rows if k in (str(x.get("brand")) + " " + str(x.get("name"))).lower()]
        keep[k] = hit
        print(f"\n{k}: {len(hit)} rows ({sum(1 for x in hit if (x['avail'] or 0) > 0)} available)")
        for x in hit[:60]:
            print(f"   {x.get('brand')!s:14} | {x.get('category')!s:12} | {x.get('badge')!s:10} | "
                  f"{x.get('product_type')!s:8} | {x['avail']} | ₹{x.get('price_inr')} | {x.get('name')!s:.90}")
    ch = [x for x in rows if re.search(r"chase|treasure|\bsth\b|\bth\b|zamac|limited", str(x.get("name")) + " "
                                         + str(x.get("badge")), re.I)]
    print(f"\nchase-ish names/badges, all brands: {len(ch)}")
    for x in ch[:120]:
        print(f"   {x.get('brand')!s:14} | {x.get('badge')!s:10} | {x['avail']} | {x.get('name')!s:.100}")
    keep["chase"] = ch
    REPORT["mg"] = {k: [{kk: x.get(kk) for kk in ("id", "slug", "name", "brand", "category", "badge",
                                                    "product_type", "avail", "price_inr", "updated_at")}
                        for x in v] for k, v in keep.items()}
    REPORT["mg_brands"] = collections.Counter(str(x.get("brand")) for x in rows).most_common(200)


# ── Karz & Dolls ──────────────────────────────────────────────────────────────
def kd_products(page):
    m = bot._KD_NEXT.search(page)
    if not m:
        return None
    props = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
    found, stack = [], [props]
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            if "pid" in n and "pro_name" in n:
                found.append(n)
            else:
                stack.extend(n.values())
    return found


@section("Karz & Dolls: menu, chase shelf, Matchbox / Majorette / monster pages")
def kd():
    r = get(bot._KD + "/")
    home = r.text
    links = sorted(set(re.findall(r'href="(/[a-z0-9\-]+/[a-z0-9\-]+)"', home)) - {""})
    links = [l for l in links if not l.startswith("/details/")]
    print(f"home: HTTP {r.status_code}, {len(home)} bytes, {len(links)} category links")
    print("   ", links)
    m = bot._KD_NEXT.search(home)
    menu = []
    if m:
        blob = m.group(1)
        for k in ("matchbox", "majorette", "monster", "chase"):
            for mm in list(re.finditer(k, blob, re.I))[:6]:
                print(f"   json ctx[{k}]: …{blob[max(0, mm.start() - 120): mm.end() + 120]}…")
        menu = sorted(set(re.findall(r'"(?:slug|url|link|cat_slug|category_slug)"\s*:\s*"([^"]{3,80})"', blob)))
        print(f"   slugs in __NEXT_DATA__: {menu[:200]}")
    REPORT["kd_links"] = links
    REPORT["kd_slugs"] = menu
    targets = [bot._KD + "/specials/chase-car"]
    targets += [bot._KD + l for l in links if re.search(r"matchbox|majorette|monster|chase", l, re.I)]
    for u in (bot._KD + "/matchbox", bot._KD + "/majorette", bot._KD + "/hot-wheels/monster-trucks",
              bot._KD + "/matchbox/matchbox", bot._KD + "/majorette/majorette"):
        if u not in targets:
            targets.append(u)
    pages = {}
    for u in targets:
        try:
            r = get(u)
        except Exception as e:
            print(f"{u}: {type(e).__name__}")
            continue
        prods = kd_products(r.text) if r.status_code == 200 else None
        print(f"\n{u}: HTTP {r.status_code}, {len(r.text)} bytes, products {None if prods is None else len(prods)}")
        rows = []
        for p in prods or []:
            rows.append({k: p.get(k) for k in ("pid", "pro_name", "product_sname", "sku", "in_stock",
                                               "is_preorder", "dis_price", "act_price", "slug", "brand",
                                               "brand_name", "cat_name", "category")})
        for x in rows[:80]:
            print(f"   {x['in_stock']} | ₹{x['dis_price']}/{x['act_price']} | {str(x['product_sname'])[:28]:28} | "
                  f"{str(x['pro_name'])[:90]}")
        if prods:
            print(f"   keys of #1: {sorted(prods[0].keys())}")
        pages[u] = rows
    REPORT["kd_pages"] = pages


# ── Hamleys ───────────────────────────────────────────────────────────────────
@section("Hamleys: Matchbox / Majorette / monster trucks / chase")
def hm():
    sess = bot._hm_session()
    tok, app = bot._hm_app_creds(sess)
    hdr = {**H, "Accept": "application/json, text/plain, */*", "x-currency-code": "INR",
           "Referer": "https://hamleys.in/brand/hot-wheels"}
    if tok:
        hdr["x-fp-api-key"] = tok
    if app:
        hdr["x-application-id"] = app
    base = "https://hamleys.in/api/service/application/catalog/v1.0/products/"
    res = {}
    for label, q in (("brand matchbox", "f=brand%3Amatchbox"), ("brand majorette", "f=brand%3Amajorette"),
                     ("q matchbox", "q=matchbox"), ("q majorette", "q=majorette"),
                     ("q monster truck", "q=monster%20truck"), ("q chase", "q=chase")):
        out, pid, pages = [], "*", 0
        while pages < 6:
            u = f"{base}?{q}&filters=false&page_size=100&page_id={quote(pid, safe='*')}"
            r = (sess.get(u, headers=hdr, timeout=25) if sess else get(u, headers=hdr))
            if r.status_code != 200:
                print(f"{label}: HTTP {r.status_code}")
                break
            d = r.json()
            for it in d.get("items") or []:
                out.append({"slug": it.get("slug"), "name": it.get("name"),
                            "brand": (it.get("brand") or {}).get("name"), "sellable": it.get("sellable")})
            pg = d.get("page") or {}
            if not (pg.get("has_next") and pg.get("next_id")):
                break
            pid, pages = pg["next_id"], pages + 1
        print(f"\n{label}: {len(out)} items ({sum(1 for x in out if x['sellable'])} sellable); "
              f"brands {collections.Counter(x['brand'] for x in out).most_common(6)}")
        for x in out[:40]:
            print(f"   {x['sellable']} | {x['brand']} | {str(x['name'])[:95]}")
        res[label] = out
    REPORT["hm"] = res


for fn in (fc_brands, fc_lines, fc_hw, mg, kd, hm):
    if os.getenv("PROBE_ONLY") and fn.__name__ not in os.getenv("PROBE_ONLY"):
        continue
    fn()
json.dump(REPORT, open(os.path.join(ROOT, "probe_report.json"), "w"), indent=1, ensure_ascii=False, default=str)
print("\nreport saved")
