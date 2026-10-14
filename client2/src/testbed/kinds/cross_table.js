// The cross table kind - its visible area only (ROOT_PART_BASE_SET: the root is the template): a row axis, a column axis,
// the cell values folded over the rows each cell holds, grand totals. A cell - and a row or column head - is a hub of its
// rows, given back whole; its paint (marked, Color by) is the root's.

import { combosOf, slotWords, foldRows, EMPTY, PART_SEP } from '../slot.js';

/** What a cell holds with no cell slot: its rows, each once (owner 10-14 «ㅇㅇ 행수») - said as the fold it is. */
export const ROWS_COUNT = 'UniqueCount(rows)';

export const SLOTS = Object.freeze([
  { key: 'rows', label: 'Row axis', category: true, tray: 'left', many: true },
  { key: 'columns', label: 'Column axis', category: true, tray: 'top', plus: true, many: true },
  { key: 'cells', label: 'Cell values', folds: true, tray: 'bottom', plus: true, empty: ROWS_COUNT },
]);
export { EMPTY };
const TOTAL = 'Total';

/** A cell's number as the table says it: thousands grouped, at most three decimals. */
export const cellWords = (v) => (v === null || v === undefined ? '-'
  : typeof v === 'number' ? v.toLocaleString('en-US', { maximumFractionDigits: 3 }) : String(v));

/**
 * @param {Array<{id, reads: object, raw: object}>} rows  `raw.cells` - what the cell slot keeps of the row (slot.js rawOf)
 * @param {{marked: (id) => boolean, declaration?: object}} ctx  the declaration's cell slot: its reduce (none - Count) or its expression
 */
export function crossModel(rows, ctx) {
  const cellSlot = ((ctx.declaration && ctx.declaration.encode) || {}).cells;
  const cells = new Map();
  const keyOf = (r, c) => `${r}\u0000${c}`;
  const rowKeys = new Set();
  const colKeys = new Set();
  // A row with two values on an axis stands in both (lead aca803a7a «counts twice»); none - (Empty).
  for (const { values: [r, c], ids } of combosOf(rows, ['rows', 'columns'])) {
    rowKeys.add(r);
    colKeys.add(c);
    cells.set(keyOf(r, c), { ids });
  }
  // a cell holds rows (a mark its row's - units.js marksOf; a row's marks fold its cell values once)
  const byId = new Map(rows.map((row) => [row.row || row.id, row]));
  /** A set of rows folded: the cell slot's values of each row once (a row in two columns counts once in its row's total). */
  const folded = (ids) => {
    const once = [...new Set(ids)];
    if (!rows.some((row) => row.raw && row.raw.cells)) return once.length;
    return foldRows(cellSlot, once.map((id) => byId.get(id).raw.cells), ctx.askMarked);
  };
  // An axis of several columns - its keys' values column by column (slot.js readSlot `parts`), sorted level by level,
  // (Empty) last in each; one column - each key itself.
  const partsOf = new Map();
  for (const row of rows) {
    for (const key of ['rows', 'columns']) {
      const read = row.reads[key];
      if (!read || !read.parts) continue;
      if (read.state === 'one') partsOf.set(read.value, read.parts);
      else read.values.forEach((v, k) => partsOf.set(v, read.parts[k]));
    }
  }
  const parts = (k) => partsOf.get(k) || [k];
  const level = (a, b) => (a === EMPTY) - (b === EMPTY) || (a < b ? -1 : a > b ? 1 : 0);
  const sort = (keys) => [...keys].sort((a, b) => { const [p, q] = [parts(a), parts(b)]; for (let i = 0; i < Math.max(p.length, q.length); i += 1) { const d = level(p[i] || '', q[i] || ''); if (d) return d; } return 0; });
  const enc = (ctx.declaration && ctx.declaration.encode) || {};
  const R = sort(rowKeys);
  const C = sort(colKeys);
  const grid = R.map((r) => C.map((c) => {
    const cell = cells.get(keyOf(r, c));
    if (!cell) return { value: null, ids: [], marked: false };
    // its paint is the root's: marked, and its rows' Color by colour when one is declared
    const p = ctx.paint(cell.ids, [[slotWords(enc.rows), r], [slotWords(enc.columns), c]]);
    return { value: folded(cell.ids), ids: cell.ids, marked: p.marked, color: ctx.colored ? p.color : null };
  }));
  const rowIds = R.map((_, i) => grid[i].flatMap((cell) => cell.ids));
  const colIds = C.map((_, j) => grid.flatMap((line) => line[j].ids));
  return {
    rowKeys: R, colKeys: C, rowParts: R.map(parts), colParts: C.map(parts), grid,
    rowTotals: rowIds.map(folded), colTotals: colIds.map(folded), total: folded(rows.map((row) => row.row || row.id)),
    rowIds, colIds,
  };
}

