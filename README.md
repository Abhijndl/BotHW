# 🏎️ Hot Wheels / Diecast Collector Tracker (v4 — God Tier)

Free, always-on stock tracker for **FirstCry**, **Minifygram**, and **Blinkit**,
pinned to **Dehradun 248001**. Sends a Telegram ping the moment something you
care about changes:

| Signal | Emoji | Fires when |
|---|---|---|
| New listing | 🆕 | A SKU we've never seen appears, in stock |
| Restock | 🔥 | Something out of stock comes back |
| Price drop | 💸 | Price falls below the last-seen price |
| Newly listed but OOS | 👀 | Brand-new SKU that's sold out (wishlist it) |

Watchlist keywords (RLC, Treasure Hunt, Team Transport, etc.) get an extra 🎯 flag.

## Why this version actually works

The old bot launched headless Chromium via Playwright. On GitHub Actions that
browser kept failing to install (`chrome-headless-shell doesn't exist`) — which
is why you were getting "0 products found" every run.

**v4 never opens a browser.** It talks straight to the data each site's own
front-end uses, over plain HTTP with a real Chrome TLS fingerprint (`curl_cffi`):

- **FirstCry** — server-rendered HTML, parsed directly. Fast and reliable.
- **Minifygram** — Supabase REST API, auto-discovered from the site each run
  (so it keeps working if they redeploy).
- **Blinkit** — internal search API, location-pinned. Best-effort; the flakiest
  of the three but never blocks the others.

Each source is isolated: if one gets blocked, you still get alerts from the rest.
Runs in ~20–40 seconds instead of 2–3 minutes.

## Setup (5 minutes)

1. **Create a Telegram bot**
   - Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the **token**.
   - Message [@userinfobot](https://t.me/userinfobot) → copy your numeric **chat ID**.
   - Send your new bot any message once (so it's allowed to DM you).

2. **Fork / create this repo** and add these files:
   `bot.py`, `requirements.txt`, `seen.json`, `.github/workflows/monitor.yml`.

3. **Add repo secrets** (Settings → Secrets and variables → Actions → New secret):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `MINIFYGRAM_ANON_KEY` is **optional** — Minifygram tracking works out of the
     box (see below). Only add this secret if the bot logs an auth error saying
     the key has been rotated.

4. **Enable Actions** (Actions tab → enable workflows), then hit **Run workflow**
   once to arm it. The first run just learns the baseline and messages you
   "Tracker armed". After that you only get pinged on real changes.

## Minifygram — works out of the box, real-time stock

v4.4 captured Minifygram's own site traffic and found the exact query their
front-end uses to check stock: a `product_skus` table (field `available`) is
fetched *embedded inside* the products query, so one API call returns every
Hot Wheels product with its real, live stock — the same data their "Add to
cart" / "Sold out" button reads. No page-scraping, no guessing.

This needs Minifygram's public anon key — a client-side key that ships in
their own browser JavaScript to every visitor, so it's safe to embed — and a
working one is already built into `bot.py`. Nothing to set up.

**If Minifygram ever rotates the key**, the bot will log an auth error and
tracking will pause. To fix it:
1. Open <https://minifygram.com> in Chrome/Edge → **F12** → **Network** tab.
2. Refresh, click into any product.
3. Click any request to `seoqlgtbygddyehugjwv.supabase.co`.
4. Copy the long **`apikey`** request header value (starts with `eyJ…`).
5. Add/update it as repo secret **`MINIFYGRAM_ANON_KEY`** — this always takes
   priority over the built-in default.


## Tuning (all in `monitor.yml` env)

- `MAX_ALERT_PRICE` — only alert on NEW listings at/under this ₹ price (`0` = no cap).
  Set to e.g. `400` to focus on cheap singles and skip pricey track sets.
- `WATCHLIST` — comma-separated keywords that get a 🎯 flag.
- `SILENT` — `true` (default) = only ping on changes. `false` = heartbeat every run.
- `DEBUG` — `true` = also send a heartbeat each run while you're setting up.
- Cron cadence — default every 15 min. Change the `schedule` line for faster/slower.

## Notes & limits

- **Alert dedup (v4.1):** every product alerts as 🆕 NEW at most **once ever**;
  restocks have a 24h per-product cooldown. `seen.json` is now a permanent
  memory that grows over time — never overwritten — so FirstCry's rotating
  28-item view can't cause repeat alerts anymore. Don't hand-edit or reset it
  unless you want a fresh baseline.
- **Blinkit** is location-locked *and* geo-blocks foreign datacenter IPs.
  GitHub Actions runs from US IPs, so Blinkit usually returns nothing from
  there — the bot logs the exact HTTP status each run so you can see why.
  Two real fixes if you want Blinkit badly:
  1. **Self-hosted runner** (best): install a GitHub Actions runner on any
     always-on device on your home network (an old laptop / phone with Termux /
     Raspberry Pi). Runs from your Dehradun IP → Blinkit works natively.
  2. Accept it as best-effort: FirstCry + Minifygram already cover the main
     collector drops; Blinkit's toy stock in Dehradun is thin anyway.
- **FirstCry** occasionally rate-limits datacenter IPs. GitHub's runner IPs are
  usually fine; if you see repeated FC blocks, widen the cron interval a little.
- This reads only public catalog pages/APIs — the same data your browser loads.
  Keep the cadence reasonable (15 min is plenty) to stay a polite guest.
