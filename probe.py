#!/usr/bin/env python3
"""Probe #44: Karz & Dolls — does the tracker's link format open a product that
IS in stock (so a 404 means "sold out / taken down")? What do KND's own links
look like? And how do the box and blister-pack shelves tell their cars apart?"""
import json, re, time, html, collections
from urllib.parse import quote
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
KD = "https://www.karzanddolls.com"
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def get(url):
    try:
        r = http.get(url, headers=H, timeout=25, allow_redirects=True, **IMP)
        return r.status_code, r.text, str(r.url)
    except Exception as e:
        return None, "", type(e).__name__


def products(page):
    m = NEXT.search(page or "")
    if not m:
        return []
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


shelf = {}
for path in ["/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack"]:
    code, page, _ = get(KD + path)
    ps = products(page)
    shelf[path] = ps
    print(f"=== {path}: HTTP {code}, {len(ps)} products")
    if ps:
        print("  fields of a product:", sorted(ps[0].keys()))
        for p in ps[:6]:
            print("   ", {k: p.get(k) for k in ("pid", "pro_name", "slug", "product_sname", "sku", "in_stock", "act_price", "dis_price",
                                                  "cat_name", "subcat_name", "category", "sub_category", "pack", "packaging", "type")
                       if k in p})
    links = re.findall(r'href="(/details/[^"]+)"', page or "")
    print(f"  KND's own product links on this page: {len(links)}; e.g. {[html.unescape(x) for x in links[:3]]}")

# the same car on both shelves? (box and blister of one model)
names = collections.defaultdict(list)
for path, ps in shelf.items():
    for p in ps:
        names[re.sub(r"[^A-Z0-9]", "", str(p.get("pro_name", "")).upper())].append((path, p))
both = {k: v for k, v in names.items() if len({x[0] for x in v}) > 1}
print(f"\n=== models listed on BOTH shelves: {len(both)}")
for k, v in list(both.items())[:8]:
    for path, p in v:
        print(f"   {path:32} pid={p.get('pid')} ₹{p.get('dis_price') or p.get('act_price')} in_stock={p.get('in_stock')} sku={p.get('sku')!r} sname={p.get('product_sname')!r} name={p.get('pro_name')!r}")
dup_same_shelf = {k: v for k, v in names.items() if len(v) > 1 and len({x[0] for x in v}) == 1}
print(f"=== same name twice on one shelf: {len(dup_same_shelf)}")
for k, v in list(dup_same_shelf.items())[:5]:
    for path, p in v:
        print(f"   {path:32} pid={p.get('pid')} ₹{p.get('dis_price') or p.get('act_price')} sku={p.get('sku')!r} sname={p.get('product_sname')!r} name={p.get('pro_name')!r}")
# words in blister-shelf names / skus vs box-shelf ones
for path, ps in shelf.items():
    c = collections.Counter()
    for p in ps:
        t = (str(p.get("pro_name")) + " " + str(p.get("sku")) + " " + str(p.get("product_sname"))).upper()
        for w in ("BLISTER", "BOX", "CARD", "PACK", "BL", "-B"):
            if w in t:
                c[w] += 1
    print(f"  words on {path}: {dict(c)}  (of {len(ps)})")

print("\n=== does the tracker's link format open an in-stock car? ===")
tested = 0
for path, ps in shelf.items():
    for p in ps:
        if str(p.get("in_stock")) not in ("1", "True", "true"):
            continue
        slug, pid = str(p.get("slug") or ""), str(p.get("pid"))
        for label, url in (("tracker's link", f"{KD}/details/{quote(slug, safe='-_.~')}?pid={quote(pid, safe='')}"),
                           ("slug 'x'", f"{KD}/details/x?pid={pid}"),
                           ("no ?pid", f"{KD}/details/{quote(slug, safe='-_.~')}")):
            code, page, final = get(url)
            nm = str(p.get("pro_name"))[:30]
            print(f"  {label:15} HTTP {code}  page shows '{nm}': {nm.upper()[:20] in (page or '').upper()}  404: {'Page not found' in (page or '')}  {url[len(KD):][:90]}")
        tested += 1
        if tested >= 3:
            break
    if tested >= 3:
        break
