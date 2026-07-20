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
        for k in ("mg_updated_at", "stock_ver"):
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
# SOURCE 1 — FirstCry  (server-rendered HTML)
# ══════════════════════════════════════════════════════════════════════════════════
# Each listing URL surfaces a different ~28-product slice in the raw HTML (the rest
# loads via "Show More" JS we don't trigger). Hitting several sorts and taking the
# union gives much wider catalog coverage for restock detection, while sort=new is
# what reliably catches brand-new arrivals.
FIRSTCRY_URLS = [
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=new",         # newest first → new-listing detection
    "https://www.firstcry.com/hot-wheels/0/0/113",                  # bestseller default
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=discount",    # discounted slice
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=pl",          # price low→high slice
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=ph",          # price high→low slice (opposite end)
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=rating",      # top-rated slice
    "https://www.firstcry.com/hot-wheels/0/0/113?sort=popularity",  # popularity slice
    "https://www.firstcry.com/hot-wheels/5/0/113",                  # toys & gaming sub-slice
    "https://www.firstcry.com/search?q=hot%20wheels&sort=new",      # search page — independent slice
    "https://www.firstcry.com/search?q=hot%20wheels%20die%20cast",  # search variant
]
# Coverage note: FirstCry server-renders only the first ~20-28 cards per view
# (the rest load via infinite-scroll JS we don't run). Each sort/search view
# surfaces a DIFFERENT slice, so the union above typically covers the catalog's
# most alert-relevant regions: sort=new catches every new listing, bestseller +
# popularity catch hot restocks, and the price-extremes/rating/search slices
# fill in the middle. Mid-catalog items outside all slices can still be missed —
# that's a hard limit of scraping without a browser, traded for reliability.

# A product "card" on the listing page always contains at least one
# /<id>/product-detail link, a name, a price, and either "ADD TO CART" or
# "Notify Me". We split the page on the product-detail anchors and parse each block.
_FC_CARD_SPLIT = re.compile(r'(?=<a\b[^>]*?/(\d{5,})/product-detail)', re.I)
_FC_ID         = re.compile(r'/(\d{5,})/product-detail', re.I)
_FC_HREF       = re.compile(
    r'''((?:https?://(?:www\.)?firstcry\.com)?/[^\s"'<>]*?/\d{5,}/product-detail[^\s"'<>]*)''', re.I)
_FC_TITLE      = re.compile(r'title="([^"]{6,200}?)"', re.I)
_FC_PRICE      = re.compile(r'₹?\s*([\d,]+(?:\.\d+)?)')
_TAG           = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return html.unescape(_TAG.sub(" ", s)).replace("\xa0", " ").strip()


