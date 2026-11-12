// AXIS COMPARE - the + rows and the − rows of one table side by side in ONE table (owner 11-11 drawing: «axis | + | −»):
// a line an axis value, a column the shown columns' values on each side, folded by the axis - a text column by
// UniqueConcatenate, a number column by Avg (owner «문자면 uniqueconcat, 숫자면 avg»), the calculator's own folds
// (expression.js foldItems). A line whose sides differ is flagged and goes up; «Differs only» keeps those. The Tables page
// and the walk's compare (클라2) place this one part - its data is flat rows per sign, never a walk's answer.
import { foldItems } from '../expression.js';
import { SIGN } from '../rnd_board/marking_store.js';
import { placeUnder, watchForDismiss } from '../dropdown.js';

export const FOLD_TEXT = 'UniqueConcatenate';
export const FOLD_NUMBER = 'Avg';
/** A side's sign as a head says it. */
export const SIDE_WORDS = Object.freeze({ [SIGN.CASE]: '+', [SIGN.CONTROL]: '−' });
/** What a side with no row of a line shows in each of its cells. */
export const MISSING = '−';

const spell = (v) => (v === null || v === undefined ? '' : String(v).trim());
const keyOf = (row, axes) => JSON.stringify(axes.map((a) => spell(row[a])));

/**
 * The lines: {axis: [axis values], cells: {sign: {column: folded value} | null}, differs: [columns], one: bool} - a line
 * a distinct axis value over both sides; a side without it null (`one`: on one side only); `differs` the columns whose
 * folded values are not the same. Differing lines first, then by the axis values.
 * @param {{sides: Array<{sign: number, rows: Array<object>}>, axes: string[], columns: string[], kinds?: object}} asked
 */
export function foldSides({ sides, axes, columns, kinds = {} }) {
  const fold = (rows, column) => foldItems(kinds[column] === 'number' ? FOLD_NUMBER : FOLD_TEXT,
    rows.map((r) => ({ value: r[column] }))).value;
  const groups = new Map();
  for (const side of sides) {
    for (const row of side.rows) {
      const key = keyOf(row, axes);
      if (!groups.has(key)) groups.set(key, { axis: axes.map((a) => row[a] ?? null), bySign: new Map() });
      const g = groups.get(key);
      if (!g.bySign.has(side.sign)) g.bySign.set(side.sign, []);
      g.bySign.get(side.sign).push(row);
    }
  }
  const lines = [...groups.values()].map((g) => {
    const cells = Object.fromEntries(sides.map((side) => {
      const rows = g.bySign.get(side.sign);
      return [side.sign, rows ? Object.fromEntries(columns.map((c) => [c, fold(rows, c)])) : null];
    }));
    const held = sides.map((s) => cells[s.sign]).filter(Boolean);
    const one = held.length < sides.length;
    const differs = held.length < 2 ? [] : columns.filter((c) => new Set(held.map((h) => spell(h[c]))).size > 1);
    return { axis: g.axis, cells, differs, one };
  });
  const order = (a, b) => {
    for (let i = 0; i < a.axis.length; i += 1) {
      const x = spell(a.axis[i]); const y = spell(b.axis[i]);
      const c = x.localeCompare(y, 'en', { numeric: true });
      if (c) return c;
    }
    return 0;
  };
  const up = (l) => (l.differs.length || l.one ? 0 : 1);
  return lines.sort((a, b) => up(a) - up(b) || order(a, b));
}

/** A folded value as a cell says it: a number to six significant digits. */
export function cellWords(value) {
  if (value === null || value === undefined) return '';
  return typeof value === 'number' ? String(Number(value.toPrecision(6))) : String(value);
}

/** A head's column pick: a button «Words (n)» opening a list of checks. */
class Pick {
  constructor(doc, words, onChange) {
    this.doc = doc;
    this.words = words;
    this.onChange = onChange;
    this.options = [];
    this.picked = [];
    this.root = this.el('span', 'tables-pick');
    this.button = this.el('button', 'ctl-small');
    this.button.type = 'button';
    this.root.append(this.button);
    this.button.addEventListener('click', () => (this.panel ? this.close() : this.open()));
    this.panel = null;
    this.draw();
  }

