#!/usr/bin/env python3
"""
Hot Wheels case table for the tracker  ·  hw_cases.json
=======================================================
Reads the collector checklists on 164custom.com — every mainline case (A, B, C …
Q) of the last two years, this year and next year, plus each year's Treasure
Hunt and Super Treasure Hunt lists — and saves them as hw_cases.json, which the
tracker uses to say which case a car is from and whether it's a TH / STH.

Runs on its own once a day (.github/workflows/cases.yml). It never touches a
store, and the tracker itself makes no extra requests for this: it only reads
the saved file. New cases show up here as soon as the checklist site publishes
them (usually weeks before the cars reach Indian shops).

A page that can't be read, or reads as empty, never wipes what we already
have: that case keeps its previous rows.
"""
import html
import json
import os
import re
import sys
import time

OUT = os.getenv("HW_CASES_FILE", "hw_cases.json")
BASE = "https://164custom.com/hot-wheels"
# Mattel's case letters skip I and O; a year has had up to Q so far
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
PAUSE_S = float(os.getenv("CASES_PAUSE_S", "0.6"))     # polite: one page at a time

_cells = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_rows = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)


def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parse_table(page: str) -> list[dict]:
    """Rows of a 164custom checklist table: Year, Image, Name, HW #, Color,
    Part, Type, Series, Series #, Case."""
    head, out = None, []
    for r in _rows.findall(page or ""):
        cells = [_txt(c) for c in _cells.findall(r)]
        if not cells:
            continue
        if head is None and "Name" in cells and "Case" in cells:
            head = cells
            continue
        if head is None or len(cells) != len(head) or not cells[0][:4].isdigit():
            continue
        row = dict(zip(head, cells))
        try:
            year = int(row.get("Year", "")[:4])
        except ValueError:
            continue
        num = row.get("HW #", "").strip()
        out.append({
            "y": year,
            "c": (row.get("Case") or "").strip().upper()[:2],
            "n": int(num) if num.isdigit() else None,
            "name": row.get("Name", "").strip(),
            "col": row.get("Color", "").strip(),
            "part": row.get("Part", "").strip().upper(),
            "ser": row.get("Series", "").strip(),
            "sn": row.get("Series #", "").strip(),
            "type": row.get("Type", "").strip(),
        })
    return [r for r in out if r["name"]]


def _get(url: str):
    from curl_cffi import requests as http
    time.sleep(PAUSE_S)
    try:
        r = http.get(url, timeout=25, impersonate="chrome124",
                     headers={"Accept-Language": "en-US,en;q=0.9"})
    except Exception as e:
        print(f"  ! {url}: {e}")
        return None
    if r.status_code != 200:
        print(f"  ! {url}: HTTP {r.status_code}")
        return None
    return r.text


def build(years, fetch=_get) -> dict:
    """{"cases": {"2026-M": [rows]}, "th": {year: [rows]}, "sth": {year: [rows]},
    "failed": [urls]} — only what could be read this time."""
    cases, th, sth, failed = {}, {}, {}, []
    for y in years:
        misses = 0
        for L in LETTERS:
            url = f"{BASE}/case-{L.lower()}/{y}.html"
            page = fetch(url)
            rows = [r for r in parse_table(page or "") if r["y"] == y]
            if page is None:
                failed.append(url)
            if rows:
                cases[f"{y}-{L}"] = rows
                misses = 0
            else:
                misses += 1
                # past Q, two empty letters in a row end the year
                if L > "Q" and misses >= 2:
                    break
        for kind, store in (("treasure-hunt", th), ("super-treasure-hunt", sth)):
            url = f"{BASE}/{kind}/{y}.html"
            page = fetch(url)
            if page is None:
                failed.append(url)
            rows = [r for r in parse_table(page or "") if r["y"] == y]
            if rows:
                store[str(y)] = rows
    return {"cases": cases, "th": th, "sth": sth, "failed": failed}


def merge(old: dict, new: dict) -> dict:
    """New readings replace old ones case by case; anything this run couldn't
    read keeps its previous rows."""
    cases = dict(old.get("cases") or {})
    cases.update(new["cases"])
    th = dict(old.get("th") or {})
    th.update(new["th"])
    sth = dict(old.get("sth") or {})
    sth.update(new["sth"])
    return {"cases": cases, "th": th, "sth": sth}


