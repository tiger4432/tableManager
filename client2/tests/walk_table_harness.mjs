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
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { walkTableView } from '../src/walk/table_view.js';
import { SIGN } from '../src/rnd_board/marking_store.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'walk', 'main.js');
const LF = String.fromCharCode(10);

// ── the smallest document `boot()` actually needs ────────────────────────────────────────
// Measured, not guessed: `createElement` · `append` · `textContent` · `className` ·
// `setAttribute` · `addEventListener` · `value` · `checked` · `type`, plus a `head` for
// `ensureWalkStyles`. Nothing else is touched, which is what makes this cheap.
function makeDoc() {
  const make = (tag) => option(tag, {
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
// The browser's rule for an <option>: with no value of its own it is worth its TEXT. A stub where every
// value starts as '' cannot see the type placeholder becoming a type (lead b417e2ad8), so it keeps the rule.
function option(tag, node) {
  if (tag !== 'option') return node;
  delete node.value;
  return Object.defineProperty(node, 'value', {
    get() { return this._value !== undefined ? this._value : this.textContent; },
    set(v) { this._value = String(v); },
  });
}

const walkAll = (el, out = []) => { out.push(el); el.children.forEach((c) => walkAll(c, out)); return out; };
const byClass = (host, cls) => walkAll(host).filter((e) => (e.className || '') === cls);
const byTag = (host, tag) => walkAll(host).filter((e) => e.tagName === tag);
// The view's own cells: the table's check column (lead 53050a4ec) is the page's, not the view's.
const viewCells = (host, tag) => byTag(host, tag).filter((e) => e.className !== 'wk-check');
const settle = async () => { for (let i = 0; i < 8; i += 1) await Promise.resolve(); };
// What «Copy table» handed the clipboard writer, and what the writer answers (lead a27dfbb0f): the page's writer, handed in.
const CLIP = [];
const CLIP_OK = { ok: true };
const writeClipboard = (html, text) => { CLIP.push({ html, text }); return CLIP_OK.ok; };

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

// Two + starts and one −; a die reached from + only, one from − only, one from both. The answer's reach is the server's.
const SIGNED = {
  nodes: [
    { id: 's:a', type: 'wafer@1', label: 'A', depth: 0, keys: { wafer: 'A' } },
    { id: 's:c', type: 'wafer@1', label: 'C', depth: 0, keys: { wafer: 'C' } },
    { id: 's:b', type: 'wafer@1', label: 'B', depth: 0, keys: { wafer: 'B' } },
    { id: 'd:1', type: 'die@1', label: 'D-1', depth: 1, keys: { mat_id: 'M-1' } },
    { id: 'd:2', type: 'die@1', label: 'D-2', depth: 1, keys: { mat_id: 'M-2' } },
    { id: 'd:3', type: 'die@1', label: 'D-3', depth: 2, keys: { mat_id: 'M-3' } },
    { id: 'd:4', type: 'die@1', label: 'D-4', depth: 1, keys: { mat_id: 'M-4' } },
  ],
  edges: [{ id: 'e:a3', source: 's:a', target: 'd:3', predicate: 'inspected', qualifiers: { gate: 7, note: null } },
    { id: 'e:b3', source: 's:b', target: 'd:3', predicate: 'inspected', qualifiers: { gate: 9, note: null } },
    { id: 'e:a4', source: 's:a', target: 'd:4', predicate: 'inspected', qualifiers: { gate: 1, note: null } },
    { id: 'e:c4', source: 's:c', target: 'd:4', predicate: 'inspected', qualifiers: { gate: 2, note: null } }],
  propagation: { ranked: [{ id: 'd:1', reach: [2, 0] }, { id: 'd:2', reach: [0, 1] },
    { id: 'd:3', reach: [1, 1], evidence: [{ seed: 's:a', sign: '+', hops: [{ id: 's:a' }, { id: 'd:3', predicates: ['inspected'] }] },
      { seed: 's:b', sign: '-', hops: [{ id: 's:b' }, { id: 'd:3', predicates: ['inspected'] }] }] },
    { id: 'd:4', reach: [2, 0], evidence: [{ seed: 's:a', sign: '+', hops: [{ id: 's:a' }, { id: 'd:4', predicates: ['inspected'] }] },
      { seed: 's:c', sign: '+', hops: [{ id: 's:c' }, { id: 'd:4', predicates: ['inspected'] }] }] }] },
};
const SIGNED_STARTS = { positive: ['s:a', 's:c'], negative: ['s:b'] };
// Route (lead df11f9e81, 10-10): a base wafer (+ start) whose die a core die is bonded from; the core wafer reached
// through it; a − wafer whose die measures the same quantity. The measurement an edge (scheme A) or an event node
// (scheme B). Each node's ranked row carries the paths the server walked to it (its evidence), as an answer does.
const bn = (id, type, keys = {}) => ({ id, type, label: id.toUpperCase(), depth: 0, keys });
const be = (source, predicate, target, qualifiers) => ({ id: `${source}>${predicate}>${target}`, source, target, predicate, ...(qualifiers ? { qualifiers } : {}) });
const BOND_NODES = [bn('w:b', 'wafer@1', { wafer: 'B' }), bn('w:c', 'wafer@1', { wafer: 'C' }), bn('w:n', 'wafer@1', { wafer: 'N' }),
  bn('d:b', 'die@1', { mat_id: 'B-1' }), bn('d:c', 'die@1', { mat_id: 'C-1' }), bn('d:n', 'die@1', { mat_id: 'N-1' }), bn('q:1', 'quantity@1')];
const BOND_EDGES = [be('d:b', 'in_container', 'w:b'), be('d:c', 'in_container', 'w:c'), be('d:c', 'bonded_from', 'd:b'),
  be('d:n', 'in_container', 'w:n')];
const walked = (seed, sign, ...hops) => ({ seed, sign, hops: [{ id: seed }, ...hops.map(([id, ...predicates]) => ({ id, predicates }))] });
const FROM_B = [['d:b', 'in_container'], ['d:c', 'bonded_from'], ['w:c', 'in_container']];
const BOND_PATHS = { 'd:b': [walked('w:b', '+', FROM_B[0])], 'd:c': [walked('w:b', '+', ...FROM_B.slice(0, 2))],
  'w:c': [walked('w:b', '+', ...FROM_B)], 'd:n': [walked('w:n', '-', ['d:n', 'in_container'])],
  'q:1': [walked('w:b', '+', ['q:1', 'measures']), walked('w:n', '-', ['d:n', 'in_container'], ['q:1', 'measures'])] };
const BOND_REACH = { 'd:b': [1, 0], 'd:c': [1, 0], 'w:c': [1, 0], 'd:n': [0, 1], 'q:1': [1, 1] };
const bondRanked = (more = {}, paths = {}) => ({ ranked: Object.entries({ ...BOND_REACH, ...more })
  .map(([id, reach]) => ({ id, reach, evidence: { ...BOND_PATHS, ...paths }[id] || [] })) });
const BOND_EDGE = { nodes: BOND_NODES,
  edges: [...BOND_EDGES, be('w:b', 'measures', 'q:1', { value: 1 }), be('d:n', 'measures', 'q:1', { value: 2 })], propagation: bondRanked() };
const BOND_EVENT = { nodes: [...BOND_NODES, bn('m:1', 'measurement@1'), bn('m:2', 'measurement@1')],
  edges: [...BOND_EDGES, be('w:b', 'measured', 'm:1'), be('m:1', 'of', 'q:1'), be('d:n', 'measured', 'm:2'), be('m:2', 'of', 'q:1')],
  propagation: bondRanked({ 'm:1': [1, 0], 'm:2': [0, 1] }, { 'm:1': [walked('w:b', '+', ['m:1', 'measured'])],
    'm:2': [walked('w:n', '-', ['d:n', 'in_container'], ['m:2', 'measured'])],
    'q:1': [walked('w:b', '+', ['m:1', 'measured'], ['q:1', 'of']), walked('w:n', '-', ['d:n', 'in_container'], ['m:2', 'measured'], ['q:1', 'of'])] }) };
const BOND_STARTS = { positive: ['w:b'], negative: ['w:n'] };
const BONDING = 'in_container → bonded_from → in_container';
// The core die also stacked on a second base die: the server walked two paths to the core wafer.
const BOND_TWO = { ...BOND_EDGE, nodes: [...BOND_EDGE.nodes, bn('d:b2', 'die@1', { mat_id: 'B-2' })],
  edges: [...BOND_EDGE.edges, be('d:b2', 'in_container', 'w:b'), be('d:c', 'stacked_on', 'd:b2')],
  propagation: bondRanked({ 'd:b2': [1, 0] }, { 'd:b2': [walked('w:b', '+', ['d:b2', 'in_container'])],
    'w:c': [walked('w:b', '+', ...FROM_B), walked('w:b', '+', ['d:b2', 'in_container'], ['d:c', 'stacked_on'], ['w:c', 'in_container'])] }) };
const STACKING = 'in_container → stacked_on → in_container';
// C (lead 99ed68cb7): the core wafer measures the quantity too - who gave each value, under it.
const BOND_SRC = { ...BOND_EDGE, edges: [...BOND_EDGE.edges, be('w:c', 'measures', 'q:1', { value: 3 })] };
const BOND_SRC_EVENT = { ...BOND_EVENT,
  nodes: [...BOND_EVENT.nodes.map((n) => (/^m:/.test(n.id) ? { ...n, attributes: { value: n.id === 'm:1' ? 1 : 2 } } : n)),
    { ...bn('m:3', 'measurement@1'), attributes: { value: 3 } }],
  edges: [...BOND_EVENT.edges, be('w:c', 'measured', 'm:3'), be('m:3', 'of', 'q:1')],
  propagation: { ranked: [...BOND_EVENT.propagation.ranked, { id: 'm:3', reach: [1, 0],
    evidence: [walked('w:b', '+', ...FROM_B, ['m:3', 'measured'])] }] } };
const OF_VALUE = new Map([['quantity@1', [{ steps: [{ predicate: 'of', direction: 'incoming' }], value: { on: 'node', name: 'value' },
  words: ['of (in)', 'value'] }]]]);
const SRC_18766 = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'walk_value_source_18766.json'), 'utf8'));
// The demo's usual form, collect quantity alone (lead 10-11): the wafers that gave bond_temp's values are not in nodes.
const SRC_COLLECT = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'walk_value_source_collect_18766.json'), 'utf8'));
// E1 (lead 10-10): one step from bond_temp on 18766 - what a Next from its row sends, and its declaration's two types.
const NEXT_18766 = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'walk_next_18766.json'), 'utf8'));
// The flat table's two node-own columns, carried into the walk table's centre (lead 10-11), on walk_route_fill's own
// declarations: a type that declares attributes stands «Conflicts»; a predicate confirmed by another stands its column.
const CARRY_DECL = { ok: true, entities: [{ type: 'die@1', keys: ['mat_id'], attributes: ['grade'] }, { type: 'wafer@1', keys: ['wafer'] }],
  predicates: [{ name: 'observed', absence_confirmed_by: 'inspected' }, { name: 'inspected' }] };
const CARRY = { nodes: [
  { id: 'k:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' }, attribute_conflicts: 2, absence: { observed: { verdict: 'unknown', why: 'not_examined' } } },
  { id: 'k:2', type: 'die@1', label: 'D-2', keys: { mat_id: 'M-2' }, attribute_conflicts: 0 }], edges: [] };
// D (lead 99ed68cb7): CONTROL · B walked once more from the same baskets. 18766 from «void»: A the 12, B leads_to.
const CTL_18766 = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'walk_control_18766.json'), 'utf8'));
const CTL_STARTS = { positive: [CTL_18766.a.seed.id], negative: [] };
// B on the signed answer: d:3 from + (A reached it from both), and d:5 from − through w:5, a wafer only B reached.
const CTL_SIGNED = {
  nodes: [...SIGNED.nodes.filter((n) => ['s:a', 's:c', 's:b', 'd:3'].includes(n.id)),
    { id: 'w:5', type: 'wafer@1', label: 'W-5', depth: 1, keys: { wafer: 'W5' } },
    { id: 'd:5', type: 'die@1', label: 'D-5', depth: 2, keys: { mat_id: 'M-5' } }],
  edges: [{ id: 'b:c3', source: 's:c', target: 'd:3', predicate: 'leads_to' }, { id: 'b:b5', source: 's:b', target: 'w:5', predicate: 'leads_to' },
    { id: 'b:55', source: 'w:5', target: 'd:5', predicate: 'inspected', qualifiers: { gate: 4, note: null } }],
  propagation: { ranked: [{ id: 'd:3', reach: [1, 0], evidence: [walked('s:c', '+', ['d:3', 'leads_to'])] },
    { id: 'w:5', reach: [0, 1], evidence: [walked('s:b', '-', ['w:5', 'leads_to'])] },
    { id: 'd:5', reach: [0, 1], evidence: [walked('s:b', '-', ['w:5', 'leads_to'], ['d:5', 'inspected'])] }] },
};
// A cell's values, as drawn: its value lines (C draws a source line under each).
const valsOf = (c) => ((c && c.children) || []).filter((k) => k.className === 'wk-val').map((k) => k._text).join(' · ');
const srcsOf = (c) => ((c && c.children) || []).filter((k) => k.className === 'wk-src').map((k) => k._text);
const GATE_IN = 'inspected (in) · gate';
const NOTE_IN = 'inspected (in) · note';
const ALL = 'd:1,d:2,d:3,d:4,s:a,s:b,s:c';

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

const has = (e, cls) => String(e.className || '').split(/\s+/).includes(cls);
const TABLE = await import('../src/walk/table_view.js');

