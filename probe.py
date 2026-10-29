#!/usr/bin/env python3
"""Probe #50: the v17.6 tracker's own Karz & Dolls reader against the live
shop — what names (with [Box] / [Blister]) and links it produces, and do those
links open the right car? Read-only (no Telegram, no state)."""
import json, os, re, sys, collections, importlib.util, random
from concurrent.futures import ThreadPoolExecutor
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "GITHUB_ACTIONS": "true"})
spec = importlib.util.spec_from_file_location("b176", "bot_v176.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

items = b.scrape_karzanddolls()
print(f"\n{len(items)} KND products the tracker keeps; healthy={b.KD_HEALTHY[0]}")
lab = collections.Counter("[Blister]" if n.endswith("[Blister]") or "[Blister] [" in n else
                          "[Box]" if "[Box]" in n else ("BLISTER in name" if "BLISTER" in n.upper() else "none")
                          for n in (d["name"] for d in items))
print("labels:", dict(lab))
mg = [d for d in items if re.search(r"\bMINI\s*GT\b", d["name"], re.I) and "KAIDO" not in d["name"].upper()]
unl = [d["name"] for d in mg if "[Box]" not in d["name"] and "[Blister]" not in d["name"] and not re.search(r"BLISTER|\bBOX\b", d["name"].upper())]
print(f"Mini GT (not Kaido) products: {len(mg)}; saying neither box nor blister: {len(unl)} {unl[:6]}")
names = collections.Counter(re.sub(r"[^a-z0-9]", "", d["name"].lower()) for d in items)
dup = [n for n, c in names.items() if c > 1]
print(f"names still shared by two listings (would merge in one alert): {len(dup)} {dup[:6]}")
print("\nsamples:")
for d in random.Random(4).sample(items, 12):
    print(f"  {d['stock']:12} {d['price']:>7}  {d['name'][:84]!r}")

def opens(d):
    pid = d["id"][3:]
    try:
        r = b.http.get(d["url"], headers=b.COMMON_HEADERS, timeout=25, **b._IMPERSONATE)
        m = NEXT.search(r.text or "")
        pd = ((json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}).get("productdetails") or {} if m else {}
        return r.status_code, str(pd.get("pid")) == pid
    except Exception as e:
        return type(e).__name__, False

ins = [d for d in items if d["stock"] == "in_stock"]
odd = [d for d in ins if "%25" in d["url"]]
pick = odd + random.Random(7).sample([d for d in ins if d not in odd], min(80, len(ins) - len(odd)))
with ThreadPoolExecutor(8) as ex:
    res = list(ex.map(lambda d: (d, *opens(d)), pick))
good = sum(1 for _, _, ok in res if ok)
print(f"\nlinks checked: {len(res)} in-stock ({len(odd)} with a twice-encoded character) — open the right car: {good}")
for d, code, ok in res:
    if not ok or d in odd:
        print(f"  {'OK ' if ok else 'BAD'} HTTP {code} {d['name'][:60]!r} {d['url'][len(b._KD):][:90]!r}")
json.dump({"labels": dict(lab), "unlabelled": unl, "dup": dup, "checked": len(res), "open": good,
           "items": [{k: d[k] for k in ("id", "name", "url", "stock", "price")} for d in items]},
          open("probe_report.json", "w"), indent=1, ensure_ascii=False)
