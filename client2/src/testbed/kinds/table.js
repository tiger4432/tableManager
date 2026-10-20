// The table kind of the visual part (owner 10-13 «근원부품 table», Spotfire's Table): a line a row - the row type's nodes
// the root kept - and a column a slot, added with «+» (the axes' picker: the walk table's «+ Column» choice). A line
// pressed marks its node through the root (a press replaces, Ctrl adds); a press below the lines clears; a column head
// pressed sorts by it, again the other way. Its columns and its sort are its declaration's: encode.col1 … and `sort`.

import { numberOf, valueWords } from '../../walk/reach_table.js';
import { dragMarks } from '../drag_mark.js';
import { slotWords, isTimeRead } from '../slot.js';
import { IMAGE_ROW_PX } from '../../image_thumb.js';

const COLUMN = /^col(\d+)$/;
/** Lines drawn above and below the ones in view (owner 10-20 «보이는 줄만»); with no height to measure, the first 2 x this. */
export const OVERSCAN = 20;
const order = (key) => Number(COLUMN.exec(key)[1]);

/** The next column's key. */
const nextOf = (keys) => `col${keys.length ? Math.max(...keys.map(order)) + 1 : 1}`;
/** The table's slots: one a column the declaration holds, in their order; the next one «+ Column» in the bottom tray (the
 *  frame standard 9). */
export const slots = (encode) => {
  const keys = Object.keys(encode || {}).filter((k) => COLUMN.test(k)).sort((a, b) => order(a) - order(b));
  return [...keys.map((key) => ({ key, label: `Column ${order(key)}` })), { key: nextOf(keys), label: 'Add a column', tray: 'bottom', words: '+ Column' }];
};

