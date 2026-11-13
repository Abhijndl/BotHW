#!/usr/bin/env python3
"""Perfume deal alerts from five Indian perfume stores.

Watches partials, sales, testers and decants (Shopify collections) and sends a
Telegram message the moment something is listed or comes back in stock, plus a
note when one of the stores starts a new sale.

It runs in its own GitHub workflow (.github/workflows/perfume.yml), apart from
the Hot Wheels tracker: each run watches for PERFUME_MAX_RUN_S seconds, makes
sure the next run is queued, and keeps its memory (perfume.json) on the
perfume-state branch, so it never writes to main.
"""
import gzip
import hashlib
import json
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

WHIFF = "https://www.whiffculture.com"
SCENTORIA = "https://www.scentoria.co.in"
SCENTIRA = "https://www.scentira.in"
SILLAGE = "https://www.sillageperfumes.in"
SNIFF = "https://sniff.co.in"


def W(wid, store, site, coll, label, new, every, variants=None, gone=False, notes=False):
    """One watched list. new: alert heading for a new item. variants: watch only the
    variants whose title matches (Scentira sells partials as a variant). gone: the
    list drops what sells out, so an in-stock item missing from it counts as sold out.
    notes: the store writes 'A floral, sweet ... fragrance' in its descriptions."""
    return {"id": wid, "store": store, "site": site, "coll": coll, "label": label, "new": new,
            "every": every, "variants": variants, "gone": gone, "notes": notes}


WATCHES = [
    W("whiff-partials", "Whiff Culture", WHIFF, "partial-sale", "partials", "NEW PARTIAL", 10, notes=True),
    W("scentoria-partials", "Scentoria", SCENTORIA, "partials", "partials", "NEW PARTIAL", 15, gone=True),
    W("scentira-partials", "Scentira", SCENTIRA, "partials", "partials", "NEW PARTIAL", 20, variants=r"\bpartial\b"),
    W("whiff-flash", "Whiff Culture", WHIFF, "flash-sale", "flash sale", "NEW IN FLASH SALE", 30, notes=True),
    W("whiff-testers", "Whiff Culture", WHIFF, "testers", "testers", "NEW TESTER", 30, notes=True),
    W("scentoria-deals", "Scentoria", SCENTORIA, "deals-of-the-week", "hot deals", "NEW HOT DEAL", 30),
    W("scentoria-festive", "Scentoria", SCENTORIA, "festive-sale", "festive sale", "NEW IN FESTIVE SALE", 30),
    W("scentira-clearance", "Scentira", SCENTIRA, "clearance", "clearance", "NEW IN CLEARANCE", 30),
    W("scentira-offers", "Scentira", SCENTIRA, "new-offers", "offers", "NEW OFFER", 30),
    W("sillage-steals", "Sillage", SILLAGE, "clearance-sale", "steals", "NEW STEAL", 30),
    W("sillage-sale", "Sillage", SILLAGE, "sale", "sale", "NEW IN SALE", 30),
    W("sniff-50ml", "Sniff", SNIFF, "50ml-sale", "50ml sale", "NEW IN 50ML SALE", 30, gone=True),
    W("sillage-decants", "Sillage", SILLAGE, "decants", "decants", "NEW DECANT", 60),
]
if os.getenv("PERFUME_WATCHES"):          # tests point the watcher at fake stores
    WATCHES = [W(**w) for w in json.loads(os.environ["PERFUME_WATCHES"])]

