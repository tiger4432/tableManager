// THE TESTBED PAGE (lead aca803a7a ㄴ): the R&D board's frame - a layout of declarations, one marking store - holding
// the visual part's kinds, the basket, the status bar, the filters panel and the properties panel. The layout is data;
// Save keeps the visuals' declarations and a reopen draws the same picture from them.

import * as echarts from 'echarts/core';
import { ScatterChart } from 'echarts/charts';
import { GridComponent, BrushComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { GridShell } from '../rnd_board/grid_shell.js';
import { MarkingStore } from '../rnd_board/marking_store.js';
import { fetchSubgraph, fetchDeclaration, fetchKeyValues } from '../rnd_board/api.js';
import { VisualPart } from './visual_part.js';
import { StartPart } from './start_part.js';
import { BasketPart } from './basket_part.js';
import { StatusPart } from './status_part.js';
import { FiltersPart } from './filters_part.js';
import { PropertiesPart } from './properties_part.js';
import { SlotPicker } from './picker.js';
import { HubBook } from './hubs.js';
import { KeyedStore } from './keyed_store.js';
import { kind as scatterKind } from './kinds/scatter.js';
import { kind as crossKind } from './kinds/cross_table.js';

export const PARTS = Object.freeze({ visual: VisualPart, start: StartPart, basket: BasketPart, status: StatusPart,
  filters: FiltersPart, properties: PropertiesPart });
export const KINDS = Object.freeze({ scatter: scatterKind, crossTable: crossKind });
/** The page's markings and system filters, each its people's name (mockup fix ④). */
export const MARKINGS = Object.freeze([{ name: 'marking:start', label: 'Start' }, { name: 'marking:pick', label: 'Pick' }]);
export const FILTERS = Object.freeze([{ name: 'filter:1', label: 'Filter' }]);
const SAVED = 'testbed:visuals';

export const LAYOUT = Object.freeze({
  columns: 'minmax(0, 1fr) minmax(0, 1fr) 252px', rows: '44px minmax(0, 1fr) minmax(0, 1fr) 32px', gap: '2px',
  panels: [
    { id: 'start', part: 'start', at: { column: 1, row: 1, columnSpan: 2 }, writes: 'marking:start' },
    { id: 'scatter-1', part: 'visual', kind: 'scatter', at: { column: 1, row: 2, rowSpan: 2 }, row: null,
      start: { marking: 'marking:start' }, system: 'filter:1', filter: [], encode: {}, reads: 'marking:pick', writes: 'marking:pick' },
    { id: 'cross-1', part: 'visual', kind: 'crossTable', at: { column: 2, row: 2 }, row: null,
      start: { marking: 'marking:start' }, system: 'filter:1', filter: [], encode: {}, reads: 'marking:pick', writes: 'marking:pick' },
    { id: 'basket', part: 'basket', at: { column: 2, row: 3 }, reads: 'marking:pick', writes: 'marking:pick', title: 'Marked' },
    { id: 'status', part: 'status', at: { column: 1, row: 4, columnSpan: 2 } },
    { id: 'properties', part: 'properties', at: { column: 3, row: 1, rowSpan: 2 } },
    { id: 'filters', part: 'filters', at: { column: 3, row: 3, rowSpan: 2 }, title: 'Filters', options: { name: 'filter:1' } },
  ],
});

/** Whether a slot's value is one-valued by declaration - its last step's predicate declared cardinality one. */
export function oneValuedBy(predicates) {
  const one = new Set((predicates || []).filter((p) => p && (p.cardinality === 'one' || (p.object && p.object.cardinality === 'one'))).map((p) => p.name));
  return (slot) => Boolean(slot && slot.steps && slot.steps.length && one.has(slot.steps[slot.steps.length - 1].predicate));
}

/** The layout with the saved visuals laid over it (by id) and every visual's empty row type the first declared one. */
export function laidOut(layout, saved, entities) {
  const byId = new Map((saved || []).map((d) => [d.id, d]));
  const first = ((entities || [])[0] || {}).type || null;
  return { ...layout, panels: layout.panels.map((p) => {
    // A saved entry is a declaration; the page's dependencies (`options`) are the layout's, never the saved one's.
    const d = byId.has(p.id) ? { ...p, ...byId.get(p.id), at: p.at, part: p.part, options: p.options } : p;
    return d.part === 'visual' && !d.row ? { ...d, row: first } : d;
  }) };
}

/** Every entry its page dependencies (the board's bindLoaders, for this page): its own options win. */
export function bound(layout, shared) {
  return { ...layout, panels: layout.panels.map((p) => ({ ...p, options: { ...shared, ...(p.options || {}) } })) };
}

/**
 * Boot the page. `deps` - doc, host, apiBase, fetchImpl, charts ({init}), storage (localStorage or null), theme.
 * @returns {{shell, markings, filters, stats, active, hubs, save: Function}}
 */
export async function boot(deps) {
  const { doc, host, apiBase = '', fetchImpl, storage = null } = deps;
  const theme = deps.theme === 'light' ? 'light' : 'dark';
  // On the page's root: the Spotfire tokens (tokens.css) follow it, the header and the picker (on the body) too.
  const root = (doc.documentElement && doc.documentElement.style) ? doc.documentElement : host;
  root.setAttribute('data-tb-theme', theme);
  // The site's tokens the same way: the walk page's parts on this page (the start row, its picker) wear them (lead 10-13:
  // the open picker a white box on the dark page).
  root.setAttribute('data-theme', theme);
  const markings = new MarkingStore();
  const filters = new KeyedStore({ 'filter:1': [] });
  const stats = new KeyedStore();
  const active = new KeyedStore();
  const hubs = new HubBook();
  const names = new Map();
  const declaration = await fetchDeclaration({ apiBase, fetchImpl });
  const entities = () => (declaration.ok ? declaration.entities : []);
  const pickerHost = doc.createElement('div');
  pickerHost.className = 'sf-pop-host';
  pickerHost.style.display = 'none';
  (doc.body || host).appendChild(pickerHost);
  const picker = new SlotPicker(pickerHost, { doc });
  let saved = null;
  try { saved = storage ? JSON.parse(storage.getItem(SAVED) || 'null') : null; } catch (e) { saved = null; }
  const shell = new GridShell(host, { doc, markings, parts: PARTS });
  const shared = {
    kinds: KINDS, filters, stats, active, hubs, names, charts: deps.charts,
    fetchWalk: (params) => fetchSubgraph({ apiBase, fetchImpl, ...params }),
    walkParams: {},
    oneValued: oneValuedBy(declaration.ok ? declaration.predicates : []),
    openPicker: (at) => picker.open(at),
    partOf: (id) => shell.partOf(id),
    entities, markingNames: MARKINGS, filterNames: FILTERS,
    askKeys: ({ type, startsWith }) => fetchKeyValues({ apiBase, fetchImpl, type, startsWith, limit: 20 }),
  };
  const layout = laidOut(LAYOUT, saved, entities());
  shell.render(bound(layout, shared));
  const firstVisual = layout.panels.find((p) => p.part === 'visual');
  if (firstVisual) active.set('active', firstVisual.id);
  /** The visuals' declarations as they stand - what Save writes and the next boot lays over the layout. */
  const declarations = () => layout.panels.filter((p) => p.part === 'visual').map((p) => shell.partOf(p.id).declaration());
  const save = () => { const all = declarations(); try { if (storage) storage.setItem(SAVED, JSON.stringify(all)); } catch (e) { /* not kept */ } return all; };
  if (typeof doc.addEventListener === 'function') {
    doc.addEventListener('mousedown', (event) => {
      if (pickerHost.style.display === 'none') return;
      const path = typeof event.composedPath === 'function' ? event.composedPath() : [event.target];
      if (!path.includes(pickerHost) && !(event.target && event.target.closest && event.target.closest('.sf-pill, .sf-plus'))) picker.close();
    });
  }
  return { shell, markings, filters, stats, active, hubs, names, save, declarations, picker };
}

// ── the browser ──
if (typeof document !== 'undefined' && document.getElementById('tb-board')) {
  echarts.use([ScatterChart, GridComponent, BrushComponent, CanvasRenderer]);
  const params = new URLSearchParams(window.location.search);
  let storage = null;
  try { storage = window.localStorage; } catch (e) { storage = null; }
  import('../config.js').then(({ API_BASE }) => boot({ doc: document, host: document.getElementById('tb-board'), apiBase: API_BASE,
    charts: { init: (el) => echarts.init(el, null, { renderer: 'canvas' }) }, storage, theme: params.get('theme') })).then((page) => {
    const save = document.getElementById('tb-save');
    save.addEventListener('click', () => { page.save(); save.textContent = 'Saved'; setTimeout(() => { save.textContent = 'Save'; }, 1200); });
    document.getElementById('tb-reset').addEventListener('click', () => {
      try { if (storage) storage.removeItem(SAVED); } catch (e) { /* nothing kept */ }
      window.location.reload();
    });
    const theme = document.getElementById('tb-theme');
    theme.textContent = params.get('theme') === 'light' ? 'Dark' : 'Light';
    theme.addEventListener('click', () => { params.set('theme', params.get('theme') === 'light' ? 'dark' : 'light'); window.location.search = params.toString(); });
  });
}
