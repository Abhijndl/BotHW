#!/usr/bin/env python3
"""Probe #51: Karz & Dolls unit counts. Every in-stock car on the shelves the
tracker reads: its product page's product_attr qty, add_limit, and what the page
itself shows (Add to Cart / Out of Stock / a quantity box and its max). Is qty a
real count? How many in-stock cars say 0? Read-only."""
import json, re, collections, html as H_
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
KD = "https://www.karzanddolls.com"
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
SHELVES = ["/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack", "/specials/special-stocks-64-43-scale", "/", "/specials/chase-car",
           "/mini-gt/kaido-house", "/pre-orders/pre-order-minigt", "/hot-wheels/mainlines", "/hot-wheels/pop-culture",
           "/hot-wheels/card-art-premiums", "/hot-wheels/gift-pack", "/hot-wheels/car-culture", "/hot-wheels/team-transport",
           "/hot-wheels/character-cars", "/hot-wheels/hot-wheels-accessories"]


def get(url):
    for _ in range(2):
        try:
            r = http.get(url, headers=H, timeout=25, **IMP)
            return r.status_code, r.text
        except Exception:
            pass
    return None, ""


def nd(page):
    m = NEXT.search(page or "")
    return json.loads(m.group(1)) if m else {}


def prods(page):
    pp = (nd(page).get("props") or {}).get("pageProps") or {}
    found, stack = [], [pp]
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            if "pid" in n and "pro_name" in n and "slug" in n:
                found.append(n)
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
    return found


def kd_url(slug, pid):
    path = "".join(quote(quote(c, safe=""), safe="") if c in "?#%" else quote(c, safe="-_.~") for c in slug)
    return f"{KD}/details/{path}?pid={quote(pid, safe='')}"


shelf_of, allp = {}, {}
with ThreadPoolExecutor(8) as ex:
    for s, (code, page) in zip(SHELVES, ex.map(lambda s: get(KD + s), SHELVES)):
        for p in prods(page):
            if str(p.get("in_stock")) == "1":
                allp.setdefault(str(p["pid"]), p)
                shelf_of.setdefault(str(p["pid"]), s)
print(f"{len(allp)} in-stock products on {len(SHELVES)} shelves")


def look(pid):
    p = allp[pid]
    code, page = get(kd_url(str(p["slug"]).strip(), pid))
    d = ((nd(page).get("props") or {}).get("pageProps") or {}).get("productdetails") or {}
    try:
        attr = json.loads(d.get("product_attr") or "{}")
    except Exception:
        attr = {"raw": str(d.get("product_attr"))[:80]}
    resp = (attr.get("response") or []) if isinstance(attr, dict) else []
    qtys = [r.get("qty") for r in resp if isinstance(r, dict)]
    body = re.sub(r"<script.*?</script>", " ", page or "", flags=re.S)
    words = {w: body.count(w) for w in ("Add to Cart", "ADD TO CART", "Out of Stock", "OUT OF STOCK", "Sold Out", "SOLD OUT",
                                          "Notify Me", "NOTIFY ME", "Buy Now", "BUY NOW") if body.count(w)}
    maxes = re.findall(r'<input[^>]*type="number"[^>]*>', body)[:2]
    return {"pid": pid, "http": code, "shelf": shelf_of[pid], "nm": str(p.get("pro_name")).strip()[:70],
            "sku": re.sub(r"\s+", " ", str(p.get("sku"))).strip()[:40], "price": p.get("dis_price"),
            "pre": p.get("is_preorder"), "type": p.get("type"), "in_stock": d.get("in_stock"), "lim": d.get("add_limit"),
            "qtys": qtys, "n_attr": len(resp), "attr_keys": sorted({k for r in resp if isinstance(r, dict) for k in r})[:8],
            "words": words, "num_inputs": maxes, "id": d.get("id")}


with ThreadPoolExecutor(8) as ex:
    rows = list(ex.map(look, list(allp)))
ok = [r for r in rows if r["http"] == 200]
print(f"pages read: {len(ok)} of {len(rows)}")
def q0(r):
    try:
        return int(r["qtys"][0])
    except Exception:
        return None
dist = collections.Counter("none" if q0(r) is None else "0" if q0(r) == 0 else "1" if q0(r) == 1 else "2-5" if q0(r) <= 5
                           else "6-20" if q0(r) <= 20 else "21-100" if q0(r) <= 100 else ">100" for r in ok)
print("qty on the product page of in-stock cars:", dict(dist))
print("product_attr shapes:", collections.Counter((r["n_attr"], tuple(r["attr_keys"])) for r in ok).most_common(5))
print("page words (qty>0):", collections.Counter(tuple(sorted(r["words"])) for r in ok if (q0(r) or 0) > 0).most_common(4))
print("page words (qty=0):", collections.Counter(tuple(sorted(r["words"])) for r in ok if q0(r) == 0).most_common(4))
print("number inputs seen:", collections.Counter(tuple(r["num_inputs"]) for r in ok).most_common(3))
by_shelf = collections.defaultdict(collections.Counter)
for r in ok:
    by_shelf[r["shelf"]]["0" if q0(r) == 0 else ("none" if q0(r) is None else ">0")] += 1
print("by shelf:", {k: dict(v) for k, v in by_shelf.items()})
by_pre = collections.Counter((str(r["pre"]), "0" if q0(r) == 0 else ">0") for r in ok)
print("by pre-order flag:", dict(by_pre))
print("\nqty = 0 while in stock (first 25):")
for r in [r for r in ok if q0(r) == 0][:25]:
    print(f"  {r['shelf']:30} ₹{r['price']:<5} lim={r['lim']:<3} pre={r['pre']} type={r['type']} id={r['id']} {r['nm'][:52]!r} {r['sku']!r}")
print("\nqty > 0 (sample of 15):")
for r in [r for r in ok if (q0(r) or 0) > 0][:15]:
    print(f"  {r['shelf']:30} ₹{r['price']:<5} lim={r['lim']:<3} qty={r['qtys']} id={r['id']} {r['nm'][:52]!r}")
json.dump(rows, open("probe_report.json", "w"), indent=1, ensure_ascii=False)
