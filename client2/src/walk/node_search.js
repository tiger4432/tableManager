// ═══════════════════════════════════════════════════════════════════════════════
// NODE SEARCH — PICK A NODE found by its first letters (owner 10-10 «pick a node 좀 더 검색 기능 및 속도 강화해 logN 으로»,
// lead bccbdd601). A pause in typing asks the server once for the nodes whose key starts with what is typed - the
// ledger's own index, whatever its size - and the first ones hang under the box. A press or Enter picks one; what is
// typed and not picked stays the key as typed.
//
// The box stands for ONE key, the one the server searches by (its answer's prefix_axis): the page draws no second cell
// for it. A type the server cannot search by first letters says why (prefix_refusal) and the page types its keys in
// their own cells.
// ═══════════════════════════════════════════════════════════════════════════════
import { LOADING, unitText } from '../ui_words.js';
import { isBlank } from '../absent.js';

/** How many nodes one answer hangs under the box, and how long typing rests before it asks. */
export const SEARCH_LIMIT = 20;
export const SEARCH_DELAY_MS = 250;

export const SEARCH_WORDS = Object.freeze({
  hint: 'First letters',
  none: (prefix) => `No node starts with ${prefix} · + Add takes it as typed`,
  empty: 'No node of this type in the ledger',
  scanCut: (n) => `Not every node read (up to ${n})`,
  more: (n) => `${unitText(n, 'node')} shown · not all · type more`,
  failed: (why) => `Node list · ${why}`,
});
/** The server's prefix_case, said where the letters are typed. */
const CASE_HINT = Object.freeze({ insensitive: 'First letters · any case', exact: 'First letters · exact case' });

