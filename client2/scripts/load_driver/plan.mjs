// ═══════════════════════════════════════════════════════════════════════════════
// C-41 — the ten-user driver's DECISIONS, in a module the harness imports.
//
// 🔴 THE RUNNER DOES I/O AND NOTHING ELSE. Every judgement this driver makes — which requests
//    a lane sends, whether two lanes would answer each other out of a cache, what a percentile
//    is, whether ten lanes actually overlapped, and how far this box meets the spec — lives
//    here, because a judgement inside the runner would need a live server to score and would
//    therefore never be scored at all.
//
// 🔴 NO TABLE, MAP OR SEED NAME IS WRITTEN IN THIS FILE OR IN THE RUNNER. They come from the
//    lane declaration, which is the whole point: a name in code is a driver that measures the
//    box it was written on and nothing else.
// ═══════════════════════════════════════════════════════════════════════════════

/** The spec the owner gave, as the axes a box is measured AGAINST (2026-09-08). */
export const SPEC_AXES = Object.freeze(['chain_rows_per_transaction', 'map_grid', 'users', 'atoms']);

/**
 * The requests one lane sends, in the shapes the SCREENS send them.
 *
 * 🔴 Every query string here is the screen's own, copied from the call site rather than
 *    invented: a driver that sent a tidier request would measure a route nobody uses.
 *      grid   `api.js:332` — skip/limit + the sort tail + `defer_total=true`
 *      count  `api.js:282` — the same narrowing, counted separately, which is why the screen
 *                            shows rows before it shows a total
 *      meta   `map_editor.js:5035` — limit=2 and BOTH key columns, because one map_id can
 *                            exist in two tables
 *      paint  `map_editor.js:183` — the overlay's declaration for that table
 *      walk   `rnd_board/api.js:1838` — the seed id, `follow` repeated, nothing invented
 */
export function laneRequests(lane) {
  const grid = lane && lane.grid;
  const map = lane && lane.map;
  const walk = lane && lane.walk;
  const out = [];
  if (grid && grid.table) {
    const sort = `&order_by=${encodeURIComponent(grid.order_by)}&order_desc=${!!grid.order_desc}`;
    out.push({ route: 'grid.data',
      path: `/tables/${encodeURIComponent(grid.table)}/data`
        + `?skip=${grid.skip || 0}&limit=${grid.limit}${sort}&defer_total=true` });
    out.push({ route: 'grid.count',
      path: `/tables/${encodeURIComponent(grid.table)}/data/count` });
  }
  if (map && map.table && map.map_id) {
    const filters = JSON.stringify({
      target_table: { filterType: 'text', type: 'equals', filter: String(map.table) },
      map_id: { filterType: 'text', type: 'equals', filter: String(map.map_id) },
    });
    out.push({ route: 'map.meta',
      path: `/tables/${encodeURIComponent(map.metadata_table)}/data?limit=2&defer_total=true`
        + `&filters=${encodeURIComponent(filters)}` });
    out.push({ route: 'map.overlay',
      path: `/api/maps/paint-rules?table=${encodeURIComponent(map.table)}` });
  }
  if (walk && walk.type) {
    const query = new URLSearchParams();
    query.set('id', seedId(walk.type, walk.keys));
    (walk.follow || []).forEach((p) => query.append('follow', String(p).split('@')[0]));
    if (walk.hops) query.set('hops', String(walk.hops));
    if (walk.node_limit) query.set('node_limit', String(walk.node_limit));
    out.push({ route: 'walk.subgraph', path: `/api/ledger/subgraph?${query}` });
  }
  return out;
}

/**
 * The walk's seed id — base64URL, exactly as `rnd_board/api.js:entitySeedId` builds it.
 *
 * ⚠️ base64URL IS THE SERVER'S REQUIREMENT, not a preference: a key containing `+` answers 422
 *    under standard base64 and 200 under this one, and today's seeds happen not to contain one,
 *    so the difference is invisible until it is not.
 */
