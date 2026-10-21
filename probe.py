#!/usr/bin/env python3
"""Probe #27: is FirstCry's in-stock list (OutOfStock=1) really about YOUR
pincode, and where do brand-new cars sit in the catalogue? Read only.

A. In-stock list + full catalogue for 248001, pcode=0 (nationwide) and four
   other pincodes: sizes, which cars differ, whether counts differ.
B. Catalogue for 248001 (Popularity order): page of the 25 highest ids.
C. Cars the 248001 catalogue shows with units but its in-stock list doesn't
   ('cat'): product page CS + delivery check for 248001 + other pincodes' lists.
D. 248001 list + catalogue again twice, ~60 s apart: what comes and goes.
"""
import importlib.util, json, os, random, time
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""})
spec = importlib.util.spec_from_file_location("b", "bot_v16.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
T0 = time.time()
H = {**m.COMMON_HEADERS, "Accept": "application/json, text/javascript, */*; q=0.01",
     "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
     "Referer": m._FC_API_REFERER}
COOK = m._fc_cookies()
PINS = ["248001", "0", "110001", "560001", "400001", "781001"]
REPORT = {}


def el():
    return f"+{time.time() - T0:4.0f}s"


def sweep(pin, oos):
    """{pid: (position, units, name)} for one listing, every page."""
    m._FC_PCODE_ACTIVE[0] = pin
    out, page = {}, 1
    while page <= 30:
        url = m._fc_api_query(page, 20, {"OutOfStock": oos, "searchrank": str(random.randint(10**6, 10**7))})
        data = None
        for _ in range(3):
            try:
                r = m.http.get(url, headers=H, cookies=COOK, timeout=20, **m._IMPERSONATE)
                if r.status_code == 200:
                    data = m._fc_unwrap(r.json())
                    break
                print(f"   {pin} oos={oos!r} p{page}: HTTP {r.status_code}")
            except Exception as e:
                print(f"   {pin} oos={oos!r} p{page}: {type(e).__name__}")
            time.sleep(1.5)
        prods = m._fc_api_products(data) if data else []
        for p in prods:
            pid = str(m._ci(p, *m._ID_KEYS) or "")
            if pid.isdigit() and pid not in out:
                out[pid] = (len(out), m._fc_api_stock(p)[1], m._fc_name(str(m._ci(p, *m._NAME_KEYS) or ""))[:46])
        if len(prods) < 20:
            break
        page += 1
        time.sleep(0.25)
    return out


print("=" * 20, "A. in-stock list + catalogue per pincode", "=" * 20)
L, C = {}, {}
for pin in PINS:
    L[pin] = sweep(pin, "1")
    C[pin] = sweep(pin, "")
    n_c_in = sum(1 for v in C[pin].values() if (v[1] or 0) > 0)
    print(f"{el()} pcode={pin:7}: in-stock list {len(L[pin])} cars (units>0: "
          f"{sum(1 for v in L[pin].values() if (v[1] or 0) > 0)}); catalogue {len(C[pin])} cars, {n_c_in} with units")
base = L["248001"]
for pin in PINS[1:]:
    only_here = [p for p in base if p not in L[pin]]
    only_there = [p for p in L[pin] if p not in base]
    common = [p for p in base if p in L[pin]]
    diff = [(p, base[p][1], L[pin][p][1]) for p in common if base[p][1] != L[pin][p][1]]
    print(f"\n  248001 list vs {pin}: only on 248001's {len(only_here)}, only on {pin}'s {len(only_there)}, "
          f"same cars {len(common)}, counts differ for {len(diff)}")
    for p in only_here[:6]:
        print(f"     only 248001: {p} units {base[p][1]} {base[p][2]}")
    for p in only_there[:6]:
        print(f"     only {pin}: {p} units {L[pin][p][1]} {L[pin][p][2]}")
    for p, a, b in diff[:6]:
        print(f"     count 248001={a} vs {pin}={b}: {p} {base[p][2]}")
cdiff = [(p, C["248001"][p][1], C["0"][p][1]) for p in C["248001"] if p in C["0"] and C["248001"][p][1] != C["0"][p][1]]
print(f"\n  catalogue 248001 vs nationwide: counts differ for {len(cdiff)} of {len(C['248001'])}")
for p, a, b in cdiff[:8]:
    print(f"     {p}: 248001={a} vs 0={b} {C['248001'][p][2]}")
REPORT["A"] = {pin: {"list": len(L[pin]), "cat": len(C[pin])} for pin in PINS}

print("\n" + "=" * 20, "B. where the newest ids sit (catalogue, 248001)", "=" * 20)
cat = C["248001"]
n = len(cat)
for p in sorted(cat, key=int, reverse=True)[:25]:
    pos, u, nm = cat[p]
    print(f"   {p} page {pos // 20 + 1:2}/{-(-n // 20)} pos {pos:3} units {u} {nm}")
lst = L["248001"]
print("   in-stock list, newest 10:")
for p in sorted(lst, key=int, reverse=True)[:10]:
    pos, u, nm = lst[p]
    print(f"   {p} page {pos // 20 + 1:2}/{-(-len(lst) // 20)} pos {pos:3} units {u} {nm}")

print("\n" + "=" * 20, "C. catalogue says units, 248001's in-stock list doesn't", "=" * 20)
catin = [p for p, v in cat.items() if (v[1] or 0) > 0 and p not in lst]
print(f"   {len(catin)} such cars")
pick = sorted(catin, key=int, reverse=True)[:16]
m._FC_PCODE_ACTIVE[0] = "248001"
for p in pick:
    m.fc_page(p)
    time.sleep(0.3)
svc = m.fc_delivery(pick) if pick else {}
isv = m.fc_delivery_count(pick) if pick else {}
for p in pick:
    live = m._FC_LIVE.get(p) or {}
    on = [pin for pin in PINS[1:] if p in L[pin]]
    print(f"   {p} cat units {cat[p][1]:>4} | page CS {live.get('cs')} | 248001 svc {svc.get(p)} isv {isv.get(p)} "
          f"TAT {live.get('days')} | on lists of: {on or '-'} | {cat[p][2]}")
REPORT["C"] = {p: {"cat": cat[p][1], "cs": (m._FC_LIVE.get(p) or {}).get("cs"), "svc": svc.get(p),
                   "isv": isv.get(p), "on": [pin for pin in PINS[1:] if p in L[pin]]} for p in pick}

print("\n" + "=" * 20, "D. 248001 again, twice, ~60 s apart", "=" * 20)
prev_l, prev_c = L["248001"], C["248001"]
for rnd in (1, 2):
    time.sleep(max(0, 60 - (time.time() - T0) % 60))
    l2, c2 = sweep("248001", "1"), sweep("248001", "")
    gone = [p for p in prev_l if p not in l2]
    came = [p for p in l2 if p not in prev_l]
    cu = [(p, prev_c[p][1], c2[p][1]) for p in c2 if p in prev_c and prev_c[p][1] != c2[p][1]]
    newc = [p for p in c2 if p not in prev_c]
    print(f"{el()} round {rnd}: list {len(l2)} (+{len(came)} -{len(gone)}), catalogue {len(c2)} "
          f"(+{len(newc)} new ids), catalogue counts changed {len(cu)}")
    for p in came[:6]:
        print(f"     list +{p} units {l2[p][1]} {l2[p][2]}")
    for p in gone[:6]:
        print(f"     list -{p} (catalogue now {(c2.get(p) or (0, '?'))[1]}) {prev_l[p][2]}")
    for p in newc[:6]:
        print(f"     catalogue new id {p} units {c2[p][1]} pos {c2[p][0]} {c2[p][2]}")
    prev_l, prev_c = l2, c2
json.dump(REPORT, open("probe_report.json", "w"), indent=1)
print(f"\ndone in {time.time() - T0:.0f}s")
