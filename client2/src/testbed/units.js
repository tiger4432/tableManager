// THE ROW UNIT - the root part's Marker by (base set 6, docs/architecture/ROOT_PART_BASE_SET.md): what one mark of a kind
// is - a node; a hub, the rows a combination of the Marker by values holds (a cross table cell's hub, the same id); or a
// value record, a row spread into its Y's records (owner 10-13 «기록 하나가 점 하나»). The root makes the units and reads
// every slot of each once; a kind that draws a mark a unit (`units: true`) only draws them.

import { combosOf, foldRows, isExpression, slotWords, columnsOf } from './slot.js';
import { hubId } from './hubs.js';

const MARKER = /^marker(\d+)$/;
const markerOrder = (key) => Number(MARKER.exec(key)[1]);
/** The Marker by keys the declaration holds, in order. */
export const markersOf = (encode) => Object.keys(encode || {}).filter((k) => MARKER.test(k)).sort((a, b) => markerOrder(a) - markerOrder(b));
/** The key «+» on Marker by fills next. */
export const nextMarker = (encode) => { const keys = markersOf(encode); return `marker${keys.length ? markerOrder(keys[keys.length - 1]) + 1 : 1}`; };

/** A unit: a hub when a Marker by is held; else a value record (`markerBy: 'record'`); else a node. */
export const unitOf = (decl) => (markersOf((decl || {}).encode).length ? 'hub' : (decl || {}).markerBy === 'record' ? 'record' : 'node');
/** The Marker by choices that are not a slot - every Marker by pill lists them: a node, a value record, no Marker by
 *  slot held. */
const choices = (encode) => {
  const rest = Object.fromEntries(Object.entries(encode || {}).filter(([k]) => !MARKER.test(k)));
  return [{ words: '(Node)', patch: { markerBy: null, encode: rest } }, { words: '(Value record)', patch: { markerBy: 'record', encode: rest } }];
};

/** The Marker by slots: each held and the next one, each with the choices (Node, Value record). */
export const markerSlots = (encode) => [...markersOf(encode), nextMarker(encode)].map((key) => ({ key, label: 'Marker by', category: true, choices: choices(encode) }));

/** Several values no reduce folds, where a kind draws one value a place (the sheet's cell) - the root's sentence. */
export const MANY_WORDS = (n) => `${n ? `${n} values` : 'Several values'} — wrap in an aggregate`;
/** Why a row draws no mark: two of its slots read several values from different records. */
export const PAIR_WORDS = (a, b) => `${a} and ${b} come from different records — pick a reduce`;

/**
 * THE MARKS (lead-board-13 ②, owner 10-14 «펼쳐 그리기 기본 · 부품별로 다른 일 안 하게»): the root spreads each row into the
 * marks a kind draws, every read of a mark one value - a slot of one value the same on all its marks; a slot a reduce or
 * an expression folds one a row (readSlot already); a slot of several, a mark each - and two or more such slots pair
 * value by value when they come from the same records (an edge's atom, a node's value record), else the row draws none
 * and says why. A mark is its row's (`ids`, `row`): a press marks the row.
 * @param {Array<{id, label, reads, raw}>} rows  @param {string[]} keys  the slots read
 * @param {(id: string, key: string) => Array<{value, record}>|null} recordsOf  a several slot's reads, each its record (the
 *   root's; null - a slot that cannot say: an expression, several columns)
 * @param {(key: string) => string} words  a slot in words
 * @returns {{marks: Array, dropped: Array<{id, why}>}}
 */
