#!/usr/bin/env python3
"""
Hot Wheels / Diecast Collector Tracker  ·  v17.4
================================================
Stores  : FirstCry · Minifygram · Karz & Dolls · Hamleys  (Dehradun 248001)
          (Blinkit / BigBasket block GitHub's servers — phone watcher covers them)
Runtime : Pure HTTP (curl_cffi with a real Chrome fingerprint). No browser.
Host    : GitHub Actions, triggered every minute by cron-job.org; state lives in
          seen.json, committed back after each run.

HOW A RUN WORKS
---------------
FirstCry, v17: its own CHECKOUT CART has the final word. Asked as a guest about
a cart for 248001 (a cookie string — nothing is stored or ordered), it answers
per car what your app's cart shows: the units it can send to your pincode and
the delivery date — or nothing / 0 where your cart says "Cannot be delivered to
248001". Every FirstCry stock change is decided by it; the listing, product
pages and delivery check described below only point at cars to ask about, and
every Hot Wheels car is asked in turn (🎯 cars about every half minute). The
signals below are the fallback when the cart can't be asked.
v17.1: and the car's product page must sell it too ("Add to cart", not "Notify
me") — the cart counts units the page has already sold (the Armored Batmobile,
23 Oct 16:20). No alert ever goes out while the page says 0.
v17.2: a 🎯 car the cart already has while its page says 0 is about to go on
sale (the Custom Otto: 25 min like that, then its one unit sold 37 s after it
did), so its page is read every pass. A 🎯 car may alert again 30 min after its
last alert; any other car at most every 6 h.
v17.3: chase pieces of Matchbox, Majorette and Hot Wheels Monster Trucks are
tracked too — a Super Chase, a chase car, a Treasure Hunt — wherever a store
says so: Karz & Dolls' chase shelf, names and SKU lines (its Matchbox, Majorette
and monster-truck shelves are read now), Minifygram's badges and names. Every
other Matchbox / Majorette / monster truck stays out, however the store spells
it ("Monster Toy Truck", "MONST ER TRUCKS" used to slip through). Minifygram's
"Treasure Hunt" badge now marks a Hot Wheels car whose name doesn't say so.
v17.4: a fresh release alerts before its page catches up. 25 Oct 10:00 the
Dino 206 GT came onto FirstCry's in-stock list for 248001 with a batch in the
cart while its page said "Out of Stock" for 3 more minutes — buyable from your
Profile all along (a deals channel posted it then; we waited for the page and
alerted at 10:04, as it sold out). A car that came onto that list in the last
10 min with 5+ units in the cart now alerts at once, saying how to buy it
(♡ it, add it from Favourites). Your marques also count by the case
checklist's series: the Dino 206 GT is a 2026 "Ferrari" → ❤️ FERRARI, 🎯.
And a car coming back needs FC_MIN_ALERT_STOCK units again (2; one for 🎯
cars), as your settings say — since v17 the cart let single units of any car
through ("only 1 left" Track Ripper, 25 Oct).

Each run stays alive RUN_SECONDS (40 s on GitHub) and checks in passes:
  • FirstCry every FC_EVERY seconds (12 s). Its listing (in-stock list every
    pass, whole catalogue every 2 min, both read live) says where to look;
    the PRODUCT PAGE decides (v14). A car only counts as orderable when its
    freshly loaded page shows units (ADD TO CART) AND FirstCry's own delivery
    check says FC_MIN_ALERT_STOCK+ units can reach your pincode (v15: its
    IsServicable count — the SF90 showed 155 on the page and 1 for 248001;
    v15.1: one unit is enough for your 🎯 cars, FC_MIN_ALERT_STOCK_TARGET).
    v16.1: that count is national, not your pincode's — FirstCry's cart is
    what knows "Cannot be delivered to 248001". So fewer than FC_SURE_UNITS (5)
    units alert only once FirstCry's in-stock list for 248001 shows the car
    too, and a car whose alert was gone within minutes needs 5+ for 12 h.
    v16.2: when that list and the delivery check say yes but the product page
    still shows 0 (new stock — the page catches up 1-15 min later), it alerts.
    v16.3: for a car listed in the last few hours (FC_NEW_FRESH_H) the
    catalogue counts as that list too, and a car seen for the first time gets
    its delivery check at once — 21 Oct a brand-new '20 Charger Hellcat had
    units in the catalogue at 22:20 (already buyable: ♡ it, then add it to the
    cart from Favourites), reached the in-stock list at 22:27 and was gone by
    22:33. Such alerts carry that tip. The catalogue is now read every 2 min
    (FC_CATALOGUE_EVERY), since new cars show up there first. An alert on a
    page that still says 0 needs that state to be new (FC_PAGE_LAG_MIN): a
    Lucid Air sat like that for days and was alerted and gone at 23:12. Apart
    from that brand-new case, only the in-stock list for 248001 vouches for a
    few units — the catalogue shows cars that list leaves out for days. After a
    phantom, a car alerts again only once two readings in a row say it can
    reach you.
    v16.4: every car coming back must be on that in-stock list for 248001 —
    22 Oct 10:39 the AAR Cuda alerted with 5 units (5+ used to skip the list),
    the list never had it, and the cart said "just went out of stock". A car
    held in stock that the list hasn't shown for 10 min (FC_OFFLIST_MIN) is out
    for you, so its real restock can alert.
    The listing lagged the page by up to ~10 min and kept showing cars nobody
    could order. Every pass, the cheap delivery check also looks at every 🎯
    car (and every tracked car once a run), so a car becoming deliverable is
    seen within seconds; the product pages of out-of-stock 🎯 sets are read in
    a rotation that reaches every set.
  • Minifygram: full list every 2 min, plus a tiny "anything changed?" check
    every pass that pulls new listings in within seconds. Trading cards too.
  • Karz & Dolls every 2 min, read from the JSON the site embeds in its pages.
  • Hamleys every 10 min.
  The slower stores only run in each run's first pass, so runs end before the
  next trigger. If no next run is waiting when the time is up (cron-job.org
  skipped or delayed a trigger), the run keeps watching up to RUN_EXTEND_S more.
Alerts go out the moment a store's check finishes; nothing waits for slower
stores. Runs are chained back to back, so the watch is continuous.

ALERTS
------
🆕 new listing (in stock) · 🔥 back in stock · 💸 price drop
🎯 = one of your marques / watchlist (listed first) · ✅/⚠️ N left for 248001 =
what FirstCry's cart can send you (v17), with its delivery date (🚚). 📦 … (all-India)
= FirstCry's national count, shown only when the cart couldn't be asked.
v16: every 🎯 car that's in stock gets its own message, and its first line
says what it is — Treasure Hunts and the like first:
  💎 SUPER TREASURE HUNT   💎 SUPER CHASE   🏆 TREASURE HUNT   ⛓️ CHASE   🔩 ZAMAC
  (a chase piece of another line says which: "⛓️ CHASE · MAJORETTE",
   "💎 SUPER CHASE · MATCHBOX", "🏆 TREASURE HUNT · MONSTER TRUCKS")
  ✨ STH CAR (the regular car whose Super TH is packed in the same case —
     FirstCry doesn't sort them out)
  ❤️ Ferrari  🖤 Porsche  💛 Lamborghini  💙 Skyline / GT-R / Nissan
  🧡 Supra / Toyota  💜 Honda / Mazda / Subaru / Mitsubishi
  🤍 BMW / Mercedes / Audi / McLaren / Bugatti …  💚 Mustang / Corvette / Dodge …
  🩵 premium lines (RLC, Car Culture, Boulevard, Silver Series …)
Every alert also says which case a mainline car is from ("📦 2026 Case M ·
Cool Classics · #228"), from hw_cases.json — rebuilt daily by cases.py from
the 164custom.com checklists (no extra requests to any store). TH / STH / chase
/ ZAMAC cars are 🎯 too: checked every pass, alerted from one unit.
FirstCry links open a freshly rendered page (…?fresh=…), not a CDN copy that
can be 20 minutes old.
Every product's NEW alert fires once ever. Restocks: 1 h cooldown when
FirstCry's product page confirmed them, 24 h otherwise.
"""

import os
import re
import json
import html
import time
import calendar
import threading
import traceback
import difflib
import functools
from urllib.parse import quote, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── HTTP client ────────────────────────────────────────────────────────────────
# curl_cffi impersonates a real Chrome TLS/JA3 fingerprint, which is what lets
# plain HTTP requests past Akamai/Cloudflare bot walls that block vanilla
# python-requests. This is the single most important dependency.
try:
    from curl_cffi import requests as http
    _IMPERSONATE = {"impersonate": "chrome124"}
except Exception:                     # graceful fallback if curl_cffi missing
    import requests as http           # type: ignore
    _IMPERSONATE = {}


# ── Config ──────────────────────────────────────────────────────────────────────
PINCODE   = "248001"
CITY      = "Dehradun"
LAT, LON  = 30.3165, 78.0322          # Dehradun centre — used for Blinkit

SEEN_FILE = "seen.json"

# Set by runner.py (always-on mode) to run only the sources that are due this
# tick, so each store can have its own cadence. None = run everything (the
# normal GitHub Actions behaviour, unchanged).
ACTIVE_SOURCES = None

# ONLY_SOURCES lets a single run check just some stores — e.g. the extra
# every-minute cron-job.org trigger sends only="firstcry". Accepts short names.
_SRC_ALIASES = {"firstcry": "FirstCry", "fc": "FirstCry",
                "minifygram": "Minifygram", "mg": "Minifygram",
                "hamleys": "Hamleys", "hm": "Hamleys",
                "karzdolls": "Karz&Dolls", "karzanddolls": "Karz&Dolls", "kd": "Karz&Dolls",
                "bigbasket": "BigBasket", "bb": "BigBasket",
                "blinkit": "Blinkit", "bl": "Blinkit"}
_only = {_SRC_ALIASES.get(t.strip().lower().replace(" ", "").replace("&", ""))
         for t in os.getenv("ONLY_SOURCES", "").split(",") if t.strip()}
_only.discard(None)
if _only:
    ACTIVE_SOURCES = _only

# Behaviour toggles (set as env in the workflow)
DEBUG   = os.getenv("DEBUG",   "false").lower() == "true"   # verbose + heartbeat msg
SILENT  = os.getenv("SILENT",  "true").lower()  == "true"   # only ping on real changes
FIRST_RUN_SILENT = os.getenv("FIRST_RUN_SILENT", "true").lower() == "true"

# Only alert on cars at/under this price on the "new listing" channel, so you're
# not spammed by ₹3000 track sets. Set to 0 to disable the filter.
MAX_ALERT_PRICE = int(os.getenv("MAX_ALERT_PRICE", "0"))

# Optional keyword watchlist — if set, new_listing alerts for matching names get
# an extra 🎯 flag (case-insensitive, comma separated). e.g. "rlc,treasure hunt,team transport"
WATCHLIST = [w.strip().lower() for w in os.getenv("WATCHLIST", "").split(",") if w.strip()]

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
# The secret may hold SEVERAL chats separated by commas, e.g. your own chat plus a
# friends' group:  "123456789,-1001234567890"  (group ids start with a minus).
TELEGRAM_CHAT_IDS  = [c for c in re.split(r"[\s,;]+", TELEGRAM_CHAT_ID or "") if c]

TIMEOUT = 30

# ── Concurrency ────────────────────────────────────────────────────────────────
SRC_WORKERS = int(os.getenv("SRC_WORKERS", "6"))
FC_WORKERS  = int(os.getenv("FC_WORKERS", "10"))
HM_WORKERS  = int(os.getenv("HM_WORKERS", "8"))

# ── Run loop & per-store schedule (v13) ────────────────────────────────────────
# RUN_SECONDS > 0 keeps one run alive for that long, re-checking FirstCry every
# FC_EVERY seconds and alerting the moment something changes. With cron-job.org
# dispatching every minute, runs follow each other back to back, so FirstCry is
# watched continuously instead of once a minute. 0 = classic single pass.
RUN_SECONDS   = float(os.getenv("RUN_SECONDS", "0"))
FC_EVERY      = max(8.0, float(os.getenv("FC_EVERY", "12")))
# v14.1: when RUN_SECONDS is up and NO other run is waiting to take over, keep
# checking for up to RUN_EXTEND_S more seconds (asking GitHub every pass), so a
# trigger that cron-job.org skips or sends late doesn't leave FirstCry
# unwatched. Measured 18 Oct: no trigger ever arrived in minutes ending in 5,
# and the :x0 one came ~35 s late — gaps of 65-84 s without a single check.
# If GitHub can't be asked, the run ends on time as before.
RUN_EXTEND_S  = max(0.0, float(os.getenv("RUN_EXTEND_S", "0")))
# How often the WHOLE FirstCry catalogue (sold-out cars included) is read, in
# seconds. Every pass reads FirstCry's in-stock list; the catalogue keeps new
# sold-out listings and names/prices current — and a brand-new car often shows
# units there minutes before the in-stock list has it (v16.3: 2 min, was 10;
# it's ~21 pages fetched in parallel, a couple of seconds).
FC_CATALOGUE_EVERY = float(os.getenv("FC_CATALOGUE_EVERY", "120"))

# Each store is checked when it is due, whatever triggered the run, so one
# every-minute trigger covers everything. Seconds between checks; -1 = never.
_ON_GITHUB = os.getenv("GITHUB_ACTIONS", "").lower() == "true"
MG_WATCH = os.getenv("MG_WATCH", "true").lower() == "true"
SOURCE_EVERY = {
    "FirstCry":   0,
    # full Minifygram list every 2 min; in between, a tiny "anything changed?"
    # check every pass (MG_WATCH) pulls it in early when something moves
    "Minifygram": float(os.getenv("MG_EVERY_S", "120")),
    "Karz&Dolls": float(os.getenv("KD_EVERY_S", "120")),
    "Hamleys":    float(os.getenv("HM_EVERY_S", "600")),
    # Both geo-block GitHub's US runners (HTTP 403 on every call), so on GitHub
    # they're skipped unless explicitly re-enabled. The phone watcher covers them.
    "BigBasket":  float(os.getenv("BB_EVERY_S", "-1" if _ON_GITHUB else "900")),
    "Blinkit":    float(os.getenv("BL_EVERY_S", "-1" if _ON_GITHUB else "900")),
}

COMMON_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── Telegram ─────────────────────────────────────────────────────────────────────
def _tg_send(idx: int, msg: str) -> bool:
    """Send to one chat. Follows a group→supergroup upgrade (the group gets a new
    id) and waits out one Telegram rate-limit; anything else is logged plainly."""
    label = f"chat {idx + 1} (…{TELEGRAM_CHAT_IDS[idx][-4:]})"
    for _ in range(3):
        r = http.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_IDS[idx], "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": "true"},
            timeout=15, **_IMPERSONATE)
        if r.ok:
            return True
        try:
            j = r.json() or {}
        except Exception:
            j = {}
        p = j.get("parameters") or {}
        if p.get("migrate_to_chat_id"):
            new_id = str(p["migrate_to_chat_id"])
            print(f"[TG] {label} was upgraded to a supergroup; its id is now {new_id}. "
                  f"Put {new_id} in the TELEGRAM_CHAT_ID secret.")
            TELEGRAM_CHAT_IDS[idx] = new_id
            continue
        if r.status_code == 429 and p.get("retry_after"):
            time.sleep(min(int(p["retry_after"]), 30))
            continue
        print(f"[TG] {label} failed {r.status_code}: "
              f"{j.get('description') or r.text[:150]}")
        return False
    return False


def tg(msg: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS):
        print("[TG] (no creds) " + msg[:200]); return
    ok = 0
    for i in range(len(TELEGRAM_CHAT_IDS)):
        try:
            ok += _tg_send(i, msg)
        except Exception as e:
            print(f"[TG] chat {i + 1}: {e}")
    print(f"[TG] sent to {ok}/{len(TELEGRAM_CHAT_IDS)} chat(s)")


# ── State ─────────────────────────────────────────────────────────────────────────
# seen.json is a PERMANENT memory of every product ever observed, keyed by id:
#   { stock, name, price, source, url, first_seen, last_seen, alerted_new, last_restock_alert }
#
# CRITICAL DESIGN RULE — MERGE, never overwrite:
# FirstCry only exposes ~28 items per sort view, and the visible slice rotates
# between runs. The old code replaced seen.json with just the currently-visible
# items, so anything that rotated out of view was forgotten — and re-alerted as
# "NEW" when it rotated back in. That was the repeated-alert bug. Now products
# that aren't visible this run simply keep their last-known state.
def load_seen() -> dict:
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _bucket(ts: str) -> str:
    """Floor an ISO timestamp to 15 minutes. Timestamps that changed on EVERY run
    made seen.json differ on every run, forcing a git commit + push each time.
    Rounded, a quiet run produces an identical file, the save step is skipped,
    and runs finish sooner. All timing logic works in hours, so 15-minute
    precision changes nothing about behaviour."""
    if not ts or len(ts) < 16:
        return ts
    try:
        return f"{ts[:14]}{int(ts[14:16]) // 15 * 15:02d}:00"
    except ValueError:
        return ts


def merge_and_save_seen(seen: dict, current: dict) -> None:
    """Merge this run's observations into the permanent memory and persist it."""
    now = _bucket(time.strftime("%Y-%m-%dT%H:%M:%S"))
    for pid, d in current.items():
        prev = seen.get(pid, {})
        entry = {
            "stock":  d["stock"],
            "name":   d["name"],
            "price":  d.get("price", "") or prev.get("price", ""),
            "source": d.get("source", ""),
            "url":    d.get("url", "") or prev.get("url", ""),
            "first_seen": prev.get("first_seen", now),
            "last_seen":  now,
            # alert bookkeeping survives the merge
            "alerted_new":        prev.get("alerted_new", False),
            "last_restock_alert": prev.get("last_restock_alert", ""),
            "last_price_alert":   prev.get("last_price_alert", ""),
        }
        # per-source bookkeeping (e.g. Minifygram's stock-detection version tag)
        for k in ("mg_updated_at", "stock_ver", "hm_verified_at", "auto_watch",
                  "fc_listed_at", "fc_api_seen_at", "fc_trusted", "fc_live", "fc_lst", "fc_gid", "fc_phantom",
                  "fc_new_pending", "fc_pb", "fc_arr", "fc_off", "fc_cart",
                  "fc_svc", "fc_lst_on", "fc_lst_seen"):
            v = d.get(k, prev.get(k, ""))
            if k in ("hm_verified_at", "fc_listed_at", "fc_api_seen_at", "fc_lst_seen") and isinstance(v, str):
                v = _bucket(v)
            if v:
                entry[k] = v
        seen[pid] = entry
    _save_seen_file(seen)


def _save_seen_file(seen: dict) -> None:
    meta = seen.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
    meta["fc_offset"] = _FC_NEXT_OFFSET[0]
    seen["_meta"] = meta
    # Written to a temp file and swapped in, so a reader never sees half a file
    # (stores are checked in parallel threads while results are being saved).
    tmp = SEEN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SEEN_FILE)


def _hours_since(iso: str) -> float:
    if not iso:
        return 1e9
    try:
        then = time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%S"))
        return (time.time() - then) / 3600.0
    except Exception:
        return 1e9


def price_to_int(p) -> int | None:
    if p is None:
        return None
    digits = re.sub(r"[^\d]", "", str(p).split(".")[0])
    return int(digits) if digits else None


# ══════════════════════════════════════════════════════════════════════════════════
# SOURCE 1 — FirstCry  (v8 — correct prices, real links, wider discovery)
# ══════════════════════════════════════════════════════════════════════════════════
# THREE BUGS THIS RELEASE FIXES, all confirmed from live alerts:
#
# 1. PRICE DROP SPAM ("Gone mad" alerted 4-5x, "was ₹157" → "₹100").
#    The price parser read numbers out of the PRODUCT NAME and out of FirstCry's
#    club-cash boilerplate:
#      • "Erikenstein ROD (117/250)"  → mrp ₹250, "was ₹117"  (collector number!)
#      • "1970 Custom Plymouth"       → mrp ₹1970             (model year!)
#      • "(Min. 100/- Club Cash …)"   → price ₹100            (boilerplate!)
#    The recurring ₹100 flapping against the real price is what produced the
#    repeated PRICE DROP alerts for the same car.
#    Now: the product name is REMOVED from the text before any number is read,
#    collector patterns (117/250) and years (19xx/20xx) are stripped, club-cash
#    boilerplate is stripped, ₹-prefixed amounts are strongly preferred, and an
#    MRP is only accepted if it is a sane multiple of the price.
#
# 2. LINKS OPENING ON SOLD-OUT / WRONG PAGES.
#    Alerts used a synthetic /x/x/{id}/product-detail URL. We now capture the
#    REAL canonical href from the card itself, so links land on the proper page.
#
# 3. NEW ARRIVALS MISSED (Audi RS 5, Czinger 21C, Pagani Utopia …).
#    FirstCry's search takes ?searchstring= — the ?q= form used before is not
#    valid, so those "search slices" contributed nothing. Search pages are now
#    correct, and a set of model/series keyword searches is included, each of
#    which is an independent server-rendered slice of ~20 products.
_FC_FACET = ("https://www.firstcry.com/toy-cars,-trains-and-vehicles/hotwheels"
             "?cid=5&scid=94&character-shop=t5-7701")
_FC_SEARCH = "https://www.firstcry.com/search?searchstring="

_FC_BRAND = "https://www.firstcry.com/hot-wheels/5/0/113"
_FC_CAT = "?cid=5&scid=94&character-shop=t5-7701"
_FC_FACET = "https://www.firstcry.com/toy-cars,-trains-and-vehicles/hotwheels" + _FC_CAT

# CORE pages — fetched EVERY run. The brand pages carry the footer
# "New Arrivals:" list, which is the fastest signal for a genuinely new SKU.
_FC_CORE_URLS = [
    "https://www.firstcry.com/hot-wheels/0/0/113",
    _FC_BRAND,
    "https://www.firstcry.com/hot-wheels/toy-cars-trains-and-vehicles/5/94/113",
    "https://www.firstcry.com/toy-cars,-trains-and-vehicles/cars-and-jeeps/hot-wheels"
    "?cid=5&scid=94&type=t1-7973&brand=113",
    _FC_SEARCH + "hot%20wheels",
    _FC_SEARCH + "hot%20wheels%20die%20cast",
]

# ROTATING pool — a slice is fetched each run, advancing every run, so the whole
# pool is covered every few runs without hammering FirstCry.
#
# WHY SO MANY: the brand page reports 380 items but server-renders only ~20.
# Sorting and "Show More Products" are JavaScript-only (verified: every sort
# option is a javascript:void(0) link and ?sort=/?ProductPage= are stripped
# server-side). So each URL is a ~20-product window and the ONLY way to see the
# rest of the catalog is to open many different windows. Filter facets (price
# band, colour, age, discount) and keyword searches each produce a different
# window; their union is our catalog.
_FC_ROTATE_URLS = (
    # price bands — the site's own buckets (0-250:164, 250-500:87, 500-1000:103,
    # 1000-2000:20, 2000-3000:5, 3000-4000:3)
    [f"{_FC_FACET}&price={a}-{b}" for a, b in
     ((0, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 3000), (3000, 4000))]
    + [f"{_FC_BRAND}?price={a}-{b}" for a, b in
       ((0, 250), (250, 500), (500, 1000), (1000, 2000))]
    # colours — small buckets, so each window covers most of its colour
    + [f"{_FC_FACET}&color={c}" for c in
       ("Blue", "Red", "Black", "White", "Orange", "Yellow", "Green", "Purple",
        "Grey", "Silver", "Multi%20Color", "Light%2FSky%20Blue", "Dark%20Green",
        "Golden", "Brown", "Pink", "Maroon", "Navy%20Blue")]
    # age / discount / gender facets
    + [f"{_FC_FACET}&age={a}" for a in (4, 6, 8, 10, 12)]
    + [f"{_FC_FACET}&discount={d}" for d in ("0-10", "10-20", "20-30", "40-100")]
    + [f"{_FC_FACET}&gender={g}" for g in ("boy", "girl", "unisex")]
    + [f"{_FC_FACET}&sub-type=t6-7966", f"{_FC_FACET}&sub-type=t6-7972",
       f"{_FC_FACET}&skills=4", f"{_FC_FACET}&skills=7"]
    # keyword searches — series, then marques/models seen in the catalogue
    + [_FC_SEARCH + quote(t) for t in (
        "hot wheels premium", "hot wheels car culture", "hot wheels team transport",
        "hot wheels boulevard", "hot wheels fast furious", "hot wheels exotics",
        "hot wheels silver series", "hot wheels legends", "hot wheels mainline",
        "hot wheels 5 pack", "hot wheels collector", "hot wheels track",
        "hot wheels porsche", "hot wheels ferrari", "hot wheels nissan",
        "hot wheels toyota", "hot wheels audi", "hot wheels lamborghini",
        "hot wheels bmw", "hot wheels honda", "hot wheels ford", "hot wheels chevy",
        "hot wheels mazda", "hot wheels subaru", "hot wheels datsun",
        "hot wheels skyline", "hot wheels mustang", "hot wheels corvette",
        "hot wheels batman", "hot wheels mario", "hot wheels marvel",
        "hot wheels tooned", "hot wheels rod", "hot wheels drift")]
)

# How many rotating URLs to fetch per run (core pages are always fetched too).
FC_ROTATE_PER_RUN = int(os.getenv("FC_ROTATE_PER_RUN", "18"))
_FC_NEXT_OFFSET = [0]      # advanced each run, persisted in seen.json
_FC_SITE_COUNT = [0]       # "(380 Items)" as reported by FirstCry itself

# env override ("|" separated, because FirstCry paths contain commas) pins an
# explicit list and disables rotation.
_FC_ENV_URLS = [u.strip() for u in os.getenv("FC_LISTING_URLS", "").split("|") if u.strip()]

FC_EXCLUDE = [w.strip().lower() for w in
              os.getenv("FC_EXCLUDE",
                        "monster truck,monster jam,monstred,hopper ball,"
                        "track set,trackset,track and,track with,track builder,"
                        "track creator,playset,play set,race off,raceway,speedway,"
                        "garage,car wash,loop dash,loop track,launch & loop,launcher,"
                        "stunt track,hot wheels city,ultimate garage,super loop,"
                        "pit stop,action set,crash & track,ultimate,"
                        # Hot Wheels-branded merchandise that isn't a car
                        "water bottle,sipper,canteen,sunglass,digital watch,wrist watch,t-shirt,tshirt,sweatshirt,sandwich box,lunch box,tiffin,play ball,school bag,backpack,umbrella,raincoat,socks,slippers,sandals,shoes,bicycle")
              .split(",") if w.strip()]
# v17.3: the monster-truck words in FC_EXCLUDE make monster trucks a chase-only
# line (chase_line): a monster-truck Treasure Hunt / chase gets through, any
# other monster truck stays out — however the store spells it ("Monster Toy
# Truck", "MONST ER TRUCKS" and "-Onster Trucks" all slipped past the words:
# 4 regular monster trucks alerted on 24 Oct alone). CHASE_ONLY_LINES=false
# puts everything back as it was in v17.2.
CHASE_ONLY_LINES = os.getenv("CHASE_ONLY_LINES", "true").lower() == "true"
_FC_MT_EXCLUDED = any(re.search(r"monst", k) for k in FC_EXCLUDE)
_FC_EXCLUDE_HARD = ([k for k in FC_EXCLUDE if not re.search(r"monst", k)] if CHASE_ONLY_LINES
                    else list(FC_EXCLUDE))

# Always-track product ids (e.g. your FirstCry Shortlist). Paste ids or full
# product URLs, comma separated — these stay in the catalog permanently and are
# flagged 🎯 in alerts so a restock on your wishlist is unmissable.
_FC_WATCH_RAW = os.getenv("FC_WATCH", "")
# ── Auto-watch by marque ──────────────────────────────────────────────────────
# Any Hot Wheels whose name matches one of these is automatically added to the
# priority watch — checked EVERY run via FirstCry's search, the same as a
# hand-picked FC_WATCH entry. This is what removes the manual step: you never
# have to paste a link for a sold-out car you care about; if it's a Porsche,
# Ferrari, Lambo, Supra (etc.) the bot starts guarding it the moment it first
# sees it, and pings you the instant it returns.
FC_MARQUES = [w.strip().lower() for w in os.getenv("FC_MARQUES", ",".join([
    # the ones you named
    "porsche", "ferrari", "lamborghini", "supra",
    # JDM icons
    "skyline", "gt-r", "gtr", "nissan", "datsun", "rx-7", "rx7", "mazda",
    "civic", "type r", "nsx", "honda", "toyota", "ae86", "silvia", "180sx",
    "evo", "lancer", "subaru", "wrx", "impreza", "celica", "mr2",
    # euro / exotic
    "bmw", "m3", "m4", "audi", "rs6", "rs 6", "mercedes", "amg", "bugatti",
    "mclaren", "aston martin", "koenigsegg", "pagani", "alfa romeo",
    "countach", "aventador", "huracan", "diablo", "testarossa", "f40", "f50",
    "911", "930", "934", "935", "993", "959", "carrera", "singer",
    # american muscle
    "mustang", "corvette", "camaro", "challenger", "charger", "plymouth",
    # collector lines worth guarding regardless of marque
    "premium", "car culture", "team transport", "boulevard", "rlc",
    "treasure hunt", "silver series", "fast furious", "fast & furious",
    "exotics", "legends", "silhouettes", "japan historics", "modern classics",
])).split(",") if w.strip()]

# Hard cap on per-run priority checks (each costs 1-3 requests). Out-of-stock
# items are checked first, because in-stock ones are already visible on listings.
FC_WATCH_MAX = int(os.getenv("FC_WATCH_MAX", "25"))

# Hours a car can go unseen on every listing window before we treat it as sold
# out. 3h ≈ 7 full sweeps of the 78-window rotation at a 5-minute cadence, so an
# in-stock car almost always reappears well within it.
FC_STALE_H = float(os.getenv("FC_STALE_H", "3"))


def _fc_is_marque(name: str) -> bool:
    n = " " + re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()) + " "
    if any(k in n for k in FC_MARQUES):
        return True
    # v17.4: …or its series in the case checklist is one of them — the Dino
    # 206 GT is in the 2026 "Ferrari" series, though its name never says Ferrari
    # (25 Oct it went out as a plain alert, 4 min after a deals channel had it)
    s = _hw_series_text(name)
    return bool(s) and any(k in s for k in FC_MARQUES)


def _hw_series_text(name: str) -> str:
    """The car's series from the case checklist (" ferrari "), or ""."""
    info = hw_info(name) if name else None
    ser = (info or {}).get("ser") or ""
    if not ser or ser.upper() == "TBD":
        return ""
    return " " + re.sub(r"[^a-z0-9 ]", " ", ser.lower()) + " "


# ── Hot Wheels cases, Treasure Hunts, Super Treasure Hunts (v16) ─────────────
# hw_cases.json is rebuilt once a day by cases.py (its own workflow) from the
# collector checklists on 164custom.com: every mainline case (A, B, C … Q) of
# the last two years, this year and next, with each year's Treasure Hunts and
# Super Treasure Hunts. The tracker only reads that file — not one extra
# request to any store. A store's car is matched by its number ("229/250"),
# name and colour; when the match isn't certain, nothing is claimed.
HW_CASES_FILE = os.getenv("HW_CASES_FILE", "hw_cases.json")
_HW = {"cars": None}
# words in store names that say nothing about which car it is
_HW_FILL = set("""hot wheels wheel hotwheels hw die cast diecast cat free toy toys car cars vehicle
vehicles for kids kid boys girls boy girl age ages years year yrs collectible collectibles
collector collectors collection scale model models the with and of a an mainline basic
basics single personnalise equipe fourgonnette voiture multicolor multicolour assorted
original authentic mattel genuine pc piece pcs 64""".split())
_HW_COLOUR_FILL = set("""metalflake spectraflame satin matte flat pearl pearlescent met metallic candy
translucent chrome dark light bright deep pale t""".split())
_HW_COLOUR_SYN = {"golden": "gold", "navy": "blue", "royal": "", "sky": "", "maroon": "red",
                  "burgundy": "red", "crimson": "red", "wine": "red", "lime": "green",
                  "olive": "green", "pista": "green", "mint": "green", "turquoise": "teal",
                  "aqua": "teal", "cyan": "teal", "beige": "cream", "ivory": "cream", "tan": "brown",
                  "bronze": "brown", "magenta": "pink", "violet": "purple", "lavender": "purple",
                  "silvery": "silver", "multicolor": "", "multicolour": ""}
