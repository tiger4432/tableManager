// One batch on the page: the items it shows that this run has not read yet. Columns based on the item are read before it
// is opened; when the key is all of them, an item whose key the table already has is skipped unopened. An item is opened
// only when a column is based on the content area.
import { readColumns } from './extract.js';

export const MISS = Object.freeze({ NO_KEY: 'no_key', NOT_OPENED: 'not_opened', REFUSED: 'refused' });

/** A row's key - its key columns' values joined by «|» - or null when one has no value. */
export function keyOf(t, cells) {
  const parts = t.keys.map((c) => cells[c]);
  return parts.some((v) => v === null || v === undefined) ? null : parts.join('|');
}

/**
 * page      { items(most) -> handles not read yet (marked read), where() -> address, base(handle) -> item element,
 *             open(handle, fields) -> {opened, detail, cells?}, content() -> content element, close() }
 * existing  [cells] -> Set of the keys (keyOf) the table already has
 * -> { seen, read, skipped, rows: [{key, cells, at, index}], misses: [{reason, detail, at, index, cells}] } - seen: items taken
 *    from the page, read: of them the ones this run reads (a retry's `t.only`: the kept items)
 */
export async function readBatch(t, page, { room, existing, firstIndex = 0 }) {
  const before = t.fields.filter((f) => f.base === 'item');
  const after = t.fields.filter((f) => f.base === 'content');
  const keyBefore = t.keys.every((c) => before.some((f) => f.column === c));
  const at = page.where();
  const taken = page.items(room).map((h, i) => ({ h, index: firstIndex + i, cells: readColumns(page.base(h), before) }));
  // a retry reads only the kept items - known by the values read before opening
  const same = (a, b) => before.every((f) => (a[f.column] ?? null) === (b[f.column] ?? null));
  const listed = t.only ? taken.filter((x) => t.only.some((c) => same(c, x.cells))) : taken;
  const out = { seen: taken.length, read: listed.length, skipped: 0, rows: [], misses: [] };
  const known = keyBefore ? await existing(listed.map((x) => x.cells).filter((c) => keyOf(t, c) !== null)) : new Set();
  for (const x of listed) {
    if (keyBefore && known.has(keyOf(t, x.cells))) { out.skipped += 1; continue; }
    let cells = x.cells;
    if (after.length) {
      const o = await page.open(x.h, after);
      if (!o.opened) { out.misses.push({ reason: MISS.NOT_OPENED, detail: o.detail, at, index: x.index, cells }); continue; }
      cells = { ...cells, ...(o.cells || readColumns(page.content(), after)) };
      await page.close();
    }
    const key = keyOf(t, cells);
    if (key === null) { out.misses.push({ reason: MISS.NO_KEY, detail: `${t.keys.join(', ')} has no value`, at, index: x.index, cells }); continue; }
    out.rows.push({ key, cells, at, index: x.index });
  }
  if (!keyBefore && out.rows.length) {
    const had = await existing(out.rows.map((r) => r.cells));
    out.skipped += out.rows.filter((r) => had.has(r.key)).length;
    out.rows = out.rows.filter((r) => !had.has(r.key));
  }
  return out;
}
