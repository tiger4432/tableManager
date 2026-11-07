// A column's formula, on its header (owner 10-28 option A): right-click the header, or press its «fx» mark, and the
// column's same-row formula opens under it - its preview over the table's first rows and how many rows saving recomputes,
// the server's refusal word for word, Apply and Remove. The formula is a chain rule the server keeps (`chain.formula`,
// B 9d56d6f1d); this part sends text and draws answers - it does not read the formula. As one types (owner's mockup,
// 11-07) it offers what the caret stands in: function names with their arguments, a column after «[», and inside a
// call that call's arguments with the one being typed in bold.
//
// NO NETWORK, NO DOM GLOBALS: `send` and `doc` come in (the grid page hands adminFetch's; the harness a fake).
import { setDisabledReason } from './disabled_reason.js';
import { SIGNATURES } from './expression.js';
import { placeUnder, watchForDismiss } from './dropdown.js';
import { ReadBoard } from './latest_read.js';
import { countNumberText, countOf, COUNT_FAILED, COUNTING_ROWS } from './match_count.js';
import { OptionList } from './option_list.js';
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

/** Scans `text` up to `caret`: is the caret in a text in quotes, in an open «[», and the calls still open there. */
function scan(text, caret) {
  const before = String(text || '').slice(0, caret);
  const calls = [];
  let quote = null;
  let bracket = -1;
  for (let i = 0; i < before.length; i += 1) {
    const ch = before[i];
    if (quote) { if (ch === quote) quote = null; continue; }
    if (bracket >= 0) { if (ch === ']') bracket = -1; continue; }
    if (ch === '"' || ch === "'") quote = ch;
    else if (ch === '[') bracket = i;
    else if (ch === '(') { const m = /([A-Za-z_][A-Za-z0-9_]*)\s*$/.exec(before.slice(0, i)); calls.push({ name: m ? m[1] : '', arg: 0 }); }
    else if (ch === ')') calls.pop();
    else if (ch === ',' && calls.length) calls[calls.length - 1].arg += 1;
  }
  return { before, quote, bracket, calls };
}

/** What the caret stands in, for the list under the formula: a column's name after an open «[», or a function's name -
 *  {kind: 'column' | 'function', from, prefix}, `from` where the name begins; null in a text in quotes or elsewhere. */
export function completionAt(text, caret) {
  const { before, quote, bracket } = scan(text, caret);
  if (quote) return null;
  if (bracket >= 0) return { kind: 'column', from: bracket + 1, prefix: before.slice(bracket + 1) };
  const word = /[A-Za-z_][A-Za-z0-9_]*$/.exec(before);
  if (!word || /[A-Za-z0-9_.]/.test(before[word.index - 1] || '')) return null;
  return { kind: 'function', from: word.index, prefix: word[0] };
}

/** The call the caret is inside and which of its arguments it is in: {name, arg} for the innermost «name(» still open;
 *  null outside one. */
export function callAt(text, caret) {
  const { calls } = scan(text, caret);
  const at = calls[calls.length - 1];
  return at && at.name ? { name: at.name, arg: at.arg } : null;
}

const signatureOf = (name) => SIGNATURES.find((s) => s.name.toLowerCase() === String(name).toLowerCase()) || null;
/** «Name(a, b)» - the signature line's words. */
export const signatureText = (s) => `${s.name}(${s.args.join(', ')})`;

const byName = (a, b) => (a.name.toLowerCase() < b.name.toLowerCase() ? -1 : a.name.toLowerCase() > b.name.toLowerCase() ? 1 : 0);
/** What the list offers at `caret`: {from, kind, items: [{value, head, rest, side}]} - the names starting with what is
 *  typed, any case (functions by name, columns in the table's order); null when nothing does. A function needs a letter
 *  typed; after «[» every column is offered. */
export function offerAt(text, caret, columns = []) {
  const c = completionAt(text, caret);
  if (!c || (c.kind === 'function' && !c.prefix)) return null;
  const typed = c.prefix.toLowerCase();
  const names = c.kind === 'function' ? SIGNATURES.filter((s) => s.name.toLowerCase().startsWith(typed)).sort(byName)
    : columns.filter((name) => String(name).toLowerCase().startsWith(typed)).map((name) => ({ name: String(name) }));
  if (!names.length) return null;
  // a column as it goes in: [name]
  const column = c.kind === 'column';
  return { from: c.from, kind: c.kind, items: names.map((s) => ({ value: s.name, before: column ? '[' : '',
    head: s.name.slice(0, c.prefix.length), rest: s.name.slice(c.prefix.length) + (column ? ']' : ''),
    side: column ? '' : signatureText(s) })) };
}

/** `value` taken into `text` for the name the caret stands in: a function as «Name(», a column as «name]» (over a «]»
 *  already there) - {text, caret}. */
