// TABLES - one source table's box (owner 11-06 «Tables», lead L1): its rows read by page through the grid's own door
// (/tables/{t}/data and /data/count, narrowed as the grid narrows - narrowing.js's query), drawn by the table kind's
// one renderer (testbed/kinds/table.js, only the lines in view), the next page read as the view nears the end. The first
// table never opens whole (owner 11-06): rows are read once a search or a filter narrows it. A class with its mount and
// its deps - no module state, two on one page do not meet.

import { tableModel, render } from '../testbed/kinds/table.js';
import { floatingText } from '../value_filter.js';
import { countNumberText, countOf } from '../match_count.js';
import { refusalText } from '../refusal.js';
import { crossIcon } from '../cross_icon.js';
import { SIGN } from '../rnd_board/marking_store.js';
import { markingIntent } from '../rnd_board/panel.js';
import { rowNodeId } from './chain.js';
import { rowsKey } from '../rows_key.js';

export const PAGE_ROWS = 500;
/** The next page is read when fewer lines than this are left below the view. */
export const MORE_WITHIN_LINES = 60;
export const START_WORDS = 'Search to open rows';
export const READING_WORDS = 'Reading rows…';
const COLUMN = (k) => `col${k + 1}`;

/** The narrowing's parts: its query, its filters (the grid's model), its search and the transaction it names. */
export function narrowingOf(text) {
  const params = new URLSearchParams(text || '');
  let filters = {};
  try { filters = JSON.parse(params.get('filters') || '{}') || {}; } catch { filters = {}; }
  return { params, filters, q: params.get('q') || '', tx: params.get('transaction_id') || '' };
}

/** Whether it narrows at all - the first table opens only then. */
export const narrows = (text) => { const n = narrowingOf(text); return Boolean(n.q || n.tx || Object.keys(n.filters).length); };

/** The narrowing with one column's filter taken off. */
export function withoutFilter(text, column) {
  const n = narrowingOf(text);
  delete n.filters[column];
  if (Object.keys(n.filters).length) n.params.set('filters', JSON.stringify(n.filters)); else n.params.delete('filters');
  return n.params.toString();
}

/** The narrowing with its search set (blank: none, and its columns with it). */
export function withSearch(text, q) {
  const n = narrowingOf(text);
  const said = String(q || '').trim();
  if (said) n.params.set('q', said); else { n.params.delete('q'); n.params.delete('cols'); }
  return n.params.toString();
}

/** The transaction narrowing taken off. */
export function withoutTransaction(text) {
  const n = narrowingOf(text);
  n.params.delete('transaction_id');
  return n.params.toString();
}

/** Its chips: a column's filter as its floating cell says it, and the transaction it is narrowed to. */
export function chipsOf(text) {
  const n = narrowingOf(text);
  const chips = Object.entries(n.filters).map(([column, model]) => ({ column, words: `${column} ${floatingText(model)}`.trim() }));
  if (n.tx) chips.push({ column: null, words: `Transaction ${n.tx}` });
  return chips;
}

/** A page's query: the narrowing, the page - by `key` (rows_key.js) when there is one, skip beside it -, the order (none:
 *  entered order, row_id), the world, the server marking it is opened by; the count comes apart. */
export function pageQuery(text, { skip = 0, key = null, limit = PAGE_ROWS, order = null, world = null, marking = null } = {}) {
  const p = new URLSearchParams(text || '');
  if (marking) p.set('marking', marking);
  p.set('skip', String(skip));
  for (const [side, rowId] of Object.entries(key || {})) p.set(side, rowId);
  p.set('limit', String(limit));
  p.set('order_by', order ? order.column : 'row_id');
  p.set('order_desc', String(Boolean(order && order.desc)));
  p.set('defer_total', 'true');
  if (world) p.set('world', world);
  return p.toString();
}

/** The count's query: the narrowing, the world and the server marking only. */
export function countQuery(text, world = null, marking = null) {
  const p = new URLSearchParams(text || '');
  if (marking) p.set('marking', marking);
  if (world) p.set('world', world);
  return p.toString();
}

/** The grid door's rows as the table kind reads them: a line a row, a read a column. */
export function linesOf(rows, columns) {
  return rows.map((row) => ({
    id: row.row_id,
    reads: Object.fromEntries(columns.map((column, k) => {
      // a cell's value; a column the row carries itself (row_id, created_at, updated_at) its own, as the grid reads them
      const value = row.data && row.data[column] ? row.data[column].value : (row[column] ?? null);
      return [COLUMN(k), value === null || value === undefined || value === '' ? { state: 'none' } : { state: 'one', value }];
    })),
  }));
}