TG = os.getenv("TG_BASE", "https://api.telegram.org").rstrip("/")
GH_API = os.getenv("GH_API", "https://api.github.com").rstrip("/")
MAX_RUN = float(os.getenv("PERFUME_MAX_RUN_S", "1200"))
GUARD = float(os.getenv("PERFUME_GUARD_S", "120"))
XGUARD = float(os.getenv("PERFUME_XGUARD_S", "21600"))
FAIL_WARN = float(os.getenv("PERFUME_FAIL_WARN_S", "900"))
NUDGE_EVERY = float(os.getenv("PERFUME_NUDGE_S", "43200"))
BACKOFF = float(os.getenv("PERFUME_BACKOFF_S", "60"))
SALES_EVERY = float(os.getenv("PERFUME_SALES_EVERY_S", "900"))
SALES_FIRST = float(os.getenv("PERFUME_SALES_FIRST_S", "45"))
PUSH_EVERY = float(os.getenv("PERFUME_PUSH_EVERY_S", "300"))
PULL_RETRY = float(os.getenv("PERFUME_PULL_RETRY_S", "60"))
PULL_TRIES = int(os.getenv("PERFUME_PULL_TRIES", "4"))
SEND_GAP = float(os.getenv("PERFUME_SEND_GAP_S", "1.1"))
STATE = os.getenv("PERFUME_STATE", "perfume.json")
BRANCH = os.getenv("PERFUME_STATE_BRANCH", "").strip()
STOP = os.getenv("PERFUME_STOP", ".perfume_stop")
DONE = os.getenv("PERFUME_DONE", ".perfume_done")
TOKEN = os.getenv("PERFUME_BOT_TOKEN", "").strip()
CHAT = os.getenv("PERFUME_CHAT_ID", "").strip()
HW_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
HW_CHAT = os.getenv("TELEGRAM_CHAT_ID", "").strip()
REPO = os.getenv("GITHUB_REPOSITORY", "")
RUN_ID = os.getenv("GITHUB_RUN_ID", "")
WF = os.getenv("GITHUB_WORKFLOW_REF", "").split("@")[0].rsplit("/", 1)[-1] or "perfume.yml"
CHAIN = os.getenv("PERFUME_CHAIN", "1" if os.getenv("GITHUB_ACTIONS") == "true" else "0") == "1"
SOLD_CONFIRM = 2
BULK = 5
BULK_ROWS = 25
PAGE = 250
MAX_PAGES = 8
KEEP_DAYS = 30
SALE_RE = re.compile(r"\b(sales?|clearance|deals?|flash|offers?|steals?)\b", re.I)
SALE_SKIP = re.compile(r"^cs-|exclud|eligible", re.I)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
_dest = []
_last_send = [0.0]
_pushed = [None]
_can_push = [True]


def log(msg):
    print(time.strftime("%H:%M:%S"), "[perfume]", msg, flush=True)


def hm(ts):
    return time.strftime("%H:%M", time.gmtime(ts + 19800))


def host(site):
    return urllib.parse.urlparse(site).netloc


# ── reading the stores ───────────────────────────────────────────────────────
def get(url, timeout=10):
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


def fetch(w):
    out = []
    for page in range(1, MAX_PAGES + 1):
        url = (f"{w['site']}/collections/{w['coll']}/products.json"
               f"?limit={PAGE}&page={page}&_={int(time.time() * 1000)}")
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
        out += [p for p in prods if isinstance(p, dict) and p.get("id") and isinstance(p.get("title"), str)]
        if len(prods) < PAGE:
            break
    return out, ""


def rows_of(w, prods):
    """{key: (product, variants)} — one row per product, or per matching variant."""
    out = {}
    for p in prods:
        vs = [v for v in p.get("variants") or [] if isinstance(v, dict)]
        if w.get("variants"):
            for v in vs:
                if v.get("id") and re.search(w["variants"], str(v.get("title") or ""), re.I):
                    out[f"{p['id']}:{v['id']}"] = (p, [v])
        else:
            out[str(p["id"])] = (p, vs)
    return out


def available(vs):
    return any(v.get("available") for v in vs)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def low_price(vs):
    prices = [num(v.get("price")) for v in ([v for v in vs if v.get("available")] or vs)]
    prices = [p for p in prices if p is not None]
    return min(prices) if prices else None


def rupees(v):
    if v is None:
        return ""
    return f"₹{v:,.0f}" if float(v).is_integer() else f"₹{v:,.2f}"


def vname(v):
    t = str(v.get("title") or "").strip()
    return "" if t.lower() == "default title" else t


