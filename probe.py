#!/usr/bin/env python3
"""Probe #36: dry run of v17.3 (bot_v173.py) — chase pieces of Matchbox,
Majorette and Hot Wheels Monster Trucks — against every live store, with no
Telegram (alerts printed, not sent), on a COPY of the current seen.json, with
the monitor's settings. Three runs back to back: errors, timings, what it would
send, what it now keeps out, and which names changed."""
import collections, importlib.util, json, os, shutil, time, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DRY = os.path.join(ROOT, "dry")
os.makedirs(DRY, exist_ok=True)
with urllib.request.urlopen("https://raw.githubusercontent.com/Abhijndl/BotHW/main/seen.json", timeout=30) as r:
    open(os.path.join(DRY, "seen.json"), "wb").write(r.read())
print("seen.json copied:", os.path.getsize(os.path.join(DRY, "seen.json")), "bytes")
shutil.copy(os.path.join(ROOT, "hw_cases.json"), os.path.join(DRY, "hw_cases.json"))

env = {
    "TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "ONLY_SOURCES": "fc,mg,kd,hm",
    "RUN_SECONDS": "40", "FC_EVERY": "12", "RUN_EXTEND_S": "0", "FC_CATALOGUE_EVERY": "120",
    "SILENT": "true", "FIRST_RUN_SILENT": "true", "MAX_ALERT_PRICE": "0", "DEBUG": "false",
    "WATCHLIST": "rlc,treasure hunt,team transport,car culture,boulevard,premium,silhouettes,kaido house,liberty walk",
    "FC_EXCLUDE": "monster truck,monster jam,monstred,hopper ball,track set,trackset,track and,track with,track builder,track creator,playset,play set,race off,raceway,speedway,garage,car wash,loop dash,loop track,launch & loop,launcher,stunt track,hot wheels city,ultimate garage,super loop,pit stop,action set,crash & track,ultimate,water bottle,sipper,canteen,sunglass,digital watch,wrist watch,t-shirt,tshirt,sweatshirt,sandwich box,lunch box,tiffin,play ball,school bag,backpack,umbrella,raincoat,socks,slippers,sandals,shoes,bicycle,car case,storage case,carry case,storage box",
    "FC_MARQUES": "porsche,ferrari,lamborghini,supra,skyline,gt-r,gtr,nissan,datsun,rx-7,rx7,mazda,civic,type r,nsx,honda,toyota,ae86,silvia,evo,lancer,subaru,wrx,impreza,celica,mr2,bmw,m3,m4,audi,rs6,mercedes,amg,bugatti,mclaren,aston martin,koenigsegg,pagani,alfa romeo,countach,aventador,huracan,diablo,testarossa,f40,f50,911,930,993,959,carrera,singer,mustang,corvette,camaro,challenger,charger,plymouth,premium,car culture,team transport,boulevard,rlc,treasure hunt,silver series,fast furious,exotics,legends,silhouettes,japan historics,modern classics",
    "FC_WATCH": "https://www.firstcry.com/hot-wheels/hot-wheels-premium-fast-and-furious-die-cast-toy-car-for-adult-collectors-orange/21161951/product-detail",
    "FC_LIVE_POLL": "4", "FC_RESTOCK_COOLDOWN_H": "1", "FC_MIN_ALERT_STOCK_TARGET": "1",
    "FC_MIN_ALERT_STOCK": "2", "FC_SURE_UNITS": "5", "FC_API_PARALLEL": "10",
    "SRC_WORKERS": "6", "FC_WORKERS": "10", "HM_WORKERS": "8", "FC_CART": "true", "FC_CART_MAX": "150",
    "FC_CART_COOLDOWN_MIN": "30", "FC_CART_COOLDOWN_OTHER_H": "6",
    "MG_BRANDS": "hotwheels,mattel,minigt,mini gt,kaido house", "MG_CATEGORIES": "trading card,tcg",
}
os.environ.update(env)
os.chdir(DRY)
spec = importlib.util.spec_from_file_location("bot_v173", os.path.join(ROOT, "bot_v173.py"))
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)
print("version:", (bot.__doc__ or "").strip().splitlines()[0])
sent = []


def fake_tg(msg, *a, **k):
    sent.append(msg)
    print("\n----- TELEGRAM (dry run, not sent) -----\n" + msg + "\n----------------------------------------")
    return True


bot.tg = fake_tg
bot._successor_waiting = lambda: True


def rows():
    return {k: v for k, v in json.load(open("seen.json")).items() if isinstance(v, dict) and k != "_meta"}


s0 = rows()
for n in range(1, 4):
    print(f"\n================ RUN {n} ================")
    before = rows()
    t0 = time.time()
    try:
        bot.main()
    except Exception:
        import traceback
        traceback.print_exc()
    after = rows()
    flips = [(k, (before.get(k) or {}).get("stock"), v.get("stock"), v.get("name", "")[:60])
             for k, v in after.items() if (before.get(k) or {}).get("stock") != v.get("stock")]
    renamed = [(k, (before.get(k) or {}).get("name", "")[:50], v.get("name", "")[:70])
               for k, v in after.items() if k in before and before[k].get("name") != v.get("name")]
    added = [(k, v.get("stock"), v.get("name", "")[:70]) for k, v in after.items() if k not in before]
    print(f"\nrun {n}: {time.time() - t0:.0f}s, {len(sent)} message(s) so far, {len(flips)} stock change(s), "
          f"{len(added)} new, {len(renamed)} renamed")
    for f in flips[:30]:
        print("   flip", f)
    for a in added[:30]:
        print("   new ", a)
    for r in renamed[:30]:
        print("   name", r)
    print("   by source:", dict(collections.Counter(v.get("source") for v in after.values())))
    print("   cart stats:", bot._FC_CART_STATS, "| live stats:", bot._FC_LIVE_STATS)
    time.sleep(max(0, 60 - (time.time() - t0)))

final = rows()
chase = [(k, v.get("stock"), v.get("name", "")[:80]) for k, v in final.items()
         if bot.hw_priority(v.get("name", "")) in ("sth", "schase", "th", "chase")]
print(f"\ntracked chase pieces (any store): {len(chase)}")
for c in chase:
    print("  ", c)
out_now = [(k, v.get("stock"), v.get("name", "")[:80]) for k, v in final.items() if bot._fc_excluded(v.get("name", ""))]
print(f"\nstored items v17.3 now keeps out: {len(out_now)}")
for o in out_now[:30]:
    print("  ", o)
print(f"\n{len(sent)} message(s) would have been sent in all")
json.dump({"sent": sent, "chase": chase, "out": out_now}, open(os.path.join(ROOT, "probe_report.json"), "w"),
          indent=1, ensure_ascii=False)
