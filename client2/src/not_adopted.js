// «Not adopted» under the chain rules (owner 11-08 ㄱ): the chain's layers no rule owns - written before ownership - by
// who wrote them, as the chain worker's last census lap counted them (GET /admin/chain/rules `not_adopted`). They stay
// as they are; the way out is the rule's re-run, then R2 withdraw of the old name. No request of its own: the page
// hands in the rules answer it already read.
import { localShort } from './server_time.js';
import './not_adopted.css';

export const NOT_ADOPTED = 'Not adopted';
export const COUNTING = 'Counting - the first pass has not ended';
export const NONE = 'None - every chain layer has its rule';
export const WAY_OUT = 'Re-run the rule, then withdraw the old name (R2)';

/** The rules answer's census: {at, layers, names} · null (no pass ended) · undefined (not read - keep what is drawn). */
export function notAdoptedOf(rules) {
  if (!rules || typeof rules !== 'object' || !('not_adopted' in rules)) return undefined;
  const n = rules.not_adopted;
  return n && typeof n === 'object' ? { at: n.at, layers: n.layers || 0, names: Array.isArray(n.names) ? n.names : [] }
    : null;
}

export class NotAdopted {
  /** @param deps { doc } */
  constructor(mount, { doc } = {}) {
    this.mount = mount;
    this.doc = doc || mount.ownerDocument;
    this.root = this.el(mount, 'div', 'not-adopted', '');
    this.head = this.el(this.root, 'div', 'not-adopted__head', '');
    this.el(this.head, 'span', 'not-adopted__label', NOT_ADOPTED);
    this.at = this.el(this.head, 'span', 'not-adopted__at', '');
    this.state = this.el(this.root, 'div', 'not-adopted__state', COUNTING);
    this.list = this.el(this.root, 'table', 'not-adopted__list', '');
    this.way = this.el(this.root, 'div', 'not-adopted__way', WAY_OUT);
    this.render(null);
  }

  el(parent, tag, cls, text) {
    const e = this.doc.createElement(tag);
    e.className = cls;
    e.textContent = text;
    parent.appendChild(e);
    return e;
  }

  /** `census` from notAdoptedOf: undefined leaves the block as it is. */
  render(census) {
    if (census === undefined) return;
    const names = census ? census.names : [];
    this.root.dataset.state = !census ? 'counting' : names.length ? 'rows' : 'none';
    this.at.textContent = census && census.at ? `as of ${localShort(new Date(census.at * 1000).toISOString())}` : '';
    this.state.textContent = !census ? COUNTING : names.length ? '' : NONE;
    this.state.hidden = Boolean(census && names.length);
    this.list.replaceChildren();
    this.list.hidden = this.way.hidden = !names.length;
    for (const row of names) {
      const tr = this.el(this.list, 'tr', 'not-adopted__row', '');
      this.el(tr, 'td', 'not-adopted__name', row.name || '(no writer)');
      this.el(tr, 'td', 'not-adopted__count', `${Number(row.layers || 0).toLocaleString('en-US')} layer(s)`);
      this.el(tr, 'td', 'not-adopted__tables',
        (row.tables || []).map(([table, n]) => `${table} ${Number(n).toLocaleString('en-US')}`).join(' · '));
    }
  }
}
