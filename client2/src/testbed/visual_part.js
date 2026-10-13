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

  /** Its kind's slots - a list, or what the kind makes of the declaration's encode (a table's columns). */
  slotList() {
    const listed = this.kind ? this.kind.slots : [];
    return typeof listed === 'function' ? listed(this.decl.encode || {}) : listed;
  }

  mount() {
    super.mount();
    const off = [];
    // The system filter changed: from its start side again - a node it let go comes back when it widens.
    if (this.filters) off.push(this.filters.subscribe('*', (name) => { if (name === this.decl.system) this.load(); }));
    if (this.active) off.push(this.active.subscribe('active', () => this.paintActive()));
    // A marking's colour changed: its marked points and lines.
    if (this.markingList) off.push(this.markingList.subscribe('list', () => this.refold()));
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
    // Closed while it was the active one: no part is.
    if (this.active && this.active.get('active') === this.decl.id) this.active.set('active', null);
    if (this.drawn) this.drawn.dispose();
    this.drawn = null;
    super.destroy();
  }

  /** The declaration as it stands - what Save writes and a reopen reads back. */
  declaration() { return JSON.parse(JSON.stringify(this.decl)); }

  /** A changed declaration: a new start, row type or system filter walks again; anything else folds again. One that
   *  closes a loop of markings with the page's other visuals is refused and the loop named (`this.loop`). */
  setDeclaration(asked) {
    const { reads: _shown, ...next } = asked;
    this.loop = chainLoop([...this.peers().filter((d) => d.id !== next.id), next]);
    if (this.loop) { this.publish(); return false; }
    const walkAgain = JSON.stringify([next.start, next.row, next.system]) !== JSON.stringify([this.decl.start, this.decl.row, this.decl.system]);
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

  /** The markings its limit names and it does not hear already (the one it shows, the one it starts from): a change
   *  folds again. */
  listenLimit() {
    for (const off of this._limitOffs || []) off();
    const heard = new Set([this.reads, this.start && this.start.marking]);
    const names = ((this.decl.limit && this.decl.limit.markings) || []).filter((n) => !heard.has(n));
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

  systemConditions() {
    return (this.decl.system && this.filters && this.filters.get(this.decl.system)) || [];
  }

  async load() {
    const seeds = this.seeds();
    if (!seeds) { this.state = 'no-start'; this.answer = null; this.publish(); this.render(); this.prune(new Set()); return; }
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
    // The picker's rows: the filters' - a limit takes rows out of the picture, not out of what a column can read.
    this.rowIds = afterPart.kept;
    const limited = limitRows(afterPart.kept, this.decl.limit, (name) => this.markings.entries(name), this.hubs);
    const encode = this.decl.encode || {};
    const rows = limited.map((id) => {
      const node = index.nodes.get(id) || {};
      const reads = {};
      const raw = {};
      for (const s of this.slotList()) {
        const slot = encode[s.key];
        if (!slot) continue;
        reads[s.key] = readSlot(index, inside, id, slot, this.oneValued(slot));
        if (s.folds) raw[s.key] = rawOf(index, inside, id, slot);
      }
      return { id, label: node.label || id, reads, raw };
    });
    const entries = this.reads ? this.markings.entries(this.reads) : [];
    const marked = (id) => holds(entries, this.hubs, id);
    this.model = this.kind.model(rows, { marked, markColor: this.markColor(), palette: this.palette(), declaration: this.decl });
    // Hidden - the marked rows the FILTERS hide; one the limit leaves out is the limit's, not hidden.
    const shown = new Set(afterPart.kept);
    const hidden = new Set([...received.filter((id) => !shown.has(id) && marked(id))]).size;
    // M - the rows the walk brought; a, b and c - what each layer took from them (lead 5835e6714). The start side's drops
    // are not among M: they were never walked from.
    this.counts = { rows: limited.length, of: received.length, system: afterSystem.dropped, startDropped: this.startDropped || 0,
      part: afterPart.dropped, limit: afterPart.kept.length - limited.length, marked: received.filter(marked).length, hidden,
      columns: Object.keys(encode).length, source: this.decl.row,
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
    return this.slotList().filter((s) => encode[s.key]).map((s) => {
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
      markHubs: (list, event) => this.markHubs(list, event),
      clear: () => this.clear(),
      // A field of the kind's own (a table's sort), written into the declaration - Save keeps it.
      declare: (patch) => this.setDeclaration({ ...this.decl, ...patch }),
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
 * ('any'), a hub as its members (hubs.holds). When every one of them is empty: all the rows (`none: 'all'`) or none
 * ('empty'). No marking named: no limit.
 * @param {string[]} ids
 * @param {{markings: string[], must?: 'all'|'any', none?: 'all'|'empty'}|null|undefined} limit
 * @param {(name: string) => Array<[string, number]>} entriesOf  @param {import('./hubs.js').HubBook} book
 */
export function limitRows(ids, limit, entriesOf, book) {
  const names = (limit && limit.markings) || [];
  if (!names.length) return ids;
  const held = names.map(entriesOf);
  if (held.every((entries) => !entries.length)) return limit.none === 'empty' ? [] : ids;
  const test = limit.must === 'any' ? 'some' : 'every';
  return ids.filter((id) => held[test]((entries) => holds(entries, book, id)));
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
