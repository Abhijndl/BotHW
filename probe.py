#!/usr/bin/env python3
"""Probe #41: how CallMeBot's free APIs answer, so the tracker can tell the user
plainly whether their ringing alerts work. Nobody is called or messaged: a
Telegram call and a Telegram text to a username that doesn't exist, and a
WhatsApp message with a made-up number and API key. Each answer is timed and
its text saved."""
import html, json, re, time, urllib.parse, urllib.request

U = "@hwtracker_probe_no_such_user_7731"
call_q = urllib.parse.urlencode({"user": U, "text": "probe", "lang": "en-GB-Standard-B", "rpt": "1", "cc": "no"})
tests = [
    ("tg_call_unknown_user_http", "http://api.callmebot.com/start.php?" + call_q),
    ("tg_call_unknown_user_https", "https://api.callmebot.com/start.php?" + call_q),
    ("tg_call_bad_phone", "https://api.callmebot.com/start.php?" + urllib.parse.urlencode(
        {"user": "+910000000000", "text": "probe", "rpt": "1", "cc": "no"})),
    ("wa_bad_key", "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
        {"phone": "+910000000000", "text": "probe", "apikey": "000000"})),
    ("tg_text_unknown_user", "https://api.callmebot.com/text.php?" + urllib.parse.urlencode({"user": U, "text": "probe"})),
]
report = []
for name, url in tests:
    t0 = time.time()
    rec = {"test": name, "url": url.split("?")[0]}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hw-tracker-probe"})
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read().decode("utf-8", "replace")
            rec.update(status=r.status, ctype=r.headers.get("Content-Type"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        rec.update(status=e.code, ctype=e.headers.get("Content-Type"))
    except Exception as e:
        body = ""
        rec.update(status=None, error=f"{type(e).__name__}: {e}")
    rec["secs"] = round(time.time() - t0, 2)
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", body)))).strip()
    rec["text"] = text[:1500]
    rec["raw"] = body[:1200]
    report.append(rec)
    print(json.dumps(rec, ensure_ascii=False, indent=1))
    time.sleep(3)
json.dump(report, open("probe_report.json", "w"), indent=1, ensure_ascii=False)
