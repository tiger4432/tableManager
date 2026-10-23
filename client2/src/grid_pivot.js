// The main grid's pivot (owner 10-22, lead ㄱ ①): a long table read as one row per key group and one column per item -
// the server's answer (`?pivot=true`) laid in the grid's own row shape. An item's column is named as the server names
// its filter and its sort («item:<value>»), so the grid's filter, sort, count and pages go through their own doors.

import { isBlank } from './absent.js';

export const ITEM_PREFIX = 'item:';
export const itemColId = (name) => `${ITEM_PREFIX}${name}`;
/** The item an item column holds, else null. */
export const itemOf = (colId) => (typeof colId === 'string' && colId.startsWith(ITEM_PREFIX) ? colId.slice(ITEM_PREFIX.length) : null);

/** A paste, fill or clear reaching a key column in pivot view - refused whole (lead 10-22 ②): a key is every long row's. */
export const PIVOT_KEY_NOTE = 'Key columns cannot be changed in pivot view';
/** A value written on a new row while one of its keys is blank - refused: it would make a long row without that key. */
export const PIVOT_NEW_KEYS_NOTE = 'Fill every key column of the new row first';

/** A row added in pivot view (owner 10-23): on the screen only - its keys are typed on it, and its first value written
 *  makes its long rows. Saved, the page read again shows it as the server's group. */
const NEW_ROW_PREFIX = 'pivot:new:';
export const isNewPivotRow = (rowId) => typeof rowId === 'string' && rowId.startsWith(NEW_ROW_PREFIX);
export const newPivotRows = (count, now = Date.now()) => Array.from({ length: count }, (_, i) => ({ row_id: `${NEW_ROW_PREFIX}${now}-${i}`, data: {} }));

/** The key columns a write reaches, of the grid's updates ({updates} each) - none but item columns may be written. */
export const keyColumnsIn = (items) => [...new Set(items.flatMap((item) => Object.keys(item.updates || {}))
  .filter((col) => itemOf(col) === null))];

const valueOf = (cell) => (cell && typeof cell === 'object' ? cell.value : cell);

const isFresh = (item) => isNewPivotRow(item.rowNode.data.row_id);

/** The line a pivot write is refused with, '' when it goes (owner 10-23). A key cell of a saved group refuses it whole;
 *  on a new row the key cells are its own, and a value there while a key is still blank - counting the keys this write
 *  brings - refuses it. Items are {rowNode, updates}. */
export function pivotWriteRefusal(view, items) {
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

/** The columns a pivot view shows: its keys, then its items. Before its first answer, the declaration's keys. */
export function pivotColumns(view, pivot, keySources) {
  if (view) return [...view.keys, ...view.items.map(itemColId)];
  return (keySources || []).filter((key) => key !== pivot.column);
}

/** The answer's key groups as grid rows: a group's keys and its cells, each cell carrying the long row it is. */
export function pivotRows(answer) {
  const view = answer.pivot;
  return (answer.data || []).map((group) => {
    const data = {};
    for (const key of view.keys) data[key] = { value: group[key] };
    for (const [item, cell] of Object.entries(group.cells || {})) data[itemColId(item)] = { value: cell.value, row_id: cell.row_id };
    return { row_id: `pivot:${JSON.stringify(view.keys.map((key) => group[key]))}`, data };
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
