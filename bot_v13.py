#!/usr/bin/env python3
"""
Hot Wheels / Diecast Collector Tracker  ·  v13
==============================================
Stores  : FirstCry · Minifygram · Karz & Dolls · Hamleys  (Dehradun 248001)
          (Blinkit / BigBasket block GitHub's servers — phone watcher covers them)
Runtime : Pure HTTP (curl_cffi with a real Chrome fingerprint). No browser.
Host    : GitHub Actions, triggered every minute by cron-job.org; state lives in
          seen.json, committed back after each run.

HOW A RUN WORKS (v13)
---------------------
Each run stays alive RUN_SECONDS (45 s on GitHub) and checks in passes:
  • FirstCry every FC_EVERY seconds (15 s): a full catalogue sweep first, then
    quick sweeps of the in-stock list. Every request asks for a cache key
    FirstCry hasn't built yet, so the data is computed live — the plain request
    the bot used to make was answered from a 15-minute cache (measured: 9-15
    minutes old), which is why alerts used to arrive after cars had sold out.
  • Minifygram: full list every 2 min, plus a tiny "anything changed?" check
    every pass that pulls new listings in within seconds. Trading cards too.
  • Karz & Dolls every 2 min, read from the JSON the site embeds in its pages.
  • Hamleys every 10 min.
Alerts go out the moment a store's check finishes; nothing waits for slower
stores. Runs are chained back to back, so the watch is continuous.

ALERTS
------
🆕 new listing (in stock) · 🔥 back in stock · 💸 price drop
🎯 = one of your marques / watchlist (listed first) · 📦/⚠️ = units left
Every product's NEW alert fires once ever; restocks have a 24 h cooldown.
"""

import os
import re
import json
import html
import time
import traceback
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
FC_EVERY      = max(8.0, float(os.getenv("FC_EVERY", "15")))
# Within a long run, a FULL catalogue sweep happens at least this often; the
# sweeps in between are quick "hot" sweeps of the in-stock part of the catalogue.
FC_FULL_EVERY = float(os.getenv("FC_FULL_EVERY", "60"))

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
                  "fc_listed_at", "fc_api_seen_at", "fc_trusted"):
            v = d.get(k, prev.get(k, ""))
            if k in ("hm_verified_at", "fc_listed_at", "fc_api_seen_at") and isinstance(v, str):
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
                        "pit stop,action set,crash & track,ultimate")
              .split(",") if w.strip()]

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
    return any(k in n for k in FC_MARQUES)


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
    "|".join(r"\b" + re.escape(k) for k in FC_EXCLUDE), re.I
) if FC_EXCLUDE else None



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
    if not _FC_EXCL_RE:
        return False
    return bool(_FC_EXCL_RE.search(name or ""))


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
_FC_PREV_INSTOCK = [None]  # ids on the previous complete in-stock list (this run)
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
                and 0 < count < FC_MIN_ALERT_STOCK):
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


