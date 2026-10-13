// A value slot (lead b19236b03): { steps, value: {on, name}, end?, endTypes?, reduce? } - the walk table's «+ Column»
// column (walk/reach_table) plus how its values fold. A row reads it the way the table reads a cell; the reduce folds
// what it read, and no reduce takes one value only. Or an expression slot { expr, words } (Custom expression…, lead
// 10-13 plan a): the calculator (src/expression.js) answers it over the rows a point or a cell holds, [name] the row's
// own value. This file is the one place that asks which of the two a slot is.

import { readsOf, recordsOf, waysOf, WAYS_A_CELL } from '../walk/reach_table.js';
import { timeOf } from '../walk/trend.js';
import { parseServerInstant } from '../server_time.js';
import { isBlank } from '../absent.js';
import { compile, run, Reads, ExpressionError } from '../expression.js';
import { fold } from './aggregate.js';

const spelling = (v) => JSON.stringify(v);

/**
 * What row `x` holds for a slot, inside the walk's node set.
 * @param {boolean} [oneValued]  the slot's value is declared one-valued (cardinality one): several reads are its history
 *   and the newest is the value - Latest without asking (lead aca803a7a).
 * @param {Function} [marked]  the page's marking answer (name, node) -> true · false · null, for an expression's Marked()
 * @returns {{state: 'one'|'several'|'empty'|'missing', value?: *, values?: Array, n?: number, tied?: number, notNumber?: boolean}}
 *   one - a value to draw; several - values that differ and no reduce, so not drawn; empty - nothing said (notNumber:
 *   an expression's operator met a text that is not a number); missing - the row is not in the walk
 */
