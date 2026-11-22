#!/usr/bin/env python3
"""Probe #77: how fast FirstCry lets one request follow another, and whether
Shopify's /products.json lists the most recently changed products first."""
import json, sys, threading, time, urllib.request

T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


src = urllib.request.urlopen("https://raw.githubusercontent.com/Abhijndl/BotHW/main/bot.py", timeout=30).read()
open("bot_main.py", "wb").write(src)
sys.path.insert(0, ".")
import bot_main as B  # noqa: E402
from curl_cffi import requests as http  # noqa: E402

IMP = {"impersonate": "chrome124"}


def shops():
    for dom in ("zoomsters.in", "toycollectorsindia.com", "kinderlogs.in", "thepeppystore.in", "torquetribe.in",
                "rywheelz.com"):
        try:
            seq = []
            for page in (1, 2):
                r = http.get(f"https://{dom}/products.json?limit=250&page={page}", headers=B.COMMON_HEADERS,
                             timeout=20, **IMP)
                ps = (r.json() or {}).get("products") or [] if r.status_code == 200 else []
                seq += [(p.get("updated_at") or "")[:19] for p in ps]
                time.sleep(0.5)
            desc = all(a >= b for a, b in zip(seq, seq[1:]))
            log(f"[SHOP] {dom}: {len(seq)} on pages 1-2; updated_at descending: {desc}; first: {seq[:4]}; "
                f"page-2 start: {seq[250:252]}")
            r = http.get(f"https://{dom}/collections.json?limit=250", headers=B.COMMON_HEADERS, timeout=20, **IMP)
            cols = (r.json() or {}).get("collections") or [] if r.status_code == 200 else []
            log(f"[SHOP] {dom}: collections.json {r.status_code}, {len(cols)}:",
                [(c.get("handle"), c.get("products_count")) for c in cols
                 if any(w in (c.get("handle") or "") for w in ("hot", "wheel", "mini", "gt", "majorette", "matchbox",
                                                              "kaido", "diecast", "die-cast", "premium", "new"))][:12])
        except Exception as e:
            log(f"[SHOP] {dom}: {type(e).__name__} {e}")


bg = threading.Thread(target=shops, daemon=True)
bg.start()

HDR = {**B.COMMON_HEADERS, **B._FC_NOCACHE, "Accept": "application/json, text/javascript, */*; q=0.01",
       "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
       "Referer": B._FC_API_REFERER}


def one(i):
    q = B._fc_api_query(1 + i % 9, 20, {"OutOfStock": "1", "searchrank": str(int(time.time() * 1000))})
    t1 = time.time()
    try:
        r = http.get(B._fc_bust(q), headers=HDR, timeout=15, **IMP)
        return r.status_code, time.time() - t1
    except Exception as e:
        return type(e).__name__, time.time() - t1


for label, gap, n in (("back to back", 0.0, 60), ("0.3 s apart", 0.3, 60), ("0.6 s apart", 0.6, 40)):
    codes, lat, t1 = [], [], time.time()
    for i in range(n):
        st, dt = one(i)
        codes.append(st)
        lat.append(dt)
        if st != 200:
            break
        time.sleep(gap)
    rate = len(codes) / (time.time() - t1)
    log(f"[FC] {label}: {len(codes)} requests, {sum(1 for c in codes if c == 200)} ok, {rate:.2f}/s, "
        f"median latency {sorted(lat)[len(lat) // 2]:.2f}s, last {codes[-1]}")
    if codes[-1] != 200:
        for k in range(8):
            time.sleep(15)
            st, _ = one(0)
            log(f"[FC]   +{15 * (k + 1)} s → {st}")
            if st == 200:
                break
bg.join(timeout=60)
log("done")
