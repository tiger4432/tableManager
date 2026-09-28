// THE COLUMN SAVE — owner 09-28 「고른 칸만 고쳐쓰기」 (lead 40bae1219). Only the chosen value
// column's CHANGED cells go out, through the grid's own write door (PUT /tables/<t>/data/updates)
// and never with `replace_map` — so the row's other columns, its corrections, layers and history
// stay where they are, and the chain and history see what a grid edit makes them see.
//
// KEEP IT A LEAF: it imports nothing, so its harness can build the «send every cell» mutant from
// this file's text as a `data:` URL (the `push_columns.js` rule).

const text = (v) => (v === null || v === undefined ? '' : String(v).trim());
// The load reads a coordinate with parseInt and skips what does not parse; the same reading here.
const coord = (v) => { const n = parseInt(v, 10); return Number.isNaN(n) ? text(v) : String(n); };

/** One spelling of a stored coordinate for both sides of the comparison. */
export function coordKey(x, y) {
  return `${coord(x)}|${coord(y)}`;
}

/**
 * A painted cell has no row yet. The server gives it one by the table's declared key
 * (`composite_key_source`); a key that names neither x nor y would land every painted cell of the
 * map on ONE row. Painting is safe when the table declares no such key or its key holds both.
 */
export function paintIsSafe(schema, xCol, yCol) {
  const key = Array.isArray(schema?.composite_key_source) ? schema.composite_key_source : [];
  return key.length === 0 || (key.includes(xCol) && key.includes(yCol));
}

/**
 * baseline  Map coordKey -> the value read at load ('' = empty)
 * current   Map coordKey -> the value on screen now (inside cells, '' = empty)
 * rows      the map's rows read again just before the write: [{ row_id, data: { col: { value } } }]
 * Returns { refusal, cells } when the save must not go out, else
 *         { updates, written: [coordKey], edited, painted, cleared, conflicts: [coordKey] }.
 * Conflicts are cells whose stored value is no longer the one read at load — never overwritten.
 */
export function planColumnSave({ baseline, current, rows, xCol, yCol, valCol, types = {},
  keyValues = {}, paintAllowed = true, author = 'system' }) {
  const typed = (col, v) => ((types[col] || 'string') === 'number' ? Number(v) : v);
  const cleared = (col) => ((types[col] || 'string') === 'number' ? null : '');

  const byCell = new Map();
  for (const row of rows || []) {
    const d = row.data || {};
    const k = coordKey(d[xCol]?.value, d[yCol]?.value);
    if (!byCell.has(k)) byCell.set(k, []);
    byCell.get(k).push(row);
  }

  // A coordinate read at load but not on screen now is not an edit.
  const changed = [];
  for (const [k, now] of current) {
    const was = baseline.get(k) ?? '';
    if (now !== was) changed.push({ k, was, now });
  }

  const doubled = changed.filter(({ k }) => (byCell.get(k) || []).length > 1).map(({ k }) => k);
  if (doubled.length) return { refusal: 'doubled', cells: doubled };
  const painted = changed.filter(({ k, was, now }) => !byCell.has(k) && was === '' && now !== '')
    .map(({ k }) => k);
  if (painted.length && !paintAllowed) return { refusal: 'paint', cells: painted };

  const out = { updates: [], written: [], edited: 0, painted: 0, cleared: 0, conflicts: [] };
  for (const { k, was, now } of changed) {
    const row = (byCell.get(k) || [])[0];
    if (text(row ? row.data?.[valCol]?.value : '') !== was) { out.conflicts.push(k); continue; }
    const item = { source_name: 'user', updated_by: author };
    if (row) {
      item.row_id = row.row_id;
      item.updates = { [valCol]: now === '' ? cleared(valCol) : typed(valCol, now) };
      out[now === '' ? 'cleared' : 'edited'] += 1;
    } else {
      const [x, y] = k.split('|');
      item.updates = { ...keyValues, [xCol]: typed(xCol, x), [yCol]: typed(yCol, y), [valCol]: typed(valCol, now) };
      out.painted += 1;
    }
    out.updates.push(item);
    out.written.push(k);
  }
  return out;
}