def offer_text(vs):
    """'20 ML · ₹989', '₹2,950 (was ₹4,200, −30%)', or up to three sizes with prices."""
    pool = [v for v in vs if v.get("available")] or vs

    def price(v, single):
        pr, was = num(v.get("price")), num(v.get("compare_at_price"))
        if pr is None:
            return ""
        s = rupees(pr)
        if was and was > pr * 1.02:
            off = round(100 * (1 - pr / was))
            s += f" (was {rupees(float(round(was)))}, −{off}%)" if single else f" (−{off}%)"
        return s
    if len(pool) == 1:
        return " · ".join(x for x in (vname(pool[0]), price(pool[0], True)) if x)
    parts = [" ".join(x for x in (vname(v), price(v, False)) if x) for v in pool[:3]]
    if len(pool) > 3:
        parts.append(f"+{len(pool) - 3} more")
    return " · ".join(x for x in parts if x)


def accords(p):
    text = re.sub(r"<[^>]+>", " ", p.get("body_html") or "")
    m = re.search(r"\bAn?\s+([a-z][a-z ,&-]{2,60}?)\s+fragrance\b", text)
    return m.group(1).strip() if m else ""


def link(w, p, vs):
    url = f"{w['site']}/products/{p.get('handle')}"
    return f"{url}?variant={vs[0]['id']}" if w.get("variants") and vs else url


def name(w, p, vs):
    t = p["title"].strip()
    return f"{t} ({vname(vs[0])})" if w.get("variants") and vs and vname(vs[0]) else t


def alert_text(w, kind, p, vs):
    head = (f"🧴 {w['new']} · {w['store']}" if kind == "new"
            else f"🧴 BACK IN STOCK · {w['store']} {w['label']}")
    info = " · ".join(x for x in (offer_text(vs), accords(p) if w.get("notes") else "") if x)
    return "\n".join(x for x in (head, p["title"].strip(), info, link(w, p, vs)) if x)


def bulk_text(w, ev):
    fresh = all(k == "new" for k, _, _, _ in ev)
    head = (f"🧴 {len(ev)} new in {w['store']} {w['label']}:" if fresh
            else f"🧴 {len(ev)} listed or back in stock · {w['store']} {w['label']}:")
    rows = [f"• {name(w, p, vs)} — {rupees(low_price(vs))}" + ("" if fresh or k == "new" else " (back)")
            + f"\n  {link(w, p, vs)}" for k, _, p, vs in ev[:BULK_ROWS]]
    if len(ev) > BULK_ROWS:
        rows.append(f"…and {len(ev) - BULK_ROWS} more: {w['site']}/collections/{w['coll']}")
    return head + "\n" + "\n".join(rows)


# ── memory ───────────────────────────────────────────────────────────────────
def wstate(st, w):
    return st["w"].setdefault(w["id"], {"items": {}})


