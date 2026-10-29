#!/usr/bin/env python3
"""Probe #48: Karz & Dolls — (1) can a car whose slug has a '?' be opened at
all (double-encoded, '?' dropped, the shop's own link)? (2) Is there a search
page to link to instead? (3) Can a car be added to the cart from the shelf?
(4) How do box and blister show in sku/name on every Mini GT shelf? Read-only."""
import json, re, html, collections, time
from urllib.parse import quote
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
KD = "https://www.karzanddolls.com"
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def get(url, **kw):
    try:
        r = http.get(url, headers={**H, **kw.pop("h", {})}, timeout=25, allow_redirects=True, **IMP, **kw)
        return r.status_code, r.text, str(r.url)
    except Exception as e:
        return None, "", ""


def nd(page):
    m = NEXT.search(page or "")
    return json.loads(m.group(1)) if m else {}


def detail(page):
    pp = (nd(page).get("props") or {}).get("pageProps") or {}
    return pp.get("productdetails") or {}


def shelf_products(page):
    pp = (nd(page).get("props") or {}).get("pageProps") or {}
    found, stack = [], [pp]
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            if "pid" in n and "pro_name" in n and "slug" in n:
                found.append(n)
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
    return found


rep = {}
print("=== 1. opening a car whose slug has a '?' ===")
Q = [("/action-figures/dolls", "Pqp262Op36", "?barbie-made-to-move-fashion-doll-with-black-hair-"),
     ("/lego/lego-duplo", "KBg7nKepRr", "lego-duplo-?-disney-mickey-minnie-birthday-train-building-toy-22-pie")]
R1 = []
for shelf, pid, slug_hint in Q:
    code, page, _ = get(KD + shelf)
    ps = [p for p in shelf_products(page) if str(p["pid"]) == pid]
    if not ps:
        print(f"  {pid}: not on {shelf} any more")
        continue
    p = ps[0]
    slug = str(p["slug"])
    own = sorted(set(html.unescape(m) for m in re.findall(r'href="([^"]*' + re.escape(pid) + r'[^"]*)"', page or "")))
    print(f"  {pid} in_stock={p.get('in_stock')} slug={slug!r}  shop's own hrefs: {own[:3]}")
    tries = [("tracker's (%3F)", f"/details/{quote(slug, safe='-_.~')}?pid={pid}"),
             ("double %253F", "/details/" + quote(slug, safe='-_.~').replace("%3F", "%253F") + f"?pid={pid}"),
             ("'?' dropped", "/details/" + quote(slug.replace("?", ""), safe='-_.~') + f"?pid={pid}"),
             ("'?'→'-'", "/details/" + quote(slug.replace("?", "-"), safe='-_.~') + f"?pid={pid}"),
             ("before '?' only", "/details/" + quote(slug.split("?")[0], safe='-_.~') + f"?pid={pid}"),
             ("after '?' only", "/details/" + quote(slug.split("?", 1)[1], safe='-_.~') + f"?pid={pid}"),
             ("pid as slug", f"/details/{pid}?pid={pid}")] + [("shop's own", h) for h in own[:2]]
    for label, path in tries:
        code, page2, final = get(KD + path if path.startswith("/") else path)
        d = detail(page2)
        ok = str(d.get("pid")) == pid
        R1.append({"pid": pid, "label": label, "path": path, "http": code, "opens": ok})
        print(f"    {label:17} HTTP {code} opens it: {ok}  {path[:90]!r}")
rep["q"] = R1

print("\n=== 2. a search page? ===")
code, home, _ = get(KD + "/")
js = re.findall(r'<script[^>]+src="([^"]+\.js)"', home or "")
hits = collections.Counter()
for src in js[:14]:
    c2, body, _ = get(src if src.startswith("http") else KD + src, h={"Accept": "*/*"})
    for m in re.findall(r'["\'`](/[a-zA-Z\-_/]*search[a-zA-Z\-_/]*(?:\?[a-zA-Z_]+=)?)', body or "", re.I):
        hits[m] += 1
    for m in re.findall(r'(search[A-Za-z]*)\s*[:=]', body or ""):
        hits["(key) " + m] += 1
print("  search-ish strings in the scripts:", hits.most_common(25))
forms = re.findall(r'<form[^>]*>', home or "")
print("  forms on the home page:", forms[:4])
inputs = re.findall(r'<input[^>]*(?:search|Search)[^>]*>', home or "")
print("  search inputs:", inputs[:3])
cands = ["/search?q=mclaren", "/search?keyword=mclaren", "/search?search=mclaren", "/search/mclaren", "/searchresult?search=mclaren",
         "/search-result?search=mclaren", "/products?search=mclaren", "/search?query=mclaren", "/search?term=mclaren", "/search?s=mclaren"]
