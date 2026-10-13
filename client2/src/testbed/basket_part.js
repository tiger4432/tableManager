// The basket (lead aca803a7a): what a marking holds, as Spotfire's table draws rows - a node a line, a hub one line that
// opens into its members. Its own part: { reads: marking }.

import { Panel } from '../rnd_board/panel.js';
import { isHubId, hubWords } from './hubs.js';
import { writeClipboardRich } from '../clipboard_write.js';
import { escapeHtml } from '../utils.js';

export class BasketPart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const d = deps || {};
    this.hubs = d.hubs;
    this.names = d.names || new Map();
    this.open = new Set();
  }

  /** Every node the marking holds, a hub opened into its members - what Copy ids copies. */
  nodeIds() {
    const entries = this.reads ? this.markings.entries(this.reads) : [];
    return [...new Set(entries.flatMap(([id]) => (isHubId(id) ? this.hubs.membersOf(id) : [id])))];
  }

  render() {
    const doc = this.doc;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    const entries = this.reads ? this.markings.entries(this.reads) : [];
    const hubs = entries.filter(([id]) => isHubId(id)).length;
    const root = el('section', 'sf-part tb-basket');
    const title = el('div', 'sf-part__title');
    title.append(el('span', 'sf-part__t', this.title || 'Marked'),
      el('span', 'sf-part__meta', `${entries.length - hubs} nodes · ${hubs} hubs`));
    const copy = el('button', 'sf-btn', 'Copy ids');
    copy.type = 'button';
    copy.addEventListener('click', () => { const ids = this.nodeIds(); writeClipboardRich(`<pre>${escapeHtml(ids.join('\n'))}</pre>`, ids.join('\n')); });
    const clear = el('button', 'sf-btn', 'Clear');
    clear.type = 'button';
    clear.addEventListener('click', () => { if (this.reads) this.markings.clear(this.reads); });
    title.append(copy, clear);
    const table = el('table', 'sf-table sf-table--rows');
    const head = el('tr');
    for (const words of ['', 'Type', 'Node', 'Members', 'Id']) head.append(el('th', '', words));
    table.append(head);
    const line = (cells, cls) => { const tr = el('tr', cls); for (const c of cells) tr.append(c); table.append(tr); return tr; };
    const said = (id) => this.names.get(id) || {};
    if (!entries.length) line([el('td'), el('td', '', 'Nothing marked')]);
    for (const [id] of entries) {
      if (isHubId(id)) {
        const members = this.hubs.membersOf(id);
        const toggle = el('button', 'sf-table__toggle', this.open.has(id) ? '▾' : '▸');
        toggle.type = 'button';
        toggle.setAttribute('aria-label', this.open.has(id) ? 'Close the hub' : 'Open the hub');
        toggle.addEventListener('click', () => { if (this.open.has(id)) this.open.delete(id); else this.open.add(id); this.render(); });
        const td = el('td');
        td.append(toggle);
        line([td, el('td', '', 'hub'), el('td', '', hubWords(id)), el('td', 'is-num', String(members.length)), el('td')], 'is-hub');
        if (this.open.has(id)) {
          for (const m of members) line([el('td'), el('td', '', said(m).type || ''), el('td', 'is-member', said(m).label || m), el('td'), el('td', 'is-id', m)], 'is-member-row');
        }
      } else {
        line([el('td'), el('td', '', said(id).type || ''), el('td', '', said(id).label || id), el('td'), el('td', 'is-id', id)]);
      }
    }
    const scroll = el('div', 'tb-basket__scroll');
    scroll.append(table);
    root.append(title, scroll);
    this.host.replaceChildren(root);
  }
}
