// A value slot (lead b19236b03): { steps, value: {on, name}, end?, endTypes?, reduce? } - the walk table's «+ Column»
// column (walk/reach_table) plus how its values fold. A row reads it the way the table reads a cell; the reduce folds
// what it read, and no reduce takes one value only. Or an expression slot { expr, words } (Custom expression…, lead
// 10-13 plan a): the calculator (src/expression.js) answers it over the rows a point or a cell holds, [name] the row's
// own value. Or { self: true } - the row's own node (a sheet's key cell), or { constant } - a value as written (a
// sheet's cell). This file is the one place that asks which a slot is.

import { readsOf, recordsOf, waysOf, WAYS_A_CELL, valueWords, numberOf } from '../walk/reach_table.js';
import { timeOf } from '../walk/trend.js';
import { parseServerInstant, localStamp, NO_TIME } from '../server_time.js';
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
export function readSlot(index, inside, x, slot, oneValued = false, marked = null, cell = undefined) {
  // A slot of several columns (owner 10-14 «알약 여러 컬럼»): each column read, their values' combination one category
  // («A, B» - Spotfire's), `parts` its values column by column (a cross table's levels); one column - that column.
  if (Array.isArray(slot)) {
    const cols = columnsOf(slot);
    if (cols.length === 1) return readSlot(index, inside, x, cols[0], oneValued, marked, cell);
    if (!cols.length) return { state: 'empty', n: 0 };
    const reads = cols.map((c) => readSlot(index, inside, x, c, false, marked, cell));
    if (reads.some((r) => r.state === 'missing')) return { state: 'missing' };
    let tuples = [[]];
    for (const r of reads) {
      const cats = categoriesOf(r).map(String);
      tuples = tuples.flatMap((t) => (cats.length ? cats : [EMPTY]).map((v) => [...t, v]));
    }
    const values = tuples.map((t) => t.join(PART_SEP));
    return values.length === 1 ? { state: 'one', value: values[0], parts: tuples[0], n: 1 } : { state: 'several', values, parts: tuples, n: values.length };
  }
  if (isExpression(slot)) {
    if (!inside.has(x)) return { state: 'missing' };
    const c = compile(slot.expr);
    // Each name's declared column type, as the walk says it (a datetime's Min and Max compare instants - lead 10-13).
    const types = c.ok ? Object.fromEntries(c.names.map((n) => [n, typeOfName(index, inside, x, n)]).filter(([, t]) => t)) : {};
    const read = answerOne(run(c, [calcRow(index, inside, x)], { marked, cell, types }));
    return Object.keys(types).length ? { ...read, types } : read;
  }
  if (slot.self) return inside.has(x) ? { state: 'one', value: x, n: 1 } : { state: 'missing' };
  if ('constant' in slot) return isBlank(slot.constant) ? { state: 'empty', n: 0 } : { state: 'one', value: slot.constant, n: 1 };
  const got = readsAt(index, inside, x, slot);
  if (got.missing) return { state: 'missing' };
  const reads = got.reads;
  const reduce = slot.reduce || (oneValued ? 'Latest' : null);
  // a time read (readsAt) - said as a time wherever it is shown (valueText); the type its reads declare when they say one
  const declaredTypes = [...new Set(reads.map((r) => r.declared).filter(Boolean))];
  const time = { ...(reads.some((r) => r.time) ? { time: true } : {}), ...(declaredTypes.length === 1 ? { declared: declaredTypes[0] } : {}) };
  if (reduce) {
    const f = fold(reduce, reads);
    return f.value === null ? { state: 'empty', n: f.n, tied: f.tied } : { state: 'one', value: f.value, n: f.n, ...time };
  }
  const values = [...new Map(reads.flatMap((r) => [].concat(r.value)).map((v) => [spelling(v), v])).values()];
  if (!values.length) return { state: 'empty', n: 0 };
  return values.length === 1 ? { state: 'one', value: values[0], n: reads.length, ...time } : { state: 'several', values, n: reads.length, ...time };
}

/** The scales a slot may be drawn on (lead-board-13 ①, owner 10-14 «카테고리컬, 컨티뉴어스 별로»). */
export const SCALES = Object.freeze(['categorical', 'continuous']);
const CONTINUOUS_DECLARED = new Set(['number', 'datetime']);
const ISO_TIME = /^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/;
/** A value written as an ISO time (a date, a date and time, an offset or Z). */
export const isTimeText = (v) => typeof v === 'string' && ISO_TIME.test(v.trim());

/**
 * A slot's scale - THE one seat (lead-board-13 ①): the declaration's pick (`scale[key]`) when it makes one; else the walk's
 * declared type - number or datetime continuous (owner 10-14 «ㄱ») -, else its values - all numbers or all times
 * continuous, any other categorical. `time`: its values are times (declared datetime, or all written as times) - a
 * continuous time axis, or categories in time order.
 * @param {Array<{state, value?, values?, declared?}>} reads  the slot's reads, a row each
 * @param {'categorical'|'continuous'|null} [chosen]
 * @returns {{scale: 'categorical'|'continuous', time: boolean}}
 */
export function scaleOf(reads, chosen = null) {
  const said = (reads || []).filter((r) => r && (r.state === 'one' || r.state === 'several'));
  const values = said.flatMap((r) => (r.state === 'one' ? [r.value] : r.values || [])).filter((v) => !isBlank(v));
  const declared = [...new Set(said.map((r) => r.declared).filter(Boolean))];
  const one = declared.length === 1 ? declared[0] : null;
  const allTimes = values.length > 0 && values.every(isTimeText);
  const time = one === 'datetime' || allTimes;
  if (SCALES.includes(chosen)) return { scale: chosen, time };
  if (one && CONTINUOUS_DECLARED.has(one)) return { scale: 'continuous', time };
  const allNumbers = values.length > 0 && values.every((v) => numberOf(v) !== null);
  return { scale: allNumbers || allTimes ? 'continuous' : 'categorical', time };
}

