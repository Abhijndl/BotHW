#!/usr/bin/env python3
"""Probe #83: the new Whiff reader against the live site and the real memory (no Telegram), plus cache headers."""
import gzip, json, os, re, sys, time, urllib.error, urllib.request

os.environ["PERFUME_STATE"] = "whiff_state.json"
sys.path.insert(0, ".")
import perfume_new as P

T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


st = P.load()
now = time.time()
for w in [w for w in P.WATCHES if w["store"] == "Whiff Culture"]:
    t = time.time()
    prods, why = P.fetch(w)
    dt = time.time() - t
    if prods is None:
        log(f"[DRY] {w['id']}: FAILED {why}")
        continue
    ev, why = P.check(st, w, now, (prods, ""))
    ws = st["w"][w["id"]]
    log(f"[DRY] {w['id']}: read {len(prods)} in {dt:.2f}s, in stock {sum(1 for p in prods if P.available(p['variants']))}, "
        f"events {len(ev)} {[(k, p['title']) for k, _, p, _ in ev][:8]} | memory n={ws.get('n')} learnt={ws.get('learnt')}")
    sample = next((p for p in prods if P.available(p["variants"])), prods[0])
    log(f"[DRY] {w['id']} sample alert:\n" + P.alert_text(w, "new", sample, sample["variants"]))

UA = P.UA
B = P.WHIFF


def get(url, extra=None, accept="*/*"):
    h = {"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"}
    h.update(extra or {})
    t = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=25) as r:
            body, hd, code = r.read(), dict(r.headers), r.status
    except urllib.error.HTTPError as e:
        body, hd, code = e.read() or b"", dict(e.headers or {}), e.code
    raw = len(body)
    if "gzip" in (hd.get("Content-Encoding") or "").lower():
        body = gzip.decompress(body)
    return code, body.decode("utf-8", "replace"), {k: v for k, v in hd.items() if k.lower() != "content-security-policy"}, time.time() - t, raw


for path, extra in (("/collections/partial-bottles", {"RSC": "1"}), ("/new-arrivals", {"RSC": "1"}), ("/sitemap.xml", None)):
    code, body, hd, dt, raw = get(B + path, extra)
    log(f"[HDR] {path}: {code} {dt:.2f}s gz={raw} raw={len(body)} headers={json.dumps(hd)[:900]}")
    if path == "/new-arrivals":
        ps = P.page_products(body) or []
        log("[NEW] first 12:", [(p.get("name"), P.gid(p.get("shopifyId")), p.get("isPartialBottle"),
                                any(v.get("inStock") for v in p.get("variants") or [])) for p in ps[:12]])
        ids = [int(P.gid(p.get("shopifyId")) or 0) for p in ps]
        log(f"[NEW] sorted newest-first by id: {ids == sorted(ids, reverse=True)}; partials among 250: "
            f"{sum(1 for p in ps if p.get('isPartialBottle'))}")
    if path == "/sitemap.xml":
        mods = re.findall(r"<url>\s*<loc>([^<]+)</loc>(?:\s*<lastmod>([^<]+)</lastmod>)?", body)
        log(f"[MAP] {len(mods)} urls, with lastmod: {sum(1 for _, m in mods if m)}; newest lastmods:",
            sorted(((m, u) for u, m in mods if m), reverse=True)[:8])
        log("[MAP] sample:", body[:700].replace("\n", " "))
        for i in range(2):
            time.sleep(5)
            code, body2, hd2, dt2, raw2 = get(B + path)
            log(f"[MAP] again: {code} {dt2:.2f}s cache={hd2.get('X-Vercel-Cache')} same={body2 == body}")
log("done")