_HW_NOT_SINGLE = re.compile(
    r"\b(premium|car culture|boulevard|team transport|rlc|red line club|silver series|pop culture|"
    r"elite ?64|\d+[- ]?pack|pack of|set of|multi ?pack|gift ?pack|box ?set|bundle|playset|"
    r"play set|launcher|monster|matchbox|match box|mbx|majorette|mini ?gt|kaido)\b", re.I)
_HW_STH_WORDS = re.compile(r"\b(sth|super\s*treasure\s*hunts?|super\s*th|\$th)\b", re.I)
_HW_TH_WORDS = re.compile(r"\b(treasure\s*hunts?|t[\s-]?hunt|th)\b", re.I)
_HW_CHASE_WORDS = re.compile(r"\bchase\b", re.I)          # not "High Tail Chaser"
# v17.3: Matchbox's rarest pieces are "Super Chases"
_HW_SCHASE_WORDS = re.compile(r"\bsuper\s*-?\s*chase\b", re.I)
# …but "chase" in a toy's TITLE isn't a chase piece: Hot Wheels Monster Trucks
# "Charge & Chase Challenge", a "Police Chase" set — nor is a "Chance of Chase"
# (Minifygram's badge for a box that might hold one)
_CHASE_TITLE = re.compile(
    r"\bchances?\s+(?:of|for|at)\s+(?:an?\s+)?chase\b"
    r"|\bcharge\s*(?:&|and|n)\s*chase\b"
    r"|\b(?:police|cop|dino|raptor|rescue)\s+chase\b|\bhigh[\s-]*speed\s+chase\b"
    r"|\bchase\s*(?:challenge|playset|play\s*set|set|track|game|launcher|down|pack\s+of)\b"
    r"|\bchase\s*(?:&|and)\s+\w", re.I)
_HW_ZAMAC_WORDS = re.compile(r"\bzamac\b", re.I)

# ── v17.3: chase pieces of lines you don't otherwise track ──────────────────
# Matchbox and Majorette (and Hot Wheels Monster Trucks, which FC_EXCLUDE keeps
# out) are tracked for their chase pieces only — a Super Chase, a chase car, a
# Treasure Hunt — wherever a store names it so: Karz & Dolls' chase shelf and
# names ("… CHASE"), Minifygram's badges ("Treasure Hunt") and names. Every
# other Matchbox / Majorette / monster truck stays out, as before. (FirstCry and
# Hamleys sell them as ordinary cars or assortments: nothing there says which
# one is the chase — no name, no model number — so they can't be told apart.)
_LINE_RES = (
    ("MATCHBOX", re.compile(r"\bmatch\s*-?\s*box\b|\bmbx\b", re.I)),
    ("MAJORETTE", re.compile(r"\bmajorette\b", re.I)),
    # FirstCry writes these every which way: "Monster Trucks", "Monster Toy
    # Truck", "MONST ER TRUCKS", "Drag Busm -Onster Trucks"; Hamleys "monster-truck"
    ("MONSTER TRUCKS", re.compile(r"onst[\s\-_]*er[\s\-_]*(?:toy[\s\-_]*)?trucks?|\bmonster[\s\-_]*jam\b|"
                                  r"\bmonstred\b", re.I)),
)
# A chase-only line's piece must say it plainly: "Super Chase", "Chase Car",
# "(Chase)", a name ending in "CHASE", our own "[CHASE]" tag, "Treasure Hunt",
# "STH", "(TH)" or a name ending in "TH" — never a "TH" elsewhere (Trends
# Hobby's "TH Porsche 911", model codes).
_CHASE_STRICT = re.compile(
    r"\bsuper\s*-?\s*chase\b|\bchase\s*(?:car|edition|version|variant|piece|model|unit)s?\b|"
    r"[\[(]\s*chase\s*[\])]|\bchase\s*[\]).!*]*\s*$|^\W*chase\b|"
    r"\b(?:matchbox|mbx|majorette|hot\s*wheels|mini\s*gt|kaido(?:\s*house)?)\s+chase\b", re.I)
_TH_STRICT = re.compile(r"\b(?:super\s*)?treasure\s*hunts?\b|\bt-hunt\b|\bsth\b|\$th\b|\bsuper\s*th\b|"
                        r"[\[(]\s*th\s*[\])]|\bth\s*[\]).!*]*\s*$", re.I)
_CHASE_RANK = {"sth": 4, "schase": 3, "th": 2, "chase": 1}


def chase_line(name: str):
    """'MATCHBOX', 'MAJORETTE' or 'MONSTER TRUCKS' — a line tracked for its
    chase pieces only — or None. Monster trucks count only while FC_EXCLUDE
    keeps them out (remove "monster truck" there to track all of them)."""
    if not name:
        return None
    for label, rx in _LINE_RES:
        if rx.search(name):
            if label == "MONSTER TRUCKS" and not _FC_MT_EXCLUDED:
                return None
            return label
    return None


def chase_kind(text: str):
    """'sth', 'schase', 'th' or 'chase' when the words plainly name a chase
    piece (strict — see _CHASE_STRICT), else None."""
    t = text or ""
    if not t or _CHASE_TITLE.search(t):
        return None
    if _HW_STH_WORDS.search(t):
        return "sth"
    if _HW_SCHASE_WORDS.search(t):
        return "schase"
    if _TH_STRICT.search(t):
        return "th"
    if _CHASE_STRICT.search(t):
        return "chase"
    return None


def chase_tag(text: str, name: str) -> str:
    """The marker to add to a product's name when the store says it's a chase
    somewhere else (its SKU line, a badge, its shelf): " [SUPER CHASE]" … — or
    "" when the name already says as much. The name is what every check reads."""
    k = chase_kind(text)
    if not k or _CHASE_RANK.get(chase_kind(name), 0) >= _CHASE_RANK[k]:
        return ""
    return " " + _CHASE_TAGS[k]


_CHASE_TAGS = {"sth": "[SUPER TREASURE HUNT]", "schase": "[SUPER CHASE]",
               "th": "[TREASURE HUNT]", "chase": "[CHASE]"}


def _hw_tokens(s: str) -> list:
    s = (s or "").lower().replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")
    s = re.sub(r"\d{1,3}\s*[/-]\s*250\b", " ", s)       # the collector number
    s = re.sub(r"\b(?:19|20)(\d\d)\b", r"\1", s)         # 1970 -> 70, 2019 -> 19
    s = re.sub(r"'(\d\d)\b", r"\1", s)                    # '66 -> 66
    s = s.replace("grey", "gray")
    out = []
    for t in re.sub(r"[^a-z0-9.]+", " ", s).split():
        t = t.strip(".")
        if t and t not in _HW_FILL:
            out.append(t)
    return out


def _hw_colour(s: str) -> set:
    out = set()
    for w in _hw_tokens((s or "").replace("/", " ").replace("&", " ")):
        w = _HW_COLOUR_SYN.get(w, w)
        if w and w not in _HW_COLOUR_FILL and len(w) > 1 and not w.isdigit():
            out.add(w)
    return out


# colours stores and checklists name differently (FirstCry's "Grey" is often
# the checklist's "Silver"): half a match, enough to break a tie
_HW_NEAR = {frozenset(p) for p in (("gray", "silver"), ("cream", "white"), ("champagne", "gold"),
                                   ("champagne", "silver"), ("teal", "blue"), ("teal", "green"),
                                   ("copper", "brown"), ("copper", "orange"), ("gold", "yellow"))}


def _hw_colour_fit(store: set, table: set) -> float:
    if not store:
        return 0.0
    exact = len(store & table)
    near = sum(1 for a in store - table if any(frozenset((a, b)) in _HW_NEAR for b in table))
    return (exact + 0.5 * near) / len(store)


def _hw_load():
    """The case table, indexed by word and by number (once per run)."""
    if _HW["cars"] is not None:
        return _HW
    cars = []
    try:
        if os.path.exists(HW_CASES_FILE):
            with open(HW_CASES_FILE, encoding="utf-8") as f:
                cars = json.load(f).get("cars") or []
    except Exception as exc:
        print(f"[HW] case table unreadable ({exc}) — alerts go out without case info")
        cars = []
    by_tok, by_n, sth = {}, {}, {}
    for i, e in enumerate(cars):
        e["_t"] = _hw_tokens(e.get("name", ""))
        e["_j"] = "".join(e["_t"])
        e["_col"] = _hw_colour(e.get("col", ""))
        for t in set(e["_t"]):
            if len(t) >= 3 and not re.fullmatch(r"\d\d", t):
                by_tok.setdefault(t, []).append(i)
        if e.get("n"):
            by_n.setdefault(e["n"], []).append(i)
        if e.get("sth"):
            sth[(e.get("y"), e.get("c"), e.get("n"))] = e.get("col", "")
    _HW.update(cars=cars, by_tok=by_tok, by_n=by_n, sth=sth)
    if cars:
        print(f"[HW] case table: {len(cars)} cars "
              f"({len({(e.get('y'), e.get('c')) for e in cars})} cases)")
    return _HW


def _hw_tok_eq(a: str, b: str) -> bool:
    """Same word, allowing a store's typo ("Toyoto") — but never "Super" for
    "Supra", and a word with digits (928, EB110, 2.7) only exactly."""
    if a == b:
        return True
    if len(a) < 5 or len(b) < 5 or re.search(r"\d", a + b):
        return False
    return (a.startswith(b) or b.startswith(a)
            or difflib.SequenceMatcher(None, a, b).ratio() >= 0.85)


def _hw_score(S: list, T: list) -> float:
    """How well a store name (words S) names the checklist car (words T), 0-1.
    The table's model year is optional when the store gives none."""
    yr = lambda t: re.fullmatch(r"\d\d", t)
    has_year = any(yr(t) for t in S)
    T2 = [t for t in T if has_year or not yr(t)]
    if not T2 or not S:
        return 0.0
    # model numbers must agree: a Porsche 914 is not a 928, a '94 Supra not a '20
    dT = {t for t in T2 if re.search(r"\d", t)}
    dS = {t for t in S if re.search(r"\d", t) and not (yr(t) and not any(yr(x) for x in T2))}
    if dT != dS and not ("".join(S) == "".join(T2)):
        return 0.0
    mT = sum(1 for t in T2 if any(_hw_tok_eq(t, x) for x in S))
    mS = sum(1 for x in S if any(_hw_tok_eq(x, t) for t in T2))
    r, p = mT / len(T2), mS / len(S)
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    # words split or joined differently ("Road Runner" / "Roadrunner") — only
    # when the letters are practically the same
    joined = difflib.SequenceMatcher(None, "".join(S), "".join(T2)).ratio()
    return max(f1, joined if joined >= 0.93 else 0.0)


@functools.lru_cache(maxsize=16384)
def hw_info(name: str):
    """Which case a store's car comes from: {"y", "c", "n", "ser", "th", "sth",
    "sth_col"} — or None when it isn't a mainline single or the match isn't
    certain (two cases fit equally, or the number points elsewhere)."""
    T = _hw_load()
    if not T["cars"] or not name or _HW_NOT_SINGLE.search(name):
        return None
    raw = re.sub(r"\[[^\]]*\]", " ", name)               # [PRE-ORDER]
    colour = set()
    # FirstCry ends a name with its colour: "… Toy Car - Grey", "… Toy Car- Silver"
    parts = re.split(r"\s+-\s*|\s*-\s+", raw)
    if len(parts) > 1 and len(parts[-1].split()) <= 4:
        raw = " ".join(parts[:-1])
        colour = _hw_colour(parts[-1])
    m = re.search(r"\b(\d{1,3})\s*[/-]\s*250\b", raw)
    num = int(m.group(1)) if m else None
    S = _hw_tokens(raw)
    if not S:
        return None
    if num:
        idx = set(T["by_n"].get(num, []))
        if not idx:
            return None                                   # a number we don't have
        need = 0.75
    else:
        if not colour:
            return None           # no number, no colour: too little to be sure
        idx = set()
        for t in S:
            idx.update(T["by_tok"].get(t, []))
        need = 0.82
    sth_words = bool(_HW_STH_WORDS.search(name)) or "spectraflame" in name.lower()
    scored, supers = [], []
    for i in idx:
        e = T["cars"][i]
        sc = _hw_score(S, e["_t"])
        if sc < need:
            continue
        if e.get("sth") and not sth_words:
            supers.append((sc, e))    # stores list the regular car; a Super is never assumed
            continue
        scored.append((sc, e))
    if not scored and supers and num and not sth_words:
        # the checklist has only the Super for this number (2026 P #245 '70
        # Plymouth AAR Cuda: Spectraflame Gold, no yellow regular row): the
        # store's car is the regular one, and its Super is in that case
        cases = {(e.get("y"), e.get("c")) for _, e in supers}
        if len(cases) == 1:
            e = max(supers, key=lambda x: x[0])[1]
            return {"y": e.get("y"), "c": e.get("c"), "n": e.get("n"), "ser": e.get("ser") or "",
                    "th": False, "sth": False, "sth_col": e.get("col", "")}
    if not scored:
        return None
    best = max(sc for sc, _ in scored)
    top = [e for sc, e in scored if sc >= best - 0.04]
    if colour:
        cs = [(_hw_colour_fit(colour, e["_col"]), e) for e in top]
        bc = max(c for c, _ in cs)
        if bc > 0:
            top = [e for c, e in cs if c >= bc - 1e-9]
        elif not num:
            return None           # name alone, in a colour none of them comes in
    if sth_words and any(e.get("sth") for e in top):
        top = [e for e in top if e.get("sth")]
    if len({(e.get("y"), e.get("c")) for e in top}) != 1:
        return None                                       # two cases fit: say nothing
    e = top[0]
    return {"y": e.get("y"), "c": e.get("c"), "n": e.get("n"), "ser": e.get("ser") or "",
            "th": all(x.get("th") for x in top), "sth": all(x.get("sth") for x in top),
            "sth_col": None if any(x.get("sth") for x in top) else
            T["sth"].get((e.get("y"), e.get("c"), e.get("n")))}


@functools.lru_cache(maxsize=16384)
def hw_priority(name: str):
    """'sth', 'schase' (a Super Chase, v17.3), 'th', 'chase', 'sth_car' (the
    regular car whose Super TH is in its case — FirstCry doesn't sort them out)
    or 'zamac' — what makes this car one to chase above your marques. None for
    an ordinary car."""
    if not name:
        return None
    info = hw_info(name)
    if _HW_STH_WORDS.search(name) or (info and info.get("sth")):
        return "sth"
    if _HW_SCHASE_WORDS.search(name) and not _CHASE_TITLE.search(name):
        return "schase"
    if (info and info.get("th")) or _HW_TH_WORDS.search(name):
        return "th"
    if _HW_CHASE_WORDS.search(name) and not _CHASE_TITLE.search(name):
        return "chase"
    if info and info.get("sth_col"):
        return "sth_car"
    if _HW_ZAMAC_WORDS.search(name):
        return "zamac"
    return None


FC_WATCH_IDS = set(re.findall(r"\d{5,}", _FC_WATCH_RAW))
# keep the full URL per id so a search phrase can be derived from its slug
FC_WATCH_URLS = {m.group(1): m.group(0) for m in re.finditer(
    r"https://www\.firstcry\.com/[^\s,]*?/(\d{5,})/product-detail[^\s,]*", _FC_WATCH_RAW)}

# Card anchor of truth: the card image filename carries the product id and its
# title= carries the clean name, so id↔name can never be mismatched, and size
# variant links (which have no image) stay out of the parse entirely.
_FC_IMG = re.compile(
    r'<img[^>]+products/\d+x\d+/(\d{5,})[a-z]?\.jpg[^>]*?title="([^"]{6,250})"', re.I)
_FC_IMG_ALT = re.compile(
    r'<img[^>]+title="([^"]{6,250})"[^>]+products/\d+x\d+/(\d{5,})[a-z]?\.jpg', re.I)
_FC_FOOTER_LINK = re.compile(
    r'href="https://www\.firstcry\.com/hot-wheels/[^"]*?/(\d{5,})/product-detail[^"]*"'
    r'[^>]*title="([^"]{6,250})"', re.I)


# Shared HTML helpers (used by the FirstCry, Hamleys and Karz&Dolls parsers).
_TAG = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return html.unescape(_TAG.sub(" ", s)).replace("\xa0", " ").strip()


# Exclusion keywords are matched on WORD BOUNDARIES, not raw substrings.
# Substring matching silently ate legitimate products: "play set" matched
# "Dis-play set-s" and killed the Premium Collector Display Set.
# LEADING word boundary only: a trailing \b would break plurals
# ("monster truck" must still match "Monster Trucks"), while the leading \b is
# what stops "play set" matching "dis-play set-s".
_FC_EXCL_RE = re.compile(
    "|".join(r"\b" + re.escape(k) for k in _FC_EXCLUDE_HARD), re.I
) if _FC_EXCLUDE_HARD else None



# ── Cache busting ──────────────────────────────────────────────────────────────
# FirstCry serves listing/search pages through a CDN. A cached snapshot can show
# ADD TO CART for a car that sold out minutes ago — which produces a "BACK IN
# STOCK" alert for something already gone. Every FirstCry request therefore
# carries a unique cache-buster and no-cache headers so we read live state.
_FC_NOCACHE = {"Cache-Control": "no-cache, no-store, max-age=0",
               "Pragma": "no-cache"}


def _fc_bust(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}_={int(time.time() * 1000)}"


def _fc_excluded(name: str) -> bool:
    """Out of tracking on every store: a big set or merchandise (FC_EXCLUDE), or
    a Matchbox / Majorette / monster truck that isn't a chase piece (v17.3)."""
    n = name or ""
    if _FC_EXCL_RE and _FC_EXCL_RE.search(n):
        return True
    return bool(CHASE_ONLY_LINES and chase_line(n) and not chase_kind(n))


def _fc_name(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()[:180]


def _fc_real_url(region: str, pid: str) -> str:
    """Canonical product URL taken from the card itself (not synthesised)."""
    for m in re.finditer(
            r'''(?:href=["'])?((?:https://www\.firstcry\.com)?/[^\s"'<>]*?/'''
            + pid + r'''/product-detail)''', region, re.I):
        u = html.unescape(m.group(1))
        u = re.sub(r"^/+(?=www\.firstcry\.com)", "", u)
        if u.startswith("www."):
            u = "https://" + u
        elif u.startswith("/"):
            u = "https://www.firstcry.com" + u
        u = re.sub(r"(https://www\.firstcry\.com)/+(?:www\.)?firstcry\.com", r"\1", u)
        if "/product-detail" in u:
            u = u.split("?")[0]
            # encode stray characters so Telegram links stay clickable
            return quote(u, safe=":/-_.~")
    return f"https://www.firstcry.com/x/x/{pid}/product-detail"


def _fc_card_stock_price(region: str, name: str = "") -> tuple:
    """Price / MRP / stock for one card. Name is passed in so its own numbers
    (collector numbers, model years) can be removed before parsing prices."""
    price_region = region
    cut = re.search(r"Sizes?\s*:", region, re.I)
    if cut:
        price_region = region[:cut.start()]
    txt = _clean(price_region)

    # ── strip everything that is NOT a price ──────────────────────────────────
    if name:
        for variant in {name, html.escape(name), name.replace("&", "&amp;")}:
            if variant:
                txt = txt.replace(variant, " ")
    txt = re.sub(r"\(\s*\d{1,3}\s*/\s*\d{1,4}\s*\)", " ", txt)       # (117/250)
    txt = re.sub(r"\b\d{1,3}\s*/\s*\d{1,4}\b", " ", txt)             # 117/250
    txt = re.sub(r"\b(?:19|20)\d{2}\b", " ", txt)                    # model years
    txt = re.sub(r"Buy\s*&?\s*Earn\s*Club\s*Cash.*?(?:required\.?\)?|plan\.)",
                 " ", txt, flags=re.I | re.S)                        # club blurb
    txt = re.sub(r"Min\.?\s*[\d,]+\s*/-", " ", txt, flags=re.I)      # "Min. 100/-"
    txt = re.sub(r"Club\s*(?:Price|Cash)[^\d]{0,25}[\d,.]+", " ", txt, flags=re.I)
    txt = re.sub(r"\(\s*[\d,]+\s*Ratings?\s*\)", " ", txt, flags=re.I)
    txt = re.sub(r"\d+\s*%\s*Off", " ", txt, flags=re.I)
    txt = re.sub(r"\b\d+\s*(?:Years?|Yrs?|Months?|cm|mm|pcs?|pack|X)\b", " ", txt, flags=re.I)
    txt = re.sub(r"\b\d{5,}\b", " ", txt)

    # ₹-prefixed amounts are authoritative; bare numbers only as a fallback
    nums = [price_to_int(x) for x in re.findall(r"₹\s*([\d,]+(?:\.\d+)?)", txt)]
    nums = [n for n in nums if n and 30 <= n <= 60000]
    if not nums:
        nums = [price_to_int(x) for x in
                re.findall(r"\b(\d{2,5}(?:\.\d{1,2})?)\b", txt)]
        nums = [n for n in nums if n and 30 <= n <= 60000]

    price = min(nums) if nums else None
    mrp = max(nums) if nums else None
    # an MRP must be above the price but not absurdly so (guards leftovers)
    if mrp and price and not (price < mrp <= price * 4):
        mrp = None

    up = region.upper()
    if "ADD TO CART" in up or "ADD TO BAG" in up:
        stock = "in_stock"
    elif "NOTIFY ME" in up or "OUT OF STOCK" in up or "SOLD OUT" in up:
        stock = "out_of_stock"
    else:
        stock = None
    return price, mrp, stock


# ── Watchlist: per-product stock via FirstCry's own search ─────────────────────
# WHY THIS EXISTS
# FirstCry product pages are JS-rendered: fetching a live product page returns
# NO price and NO Add-to-Cart/Notify-Me anywhere in the HTML (verified on
# /21161951/product-detail, a live Premium Fast & Furious listing). So a product
# is only observable to us when it appears on a *listing* page — and a sold-out
# premium car usually doesn't appear on any of the category slices at all.
# That's how a wishlist item can restock without us ever seeing it.
#
# The fix: FirstCry's SEARCH results ARE server-rendered cards, complete with
# price and the ADD TO CART / Notify Me state. So for each watched product we
# search for its own name and read the card whose id matches. That gives an
# exact, per-product stock check for the things you actually care about,
# independent of whether they surface in any category listing.
# Generic words that appear in almost every Hot Wheels name. Searching with
# them buries the actual model, which is why the first version of this only
# resolved 3 of 25 watched products: a 9-word query like "hot wheels die cast
# free wheel toy car 1995" matches everything and pins nothing.
_FC_STOPWORDS = {
    "hot", "wheels", "hotwheels", "die", "cast", "diecast", "die-cast", "free",
    "wheel", "toy", "toys", "car", "cars", "vehicle", "vehicles", "model",
    "models", "with", "smooth", "rolling", "pack", "of", "scale", "164",
    "multicolor", "multicolour", "color", "colour", "colours", "the", "and",
    "for", "adult", "adults", "collectors", "collector", "kids", "years",
    "year", "new", "edition", "pcs", "piece", "pieces", "a", "an", "in", "to",
}


def _fc_distinctive(name: str) -> list:
    """The words that actually identify the model (marque, model, variant)."""
    words = re.sub(r"[^A-Za-z0-9 ]", " ", name or "").split()
    out = []
    for w in words:
        lw = w.lower()
        if lw in _FC_STOPWORDS:
            continue
        if lw.isdigit() and len(lw) != 4:      # keep years, drop 1/64, 250 etc.
            continue
        out.append(w)
    return out


def _fc_watch_terms(pid: str, prev_fc: dict) -> list:
    """Search phrases for a watched product, most specific first."""
    row = prev_fc.get(pid, {})
    name = (row.get("name") or "").strip()
    if not name:
        url = row.get("url") or FC_WATCH_URLS.get(pid, "")
        m = re.search(r"firstcry\.com/[^/]+/([^/]+)/\d{5,}/product-detail", url)
        if m:
            name = m.group(1).replace("-", " ")
    if not name:
        return []

    key = _fc_distinctive(name)
    terms = []
    if key:
        # "hot wheels <model>" is what a person would actually type
        terms.append("hot wheels " + " ".join(key[:3]))
        if len(key) > 2:
            terms.append("hot wheels " + " ".join(key[:2]))
        terms.append(" ".join(key[:4]))
    # last resort: the older whole-name prefix
    words = re.sub(r"[^A-Za-z0-9 ]", " ", name).split()
    if words:
        terms.append(" ".join(words[:6]))
    seen, out = set(), []
    for t in terms:
        t = re.sub(r"\s+", " ", t).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:4]


def fc_check_watched(prev_fc: dict, ids=None) -> dict:
    """Return {pid: {name, price, mrp, stock, url}} for watched products."""
    ids = FC_WATCH_IDS if ids is None else set(ids)
    if not ids:
        return {}
    found = {}

    def one(pid):
        for term in _fc_watch_terms(pid, prev_fc):
            url = _FC_SEARCH + quote(term)
            try:
                r = http.get(_fc_bust(url), headers={**COMMON_HEADERS, **_FC_NOCACHE},
                             timeout=TIMEOUT, **_IMPERSONATE)
            except Exception:
                continue
            if r.status_code != 200 or len(r.text) < 5000:
                continue
            page = r.text
            marks = [(m.start(), m.group(1), _fc_name(m.group(2)))
                     for m in _FC_IMG.finditer(page)]
            marks += [(m.start(), m.group(2), _fc_name(m.group(1)))
                      for m in _FC_IMG_ALT.finditer(page)]
            marks.sort()
            for i, (pos, found_pid, nm) in enumerate(marks):
                if found_pid != pid:
                    continue
                end = marks[i + 1][0] if i + 1 < len(marks) else min(len(page), pos + 6000)
                region = page[pos:end]
                price, mrp, stock = _fc_card_stock_price(region, nm)
                if stock is None:
                    continue
                return {"name": nm, "price": price, "mrp": mrp, "stock": stock,
                        "url": _fc_real_url(page[max(0, pos - 2500):end], pid)}
            time.sleep(0.3)
        return None

    with ThreadPoolExecutor(max_workers=min(FC_WORKERS, 6)) as ex:
        futs = {ex.submit(one, p): p for p in ids}
        for fut in as_completed(futs):
            pid = futs[fut]
            try:
                info = fut.result()
            except Exception:
                info = None
            if info:
                found[pid] = info
    if ids:
        hit = sum(1 for p in ids if p in found)
        ins = sum(1 for p in found.values() if p["stock"] == "in_stock")
        print(f"  [FC] priority check: resolved {hit}/{len(ids)} ({ins} in stock)")
    return found



def fc_confirm_restocks(changes: dict, current: dict) -> int:
    """Re-verify FirstCry restocks against a FRESH request before alerting.

    A restock alert is the one that makes you drop everything, so a false
    positive is expensive. Between our listing read and the alert, the car may
    already be gone — or the page we read may have been a CDN snapshot. Here we
    re-check each FirstCry restock candidate individually (cache-busted) and
    drop any that no longer confirms as in stock, reverting its stored state so
    a genuine restock can still fire later.
    Returns how many were suppressed.
    """
    # API-sourced stock is authoritative and fetched fresh, so only restocks read
    # from HTML listings need a second look.
    cands = [d for d in changes.get("restocks", [])
             if d["source"] == "firstcry" and not str(d.get("stock_ver", "")).startswith("fc_api")]
    if not cands:
        return 0
    prev_fc = {}
    ids = [d["id"][3:] for d in cands]
    for d in cands:
        prev_fc[d["id"][3:]] = {"name": d["name"], "url": d.get("url", "")}
    fresh = fc_check_watched(prev_fc, ids)

    kept, dropped = [], 0
    for d in changes["restocks"]:
        if d["source"] != "firstcry" or str(d.get("stock_ver", "")).startswith("fc_api"):
            kept.append(d)
            continue
        pid = d["id"][3:]
        info = fresh.get(pid)
        if info and info["stock"] == "in_stock":
            kept.append(d)
        elif info:
            # confirmed gone again — revert so the next real restock still alerts
            dropped += 1
            if d["id"] in current:
                current[d["id"]]["stock"] = "out_of_stock"
            print(f"  [FC] restock NOT confirmed (sold out again): {d['name'][:52]}")
        else:
            # couldn't verify — send it rather than risk missing a real drop
            kept.append(d)
            print(f"  [FC] restock unverified, alerting anyway: {d['name'][:52]}")
    changes["restocks"] = kept
    return dropped


# ══════════════════════════════════════════════════════════════════════════════════
# FirstCry — INTERNAL JSON API (the same call the site's "Show More" button makes)
# ══════════════════════════════════════════════════════════════════════════════════
# Discovered from a HAR capture of hotwheels/5/0/113: every "Show More Products"
# click calls
#     /svcs/SearchResult.svc/GetSearchResultProductsPaging?PageNo=N&PageSize=20
#         &MasterBrand=113 (Hot Wheels) ... 59 params in total
# with only anonymous session cookies — no login. Paging through it returns the
# WHOLE catalogue, sold-out items included, as JSON. That replaces the entire
# HTML-window rotation: one short loop of requests gives every product with its
# real stock, instead of 24 page loads that each see ~20 of ~430 products.
#
# FirstCry's internal product records carry an exact unit count
# ("stock": {"current": 82} / "CurrentStock": 530 — both seen in real captures),
# so beyond in/out we can warn when a car is nearly gone.
#
# The response body wasn't saved in the capture (the page navigated away), so
# the parser below is deliberately tolerant of FirstCry's known field-name
# variants, and it prints the detected schema on the first page of every run so
# the log confirms exactly what it read. If the API ever fails, scrape_firstcry
# falls back to the proven HTML path automatically.
FC_USE_API      = os.getenv("FC_USE_API", "true").lower() == "true"
FC_API_URL      = "https://www.firstcry.com/svcs/SearchResult.svc/GetSearchResultProductsPaging"
FC_API_BRAND    = os.getenv("FC_API_BRAND", "113")          # Hot Wheels master brand
FC_API_PAGESIZE = int(os.getenv("FC_API_PAGESIZE", "20"))   # FirstCry caps pages at 20 anyway
FC_API_TIMEOUT  = int(os.getenv("FC_API_TIMEOUT", "15"))   # per JSON request; retried on timeout
FC_API_PARALLEL = max(1, int(os.getenv("FC_API_PARALLEL", "5")))  # pages fetched at once
FC_API_MAXPAGES = int(os.getenv("FC_API_MAXPAGES", "40"))
FC_LOW_STOCK    = int(os.getenv("FC_LOW_STOCK", "5"))       # "only N left" threshold

# Your delivery pincode. The site's own call sent pcode=0 (no location), which
# makes FirstCry report stock across ALL its warehouses nationwide — so a single
# unit in a distant warehouse looked "in stock" to the bot but was "not
# deliverable" to you. With your pincode, stock reflects what can reach you.
# If FirstCry rejects the pincode request, the bot falls back to pcode=0.
FC_PINCODE = os.getenv("FC_PINCODE", "248001").strip() or "0"
_FC_PCODE_ACTIVE = [FC_PINCODE]

