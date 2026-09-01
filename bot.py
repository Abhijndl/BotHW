#!/usr/bin/env python3
"""
Hot Wheels / Diecast Collector Tracker  ·  v4 "God Tier"
========================================================
Sources  : FirstCry · Minifygram · Blinkit  (Dehradun 248001)
Runtime  : Pure HTTP. No Playwright, no Chromium, no browser.
Host     : GitHub Actions (free) — runs on a schedule, pushes state back to the repo.

WHY THIS REWRITE
----------------
The old bot launched a headless Chromium via Playwright. On free hosts that
browser frequently fails to install ("Executable doesn't exist … chrome-headless-shell"),
which is exactly the error your Telegram bot kept reporting. It also made every
run slow (~2-3 min) and fragile.

This version never opens a browser. It talks to the same data the websites'
own front-ends use:

  • FirstCry  — the category page is fully server-rendered HTML. We fetch it
                with a real browser TLS fingerprint (curl_cffi) and parse the
                product cards directly. Every SKU, price, MRP, and in-stock /
                notify-me state is right there in the markup.

  • Minifygram — a Supabase-backed React app. We call its public Supabase REST
                 endpoint directly and get clean JSON (id, name, price, stock).
                 The anon key + project URL are auto-discovered from the site's
                 JS bundle at runtime, so it keeps working if they redeploy.

  • Blinkit   — quick-commerce, location-locked. We call the same internal
                search API the website uses, pinned to your Dehradun coordinates.
                Blinkit is the flakiest of the three (aggressive bot defense);
                it's best-effort and never blocks the other two sources.

Each source is independent and wrapped in try/except: one failing never stops
the others. If a source gets blocked, you still get alerts from the rest.

ALERTS
------
new_listing   a SKU we've never seen, in stock  →  🆕
restock       was out of stock, now in stock     →  🔥
price_drop    price fell vs last run             →  💸
back_soon     newly listed but out of stock      →  👀  (so you can wishlist it)

Everything is diffed against seen.json, which the workflow commits back after
each run so state survives between runs.
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

TIMEOUT = 30

# ── Concurrency ────────────────────────────────────────────────────────────────
# Sources run in parallel with each other, and page fetches run in parallel
# within a source. A run drops from ~2 min of sequential fetching to ~20-30s.
SRC_WORKERS = int(os.getenv("SRC_WORKERS", "6"))
FC_WORKERS  = int(os.getenv("FC_WORKERS", "8"))
HM_WORKERS  = int(os.getenv("HM_WORKERS", "8"))

COMMON_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── Telegram ─────────────────────────────────────────────────────────────────────
def tg(msg: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("[TG] (no creds) " + msg[:200]); return
    try:
        r = http.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": "true"},
            timeout=15, **_IMPERSONATE)
        if not r.ok:
            print(f"[TG] {r.status_code}: {r.text[:150]}")
    except Exception as e:
        print(f"[TG] {e}")


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


def merge_and_save_seen(seen: dict, current: dict) -> None:
    """Merge this run's observations into the permanent memory and persist it."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
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
        }
        # per-source bookkeeping (e.g. Minifygram's stock-detection version tag)
        for k in ("mg_updated_at", "stock_ver", "hm_verified_at"):
            v = d.get(k, prev.get(k, ""))
            if v:
                entry[k] = v
        seen[pid] = entry
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)


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
# SOURCE 1 — FirstCry  (listing-card parsing, wide facet coverage)
# ══════════════════════════════════════════════════════════════════════════════════
# v6 FIX — why every FirstCry alert said "sold out":
#   v5 read stock from each PRODUCT page. But FirstCry product pages do NOT
#   server-render the buy box — price and "Add to Cart" are injected by JS, so
#   the HTML we fetch contains neither. The code defaulted to out_of_stock when
#   it couldn't find them, so EVERY product read as sold out. Verified by
#   fetching a live product page: no price, no cart button anywhere in the HTML.
#
#   LISTING pages, by contrast, DO server-render price + ADD TO CART / Notify Me
#   inside each card. So stock now comes from the listing card itself — one
#   fetch gives ~20 products complete with accurate stock, and it's far faster
#   than 40 individual page fetches.
#
# COVERAGE — sort=/ProductPage= params are stripped server-side (both verified),
# so the only way to see beyond one page is different FACET pages. FirstCry's
# character-shop facets (age / sub-type / skills / theme) each return a
# different ~20-product slice; their union is the tracked catalog. Unknown-good
# URLs are harmless: each is logged with how many NEW products it contributed,
# so you can prune or extend the list from the run log.
_FC_FACET = ("https://www.firstcry.com/toy-cars,-trains-and-vehicles/hotwheels"
             "?cid=5&scid=94&character-shop=t5-7701")

