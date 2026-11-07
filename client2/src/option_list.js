// ONE LIST OF OPTIONS under a box (lead 11-07): its rows, the one active row, ↑↓ moving it, a press picking a row, the
// active row kept in view, and listbox · option · aria-selected. The walk's node search, a grid cell's value suggestions
// and the formula popover draw their lists through this part; where the list stands, when it opens, which row is active
// on opening and what a pick does are theirs.
//
// The mount is the list itself: rows are its children, nothing between (a caller may add its own lines after them).
// Its look comes with it (ensureStyle): the walk page loads no base.css. Each rule is :where - a page's own class wins.
import { ensureStyle } from './style_once.js';

const STAMP = 'data-option-list-styles';

/** A row at the small height; what was typed bold; the active row the accent's. */
export const OPTION_LIST_CSS = `
:where(.option-list) { display: flex; flex-direction: column; }
:where(.option-list__row) { display: flex; align-items: center; gap: var(--space-3); min-height: var(--control-h-small);
  padding: 0 var(--space-3); font-family: var(--font-mono); font-size: var(--fs-button); font-variant-numeric: tabular-nums;
  white-space: nowrap; color: var(--text); cursor: pointer; }
:where(.option-list__row:hover) { background: var(--tint-hover); }
:where(.option-list__row.is-active) { background: var(--accent-weak); color: var(--accent); }
/* a value longer than the list ends in «…», saying it was cut */
:where(.option-list__text) { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
:where(.option-list__text b) { font-weight: 700; }
:where(.option-list__side) { flex: none; margin-left: auto; color: var(--text-dim); }
`;

/**
 * @param {HTMLElement} mount  the listbox
 * @param {{doc?: Document, onPick?: (index: number) => void}} deps
 */
export class OptionList {
  constructor(mount, deps = {}) {
    this.root = mount;
    this.doc = deps.doc || mount.ownerDocument;
    this.onPick = deps.onPick || (() => {});
    this.rows = [];
    this.active = -1;
    if (!String(mount.className || '').split(/\s+/).includes('option-list')) {
      mount.className = [mount.className, 'option-list'].filter(Boolean).join(' ');
    }
    mount.setAttribute('role', 'listbox');
    ensureStyle(this.doc, STAMP, OPTION_LIST_CSS);
  }

  get size() { return this.rows.length; }

  el(tag, cls, text) {
    const node = this.doc.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /** Draws `items` ({before, head, rest, side}: `head` bold - what was typed, `before` ahead of it; `side` at the row's
   *  right) with `active` lit (-1: none). */
  show(items, active = -1) {
    this.root.textContent = '';
    this.rows = items.map((item, i) => {
      const row = this.el('div', 'option-list__row');
      row.setAttribute('role', 'option');
      const text = this.el('span', 'option-list__text');
      if (item.head) {
        if (item.before) text.appendChild(this.el('span', '', item.before));
        text.appendChild(this.el('b', '', item.head));
        text.appendChild(this.el('span', '', item.rest || ''));
      } else text.textContent = (item.before || '') + (item.rest || '');
      row.appendChild(text);
      if (item.side) row.appendChild(this.el('span', 'option-list__side', item.side));
      // mousedown, not click: the box keeps its focus, so the list is still there when the press lands
      row.addEventListener('mousedown', (e) => { if (e && e.preventDefault) e.preventDefault(); this.onPick(i); });
      this.root.appendChild(row);
      return row;
    });
    this.active = -1;
    this.light(active >= 0 && active < this.rows.length ? active : -1);
  }

  /** Empties the list. */
  clear() { this.show([]); }

  /** The active row `step` rows on, held to the first and the last; none active yet, the first. */
  move(step) {
    if (!this.rows.length) return this.active;
    this.light(Math.min(this.rows.length - 1, Math.max(0, this.active + step)));
    return this.active;
  }

  light(index) {
    const lit = (row, on) => {
      if (!row) return;
      row.className = on ? 'option-list__row is-active' : 'option-list__row';
      row.setAttribute('aria-selected', on ? 'true' : 'false');
    };
    this.rows.forEach((row, i) => { if (i !== index) lit(row, false); });
    this.active = index;
    lit(this.rows[index], true);
    const row = this.rows[index];
    if (row && typeof row.scrollIntoView === 'function') row.scrollIntoView({ block: 'nearest' });
  }
}
