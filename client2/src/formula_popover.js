// A column's formula, on its header (owner 10-28 option A): right-click the header, or press its «fx» mark, and the
// column's same-row formula opens under it - its preview over the table's first rows and how many rows saving recomputes,
// the server's refusal word for word, Apply and Remove. The formula is a chain rule the server keeps (`chain.formula`,
// B 9d56d6f1d); this part sends text and draws answers - it does not read the formula. As one types (owner's mockup,
// 11-07) it offers what the caret stands in: function names with their arguments, a column after «[», and inside a
// call that call's arguments with the one being typed in bold - the formula field (formula_input.js), one of four.
//
// NO NETWORK, NO DOM GLOBALS: `send` and `doc` come in (the grid page hands adminFetch's; the harness a fake).
import { setDisabledReason } from './disabled_reason.js';
import { placeUnder, watchForDismiss } from './dropdown.js';
import { ReadBoard } from './latest_read.js';
import { countNumberText, countOf, COUNT_FAILED, COUNTING_ROWS } from './match_count.js';
import { FormulaInput } from './formula_input.js';
import { localStamp } from './server_time.js';
import { unitText } from './ui_words.js';

export const FORMULA_ROUTE = '/admin/chain/formula';
/** How long typing rests before its preview is asked. */
export const PREVIEW_REST_MS = 350;
const BLANK = '—';
/** Why Apply is off - the reason on the button (disabled_reason.js). */
export const NEEDS_PREVIEW = 'Preview this formula first (Enter)';
export const REFUSED_FIRST = 'Refused - the line under the formula says why';
export const SENDING = 'Sent - waiting for the server';

/** The request for each thing the popover asks: {method, path, body}. Saving and removing carry the `base` the read
 *  gave (the file as it was read); a preview carries none and writes nothing. */
export function formulaRequest(kind, { table, column, formula = '', base = '' } = {}) {
  if (kind === 'read') return { method: 'GET', path: `${FORMULA_ROUTE}?table=${encodeURIComponent(table)}`, body: null };
  if (kind === 'preview') return { method: 'POST', path: FORMULA_ROUTE, body: { table, column, formula, preview: true } };
  if (kind === 'save') return { method: 'POST', path: FORMULA_ROUTE, body: { table, column, formula, base } };
  if (kind === 'remove') return { method: 'POST', path: FORMULA_ROUTE, body: { table, column, formula: '', base } };
  throw new Error(`no formula request ${kind}`);
}

/** The column's entry in the read's answer ({column, formula, rule, enabled}), or null. */
export function formulaOf(read, column) {
  const listed = read && Array.isArray(read.formulas) ? read.formulas : [];
  return listed.find((f) => f && f.column === column) || null;
}

/** «1,234 rows will be recomputed» and when it was counted - the preview's `count`, as the grid's footer reads one. */
export function recomputeLine(count) {
  const c = countOf(count || null);
  if (c.failed) return { text: c.failed.reason ? `${COUNT_FAILED} (${c.failed.reason})` : COUNT_FAILED, at: '' };
  if (c.total === null) return { text: COUNTING_ROWS, at: '' };
  return { text: `${unitText(countNumberText(c), 'row')} will be recomputed`,
    at: c.countedAt && !c.capped ? `counted ${localStamp(c.countedAt)}` : '' };
}

const cellText = (v) => (v === null || v === undefined || v === '' ? BLANK : String(v));

/** The preview's sample as a table: the row's keys, the columns the formula reads, the cell now and what it becomes. */
export function previewTable(sample) {
  const rows = Array.isArray(sample) ? sample : [];
  const first = rows[0] || {};
  const keys = Object.keys(first.keys || {});
  const reads = Object.keys(first.reads || {});
  const values = rows.map((r) => [...keys.map((k) => (r.keys || {})[k]), ...reads.map((k) => (r.reads || {})[k]), r.now, r.becomes]);
  const head = [...keys, ...reads, 'now', 'becomes'];
  return {
    head,
    // a column of numbers stands right, its digits under each other; the row's keys are names and stand left
    numeric: head.map((_, i) => i >= keys.length && values.every((v) => v[i] === null || v[i] === undefined || typeof v[i] === 'number')),
    rows: rows.map((r) => ({
      cells: [...keys.map((k) => cellText((r.keys || {})[k])), ...reads.map((k) => cellText((r.reads || {})[k])),
        cellText(r.now), cellText(r.becomes)],
      changed: cellText(r.now) !== cellText(r.becomes),
    })),
  };
}

