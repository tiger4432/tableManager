// The map kind of the visual part (owner 10-13 scenario A «본딩 웨이퍼 다이맵»): a cell a row at its X and Y - a die at its
// keys x and y - on a grid the rows' own coordinates span (the map editor's meta as the background is not wired: the
// owner's «메타가 없으면 데이터 좌표로 격자»). A cell pressed marks its node (a press replaces, Ctrl adds); a press on the
// ground clears; marked cells in their marking's colour, the rest dimmed while something is marked.

import { numberOf } from '../../walk/reach_table.js';
import { mix } from '../palette.js';

const SVG = 'http://www.w3.org/2000/svg';

export const SLOTS = Object.freeze([
  { key: 'x', label: 'X' },
  { key: 'y', label: 'Y' },
]);

/**
 * @param {Array<{id, label, reads: object}>} rows
 * @param {{marked: (id) => boolean, markColor?: string|null, palette: object}} ctx
 */
export function mapModel(rows, ctx) {
  const cells = [];
  let notDrawn = 0;
  for (const row of rows) {
    const [x, y] = ['x', 'y'].map((k) => (row.reads[k] && row.reads[k].state === 'one' ? numberOf(row.reads[k].value) : null));
    if (x === null || y === null) { notDrawn += 1; continue; }
    cells.push({ id: row.id, label: row.label, x, y, marked: ctx.marked(row.id) });
  }
  const anyMarked = cells.some((c) => c.marked);
  const [one, line] = ctx.palette.one;
  for (const c of cells) {
    c.fill = c.marked ? (ctx.markColor || one) : anyMarked ? mix(one, ctx.palette.bg) : one;
    c.line = c.marked ? (ctx.markColor || line) : anyMarked ? mix(line, ctx.palette.bg) : line;
  }
  const span = (k) => (cells.length ? [Math.min(...cells.map((c) => c[k])), Math.max(...cells.map((c) => c[k]))] : [0, 0]);
  return { cells, notDrawn, anyMarked, x: span('x'), y: span('y') };
}

/** Draw a model: the grid (an SVG, a cell a rect), the X and Y pills under it. */
export function render(body, model, ctx) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  body.className = 'sf-part__body tb-map';
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
    rect.addEventListener('click', (event) => { if (event.stopPropagation) event.stopPropagation(); ctx.mark([c.id], event); });
    svg.appendChild(rect);
  }
  svg.addEventListener('click', (event) => { if (event.target === svg) ctx.clear(); });
  plot.append(svg);
  const tray = el('div', 'tb-xtray');
  tray.append(el('span', 'sf-note', model.notDrawn ? `${model.notDrawn} not drawn` : ''), ctx.pill('x'), ctx.pill('y'));
  body.replaceChildren(plot, tray);
  return { resize: () => {}, dispose: () => {} };
}

/** The title when the declaration names none - its row type's map. */
export const title = (encode, declaration) => `${(declaration && declaration.row) || ''} map`.trim();

/** The add window's picture of it: a grid of cells. */
export const icon = { tone: 'cat-4', paths: [['M4 4h4v4H4zM10 4h4v4h-4zM16 4h4v4h-4zM4 10h4v4H4zM16 10h4v4h-4zM4 16h4v4H4zM10 16h4v4h-4zM16 16h4v4h-4z', 1], ['M10 10h4v4h-4z', 0.6]] };

export const kind = { name: 'map', label: 'Map', slots: SLOTS, title, model: mapModel, render, icon };