export function readSlot(index, inside, x, slot, oneValued = false, marked = null) {
  if (isExpression(slot)) return inside.has(x) ? answerOne(run(compile(slot.expr), [calcRow(index, inside, x)], { marked })) : { state: 'missing' };
  const got = readsAt(index, inside, x, slot);
  if (got.missing) return { state: 'missing' };
  const reads = got.reads;
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

/** A name with a way in it (owner afcb79f14): «.» joins the steps and the value, the last part the value's name, «~»
 *  after a predicate walks it backwards - [in_container~.x]. -> { steps, name }, or null: a name with no way. */
export function wayOf(name) {
  const parts = String(name).split('.');
  if (parts.length < 2) return null;
  const last = parts.pop();
  return { name: last, steps: stepsOf(parts.join('.')) };
}

/** Steps alone in the brackets' spelling - Marked's way, [in_container~.in_lot]. */
export const stepsOf = (text) => String(text).split('.').filter(Boolean)
  .map((p) => (p.endsWith('~') ? { predicate: p.slice(0, -1), direction: 'incoming' } : { predicate: p, direction: 'outgoing' }));

/** Steps in the brackets' spelling - what Custom expression starts from. */
export const wayWords = (steps) => (steps || []).map((s) => `${s.predicate}${s.direction === 'incoming' ? '~' : ''}`).join('.');

/** What `name` reads on row `x` - the one seat the calculator's row and the picker's check ask: the row's own value; or,
 *  a name with a way in it, what the way's ends call it - an end node's own value or the last edge's attribute (both:
 *  refused - two answers; neither: none). -> { steps, value } (value null: the name says nothing here). */
export function nameValue(index, inside, x, name) {
  const way = wayOf(name);
  if (!way) return { steps: [], value: ownValue(index.nodes.get(x) || {}, name) };
  const { ends } = waysOf(index, inside, [x], way.steps, WAYS_A_CELL);
  const onEdge = ends.some((e) => e.edge && Object.prototype.hasOwnProperty.call(e.edge.qualifiers || {}, way.name));
  const own = ends.map((e) => ownValue(index.nodes.get(e.node) || {}, way.name)).find(Boolean) || null;
  if (onEdge && own) throw new ExpressionError(`[${name}] is both a value of the node it reaches and of its edge`);
  return { steps: way.steps, value: onEdge ? { on: 'edge', name: way.name } : own };
}

/** A row as the calculator reads it: each name its value's reads (its own, or a way's), with their times. */
export function calcRow(index, inside, x) {
  return {
    at: null,
    id: x,
    // Marked's way (lead 10-13): the nodes it ends at from this row - none, null (unknown).
    endsOf: (text) => {
      const { ends } = waysOf(index, inside, [x], stepsOf(text), Infinity);
      return ends.length ? [...new Set(ends.map((e) => e.node))] : null;
    },
    get: (name) => {
      const { steps, value } = nameValue(index, inside, x, name);
      return value ? new Reads(readsAt(index, inside, x, { steps, value }).reads) : null;
    },
  };
}

/** One row's answer as a slot read. */
function answerOne(out) {
  if (out.several) return { state: 'several', values: [] };
  const v = 'values' in out ? out.values[0] : out.value;
  return isBlank(v) ? { state: 'empty', n: 0, why: out.why, notNumber: out.notNumber > 0 } : { state: 'one', value: v, n: 1 };
}

/** What a folding slot keeps of a row: its reads {value, t} (`records` - each read spread into its records), or the row
 *  itself for an expression. */
export function rawOf(index, inside, x, slot, records = false) {
  if (isExpression(slot)) return calcRow(index, inside, x);
  // A calculation reads every way (lead 10-13: a fold over 50 of 2,199 is a wrong answer said as a right one).
  return readsAt(index, inside, x, slot, records).reads;
}

/** A set of rows' raws folded - a cell, a total: the expression over the rows, or the reduce over their reads. */
export function foldRows(slot, raws, marked = null) {
  if (isExpression(slot)) { const out = run(compile(slot.expr), raws, { marked }); return 'value' in out ? out.value : null; }
  return fold((slot && slot.reduce) || 'Count', raws.flatMap((r) => r || [])).value;
}

/** A category slot's members for one row: each of its values (the cross table counts a row with two in both cells - lead
 *  aca803a7a, as the server's group_by puts a plural node in every group it names), [] when it says none. */
export function categoriesOf(read) {
  if (read.state === 'one') return [].concat(read.value);
  if (read.state === 'several') return read.values;
  return [];
}

/** Every read of a slot from row `x`: {value, t} - t its time (trend.js timeOf: its edge's or node record's occurred_at).
 *  A slot `of: 'time'` reads the time itself (ISO, the trend's time axis), a read with none left out. */
export function readsAt(index, inside, x, slot, records = false) {
  const got = readsOf(index, inside, x, slot, Infinity);
  if (got.missing) return { missing: true, reads: [] };
  // records - each read spread into its records (reach_table.recordsOf: an edge's every atom), `read` the read it is of
  const reads = records ? got.reads.flatMap((r, read) => recordsOf(index, slot, r).map((rec) => ({ value: plainValue(rec.value), t: timeOf(rec.when), read })))
    : got.reads.map((r) => ({ value: plainValue(r.value), t: timeOf(r.when) }));
  return { missing: false, reads: slot.of === 'time' ? reads.filter((r) => r.t !== null).map((r) => ({ ...r, value: new Date(r.t).toISOString() })) : reads };
}

/** A value as a slot reads it: a time the server sends as {"$datetime": iso} (ledger roleframe) its instant in ISO -
 *  the one reading of the server's time (server_time.js parseServerInstant); the rest as it came. */
export function plainValue(v) {
  if (!v || typeof v !== 'object' || typeof v.$datetime !== 'string') return v;
  const at = parseServerInstant(v.$datetime);
  return at ? at.toISOString() : v.$datetime;
}

/** A category saying none. */
export const EMPTY = '(Empty)';

/** The rows of every combination of categories some keys make - a row's categories on a key (none - (Empty), a key with
 *  no slot - ''), a row with two on one key in both: [{values, ids}] in first-seen order. A cross table's cells and the
 *  scatter's Marker by markers are these - each a hub of its rows. */
export function combosOf(rows, keys) {
  const out = new Map();
  for (const row of rows) {
    let combos = [[]];
    for (const key of keys) {
      const read = row.reads[key];
      const cats = read ? (categoriesOf(read).length ? categoriesOf(read).map(String) : [EMPTY]) : [''];
      combos = combos.flatMap((c) => cats.map((v) => [...c, v]));
    }
    for (const values of combos) {
      const at = JSON.stringify(values);
      if (!out.has(at)) out.set(at, { values, ids: [] });
      out.get(at).ids.push(row.id);
    }
  }
  return [...out.values()];
}

/** A slot in words - what a pill and an axis say: «Avg(void_ratio)», «Latest(bond_temp)», «recipe». */
export function slotWords(slot) {
  if (!slot) return '(None)';
  if (isExpression(slot)) return slot.expr;
  const said = slot.words && slot.words.length ? slot.words[0] : slot.value.on === 'label' ? 'name' : slot.value.name;
  const name = slot.of === 'time' ? `time · ${said}` : said;
  return slot.reduce ? `${slot.reduce}(${name})` : name;
}
