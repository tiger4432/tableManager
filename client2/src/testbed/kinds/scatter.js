// The scatter kind of the visual part: its slots, its model, its picture (ECharts, injected - the kind never imports it).
// What the root hands in is the same for every kind: rows and their slots read, what is marked, the declaration, the
// palette its tokens give (testbed/palette.js).

import { numberOf } from '../../walk/reach_table.js';
import { categoryColor, mix, MARKER_PX, MARKER_PCT } from '../palette.js';
import { slotWords } from '../slot.js';

export const SLOTS = Object.freeze([
  { key: 'x', label: 'X-axis' },
  { key: 'y', label: 'Y-axis' },
  { key: 'color', label: 'Color by', category: true },
]);

const ISO_TIME = /^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/;
/** An axis by what its values are: all numbers a value axis, all ISO times a time axis, else categories. */
export function axisKind(values) {
  const said = values.filter((v) => v !== null && v !== undefined && v !== '');
  if (said.length && said.every((v) => numberOf(v) !== null)) return 'value';
  if (said.length && said.every((v) => typeof v === 'string' && ISO_TIME.test(v.trim()))) return 'time';
  return 'category';
}

/**
 * The picture's model. A point is a row whose x and y each hold one value (a several without a reduce is not drawn -
 * lead aca803a7a «N rows with several values»); its colour is its category's, mixed toward the background when something
 * else is marked and it is not.
 * @param {Array<{id, label, reads: Record<string, object>}>} rows
 * @param {{marked: (id) => boolean, palette: object, declaration?: object}} ctx  the declaration's markerPct - the marker size
 */
export function scatterModel(rows, ctx) {
  const palette = ctx.palette;
  const drawable = [];
  let notDrawn = 0;
  let several = 0;
  for (const row of rows) {
    const { x, y, color } = row.reads;
    if ([x, y, color].some((r) => r && r.state === 'several')) { several += 1; continue; }
    if (!x || !y || x.state !== 'one' || y.state !== 'one') { notDrawn += 1; continue; }
    drawable.push({ id: row.id, label: row.label, x: x.value, y: y.value, category: color && color.state === 'one' ? color.value : null });
  }
  const categories = [...new Set(drawable.map((p) => p.category).filter((c) => c !== null).map(String))].sort();
  const anyMarked = drawable.some((p) => ctx.marked(p.id));
  const points = drawable.map((p) => {
    const k = p.category === null ? -1 : categories.indexOf(String(p.category));
    const [fill, border] = k < 0 ? palette.one : categoryColor(palette, k);
    const marked = ctx.marked(p.id);
    const dim = anyMarked && !marked;
    return { ...p, marked, fill: dim ? mix(fill, palette.bg) : fill, border: dim ? mix(border, palette.bg) : border };
  });
  const legend = categories.map((name, k) => ({ name, fill: categoryColor(palette, k)[0], border: categoryColor(palette, k)[1],
    ids: points.filter((p) => String(p.category) === name).map((p) => p.id),
    dim: anyMarked && !points.some((p) => p.marked && String(p.category) === name) }));
  return { points, legend, one: palette.one, anyMarked, notDrawn, several,
    xKind: axisKind(points.map((p) => p.x)), yKind: axisKind(points.map((p) => p.y)),
    size: MARKER_PX * (((ctx.declaration && ctx.declaration.markerPct) || MARKER_PCT) / MARKER_PCT) };
}

/** A number as an axis says it - no unit added (mockup fix ③: «1.0 %» on a ratio was a wrong sentence). */
export const tickWords = (v) => (typeof v === 'number' ? (Number.isInteger(v) ? String(v) : String(Number(v.toPrecision(6)))) : String(v));

/** The ECharts option for a model - pure, so the picture is scored without a canvas. */
export function scatterOption(model, palette) {
  const t = palette;
  const axis = (kind, values) => ({
    type: kind, scale: kind === 'value', data: kind === 'category' ? [...new Set(values.map(String))].sort() : undefined,
    axisLine: { show: true, lineStyle: { color: t.axis, width: 1 } }, axisTick: { show: false }, splitLine: { show: false },
    axisLabel: { color: t.text, fontFamily: 'Roboto', fontSize: 12, formatter: kind === 'value' ? tickWords : undefined },
  });
  // Marked points last, so they stand over the dimmed ones as Spotfire draws them.
  const ordered = [...model.points].sort((a, b) => Number(a.marked) - Number(b.marked));
  return {
    animation: false,
    grid: { left: 60, right: 8, top: 16, bottom: 28, containLabel: false },
    xAxis: axis(model.xKind, model.points.map((p) => p.x)),
    yAxis: axis(model.yKind, model.points.map((p) => p.y)),
    brush: { toolbox: [], xAxisIndex: 0, brushType: 'rect', brushMode: 'single', transformable: false,
      brushStyle: { borderWidth: 1, color: t.brush, borderColor: t.active }, inBrush: {}, outOfBrush: {} },
    series: [{
      type: 'scatter', symbolSize: model.size, cursor: 'pointer',
      data: ordered.map((p) => ({ value: [model.xKind === 'category' ? String(p.x) : p.x, model.yKind === 'category' ? String(p.y) : p.y],
        id: p.id, name: p.label, itemStyle: { color: p.fill, borderColor: p.border, borderWidth: 1, opacity: 1 } })),
      emphasis: { scale: false },
    }],
  };
}

