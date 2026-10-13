// The reduces a value slot takes (lead aca803a7a · owner 「1 ㅇㅇ」): Spotfire's spelling, down to the declaration. The
// folds are the expression calculator's one function table (src/expression.js, lead 10-13 plan a) - contracts/
// walk_aggregate scores them against the server's walk fold, contracts/expression against Spotfire's rules; Latest is
// ours (Spotfire has none - task/SPOTFIRE_FUNCTIONS.md 1-a).

import { foldItems } from '../expression.js';

export const REDUCES = Object.freeze(['Count', 'UniqueCount', 'Sum', 'Avg', 'Min', 'Max', 'Median', 'Latest']);

/**
 * One slot's values folded. `reads` are {value, t}: t the read's time in ms (the atom's occurred_at), null when it says
 * none. A list value counts as its items. Blank values never count.
 * @returns {{value: *, n: number, skipped?: number, tied?: number, untimed?: number}} - value null when there is nothing
 *   to fold (0 would say the values were there and summed to nothing); `skipped` the values a numeric fold could not read
 *   as numbers; Latest's `tied` the values sharing the newest time, `untimed` the reads with no time to order by.
 */
export function fold(reduce, reads) {
  if (!REDUCES.includes(reduce)) throw new Error(`Unknown reduce: ${reduce}`);
  const { value, n, ...rest } = foldItems(reduce, reads || []);
  return { value, n, ...rest };
}
