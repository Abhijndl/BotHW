#!/usr/bin/env python3
"""Probe #37: cars the cart would take while their product page says 0 — how
many units does the cart have for 248001, and is the car on FirstCry's in-stock
list for 248001? (25 Oct 10:00 the Dino 206 GT was buyable from Favourites
while its page still said Out of Stock.) Four looks, a minute apart. Read-only:
no Telegram, nothing saved, nothing ordered."""
import importlib.util, json, os, time, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.update({"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": "", "FC_CART": "true", "FC_LIVE_DEBUG": ""})
spec = importlib.util.spec_from_file_location("bot_v173", os.path.join(ROOT, "bot_v173.py"))
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)
with urllib.request.urlopen("https://raw.githubusercontent.com/Abhijndl/BotHW/main/seen.json", timeout=30) as r:
    seen = json.loads(r.read())
fc = {k[3:]: v for k, v in seen.items() if k.startswith("fc_") and isinstance(v, dict)}
watch = [p for p, v in fc.items() if v.get("stock") != "in_stock"
         and (v.get("fc_cart") == "y" or v.get("fc_live") in ("page 0", "arriving"))]
held = [p for p, v in fc.items() if v.get("stock") == "in_stock"]
print(f"{len(watch)} cars the cart said yes to while held sold out; {len(held)} held in stock")
report = []
for look in range(4):
    t0 = time.time()
    inst = bot.fc_api_catalogue(hot=True) or {}
    listed = {str(k) for k in inst}
    cart = bot.fc_cart_check(watch + held) or {}
    live = bot.fc_live_check(watch, max_pages=20) if watch else {}
    rows = []
    for p in watch:
        a = cart.get(p) or {}
        e = live.get(p) or bot._FC_LIVE.get(p) or {}
        rows.append({"pid": p, "name": fc[p].get("name", "")[:58], "cart_ok": a.get("ok"), "cart_n": a.get("n"),
                     "page_cs": e.get("cs"), "isv": e.get("isv"), "on_list": p in listed,
                     "list_units": bot._fc_api_stock(inst[p])[1] if p in inst else None})
    print(f"\n== look {look + 1} ({time.strftime('%H:%M:%S')} UTC, {time.time() - t0:.0f}s): "
          f"{len(listed)} on the in-stock list")
    for r in sorted(rows, key=lambda r: -(r["cart_n"] or 0)):
        print(f"   cart {str(r['cart_ok']):5} n={str(r['cart_n']):4} page={str(r['page_cs']):4} "
              f"list={'yes' if r['on_list'] else 'no ':3} ({str(r['list_units']):4}) {r['name']}")
    # held cars: the cart's counts, for comparison
    ns = sorted(((cart.get(p) or {}).get("n") or 0) for p in held if (cart.get(p) or {}).get("ok"))
    if ns:
        print(f"   held in stock & cart ok: {len(ns)} cars, cart units median {ns[len(ns) // 2]}, "
              f"min {ns[0]}, ≤2 units: {sum(1 for n in ns if n <= 2)}")
    report.append(rows)
    time.sleep(max(0, 60 - (time.time() - t0)))
json.dump(report, open(os.path.join(ROOT, "probe_report.json"), "w"), indent=1, ensure_ascii=False)
