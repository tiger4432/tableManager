// FORMULA POPOVER — a column's formula on its header (owner 10-28 option A), scored.
//
// The subject is imported whole (owner 2026-09-02: 잘라쓰기 하니스 절대 금지). What is scored:
//   A  the requests: read · preview · save (the read's base, no preview flag) · remove (empty formula)
//   B  opening: an existing formula is filled in and previewed, Remove offered; none - empty, nothing sent
//   C  the preview: the recompute line (counted · counting · failed), the sample table, the server's sentence; Apply
//      only for the text that was previewed; an answer to an older text is dropped
//   D  a refusal stands word for word and Apply stays off; Apply and Remove send once, toast, and close
//   E  Esc and a press outside close it, a press inside does not; a column chip lands at the caret; two instances
//   F  the header's fx mark opens the formula and its press does not reach the header (no sort, no drag)
//   G  as one types (owner's mockup 11-07), through the popover's formula field (formula_input.js, scored on its own by
//      formula_input_harness.mjs): names and columns offered, ↑↓ Enter Tab take a row, Esc closes the list alone, Enter
//      with no list previews, the arguments under the server's refusal
// Run: node client2/tests/formula_popover_harness.mjs
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/formula_popover.js';
import { FORMULA_MARK } from '../src/formula_input.js';

const SRC_PATH = fileURLToPath(new URL('../src/formula_popover.js', import.meta.url));
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

// ── a DOM just big enough: built, clicked, events bubble and can be stopped ─────────────
function makeDoc() {
  const docListeners = {};
  const doc = {
    addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
    removeEventListener(type, fn) { docListeners[type] = (docListeners[type] || []).filter((f) => f !== fn); },
    fire(type, init = {}) { (docListeners[type] || []).slice().forEach((fn) => fn(init)); },
    listening(type) { return (docListeners[type] || []).length; },
    createElement(tag) {
      const el = {
        tagName: String(tag).toUpperCase(), className: '', children: [], parentNode: null, hidden: false,
        attrs: {}, listeners: {}, _text: '', value: '', disabled: false, type: '', placeholder: '', title: '',
        selectionStart: null, selectionEnd: null, focused: false,
        get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
        set textContent(v) { this._text = String(v); this.children = []; },
        appendChild(c) { if (c.parentNode) c.remove(); c.parentNode = this; this.children.push(c); return c; },
        remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((x) => x !== this); this.parentNode = null; },
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
        addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
        focus() { this.focused = true; },
        setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b; },
        // bubbles from here up its parents until a listener stops it
        dispatch(type, init = {}) {
          const event = { type, target: this, key: init.key, stopped: false, prevented: false,
            stopPropagation() { this.stopped = true; }, preventDefault() { this.prevented = true; } };
          for (let node = this; node && !event.stopped; node = node.parentNode) {
            (node.listeners[type] || []).slice().forEach((fn) => fn(event));
          }
          return event;
        },
        fire(type, init) { return this.dispatch(type, init); },
        click() { return this.disabled ? null : this.dispatch('click'); },
      };
      el.ownerDocument = doc;
      return el;
    },
  };
  return doc;
}
const has = (el, cls) => String(el.className).split(' ').includes(cls);
const find = (el, cls) => {
  if (!el) return null;
  if (has(el, cls)) return el;
  for (const c of el.children) { const hit = find(c, cls); if (hit) return hit; }
  return null;
};
const all = (el, tag, out = []) => { if (el.tagName === tag) out.push(el); el.children.forEach((c) => all(c, tag, out)); return out; };
const tick = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

// a clock the harness runs by hand
function makeClock() {
  const pending = new Map();
  let n = 0;
  return { set: (fn) => { n += 1; pending.set(n, fn); return n; }, clear: (h) => pending.delete(h),
    run() { const fns = [...pending.values()]; pending.clear(); fns.forEach((fn) => fn()); }, get size() { return pending.size; } };
}