def scrape_firstcry() -> list[dict]:
    out, seen_ids = [], set()

    for url in FIRSTCRY_URLS:
        page = None
        for attempt in range(2):                       # one retry on transient block
            try:
                r = http.get(url, headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE)
            except Exception as e:
                print(f"  [FC] request failed: {e}")
                time.sleep(2)
                continue
            if r.status_code == 200 and len(r.text) > 5000:
                page = r.text
                break
            print(f"  [FC] {url} → HTTP {r.status_code}, len {len(r.text)} "
                  f"(attempt {attempt + 1})")
            time.sleep(3)                              # back off, then retry once
        if not page:
            continue

        # The footer has "Popular Products" / "New Arrival" link lists that also
        # contain /product-detail hrefs but no price or cart button. We keep the
        # region before the footer's "Hot Wheels Online Shopping Store" heading so
        # those don't get counted as products.
        cut = re.search(r'Hot Wheels Online Shopping Store', page, re.I)
        grid = page[:cut.start()] if cut else page

        blocks = _FC_CARD_SPLIT.split(grid)
        cnt = 0
        for block in blocks:
            idm = _FC_ID.search(block or "")
            if not idm:
                continue
            pid_raw = idm.group(1)
            uid = f"fc_{pid_raw}"
            if uid in seen_ids:
                continue

            # href — find a path containing THIS product's id. If the page markup
            # hides the href (JS-attached, single quotes, data-attrs…), build the
            # canonical URL from the id: FirstCry resolves products by the numeric
            # id, so /x/x/{id}/product-detail always lands on the right page.
            href = None
            for hm in _FC_HREF.finditer(block):
                if f"/{pid_raw}/" in hm.group(1):
                    href = html.unescape(hm.group(1))
                    break
            if not href:
                href = f"/x/x/{pid_raw}/product-detail"
            # Normalise every URL shape we can meet: absolute, protocol-relative
            # (//www…), bare-domain (/www.firstcry.com/…), or site-relative path.
            href = re.sub(r"^/+(?=www\.firstcry\.com)", "", href)   # "/www.firstcry.com/x" → "www.firstcry.com/x"
            if href.startswith("www."):
                href = "https://" + href
            elif href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://www.firstcry.com" + href
            # collapse any accidental doubled domain
            href = re.sub(r"(https://www\.firstcry\.com)/+(?:www\.)?firstcry\.com", r"\1", href)

            # name — prefer the anchor title attribute; fall back to alt text / anchor text
            name = ""
            tm = _FC_TITLE.search(block)
            if tm:
                name = _clean(tm.group(1))
            if not name or len(name) < 5:
                # try image alt
                am = re.search(r'alt="([^"]{6,200}?)"', block, re.I)
                if am:
                    name = _clean(am.group(1))
            if not name or "hot wheel" not in name.lower():
                # last resort: first cleaned text chunk mentioning hot wheels
                txt = _clean(block)
                mt = re.search(r'(Hot\s*Wheels[^₹|]{4,120})', txt, re.I)
                if mt:
                    name = mt.group(1).strip(" -–|")
            if not name or len(name) < 5:
                continue
            name = re.sub(r"\s+", " ", name)[:180]

            # Search pages can surface other brands (Majorette, Centy, etc.) —
            # on those views, keep only actual Hot Wheels products. Category
            # 113 pages are Hot-Wheels-only so they skip this check.
            if "/search" in url and "hot wheel" not in name.lower():
                continue

            # only keep the region of the block that is the card (up to the next 'ADD TO CART'
            # /'Notify Me' + a bit), so prices from the following card don't leak in
            up = block.upper()

            # stock
            if "NOTIFY ME" in up and "ADD TO CART" not in up:
                stock = "out_of_stock"
            elif "ADD TO CART" in up or "ADD TO BAG" in up:
                stock = "in_stock"
            elif "OUT OF STOCK" in up or "SOLD OUT" in up:
                stock = "out_of_stock"
            else:
                stock = "in_stock"      # listed with a price and no notify-me → treat as available

            # price / mrp — extract from the ₹-price region only. We strip the
            # noisy bits first so rating counts ("914 Ratings"), "Club Price",
            # and "Club Cash" values can't be mistaken for the price (which would
            # cause phantom price-drop alerts).
            txt = _clean(block)
            txt_clean = re.sub(r'\(\s*[\d,]+\s*Ratings?\s*\)', ' ', txt, flags=re.I)
            txt_clean = re.sub(r'Club\s*Price\s*:?\s*[\d,.]+', ' ', txt_clean, flags=re.I)
            txt_clean = re.sub(r'Club\s*Cash[^\d]*[\d,]+', ' ', txt_clean, flags=re.I)
            txt_clean = re.sub(r'\d+%\s*Off', ' ', txt_clean, flags=re.I)
            txt_clean = re.sub(r'\d{5,}', ' ', txt_clean)          # strip product ids
            nums = [price_to_int(x) for x in _FC_PRICE.findall(txt_clean)]
            nums = [n for n in nums if n and 50 <= n <= 50000]     # sane price band
            price = min(nums) if nums else None
            mrp   = max(nums) if nums else None

            # A real product card always has a price and/or an explicit cart /
            # notify / stock marker. Footer "popular products" style link lists
            # have neither — skip them so they can't produce phantom NEW alerts
            # (matters especially on search pages, which lack the category
            # footer marker used for the grid cut above).
            has_marker = any(m in up for m in
                             ("ADD TO CART", "ADD TO BAG", "NOTIFY ME",
                              "OUT OF STOCK", "SOLD OUT"))
            if price is None and not has_marker:
                continue

            # "New" / "Bestseller" badge in the card
            is_new_badge = bool(re.search(r'>\s*New\s*<', block)) or "\nNew\n" in ("\n"+txt+"\n")

            seen_ids.add(uid)
            out.append({
                "id": uid, "source": "firstcry", "name": name, "url": href,
                "price": f"₹{price}" if price else "",
                "mrp":   f"₹{mrp}"   if mrp and mrp != price else "",
                "stock": stock,
                "badge_new": is_new_badge,
            })
            cnt += 1
        print(f"  [FC] {url.split('?')[-1] or 'default'} → {cnt} products "
              f"(running total {len(out)})")
        time.sleep(1.5)                                # be a polite guest between pages

    print(f"[*] FirstCry total: {len(out)}")
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

        # STRICT brand filter — only Hotwheels/Mattel (Minifygram sells MiniGT,
        # TimeMicro, Poprace, Inno64, Funko, etc. under the same "Diecast"
        # category, so category alone is NOT a safe filter).
        brand_norm = brand.replace(" ", "").replace("-", "")
        name_norm  = str(name).lower().replace(" ", "").replace("-", "")
        if not ("hotwheels" in brand_norm or "mattel" in brand_norm
                or "hotwheels" in name_norm):
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
# SOURCE 3 — Hamleys  (Fynd platform: JSON catalog API first, SSR HTML fallback)
# ══════════════════════════════════════════════════════════════════════════════════
# hamleys.in runs on the Fynd commerce platform. Two independent ways in:
#   1. Fynd's application catalog API (JSON, includes a `sellable` stock flag)
#   2. The brand listing page, which is server-rendered: every card is a plain
#      <a href="/product/{slug}">Name ₹ price</a> — same parse class as FirstCry.
HAMLEYS_PAGES = 5          # 46 products / ~12 per page → 4 pages + headroom


