# REVOTT stamps

**Feed items stamped onto a (Y, X) of REVOTT.** Served at https://nth-member.github.io/revott-stamps/.

A pair reads one TNLDY:

    Z = 14160 + 100·(Y + X)

and the variac ε, in X units, is a window of ±100·ε TNLDY about it. An item of the knowledge-server feeds is
stamped onto the pair when its own TNLDY — its instant on the chosen clock, read from Nsukka on the Yg clock —
lies in the window:

    |Z(item) − Z(pair)| ≤ 100·ε

0.01 X is one day; 0.0001 X, the last digit of a key, is 14.4 minutes. The variac runs from one second to five
days. Y is a value, a range with a step, or the 400 keys; X is one key, a range of keys, a layer (seals,
trumpets, vials, horns; hidden, revealed or both) or all 400 keys. Every pair is stamped, once per distinct Z,
since only Y + X sets the TNLDY; pairs on one level line share their items and each remains its own reading.
A stamp records what fell in the window, and nothing more.

## The clock

TNLDY is read from Nsukka (WAT, UTC+01:00) on the MDQNM engine's own year, Yg = 17640/48.3 days, laid on
Nsukka's calendar from 1 December 00:00 and recalibrated at every Yg year:

    TNLDY(t) = (yG − 1969)·Yg − 340 + (t − 1 December of yG − 1, 00:00 Nsukka) / day

`docs/nsukka-yg-clock.js` and `stage/nsukka_yg_clock.py` are the clock, the same files as on the other sites.
Because the stamp is compared in TNLDY, a window that meets a recalibration needs no special case: TNLDY
passed over holds no item, and TNLDY met twice holds the items of both instants.

## Each item's instant

An item has up to three clocks: the time its article page states (its schema.org `datePublished`, the
`article:published_time` meta tag, or a `<time>` element), the time its feed states, and the moment it was
first seen here, which bounds both from above. The reconciled clock takes, in order:

| | |
|---|---|
| `p` | the page's stated time, given with its zone and not after the item was first seen |
| `f` | the feed's stated time, not after the item was first seen |
| `d` | the feed's time, from a source whose feed gives only the day (most items at 00:00 or 12:00:00) |
| `s` | the moment the item was first seen, when no stated time stands |

When the page's and the feed's times differ by a whole number of hours, one of them is local time written as
UTC; for a publisher east of UTC, where nearly every source here is, that one reads late, and the earlier is
taken (Anadolu's pages read 3 hours late, The Diplomat's 9, for example). A page time with no zone that
disagrees with the feed's otherwise yields to it. The page can also stamp on one clock alone: the page's, the feed's or first seen.

## NULL is never zero

The feeds are read every 15 minutes while the reading computer runs. A source counts as **covered** for a
window only when a reading of it reached back across the whole window; **partly** when one reached into it;
otherwise **NULL**: nothing from it is not a zero. Every stamp lists its sources in these three groups.
Before the archive's first reading (2026-09-28 05:32 Nsukka) there is no archive; a window not yet closed is
**pending**, and one entirely ahead is **ahead**.

## Standing requests

`requests.json` lists standing requests: `{id, title, request}`, a request being exactly what the page sends.
After each refresh, every pair whose window ended a day before the archive's as-of is stamped, once, and the
record is appended to `docs/stamps/<id>.json` with the as-of it was made at. Records are not rewritten; items
arriving later belong to a later reading.

## How it is kept

| | |
|---|---|
| `stage/history.py` | keeps every JOMO SFO-WAM feed snapshot, which otherwise age out of that repository's reflog |
| `stage/pagetime.py` | reads each article page once for the time it states: this project's user agent, robots.txt obeyed, one request per site every two seconds, a site that refuses left alone; Google News links lead to Google and are not read |
| `stage/archive.py` | one instant per item, filed on Nsukka's days in `docs/data/days/`, with the index, the sources, their coverage and REVOTT's 400 keys |
| `stage/standing.py` | the standing requests' records |
| `stage/stamp.py` | the stamp, exactly: the reference for `docs/stamp.js` |
| `stage/refresh.sh [--push]` | all of the above; commits only `docs/data` and `docs/stamps`, one rolling commit per Nsukka day |

On the reading computer, five minutes after each feed refresh:

    5-59/15 * * * * $HOME/revott-stamps/stage/cron.sh

Local paths are read from the untracked `.paths.json` (`history`, `jomo`, `revott`). The public archive holds
each item's headline, link, source and times — no summaries.

## Fidelity

`tests/fidelity.mjs` runs ten requests through the browser's `docs/stamp.js` and the reference
`stage/stamp.py` — single pairs on every clock, a one-second window, a pair whose TNLDY is passed over, the
40,400 pairs of Y 82.30 … 83.30 by 0.01 against all 400 keys, and the 400 keys against the trumpets — and
compares the records byte for byte, SHA-256 included: 10/10 identical.

    node tests/fidelity.mjs

## The nth-member sites

| site | repository | what it is |
|---|---|---|
| https://nth-member.github.io/revott/ | nth-member/revott | REVOTT atop GDELT: the field at every node of an instance |
| https://nth-member.github.io/gdelt/ | nth-member/gdelt | what GDELT was reading on a given day |
| https://nth-member.github.io/member/ | nth-member/member | the nth member: REVOTT's numerator, its introspection and its journal |
| https://nth-member.github.io/gematria/ | nth-member/gematria | H-Gematria/ASCII: the two name-value programs in the browser |
| https://nth-member.github.io/alien-corridor/ | nth-member/alien-corridor | the Alien Corridor Support System (MDQNM engine) in the browser |
| https://nth-member.github.io/gigaspeak/ | nth-member/gigaspeak | Gigaspeak: ASCII carried in colour, the speaker, the URL builder and the Communicator |
| https://nth-member.github.io/tsots_value_equation/ | nth-member/tsots_value_equation | the TSOTS value equation: a synthetic simulation of the Shula, run in the browser |
| https://nth-member.github.io/ipproto/ | nth-member/ipproto | IPPROTO: the 256 IP protocol numbers in 13 categories, a capture reader and a packet bridge |
| https://nth-member.github.io/revott-stamps/ | nth-member/revott-stamps | REVOTT stamps: feed items stamped onto a (Y, X) within a variable window |
