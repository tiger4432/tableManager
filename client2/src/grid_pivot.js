// The main grid's pivot (owner 10-22, lead ㄱ ①): a long table read as one row per key group and one column per item -
// the server's answer (`?pivot=true`) laid in the grid's own row shape. An item's column is named as the server names
// its filter and its sort («item:<value>»), so the grid's filter, sort, count and pages go through their own doors.

import { isBlank } from './absent.js';

export const ITEM_PREFIX = 'item:';
export const itemColId = (name) => `${ITEM_PREFIX}${name}`;
/** The item an item column holds, else null. */
export const itemOf = (colId) => (typeof colId === 'string' && colId.startsWith(ITEM_PREFIX) ? colId.slice(ITEM_PREFIX.length) : null);
/** A column's header word: an item column its item, any other its name in capitals. */
export const headerWord = (colId) => itemOf(colId) ?? String(colId).toUpperCase();

/** A paste, fill or clear reaching a key column in pivot view - refused whole (lead 10-22 ②): a key is every long row's. */
export const PIVOT_KEY_NOTE = 'Key columns cannot be changed in pivot view';
/** A value written on a new row while one of its keys is blank - refused: it would make a long row without that key. */
export const PIVOT_NEW_KEYS_NOTE = 'Fill every key column of the new row first';

/** A row added in pivot view (owner 10-23): on the screen only - its keys are typed on it, and its first value written
 *  makes its long rows. Saved, the page read again shows it as the server's group. */
const NEW_ROW_PREFIX = 'pivot:new:';
export const isNewPivotRow = (rowId) => typeof rowId === 'string' && rowId.startsWith(NEW_ROW_PREFIX);
export const newPivotRows = (count, now = Date.now()) => Array.from({ length: count }, (_, i) => ({ row_id: `${NEW_ROW_PREFIX}${now}-${i}`, data: {} }));

/** An item added in pivot view (owner 11-11 «피벗 상태에서 다이렉트로 아이템 추가»): its column on the screen alone, like a
 *  new row - the first value written under it makes its long row, as any blank cell's does (`pivotUpdate`). {view, item,
 *  refusal}: a blank name, or an item the view already shows, is refused and the view kept. */
export const PIVOT_ITEM_BLANK_NOTE = 'Name the item';
export function withItem(view, name) {
  const item = String(name == null ? '' : name).trim();
  if (!item) return { view, item, refusal: PIVOT_ITEM_BLANK_NOTE };
  if (view.items.includes(item)) return { view, item, refusal: `«${item}» is already an item` };
  return { view: { ...view, items: [...view.items, item] }, item, refusal: '' };
}

/** A paste, fill or clear reaching a carried column in pivot view - refused whole (owner 11-06): its value is its long
 *  rows', one or «N values». */
export const PIVOT_CARRY_NOTE = 'Carried columns cannot be changed in pivot view';

/** The columns a pivot row carries read-only (owner 11-06 `carry`): the answer's, before it the declaration's. */
export const carryColumns = (view, pivot) => (view && view.carry) || (pivot && pivot.carry) || [];

/** «N values» - a carried cell whose long rows hold more than one value; '' for one (or none). */
export const carryText = (cell) => (cell && cell.values ? `${cell.values} values` : '');

/** The key columns a write reaches, of the grid's updates ({updates} each) - none but item columns may be written. */
export const keyColumnsIn = (items) => [...new Set(items.flatMap((item) => Object.keys(item.updates || {}))
  .filter((col) => itemOf(col) === null))];

const valueOf = (cell) => (cell && typeof cell === 'object' ? cell.value : cell);

const isFresh = (item) => isNewPivotRow(item.rowNode.data.row_id);

/** The line a pivot write is refused with, '' when it goes (owner 10-23). A key cell of a saved group refuses it whole;
 *  on a new row the key cells are its own, and a value there while a key is still blank - counting the keys this write
 *  brings - refuses it. Items are {rowNode, updates}. */
