// THE VISUAL PART - one root, kinds as declarations (lead aca803a7a ㄱ, owner 「근원 부품 만들어와」). The root does what
// every kind needs: the walk from its marking, the rows of its row type, the two filters, each slot read, the marking it
// writes and the one it shows; a kind says only its slots, its title, its model and its picture, and reads its own
// fields off the declaration. The root never asks which kind it holds (owner: «kind 는 운영자가 적는 낱말이지 실행이
// 갈리는 축이 아니다»).
//
// declaration  { id, part: 'visual', kind, title?, row, start: {marking: name|null}, system: name|null,
//                filter: [conditions], encode: {slotKey: slot}, reads: name, writes: name }
//   start.marking null - «All»: every node of the row type (seed_type)
//   system - the system filter it uses (Spotfire «Use filtering from page»), null none; filter - its own final conditions
//
// Flow (owner 10-12): system marking + system filter -> the part walks from the marking -> its own filter -> drawn.

import { Panel, markingIntent } from '../rnd_board/panel.js';
import { indexGraph } from '../walk/reach_table.js';
import { readSlot, slotWords, rawOf } from './slot.js';
import { keepNodes } from './filter.js';
import { hubId, holds } from './hubs.js';
import { seedsOf } from '../rnd_board/marking_store.js';
import { truncationAxes } from '../rnd_board/api.js';
import { paletteOf } from './palette.js';

