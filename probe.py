#!/usr/bin/env python3
"""Probe #81: read Whiff Culture's product data from its pages, and how fresh it is."""
import gzip, json, re, time, urllib.error, urllib.request

T0 = time.time()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
B = "https://www.whiffculture.com"
OLD = {"14942891868528", "14942899601776", "14942903468400", "14942919033200", "14942923620720"}


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def get(url, extra=None, accept="text/html,application/json;q=0.9,*/*;q=0.8", data=None, timeout=25):
    h = {"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"}
    h.update(extra or {})
    req = urllib.request.Request(url, headers=h, data=data)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body, hd, code, final = r.read(), dict(r.headers), r.status, r.geturl()
    except urllib.error.HTTPError as e:
        body, hd, code, final = e.read() or b"", dict(e.headers or {}), e.code, url
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", {}, url, time.time() - t
    if "gzip" in (hd.get("Content-Encoding") or "").lower():
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
    return code, body.decode("utf-8", "replace"), hd, final, time.time() - t


def products(rsc):
    i = rsc.find('"initialProducts":')
    if i < 0:
        return None
    arr, _ = json.JSONDecoder().raw_decode(rsc, i + len('"initialProducts":'))
    return arr


def cache(hd):
    return f"cache={hd.get('X-Vercel-Cache')} age={hd.get('Age')}"


# 1. the partials list from the RSC payload
code, rsc, hd, final, dt = get(B + "/collections/partial-bottles", {"RSC": "1"}, accept="text/x-component")
log(f"[RSC] {code} {dt:.2f}s len={len(rsc)} {cache(hd)}")
ps = products(rsc) or []
log(f"[RSC] {len(ps)} products; keys of first: {sorted(ps[0].keys()) if ps else None}")
if ps:
    log("[RSC] first product:", json.dumps(ps[0])[:2500])
    ids = {str(p.get("shopifyId", "")).rsplit("/", 1)[-1] for p in ps}
    log(f"[RSC] old ids found: {len(OLD & ids)}/5")
    log("[RSC] inStock values:", {str(k): sum(1 for p in ps if p.get("inStock") == k) for k in (True, False, None)})
    for k in ("variants", "sizes", "price", "compareAtPrice", "createdAt", "publishedAt", "updatedAt", "tags"):
        if k in ps[0]:
            log(f"[RSC] {k} of first:", json.dumps(ps[0][k])[:600])
    log("[RSC] newest 5 by shopify id:", [(p.get("shopifyId", "").rsplit("/", 1)[-1], p.get("name"), p.get("inStock"))
                                          for p in sorted(ps, key=lambda p: int(str(p.get("shopifyId", "0")).rsplit("/", 1)[-1] or 0))[-5:]])
# client chunks referenced only from the payload
chunks = sorted(set(re.findall(r'static/chunks/[^"]+\.js', rsc)))
log(f"[RSC] {len(chunks)} chunks referenced")
lines = [l for l in rsc.split("\n") if re.match(r"^[0-9a-f]+:I\[", l)]
for l in lines:
    if re.search(r"Collection|Product|Grid|Shop|Listing", l):
        log("[RSC] client ref:", l[:400])
for c in chunks:
    if "/app/" not in c and not re.search(r"collection|product", c, re.I):
        continue
    code, js, hd2, _, _ = get(B + "/_next/" + c, accept="*/*")
    hits = []
    for m in re.finditer(r'fetch\(|/api/[a-zA-Z][\w/\-]*|revalidate|router\.refresh|setInterval|useSWR|useQuery', js):
        hits.append(js[max(0, m.start() - 120):m.end() + 160].replace("\n", " "))
    log(f"[JS] {c} len={len(js)} hits={len(hits)}")
    for h in hits[:10]:
        log("     ", h)

# 2. other lists
for c in ("partial-sale", "sale", "testers", "vials"):
    code, body, hd, final, dt = get(B + "/collections/" + c, {"RSC": "1"}, accept="text/x-component")
    pp = products(body) or []
    log(f"[COLL] {c}: {code} {dt:.2f}s len={len(body)} {cache(hd)} products={len(pp)} in={sum(1 for p in pp if p.get('inStock'))}")

# 3. api guesses
for u in ("/api/products", "/api/products?collection=partial-bottles", "/api/collections/partial-bottles",
          "/api/collection/partial-bottles", "/api/collections?slug=partial-bottles", "/api/search?q=partial",
          "/api/inventory", "/api/stock", "/api/products/rayhaan-nocturno-elixir-partial", "/api/revalidate"):
    code, body, hd, final, dt = get(B + u, accept="application/json")
    log(f"[API] {u}: {code} {dt:.2f}s ctype={hd.get('Content-Type')} len={len(body)} :: {body[:200]!r}")

# 4. a product page
if ps:
    slug = ps[0].get("slug")
    for i in range(2):
        code, body, hd, final, dt = get(f"{B}/products/{slug}", {"RSC": "1"}, accept="text/x-component")
        log(f"[PROD] {slug}: {code} {dt:.2f}s len={len(body)} {cache(hd)}")
    for m in list(re.finditer(r'"inStock"|availableForSale|quantityAvailable|inventory', body))[:3]:
        log("[PROD] around:", body[max(0, m.start() - 300):m.end() + 300].replace("\n", " "))

# 5. the shop's myshopify name from an old copy of the site
for u in ("https://web.archive.org/web/2025id_/https://www.whiffculture.com/",
          "https://web.archive.org/web/2026id_/https://www.whiffculture.com/collections/partial-sale"):
    code, body, hd, final, dt = get(u, timeout=40)
    shops = sorted(set(re.findall(r'([a-z0-9][a-z0-9\-]*\.myshopify\.com)', body)))
    log(f"[ARCH] {u}: {code} {dt:.2f}s final={final} len={len(body)} shops={shops}")
    if shops:
        break
else:
    shops = []
for s in shops[:2]:
    q = ('{collection(handle:"partial-bottles"){products(first:250){nodes{id title handle availableForSale '
         'variants(first:3){nodes{id title availableForSale price{amount} compareAtPrice{amount}}}}}}}')
    for ver in ("2025-01", "2025-07"):
        code, body, hd, final, dt = get(f"https://{s}/api/{ver}/graphql.json", {"Content-Type": "application/json"},
                                        accept="application/json", data=json.dumps({"query": q}).encode())
        log(f"[SF] {s} {ver}: {code} {dt:.2f}s len={len(body)} :: {body[:400]!r}")
        try:
            nodes = json.loads(body)["data"]["collection"]["products"]["nodes"]
            log(f"[SF] {len(nodes)} products, in stock {sum(1 for n in nodes if n['availableForSale'])}")
            break
        except Exception as e:
            log("[SF] parse:", type(e).__name__)

# 6. how fresh is the cached list (every 20 s for 6 min)
t_end = time.time() + 360
while time.time() < t_end:
    code, body, hd, final, dt = get(B + "/collections/partial-bottles", {"RSC": "1"}, accept="text/x-component")
    code2, body2, hd2, _, dt2 = get(B + f"/collections/partial-bottles?_={int(time.time()*1000)}", {"RSC": "1"},
                                    accept="text/x-component")
    pp = products(body) or []
    log(f"[FRESH] {code} {dt:.2f}s {cache(hd)} n={len(pp)} in={sum(1 for p in pp if p.get('inStock'))} | "
        f"busted {code2} {dt2:.2f}s {cache(hd2)} same={body2 == body}")
    time.sleep(20)
log("done")
