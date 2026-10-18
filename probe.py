#!/usr/bin/env python3
"""Probe #14: dry run of v14 (bot_v14.py) against the live stores — no Telegram
(alerts printed, not sent), on a COPY of the current seen.json. Shows what the
first v14 runs would change and send."""
import importlib.util, json, os, shutil, sys, time, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DRY = os.path.join(ROOT, "dry")
os.makedirs(DRY, exist_ok=True)

# latest live state from main (raw file; may lag a few minutes behind)
with urllib.request.urlopen("https://raw.githubusercontent.com/Abhijndl/BotHW/main/seen.json", timeout=30) as r:
    open(os.path.join(DRY, "seen.json"), "wb").write(r.read())
print("seen.json copied:", os.path.getsize(os.path.join(DRY, "seen.json")), "bytes")

env = {
    "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "",
    "RUN_SECONDS": "40", "FC_EVERY": "12", "FC_CATALOGUE_EVERY": "600",
    "MG_EVERY_S": "120", "KD_EVERY_S": "120", "HM_EVERY_S": "600",
    "SILENT": "true", "FIRST_RUN_SILENT": "true", "MAX_ALERT_PRICE": "0", "DEBUG": "false",
    "WATCHLIST": "rlc,treasure hunt,team transport,car culture,boulevard,premium,silhouettes,kaido house,liberty walk",
    "FC_EXCLUDE": "monster truck,monster jam,monstred,hopper ball,track set,trackset,track and,track with,track builder,track creator,playset,play set,race off,raceway,speedway,garage,car wash,loop dash,loop track,launch & loop,launcher,stunt track,hot wheels city,ultimate garage,super loop,pit stop,action set,crash & track,ultimate",
    "FC_MARQUES": "porsche,ferrari,lamborghini,supra,skyline,gt-r,gtr,nissan,datsun,rx-7,rx7,mazda,civic,type r,nsx,honda,toyota,ae86,silvia,evo,lancer,subaru,wrx,impreza,celica,mr2,bmw,m3,m4,audi,rs6,mercedes,amg,bugatti,mclaren,aston martin,koenigsegg,pagani,alfa romeo,countach,aventador,huracan,diablo,testarossa,f40,f50,911,930,993,959,carrera,singer,mustang,corvette,camaro,challenger,charger,plymouth,premium,car culture,team transport,boulevard,rlc,treasure hunt,silver series,fast furious,exotics,legends,silhouettes,japan historics,modern classics",
    "FC_WATCH": "https://www.firstcry.com/hot-wheels/hot-wheels-premium-fast-and-furious-die-cast-toy-car-for-adult-collectors-orange/21161951/product-detail",
    "FC_API_PARALLEL": "10", "MG_BRANDS": "hotwheels,mattel,minigt,mini gt,kaido house",
    "MG_CATEGORIES": "trading card,tcg", "SRC_WORKERS": "6", "FC_WORKERS": "10", "HM_WORKERS": "8",
}
os.environ.update(env)
os.chdir(DRY)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


new = load(os.path.join(ROOT, "bot_v14.py"), "bot_v14")
sent = []
def fake_tg(msg):
    sent.append(msg)
    print("\n----- TELEGRAM (dry run, not sent) -----\n" + msg + "\n----------------------------------------")
new.tg = fake_tg

print("\n================ FORCED PASS: every store once ================")
seen = new.load_seen()
new._fc_fresh_load(seen)
t0 = time.time()
before = {k: v.get("stock") for k, v in seen.items() if k.startswith("fc_") and isinstance(v, dict)}
new.run_pass(seen, ["FirstCry"], False, True, "forced pass (FirstCry + full catalogue)")
after = {k: v.get("stock") for k, v in seen.items() if k.startswith("fc_") and isinstance(v, dict)}
flips = [(k, before.get(k), after[k], seen[k].get("name", "")[:60]) for k in after if before.get(k) != after[k]]
print("FirstCry stock changes in the forced pass:", len(flips))
for f in flips[:40]:
    print("   ", f)
print(f"forced pass took {time.time()-t0:.1f}s")
import collections
print("verdicts stored:", collections.Counter(v.get("fc_live") for k, v in seen.items() if k.startswith("fc_") and isinstance(v, dict)))
print("stats:", new._FC_LIVE_STATS)
for k, b, a, nm in flips[:60]:
    info = new._FC_LIVE.get(k[3:]) or {}
    print(f"   {k} {b} -> {a} | page CS {info.get('cs')} delivery {info.get('svc')} | verdict {seen[k].get('fc_live')} | {nm}")

print("\n================ DRY RUN of main() (alerts printed, not sent) ================")
t0 = time.time()
new.main()
print(f"main() took {time.time()-t0:.1f}s; {len(sent)} message(s) would have been sent")
print("stats:", new._FC_LIVE_STATS)
after2 = {k: v.get("stock") for k, v in seen.items() if k.startswith("fc_") and isinstance(v, dict)}

import collections
print("verdicts after run 1:", collections.Counter(v.get("fc_live") for k, v in new.load_seen().items() if k.startswith("fc_") and isinstance(v, dict)))
print("\n================ SECOND RUN (steady state) ================")
n0 = len(sent); p0 = dict(new._FC_LIVE_STATS)
t0 = time.time()
new.main()
print(f"run 2 took {time.time()-t0:.1f}s; {len(sent) - n0} message(s) would have been sent; "
      f"pages {new._FC_LIVE_STATS['pages'] - p0['pages']}, delivery checks {new._FC_LIVE_STATS['tat'] - p0['tat']}")
seen2 = new.load_seen()
print("verdicts after run 2:", collections.Counter(v.get("fc_live") for k, v in seen2.items() if k.startswith("fc_") and isinstance(v, dict)))
for k, v in seen2.items():
    if k.startswith("fc_") and isinstance(v, dict) and v.get("fc_live") in ("no delivery", "unconfirmed", "last unit"):
        print(f"   {k} {v.get('stock')} {v.get('fc_live')} | {v.get('name', '')[:60]}")
