// FORMULA INPUT — the one formula field (owner 11-09 «ㄴ»), scored. The column's formula, a colour rule's condition, the
// test bed's expression and a chain rule's formula cells all draw it.
//
// The subject is imported whole (owner 2026-09-02: 잘라쓰기 하니스 절대 금지). What is scored:
//   H  the helpers: names offered with their arguments, columns after «[», the words a field takes, nothing in a text in
//      quotes (an escaped quote keeps it one), the call and its argument, taken text
//   I  as one types: the list under the field, ↑↓ Enter Tab take a row, Esc closes the list alone, a press takes a row,
//      Enter with no list is the owner's, the call's arguments with the one being typed in bold, the refusal line as one
//      types and the arguments under it
//   J  two on one page: typing, a list, a refusal and a taken row in one leave the other as it was
// Run: node client2/tests/formula_input_harness.mjs
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import * as BASELINE from '../src/formula_input.js';

const SRC_PATH = fileURLToPath(new URL('../src/formula_input.js', import.meta.url));
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
          const event = { type, target: this, key: init.key, ctrlKey: !!init.ctrlKey, metaKey: !!init.metaKey, stopped: false, prevented: false,
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
const bold = (el) => all(el, 'B').map((b) => b.textContent).join();

/** One field in a host of its own; `doc` shared when two sit on one page. */
function field(M, deps = {}, doc = makeDoc()) {
  const host = doc.createElement('div');
  const entered = [];
  const typed = [];
  const f = new M.FormulaInput(host, { doc, columns: () => ['a', 'b', 'dt_lot'], onEnter: (t) => entered.push(t),
    onInput: (t) => typed.push(t), ...deps });
  const typeIn = (text) => { f.input.value = text; f.input.setSelectionRange(text.length, text.length); f.input.fire('input'); };
  const list = find(host, 'formula-input__complete');
  const sign = find(host, 'formula-input__signature');
  const why = find(host, 'formula-input__why');
  const lit = () => list.children.findIndex((r) => r.getAttribute('aria-selected') === 'true');
  const order = () => find(host, 'formula-input').children.filter((n) => !n.hidden).map((n) => n.className);
  return { f, host, doc, entered, typed, typeIn, list, sign, why, lit, order };
}

/** The questions, asked of a (possibly mutated) module. Returns the failed names (quiet) or scores them (loud). */
async function suite(M, loud) {
  const bad = [];
  const say = (name, cond, saw) => { if (loud) ok(name, cond, saw); else if (!cond) bad.push(name); };

  if (loud) console.log('\n── H. THE HELPERS ──────────────────────────────────────────────────');
  const da = M.offerAt('=Da', 3, []);
  say('H1 a name typed: the functions that start with it, by name, each with its arguments',
    da && da.kind === 'function' && da.items[0].value === 'Date' && da.items[1].value === 'DatePart'
    && da.items[1].side === 'DatePart(part, value)' && da.items[1].head === 'Da' && da.items[1].rest === 'tePart',
    da && da.items.slice(0, 3));
  const col = M.offerAt('=Sum([D', 7, ['dt_lot', 'b', 'dt_x']);
  say('H2 after «[» the table\'s columns that start with it, any case, in the table\'s order; «[» alone - all',
    col && col.kind === 'column' && col.items.map((i) => i.value).join() === 'dt_lot,dt_x'
    && M.offerAt('=Sum([', 6, ['a', 'b']).items.length === 2, col);
  say('H3 nothing in a text in quotes, after a digit, or for a name nothing starts with',
    M.offerAt('="Da', 4, []) === null && M.offerAt('=1Da', 4, []) === null && M.offerAt('=Zzz', 4, []) === null);
  say('H4 an escaped quote keeps the text open - nothing offered in it; past its close, names again',
    M.offerAt('="a\\"Da', 7, []) === null && M.offerAt('="a\\\\"&Da', 9, []) !== null);
  say('H5 the call the caret is in and which argument: commas at its own depth, a call inside it closed',
    JSON.stringify(M.callAt('=DatePart("a,b", ', 17)) === '{"name":"DatePart","arg":1}'
    && JSON.stringify(M.callAt('=Round(Sum([a], [b]), ', 22)) === '{"name":"Round","arg":1}'
    && M.callAt('=[a]+1', 6) === null, [M.callAt('=DatePart("a,b", ', 17), M.callAt('=Round(Sum([a], [b]), ', 22)]);
  const fn = M.acceptAt('=Datx+1', 4, M.offerAt('=Datx+1', 4, []) || { kind: 'function', from: 1 }, 'DatePart');
  const cl = M.acceptAt('=Sum([dt_]+1', 9, M.offerAt('=Sum([dt_]+1', 9, ['dt_lot']), 'dt_lot');
  say('H6 taken: a function as «Name(» over the rest of the word, a column as «name]» over a «]» already there',
    fn.text === '=DatePart(, )+1' && fn.caret === 10 && cl.text === '=Sum([dt_lot]+1' && cl.caret === 13, [fn, cl]);
  say('H8 a function taken comes as its call\'s skeleton: a slot for each argument it needs, none for «[…]» or «...»',
    M.callSkeleton('If') === 'If(, , )' && M.callSkeleton('DatePart') === 'DatePart(, )' && M.callSkeleton('Sum') === 'Sum()'
    && M.callSkeleton('Count') === 'Count()' && M.callSkeleton('Find') === 'Find(, )', ['If', 'DatePart', 'Sum', 'Count', 'Find'].map(M.callSkeleton));
  const w = M.offerAt('uni', 3, [], ['unique_concat', 'spec_out.s_o']);
  const wt = w && M.acceptAt('uni', 3, w, w.items.find((i) => i.word).value, true);
  say('H7 the words a field takes beside a formula are offered with the functions and taken as themselves',
    Boolean(w) && w.items.some((i) => i.value === 'unique_concat' && i.word && i.side === '')
    && w.items.some((i) => i.value === 'UniqueConcatenate') && wt.text === 'unique_concat'
    && M.offerAt('spec_out.s', 10, [], ['spec_out.s_o']).items[0].value === 'spec_out.s_o', [w && w.items, wt]);

  if (loud) console.log('\n── I. AS ONE TYPES ─────────────────────────────────────────────────');
  const t = field(M);
  t.typeIn('=Da');
  say('I1 typing «=Da» opens the list under the field, the first row lit', !t.list.hidden && t.list.children.length > 2
    && t.lit() === 0 && t.list.getAttribute('role') === 'listbox' && t.f.input.getAttribute('aria-expanded') === 'true', [t.list.hidden, t.lit()]);
  t.f.input.fire('keydown', { key: 'ArrowDown' });
  const enter = t.f.input.fire('keydown', { key: 'Enter' });
  say('I2 ↓ then Enter takes the lit row as «DatePart(, )», the caret in its first slot - the owner\'s apply not called, the list closed',
    t.f.value === '=DatePart(, )' && t.f.input.selectionStart === 10 && enter.prevented && t.list.hidden && t.entered.length === 0,
    [t.f.value, t.entered]);
  say('I3 ...and its arguments stand under it, the first in bold', !t.sign.hidden && t.sign.textContent === 'DatePart(part, value)'
    && bold(t.sign) === 'part', t.sign.textContent);
  t.typeIn('=DatePart("year", ');
  say('I4 past a comma the second argument is the bold one', bold(t.sign) === 'value', bold(t.sign));
  t.typeIn('=Find("a", "b", ');
  say('I5 an argument that may be left out stands in [ ]', t.sign.textContent === 'Find(text, within, [nth])'
    && bold(t.sign) === '[nth]', t.sign.textContent);
  t.typeIn('=Sum([a], [b], ');
  say('I6 a fold of more columns: past its last named argument «...» is bold',
    t.sign.textContent === 'Sum(column, ...)' && bold(t.sign) === '...', t.sign.textContent);
  t.typeIn('=Sum([');
  const tab = t.f.input.fire('keydown', { key: 'Tab' });
  say('I7 «[» offers the columns; Tab takes the lit one as «a]»', t.f.value === '=Sum([a]' && tab.prevented && t.list.hidden, t.f.value);
  t.typeIn('=Su');
  const esc = t.f.input.fire('keydown', { key: 'Escape' });
  say('I8 Esc closes the list alone - the key goes no further', t.list.hidden && esc.stopped && t.f.value === '=Su');
  t.typeIn('=Ro');
  t.list.children[0].dispatch('mousedown');
  say('I9 a press on a row takes it', t.f.value === '=Round(, )' && t.list.hidden, t.f.value);
  t.typeIn('=[a]+1');
  const plain = t.f.input.fire('keydown', { key: 'Enter' });
  say('I10 with no list open, Enter is a new line - the box\'s own, not the owner\'s', t.entered.length === 0 && !plain.prevented, t.entered);
  const ctrl = t.f.input.fire('keydown', { key: 'Enter', ctrlKey: true });
  const cmd = t.f.input.fire('keydown', { key: 'Enter', metaKey: true });
  say('I16 Ctrl+Enter (⌘+Enter) is the owner\'s apply - with the text', t.entered.join() === '=[a]+1,=[a]+1' && ctrl.prevented
    && cmd.prevented, t.entered);
  const lone = field(M, { onEnter: undefined });
  const raised = [];
  let sent = 0;
  lone.doc.defaultView = { Event: function Ev(type) { this.type = type; } };
  lone.f.input.dispatchEvent = (ev) => { raised.push(ev.type); };
  lone.f.input.form = { requestSubmit: () => { sent += 1; } };
  lone.typeIn('=[a]');
  raised.length = 0;
  lone.f.input.fire('keydown', { key: 'Enter', ctrlKey: true });
  say('I17 with no owner, Ctrl+Enter raises the box\'s change and sends the form it sits in - as Enter in one line did',
    raised.join() === 'change' && sent === 1, [raised, sent]);
  say('I11 each change is told to the owner', t.typed.length > 5 && t.typed[t.typed.length - 1] === '=[a]+1', t.typed.length);
  const r = field(M, { refusal: (text) => (text.includes('(') && !text.includes(')') ? 'The expression ends too soon' : '') });
  r.typeIn('=DatePart(');
  say('I12 a field that reads its text says why as one types; the arguments line hangs under the refusal',
    !r.why.hidden && r.why.textContent === 'The expression ends too soon' && r.f.input.getAttribute('aria-invalid') === 'true'
    && r.order().join() === 'formula-input__field,formula-input__why,formula-input__signature', [r.why.textContent, r.order()]);
  r.typeIn('=DatePart(1, 2)');
  say('I13 ...and the line goes when the text stands', r.why.hidden && r.f.input.getAttribute('aria-invalid') === 'false'
    && r.order().join() === 'formula-input__field', r.order());
  r.f.refuse('the server says no');
  say('I14 the owner can say why too (a server\'s refusal)', !r.why.hidden && r.why.textContent === 'the server says no');
  r.f.value = '';
  say('I15 an empty field refuses nothing', r.why.hidden);

  if (loud) console.log('\n── J. TWO ON ONE PAGE ──────────────────────────────────────────────');
  const doc = makeDoc();
  const a = field(M, { refusal: () => 'A refuses' }, doc);
  const b = field(M, { columns: () => ['z'] }, doc);
  a.typeIn('=Da');
  say('J1 typing in one opens its list alone; the other\'s text, list and line are as they were',
    !a.list.hidden && b.list.hidden && b.f.value === '' && b.why.hidden && !a.why.hidden && a.list !== b.list);
  b.typeIn('=Sum([');
  say('J2 each offers its own columns', b.list.children.map((x) => x.textContent).join() === '[z]' && !a.list.hidden,
    b.list.children.map((x) => x.textContent));
  b.f.input.fire('keydown', { key: 'Enter' });
  say('J3 a row taken in one changes that one alone', b.f.value === '=Sum([z]' && a.f.value === '=Da' && b.entered.length === 0
    && a.entered.length === 0, [a.f.value, b.f.value]);
  if (loud) console.log('\n── F. THE FORMULA MARK ───────────────────────────────────────────────');
  const marked = (x) => find(x.host, 'formula-input__field').children;
  const mark = (x) => marked(x).filter((n) => has(n, 'formula-mark'));
  say('F1 the field wears the formula mark once, before the box, in each field on the page',
    mark(a).length === 1 && mark(b).length === 1 && marked(a)[0] === mark(a)[0] && mark(a)[0].textContent === M.FORMULA_MARK
    && M.FORMULA_MARK === 'fx', marked(a).map((n) => n.className));
  const own = M.formulaMark(makeDoc());
  say('F2 the mark a folded line wears is the same one (one place)', has(own, 'formula-mark') && own.textContent === M.FORMULA_MARK
    && own.getAttribute('aria-hidden') === 'true', own.className);
  const keys = find(a.host, 'formula-input__keys');
  say('F3 how to apply stands beside the box, in the field\'s own words', keys && keys.textContent === M.APPLY_KEYS
    && M.APPLY_KEYS === 'Ctrl+Enter to apply' && find(a.host, 'formula-input__field').children.includes(keys));
  say('F4 the box takes many lines', a.f.input.tagName === 'TEXTAREA', a.f.input.tagName);
  return bad;
}

await suite(BASELINE, true);

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}`);
  return src.replace(from, to);
};
const DEFECTS = [
  ['M1 a plain Enter applies - no new line, and it takes no listed row',
    swap("    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {", "    if (e.key === 'Enter') {")],
  ['M11 with no owner, Ctrl+Enter sends no form', swap('    if (this.input.form && this.input.form.requestSubmit) this.input.form.requestSubmit();\n', '')],
  ['M12 ⌘+Enter is not taken', swap("(e.ctrlKey || e.metaKey)", 'e.ctrlKey')],
  ['M13 a function taken as «Name(» alone', swap("(word ? value : callSkeleton(value))", '(word ? value : `${value}(`)')],
  ['M15 an optional argument gets a slot', swap(" && !/^\\[.*\\]$/.test(a)", '')],
  ['M14 no word for how to apply', swap('    field.appendChild(this.keys);\n', '')],
  ['M2 the argument being typed does not move past a comma',
    swap("    else if (ch === ',' && calls.length) calls[calls.length - 1].arg += 1;\n", '')],
  ['M3 Esc with the list open goes on to the owner',
    swap('      if (e.stopPropagation) e.stopPropagation();\n      this.closeList();', '      this.closeList();')],
  ['M4 the arguments line hangs under the field, over the refusal',
    swap('    this.root.appendChild(this.sign);', '    field.appendChild(this.sign);')],
  ['M5 a column taken over a «]» already there doubles it',
    swap(": (/^[^[\\](),]*\\]/.exec(after) || [''])[0];", ": '';")],
  ['M6 an escaped quote closes the text',
    swap("      if (ch === '\\\\' && ESCAPED.includes(before[i + 1] || '')) i += 1;\n      else if (ch === quote) quote = null;", '      if (ch === quote) quote = null;')],
  ['M7 the field\'s own reading is not asked as one types',
    swap('    this.suggest();\n    this.check();', '    this.suggest();')],
  ['M8 one list for every field on the page (module state)',
    (src) => swap("    this.list = el('div', 'formula-input__complete');", "    this.list = SHARED.list || (SHARED.list = el('div', 'formula-input__complete'));")(src)
      .replace("export class FormulaInput {", "const SHARED = {};\nexport class FormulaInput {")],
  ['M9 a word taken as a call',
    swap("const piece = offer.kind === 'function' ? (word ? value : callSkeleton(value)) : `${value}]`;", "const piece = offer.kind === 'function' ? callSkeleton(value) : `${value}]`;")],
];
DEFECTS.push(['M10 the field wears no formula mark', swap('    field.appendChild(formulaMark(this.doc));\n', '')]);
const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bscan\b/g, 'scanText')],
  ['comments stripped', (src) => src.split('\n').filter((l) => !l.trim().startsWith('//')
    && !l.trim().startsWith('*') && !l.trim().startsWith('/*')).join('\n')],
];
async function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad;
    try { bad = (await suite((await loadWithProbe(SRC_PATH, { mutate, tag: 'formulain' })).module, false)).length > 0; }
    catch (e) { if (/did not mutate|unchanged/.test(String(e && e.message))) die(`${name}: ${e.message}`); bad = true; }
    if (bad === mustCatch) { hit++; passed++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}
await score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
await score(CONTROLS, false, 'control mutants (each must ESCAPE)');
console.log(`\n${passed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