# Minimum units for a car to count as "in stock" for alerting. A single unit is
# almost always gone by the time you tap the link, so by default 1 unit is
# treated as sold out — and when FirstCry actually restocks it (2+ units), you
# get the alert then. Set to 1 to be alerted even for last-unit cars.
FC_MIN_ALERT_STOCK = max(1, int(os.getenv("FC_MIN_ALERT_STOCK", "2")))
# v15.1: your 🎯 cars (hand-picked, marques, watchlist) alert from this many —
# one unit that can reach you is worth a try for those (Club: no delivery fee
# on a single order). Other cars keep FC_MIN_ALERT_STOCK.
FC_MIN_ALERT_STOCK_TARGET = max(1, int(os.getenv("FC_MIN_ALERT_STOCK_TARGET", "1")))
# v16.1: FirstCry's product page and its delivery check count units for the
# whole country — the same answer for every pincode (probe 18, 20 Oct); it's
# FirstCry's cart that says "Cannot be delivered to 248001". The one part of
# FirstCry that looks at your pincode is its in-stock list (asked for 248001).
# 20-21 Oct, every alert you checked in the cart was undeliverable — Porsche
# 928S (3 left), Toyota Tacoma (1), Mercedes 300 SL (1), Pantone Bronco (2) —
# and each time the in-stock list said "out" while the page said "in".
# v16.4: so EVERY car coming back must be on that list — 22 Oct 10:39 the AAR
# Cuda alerted with 5 units and a yes from the delivery check, the list never
# had it, and the cart said "just went out of stock" (5+ units used to skip the
# list). Only a car listed in the last few hours may go on the catalogue's word
# (FC_NEW_FRESH_H). FC_SURE_UNITS is now the units a car needs while it's held
# as a phantom; 0 turns all of this off.
FC_SURE_UNITS = max(0, int(os.getenv("FC_SURE_UNITS", "5")))
# A car we hold in stock that FirstCry's in-stock list for 248001 hasn't shown
# for this many minutes is out for you, whatever the page and delivery check say
# — otherwise its real restock could never alert. (The list drops cars for a
# few minutes when it refreshes, so not at once.)
FC_OFFLIST_MIN = float(os.getenv("FC_OFFLIST_MIN", "10"))
# A car whose alert turned out a phantom (out again within FC_PHANTOM_MIN
# minutes) needs FC_SURE_UNITS units for FC_PHANTOM_HOLD_H hours: the same few
# units kept coming and going — Mercedes CLA 5 alerts in a day, Honda City
# Turbo 5, Toyota Tacoma 4, Pantone Bronco 4, each gone within minutes.
FC_PHANTOM_MIN = float(os.getenv("FC_PHANTOM_MIN", "30"))
FC_PHANTOM_HOLD_H = float(os.getenv("FC_PHANTOM_HOLD_H", "12"))
# v16.3: new stock the CATALOGUE shows (not yet FirstCry's in-stock list for
# 248001) while the product page says 0 alerts only for a car listed in the last
# this-many hours — brand-new stock whose page hasn't caught up. Older cars sit
# in that state for days (21 Oct: a Lucid Air since the 19th, on every other
# pincode's in-stock list but not 248001's) and wait for the list.
FC_NEW_FRESH_H = float(os.getenv("FC_NEW_FRESH_H", "6"))
# …and any such alert on the page's 0 only while that state is new: units for
# 248001 appeared less than this many minutes ago. Pages of new stock catch up
# within 1-15 min; a page that still says 0 after that isn't catching up (21 Oct
# 23:12 the same Lucid Air, on and off 248001's list, was alerted and gone).
FC_PAGE_LAG_MIN = float(os.getenv("FC_PAGE_LAG_MIN", "20"))
# v2: the v1 run that misread TTL wrongly flipped ~209 cars to sold out. Bumping
# the version makes the next run treat every FirstCry reading as a silent
# correction, so those cars reappearing can NOT fire false restock alerts.
FC_API_STOCK_VER = f"fc_api_v3_p{os.getenv('FC_PINCODE', '248001').strip() or '0'}_m{max(1, int(os.getenv('FC_MIN_ALERT_STOCK', '2')))}"
_FC_API_REFERER = "https://www.firstcry.com/hotwheels/5/0/113"
FC_LAST_MODE = [None]      # "api" or "html" — read by runner.py to pick a safe cadence
FC_API_COMPLETE = [False]  # did the last API sweep reach the natural end?

# exact parameter set, in the order the site sends it
_FC_API_PARAMS = [
    ("PageNo", "2"),
    ("PageSize", "20"),
    ("SortExpression", "Popularity"),
    ("OnSale", "5"),
    ("SearchString", "brand"),
    ("SubCatId", ""),
    ("BrandId", ""),
    ("Price", ""),
    ("Age", ""),
    ("Color", ""),
    ("OptionalFilter", ""),
    ("OutOfStock", ""),
    ("Type1", ""),
    ("Type2", ""),
    ("Type3", ""),
    ("Type4", ""),
    ("Type5", ""),
    ("Type6", ""),
    ("Type7", ""),
    ("Type8", ""),
    ("Type9", ""),
    ("Type10", ""),
    ("Type11", ""),
    ("Type12", ""),
    ("Type13", ""),
    ("Type14", ""),
    ("Type15", ""),
    ("combo", ""),
    ("discount", ""),
    ("searchwithincat", ""),
    ("ProductidQstr", ""),
    ("searchrank", ""),
    ("pmonths", ""),
    ("cgen", ""),
    ("PriceQstr", ""),
    ("DiscountQstr", ""),
    ("sorting", ""),
    ("MasterBrand", "113"),
    ("Rating", ""),
    ("Offer", ""),
    ("skills", ""),
    ("material", ""),
    ("curatedcollections", ""),
    ("measurement", ""),
    ("gender", ""),
    ("exclude", ""),
    ("premium", ""),
    ("pcode", "0"),                      # replaced at runtime by FC_PINCODE
    ("isclub", "0"),
    ("deliverytype", ""),
    ("authors", ""),
    ("booktype", ""),
    ("character", ""),
    ("collections", ""),
    ("format", ""),
    ("genre", ""),
    ("booklanguage", ""),
    ("publication", ""),
    ("skill", "")
]


# ── Fresh data: getting past FirstCry's 15-minute cache (v13) ─────────────────
# Measured, not guessed. This repo's own history (14,000 seen.json commits) shows
# every FirstCry change the bot ever saw arriving in waves ~16 minutes apart, and
# live probes of the API confirmed why: FirstCry's server caches each listing
# answer for 900 s ("Cache-Control: max-age=900"; a cached answer carries "TTL" =
# seconds it has left). The old "_=<timestamp>" buster only got past the CDN —
# FirstCry's own cache ignores unknown parameters, so the bot kept reading a
# snapshot up to 15 minutes old, and a hot car could restock and sell out inside
# that window without ever being seen.
#
# Live probes from GitHub's runners (18 Oct 2026): the request the bot made was
# answered from that cache with TTL 337→3, i.e. data 9-15 minutes old. FirstCry's
# cache key DOES include its own "searchrank" and "sorting" parameters, which
# don't change the results (probe: 401 products, identical stock, all 22 pages
# computed live), so a new value per sweep makes FirstCry compute the answer
# fresh. Every answer is checked: a live one carries no TTL. If a trick ever
# stops working the bot notices within three sweeps, logs it, and tries the
# next one, falling back to the plain request — never worse than before.
FC_FRESH = os.getenv("FC_FRESH", "auto").strip().lower()
_FC_FRESH_ORDER = ["searchrank", "sorting"]
_FC_FRESH = {"strategy": None, "stale": 0, "dirty": False, "fresh_pages": 0,
             "stale_pages": 0, "max_age": 0}


def _fc_fresh_load(seen: dict) -> None:
    meta = seen.get("_meta") if isinstance(seen.get("_meta"), dict) else {}
    st = meta.get("fc_fresh") if isinstance(meta.get("fc_fresh"), dict) else {}
    s = st.get("s")
    if FC_FRESH in _FC_FRESH_ORDER:
        s = FC_FRESH
    elif FC_FRESH in ("off", "none", "0", "false", "no"):
        s = "none"
    elif s not in _FC_FRESH_ORDER + ["none"]:
        s = _FC_FRESH_ORDER[0]
    elif s == "none" and _hours_since(st.get("since", "")) >= 6:
        s = _FC_FRESH_ORDER[0]           # every 6 h, try the tricks again
    _FC_FRESH["strategy"] = s


def _fc_fresh_save(seen: dict) -> None:
    if not _FC_FRESH["dirty"]:
        return
    meta = seen.setdefault("_meta", {})
    meta["fc_fresh"] = {"s": _FC_FRESH["strategy"],
                        "since": _bucket(time.strftime("%Y-%m-%dT%H:%M:%S"))}
    _save_seen_file(seen)


def _fc_fresh_params() -> dict:
    """Extra query values that give this sweep a cache key FirstCry hasn't built."""
    s = _FC_FRESH["strategy"]
    token = str(int(time.time() * 1000) % 1_000_000_000)    # unique per sweep
    if s == "searchrank":
        return {"searchrank": token}
    if s == "sorting":
        return {"sorting": token}
    return {}


def _fc_fresh_verdict(fresh_pages: int, stale_pages: int, max_age: int) -> str:
    """Judge one sweep; switch trick after 3 stale sweeps in a row."""
    _FC_FRESH["fresh_pages"], _FC_FRESH["stale_pages"] = fresh_pages, stale_pages
    _FC_FRESH["max_age"] = max_age
    s = _FC_FRESH["strategy"]
    if s in (None, "none"):
        return f"plain request (cached; data up to {max_age}s old)" if stale_pages else "plain request"
    if stale_pages == 0:
        _FC_FRESH["stale"] = 0
        return f"fresh ✓ ({s}, {fresh_pages} page(s) computed live)"
    _FC_FRESH["stale"] += 1
    note = (f"cached ✗ ({s}: {stale_pages} page(s) came from FirstCry's cache, "
            f"up to {max_age}s old)")
    if FC_FRESH == "auto" and _FC_FRESH["stale"] >= 3:
        order = _FC_FRESH_ORDER + ["none"]
        nxt = order[min(order.index(s) + 1, len(order) - 1)] if s in order else "none"
        print(f"  [FC-API] fresh-data trick '{s}' stopped working — switching to '{nxt}'")
        _FC_FRESH["strategy"], _FC_FRESH["stale"], _FC_FRESH["dirty"] = nxt, 0, True
    return note


def _fc_api_query(page: int, size: int, extra: dict | None = None) -> str:
    extra = extra or {}
    out = []
    for k, v in _FC_API_PARAMS:
        if k == "PageNo":
            v = str(page)
        elif k == "PageSize":
            v = str(size)
        elif k == "MasterBrand":
            v = FC_API_BRAND
        elif k == "pcode":
            v = _FC_PCODE_ACTIVE[0]
        if k in extra:
            v = extra[k]
        out.append(f"{k}={quote(v, safe='')}")
    return FC_API_URL + "?" + "&".join(out)


def _fc_unwrap(o):
    """WCF services often return {"XResult": "<json encoded as a string>"}."""
    if isinstance(o, str):
        s = o.strip()
        if s[:1] in "[{":
            try:
                return _fc_unwrap(json.loads(s))
            except Exception:
                return o
        return o
    if isinstance(o, dict):
        return {k: _fc_unwrap(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_fc_unwrap(v) for v in o]
    return o


def _ci(d: dict, *names):
    """Case-insensitive lookup; supports dotted paths like 'stock.current'."""
    for n in names:
        cur, ok = d, True
        for part in n.lower().split("."):
            if isinstance(cur, dict):
                lk = {k.lower(): k for k in cur}
                if part in lk:
                    cur = cur[lk[part]]
                    continue
            ok = False
            break
        if ok and cur not in (None, ""):
            return cur
    return None


# FirstCry's SearchResult.svc uses abbreviated keys — confirmed from a live
# response: PId, PInfId, PNm (name), MRP, Disc, CrntStock, P_Grp_ID, BNm …
_ID_KEYS    = ("pid", "pinfid", "productid", "productinfoid", "prodid", "infoid", "id")
_NAME_KEYS  = ("pnm", "pname", "productname", "prodname", "prodnm", "name", "title")
_PRICEY     = ("pricing", "mrp", "price", "discprice", "sellingprice", "sp",
               "actualprice", "nonclubprice", "stock", "currentstock", "crntstock")


def _fc_api_products(data) -> list:
    """Collect product-like dicts. A product needs an id, a name AND a price or
    stock field — the last test stops nested {"name","id"} brand/category
    objects from being mistaken for products."""
    found, stack = [], [data]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            keys = {k.lower() for k in n}
            if (any(k in keys for k in _ID_KEYS) and any(k in keys for k in _NAME_KEYS)
                    and any(k in keys for k in _PRICEY)):
                found.append(n)
                continue
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)
    return found


def _truthy(v) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "y")


def _fc_api_stock(p: dict):
    """(stock_state, unit_count_or_None) from a product record."""
    s = _ci(p, "stock")
    cnt = None
    if isinstance(s, dict):
        cnt = _ci(s, "current", "qty", "available")
    elif s is not None and re.fullmatch(r"-?\d+(\.\d+)?", str(s).strip()):
        cnt = s
    if cnt is None:
        cnt = _ci(p, "crntstock", "currentstock", "curstock", "stockqty", "availableqty",
                  "availablestock", "inventoryqty", "stk")
    if cnt is not None:
        try:
            c = int(float(cnt))
            return ("in_stock" if c > 0 else "out_of_stock"), c
        except Exception:
            pass
    oos = _ci(p, "isoutofstock", "outofstock", "isoos", "oos", "soldout", "issoldout")
    if oos is not None:
        return ("out_of_stock" if _truthy(oos) else "in_stock"), None
    ins = _ci(p, "instock", "isinstock", "available", "isavailable")
    if ins is not None:
        return ("in_stock" if _truthy(ins) else "out_of_stock"), None
    return None, None


def _fc_slug(name: str) -> str:
    # FirstCry writes "&" as "and" in its URLs (…/fast-and-furious-…)
    n = (name or "").lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", n).strip("-")[:150] or "hot-wheels"


FC_THROTTLED = [0.0]   # epoch until which quick sweeps pause (FirstCry sent 429/403)
_FC_INSTOCK_PAGES = [9]  # pages the in-stock-only list takes (178 cars → 9 pages)
_FC_SESSION = {"cookies": None, "at": 0.0}
FC_LAST_SWEEP = {"hot": False, "pages": 0, "fresh": "", "secs": 0.0, "complete": False}


def _fc_cookies() -> dict:
    """Anonymous session cookies from one listing-page visit, reused for 10 min
    rather than paying a warm-up request before every sweep."""
    if _FC_SESSION["cookies"] is not None and time.time() - _FC_SESSION["at"] < 600:
        return _FC_SESSION["cookies"]
    cookies = {}
    try:
        sess = http.Session(**_IMPERSONATE) if _IMPERSONATE else http.Session()
        sess.get(_fc_bust(_FC_API_REFERER), headers={**COMMON_HEADERS, **_FC_NOCACHE},
                 timeout=FC_API_TIMEOUT)
        jar = getattr(sess.cookies, "jar", sess.cookies)
        cookies = {c.name: c.value for c in jar}
    except Exception as e:
        print(f"  [FC-API] warm-up failed: {type(e).__name__}")
    _FC_SESSION.update(cookies=cookies, at=time.time())
    return cookies


