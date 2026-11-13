#!/usr/bin/env python3
"""Probe #64: perfume watches. (1) find each store's partials/sale collections
(collections.json, all pages; Scentoria title/tag scan), (2) read every planned
watch with plain urllib -- the same client perfume.py uses -- at the planned
pace for ~7 minutes, recording status codes, timings and every stock flip, so
we know how noisy each watch would be before any alert is wired to it."""
import gzip, json, re, time, urllib.error, urllib.request
from collections import Counter, defaultdict

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
SITES = {"whiff": "https://www.whiffculture.com", "scentoria": "https://www.scentoria.co.in",
         "scentira": "https://www.scentira.in", "sillage": "https://www.sillageperfumes.in",
         "sniff": "https://sniff.co.in"}
R = {"collections": {}, "scan": {}, "watches": {}}
T0 = time.time()


def get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                               "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, data, enc, final = r.status, r.read(), r.headers.get("Content-Encoding", ""), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", int((time.time() - t) * 1000), url
    except Exception as e:
        return type(e).__name__, "", int((time.time() - t) * 1000), url
    if "gzip" in enc.lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace"), int((time.time() - t) * 1000), final


def products(base, path, max_pages=12):
    out, pages = [], 0
    for page in range(1, max_pages + 1):
        code, body, ms, _ = get(f"{base}{path}?limit=250&page={page}&_={int(time.time()*1000)}")
        pages += 1
        if code != 200:
            return None, f"HTTP {code}", pages
        try:
            ps = json.loads(body)["products"]
        except Exception:
            return None, "bad json", pages
        out += ps
        if len(ps) < 250:
            break
    return out, "", pages


# ---------- 1. collections on every store
for key, base in SITES.items():
    allc = []
    for page in range(1, 6):
        code, body, ms, final = get(f"{base}/collections.json?limit=250&page={page}")
        if code != 200:
            print(f"{key}: collections.json page {page} -> {code}")
            break
        cs = json.loads(body).get("collections") or []
        allc += cs
        if len(cs) < 250:
            break
        time.sleep(0.4)
    hit = [(c["handle"], c["title"], c.get("products_count")) for c in allc
           if re.search(r"partial|sale|clearance|deal|tester|decant|flash|offer|discount|outlet|last", c["handle"] + " " + c["title"], re.I)]
    R["collections"][key] = hit
    print(f"\n== {key}: {len(allc)} collections; partial/deal-like ({len(hit)}):")
    for h in hit:
        print("   ", h)

# ---------- 2. Scentoria: where do the 'Partial' products live?
ps, why, pages = products(SITES["scentoria"], "/products.json", 16)
if ps is not None:
    part = [p for p in ps if re.search(r"\bpartial\b", p["title"], re.I)]
    av = [p for p in part if any(v.get("available") for v in p["variants"])]
    tags = Counter(t for p in part for t in (p.get("tags") or []))
    types = Counter(p.get("product_type") or "-" for p in part)
    vt = Counter(v.get("title") for p in part for v in p["variants"])
    newest = sorted(((p.get("created_at") or "")[:16], p["title"], any(v.get("available") for v in p["variants"])) for p in part)[-8:]
    R["scan"]["scentoria"] = {"products": len(ps), "pages": pages, "partials": len(part), "partials_in": len(av),
                              "tags": tags.most_common(15), "types": types.most_common(5), "variant_titles": vt.most_common(8),
                              "newest": newest}
    print(f"\n== scentoria /products.json: {len(ps)} products in {pages} pages; {len(part)} titled Partial, {len(av)} in stock")
    print("   tags:", tags.most_common(15))
    print("   types:", types.most_common(5), "| variant titles:", vt.most_common(8))
    print("   newest partials:", newest)
    print("   in-stock partials e.g.:", [(p["title"], p["variants"][0].get("price"), p["variants"][0].get("compare_at_price")) for p in av[:6]])
else:
    print("scentoria products.json failed:", why)