export function marksOf(rows, keys, recordsOf, words, folds = []) {
  const marks = [];
  const dropped = [];
  for (const row of rows) {
    const many = keys.filter((k) => row.reads[k] && row.reads[k].state === 'several');
    if (!many.length) { marks.push({ ...row, ids: [row.id], row: row.id }); continue; }
    let picks;
    // each pick's records - a folded slot's values (`folds`: a cross table's cells) go with the mark of their record
    let recsOf = () => null;
    if (many.length === 1) {
      picks = (row.reads[many[0]].values || []).map((value) => [value]);
      const listed = folds.length ? recordsOf(row.id, many[0]) : null;
      if (listed) recsOf = (k) => listed.filter((r) => JSON.stringify(r.value) === JSON.stringify(picks[k][0])).map((r) => r.record);
    } else {
      const lists = many.map((k) => recordsOf(row.id, k));
      const recs = lists.map((l) => (l ? [...new Set(l.map((r) => r.record))] : null));
      const one = (l) => l && l.length === new Set(l.map((r) => r.record)).size;
      const same = lists.every(one) && recs.every((r) => r && r.length === recs[0].length && r.every((x) => recs[0].includes(x)));
      if (!same) { dropped.push({ id: row.id, why: PAIR_WORDS(words(many[0]), words(many[1])) }); continue; }
      picks = recs[0].map((rec) => lists.map((l) => l.find((r) => r.record === rec).value));
      recsOf = (k) => [recs[0][k]];
    }
    if (!picks.length) { dropped.push({ id: row.id, why: MANY_WORDS(0) }); continue; }
    picks.forEach((values, k) => {
      const reads = { ...row.reads };
      many.forEach((key, i) => {
        const base = row.reads[key];
        reads[key] = { state: 'one', value: values[i], n: 1, ...(base.time ? { time: true } : {}), ...(base.declared ? { declared: base.declared } : {}) };
      });
      // a folded slot's values of this mark's record - none of them its: the row's all (its values are no column's)
      const raw = row.raw && folds.length ? { ...row.raw } : row.raw;
      for (const f of folds) {
        const recs = recsOf(k);
        const all = row.raw && row.raw[f];
        const mine = recs && Array.isArray(all) ? all.filter((r) => r && recs.includes(r.record)) : null;
        if (mine && mine.length) raw[f] = mine;
      }
      marks.push({ ...row, id: `${row.id}#${k}`, ids: [row.id], row: row.id, reads, raw });
    });
  }
  return { marks, dropped };
}

/** A hub (or a value record) whose rows say several values on a slot with no reduce - why it is not drawn. */
export const HUB_MANY_WORDS = 'several values - pick a reduce (Avg · Count · Latest …)';

/**
 * What a kind draws, from rows - THE root's one spreading (lead-board-13 ②): a kind of one value a cell (`cells`, the
 * sheet) the rows with several refused; a Marker by (a hub, a value record - `record` the slot a record spreads) its units,
 * one with several left out; else the marks (marksOf). Every kind's root and its tests ask this one.
 * `drawn` - the slots the kind draws a mark's value of (its own: a scatter's x and y, a table's columns); the root's own
 * slots keep their row's reading. THE rule (lead 10-15): a slot that places or groups (an axis, Panel by, Marker by, a
 * cross table's rows and columns) stands a row in each of its values; a slot that paints (Color by, Shape by) can paint
 * one look only, so several is «(Multiple)» (color_by paintCategoryOf).
 * @returns {{units: Array, dropped: Array<{id, why}>}}
 */
export function spreadUnits(rows, decl, keys, { cells = false, record = null, recordsOf = () => null, words = (k) => k, marked = null, drawn = keys, folds = [] } = {}) {
  if (cells) return { units: refuseMany(rows), dropped: [] };
  if (record && unitOf(decl) !== 'node') {
    const all = unitsOf(rows, decl, keys, record, marked);
    const one = all.filter((u) => !drawn.some((k) => u.reads[k] && u.reads[k].state === 'several'));
    return { units: one, dropped: all.filter((u) => !one.includes(u)).map((u) => ({ id: u.id, why: HUB_MANY_WORDS })) };
  }
  // `folds` - the slots a kind folds a cell over (the cross table's cells): a mark keeps its own record's values of them
  const got = marksOf(rows, drawn, recordsOf, words, folds);
  return { units: got.marks, dropped: got.dropped };
}

/** A kind that draws one value a place (the sheet): a row's several read is the root's refusal - #MANY and why. */
export const refuseMany = (rows) => rows.map((row) => {
  const many = Object.entries(row.reads).filter(([, r]) => r && r.state === 'several');
  if (!many.length) return { ...row, ids: [row.id], row: row.id };
  const reads = { ...row.reads };
  for (const [k, r] of many) reads[k] = { state: 'empty', n: 0, error: '#MANY', why: MANY_WORDS(r.n || (r.values || []).length) };
  return { ...row, ids: [row.id], row: row.id, reads };
});

/** The pill's words when no Marker by is held. */
export const unitWords = (decl) => (unitOf(decl) === 'record' ? '(Value record)' : '(Node)');