# NOTE: these URLs contain commas ("toy-cars,-trains-and-vehicles"), so the env
# override is split on "|" (not ",") — a comma split would shred the paths.
_FC_DEFAULT_URLS = [
    # brand pages
    "https://www.firstcry.com/hot-wheels/0/0/113",
    "https://www.firstcry.com/hot-wheels/5/0/113",
    "https://www.firstcry.com/hot-wheels/10/0/113",
    "https://www.firstcry.com/hot-wheels/22/0/113",
    "https://www.firstcry.com/hot-wheels/14/0/113",
    # cars & jeeps brand facet
    "https://www.firstcry.com/toy-cars,-trains-and-vehicles/cars-and-jeeps/hot-wheels"
    "?cid=5&scid=94&type=t1-7973&brand=113",
    # sub-type facets
    _FC_FACET + "&sub-type=t6-7966",            # die-cast models
    _FC_FACET + "&sub-type=t6-7972",            # free wheel toys
    # age facets (each a different slice)
    _FC_FACET + "&age=4",
    _FC_FACET + "&age=6",
    _FC_FACET + "&age=8",
    _FC_FACET + "&age=10",
    _FC_FACET + "&age=12",
    # skills / theme facets
    _FC_FACET + "&skills=4",
    _FC_FACET + "&skills=7",
    _FC_FACET + "&sub-type=t6-7966&age=10",
    _FC_FACET + "&sub-type=t6-7966&age=6",
    _FC_FACET + "&sub-type=t6-7972&skills=7",
]
FC_LISTING_URLS = ([u.strip() for u in os.getenv("FC_LISTING_URLS", "").split("|") if u.strip()]
                   or _FC_DEFAULT_URLS)

# Products whose NAME contains any of these keywords are ignored everywhere.
FC_EXCLUDE = [w.strip().lower() for w in
              os.getenv("FC_EXCLUDE", "monster truck,monster jam,monstred,hopper ball")
              .split(",") if w.strip()]

# Card anchor of truth: the card image's filename holds the product id and its
# title= holds the clean name, so the two can never be mismatched. Size-variant
# links have no image, which is what keeps them out of the parse entirely.
_FC_IMG = re.compile(
    r'<img[^>]+products/\d+x\d+/(\d{5,})[a-z]?\.jpg[^>]*?title="([^"]{6,250})"', re.I)
_FC_IMG_ALT = re.compile(
    r'<img[^>]+title="([^"]{6,250})"[^>]+products/\d+x\d+/(\d{5,})[a-z]?\.jpg', re.I)
_FC_FOOTER_LINK = re.compile(
    r'href="https://www\.firstcry\.com/hot-wheels/[^"]*?/(\d{5,})/product-detail[^"]*"'
    r'[^>]*title="([^"]{6,250})"', re.I)


# Shared HTML helpers (used by FirstCry, Hamleys and Karz&Dolls parsers).
_TAG = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return html.unescape(_TAG.sub(" ", s)).replace("\xa0", " ").strip()


def _fc_excluded(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in FC_EXCLUDE)


