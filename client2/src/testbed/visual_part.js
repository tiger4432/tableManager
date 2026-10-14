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
//   start.marking null - «All»: every node of the row type (seed_type); start.node - one node written, «type("key", …)»
//   (a sheet's key cell, owner 3b97fcfb9), its type the row type when the declaration names none
//   system - the system filter it uses (Spotfire «Use filtering from page»), null none; filter - its own final conditions
//   limit - Spotfire's «Limit data using markings» (owner 10-13): only the rows the named markings hold (limitRows)
//
// Flow (owner 10-12): system marking + system filter -> the part walks from the marking -> its own filter -> the
// markings' limit -> drawn.

import { Panel, markingIntent } from '../rnd_board/panel.js';
import { indexGraph, valuesAt } from '../walk/reach_table.js';
import { readSlot, readSlots, slotWords, rawOf, isTimeRead, columnsOf, scaleOf, valueText, readsAt, isExpression, foldKey } from './slot.js';
import { walkingDino } from './walking_dino.js';
import { keepNodes } from './filter.js';
import { hubId, nodesOfPress } from './hubs.js';
import { MarkingLayers } from './marking_layer.js';
import { COLOR_SLOT, legendBlock, paletteBox, paintRows } from './color_by.js';
import { LABEL_SLOT, tipSlots, tipLines, labelOf } from './tooltip.js';
import { SHOW_SLOT, showItems } from './show_items.js';
import { PANEL_SLOT, panelsOf, inPanel, withPanel, extentsOf } from './trellis.js';
import { SHAPE_SLOT, SHAPE_LEGEND, shapesOf, shapeOfIds } from './shape_by.js';
import { markerSlots, unitOf, unitWords, markersOf, nextMarker, spreadUnits } from './units.js';
import { routesFor, typeOfStart } from './route.js';
import { readable, valueAsk, covers, changedSlots, chunks, walkToEnd, SEED_CHUNK } from './part_walks.js';
import { fitUnder } from '../dropdown.js';
import { seedsOf } from '../rnd_board/marking_store.js';
import { entitySeedId } from '../rnd_board/api.js';
import { compile, run } from '../expression.js';
import { paletteOf } from './palette.js';
import { ImageLoader, Thumb, imagesOf, drawsImage, IMAGES_REFUSED, TIP_IMAGE_PX } from '../image_thumb.js';
import { ImagePreview } from '../image_preview.js';

