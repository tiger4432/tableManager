// The scatter kind - its visible area only (docs/architecture/ROOT_PART_BASE_SET.md: the root is the template): a point a
// unit the root made (a node, a hub, a value record) at its x and y, painted as the root says; a press or a rectangle
// gives back which. Its trays, legend, marking and colour are the root's.

import { numberOf } from '../../walk/reach_table.js';
import { MARKER_PX, MARKER_PCT } from '../palette.js';
import { slotWords } from '../slot.js';

/** Its slots: the axes on the template's trays - Y on the left, X under. */
export const SLOTS = Object.freeze([
  { key: 'x', label: 'X-axis', tray: 'bottom', plus: true },
  { key: 'y', label: 'Y-axis', tray: 'left', plus: true },
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
 * The picture's model. A point is a unit whose x and y each hold one value (a several without a reduce is not drawn -
 * lead aca803a7a «N rows with several values»); its paint is the root's (`ctx.paint(ids)`: colour, marked, dimmed).
 * @param {Array<{id, ids?, where?, label, reads: Record<string, object>}>} units
 * @param {{paint?: (ids) => {fill, line, marked}, palette: object, declaration?: object}} ctx  the declaration's markerPct -
 *   the marker size
 */
export function scatterModel(units, ctx) {
  const paint = ctx.paint || (() => ({ fill: ctx.palette.one[0], line: ctx.palette.one[1], marked: false }));
  const points = [];
  let notDrawn = 0;
  let several = 0;
  for (const u of units) {
    const { x, y } = u.reads;
    if ([x, y].some((r) => r && r.state === 'several')) { several += 1; continue; }
    if (!x || !y || x.state !== 'one' || y.state !== 'one') { notDrawn += 1; continue; }
    const ids = u.ids || [u.id];
    const p = paint(ids, u.where || null);
    // its label - the root's (none, marked, all)
    const tag = ctx.label ? ctx.label(u) : null;
    // its shape - the root's (Shape by)
    const shape = ctx.shape ? ctx.shape(ids) : null;
    points.push({ id: u.id, ids, where: u.where || null, label: u.label, tag, shape, x: x.value, y: y.value, marked: p.marked, fill: p.fill, border: p.line });
  }
  return { points, notDrawn, several, note: [notDrawn ? `${notDrawn} not drawn` : '', several ? `${several} rows with several values` : ''].filter(Boolean).join(' · '),
    xKind: axisKind(points.map((p) => p.x)), yKind: axisKind(points.map((p) => p.y)),
    // a trellis panel's axes: the extents over every panel (the root's)
    range: ctx.extent ? { x: ctx.extent('x'), y: ctx.extent('y') } : null,
    size: MARKER_PX * (((ctx.declaration && ctx.declaration.markerPct) || MARKER_PCT) / MARKER_PCT) };
}

/** A number as an axis says it - no unit added (mockup fix ③: «1.0 %» on a ratio was a wrong sentence). */
export const tickWords = (v) => (typeof v === 'number' ? (Number.isInteger(v) ? String(v) : String(Number(v.toPrecision(6)))) : String(v));

/** The ECharts option for a model - pure, so the picture is scored without a canvas. */
export function scatterOption(model, palette) {
  const t = palette;
  const axis = (kind, values, range = null) => ({
    type: kind, scale: kind === 'value', data: kind === 'category' ? [...new Set(values.map(String))].sort() : undefined,
    ...(kind === 'value' && range ? { min: range[0], max: range[1] } : {}),
    axisLine: { show: true, lineStyle: { color: t.axis, width: 1 } }, axisTick: { show: false }, splitLine: { show: false },
    axisLabel: { color: t.text, fontFamily: 'Roboto', fontSize: 12, formatter: kind === 'value' ? tickWords : undefined },
  });
  // Marked points last, so they stand over the dimmed ones as Spotfire draws them.
  const ordered = [...model.points].sort((a, b) => Number(a.marked) - Number(b.marked));
  const xAxis = axis(model.xKind, model.points.map((p) => p.x), model.range && model.range.x);
  // a label on the point's inner side - right of a point in the left half, left of one in the right half - so it stays
  // in the plot, not under the legend beside it (lead 10-14)
  const along = (v) => (model.xKind === 'category' ? xAxis.data.indexOf(String(v)) : model.xKind === 'time' ? Date.parse(v) : numberOf(v));
  const xs = model.points.map((p) => along(p.x)).filter((v) => v !== null && Number.isFinite(v));
  const mid = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : 0;
  const side = (p) => (along(p.x) > mid ? 'left' : 'right');
  return {
    animation: false,
    grid: { left: 60, right: 8, top: 16, bottom: 28, containLabel: false },
    xAxis,
    yAxis: axis(model.yKind, model.points.map((p) => p.y), model.range && model.range.y),
    brush: { toolbox: [], xAxisIndex: 0, brushType: 'rect', brushMode: 'single', transformable: false,
      brushStyle: { borderWidth: 1, color: t.brush, borderColor: t.active }, inBrush: {}, outOfBrush: {} },
    series: [{
      type: 'scatter', symbolSize: model.size, cursor: 'pointer',
      data: ordered.map((p) => ({ value: [model.xKind === 'category' ? String(p.x) : p.x, model.yKind === 'category' ? String(p.y) : p.y],
        id: p.id, name: p.label, ...(p.shape ? { symbol: p.shape } : {}), itemStyle: { color: p.fill, borderColor: p.border, borderWidth: 1, opacity: 1 },
        label: { show: p.tag !== null && p.tag !== undefined, formatter: String(p.tag), position: side(p), color: t.text, fontFamily: 'Roboto', fontSize: 12 } })),
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
 * Draw a model into the area the template hands over (an ECharts instance from `ctx.charts`). Brushing a rectangle gives
 * back what it holds, a click one point, a press on nothing clears - a node or a value record its node through
 * `ctx.mark`, a Marker by hub whole through `ctx.markHubs`.
 * @returns {{resize: () => void, dispose: () => void}}
 */
export function render(area, model, ctx) {
  const doc = ctx.doc;
  const plot = doc.createElement('div');
  plot.className = 'tb-plot';
  area.replaceChildren(plot);
  const option = scatterOption(model, ctx.palette);
  // A point pressed or in a rectangle: a node or a value record marks its node; a Marker by marker marks its hub whole.
  const byId = new Map(model.points.map((p) => [p.id, p]));
  const markPoints = (ids, event) => {
    const pts = ids.map((id) => byId.get(id)).filter(Boolean);
    if (pts.some((p) => p.where)) ctx.markHubs(pts.map((p) => [p.where, p.ids]), event); else ctx.mark([...new Set(pts.flatMap((p) => p.ids))], event);
  };
  const chart = ctx.charts.init(plot);
  chart.setOption(option, true);
  // The brush is always on: a drag draws a rectangle (Spotfire's), no toolbox button to arm it.
  chart.dispatchAction({ type: 'takeGlobalCursor', key: 'brush', brushOption: { brushType: 'rect', brushMode: 'single' } });
  // A rectangle drawn marks what it holds; the rectangle then goes (Spotfire keeps none on screen).
  chart.on('brushEnd', (params) => {
    const drawn = params && params.areas && params.areas[0];
    if (!drawn) return;
    chart.dispatchAction({ type: 'brush', areas: [] });
    markPoints(idsInRange(model, option, drawn.coordRange), ctx.lastEvent());
  });
  chart.on('click', (params) => { if (params && params.data && params.data.id) markPoints([params.data.id], params.event && params.event.event); });
  // the point under the pointer - the root says its tooltip
  chart.on('mouseover', (params) => { if (params && params.data && params.data.id) ctx.hover({ id: params.data.id }, params.event && params.event.event); });
  chart.on('mouseout', () => ctx.hover(null));
  const zr = chart.getZr && chart.getZr();
  if (zr) {
    zr.on('mousedown', (e) => ctx.remember(e && e.event));
    zr.on('click', (e) => { if (!e.target) ctx.clear(); });
  }
  return { resize: () => chart.resize(), dispose: () => chart.dispose() };
}

/** The title when the declaration names none - «y vs. x». */
export const title = (encode) => `${slotWords(encode.y)} vs. ${slotWords(encode.x)}`;

/** The add window's picture of it: points. */
export const icon = { tone: 'cat-1', paths: [['M4 16h3v3H4zM8 11h3v3H8zM13 13h3v3h-3zM12 6h3v3h-3zM17 3h3v3h-3zM18 9h3v3h-3z', 1]] };

// units - a point a unit of the root's Marker by; a value record spreads Y's records.
export const kind = { name: 'scatter', label: 'Scatter plot', slots: SLOTS, units: { record: 'y' }, points: true, title, model: scatterModel, render, icon };
