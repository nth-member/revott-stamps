"""TNLDY read from Nsukka: the Yg year laid directly onto the Gregorian calendar, recalibrated every Yg year.

    Z(t) = (yG - 1969)·Yg - 340 + (t - S(yG)) / day

    Yg     = 17640/48.3 = 8400/23 days
    yG     the Yg year holding t: Nsukka's civil year, plus one from 1 December
    S(yG)  1 December of year yG - 1, 00:00:00 Nsukka time (WAT, UTC+01:00 since 1919, no daylight saving)

The MDQNM engine's own reckoning (sfo10, miscellaneous_streamlines): decimal year = Z·48.3/17640 + 5849 + 391/420
- 3880, so Z = 0 is yearday 340 of Yg 1969, and yearday(Z, yG) = Z + 340 + (1969 - yG)·Yg; its month table starts
the year in December. A yearday is counted in real days from S(yG) and lands on whatever Gregorian day it falls
on, 29 February included. Each Yg year occupies the 365 or 366 civil days from one 1 December to the next, so at
every S(yG) the clock is recalibrated: after 365 days the last 5/23 day of the old year's Z is passed over (no
instant has it); after 366 days the first 18/23 day of the new year's Z occurs twice.
"""
from __future__ import annotations

import datetime as dt
from fractions import Fraction

YG = Fraction(17640) / Fraction("48.3")
DAY_MS = 86_400_000
WAT = dt.timezone(dt.timedelta(hours=1), "WAT")
UNIX = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def ms_of(t: dt.datetime) -> int:
    """Epoch milliseconds of an aware datetime (sub-millisecond part truncated toward the past)."""
    d = t - UNIX
    return (d.days * 86400 + d.seconds) * 1000 + d.microseconds // 1000


def start_ms(yg: int) -> int:
    """S(yG): 1 December of yG - 1, 00:00 Nsukka, in epoch milliseconds."""
    return ms_of(dt.datetime(yg - 1, 12, 1, tzinfo=WAT))


def yg_of(ms: int) -> int:
    n = (UNIX + dt.timedelta(milliseconds=ms)).astimezone(WAT)
    return n.year + (1 if n.month == 12 else 0)


def z_start(yg: int) -> Fraction:
    return (yg - 1969) * YG - 340


def z_of(ms: int) -> Fraction:
    """TNLDY of the instant `ms` (epoch milliseconds), exactly."""
    yg = yg_of(ms)
    return z_start(yg) + Fraction(ms - start_ms(yg), DAY_MS)


def instants(z) -> list[Fraction]:
    """Every instant (epoch ms, exact) at which the clock reads Z: none in a passed-over tail, two in a doubled head."""
    z = Fraction(z)
    guess = 1969 + int((z + 340) // YG)
    out = []
    for yg in (guess - 1, guess, guess + 1):
        yd = z - z_start(yg)
        if 0 <= yd < Fraction(start_ms(yg + 1) - start_ms(yg), DAY_MS):
            out.append(start_ms(yg) + yd * DAY_MS)
    return sorted(out)


def nsukka(ms) -> str:
    """Nsukka wall-clock time of an instant, to the millisecond: 'YYYY-MM-DD HH:MM:SS.mmm'."""
    whole = int(Fraction(ms) // 1) if not isinstance(ms, int) else ms
    frac = Fraction(ms) - whole
    whole += 1 if frac >= Fraction(1, 2) else 0
    n = (UNIX + dt.timedelta(milliseconds=whole)).astimezone(WAT)
    return n.strftime("%Y-%m-%d %H:%M:%S.") + f"{n.microsecond // 1000:03d}"


def reading(ms: int) -> dict:
    yg = yg_of(ms)
    return {"nsukka": nsukka(ms), "yg": yg, "yearday": Fraction(ms - start_ms(yg), DAY_MS), "z": z_of(ms)}
