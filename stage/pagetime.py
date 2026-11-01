#!/usr/bin/env python3
"""Lift each article's publication time from the article page itself.

    python3 stage/pagetime.py backfill [--domains a,b,...] [--limit N]   the saved feed history
    python3 stage/pagetime.py new [--limit N]                              items the archive holds without one

A feed states when its publisher says an item appeared; the page usually states it again, in its own
metadata (schema.org JSON-LD datePublished, the article:published_time meta tag, or a <time> element),
often with its zone. Both are kept, and stage/archive.py reconciles them with the moment the item was
first seen. Results go to ~/.cache/revott-stamps/pagetimes.jsonl, one line per page, so no page is read
twice.

Manners: the user agent names this project; robots.txt is obeyed; one request per host every two
seconds; a host that refuses three times is left alone for the rest of the run. Google News links lead
to Google, not to the article, and are not read. Standard library only.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import email.utils
import gzip
import html
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import HISTORY  # noqa: E402  (the feed history folder, from .paths.json)

UA = "revott-stamps/1.0 (+https://nth-member.github.io/revott-stamps/)"
CACHE = Path.home() / ".cache" / "revott-stamps" / "pagetimes.jsonl"
ARCHIVE_PENDING = Path(__file__).resolve().parents[1] / ".pending-pages.json"   # written by archive.py
PER_HOST_GAP = 2.0
REFUSALS_BEFORE_LEAVING = 3

PUB_META = ["article:published_time", "og:article:published_time", "article:published", "og:published_time",
            "datepublished", "pubdate", "publishdate", "publish-date", "publish_date", "parsely-pub-date",
            "sailthru.date", "dc.date.issued", "dcterms.issued", "dcterms.created", "dc.date", "dcterms.date",
            "citation_online_date", "citation_publication_date", "prism.publicationdate", "date", "datecreated"]
MOD_META = ["article:modified_time", "og:updated_time", "datemodified", "dcterms.modified", "lastmod", "last-modified"]
ARTICLE = re.compile(r"article|posting|report", re.I)
ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,]\d+)?)?)?\s*(Z|[+-]\d{2}:?\d{2}|[+-]\d{2})?$", re.I)


def parse_time(raw: str):
    """A stated time -> (UTC datetime, resolution 's'|'min'|'day', zone stated) or None."""
    s = html.unescape((raw or "").strip())
    m = ISO.match(s)
    if m:
        y, mo, d, hh, mi, ss, z = m.groups()
        res = "day" if hh is None else ("min" if ss is None else "s")
        t = dt.datetime(int(y), int(mo), int(d), int(hh or 0), int(mi or 0), int(ss or 0))
        if z is None:
            return t.replace(tzinfo=dt.timezone.utc), res, False
        if z.upper() == "Z":
            off = dt.timedelta(0)
        else:
            z = z.replace(":", "")
            off = (-1 if z[0] == "-" else 1) * dt.timedelta(hours=int(z[1:3]), minutes=int(z[3:5] or 0))
        return (t - off).replace(tzinfo=dt.timezone.utc), res, True
    try:
        t = email.utils.parsedate_to_datetime(s)
        return t.astimezone(dt.timezone.utc), "s", t.tzinfo is not None
    except (TypeError, ValueError, IndexError):
        return None


def _ld_objects(text):
    for block in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", text, re.S | re.I):
        block = block.strip().removeprefix("<!--").removesuffix("-->").strip()
        try:
            data = json.loads(block)
        except ValueError:
            for k, v in re.findall(r'"(datePublished|dateModified|dateCreated)"\s*:\s*"([^"]+)"', block):
                yield {"@type": "?", k: v}
            continue
        stack = [data]
        while stack:
            o = stack.pop()
            if isinstance(o, list):
                stack.extend(o)
            elif isinstance(o, dict):
                yield o
                stack.extend(v for v in o.values() if isinstance(v, (dict, list)))


def extract(text: str) -> dict:
    """The page's own statement of publication: {published, modified, via}, raw strings; {} if none."""
    out = {}
    objs = sorted(_ld_objects(text), key=lambda o: 0 if ARTICLE.search(str(o.get("@type", ""))) else 1)
    for o in objs:
        p = o.get("datePublished") or o.get("dateCreated") or o.get("uploadDate")
        if isinstance(p, str) and parse_time(p):
            m = o.get("dateModified")
            out = {"published": p, "modified": m if isinstance(m, str) else None, "via": "json-ld"}
            break
    metas = {}
    for tag in re.findall(r"<meta\b[^>]*>", text, re.I):
        a = {k.lower(): v for k, _, v in re.findall(r'([\w:.-]+)\s*=\s*(["\'])(.*?)\2', tag, re.S)}
        key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
        if key and "content" in a and key not in metas:
            metas[key] = a["content"]
    if "published" not in out:
        for k in PUB_META:
            if k in metas and parse_time(metas[k]):
                out = {"published": metas[k], "via": "meta " + k}
                break
    if out and not out.get("modified"):
        out["modified"] = next((metas[k] for k in MOD_META if k in metas and parse_time(metas[k])), None)
    if "published" not in out:
        times = re.findall(r"<time\b[^>]*>", text, re.I)
        for t in [t for t in times if re.search(r'itemprop=["\']datePublished|\bpubdate\b|publish', t, re.I)] or times:
            m = re.search(r'datetime=["\']([^"\']+)', t, re.I)
            if m and parse_time(m.group(1)):
                out = {"published": m.group(1), "via": "time tag"}
                break
    return out


