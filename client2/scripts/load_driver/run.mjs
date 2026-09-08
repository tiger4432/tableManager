// ═══════════════════════════════════════════════════════════════════════════════
// C-41 — ten users at once, against the three routes the screens actually use.
//
//   node client2/scripts/load_driver/run.mjs [lanes.json] [--rounds N]
//
// 🔴 THIS FILE DOES I/O AND PRINTS. Every judgement is in `plan.mjs` so the harness can score
//    it without a server; a decision made here would be a decision nobody ever measures.
// 🔴 NO TABLE, MAP OR SEED NAME APPEARS HERE. They are in the lane declaration.
// ⚠️ WHAT THIS CANNOT SAY: the ledger's atom count. There is no unauthenticated route that
//    reports it (`/api/ledger/{subgraph,key-values,gaps,declaration}` is the whole public
//    surface, and `/admin/ledger/sources` is token-gated), so the axis prints 「못 셈」 rather
//    than a zero. An unmeasured axis is not a met one and is not an empty one.
// ═══════════════════════════════════════════════════════════════════════════════
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import {
  laneRequests, cacheWarnings, resultRow, specHeader, meetsSpec, maxOverlap, gridOf,
} from './plan.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const roundsFlag = args.indexOf('--rounds');
// The flag's VALUE is not a path. Without this the first `node run.mjs --rounds 3` tried to
// open a declaration called `3`.
const positional = args.filter((a, i) => !a.startsWith('--') && i !== roundsFlag + 1);
const declPath = resolve(positional[0] || join(HERE, 'lanes.json'));
const decl = JSON.parse(readFileSync(declPath, 'utf8'));
const rounds = roundsFlag >= 0 ? Number(args[roundsFlag + 1]) : (decl.rounds || 5);
const base = decl.api_base;

const calls = [];                                  // every call, with its interval
const grids = new Set();                           // what the loaded maps say their grid is
const t0 = performance.now();

/** One request. It NEVER throws: a connection refused is a status 0 and a row of the table. */
async function once(laneId, route, path) {
  const start = performance.now();
  let status = 0, truncated = null;
  try {
    const res = await fetch(base + path);
    status = res.status;
    const body = await res.json().catch(() => null);
    // The walk says whether it was cut, and only the walk does. A route that carries no
    // budget leaves this null, which reads as 「말 안 함」 rather than 「안 잘림」.
    const grid = gridOf(body);
    if (grid) grids.add(grid);
    if (body && body.truncated !== undefined) {
      const t = body.truncated;
      truncated = typeof t === 'boolean' ? t
        : (t && typeof t === 'object'
          ? Object.values(t).some((axis) => axis && axis.cut === true) : null);
    }
  } catch {
    status = 0;
  }
  const end = performance.now();
  calls.push({ lane: laneId, route, status, truncated, ms: end - start, start, end });
}

/** One lane: its five requests, `rounds` times, in order — one user is one browser. */
async function lane(spec) {
  const requests = laneRequests({ ...spec, map: spec.map && { ...spec.map, metadata_table: decl.metadata_table } });
  for (let round = 0; round < rounds; round += 1) {
    for (const req of requests) await once(spec.id, req.route, req.path);
  }
}

// 🔴 THE TEN START TOGETHER. `Promise.all` over the lanes, `await` only INSIDE a lane —
//    awaiting the lanes one at a time is the accident this driver exists to avoid, and the
//    overlap printed below is what proves it did not happen.
const warnings = cacheWarnings(decl.lanes);
await Promise.all(decl.lanes.map(lane));
const wall = performance.now() - t0;

// ══ the table ═══════════════════════════════════════════════════════════════════════════
const observed = {
  users: decl.lanes.length,
  // 🔴 MEASURED, NOT DECLARED. Ten lanes that ran one after another are ten users on paper
  //    and one user in fact.
  concurrent: maxOverlap(calls),
  // 🔴 READ OFF THE METADATA ROWS THE LANES LOADED. Several lanes, several maps: they are
  //    all reported, and the axis is met only when every one of them is the declared shape.
  //    Collapsing them to the first would let one 20x20 map vouch for nine that are not.
  map_grid: grids.size ? [...grids].sort().join('/') : null,
  chain_rows_per_transaction: null,
  atoms: null,
};
const header = specHeader(decl.spec, observed, decl.given);

console.log('# C-41 ten-user driver');
console.log(`# declaration: ${declPath}`);
console.log(`# rounds/lane: ${rounds} · lanes: ${decl.lanes.length} · calls: ${calls.length}`
  + ` · wall: ${wall.toFixed(0)} ms`);
console.log(`# max concurrent in flight: ${observed.concurrent}`
  + (observed.concurrent < decl.lanes.length ? '  <- NOT ten at once' : ''));
console.log('#');
console.log('# spec coverage of THIS box — an unmet axis makes every number below a 박스 수:');
for (const row of header) {
  console.log(`#   ${String(row.axis).padEnd(28)} want ${String(row.want).padEnd(10)}`
    + ` got ${String(row.got === null ? '—' : row.got).padEnd(10)}`
    + ` ${String(row.verdict).padEnd(6)} ${row.source || ''}`);
}
console.log(`# VERDICT: ${meetsSpec(header) ? '운영 모양 박스' : '규격 미달 박스에서 — 이 표의 수는 «박스 수»'}`);
console.log('#');
if (warnings.length) {
  console.log('# CACHE WARNING — lanes sharing material do not measure ten users:');
  for (const w of warnings) console.log(`#   ${w}`);
  console.log('#');
} else {
  console.log('# cache: every lane on its own table, map and seed');
  console.log('#');
}

const routes = [...new Set(calls.map((c) => c.route))];
const rows = [];
for (const laneSpec of decl.lanes) {
  for (const route of routes) {
    const mine = calls.filter((c) => c.lane === laneSpec.id && c.route === route);
    if (mine.length) rows.push(resultRow(laneSpec.id, route, mine));
  }
}
const col = (v, w) => String(v === null ? '—' : v).padEnd(w);
console.log(`${col('lane', 6)}${col('route', 16)}${col('p50 ms', 9)}${col('p95 ms', 9)}`
  + `${col('ok/n', 8)}${col('status', 10)}${col('truncated', 10)}`);
for (const r of rows) {
  console.log(`${col(r.lane, 6)}${col(r.route, 16)}`
    + `${col(r.p50 === null ? null : r.p50.toFixed(1), 9)}`
    + `${col(r.p95 === null ? null : r.p95.toFixed(1), 9)}`
    + `${col(`${r.ok}/${r.n}`, 8)}${col(r.status, 10)}${col(r.truncated, 10)}`);
}

// 🔴 A NON-2xx ANYWHERE IS SAID AGAIN AT THE BOTTOM, because a reader scanning a forty-row
//    table for one 500 is a reader who will miss it.
const bad = rows.filter((r) => r.ok < r.n);
if (bad.length) {
  console.log('\n# calls that did not answer 2xx (status 0 = no connection):');
  for (const r of bad) console.log(`#   ${r.lane} ${r.route} — ${r.ok}/${r.n} ok, status ${r.status}`);
}