/**
 * The units of the rows by the declaration, each slot read as one: { id, ids, where, label, reads } - a hub's id its
 * hub id and `where` its values by the slots' words; a value record's id the row's and its record's place.
 * @param {Array<{id, label, reads, raw}>} rows  a slot that folds is in `raw` too (every read; for a value record its records)
 * @param {object} decl  @param {string[]} keys  the slots read  @param {string} recordKey  the slot whose records a value
 *   record spreads (the kind's `units.record`)  @param {Function} [marked]  an expression's Marked() (the root's)
 */
export function unitsOf(rows, decl, keys, recordKey, marked = null) {
  const encode = (decl && decl.encode) || {};
  const unit = unitOf(decl);
  if (unit === 'node') return rows.map((row) => ({ ...row, ids: [row.id], where: null }));
  if (unit === 'record') {
    return rows.flatMap((row) => recordPicks(row, recordKey, encode[recordKey]).map((picks, k) => ({ id: `${row.id}#${k}`, ids: [row.id], where: null, label: row.label,
      reads: Object.fromEntries(keys.map((key) => [key, recordRead(row, key, picks, encode[key], recordKey, marked)])) })));
  }
  const markers = markersOf(encode);
  const byId = new Map(rows.map((r) => [r.id, r]));
  return combosOf(rows, markers).map(({ values, ids }) => {
    const where = markers.map((k, i) => [slotWords(encode[k]), values[i]]);
    const of = ids.map((id) => byId.get(id));
    return { id: hubId(decl.row, where), ids, where, label: values.join(' · '),
      reads: Object.fromEntries(keys.map((key) => [key, foldedRead(of, key, encode[key], marked)])) };
  });
}

/** A hub's rows read as one on a slot: with a reduce or an expression, every value of theirs folded (slot.foldRows - the
 *  cross table's rule); without, the value when they all say one and the same, several when not, empty when none says one. */
function foldedRead(rows, key, slots, marked) {
  if (!slots) return undefined;
  // a list of one is that column; one of several is read as its rows read it (their combinations)
  const cols = columnsOf(slots);
  const slot = cols.length === 1 ? cols[0] : {};
  if (slot.reduce || isExpression(slot)) {
    const value = foldRows(slot, rows.map((r) => r.raw && r.raw[key]), marked);
    const time = rows.some((r) => ((r.raw && r.raw[key]) || []).some((x) => x.time)) ? { time: true } : {};
    return value === null || value === undefined ? { state: 'empty' } : { state: 'one', value, ...time };
  }
  const reads = rows.map((r) => r.reads[key]).filter(Boolean);
  const time = reads.some((r) => r.time) ? { time: true } : {};
  if (reads.some((r) => r.state === 'several')) return { state: 'several', values: [], ...time };
  const said = [...new Map(reads.filter((r) => r.state === 'one').map((r) => [JSON.stringify(r.value), r.value])).values()];
  return said.length === 1 ? { state: 'one', value: said[0], ...time } : said.length ? { state: 'several', values: said, ...time } : { state: 'empty' };
}

/** A row's value records as units: each record of the record slot its own; that slot with a reduce - each read's records
 *  (an edge's) one. */
function recordPicks(row, recordKey, recordSlot) {
  const ys = (row.raw && row.raw[recordKey]) || [];
  if (!(recordSlot && recordSlot.reduce)) return ys.map((_, k) => [k]);
  const byRead = new Map();
  ys.forEach((r, k) => { if (!byRead.has(r.read)) byRead.set(r.read, []); byRead.get(r.read).push(k); });
  return [...byRead.values()];
}

/** A value record's read on a slot: the records it takes when the slot reads as many as the record slot (itself; its
 *  time) - folded by the slot's reduce, else their one value (several when they differ); else the row's one value. */
function recordRead(row, key, picks, slots, recordKey, marked) {
  if (!slots) return undefined;
  const cols = columnsOf(slots);
  const slot = cols.length === 1 ? cols[0] : {};
  const raw = row.raw && row.raw[key];
  const records = row.raw && row.raw[recordKey];
  if (!raw || !records || raw.length !== records.length) return row.reads[key];
  const items = picks.map((k) => raw[k]);
  if (slot.reduce) { const value = foldRows(slot, [items], marked); return value === null || value === undefined ? { state: 'empty' } : { state: 'one', value }; }
  const said = [...new Map(items.map((r) => [JSON.stringify(r.value), r.value])).values()];
  return said.length === 1 ? { state: 'one', value: said[0] } : { state: 'several', values: said };
}
