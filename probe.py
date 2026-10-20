#!/usr/bin/env python3
"""Probe #16: is the delivery check's own count (Result.IsServicable, answered
for the main product) the number of units you can really order — the "1" the
user saw for the SF90 while its page said 155?

For every car of a few colour sets: page CS, groupserviceability (the 0/1 the
page uses), and a delivery check with THAT car as the main product (its
IsServicable count, ProductTAT, next-day flag, shipping date) — three rounds,
~2.5 min apart, to see what moves together.
"""
import json, re, time, random, os, collections
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

T0 = time.time()
IMP = {"impersonate": "chrome124"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
REF = "https://www.firstcry.com/hotwheels/5/0/113"
S = http.Session(**IMP)
S.get(REF, headers=H, timeout=20)
COOK = {c.name: c.value for c in getattr(S.cookies, "jar", S.cookies)}
TAT = "https://www.firstcry.com/tatapi/oam/checkdeliveryinfo"
SETS = ["23075648", "23074613", "24473731", "24776024", "24503746", "23351187", "22597521"]
OUT = []


def el():
    return f"+{time.time() - T0:4.0f}s"


def json_after(txt, pat):
    m = re.search(pat, txt)
    if not m:
        return None
    i = txt.find("{", m.end() - 1)
    depth, ins, esc = 0, False, False
    for j in range(i, min(len(txt), i + 3_000_000)):
        c = txt[j]
        if ins:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                ins = False
        elif c == '"':
            ins = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(txt[i:j + 1])
                except Exception:
                    return None
    return None


def page(pid):
    url = f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail?fresh={random.randint(10**8, 10**9)}"
    r = http.get(url, headers=H, cookies=COOK, timeout=20, **IMP)
    cur = json_after(r.text, r"CurrentProductDetailJSON\s*=\s*\{") or {}
    return {str(k): v for k, v in cur.items() if isinstance(v, dict)}


def tat(main, group, pincode="248001"):
    body = {"ProductIDs": str(main), "Pincode": pincode, "ComboId": 0, "CheckTAT": True,
            "CheckDropShipment": False, "CheckCOD": True, "subCatID": 94, "MRP": 179,
            "AddressType": "Home", "Discount": 0, "minQty": 1, "CatID": 5, "ftk": "",
            "groupproducts": ",".join(group)}
    hdr = {**H, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
           "Origin": "https://www.firstcry.com", "Referer": f"https://www.firstcry.com/hot-wheels/x/{main}/product-detail"}
    for _ in range(2):
        try:
            r = http.post(TAT, data=json.dumps(body), headers=hdr, cookies=COOK, timeout=15, **IMP)
            return (r.json() or {}).get("Result") or {}
        except Exception:
            time.sleep(0.5)
    return {}


rows_all = collections.defaultdict(list)
for rnd in range(3):
    if rnd:
        time.sleep(max(0, rnd * 150 - (time.time() - T0)))
    print("\n" + "=" * 12, f"round {rnd + 1} {el()}", "=" * 12)
    for sp in SETS:
        cur = page(sp)
        members = list(cur)
        with ThreadPoolExecutor(10) as ex:
            res = dict(zip(members, ex.map(lambda m: tat(m, members), members)))
        grp = (res.get(sp) or {}).get("groupserviceability") or {}
        print(f"\n set of {sp} ({len(members)} cars)")
        print(f"   {'car':9} {'name':38} {'CS':>4} {'grp':>3} {'IsSv':>4} {'TAT':>6} NDD ship")
        for m in sorted(members, key=lambda x: -(cur[x].get('CS') or 0)):
            r = res.get(m) or {}
            g = {str(k): v for k, v in (r.get("groupserviceability") or {}).items()}
            row = (cur[m].get("CS"), g.get(m), r.get("IsServicable"), r.get("ProductTAT"), r.get("IsNDD"),
                   re.sub("<[^>]+>", "", str(r.get("ShippingDate") or "")))
            rows_all[m].append(row)
            OUT.append({"round": rnd, "car": m, "name": cur[m].get("pn"), "CS": row[0], "grp": row[1],
                        "IsServicable": row[2], "TAT": row[3], "NDD": row[4], "ship": row[5], "group_view": grp.get(m)})
            print(f"   {m:9} {str(cur[m].get('pn'))[:38]:38} {str(row[0]):>4} {str(row[1]):>3} {str(row[2]):>4} {str(row[3]):>6} {str(row[4])[:1]} {row[5][:22]}")

print("\n" + "=" * 12, "summary", "=" * 12)
c = collections.Counter()
for m, rs in rows_all.items():
    for cs, g, isv, tt, ndd, ship in rs:
        c[(("CS>0" if (cs or 0) > 0 else "CS=0"), f"grp={g}", ("IsSv>=2" if (isv or 0) >= 2 else f"IsSv={isv}"), f"NDD={ndd}")] += 1
for k, n in sorted(c.items(), key=lambda kv: -kv[1]):
    print("  ", k, n)
moved = {m: rs for m, rs in rows_all.items() if len(set((r[1], r[2]) for r in rs)) > 1}
print("cars whose delivery answer moved across rounds:", len(moved))
for m, rs in list(moved.items())[:20]:
    print("  ", m, [(r[0], r[1], r[2]) for r in rs])
json.dump(OUT, open("probe_report.json", "w"), indent=1, default=str)
print(f"done in {time.time() - T0:.0f}s")
