#!/usr/bin/env python3
"""Keep every JOMO SFO-WAM feed snapshot, from the checkout's reflog and GitHub's log, read-only.

    python3 stage/history.py

The FEEDS snapshot is one rolling commit, amended every 15 minutes and force-pushed. Until
2026-11-03 this computer made it, so its history is in the checkout's reflog, which git's
automatic gc trims to 30 days; since then GitHub makes it, and logs what each snapshot adds in
feeds/history/ (JOMO SFO-WAM's feeds/history.py, 30 days kept), which this fetches and reads from
origin/main. Together they write, into the history folder named in .paths.json:

    items.jsonl.gz     every distinct item (by id), as first seen, with
                       _first_seen = the generated time of the first snapshot that held it
    coverage.jsonl.gz  one line per snapshot: generated time, the sources that failed in it, and
                       for each source read successfully the publisher-date span of the items it
                       returned [oldest, newest, count] -- the source is covered from its oldest
                       item to the snapshot's time; outside every such span it is NULL, never zero

Running it again merges: items already exported keep their first-seen time.
"""
import gzip, json, subprocess, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from pathlib import Path

from paths import HISTORY, JOMO as REPO
OUT = HISTORY


def load(name):
    p = OUT / name
    if not p.exists():
        return []
    with gzip.open(p, "rt") as f:
        return [json.loads(line) for line in f]


def main():
    shas = subprocess.run(["git", "-C", str(REPO), "reflog", "--format=%H"],
                          capture_output=True, text=True, check=True).stdout.split()
    shas = list(dict.fromkeys(shas))[::-1]
    cat = subprocess.Popen(["git", "-C", str(REPO), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def blob(spec):
        cat.stdin.write((spec + "\n").encode()); cat.stdin.flush()
        head = cat.stdout.readline().split()
        if head[-1] == b"missing":
            return None
        data = cat.stdout.read(int(head[2])); cat.stdout.read(1)
        return data

    items = {i["id"]: i for i in load("items.jsonl.gz")}
    cover = {c["generated"]: c for c in load("coverage.jsonl.gz")}
    for s in shas:
        raw = blob(f"{s}:docs/feeds/all.json") or blob(f"{s}:public/feeds/all.json")
        if not raw:
            continue
        try:
            f = json.loads(raw)
        except ValueError:
            continue
        gen = f.get("_jomo", {}).get("generated")
        if not gen:
            continue
        srcs = f["_jomo"].get("sources", [])
        failed = sorted(x["id"] for x in srcs if x.get("error"))
        span = {}
        for i in f.get("items", []):
            src = i["_jomo"]["source"]
            if src in failed or i["_jomo"].get("fetched") != gen or "date_published" not in i:
                continue
            o = span.setdefault(src, [i["date_published"], i["date_published"], 0])
            o[0] = min(o[0], i["date_published"]); o[1] = max(o[1], i["date_published"]); o[2] += 1
        cover[gen] = {"generated": gen, "commit": s, "sources": len(srcs), "failed": failed,
                      "span": dict(sorted(span.items()))}
        for i in f.get("items", []):
            if i["id"] not in items or items[i["id"]]["_first_seen"] > gen:
                items[i["id"]] = dict(i, _first_seen=gen)
    fetch = subprocess.run(["git", "-C", str(REPO), "fetch", "-q", "origin"], capture_output=True, text=True)
    if fetch.returncode:
        print("history: fetch failed, so GitHub's log is read as last fetched:", fetch.stderr.strip()[:200])
    names = subprocess.run(["git", "-C", str(REPO), "ls-tree", "--name-only", "origin/main", "feeds/history/"],
                           capture_output=True, text=True).stdout.split()
    logged = 0
    for name in names:
        raw = blob(f"origin/main:{name}")
        for line in gzip.decompress(raw).decode().splitlines() if raw else []:
            r = json.loads(line)
            gen = r["generated"]
            logged += 1
            cover.setdefault(gen, {"generated": gen, "commit": None, "sources": r["sources"], "failed": r["failed"],
                                   "span": r["span"]})
            for i in r["new"]:
                if i["id"] not in items or items[i["id"]]["_first_seen"] > gen:
                    items[i["id"]] = dict(i, _first_seen=gen)
    cat.stdin.close(); cat.wait()

    rows = sorted(items.values(), key=lambda i: (i["_first_seen"], i["id"]))
    with gzip.open(OUT / "items.jsonl.gz", "wt") as f:
        for i in rows:
            f.write(json.dumps(i, ensure_ascii=False, separators=(",", ":")) + "\n")
    with gzip.open(OUT / "coverage.jsonl.gz", "wt") as f:
        for c in sorted(cover.values(), key=lambda c: c["generated"]):
            f.write(json.dumps(c, separators=(",", ":")) + "\n")
    print(f"{len(cover)} snapshots ({logged} in GitHub's log), {len(rows)} items, first {min(cover)} .. last {max(cover)}")


if __name__ == "__main__":
    main()
