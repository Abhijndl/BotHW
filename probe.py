#!/usr/bin/env python3
"""Probe #35: FirstCry's Matchbox ("Match Box") and Majorette catalogues via
their brand ids (from the search page's brand filter), Hamleys' sitemap for
Matchbox / Majorette / monster / chase slugs, and how Karz & Dolls names chase
pieces across its Hot Wheels, Mini GT, Matchbox and Majorette shelves.
Read-only: no Telegram, no seen.json writes, nothing added to any cart."""
import collections, importlib.util, json, os, re, time, traceback
from urllib.parse import quote

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "FC_CART": "false"})
spec = importlib.util.spec_from_file_location("bot_v172", os.path.join(ROOT, "bot_v172.py"))
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)
http, IMP, H = bot.http, bot._IMPERSONATE, bot.COMMON_HEADERS
REPORT = {}
CHASEY = re.compile(r"chase|treasure|\bsth\b|\bth\b|zamac|super|limited|rubber|real rider|gold|raw|"
                    r"special|exclusive|collector|bonus|edition|black edition|chrome", re.I)


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


def fc_api(extra, pages=40, label="", referer=None):
    hdr = {**H, **bot._FC_NOCACHE, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
           "Referer": referer or bot._FC_API_REFERER}
    ck = bot._fc_cookies()
    prods, errs, npages = {}, [], 0
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
        npages += 1
        its = bot._fc_api_products(data)
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
                     "count": cnt, "bnm": str(bot._ci(p, "BNm") or ""), "bid": str(bot._ci(p, "BId") or ""),
                     "cat": f"{bot._ci(p, 'SCNm') or ''}", "mrp": bot._ci(p, "MRP"),
                     "prem": bot._ci(p, "IsPremium"), "new": bot._ci(p, "newdays"),
                     "tag": bot._ci(p, "collectiontag"), "pre": bot._ci(p, "ispreorder")})
    ins = sum(1 for x in rows if (x["count"] or 0) > 0)
    print(f"[FC-API {label}] {extra} → {len(rows)} products over {npages} page(s), {ins} with stock, "
          f"errors {errs}")
    if rows:
        print(f"   brands: {collections.Counter((x['bnm'], x['bid']) for x in rows).most_common(6)}")
        print(f"   subcategories: {collections.Counter(x['cat'] for x in rows).most_common(10)}")
    return rows


FACET = re.compile(r'data-val="(\d+)"[^>]*>\s*</span>\s*<div>\s*<span class="txt[^"]*">\s*([^<]+?)\s*</span>'
                   r'\s*<span class="cnt[^"]*"\s+data-val="\d+">\s*\((\d+)\)', re.S)
FACET2 = re.compile(r'<span class="txt[^"]*">\s*([^<]+?)\s*</span>\s*<span class="cnt[^"]*"\s+data-val="(\d+)">'
                    r'\s*\((\d+)\)', re.S)


@section("FirstCry: brand filter ids on the search pages")
def fc_facets():
    ids = {}
    for term in ("matchbox", "match box", "majorette", "hot wheels monster trucks"):
        u = bot._FC_SEARCH + quote(term)
        r = get(bot._fc_bust(u), headers={**H, **bot._FC_NOCACHE})
        t = r.text
        fac = [(m.group(1).strip(), m.group(2), int(m.group(3))) for m in FACET2.finditer(t)]
        print(f"\nsearch '{term}': HTTP {r.status_code}, {len(fac)} filter entries")
        brandish = [f for f in fac if re.search(r"match|major|hot|wheel|mattel|monster", f[0], re.I)]
        print(f"   brand-like: {brandish}")
        print(f"   all: {fac[:80]}")
        for nm, i, n in fac:
            ids.setdefault(nm.lower(), set()).add(i)
        # where the brand filter list sits (to read its parameter name)
        k = t.find('data-val="1335"')
        if k > 0:
            print(f"   ctx 1335: …{t[max(0, k - 700):k + 200]}…".replace("\n", " "))
    REPORT["fc_facets"] = {k: sorted(v) for k, v in ids.items()}


