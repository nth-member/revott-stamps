#!/usr/bin/env python3
"""Standing requests: stamp each pair once its window has closed and settled, and keep the record.

    python3 stage/standing.py

requests.json lists the standing requests, as {id, title, request}; a request is what the page sends
(stage/stamp.py). After each refresh, every TNLDY of a request whose window ended at least SETTLE
before the archive's as-of, and began after the archive's first reading, is stamped -- once. The
record is appended to docs/stamps/<id>.json with the as-of it was made at, and is not rewritten:
items that arrive later belong to a later reading, not to this record. docs/stamps/index.json lists
the requests for the page, with each one's latest record and its next window still to close.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nsukka_yg_clock as clock  # noqa: E402
from stamp import canonical, data, dec, fmt, span_of, stamp_z, xs_of, ys_of, zmap  # noqa: E402

ROOT = HERE.parent
OUT = ROOT / "docs" / "stamps"
SETTLE = 24 * 3600 * 1000           # a day after a window ends, its late items have mostly arrived


def nsukka(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, clock.WAT).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    requests = json.loads((ROOT / "requests.json").read_text())
    idx = data("index.json")
    as_of, first = idx["as_of"], idx["first_reading"]
    OUT.mkdir(parents=True, exist_ok=True)
    listing, made = [], 0
    for sr in requests:
        req = sr["request"]
        path = OUT / f"{sr['id']}.json"
        book = json.loads(path.read_text()) if path.exists() else {"id": sr["id"], "title": sr["title"], "request": req, "records": []}
        if book["request"] != req:
            print(f"standing: {sr['id']}: the request changed; its records are kept, new ones follow the new request")
            book["request"] = req
        done = {r["z"] for r in book["records"]}
        eps, domains = dec(req["eps"]), set(req["domains"])
        ztp, unit = zmap(req)
        pairs = {}
        for y in ys_of(req["y"]):
            for x in xs_of(req["x"]):
                pairs.setdefault(ztp + unit * (y + x), []).append([fmt(y, 6), fmt(x, 6)])
        nxt = None
        for z in sorted(pairs):
            key = fmt(z, 6)
            a, b = span_of(z - unit * eps, z + unit * eps)
            if b + SETTLE > as_of:
                if b >= as_of and (nxt is None or b < nxt[1]) and a > first:
                    nxt = (key, b)
                continue
            if a < first or key in done:
                continue
            s = stamp_z(z, eps, req.get("clock", "reconciled"), domains, unit)
            rec = {"z": key, "pairs": pairs[z], "as_of": as_of, **{k: s[k] for k in ("instants", "window", "items", "coverage")}}
            rec["id"] = hashlib.sha256(canonical(rec).encode()).hexdigest()
            book["records"].append(rec)
            made += 1
        book["records"].sort(key=lambda r: F(r["z"]))
        path.write_text(json.dumps(book, ensure_ascii=False, separators=(",", ":")))
        last = book["records"][-1] if book["records"] else None
        listing.append({"id": sr["id"], "title": sr["title"], "request": req, "records": len(book["records"]),
                        "latest": f"{nsukka(last['instants'][0]) if last['instants'] else 'passed over'} · TNLDY {last['z']} · "
                                  f"{len(last['items'])} items" if last else None,
                        "next": f"window closes {nsukka(nxt[1])} Nsukka · TNLDY {nxt[0]}" if nxt else None})
    (OUT / "index.json").write_text(json.dumps(listing, ensure_ascii=False, separators=(",", ":")))
    print(f"standing: {len(requests)} requests, {made} new records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
