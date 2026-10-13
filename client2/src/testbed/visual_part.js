// THE VISUAL PART - one root, kinds as declarations (lead aca803a7a ㄱ, owner 「근원 부품 만들어와」). The root does what
// every kind needs: the walk from its marking, the rows of its row type, the two filters, each slot read, the marking it
// writes and the one it shows; a kind says only its slots, its title, its model and its picture, and reads its own
// fields off the declaration. The root never asks which kind it holds (owner: «kind 는 운영자가 적는 낱말이지 실행이
// 갈리는 축이 아니다»).
//
// declaration  { id, part: 'visual', kind, title?, row, start: {marking: name|null}, system: name|null,
//                filter: [conditions], limit: {markings, must, none} | null, encode: {slotKey: slot}, writes: name }
//   the markings it RECEIVES - start.marking (walked from) and limit.markings; the one it EMITS - writes, the one a press
//   marks and the one it shows marked (Spotfire's one «Marking»). markingsOf is the one place that reads the three.
//   start.marking null - «All»: every node of the row type (seed_type)
//   system - the system filter it uses (Spotfire «Use filtering from page»), null none; filter - its own final conditions
//   limit - Spotfire's «Limit data using markings» (owner 10-13): only the rows the named markings hold (limitRows)
//
// Flow (owner 10-12): system marking + system filter -> the part walks from the marking -> its own filter -> the
// markings' limit -> drawn.

import { Panel, markingIntent } from '../rnd_board/panel.js';
import { indexGraph, valuesAt } from '../walk/reach_table.js';
import { readSlot, slotWords, rawOf } from './slot.js';
import { keepNodes } from './filter.js';
import { hubId } from './hubs.js';
import { MarkingLayers } from './marking_layer.js';
import { COLOR_SLOT, legendBlock, paletteBox, paintRows } from './color_by.js';
import { LABEL_SLOT, tipSlots, tipLines, labelOf } from './tooltip.js';
import { markerSlots, unitsOf, unitOf, unitWords, markersOf, nextMarker } from './units.js';
import { routesFor, routeOf, typeOfStart, walkOfRoute, routeEnds, routeWords } from './route.js';
import { fitUnder } from '../dropdown.js';
import { seedsOf } from '../rnd_board/marking_store.js';
import { truncationAxes } from '../rnd_board/api.js';
import { paletteOf } from './palette.js';

