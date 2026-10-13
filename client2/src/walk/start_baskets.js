// ═══════════════════════════════════════════════════════════════════════════════
// START BASKETS — the walk's start marking edited as two baskets (owner 10-10 «pos, neg 를 복수로 · 걷기 우측 패널에
// 장바구니 느낌으로 · 각각 + 버튼해서 노드 넣게 · walk 버튼은 장바구니 넣은 걸로 걷기 요청», lead bc63378e5).
//
// The baskets keep no list of their own: they read and write one marking of the page's store, Positive its + marks and
// Negative its - marks. A node has one sign, so + on the other basket moves it. What a basket remembers is only how to
// name a node it was handed (label, type, keys) - the page asks it that when it walks or names a start.
// ═══════════════════════════════════════════════════════════════════════════════
import { SIGN } from '../rnd_board/marking_store.js';
import { setDisabledReason } from '../disabled_reason.js';
import { fitUnder, watchForDismiss } from '../dropdown.js';

export const BASKET_WORDS = Object.freeze({
  positive: 'Positive',
  negative: 'Negative',
  addStart: '+ Add start',
  vs: 'vs',
  remove: '×',
  noPick: 'Pick a node first',
  noStart: 'Add a start to Positive first',
  // A key typed that the ledger names no node by (lead b5cdcbc75): + still takes it.
  unheld: '0 atoms · not in the ledger',
});

export class StartBaskets {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, markings: object, name: string, picked?: Function}} deps
   *   `picked()` - the node PICK A NODE holds now, `{ id, label, type, keys, unheld? }`, or null; `unheld` when no
   *   node of the ledger is those keys
   */
  constructor(mount, deps = {}) {
    this.doc = deps.doc || mount.ownerDocument;
    this.markings = deps.markings;
    this.name = deps.name;
    this.picked = deps.picked || (() => null);
    this.known = new Map();
    // The walk's sentence bar (lead 10-11 W A): the baskets as chips, then «+ Add start» - its dropdown seats the page's
    // `pick` (Type · Pick a node) once, so a redraw here never takes the caret from it, and the two adds.
    this.root = this._el('span', 'wk-baskets');
    this.list = this._el('span', 'wk-basketlist');
    this.pop = this._el('details', 'wk-barpop');
    const body = this._el('div', 'wk-barpopbody');
    this.adders = this._el('div', 'wk-adders');
    if (deps.pick) body.append(deps.pick);
    body.append(this.adders);
    const chip = this._el('summary', 'wk-barchip', BASKET_WORDS.addStart);
    this.pop.append(chip, body);
    this.root.append(this.list, this.pop);
    // Open, its window takes the one placement (dropdown.js fitUnder, lead 72b2d7f8f): under the chip, above it at the
    // foot of the page, cut and scrolled when neither fits; fixed, so a panel that clips its own box does not hide it.
    // The gap is the stylesheet's --space-1.
    this.place = () => { if (this.pop.open) fitUnder(body, chip, { align: 'left', gap: 3.4 }); };
    // Open, a click outside it or Escape shuts it - the one way a picker closes (dropdown.js watchForDismiss; lead 10-13,
    // 18766: it stayed over the graph after a start was put in); shut, it hears nothing.
    this.unwatch = null;
    this.onToggle = () => {
      this.place();
      if (this.pop.open && !this.unwatch) this.unwatch = watchForDismiss(this.doc, this.pop, () => this.close());
      else if (!this.pop.open) this.close();
    };
    if (this.pop.addEventListener) this.pop.addEventListener('toggle', this.onToggle);
    mount.appendChild(this.root);
    // Whoever writes the marking, the baskets say it as it stands.
    this.unsubscribe = this.markings.subscribe(this.name, () => this.render());
    this.render();
  }

  /** How a start was named when it was put in: `{ label, type, keys }`, or null for a node no basket was handed. */
  describe(id) { return this.known.get(id) || null; }

  /** The picked node - or the one handed (the graph's «Walk on from here») - into the basket of `sign`; from the other
   *  basket it moves. */
  add(sign, node = this.picked()) {
    if (!node) return;
    this.known.set(node.id, { label: node.label, type: node.type, keys: { ...(node.keys || {}) } });
    this.markings.set(this.name, node.id, sign);
  }

  remove(id) { this.markings.set(this.name, id, SIGN.ABSENT); }

  /** A node picked from the list: into Positive, and «+ Add start» shut (lead 10-14). */
  take(node = this.picked()) {
    this.add(SIGN.CASE, node);
    this.close();
  }

  /** «+ Add start» shut, and the page no longer heard. */
  close() {
    this.pop.open = false;
    if (this.unwatch) { this.unwatch(); this.unwatch = null; }
  }

  _el(tag, cls, text) {
    const n = this.doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  render() {
    this.list.textContent = '';
    this.adders.textContent = '';
    const entries = this.markings.entries(this.name);
    const node = this.picked();
    for (const [sign, word, mark] of [[SIGN.CASE, BASKET_WORDS.positive, '+'], [SIGN.CONTROL, BASKET_WORDS.negative, '−']]) {
      const ids = entries.filter(([, s]) => s === sign).map(([id]) => id);
      if (sign === SIGN.CONTROL) this.list.append(this._el('span', 'wk-vs', BASKET_WORDS.vs));
      const box = this._el('span', 'wk-basket' + (sign === SIGN.CONTROL ? ' is-control' : ''));
      box.setAttribute('data-sign', mark);
      box.title = word;
      box.append(this._el('span', 'wk-basketsign', mark), this._el('span', 'wk-basketcount', String(ids.length)));
      for (const id of ids) {
        const said = this.describe(id) || {};
        const row = this._el('span', 'wk-basketrow');
        row.setAttribute('data-start', id);
        row.title = said.type || '';
        row.append(this._el('span', 'wk-basketlabel', said.label || id));
        const x = this._el('button', 'wk-basketremove', BASKET_WORDS.remove);
        x.type = 'button';
        x.setAttribute('aria-label', `Remove ${said.label || id}`);
        x.addEventListener('click', () => this.remove(id));
        row.append(x);
        box.append(row);
      }
      this.list.append(box);
      const add = this._el('button', 'wk-basketadd', `${mark} ${word}`);
      add.type = 'button';
      add.setAttribute('data-sign', mark);
      add.setAttribute('aria-label', `Add the picked node to ${word}`);
      setDisabledReason(add, node ? '' : BASKET_WORDS.noPick);
      add.addEventListener('click', () => this.add(sign));
      this.adders.append(add);
    }
    if (node && node.unheld) this.adders.append(this._el('div', 'wk-note wk-unheld', BASKET_WORDS.unheld));
    // Its window grew or shrank (a node list came): placed again.
    this.place();
  }
}
