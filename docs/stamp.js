/* REVOTT stamps, in the browser: the same computation as stage/stamp.py, exactly (tests/fidelity.mjs).

   A pair (Y, X) reads TNLDY Z = Ztp + Uy·Y + Ux·X, REVOTT's Ztp = 14160 and Uy = Ux = 100 days unless the request
   sets "ztp", "unit_y" and "unit_x" (days: a decimal or a ratio, as 17640/48.3; an older "unit" sets both). The
   variac ε, in X units, is a window of ±Ux·ε TNLDY about it; an item is stamped onto the pair when its own TNLDY -- its instant on the chosen clock, read on
   the Nsukka/Yg clock (nsukka-yg-clock.js) -- lies in the window: |Z(item) − Z(pair)| ≤ Ux·ε. All
   arithmetic is exact (BigInt fractions), so the browser's record, and its SHA-256, are the reference's.

   Stamp.create(load) -> { run(request) }, where load(name) returns a Promise of docs/data/<name>.
   Loads as a plain script (window.Stamp) or through require(). */
(function (root) {
  "use strict";
  const Y = root.NsukkaYg || (typeof require === "function" ? require("./nsukka-yg-clock.js") : null);
  const CLOCKS = { reconciled: 0, page: 7, feed: 6, seen: 5 };
  const MARGIN = 3n, DAYS_SLACK = 1e-6;
  const DEN = BigInt(Y.YG_DEN * Y.DAY_MS);                          // zOf(ms).num / DEN is exact

  /* fractions: [n, d] with d > 0 */
  const dec = v => Y.frac(String(v));
  const add = ([a, b], [c, d]) => [a * d + c * b, b * d];
  const sub = ([a, b], [c, d]) => [a * d - c * b, b * d];
  const mul = ([a, b], [c, d]) => [a * c, b * d];
  const cmp = ([a, b], [c, d]) => { const x = a * d - c * b; return x < 0n ? -1 : x > 0n ? 1 : 0; };
  const int = n => [BigInt(n), 1n];
  const floorDiv = (n, d) => { const q = n / d; return (n % d !== 0n && (n < 0n) !== (d < 0n)) ? q - 1n : q; };
  const pow10 = k => 10n ** BigInt(k);

  /* A unit in days: a decimal, or a ratio of two, as 17640/48.3 (stage/stamp.py unit_of). */
  function unitOf(v) {
    const s = String(v).trim(), parts = s.split("/");
    let u = parts.length > 1 ? [dec(parts[0].trim())[0] * dec(parts[1].trim())[1], dec(parts[0].trim())[1] * dec(parts[1].trim())[0]] : dec(s);
    if (u[1] < 0n) u = [-u[0], -u[1]];
    if (u[0] <= 0n) throw new Error("the unit must be positive");
    return u;
  }

  /* An exact fraction to `places` decimals, rounded half away from zero, as stage/stamp.py fmt. */
  function fmt([n, d], places = 6) {
    const neg = n < 0n, a = neg ? -n : n, q = a * pow10(places);
    let w = q / d; if ((q % d) * 2n >= d) w += 1n;
    const s = w.toString().padStart(places + 1, "0");
    const out = places ? s.slice(0, -places) + "." + s.slice(-places) : s;
    return (neg && w !== 0n ? "-" : "") + out;
  }

  function create(load) {
    const cache = new Map();
    const get = name => { if (!cache.has(name)) cache.set(name, load(name)); return cache.get(name); };

    function ysOf(spec, keys) {
      if (spec.mode === "value") return [dec(spec.value)];
      if (spec.mode === "range") {
        const lo = dec(spec.from), hi = dec(spec.to), st = dec(spec.step);
        const [qn, qd] = sub(hi, lo), n = (qn * st[1]) / (qd * st[0]);   // int((hi - lo) / step), both ≥ 0
        const out = [];
        for (let k = 0n; k <= n; k++) out.push(add(lo, mul(int(k), st)));
        return out;
      }
      return keys.map(k => dec(k[0]));
    }
    const LAYERS = { seals: "S", trumpets: "T", vials: "V", horns: "H" };
    function xsOf(spec, keys) {
      if (spec.mode === "key") return [dec(spec.x)];
      if (spec.mode === "range") {
        const lo = dec(spec.from), hi = dec(spec.to);
        return keys.map(k => dec(k[0])).filter(x => cmp(lo, x) <= 0 && cmp(x, hi) <= 0);
      }
      if (spec.mode === "layer") {
        const want = LAYERS[spec.layer], hidden = spec.hidden || "both", out = [];
        for (const [x, , layers] of keys) {
          for (const a of layers) {
            const hid = a.endsWith("hidden"), core = hid ? a.slice(0, -6) : a;
            if (core && core.at(-1) === want && /^\d+$/.test(core.slice(0, -1)) && (hidden === "both" || (hidden === "yes") === hid)) {
              out.push(dec(x)); break;
            }
          }
        }
        return out;
      }
      return keys.map(k => dec(k[0]));
    }

    function edge(z, first) {
      const got = Y.instantsOfFrac(z[0], z[1]);
      if (got.length) return first ? Math.min(...got) : Math.max(...got);
      const yg = 1969 + Number(floorDiv((z[0] + 340n * z[1]) * 23n, 8400n * z[1]));
      return Y.startMs(yg + 1);
    }
    const coverage = (iv, a, b) => iv.some(([c0, c1]) => c0 <= a && b <= c1) ? "covered"
                                 : iv.some(([c0, c1]) => c0 <= b && a <= c1) ? "partly" : "null";

    /* The GDELT days a window [a, b] touches within the archive's GDELT tier (its first day until the first
       feed reading), as Nsukka dates, and that tier's coverage of the window; null if it misses the tier. */
    const DAY_MS = 86400000, WAT_MS = 3600000;
    const dayNo = t => { const n = t + WAT_MS, r = ((n % DAY_MS) + DAY_MS) % DAY_MS; return (n - r) / DAY_MS; };
    function gdeltDays(a, b, idx) {
      const t0 = idx.archive_start, t1 = idx.first_reading;
      const lo = Math.max(a, t0), hi = Math.min(b, t1 - 1);
      if (lo > hi) return null;
      const d0 = dayNo(lo), d1 = dayNo(hi), missing = new Set(idx.gdelt.missing), present = [];
      for (let d = d0; d <= d1; d++) {
        const day = new Date(d * DAY_MS).toISOString().slice(0, 10);
        if (!missing.has(day)) present.push(day);
      }
      const cov = !present.length ? "null" : present.length === d1 - d0 + 1 && t0 <= a && b < t1 ? "covered" : "partly";
      return [present, cov];
    }

    async function stampZ(z, eps, clockName, domains, unit) {
      const [idx, srcs, cov] = await Promise.all([get("index.json"), get("sources.json"), get("coverage.json")]);
      const h = mul(unit, eps), pos = CLOCKS[clockName], m = clockName === "reconciled" ? 0n : MARGIN;
      const lo = sub(z, h), hi = add(z, h), a = edge(lo, true), b = edge(hi, false);
      const status = b < idx.archive_start ? "before the archive" : a > idx.as_of ? "ahead"
                   : b > idx.as_of ? "pending" : a < idx.archive_start ? "partly before the archive" : "stamped";
      const base = { z: fmt(z, 6), instants: Y.instantsOfFrac(z[0], z[1]), window: [a, b], status };
      if (status === "before the archive" || status === "ahead") return base;
      const loF = Number(lo[0]) / Number(lo[1]) - Number(m) - DAYS_SLACK, hiF = Number(hi[0]) / Number(hi[1]) + Number(m) + DAYS_SLACK;
      const items = [];
      for (const [d, [, zmin, zmax]] of Object.entries(idx.days)) {
        if (zmax < loF || zmin > hiF) continue;
        for (const r of await get("days/" + d + ".json")) {
          if (!domains.has(srcs[r[2]][1]) || r[pos] == null) continue;
          const off = sub([BigInt(Y.zOf(r[pos]).num), DEN], z);             // Z(item) − Z(pair)
          const absOff = off[0] < 0n ? [-off[0], off[1]] : off;
          if (cmp(absOff, h) <= 0) items.push([off, r]);
        }
      }
      items.sort((p, q) => cmp(p[0], q[0]) || (p[1][4] < q[1][4] ? -1 : p[1][4] > q[1][4] ? 1 : 0));
      const chosen = Object.keys(srcs).filter(s => domains.has(srcs[s][1])).sort();
      const st = Object.fromEntries(chosen.map(s => [s, coverage(cov[s] || [], a, b)]));
      base.items = items.map(([off, r]) => [fmt(mul(off, int(86400)), 3), r[pos], r[1], r[2], r[3], r[4], r[8]]);
      base.coverage = Object.fromEntries(["covered", "partly", "null"].map(k => [k, chosen.filter(s => st[s] === k)]));
      const g = gdeltDays(a, b, idx);
      if (g) { base.gdelt = g[0]; base.coverage[g[1]].push("gdelt"); }    // the GDELT tier, at day precision
      return base;
    }

    /* A request -> its record: {request, as_of, pairs: [[y, x, z]], stamps: {z: stamp}, id}. */
    async function run(request, onProgress) {
      const [idx, keys] = await Promise.all([get("index.json"), get("keys.json")]);
      const eps = dec(request.eps), domains = new Set(request.domains);
      const ztp = "ztp" in request ? dec(request.ztp) : int(14160);
      const unit = k => { const v = k in request ? request[k] : request.unit; return v === undefined ? int(100) : unitOf(v); };
      const uy = unit("unit_y"), ux = unit("unit_x"), pairs = [];
      for (const y of ysOf(request.y, keys)) for (const x of xsOf(request.x, keys)) pairs.push([y, x, add(ztp, add(mul(uy, y), mul(ux, x)))]);
      const zs = new Map();                                 // one stamp per TNLDY to 6 decimals, the first of any tie
      for (const z of pairs.map(p => p[2]).sort(cmp)) { const k = fmt(z, 6); if (!zs.has(k)) zs.set(k, z); }
      const order = [...zs.values()], stamps = {};
      let n = 0;
      for (const z of order) {
        stamps[fmt(z, 6)] = await stampZ(z, eps, request.clock || "reconciled", domains, ux);
        if (onProgress && ++n % 500 === 0) await onProgress(n, order.length);
      }
      const rec = { request, as_of: idx.as_of, pairs: pairs.map(([y, x, z]) => [fmt(y, 6), fmt(x, 6), fmt(z, 6)]), stamps };
      rec.id = await sha256(canonical(rec));
      return rec;
    }
    return { run, fmt, dec, unitOf };
  }

  /* JSON as Python's json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True) writes it. */
  function canonical(v) {
    if (v === null || typeof v !== "object") return JSON.stringify(v);
    if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
    return "{" + Object.keys(v).sort().map(k => JSON.stringify(k) + ":" + canonical(v[k])).join(",") + "}";
  }
  async function sha256(text) {
    const buf = await root.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
  }

  const api = { create, canonical, sha256 };
  root.Stamp = api;
  if (typeof module === "object" && module && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
