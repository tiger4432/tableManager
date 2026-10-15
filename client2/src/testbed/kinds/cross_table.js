// The cross table kind - its visible area only (ROOT_PART_BASE_SET: the root is the template): a row axis, a column axis,
// the cell values folded over the rows each cell holds, grand totals. A cell - and a row or column head - is a hub of its
// rows, given back whole; its paint (marked, Color by) is the root's.

import { combosOf, slotWords, foldRows, EMPTY, PART_SEP, categoryCompare, columnsOf, foldKey, COLUMN_NAMES } from '../slot.js';

/** What a cell holds with no cell slot: its rows, each once (owner 10-14 «ㅇㅇ 행수») - said as the fold it is. */
export const ROWS_COUNT = 'UniqueCount(rows)';

export const SLOTS = Object.freeze([
  { key: 'rows', label: 'Row axis', category: true, tray: 'left', many: true, names: true },
  { key: 'columns', label: 'Column axis', category: true, tray: 'top', plus: true, many: true, names: true },
  { key: 'cells', label: 'Cell values', folds: true, tray: 'bottom', plus: true, many: true, empty: ROWS_COUNT },
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
  const enc = (ctx.declaration && ctx.declaration.encode) || {};
  // the cell values (owner 10-15 «Cell values 여러 개»): each folded on its own (slot.js foldKey); none - the rows counted
  const measures = columnsOf(enc.cells);
  const M = Math.max(1, measures.length);
  const own = (key) => columnsOf(enc[key]).filter((c) => !c.names).length > 0;
  // where the values stand - «(Column Names)» on an axis, at its level; two values or more put nowhere: the column axis,
  // innermost (Spotfire's)
  const namesAt = (key) => columnsOf(enc[key]).findIndex((c) => c.names);
  const placed = ['rows', 'columns'].find((key) => namesAt(key) >= 0);
  const place = placed ? { key: placed, at: namesAt(placed) }
    : measures.length > 1 ? { key: 'columns', at: columnsOf(enc.columns).length } : null;
  const cells = new Map();
  const keyOf = (r, c) => `${r}\u0000${c}`;
  const rowKeys = new Set();
  const colKeys = new Set();
  // A row with two values on an axis stands in both (lead aca803a7a «counts twice»); none - (Empty); an axis of the
  // values' names alone reads no row
  for (const { values: [r0, c0], ids, marks } of combosOf(rows, ['rows', 'columns'])) {
    const [r, c] = [own('rows') ? r0 : '', own('columns') ? c0 : ''];
    rowKeys.add(r);
    colKeys.add(c);
    cells.set(keyOf(r, c), { ids, marks });
  }
  /** A set of marks folded on value `m` (lead 10-15 ②: in the cell, not in the row): each mark's own values of it - its
   *  record's (units.js marksOf), a row's once when its marks share them; no cell value - the rows. */
  const folded = (marks, m = 0) => {
    const k = foldKey('cells', m);
    if (!measures.length || !rows.some((row) => row.raw && row.raw[k])) return new Set(marks.map((x) => x.row || x.id)).size;
    return foldRows(measures[m], [...new Set(marks.map((x) => x.raw[k]))], ctx.askMarked);
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
  // each level in the one order of categories (slot.js categoryCompare - the axis's time from its scale)
  const sort = (keys, key) => {
    const level = categoryCompare(Boolean(ctx.scale && ctx.scale(key).time));
    return [...keys].sort((a, b) => { const [p, q] = [parts(a), parts(b)]; for (let i = 0; i < Math.max(p.length, q.length); i += 1) { const d = level(p[i] || '', q[i] || ''); if (d) return d; } return 0; });
  };
  const said = (m) => (measures[m] ? slotWords(measures[m]) : ROWS_COUNT);
  // an axis's lines: a key each - and on the values' axis a key a value, the values' level at its place in the hierarchy
  // (the levels outside it first, then the values, then the levels inside)
  const linesOf = (key, keys) => {
    const base = sort(keys, key).map((k) => ({ k, m: null, parts: own(key) ? parts(k) : (place && place.key === key ? [] : [k]) }));
    if (!place || place.key !== key) return base;
    const outer = (l) => l.parts.slice(0, place.at).join(PART_SEP);
    const groups = [];
    for (const l of base) { const g = groups[groups.length - 1]; if (g && g.at === outer(l)) g.lines.push(l); else groups.push({ at: outer(l), lines: [l] }); }
    return groups.flatMap((g) => Array.from({ length: M }, (_, m) => g.lines.map((l) => ({ k: l.k, m,
      parts: [...l.parts.slice(0, place.at), said(m), ...l.parts.slice(place.at)] }))).flat());
  };
  const R = linesOf('rows', rowKeys);
  const C = linesOf('columns', colKeys);
  const grid = R.map((r) => C.map((c) => {
    const cell = cells.get(keyOf(r.k, c.k));
    if (!cell) return { value: null, ids: [], marks: [], marked: false };
    // its paint is the root's: marked, and its rows' Color by colour when one is declared
    const p = ctx.paint(cell.ids, [[slotWords(enc.rows), r.k], [slotWords(enc.columns), c.k]]);
    return { value: folded(cell.marks, r.m ?? c.m ?? 0), ids: cell.ids, marks: cell.marks, marked: p.marked, color: ctx.colored ? p.color : null };
  }));
  // a total a value where the values stand across it (Spotfire's): a Total column a value when they are on the columns,
  // a Total row a value when on the rows; else one, on the line's own value
  const across = (key) => (place && place.key === key ? M : 0);
  const marksOfKey = (k, axis) => [...(axis === 'rows' ? colKeys : rowKeys)].flatMap((o) => (cells.get(axis === 'rows' ? keyOf(k, o) : keyOf(o, k)) || { marks: [] }).marks);
  const totalsOf = (line, axis, other) => (across(other)
    ? Array.from({ length: M }, (_, m) => folded(marksOfKey(line.k, axis), m)) : folded(marksOfKey(line.k, axis), line.m ?? 0));
  return {
    rowKeys: R.map((l) => l.k), colKeys: C.map((l) => l.k), rowParts: R.map((l) => l.parts), colParts: C.map((l) => l.parts), grid,
    rowMeasures: R.map((l) => l.m), colMeasures: C.map((l) => l.m), measures: Array.from({ length: M }, (_, m) => said(m)),
    valuesOn: place ? place.key : null,
    rowTotals: R.map((l) => totalsOf(l, 'rows', 'columns')), colTotals: C.map((l) => totalsOf(l, 'columns', 'rows')),
    total: place ? Array.from({ length: M }, (_, m) => folded(rows, m)) : folded(rows),
    rowIds: R.map((_, i) => grid[i].flatMap((cell) => cell.ids)), colIds: C.map((_, j) => grid.flatMap((line) => line[j].ids)),
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
  // a value as the slot says it (the root's one place - a slot of days its days); the hub keeps the value itself
  const said = (key, v) => (ctx.text && v !== '' && typeof v !== 'number' && v !== null && v !== undefined ? ctx.text(key, v) : v);
  const cellSaid = (v) => (ctx.text && typeof v === 'string' ? ctx.text('cells', v) : cellWords(v));
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
      const th = el('th', 'sf-table__col', said('columns', run.word));
      th.colSpan = run.n;
      const ids = model.colIds.slice(run.from, run.from + run.n).flat();
      th.addEventListener('click', (event) => ctx.markHub([[words.columns, run.at]], ids, event));
      head.append(th);
    }
    if (lv === 0) {
      // a Total column a value when the values stand on the columns (owner 10-15)
      for (const word of model.valuesOn === 'columns' ? model.measures.map((m) => `${TOTAL} · ${m}`) : [TOTAL]) {
        const total = el('th', 'sf-table__col sf-table__total', word);
        total.rowSpan = colLevels;
        head.append(total);
      }
    }
    table.append(head);
  }
  const rowRuns = Array.from({ length: rowLevels }, (_, lv) => new Map(runs(rowParts, lv).map((run) => [run.from, run])));
  model.rowKeys.forEach((r, i) => {
    const tr = el('tr');
    for (let lv = 0; lv < rowLevels; lv += 1) {
      const run = rowRuns[lv].get(i);
      if (!run) continue;
      const th = el('th', lv === 0 ? 'sf-table__row' : 'sf-table__row sf-table__row--in', said('rows', run.word));
      th.rowSpan = run.n;
      const ids = model.rowIds.slice(run.from, run.from + run.n).flat();
      th.addEventListener('click', (event) => ctx.markHub([[words.rows, run.at]], ids, event));
      tr.append(th);
    }
    model.grid[i].forEach((cell, j) => {
      const td = el('td', cell.marked ? 'is-marked' : '', cellSaid(cell.value));
      if (cell.color && !cell.marked) td.style.background = cell.color;
      if (cell.ids.length) {
        td.addEventListener('click', (event) => ctx.markHub([[words.rows, r], [words.columns, model.colKeys[j]]], cell.ids, event));
        td.addEventListener('mousemove', (event) => ctx.hover({ ids: cell.ids, label: model.colKeys[j] ? `${r} · ${model.colKeys[j]}` : r }, event));
        td.addEventListener('mouseleave', () => ctx.hover(null));
      }
      tr.append(td);
    });
    for (const v of [].concat(model.rowTotals[i])) tr.append(el('td', 'sf-table__total', cellSaid(v)));
    table.append(tr);
  });
  // a Total row a value when the values stand on the rows (owner 10-15), else one
  const onRows = model.valuesOn === 'rows';
  (onRows ? model.measures : [null]).forEach((m, k) => {
    const foot = el('tr', 'sf-table__totals');
    const totalHead = el('th', 'sf-table__row', m === null ? TOTAL : `${TOTAL} · ${m}`);
    totalHead.colSpan = rowLevels;
    foot.append(totalHead);
    model.colTotals.forEach((v) => foot.append(el('td', 'sf-table__total', cellSaid(onRows ? v[k] : v))));
    for (const v of onRows ? [[].concat(model.total)[k]] : [].concat(model.total)) foot.append(el('td', 'sf-table__total', cellSaid(v)));
    table.append(foot);
  });
  wrap.append(table);
  area.replaceChildren(wrap);
  return { resize: () => {}, dispose: () => {} };
}

/** The title when the declaration names none - «Avg(press) per lot and product», no cell slot «UniqueCount(rows)». */
export const title = (encode) => `${columnsOf(encode.cells).length ? columnsOf(encode.cells).map(slotWords).join(' · ') : ROWS_COUNT} per ${slotWords(encode.rows)} and ${slotWords(encode.columns)}`;

/** The add window's picture of it: a head, a row head, cells. */
export const icon = { tone: 'cat-7', paths: [['M4 3h16v4H4zM4 9h4v12H4z', 1], ['M10 9h4v5h-4zM16 9h4v5h-4zM10 16h4v5h-4zM16 16h4v5h-4z', 0.6]] };

export const kind = { name: 'crossTable', label: 'Cross table', slots: SLOTS, title, model: crossModel, render, icon };
