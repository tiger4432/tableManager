// The reduces a value slot takes (lead aca803a7a · owner 「1 ㅇㅇ」): Spotfire's spelling, down to the declaration. The
// seven are the server's walk fold (ledger_subgraph AGGREGATE_MEASURES) and fold the same way - contracts/walk_aggregate
// scores this file against the server's answers; Latest is ours (Spotfire has none - task/SPOTFIRE_FUNCTIONS.md 1-a).

import { isBlank } from '../absent.js';
import { numberOf } from '../walk/reach_table.js';

export const REDUCES = Object.freeze(['Count', 'UniqueCount', 'Sum', 'Avg', 'Min', 'Max', 'Median', 'Latest']);
const NUMERIC = new Set(['Sum', 'Avg', 'Min', 'Max', 'Median']);

/** A value's one spelling for «the same value» - a list by its items (reach_table sameValue). */
const spelling = (v) => JSON.stringify(v);

/**
 * One slot's values folded. `reads` are {value, t}: t the read's time in ms (the atom's occurred_at), null when it says
 * none. A list value counts as its items. Blank values never count.
 * @returns {{value: *, n: number, skipped?: number, tied?: number, untimed?: number}} - value null when there is nothing
 *   to fold (0 would say the values were there and summed to nothing); `skipped` the values a numeric fold could not read
 *   as numbers; Latest's `tied` the values sharing the newest time, `untimed` the reads with no time to order by.
 */
export function fold(reduce, reads) {
  const flat = (reads || []).flatMap((r) => (Array.isArray(r.value) ? r.value.map((value) => ({ ...r, value })) : [r]))
    .filter((r) => !isBlank(r.value));
  const n = flat.length;
  if (reduce === 'Count') return { value: n, n };
  if (reduce === 'UniqueCount') return { value: new Set(flat.map((r) => spelling(r.value))).size, n };
  if (reduce === 'Latest') return latest(flat);
  if (!NUMERIC.has(reduce)) throw new Error(`Unknown reduce: ${reduce}`);
  const nums = flat.map((r) => numberOf(r.value)).filter((x) => x !== null);
  const skipped = n - nums.length;
  if (!nums.length) return { value: null, n, skipped };
  const sorted = [...nums].sort((a, b) => a - b);
  const sum = nums.reduce((a, b) => a + b, 0);
  const value = reduce === 'Sum' ? sum
    : reduce === 'Avg' ? sum / nums.length
      : reduce === 'Min' ? sorted[0]
        : reduce === 'Max' ? sorted[sorted.length - 1]
          : sorted.length % 2 ? sorted[(sorted.length - 1) / 2]
            : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
  return { value, n, skipped };
}

/** The value at the newest time. Two different values at that time: none - no rule orders them (the server's
 *  current_conflicts). One read: its value, timed or not. */
function latest(flat) {
  if (!flat.length) return { value: null, n: 0 };
  if (flat.length === 1) return { value: flat[0].value, n: 1 };
  const timed = flat.filter((r) => Number.isFinite(r.t));
  const untimed = flat.length - timed.length;
  if (!timed.length) {
    const one = new Set(flat.map((r) => spelling(r.value)));
    return one.size === 1 ? { value: flat[0].value, n: flat.length } : { value: null, n: flat.length, untimed };
  }
  const newest = Math.max(...timed.map((r) => r.t));
  const at = [...new Map(timed.filter((r) => r.t === newest).map((r) => [spelling(r.value), r.value])).values()];
  return at.length === 1 ? { value: at[0], n: flat.length, untimed } : { value: null, n: flat.length, tied: at.length, untimed };
}
