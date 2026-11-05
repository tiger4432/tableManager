// «N hidden ▾» in the filter chip row (owner 11-05): the data columns hidden - by the column chooser or a header's
// «Hide column» - listed under it, each shown again alone or all at once. The pivot's held item column is not one.
import { placeUnder, watchForDismiss } from './dropdown.js';

/** One part: its own div in `mount`. deps: doc · show(colIds) - the page's one way to show columns. */
export class HiddenColumns {
  constructor(mount, deps = {}) {
    this.doc = deps.doc || mount.ownerDocument;
    this.show = deps.show;
    this.root = this.el('div', 'hidden-cols');
    this.button = this.el('button', 'filter-chips-more hidden-cols__open');
    this.button.type = 'button';
    this.button.addEventListener('click', () => (this.panel ? this.close() : this.open()));
    this.root.appendChild(this.button);
    mount.appendChild(this.root);
    this.hidden = [];
    this.panel = null;
    this.unwatch = null;
    this.draw([]);
  }

  el(tag, cls, text) {
    const node = this.doc.createElement(tag);
    node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /** `hidden` - [{id, word}] in the grid's order; none hides the chip. */
  draw(hidden) {
    this.hidden = hidden;
    this.root.hidden = !hidden.length;
    this.button.textContent = `${hidden.length} hidden ▾`;
    if (!hidden.length) this.close();
    else if (this.panel) this.fill();
  }

  open() {
    this.panel = this.el('div', 'glass-dropdown-panel hidden-cols__panel');
    this.root.appendChild(this.panel);
    this.fill();
    this.unwatch = watchForDismiss(this.doc, this.root, () => this.close());
  }

  fill() {
    const rows = this.hidden.map(({ id, word }) => {
      const row = this.el('div', 'hidden-cols__row');
      const show = this.el('button', 'btn-quiet hidden-cols__show', 'Show');
      show.type = 'button';
      show.addEventListener('click', () => this.show([id]));
      row.append(this.el('span', 'hidden-cols__word', word), show);
      return row;
    });
    const all = this.el('button', 'ctl-small hidden-cols__all', 'Show all');
    all.type = 'button';
    all.addEventListener('click', () => this.show(this.hidden.map((col) => col.id)));
    this.panel.replaceChildren(...rows, all);
    placeUnder(this.panel, this.button, { align: 'left' });
  }

  close() {
    if (this.unwatch) this.unwatch();
    this.unwatch = null;
    if (this.panel) this.panel.remove();
    this.panel = null;
  }
}