const READ = { table: 'fx', base: 'B1', formulas: [{ column: 'c', formula: '=[a]+[b]*3', rule: 'formula fx.c', enabled: true }] };
const PREVIEW = {
  rule: 'formula fx.c', says: "Saving replaces this column's values row by row.",
  count: { total: 1234, capped: false, counted_at: '2026-10-29T10:20:31Z', count_seconds: 0.2, counting: false, failed: null },
  sample: [
    { keys: { lot_id: 'L-1001' }, reads: { a: 2, b: 1 }, now: 4, becomes: 5 },
    { keys: { lot_id: 'L-1002' }, reads: { a: 3, b: 2 }, now: 9, becomes: 9 },
    { keys: { lot_id: 'L-1003' }, reads: { a: 1.5, b: null }, now: null, becomes: null },
  ],
};

/** A send that answers by request: the read, a preview, a save, a removal - each overridable; every request kept. */
function makeSend(over = {}) {
  const sent = [];
  const send = async (req, opts) => {
    sent.push({ ...req, signal: opts && opts.signal ? 'signal' : null });
    const kind = req.method === 'GET' ? 'read' : req.body.preview ? 'preview' : req.body.formula === '' ? 'remove' : 'save';
    const answer = kind in over ? over[kind] : {
      read: { ok: true, body: READ }, preview: { ok: true, body: PREVIEW },
      save: { ok: true, body: { rule: 'formula fx.c', run_id: 'r-2041', base: 'B2' } },
      remove: { ok: true, body: { rule: 'formula fx.c', run_id: 'r-2042', base: 'B3' } },
    }[kind];
    return typeof answer === 'function' ? answer(req) : answer;
  };
  return { send, sent };
}

function mount(M, over = {}, extra = {}) {
  const doc = makeDoc();
  const host = doc.createElement('div');
  const clock = makeClock();
  const { send, sent } = makeSend(over);
  const said = [];
  const saved = [];
  const pop = new M.FormulaPopover(host, { doc, send, clock, say: (t, type, o) => said.push({ t, type, o }),
    onSaved: (x) => saved.push(x), openQueue: () => {}, ...extra });
  return { doc, host, clock, sent, said, saved, pop };
}
const posts = (sent) => sent.filter((r) => r.method === 'POST');

const X = BASELINE;

console.log('\n── A. THE REQUESTS ─────────────────────────────────────────────────');
{
  ok('A1 the read names the table', X.formulaRequest('read', { table: 'f x' }).path === '/admin/chain/formula?table=f%20x');
  const p = X.formulaRequest('preview', { table: 'fx', column: 'c', formula: '=[a]' });
  ok('A2 a preview says preview and carries no base', p.method === 'POST' && p.body.preview === true && !('base' in p.body), p);
  const s = X.formulaRequest('save', { table: 'fx', column: 'c', formula: '=[a]', base: 'B1' });
  ok('A3 a save carries the read\'s base and no preview flag', s.body.base === 'B1' && !('preview' in s.body)
    && s.body.formula === '=[a]', s);
  const r = X.formulaRequest('remove', { table: 'fx', column: 'c', formula: '=[a]', base: 'B1' });
  ok('A4 a removal sends an empty formula with the base', r.body.formula === '' && r.body.base === 'B1', r);
  ok('A5 the column\'s entry is found in the read', X.formulaOf(READ, 'c').formula === '=[a]+[b]*3'
    && X.formulaOf(READ, 'a') === null && X.formulaOf(null, 'c') === null);
}

