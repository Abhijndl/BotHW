#!/usr/bin/env python3
"""Probe: can GitHub's runner load the Blinkit product page, and what does it
show for the 'Coming soon' item (prid 1454828)? Read-only, one request per try."""
import json, re, time
from curl_cffi import requests

URL = "https://blinkit.com/prn/x/prid/1454828"
HDR = {"Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml"}
report = {"url": URL, "tries": []}
for i, imp in enumerate(["chrome", "safari", "chrome124"], 1):
    t = time.time()
    try:
        r = requests.get(URL, headers=HDR, impersonate=imp, timeout=20, allow_redirects=True)
        body = r.text
        row = {"try": i, "impersonate": imp, "status": r.status_code, "final_url": str(r.url),
               "bytes": len(body), "secs": round(time.time() - t, 1),
               "title": (re.search(r"<title>(.*?)</title>", body, re.S) or [None, None])[1],
               "has_next_data": "__NEXT_DATA__" in body,
               "has_json_ld": "application/ld+json" in body,
               "words": {w: bool(re.search(w, body, re.I)) for w in
                         ["coming soon", "notify", "out of stock", "sold out", "add to cart", "1454828", "Supra", "549", "Dehradun", "248001"]}}
        m = re.search(r'"(?:inStock|in_stock|availability)"\s*:\s*("?[^,}]{1,40})', body)
        row["stock_field"] = m.group(1) if m else None
        row["snippet"] = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", body, flags=re.S))[:600]
    except Exception as e:
        row = {"try": i, "impersonate": imp, "error": repr(e)[:300], "secs": round(time.time() - t, 1)}
    report["tries"].append(row)
    print(json.dumps(row, ensure_ascii=False)[:1200])
    if row.get("status") == 200 and row.get("bytes", 0) > 20000:
        break
with open("probe_blinkit_report.json", "w") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)
