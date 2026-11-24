#!/usr/bin/env python3
"""Probe #89: the new Hot Wheels case on FirstCry (24 Nov) - can it reach 248001, and which pincodes can it reach?"""
import json, os, sys, time

os.environ.setdefault("FC_PINCODE", "248001")
os.environ["FC_WWW_RATE"] = "1.5"
sys.path.insert(0, ".")
import bot_now as B

CARS = {"25045161": "Skyline GT-R BNR34 (J-Imports, black)", "25045673": "Porsche 908-3 Gulf",
        "25045680": "Porsche 911 Turbo Cabriolet", "25045641": "Toyota AE86 Trueno", "25045647": "Mazda RX-7",
        "25045653": "1985 Honda CR-X", "25045466": "Mercedes CLA (alerted)", "25045658": "Mazda RX-3 (alerted)"}
PINS = {"248001": "Dehradun", "249401": "Haridwar", "247001": "Saharanpur", "110001": "Delhi", "122001": "Gurgaon",
        "201301": "Noida", "160017": "Chandigarh", "302001": "Jaipur", "400001": "Mumbai", "411001": "Pune",
        "560001": "Bengaluru", "500001": "Hyderabad", "600001": "Chennai", "700001": "Kolkata", "226001": "Lucknow"}
ids = list(CARS)
t0 = time.time()
print(time.strftime("%H:%M:%S UTC", time.gmtime()), flush=True)
page = B.fc_page("25045161")
print("[PAGE] Skyline page read:", json.dumps({k: {kk: vv for kk, vv in (v or {}).items() if kk in ("cs", "svc", "isv", "name", "price")}
                                              for k, v in (page or {}).items()})[:1500], flush=True)
for pid in ("25045673", "25045680", "25045641"):
    pg = B.fc_page(pid)
    print(f"[PAGE] {CARS[pid]}:", json.dumps({k: {kk: vv for kk, vv in (v or {}).items() if kk in ("cs", "svc", "isv")}
                                              for k, v in (pg or {}).items() if k in CARS}), flush=True)
for pin, city in PINS.items():
    svc = B.fc_delivery(ids, pin)
    cnt = B.fc_delivery_count(ids, pin)
    cart = B.fc_cart_check(ids, pin) or {}
    row = []
    for pid, name in CARS.items():
        c = cart.get(pid) or {}
        row.append(f"{name.split(' (')[0][:18]}: svc={svc.get(pid)} units={cnt.get(pid)} cart={'Y' if c.get('ok') else 'n'}{'' if c.get('n') is None else '/' + str(c.get('n'))}")
    print(f"[PIN] {pin} {city}: " + " | ".join(row), flush=True)
print(f"done in {time.time() - t0:.0f}s", flush=True)