async function suite(mod) {
  const { host } = await render(mod);
  const view = walkTableView(RESULT, DECL.entities);

  console.log(`${LF}-- the page draws the view's answer, not its own --`);
  eq('V1 one section head per section, worded by the view',
    byClass(host, 'wk-sechead').map((e) => e.textContent).join(' | '),
    view.sections.map((s) => s.heading).join(' | '));
  // The walk table (E1: the flat table retired): a section's last head row is its centre then its side's columns; a
  // row's cells the same, a side cell drawn as its value line.
  const headRows = byTag(host, 'thead').map((t) => t.children[t.children.length - 1]);
  const drawn = byTag(host, 'tbody').flatMap((b) => b.children.map((tr) => tr.children.filter((c) => c.className !== 'wk-check')));
  const said = (c) => (has(c, 'wk-centre') ? c.textContent : valsOf(c));
  eq('V2 the column labels are the view\'s, in the view\'s order',
    headRows.map((tr) => tr.children.filter((c) => c.className !== 'wk-check').map((c) => c.textContent).join(',')).join(' | '),
    view.sections.map((s) => [...s.centreHeads, ...s.parts.map((x) => x.leaf)].join(',')).join(' | '));
  eq('V3 every cell is the view\'s text, in the view\'s order',
    drawn.map((cells) => cells.map(said).join('|')).join(' / '),
    view.sections.flatMap((s) => s.rows.map((r) => [...r.centre, ...r.byGroup[0]].map((c) => c.text).join('|'))).join(' / '));
  // 🔴 0 IS A VALUE. `x: 0` in the fixture is the discriminant: a renderer using `v || ''`
  //    draws it as the same mark an absent key gets, and the row then lies about the die.
  ok('V4 a zero is drawn as 0 and an absent key as «—», not as the same glyph',
    drawn.flat().map(said).includes('0') && drawn.flat().map(said).includes(TABLE.EMPTY), drawn.flat().map(said).join('|'));
  eq('V5 the numeric class follows the view\'s reading of each cell',
    drawn.map((cells) => cells.filter((c) => !has(c, 'wk-centre')).map((c) => (has(c, 'wk-num') ? 1 : 0)).join('')).join(' / '),
    view.sections.flatMap((s) => s.rows.map((r) => r.byGroup[0].map((c) => (c.numeric ? 1 : 0)).join(''))).join(' / '));
  // ⚰️ V6 (the id cell's own class) retired with the flat table (E1): the id is behind the copy press (Z16).

  console.log(`${LF}-- the cap is a number the screen SAYS --`);
  const many = { nodes: Array.from({ length: 203 }, (_, i) => (
    { id: `m:${i}`, type: 'die@1', label: `L${i}`, keys: {} })), edges: [] };
  const { host: capped } = await render(mod, many);
  const capView = walkTableView(many, DECL.entities);
  // ⚠️ THE PAGE HAS OTHER NOTES. Scoping by class alone caught the form's two and made
  //    「no note」 unfalsifiable; the cap note is the one that says so.
  const capNotes = (h) => byClass(h, 'wk-note').map((e) => e.textContent)
    .filter((t) => t.includes('not drawn'));
  eq('C1 over the cap the view hides exactly what did not fit', capView.hidden, 3);
  eq('C2 and the screen prints THAT number',
    capNotes(capped).join(' / '), '3 more not drawn');
  ok('C3 the total is not what is printed, since 203 would read as all of it being hidden',
    !capNotes(capped).some((t) => t.includes('203')), capNotes(capped).join(' / '));
  const { host: exact } = await render(mod, { nodes: RESULT.nodes, edges: [] });
  eq('C4 under the cap there is no cap note -- the absence is the answer',
    capNotes(exact).length, 0);

  console.log(`${LF}-- signed starts and checks, the board's way (lead 10-09) --`);
  {
    const DECLS = { ok: true,
      entities: [{ type: 'die@1', keys: ['mat_id'] }, { type: 'wafer@1', keys: ['wafer'] }],
      predicates: [{ name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } }] };
    const asked = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      if (u.includes('/subgraph')) asked.push(u);
      return { ok: true, status: 200, json: async () => (u.includes('/subgraph') ? RESULT : DECLS) };
    } });
    await settle();
    const go = () => walkAll(host).find((e) => e.className === 'wk-go');
    const click = (e, event = {}) => { for (const fn of (e && e.listeners.click) || []) fn(event); };
    const query = (u) => new URLSearchParams((u || '').split('?')[1] || '');
    // The starts go in the baskets (lead bc63378e5): A by Positive's +, B by Negative's +, then Walk.
    const basket = (sign) => walkAll(host).find((e) => e.attrs && e.attrs['data-sign'] === sign && e.className.startsWith('wk-basket'));
    const plus = (sign) => click(walkAll(basket(sign) || { children: [] }).find((e) => e.className === 'wk-basketadd'));
    handle.state.type = 'wafer@1';
    handle.state.keys = { wafer: 'A' };
    plus('+');
    handle.state.keys = { wafer: 'B' };
    plus('−');
    click(go());
    await settle();
    const starts = handle.graph.markings.entries('walk-start');
    const q = query(asked[asked.length - 1]);
    ok('S1 the baskets are the starts - A in Positive as +, B in Negative as -; Walk asks both',
      starts.length === 2 && starts[0][1] === SIGN.CASE && starts[1][1] === SIGN.CONTROL
        && q.getAll('positive').join() === starts[0][0] && q.getAll('negative').join() === starts[1][0],
      JSON.stringify({ starts, q: q.toString().slice(0, 200) }));
    const said = ['+', '−'].map((sign) => walkAll(basket(sign) || { children: [] })
      .filter((e) => e.className === 'wk-basketlabel').map((e) => e.textContent).join());
    ok('S2 each basket names its starts', JSON.stringify(said) === JSON.stringify(['A', 'B']), JSON.stringify(said));
    const box = (id) => walkAll(host).find((e) => e.attrs && e.attrs['data-row'] === id);
    click(box('n:1'), { shiftKey: true });
    click(box('n:2'));
    const row1 = walkAll(host).find((e) => e.tagName === 'tr' && e.children.includes(walkAll(host).find((c) => c.className === 'wk-check' && c.children.includes(box('n:1')))));
    ok('S3 a Shift click checks a row as a control, drawn as one; a click checks it as +',
      handle.graph.markings.signOf(handle.state.marks, 'n:1') === SIGN.CONTROL && handle.graph.markings.signOf(handle.state.marks, 'n:2') === SIGN.CASE
        && Boolean(row1) && row1.className === 'is-control' && box('n:1').checked === true,
      JSON.stringify(handle.graph.markings.entries(handle.state.marks)));
    const before = asked.length;
    click(walkAll(host).find((e) => e.className === 'wk-next-edge'));
    await settle();
    const n = query(asked[before]);
    ok('S4 Next walks on from the + rows with the - rows as negative',
      asked.length === before + 1 && n.getAll('positive').join() === 'n:2' && n.getAll('negative').join() === 'n:1',
      n.toString().slice(0, 200));
  }

  console.log(`${LF}-- the server's sentence in the head (lead b5cdcbc75) --`);
  {
    const said = async (result) => {
      const { host, handle } = await render(mod, result);
      handle.state.asked = { type: 'die@1', keys: {} };
      handle.render();
      return [byClass(host, 'wk-note wk-said').map((e) => e.textContent), byClass(host, 'wk-note').filter((e) => e.textContent === 'No node reached').length];
    };
    const empty = await said({ state: 'empty', message: 'No ledger evidence is connected to the selected node',
      nodes: [RESULT.nodes[0]], edges: [] });
    const none = await said({ state: 'empty', message: 'This walk reached no node beyond its seeds', nodes: [], edges: [] });
    const plain = await said(RESULT);
    ok('H1 the head says the server\'s state and sentence - one node and «empty» is not a node with no data; with none, '
      + 'its sentence once; a plain answer, nothing',
      JSON.stringify([empty, none, plain]) === JSON.stringify([[['empty · No ledger evidence is connected to the selected node'], 0],
        [['empty · This walk reached no node beyond its seeds'], 0], [[], 0]]),
      JSON.stringify([empty, none, plain]));
  }

  console.log(`${LF}-- E1: one basket walked = a Next from that row (owner 10-10) --`);
  {
    const asked = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      if (u.includes('/subgraph')) asked.push(u);
      const first = u.includes('/subgraph') && !u.includes('follow=measures');
      return { ok: true, status: 200, json: async () => (!u.includes('/subgraph') ? NEXT_18766._decl : first ? SRC_18766 : NEXT_18766) };
    } });
    await settle();
    const click = (e, event = {}) => { for (const fn of (e && e.listeners.click) || []) fn(event); };
    const basketAdd = () => walkAll(walkAll(host).find((e) => e.attrs && e.attrs['data-sign'] === '+' && e.className.startsWith('wk-basket')) || { children: [] })
      .find((e) => e.className === 'wk-basketadd');
    const tableOf = () => walkAll(host).filter((e) => e.className === 'wk-sec').map((sec) => [sec.children[0].textContent,
      ...walkAll(sec).filter((e) => e.tagName === 'tr').map((tr) => tr.children.filter((c) => c.className !== 'wk-check')
        .map((c) => (has(c, 'wk-centre') ? c.textContent : valsOf(c) || c.textContent)).join('|'))]);
    const query = (u) => new URLSearchParams((u || '').split('?')[1] || '');
    // One + start alone goes by its seed id (walk_layout L7 L8), a Next's by positive: the same start either way.
    const shape = (u) => [`start=${query(u).getAll('positive').join(',') || query(u).get('id')}`,
      ...['follow', 'collect', 'direction', 'hops', 'node_limit', 'fanout_limit'].map((k) => `${k}=${query(u).getAll(k).join(',')}`)].join('&');
    const bodyRows = (sec) => walkAll(sec).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).length;
    const headOf = (sec) => (walkAll(sec).filter((e) => e.tagName === 'thead').map((t) => t.children[t.children.length - 1])[0] || { children: [] })
      .children.filter((c) => c.className !== 'wk-check').map((c) => c.textContent);
    const q = NEXT_18766.seed;
    // (a) bond_temp alone in +, the form set to the step a Next takes.
    handle.state.type = 'quantity';
    handle.state.keys = { ...q.keys };
    click(basketAdd());
    handle.state.follow = new Set(['measures']);
    handle.state.collect = new Set(['wafer']);
    handle.state.direction = 'both';
    handle.state.hops = '1';
    handle.state.fanoutLimit = '7';
    click(walkAll(host).find((e) => e.className === 'wk-go'));
    await settle();
    const a = tableOf();
    const askA = asked[asked.length - 1];
    const waferSec = walkAll(host).filter((e) => e.className === 'wk-sec').find((sec) => /^wafer/.test(sec.children[0].textContent));
    const [wafers, head] = waferSec ? [bodyRows(waferSec), headOf(waferSec)] : [0, []];
    // (b) the C answer's base wafer alone in +, Walk; bond_temp's row checked; Next measures → wafer.
    const base = SRC_18766._starts.positive[0];
    handle.state.type = 'wafer';
    handle.state.keys = { wafer: SRC_18766.nodes.find((n) => n.id === base).keys.wafer };
    handle.graph.markings.clear('walk-start');
    click(basketAdd());
    handle.state.follow = new Set();
    handle.state.collect = new Set();
    // The form's hops is the first walk's; a Next is one step (lead 10-11).
    handle.state.hops = '3';
    click(walkAll(host).find((e) => e.className === 'wk-go'));
    await settle();
    click(walkAll(host).find((e) => e.attrs && e.attrs['data-row'] === q.id));
    click(walkAll(host).find((e) => e.className === 'wk-next-edge' && e.textContent === 'measures → wafer'));
    await settle();
    const b = tableOf();
    const askB = asked[asked.length - 1];
    ok('EA1 18766: bond_temp alone in + and Walk draws the table a Next from its row draws - same head, rows, columns, cells; 64 wafers, measures value · eqp_id · role · step, Route; the same ask, the form\'s node_limit and fanout_limit on both, the Next\'s hops its step\'s (owner 10-10, lead 10-11)',
      a.length > 0 && JSON.stringify(a) === JSON.stringify(b) && wafers === 64 && shape(askA) === shape(askB)
        && shape(askA) === `start=${q.id}&follow=measures&collect=wafer&direction=both&hops=1&node_limit=${mod.NODE_LIMIT}&fanout_limit=7`
        && ['value', 'eqp_id', 'role', 'step', 'Route'].every((h) => head.includes(h)) && head[0] === 'wafer',
      JSON.stringify({ a: a.map((sec) => sec.slice(0, 5)), b: b.map((sec) => sec.slice(0, 5)), wafers, head, askA: shape(askA), askB: shape(askB) }));
  }

  console.log(`${LF}-- the type placeholder is no type (lead b417e2ad8) --`);
  {
    const asked = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '',
      fetchImpl: async (url) => { asked.push(String(url)); return { ok: true, status: 200, json: async () => DECL }; } });
    await settle();
    // The page's own control, as the browser drives it: the select takes the picked option's value.
    const pick = (at) => {
      const sel = byClass(host, 'wk-select')[0];
      if (!sel) return;
      sel.value = at(sel.children).value;
      for (const fn of sel.listeners.change || []) fn();
    };
    pick((opts) => opts.find((o) => o.value === 'die@1'));
    await settle();
    const subjects = () => asked.filter((u) => u.includes('/key-values')).length;
    const onType = subjects();
    pick((opts) => opts[0]);
    await settle();
    const go = byClass(host, 'wk-go')[0];
    ok('P1 picking the placeholder again: no type, Run is off, no subject list is asked',
      onType === 1 && handle.state.type === '' && go && go.disabled === true && subjects() === onType,
      `${onType} ${JSON.stringify(handle.state.type)} ${go && go.disabled} ${subjects()}`);
  }

  console.log(`${LF}-- a walk may start from a node that only appears as an object (29cee1d47) --`);
  {
    // Shapes and classes from the shipped sample: recipe@1 is a static object-only type, defect@1
    // an object-only type that is not static, die@1 on both sides.
    const DECL2 = { ok: true,
      entities: [{ type: 'die@1', keys: ['mat_id'] }, { type: 'wafer@1', keys: ['wafer'] },
        { type: 'recipe@1', keys: ['recipe'], class: ['static'] }, { type: 'defect@1', keys: ['defect'] },
        { type: 'note@1', keys: ['note'] }],
      predicates: [
        { name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } },
        { name: 'processed_with@1', subjects: ['wafer@1'], object: { types: ['recipe@1'] } },
        { name: 'observed@1', subjects: ['die@1'], object: { types: ['defect@1'] } }] };
    const stand = async (keyValues) => {
      const doc = makeDoc();
      const host = doc.createElement('div');
      mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => ({ ok: true, status: 200,
        json: async () => (String(url).includes('/key-values') ? keyValues : DECL2) }) });
      await settle();
      const sel = byClass(host, 'wk-select')[0];
      return { host, pick: async (type) => {
        sel.value = type;
        for (const fn of sel.listeners.change || []) fn();
        await settle();
      } };
    };
    const follow = (h) => walkAll(h).filter((e) => e.attrs && e.attrs['data-follow'] !== undefined)
      .map((e) => e.attrs['data-follow']).join(',');
    const notes = (h) => byClass(h, 'wk-note').map((e) => e.textContent).join(' / ');

    const listed = await stand({ nodes: [{ keys: { recipe: 'R-1' }, count: 3 }], scanned: 1,
      scan_truncated: false, values_truncated: false });
    await listed.pick('recipe@1');
    // The box (lead bccbdd601), focused as the browser does: its rows are the server's nodes, keys and count.
    const boxIn = walkAll(listed.host).find((e) => e.attrs && e.attrs.role === 'combobox');
    for (const fn of (boxIn && boxIn.listeners.focus) || []) fn({});
    const offered = byClass(listed.host, 'wk-searchitem').map((e) => e.children.map((c) => c.textContent).join(' '));
    ok('F2 the seed field is Pick a node and its box, focused, offers the node the server listed',
      walkAll(listed.host).some((e) => e.className === 'wk-label' && e.textContent === 'Pick a node')
        && offered.includes('R-1 3 atoms'), offered.join(' | '));
    // 🔴 EVERY DECLARED PREDICATE, WHATEVER THE TYPE (owner 10-06, lead bf3653401) — the walk filters, not the list.
    const ALL = DECL2.predicates.map((p) => p.name).join(',');
    eq('F6 static recipe@1 draws every declared predicate', follow(listed.host), ALL);
    await listed.pick('note@1');
    eq('F7 a type no predicate touches still draws every declared predicate', follow(listed.host), ALL);
    await listed.pick('defect@1');
    eq('F1 defect@1 draws every declared predicate, those that do not touch it too',
      follow(listed.host), ALL);
    // 🔴 A TYPE CHANGE KEEPS EVERY TICK (lead 10-06, reversing 10-02): every box is drawn, so no tick is hidden.
    //    The frozen R&D box still drops what does not touch the new type (its harness, H3).
    const tick = (h, name) => {
      const row = walkAll(h).find((e) => e.attrs && e.attrs['data-follow'] === name);
      const cb = row && row.children.find((c) => c.tagName === 'input');
      for (const fn of (cb && cb.listeners.change) || []) fn();
    };
    const ticked = (h) => walkAll(h).filter((e) => e.attrs && e.attrs['data-follow'] !== undefined
      && e.children.some((c) => c.tagName === 'input' && c.checked)).map((e) => e.attrs['data-follow']).join(',');
    await listed.pick('die@1');
    tick(listed.host, 'inspected@1');
    const before = ticked(listed.host);
    await listed.pick('recipe@1');
    const dropped = ticked(listed.host);
    tick(listed.host, 'processed_with@1');
    await listed.pick('wafer@1');
    ok('F8 changing the type keeps every tick, those that do not touch the new type too',
      before === 'inspected@1' && dropped === 'inspected@1' && ticked(listed.host) === 'inspected@1,processed_with@1',
      `${before} / ${dropped} / ${ticked(listed.host)}`);
    await listed.pick('die@1');
    // The page half of the board harness's old B8 (lead 10-06): every declared type, every declared predicate.
    const apart = [];
    for (const { type } of DECL2.entities) {
      await listed.pick(type);
      if (follow(listed.host) !== ALL) apart.push(`${type}: ${follow(listed.host)}`);
    }
    ok('F9 every declared type draws every declared predicate', apart.length === 0, apart.join(' ; '));
    await listed.pick('die@1');
    eq('F3 die@1 draws every declared predicate, in declaration order',
      follow(listed.host), 'inspected@1,processed_with@1,observed@1');

    const empty = await stand({ nodes: [], scanned: 0, scan_truncated: false, values_truncated: false });
    await empty.pick('recipe@1');
    ok('F4 read and empty says there is no node of the type',
      notes(empty.host).includes('No node of this type in the ledger'), notes(empty.host));
    const cut = await stand({ nodes: [], scanned: 1001, scan_truncated: true, values_truncated: false });
    await cut.pick('recipe@1');
    ok('F5 not read to the end says how many nodes were read',
      notes(cut.host).includes('Not every node read (up to 1001)'), notes(cut.host));
  }

  console.log(`${LF}-- the table walks on from its checked rows along a declared edge (lead 53050a4ec) --`);
  {
    // A predicate within a type (bonded_to die -> die) as well as across: the list is the declaration's, both kinds.
    const DECL3 = { ok: true,
      entities: [{ type: 'die@1', keys: ['mat_id'] }, { type: 'wafer@1', keys: ['wafer'] }],
      predicates: [
        { name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } },
        { name: 'bonded_to@1', subjects: ['die@1'], object: { types: ['die@1'] } }] };
    const START = { nodes: [
      { id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' } },
      { id: 'n:2', type: 'die@1', label: 'D-2', keys: { mat_id: 'M-2' } }], edges: [] };
    const STEP = { nodes: [{ id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' } },
      { id: 'n:4', type: 'die@1', label: 'D-4', keys: { mat_id: 'M-4' } }],
    edges: [{ id: 'e:4', source: 'n:1', target: 'n:4', predicate: 'bonded_to@1' }], truncated: null };
    const asked = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      if (u.includes('/subgraph')) asked.push(u);
      return { ok: true, status: 200, json: async () => (u.includes('/subgraph') ? STEP : DECL3) };
    } });
    await settle();
    handle.state.type = 'die@1';
    handle.state.asked = { type: 'die@1', keys: { mat_id: 'M-1' } };
    handle.state.run = 'done';
    handle.state.result = START;
    handle.render();
    const edges = (h) => walkAll(h).filter((e) => e.className === 'wk-next-edge');
    const press = (e) => { for (const fn of (e && e.listeners.click) || []) fn(); };
    const tick = (h, id) => {
      const cb = walkAll(h).find((e) => e.attrs && e.attrs['data-row'] === id);
      for (const fn of (cb && cb.listeners.click) || []) fn({});
    };
    const steps = (h) => walkAll(h).filter((e) => /^wk-step( is-on)?$/.test(e.className || ''));
    const rowsShown = (h) => walkAll(h).filter((e) => e.attrs && e.attrs['data-row']).map((e) => e.attrs['data-row']);
    eq('N1 the Next of the die section is the declaration\'s edges one step from die@1, both kinds',
      edges(host).map((e) => e.textContent).join(' | '), 'inspected@1 → wafer@1 | bonded_to@1 → die@1');
    press(edges(host)[1]);
    await settle();
    ok('N2 nothing checked: every edge is off with its reason, and a press asks nothing',
      edges(host).length === 2 && edges(host).every((e) => e.disabled === true && e.attrs.title === 'Check rows first')
        && asked.length === 0, `${edges(host).map((e) => e.disabled)} ${asked.length}`);
    tick(host, 'n:1');
    const marked = handle.graph.markings.signOf('walk-2', 'n:1');
    ok('N3 a checked row is the page\'s marking the graph reads (walk-2), and the edges come on',
      marked === SIGN.CASE && edges(host).every((e) => e.disabled === false), String(marked));
    press(edges(host).find((e) => e.textContent === 'bonded_to@1 → die@1'));
    await settle();
    const q = new URLSearchParams((asked[0] || '').split('?')[1] || '');
    ok('N4 a press walks one step from the checked row alone, along that edge to its type',
      asked.length === 1 && q.getAll('positive').join() === 'n:1' && q.getAll('follow').join() === 'bonded_to@1'
        && q.getAll('collect').join() === 'die@1' && q.get('hops') === '1' && q.get('direction') === 'both',
      asked[0]);
    ok('N5 the step stacks: Step 2 lit, and the table is that step\'s answer',
      steps(host).length === 2 && steps(host)[1].className === 'wk-step is-on'
        && steps(host)[1].textContent === 'Step 2 · bonded_to@1 → die@1' && rowsShown(host).join() === 'n:1,n:4',
      `${steps(host).map((s) => s.textContent)} ${rowsShown(host)}`);
    tick(host, 'n:4');
    press(edges(host).find((e) => e.textContent === 'bonded_to@1 → die@1'));
    await settle();
    const third = steps(host).length;
    press(steps(host)[0]);
    ok('N6 a second step stacks a third; Step 1 shows the first table again and the chain stays',
      third === 3 && steps(host).length === 3 && steps(host)[0].className === 'wk-step is-on'
        && rowsShown(host).join() === 'n:1,n:2', `${third} ${rowsShown(host)}`);
    // F (lead 77f1afd3b): five steps on - each its own marking, checks and Next at the fifth; step two walked again drops
    // the steps after it and their markings.
    const NAMES = () => handle.state.steps.map((x) => x.marks);
    press(steps(host)[steps(host).length - 1]);
    for (let k = 0; k < 3; k += 1) {
      tick(host, 'n:4');
      press(edges(host).find((e) => e.textContent === 'bonded_to@1 → die@1'));
      await settle();
    }
    tick(host, 'n:4');
    const fifth = [handle.state.steps.length, handle.state.at, steps(host).length, NAMES().length === new Set(NAMES()).size,
      handle.graph.markings.signOf(NAMES()[4], 'n:4'), edges(host).every((e) => e.disabled === false),
      handle.graph.chain(7) !== '' && !NAMES().includes(handle.graph.chain(7))];
    ok('CH1 five steps on: each its own marking - checked at the fifth, Next on, the graph\'s chain goes on past them (lead 77f1afd3b)',
      JSON.stringify(fifth) === JSON.stringify([5, 5, 6, true, SIGN.CASE, true, true]), JSON.stringify([fifth, NAMES()]));
    const later = NAMES().slice(1);
    press(steps(host)[1]);
    tick(host, 'n:1');
    press(edges(host).find((e) => e.textContent === 'bonded_to@1 → die@1'));
    await settle();
    ok('CH2 step two walked on again: the steps after it go and so do their markings; the new step a name never used',
      handle.state.steps.length === 2 && later.every((name) => handle.graph.markings.count(name) === 0)
        && !later.includes(NAMES()[1]) && NAMES()[1] !== '',
      JSON.stringify([handle.state.steps.length, later.map((name) => handle.graph.markings.count(name)), NAMES()]));
    handle.state.view = 'table';
    handle.state.keys = { mat_id: 'M-1' };
    handle.baskets.add(SIGN.CASE);
    void handle.fire();
    await settle();
    ok('N7 a new start clears the steps and what their checks wrote',
      steps(host).length === 0 && handle.graph.markings.count('walk-2') === 0 && handle.state.steps.length === 0,
      `${steps(host).length} ${handle.graph.markings.count('walk-2')}`);

    // A predicate whose subject and object are one type, on real server answers (capture_walk_bundles.py): the
    // server answers each direction as it was asked, so a Next that walks one way only brings one side (lead 11e5ea207).
    const SAME = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'walk_step_same_type.json'), 'utf8'));
    const sameAsked = [];
    const sameHost = doc.createElement('div');
    const same = mod.boot(doc, sameHost, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      if (!u.includes('/subgraph')) return { ok: true, status: 200, json: async () => SAME._declaration };
      sameAsked.push(u);
      const body = SAME._answers[new URLSearchParams(u.split('?')[1] || '').get('direction')];
      return body ? { ok: true, status: 200, json: async () => body } : { ok: false, status: 422, json: async () => ({}) };
    } });
    await settle();
    const startNode = SAME._answers.both.nodes.find((n) => n.id === SAME._start.id);
    same.state.type = SAME._start.type;
    same.state.asked = { type: SAME._start.type, keys: { ...SAME._start.keys } };
    same.state.run = 'done';
    same.state.result = { nodes: [startNode], edges: [] };
    same.render();
    tick(sameHost, SAME._start.id);
    press(edges(sameHost).find((e) => e.textContent === `${SAME._predicate} → ${SAME._start.type}`));
    await settle();
    const sideOf = (d) => new Set(SAME._answers[d].nodes.map((n) => n.id).filter((id) => id !== SAME._start.id));
    const [outSide, inSide] = [sideOf('outgoing'), sideOf('incoming')];
    const sameRows = rowsShown(sameHost);
    ok('N8 a same-type predicate: the Next brings both sides - what it leads to and what leads to it',
      [...outSide].some((id) => !inSide.has(id)) && [...inSide].some((id) => !outSide.has(id))
        && sameAsked.length === 1 && JSON.stringify([...sameRows].sort())
          === JSON.stringify([SAME._start.id, ...outSide, ...inSide].sort()),
      `${sameAsked.length} ${sameRows.length} out ${outSide.size} in ${inSide.size}`);
  }
  // ── G (lead 5ea461e04): the steps a tree - from one step an edge A, then an edge B; A again ──
  {
    const DECLG = { ok: true,
      entities: [{ type: 'die@1', keys: ['mat_id'] }, { type: 'wafer@1', keys: ['wafer'] }],
      predicates: [
        { name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } },
        { name: 'bonded_to@1', subjects: ['die@1'], object: { types: ['die@1'] } }] };
    const ROOTG = { nodes: [{ id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' } },
      { id: 'n:2', type: 'die@1', label: 'D-2', keys: { mat_id: 'M-2' } }], edges: [] };
    const BY = {
      'bonded_to@1': { nodes: [{ id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' } }, { id: 'n:4', type: 'die@1', label: 'D-4', keys: { mat_id: 'M-4' } }],
        edges: [{ id: 'e:4', source: 'n:1', target: 'n:4', predicate: 'bonded_to@1' }] },
      'inspected@1': { nodes: [{ id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' } }, { id: 'w:1', type: 'wafer@1', label: 'W-1', keys: { wafer: 'W1' } }],
        edges: [{ id: 'e:w', source: 'w:1', target: 'n:1', predicate: 'inspected@1' }] } };
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      const follow = new URLSearchParams(u.split('?')[1] || '').get('follow');
      return { ok: true, status: 200, json: async () => (u.includes('/subgraph') ? BY[follow] : DECLG) };
    } });
    await settle();
    handle.state.type = 'die@1';
    handle.state.asked = { type: 'die@1', keys: { mat_id: 'M-1' } };
    handle.state.run = 'done';
    handle.state.result = ROOTG;
    handle.render();
    const press = (e) => { for (const fn of (e && e.listeners.click) || []) fn(); };
    const tick = (id) => { const cb = walkAll(host).find((e) => e.attrs && e.attrs['data-row'] === id); for (const fn of (cb && cb.listeners.click) || []) fn({}); };
    const next = (words) => walkAll(host).find((e) => e.className === 'wk-next-edge' && e.textContent === words);
    const tab = (id) => walkAll(host).find((e) => e.attrs && e.attrs['data-step'] === String(id));
    const tabs = () => walkAll(host).filter((e) => e.className === 'wk-steprow')
      .map((row) => row.children.map((b) => `${b.textContent}${b.className.includes('is-on') ? ' *' : ''}`));
    const rows = () => walkAll(host).filter((e) => e.attrs && e.attrs['data-row']).map((e) => e.attrs['data-row']).join();
    const A = 'bonded_to@1 → die@1';
    const B = 'inspected@1 → wafer@1';
    tick('n:1');
    press(next(A));
    await settle();
    const a = handle.state.at;
    press(tab(0));
    press(next(B));
    await settle();
    const b = handle.state.at;
    ok('GB1 from one step an edge A, then an edge B: both stay, siblings at one level, B the branch (lead 5ea461e04)',
      handle.state.steps.length === 2 && handle.state.steps.every((x) => x.parent === 0) && a !== b
        && JSON.stringify(tabs()) === JSON.stringify([[`Step 1 · ${handle.state.steps.length ? '+ 1' : ''} *`], [`Step 2 · ${A}`, `Step 2 · ${B} *`]]),
      JSON.stringify(tabs()));
    const chainOf = () => handle.graph.chain(2);
    const onB = [rows(), chainOf() === (handle.state.steps.find((x) => x.id === b) || {}).marks];
    press(tab(a));
    const onA = [rows(), chainOf() === (handle.state.steps.find((x) => x.id === a) || {}).marks, handle.state.leaf === a];
    ok('GB2 a tab off the branch chooses it: its table, and the graph\'s chain is that branch\'s',
      JSON.stringify([onB, onA]) === JSON.stringify([['n:1,w:1', true], ['n:1,n:4', true, true]]), JSON.stringify([onB, onA]));
    tick('n:4');
    press(next(A));
    await settle();
    const a1 = handle.state.steps.find((x) => x.parent === a);
    press(tab(b));
    tick('w:1');
    const bMarks = (handle.state.steps.find((x) => x.id === b) || {}).marks;
    press(tab(0));
    press(next(A));
    await settle();
    ok('GB3 the same edge again walks that branch again: it and its steps go with their markings; B and its checks stay',
      Boolean(a1) && !handle.state.steps.some((x) => x.id === a || x.id === a1.id) && handle.graph.markings.count(a1.marks) === 0
        && handle.state.steps.some((x) => x.id === b) && handle.graph.markings.count(bMarks) === 1
        && handle.state.steps.filter((x) => x.parent === 0).length === 2,
      JSON.stringify([handle.state.steps.map((x) => [x.id, x.parent, x.title]), a1 && handle.graph.markings.count(a1.marks), handle.graph.markings.count(bMarks)]));
  }
  // ── «Copy table» on the page (lead a27dfbb0f): every column, the folded too; the rows the filter shows; said beside it ──
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', writeClipboard, fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
    await settle();
    handle.state.type = 'wafer@1';
    handle.state.asked = { type: 'wafer@1', keys: {}, ...SIGNED_STARTS };
    handle.state.run = 'done';
    handle.state.result = SIGNED;
    handle.render();
    const has = (e, cls) => String(e.className || '').split(/\s+/).includes(cls);
    const dieSec = () => walkAll(host).filter((e) => e.className === 'wk-sec').find((x) => x.children[0] && /^die/.test(x.children[0].textContent)) || { children: [] };
    const press = (e) => { for (const fn of (e && e.listeners.click) || []) fn({}); };
    const copy = () => { const at = CLIP.length; press(walkAll(dieSec()).find((e) => has(e, 'wk-copytable'))); return CLIP.length > at ? CLIP[CLIP.length - 1].text : ''; };
    const said = () => (walkAll(dieSec()).find((e) => has(e, 'wk-copied')) || {}).textContent;
    const shownHeads = walkAll(dieSec()).filter((e) => e.tagName === 'th').map((e) => e.textContent);
    const lines = (text) => text.split(String.fromCharCode(10)).map((l) => l.split(String.fromCharCode(9)));
    const all = lines(copy());
    const allSaid = said();
    press(walkAll(host).find((e) => e.attrs && e.attrs['data-rows'] === 'missing'));
    const missed = lines(copy());
    const missedRows = walkAll(dieSec()).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).length;
    const notes = all[0].filter((h) => / note$/.test(h));
    ok('CP3 the page' + "'" + 's «Copy table»: TSV a head row and a row each the filter shows, every row as wide as the head, the column the screen folds (note) copied on both sides, the id last; «Copied N rows» beside it',
      all.length > 1 && all.every((r) => r.length === all[0].length) && notes.length === 2 && !shownHeads.some((h) => / note$/.test(h) || h === 'note')
        && all[0][all[0].length - 1] === 'id' && allSaid === `Copied ${all.length - 1} rows`
        && missed.length - 1 === missedRows && missed.length < all.length,
      JSON.stringify([all[0], all.length, allSaid, missed.length, missedRows, shownHeads]));
    CLIP_OK.ok = false;
    copy();
    const failed = said();
    CLIP_OK.ok = true;
    ok('CP4 a copy the browser refused says so and what to do instead', failed === 'Copy failed · Select the table and press Ctrl+C', failed);
  }
  // ── the page with B (lead 99ed68cb7 D): each side's cells tinted by who reached the row, the three counts over it ──
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
    await settle();
    handle.state.type = 'wafer@1';
    handle.state.asked = { type: 'wafer@1', keys: {}, ...SIGNED_STARTS };
    handle.state.run = 'done';
    handle.state.result = SIGNED;
    handle.state.resultB = CTL_SIGNED;
    let drew = true;
    try { handle.render(); } catch (e) { drew = false; }
    const has = (e, cls) => String(e.className || '').split(/\s+/).includes(cls);
    const sec = walkAll(host).filter((e) => e.className === 'wk-sec').find((x) => x.children[0] && /^die/.test(x.children[0].textContent)) || { children: [] };
    const line = walkAll(sec).filter((e) => e.className === 'wk-reachedside').map((part) => [part._text, ...part.children.map((c) => c.textContent)]);
    const tint = (id) => ((walkAll(sec).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === id) || { children: [] }).children)
      .filter((c) => c.tagName === 'td' && c.className !== 'wk-check').map((c) => (has(c, 'is-ctl-ab') ? 'ab' : has(c, 'is-ctl-b') ? 'b' : ''));
    ok('ZD4 the page: over a section each side\'s three counts; a side\'s cells tinted A + B or B only, A only bare, the other side its own',
      drew && JSON.stringify([line, tint('d:3'), tint('d:5')]) === JSON.stringify([
        [['Positive · ', 'A only 2', 'A + B 1', 'B only 0'], ['Negative · ', 'A only 2', 'A + B 0', 'B only 1']],
        ['ab', 'ab', '', '', '', ''], ['', '', '', 'b', 'b']]),
      JSON.stringify([drew, line, tint('d:3'), tint('d:5')]));
    // + only (no − start), one side since E1 (lead 10-11): its counts once, a row's side cells its kind - the node's own
    // cells in the centre bare.
    const plainDoc = makeDoc();
    const plainHost = plainDoc.createElement('div');
    const plain = mod.boot(plainDoc, plainHost, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
    await settle();
    plain.state.type = 'wafer@1';
    plain.state.asked = { type: 'wafer@1', keys: {}, positive: ['s:a', 's:c'], negative: [] };
    plain.state.run = 'done';
    plain.state.result = SIGNED;
    plain.state.resultB = CTL_SIGNED;
    try { plain.render(); } catch (e) { drew = false; }
    const pSec = walkAll(plainHost).filter((e) => e.className === 'wk-sec').find((x) => x.children[0] && /^die/.test(x.children[0].textContent)) || { children: [] };
    const pLine = walkAll(pSec).filter((e) => e.className === 'wk-reachedside').map((part) => [part._text, ...part.children.map((c) => c.textContent)]);
    // A row's side cells by its id, the centre's apart.
    const pTint = (id) => [...new Set(((walkAll(pSec).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === id) || { children: [] }).children)
      .filter((c) => c.tagName === 'td' && c.className !== 'wk-check' && !has(c, 'wk-centre')).map((c) => (has(c, 'is-ctl-ab') ? 'ab' : has(c, 'is-ctl-b') ? 'b' : '')))];
    ok('ZD5 + only with B, one side: its counts once, a row\'s side cells its kind - d:3 A + B, d:5 B only, d:1 bare (E1, lead 10-11)',
      drew && JSON.stringify([pLine, pTint('d:3'), pTint('d:5'), pTint('d:1')]) === JSON.stringify([[['Positive · ', 'A only 3', 'A + B 1', 'B only 1']], ['ab'], ['b'], ['']]),
      JSON.stringify([drew, pLine, pTint('d:3'), pTint('d:5'), pTint('d:1')]));
  }
  // ── the page: side by side when the walk had a - start (lead 5cf5c3401, the mockup) ──
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
    await settle();
    handle.state.type = 'wafer@1';
    handle.state.asked = { type: 'wafer@1', keys: {}, ...SIGNED_STARTS };
    handle.state.run = 'done';
    handle.state.result = SIGNED;
    handle.render();
    const has = (e, cls) => String(e.className || '').split(/\s+/).includes(cls);
    const heads = walkAll(host).filter((e) => has(e, 'wk-sidehead')).map((e) => e.textContent);
    const missing = walkAll(host).filter((e) => e.tagName === 'td' && has(e, 'wk-missing')).length;
    const secs = walkAll(host).filter((e) => e.className === 'wk-sec');
    const nextFirst = secs.length > 0 && secs.every((sec) => {
      const next = sec.children.findIndex((c) => c.className === 'wk-next');
      return next >= 0 && next < sec.children.findIndex((c) => has(c, 'wk-table'));
    });
    ok('Z9 the page: a table a type, a band a group with its starts and rows, missing in red, Next above',
      JSON.stringify(heads) === JSON.stringify(['Positive · 2 starts · 2 rows', 'Negative · 1 start · 1 row',
        'Positive · 2 starts · 3 rows', 'Negative · 1 start · 2 rows']) && missing === 6 && nextFirst,
      `${JSON.stringify(heads)} ${missing} ${nextFirst}`);
    const views = walkAll(host).filter((e) => e.attrs && e.attrs['data-view']).map((e) => e.attrs['data-view']);
    const compared = walkAll(host).filter((e) => /(^| )cmp-/.test(e.className || '')).length;
    ok('Z10 no way to Compare: the views are Table and Graph, nothing of it drawn',
      views.join() === 'table,graph' && compared === 0, `${views} ${compared}`);
    const dieSec = () => walkAll(host).filter((e) => e.className === 'wk-sec')
      .find((sec) => sec.children[0] && /^die/.test(sec.children[0].textContent)) || { children: [] };
    const table = () => walkAll(dieSec()).find((e) => has(e, 'wk-sides')) || { children: [] };
    // The head rows: the group, the step, the value's name (lead 34d91c09d (나)); the rows below carry their id.
    const headRows = () => walkAll(table()).filter((e) => e.tagName === 'tr' && !(e.attrs && e.attrs['data-row-id']));
    const headRow = () => (headRows()[headRows().length - 1] || { children: [] }).children
      .filter((c) => c.className !== 'wk-check').map((c) => c.textContent);
    const stepRow = () => (headRows().length === 3 ? headRows()[1].children : []).filter((c) => c.className !== 'wk-check')
      .map((c) => [c.textContent, c.colSpan]);
    const rowOf = (id) => walkAll(table()).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === id);
    const tds = (id) => ((rowOf(id) || { children: [] }).children).filter((c) => c.className !== 'wk-check')
      .map((c) => (c.children.find((k) => k.className === 'wk-centrelabel') ? c.children.find((k) => k.className === 'wk-centrelabel').textContent : valsOf(c)));
    ok('Z13 two groups: Route outermost, the + columns, the node in the centre, delta beside it, the − columns, Route outermost (34d91c09d, df11f9e81)',
      JSON.stringify([headRow(), tds('d:3')]) === JSON.stringify([['Route', 'gate', 'mat_id', 'Δ', 'gate', 'Route'], ['inspected', '7', 'M-3', '−2', '9', 'inspected']]),
      JSON.stringify([headRow(), tds('d:3')]));
    // The node axis in the middle of its box (lead 10-10): a box at 400 px, 800 wide, 2000 to scroll.
    const scrollTo = (axisLeft, axisRight) => mod.axisScrollLeft({ boxLeft: 400, boxWidth: 800, axisLeft, axisRight, scrollLeft: 0, scrollWidth: 2000 });
    ok('Z28 a table opens with its node axis in the middle of its box, within what the box can scroll',
      JSON.stringify([scrollTo(1300, 1500), scrollTo(500, 600), scrollTo(2300, 2400)]) === JSON.stringify([600, 0, 1200]),
      JSON.stringify([scrollTo(1300, 1500), scrollTo(500, 600), scrollTo(2300, 2400)]));
    ok('Z27 the step once over the columns that share it, the value\'s name under each (34d91c09d)',
      JSON.stringify(stepRow()) === JSON.stringify([['', 1], ['inspected (in)', 1], ['', 1], ['', 1], ['inspected (in)', 1], ['', 1]]), JSON.stringify(stepRow()));
    const copy = walkAll(rowOf('d:3') || { children: [] }).find((e) => e.className === 'wk-copyid');
    ok('Z16 the id is behind a press in the centre, not a column - an icon, its name for a reader (34d91c09d 5)',
      Boolean(copy) && copy.attrs['data-id'] === 'd:3' && copy.textContent === '' && copy.attrs['aria-label'] === 'Copy id'
      && !headRow().includes('id'), JSON.stringify([headRow(), copy && copy.textContent]));
    const fire = (b) => { for (const fn of (b && b.listeners.click) || []) fn({ stopPropagation() {} }); };
    // Several values (34d91c09d 1): the first and «+N»; a press on «+N» unfolds them all, another folds.
    const moreOf = () => walkAll(rowOf('d:4') || { children: [] }).find((e) => e.className === 'wk-more');
    const cellOf4 = () => ((rowOf('d:4') || { children: [] }).children.find((c) => c.children.includes(moreOf())));
    const said = () => (cellOf4() ? [valsOf(cellOf4()), moreOf().textContent, has(cellOf4(), 'is-open')] : null);
    const shut = said();
    fire(moreOf());
    const opened = said();
    fire(moreOf());
    ok('Z24 several values in a cell: the first and «+N»; pressed, every one in the cell; pressed again, folded (34d91c09d 1)',
      JSON.stringify([shut, opened, said()]) === JSON.stringify([['1', '+1', false], ['1 · 2', 'Less', true], ['1', '+1', false]]),
      JSON.stringify([shut, opened, said()]));
    // Route's «+N» on the page (lead df11f9e81): the same press as a value cell's - every route, then the first again.
    const page2 = makeDoc();
    const host2 = page2.createElement('div');
    const two = mod.boot(page2, host2, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
    await settle();
    two.state.type = 'wafer@1';
    two.state.asked = { type: 'wafer@1', keys: {}, ...BOND_STARTS };
    two.state.run = 'done';
    two.state.result = BOND_TWO;
    let drew = true;
    try { two.render(); } catch (e) { drew = false; }
    const coreMore = () => walkAll(walkAll(host2).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === 'w:c') || { children: [] })
      .find((e) => e.className === 'wk-more');
    const coreCell = () => (walkAll(host2).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === 'w:c') || { children: [] })
      .children.find((c) => c.children.includes(coreMore()));
    const coreSaid = () => (coreCell() ? [valsOf(coreCell()), coreMore().textContent] : null);
    const routeShut = coreSaid();
    try { fire(coreMore()); } catch (e) { drew = false; }
    const routeOpen = coreSaid();
    ok('Z32 a Route cell\'s «+N» on the page: pressed, every path in the cell; the first and «+N» before',
      drew && JSON.stringify([routeShut, routeOpen]) === JSON.stringify([[BONDING, '+1'], [`${BONDING} · ${STACKING}`, 'Less']]),
      JSON.stringify([drew, routeShut, routeOpen]));
    const srcShut = cellOf4() ? [valsOf(cellOf4()), srcsOf(cellOf4())] : null;
    fire(moreOf());
    const srcOpen = cellOf4() ? [valsOf(cellOf4()), srcsOf(cellOf4())] : null;
    fire(moreOf());
    ok('Z41 the page: under a value who gave it; «+N» opened, each value its own source (lead 99ed68cb7 C)',
      JSON.stringify([srcShut, srcOpen]) === JSON.stringify([['1', ['A · start']], ['1 · 2', ['A · start', 'C · start']]]),
      JSON.stringify([srcShut, srcOpen]));
    const bands = walkAll(host).filter((e) => has(e, 'wk-sidehead')).map((e) => [e.attrs['data-sign'], has(e, 'wk-plus'), has(e, 'wk-minus')]);
    ok('Z25 a band its sign\'s class - + one colour, − the other (34d91c09d 4)',
      JSON.stringify(bands.slice(0, 2)) === JSON.stringify([['+', true, false], ['\u2212', false, true]]), JSON.stringify(bands));
    // A column no row has a value in (34d91c09d 7): folded, said by its count; pressed, it stands in each group.
    const foldOf = () => walkAll(dieSec()).find((e) => has(e, 'wk-emptycols'));
    const folded = [foldOf() && foldOf().textContent, headRow()];
    fire(foldOf());
    const unfolded = [foldOf() && foldOf().attrs['aria-pressed'], headRow()];
    const unfoldedSteps = stepRow();
    fire(foldOf());
    ok('Z26 «1 empty column»: pressed, the column stands in each group; pressed again, folded',
      JSON.stringify([folded, unfolded, headRow(), unfoldedSteps]) === JSON.stringify([['1 empty column', ['Route', 'gate', 'mat_id', 'Δ', 'gate', 'Route']],
        ['true', ['Route', 'note', 'gate', 'mat_id', 'Δ', 'gate', 'note', 'Route']], ['Route', 'gate', 'mat_id', 'Δ', 'gate', 'Route'],
        [['', 1], ['inspected (in)', 2], ['', 1], ['', 1], ['inspected (in)', 2], ['', 1]]]),
      JSON.stringify([folded, unfolded, headRow(), unfoldedSteps]));
    const press = (value) => {
      const b = walkAll(host).find((e) => e.attrs && e.attrs['data-rows'] === value);
      for (const fn of (b && b.listeners.click) || []) fn({});
    };
    const shown = () => walkAll(host).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).map((e) => e.attrs['data-row-id']).sort().join();
    press('differs');
    const differs = shown();
    press('missing');
    const missed = shown();
    press('all');
    ok('Z14 All rows · Differs · Missing: the rows the groups differ on, the rows one missed, then every row',
      JSON.stringify([differs, missed, shown()]) === JSON.stringify([ALL, 'd:1,d:2,d:4,s:a,s:b,s:c', ALL]), JSON.stringify([differs, missed]));
    // + Column on the die section: the route in, then the far wafer's key - a column each group, + reversed.
    const addOn = walkAll(dieSec()).find((e) => e.tagName === 'button' && e.textContent === '+ Column');
    for (const fn of (addOn && addOn.listeners.click) || []) fn({});
    const pick = (n, test) => {
      const sel = walkAll(dieSec()).filter((e) => e.tagName === 'select')[n];
      const opt = sel && sel.children.find((o) => test(o.textContent));
      if (!opt) return false;
      sel.value = opt.value;
      for (const fn of sel.listeners.change || []) fn({});
      return true;
    };
    const route = pick(0, (t) => t.startsWith('inspected (in) → '));
    const value = route && pick(1, (t) => t === 'key · wafer');
    const ADDED_STEP = 'inspected (in) → wafer@1';
    ok('Z15 + Column: a route the rows take, then what its end holds - a column each group, the + side reversed',
      JSON.stringify([route, value, headRow(), stepRow(), tds('d:3')]) === JSON.stringify([true, true,
        ['Route', 'wafer', 'gate', 'mat_id', 'Δ', 'gate', 'wafer', 'Route'],
        [['', 1], [ADDED_STEP, 1], ['inspected (in)', 1], ['', 1], ['', 1], ['inspected (in)', 1], [ADDED_STEP, 1], ['', 1]],
        ['inspected', 'A', '7', 'M-3', '−2', '9', 'B', 'inspected']]),
      JSON.stringify([route, value, headRow(), stepRow(), tds('d:3')]));
  }
}

