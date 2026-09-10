/**
 * 걷기 «페이지»가 표를 자기가 짓지 않는다 — 그려진 것이 `walkTableView` 의 답이다.
 *
 *   node client2/tests/walk_table_harness.mjs
 *
 * WHY THIS EXISTS (C-72). C-70 moved the sectioning and the columns into `derive.js` so the two
 * walk tables could not drift, and the SEARCH BOX half was scored on screen. The PAGE half was
 * not: its call sat inside `boot()`, so 「it calls that function」 rested on 「its own copy is
 * deleted」 and nothing would redden the day somebody put a copy back. I reported that the page
 * could not be stood up — that was WRONG. `boot(doc, host, deps)` takes an injected `doc`, and
 * the file's own footer says why: 「bare node 로 이 모듈을 읽어도 DOM 을 안 건드려야 하니스가
 * 붙을 수 있습니다」. The place to measure already existed; C-72 made the half importable
 * (`table_view.js`) so the comparison has something to compare AGAINST.
 *
 * 🔴 WHAT IT ASSERTS IS AN EQUALITY, NOT A LOOK. Every head, every column label, every cell and
 *    its two classes are compared to what `walkTableView` returns for the same input — order
 *    included. A renderer that draws something reasonable but does not ask is red.
 *
 * 🔴 THE MUTANT THE RULING ASKED FOR IS M1: the renderer names its own columns again. It leaves
 *    the row count and the section count untouched, which is why counting could never find it.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { walkTableView } from '../src/walk/table_view.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'walk', 'main.js');
const LF = String.fromCharCode(10);

// ── the smallest document `boot()` actually needs ────────────────────────────────────────
// Measured, not guessed: `createElement` · `append` · `textContent` · `className` ·
// `setAttribute` · `addEventListener` · `value` · `checked` · `type`, plus a `head` for
// `ensureWalkStyles`. Nothing else is touched, which is what makes this cheap.
function makeDoc() {
  const make = (tag) => ({
    tagName: tag, children: [], attrs: {}, listeners: {},
    className: '', value: '', checked: false, type: '', _text: '',
    append(...cs) { cs.forEach((c) => this.children.push(c)); },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
  });
  return { createElement: make, head: make('head') };
}

const walkAll = (el, out = []) => { out.push(el); el.children.forEach((c) => walkAll(c, out)); return out; };
const byClass = (host, cls) => walkAll(host).filter((e) => (e.className || '') === cls);
const byTag = (host, tag) => walkAll(host).filter((e) => e.tagName === tag);
const settle = async () => { for (let i = 0; i < 8; i += 1) await Promise.resolve(); };

// ── fixtures ─────────────────────────────────────────────────────────────────────────────
// 🔴 MIXED TYPES AND A QUALIFIER, because a single-type answer with no qualifiers is one a
//    hard-coded renderer draws correctly. `x: 0` is here on purpose too: 「없음」 and 「0」 have
//    to stay different glyphs, and that decision moved with the half being scored.
const DECL = {
  ok: true,
  entities: [
    { type: 'die@1', keys: ['mat_id', 'x', 'y'] },
    { type: 'wafer@1', keys: ['wafer'] },
  ],
  predicates: [{ name: 'inspected@1', subjects: ['wafer@1'], object: {} }],
};
const RESULT = {
  nodes: [
    { id: 'n:1', type: 'die@1', label: 'D-1', depth: 1, keys: { mat_id: 'M-1', x: 0, y: 12 } },
    { id: 'n:2', type: 'die@1', label: 'D-2', depth: 2, keys: { mat_id: 'M-2', x: 3 } },
    { id: 'n:3', type: 'wafer@1', label: 'W-1', depth: 0, keys: { wafer: 'SYN-1' } },
  ],
  edges: [{ id: 'e:1', source: 'n:3', target: 'n:1', predicate: 'inspected', qualifiers: { gate: 7 } }],
};

let ran = 0;
const NAMES = [];
let failures = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failures.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

/** Stand the page up and hand back its host, with the walk answered from a fixture. */
async function render(mod, result = RESULT) {
  const doc = makeDoc();
  const host = doc.createElement('div');
  const handle = mod.boot(doc, host, {
    apiBase: '',
    // 🔴 The declaration comes through the SAME door the product uses. Writing it into
    //    `state.decl` would skip whatever the loader does to it.
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }),
  });
  await settle();
  handle.state.type = 'die@1';
  handle.state.run = 'done';
  handle.state.result = result;
  handle.render();
  return { host, handle };
}

