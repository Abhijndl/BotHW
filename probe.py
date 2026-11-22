#!/usr/bin/env python3
"""Probe #78: how fast Whiff Culture's partials list can be read from GitHub."""
import gzip, json, time, urllib.error, urllib.request

T0 = time.time()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
W = "https://www.whiffculture.com"


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                               "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"})
    t1 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            code, data, enc, hd = r.status, r.read(), r.headers.get("Content-Encoding", ""), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, "", 0, time.time() - t1, dict(e.headers or {})
    raw = len(data)
    if "gzip" in enc.lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace"), raw, time.time() - t1, hd


# the collection itself: is there a cheap "something changed" signal?
for i in range(3):
    code, body, raw, dt, hd = get(f"{W}/collections/partial-sale.json?_={int(time.time() * 1000)}")
    try:
        c = json.loads(body).get("collection") or {}
    except Exception:
        c = {}
    log(f"[COLL] {code} {raw} B {dt:.2f}s products_count={c.get('products_count')} updated_at={c.get('updated_at')} "
        f"sort={c.get('sort_order')} keys={sorted(c.keys())[:14]} cache={hd.get('Cache-Control') or hd.get('cache-control')} "
        f"age={hd.get('Age') or hd.get('age')} cf={hd.get('CF-Cache-Status') or hd.get('cf-cache-status')}")
    time.sleep(1)

code, body, raw, dt, hd = get(f"{W}/collections/partial-sale/products.json?limit=250&_={int(time.time() * 1000)}")
ps = json.loads(body).get("products") or []
log(f"[LIST] {code} {len(ps)} products, {raw} B gzipped / {len(body)} B, {dt:.2f}s; "
    f"first created: {[p.get('created_at', '')[:16] for p in ps[:5]]}; published: {[p.get('published_at', '')[:16] for p in ps[:3]]}")
newest = sorted(ps, key=lambda p: p.get("created_at") or "", reverse=True)[:5]
log("[LIST] newest 5:", [(p.get("created_at", "")[:16], p.get("title", "")[:40]) for p in newest])
log("[LIST] positions of the newest 5 in the list:", [ps.index(p) for p in newest])
for q in ("sort_by=created-descending", "sort_by=updated-descending"):
    code, body, raw, dt, hd = get(f"{W}/collections/partial-sale/products.json?limit=10&{q}&_={int(time.time() * 1000)}")
    try:
        p2 = json.loads(body).get("products") or []
    except Exception:
        p2 = []
    log(f"[SORT] {q}: {code}, first created: {[p.get('created_at', '')[:16] for p in p2[:5]]}")
code, body, raw, dt, hd = get(f"{W}/collections/partial-sale/products.json?limit=5&_={int(time.time() * 1000)}")
log(f"[SMALL] limit=5: {code} {raw} B {dt:.2f}s")
code, body, raw, dt, hd = get(f"{W}/collections.json?limit=250")
try:
    cols = json.loads(body).get("collections") or []
except Exception:
    cols = []
log("[COLLS]", [(c.get("handle"), c.get("products_count"), (c.get("updated_at") or "")[:16]) for c in cols
                if any(w in (c.get("handle") or "") for w in ("partial", "decant", "new", "flash", "tester", "sale"))])

# pace: the whole partials list every 3 s for 3 minutes, then every 1.5 s for a minute
for gap, secs in ((3.0, 180), (1.5, 60)):
    codes, lat, sizes, t1 = [], [], [], time.time()
    while time.time() - t1 < secs:
        t2 = time.time()
        code, body, raw, dt, hd = get(f"{W}/collections/partial-sale/products.json?limit=250&_={int(time.time() * 1000)}")
        codes.append(code)
        lat.append(dt)
        sizes.append(raw)
        if code != 200:
            log(f"[PACE {gap}s] request {len(codes)} → {code}; retry-after={hd.get('Retry-After') or hd.get('retry-after')}")
            time.sleep(15)
        time.sleep(max(0, gap - (time.time() - t2)))
    lat.sort()
    log(f"[PACE {gap}s] {len(codes)} reads, {sum(1 for c in codes if c == 200)} ok, latency median {lat[len(lat) // 2]:.2f}s "
        f"p90 {lat[int(len(lat) * 0.9)]:.2f}s, {sum(sizes) / max(1, len(sizes)) / 1024:.0f} KB each (gzipped)")
log("done")
