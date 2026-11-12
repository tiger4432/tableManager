// The page a template runs on, as the batch reads it (lib/batch.js): the list's items not read yet, opening one and
// looking at the content area (lib/open_check.js), the content area, closing, and the next page.
import { shownAll, visibleText, waitOpened, waitStill } from './open_check.js';
import { readColumn } from './extract.js';
import { areasOf } from './selectors.js';

const pause = (ms) => new Promise((r) => setTimeout(r, ms));

/** The content area on the screen, as one base: of each area its selector lists («a, b» - a title and a body may be two),
 *  the elements shown - a hidden copy passed by; several shown, the ones whose text is not `was`'s (before the click).
 *  null when none is shown. */
export function contentOf(t, doc, win, was = null) {
  const els = [...new Set(areasOf(t.content).flatMap((area) => {
    const on = shownAll(doc, area, win);
    const moved = was && on.length > 1 ? on.filter((el) => was.get(el) !== visibleText(el)) : [];
    return moved.length ? moved : on;
  }))];
  if (els.length < 2) return els[0] || null;
  return {
    innerText: els.map(visibleText).join('\n'),
    querySelector: (s) => els.map((el) => el.querySelector(s)).find(Boolean) || null,
    getAttribute: (a) => els[0].getAttribute(a),
  };
}

/** In a tab a link opened: wait for the content area to show text (and the pair to agree), then read `fields` there. */
export async function readOpenedHere(t, fields, pairValue, { doc = document, win = window } = {}) {
  const content = () => contentOf(t, doc, win);
  const look = () => {
    const el = content();
    return { isShown: Boolean(el), after: visibleText(el), pair: t.pair && el ? { item: pairValue, content: readColumn(el, t.pair.content) } : null };
  };
  const o = await waitOpened(look, { before: '', limitMs: t.waitSeconds * 1000 });
  return o.opened ? { opened: true, cells: Object.fromEntries(fields.map((f) => [f.column, readColumn(content(), f)])) } : o;
}

export class DomPage {
  constructor(t, { doc = document, win = window, openTab = null } = {}) {
    this.t = t;
    this.openTab = openTab;     // (address, fields) -> {opened, detail, cells}: a link opened in a tab of its own
    this.doc = doc;
    this.win = win;
    this.read = new Map();          // item element -> its text when read (a list that reuses its elements shows new text)
  }

  area() { return shownAll(this.doc, this.t.listArea, this.win)[0] || this.doc; }
  all() { return [...this.area().querySelectorAll(this.t.item)]; }
  fresh() { return this.all().filter((el) => !this.read.has(el) || this.read.get(el) !== visibleText(el)); }

  items(most) {
    const out = this.fresh().slice(0, most);
    for (const el of out) this.read.set(el, visibleText(el));
    return out;
  }

  where() { return this.win.location.href; }
  base(h) { return h; }

  content() { return contentOf(this.t, this.doc, this.win, this.was); }

  /** The content area's print - the whole text of every element its selector names, hidden or not: a pane hidden by a
   *  close still holds the last body, and that body showing again is not a change. */
  print() { return [...this.doc.querySelectorAll(this.t.content || ':not(*)')].map((e) => e.textContent.replace(/\s+/g, ' ').trim()).join(' | '); }

  look(h) {
    const el = this.content();
    const pair = this.t.pair && el ? { item: readColumn(h, this.t.pair.item), content: readColumn(el, this.t.pair.content) } : null;
    return { isShown: Boolean(el), after: this.print(), pair };
  }

  async open(h, fields) {
    const target = (this.t.clickTarget && h.querySelector(this.t.clickTarget)) || h;
    if (this.t.opens === 'new_tab') {
      const address = target.href || (target.querySelector('a[href]') || {}).href;
      if (!address) return { opened: false, detail: 'no link to open' };
      return this.openTab(address, fields, this.t.pair ? readColumn(h, this.t.pair.item) : null);
    }
    const limitMs = this.t.waitSeconds * 1000;
    // the item before did not open: its late content first, or this item is kept unopened. Content later than twice the
    // wait is not caught - the pane stood still and this item opens (QA 11-11, bench X7)
    // `late`: 'clicked' - the item before was clicked and did not open; 'kept' - it was kept unclicked, the area still moving
    if (this.late && !(await waitStill(() => this.print(), { limitMs }))) {
      const s = Math.round(limitMs / 1000);
      const detail = this.late === 'clicked' ? `the item before did not settle in ${s} s - raise Wait` : `the content area did not settle in ${s} s - raise Wait`;
      this.late = 'kept';
      return { opened: false, detail };
    }
    target.scrollIntoView({ block: 'nearest' });
    const before = this.print();
    this.was = new Map([...this.doc.querySelectorAll(this.t.content || ':not(*)')].map((el) => [el, visibleText(el)]));
    target.click();
    const o = await waitOpened(() => this.look(h), { before, limitMs });
    this.late = o.opened ? null : 'clicked';
    return o;
  }

  async close() {
    const c = shownAll(this.doc, this.t.close, this.win)[0];
    if (c) { c.click(); await pause(50); }
  }

  /** The next page - the button clicked, or the list area scrolled to its end - -> 'more' when new items came in time. */
  async next() {
    if (this.t.next.how === 'scroll') {
      const a = this.area();
      if (a === this.doc) this.win.scrollTo(0, this.doc.documentElement.scrollHeight); else a.scrollTop = a.scrollHeight;
    } else {
      const b = shownAll(this.doc, this.t.next.selector, this.win, { scroll: true })[0];   // below the fold is not hidden
      if (!b || b.disabled || b.getAttribute('aria-disabled') === 'true') return 'none';
      b.click();
    }
    const end = Date.now() + this.t.endSeconds * 1000;
    for (;;) {
      if (this.fresh().length) return 'more';
      if (Date.now() >= end) return 'none';
      await pause(150);
    }
  }
}
