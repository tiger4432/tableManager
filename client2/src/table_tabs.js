// The «Open tables» row under the top bar (owner 11-05 ㄱ, mockup v3): one tab per open table - its name, a note (its
// filters, a pivot), × to close - the open one marked; past `fit` tabs the rest go under «+N ▾».
// A part: its own mount and callbacks, no module state - two rows on one page do not meet.

const FIT = 8;

export class TableTabs {
  /** `mount` an element (the nav); `onPick(table)` · `onClose(table)`; `noteOf(table)` -> a short word or ''. */
  constructor({ mount, onPick, onClose, noteOf = () => '', fit = FIT, doc = document }) {
    this.mount = mount;
    this.onPick = onPick;
    this.onClose = onClose;
    this.noteOf = noteOf;
    this.fit = fit;
    this.doc = doc;
    this.moreOpen = false;
  }

  _el(tag, cls, text) {
    const n = this.doc.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  _tab(table, current) {
    const tab = this._el('span', 'table-tab' + (table === current ? ' is-open' : ''));
    tab.dataset.table = table;
    const name = this._el('button', 'table-tab-name', table);
    name.type = 'button';
    if (table === current) name.setAttribute('aria-current', 'page');
    name.addEventListener('click', () => { if (table !== current) this.onPick(table); });
    tab.append(name);
    const note = this.noteOf(table);
    if (note) tab.append(this._el('span', 'table-tab-note', note));
    const close = this._el('button', 'table-tab-close', '×');
    close.type = 'button';
    close.setAttribute('aria-label', `Close ${table}`);
    close.addEventListener('click', (e) => { e.stopPropagation(); this.onClose(table); });
    tab.append(close);
    return tab;
  }

  /** Draw `tables` with `current` open. The open table always shows in the row, even when it is past `fit`. */
  draw(tables, current) {
    const list = Array.isArray(tables) ? tables : [];
    let shown = list.slice(0, this.fit);
    if (current && list.includes(current) && !shown.includes(current)) shown = [...shown.slice(0, this.fit - 1), current];
    const rest = list.filter((t) => !shown.includes(t));
    this.mount.replaceChildren(...shown.map((t) => this._tab(t, current)));
    this.mount.hidden = list.length === 0;
    if (!rest.length) { this.moreOpen = false; return; }
    const more = this._el('span', 'table-tab-more');
    const btn = this._el('button', 'table-tab-more-btn', `+${rest.length} ▾`);
    btn.type = 'button';
    btn.setAttribute('aria-expanded', String(this.moreOpen));
    btn.addEventListener('click', () => { this.moreOpen = !this.moreOpen; this.draw(list, current); });
    more.append(btn);
    if (this.moreOpen) {
      const menu = this._el('div', 'table-tab-menu');
      menu.setAttribute('role', 'menu');
      for (const t of rest) {
        const item = this._el('button', 'table-tab-menu-item', t);
        item.type = 'button';
        item.setAttribute('role', 'menuitem');
        item.addEventListener('click', () => { this.moreOpen = false; this.onPick(t); });
        menu.append(item);
      }
      more.append(menu);
    }
    this.mount.append(more);
  }
}

/** A tab's note from what its table was left as: «N filters», «pivot» - '' when it says nothing. */
export function tableNote(settings) {
  if (!settings) return '';
  const n = settings.filterModel ? Object.keys(settings.filterModel).length : 0;
  return [n ? `${n} ${n === 1 ? 'filter' : 'filters'}` : '', settings.pivot ? 'pivot' : ''].filter(Boolean).join(' · ');
}

/** ← → over the tables opened in this browser tab, and the address saying the table (?table=, so a reload opens it):
 *  each table opened is a step; Back / Forward walk them through the browser's own history; a step walked opens its
 *  table without adding a step. -> { went(table) } for the table follower. */
export function tableSteps({ back, forward, open, win = window }) {
  let at = (win.history.state && win.history.state.tableStep) || 0;
  let top = at;
  let walking = false;
  let restoring = false;
  const paint = () => {
    if (back) back.disabled = at <= 0;
    if (forward) forward.disabled = at >= top;
  };
  win.addEventListener('popstate', (e) => {
    const step = e.state;
    if (!step || !step.table) return;
    const from = at;
    at = step.tableStep || 0;
    if (restoring) { restoring = false; paint(); return; }
    walking = true;
    // refused (edits staged): the table on screen did not move, so the address goes back to it
    Promise.resolve(open(step.table)).then((opened) => {
      if (opened === false && at !== from) { restoring = true; win.history.go(from - at); }
    }).finally(() => { walking = false; paint(); });
  });
  if (back) back.addEventListener('click', () => win.history.back());
  if (forward) forward.addEventListener('click', () => win.history.forward());
  paint();
  return {
    went(table) {
      if (walking) return;
      const here = win.history.state;
      if (here && here.table === table) return;
      const url = new URL(win.location.href);
      url.searchParams.set('table', table);
      url.searchParams.delete('tx');
      if (!here || !here.table) {
        win.history.replaceState({ table, tableStep: at }, '', url);
      } else {
        at += 1;
        top = at;
        win.history.pushState({ table, tableStep: at }, '', url);
      }
      paint();
    },
  };
}