def _fc_name(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()[:180]


def _fc_card_stock_price(region: str) -> tuple:
    """Price/MRP/stock from one card's HTML region."""
    # Stock markers are read from the WHOLE card region, because the
    # Add-to-Cart button can sit AFTER the size-variant block. Price, however,
    # is read from the region with that block removed, so a variant's numbers
    # can never be mistaken for this product's price.
    price_region = region
    cut = re.search(r"Sizes?\s*:", region, re.I)
    if cut:
        price_region = region[:cut.start()]
    txt = _clean(price_region)
    txt = re.sub(r"\(\s*[\d,]+\s*Ratings?\s*\)", " ", txt, flags=re.I)
    txt = re.sub(r"Club\s*(Price|Cash)[^\d]{0,25}[\d,.]+", " ", txt, flags=re.I)
    txt = re.sub(r"Earn Club Cash[^.]{0,60}", " ", txt, flags=re.I)
    txt = re.sub(r"\d+%\s*Off", " ", txt, flags=re.I)
    txt = re.sub(r"\b\d{5,}\b", " ", txt)
    nums = [price_to_int(x) for x in re.findall(r"([\d,]+(?:\.\d+)?)", txt)]
    nums = [n for n in nums if n and 50 <= n <= 60000]
    price = min(nums) if nums else None
    mrp = max(nums) if nums else None
    up = region.upper()
    if "ADD TO CART" in up or "ADD TO BAG" in up:
        stock = "in_stock"
    elif "NOTIFY ME" in up or "OUT OF STOCK" in up or "SOLD OUT" in up:
        stock = "out_of_stock"
    else:
        stock = None                      # unknown — caller keeps prior state
    return price, (mrp if mrp and mrp != price else None), stock


def scrape_firstcry() -> list[dict]:
    prev_all = load_seen()
    prev_fc = {pid[3:]: v for pid, v in prev_all.items()
               if pid.startswith("fc_") and isinstance(v, dict)}

    seen_now: dict = {}          # id -> {name, price, mrp, stock}

    def fetch(url):
        for _ in range(2):
            try:
                r = http.get(url, headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE)
                if r.status_code == 200 and len(r.text) > 5000:
                    return r.text
            except Exception:
                pass
            time.sleep(1.5)
        return None

    with ThreadPoolExecutor(max_workers=FC_WORKERS) as ex:
        pages = {ex.submit(fetch, u): u for u in FC_LISTING_URLS}
        for fut in as_completed(pages):
            url = pages[fut]
            try:
                page = fut.result()
            except Exception:
                page = None
            if not page:
                print(f"  [FC] {url[-45:]} → unavailable")
                continue

            # locate every card image (id + name), then take the HTML between
            # this image and the next as that card's own region
            marks = []
            for m in _FC_IMG.finditer(page):
                marks.append((m.start(), m.group(1), _fc_name(m.group(2))))
            for m in _FC_IMG_ALT.finditer(page):
                marks.append((m.start(), m.group(2), _fc_name(m.group(1))))
            marks.sort()

            added = 0
            for i, (pos, pid, nm) in enumerate(marks):
                if not nm or _fc_excluded(nm):
                    continue
                end = marks[i + 1][0] if i + 1 < len(marks) else min(len(page), pos + 6000)
                price, mrp, stock = _fc_card_stock_price(page[pos:end])
                cur = seen_now.get(pid)
                if cur is None or (cur.get("stock") is None and stock):
                    seen_now[pid] = {"name": nm, "price": price, "mrp": mrp, "stock": stock}
                    if cur is None:
                        added += 1

            # footer New Arrival / Most Popular: names + ids only (no stock)
            for m in _FC_FOOTER_LINK.finditer(page):
                pid, nm = m.group(1), _fc_name(m.group(2))
                if nm and not _fc_excluded(nm) and pid not in seen_now:
                    seen_now[pid] = {"name": nm, "price": None, "mrp": None, "stock": None}
                    added += 1
            print(f"  [FC] +{added:3d} new  ({len(seen_now)} total)  {url[-52:]}")

    if not seen_now:
        print("[*] FirstCry: nothing parsed (blocked?)")
        return []

    # carry forward previously known products not visible on today's slices
    out = []
    for pid, v in prev_fc.items():
        if pid.isdigit() and pid not in seen_now:
            nm = v.get("name", "")
            if nm and not _fc_excluded(nm) and "'+'" not in nm:
                seen_now[pid] = {"name": nm, "price": price_to_int(v.get("price")),
                                 "mrp": None, "stock": None}

    skipped_unknown = 0
    for pid, v in seen_now.items():
        prevrow = prev_fc.get(pid, {})
        stock = v["stock"] or prevrow.get("stock")
        if stock is None:
            # Never seen as a real card and no prior state (e.g. a footer-only
            # "New Arrival" link). Guessing would either invent a fake in-stock
            # alert or spam a "sold out" one, so we skip it — it gets picked up
            # properly the moment it appears on any listing card.
            skipped_unknown += 1
            continue
        price = v["price"] if v["price"] else price_to_int(prevrow.get("price"))
        out.append({
            "id": f"fc_{pid}", "source": "firstcry", "name": v["name"],
            "url": f"https://www.firstcry.com/x/x/{pid}/product-detail",
            "price": f"₹{price}" if price else "",
            "mrp": f"₹{v['mrp']}" if v["mrp"] else "",
            "stock": stock,
            "badge_new": False,
            "stock_ver": "fc_listing_v2",
        })
    ins = sum(1 for d in out if d["stock"] == "in_stock")
    print(f"[*] FirstCry total: {len(out)} ({ins} in stock, "
          f"{len(seen_now)} seen this run, {skipped_unknown} unknown-skipped)")
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
    "badge,is_active,updated_at,"
    "product_skus!product_skus_product_id_fkey(available)"
)


