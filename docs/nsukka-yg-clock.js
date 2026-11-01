/* TNLDY read from Nsukka: the Yg year laid directly onto the Gregorian calendar, recalibrated every Yg year.

     Z(t) = (yG - 1969)·Yg - 340 + (t - S(yG)) / day

     Yg     = 17640/48.3 = 8400/23 days
     yG     the Yg year holding t: Nsukka's civil year, plus one from 1 December
     S(yG)  1 December of year yG - 1, 00:00:00 Nsukka time (WAT, UTC+01:00 since 1919, no daylight saving)

   The MDQNM engine's own reckoning (sfo10, miscellaneous_streamlines): decimal year = Z·48.3/17640 + 5849 +
   391/420 - 3880, so Z = 0 is yearday 340 of Yg 1969, and yearday(Z, yG) = Z + 340 + (1969 - yG)·Yg; its year
   starts in December. A yearday is counted in real days from S(yG) and lands on whatever Gregorian day it falls
   on, 29 February included. Each Yg year occupies the 365 or 366 civil days from one 1 December to the next, so
   the clock is recalibrated at every S(yG): after 365 days the last 5/23 day of the old year's Z is passed over
   (no instant has it); after 366 days the first 18/23 day of the new year's Z occurs twice.

   Arithmetic is exact: Z is an integer numerator over 23·86 400 000, and instants are found with BigInt.
   Loads as a plain script (window.NsukkaYg, self.NsukkaYg in a worker) or through require(). */
(function (root) {
  "use strict";
  const YG_NUM = 8400, YG_DEN = 23, DAY_MS = 86400000, WAT_MS = 3600000;
  const DEN = YG_DEN * DAY_MS;                                     // Z = num / DEN exactly

  const startMs = yg => Date.UTC(yg - 1, 11, 1) - WAT_MS;           // S(yG)
  function ygOf(ms) { const n = new Date(Math.floor(ms) + WAT_MS); return n.getUTCFullYear() + (n.getUTCMonth() === 11 ? 1 : 0); }
  const zStartNum = yg => ((yg - 1969) * YG_NUM - 340 * YG_DEN) * DAY_MS;

  /* TNLDY of the instant `ms` (epoch milliseconds): { num, z }, z = num / DEN, num an exact integer. */
  function zOf(ms) {
    const t = Math.floor(ms), yg = ygOf(t), num = zStartNum(yg) + YG_DEN * (t - startMs(yg));
    return { num, z: num / DEN };
  }
  const zNow = () => zOf(Date.now()).z;

  /* A decimal (string or number, exponent allowed) as an exact fraction [n, d] of BigInts. */
  function frac(z) {
    const s = (typeof z === "string" ? z.trim() : String(z)).toLowerCase();
    const m = /^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/.exec(s);
    if (!m) throw new Error("not a plain decimal: " + s);
    const digits = m[2] + (m[3] || ""), e = (m[4] ? +m[4] : 0) - (m[3] || "").length;
    let n = BigInt(digits) * (m[1] === "-" ? -1n : 1n), d = 1n;
    if (e >= 0) n *= 10n ** BigInt(e); else d = 10n ** BigInt(-e);
    return [n, d];
  }

  /* Every instant (epoch ms, rounded half up) at which the clock reads Z = n/d: [] in a passed-over tail,
     two in a doubled head, otherwise one. */
  function instantsOfFrac(n, d) {
    const out = [], guess = 1969 + Math.floor((Number(n) / Number(d) + 340) / (YG_NUM / YG_DEN));
    for (const yg of [guess - 1, guess, guess + 1]) {
      const s = BigInt(startMs(yg)), len = BigInt(startMs(yg + 1)) - s;
      const yd = n * BigInt(DEN) - BigInt(zStartNum(yg)) * d;          // yearday · DEN · d
      if (yd < 0n || yd * BigInt(DAY_MS) >= len * BigInt(DEN) * d) continue;
      const q = BigInt(DEN) * d;                                        // yearday in ms = yd·DAY_MS / q
      out.push(Number(s + (2n * yd * BigInt(DAY_MS) + q) / (2n * q)));
    }
    return out.sort((a, b) => a - b);
  }
  const instantsOf = z => { const [n, d] = frac(z); return instantsOfFrac(n, d); };

  /* The Yg year and yearday of an instant: { yg, yearday } (yearday in days, from S(yG)). */
  function reading(ms) { const yg = ygOf(ms); return { yg, yearday: (Math.floor(ms) - startMs(yg)) / DAY_MS, z: zOf(ms).z }; }

  /* The next recalibration after `ms`: { at, step } with step in days (+5/23 or -18/23). */
  function nextRecalibration(ms) {
    const yg = ygOf(ms), at = startMs(yg + 1), len = (at - startMs(yg)) / DAY_MS;
    return { at, step: YG_NUM / YG_DEN - len, stepText: len === 365 ? "+5/23 d" : "-18/23 d" };
  }

  const p = (v, w = 2) => String(v).padStart(w, "0");
  function fields(ms) {
    const n = new Date(Math.round(ms) + WAT_MS), y = n.getUTCFullYear();
    return { y: (y < 0 ? "-" : "") + p(Math.abs(y), 4), mo: p(n.getUTCMonth() + 1), d: p(n.getUTCDate()),
             h: p(n.getUTCHours()), mi: p(n.getUTCMinutes()), s: p(n.getUTCSeconds()), ms: p(n.getUTCMilliseconds(), 3) };
  }
  /* Nsukka wall-clock time: "YYYY-MM-DD HH:MM:SS.mmm". */
  function nsukka(ms) { const f = fields(ms); return `${f.y}-${f.mo}-${f.d} ${f.h}:${f.mi}:${f.s}.${f.ms}`; }
  /* The same as ISO 8601 with Nsukka's offset, as Joda prints a DateTime: "YYYY-MM-DDTHH:MM:SS.mmm+01:00". */
  function isoNsukka(ms) { const f = fields(ms); return `${f.y}-${f.mo}-${f.d}T${f.h}:${f.mi}:${f.s}.${f.ms}+01:00`; }
  /* Nsukka's calendar date of an instant: "YYYY-MM-DD". */
  const dateNsukka = ms => nsukka(ms).slice(0, 10);

  const api = { YG_NUM, YG_DEN, DAY_MS, WAT_MS, startMs, ygOf, zOf, zNow, frac, instantsOf, instantsOfFrac,
                reading, nextRecalibration, nsukka, isoNsukka, dateNsukka };
  root.NsukkaYg = api;
  if (typeof module === "object" && module && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
