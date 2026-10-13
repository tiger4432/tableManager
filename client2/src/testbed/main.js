// THE TESTBED PAGE (lead aca803a7a ㄴ): the R&D board's frame - a layout of declarations, one marking store - holding
// the visual part's kinds, the status bar, the filters panel, the properties panel and the left bar that adds a visual.
// The layout is data; Save keeps the tree and the visuals' declarations and a reopen draws the same picture from them.

import * as echarts from 'echarts/core';
import { ScatterChart } from 'echarts/charts';
import { GridComponent, BrushComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { GridShell } from '../rnd_board/grid_shell.js';
import { MarkingStore } from '../rnd_board/marking_store.js';
import { fetchSubgraph, fetchDeclaration, fetchKeyValues } from '../rnd_board/api.js';
import { VisualPart, markingsOf, withoutMarking } from './visual_part.js';
import { StartPart } from './start_part.js';
import { BannerPart } from './banner_part.js';
import { StatusPart } from './status_part.js';
import { FiltersPart } from './filters_part.js';
import { PropertiesPart } from './properties_part.js';
import { SlotPicker } from './picker.js';
import { HubBook, isHubId } from './hubs.js';
import { KeyedStore } from './keyed_store.js';
import { GraphBook, MarkingLayers } from './marking_layer.js';
import { kind as scatterKind } from './kinds/scatter.js';
import { kind as crossKind } from './kinds/cross_table.js';
import { kind as tableKind } from './kinds/table.js';
import { kind as mapKind } from './kinds/map.js';
import { kind as sheetKind } from './kinds/sheet.js';

export const PARTS = Object.freeze({ visual: VisualPart, start: StartPart, status: StatusPart, filters: FiltersPart,
  properties: PropertiesPart, banner: BannerPart });
/** The kinds, in the add window's order (Spotfire's: Table, Cross table, …, Scatter plot). */
export const KINDS = Object.freeze({ table: tableKind, crossTable: crossKind, scatter: scatterKind, map: mapKind, sheet: sheetKind });
/** The page's markings when nothing is saved - a declaration the people add to, rename, colour and delete (Spotfire's
 *  Edit › Markings; Pick in Spotfire's default marking green). Its system filters. Each its people's name (mockup fix ④). */
export const MARKINGS = Object.freeze([{ name: 'marking:start', label: 'Start', color: '#F08C00' },
  { name: 'marking:pick', label: 'Pick', color: '#00A650' }]);
/** A new marking's colours, in turn (the first not in use). */
export const MARKING_COLORS = Object.freeze(['#3B82F6', '#D63384', '#8B5CF6', '#14B8A6', '#E11D48', '#84CC16']);
export const FILTERS = Object.freeze([{ name: 'filter:1', label: 'Filter' }]);
const SAVED = 'testbed:visuals';

/** A visual as the page seats one - the layout's and one the left bar adds: walked from the start, the page's filter,
 *  showing and writing the pick. Its kind, id and row type are its own. */
export const VISUAL = Object.freeze({ part: 'visual', row: null, start: { marking: 'marking:start' }, system: 'filter:1', filter: [],
  encode: {}, writes: 'marking:pick' });

// The page (lead 10-13, Spotfire's): the visualization area is a split tree of the visuals; the left bar, the start row,
// the status bar, the properties and the filters are docked chrome around it (rnd_board/grid_shell.js).
export const LAYOUT = Object.freeze({
  gap: 'var(--sf-gap)',
  panels: [
    { id: 'banner', part: 'banner', dock: 'left', size: 'var(--sf-banner-w)' },
    { id: 'start', part: 'start', dock: 'top', size: '44px', writes: 'marking:start' },
    { ...VISUAL, id: 'scatter-1', kind: 'scatter' },
    { ...VISUAL, id: 'cross-1', kind: 'crossTable' },
    // The marked rows (owner 10-13 «ㄴ 은 근원부품 테이블에 마킹제한 적용한것»): a table of the pick - limited by it, empty
    // while nothing is picked - over every row the start reaches, no filter.
    { ...VISUAL, id: 'marked', kind: 'table', title: 'Marked', system: null,
      limit: { markings: ['marking:pick'], must: 'all', none: 'empty' },
      encode: { col1: { steps: [], value: { on: 'label', name: 'name' }, words: ['name'] } } },
    { id: 'status', part: 'status', dock: 'bottom', size: 'var(--sf-status-h)' },
    { id: 'properties', part: 'properties', dock: 'right', size: '252px' },
    { id: 'filters', part: 'filters', dock: 'right', size: '252px', title: 'Filters', options: { name: 'filter:1' } },
  ],
  root: { split: 'row', children: [{ id: 'scatter-1', size: 1 },
    { split: 'column', size: 1, children: [{ id: 'cross-1', size: 1 }, { id: 'marked', size: 1 }] }] },
});

/** Whether a slot's value is one-valued by declaration - its last step's predicate declared cardinality one. */
export function oneValuedBy(predicates) {
  const one = new Set((predicates || []).filter((p) => p && (p.cardinality === 'one' || (p.object && p.object.cardinality === 'one'))).map((p) => p.name));
  return (slot) => Boolean(slot && slot.steps && slot.steps.length && one.has(slot.steps[slot.steps.length - 1].predicate));
}

/**
 * The layout with a save laid over it, every visual's empty row type the first declared one. A save is { root, visuals }:
 * the tree and each visual's declaration, the docked chrome staying the layout's; an older one - the visuals by id, an
 * array - lays its visuals over the layout's own tree.
 */
export function laidOut(layout, saved, entities) {
  const first = ((entities || [])[0] || {}).type || null;
  // A visual walked from a written node (a sheet's key) takes its row type from that node - not the first declared one
  // (18766 10-14: a sheet saved and reopened walked from its key to the first type and drew every cell empty).
  const typed = (d) => (d.part === 'visual' && !d.row && !(d.start && d.start.node) ? { ...d, row: first } : d);
  if (saved && !Array.isArray(saved) && saved.root !== undefined) {
    return { ...layout, root: saved.root, panels: [...layout.panels.filter((p) => p.dock), ...(saved.visuals || []).map(typed)] };
  }
  const byId = new Map((saved || []).map((d) => [d.id, d]));
  // A saved entry is a declaration; the page's dependencies (`options`) are the layout's, never the saved one's.
  return { ...layout, panels: layout.panels.map((p) => typed(byId.has(p.id) ? { ...p, ...byId.get(p.id), part: p.part, options: p.options } : p)) };
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
  const markingList = new KeyedStore({ list: ((saved && !Array.isArray(saved) && saved.markings) || MARKINGS).map((m) => ({ ...m })) });
  // The page's relations (Spotfire's Relations: a node type, a predicate, a node type, one way or both) - what a marking
  // spreads along; the graph its parts walked; the layers every part asks «is this marked» (marking_layer.js).
  const relations = new KeyedStore({ list: ((saved && !Array.isArray(saved) && saved.relations) || []).map((r) => ({ ...r })) });
  const layers = new MarkingLayers({ markings, hubs, graph: new GraphBook(), relations });
  /** The panels that name a marking - received or emitted (visual_part.markingsOf). */
  const usersOf = (name) => shell.layoutNow().panels.filter((p) => {
    const { start, limit, emits } = markingsOf(p);
    return start === name || emits === name || limit.includes(name);
  });
  const titleOf = (p) => (shell.partOf(p.id) && shell.partOf(p.id).titleWords ? shell.partOf(p.id).titleWords() : p.title || p.id);
  /** Spotfire's Edit › Markings: a new one (its name the next free, its colour the next unused), a label or colour
   *  changed, one deleted - the visuals that walked from it walk from «All», limits lose it, a part writing it writes
   *  none. One a docked panel names (the start row writes Start) is not deleted: the reply names it. */
  const markingBook = {
    list: markingList,
    add() {
      const list = markingList.get('list');
      let n = list.length + 1;
      while (list.some((m) => m.name === `marking:${n}` || m.label === `Marking (${n})`)) n += 1;
      const color = MARKING_COLORS.find((c) => !list.some((m) => m.color === c)) || MARKING_COLORS[0];
      markingList.set('list', [...list, { name: `marking:${n}`, label: `Marking (${n})`, color }]);
      return `marking:${n}`;
    },
    /** A label or colour changed - a label another marking has is refused, the reply naming it. */
    edit(name, patch) {
      const list = markingList.get('list');
      if (patch.label !== undefined && list.some((m) => m.name !== name && m.label === patch.label)) return { refused: `Another marking is named ${patch.label}` };
      markingList.set('list', list.map((m) => (m.name === name ? { ...m, ...patch } : m)));
      return { refused: null };
    },
    users: (name) => usersOf(name).map(titleOf),
    remove(name) {
      const users = usersOf(name);
      const fixed = users.filter((p) => p.part !== 'visual');
      if (fixed.length) return { removed: false, users: fixed.map(titleOf) };
      for (const p of users) shell.partOf(p.id).setDeclaration(withoutMarking(shell.partOf(p.id).declaration(), name));
      markings.clear(name);
      markingList.set('list', markingList.get('list').filter((m) => m.name !== name));
      return { removed: true, users: users.map(titleOf) };
    },
  };
  const shared = {
    kinds: KINDS, filters, stats, active, hubs, names, charts: deps.charts,
    fetchWalk: (params) => fetchSubgraph({ apiBase, fetchImpl, ...params }),
    walkParams: {},
    oneValued: oneValuedBy(declaration.ok ? declaration.predicates : []),
    openPicker: (at) => picker.open(at),
    partOf: (id) => shell.partOf(id),
    entities, markingList, markingBook, relations, layers, filterNames: FILTERS,
    predicates: () => (declaration.ok ? declaration.predicates : []),
    peers: () => declarations(),
    vocabulary: () => (declaration.ok ? declaration : null),
    askKeys: ({ type, startsWith }) => fetchKeyValues({ apiBase, fetchImpl, type, startsWith, limit: 20 }),
    onAdd: (kind) => add(kind),
  };
  // What was marked when it was saved - the start too, a hub with its members (Spotfire keeps the markings in the file):
  // in the stores before the parts are seated, so they walk from it.
  if (saved && !Array.isArray(saved)) {
    for (const [id, members] of Object.entries(saved.hubs || {})) hubs.put(id, members);
    for (const [name, entries] of Object.entries(saved.marks || {})) markings.replace(name, entries);
  }
  const layout = laidOut(LAYOUT, saved, entities());
  shell.render(bound(layout, shared));
  const firstVisual = layout.panels.find((p) => p.part === 'visual');
  if (firstVisual) active.set('active', firstVisual.id);
  /** A visual of a kind added where Spotfire adds one (the largest split in two), the active one now. */
  const add = (kind) => {
    let n = 1;
    while (shell.panels.has(`${kind}-${n}`)) n += 1;
    const decl = { ...VISUAL, id: `${kind}-${n}`, kind, row: ((entities()[0] || {}).type) || null };
    shell.add(bound({ panels: [decl] }, shared).panels[0]);
    active.set('active', decl.id);
    return decl.id;
  };
  /** The visuals' declarations as they stand, in the tree as it stands. */
  const declarations = () => shell.layoutNow().panels.filter((p) => p.part === 'visual');
  /** What Save writes and the next boot lays over the layout: the tree, the visuals and the markings. */
  const save = () => {
    const names = markingList.get('list').map((m) => m.name);
    const marks = Object.fromEntries(names.map((name) => [name, markings.entries(name)]).filter(([, entries]) => entries.length));
    const held = Object.fromEntries([...new Set(Object.values(marks).flat().map(([id]) => id))].filter(isHubId).map((id) => [id, hubs.membersOf(id)]));
    const kept = { root: shell.layoutNow().root, visuals: declarations(), markings: markingList.get('list'), relations: relations.get('list'), marks, hubs: held };
    try { if (storage) storage.setItem(SAVED, JSON.stringify(kept)); } catch (e) { /* not kept */ }
    return kept;
  };
  if (typeof doc.addEventListener === 'function') {
    doc.addEventListener('mousedown', (event) => {
      if (pickerHost.style.display === 'none') return;
      const path = typeof event.composedPath === 'function' ? event.composedPath() : [event.target];
      if (!path.includes(pickerHost) && !(event.target && event.target.closest && event.target.closest('.sf-pill, .sf-plus'))) picker.close();
    });
  }
  return { shell, markings, filters, stats, active, hubs, names, save, declarations, picker, add, markingBook, relations, layers };
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
    // Reset - back to what was saved (Spotfire's «Reset to saved»); Clear saved - forget it, the page's own layout next.
    document.getElementById('tb-reset').addEventListener('click', () => window.location.reload());
    document.getElementById('tb-clear').addEventListener('click', () => {
      try { if (storage) storage.removeItem(SAVED); } catch (e) { /* nothing kept */ }
      window.location.reload();
    });
    const theme = document.getElementById('tb-theme');
    theme.textContent = params.get('theme') === 'light' ? 'Dark' : 'Light';
    theme.addEventListener('click', () => { params.set('theme', params.get('theme') === 'light' ? 'dark' : 'light'); window.location.search = params.toString(); });
  });
}