/** What the toast says once the server took a save or a removal. */
export function doneLine(kind, answer) {
  const a = answer || {};
  const run = a.run_id ? ` · run ${a.run_id}` : '';
  return kind === 'remove'
    ? `Formula removed · ${a.rule || ''} · column resolved again${run}`
    : `Formula saved · ${a.rule || ''} · recompute queued${run}`;
}

const CLOCK = { set: (fn, ms) => setTimeout(fn, ms), clear: (h) => clearTimeout(h) };

/**
 * One popover. `host` is where it is born (placeUnder moves its panel to the body); `deps`:
 *   doc      the document
 *   send     async (request) -> {ok: true, body} | {ok: false, error}  - the refusal already a sentence
 *   say      (text, type, opts) - the page's toast
 *   onSaved  ({table, column}) - the page reads the table's formulas again
 *   openQueue () - the toast's «Open queue»
 *   hide     (column) - «Hide column» in the head; without it, no such button
 *   clock   {set, clear} - the preview's rest
 */
export class FormulaPopover {
  constructor(host, deps = {}) {
    this.host = host;
    this.doc = deps.doc;
    this.send = deps.send;
    this.say = deps.say || (() => {});
    this.onSaved = deps.onSaved || (() => {});
    this.openQueue = deps.openQueue || null;
    this.hide = deps.hide || null;
    this.clock = deps.clock || CLOCK;
    this.board = new ReadBoard();
    this.panel = null;
    this.unwatch = null;
    this.rest = null;
    this.target = null;
    this.anchor = null;
    this.base = '';
    this.existing = null;
    this.previewed = null;
    this.columns = [];
    this.formula = null;
  }

  get isOpen() { return this.panel !== null; }

  /** Opens under `anchor` for `table`.`column`; `columns` are the ones the formula may read (its own is left out).
   *  `formula` false: a column no formula stands on (a system one, a pivot's item column) - the head alone, its
   *  «Hide column», named by `word` (lead 11-06: one popover, not a second). */
  async open({ table, column, columns = [], anchor = null, formula = true, word = column }) {
    this.close();
    this.target = { table, column };
    this.base = '';
    this.existing = null;
    this.previewed = null;
    this.anchor = anchor;
    this.draw(columns.filter((c) => c !== column), formula ? null : word);
    this.fit();
    if (!formula) return;
    if (this.input.focus) this.input.focus();
    const mine = this.target;
    const read = await this.send(formulaRequest('read', { table }));
    if (this.target !== mine) return;
    if (!read.ok) { this.refuse(read.error); return; }
    this.base = (read.body && read.body.base) || '';
    this.existing = formulaOf(read.body, column);
    if (this.existing) {
      this.input.value = this.existing.formula || '';
      this.removeBtn.hidden = false;
      this.preview();
    }
  }

  close() {
    if (this.rest) this.clock.clear(this.rest);
    this.rest = null;
    this.board.begin();
    if (this.unwatch) this.unwatch();
    this.unwatch = null;
    if (this.panel && this.panel.remove) this.panel.remove();
    else if (this.panel && this.panel.parentNode && this.panel.parentNode.removeChild) this.panel.parentNode.removeChild(this.panel);
    this.panel = null;
    this.target = null;
  }

