#!/usr/bin/env python3
"""Probe #47: Karz & Dolls — (1) when two products share one slug, which one
does the page show (read pageProps.productdetails this time)? (2) Does a '?'
inside a slug cut it short in the shop's own lookup (so a car like the
McLaren LB?WORKS can't open even while in stock)? (3) Any in-stock car with
'?', '#', '&', '/', '%' or '+' in its slug on any category? (4) What does a
product's details record hold (any unit count)? Read-only."""
import json, re, html, collections, time
from urllib.parse import quote, unquote
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
KD = "https://www.karzanddolls.com"
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def get(url, **kw):
    try:
        r = http.get(url, headers={**H, **kw.pop("h", {})}, timeout=25, allow_redirects=True, **IMP, **kw)
        return r.status_code, r.text
    except Exception as e:
        return None, ""


def nd(page):
    m = NEXT.search(page or "")
    return json.loads(m.group(1)) if m else {}


def detail(page):
    pp = (nd(page).get("props") or {}).get("pageProps") or {}
    return pp.get("productdetails") or {}, sorted(pp.keys())


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


def link(slug, pid):
    return f"{KD}/details/{quote(slug, safe='-_.~')}?pid={quote(pid, safe='')}"


rep = {}
SHELVES = ["/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack", "/mini-gt/kaido-house", "/pre-orders/pre-order-minigt", "/",
           "/hot-wheels/mainlines", "/hot-wheels/car-culture", "/hot-wheels/pop-culture", "/specials/chase-car"]
allp, cats = {}, set()
for s in SHELVES:
    code, page = get(KD + s)
    for p in shelf_products(page):
        allp[str(p["pid"])] = p
    if s == "/":
        for m in re.findall(r'href="(/[a-z0-9\-]+/[a-z0-9\-]+(?:/[A-Za-z0-9=]+)?)"', page or ""):
            cats.add(html.unescape(m))
        for m in re.findall(r'href="(/details/[a-z0-9\-]+/[a-z0-9\-]+/[A-Za-z0-9=]{2,8})"', page or ""):
            cats.add(html.unescape(m))

print("=== 4. what a details record holds ===")
inst = [p for p in allp.values() if str(p.get("in_stock")) == "1" and re.fullmatch(r"[a-z0-9\-]+", str(p.get("slug")))]
code, page = get(link(inst[0]["slug"], inst[0]["pid"]))
d, keys = detail(page)
print("  pageProps keys:", keys)
print("  productdetails:", {k: (v if len(json.dumps(v, default=str)) < 120 else f"<{type(v).__name__} {len(json.dumps(v, default=str))} chars>") for k, v in d.items()})
rep["detail_keys"] = sorted(d.keys())

print("\n=== 1. two products with one slug ===")
byslug = collections.defaultdict(list)
for p in allp.values():
    byslug[str(p["slug"])].append(p)
dups = {k: v for k, v in byslug.items() if len({str(x["pid"]) for x in v}) > 1}
print(f"  {len(allp)} products on {len(SHELVES)} shelves; {len(dups)} slugs shared by 2+ products")
C = []
for slug, ps in list(dups.items())[:12]:
    for p in ps:
        code, page = get(link(slug, str(p["pid"])))
        d, _ = detail(page)
        same = str(d.get("pid")) == str(p["pid"])
        C.append({"slug": slug, "pid": p["pid"], "sku": p.get("sku"), "price": p.get("dis_price"), "http": code,
                  "shows_pid": d.get("pid"), "shows_sku": d.get("sku"), "shows_price": d.get("dis_price"), "same": same})
        print(f"  {slug[:44]!r:48} pid={p['pid']} ₹{p.get('dis_price')} {str(p.get('sku')).strip()[:24]!r:27} → HTTP {code} shows pid={d.get('pid')} ₹{d.get('dis_price')} {str(d.get('sku')).strip()[:24]!r} {'SAME' if same else 'OTHER'}")
rep["shared"] = C
print("  same:", sum(c["same"] for c in C), "of", len(C))

print("\n=== 2. does a '?' cut the slug short? (in-stock cars) ===")
F = []
for p in inst[:3]:
    slug, pid = str(p["slug"]), str(p["pid"])
    for label, path in [("as is", quote(slug)), ("+%3F", quote(slug) + "%3F"), ("+%3Fzzz", quote(slug) + "%3Fzzz"),
                        ("+zzz", quote(slug) + "zzz"), ("+%23zzz", quote(slug) + "%23zzz"), ("+%26zzz", quote(slug) + "%26zzz"),
                        ("+%2Fzzz", quote(slug) + "%2Fzzz"), ("+%25zzz", quote(slug) + "%25zzz"), ("+%2Bzzz", quote(slug) + "%2Bzzz")]:
        code, page = get(f"{KD}/details/{path}?pid={pid}")
        d, _ = detail(page)
        F.append({"slug": slug, "label": label, "http": code, "shows": d.get("pid")})
        print(f"  {slug[:40]!r:44} {label:9} → HTTP {code} shows pid={d.get('pid')} {'(it)' if str(d.get('pid')) == pid else ''}")
rep["cut"] = F

print("\n=== 3. any in-stock car with '?', '#', '&', '/', '%' or '+' in its slug? ===")
cats = sorted(c for c in cats if not c.startswith(("/_next", "/api", "/static")))
print(f"  {len(cats)} category links on the home page")
odd = {}
for c in cats[:110]:
    code, page = get(KD + c)
    for p in shelf_products(page):
        allp[str(p["pid"])] = p
        if re.search(r"[?#&/%+]", str(p.get("slug"))):
            odd[str(p["pid"])] = (c, p)
print(f"  {len(allp)} products in all; {len(odd)} with those characters:")
G = []
for pid, (c, p) in list(odd.items())[:12]:
    code, page = get(link(str(p["slug"]), pid))
    d, _ = detail(page)
    G.append({"cat": c, "pid": pid, "slug": p["slug"], "in_stock": p.get("in_stock"), "http": code, "shows": d.get("pid")})
    print(f"  {c[:30]:32} in_stock={p.get('in_stock')} slug={str(p['slug'])[:60]!r} → HTTP {code} shows={d.get('pid')} {'(it)' if str(d.get('pid')) == pid else ''}")
rep["odd"] = G
json.dump(rep, open("probe_report.json", "w"), indent=1, default=str)