class Hosts:
    """robots.txt, spacing and refusals, per host."""

    def __init__(self):
        self.lock = threading.Lock()
        self.robots, self.next_at, self.refused, self.host_locks = {}, {}, {}, {}

    def _robots(self, scheme_host: str):
        if scheme_host not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                req = urllib.request.Request(scheme_host + "/robots.txt", headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=15) as r:
                    rp.parse(r.read(500_000).decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                rp.parse([] if 400 <= e.code < 500 else ["User-agent: *", "Disallow: /"])
            except Exception:
                rp.parse(["User-agent: *", "Disallow: /"])        # unreadable: do not guess
            self.robots[scheme_host] = rp
        return self.robots[scheme_host]

    def lock_for(self, host):
        with self.lock:
            return self.host_locks.setdefault(host, threading.Lock())


def fetch_page(url: str, hosts: Hosts) -> dict:
    m = re.match(r"(https?://[^/]+)", url)
    if not m:
        return {"u": url, "status": "bad url"}
    sh = m.group(1)
    host = sh.split("//", 1)[1]
    with hosts.lock_for(host):
        if hosts.refused.get(host, 0) >= REFUSALS_BEFORE_LEAVING:
            return {"u": url, "status": "host refuses", "skip": True}
        if not hosts._robots(sh).can_fetch(UA, url):
            return {"u": url, "status": "robots.txt disallows"}
        wait = hosts.next_at.get(host, 0) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        hosts.next_at[host] = time.monotonic() + PER_HOST_GAP
        rec = {"u": url, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                                                       "Accept-Encoding": "gzip, deflate"})
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = r.read(4_000_000)
                enc = r.headers.get("Content-Encoding", "")
                if enc == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                elif enc == "deflate":
                    raw = zlib.decompress(raw)
                text = raw.decode(r.headers.get_content_charset() or "utf-8", errors="replace")
            rec["status"] = "ok"
            rec.update(extract(text))
            if "published" not in rec:
                rec["status"] = "no time on the page"
        except urllib.error.HTTPError as e:
            rec["status"] = f"HTTP {e.code}"
            if e.code in (401, 403, 429, 451):
                hosts.refused[host] = hosts.refused.get(host, 0) + 1
        except Exception as e:  # one page must not stop the others
            rec["status"] = f"{type(e).__name__}"[:60]
        return rec


def done_urls() -> set:
    if not CACHE.exists():
        return set()
    out = set()
    for line in CACHE.open():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not r.get("skip"):
            out.add(r["u"])
    return out


def run(urls: list[str], limit: int, label: str) -> None:
    seen = done_urls()
    todo = [u for u in dict.fromkeys(urls) if u not in seen and "news.google.com" not in u][:limit]
    print(f"{label}: {len(todo)} pages to read ({len(seen)} already read)", flush=True)
    hosts, n, ok = Hosts(), 0, 0
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    by_host = {}
    for u in todo:
        by_host.setdefault(u.split("/")[2], []).append(u)
    # Interleave hosts so that the per-host spacing, not the queue, sets the pace.
    order = []
    while any(by_host.values()):
        for h in list(by_host):
            if by_host[h]:
                order.append(by_host[h].pop(0))
    with CACHE.open("a") as out, cf.ThreadPoolExecutor(8) as pool:
        for rec in pool.map(lambda u: fetch_page(u, hosts), order):
            n += 1
            ok += rec.get("status") == "ok"
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if n % 500 == 0:
                print(f"  {n}/{len(order)} read, {ok} with a time", flush=True)
    print(f"{label}: {n} read, {ok} with a time on the page", flush=True)


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else "new"
    opt = dict(zip(argv[1::2], argv[2::2]))
    limit = int(opt.get("--limit", "1000000"))
    if mode == "backfill":
        domains = set(opt["--domains"].split(",")) if "--domains" in opt else None
        urls = []
        with gzip.open(HISTORY / "items.jsonl.gz", "rt") as f:
            for line in f:
                i = json.loads(line)
                if domains is None or i["_jomo"]["domain"] in domains:
                    urls.append(i["url"])
        run(urls[::-1], limit, "backfill")        # newest first
    elif mode == "new":
        urls = json.loads(ARCHIVE_PENDING.read_text()) if ARCHIVE_PENDING.exists() else []
        run(urls, limit, "new")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