@section("FirstCry: Match Box / Majorette catalogues")
def fc_cats():
    fac = REPORT.get("fc_facets") or {}
    cands = {}
    for k, v in fac.items():
        if re.search(r"match\s*box|majorette", k, re.I):
            for i in v:
                cands[i] = k
    cands.setdefault("1335", "majorette")
    out = {}
    for bid, nm in sorted(cands.items()):
        for extra in ({"MasterBrand": bid}, {"MasterBrand": "", "BrandId": bid}):
            rows = fc_api(extra, label=f"{nm} {bid}")
            good = [x for x in rows if x["bid"] == bid or nm.split()[0] in x["name"].lower()]
            if not rows:
                continue
            print(f"   {len(good)} of {len(rows)} are {nm}")
            out[f"{nm}_{bid}_{'mb' if 'BrandId' not in extra else 'bid'}"] = rows
            for x in rows:
                if CHASEY.search(x["name"]):
                    print(f"   ⛓ {x['pid']} {x['count']} ₹{x['mrp']} pre={x['pre']} new={x['new']} "
                          f"{x['name'][:105]}")
            for x in sorted(rows, key=lambda x: -(x["count"] or 0))[:12]:
                print(f"   · {x['pid']} {x['count']} ₹{x['mrp']} {x['cat'][:20]} {x['name'][:95]}")
            if len(good) > 0.8 * len(rows):
                break
    REPORT["fc_cats"] = out


@section("Hamleys sitemap: Matchbox / Majorette / monster / chase slugs")
def hm():
    sess = bot._hm_session()
    urls, fetched, queue = [], set(), []
    r = sess.get("https://hamleys.in/robots.txt", headers=H, timeout=25)
    queue += re.findall(r"(?im)^sitemap:\s*(\S+)", r.text) if r.status_code == 200 else []
    queue += ["https://hamleys.in/sitemap.xml"]
    while queue and len(fetched) < 25:
        sm = queue.pop(0)
        if sm in fetched:
            continue
        fetched.add(sm)
        try:
            r = sess.get(sm, headers=H, timeout=25)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text):
            if loc.endswith(".xml"):
                queue.append(loc)
            elif "/product/" in loc:
                urls.append(loc.rsplit("/product/", 1)[-1].strip("/"))
    print(f"{len(fetched)} sitemaps, {len(urls)} product slugs")
    res = {}
    for k in ("hot-wheels", "matchbox", "majorette", "monster", "chase", "treasure", "super-treasure", "zamac"):
        hit = [u for u in urls if k in u.lower()]
        res[k] = hit
        print(f"\n{k}: {len(hit)}")
        if k not in ("hot-wheels",):
            for u in hit[:40]:
                print(f"   {u}")
    REPORT["hm_slugs"] = res


@section("Karz & Dolls: chase naming across shelves")
def kd():
    cats = ["/hot-wheels/mainlines", "/hot-wheels/pop-culture", "/hot-wheels/card-art-premiums",
            "/hot-wheels/gift-pack", "/hot-wheels/car-culture", "/hot-wheels/fast-and-furious",
            "/hot-wheels/boulevard-series", "/hot-wheels/team-transport", "/hot-wheels/character-cars",
            "/hot-wheels/monster-trucks", "/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack",
            "/mini-gt/kaido-house", "/pre-orders/pre-order-minigt", "/pre-orders/pre-order-special-stock",
            "/specials/chase-car", "/specials/special-stocks-64-43-scale", "/majorette/premium-cars",
            "/majorette/basic-cars", "/matchbox/matchbox-basic-cars", "/matchbox/matchbox-moving-parts",
            "/matchbox/matchbox-superfast", "/tarmac-works/tarmac-works", "/pop-race/pop-race",
            "/greenlight/classics", "/"]
    res = {}
    for c in cats:
        try:
            r = get(bot._KD + c)
        except Exception as e:
            print(f"{c}: {type(e).__name__}")
            continue
        m = bot._KD_NEXT.search(r.text)
        found = []
        if m:
            props = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
            stack = [props]
            while stack:
                n = stack.pop()
                if isinstance(n, list):
                    stack.extend(n)
                elif isinstance(n, dict):
                    if "pid" in n and "pro_name" in n:
                        found.append(n)
                    else:
                        stack.extend(n.values())
        hits = [p for p in found if CHASEY.search(f"{p.get('pro_name')} {p.get('product_sname')} {p.get('sku')}")]
        print(f"\n{c}: {len(found)} products, {len(hits)} chase-ish")
        for p in hits[:30]:
            print(f"   {p.get('in_stock')} | {str(p.get('product_sname'))[:40]:40} | {str(p.get('pro_name'))[:80]}")
        res[c] = [{k: p.get(k) for k in ("pid", "pro_name", "product_sname", "sku", "in_stock", "is_preorder",
                                          "dis_price")} for p in found]
    REPORT["kd"] = res


for fn in (fc_facets, fc_cats, hm, kd):
    if os.getenv("PROBE_ONLY") and fn.__name__ not in os.getenv("PROBE_ONLY"):
        continue
    fn()
json.dump(REPORT, open(os.path.join(ROOT, "probe_report.json"), "w"), indent=1, ensure_ascii=False, default=str)
print("\nreport saved")