def check(st, w, now):
    """Read one list; returns (events, '') or (None, why it failed)."""
    prods, why = fetch(w)
    if prods is None:
        return None, why
    ws = wstate(st, w)
    rs = rows_of(w, prods)
    items = ws["items"]
    first = not ws.get("learnt")
    if not first and ws.get("n", 0) >= 10 and len(rs) < 0.5 * ws["n"]:
        ws["low"] = ws.get("low", 0) + 1
        if ws["low"] < 3:          # a short read now and then is ignored; three in a row is the new normal
            log(f"{w['id']}: only {len(rs)} in this read (was {ws['n']}); ignored")
            return [], ""
    ws["low"] = 0
    ws["n"] = len(rs)
    today = int(now // 86400)
    was_in = {k for k, it in items.items() if it.get("a")}
    ev = []
    for key, (p, vs) in rs.items():
        av, pr = available(vs), low_price(vs)
        it = items.get(key)
        if it is None:
            items[key] = {"t": p["title"].strip()[:60], "a": av, "in": first or av, "p": pr, "s": today}
            if av and not first:
                items[key]["al"] = now
                ev.append(("new", key, p, vs))
            continue
        it["t"], it["p"], it["s"] = p["title"].strip()[:60], pr, today
        if av:
            it.pop("so", None)
            if not it["a"]:
                kind = "back" if it.get("in") else "new"
                it["a"] = it["in"] = True
                if now - it.get("al", 0) >= GUARD:
                    it["al"] = now
                    ev.append((kind, key, p, vs))
        elif it["a"]:
            it["so"] = it.get("so", 0) + 1
            if it["so"] >= SOLD_CONFIRM:
                it["a"] = False
                it.pop("so", None)
    if w.get("gone") and not first and was_in and len(rs) >= 0.6 * len(was_in):
        for key in was_in - set(rs):          # dropped from a list that drops what sells out
            it = items[key]
            it["so"] = it.get("so", 0) + 1
            if it["so"] >= SOLD_CONFIRM:
                it["a"] = False
                it.pop("so", None)
    for key in [k for k, it in items.items() if today - it.get("s", today) > KEEP_DAYS]:
        del items[key]
    if first:
        ws["learnt"] = True
        log(f"{w['id']}: learnt {len(rs)} ({sum(1 for _, vs in rs.values() if available(vs))} in stock)")
    return ev, ""


def load():
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
        assert isinstance(st, dict)
    except (OSError, ValueError, AssertionError):
        st = {}
    if "items" in st and "w" not in st:      # memory from the first version: Whiff Culture partials only
        items = st.pop("items") or {}
        st["w"] = {"whiff-partials": {"items": items, "n": st.pop("n", len(items)), "learnt": bool(items),
                                      "fail_since": st.pop("fail_since", None),
                                      "fail_warned": st.pop("fail_warned", False)}}
        if st.get("hello"):
            st["cover"] = ["whiff-partials"]
    st.setdefault("w", {})
    st["v"] = 2
    return st


def dump(st):
    return json.dumps(st, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def save(st):
    tmp = STATE + ".tmp"
    with open(tmp, "wb") as f:
        f.write(dump(st))
    os.replace(tmp, STATE)


def git(args, data=None, env=None):
    try:
        r = subprocess.run(["git", *args], input=data, capture_output=True, timeout=60,
                           env={**os.environ, **(env or {})})
        return r.returncode, r.stdout, r.stderr.decode("utf-8", "replace").strip()
    except Exception as e:
        return 1, b"", repr(e)


def pull(tries=PULL_TRIES):
    """Copy perfume.json from the state branch. False: couldn't read it — then this run
    neither saves nor greets, so a passing GitHub hiccup can't wipe the memory."""
    if not BRANCH:
        return True
    err = ""
    for attempt in range(tries):
        if attempt:
            time.sleep(5)
        rc, _, err = git(["fetch", "-q", "--depth=1", "origin", f"+refs/heads/{BRANCH}:refs/perfume/state"])
        if rc == 0:
            rc, data, err = git(["show", "refs/perfume/state:perfume.json"])
            if rc == 0:
                with open(STATE, "wb") as f:
                    f.write(data)
                _pushed[0] = data
            else:
                log(f"the {BRANCH} branch has no perfume.json: starting fresh")
            return True
        if "couldn't find remote ref" in err:
            log(f"no {BRANCH} branch yet: starting fresh")
            return True
    log(f"couldn't read the {BRANCH} branch ({err[:160]})")
    return False


def push(st, why):
    if not BRANCH or not _can_push[0]:
        return
    data = dump(st)
    if data == _pushed[0]:
        return
    rc, blob, err = git(["hash-object", "-w", "--stdin"], data)
    if rc == 0:
        rc, tree, err = git(["mktree"], b"100644 blob " + blob.strip() + b"\tperfume.json\n")
    if rc == 0:
        ident = {"GIT_AUTHOR_NAME": "github-actions", "GIT_AUTHOR_EMAIL": "actions@github.com",
                 "GIT_COMMITTER_NAME": "github-actions", "GIT_COMMITTER_EMAIL": "actions@github.com"}
        rc, commit, err = git(["commit-tree", tree.decode().strip(), "-m", "perfume state [skip ci]"], env=ident)
    if rc == 0:
        rc, _, err = git(["push", "-q", "-f", "origin", f"{commit.decode().strip()}:refs/heads/{BRANCH}"])
    if rc == 0:
        _pushed[0] = data
        log(f"saved ({why})")
    else:
        log(f"couldn't save to {BRANCH}: {err[:160]}")


# ── keeping the runs going ───────────────────────────────────────────────────
def gh(method, path, body=None):
    hdr = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
           "User-Agent": "perfume-watcher"}
    tok = os.getenv("GITHUB_TOKEN", "")
    if tok:
        hdr["Authorization"] = f"Bearer {tok}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{GH_API}{path}", data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, type(e).__name__


def queue_next():
    """Make sure another run of this workflow is waiting to start when this one ends."""
    if not (CHAIN and REPO):
        return None
    code, body = gh("GET", f"/repos/{REPO}/actions/workflows/{WF}/runs?per_page=10")
    if code == 200:
        try:
            runs = json.loads(body).get("workflow_runs") or []
        except ValueError:
            runs = []
        if any(str(r.get("id")) != RUN_ID and r.get("status") in ("queued", "pending", "waiting", "requested")
               for r in runs):
            log("the next run is already waiting")
            return True
    code, _ = gh("POST", f"/repos/{REPO}/actions/workflows/{WF}/dispatches", {"ref": "main"})
    log("queued the next run" if code == 204 else f"couldn't queue the next run (HTTP {code})")
    return code == 204


# ── Telegram ─────────────────────────────────────────────────────────────────
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
    """Your chat with the perfume bot, from your /start (only ever the perfume bot's updates)."""
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
    for attempt in range(2):
        wait = _last_send[0] + SEND_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        r = tg(token, "sendMessage", {"chat_id": chat, "text": text[:4000],
                                      "disable_web_page_preview": "false" if preview else "true"})
        _last_send[0] = time.time()
        retry = (r.get("parameters") or {}).get("retry_after")
        if r.get("ok") or r.get("error_code") != 429 or not isinstance(retry, int) or retry > 30:
            break
        time.sleep(retry)
    if not r.get("ok"):
        log(f"Telegram refused a message ({r.get('error_code')}: {r.get('description', '')[:80]})")
    return bool(r.get("ok"))


def ensure_dest(st):
    if not _dest:
        _dest.append(resolve(st))
    return _dest[0]


def send(st, text, preview=False):
    token, chat, mine = ensure_dest(st)
    if raw_send(token, chat, text, preview):
        return True
    if mine:
        _dest[0] = (HW_TOKEN, HW_CHAT, False)
        return raw_send(HW_TOKEN, HW_CHAT, text, preview)
    return False


def summary(st, ids):
    by = {}
    for w in WATCHES:
        if w["id"] in ids:
            by.setdefault(w["store"], []).append(w)
    out = []
    for store, ws in by.items():
        parts = []
        for w in ws:
            s = wstate(st, w)
            n_in = sum(1 for it in s["items"].values() if it.get("a"))
            n = (f"{n_in} in stock" if not parts else str(n_in)) if s.get("learnt") else "can't read it yet"
            parts.append(f"{w['label']} ({n})")
        out.append(f"• {store}: " + ", ".join(parts))
    return out


def greet(st):
    """The first message, a 'Connected' when the perfume bot starts working, a note when
    more stores are added — and a reminder now and then if the perfume bot can't reach you."""
    token, chat, mine = ensure_dest(st)
    ids = [w["id"] for w in WATCHES]
    hello = tag() if mine else "hw"
    tail = ("I'll message you the moment something new is listed or comes back in stock, "
            "and when one of these stores starts a new sale.")
    later = [] if mine or TOKEN else ["(Alerts come here until your perfume bot is set up.)"]
    added = [i for i in ids if i not in (st.get("cover") or ["whiff-partials"])]
    if mine and st.get("hello") != hello:
        text = ["✅ Connected. Perfume alerts will come here."] + summary(st, ids) + [tail]
    elif not mine and not st.get("hello"):
        text = ["🧴 Perfume watcher is on."] + summary(st, ids) + [tail] + later
    elif added:
        text = ["🧴 Perfume watcher now also covers:"] + summary(st, added) + [tail] + later
    else:
        if not mine and TOKEN and time.time() - st.get("nudge", 0) >= NUDGE_EVERY:
            st["nudge"] = time.time()
            why = ("Telegram didn't accept the PERFUME_BOT_TOKEN secret; copy the token from @BotFather again"
                   if st.get("why") == "token" else "Open it in Telegram and tap Start")
            raw_send(token, chat, f"🧴 Your perfume bot can't message you yet. {why} "
                                  "(perfume alerts come here until then).", False)
        return
    if raw_send(token, chat, "\n".join(text), False):
        st["hello"], st["cover"] = hello, ids


def failed(st, w, now, why):
    ws = wstate(st, w)
    if not ws.get("fail_since"):
        ws["fail_since"] = now
    if ws.get("fail_warned") or now - ws["fail_since"] < FAIL_WARN:
        return
    group = [x for x in WATCHES if x["store"] == w["store"] and wstate(st, x).get("fail_since")
             and not wstate(st, x).get("fail_warned") and now - wstate(st, x)["fail_since"] >= FAIL_WARN - 60]
    for x in group:
        wstate(st, x)["fail_warned"] = True
    since = min(wstate(st, x)["fail_since"] for x in group)
    what = ", ".join(x["label"] for x in group)
    if why == "HTTP 404":
        send(st, f"⚠️ {w['store']}'s {what} page has gone (404) since {hm(since)}. I'll keep checking in case it comes back.")
    else:
        send(st, f"⚠️ I can't read {w['store']}'s {what} since {hm(since)} ({why}). I'll keep trying.")


def recovered(st, w):
    if not wstate(st, w).get("fail_warned"):
        wstate(st, w)["fail_since"] = None
        return
    for x in WATCHES:
        if x["store"] == w["store"]:
            wstate(st, x)["fail_since"], wstate(st, x)["fail_warned"] = None, False
    send(st, f"✅ {w['store']} can be read again.")


def deliver(st, w, ev, now):
    """Send one watch's news: one message each, or one list when there are many. An item
    another list already announced in the last few hours isn't announced twice."""
    sent = st.setdefault("sent", {})
    keep = []
    for e in ev:
        dk = f"{host(w['site'])}|{e[1]}"
        prev = sent.get(dk)
        if prev and prev[1] != w["id"] and now - prev[0] < XGUARD:
            log(f"{w['id']}: {e[2]['title']} — already announced via {prev[1]}")
            continue
        sent[dk] = [now, w["id"]]
        keep.append(e)
    for kind, _, p, _ in keep:
        log(f"{w['id']}: {kind}: {p['title']}")
    if len(keep) > BULK:
        send(st, bulk_text(w, keep))
    else:
        for kind, _, p, vs in keep:
            send(st, alert_text(w, kind, p, vs), preview=True)
    for k in [k for k, (t, _) in sent.items() if now - t > max(XGUARD, 86400)]:
        del sent[k]
    return bool(keep)


def check_sales(st, site, store, now):
    """A note when the store starts a sale: a sale-like collection that's new or no longer empty."""
    cs = []
    for page in range(1, 4):
        try:
            code, body = get(f"{site}/collections.json?limit=250&page={page}&_={int(time.time() * 1000)}")
            got = json.loads(body).get("collections") if code == 200 else None
        except Exception:
            got = None
        if not isinstance(got, list):
            return False
        cs += [c for c in got if isinstance(c, dict)]
        if len(got) < 250:
            break
    watched = {w["coll"] for w in WATCHES if w["site"] == site}
    cur = {}
    for c in cs:
        h, t, n = c.get("handle"), str(c.get("title") or ""), c.get("products_count")
        if (isinstance(h, str) and isinstance(n, int) and h not in watched and not SALE_SKIP.search(h)
                and SALE_RE.search(h.replace("-", " ") + " " + t)):
            cur[h] = (n, t.strip() or h)
    sales = st.setdefault("sales", {})
    known = sales.get(host(site))
    sales[host(site)] = {h: n for h, (n, _) in cur.items()}
    if known is None:
        return False
    new = [(h, n, t) for h, (n, t) in cur.items() if n > 0 and known.get(h, 0) == 0]
    if not new:
        return False
    log(f"{store}: new sale {[h for h, _, _ in new]}")
    rows = [f"• {t} — {n} item{'s' if n != 1 else ''}\n  {site}/collections/{h}" for h, n, t in new[:8]]
    send(st, f"🏷️ NEW SALE{'S' if len(new) > 1 else ''} · {store}\n" + "\n".join(rows))
    return True


# ── the run ──────────────────────────────────────────────────────────────────
def _bye(*_):
    raise SystemExit(0)


def main():
    signal.signal(signal.SIGTERM, _bye)
    for f in (STOP, DONE):
        if os.path.exists(f):
            os.remove(f)
    _can_push[0] = pull()
    st = load()
    queue_next()
    t0 = time.time()
    run = {"no": os.getenv("GITHUB_RUN_NUMBER", ""), "checks": 0, "from": int(t0)}
    due = {w["id"]: t0 for w in WATCHES}
    sites = list(dict.fromkeys((w["site"], w["store"]) for w in WATCHES))
    sales_due = {s: t0 + SALES_FIRST for s, _ in sites}
    pause, tried = {}, set()
    greeted = queued = False
    last_push = next_pull = t0
    try:
        while not os.path.exists(STOP) and time.time() - t0 < MAX_RUN:
            now = time.time()
            if not _can_push[0] and now >= next_pull:
                next_pull = now + PULL_RETRY
                if pull(tries=1):              # memory readable again: carry on from it
                    _can_push[0] = True
                    st = load()
                    tried.clear()
            w = next((w for w in WATCHES if now >= due[w["id"]] and now >= pause.get(w["site"], 0)), None)
            sale = next((s for s in sites if now >= sales_due[s[0]] and now >= pause.get(s[0], 0)), None)
            if w is None and sale is None:
                time.sleep(0.2)
                continue
            urgent = False
            if w is not None:
                try:
                    ev, why = check(st, w, now)
                except Exception as e:
                    ev, why = None, "unexpected data"
                    log(f"{w['id']}: error {e!r}")
                if ev is None:
                    log(f"{w['id']}: read failed: {why}")
                    failed(st, w, now, why)
                    if why in ("HTTP 429", "HTTP 403"):
                        pause[w["site"]] = time.time() + BACKOFF
                else:
                    recovered(st, w)
                    urgent = deliver(st, w, ev, now) if ev else False
                due[w["id"]] = time.time() + w["every"]
                tried.add(w["id"])
                run["checks"] += 1
            else:
                try:
                    urgent = check_sales(st, sale[0], sale[1], now)
                except Exception as e:
                    log(f"{sale[1]}: sales check error {e!r}")
                sales_due[sale[0]] = time.time() + SALES_EVERY
            run["to"] = int(time.time())
            st["run"] = run
            if not greeted and len(tried) == len(WATCHES) and _can_push[0]:
                greeted = True
                before = (st.get("hello"), st.get("cover"))
                greet(st)
                urgent = urgent or (st.get("hello"), st.get("cover")) != before
            save(st)
            if urgent or time.time() - last_push >= PUSH_EVERY:
                push(st, "news" if urgent else "regular")
                last_push = time.time()
            if not queued and time.time() - t0 >= MAX_RUN - 120:
                queued = True
                queue_next()
    finally:
        st["run"] = run
        save(st)
        push(st, "end of run")
        log(f"stopped after {run['checks']} checks")
        open(DONE, "w").close()


if __name__ == "__main__":
    main()
