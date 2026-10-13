// The scatter kind of the visual part: its slots, its model, its picture (ECharts, injected - the kind never imports it).
// What the root hands in is the same for every kind: rows and their slots read, what is marked, the declaration, the
// palette its tokens give (testbed/palette.js).

import { numberOf } from '../../walk/reach_table.js';
import { mix, MARKER_PX, MARKER_PCT } from '../palette.js';
import { colorsOf, colorOfIds } from '../color_by.js';
import { slotWords, combosOf, foldRows, isExpression } from '../slot.js';
import { hubId } from '../hubs.js';

export const SLOTS = Object.freeze([
  { key: 'x', label: 'X-axis' },
  { key: 'y', label: 'Y-axis' },
]);
const MARKER = /^marker(\d+)$/;
const markerOrder = (key) => Number(MARKER.exec(key)[1]);
/** The Marker by keys the declaration holds, in order. */
export const markersOf = (encode) => Object.keys(encode || {}).filter((k) => MARKER.test(k)).sort((a, b) => markerOrder(a) - markerOrder(b));
/** The key «+» on Marker by fills next. */
export const nextMarker = (encode) => { const keys = markersOf(encode); return `marker${keys.length ? markerOrder(keys[keys.length - 1]) + 1 : 1}`; };

/** What a point is (Spotfire's «Marker by»): a hub of the rows a combination of the Marker by values holds; else one
 *  value record - a read of Y, a row spread into its reads (`markerBy: 'record'`); else a node. */
export const unitOf = (decl) => (markersOf((decl || {}).encode).length ? 'hub' : (decl || {}).markerBy === 'record' ? 'record' : 'node');
/** The Marker by choices that are not a slot - the next one's picker lists them. */
const UNITS = Object.freeze([{ words: '(Node)', patch: { markerBy: null } }, { words: '(Value record)', patch: { markerBy: 'record' } }]);

/** Its slots: the axes, Color by, each Marker by held and the next one. A hub or a record reads every value of the axes. */
export const slots = (encode, decl) => {
  const unit = unitOf({ ...(decl || {}), encode });
  // a hub folds its rows' reads; a value record reads the records themselves
  const axes = SLOTS.map((s) => (unit !== 'node' && (s.key === 'x' || s.key === 'y') ? { ...s, folds: true, records: unit === 'record' } : s));
  return [...axes, ...markersOf(encode).map((key) => ({ key, label: 'Marker by', category: true })),
    { key: nextMarker(encode), label: 'Marker by', category: true, choices: UNITS }];
};

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
 * @param {{marked: (id) => boolean, markColor?: string|null, palette: object, declaration?: object}} ctx  the declaration's
 *   markerPct - the marker size
 */
export function scatterModel(rows, ctx) {
  const palette = ctx.palette;
  // The colours are the root's (color_by.js) - handed in, or asked of the same seat when the model is made alone.
  const colors = ctx.colors || colorsOf(rows, ctx);
  const encode = (ctx.declaration && ctx.declaration.encode) || {};
  const markers = markersOf(encode);
  const unit = unitOf(ctx.declaration);
  const drawable = [];
  let notDrawn = 0;
  let several = 0;
  // Each marker's rows read as one row: a slot with a reduce folds their values (all of them, not of each row's fold); one
  // without says its value when they all say the same one, several when not.
  const byId = new Map(rows.map((r) => [r.id, r]));
  const units = unit === 'hub' ? combosOf(rows, markers).map(({ values, ids }) => ({ ids, values, rows: ids.map((id) => byId.get(id)) }))
    : unit === 'record' ? rows.flatMap((row) => recordUnits(row, encode.y).map((picks, k) => ({ ids: [row.id], values: null, rows: [row], k, picks })))
      : rows.map((row) => ({ ids: [row.id], values: null, rows: [row] }));
  for (const one of units) {
    const read = (key) => (unit === 'hub' ? foldedRead(one.rows, key, encode[key]) : unit === 'record' ? recordRead(one.rows[0], key, one.picks, encode[key])
      : one.rows[0].reads[key]);
    const [x, y, color] = ['x', 'y', 'color'].map(read);
    if ([x, y, color].some((r) => r && r.state === 'several')) { several += 1; continue; }
    if (!x || !y || x.state !== 'one' || y.state !== 'one') { notDrawn += 1; continue; }
    const where = one.values && markers.map((k, i) => [slotWords(encode[k]), one.values[i]]);
    const id = where ? hubId(ctx.declaration.row, where) : unit === 'record' ? `${one.ids[0]}#${one.k}` : one.ids[0];
    drawable.push({ id, ids: one.ids, where, label: where ? one.values.join(' · ') : one.rows[0].label,
      x: x.value, y: y.value, color: colorOfIds(colors, one.ids) });
  }
  // A marker is marked when a row of it is (a hub as its members).
  const isMarked = (p) => p.ids.some(ctx.marked);
  const anyMarked = drawable.some(isMarked);
  const points = drawable.map((p) => {
    const { fill, line: border } = p.color;
    const marked = isMarked(p);
    const dim = anyMarked && !marked;
    // A marked point in its marking's colour (Spotfire's), the others dimmed toward the background.
    if (marked && ctx.markColor) return { ...p, marked, fill: ctx.markColor, border: ctx.markColor };
    return { ...p, marked, fill: dim ? mix(fill, palette.bg) : fill, border: dim ? mix(border, palette.bg) : border };
  });
  return { points, colors, one: palette.one, anyMarked, notDrawn, several, encode, unit,
    xKind: axisKind(points.map((p) => p.x)), yKind: axisKind(points.map((p) => p.y)),
    size: MARKER_PX * (((ctx.declaration && ctx.declaration.markerPct) || MARKER_PCT) / MARKER_PCT) };
}

