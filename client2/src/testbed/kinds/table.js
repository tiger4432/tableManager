// The table kind of the visual part (owner 10-13 «근원부품 table», Spotfire's Table): a line a row - the row type's nodes
// the root kept - and a column a slot, added with «+» (the axes' picker: the walk table's «+ Column» choice). A line
// pressed marks its node through the root (a press replaces, Ctrl adds); a press below the lines clears; a column head
// pressed sorts by it, again the other way. Its columns and its sort are its declaration's: encode.col1 … and `sort`.

import { numberOf, valueWords } from '../../walk/reach_table.js';
import { slotWords } from '../slot.js';

const COLUMN = /^col(\d+)$/;
const order = (key) => Number(COLUMN.exec(key)[1]);

/** The table's slots: one a column the declaration holds, in their order. */
export const slots = (encode) => Object.keys(encode || {}).filter((k) => COLUMN.test(k)).sort((a, b) => order(a) - order(b))
  .map((key) => ({ key, label: `Column ${order(key)}` }));

/** A read as a cell says it: one value, several joined (the walk table's words), nothing blank. */
function cellOf(read) {
  if (!read || read.state === 'empty' || read.state === 'missing') return { text: '', value: null };
  if (read.state === 'several') return { text: read.values.map(valueWords).join(' · '), value: read.values[0] };
  return { text: valueWords(read.value), value: read.value };
}

/** Two cells in a sort's order: numbers as numbers, the rest as text; a blank last either way. */
function compare(a, b) {
  if (a.value === null || b.value === null) return (a.value === null) - (b.value === null);
  const [x, y] = [numberOf(a.value), numberOf(b.value)];
  if (x !== null && y !== null) return x - y;
  return a.text < b.text ? -1 : a.text > b.text ? 1 : 0;
}

/**
 * @param {Array<{id, label, reads: object}>} rows
 * @param {{marked: (id) => boolean, declaration?: object}} ctx  the declaration's `sort` {key, desc}
 */
export function tableModel(rows, ctx) {
  const decl = ctx.declaration || {};
  const keys = slots(decl.encode).map((s) => s.key);
  let lines = rows.map((row) => ({ id: row.id, cells: keys.map((k) => cellOf(row.reads[k])), marked: ctx.marked(row.id) }));
  const sort = decl.sort && keys.includes(decl.sort.key) ? decl.sort : null;
  if (sort) {
    const at = keys.indexOf(sort.key);
    lines = lines.map((line, i) => [line, i]).sort(([p, i], [q, j]) => {
      const blank = (p.cells[at].value === null) - (q.cells[at].value === null);
      if (blank) return blank;
      return (sort.desc ? -1 : 1) * compare(p.cells[at], q.cells[at]) || i - j;
    }).map(([line]) => line);
  }
  // A column of numbers stands right, as Spotfire's.
  const numeric = keys.map((_, k) => {
    const said = lines.map((l) => l.cells[k].value).filter((v) => v !== null);
    return said.length > 0 && said.every((v) => numberOf(v) !== null);
  });
  const next = `col${keys.length ? Math.max(...keys.map(order)) + 1 : 1}`;
  return { keys, lines, sort, numeric, next };
}

/** Draw a model: the column heads (each sorts; «+» adds one), a line a row, the marked ones marked. */
export function render(body, model, ctx) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  body.className = 'sf-part__body tb-table';
  const wrap = el('div', 'tb-table__wrap');
  const table = el('table', 'sf-table sf-table--rows');
  const head = el('tr');
  model.keys.forEach((key, k) => {
    const on = model.sort && model.sort.key === key;
    const th = el('th', model.numeric[k] ? 'is-num' : '', ctx.words(key));
    if (on) th.append(el('span', 'sf-table__sort', model.sort.desc ? '▼' : '▲'));
    th.addEventListener('click', () => ctx.declare({ sort: { key, desc: on ? !model.sort.desc : false } }));
    head.append(th);
  });
  const plus = el('th', 'sf-table__add');
  plus.append(ctx.plus(model.next));
  head.append(plus);
  table.append(head);
  for (const line of model.lines) {
    const tr = el('tr', line.marked ? 'is-marked' : '');
    line.cells.forEach((cell, k) => tr.append(el('td', model.numeric[k] ? 'is-num' : '', cell.text)));
    tr.append(el('td', 'sf-table__add'));
    tr.addEventListener('click', (event) => { event.stopPropagation(); ctx.mark([line.id], event); });
    table.append(tr);
  }
  wrap.append(table);
  // A press on the table's own ground, not on a line or a head, unmarks (Spotfire: a click on nothing).
  wrap.addEventListener('click', (event) => { if (event.target === wrap) ctx.clear(); });
  body.replaceChildren(wrap);
  return { resize: () => {}, dispose: () => {} };
}

/** The title when the declaration names none - its row type, as Spotfire's table says its data table. */
export const title = (encode, declaration) => (declaration && declaration.row) || 'Table';

/** The add window's picture of it: a head and lines. */
export const icon = { tone: 'cat-1', paths: [['M4 3h16v4H4z', 1], ['M4 9h16v3H4zM4 14h16v3H4zM4 19h16v2H4z', 0.6]] };

export const kind = { name: 'table', label: 'Table', slots, title, model: tableModel, render, icon };
