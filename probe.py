#!/usr/bin/env python3
"""Probe #84: is Whiff Culture's partials page behind its search list, and do HEAD requests show page versions."""
import gzip, json, re, time, urllib.error, urllib.request

T0 = time.time()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
B = "https://www.whiffculture.com"


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def req(url, extra=None, accept="*/*", method="GET"):
    h = {"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"}
    h.update(extra or {})
    t = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h, method=method), timeout=25) as r:
            body, hd, code = r.read(), dict(r.headers), r.status
    except urllib.error.HTTPError as e:
        body, hd, code = e.read() or b"", dict(e.headers or {}), e.code
    raw = len(body)
    if "gzip" in (hd.get("Content-Encoding") or "").lower() and body:
        body = gzip.decompress(body)
    return code, body.decode("utf-8", "replace"), hd, time.time() - t, raw


def products(body):
    i = body.find('"initialProducts":')
    if i < 0:
        return None
    return json.JSONDecoder().raw_decode(body, i + len('"initialProducts":'))[0]


def v(hd):
    return f"date={hd.get('Date')} age={hd.get('Age')} cache={hd.get('X-Vercel-Cache')} len={hd.get('Content-Length')}"


# 1. HEAD vs GET
for i in range(3):
    c1, b1, h1, d1, r1 = req(B + "/collections/partial-bottles", {"RSC": "1"}, "text/x-component", "HEAD")
    c2, b2, h2, d2, r2 = req(B + "/collections/partial-bottles", {"RSC": "1"}, "text/x-component")
    log(f"[HEAD] {c1} {d1:.2f}s bytes={r1} {v(h1)} | GET {c2} {d2:.2f}s bytes={r2} {v(h2)}")
    time.sleep(3)
c, b, h, d, r = req(B + "/collections/partial-bottles", None, "text/html", "HEAD")
log(f"[HEAD html] {c} {d:.2f}s bytes={r} {v(h)}")

# 2. partials in the search list but not on the partials page
c, body, h, d, r = req(B + "/api/products", None, "application/json")
sp = json.loads(body)["products"]
log(f"[API] {c} {d:.2f}s {v(h)} n={len(sp)}")
c, body, h, d, r = req(B + "/collections/partial-bottles", {"RSC": "1"}, "text/x-component")
pb = products(body) or []
pslugs = {p.get("slug") for p in pb}
part = [p for p in sp if re.search(r"\bpartial", str(p.get("name", "")), re.I)]
extra = [p for p in part if p.get("slug") not in pslugs]
missing = [p.get("slug") for p in pb if p.get("slug") not in {q.get("slug") for q in sp}]
log(f"[CMP] partial-looking in search: {len(part)}, on partials page: {len(pb)}, extra in search: {len(extra)}, "
    f"on page but not in search: {len(missing)} {missing[:10]}")
for p in extra[:25]:
    slug = p.get("slug")
    c, body, h, d, r = req(f"{B}/products/{slug}", {"RSC": "1"}, "text/x-component")
    m = re.search(r'"slug":"' + re.escape(slug) + r'".{0,400}?', body)
    sid = re.search(r'"shopifyId":"gid://shopify/Product/(\d+)"', body)
    i = body.find('"variants":[')
    vs = json.JSONDecoder().raw_decode(body, i + len('"variants":'))[0] if i >= 0 else []
    flags = {k: re.search(r'"' + k + r'":(true|false)', body).group(1) if re.search(r'"' + k + r'":(true|false)', body) else None
             for k in ("isPartialBottle", "isTester", "isSale")}
    log(f"[EXTRA] {p.get('brand')} | {p.get('name')} | {slug} -> {c} {d:.2f}s {v(h)} id={sid.group(1) if sid else None} "
        f"stock={[x.get('inStock') for x in vs][:4]} price={p.get('defaultPrice')} {flags}")

# 3. product-page shape, for a known partial
if pb:
    slug = pb[-1].get("slug")
    c, body, h, d, r = req(f"{B}/products/{slug}", {"RSC": "1"}, "text/x-component")
    i = body.find('"shopifyId"')
    log(f"[PROD] {slug}: {c} bytes={r} {v(h)} keys-near: {body[max(0, i - 300):i + 200]}")
    for k in ('"product":{', '"initialProduct":', '"productData":'):
        log(f"[PROD] has {k}: {k in body}")
log("done")