for m, _ in hits.most_common(8):
    if m.startswith("/") and "?" in m:
        cands.append(m + "mclaren")
    elif m.startswith("/"):
        cands.append(m.rstrip("/") + "/mclaren")
R2 = []
for c in dict.fromkeys(cands):
    code, page, final = get(KD + c)
    ps = shelf_products(page)
    mc = [p for p in ps if "MCLAREN" in str(p.get("pro_name")).upper()]
    R2.append({"url": c, "http": code, "n": len(ps), "mclaren": len(mc), "page": nd(page).get("page"), "final": final})
    print(f"  {c:40} HTTP {code} page={nd(page).get('page')!r} products={len(ps)} mclaren={len(mc)} → {final[len(KD):][:60]}")
rep["search"] = R2

print("\n=== 3. add to cart from the shelf? ===")
code, page, _ = get(KD + "/mini-gt/mini-gt-blister-pack")
for w in ("Add to cart", "ADD TO CART", "Add To Cart", "Buy Now", "BUY NOW", "Notify", "Quick", "addtocart", "addToCart"):
    n = (page or "").count(w)
    if n:
        print(f"  {w!r}: {n} times")
i = (page or "").find("Add to")
print("  around the first 'Add to':", re.sub(r"\s+", " ", (page or "")[max(0, i - 400):i + 120])[:600] if i >= 0 else "(none)")

print("\n=== 4. box / blister on every Mini GT shelf ===")
shelves = {}
for s in ["/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack", "/mini-gt/kaido-house", "/pre-orders/pre-order-minigt"]:
    code, page, _ = get(KD + s)
    shelves[s] = {str(p["pid"]): p for p in shelf_products(page)}
blister_pids = set(shelves["/mini-gt/mini-gt-blister-pack"])
for s, ps in shelves.items():
    def has(p, w):
        return w in re.sub(r"\s+", " ", (str(p.get("sku")) + " " + str(p.get("product_sname")) + " " + str(p.get("pro_name"))).upper())
    nb = [p for p in ps.values() if has(p, "BLISTER")]
    nbox = [p for p in ps.values() if re.search(r"\bBOX\b", (str(p.get("pro_name")) + " " + str(p.get("sku"))).upper())]
    print(f"  {s:32} {len(ps)} products; BLISTER in sku/name: {len(nb)}; BOX: {len(nbox)}")
    for p in list(ps.values())[:4]:
        print(f"      sku={str(p.get('sku')).strip()[:30]!r} sname={str(p.get('product_sname')).strip()[:30]!r} name={str(p.get('pro_name')).strip()[:60]!r} ₹{p.get('dis_price')}")
    if s == "/mini-gt/mini-gt":
        for p in nb:
            print(f"      BLISTER here: sku={str(p.get('sku')).strip()[:34]!r} name={str(p.get('pro_name')).strip()[:60]!r} also on blister shelf: {str(p['pid']) in blister_pids}")
        for p in nbox:
            print(f"      BOX here: sku={str(p.get('sku')).strip()[:34]!r} name={str(p.get('pro_name')).strip()[:60]!r}")
    if s in ("/mini-gt/kaido-house", "/pre-orders/pre-order-minigt"):
        for p in nb[:6]:
            print(f"      BLISTER: sku={str(p.get('sku')).strip()[:34]!r} name={str(p.get('pro_name')).strip()[:70]!r}")
rep["shelves"] = {s: [{k: p.get(k) for k in ("pid", "sku", "product_sname", "pro_name", "dis_price")} for p in ps.values()] for s, ps in shelves.items()}

print("\n=== 5. the unit count on product pages (product_attr qty) ===")
Q5 = []
for p in list(shelves["/mini-gt/mini-gt-blister-pack"].values())[:10]:
    code, page, _ = get(f"{KD}/details/{quote(str(p['slug']), safe='-_.~')}?pid={p['pid']}")
    d = detail(page)
    try:
        attr = json.loads(d.get("product_attr") or "{}")
    except Exception:
        attr = d.get("product_attr")
    Q5.append({"pid": p["pid"], "attr": attr, "add_limit": d.get("add_limit")})
    print(f"  {str(p['pro_name'])[:50]!r:54} add_limit={d.get('add_limit')} product_attr={json.dumps(attr)[:140]}")
rep["qty"] = Q5
json.dump(rep, open("probe_report.json", "w"), indent=1, default=str)