console.log('\n── B. OPENING ──────────────────────────────────────────────────────');
{
  const m = mount(X);
  await m.pop.open({ table: 'fx', column: 'c', columns: ['lot_id', 'a', 'b', 'c'] });
  await tick();
  const panel = m.pop.panel;
  ok('B1 the popover names its column', find(panel, 'formula-pop__title').textContent === 'Formula · fx.c');
  ok('B2 an existing formula is filled in', find(panel, 'formula-pop__input').value === '=[a]+[b]*3');
  ok('B3 ...Remove is offered', find(panel, 'formula-pop__remove').hidden === false);
  ok('B4 ...and it is previewed at once', posts(m.sent).length === 1 && posts(m.sent)[0].body.formula === '=[a]+[b]*3', m.sent);
  const chips = all(panel, 'BUTTON').filter((b) => has(b, 'formula-pop__chip')).map((b) => b.textContent);
  ok('B5 the chips offer the other columns, not its own', JSON.stringify(chips) === '["[lot_id]","[a]","[b]"]', chips);

  const e = mount(X, { read: { ok: true, body: { table: 'fx', base: 'B1', formulas: [] } } });
  await e.pop.open({ table: 'fx', column: 'd', columns: ['a', 'b', 'd'] });
  await tick();
  ok('B6 a column without one opens empty, sends no preview, offers no Remove',
    find(e.pop.panel, 'formula-pop__input').value === '' && posts(e.sent).length === 0
      && find(e.pop.panel, 'formula-pop__remove').hidden === true);
  ok('B7 ...and Apply is off, saying why', find(e.pop.panel, 'formula-pop__apply').disabled === true
    && find(e.pop.panel, 'formula-pop__apply').getAttribute('title') === X.NEEDS_PREVIEW);

  const r = mount(X, { read: { ok: false, error: 'Admin token rejected (HTTP 401)' } });
  await r.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  await tick();
  ok('B8 a refused read says why in the popover', find(r.pop.panel, 'formula-input__why').textContent === 'Admin token rejected (HTTP 401)'
    && find(r.pop.panel, 'formula-input__why').hidden === false);
}

console.log('\n── C. THE PREVIEW ──────────────────────────────────────────────────');
{
  const line = X.recomputeLine(PREVIEW.count);
  ok('C1 the count says the rows saving recomputes', line.text === '1,234 rows will be recomputed', line);
  ok('C2 ...and when it was counted', /^counted \d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/.test(line.at), line.at);
  ok('C3 a count still counting says so, not a number', X.recomputeLine({ total: null, counting: true }).text === 'Counting rows…');
  ok('C4 a failed count says it failed and why', X.recomputeLine({ total: null, failed: { reason: 'timeout' } }).text === 'Count failed (timeout)');
  ok('C5 a capped count keeps its +', X.recomputeLine({ total: 10000, capped: true }).text === '10,000+ rows will be recomputed'
    && X.recomputeLine({ total: 10000, capped: true }).at === '');
  const t = X.previewTable(PREVIEW.sample);
  ok('C6 the table: the keys, the columns read, now, becomes', JSON.stringify(t.head) === '["lot_id","a","b","now","becomes"]', t.head);
  ok('C7 a blank is drawn as a blank, not as 0', JSON.stringify(t.rows[2].cells) === '["L-1003","1.5","—","—","—"]', t.rows[2]);
  ok('C8 a row whose cell changes is marked, one that stays is not', t.rows[0].changed === true && t.rows[1].changed === false);
  ok('C8b the numbers stand right, the row keys left', JSON.stringify(t.numeric) === '[false,true,true,true,true]', t.numeric);
  const named = X.previewTable([{ keys: { k: 'x' }, reads: { a: 'lot' }, now: 1, becomes: 2 }]);
  ok('C8c a column read as words stands left', JSON.stringify(named.numeric) === '[false,false,true,true]', named.numeric);

  const m = mount(X);
  await m.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b'] });
  await tick();
  const out = find(m.pop.panel, 'formula-pop__preview');
  ok('C9 the preview is drawn: the line, the rows, the server\'s sentence', out.hidden === false
    && find(out, 'formula-pop__count').textContent.startsWith('1,234 rows will be recomputed (counted ')
    && all(out, 'TR').length === 4 && find(out, 'formula-pop__says').textContent === PREVIEW.says);
  ok('C10 the changed cell is marked in the drawing', find(out, 'is-changed') !== null
    && find(out, 'is-changed').textContent === '5');
  const apply = find(m.pop.panel, 'formula-pop__apply');
  ok('C11 Apply is on for the previewed text', apply.disabled === false);
  const input = find(m.pop.panel, 'formula-pop__input');
  input.value = '=[a]*2';
  input.fire('input');
  ok('C12 typing turns Apply off at once', apply.disabled === true);
  ok('C13 ...and asks nothing until typing rests', posts(m.sent).length === 1 && m.clock.size === 1);
  m.clock.run();
  await tick();
  ok('C14 once it rests the new text is previewed', posts(m.sent).length === 2 && posts(m.sent)[1].body.formula === '=[a]*2'
    && posts(m.sent)[1].signal === 'signal', posts(m.sent));
  ok('C15 ...and Apply comes back for it', apply.disabled === false);

  // an older preview answering after a newer one is dropped
  let release;
  const slow = new Promise((r) => { release = r; });
  let n = 0;
  const race = mount(X, { preview: (req) => { n += 1; return n === 1 ? slow : { ok: true, body: { ...PREVIEW, says: `for ${req.body.formula}` } }; },
    read: { ok: true, body: { table: 'fx', base: 'B1', formulas: [] } } });
  await race.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  const rin = find(race.pop.panel, 'formula-pop__input');
  rin.value = '=[a]';
  rin.fire('keydown', { key: 'Enter' });
  rin.value = '=[a]+1';
  rin.fire('keydown', { key: 'Enter' });
  await tick();
  release({ ok: true, body: { ...PREVIEW, says: 'for =[a]' } });
  await tick();
  ok('C16 an answer to an older text does not overwrite the newer one', find(race.pop.panel, 'formula-pop__says').textContent === 'for =[a]+1',
    find(race.pop.panel, 'formula-pop__says').textContent);
}

