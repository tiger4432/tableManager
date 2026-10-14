// The sheet kind of the visual part (owner 10-13 «엑셀 스타일 부품» 3b97fcfb9 · 4554ee685 · «포맷팅 기능 필요»; lead 10-14 ㄱ):
// an A1 grid of cells, each { input, format } in the declaration's `cells`; one cell the key (`key`, its place on the
// grid), whose input is the root's start (`start.node`, «type("key")» - the report's handle, the node the root walks
// from). A cell shows its value as its format says; its input shows only while it is edited, in the cell or the formula
// bar. The values are the root's: every cell is a slot (slots below) the root reads on the key's row, a cell naming
// another (A1, B1:B9) in the order they name each other (readSlots); the key's colour and marking are the root's paint.
// A format is drawing alone - changing one computes nothing here.

import { numberOf, valueWords } from '../../walk/reach_table.js';
import { parseServerInstant } from '../../server_time.js';
import { timeText, isTimeRead } from '../slot.js';
import { entityOfId } from '../../rnd_board/api.js';
import { place, address, letters } from '../../expression.js';
import { setDisabledReason } from '../../disabled_reason.js';

export const SHEET_WORDS = Object.freeze({
  oneKey: 'one key per sheet',
  unknownFormat: 'unknown format',
  cycle: (ring) => `A cycle: ${ring.join(' → ')}`,
  key: 'Key',
  general: 'General',
  format: 'Format',
  noKey: (name) => `No key ${name} on this node`,
  pickOne: 'Pick one cell',
});

/** The formats a cell can say (a closed table): numbers and times as Excel spells them, a node by its name or keys. */
export const FORMATS = Object.freeze(['0', '0.00', '#,##0', '0.0%', '0.00E+00', 'yyyy-mm-dd', 'yyyy-mm-dd hh:mm', 'name', 'key']);
const KEY_FORMAT = /^key:(.+)$/;
export const knownFormat = (f) => !f || FORMATS.includes(f) || KEY_FORMAT.test(f);

// The grid grows to the last cell written and a margin past it (lead 10-14), never below a small sheet.
const MARGIN = { c: 2, r: 5 };
const LEAST = { c: 5, r: 10 };

/** x to d places - no «-0» for a small negative. */
function fixed(x, d) {
  const text = x.toFixed(d);
  return /^-[0.]+$/.test(text) ? text.slice(1) : text;
}
const grouped = (text) => text.replace(/^(-?)(\d+)/, (_, s, n) => s + n.replace(/\B(?=(\d{3})+(?!\d))/g, ','));
const pad = (n) => String(n).padStart(2, '0');

/**
 * A value as a format says it. `node` {label, keys} when the value is a node; `time` when it was read from a column the
 * walk declares datetime - with no format it is drawn as the grid draws a datetime cell (server_time localStamp).
 * @returns {{text: string, why?: string}}
 */