/** A read as a cell says it: a mark's one value (the root spreads several into marks - units.js marksOf), nothing blank. */
function cellOf(read, key, ctx) {
  // a slot of images (the root's): the cell's pictures, turned in place
  const images = ctx.images ? ctx.images(key, read) : null;
  if (images) return { text: '', value: null, images };
  if (!read || read.state !== 'one') return { text: '', value: null };
  // as the slot says it (the root's one place - a time, a slot of days its days)
  return { text: ctx.text ? ctx.text(key, read.value, isTimeRead(read)) : valueWords(read.value), value: read.value };
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
 * @param {{paint: (ids) => {marked, color}, colored: boolean, declaration?: object}} ctx  the root's paint; the declaration's
 *   `sort` {key, desc}
 */
export function tableModel(rows, ctx) {
  const decl = ctx.declaration || {};
  const keys = slots(decl.encode).filter((s) => !s.tray).map((s) => s.key);
  // a line's paint is the root's: marked, and its row's Color by colour when one is declared
  // a line a mark - its row's (`ids`): the lines of one row painted together, a press marks the row
  let lines = rows.map((row) => { const ids = row.ids || [row.id]; const p = ctx.paint(ids);
    return { id: row.id, ids, cells: keys.map((k) => cellOf(row.reads[k], k, ctx)), marked: p.marked, color: ctx.colored ? p.color : null }; });
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
  const next = nextOf(keys);
  // a column of images makes every line one height - IMAGE_ROW_PX (lead 10-15 ③)
  const pictured = lines.some((l) => l.cells.some((c) => c.images));
  return { keys, lines, sort, numeric, next, pictured };
}

/** Draw a model into the template's area: the column heads (each sorts; «+» adds one), a line a row, the marked ones
 *  marked. */
export function render(area, model, ctx) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const wrap = el('div', 'tb-table__wrap');
  const table = el('table', `sf-table sf-table--rows${model.pictured ? ' sf-table--images' : ''}`);
  if (model.pictured && table.style && table.style.setProperty) table.style.setProperty('--sf-image-row', `${IMAGE_ROW_PX}px`);
  const head = el('tr');
  model.keys.forEach((key, k) => {
    const on = model.sort && model.sort.key === key;
    const th = el('th', model.numeric[k] ? 'is-num' : '', ctx.words(key));
    if (on) th.append(el('span', 'sf-table__sort', model.sort.desc ? '▼' : '▲'));
    th.addEventListener('click', () => ctx.declare({ sort: { key, desc: on ? !model.sort.desc : false } }));
    head.append(th);
  });
  const thead = el('thead');
  thead.append(head);
  const body = el('tbody');
  table.append(thead, body);
  // a drag over lines marks the lines between (owner 10-16) - drag_mark.js, the cross table's one helper; the lines
  // between are the model's by their numbers, so a drag scrolled past lines not drawn marks them too
  const drag = dragMarks((spanned, event) => {
    const at = spanned.map((c) => c.row);
    const between = model.lines.slice(Math.min(...at), Math.max(...at) + 1);
    ctx.mark([...new Set(between.flatMap((l) => l.ids || [l.id]))], event, true);
  });
  const lineOf = (line, i) => {
    const tr = el('tr', line.marked ? 'is-marked' : '');
    if (line.color) { tr.setAttribute('data-color', line.color); tr.style.setProperty('--sf-line-color', line.color); }
    line.cells.forEach((cell, k) => {
      const td = el('td', model.numeric[k] ? 'is-num' : '', cell.text);
      if (cell.images && ctx.thumb) { const holder = el('span', 'sf-thumb__at'); td.append(holder); ctx.thumb(holder, cell.images, IMAGE_ROW_PX); }
      tr.append(td);
    });
    tr.addEventListener('click', (event) => { event.stopPropagation(); if (!drag.ended()) ctx.mark(line.ids || [line.id], event); });
    drag.add(tr, i, 0, line);
    tr.addEventListener('mousemove', (event) => ctx.hover({ id: line.id }, event));
    tr.addEventListener('mouseleave', () => ctx.hover(null));
    return tr;
  };
  // Only the lines in view are drawn (owner 10-20: 34,075 lines at once held the page for minutes) - a spacer line above
  // and below keeps the scroll as long as every line; the window follows the scroll and the box's size. The window starts
  // on an even line so a line keeps its stripe (nth-child) as it scrolls.
  const pad = () => { const td = el('td'); td.colSpan = Math.max(1, model.keys.length); const tr = el('tr', 'tb-table__pad'); tr.append(td); return [tr, td]; };
  const [above, aboveTd] = pad();
  const [below, belowTd] = pad();
  let from = -1;
  let to = -1;
  let rowPx = 0;
  const draw = () => {
    // the line height read off a line drawn (not yet laid out, nothing) - the window is then the box's real size
    const shown = body.children[1];
    if (!rowPx && shown && shown !== below && shown.getBoundingClientRect) rowPx = shown.getBoundingClientRect().height || 0;
    const n = model.lines.length;
    const view = wrap.clientHeight || 0;
    const top = wrap.scrollTop || 0;
    let [a, b] = view > 0 && rowPx > 0
      ? [Math.max(0, Math.floor(top / rowPx) - OVERSCAN), Math.min(n, Math.ceil((top + view) / rowPx) + OVERSCAN)]
      : [0, Math.min(n, 2 * OVERSCAN)];
    a -= a % 2;
    if (a === from && b === to) return;
    const lines = model.lines.slice(a, b).map((line, k) => lineOf(line, a + k));
    aboveTd.style.height = `${a * rowPx}px`;
    belowTd.style.height = `${(n - b) * rowPx}px`;
    body.replaceChildren(above, ...lines, below);
    [from, to] = [a, b];
    if (!rowPx && lines.length && view > 0) draw();
  };
  let asked = false;
  const frame = (doc.defaultView && doc.defaultView.requestAnimationFrame) || ((fn) => setTimeout(fn, 16));
  wrap.addEventListener('scroll', () => { if (asked) return; asked = true; frame(() => { asked = false; draw(); }); });
  wrap.append(table);
  // A press on the table's own ground, not on a line or a head, unmarks (Spotfire: a click on nothing).
  wrap.addEventListener('click', (event) => { if (event.target === wrap) ctx.clear(); });
  area.replaceChildren(wrap);
  draw();
  // a new size draws again only when the lines in view are other lines
  return { resize: draw, dispose: () => {} };
}

/** The title when the declaration names none - its row type, as Spotfire's table says its data table. */
export const title = (encode, declaration) => (declaration && declaration.row) || 'Table';

/** The add window's picture of it: a head and lines. */
export const icon = { tone: 'cat-1', paths: [['M4 3h16v4H4z', 1], ['M4 9h16v3H4zM4 14h16v3H4zM4 19h16v2H4z', 0.6]] };

export const kind = { name: 'table', label: 'Table', slots, title, model: tableModel, render, icon };
