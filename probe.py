#!/usr/bin/env python3
"""Probe #82: does Whiff Culture's new site keep the same products, and how often do its lists refresh."""
import gzip, hashlib, json, re, time, urllib.error, urllib.request

T0 = time.time()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
B = "https://www.whiffculture.com"
OLD = json.load(open("whiff_old.json"))


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def get(url, extra=None, accept="text/html,application/json;q=0.9,*/*;q=0.8", timeout=25):
    h = {"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"}
    h.update(extra or {})
    req = urllib.request.Request(url, headers=h)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body, hd, code = r.read(), dict(r.headers), r.status
    except urllib.error.HTTPError as e:
        body, hd, code = e.read() or b"", dict(e.headers or {}), e.code
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", {}, time.time() - t, 0
    raw = len(body)
    if "gzip" in (hd.get("Content-Encoding") or "").lower():
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
    return code, body.decode("utf-8", "replace"), hd, time.time() - t, raw


def rsc(path):
    return get(B + path, {"RSC": "1"}, accept="text/x-component")


def products(body):
    i = body.find('"initialProducts":')
    if i < 0:
        return None
    arr, _ = json.JSONDecoder().raw_decode(body, i + len('"initialProducts":'))
    return arr


def sid(p):
    return str(p.get("shopifyId") or "").rsplit("/", 1)[-1]


def avail(p):
    return any(v.get("inStock") is True for v in p.get("variants") or [])


def cache(hd):
    return f"{hd.get('X-Vercel-Cache')} age={hd.get('Age')}"


# 1. same products as before?
for wid, path in (("whiff-partials", "/collections/partial-bottles"), ("whiff-flash", "/collections/sale"),
                  ("whiff-flash", "/collections/flash-sale"), ("whiff-testers", "/collections/testers")):
    code, body, hd, dt, raw = rsc(path)
    ps = products(body) or []
    new = {sid(p): avail(p) for p in ps}
    old = OLD[wid]
    both = set(new) & set(old)
    agree = sum(1 for k in both if new[k] == old[k])
    log(f"[SAME] {path}: {code} {dt:.2f}s gz={raw} raw={len(body)} {cache(hd)} n={len(ps)} in={sum(new.values())} | "
        f"old n={len(old)} in={sum(old.values())} | overlap={len(both)} stock agrees={agree}")
    only_new = [(p.get("brand"), p.get("name"), avail(p)) for p in ps if sid(p) not in old]
    log(f"[SAME] {path}: not in old memory ({len(only_new)}):", only_new[:12])
    flips = [(p.get("name"), old[sid(p)], avail(p)) for p in ps if sid(p) in old and old[sid(p)] != avail(p)]
    log(f"[SAME] {path}: stock differs ({len(flips)}):", flips[:12])
    if ps and wid == "whiff-flash":
        log("[SAME] a sale product:", json.dumps({k: ps[0].get(k) for k in ("name", "brand", "defaultPrice", "originalPrice", "isSale", "tags", "variants")})[:900])

# 2. menu, sitemap and the routes the cache purge mentions
code, body, hd, dt, raw = get(B + "/api/menu", accept="application/json")
log(f"[MENU] {code} {dt:.2f}s {cache(hd)} :: {body[:1500]}")
code, body, hd, dt, raw = get(B + "/sitemap.xml", accept="application/xml")
locs = re.findall(r"<loc>([^<]+)</loc>", body)
log(f"[MAP] {code} {dt:.2f}s {cache(hd)} {len(locs)} urls; collections:",
    sorted({u.split('/collections/')[1] for u in locs if '/collections/' in u})[:80])
log("[MAP] non-product urls:", [u for u in locs if "/products/" not in u][:60])
for path in ("/new-arrivals", "/collections/new-arrivals", "/collections/new", "/shop", "/catalog", "/collections/all"):
    code, body, hd, dt, raw = rsc(path)
    ps = products(body)
    arrays = len(re.findall(r'"shopifyId":"gid://shopify/Product/', body))
    log(f"[ROUTE] {path}: {code} {dt:.2f}s gz={raw} {cache(hd)} initialProducts={None if ps is None else len(ps)} shopifyIds={arrays}")
code, body, hd, dt, raw = get(B + "/api/products", accept="application/json")
try:
    ap = json.loads(body)["products"]
except Exception:
    ap = []
log(f"[APIP] {code} {dt:.2f}s gz={raw} {cache(hd)} cc={hd.get('Cache-Control')} n={len(ap)} keys={sorted(ap[0].keys()) if ap else None}")
if ap:
    part = [p for p in ap if p.get("isPartialBottle") or "partial" in str(p.get("name", "")).lower()]
    log(f"[APIP] partial-looking: {len(part)}; sample:", json.dumps(part[:1])[:900])

# 3. how often the lists refresh (every 30 s for 12 min)
prev = {}
t_end = time.time() + 720
while time.time() < t_end:
    row = []
    for path in ("/collections/partial-bottles", "/collections/sale", "/collections/testers"):
        code, body, hd, dt, raw = rsc(path)
        ps = products(body) or []
        h = hashlib.md5(json.dumps(sorted((sid(p), avail(p)) for p in ps)).encode()).hexdigest()[:8]
        ch = "" if prev.get(path) in (None, h) else " CHANGED"
        prev[path] = h
        row.append(f"{path.rsplit('/', 1)[1]} {code} {cache(hd)} n={len(ps)} in={sum(avail(p) for p in ps)} {h}{ch}")
    code, body, hd, dt, raw = get(B + "/api/products", accept="application/json")
    row.append(f"api {code} {cache(hd)} gz={raw}")
    log("[FRESH] " + " | ".join(row))
    time.sleep(30)
log("done")
