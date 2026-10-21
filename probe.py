#!/usr/bin/env python3
"""Probe #26: can FirstCry's listing be read newest-first (so a brand-new car
is seen within seconds, not at the next 10-minute catalogue read)? Tries sort
values on page 1 and prints the first products (id, stock for 248001, name)."""
import importlib.util, os, random, time
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""})
spec = importlib.util.spec_from_file_location("b", "bot_v16.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m._FC_PCODE_ACTIVE[0] = "248001"
H = {**m.COMMON_HEADERS, "Accept": "application/json, text/javascript, */*; q=0.01",
     "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest", "Referer": m._FC_API_REFERER}
cook = m._fc_cookies()
for sort in ("Popularity", "NewArrivals", "New Arrivals", "newarrivals", "NewArrival", "New", "Latest", "Newest",
             "ProductID", "productid desc", "Discount", "BestSeller", "Rating", "PriceLowToHigh"):
    for oos in ("", "1"):
        url = m._fc_api_query(1, 20, {"SortExpression": sort, "OutOfStock": oos, "searchrank": str(random.randint(10**6, 10**7))})
        try:
            r = m.http.get(url, headers=H, cookies=cook, timeout=20, **m._IMPERSONATE)
            data = m._fc_unwrap(r.json()) if r.status_code == 200 else None
        except Exception as e:
            print(f"{sort!r:18} oos={oos!r}: ERR {e}")
            continue
        prods = m._fc_api_products(data) if data else []
        ids = [int(m._ci(p, *m._ID_KEYS) or 0) for p in prods]
        top = [(int(m._ci(p, *m._ID_KEYS) or 0), m._ci(p, "CrntStock"), str(m._ci(p, *m._NAME_KEYS))[:38]) for p in prods[:6]]
        print(f"{sort!r:18} oos={oos!r}: HTTP {r.status_code}, {len(prods)} products, ids sorted desc: {ids == sorted(ids, reverse=True)}, max id {max(ids) if ids else '-'}")
        for t in top:
            print("      ", t)
        time.sleep(0.4)