/** The header's count: narrowed - «1,284 of 412,930 rows», else the table's. */
export function countWords(narrowed, whole, isNarrowed) {
  return isNarrowed ? `${countNumberText(narrowed)} of ${countNumberText(whole)} rows` : `${countNumberText(whole)} rows`;
}

/** Whether a next page can hold rows: the last page came full, and the count (when it is known and not capped) says
 *  more than is read. */
export function moreAfter(lastPage, read, counted) {
  const c = countOf(counted);
  return lastPage === PAGE_ROWS && !(c.total !== null && !c.capped && read >= c.total);
}

/** The foot: what is read of what there is, and whether more comes on scroll. */
export function footWords({ read, more, total }) {
  if (!read) return more ? READING_WORDS : 'No rows';
  const of = total === null || total === undefined ? '' : ` of ${countNumberText(total)}`;
  return more ? `rows 1–${read.toLocaleString('en-US')}${of} · next page on scroll` : `all ${read.toLocaleString('en-US')} rows`;
}

export class TableBox {
  /**
   * @param {HTMLElement} mount
   * @param {{doc: Document, fetch: Function, apiBase: string, table: string, narrowing?: string, world?: string|null,
   *          frame?: (fn) => void, markings?: MarkingStore, writes?: string, marking?: string, title?: string}} deps
   *   writes  the marking name a press marks rows under (+, Shift −; the store's toggle, as the walk's table); none: no
   *           press marks   marking  the server marking the box opens by - its rows only, no search needed
   */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.doc = deps.doc;
    this.table = deps.table;
    this.narrowing = deps.narrowing || '';
    this.world = deps.world || null;
    this.columns = [];
    this.rows = [];
    this.order = null;
    this.more = false;
    this.reading = 0;
    this.busy = false;
    this.total = null;
    this.markings = deps.markings || null;
    this.writes = deps.writes || null;
    this.marking = deps.marking || null;
  }

  /** The row ids marked with `sign` under the box's name. */
  marked(sign) {
    if (!this.markings || !this.writes) return [];
    return this.markings.entries(this.writes).filter(([, s]) => s === sign).map(([id]) => id);
  }

  /** A press on lines toggles each under the sign Shift says; a drag marks them all with it. */
  mark(ids, event, drag = false) {
    if (!this.markings || !this.writes) return;
    const { sign } = markingIntent(event);
    for (const id of ids) {
      const node = rowNodeId(this.table, id);
      if (drag) this.markings.set(this.writes, node, sign); else this.markings.toggle(this.writes, node, sign);
    }
  }

  drawMarks() {
    if (!this.marksEl) return;
    const plus = this.marked(SIGN.CASE).length;
    const minus = this.marked(SIGN.CONTROL).length;
    this.marksEl.textContent = plus || minus ? `+ ${plus.toLocaleString('en-US')} · − ${minus.toLocaleString('en-US')} marked` : '';
  }

  _el(tag, cls, text) {
    const n = this.doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  _get(path) {
    return this.deps.fetch(`${this.deps.apiBase}/tables/${encodeURIComponent(this.table)}${path}`);
  }

  /** Draw the box and read it. */
  async open() {
    const box = this._el('section', 'tables-box');
    const head = this._el('header', 'tables-box__head');
    if (this.deps.title) head.append(this._el('span', 'tables-box__title', this.deps.title));
    head.append(this._el('span', 'tables-box__name', this.table));
    this.countEl = this._el('span', 'tables-box__count', '');
    this.marksEl = this._el('span', 'tables-box__marks', '');
    head.append(this.countEl, this.marksEl);
    if (this.markings && this.writes) {
      this.unsubscribe = this.markings.subscribe(this.writes, () => { this.drawMarks(); if (this.rows.length) this.draw(); });
    }
    this.drawMarks();
    const bar = this._el('div', 'tables-box__bar');
    const label = this._el('label', 'tables-box__label', 'Search');
    this.search = this._el('input', 'ctl-small tables-box__search');
    this.search.type = 'text';
    this.search.id = `tables-search-${this.table}`;
    label.htmlFor = this.search.id;
    this.search.value = narrowingOf(this.narrowing).q;
    this.search.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') this.renarrow(withSearch(this.narrowing, this.search.value));
    });
    this.chips = this._el('span', 'tables-box__chips');
    bar.append(label, this.search, this.chips);
    this.area = this._el('div', 'tables-box__body');
    this.foot = this._el('footer', 'tables-box__foot', '');
    box.append(head, bar, this.area, this.foot);
    this.mount.replaceChildren(box);
    this.drawChips();
    const schema = await this._get('/schema');
    if (!schema.ok) { this.say(await refusalText(schema, 'Columns read failed')); return; }
    this.columns = ((await schema.json()).columns || []).slice();
    await this.reread();
  }

  drawChips() {
    const chips = chipsOf(this.narrowing).map((c) => {
      const chip = this._el('span', 'chip', c.words);
      const x = this._el('button', 'chip-remove');
      x.type = 'button';
      x.append(crossIcon(this.doc));
      x.setAttribute('aria-label', `Remove ${c.words}`);
      x.addEventListener('click', () => this.renarrow(c.column === null ? withoutTransaction(this.narrowing) : withoutFilter(this.narrowing, c.column)));
      chip.append(x);
      return chip;
    });
    this.chips.replaceChildren(...chips);
  }

  say(words) { this.foot.textContent = words; }

  /** A new narrowing: its chips, its count and its rows from the first page. */
  async renarrow(text) {
    this.narrowing = text;
    this.search.value = narrowingOf(text).q;
    this.drawChips();
    await this.reread();
  }

  /** The counts and the first page again (a new narrowing or order). */
  async reread() {
    const ticket = (this.reading += 1);
    this.rows = [];
    this.more = false;
    this.busy = false;
    const opened = narrows(this.narrowing) || Boolean(this.marking);
    const counts = Promise.all([
      opened ? this._get(`/data/count?${countQuery(this.narrowing, this.world, this.marking)}`) : null,
      this._get(`/data/count?${countQuery('', this.world)}`),
    ].map(async (asked) => { const res = await asked; return res && res.ok ? res.json() : null; }));
    if (!opened) {
      this.area.replaceChildren(this._el('p', 'meta tables-box__start', START_WORDS));
      this.say('');
    } else {
      this.more = true;
      this.say(READING_WORDS);
      await this.page(ticket);
    }
    const [narrowed, whole] = await counts;
    if (ticket !== this.reading) return;
    this.total = narrowed;
    if (opened && this.rows.length) this.more = moreAfter(this.lastPage, this.rows.length, narrowed);
    this.countEl.textContent = countWords(narrowed, whole, opened);
    if (opened && this.rows.length) this.say(footWords({ read: this.rows.length, more: this.more, total: this.total }));
  }

  /** The next page, added below the lines read. */
  async page(ticket = this.reading) {
    if (this.busy || !this.more) return;
    this.busy = true;
    const res = await this._get(`/data?${pageQuery(this.narrowing, { skip: this.rows.length, key: rowsKey(this.rows, 'after'), order: this.order, world: this.world, marking: this.marking })}`);
    if (ticket !== this.reading) return;
    this.busy = false;
    if (!res.ok) { this.more = false; this.say(await refusalText(res, 'Rows read failed')); return; }
    const got = (await res.json()).data || [];
    this.rows = this.rows.concat(got);
    this.lastPage = got.length;
    this.more = moreAfter(got.length, this.rows.length, this.total);
    this.draw();
    this.say(footWords({ read: this.rows.length, more: this.more, total: this.total }));
  }

  /** Order by a column (the head pressed) - the server's order, read again from the first page. */
  orderBy(column, desc) {
    this.order = { column, desc };
    return this.reread();
  }

  draw() {
    const encode = Object.fromEntries(this.columns.map((column, k) => [COLUMN(k), { column }]));
    // a marked row: + as the table marks, − with the control colour beside (tables.css)
    const signOf = (id) => (this.markings && this.writes ? this.markings.signOf(this.writes, rowNodeId(this.table, id)) : SIGN.ABSENT);
    const paint = ([id]) => { const s = signOf(id); return { marked: s !== SIGN.ABSENT, color: s === SIGN.CONTROL ? 'var(--danger)' : null }; };
    const model = tableModel(linesOf(this.rows, this.columns), { paint, colored: true, declaration: { encode } });
    // the order is the server's - the heads say it, the lines stand as read
    model.sort = this.order ? { key: COLUMN(this.columns.indexOf(this.order.column)), desc: this.order.desc } : null;
    const before = this.area.querySelector('.tb-table__wrap');
    const was = before ? before.scrollTop || 0 : 0;
    render(this.area, model, {
      doc: this.doc,
      words: (key) => this.columns[Number(key.slice(3)) - 1],
      declare: ({ sort }) => this.orderBy(this.columns[Number(sort.key.slice(3)) - 1], sort.desc),
      mark: (ids, event, drag) => this.mark(ids, event, drag),
      clear: () => { if (this.markings && this.writes) this.markings.clear(this.writes); },
      hover: () => {},
    });
    const wrap = this.area.querySelector('.tb-table__wrap');
    if (!wrap) return;
    if (was) wrap.scrollTop = was;
    wrap.addEventListener('scroll', () => {
      const lines = this.rows.length;
      const per = lines ? wrap.scrollHeight / lines : 0;
      const left = per ? (wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight) / per : Infinity;
      if (left < MORE_WITHIN_LINES) this.page();
    });
  }
}
