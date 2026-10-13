// The start row: the walk page's own pickers - a node type, NodeSearch (the key typed, the node picked) and StartBaskets
// (+ and −) - writing the marking the visuals start from. A seat around them, so the grid can hold them and take them away.

import { Panel } from '../rnd_board/panel.js';
import { SIGN } from '../rnd_board/marking_store.js';
import { entitySeedId } from '../rnd_board/api.js';
import { NodeSearch } from '../walk/node_search.js';
import { StartBaskets } from '../walk/start_baskets.js';
import { isBlank } from '../absent.js';
import { ensureWalkStyles } from '../walk/styles.js';

export class StartPart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const d = deps || {};
    this.entities = d.entities || (() => []);
    this.askKeys = d.askKeys;
    this.type = d.type || null;
    this.keys = {};
  }

  mount() {
    const doc = this.doc;
    // The walk page's pickers wear the walk page's styles.
    ensureWalkStyles(doc);
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    const root = el('div', 'tb-start');
    root.append(el('span', 'tb-start__lab', 'Start'));
    const pick = el('div', 'tb-start__pick');
    this.select = el('select', 'tb-start__type');
    this.select.setAttribute('aria-label', 'Node type');
    this.search = new NodeSearch(el('div', ''), { doc,
      ask: (prefix) => this.askKeys({ type: this.type, startsWith: prefix }),
      onType: (text) => { if (this.search.axis) this.keys = { [this.search.axis]: text }; this.baskets.render(); },
      onPick: (node) => { this.keys = { ...node.keys }; this.search.setText(node.keys[this.search.axis] || ''); this.baskets.render(); this.baskets.take(); },
      onAnswer: () => this.baskets.render() });
    pick.append(this.select, this.search.root);
    this.baskets = new StartBaskets(el('span', ''), { doc, markings: this.markings, name: this.writes, picked: () => this.picked(), pick });
    this.select.addEventListener('change', () => { this.type = this.select.value; this.keys = {}; void this.search.open(); this.baskets.render(); });
    root.append(this.baskets.root);
    this.host.replaceChildren(root);
    this.fillTypes();
  }

  /** The types the declaration names; the first picked when none is. */
  fillTypes() {
    const types = this.entities().map((e) => e.type);
    this.select.replaceChildren(...types.map((t) => { const o = this.doc.createElement('option'); o.value = t; o.textContent = t; return o; }));
    if (!this.type || !types.includes(this.type)) this.type = types[0] || null;
    if (this.type) { this.select.value = this.type; void this.search.open(); }
  }

  /** The node the + takes: the type and the keys typed or picked. */
  picked() {
    const keys = Object.fromEntries(Object.entries(this.keys || {}).filter(([, v]) => !isBlank(v)));
    if (!this.type || !Object.keys(keys).length) return null;
    return { id: entitySeedId(this.type, keys), label: Object.values(keys).join(' · '), type: this.type, keys,
      unheld: this.search.holdsNone ? this.search.holdsNone(keys[this.search.axis]) : false };
  }

  add(sign = SIGN.CASE) { this.baskets.add(sign); }

  destroy() {
    if (this.search) clearTimeout(this.search.timer);
    if (this.baskets && this.baskets.unsubscribe) this.baskets.unsubscribe();
    super.destroy();
  }
}