async function suite(mod) {
  const { host } = await render(mod);
  const view = walkTableView(RESULT, DECL.entities);

  console.log(`${LF}-- the page draws the view's answer, not its own --`);
  eq('V1 one section head per section, worded by the view',
    byClass(host, 'wk-sechead').map((e) => e.textContent).join(' | '),
    view.sections.map((s) => s.heading).join(' | '));
  eq('V2 the column labels are the view\'s, in the view\'s order',
    byTag(host, 'th').map((e) => e.textContent).join(','),
    view.sections.flatMap((s) => s.columns.map((c) => c.name)).join(','));
  eq('V3 every cell is the view\'s text, in the view\'s order',
    byTag(host, 'td').map((e) => e.textContent).join('|'),
    view.sections.flatMap((s) => s.rows.flatMap((r) => r.cells.map((c) => c.text))).join('|'));
  // 🔴 0 IS A VALUE. `x: 0` in the fixture is the discriminant: a renderer using `v || ''`
  //    draws it as the same blank an absent key gets, and the row then lies about the die.
  ok('V4 a zero is drawn as 0 and an absent key as a blank, not as the same glyph',
    byTag(host, 'td').map((e) => e.textContent).includes('0')
      && byTag(host, 'td').map((e) => e.textContent).includes(''),
    byTag(host, 'td').map((e) => e.textContent).join('|'));
  eq('V5 the numeric class follows the view\'s reading of each cell',
    byTag(host, 'td').map((e) => (e.className === 'wk-num' ? 1 : 0)).join(''),
    view.sections.flatMap((s) => s.rows.flatMap((r) => r.cells.map(
      (c) => (c.numeric && c.kind !== 'id' ? 1 : 0)))).join(''));
  eq('V6 the id cell keeps its own class rather than the numeric one',
    byTag(host, 'td').filter((e) => e.className === 'wk-id').length,
    view.sections.reduce((n, s) => n + s.rows.length, 0));

  console.log(`${LF}-- the cap is a number the screen SAYS --`);
  const many = { nodes: Array.from({ length: 203 }, (_, i) => (
    { id: `m:${i}`, type: 'die@1', label: `L${i}`, keys: {} })), edges: [] };
  const { host: capped } = await render(mod, many);
  const capView = walkTableView(many, DECL.entities);
  // ⚠️ THE PAGE HAS OTHER NOTES. Scoping by class alone caught the form's two and made
  //    「no note」 unfalsifiable; the cap note is the one that says so.
  const capNotes = (h) => byClass(h, 'wk-note').map((e) => e.textContent)
    .filter((t) => t.includes('안 그림'));
  eq('C1 over the cap the view hides exactly what did not fit', capView.hidden, 3);
  eq('C2 and the screen prints THAT number',
    capNotes(capped).join(' / '), '이 아래 3 개 안 그림');
  ok('C3 the total is not what is printed, since 203 would read as all of it being hidden',
    !capNotes(capped).some((t) => t.includes('203')), capNotes(capped).join(' / '));
  const { host: exact } = await render(mod, { nodes: RESULT.nodes, edges: [] });
  eq('C4 under the cap there is no cap note -- the absence is the answer',
    capNotes(exact).length, 0);
}

