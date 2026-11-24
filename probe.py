#!/usr/bin/env python3
"""Probe #88: page-version checks on all three Whiff pages, live, for 90 s (no Telegram)."""
import os, sys, time, urllib.request

os.environ["PERFUME_STATE"] = "whiff_state.json"
sys.path.insert(0, ".")
import perfume_new as P

calls = {}
_open = urllib.request.urlopen


def counting(req, *a, **k):
    key = (req.get_method(), req.full_url.rsplit("/", 1)[-1])
    calls[key] = calls.get(key, 0) + 1
    return _open(req, *a, **k)


urllib.request.urlopen = counting
st = P.load()
ws = [w for w in P.WATCHES if w["store"] == "Whiff Culture"]
t0 = time.time()
n = 0
while time.time() - t0 < 75:
    t = time.time()
    for w in ws:
        prods, why = P.fetch(w)
        ev, _ = P.check(st, w, time.time(), (prods, why)) if prods is not None else (None, why)
        if ev:
            print(f"[{time.time() - t0:5.1f}s] {w['id']}: {[(k, p['title']) for k, _, p, _ in ev]}", flush=True)
        if prods is None:
            print(f"[{time.time() - t0:5.1f}s] {w['id']}: FAILED {why}", flush=True)
    n += 1
    time.sleep(max(0, 3 - (time.time() - t)))
print(f"done: {n} rounds", {f"{m} {u}": c for (m, u), c in sorted(calls.items())}, flush=True)
for w in ws:
    print(w["id"], "version", P._page[w["id"]][0], "in stock", sum(1 for i in st["w"][w["id"]]["items"].values() if i.get("a")))
