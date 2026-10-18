#!/usr/bin/env python3
"""Probe #3: run the NEW bot (bot_v13.py) for real against the live stores, in a
dry run — no Telegram credentials (alerts are printed instead of sent) and a
COPY of the current seen.json, so the live bot and its state are untouched.
Also compares the new Karz & Dolls JSON parser with the old HTML parser."""
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
    "RUN_SECONDS": os.getenv("RUN_SECONDS", "45"), "FC_EVERY": "20", "FC_FULL_EVERY": "60",
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


new = load(os.path.join(ROOT, "bot_v13.py"), "bot_v13")
old = load(os.path.join(ROOT, "bot.py"), "bot_old")

print("\n================ KND: new JSON parser vs old HTML parser ================")
t0 = time.time(); kn = new.scrape_karzanddolls(); t1 = time.time()
ko = old.scrape_karzanddolls(); t2 = time.time()
sn = {d["id"]: d for d in kn}; so = {d["id"]: d for d in ko}
print(f"new: {len(sn)} products in {t1-t0:.1f}s (healthy={new.KD_HEALTHY[0]}); old: {len(so)} in {t2-t1:.1f}s")
print("only in new:", [(k, sn[k]['name'][:50], sn[k]['stock']) for k in sorted(set(sn) - set(so))][:40])
print("only in old:", [(k, so[k]['name'][:50]) for k in sorted(set(so) - set(sn))][:40])
diff = [(k, so[k]['stock'], sn[k]['stock'], so[k]['price'], sn[k]['price'], sn[k]['name'][:40])
        for k in set(sn) & set(so) if (so[k]['stock'], so[k]['price']) != (sn[k]['stock'], sn[k]['price'])]
print("stock/price differences:", diff[:30])
names = [(sn[k]['name'][:45], so[k]['name'][:45]) for k in list(set(sn) & set(so))[:8]]
print("name samples (new, old):", names)

print("\n================ Minifygram ================")
mg = new.scrape_minifygram()
print("watermark:", new.mg_watermark(), "| last full-fetch watermark:", new._MG_LAST_WM[0])
for d in mg:
    if "🃏" in d["name"] or "[PRE-ORDER]" in d["name"]:
        print("  ", d["stock"], d["price"], d["name"][:80])

print("\n================ DRY RUN of main() (alerts printed, not sent) ================")
t0 = time.time()
new.main()
print(f"main() took {time.time()-t0:.1f}s")