  el(tag, cls, text) { const n = this.doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

  set(options, picked) { this.options = options; this.picked = picked.filter((c) => options.includes(c)); this.draw(); }

  draw() { this.button.textContent = `${this.words} (${this.picked.length}) ▾`; }

  open() {
    const panel = this.el('div', 'tables-pick__panel');
    for (const column of this.options) {
      const label = this.el('label', 'tables-pick__row');
      const box = this.el('input');
      box.type = 'checkbox';
      box.checked = this.picked.includes(column);
      box.addEventListener('change', () => {
        this.picked = this.options.filter((c) => (c === column ? box.checked : this.picked.includes(c)));
        this.draw();
        this.onChange(this.picked);
      });
      label.append(box, this.el('span', '', column));
      panel.append(label);
    }
    this.panel = panel;
    this.root.append(panel);
    placeUnder(panel, this.button, { align: 'left' });
    this.unwatch = watchForDismiss(this.doc, this.root, () => this.close());
  }

  close() {
    if (this.unwatch) this.unwatch();
    this.unwatch = null;
    if (this.panel && this.panel.parentNode) this.panel.parentNode.removeChild(this.panel);
    this.panel = null;
  }
}

export class AxisCompare {
  /** @param {HTMLElement} mount  its own div
   *  @param {{doc: Document, onPick?: ({axes, columns, only}) => void}} deps  onPick: told each pick, so the page keeps it */
  constructor(mount, deps) {
    this.mount = mount;
    this.doc = deps.doc;
    this.onPick = deps.onPick || (() => {});
    this.sides = [];
    this.columns = [];
    this.kinds = {};
    this.axes = [];
    this.shown = [];
    this.only = false;
    this.root = this.el('section', 'tables-compare');
    const head = this.el('header', 'tables-compare__head');
    this.titleEl = this.el('span', 'tables-box__name', '');
    this.axisPick = new Pick(this.doc, 'Rows by', (picked) => { this.axes = picked; this.picked(); });
    this.valuePick = new Pick(this.doc, 'Values', (picked) => { this.shown = picked; this.picked(); });
    const only = this.el('label', 'tables-compare__only');
    this.onlyBox = this.el('input');
    this.onlyBox.type = 'checkbox';
    this.onlyBox.addEventListener('change', () => { this.only = this.onlyBox.checked; this.picked(); });
    only.append(this.onlyBox, this.el('span', '', 'Differs only'));
    this.countEl = this.el('span', 'tables-box__count', '');
    head.append(this.titleEl, this.axisPick.root, this.valuePick.root, only, this.countEl);
    this.area = this.el('div', 'tables-compare__body');
    this.root.append(head, this.area);
    mount.replaceChildren(this.root);
  }

  el(tag, cls, text) { const n = this.doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

  picked() { this.onPick({ axes: this.axes, columns: this.shown, only: this.only }); this.draw(); }

  /** The data: the sides' rows, the columns there are, their kinds, and the picks (kept where the columns still are). */
  show({ title = '', sides, columns, kinds = {}, axes = this.axes, shown = this.shown, only = this.only }) {
    this.titleEl.textContent = title;
    this.sides = sides;
    this.columns = columns;
    this.kinds = kinds;
    this.axisPick.set(columns, axes);
    this.valuePick.set(columns, shown);
    this.axes = this.axisPick.picked;
    this.shown = this.valuePick.picked;
    this.only = Boolean(only);
    this.onlyBox.checked = this.only;
    this.draw();
  }

  draw() {
    const shown = this.shown.filter((c) => !this.axes.includes(c));
    if (!this.axes.length || !shown.length) {
      this.countEl.textContent = '';
      this.area.replaceChildren(this.el('p', 'meta tables-box__start', !this.axes.length ? 'Pick Rows by' : 'Pick Values'));
      return;
    }
    const lines = foldSides({ sides: this.sides, axes: this.axes, columns: shown, kinds: this.kinds });
    const differing = lines.filter((l) => l.differs.length || l.one).length;
    this.countEl.textContent = `${lines.length.toLocaleString('en-US')} rows · ${differing.toLocaleString('en-US')} differ`;
    const kept = this.only ? lines.filter((l) => l.differs.length || l.one) : lines;
    const table = this.el('table', 'sf-table sf-table--rows tables-compare__table');
    const head = this.el('thead');
    const top = this.el('tr');
    for (const a of this.axes) { const th = this.el('th', 'tables-compare__axis', a); th.rowSpan = 2; top.append(th); }
    for (const side of this.sides) {
      const th = this.el('th', 'tables-compare__side', SIDE_WORDS[side.sign] || String(side.sign));
      th.colSpan = shown.length;
      top.append(th);
    }
    const names = this.el('tr');
    for (const side of this.sides) for (const c of shown) names.append(this.el('th', side === this.sides[0] ? '' : 'tables-compare__first', c));
    head.append(top, names);
    const body = this.el('tbody');
    for (const line of kept) {
      const tr = this.el('tr', line.differs.length || line.one ? 'is-differs' : '');
      for (const v of line.axis) tr.append(this.el('td', 'tables-compare__axis', cellWords(v)));
      for (const side of this.sides) {
        const cells = line.cells[side.sign];
        shown.forEach((c, k) => {
          const cls = [k === 0 && side !== this.sides[0] ? 'tables-compare__first' : '', this.kinds[c] === 'number' ? 'is-num' : '',
            !cells ? 'is-missing' : line.differs.includes(c) ? 'is-differs' : ''].filter(Boolean).join(' ');
          tr.append(this.el('td', cls, cells ? cellWords(cells[c]) : MISSING));
        });
      }
      body.append(tr);
    }
    table.append(head, body);
    const wrap = this.el('div', 'tb-table__wrap');
    wrap.append(table);
    this.area.replaceChildren(wrap);
  }
}