export function acceptAt(text, caret, offer, value) {
  const t = String(text || '');
  const after = t.slice(caret);
  const rest = offer.kind === 'function' ? /^[A-Za-z0-9_]*/.exec(after)[0] : (/^[^[\](),]*\]/.exec(after) || [''])[0];
  const piece = offer.kind === 'function' ? `${value}(` : `${value}]`;
  return { text: t.slice(0, offer.from) + piece + after.slice(rest.length), caret: offer.from + piece.length };
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
    this.offer = null;
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
    this.offer = null;
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

    const field = this.el('label', 'formula-pop__field');
    field.appendChild(this.el('span', 'formula-pop__label', 'Formula'));
    this.input = this.el('input', 'formula-pop__input');
    this.input.type = 'text';
    this.input.spellcheck = false;
    this.input.placeholder = '=[a]+[b]*3';
    this.input.setAttribute('role', 'combobox');
    this.input.setAttribute('aria-autocomplete', 'list');
    this.input.addEventListener('input', () => this.typed());
    this.input.addEventListener('keydown', (e) => this.key(e));
    // the caret moved without typing: what it stands in now
    this.input.addEventListener('click', () => this.suggest());
    this.input.addEventListener('keyup', (e) => { if (e && /^(ArrowLeft|ArrowRight|Home|End)$/.test(e.key)) this.suggest(); });
    field.appendChild(this.input);
    this.list = this.el('div', 'formula-pop__complete');
    this.list.hidden = true;
    this.options = new OptionList(this.list, { doc: this.doc, onPick: (i) => this.accept(i) });
    field.appendChild(this.list);
    // The field and the server's refusal under it are one block; the call's arguments hang under that block - under the
    // refusal when there is one, both read (owner 11-07), else right under the field.
    const entry = this.el('div', 'formula-pop__entry');
    entry.appendChild(field);

    this.why = this.el('div', 'formula-pop__why');
    this.why.setAttribute('role', 'alert');
    this.why.hidden = true;
    entry.appendChild(this.why);
    this.sign = this.el('div', 'formula-pop__signature');
    this.sign.setAttribute('role', 'status');
    this.sign.hidden = true;
    entry.appendChild(this.sign);
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
  insert(name) {
    const text = this.input.value || '';
    const at = Number.isInteger(this.input.selectionStart) ? this.input.selectionStart : text.length;
    const end = Number.isInteger(this.input.selectionEnd) ? this.input.selectionEnd : at;
    const piece = `[${name}]`;
    this.input.value = text.slice(0, at) + piece + text.slice(end);
    if (this.input.setSelectionRange) this.input.setSelectionRange(at + piece.length, at + piece.length);
    if (this.input.focus) this.input.focus();
    this.typed();
  }

  caret() {
    const text = this.input.value || '';
    return Number.isInteger(this.input.selectionStart) ? this.input.selectionStart : text.length;
  }

  /** What the caret stands in: the names that start with what is typed (the first lit), else the arguments of the call
   *  it is inside, the one it is in bold; else nothing. */
  suggest() {
    const text = this.input.value || '';
    const at = this.caret();
    this.offer = offerAt(text, at, this.columns);
    if (this.offer) this.options.show(this.offer.items, 0);
    else this.options.clear();
    this.list.hidden = !this.offer;
    this.input.setAttribute('aria-expanded', this.offer ? 'true' : 'false');
    const call = this.offer ? null : callAt(text, at);
    const s = call && signatureOf(call.name);
    this.sign.textContent = '';
    if (s) {
      // the argument being typed; past the last, the «...» that takes more
      const lit = s.args[s.args.length - 1] === '...' ? Math.min(call.arg, s.args.length - 1) : call.arg;
      this.sign.appendChild(this.el('span', '', `${s.name}(`));
      s.args.forEach((a, i) => {
        if (i) this.sign.appendChild(this.el('span', '', ', '));
        this.sign.appendChild(this.el(i === lit ? 'b' : 'span', '', a));
      });
      this.sign.appendChild(this.el('span', '', ')'));
    }
    this.sign.hidden = !s;
  }

  closeList() {
    this.offer = null;
    this.options.clear();
    this.list.hidden = true;
    this.input.setAttribute('aria-expanded', 'false');
  }

  /** The offered row `i` into the formula where the caret is. */
  accept(i) {
    const item = this.offer && this.offer.items[i];
    if (!item) return;
    const took = acceptAt(this.input.value || '', this.caret(), this.offer, item.value);
    this.input.value = took.text;
    if (this.input.setSelectionRange) this.input.setSelectionRange(took.caret, took.caret);
    if (this.input.focus) this.input.focus();
    this.typed();
  }

  /** With the list open, ↑↓ move its lit row, Enter or Tab take it and Esc closes the list alone; else Enter previews.
   *  A key that closes a Korean syllable is the input method's. */
  key(e) {
    if (!e || e.isComposing === true || e.keyCode === 229) return;
    const open = !this.list.hidden && this.options.size > 0;
    if (open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      if (e.preventDefault) e.preventDefault();
      this.options.move(e.key === 'ArrowDown' ? 1 : -1);
    } else if (open && (e.key === 'Enter' || e.key === 'Tab')) {
      if (e.preventDefault) e.preventDefault();
      this.accept(this.options.active);
    } else if (open && e.key === 'Escape') {
      // the popover stays: its press-outside-or-Esc watch is on the document, this key does not reach it
      if (e.stopPropagation) e.stopPropagation();
      this.closeList();
    } else if (e.key === 'Enter') this.preview();
  }

  /** Text changed: what was previewed no longer stands for it; its preview is asked once typing rests. */
  typed() {
    this.suggest();
    this.previewed = null;
    setDisabledReason(this.applyBtn, NEEDS_PREVIEW);
    if (this.rest) this.clock.clear(this.rest);
    this.rest = this.clock.set(() => { this.rest = null; this.preview(); }, PREVIEW_REST_MS);
  }

  refuse(sentence) {
    this.why.textContent = sentence || '';
    this.why.hidden = !sentence;
    this.input.setAttribute('aria-invalid', sentence ? 'true' : 'false');
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
