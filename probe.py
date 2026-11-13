#!/usr/bin/env python3
"""Probe #65: Scentira's three partials lists compared (which one is complete?),
pagination steadiness of the multi-page lists, and the extra deal collections
(Sillage Steals / Sale, Scentira New Offers / Sale, Whiff's seasonal sales)."""
import gzip, json, re, time, urllib.error, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
R = {}


def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                               "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, data, enc = r.status, r.read(), r.headers.get("Content-Encoding", "")
    except urllib.error.HTTPError as e:
        return e.code, ""
    if "gzip" in enc.lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace")


def products(base, path, max_pages=12):
    out = []
    for page in range(1, max_pages + 1):
        code, body = get(f"{base}{path}?limit=250&page={page}&_={int(time.time()*1000)}")
        if code != 200:
            return None
        ps = json.loads(body)["products"]
        out += ps
        if len(ps) < 250:
            break
        time.sleep(0.3)
    return out


def pv(ps):
    """partial variants: {(pid, vid): (available, title)}"""
    return {(p["id"], v["id"]): (bool(v.get("available")), f"{p['title']} / {v['title']}")
            for p in ps for v in p["variants"] if re.search(r"\bpartial\b", v.get("title") or "", re.I)}


S = "https://www.scentira.in"
allp = products(S, "/products.json", 10)
part = products(S, "/collections/partials/products.json")
allpart = products(S, "/collections/all-partials/products.json")
dpart = products(S, "/collections/diwali-partials/products.json")
for name, ps in (("products.json", allp), ("partials", part), ("all-partials", allpart), ("diwali-partials", dpart)):
    v = pv(ps or [])
    print(f"scentira {name}: {len(ps or [])} products, {len(v)} partial variants, {sum(a for a, _ in v.values())} in stock")
va, vp, vap = pv(allp), pv(part), pv(allpart)
inn = lambda d: {k for k, (a, _) in d.items() if a}
print("  in-stock partial variants in products.json but NOT in 'partials':", len(inn(va) - set(vp)),
      [va[k][1] for k in list(inn(va) - set(vp))[:5]])
print("  ... NOT in 'all-partials':", len(inn(va) - set(vap)), [va[k][1] for k in list(inn(va) - set(vap))[:5]])
print("  products in 'partials' without any partial variant:", sum(1 for p in part or [] if not any(re.search(r'\bpartial\b', v.get('title') or '', re.I) for v in p['variants'])))
vt = {}
for k, (a, t) in va.items():
    s = t.split(" / ", 1)[1]
    vt[s] = vt.get(s, 0) + 1
print("  partial variant titles:", sorted(vt.items(), key=lambda x: -x[1])[:12])
ex = [p for p in allp if any(re.search(r"\bpartial\b", v.get("title") or "", re.I) and v.get("available") for v in p["variants"])][:3]
for p in ex:
    print("  e.g.", p["title"], "|", [(v["title"], v["price"], v.get("compare_at_price"), v["available"]) for v in p["variants"]], "| updated", p.get("updated_at"))

# pagination steadiness: read the multi-page lists 3 times back to back
for base, coll in ((S, "partials"), ("https://www.sillageperfumes.in", "decants")):
    sets = []
    for i in range(3):
        ps = products(base, f"/collections/{coll}/products.json")
        sets.append({p["id"] for p in ps or []})
        time.sleep(2)
    print(f"{base} {coll}: sizes {[len(s) for s in sets]}, ids missing between reads: "
          f"{[len(sets[0] ^ s) for s in sets[1:]]}")

# extra deal collections
for base, coll in (("https://www.sillageperfumes.in", "clearance-sale"), ("https://www.sillageperfumes.in", "sale"),
                   (S, "new-offers"), (S, "sale"), (S, "diwali-sale"),
                   ("https://www.whiffculture.com", "diwali-sale"), ("https://www.whiffculture.com", "pre-diwali-sale"),
                   ("https://www.whiffculture.com", "independence-day-sale"),
                   ("https://www.scentoria.co.in", "partials"), ("https://sniff.co.in", "50ml-sale")):
    ps = products(base, f"/collections/{coll}/products.json")
    if ps is None:
        print(base, coll, "failed")
        continue
    n_in = sum(1 for p in ps if any(v.get("available") for v in p["variants"]))
    disc = []
    for p in ps:
        for v in p["variants"]:
            try:
                pr, c = float(v["price"]), float(v.get("compare_at_price") or 0)
            except (TypeError, ValueError):
                continue
            if v.get("available") and c > pr:
                disc.append(round(100 * (1 - pr / c)))
    newest = sorted(((p.get("published_at") or "")[:10], p["title"][:40]) for p in ps)[-3:]
    print(f"{base}/collections/{coll}: {len(ps)} listed, {n_in} in stock; discounted variants {len(disc)}"
          f" (median {sorted(disc)[len(disc)//2] if disc else '-'}% off); newest {newest}")
    print("    e.g.", [(p["title"][:45], [(v["title"][:20], v["price"], v.get("compare_at_price")) for v in p["variants"][:2]]) for p in ps[:3]])