// ═══ baseline ═══════════════════════════════════════════════════════════════════════════
const first = await loadWithProbe(SRC, {});
await suite(first.module);
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${ran} assertions, `
  + `${failures.length} failure(s)`);
failures.forEach((f) => console.log(`   x ${f}`));
const base = { ran, names: NAMES.slice(), failed: failures.length };

// ═══ mutants ════════════════════════════════════════════════════════════════════════════
const MUTANTS = [
  // 🔴 THE ONE THE RULING ASKED FOR: a copy put back. Same sections, same rows, same counts.
  { id: 'M1', what: 'the renderer names its own columns again',
    catches: 'V2 the column labels',
    from: "      for (const column of section.columns) hr.append(el(doc, 'th', '', column.name));",
    to: "      for (const name of ['\\uae4a\\uc774', '\\ub77c\\ubca8', 'id'])"
      + " hr.append(el(doc, 'th', '', name));" },
  // 🔴 THIS SLOT HELD AN EQUIVALENT MUTANT, AND THE HARNESS SAID SO. It was `cell.text || ''`,
  //    meant to collapse 0 into a blank -- but `cell.text` is already a STRING and '0' is
  //    truthy, so it changed nothing and ESCAPED. The rule it aimed at (0 is a value, absent is
  //    a blank) moved into `table_view.valueText` with the half being scored, and the renderer
  //    no longer HAS a raw value to collapse. Re-anchored rather than chased with a weaker
  //    assertion: the cells drawn in the wrong order. Same count, nothing thrown.
  { id: 'M2', what: 'the cells are drawn in the wrong order',
    catches: 'V3 every cell is the view',
    from: '        for (const cell of row.cells) {',
    to: '        for (const cell of [...row.cells].reverse()) {' },
  { id: 'M3', what: 'the numeric class is dropped',
    catches: 'V5 the numeric class',
    from: "          const td = el(doc, 'td', cell.numeric ? 'wk-num' : '', cell.text);",
    to: "          const td = el(doc, 'td', '', cell.text);" },
  { id: 'M4', what: 'the cap note prints the total instead of what was hidden',
    catches: 'C3 the total is not what is printed',
    from: '      box.append(el(doc, \'div\', \'wk-note\', `이 아래 ${view.hidden} 개 안 그림`));',
    to: '      box.append(el(doc, \'div\', \'wk-note\', `이 아래 ${r.nodes.length} 개 안 그림`));' },
  // 🔴 CONTROL: a comment cannot change an answer. If this reddens something, the harness is
  //    reading text rather than behaviour.
  { id: 'M5', what: 'CONTROL: a comment line is removed', control: true,
    from: '  // 🔴 C-72. 이 함수는 이제 «아무것도 정하지 않습니다» — 구획도 컬럼도 셀 글자도 못 그린',
    to: '  //' },
];

const runMutant = async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  const loaded = await loadWithProbe(SRC, {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  await suite(loaded.module);
  // 🔴 THE FIELD IS `failures`. Returning it as `failed` made every defect ESCAPE while the
  //    assertion it named was visibly red two lines above — the scorer reads one name, and
  //    a missing one is indistinguishable from 「nothing failed」.
  return { ran, names: NAMES.slice(), failures: failures.slice() };
};

const defects = await scoreMutants(MUTANTS.filter((m) => !m.control), runMutant,
  { baselineRan: base.ran, baselineNames: base.names,
    title: `${LF}== defect mutants (each must be CAUGHT by the check it names) ==` });
const controls = await scoreMutants(MUTANTS.filter((m) => m.control), runMutant,
  { mustCatch: false, baselineRan: base.ran, baselineNames: base.names,
    title: `${LF}== controls (each must wake NOTHING) ==` });

const scored = MUTANTS.length - defects.wrong - controls.wrong;
console.log(`${LF}  ${scored}/${MUTANTS.length} scored as intended.`);
const failed = base.failed + (MUTANTS.length - scored);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
