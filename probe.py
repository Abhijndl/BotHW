#!/usr/bin/env python3
"""Probe #18: the Porsche 928S (23345758) alerted 'only 3 left' at 13:21 IST; the
user's cart a moment later said '1 Left · Undeliverable · Cannot be delivered to
248001'. The bot still records it deliverable. What does FirstCry say now?

A. Full page entry + full delivery-check Result (bot-style and page-style, several
   pincodes) for the Porsche, the Buick Riviera (alerted 13:03) and two controls.
B. Every ~15 s for ~4 min: page CS, groupserviceability, IsServicable, TAT,
   dispatch hours, shipping date — what moves.
C. Look for what the cart uses to say 'cannot be delivered': endpoints in the
   cart page and the product page scripts (read only, nothing is added to a cart).
"""
import json, re, time, random, os, collections
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

T0 = time.time()
DUR = float(os.getenv("PROBE_SECONDS", "240"))
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
FOCUS = {"23345758": "Porsche928S", "24473713": "BuickRiviera", "24473712": "SaltStreaker(ctrl)",
         "23075645": "AudiRS6"}
OUT = {"A": {}, "B": [], "C": {}}


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
    pdj = json_after(r.text, r"(?<![A-Za-z])ProductDetailJSON\s*=\s*\{") or {}
    return {str(k): v for k, v in cur.items() if isinstance(v, dict)}, (pdj.get("PInfo") or {}), r.text


def tat(main, group, pincode="248001", pinfo=None, ent=None, style="bot"):
    if style == "bot":
        body = json.dumps({"ProductIDs": str(main), "Pincode": pincode, "ComboId": 0, "CheckTAT": True,
                           "CheckDropShipment": False, "CheckCOD": True, "subCatID": 94, "MRP": 179,
                           "AddressType": "Home", "Discount": 0, "minQty": 1, "CatID": 5, "ftk": "",
                           "groupproducts": ",".join(group)})
    else:
        pinfo, ent = pinfo or {}, ent or {}
        pmrp = ent.get("mrp") or pinfo.get("MRP") or 0
        pdis = ent.get("Dis") if ent.get("Dis") not in ("", None, 0) else (pinfo.get("Dis") or 0)
        body = '{"ProductIDs":"%s","Pincode":"%s","ComboId":0,"CheckTAT":true,"CheckDropShipment":%s,"CheckCOD":%s,"subCatID":%s,"MRP":%s,"AddressType":"Home","Discount":%s,"minQty":%s,"CatID":%s, "ftk": "","groupproducts":"%s"}' % (
            main, pincode, "true" if str(pinfo.get("StockT", "")).lower() == "creditvendorstock" else "false",
            "true" if pinfo.get("CODA") else "false", pinfo.get("SCID") or 0, pmrp, pdis,
            ent.get("minQty") or 1, pinfo.get("PCID") or 0, ",".join(group))
    hdr = {**H, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
           "Origin": "https://www.firstcry.com", "Referer": f"https://www.firstcry.com/hot-wheels/x/{main}/product-detail"}
    try:
        r = http.post(TAT, data=body, headers=hdr, cookies=COOK, timeout=15, **IMP)
        res = (r.json() or {}).get("Result") or {}
    except Exception as e:
        return {}, {"err": str(e)[:80]}
    return {str(k): v for k, v in (res.get("groupserviceability") or {}).items()}, res


# ── A ──────────────────────────────────────────────────────────────────────────
print("=" * 14, "A. full answers", "=" * 14)
groups, pinfos, ents = {}, {}, {}
for pid, nm in FOCUS.items():
    cur, pinfo, txt = page(pid)
    groups[pid], pinfos[pid], ents[pid] = list(cur), pinfo, cur.get(pid) or {}
    print(f"\n{el()} {nm} {pid}: set of {len(cur)}; page entry:")
    print("   ", json.dumps(ents[pid], ensure_ascii=False)[:1500])
    print("   PInfo:", json.dumps({k: pinfo.get(k) for k in list(pinfo)[:60]}, ensure_ascii=False)[:1500])
    print("   set CS:", {k: v.get("CS") for k, v in cur.items()})
    for kw in ("Left", "left", "Undeliverable", "not deliverable", "Cannot be delivered", "outofstock", "Out of Stock", "NOTIFY"):
        n = txt.count(kw)
        if n:
            print(f"   page text '{kw}': {n}x")
    for style in ("bot", "page"):
        g, res = tat(pid, groups[pid], "248001", pinfo, ents[pid], style)
        print(f"   delivery ({style}) this car grp={g.get(pid)} | " + json.dumps({k: v for k, v in res.items() if k != "groupserviceability"}, ensure_ascii=False)[:1300])
    for pin in ("248002", "248006", "248171", "110001", "122001", "560001", "400001"):
        g, res = tat(pid, groups[pid], pin, pinfo, ents[pid], "page")
        print(f"   pincode {pin}: grp={g.get(pid)} IsServicable={res.get('IsServicable')} TAT={res.get('ProductTAT')} "
              f"dispatch={res.get('DispatchHrs')} ship={re.sub('<[^>]+>', '', str(res.get('ShippingDate') or ''))[:30]} NDD={res.get('IsNDD')}")
    OUT["A"][pid] = {"entry": ents[pid], "pinfo": pinfo, "set": {k: v.get("CS") for k, v in cur.items()}}

