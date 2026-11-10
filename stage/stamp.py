#!/usr/bin/env python3
"""Stamps, exactly: the reference that docs/stamp.js must reproduce (tests/fidelity.mjs).

A pair (Y, X) reads TNLDY Z = Ztp + Uy·Y + Ux·X: REVOTT's turning point Ztp = 14160 and units Uy = Ux = 100
days unless the request sets others ("ztp", a decimal; "unit_y" and "unit_x", in days, each a decimal or a
ratio such as 17640/48.3; an older "unit" sets both). The variac ε, in X units, is a window of ±Ux·ε TNLDY
about it. An item is stamped onto the pair when its own TNLDY -- its instant on the chosen clock,
read on the Nsukka/Yg clock -- lies in that window:

    |Z(item) − Z(pair)| ≤ Ux·ε

Everything is compared in TNLDY, so a window that meets a Yg recalibration is handled by the clock
itself: TNLDY passed over holds no item, TNLDY met twice holds the items of both instants.

A request names Y (a value, a range with a step, or REVOTT's keys) and X (keys: one, a range, a layer,
or all of them); every pair is stamped, once per distinct Z. Y, X and the keys are never altered: Ztp and
the units only place them in time.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from decimal import Decimal
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import nsukka_yg_clock as clock  # noqa: E402

DATA = HERE.parent / "docs" / "data"
CLOCKS = {"reconciled": 0, "page": 7, "feed": 6, "seen": 5}
MARGIN = 3          # days of TNLDY around a window searched when the clock is not the reconciled one
SLACK = 1e-6        # the day index rounds its TNLDY ranges to 6 decimals


def dec(v) -> F:
    return F(Decimal(str(v)))


ZTP, UNIT = F(14160), F(100)          # REVOTT's turning point and its unit of Y and of X, in days


def unit_of(v) -> F:
    """A unit in days: a decimal, or a ratio of two, as 17640/48.3."""
    s = str(v).strip()
    u = dec(s.split("/")[0].strip()) / dec(s.split("/")[1].strip()) if "/" in s else dec(s)
    if u <= 0:
        raise ValueError("the unit must be positive")
    return u


def zmap(request: dict) -> tuple[F, F, F]:
    """(Ztp, Uy, Ux) of a request: REVOTT's 14160, 100 days and 100 days unless it sets its own."""
    def unit(k):
        v = request.get(k, request.get("unit"))
        return UNIT if v is None else unit_of(v)
    return (dec(request["ztp"]) if "ztp" in request else ZTP), unit("unit_y"), unit("unit_x")


def fmt(v: F, places: int = 6) -> str:
    """An exact rational to `places` decimals, rounded half away from zero (docs/stamp.js does the same)."""
    q = abs(v) * 10 ** places
    n = int(q) + (1 if q - int(q) >= F(1, 2) else 0)
    sign = "-" if v < 0 and n else ""
    whole, frac = divmod(n, 10 ** places)
    return f"{sign}{whole}.{frac:0{places}d}" if places else f"{sign}{whole}"