// ═══ baseline ═══════════════════════════════════════════════════════════════════════════
const first = await loadWithProbe(SRC, {});
await suite(first.module);
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${ran} assertions, `
  + `${failures.length} failure(s)`);
failures.forEach((f) => console.log(`   x ${f}`));
// ── Q: several edges into one node keep every value (lead 10-09, demo ①: the cell said the last edge's alone) ──
const TWO = {
  nodes: [
    { id: 'q:1', type: 'die@1', label: 'D-1', depth: 1, keys: { mat_id: 'M-1' } },
    { id: 'q:a', type: 'wafer@1', label: 'W-1', depth: 0, keys: { wafer: 'A' } },
    { id: 'q:b', type: 'wafer@1', label: 'W-2', depth: 0, keys: { wafer: 'B' } },
  ],
  edges: [
    { id: 'q:e1', source: 'q:a', target: 'q:1', predicate: 'inspected', qualifiers: { gate: 7 } },
    { id: 'q:e2', source: 'q:b', target: 'q:1', predicate: 'inspected', qualifiers: { gate: 9 } },
  ],
};
const gateCell = (TV, answer) => {
  const die = TV.walkTableView(answer, DECL.entities, DECL.predicates).sections.find((s) => s.type === 'die@1');
  const at = die ? die.heads.indexOf('inspected (in) · gate') : -1;
  return at >= 0 ? die.rows[0].byGroup[0][at] : { text: null, numeric: null };
};
const qualifierSuite = (TV) => {
  // The walk table's cell (E1, the flat table's fold retired): every edge's value kept, each with the node that gave it.
  const two = gateCell(TV, TWO);
  ok('Q1 two edges into one node: the cell keeps both values and whose',
    JSON.stringify([two.text, two.rest, two.values, two.sources]) === JSON.stringify(['7', '+1', ['7', '9'], [`A · ${TV.EMPTY}`, `B · ${TV.EMPTY}`]]),
    JSON.stringify(two));
  const one = gateCell(TV, RESULT);
  ok('Q2 one edge: the value as it came, a number', one.text === '7' && one.numeric === true, JSON.stringify(one));
  // The flat table's two node-own columns in the centre (lead 10-11), read by its functions.
  const carry = TV.walkTableView(CARRY, CARRY_DECL.entities, CARRY_DECL.predicates).sections.find((x) => x.type === 'die@1') || { centreHeads: [], rows: [] };
  const centreOf = (id) => ((carry.rows.find((r) => r.id === id) || { centre: [] }).centre).map((c) => c.text);
  ok('EC1 «Conflicts» stands in the centre where the type declares attributes: the count the server said, none «—»',
    carry.centreHeads.includes('Conflicts') && centreOf('k:1')[carry.centreHeads.indexOf('Conflicts')] === '2'
      && centreOf('k:2')[carry.centreHeads.indexOf('Conflicts')] === TV.EMPTY,
    JSON.stringify([carry.centreHeads, centreOf('k:1'), centreOf('k:2')]));
  ok('EC2 a confirmation predicate\'s column stands in the centre (C-98): the server\'s verdict and why, none «—»',
    carry.centreHeads.includes('observed') && centreOf('k:1')[carry.centreHeads.indexOf('observed')] === 'unknown · not_examined'
      && centreOf('k:2')[carry.centreHeads.indexOf('observed')] === TV.EMPTY,
    JSON.stringify([carry.centreHeads, centreOf('k:1'), centreOf('k:2')]));
};
// The suite's own count: a mutant of main.js runs the suite alone, so its shrink is measured against this.
const suiteRan = ran;
// ── the walk table side by side as the formula (lead 5cf5c3401; the signs by the server's reach) ──
const rowIds = (table) => table.sections.flatMap((sec) => sec.rows.map((r) => r.id)).sort().join(',');
const sideSuite = (TV) => {
  const view = (starts, result = SIGNED, added) => TV.walkTableView(result, DECL.entities, DECL.predicates, undefined, starts, added);
  // A row's cell in one group under one head, as drawn: missing in brackets.
  const cell = (table, type, id, head, group) => {
    const sec = table.sections.find((x) => x.type === type);
    const at = sec ? sec.heads.indexOf(head) : -1;
    const row = sec && sec.rows.find((r) => r.id === id);
    const side = row && row.byGroup[group];
    const got = side && at >= 0 ? (side[0] && side[0].missing ? side[0] : side[at]) : null;
    return got ? (got.missing ? `[${got.text}]` : got.text) : null;
  };
  const raw = (table, type, id, head, group) => {
    const sec = table.sections.find((x) => x.type === type);
    const at = sec ? sec.heads.indexOf(head) : -1;
    const row = sec && sec.rows.find((r) => r.id === id);
    return row && at >= 0 ? row.byGroup[group][at] : null;
  };
  const plain = view({ positive: ['s:a', 's:c'], negative: [] });
  ok('Z1 no - start: one side, every node the walk brought (E1: the flat table retired)', plain.groups.length === 1
    && plain.sections.every((x) => x.groups.length === 1) && rowIds(plain) === ALL,
    `${JSON.stringify(plain.groups)} ${rowIds(plain)}`);
  const two = view(SIGNED_STARTS);
  ok('Z2 a node a row: one row whichever groups reached it', rowIds(two) === ALL
    && two.sections.every((x) => new Set(x.rows.map((r) => r.id)).size === x.rows.length), rowIds(two));
  ok('Z3 reached by one group only: the other says missing',
    cell(two, 'die@1', 'd:1', GATE_IN, 1) === '[missing]' && cell(two, 'die@1', 'd:2', GATE_IN, 0) === '[missing]',
    `${cell(two, 'die@1', 'd:1', GATE_IN, 1)} | ${cell(two, 'die@1', 'd:2', GATE_IN, 0)}`);
  ok('Z4 reached but no value says so, not missing',
    cell(two, 'die@1', 'd:1', GATE_IN, 0) === TV.EMPTY && cell(two, 'die@1', 'd:2', GATE_IN, 1) === TV.EMPTY,
    `${cell(two, 'die@1', 'd:1', GATE_IN, 0)} | ${cell(two, 'die@1', 'd:2', GATE_IN, 1)}`);
  ok('Z5 a cell reads its group\'s edges only: the node both reached says each group\'s own value',
    cell(two, 'die@1', 'd:3', GATE_IN, 0) === '7' && cell(two, 'die@1', 'd:3', GATE_IN, 1) === '9',
    `${cell(two, 'die@1', 'd:3', GATE_IN, 0)} | ${cell(two, 'die@1', 'd:3', GATE_IN, 1)}`);
  // Copy table (lead a27dfbb0f): one head row - each side's columns under its sign, the node's own, Δ, the id last;
  // values raw, several «; », none empty, a side not reached «missing» in each of its columns.
  const cpDie = two.sections.find((x) => x.type === 'die@1') || { groups: [], heads: [], centreHeads: [], deltaHeads: [], rows: [] };
  const sheet = TV.sheetOf ? TV.sheetOf(cpDie, 'all') : { head: [], rows: [] };
  const cpRow = (id) => sheet.rows.find((r) => r[r.length - 1] === id) || [];
  const at = (h) => sheet.head.indexOf(h);
  const d3Delta = ((cpDie.rows.find((r) => r.id === 'd:3') || { deltas: [] }).deltas[0] || {}).value;
  ok('CP1 the section as a sheet: head + ' + "side' columns, the node's own, - side' columns, Δ, id; a row as wide as the head; d:1's - side «missing» in each column; d:4 «1; 2»; d:3 7 and 9 and its Δ its number; no «—»",
    sheet.head.length === cpDie.heads.length * 2 + cpDie.centreHeads.length + cpDie.deltaHeads.length + 1
      && sheet.head[0] === `+ ${cpDie.heads[0]}` && sheet.head[sheet.head.length - 1] === 'id'
      && sheet.rows.length === cpDie.rows.length && sheet.rows.every((r) => r.length === sheet.head.length)
      && cpDie.heads.every((h) => cpRow('d:1')[at(`− ${h}`)] === TV.MISSING)
      && cpRow('d:4')[at(`+ ${GATE_IN}`)] === '1; 2' && cpRow('d:3')[at(`+ ${GATE_IN}`)] === '7' && cpRow('d:3')[at(`− ${GATE_IN}`)] === '9'
      && typeof d3Delta === 'number' && cpRow('d:3')[at(cpDie.deltaHeads[0])] === String(d3Delta)
      && !sheet.rows.some((r) => r.includes(TV.EMPTY)),
    JSON.stringify([sheet.head, cpRow('d:1'), cpRow('d:3'), cpRow('d:4')]));
  const differs = TV.sheetOf ? TV.sheetOf(cpDie, 'differs') : { rows: [] };
  const missing = TV.sheetOf ? TV.sheetOf(cpDie, 'missing') : { rows: [] };
  ok('CP2 the sheet follows the filter: Differs the rows the sides differ on, Missing the rows one missed - fewer than all',
    JSON.stringify(differs.rows.map((r) => r[r.length - 1])) === JSON.stringify(cpDie.rows.filter((r) => r.differs).map((r) => r.id))
      && JSON.stringify(missing.rows.map((r) => r[r.length - 1])) === JSON.stringify(cpDie.rows.filter((r) => r.missing).map((r) => r.id))
      && missing.rows.length > 0 && missing.rows.length < sheet.rows.length,
    JSON.stringify([differs.rows.length, missing.rows.length, sheet.rows.length]));
  const d4 = raw(two, 'die@1', 'd:4', GATE_IN, 0) || {};
  ok('Z6 several edges in one group: every value kept, none overwritten - the first said, «+N» the rest (34d91c09d 1)',
    JSON.stringify([d4.text, d4.rest, d4.values]) === JSON.stringify(['1', '+1', ['1', '2']]), JSON.stringify(d4));
  const blind = view(SIGNED_STARTS, { ...SIGNED, propagation: null });
  ok('Z7 an answer that ranks nothing: one side holding every node, said to be both signs', blind.groups.length === 1
    && blind.unsplit === true && rowIds(blind) === ALL, `${JSON.stringify(blind.groups)} ${blind.unsplit}`);
  const bare = view(SIGNED_STARTS, { ...SIGNED, edges: SIGNED.edges.map(({ qualifiers, ...e }) => e) });
  const bareDie = bare.sections.find((x) => x.type === 'die@1') || { heads: [], rows: [] };
  const d3 = bareDie.rows.find((r) => r.id === 'd:3') || { byGroup: [[], []] };
  const d1 = bareDie.rows.find((r) => r.id === 'd:1') || { byGroup: [[], []] };
  ok('Z8 a type with no column: Route alone - how each side reached it (via and depth folded into it, lead df11f9e81); missing where it did not, once',
    JSON.stringify([bareDie.heads, d3.byGroup.map((g) => g.map((c) => c.text)), d1.byGroup[1].map((c) => [c.missing, c.span])])
      === JSON.stringify([[TV.ROUTE], [['inspected'], ['inspected']], [[true, 1]]]),
    JSON.stringify([bareDie.heads, d3.byGroup, d1.byGroup[1]]));
  const die = two.sections.find((x) => x.type === 'die@1') || { groups: [], heads: [], centreHeads: [], deltaHeads: [], rows: [] };
  const wafer = two.sections.find((x) => x.type === 'wafer@1') || { heads: [] };
  ok('Z11 an edge attribute\'s head: its predicate, «(in)» when taken in, and its name',
    JSON.stringify([die.heads, wafer.heads]) === JSON.stringify([[GATE_IN, TV.ROUTE], ['inspected · gate', TV.ROUTE]]), JSON.stringify([die.heads, wafer.heads]));
  ok('Z12 delta where both groups say one number: the first less the second; its head once',
    JSON.stringify([die.deltaHeads, die.rows.map((r) => r.deltas.map((d) => d.text).join())])
      === JSON.stringify([[TV.DELTA], ['', '', '−2', '']]), JSON.stringify([die.deltaHeads, die.rows.map((r) => r.deltas)]));
  ok('Z17 the node\'s own columns - the keys its rows carry - once in the centre, read off the row',
    JSON.stringify([die.centreHeads, (die.rows.find((r) => r.id === 'd:3') || { centre: [] }).centre.map((c) => c.text)])
      === JSON.stringify([['mat_id'], ['M-3']]), JSON.stringify(die.centreHeads));
  ok('Z20 a band a group: its starts and its rows', JSON.stringify(die.groups) === JSON.stringify([
    { sign: '+', starts: 2, count: 3 }, { sign: '−', starts: 1, count: 2 }]), JSON.stringify(die.groups));
  const added = new Map([['die@1', [{ steps: [{ predicate: 'inspected', direction: 'incoming' }], value: { on: 'key', name: 'wafer' },
    words: ['inspected (in) → wafer@1', 'wafer'] }]]]);
  const more = view(SIGNED_STARTS, SIGNED, added);
  ok('Z18 an added column: its route\'s far node, a column of each group',
    cell(more, 'die@1', 'd:3', 'inspected (in) → wafer@1 · wafer', 0) === 'A' && cell(more, 'die@1', 'd:3', 'inspected (in) → wafer@1 · wafer', 1) === 'B',
    `${cell(more, 'die@1', 'd:3', 'inspected (in) → wafer@1 · wafer', 0)} ${cell(more, 'die@1', 'd:3', 'inspected (in) → wafer@1 · wafer', 1)}`);
  const capped = TV.cellWords({ missing: false, values: [1, 2], more: true });
  ok('Z19 words: several values past the cap, and a difference without its float tail',
    JSON.stringify([capped.text, capped.rest, TV.deltaWords(0.22 - 0.3305), TV.deltaWords(19.5)])
      === JSON.stringify(['1', '+1+', '−0.1105', '+19.5']), JSON.stringify(capped));
  // The nine (lead 34d91c09d).
  const moreDie = more.sections.find((x) => x.type === 'die@1') || { rows: [] };
  const m1 = moreDie.rows.find((r) => r.id === 'd:1') || { byGroup: [[], []] };
  const m3 = moreDie.rows.find((r) => r.id === 'd:3') || { byGroup: [[], []] };
  ok('Z21 a side that did not reach the node: one missing cell across its columns; a side that did: a cell a column (34d91c09d 3)',
    JSON.stringify([m1.byGroup[1].map((c) => [c.text, c.span]), m3.byGroup[0].length]) === JSON.stringify([[['missing', 3]], 3]),
    JSON.stringify([m1.byGroup[1], m3.byGroup[0].length]));
  const eqp = view(SIGNED_STARTS, { ...SIGNED, edges: SIGNED.edges.map((e) => ({ ...e, qualifiers: { ...e.qualifiers, eqp: 'E' } })) });
  const eqpDie = eqp.sections.find((x) => x.type === 'die@1') || { heads: [] };
  ok('Z22 the number columns nearest the node, the rest outward, each in its order (34d91c09d 2)',
    JSON.stringify(eqpDie.heads) === JSON.stringify([GATE_IN, 'inspected (in) · eqp', TV.ROUTE]), JSON.stringify(eqpDie.heads));
  const open = TV.walkTableView(SIGNED, DECL.entities, DECL.predicates, undefined, SIGNED_STARTS, new Map(), new Set(['die@1']));
  const openDie = open.sections.find((x) => x.type === 'die@1') || { heads: [] };
  ok('Z23 a column no row has a value in folds, counted; its type opened, it stands (34d91c09d 7)',
    JSON.stringify([die.heads, die.empty, openDie.heads, openDie.empty]) === JSON.stringify([[GATE_IN, TV.ROUTE], { count: 1, open: false },
      [GATE_IN, NOTE_IN, TV.ROUTE], { count: 1, open: true }]), JSON.stringify([die.heads, die.empty, openDie.heads, openDie.empty]));
  // C (lead 99ed68cb7): who gave a value - the node its read ends at, its keys, its side's route - on both schemes and 18766.
  const srcOf = (t, type, id, head, group) => (raw(t, type, id, head, group) || {}).sources || null;
  const edgeSrc = view(BOND_STARTS, BOND_SRC);
  ok('Z38 a value\'s source, the measurement an edge: the wafer that measured it, its keys and its side\'s route',
    JSON.stringify([srcOf(edgeSrc, 'quantity@1', 'q:1', 'measures (in) · value', 0), srcOf(edgeSrc, 'quantity@1', 'q:1', 'measures (in) · value', 1)])
      === JSON.stringify([['B · start', `C · ${BONDING}`], ['N-1 · in_container']]),
    JSON.stringify([srcOf(edgeSrc, 'quantity@1', 'q:1', 'measures (in) · value', 0), srcOf(edgeSrc, 'quantity@1', 'q:1', 'measures (in) · value', 1)]));
  const eventSrc = TV.walkTableView(BOND_SRC_EVENT, DECL.entities, DECL.predicates, undefined, BOND_STARTS, OF_VALUE);
  ok('Z39 a value\'s source, the measurement an event node: that node, its label (no keys), and its side\'s route',
    JSON.stringify([srcOf(eventSrc, 'quantity@1', 'q:1', 'of (in) · value', 0), srcOf(eventSrc, 'quantity@1', 'q:1', 'of (in) · value', 1)])
      === JSON.stringify([['M:1 · measured', `M:3 · ${BONDING} → measured`], ['M:2 · in_container → measured']]),
    JSON.stringify([srcOf(eventSrc, 'quantity@1', 'q:1', 'of (in) · value', 0), srcOf(eventSrc, 'quantity@1', 'q:1', 'of (in) · value', 1)]));
  const bt = TV.walkTableView(SRC_18766, SRC_18766._entities, [], undefined, SRC_18766._starts);
  const btId = SRC_18766.nodes.find((n) => n.label === 'bond_temp').id;
  const btCell = (g) => raw(bt, 'quantity', btId, 'measures (in) · value', g) || {};
  ok('Z40 18766 bond_temp: + 35.5 «SYN-BW-103-11 · start», 21.5 and 23.5 the core wafers by their bonding; − 13 «SYN-BW-SPL-400-19 · start»',
    JSON.stringify([btCell(0).values, btCell(0).sources, btCell(1).text, btCell(1).sources]) === JSON.stringify([['35.5', '21.5', '23.5'],
      ['SYN-BW-103-11 · start', 'SYN-CW-103-01 · in_container → bonded_from → in_container', 'SYN-CW-103-02 · in_container → bonded_from → in_container'],
      '13', ['SYN-BW-SPL-400-19 · start']]),
    JSON.stringify([btCell(0).values, btCell(0).sources, btCell(1).text, btCell(1).sources]));
  const bc = TV.walkTableView(SRC_COLLECT, SRC_COLLECT._entities, [], undefined, SRC_COLLECT._starts);
  const bcCell = (g) => raw(bc, 'quantity', btId, 'measures (in) · value', g) || {};
  const everySource = bc.sections.flatMap((x) => x.rows.flatMap((r) => r.byGroup.flatMap((side) => side.flatMap((c) => c.sources || []))));
  ok('Z42 collect quantity alone (the demo\'s form): the wafers are not in nodes, their keys read off their ids - the same sources as Z40, no id in any (lead 10-11)',
    JSON.stringify([bcCell(0).sources, bcCell(1).sources]) === JSON.stringify([btCell(0).sources, btCell(1).sources])
      && everySource.length >= 4 && !everySource.some((w) => w.includes('ledger-entity:')),
    JSON.stringify([bcCell(0).sources, bcCell(1).sources, everySource.filter((w) => w.includes('ledger-entity:')).length]));
  // A node the answer did not send and whose id is no entity's: «—», never the id.
  const unsent = view(BOND_STARTS, { ...BOND_SRC, nodes: BOND_SRC.nodes.filter((n) => n.id !== 'w:c') });
  ok('Z43 a value\'s node neither sent nor an entity id: its source says «—», not the id',
    JSON.stringify(srcOf(unsent, 'quantity@1', 'q:1', 'measures (in) · value', 0)) === JSON.stringify(['B · start', `${TV.EMPTY} · ${BONDING}`]),
    JSON.stringify(srcOf(unsent, 'quantity@1', 'q:1', 'measures (in) · value', 0)));
  // D (lead 99ed68cb7): who reached a row - A only, A + B, B only - each side its own; B's path under Route.
  const ctlKinds = (t, type) => {
    const sec = t.sections.find((x) => x.type === type) || { rows: [] };
    return [sec.reached, sec.rows.length, sec.rows.filter((r) => r.reached && r.reached[0] === 'b').map((r) => r.id).sort()];
  };
  const qa = new Set(CTL_18766.a.nodes.map((n) => n.id));
  const onlyB = CTL_18766.b.nodes.filter((n) => n.type === 'quantity' && !qa.has(n.id)).map((n) => n.id).sort();
  const ctl = TV.walkTableView(CTL_18766.a, [], [], undefined, CTL_STARTS, new Map(), new Set(), CTL_18766.b);
  ok('ZD1 18766 from void, B leads_to: quantity 35 rows - A only 17 · A + B 15 · B only 3, the three B only the ones A did not reach',
    JSON.stringify(ctlKinds(ctl, 'quantity')) === JSON.stringify([[{ a: 17, ab: 15, b: 3 }], 35, onlyB]) && onlyB.length === 3,
    JSON.stringify(ctlKinds(ctl, 'quantity')));
  const noCtl = TV.walkTableView(CTL_18766.a, [], [], undefined, CTL_STARTS);
  ok('ZD2 no B: no row says who reached it, A\'s rows alone',
    JSON.stringify(ctlKinds(noCtl, 'quantity')) === JSON.stringify([null, 32, []])
      && noCtl.sections.every((x) => x.reached === null && x.rows.every((r) => r.reached === null)),
    JSON.stringify(ctlKinds(noCtl, 'quantity')));
  const sides = TV.walkTableView(SIGNED, DECL.entities, DECL.predicates, undefined, SIGNED_STARTS, new Map(), new Set(), CTL_SIGNED);
  const sDie = sides.sections.find((x) => x.type === 'die@1') || { rows: [] };
  const sRow = (id) => sDie.rows.find((r) => r.id === id) || { byGroup: [[], []] };
  const sRoute = (id, g) => { const c = raw(sides, 'die@1', id, TV.ROUTE, g) || {}; return [c.text, c.sources || null]; };
  ok('ZD3 two baskets, each side its own: d:3 A + B on + and A only on −, d:5 B only on −; Route says B\'s path a line more; a value only B brought, B\'s source',
    JSON.stringify([sDie.reached, sRow('d:3').reached, sRow('d:5').reached, sRoute('d:3', 0), sRoute('d:3', 1), sRoute('d:5', 1),
      srcOf(sides, 'die@1', 'd:5', GATE_IN, 1), srcOf(sides, 'die@1', 'd:3', GATE_IN, 0)])
      === JSON.stringify([[{ a: 2, ab: 1, b: 0 }, { a: 2, ab: 0, b: 1 }], ['ab', 'a'], [null, 'b'], ['inspected', ['B · leads_to']],
        ['inspected', null], [TV.EMPTY, ['B · leads_to → inspected']], ['B · W5 · leads_to'], ['A · start']]),
    JSON.stringify([sDie.reached, sRow('d:3').reached, sRow('d:5').reached, sRoute('d:3', 0), sRoute('d:3', 1), sRoute('d:5', 1),
      srcOf(sides, 'die@1', 'd:5', GATE_IN, 1), srcOf(sides, 'die@1', 'd:3', GATE_IN, 0)]));
  // Two Δ columns: each Δ says its own column - by the column's index, Route standing first in heads (B).
  const scored = view(SIGNED_STARTS, { ...SIGNED, edges: SIGNED.edges.map((e, k) => ({ ...e, qualifiers: { ...e.qualifiers, score: 10 + k } })) });
  const scoredDie = scored.sections.find((x) => x.type === 'die@1') || { deltaHeads: [] };
  ok('Z37 two Δ columns: each «Δ» names its own column',
    JSON.stringify(scoredDie.deltaHeads) === JSON.stringify([`${TV.DELTA} ${GATE_IN}`, `${TV.DELTA} inspected (in) · score`]),
    JSON.stringify(scoredDie.deltaHeads));
  // Route on both schemes (lead df11f9e81): the base wafer a start, the core wafer its bonding route, each side its own.
  const routeOf = (scheme) => {
    const t = view(BOND_STARTS, scheme);
    return [['wafer@1', 'w:b'], ['wafer@1', 'w:c'], ['wafer@1', 'w:n'], ['quantity@1', 'q:1']]
      .map(([type, id]) => [id, cell(t, type, id, TV.ROUTE, 0), cell(t, type, id, TV.ROUTE, 1)]);
  };
  const bondWant = (plus, minus) => [['w:b', TV.STARTED, '[missing]'], ['w:c', BONDING, '[missing]'], ['w:n', '[missing]', TV.STARTED],
    ['q:1', plus, minus]];
  ok('Z29 Route = the paths the server walked, the measurement an edge: the base wafer «start», the core wafer its bonding, + and − each its own starts\' paths, a side not reached missing',
    JSON.stringify(routeOf(BOND_EDGE)) === JSON.stringify(bondWant('measures', 'in_container → measures')), JSON.stringify(routeOf(BOND_EDGE)));
  ok('Z30 Route, the measurement an event node: the same wafers, the quantity two steps on',
    JSON.stringify(routeOf(BOND_EVENT)) === JSON.stringify(bondWant('measured → of', 'in_container → measured → of')),
    JSON.stringify(routeOf(BOND_EVENT)));
  const core = raw(view(BOND_STARTS, BOND_TWO), 'wafer@1', 'w:c', TV.ROUTE, 0) || {};
  ok('Z31 two paths walked to one node: the first and «+N», every one kept (the nine\'s several values)',
    JSON.stringify([core.text, core.rest, core.values]) === JSON.stringify([BONDING, '+1',
      [BONDING, STACKING]]), JSON.stringify(core));
};
qualifierSuite(await import('../src/walk/table_view.js'));
sideSuite(await import('../src/walk/table_view.js'));
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline with Q: ${ran} assertions`);
const base = { ran, names: NAMES.slice(), failed: failures.length };