def scrape_firstcry(prev_all: dict | None = None, hot: bool = False) -> list[dict]:
    if prev_all is None:
        prev_all = load_seen()
    prev_fc = {pid[3:]: v for pid, v in prev_all.items()
               if pid.startswith("fc_") and isinstance(v, dict)}

    # ── Quick sweep: in-stock part of the catalogue only ──────────────────────
    # Only cars actually read are returned; everything else keeps its last state
    # until the next full sweep (nothing is inferred from absence here).
    if hot:
        if not FC_USE_API or FC_LAST_MODE[0] == "html":
            return []
        if FC_THROTTLED[0] > time.time():
            print("  [FC-API] quick sweeps paused — FirstCry answered 429/403 recently")
            return []
        api = fc_api_catalogue(hot=True)
        if api is None:
            return []
        recs = fc_api_records(api, prev_fc, quiet=True)
        # A car that WAS on the previous complete in-stock list and has dropped
        # off this one has sold out. Recording that now (instead of at the next
        # full sweep) means a sell-out followed by a quick restock still fires
        # its alert. Only list-to-list changes count: the in-stock filter and
        # the full catalogue can disagree about a handful of cars (live dry run:
        # 182 vs 178), and those must never flip-flop into false restocks.
        listed = {str(pid) for pid in api}
        prev_listed = _FC_PREV_INSTOCK[0]
        _FC_PREV_INSTOCK[0] = listed if FC_LAST_SWEEP["complete"] else None
        if FC_LAST_SWEEP["complete"] and prev_listed:
            got = {r["id"][3:] for r in recs}
            prev_in = [pid for pid in prev_listed - listed
                       if (prev_fc.get(pid) or {}).get("stock") == "in_stock"
                       and not _fc_excluded((prev_fc.get(pid) or {}).get("name", ""))]
            if len(listed) >= 0.7 * len(prev_listed):
                for pid in prev_in:
                    if pid in got:
                        continue
                    v = prev_fc[pid]
                    nm = v.get("name", "")
                    recs.append({
                        "id": f"fc_{pid}", "source": "firstcry", "name": nm,
                        "url": v.get("url") or f"https://www.firstcry.com/x/x/{pid}/product-detail",
                        "price": v.get("price", ""), "mrp": "", "stock": "out_of_stock",
                        "badge_new": False, "watched": pid in FC_WATCH_IDS or _fc_is_marque(nm),
                        "auto_watch": _fc_is_marque(nm),
                        "stock_ver": FC_API_STOCK_VER, "fc_trusted": True,
                        "fc_listed_at": v.get("fc_listed_at", ""),
                        "fc_api_seen_at": v.get("fc_api_seen_at", ""),
                    })
        return recs

    # ── Preferred path: FirstCry's own JSON catalogue API ──────────────────────
    if FC_USE_API:
        api = fc_api_catalogue()
        if api:
            recs = fc_api_records(api, prev_fc)
            got = {r["id"][3:] for r in recs}
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
            # A product missing from the API is only treated as delisted once it
            # has been absent for FC_STALE_H hours. The first version flipped
            # everything missing immediately — and when a response was cut short
            # (as happened with the TTL bug) that marked 209 cars sold out at once,
            # setting up a flood of false "restocks" when they reappeared. Aging
            # means a truncated response can never cause that: a car only flips
            # after hours of consistent absence, and its return is a real relisting.
            delisted = 0
            for pid, v in prev_fc.items():
                if pid in got or not pid.isdigit():
                    continue
                nm = v.get("name", "")
                if not nm or _fc_excluded(nm):
                    continue
                st = v.get("stock")
                if st is None:
                    continue
                seen_at = v.get("fc_api_seen_at") or now_iso      # grace for old entries
                if (st == "in_stock" and FC_API_COMPLETE[0]
                        and _hours_since(seen_at) >= FC_STALE_H):
                    st, delisted = "out_of_stock", delisted + 1
                recs.append({
                    "id": f"fc_{pid}", "source": "firstcry", "name": nm,
                    "url": v.get("url") or f"https://www.firstcry.com/x/x/{pid}/product-detail",
                    "price": v.get("price", ""), "mrp": "", "stock": st,
                    "badge_new": False, "watched": pid in FC_WATCH_IDS or _fc_is_marque(nm),
                    "auto_watch": _fc_is_marque(nm),
                    # NOT re-stamped. The v11.2 bug stamped carried (unread) cars
                    # with the current version, disguising a stale "sold out" as
                    # a fresh reading — so when those cars were finally read, a
                    # false "restock" fired. Carried cars now keep exactly the
                    # version and trust they already had.
                    "stock_ver": v.get("stock_ver", ""),
                    "fc_trusted": bool(v.get("fc_trusted")),
                    "fc_listed_at": v.get("fc_listed_at", ""),
                    "fc_api_seen_at": seen_at,
                })
            ins = sum(1 for r in recs if r["stock"] == "in_stock")
            low = sum(1 for r in recs if r.get("stock_count")
                      and 0 < r["stock_count"] <= FC_LOW_STOCK)
            FC_LAST_MODE[0] = "api"
            print(f"[*] FirstCry total (API): {len(recs)} ({ins} in stock, "
                  f"{low} low-stock, {delisted} aged to delisted)")
            return recs
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
    if any(tok in brand or tok in name for tok in MG_BRANDS):
        if not cat or not MG_CAR_CATEGORIES or any(t in cat for t in MG_CAR_CATEGORIES):
            return "car"
    return None