/** Whether a read is a time: the walk says so - its column declared datetime (an edge's `column_types`, a node record's
 *  `column_type`), or a calculator's name of that type (`types`) - or it reads the time itself. */
export const isTimeRead = (read) => Boolean(read && (read.time || (read.types && Object.values(read.types).includes('datetime'))));

/** A value as it is shown - THE one place (tooltip, label, filter, Sheet): a time in the viewer's zone as the grid shows a
 *  datetime cell (server_time localStamp), the rest valueWords. */
export function valueText(value, time = false) {
  return (time && timeText(value)) || valueWords(value);
}

/** A time value in the viewer's zone (server_time localStamp); not a time - null. */
export const timeText = (value) => (localStamp(value) !== NO_TIME ? localStamp(value) : null);

/**
 * Every slot of a row, `pairs` [key, slot]. With `cells` (a kind of cells - the sheet, owner 3b97fcfb9) an expression
 * that names another slot's key (A1, B1:B9) reads that one's value: each read once, in the order they name each other;
 * a ring of them is a cycle, each of its slots {state: 'cycle', ring}. Without, a cell reference is refused by name.
 */
export function readSlots(index, inside, x, pairs, oneValued, marked, cells = false) {
  const bySlot = new Map(pairs);
  const out = {};
  if (!cells) { for (const [k, s] of pairs) out[k] = readSlot(index, inside, x, s, oneValued(s), marked); return out; }
  const busy = [];
  const need = (k) => {
    if (out[k]) return out[k];
    const at = busy.indexOf(k);
    if (at >= 0) return { state: 'cycle', ring: [...busy.slice(at), k] };
    const s = bySlot.get(k);
    if (!s) return null;
    busy.push(k);
    let ring = null;
    const value = (ref) => {
      const r = need(ref);
      if (r && r.state === 'cycle') { ring = ring || r.ring; return null; }
      return r && r.state === 'one' ? r.value : null;
    };
    const read = readSlot(index, inside, x, s, oneValued(s), marked, value);
    busy.pop();
    out[k] = ring ? { state: 'cycle', ring } : read;
    return out[k];
  };
  for (const [k] of pairs) need(k);
  return out;
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

/** A name's declared column type - the walk's (`column_type` on a node's record, `column_types` on an edge, implementer
 *  A d1f1c3e4b): its own value's, or its way's ends' first that says one; none - null. */
export function typeOfName(index, inside, x, name) {
  let at;
  try { at = nameValue(index, inside, x, name); } catch (e) { return null; }
  if (!at.value) return null;
  const ends = at.steps.length ? waysOf(index, inside, [x], at.steps, WAYS_A_CELL).ends : [{ node: x, edge: null }];
  for (const e of ends) {
    const said = at.value.on === 'edge' ? e.edge && (e.edge.column_types || {})[at.value.name]
      : ((((index.nodes.get(e.node) || {}).records || {})[at.value.name] || [])[0] || {}).column_type;
    if (said) return said;
  }
  return null;
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
  const reads = records ? got.reads.flatMap((r, read) => recordsOf(index, slot, r).map((rec) => ({ value: plainValue(rec.value), t: timeOf(rec.when), read, ...timeOfRead(index, slot, { ...r, value: rec.value }) })))
    : got.reads.map((r) => ({ value: plainValue(r.value), t: timeOf(r.when), ...timeOfRead(index, slot, r) }));
  return { missing: false, reads: slot.of === 'time' ? reads.filter((r) => r.t !== null).map((r) => ({ ...r, value: new Date(r.t).toISOString(), time: true })) : reads };
}

/** A read's declared column type as the walk says it - an edge's `column_types`, a node record's `column_type` - or null. */
function declaredOf(index, slot, r) {
  const name = slot.value && slot.value.name;
  const said = slot.value && slot.value.on === 'edge' ? r.edge && (r.edge.column_types || {})[name]
    : ((((index.nodes.get(r.node) || {}).records || {})[name] || [])[0] || {}).column_type;
  return typeof said === 'string' && said ? said : null;
}

/** A read a time: the server's {"$datetime"}, or a column the walk declares datetime - {time: true}; and its declared type. */
function timeOfRead(index, slot, r) {
  const declared = declaredOf(index, slot, r);
  const time = (r.value && typeof r.value === 'object' && typeof r.value.$datetime === 'string') || declared === 'datetime';
  return { ...(time ? { time: true } : {}), ...(declared ? { declared } : {}) };
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

/** A slot's columns - THE one place an older one-column slot reads as a list of one (owner 10-14: a pill of several
 *  columns; the declaration's slot value [column …]). */
export const columnsOf = (slot) => (Array.isArray(slot) ? slot.filter(Boolean) : slot ? [slot] : []);
/** A combination of several columns' values, as one category says it (Spotfire's «A, B»). */
export const PART_SEP = ', ';

/** A slot in words - what a pill and an axis say: «Avg(void_ratio)», «Latest(bond_temp)», «recipe»; several columns
 *  outer to inner, «lot › product». */
export function slotWords(slot) {
  if (Array.isArray(slot)) { const cols = columnsOf(slot); return cols.length ? cols.map(slotWords).join(' › ') : '(None)'; }
  if (!slot) return '(None)';
  if (isExpression(slot)) return slot.expr;
  const said = slot.words && slot.words.length ? slot.words[0] : slot.value.on === 'label' ? 'name' : slot.value.name;
  const name = slot.of === 'time' ? `time · ${said}` : said;
  return slot.reduce ? `${slot.reduce}(${name})` : name;
}