# ---------- 3. the planned watches, read at the planned pace for ~7 minutes
WATCH = [  # (id, site, collection, every_s, variant filter)
    ("whiff-partials", "whiff", "partial-sale", 10, None),
    ("whiff-flash", "whiff", "flash-sale", 30, None),
    ("whiff-testers", "whiff", "testers", 30, None),
    ("scentoria-deals", "scentoria", "deals-of-the-week", 30, None),
    ("scentoria-festive", "scentoria", "festive-sale", 30, None),
    ("scentira-partials", "scentira", "all-partials", 30, r"partial"),
    ("scentira-clearance", "scentira", "clearance", 30, None),
    ("sillage-decants", "sillage", "decants", 30, None),
    ("sniff-50ml", "sniff", "50ml-sale", 30, None),
]
for h, t, n in R["collections"].get("scentoria", []):
    if re.search(r"partial", h + " " + t, re.I):
        WATCH.append((f"scentoria-{h}", "scentoria", h, 30, None))
        print("\n(adding Scentoria collection to the recording:", h, ")")

snap, stats, events = {}, defaultdict(lambda: {"codes": Counter(), "ms": [], "pages": Counter(), "n": []}), defaultdict(list)
nxt = {w[0]: 0 for w in WATCH}
END = T0 + 8 * 60
while time.time() < END:
    now = time.time()
    for wid, site, coll, every, vfilt in WATCH:
        if now < nxt[wid]:
            continue
        nxt[wid] = now + every
        t = time.time()
        ps, why, pages = products(SITES[site], f"/collections/{coll}/products.json", 6)
        s = stats[wid]
        s["ms"].append(int((time.time() - t) * 1000))
        s["pages"][pages] += 1
        if ps is None:
            s["codes"][why] += 1
            continue
        s["codes"]["ok"] += 1
        s["n"].append(len(ps))
        cur = {}
        for p in ps:
            if vfilt:
                for v in p["variants"]:
                    if re.search(vfilt, v.get("title") or "", re.I):
                        cur[f"{p['id']}:{v['id']}"] = (bool(v.get("available")), f"{p['title']} / {v['title']}", v.get("price"))
            else:
                cur[str(p["id"])] = (any(v.get("available") for v in p["variants"]), p["title"], p["variants"][0].get("price") if p["variants"] else None)
        old = snap.get(wid)
        if old is not None:
            ts = time.strftime("%H:%M:%S", time.gmtime(time.time() + 19800))
            for k, (a, title, pr) in cur.items():
                if k not in old:
                    events[wid].append((ts, "NEW " + ("in" if a else "out"), title, pr))
                elif old[k][0] != a:
                    events[wid].append((ts, "-> in" if a else "-> out", title, pr))
            for k in old:
                if k not in cur:
                    events[wid].append((ts, "GONE", old[k][1], old[k][2]))
        snap[wid] = cur
    time.sleep(0.5)

print(f"\n\n== recording {int(time.time() - T0)} s since start (IST {time.strftime('%H:%M', time.gmtime(T0 + 19800))})")
for wid, site, coll, every, vfilt in WATCH:
    s = stats[wid]
    cur = snap.get(wid) or {}
    n_in = sum(1 for a, _, _ in cur.values() if a)
    ms = sorted(s["ms"]) or [0]
    print(f"\n-- {wid} ({SITES[site]}/collections/{coll}, every {every}s): reads {dict(s['codes'])}, pages {dict(s['pages'])}, "
          f"ms median {ms[len(ms)//2]} max {ms[-1]}, items {min(s['n'] or [0])}-{max(s['n'] or [0])}, tracked {len(cur)}, in stock {n_in}")
    for e in events[wid][:30]:
        print("    ", e)
    if len(events[wid]) > 30:
        print(f"     ...and {len(events[wid]) - 30} more events")
    R["watches"][wid] = {"codes": dict(s["codes"]), "pages": dict(s["pages"]), "ms": ms, "n": s["n"],
                         "tracked": len(cur), "in": n_in, "events": events[wid],
                         "sample_in": sorted(t for a, t, _ in cur.values() if a)[:15]}
    print("     in stock e.g.:", R["watches"][wid]["sample_in"][:6])

json.dump(R, open("probe_report.json", "w"), indent=1, default=str)