def _mg_preorder_open(row: dict) -> bool:
    """A pre-order can be booked: not closed by status or by its closing time."""
    st = str(row.get("preorder_status") or "").lower()
    if st in ("booking_closed", "closed", "cancelled", "canceled"):
        return False
    close = str(row.get("preorder_close_at") or "")
    if close:
        try:
            ts = time.mktime(time.strptime(close[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
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
            # v13: pre-orders count as available only while booking is open,
            # trading cards added. The version bump applies the new reading
            # once, silently, instead of alerting on the changed rules.
            "stock_ver": "mg_skus_v2",
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
KD_URLS = ([u.strip() for u in os.getenv("KD_URLS", "").split("|") if u.strip()]
           or _KD_DEFAULT_URLS)
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


def _kd_from_next_data(page: str, cat: str):
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
        blob = (name + " " + line).upper()
        flat = blob.replace(" ", "").replace("-", "")
        if any(k in flat for k in _KD_DENY):
            continue
        is_hw_line = blob.startswith("HW ") or " HW " in f" {line.upper()} "
        if not (cat_ok or is_hw_line or any(k in flat for k in _KD_BRAND_TOKENS)):
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
            "name": (name + (" [PRE-ORDER]" if is_pre else ""))[:180],
            "url": f"{_KD}/details/{quote(slug, safe='-_.~')}?pid={quote(pid, safe='')}",
            "price": f"₹{price}", "mrp": f"₹{mrp}" if mrp and mrp > price else "",
            "stock": "in_stock" if str(p.get("in_stock")) in ("1", "True", "true") else "out_of_stock",
            "badge_new": False,
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
        pages = {ex.submit(fetch, u): u for u in KD_URLS}
        for fut in as_completed(pages):
            u = pages[fut]
            cat = u.rstrip("/").rsplit("/", 1)[-1] if u.rstrip("/") != _KD else ""
            try:
                page = fut.result()
            except Exception:
                page = None
                KD_HEALTHY[0] = False
            if not page:
                continue
            # Preferred: the product list Next.js embeds in the page as JSON
            # (exact names, prices, in_stock and pre-order flags). The HTML card
            # parser below is the fallback if that ever disappears.
            recs = _kd_from_next_data(page, cat)
            if recs is not None:
                found = 0
                for d in recs:
                    if d["id"] not in seen_ids:
                        seen_ids.add(d["id"])
                        out.append(d)
                        found += 1
                if found:
                    print(f"  [KD] {cat or 'home'} → {found}")
                elif recs:
                    print(f"  [KD] {cat or 'home'} → 0 new ({len(recs)} already listed elsewhere)")
                else:
                    print(f"  [KD] {cat or 'home'} → 0 (empty right now)")
                continue
            found = 0
            for part in re.split(r'(?=<a[^>]+href="/details/)', page):
                lm = _KD_LINK.search(part or "")
                if not lm:
                    continue
                path = html.unescape(lm.group(1))
                pm = _KD_PID.search(path)
                if not pm:
                    continue
                pid = pm.group(1)
                uid = f"kd_{pid}"
                if uid in seen_ids:
                    continue
                txt = _clean(part[:3000])
                nm = re.search(r'([A-Z0-9][A-Z0-9 ()\'"“”\.\,/&#\-\+]{8,150}?)\s*₹', txt)
                if not nm:
                    continue
                name = re.sub(r"\s+", " ", nm.group(1)).strip(" -–|,")[:180]
                if len(name) < 6:
                    continue
                up = part.upper()
                is_pre = "PRE-ORDER" in up or "PRE ORDER" in up or name.startswith("PREORDER")
                if is_pre and not KD_INCLUDE_PREORDER:
                    continue
                # deny-list is matched against the card's opening text (badge +
                # SKU line + name) because the brand often appears ONLY in the
                # SKU line, e.g. "1:43 SOLIDO 421438273".
                deny_scope = txt[:250].upper().replace(" ", "").replace("-", "")
                if any(k in deny_scope for k in _KD_DENY):
                    continue
                sku = ""
                sm = re.search(r'((?:MINI\s*GT|HOT\s*WHEELS|HOTWHEELS|KAIDO)[A-Z0-9 \-]{0,30})',
                               txt, re.I)
                if sm:
                    sku = sm.group(1).strip()
                blob = (name + " " + sku).upper().replace(" ", "")
                if not any(k in blob for k in ("MINIGT", "HOTWHEELS", "KAIDO")):
                    if not any(k in cat for k in ("hot-wheels", "mini-gt", "kaido", "minigt")):
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
                seen_ids.add(uid)
                out.append({
                    "id": uid, "source": "karzdolls",
                    "name": (name + (" [PRE-ORDER]" if is_pre else ""))[:180],
                    "url": _KD + quote(path, safe="/:?=&"),
                    "price": f"₹{price}", "mrp": f"₹{mrp}" if mrp else "",
                    "stock": stock, "badge_new": "NEW ARRIVAL" in up,
                })
                found += 1
            if found:
                print(f"  [KD] {cat or 'home'} → {found}")
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
            continue

        prev_stock = prev.get("stock")
        prev_price = price_to_int(prev.get("price"))

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

        if (stock == "in_stock" and prev_stock == "out_of_stock"
                and not is_correction
                and _hours_since(prev.get("last_restock_alert", "")) >= RESTOCK_COOLDOWN_H):
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


def _is_flagged(d) -> bool:
    return bool(d.get("watched")) or any(w in d["name"].lower() for w in WATCHLIST)


def _line(d, extra="") -> str:
    tag = SRC.get(d["source"], "")
    flag = " 🎯" if _is_flagged(d) else ""
    cnt = d.get("stock_count")
    if isinstance(cnt, int) and cnt > 0:
        # how many FirstCry has right now — "only 3 left" means move fast
        flag += f" ⚠️ only {cnt} left" if cnt <= FC_LOW_STOCK else f" 📦 {cnt} left"
    price = d.get("price", "")
    mrp = f" <s>{d['mrp']}</s>" if d.get("mrp") else ""
    return f"[{tag}] <b>{html.escape(d['name'], quote=False)}</b>{flag}  {price}{mrp}{extra}\n{d['url']}"


def _flagged_first(items: list) -> list:
    """🎯 cars (your marques / watchlist) at the top of each section."""
    return sorted(items, key=lambda d: 0 if _is_flagged(d) else 1)


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


def build_alert(ch: dict) -> str | None:
    parts = []
    shown = set()

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
def _source_table(snap: dict, fc_hot: bool):
    return (("FirstCry",   lambda: scrape_firstcry(snap, hot=fc_hot)),
            ("Minifygram", scrape_minifygram),
            ("Hamleys",    scrape_hamleys),
            ("Karz&Dolls", scrape_karzanddolls),
            ("BigBasket",  scrape_bigbasket),
            ("Blinkit",    scrape_blinkit))


def _due(name: str, t: float, t_prev: float) -> bool:
    """Is a store due in the pass at time t (previous pass at t_prev)?

    Stateless on purpose: a store checked every E seconds runs in whichever pass
    first crosses a multiple of E on the wall clock. Back-to-back runs therefore
    share one schedule without storing timestamps in seen.json — storing them
    would change the file on every run and force a git commit every minute."""
    if ACTIVE_SOURCES is not None:
        return name in ACTIVE_SOURCES
    every = SOURCE_EVERY.get(name, 0)
    if every < 0:
        return False
    if every == 0:
        return True
    return int(t // every) != int(t_prev // every)


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


def _process(seen: dict, products: list, store: str, fc_hot: bool) -> int:
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
                 if d["source"] == src_key and not _fresh_fc(d)]
        if len(burst) > BURST_LIMIT:
            drop = {d["id"] for d in burst}
            changes["new_listings"] = [d for d in changes["new_listings"] if d["id"] not in drop]
            changes["back_soon"] = [d for d in changes["back_soon"] if d["id"] not in drop]
            ins = sum(1 for d in burst if d["stock"] == "in_stock")
            print(f"[=] Discovery burst from {src_key}: {len(burst)} items absorbed.")
            tg(f"📈 <b>Coverage expanded:</b> {SRC.get(src_key, src_key)} +{len(burst)} newly "
               f"tracked products ({ins} in stock). Alerts on changes from here.")

    alert = build_alert(changes)
    if alert:
        tg(alert)
        print("\n" + alert)
    else:
        n = sum(len(v) for v in changes.values())
        if n or not fc_hot:
            print(f"[=] {store}: no alert-worthy changes ({n} minor)")
    merge_and_save_seen(seen, current)
    return len(current)


def run_pass(seen: dict, names: list, first_run: bool, fc_hot: bool, label: str) -> None:
    t0 = time.time()
    snap = dict(seen)            # scrapers read this; only the main thread writes `seen`
    sources = [(n, fn) for n, fn in _source_table(snap, fc_hot) if n in names]
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
                _process(seen, prods, name, fc_hot)
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

    if (total == 0 and not fc_hot and ACTIVE_SOURCES is None
            and len(names) >= 3 and errors):
        # Only shout if EVERYTHING died on a full pass — actionable, not spammy.
        tg("⚠️ <b>Hot Wheels Tracker</b>\nAll stores returned nothing this run "
           "(likely a temporary block). Will retry automatically.\n"
           f"<code>{html.escape('; '.join(errors)[:300], quote=False)}</code>")
    if DEBUG and not fc_hot:
        tg(heartbeat({k: v for k, v in seen.items()
                      if k != "_meta" and isinstance(v, dict) and "source" in v},
                     {"new_listings": [], "restocks": [], "price_drops": [], "back_soon": []}))


def main():
    t_run = time.time()
    seen = load_seen()
    first_run = (len(seen) == 0)
    _fc_fresh_load(seen)

    # One-time migration: entries written by the old overwrite-style seen.json
    # lack the alerted_new flag — treat them all as already alerted.
    if seen and not any("alerted_new" in v for k, v in seen.items()
                        if k != "_meta" and isinstance(v, dict)):
        for k, v in seen.items():
            if k != "_meta" and isinstance(v, dict):
                v["alerted_new"] = True
        print(f"[~] Migrated {len(seen)} legacy seen entries (marked already-alerted).")

    all_names = [n for n, _ in _source_table(seen, False)]
    # Runs are chained back to back, so the previous run's last check was roughly
    # 30 s before this one started; the first pass covers that gap.
    t_prev = t_run - 30
    last_full_fc = 0.0
    pass_no = 0
    while True:
        t = time.time()
        pass_no += 1
        names = [n for n in all_names if _due(n, t, t_prev)]
        if ("Minifygram" not in names and MG_WATCH and ACTIVE_SOURCES is None
                and SOURCE_EVERY.get("Minifygram", 0) >= 0 and not first_run):
            wm = mg_watermark()
            meta = seen.get("_meta") if isinstance(seen.get("_meta"), dict) else {}
            if wm and wm != meta.get("mg_wm"):
                print("[*] Minifygram changed since the last check — checking it now")
                names.append("Minifygram")
        fc_hot = (pass_no > 1 and "FirstCry" in names
                  and (t - last_full_fc) < FC_FULL_EVERY - 1)
        label = f"pass {pass_no}" + (" (FirstCry quick sweep)" if fc_hot else "")
        if names:
            try:
                run_pass(seen, names, first_run, fc_hot, label)
            except Exception:
                # one bad pass must not end the run (earlier results are saved)
                print(f"[!] {label} failed:\n{traceback.format_exc()}")
        if "FirstCry" in names and not fc_hot:
            last_full_fc = t
        t_prev = t
        if first_run or RUN_SECONDS <= 0:
            break
        nxt = t + FC_EVERY
        if nxt - t_run > RUN_SECONDS:
            break
        time.sleep(max(0.0, nxt - time.time()))
    _fc_fresh_save(seen)
    print(f"\n[*] run finished: {pass_no} pass(es) in {time.time()-t_run:.0f}s")


if __name__ == "__main__":
    main()