export class VisualPart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const d = deps || {};
    // The declaration without the page's dependencies (`options` - the stores, the walk): those are the page's, not saved.
    // `reads` is not a field: the marking it shows is the one it writes (an older save's reads is dropped).
    const { options: _pageDeps, reads: _shown, ...own } = d.declaration || {};
    this.decl = JSON.parse(JSON.stringify(own));
    this.writes = this.decl.writes || null;
    this.reads = this.writes;
    // The page's declared markings ({list: [{name, label, color}]}) and the other visuals' declarations (the loop check).
    this.markingList = d.markingList || null;
    this.peers = d.peers || (() => []);
    this.loop = null;
    this.kinds = d.kinds || {};
    this.fetchWalk = d.fetchWalk;
    this.filters = d.filters;
    this.stats = d.stats;
    this.active = d.active;
    this.hubs = d.hubs;
    // THE one place «is this marked» is asked (marking_layer.js): the page's layers, or its own over its markings.
    this.layers = d.layers || new MarkingLayers({ markings: d.markings, hubs: d.hubs });
    // The page's declaration (types and predicates) - the routes from a start to the rows (route.js).
    this.vocabulary = d.vocabulary || (() => null);
    this.relationsStore = d.relations || null;
    this.names = d.names;
    this.charts = d.charts;
    // The colours a canvas draws with, read when it draws (testbed/palette.js); the page's tokens by default.
    this.palette = d.palette || (() => paletteOf(this.doc));
    this.openPicker = d.openPicker || (() => {});
    this.oneValued = d.oneValued || (() => false);
    this.walkParams = d.walkParams || {};
    this.start = this.decl.start || null;
    this.state = 'idle';
    this.answer = null;
    this.drawn = null;
    this.event = null;
    this.walking = 0;
  }

  get kind() { return this.kinds[this.decl.kind] || null; }

  /** Its kind's slots - a list, or what the kind makes of the declaration (a table's columns, the scatter's Marker by). */
  slotList() {
    const listed = this.kind ? this.kind.slots : [];
    const own = typeof listed === 'function' ? listed(this.decl.encode || {}, this.decl) : listed;
    // A kind drawing a mark a unit holds Marker by (units.js); a hub folds its rows' reads, a value record reads records.
    const unit = this.kind && this.kind.units ? unitOf(this.decl) : 'node';
    const read = unit === 'node' ? own : own.map((s) => ({ ...s, folds: true, records: unit === 'record' }));
    // Color by is the root's - every kind holds it (color_by.js).
    // Color by, Label by and the Tooltip slots too (tooltip.js) - the root's, every kind's.
    return [...read, ...(this.kind && this.kind.units ? markerSlots(this.decl.encode) : []), COLOR_SLOT, LABEL_SLOT, ...tipSlots(this.decl.encode)];
  }

  mount() {
    super.mount();
    const off = [];
    // The system filter changed: from its start side again - a node it let go comes back when it widens.
    if (this.filters) off.push(this.filters.subscribe('*', (name) => { if (name === this.decl.system) this.load(); }));
    if (this.active) off.push(this.active.subscribe('active', () => this.paintActive()));
    // A marking's colour changed: its marked points and lines.
    if (this.markingList) off.push(this.markingList.subscribe('list', () => this.refold()));
    // The relations changed: every marking's layer is another.
    if (this.relationsStore) off.push(this.relationsStore.subscribe('list', () => this.refold()));
    this._offs = off;
    this.listenLimit();
    if (this.host && typeof this.host.addEventListener === 'function') {
      this.host.addEventListener('mousedown', () => { if (this.active) this.active.set('active', this.decl.id); });
    }
    this.load();
  }

  destroy() {
    for (const off of this._offs || []) off();
    for (const off of this._limitOffs || []) off();
    this.closePalette();
    // Closed while it was the active one: no part is.
    if (this.active && this.active.get('active') === this.decl.id) this.active.set('active', null);
    if (this.drawn) this.drawn.dispose();
    this.drawn = null;
    super.destroy();
  }

  /** The declaration as it stands - what Save writes and a reopen reads back. */
  declaration() { return JSON.parse(JSON.stringify(this.decl)); }

  /** A changed declaration: a new start, row type, route or system filter walks again; anything else folds again. One that
   *  closes a loop of markings with the page's other visuals is refused and the loop named (`this.loop`). */
  setDeclaration(asked) {
    const { reads: _shown, ...next } = asked;
    this.loop = chainLoop([...this.peers().filter((d) => d.id !== next.id), next]);
    if (this.loop) { this.publish(); return false; }
    const walkAgain = JSON.stringify([next.start, next.row, next.system, next.route || null]) !== JSON.stringify([this.decl.start, this.decl.row, this.decl.system, this.decl.route || null]);
    const before = this.decl;
    this.decl = JSON.parse(JSON.stringify(next));
    this.start = this.decl.start || null;
    this.writes = this.decl.writes || null;
    this.listen(before);
    this.listenLimit();
    if (walkAgain) this.load(); else this.refold();
    return true;
  }

  /** The markings it hears follow its declaration: the one it writes (and shows), the one it starts from. */
  listen(before) {
    if (!this.markings) return;
    if ((before.writes || null) !== (this.decl.writes || null)) {
      if (this._unsubscribe) this._unsubscribe();
      this.reads = this.decl.writes || null;
      this._unsubscribe = this.reads ? this.markings.subscribe(this.reads, () => this.onMarkingChanged()) : null;
    }
    const was = before.start && before.start.marking;
    const now = this.start && this.start.marking;
    if (was !== now) {
      if (this._startOff) this._startOff();
      this._startOff = now && now !== this.reads ? this.markings.subscribe(now, () => this.onStartChanged()) : null;
    }
  }

  /** The markings its limit names and its expressions asked (Marked) that it does not hear already (the one it shows,
   *  the one it starts from): a change folds again. */
  listenLimit() {
    for (const off of this._limitOffs || []) off();
    const heard = new Set([this.reads, this.start && this.start.marking]);
    const names = [...new Set([...((this.decl.limit && this.decl.limit.markings) || []), ...(this.askedMarkings || [])])].filter((n) => !heard.has(n));
    this._limitOffs = this.markings ? names.map((n) => this.markings.subscribe(n, () => this.refold())) : [];
  }

  setSlot(key, slot) {
    const encode = { ...(this.decl.encode || {}) };
    if (slot) encode[key] = slot; else delete encode[key];
    this.setDeclaration({ ...this.decl, encode });
  }

  onStartChanged() { this.load(); }
  onMarkingChanged() { this.refold(); }
  onResize() { if (this.drawn) this.drawn.resize(); else this.render(); }

  /** The seeds: «All» - the row type described; else the start marking's entries, a hub its members. */
  seeds() {
    const name = this.start && this.start.marking;
    if (!name) return this.decl.row ? { all: true } : null;
    const got = seedsOf(this.markings.entries(name), (id) => this.hubs.open(id));
    return got.positive.length ? got : null;
  }

  /** The routes from the start's type to the row type, and the one it takes (route.js) - none when it starts from All or
   *  no route is known. */
  routes() {
    const name = this.start && this.start.marking;
    const first = name && this.markings ? this.markings.entries(name)[0] : null;
    return first ? routesFor(this.vocabulary(), typeOfStart(first[0]), this.decl.row) : [];
  }

  route() { return routeOf(this.decl, this.routes()); }

  /** Its start's node type - the first entry's (a hub its row type); none known - null. */
  startType() {
    const name = this.start && this.start.marking;
    const first = name && this.markings ? this.markings.entries(name)[0] : null;
    return first ? typeOfStart(first[0]) : null;
  }

  /** Its rows in a walk's answer: the route's ends from the seeds it walked from; with no route, every node of its row
   *  type the walk reached. */
  rowsOf(answer) {
    if (this.walkedRoute && this.walkedSeeds) return routeEnds(answer, this.walkedSeeds, this.walkedRoute);
    return ((answer && answer.nodes) || []).filter((n) => n.type === this.decl.row).map((n) => n.id);
  }

  systemConditions() {
    return (this.decl.system && this.filters && this.filters.get(this.decl.system)) || [];
  }

  async load() {
    let seeds = this.seeds();
    if (!seeds) { this.state = 'no-start'; this.answer = null; this.publish(); this.render(); this.prune(new Set()); return; }
    const ticket = (this.walking += 1);
    this.state = 'walking';
    this.render();
    this.walkedRoute = seeds.all ? null : this.route();
    // No route from its start to its rows - or the route it names does not start there: said, nothing drawn, no other
    // start walked instead.
    const startType = seeds.all ? null : this.startType();
    if (!seeds.all && !this.walkedRoute && startType && (this.decl.route || this.vocabulary())) {
      this.state = 'refused';
      this.refusal = this.decl.route ? `Route ${routeWords(this.decl.route)} does not start from ${startType}, the start`
        : `No route from ${startType} to ${this.decl.row}`;
      this.answer = null;
      this.publish();
      this.render();
      this.prune(new Set());
      return;
    }
    // A route starts from one type (its start's first): starts of another type are not walked, and said (QA 10-14).
    this.otherStarts = null;
    if (this.walkedRoute) {
      const from = this.walkedRoute.chain[0];
      const other = (seeds.positive || []).filter((id) => { const type = typeOfStart(id); return type && type !== from; });
      if (other.length) {
        this.otherStarts = { from, n: other.length };
        seeds = { ...seeds, positive: seeds.positive.filter((id) => !other.includes(id)) };
      }
    }
    let positive = seeds.positive || [];
    // The walk from every seed does not hang on the system filter: one in hand for the same seeds is taken again (a
    // filter changed), and only the start side is judged anew.
    const asked = JSON.stringify([seeds, this.decl.row, this.walkedRoute]);
    let res = this.seedWalk && this.seedWalk.asked === asked ? this.seedWalk.res : await this.walkFrom(seeds);
    if (ticket !== this.walking) return;
    if (res.ok) this.seedWalk = { asked, res };
    this.startDropped = 0;
    // The system filter's start side: the marking's nodes of a condition's type are kept first, and the walk is taken
    // again from the kept ones - a dropped wafer's dies do not come in (lead 5835e6714).
    if (res.ok && !seeds.all) {
      const index = indexGraph(res.body);
      const inside = insideOf(res.body);
      const { kept, dropped } = keepNodes(index, inside, positive, this.systemConditions(), this.oneValued, (words, id) => this.layers.marked(this.markingNamed(words), id));
      if (dropped) {
        this.startDropped = dropped;
        positive = kept;
        res = kept.length ? await this.walkFrom({ positive: kept, negative: seeds.negative }) : { ok: true, body: { nodes: [], edges: [] } };
        if (ticket !== this.walking) return;
      }
    }
    if (!res.ok) {
      this.state = 'refused';
      this.refusal = refusalWords(res);
      this.answer = null;
      this.publish();
      this.render();
      return;
    }
    this.walkedSeeds = positive;
    this.layers.graph.add(res.body);
    this.answer = res.body;
    this.state = 'ready';
    this.refold();
    this.prune(insideOf(res.body));
  }

  /** Its data walked anew: what its marking holds that the new data does not hold leaves the marking (Spotfire: rows
   *  filtered out are no longer marked); a part that starts from that marking walks next - a chain follows in one pass. */
  prune(inside) {
    if (!this.writes || !this.markings) return;
    const entries = this.markings.entries(this.writes);
    const kept = entries.filter(([id]) => this.hubs.open(id).some((n) => inside.has(n)));
    if (kept.length !== entries.length) this.markings.replace(this.writes, kept);
  }

  /** The colour of the marking it writes - its marked points and lines (Spotfire's marking colour). */
  markColor() {
    const m = ((this.markingList && this.markingList.get('list')) || []).find((x) => x.name === this.writes);
    return (m && m.color) || null;
  }

  walkFrom(seeds) {
    // The walk's budget: the page's, then the declaration's own (`walk`: node_limit, hops - the server's names).
    // the steps are the route's (walkOfRoute) - a declaration's walk budget is its node_limit
    const { hops: _steps, ...budget } = this.decl.walk || {};
    const base = { ...this.walkParams, ...budget };
    // Along its route: the route's predicates and steps and its slots' (route.js walkOfRoute).
    const along = !seeds.all && this.walkedRoute ? walkOfRoute(this.walkedRoute, this.decl.encode) : {};
    const params = seeds.all ? { ...base, seed_type: this.decl.row }
      : { ...base, ...along, nodeId: seeds.positive[0], positive: seeds.positive, negative: seeds.negative || [] };
    return this.fetchWalk(params);
  }

  /** Rows, filters, slots and the kind's model again from the walk in hand - a filter, a marking or a slot changed. */
  refold() {
    if (!this.answer || !this.kind) { this.render(); return; }
    const index = indexGraph(this.answer);
    const inside = insideOf(this.answer);
    this.index = index;
    this.inside = inside;
    const received = this.rowsOf(this.answer);
    if (this.names) for (const n of this.answer.nodes || []) this.names.set(n.id, { type: n.type, label: n.label || n.id });
    // An expression's Marked("name") - in a slot, a fold, a filter: the marking layer; a row it cannot know is counted,
    // the markings asked heard. The calculator asks (name, node) -> true · false · null (expression.js Marked).
    const asked = new Set();
    const unknown = new Set();
    const askMarked = (words, id) => {
      const name = this.markingNamed(words);
      asked.add(name);
      const v = this.layers.marked(name, id);
      if (v === null) unknown.add(id);
      return v;
    };
    const sys = this.systemConditions().filter((c) => c.row === this.decl.row);
    const afterSystem = keepNodes(index, inside, received, sys, this.oneValued, askMarked);
    const afterPart = keepNodes(index, inside, afterSystem.kept, this.decl.filter || [], this.oneValued, askMarked);
    // The picker's rows: the filters' - a limit takes rows out of the picture, not out of what a column can read.
    this.rowIds = afterPart.kept;
    const limited = limitRows(afterPart.kept, this.decl.limit, this.layers);
    const encode = this.decl.encode || {};
    const rows = limited.map((id) => {
      const node = index.nodes.get(id) || {};
      const reads = {};
      const raw = {};
      for (const s of this.slotList()) {
        const slot = encode[s.key];
        if (!slot) continue;
        reads[s.key] = readSlot(index, inside, id, slot, this.oneValued(slot), askMarked);
        if (s.folds) raw[s.key] = rawOf(index, inside, id, slot, Boolean(s.records));
      }
      return { id, label: node.label || id, reads, raw };
    });
    const marked = (id) => this.layers.marked(this.reads, id) === true;
    // Each row's colour and each mark's paint - the root's, once (color_by.js); the units a kind draws a mark of (units.js).
    const { colors, colored, paint } = paintRows(rows, { palette: this.palette(), declaration: this.decl, marked, markColor: this.markColor() });
    this.colors = colors;
    // the colours given to categories not declared yet are kept in the declaration - Save keeps them, more categories
    // later leave them where they are (a declaration field, no walk)
    if (colors.any && Object.keys(colors.assigned).length) this.decl = { ...this.decl, colors: { ...(this.decl.colors || {}), ...colors.assigned } };
    const units = this.kind.units ? unitsOf(rows, this.decl, this.slotList().map((s) => s.key), this.kind.units.record, askMarked) : rows;
    // what a tooltip and a label read: the marks the kind draws (units) and the rows (a mark a kind groups itself)
    this.rowsById = new Map(rows.map((r) => [r.id, r]));
    this.unitsById = new Map(units.map((u) => [u.id, u]));
    const label = (mark) => labelOf(mark, { decl: this.decl, rowsById: this.rowsById, marked: (ids) => ids.some(marked) });
    this.model = this.kind.model(units, { paint, colored, askMarked, label, palette: this.palette(), declaration: this.decl });
    // Hidden - the marked rows the FILTERS hide; one the limit leaves out is the limit's, not hidden.
    const shown = new Set(afterPart.kept);
    const hidden = new Set([...received.filter((id) => !shown.has(id) && marked(id))]).size;
    // M - the rows the walk brought; a, b and c - what each layer took from them (lead 5835e6714). The start side's drops
    // are not among M: they were never walked from.
    this.counts = { rows: limited.length, of: received.length, system: afterSystem.dropped, startDropped: this.startDropped || 0, otherStarts: this.otherStarts,
      part: afterPart.dropped, limit: afterPart.kept.length - limited.length, marked: received.filter(marked).length, hidden,
      columns: Object.keys(encode).length, source: this.decl.row,
      // the drawn rows an expression slot left empty because an operator met a text that is not a number (lead 10-13 ①)
      notNumber: rows.filter((r) => Object.values(r.reads).some((read) => read.notNumber)).length,
      // the rows an expression's Marked could not answer - a relation's edge of theirs not walked yet
      unknown: unknown.size,
      // The board's one reading of a cut walk (rnd_board/api.js truncationAxes).
      cut: (truncationAxes(this.answer.truncated, { hopsChosen: false }) || []).length > 0 };
    if ([...asked].join() !== [...(this.askedMarkings || [])].join()) { this.askedMarkings = asked; this.listenLimit(); }
    this.publish();
    this.render();
  }

  /** A marking's people's name. */
  markingLabel(name) {
    const m = ((this.markingList && this.markingList.get('list')) || []).find((x) => x.name === name);
    return m ? m.label : name;
  }

  /** A marking by the words an expression names it: its label (the people's) or its name. */
  markingNamed(words) {
    const m = ((this.markingList && this.markingList.get('list')) || []).find((x) => x.label === words || x.name === words);
    return m ? m.name : words;
  }

  /** The part's counts for the status bar and the filters panel, under its id. */
  publish() {
    if (!this.stats) return;
    this.stats.set(this.decl.id, this.state === 'ready' && this.counts ? { ...this.counts, title: this.titleWords(), slots: this.slotSummaries() }
      : { rows: 0, of: 0, system: 0, part: 0, marked: 0, hidden: 0, columns: 0, source: this.decl.row, state: this.state, title: this.titleWords(), slots: [] });
  }

  /** Each slot's values over the received rows - what the filters panel offers a condition over. */
  slotSummaries() {
    if (!this.index || !this.kind) return [];
    const encode = this.decl.encode || {};
    const received = this.rowsOf(this.answer);
    // its slots, then the rows' own values (keys, attributes - the walk table's «+ Column» values at no step) a filter can
    // take too (the 18766 run: «+ Add filter» offered the axes only)
    const held = new Set(Object.values(encode).filter((s) => s && Array.isArray(s.steps) && !s.steps.length && s.value).map((s) => `${s.value.on}:${s.value.name}`));
    const own = valuesAt(this.index, received, []).filter((v) => !held.has(`${v.on}:${v.name}`))
      .map((value) => ({ key: `own:${value.on}:${value.name}`, slot: { steps: [], value, words: [value.on === 'label' ? 'name' : value.name] } }));
    return [...this.slotList().filter((s) => encode[s.key]).map((s) => ({ key: s.key, slot: encode[s.key] })), ...own].map(({ key, slot }) => {
      const counts = new Map();
      let empty = 0;
      for (const id of received) {
        const read = readSlot(this.index, this.inside, id, slot, this.oneValued(slot));
        const values = read.state === 'one' ? [read.value] : read.state === 'several' ? read.values : [];
        if (!values.length) empty += 1;
        for (const v of values) counts.set(JSON.stringify(v), [v, (counts.get(JSON.stringify(v)) || [v, 0])[1] + 1]);
      }
      return { key, words: slotWords(slot), slot, row: this.decl.row, values: [...counts.values()], empty };
    });
  }

  titleWords() {
    if (this.decl.title) return this.decl.title;
    return this.kind ? this.kind.title(this.decl.encode || {}, this.decl) : '';
  }

  // ── marking, through the names the declaration gives ──
  remember(event) { this.event = event || null; }
  lastEvent() { return this.event; }

  mark(ids, event) {
    if (!this.writes) return;
    const { mode, sign } = markingIntent(event || this.event);
    if (mode === 'add') { for (const id of ids) this.markings.set(this.writes, id, sign); return; }
    this.markings.replace(this.writes, ids.map((id) => [id, sign]));
  }

  markHub(where, ids, event) { this.markHubs([[where, ids]], event); }

  /** Hubs marked whole - each [where, its members], in one press. */
  markHubs(list, event) { this.mark(list.map(([where, ids]) => this.hubs.put(hubId(this.decl.row, where), ids)), event); }

  clear() { if (this.writes) this.markings.clear(this.writes); }

  // ── the picture ──
  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    if (this.drawn) { this.drawn.dispose(); this.drawn = null; }
    const root = el('section', 'sf-part');
    root.setAttribute('data-kind', this.decl.kind || '');
    if (this.markColor() && root.style && root.style.setProperty) root.style.setProperty('--sf-marked', this.markColor());
    const title = el('div', 'sf-part__title');
    // The handle a page moves the part by (grid_shell: drag the title bar onto another part's edge).
    title.setAttribute('data-part-title', '');
    title.append(el('span', 'sf-part__t', this.titleWords()));
    // its description - one line under the title (base set 1)
    const said = (this.decl.description || '').trim();
    const body = el('div', 'sf-part__body');
    root.append(title, ...(said ? [el('div', 'sf-part__desc', said)] : []), body);
    this.host.replaceChildren(root);
    this.root = root;
    this.paintActive();
    if (!this.kind) { body.append(el('div', 'sf-say', `Unknown kind: ${this.decl.kind}`)); return; }
    if (this.state !== 'ready' || !this.model) {
      const from = this.start && this.start.marking;
      const words = { 'no-start': from ? `Mark ${this.markingLabel(from)}` : 'Mark a start', walking: 'Walking…', refused: this.refusal || 'Walk refused', idle: '' }[this.state] || '';
      body.append(el('div', 'sf-say', words));
      return;
    }
    // THE TEMPLATE (ROOT_PART_BASE_SET: the root is the template, a kind the visible area): the pill trays round the
    // area - each slot a kind puts on a tray (`tray`: top, left, bottom; `plus`: one more), the kind's note under it - and
    // the legend beside it: Marker by (a kind drawing a mark a unit), Color by.
    body.classList.add('sf-frame');
    const trays = Object.fromEntries(['top', 'left', 'bottom'].map((side) => [side, el('div', `sf-frame__tray sf-frame__${side}`)]));
    // a hub whose rows say several values on a slot with no reduce: what to do about it
    const hint = this.kind.units && unitOf(this.decl) === 'hub' && this.model.several ? 'pick a reduce (Avg · Count · Latest …)' : '';
    const note = [this.model.note, hint].filter(Boolean).join(' - ');
    if (note) trays.bottom.append(el('span', 'sf-note', note));
    const pills = Object.fromEntries(Object.entries(trays).map(([side, tray]) => { const g = el('div', 'sf-frame__pills'); tray.append(g); return [side, g]; }));
    for (const s of this.slotList().filter((x) => x.tray)) {
      pills[s.tray].append(this.pill(s.key, { vertical: s.tray === 'left' }));
      if (s.plus) pills[s.tray].append(this.plus(s.key));
    }
    const area = el('div', 'sf-frame__area');
    const legend = el('div', 'sf-legend');
    if (this.kind.units) {
      const encode = this.decl.encode || {};
      const held = markersOf(encode);
      const line = el('div', 'sf-legend__row');
      if (held.length) line.append(...held.map((k) => this.pill(k)), this.plus(nextMarker(encode)));
      else line.append(this.pill(nextMarker(encode), { words: unitWords(this.decl) }));
      legend.append(el('div', 'sf-legend__ttl', 'Marker by:'), line);
    }
    legend.append(legendBlock(this.colors, { doc, pill: (key, opts) => this.pill(key, opts), plus: (key) => this.plus(key),
      words: (key) => slotWords((this.decl.encode || {})[key]), markHub: (where, ids, event) => this.markHub(where, ids, event),
      openPalette: (category, anchor) => this.openPalette(category, anchor) }));
    body.append(trays.top, trays.left, area, trays.bottom, legend);
    this.drawn = this.kind.render(area, this.model, {
      doc, palette: this.palette(), charts: this.charts,
      words: (key) => slotWords((this.decl.encode || {})[key]),
      plus: (key) => this.plus(key),
      // what is under the pointer - {id} a mark it was handed, {ids} rows it grouped; null nothing (tooltip.js)
      hover: (mark, event) => this.showTip(mark, event),
      mark: (ids, event) => this.mark(ids, event),
      markHub: (where, ids, event) => this.markHub(where, ids, event),
      markHubs: (list, event) => this.markHubs(list, event),
      clear: () => this.clear(),
      // A field of the kind's own (a table's sort), written into the declaration - Save keeps it.
      declare: (patch) => this.setDeclaration({ ...this.decl, ...patch }),
      remember: (event) => this.remember(event),
      lastEvent: () => this.lastEvent(),
    });
  }

  /** A slot's «+» - pressed, its picker. */
  plus(key) {
    const p = this.doc.createElement('button');
    p.className = 'sf-plus';
    p.textContent = '+';
    p.type = 'button';
    p.title = 'Add one more column';
    p.addEventListener('click', () => this.openPicker({ part: this, key, anchor: p }));
    return p;
  }

  /** A category's colour picked from the palette under its legend circle (Spotfire's) - the declaration's `colors`. */
  openPalette(category, anchor) {
    const doc = this.doc;
    this.closePalette();
    const current = ((this.decl.colors || {})[category]) || ((this.colors.categories.find((c) => c.name === category) || {}).fill);
    const host = doc.createElement('div');
    host.className = 'sf-pop-host';
    host.append(paletteBox(doc, this.palette(), current, (fill) => {
      this.closePalette();
      this.setDeclaration({ ...this.decl, colors: { ...(this.decl.colors || {}), [category]: fill } });
    }));
    (doc.body || this.host).appendChild(host);
    if (anchor && anchor.getBoundingClientRect) fitUnder(host, anchor, { align: 'left', gap: 4 });
    const outside = (event) => { if (!(event.target && host.contains && host.contains(event.target))) this.closePalette(); };
    const key = (event) => { if (event.key === 'Escape') this.closePalette(); };
    if (typeof doc.addEventListener === 'function') { doc.addEventListener('mousedown', outside); doc.addEventListener('keydown', key); }
    this._palette = { host, off: () => { if (typeof doc.removeEventListener === 'function') { doc.removeEventListener('mousedown', outside); doc.removeEventListener('keydown', key); } } };
  }

  /** The tooltip over the part for a mark under the pointer (base set 10); none - gone. */
  showTip(mark, event) {
    if (!this.root || !this.doc) return;
    if (!this.tip) { this.tip = this.doc.createElement('div'); this.tip.className = 'sf-tip'; }
    if (!mark || !event) { this.tip.remove ? this.tip.remove() : null; return; }
    const unit = (mark.id !== undefined && this.unitsById && this.unitsById.get(mark.id)) || mark;
    const lines = tipLines({ ...unit, ids: unit.ids || mark.ids || [] }, { rowsById: this.rowsById || new Map(), slots: this.slotList(), encode: this.decl.encode || {} });
    this.tip.replaceChildren(...lines.map((line, k) => { const n = this.doc.createElement('div'); if (!k) n.className = 'sf-tip__h'; n.textContent = line; return n; }));
    const box = this.root.getBoundingClientRect ? this.root.getBoundingClientRect() : { left: 0, top: 0 };
    this.tip.style.left = `${(event.clientX || 0) - box.left + 12}px`;
    this.tip.style.top = `${(event.clientY || 0) - box.top + 12}px`;
    if (this.tip.parentNode !== this.root) this.root.appendChild(this.tip);
  }

  closePalette() {
    if (!this._palette) return;
    this._palette.off();
    if (this._palette.host.remove) this._palette.host.remove(); else if (this._palette.host.parentNode) this._palette.host.parentNode.removeChild(this._palette.host);
    this._palette = null;
  }

  /** A slot's pill - pressed, its picker. `opts.words`: a pill that only says them (no slot of the kind, nothing to pick). */
  pill(key, opts = {}) {
    const doc = this.doc;
    const p = doc.createElement('button');
    p.type = 'button';
    p.className = `sf-pill${opts.vertical ? ' sf-pill--v' : ''}`;
    const slot = (this.decl.encode || {})[key];
    p.textContent = opts.words || slotWords(slot);
    const caret = doc.createElement('span');
    caret.className = 'sf-pill__caret';
    caret.textContent = '▾';
    p.append(caret);
    if (this.slotList().some((s) => s.key === key)) p.addEventListener('click', () => this.openPicker({ part: this, key, anchor: p }));
    return p;
  }

  paintActive() {
    if (!this.root || !this.root.classList) return;
    const on = Boolean(this.active && this.active.get('active') === this.decl.id);
    if (on) this.root.classList.add('is-active'); else this.root.classList.remove('is-active');
  }
}

