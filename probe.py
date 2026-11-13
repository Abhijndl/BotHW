#!/usr/bin/env python3
"""Probe #63: which Indian perfume stores the GitHub runner can read (Shopify JSON),
and what deal collections (partials, sale, decants) they have. Read-only, few requests."""
import json, re, time
from curl_cffi import requests as cr

SITES = ["whiffculture.com", "scentoria.co.in", "scentira.in", "sniff.co.in", "sillageperfumes.in",
         "perfumenetwork.in", "thescentstories.com"]
DEAL = re.compile(r"partial|sale|clearance|deal|offer|discount|decant|tester|split|pre.?owned|used|bnib|bottle.?share|last.?chance|outlet|flash", re.I)
R = {}


def get(url):
    t = time.time()
    try:
        r = cr.get(url, impersonate="chrome", timeout=20, headers={"Accept-Language": "en-IN,en;q=0.9"})
        return r.status_code, r.text, int((time.time() - t) * 1000), r.headers.get("server", "")
    except Exception as e:
        return None, repr(e)[:120], int((time.time() - t) * 1000), ""


def prods_of(body):
    try:
        return json.loads(body)["products"]
    except Exception:
        return None


def avail(p):
    return any(v.get("available") for v in p.get("variants", []))


def price(p):
    try:
        return min(float(v["price"]) for v in p.get("variants", []))
    except Exception:
        return None


for site in SITES:
    base = f"https://www.{site}" if site != "sniff.co.in" else f"https://{site}"
    out = {"site": site}
    code, body, ms, server = get(f"{base}/products.json?limit=250")
    ps = prods_of(body) if code == 200 else None
    out.update(products_json=code, ms=ms, server=server)
    if ps is None and code != 200:
        base = f"https://{site}"
        code, body, ms, server = get(f"{base}/products.json?limit=250")
        ps = prods_of(body) if code == 200 else None
        out.update(products_json=code, ms=ms, server=server, base=base)
    print(f"\n===== {site}: products.json -> {code} in {ms} ms (server {server}) {'' if ps is not None else body[:150]!r}")
    if ps is not None:
        allp = list(ps)
        for pg in range(2, 9):
            if len(ps) < 250:
                break
            c2, b2, _, _ = get(f"{base}/products.json?limit=250&page={pg}")
            ps = prods_of(b2) or []
            allp += ps
            time.sleep(0.5)
        n_av = sum(1 for p in allp if avail(p))
        out.update(n_products=len(allp), n_available=n_av)
        partial_titles = [p["title"] for p in allp if re.search(r"partial", p["title"], re.I)]
        out["partials_in_titles"] = len(partial_titles)
        types = {}
        for p in allp:
            types[p.get("product_type") or "-"] = types.get(p.get("product_type") or "-", 0) + 1
        vt = {}
        for p in allp:
            for v in p.get("variants", []):
                vt[v.get("title")] = vt.get(v.get("title"), 0) + 1
        newest = sorted(allp, key=lambda p: p.get("published_at") or "", reverse=True)[:5]
        print(f"  {len(allp)} products, {n_av} in stock; 'partial' in {len(partial_titles)} titles: {partial_titles[:6]}")
        print(f"  types: {sorted(types.items(), key=lambda x: -x[1])[:8]}")
        print(f"  variant titles: {sorted(vt.items(), key=lambda x: -x[1])[:10]}")
        print(f"  newest: {[(p.get('published_at','')[:10], p['title'][:50]) for p in newest]}")
        disc = [p for p in allp if avail(p) and any(v.get("compare_at_price") and float(v["compare_at_price"] or 0) > float(v["price"]) * 1.15 for v in p.get("variants", []))]
        out["discounted_15pct_in_stock"] = len(disc)
        print(f"  in stock with 15%+ off MRP: {len(disc)} e.g. {[(p['title'][:40], price(p)) for p in disc[:4]]}")
    time.sleep(0.5)
    c3, b3, _, _ = get(f"{base}/collections.json?limit=250")
    cols = []
    try:
        cols = json.loads(b3)["collections"]
    except Exception:
        pass
    out["collections"] = len(cols)
    deal_cols = [(c["handle"], c.get("title"), c.get("products_count")) for c in cols if DEAL.search(c["handle"] + " " + (c.get("title") or ""))]
    out["deal_collections"] = deal_cols
    print(f"  collections.json -> {c3}: {len(cols)} collections; deal-like: {deal_cols[:15]}")
    for h, t, n in deal_cols[:6]:
        time.sleep(0.5)
        c4, b4, ms4, _ = get(f"{base}/collections/{h}/products.json?limit=250")
        cp = prods_of(b4) if c4 == 200 else None
        if cp is None:
            print(f"    /collections/{h} -> {c4}")
            continue
        cav = [p for p in cp if avail(p)]
        print(f"    /collections/{h} ({t}): {len(cp)} listed, {len(cav)} in stock, {ms4} ms; e.g. "
              f"{[(p['title'][:45], price(p)) for p in (cav or cp)[:4]]}")
        out.setdefault("deal_detail", []).append({"handle": h, "title": t, "listed": len(cp), "in_stock": len(cav),
                                                  "sample": [(p['title'], price(p), avail(p)) for p in (cav or cp)[:8]]})
    R[site] = out
    time.sleep(1)
json.dump(R, open("probe_report.json", "w"), indent=1, ensure_ascii=False)
