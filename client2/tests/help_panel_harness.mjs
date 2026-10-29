// HELP PANEL — the admin help's side panel (owner 10-29 «ㄴ»), scored.
//
// The subject is imported whole (owner 2026-09-02: 잘라쓰기 하니스 절대 금지). What is scored:
//   A  the request: the question as typed, to POST /admin/help/ask
//   B  an answer as drawn: a tool and its fields and count · a tool outside the tab and its doors · not sure and the
//      tools near · not asked (the model's refusal by name) · a count refused
//   C  asking: Ask off while empty or waiting, the seconds counted, Open form hands the fields, help_id and count
//   D  Cancel stops the waiting only - the answer that comes after is kept, marked «arrived after you stopped»
//   E  Earlier: newest first, the shown ask not listed twice, a row shows its ask again, a run said on its ask;
//      nothing asked says so; two instances apart
// Run: node client2/tests/help_panel_harness.mjs
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/help_panel.js';

const SRC_PATH = fileURLToPath(new URL('../src/help_panel.js', import.meta.url));
let passed = 0;
let failed = 0;
function ok(name, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${name}`); }
  else { failed++; console.log(`  FAIL ${name}${saw === undefined ? '' : `  saw: ${JSON.stringify(saw)}`}`); }
}
function die(msg) { console.log(`HARNESS FAILURE: ${msg}`); console.log(`ASSERTIONS ${passed} ${failed + 1}`); process.exit(1); }

// ── a DOM just big enough: built, clicked, events bubble ─────────────────────────────
function makeDoc() {
  return {
    createElement(tag) {
      const el = {
        tagName: String(tag).toUpperCase(), className: '', children: [], parentNode: null, hidden: false, id: '',
        attrs: {}, listeners: {}, dataset: {}, _text: '', value: '', disabled: false, type: '', focused: false,
        get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
        set textContent(v) { this._text = String(v); this.children = []; },
        appendChild(c) { if (c.parentNode) c.remove(); c.parentNode = this; this.children.push(c); return c; },
        remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((x) => x !== this); this.parentNode = null; },
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
        removeAttribute(k) { delete this.attrs[k]; },
        addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
        focus() { this.focused = true; },
        fire(type, init = {}) {
          const event = { type, target: this, key: init.key, shiftKey: Boolean(init.shiftKey), prevented: false,
            stopPropagation() {}, preventDefault() { this.prevented = true; } };
          (this.listeners[type] || []).slice().forEach((fn) => fn(event));
          return event;
        },
        click() { return this.disabled ? null : this.fire('click'); },
      };
      return el;
    },
  };
}
const has = (el, cls) => String(el.className).split(' ').includes(cls);
const find = (el, cls) => {
  if (!el) return null;
  if (has(el, cls)) return el;
  for (const c of el.children) { const hit = find(c, cls); if (hit) return hit; }
  return null;
};
const findAll = (el, cls, out = []) => { if (!el) return out; if (has(el, cls)) out.push(el); el.children.forEach((c) => findAll(c, cls, out)); return out; };
const text = (el, cls) => { const hit = find(el, cls); return hit ? hit.textContent : null; };
const tick = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

// a clock the harness runs by hand
function makeClock(start = Date.parse('2026-10-29T09:00:00Z')) {
  const pending = new Map();
  let n = 0;
  let now = start;
  return { set: (fn) => { n += 1; pending.set(n, fn); return n; }, clear: (h) => pending.delete(h), now: () => now,
    advance(ms) { now += ms; const fns = [...pending.values()]; pending.clear(); fns.forEach((fn) => fn()); },
    get size() { return pending.size; } };
}

const FORMS = { chain_replay: 'Replay chain rules over old data (R1)', resolve: 'Recompute shown values from stored layers (R3)' };
const TOOL = {
  op: 'chain_replay', label: 'Replay chain rules over old data (R1)', why: "The join's rule never ran over old rows.",
  params: { rule: 'inventory_confirmed', row_ids: ['r1', 'r2'] }, similar: [], refused: null, tries: 1, help_id: 'h-tool',
  count: { affected: 1240, affected_label: 'rows to re-run', count_kind: 'sample' }, count_refused: null,
};
const DOOR = {
  op: 'formula_column', label: 'Compute a column from a formula', why: 'A same-row formula.', params: {}, similar: [],
  refused: null, tries: 1, help_id: 'h-door', count: null, count_refused: null,
  doors: [{ name: 'on the grid', how: "the grid's column header - right-click it", when: 'the formula window',
            open: { label: 'Open the grid', href: 'index.html' } },
          { name: 'save', how: 'POST /admin/chain/formula', when: 'saved' }],
};
const UNSURE = {
  op: null, params: {}, why: 'The question names no table.', refused: "'x' is not a tool in the list", tries: 2,
  help_id: 'h-unsure', count: null, count_refused: null, label: null,
  similar: [{ op: 'resolve', label: 'Recompute shown values from stored layers (R3)' },
            { op: 'formula_column', label: 'Compute a column from a formula' }],
};
const NOT_ASKED = { op: null, params: {}, why: null, similar: [], tries: 0, help_id: 'h-no', count: null, count_refused: null,
  refused: 'the language model call failed: Request timed out.', label: null };
const COUNT_REFUSED = { ...TOOL, help_id: 'h-cr', count: null,
  count_refused: 'The count for this operation cannot be computed: QueryCanceled' };

/** A send whose answers the harness releases by hand, in order; every request kept. */
function makeSend() {
  const sent = [];
  const waiting = [];
  const send = (req) => { sent.push(req); return new Promise((resolve) => waiting.push(resolve)); };
  return { send, sent, answer(got) { const r = waiting.shift(); if (r) r(got); } };
}

function mount(M) {
  const doc = makeDoc();
  const host = doc.createElement('div');
  const clock = makeClock();
  const s = makeSend();
  const opened = [];
  const panel = new M.HelpPanel(host, { doc, send: s.send, clock, forms: () => FORMS, openForm: (x) => opened.push(x) });
  panel.open();
  return { doc, host, clock, s, opened, panel };
}
async function asked(m, question, got) {
  find(m.panel.root, 'help-panel__input').value = question;
  find(m.panel.root, 'help-panel__input').fire('input');
  find(m.panel.root, 'help-panel__ask').click();
  if (got) { m.s.answer(got); await tick(); }
}
const card = (m) => find(m.panel.root, 'help-panel__card');

const X = BASELINE;

console.log('\n── A. THE REQUEST ──────────────────────────────────────────────────');
{
  const r = X.helpRequest('dt_lot 칸이 비어 있어');
  ok('A1 the question as typed, to the help route', r.method === 'POST' && r.path === '/admin/help/ask'
    && r.body.question === 'dt_lot 칸이 비어 있어', r);
}

console.log('\n── B. AN ANSWER AS DRAWN ───────────────────────────────────────────');
{
  const t = X.answerView(TOOL, FORMS);
  ok('B1 a tool: its label, its name, the model\'s why', t.kind === 'tool' && t.title === TOOL.label && t.op === 'chain_replay' && t.why === TOOL.why);
  ok('B2 ...its fields as filled, a list joined', t.fields.length === 2 && t.fields[1].value === 'r1, r2', t.fields);
  ok('B3 ...the count with the tool\'s own word', t.count && t.count.value === '1240' && t.count.label === 'rows to re-run', t.count);
  ok('B4 ...and a form, as the page has one', t.form === true && t.helpId === 'h-tool');
  const d = X.answerView(DOOR, FORMS);
  ok('B5 a tool outside the tab: no form, its doors', d.form === false && d.doors.length === 2 && d.doors[0].how.startsWith("the grid's"));
  ok('B6 ...a door opens a page only when it says which', d.doors[0].open && d.doors[0].open.href === 'index.html' && d.doors[1].open === null);
  const u = X.answerView(UNSURE, FORMS);
  ok('B7 not sure: the tools near with the server\'s labels, a form only for the page\'s', u.kind === 'unsure' && u.near.length === 2
    && u.near[0].form === true && u.near[1].form === false && u.near[1].label === 'Compute a column from a formula', u.near);
  const n = X.answerView(NOT_ASKED, FORMS);
  ok('B8 the model not asked: its refusal word for word', n.kind === 'refused' && n.title === 'Not asked' && n.refused === NOT_ASKED.refused);
  const c = X.answerView(COUNT_REFUSED, FORMS);
  ok('B9 a count refused: no number, the server\'s sentence, the form still offered', c.count === null && c.countRefused === COUNT_REFUSED.count_refused && c.form === true);
}

console.log('\n── C. ASKING ───────────────────────────────────────────────────────');
{
  const m = mount(X);
  const askBtn = find(m.panel.root, 'help-panel__ask');
  ok('C1 the panel lives in its own host, open', m.host.children.length === 1 && m.panel.isOpen);
  ok('C2 Ask is off while nothing is written, and says why', askBtn.disabled === true && askBtn.getAttribute('title') === X.WRITE_FIRST);
  ok('C3 the head says the asks last until reload', text(m.panel.root, 'help-panel__tag') === X.UNTIL_RELOAD);
  ok('C4 nothing asked says so', text(m.panel.root, 'help-panel__empty') === X.NOTHING_ASKED);
  await asked(m, '  dt_lot 칸이 비어 있어 ');
  ok('C5 one request, the question trimmed', m.s.sent.length === 1 && m.s.sent[0].body.question === 'dt_lot 칸이 비어 있어');
  ok('C6 while it is out: the card says so, Ask off with its reason', text(card(m), 'help-card__title') === 'Asking the model'
    && askBtn.disabled === true && askBtn.getAttribute('title') === X.ASKING);
  const cancelBefore = find(card(m), 'help-card__cancel');
  m.clock.advance(3000);
  ok('C7 the seconds are counted', text(card(m), 'help-card__meta') === '3 s', text(card(m), 'help-card__meta'));
  ok('C7b ...in place: Cancel is the same button, not drawn again under the hand', find(card(m), 'help-card__cancel') === cancelBefore);
  find(m.panel.root, 'help-panel__ask').click();
  ok('C8 a second Ask while one is out sends nothing', m.s.sent.length === 1);
  m.s.answer({ ok: true, body: TOOL });
  await tick();
  ok('C9 the answer: the tool, its fields, its count', text(card(m), 'help-card__title') === TOOL.label
    && text(card(m), 'help-card__count-value') === '1240' && text(card(m), 'help-card__count-label') === 'rows to re-run');
  ok('C10 the clock stops once it came', m.clock.size === 0);
  find(card(m), 'help-card__open').click();
  const o = m.opened[0] || {};
  ok('C11 Open form hands the tool, its fields, the ask\'s help_id and question, and the count', m.opened.length === 1
    && o.op === 'chain_replay' && o.params.rule === 'inventory_confirmed' && o.helpId === 'h-tool'
    && o.question === 'dt_lot 칸이 비어 있어' && o.count && o.count.affected === 1240, o);
  ok('C12 Enter asks, shift+Enter does not', (() => {
    const k = mount(X);
    const input = find(k.panel.root, 'help-panel__input');
    input.value = 'q';
    input.fire('input');
    input.fire('keydown', { key: 'Enter', shiftKey: true });
    const before = k.s.sent.length;
    input.fire('keydown', { key: 'Enter' });
    return before === 0 && k.s.sent.length === 1;
  })());
}

console.log('\n── D. CANCEL ───────────────────────────────────────────────────────');
{
  const m = mount(X);
  await asked(m, 'first');
  find(card(m), 'help-card__cancel').click();
  ok('D1 Cancel says the server still finishes it', text(card(m), 'help-card__title') === X.STOPPED_WAITING, text(card(m), 'help-card__title'));
  ok('D2 ...and Ask is on again', find(m.panel.root, 'help-panel__ask').disabled === false);
  m.s.answer({ ok: true, body: TOOL });
  await tick();
  ok('D3 the answer that came after is kept, marked', text(card(m), 'help-card__title') === TOOL.label
    && text(card(m), 'help-card__late') === X.ARRIVED_LATE);
  const n = mount(X);
  await asked(n, 'first');
  find(card(n), 'help-card__cancel').click();
  await asked(n, 'second');
  n.s.answer({ ok: true, body: TOOL });
  await tick();
  const rows = findAll(n.panel.root, 'help-row');
  ok('D4 asked again meanwhile: the late one lands in Earlier, marked', rows.length === 1
    && text(rows[0], 'help-row__q') === 'first' && text(rows[0], 'help-row__tail') === X.ARRIVED_LATE, rows.map((r) => r.textContent));
  ok('D5 ...and the new ask is still the one waited for', text(card(n), 'help-card__title') === 'Asking the model');
}

console.log('\n── E. WHAT EACH ANSWER DRAWS ───────────────────────────────────────');
{
  const r = mount(X);
  await asked(r, 'q', { ok: true, body: NOT_ASKED });
  ok('E1 not asked: the model\'s refusal word for word, no form', text(card(r), 'help-card__refused') === NOT_ASKED.refused
    && !find(card(r), 'help-card__open'));
  const f = mount(X);
  await asked(f, 'q', { ok: false, error: 'Help refused: 503 token not set' });
  ok('E2 a refused request: its sentence as the card', text(card(f), 'help-card__refused') === 'Help refused: 503 token not set');
  const u = mount(X);
  await asked(u, 'q', { ok: true, body: UNSURE });
  const opens = findAll(card(u), 'help-card__open');
  ok('E3 not sure: the tools near, Open form only where the page has the form', findAll(card(u), 'help-card__near-row').length === 2
    && opens.length === 1 && text(card(u), 'help-card__meta') === 'asked 2 times');
  opens[0].click();
  ok('E4 ...that Open form opens the tool empty, the ask\'s help_id on it', u.opened.length === 1 && u.opened[0].op === 'resolve'
    && Object.keys(u.opened[0].params).length === 0 && u.opened[0].helpId === 'h-unsure');
  const d = mount(X);
  await asked(d, 'q', { ok: true, body: DOOR });
  const page = find(card(d), 'help-card__page');
  ok('E5 outside the tab: its doors, a page link where a door names one, no Open form',
    findAll(card(d), 'help-card__door').length === 2 && page && page.getAttribute('href') === 'index.html'
    && page.textContent === 'Open the grid' && !find(card(d), 'help-card__open'));
  const c = mount(X);
  await asked(c, 'q', { ok: true, body: COUNT_REFUSED });
  ok('E6 a count refused: the sentence, no number, Open form still there', text(card(c), 'help-card__count-refused') === COUNT_REFUSED.count_refused
    && !find(card(c), 'help-card__count') && find(card(c), 'help-card__open'));
}

console.log('\n── F. EARLIER · TWO PANELS ─────────────────────────────────────────');
{
  const m = mount(X);
  await asked(m, 'one', { ok: true, body: TOOL });
  await asked(m, 'two', { ok: true, body: UNSURE });
  await asked(m, 'three', { ok: true, body: DOOR });
  const rows = findAll(m.panel.root, 'help-row');
  ok('F1 Earlier: newest first, the shown ask not listed', rows.length === 2 && text(rows[0], 'help-row__q') === 'two'
    && text(rows[1], 'help-row__q') === 'one', rows.map((r) => text(r, 'help-row__q')));
  ok('F2 a row says what came back', text(rows[0], 'help-row__what') === 'Not sure' && text(rows[1], 'help-row__what') === TOOL.label);
  rows[1].click();
  ok('F3 a row shows its ask again', text(card(m), 'help-card__title') === TOOL.label && findAll(m.panel.root, 'help-row').length === 2);
  m.panel.noteRun('h-tool', 'r-77');
  m.panel.noteRun('h-nobody', 'r-78');
  const again = findAll(m.panel.root, 'help-row');
  ok('F4 a run queued from an answer is said on its ask, and only there', m.panel.asks.find((r) => r.question === 'one').runId === 'r-77'
    && !again.some((r) => text(r, 'help-row__tail') === 'run r-78'));
  findAll(m.panel.root, 'help-row')[0].click();
  ok('F5 ...and on its row once it is listed', findAll(m.panel.root, 'help-row').some((r) => text(r, 'help-row__tail') === 'run r-77'));
  const doc = makeDoc();
  const h1 = doc.createElement('div');
  const h2 = doc.createElement('div');
  const s1 = makeSend();
  const s2 = makeSend();
  const p1 = new X.HelpPanel(h1, { doc, send: s1.send, clock: makeClock(), forms: () => FORMS });
  const p2 = new X.HelpPanel(h2, { doc, send: s2.send, clock: makeClock(), forms: () => FORMS });
  p1.open();
  p2.open();
  find(p1.root, 'help-panel__input').value = 'only here';
  find(p1.root, 'help-panel__input').fire('input');
  find(p1.root, 'help-panel__ask').click();
  ok('F6 two panels: an ask on one leaves the other untouched', s1.sent.length === 1 && s2.sent.length === 0
    && p2.asks.length === 0 && find(p2.root, 'help-panel__card').hidden === true && h1.children[0] !== h2.children[0]);
  p1.close();
  ok('F7 closing hides it and keeps its asks', p1.isOpen === false && p1.asks.length === 1 && p2.isOpen);
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 Cancel drops the answer that comes after', swap('    rec.late = rec.stopped;\n', '    if (rec.stopped) return;\n')],
  ['M2 Open form leaves the ask\'s help_id behind',
    swap('op: v.op, params: v.params, helpId: v.helpId,', 'op: v.op, params: v.params, helpId: null,')],
  ['M3 the model\'s refusal is drawn as a word of the screen\'s own',
    swap("this.el('div', 'help-card__refused', v.refused)", "this.el('div', 'help-card__refused', 'Refused')")],
  ['M4 Open form offered for a tool the page has no form for', swap('form: a.op in forms, params,', 'form: true, params,')],
  ['M5 a count refused is not said', swap('if (v.countRefused) box', 'if (false) box')],
  ['M6 Ask stays on while one is out', swap('const why = this.waiting ? ASKING', 'const why = false ? ASKING')],
  ['M7 the shown ask is listed in Earlier too', swap('this.asks.filter((r) => r !== this.shown)', 'this.asks')],
  ['M8 the model not asked is drawn as not sure', swap('if (!a.tries) return', 'if (false) return')],
  ['M10 the waiting card is drawn again each second', swap('if (this.seconds && rec === this.shown) this.seconds.textContent = this.secondsOf(rec);', 'this.render();')],
  ['M9 a page link drawn for a door that names none',
    swap("open: d.open && d.open.href ? {", "open: { label: '', href: '#' } || d.open && d.open.href ? {")],
];
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bshown\b/g, 'onCard')],
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')
    && !l.trim().startsWith('*') && !l.trim().startsWith('/*')).join('\n')],
];

/** The same questions as above, asked of a (possibly mutated) module. true = something is wrong. */
async function verdict(M) {
  if (M.answerView(NOT_ASKED, FORMS).kind !== 'refused') return true;
  if (M.answerView(DOOR, FORMS).form !== false) return true;
  if (M.answerView(DOOR, FORMS).doors[1].open !== null) return true;

  const m = mount(M);
  await asked(m, 'first');
  if (find(m.panel.root, 'help-panel__ask').disabled !== true) return true;
  const before = find(card(m), 'help-card__cancel');
  m.clock.advance(1000);
  if (find(card(m), 'help-card__cancel') !== before) return true;
  find(card(m), 'help-card__cancel').click();
  m.s.answer({ ok: true, body: TOOL });
  await tick();
  if (text(card(m), 'help-card__late') !== BASELINE.ARRIVED_LATE) return true;
  find(card(m), 'help-card__open').click();
  if (!m.opened[0] || m.opened[0].helpId !== 'h-tool') return true;
  await asked(m, 'second', { ok: true, body: COUNT_REFUSED });
  if (text(card(m), 'help-card__count-refused') !== COUNT_REFUSED.count_refused) return true;
  if (findAll(m.panel.root, 'help-row').length !== 1) return true;

  const r = mount(M);
  await asked(r, 'q', { ok: true, body: NOT_ASKED });
  if (text(card(r), 'help-card__refused') !== NOT_ASKED.refused) return true;
  return false;
}

if (await verdict(BASELINE)) die('the scorer already fails on the UNMUTATED module');
async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad;
    try { bad = await verdict((await loadWithProbe(SRC_PATH, { mutate, tag: 'helppanel' })).module); }
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
