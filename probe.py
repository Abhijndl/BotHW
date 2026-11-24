#!/usr/bin/env python3
"""Probe #79: what Whiff Culture's new site is made of, and where its partials live now."""
import gzip, json, re, time, urllib.error, urllib.request

T0 = time.time()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def get(url, accept="text/html,application/json;q=0.9,*/*;q=0.8"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip",
                                               "Accept-Language": "en-IN,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data, hd, code, final = r.read(), dict(r.headers), r.status, r.geturl()
    except urllib.error.HTTPError as e:
        data, hd, code, final = e.read() or b"", dict(e.headers or {}), e.code, url
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", {}, url
    if "gzip" in (hd.get("Content-Encoding") or hd.get("content-encoding") or "").lower():
        try:
            data = gzip.decompress(data)
        except Exception:
            pass
    return code, data.decode("utf-8", "replace"), hd, final


for u in ("https://www.whiffculture.com/", "https://whiffculture.com/", "https://www.whiffculture.com/products.json?limit=3",
          "https://www.whiffculture.com/collections.json?limit=250", "https://www.whiffculture.com/collections/partial-sale",
          "https://www.whiffculture.com/collections/partial-sale/products.json?limit=3"):
    code, body, hd, final = get(u)
    hdrs = {k: v for k, v in hd.items() if k.lower() in ("server", "x-powered-by", "x-shopid", "x-shopify-stage",
                                                          "powered-by", "x-nextjs-cache", "x-vercel-id", "cf-ray",
                                                          "content-type", "location", "x-wix-request-id", "set-cookie")}
    log(f"[GET] {u} → {code} final={final} len={len(body)} headers={json.dumps(hdrs)[:500]}")
    if u.endswith("/"):
        hints = {k: bool(re.search(p, body, re.I)) for k, p in {
            "shopify": r"cdn\.shopify|Shopify\.theme|myshopify", "next": r"__NEXT_DATA__|/_next/", "woo": r"woocommerce|wp-content",
            "wix": r"wix\.com|_wixCIDX", "nuxt": r"__NUXT__", "magento": r"Magento|mage/", "odoo": r"odoo",
            "dukaan": r"dukaan", "shopflo": r"shopflo", "bigcommerce": r"bigcommerce", "react": r"react",
            "gokwik": r"gokwik", "zecpe": r"zecpe"}.items()}
        log("[HTML] platform hints:", hints)
        links = sorted(set(re.findall(r'href="(/[^"#?]{1,120})', body)))
        log("[HTML] links:", [l for l in links if re.search(r"partial|decant|sale|flash|tester|collection|categor|shop|product", l, re.I)][:80])
        apis = sorted(set(re.findall(r'["\'](https?://[^"\']*(?:api|graphql|storefront)[^"\']*)["\']', body, re.I)))[:30]
        log("[HTML] api-looking urls:", apis)
        scripts = sorted(set(re.findall(r'<script[^>]+src="([^"]+)"', body)))[:40]
        log("[HTML] scripts:", scripts)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
        if m:
            log("[HTML] __NEXT_DATA__ start:", m.group(1)[:1500])
        log("[HTML] head:", re.sub(r"\s+", " ", body[:1500]))
log("done")
