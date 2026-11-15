#!/usr/bin/env python3
"""Probe #72: miniatures — The Scent Stories, The Fragrance Heaven, Splash Fragrance,
Friday Charm, and the seven stores already watched."""
import gzip, json, re, time, urllib.error, urllib.request
from collections import Counter

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
MINI = re.compile(r"mini(ature)?s?\b|travel|pocket", re.I)


def get(url, accept="application/json", timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip",
                                               "Accept-Language": "en-IN,en;q=0.9"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, data, hdr, final = r.status, r.read(), dict(r.headers), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", dict(e.headers or {}), url, int((time.time() - t) * 1000)
    except Exception as e:
        return type(e).__name__, "", {}, url, int((time.time() - t) * 1000)
    if "gzip" in (hdr.get("Content-Encoding") or "").lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace"), hdr, final, int((time.time() - t) * 1000)


def shopify(base, path):
    out = []
    for page in range(1, 9):
        code, body, _, _, _ = get(f"{base}{path}?limit=250&page={page}&_={int(time.time()*1000)}")
        if code != 200:
            return out or None, code
        ps = json.loads(body).get("products") or []
        out += ps
        if len(ps) < 250:
            break
    return out, 200


def avail(p):
    return any(v.get("available") for v in p.get("variants") or [])


def collections(base):
    cs = []
    for page in range(1, 5):
        code, body, _, _, _ = get(f"{base}/collections.json?limit=250&page={page}")
        if code != 200:
            break
        got = json.loads(body).get("collections") or []
        cs += got
        if len(got) < 250:
            break
    return cs


print("==================== The Scent Stories")
for b in ("https://thescentstories.com", "https://www.thescentstories.com"):
    code, html, hdr, final, ms = get(b + "/", "text/html")
    print(f"{b}/ -> {code} in {ms} ms, final {final}, server {hdr.get('Server') or hdr.get('server')}, "
          f"marks {[m for m in ('odoo', 'web.assets', '/shop/category', 'cdn.shopify', 'woocommerce', '_next') if m in html]}")
    if code == 200:
        cats = sorted(set(re.findall(r'href="(/shop/category/[^"#?]+)"', html)))
        print("  shop categories:", cats[:40])
        break
TS = "https://thescentstories.com"
for path in ("/shop", "/shop/category/miniatures", "/shop?search=miniature"):
    code, html, hdr, final, ms = get(TS + path, "text/html")
    names = re.findall(r'itemprop="name"[^>]*>([^<]{3,90})<', html) or re.findall(r'class="[^"]*o_wsale_products_item_title[^"]*"[^>]*>\s*<a[^>]*>([^<]{3,90})<', html)
    print(f"  {path} -> {code} in {ms} ms, final {final}, {len(html)} bytes, product names found {len(names)} e.g. {names[:4]}")
    cats = sorted(set(re.findall(r'href="(/shop/category/[^"#?]+)"', html)))
    if cats:
        print("    categories:", [c for c in cats if MINI.search(c)][:10], "of", len(cats))
for path in ("/shop/products/autocomplete", "/website/snippet/filters"):
    body = json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"term": "miniature", "options": {"limit": 5}}}).encode()
    req = urllib.request.Request(TS + path, data=body, headers={"User-Agent": UA, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"  POST {path} -> {r.status}: {r.read()[:300]!r}")
    except Exception as e:
        print(f"  POST {path} -> {getattr(e, 'code', type(e).__name__)}")

for name, base, mini_path in (("The Fragrance Heaven", "https://fragranceheaven.in", "/collections/miniatures/products.json"),
                              ("Friday Charm", "https://www.fridaycharm.com", "/collections/miniature/products.json")):
    print(f"\n==================== {name}")
    code, html, hdr, final, ms = get(base + "/", "text/html")
    print(f"{base}/ -> {code} in {ms} ms, final {final}, shopify {'cdn.shopify' in html}")
    base = re.match(r"https?://[^/]+", final).group(0) if code == 200 else base
    cs = collections(base)
    print("  mini-like collections:", [(c['handle'], c['title'], c.get('products_count')) for c in cs if MINI.search(c['handle'] + ' ' + c['title'])])
    ps, why = shopify(base, mini_path)
    print(f"  {mini_path}: {len(ps or [])} listed, {sum(avail(p) for p in ps or [])} in stock ({why})")
    for p in sorted(ps or [], key=lambda p: p.get("created_at") or "")[-6:]:
        print("    e.g.", (p.get("created_at") or "")[:10], p["title"][:60], [(v.get("title")[:15], v.get("price"), v.get("compare_at_price"), v.get("available")) for v in p["variants"][:2]])
    codes = [get(f"{base}{mini_path}?limit=250&_={int(time.time()*1000)}")[0] for _ in range(4)]
    print("  4 quick reads:", codes)

print("\n==================== Splash Fragrance")
SP = "https://splashfragrance.in"
code, html, hdr, final, ms = get(SP + "/", "text/html")
print(f"{SP}/ -> {code} in {ms} ms, final {final}, server {hdr.get('Server') or hdr.get('server')}, woo {'woocommerce' in html}")
code, body, hdr, _, ms = get(f"{SP}/wp-json/wc/store/v1/products/categories?per_page=100")
cats = json.loads(body) if code == 200 else []
print(f"categories -> {code} in {ms} ms: {len(cats)}; mini-like: {[(c['id'], c['slug'], c['name'], c.get('count')) for c in cats if MINI.search(c['slug'] + ' ' + c['name'])]}")
for c in [c for c in cats if MINI.search(c['slug'] + ' ' + c['name'])][:3]:
    items = []
    for page in range(1, 6):
        code, body, hdr, _, ms = get(f"{SP}/wp-json/wc/store/v1/products?category={c['id']}&per_page=100&page={page}")
        if code != 200:
            print("   page", page, "->", code)
            break
        got = json.loads(body)
        items += got
        if len(got) < 100:
            break
    print(f"  category {c['slug']}: {len(items)} read, in stock {sum(1 for i in items if i.get('is_in_stock'))}, types {Counter(i.get('type') for i in items)}")
    for i in items[:5]:
        pr = i.get("prices") or {}
        print("    e.g.", i["name"][:60], "|", pr.get("price"), pr.get("regular_price"), pr.get("currency_minor_unit"), "|", i.get("is_in_stock"), "|", i.get("permalink"))
codes = [get(f"{SP}/wp-json/wc/store/v1/products?per_page=20&_={int(time.time()*1000)}")[0] for _ in range(4)]
print("  4 quick reads:", codes)

print("\n==================== the seven watched stores")
for name, base in (("Whiff Culture", "https://www.whiffculture.com"), ("Scentoria", "https://www.scentoria.co.in"),
                   ("Scentira", "https://www.scentira.in"), ("Sillage", "https://www.sillageperfumes.in"), ("Sniff", "https://sniff.co.in")):
    cs = collections(base)
    hits = [(c['handle'], c['title'], c.get('products_count')) for c in cs if MINI.search(c['handle'] + ' ' + c['title'])]
    print(f"{name}: {len(cs)} collections; mini-like: {hits}")
    for h, t, n in hits[:4]:
        ps, why = shopify(base, f"/collections/{h}/products.json")
        print(f"   {h}: {len(ps or [])} listed, {sum(avail(p) for p in ps or [])} in stock; e.g. {[p['title'][:40] for p in (ps or [])[:3]]}")
    ps, why = shopify(base, "/products.json")
    mt = [p for p in ps or [] if re.search(r"\bminiature|\bmini\b", p["title"], re.I)]
    print(f"   whole store: {len(ps or [])} products, {len(mt)} titled mini/miniature ({sum(avail(p) for p in mt)} in stock) e.g. {[p['title'][:45] for p in mt[:3]]}")
code, body, _, _, _ = get("https://www.sovereignscents.in/api/products?limit=1000&search=mini")
print("Sovereign Scents search=mini:", code, len(json.loads(body).get("products") or []) if code == 200 else "-")
for q in ("mini", "miniature"):
    code, body, _, _, _ = get(f"https://acordell.com/wp-json/wc/store/v1/products?per_page=100&search={q}")
    items = json.loads(body) if code == 200 else []
    print(f"Acordell search={q}: {code} {len(items)}", [i['name'][:40] for i in items[:4]])
