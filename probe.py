#!/usr/bin/env python3
"""Probe #85: the Whiff reader with version checks, live, for 60 s (no Telegram)."""
import os, sys, time, urllib.request

os.environ["PERFUME_STATE"] = "whiff_state.json"
sys.path.insert(0, ".")
import perfume_new as P

calls = {"HEAD": 0, "GET": 0}
_open = urllib.request.urlopen


def counting(req, *a, **k):
    calls[req.get_method() if isinstance(req, urllib.request.Request) else "GET"] += 1
    return _open(req, *a, **k)


urllib.request.urlopen = counting
st = P.load()
w = next(w for w in P.WATCHES if w["id"] == "whiff-partials")
t0 = time.time()
n = 0
while time.time() - t0 < 60:
    t = time.time()
    prods, why = P.fetch(w)
    ev, why2 = P.check(st, w, time.time(), (prods, why)) if prods is not None else (None, why)
    n += 1
    if n <= 3 or n % 10 == 0:
        print(f"[{time.time() - t0:5.1f}s] read {n}: {len(prods or [])} products, {sum(1 for p in prods or [] if P.available(p['variants']))} in stock, "
              f"events {len(ev or [])}, took {time.time() - t:.2f}s, calls {calls}", flush=True)
    time.sleep(max(0, 2 - (time.time() - t)))
print(f"done: {n} checks, calls {calls}, page version {P._page[w['id']][0]}")