# ── C (before B so it isn't cut off) ──────────────────────────────────────────
print("\n" + "=" * 14, "C. what the cart uses", "=" * 14)
seen_js = set()
for url in ("https://www.firstcry.com/cart", "https://www.firstcry.com/hot-wheels/x/23345758/product-detail"):
    try:
        r = http.get(url, headers=H, cookies=COOK, timeout=20, **IMP)
    except Exception as e:
        print("  ", url, "failed", e)
        continue
    print(f"  {url} → {r.status_code}, {len(r.text)} bytes, final {getattr(r, 'url', '')}")
    for m in sorted(set(re.findall(r"https?://[^\s\"'<>]+?(?:svc|api|Service|cart)[^\s\"'<>]*", r.text, re.I)))[:60]:
        print("     url:", m[:160])
    js = re.findall(r"<script[^>]+src=[\"']([^\"']+\.js[^\"']*)", r.text)
    for j in js:
        if j.startswith("//"):
            j = "https:" + j
        elif j.startswith("/"):
            j = "https://www.firstcry.com" + j
        if j in seen_js or not re.search(r"cart|pdp|product|checkout|common|main|app", j, re.I):
            continue
        seen_js.add(j)
        try:
            jr = http.get(j, headers=H, timeout=20, **IMP)
        except Exception:
            continue
        hits = set()
        for m in re.finditer(r"[\"'](/?[A-Za-z0-9_/.\-]*(?:deliver|servic|pincode|cart|checkout|tat)[A-Za-z0-9_/.\-]*)[\"']", jr.text, re.I):
            s = m.group(1)
            if len(s) > 6 and ("/" in s or "." in s):
                hits.add(s)
        if hits:
            print(f"     js {j[:110]} ({len(jr.text)} b):")
            for h in sorted(hits)[:40]:
                print("        ", h[:150])
        for kw in ("Cannot be delivered", "Undeliverable", "cannot be delivered"):
            for m in re.finditer(re.escape(kw), jr.text):
                print(f"        '{kw}' …{jr.text[max(0, m.start() - 300):m.start() + 120]!r}"[:600])
                break

# ── B ──────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 14, "B. time series", "=" * 14)
last = {}
rnd = 0
while time.time() - T0 < DUR:
    t_r = time.time()
    with ThreadPoolExecutor(8) as ex:
        pg = dict(zip(FOCUS, ex.map(lambda p: page(p)[0], FOCUS)))
        tp = dict(zip(FOCUS, ex.map(lambda p: tat(p, groups[p], "248001", pinfos[p], pg[p].get(p) or {}, "page"), FOCUS)))
    for pid, nm in FOCUS.items():
        g, res = tp[pid]
        cur = {"CS": (pg[pid].get(pid) or {}).get("CS"), "grp": g.get(pid), "IsSv": res.get("IsServicable"),
               "TAT": res.get("ProductTAT"), "disp": res.get("DispatchHrs"), "NDD": res.get("IsNDD"),
               "ship": re.sub("<[^>]+>", "", str(res.get("ShippingDate") or ""))[:28]}
        OUT["B"].append((round(time.time() - T0), pid, cur))
        p = last.get(pid)
        if p is None:
            print(f"{el()} {nm:18} start {cur}")
        elif p != cur:
            print(f"{el()} {nm:18} " + " ".join(f"{k}:{p[k]}->{cur[k]}" for k in cur if p[k] != cur[k]))
        last[pid] = cur
    rnd += 1
    time.sleep(max(0, 15 - (time.time() - t_r)))
print(f"\n{el()} {rnd} rounds; last: " + json.dumps(last, ensure_ascii=False))
json.dump(OUT, open("probe_report.json", "w"), indent=1, default=str)
print(f"done in {time.time() - T0:.0f}s")
