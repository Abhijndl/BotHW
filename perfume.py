#!/usr/bin/env python3
"""Whiff Culture partials watcher, run beside bot.py in each GitHub run.

Reads the partial-sale collection every PERFUME_EVERY_S seconds and sends a
Telegram message the moment a partial is listed or comes back in stock. Runs
until .perfume_stop appears, then saves perfume.json and writes .perfume_done.
"""
import gzip
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

SITE = os.getenv("PERFUME_SITE", "https://www.whiffculture.com").rstrip("/")
COLL = os.getenv("PERFUME_COLLECTION", "partial-sale")
TG = os.getenv("TG_BASE", "https://api.telegram.org").rstrip("/")
EVERY = float(os.getenv("PERFUME_EVERY_S", "10"))
MAX_RUN = float(os.getenv("PERFUME_MAX_RUN_S", "420"))
GUARD = float(os.getenv("PERFUME_GUARD_S", "120"))
FAIL_WARN = float(os.getenv("PERFUME_FAIL_WARN_S", "900"))
NUDGE_EVERY = float(os.getenv("PERFUME_NUDGE_S", "43200"))
BACKOFF = float(os.getenv("PERFUME_BACKOFF_S", "60"))
STATE = os.getenv("PERFUME_STATE", "perfume.json")
STOP = os.getenv("PERFUME_STOP", ".perfume_stop")
DONE = os.getenv("PERFUME_DONE", ".perfume_done")
TOKEN = os.getenv("PERFUME_BOT_TOKEN", "").strip()
CHAT = os.getenv("PERFUME_CHAT_ID", "").strip()
HW_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
HW_CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
SOLD_CONFIRM = 2
BULK = 5
PAGE = 250
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
_dest = []


def log(msg):
    print(time.strftime("%H:%M:%S"), "[perfume]", msg, flush=True)


def hm(ts):
    return time.strftime("%H:%M", time.gmtime(ts + 19800))


def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                               "Accept-Encoding": "gzip", "Accept-Language": "en-IN,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, data, enc = r.status, r.read(), r.headers.get("Content-Encoding", "")
    except urllib.error.HTTPError as e:
        return e.code, ""
    if "gzip" in enc.lower():
        data = gzip.decompress(data)
    return code, data.decode("utf-8", "replace")


def fetch():
    out = []
    for page in range(1, 5):
        url = f"{SITE}/collections/{COLL}/products.json?limit={PAGE}&page={page}&_={int(time.time() * 1000)}"
        try:
            code, body = get(url)
        except Exception as e:
            return None, type(e).__name__
        if code != 200:
            return None, f"HTTP {code}"
        try:
            prods = json.loads(body)["products"]
            assert isinstance(prods, list)
        except Exception:
            return None, "not the usual product list"
        out += [p for p in prods if isinstance(p, dict) and p.get("id") and p.get("title")]
        if len(prods) < PAGE:
            return out, ""
    return out, ""


def available(p):
    return any(v.get("available") for v in p.get("variants") or [])


def price_of(p):
    vs = [v for v in p.get("variants") or [] if v.get("available")] or p.get("variants") or []
    try:
        return min(float(v["price"]) for v in vs)
    except (KeyError, TypeError, ValueError):
        return None


def rupees(v):
    if v is None:
        return ""
    return f"₹{v:,.0f}" if float(v).is_integer() else f"₹{v:,.2f}"


def accords(p):
    text = re.sub(r"<[^>]+>", " ", p.get("body_html") or "")
    m = re.search(r"\bAn?\s+([a-z][a-z ,&-]{2,60}?)\s+fragrance\b", text)
    return m.group(1).strip() if m else ""


def size_of(p):
    vs = [v for v in p.get("variants") or [] if v.get("available")] or p.get("variants") or []
    names = [str(v.get("title") or "").strip() for v in vs]
    names = [n for n in dict.fromkeys(names) if n and n.lower() != "default title"]
    return ", ".join(names[:3])


def link(p):
    return f"{SITE}/products/{p.get('handle')}"


def alert_text(kind, p):
    head = "🧴 NEW PARTIAL · Whiff Culture" if kind == "new" else "🧴 BACK IN STOCK · Whiff Culture"
    info = " · ".join(x for x in (size_of(p), rupees(price_of(p)), accords(p)) if x)
    return "\n".join(x for x in (head, p["title"].strip(), info, link(p)) if x)