console.log('\n── D. REFUSAL · APPLY · REMOVE ──────────────────────────────────────');
{
  const loop = "fx: b -> c -> b - these rules wake each other and never settle";
  const m = mount(X, { preview: { ok: false, error: "'z' is not a column of fx" } });
  await m.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  await tick();
  const why = find(m.pop.panel, 'formula-input__why');
  ok('D1 a refused preview says the server\'s sentence word for word', why.textContent === "'z' is not a column of fx" && why.hidden === false);
  ok('D2 ...the field is marked invalid, the preview hidden, Apply off',
    find(m.pop.panel, 'formula-pop__input').getAttribute('aria-invalid') === 'true'
      && find(m.pop.panel, 'formula-pop__preview').hidden === true && find(m.pop.panel, 'formula-pop__apply').disabled === true);
  find(m.pop.panel, 'formula-pop__apply').disabled = false;
  find(m.pop.panel, 'formula-pop__apply').click();
  await tick();
  ok('D3 Apply sends nothing for a text that did not preview', posts(m.sent).every((r) => r.body.preview === true), posts(m.sent));

  const s = mount(X);
  await s.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b'] });
  await tick();
  find(s.pop.panel, 'formula-pop__apply').click();
  await tick();
  const save = posts(s.sent).find((r) => !r.body.preview);
  ok('D4 Apply sends the formula with the read\'s base', save && save.body.formula === '=[a]+[b]*3' && save.body.base === 'B1'
    && !('preview' in save.body), save);
  ok('D5 ...the toast says what the server did, with Open queue',
    s.said.length === 1 && s.said[0].t === 'Formula saved · formula fx.c · recompute queued · run r-2041'
      && s.said[0].o.action && s.said[0].o.action.label === 'Open queue', s.said);
  ok('D6 ...the page is told to read the formulas again, and the popover closes',
    s.saved.length === 1 && s.saved[0].column === 'c' && s.pop.isOpen === false && s.host.children.length === 0);

  const refused = mount(X, { save: { ok: false, error: loop } });
  await refused.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b'] });
  await tick();
  find(refused.pop.panel, 'formula-pop__apply').click();
  await tick();
  ok('D7 a refused save stays open with the server\'s sentence, nothing toasted',
    refused.pop.isOpen && find(refused.pop.panel, 'formula-input__why').textContent === loop && refused.said.length === 0
      && refused.saved.length === 0);

  const rm = mount(X);
  await rm.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b'] });
  await tick();
  find(rm.pop.panel, 'formula-pop__remove').click();
  await tick();
  const removal = posts(rm.sent).find((r) => !r.body.preview);
  ok('D8 Remove sends an empty formula with the base', removal && removal.body.formula === '' && removal.body.base === 'B1', removal);
  ok('D9 ...and its toast says the column is resolved again', rm.said[0] && rm.said[0].t === 'Formula removed · formula fx.c · column resolved again · run r-2042'
    && rm.saved.length === 1 && !rm.pop.isOpen, rm.said);
}

