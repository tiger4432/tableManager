// A table read in the order its rows were entered, and the places people drag them to (owner 11-06, lead ①②④): a
// table that declares "order": "entered" is read by the sort name `entered`; a drag writes ONE row of the shipped
// `sys_looks` - the moved thing's first row_id and its place, a text between its neighbours' order keys
// (server/grid_order.py reads it). A place is made of digits after a neighbour's own characters: it never parts from a
// row id at a «-», so it sorts the same under any collation that sorts uuid7 text by arrival (inferred, not measured).

export const ENTERED = 'entered';
export const LOOK_TABLE = 'sys_looks';
export const ROW = 'row';
export const GROUP = 'group';
export const ITEM = 'item';

/** A drop whose neighbour on one side is on another page - its place cannot be said from this one. */
export const PLACE_OFF_PAGE_NOTE = 'Drop it between two rows of this page';
/** Two neighbours whose keys do not stand in order - the read is stale. */
export const PLACE_STALE_NOTE = 'The order changed - reload and drag again';

/** A text strictly between `before` and `after` (either null: the start or the end) - `before` < `after` as JS compares
 *  them. Not after a neighbour that is a prefix of the other, it is `before` + «8»; else the first digit under the
 *  other's next character, or that character and on. Never ends in «0», so there is always room under it. */
export function placeBetween(before, after) {
  const low = before || '';
  if (after == null) return `${low}8`;
  if (!(low < after)) return null;
  if (!after.startsWith(low)) return `${low}8`;
  const rest = after.slice(low.length);
  const code = rest.charCodeAt(0);
  if (code > 0x31) return low + String.fromCharCode(Math.max(0x31, (0x30 + code) >> 1));
  if (code === 0x31) return `${low}08`;
  const deeper = placeBetween('', rest.slice(1));
  return deeper === null ? null : low + rest[0] + deeper;
}

/**
 * The place a drop gives: `keys` the order keys as shown (the moved one included), `from` its index, `to` the index it
 * lands on; `openStart` / `openEnd` - whether a row comes before the first shown / after the last shown (another page).
 * -> {place} | {refused} | null (no move).
 */
export function dropPlace(keys, from, to, { openStart = false, openEnd = false } = {}) {
  if (from === to || to < 0 || to >= keys.length) return null;
  const rest = keys.filter((_, i) => i !== from);
  const at = to;                                   // the moved one's index once it is there
  const before = at > 0 ? rest[at - 1] : null;
  const after = at < rest.length ? rest[at] : null;
  if ((before === null && openStart) || (after === null && openEnd)) return { refused: PLACE_OFF_PAGE_NOTE };
  const place = placeBetween(before, after);
  return place === null ? { refused: PLACE_STALE_NOTE } : { place };
}

/** The write of one look row (a place, a rule, a paint) - one update of PUT /tables/sys_looks/data/updates. */
export function lookUpdate(table, axis, key, cells, by) {
  return { updates: { look_table: table, look_axis: axis, look_key: key, ...cells }, source_name: 'user', updated_by: by };
}

/** The write of a place. */
export const placeUpdate = (table, axis, first, position, by) => lookUpdate(table, axis, first, { position }, by);

/** A broadcast item's cell value. */
export const cellOf = (item, col) => { const c = item && item.data && item.data[col]; return c && typeof c === 'object' ? c.value : c; };
/** A place as this screen remembers writing it. */
export const placeWord = (first, position) => `${first} ${position}`;

/** Whether a sys_looks broadcast says a place on `table` this screen did not just write itself (`written`: its
 *  `placeWord`s) - a message without items (a count) may. */
export function placesOn(msg, table, written = new Set()) {
  const items = msg && Array.isArray(msg.items) ? msg.items : [];
  if (!items.length) return true;
  const ours = items.filter((item) => cellOf(item, 'look_table') === table && [ROW, GROUP, ITEM].includes(cellOf(item, 'look_axis')));
  return ours.some((item) => !written.has(placeWord(cellOf(item, 'look_key'), cellOf(item, 'position'))));
}
