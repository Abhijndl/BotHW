#!/usr/bin/env python3
"""Probe #76: more Indian diecast stores, Shopify newest-first endpoints,
FirstCry product-page pacing and Matchbox's brand id."""
import json, re, sys, threading, time, traceback, urllib.request

T0 = time.time()
LOCK = threading.Lock()


def log(*a):
    with LOCK:
        print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


src = urllib.request.urlopen("https://raw.githubusercontent.com/Abhijndl/BotHW/main/bot.py", timeout=30).read()
open("bot_main.py", "wb").write(src)
sys.path.insert(0, ".")
import bot_main as B  # noqa: E402
from curl_cffi import requests as http  # noqa: E402

IMP = {"impersonate": "chrome124"}
STORES = ["toycollectorsindia.com", "rywheelz.com", "diecastbharat.com", "minibeesandwheels.com", "kinderlogs.in",
          "1isto64.com", "ogmini.com", "www.ogmini.com", "hobbyshoppy.in", "thepeppystore.in", "zoomsters.in",
          "torquetribe.in", "303diecastshop.in", "toymarche.com", "funcorp.in", "toycra.com", "scalearts.in",
          "www.toycollectorsindia.com", "theminiaturestore.in", "minizone.in"]
WANT = re.compile(r"hot\s*-?\s*wheels?|mini\s*-?\s*gt|majorette|match\s*-?\s*box|kaido", re.I)


def store(dom):
    o = {"dom": dom}
    try:
        r = http.get(f"https://{dom}/products.json?limit=250", headers=B.COMMON_HEADERS, timeout=20, **IMP)
        o["status"] = r.status_code
        if r.status_code != 200:
            o["head"] = r.text[:90].replace("\n", " ")
            return o
        prods = (r.json() or {}).get("products") or []
        o["page1"] = len(prods)
        rel = [p for p in prods if WANT.search(" ".join([p.get("title", ""), p.get("vendor", ""), p.get("product_type", ""),
                                                         " ".join(p.get("tags") or [])]))]
        o["diecast_p1"] = len(rel)
        o["in_p1"] = sum(1 for p in rel if any(v.get("available") for v in p.get("variants") or []))
        if prods:
            p0 = prods[0]
            o["order_p1"] = [(p.get("id"), (p.get("created_at") or "")[:10]) for p in prods[:3]]
            o["variant_keys"] = sorted((p0.get("variants") or [{}])[0].keys())[:30]
            o["sample"] = [(p.get("title", "")[:50], [v.get("available") for v in p.get("variants") or []][:3])
                           for p in rel[:4]]
        # newest first?
        for path in ("/collections/all/products.json?limit=5&sort_by=created-descending",
                     "/products.json?limit=5&sort_by=created-descending",
                     "/collections/all.atom"):
            try:
                t1 = time.time()
                r2 = http.get(f"https://{dom}{path}", headers=B.COMMON_HEADERS, timeout=20, **IMP)
                if r2.status_code == 200 and path.endswith(".atom"):
                    ent = re.findall(r"<title>([^<]{3,80})</title>", r2.text)[1:4]
                    o["atom"] = ent
                elif r2.status_code == 200:
                    ps = (r2.json() or {}).get("products") or []
                    o[path.split("?")[0][:20] + " sorted"] = [(p.get("id"), (p.get("created_at") or "")[:16], p.get("title", "")[:30])
                                                            for p in ps[:3]]
                else:
                    o[path[:24]] = r2.status_code
                o["t_" + path[:12]] = round(time.time() - t1, 2)
            except Exception as e:
                o[path[:24]] = type(e).__name__
    except Exception as e:
        o["err"] = (type(e).__name__ + " " + str(e))[:90]
    return o


def stores():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(5) as ex:
        for o in ex.map(store, STORES):
            log("[SHOP]", json.dumps(o, ensure_ascii=False)[:1500])


bg = threading.Thread(target=stores, daemon=True)
bg.start()

# Matchbox brand id on FirstCry: the brand page and the search page
for u in ("https://www.firstcry.com/matchbox", "https://www.firstcry.com/search?q=matchbox",
          "https://www.firstcry.com/hot-wheels-matchbox", "https://www.firstcry.com/search?q=mini%20gt"):
    try:
        r = http.get(B._fc_bust(u), headers=B.COMMON_HEADERS, timeout=20, **IMP)
        ids = sorted(set(re.findall(r"(?:MasterBrand|brandid|BrandId|brand_id|mbid)['\"=: ]+(\d{2,6})", r.text, re.I)))[:20]
        links = sorted(set(re.findall(r"/([a-z0-9-]*match[a-z0-9-]*)/5/0/(\d+)", r.text, re.I)))[:10]
        log("[FC-MB]", u, r.status_code, r.url[:90], "ids:", ids, "links:", links,
            "names:", re.findall(r'title="([^"]*[Mm]atchbox[^"]{0,60})"', r.text)[:5])
    except Exception as e:
        log("[FC-MB]", u, type(e).__name__)
    time.sleep(1.5)

# product pages one at a time, 1 per 2 s, until FirstCry objects
pids = ["24999461", "24999404", "24961445", "24854851", "24194169", "23033009", "24961454", "24892560", "24963176",
        "24961441", "24961442", "24961443", "24961444", "24961455", "24961456", "24961457", "24961458", "24892748",
        "24892749", "24892755", "24892756", "24892757", "24970767", "24995807", "24995809"]
ok = 0
for i, p in enumerate(pids * 2):
    t1 = time.time()
    try:
        r = http.get(f"https://www.firstcry.com/hot-wheels/x/{p}/product-detail?fresh={int(time.time()*1000)}",
                     headers={**B.COMMON_HEADERS, **B._FC_NOCACHE}, timeout=15, **IMP)
        st = r.status_code
    except Exception as e:
        st = type(e).__name__
    if st != 200:
        log(f"[PAGE] #{i + 1} → {st} after {ok} ok (1 per 2 s)", r.headers.get("server", "") if st in (403, 429) else "")
        if st in (403, 429):
            break
    else:
        ok += 1
    time.sleep(max(0, 2 - (time.time() - t1)))
else:
    log(f"[PAGE] {ok} product pages at 1 per 2 s, no block")

# a burst like the bot's: 8 product pages at once
from concurrent.futures import ThreadPoolExecutor  # noqa: E402


def pg(p):
    try:
        return http.get(f"https://www.firstcry.com/hot-wheels/x/{p}/product-detail?fresh={int(time.time()*1000)}",
                        headers={**B.COMMON_HEADERS, **B._FC_NOCACHE}, timeout=15, **IMP).status_code
    except Exception as e:
        return type(e).__name__


with ThreadPoolExecutor(8) as ex:
    log("[BURST] 8 pages at once:", list(ex.map(pg, pids[:8])))
with ThreadPoolExecutor(8) as ex:
    log("[BURST] 8 more at once:", list(ex.map(pg, pids[8:16])))
time.sleep(3)
log("[BURST] one more after 3 s:", pg(pids[17]))
for k in range(6):
    time.sleep(20)
    log(f"[BURST] +{20 * (k + 1)} s:", pg(pids[18]))

bg.join(timeout=150)
log("done")
