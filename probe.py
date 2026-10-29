#!/usr/bin/env python3
"""Probe #58: the v17.7 tracker's own code against the live Karz & Dolls — the
fast check of the busiest shelves (time, cars), the full check, and its unit
count for three ordinary cars through a guest cart, emptied afterwards."""
import os, re, time, uuid, importlib.util, json
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "GITHUB_ACTIONS": "true"})
spec = importlib.util.spec_from_file_location("b177", "bot_v177.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
for i in range(3):
    t = time.time(); fast = b.scrape_karzanddolls(fast=True); print(f"fast check {i + 1}: {len(fast)} cars in {time.time() - t:.1f}s")
t = time.time(); full = b.scrape_karzanddolls(); print(f"full check: {len(full)} cars in {time.time() - t:.1f}s, healthy={b.KD_HEALTHY[0]}")
print("fast shelves:", [b._kd_path(u) for u in b.KD_FAST_URLS])
hype = re.compile(r"LB|LIBERTY|PORSCHE|MCLAREN|LAMBORGHINI|FERRARI|SKYLINE|GT-?R|SUPRA|KAIDO|BUGATTI|SILHOUETTE", re.I)
pick = [d for d in fast if d["stock"] == "in_stock" and not hype.search(d["name"]) and d.get("kd_num")][:3]
fixed = uuid.uuid4()
b.uuid.uuid4 = lambda: fixed
t = time.time()
done = b.kd_stock_counts(pick)
print(f"count read in {time.time() - t:.1f}s:", [(d["name"][:40], d.get("stock_count"), d.get("kd_cart0")) for d in pick])
t = time.time(); done(); print(f"cart emptied in {time.time() - t:.1f}s")
r = b.http.get(f"{b._KD_API}/cart/visitor?visitor_id={fixed}", headers=b._KD_API_HEADERS, timeout=10, **b._IMPERSONATE)
print("guest cart afterwards:", r.status_code, r.json().get("data"))
print("alert lines:")
for d in pick:
    print("  ", b._line(d).split("\n")[0])
