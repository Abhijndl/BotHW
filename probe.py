#!/usr/bin/env python3
"""Probe #86: the sale checks, live (no Telegram)."""
import os, sys, time

os.environ["PERFUME_STATE"] = "whiff_state.json"
sys.path.insert(0, ".")
import perfume_new as P

t = time.time()
print("whiff menu sales:", P.next_sales(P.WHIFF), f"{time.time() - t:.2f}s", flush=True)
for site in (P.SCENTORIA, P.SCENTIRA, P.SILLAGE):
    t = time.time()
    print(site, "sales:", P.shopify_sales(site), f"{time.time() - t:.2f}s", flush=True)
st = P.load()
print("check_sales whiff ->", P.check_sales(st, P.WHIFF, "Whiff Culture", time.time(), "next"), st["sales"].get("www.whiffculture.com"))