export class VisualPart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const d = deps || {};
    // The declaration without the page's dependencies (`options` - the stores, the walk): those are the page's, not saved.
    const { options: _pageDeps, ...own } = d.declaration || {};
    this.decl = JSON.parse(JSON.stringify(own));
    this.kinds = d.kinds || {};
    this.fetchWalk = d.fetchWalk;
    this.filters = d.filters;
    this.stats = d.stats;
    this.active = d.active;
    this.hubs = d.hubs;
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

  mount() {
    super.mount();
    const off = [];
    // The system filter changed: from its start side again - a node it let go comes back when it widens.
    if (this.filters) off.push(this.filters.subscribe('*', (name) => { if (name === this.decl.system) this.load(); }));
    if (this.active) off.push(this.active.subscribe('active', () => this.paintActive()));
    this._offs = off;
    if (this.host && typeof this.host.addEventListener === 'function') {
      this.host.addEventListener('mousedown', () => { if (this.active) this.active.set('active', this.decl.id); });
    }
    this.load();
  }

  destroy() {
    for (const off of this._offs || []) off();
    if (this.drawn) this.drawn.dispose();
    this.drawn = null;
    super.destroy();
  }

  /** The declaration as it stands - what Save writes and a reopen reads back. */
  declaration() { return JSON.parse(JSON.stringify(this.decl)); }

  /** A changed declaration: a new start, row type or system filter walks again; anything else folds again. */
  setDeclaration(next) {
    const walkAgain = JSON.stringify([next.start, next.row, next.system]) !== JSON.stringify([this.decl.start, this.decl.row, this.decl.system]);
    const before = this.decl;
    this.decl = JSON.parse(JSON.stringify(next));
    this.start = this.decl.start || null;
    this.writes = this.decl.writes || null;
    this.listen(before);
    if (walkAgain) this.load(); else this.refold();
  }

  /** The markings it hears follow its declaration: the one it shows, the one it starts from. */
  listen(before) {
    if (!this.markings) return;
    if ((before.reads || null) !== (this.decl.reads || null)) {
      if (this._unsubscribe) this._unsubscribe();
      this.reads = this.decl.reads || null;
      this._unsubscribe = this.reads ? this.markings.subscribe(this.reads, () => this.onMarkingChanged()) : null;
    }
    const was = before.start && before.start.marking;
    const now = this.start && this.start.marking;
    if (was !== now) {
      if (this._startOff) this._startOff();
      this._startOff = now && now !== this.reads ? this.markings.subscribe(now, () => this.onStartChanged()) : null;
    }
  }

  showMarking(name) { this.setDeclaration({ ...this.decl, reads: name }); }

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

  systemConditions() {
    return (this.decl.system && this.filters && this.filters.get(this.decl.system)) || [];
  }

  async load() {
    const seeds = this.seeds();
    if (!seeds) { this.state = 'no-start'; this.answer = null; this.publish(); this.render(); return; }
    const ticket = (this.walking += 1);
    this.state = 'walking';
    this.render();
    let positive = seeds.positive || [];
    // The walk from every seed does not hang on the system filter: one in hand for the same seeds is taken again (a
    // filter changed), and only the start side is judged anew.
    const asked = JSON.stringify([seeds, this.decl.row]);
    let res = this.seedWalk && this.seedWalk.asked === asked ? this.seedWalk.res : await this.walkFrom(seeds);
    if (ticket !== this.walking) return;
    if (res.ok) this.seedWalk = { asked, res };
    this.startDropped = 0;
    // The system filter's start side: the marking's nodes of a condition's type are kept first, and the walk is taken
    // again from the kept ones - a dropped wafer's dies do not come in (lead 5835e6714).
    if (res.ok && !seeds.all) {
      const index = indexGraph(res.body);
      const inside = insideOf(res.body);
      const { kept, dropped } = keepNodes(index, inside, positive, this.systemConditions(), this.oneValued);
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
    this.answer = res.body;
    this.state = 'ready';
    this.refold();
  }

  walkFrom(seeds) {
    const base = { ...this.walkParams };
    const params = seeds.all ? { ...base, seed_type: this.decl.row }
      : { ...base, nodeId: seeds.positive[0], positive: seeds.positive, negative: seeds.negative || [] };
    return this.fetchWalk(params);
  }

  /** Rows, filters, slots and the kind's model again from the walk in hand - a filter, a marking or a slot changed. */
  refold() {
    if (!this.answer || !this.kind) { this.render(); return; }
    const index = indexGraph(this.answer);
    const inside = insideOf(this.answer);
    this.index = index;
    this.inside = inside;
    const received = (this.answer.nodes || []).filter((n) => n.type === this.decl.row).map((n) => n.id);
    if (this.names) for (const n of this.answer.nodes || []) this.names.set(n.id, { type: n.type, label: n.label || n.id });
    const sys = this.systemConditions().filter((c) => c.row === this.decl.row);
    const afterSystem = keepNodes(index, inside, received, sys, this.oneValued);
    const afterPart = keepNodes(index, inside, afterSystem.kept, this.decl.filter || [], this.oneValued);
    this.rowIds = afterPart.kept;
    const encode = this.decl.encode || {};
    const rows = afterPart.kept.map((id) => {
      const node = index.nodes.get(id) || {};
      const reads = {};
      const raw = {};
      for (const s of this.kind.slots) {
        const slot = encode[s.key];
        if (!slot) continue;
        reads[s.key] = readSlot(index, inside, id, slot, this.oneValued(slot));
        if (s.folds) raw[s.key] = rawOf(index, inside, id, slot);
      }
      return { id, label: node.label || id, reads, raw };
    });
    const entries = this.reads ? this.markings.entries(this.reads) : [];
    const marked = (id) => holds(entries, this.hubs, id);
    this.model = this.kind.model(rows, { marked, palette: this.palette(), declaration: this.decl });
    const shown = new Set(afterPart.kept);
    const hidden = new Set([...received.filter((id) => !shown.has(id) && marked(id))]).size;
    // M - the rows the walk brought; a and b - what each layer took from them (lead 5835e6714). The start side's drops
    // are not among M: they were never walked from.
    this.counts = { rows: afterPart.kept.length, of: received.length, system: afterSystem.dropped, startDropped: this.startDropped || 0,
      part: afterPart.dropped, marked: received.filter(marked).length, hidden, columns: Object.keys(encode).length, source: this.decl.row,
      // the drawn rows an expression slot left empty because an operator met a text that is not a number (lead 10-13 ①)
      notNumber: rows.filter((r) => Object.values(r.reads).some((read) => read.notNumber)).length,
      // The board's one reading of a cut walk (rnd_board/api.js truncationAxes).
      cut: (truncationAxes(this.answer.truncated, { hopsChosen: false }) || []).length > 0 };
    this.publish();
    this.render();
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
    const received = (this.answer.nodes || []).filter((n) => n.type === this.decl.row).map((n) => n.id);
    return this.kind.slots.filter((s) => encode[s.key]).map((s) => {
      const slot = encode[s.key];
      const counts = new Map();
      let empty = 0;
      for (const id of received) {
        const read = readSlot(this.index, this.inside, id, slot, this.oneValued(slot));
        const values = read.state === 'one' ? [read.value] : read.state === 'several' ? read.values : [];
        if (!values.length) empty += 1;
        for (const v of values) counts.set(JSON.stringify(v), [v, (counts.get(JSON.stringify(v)) || [v, 0])[1] + 1]);
      }
      return { key: s.key, words: slotWords(slot), slot, row: this.decl.row, values: [...counts.values()], empty };
    });
  }

  titleWords() {
    if (this.decl.title) return this.decl.title;
    return this.kind ? this.kind.title(this.decl.encode || {}) : '';
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

  markHub(where, ids, event) {
    const id = this.hubs.put(hubId(this.decl.row, where), ids);
    this.mark([id], event);
  }

  clear() { if (this.writes) this.markings.clear(this.writes); }

  // ── the picture ──
  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    if (this.drawn) { this.drawn.dispose(); this.drawn = null; }
    const root = el('section', 'sf-part');
    root.setAttribute('data-kind', this.decl.kind || '');
    const title = el('div', 'sf-part__title');
    title.append(el('span', 'sf-part__t', this.titleWords()));
    const body = el('div', 'sf-part__body');
    root.append(title, body);
    this.host.replaceChildren(root);
    this.root = root;
    this.paintActive();
    if (!this.kind) { body.append(el('div', 'sf-say', `Unknown kind: ${this.decl.kind}`)); return; }
    if (this.state !== 'ready' || !this.model) {
      const words = { 'no-start': 'Mark a start', walking: 'Walking…', refused: this.refusal || 'Walk refused', idle: '' }[this.state] || '';
      body.append(el('div', 'sf-say', words));
      return;
    }
    this.drawn = this.kind.render(body, this.model, {
      doc, palette: this.palette(), charts: this.charts,
      words: (key) => slotWords((this.decl.encode || {})[key]),
      pill: (key, opts) => this.pill(key, opts),
      plus: (key) => { const p = el('button', 'sf-plus', '+'); p.type = 'button'; p.title = 'Add one more column'; p.addEventListener('click', () => this.openPicker({ part: this, key, anchor: p })); return p; },
      mark: (ids, event) => this.mark(ids, event),
      markHub: (where, ids, event) => this.markHub(where, ids, event),
      clear: () => this.clear(),
      remember: (event) => this.remember(event),
      lastEvent: () => this.lastEvent(),
    });
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
    if (this.kind.slots.some((s) => s.key === key)) p.addEventListener('click', () => this.openPicker({ part: this, key, anchor: p }));
    return p;
  }

  paintActive() {
    if (!this.root || !this.root.classList) return;
    const on = Boolean(this.active && this.active.get('active') === this.decl.id);
    if (on) this.root.classList.add('is-active'); else this.root.classList.remove('is-active');
  }
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
