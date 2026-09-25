// OVERVIEW BOARD — mockup A's STATUS section: one line per part, red rows need a look.
//
// Draws and decides NOTHING: every row arrives already judged from `overview_status.js`, and the
// board only seats it — [dot] [name] [facts] [word] [Open ›], five columns, one line each.
// A row whose page handed it a BODY opens in place under itself; the body is an element the PAGE
// owns (the loops table, the declaration check, the running list) and is moved in once, so the
// part that fills it keeps its own mount.
//
// One mount, one div, no module state — two boards on one page do not touch each other.
import { ROW_ORDER } from './overview_status.js';

export class OverviewBoard {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, order?: string[], bodies?: Object<string, HTMLElement>,
   *          open?: Object<string, Function>}} [deps]
   *   bodies  key -> the element that opens under that row
   *   open    key -> what 「Open ›」 does; a row without one has no button
   */
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('OverviewBoard needs a mount element');
    this.doc = deps.doc || mount.ownerDocument;
    this.root = this.doc.createElement('div');
    this.root.className = 'ov-board';
    this.seats = new Map();
    const bodies = deps.bodies || {};
    const open = deps.open || {};
    for (const key of deps.order || ROW_ORDER) this._seat(key, bodies[key], open[key]);
    mount.appendChild(this.root);
  }

  _cell(cls) {
    const el = this.doc.createElement('span');
    el.className = cls;
    return el;
  }

  _seat(key, body, open) {
    const doc = this.doc;
    const line = doc.createElement('div');
    line.className = 'ov-row';
    line.setAttribute('data-key', key);
    const seat = { line, dot: this._cell('ov-row-dot'), name: this._cell('ov-row-name'),
                   facts: this._cell('ov-row-facts'), word: this._cell('ov-row-word'), wrap: null };
    for (const cell of [seat.dot, seat.name, seat.facts, seat.word]) line.appendChild(cell);
    let btn = null;
    if (open) {
      btn = doc.createElement('button');
      btn.type = 'button';
      btn.className = 'ov-row-open';
      btn.textContent = 'Open ›';
      btn.addEventListener('click', () => open());
      line.appendChild(btn);
    } else {
      line.appendChild(this._cell('ov-row-open'));
    }
    this.root.appendChild(line);
    if (body) {
      const wrap = doc.createElement('div');
      wrap.className = 'ov-row-body';
      wrap.hidden = true;
      wrap.appendChild(body);
      this.root.appendChild(wrap);
      seat.wrap = wrap;
      line.setAttribute('role', 'button');
      line.setAttribute('tabindex', '0');
      line.setAttribute('aria-expanded', 'false');
      const toggle = () => this.toggle(key);
      // 「Open ›」 goes to the tab; it does not also fold the row open on its way out.
      line.addEventListener('click', (e) => { if (!btn || e.target !== btn) toggle(); });
      line.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
      });
    }
    this.seats.set(key, seat);
  }

  /** @param {{key: string, name: string, facts: string[], tone: string, word: string}} row */
  update(row) {
    const seat = row && this.seats.get(row.key);
    if (!seat) return;
    seat.line.setAttribute('data-tone', row.tone);
    seat.name.textContent = row.name;
    seat.facts.textContent = row.facts.join(' · ');
    seat.word.textContent = row.word;
  }

  /** Open or close the body under a row. Returns whether it is open now. */
  toggle(key, open) {
    const seat = this.seats.get(key);
    if (!seat || !seat.wrap) return false;
    const next = open === undefined ? seat.wrap.hidden : !!open;
    seat.wrap.hidden = !next;
    seat.line.setAttribute('aria-expanded', String(next));
    return next;
  }
}