export function pivotWriteRefusal(view, items) {
  const carried = carryColumns(view);
  if (items.some((item) => Object.keys(item.updates || {}).some((col) => carried.includes(col)))) return PIVOT_CARRY_NOTE;
  if (keyColumnsIn(items.filter((item) => !isFresh(item))).length) return PIVOT_KEY_NOTE;
  const keysOf = (item) => view.keys.map((key) => (key in item.updates ? item.updates[key] : valueOf((item.rowNode.data.data || {})[key])));
  const blankKey = items.filter(isFresh)
    .some((item) => Object.keys(item.updates).some((col) => itemOf(col) !== null) && keysOf(item).some(isBlank));
  return blankKey ? PIVOT_NEW_KEYS_NOTE : '';
}

/** A new row's key cells moved out of the write onto the row - they are not written, its values carry them. True when
 *  any moved. */
export function holdNewRowKeys(view, items) {
  let moved = false;
  for (const item of items.filter(isFresh)) {
    for (const key of view.keys.filter((col) => col in item.updates)) {
      const data = item.rowNode.data.data || (item.rowNode.data.data = {});
      data[key] = { ...(data[key] || {}), value: item.updates[key] };
      delete item.updates[key];
      moved = true;
    }
  }
  return moved;
}

/** The long table's filters that read one group's rows - each key equal, a blank key blank (owner 10-23: a group deleted
 *  takes every long row of its keys, items not shown included). */
export function groupFilters(view, rowData) {
  return Object.fromEntries(view.keys.map((key) => {
    const v = valueOf((rowData.data || {})[key]);
    return [key, isBlank(v) ? { type: 'blank' } : { type: 'equals', filter: v }];
  }));
}

/** The first long row a group's read brought whose key is not the group's - {key, want, got}, else null. A read that did
 *  not narrow by a key brings the whole table (lead 10-23: a delete stops on it). */
export function strayLongRow(view, rowData, rows) {
  const same = (a, b) => (isBlank(a) && isBlank(b)) || String(a) === String(b);
  for (const row of rows) {
    for (const key of view.keys) {
      const want = valueOf((rowData.data || {})[key]);
      const got = valueOf((row.data || {})[key]);
      if (!same(want, got)) return { key, want, got };
    }
  }
  return null;
}

/** The grid's updates as the server takes them (lead 10-22 ②): with a pivot view, a group's update becomes one update per
 *  item cell - its long row's, or a blank cell's keys and item. Without one (null), the updates as they are.
 *  @param {(rowId: string) => any} rowOf the grid row a group id is */
export function pivotWire(view, updates, rowOf) {
  if (!view) return updates;
  return updates.flatMap(({ row_id: rowId, updates: cells, ...rest }) => Object.entries(cells)
    .map(([colId, value]) => ({ ...rest, ...pivotUpdate(view, rowOf(rowId), colId, value) })));
}

const longIdOf = (rowData, colId) => {
  const cell = rowData && rowData.data && rowData.data[colId];
  return cell && cell.row_id ? cell.row_id : null;
};

/** The rows Apply reads again for the staged edits (pendingTxEdits' values): each edit's row - with a pivot view the
 *  long row its cell is, a blank cell none (lead 10-23 ㄱ: a group id is no row of the table). */
export function stagedReadIds(view, edits, rowOf) {
  if (!view) return [...new Set(edits.map((edit) => edit.rowId))];
  return [...new Set(edits.map((edit) => longIdOf(rowOf(edit.rowId), edit.colId)).filter(Boolean))];
}

/** Apply's read again as grid rows, and the keys of the staged edits whose row it no longer finds. With a pivot view a
 *  group comes back as the grid holds it, each staged cell at its long row's value - an edit is dropped only when its
 *  own long row is gone. */
export function stagedReadRows(view, staged, rowOf, read) {
  const found = new Map(read.map((row) => [row.row_id, row]));
  const entries = Object.entries(staged);
  if (!view) return { rows: read, gone: entries.filter(([, edit]) => !found.has(edit.rowId)).map(([key]) => key) };
  const groups = new Map();
  const gone = [];
  for (const [key, edit] of entries) {
    const held = rowOf(edit.rowId);
    const id = longIdOf(held, edit.colId);
    if (!id) continue;
    const long = found.get(id);
    if (!long) { gone.push(key); continue; }
    const group = groups.get(edit.rowId) || { ...held, data: { ...held.data } };
    const cell = long.data && long.data[view.value];
    if (cell) group.data[edit.colId] = { ...group.data[edit.colId], value: cell.value };
    groups.set(edit.rowId, group);
  }
  return { rows: [...groups.values()], gone };
}

