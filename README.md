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
   - `MINIFYGRAM_ANON_KEY` *(optional but recommended — see below)*

4. **Enable Actions** (Actions tab → enable workflows), then hit **Run workflow**
   once to arm it. The first run just learns the baseline and messages you
   "Tracker armed". After that you only get pinged on real changes.

## Turning on Minifygram (one-time, ~60 seconds)

Minifygram is a Lovable app backed by Supabase. Its product data is reachable
through a public Supabase REST endpoint, but you need the site's **anon key** —
a *public* key that's designed to live in browser code, so it's safe to use.

Grab it once:

1. Open <https://minifygram.com> in Chrome/Edge.
2. Press **F12** → click the **Network** tab.
3. Refresh the page, then click into any product.
4. In the request list, click any row going to `seoqlgtbygddyehugjwv.supabase.co`.
5. Scroll the **Headers** panel to **Request Headers** and copy the long
   **`apikey`** value (it starts with `eyJ…`).
6. Add it as repo secret **`MINIFYGRAM_ANON_KEY`**.

That's it — the bot auto-detects the product table and starts tracking new
listings, restocks (e.g. sold-out RLC / Super Treasure Hunts coming back), and
price changes. If you skip this, FirstCry (and Blinkit when reachable) still work;
Minifygram just stays off.

> Why not automatic? The bot *tries* to auto-discover the key from the site's
> JavaScript, but Minifygram sits behind Cloudflare, which often blocks
> GitHub's datacenter IPs from loading that JS. The Supabase endpoint itself is
> **not** behind Cloudflare, so once you supply the key, tracking is rock-solid.

## Tuning (all in `monitor.yml` env)

- `MAX_ALERT_PRICE` — only alert on NEW listings at/under this ₹ price (`0` = no cap).
  Set to e.g. `400` to focus on cheap singles and skip pricey track sets.
- `WATCHLIST` — comma-separated keywords that get a 🎯 flag.
- `SILENT` — `true` (default) = only ping on changes. `false` = heartbeat every run.
- `DEBUG` — `true` = also send a heartbeat each run while you're setting up.
- Cron cadence — default every 15 min. Change the `schedule` line for faster/slower.

## Notes & limits

- **Blinkit** has the most aggressive bot defense. If it returns nothing, the
  other two still work. It's a bonus source, not the backbone.
- **FirstCry** occasionally rate-limits datacenter IPs. GitHub's runner IPs are
  usually fine; if you see repeated FC blocks, widen the cron interval a little.
- State lives in `seen.json`, committed back after each run so it survives
  between runs. Don't hand-edit it.
- This reads only public catalog pages/APIs — the same data your browser loads.
  Keep the cadence reasonable (15 min is plenty) to stay a polite guest.