// ═══ mutants ════════════════════════════════════════════════════════════════════════════
const NEXT_ASK = '    const asked = { ...knobs(), ...stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to }) };';
const MUTANTS = [
  { id: 'DM7', what: 'a side\'s cells not tinted by who reached the row', catches: 'ZD4',
    from: "row.reached && row.reached[i] && row.reached[i] !== 'a' ?", to: 'false ?' },
  { id: 'DM8', what: 'the three counts not drawn over a section', catches: 'ZD4',
    from: '      if (section.reached) sec.append(reachedLine(section));\n', to: '' },
  { id: 'NZ16', what: 'the source line not drawn under a value', catches: 'Z41',
    from: "        if (sources[k]) c.append(el(doc, 'div', 'wk-src', sources[k]));\n", to: '' },
  { id: 'NZ15', what: 'a Route cell\'s «+N» keyed by a value column it does not have', catches: 'Z32',
    from: '${cell.col === undefined ? ROUTE : columnKey(section.columns[cell.col])}', to: '${columnKey(section.columns[cell.col])}' },
  { id: 'NZ1', what: 'the page draws no band a group', catches: 'Z9',
    from: '    thead.append(band, ...(section.parts', to: '    thead.append(...(section.parts' },
  { id: 'NZ2', what: 'the Next row gone from above its table', catches: 'Z9',
    from: '      // Next above its table, once (lead 3375edd9b).\n      if (checks) sec.append(nextRow(at, section, checks));\n', to: '' },
  { id: 'NZ3', what: 'the Compare view back', catches: 'Z10',
    from: "    for (const [name, word] of [['table', 'Table'], ['graph', 'Graph']]) {",
    to: "    for (const [name, word] of [['table', 'Table'], ['graph', 'Graph'], ['compare', 'Compare']]) {" },
  { id: 'NZ4', what: 'the + side not reversed', catches: 'Z15',
    from: '      const parts = pair && i === 0 ? [...section.parts].reverse() : section.parts;', to: '      const parts = section.parts;' },
  { id: 'NZ5', what: 'the node first, not in the centre', catches: 'Z13',
    from: '    if (pair) { side(section.groups[0], 0); centre(); delta(); side(section.groups[1], 1); } else { centre(); section.groups.forEach(side); }',
    to: '    { centre(); section.groups.forEach(side); delta(); }' },
  { id: 'NZ11', what: 'delta last again, past the − side', catches: 'Z13',
    from: '      if (pair) { group(0); node(); deltas(); group(1); }', to: '      if (pair) { group(0); node(); group(1); deltas(); }' },
  { id: 'NZ12', what: 'the step said in every head again', catches: 'Z26',
    from: '        if (k > 0 && parts[k - 1].step === p.step) {', to: '        if (false) {' },
  { id: 'NZ14', what: 'the axis scrolled past either end of the box', catches: 'Z28',
    from: '  return Math.max(0, Math.min(scrollWidth - boxWidth, Math.round(want)));', to: '  return Math.round(want);' },
  { id: 'NZ13', what: 'no step row', catches: 'Z27',
    from: '    thead.append(band, ...(section.parts.some((p) => p.step) ? [steps] : []), head);', to: '    thead.append(band, head);' },
  { id: 'NZ7', what: 'several values on one line again', catches: 'Z24',
    from: '      if (cell.rest) {', to: '      if (false) {' },
  { id: 'NZ8', what: 'one band colour for both signs', catches: 'Z25',
    from: "`wk-sidehead ${cls}${pair && i === 0 ? ' is-left' : ''}`", to: "'wk-sidehead'" },
  { id: 'NZ9', what: 'the empty-column press does nothing', catches: 'Z26',
    from: 'if (state.emptyOpen.has(section.type)) state.emptyOpen.delete(section.type); else state.emptyOpen.add(section.type);', to: '' },
  { id: 'NZ10', what: 'Copy id in words again', catches: 'Z16',
    from: "copy.append(el(doc, 'span', 'wk-copyicon'));", to: "copy.append(el(doc, 'span', 'wk-copyicon', 'Copy id'));" },
  { id: 'NZ6', what: 'the filter draws every row', catches: 'Z14',
    from: '    const rows = rowsShown(section, state.rowFilter);', to: "    const rows = rowsShown(section, 'all');" },
  { id: 'CPm4', what: 'the copy without the folded columns', catches: 'CP3',
    from: 'build(new Set([...state.emptyOpen, section.type]))', to: 'build(state.emptyOpen)' },
  { id: 'CPm5', what: 'the copy ignores the filter', catches: 'CP3',
    from: 'sheetOf(full, state.rowFilter)', to: 'sheetOf(full)' },
  { id: 'CPm6', what: 'a copy that failed said as done', catches: 'CP4',
    from: ': COPY_WORDS.failed;', to: ': COPY_WORDS.done(sheet.rows.length, unit);' },
  // 🔴 THE ONE THE RULING ASKED FOR: a copy put back. Same sections, same rows, same counts.
  { id: 'M1', what: 'the renderer names its own columns again',
    catches: 'V2 the column labels',
    from: "      for (const p of parts) head.append(el(doc, 'th', cls, p.leaf));",
    to: "      for (const p of parts) head.append(el(doc, 'th', cls, p.step || p.leaf));" },
  // 🔴 THIS SLOT HELD AN EQUIVALENT MUTANT, AND THE HARNESS SAID SO. It was `cell.text || ''`,
  //    meant to collapse 0 into a blank -- but `cell.text` is already a STRING and '0' is
  //    truthy, so it changed nothing and ESCAPED. The rule it aimed at (0 is a value, absent is
  //    a blank) moved into `table_view.valueText` with the half being scored, and the renderer
  //    no longer HAS a raw value to collapse. Re-anchored rather than chased with a weaker
  //    assertion: the cells drawn in the wrong order. Same count, nothing thrown.
  { id: 'M2', what: 'the cells are drawn in the wrong order',
    catches: 'V3 every cell is the view',
    from: '        for (const cell of cells(i)) {',
    to: '        for (const cell of [...cells(i)].reverse()) {' },
  { id: 'M3', what: 'the numeric class is dropped',
    catches: 'V5 the numeric class',
    from: "`${cell.numeric ? 'wk-num ' : ''}${cls}`",
    to: "`${cls}`" },
  { id: 'HM1', what: 'the server\'s sentence not in the head', catches: 'H1',
    from: "      if (r.message) head.append(el(doc, 'span', 'wk-note wk-said', [r.state, r.message].filter(Boolean).join(' · ')));\n", to: '' },
  { id: 'EAm1', what: 'the first walk\'s table without its starts', catches: 'EA1',
    from: '    state.asked = { ...asked, keys: { ...asked.keys }, positive: starts.positive, negative: starts.negative };',
    to: '    state.asked = { ...asked, keys: { ...asked.keys } };' },
  { id: 'M4', what: 'the cap note prints the total instead of what was hidden',
    catches: 'C3 the total is not what is printed',
    from: '      box.append(el(doc, \'div\', \'wk-note\', `${view.hidden} more not drawn`));',
    to: '      box.append(el(doc, \'div\', \'wk-note\', `${view.shown + view.hidden} more not drawn`));' },
  { id: 'M6', what: 'the type placeholder carries its text as its value again',
    catches: 'P1 picking the placeholder',
    from: "    none.value = '';\n", to: '' },
  // ── 29cee1d47 ────────────────────────────────────────────────────────────────────────
  { id: 'M7', what: 'the list is drawn from what touches the start type again, as before 10-06',
    catches: 'F1 defect@1',
    from: '  const followOptions = () => followChoices(allPredicates(), allPredicates(), state.follow);',
    to: '  const followOptions = () => followChoices(declaredPredicates().filter((p) => !state.type'
      + ' || (p.subjects || []).includes(state.type) || ((p.object || {}).types || []).includes(state.type))'
      + '.map((p) => p.name), allPredicates(), state.follow);' },
  { id: 'M11', what: 'a type change drops the ticks again',
    catches: 'F8 changing the type',
    from: '        Object.entries(state.keys).filter(([k]) => allowedKeys.has(k)));',
    to: '        Object.entries(state.keys).filter(([k]) => allowedKeys.has(k))); state.follow = new Set();' },
  { id: 'M8', what: 'a type picked opens no box',
    catches: 'F2 the seed field',
    from: '      void openSearch();\n', to: '' },
  // M9 (an empty list read as not read to the end) is the search box's now: node_search_harness NS5.
  // ── lead 53050a4ec: the table's continue ────────────────────────────────────────────────
  // The board's markingIntent on the walk page (lead 10-09).
  { id: 'SM2', what: 'the table walks the form\'s subject alone, not the starts', catches: 'S1',
    from: '    const asked = { ...spec(), ...(one ? { type: one.type, keys: { ...one.keys } } : {}), ...(signed ? starts : {}) };', to: '    const asked = spec();' },
  { id: 'SM3', what: 'a check takes no sign from Shift', catches: 'S3',
    from: "markings.toggle(checks, id, markingIntent(event).sign); render(); });", to: "markings.toggle(checks, id, SIGN.CASE); render(); });" },
  { id: 'SM4', what: 'Next drops the - rows', catches: 'S4',
    from: 'stepAlong({ positive: seeds.positive, negative: seeds.negative,', to: 'stepAlong({ positive: seeds.positive,' },
  { id: 'NM1', what: 'the Next walks from every row of the section, not the checked ones', catches: 'N2',
    from: '    const seeds = seedsOf(section.rows.map((row) => [row.id, markings.signOf(checks, row.id)]));',
    to: '    const seeds = { positive: section.rows.map((row) => row.id), negative: [] };' },
  { id: 'NM2', what: 'a press with nothing checked still asks', catches: 'N2',
    from: "      go.addEventListener('click', () => { if (seeds.positive.length) void walkOn(at, seeds, route); });",
    to: "      go.addEventListener('click', () => { void walkOn(at, seeds, route); });" },
  { id: 'NM3', what: 'the next step builds its own walk instead of the one step', catches: 'N4',
    from: '    const asked = { ...knobs(), ...stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to }) };',
    to: '    const asked = { positive: seeds.positive, follow: [route.predicate] };' },
  // stepAlong's own default ('both') is imported by main.js and not swapped by this loader; the call site stands in.
  { id: 'NM7', what: 'the Next walks one way only', catches: 'N8',
    from: '    const asked = { ...knobs(), ...stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to }) };',
    to: "    const asked = { ...knobs(), ...stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to, direction: 'outgoing' }) };" },
  { id: 'EKm1', what: 'a Next without the form\'s knobs - a cut answer cut elsewhere', catches: 'EA1',
    from: '    const asked = { ...knobs(), ...stepAlong(', to: '    const asked = { ...stepAlong(' },
  { id: 'EKm2', what: 'a Next walks the form\'s hops, not one step', catches: 'EA1',
    from: NEXT_ASK, to: NEXT_ASK.replace('{ ...knobs(), ...stepAlong(', '{ ...stepAlong(').replace('farType: route.to }) };', 'farType: route.to }), ...knobs() };') },
  { id: 'NM4', what: 'the checks are kept apart from the graph\'s marking', catches: 'N3',
    from: "  const checksOf = (at) => (at === 0 ? state.marks : stepOf(at).marks);", to: '  const checksOf = (at) => `table-${at}`;' },
  { id: 'FM1', what: 'a step\'s marking named by its place again', catches: 'CH2',
    from: "reason: '', marks: nextMarks() };", to: "reason: '', marks: `walk-${at + 3}` };" },
  { id: 'FM2', what: 'a step walked again leaves the dropped steps\' markings', catches: 'CH2',
    from: '    dropMarks(dropped);\n', to: '' },
  { id: 'GM1', what: 'another edge from a step walks over its sibling', catches: 'GB1',
    from: '    const again = state.steps.find((s) => s.parent === at && s.title === title);', to: '    const again = state.steps.find((s) => s.parent === at);' },
  { id: 'GM2', what: 'the graph\'s chain every step, not the branch\'s', catches: 'GB2',
    from: '    const names = [START, state.marks, ...pathTo(state.leaf).map((s) => s.marks)];', to: '    const names = [START, state.marks, ...state.steps.map((s) => s.marks)];' },
  { id: 'GM3', what: 'the same edge again walks every branch from that step again', catches: 'GB3',
    from: '    const dropped = again ? subtree(again.id) : [];', to: '    const dropped = again ? state.steps.filter((s) => s.parent === at).flatMap((s) => subtree(s.id)) : [];' },
  { id: 'GM4', what: 'a tab off the branch shows its step and leaves the branch', catches: 'GB2',
    from: '          if (!branch.includes(id)) state.leaf = id;\n', to: '' },
  { id: 'NM5', what: 'a new start keeps the steps', catches: 'N7',
    from: '    state.steps = []; state.at = 0; state.leaf = 0; state.marks = nextMarks();\n', to: '    state.marks = nextMarks();\n' },
  { id: 'NM6', what: 'a step pressed does not go back', catches: 'N6',
    from: "          state.at = id;\n",
    to: "" },
  // 🔴 CONTROL: a comment cannot change an answer. If this reddens something, the harness is
  //    reading text rather than behaviour.
  { id: 'M5', what: 'CONTROL: a comment line is removed', control: true,
    from: '// 🔴 C-72. 표의 «결정»은 전부 여기 있고 이 파일에는 DOM 쓰기만 남습니다.',
    to: '//' },
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
  { baselineRan: suiteRan, baselineNames: base.names,
    title: `${LF}== defect mutants (each must be CAUGHT by the check it names) ==` });
