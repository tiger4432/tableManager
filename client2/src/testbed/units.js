// THE ROW UNIT - the root part's Marker by (base set 6, docs/architecture/ROOT_PART_BASE_SET.md): what one mark of a kind
// is - a node; a hub, the rows a combination of the Marker by values holds (a cross table cell's hub, the same id); or a
// value record, a row spread into its Y's records (owner 10-13 «기록 하나가 점 하나»). The root makes the units and reads
// every slot of each once; a kind that draws a mark a unit (`units: true`) only draws them.

import { combosOf, foldRows, isExpression, slotWords } from './slot.js';
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
function foldedRead(rows, key, slot, marked) {
  if (!slot) return undefined;
  if (slot.reduce || isExpression(slot)) {
    const value = foldRows(slot, rows.map((r) => r.raw && r.raw[key]), marked);
    return value === null || value === undefined ? { state: 'empty' } : { state: 'one', value };
  }
  const reads = rows.map((r) => r.reads[key]).filter(Boolean);
  if (reads.some((r) => r.state === 'several')) return { state: 'several', values: [] };
  const said = [...new Map(reads.filter((r) => r.state === 'one').map((r) => [JSON.stringify(r.value), r.value])).values()];
  return said.length === 1 ? { state: 'one', value: said[0] } : said.length ? { state: 'several', values: said } : { state: 'empty' };
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
function recordRead(row, key, picks, slot, recordKey, marked) {
  if (!slot) return undefined;
  const raw = row.raw && row.raw[key];
  const records = row.raw && row.raw[recordKey];
  if (!raw || !records || raw.length !== records.length) return row.reads[key];
  const items = picks.map((k) => raw[k]);
  if (slot.reduce) { const value = foldRows(slot, [items], marked); return value === null || value === undefined ? { state: 'empty' } : { state: 'one', value }; }
  const said = [...new Map(items.map((r) => [JSON.stringify(r.value), r.value])).values()];
  return said.length === 1 ? { state: 'one', value: said[0] } : { state: 'several', values: said };
}