/** The points a rectangle holds - its coordRange as ECharts gives it at brushEnd ([[x0, x1], [y0, y1]] in axis values; a
 *  category axis in category positions, a time axis in ms). Pure, so a drag is scored without a canvas. */
export function idsInRange(model, option, coordRange) {
  if (!coordRange || coordRange.length !== 2) return [];
  const at = (kind, axis, v) => (kind === 'category' ? axis.data.indexOf(String(v)) : kind === 'time' ? Date.parse(v) : numberOf(v));
  const inside = ([lo, hi], x) => x !== null && Number.isFinite(x) && x >= Math.min(lo, hi) && x <= Math.max(lo, hi);
  return model.points.filter((p) => inside(coordRange[0], at(model.xKind, option.xAxis, p.x)) && inside(coordRange[1], at(model.yKind, option.yAxis, p.y)))
    .map((p) => p.id);
}

/**
 * Draw a model into the body the root hands over: the Y tray, the plot (an ECharts instance from `ctx.charts`), the
 * legend, the X tray. Brushing a rectangle marks what it holds, a click marks one point, a press on nothing clears -
 * each through `ctx.mark`; a legend value marks its hub through `ctx.markHub`.
 * @returns {{resize: () => void, dispose: () => void}}
 */
export function render(body, model, ctx) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  body.className = 'sf-part__body tb-scatter';
  const ytray = el('div', 'tb-ytray');
  ytray.append(ctx.plus('y'), ctx.pill('y', { vertical: true }));
  const plot = el('div', 'tb-plot');
  const legend = el('div', 'sf-legend');
  const ttl = (words) => el('div', 'sf-legend__ttl', words);
  const row = (...kids) => { const r = el('div', 'sf-legend__row'); r.append(...kids); return r; };
  legend.append(ttl('Marker by:'), row(ctx.pill(null, { words: '(Node)' })), ttl('Color by:'), row(ctx.pill('color'), ctx.plus('color')));
  if (model.legend.length) {
    for (const item of model.legend) {
      const v = el('button', `sf-legend__v${item.dim ? ' is-dim' : ''}`);
      v.type = 'button';
      const ico = el('span', 'sf-legend__ico');
      ico.style.background = item.fill;
      ico.style.borderColor = item.border;
      v.append(ico, el('span', 'sf-legend__name', item.name));
      v.addEventListener('click', (event) => ctx.markHub([[ctx.words('color'), item.name]], item.ids, event));
      legend.append(v);
    }
  } else {
    const v = el('div', 'sf-legend__v');
    const ico = el('span', 'sf-legend__ico');
    ico.style.background = model.one[0];
    ico.style.borderColor = model.one[1];
    v.append(ico, el('span', 'sf-legend__name', 'All values'));
    legend.append(v);
  }
  const xtray = el('div', 'tb-xtray');
  const note = el('span', 'sf-note', [model.notDrawn ? `${model.notDrawn} not drawn` : '',
    model.several ? `${model.several} rows with several values` : ''].filter(Boolean).join(' · '));
  xtray.append(note, ctx.pill('x'), ctx.plus('x'));
  body.replaceChildren(ytray, plot, legend, xtray);

  const option = scatterOption(model, ctx.palette);
  const chart = ctx.charts.init(plot);
  chart.setOption(option, true);
  // The brush is always on: a drag draws a rectangle (Spotfire's), no toolbox button to arm it.
  chart.dispatchAction({ type: 'takeGlobalCursor', key: 'brush', brushOption: { brushType: 'rect', brushMode: 'single' } });
  // A rectangle drawn marks what it holds; the rectangle then goes (Spotfire keeps none on screen).
  chart.on('brushEnd', (params) => {
    const area = params && params.areas && params.areas[0];
    if (!area) return;
    chart.dispatchAction({ type: 'brush', areas: [] });
    ctx.mark(idsInRange(model, option, area.coordRange), ctx.lastEvent());
  });
  chart.on('click', (params) => { if (params && params.data && params.data.id) ctx.mark([params.data.id], params.event && params.event.event); });
  const zr = chart.getZr && chart.getZr();
  if (zr) {
    zr.on('mousedown', (e) => ctx.remember(e && e.event));
    zr.on('click', (e) => { if (!e.target) ctx.clear(); });
  }
  return { resize: () => chart.resize(), dispose: () => chart.dispose() };
}

/** The title when the declaration names none - «y vs. x». */
export const title = (encode) => `${slotWords(encode.y)} vs. ${slotWords(encode.x)}`;

export const kind = { name: 'scatter', label: 'Scatter plot', slots: SLOTS, title, model: scatterModel, render };
