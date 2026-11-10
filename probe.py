#!/usr/bin/env python3
"""Probe #60: Majorette on FirstCry, with the v17.7 tracker's own FirstCry code:
its brand id, every product it lists (names, stock for 248001), what a search
for the DTM series returns, and whether the cart / page / delivery checks work
for a Majorette car. Read-only (the cart is a guest cart; nothing is ordered)."""
import os, re, time, json, importlib.util, traceback
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "GITHUB_ACTIONS": "true"})
spec = importlib.util.spec_from_file_location("b177", "bot_v177.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
R = {}
H = {**b.COMMON_HEADERS, **b._FC_NOCACHE, "Accept": "application/json, text/javascript, */*; q=0.01",
     "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
     "Referer": "https://www.firstcry.com/"}


def api(extra, page=1):
    r = b.http.get(b._fc_bust(b._fc_api_query(page, 20, extra)), headers=H, cookies=b._fc_cookies(),
                   timeout=20, **b._IMPERSONATE)
    try:
        return r.status_code, b._fc_unwrap(r.json())
    except Exception:
        return r.status_code, None


def brief(p):
    st, n = b._fc_api_stock(p)
    return {"pid": str(b._ci(p, *b._ID_KEYS)), "name": b._fc_name(str(b._ci(p, *b._NAME_KEYS) or "")),
            "stock": st, "n": n, "mrp": b._ci(p, "mrp"), "brand": b._ci(p, "BNm"), "sub": b._ci(p, "SCNm"),
            "cat": b._ci(p, "CNm")}


def step(name, fn):
    print(f"\n=== {name}", flush=True)
    try:
        fn()
    except Exception:
        print("FAILED:", traceback.format_exc()[-600:])


def s1():
    code, d = api({})
    hw = b._fc_api_products(d)
    print("hot wheels page 1:", code, len(hw), "products")
    if hw:
        print("record keys:", sorted(hw[0].keys()))
        print("sample:", json.dumps(hw[0], ensure_ascii=False)[:900])
        R["hw_sample"] = hw[0]


def s4():
    bid = "1335"      # https://www.firstcry.com/majorette/5/0/1335
    R["brand_id"] = bid
    if not bid:
        print("no brand id found")
        return
    allp = {}
    for label, extra in (("MasterBrand", {"MasterBrand": bid}), ("BrandId", {"MasterBrand": "", "BrandId": bid})):
        got, page = {}, 1
        while page <= 25:
            code, d = api(extra, page)
            ps = b._fc_api_products(d) if d is not None else []
            for p in ps:
                got[str(b._ci(p, *b._ID_KEYS))] = p
            if len(ps) < 20:
                break
            page += 1
        brands = sorted({str(b._ci(p, "BNm")) for p in got.values()})
        print(f"sweep by {label}={bid}: {len(got)} products over {page} page(s); brands {brands[:6]}")
        if len(got) > len(allp):
            allp = got
    rows = sorted((brief(p) for p in allp.values()), key=lambda x: x["name"])
    R["majorette_all"] = rows
    R["majorette_raw"] = list(allp.values())[:400]
    ins = [x for x in rows if x["stock"] == "in_stock"]
    print(f"Majorette on FirstCry: {len(rows)} products, {len(ins)} in stock for 248001")
    for x in rows:
        print("   ", x["pid"], "|", x["name"][:100], "|", x["stock"], x["n"], "| ₹", x["mrp"], "|", x["sub"])
    code, d = api({"MasterBrand": bid, "OutOfStock": "1"})
    ps = b._fc_api_products(d) if d is not None else []
    print(f"in-stock-only filter page 1: HTTP {code}, {len(ps)} products, all with stock>0: "
          f"{all((b._fc_api_stock(p)[1] or 0) > 0 for p in ps)}")


def s5():
    rows = R.get("majorette_all") or []
    ins = [x["pid"] for x in rows if x["stock"] == "in_stock"][:3]
    oos = [x["pid"] for x in rows if x["stock"] == "out_of_stock"][:2]
    pick = ins + oos
    print("checking", pick)
    if not pick:
        return
    for p in pick[:3]:
        pg = b.fc_page(p)
        print("page", p, "->", None if pg is None else {k: {kk: v.get(kk) for kk in ("cs", "pn", "mrp", "gid", "gone")} for k, v in list(pg.items())[:4]})
    cart = b.fc_cart_check(pick)
    print("cart ->", json.dumps(cart, ensure_ascii=False)[:900] if cart is not None else None)
    try:
        dl = b.fc_delivery(pick)
        print("delivery ->", json.dumps(dl, ensure_ascii=False, default=str)[:600])
    except Exception as e:
        print("delivery error", repr(e)[:200])
    p = pick[0]
    nm = next(x["name"] for x in rows if x["pid"] == p)
    for u in (f"https://www.firstcry.com/hot-wheels/{b._fc_slug(nm)}/{p}/product-detail",
              f"https://www.firstcry.com/majorette/{b._fc_slug(nm)}/{p}/product-detail"):
        q = b.http.get(u, headers={**b.COMMON_HEADERS}, timeout=20, **b._IMPERSONATE)
        canon = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', q.text)
        print("link", u[:70], "->", q.status_code, str(q.url)[:110], "| canonical:", canon.group(1) if canon else None)
    R["checks"] = {"pick": pick, "cart": cart}


for nm, fn in (("4 majorette brand sweep", s4), ("5 cart / page / delivery for majorette", s5)):
    step(nm, fn)
json.dump(R, open("probe_report.json", "w"), ensure_ascii=False, indent=1, default=str)
