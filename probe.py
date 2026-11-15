#!/usr/bin/env python3
"""Probe #73: Scentoria 'Minis' (official minis or decants?), The Scent Stories' miniature
pages (newest first, how many per page, stock marks), Splash newest-first reads."""
import gzip, json, re, time, urllib.error, urllib.request
from collections import Counter

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def get(url, accept="application/json", timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip",
                                               "Accept-Language": "en-IN,en;q=0.9"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, data, hdr = r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, "", dict(e.headers or {}), int((time.time() - t) * 1000)
    except Exception as e:
        return type(e).__name__, "", {}, int((time.time() - t) * 1000)
    if "gzip" in (hdr.get("Content-Encoding") or "").lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace"), hdr, int((time.time() - t) * 1000)


print("==================== Scentoria minis")
B = "https://www.scentoria.co.in"
ps = []
for page in range(1, 6):
    code, body, _, _ = get(f"{B}/collections/minis/products.json?limit=250&page={page}")
    got = json.loads(body)["products"]
    ps += got
    if len(got) < 250:
        break
vt = Counter(v.get("title") for p in ps for v in p["variants"])
print("products", len(ps), "| variant titles:", vt.most_common(15))
print("product types:", Counter(p.get("product_type") for p in ps).most_common(8))
print("tags:", Counter(t for p in ps for t in p.get("tags") or []).most_common(15))
for p in ps[:5]:
    print("  e.g.", p["title"][:50], [(v["title"], v["price"], v["available"]) for v in p["variants"][:4]])
off = [p for p in ps if re.search(r"miniature|mini\b|travel|5\s?ml|7\.5\s?ml", p["title"] + " " + " ".join(v["title"] for v in p["variants"]), re.I)]
print("titles or sizes that look like official minis:", len(off), [p["title"][:45] for p in off[:6]])

print("\n==================== The Scent Stories")
T = "https://thescentstories.com"
for q in ("", "?order=create_date+desc", "?order=create_date+desc&ppg=60", "?ppg=100"):
    code, html, hdr, ms = get(f"{T}/shop/category/miniatures-58{q}", "text/html")
    cards = re.findall(r'<div[^>]+class="[^"]*oe_product_cart[^"]*"(.*?)</form>', html, re.S) or re.findall(r'(<form[^>]+action="/shop/cart/update".*?</form>)', html, re.S)
    links = re.findall(r'href="(/shop/[a-z0-9\-]+-\d+)"', html)
    pages = sorted(set(int(x) for x in re.findall(r'/shop/category/miniatures-58/page/(\d+)', html)))
    print(f"  {q or '(default)'} -> {code} in {ms} ms, {len(html)} bytes, cards {len(cards)}, product links {len(set(links))}, pages {pages[-3:] if pages else '-'}")
    if q == "?order=create_date+desc":
        sample = html
code, html, hdr, ms = get(f"{T}/shop/category/miniatures-58?order=create_date+desc", "text/html")
i = html.find('o_wsale_products_item_title')
print("--- one product card (raw) ---")
start = html.rfind("<form", 0, i) if i > 0 else -1
print(html[start: start + 3000] if start > 0 else html[i - 1500: i + 1500])
print("--- stock/ribbon words ---", Counter(w.lower() for w in re.findall(r'(?i)out of stock|sold out|in stock|coming soon|o_ribbon[^"]*"[^>]*>\s*([^<]{0,30})', html)).most_common(10))
names = re.findall(r'o_wsale_products_item_title[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>', html)
print("first names (newest first):", names[:8])
prices = re.findall(r'<span class="oe_currency_value">([^<]+)</span>', html)
print("prices seen:", prices[:12])
code, ph, hdr, ms = get(T + names[0][0], "text/html") if names else (0, "", {}, 0)
print(f"product page {names[0][0] if names else '-'} -> {code} in {ms} ms; stock words: {Counter(w.lower() for w in re.findall(r'(?i)out of stock|sold out|in stock|add to cart|notify me', ph)).most_common(6)}")
m = re.search(r'name="product_template_id"\s+value="(\d+)"', ph) or re.search(r'data-product-template-id="(\d+)"', ph)
print("template id:", m.group(1) if m else None)

print("\n==================== Splash official miniatures, newest first")
S = "https://splashfragrance.in"
code, body, hdr, ms = get(f"{S}/wp-json/wc/store/v1/products?category=1922&per_page=100&orderby=date&order=desc")
items = json.loads(body) if code == 200 else []
print(f"-> {code} in {ms} ms; total {hdr.get('X-WP-Total') or hdr.get('x-wp-total')}, pages {hdr.get('X-WP-TotalPages') or hdr.get('x-wp-totalpages')}, read {len(items)}, in stock {sum(1 for x in items if x.get('is_in_stock'))}")
for x in items[:6]:
    print("  ", x["id"], x["name"][:70], (x.get("prices") or {}).get("price"), x.get("is_in_stock"))
allm = []
t0 = time.time()
for page in range(1, 12):
    code, body, hdr, ms = get(f"{S}/wp-json/wc/store/v1/products?category=1922&per_page=100&page={page}")
    if code != 200:
        print("  page", page, code)
        break
    got = json.loads(body)
    allm += got
    if len(got) < 100:
        break
print(f"  full read: {len(allm)} in {time.time()-t0:.1f} s, in stock {sum(1 for x in allm if x.get('is_in_stock'))}")
sz = Counter(re.search(r"(\d+(?:\.\d+)?)\s?ml", x["name"], re.I).group(1) if re.search(r"(\d+(?:\.\d+)?)\s?ml", x["name"], re.I) else "?" for x in allm)
print("  sizes in names:", sz.most_common(12))