  el(tag, cls, text) {
    const node = this.doc.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  button(cls, text, onClick) {
    const btn = this.el('button', cls, text);
    btn.type = 'button';
    btn.addEventListener('click', onClick);
    return btn;
  }

  /** `only` - the column's word when the popover holds its head alone (no formula stands on the column). */
  draw(columns, only = null) {
    const { table, column } = this.target;
    this.columns = columns;
    this.formula = null;
    const panel = this.el('div', 'glass-dropdown-panel formula-pop');
    panel.setAttribute('role', 'dialog');
    const title = only === null ? `Formula · ${table}.${column}` : `${table} · ${only}`;
    panel.setAttribute('aria-label', title);

    const head = this.el('div', 'formula-pop__head');
    head.appendChild(this.el('span', 'formula-pop__title', title));
    // the header's right click is where a column is hidden too (owner 11-05); «N hidden» shows it again
    if (this.hide) head.appendChild(this.button('btn-quiet formula-pop__hide', 'Hide column', () => { this.hide(column); this.close(); }));
    const shut = this.button('btn-quiet formula-pop__close', '×', () => this.close());
    shut.setAttribute('aria-label', 'Close');
    head.appendChild(shut);
    panel.appendChild(head);
    if (only !== null) { this.mount(panel); return; }

    const entry = this.el('div', 'formula-pop__entry');
    entry.appendChild(this.el('span', 'formula-pop__label', 'Formula'));
    // the server reads the formula: its refusal comes back with the preview (refuse)
    this.formula = new FormulaInput(entry, { doc: this.doc, cls: 'formula-pop__input', placeholder: '=[a]+[b]*3',
      label: 'Formula', columns: () => this.columns, onInput: () => this.typed(), onEnter: () => this.preview() });
    this.input = this.formula.input;
    panel.appendChild(entry);

    if (columns.length) {
      const insert = this.el('div', 'formula-pop__insert');
      insert.appendChild(this.el('span', 'formula-pop__label', 'Insert column'));
      for (const name of columns) insert.appendChild(this.button('chip formula-pop__chip', `[${name}]`, () => this.insert(name)));
      panel.appendChild(insert);
    }

    this.out = this.el('div', 'formula-pop__preview');
    this.out.hidden = true;
    panel.appendChild(this.out);

    const foot = this.el('div', 'formula-pop__foot');
    this.removeBtn = this.button('btn-quiet btn-danger formula-pop__remove', 'Remove formula', () => this.commit('remove'));
    this.removeBtn.hidden = true;
    foot.appendChild(this.removeBtn);
    foot.appendChild(this.button('formula-pop__cancel', 'Cancel', () => this.close()));
    this.applyBtn = this.button('btn-primary formula-pop__apply', 'Apply', () => this.commit('save'));
    setDisabledReason(this.applyBtn, NEEDS_PREVIEW);
    foot.appendChild(this.applyBtn);
    panel.appendChild(foot);
    this.mount(panel);
  }

  /** The drawn panel in its host, shut by a press outside or Esc. */
  mount(panel) {
    this.host.appendChild(panel);
    this.panel = panel;
    this.unwatch = watchForDismiss(this.doc, panel, () => this.close());
  }

  /** Under its anchor, kept on screen - again whenever the preview or a refusal changes its height. */
  fit() {
    if (this.anchor && this.panel) placeUnder(this.panel, this.anchor, { align: 'left' });
  }

  /** `[name]` where the caret is, then the preview as if typed. */
  insert(name) { this.formula.insert(`[${name}]`); }

  /** Text changed: what was previewed no longer stands for it; its preview is asked once typing rests. */
  typed() {
    this.previewed = null;
    setDisabledReason(this.applyBtn, NEEDS_PREVIEW);
    if (this.rest) this.clock.clear(this.rest);
    this.rest = this.clock.set(() => { this.rest = null; this.preview(); }, PREVIEW_REST_MS);
  }

  refuse(sentence) {
    this.formula.refuse(sentence);
    this.fit();
  }

  async preview() {
    if (!this.target) return;
    const formula = (this.input.value || '').trim();
    const ticket = this.board.begin();
    if (!formula) { this.refuse(''); this.out.hidden = true; return; }
    const said = await this.send(formulaRequest('preview', { ...this.target, formula }), { signal: ticket.signal });
    if (!ticket.current() || !this.target) return;
    if (!said.ok) {
      this.refuse(said.error);
      this.out.hidden = true;
      setDisabledReason(this.applyBtn, REFUSED_FIRST);
      return;
    }
    this.refuse('');
    this.drawPreview(said.body || {});
    this.previewed = formula;
    setDisabledReason(this.applyBtn, '');
  }

  drawPreview(answer) {
    const out = this.out;
    out.textContent = '';
    out.appendChild(this.el('span', 'formula-pop__section', 'Preview'));
    const line = recomputeLine(answer.count);
    const count = this.el('span', 'formula-pop__count', line.text);
    if (line.at) count.appendChild(this.el('span', 'formula-pop__at', ` (${line.at})`));
    out.appendChild(count);
    const table = previewTable(answer.sample);
    if (table.rows.length) {
      const box = this.el('div', 'formula-pop__table');
      const t = this.el('table');
      const hr = this.el('tr');
      table.head.forEach((h, i) => hr.appendChild(this.el('th', table.numeric[i] ? 'is-num' : '', h)));
      const thead = this.el('thead');
      thead.appendChild(hr);
      t.appendChild(thead);
      const tbody = this.el('tbody');
      for (const row of table.rows) {
        const tr = this.el('tr');
        row.cells.forEach((v, i) => {
          const last = i === row.cells.length - 1;
          const cls = [table.numeric[i] ? 'is-num' : '', i === row.cells.length - 2 ? 'formula-pop__now' : '',
            last ? 'formula-pop__becomes' : '', last && row.changed ? 'is-changed' : ''].filter(Boolean).join(' ');
          tr.appendChild(this.el('td', cls, v));
        });
        tbody.appendChild(tr);
      }
      t.appendChild(tbody);
      box.appendChild(t);
      out.appendChild(box);
    }
    if (answer.says) out.appendChild(this.el('span', 'formula-pop__says', answer.says));
    out.hidden = false;
    this.fit();
  }

  /** Apply (save) or Remove: the server's answer is the toast; a refusal stays in the popover, word for word. */
  async commit(kind) {
    if (!this.target) return;
    if (kind === 'save' && (this.previewed === null || this.previewed !== (this.input.value || '').trim())) return;
    const target = this.target;
    setDisabledReason(this.applyBtn, SENDING);
    setDisabledReason(this.removeBtn, SENDING);
    const said = await this.send(formulaRequest(kind, { ...target, formula: this.previewed || '', base: this.base }));
    if (this.target !== target) return;
    setDisabledReason(this.removeBtn, '');
    if (!said.ok) {
      this.refuse(said.error);
      setDisabledReason(this.applyBtn, REFUSED_FIRST);
      return;
    }
    this.say(doneLine(kind, said.body), 'success',
      this.openQueue ? { action: { label: 'Open queue', run: this.openQueue } } : {});
    this.close();
    this.onSaved(target);
  }
}

/**
 * The header of a column that has a formula (AG-Grid's innerHeaderComponent, drawn inside the header's own text span):
 * its name and an «fx» mark. Pressing the mark opens the formula; it is not a press on the header - it does not sort
 * and does not start a column drag. params: displayName · formula · open(anchor).
 */
export class FormulaHeader {
  init(params) {
    const doc = params.doc || (typeof document !== 'undefined' ? document : null);
    this.gui = doc.createElement('span');
    this.gui.className = 'formula-header';
    this.name = doc.createElement('span');
    this.gui.appendChild(this.name);
    this.mark = doc.createElement('button');
    this.mark.type = 'button';
    this.mark.className = 'formula-mark';
    this.mark.textContent = 'fx';
    const stop = (e) => { if (e && e.stopPropagation) e.stopPropagation(); };
    this.mark.addEventListener('mousedown', stop);
    this.mark.addEventListener('click', (e) => {
      stop(e);
      if (e && e.preventDefault) e.preventDefault();
      if (this.params && this.params.open) this.params.open(this.mark);
    });
    this.gui.appendChild(this.mark);
    this.refresh(params);
  }

  getGui() { return this.gui; }

  refresh(params) {
    this.params = params;
    this.name.textContent = params.displayName == null ? '' : String(params.displayName);
    this.mark.title = params.formula || '';
    this.mark.setAttribute('aria-label', `Formula ${params.formula || ''}`.trim());
    return true;
  }
}