console.log('\n── E. CLOSING · CHIPS · TWO INSTANCES ───────────────────────────────');
{
  const m = mount(X);
  await m.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b'] });
  await tick();
  m.doc.fire('mousedown', { target: find(m.pop.panel, 'formula-pop__input') });
  ok('E1 a press inside does not close it', m.pop.isOpen);
  m.doc.fire('mousedown', { target: m.doc.createElement('div') });
  ok('E2 a press outside closes it and lets go of the page', !m.pop.isOpen && m.doc.listening('mousedown') === 0
    && m.doc.listening('keydown') === 0);
  await m.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b'] });
  await tick();
  m.doc.fire('keydown', { key: 'Escape' });
  ok('E3 Esc closes it', !m.pop.isOpen);
  find(m.host, 'formula-pop__cancel');
  await m.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b'] });
  await tick();
  find(m.pop.panel, 'formula-pop__cancel').click();
  ok('E4 Cancel closes it and sends nothing more', !m.pop.isOpen && posts(m.sent).every((r) => r.body.preview === true));

  const c = mount(X, { read: { ok: true, body: { table: 'fx', base: 'B1', formulas: [] } } });
  await c.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b'] });
  const input = find(c.pop.panel, 'formula-pop__input');
  input.value = '=[a]+*3';
  input.setSelectionRange(5, 5);
  const chipB = all(c.pop.panel, 'BUTTON').find((b) => b.textContent === '[b]');
  chipB.click();
  ok('E5 a chip lands at the caret, the caret after it', input.value === '=[a]+[b]*3' && input.selectionStart === 8, [input.value, input.selectionStart]);
  ok('E6 ...and is a typed change: Apply off, its preview waits for the rest', find(c.pop.panel, 'formula-pop__apply').disabled === true
    && c.clock.size === 1);

  const doc = makeDoc();
  const a = mount(X);
  const b = mount(X);
  await a.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  await b.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  await tick();
  a.pop.close();
  ok('E7 two instances: closing one leaves the other open', !a.pop.isOpen && b.pop.isOpen && b.host.children.length === 1);
  void doc;
}

console.log('\n── F. THE HEADER\'S fx MARK ─────────────────────────────────────────');
{
  const doc = makeDoc();
  const label = doc.createElement('div');
  const sorted = [];
  label.addEventListener('click', () => sorted.push('sort'));
  label.addEventListener('mousedown', () => sorted.push('drag'));
  const opened = [];
  const head = new X.FormulaHeader();
  head.init({ doc, displayName: 'C', formula: '=[a]+[b]*3', open: (anchor) => opened.push(anchor) });
  label.appendChild(head.getGui());
  const mark = find(head.getGui(), 'formula-mark');
  ok('F1 the header says its name and carries the mark', head.getGui().textContent === 'Cfx' && mark.title === '=[a]+[b]*3');
  mark.dispatch('mousedown');
  const clicked = mark.click();
  ok('F2 pressing the mark opens the formula under the mark', opened.length === 1 && opened[0] === mark);
  ok('F3 ...and the press reaches the header neither as a sort nor as a drag', sorted.length === 0 && clicked.prevented, sorted);
  head.getGui().dispatch('click');
  ok('F4 a press on the name still sorts', sorted.length === 1 && sorted[0] === 'sort');
  head.refresh({ doc, displayName: 'C2', formula: '=[a]', open: (anchor) => opened.push(anchor) });
  ok('F5 a refresh keeps the mark and says the new formula', head.getGui().textContent === 'C2fx' && mark.title === '=[a]'
    && find(head.getGui(), 'formula-mark') === mark);
  ok('F6 the header\'s mark is the formula field\'s one word (formula_input.FORMULA_MARK)', mark.textContent === FORMULA_MARK,
    mark.textContent);
}

