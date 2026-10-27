#!/usr/bin/env python3
"""Probe #42: why does FirstCry's cart tell the tracker "6 left for 248001" while
your app's cart says "Cannot be delivered to 248001"? For 11 minutes, every 5 s,
the same cars are asked in several ways at the same moment, and everything
FirstCry answers is kept:
  • a one-car guest cart (like your app's cart holds one or two cars)
  • the tracker's own way: one cart of 75 cars
  • a two-car cart (Skyline + Click Shift, like yours)
  • a one-car cart that also gives Dehradun's location (latlong)
  • a one-car cart with a brand-new device id every time
  • FirstCry's delivery check (the product page's) — every 5 s
  • the product page's stock — every 30 s; the in-stock list for 248001 — every 30 s
Every field of every cart line is kept (the tracker reads 4), with the answering
server's headers. Nothing is bought; carts are guest carts."""
import collections, concurrent.futures as cf, importlib.util, json, os, random, shutil, time, uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "FC_PINCODE": "248001"})
spec = importlib.util.spec_from_file_location("bot", os.path.join(ROOT, "bot_v1754.py"))
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)
http, IMP = bot.http, bot._IMPERSONATE
PIN = "248001"
T = {"24776061": "Skyline HT 2000GT-X TH (flickered 12-26 s, 4x today)",
     "24248198": "Click Shift 178 (control: in stock all week)",
     "24235312": "98 Honda Prelude (flickered 30-109 s)",
     "24476003": "Ferrari 12 Cilindri green (flickered; long real restocks too)",
     "24783699": "70 AAR Cuda 245 (flickered 48-106 s)",
     "24783761": "20 Hellcat 134 (flickered 8-117 s)",
     "24776075": "2019 Audi R8 Spyder 130 (flickered 11-50 s)"}
EVERY_ROUND = ["24776061", "24248198", "24235312", "24476003"]
seen = json.load(open(os.path.join(ROOT, "seen.json")))
others = [k[3:] for k, v in seen.items() if k.startswith("fc_") and k[3:].isdigit() and isinstance(v, dict)
          and k[3:] not in T and "hot wheels" in (v.get("name") or "").lower()]
random.seed(7)
FILL = random.sample(others, 68)
BATCH = list(T) + FILL                     # 75 cars, like one of the tracker's carts
HDR_KEYS = ("server", "via", "x-cache", "x-served-by", "x-azure-ref", "cf-ray", "x-amz-cf-id", "x-backend",
            "x-powered-by", "x-aspnet-version", "x-server", "x-node", "x-upstream", "age", "x-ms-request-id")


def cart(pids, latlong="", fresh_dev=False):
    dev = ({"fcdid": str(uuid.uuid4()), "fingerprint": uuid.uuid4().hex} if fresh_dev else DEV)
    hdr = {**bot.COMMON_HEADERS, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "Origin": "https://checkout.firstcry.com",
           "Referer": "https://checkout.firstcry.com/pay", **dev}
    body = {"pro": "*".join(f"NO^{p}^1^0" for p in pids), "shipPin": PIN, "SiteType": 0, "LC": 0, "CR": 0,
            "Coupons": "", "FC_AUTH": "", "ShipMobile": "", "ShipPhone": "", "PayBack": "", "State": "",
            "PaymentType": "", "LPO": False, "LSD": False, "CCA": "", "LT": "N", "UA": hdr.get("User-Agent", ""),
            "AddressType": "Home", "AssemblyMap": "", "ptype": "", "pvalue": "", "FitKidChildIdMap": "",
            "CouponCodeToCheck": "", "GiftCodeToCheck": "", "BuyerType": "", "CardPar": "", "RemoveFreeErr": "",
            "redesign": True, "caller": "", "Ageid": "", "bmsm": "", "SegmentIDs": "", "latlong": latlong,
            "segmentcookie": "", "cardref": "", "savedCardBankCode": "", "savedCardIssuingBank": "", "cardtoken": ""}
    t0 = time.time()
    try:
        r = http.post(bot.FC_CART_URL, data=json.dumps(body), headers=hdr, timeout=12, **IMP)
    except Exception as e:
        return {"err": type(e).__name__, "ms": int((time.time() - t0) * 1000)}
    out = {"code": r.status_code, "ms": int((time.time() - t0) * 1000),
           "hdr": {k: v for k, v in r.headers.items() if k.lower() in HDR_KEYS}}
    try:
        x = r.json().get("LoadCartResult")
        while isinstance(x, str):
            x = json.loads(x)
        summ = (x or {}).get("pOrderSummary") or {}
    except Exception:
        out["err"] = "not json"
        return out
    out["pin"] = summ.get("ShipPinCode")
    out["summ_keys"] = sorted(summ.keys())
    out["items"] = {str(it.get("ProductID")): it for it in (summ.get("PurchaseOrderItemList") or []) if isinstance(it, dict)}
    out["msgs"] = {k: summ.get(k) for k in summ if any(w in k.lower() for w in ("msg", "message", "error", "deliver", "servic"))}
    return out