def scrape_minifygram() -> list[dict]:
    key = MINIFYGRAM_ANON_KEY
    headers = _mg_headers(key)

    url = (f"{MINIFYGRAM_SUPABASE}/rest/v1/products"
           f"?select={quote(_MG_SELECT, safe=',!()')}&is_active=eq.true&limit=1000")
    try:
        r = http.get(url, headers=headers, timeout=TIMEOUT, **_IMPERSONATE)
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
                  "with a fresh key (see README) — the hardcoded default is stale.")
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
    print(f"  [MG] products (embedded stock) → {len(rows)} rows")

    out = []
    no_sku_count = 0
    for row in rows:
        rid   = row.get("id")
        name  = row.get("name")
        slug  = row.get("slug") or rid
        brand = str(row.get("brand") or "").lower()
        if not (rid and name):
            continue

        # ── Brand allowlist (configurable) ────────────────────────────────────
        # Minifygram sells many diecast brands (TimeMicro, Poprace, Inno64,
        # Funko…) under the same "Diecast" category, so category alone is not a
        # safe filter — we match by brand/name tokens. Default tracks Hot
        # Wheels + MiniGT (incl. Kaido House, a MiniGT line). Override with the
        # MG_BRANDS env (comma-separated tokens, spaces/hyphens ignored).
        allowed = [t.strip().lower().replace(" ", "").replace("-", "")
                   for t in os.getenv(
                       "MG_BRANDS",
                       "hotwheels,mattel,minigt,mini gt,kaido house").split(",")
                   if t.strip()]
        brand_norm = brand.replace(" ", "").replace("-", "")
        name_norm  = str(name).lower().replace(" ", "").replace("-", "")
        if not any(tok in brand_norm or tok in name_norm for tok in allowed):
            continue

        # ── Authoritative stock: product_skus[].available, summed ──────────────
        skus = row.get("product_skus") or []
        if skus:
            total_available = sum(
                (s.get("available") or 0) for s in skus if isinstance(s, dict))
            in_stock = total_available > 0
        else:
            # No SKU row at all for this product. Fall back to product_type,
            # which reads "in-stock" on the confirmed live example; anything
            # else (e.g. "sold-out", "preorder") counts as not-immediately-buyable.
            no_sku_count += 1
            ptype = str(row.get("product_type") or "").lower()
            in_stock = ptype == "in-stock"

        price = price_to_int(row.get("price_inr"))
        mrp   = price_to_int(row.get("mrp_inr"))

        out.append({
            "id": f"mg_{rid}", "source": "minifygram", "name": str(name)[:180],
            "url": f"https://minifygram.com/product/{slug}",
            "price": f"₹{price}" if price else "",
            "mrp":   f"₹{mrp}"   if mrp and mrp != price else "",
            "stock": "in_stock" if in_stock else "out_of_stock",
            "badge_new": bool(row.get("badge")),
            "mg_updated_at": str(row.get("updated_at") or ""),
            # v4.4: authoritative product_skus.available query. Any prior stamp
            # (page-scraping guesses, sold_out-column guesses) gets silently
            # corrected once, per the stock_ver mechanism in compute_changes().
            "stock_ver": "mg_skus_v1",
        })

    if no_sku_count:
        print(f"  [MG] {no_sku_count} products had no SKU row — used product_type fallback")

    ins = sum(1 for d in out if d["stock"] == "in_stock")
    print(f"[*] Minifygram total: {len(out)} ({ins} in stock)")
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