export class NodeSearch {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, ask: Function, onType?: Function, onPick?: Function, delay?: number}} deps
   *   `ask(prefix)` answers as fetchKeyValues does - `{ ok, nodes, scanned, scanTruncated, valuesTruncated, prefixAxis,
   *   prefixCase, prefixRefusal, message }`; `onType(text)` hears every keystroke; `onPick(node)` the node picked
   */
  constructor(mount, deps = {}) {
    this.doc = deps.doc || mount.ownerDocument;
    this.ask = deps.ask;
    this.onType = deps.onType || (() => {});
    this.onPick = deps.onPick || (() => {});
    this.delay = deps.delay === undefined ? SEARCH_DELAY_MS : deps.delay;
    this.axis = null;
    this.state = 'idle';
    this.answer = null;
    this.asked = '';
    this.active = -1;
    this.isOpen = false;
    this.seq = 0;
    this.timer = null;
    this.root = this._el('div', 'wk-search');
    this.cell = this._el('label', 'wk-cell');
    this.name = this._el('span', 'wk-keyname');
    this.input = this._el('input', 'wk-input');
    this.input.type = 'text';
    this.input.setAttribute('role', 'combobox');
    this.input.setAttribute('aria-autocomplete', 'list');
    this.cell.append(this.name, this.input);
    this.list = this._el('div', 'wk-searchlist');
    this.list.setAttribute('role', 'listbox');
    this.note = this._el('div', 'wk-note');
    this.root.append(this.cell, this.list, this.note);
    mount.appendChild(this.root);
    this.input.addEventListener('input', () => {
      this.onType(this.input.value);
      this.isOpen = true;
      clearTimeout(this.timer);
      this.timer = setTimeout(() => { void this._ask(this.input.value); }, this.delay);
    });
    // Focused or pressed, the list opens - a press reopens it after Escape.
    const open = () => { this.isOpen = true; this._draw(); };
    this.input.addEventListener('focus', open);
    this.input.addEventListener('click', open);
    this.input.addEventListener('blur', () => { this.isOpen = false; this._draw(); });
    this.input.addEventListener('keydown', (e) => this._key(e));
    this._draw();
  }

  _el(tag, cls, text) {
    const n = this.doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  /** A new type: forget the old one's answer and ask the first nodes once, which also says the key the box stands for. */
  async open() {
    clearTimeout(this.timer);
    this.axis = null;
    this.answer = null;
    this.asked = '';
    this.input.value = '';
    this.state = 'loading';
    this._draw();
    const got = await this._ask('');
    if (!got) return null;
    this.axis = (got.ok && got.prefixAxis) || null;
    this.state = 'ready';
    this._draw();
    return got;
  }

  /** The page sets the box's text (a pick, a type change) without asking. */
  setText(text) {
    const value = text === undefined || text === null ? '' : String(text);
    if (this.input.value !== value) this.input.value = value;
  }

  async _ask(text) {
    const mine = ++this.seq;
    const prefix = isBlank(text) ? '' : String(text).trim();
    const got = await this.ask(prefix);
    // A later keystroke or type asked since: this answer is for letters no longer in the box.
    if (mine !== this.seq) return null;
    this.answer = got;
    this.asked = prefix;
    this.active = -1;
    this._draw();
    return got;
  }

  _nodes() { return (this.answer && this.answer.ok && this.answer.nodes) || []; }

  _pick(i) {
    const node = this._nodes()[i];
    if (!node) return;
    this.isOpen = false;
    this.active = -1;
    this._draw();
    this.onPick(node);
  }

  _key(e) {
    const n = this._nodes().length;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!n) return;
      e.preventDefault();
      this.isOpen = true;
      this.active = e.key === 'ArrowDown' ? Math.min(this.active + 1, n - 1) : Math.max(this.active - 1, 0);
      this._draw();
    } else if (e.key === 'Enter') {
      // Only an answer for the letters in the box: before it lands, the key as typed stands.
      const now = isBlank(this.input.value) ? '' : String(this.input.value).trim();
      if (!this.isOpen || !n || now !== this.asked) return;
      e.preventDefault();
      this._pick(this.active >= 0 ? this.active : 0);
    } else if (e.key === 'Escape') {
      this.isOpen = false;
      this._draw();
    }
  }

  _draw() {
    const got = this.answer;
    const refusal = got && got.ok && !got.prefixAxis && got.prefixRefusal;
    // No box when the server cannot search this type by first letters: its sentence stands where the box was.
    this.cell.hidden = this.state === 'loading' || Boolean(refusal);
    this.name.textContent = this.axis || '';
    this.input.placeholder = CASE_HINT[got && got.prefixCase] || SEARCH_WORDS.hint;
    this.input.setAttribute('aria-expanded', String(this.isOpen && this._nodes().length > 0));
    this.list.textContent = '';
    this.note.textContent = '';
    let say = '';
    if (this.state === 'loading') say = LOADING;
    else if (refusal) say = refusal;
    else if (got && !got.ok) say = SEARCH_WORDS.failed(got.message);
    // Nothing of this type to open a list on: said with the box closed.
    else if (got && !this._nodes().length && !this.asked) {
      say = got.scanTruncated ? SEARCH_WORDS.scanCut(got.scanned) : SEARCH_WORDS.empty;
    } else if (got && this.isOpen) {
      const nodes = this._nodes();
      nodes.forEach((node, i) => {
        const item = this._el('div', 'wk-searchitem' + (i === this.active ? ' is-active' : ''));
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(i === this.active));
        item.setAttribute('data-index', String(i));
        item.append(this._el('span', 'wk-searchkey', Object.values(node.keys || {}).map((v) => String(v)).join(' · ')));
        if (node.count) item.append(this._el('span', 'wk-searchcount', String(node.count)));
        // mousedown, not click: the box keeps its focus, so the list is still there when the press lands.
        item.addEventListener('mousedown', (e) => { e.preventDefault(); this._pick(i); });
        this.list.append(item);
      });
      if (!nodes.length) say = SEARCH_WORDS.none(this.asked);
      else if (got.valuesTruncated) say = SEARCH_WORDS.more(nodes.length);
    }
    this.list.hidden = !this.list.children.length;
    this.note.textContent = say;
    this.note.hidden = !say;
  }
}
