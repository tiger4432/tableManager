// The main grid's pivot (owner 10-22, lead ㄱ ①): a long table read as one row per key group and one column per item -
// the server's answer (`?pivot=true`) laid in the grid's own row shape. An item's column is named as the server names
// its filter and its sort («item:<value>»), so the grid's filter, sort, count and pages go through their own doors.

export const ITEM_PREFIX = 'item:';
export const itemColId = (name) => `${ITEM_PREFIX}${name}`;
/** The item an item column holds, else null. */
export const itemOf = (colId) => (typeof colId === 'string' && colId.startsWith(ITEM_PREFIX) ? colId.slice(ITEM_PREFIX.length) : null);

/** A row added or deleted, or rows pasted in as a table, in pivot view - a group is no row of the table. */
export const PIVOT_ROWS_NOTE = 'Rows are added and deleted with Pivot off';
/** A paste, fill or clear reaching a key column in pivot view - refused whole (lead 10-22 ②): a key is every long row's. */
export const PIVOT_KEY_NOTE = 'Key columns cannot be changed in pivot view';

/** The key columns a write reaches, of the grid's updates ({updates} each) - none but item columns may be written. */
export const keyColumnsIn = (items) => [...new Set(items.flatMap((item) => Object.keys(item.updates || {}))
  .filter((col) => itemOf(col) === null))];

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