/**
 * Spotfire's «Limit data using markings»: the rows the named markings hold - in every one (`must: 'all'`) or in any
 * ('any'), each as its layer holds it (marking_layer.js - a hub its members, spread along the relations). When every one
 * of them is empty: all the rows (`none: 'all'`) or none ('empty'). No marking named: no limit.
 * @param {string[]} ids
 * @param {{markings: string[], must?: 'all'|'any', none?: 'all'|'empty'}|null|undefined} limit
 * @param {import('./marking_layer.js').MarkingLayers} layers
 */
export function limitRows(ids, limit, layers) {
  const names = (limit && limit.markings) || [];
  if (!names.length) return ids;
  const held = names.map((name) => layers.layer(name));
  if (held.every((layer) => !layer.members)) return limit.none === 'empty' ? [] : ids;
  const test = limit.must === 'any' ? 'some' : 'every';
  return ids.filter((id) => held[test]((layer) => layer.set.has(id)));
}

/** THE one place a declaration's markings are read: the ones it receives (`start` it walks from, `limit` it is limited
 *  by) and the one it emits (`writes`). Any panel's declaration - the start row's writes too. */
export function markingsOf(decl) {
  const d = decl || {};
  return { start: (d.start && d.start.marking) || null, limit: (d.limit && d.limit.markings) || [], emits: d.writes || null };
}

