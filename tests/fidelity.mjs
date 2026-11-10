// The browser's stamps (docs/stamp.js) must equal the reference's (stage/stamp.py) byte for byte.
//   node tests/fidelity.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const ROOT = new URL("..", import.meta.url).pathname;
globalThis.NsukkaYg = require(ROOT + "docs/nsukka-yg-clock.js");
const Stamp = require(ROOT + "docs/stamp.js");
const S = Stamp.create(async name => JSON.parse(readFileSync(ROOT + "docs/data/" + name, "utf8")));
const SIX = ["geopolitical-analysis", "middle-east", "balkans", "world", "russia-eurasia", "science-technology"];
const ALL = [...new Set(Object.values(JSON.parse(readFileSync(ROOT + "docs/data/sources.json"))).map(v => v[1]))].sort();
const R = (y, x, eps, clock, domains, g) => ({ y, x, eps, clock, domains, ...g });
const cases = [
  R({ mode: "value", value: "82.80" }, { mode: "key", x: "-16.5721" }, "0.00005", "reconciled", SIX),
  R({ mode: "value", value: "82.80" }, { mode: "key", x: "-16.5721" }, "0.00005", "seen", SIX),
  R({ mode: "value", value: "82.80" }, { mode: "key", x: "-16.5721" }, "0.0005", "feed", SIX),
  R({ mode: "value", value: "82.80" }, { mode: "key", x: "-16.5721" }, "0.005", "page", ALL),
  R({ mode: "value", value: "82.80" }, { mode: "key", x: "-16.40" }, "0.0000001157", "reconciled", ALL),
  R({ mode: "value", value: "24.50" }, { mode: "range", from: "-16.6", to: "-16.0" }, "0.5", "reconciled", SIX),
  R({ mode: "value", value: "24.545" }, { mode: "key", x: "42.28" }, "0.00005", "reconciled", SIX),     // its Z is passed over
  R({ mode: "range", from: "82.30", to: "83.30", step: "0.01" }, { mode: "all" }, "0.00005", "reconciled", ["world"]),
  R({ mode: "keys" }, { mode: "layer", layer: "trumpets", hidden: "both" }, "0.01", "reconciled", ALL),
  R({ mode: "range", from: "62.00", to: "62.40", step: "0.05" }, { mode: "layer", layer: "seals", hidden: "no" }, "0.05", "seen", SIX),
  // the GDELT tier: 2013-04-01 until the first feed reading, at day precision
  R({ mode: "value", value: "24.50" }, { mode: "key", x: "0.0" }, "0.00005", "reconciled", SIX),         // two GDELT days, covered
  R({ mode: "value", value: "66.185" }, { mode: "key", x: "0.0" }, "0.005", "reconciled", ALL),          // across the first reading
  R({ mode: "value", value: "19.89" }, { mode: "key", x: "0.0" }, "0.003", "reconciled", SIX),           // days GDELT never published: NULL
  R({ mode: "value", value: "19.89" }, { mode: "key", x: "0.0" }, "0.03", "page", SIX),                  // and around them: partly
  R({ mode: "value", value: "16.90" }, { mode: "key", x: "0.0" }, "0.01", "reconciled", SIX),            // partly before the archive
  R({ mode: "value", value: "24.50" }, { mode: "all" }, "0.005", "reconciled", ALL),
  R({ mode: "keys" }, { mode: "key", x: "-16.5721" }, "0.005", "feed", SIX),
  // GLOBAL: another turning point Ztp and units Uy of Y and Ux of X, Y and X unaltered
  R({ mode: "value", value: "24.50" }, { mode: "range", from: "-7.6", to: "-7.0" }, "0.0001", "reconciled", SIX, { unit_y: "17640/48.3", unit_x: "17640/48.3" }),
  R({ mode: "range", from: "16.00", to: "17.00", step: "0.05" }, { mode: "layer", layer: "trumpets", hidden: "both" }, "0.0005", "reconciled", ALL, { unit_y: "360", unit_x: "360" }),
  R({ mode: "value", value: "82.80" }, { mode: "all" }, "0.00002", "feed", SIX, { ztp: "-5000.5", unit_y: "365.25", unit_x: "365.25" }),
  R({ mode: "value", value: "0.0" }, { mode: "key", x: "0.0" }, "0.00005", "reconciled", SIX, { ztp: "20800" }),
  R({ mode: "value", value: "82.80" }, { mode: "key", x: "-16.5721" }, "0.00005", "reconciled", SIX, { ztp: "14160.0", unit_y: "100", unit_x: "100" }),
  R({ mode: "value", value: "24.50" }, { mode: "all" }, "0.0005", "reconciled", SIX, { unit_y: "17640/48.3" }),               // Uy alone
  R({ mode: "keys" }, { mode: "key", x: "-16.5721" }, "0.00005", "page", ALL, { unit_x: "360" }),                             // Ux alone
  R({ mode: "range", from: "82.00", to: "83.00", step: "0.01" }, { mode: "layer", layer: "seals", hidden: "both" }, "0.0001", "reconciled", SIX,
    { ztp: "-1000", unit_y: "360", unit_x: "8400/23" }),                                                                         // yJ for Y, yG for X
  R({ mode: "value", value: "24.50" }, { mode: "range", from: "-7.6", to: "-7.0" }, "0.0001", "reconciled", SIX, { unit: "17640/48.3" }), // an older "unit": both
  R({ mode: "range", from: "23.05", to: "23.15", step: "0.001" }, { mode: "key", x: "-16.5721" }, "0.0002", "reconciled", SIX, { unit_y: "360" }), // feed era, Uy ≠ Ux
];
let bad = 0;
for (const [k, req] of cases.entries()) {
  const js = Stamp.canonical(await S.run(req));
  const py = execFileSync("python3", [ROOT + "stage/stamp.py", "--json", JSON.stringify(req)], { maxBuffer: 1 << 30 }).toString().trim();
  const rec = JSON.parse(js), n = Object.keys(rec.stamps).length, items = Object.values(rec.stamps).reduce((s, v) => s + (v.items ? v.items.length : 0), 0);
  const same = js === py;
  if (!same) { bad++; writeFileSync(`/tmp/fid-${k}-js.json`, js); writeFileSync(`/tmp/fid-${k}-py.json`, py); }
  console.log(`${same ? "same" : "DIFF"}  case ${k}: ${rec.pairs.length} pairs, ${n} TNLDY, ${items} items stamped, id ${rec.id.slice(0, 12)}`);
}
console.log(bad ? `FAIL ${bad} of ${cases.length}` : `${cases.length}/${cases.length} identical`);
process.exit(bad ? 1 : 0);