export function seedId(type, keys) {
  const bare = String(type || '').split('@')[0];
  const json = JSON.stringify([bare, keys || {}]);
  const b64 = Buffer.from(json, 'utf8').toString('base64');
  return 'ledger-entity:v1:' + b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * 「두 열이 같은 것을 들면 캐시가 답한다」 — said, never silently tolerated.
 *
 * 🔴 THIS IS THE ONE THAT MAKES THE WHOLE RUN MEANINGLESS WHEN IT IS WRONG. Ten lanes reading
 *    the same table measure one cold query and nine warm ones, and the table of numbers looks
 *    BETTER for it — a load driver whose defect flatters the result is a driver nobody
 *    double-checks. So it is a value the harness scores, not a note somebody remembers.
 *
 * @returns {string[]} one line per collision, empty when every lane is on its own material
 */
export function cacheWarnings(lanes) {
  const axes = [
    ['grid', (l) => l.grid && l.grid.table],
    ['map', (l) => l.map && `${l.map.table}/${l.map.map_id}`],
    ['walk', (l) => l.walk && JSON.stringify([l.walk.type, l.walk.keys])],
  ];
  const out = [];
  for (const [axis, of] of axes) {
    const seen = new Map();
    for (const lane of lanes || []) {
      const value = of(lane);
      if (value == null) continue;
      const before = seen.get(value);
      if (before) out.push(`${axis}: ${before} and ${lane.id} share ${value} — the second is a cache hit`);
      else seen.set(value, lane.id);
    }
  }
  return out;
}

/** The p-th percentile of `samples`, nearest-rank. Empty in, null out — never 0. */
export function percentile(samples, p) {
  const sorted = (samples || []).filter((n) => Number.isFinite(n)).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const rank = Math.max(1, Math.ceil((p / 100) * sorted.length));
  return sorted[Math.min(rank, sorted.length) - 1];
}

/**
 * One row of the table: what happened, INCLUDING when nothing did.
 *
 * 🔴 A FAILED CALL IS A ROW, NOT AN ABSENCE. A driver that drops what did not answer reports
 *    a fast run made of the requests that worked, and the one route that 500s is the one the
 *    reader most needs to see. `0` is this file's spelling for 「연결 자체가 안 됨」.
 * ⚠️ `truncated` is the walk's own answer, and `null` means it did not say — a route that
 *    carries no budget is not a route that was not cut.
 */
export function resultRow(lane, route, calls) {
  const okMs = calls.filter((c) => c.status >= 200 && c.status < 300).map((c) => c.ms);
  const statuses = [...new Set(calls.map((c) => c.status))].sort((a, b) => a - b);
  const cut = calls.map((c) => c.truncated).filter((v) => v != null);
  return {
    lane, route,
    p50: percentile(okMs, 50), p95: percentile(okMs, 95),
    n: calls.length, ok: okMs.length,
    status: statuses.join('/'),
    truncated: cut.length ? cut.some(Boolean) : null,
  };
}

/**
 * The map's grid, out of the metadata row the driver already fetched.
 *
 * 🔴 MEASURED RATHER THAN 「못 셈」. The 20x20 axis is one of the four, and the meta request is
 *    already on the wire — reporting it as unmeasured when the answer is in a response we hold
 *    would be the driver hiding a shortfall behind an absence.
 * ⚠️ `grid_metadata` is a JSON STRING inside the row, exactly as `map_editor.js:fetchGridMetaFor`
 *    reads it. Unparseable or absent returns null, which is 「말 안 함」 and not 「0x0」.
 */
export function gridOf(body) {
  const rows = body && Array.isArray(body.data) ? body.data : [];
  const raw = rows.length ? rows[0]?.data?.grid_metadata?.value : null;
  if (!raw) return null;
  let meta;
  try { meta = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { return null; }
  const cols = Number(meta && meta.grid_cols);
  const rowsN = Number(meta && meta.grid_rows);
  if (!Number.isFinite(cols) || !Number.isFinite(rowsN)) return null;
  return `${cols}x${rowsN}`;
}

/**
 * How far this box is from the shape the numbers would need to mean anything.
 *
 * 🔴 THE HEADER IS NOT DECORATION. The owner's rule is that a box below the production shape
 *    produces 「박스 수」 — numbers that say nothing about production — so the table has to
 *    carry, at its head, which axes were met. An unmet axis is named; an axis nobody could
 *    measure is named as unmeasured, which is a third state and not a zero.
 */
export function specHeader(spec, observed, given) {
  return SPEC_AXES.map((axis) => {
    const want = spec ? spec[axis] : undefined;
    const mine = observed ? observed[axis] : undefined;
    // 🔴 A MEASUREMENT BEATS A CLAIM, ALWAYS. Someone handing this driver a number for an axis
    //    it CAN measure would be overwriting an observation with an assertion — and the axis
    //    most worth overwriting is the one that fell short. So a supplied value is used only
    //    where this driver has nothing of its own.
    const handed = mine === undefined || mine === null ? (given ? given[axis] : undefined) : null;
    const got = mine === undefined || mine === null
      ? (handed && handed.value !== undefined ? handed.value : undefined) : mine;
    // 🔴 AND WHERE IT CAME FROM RIDES WITH IT. 「this driver watched it」 and 「somebody told
    //    me」 are different kinds of fact, and a header that printed them alike would let one
    //    lane's claim be quoted as a measurement.
    const source = got === undefined || got === null ? null
      : (handed && handed.value !== undefined ? String(handed.source || '받은 수') : '이 드라이버');
    if (got === undefined || got === null) return { axis, want, got: null, source: null, verdict: '못 셈' };
    const met = typeof want === 'number' && typeof got === 'number' ? got >= want : got === want;
    return { axis, want, got, source, verdict: met ? '갖춤' : '미달' };
  });
}

/** True when the run met the spec on every axis it could measure. */
export function meetsSpec(header) {
  return header.every((row) => row.verdict === '갖춤');
}

/**
 * How many calls were in flight at once, from their intervals.
 *
 * 🔴 TEN LANES RUNNING ONE AFTER ANOTHER IS A DIFFERENT EXPERIMENT, and it is the one a
 *    driver accidentally runs — an `await` in the wrong loop turns ten users into one user
 *    ten times, every number improves, and nothing says so. So the overlap is MEASURED from
 *    the timestamps rather than assumed from the code's shape.
 */
export function maxOverlap(intervals) {
  const edges = [];
  for (const it of intervals || []) {
    if (!Number.isFinite(it.start) || !Number.isFinite(it.end)) continue;
    edges.push([it.start, 1], [it.end, -1]);
  }
  // A close at the same instant as an open is NOT an overlap: -1 sorts first.
  edges.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let now = 0, peak = 0;
  for (const [, delta] of edges) { now += delta; if (now > peak) peak = now; }
  return peak;
}
