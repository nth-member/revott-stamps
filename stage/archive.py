#!/usr/bin/env python3
"""Build the stamps' archive: every feed item seen, dated once, filed on Nsukka's days.

    python3 stage/archive.py

Reads the feed history (stage/history.py), the JOMO SFO-WAM catalogue of sources, the page times
lifted by stage/pagetime.py and REVOTT's keys, and writes docs/data/:

    index.json             as-of, the days held with their item counts and TNLDY ranges
    sources.json           id -> [label, domain, perspective, date-only]
    coverage.json          per source, the stretches across which it was being read: [[from, to], ...]
    keys.json              REVOTT's keys: [x, reading, apocalypse layers]
    days/YYYY-MM-DD.json   the items whose instant falls on that day in Nsukka

and the untracked .pending-pages.json, the article pages not yet read for their own time.

Each item has up to three clocks: the time its page states, the time its feed states, and the moment
it was first seen here, which bounds both from above. One instant is chosen, and how:

    p   the page's stated time, given with its zone and not after the item was first seen
    f   the feed's stated time, not after it was first seen
    d   the feed's time from a source whose feed gives the day only (most items at 00:00 or 12:00:00)
    s   the moment it was first seen, when neither stated time stands

When page and feed differ by a whole number of hours, one of them is local time written as UTC; for a
publisher east of UTC, where nearly every source here is, that one reads late, so the earlier is taken
(not for day-only feeds). A page time without a zone that disagrees with the feed otherwise yields to it. An item is stored as
[instant, how, source, title, url, first seen, feed time, page time, note], times in epoch ms.
The same inputs always give the same files. Standard library only.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paths import HISTORY, JOMO, REVOTT  # noqa: E402
from pagetime import CACHE, parse_time  # noqa: E402
import nsukka_yg_clock as clock  # noqa: E402

ROOT = HERE.parent
DATA = ROOT / "docs" / "data"
TOL = 60_000                 # one minute of clock disagreement is allowed
HOUR = 3_600_000


def ms(iso: str | None) -> int | None:
    if not iso:
        return None
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return clock.ms_of(t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc))


def nsukka_day(t: int) -> str:
    return dt.datetime.fromtimestamp((t + clock.WAT.utcoffset(None).total_seconds() * 1000) / 1000,
                                     dt.timezone.utc).date().isoformat()


def load_jsonl_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f]


def page_times() -> dict[str, dict]:
    out = {}
    if CACHE.exists():
        for line in CACHE.open():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("status") == "ok" and r.get("published"):
                out[r["u"]] = r
            elif r["u"] not in out and not r.get("skip"):
                out[r["u"]] = r                                  # read, but no time: do not read again
    return out


def date_only_sources(items: list[dict]) -> set[str]:
    """Sources whose feed times are mostly 00:00:00 or 12:00:00 UTC: their feed gives the day only."""
    n, flat = defaultdict(int), defaultdict(int)
    for i in items:
        p = i.get("date_published")
        if p:
            n[i["_jomo"]["source"]] += 1
            if p[11:19] in ("00:00:00", "12:00:00"):
                flat[i["_jomo"]["source"]] += 1
    return {s for s in n if n[s] >= 10 and flat[s] / n[s] >= 0.6}


def reconcile(feed: int | None, page, seen: int, capped: bool, date_only: bool):
    """-> (instant, how, note)"""
    feed_ok = feed is not None and not capped and feed <= seen + TOL
    note = ""
    if page is not None:
        p, _res, zone = page
        if p > seen + TOL:
            note = "the page states a time after the item was first seen"
        elif not feed_ok or abs(p - feed) <= TOL:
            return p, "p", "" if (zone or feed_ok) else "the page gives no zone; read as UTC"
        else:
            d = abs(p - feed)
            hours = round(d / HOUR)
            if hours >= 1 and abs(d - hours * HOUR) <= TOL and not date_only:
                # A zone written wrong on one side: local time labelled as UTC reads late for a
                # publisher east of UTC, where nearly every source here is. The earlier is taken.
                t = min(p, feed)
                return t, ("p" if t == p else "f"), f"page and feed differ by {hours} h, a zone written wrong; the earlier taken"
            if zone:
                return p, "p", f"the feed states {round((feed - p) / 60000):+d} min"
            note = "the page's time has no zone and disagrees with the feed's"
    if feed_ok:
        if date_only:
            return feed, "d", note or "the feed gives the day only"
        return feed, "f", note
    if feed is not None:
        note = note or ("the feed's time was later than its reading" if capped else "the feed states a time after the item was first seen")
    return seen, "s", note or "no time stated"


def keys() -> list:
    sys.path.insert(0, str(REVOTT))
    from revott.sfo import SFO
    sfo = SFO()
    return [[x, sfo.keys[x].reading, sfo.keys[x].apoc] for x in sfo.order]


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


def main() -> int:
    items = load_jsonl_gz(HISTORY / "items.jsonl.gz")
    cover = load_jsonl_gz(HISTORY / "coverage.jsonl.gz")
    catalogue = {s["id"]: s for s in json.loads((JOMO / "feeds" / "catalogue.json").read_text())}
    pages = page_times()
    flat = date_only_sources(items)

    sources = {}
    for i in items:
        j = i["_jomo"]
        c = catalogue.get(j["source"], {})
        sources.setdefault(j["source"], [c.get("label") or i["authors"][0]["name"], c.get("domain") or j["domain"],
                                         c.get("perspective") or j.get("perspective", ""), j["source"] in flat])

    days, pending, hows = defaultdict(list), [], defaultdict(int)
    for i in items:
        seen = ms(i["_first_seen"])
        feed = ms(i.get("date_published"))
        capped = bool(feed is not None and i["_jomo"].get("fetched") and i.get("date_published") == i["_jomo"]["fetched"])
        pg = pages.get(i["url"])
        page = None
        if pg and pg.get("status") == "ok":
            got = parse_time(pg["published"])
            if got:
                page = (clock.ms_of(got[0]), got[1], got[2])
        elif pg is None and "news.google.com" not in i["url"]:
            pending.append(i["url"])
        t, how, note = reconcile(feed, page, seen, capped, i["_jomo"]["source"] in flat)
        hows[how] += 1
        days[nsukka_day(t)].append([t, how, i["_jomo"]["source"], i["title"], i["url"], seen, feed,
                                    page[0] if page else None, note])

    index = {}
    for day, rows in sorted(days.items()):
        rows.sort(key=lambda r: (r[0], r[4]))
        dump(DATA / "days" / f"{day}.json", rows)
        zs = [float(clock.z_of(r[0])) for r in rows]
        index[day] = [len(rows), round(min(zs), 6), round(max(zs), 6)]
    for old in (DATA / "days").glob("*.json"):
        if old.stem not in days:
            old.unlink()

    spans = defaultdict(list)
    for c in cover:
        g = ms(c["generated"])
        for src, (oldest, _newest, _n) in c.get("span", {}).items():
            spans[src].append([min(ms(oldest), g), g])
    coverage = {}
    for src, iv in sorted(spans.items()):
        iv.sort()
        merged = [iv[0][:]]
        for a, b in iv[1:]:
            if a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        coverage[src] = merged

    as_of = max(ms(c["generated"]) for c in cover)
    first = min(ms(c["generated"]) for c in cover)
    dump(DATA / "sources.json", dict(sorted(sources.items())))
    dump(DATA / "coverage.json", coverage)
    dump(DATA / "keys.json", keys())
    dump(DATA / "index.json", {"as_of": as_of, "first_reading": first, "items": len(items),
                               "snapshots": len(cover), "how": dict(sorted(hows.items())), "days": index})
    (ROOT / ".pending-pages.json").write_text(json.dumps(pending[::-1]))
    print(f"archive: {len(items)} items on {len(days)} days, as of "
          f"{dt.datetime.fromtimestamp(as_of / 1000, clock.WAT):%Y-%m-%d %H:%M} Nsukka; clocks {dict(hows)}; "
          f"{len(pending)} pages not yet read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
