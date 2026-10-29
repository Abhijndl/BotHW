#!/usr/bin/env python3
"""KND recorder (research, 29 Oct): polls Karz & Dolls' shelves far more often
than the tracker does and logs every car that appears on / disappears from a
shelf, with the time, so we can measure how long cars really stay in stock —
including the ones that come and go between the tracker's 2-minute checks.
Read-only: it only loads public shelf pages. Output: kd_rec.jsonl (events),
kd_rec_polls.json (per-page poll counts, failures, response times)."""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as http

KD = "https://www.karzanddolls.com"
FAST = ["/mini-gt/mini-gt", "/mini-gt/mini-gt-blister-pack", "/specials/special-stocks-64-43-scale", "/",
        "/specials/chase-car", "/mini-gt/kaido-house"]
SLOW = ["/hot-wheels/mainlines", "/hot-wheels/pop-culture", "/hot-wheels/card-art-premiums", "/hot-wheels/gift-pack",
        "/hot-wheels/car-culture", "/hot-wheels/fast-and-furious", "/hot-wheels/boulevard-series", "/hot-wheels/team-transport",
        "/hot-wheels/character-cars", "/hot-wheels/disney-cars", "/hot-wheels/hot-wheels-accessories", "/pre-orders/pre-order-minigt",
        "/pre-orders/pre-order-special-stock", "/hot-wheels/monster-trucks", "/matchbox/matchbox-basic-cars",
        "/matchbox/matchbox-moving-parts", "/matchbox/matchbox-superfast", "/majorette/premium-cars", "/majorette/basic-cars",
        "/majorette/majorette"]
FAST_S = float(os.getenv("KDREC_FAST_S", "15"))
SLOW_S = float(os.getenv("KDREC_SLOW_S", "45"))
RUN_FOR = float(os.getenv("KDREC_RUN_FOR_S", str(5 * 3600 + 40 * 60)))
SAVE_EVERY = 20 * 60
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)
lock = threading.Lock()
EV = open("kd_rec.jsonl", "a", buffering=1)
last = {}           # page -> {pid: info}
polls = {p: {"ok": 0, "fail": 0, "secs": [], "n": None} for p in FAST + SLOW}
inflight = set()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}Z"


def products(page):
    m = NEXT.search(page or "")
    if not m:
        return None
    pp = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
    found, stack = {}, [pp]
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            if "pid" in n and "pro_name" in n:
                found[str(n["pid"])] = n
            else:
                stack.extend(n.values())
    return found


def poll(path):
    t0 = time.time()
    t_iso = now()
    try:
        r = http.get(KD + path, headers=H, timeout=25, impersonate="chrome124")
        ok = r.status_code == 200 and len(r.text) > 4000
        ps = products(r.text) if ok else None
    except Exception as e:
        ok, ps = False, None
    dt = round(time.time() - t0, 2)
    with lock:
        inflight.discard(path)
        st = polls[path]
        if ps is None:
            st["fail"] += 1
            return
        st["ok"] += 1
        st["secs"].append(dt)
        cur = {pid: p for pid, p in ps.items() if str(p.get("in_stock")) in ("1", "True", "true")}
        st["n"] = len(cur)
        old = last.get(path)
        if old is None:
            EV.write(json.dumps({"t": t_iso, "ts": round(t0, 2), "page": path, "ev": "base", "n": len(cur),
                                 "pids": sorted(cur)}) + "\n")
        else:
            for pid in cur.keys() - old.keys():
                p = cur[pid]
                EV.write(json.dumps({"t": t_iso, "ts": round(t0, 2), "page": path, "ev": "in", "pid": pid,
                                     "nm": re.sub(r"\s+", " ", str(p.get("pro_name"))).strip()[:120],
                                     "sku": re.sub(r"\s+", " ", str(p.get("sku") or "")).strip()[:60],
                                     "p": p.get("dis_price"), "pre": p.get("is_preorder"), "lim": p.get("add_limit")},
                                    ensure_ascii=False) + "\n")
            for pid in old.keys() - cur.keys():
                EV.write(json.dumps({"t": t_iso, "ts": round(t0, 2), "page": path, "ev": "out", "pid": pid,
                                     "nm": re.sub(r"\s+", " ", str(old[pid].get("pro_name"))).strip()[:120]},
                                    ensure_ascii=False) + "\n")
        last[path] = cur


def save(final=False):
    with lock:
        summ = {p: {"ok": v["ok"], "fail": v["fail"], "n": v["n"],
                    "avg_s": round(sum(v["secs"]) / len(v["secs"]), 2) if v["secs"] else None,
                    "p90_s": sorted(v["secs"])[int(len(v["secs"]) * 0.9)] if v["secs"] else None} for p, v in polls.items()}
        json.dump({"updated": now(), "fast_s": FAST_S, "slow_s": SLOW_S, "pages": summ}, open("kd_rec_polls.json", "w"), indent=1)
    cmds = [["git", "add", "-f", "kd_rec.jsonl", "kd_rec_polls.json"],
            ["git", "-c", "user.name=github-actions", "-c", "user.email=actions@github.com", "commit", "-q", "-m",
             f"kd recorder {'final' if final else 'checkpoint'} [skip ci]"]]
    for c in cmds:
        subprocess.run(c, capture_output=True)
    for _ in range(4):
        subprocess.run(["git", "pull", "-q", "--rebase", "-X", "ours", "origin", "claude/probe"], capture_output=True)
        if subprocess.run(["git", "push", "-q", "origin", "HEAD:claude/probe"], capture_output=True).returncode == 0:
            print(f"[{now()}] saved", flush=True)
            return
        time.sleep(3)
    print(f"[{now()}] save failed", flush=True)


start = time.time()
due = {p: start + i * (FAST_S / len(FAST)) for i, p in enumerate(FAST)}
due.update({p: start + i * (SLOW_S / len(SLOW)) for i, p in enumerate(SLOW)})
every = {**{p: FAST_S for p in FAST}, **{p: SLOW_S for p in SLOW}}
next_save = start + SAVE_EVERY
print(f"recording {len(FAST)} pages every {FAST_S:.0f}s and {len(SLOW)} every {SLOW_S:.0f}s for {RUN_FOR/3600:.1f} h", flush=True)
with ThreadPoolExecutor(6) as ex:
    while time.time() - start < RUN_FOR:
        t = time.time()
        for p, d in due.items():
            if d <= t and p not in inflight:
                with lock:
                    inflight.add(p)
                due[p] = max(d + every[p], t)
                ex.submit(poll, p)
        if t >= next_save:
            next_save = t + SAVE_EVERY
            threading.Thread(target=save, daemon=True).start()
        time.sleep(0.25)
time.sleep(30)
save(final=True)