def flatten(data: dict) -> list[dict]:
    """One row per car the tracker can match: case rows, with TH / STH marked
    (by part number, else by year + number + colour). TH / STH rows a case page
    doesn't list yet are added from their own lists."""
    th_parts, sth_parts, th_keys, sth_keys = set(), set(), set(), set()
    extra = []
    for kind, lists in (("th", data.get("th") or {}), ("sth", data.get("sth") or {})):
        for rows in lists.values():
            for r in rows:
                key = (r["y"], r["n"], r["col"].lower())
                (th_parts if kind == "th" else sth_parts).add(r["part"])
                (th_keys if kind == "th" else sth_keys).add(key)
                extra.append((kind, r))
    out, have = [], set()
    for case_key in sorted(data.get("cases") or {}):
        for r in data["cases"][case_key]:
            key = (r["y"], r["n"], r["col"].lower())
            e = {k: r[k] for k in ("y", "c", "n", "name", "col", "part", "ser", "sn")}
            if (r["part"] and r["part"] in sth_parts) or key in sth_keys:
                e["sth"] = 1
            elif (r["part"] and r["part"] in th_parts) or key in th_keys:
                e["th"] = 1
            # the same car listed twice (two part numbers) is kept once — but a
            # Super TH and its regular car stay apart even when the page gives
            # both the same colour (2026 L: Nissan Maxima Drift Car, "Black")
            sig = (e["y"], e["c"], e["n"], e["name"].lower(), e["col"].lower(), bool(e.get("sth")))
            if sig in have:
                continue
            have.add(sig)
            out.append(e)
    for kind, r in extra:
        sig = (r["y"], r["c"], r["n"], r["name"].lower(), r["col"].lower(), kind == "sth")
        if sig in have or not r["c"]:
            continue
        e = {k: r[k] for k in ("y", "c", "n", "name", "col", "part", "ser", "sn")}
        e[kind] = 1
        have.add(sig)
        out.append(e)
    out.sort(key=lambda e: (e["y"], e["c"], e["n"] or 0, e["name"]))
    return out


def dump(doc: dict) -> str:
    """JSON with one car (and one case) per line, so a day's changes read as a
    short diff."""
    j = lambda o: json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    raw = doc["raw"]
    parts = ["{", f'"source":{j(doc["source"])},', f'"years":{j(doc["years"])},',
             f'"cases":{j(doc["cases"])},', '"cars":[']
    parts.append(",\n".join(j(e) for e in doc["cars"]))
    parts.append('],\n"raw":{')
    blocks = []
    for kind in ("cases", "th", "sth"):
        inner = ",\n".join(f"{j(k)}:{j(v)}" for k, v in sorted(raw.get(kind, {}).items()))
        blocks.append(f'{j(kind)}:{{\n{inner}\n}}')
    parts.append(",\n".join(blocks))
    parts.append("}\n}\n")
    return "\n".join(parts)


def main() -> int:
    year = int(os.getenv("CASES_YEAR") or time.strftime("%Y"))
    years = [year - 2, year - 1, year, year + 1]
    old = {}
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding="utf-8")).get("raw") or {}
        except Exception:
            old = {}
    got = build(years)
    print(f"read {len(got['cases'])} case pages, TH lists {sorted(got['th'])}, "
          f"STH lists {sorted(got['sth'])}; {len(got['failed'])} page(s) failed")
    if not got["cases"] and old:
        print("nothing readable this time — keeping the saved table")
        return 0
    raw = merge(old, got)
    cars = flatten(raw)
    doc = {"source": "164custom.com checklists", "years": years,
           "cases": sorted(raw["cases"]), "cars": cars, "raw": raw}
    new_txt = dump(doc)
    old_txt = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    if new_txt == old_txt:
        print("no change")
        return 0
    with open(OUT + ".tmp", "w", encoding="utf-8") as f:
        f.write(new_txt)
    os.replace(OUT + ".tmp", OUT)
    by = {}
    for e in cars:
        by.setdefault(e["y"], set()).add(e["c"])
    print(f"saved {len(cars)} cars: " + ", ".join(f"{y} {''.join(sorted(c))}" for y, c in sorted(by.items()))
          + f"; TH {sum(1 for e in cars if e.get('th'))}, STH {sum(1 for e in cars if e.get('sth'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
