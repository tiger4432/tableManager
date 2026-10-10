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
    .map((r) => ({ t: timeOf(r.edge), value: r.value, group: i, walked: true, key: keyOf(r.edge, `${i}:${r.node}`) })));
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
    return { t: timeOf(e), value: (e.qualifiers || {})[column.value.name], group: group >= 0 ? group : null, walked: walked.has(key), key };
  }).filter((p) => !isBlank(p.value));
}

/** The walk's points with a page's: one point a key, the walk's kept (it knows the group it came by). */
export function mergePoints(walk, page) {
  const seen = new Set(walk.map((p) => p.key));
  return [...walk, ...page.filter((p) => !seen.has(p.key))];
}

const isNumber = (v) => typeof v === 'number' && Number.isFinite(v);

/**
 * The chart's model: the numbers on a value axis, the rest in lanes - one a value, the most frequent first, past
 * `lanes` the rest in «others» - the time span, the value span, and how many points had no time.
 */
export function trendModel(points, lanes = LANES) {
  const timed = points.filter((p) => p.t !== null);
  const numbers = timed.filter((p) => isNumber(p.value));
  const words = timed.filter((p) => !isNumber(p.value)).map((p) => ({ ...p, word: valueWords(p.value) }));
  const counts = new Map();
  for (const p of words) counts.set(p.word, (counts.get(p.word) || 0) + 1);
  const order = [...counts].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).map(([w]) => w);
  const kept = new Set(order.slice(0, lanes));
  const ts = timed.map((p) => p.t);
  const vs = numbers.map((p) => p.value);
  return {
    numbers,
    words: words.map((p) => ({ ...p, lane: kept.has(p.word) ? p.word : OTHERS })),
    lanes: [...order.slice(0, lanes), ...(order.length > lanes ? [OTHERS] : [])],
    t: ts.length ? [Math.min(...ts), Math.max(...ts)] : null,
    v: vs.length ? [Math.min(...vs), Math.max(...vs)] : null,
    untimed: points.length - timed.length,
  };
}

/** The walked time: the latest walked point's, else the answer's own time. */
export function walkedTime(points, asOf) {
  const ts = points.filter((p) => p.walked && p.t !== null).map((p) => p.t);
  if (ts.length) return Math.max(...ts);
  const t = Date.parse(asOf);
  return Number.isFinite(t) ? t : null;
}
