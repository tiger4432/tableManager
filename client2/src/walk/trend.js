// ═══════════════════════════════════════════════════════════════════════════════
// TREND — one column's values on a time axis (owner 10-10 «범주 트렌드로 한 부품으로 끝내», lead f984ab01d, a2eb4a516):
// a point a read - the value the table's cell reads (reach_table.readsOf), at the time of its way's last edge, coloured by
// the group it came by. Numbers stand on a value axis; every other value has a lane (the most frequent first, the rest
// «others»). A time page from the server adds the row's other edges of that step around the walked time.
// ═══════════════════════════════════════════════════════════════════════════════
import { readsOf, valueWords } from './reach_table.js';
import { isBlank } from '../absent.js';

/** The lanes a trend keeps for words; past them one lane «others». */
export const LANES = 8;
export const OTHERS = 'others';
/** The points one server page asks (the implementer's contract: page=1000, at most 5000). */
export const PAGE_ROWS = 1000;

const timeOf = (edge) => {
  const t = edge && Date.parse(edge.occurred_at);
  return Number.isFinite(t) ? t : null;
};
const keyOf = (edge, fallback) => (edge && (edge.claim_id || edge.id)) || fallback;

/** The walk's own points of one row's column: each group's reads, at the time of each read's last edge. */
export function walkPoints(index, groups, x, column) {
  return groups.flatMap((g, i) => readsOf(index, g.inside, x, column).reads
    .map((r) => ({ t: timeOf(r.edge), value: r.value, group: i, walked: true, key: keyOf(r.edge, `${i}:${r.node}`), node: r.node })));
}

/**
 * A time page's points (lead's B, the implementer's contract): an edge a point, its value the column's edge attribute,
 * its group the first whose reach holds the edge's far end (none: another row's), walked when the walk brought it.
 */
export function pagePoints(answer, groups, x, column, walked = new Set()) {
  return ((answer && answer.edges) || []).map((e) => {
    const far = e.source === x ? e.target : e.source;
    const group = groups.findIndex((g) => g.inside.has(far));
    const key = keyOf(e, e.id);
    return { t: timeOf(e), value: (e.qualifiers || {})[column.value.name], group: group >= 0 ? group : null, walked: walked.has(key), key,
      node: far };
  }).filter((p) => !isBlank(p.value));
}

/**
 * Where a time page reads a trend's edges from (lead 10-10 E2): the node every read of `rows` shares - the row when
 * there is one, else the far end they all reach, the step taken the other way - for one step whose edge carries the
 * value (the server's time-page shape). Several ends, or another column: none.
 */
export function pageAnchor(rows, points, column) {
  const step = column.steps.length === 1 && column.value.on === 'edge' ? column.steps[0] : null;
  if (!step) return null;
  if (rows.length === 1) return { id: rows[0], predicate: step.predicate, direction: step.direction };
  const ends = [...new Set(points.map((p) => p.node))];
  return ends.length === 1
    ? { id: ends[0], predicate: step.predicate, direction: step.direction === 'incoming' ? 'outgoing' : 'incoming' } : null;
}

/** The walk's points with a page's: one point a key, the walk's kept (it knows the group it came by). */
export function mergePoints(walk, page) {
  const seen = new Set(walk.map((p) => p.key));
  return [...walk, ...page.filter((p) => !seen.has(p.key))];
}

const isNumber = (v) => typeof v === 'number' && Number.isFinite(v);

/** A time page's window, ms: the first and last time it holds; none for an empty page. */
export function windowOf(answer) {
  const w = answer && answer.page && answer.page.window;
  const span = w ? [Date.parse(w.from), Date.parse(w.to)] : [];
  return span.length && span.every(Number.isFinite) ? span : null;
}

/**
 * The time axis (lead 10-10, on the box: one side's walked point two days off squeezed 2,000 points into one line at the
 * right): the time pages' windows and the pressed side's walked points. Without either, every timed point.
 */
function axisOf(timed, frame) {
  const ts = [...(frame.windows || []).flat(),
    ...timed.filter((p) => p.walked && p.group === frame.group).map((p) => p.t)];
  const all = ts.length ? ts : timed.map((p) => p.t);
  return all.length ? [Math.min(...all), Math.max(...all)] : null;
}

/**
 * The chart's model: the numbers on a value axis, the rest in lanes - one a value, the most frequent first, past
 * `lanes` the rest in «others» - the time span, the value span, and how many points had no time. A point outside the
 * axis is not drawn; each group's before and after it say themselves at the edge (`outside`: the nearest time, how many).
 */
export function trendModel(points, lanes = LANES, frame = {}) {
  const span = axisOf(points.filter((p) => p.t !== null), frame);
  const timed = points.filter((p) => p.t !== null && p.t >= span[0] && p.t <= span[1]);
  const outside = [];
  for (const p of points.filter((x) => x.t !== null && (x.t < span[0] || x.t > span[1]))) {
    const before = p.t < span[0];
    const at = outside.find((o) => o.group === p.group && o.before === before);
    if (!at) outside.push({ group: p.group, before, t: p.t, n: 1 });
    else { at.n += 1; if (before ? p.t > at.t : p.t < at.t) at.t = p.t; }
  }
  const numbers = timed.filter((p) => isNumber(p.value));
  const words = timed.filter((p) => !isNumber(p.value)).map((p) => ({ ...p, word: valueWords(p.value) }));
  const counts = new Map();
  for (const p of words) counts.set(p.word, (counts.get(p.word) || 0) + 1);
  const order = [...counts].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).map(([w]) => w);
  const kept = new Set(order.slice(0, lanes));
  const vs = numbers.map((p) => p.value);
  return {
    numbers,
    words: words.map((p) => ({ ...p, lane: kept.has(p.word) ? p.word : OTHERS })),
    lanes: [...order.slice(0, lanes), ...(order.length > lanes ? [OTHERS] : [])],
    t: timed.length ? span : null,
    v: vs.length ? [Math.min(...vs), Math.max(...vs)] : null,
    untimed: points.filter((p) => p.t === null).length,
    outside,
  };
}

/** The walked time: the pressed side's latest walked point's (any side's when none is named), else the answer's. */
export function walkedTime(points, asOf, group) {
  const ts = points.filter((p) => p.walked && p.t !== null && (group === undefined || p.group === group)).map((p) => p.t);
  if (ts.length) return Math.max(...ts);
  const t = Date.parse(asOf);
  return Number.isFinite(t) ? t : null;
}