def _hamleys_api() -> list[dict] | None:
    """Try Fynd's standard application catalog endpoint. Returns None if the
    endpoint isn't open on this store (fall back to HTML)."""
    out = []
    for page in range(1, HAMLEYS_PAGES + 1):
        u = (f"https://hamleys.in/api/service/application/catalog/v1.0/products/"
             f"?brand=hot-wheels&page_no={page}&page_size=50")
        try:
            r = http.get(u, headers={**COMMON_HEADERS, "Accept": "application/json"},
                         timeout=TIMEOUT, **_IMPERSONATE)
            if r.status_code != 200:
                return None if page == 1 else out
            data = r.json()
        except Exception:
            return None if page == 1 else out
        items = data.get("items") or []
        if not items:
            break
        for it in items:
            slug = it.get("slug") or ""
            name = it.get("name") or ""
            if not (slug and name):
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
                "price": f"₹{price}" if price else "",
                "mrp": "",
                "stock": "in_stock" if (sellable is None or sellable) else "out_of_stock",
                "badge_new": False,
            })
        if not (data.get("page") or {}).get("has_next"):
            break
        time.sleep(0.8)
    return out


_HM_CARD = re.compile(r'href="(/product/[^"]+)"', re.I)


def scrape_hamleys() -> list[dict]:
    # Path 1: JSON API
    api = _hamleys_api()
    if api:
        # keep only actual Hot Wheels (API is brand-filtered already, belt & braces)
        api = [d for d in api if "hot wheel" in d["name"].lower()
               or "hotwheels" in d["name"].lower().replace(" ", "")]
        print(f"[*] Hamleys total (API): {len(api)}")
        if api:
            return api

    # Path 2: SSR HTML listing pages
    out, seen_ids = [], set()
    for page in range(1, HAMLEYS_PAGES + 1):
        u = f"https://hamleys.in/products?brand=hot-wheels&page_no={page}"
        try:
            r = http.get(u, headers=COMMON_HEADERS, timeout=TIMEOUT, **_IMPERSONATE)
        except Exception as e:
            print(f"  [HM] page {page} failed: {e}")
            break
        if r.status_code != 200 or len(r.text) < 3000:
            print(f"  [HM] page {page} → HTTP {r.status_code}")
            break
        page_html = r.text

        # Split into per-card regions on /product/ hrefs (like the FC parser)
        parts = re.split(r'(?=<a[^>]+href="/product/)', page_html)
        found = 0
        for part in parts:
            hm = _HM_CARD.search(part or "")
            if not hm:
                continue
            path = hm.group(1)
            slug = path.rsplit("/", 1)[-1]
            uid = f"hm_{slug}"
            if uid in seen_ids:
                continue

            txt = _clean(part[:2500])
            nm = re.search(r'(Hot\s*Wheels[^₹]{3,150})', txt, re.I)
            if not nm:
                continue                    # non-HW or nav link
            name = re.sub(r"\s+", " ", nm.group(1)).strip(" -–|")[:180]

            pnums = [price_to_int(x) for x in re.findall(r'₹\s*([\d,]+)', txt)]
            pnums = [p for p in pnums if p and 50 <= p <= 100000]
            price = min(pnums) if pnums else None

            up = part.upper()
            if "OUT OF STOCK" in up or "SOLD OUT" in up or "NOTIFY" in up:
                stock = "out_of_stock"
            else:
                stock = "in_stock"          # listing shows Add-to-bag cards

            if price is None and stock == "in_stock":
                continue                    # nav/footer link, not a card

            seen_ids.add(uid)
            out.append({
                "id": uid, "source": "hamleys", "name": name,
                "url": f"https://hamleys.in{path}",
                "price": f"₹{price}" if price else "",
                "mrp": "",
                "stock": stock,
                "badge_new": False,
            })
            found += 1
        print(f"  [HM] page {page} → {found} products")
        if found == 0:
            break
        time.sleep(1.0)

    print(f"[*] Hamleys total: {len(out)}")
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
    watch_ids = re.findall(r"/prid/(\d+)", os.getenv("BLINKIT_WATCH", ""))
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

    # Step 1b: check each watchlisted product directly (see BLINKIT_WATCH above)
    for prid in watch_ids:
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


SRC = {"firstcry": "🛒FC", "minifygram": "💎MG", "hamleys": "🧸HM", "blinkit": "⚡BL"}


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
                       ("hamleys", "🧸 Hamleys"), ("blinkit", "⚡ Blinkit")):
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
    for name, fn in (("FirstCry", scrape_firstcry),
                     ("Minifygram", scrape_minifygram),
                     ("Hamleys", scrape_hamleys),
                     ("Blinkit", scrape_blinkit)):
        print(f"\n[*] {name} …")
        try:
            prods = fn()
            if prods:
                live_sources.append(name)
            all_products.extend(prods)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print(f"[!] {name} error:\n{traceback.format_exc()}")

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