def fc_api_catalogue(hot: bool = False):
    """Hot Wheels catalogue via FirstCry's own paging API, or None.

    hot=False  FULL sweep: every page (~21), sold-out cars included. Pages are
               fetched in parallel and a slow page is retried; the sweep only
               counts as COMPLETE when every page up to the natural end
               succeeded (that's what lets a car missing for hours be treated
               as delisted).
    hot=True   QUICK sweep: FirstCry's own "OutOfStock" filter returns ONLY the
               cars in stock for your pincode (probe: 178 cars, 9 pages, every
               one with stock > 0) — every in-stock car, including anything that
               has just restocked or just been listed, in under half the
               requests. No retries: the next sweep is seconds away.
    """
    t0 = time.time()
    headers = {**COMMON_HEADERS, **_FC_NOCACHE,
               "Accept": "application/json, text/javascript, */*; q=0.01",
               "Content-Type": "application/json; charset=utf-8",
               "X-Requested-With": "XMLHttpRequest",
               "Referer": _FC_API_REFERER}
    cookies = _fc_cookies()
    size = FC_API_PAGESIZE
    base = {"OutOfStock": "1"} if hot else {}
    fresh = _fc_fresh_params()
    extra = {**base, **fresh}
    ages = {}                                   # page -> None (live) or seconds old

    def fetch(page, ex):
        """(decoded JSON or None, error text or None)."""
        err = None
        for attempt in range(1 if hot else 3):
            try:
                r = http.get(_fc_bust(_fc_api_query(page, size, ex)), headers=headers,
                             cookies=cookies, timeout=FC_API_TIMEOUT, **_IMPERSONATE)
            except Exception as e:
                err = type(e).__name__
            else:
                if r.status_code == 200:
                    try:
                        data = _fc_unwrap(r.json())
                    except Exception:
                        err = f"not JSON ({r.text[:80]!r})"
                    else:
                        ttl = data.get("TTL") if isinstance(data, dict) else None
                        try:
                            ages[page] = None if ttl in (None, "") else max(0, 900 - int(float(ttl)))
                        except (TypeError, ValueError):
                            ages[page] = None
                        return data, None
                else:
                    err = f"HTTP {r.status_code}"
                    if r.status_code in (429, 403):
                        FC_THROTTLED[0] = time.time() + 300
            if attempt < 2 and not hot:
                # back off harder when FirstCry is signalling overload
                time.sleep((3.0 if err in ("HTTP 429", "HTTP 403") else 1.5) * (attempt + 1))
        return None, err

    if not hot:
        _FC_PCODE_ACTIVE[0] = FC_PINCODE
    data, err = fetch(1, extra)
    items = _fc_api_products(data) if data is not None else []
    if not items and fresh:
        # the fresh-data value broke the request — never let that cost a sweep
        print(f"  [FC-API] fresh-data request returned nothing ({err or 'empty'}) — "
              f"plain request this sweep")
        if FC_FRESH == "auto":
            _FC_FRESH["stale"] = 2           # one more miss and the next trick is tried
        fresh, extra = {}, dict(base)
        data, err = fetch(1, extra)
        items = _fc_api_products(data) if data is not None else []
    if not items and not hot and FC_PINCODE != "0":
        print(f"  [FC-API] pincode {FC_PINCODE} request returned nothing ({err or 'empty'}) "
              f"— falling back to nationwide stock (pcode=0)")
        _FC_PCODE_ACTIVE[0] = "0"
        data, err = fetch(1, extra)
        items = _fc_api_products(data) if data is not None else []
    if data is None:
        print(f"  [FC-API] page 1 failed: {err}")
        return None
    if not items and not hot:
        top = list(data.keys())[:12] if isinstance(data, dict) else type(data).__name__
        print(f"  [FC-API] no products recognised. top-level: {top}")
        print(f"  [FC-API] response head: {json.dumps(data)[:400]}")
        return None
    if not hot:
        print(f"  [FC-API] stock for pincode: {_FC_PCODE_ACTIVE[0]}")

    products, failed = {}, []

    def add(its):
        n = 0
        for p in its:
            pid = str(_ci(p, *_ID_KEYS) or "").strip()
            if pid.isdigit() and pid not in products:
                products[pid] = p
                n += 1
        return n

    add(items)
    end_found = len(items) < min(size, 20)
    page, dry = 1, 0

    while not end_found and page < FC_API_MAXPAGES:
        if hot:
            # the first batch covers the expected length in one go
            span = (max(2, _FC_INSTOCK_PAGES[0]) - 1) if page == 1 else 3
        else:
            span = FC_API_PARALLEL
        batch = list(range(page + 1, min(page + max(1, span), FC_API_MAXPAGES) + 1))
        with ThreadPoolExecutor(max_workers=len(batch)) as ex:
            results = dict(zip(batch, ex.map(lambda pg: fetch(pg, extra), batch)))
        for pg in batch:                       # process strictly in page order
            page = pg
            data, err = results[pg]
            if data is None:
                failed.append(f"{pg}({err})")
                continue                        # skip it, keep collecting later pages
            its = _fc_api_products(data)
            new = add(its)
            if len(its) < min(size, 20):
                end_found = True                # short/empty page = end of the list
                break
            # two full pages in a row adding nothing: the server is ignoring
            # PageNo (serving the same page) — stop rather than loop to the cap
            dry = dry + 1 if new == 0 else 0
            if dry >= 2:
                failed.append("paging-stalled")
                end_found = False
                break
        if dry >= 2:
            break

    complete = end_found and not failed
    live = sum(1 for a in ages.values() if a is None)
    stale = len(ages) - live
    max_age = max([a for a in ages.values() if a is not None] or [0])
    verdict = _fc_fresh_verdict(live, stale, max_age) if (fresh or stale) else "plain request"
    FC_LAST_SWEEP.update(hot=hot, pages=len(ages), fresh=verdict, secs=time.time() - t0,
                         complete=complete)
    n_in = sum(1 for p in products.values() if (_fc_api_stock(p)[1] or 0) > 0)
    if complete:
        # pages the in-stock list needs, +1 when it's an exact multiple of 20
        # (the empty page after a full one is how its end is recognised)
        _FC_INSTOCK_PAGES[0] = max(1, -(-(n_in + 1) // 20))
    if hot:
        print(f"  [FC-API] quick sweep: {n_in} in stock from {len(ages)} page(s) in "
              f"{time.time()-t0:.1f}s — {verdict}"
              + ("" if complete else f" — incomplete ({', '.join(failed) or 'no end'})"))
        return products
    if not products:
        return None
    from collections import Counter
    cats = Counter(str(_ci(p, "SCNm") or "?") for p in products.values())
    note = "" if complete else f" — INCOMPLETE (failed: {', '.join(failed) or 'no end found'})"
    print(f"  [FC-API] {len(products)} products across {page} page(s) "
          f"({len(products) - n_in} with zero stock) in {time.time()-t0:.1f}s{note}")
    print(f"  [FC-API] data: {verdict}")
    print(f"  [FC-API] subcategories: {dict(cats.most_common(8))}")
    FC_API_COMPLETE[0] = complete
    return products


def fc_api_records(products: dict, prev_fc: dict, quiet: bool = False) -> list:
    """Turn raw API records into tracker products (after exclusions)."""
    out, sample_done = [], quiet
    for pid, p in products.items():
        name = _fc_name(str(_ci(p, *_NAME_KEYS) or ""))
        if not name or _fc_excluded(name):
            continue
        # FirstCry's own category labels (CNm / SCNm) catch big sets whose NAME
        # doesn't say "track set" (e.g. "Ultimate Dual Dragon Transporter").
        cat = " ".join(str(_ci(p, k) or "") for k in ("CNm", "SCNm"))
        if cat.strip() and _fc_excluded(cat):
            continue
        premium = _truthy(_ci(p, "IsPremium") or 0)
        stock, count = _fc_api_stock(p)
        if stock is None:
            stock = (prev_fc.get(pid) or {}).get("stock")
            if stock is None:
                continue
        if (stock == "in_stock" and isinstance(count, int)
                and 0 < count < _fc_min_units(pid, name)):
            stock = "out_of_stock"      # effectively gone — alert when FirstCry restocks it
        mrp = price_to_int(_ci(p, "pricing.mrp", "mrp"))
        price = price_to_int(_ci(p, "pricing.discPrice", "discprice", "dpric", "dprice",
                                 "sprice", "sellprice", "sellingprice", "offerprice",
                                 "nonclubprice", "actualprice", "actprice", "pric",
                                 "sp", "price"))
        if not price and mrp:
            # FirstCry sends MRP plus a discount ("Disc"). It's a percentage in
            # their other API (mrp 445, disc 11 -> 397.25); treat small values as
            # a percent and larger ones as a rupee amount off.
            try:
                d = float(str(_ci(p, "disc", "discount", "discper") or 0))
            except ValueError:
                d = 0.0
            if 0 < d < 100:
                price = int(round(mrp * (1 - d / 100.0)))
            elif 100 <= d < mrp:
                price = int(round(mrp - d))
            else:
                price = mrp
        if mrp and price and not (price < mrp <= price * 4):
            mrp = None
        url = _ci(p, "producturl", "purl", "url", "seourl", "pdpurl", "prdurl")
        if url and str(url).startswith("/"):
            url = "https://www.firstcry.com" + str(url)
        if not (url and str(url).startswith("http")):
            url = f"https://www.firstcry.com/hot-wheels/{_fc_slug(name)}/{pid}/product-detail"
        pre = _ci(p, "tags.ispreorder", "ispreorder", "preorder")
        if pre is not None and _truthy(pre):
            name = name + " [PRE-ORDER]"
        if not sample_done:
            print(f"  [FC-API] sample: {name[:48]} | stock={stock} count={count} "
                  f"price={price} mrp={mrp}")
            sample_done = True
        out.append({
            "id": f"fc_{pid}", "source": "firstcry", "name": name, "url": url,
            "price": f"₹{price}" if price else "",
            "mrp": f"₹{mrp}" if mrp else "",
            "stock": stock,
            "stock_count": count,
            "badge_new": False,
            "watched": pid in FC_WATCH_IDS or _fc_is_marque(name) or premium,
            "auto_watch": _fc_is_marque(name) or premium,
            "stock_ver": FC_API_STOCK_VER,
            # trusted = this stock value came from an actual API reading this run
            "fc_trusted": True,
            "fc_listed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "fc_api_seen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
    return out


def _fc_oos_record(pid: str, v: dict) -> dict:
    """A stored FirstCry car re-recorded as not buyable (live reading)."""
    nm = v.get("name", "")
    return {"id": f"fc_{pid}", "source": "firstcry", "name": nm,
            "url": v.get("url") or f"https://www.firstcry.com/x/x/{pid}/product-detail",
            "price": v.get("price", ""), "mrp": "", "stock": "out_of_stock",
            "badge_new": False, "watched": pid in FC_WATCH_IDS or _fc_is_marque(nm),
            "auto_watch": _fc_is_marque(nm), "stock_ver": FC_API_STOCK_VER,
            "fc_trusted": True, "fc_listed_at": v.get("fc_listed_at", ""),
            "fc_api_seen_at": v.get("fc_api_seen_at", "")}


# ══════════════════════════════════════════════════════════════════════════════════
# FirstCry — the product page is the final word (v14)
# ══════════════════════════════════════════════════════════════════════════════════
# Measured on 18 Oct 2026 (probes 9-13, run on GitHub against the live site):
#   • The listing the bot reads (catalogue + in-stock list) is FirstCry's search
#     index. It refreshes in batches every few minutes, so it ran up to ~10 min
#     behind the product page, and it kept showing cars nobody could order: the
#     Plymouth Road Runner stayed on the in-stock list with "2" for 20+ minutes
#     after its page said 0.
#   • The product page you open from an alert came from a CDN copy up to 20 min
#     old. The same link with a query string (…/product-detail?fresh=…) is
#     rendered fresh instead.
#   • Whether you can order a car is decided by what the page itself checks:
#       CurrentProductDetailJSON[car].CS > 0   → ADD TO CART (else "Notify me")
#       FirstCry's delivery check for your     → groupserviceability[car] == 0
#       pincode (tatapi/oam/checkdeliveryinfo)   makes the page silently switch
#                                                to another car of the same set
#                                                (the Road Runner link that
#                                                opened the Datsun 620)
#     One product page lists every car of its colour set (up to ~27 cars), and
#     one delivery-check call answers for up to 40 cars.
# So every FirstCry change the listing reports is confirmed on the product page
# and the delivery check before it can become an alert, cars believed in stock
# are re-checked against the delivery check every pass, and the product pages
# of your 🎯 cars that are out of stock are read directly, a few sets per pass,
# so their restock doesn't wait for the listing to catch up.
FC_LIVE         = os.getenv("FC_LIVE", "true").lower() == "true"
FC_LIVE_POLL    = max(0, int(os.getenv("FC_LIVE_POLL", "4")))    # 🎯 sets read per pass
FC_LIVE_AUDIT   = max(0, int(os.getenv("FC_LIVE_AUDIT", "3")))   # unconfirmed in-stock sets per pass
FC_LIVE_MAX     = max(1, int(os.getenv("FC_LIVE_MAX", "14")))    # product pages per pass, at most
# A car the listing keeps calling in stock although its page says it can't be
# ordered (or the reverse) is re-read every FC_LIVE_RECHECK_MIN minutes, not
# every pass — the listing can disagree with the page for half an hour.
FC_LIVE_RECHECK = max(1, int(os.getenv("FC_LIVE_RECHECK_MIN", "3")))
# Product pages normally answer in ~0.5-1.5 s and the delivery check in ~0.4 s.
# Short timeouts keep a slow FirstCry from stretching a pass: on 18 Oct one run
# took 195 s instead of ~45 (most likely timeouts piling up), and every second
# a pass runs long is a second FirstCry isn't re-checked.
FC_PAGE_TIMEOUT = float(os.getenv("FC_PAGE_TIMEOUT", "8"))
FC_TAT_TIMEOUT  = float(os.getenv("FC_TAT_TIMEOUT", "6"))
FC_LIVE_BUDGET  = float(os.getenv("FC_LIVE_BUDGET_S", "15"))   # live-check seconds per pass
# Restocks confirmed on the page can't be listing flicker, so the same car may
# alert again an hour later. The 24 h rule (still used for unconfirmed ones)
# silenced 39 genuine FirstCry comebacks in 3 days — Ferrari 12 Cilindri twice,
# Skyline 2000 GT-R, McLaren W1, Audi R8 … — all 2.3 h or more apart.
FC_RESTOCK_COOLDOWN_H = float(os.getenv("FC_RESTOCK_COOLDOWN_H", "1"))
_FC_HW_NAME     = re.compile(r"hot\s*-?\s*wheel", re.I)
FC_TAT_URL      = "https://www.firstcry.com/tatapi/oam/checkdeliveryinfo"
FC_TAT_BATCH    = 40
# v15: asked about one car as the MAIN product, the delivery check also says how
# many units can actually reach your pincode (Result.IsServicable). 20 Oct: the
# SF90's page said 155 (FirstCry's national stock) while IsServicable said 1 for
# 248001 — the "1" the app showed — and 0 six minutes later. 36 of 137 FirstCry
# alerts in 40 h stopped being orderable within 5 minutes, nearly all cars with
# one local unit that kept being reserved and released. So a restock now needs
# FC_MIN_ALERT_STOCK units that can be delivered to you, and that is the count
# the alert shows.
# Cars that sit right at the edge (one local unit, or local units the page
# doesn't sell yet) are re-read every FC_LIVE_NEAR_RECHECK minutes.
FC_LIVE_NEAR_RECHECK = max(1, int(os.getenv("FC_LIVE_NEAR_RECHECK_MIN", "1")))
_FC_RUN_PASS = [0]          # live checks done in this run (the first one sweeps every car)
FC_LIVE_DEBUG = os.getenv("FC_LIVE_DEBUG", "").lower() in ("1", "true", "yes")
_FC_LIVE: dict = {}         # pid -> {"cs","svc","pn","mrp","dis","gid","members","at_page","at_svc"}
_FC_PAGE_TRIED: dict = {}   # pid -> when its product page (or its set's) was last asked for
_FC_LIVE_PAUSE = [0.0]      # epoch until which product pages are left alone (429/403)
_FC_TAT_PAUSE = [0.0]       # epoch until which the delivery check is left alone
_FC_LIVE_STATS = {"pages": 0, "tat": 0}
_FC_LIVE_SINCE = [""]       # when v14 first ran (seen.json _meta), 15-min bucket
_FC_LIVE_LOCK = threading.Lock()


# ── v17: FirstCry's own checkout cart is the final word ─────────────────────────
# Every other FirstCry signal turned out to be national or out of date: the
# product page and the delivery check count the whole country, and even the
# in-stock list for 248001 had the '70 AAR Cuda on 23 Oct 13:30 while your cart
# said "Cannot be delivered to 248001". FirstCry's checkout page asks
# CSC.fcappservices.in/…/ShoppingCart.svc/json/LoadCart about a guest cart — a
# cookie string, "NO^<id>^1^0" per car; nothing is stored or ordered — and gets,
# per car, the units it can send to your pincode (CurrentStock), the warehouse
# that would ship it ("0" = none), pincode limits and the delivery date. A car
# you can buy is in that answer with units from a real warehouse; the AAR Cuda
# wasn't in it at all. One call answers ~100 cars in ~1.5 s (probes 23 Oct).
# Every FirstCry stock change, in or out, is decided by it. Cars the listing,
# page or delivery check point at are asked every pass; cars held in stock, 🎯
# cars and the rest are asked in turn, so a car turning buyable is seen within
# about half a minute (🎯) to a few minutes even when the page and the lists
# lag. If the cart can't be asked, the signals decide as before and the alert
# says the cart wasn't checked.
FC_CART = os.getenv("FC_CART", "true").lower() == "true"
FC_CART_URL = "https://CSC.fcappservices.in/ShoppingCart/ShoppingCart.svc/json/LoadCart"
FC_CART_BATCH = max(1, int(os.getenv("FC_CART_BATCH", "75")))      # cars per call
FC_CART_MAX = max(0, int(os.getenv("FC_CART_MAX", "150")))         # cars asked in turn per pass
FC_CART_TIMEOUT = float(os.getenv("FC_CART_TIMEOUT", "10"))
# a comeback the cart confirmed may alert again after this many minutes (units
# that really came back after a sell-out are worth knowing about)
FC_CART_COOLDOWN_MIN = float(os.getenv("FC_CART_COOLDOWN_MIN", "30"))
# v17.2: …that's for your 🎯 cars (another real chance). Any other car alerts at
# most once in this many hours: 23-24 Oct, 70 alerts in 14 h, about half of them
# the same few cars over and over (Trophy Case 7×, Twin Tags 6×, Safari Mode 6×)
# as single units were reserved and released.
FC_CART_COOLDOWN_OTHER_H = float(os.getenv("FC_CART_COOLDOWN_OTHER_H", "6"))
# v17.1: …and only while its product page sells it too — "Add to cart" on the
# page, not "Notify me". The cart counts units the page has already sold: 23 Oct
# 16:20 it had 1 Armored Batmobile for 248001 while the page and your Favourites
# said Out of Stock. A page reading counts as current for this many seconds.
FC_CART_PAGE_S = float(os.getenv("FC_CART_PAGE_S", "90"))
# v17.4: …except a fresh release. 25 Oct 10:00 FirstCry put the Dino 206 GT on
# sale: its in-stock list for 248001 picked it up and the cart had a batch for
# you, while its product page said "Out of Stock" for 3 more minutes — and it
# could be bought all along from your Profile (Favourites / Recently viewed →
# add to cart). A deals channel posted it then; we alerted when the page caught
# up, 4 min later, and it sold out as you paid. So a car that came onto that
# list in the last FC_FRESH_MIN minutes, with FC_FRESH_UNITS+ units in the cart,
# alerts at once — with that tip — whatever its page says. (The Batmobile, 23
# Oct, was in the cart but never on that list: the page AND your Favourites
# said Out of Stock. Cars the cart would take while that list leaves them out —
# up to 7 units each, probe 37 — still wait for their page.) 0 = off.
FC_FRESH_UNITS = max(0, int(os.getenv("FC_FRESH_UNITS", "5")))
FC_FRESH_MIN = float(os.getenv("FC_FRESH_MIN", "10"))
# "came onto the list" = on it again after at least this many minutes off it —
# the list drops cars for a few minutes whenever it refreshes
FC_FRESH_GAP_MIN = float(os.getenv("FC_FRESH_GAP_MIN", "30"))
_FC_CART_PAUSE = [0.0]      # epoch until which the cart is left alone (429/403)
_FC_CART_DEV = {}           # this run's guest device id + fingerprint headers
_FC_CART_STATS = {"calls": 0, "cars": 0, "fail": 0}


def fc_cart_check(pids, pincode: str | None = None):
    """FirstCry's checkout cart, asked as a guest about these cars for your
    pincode → {car: {"ok", "n", "eta", "price", "mrp", "name"}} — or None if the
    cart couldn't be asked at all. A car the cart leaves out isn't buyable for
    you right now ("ok": False, "gone": True)."""
    pincode = str(pincode or FC_PINCODE)
    pids = [str(p) for p in dict.fromkeys(pids) if str(p).isdigit()]
    if not pids:
        return {}
    if pincode in ("", "0") or _FC_CART_PAUSE[0] > time.time():
        return None
    if not _FC_CART_DEV:
        import uuid
        _FC_CART_DEV.update(fcdid=str(uuid.uuid4()), fingerprint=uuid.uuid4().hex)
    hdr = {**COMMON_HEADERS, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8", "Origin": "https://checkout.firstcry.com",
           "Referer": "https://checkout.firstcry.com/pay", **_FC_CART_DEV}

    def one(chunk):
        body = {"pro": "*".join(f"NO^{p}^1^0" for p in chunk), "shipPin": pincode, "SiteType": 0,
                "LC": 0, "CR": 0, "Coupons": "", "FC_AUTH": "", "ShipMobile": "", "ShipPhone": "",
                "PayBack": "", "State": "", "PaymentType": "", "LPO": False, "LSD": False, "CCA": "",
                "LT": "N", "UA": hdr.get("User-Agent", ""), "AddressType": "Home", "AssemblyMap": "",
                "ptype": "", "pvalue": "", "FitKidChildIdMap": "", "CouponCodeToCheck": "",
                "GiftCodeToCheck": "", "BuyerType": "", "CardPar": "", "RemoveFreeErr": "",
                "redesign": True, "caller": "", "Ageid": "", "bmsm": "", "SegmentIDs": "", "latlong": "",
                "segmentcookie": "", "cardref": "", "savedCardBankCode": "", "savedCardIssuingBank": "",
                "cardtoken": ""}
        try:
            r = http.post(FC_CART_URL, data=json.dumps(body), headers=hdr, timeout=FC_CART_TIMEOUT,
                          **_IMPERSONATE)
        except Exception:
            return chunk, None
        _FC_CART_STATS["calls"] += 1
        if r.status_code in (403, 429):
            _FC_CART_PAUSE[0] = time.time() + 300
            print(f"  [FC-CART] FirstCry answered {r.status_code} — cart checks paused for 5 min")
            return chunk, None
        if r.status_code != 200:
            return chunk, None
        try:
            x = r.json()
            x = x.get("LoadCartResult") if isinstance(x, dict) else None
            while isinstance(x, str):
                x = json.loads(x)
            summ = (x or {}).get("pOrderSummary")
        except Exception:
            return chunk, None
        if not isinstance(summ, dict) or str(summ.get("ShipPinCode") or "") != pincode:
            return chunk, None
        items = summ.get("PurchaseOrderItemList") or []
        if len(chunk) >= 10 and len(items) < len(chunk) / 2:
            return chunk, None          # most of a big cart missing: a hiccup, not a sell-out
        got = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            p = str(it.get("ProductID") or "")
            n = _fc_int(it.get("CurrentStock")) or 0
            isv = _fc_int(it.get("IsServicable"))
            wh = str(it.get("warehouseid") or "0")
            limited = ((_fc_int(it.get("NoOfPinCodeToCheck")) or 0) > 0
                       and not (it.get("isValidPincodeForDropShipment") or it.get("IsValidPincodeForDropShipProduct")))
            ok = n > 0 and (isv is None or isv > 0) and wh not in ("", "0") and not limited
            got[p] = {"ok": ok, "n": (min(n, isv) if isv else n) if ok else 0,
                      "eta": str(it.get("EstimatedDeliveryDate") or ""), "price": it.get("ActualPrice"),
                      "mrp": it.get("MRP"), "name": str(it.get("ProductName") or "")}
        return chunk, got

    chunks = [pids[i:i + FC_CART_BATCH] for i in range(0, len(pids), FC_CART_BATCH)]
    out, failed = {}, 0
    with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as ex:
        for chunk, got in ex.map(one, chunks):
            if got is None:
                failed += 1
                continue
            for p in chunk:
                out[p] = got.get(p) or {"ok": False, "n": 0, "gone": True, "eta": "", "price": None,
                                        "mrp": None, "name": ""}
    _FC_CART_STATS["cars"] += len(out)
    _FC_CART_STATS["fail"] += failed
    return None if failed == len(chunks) else out


def _fc_eta(s: str) -> str:
    """'2026-10-24 00:00:00' → 'Sat 24 Oct'."""
    try:
        return time.strftime("%a %d %b", time.strptime(str(s)[:10], "%Y-%m-%d"))
    except Exception:
        return ""


def _fc_json_after(txt: str, pat: str):
    """The JSON object that starts right after `pat` (balanced braces, aware of
    strings), or None."""
    m = re.search(pat, txt)
    if not m:
        return None
    i = txt.find("{", m.end() - 1)
    if i < 0:
        return None
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


def _fc_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def fc_fresh_link(url: str) -> str:
    """A FirstCry product link as sent in alerts. With a query string FirstCry
    renders the page fresh, instead of a CDN copy that can be 20 minutes old
    (which is how a car that really was buyable could open as sold out)."""
    if "firstcry.com" not in (url or "") or "fresh=" in url:
        return url
    return f"{url}{'&' if '?' in url else '?'}fresh={int(time.time()) % 1_000_000}"


def fc_page(pid: str):
    """Read one product page fresh → {car: live info} for its whole colour set,
    or None if it couldn't be read."""
    if _FC_LIVE_PAUSE[0] > time.time():
        return None
    url = (f"https://www.firstcry.com/hot-wheels/x/{pid}/product-detail"
           f"?fresh={int(time.time() * 1000) % 1_000_000_000}")
    try:
        r = http.get(url, headers={**COMMON_HEADERS, **_FC_NOCACHE}, cookies=_fc_cookies(),
                     timeout=FC_PAGE_TIMEOUT, **_IMPERSONATE)
    except Exception:
        return None
    _FC_LIVE_STATS["pages"] += 1
    if r.status_code in (403, 429):
        _FC_LIVE_PAUSE[0] = time.time() + 300
        print(f"  [FC-LIVE] FirstCry answered {r.status_code} — product pages paused for 5 min")
        return None
    if r.status_code != 200:
        return None
    cur = _fc_json_after(r.text, r"CurrentProductDetailJSON\s*=\s*\{")
    if not isinstance(cur, dict) or not cur:
        return None
    now = time.time()
    members = [str(k) for k, v in cur.items() if isinstance(v, dict)]
    out = {}
    with _FC_LIVE_LOCK:
        if str(pid) not in members:
            # FirstCry rendered a page that doesn't list this car at all
            # (delisted): nothing to order
            _FC_LIVE.setdefault(str(pid), {}).update(cs=0, svc=None, members=[str(pid)],
                                                     at_page=now, gone=True)
            out[str(pid)] = _FC_LIVE[str(pid)]
        for k, v in cur.items():
            if not isinstance(v, dict):
                continue
            k = str(k)
            ent = _FC_LIVE.setdefault(k, {})
            ent.update(cs=_fc_int(v.get("CS")), pn=_fc_name(str(v.get("pn") or "")),
                       mrp=_fc_int(v.get("mrp")), dis=v.get("Dis"),
                       gid=str(v.get("Gid") or ""), pre=_truthy(v.get("ispreorder") or 0),
                       members=members, at_page=now)
            out[k] = ent
    return out


def fc_delivery(pids, pincode: str | None = None) -> dict:
    """FirstCry's own delivery check for your pincode, the call the product page
    makes: {car: 1 (can be delivered) or 0 (can't)}. 40 cars per call."""
    pincode = str(pincode or FC_PINCODE)
    pids = [str(p) for p in dict.fromkeys(pids) if str(p).isdigit()]
    if (not pids or pincode in ("", "0") or _FC_LIVE_PAUSE[0] > time.time()
            or _FC_TAT_PAUSE[0] > time.time()):
        return {}
    hdr = {**COMMON_HEADERS, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8",
           "X-Requested-With": "XMLHttpRequest", "Origin": "https://www.firstcry.com"}

    def one(chunk):
        body = {"ProductIDs": chunk[0], "Pincode": pincode, "ComboId": 0, "CheckTAT": True,
                "CheckDropShipment": False, "CheckCOD": True, "subCatID": 94, "MRP": 179,
                "AddressType": "Home", "Discount": 0, "minQty": 1, "CatID": 5, "ftk": "",
                "groupproducts": ",".join(chunk)}
        ref = f"https://www.firstcry.com/hot-wheels/x/{chunk[0]}/product-detail"
        try:
            r = http.post(FC_TAT_URL, data=json.dumps(body), headers={**hdr, "Referer": ref},
                          cookies=_fc_cookies(), timeout=FC_TAT_TIMEOUT, **_IMPERSONATE)
        except Exception:
            return None
        _FC_LIVE_STATS["tat"] += 1
        if r.status_code != 200:
            return None
        try:
            g = ((r.json() or {}).get("Result") or {}).get("groupserviceability") or {}
        except Exception:
            g = {}
        return {str(k): _fc_int(v) for k, v in g.items()}

    chunks = [pids[i:i + FC_TAT_BATCH] for i in range(0, len(pids), FC_TAT_BATCH)]
    out, now, failed = {}, time.time(), 0
    with ThreadPoolExecutor(max_workers=min(6, len(chunks))) as ex:
        for res in ex.map(one, chunks):
            failed += res is None
            for k, v in (res or {}).items():
                if v in (0, 1):
                    out[k] = v
    if failed == len(chunks):
        # not answering at all: leave it alone for a minute (pages still decide
        # on units; a car off the in-stock list then waits as "unconfirmed")
        _FC_TAT_PAUSE[0] = time.time() + 60
        print("  [FC-LIVE] delivery check not answering — paused for 1 min")
    with _FC_LIVE_LOCK:
        for k, v in out.items():
            _FC_LIVE.setdefault(k, {}).update(svc=v, at_svc=now)
    return out


def fc_delivery_count(pids, pincode: str | None = None) -> dict:
    """Ask the delivery check about each car as the MAIN product: how many units
    can be delivered to your pincode (IsServicable), plus next-day / days. One
    small call per car, in parallel. {car: units} for the cars it answered."""
    pincode = str(pincode or FC_PINCODE)
    pids = [str(p) for p in dict.fromkeys(pids) if str(p).isdigit()]
    if (not pids or pincode in ("", "0") or _FC_LIVE_PAUSE[0] > time.time()
            or _FC_TAT_PAUSE[0] > time.time()):
        return {}
    hdr = {**COMMON_HEADERS, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/json; charset=utf-8",
           "X-Requested-With": "XMLHttpRequest", "Origin": "https://www.firstcry.com"}

    def one(p):
        members = ((_FC_LIVE.get(p) or {}).get("members") or [p])[:FC_TAT_BATCH]
        if p not in members:
            members = [p] + members[:FC_TAT_BATCH - 1]
        body = {"ProductIDs": p, "Pincode": pincode, "ComboId": 0, "CheckTAT": True,
                "CheckDropShipment": False, "CheckCOD": True, "subCatID": 94, "MRP": 179,
                "AddressType": "Home", "Discount": 0, "minQty": 1, "CatID": 5, "ftk": "",
                "groupproducts": ",".join(members)}
        ref = f"https://www.firstcry.com/hot-wheels/x/{p}/product-detail"
        try:
            r = http.post(FC_TAT_URL, data=json.dumps(body), headers={**hdr, "Referer": ref},
                          cookies=_fc_cookies(), timeout=FC_TAT_TIMEOUT, **_IMPERSONATE)
        except Exception:
            return p, None
        _FC_LIVE_STATS["tat"] += 1
        if r.status_code != 200:
            return p, None
        try:
            return p, (r.json() or {}).get("Result") or None
        except Exception:
            return p, None

    out, now, failed = {}, time.time(), 0
    with ThreadPoolExecutor(max_workers=min(8, len(pids))) as ex:
        for p, res in ex.map(one, pids):
            if not isinstance(res, dict):
                failed += 1
                continue
            isv = _fc_int(res.get("IsServicable"))
            g = {str(k): _fc_int(v) for k, v in (res.get("groupserviceability") or {}).items()}
            with _FC_LIVE_LOCK:
                ent = _FC_LIVE.setdefault(p, {})
                ent.update(isv=isv, at_isv=now, ndd=bool(res.get("IsNDD")),
                           days=str(res.get("ProductTAT") or ""))
                for k, v in g.items():
                    if v in (0, 1):
                        _FC_LIVE.setdefault(k, {}).update(svc=v, at_svc=now)
            if isv is not None:
                out[p] = isv
    if failed == len(pids) and len(pids) >= 3:
        _FC_TAT_PAUSE[0] = time.time() + 60
        print("  [FC-LIVE] delivery check not answering — paused for 1 min")
    return out


def fc_live_check(pids, max_pages: int | None = None, gids: dict | None = None) -> dict:
    """Live state of these cars — {car: info with "cs" (units on its product
    page) and "svc" (delivery check)} — for every car whose page was read in the
    last minute, plus every other car of those colour sets. One page per set;
    then one delivery check for every car with units. `gids` (car → colour set
    stored from an earlier run) lets cars of one set share a page read before
    this run has read any page."""
    max_pages = FC_LIVE_MAX if max_pages is None else max_pages
    now = time.time()
    deadline = now + FC_LIVE_BUDGET
    pids = [str(p) for p in dict.fromkeys(pids) if str(p).isdigit()]
    fresh = lambda p: now - (_FC_LIVE.get(p) or {}).get("at_page", 0) <= 60
    todo, covered, sets_ = [], set(), set()
    for p in pids:
        g = (gids or {}).get(p)
        if fresh(p) or p in covered or (g and g in sets_):
            continue
        todo.append(p)
        covered.add(p)
        covered.update((_FC_LIVE.get(p) or {}).get("members") or [])
        if g:
            sets_.add(g)
    todo = todo[:max_pages]

    def tried(ps):
        with _FC_LIVE_LOCK:
            for p in ps:
                for m in [p] + list((_FC_LIVE.get(p) or {}).get("members") or []):
                    _FC_PAGE_TRIED[m] = now

    if todo:
        tried(todo)
        with ThreadPoolExecutor(max_workers=min(8, len(todo))) as ex:
            list(ex.map(fc_page, todo))
        # set membership we remembered was wrong → that car's own page
        again = [p for p in pids if not fresh(p) and p not in todo][:max(0, max_pages - len(todo))]
        if again and time.time() < deadline:
            tried(again)
            with ThreadPoolExecutor(max_workers=min(8, len(again))) as ex:
                list(ex.map(fc_page, again))
    sets = set()
    for p in pids:
        if fresh(p):
            sets.update(_FC_LIVE[p].get("members") or [p])
    res = {p: _FC_LIVE[p] for p in sets if p in _FC_LIVE and fresh(p)}
    asked = set(pids)
    # v16.3: also the cars asked about whose page shows 0 — a brand-new car's
    # page often does while it can already be bought (Hellcat, 21 Oct)
    ask = [p for p, v in res.items() if ((v.get("cs") or 0) > 0 or p in asked)
           and now - v.get("at_svc", 0) > 30]
    if ask and time.time() < deadline:
        fc_delivery(ask)
    # how many units can reach you — for the cars asked about that might be
    # orderable (the delivery check didn't say no)
    need = [p for p in pids if p in res and res[p].get("svc") != 0
            and not ((res[p].get("cs") or 0) <= 0 and res[p].get("svc") is None)
            and now - res[p].get("at_isv", 0) > 20]
    if need and time.time() < deadline:
        fc_delivery_count(need)
    return res


def _fc_min_units(pid: str, name: str) -> int:
    """Units you must be able to order before a car counts as in stock:
    FC_MIN_ALERT_STOCK_TARGET for your 🎯 cars, FC_MIN_ALERT_STOCK for the rest."""
    nm = name or ""
    flagged = (str(pid) in FC_WATCH_IDS or _fc_is_marque(nm)
               or any(w in nm.lower() for w in WATCHLIST) or bool(hw_priority(nm)))
    return FC_MIN_ALERT_STOCK_TARGET if flagged else FC_MIN_ALERT_STOCK


def _fc_live_verdict(info: dict | None, on_list: bool = False, need: int | None = None) -> str | None:
    """What FirstCry says about a car right now, from its product page (CS =
    national stock), the delivery check's 0/1 for it (svc) and the units that
    can reach your pincode (isv):
      'ok'          `need` (FC_MIN_ALERT_STOCK, or the 🎯 minimum) or more
                    units you can order (min of page & local)
      'last unit'   fewer local units than that (reserved and released all day)
      'arriving'    local units, but the page isn't selling them yet (CS 0)
      'no delivery' stock, but none that can reach you (the SF90's 155)
      'sold out'    nothing anywhere
      'unconfirmed' the delivery check gave no count — nothing changes on that
      ('unlisted', v16.1: fewer than FC_SURE_UNITS units that FirstCry's
      in-stock list for your pincode doesn't show yet — set in fc_apply_live)
    None when the page wasn't read."""
    if not info or info.get("cs") is None:
        return None
    need = FC_MIN_ALERT_STOCK if need is None else need
    cs, svc, isv = info["cs"], info.get("svc"), info.get("isv")
    if svc == 0 or isv == 0:
        return "no delivery" if cs > 0 else "sold out"
    if isv is not None and isv > 0:
        if cs <= 0:
            return "arriving"
        return "ok" if min(cs, isv) >= need else "last unit"
    if cs <= 0:
        return "sold out"
    # no count: only cars the delivery check never answers for (sets, bikes…)
    # can still go by the in-stock list, as before
    if svc is None and on_list and cs >= need:
        return "ok"
    return "unconfirmed"


def _fc_target(pid: str, v: dict) -> bool:
    nm = (v or {}).get("name", "")
    # Hot Wheels only: old records of a "Jukku Resembling Ferrari SF90" pull-back
    # and Babyhug RC cars matched the marques and ate delivery checks every pass
    return bool(nm) and not _fc_excluded(nm) and bool(_FC_HW_NAME.search(nm)) and (
        pid in FC_WATCH_IDS or bool((v or {}).get("auto_watch")) or _fc_is_marque(nm)
        or bool(hw_priority(nm)))


def _fc_on_list(w, p: str, v, fc_max: int) -> bool:
    """The listing's word `w` ('list' / 'cat' / 'out') says the car is on sale
    for 248001: on FirstCry's in-stock list — or, for a car listed in the last
    FC_NEW_FRESH_H hours, in its catalogue with units (v16.3)."""
    if w == "list":
        return True
    if w != "cat":
        return False
    if not v:
        return str(p).isdigit() and int(p) > fc_max
    return _hours_since(v.get("first_seen", "")) < FC_NEW_FRESH_H


def _fc_poll_sets(prev_fc: dict, k: int, pass_idx: int = 0) -> list:
    """Product pages to read this pass for 🎯 cars that are out of stock: your
    hand-picked cars every pass, then one car per colour set from two
    rotations — sets with something going on (a car restocked in the last 3
    days, in stock now, or at the edge) and the rest.

    v15: the position in each rotation comes from the run number and the pass
    within the run, so consecutive passes read consecutive sets and every set
    comes round. The old wall-clock position skipped the same slots every
    minute (the gap between runs), so some sets were never read: 39 of 147 🎯
    cars in two days, the SF90 among them."""
    if k <= 0:
        return []
    picks = [p for p in FC_WATCH_IDS if (prev_fc.get(p) or {}).get("stock") != "in_stock"][:k]
    groups = {}
    for pid, v in prev_fc.items():
        if pid.isdigit():
            groups.setdefault(v.get("fc_gid") or pid, []).append(v)
    active = {g for g, vs in groups.items()
              if any(v.get("stock") == "in_stock" or v.get("fc_live") in ("arriving", "last unit", "unlisted")
                     or _hours_since(v.get("last_restock_alert", "")) < 72 for v in vs)}
    reps = {}
    for pid in sorted((p for p in prev_fc if p.isdigit()), key=int, reverse=True):
        v = prev_fc[pid]
        if v.get("stock") == "in_stock" or pid in picks or not _fc_target(pid, v):
            continue
        reps.setdefault(v.get("fc_gid") or (_FC_LIVE.get(pid) or {}).get("gid") or pid, pid)
    hot = [p for g, p in reps.items() if g in active]
    rest = [p for g, p in reps.items() if g not in active]
    rn = os.getenv("GITHUB_RUN_NUMBER", "")
    pos = (int(rn) if rn.isdigit() else int(time.time() // 60)) * 4 + pass_idx
    free = max(0, k - len(picks))
    n_hot = min(len(hot), (free + 1) // 2 if rest else free)
    n_rest = min(len(rest), free - n_hot)
    for pool, n in ((hot, n_hot), (rest, n_rest)):
        if pool and n:
            start = (pos * n) % len(pool)
            picks += [pool[(start + i) % len(pool)] for i in range(n)]
    return list(dict.fromkeys(picks))


def fc_apply_live(recs: list, prev_fc: dict, full: bool = False, list_ok: bool = True) -> list:
    """Make the product page + delivery check the final word on FirstCry stock.

    The listing (`recs`) only says where to look. A car whose listing state
    differs from what we stored is confirmed on its product page first; cars we
    believe in stock are re-checked against the delivery check every pass; a
    few 🎯 sets are read directly. Every car whose page was read this pass gets
    its state from the page. Returns the records to process (cars outside the
    listing that the page reads changed are added)."""
    if not FC_LIVE:
        return recs
    t0 = time.time()
    by = {r["id"][3:]: r for r in recs}
    # what the listing itself said, before any page verdict is applied
    word = {p: ("list" if r["stock"] == "in_stock" else "cat" if r.get("fc_cat_in") else "out")
            for p, r in by.items() if not r.get("fc_carried")}
    listed_in = {p for p, w in word.items() if w == "list"}
    for p in listed_in:
        if (prev_fc.get(p) or {}).get("fc_off"):
            by[p]["fc_off"] = ""       # back on the in-stock list: its off-list clock stops
    slot = int(time.time() // 60)
    # v17.4: when each car came onto FirstCry's in-stock list for 248001 (a car
    # listed in the last few hours: its catalogue) — a fresh release's alert
    # needn't wait for its product page (FC_FRESH_UNITS)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    fc_max0 = max([int(p) for p in prev_fc if p.isdigit()] or [0])
    # (the first run that keeps these times can't tell which cars only just
    # came on, so every car on the list then counts as "long since")
    tracking = any(v.get("fc_lst_seen") for v in prev_fc.values())
    for p, r in by.items():
        if r.get("fc_carried") or not _fc_on_list(word.get(p), p, prev_fc.get(p), fc_max0):
            continue
        v = prev_fc.get(p) or {}
        on, seen_at = v.get("fc_lst_on", ""), v.get("fc_lst_seen", "")
        if not tracking:
            on = on or "2000-01-01T00:00:00"
        elif not seen_at or _hours_since(seen_at) * 60 >= FC_FRESH_GAP_MIN:
            on = now_iso                   # on the list again after FC_FRESH_GAP_MIN off it (or ever)
        r["fc_lst_on"] = on
        r["fc_lst_seen"] = now_iso         # (kept to 15 min when saved)

    def claim(p):
        """What the listing says this pass: 'list' (on the in-stock list),
        'cat' (only the catalogue shows units), 'out', or None (no word)."""
        if p in word:
            return word[p]
        # absent from this pass's listing: only meaningful for cars we hold in stock
        v = prev_fc.get(p) or {}
        if v.get("stock") != "in_stock":
            return None
        # v16.3: a new car alerted on the catalogue's word (page still 0, not
        # on the in-stock list yet) keeps that word until the catalogue is read
        # again — or it would drop out at the next quick check and come back
        # as a second alert once the list caught up. The delivery check still
        # watches it every pass.
        if not full and v.get("fc_pb") and v.get("fc_lst") == "cat":
            return "cat"
        return "out"

    def wanted(p):
        nm = ((by.get(p) or prev_fc.get(p) or {}).get("name") or "")
        if not (p.isdigit() and nm) or _fc_excluded(nm):
            return False
        # outside the listing only Hot Wheels count (old records of other things
        # — a Babyhug RC car — turn up in the sets of Hot Wheels pages)
        return p in word or bool(_FC_HW_NAME.search(nm))

    cands, held, recheck = [], {}, set()
    # (stored entries for track sets etc. from before they were excluded never
    # reach an alert, so they must not use up page reads either)
    pool = {p for p in set(by) | {p for p, v in prev_fc.items() if v.get("stock") == "in_stock"}
            if wanted(p)}
    # cars the listing calls in stock first, 🎯 cars first, newest first: when a
    # wave is bigger than one pass's page reads, those are read first
    for p in sorted(pool, key=lambda p: ((by.get(p) or {}).get("stock") != "in_stock",
                                         not _fc_target(p, by.get(p) or prev_fc.get(p) or {}), -int(p))):
        v = prev_fc.get(p) or {}
        c = claim(p)
        if c is None or (c != "out") == (v.get("stock") == "in_stock"):
            continue
        # The listing disagrees with what we hold. A disagreement we already
        # checked (same listing word as at the last page read) is re-read every
        # FC_LIVE_RECHECK minutes; anything new is read now.
        if v.get("fc_live") and v.get("fc_lst") == c:
            if (slot + int(p)) % FC_LIVE_RECHECK:
                held[p] = v.get("stock") or "out_of_stock"
                continue
            recheck.add(p)                        # read before: news goes first
        cands.append(p)

    # The delivery check's 0/1 is cheap (40 cars a call) and moves the moment
    # units for your pincode appear or go. Every pass it covers the cars we hold
    # in stock, every 🎯 car, and every car at the edge; the first pass of a
    # run covers every car we track.
    first_call = _FC_RUN_PASS[0] == 0
    _FC_RUN_PASS[0] += 1
    hold_in = [p for p in pool if (prev_fc.get(p) or {}).get("stock") == "in_stock" or p in listed_in]
    edge = {p for p, v in prev_fc.items()
            if v.get("fc_live") in ("no delivery", "last unit", "arriving", "unconfirmed", "unlisted")
            and wanted(p)}
    tgt = {p for p, v in prev_fc.items() if p.isdigit() and v.get("stock") != "in_stock" and _fc_target(p, v)}
    sweep = set(hold_in) | edge | tgt
    if first_call:
        sweep |= {p for p in prev_fc if wanted(p)}
    svc_now = fc_delivery(sorted(sweep)) if sweep else {}
    flips, due = [], []
    for p in sorted(sweep, key=lambda p: (not _fc_target(p, prev_fc.get(p) or {}), -int(p))):
        sv = svc_now.get(p)
        if sv is None or p in cands:
            continue
        v = prev_fc.get(p) or {}
        if v.get("stock") == "in_stock":
            if sv == 0:
                flips.append(p)                   # can't be delivered here any more
            elif v.get("fc_live") == "last unit" and (slot + int(p)) % FC_LIVE_NEAR_RECHECK == 0:
                due.append(p)                     # is that last unit still there?
            elif v.get("fc_pb") and (slot + int(p)) % FC_LIVE_RECHECK == 0:
                due.append(p)                     # v16.3: alerted while its page said 0 — caught up?
        elif sv == 1:
            if str(v.get("fc_svc", "")) != "1":
                flips.append(p)                   # deliverable here since we last looked: read now
            elif (slot + int(p)) % (FC_LIVE_NEAR_RECHECK if v.get("fc_live") in ("arriving", "unlisted")
                                    else FC_LIVE_RECHECK) == 0:
                due.append(p)                     # known to sit at the edge: re-read now and then
    # changes first (🎯 cars first); routine re-reads only a few per pass, so
    # they can't crowd out a real change — and they take turns (🎯 cars get
    # half the slots), or the same few would take every slot while a car
    # further down the list waits for the listing (dry run 20 Oct: 4 of 12
    # 'arriving' cars were re-read every pass, the other 8 never)
    n_due = FC_LIVE_AUDIT + 1
    if len(due) > n_due:
        rn = os.getenv("GITHUB_RUN_NUMBER", "")
        pos = (int(rn) if rn.isdigit() else slot) * 4 + _FC_RUN_PASS[0] - 1
        mine = [p for p in due if _fc_target(p, prev_fc.get(p) or {})]
        rest = [p for p in due if p not in set(mine)]
        n_m = min(len(mine), (n_due + 1) // 2 if rest else n_due)
        n_r = min(len(rest), n_due - n_m)
        n_m = min(len(mine), n_due - n_r)
        pick = []
        for pool_, n in ((mine, n_m), (rest, n_r)):
            if pool_ and n:
                start = (pos * n) % len(pool_)
                pick += [pool_[(start + i) % len(pool_)] for i in range(n)]
        due = list(dict.fromkeys(pick))
    if FC_LIVE_DEBUG:
        print(f"  [FC-LIVE] listing {cands[:12]} | delivery flips {flips[:12]} | re-reads {due[:n_due]}")
    # Reading order when there are more changes than one pass reads: a possible
    # restock first (the listing or the delivery check turning yes for a car we
    # hold sold out), 🎯 cars first, newest first; then cars that may have gone;
    # then the routine re-reads. A 🎯 car the delivery check just turned yes for
    # — how the SF90 would have been caught — must not wait behind a wave of
    # listing changes.
    firsts = sorted(dict.fromkeys(cands + flips),
                    key=lambda p: ((prev_fc.get(p) or {}).get("stock") == "in_stock", p in recheck,
                                   not _fc_target(p, by.get(p) or prev_fc.get(p) or {}), -int(p)))
    cands = firsts + [p for p in due[:n_due] if p not in firsts]

    poll = _fc_poll_sets(prev_fc, FC_LIVE_POLL, _FC_RUN_PASS[0] - 1)
    order = list(dict.fromkeys(cands + poll))
    gids = {p: (prev_fc.get(p) or {}).get("fc_gid") for p in order if (prev_fc.get(p) or {}).get("fc_gid")}
    live = fc_live_check(order, gids=gids) if order else {}
    # in-stock cars never confirmed on a page (e.g. from before v14): a few sets a pass
    audit = [p for p in sorted(hold_in, key=int, reverse=True)
             if not (prev_fc.get(p) or {}).get("fc_live") and p not in live and p not in cands]
    if audit and FC_LIVE_AUDIT and time.time() - t0 < FC_LIVE_BUDGET / 2:
        live.update(fc_live_check(audit, max_pages=FC_LIVE_AUDIT))
    order += [p for p in audit if p in live]

    fc_max = max([int(p) for p in prev_fc if p.isdigit()] or [0])
    n_up = n_down = n_new = n_fail = n_wait = 0
    for p, r in list(by.items()):
        if p in held:
            r["stock"] = held[p]
            if held[p] != "in_stock":
                r["stock_count"] = None
    later = set()
    for p in cands:
        if p in live:
            continue
        if _FC_PAGE_TRIED.get(p, 0) >= t0 or _FC_LIVE_PAUSE[0] > time.time():
            n_fail += 1                            # its page couldn't be read: the listing's word stands
            continue
        # not read this pass only because other cars came first (a wave bigger
        # than one pass's page reads): the listing's word waits for the page,
        # next pass — a car announced unread can turn out not orderable at all
        n_wait += 1
        r, v = by.get(p), prev_fc.get(p)
        if r is None:
            continue
        if v and v.get("stock"):
            r["stock"] = v["stock"]
            if v["stock"] != "in_stock":
                r["stock_count"] = None
        elif not v and prev_fc and int(p) > fc_max:
            # a brand-new listing: announced once its page is read. (Older ids
            # new to us keep the listing's word, so a coverage burst still
            # arrives in one piece for the burst guard; the first run records
            # everything as is.)
            later.add(p)
    out = [r for r in recs if r["id"][3:] not in later]
    for p, info in live.items():
        verdict = _fc_live_verdict(info, on_list=p in listed_in, need=_fc_min_units(
            p, (by.get(p) or prev_fc.get(p) or {}).get("name") or info.get("pn") or ""))
        if verdict is None:
            continue
        v = prev_fc.get(p)
        r = by.get(p)
        if (r is None or r.get("fc_carried")) and v is not None and not wanted(p):
            continue
        if (verdict == "sold out" and v and v.get("fc_live") == "arriving"
                and info.get("svc") == 1 and info.get("isv") is None):
            # read as part of another car's set, not counted this pass: the page
            # still sells none, and its last count (units on their way) stands —
            # calling it 'sold out' would drop it from the re-reads
            verdict = "arriving"
        listed_n = None
        # listed in the last FC_NEW_FRESH_H hours (a brand-new id, or first seen then)
        fresh = ((v is None and p.isdigit() and int(p) > fc_max)
                 or (v is not None and _hours_since(v.get("first_seen", "")) < FC_NEW_FRESH_H))
        # since when units for you exist while the page says 0 ('' = not so now)
        arr = ""
        if verdict == "arriving":
            arr = (v or {}).get("fc_arr", "")
            if not arr:
                # just turned so — unless it already was before v16.3 kept the time
                was = (v or {}).get("fc_live") == "arriving" or (v or {}).get("stock") == "in_stock"
                arr = "2000-01-01T00:00:00" if was else time.strftime("%Y-%m-%dT%H:%M:%S")
        young = bool(arr) and _hours_since(arr) * 60 < FC_PAGE_LAG_MIN
        # FirstCry's in-stock list for 248001 has it — or, for a car listed in
        # the last few hours, its catalogue does (v16.3/16.4)
        on_list = claim(p) == "list" or (claim(p) == "cat" and fresh)
        # (v16.2-16.3 alerted while the product page still said 0, on the word
        # of FirstCry's lists or catalogue. v17.1: never — a page at 0 shows
        # "Notify me" instead of "Add to cart", and your Favourites say Out of
        # Stock too; 23 Oct 16:20 the Armored Batmobile alerted like that.)
        if verdict == "ok" and (v or {}).get("stock") != "in_stock" and FC_SURE_UNITS:
            cs_, isv_ = info.get("cs") or 0, info.get("isv")
            units = min(cs_, isv_) if isv_ is not None else cs_
            phantom = _hours_since((v or {}).get("fc_phantom", "")) < FC_PHANTOM_HOLD_H
            if not on_list:
                # v16.4: FirstCry's in-stock list for 248001 doesn't have it —
                # not yet, however many units the page counts across the country
                # (22 Oct: the AAR Cuda's 5). The catalogue doesn't vouch for an
                # older car either: it shows cars that list leaves out for days
                # (probe 21 Oct: four on every other pincode's list, not 248001's)
                verdict = "unlisted"
            elif phantom and units < FC_SURE_UNITS:
                # the same few units of a car that just turned out a phantom
                verdict = "unlisted"
            elif phantom and not ((v or {}).get("fc_live") == "unlisted"
                                  and str((v or {}).get("fc_svc", "")) == "1"):
                # v16.3: its last alert was gone within minutes, so this time a
                # second reading must agree first — 21 Oct 23:06 the Hellcat
                # could reach 248001 for 22 s, with 338 units across the country
                verdict = "unlisted"
        before = (v or {}).get("stock")
        if verdict == "ok":
            st = "in_stock"
        elif verdict == "unconfirmed" or (verdict == "last unit" and before == "in_stock"):
            # no count from the delivery check: no change. A car down to its
            # last local unit keeps its place until it's really gone, so it
            # can't flap in and out as that unit is reserved and released.
            st = before or "out_of_stock"
        else:
            st = "out_of_stock"
        # v16.4: held in stock, but off FirstCry's in-stock list for 248001 for
        # FC_OFFLIST_MIN minutes → out for you, whatever the page says (22 Oct the
        # AAR Cuda stayed "in" after the cart said it was gone, so its real
        # restock could never have alerted). Only counted while that list was
        # read in full.
        off = ""
        if FC_SURE_UNITS and before == "in_stock" and st == "in_stock" and not on_list:
            off = (v or {}).get("fc_off") or ""
            if list_ok:
                off = off or time.strftime("%Y-%m-%dT%H:%M:%S")
                if _hours_since(off) * 60 >= FC_OFFLIST_MIN:
                    st, verdict, off = "out_of_stock", "unlisted", ""
        if r is None:
            if v is None:
                nm = info.get("pn") or ""
                # a product page's set can include things that aren't Hot Wheels
                # at all (18 Oct: feeding bottles, steriliser parts)
                if not nm or _fc_excluded(nm) or not _FC_HW_NAME.search(nm):
                    continue
                mrp = info.get("mrp")
                dis = _fc_int(info.get("dis")) or 0
                price = int(round(mrp * (1 - dis / 100.0))) if mrp and 0 <= dis < 100 else mrp
                r = {"id": f"fc_{p}", "source": "firstcry", "name": nm + (" [PRE-ORDER]" if info.get("pre") else ""),
                     "url": f"https://www.firstcry.com/hot-wheels/{_fc_slug(nm)}/{p}/product-detail",
                     "price": f"₹{price}" if price else "", "mrp": f"₹{mrp}" if mrp and price and price < mrp else "",
                     "badge_new": False, "watched": p in FC_WATCH_IDS or _fc_is_marque(nm),
                     "auto_watch": _fc_is_marque(nm), "stock_ver": FC_API_STOCK_VER, "fc_trusted": True,
                     "fc_listed_at": "", "fc_api_seen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     # a car of a set we read that the listing never showed: tracked
                     # silently from now on, unless it is a genuinely new id
                     "fc_absorb": int(p) <= fc_max}
                n_new += 1
            else:
                sv = info.get("svc") if info.get("svc") is not None else svc_now.get(p)
                if (v.get("stock") == st
                        and v.get("fc_live") == (v.get("fc_live") if verdict == "unconfirmed" else verdict)
                        and v.get("fc_gid") == (info.get("gid") or v.get("fc_gid"))
                        and str(v.get("fc_svc", "")) == ("" if sv is None else str(sv))
                        and v.get("fc_lst", "") == (claim(p) or v.get("fc_lst", ""))
                        and (v.get("fc_off") or "") == off):
                    continue                       # nothing new for a car outside the listing
                # outside the listing only Hot Wheels count (an old record for a
                # Babyhug RC car turned up on a Hot Wheels page's set)
                if (not v.get("name") or _fc_excluded(v.get("name", ""))
                        or not _FC_HW_NAME.search(v.get("name", ""))):
                    continue
                r = {"id": f"fc_{p}", "source": "firstcry", "name": v.get("name", ""),
                     "url": v.get("url") or f"https://www.firstcry.com/x/x/{p}/product-detail",
                     "price": v.get("price", ""), "mrp": "", "badge_new": False,
                     "watched": p in FC_WATCH_IDS or _fc_is_marque(v.get("name", "")),
                     "auto_watch": _fc_is_marque(v.get("name", "")), "stock_ver": FC_API_STOCK_VER,
                     "fc_trusted": True, "fc_listed_at": v.get("fc_listed_at", ""),
                     "fc_api_seen_at": v.get("fc_api_seen_at", "")}
            out.append(r)
            by[p] = r
        # The first page reading of a car tracked from before v14, which the
        # listing isn't calling in stock, is a correction, not news: cars the
        # listing was hiding (on sale for hours) must not all fire "back in
        # stock" the first time their set is read. Later comebacks — and cars
        # first seen since v14 started — alert normally.
        if (st == "in_stock" and before != "in_stock" and v and not v.get("fc_live")
                and claim(p) not in ("list", "cat")
                and v.get("first_seen", "") < (_FC_LIVE_SINCE[0] or "0")):
            r["fc_first_read"] = True
        if verdict == "unconfirmed" and v and v.get("fc_live"):
            verdict = v["fc_live"]                 # no new word on delivery: keep the last one
        r["stock"] = st
        isv, cs = info.get("isv"), info.get("cs") or 0
        # the count you can actually get: page stock, capped by what can reach you
        r["stock_count"] = (min(cs, isv) if isv else cs) if st == "in_stock" else None
        if st == "in_stock" and not cs:
            r["stock_count"] = listed_n or isv or None      # no fresh count from the page
        r["fc_pb"] = ""
        r["fc_arr"] = arr
        r["fc_off"] = off
        r["fc_live"] = verdict
        sv = info.get("svc") if info.get("svc") is not None else svc_now.get(p)
        r["fc_svc"] = "" if sv is None else str(sv)
        r["fc_lst"] = claim(p) or (v or {}).get("fc_lst", "")
        r["fc_gid"] = info.get("gid") or (v or {}).get("fc_gid", "")
        r["fc_live_now"] = True
        # seen on its own page counts as seen: a car only the product pages show
        # must not age into "delisted" (and then come back as a false restock)
        r["fc_api_seen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        n_up += before != "in_stock" and st == "in_stock"
        n_down += before == "in_stock" and st != "in_stock"
    if FC_CART:
        out = _fc_cart_apply(out, prev_fc, word)
    if order or n_fail or n_wait:
        print(f"  [FC-LIVE] {len(cands)} to confirm, {len(poll)} 🎯 set(s) read, "
              f"{sum(1 for p in audit if p in live)} audited → "
              f"{len(live)} car(s) seen live in {time.time() - t0:.1f}s; "
              f"{n_up} now orderable, {n_down} not any more"
              + (f", {n_new} newly tracked" if n_new else "")
              + (f", {n_fail} unconfirmed (page not read)" if n_fail else "")
              + (f", {n_wait} waiting for their page" if n_wait else ""))
    return out


def _fc_cart_apply(out: list, prev_fc: dict, word: dict) -> list:
    """v17: FirstCry's checkout cart decides every FirstCry stock change (see
    FC_CART). Asks about the cars the signals point at plus a turn of the rest,
    and makes the records say what the cart says."""
    t0 = time.time()
    recs = {r["id"][3:]: r for r in out if r.get("source") == "firstcry" and str(r.get("id", "")).startswith("fc_")}

    def hw(v):
        nm = (v or {}).get("name") or ""
        return bool(nm) and not _fc_excluded(nm) and bool(_FC_HW_NAME.search(nm))

    # every stock change the signals propose (either way), and every car they
    # half point at: a few units off the list, a page still at 0, a last unit,
    # FirstCry's lists showing a car we hold sold out
    must = []
    proposed = {}
    for p, r in recs.items():
        if not p.isdigit() or r.get("fc_carried") or not hw(r):
            continue
        before = (prev_fc.get(p) or {}).get("stock")
        if r.get("stock") != before or (r.get("stock") != "in_stock" and (
                r.get("fc_live") in ("unlisted", "arriving", "last unit", "page 0") or word.get(p) in ("list", "cat"))):
            must.append(p)
            proposed[p] = r.get("stock")
    # in turn: cars held in stock (still buyable for you?), 🎯 cars, the rest
    pool = {p: v for p, v in prev_fc.items() if p.isdigit() and hw(v) and p not in proposed}
    held = sorted((p for p, v in pool.items() if v.get("stock") == "in_stock"), key=int)
    tgt = sorted((p for p, v in pool.items() if v.get("stock") != "in_stock" and _fc_target(p, v)), key=int)
    rest = sorted((p for p, v in pool.items() if v.get("stock") != "in_stock" and not _fc_target(p, v)), key=int)
    # v17.4: and every pass, the cars the cart said yes to while we hold them
    # sold out (their page or FirstCry's list is about to catch up)
    yes_before = [p for p, v in pool.items() if v.get("stock") != "in_stock" and v.get("fc_cart") == "y"]
    must += [p for p in yes_before if p not in must]
    free = max(0, FC_CART_MAX - len(must))
    want = [min(len(held), free // 4), min(len(tgt), free // 2), 0]
    want[2] = min(len(rest), free - want[0] - want[1])
    spare = free - sum(want)
    for i, pl in ((1, tgt), (0, held)):            # nothing left over unused
        extra = min(spare, len(pl) - want[i])
        want[i] += extra
        spare -= extra
    rn = os.getenv("GITHUB_RUN_NUMBER", "")
    pos = (int(rn) if rn.isdigit() else int(time.time() // 60)) * 4 + _FC_RUN_PASS[0]
    picks = []
    for pl, n in zip((held, tgt, rest), want):
        if pl and n:
            start = (pos * n) % len(pl)
            picks += [pl[(start + i) % len(pl)] for i in range(n)]
    ask = list(dict.fromkeys(must + picks))
    if not ask:
        return out
    res = fc_cart_check(ask)
    if res is None:
        res = {}
        print(f"  [FC-CART] the cart couldn't be asked ({len(ask)} cars) — the listing / page signals decide")
    # buyable = the cart can send it to you AND its product page sells it; a car
    # the cart would take but whose page wasn't read just now is read first
    now = time.time()

    def page_cs(p):
        e = _FC_LIVE.get(p) or {}
        return e.get("cs") if now - e.get("at_page", 0) <= FC_CART_PAGE_S else None

    slot = int(now // 60)
    fc_max = max([int(p) for p in prev_fc if p.isdigit()] or [0])

    def on_list(p):
        return _fc_on_list(word.get(p), p, prev_fc.get(p), fc_max)

    def batch(p, a):
        """v17.4: on FirstCry's in-stock list for 248001 with FC_FRESH_UNITS+
        units in the cart — buyable from your Profile even while its page says 0"""
        return bool(FC_FRESH_UNITS and a.get("ok") and (a.get("n") or 0) >= FC_FRESH_UNITS and on_list(p))

    def list_fresh(p):
        """…and it came onto that list in the last FC_FRESH_MIN minutes"""
        on = (recs.get(p) or {}).get("fc_lst_on") or (prev_fc.get(p) or {}).get("fc_lst_on", "")
        return bool(on) and _hours_since(on) * 60 < FC_FRESH_MIN

    # (a car already known to sit in the cart with its page at 0 is re-read every
    # FC_LIVE_RECHECK minutes, not every time the cart is asked — but every
    # time when it's a 🎯 car, on FirstCry's in-stock list, or has a batch in
    # the cart: those are about to go on sale)
    want = [p for p, a in res.items() if a.get("ok") and page_cs(p) is None
            and (prev_fc.get(p) or {}).get("stock") != "in_stock"
            and ((prev_fc.get(p) or {}).get("fc_live") != "page 0" or (slot + int(p)) % FC_LIVE_RECHECK == 0
                 or _fc_target(p, prev_fc.get(p) or {}) or on_list(p)
                 or (FC_FRESH_UNITS and (a.get("n") or 0) >= FC_FRESH_UNITS))]
    # v17.2: 🎯 cars first — 23 Oct the Custom Otto sat in the cart with its page
    # at 0 for 25 min, then sold its one unit 37 s after it went on sale
    want.sort(key=lambda p: not _fc_target(p, prev_fc.get(p) or {}))
    if want and _FC_LIVE_PAUSE[0] <= now:
        todo, covered = [], set()
        for p in want:
            if p not in covered:
                todo.append(p)
                covered.update((_FC_LIVE.get(p) or {}).get("members") or [p])
        todo = todo[:FC_LIVE_MAX]
        with ThreadPoolExecutor(max_workers=min(8, len(todo))) as ex:
            list(ex.map(fc_page, todo))
    n_yes = n_in = n_out = n_fix = n_page0 = n_wait = n_fast = n_short = 0
    for p in must:
        if p not in res:                           # not answered: the signals' word stands, flagged
            r = recs.get(p)
            if r is not None and r.get("stock") == "in_stock" and (prev_fc.get(p) or {}).get("stock") != "in_stock":
                r["fc_cart_unchecked"] = True
    for p, a in res.items():
        v = prev_fc.get(p) or {}
        before = v.get("stock")
        cart_ok = bool(a.get("ok"))
        cs_ = page_cs(p)
        fast = short = False
        if cart_ok and before != "in_stock":
            if batch(p, a) and list_fresh(p) and not (cs_ and cs_ > 0) and prev_fc:
                # v17.4: a fresh release — on sale for you before its page says so
                buy = fast = True
                n_fast += 1
            elif cs_ is None and prev_fc:
                # the cart would take it, its page wasn't read just now: decided
                # when it is (the listing's word doesn't stand in for it)
                r = recs.get(p)
                if r is not None and r.get("stock") == "in_stock":
                    r["stock"] = before or "out_of_stock"
                    r["stock_count"] = None
                n_wait += 1
                continue
            else:
                # coming in: the page must sell it (very first run: the listing's word)
                buy = bool(cs_ and cs_ > 0) if cs_ is not None else (recs.get(p) or {}).get("stock") == "in_stock"
                # v17.4: …with the units your settings ask for — FC_MIN_ALERT_STOCK
                # (2), one for your 🎯 cars. Since v17 the cart's say let single
                # units of any car through (25 Oct: a Track Ripper, "only 1 left").
                n_cart = a.get("n") or 0
                units = min(n_cart, cs_) if (n_cart and cs_) else (n_cart or cs_ or 0)
                nm_ = (recs.get(p) or v).get("name") or a.get("name") or ""
                if buy and prev_fc and units < _fc_min_units(p, nm_):
                    buy, short = False, True
        elif cart_ok:
            # held: out once a page reading says 0 — unless FirstCry's list still
            # has it with a batch in the cart (a fresh release whose page lags)
            buy = cs_ is None or cs_ > 0 or batch(p, a)
        else:
            buy = False
        n_page0 += cart_ok and not buy and not short
        n_short += short
        st = "in_stock" if buy else "out_of_stock"
        cart = "y" if cart_ok else "n"
        n_yes += buy
        r = recs.get(p)
        if r is None:
            if v.get("stock") == st and v.get("fc_cart") == cart:
                continue                           # nothing new
            if not hw(v):
                continue
            nm = v.get("name", "")
            r = {"id": f"fc_{p}", "source": "firstcry", "name": nm,
                 "url": v.get("url") or f"https://www.firstcry.com/hot-wheels/{_fc_slug(nm)}/{p}/product-detail",
                 "price": v.get("price", ""), "mrp": "", "badge_new": False,
                 "watched": p in FC_WATCH_IDS or _fc_is_marque(nm), "auto_watch": _fc_is_marque(nm),
                 "stock_ver": FC_API_STOCK_VER, "fc_trusted": True, "fc_listed_at": v.get("fc_listed_at", ""),
                 "fc_api_seen_at": v.get("fc_api_seen_at", "")}
            out.append(r)
            recs[p] = r
        r.pop("fc_carried", None)
        if v and before != st and not v.get("fc_cart") and proposed.get(p) != st and not r.get("fc_first_read"):
            # its first cart answer, and nothing else said so: a correction, not news
            r["fc_first_read"] = True
            n_fix += 1
        r["stock"] = st
        r["fc_cart"] = cart
        r.pop("fc_cart_unchecked", None)
        if buy:
            n = a.get("n") or 0
            if cs_:
                n = min(n, cs_) if n else cs_
            r["stock_count"] = n or None
            r["fc_cart_eta"] = _fc_eta(a.get("eta", ""))
            r["fc_live"] = "ok"
            r["fc_live_now"] = True
            try:
                price = float(a.get("price") or 0)
                mrp = float(a.get("mrp") or 0)
            except (TypeError, ValueError):
                price = mrp = 0
            if price > 0:
                r["price"] = f"₹{int(round(price))}"
                r["mrp"] = f"₹{int(round(mrp))}" if mrp > price + 0.5 else ""
            # "cart": in on the cart's and FirstCry's list's word while its page
            # still says 0 — the alert says how to buy it anyway
            if fast:
                r["fc_fast"] = True
            if cs_ is not None:
                r["fc_pb"] = "cart" if (fast or not cs_ or cs_ <= 0) else ""
            else:
                r["fc_pb"] = "cart" if (fast or v.get("fc_pb") == "cart") else ""
            n_in += before != "in_stock"
        else:
            r["stock_count"] = None
            r["fc_pb"] = ""
            if short:
                r["fc_live"] = "last unit"          # on sale, but fewer units than you asked for
            elif cart_ok:
                r["fc_live"] = "page 0"             # the cart has it, its page doesn't sell it (yet)
            elif r.get("fc_live") in ("ok", "page 0", None, ""):
                r["fc_live"] = "not in cart"
            n_out += before == "in_stock"
    print(f"  [FC-CART] {len(ask)} car(s) asked ({len(must)} pointed at, {len(ask) - len(must)} in turn) "
          f"in {time.time() - t0:.1f}s: {n_yes} buyable for {FC_PINCODE}; {n_in} now in, {n_out} now out"
          + (f", {n_page0} in the cart but not on sale on their page" if n_page0 else "")
          + (f", {n_fast} fresh release(s) in ahead of their page" if n_fast else "")
          + (f", {n_short} on sale with fewer units than you asked for" if n_short else "")
          + (f", {n_wait} waiting for their page" if n_wait else "")
          + (f", {n_fix} first answers applied quietly" if n_fix else ""))
    return out


def scrape_firstcry(prev_all: dict | None = None, full: bool = False) -> list[dict]:
    """FirstCry, read live (see the fresh-data notes above fc_api_catalogue).

    Every pass reads FirstCry's in-stock list (~10 pages). full=True (every
    FC_CATALOGUE_EVERY seconds) also reads the whole catalogue, sold-out cars
    included, so new listings and names/prices of sold-out cars stay known.

    WHAT COUNTS AS IN STOCK (v14): the listing only says where to look —
    fc_apply_live() confirms every change on the car's product page and
    FirstCry's delivery check for your pincode, and reads the pages of your 🎯
    cars directly (see the notes above fc_apply_live). If product pages can't
    be read, the listing's word is used as before: the in-stock list decides,
    and the catalogue can only confirm a sell-out.
    """
    if prev_all is None:
        prev_all = load_seen()
    prev_fc = {pid[3:]: v for pid, v in prev_all.items()
               if pid.startswith("fc_") and isinstance(v, dict)}

    if FC_USE_API:
        if FC_THROTTLED[0] > time.time() and not full:
            print("  [FC-API] paused for a few minutes — FirstCry answered 429/403")
            return []
        inst = fc_api_catalogue(hot=True)            # what you can actually buy
        inst_ok = inst is not None and FC_LAST_SWEEP["complete"]
        listed = {str(k) for k in (inst or {})}
        cat = fc_api_catalogue() if full else None   # everything, sold-out too
        if inst is not None or cat:
            recs = fc_api_records(inst or {}, prev_fc, quiet=True)
            got = {r["id"][3:] for r in recs}
            delisted = 0
            if cat:
                for r in fc_api_records({k: v for k, v in cat.items() if str(k) not in listed},
                                        prev_fc):
                    pid = r["id"][3:]
                    # Not on the in-stock list. If the catalogue also says sold
                    # out, it is. If the catalogue still shows units, the two
                    # disagree: keep what we knew. (The in-stock list drops cars
                    # for a few minutes whenever it refreshes; flipping them to
                    # sold out made them "come back" as false restock alerts.)
                    if r["stock"] == "in_stock":
                        r["fc_cat_in"] = True        # v14: worth a look on the product page
                        r["stock"] = (prev_fc.get(pid) or {}).get("stock") or "out_of_stock"
                    r["stock_count"] = None
                    recs.append(r)
                    got.add(pid)
                # cars missing from the catalogue: kept as they were, and only
                # treated as delisted after FC_STALE_H hours of absence
                now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
                for pid, v in prev_fc.items():
                    if pid in got or not pid.isdigit():
                        continue
                    nm = v.get("name", "")
                    if not nm or _fc_excluded(nm) or v.get("stock") is None:
                        continue
                    st = v.get("stock")
                    seen_at = v.get("fc_api_seen_at") or now_iso
                    if (st == "in_stock" and FC_API_COMPLETE[0]
                            and _hours_since(seen_at) >= FC_STALE_H):
                        st, delisted = "out_of_stock", delisted + 1
                    recs.append({
                        "id": f"fc_{pid}", "source": "firstcry", "name": nm,
                        "url": v.get("url") or f"https://www.firstcry.com/x/x/{pid}/product-detail",
                        "price": v.get("price", ""), "mrp": "", "stock": st,
                        "badge_new": False, "watched": pid in FC_WATCH_IDS or _fc_is_marque(nm),
                        "auto_watch": _fc_is_marque(nm),
                        # carried cars keep exactly the version/trust they had
                        "stock_ver": v.get("stock_ver", ""),
                        "fc_trusted": bool(v.get("fc_trusted")),
                        "fc_listed_at": v.get("fc_listed_at", ""),
                        "fc_api_seen_at": seen_at,
                        "fc_carried": True,          # not in the listing this time
                    })
                    got.add(pid)
            # v13.1.1: a car missing from the in-stock list is NOT marked sold
            # out on that alone (18 Oct: Street Wiener, 222 units, vanished from
            # the list for 5 minutes and came back as a false "back in stock").
            # It goes sold out when the list shows it below FC_MIN_ALERT_STOCK,
            # when the catalogue agrees it's gone, or after FC_STALE_H hours away.
            FC_LAST_MODE[0] = "api"
            try:
                recs = fc_apply_live(recs, prev_fc, full, list_ok=inst_ok)
            except Exception:
                print(f"  [FC-LIVE] live check failed — listing used as is:\n{traceback.format_exc()}")
            if full:
                ins = sum(1 for r in recs if r["stock"] == "in_stock")
                print(f"[*] FirstCry total (API): {len(recs)} tracked, {ins} buyable now "
                      f"(in-stock list {'complete' if inst_ok else 'INCOMPLETE'}), "
                      f"{delisted} aged to delisted")
            return recs
        if not full:
            return []
        print("  [FC] API unavailable this run — falling back to HTML listing scrape")
    FC_LAST_MODE[0] = "html"

    seen_now: dict = {}

    def fetch(url):
        for _ in range(2):
            try:
                r = http.get(_fc_bust(url), headers={**COMMON_HEADERS, **_FC_NOCACHE},
                             timeout=TIMEOUT, **_IMPERSONATE)
                if r.status_code == 200 and len(r.text) > 5000:
                    return r.text
            except Exception:
                pass
            time.sleep(1.5)
        return None

    # pick this run's URL set: core + a rotating slice
    if _FC_ENV_URLS:
        run_urls = _FC_ENV_URLS
    else:
        meta = prev_all.get("_meta", {}) if isinstance(prev_all.get("_meta"), dict) else {}
        off = int(meta.get("fc_offset", 0)) % max(1, len(_FC_ROTATE_URLS))
        n = max(0, FC_ROTATE_PER_RUN)
        slice_ = [_FC_ROTATE_URLS[(off + i) % len(_FC_ROTATE_URLS)] for i in range(n)]
        run_urls = _FC_CORE_URLS + slice_
        _FC_NEXT_OFFSET[0] = off + n
        print(f"  [FC] window {off}-{off+n} of {len(_FC_ROTATE_URLS)} rotating "
              f"(+{len(_FC_CORE_URLS)} core)")

    with ThreadPoolExecutor(max_workers=FC_WORKERS) as ex:
        pages = {ex.submit(fetch, u): u for u in run_urls}
        for fut in as_completed(pages):
            url = pages[fut]
            try:
                page = fut.result()
            except Exception:
                page = None
            if not page:
                print(f"  [FC] ✗ {url[-48:]}")
                continue

            marks = [(m.start(), m.group(1), _fc_name(m.group(2)))
                     for m in _FC_IMG.finditer(page)]
            marks += [(m.start(), m.group(2), _fc_name(m.group(1)))
                      for m in _FC_IMG_ALT.finditer(page)]
            marks.sort()

            added = 0
            for i, (pos, pid, nm) in enumerate(marks):
                if not nm or _fc_excluded(nm):
                    continue
                # searches can return other brands — keep Hot Wheels only
                if "searchstring=" in url and "hot wheel" not in nm.lower():
                    continue
                end = marks[i + 1][0] if i + 1 < len(marks) else min(len(page), pos + 6000)
                region = page[pos:end]
                price, mrp, stock = _fc_card_stock_price(region, nm)
                rec = {"name": nm, "price": price, "mrp": mrp, "stock": stock,
                       "url": _fc_real_url(page[max(0, pos - 2500):end], pid)}
                cur = seen_now.get(pid)
                if cur is None:
                    seen_now[pid] = rec
                    added += 1
                elif cur.get("stock") is None and stock:
                    seen_now[pid] = rec

            for m in _FC_FOOTER_LINK.finditer(page):
                pid, nm = m.group(1), _fc_name(m.group(2))
                if nm and not _fc_excluded(nm) and pid not in seen_now:
                    seen_now[pid] = {"name": nm, "price": None, "mrp": None,
                                     "stock": None, "url": None}
                    added += 1
            # Only trust the item count from the Hot Wheels BRAND pages. Search
            # pages report their own (much larger) result totals — that's where
            # the nonsense "covering 288/5051" came from.
            if "searchstring=" not in url and "/113" in url:
                m = re.search(r"\(\s*(\d{2,5})\s*Items?\s*\)", page, re.I)
                if m:
                    c = int(m.group(1))
                    if 50 <= c <= 3000:
                        _FC_SITE_COUNT[0] = max(_FC_SITE_COUNT[0], c)
            tag = "search" if "searchstring=" in url else "list"
            print(f"  [FC] +{added:3d} ({len(seen_now)} total) [{tag}] {url[-46:]}")

    # Watched products get a direct per-product check via search, so a wishlist
    # restock is caught even when the item appears on no category listing.
    # Priority set = your explicit FC_WATCH ids + every marque match we've ever
    # recorded. Sold-out ones come first (a restock is the thing we can only
    # catch here); then the stalest. Capped so the request budget stays sane.
    auto = [pid for pid, v in prev_fc.items()
            if v.get("auto_watch") or _fc_is_marque(v.get("name", ""))]
    auto.sort(key=lambda p: (
        0 if prev_fc.get(p, {}).get("stock") == "out_of_stock" else 1,
        prev_fc.get(p, {}).get("last_seen", "")))
    # Items already resolved with a definite stock state on this run's listing
    # sweep don't need a second lookup — skip them so the budget goes to the
    # ones only a direct search can answer (typically the sold-out ones).
    already = {p for p, v in seen_now.items() if v.get("stock")}
    cand = [p for p in dict.fromkeys(list(FC_WATCH_IDS) + auto)
            if p not in already or p in FC_WATCH_IDS]
    priority = cand[:FC_WATCH_MAX]
    if priority:
        n_auto = len([p for p in priority if p not in FC_WATCH_IDS])
        print(f"  [FC] priority: {len(priority)} ({len(FC_WATCH_IDS & set(priority))} "
              f"manual + {n_auto} auto-watch by marque)")
    for pid, info in fc_check_watched(prev_fc, priority).items():
        seen_now[pid] = info

    if not seen_now:
        print("[*] FirstCry: nothing parsed (blocked?)")
        return []

    # carry forward everything previously known (and anything you're watching)
    for pid in FC_WATCH_IDS:
        if pid not in seen_now and pid not in prev_fc:
            seen_now[pid] = {"name": f"Watched product {pid}", "price": None,
                             "mrp": None, "stock": None,
                             "url": FC_WATCH_URLS.get(pid)}
    for pid, v in prev_fc.items():
        if pid.isdigit() and pid not in seen_now:
            nm = v.get("name", "")
            if nm and not _fc_excluded(nm) and "'+'" not in nm:
                seen_now[pid] = {"name": nm, "price": price_to_int(v.get("price")),
                                 "mrp": None, "stock": None, "url": v.get("url")}

    out, unknown, aged = [], 0, 0
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    for pid, v in seen_now.items():
        prevrow = prev_fc.get(pid, {})
        # "observed" = we actually read this card's stock on a page this run.
        # Carried-forward entries and footer links arrive with stock=None.
        observed = v["stock"] is not None
        stock = v["stock"] or prevrow.get("stock")
        if stock is None:
            unknown += 1          # never guess — avoids phantom sold-out alerts
            continue
        # THE CORE FIX. On FirstCry a sold-out car usually just drops out of the
        # listings instead of showing "sold out". Previously that meant we kept
        # its last state ("in stock") forever, so when it came back there was no
        # sold-out -> in-stock transition and the restock alert could never fire.
        # Now: if a car we believed in stock hasn't been seen on ANY of the 78
        # rotating windows for FC_STALE_H hours (several full sweeps), we record
        # it as sold out. When it reappears, that's a genuine restock and alerts
        # (after the fresh-request confirmation step).
        listed_at = now_iso if observed else (prevrow.get("fc_listed_at") or now_iso)
        if (not observed and stock == "in_stock"
                and _hours_since(listed_at) >= FC_STALE_H):
            stock = "out_of_stock"
            aged += 1
        price = v["price"] if v["price"] else price_to_int(prevrow.get("price"))
        out.append({
            "id": f"fc_{pid}", "source": "firstcry", "name": v["name"],
            "url": v.get("url") or prevrow.get("url")
                   or f"https://www.firstcry.com/x/x/{pid}/product-detail",
            "price": f"₹{price}" if price else "",
            "mrp": f"₹{v['mrp']}" if v["mrp"] else "",
            "stock": stock,
            "badge_new": False,
            "watched": pid in FC_WATCH_IDS or _fc_is_marque(v["name"]),
            "auto_watch": _fc_is_marque(v["name"]),
            "stock_ver": "fc_listing_v3",
            "fc_trusted": False,
            "fc_listed_at": listed_at,
        })
    ins = sum(1 for d in out if d["stock"] == "in_stock")
    cov = (f", covering {len(out)}/{_FC_SITE_COUNT[0]} of catalogue"
           if _FC_SITE_COUNT[0] else "")
    read_now = sum(1 for v in seen_now.values() if v.get("stock") is not None)
    print(f"[*] FirstCry total: {len(out)} ({ins} in stock, {read_now} read live "
          f"this run, {aged} aged to sold-out, {unknown} unknown{cov})")
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# SOURCE 2 — Minifygram  (Supabase REST — authoritative, real-time stock)
# ══════════════════════════════════════════════════════════════════════════════════
# Minifygram is a Lovable app whose data lives in this Supabase project. The REST
# endpoint runs on Supabase's own infra — NOT behind Minifygram's Cloudflare — so
# it's reachable directly with the site's own public anon key.
#
# v4.4 breakthrough: captured a HAR of minifygram.com's own network traffic and
# found the EXACT query their front-end uses to check stock. Stock lives in a
# separate `product_skus` table (field `available`, >0 = in stock), and their own
# code fetches it EMBEDDED inside the products query via PostgREST's foreign-table
# syntax:
#     products?select=...,product_skus!product_skus_product_id_fkey(available)
# One API call now returns all ~170+ Hot Wheels with their REAL stock. This
# replaces every earlier guess (sold_out column, page-scraping meta tags, blind
# SKU-table probing) — all of which were wrong or unreliable. This is the same
# data Minifygram's own website reads to decide whether to show "Add to cart" or
# "Sold out".
MINIFYGRAM_SUPABASE = "https://seoqlgtbygddyehugjwv.supabase.co"

# Public anon key, captured directly from a live request Minifygram's own site
# made to its API. This is a client-side key by design (it ships in their
# browser JS to every visitor) — safe to embed, grants nothing beyond what any
# site visitor already has. Override with the MINIFYGRAM_ANON_KEY repo secret
# if Minifygram ever rotates it (bot will log a clear auth error if so).
_MINIFYGRAM_ANON_KEY_DEFAULT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNlb3FsZ3RieWdkZHllaHVnand2Iiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3NzcxMzEwNzgsImV4cCI6MjA5MjcwNzA3OH0."
    "TxGeE5sXW2zivw6xhJ7TIAWibGxiPzv4wcmaEihUsqY"
)
MINIFYGRAM_ANON_KEY = os.getenv("MINIFYGRAM_ANON_KEY", "").strip() or _MINIFYGRAM_ANON_KEY_DEFAULT

_SB_KEY_RE = re.compile(r'(eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,})')


def _looks_like_anon(jwt: str) -> bool:
    """Cheap check that a JWT is a Supabase anon key (role:anon in the payload)."""
    try:
        import base64
        payload = jwt.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("role") == "anon" or data.get("iss") == "supabase"
    except Exception:
        return False


def _discover_anon_key_from_bundle() -> str | None:
    """Last-resort fallback: mine the site's JS for a fresh anon key.

    Only used if the hardcoded/secret key stops working (Minifygram rotated
    it). Not needed in the normal case, since anon keys are long-lived.
    """
    try:
        idx = http.get("https://minifygram.com/", headers=COMMON_HEADERS,
                       timeout=TIMEOUT, **_IMPERSONATE)
    except Exception as e:
        print(f"  [MG] index fetch failed: {e}")
        return None
    shell = idx.text
    assets = re.findall(r'(?:src|href)="([^"]+\.js)"', shell)
    assets = [urljoin("https://minifygram.com/", a) for a in assets]
    for src in [None] + assets[:12]:
        try:
            text = shell if src is None else http.get(
                src, headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE).text
        except Exception:
            continue
        for m in _SB_KEY_RE.finditer(text):
            if _looks_like_anon(m.group(1)):
                return m.group(1)
    return None


def _mg_headers(key: str) -> dict:
    return {**COMMON_HEADERS, "apikey": key,
            "Authorization": f"Bearer {key}", "Accept": "application/json"}


# The exact fields Minifygram's own site requests, plus the embedded stock join.
_MG_SELECT = (
    "id,slug,name,brand,scale,category,price_inr,mrp_inr,product_type,"
    "badge,is_active,updated_at,preorder_status,preorder_close_at,"
    "product_skus!product_skus_product_id_fkey(available)"
)
# Older column set, used automatically if the pre-order columns ever disappear.
_MG_SELECT_BASIC = (
    "id,slug,name,brand,scale,category,price_inr,mrp_inr,product_type,"
    "badge,is_active,updated_at,"
    "product_skus!product_skus_product_id_fkey(available)"
)

# What to track. Brands are matched as tokens against brand + name (spaces and
# hyphens ignored); categories are matched against Minifygram's category name,
# whatever the brand. Default: Hot Wheels + MiniGT (incl. Kaido House) diecast,
# plus the "Trading Cards (TCG)" category.
MG_BRANDS = [t.strip().lower().replace(" ", "").replace("-", "")
             for t in os.getenv("MG_BRANDS", "hotwheels,mattel,minigt,mini gt,kaido house").split(",")
             if t.strip()]
MG_CATEGORIES = [t.strip().lower() for t in os.getenv("MG_CATEGORIES", "trading card,tcg").split(",")
                 if t.strip()]
# Brand matches only count in these categories, so "Hotwheels Stand" 3D-printed
# display stands and keychains don't show up as cars.
MG_CAR_CATEGORIES = [t.strip().lower() for t in os.getenv("MG_CAR_CATEGORIES", "diecast,pre-order").split(",")
                     if t.strip()]


def _mg_wanted(row: dict) -> str | None:
    """'car', 'card' or None for a Minifygram product row."""
    cat = str(row.get("category") or "").lower()
    if MG_CATEGORIES and any(t in cat for t in MG_CATEGORIES):
        return "card"
    brand = str(row.get("brand") or "").lower().replace(" ", "").replace("-", "")
    name = str(row.get("name") or "").lower().replace(" ", "").replace("-", "")
    car_cat = not cat or not MG_CAR_CATEGORIES or any(t in cat for t in MG_CAR_CATEGORIES)
    if any(tok in brand or tok in name for tok in MG_BRANDS):
        if car_cat:
            return "car"
    # v17.3: a Matchbox / Majorette chase piece — its badge or name says so
    if CHASE_ONLY_LINES and car_cat and _mg_line(row) and _mg_chase(row):
        return "car"
    return None


def _mg_line(row: dict):
    """'MATCHBOX' / 'MAJORETTE' for a Minifygram row of a chase-only brand."""
    cl = chase_line(f"{row.get('brand') or ''} {row.get('name') or ''}")
    return cl if cl in ("MATCHBOX", "MAJORETTE") else None


def _mg_chase(row: dict):
    """The chase kind Minifygram gives a row — by its badge ("Treasure Hunt",
    "Chase", "Super Chase"; not "Chance of Chase") or its name — else None."""
    kinds = [chase_kind(str(row.get(k) or "")) for k in ("badge", "name")]
    kinds = [k for k in kinds if k]
    return max(kinds, key=lambda k: _CHASE_RANK[k]) if kinds else None


def _mg_preorder_open(row: dict) -> bool:
    """A pre-order can be booked: not closed by status or by its closing time."""
    st = str(row.get("preorder_status") or "").lower()
    if st in ("booking_closed", "closed", "cancelled", "canceled"):
        return False
    close = str(row.get("preorder_close_at") or "")
    if close:
        try:
            ts = calendar.timegm(time.strptime(close[:19], "%Y-%m-%dT%H:%M:%S"))  # UTC
            if ts < time.time():
                return False
        except Exception:
            pass
    return True


def _mg_or_filter() -> str:
    """Server-side pre-filter (PostgREST or=) so Minifygram sends only the rows
    we might track — half the payload. The exact rules are still applied in
    _mg_wanted(); this only has to be a superset of them."""
    pats = {"*hot*wheel*", "*mini*gt*", "*kaido*", "*mattel*"}
    if CHASE_ONLY_LINES:
        pats |= {"*matchbox*", "*majorette*"}       # v17.3: for their chase pieces
    for raw in os.getenv("MG_BRANDS", "").split(","):
        t = re.sub(r"[^a-z0-9 ]", "", raw.strip().lower())
        if t:
            pats.add("*" + "*".join(t.split()) + "*")
    conds = [f"{col}.ilike.{p}" for p in sorted(pats) for col in ("brand", "name")]
    for raw in MG_CATEGORIES:
        t = re.sub(r"[^a-z0-9 ]", "", raw)
        if t:
            conds.append("category.ilike.*" + "*".join(t.split()) + "*")
    return "or=(" + ",".join(conds) + ")"


_MG_LAST_WM = [None]   # newest updated_at among the rows of the last full fetch


def mg_watermark() -> str | None:
    """Newest 'updated_at' among the products we track — one tiny request.
    Minifygram bumps it whenever a product is added or edited (a new listing,
    a restock entered by the shop, a price change), so checking it every pass
    and fetching the full list only when it moves catches new arrivals within
    seconds without re-downloading the catalogue every time."""
    url = (f"{MINIFYGRAM_SUPABASE}/rest/v1/products?select=updated_at"
           f"&is_active=eq.true&{_mg_or_filter()}&order=updated_at.desc&limit=1")
    try:
        r = http.get(url, headers=_mg_headers(MINIFYGRAM_ANON_KEY), timeout=15, **_IMPERSONATE)
        if r.status_code != 200:
            return None
        rows = r.json()
        return str(rows[0].get("updated_at") or "") if rows else ""
    except Exception:
        return None


def scrape_minifygram() -> list[dict]:
    key = MINIFYGRAM_ANON_KEY
    headers = _mg_headers(key)

    def products_url(select, filtered=True):
        return (f"{MINIFYGRAM_SUPABASE}/rest/v1/products"
                f"?select={quote(select, safe=',!()')}&is_active=eq.true&limit=2000"
                + (f"&{_mg_or_filter()}" if filtered else ""))

    try:
        # a rejected filter or column (HTTP 400) steps down to a plainer query
        for url in (products_url(_MG_SELECT), products_url(_MG_SELECT, filtered=False),
                    products_url(_MG_SELECT_BASIC, filtered=False)):
            r = http.get(url, headers=headers, timeout=TIMEOUT, **_IMPERSONATE)
            if r.status_code != 400:
                break
    except Exception as e:
        print(f"  [MG] request failed: {e}")
        return []

    if r.status_code in (401, 403):
        # Key rotated? Try to mine a fresh one once, then give up cleanly.
        print(f"  [MG] auth failed (HTTP {r.status_code}) — key may have rotated. "
              f"Trying to re-discover…")
        fresh = _discover_anon_key_from_bundle()
        if fresh and fresh != key:
            headers = _mg_headers(fresh)
            try:
                r = http.get(url, headers=headers, timeout=TIMEOUT, **_IMPERSONATE)
            except Exception as e:
                print(f"  [MG] retry failed: {e}")
                return []
        if r.status_code in (401, 403):
            print("  [MG] still unauthorized. Set MINIFYGRAM_ANON_KEY repo secret "
                  "with a fresh key — the built-in one is stale.")
            return []

    if r.status_code != 200:
        print(f"  [MG] products query → HTTP {r.status_code}: {r.text[:200]}")
        return []

    try:
        rows = r.json()
    except Exception as e:
        print(f"  [MG] bad JSON response: {e}")
        return []

    if not isinstance(rows, list):
        print(f"  [MG] unexpected response shape: {type(rows)}")
        return []
    _MG_LAST_WM[0] = max((str(x.get("updated_at") or "") for x in rows), default="") or None

    out = []
    no_sku_count = cards = pre = 0
    for row in rows:
        rid   = row.get("id")
        name  = row.get("name")
        slug  = row.get("slug") or rid
        if not (rid and name):
            continue
        kind = _mg_wanted(row)
        if not kind:
            continue

        # ── Authoritative stock: product_skus[].available, summed ──────────────
        skus = row.get("product_skus") or []
        if skus:
            total_available = sum(
                (s.get("available") or 0) for s in skus if isinstance(s, dict))
            in_stock = total_available > 0
        else:
            no_sku_count += 1
            total_available = None
            in_stock = str(row.get("product_type") or "").lower() == "in-stock"

        label = str(name)[:170]
        if _mg_line(row) and not _mg_line({"name": label}):
            # "Volkswagen Beetle" by Matchbox → "Matchbox Volkswagen Beetle"
            label = f"{str(row.get('brand') or '').strip()} {label}"[:170]
        # v17.3: Minifygram's badge says Treasure Hunt / Chase where the name
        # doesn't ("2 Jet Z", badge "Treasure Hunt") — the name carries it now
        label += chase_tag(str(row.get("badge") or ""), label)
        is_pre = str(row.get("product_type") or "").lower() == "preorder"
        if is_pre:
            pre += 1
            if str(row.get("preorder_status") or "").lower() != "stock_arrived":
                # bookable = units left AND booking still open
                in_stock = in_stock and _mg_preorder_open(row)
                label += " [PRE-ORDER]"
        if kind == "card":
            cards += 1
            label = "🃏 " + label

        price = price_to_int(row.get("price_inr"))
        mrp   = price_to_int(row.get("mrp_inr"))

        out.append({
            "id": f"mg_{rid}", "source": "minifygram", "name": label,
            "url": f"https://minifygram.com/product/{slug}",
            "price": f"₹{price}" if price else "",
            "mrp":   f"₹{mrp}"   if mrp and mrp != price else "",
            "stock": "in_stock" if in_stock else "out_of_stock",
            "stock_count": (total_available if isinstance(total_available, int)
                            and 0 < total_available <= FC_LOW_STOCK else None),
            "badge_new": bool(row.get("badge")),
            "mg_updated_at": str(row.get("updated_at") or ""),
            # Same tag as before on purpose: v13's rule changes (closed
            # pre-orders count as unavailable, trading cards added) can only
            # turn a car unavailable or add new ones — never cause a false
            # restock — and changing the tag would silence real restocks of
            # cars that are inactive right now.
            "stock_ver": "mg_skus_v1",
        })

    if no_sku_count:
        print(f"  [MG] {no_sku_count} products had no SKU row — used product_type fallback")

    ins = sum(1 for d in out if d["stock"] == "in_stock")
    print(f"[*] Minifygram total: {len(out)} of {len(rows)} ({ins} in stock; "
          f"{cards} trading cards, {pre} pre-orders)")
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# SOURCE 3 — Hamleys  (sitemap catalog discovery + SSR product-page stock)
# ══════════════════════════════════════════════════════════════════════════════════
# hamleys.in (Fynd platform) server-renders its listing page but only the first
# 12 cards, and strips page/sort params server-side (verified live) — so the
# listing alone can never see all ~46 Hot Wheels products. Architecture:
#   1. CATALOG: discover every /product/ URL with "hot-wheels" in the slug from
#      the sitemap (complete — includes items the listing hides), plus the
#      listing's top-12, plus anything we've ever seen before (seen.json).
#   2. STOCK:  items visible on the listing render with Add-to-bag → in stock.
#      Everything else gets its own SSR product page checked on a rotating
#      budget (HM_VERIFY_BUDGET per run, never-checked first, then stalest).
#   3. Optional fast path: Fynd's catalog JSON API with a cookie session —
#      if this store has it open, one call replaces all page checks.
HM_VERIFY_BUDGET = int(os.getenv("HM_VERIFY_BUDGET", "12"))
_HM_CARD = re.compile(r'href="(/product/[^"]+)"', re.I)


def _hm_session():
    try:
        return http.Session(**_IMPERSONATE) if _IMPERSONATE else http.Session()
    except Exception:
        return None


_HM_CREDS = [None]          # cached per process: (token, application_id)
_HM_TOKEN_RE = re.compile(
    r'["\'](?:x-fp-api-key|applicationToken|api_key|apiKey)["\']\s*[:=]\s*["\']([A-Za-z0-9_\-]{16,64})["\']')
_HM_APPID_RE = re.compile(r'applications/([0-9a-f]{24})')


def _hm_app_creds(sess):
    """Public Fynd application token + id, mined from hamleys.in's own assets."""
    if _HM_CREDS[0] is not None:
        return _HM_CREDS[0]
    tok = app_id = None

    def _g(u):
        return (sess.get(u, headers=COMMON_HEADERS, timeout=TIMEOUT) if sess
                else http.get(u, headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE))
    try:
        r = _g("https://hamleys.in/brand/hot-wheels")
        shell = r.text if r.status_code == 200 else ""
    except Exception:
        shell = ""
    blobs = [shell]
    for m in list(re.finditer(r'(?:src|href)="([^"]+\.js)"', shell))[:10]:
        u = urljoin("https://hamleys.in/", m.group(1))
        try:
            blobs.append(_g(u).text)
        except Exception:
            pass
    for b in blobs:
        if not b:
            continue
        if app_id is None:
            ma = _HM_APPID_RE.search(b)
            if ma:
                app_id = ma.group(1)
        if tok is None:
            mt = _HM_TOKEN_RE.search(b)
            if mt:
                tok = mt.group(1)
        if tok and app_id:
            break
    if tok or app_id:
        print(f"  [HM] creds: token={'yes' if tok else 'no'} app_id={app_id or 'no'}")
    _HM_CREDS[0] = (tok, app_id)
    return _HM_CREDS[0]


def _hamleys_api(sess) -> list[dict] | None:
    """Fynd application catalog API — the real source behind hamleys.in.

    hamleys.in/brand/hot-wheels renders NO products server-side (the grid is
    JS-loaded); its JS calls Fynd's public storefront API, so we call the same
    endpoint. Fynd uses CURSOR pagination (page_id=* then page.next_id) — the
    earlier ?brand=&page_no= guess was the wrong shape and always returned
    nothing, which is why this source went silent.
    """
    # Fynd storefront APIs are authenticated with the site's PUBLIC application
    # token (x-fp-api-key) — the same one their own browser JS sends. Without it
    # every call returns HTTP 401, which is exactly what the logs showed. We mine
    # it from the site once per run, alongside the application id that appears in
    # their CDN asset paths (.../applications/<24-hex>/...).
    tok, app_id = _hm_app_creds(sess)
    headers = {**COMMON_HEADERS, "Accept": "application/json, text/plain, */*",
               "x-currency-code": "INR", "Referer": "https://hamleys.in/brand/hot-wheels"}
    if tok:
        headers["x-fp-api-key"] = tok
    if app_id:
        headers["x-application-id"] = app_id

    def _g(u):
        return (sess.get(u, headers=headers, timeout=TIMEOUT) if sess
                else http.get(u, headers=headers, timeout=TIMEOUT, **_IMPERSONATE))

    base = "https://hamleys.in/api/service/application/catalog/v1.0/products/"
    shapes = [
        base + "?f=brand%3Ahot-wheels&filters=false&page_size=100&page_id={pid}",
        base + "?q=hot%20wheels&filters=false&page_size=100&page_id={pid}",
        base + "?f=brand%3Ahotwheels&filters=false&page_size=100&page_id={pid}",
    ]
    for shape in shapes:
        out, pid, pages, ok = [], "*", 0, False
        while pages < 8:
            try:
                r = _g(shape.format(pid=quote(pid, safe="*")))
            except Exception as e:
                print(f"  [HM] api {type(e).__name__}"); break
            if r.status_code != 200:
                print(f"  [HM] api → HTTP {r.status_code}"); break
            try:
                data = r.json()
            except Exception:
                break
            ok = True
            items = data.get("items") or []
            if not items:
                break
            for it in items:
                slug = it.get("slug") or ""
                name = it.get("name") or ""
                if not (slug and name):
                    continue
                nl = name.lower().replace(" ", "")
                brand = str((it.get("brand") or {}).get("name", "")).lower().replace(" ", "")
                if "hotwheels" not in nl and "hotwheels" not in brand:
                    continue
                price = None
                pr = it.get("price") or {}
                for k in ("effective", "marked"):
                    v = pr.get(k) or {}
                    price = price or price_to_int(v.get("min") or v.get("max"))
                sellable = it.get("sellable")
                out.append({
                    "id": f"hm_{slug}", "source": "hamleys", "name": str(name)[:180],
                    "url": f"https://hamleys.in/product/{slug}",
                    "price": f"₹{price}" if price else "", "mrp": "",
                    "stock": "in_stock" if (sellable is None or sellable) else "out_of_stock",
                    "badge_new": False, "stock_ver": "hm_api_v2"})
            page = data.get("page") or {}
            nxt = page.get("next_id")
            if not (page.get("has_next") and nxt):
                break
            pid = nxt; pages += 1; time.sleep(0.4)
        if ok and out:
            ins = sum(1 for d in out if d["stock"] == "in_stock")
            print(f"  [HM] Fynd API → {len(out)} Hot Wheels ({ins} in stock, {pages+1} page(s))")
            return out
    print("  [HM] Fynd API returned nothing — falling back to page checks")
    return None


def _hm_sitemap_slugs(sess) -> set:
    """Collect all hot-wheels product slugs from the sitemap(s)."""
    def _g(u):
        return (sess.get(u, headers=COMMON_HEADERS, timeout=TIMEOUT) if sess
                else http.get(u, headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE))
    slugs = set()
    sitemap_urls = []
    # robots.txt usually lists the sitemap(s)
    try:
        r = _g("https://hamleys.in/robots.txt")
        if r.status_code == 200:
            sitemap_urls += re.findall(r"(?im)^sitemap:\s*(\S+)", r.text)
    except Exception:
        pass
    sitemap_urls += ["https://hamleys.in/sitemap.xml"]

    fetched, queue = set(), list(dict.fromkeys(sitemap_urls))
    while queue and len(fetched) < 12:
        sm = queue.pop(0)
        if sm in fetched:
            continue
        fetched.add(sm)
        try:
            r = _g(sm)
            if r.status_code != 200:
                continue
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
        except Exception:
            continue
        for loc in locs:
            if loc.endswith(".xml") and ("product" in loc.lower() or "sitemap" in loc.lower()):
                queue.append(loc)
            elif "/product/" in loc and "hot-wheels" in loc.lower():
                slugs.add(loc.rsplit("/product/", 1)[-1].strip("/"))
    if slugs:
        print(f"  [HM] sitemap → {len(slugs)} hot-wheels product slugs")
    return slugs


def _hm_page_check(sess, slug: str) -> dict | None:
    """SSR product page → {name, price, stock}. None if page invalid/unreachable.
    Validation: the page must contain this product's own slug words, so an error
    page or shell can never masquerade as a stock answer (lesson from MG)."""
    toks = [w for w in re.split(r"[-_]", slug.lower()) if len(w) > 2][:3]
    u = f"https://hamleys.in/product/{slug}"
    try:
        r = (sess.get(u, headers=COMMON_HEADERS, timeout=TIMEOUT) if sess
             else http.get(u, headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE))
    except Exception:
        return None
    if r.status_code != 200 or len(r.text) < 2000:
        return None
    page = r.text
    tit = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    title = _clean(tit.group(1)) if tit else ""
    blob = (title + " " + page[:20000]).lower()
    hits = sum(1 for t in toks if t in blob)
    if toks and hits < max(1, len(toks) - 1):
        return None                                   # not this product's page
    name = re.sub(r"\s*[|–-]\s*Hamleys.*$", "", title, flags=re.I).strip() or slug
    pnums = [price_to_int(x) for x in re.findall(r"₹\s*([\d,]+)", page[:30000])]
    pnums = [p for p in pnums if p and 50 <= p <= 100000]
    price = min(pnums) if pnums else None
    up = page.upper()
    if "OUT OF STOCK" in up or "SOLD OUT" in up or "NOTIFY ME" in up:
        stock = "out_of_stock"
    elif "ADD TO BAG" in up or "ADD TO CART" in up:
        stock = "in_stock"
    else:
        stock = "out_of_stock"                        # unknown → conservative
    return {"name": name[:180], "price": price, "stock": stock}


def scrape_hamleys() -> list[dict]:
    sess = _hm_session()
    # warm cookies + grab the listing's top-12 (they render Add-to-bag = in stock)
    listing_items = {}
    try:
        r = (sess.get("https://hamleys.in/products?brand=hot-wheels",
                      headers=COMMON_HEADERS, timeout=TIMEOUT) if sess
             else http.get("https://hamleys.in/products?brand=hot-wheels",
                           headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE))
        if r.status_code == 200 and len(r.text) > 3000:
            for part in re.split(r'(?=<a[^>]+href="/product/)', r.text):
                hm = _HM_CARD.search(part or "")
                if not hm:
                    continue
                slug = hm.group(1).rsplit("/", 1)[-1]
                txt = _clean(part[:2500])
                nm = re.search(r'(Hot\s*Wheels[^₹]{3,150})', txt, re.I)
                if not nm:
                    continue
                pnums = [price_to_int(x) for x in re.findall(r'₹\s*([\d,]+)', txt)]
                pnums = [p for p in pnums if p and 50 <= p <= 100000]
                up = part.upper()
                oos = "OUT OF STOCK" in up or "SOLD OUT" in up or "NOTIFY" in up
                listing_items[slug] = {
                    "name": re.sub(r"\s+", " ", nm.group(1)).strip(" -–|")[:180],
                    "price": min(pnums) if pnums else None,
                    "stock": "out_of_stock" if oos else "in_stock",
                }
            print(f"  [HM] listing → {len(listing_items)} visible products")
        else:
            print(f"  [HM] listing → HTTP {r.status_code}")
    except Exception as e:
        print(f"  [HM] listing failed: {e}")

    # fast path: full catalog with sellable flags in one API call
    api = _hamleys_api(sess)
    if api:
        api = [d for d in api if "hot wheel" in d["name"].lower()
               or "hotwheels" in d["name"].lower().replace(" ", "")]
        if api:
            print(f"[*] Hamleys total (API): {len(api)}")
            return api

    # full catalog: sitemap ∪ listing ∪ everything ever seen
    prev_all = load_seen()
    slugs = _hm_sitemap_slugs(sess)
    slugs |= set(listing_items)
    slugs |= {pid[3:] for pid, v in prev_all.items()
              if pid.startswith("hm_") and isinstance(v, dict)}

    # rotate page checks over items NOT visible on the listing
    to_check = [s for s in slugs if s not in listing_items]
    to_check.sort(key=lambda s: prev_all.get(f"hm_{s}", {}).get("hm_verified_at", ""))
    checked, fails = {}, 0
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    batch = to_check[:HM_VERIFY_BUDGET]
    if batch:
        with ThreadPoolExecutor(max_workers=HM_WORKERS) as ex:
            futs = {ex.submit(_hm_page_check, sess, s): s for s in batch}
            for fut in as_completed(futs):
                try:
                    info = fut.result()
                except Exception:
                    info = None
                if info:
                    checked[futs[fut]] = info
                else:
                    fails += 1
    if fails and not checked:
        print(f"  [HM] all {fails} page checks failed — markup may have changed")
    if checked:
        oos = sum(1 for v in checked.values() if v["stock"] == "out_of_stock")
        print(f"  [HM] page-checked {len(checked)} products "
              f"({len(checked)-oos} in stock / {oos} sold out)")

    out = []
    for s in sorted(slugs):
        pid = f"hm_{s}"
        prevrow = prev_all.get(pid, {})
        if s in listing_items:
            info = listing_items[s]
            verified_at = now
        elif s in checked:
            info = checked[s]
            verified_at = now
        else:
            # not checked this run — keep last known state
            info = {"name": prevrow.get("name") or s.replace("-", " ").title(),
                    "price": price_to_int(prevrow.get("price")),
                    "stock": prevrow.get("stock") or "out_of_stock"}
            verified_at = prevrow.get("hm_verified_at", "")
        out.append({
            "id": pid, "source": "hamleys", "name": str(info["name"])[:180],
            "url": f"https://hamleys.in/product/{s}",
            "price": f"₹{info['price']}" if info.get("price") else "",
            "mrp": "",
            "stock": info["stock"],
            "badge_new": False,
            "stock_ver": "hm_pages_v1",
            "hm_verified_at": verified_at,
        })
    ins = sum(1 for d in out if d["stock"] == "in_stock")
    print(f"[*] Hamleys total: {len(out)} ({ins} in stock)")
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# SOURCE — Karz and Dolls  (Hot Wheels + MiniGT, all categories)
# ══════════════════════════════════════════════════════════════════════════════════
# KND relaunched on a new Next.js site; product links are now
# /details/{slug}?pid={ID} and ALL Hot Wheels + MiniGT categories are tracked.
# Category pages are fully server-rendered (name, SKU line, price, sale price,
# Add-to-Cart), so one fetch per category = that category complete with stock.
_KD = "https://www.karzanddolls.com"
_KD_DEFAULT_URLS = [
    f"{_KD}/hot-wheels/mainlines",
    f"{_KD}/hot-wheels/pop-culture",
    f"{_KD}/hot-wheels/card-art-premiums",
    f"{_KD}/hot-wheels/gift-pack",
    f"{_KD}/hot-wheels/car-culture",
    f"{_KD}/hot-wheels/fast-and-furious",
    f"{_KD}/hot-wheels/boulevard-series",
    f"{_KD}/hot-wheels/team-transport",
    f"{_KD}/hot-wheels/character-cars",
    f"{_KD}/hot-wheels/disney-cars",
    f"{_KD}/hot-wheels/hot-wheels-accessories",
    f"{_KD}/mini-gt/mini-gt",
    f"{_KD}/mini-gt/mini-gt-blister-pack",
    f"{_KD}/mini-gt/kaido-house",
    f"{_KD}/pre-orders/pre-order-minigt",
    f"{_KD}/pre-orders/pre-order-special-stock",
    # v13: chase cars and KND's "special stocks" shelf (mixed brands — only Hot
    # Wheels / MiniGT / Kaido cards pass the brand checks below), plus the home
    # page, whose "New Arrival" strip is where fresh stock shows up first.
    f"{_KD}/specials/chase-car",
    f"{_KD}/specials/special-stocks-64-43-scale",
    f"{_KD}/",
]
# v17.3: shelves of the chase-only lines — only their chase pieces are kept
_KD_CHASE_LINE_URLS = [
    f"{_KD}/hot-wheels/monster-trucks",
    f"{_KD}/matchbox/matchbox-basic-cars",
    f"{_KD}/matchbox/matchbox-moving-parts",
    f"{_KD}/matchbox/matchbox-superfast",
    f"{_KD}/majorette/premium-cars",
    f"{_KD}/majorette/basic-cars",
    f"{_KD}/majorette/majorette",
]
KD_URLS = ([u.strip() for u in os.getenv("KD_URLS", "").split("|") if u.strip()]
           or _KD_DEFAULT_URLS + (_KD_CHASE_LINE_URLS if CHASE_ONLY_LINES else []))
# Every car on these shelves is a chase car, whatever its name says.
_KD_CHASE_SHELVES = ("/specials/chase-car",)
# False when any KND page failed this pass: products on that page would look
# "missing", so the absence = sold-out check must not run (it would mark them
# sold out and then fire false restock alerts when the page loads again).
KD_HEALTHY = [True]
KD_INCLUDE_PREORDER = os.getenv("KD_INCLUDE_PREORDER", "true").lower() == "true"

# Other brands KND sells that must never appear in Hot Wheels / MiniGT alerts.
_KD_DENY = tuple(t.strip().upper().replace(" ", "") for t in os.getenv(
    "KD_DENY",
    "LEGO,BARBIE,FUNKO,MATCHBOX,SOLIDO,SCHUCO,GREENLIGHT,POPRACE,TARMAC,INNO64,"
    "PARA64,PARAGON,TOMICA,MAJORETTE,BBURAGO,MAISTO,ERACARS,JADA,BBR,SPARK,"
    "AMERICANDIORAMA,ALMOSTREAL,LCDMODELS,TRENDSHOBBY,GHOSTPLAYER,KILOWORKS,"
    "ZDTOYS,MARVEL,TRANSFORMERS,WWE,JURASSIC,MASTERVERSE,IMAGINEXT,BOOK,VMB,"
    "RMZ,MSZ,GOC,QUBECARZ,TSM,TOPSPEED").split(",") if t.strip())

_KD_LINK = re.compile(r'href="(/details/[^"]+?)"', re.I)
_KD_PID = re.compile(r'[?&]pid=([A-Za-z0-9]+)')


_KD_NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)
_KD_BRAND_TOKENS = ("HOTWHEELS", "MINIGT", "KAIDO")
# a chase piece of a chase-only line may be Matchbox / Majorette
_KD_DENY_CHASE = tuple(k for k in _KD_DENY if k not in ("MATCHBOX", "MAJORETTE", "MBX"))


def _kd_line(path: str, text: str):
    """The chase-only line of a KND product: its shelf says it (/matchbox/…,
    /majorette/…, /hot-wheels/monster-trucks), or its own words do."""
    if not CHASE_ONLY_LINES:
        return None
    p = (path or "").lower()
    if p.startswith("/matchbox/"):
        return "MATCHBOX"
    if p.startswith("/majorette/"):
        return "MAJORETTE"
    if "monster-truck" in p and _FC_MT_EXCLUDED:
        return "MONSTER TRUCKS"
    return chase_line(text)


_KD_LINE_PREFIX = {"MATCHBOX": "MATCHBOX", "MAJORETTE": "MAJORETTE", "MONSTER TRUCKS": "HOT WHEELS MONSTER TRUCKS"}
_KD_LEFT_OUT: dict = {}     # page path -> products left out this pass as not chase pieces (for the log)


def _kd_named(name: str, cl) -> str:
    """KND names often leave the brand to the SKU line ("NISSAN Z BLUE" on its
    Majorette shelf): a chase-only line's name gets it up front, so the alert
    says which line it is."""
    if not cl or any(lab == cl and rx.search(name) for lab, rx in _LINE_RES):
        return name
    return f"{_KD_LINE_PREFIX.get(cl, cl)} {name}"


def _kd_chase_tag(path: str, name: str, *fields) -> str | None:
    """None to drop the product; else the marker its name needs (often "").
    A product on the chase shelf is a chase; a Matchbox / Majorette / monster
    truck must be one (its name, SKU line or shelf says so), or it's dropped."""
    shelf = (path or "").rstrip("/") in _KD_CHASE_SHELVES
    fields = [str(f or "") for f in fields]
    kinds = [k for k in (chase_kind(t) for t in [name, *fields] + (["[CHASE]"] if shelf else [])) if k]
    best = max(kinds, key=lambda k: _CHASE_RANK[k]) if kinds else None
    if not best and _kd_line(path, " ".join([name, *fields])):
        return None
    return chase_tag(_CHASE_TAGS[best], name) if best else ""


def _kd_from_next_data(page: str, cat: str, path: str = ""):
    """Products from the page's __NEXT_DATA__ JSON (probe, 18 Oct 2026):
    category pages carry props.pageProps.products, the home page carries
    newarrivalsdata / productdata / ispreorderdata / carsdata …, each product
    {pid, pro_name, slug, product_sname, sku, act_price, dis_price, in_stock,
    is_preorder, preorder_price}. Returns None when the JSON isn't there, so
    the caller can fall back to parsing the HTML cards."""
    m = _KD_NEXT.search(page)
    if not m:
        return None
    try:
        props = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
    except Exception:
        return None
    found, stack = [], [props]
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            if "pid" in n and "pro_name" in n:
                found.append(n)
            else:
                stack.extend(n.values())
    if not found and "products" not in props:
        return None          # not the page shape we know — use the HTML parser
    cat_ok = any(k in cat for k in ("hot-wheels", "mini-gt", "kaido", "minigt"))
    out = []
    for p in found:
        pid = str(p.get("pid") or "").strip()
        name = re.sub(r"\s+", " ", str(p.get("pro_name") or "")).strip(" -–|,")
        if not pid or len(name) < 4 or str(p.get("is_approved", 1)) == "0":
            continue
        line = str(p.get("product_sname") or p.get("sku") or "")
        sku = str(p.get("sku") or "")
        # v17.3: the chase shelf's cars are chases; a Matchbox / Majorette /
        # monster truck is kept only when it's a chase piece
        tag = _kd_chase_tag(path, name, line, sku)
        if tag is None:
            _KD_LEFT_OUT[path] = _KD_LEFT_OUT.get(path, 0) + 1
            continue
        cl = _kd_line(path, f"{name} {line} {sku}")
        blob = (name + " " + line).upper()
        flat = blob.replace(" ", "").replace("-", "")
        if not cat_ok:
            # mixed shelves (home page, specials): Hot Wheels / MiniGT / Kaido
            # only, and never another brand. On the brand's own category pages
            # every product is that brand — Hot Wheels Marvel or Jurassic
            # character cars are still Hot Wheels — so the deny-list isn't
            # applied there. (v17.3: plus Matchbox / Majorette chase pieces.)
            if any(k in flat for k in (_KD_DENY_CHASE if cl else _KD_DENY)):
                continue
            is_hw_line = blob.startswith("HW ") or " HW " in f" {line.upper()} "
            if not (is_hw_line or any(k in flat for k in _KD_BRAND_TOKENS)
                    or cl in ("MATCHBOX", "MAJORETTE")
                    or (cl and path.lower().startswith("/hot-wheels/"))):
                continue
        is_pre = str(p.get("is_preorder") or "0") not in ("0", "", "None", "False")
        if is_pre and not KD_INCLUDE_PREORDER:
            continue
        price = price_to_int(p.get("dis_price")) or price_to_int(p.get("act_price"))
        mrp = price_to_int(p.get("act_price"))
        if not price:
            continue
        slug = str(p.get("slug") or "").strip()
        out.append({
            "id": f"kd_{pid}", "source": "karzdolls",
            "name": (_kd_named(name, cl) + tag + (" [PRE-ORDER]" if is_pre else ""))[:180],
            "url": f"{_KD}/details/{quote(slug, safe='-_.~')}?pid={quote(pid, safe='')}",
            "price": f"₹{price}", "mrp": f"₹{mrp}" if mrp and mrp > price else "",
            "stock": "in_stock" if str(p.get("in_stock")) in ("1", "True", "true") else "out_of_stock",
            "badge_new": False,
        })
    return out


def _kd_from_html(page: str, cat: str, path: str = "") -> list:
    """The fallback: the page's HTML product cards."""
    out = []
    for part in re.split(r'(?=<a[^>]+href="/details/)', page):
        lm = _KD_LINK.search(part or "")
        if not lm:
            continue
        link = html.unescape(lm.group(1))
        pm = _KD_PID.search(link)
        if not pm:
            continue
        uid = f"kd_{pm.group(1)}"
        txt = _clean(part[:3000])
        nm = re.search(r'([A-Z0-9][A-Z0-9 ()\'"“”\.\,/&#\-\+\[\]]{8,150}?)\s*₹', txt)
        if not nm:
            continue
        name = re.sub(r"\s+", " ", nm.group(1)).strip(" -–|,")[:180]
        if len(name) < 6:
            continue
        up = part.upper()
        is_pre = "PRE-ORDER" in up or "PRE ORDER" in up or name.startswith("PREORDER")
        if is_pre and not KD_INCLUDE_PREORDER:
            continue
        tag = _kd_chase_tag(path, name, txt[:250])
        if tag is None:
            _KD_LEFT_OUT[path] = _KD_LEFT_OUT.get(path, 0) + 1
            continue
        cl = _kd_line(path, txt[:250])
        # deny-list is matched against the card's opening text (badge +
        # SKU line + name) because the brand often appears ONLY in the
        # SKU line, e.g. "1:43 SOLIDO 421438273".
        deny_scope = txt[:250].upper().replace(" ", "").replace("-", "")
        if any(k in deny_scope for k in (_KD_DENY_CHASE if cl else _KD_DENY)):
            continue
        sku = ""
        sm = re.search(r'((?:MINI\s*GT|HOT\s*WHEELS|HOTWHEELS|KAIDO)[A-Z0-9 \-]{0,30})',
                       txt, re.I)
        if sm:
            sku = sm.group(1).strip()
        blob = (name + " " + sku).upper().replace(" ", "")
        if not any(k in blob for k in ("MINIGT", "HOTWHEELS", "KAIDO")):
            if not (any(k in cat for k in ("hot-wheels", "mini-gt", "kaido", "minigt"))
                    or cl in ("MATCHBOX", "MAJORETTE")
                    or (cl and path.lower().startswith("/hot-wheels/"))):
                continue
        pnums = [price_to_int(x) for x in re.findall(r"₹\s*([\d,]+)", txt)]
        pnums = [p for p in pnums if p and 50 <= p <= 200000]
        if not pnums:
            continue
        price = pnums[0]
        mrp = pnums[1] if len(pnums) > 1 and pnums[1] > price else None
        if "ADD TO CART" in up:
            stock = "in_stock"
        elif "OUT OF STOCK" in up or "SOLD OUT" in up or "NOTIFY" in up:
            stock = "out_of_stock"
        else:
            continue
        out.append({
            "id": uid, "source": "karzdolls",
            "name": (_kd_named(name, cl) + tag + (" [PRE-ORDER]" if is_pre else ""))[:180],
            "url": _KD + quote(link, safe="/:?=&"),
            "price": f"₹{price}", "mrp": f"₹{mrp}" if mrp else "",
            "stock": stock, "badge_new": "NEW ARRIVAL" in up,
        })
    return out


def scrape_karzanddolls() -> list[dict]:
    out, seen_ids = [], set()
    KD_HEALTHY[0] = True

    def fetch(u):
        label = u.rstrip("/").rsplit("/", 1)[-1] if u.rstrip("/") != _KD else "home"
        for attempt in range(2):
            try:
                r = http.get(u, headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE)
                if r.status_code == 200 and len(r.text) > 4000:
                    return r.text
                if r.status_code == 404:
                    # a removed/renamed category is not a failed fetch
                    print(f"  [KD] {label} → HTTP 404 (category gone)")
                    return None
                err = f"HTTP {r.status_code}"
            except Exception as e:
                err = type(e).__name__
            time.sleep(1.5)
        print(f"  [KD] {label} → {err}")
        KD_HEALTHY[0] = False
        return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch, u): u for u in KD_URLS}
        pages = {}
        for fut in as_completed(futs):
            try:
                pages[futs[fut]] = fut.result()
            except Exception:
                pages[futs[fut]] = None
                KD_HEALTHY[0] = False
    # v17.3: pages are read in a fixed order — the chase shelf first — so a car
    # listed on two shelves always comes out the same way (with its chase tag)
    order = sorted(KD_URLS, key=lambda u: 0 if u[len(_KD):].rstrip("/") in _KD_CHASE_SHELVES else 1)
    _KD_LEFT_OUT.clear()
    for u in order:
        page = pages.get(u)
        if not page:
            continue
        cat = u.rstrip("/").rsplit("/", 1)[-1] if u.rstrip("/") != _KD else ""
        path = u[len(_KD):] if u.startswith(_KD) else u
        # Preferred: the product list Next.js embeds in the page as JSON
        # (exact names, prices, in_stock and pre-order flags). The HTML card
        # parser is the fallback if that ever disappears.
        recs = _kd_from_next_data(page, cat, path)
        if recs is None:
            recs = _kd_from_html(page, cat, path)
        found = 0
        for d in recs:
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                out.append(d)
                found += 1
        left = _KD_LEFT_OUT.get(path, 0)
        note = f" ({left} not chase pieces, left out)" if left else ""
        if found:
            print(f"  [KD] {cat or 'home'} → {found}{note}")
        elif recs:
            print(f"  [KD] {cat or 'home'} → 0 new ({len(recs)} already listed elsewhere){note}")
        elif left:
            print(f"  [KD] {cat or 'home'} → no chase pieces right now ({left} others left out)")
        else:
            print(f"  [KD] {cat or 'home'} → 0 (empty right now)")
    ins = sum(1 for d in out if d["stock"] == "in_stock")
    print(f"[*] Karz&Dolls total: {len(out)} ({ins} in stock)"
          + ("" if KD_HEALTHY[0] else " — some pages failed, sold-out check skipped"))
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# SOURCE — BigBasket  (search API, best effort — geo-limited)
# ══════════════════════════════════════════════════════════════════════════════════
# BigBasket screens datacenter IPs, so from GitHub's US runners this usually
# returns 403 and contributes nothing (never blocking other sources). It works
# from an Indian IP, i.e. the phone watcher.
BB_TERMS = [t.strip() for t in os.getenv("BB_TERMS", "hot wheels,hotwheels").split(",")
            if t.strip()]


def scrape_bigbasket() -> list[dict]:
    out, seen_ids = [], set()
    headers = {**COMMON_HEADERS, "Accept": "application/json, text/plain, */*",
               "Referer": "https://www.bigbasket.com/", "x-channel": "BB-WEB"}
    try:
        sess = http.Session(**_IMPERSONATE) if _IMPERSONATE else http.Session()
        h = sess.get("https://www.bigbasket.com/", headers=COMMON_HEADERS, timeout=TIMEOUT)
        print(f"  [BB] homepage → HTTP {h.status_code}")
    except Exception as e:
        sess = None
        print(f"  [BB] homepage failed: {type(e).__name__}")

    def _g(u):
        return (sess.get(u, headers=headers, timeout=TIMEOUT) if sess
                else http.get(u, headers=headers, timeout=TIMEOUT, **_IMPERSONATE))

    for term in BB_TERMS:
        for api in (f"https://www.bigbasket.com/listing-svc/v2/products?type=ps&slug={quote(term)}&page=1",
                    f"https://www.bigbasket.com/product/get-products/?slug={quote(term)}&type=ps&page=1"):
            try:
                r = _g(api)
                if r.status_code != 200:
                    print(f"  [BB] {api.split('.com')[1][:32]} → HTTP {r.status_code}")
                    continue
                data = r.json()
            except Exception as e:
                print(f"  [BB] {api.split('.com')[1][:32]} → {type(e).__name__}")
                continue
            found, stack = 0, [data]
            while stack:
                n = stack.pop()
                if isinstance(n, dict):
                    nm = n.get("desc") or n.get("name") or n.get("p_desc")
                    pid = n.get("id") or n.get("sku") or n.get("p_id")
                    if nm and pid and re.search(r"hot\s*wheel", str(nm), re.I):
                        uid = f"bb_{pid}"
                        if uid not in seen_ids:
                            seen_ids.add(uid)
                            pr = n.get("pricing") or {}
                            sp = None
                            if isinstance(pr, dict):
                                d2 = pr.get("discount") or {}
                                pp = d2.get("prim_price") if isinstance(d2, dict) else None
                                if isinstance(pp, dict):
                                    sp = pp.get("sp")
                            av = n.get("availability") or {}
                            st = str(av.get("avail_status", "")) if isinstance(av, dict) else ""
                            sold = st in ("002",) or n.get("in_stock") is False
                            val = sp or n.get("sp") or n.get("mrp")
                            out.append({"id": uid, "source": "bigbasket",
                                        "name": str(nm)[:180],
                                        "url": f"https://www.bigbasket.com/pd/{pid}/{n.get('slug') or ''}/",
                                        "price": f"₹{price_to_int(val)}" if val else "",
                                        "mrp": "",
                                        "stock": "out_of_stock" if sold else "in_stock",
                                        "badge_new": False})
                            found += 1
                    stack.extend(n.values())
                elif isinstance(n, list):
                    stack.extend(n)
            if found:
                print(f"  [BB] '{term}' → {found}")
                break
        if out:
            break
    if not out:
        print("  [BB] no results — likely geo/bot-blocked from this runner's IP.")
    print(f"[*] BigBasket total: {len(out)}")
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# SOURCE 4 — Blinkit  (internal search API, location-pinned) — best effort
# ══════════════════════════════════════════════════════════════════════════════════
def scrape_blinkit() -> list[dict]:
    out, seen_ids = [], set()

    # ── Watchlist mode ─────────────────────────────────────────────────────────
    # Paste Blinkit product links (from the app's Share button) into the
    # BLINKIT_WATCH env var, comma-separated, e.g.:
    #   BLINKIT_WATCH="https://blinkit.com/prn/hot-wheels-x/prid/12345, https://blinkit.com/prn/y/prid/67890"
    # The bot extracts each product id and checks that exact item every run —
    # much more reliable than search, since it's one product endpoint per item.
    # NOTE: still subject to the same geo-block from GitHub's US runners; this
    # becomes fully live the day the workflow runs from an Indian IP
    # (self-hosted runner). The code is ready either way.
    watch_raw = os.getenv("BLINKIT_WATCH", "")
    # capture full share-links where given (preferred: we fetch the exact page),
    # plus any bare /prid/N ids as fallback
    watch_urls = re.findall(r"https?://blinkit\.com/\S*?/prid/\d+", watch_raw)
    watch_ids  = re.findall(r"/prid/(\d+)", watch_raw)
    url_by_id  = {re.search(r"/prid/(\d+)", u).group(1): u for u in watch_urls}
    headers = {
        **COMMON_HEADERS,
        "Accept": "application/json, text/plain, */*",
        "app_client": "consumer_web",
        "app_version": "1010101010",
        "web_app_version": "1008010016",
        "platform": "desktop_web",
        "lat": str(LAT), "lon": str(LON),
        "Referer": "https://blinkit.com/s/?q=hot%20wheels",
        "Origin": "https://blinkit.com",
        "device_id": "hwtracker-" + PINCODE,
    }

    # Step 1: hit the homepage first to establish cookies (Blinkit's API often
    # rejects cookie-less calls). curl_cffi sessions carry cookies automatically.
    sess = None
    try:
        sess = http.Session(**_IMPERSONATE) if _IMPERSONATE else http.Session()
        h = sess.get("https://blinkit.com/", headers=COMMON_HEADERS, timeout=TIMEOUT)
        print(f"  [BL] homepage → HTTP {h.status_code}")
    except Exception as e:
        print(f"  [BL] homepage failed: {e}")

    def _get(u):
        if sess is not None:
            return sess.get(u, headers=headers, timeout=TIMEOUT)
        return http.get(u, headers=headers, timeout=TIMEOUT, **_IMPERSONATE)

    # Step 1b: check each watchlisted product (see BLINKIT_WATCH above).
    # PRIMARY: fetch the product's own share-link page — it's fully
    # server-rendered (verified live): <title> carries "…Buy Online at ₹685…",
    # the body carries price/MRP and the Add-to-cart vs Out-of-stock state, and
    # none of it needs lat/lon. FALLBACK: the internal JSON product API.
    for prid in watch_ids:
        page_url = url_by_id.get(prid, f"https://blinkit.com/prn/x/prid/{prid}")
        got = False
        try:
            r = _get(page_url)
            if r.status_code == 200 and len(r.text) > 3000:
                page = r.text
                tit = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
                title = _clean(tit.group(1)) if tit else ""
                name = re.sub(r"\s*Price\s*-\s*Buy Online.*$", "", title, flags=re.I).strip()
                pm = (re.search(r"at\s*₹\s*([\d,]+)", title)
                      or re.search(r"₹\s*([\d,]+)", page))
                pval = price_to_int(pm.group(1)) if pm else None
                up = page.upper()
                sold = ("OUT OF STOCK" in up or "SOLD OUT" in up
                        or "CURRENTLY UNAVAILABLE" in up or "NOTIFY ME" in up)
                if name:
                    out.append({
                        "id": f"bl_{prid}", "source": "blinkit",
                        "name": name[:180], "url": page_url,
                        "price": f"₹{pval}" if pval else "", "mrp": "",
                        "stock": "out_of_stock" if sold else "in_stock",
                        "badge_new": False,
                    })
                    seen_ids.add(f"bl_{prid}")
                    got = True
            else:
                print(f"  [BL] watch page {prid} → HTTP {r.status_code}")
        except Exception as e:
            print(f"  [BL] watch page {prid} → {type(e).__name__}")

        if got:
            continue
        # Fallback: internal product API
        for api in (f"https://blinkit.com/v1/products/{prid}",
                    f"https://blinkit.com/v2/products/{prid}"):
            try:
                r = _get(api)
                if r.status_code != 200:
                    continue
                node = r.json()
            except Exception:
                continue
            # product payloads vary; walk for the first dict with a name
            stack, info = [node], None
            while stack and info is None:
                n = stack.pop()
                if isinstance(n, dict):
                    if n.get("name") or n.get("display_name"):
                        info = n
                        break
                    stack.extend(n.values())
                elif isinstance(n, list):
                    stack.extend(n)
            if info:
                name = info.get("name") or info.get("display_name")
                inv = info.get("inventory")
                sold = (info.get("is_sold_out") or info.get("out_of_stock")
                        or (isinstance(inv, (int, float)) and inv <= 0))
                pval = price_to_int(info.get("price") or info.get("offer_price")
                                    or info.get("mrp"))
                out.append({
                    "id": f"bl_{prid}", "source": "blinkit",
                    "name": str(name)[:180],
                    "url": f"https://blinkit.com/prn/x/prid/{prid}",
                    "price": f"₹{pval}" if pval else "", "mrp": "",
                    "stock": "out_of_stock" if sold else "in_stock",
                    "badge_new": False,
                })
                seen_ids.add(f"bl_{prid}")
                break
    if watch_ids:
        print(f"  [BL] watchlist: {len([o for o in out])}/{len(watch_ids)} reachable")

    # Step 2: try the search APIs (multiple generations of Blinkit's endpoint)
    for term in ("hot wheels", "hotwheels"):
        apis = (
            f"https://blinkit.com/v1/layout/search?q={quote(term)}&search_type=type_to_search",
            f"https://blinkit.com/v6/search/products?start=0&size=30&search_type=7&q={quote(term)}",
            f"https://blinkit.com/v2/search/products?q={quote(term)}",
        )
        for api in apis:
            try:
                r = _get(api)
                if r.status_code != 200:
                    print(f"  [BL] {api.split('.com')[1][:40]} → HTTP {r.status_code}")
                    continue
                data = r.json()
            except Exception as e:
                print(f"  [BL] {api.split('.com')[1][:40]} → {type(e).__name__}")
                continue

            # Walk the JSON for product-ish dicts
            found = 0
            stack = [data]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    name = (node.get("name") or node.get("display_name")
                            or node.get("product_name") or node.get("title"))
                    pid  = node.get("product_id") or node.get("id") or node.get("merchant_id")
                    if name and pid and re.search(r"hot\s*wheel", str(name), re.I):
                        uid = f"bl_{pid}"
                        if uid not in seen_ids:
                            seen_ids.add(uid)
                            price = (node.get("price") or node.get("offer_price")
                                     or node.get("mrp") or node.get("selling_price"))
                            inv = node.get("inventory")
                            if inv is None:
                                inv = node.get("stock")
                            unavailable = (node.get("is_sold_out") or node.get("out_of_stock")
                                           or (isinstance(inv, (int, float)) and inv <= 0))
                            pval = price_to_int(price)
                            out.append({
                                "id": uid, "source": "blinkit", "name": str(name)[:180],
                                "url": f"https://blinkit.com/prn/x/prid/{pid}",
                                "price": f"₹{pval}" if pval else "",
                                "mrp": "",
                                "stock": "out_of_stock" if unavailable else "in_stock",
                                "badge_new": False,
                            })
                            found += 1
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
            if found:
                print(f"  [BL] '{term}' → {found}")
                break   # got results for this term, stop trying other endpoints
        if out:
            break

    if not out:
        # Honest diagnostics: Blinkit is location-locked AND geo-blocks foreign
        # datacenter IPs. GitHub Actions runs from US IPs, which Blinkit often
        # rejects outright. This is a known limitation of any free hosted
        # tracker — see README for the workaround (self-hosted runner / cron
        # from an Indian IP), which makes this source work reliably.
        print("  [BL] no results — likely geo-blocked from this runner's IP (US datacenter).")
    print(f"[*] Blinkit total: {len(out)}")
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# DIFF + ALERTS
# ══════════════════════════════════════════════════════════════════════════════════
RESTOCK_COOLDOWN_H = 24

# Sources whose pages show their COMPLETE catalogue, so a product missing from a
# healthy scrape really has sold out / been delisted.
ABSENCE_SOURCES = [s.strip() for s in os.getenv("ABSENCE_SOURCES", "karzdolls").split(",")
                   if s.strip()]
PRICE_COOLDOWN_H   = 24     # min hours between price-drop alerts per product     # don't re-alert the same product's restock within 24h


def compute_changes(current: dict, seen: dict) -> dict:
    """Diff current observations against permanent memory.

    Dedup rules (this is what stops repeated alerts):
      • NEW fires at most ONCE EVER per product id (alerted_new flag in seen.json).
      • RESTOCK fires only on a genuine OOS→in-stock transition, with a 24h
        cooldown per product so a flapping listing can't spam.
    Bookkeeping flags are written into `seen` here and persisted by
    merge_and_save_seen() at the end of the run.
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    new_listings, restocks, price_drops, back_soon = [], [], [], []

    for pid, d in current.items():
        if pid == "_meta":
            continue
        prev = seen.get(pid)
        stock = d["stock"]
        cur_price = price_to_int(d.get("price"))

        if prev is None or not prev.get("alerted_new", False):
            # Never alerted as new before → this is its one NEW alert, ever.
            if stock == "in_stock":
                new_listings.append(d)
            else:
                back_soon.append(d)      # newly listed but OOS — wishlist candidate
            # Mark it so it can never fire NEW/back_soon again, even if it
            # disappears from view for weeks and then comes back.
            entry = seen.setdefault(pid, {})
            entry["alerted_new"] = True
            if stock != "in_stock" and d.get("source") == "firstcry":
                entry["fc_new_pending"] = now   # its first in-stock moment is still NEW
            continue

        prev_stock = prev.get("stock")
        prev_price = price_to_int(prev.get("price"))
        # v16.1: an alert that was out again within minutes was a phantom —
        # remembered, so the same few units can't alert again and again
        if (prev_stock == "in_stock" and stock == "out_of_stock" and prev.get("last_restock_alert")
                and _hours_since(prev["last_restock_alert"]) * 60 < FC_PHANTOM_MIN):
            prev["fc_phantom"] = now

        # A source can carry a "stock_ver" tag marking which detection logic
        # produced its stock reading (e.g. Minifygram's v4.4 rewrite from
        # page-guessing to the authoritative product_skus query). If this
        # run's tag differs from what's stored, the stock value may have just
        # been CORRECTED rather than genuinely changed — so we apply it
        # silently instead of firing a possibly-false restock alert. Real
        # restocks after that read normally.
        stock_ver = d.get("stock_ver")
        is_correction = bool(stock_ver) and stock_ver != prev.get("stock_ver")
        # Trust rule: alerts only fire on a change between TWO genuine readings.
        # If this is the first trusted reading of a car (its previous state was
        # carried, guessed, HTML-scraped, or left over from an earlier bug), the
        # reading is applied silently — it corrects the record, it isn't news.
        if d.get("fc_trusted") and not prev.get("fc_trusted"):
            is_correction = True
        if d.get("fc_first_read"):
            is_correction = True

        # a restock confirmed on FirstCry's product page can't be listing
        # flicker, so it may alert again after FC_RESTOCK_COOLDOWN_H hours
        cooldown = (FC_RESTOCK_COOLDOWN_H if d.get("fc_live_now") and d.get("fc_live") == "ok"
                    else RESTOCK_COOLDOWN_H)
        if d.get("fc_cart") == "y":
            # v17: the cart confirmed it — real units again; v17.2: 🎯 cars after
            # FC_CART_COOLDOWN_MIN, the rest at most every FC_CART_COOLDOWN_OTHER_H
            cooldown = (FC_CART_COOLDOWN_MIN / 60.0 if _is_flagged(d) else FC_CART_COOLDOWN_OTHER_H)
        if (stock == "in_stock" and prev_stock == "out_of_stock"
                and not is_correction
                and _hours_since(prev.get("last_restock_alert", "")) >= cooldown):
            # a new listing first seen sold out (its NEW alert went unsent) that
            # comes in within a day is news as NEW, not "back"
            if prev.get("fc_new_pending") and _hours_since(prev["fc_new_pending"]) < 24:
                new_listings.append({**d, "_known": True})
                prev.pop("fc_new_pending", None)
            else:
                restocks.append(d)
            prev["last_restock_alert"] = now

        # PRICE DROP — guarded. The old rule fired on ANY decrease, so a
        # mis-parsed price flapping between runs (e.g. ₹100 from the club-cash
        # blurb vs the real ₹157) produced the same alert over and over. Now a
        # drop must be genuine (>=5% AND >=₹15) and can only alert once per
        # PRICE_COOLDOWN_H per product.
        # Must have been in stock BEFORE too. Without this, a car restocking at a
        # lower price fired both "BACK IN STOCK" and "PRICE DROP" for the same
        # event — the duplicate lines in the same message.
        if (stock == "in_stock" and prev_stock == "in_stock"
                and cur_price and prev_price
                and not is_correction
                and cur_price <= prev_price * 0.95
                and (prev_price - cur_price) >= 15
                and _hours_since(prev.get("last_price_alert", "")) >= PRICE_COOLDOWN_H):
            price_drops.append({**d, "prev_price": prev.get("price")})
            prev["last_price_alert"] = now

    return {"new_listings": new_listings, "restocks": restocks,
            "price_drops": price_drops, "back_soon": back_soon}


SRC = {"firstcry": "🛒FC", "minifygram": "💎MG", "hamleys": "🧸HM", "karzdolls": "🏁KD",
       "bigbasket": "🧺BB", "blinkit": "⚡BL"}


def _within_budget(d) -> bool:
    if MAX_ALERT_PRICE <= 0:
        return True
    p = price_to_int(d.get("price"))
    return (p is None) or (p <= MAX_ALERT_PRICE)


def _is_marque_flagged(d) -> bool:
    """A watched FirstCry car, a WATCHLIST keyword, or one of your marques
    (Porsche, Ferrari, Lamborghini, Supra …) — on every store."""
    return (bool(d.get("watched")) or any(w in d["name"].lower() for w in WATCHLIST)
            or _fc_is_marque(d["name"]))


def _is_flagged(d) -> bool:
    """🎯: your marques / watchlist, plus every Treasure Hunt, Super Treasure
    Hunt, chase and ZAMAC (v16)."""
    return _is_marque_flagged(d) or bool(hw_priority(d["name"]))


# v16: what a 🎯 alert is about, at a glance — its own message, first line.
# Specials first (a Porsche Treasure Hunt reads "🏆🖤 TREASURE HUNT · PORSCHE").
_HW_KINDS = {
    "sth":     ("💎", "SUPER TREASURE HUNT"),
    "schase":  ("💎", "SUPER CHASE"),
    "th":      ("🏆", "TREASURE HUNT"),
    "chase":   ("⛓️", "CHASE"),
    "sth_car": ("✨", "STH CAR"),
    "zamac":   ("🔩", "ZAMAC"),
}
_HW_RANK = {"sth": 0, "schase": 0, "th": 1, "chase": 2, "sth_car": 3, "zamac": 4}
# A heart per family of your marques — the colour says which at a glance — and
# the word that matched names it ("SKYLINE", "SUPRA", "McLAREN"). First fit wins.
_HEARTS = [
    ("❤️", [("ferrari", "FERRARI"), ("laferrari", "FERRARI"), ("testarossa", "FERRARI"),
            ("f40", "FERRARI"), ("f50", "FERRARI"), ("enzo", "FERRARI"), ("sf90", "FERRARI"),
            ("12cilindri", "FERRARI"), ("12cilinderi", "FERRARI"), ("purosangue", "FERRARI")]),
    ("🖤", [("porsche", "PORSCHE"), ("911", "PORSCHE"), ("930", "PORSCHE"), ("934", "PORSCHE"),
            ("935", "PORSCHE"), ("959", "PORSCHE"), ("964", "PORSCHE"), ("993", "PORSCHE"),
            ("918", "PORSCHE"), ("carrera", "PORSCHE"), ("singer", "PORSCHE"), ("taycan", "PORSCHE")]),
    ("💛", [("lamborghini", "LAMBORGHINI"), ("countach", "LAMBORGHINI"), ("aventador", "LAMBORGHINI"),
            ("huracan", "LAMBORGHINI"), ("diablo", "LAMBORGHINI"), ("miura", "LAMBORGHINI"),
            ("murcielago", "LAMBORGHINI"), ("revuelto", "LAMBORGHINI"), ("urus", "LAMBORGHINI"),
            ("sian", "LAMBORGHINI"), ("veneno", "LAMBORGHINI"), ("gallardo", "LAMBORGHINI")]),
    ("💙", [("skyline", "SKYLINE"), ("gt-r", "GT-R"), ("gtr", "GT-R"), ("silvia", "SILVIA"),
            ("180sx", "180SX"), ("fairlady", "FAIRLADY Z"), ("datsun", "DATSUN"), ("nissan", "NISSAN")]),
    ("🧡", [("supra", "SUPRA"), ("ae86", "AE86"), ("celica", "TOYOTA"), ("mr2", "TOYOTA"),
            ("toyota", "TOYOTA"), ("lexus", "LEXUS")]),
    ("💜", [("nsx", "HONDA NSX"), ("type r", "HONDA TYPE R"), ("civic", "HONDA"), ("honda", "HONDA"),
            ("rx-7", "RX-7"), ("rx7", "RX-7"), ("mazda", "MAZDA"), ("wrx", "SUBARU"), ("impreza", "SUBARU"),
            ("subaru", "SUBARU"), ("lancer", "MITSUBISHI"), ("evo", "MITSUBISHI"), ("mitsubishi", "MITSUBISHI")]),
    ("🤍", [("bugatti", "BUGATTI"), ("mclaren", "McLAREN"), ("koenigsegg", "KOENIGSEGG"),
            ("pagani", "PAGANI"), ("aston martin", "ASTON MARTIN"), ("alfa romeo", "ALFA ROMEO"),
            ("bmw", "BMW"), ("m3", "BMW"), ("m4", "BMW"), ("amg", "MERCEDES"), ("mercedes", "MERCEDES"),
            ("benz", "MERCEDES"), ("audi", "AUDI"), ("rs6", "AUDI"), ("rs 6", "AUDI")]),
    ("💚", [("mustang", "MUSTANG"), ("shelby", "SHELBY"), ("corvette", "CORVETTE"), ("camaro", "CAMARO"),
            ("challenger", "DODGE"), ("charger", "DODGE"), ("viper", "DODGE"), ("cuda", "PLYMOUTH"),
            ("road runner", "PLYMOUTH"), ("roadrunner", "PLYMOUTH"), ("plymouth", "PLYMOUTH")]),
    ("🩵", [("rlc", "RLC"), ("red line club", "RLC"), ("car culture", "CAR CULTURE"),
            ("team transport", "TEAM TRANSPORT"), ("boulevard", "BOULEVARD"),
            ("silver series", "SILVER SERIES"), ("fast furious", "FAST & FURIOUS"),
            ("fast & furious", "FAST & FURIOUS"), ("pop culture", "POP CULTURE"),
            ("silhouettes", "PREMIUM"), ("japan historics", "PREMIUM"), ("modern classics", "PREMIUM"),
            ("legends", "PREMIUM"), ("exotics", "PREMIUM"), ("premium", "PREMIUM")]),
]


def _heart(name: str):
    # (v17.4: the checklist's series counts too — "Dino 206 GT" → ❤️ FERRARI)
    n = " " + re.sub(r"[^a-z0-9& ]", " ", (name or "").lower()) + " " + _hw_series_text(name)
    for emoji, keys in _HEARTS:
        for k, label in keys:
            if " " + re.sub(r"[^a-z0-9& ]", " ", k) + " " in n:
                return emoji, label
    return "🎯", "WATCHLIST"


def _badge(d):
    """(emoji, LABEL) for a 🎯 car's own message, or None for any other car."""
    kind = hw_priority(d["name"])
    marque = _heart(d["name"]) if _is_marque_flagged(d) else None
    if kind:
        e, label = _HW_KINDS[kind]
        # v17.3: which line it's from, when it isn't Hot Wheels mainline
        line = _line_label(d["name"])
        if line:
            label = f"{label} · {line}"
        if marque and marque[0] != "🎯":
            return e + marque[0], f"{label} · {marque[1]}"
        return e, label
    return marque


def _line_label(name: str):
    """'MATCHBOX', 'MAJORETTE', 'MONSTER TRUCKS', 'MINI GT' or None (Hot Wheels)."""
    for label, rx in _LINE_RES:
        if rx.search(name or ""):
            return label
    if re.search(r"\bmini\s*-?\s*gt\b|\bkaido\b", name or "", re.I):
        return "MINI GT"
    return None


def _hw_line(d) -> str:
    """One line on what the car is: its case, series and number, Treasure Hunt
    / Super Treasure Hunt / chase — or "" when unknown."""
    name = d.get("name", "")
    info = hw_info(name)
    bits = []
    if info:
        where = f"{info['y']} Case {info['c']}"
        if info.get("sth"):
            bits.append(f"💎 Super Treasure Hunt · {where}")
        elif info.get("th"):
            bits.append(f"🏆 Treasure Hunt · {where}")
        else:
            bits.append(f"📦 {where}")
        if info.get("ser") and info["ser"].upper() != "TBD":
            bits.append(info["ser"])
        if info.get("n"):
            bits.append(f"#{info['n']}")
        if info.get("sth_col"):
            bits.append(f"💎 its Super TH ({info['sth_col']}) is in this case")
    else:
        if _HW_STH_WORDS.search(name):
            bits.append("💎 Super Treasure Hunt")
        elif _HW_TH_WORDS.search(name):
            bits.append("🏆 Treasure Hunt")
    kind = hw_priority(name)
    if kind == "schase":
        bits.append("💎 Super Chase")
    elif kind == "chase" or (_HW_CHASE_WORDS.search(name) and not _CHASE_TITLE.search(name)):
        bits.append("⛓️ Chase")
    return " · ".join(bits)


def _line(d, extra="") -> str:
    tag = SRC.get(d["source"], "")
    flag = " 🎯" if _is_flagged(d) else ""
    cnt = d.get("stock_count")
    if isinstance(cnt, int) and cnt > 0:
        # how many the store has right now — "only 3 left" means move fast.
        # FirstCry's numbers are for the whole country: only your own cart
        # knows how many can reach 248001 (21 Oct: an alert said plenty, the
        # cart said 1 left, not deliverable) — so the alert says so (v16.3)
        if d.get("fc_cart") == "y":
            # v17: what FirstCry's cart can send to your pincode
            where = f" for {FC_PINCODE}"
            flag += f" ⚠️ only {cnt} left{where}" if cnt <= FC_LOW_STOCK else f" ✅ {cnt} left{where}"
        else:
            where = " (all-India)" if d.get("source") == "firstcry" else ""
            flag += f" ⚠️ only {cnt} left{where}" if cnt <= FC_LOW_STOCK else f" 📦 {cnt} left{where}"
    price = d.get("price", "")
    mrp = f" <s>{d['mrp']}</s>" if d.get("mrp") else ""
    url = fc_fresh_link(d["url"]) if d.get("source") == "firstcry" else d["url"]
    info = _hw_line(d)
    info = f"\n{info}" if info else ""
    if d.get("fc_cart") == "y" and d.get("fc_cart_eta"):
        info += f"\n🚚 cart says: delivery by {d['fc_cart_eta']}"
    if d.get("fc_fast"):
        # v17.4: a fresh release ahead of its product page
        info += ("\n📄 just released — its page may still say Out of Stock: tap ♡, then add it "
                 "to the cart from Favourites in your Profile")
    if d.get("fc_cart_unchecked"):
        info += "\n⚠️ FirstCry's cart couldn't be checked this time — check delivery before paying"
    return f"[{tag}] <b>{html.escape(d['name'], quote=False)}</b>{flag}  {price}{mrp}{extra}{info}\n{url}"


def _flagged_first(items: list) -> list:
    """🎯 cars (your marques / watchlist) at the top of each section."""
    return sorted(items, key=lambda d: 0 if _is_flagged(d) else 1)


def _priority_rank(d) -> int:
    k = hw_priority(d["name"])
    return _HW_RANK.get(k, 9)


# 👀 "new listing — sold out" alerts tell you about a car you can't buy. Off by
# default; its restock still alerts normally. Set ALERT_NEW_SOLD_OUT=true to get
# them back.
ALERT_NEW_SOLD_OUT = os.getenv("ALERT_NEW_SOLD_OUT", "false").lower() == "true"


def _dedupe(items: list, seen_keys: set) -> list:
    """One line per car per message: FirstCry sometimes lists the same car under
    more than one product id, which showed up as the same name twice."""
    out = []
    for d in items:
        key = (d.get("source"), re.sub(r"[^a-z0-9]", "", str(d.get("name", "")).lower()))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(d)
    return out


def build_alerts(ch: dict) -> list:
    """The messages for one store's changes. v16: every 🎯 car that's in stock
    (new or back) gets its own message whose first line says what it is —
    🏆 TREASURE HUNT, 💎 SUPER TREASURE HUNT, ❤️ FERRARI, 🖤 PORSCHE … — so the
    lock screen tells you at a glance; Treasure Hunts and the like go first.
    Everything else follows in one message, as before."""
    shown, solo = set(), []
    for key, event in (("new_listings", "NEW IN STOCK"), ("restocks", "BACK IN STOCK")):
        items = ch.get(key) or []
        if key == "new_listings":
            items = [d for d in items if _within_budget(d)]
        for d in items:
            b = _badge(d)
            if b:
                solo.append((_priority_rank(d), b, event, d))
    out = []
    for _, (emoji, label), event, d in sorted(solo, key=lambda x: x[0]):
        if not _dedupe([d], shown):
            continue
        out.append(f"{emoji} <b>{label} · {event}</b>\n" + _line(d))
    rest = build_alert(ch, shown)
    if rest:
        out.append(rest)
    return out


def build_alert(ch: dict, shown: set | None = None) -> str | None:
    parts = []
    shown = set() if shown is None else shown

    # ── In-stock alerts (loud) ─────────────────────────────────────────────────
    news = _flagged_first(_dedupe([d for d in ch["new_listings"] if _within_budget(d)], shown))
    if news:
        parts.append("🆕 <b>NEW — in stock</b>")
        parts += ["  " + _line(d) for d in news[:25]]

    restocks = _flagged_first(_dedupe(ch["restocks"], shown))
    if restocks:
        parts.append(("\n" if parts else "") + "🔥 <b>BACK IN STOCK — grab it now</b>")
        parts += ["  " + _line(d) for d in restocks[:25]]

    drops = _flagged_first(_dedupe(ch["price_drops"], shown))
    if drops:
        parts.append(("\n" if parts else "") + "💸 <b>PRICE DROP</b>")
        parts += ["  " + _line(d, extra=f"  (was {d['prev_price']})") for d in drops[:25]]

    # ── Newly listed but sold out (quiet — always show, capped at 8) ──────────
    # These are worth knowing about: hit the 💙 wishlist button on the site so
    # Minifygram notifies you when they restock. Next run the bot will catch the
    # restock itself too.
    bs = (_dedupe([d for d in ch["back_soon"] if _within_budget(d)], shown)
          if ALERT_NEW_SOLD_OUT else [])
    if bs:
        parts.append(("\n" if parts else "") + "👀 <b>NEW listing — sold out (wishlist it!)</b>")
        parts += ["  " + _line(d) + "  <i>sold out</i>" for d in bs[:8]]

    if not parts:
        return None
    # No banner line: the notification preview starts straight with what
    # happened and the first car, so you can decide from the lock screen.
    return "\n".join(parts)


def heartbeat(current: dict, ch: dict) -> str:
    by = {}
    for d in current.values():
        by.setdefault(d["source"], [0, 0])
        by[d["source"]][0] += 1
        if d["stock"] == "in_stock":
            by[d["source"]][1] += 1
    lines = ["💓 <b>Heartbeat</b> — tracker is alive"]
    for src, label in (("firstcry", "🛒 FirstCry"), ("minifygram", "💎 Minifygram"),
                       ("hamleys", "🧸 Hamleys"), ("karzdolls", "🏁 Karz&Dolls"),
                       ("bigbasket", "🧺 BigBasket"), ("blinkit", "⚡ Blinkit")):
        if src in by:
            total, ins = by[src]
            lines.append(f"{label}: {ins} in stock / {total} tracked")
        else:
            lines.append(f"{label}: ⚠️ no data this run")
    changes = sum(len(v) for v in ch.values())
    lines.append(f"\nChanges this run: {changes}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════════
def _source_table(snap: dict, fc_full: bool):
    return (("FirstCry",   lambda: scrape_firstcry(snap, full=fc_full)),
            ("Minifygram", scrape_minifygram),
            ("Hamleys",    scrape_hamleys),
            ("Karz&Dolls", scrape_karzanddolls),
            ("BigBasket",  scrape_bigbasket),
            ("Blinkit",    scrape_blinkit))


def _due(name: str, t: float, t_prev: float) -> bool:
    """Is a store due at time t, looking back to t_prev?

    Stateless on purpose: a store checked every E seconds is due when a multiple
    of E on the wall clock fell between t_prev and t. Chained runs (one a
    minute, each looking back 60 s) therefore share one schedule without
    storing timestamps in seen.json — storing them would change the file on
    every run and force a git commit every minute."""
    if ACTIVE_SOURCES is not None:
        return name in ACTIVE_SOURCES
    every = SOURCE_EVERY.get(name, 0)
    if every < 0:
        return False
    if every == 0:
        return True
    return int(t // every) != int(t_prev // every)


def _successor_waiting():
    """Is another run of this workflow already waiting to start? True / False,
    or None when GitHub can't be asked (then the run just ends on time)."""
    repo, me = os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_RUN_ID", "")
    if not (repo and me):
        return None
    wf = os.getenv("GITHUB_WORKFLOW_REF", "").split("@")[0].rsplit("/", 1)[-1] or "monitor.yml"
    hdr = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
           "User-Agent": "hw-tracker"}
    tok = os.getenv("GITHUB_TOKEN", "")
    if tok:
        hdr["Authorization"] = f"Bearer {tok}"
    try:
        r = http.get(f"https://api.github.com/repos/{repo}/actions/workflows/{wf}/runs?per_page=10",
                     headers=hdr, timeout=10)
        if r.status_code != 200:
            return None
        runs = (r.json() or {}).get("workflow_runs") or []
    except Exception:
        return None
    return any(str(x.get("id")) != me and x.get("status") in ("queued", "pending", "waiting", "requested")
               for x in runs)


def _absence_check(seen: dict, products: list, src_key: str) -> list:
    """Karz & Dolls category pages list the whole category and simply DROP a car
    when it sells out, so a car we believed in stock that is missing from a
    healthy scrape is recorded as sold out — that's what lets its return fire a
    restock alert. Skipped when the scrape looks partial."""
    if src_key not in ABSENCE_SOURCES:
        return []
    got = {p["id"] for p in products if p["source"] == src_key}
    if not got:
        return []
    if src_key == "karzdolls" and not KD_HEALTHY[0]:
        print("[!] karzdolls: a category page failed — skipping absence check")
        return []
    prev_in = {k for k, v in seen.items()
               if k != "_meta" and isinstance(v, dict)
               and v.get("source") == src_key and v.get("stock") == "in_stock"}
    if prev_in and len(got) < 0.6 * len(prev_in):
        print(f"[!] {src_key}: only {len(got)} vs {len(prev_in)} last time — "
              f"skipping absence check (likely a partial fetch)")
        return []
    gone = []
    for k, v in seen.items():
        if (k == "_meta" or not isinstance(v, dict) or v.get("source") != src_key
                or k in got or v.get("stock") != "in_stock"):
            continue
        gone.append({"id": k, "source": src_key, "name": v.get("name", ""),
                     "url": v.get("url", ""), "price": v.get("price", ""), "mrp": "",
                     "stock": "out_of_stock", "badge_new": False})
    if gone:
        print(f"[*] {src_key}: {len(gone)} product(s) no longer listed → marked sold out")
    return gone


def _process(seen: dict, products: list, store: str, quiet: bool) -> int:
    """Diff ONE store's fresh results against memory, alert at once, save.
    Each store is handled the moment its own check finishes, so a FirstCry
    alert never waits for a slower store (Hamleys can take 20 s)."""
    if not products:
        return 0
    src_keys = {p["source"] for p in products}
    for sk in list(src_keys):
        products = products + _absence_check(seen, products, sk)

    # Global keyword exclusion — every store, not just FirstCry.
    if FC_EXCLUDE:
        products = [p for p in products if not _fc_excluded(p["name"])]
    if not products:
        return 0
    current = {p["id"]: p for p in products}

    # The first time a store appears (a newly added store) while others already
    # have history, its whole catalogue is absorbed silently.
    known_sources = {v.get("source") for k, v in seen.items()
                     if k != "_meta" and isinstance(v, dict)}
    for s in src_keys - known_sources:
        items = [pid for pid, d in current.items() if d["source"] == s]
        ins = sum(1 for pid in items if current[pid]["stock"] == "in_stock")
        for pid in items:
            seen.setdefault(pid, {})["alerted_new"] = True
        print(f"[=] New source '{s}': baseline {len(items)} items absorbed silently.")
        tg(f"🆕 <b>New store added:</b> {SRC.get(s, s)} — tracking {len(items)} products "
           f"({ins} in stock). Alerts start from the next change.")

    # FirstCry product ids only ever increase: an id above every id seen before
    # is a genuinely NEW listing. Captured before compute_changes adds this pass.
    fc_max_known = 0
    if "firstcry" in src_keys:
        _ids = [int(k[3:]) for k, v in seen.items()
                if k.startswith("fc_") and k[3:].isdigit() and isinstance(v, dict)]
        fc_max_known = max(_ids) if _ids else 0

    # Cars found on a product page that the listing never showed (other cars of
    # the same colour set) start being tracked silently — they aren't new.
    for pid, d in current.items():
        if d.get("fc_absorb") and pid not in seen:
            seen[pid] = {"alerted_new": True}

    changes = compute_changes(current, seen)

    # Verify FirstCry restocks read from HTML (fallback path only) before alerting.
    if "firstcry" in src_keys:
        try:
            n_sup = fc_confirm_restocks(changes, current)
            if n_sup:
                print(f"[*] suppressed {n_sup} unconfirmed FirstCry restock(s)")
        except Exception as exc:
            print(f"[!] restock confirmation skipped: {exc}")

    # ── Discovery-burst guard ──────────────────────────────────────────────────
    # A genuine drop is a handful of new products. If a store suddenly surfaces
    # MANY never-seen items at once, that's coverage expanding (a new category, a
    # site change) — absorbed with a one-line note. Brand-new FirstCry ids are
    # never absorbed: a case drop really does list 10-20 cars at once.
    BURST_LIMIT = int(os.getenv("DISCOVERY_BURST_LIMIT", "8"))

    def _fresh_fc(d):
        k = d["id"]
        return (d["source"] == "firstcry" and fc_max_known > 0
                and k[3:].isdigit() and int(k[3:]) > fc_max_known)

    for src_key in src_keys:
        burst = [d for d in (changes["new_listings"] + changes["back_soon"])
                 if d["source"] == src_key and not _fresh_fc(d) and not d.get("_known")]
        if len(burst) > BURST_LIMIT:
            drop = {d["id"] for d in burst}
            changes["new_listings"] = [d for d in changes["new_listings"] if d["id"] not in drop]
            changes["back_soon"] = [d for d in changes["back_soon"] if d["id"] not in drop]
            ins = sum(1 for d in burst if d["stock"] == "in_stock")
            print(f"[=] Discovery burst from {src_key}: {len(burst)} items absorbed.")
            tg(f"📈 <b>Coverage expanded:</b> {SRC.get(src_key, src_key)} +{len(burst)} newly "
               f"tracked products ({ins} in stock). Alerts on changes from here.")

    alerts = build_alerts(changes)
    for i, alert in enumerate(alerts):
        if i:
            time.sleep(0.4)            # Telegram: a burst of messages to one chat
        tg(alert)
        print("\n" + alert)
    if not alerts:
        n = sum(len(v) for v in changes.values())
        if n or not quiet:
            print(f"[=] {store}: no alert-worthy changes ({n} minor)")
    merge_and_save_seen(seen, current)
    return len(current)


def run_pass(seen: dict, names: list, first_run: bool, fc_full: bool, label: str,
             first_pass: bool = True) -> None:
    t0 = time.time()
    snap = dict(seen)            # scrapers read this; only the main thread writes `seen`
    sources = [(n, fn) for n, fn in _source_table(snap, fc_full) if n in names]
    total, errors, live = 0, [], []
    first_products = []
    with ThreadPoolExecutor(max_workers=max(1, min(SRC_WORKERS, len(sources)))) as ex:
        futs = {ex.submit(fn): name for name, fn in sources}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                prods = fut.result() or []
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                print(f"[!] {name} error:\n{traceback.format_exc()}")
                continue
            if prods:
                live.append(name)
            total += len(prods)
            if first_run and FIRST_RUN_SILENT:
                first_products.extend(prods)
                continue
            try:
                _process(seen, prods, name, quiet=not first_pass)
            except Exception:
                errors.append(f"{name}: processing failed")
                print(f"[!] {name} processing error:\n{traceback.format_exc()}")
    print(f"[*] {label}: {', '.join(names)} → {total} products in {time.time()-t0:.1f}s"
          + (f" (live: {', '.join(sorted(live))})" if live else ""))
    if "Minifygram" in names and _MG_LAST_WM[0]:
        meta = seen.setdefault("_meta", {})
        if meta.get("mg_wm") != _MG_LAST_WM[0]:
            meta["mg_wm"] = _MG_LAST_WM[0]
            _save_seen_file(seen)

    if first_run and FIRST_RUN_SILENT and first_products:
        # First run only learns the baseline — no flood of "new" alerts.
        current = {p["id"]: p for p in first_products if not _fc_excluded(p["name"])}
        for pid in current:
            seen.setdefault(pid, {})["alerted_new"] = True
        by_src = {}
        for d in current.values():
            by_src.setdefault(d["source"], [0, 0])
            by_src[d["source"]][0] += 1
            if d["stock"] == "in_stock":
                by_src[d["source"]][1] += 1
        breakdown = "\n".join(f"  {SRC.get(s, s)} {v[1]} in stock / {v[0]} total"
                              for s, v in by_src.items())
        print(f"[=] First run: baseline saved ({len(current)} products). No alerts.")
        tg(f"✅ <b>Hot Wheels Tracker armed</b>\nBaseline: {len(current)} products\n"
           f"{breakdown}\n\nYou'll get pinged on new listings, restocks &amp; price drops.")
        merge_and_save_seen(seen, current)
        return

    if (total == 0 and first_pass and ACTIVE_SOURCES is None
            and len(names) >= 3 and errors):
        # Only shout if EVERYTHING died on a full pass — actionable, not spammy.
        tg("⚠️ <b>Hot Wheels Tracker</b>\nAll stores returned nothing this run "
           "(likely a temporary block). Will retry automatically.\n"
           f"<code>{html.escape('; '.join(errors)[:300], quote=False)}</code>")
    if DEBUG and first_pass:
        tg(heartbeat({k: v for k, v in seen.items()
                      if k != "_meta" and isinstance(v, dict) and "source" in v},
                     {"new_listings": [], "restocks": [], "price_drops": [], "back_soon": []}))


def main():
    t_run = time.time()
    seen = load_seen()
    first_run = (len(seen) == 0)
    _fc_fresh_load(seen)
    if FC_LIVE:
        meta = seen.setdefault("_meta", {}) if isinstance(seen.get("_meta", {}), dict) else {}
        if not meta.get("fc_live_since"):
            meta["fc_live_since"] = _bucket(time.strftime("%Y-%m-%dT%H:%M:%S"))
        _FC_LIVE_SINCE[0] = meta["fc_live_since"]

    # One-time migration: entries written by the old overwrite-style seen.json
    # lack the alerted_new flag — treat them all as already alerted.
    if seen and not any("alerted_new" in v for k, v in seen.items()
                        if k != "_meta" and isinstance(v, dict)):
        for k, v in seen.items():
            if k != "_meta" and isinstance(v, dict):
                v["alerted_new"] = True
        print(f"[~] Migrated {len(seen)} legacy seen entries (marked already-alerted).")

    all_names = [n for n, _ in _source_table(seen, False)]
    # Runs are chained back to back about a minute apart. The slower stores
    # are only checked in each run's FIRST pass, looking back over the last
    # 60 s for a due time, so the later passes are quick FirstCry-only checks
    # and every run finishes before the next trigger arrives.
    look_back = t_run - 60
    pass_no = 0
    extended, ext_since = False, None
    timings = []
    while True:
        t = time.time()
        pass_no += 1
        if pass_no == 1:
            names = [n for n in all_names if _due(n, t, look_back)]
            fc_full = ("FirstCry" in names and
                       (int(t // FC_CATALOGUE_EVERY) != int(look_back // FC_CATALOGUE_EVERY)
                        or not any(k.startswith("fc_") for k in seen)))
        else:
            names = ["FirstCry"] if "FirstCry" in all_names and _due("FirstCry", t, t) else []
            fc_full = False
            if ext_since is not None and ACTIVE_SOURCES is None:
                # Staying on past RUN_SECONDS: the next run's look-back won't
                # reach back this far, so stores falling due since this run
                # began are checked here instead of being skipped.
                names += [n for n in all_names if n != "FirstCry" and _due(n, t, ext_since)]
                fc_full = ("FirstCry" in names and
                           int(t // FC_CATALOGUE_EVERY) != int(ext_since // FC_CATALOGUE_EVERY))
                ext_since = t
        if ("Minifygram" not in names and MG_WATCH and ACTIVE_SOURCES is None
                and SOURCE_EVERY.get("Minifygram", 0) >= 0 and not first_run):
            wm = mg_watermark()
            meta = seen.get("_meta") if isinstance(seen.get("_meta"), dict) else {}
            if wm and wm != meta.get("mg_wm"):
                print("[*] Minifygram changed since the last check — checking it now")
                names.append("Minifygram")
        label = f"pass {pass_no}" + (" (+ full FirstCry catalogue)" if fc_full else "")
        if names:
            try:
                run_pass(seen, names, first_run, fc_full, label, first_pass=(pass_no == 1))
            except Exception:
                # one bad pass must not end the run (earlier results are saved)
                print(f"[!] {label} failed:\n{traceback.format_exc()}")
        timings.append(f"{int(t - t_run)}s:{'+'.join(n[:2] for n in names) or '-'}={time.time() - t:.0f}s")
        if first_run or RUN_SECONDS <= 0:
            break
        nxt = t + FC_EVERY
        if nxt - t_run > RUN_SECONDS:
            # time's up — unless nobody is waiting to take over (a skipped or
            # late trigger): then keep watching, up to RUN_EXTEND_S longer
            if nxt - t_run > RUN_SECONDS + RUN_EXTEND_S or _successor_waiting() is not False:
                break
            if not extended:
                print("[*] no run waiting to take over (trigger skipped or late) — still watching")
                extended, ext_since = True, t_run
        time.sleep(max(0.0, nxt - time.time()))
    _fc_fresh_save(seen)
    took = time.time() - t_run
    print(f"\n[*] run finished: {pass_no} pass(es) in {took:.0f}s ({', '.join(timings)})")
    if _ON_GITHUB and took > RUN_SECONDS + RUN_EXTEND_S + 25:
        # visible in the run's summary and through the API, without the logs
        print(f"::notice title=Long run ({took:.0f}s)::{', '.join(timings)[:900]}")


if __name__ == "__main__":
    main()
