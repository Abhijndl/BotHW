#!/usr/bin/env python3
"""Probe #80: where Whiff Culture's new Next.js site gets its products from."""
import gzip, json, re, time, urllib.error, urllib.request

T0 = time.time()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
B = "https://www.whiffculture.com"


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def get(url, extra=None, accept="text/html,application/json;q=0.9,*/*;q=0.8"):
    h = {"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"}
    h.update(extra or {})
    req = urllib.request.Request(url, headers=h)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data, hd, code, final = r.read(), dict(r.headers), r.status, r.geturl()
    except urllib.error.HTTPError as e:
        data, hd, code, final = e.read() or b"", dict(e.headers or {}), e.code, url
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", {}, url, time.time() - t
    if "gzip" in (hd.get("Content-Encoding") or "").lower():
        try:
            data = gzip.decompress(data)
        except Exception:
            pass
    return code, data.decode("utf-8", "replace"), hd, final, time.time() - t


def around(body, pat, n=2, w=350):
    out = []
    for m in re.finditer(pat, body):
        out.append(body[max(0, m.start() - w):m.end() + w].replace("\n", " "))
        if len(out) >= n:
            break
    return out


PATS = r"myshopify\.com|storefront|graphql|[Aa]ccess[-_]?[Tt]oken|X-Shopify|/api/[a-z]|checkoutUrl|cartCreate|NEXT_PUBLIC"

# collection page, twice, to see caching
for i in range(2):
    code, body, hd, final, dt = get(B + "/collections/partial-bottles")
    log(f"[PB{i}] {code} {dt:.2f}s len={len(body)} final={final}")
    log(f"[PB{i}] headers:", json.dumps(hd)[:1200])
    time.sleep(1)
pb = body
prods = sorted(set(re.findall(r'/products/([a-z0-9][a-z0-9\-]*)', pb)))
log(f"[PB] product handles: {len(prods)}", prods[:60])
for k in ("availableForSale", "quantityAvailable", "compareAtPrice", "gid://shopify/Product/", "gid://shopify/ProductVariant/",
          "__next_f", "totalInventory", "inStock", "soldOut", "sold out", "Sold out", "Sold Out", "pageInfo", "hasNextPage", "endCursor"):
    log(f"[PB] count {k!r}: {pb.count(k)}")
for s in around(pb, r"availableForSale", 2):
    log("[PB] around availableForSale:", s)
for s in around(pb, r"gid://shopify/Product/\d+", 1):
    log("[PB] around Product gid:", s)
for s in around(pb, PATS, 8, 160):
    log("[PB] api-ish:", s)

# scripts on the collection page
scripts = sorted(set(re.findall(r'src="(/_next/static/[^"]+\.js)"', pb)))
log(f"[JS] {len(scripts)} scripts")
for s in scripts:
    code, js, hd, final, dt = get(B + s, accept="*/*")
    hits = around(js, PATS, 6, 140)
    if hits:
        log(f"[JS] {s} len={len(js)}")
        for h in hits:
            log("    ", h)

# RSC flight payload
code, body, hd, final, dt = get(B + "/collections/partial-bottles", {"RSC": "1"}, accept="text/x-component")
log(f"[RSC] {code} {dt:.2f}s len={len(body)} ctype={hd.get('Content-Type')} cache={hd.get('X-Vercel-Cache')} age={hd.get('Age')}")
log("[RSC] head:", body[:600].replace("\n", " "))

# pagination / sort params
for q in ("?page=2", "?sort=newest", "?sort_by=created-descending"):
    code, body, hd, final, dt = get(B + "/collections/partial-bottles" + q)
    hs = sorted(set(re.findall(r'/products/([a-z0-9][a-z0-9\-]*)', body)))
    log(f"[PB{q}] {code} {dt:.2f}s len={len(body)} handles={len(hs)} first={hs[:5]}")

# the other lists
for c in ("partial-sale", "partial-bottles", "sale", "testers", "vials", "decant-sets", "all"):
    code, body, hd, final, dt = get(B + "/collections/" + c)
    hs = sorted(set(re.findall(r'/products/([a-z0-9][a-z0-9\-]*)', body)))
    log(f"[COLL] {c}: {code} {dt:.2f}s len={len(body)} handles={len(hs)} avail={body.count('availableForSale')} "
        f"cache={hd.get('X-Vercel-Cache')} age={hd.get('Age')} cc={hd.get('Cache-Control')}")

# a product page
if prods:
    code, body, hd, final, dt = get(B + "/products/" + prods[0])
    log(f"[PROD] {prods[0]}: {code} {dt:.2f}s len={len(body)} cache={hd.get('X-Vercel-Cache')} cc={hd.get('Cache-Control')}")
    for s in around(body, r"availableForSale|quantityAvailable", 2, 300):
        log("[PROD] around:", s)

# old Shopify storefront on other hosts
for host in ("whiffculture.myshopify.com", "whiff-culture.myshopify.com", "whiffculture-in.myshopify.com",
             "checkout.whiffculture.com", "shop.whiffculture.com", "store.whiffculture.com", "secure.whiffculture.com"):
    for path in ("/products.json?limit=1", "/collections/partial-bottles/products.json?limit=1"):
        code, body, hd, final, dt = get(f"https://{host}{path}", accept="application/json")
        log(f"[HOST] {host}{path}: {code} {dt:.2f}s final={final} len={len(body)} :: {body[:160]!r}")
log("done")