console.log('\n── G. AS ONE TYPES: NAMES, COLUMNS, ARGUMENTS ─────────────────────');
{
  const m = mount(X);
  await m.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b', 'c'] });
  await tick();
  const input = find(m.pop.panel, 'formula-pop__input');
  const list = find(m.pop.panel, 'formula-input__complete');
  const sign = find(m.pop.panel, 'formula-input__signature');
  const typeIn = (text) => { input.value = text; input.setSelectionRange(text.length, text.length); input.fire('input'); };
  const lit = () => list.children.findIndex((r) => r.getAttribute('aria-selected') === 'true');
  typeIn('=Da');
  ok('G6 typing «=Da» opens the list under the formula, the first row lit', !list.hidden && list.children.length > 2
    && lit() === 0 && list.getAttribute('role') === 'listbox' && input.getAttribute('aria-expanded') === 'true', [list.hidden, lit()]);
  input.fire('keydown', { key: 'ArrowDown' });
  const sentBefore = m.sent.length;
  const enter = input.fire('keydown', { key: 'Enter' });
  await tick();
  ok('G7 ↓ then Enter takes the lit row as «DatePart(» - no preview asked by that Enter, the list closed',
    input.value === '=DatePart(' && input.selectionStart === 10 && enter.prevented && list.hidden
    && m.sent.length === sentBefore, [input.value, m.sent.length - sentBefore]);
  ok('G8 ...and its arguments stand under it, the first in bold', !sign.hidden && sign.textContent === 'DatePart(part, value)'
    && all(sign, 'B').map((b) => b.textContent).join() === 'part', sign.textContent);
  typeIn('=DatePart("year", ');
  ok('G9 past a comma the second argument is the bold one', all(sign, 'B').map((b) => b.textContent).join() === 'value');
  typeIn('=Sum([a], [b], ');
  ok('G10 a fold of more columns: past its last named argument «...» is bold',
    sign.textContent === 'Sum(column, ...)' && all(sign, 'B').map((b) => b.textContent).join() === '...', sign.textContent);
  typeIn('=Sum([');
  ok('G11 «[» offers the columns the formula may read (its own column not among them)',
    !list.hidden && list.children.map((r) => r.textContent).join() === '[a],[b]', list.children.map((r) => r.textContent));
  typeIn('=Sum([A');
  ok('G11b ...each as it goes in, «[» then what was typed in bold then the rest «]»', list.children.length === 1
    && list.children[0].textContent === '[a]' && all(list.children[0], 'B').map((b) => b.textContent).join() === 'a'
    && list.children[0].textContent.startsWith('['), list.children.map((r) => r.textContent));
  typeIn('=Sum([');
  const tab = input.fire('keydown', { key: 'Tab' });
  ok('G12 Tab takes the lit column as «a]»', input.value === '=Sum([a]' && tab.prevented && list.hidden, input.value);
  typeIn('=Su');
  const esc = input.fire('keydown', { key: 'Escape' });
  ok('G13 Esc closes the list alone - the popover stays open (the key does not reach its watch)',
    list.hidden && esc.stopped && m.pop.isOpen && input.value === '=Su');
  typeIn('=Ro');
  list.children[0].dispatch('mousedown');
  ok('G14 a press on a row takes it', input.value === '=Round(' && list.hidden, input.value);
  const typedEnter = mount(X);
  await typedEnter.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  await tick();
  const tin = find(typedEnter.pop.panel, 'formula-pop__input');
  tin.value = '=[a]+1';
  tin.setSelectionRange(6, 6);
  tin.fire('input');
  tin.fire('keydown', { key: 'Enter' });
  await tick();
  ok('G15 with no list open, Enter still previews', posts(typedEnter.sent).some((r) => r.body.preview === true));

  // The arguments line hangs under the block of the field and its refusal (owner 11-07): after the refusal when one
  // stands, both read; with none, right under the field.
  const order = (p) => find(p.pop.panel, 'formula-input').children.filter((n) => !n.hidden).map((n) => n.className);
  const refused = mount(X, { preview: { ok: false, error: 'The expression ends too soon' } });
  await refused.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  await tick();
  const rin2 = find(refused.pop.panel, 'formula-pop__input');
  rin2.value = '=DatePart(';
  rin2.setSelectionRange(10, 10);
  rin2.fire('input');
  refused.clock.run();
  await tick();
  const clean = mount(X);
  await clean.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  await tick();
  const cin = find(clean.pop.panel, 'formula-pop__input');
  cin.value = '=DatePart(';
  cin.setSelectionRange(10, 10);
  cin.fire('input');
  ok('G16 the arguments line comes after the refusal, both shown; with no refusal, right after the field',
    order(refused).join() === 'formula-input__field,formula-input__why,formula-input__signature'
    && order(clean).join() === 'formula-input__field,formula-input__signature', [order(refused), order(clean)]);
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M0 the header says a mark word of its own', swap('    this.mark.textContent = FORMULA_MARK;', "    this.mark.textContent = 'ƒ';")],
  ['M1 typing leaves Apply on for a text never previewed',
    swap("    this.previewed = null;\n    setDisabledReason(this.applyBtn, NEEDS_PREVIEW);\n    if (this.rest)", "    if (this.rest)")],
  ['M2 an older preview\'s answer is drawn over the newer',
    swap('if (!ticket.current() || !this.target) return;', 'if (!this.target) return;')],
  ['M3 a save goes without the read\'s base',
    swap("body: { table, column, formula, base } };", "body: { table, column, formula } };")],
  ['M4 a refusal is drawn as a word of the screen\'s own',
    swap('    this.formula.refuse(sentence);', "    this.formula.refuse(sentence ? 'Refused' : '');")],
  ['M5 the fx press reaches the header',
    swap("    this.mark.addEventListener('click', (e) => {\n      stop(e);", "    this.mark.addEventListener('click', (e) => {")],
  ['M6 the column is offered as its own operand',
    swap('this.draw(columns.filter((c) => c !== column), formula ? null : word);', 'this.draw(columns, formula ? null : word);')],
  ['M7 a blank operand is drawn as 0',
    swap("v === null || v === undefined || v === '' ? BLANK", "v === null || v === undefined || v === '' ? '0'")],
  ['M8 a count still counting is drawn as a number',
    swap("if (c.total === null) return { text: COUNTING_ROWS, at: '' };", "if (c.total === null) return { text: '0 rows will be recomputed', at: '' };")],
  ['M9 a refused save closes as if saved',
    swap("    if (!said.ok) {\n      this.refuse(said.error);\n      setDisabledReason(this.applyBtn, REFUSED_FIRST);", "    if (false) {\n      this.refuse(said.error);\n      setDisabledReason(this.applyBtn, REFUSED_FIRST);")],
  ['M10 the field offers every column, its own too',
    swap('columns: () => this.columns,', 'columns: () => [...this.columns, this.target.column],')],
  ['M11 Enter with no list open previews nothing',
    swap('onEnter: () => this.preview() });', 'onEnter: () => {} });')],
];
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bpreviewed\b/g, 'shownFor')],
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')
    && !l.trim().startsWith('*') && !l.trim().startsWith('/*')).join('\n')],
];