/** Draw a model into the template's area: the table scrolls inside its own box (mockup fix ①). A cell, a row head or a
 *  column head gives back its hub through `ctx.markHub`. */
export function render(area, model, ctx) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const wrap = el('div', 'tb-cross__wrap');
  const table = el('table', 'sf-table');
  const words = { rows: ctx.words('rows'), columns: ctx.words('columns') };
  // An axis of several columns is a hierarchy (Spotfire's): a head a level, an outer value the same along its run told
  // once (colspan / rowspan), the inner one each time; a head pressed marks the rows under it.
  const rowParts = model.rowParts || model.rowKeys.map((k) => [k]);
  const colParts = model.colParts || model.colKeys.map((k) => [k]);
  const rowLevels = Math.max(1, ...rowParts.map((p) => p.length));
  const colLevels = Math.max(1, ...colParts.map((p) => p.length));
  const runs = (list, lv) => { const out = []; list.forEach((p, k) => { const at = p.slice(0, lv + 1).join(PART_SEP); const last = out[out.length - 1];
    if (last && last.at === at) last.n += 1; else out.push({ at, word: p[lv] === undefined ? '' : p[lv], from: k, n: 1 }); }); return out; };
  for (let lv = 0; lv < colLevels; lv += 1) {
    const head = el('tr');
    if (lv === 0) {
      const corner = el('th', 'sf-table__corner', words.rows);
      corner.colSpan = rowLevels;
      corner.rowSpan = colLevels;
      head.append(corner);
    }
    for (const run of runs(colParts, lv)) {
      const th = el('th', 'sf-table__col', run.word);
      th.colSpan = run.n;
      const ids = model.colIds.slice(run.from, run.from + run.n).flat();
      th.addEventListener('click', (event) => ctx.markHub([[words.columns, run.at]], ids, event));
      head.append(th);
    }
    if (lv === 0) { const total = el('th', 'sf-table__col sf-table__total', TOTAL); total.rowSpan = colLevels; head.append(total); }
    table.append(head);
  }
  const rowRuns = Array.from({ length: rowLevels }, (_, lv) => new Map(runs(rowParts, lv).map((run) => [run.from, run])));
  model.rowKeys.forEach((r, i) => {
    const tr = el('tr');
    for (let lv = 0; lv < rowLevels; lv += 1) {
      const run = rowRuns[lv].get(i);
      if (!run) continue;
      const th = el('th', lv === 0 ? 'sf-table__row' : 'sf-table__row sf-table__row--in', run.word);
      th.rowSpan = run.n;
      const ids = model.rowIds.slice(run.from, run.from + run.n).flat();
      th.addEventListener('click', (event) => ctx.markHub([[words.rows, run.at]], ids, event));
      tr.append(th);
    }
    model.grid[i].forEach((cell, j) => {
      const td = el('td', cell.marked ? 'is-marked' : '', cellWords(cell.value));
      if (cell.color && !cell.marked) td.style.background = cell.color;
      if (cell.ids.length) {
        td.addEventListener('click', (event) => ctx.markHub([[words.rows, r], [words.columns, model.colKeys[j]]], cell.ids, event));
        td.addEventListener('mousemove', (event) => ctx.hover({ ids: cell.ids, label: model.colKeys[j] ? `${r} · ${model.colKeys[j]}` : r }, event));
        td.addEventListener('mouseleave', () => ctx.hover(null));
      }
      tr.append(td);
    });
    tr.append(el('td', 'sf-table__total', cellWords(model.rowTotals[i])));
    table.append(tr);
  });
  const foot = el('tr', 'sf-table__totals');
  const totalHead = el('th', 'sf-table__row', TOTAL);
  totalHead.colSpan = rowLevels;
  foot.append(totalHead);
  model.colTotals.forEach((v) => foot.append(el('td', 'sf-table__total', cellWords(v))));
  foot.append(el('td', 'sf-table__total', cellWords(model.total)));
  table.append(foot);
  wrap.append(table);
  area.replaceChildren(wrap);
  return { resize: () => {}, dispose: () => {} };
}

/** The title when the declaration names none - «Avg(press) per lot and product», no cell slot «UniqueCount(rows)». */
export const title = (encode) => `${encode.cells ? slotWords(encode.cells) : ROWS_COUNT} per ${slotWords(encode.rows)} and ${slotWords(encode.columns)}`;

/** The add window's picture of it: a head, a row head, cells. */
export const icon = { tone: 'cat-7', paths: [['M4 3h16v4H4zM4 9h4v12H4z', 1], ['M10 9h4v5h-4zM16 9h4v5h-4zM10 16h4v5h-4zM16 16h4v5h-4z', 0.6]] };

export const kind = { name: 'crossTable', label: 'Cross table', slots: SLOTS, title, model: crossModel, render, icon };