/** The row walk's key among its walks in flight. */
const ROW_WALK = Symbol('row walk');
/** The relations walk's key among its value walks - the walk line's words. */
const RELATION_WALK = 'Relations';
/** The value walks it keeps in hand after their slot moved on. */
const KEPT_WALKS = 8;

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
    // its walks (part_walks.js): a value walk a slot (and the value walks in hand, the last few) - its row walks are the
    // page's (GraphBook.walks); a request each may drop (the next of its kind); how many rows a value walk starts from at once
    this.values = new Map();
    this.valueWalks = [];
    this.aborts = new Map();
    this.seedChunk = d.seedChunk || SEED_CHUNK;
    this.start = this.decl.start || null;
    this.state = 'idle';
    this.answer = null;
    this.drawn = null;
    this.event = null;
    this.walking = 0;
    // its pictures (lead-board-14): the page's one loader, a preview of its own, a mark's turn of its images (not saved)
    this.images = d.images || new ImageLoader({ base: d.apiBase || '' });
    this.turns = new Map();
    this.previewer = null;
  }

  get kind() { return this.kinds[this.decl.kind] || null; }

  /** Its kind's slots - a list, or what the kind makes of the declaration (a table's columns, the scatter's Marker by). */
  slotList() {
    const listed = this.kind ? this.kind.slots : [];
    const own = typeof listed === 'function' ? listed(this.decl.encode || {}, this.decl) : listed;
    // A kind drawing a mark a unit holds Marker by (units.js); a hub folds its rows' reads, a value record reads records.
    const unit = this.kind && this.kind.units ? unitOf(this.decl) : 'node';
    const folded = (s) => (unit === 'node' ? s : { ...s, folds: true, records: unit === 'record' });
    // Color by, Label by and the Tooltip slots (tooltip.js) - the root's, every kind's; Top/Bottom by (show_items.js) too,
    // read the way the kind's own slots are (a hub its rows folded)
    // Shape by (shape_by.js) - a kind that draws points; a base set slot a kind says it takes not (`without`) left out
    const without = (this.kind && this.kind.without) || [];
    return [...own.map(folded), ...(this.kind && this.kind.units ? markerSlots(this.decl.encode) : []), COLOR_SLOT, ...(this.kind && this.kind.points ? [SHAPE_SLOT] : []), LABEL_SLOT, ...tipSlots(this.decl.encode),
      folded(SHOW_SLOT), PANEL_SLOT].filter((s) => !without.includes(s.key));
  }

  /** The slots it reads, by key: a slot the kind hands with its own (a sheet's cell) or the declaration's. */
  slotsHeld() {
    const encode = this.decl.encode || {};
    return Object.fromEntries(this.slotList().map((s) => [s.key, s.slot || encode[s.key]]).filter(([, slot]) => slot));
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
    if (this.relationsStore) off.push(this.relationsStore.subscribe('list', () => this.load()));
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
    this.unwatch();
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
    const slotsBefore = this.slotsHeld();
    this.decl = JSON.parse(JSON.stringify(next));
    this.start = this.decl.start || null;
    this.writes = this.decl.writes || null;
    this.listen(before);
    this.listenLimit();
    if (walkAgain) { this.load(); return true; }
    // THE SLOT SEAT (owner 10-14 «값 받는 것 바뀔 때마다 다»): each slot whose declaration changed walks its values
    // again - any slot of any kind, the kind not asked
    const changed = changedSlots(slotsBefore, this.slotsHeld());
    for (const key of changed) this.walkValues(key);
    // a slot changed - its walk is on its way: the fold on the next task (refoldSoon); anything else folds now
    if (changed.length) this.refoldSoon(); else this.refold();
    return true;
  }

  /** The fold again on the next task, once however many ask - a pick returns at once and the page paints before the
   *  fold (owner 10-15 «축 선언 누르고 걸어올 때까지 정지 - 비동기로»); a part taken off by then folds nothing. */
  refoldSoon() {
    if (this.refoldQueued) return;
    this.refoldQueued = true;
    setTimeout(() => { this.refoldQueued = false; if (this.host) this.refold(); }, 0);
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
  // a picture follows its own drawing div (watch, in render); a part not drawn yet draws into the box it is handed
  onResize() { if (!this.drawn) this.render(); }

  /** Each drawing div watched for its size - the picture in it follows (lead 10-14: a trellis panel kept a 40 x 44 canvas
   *  after the window grew). THE one place a picture is resized. */
  watch(div, drawn) {
    const RO = (this.doc && this.doc.defaultView && this.doc.defaultView.ResizeObserver) || globalThis.ResizeObserver;
    if (!RO || !drawn) return;
    const ro = new RO(() => drawn.resize());
    ro.observe(div);
    this.watches.push(ro);
  }

  unwatch() { for (const ro of this.watches || []) ro.disconnect(); this.watches = []; }

  /** A start written as one node (`start.node`): its id by the page's node types (expression.js type("key")), or why not. */
  startNode() {
    const text = this.start && this.start.node;
    if (!text) return null;
    const entities = ((this.vocabulary() || {}).entities) || [];
    const nodes = Object.fromEntries(entities.filter((e) => e && e.type).map((e) => [e.type, { keys: e.keys || [], id: (k) => entitySeedId(e.type, k) }]));
    const c = compile(text, { nodes });
    if (!c.ok) return { why: c.why };
    const out = run(c, []);
    return typeof out.value === 'string' ? { id: out.value } : { why: out.why || `${text} names no node` };
  }

  /** Its row type: the declaration's, else a written start's own type. */
  rowType() {
    if (this.decl.row) return this.decl.row;
    const s = this.startNode();
    return s && s.id ? typeOfStart(s.id) : null;
  }

  /** The seeds: a written start - that node; «All» - the row type described; else the start marking's entries, a hub
   *  its members - the pressed nodes only (owner 10-15: the marking's spread layer paints, limits and answers Marked();
   *  it starts nothing - a part laid between is the bridge to spread a start). */
  seeds() {
    if (this.start && this.start.node) { const s = this.startNode(); return s && s.id ? { positive: [s.id] } : null; }
    const name = this.start && this.start.marking;
    if (!name) return this.rowType() ? { all: true } : null;
    const got = seedsOf(this.markings.entries(name), (id) => this.hubs.open(id));
    return got.positive.length ? { positive: got.positive, negative: got.negative } : null;
  }

  /** Its start's node types - its seeds' (a marking of two types or more starts from them together). */
  startTypes() {
    const s = this.seeds();
    return s && s.positive ? [...new Set(s.positive.map(typeOfStart).filter(Boolean))].sort() : [];
  }

  /** The routes from its start's types to its row type (route.js routesFor) - none when it starts from All. */
  routes() {
    const rows = this.rowType();
    return this.startTypes().filter((t) => t !== rows).flatMap((t) => routesFor(this.vocabulary(), t, rows));
  }

  /** Its rows - the row walk's (a value walk's nodes of the row type are not rows). */
  rowsOf() { return this.rowIds0 || []; }

  systemConditions() {
    return (this.decl.system && this.filters && this.filters.get(this.decl.system)) || [];
  }

  async load() {
    let seeds = this.seeds();
    // A kind of cells (the sheet) draws before it has a start - its key is one of its cells.
    if (!seeds && this.kind && this.kind.cells) {
      this.walking += 1; this.abortWalk(); this.walkedSeeds = []; this.rowIds0 = []; this.rowWalk = null; this.values = new Map(); this.answer = { nodes: [], edges: [] }; this.state = 'ready';
      this.refold(); this.prune(new Set()); return;
    }
    if (!seeds) { this.walking += 1; this.abortWalk(); this.state = 'no-start'; this.answer = null; this.publish(); this.render(); this.prune(new Set()); return; }
    // a load drops the walks in flight - their rows are the last load's
    const ticket = (this.walking += 1);
    this.abortWalk();
    this.state = 'walking';
    this.render();
    // No route from a start type to its rows: said, nothing drawn (a start of the row type is its own row)
    const away = seeds.all ? [] : this.startTypes().filter((t) => t !== this.rowType());
    if (away.length && !this.routes().length && this.vocabulary()) {
      this.state = 'refused';
      this.refusal = `No route from ${away.join(', ')} to ${this.rowType()}`;
      this.answer = null;
      this.publish();
      this.render();
      this.prune(new Set());
      return;
    }
    let positive = seeds.positive || [];
    // THE ROW WALK (owner 10-14): from the start along the route only, carrying the row type and the start's, to its end
    let rows = await this.walkRows(seeds, ticket);
    if (!rows) return;
    this.startDropped = 0;
    // The system filter's start side: the marking's nodes of a condition's type are kept first, and the row walk is taken
    // again from the kept ones - a dropped wafer's dies do not come in (lead 5835e6714).
    if (rows.ok && !seeds.all) {
      const held = readable(rows.answers);
      const { kept, dropped } = keepNodes(indexGraph(held), insideOf(held), positive, this.systemConditions(), this.oneValued, (words, id) => this.layers.marked(this.markingNamed(words), id));
      if (dropped) {
        this.startDropped = dropped;
        positive = kept;
        rows = kept.length ? await this.walkRows({ positive: kept, negative: seeds.negative }, ticket) : { ok: true, answers: [], complete: true, ask: null };
        if (!rows) return;
      }
    }
    if (!rows.ok) {
      this.state = 'refused';
      this.refusal = rows.why;
      this.answer = null;
      this.publish();
      this.render();
      return;
    }
    this.walkedSeeds = positive;
    this.rowWalk = rows;
    const rowAnswer = readable(rows.answers);
    // its rows: every node of its row type the row walk reached (owner 10-14 - collect), its start's own among them
    this.rowIds0 = rowAnswer.nodes.filter((n) => n.type === this.rowType() && n.carried !== false).map((n) => n.id);
    this.values = new Map();
    this.state = 'ready';
    this.answerAgain();
    this.refold();
    // then a value walk a slot (and the relations walk of a part that writes); the marking it writes is pruned when they are in
    await Promise.all([...Object.keys(this.slotsHeld()).map((key) => this.walkValues(key)), this.walkValues(RELATION_WALK, this.relationSlot())]);
    if (ticket !== this.walking) return;
    this.prune(insideOf(this.answer));
  }

  /** The page's relations at its row type, as the columns a value walk takes - a part that writes a marking walks them,
   *  so the edges its marking spreads along are on the page (lead 10-14); none - null. */
  relationSlot() {
    const rows = this.rowType();
    const list = (this.relationsStore && this.relationsStore.get('list')) || [];
    const column = (predicate, direction, end) => ({ steps: [{ predicate, direction }], endTypes: [end] });
    const columns = list.flatMap((r) => [...(r.from === rows ? [column(r.predicate, 'outgoing', r.to)] : []), ...(r.to === rows ? [column(r.predicate, 'incoming', r.from)] : [])]);
    return this.writes && columns.length ? columns : null;
  }

  /** The answer it reads: the row walk's and every value walk's (part_walks.js readable). */
  answerAgain() {
    this.answer = readable([...((this.rowWalk && this.rowWalk.answers) || []), ...[...this.values.values()].flatMap((v) => v.answers || [])]);
    // the page's graph takes the nodes a walk carried - one standing by its id would hide its record when it comes
    this.layers.graph.add({ ...this.answer, nodes: this.answer.nodes.filter((n) => n.carried !== false) });
  }

  /** The walk's budget: the page's, then the declaration's own (`walk`: node_limit - the steps are the route's or the slot's). */
  budget() {
    const { hops: _steps, ...own } = this.decl.walk || {};
    // a part reads nodes and edges - no ranking asked (propagation)
    return { ...this.walkParams, ...own, propagation: false };
  }

  /** Drop a walk in flight (`key`: the row walk or a slot's), or every one. */
  abortWalk(key) {
    for (const [k, control] of this.aborts) if (key === undefined || k === key) { control.abort(); this.aborts.delete(k); }
  }

  /**
   * The row walk from `seeds`: a row walk in hand that covers it is taken again (part_walks.js covers), else asked to its
   * end, a walk in flight dropped. Null - a newer load took over.
   */
  async walkRows(seeds, ticket) {
    if (seeds.all) return this.walkRowsOf(seeds, ticket);
    // a start of the row type is its own row; the rest walk to the rows - asked together, read as one
    const own = seeds.positive.filter((id) => typeOfStart(id) === this.rowType());
    const away = seeds.positive.filter((id) => typeOfStart(id) !== this.rowType());
    const sides = [own, away].filter((ids) => ids.length);
    const got = await Promise.all(sides.map((ids) => this.walkRowsOf({ positive: ids, negative: seeds.negative }, ticket)));
    if (got.some((g) => !g)) return null;
    const refused = got.find((g) => !g.ok);
    if (refused) return refused;
    // the start's own rows are those nodes only - their walk brings their records, not rows
    const mine = new Set(own);
    if (own.length) got[0] = { ...got[0], answers: [{ nodes: readable(got[0].answers).nodes.filter((n) => mine.has(n.id)), edges: [], truncated: null }] };
    return { ok: true, answers: got.flatMap((g) => g.answers), complete: got.every((g) => g.complete), why: (got.find((g) => g.why) || {}).why || null,
      cached: got.every((g) => g.cached), negative: seeds.negative || [] };
  }

  /** One row walk from seeds of one side: of the row type - none when the page holds them, else their records; of other
   *  types - along every route's predicates (route.js routesFor, owner 10-14), its steps the longest, carrying the row
   *  type and the start's. */
  async walkRowsOf(seeds, ticket) {
    const rows = this.rowType();
    const own = !seeds.all && seeds.positive.every((id) => typeOfStart(id) === rows);
    // A start of the row type walks none (lead 10-14) when a walk on the page carried its nodes: they are the rows, read
    // off the page's graph (a start written by hand is walked for its records)
    if (own && seeds.positive.every((id) => this.layers.graph.nodes.has(id))) {
      const nodes = seeds.positive.map((id) => this.layers.graph.nodes.get(id));
      return { ok: true, answers: [{ nodes, edges: [], truncated: null }], complete: true, why: null, ask: null, negative: seeds.negative || [] };
    }
    const routes = seeds.all || own ? [] : this.routes();
    const types = seeds.all ? [] : [...new Set(seeds.positive.map(typeOfStart).filter(Boolean))];
    const ask = { seeds: seeds.all ? [`all:${rows}`] : [...seeds.positive].sort(), follow: [...new Set(routes.flatMap((r) => r.follow))].sort(),
      hops: Math.max(1, ...routes.map((r) => r.hops)), collect: [...new Set([rows, ...types].filter(Boolean))].sort() };
    // the page's row walks: one in flight that will cover it waited for, one in hand that covers it taken (any part's)
    const walks = this.layers.graph.walks;
    const same = (w) => JSON.stringify(w.negative || []) === JSON.stringify(seeds.negative || []);
    const coming = walks.find((w) => w.receiving && same(w) && covers({ ...w.ask, complete: true }, ask));
    if (coming) {
      await coming.done;
      if (ticket !== this.walking) return null;
    }
    const held = walks.find((w) => !w.receiving && same(w) && covers(w.ask, ask));
    if (held) return { ...held, cached: true };
    this.abortWalk();
    const control = new AbortController();
    this.aborts.set(ROW_WALK, control);
    let finished;
    const record = { ok: true, answers: [], complete: false, why: null, ask: { ...ask, complete: false }, negative: seeds.negative || [], receiving: true,
      done: new Promise((r) => { finished = r; }) };
    walks.unshift(record);
    walks.splice(KEPT_WALKS);
    const leave = () => { record.receiving = false; const at = walks.indexOf(record); if (at >= 0) walks.splice(at, 1); finished(); };
    const params = seeds.all ? { ...this.budget(), seed_type: rows, collect: ask.collect }
      : { ...this.budget(), nodeId: seeds.positive[0], positive: seeds.positive, negative: seeds.negative || [], follow: ask.follow, hops: ask.hops, collect: ask.collect };
    // the rows are drawn when their walk is in
    const got = await walkToEnd(this.fetchWalk, params, control.signal, null);
    if (got.aborted || ticket !== this.walking) { leave(); return null; }
    this.aborts.delete(ROW_WALK);
    if (got.refused) { leave(); return { ok: false, why: refusalWords(got.res) }; }
    Object.assign(record, { answers: got.answers, complete: got.complete, why: got.why, ask: { ...ask, complete: got.complete }, receiving: false });
    finished();
    return record;
  }

  /**
   * A slot's value walk (part_walks.js valueAsk) from the rows: none when it reads the rows' own values; not asked when a
   * walk in hand covers it; else asked to its end, its rows by the seed cap, drawn when every run is in, the slot's walk
   * in flight dropped.
   */
  async walkValues(key, slot = this.slotsHeld()[key]) {
    this.abortWalk(key);
    const asked = slot && this.rowIds0 ? valueAsk(slot, this.rowType(), this.vocabulary()) : null;
    if (!asked || !this.rowIds0.length) {
      if (this.values.delete(key)) { this.answerAgain(); this.refoldSoon(); }
      return;
    }
    const ask = { ...asked, seeds: [...this.rowIds0].sort() };
    // another slot's walk in flight that will cover it - waited for, not asked twice (a load walks every slot at once)
    const ticket = this.walking;
    const coming = [...this.values.entries()].find(([k, h]) => k !== key && h.receiving && covers({ ...h, complete: true }, ask));
    if (coming) {
      await coming[1].done;
      if (ticket !== this.walking || this.aborts.has(key)) return;
    }
    // its own walk before (a column taken off) or another slot's (another attribute of a type walked) - the answers kept
    const holder = [...this.values.values(), ...this.valueWalks].find((h) => covers(h, ask));
    if (holder) {
      this.values.set(key, { ...ask, answers: holder.answers, complete: true, cached: true });
      this.answerAgain();
      this.refoldSoon();
      return;
    }
    const control = new AbortController();
    this.aborts.set(key, control);
    let finished;
    const record = { ...ask, answers: [], complete: false, receiving: true, why: null, done: new Promise((r) => { finished = r; }) };
    this.values.set(key, record);
    // its rows by the seed cap, the runs asked together (lead 10-14); folded once, when every run is in (lead-board-10b:
    // a fold a page was 5 s of 8.7 on the operating-shape board)
    const gots = await Promise.all(chunks(ask.seeds, this.seedChunk).map((some) => walkToEnd(this.fetchWalk,
      { ...this.budget(), nodeId: some[0], positive: some, negative: [], follow: ask.follow, hops: ask.hops, ...(ask.collect ? { collect: ask.collect } : {}) },
      control.signal, null)));
    if (gots.some((got) => got.aborted) || ticket !== this.walking || this.aborts.get(key) !== control) { finished(); return; }
    const done = gots.flatMap((got) => got.answers);
    const cut = gots.find((got) => !got.complete);
    const complete = !cut;
    if (cut) record.why = cut.why;
    this.aborts.delete(key);
    Object.assign(record, { answers: done, complete, receiving: false });
    if (complete) this.valueWalks = [record, ...this.valueWalks].slice(0, KEPT_WALKS);
    finished();
    this.answerAgain();
    this.refold();
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

  /** Rows, filters, slots and the kind's model again from the walk in hand - a filter, a marking or a slot changed. */
  refold() {
    if (!this.answer || !this.kind) { this.render(); return; }
    const index = indexGraph(this.answer);
    const inside = insideOf(this.answer);
    this.index = index;
    this.inside = inside;
    const received = this.rowsOf();
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
    const sys = this.systemConditions().filter((c) => c.row === this.rowType());
    const afterSystem = keepNodes(index, inside, received, sys, this.oneValued, askMarked);
    const afterPart = keepNodes(index, inside, afterSystem.kept, this.decl.filter || [], this.oneValued, askMarked);
    // The picker's rows: the filters' - a limit takes rows out of the picture, not out of what a column can read.
    this.rowIds = afterPart.kept;
    const limited = limitRows(afterPart.kept, this.decl.limit, this.layers);
    const encode = this.decl.encode || {};
    const held = this.slotsHeld();
    const listed = this.slotList();
    const rows = limited.map((id) => {
      const node = index.nodes.get(id) || {};
      const reads = readSlots(index, inside, id, Object.entries(held), this.oneValued, askMarked, Boolean(this.kind.cells));
      const raw = {};
      // a folded slot of several values (a cross table's cells, owner 10-15): a raw each (slot.js foldKey)
      for (const s of listed) {
        if (held[s.key] && s.folds) columnsOf(held[s.key]).forEach((col, i) => { raw[foldKey(s.key, i)] = rawOf(index, inside, id, col, Boolean(s.records)); });
      }
      return { id, label: node.label || id, reads, raw };
    });
    const marked = (id) => this.layers.marked(this.reads, id) === true;
    // Each row's colour and each mark's paint - the root's, once (color_by.js); the units a kind draws a mark of (units.js).
    // a press that stands for nodes (hubs.js) marks no row - a mark is marked when what its press stands for is
    const anyHeld = [...inside].some(marked);
    // each slot's scale - THE one seat (slot.js scaleOf, lead-board-13 ①): the declaration's pick, else the declared type,
    // else the values; the kind draws by it and so does Color by
    const scales = Object.fromEntries(listed.filter((s) => held[s.key]).map((s) => [s.key, scaleOf(rows.map((r) => r.reads[s.key]), (this.decl.scale || {})[s.key])]));
    this.scales = scales;
    // images (lead-board-14) - THE one seat: a slot the walk declares image draws pictures, a mark's own (not spread into
    // marks, turned in place); a slot that paints or places by category (`noImages`: Color by, a cross table's axes) reads
    // nothing and the note says so
    const pictures = Object.keys(scales).filter((k) => scales[k].scale === 'image');
    const refused = listed.filter((s) => s.noImages && pictures.includes(s.key)).map((s) => s.key);
    for (const r of rows) for (const k of refused) r.reads[k] = { state: 'empty', n: 0 };
    this.imageRefusal = refused.length ? IMAGES_REFUSED : null;
    const images = (key, read) => (pictures.includes(key) ? imagesOf(read) : null);
    const { colors, colored, paint: painted } = paintRows(rows, { palette: this.palette(), declaration: this.decl, marked, markColor: this.markColor(), anyHeld, scale: scales.color || null });
    // a mark is painted by its rows (a press marks them - hubs.js nodesOfPress)
    const paint = (ids) => painted(ids);
    this.colors = colors;
    // the colours given to categories not declared yet are kept in the declaration - Save keeps them, more categories
    // later leave them where they are (a declaration field, no walk)
    if (colors.any && Object.keys(colors.assigned).length) this.decl = { ...this.decl, colors: { ...(this.decl.colors || {}), ...colors.assigned } };
    // each row's shape (shape_by.js) - a points kind's; the shapes given kept in the declaration as the colours are
    const shapes = this.kind.points ? shapesOf(pictures.includes('shape') ? rows.map((r) => ({ ...r, reads: { ...r.reads, shape: undefined } })) : rows, this.decl) : null;
    this.shapes = shapes;
    if (shapes && shapes.any && Object.keys(shapes.assigned).length) this.decl = { ...this.decl, shapes: { ...(this.decl.shapes || {}), ...shapes.assigned } };
    // a Shape by of images: the mark's picture (ctx.picture), else the shapes
    const shape = pictures.includes('shape') ? (ids, unit) => this.pictureSpec(unit, 'shape', images)
      : shapes && shapes.any ? (ids) => shapeOfIds(shapes, ids) : null;
    // THE MARKS (units.js marksOf, lead-board-13 ②): the root spreads the rows into what a kind draws - a node unit's marks,
    // a hub's or a value record's units (Marker by), the sheet one value a cell (several - the root's refusal); a hub or a
    // row that cannot be drawn as one value a slot is left out with why, said in the note
    const keysRead = this.slotList().map((s) => s.key);
    const recorded = (id, key) => {
      const s = held[key];
      if (!s || Array.isArray(s) || isExpression(s) || s.self || 'constant' in s) return null;
      return readsAt(index, inside, id, s).reads.map((r) => ({ value: r.value, record: r.record }));
    };
    // the slots the kind draws a mark's value of - its own (a scatter's x and y, a table's columns), not the root's
    const own = typeof this.kind.slots === 'function' ? this.kind.slots(encode) : (this.kind.slots || []);
    const drawn = own.map((s) => s.key).filter((k) => keysRead.includes(k));
    const spread = (some) => spreadUnits(some, this.decl, keysRead, { cells: Boolean(this.kind.cells), record: this.kind.units ? this.kind.units.record : null,
      recordsOf: recorded, words: (key) => slotWords(encode[key]), marked: askMarked, drawn, pictures,
      folds: listed.filter((s) => s.folds && held[s.key]).flatMap((s) => columnsOf(held[s.key]).map((_, i) => foldKey(s.key, i))) });
    const spreadAll = spread(rows);
    const units = spreadAll.units;
    this.dropped = spreadAll.dropped;
    // what a tooltip and a label read: the marks the kind draws (units) and the rows (a mark a kind groups itself)
    this.rowsById = new Map(rows.map((r) => [r.id, r]));
    this.unitsById = new Map(units.map((u) => [u.id, u]));
    // labels shown: the declaration's; none written and Label by of images - All (lead 10-15: a picture put in shows)
    const shows = this.decl.labels || (pictures.includes('label') ? 'all' : 'none');
    const label = (mark) => labelOf(mark, { decl: this.decl, shows, rowsById: this.rowsById, marked: (ids) => ids.some(marked), images });
    // the top or bottom N marks by the Top/Bottom by slot (show_items.js) - the rest not drawn, said in the status
    // the base set slots its kind takes (a kind's `without` - the sheet takes no Top/Bottom by, no Panel by)
    const takes = new Set(this.slotList().map((s) => s.key));
    const showing = takes.has('show') ? showItems(units, this.decl) : { kept: units, hidden: 0, rule: null, n: 0 };
    // A written start as the kind may show it (the sheet's key cell): its text and the node it names, or why not.
    const start = this.start && this.start.node ? { text: this.start.node, ...(this.startNode() || {}) } : null;
    const modelCtx = { paint, colored, askMarked, label, shape, palette: this.palette(), declaration: this.decl, start,
      scale: (key) => scales[key] || scaleOf([], (this.decl.scale || {})[key]), text: (key, v, time) => this.text(key, v, time), images };
    this.imagesOf = images;
    this.model = this.kind.model(showing.kept, modelCtx);
    // Trellis (trellis.js): a panel a Panel by value - its rows' marks, the shown ones only, every panel on one extent
    const split = takes.has('panel') ? panelsOf(rows, this.decl) : null;
    if (split) {
      const keep = new Set(showing.kept.map((u) => u.id));
      const marks = split.map((panel) => inPanel(spread(panel.rows).units.filter((u) => keep.has(u.id)), panel, this.rowType()));
      const extent = extentsOf(marks.flat());
      for (const u of marks.flat()) this.unitsById.set(u.id, u);
      this.panels = split.map((panel, i) => ({ name: panel.name, where: panel.where, model: this.kind.model(marks[i], { ...modelCtx, extent }) }));
    } else this.panels = null;
    // Hidden - the marked rows the FILTERS hide; one the limit leaves out is the limit's, not hidden.
    const shown = new Set(afterPart.kept);
    const hidden = new Set([...received.filter((id) => !shown.has(id) && marked(id))]).size;
    // the marking holds nodes of other types only and no relation takes them to the row type - why no row is marked
    const heldTypes = this.reads && this.markings ? [...new Set(this.markings.entries(this.reads).flatMap(([id]) => this.hubs.open(id))
      .map((id) => this.layers.graph.typeOf(id)).filter(Boolean))] : [];
    const heldOnly = heldTypes.length && !heldTypes.includes(this.rowType()) && !this.layers.layer(this.reads).types.has(this.rowType()) ? heldTypes : null;
    // M - the rows the walk brought; a, b and c - what each layer took from them (lead 5835e6714). The start side's drops
    // are not among M: they were never walked from.
    this.counts = { rows: limited.length, of: received.length, system: afterSystem.dropped, startDropped: this.startDropped || 0,
      part: afterPart.dropped, limit: afterPart.kept.length - limited.length, marked: received.filter(marked).length, hidden, heldOnly,
      shown: showing.rule ? { rule: showing.rule, n: showing.n, by: slotWords(encode.show), hidden: showing.hidden } : null,
      columns: Object.keys(encode).length, source: this.rowType(),
      // the drawn rows an expression slot left empty because an operator met a text that is not a number (lead 10-13 ①)
      notNumber: rows.filter((r) => Object.values(r.reads).some((read) => read.notNumber)).length,
      // ...and those a date function met a text that is not a time on (the same count, lead 10-14)
      notTime: rows.filter((r) => Object.values(r.reads).some((read) => read.notTime)).length,
      // the rows an expression's Marked could not answer - a relation's edge of theirs not walked yet
      unknown: unknown.size,
      // a walk of its came back cut - the one judgment (part_walks.js walkToEnd: an axis of the last page; its steps are
      // asked, the depth reached is no cut)
      cut: [this.rowWalk, ...this.values.values()].some((w) => w && !w.complete && !w.receiving),
      // its walks (owner 10-14): the row walk's rows, and each slot's value walk - complete, receiving, cached or why not
      walks: this.walkWords() };
    if ([...asked].join() !== [...(this.askedMarkings || [])].join()) { this.askedMarkings = asked; this.listenLimit(); }
    this.publish();
    this.render();
  }

  /** Its walks' words: the row walk, then a value walk a slot by its label. */
  walkWords() {
    const said = (w) => (w.cached ? 'cached' : w.receiving ? 'receiving' : w.complete ? 'complete' : (w.why || 'cut'));
    const label = new Map(this.slotList().map((s) => [s.key, s.label || s.key]));
    return { rows: this.rowWalk ? said(this.rowWalk) : null,
      values: [...this.values.entries()].map(([key, w]) => ({ name: label.get(key) || key, state: said(w) })) };
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
      : { rows: 0, of: 0, system: 0, part: 0, marked: 0, hidden: 0, columns: 0, source: this.rowType(), state: this.state, title: this.titleWords(), slots: [] });
  }

  /** Each slot's values over the received rows - what the filters panel offers a condition over. */
  slotSummaries() {
    if (!this.index || !this.kind) return [];
    const encode = this.decl.encode || {};
    const received = this.rowsOf();
    // its slots, then the rows' own values (keys, attributes - the walk table's «+ Column» values at no step) a filter can
    // take too (the 18766 run: «+ Add filter» offered the axes only)
    const held = new Set(Object.values(encode).flatMap(columnsOf).filter((s) => Array.isArray(s.steps) && !s.steps.length && s.value).map((s) => `${s.value.on}:${s.value.name}`));
    const own = valuesAt(this.index, received, []).filter((v) => !held.has(`${v.on}:${v.name}`))
      .map((value) => ({ key: `own:${value.on}:${value.name}`, slot: { steps: [], value, words: [value.on === 'label' ? 'name' : value.name] } }));
    // a slot of several columns - a filter a column
    return [...this.slotList().filter((s) => encode[s.key]).flatMap((s) => columnsOf(encode[s.key]).map((slot, k) => ({ key: k ? `${s.key}#${k}` : s.key, slot }))), ...own].map(({ key, slot }) => {
      const counts = new Map();
      let empty = 0;
      let time = false;
      for (const id of received) {
        const read = readSlot(this.index, this.inside, id, slot, this.oneValued(slot));
        if (isTimeRead(read)) time = true;
        const values = read.state === 'one' ? [read.value] : read.state === 'several' ? read.values : [];
        if (!values.length) empty += 1;
        for (const v of values) counts.set(JSON.stringify(v), [v, (counts.get(JSON.stringify(v)) || [v, 0])[1] + 1]);
      }
      return { key, words: slotWords(slot), slot, row: this.rowType(), values: [...counts.values()], empty, time };
    });
  }

  titleWords() {
    if (this.decl.title) return this.decl.title;
    return this.kind ? this.kind.title(this.decl.encode || {}, this.decl) : '';
  }

  // ── marking, through the names the declaration gives ──
  remember(event) { this.event = event || null; }
  lastEvent() { return this.event; }

  /** A press marks what it stands for: with Ctrl added, else in place of what was marked; a press on what is marked
   *  takes it out - with Ctrl or without (owner 10-16 «ctrl 마킹 추가 제거 · 재클릭은 마킹 리스트 빼기»). A drag
   *  (`drag`: a rectangle, a span of lines or cells) marks what it holds: Ctrl adds, else replaces - never takes out. */
  mark(ids, event, drag = false) {
    if (!this.writes) return;
    const { mode, sign } = markingIntent(event || this.event);
    const held = this.markings.entries(this.writes);
    const on = new Set(held.filter(([, s]) => s === sign).map(([id]) => id));
    if (!drag && ids.length && ids.every((id) => on.has(id))) {
      const out = new Set(ids);
      this.markings.replace(this.writes, held.filter(([id]) => !out.has(id)));
      return;
    }
    if (mode === 'add') { for (const id of ids) this.markings.set(this.writes, id, sign); return; }
    this.markings.replace(this.writes, ids.map((id) => [id, sign]));
  }

  markHub(where, ids, event, drag = false) { this.markHubs([[where, ids]], event, drag); }

  /** Hubs marked whole - each [where, its members], in one press (or one drag). */
  markHubs(list, event, drag = false) {
    const press = ([where, ids]) => nodesOfPress(ids) || [this.hubs.put(hubId(this.rowType(), where), ids)];
    this.mark([...new Set(list.flatMap(press))], event, drag);
  }

  clear() { if (this.writes) this.markings.clear(this.writes); }

  // ── the picture ──
  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    this.unwatch();
    if (this.drawn) { this.drawn.dispose(); this.drawn = null; }
    const root = el('section', 'sf-part');
    root.setAttribute('data-kind', this.decl.kind || '');
    if (this.markColor() && root.style && root.style.setProperty) root.style.setProperty('--sf-marked', this.markColor());
    const title = el('div', 'sf-part__title');
    // The handle a page moves the part by (grid_shell: drag the title bar onto another part's edge).
    title.setAttribute('data-part-title', '');
    // one line, cut with its words in its tooltip (the frame standard 2)
    const name = el('span', 'sf-part__t', this.titleWords());
    name.title = this.titleWords();
    name.setAttribute('data-clip-ok', '');
    title.append(name);
    // its description - one line under the title (base set 1)
    const said = (this.decl.description || '').trim();
    const body = el('div', 'sf-part__body');
    root.append(title, ...(said ? [el('div', 'sf-part__desc', said)] : []), body);
    this.host.replaceChildren(root);
    this.root = root;
    // a mark's images turned by the wheel or the arrow keys while its tooltip is up (lead 10-15 ②: that mark only)
    root.addEventListener('wheel', (event) => { if (this.turnTip(event.deltaY > 0 ? 1 : -1) && event.preventDefault) event.preventDefault(); });
    if (!this.keysHeard && doc.addEventListener) {
      this.keysHeard = true;
      doc.addEventListener('keydown', (event) => {
        const d = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (d && this.turnTip(d) && event.preventDefault) event.preventDefault();
      });
    }
    if (this.previewer) root.append(this.previewer.mount);
    if (this.tip && this.tipMark) root.appendChild(this.tip);
    this.paintActive();
    if (!this.kind) { body.append(el('div', 'sf-say', `Unknown kind: ${this.decl.kind}`)); return; }
    // THE TEMPLATE (ROOT_PART_BASE_SET: the root is the template, a kind the visible area - the part frame standard,
    // task/design/BOARD_PART_FRAME_*.dc.html): the pill trays round the area - each slot a kind puts on a tray (`tray`: top,
    // left, bottom; `plus`: one more), the note under it - and the legend beside it: Marker by (a kind drawing a mark a
    // unit), Color by, Shape by. Drawn before a walk too: its empty line in the area's centre.
    const ready = this.state === 'ready' && Boolean(this.model);
    body.classList.add('sf-frame');
    // the legend column when the legend has something to draw - Marker by (a kind drawing a mark a unit), a Color by or a
    // Shape by declared; nothing - the column takes nothing (lead 10-14)
    const encodeNow = this.decl.encode || {};
    const legendHeld = Boolean(this.kind.units || encodeNow.color || (this.kind.points && encodeNow.shape));
    if (!legendHeld) body.classList.add('sf-frame--nolegend');
    const trays = Object.fromEntries(['top', 'left', 'bottom'].map((side) => [side, el('div', `sf-frame__tray sf-frame__${side}`)]));
    // the rows (or hubs) the root drew no mark for, and why - the first reason said (units.js marksOf)
    const dropped = ready && (this.dropped || []).length ? `${this.dropped.length} not drawn: ${this.dropped[0].why}` : '';
    const note = [ready ? this.model.note : '', dropped, ready ? this.imageRefusal : ''].filter(Boolean).join(' - ');
    if (note) {
      // one line, cut - its words in its tooltip (the frame standard 8)
      const n = el('span', 'sf-note', note);
      n.title = note;
      n.setAttribute('data-clip-ok', '');
      trays.bottom.append(n);
    }
    const pills = Object.fromEntries(Object.entries(trays).map(([side, tray]) => { const g = el('div', 'sf-frame__pills'); tray.append(g); return [side, g]; }));
    for (const s of this.slotList().filter((x) => x.tray)) {
      pills[s.tray].append(this.pill(s.key, { vertical: s.tray === 'left', ...(s.words ? { words: s.words } : {}) }));
      if (s.plus) pills[s.tray].append(this.plus(s.key));
    }
    const area = el('div', 'sf-frame__area');
    const legend = el('div', 'sf-legend');
    if (!ready) {
      const from = this.start && this.start.marking;
      const words = { 'no-start': from ? `Mark ${this.markingLabel(from)}` : 'Mark a start', walking: 'Walking…', refused: this.refusal || 'Walk refused', idle: '' }[this.state] || '';
      const said = el('div', 'sf-say', words);
      said.setAttribute('aria-live', 'polite');
      if (this.state === 'walking') said.insertBefore(walkingDino(this.doc), said.firstChild);
      area.append(said);
      body.append(trays.top, trays.left, area, trays.bottom, ...(legendHeld ? [legend] : []));
      return;
    }
    if (this.kind.units) {
      const encode = this.decl.encode || {};
      const held = markersOf(encode);
      const line = el('div', 'sf-legend__row');
      if (held.length) line.append(...held.map((k) => this.pill(k)), this.plus(nextMarker(encode)));
      else line.append(this.pill(nextMarker(encode), { words: unitWords(this.decl) }));
      legend.append(el('div', 'sf-legend__ttl', 'Marker by:'), line);
    }
    const legendCtx = { doc, text: (key, v, time) => this.text(key, v, time), pill: (key, opts) => this.pill(key, opts), plus: (key) => this.plus(key),
      words: (key) => slotWords((this.decl.encode || {})[key]), markHub: (where, ids, event, drag) => this.markHub(where, ids, event, drag),
      openPalette: (category, anchor) => this.openPalette(category, anchor) };
    legend.append(legendBlock(this.colors, legendCtx));
    if (this.shapes) legend.append(legendBlock(this.shapes, legendCtx, SHAPE_LEGEND));
    body.append(trays.top, trays.left, area, trays.bottom, ...(legendHeld ? [legend] : []));
    const drawCtx = {
      doc, palette: this.palette(), charts: this.charts,
      // a tray the kind draws in itself (the sheet's formula bar in the top one - the frame standard 5)
      tray: (side) => trays[side] || null,
      words: (key) => slotWords((this.decl.encode || {})[key]),
      text: (key, v, time) => this.text(key, v, time),
      // pictures (image_thumb.js): a place's own turn-by-hand thumbnail; a mark's picture at its turn, asked when drawable
      thumb: (mount, refs, px) => new Thumb(mount, { doc, loader: this.images, preview: this.preview() }).show(refs, px),
      picture: (spec, px) => this.picture(spec, px),
      plus: (key) => this.plus(key),
      // what is under the pointer - {id} a mark it was handed, {ids} rows it grouped; null nothing (tooltip.js)
      hover: (mark, event) => this.showTip(mark, event),
      mark: (ids, event, drag) => this.mark(ids, event, drag),
      markHub: (where, ids, event, drag) => this.markHub(where, ids, event, drag),
      markHubs: (list, event, drag) => this.markHubs(list, event, drag),
      clear: () => this.clear(),
      // A field of the kind's own (a table's sort), written into the declaration - Save keeps it.
      declare: (patch) => this.setDeclaration({ ...this.decl, ...patch }),
      remember: (event) => this.remember(event),
      lastEvent: () => this.lastEvent(),
    };
    if (!this.panels) { this.drawn = this.kind.render(area, this.model, drawCtx); this.watch(area, this.drawn); return; }
    // the panels (trellis.js): each drawn by the kind as one picture; a press in one marks its rows there
    area.classList.add('sf-trellis');
    if (area.style) area.style.gridTemplateColumns = `repeat(${Math.ceil(Math.sqrt(this.panels.length))}, minmax(0, 1fr))`;
    const drawn = this.panels.map((panel) => {
      const box = el('div', 'sf-trellis__panel');
      const head = el('div', 'sf-trellis__h', this.text('panel', panel.name));
      head.title = panel.name;
      head.setAttribute('data-clip-ok', '');
      const at = el('div', 'sf-trellis__area');
      box.append(head, at);
      area.append(box);
      const one = this.kind.render(at, panel.model, { ...drawCtx,
        markHub: (where, ids, event, drag) => this.markHub(withPanel(where, panel), ids, event, drag),
        markHubs: (list, event, drag) => this.markHubs(list.map(([where, ids]) => [withPanel(where, panel), ids]), event, drag) });
      this.watch(at, one);
      return one;
    });
    this.drawn = { resize: () => drawn.forEach((d) => d && d.resize()), dispose: () => drawn.forEach((d) => d && d.dispose()) };
  }

  /** A slot's «+» - pressed, its picker. */
  plus(key) {
    const p = this.doc.createElement('button');
    p.className = 'sf-plus';
    p.textContent = '+';
    p.type = 'button';
    p.title = 'Add one more column';
    p.addEventListener('click', () => this.openPicker({ part: this, key, anchor: p, add: true }));
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
  /** A value as this part shows it on a slot - the slot's scale (a time, a slot of days) through slot.js valueText, the one
   *  place every kind's heads, ticks, legends and cells say a value by; `time` a read's own say-so (isTimeRead). */
  text(key, value, time = false) {
    const s = (this.scales || {})[key] || {};
    return valueText(value, Boolean(time || s.time), Boolean(s.day));
  }

  /** The part's own preview of a picture (image_preview.js) - one box, its own div. */
  preview() {
    if (!this.previewer && this.doc) {
      const mount = this.doc.createElement('div');
      this.previewer = new ImagePreview(mount, { doc: this.doc, base: this.images.base });
      if (this.root) this.root.append(mount);
    }
    return this.previewer;
  }

  /** What a mark shows of a slot of images: {id, key, refs} - its picture at its turn, ctx.picture. */
  pictureSpec(mark, key, images) {
    const refs = images ? images(key, mark && mark.reads ? mark.reads[key] : null) : null;
    return refs && refs.length ? { id: mark.id || (mark.ids || []).join(','), key, refs } : null;
  }

  /** A mark's picture at its turn, drawn at `px`: its address once the page's loader has it; drawable and not here - asked,
   *  the part drawn again when it comes; too small - none asked (image_thumb.js THUMB_MIN_PX). */
  picture(spec, px) {
    if (!spec || !spec.refs || !spec.refs.length || !drawsImage(px)) return null;
    const url = this.images.url(spec.refs[(this.turns.get(`${spec.id}|${spec.key}`) || 0) % spec.refs.length], px);
    if (this.images.has(url)) return url;
    this.images.want(url, (ok) => { if (ok) this.refoldSoon(); });
    return null;
  }

  /** Drawn again once, after the pictures that came this turn. */
  refoldSoon() {
    if (this.soon) return;
    this.soon = true;
    Promise.resolve().then(() => { this.soon = false; this.refold(); });
  }

  /** The tooltip's mark turns its images by one - true when it holds some to turn. */
  turnTip(d) {
    const specs = (this.tipSpecs || []).filter((s) => s.refs.length > 1);
    if (!this.tipMark || !specs.length) return false;
    for (const s of specs) {
      const k = `${s.id}|${s.key}`;
      this.turns.set(k, ((this.turns.get(k) || 0) + d + s.refs.length) % s.refs.length);
    }
    this.showTip(this.tipMark, this.tipEvent);
    if (specs.some((s) => s.key === 'shape' || s.key === 'label')) this.refoldSoon();
    return true;
  }

  showTip(mark, event) {
    if (!this.root || !this.doc) return;
    if (!this.tip) { this.tip = this.doc.createElement('div'); this.tip.className = 'sf-tip'; }
    if (!mark || !event) { this.tipMark = null; this.tipSpecs = null; this.tip.remove ? this.tip.remove() : null; return; }
    this.tipMark = mark;
    this.tipEvent = event;
    const unit = (mark.id !== undefined && this.unitsById && this.unitsById.get(mark.id)) || mark;
    const lines = tipLines({ ...unit, ids: unit.ids || mark.ids || [] }, { rowsById: this.rowsById || new Map(), slots: this.slotList(), encode: this.decl.encode || {},
      text: (key, v, time) => this.text(key, v, time), images: this.imagesOf || null });
    this.tipSpecs = lines.filter((line) => line && typeof line === 'object').map((line) => line.spec);
    this.tip.replaceChildren(...lines.map((line, k) => {
      const n = this.doc.createElement('div');
      if (!k) n.className = 'sf-tip__h';
      if (line && typeof line === 'object') {
        // a slot of images: its words, its picture at the mark's turn and «k/n»
        n.className = 'sf-tip__img';
        const at = (this.turns.get(`${line.spec.id}|${line.spec.key}`) || 0) % line.spec.refs.length;
        const holder = this.doc.createElement('span');
        holder.className = 'sf-thumb__at';
        if (holder.style) { holder.style.width = `${TIP_IMAGE_PX}px`; holder.style.height = `${TIP_IMAGE_PX}px`; }
        const words = this.doc.createElement('span');
        words.textContent = `${line.words}: `;
        n.append(words, holder);
        new Thumb(holder, { doc: this.doc, loader: this.images, at }).show(line.spec.refs, TIP_IMAGE_PX);
      } else n.textContent = line;
      return n;
    }));
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
    // which part's which slot - the picker finds the pill again when the part is drawn again
    p.setAttribute('data-slot', key);
    p.setAttribute('data-part', this.decl.id || '');
    const slot = (this.decl.encode || {})[key];
    // a slot nothing is declared in says what the kind does without it, when the kind says (the cross table's cells)
    const empty = slot ? '' : ((this.slotList().find((s) => s.key === key) || {}).empty || '');
    p.textContent = opts.words || empty || slotWords(slot);
    // a pill its tray cuts says its words whole in its tooltip
    p.title = p.textContent;
    p.setAttribute('data-clip-ok', '');
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
