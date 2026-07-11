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

4. **Enable Actions** (Actions tab → enable workflows), then hit **Run workflow**
   once to arm it. The first run just learns the baseline and messages you
   "Tracker armed". After that you only get pinged on real changes.

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
