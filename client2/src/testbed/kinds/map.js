// The map kind - its visible area only (ROOT_PART_BASE_SET: the root is the template; owner 10-13 scenario A «본딩 웨이퍼
// 다이맵»): a cell at X and Y - a die at its keys x and y - on a grid the rows' own coordinates span (the map editor's meta
// as the background is not wired: the owner's «메타가 없으면 데이터 좌표로 격자»). A cell is a coordinate: the hub of the
// rows at it (two wafers' dies at one x, y - one cell), given back whole when pressed; a press on the ground clears. Its
// paint is the root's.

import { numberOf } from '../../walk/reach_table.js';
import { combosOf } from '../slot.js';

const SVG = 'http://www.w3.org/2000/svg';

export const SLOTS = Object.freeze([
  { key: 'x', label: 'X', tray: 'bottom' },
  { key: 'y', label: 'Y', tray: 'bottom' },
]);

/**
 * @param {Array<{id, label, reads: object}>} rows
 * @param {{paint: (ids) => {fill, line, marked}}} ctx  the root's paint
 */
export function mapModel(rows, ctx) {
  const cells = [];
  let notDrawn = 0;
  for (const { values, ids } of combosOf(rows, ['x', 'y'])) {
    const [x, y] = values.map(numberOf);
    if (x === null || y === null) { notDrawn += ids.length; continue; }
    // its paint is the root's
    const p = ctx.paint(ids);
    // its label - the root's (none, marked, all)
    const tag = ctx.label ? ctx.label({ ids }) : null;
    cells.push({ ids, where: values, x, y, tag, marked: p.marked, fill: p.fill, line: p.line });
  }
  const span = (k) => (cells.length ? [Math.min(...cells.map((c) => c[k])), Math.max(...cells.map((c) => c[k]))] : [0, 0]);
  return { cells, notDrawn, note: notDrawn ? `${notDrawn} not drawn` : '', x: span('x'), y: span('y') };
}

/** Draw a model into the template's area: the grid (an SVG, a cell a rect). */
export function render(area, model, ctx) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const plot = el('div', 'tb-map__plot');
  const svg = doc.createElementNS(SVG, 'svg');
  const [x0, x1] = model.x;
  const [y0, y1] = model.y;
  svg.setAttribute('viewBox', `${x0 - 0.5} ${y0 - 0.5} ${x1 - x0 + 2} ${y1 - y0 + 2}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  svg.setAttribute('class', 'tb-map__svg');
  for (const c of model.cells) {
    const rect = doc.createElementNS(SVG, 'rect');
    rect.setAttribute('x', String(c.x));
    rect.setAttribute('y', String(c.y));
    rect.setAttribute('width', '0.9');
    rect.setAttribute('height', '0.9');
    rect.setAttribute('fill', c.fill);
    rect.setAttribute('stroke', c.line);
    rect.setAttribute('stroke-width', '0.04');
    rect.setAttribute('data-cell', `${c.x},${c.y}`);
    rect.addEventListener('mousemove', (event) => ctx.hover({ ids: c.ids, label: c.ids.length > 1 ? `${c.x}, ${c.y}` : undefined }, event));
    rect.addEventListener('mouseleave', () => ctx.hover(null));
    rect.addEventListener('click', (event) => {
      if (event.stopPropagation) event.stopPropagation();
      ctx.markHub([[ctx.words('x'), c.where[0]], [ctx.words('y'), c.where[1]]], c.ids, event);
    });
    svg.appendChild(rect);
    if (c.tag !== null && c.tag !== undefined) {
      const text = doc.createElementNS(SVG, 'text');
      text.setAttribute('x', String(c.x + 0.45));
      text.setAttribute('y', String(c.y + 0.6));
      text.setAttribute('class', 'tb-map__tag');
      text.textContent = String(c.tag);
      svg.appendChild(text);
    }
  }
  svg.addEventListener('click', (event) => { if (event.target === svg) ctx.clear(); });
  plot.append(svg);
  area.replaceChildren(plot);
  return { resize: () => {}, dispose: () => {} };
}

/** The title when the declaration names none - its row type's map. */
export const title = (encode, declaration) => `${(declaration && declaration.row) || ''} map`.trim();

/** The add window's picture of it: a grid of cells. */
export const icon = { tone: 'cat-4', paths: [['M4 4h4v4H4zM10 4h4v4h-4zM16 4h4v4h-4zM4 10h4v4H4zM16 10h4v4h-4zM4 16h4v4H4zM10 16h4v4h-4zM16 16h4v4h-4z', 1], ['M10 10h4v4h-4z', 0.6]] };

export const kind = { name: 'map', label: 'Map', slots: SLOTS, title, model: mapModel, render, icon };