const controls = await scoreMutants(MUTANTS.filter((m) => m.control), runMutant,
  { mustCatch: false, baselineRan: suiteRan, baselineNames: base.names,
    title: `${LF}== controls (each must wake NOTHING) ==` });

// table_view.js's own: the fold of several edges into one node.
const TV_SRC = path.join(HERE, '..', 'src', 'walk', 'table_view.js');
const TV_MUTANTS = [
  { id: 'CPm1', what: 'several values copied as the first alone', catches: 'CP1',
    from: "cell.values ? cell.values.join('; ')", to: 'cell.values ? cell.values[0]' },
  { id: 'CPm2', what: 'Δ copied in its words, not its number', catches: 'CP1',
    from: ': String(d.value)));', to: ': d.text));' },
  { id: 'CPm3', what: 'every row shown whatever the filter', catches: 'CP2',
    from: "filter === 'all' || (filter === 'differs' ? row.differs : row.missing)", to: 'true' },
  { id: 'DM1', what: 'reached by both said A only', catches: 'ZD1',
    from: "const reachedBy = (inA, inB) => (inA && inB ? 'ab' : inB ? 'b' : 'a');", to: "const reachedBy = (inA, inB) => (inA ? 'a' : inB ? 'b' : 'ab');" },
  { id: 'DM2', what: 'B\'s nodes not merged into the rows', catches: 'ZD1',
    from: '  const walked = control ? mergeWalks(result, control) : result;', to: '  const walked = result;' },
  { id: 'DM3', what: 'a side coloured by the + side\'s B', catches: 'ZD3',
    from: 'reachedBy(g.a.has(node.id), g.b.has(node.id))', to: 'reachedBy(g.a.has(node.id), groups[0].b.has(node.id))' },
  { id: 'DM4', what: 'no B line under Route', catches: 'ZD3',
    from: 'sources: [`B · ${sourcesB.route(g, id).text}`] }', to: 'sources: [] }' },
  { id: 'DM5', what: 'a value only B brought says A\'s source', catches: 'ZD3',
    from: 'byB(g, id) && !g.a.has(id) ?', to: 'false ?' },
  { id: 'DM6', what: 'no B, rows said reached anyway', catches: 'ZD2',
    from: 'a: g.inside, b: groupsB[i].inside })) : groupsA;', to: 'a: g.inside, b: groupsB[i].inside })) : groupsA.map((g) => ({ ...g, a: g.inside, b: new Set() }));' },
  { id: 'ZM1', what: 'the rows only those the first group reached', catches: 'Z2',
    from: '  const members = nodes.filter((n) => groups.some((g) => g.inside.has(n.id)));',
    to: '  const members = nodes.filter((n) => groups[0].inside.has(n.id));' },
  { id: 'ZM2', what: 'the node\'s own columns a group\'s, not the centre\'s', catches: 'Z17',
    from: '    const ownAll = all.filter((c) => !c.steps.length);\n    const ownCells = rows.map((node) => ownAll.map((c) => cellOf(index, new Set([node.id]), node.id, c)));\n    const sideAll = all.filter((c) => c.steps.length);',
    to: '    const ownAll = [];\n    const ownCells = rows.map(() => []);\n    const sideAll = all;' },
  // ⚰️ ZM3 (groups even without a − start) retired 10-11: E1 made that the rule - a + only walk is one side (Z1).
  { id: 'ZM3', what: 'a + only walk read as two sides', catches: 'Z1 ',
    from: "...(negative.length ? [{ name: '−', starts: negative }] : [])", to: "{ name: '−', starts: negative }" },
  { id: 'ECm1', what: '«Conflicts» not carried', catches: 'EC1',
    from: ".filter((c) => c.kind === 'conflicts' || c.kind === 'absence')", to: ".filter((c) => c.kind === 'absence')" },
  { id: 'ECm2', what: 'the confirmation predicate\'s column not carried', catches: 'EC2',
    from: ".filter((c) => c.kind === 'conflicts' || c.kind === 'absence')", to: ".filter((c) => c.kind === 'conflicts')" },
  { id: 'ZM4', what: 'no delta column', catches: 'Z12',
    from: '  const deltas = groups.length === 2 ? columns.map', to: '  const deltas = false ? columns.map' },
  { id: 'ZM5', what: 'reached but no value drawn missing', catches: 'Z4',
    from: '  if (!values.length) return { text: EMPTY };', to: '  if (!values.length) return { text: MISSING, missing: true };' },
  { id: 'ZM6', what: 'several values: the first alone', catches: 'Z6',
    from: '  if (values.length === 1 && !cell.more)', to: '  if (values.length >= 1 && !cell.more)' },
  { id: 'ZM7', what: 'no Route head', catches: 'Z8',
    from: '    const heads = [...columnHeads, ROUTE];', to: '    const heads = [...columnHeads];' },
  // RM6 («Δ <head>» read from heads) retired with Route moved to the outer end: heads[c] is columnHeads[c] again, the
  // mutant changes nothing (Z37 stays, guarding the order).
  { id: 'VS1', what: 'a value\'s source the row\'s node, not the read\'s', catches: 'Z38',
    from: '(byCol[i].nodes || []).map((id) => sources.source(g, id))', to: '(byCol[i].nodes || []).map(() => sources.source(g, node.id))' },
  { id: 'VS2', what: 'a value\'s source without its route', catches: 'Z40',
    from: 'source: (g, id) => `${keyWords(id)} · ${g ? route(g, id).text : NOT_WALKED}`', to: 'source: (g, id) => `${keyWords(id)}`' },
  { id: 'VS3', what: 'a source from the other side\'s paths', catches: 'Z38',
    from: 'sources: (byCol[i].nodes || []).map((id) => sources.source(g, id))', to: 'sources: (byCol[i].nodes || []).map((id) => sources.source(groups[(i + 1) % groups.length], id))' },
  { id: 'VS4', what: 'a node the answer did not send: its keys not read off its id', catches: 'Z42',
    from: '    const node = nodes.get(id) || entityOfId(id) || {};', to: '    const node = nodes.get(id) || {};' },
  { id: 'VS5', what: 'a source without keys or a label says its id', catches: 'Z43',
    from: "    return said.length ? said.join(' / ') : (node.label || EMPTY);", to: "    return said.length ? said.join(' / ') : (node.label || id);" },
  { id: 'RM1', what: 'a side reads the other side\'s paths', catches: 'Z29',
    from: '.filter((path) => g.starts.includes(path.seed))', to: '.filter((path) => !g.starts.includes(path.seed))' },
  { id: 'RM2', what: 'a start says nothing', catches: 'Z29',
    from: '    if (g.starts.includes(id)) return { text: STARTED };\n', to: '' },
  { id: 'RM3', what: 'a path\'s hops read backwards', catches: 'Z29',
    from: 'path.hops.slice(1).map(', to: 'path.hops.slice(1).reverse().map(' },
  { id: 'RM4', what: 'two paths walked: the first alone', catches: 'Z31',
    from: 'return ways.length ? cellWords({ values: ways }', to: 'return ways.length ? cellWords({ values: ways.slice(0, 1) }' },
  { id: 'RM5', what: 'no Route cell under its head', catches: 'Z29',
    from: ' })), routeCell(g, node.id)];', to: ' }))];' },
  { id: 'ZM8', what: 'an added column dropped', catches: 'Z18',
    from: ', ...(added.get(type) || [])];', to: '];' },
  { id: 'ZM9', what: 'a difference keeps its float tail', catches: 'Z19',
    from: '  const n = Number(delta.toPrecision(10));', to: '  const n = delta;' },
  { id: 'ZM10', what: 'a side that did not reach: a missing cell a column again', catches: 'Z21',
    from: '        if (!g.inside.has(node.id)) return [{ text: MISSING, missing: true, span: heads.length }];\n', to: '' },
  { id: 'ZM11', what: 'the columns in their found order, numbers anywhere', catches: 'Z22',
    from: "\n      .sort((p, q) => (kindsAll[q] === 'number') - (kindsAll[p] === 'number'));", to: ';' },
  { id: 'ZM12', what: 'an empty column drawn', catches: 'Z23',
    from: '.filter((c) => keep || !sideEmpty[c])', to: '.filter(() => true)' },
  // ⚰️ QM1 (the flat table's fold: the last edge's value) retired 10-11 with qualifiersByNode (E1); every value kept is
  //    the walk table's cell now - Q1, Z6 and ZM6.
];
const tv = await scoreMutants(TV_MUTANTS, async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  const loaded = await loadWithProbe(TV_SRC, {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  qualifierSuite(loaded.module);
  sideSuite(loaded.module);
  return { ran, names: NAMES.slice(), failures: failures.slice() };
}, { baselineNames: base.names, title: `${LF}== table_view mutants (each must be CAUGHT by the check it names) ==` });

const all = MUTANTS.length + TV_MUTANTS.length;
const scored = all - defects.wrong - controls.wrong - tv.wrong;
console.log(`${LF}  ${scored}/${all} scored as intended.`);
const failed = base.failed + (all - scored);
console.log(`ASSERTIONS ${base.ran + all} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