def ms_round(t: F) -> int:
    """Epoch ms, rounded half up, as the browser's clock rounds."""
    return int((t + F(1, 2)) // 1)


@lru_cache(None)
def data(name: str):
    return json.loads((DATA / name).read_text())


@lru_cache(None)
def day(name: str):
    return json.loads((DATA / "days" / f"{name}.json").read_text())


def keys():
    return data("keys.json")


def ys_of(spec: dict) -> list[F]:
    if spec["mode"] == "value":
        return [dec(spec["value"])]
    if spec["mode"] == "range":
        lo, hi, step = dec(spec["from"]), dec(spec["to"]), dec(spec["step"])
        n = int((hi - lo) / step)
        return [lo + k * step for k in range(n + 1)]
    return [dec(k[0]) for k in keys()]                       # "keys"


LAYERS = {"seals": "S", "trumpets": "T", "vials": "V", "horns": "H"}


def xs_of(spec: dict) -> list[F]:
    ks = keys()
    if spec["mode"] == "key":
        return [dec(spec["x"])]
    if spec["mode"] == "range":
        lo, hi = dec(spec["from"]), dec(spec["to"])
        return [dec(k[0]) for k in ks if lo <= dec(k[0]) <= hi]
    if spec["mode"] == "layer":
        want = LAYERS[spec["layer"]]
        hidden = spec.get("hidden", "both")
        out = []
        for x, _r, layers in ks:
            for a in layers:
                core, hid = (a[:-6], True) if a.endswith("hidden") else (a, False)
                if core and core[-1] == want and core[:-1].isdigit() and (hidden == "both" or (hidden == "yes") == hid):
                    out.append(dec(x))
                    break
        return out
    return [dec(k[0]) for k in ks]                           # "all"


def span_of(z_lo: F, z_hi: F) -> tuple[int, int]:
    """The stretch of real time across which the clock reads within [z_lo, z_hi], as [first, last] ms;
    a bound passed over at a recalibration is reached at the recalibration itself."""
    def edge(z, first):
        got = clock.instants(z)
        if got:
            return ms_round(min(got) if first else max(got))
        yg = 1969 + int((z + 340) // clock.YG)
        return clock.start_ms(yg + 1)
    return edge(z_lo, True), edge(z_hi, False)


DAY_MS, WAT_MS = 86_400_000, 3_600_000


def gdelt_days(a: int, b: int, idx: dict):
    """The GDELT days a window [a, b] touches within the archive's GDELT tier (its first day until the first
    feed reading), as Nsukka dates, and that tier's coverage of the window; None if the window misses the tier."""
    t0, t1 = idx["archive_start"], idx["first_reading"]
    lo, hi = max(a, t0), min(b, t1 - 1)
    if lo > hi:
        return None
    d0, d1 = (lo + WAT_MS) // DAY_MS, (hi + WAT_MS) // DAY_MS
    days = [(dt.date(1970, 1, 1) + dt.timedelta(days=d)).isoformat() for d in range(d0, d1 + 1)]
    missing = set(idx["gdelt"]["missing"])
    present = [d for d in days if d not in missing]
    cov = "null" if not present else "covered" if len(present) == len(days) and t0 <= a and b < t1 else "partly"
    return present, cov


def coverage(src: str, a: int, b: int) -> str:
    iv = data("coverage.json").get(src, [])
    if any(c0 <= a and b <= c1 for c0, c1 in iv):
        return "covered"
    if any(c0 <= b and a <= c1 for c0, c1 in iv):
        return "partly"
    return "null"


def stamp_z(z: F, eps: F, clock_name: str, domains: set[str], unit: F = UNIT) -> dict:
    """Everything stamped onto one TNLDY."""
    h = unit * eps
    idx = data("index.json")
    srcs = data("sources.json")
    pos = CLOCKS[clock_name]
    m = 0 if clock_name == "reconciled" else MARGIN
    lo, hi = z - h, z + h
    a, b = span_of(lo, hi)
    status = ("before the archive" if b < idx["archive_start"] else
              "ahead" if a > idx["as_of"] else
              "pending" if b > idx["as_of"] else
              "partly before the archive" if a < idx["archive_start"] else "stamped")
    base = {"z": fmt(z, 6), "instants": [ms_round(t) for t in clock.instants(z)], "window": [a, b], "status": status}
    if status in ("before the archive", "ahead"):
        return base
    items = []
    for d, (_n, zmin, zmax) in idx["days"].items():
        if zmax < lo - m - SLACK or zmin > hi + m + SLACK:
            continue
        for r in day(d):
            if srcs[r[2]][1] not in domains or r[pos] is None:
                continue
            zi = clock.z_of(r[pos])
            if abs(zi - z) <= h:
                items.append((zi - z, r))
    items.sort(key=lambda t: (t[0], t[1][4]))
    chosen = sorted(s for s, v in srcs.items() if v[1] in domains)
    cov = {s: coverage(s, a, b) for s in chosen}
    base["items"] = [[fmt(off * 86400, 3), r[pos], r[1], r[2], r[3], r[4], r[8]] for off, r in items]
    base["coverage"] = {k: [s for s in chosen if cov[s] == k] for k in ("covered", "partly", "null")}
    g = gdelt_days(a, b, idx)
    if g is not None:                                     # the GDELT tier: the days themselves, at day precision
        base["gdelt"] = g[0]
        base["coverage"][g[1]].append("gdelt")
    return base


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def stamp(request: dict) -> dict:
    """A request -> its stamps: {request, as_of, pairs: [[y, x, z]], stamps: {z: stamp}, id}."""
    eps = dec(request["eps"])
    domains = set(request["domains"])
    ztp, uy, ux = zmap(request)
    pairs = [(y, x, ztp + uy * y + ux * x) for y in ys_of(request["y"]) for x in xs_of(request["x"])]
    stamps = {}
    for z in sorted(set(p[2] for p in pairs)):          # one stamp per TNLDY to 6 decimals, the first of any tie
        if fmt(z, 6) not in stamps:
            stamps[fmt(z, 6)] = stamp_z(z, eps, request.get("clock", "reconciled"), domains, ux)
    rec = {"request": request, "as_of": data("index.json")["as_of"],
           "pairs": [[fmt(y, 6), fmt(x, 6), fmt(z, 6)] for y, x, z in pairs], "stamps": stamps}
    rec["id"] = hashlib.sha256(canonical(rec).encode()).hexdigest()
    return rec


if __name__ == "__main__":
    if sys.argv[1:2] == ["--json"]:                  # tests/fidelity.mjs: one request in, its record out
        print(canonical(stamp(json.loads(sys.argv[2]))))
        sys.exit(0)
    req = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "y": {"mode": "value", "value": "82.80"}, "x": {"mode": "key", "x": "-16.5721"}, "eps": "0.00005",
        "clock": "reconciled", "domains": ["geopolitical-analysis", "middle-east", "balkans", "world",
                                           "russia-eurasia", "science-technology"]}
    r = stamp(req)
    for z, s in r["stamps"].items():
        if "items" not in s:
            print(f"Z {z} · {s['status']}")
            continue
        print(f"Z {z} · {s['status']} · {len(s['items'])} items · coverage "
              f"{len(s['coverage']['covered'])} covered, {len(s['coverage']['partly'])} partly, {len(s['coverage']['null'])} NULL")
        for it in s["items"][:12]:
            print(f"  {it[0]:>9} s  {dt.datetime.fromtimestamp(it[1] / 1000, clock.WAT):%H:%M:%S}  {it[2]}  {it[3]:<22} {it[4][:70]}")
    print("id", r["id"])