/** The declaration's keys: the table's key columns less the item column. */
const pivotKeys = (pivot, keySources) => (keySources || []).filter((key) => key !== pivot.column);

/** The columns a pivot view has: its keys, its carried columns (owner 11-06), then its items - before its first answer,
 *  the declaration's keys and carry - and last the item column, held hidden so a filter on it stays in the grid's model
 *  and its chip (owner 11-05 ㄴ). */
export function pivotColumns(view, pivot, keySources) {
  const carry = carryColumns(view, pivot);
  return [...(view ? [...view.keys, ...carry, ...view.items.map(itemColId)] : [...pivotKeys(pivot, keySources), ...carry]),
    pivot.column];
}

/** The filter of the item column a pivot view holds hidden: the server reads it on the long rows, so every group row
 *  passes here - the grid filters the rows it holds by its column filters, and a group row has no item column value.
 *  Its model is kept as it was set (a text or number filter's) for the chip and the read. */
export class HeldColumnFilter {
  init() { this.model = null; }
  getGui() { return document.createElement('div'); }
  isFilterActive() { return this.model != null; }
  doesFilterPass() { return true; }
  getModel() { return this.model; }
  setModel(model) { this.model = model || null; }
}

/** A switch between the long view and the pivot (owner 11-05 ㄴ · ㄱ, both ways): the key, carried (owner 11-11 ㄴ) and
 *  item column filters are kept - the server reads them in either view - and the rest dropped (the value column's, an
 *  item's «item:<v>»). */
export function carriedFilters(model, pivot, keySources) {
  const kept = [...pivotKeys(pivot, keySources), ...carryColumns(null, pivot), pivot.column];
  const keep = {};
  const dropped = [];
  for (const [col, filter] of Object.entries(model || {})) {
    if (kept.includes(col)) keep[col] = filter;
    else dropped.push(col);
  }
  return { keep, dropped };
}

/** The answer's key groups as grid rows: a group's keys and its cells, each cell carrying the long row it is. */
export function pivotRows(answer) {
  const view = answer.pivot;
  return (answer.data || []).map((group) => {
    const data = {};
    for (const key of view.keys) data[key] = { value: group[key] };
    // a carried cell: its one value, or none and how many (copied blank - lead 11-06)
    for (const [col, cell] of Object.entries(group.carry || {})) {
      data[col] = cell.values ? { value: null, values: cell.values } : { value: cell.value };
    }
    for (const [item, cell] of Object.entries(group.cells || {})) {
      // its writer when a colour rule asked (server/grid_look.py)
      data[itemColId(item)] = { value: cell.value, row_id: cell.row_id, ...('written_by' in cell ? { written_by: cell.written_by } : {}) };
    }
    const row = { row_id: `pivot:${JSON.stringify(view.keys.map((key) => group[key]))}`, data };
    // read in entered order (owner 11-06): its first long row - what its place is written on - and its order key
    return group.order_key ? { ...row, first: group.first, order_key: group.order_key } : row;
  });
}

/** One cell's write (one update of PUT /data/updates): its own row's value - a blank cell, its keys and its item, which
 *  makes the row. */
export function pivotUpdate(view, rowData, colId, value) {
  const cell = rowData.data[colId];
  if (cell && cell.row_id) return { row_id: cell.row_id, updates: { [view.value]: value } };
  const updates = {};
  for (const key of view.keys) updates[key] = rowData.data[key] ? rowData.data[key].value : null;
  updates[view.column] = itemOf(colId);
  updates[view.value] = value;
  return { updates };
}

/** Whether a table was last shown pivoted, per table in this browser (owner 10-22) - false where nothing can be kept. */
export function rememberedPivot(storage, table) {
  try { return Boolean(storage) && storage.getItem(`grid-pivot:${table}`) === 'on'; } catch (e) { return false; }
}
export function rememberPivot(storage, table, on) {
  try {
    if (!storage) return;
    if (on) storage.setItem(`grid-pivot:${table}`, 'on');
    else storage.removeItem(`grid-pivot:${table}`);
  } catch (e) { /* not kept - the next visit starts unpivoted */ }
}
