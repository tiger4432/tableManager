// A value slot (lead b19236b03): { steps, value: {on, name}, end?, endTypes?, reduce? } - the walk table's «+ Column»
// column (walk/reach_table) plus how its values fold. A row reads it the way the table reads a cell; the reduce folds
// what it read, and no reduce takes one value only. Or an expression slot { expr, words } (Custom expression…, lead
// 10-13 plan a): the calculator (src/expression.js) answers it over the rows a point or a cell holds, [name] the row's
// own value. This file is the one place that asks which of the two a slot is.

import { readsOf } from '../walk/reach_table.js';
import { timeOf } from '../walk/trend.js';
import { isBlank } from '../absent.js';
import { compile, run, Reads, ExpressionError } from '../expression.js';
import { fold } from './aggregate.js';

const spelling = (v) => JSON.stringify(v);

/**
 * What row `x` holds for a slot, inside the walk's node set.
 * @param {boolean} [oneValued]  the slot's value is declared one-valued (cardinality one): several reads are its history
 *   and the newest is the value - Latest without asking (lead aca803a7a).
 * @returns {{state: 'one'|'several'|'empty'|'missing', value?: *, values?: Array, n?: number, tied?: number, notNumber?: boolean}}
 *   one - a value to draw; several - values that differ and no reduce, so not drawn; empty - nothing said (notNumber:
 *   an expression's operator met a text that is not a number); missing - the row is not in the walk
 */
export function readSlot(index, inside, x, slot, oneValued = false) {
  if (isExpression(slot)) return inside.has(x) ? answerOne(run(compile(slot.expr), [calcRow(index, inside, x)])) : { state: 'missing' };
  const got = readsOf(index, inside, x, slot, Infinity);
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

/** Is this slot an expression - the one place that asks. */
export const isExpression = (slot) => Boolean(slot) && typeof slot.expr === 'string';

/** Which of a node's own values a name reads: its attribute, its key, or «name» - its label. A name that is both an
 *  attribute and a key is refused (the grammar's «two answers refuse», afcb79f14). None: the node says nothing. */
export function ownValue(node, name) {
  const has = (o) => Object.prototype.hasOwnProperty.call(o || {}, name);
  if (has(node.attributes) && has(node.keys)) throw new ExpressionError(`[${name}] is both a key and a value of ${node.type || 'this row'}`);
  if (has(node.attributes)) return { on: 'node', name };
  if (has(node.keys)) return { on: 'key', name };
  return name === 'name' ? { on: 'label', name } : null;
}

/** A row as the calculator reads it: each name its own value's reads, with their times. */
export function calcRow(index, inside, x) {
  const node = index.nodes.get(x) || {};
  return {
    at: null,
    get: (name) => {
      const value = ownValue(node, name);
      return value ? new Reads(readsOf(index, inside, x, { steps: [], value }, Infinity).reads.map((r) => ({ value: r.value, t: timeOf(r.when) }))) : null;
    },
  };
}

/** One row's answer as a slot read. */
function answerOne(out) {
  if (out.several) return { state: 'several', values: [] };
  const v = 'values' in out ? out.values[0] : out.value;
  return isBlank(v) ? { state: 'empty', n: 0, why: out.why, notNumber: out.notNumber > 0 } : { state: 'one', value: v, n: 1 };
}

/** What a folding slot keeps of a row: its reads {value, t}, or the row itself for an expression. */
export function rawOf(index, inside, x, slot) {
  if (isExpression(slot)) return calcRow(index, inside, x);
  // A calculation reads every way (lead 10-13: a fold over 50 of 2,199 is a wrong answer said as a right one).
  return readsOf(index, inside, x, slot, Infinity).reads.map((r) => ({ value: r.value, t: timeOf(r.when) }));
}

/** A set of rows' raws folded - a cell, a total: the expression over the rows, or the reduce over their reads. */
export function foldRows(slot, raws) {
  if (isExpression(slot)) { const out = run(compile(slot.expr), raws); return 'value' in out ? out.value : null; }
  return fold((slot && slot.reduce) || 'Count', raws.flatMap((r) => r || [])).value;
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
  if (isExpression(slot)) return slot.expr;
  const name = slot.words && slot.words.length ? slot.words[0] : slot.value.on === 'label' ? 'name' : slot.value.name;
  return slot.reduce ? `${slot.reduce}(${name})` : name;
}
