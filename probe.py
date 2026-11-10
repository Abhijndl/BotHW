#!/usr/bin/env python3
"""Probe #61: v17.8 against the real FirstCry: Majorette's in-stock list and whole
list through the new code, which cars pass the filter, what it costs. Read-only."""
import os, time, json, importlib.util, traceback
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "GITHUB_ACTIONS": "true"})
spec = importlib.util.spec_from_file_location("b178", "bot_v178.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
R = {}
calls = []
real_get = b.http.get
def counting_get(url, **kw):
    calls.append(url)
    return real_get(url, **kw)
b.http.get = counting_get
try:
    for hot in (True, False):
        n0, t0 = len(calls), time.time()
        prods, ok = b.fc_api_brand_sweep("1335", hot)
        recs = b.fc_api_records(prods, {}, quiet=True)
        R["hot" if hot else "all"] = {"n": len(prods), "complete": ok, "requests": len(calls) - n0,
                                      "secs": round(time.time() - t0, 1),
                                      "tracked": sorted((r["name"], r["stock"], r.get("stock_count"), r["url"]) for r in recs)}
        print(f"\n=== {'in-stock list' if hot else 'whole list'}: {len(prods)} products, complete={ok}, "
              f"{len(calls)-n0} requests, {time.time()-t0:.1f}s; tracked after the filter: {len(recs)}")
        for nm, st, c, u in R["hot" if hot else "all"]["tracked"]:
            print(f"   {st:13} {str(c):>4}  {nm[:95]}")
    n0 = len(calls)
    a = b.fc_extra_products(True); a2 = b.fc_extra_products(True)
    print(f"\nstand-in: two calls → {len(calls)-n0} requests, {len(a)} = {len(a2)} cars")
    hw0, t0 = len(calls), time.time()
    hw = b.fc_api_catalogue(hot=True)
    print(f"Hot Wheels in-stock list for comparison: {len(hw or {})} cars, {len(calls)-hw0} requests, {time.time()-t0:.1f}s")
    R["hw_requests"] = len(calls) - hw0
    print("\nlink check:", end=" ")
    rec = next((r for r in b.fc_api_records(prods, {}, quiet=True)), None)
    if rec:
        r = real_get(rec["url"], headers=b.COMMON_HEADERS, timeout=20, **b._IMPERSONATE)
        print(rec["url"], "->", r.status_code, len(r.text))
except Exception:
    print("FAILED:", traceback.format_exc()[-1500:])
json.dump(R, open("probe_report.json", "w"), indent=1, ensure_ascii=False)
