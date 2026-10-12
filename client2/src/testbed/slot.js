// A value slot (lead b19236b03): { steps, value: {on, name}, end?, endTypes?, reduce? } - the walk table's «+ Column»
// column (walk/reach_table) plus how its values fold. A row reads it the way the table reads a cell; the reduce folds
// what it read, and no reduce takes one value only.

import { readsOf } from '../walk/reach_table.js';
import { timeOf } from '../walk/trend.js';
import { fold } from './aggregate.js';

const spelling = (v) => JSON.stringify(v);

/**
 * What row `x` holds for a slot, inside the walk's node set.
 * @param {boolean} [oneValued]  the slot's value is declared one-valued (cardinality one): several reads are its history
 *   and the newest is the value - Latest without asking (lead aca803a7a).
 * @returns {{state: 'one'|'several'|'empty'|'missing', value?: *, values?: Array, n?: number, tied?: number}}
 *   one - a value to draw; several - values that differ and no reduce, so not drawn; empty - nothing said; missing -
 *   the row is not in the walk
 */
export function readSlot(index, inside, x, slot, oneValued = false) {
  const got = readsOf(index, inside, x, slot);
  if (got.missing) return { state: 'missing' };
  const reads = got.reads.map((r) => ({ value: r.value, t: timeOf(r.when) }));
  const reduce = slot.reduce || (oneValued ? 'Latest' : null);
  if (reduce) {
    const f = fold(reduce, reads);
    return f.value === null ? { state: 'empty', n: f.n, tied: f.tied } : { state: 'one', value: f.value, n: f.n };
  }
  const values = [...new Map(reads.flatMap((r) => [].concat(r.value)).map((v) => [spelling(v), v])).values()];
  if (!values.length) return { state: 'empty', n: 0 };
  return values.length === 1 ? { state: 'one', value: values[0], n: reads.length } : { state: 'several', values, n: reads.length };
}

/** A category slot's members for one row: each of its values (the cross table counts a row with two in both cells - lead
 *  aca803a7a, as the server's group_by puts a plural node in every group it names), [] when it says none. */
export function categoriesOf(read) {
  if (read.state === 'one') return [].concat(read.value);
  if (read.state === 'several') return read.values;
  return [];
}

/** A slot in words - what a pill and an axis say: «Avg(void_ratio)», «Latest(bond_temp)», «recipe». */
export function slotWords(slot) {
  if (!slot) return '(None)';
  const name = slot.words && slot.words.length ? slot.words[0] : slot.value.on === 'label' ? 'name' : slot.value.name;
  return slot.reduce ? `${slot.reduce}(${name})` : name;
}