def _hamleys_api(sess) -> list[dict] | None:
    """Fynd application catalog API — the real source behind hamleys.in.

    v7: hamleys.in/brand/hot-wheels renders NO products server-side (the grid is
    JS-loaded), which is why this source went silent. The page's JS calls Fynd's
    public storefront API, so we call the same endpoint directly. Fynd uses
    CURSOR pagination (page_id=* then page.next_id) — the old ?brand=&page_no=
    guess was the wrong parameter shape and always returned nothing.
    """
    headers = {**COMMON_HEADERS, "Accept": "application/json, text/plain, */*",
               "x-currency-code": "INR", "Referer": "https://hamleys.in/brand/hot-wheels"}

    def _g(u):
        return (sess.get(u, headers=headers, timeout=TIMEOUT) if sess
                else http.get(u, headers=headers, timeout=TIMEOUT, **_IMPERSONATE))

    base = "https://hamleys.in/api/service/application/catalog/v1.0/products/"
    # Query shapes to try, most precise first.
    shapes = [
        base + "?f=brand%3Ahot-wheels&filters=false&page_size=100&page_id={pid}",
        base + "?q=hot%20wheels&filters=false&page_size=100&page_id={pid}",
        base + "?f=brand%3Ahotwheels&filters=false&page_size=100&page_id={pid}",
    ]

    for shape in shapes:
        out, pid, pages = [], "*", 0
        ok = False
        while pages < 8:
            try:
                r = _g(shape.format(pid=quote(pid, safe="*")))
            except Exception as e:
                print(f"  [HM] api {type(e).__name__}")
                break
            if r.status_code != 200:
                print(f"  [HM] api → HTTP {r.status_code}")
                break
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
                    "badge_new": False, "stock_ver": "hm_api_v2",
                })
            page = data.get("page") or {}
            nxt = page.get("next_id")
            if not (page.get("has_next") and nxt):
                break
            pid = nxt
            pages += 1
            time.sleep(0.4)
        if ok and out:
            ins = sum(1 for d in out if d["stock"] == "in_stock")
            print(f"  [HM] Fynd API → {len(out)} Hot Wheels ({ins} in stock, "
                  f"{pages+1} page(s))")
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
                s = futs[fut]
                try:
                    info = fut.result()
                except Exception:
                    info = None
                if info:
                    checked[s] = info
                else:
                    fails += 1
    if fails and not checked:
        print(f"  [HM] all {fails} page checks failed — site markup may have changed")
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
# v6: KND relaunched on a new Next.js site (the old karzanddolls.in is now
# archive-only), which is why this source went silent. Two changes:
#   • product links are now /details/{slug}?pid={ID} — the pid is the stable id
#   • ALL Hot Wheels and MiniGT categories are tracked, not just blister packs
# Category pages are fully server-rendered (name, SKU line, price, sale price,
# and Add-to-Cart), so one fetch per category = that whole category with stock.
_KD = "https://www.karzanddolls.com"
_KD_DEFAULT_URLS = [
    # Hot Wheels
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
    # MiniGT family
    f"{_KD}/mini-gt/mini-gt",
    f"{_KD}/mini-gt/mini-gt-blister-pack",
    f"{_KD}/mini-gt/kaido-house",
    # Pre-orders (new MiniGT drops appear here first)
    f"{_KD}/pre-orders/pre-order-minigt",
    f"{_KD}/pre-orders/pre-order-special-stock",
]
KD_URLS = ([u.strip() for u in os.getenv("KD_URLS", "").split("|") if u.strip()]
           or _KD_DEFAULT_URLS)

# Track pre-orders? They're "in stock" in the sense that you can reserve them.
KD_INCLUDE_PREORDER = os.getenv("KD_INCLUDE_PREORDER", "true").lower() == "true"

# Brands KND also sells that we never want in Hot Wheels / MiniGT alerts.
_KD_DENY = tuple(t.strip().upper().replace(" ", "") for t in os.getenv(
    "KD_DENY",
    "LEGO,BARBIE,FUNKO,MATCHBOX,SOLIDO,SCHUCO,GREENLIGHT,POPRACE,TARMAC,INNO64,"
    "PARA64,PARAGON,TOMICA,MAJORETTE,BBURAGO,MAISTO,ERACARS,JADA,BBR,SPARK,"
    "AMERICANDIORAMA,ALMOSTREAL,LCDMODELS,TRENDSHOBBY,GHOSTPLAYER,KILOWORKS,"
    "ZDTOYS,MARVEL,TRANSFORMERS,WWE,JURASSIC,MASTERVERSE,IMAGINEXT,BOOK,VMB,"
    "RMZ,MSZ,GOC,QUBECARZ,TSM,TOPSPEED").split(",") if t.strip())

_KD_LINK = re.compile(r'href="(/details/[^"]+?)"', re.I)
_KD_PID = re.compile(r'[?&]pid=([A-Za-z0-9]+)')


