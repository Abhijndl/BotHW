#!/usr/bin/env python3
"""Probe #66: Sovereign Scents and Acordell — platform, partials/decant/sale lists,
how partials and sold-out items appear, and whether GitHub runners can read them."""
import gzip, json, re, time, urllib.error, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
R = {}


def get(url, timeout=15, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                               "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"})
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


def products(base, path, max_pages=20):
    out = []
    for page in range(1, max_pages + 1):
        code, body, _, _, _ = get(f"{base}{path}?limit=250&page={page}&_={int(time.time()*1000)}")
        if code != 200:
            return out or None, code
        try:
            ps = json.loads(body)["products"]
        except Exception:
            return out or None, "not json"
        out += ps
        if len(ps) < 250:
            break
        time.sleep(0.3)
    return out, 200


def avail(p):
    return any(v.get("available") for v in p.get("variants") or [])


for host in ("sovereignscents.in", "acordell.com"):
    print(f"\n==================== {host}")
    base = None
    for b in (f"https://{host}", f"https://www.{host}"):
        code, body, hdr, final, ms = get(b + "/", accept="text/html")
        marks = [m for m in ("cdn.shopify.com", "Shopify.theme", "myshopify", "woocommerce", "wp-content", "wix.com",
                             "dukaan", "_next/static", "zohocommerce", "bigcommerce", "magento", "squarespace", "webflow")
                 if m in body]
        print(f"{b}/ -> {code} in {ms} ms, final {final}, server {hdr.get('Server') or hdr.get('server')}, "
              f"shopify headers {[k for k in hdr if k.lower().startswith(('x-shopid', 'x-shopify', 'powered-by'))]}, marks {marks}")
        if code == 200 and base is None:
            base = final.rstrip("/").split("?")[0]
            base = re.match(r"https?://[^/]+", base).group(0)
    if not base:
        print("homepage unreachable")
        continue
    R[host] = {"base": base}
    code, body, hdr, _, ms = get(f"{base}/products.json?limit=5")
    print(f"/products.json -> {code} in {ms} ms ({len(body)} bytes)")
    if code == 200:
        ps, why = products(base, "/products.json")
        print(f"  all products: {len(ps or [])} ({why})")
        part = [p for p in ps or [] if re.search(r"\bpartial", p["title"], re.I)]
        pvar = [(p, v) for p in ps or [] for v in p.get("variants") or [] if re.search(r"\bpartial", v.get("title") or "", re.I)]
        print(f"  titled partial: {len(part)} ({sum(avail(p) for p in part)} in stock); partial variants: {len(pvar)} ({sum(1 for _, v in pvar if v.get('available'))} in stock)")
        for p in sorted(part, key=lambda p: p.get("created_at") or "")[-6:]:
            print("    e.g.", p["title"][:60], "|", p.get("product_type"), "|", (p.get("created_at") or "")[:10],
                  [(v.get("title")[:25], v.get("price"), v.get("compare_at_price"), v.get("available")) for v in p["variants"][:3]])
        for p, v in pvar[:4]:
            print("    variant e.g.", p["title"][:50], "/", v.get("title"), v.get("price"), v.get("available"))
        tags = {}
        for p in part:
            for t in p.get("tags") or []:
                tags[t] = tags.get(t, 0) + 1
        print("  partial tags:", sorted(tags.items(), key=lambda x: -x[1])[:12])
        cs = []
        for page in range(1, 5):
            c2, b2, _, _, _ = get(f"{base}/collections.json?limit=250&page={page}")
            if c2 != 200:
                print("  collections.json ->", c2)
                break
            got = json.loads(b2).get("collections") or []
            cs += got
            if len(got) < 250:
                break
        print(f"  collections: {len(cs)}")
        for c in cs:
            if re.search(r"partial|decant|sale|tester|deal|offer|clearance|flash|steal|discount|new", c["handle"] + " " + c["title"], re.I):
                print(f"    {c['handle']!r} {c['title']!r} {c.get('products_count')}")
        for c in cs:
            if re.search(r"partial", c["handle"] + " " + c["title"], re.I):
                cp, why = products(base, f"/collections/{c['handle']}/products.json")
                n_in = sum(avail(p) for p in cp or [])
                print(f"  collection {c['handle']}: {len(cp or [])} listed, {n_in} in stock ({why}); count says {c.get('products_count')}")
                ids_all = {p['id'] for p in part}
                ids_c = {p['id'] for p in cp or []}
                print(f"    partial-titled products not in it: {len(ids_all - ids_c)} (in stock: {sum(1 for p in part if p['id'] not in ids_c and avail(p))})")
        # pace: 6 quick reads of the biggest partial list
        t0 = time.time(); codes = []
        for i in range(6):
            codes.append(get(f"{base}/products.json?limit=250&_={int(time.time()*1000)}")[0])
            time.sleep(1)
        print(f"  6 reads in {time.time()-t0:.0f} s: {codes}")
    else:
        for path in ("/wp-json/wc/store/v1/products?per_page=5", "/wp-json/", "/api/products", "/sitemap.xml", "/robots.txt"):
            c2, b2, h2, _, ms = get(base + path, accept="*/*")
            print(f"  {path} -> {c2} in {ms} ms: {b2[:200]!r}")

json.dump(R, open("probe_report.json", "w"), indent=1)