/** The same questions as above, asked of a (possibly mutated) module. true = something is wrong. */
async function verdict(M) {
  if ('preview' in M.formulaRequest('save', { table: 't', column: 'c', formula: '=1', base: 'B' }).body) return true;
  if (M.formulaRequest('save', { table: 't', column: 'c', formula: '=1', base: 'B' }).body.base !== 'B') return true;
  if (M.recomputeLine({ total: null, counting: true }).text !== 'Counting rows…') return true;
  if (M.previewTable(PREVIEW.sample).rows[2].cells[2] !== '—') return true;
  const g = mount(M);
  await g.pop.open({ table: 'fx', column: 'c', columns: ['a', 'c'] });
  await tick();
  const gin = find(g.pop.panel, 'formula-pop__input');
  const glist = find(g.pop.panel, 'formula-input__complete');
  const gtype = (text) => { gin.value = text; gin.setSelectionRange(text.length, text.length); gin.fire('input'); };
  gtype('=Da');
  const sentAt = g.sent.length;
  gin.fire('keydown', { key: 'Enter' });
  await tick();
  if (gin.value !== '=Date(' || g.sent.length !== sentAt) return true;
  gtype('=DatePart("year", ');
  if (all(find(g.pop.panel, 'formula-input__signature'), 'B').map((b) => b.textContent).join() !== 'value') return true;
  gtype('=Su');
  if (!gin.fire('keydown', { key: 'Escape' }).stopped || !glist.hidden) return true;
  gtype('=Sum([');
  if (find(g.pop.panel, 'formula-input__complete').children.map((r) => r.textContent).join() !== '[a]') return true;
  gtype('=[a]+1');
  const before = g.sent.length;
  gin.fire('keydown', { key: 'Enter' });
  await tick();
  if (!posts(g.sent.slice(before)).some((r) => r.body.preview === true)) return true;

  const m = mount(M);
  await m.pop.open({ table: 'fx', column: 'c', columns: ['a', 'c'] });
  await tick();
  if (all(m.pop.panel, 'BUTTON').some((b) => b.textContent === '[c]')) return true;
  const input = find(m.pop.panel, 'formula-pop__input');
  input.value = '=[a]';
  input.fire('input');
  if (find(m.pop.panel, 'formula-pop__apply').disabled !== true) return true;

  let release;
  const slow = new Promise((r) => { release = r; });
  let n = 0;
  const race = mount(M, { preview: (req) => { n += 1; return n === 1 ? slow : { ok: true, body: { ...PREVIEW, says: `for ${req.body.formula}` } }; },
    read: { ok: true, body: { table: 'fx', base: 'B1', formulas: [] } } });
  await race.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  const rin = find(race.pop.panel, 'formula-pop__input');
  rin.value = '=[a]';
  rin.fire('keydown', { key: 'Enter' });
  rin.value = '=[a]+1';
  rin.fire('keydown', { key: 'Enter' });
  await tick();
  release({ ok: true, body: { ...PREVIEW, says: 'for =[a]' } });
  await tick();
  if (find(race.pop.panel, 'formula-pop__says').textContent !== 'for =[a]+1') return true;

  const r = mount(M, { preview: { ok: false, error: 'why exactly' } });
  await r.pop.open({ table: 'fx', column: 'c', columns: ['a'] });
  await tick();
  if (find(r.pop.panel, 'formula-input__why').textContent !== 'why exactly') return true;

  const s = mount(M, { save: { ok: false, error: 'loop' } });
  await s.pop.open({ table: 'fx', column: 'c', columns: ['a', 'b'] });
  await tick();
  find(s.pop.panel, 'formula-pop__apply').click();
  await tick();
  if (!s.pop.isOpen || s.said.length) return true;

  const doc = makeDoc();
  const label = doc.createElement('div');
  const sorted = [];
  label.addEventListener('click', () => sorted.push('sort'));
  const head = new M.FormulaHeader();
  head.init({ doc, displayName: 'C', formula: '=1', open: () => {} });
  label.appendChild(head.getGui());
  find(head.getGui(), 'formula-mark').click();
  if (sorted.length) return true;
  if (find(head.getGui(), 'formula-mark').textContent !== FORMULA_MARK) return true;
  return false;
}

if (await verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module');
async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad;
    try { bad = await verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'formulapop' })).module); }
    catch (e) { if (/did not mutate|unchanged/.test(String(e && e.message))) die(`${name}: ${e.message}`); bad = true; }
    if (bad === mustCatch) { hit++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}
const caught = await score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
const escaped = await score(CONTROLS, false, 'control mutants (each must ESCAPE)');
console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
