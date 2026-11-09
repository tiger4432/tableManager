// One formula field (owner 11-09 «ㄴ»). As one types it offers what the caret stands in - the functions with their
// arguments (the catalogue's signatures), a column after «[», the words a field takes beside a formula - and inside a
// call that call's arguments with the one being typed in bold; under it the refusal line. Four places write formulas
// with it: a column's formula (formula_popover.js), a colour rule's condition (look_panel.js), the test bed's custom
// expression (testbed/picker.js) and a chain rule's formula cells (the skeleton's `formula` leaves).
//
// It reads nothing itself: what it offers and what it refuses come in (`deps`). No module state - two on one page are
// two fields.
import { SIGNATURES, ESCAPED } from './expression.js';
import { OptionList } from './option_list.js';

/** Scans `text` up to `caret`: is the caret in a text in quotes, in an open «[», and the calls still open there. */
function scan(text, caret) {
  const before = String(text || '').slice(0, caret);
  const calls = [];
  let quote = null;
  let bracket = -1;
  for (let i = 0; i < before.length; i += 1) {
    const ch = before[i];
    if (quote) {
      if (ch === '\\' && ESCAPED.includes(before[i + 1] || '')) i += 1;
      else if (ch === quote) quote = null;
      continue;
    }
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
  const word = /[A-Za-z_][A-Za-z0-9_.]*$/.exec(before);
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

export const signatureOf = (name) => SIGNATURES.find((s) => s.name.toLowerCase() === String(name).toLowerCase()) || null;
/** «Name(a, b)» - the signature line's words. */
export const signatureText = (s) => `${s.name}(${s.args.join(', ')})`;

const byName = (a, b) => (a.name.toLowerCase() < b.name.toLowerCase() ? -1 : a.name.toLowerCase() > b.name.toLowerCase() ? 1 : 0);
/** What the list offers at `caret`: {from, kind, items: [{value, head, rest, side}]} - the names starting with what is
 *  typed, any case (functions and `words` by name, columns in the table's order); null when nothing does. A function
 *  needs a letter typed; after «[» every column is offered; an empty field offers every word it takes. `words`: what
 *  the field takes beside a formula. */
export function offerAt(text, caret, columns = [], words = []) {
  const c = String(text || '').trim() || !words.length ? completionAt(text, caret) : { kind: 'function', from: 0, prefix: '' };
  if (!c || (c.kind === 'function' && !c.prefix && String(text || '').trim())) return null;
  const typed = c.prefix.toLowerCase();
  const starts = (name) => String(name).toLowerCase().startsWith(typed);
  const names = c.kind === 'function'
    ? [...(c.prefix ? SIGNATURES.filter((s) => starts(s.name)) : []), ...words.filter(starts).map((w) => ({ name: String(w), word: true }))].sort(byName)
    : columns.filter(starts).map((name) => ({ name: String(name) }));
  if (!names.length) return null;
  // a column as it goes in: [name]
  const column = c.kind === 'column';
  return { from: c.from, kind: c.kind, items: names.map((s) => ({ value: s.name, word: Boolean(s.word), before: column ? '[' : '',
    head: s.name.slice(0, c.prefix.length), rest: s.name.slice(c.prefix.length) + (column ? ']' : ''),
    side: column || s.word ? '' : signatureText(s) })) };
}

/** `value` taken into `text` for the name the caret stands in: a function as «Name(», a word as itself, a column as
 *  «name]» (over a «]» already there) - {text, caret}. */
export function acceptAt(text, caret, offer, value, word = false) {
  const t = String(text || '');
  const after = t.slice(caret);
  const rest = offer.kind === 'function' ? /^[A-Za-z0-9_.]*/.exec(after)[0] : (/^[^[\](),]*\]/.exec(after) || [''])[0];
  const piece = offer.kind === 'function' ? (word ? value : `${value}(`) : `${value}]`;
  return { text: t.slice(0, offer.from) + piece + after.slice(rest.length), caret: offer.from + piece.length };
}

/**
 * One formula field drawn into `host`. `deps`:
 *   doc          the document
 *   columns      () -> the names offered after «[»
 *   words        () -> what the field takes beside a formula, offered with the functions
 *   refusal      (text) -> why `text` cannot stand, or '' - read as one types; without it the field's owner says (refuse)
 *   onInput      (text) - typed
 *   onEnter      (text) - Enter with no list open
 *   cls · placeholder · label (its accessible name) · name · value
 */
export class FormulaInput {
  constructor(host, deps = {}) {
    this.doc = deps.doc;
    this.deps = deps;
    this.offer = null;
    const el = (tag, cls) => { const node = this.doc.createElement(tag); node.className = cls; return node; };
    this.root = el('div', 'formula-input');
    this.input = el('input', `formula-input__input${deps.cls ? ` ${deps.cls}` : ''}`);
    this.input.type = 'text';
    this.input.spellcheck = false;
    this.input.autocomplete = 'off';
    if (deps.placeholder) this.input.placeholder = deps.placeholder;
    if (deps.name) this.input.name = deps.name;
    if (deps.label) this.input.setAttribute('aria-label', deps.label);
    this.input.setAttribute('role', 'combobox');
    this.input.setAttribute('aria-autocomplete', 'list');
    this.input.setAttribute('aria-expanded', 'false');
    this.input.value = deps.value || '';
    this.input.addEventListener('input', () => this.typed());
    this.input.addEventListener('keydown', (e) => this.key(e));
    // the caret moved without typing: what it stands in now
    this.input.addEventListener('click', () => this.suggest());
    this.input.addEventListener('focus', () => this.suggest());
    this.input.addEventListener('keyup', (e) => { if (e && /^(ArrowLeft|ArrowRight|Home|End)$/.test(e.key)) this.suggest(); });
    this.input.addEventListener('blur', () => this.closeList());
    this.list = el('div', 'formula-input__complete');
    this.list.hidden = true;
    this.options = new OptionList(this.list, { doc: this.doc, onPick: (i) => this.accept(i) });
    // The field and the refusal under it are one block; the call's arguments hang under that block - under the
    // refusal when there is one, both read (owner 11-07), else right under the field.
    this.why = el('div', 'formula-input__why');
    this.why.setAttribute('role', 'alert');
    this.why.hidden = true;
    this.sign = el('div', 'formula-input__signature');
    this.sign.setAttribute('role', 'status');
    this.sign.hidden = true;
    // the list hangs under the field itself, the arguments under the whole block
    const field = el('div', 'formula-input__field');
    field.appendChild(this.input);
    field.appendChild(this.list);
    this.root.appendChild(field);
    this.root.appendChild(this.why);
    this.root.appendChild(this.sign);
    host.appendChild(this.root);
    // a value it was given is read as typed ones are: a saved formula drawn again says why it is refused
    this.check();
  }

  get value() { return this.input.value || ''; }

  set value(text) {
    this.input.value = text || '';
    this.check();
  }

  focus() { if (this.input.focus) this.input.focus(); }

  caret() {
    const text = this.value;
    return Number.isInteger(this.input.selectionStart) ? this.input.selectionStart : text.length;
  }

  /** `piece` where the caret is (over what is selected), then as if typed. */
  insert(piece) {
    const text = this.value;
    const at = this.caret();
    const end = Number.isInteger(this.input.selectionEnd) ? this.input.selectionEnd : at;
    this.input.value = text.slice(0, at) + piece + text.slice(end);
    if (this.input.setSelectionRange) this.input.setSelectionRange(at + piece.length, at + piece.length);
    this.focus();
    this.told();
  }

  /** Text the field put in itself (a row taken, a piece inserted), told as typing is - the page's own `input`
   *  listeners too, where the document has events (a form that writes on input). */
  told() {
    const Ev = this.doc.defaultView && this.doc.defaultView.Event;
    if (Ev && this.input.dispatchEvent) this.input.dispatchEvent(new Ev('input', { bubbles: true }));
    else this.typed();
  }

  /** The refusal line: `sentence`, or none. */
  refuse(sentence) {
    this.why.textContent = sentence || '';
    this.why.hidden = !sentence;
    this.input.setAttribute('aria-invalid', sentence ? 'true' : 'false');
  }

  /** The field's own reading, when it has one. */
  check() {
    if (this.deps.refusal) this.refuse(this.value.trim() ? this.deps.refusal(this.value) : '');
  }

  /** What the caret stands in: the names that start with what is typed (the first lit), else the arguments of the call
   *  it is inside, the one it is in bold; else nothing. */
  suggest() {
    const text = this.value;
    const at = this.caret();
    const columns = this.deps.columns ? this.deps.columns() : [];
    const words = this.deps.words ? this.deps.words() : [];
    this.offer = offerAt(text, at, columns, words);
    if (this.offer) this.options.show(this.offer.items, 0);
    else this.options.clear();
    this.list.hidden = !this.offer;
    this.input.setAttribute('aria-expanded', this.offer ? 'true' : 'false');
    const call = this.offer ? null : callAt(text, at);
    const s = call && signatureOf(call.name);
    this.sign.textContent = '';
    if (s) {
      const el = (tag, text2) => { const node = this.doc.createElement(tag); node.textContent = text2; return node; };
      // the argument being typed; past the last, the «...» that takes more
      const lit = s.args[s.args.length - 1] === '...' ? Math.min(call.arg, s.args.length - 1) : call.arg;
      this.sign.appendChild(el('span', `${s.name}(`));
      s.args.forEach((a, i) => {
        if (i) this.sign.appendChild(el('span', ', '));
        this.sign.appendChild(el(i === lit ? 'b' : 'span', a));
      });
      this.sign.appendChild(el('span', ')'));
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
    const took = acceptAt(this.value, this.caret(), this.offer, item.value, item.word);
    this.input.value = took.text;
    if (this.input.setSelectionRange) this.input.setSelectionRange(took.caret, took.caret);
    this.focus();
    this.told();
  }

  /** With the list open, ↑↓ move its lit row, Enter or Tab take it and Esc closes the list alone; else Enter is the
   *  owner's. A key that closes a Korean syllable is the input method's. */
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
      // the owner stays open: its press-outside-or-Esc watch is on the document, this key does not reach it
      if (e.stopPropagation) e.stopPropagation();
      this.closeList();
    } else if (e.key === 'Enter' && this.deps.onEnter) {
      if (e.preventDefault) e.preventDefault();
      this.deps.onEnter(this.value);
    }
  }

  typed() {
    this.suggest();
    this.check();
    if (this.deps.onInput) this.deps.onInput(this.value);
  }
}