def verdict(it):
    """The tracker's own reading of a cart line (fc_cart_check)."""
    if not it:
        return "absent"
    n = bot._fc_int(it.get("CurrentStock")) or 0
    isv = bot._fc_int(it.get("IsServicable"))
    wh = str(it.get("warehouseid") or "0")
    limited = ((bot._fc_int(it.get("NoOfPinCodeToCheck")) or 0) > 0
               and not (it.get("isValidPincodeForDropShipment") or it.get("IsValidPincodeForDropShipProduct")))
    ok = n > 0 and (isv is None or isv > 0) and wh not in ("", "0") and not limited
    return f"{'YES' if ok else 'no'}(n={n},isv={isv},wh={wh},npc={it.get('NoOfPinCodeToCheck')},dsv={it.get('isValidPincodeForDropShipment')})"


DEV = {"fcdid": str(uuid.uuid4()), "fingerprint": uuid.uuid4().hex}
rounds, first_items, last_items, changes = [], {}, {}, []
t_end = time.time() + 11 * 60
rnd = 0
pool = cf.ThreadPoolExecutor(max_workers=12)
while time.time() < t_end:
    rnd += 1
    t0 = time.time()
    jobs = {}
    for p in (list(T) if rnd % 2 == 0 else EVERY_ROUND):
        jobs[("single", p)] = pool.submit(cart, [p])
    if rnd % 2 == 0:
        jobs[("batch75", "*")] = pool.submit(cart, BATCH)
        jobs[("pair", "*")] = pool.submit(cart, ["24776061", "24248198"])
        jobs[("latlong", "24776061")] = pool.submit(cart, ["24776061"], "30.3165,78.0322")
        jobs[("freshdev", "24776061")] = pool.submit(cart, ["24776061"], "", True)
    tat = pool.submit(bot.fc_delivery, list(T))
    pages = {}
    if rnd % 6 == 1:
        bot._FC_LIVE.clear()
        for p in T:
            pages[p] = pool.submit(bot.fc_page, p)
    lst = pool.submit(bot.fc_api_catalogue, True) if rnd % 6 == 1 else None
    rec = {"r": rnd, "t": time.strftime("%H:%M:%S", time.gmtime(t0 + 19800)), "v": {}}
    for (kind, p), f in jobs.items():
        res = f.result()
        rec.setdefault("meta", {})[f"{kind}:{p}"] = {k: res.get(k) for k in ("code", "ms", "err", "hdr", "pin")}
        if res.get("msgs"):
            rec["meta"][f"{kind}:{p}"]["msgs"] = res["msgs"]
        for q in (T if p == "*" else [p]):
            if kind == "pair" and q not in ("24776061", "24248198"):
                continue
            it = (res.get("items") or {}).get(q)
            rec["v"][f"{kind}:{q}"] = verdict(it)
            key = (kind, q)
            if it is not None:
                if key not in first_items:
                    first_items[key] = it
                prev = last_items.get(key)
                if prev is not None:
                    diff = {k: (prev.get(k), it.get(k)) for k in set(prev) | set(it) if prev.get(k) != it.get(k)}
                    if diff:
                        changes.append({"r": rnd, "t": rec["t"], "kind": kind, "pid": q, "diff": diff})
                last_items[key] = it
    try:
        rec["tat"] = tat.result()
    except Exception as e:
        rec["tat"] = {"err": type(e).__name__}
    if pages:
        rec["page_cs"] = {}
        for p, f in pages.items():
            try:
                f.result()
            except Exception:
                pass
            rec["page_cs"][p] = (bot._FC_LIVE.get(p) or {}).get("cs")
    if lst is not None:
        try:
            got = lst.result() or {}
            rec["on_list"] = {p: (p in {str(k) for k in got}) for p in T}
            rec["list_complete"] = bot.FC_LAST_SWEEP.get("complete")
        except Exception as e:
            rec["on_list"] = {"err": type(e).__name__}
    rounds.append(rec)
    line = " | ".join(f"{p[-4:]}:{rec['v'].get('single:' + p, '-')[:3]}" for p in T)
    print(f"[{rec['t']}] r{rnd} {line} | tat {rec.get('tat')}" + (f" | page {rec.get('page_cs')}" if pages else "")
          + (f" | list {rec.get('on_list')}" if lst is not None else ""), flush=True)
    time.sleep(max(0, 5 - (time.time() - t0)))

