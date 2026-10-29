#!/usr/bin/env python3
"""Probe #57: how long KND's guest-cart count takes (add → read → remove), for
one and for three ordinary cars at once, and what the stock-blocking fields
say. Fresh visitor carts, items removed each time, nothing ordered."""
import json, time, uuid
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http
IMP = {"impersonate": "chrome124"}
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept": "application/json", "Content-Type": "application/json", "Origin": "https://www.karzanddolls.com", "Referer": "https://www.karzanddolls.com/"}
API = "https://www.karzanddolls.com/karzOffice/api"
S = http.Session(impersonate="chrome124")


def one_round(ids):
    vid = str(uuid.uuid4())
    t0 = time.time()
    with ThreadPoolExecutor(4) as ex:
        adds = list(ex.map(lambda i: S.post(f"{API}/cart/visitor/add", headers=H, data=json.dumps({"visitor_id": vid, "product_id": i, "quantity": 1}), timeout=10).status_code, ids))
    t1 = time.time()
    r = S.get(f"{API}/cart/visitor?visitor_id={vid}", headers=H, timeout=10)
    items = r.json().get("data") or []
    t2 = time.time()
    with ThreadPoolExecutor(4) as ex:
        rem = list(ex.map(lambda it: S.post(f"{API}/cart/visitor/remove", headers=H, data=json.dumps({"visitor_id": vid, "cart_item_id": it["id"]}), timeout=10).status_code, items))
    t3 = time.time()
    left = S.get(f"{API}/cart/visitor?visitor_id={vid}", headers=H, timeout=10).json().get("data")
    counts = {it["product"]["id"]: it["product"].get("pro_stock") for it in items}
    return round(t1 - t0, 2), round(t2 - t1, 2), round(t3 - t2, 2), adds, counts, left, items


for ids in ([4213], [4213, 4538, 6079], [4538], [4213, 4538, 6079]):
    a, g, rm, adds, counts, left, items = one_round(ids)
    print(f"{len(ids)} car(s): add {a}s, read {g}s, remove {rm}s  → counts {counts}  adds {adds}  cart after: {left}")
p = items[0]["product"]
print("\nstock fields of one car:", {k: p.get(k) for k in ("id", "pro_name", "pro_stock", "initial_stock", "in_stock", "add_limit", "isstock_blocked",
                                                       "block_order_time", "block_type", "blocked_user", "add_to_bag", "pro_sta", "creation_time")})
