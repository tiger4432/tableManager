// The left bar (lead 10-13, Spotfire's): its chart button opens the add window beside it - a line a kind of the visual
// part, its picture and its name, in the kinds' order; a pick adds one (the page's `onAdd`) and the window closes, as a
// press outside it or Escape does. The window hangs over the page, not inside the bar.

import { Panel } from '../rnd_board/panel.js';

const SVG = 'http://www.w3.org/2000/svg';
const CHART = 'M4 12h4v9H4zM10 7h4v14h-4zM16 3h4v18h-4z';

export class BannerPart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const d = deps || {};
    this.kinds = d.kinds || {};
    this.onAdd = d.onAdd || (() => {});
    this.open = false;
  }

  mount() {
    super.mount();
    const doc = this.doc;
    this._press = (event) => {
      if (!this.open) return;
      const path = typeof event.composedPath === 'function' ? event.composedPath() : [event.target];
      if (!path.includes(this.flyout) && !path.includes(this.button)) this.toggle(false);
    };
    this._key = (event) => { if (event.key === 'Escape') this.toggle(false); };
    doc.addEventListener('mousedown', this._press);
    doc.addEventListener('keydown', this._key);
  }

  destroy() {
    if (typeof this.doc.removeEventListener === 'function') {
      this.doc.removeEventListener('mousedown', this._press);
      this.doc.removeEventListener('keydown', this._key);
    }
    super.destroy();
  }

  toggle(open) {
    this.open = open;
    this.render();
  }

  /** A kind's line in the window: picked, the kind added. */
  pick(name) {
    this.toggle(false);
    this.onAdd(name);
  }

  render() {
    const doc = this.doc;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    const icon = (paths, cls) => {
      const svg = doc.createElementNS(SVG, 'svg');
      svg.setAttribute('viewBox', '0 0 24 24');
      if (cls) svg.setAttribute('class', cls);
      for (const [d, opacity] of paths) {
        const path = doc.createElementNS(SVG, 'path');
        path.setAttribute('d', d);
        if (opacity !== 1) path.setAttribute('opacity', String(opacity));
        svg.appendChild(path);
      }
      return svg;
    };
    const bar = el('nav', 'sf-banner');
    this.button = el('button', `sf-banner__b${this.open ? ' is-on' : ''}`);
    this.button.type = 'button';
    this.button.title = 'Visualization types';
    this.button.setAttribute('aria-label', 'Visualization types');
    this.button.setAttribute('aria-expanded', String(this.open));
    this.button.append(icon([[CHART, 1]]));
    this.button.addEventListener('click', () => this.toggle(!this.open));
    bar.append(this.button);
    this.flyout = null;
    if (this.open) {
      const fly = el('div', 'sf-flyout');
      fly.setAttribute('role', 'menu');
      fly.append(el('div', 'sf-flyout__h', 'Visualization types'));
      for (const [name, kind] of Object.entries(this.kinds)) {
        const it = el('button', 'sf-flyout__it');
        it.type = 'button';
        it.setAttribute('role', 'menuitem');
        const pic = icon((kind.icon && kind.icon.paths) || [], 'sf-flyout__ico');
        if (kind.icon) pic.style.color = `var(--sf-${kind.icon.tone})`;
        it.append(pic, el('span', '', kind.label || name));
        it.addEventListener('click', () => this.pick(name));
        fly.append(it);
      }
      // Beside the bar, its height: the bar's box on the screen.
      if (this.host.getBoundingClientRect) {
        const box = this.host.getBoundingClientRect();
        Object.assign(fly.style, { left: `${box.right}px`, top: `${box.top}px`, height: `${box.height}px` });
      }
      this.flyout = fly;
      bar.append(fly);
    }
    this.host.replaceChildren(bar);
  }
}