def scrape_karzanddolls() -> list[dict]:
    out, seen_ids = [], set()

    def fetch(u):
        try:
            r = http.get(u, headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE)
            if r.status_code == 200 and len(r.text) > 4000:
                return r.text
            print(f"  [KD] {u.rsplit('/',1)[-1]} → HTTP {r.status_code}")
        except Exception as e:
            print(f"  [KD] {u.rsplit('/',1)[-1]} → {type(e).__name__}")
        return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        pages = {ex.submit(fetch, u): u for u in KD_URLS}
        for fut in as_completed(pages):
            cat = pages[fut].rsplit("/", 1)[-1]
            try:
                page = fut.result()
            except Exception:
                page = None
            if not page:
                continue

            # split into card regions on /details/ links
            parts = re.split(r'(?=<a[^>]+href="/details/)', page)
            found = 0
            for part in parts:
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
                # name: the card heading is the longest caps-ish run before ₹
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

                # brand gate: Hot Wheels or MiniGT family only
                sku = ""
                sm = re.search(r'((?:MINI\s*GT|HOT\s*WHEELS|HOTWHEELS|KAIDO)[A-Z0-9 \-]{0,30})',
                               txt, re.I)
                if sm:
                    sku = sm.group(1).strip()
                blob = (name + " " + sku).upper().replace(" ", "")
                # KND category pages also render "Trending"/"Similar" cards from
                # other brands, so a category match alone is not enough — an
                # explicit deny-list keeps LEGO/Barbie/other diecast makers out.
                # Match the deny-list against the start of the whole card text
                # (badge + SKU line + name), because the brand often appears
                # ONLY in the SKU line, e.g. "1:43 SOLIDO 421438273".
                deny_scope = txt[:250].upper().replace(" ", "").replace("-", "")
                if any(k in deny_scope for k in _KD_DENY):
                    continue
                if not any(k in blob for k in ("MINIGT", "HOTWHEELS", "KAIDO")):
                    # no brand token on the card — fall back to the category,
                    # which is brand-specific on this site
                    if not any(k in cat for k in ("hot-wheels", "mini-gt", "kaido", "minigt")):
                        continue

                pnums = [price_to_int(x) for x in re.findall(r"₹\s*([\d,]+)", txt)]
                pnums = [p for p in pnums if p and 50 <= p <= 200000]
                # a pre-order card shows the deposit (₹99) second — ignore it
                price = pnums[0] if pnums else None
                mrp = None
                if len(pnums) > 1 and pnums[1] > (price or 0):
                    mrp = pnums[1]

                if price is None:
                    continue
                if "ADD TO CART" in up:
                    stock = "in_stock"
                elif "OUT OF STOCK" in up or "SOLD OUT" in up or "NOTIFY" in up:
                    stock = "out_of_stock"
                else:
                    continue

                seen_ids.add(uid)
                tag = " [PRE-ORDER]" if is_pre else ""
                link = _KD + quote(path, safe="/:?=&")
                out.append({
                    "id": uid, "source": "karzdolls",
                    "name": (name + tag)[:180], "url": link,
                    "price": f"₹{price}", "mrp": f"₹{mrp}" if mrp else "",
                    "stock": stock,
                    "badge_new": "NEW ARRIVAL" in up,
                })
                found += 1
            if found:
                print(f"  [KD] {cat} → {found}")

    ins = sum(1 for d in out if d["stock"] == "in_stock")
    print(f"[*] Karz&Dolls total: {len(out)} ({ins} in stock)")
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# SOURCE — BigBasket  (search API, best effort — geo-limited)
# ══════════════════════════════════════════════════════════════════════════════════
# Like Blinkit, BigBasket screens datacenter IPs, so from GitHub's US runners this
# usually returns 403 and simply contributes nothing (it never blocks other
# sources). It works from an Indian IP — i.e. the phone watcher.
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
                    print(f"  [BB] {api.split('.com')[1][:34]} → HTTP {r.status_code}")
                    continue
                data = r.json()
            except Exception as e:
                print(f"  [BB] {api.split('.com')[1][:34]} → {type(e).__name__}")
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
                            slug = n.get("slug") or ""
                            out.append({"id": uid, "source": "bigbasket",
                                        "name": str(nm)[:180],
                                        "url": f"https://www.bigbasket.com/pd/{pid}/{slug}/",
                                        "price": f"₹{price_to_int(sp or n.get('sp') or n.get('mrp'))}"
                                                 if (sp or n.get('sp') or n.get('mrp')) else "",
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
RESTOCK_COOLDOWN_H = 24     # don't re-alert the same product's restock within 24h


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

        if (stock == "in_stock" and prev_stock == "out_of_stock"
                and not is_correction
                and _hours_since(prev.get("last_restock_alert", "")) >= RESTOCK_COOLDOWN_H):
            restocks.append(d)
            prev["last_restock_alert"] = now

        if (stock == "in_stock" and cur_price and prev_price
                and cur_price < prev_price and not is_correction):
            price_drops.append({**d, "prev_price": prev.get("price")})

    return {"new_listings": new_listings, "restocks": restocks,
            "price_drops": price_drops, "back_soon": back_soon}


SRC = {"firstcry": "🛒FC", "minifygram": "💎MG", "hamleys": "🧸HM", "karzdolls": "🏁KD",
       "bigbasket": "🧺BB", "blinkit": "⚡BL"}


def _within_budget(d) -> bool:
    if MAX_ALERT_PRICE <= 0:
        return True
    p = price_to_int(d.get("price"))
    return (p is None) or (p <= MAX_ALERT_PRICE)


def _line(d, extra="") -> str:
    tag = SRC.get(d["source"], "")
    flag = " 🎯" if any(w in d["name"].lower() for w in WATCHLIST) else ""
    price = d.get("price", "")
    mrp = f" <s>{d['mrp']}</s>" if d.get("mrp") else ""
    return f"[{tag}] <b>{html.escape(d['name'])}</b>{flag}  {price}{mrp}{extra}\n{d['url']}"


def build_alert(ch: dict) -> str | None:
    parts = []

    # ── In-stock alerts (loud) ─────────────────────────────────────────────────
    news = [d for d in ch["new_listings"] if _within_budget(d)]
    if news:
        parts.append("🆕 <b>NEW — in stock</b>")
        parts += ["  " + _line(d) for d in news[:25]]

    if ch["restocks"]:
        parts.append("\n🔥 <b>BACK IN STOCK — grab it now</b>")
        parts += ["  " + _line(d) for d in ch["restocks"][:25]]

    if ch["price_drops"]:
        parts.append("\n💸 <b>PRICE DROP</b>")
        parts += ["  " + _line(d, extra=f"  (was {d['prev_price']})") for d in ch["price_drops"][:25]]

    # ── Newly listed but sold out (quiet — always show, capped at 8) ──────────
    # These are worth knowing about: hit the 💙 wishlist button on the site so
    # Minifygram notifies you when they restock. Next run the bot will catch the
    # restock itself too.
    bs = [d for d in ch["back_soon"] if _within_budget(d)]
    if bs:
        parts.append("\n👀 <b>NEW listing — sold out (wishlist it!)</b>")
        parts += ["  " + _line(d) + "  <i>sold out</i>" for d in bs[:8]]

    if not parts:
        return None
    header = "🏎️ <b>Hot Wheels Tracker</b> — Dehradun\n"
    return header + "\n".join(parts)


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
def main():
    seen = load_seen()
    first_run = (len(seen) == 0)

    all_products, errors, live_sources = [], [], []
    sources = (("FirstCry", scrape_firstcry),
               ("Minifygram", scrape_minifygram),
               ("Hamleys", scrape_hamleys),
               ("Karz&Dolls", scrape_karzanddolls),
               ("BigBasket", scrape_bigbasket),
               ("Blinkit", scrape_blinkit))
    # Sources run concurrently — total time is the SLOWEST source, not the sum.
    # Each stays fully isolated: one failing never affects the others.
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=SRC_WORKERS) as ex:
        futs = {ex.submit(fn): name for name, fn in sources}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                prods = fut.result()
                if prods:
                    live_sources.append(name)
                all_products.extend(prods)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                print(f"[!] {name} error:\n{traceback.format_exc()}")
    print(f"\n[*] all sources finished in {time.time()-t0:.1f}s "
          f"→ {len(all_products)} products")

    # Global keyword exclusion — applies to EVERY source, not just FirstCry, so
    # e.g. Monster Trucks can't reappear via Hamleys or Karz&Dolls.
    if FC_EXCLUDE:
        before = len(all_products)
        all_products = [p for p in all_products if not _fc_excluded(p["name"])]
        if before != len(all_products):
            print(f"[*] excluded {before-len(all_products)} products "
                  f"matching {FC_EXCLUDE}")

    if not all_products:
        # Only shout if EVERYTHING died — and keep it actionable, not spammy.
        tg("⚠️ <b>Hot Wheels Tracker</b>\nAll sources returned 0 this run "
           "(likely a temporary block). Will retry next run.\n"
           + (f"<code>{'; '.join(errors)[:300]}</code>" if errors else ""))
        print("[!] No products from any source.")
        return

    current = {p["id"]: p for p in all_products}

    # ── Per-source silent baseline ─────────────────────────────────────────────
    # When a brand-new SOURCE appears (e.g. Hamleys added in an upgrade) while
    # other sources already have history, its entire catalog would otherwise
    # fire as ~dozens of "NEW" alerts at once. Instead: the first time a source
    # shows up, absorb its items silently (mark alerted_new), announce a one-line
    # baseline, and alert only on changes from the next run onward.
    if seen:
        known_sources = {v.get("source") for v in seen.values() if isinstance(v, dict)}
        new_sources = {d["source"] for d in current.values()} - known_sources
        for s in new_sources:
            items = [pid for pid, d in current.items() if d["source"] == s]
            ins = sum(1 for pid in items if current[pid]["stock"] == "in_stock")
            for pid in items:
                seen.setdefault(pid, {})["alerted_new"] = True
            label = SRC.get(s, s)
            print(f"[=] New source '{s}': baseline {len(items)} items absorbed silently.")
            tg(f"🆕 <b>New source added:</b> {label} — tracking {len(items)} products "
               f"({ins} in stock). Alerts start from the next change.")

    # One-time migration: entries written by the old overwrite-style seen.json
    # lack the alerted_new flag. Treat every pre-existing entry as already
    # alerted, so upgrading the bot doesn't replay old alerts.
    if seen and not any("alerted_new" in v for v in seen.values() if isinstance(v, dict)):
        for v in seen.values():
            if isinstance(v, dict):
                v["alerted_new"] = True
        print(f"[~] Migrated {len(seen)} legacy seen entries (marked already-alerted).")

    changes = compute_changes(current, seen)

    # ── Discovery-burst guard ──────────────────────────────────────────────────
    # A genuine drop is 1-5 new products. If one source suddenly surfaces MANY
    # never-seen items in a single run, that's coverage expanding (a new sitemap,
    # a new listing slice, an upgrade) — not 30 simultaneous releases. Absorb
    # those silently with a one-line summary instead of an alert blast.
    # compute_changes has already marked them alerted_new, so this stays one-time.
    BURST_LIMIT = int(os.getenv("DISCOVERY_BURST_LIMIT", "8"))
    for src_key in {d["source"] for d in current.values()}:
        burst = [d for d in (changes["new_listings"] + changes["back_soon"])
                 if d["source"] == src_key]
        if len(burst) > BURST_LIMIT:
            changes["new_listings"] = [d for d in changes["new_listings"]
                                       if d["source"] != src_key]
            changes["back_soon"] = [d for d in changes["back_soon"]
                                    if d["source"] != src_key]
            ins = sum(1 for d in burst if d["stock"] == "in_stock")
            label = SRC.get(src_key, src_key)
            print(f"[=] Discovery burst from {src_key}: {len(burst)} items absorbed.")
            tg(f"📈 <b>Coverage expanded:</b> {label} +{len(burst)} newly tracked "
               f"products ({ins} in stock). Alerts on changes from here.")

    if first_run and FIRST_RUN_SILENT:
        # First run just learns the baseline — don't fire 200 "new" alerts.
        # Every baseline product is marked alerted_new so it can never fire NEW later.
        for pid in current:
            seen.setdefault(pid, {})["alerted_new"] = True
        by_src = {}
        for d in current.values():
            by_src.setdefault(d["source"], [0, 0])
            by_src[d["source"]][0] += 1
            if d["stock"] == "in_stock":
                by_src[d["source"]][1] += 1
        breakdown = "\n".join(
            f"  {'🛒FC' if s=='firstcry' else '💎MG' if s=='minifygram' else '⚡BL'} "
            f"{by_src[s][1]} in stock / {by_src[s][0]} total"
            for s in ("firstcry", "minifygram", "blinkit") if s in by_src
        )
        print(f"[=] First run: baseline saved ({len(current)} products). No alerts.")
        tg(f"✅ <b>Hot Wheels Tracker re-armed</b>\nBaseline: {len(current)} products\n"
           f"{breakdown}\n\nYou'll get pinged on new listings, restocks &amp; price drops.")
        merge_and_save_seen(seen, current)
        return

    alert = build_alert(changes)
    if alert:
        tg(alert)
        print("\n" + alert)
    elif not SILENT:
        tg(heartbeat(current, changes))
    else:
        n = sum(len(v) for v in changes.values())
        print(f"[=] No alert-worthy changes ({n} minor). Sources live: {', '.join(live_sources)}")

    if DEBUG:
        tg(heartbeat(current, changes))

    merge_and_save_seen(seen, current)


if __name__ == "__main__":
    main()
