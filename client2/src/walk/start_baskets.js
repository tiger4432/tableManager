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

export const BASKET_WORDS = Object.freeze({
  positive: 'Positive',
  negative: 'Negative',
  add: '+ Add',
  remove: '×',
  empty: 'Empty',
  noPick: 'Pick a node first',
  noStart: 'Add a start to Positive first',
});

export class StartBaskets {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, markings: object, name: string, picked?: Function}} deps
   *   `picked()` - the node PICK A NODE holds now, `{ id, label, type, keys }`, or null
   */
  constructor(mount, deps = {}) {
    this.doc = deps.doc || mount.ownerDocument;
    this.markings = deps.markings;
    this.name = deps.name;
    this.picked = deps.picked || (() => null);
    this.known = new Map();
    this.root = this.doc.createElement('div');
    this.root.className = 'wk-baskets';
    mount.appendChild(this.root);
    // Whoever writes the marking, the baskets say it as it stands.
    this.unsubscribe = this.markings.subscribe(this.name, () => this.render());
    this.render();
  }

  /** How a start was named when it was put in: `{ label, type, keys }`, or null for a node no basket was handed. */
  describe(id) { return this.known.get(id) || null; }

  /** The picked node into the basket of `sign`; from the other basket it moves. */
  add(sign) {
    const node = this.picked();
    if (!node) return;
    this.known.set(node.id, { label: node.label, type: node.type, keys: { ...(node.keys || {}) } });
    this.markings.set(this.name, node.id, sign);
  }

  remove(id) { this.markings.set(this.name, id, SIGN.ABSENT); }

  _el(tag, cls, text) {
    const n = this.doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  render() {
    this.root.textContent = '';
    const entries = this.markings.entries(this.name);
    const node = this.picked();
    for (const [sign, word, mark] of [[SIGN.CASE, BASKET_WORDS.positive, '+'], [SIGN.CONTROL, BASKET_WORDS.negative, '−']]) {
      const ids = entries.filter(([, s]) => s === sign).map(([id]) => id);
      const box = this._el('section', 'wk-basket' + (sign === SIGN.CONTROL ? ' is-control' : ''));
      box.setAttribute('data-sign', mark);
      const head = this._el('div', 'wk-baskethead');
      head.append(this._el('span', 'wk-label', word), this._el('span', 'wk-basketcount', String(ids.length)));
      const add = this._el('button', 'wk-basketadd', BASKET_WORDS.add);
      add.type = 'button';
      add.setAttribute('aria-label', `Add the picked node to ${word}`);
      setDisabledReason(add, node ? '' : BASKET_WORDS.noPick);
      add.addEventListener('click', () => this.add(sign));
      box.append(head, add);
      if (!ids.length) box.append(this._el('div', 'wk-note', BASKET_WORDS.empty));
      for (const id of ids) {
        const said = this.describe(id) || {};
        const row = this._el('div', 'wk-basketrow');
        row.setAttribute('data-start', id);
        row.append(this._el('span', 'wk-basketlabel', said.label || id), this._el('span', 'wk-baskettype', said.type || ''));
        const x = this._el('button', 'wk-basketremove', BASKET_WORDS.remove);
        x.type = 'button';
        x.setAttribute('aria-label', `Remove ${said.label || id}`);
        x.addEventListener('click', () => this.remove(id));
        row.append(x);
        box.append(row);
      }
      this.root.append(box);
    }
  }
}