export function formatValue(value, format, node = null, time = false) {
  if (value === null || value === undefined || value === '') return { text: '' };
  const why = knownFormat(format) ? undefined : SHEET_WORDS.unknownFormat;
  const f = why ? null : format;
  const at = time && !f ? timeText(value) : null;
  if (at) return { text: at, why };
  if (node) {
    const keys = node.keys || {};
    const m = f && KEY_FORMAT.exec(f);
    if (m) return m[1] in keys ? { text: valueWords(keys[m[1]]) } : { text: node.label, why: SHEET_WORDS.noKey(m[1]) };
    if (f === 'key') return { text: Object.values(keys).map(valueWords).join(' · ') };
    return { text: node.label, why };
  }
  const x = numberOf(value);
  if (x !== null) {
    if (f === '0') return { text: fixed(x, 0) };
    if (f === '0.00') return { text: fixed(x, 2) };
    if (f === '#,##0') return { text: grouped(fixed(x, 0)) };
    if (f === '0.0%') return { text: `${fixed(x * 100, 1)}%` };
    if (f === '0.00E+00') {
      const [m, e] = (x === 0 ? 0 : x).toExponential(2).split('e');
      return { text: `${m}E${Number(e) < 0 ? '-' : '+'}${pad(Math.abs(Number(e)))}` };
    }
  }
  if (f === 'yyyy-mm-dd' || f === 'yyyy-mm-dd hh:mm') {
    const at = parseServerInstant(value);
    if (at) {
      const day = `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
      return { text: f === 'yyyy-mm-dd' ? day : `${day} ${pad(at.getHours())}:${pad(at.getMinutes())}` };
    }
  }
  return { text: valueWords(value), why };
}

const nodeOf = (id, label) => {
  const e = entityOfId(id);
  return e ? { label: label || Object.values(e.keys).map(valueWords).join(' · '), keys: e.keys } : null;
};

/** A cell as the sheet shows it: its value from the root's read (a formula), the key's node, or its own input. */
function cellOf(at, spec, decl, row, ctx) {
  const isKey = decl.key === at;
  const start = (ctx && ctx.start) || null;
  // The key's input is the root's start - one text, not a copy in `cells`.
  const raw = isKey ? (start && start.text ? `=${start.text}` : '') : spec.input;
  const input = raw === undefined || raw === null ? '' : String(raw);
  const out = { at, input, format: spec.format || null, isKey, text: '', why: undefined, error: null, num: false, color: null, marked: false };
  let value = null;
  let node = null;
  let time = false;
  if (out.isKey) {
    if (start && start.why) { out.error = '#NAME?'; out.why = start.why; out.text = out.error; return out; }
    if (row) {
      value = row.id;
      node = nodeOf(row.id, row.label) || { label: row.label || row.id, keys: {} };
      const paint = ctx && ctx.paint ? ctx.paint([row.id]) : null;
      if (paint) { out.color = paint.color; out.marked = paint.marked; }
    }
  } else if (input.startsWith('=')) {
    const read = row && row.reads ? row.reads[at] : null;
    // a slot of images (the root's): the cell's pictures - a line too small to show one, its mark and the preview
    const images = ctx && ctx.images ? ctx.images(at, read) : null;
    if (images) { out.images = images; return out; }
    if (read && read.state === 'one') value = read.value;
    if (read && read.types) time = isTimeRead(read);
    else if (read && read.state === 'cycle') { out.error = '#CYCLE'; out.why = SHEET_WORDS.cycle(read.ring || []); }
    // a refusal - the calculator's, or the root's (units.js refuseMany: #MANY and why) - drawn as it says
    else if (read && read.why) { out.error = read.error || (/^No (value|function) named/.test(read.why) ? '#NAME?' : '#ERROR'); out.why = read.why; }
    if (value !== null && typeof value === 'string') node = nodeOf(value, read && read.label);
  } else if (input.trim() !== '') {
    value = numberOf(input) !== null ? numberOf(input) : input;
  }
  if (out.error) { out.text = out.error; return out; }
  const said = formatValue(value, out.format, node, time);
  out.text = said.text;
  out.why = said.why;
  out.num = !node && numberOf(value) !== null;
  return out;
}

/**
 * @param {Array<{id, label, reads: object}>} rows  the key's row (the root walks from the key) - the first is the sheet's
 * @param {{declaration?: object}} ctx  `cells` {A1: {input, format}} · `key` the key cell's address
 */
export function sheetModel(rows, ctx) {
  const decl = (ctx && ctx.declaration) || {};
  const cells = decl.cells || {};
  const row = (rows || [])[0] || null;
  const used = Object.keys(cells).map(place).filter(Boolean);
  if (place(decl.key)) used.push(place(decl.key));
  const cols = Math.max(LEAST.c, ...used.map((p) => p.c + MARGIN.c));
  const lines = Math.max(LEAST.r, ...used.map((p) => p.r + MARGIN.r));
  const grid = [];
  for (let r = 1; r <= lines; r += 1) {
    const line = [];
    for (let c = 1; c <= cols; c += 1) { const at = address(c, r); line.push(cellOf(at, cells[at] || {}, decl, row, ctx)); }
    grid.push(line);
  }
  return { cols, rows: lines, grid, key: decl.key || null, cells, keyId: row ? row.id : null, start: (ctx && ctx.start) || null };
}

/** The declaration's cells with `at` set - an empty input with no format leaves the cell out. */
export function withCell(cells, at, patch) {
  const next = { ...(cells || {}) };
  const spec = { ...(next[at] || {}), ...patch };
  if (!spec.format) delete spec.format;
  if (spec.input === undefined || spec.input === null || String(spec.input) === '') delete spec.input;
  if (Object.keys(spec).length) next[at] = spec; else delete next[at];
  return next;
}

/** The key placed or taken (lead 10-13 3b97fcfb9: one a sheet): a patch, or the refusal. Placed on a formula cell its
 *  text becomes the root's start (`start.node`, its row its type); taken back, the start goes back into the cell. */
export function keyPatch(decl, at) {
  const cells = decl.cells || {};
  const text = decl.start && decl.start.node;
  if (decl.key === at) return { patch: { key: null, start: null, cells: withCell(cells, at, { input: text ? `=${text}` : '' }) } };
  if (decl.key) return { refused: SHEET_WORDS.oneKey };
  const input = String((cells[at] || {}).input || '');
  if (!input.startsWith('=')) return { patch: { key: at } };
  return { patch: { key: at, start: { node: input.slice(1) }, row: null, cells: withCell(cells, at, { input: '' }) } };
}

/** A key cell's input written: the root's start (empty - no start). */
export const startPatch = (input) => {
  const text = String(input || '').replace(/^=/, '').trim();
  return { start: text ? { node: text } : null, row: null };
};

/** Draw a model: the formula bar (the cell picked, its input, its format, Key) and the grid. */
export function render(body, model, ctx) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  // What is picked lives on this part's own body - redrawn after a declaration, the pick stays.
  const own = body.sheetPick || (body.sheetPick = { sel: ['A1'], anchor: 'A1', say: '' });
  const byAt = new Map(model.grid.flat().map((c) => [c.at, c]));
  const first = () => byAt.get(own.sel[0]) || { at: own.sel[0], input: '', format: null };
  const declare = (patch) => { own.say = ''; ctx.declare(patch); };
  const commit = (at, input) => declare(at === model.key ? startPatch(input) : { cells: withCell(model.cells, at, { input }) });
  const redraw = () => render(body, model, ctx);

  const bar = el('div', 'sf-sheet__bar');
  const name = el('span', 'sf-sheet__name', own.sel.length > 1 ? `${own.sel.length} cells` : own.sel[0]);
  const input = el('input', 'sf-sheet__input');
  input.type = 'text';
  input.setAttribute('aria-label', 'Cell input');
  input.value = own.sel.length === 1 ? first().input : '';
  setDisabledReason(input, own.sel.length === 1 ? '' : SHEET_WORDS.pickOne);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); commit(own.sel[0], input.value); }
    if (e.key === 'Escape') input.value = first().input;
  });
  const fmt = el('select', 'sf-sheet__fmt');
  fmt.setAttribute('aria-label', SHEET_WORDS.format);
  const shared = [...new Set(own.sel.map((at) => (byAt.get(at) || {}).format || ''))];
  const now = shared.length === 1 ? shared[0] : '';
  for (const f of ['', ...FORMATS, ...(now && !FORMATS.includes(now) ? [now] : [])]) {
    const o = el('option', '', f || SHEET_WORDS.general);
    o.value = f;
    fmt.append(o);
  }
  fmt.value = now;
  const typed = el('input', 'sf-sheet__fmtx');
  typed.type = 'text';
  typed.placeholder = 'key:lot';
  typed.setAttribute('aria-label', 'Format, typed');
  const setFormat = (format) => {
    if (format && !knownFormat(format)) { own.say = SHEET_WORDS.unknownFormat; redraw(); return; }
    let cells = model.cells;
    for (const at of own.sel) cells = withCell(cells, at, { format: format || null });
    declare({ cells });
  };
  fmt.addEventListener('change', () => setFormat(fmt.value));
  typed.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); setFormat(typed.value.trim()); } });
  const key = el('button', 'sf-btn sf-sheet__key', SHEET_WORDS.key);
  key.type = 'button';
  setDisabledReason(key, own.sel.length === 1 ? '' : SHEET_WORDS.pickOne);
  key.addEventListener('click', () => {
    const got = keyPatch({ key: model.key, cells: model.cells, start: model.start && { node: model.start.text } }, own.sel[0]);
    if (got.refused) { own.say = got.refused; redraw(); return; }
    declare(got.patch);
  });
  bar.append(name, input, el('span', 'sf-sheet__lab', SHEET_WORDS.format), fmt, typed, key);
  const say = el('div', 'sf-sheet__say', own.say || (own.sel.length === 1 ? first().why || '' : ''));

  const wrap = el('div', 'sf-sheet__wrap');
  const table = el('table', 'sf-table sf-sheet__grid');
  const head = el('tr');
  head.append(el('th', 'sf-table__corner'));
  for (let c = 1; c <= model.cols; c += 1) head.append(el('th', 'sf-table__col', letters(c)));
  table.append(head);
  const pick = (at, event) => {
    if (event && event.shiftKey && own.anchor) {
      const a = place(own.anchor); const b = place(at);
      own.sel = [];
      for (let r = Math.min(a.r, b.r); r <= Math.max(a.r, b.r); r += 1) for (let c = Math.min(a.c, b.c); c <= Math.max(a.c, b.c); c += 1) own.sel.push(address(c, r));
    } else if (event && (event.ctrlKey || event.metaKey)) {
      own.sel = own.sel.includes(at) ? own.sel.filter((x) => x !== at) : [...own.sel, at];
      if (!own.sel.length) own.sel = [at];
      own.anchor = at;
    } else { own.sel = [at]; own.anchor = at; }
    own.say = '';
    redraw();
  };
  model.grid.forEach((line, i) => {
    const tr = el('tr');
    tr.append(el('th', 'sf-table__row', String(i + 1)));
    for (const cell of line) {
      const cls = [cell.num ? 'is-num' : '', own.sel.includes(cell.at) ? 'is-sel' : '', cell.isKey ? 'is-key' : '', cell.error ? 'is-err' : '',
        cell.marked ? 'is-marked' : ''].filter(Boolean).join(' ');
      const td = el('td', cls, cell.text);
      if (cell.images && ctx.thumb) { const holder = el('span', 'sf-thumb__at'); td.append(holder); ctx.thumb(holder, cell.images, 0); }
      td.setAttribute('data-at', cell.at);
      if (cell.color) { td.setAttribute('data-color', cell.color); if (td.style && td.style.setProperty) td.style.setProperty('--sf-sheet-key', cell.color); }
      if (cell.why) td.title = cell.why;
      td.addEventListener('click', (event) => {
        if (cell.isKey && model.keyId && ctx.mark) ctx.mark([model.keyId], event);
        pick(cell.at, event);
      });
      // Edited in place: its input, Enter or leaving keeps it, Escape drops it.
      td.addEventListener('dblclick', () => {
        own.sel = [cell.at]; own.anchor = cell.at;
        const box = el('input', 'sf-sheet__edit');
        box.type = 'text';
        box.value = cell.input;
        let done = false;
        const finish = (keep) => { if (done) return; done = true; if (keep && box.value !== cell.input) commit(cell.at, box.value); else redraw(); };
        box.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') { e.preventDefault(); finish(true); }
          if (e.key === 'Escape') finish(false);
        });
        box.addEventListener('blur', () => finish(true));
        td.replaceChildren(box);
        if (box.focus) box.focus();
      });
      tr.append(td);
    }
    table.append(tr);
  });
  wrap.append(table);
  // the formula bar in the root's top tray (the frame standard 5, full width); the grid in the area
  const top = ctx.tray ? ctx.tray('top') : null;
  const sheet = el('div', top ? 'sf-sheet' : 'sf-sheet sf-sheet--bar');
  if (top) {
    if (top.sheetBar && top.sheetBar.parentNode) top.sheetBar.parentNode.removeChild(top.sheetBar);
    top.sheetBar = bar;
    top.append(bar);
    sheet.append(say, wrap);
  } else sheet.append(bar, say, wrap);
  body.replaceChildren(sheet);
  return { resize: () => {}, dispose: () => {} };
}

/** The title when the declaration names none. */
export const title = () => 'Sheet';

/** The sheet's slots - every cell, the root reads them on the key's row: the key the row itself, a formula its
 *  expression (the input after «=»), a value as written (a number its number). */
export const slots = (encode, declaration) => {
  const d = declaration || {};
  const out = Object.entries(d.cells || {}).filter(([at, spec]) => at !== d.key && spec && String(spec.input || '').trim() !== '')
    .map(([at, spec]) => {
      const input = String(spec.input);
      const slot = input.startsWith('=') ? { expr: input.slice(1) } : { constant: numberOf(input) !== null ? numberOf(input) : input };
      return { key: at, label: at, slot };
    });
  return d.key ? [{ key: d.key, label: d.key, slot: { self: true } }, ...out] : out;
};

/** The add window's picture of it: a grid. */
export const icon = { tone: 'cat-2', paths: [['M3 3h18v18H3z', 0.25], ['M3 8h18v1H3zM3 13h18v1H3zM3 18h18v1H3zM9 3h1v18H9zM15 3h1v18h-1z', 1]] };

// cells - a kind of cells: its slots name each other (A1, B1:B9) and it draws before its key is written (the root's).
// a sheet is one table of cells: no Top/Bottom N of its rows, no panels (lead 10-14)
export const kind = { name: 'sheet', label: 'Sheet', slots, title, model: sheetModel, render, icon, cells: true, without: ['show', 'panel'] };