def bulk_text(ev):
    rows = [f"• {p['title'].strip()} — {rupees(price_of(p))}" + (" (back)" if k == "back" else "") + f"\n  {link(p)}"
            for k, p in ev]
    return f"🧴 {len(ev)} partials just listed on Whiff Culture:\n" + "\n".join(rows)


def instock_lines(st, limit=25):
    rows = [(it.get("t", ""), it.get("p")) for it in st["items"].values() if it.get("a")]
    rows.sort()
    out = [f"• {t} — {rupees(p)}" for t, p in rows[:limit]]
    if len(rows) > limit:
        out.append(f"…and {len(rows) - limit} more")
    return out


def _key():
    return hashlib.sha256(("perfume-chat:" + TOKEN).encode()).digest()


def seal(chat):
    k, b = _key(), f"c:{chat}".encode()
    return bytes(x ^ k[i % len(k)] for i, x in enumerate(b)).hex()


def unseal(h):
    try:
        k, b = _key(), bytes.fromhex(h or "")
        s = bytes(x ^ k[i % len(k)] for i, x in enumerate(b)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    return s[2:] if s.startswith("c:") and re.fullmatch(r"-?\d+", s[2:]) else None


def tg(token, method, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{TG}/bot{token}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except ValueError:
            return {"ok": False, "error_code": e.code}
    except Exception as e:
        return {"ok": False, "error_code": 0, "description": type(e).__name__}


def linked_chat(st):
    res = tg(TOKEN, "getUpdates", {"timeout": 0, "allowed_updates": '["message"]'})
    if not res.get("ok"):
        return None, res.get("error_code")
    want = HW_CHAT if re.fullmatch(r"\d+", HW_CHAT) else None
    for u in res.get("result", []):
        m = u.get("message") or {}
        chat, who = m.get("chat") or {}, m.get("from") or {}
        if chat.get("type") == "private" and (want is None or str(who.get("id")) == want):
            st["chat"] = seal(chat["id"])
            return str(chat["id"]), None
    return None, None


def tag():
    return hashlib.sha256(TOKEN.encode()).hexdigest()[:12]


def resolve(st):
    if TOKEN:
        st["why"] = "start"
        cands = [c for c in (CHAT, unseal(st.get("chat")), HW_CHAT if re.fullmatch(r"\d+", HW_CHAT) else "") if c]
        for c in dict.fromkeys(cands):
            r = tg(TOKEN, "getChat", {"chat_id": c})
            if r.get("ok"):
                return TOKEN, c, True
            if r.get("error_code") == 401:
                st["why"] = "token"
                break
        else:
            c, err = linked_chat(st)
            if c:
                return TOKEN, c, True
        log("the perfume bot can't reach you yet; using the Hot Wheels bot")
    return HW_TOKEN, HW_CHAT, False


def raw_send(token, chat, text, preview):
    if not token or not chat:
        log("no Telegram bot to send with: " + text.replace("\n", " | ")[:200])
        return False
    r = tg(token, "sendMessage", {"chat_id": chat, "text": text[:4000],
                                  "disable_web_page_preview": "false" if preview else "true"})
    if not r.get("ok"):
        log(f"Telegram refused a message ({r.get('error_code')}: {r.get('description', '')[:80]})")
    return bool(r.get("ok"))


def ensure_dest(st):
    if not _dest:
        _dest.append(resolve(st))
        greet(st)
    return _dest[0]


def send(st, text, preview=False):
    token, chat, mine = ensure_dest(st)
    if raw_send(token, chat, text, preview):
        return True
    if mine:
        _dest[0] = (HW_TOKEN, HW_CHAT, False)
        return raw_send(HW_TOKEN, HW_CHAT, text, preview)
    return False


def greet(st):
    token, chat, mine = _dest[0]
    if not st["items"]:
        return
    hello = tag() if mine else "hw"
    if mine and st.get("hello") != hello:
        head = "✅ Connected. Whiff Culture partial alerts will come here."
    elif not mine and not st.get("hello"):
        head = "🧴 Perfume watcher is on for Whiff Culture partials."
        if not TOKEN:
            head += " Alerts come here until your perfume bot is set up."
    else:
        if not mine and TOKEN and time.time() - st.get("nudge", 0) >= NUDGE_EVERY:
            st["nudge"] = time.time()
            why = ("Telegram didn't accept the PERFUME_BOT_TOKEN secret; copy the token from @BotFather again"
                   if st.get("why") == "token" else "Open it in Telegram and tap Start")
            raw_send(token, chat, f"🧴 Your perfume bot can't message you yet. {why} "
                                  "(perfume alerts come here until then).", False)
        return
    st["hello"] = hello
    n_in = sum(1 for it in st["items"].values() if it.get("a"))
    body = [head, f"{len(st['items'])} partials listed, {n_in} in stock right now. "
                  "I'll message you the moment one is listed or comes back."]
    if n_in:
        body += ["In stock now:"] + instock_lines(st)
    raw_send(token, chat, "\n".join(body), False)


def failed(st, now, why):
    if not st.get("fail_since"):
        st["fail_since"] = now
    if not st.get("fail_warned") and now - st["fail_since"] >= FAIL_WARN:
        st["fail_warned"] = True
        send(st, f"⚠️ I can't read Whiff Culture's partials since {hm(st['fail_since'])} ({why}). I'll keep trying.")


def recovered(st):
    if st.get("fail_warned"):
        send(st, "✅ Whiff Culture's partials can be read again.")
    st["fail_since"], st["fail_warned"] = None, False


def check(st, now):
    prods, why = fetch()
    if prods is None:
        log(f"read failed: {why}")
        failed(st, now, why)
        return why
    recovered(st)
    items = st["items"]
    first = not items
    if not first and len(prods) < 0.5 * st.get("n", 0):
        log(f"only {len(prods)} partials in this read (was {st['n']}); ignored")
        return ""
    st["n"] = len(prods)
    ev = []
    for p in prods:
        pid, av, pr = str(p["id"]), available(p), price_of(p)
        it = items.get(pid)
        if it is None:
            items[pid] = {"t": p["title"].strip()[:90], "a": av, "in": first or av, "p": pr}
            if av and not first:
                items[pid]["al"] = now
                ev.append(("new", p))
            continue
        it["t"], it["p"] = p["title"].strip()[:90], pr
        if av:
            it.pop("so", None)
            if not it["a"]:
                kind = "back" if it.get("in") else "new"
                it["a"] = it["in"] = True
                if now - it.get("al", 0) >= GUARD:
                    it["al"] = now
                    ev.append((kind, p))
        elif it["a"]:
            it["so"] = it.get("so", 0) + 1
            if it["so"] >= SOLD_CONFIRM:
                it["a"] = False
                it.pop("so", None)
    if first:
        log(f"learnt {len(prods)} partials ({sum(1 for p in prods if available(p))} in stock)")
        return ""
    if len(ev) > BULK:
        send(st, bulk_text(ev))
    for kind, p in ev if len(ev) <= BULK else []:
        log(f"{kind}: {p['title']}")
        send(st, alert_text(kind, p), preview=True)
    return ""


def load():
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    st.setdefault("items", {})
    return st


def save(st):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, STATE)


def main():
    for f in (STOP, DONE):
        if os.path.exists(f):
            os.remove(f)
    st = load()
    t0 = time.time()
    run = {"no": os.getenv("GITHUB_RUN_NUMBER", ""), "checks": 0, "from": int(t0)}
    nxt = t0
    try:
        while not os.path.exists(STOP) and time.time() - t0 < MAX_RUN:
            if time.time() >= nxt:
                try:
                    why = check(st, time.time())
                    run["checks"] += 1
                except Exception as e:
                    why = ""
                    log(f"error: {e!r}")
                wait = max(EVERY, BACKOFF) if why in ("HTTP 429", "HTTP 403") else EVERY
                nxt = time.time() + wait
                run["to"] = int(time.time())
                st["run"] = run
                if st["items"] and not _dest and (not st.get("hello") or (TOKEN and st.get("hello") != tag())):
                    ensure_dest(st)
                save(st)
            time.sleep(0.2)
    finally:
        st["run"] = run
        save(st)
        log(f"stopped after {run['checks']} checks")
        open(DONE, "w").close()


if __name__ == "__main__":
    main()