# ── summary ───────────────────────────────────────────────────────────────────
keys = collections.Counter()
for it in first_items.values():
    keys.update(it.keys())
print("\n===== every field of a cart line (how many lines had it) =====")
print(", ".join(f"{k}({n})" for k, n in sorted(keys.items())))
print("\n===== the first line of each car, one-car cart =====")
for p in T:
    it = first_items.get(("single", p))
    print(f"--- {p} {T[p]}")
    print(json.dumps(it, ensure_ascii=False)[:3000] if it else "  (never in the cart's answer)")
print("\n===== the tracker's verdict over time, per car and way of asking =====")
for p in T:
    for kind in ("single", "batch75", "pair", "latlong", "freshdev"):
        seq = [(r["t"], r["v"].get(f"{kind}:{p}")) for r in rounds if f"{kind}:{p}" in r["v"]]
        if not seq:
            continue
        flips, last = [], None
        for t, v in seq:
            s = (v or "")[:3]
            if s != last:
                flips.append(f"{t} {v}")
                last = s
        yes = sum(1 for _, v in seq if (v or "").startswith("YES"))
        print(f"{p} {kind:8} {yes:3}/{len(seq)} yes, {len(flips) - 1} flips: " + " → ".join(flips[:12]))
print("\n===== at the same moment: does the one-car cart agree with the others? =====")
for p in T:
    for kind in ("batch75", "pair", "latlong", "freshdev"):
        both = [(r["v"].get(f"single:{p}", "")[:3], r["v"].get(f"{kind}:{p}", "")[:3]) for r in rounds
                if f"{kind}:{p}" in r["v"] and f"single:{p}" in r["v"]]
        if both:
            print(f"{p} single vs {kind:8}: {sum(1 for a, b in both if a == b)}/{len(both)} agree"
                  + (f"  disagreements: {[x for x in both if x[0] != x[1]][:5]}" if any(a != b for a, b in both) else ""))
    tats = [(r["v"].get(f"single:{p}", "")[:3], (r.get("tat") or {}).get(p)) for r in rounds if f"single:{p}" in r["v"]]
    print(f"{p} single vs delivery check: " + str(collections.Counter(tats).most_common(6)))
print("\n===== cart-line fields that changed between two answers (first 60) =====")
for c in changes[:60]:
    print(c["t"], c["kind"], c["pid"], json.dumps(c["diff"], ensure_ascii=False)[:400])
print(f"({len(changes)} changes in all)")
print("\n===== answering servers =====")
hv = collections.Counter()
for r in rounds:
    for k, m in (r.get("meta") or {}).items():
        for h, v in (m.get("hdr") or {}).items():
            if h.lower() not in ("age",):
                hv[(h, str(v)[:60])] += 1
for (h, v), n in hv.most_common(25):
    print(f"  {n:4} {h}: {v}")
codes = collections.Counter(str((m or {}).get("code") or (m or {}).get("err")) for r in rounds for m in (r.get("meta") or {}).values())
print("status codes:", dict(codes))
json.dump({"rounds": rounds, "first_items": {f"{k[0]}:{k[1]}": v for k, v in first_items.items()},
           "changes": changes}, open(os.path.join(ROOT, "probe_report.json"), "w"), ensure_ascii=False)
