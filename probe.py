#!/usr/bin/env python3
"""Probe #43: Karz & Dolls — (1) which link opens a product whose own slug has a
'?' in it (the McLaren 720S LB?WORKS alert opened a 404), (2) does KND find a
product by its pid alone, (3) which shelf each of the two same-named McLarens is
on (Mini GT vs Mini GT blister pack), (4) does KND's product data say box or
blister anywhere. Read-only."""
import json, re, time, html
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
KD = "https://www.karzanddolls.com"
PIDS = ["OyLoZkMNb2", "RnLjVk9Lm0"]          # the two "MCLAREN 720S LB?WORKS THE BORING CONCEPT"
CONTROL = ("mini-gt-mclaren-750s-saros-grey", "XqLQbJRpvD")
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
report = {}


def get(url):
    t0 = time.time()
    try:
        r = http.get(url, headers=H, timeout=25, allow_redirects=True, **IMP)
        return r.status_code, r.text, str(r.url), round(time.time() - t0, 2)
    except Exception as e:
        return None, "", "", f"{type(e).__name__}"


def products(page):
    m = NEXT.search(page or "")
    if not m:
        return []
    try:
        props = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
    except Exception:
        return []
    found, stack = [], [props]
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            if "pid" in n and "pro_name" in n:
                found.append(n)
            else:
                stack.extend(n.values())
    return found


print("=== 1. shelves: where are the two McLarens, and what does KND say about them ===")
shelves = {}
for path in ["/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack", "/pre-orders/pre-order-minigt", "/"]:
    code, page, final, secs = get(KD + path)
    ps = products(page)
    shelves[path] = ps
    hits = [p for p in ps if str(p.get("pid")) in PIDS or "BORING" in str(p.get("pro_name", "")).upper()]
    print(f"{path}: HTTP {code}, {len(ps)} products, {secs}s; McLaren LB?WORKS here: {[p.get('pid') for p in hits]}")
    for p in hits:
        print("   ", json.dumps(p, ensure_ascii=False)[:1500])
    # how KND's own page links them
    for pid in PIDS:
        for mm in re.finditer(r'href="([^"]*pid=' + pid + r'[^"]*)"', page or ""):
            print(f"    KND's own link for {pid}: {html.unescape(mm.group(1))!r}")
    report[path] = {"code": code, "n": len(ps), "hits": hits}

print("\n=== 2. which link opens the product ===")
slug = "mclaren-720s-lb?works-the-boring-concept"
for pid in PIDS[:1]:
    for label, url in [
        ("bot's link (%3F)", f"{KD}/details/mclaren-720s-lb%3Fworks-the-boring-concept?pid={pid}"),
        ("raw '?' in slug", f"{KD}/details/{slug}?pid={pid}"),
        ("'?' removed", f"{KD}/details/mclaren-720s-lbworks-the-boring-concept?pid={pid}"),
        ("'?' → '-'", f"{KD}/details/mclaren-720s-lb-works-the-boring-concept?pid={pid}"),
        ("'?' → '★' encoded", f"{KD}/details/mclaren-720s-lb%E2%98%85works-the-boring-concept?pid={pid}"),
        ("any slug 'x'", f"{KD}/details/x?pid={pid}"),
        ("no slug", f"{KD}/details?pid={pid}"),
    ]:
        code, page, final, secs = get(url)
        title = re.search(r"<title>(.*?)</title>", page or "", re.S)
        has = pid in (page or "") and "BORING" in (page or "").upper()
        not_found = "Page not found" in (page or "") or "404" in (title.group(1) if title else "")
        print(f"  {label:22} HTTP {code} {secs}s  shows product: {has}  404 page: {not_found}  title: {(title.group(1).strip()[:70] if title else '-')!r}  final: {final[:110]}")
        report[f"link:{label}"] = {"code": code, "has": has, "nf": not_found, "final": final}
print("  control (a normal product, wrong slug 'x'):")
for label, url in [("its own slug", f"{KD}/details/{CONTROL[0]}?pid={CONTROL[1]}"), ("slug 'x'", f"{KD}/details/x?pid={CONTROL[1]}")]:
    code, page, final, secs = get(url)
    title = re.search(r"<title>(.*?)</title>", page or "", re.S)
    print(f"  {label:22} HTTP {code}  shows product: {CONTROL[1] in (page or '')}  404 page: {'Page not found' in (page or '')}  title: {(title.group(1).strip()[:70] if title else '-')!r}")

print("\n=== 3. the product page's own data: anything about box / blister? ===")
for pid in PIDS + [CONTROL[1]]:
    s = slug if pid in PIDS else CONTROL[0]
    for url in (f"{KD}/details/x?pid={pid}", f"{KD}/details/{s}?pid={pid}"):
        code, page, final, secs = get(url)
        m = NEXT.search(page or "")
        if not m:
            continue
        try:
            pp = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
        except Exception:
            continue
        txt = json.dumps(pp, ensure_ascii=False)
        print(f"--- {pid} via {url[len(KD):][:60]}: pageProps keys {list(pp)[:20]}")
        for w in ("blister", "box", "packag", "pack"):
            for mm in list(re.finditer(w, txt, re.I))[:4]:
                print(f"   '{w}': …{txt[max(0, mm.start() - 120):mm.end() + 120]}…")
        prod = None
        for k, v in pp.items():
            if isinstance(v, dict) and ("pro_name" in v or "pid" in v):
                prod = v
        if prod is None:
            for v in pp.values():
                if isinstance(v, list) and v and isinstance(v[0], dict) and "pro_name" in v[0]:
                    prod = v[0]
        if prod:
            print("   product fields:", json.dumps({k: (str(v)[:120]) for k, v in prod.items()}, ensure_ascii=False)[:2500])
        report[f"page:{pid}"] = pp
        break
json.dump(report, open("probe_report.json", "w"), ensure_ascii=False, default=str)