/** A declaration without a deleted marking: walked from it - «All»; limited by it - not; writing it - nothing. */
export function withoutMarking(decl, name) {
  const { start, limit, emits } = markingsOf(decl);
  const rest = limit.filter((n) => n !== name);
  return { ...decl, start: start === name ? { ...(decl.start || {}), marking: null } : decl.start,
    limit: rest.length === limit.length ? decl.limit : (rest.length ? { ...decl.limit, markings: rest } : null),
    writes: emits === name ? null : decl.writes };
}

/** A loop the visuals' markings make - a part walks from one marking and writes the next; a loop comes back to the
 *  marking it left: [marking, part id, marking, …, that marking], or null. A limit is not a step (it folds again and does
 *  not walk), so a table limited by the marking it writes (the Marked table) is not a loop. */
export function chainLoop(decls) {
  const next = new Map();
  for (const d of decls || []) {
    const { start, emits } = markingsOf(d);
    if (!start || !emits) continue;
    if (!next.has(start)) next.set(start, []);
    next.get(start).push([d.id, emits]);
  }
  const done = new Set();
  const visit = (m, path) => {
    const at = path.indexOf(m);
    if (at >= 0) return [...path.slice(at), m];
    if (done.has(m)) return null;
    for (const [id, to] of next.get(m) || []) {
      const loop = visit(to, [...path, m, id]);
      if (loop) return loop;
    }
    done.add(m);
    return null;
  };
  for (const m of next.keys()) { const loop = visit(m, []); if (loop) return loop; }
  return null;
}

/** Every node the walk holds - its nodes and its edges' ends (a type the answer did not carry still stands on a way). */
export function insideOf(answer) {
  const ids = new Set(((answer && answer.nodes) || []).map((n) => n.id));
  for (const e of (answer && answer.edges) || []) { ids.add(e.source); ids.add(e.target); }
  return ids;
}

/** A refused walk in words: the server's detail, else its status. */
function refusalWords(res) {
  const d = res && res.detail && res.detail.detail;
  if (d && typeof d === 'object') return d.message || d.reason || `Walk refused (${res.status})`;
  return typeof d === 'string' ? d : `Walk refused (${res && res.status})`;
}