/** A marker's rows read as one on a slot: with a reduce or an expression, every value of theirs folded (slot.foldRows - the
 *  cross table's rule); without, the value when they all say one and the same, several when not, empty when none says one. */
function foldedRead(rows, key, slot) {
  if (!slot) return undefined;
  if (slot.reduce || isExpression(slot)) {
    const value = foldRows(slot, rows.map((r) => r.raw && r.raw[key]));
    return value === null || value === undefined ? { state: 'empty' } : { state: 'one', value };
  }
  const reads = rows.map((r) => r.reads[key]).filter(Boolean);
  if (reads.some((r) => r.state === 'several')) return { state: 'several', values: [] };
  const said = [...new Map(reads.filter((r) => r.state === 'one').map((r) => [JSON.stringify(r.value), r.value])).values()];
  return said.length === 1 ? { state: 'one', value: said[0] } : said.length ? { state: 'several', values: said } : { state: 'empty' };
}

/** A row's value records as points (owner 10-13 «기록 하나가 점 하나»): each of Y's records its own point; Y with a reduce -
 *  each read's records (an edge's) folded into one. -> the record indexes each point takes. */
function recordUnits(row, ySlot) {
  const ys = (row.raw && row.raw.y) || [];
  if (!(ySlot && ySlot.reduce)) return ys.map((_, k) => [k]);
  const byRead = new Map();
  ys.forEach((r, k) => { if (!byRead.has(r.read)) byRead.set(r.read, []); byRead.get(r.read).push(k); });
  return [...byRead.values()];
}

/** A value record's read on a slot: the records it takes when the slot reads as many as Y (Y itself; its time) - folded by
 *  the slot's reduce, else their one value (several when they differ); else the row's one value. */
function recordRead(row, key, picks, slot) {
  if (!slot) return undefined;
  const raw = row.raw && row.raw[key];
  if (!raw || raw.length !== row.raw.y.length) return row.reads[key];
  const items = picks.map((k) => raw[k]);
  if (slot.reduce) { const value = foldRows(slot, [items]); return value === null || value === undefined ? { state: 'empty' } : { state: 'one', value }; }
  const said = [...new Map(items.map((r) => [JSON.stringify(r.value), r.value])).values()];
  return said.length === 1 ? { state: 'one', value: said[0] } : { state: 'several', values: said };
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
  // Marker by: a pill each one held and «+» for one more; none held - «(Node)» or «(Value record)», pressed picks the first.
  const encode = model.encode || {};
  const held = markersOf(encode);
  const markerRow = held.length ? row(...held.map((k) => ctx.pill(k)), ctx.plus(nextMarker(encode)))
    : row(ctx.pill(nextMarker(encode), { words: model.unit === 'record' ? '(Value record)' : '(Node)' }));
  legend.append(ttl('Marker by:'), markerRow, ctx.legend());
  const xtray = el('div', 'tb-xtray');
  const note = el('span', 'sf-note', [model.notDrawn ? `${model.notDrawn} not drawn` : '',
    model.several ? `${model.several} rows with several values` : ''].filter(Boolean).join(' · '));
  xtray.append(note, ctx.pill('x'), ctx.plus('x'));
  body.replaceChildren(ytray, plot, legend, xtray);

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
    const area = params && params.areas && params.areas[0];
    if (!area) return;
    chart.dispatchAction({ type: 'brush', areas: [] });
    markPoints(idsInRange(model, option, area.coordRange), ctx.lastEvent());
  });
  chart.on('click', (params) => { if (params && params.data && params.data.id) markPoints([params.data.id], params.event && params.event.event); });
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

export const kind = { name: 'scatter', label: 'Scatter plot', slots, title, model: scatterModel, render, icon };
