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
import { DWELL_MS, IMAGE_ROUTE } from '../src/image_preview.js';
import { WALK_CSS } from '../src/walk/styles.js';

// The stylesheet FW1 reads - a styles.js mutant swaps it for its own (owner 10-12: fixed widths).
let CSS_NOW = WALK_CSS;

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'walk', 'main.js');
const LF = String.fromCharCode(10);

// ── the smallest document `boot()` actually needs ────────────────────────────────────────
// Measured, not guessed: `createElement` · `append` · `textContent` · `className` ·
// `setAttribute` · `addEventListener` · `value` · `checked` · `type`, plus a `head` for
// `ensureWalkStyles`. Nothing else is touched, which is what makes this cheap.
function makeDoc() {
  const make = (tag) => option(tag, {
    tagName: tag, children: [], attrs: {}, listeners: {}, style: {}, ownerDocument: doc,
    className: '', value: '', checked: false, type: '', _text: '',
    append(...cs) { cs.forEach((c) => this.children.push(c)); },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    // The image cell and its preview (IM1): a mark hidden by style, a picture's address taken back on leave.
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
  });
  // A section's Trend draws an SVG (lead 10-11 W addendum 7: its rows the table's shown) - the same node, its class an
  // attribute as the browser keeps it.
  const doc = { createElement: make, createElementNS: (ns, tag) => make(tag) };
  doc.head = make('head');
  doc.body = make('body');
  return doc;
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

// The walk's judgment (owner 10-12): «does a shortest path reach the auxiliary node(s)», yes · hops / no / unknown - a fake
// answer in the server's shape (implementer, lead 10-12): each node its «aux», the answer's «aux» the seeds.
const JUDGED = { ...RESULT,
  nodes: RESULT.nodes.map((n) => ({ ...n, aux: { 'n:1': { state: 'found', hops: 2, via: 'q:aux' }, 'n:2': { state: 'none' }, 'n:3': { state: 'unknown' } }[n.id] })),
  aux: { seeds: ['q:aux'], complete: true, truncated: null, hops_reached: 2 } };

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
const DECL_RT = { ok: true,
  entities: [{ type: 'wafer@1', keys: ['wafer'] }, { type: 'lot@1', keys: ['lot'] }, { type: 'die@1', keys: ['mat_id'] }],
  predicates: [{ name: 'in@1', subjects: ['wafer@1'], object: { types: ['lot@1'] } }, { name: 'has@1', subjects: ['lot@1'], object: { types: ['die@1'] } },
    { name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } }] };
// The single way listed first, so a list in its own order says nothing about the order asked.
const WALKED = { nodes: [{ id: 's:a', type: 'wafer@1', keys: { wafer: 'A' } }, { id: 'l:1', type: 'lot@1', keys: { lot: 'L' } },
  { id: 'd:1', type: 'die@1', keys: { mat_id: 'M-1' } }, { id: 'd:2', type: 'die@1', keys: { mat_id: 'M-2' } }, { id: 'd:3', type: 'die@1', keys: { mat_id: 'M-3' } }],
  edges: [], propagation: { ranked: [
    { id: 'd:3', evidence: [{ seed: 's:a', hops: [{ id: 's:a' }, { id: 'd:3', predicates: ['inspected@1'] }] }] },
    { id: 'd:1', evidence: [{ seed: 's:a', hops: [{ id: 's:a' }, { id: 'l:1', predicates: ['in@1'] }, { id: 'd:1', predicates: ['has@1'] }] }] },
    { id: 'd:2', evidence: [{ seed: 's:a', hops: [{ id: 's:a' }, { id: 'l:1', predicates: ['in@1'] }, { id: 'd:2', predicates: ['has@1'] }] }] },
    { id: 'l:1', evidence: [{ seed: 's:a', hops: [{ id: 's:a' }, { id: 'l:1', predicates: ['in@1'] }] }] }] } };
// Long by side (owner 10-12): one quantity both baskets reached, measured from 3 + wafers, 5 − wafers and one wafer each
// basket reached (a shared lot's) - a record's side is its way's, not the quantity's.
const LS_PLUS = ['p:1', 'p:2', 'p:3'];
const LS_MINUS = ['m:1', 'm:2', 'm:3', 'm:4', 'm:5'];
const LS_DECL = { ok: true, entities: [{ type: 'wafer@1', keys: ['wafer'] }, { type: 'quantity@1', keys: ['quantity'] }],
  predicates: [{ name: 'measures@1', subjects: ['wafer@1'], object: { types: ['quantity@1'] } }] };
const LS = {
  nodes: [{ id: 'q', type: 'quantity@1', label: 'bond_temp', keys: { quantity: 'bond_temp' } },
    ...[...LS_PLUS, ...LS_MINUS, 'w:s'].map((id) => ({ id, type: 'wafer@1', label: id, keys: { wafer: id } }))],
  edges: [...LS_PLUS, ...LS_MINUS, 'w:s'].map((id, i) => ({ id: `ms:${id}`, source: id, target: 'q', predicate: 'measures', qualifiers: { value: 20 + i } })),
  propagation: { ranked: [{ id: 'q', reach: [3, 5] }, { id: 'w:s', reach: [1, 1] }] },
};
const LS_STARTS = { positive: LS_PLUS, negative: LS_MINUS };
// Long a line a record (lead 10-12 C3, rehearsal SYN-CW-001-02): one + wafer's edge two atoms (the answer's `records`) - CLEAN
// 300 and ETCH 90, each its own time and point; the shared wafer's one record reached from both sides.
const lsRecord = (claim, value, at, step) => ({ claim_id: claim, occurred_at: at, world: 'default', qualifiers: { value, ...(step ? { step } : {}) } });
const LS_RECORDS = { ...LS, edges: LS.edges.map((e) => (e.id === 'ms:p:1'
  ? { ...e, qualifiers: { value: 300, step: 'CLEAN' }, records: [lsRecord('c:1', 300, '2026-08-06T21:02:00+00:00', 'CLEAN'), lsRecord('c:2', 90, '2026-08-06T19:32:00+00:00', 'ETCH')] }
  : e.id === 'ms:w:s' ? { ...e, records: [lsRecord('c:s', 28, '2026-08-06T10:00:00+00:00')] } : e)) };
// Sort · filter · bulk select (lead 10-11 W addendum 7): one + wafer and more dies than a pick lists (PICK_MOST + 2, read off
// the module) - mat_id M-1 …, a grade A · B · none, a gate each - numbers that sort otherwise as words (2 · 9 · 10 · 100),
// two dies with none - and a point beside it (Split by, addendum 2 ⑭), every edge at its own hour.
const SF_GATES = [10, 9, 100, 2, null, 7, 3, null, 11, 1, 50, 8, 4, 6, 5, 12];
const sfAnswer = (n) => ({
  generated_at: '2026-10-02T00:00:00+00:00',
  nodes: [{ id: 'sw', type: 'wafer@1', label: 'SW', keys: { wafer: 'SW' } },
    ...Array.from({ length: n }, (_, i) => ({ id: `sd:${i + 1}`, type: 'die@1', label: `SD${i + 1}`, keys: { mat_id: `M-${i + 1}` },
      attributes: i % 3 === 2 ? {} : { grade: i % 3 === 0 ? 'A' : 'B' } }))],
  edges: Array.from({ length: n }, (_, i) => ({ id: `sf:${i + 1}`, source: 'sw', target: `sd:${i + 1}`, predicate: 'inspected',
    occurred_at: `2026-10-01T${String(i % 24).padStart(2, '0')}:00:00+00:00`,
    qualifiers: { ...(SF_GATES[i] === null ? {} : { gate: SF_GATES[i] }), point: ['C', 'T', 'L'][i % 3] } })),
});
const SF_STARTS = { positive: ['sw'], negative: [] };
const SF_DECL = { ok: true, entities: DECL.entities, predicates: [{ name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } }] };
const SF_ASC = '1,2,3,4,6,7,8,9,10,11,50,100,,';
const SF_DESC = '100,50,11,10,9,8,7,6,4,3,2,1,,';
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
  words: ['of ← measurement@1', 'value'] }]]]);
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
const valsOf = (c) => walkAll(c || { children: [] }).filter((k) => k.className === 'wk-val').map((k) => k._text).join(' · ');
const srcsOf = (c) => ((c && c.children) || []).filter((k) => k.className === 'wk-src').map((k) => k._text);
/** A row's value cells as Wide draws them (lead 10-11 W): each column its groups' cells, Δ between two. */
const sideCells = (r) => r.cells.flatMap((c) => (c.sides.length === 2 && c.delta ? [c.sides[0], c.delta, c.sides[1]] : c.sides));
/** A node cell's name, without the source line under it. */
const labelOf = (c) => walkAll(c).filter((k) => k.className === 'wk-centrelabel').map((k) => k._text).join('');
/** A head as one line. A group's (owner 10-12) draws its far end, then its way and leaf: read as its whole - «<way>
 *  <far> · <leaf>», its tags after - when the two drawn lines and its title say the same; else as drawn. */
const headSaid = (th) => {
  const text = th.children.find((c) => c.className === 'wk-headtext');
  if (!text) return th.textContent;
  const [far = '', via = ''] = text.children.map((c) => c.textContent);
  const way = (/^.*[→←]/.exec(via) || [''])[0];
  const whole = [way ? `${way} ${far}` : far, via.slice(way.length).replace(/^ · /, '')].filter(Boolean).join(' · ');
  if (!far || whole !== th.title) return th.textContent;
  return whole + th.children.filter((c) => c !== text).map((c) => c.textContent).join('');
};
// A die's gate, read in from the wafers that inspected it: one group, its far type (lead 10-11 W addendum 8 (다)).
const GATE_IN = 'inspected ← wafer@1 · gate';
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
  return { host, handle, doc };
}

const has = (e, cls) => String(e.className || '').split(/\s+/).includes(cls);
const TABLE = await import('../src/walk/table_view.js');

// 60 ways from one wafer to one quantity, then two from it on (lead 10-13, the owner's «values cut»: 50 of 2,199 drawn).
const WIDE = { nodes: [{ id: 'w', type: 'wafer', label: 'W', depth: 0 }, { id: 'q', type: 'quantity', label: 'temp', depth: 1 },
  { id: 'u1', type: 'unit', label: 'U1', depth: 2 }, { id: 'u2', type: 'unit', label: 'U2', depth: 2 }],
edges: [...Array.from({ length: 60 }, (_, i) => ({ id: `m${i}`, source: 'w', target: 'q', predicate: 'measures', qualifiers: { value: i },
  occurred_at: `2026-10-01T00:00:${String(i).padStart(2, '0')}Z` })),
  { id: 'k1', source: 'q', target: 'u1', predicate: 'in_unit', qualifiers: {} }, { id: 'k2', source: 'q', target: 'u2', predicate: 'in_unit', qualifiers: {} }] };
const WIDE_STARTS = { positive: ['w'], negative: [] };

async function suite(mod) {
  const { host } = await render(mod);
  const view = walkTableView(RESULT, DECL.entities);

  console.log(`${LF}-- the page draws the view's answer, not its own --`);
  eq('V1 one section head per section, worded by the view',
    byClass(host, 'wk-sechead').map((e) => e.textContent).join(' | '),
    view.sections.map((s) => s.heading).join(' | '));
  // The judged walk on the page (owner 10-12): the bar's auxiliary nodes go with the walk, the section offers «Reaches only».
  {
    const pageOf = async () => {
      const doc = makeDoc();
      const host = doc.createElement('div');
      const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
      await settle();
      Object.assign(handle.state, { type: 'die@1', asked: { type: 'die@1', keys: { mat_id: 'M-1' } }, run: 'done', result: JUDGED });
      handle.render();
      return { host, handle };
    };
    const one = await pageOf();
    const two = await pageOf();
    const before = Object.prototype.hasOwnProperty.call(one.handle.spec(), 'aux');
    one.handle.graph.markings.set('walk-reach', 'q:aux', SIGN.CASE);
    const chips = (h) => walkAll(h).filter((e) => e.attrs && e.attrs['data-reach']).map((e) => e.attrs['data-reach']);
    ok('AX3 an auxiliary node picked goes with the walk (aux) and says itself in the bar; none picked, nothing sent',
      !before && JSON.stringify(one.handle.spec().aux) === '["q:aux"]' && chips(one.host).join() === 'q:aux',
      JSON.stringify([before, one.handle.spec().aux, chips(one.host)]));
    ok('AX4 two pages: the other page\'s walk carries no auxiliary node and its bar says none',
      !Object.prototype.hasOwnProperty.call(two.handle.spec(), 'aux') && chips(two.host).length === 0,
      JSON.stringify([two.handle.spec().aux, chips(two.host)]));
    const press = (e) => { for (const fn of (e && e.listeners && e.listeners.click) || []) fn({}); };
    const ids = () => walkAll(one.host).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).map((e) => e.attrs['data-row-id']);
    const all = ids();
    press(walkAll(one.host).find((e) => String(e.className || '').includes('wk-reachonly')));
    ok('AX5 the page: the die section\'s «Reaches only» pressed, its table the yes row alone; the other sections as they were',
      all.includes('n:2') && !ids().includes('n:2') && ids().includes('n:1') && ids().includes('n:3'),
      `${all.join()} -> ${ids().join()}`);
    const onRule = ((CSS_NOW.replace(/\/\*[\s\S]*?\*\//g, ' ').split('}').map((r) => r.split('{'))
      .find(([sel]) => sel && sel.trim() === '.wk-reachonly.is-on') || [])[1] || '');
    const pressed = walkAll(one.host).find((e) => String(e.className || '').includes('wk-reachonly'));
    ok('AX6 «Reaches only» on says so: pressed, its class is-on, and the stylesheet fills it as a segment on is',
      Boolean(pressed) && String(pressed.className).includes('is-on') && /background:\s*var\(--accent\)/.test(onRule),
      `${pressed && pressed.className} | ${onRule}`);
    // «Reaches only» is on in the die section here: its tally still counts its «none» row.
    const tallies = walkAll(one.host).filter((e) => e.className === 'wk-reachtally').map((e) => e._text);
    ok('AX7 each judged section says its rows\' judgments as counts beside «Reaches only», every row and not the shown ones',
      JSON.stringify(tallies) === JSON.stringify(['→ q:aux: 1 reach · 1 none · 0 unknown', '→ q:aux: 0 reach · 0 none · 1 unknown']),
      JSON.stringify(tallies));
    const tallyRule = ((CSS_NOW.replace(/\/\*[\s\S]*?\*\//g, ' ').split('}').map((r) => r.split('{'))
      .find(([sel]) => sel && sel.trim() === '.wk-reachtally') || [])[1] || '');
    ok('AX8 the counts drawn in the body\'s size and colour, not the small grey words',
      /font-size:\s*var\(--wk-fs-body\)/.test(tallyRule) && /color:\s*var\(--text\)/.test(tallyRule), tallyRule);
    // Two auxiliary nodes: the judgment's head an auxiliary node a line, its whole in the title.
    const twoAux = { ...JUDGED, aux: { ...JUDGED.aux, seeds: ['q:aux', 'q:aux2'] } };
    const three = await pageOf();
    Object.assign(three.handle.state, { result: twoAux });
    three.handle.render();
    const judgedHead = walkAll(three.host).find((e) => e.tagName === 'th' && String(e.title || '').startsWith('→'));
    const drawnLines = judgedHead ? walkAll(judgedHead).filter((e) => e.className === 'wk-headfar').map((e) => e._text) : [];
    const twoView = walkTableView(twoAux, DECL.entities).sections.find((x) => x.type === 'die@1') || {};
    ok('AX9 two auxiliary nodes: the judgment\'s head drawn a node a line, whole in its title; one node, its one line as text',
      JSON.stringify(drawnLines) === '["→ q:aux","→ q:aux2"]' && judgedHead.title === '→ q:aux · q:aux2'
        && JSON.stringify((twoView.centreLines || []).slice(-1)) === '[["→ q:aux","→ q:aux2"]]'
        && !walkAll(one.host).some((e) => e.tagName === 'th' && String(e.title || '').startsWith('→') && walkAll(e).some((c) => c.className === 'wk-headfar')),
      JSON.stringify([drawnLines, judgedHead && judgedHead.title, twoView.centreLines]));
    // Two auxiliary nodes with long names: the judgment's cells «2 hops → <the node>» read whole, as the node column's keys.
    const LONG = ['q:aux-with-a-long-key-01', 'q:aux-with-a-long-key-02'];
    const longAux = { ...JUDGED, aux: { ...JUDGED.aux, seeds: LONG },
      nodes: JUDGED.nodes.map((n) => (n.aux && n.aux.state === 'found' ? { ...n, aux: { ...n.aux, via: LONG[0] } } : n)) };
    const four = await pageOf();
    Object.assign(four.handle.state, { result: longAux });
    four.handle.render();
    const longest = `2 hops → ${LONG[0]}`;
    const widths = walkAll(four.host).filter((e) => e.tagName === 'col').map((e) => String((e.attrs && e.attrs.style) || ''));
    const drawnLong = walkAll(four.host).some((e) => e.tagName === 'td' && labelOf(e) === longest || (e._text === longest));
    ok('AX10 long auxiliary names: the judgment\'s column as wide as its longest cell, not cut at the value columns\' far end',
      widths.some((w) => w.includes(`calc(${[...longest].length + 1}ch`)) && !widths.some((w) => /calc\(18ch \+ 2 \* var\(--space-2\)\), calc\(18ch/.test(w)),
      JSON.stringify([longest.length, drawnLong, widths]));
  }
  // Wide (lead 10-11 W): a section's heads say its node columns, each group's step and far end, its values' names; a
  // row's cells its node's, then each column's groups' cells, a cell drawn as its value line.
  const heads = byTag(host, 'thead').map((t) => walkAll(t).filter((c) => c.tagName === 'th' && c.className !== 'wk-check').map(headSaid).join(' '));
  const drawn = byTag(host, 'tbody').flatMap((b) => b.children.map((tr) => tr.children.filter((c) => c.className !== 'wk-check')));
  const said = (c) => (has(c, 'wk-centre') ? labelOf(c) : valsOf(c));
  ok('V2 the heads say the view\'s words: its node columns, each group\'s step and far end, each value\'s name',
    view.sections.every((s, i) => [...s.centreHeads, ...s.parts.flatMap((x) => [x.step, x.leaf])].every((w) => heads[i].includes(w))),
    heads.join(' | '));
  eq('V3 every cell is the view\'s text, in the view\'s order',
    drawn.map((cells) => cells.map(said).join('|')).join(' / '),
    view.sections.flatMap((s) => s.rows.map((r) => [...r.centre, ...sideCells(r)].map((c) => c.text).join('|'))).join(' / '));
  // 🔴 0 IS A VALUE. `x: 0` in the fixture is the discriminant: a renderer using `v || ''`
  //    draws it as the same mark an absent key gets, and the row then lies about the die.
  ok('V4 a zero is drawn as 0 and an absent key as «—», not as the same glyph',
    drawn.flat().map(said).includes('0') && drawn.flat().map(said).includes(TABLE.EMPTY), drawn.flat().map(said).join('|'));
  eq('V5 the numeric class follows the view\'s reading of each cell',
    drawn.map((cells) => cells.filter((c) => !has(c, 'wk-centre')).map((c) => (has(c, 'wk-num') ? 1 : 0)).join('')).join(' / '),
    view.sections.flatMap((s) => s.rows.map((r) => sideCells(r).map((c) => (c.numeric ? 1 : 0)).join(''))).join(' / '));
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
    // The adds sit in «+ Add start» (lead 10-11 W A), one per sign.
    const plus = (sign) => click(walkAll(host).find((e) => e.className === 'wk-basketadd' && e.attrs['data-sign'] === sign));
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

  console.log(`${LF}-- Walk ▸ and Continue: the bar's walk from other starts (owner 10-12) --`);
  {
    const { entitySeedId } = await import('../src/rnd_board/api.js');
    const DECLS = { ok: true,
      entities: [{ type: 'die@1', keys: ['mat_id'] }, { type: 'wafer@1', keys: ['wafer'] }],
      predicates: [{ name: 'inspected@1', subjects: ['wafer@1'], object: { types: ['die@1'] } }] };
    const page = async () => {
      const asked = [];
      const doc = makeDoc();
      const host = doc.createElement('div');
      const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
        const u = String(url);
        if (u.includes('/subgraph')) asked.push(u);
        return { ok: true, status: 200, json: async () => (u.includes('/subgraph') ? RESULT : DECLS) };
      } });
      await settle();
      // The bar as an operator leaves it: what to collect, which way, through what, how far.
      Object.assign(handle.state, { collect: new Set(['die@1']), follow: new Set(['inspected@1']), direction: 'out', hops: '3' });
      return { asked, host, handle };
    };
    const click = (e) => { for (const fn of (e && e.listeners.click) || []) fn({}); };
    const one = await page();
    const two = await page();
    const full = (p) => walkAll(p.host).find((e) => String(e.className || '').includes('wk-walkfull'));
    const last = (p) => p.asked[p.asked.length - 1] || '';
    // Signed starts: + n:2 and − n:1 - in the baskets and Walk; then checked and Walk ▸; then the graph's Continue ask.
    one.handle.graph.markings.set('walk-start', 'n:2', SIGN.CASE);
    one.handle.graph.markings.set('walk-start', 'n:1', SIGN.CONTROL);
    await one.handle.fire();
    await settle();
    const byWalk = last(one);
    const offBefore = full(one);
    const offWhy = [Boolean(offBefore && offBefore.disabled), offBefore && offBefore.getAttribute('title')];
    one.handle.graph.markings.set(one.handle.state.marks, 'n:2', SIGN.CASE);
    one.handle.graph.markings.set(one.handle.state.marks, 'n:1', SIGN.CONTROL);
    one.handle.render();
    const stepsBefore = one.handle.state.steps.length;
    const at = one.handle.state.at;
    click(full(one));
    await settle();
    const byFull = last(one);
    const placed = one.handle.state.steps.slice(stepsBefore);
    await one.handle.graph.walk(one.handle.graph.ask({ positive: ['n:2'], negative: ['n:1'] }));
    const byContinue = last(one);
    const q = new URLSearchParams(byWalk.split('?')[1] || '');
    ok('W1 the same starts and bar: Walk, Walk ▸ and the graph\'s Continue send the same request, the bar whole',
      Boolean(byWalk) && byWalk === byFull && byFull === byContinue && q.getAll('collect').join() === 'die@1'
        && q.getAll('follow').join() === 'inspected@1' && q.get('direction') === 'out' && q.get('hops') === '3'
        && q.getAll('positive').join() === 'n:2' && q.getAll('negative').join() === 'n:1',
      JSON.stringify([byWalk.slice(0, 220), byFull === byWalk, byContinue === byWalk]));
    // One + start the baskets never held goes as itself, its id exact: the server wrote x 9.0, and an id rebuilt from the
    // keys says 9 - another node (walk_worlds G4, 10-12). One the baskets hold goes by its type and keys, as Walk asks it.
    const exact = 'ledger-entity:v1:' + Buffer.from('["wafer@1",{"wafer":"Z","x":9.0}]').toString('base64url');
    await two.handle.graph.walk(two.handle.graph.ask({ positive: [exact], negative: [] }));
    const cq = new URLSearchParams(last(two).split('?')[1] || '');
    Object.assign(two.handle.state, { type: 'wafer@1', keys: { wafer: 'Z' } });
    click(walkAll(two.host).find((e) => e.className === 'wk-basketadd' && e.attrs['data-sign'] === '+'));
    await two.handle.fire();
    await settle();
    const zq = new URLSearchParams(last(two).split('?')[1] || '');
    ok('W2 one + start alone: one the baskets never held goes as itself, its id exact; the baskets\' own by its type and keys, as Walk asks it',
      cq.getAll('positive').join() === exact && cq.get('id') === exact && cq.getAll('collect').join() === 'die@1'
        && zq.getAll('positive').length === 0 && zq.get('id') === entitySeedId('wafer@1', { wafer: 'Z' }) && zq.getAll('collect').join() === 'die@1',
      JSON.stringify([cq.toString().slice(0, 200), zq.toString().slice(0, 200)]));
    ok('W3 Walk ▸ is off until a row is checked, and says so; pressed, one child step of the step it was on, titled Walk ▸',
      offWhy[0] === true && offWhy[1] === 'Check rows first' && placed.length === 1 && placed[0].parent === at
        && placed[0].title === 'Walk ▸' && JSON.stringify(placed[0].asked.positive) === '["n:2"]',
      JSON.stringify([offWhy, placed.map((s) => [s.parent, s.title])]));
    ok('W4 two pages: the other page\'s checks are its own - its Walk ▸ stays off',
      Boolean(full(two)) && full(two).disabled === true, String(full(two) && full(two).disabled));
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
    const basketAdd = () => walkAll(host).find((e) => e.className === 'wk-basketadd' && e.attrs['data-sign'] === '+');
    const tableOf = () => walkAll(host).filter((e) => e.className === 'wk-sec').map((sec) => [sec.children[0].textContent,
      ...walkAll(sec).filter((e) => e.tagName === 'tr').map((tr) => tr.children.filter((c) => c.className !== 'wk-check')
        .map((c) => (has(c, 'wk-centre') ? c.textContent : valsOf(c) || c.textContent)).join('|'))]);
    const query = (u) => new URLSearchParams((u || '').split('?')[1] || '');
    // One + start alone goes by its seed id (walk_layout L7 L8), a Next's by positive: the same start either way.
    const shape = (u) => [`start=${query(u).getAll('positive').join(',') || query(u).get('id')}`,
      ...['follow', 'collect', 'direction', 'hops', 'node_limit', 'fanout_limit'].map((k) => `${k}=${query(u).getAll(k).join(',')}`)].join('&');
    const bodyRows = (sec) => walkAll(sec).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).length;
    const headOf = (sec) => (walkAll(sec).filter((e) => e.tagName === 'thead').map((t) => t.children[t.children.length - 1])[0] || { children: [] })
      .children.filter((c) => c.className !== 'wk-check').map(headSaid);
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
    click(walkAll(host).find((e) => e.className === 'wk-next-edge' && e.attrs['data-route'] === 'measures ← wafer'));
    await settle();
    const b = tableOf();
    const askB = asked[asked.length - 1];
    ok('EA1 18766: bond_temp alone in + and Walk draws the table a Next from its row draws - same head, rows, columns, cells; 64 wafers, a group per quantity - bond_temp, the answer\'s far end it did not send - its value open, eqp_id · role · step behind ▸ 3; the same ask, the form\'s node_limit and fanout_limit on both, the Next\'s hops its step\'s (owner 10-10, lead 10-11 W)',
      a.length > 0 && JSON.stringify(a) === JSON.stringify(b) && wafers === 64 && shape(askA) === shape(askB)
        && shape(askA) === `start=${q.id}&follow=measures&collect=wafer&direction=both&hops=1&node_limit=${mod.NODE_LIMIT}&fanout_limit=7`
        && JSON.stringify(head) === JSON.stringify(['wafer', 'measures → bond_temp · value▸ 3']),
      JSON.stringify({ a: a.map((sec) => sec.slice(0, 5)), b: b.map((sec) => sec.slice(0, 5)), wafers, head, askA: shape(askA), askB: shape(askB) }));
    // ▸ N (lead 10-11 W addendum 8): pressed, the group's folded cells stand in place after its number; pressed again, folded.
    const wSec = () => walkAll(host).filter((e) => e.className === 'wk-sec').find((sec) => /^wafer/.test(sec.children[0].textContent)) || { children: [] };
    const heads = () => walkAll(wSec()).filter((e) => e.tagName === 'th' && e.className !== 'wk-check').map(headSaid);
    const foldTag = () => walkAll(wSec()).find((e) => e.tagName === 'button' && has(e, 'wk-tag') && /^[▸▾]/.test(e.textContent));
    const shut = heads();
    click(foldTag());
    const opened = heads();
    click(foldTag());
    ok('ZW1 a group\'s «▸ 3»: pressed, its folded cells stand in place after its number, its head «▾»; pressed again, folded (lead 10-11 W addendum 8)',
      JSON.stringify([shut, opened, heads()]) === JSON.stringify([['wafer', 'measures → bond_temp · value▸ 3'],
        ['wafer', 'measures → bond_temp▾', 'value', 'eqp_id', 'role', 'step'], ['wafer', 'measures → bond_temp · value▸ 3']]),
      JSON.stringify([shut, opened, heads()]));
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
    eq('N1 the Next of the die section is the declaration\'s edges one step from die@1, both kinds, each its arrow (lead 10-11 W)',
      edges(host).map((e) => e.attrs['data-route']).join(' | '), 'inspected@1 ← wafer@1 | bonded_to@1 → die@1');
    press(edges(host)[1]);
    await settle();
    ok('N2 nothing checked: every edge is off with its reason, and a press asks nothing',
      edges(host).length === 2 && edges(host).every((e) => e.disabled === true && e.attrs.title === 'Check rows first')
        && asked.length === 0, `${edges(host).map((e) => e.disabled)} ${asked.length}`);
    tick(host, 'n:1');
    const marked = handle.graph.markings.signOf('walk-2', 'n:1');
    ok('N3 a checked row is the page\'s marking the graph reads (walk-2), and the edges come on',
      marked === SIGN.CASE && edges(host).every((e) => e.disabled === false), String(marked));
    // The basket (W addendum 3): the checked rows under the result, a chip each; × and Clear take them out of the marking.
    const basketOf = (h) => walkAll(h).find((e) => e.className === 'wk-marked');
    const chipsOf = (h) => walkAll(h).filter((e) => e.attrs && e.attrs['data-marked']).map((e) => e.attrs['data-marked']);
    const word = (h) => (walkAll(basketOf(h) || { children: [] }).find((e) => e.className === 'wk-markedword') || {}).textContent;
    const resultOf = (h) => walkAll(h).find((e) => e.className === 'wk-result') || { children: [] };
    ok('MB1 the checked row is in the basket, the result\'s last line: «Marked · 1», its chip',
      word(host) === 'Marked · 1' && chipsOf(host).join() === 'n:1' && resultOf(host).children[resultOf(host).children.length - 1] === basketOf(host),
      `${word(host)} ${chipsOf(host)}`);
    press(walkAll(host).find((e) => e.attrs && e.attrs['data-marked'] === 'n:1'));
    const boxOf = (id) => walkAll(host).find((e) => e.attrs && e.attrs['data-row'] === id);
    ok('MB2 a chip\'s × takes the row out of the marking and unchecks it',
      handle.graph.markings.signOf('walk-2', 'n:1') === SIGN.ABSENT && (boxOf('n:1') || {}).checked === false && chipsOf(host).length === 0
        && word(host) === 'Marked · 0', `${handle.graph.markings.signOf('walk-2', 'n:1')} ${chipsOf(host)}`);
    tick(host, 'n:1');
    tick(host, 'n:2');
    const two = chipsOf(host).join();
    press(walkAll(host).find((e) => e.className === 'wk-act wk-markedclear'));
    ok('MB3 Clear empties the marking: no chip, no row checked, the edges off again',
      two === 'n:1,n:2' && handle.graph.markings.entries('walk-2').length === 0 && chipsOf(host).length === 0
        && !(boxOf('n:2') || {}).checked && edges(host).every((e) => e.disabled === true), `${two} ${chipsOf(host)}`);
    // Two pages, two baskets (the parts' rule): a tick on one is not on the other.
    const doc2 = makeDoc();
    const host2 = doc2.createElement('div');
    const handle2 = mod.boot(doc2, host2, { apiBase: '', fetchImpl: async (url) => ({ ok: true, status: 200,
      json: async () => (String(url).includes('/subgraph') ? STEP : DECL3) }) });
    await settle();
    Object.assign(handle2.state, { type: 'die@1', asked: { type: 'die@1', keys: { mat_id: 'M-1' } }, run: 'done', result: START });
    handle2.render();
    tick(host2, 'n:2');
    tick(host, 'n:1');
    ok('MB4 two pages: each basket its own checks',
      chipsOf(host).join() === 'n:1' && chipsOf(host2).join() === 'n:2', `${chipsOf(host)} | ${chipsOf(host2)}`);
    press(edges(host).find((e) => e.attrs['data-route'] === 'bonded_to@1 → die@1'));
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
    press(edges(host).find((e) => e.attrs['data-route'] === 'bonded_to@1 → die@1'));
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
      press(edges(host).find((e) => e.attrs['data-route'] === 'bonded_to@1 → die@1'));
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
    press(edges(host).find((e) => e.attrs['data-route'] === 'bonded_to@1 → die@1'));
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
    press(edges(sameHost).find((e) => e.attrs['data-route'] === `${SAME._predicate} → ${SAME._start.type}`));
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
    // Each node its depth, as a walk answer carries it - the graph places a node by it; the form walk reached n:2 and n:3
    // from n:1, the paths its evidence (G-2).
    const path1 = (id) => ({ id, evidence: [{ seed: 'n:1', hops: [{ id: 'n:1' }, { id, predicates: ['bonded_to@1'] }] }] });
    const ROOTG = { nodes: [{ id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' }, depth: 0 },
      { id: 'n:2', type: 'die@1', label: 'D-2', keys: { mat_id: 'M-2' }, depth: 1 }, { id: 'n:3', type: 'die@1', label: 'D-3', keys: { mat_id: 'M-3' }, depth: 1 }],
    edges: [{ id: 'e:2', source: 'n:1', target: 'n:2', predicate: 'bonded_to@1' }, { id: 'e:3', source: 'n:1', target: 'n:3', predicate: 'bonded_to@1' }],
    propagation: { ranked: [path1('n:2'), path1('n:3')] } };
    const BY = {
      'bonded_to@1': { nodes: [{ id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' }, depth: 0 }, { id: 'n:4', type: 'die@1', label: 'D-4', keys: { mat_id: 'M-4' }, depth: 1 }],
        edges: [{ id: 'e:4', source: 'n:1', target: 'n:4', predicate: 'bonded_to@1' }] },
      'inspected@1': { nodes: [{ id: 'n:1', type: 'die@1', label: 'D-1', keys: { mat_id: 'M-1' }, depth: 0 }, { id: 'w:1', type: 'wafer@1', label: 'W-1', keys: { wafer: 'W1' }, depth: 1 }],
        edges: [{ id: 'e:w', source: 'w:1', target: 'n:1', predicate: 'inspected@1' }] } };
    const doc = makeDoc();
    const host = doc.createElement('div');
    const walks = [];
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      const u = String(url);
      if (u.includes('/subgraph')) walks.push(u);
      const follow = new URLSearchParams(u.split('?')[1] || '').get('follow');
      return { ok: true, status: 200, json: async () => (u.includes('/subgraph') ? BY[follow] : DECLG) };
    } });
    await settle();
    handle.state.type = 'die@1';
    handle.state.asked = { type: 'die@1', keys: { mat_id: 'M-1' }, positive: ['n:1'], negative: [] };
    handle.state.run = 'done';
    handle.state.result = { ...ROOTG, ok: true };
    handle.render();
    const press = (e) => { for (const fn of (e && e.listeners.click) || []) fn(); };
    const tick = (id) => { const cb = walkAll(host).find((e) => e.attrs && e.attrs['data-row'] === id); for (const fn of (cb && cb.listeners.click) || []) fn({}); };
    const next = (words) => walkAll(host).find((e) => e.className === 'wk-next-edge' && e.attrs['data-route'] === words);
    const tab = (id) => walkAll(host).find((e) => e.attrs && e.attrs['data-step'] === String(id));
    const tabs = () => walkAll(host).filter((e) => e.className === 'wk-steprow')
      .map((row) => row.children.map((b) => `${b.textContent}${b.className.includes('is-on') ? ' *' : ''}`));
    const rows = () => walkAll(host).filter((e) => e.attrs && e.attrs['data-row']).map((e) => e.attrs['data-row']).join();
    const A = 'bonded_to@1 → die@1';
    const B = 'inspected@1 ← wafer@1';
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
    // G-2 (lead 10-11): A walked again from n:1 and n:2, then A1 from A's n:4 - the branch Step 1 > A > A1; B the other.
    press(tab(0));
    tick('n:2');
    press(next(A));
    await settle();
    const a2 = handle.state.at;
    tick('n:4');
    press(next(A));
    await settle();
    const a3 = handle.state.at;
    // This stub document draws no picture; the part's steps and layout are what it drew.
    handle.graph.render = () => {};
    const viewOf = (name) => walkAll(host).find((e) => e.attrs && e.attrs['data-view'] === name);
    const ids = (xs) => (xs || []).map((x) => x.id).sort().join();
    const drawn = async (...chosen) => {
      press(viewOf('table'));
      for (const id of chosen) press(tab(id));
      const at = walks.length;
      press(viewOf('graph'));
      await settle();
      const leaf = handle.state.steps.find((x) => x.id === handle.state.leaf);
      const steps = handle.graph.steps;
      return { asked: walks.length - at, steps: steps.length, last: Boolean(leaf) && steps.length > 0 && steps[steps.length - 1].results[0] === leaf.result,
        first: [ids(steps[0] && steps[0].results[0].nodes), ids(steps[0] && steps[0].results[0].edges)],
        picture: ((handle.graph.layout || {}).nodes || []).map((n) => n.id).sort().join() };
    };
    const drawnB = await drawn(b);
    const drawnA = await drawn(a2, a3);
    ok('GB4 the graph on a branch draws the table\'s own answers - nothing walked; the last step its whole answer; B and A1 two pictures (lead 10-11 G-2)',
      drawnB.asked === 0 && drawnA.asked === 0 && drawnB.steps === 2 && drawnA.steps === 3 && drawnB.last && drawnA.last && drawnB.picture !== drawnA.picture,
      JSON.stringify([drawnB, drawnA]));
    ok('GB5 a step before the last draws only its paths to the next step\'s starts: on B the form walk its start n:1; on A1 n:1 and n:2 by e:2; n:3, reached but walked on from by none, on neither (lead 10-11 G-2)',
      JSON.stringify([drawnB.first, drawnA.first]) === JSON.stringify([['n:1', ''], ['n:1,n:2', 'e:2']])
        && !drawnB.picture.includes('n:3') && !drawnA.picture.includes('n:3'),
      JSON.stringify([drawnB.first, drawnA.first, drawnB.picture, drawnA.picture]));
    // A lump of the picture opened while A1 ends the branch (lead 10-11): its step a child of the step whose answer brought
    // its edges - the picture's second step, A.
    handle.graph.openTable({ ok: true, nodes: [], edges: [] }, { owner: 'n:1', ownerLabel: 'D-1', predicate: 'bonded_to@1', farType: 'die@1',
      words: 'bonded_to@1 \u2192 die@1', step: 1 });
    await settle();
    const lumpStep = handle.state.steps.find((x) => x.title === 'From D-1 · bonded_to@1 \u2192 die@1') || {};
    ok('GB6 a lump from the picture\'s second step, A1 ending the branch: its step A\'s child, shown (lead 10-11)',
      lumpStep.parent === a2 && handle.state.at === lumpStep.id && a3 !== a2,
      JSON.stringify([lumpStep.parent, a2, a3, handle.state.at]));
    press(viewOf('table'));
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
    press(walkAll(dieSec()).find((e) => e.attrs && e.attrs['data-rows'] === 'missing'));
    const missed = lines(copy());
    const missedRows = walkAll(dieSec()).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).length;
    const notes = all[0].filter((h) => / note$/.test(h));
    ok('CP3 the page' + "'" + 's «Copy table»: TSV the shape shown (lead 10-11 W) - a head row, each column its + · Δ · −, the id last - and a row each the filter shows, every row as wide as the head; a column no row has a value in (note) in neither; «Copied N rows» beside it',
      all.length > 1 && all.every((r) => r.length === all[0].length) && notes.length === 0 && !shownHeads.some((h) => / note$/.test(h) || h === 'note')
        && JSON.stringify(all[0]) === JSON.stringify(['mat_id', 'inspected ← wafer@1 · gate · +', 'inspected ← wafer@1 · gate · Δ', 'inspected ← wafer@1 · gate · −', 'id'])
        && allSaid === `Copied ${all.length - 1} rows`
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
        ['', 'ab', '', ''], ['', '', '', 'b']]),
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
    const heads = [...new Set(walkAll(host).filter((e) => has(e, 'wk-sidehead')).map((e) => e.title))];
    const missing = walkAll(host).filter((e) => e.tagName === 'td' && has(e, 'wk-missing')).length;
    const secs = walkAll(host).filter((e) => e.className === 'wk-sec');
    const sv = walkTableView(SIGNED, DECL.entities, DECL.predicates, undefined, SIGNED_STARTS);
    const wantMissing = sv.sections.reduce((n, s) => n + s.rows.reduce((m, r) => m + r.cells.reduce((k, c) => k + c.sides.filter((x) => x.missing).length, 0), 0), 0);
    // Walk on is the result's last line, the basket (W addendum 3: the sections' own lines folded into it).
    const resultBox = walkAll(host).find((e) => e.className === 'wk-result');
    const walkOnLast = secs.length > 0 && Boolean(resultBox) && resultBox.children[resultBox.children.length - 1].className === 'wk-marked';
    ok('Z9 the page: a table a type, a sign under each column with its starts and rows, missing in red in each cell a side did not reach, Walk on last (lead 10-11 W)',
      JSON.stringify(heads) === JSON.stringify(['Positive · 2 starts · 2 rows', 'Negative · 1 start · 1 row',
        'Positive · 2 starts · 3 rows', 'Negative · 1 start · 2 rows']) && missing === wantMissing && wantMissing > 0 && walkOnLast,
      `${JSON.stringify(heads)} ${missing} of ${wantMissing} ${walkOnLast}`);
    const views = walkAll(host).filter((e) => e.attrs && e.attrs['data-view']).map((e) => e.attrs['data-view']);
    const compared = walkAll(host).filter((e) => /(^| )cmp-/.test(e.className || '')).length;
    ok('Z10 no way to Compare: the views are Table and Graph, nothing of it drawn',
      views.join() === 'table,graph' && compared === 0, `${views} ${compared}`);
    const headOf = (sec) => (walkAll(sec).find((e) => e.className === 'wk-sechead') || {}).textContent || '';
    const dieSec = () => walkAll(host).filter((e) => e.className === 'wk-sec').find((sec) => /^die/.test(headOf(sec))) || { children: [] };
    const table = () => walkAll(dieSec()).find((e) => has(e, 'wk-wide')) || { children: [] };
    // Wide's heads (lead 10-11 W): the node's columns, each group - its step and far end, its value's name when it shows
    // one - over its columns, the signs and Δ under; the rows below carry their id.
    const headRows = () => walkAll(table()).filter((e) => e.tagName === 'tr' && !(e.attrs && e.attrs['data-row-id']) && !has(e, 'wk-drawer'));
    const headTexts = () => headRows().map((r) => r.children.filter((c) => c.className !== 'wk-check').map(headSaid));
    const groupHeads = () => walkAll(table()).filter((e) => has(e, 'wk-stephead')).map((c) => [headSaid(c), c.colSpan]);
    const rowOf = (id) => walkAll(table()).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === id);
    const tds = (id) => ((rowOf(id) || { children: [] }).children).filter((c) => c.className !== 'wk-check')
      .map((c) => (has(c, 'wk-centre') ? labelOf(c) : valsOf(c)));
    ok('Z13 two groups: the node first, then each column its + cell, Δ, its − cell (lead 10-11 W, the mockup B-ㄱ)',
      JSON.stringify([headTexts(), tds('d:3')]) === JSON.stringify([[['mat_id', 'inspected ← wafer@1 · gate'], ['+', 'Δ', '−']], ['M-3', '7', '−2', '9']]),
      JSON.stringify([headTexts(), tds('d:3')]));
    // ⚰️ Z28 (the node axis in the middle of its box) retired 10-11 with the mirrored sides (lead W): the node is first.
    ok('Z27 a group said once over its columns - its + cell, Δ and − cell (lead 10-11 W)',
      JSON.stringify(groupHeads()) === JSON.stringify([['inspected ← wafer@1 · gate', 3]]), JSON.stringify(groupHeads()));
    const copy = walkAll(rowOf('d:3') || { children: [] }).find((e) => e.className === 'wk-copyid');
    ok('Z16 the keys are behind a press in the node cell, the id not a column - an icon, its name for a reader (34d91c09d 5, owner 10-12)',
      Boolean(copy) && copy.attrs['data-id'] === 'd:3' && copy.textContent === '' && copy.attrs['aria-label'] === 'Copy key'
      && !headTexts().flat().includes('id'), JSON.stringify([headTexts(), copy && copy.textContent]));
    const fire = (b) => { for (const fn of (b && b.listeners.click) || []) fn({ stopPropagation() {} }); };
    // Several values (34d91c09d 1, W): the first and a «+N» tag; pressed, a drawer under the row with each record and who
    // gave it - the lines Long draws; pressed again, gone.
    const tagOf = () => walkAll(rowOf('d:4') || { children: [] }).find((e) => has(e, 'wk-tag'));
    const cellOf4 = () => ((rowOf('d:4') || { children: [] }).children.find((c) => walkAll(c).includes(tagOf())));
    const drawerOf = () => {
      const rows = walkAll(table()).filter((e) => e.tagName === 'tr');
      const at = rows.indexOf(rowOf('d:4'));
      return at >= 0 && rows[at + 1] && has(rows[at + 1], 'wk-drawer') ? rows[at + 1] : null;
    };
    const records = () => (drawerOf() ? walkAll(drawerOf()).filter((e) => has(e, 'wk-record')).map((e) => e.textContent) : null);
    const said = () => (cellOf4() ? [valsOf(cellOf4()), tagOf().textContent, records()] : null);
    const shut = said();
    fire(tagOf());
    const opened = said();
    fire(tagOf());
    ok('Z24 several values in a cell: the first and «+N»; pressed, a drawer under its row with every record and who gave it; pressed again, gone (lead 10-11 W)',
      JSON.stringify([shut, opened, said()]) === JSON.stringify([['1', '+1', null], ['1', '+1', ['1+ · A · start', '2+ · C · start']], ['1', '+1', null]]),
      JSON.stringify([shut, opened, said()]));
    // A node reached by several routes (lead df11f9e81, W: the Route column retired): its source line the first and «+N»,
    // every route in its title.
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
    const coreSrc = () => {
      const tr = walkAll(host2).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === 'w:c');
      const centre = tr && tr.children.find((c) => has(c, 'wk-centre'));
      const src = centre && centre.children.find((c) => c.className === 'wk-src');
      return src ? [src.textContent, src.title] : null;
    };
    ok('Z32 a node reached by several routes: its source line the first and «+N», every route in its title (lead 10-11 W)',
      drew && JSON.stringify(coreSrc()) === JSON.stringify([`${BONDING} +1`, `${BONDING} · ${STACKING}`]), JSON.stringify([drew, coreSrc()]));
    const srcShut = cellOf4() ? [valsOf(cellOf4()), srcsOf(cellOf4())] : null;
    ok('Z41 the page: under a value who gave it, when another node did - the wafer and its way (lead 99ed68cb7 C, W 11)',
      JSON.stringify(srcShut) === JSON.stringify(['1', ['A · start']]), JSON.stringify(srcShut));
    const bands = walkAll(host).filter((e) => has(e, 'wk-sidehead')).map((e) => [e.attrs['data-sign'], has(e, 'wk-plus'), has(e, 'wk-minus')]);
    ok('Z25 a sign its class - + one colour, − the other (34d91c09d 4)',
      JSON.stringify(bands.slice(0, 2)) === JSON.stringify([['+', true, false], ['−', false, true]]), JSON.stringify(bands));
    // A column no row has a value in (lead 10-11 W): in no list - not in the head, not in Columns.
    const colsButton = () => walkAll(dieSec()).find((e) => e.attrs && e.attrs['data-columns'] !== undefined);
    fire(colsButton());
    const listed = walkAll(dieSec()).filter((e) => e.className === 'wk-popcheck').map((e) => e.textContent);
    const countWords = colsButton() && colsButton().textContent;
    fire(colsButton());
    ok('Z26 a column no row has a value in (note) is in no list: not in the head, not in Columns; Columns says k of n groups',
      JSON.stringify([headTexts().flat().some((t) => t.includes('note')), listed, countWords])
        === JSON.stringify([false, ['inspected ← wafer@1'], 'Columns · 1 of 1 ▾']),
      JSON.stringify([headTexts(), listed, countWords]));
    const press = (value) => {
      for (const b of walkAll(host).filter((e) => e.attrs && e.attrs['data-rows'] === value)) for (const fn of b.listeners.click || []) fn({});
    };
    const shown = () => walkAll(host).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).map((e) => e.attrs['data-row-id']).sort().join();
    press('differs');
    const differs = shown();
    press('missing');
    const missed = shown();
    press('all');
    ok('Z14 All rows · Differs · Missing, each section\'s own: the rows the groups differ on, the rows one missed, then every row',
      JSON.stringify([differs, missed, shown()]) === JSON.stringify([ALL, 'd:1,d:2,d:4,s:a,s:b,s:c', ALL]), JSON.stringify([differs, missed]));
    // + Column on the die section, from Columns' foot: the route in, then the far wafer's key - a group of its own, each
    // side its cell.
    fire(colsButton());
    const addOn = walkAll(dieSec()).find((e) => e.tagName === 'button' && e.textContent === '+ Column');
    fire(addOn);
    const pick = (n, test) => {
      const sel = walkAll(dieSec()).filter((e) => e.tagName === 'select' && !has(e, 'wk-longname') && !has(e, 'wk-trendcol'))[n];
      const opt = sel && walkAll(sel).find((o) => o.tagName === 'option' && test(o.textContent));
      if (!opt) return false;
      sel.value = opt.value;
      for (const fn of sel.listeners.change || []) fn({});
      return true;
    };
    const route = pick(0, (t) => t.startsWith('inspected ← '));
    const value = route && pick(1, (t) => t === 'key · wafer');
    const ADDED = 'inspected ← wafer@1 · wafer';
    ok('Z15 + Column at Columns\' foot: a route the rows take, then what its end holds - a group of its own, each side its cell - words, no row a Δ, so none drawn (lead 10-12)',
      JSON.stringify([route, value, groupHeads(), tds('d:3')]) === JSON.stringify([true, true,
        [['inspected ← wafer@1 · gate', 3], [ADDED, 2]], ['M-3', '7', '−2', '9', 'A', 'B']]),
      JSON.stringify([route, value, groupHeads(), tds('d:3')]));
  }
  // ── fixed widths (owner 10-12 「폭이 꿀렁꿀렁」 · 「컬럼 여백 남아도는데 존나 넓게」): a column a <col>, its width from
  //    the answer - a value's + and − one series, the longest words of both (28 · 1050.25 · missing · 10: 7 letters, 8ch);
  //    its Δ drawn only when a row has one (lead 10-12), then its own words alone (+1040.25: 8 letters, 9ch); the node's
  //    keys beside its copy icon - the same after a sort, a filter and a check; the head's spans over exactly those
  //    columns; the stylesheet fixes the layout on them ──
  {
    const fwEdge = (id, source, target, gate) => ({ id, source, target, predicate: 'inspected', qualifiers: { gate } });
    const FW_DASHED = [fwEdge('e:a1', 's:a', 'd:1', 28), fwEdge('e:b3', 's:b', 'd:3', 10), fwEdge('e:c4', 's:c', 'd:4', 1050.25)];
    // `wafer` another name for the wafer type - the far end the die section's group head says.
    const fixedWidths = async (edges, wafer = 'wafer@1') => {
      const named = (t) => (t === 'wafer@1' ? wafer : t);
      const decl = { ...DECL, entities: DECL.entities.map((e) => ({ ...e, type: named(e.type) })),
        predicates: DECL.predicates.map((x) => ({ ...x, subjects: x.subjects.map(named) })) };
      const doc = makeDoc();
      const host = doc.createElement('div');
      const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => decl }) });
      await settle();
      handle.state.type = wafer;
      handle.state.asked = { type: wafer, keys: {}, ...SIGNED_STARTS };
      handle.state.run = 'done';
      handle.state.result = { ...SIGNED, nodes: SIGNED.nodes.map((n) => ({ ...n, type: named(n.type) })), edges };
      handle.render();
      const press = (e) => { for (const fn of (e && e.listeners.click) || []) fn({}); };
      const change = (e) => { for (const fn of (e && e.listeners.change) || []) fn({}); };
      const secHead = (sec) => (walkAll(sec).find((c) => c.className === 'wk-sechead') || {}).textContent || '';
      const dieSec = () => walkAll(host).filter((e) => e.className === 'wk-sec').find((x) => /^die/.test(secHead(x))) || { children: [] };
      const table = () => walkAll(dieSec()).find((e) => e.tagName === 'table') || { children: [] };
      const attr = (name) => walkAll(dieSec()).find((e) => e.attrs && e.attrs[name] !== undefined);
      const widths = () => {
        const trs = walkAll(table()).filter((e) => e.tagName === 'tr');
        const body = trs.find((e) => e.attrs && e.attrs['data-row-id']);
        return { cols: walkAll(table()).filter((e) => e.tagName === 'col').map((e) => [e.className, (e.attrs.style || '').replace(/^width: /, '')]),
          cells: walkAll(table()).filter((e) => e.className === 'wk-val').map((e) => e.textContent),
          deltas: walkAll(table()).filter((e) => e.tagName === 'td' && /\bwk-delta\b/.test(e.className)).map((e) => e.textContent),
          signs: walkAll(table()).filter((e) => e.tagName === 'th' && /wk-sidehead|wk-delta/.test(e.className)).map((e) => e._text),
          spans: trs.length ? trs[0].children.reduce((n, c) => n + (c.colSpan || 1), 0) : -1, across: body ? body.children.length : -1,
          rows: walkAll(table()).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).length };
      };
      const before = widths();
      press(attr('data-sort-key'));
      press(attr('data-filter'));
      change(attr('data-pick'));
      press(attr('data-check-all'));
      return { before, after: widths() };
    };
    const rule = (sel) => ((CSS_NOW.replace(/\/\*[\s\S]*?\*\//g, ' ').split('}').map((r) => r.split('{'))
      .find(([s]) => s && s.trim() === sel) || [])[1] || '').replace(/\s+/g, ' ').trim();
    const stable = ({ before, after }) => JSON.stringify(before.cols) === JSON.stringify(after.cols) && after.rows < before.rows
      && before.spans === before.cols.length && before.across === before.cols.length && after.spans === after.cols.length;
    const values = ({ before }) => before.cols.filter(([c]) => c === 'wk-col-value').map(([, w]) => w);
    const sized = (n) => `max(calc(${n}ch + 2 * var(--space-2)), calc(2ch + var(--space-2) + var(--space-6)))`;
    const NODE_W = 'max(calc(5ch + 2 * var(--space-2) + var(--space-1) + var(--wk-h-small)), calc(7ch + var(--space-2) + var(--space-6)))';
    const dashed = await fixedWidths(FW_DASHED);
    ok('FW1 fixed widths from the answer: a <col> a column - check a finger, node its keys and icon, + and − of one value the width of the longest words of both (28 · 1050.25 · missing · 10 → 8ch, not 96px); a Δ no row has not drawn - unchanged by a sort, a filter and a check; the head spans those columns; the stylesheet lays the table out fixed (owner 10-12)',
      stable(dashed) && dashed.before.cols.length === 4
        && JSON.stringify(dashed.before.cols.slice(0, 2)) === JSON.stringify([['wk-col-check', 'var(--wk-h)'], ['wk-col-node', NODE_W]])
        && JSON.stringify(values(dashed)) === JSON.stringify([sized(8), sized(8)])
        && ['1050.25', 'missing', '28', '10'].every((v) => dashed.before.cells.includes(v))
        && dashed.before.deltas.length === 0 && JSON.stringify(dashed.before.signs) === JSON.stringify(['+', '−'])
        && /table-layout: fixed;/.test(rule('.wk-table')) && /width: 0;/.test(rule('.wk-table')) && rule('.wk-table col') === '',
      JSON.stringify([dashed, rule('.wk-table'), rule('.wk-table col')]));
    // One row with both sides' numbers - d:3 + 1050.25, − 10 - and the column has its Δ, as wide as its own words.
    const counted = await fixedWidths([...FW_DASHED, fwEdge('e:a3', 's:a', 'd:3', 1050.25)]);
    ok('FW2 one row\'s Δ draws the column\'s Δ between + and −, the width of its own words (+1040.25 → 9ch) - not the pair\'s; unchanged by a sort, a filter and a check (lead 10-12)',
      stable(counted) && counted.before.cols.length === 5 && JSON.stringify(values(counted)) === JSON.stringify([sized(8), sized(9), sized(8)])
        && counted.before.deltas.includes('+1040.25') && JSON.stringify(counted.before.signs) === JSON.stringify(['+', 'Δ', '−']),
      JSON.stringify(counted));
    // A far end longer than the values (22 letters over + and −: 11 each, 12ch) - its share sizes + and −, never Δ (+18: 5ch).
    const farLong = await fixedWidths([fwEdge('e:a3', 's:a', 'd:3', 28), fwEdge('e:b3', 's:b', 'd:3', 10)], 'long_wafer_type_name@1');
    ok('FW3 a group head\'s far-end name asks + and − for its share, never Δ: 22 letters - + and − 12ch, Δ «+18» its own 5ch (lead 10-12)',
      stable(farLong) && JSON.stringify(values(farLong)) === JSON.stringify([sized(12), sized(5), sized(12)]) && farLong.before.deltas.includes('+18'),
      JSON.stringify(farLong));
  }
  // ── the node column a section's own (lead 10-12, rehearsal: every section's at ~185 px cut 19 to 21-letter keys): its
  //    longest key, the copy icon beside it, up to COLUMN_CH.node - a longer key cut, whole in its title ──
  {
    const LONG_KEY = 'DEF-'.padEnd(65, 'x');
    const keyDecl = { ok: true, entities: [{ type: 'quantity@1', keys: ['quantity'] }, { type: 'defect@1', keys: ['defect'] }], predicates: [] };
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => keyDecl }) });
    await settle();
    handle.state.type = 'quantity@1';
    handle.state.run = 'done';
    handle.state.result = { nodes: [{ id: 'q:1', type: 'quantity@1', label: 'tape_adhesion_anomaly', keys: { quantity: 'tape_adhesion_anomaly' } },
      { id: 'q:2', type: 'quantity@1', label: 'core_cmp_nonuniform', keys: { quantity: 'core_cmp_nonuniform' } },
      { id: 'f:1', type: 'defect@1', label: LONG_KEY, keys: { defect: LONG_KEY } }], edges: [] };
    handle.render();
    const secHead = (sec) => (walkAll(sec).find((c) => c.className === 'wk-sechead') || {}).textContent || '';
    const sec = (re) => walkAll(host).filter((e) => e.className === 'wk-sec').find((x) => re.test(secHead(x))) || { children: [] };
    const nodeCol = (re) => (walkAll(sec(re)).filter((e) => e.tagName === 'col' && e.className === 'wk-col-node')
      .map((e) => (e.attrs.style || '').replace(/^width: /, ''))[0]) || '';
    const labels = (re) => walkAll(sec(re)).filter((e) => e.className === 'wk-centrelabel').map((e) => [e._text, e.title]);
    const nodeW = (n, head) => 'max(calc(' + n + 'ch + 2 * var(--space-2) + var(--space-1) + var(--wk-h-small)), calc(' + head + 'ch + var(--space-2) + var(--space-6)))';
    ok('NW1 the node column a section\'s own: quantity keys of 21 letters whole (22ch), a 65-letter defect key at the far end (36ch) - cut, whole in its title (lead 10-12)',
      nodeCol(/^quantity/) === nodeW(22, 9) && nodeCol(/^defect/) === nodeW(36, 7)
        && JSON.stringify(labels(/^defect/)) === JSON.stringify([[LONG_KEY, LONG_KEY]]),
      JSON.stringify([nodeCol(/^quantity/), nodeCol(/^defect/), labels(/^defect/)]));
  }
  // ── what the cell shows is what Copy gives (owner 10-12): a value's spaces drawn; the node cell's icon its keys ──
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', writeClipboard, fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
    await settle();
    const SPACED = '  M  1 ';
    handle.state.type = 'die@1';
    handle.state.run = 'done';
    handle.state.result = { ...RESULT, nodes: RESULT.nodes.map((n) => (n.id === 'n:1' ? { ...n, keys: { ...n.keys, mat_id: SPACED } } : n)) };
    handle.render();
    const press = (e) => { for (const fn of (e && e.listeners.click) || []) fn({}); };
    const clipped = (e) => { const at = CLIP.length; press(e); return CLIP.length > at ? CLIP[CLIP.length - 1].text : null; };
    const dieSec = walkAll(host).filter((e) => e.className === 'wk-sec').find((sec) => /^die/.test(sec.children[0].textContent)) || { children: [] };
    const rowOf = (id) => walkAll(dieSec).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === id) || { children: [] };
    const label = walkAll(rowOf('n:1')).find((e) => e.className === 'wk-centrelabel') || {};
    const sheet = clipped(walkAll(dieSec).find((e) => has(e, 'wk-copytable'))) || '';
    const rules = CSS_NOW.replace(/\/\*[\s\S]*?\*\//g, ' ').split('}').map((r) => r.split('{'));
    const ruleFor = (sel) => rules.filter(([s, body]) => body && s.split(',').map((x) => x.trim()).includes(sel)).map(([, body]) => body).join(' ');
    const kept = ['.wk-valline > .wk-val', '.wk-valline > .wk-centrelabel', '.wk-long td'].map((sel) => /white-space: pre;/.test(ruleFor(sel)));
    ok('WS1 a value\'s spaces drawn: the node cell\'s text and title the value whole, the row Copy gives it so; the stylesheet keeps the spaces on one line in Wide\'s values and names and Long\'s cells (owner 10-12)',
      label._text === SPACED && label.title === SPACED && sheet.split(LF).some((line) => line.split('\t')[0] === SPACED) && kept.every(Boolean),
      JSON.stringify([label._text, label.title, sheet.split(LF).slice(0, 3), kept]));
    const icon = (id) => walkAll(rowOf(id)).find((e) => e.className === 'wk-copyid');
    const keys = [clipped(icon('n:1')), clipped(icon('n:2'))];
    ok('CK1 the node cell\'s icon copies its keys as the cells show them, a tab between - a key not there empty - not the internal id (owner 10-12)',
      JSON.stringify(keys) === JSON.stringify([`${SPACED}\t0\t12`, 'M-2\t3\t']), JSON.stringify(keys));
  }
  // ── sort · filter · bulk select on the page (lead 10-11 W addendum 7): what is drawn is what Copy, Trend, Walk on and the
  //    head check take ──
  {
    const SF = sfAnswer(TABLE.PICK_MOST + 2);
    const standUp = async () => {
      const asked = [];
      const doc = makeDoc();
      const host = doc.createElement('div');
      const handle = mod.boot(doc, host, { apiBase: '', writeClipboard, fetchImpl: async (url) => {
        const u = String(url);
        if (u.includes('/subgraph') && !u.includes('page=')) asked.push(u);
        return { ok: true, status: 200, json: async () => (u.includes('/subgraph') ? RESULT : SF_DECL) };
      } });
      await settle();
      handle.state.type = 'wafer@1';
      handle.state.asked = { type: 'wafer@1', keys: {}, ...SF_STARTS };
      handle.state.run = 'done';
      handle.state.result = SF;
      handle.render();
      return { host, handle, asked };
    };
    const { host, handle, asked } = await standUp();
    const has = (e, cls) => String(e.className || '').split(/\s+/).includes(cls);
    const press = (e, event = {}) => { for (const fn of (e && e.listeners.click) || []) fn(event); };
    const change = (e) => { for (const fn of (e && e.listeners.change) || []) fn({}); };
    const type = (input, value) => { if (!input) return; input.value = value; for (const fn of input.listeners.input || []) fn({}); };
    const secHead = (sec) => (walkAll(sec).find((c) => c.className === 'wk-sechead') || {}).textContent || '';
    const dieSec = (h = host) => walkAll(h).filter((e) => e.className === 'wk-sec').find((x) => /^die/.test(secHead(x))) || { children: [] };
    const head = (h = host) => secHead(dieSec(h));
    const drawn = (h = host) => walkAll(dieSec(h)).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).map((e) => e.attrs['data-row-id']);
    const find = (attr, value) => walkAll(dieSec()).find((e) => e.attrs && e.attrs[attr] === value);
    const editor = () => walkAll(dieSec()).find((e) => e.className === 'wk-filteredit') || { children: [], attrs: {} };
    const field = (name) => walkAll(editor()).find((e) => e.attrs && e.attrs['data-field'] === name);
    const findBox = () => walkAll(dieSec()).find((e) => e.attrs && e.attrs['data-find'] === 'die@1');
    const sec = walkTableView(SF, SF_DECL.entities, SF_DECL.predicates, undefined, SF_STARTS).sections.find((x) => x.type === 'die@1');
    const grid = TABLE.gridOf(sec);
    const keyOf = (h) => (grid.columns.find((c) => c.head === h) || {}).key;
    const GATE = keyOf(`${GATE_IN} · +`);
    const gates = () => drawn().map((id) => SF_GATES[Number(id.split(':')[1]) - 1]).map((g) => (g === null ? '' : g)).join();
    const order = drawn().join();
    const words = (find('data-sort-key', GATE) || {}).textContent;
    const sorted = [];
    for (let i = 0; i < 3; i += 1) {
      press(find('data-sort-key', GATE));
      sorted.push([i === 2 ? drawn().join() : gates(), (find('data-sort-key', GATE) || { attrs: {} }).attrs['aria-sort'] || null]);
    }
    ok('PF1 a head pressed sorts its section: ascending, descending, its first order - said by its aria-sort, its words its own, the head no «of»',
      JSON.stringify(sorted) === JSON.stringify([[SF_ASC, 'ascending'], [SF_DESC, 'descending'], [order, null]])
        && (find('data-sort-key', GATE) || {}).textContent === words && head() === sec.heading,
      JSON.stringify([sorted, head()]));
    press(find('data-filter', GATE));
    const kindShown = editor().attrs['data-filter-kind'];
    type(field('min'), '5');
    type(field('max'), '10');
    const ranged = [gates(), head(), (walkAll(dieSec()).find((e) => e.className === 'wk-filterchip') || {}).textContent];
    ok('PF2 a number column\'s «▾»: a range under the toolbar - Min 5 · Max 10 draws the rows in it, the head «5 of 14», the filter a chip',
      kindShown === 'range' && JSON.stringify(ranged) === JSON.stringify(['10,9,7,8,6', `die@1 · 5 of ${sec.rows.length}`, `${GATE_IN} · + · ≥ 5 · ≤ 10 ×`]),
      JSON.stringify([kindShown, ranged]));
    const at0 = CLIP.length;
    press(walkAll(dieSec()).find((e) => has(e, 'wk-copytable')));
    const copied = CLIP.length > at0 ? CLIP[CLIP.length - 1].text.split(LF) : [];
    const said = (walkAll(dieSec()).find((e) => has(e, 'wk-copied')) || {}).textContent;
    ok('PF3 Copy after a filter: a line a row drawn, in its order - «Copied 5 rows»',
      copied.length === 6 && copied.slice(1).map((l) => l.split(String.fromCharCode(9)).pop()).join() === drawn().join() && said === 'Copied 5 rows',
      JSON.stringify([copied.length, said]));
    press(walkAll(dieSec()).find((e) => e.className === 'wk-filterchip'));
    press(find('data-filter', keyOf('mat_id')));
    const contains = editor().attrs['data-filter-kind'];
    type(field('contains'), 'm-1');
    const byWords = drawn().join();
    press(walkAll(editor()).find((e) => e.tagName === 'button' && e.textContent === 'Clear'));
    press(find('data-filter', keyOf('grade')));
    const picks = walkAll(editor()).filter((e) => e.attrs && e.attrs['data-pick'] !== undefined).map((e) => e.attrs['data-pick']);
    change(walkAll(editor()).find((e) => e.attrs && e.attrs['data-pick'] === 'A'));
    const byPick = drawn().length;
    press(walkAll(editor()).find((e) => e.tagName === 'button' && e.textContent === 'Clear'));
    press(walkAll(editor()).find((e) => e.tagName === 'button' && e.textContent === 'Close'));
    ok('PF4 the three kinds on the page: mat_id the words it contains («m-1» 6 rows), grade values picked (A out: 9 rows), Clear and Close each',
      JSON.stringify([contains, byWords, picks, byPick, drawn().length, editor().attrs['data-filter-kind'] || null])
        === JSON.stringify(['contains', 'sd:1,sd:10,sd:11,sd:12,sd:13,sd:14', ['A', 'B', ''], 9, sec.rows.length, null]),
      JSON.stringify([contains, byWords, picks, byPick, drawn().length]));
    // The search box and All rows · Differs · Missing: one seat, one filter.
    const seat = walkAll(dieSec()).find((e) => e.className === 'wk-filterseat') || { children: [] };
    type(findBox(), 'M-1');
    const found = [drawn().length, head()];
    press(find('data-shape', 'long'));
    const longDrawn = walkAll(dieSec()).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).length;
    const longWant = TABLE.shownOf(sec, { find: 'M-1' }, TABLE.longLines(walkTableView(SF, SF_DECL.entities, SF_DECL.predicates, undefined, SF_STARTS), sec)).lines.length;
    const at1 = CLIP.length;
    press(walkAll(dieSec()).find((e) => has(e, 'wk-copytable')));
    const longCopied = CLIP.length > at1 ? CLIP[CLIP.length - 1].text.split(LF).length - 1 : -1;
    const longHead = head();
    press(find('data-shape', 'wide'));
    ok('PF5 the search box and All rows · Differs · Missing one seat: «M-1» 6 rows, «6 of 14»; Long its lines found - drawn, copied and «N of 22 lines»',
      walkAll(seat).some((e) => e.attrs && e.attrs['data-find'] === 'die@1') && walkAll(seat).some((e) => e.attrs && e.attrs['data-rows'] === 'missing')
        && JSON.stringify(found) === JSON.stringify([6, `die@1 · 6 of ${sec.rows.length}`])
        && longDrawn === longWant && longCopied === longWant && longWant > 6 && longHead === `die@1 · ${longWant} of 22 lines`,
      JSON.stringify([found, longDrawn, longWant, longCopied, longHead]));
    // The head check: every row shown, then none of them - a hidden row's check its own.
    const marks = handle.graph.markings;
    marks.set(handle.state.marks, 'sd:2', SIGN.CASE);
    handle.render();
    const shownIds = drawn();
    press(find('data-check-all', ''));
    const allOn = marks.entries(handle.state.marks).map(([id]) => id).sort().join();
    const boxOn = (find('data-check-all', '') || {}).checked;
    press(find('data-check-all', ''));
    const allOff = marks.entries(handle.state.marks).map(([id]) => id).join();
    ok('PF6 the head check: every row shown checked (6), a hidden row\'s check kept; pressed again, the shown ones off',
      allOn === [...shownIds, 'sd:2'].sort().join() && boxOn === true && allOff === 'sd:2',
      JSON.stringify([allOn, boxOn, allOff]));
    // Walk on and Trend take the rows shown.
    type(findBox(), '');
    marks.replace(handle.state.marks, [['sd:4', SIGN.CASE], ['sd:1', SIGN.CASE]]);
    type(findBox(), 'M-1');
    const before = asked.length;
    // Walk on is the basket's, under the result (W addendum 3): the die rows checked, so its routes are die's.
    press(walkAll(host).find((e) => e.className === 'wk-next-edge'));
    await settle();
    const q = new URLSearchParams((asked[before] || '').split('?')[1] || '');
    const seeds = [...q.getAll('positive'), ...q.getAll('id')];
    handle.state.at = 0;
    handle.render();
    press(find('data-section-view', 'trend'));
    const dots = () => walkAll(dieSec()).filter((e) => e.attrs && e.attrs['data-key'] !== undefined && String(e.attrs.class).includes('wk-tp')).length;
    const trendFound = dots();
    type(findBox(), '');
    const trendAll = dots();
    press(find('data-section-view', 'table'));
    ok('PF8 Walk on from the checked rows shown (sd:1 - sd:4 hidden); the section\'s Trend a dot a row shown with a time (6), all again 12',
      asked.length === before + 1 && seeds.includes('sd:1') && !seeds.includes('sd:4') && trendFound === 6 && trendAll === 12,
      JSON.stringify([asked.length - before, seeds, trendFound, trendAll]));
    // Two pages on one screen: a filter in one is not the other's.
    const two = await standUp();
    type(findBox(), 'M-12');
    press(walkAll(dieSec(two.host)).find((e) => e.attrs && e.attrs['data-sort-key'] === GATE));
    ok('PF9 two pages: one\'s search box and the other\'s sort each its own',
      drawn().join() === 'sd:12' && drawn(two.host).length === sec.rows.length && head(two.host) === sec.heading
        && (walkAll(dieSec()).find((e) => e.attrs && e.attrs['data-sort-key'] === GATE) || { attrs: {} }).attrs['aria-sort'] === undefined,
      JSON.stringify([drawn(), drawn(two.host).length, head(two.host)]));
  }

  console.log(`${LF}-- an image reference: the main grid's image cell, nothing asked until a dwell --`);
  {
    // The same text twice: one edge's column the answer says is an image (server c5463a475), the other's not.
    const REF = 'imgs:lot 7/a.png';
    const IMAGES = { nodes: RESULT.nodes, edges: [
      { id: 'e:1', source: 'n:3', target: 'n:1', predicate: 'inspected', qualifiers: { photo: REF }, column_types: { photo: 'image' } },
      { id: 'e:2', source: 'n:3', target: 'n:2', predicate: 'inspected', qualifiers: { photo: REF } }] };
    const { host: im, doc } = await render(mod, IMAGES);
    const rowOf = (id) => byTag(im, 'tr').find((tr) => tr.attrs['data-row-id'] === id) || { children: [] };
    const marksOf = (id) => walkAll(rowOf(id)).filter((e) => e.className === 'cell-image');
    const asked = () => walkAll(doc.body).filter((e) => e.tagName === 'img' && String(e.attrs.src || '').includes(IMAGE_ROUTE)).length;
    const marked = marksOf('n:1');
    const plain = walkAll(rowOf('n:2')).filter((e) => e.className === 'wk-val').map((e) => e._text);
    const drawn = asked();
    // The dwell: the preview's one timer, caught as it is set and run by hand.
    const timers = [];
    const realTimeout = globalThis.setTimeout;
    globalThis.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
    try { for (const fn of (marked[0] && marked[0].listeners.mouseenter) || []) fn({}); } finally { globalThis.setTimeout = realTimeout; }
    const before = asked();
    globalThis.window = { innerWidth: 1280, innerHeight: 720 };
    try { for (const t of timers) t.fn(); } finally { delete globalThis.window; }
    const dwelt = asked();
    const src = (walkAll(doc.body).find((e) => e.tagName === 'img' && e.attrs.src) || { attrs: {} }).attrs.src;
    for (const fn of (marked[0] && marked[0].listeners.mouseleave) || []) fn({});
    ok('IM1 a value the answer says is an image draws the image cell (the other, same text, as text); drawing asks 0, a dwell 1, leaving takes it back',
      marked.length === 1 && walkAll(marked[0]).some((e) => e.className === 'cell-image-ref' && e._text === REF)
        && plain.includes(REF) && marksOf('n:2').length === 0
        && drawn === 0 && before === 0 && timers.length === 1 && timers[0].ms === DWELL_MS
        && dwelt === 1 && src === `${IMAGE_ROUTE}?ref=${encodeURIComponent(REF)}` && asked() === 0,
      JSON.stringify({ marks: marked.length, plain, n2marks: marksOf('n:2').length, drawn, before, timers: timers.map((t) => t.ms), dwelt, src, after: asked() }));
  }

  console.log(`${LF}-- More ▸: the server's next page of the same walk, merged (owner 10-12 «이어 걷기») --`);
  {
    // The second page: d:3 again, d:20 new, and every collected type reached.
    const PAGE2 = { ...SIGNED, nodes: [SIGNED.nodes[5], { id: 'd:20', type: 'die@1', label: 'D-20', depth: 2, keys: { mat_id: 'M-20' } }],
      edges: [{ id: 'e:a20', source: 's:a', target: 'd:20', predicate: 'inspected', qualifiers: { gate: 2, note: null } }],
      propagation: { ranked: [{ id: 'd:20', reach: [1, 0], evidence: [{ seed: 's:a', sign: '+', hops: [{ id: 's:a' }, { id: 'd:20', predicates: ['inspected'] }] }] }] },
      generated_at: '2026-10-12T05:30:00', more: { reach: { 'die@1': { complete: true, unexpanded: 0 } }, resume: null, as_of: '2026-10-12T05:00:00' } };
    const sent = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url, init) => {
      const u = String(url);
      if (!u.includes('/subgraph')) return { ok: true, status: 200, json: async () => DECL };
      sent.push({ u, method: (init && init.method) || 'GET', body: init && init.body });
      return { ok: true, status: 200, json: async () => PAGE2 };
    } });
    await settle();
    const ASK = { type: 'die@1', keys: { mat_id: 'A' }, ...SIGNED_STARTS, collect: ['die@1'], node_limit: 1000 };
    handle.state.asked = { ...ASK };
    handle.state.run = 'done';
    handle.state.result = { ...SIGNED, ok: true, ask: ASK, generatedAt: '2026-10-12T05:00:00',
      more: { reach: { 'die@1': { complete: false, unexpanded: 3 } }, resume: { cursor: 'c1' } } };
    handle.render();
    const line = () => (walkAll(host).find((e) => e.className === 'wk-reachline') || { textContent: '' });
    const go = () => walkAll(line()).find((e) => String(e.className || '').includes('wk-more'));
    const rowIds = () => walkAll(host).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).map((e) => e.attrs['data-row-id']).sort().join();
    const said = (e) => walkAll(e).filter((k) => k._text).map((k) => k._text).join('|');
    const before = [said(line()), go() && go().disabled, rowIds()];
    for (const fn of (go() || { listeners: {} }).listeners.click || []) fn({});
    await settle();
    const q = new URLSearchParams((sent[0] && sent[0].u.split('?')[1]) || '');
    ok('MR1 the head says each collected type cut or reached; More ▸ asks the same walk again, a POST with its resume - resumable, as this screen asks every walk (implementer A fe2b894f0)',
      before[0].includes('die@1: cut · 3 not expanded') && before[0].includes('more to walk') && before[1] === false
        && sent.length === 1 && sent[0].method === 'POST'
        && sent[0].body === JSON.stringify({ resume: { cursor: 'c1' } }) && q.getAll('positive').join() === 's:a,s:c'
        && q.getAll('negative').join() === 's:b' && q.getAll('collect').join() === 'die@1' && q.get('resumable') === 'true',
      JSON.stringify([before, sent.map((s) => [s.method, s.body, s.u.slice(0, 120)])]));
    ok('MR2 the next page merged into the step - the rows of both, each once - its pages said; all reached, More ▸ off and says so',
      rowIds() === [...before[2].split(','), 'd:20'].sort().join() && said(line()).includes('die@1: all reached')
        && said(line()).includes('2 pages') && !said(line()).includes('more to walk') && go().disabled === true
        && go().getAttribute('title') === 'All reached'
        && handle.state.result.generatedAt === '2026-10-12T05:00:00',
      JSON.stringify([rowIds(), said(line()), go() && go().disabled, handle.state.result.generatedAt]));
  }

  console.log(`${LF}-- More off while its walk runs: a second press asks nothing (lead 9752e91f7) --`);
  for (const kind of ['More ▸', 'More']) {
    const sent = [];
    const held = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const PAGE = { ...SIGNED, more: { reach: { 'die@1': { complete: false, unexpanded: 2 } }, resume: { cursor: 'c2' } } };
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url, init) => {
      const u = String(url);
      if (!u.includes('/subgraph')) return { ok: true, status: 200, json: async () => DECL };
      sent.push({ method: (init && init.method) || 'GET', body: init && init.body });
      return new Promise((resolve) => held.push(() => resolve({ ok: true, status: 200,
        json: async () => (kind === 'More' ? { ...SIGNED, truncated: { nodes: true, reason: 'nodes' }, limits: { nodes: 20, max_hops: 40 } } : PAGE) })));
    } });
    await settle();
    const ASK = { type: 'die@1', keys: { mat_id: 'A' }, ...SIGNED_STARTS, collect: ['die@1'], node_limit: 10 };
    handle.state.asked = { ...ASK };
    handle.state.run = 'done';
    handle.state.result = { ...SIGNED, ok: true, ask: ASK, generatedAt: '2026-10-12T05:00:00',
      ...(kind === 'More' ? { cut: true, truncatedAxes: ['nodes'], limits: { nodes: 10, max_hops: 40 } } : { more: { reach: { 'die@1': { complete: false, unexpanded: 3 } }, resume: { cursor: 'c1' } } }) };
    handle.render();
    const btn = () => walkAll(host).find((e) => String(e.className || '').includes('wk-more') && e._text === kind);
    // As a browser does: a disabled button's click does not fire.
    const press = () => { const b = btn(); if (b && !b.disabled) for (const fn of b.listeners.click || []) fn({}); };
    const live = Boolean(btn()) && btn().disabled === false;
    press();
    await settle();
    const during = [Boolean(btn()) && btn().disabled, btn() && btn().getAttribute('title')];
    press();
    await settle();
    const asked = sent.length;
    for (const go of held.splice(0)) go();
    await settle();
    await settle();
    const after = Boolean(btn()) && btn().disabled === false;
    const id = kind === 'More' ? 'MR8' : 'MR7';
    ok(`${id} ${kind}: off while its walk runs, its reason Walking…; a second press asks nothing; live again when the page lands`,
      live && during[0] === true && during[1] === 'Walking…' && asked === 1 && after,
      JSON.stringify([live, during, asked, after, sent.map((s) => s.method)]));
  }

  console.log(`${LF}-- a continued page the server no longer holds: 410 walk_expired - its line and Walk again (lead eb1ae8c9f) --`);
  for (const why of ['reloaded', 'restarted', 'expired', 'process ended', 'server updated']) {
    const sent = [];
    const doc = makeDoc();
    const host = doc.createElement('div');
    const FIRST = { ...SIGNED, more: { reach: { 'die@1': { complete: false, unexpanded: 3 } }, resume: { walk: 'k2' } } };
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url, init) => {
      const u = String(url);
      if (!u.includes('/subgraph')) return { ok: true, status: 200, json: async () => DECL };
      sent.push({ method: (init && init.method) || 'GET', body: init && init.body });
      if (init && init.method === 'POST') {
        return { ok: false, status: 410, json: async () => ({ detail: { reason: 'walk_expired', why, message: `This walk expired (${why}) - walk again` } }) };
      }
      return { ok: true, status: 200, json: async () => FIRST };
    } });
    await settle();
    const ASK = { type: 'die@1', keys: { mat_id: 'A' }, ...SIGNED_STARTS, collect: ['die@1'], node_limit: 1000 };
    handle.state.asked = { ...ASK };
    handle.state.run = 'done';
    handle.state.result = { ...SIGNED, ok: true, ask: ASK, generatedAt: '2026-10-12T05:00:00',
      more: { reach: { 'die@1': { complete: false, unexpanded: 3 } }, resume: { walk: 'k1' } } };
    handle.render();
    const rowIds = () => walkAll(host).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).map((e) => e.attrs['data-row-id']).sort().join();
    const said = (e) => walkAll(e).filter((k) => k._text).map((k) => k._text).join('|');
    const fail = () => walkAll(host).find((e) => e.className === 'wk-fail');
    const again = () => fail() && walkAll(fail()).find((e) => e.tagName === 'button' && e._text === 'Walk again');
    const before = rowIds();
    const moreNow = () => walkAll(host).find((e) => String(e.className || '').includes('wk-more') && e._text === 'More ▸');
    for (const fn of (moreNow() || { listeners: {} }).listeners.click || []) fn({});
    await settle();
    await settle();
    ok(`EX1 ${why}: the server's line and «Walk again»; the rows drawn stay; More ▸ off (its resume is gone); nothing asked again by itself`,
      Boolean(fail()) && said(fail()).includes(`This walk expired (${why}) - walk again`) && Boolean(again())
        && rowIds() === before && before.length > 0 && sent.length === 1 && sent[0].method === 'POST'
        && Boolean(moreNow()) && moreNow().disabled === true,
      JSON.stringify([fail() && said(fail()), Boolean(again()), rowIds() === before, sent.map((s) => s.method), moreNow() && moreNow().disabled]));
    if (why !== 'reloaded') continue;
    for (const fn of (again() || { listeners: {} }).listeners.click || []) fn({});
    await settle();
    await settle();
    ok('EX2 Walk again asks the first page of the same question once - a GET, no resume - and that page stands in the step',
      sent.length === 2 && sent[1].method === 'GET' && !sent[1].body && !fail()
        && handle.state.result && handle.state.result.more && handle.state.result.more.resume && handle.state.result.more.resume.walk === 'k2'
        && Boolean(moreNow()) && moreNow().disabled === false,
      JSON.stringify([sent.map((s) => [s.method, s.body || null]), Boolean(fail()), handle.state.result && handle.state.result.more, moreNow() && moreNow().disabled]));
  }
  // Walk again is a new walk (18766, lead 10-13): one + start walked by its type and keys - the wire's ask carries no
  // starts - so walked as a More its seed row read «—» and «+0 from More ×» stayed. Now: the seed row «start», no chip.
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url, init) => {
      if (!String(url).includes('/subgraph')) return { ok: true, status: 200, json: async () => DECL };
      if (init && init.method === 'POST') {
        return { ok: false, status: 410, json: async () => ({ detail: { reason: 'walk_expired', why: 'reloaded', message: 'This walk expired (reloaded) - walk again' } }) };
      }
      return { ok: true, status: 200, json: async () => ({ ...SIGNED, more: { reach: { 'die@1': { complete: false, unexpanded: 3 } }, resume: { walk: 'k2' } } }) };
    } });
    await settle();
    const WIRE = { type: 'wafer@1', keys: { wafer: 'A' }, collect: ['die@1'], node_limit: 1000 };
    handle.state.asked = { ...WIRE, keys: { wafer: 'A' }, positive: ['s:a'], negative: [] };
    handle.state.run = 'done';
    handle.state.result = { ...SIGNED, ok: true, ask: WIRE, generatedAt: '2026-10-12T05:00:00',
      more: { reach: { 'die@1': { complete: false, unexpanded: 3 } }, resume: { walk: 'k1' } } };
    handle.render();
    const press = (find) => { const b = find(); for (const fn of (b || { listeners: {} }).listeners.click || []) fn({}); };
    press(() => walkAll(host).find((e) => String(e.className || '').includes('wk-more') && e._text === 'More ▸'));
    await settle(); await settle();
    press(() => walkAll(host).find((e) => e.tagName === 'button' && e._text === 'Walk again'));
    await settle(); await settle();
    const seedRow = walkAll(host).find((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id'] === 's:a');
    const said = seedRow ? walkAll(seedRow).filter((k) => k._text).map((k) => k._text) : [];
    const chips = walkAll(host).filter((e) => e.className === 'wk-addchip').map((e) => e._text);
    ok('EX3 Walk again is a new walk: one + start by its type and keys - its row «start», its starts the step\'s, no «from More» chip',
      said.includes('start') && JSON.stringify(handle.state.asked.positive) === '["s:a"]' && !chips.some((c) => c.includes('from More')),
      JSON.stringify([said, handle.state.asked.positive, chips]));
  }

  console.log(`${LF}-- a cell past its ways: the screen says so, and Show all reads every way (lead 10-13) --`);
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
    await settle();
    handle.state.asked = { type: 'wafer', keys: { wafer: 'W' }, ...WIDE_STARTS };
    handle.state.run = 'done';
    handle.state.result = { ...WIDE, ok: true, ask: { type: 'wafer', keys: { wafer: 'W' } } };
    handle.render();
    const line = () => walkAll(host).find((e) => String(e.className || '').includes('wk-waycut'));
    const before = line() && [walkAll(line()).filter((k) => k._text).map((k) => k._text).join('|')];
    const all = line() && walkAll(line()).find((e) => e.tagName === 'button' && e._text === 'Show all');
    for (const fn of (all || { listeners: {} }).listeners.click || []) fn({});
    await settle();
    ok('WC2 the screen says its cells were cut, with Show all; pressed, every way is read and the line goes',
      Boolean(before) && before[0].includes('Cells cut at 50 ways') && Boolean(all) && !line() && handle.state.allWays === true,
      JSON.stringify([before, Boolean(all), Boolean(line()), handle.state.allWays]));
  }

  // + Column's routes on the screen: grouped by how many steps, four of them reached (lead 10-13).
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL }) });
    await settle();
    const CHAIN = { nodes: [{ id: 'bw', type: 'wafer', label: 'BW', depth: 0 }, { id: 'd', type: 'die', label: 'D', depth: 1 },
      { id: 'cd', type: 'die', label: 'CD', depth: 2 }, { id: 'cw', type: 'wafer', label: 'CW', depth: 3 }, { id: 'q', type: 'quantity', label: 'temp', depth: 4 }],
    edges: [{ id: 'e1', source: 'd', target: 'bw', predicate: 'in_wafer', qualifiers: {} }, { id: 'e2', source: 'd', target: 'cd', predicate: 'bonded_from', qualifiers: {} },
      { id: 'e3', source: 'cd', target: 'cw', predicate: 'in_wafer', qualifiers: {} }, { id: 'e4', source: 'cw', target: 'q', predicate: 'measures', qualifiers: { value: 1 } }] };
    handle.state.asked = { type: 'wafer', keys: { wafer: 'BW' }, positive: ['bw'], negative: [] };
    handle.state.run = 'done';
    handle.state.result = { ...CHAIN, ok: true, ask: { type: 'wafer', keys: { wafer: 'BW' } } };
    handle.state.picking = 'wafer';
    handle.render();
    const groups = walkAll(host).filter((e) => e.tagName === 'optgroup').map((e) => e.attrs && e.attrs.label);
    ok('RG1 + Column routes grouped by steps, four reached', JSON.stringify(groups) === JSON.stringify(['1 step', '2 steps', '3 steps', '4 steps']), JSON.stringify(groups));
  }

  console.log(`${LF}-- the Route panel: the ways the walk took, or before it the shortest route suggested (owner 10-12) --`);
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL_RT }) });
    await settle();
    Object.assign(handle.state, { type: 'wafer@1', collect: new Set(['die@1']) });
    handle.render();
    const rows = () => walkAll(host).filter((e) => e.className === 'wk-path');
    const words = () => rows().map((r) => walkAll(r).filter((k) => k.className === 'wk-pathchain').map((k) => k._text).join(''));
    const headNote = () => walkAll(host).filter((e) => e.className === 'wk-routes-head').map((h) => walkAll(h).map((k) => k._text || '').join(' ')).join();
    const before = [rows().length, headNote()];
    Object.assign(handle.state, { run: 'done', result: { ...WALKED, ok: true }, asked: { type: 'wafer@1', keys: { wafer: 'A' } } });
    handle.render();
    const after = [words(), headNote()];
    for (const fn of (rows()[0] || { listeners: {} }).listeners.click || []) fn({});
    ok('RT2 after a walk: the ways it walked to die, most nodes first - pressed, through takes that way\'s predicates and hops',
      JSON.stringify(after[0]) === JSON.stringify(['wafer@1 —in@1→ lot@1 —has@1→ die@1 · 2', 'wafer@1 —inspected@1→ die@1 · 1'])
        && after[1].includes('Walked to die@1') && handle.state.follow.has('in@1') && handle.state.follow.has('has@1') && handle.state.hops === '2',
      JSON.stringify([after, [...handle.state.follow], handle.state.hops]));
    ok('RT3 before a walk: the shortest declared route alone, said as Suggested', before[0] === 1 && before[1].includes('Suggested'),
      JSON.stringify(before));
  }

  console.log(`${LF}-- More: the same walk, the limit that cut it raised (lead 10-12) --`);
  {
    // The same walk at 800 brings d:10 from s:a and is not cut.
    const RAISED = { ...SIGNED, nodes: [...SIGNED.nodes, { id: 'd:10', type: 'die@1', label: 'D-10', depth: 1, keys: { mat_id: 'M-10' } }],
      edges: [...SIGNED.edges, { id: 'e:a10', source: 's:a', target: 'd:10', predicate: 'inspected', qualifiers: { gate: 3 } }],
      propagation: { ranked: [...SIGNED.propagation.ranked, { id: 'd:10', reach: [1, 0], evidence: [{ seed: 's:a', sign: '+', hops: [{ id: 's:a' }, { id: 'd:10', predicates: ['inspected'] }] }] }] },
      truncated: { nodes: false, reason: null }, limits: { nodes: 800, max_hops: 40 } };
    const stand = async (nodes) => {
      const asked = [];
      const doc = makeDoc();
      const host = doc.createElement('div');
      const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
        const u = String(url);
        if (!u.includes('/subgraph')) return { ok: true, status: 200, json: async () => DECL };
        asked.push(u);
        return { ok: true, status: 200, json: async () => RAISED };
      } });
      await settle();
      handle.state.type = 'die@1';
      handle.state.asked = { type: 'die@1', keys: { mat_id: 'A' }, ...SIGNED_STARTS, node_limit: nodes };
      handle.state.run = 'done';
      handle.state.result = { ...SIGNED, ok: true, cut: true, truncatedAxes: ['nodes'], limits: { nodes, max_hops: 40 } };
      handle.render();
      return { host, asked };
    };
    const moreOf = (host) => walkAll(host).find((e) => String(e.className).includes('wk-more'));
    const cutLine = (host) => (walkAll(host).find((e) => e.className === 'wk-trunc') || { textContent: '' }).textContent;
    const rowIdsOf = (host) => walkAll(host).filter((e) => e.tagName === 'tr' && e.attrs && e.attrs['data-row-id']).map((e) => e.attrs['data-row-id']).sort().join();
    const heads = (host) => walkAll(host).filter((e) => e.className === 'wk-sechead').map((e) => e.textContent).join(' | ');
    const chips = (host) => walkAll(host).filter((e) => e.className === 'wk-addchip');
    const cut = await stand(400);
    const before = [Boolean(moreOf(cut.host)), cutLine(cut.host), heads(cut.host)];
    for (const fn of (moreOf(cut.host) || { listeners: {} }).listeners.click || []) fn({});
    await settle();
    const q = new URLSearchParams((cut.asked[0] || '').split('?')[1] || '');
    const after = [cut.asked.length, q.get('node_limit'), q.getAll('positive').join(), q.getAll('negative').join(), rowIdsOf(cut.host),
      heads(cut.host), chips(cut.host).map((c) => c._text), Boolean(moreOf(cut.host))];
    const dieChip = chips(cut.host).find((c) => c._text === '+1 from More');
    for (const fn of ((dieChip && dieChip.children[0]) || { listeners: {} }).listeners.click || []) fn({});
    const undone = [rowIdsOf(cut.host), heads(cut.host), chips(cut.host).length, cutLine(cut.host)];
    const top = await stand(1000);
    const atMax = [Boolean(moreOf(top.host)), cutLine(top.host), top.asked.length];
    ok('MO2 a node cut: More asks the same walk at node_limit 800 - its starts, one request - and its answer replaces the step\'s (die 4 -> 5, «+1 from More» on die, «+0» on wafer, no More); × puts the cut answer back with its More; at the server\'s 1000 no More, the line says so',
      JSON.stringify([before, after, undone, atMax]) === JSON.stringify([[true, 'Cut · nodes 400More', 'wafer@1 · 3 | die@1 · 4'],
        [1, '800', 's:a,s:c', 's:b', `${ALL},d:10`.split(',').sort().join(), 'wafer@1 · 3 | die@1 · 5', ['+0 from More', '+1 from More'], false],
        [ALL, 'wafer@1 · 3 | die@1 · 4', 0, 'Cut · nodes 400More'], [false, 'Cut · nodes 1000 · at the server limit', 0]]),
      JSON.stringify([before, after, undone, atMax]));
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
  const at = die ? die.columnHeads.indexOf(GATE_IN) : -1;
  return at >= 0 ? die.rows[0].cells[at].sides[0] : { text: null, numeric: null };
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
  const view = (starts, result = SIGNED, added, fold) => TV.walkTableView(result, DECL.entities, DECL.predicates, undefined, starts, added, fold);
  // A row's cell in one group under one head (lead 10-11 W: a column its groups' cells), missing in brackets.
  const raw = (table, type, id, head, group) => {
    const sec = table.sections.find((x) => x.type === type);
    const at = sec ? sec.columnHeads.indexOf(head) : -1;
    const row = sec && sec.rows.find((r) => r.id === id);
    return row && at >= 0 ? row.cells[at].sides[group] : null;
  };
  const cell = (table, type, id, head, group) => {
    const got = raw(table, type, id, head, group);
    return got ? (got.missing ? `[${got.text}]` : got.text) : null;
  };
  const plain = view({ positive: ['s:a', 's:c'], negative: [] });
  ok('Z1 no - start: one side, every node the walk brought (E1: the flat table retired)', plain.groups.length === 1
    && plain.sections.every((x) => x.groups.length === 1) && rowIds(plain) === ALL,
    `${JSON.stringify(plain.groups)} ${rowIds(plain)}`);
  const two = view(SIGNED_STARTS);
  ok('Z02 a node a row: one row whichever groups reached it', rowIds(two) === ALL
    && two.sections.every((x) => new Set(x.rows.map((r) => r.id)).size === x.rows.length), rowIds(two));
  ok('Z3 reached by one group only: the other says missing',
    cell(two, 'die@1', 'd:1', GATE_IN, 1) === '[missing]' && cell(two, 'die@1', 'd:2', GATE_IN, 0) === '[missing]',
    `${cell(two, 'die@1', 'd:1', GATE_IN, 1)} | ${cell(two, 'die@1', 'd:2', GATE_IN, 0)}`);
  ok('Z04 reached but no value says so, not missing',
    cell(two, 'die@1', 'd:1', GATE_IN, 0) === TV.EMPTY && cell(two, 'die@1', 'd:2', GATE_IN, 1) === TV.EMPTY,
    `${cell(two, 'die@1', 'd:1', GATE_IN, 0)} | ${cell(two, 'die@1', 'd:2', GATE_IN, 1)}`);
  ok('Z5 a cell reads its group\'s edges only: the node both reached says each group\'s own value - one group, its far type (lead 10-11 W addendum 8 (다))',
    cell(two, 'die@1', 'd:3', GATE_IN, 0) === '7' && cell(two, 'die@1', 'd:3', GATE_IN, 1) === '9',
    `${cell(two, 'die@1', 'd:3', GATE_IN, 0)} | ${cell(two, 'die@1', 'd:3', GATE_IN, 1)}`);
  // Copy table (lead a27dfbb0f, W: the shape shown): the node's own, then each column its + · Δ · −, the id last; values
  // raw, several «; », none empty, a side not reached «missing» in each of its cells.
  const cpDie = two.sections.find((x) => x.type === 'die@1') || { groups: [], columnHeads: [], centreHeads: [], parts: [], rows: [] };
  const sheet = TV.sheetOf ? TV.sheetOf(cpDie) : { head: [], rows: [] };
  const cpRow = (id) => sheet.rows.find((r) => r[r.length - 1] === id) || [];
  const at = (h) => sheet.head.indexOf(h);
  const d3Delta = (((cpDie.rows.find((r) => r.id === 'd:3') || { cells: [] }).cells[0] || {}).delta || {}).value;
  ok('CP1 the section as a sheet, as Wide draws it: the node\'s own, each column its + · Δ · −, the id; a row as wide as the head; d:1\'s − «missing»; d:4 «1; 2»; d:3 7 and 9 and its Δ its number; no «—» (lead 10-11 W)',
    JSON.stringify(sheet.head) === JSON.stringify(['mat_id', `${GATE_IN} · +`, `${GATE_IN} · Δ`, `${GATE_IN} · −`, 'id'])
      && sheet.rows.length === cpDie.rows.length && sheet.rows.every((r) => r.length === sheet.head.length)
      && cpRow('d:1')[at(`${GATE_IN} · −`)] === TV.MISSING
      && cpRow('d:4')[at(`${GATE_IN} · +`)] === '1; 2' && cpRow('d:3')[at(`${GATE_IN} · +`)] === '7' && cpRow('d:3')[at(`${GATE_IN} · −`)] === '9'
      && typeof d3Delta === 'number' && cpRow('d:3')[at(`${GATE_IN} · Δ`)] === String(d3Delta)
      && !sheet.rows.some((r) => r.includes(TV.EMPTY)),
    JSON.stringify([sheet.head, cpRow('d:1'), cpRow('d:3'), cpRow('d:4')]));
  const differs = TV.sheetOf ? TV.sheetOf(cpDie, { rows: 'differs' }) : { rows: [] };
  const missing = TV.sheetOf ? TV.sheetOf(cpDie, { rows: 'missing' }) : { rows: [] };
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
  const bareDie = bare.sections.find((x) => x.type === 'die@1') || { columnHeads: [], rows: [] };
  const routesOf = (sec, id) => ((sec.rows.find((r) => r.id === id) || { routes: [] }).routes).map((w) => [w.sign, w.text]);
  ok('Z8 a type with no column: no column - how each side reached a row is its node cell\'s source line, a side that did not none (lead 10-11 W: the Route column retired)',
    JSON.stringify([bareDie.columnHeads, routesOf(bareDie, 'd:3'), routesOf(bareDie, 'd:1')])
      === JSON.stringify([[], [['+', 'inspected'], ['−', 'inspected']], [['+', TV.EMPTY]]]),
    JSON.stringify([bareDie.columnHeads, routesOf(bareDie, 'd:3'), routesOf(bareDie, 'd:1')]));
  const die = two.sections.find((x) => x.type === 'die@1') || { groups: [], columnHeads: [], centreHeads: [], parts: [], rows: [], listed: [] };
  const wafer = two.sections.find((x) => x.type === 'wafer@1') || { columnHeads: [] };
  ok('Z11 an edge attribute\'s head: its predicate, its arrow - in «←», out «→» -, its far type, its name (lead 10-11 W)',
    JSON.stringify([die.columnHeads, wafer.columnHeads]) === JSON.stringify([[GATE_IN], ['inspected → die@1 · gate']]), JSON.stringify([die.columnHeads, wafer.columnHeads]));
  ok('Z12 Δ under every column of two groups (W: «+ · Δ · −»): the first less the second where both say one number, «—» where not',
    JSON.stringify([die.parts.map((p) => p.delta), die.rows.map((r) => r.cells.map((c) => (c.delta ? c.delta.text : '')).join())])
      === JSON.stringify([[true], ['—', '—', '−2', '—']]), JSON.stringify([die.parts, die.rows.map((r) => r.cells.map((c) => c.delta))]));
  const dashed = view(SIGNED_STARTS, { ...SIGNED, edges: SIGNED.edges.filter((e) => e.id !== 'e:b3') });
  const dashDie = dashed.sections.find((x) => x.type === 'die@1') || { parts: [], rows: [] };
  ok('DX1 a column no row has a Δ for - every row «—» - draws none: no Δ part, no Δ cell, none copied; one row\'s Δ draws it (Z12) (lead 10-12)',
    JSON.stringify([dashDie.parts.map((p) => p.delta), dashDie.rows.map((r) => r.cells.map((c) => c.delta)), TV.sheetOf(dashDie).head])
      === JSON.stringify([[false], [[null], [null], [null], [null]], ['mat_id', `${GATE_IN} · +`, `${GATE_IN} · −`, 'id']]),
    JSON.stringify([dashDie.parts, dashDie.rows.map((r) => r.cells.map((c) => c.delta)), TV.sheetOf(dashDie).head]));
  ok('Z17 the node\'s own columns - the keys its rows carry - once, first, read off the row',
    JSON.stringify([die.centreHeads, (die.rows.find((r) => r.id === 'd:3') || { centre: [] }).centre.map((c) => c.text)])
      === JSON.stringify([['mat_id'], ['M-3']]), JSON.stringify(die.centreHeads));
  ok('Z20 a group a sign: its starts and its rows', JSON.stringify(die.groups) === JSON.stringify([
    { sign: '+', starts: 2, count: 3 }, { sign: '−', starts: 1, count: 2 }]), JSON.stringify(die.groups));
  const ADDED_HEAD = 'inspected ← wafer@1 · wafer';
  const added = new Map([['die@1', [{ steps: [{ predicate: 'inspected', direction: 'incoming' }], value: { on: 'key', name: 'wafer' },
    words: ['inspected ← wafer@1', 'wafer'] }]]]);
  const more = view(SIGNED_STARTS, SIGNED, added);
  ok('Z18 an added column: its route\'s far node, a cell of each group',
    cell(more, 'die@1', 'd:3', ADDED_HEAD, 0) === 'A' && cell(more, 'die@1', 'd:3', ADDED_HEAD, 1) === 'B',
    `${cell(more, 'die@1', 'd:3', ADDED_HEAD, 0)} ${cell(more, 'die@1', 'd:3', ADDED_HEAD, 1)}`);
  const capped = TV.cellWords({ missing: false, values: [1, 2], more: true, read: 2, total: 2199 });
  ok('Z19 words: past the cap, how many ways read of how many - and a difference without its float tail',
    JSON.stringify([capped.text, capped.rest, TV.deltaWords(0.22 - 0.3305), TV.deltaWords(19.5)])
      === JSON.stringify(['1', '2 of 2,199', '−0.1105', '+19.5']), JSON.stringify(capped));
  const moreDie = more.sections.find((x) => x.type === 'die@1') || { rows: [] };
  const m1 = moreDie.rows.find((r) => r.id === 'd:1') || { cells: [] };
  const m3 = moreDie.rows.find((r) => r.id === 'd:3') || { cells: [] };
  ok('Z21 a side that did not reach the node says missing in each of its cells; a side that did, a value or «—» (lead 10-11 W, the mockup B-ㄱ - in place of 34d91c09d 3\'s one cell across)',
    JSON.stringify([m1.cells.map((c) => [c.sides[1].text, c.sides[1].missing]), m3.cells.length]) === JSON.stringify([[['missing', true], ['missing', true]], 2]),
    JSON.stringify([m1.cells.map((c) => c.sides[1]), m3.cells.length]));
  const eqpAnswer = { ...SIGNED, edges: SIGNED.edges.map((e) => ({ ...e, qualifiers: { ...e.qualifiers, eqp: 'E' } })) };
  const eqp = view(SIGNED_STARTS, eqpAnswer);
  const eqpDie = eqp.sections.find((x) => x.type === 'die@1') || { columnHeads: [], parts: [] };
  const groupOfGate = (eqpDie.parts[0] || {}).group;
  const eqpOpen = view(SIGNED_STARTS, eqpAnswer, new Map(), { open: new Map([['die@1', new Set([groupOfGate])]]) });
  const eqpOpenDie = eqpOpen.sections.find((x) => x.type === 'die@1') || { columnHeads: [], parts: [] };
  ok('Z22 a group opens on its number cells, the rest behind its «▸ N»; opened, the numbers first, the rest after (lead 10-11 W addendum 8)',
    JSON.stringify([eqpDie.columnHeads, eqpDie.parts.map((p) => p.folded), eqpOpenDie.columnHeads, eqpOpenDie.parts.map((p) => p.open)])
      === JSON.stringify([[GATE_IN], [1], [GATE_IN, 'inspected ← wafer@1 · eqp'], [true, true]]),
    JSON.stringify([eqpDie.columnHeads, eqpDie.parts, eqpOpenDie.columnHeads]));
  const offDie = (view(SIGNED_STARTS, SIGNED, new Map(), { off: new Map([['die@1', new Set([groupOfGate])]]) }).sections.find((x) => x.type === 'die@1') || { columnHeads: [], listed: [] });
  // An added column no row has a value in (a key the wafers do not carry).
  const nothing = new Map([['die@1', [{ steps: [{ predicate: 'inspected', direction: 'incoming' }], value: { on: 'key', name: 'nothing' },
    words: ['inspected ← wafer@1', 'nothing'] }]]]);
  const nothingDie = view(SIGNED_STARTS, SIGNED, nothing).sections.find((x) => x.type === 'die@1') || { columnHeads: [], listed: [] };
  ok('Z23 a column no row has a value in (note; an added key no wafer carries) is in no list - not drawn, not behind a group\'s ▸, not in Columns, not in Long; a group Columns turns off is not drawn, listed off (lead 10-11 W)',
    JSON.stringify([nothingDie.columnHeads, nothingDie.listed.length]) === JSON.stringify([[GATE_IN], 1]) &&
    JSON.stringify([die.columnHeads, die.parts.map((x) => x.folded), die.listed.map((x) => [x.head, x.on]), die.long.map((x) => x.head), offDie.columnHeads, offDie.listed.map((x) => [x.head, x.on])])
      === JSON.stringify([[GATE_IN], [0], [['inspected ← wafer@1', true]], ['inspected ← wafer@1'], [], [['inspected ← wafer@1', false]]]),
    JSON.stringify([die.columnHeads, die.listed, die.long.map((x) => x.head), offDie.columnHeads, offDie.listed]));
  // C (lead 99ed68cb7, W 11): who gave a value - an edge's subject, a node's own - its keys and its side's route; none
  // when the row gave it itself.
  const srcOf = (t, type, id, head, group) => ((raw(t, type, id, head, group) || {}).sources || null);
  const MEASURES_IN = 'measures ← wafer@1 · value';
  const edgeSrc = view(BOND_STARTS, BOND_SRC);
  // The − side's value given by a die: its own group, its far type (lead 10-11 W addendum 8 (다)).
  const MEASURES_DIE = 'measures ← die@1 · value';
  ok('Z38 a value\'s source, the measurement an edge: the node that measured it, its keys and its side\'s route - a wafer\'s in the wafers\' group, a die\'s in the dies\'',
    JSON.stringify([srcOf(edgeSrc, 'quantity@1', 'q:1', MEASURES_IN, 0), srcOf(edgeSrc, 'quantity@1', 'q:1', MEASURES_DIE, 1)])
      === JSON.stringify([['B · start', `C · ${BONDING}`], ['N-1 · in_container']]),
    JSON.stringify([srcOf(edgeSrc, 'quantity@1', 'q:1', MEASURES_IN, 0), srcOf(edgeSrc, 'quantity@1', 'q:1', MEASURES_DIE, 1)]));
  const eventSrc = TV.walkTableView(BOND_SRC_EVENT, DECL.entities, DECL.predicates, undefined, BOND_STARTS, OF_VALUE);
  const OF_IN = 'of ← measurement@1 · value';
  ok('Z39 a value\'s source, the measurement an event node: that node, its label (no keys), and its side\'s route',
    JSON.stringify([srcOf(eventSrc, 'quantity@1', 'q:1', OF_IN, 0), srcOf(eventSrc, 'quantity@1', 'q:1', OF_IN, 1)])
      === JSON.stringify([['M:1 · measured', `M:3 · ${BONDING} → measured`], ['M:2 · in_container → measured']]),
    JSON.stringify([srcOf(eventSrc, 'quantity@1', 'q:1', OF_IN, 0), srcOf(eventSrc, 'quantity@1', 'q:1', OF_IN, 1)]));
  const bt = TV.walkTableView(SRC_18766, SRC_18766._entities, [], undefined, SRC_18766._starts);
  const btId = SRC_18766.nodes.find((n) => n.label === 'bond_temp').id;
  const BT_HEAD = 'measures ← wafer · value';
  const btCell = (g) => raw(bt, 'quantity', btId, BT_HEAD, g) || {};
  ok('Z40 18766 bond_temp: + 35.5 «SYN-BW-103-11 · start», 21.5 and 23.5 the core wafers by their bonding; − 13 «SYN-BW-SPL-400-19 · start» - one group, its far type, Δ between',
    JSON.stringify([btCell(0).values, btCell(0).sources, btCell(1).text, btCell(1).sources]) === JSON.stringify([['35.5', '21.5', '23.5'],
      ['SYN-BW-103-11 · start', 'SYN-CW-103-01 · in_container → bonded_from → in_container', 'SYN-CW-103-02 · in_container → bonded_from → in_container'],
      '13', ['SYN-BW-SPL-400-19 · start']]),
    JSON.stringify([btCell(0).values, btCell(0).sources, btCell(1).text, btCell(1).sources]));
  const bc = TV.walkTableView(SRC_COLLECT, SRC_COLLECT._entities, [], undefined, SRC_COLLECT._starts);
  const bcCell = (g) => raw(bc, 'quantity', btId, BT_HEAD, g) || {};
  const everySource = bc.sections.flatMap((x) => x.rows.flatMap((r) => r.cells.flatMap((c) => c.sides.flatMap((side) => (side.sources || []).filter(Boolean)))));
  ok('Z42 collect quantity alone (the demo\'s form): the wafers are not in nodes, their keys read off their ids - the same sources as Z40, no id in any (lead 10-11)',
    JSON.stringify([bcCell(0).sources, bcCell(1).sources]) === JSON.stringify([btCell(0).sources, btCell(1).sources])
      && everySource.length >= 4 && !everySource.some((w) => w.includes('ledger-entity:')),
    JSON.stringify([bcCell(0).sources, bcCell(1).sources, everySource.filter((w) => w.includes('ledger-entity:')).length]));
  // A node the answer did not send and whose id is no entity's: «—», never the id.
  const unsent = view(BOND_STARTS, { ...BOND_SRC, nodes: BOND_SRC.nodes.filter((n) => n.id !== 'w:c') });
  // Its type unknown, its value stands in a group of no far type.
  ok('Z43 a value\'s node neither sent nor an entity id: its source says «—», not the id',
    JSON.stringify([srcOf(unsent, 'quantity@1', 'q:1', MEASURES_IN, 0), srcOf(unsent, 'quantity@1', 'q:1', 'measures ← · value', 0)])
      === JSON.stringify([['B · start'], [`${TV.EMPTY} · ${BONDING}`]]),
    JSON.stringify([srcOf(unsent, 'quantity@1', 'q:1', MEASURES_IN, 0), srcOf(unsent, 'quantity@1', 'q:1', 'measures ← · value', 0)]));
  // D (lead 99ed68cb7): who reached a row - A only, A + B, B only - each side its own; B's path under the node.
  const ctlKinds = (t, type) => {
    const sec = t.sections.find((x) => x.type === type) || { rows: [] };
    return [sec.reached, sec.rows.length, sec.rows.filter((r) => r.reached && r.reached[0] === 'b').map((r) => r.id).sort()];
  };
  const qa = new Set(CTL_18766.a.nodes.map((n) => n.id));
  const onlyB = CTL_18766.b.nodes.filter((n) => n.type === 'quantity' && !qa.has(n.id)).map((n) => n.id).sort();
  const ctl = TV.walkTableView(CTL_18766.a, [], [], undefined, CTL_STARTS, new Map(), {}, CTL_18766.b);
  ok('ZD1 18766 from void, B leads_to: quantity 35 rows - A only 17 · A + B 15 · B only 3, the three B only the ones A did not reach',
    JSON.stringify(ctlKinds(ctl, 'quantity')) === JSON.stringify([[{ a: 17, ab: 15, b: 3 }], 35, onlyB]) && onlyB.length === 3,
    JSON.stringify(ctlKinds(ctl, 'quantity')));
  const noCtl = TV.walkTableView(CTL_18766.a, [], [], undefined, CTL_STARTS);
  ok('ZD2 no B: no row says who reached it, A\'s rows alone',
    JSON.stringify(ctlKinds(noCtl, 'quantity')) === JSON.stringify([null, 32, []])
      && noCtl.sections.every((x) => x.reached === null && x.rows.every((r) => r.reached === null)),
    JSON.stringify(ctlKinds(noCtl, 'quantity')));
  const sides = TV.walkTableView(SIGNED, DECL.entities, DECL.predicates, undefined, SIGNED_STARTS, new Map(), {}, CTL_SIGNED);
  const sDie = sides.sections.find((x) => x.type === 'die@1') || { rows: [] };
  const sRow = (id) => sDie.rows.find((r) => r.id === id) || { routes: [] };
  const sRoute = (id, sign) => { const w = sRow(id).routes.find((x) => x.sign === sign) || {}; return [w.text, w.sources || null]; };
  ok('ZD3 two baskets, each side its own: d:3 A + B on + and A only on −, d:5 B only on −; the node\'s way names each walk that reached it, on one line; a value only B brought, B\'s source',
    JSON.stringify([sDie.reached, sRow('d:3').reached, sRow('d:5').reached, sRoute('d:3', '+'), sRoute('d:3', '−'), sRoute('d:5', '−'),
      srcOf(sides, 'die@1', 'd:5', GATE_IN, 1), srcOf(sides, 'die@1', 'd:3', GATE_IN, 0)])
      === JSON.stringify([[{ a: 2, ab: 1, b: 0 }, { a: 2, ab: 0, b: 1 }], ['ab', 'a'], [null, 'b'], ['A inspected · B leads_to', null],
        ['A inspected', null], ['B leads_to → inspected', null], ['B · W5 · leads_to'], ['A · start']]),
    JSON.stringify([sDie.reached, sRow('d:3').reached, sRow('d:5').reached, sRoute('d:3', '+'), sRoute('d:3', '−'), sRoute('d:5', '−'),
      srcOf(sides, 'die@1', 'd:5', GATE_IN, 1), srcOf(sides, 'die@1', 'd:3', GATE_IN, 0)]));
  // Two number cells in one group: each its own Δ.
  const scored = view(SIGNED_STARTS, { ...SIGNED, edges: SIGNED.edges.map((e, k) => ({ ...e, qualifiers: { ...e.qualifiers, score: 10 + k } })) });
  const scoredDie = scored.sections.find((x) => x.type === 'die@1') || { parts: [] };
  ok('Z37 two number cells in one group: both open, each its own Δ under it',
    JSON.stringify(scoredDie.parts.map((p) => [p.leaf, p.delta])) === JSON.stringify([['gate', true], ['score', true]]),
    JSON.stringify(scoredDie.parts));
  // How each side reached a row on both schemes (lead df11f9e81, W: the node's source line): the base wafer a start, the
  // core wafer its bonding route, each side its own.
  const routeOf = (scheme) => {
    const t = view(BOND_STARTS, scheme);
    const of = (type, id, sign) => {
      const sec = t.sections.find((x) => x.type === type) || { rows: [] };
      const w = ((sec.rows.find((r) => r.id === id) || { routes: [] }).routes).find((x) => x.sign === sign);
      return w ? w.text : '[missing]';
    };
    return [['wafer@1', 'w:b'], ['wafer@1', 'w:c'], ['wafer@1', 'w:n'], ['quantity@1', 'q:1']].map(([type, id]) => [id, of(type, id, '+'), of(type, id, '−')]);
  };
  const bondWant = (plus, minus) => [['w:b', TV.STARTED, '[missing]'], ['w:c', BONDING, '[missing]'], ['w:n', '[missing]', TV.STARTED],
    ['q:1', plus, minus]];
  ok('Z29 a node\'s route = the paths the server walked, the measurement an edge: the base wafer «start», the core wafer its bonding, + and − each its own starts\' paths, a side not reached none',
    JSON.stringify(routeOf(BOND_EDGE)) === JSON.stringify(bondWant('measures', 'in_container → measures')), JSON.stringify(routeOf(BOND_EDGE)));
  ok('Z30 a node\'s route, the measurement an event node: the same wafers, the quantity two steps on',
    JSON.stringify(routeOf(BOND_EVENT)) === JSON.stringify(bondWant('measured → of', 'in_container → measured → of')),
    JSON.stringify(routeOf(BOND_EVENT)));
  const STATIC_ENTITIES = [...DECL.entities, { type: 'quantity@1', keys: [], class: ['static'] }];
  const waferHeads = (entities) => (TV.walkTableView(BOND_SRC, entities, DECL.predicates, undefined, BOND_STARTS).sections
    .find((x) => x.type === 'wafer@1') || { columnHeads: [] }).columnHeads;
  ok('Z44 a far node of a type the declaration calls static stands its own group, named; of any other type one group, its type (lead 10-11 W addendum 8 (다))',
    JSON.stringify([waferHeads(STATIC_ENTITIES), waferHeads(DECL.entities)]) === JSON.stringify([['measures → Q:1 · value'], ['measures → quantity@1 · value']]),
    JSON.stringify([waferHeads(STATIC_ENTITIES), waferHeads(DECL.entities)]));
  // The groups that set the sides against each other nearest the node: «alpha» (the + side alone) sorts first by name,
  // «measures» (both sides, a Δ) stands first.
  const ORDERED = { ...BOND_EDGE, edges: [...BOND_EDGE.edges, be('w:n', 'measures', 'q:1', { value: 4 }), be('w:b', 'alpha', 'q:1', { v: 5 })] };
  const orderedHeads = (view(BOND_STARTS, ORDERED).sections.find((x) => x.type === 'quantity@1') || { columnHeads: [] }).columnHeads;
  ok('Z45 a group with a Δ under it nearest the node, the rest after, each in its order (34d91c09d 2 carried to W\'s groups: the first Δ in the first screen)',
    JSON.stringify(orderedHeads) === JSON.stringify(['measures ← wafer@1 · value', 'alpha ← wafer@1 · v', 'measures ← die@1 · value']),
    JSON.stringify(orderedHeads));
  const coreSec = view(BOND_STARTS, BOND_TWO).sections.find((x) => x.type === 'wafer@1') || { rows: [] };
  const core = ((coreSec.rows.find((r) => r.id === 'w:c') || { routes: [] }).routes)[0] || {};
  ok('Z31 two paths walked to one node: the first and «+N», every one kept (the nine\'s several values)',
    JSON.stringify([core.text, core.rest, core.values]) === JSON.stringify([BONDING, '+1',
      [BONDING, STACKING]]), JSON.stringify(core));
  // Add here and More (lead 10-11 W addenda 5, 6): a walk merged into the step by mergeWalks - from s:a (+ only), s:b (−
  // only) and d:3 (both): d:7 on +, d:8 on −, d:9 on both, the existing d:1 a − value; More from the deepest node.
  const path1 = (seed, id, predicate) => ({ seed, hops: [{ id: seed }, { id, predicates: [predicate] }] });
  const dn = (id, depth) => ({ id, type: 'die@1', label: id.toUpperCase(), depth, keys: { mat_id: id.toUpperCase() } });
  const ADD = { nodes: [SIGNED.nodes[0], SIGNED.nodes[2], SIGNED.nodes[5], dn('d:7', 1), dn('d:8', 1), dn('d:9', 1), SIGNED.nodes[3]],
    edges: [be('s:a', 'inspected', 'd:7', { gate: 5 }), be('s:b', 'inspected', 'd:8', { gate: 6 }), be('s:b', 'inspected', 'd:1', { gate: 4 }),
      be('d:3', 'bonded_to', 'd:9', { gate: 3 })],
    propagation: { ranked: [['d:7', 's:a', 'inspected'], ['d:8', 's:b', 'inspected'], ['d:1', 's:b', 'inspected'], ['d:9', 'd:3', 'bonded_to']]
      .map(([id, seed, p]) => ({ id, evidence: [path1(seed, id, p)] })) } };
  const MORE_ANSWER = { nodes: [SIGNED.nodes[5], dn('d:9', 1), dn('d:10', 1)],
    edges: [be('d:3', 'bonded_to', 'd:9', { gate: 3 }), be('d:3', 'bonded_to', 'd:10', { gate: 8 })],
    propagation: { ranked: ['d:9', 'd:10'].map((id) => ({ id, evidence: [path1('d:3', id, 'bonded_to')] })) } };
  const addOf = (answer, seeds, words) => ({ words, seeds, answer });
  const add = addOf(ADD, ['s:a', 's:b', 'd:3'], 'walk on · inspected → die@1');
  const withAdds = (adds) => TV.walkTableView(SIGNED, DECL.entities, DECL.predicates, undefined, SIGNED_STARTS, new Map(), {}, null, adds);
  const one = withAdds([add]);
  const BONDED = 'bonded_to ← die@1 · gate';
  const addDie = one.sections.find((x) => x.type === 'die@1') || { rows: [], adds: [] };
  const routes = (id) => ((addDie.rows.find((r) => r.id === id) || { routes: [] }).routes).map((w) => `${w.sign} ${w.text}`);
  ok('AH1 Add here: d:7 + only, d:8 − only, d:9 both with its shared start, d:1 its − value; «+3 from walk on»; the same walk twice no row more; × leaves the rest',
    JSON.stringify([rowIds(one), cell(one, 'die@1', 'd:7', GATE_IN, 0), cell(one, 'die@1', 'd:7', GATE_IN, 1), cell(one, 'die@1', 'd:8', GATE_IN, 0),
      cell(one, 'die@1', 'd:8', GATE_IN, 1), cell(one, 'die@1', 'd:1', GATE_IN, 1), cell(one, 'die@1', 'd:9', BONDED, 0), cell(one, 'die@1', 'd:9', BONDED, 1),
      routes('d:7'), routes('d:9'), addDie.adds, rowIds(withAdds([add, add])), rowIds(withAdds([])), rowIds(view(SIGNED_STARTS))])
      === JSON.stringify([`${ALL},d:7,d:8,d:9`.split(',').sort().join(','), '5', '[missing]', '[missing]', '6', '4', '3', '3',
        ['+ inspected'], ['+ bonded_to · via shared M-3', '− bonded_to · via shared M-3'], [{ at: 0, words: add.words, n: 3 }],
        `${ALL},d:7,d:8,d:9`.split(',').sort().join(','), ALL, ALL]),
    JSON.stringify([rowIds(one), cell(one, 'die@1', 'd:7', GATE_IN, 0), cell(one, 'die@1', 'd:7', GATE_IN, 1), cell(one, 'die@1', 'd:8', GATE_IN, 0),
      cell(one, 'die@1', 'd:8', GATE_IN, 1), cell(one, 'die@1', 'd:1', GATE_IN, 1), cell(one, 'die@1', 'd:9', BONDED, 0), cell(one, 'die@1', 'd:9', BONDED, 1),
      routes('d:7'), routes('d:9'), addDie.adds, rowIds(withAdds([add, add]))]));
  const moreAdd = addOf(MORE_ANSWER, ['d:3'], 'More');
  const union = new Set([...SIGNED.nodes, ...ADD.nodes, ...MORE_ANSWER.nodes].map((n) => n.id));
  const both = withAdds([add, moreAdd]);
  // The cap is a section's own (lead 10-12): wafer 1 · die 250 · defect 50 from one start.
  const perType = { nodes: [{ id: 'w', type: 'wafer', depth: 0 }, ...Array.from({ length: 250 }, (_, i) => ({ id: `d${i}`, type: 'die', depth: 1 })),
    ...Array.from({ length: 50 }, (_, i) => ({ id: `f${i}`, type: 'defect', depth: 2 }))], edges: [] };
  const capView = TV.walkTableView(perType, [], [], undefined, { positive: ['w'], negative: [] });
  // A cut cell (lead 10-13): the cell says 50 of 60 and the view is cut; every way read (the screen's Show all) - the cell
  // holds 60, Long 60 lines, the view not cut.
  {
    const cutView = TV.walkTableView(WIDE, [], [], undefined, WIDE_STARTS);
    const allView = TV.walkTableView(WIDE, [], [], undefined, WIDE_STARTS, new Map(), {}, null, [], Infinity);
    const wSec = (v) => v.sections.find((s) => s.type === 'wafer');
    const sidesOf = (v) => (((wSec(v) || { rows: [] }).rows.find((r) => r.id === 'w') || { cells: [] }).cells || []).flatMap((c) => c.sides || []);
    const cutSide = sidesOf(cutView).find((s) => s && s.rest && s.rest.includes(' of '));
    const longN = (v) => TV.longLines(v, wSec(v)).filter((l) => String(l.column).includes('"measures"')).length;
    ok('WC1 a cell past its ways says «50 of 60» and the view is cut; every way read - the cell holds 60, Long 60 lines, not cut',
      Boolean(cutSide) && cutSide.rest === '50 of 60' && cutView.waysCut === true
        && sidesOf(allView).some((s) => s && s.rest === '+59') && allView.waysCut === false && longN(cutView) === 50 && longN(allView) === 60,
      JSON.stringify([cutSide && cutSide.rest, cutView.waysCut, sidesOf(allView).map((s) => s && s.rest), allView.waysCut, longN(cutView), longN(allView)]));
  }
  ok('CAP1 each section its own 200: die 200 and «50 more» under it, the defect section all 50, the wafer its 1',
    JSON.stringify([capView.sections.map((s) => [s.type, s.rows.length, s.hidden]), capView.shown, capView.hidden])
      === JSON.stringify([[['wafer', 1, 0], ['die', 200, 50], ['defect', 50, 0]], 251, 50]),
    JSON.stringify([capView.sections.map((s) => [s.type, s.rows.length, s.hidden]), capView.shown, capView.hidden]));
  ok('MO1 two additions (Add here, d:3\'s walk): merged rows = the union; × on Add here leaves the other\'s',
    JSON.stringify([both.shown, rowIds(withAdds([moreAdd]))])
      === JSON.stringify([union.size, `${ALL},d:10,d:9`.split(',').sort().join(',')]),
    JSON.stringify([both.shown, union.size, rowIds(withAdds([moreAdd]))]));
};
// ── sort · filter as the one «what does this table show» seat (lead 10-11 W addendum 7: table_view.shownOf) ──
const filterSuite = (TV) => {
  {
    // A walk's pages merged (owner 10-12 «이어 걷기»): nodes, edges and ranked rows each once, the newer page's first.
    const pageA = { nodes: [{ id: 'x' }, { id: 'y' }], edges: [{ id: 'e1' }], propagation: { ranked: [{ id: 'x' }, { id: 'y' }] } };
    const pageB = { nodes: [{ id: 'z' }], edges: [{ id: 'e2' }], propagation: { ranked: [{ id: 'z' }] } };
    const m = TV.mergeWalks(pageB, pageA);
    ok('MR3 pages merged: every node, edge and ranked row once',
      JSON.stringify([m.nodes.map((n) => n.id), m.edges.map((e) => e.id), m.propagation.ranked.map((r) => r.id)])
        === JSON.stringify([['x', 'y', 'z'], ['e1', 'e2'], ['x', 'y', 'z']]), JSON.stringify(m));
    // The server: a node a later page reached further comes again in that page's ranked - the later row stands.
    const again = TV.mergeWalks({ nodes: [], edges: [], propagation: { ranked: [{ id: 'x', reach: [2, 0] }] } },
      { nodes: [{ id: 'x' }], edges: [], propagation: { ranked: [{ id: 'x', reach: [1, 0] }] } });
    ok('MR4 a node ranked on two pages: the later page\'s row (its reach grown) stands', JSON.stringify(again.propagation.ranked)
      === JSON.stringify([{ id: 'x', reach: [2, 0] }]), JSON.stringify(again.propagation));
    // A continued page's top set is a difference (implementer A d5df12352): merged over pages = one walk's top set.
    const p1 = { nodes: [], edges: [], propagation: { ranked: [], top_set: ['a', 'b', 'c'] } };
    const p2 = { nodes: [], edges: [], propagation: { ranked: [], top_set: ['d'], top_set_left: ['b'] } };
    const p3 = { nodes: [], edges: [], propagation: { ranked: [], top_set: ['b', 'e'], top_set_left: ['a'] } };
    const pages = TV.mergeWalks(p3, TV.mergeWalks(p2, p1));
    const control = TV.mergeWalks({ nodes: [], edges: [], propagation: { ranked: [], top_set: ['x'] } }, p1);
    ok('TS1 a continued page\'s top set is a difference: three pages merged = one walk\'s top set, no difference left in it; a walk with none (a control walk) keeps its own',
      JSON.stringify([[...pages.propagation.top_set].sort(), 'top_set_left' in pages.propagation, control.propagation.top_set])
        === JSON.stringify([['b', 'c', 'd', 'e'], false, ['x']]), JSON.stringify([pages.propagation, control.propagation]));
    // The ways a walk took to the collected types (owner 10-12): a line a way, its nodes counted, the most first.
    const ways = TV.walkedRoutes(WALKED, new Set(['die@1']));
    ok('RT1 the walked routes to die, the most first: wafer —in→ lot —has→ die for two, wafer —inspected→ die for one; the lot not counted',
      JSON.stringify(ways.map((w) => [w.words, w.count, w.hops, w.follow]))
        === JSON.stringify([['wafer@1 —in@1→ lot@1 —has@1→ die@1', 2, 2, ['in@1', 'has@1']], ['wafer@1 —inspected@1→ die@1', 1, 1, ['inspected@1']]]),
      JSON.stringify(ways));
  }
  {
    const jv = TV.walkTableView(JUDGED, DECL.entities);
    const plain = TV.walkTableView(RESULT, DECL.entities);
    const sec = (v, t) => v.sections.find((x) => x.type === t) || { rows: [], centreHeads: [] };
    const last = (row) => row.centre[row.centre.length - 1].text;
    ok('AX01 a judged answer: each section\'s last own column «→ <the auxiliary node>», a row its yes · hops, no or unknown; none judged, no such column',
      JSON.stringify([sec(jv, 'die@1').centreHeads.slice(-1), sec(jv, 'die@1').rows.map(last), sec(jv, 'wafer@1').rows.map(last),
        sec(jv, 'die@1').judged, sec(plain, 'die@1').judged, sec(plain, 'die@1').centreHeads.some((h) => h.startsWith('→')),
        sec(jv, 'die@1').tally, sec(jv, 'wafer@1').tally, sec(plain, 'die@1').tally])
        === JSON.stringify([['→ q:aux'], ['2 hops', 'none'], ['unknown'], true, false, false,
          '→ q:aux: 1 reach · 1 none · 0 unknown', '→ q:aux: 0 reach · 0 none · 1 unknown', ''])
        // The auxiliary node itself in the answer: the server's 0, said as it is.
        && TV.reachWords({ state: 'found', hops: 0, via: 'q:aux' }, false) === '0 hops',
      JSON.stringify([sec(jv, 'die@1').centreHeads, sec(jv, 'die@1').rows.map(last), sec(jv, 'wafer@1').rows.map(last),
        sec(jv, 'die@1').tally, sec(jv, 'wafer@1').tally]));
    const only = TV.shownOf(sec(jv, 'die@1'), { reaches: true });
    const sheet = TV.sheetOf(sec(jv, 'die@1'), { reaches: true });
    ok('AX2 «Reaches only» is the one shown seat: the yes rows alone, and Copy the same rows',
      JSON.stringify([only.lines.map((l) => l.row.id), only.filtering, sheet.rows.length]) === JSON.stringify([['n:1'], true, 1]),
      JSON.stringify([only.lines.map((l) => l.row.id), only.filtering, sheet.rows.length]));
  }
  const view = TV.walkTableView(sfAnswer(TV.PICK_MOST + 2), SF_DECL.entities, SF_DECL.predicates, undefined, SF_STARTS);
  const sec = view.sections.find((x) => x.type === 'die@1') || { rows: [], centreHeads: [], columns: [], groups: [], parts: [] };
  const grid = TV.gridOf(sec);
  const at = (head, cols = grid.columns) => cols.findIndex((c) => c.head === head);
  const K = { gate: at(`${GATE_IN} · +`), mat: at('mat_id'), grade: at('grade') };
  const key = (k) => (grid.columns[k] || {}).key;
  // A column a mutant took away reads as nothing, not a throw: the cell it names fails, the rest still run.
  const words = (f, k, lines) => TV.shownOf(sec, f, lines).lines.map((l) => (l.cells[k] || {}).words).join();
  const ids = (f, lines) => TV.shownOf(sec, f, lines).lines.map((l) => l.id).join();
  const asc = words({ sort: { key: key(K.gate), dir: 'asc' } }, K.gate);
  const desc = words({ sort: { key: key(K.gate), dir: 'desc' } }, K.gate);
  ok('SF1 a sort three ways: ascending, descending, then its first order (lead 10-11 W addendum 7)',
    JSON.stringify([asc, desc, ids({ sort: null }), ids({})]) === JSON.stringify([SF_ASC, SF_DESC, sec.rows.map((r) => r.id).join(), sec.rows.map((r) => r.id).join()]),
    JSON.stringify([asc, desc]));
  ok('SF2 numbers sort as numbers: 9 before 10, 100 after 50 - and words as a reader orders them: M-2 before M-10',
    asc.startsWith('1,2,3,4,6,7,8,9,10,11,50,100') && words({ sort: { key: key(K.mat), dir: 'asc' } }, K.mat).startsWith('M-1,M-2,M-3'),
    `${asc} | ${words({ sort: { key: key(K.mat), dir: 'asc' } }, K.mat)}`);
  ok('SF3 blanks last, ascending and descending', asc.endsWith(',,') && desc.endsWith(',,') && !asc.startsWith(','), `${asc} | ${desc}`);
  // Wide's + · Δ · − each a column of its own: on SIGNED's die section + puts d:4 (1) before d:3 (7), − puts d:3 (9) first.
  const signed = TV.walkTableView(SIGNED, DECL.entities, DECL.predicates, undefined, SIGNED_STARTS).sections.find((x) => x.type === 'die@1');
  const sg = signed ? TV.gridOf(signed) : { columns: [] };
  const sKey = (h) => (sg.columns.find((c) => c.head === h) || {}).key;
  const first = (h) => (signed ? TV.shownOf(signed, { sort: { key: sKey(h), dir: 'asc' } }).lines.map((l) => l.id).slice(0, 2).join() : '');
  ok('SF4 Wide\'s + · Δ · − each a column to sort by: + d:4 (1) then d:3 (7); − d:3 (9) first; Δ d:3 (−2) first',
    JSON.stringify([sg.columns.map((c) => c.head), first(`${GATE_IN} · +`), first(`${GATE_IN} · −`).split(',')[0], first(`${GATE_IN} · Δ`).split(',')[0]])
      === JSON.stringify([['mat_id', `${GATE_IN} · +`, `${GATE_IN} · Δ`, `${GATE_IN} · −`], 'd:4,d:3', 'd:3', 'd:3']),
    JSON.stringify([sg.columns.map((c) => c.head), first(`${GATE_IN} · +`), first(`${GATE_IN} · −`), first(`${GATE_IN} · Δ`)]));
  // Long: every column - its value numbers first then words, its node as a reader orders it.
  const lines = TV.longLines(view, sec);
  const lg = TV.gridOf(sec, lines);
  const lv = at('value', lg.columns);
  const lkey = (h) => (lg.columns[at(h, lg.columns)] || {}).key;
  const longValues = TV.shownOf(sec, { sort: { key: lkey('value'), dir: 'asc' } }, lines).lines.map((l) => (l.cells[lv] || {}).words);
  ok('SF5 Long sorts by any of its columns: value - its numbers as numbers, then its words; node',
    lg.columns.map((c) => c.head).join() === TV.LONG_HEAD.join() && longValues.slice(0, 12).join() === SF_ASC.replace(/,+$/, '')
      && longValues.slice(12).join() === 'A,A,A,A,A,B,B,B,B,B'
      && (TV.shownOf(sec, { sort: { key: lkey('node'), dir: 'desc' } }, lines).lines[0] || { line: {} }).line.node === 'SD14',
    longValues.join());
  // Long, two baskets (owner 10-12 「좌우 값부터 제대로 띄워」): a value column a side, a record under the side its way came by.
  const lsView = TV.walkTableView(LS, LS_DECL.entities, LS_DECL.predicates, undefined, LS_STARTS);
  const lsSec = lsView.sections.find((x) => x.type === 'quantity@1');
  const lsGrid = lsSec ? TV.gridOf(lsSec, TV.longRecords(lsView, lsSec, TV.longLines(lsView, lsSec))) : { columns: [], lines: [] };
  const lsAt = (h) => lsGrid.columns.findIndex((c) => c.head === h);
  const lsSides = lsGrid.lines.filter((l) => l.line.name === 'measures ← wafer@1')
    .map((l) => [l.cells[lsAt('+')].words, l.cells[lsAt('−')].words]);
  const lsWhere = (plus, minus) => lsSides.filter(([p, m]) => Boolean(p) === plus && Boolean(m) === minus).map(([p, m]) => p || m).sort().join();
  ok('LS1 Long, two baskets: + and − a value column each, no Δ - 3 + records left, 5 − right, the one both reached in both, a line a record (owner 10-12)',
    JSON.stringify([lsGrid.columns.map((c) => c.head), lsWhere(true, false), lsWhere(false, true), lsWhere(true, true), lsSides.length])
      === JSON.stringify([['node', 'value name', '+', '−', 'point', 'time', 'from'], '20,21,22', '23,24,25,26,27', '28', 9]),
    JSON.stringify([lsGrid.columns.map((c) => c.head), lsSides]));
  const lrView = TV.walkTableView(LS_RECORDS, LS_DECL.entities, LS_DECL.predicates, undefined, LS_STARTS);
  const lrSec = lrView.sections.find((x) => x.type === 'quantity@1');
  const lrRows = lrSec ? TV.longRecords(lrView, lrSec, TV.longLines(lrView, lrSec)).map(TV.longRow) : [];
  const lrOf = (from) => lrRows.filter((r) => r[6].startsWith(from)).map((r) => r.slice(2, 6));
  const p1 = lrOf('p:1');
  ok('LS2 Long a line a record (lead 10-12 C3): an edge\'s two records two lines, each its value, point and time; one record both sides reached one line in both columns',
    JSON.stringify([p1.map((r) => r.slice(0, 3)), lrOf('w:s').map((r) => r.slice(0, 2)), lrRows.length])
      === JSON.stringify([[['300', '', 'step CLEAN'], ['90', '', 'step ETCH']], [['28', '28']], 10])
      && p1.length === 2 && Boolean(p1[0][3]) && Boolean(p1[1][3]) && p1[0][3] !== p1[1][3],
    JSON.stringify(lrRows));
  // Filters, each by its kind - judged over every line.
  const kind = (k) => (k < 0 ? 'none' : TV.filterKind(grid.lines, k).kind);
  ok('SF6 a column of more values than a pick lists filters by the words it contains, any case: mat_id «m-1» - M-1, M-10 … M-14',
    kind(K.mat) === 'contains' && ids({ columns: { [key(K.mat)]: { contains: 'm-1' } } }) === 'sd:1,sd:10,sd:11,sd:12,sd:13,sd:14',
    `${kind(K.mat)} ${ids({ columns: { [key(K.mat)]: { contains: 'm-1' } } })}`);
  ok('SF7 a column of numbers filters by a range: gate 5 … 10, a blank out',
    kind(K.gate) === 'range' && words({ columns: { [key(K.gate)]: { min: 5, max: 10 } } }, K.gate) === '10,9,7,8,6'
      && words({ columns: { [key(K.gate)]: { min: 50 } } }, K.gate) === '100,50',
    `${kind(K.gate)} ${words({ columns: { [key(K.gate)]: { min: 5, max: 10 } } }, K.gate)}`);
  const pick = K.grade < 0 ? { kind: 'none', choices: [] } : TV.filterKind(grid.lines, K.grade);
  ok('SF8 a column of a few values picks them: grade A · B · blank; A picked out leaves B and blank',
    pick.kind === 'pick' && pick.choices.join() === 'A,B,' && words({ columns: { [key(K.grade)]: { out: ['A'] } } }, K.grade) === 'B,,B,,B,,B,,B',
    `${pick.kind} ${pick.choices} ${words({ columns: { [key(K.grade)]: { out: ['A'] } } }, K.grade)}`);
  ok('SF9 the search box: a line\'s words or its node\'s keys, any case - «m-12» one row; with a column filter, both hold',
    ids({ find: 'm-12' }) === 'sd:12' && ids({ find: 'M-1', columns: { [key(K.gate)]: { max: 8 } } }) === 'sd:10,sd:12,sd:13,sd:14'
      && ids({ find: '  ' }) === sec.rows.map((r) => r.id).join(),
    `${ids({ find: 'm-12' })} | ${ids({ find: 'M-1', columns: { [key(K.gate)]: { max: 8 } } })}`);
  ok('SF10 «filtering» - what makes the head say «N of M» - a filter set, not a sort or an empty field',
    JSON.stringify([{}, { sort: { key: key(K.gate), dir: 'asc' } }, { find: '' }, { columns: { [key(K.gate)]: { min: null } } }, { find: 'x' }, { rows: 'missing' },
      { columns: { [key(K.grade)]: { out: ['A'] } } }].map((f) => TV.shownOf(sec, f).filtering)) === JSON.stringify([false, false, false, false, true, true, true]),
    'filtering');
};
// ── Split by (lead 10-11 W addendum 2 ⑭): a point - Long's read - splits the trend; a dot's title says it ──
const splitSuite = (R, TR, TVW) => {
  // Every way counted, by node (lead 10-13): 60 then 2 on is 120 ways - 50 kept, cut; read all, 60 and 120; the trend
  // reads as many as it is asked.
  {
    const gi = R.indexGraph(WIDE);
    const inside = new Set(gi.nodes.keys());
    const col = { steps: [{ predicate: 'measures', direction: 'outgoing' }], value: { on: 'edge', name: 'value' } };
    const two = { steps: [{ predicate: 'measures', direction: 'outgoing' }, { predicate: 'in_unit', direction: 'outgoing' }], value: { on: 'label', name: 'name' } };
    const cut = R.readsOf(gi, inside, 'w', col);
    const all = R.readsOf(gi, inside, 'w', col, Infinity);
    const far = R.readsOf(gi, inside, 'w', two);
    const pts = [TR.walkPoints(gi, [{ inside }], 'w', col).length, TR.walkPoints(gi, [{ inside }], 'w', col, Infinity).length];
    ok('RC1 every way counted: 60 - 50 read and cut; read all 60, not cut; two steps on 120 ways; the trend 50, then 60',
      JSON.stringify([cut.reads.length, cut.read, cut.total, cut.more, all.reads.length, all.more, far.total, far.read, pts])
        === JSON.stringify([50, 50, 60, true, 60, false, 120, 50, [50, 60]]),
      JSON.stringify([cut.reads.length, cut.read, cut.total, cut.more, all.reads.length, all.more, far.total, far.read, pts]));
  }
  const column = { steps: [{ predicate: 'inspected', direction: 'incoming' }], endTypes: ['wafer@1'], value: { on: 'edge', name: 'gate' } };
  const e = { qualifiers: { gate: 10, point: 'C', note: '', side: 'top' } };
  ok('SP1 a read\'s point: its edge\'s other attributes, the value and blanks out; a node\'s own value none',
    JSON.stringify([R.pointOf(column, e), R.pointWords(R.pointOf(column, e)), R.pointOf({ ...column, value: { on: 'node', name: 'gate' } }, e)])
      === JSON.stringify([[['point', 'C'], ['side', 'top']], 'point C · side top', []]),
    JSON.stringify(R.pointOf(column, e)));
  const view = TABLE_MOD.walkTableView(sfAnswer(8), SF_DECL.entities, SF_DECL.predicates, undefined, SF_STARTS);
  const sec = view.sections.find((x) => x.type === 'die@1');
  const gate = sec.trendable[0].column;
  const points = TR.rowsPoints(view, sec.rows.map((r) => r.id), gate);
  const long = TABLE_MOD.longLines(view, sec, { column: R.columnKey(gate) });
  const longPoint = (id) => (long.find((l) => l.id === id) || {}).point;
  // A point a mutant took away reads as none, not a throw.
  const pointAt = (id) => R.pointWords((points.find((p) => p.row === id) || {}).point || []);
  ok('SP2 a trend point carries the point Long says for the same read - one read (sd:1 «point C», sd:2 «point T»)',
    pointAt('sd:1') === longPoint('sd:1') && longPoint('sd:1') === 'point C' && pointAt('sd:2') === 'point T' && TR.splitNames(points).join() === 'point',
    JSON.stringify([points.map((p) => p.point), longPoint('sd:1')]));
  const model = TR.trendModel(points, undefined, { split: 'point' });
  const plain = TR.trendModel(points, undefined, {});
  ok('SP3 Split by point: a series a value - C · L · T - each point its series; no split, no series',
    JSON.stringify([model.series, model.numbers.map((p) => (model.series || [])[p.series]).join(''), plain.series])
      === JSON.stringify([['C', 'L', 'T'], points.filter((p) => p.t !== null).map((p) => ((p.point || [])[0] || [])[1]).join(''), null]),
    JSON.stringify([model.series, model.numbers.map((p) => p.series)]));
  // The part: Split by offered, a dot its series' colour and its point in its title.
  const doc = makeDoc();
  const mount = doc.createElement('div');
  const part = new TVW.TrendView(mount, { doc });
  let picked = null;
  part.show({ title: 't', model, groups: ['Positive'], t0: null, splits: ['point'], split: 'point', onSplit: (name) => { picked = name; } });
  const nodes = walkAll(mount);
  const select = nodes.find((n) => String(n.className).includes('wk-trendsplit'));
  const dots = nodes.filter((n) => n.attrs && n.attrs['data-key']);
  const titleOf = (d) => (d.children.find((c) => c.tagName === 'title') || {}).textContent;
  if (select) { select.value = 'point'; for (const fn of select.listeners.change || []) fn({}); }
  ok('SP4 the part: «Split by» offers the points\' names; a dot its series\' colour, its title its point; picking one tells the page',
    Boolean(select) && select.children.map((o) => o.textContent).join('|') === 'Split by|Split by · point'
      && dots.length === model.numbers.length && dots.every((d, i) => String(d.attrs.class).includes(`is-s${model.numbers[i].series + 1}`))
      && titleOf(dots[0]) === `point ${model.numbers[0].point[0][1]}` && picked === 'point',
    JSON.stringify([select && select.children.map((o) => o.textContent), dots.map((d) => [d.attrs.class, titleOf(d)]).slice(0, 2), picked]));
};
const TABLE_MOD = await import('../src/walk/table_view.js');
const REACH_MOD = await import('../src/walk/reach_table.js');
const TREND_MOD = await import('../src/walk/trend.js');
const TVIEW_MOD = await import('../src/walk/trend_view.js');
qualifierSuite(await import('../src/walk/table_view.js'));
sideSuite(await import('../src/walk/table_view.js'));
filterSuite(TABLE_MOD);
splitSuite(REACH_MOD, TREND_MOD, TVIEW_MOD);
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline with Q: ${ran} assertions`);
const base = { ran, names: NAMES.slice(), failed: failures.length };

// ═══ mutants ════════════════════════════════════════════════════════════════════════════
const NEXT_ASK = '    const asked = { ...knobs(), ...reachArg(), ...stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to }) };';
const MUTANTS = [
  { id: 'WFm1', what: 'Walk ▸ builds its own ask - the bar\'s collect, through and direction left behind', catches: 'W1',
    from: '    const asked = askFrom(seeds);\n    await walkStep(', to: '    const asked = { ...knobs(), ...seeds };\n    await walkStep(' },
  { id: 'WFm2', what: 'the graph\'s Continue asks its own walk again, not the bar\'s', catches: ['W1', 'W2'],
    from: '{ doc, walk, ask: askFrom, entities,', to: '{ doc, walk, entities,' },
  { id: 'WFm3', what: 'a node the baskets never held not sent - the form\'s subject walked instead', catches: 'W2',
    from: '...(signed || !one ? starts : {}) };', to: '...(signed ? starts : {}) };' },
  { id: 'WFm4', what: 'Walk ▸ on with nothing checked', catches: 'W3',
    from: "    setDisabledReason(full, all.positive.length ? '' : CHECK_ROWS_FIRST);", to: "    setDisabledReason(full, '');" },
  { id: 'AXm3', what: 'the auxiliary node is not sent', catches: 'AX3',
    from: '    return Object.assign(out, knobs(), reachArg());', to: '    return Object.assign(out, knobs());' },
  { id: 'AXm4', what: '«Reaches only» drawn but does nothing', catches: 'AX5',
    from: "      only.addEventListener('click', () => { setFilter(section.type, { reaches: !on }); render(); });", to: '' },
  { id: 'AXm8', what: 'a head of several lines drawn as one cut line again', catches: 'AX9',
    from: "      const th = el(doc, 'th', 'wk-centre', lines.length > 1 ? '' : h);\n      if (lines.length > 1) {", to: "      const th = el(doc, 'th', 'wk-centre', h);\n      if (false) {" },
  { id: 'AXm6', what: 'the judgments\' counts not drawn', catches: 'AX7',
    from: "      seat.append(el(doc, 'span', 'wk-reachtally', section.tally));", to: '' },
  { id: 'RSm1', what: 'the walk screen does not ask resumable - its cut walks come back with no key', catches: 'MR1',
    from: '  const walk = createWalkBoxWalk({ apiBase, fetchImpl, resumable: true });', to: '  const walk = createWalkBoxWalk({ apiBase, fetchImpl });' },
  { id: 'RGm1', what: 'the routes in one list, not grouped by steps', catches: 'RG1',
    from: "        g.setAttribute('label', unitText(k, 'step'));", to: "        g.setAttribute('label', 'Routes');" },
  { id: 'WCm4', what: 'Show all does nothing', catches: 'WC2',
    from: "      all.addEventListener('click', () => { state.allWays = true; render(); });", to: "      all.addEventListener('click', () => { render(); });" },
  { id: 'WCm5', what: 'a cut table says nothing (the code before)', catches: 'WC2',
    from: '    if (view.waysCut) {', to: '    if (false) {' },
  { id: 'EXm1', what: 'an expired page says Failed and offers nothing', catches: 'EX1 reloaded',
    from: '    adding = res && res.ok ? null : res && res.expired ? {', to: '    adding = res && res.ok ? null : false ? {' },
  { id: 'EXm2', what: 'Walk again sends the expired resume again', catches: 'EX2',
    from: "again: { ...asked, resume: undefined } }", to: "again: { ...asked } }" },
  { id: 'EXm3', what: 'Walk again drawn but does nothing', catches: 'EX2',
    from: "          again.addEventListener('click', () => { void walkAgain(at, ask); });\n", to: '' },
  { id: 'EXm5', what: 'Walk again lands as a More (the code before - 18766: the seed row «—», «+0 from More ×»)', catches: 'EX3',
    from: "          again.addEventListener('click', () => { void walkAgain(at, ask); });", to: "          again.addEventListener('click', () => walkMore({ asked: ask }));" },
  { id: 'MRm1', what: 'the next page replaces the step\'s answer, not merged into it', catches: 'MR2',
    from: '{ ...mergeWalks(res, was), ask: was.ask,', to: '{ ...res, ask: was.ask,' },
  { id: 'MRm2', what: 'More ▸ never off, all reached or not', catches: 'MR2',
    from: "        setDisabledReason(go, r.more.resume ? held : ALL_REACHED);", to: "        setDisabledReason(go, '');" },
  { id: 'MRm7', what: 'More ▸ live while its walk runs - a second press posts the same resume', catches: 'MR7',
    from: "        const held = adding && adding.at === state.at && adding.again ? adding.text : busy;", to: "        const held = adding && adding.at === state.at && adding.again ? adding.text : '';" },
  { id: 'EXm4', what: 'More ▸ stays live under the expired line - the dead resume sent again', catches: 'EX1 reloaded',
    from: "        const held = adding && adding.at === state.at && adding.again ? adding.text : busy;", to: "        const held = busy;" },
  { id: 'MRm8', what: 'More live while its walk runs - a second press walks again', catches: 'MR8',
    from: "          setDisabledReason(press, busy);\n", to: '' },
  { id: 'MRm5', what: 'a resume left does not say there is more to walk', catches: 'MR1',
    from: '          ...(r.more.resume ? [MORE_TO_WALK] : [])].join', to: '          ...[]].join' },
  { id: 'MRm3', what: 'the next page asked without its resume - the first page again, a GET', catches: 'MR1',
    from: '{ ...was.ask, resume: was.more.resume }', to: '{ ...was.ask }' },
  { id: 'RTm2', what: 'the Route panel the declaration\'s after a walk too, not the ways it walked', catches: 'RT2',
    from: "    const walked = shown.run === 'done' && shown.result ? walkedRoutes(shown.result, state.collect) : null;",
    to: '    const walked = null;' },
  { id: 'RTm3', what: 'before a walk every declared route listed again', catches: 'RT3',
    from: '    const found = walked || (first ? [first] : []);', to: '    const found = walked || routes();' },
  { id: 'MOm2', what: 'More asks the cut walk again with the limit that cut it', catches: 'MO2',
    from: '    void walkInto(at, more.asked, (res) => {', to: '    void walkInto(at, answerAt(at).asked, (res) => {' },
  { id: 'MOm3', what: 'More\'s answer lands nowhere - the step keeps the cut one', catches: 'MO2',
    from: '      setAnswer(at, res, more.asked);', to: '      setAnswer(at, result, asked);' },
  { id: 'IMm1', what: 'a value the answer says is an image drawn as its text', catches: 'IM1',
    from: '    const val = valueSpan(cell.image, cell.image !== undefined, cell.text);', to: '    const val = valueSpan(cell.image, false, cell.text);' },
  { id: 'DM7', what: 'a side\'s cells not tinted by who reached the row', catches: 'ZD4',
    from: "row.reached && row.reached[i] && row.reached[i] !== 'a' ?", to: 'false ?' },
  { id: 'DM8', what: 'the three counts not drawn over a section', catches: 'ZD4',
    from: '      if (section.reached) sec.append(reachedLine(section));\n', to: '' },
  { id: 'NZ16', what: 'the source line not drawn under a value', catches: 'Z41',
    from: "    if (from) { const src = el(doc, 'div', 'wk-src', from); src.title = from; c.append(src); }\n", to: '' },
  { id: 'NZ15', what: 'a node\'s route line without every route in its title', catches: 'Z32',
    from: "          src.title = same ? all(row.routes[0]) : row.routes.map((w) => `${w.sign} ${all(w)}`).join(' · ');\n", to: '' },
  { id: 'NZ1', what: 'no sign under a column', catches: 'Z9',
    from: '    thead.append(steps, ...(leafed ? [leaves] : []), ...(many && stepped ? [signs] : []));', to: '    thead.append(steps, ...(leafed ? [leaves] : []));' },
  { id: 'NZ2', what: 'Walk on gone from the result\'s foot', catches: 'Z9',
    from: '    if (checks) box.append(markedBasket(state.at, view, checks));\n', to: '' },
  { id: 'MBm1', what: 'the basket draws no chip', catches: 'MB1',
    from: '      picked.append(chip);\n    }\n    const checked', to: '    }\n    const checked' },
  { id: 'MBm2', what: 'a chip\'s × leaves its row checked', catches: 'MB2',
    from: "chip.addEventListener('click', () => { markings.set(checks, id, SIGN.ABSENT); render(); });", to: "chip.addEventListener('click', () => { render(); });" },
  { id: 'MBm3', what: 'Clear clears nothing', catches: 'MB3',
    from: "clear.addEventListener('click', () => { markings.clear(checks); render(); });", to: "clear.addEventListener('click', () => { render(); });" },
  { id: 'NZ3', what: 'the Compare view back', catches: 'Z10',
    from: "    for (const [name, word] of [['table', 'Table'], ['graph', 'Graph']]) {",
    to: "    for (const [name, word] of [['table', 'Table'], ['graph', 'Graph'], ['compare', 'Compare']]) {" },
  // ⚰️ NZ4 (the + side reversed) retired 10-11 with the mirrored sides (lead W).
  { id: 'NZ5', what: 'the node\'s cells not drawn', catches: 'Z13',
    from: '      row.centre.forEach((cell, i) => {', to: '      [].forEach((cell, i) => {' },
  { id: 'NZ11', what: 'no Δ cell between the two sides', catches: 'Z13',
    from: "          if (pair && i === 1 && cell.delta) tr.append(valueCell(cell.delta, 'wk-delta', false, () => {}));", to: '' },
  // ⚰️ NZ12 (the step said in every head) retired 10-11: a group is said once by its own run, its head NZ13's.
  // ⚰️ NZ14 (the axis scrolled past the box) retired 10-11 with Z28 and the mirrored sides (lead W).
  { id: 'NZ13', what: 'a group head without its step and far end', catches: 'Z27',
    from: "        s.title = one ? `${p.step} · ${p.leaf}` : p.step;", to: '        s.title = p.leaf;' },
  { id: 'NZ7', what: 'several values with no «+N» to open them', catches: 'Z24',
    from: "    if (cell.rest) {\n      const more = el(doc, 'button', 'wk-tag'", to: "    if (false) {\n      const more = el(doc, 'button', 'wk-tag'" },
  { id: 'NZ8', what: 'one colour for both signs', catches: 'Z25',
    from: "el(doc, 'th', `wk-sidehead ${signClass(g.sign)}`, g.sign)", to: "el(doc, 'th', 'wk-sidehead', g.sign)" },
  { id: 'NZ9', what: 'a group\'s «▸ N» opens nothing', catches: 'ZW1',
    from: "fold.addEventListener('click', () => { toggleGroup(section.type, p.group); render(); });", to: "fold.addEventListener('click', () => { render(); });" },
  { id: 'NZ10', what: 'Copy id in words again', catches: 'Z16',
    from: "copy.append(el(doc, 'span', 'wk-copyicon'));", to: "copy.append(el(doc, 'span', 'wk-copyicon', 'Copy id'));" },
  { id: 'CKm1', what: 'the node cell\'s icon copies the internal id again', catches: 'CK1 ',
    from: "line.append(copyKeyButton(row.id, (keys.length ? keys : [cell]).map(copyWords).join('\\t')));", to: 'line.append(copyKeyButton(row.id, row.id));' },
  { id: 'NZ6', what: 'the filter draws every row', catches: 'Z14',
    from: '    for (const { row } of shown.lines) {', to: '    for (const row of section.rows) {' },
  { id: 'CPm4', what: 'Wide copied as Long\'s lines', catches: 'CP3',
    from: ": copySheet(sheetOf(section, filterOf(section.type)), 'row');", to: ": copySheet(longSheet(section, longLines(view, section, {})), 'row');" },
  { id: 'CPm5', what: 'the copy ignores the filter', catches: 'CP3',
    from: "copySheet(sheetOf(section, filterOf(section.type)), 'row')", to: "copySheet(sheetOf(section), 'row')" },
  // Sort · filter · bulk select on the page (lead 10-11 W addendum 7).
  { id: 'SFm1', what: 'a head press sorts nothing', catches: 'PF1 ',
    from: "      setFilter(section.type, { sort: dir === 'asc'", to: "      setFilter(section.type, { kept: dir === 'asc'" },
  { id: 'SFm2', what: 'a column\'s «▾» opens no filter under the toolbar', catches: 'PF2 ',
    from: '      if (filters) sec.append(filters);\n', to: '' },
  { id: 'SFm3', what: 'the head says the total while a filter is set', catches: 'PF2 ',
    from: "shown.filtering ? sectionHeading(section.type, `${shown.lines.length} of ${of}`) : section.heading", to: 'section.heading' },
  { id: 'SFm6', what: 'the head check checks the hidden rows too', catches: 'PF6 ',
    from: '...rest, ...shown.ids.filter((id) => markings.signOf(checks, id) === SIGN.ABSENT)', to: '...rest, ...shown.all.map((l) => l.id).filter((id) => markings.signOf(checks, id) === SIGN.ABSENT)' },
  { id: 'SFm7', what: 'Long copied whatever the filter', catches: 'PF5 ',
    from: "copySheet(longSheet(section, shown.lines.map((line) => line.line)), 'line')", to: "copySheet(longSheet(section, longLines(view, section, {})), 'line')" },
  { id: 'FWm1', what: 'a table drawn with no fixed columns - auto widths again', catches: 'FW1 ',
    from: '      cols.append(col);\n', to: '' },
  { id: 'FWm3', what: 'every column a fixed 96 px again, whatever it holds', catches: 'FW1 ',
    from: "      col.setAttribute('style', `width: ${width}`);", to: "      col.setAttribute('style', 'width: 96px');" },
  { id: 'FWm6', what: 'a far-end name\'s share asked of Δ again', catches: 'FW3 ',
    from: '[fit(section.rows.map((row) => said(row.cells[i].delta)), 0), side]', to: '[fit(section.rows.map((row) => said(row.cells[i].delta)), shares), side]' },
  { id: 'NWm1', what: 'the node column at the value columns\' far end again - ~185 px whatever its keys', catches: 'NW1 ',
    from: '    const whole = (i) => i === 0 ||', to: '    const whole = (i) => false ||' },
  { id: 'AXm10', what: 'the judgment\'s column cut at the value columns\' far end, which auxiliary node unsaid', catches: 'AX10',
    from: ' || (section.judged && i === section.centreHeads.length - 1);', to: ';' },
  { id: 'FWm4', what: 'Δ the width of its value\'s + and − again, whatever it holds', catches: 'FW2 ',
    from: '[fit(section.rows.map((row) => said(row.cells[i].delta)), 0), side]', to: '[side, side]' },
  { id: 'SFm8', what: 'a section\'s Trend reads every row, the hidden too', catches: 'PF8 ',
    from: "    const rows = t.at === 'section' ? ids : t.rows;", to: "    const rows = t.at === 'section' ? at.section.rows.map((x) => x.id) : t.rows;" },
  { id: 'SFm9', what: 'Walk on from the checked rows the filter hides', catches: 'PF8 ',
    from: '    const seeds = seedsOf(shown.ids.map((id) => [id, markings.signOf(checks, id)]));', to: '    const seeds = seedsOf(section.rows.map((row) => [row.id, markings.signOf(checks, row.id)]));' },
  { id: 'SFm10', what: 'the search box not one of the filter', catches: 'PF5 ',
    from: "typed(find, `find\\u0000${section.type}`, (value) => setFilter(section.type, { find: value }));", to: '' },
  { id: 'SFm12', what: 'a value picked out stays in', catches: 'PF4 ',
    from: '          if (out.has(value)) out.delete(value); else out.add(value);\n', to: '' },
  { id: 'CPm6', what: 'a copy that failed said as done', catches: 'CP4',
    from: ': COPY_WORDS.failed;', to: ': COPY_WORDS.done(sheet.rows.length, unit);' },
  // 🔴 THE ONE THE RULING ASKED FOR: a copy put back. Same sections, same rows, same counts.
  { id: 'M1', what: 'a group head without its value\'s name', catches: 'V2 the heads',
    from: "one ? `${p.step} · ${p.leaf}` : p.step", to: 'p.step' },
  // 🔴 THIS SLOT HELD AN EQUIVALENT MUTANT, AND THE HARNESS SAID SO. It was `cell.text || ''`,
  //    meant to collapse 0 into a blank -- but `cell.text` is already a STRING and '0' is
  //    truthy, so it changed nothing and ESCAPED. The rule it aimed at (0 is a value, absent is
  //    a blank) moved into `table_view.valueText` with the half being scored, and the renderer
  //    no longer HAS a raw value to collapse. Re-anchored rather than chased with a weaker
  //    assertion: the cells drawn in the wrong order. Same count, nothing thrown.
  { id: 'M2', what: 'the node\'s cells drawn in the wrong order', catches: 'V3 every cell is the view',
    from: '      row.centre.forEach((cell, i) => {', to: '      [...row.centre].reverse().forEach((cell, i) => {' },
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
    from: '      if (section.hidden) sec.append(el(doc, \'div\', \'wk-note\', `${section.hidden} more not drawn`));',
    to: '      if (section.hidden) sec.append(el(doc, \'div\', \'wk-note\', `${section.rows.length + section.hidden} more not drawn`));' },
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
    from: '    return { ...spec(), ...(one ? { type: one.type, keys: { ...one.keys } } : {}), ...(signed || !one ? starts : {}) };', to: '    return spec();' },
  { id: 'SM3', what: 'a check takes no sign from Shift', catches: 'S3',
    from: "markings.toggle(checks, id, markingIntent(event).sign); render(); });", to: "markings.toggle(checks, id, SIGN.CASE); render(); });" },
  { id: 'SM4', what: 'Next drops the - rows', catches: 'S4',
    from: 'stepAlong({ positive: seeds.positive, negative: seeds.negative,', to: 'stepAlong({ positive: seeds.positive,' },
  { id: 'NM1', what: 'the Next walks from every row of the section, not the checked ones', catches: 'N2',
    from: '      const seeds = seedsOf(shown.ids.map((id) => [id, markings.signOf(checks, id)]));',
    to: '      const seeds = { positive: shown.ids, negative: [] };' },
  { id: 'NM2', what: 'a press with nothing checked still asks', catches: 'N2',
    from: "      go.addEventListener('click', () => { if (seeds.positive.length) void walkOn(at, seeds, route); });",
    to: "      go.addEventListener('click', () => { void walkOn(at, seeds, route); });" },
  { id: 'NM3', what: 'the next step builds its own walk instead of the one step', catches: 'N4',
    from: '    const asked = { ...knobs(), ...reachArg(), ...stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to }) };',
    to: '    const asked = { positive: seeds.positive, follow: [route.predicate] };' },
  // stepAlong's own default ('both') is imported by main.js and not swapped by this loader; the call site stands in.
  { id: 'NM7', what: 'the Next walks one way only', catches: 'N8',
    from: '    const asked = { ...knobs(), ...reachArg(), ...stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to }) };',
    to: "    const asked = { ...knobs(), ...reachArg(), ...stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to, direction: 'outgoing' }) };" },
  { id: 'EKm1', what: 'a Next without the form\'s knobs - a cut answer cut elsewhere', catches: 'EA1',
    from: '    const asked = { ...knobs(), ...reachArg(), ...stepAlong(', to: '    const asked = { ...reachArg(), ...stepAlong(' },
  { id: 'EKm2', what: 'a Next walks the form\'s hops, not one step', catches: 'EA1',
    from: NEXT_ASK, to: NEXT_ASK.replace('{ ...knobs(), ...reachArg(), ...stepAlong(', '{ ...reachArg(), ...stepAlong(').replace('farType: route.to }) };', 'farType: route.to }), ...knobs() };') },
  { id: 'NM4', what: 'the checks are kept apart from the graph\'s marking', catches: 'N3',
    from: "  const checksOf = (at) => (at === 0 ? state.marks : stepOf(at).marks);", to: '  const checksOf = (at) => `table-${at}`;' },
  { id: 'FM1', what: 'a step\'s marking named by its place again', catches: 'CH2',
    from: "reason: '', marks: nextMarks() };", to: "reason: '', marks: `walk-${at + 3}` };" },
  { id: 'FM2', what: 'a step walked again leaves the dropped steps\' markings', catches: 'CH2',
    from: '    dropMarks(dropped);\n', to: '' },
  { id: 'GM5', what: 'the graph walks a branch\'s step again, not the table\'s answer', catches: 'GB4',
    from: ' i += 1) await graph.continueWalk(given(i));', to: ' i += 1) await graph.continueWalk();' },
  { id: 'GM6', what: 'the graph walks the start again, not the form walk\'s answer', catches: 'GB4',
    from: '    await graph.show({ keep: true, given: given(0) });', to: '    await graph.show({ keep: true });' },
  { id: 'GM7', what: 'a step before the last drawn whole', catches: 'GB5',
    from: 'answer: i < path.length ? pathsAnswer(answers[i], [...starts[i + 1].positive, ...starts[i + 1].negative]) : answers[i] };',
    to: 'answer: answers[i] };' },
  { id: 'GM8', what: 'a lump\'s step the branch\'s end\'s child', catches: 'GB6',
    from: '    const parent = lump.step === 0 ? 0 : (pathTo(state.leaf)[lump.step - 1] || { id: state.leaf }).id;', to: '    const parent = state.leaf;' },
  { id: 'GM9', what: 'a lump\'s step one step off on the branch', catches: 'GB6',
    from: '(pathTo(state.leaf)[lump.step - 1] || { id: state.leaf })', to: '(pathTo(state.leaf)[lump.step] || { id: state.leaf })' },
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
  { id: 'TSm1', what: 'a continued page\'s top set replaces the one before', catches: 'TS1',
    from: '  const topSet = Array.isArray(left) ? { top_set: [...new Set([...top(b).filter((id) => !left.includes(id)), ...top(a)])] } : {};', to: '  const topSet = {};' },
  { id: 'TSm2', what: 'the ids that left the top stay in it', catches: 'TS1',
    from: '...top(b).filter((id) => !left.includes(id))', to: '...top(b)' },
  { id: 'MRm4', what: 'the pages merged without their ranked rows - a later page\'s row drawn in no sign', catches: 'MR3',
    from: 'ranked: once([...ranked(b), ...ranked(a)])', to: 'ranked: ranked(a)' },
  { id: 'MRm6', what: 'a node ranked on two pages keeps the earlier row - the reach a later page grew lost', catches: 'MR4',
    from: 'ranked: once([...ranked(b), ...ranked(a)])', to: 'ranked: once([...ranked(a), ...ranked(b)])' },
  { id: 'RTm1', what: 'the walked routes in no order - the commonest not first', catches: 'RT1',
    from: '    .sort((a, b) => b.count - a.count || a.hops - b.hops);', to: '    ;' },
  { id: 'AXm1', what: 'the judgment drawn nowhere', catches: 'AX01',
    from: "          ...(reaches ? [{ text: reachWords(judgedOf(node.id), reachTo.length > 1) }] : [])] };", to: "          ] };" },
  { id: 'AXm7', what: 'the counts taken over the reaching rows alone, as a filtered table would give them', catches: 'AX01',
    from: "      tally: reaches ? reachTally(reachHead, said) : '',", to: "      tally: reaches ? reachTally(reachHead, said.filter((row) => row.reach && row.reach.state === 'found')) : ''," },
  { id: 'AXm2', what: '«Reaches only» shows every row', catches: 'AX2',
    from: "    && (!f.reaches || Boolean(line.row.reach && line.row.reach.state === 'found')));", to: '    );' },
  { id: 'CPm1', what: 'several values copied as the first alone', catches: 'CP1',
    from: "cell.values ? cell.values.join('; ')", to: 'cell.values ? cell.values[0]' },
  { id: 'CPm2', what: 'Δ copied in its words, not its number', catches: 'CP1',
    from: 'String(cell.delta.value)', to: 'cell.delta.text' },
  { id: 'CPm3', what: 'every row shown whatever the filter', catches: 'CP2',
    from: "filter === 'all' || (filter === 'differs' ? line.row.differs : line.row.missing)", to: 'true' },
  { id: 'DM1', what: 'reached by both said A only', catches: 'ZD1',
    from: "const reachedBy = (inA, inB) => (inA && inB ? 'ab' : inB ? 'b' : 'a');", to: "const reachedBy = (inA, inB) => (inA ? 'a' : inB ? 'b' : 'ab');" },
  { id: 'DM2', what: 'B\'s nodes not merged into the rows', catches: 'ZD1',
    from: '  const walked = control ? mergeWalks(result, control) : result;', to: '  const walked = result;' },
  { id: 'WCm1', what: 'a cut cell says «+49+» again (the code before)', catches: 'WC1',
    from: "rest: cell.more ? `${count(cell.read)} of ${count(cell.total)}` : `+${values.length - 1}`", to: "rest: `+${values.length - 1}${cell.more ? '+' : ''}`" },
  { id: 'WCm2', what: 'Show all leaves the table at 50 ways', catches: 'WC1',
    from: '    const tableAll = tableOf(index, groups, ids, sideAll, ways);', to: '    const tableAll = tableOf(index, groups, ids, sideAll);' },
  { id: 'WCm3', what: 'Show all leaves Long at 50 ways', catches: 'WC1',
    from: 'readsOf(view.index, inside, row.id, column, view.ways)', to: 'readsOf(view.index, inside, row.id, column)' },
  { id: 'CAPm1', what: 'one cap over every section: the first 200 of the answer, a later type dropped', catches: 'CAP1',
    from: '  for (const [type, typed] of sectionsByType(members)) {', to: '  for (const [type, typed] of sectionsByType(members.slice(0, cap))) {' },
  { id: 'AHM1', what: 'an Add here or More answer overwrites the step instead of merging', catches: 'AH1',
    from: '  const merged = adds.reduce((graph, add) => mergeWalks(graph, add.answer), walked);', to: '  const merged = adds.reduce((graph, add) => add.answer, walked);' },
  { id: 'DM3', what: 'a side coloured by the + side\'s B', catches: 'ZD3',
    from: 'reachedBy(g.a.has(node.id), g.b.has(node.id))', to: 'reachedBy(g.a.has(node.id), groups[0].b.has(node.id))' },
  { id: 'DM4', what: 'the node\'s way says only A\'s - a B-only row «—» (the W 1 regression)', catches: 'ZD3',
    from: "[[g.a, 'A', own], [g.b, 'B', sourcesB]]", to: "[[g.a, 'A', own]]" },
  { id: 'DM5', what: 'a value only B brought says A\'s source', catches: 'ZD3',
    from: 'byB(g, id) && !g.a.has(id) ?', to: 'false ?' },
  { id: 'DM6', what: 'no B, rows said reached anyway', catches: 'ZD2',
    from: 'a: g.inside, b: groupsB[i].inside })) : groupsA;', to: 'a: g.inside, b: groupsB[i].inside })) : groupsA.map((g) => ({ ...g, a: g.inside, b: new Set() }));' },
  { id: 'ZM1', what: 'the rows only those the first group reached', catches: 'Z02',
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
    from: '    const deltaAt = new Set(sideAt.flatMap((c, k) => (hasDelta(c) ? [k] : [])));', to: '    const deltaAt = new Set();' },
  { id: 'ZM4b', what: 'a column no row has a Δ for draws its «—» Δ again', catches: 'DX1 ',
    from: '    const deltaAt = new Set(sideAt.flatMap((c, k) => (hasDelta(c) ? [k] : [])));',
    to: '    const deltaAt = new Set(groups.length === 2 ? sideAt.map((_, k) => k) : []);' },
  { id: 'ZM5', what: 'reached but no value drawn missing', catches: 'Z04',
    from: '  if (!values.length) return { text: EMPTY };', to: '  if (!values.length) return { text: MISSING, missing: true };' },
  { id: 'ZM6', what: 'several values: the first alone', catches: 'Z6',
    from: '  if (values.length === 1 && !cell.more)', to: '  if (values.length >= 1 && !cell.more)' },
  { id: 'ZM7', what: 'a node\'s route not read', catches: 'Z8',
    from: '        routes: groups.filter((g) => g.inside.has(node.id)).map((g) => ({ sign: g.name, ...routeCell(g, node.id) })),', to: '        routes: [],' },
  // RM6 («Δ <head>» read from heads) retired with Route moved to the outer end: heads[c] is columnHeads[c] again, the
  // mutant changes nothing (Z37 stays, guarding the order).
  { id: 'VS1', what: 'a value\'s source the row\'s node, not the read\'s', catches: 'Z38',
    from: "sources: (row.cells[c][i].nodes || []).map((id) => (id === node.id ? '' : sources.source(g, id)))", to: 'sources: (row.cells[c][i].nodes || []).map(() => sources.source(g, node.id))' },
  { id: 'VS2', what: 'a value\'s source without its route', catches: 'Z40',
    from: 'source: (g, id) => `${keyWords(id)} · ${g ? route(g, id).text : NOT_WALKED}`', to: 'source: (g, id) => `${keyWords(id)}`' },
  { id: 'VS3', what: 'a source from the other side\'s paths', catches: 'Z38',
    from: "sources: (row.cells[c][i].nodes || []).map((id) => (id === node.id ? '' : sources.source(g, id)))",
    to: "sources: (row.cells[c][i].nodes || []).map((id) => (id === node.id ? '' : sources.source(groups[(i + 1) % groups.length], id)))" },
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
  { id: 'RM5', what: 'a node\'s route from the other side\'s paths', catches: 'Z29',
    from: '.map((g) => ({ sign: g.name, ...routeCell(g, node.id) }))', to: '.map((g, k, all) => ({ sign: g.name, ...routeCell(all[(k + 1) % all.length], node.id) }))' },
  { id: 'ZM8', what: 'an added column dropped', catches: 'Z18',
    from: ', ...(added.get(type) || [])];', to: '];' },
  { id: 'ZM9', what: 'a difference keeps its float tail', catches: 'Z19',
    from: '  const n = Number(delta.toPrecision(10));', to: '  const n = delta;' },
  { id: 'ZM10', what: 'a side that did not reach: missing once, its other cells «—»', catches: 'Z21',
    from: '          : { text: MISSING, missing: true, col: c })),', to: '          : (c === 0 ? { text: MISSING, missing: true, col: c } : { text: EMPTY, col: c }))),' },
  { id: 'ZM11', what: 'an opened group in its found order, numbers anywhere', catches: 'Z22',
    from: 'shown: opened ? [...first, ...b.at.filter((i) => !first.includes(i))] : first,', to: 'shown: opened ? b.at : first,' },
  { id: 'ZM13', what: 'a group opens on its first cell, not its numbers', catches: 'Z22',
    from: 'const first = numbers.length ? numbers : b.at.slice(0, 1);', to: 'const first = b.at.slice(0, 1);' },
  { id: 'ZM14', what: 'every far node its own group', catches: 'Z40',
    from: '(t) => statics.has(t)', to: '() => true' },
  { id: 'ZM15', what: 'no far node its own group, a static type\'s too', catches: 'Z44',
    from: '(t) => statics.has(t)', to: '() => false' },
  { id: 'ZM16', what: 'the groups in their found order, a compared one anywhere', catches: 'Z45',
    from: '    const sideAt = [...folds.filter((b) => b.on && compared(b)), ...folds.filter((b) => b.on && !compared(b))].flatMap((b) => b.shown);',
    to: '    const sideAt = folds.filter((b) => b.on).flatMap((b) => b.shown);' },
  // The one «what does this table show» seat (lead 10-11 W addendum 7).
  { id: 'SFt1', what: 'numbers sorted as words', catches: 'SF2 ',
    from: '  if (a.number !== null && b.number !== null) return a.number - b.number;', to: '  if (a.number !== null && b.number !== null) return String(a.number).localeCompare(String(b.number));' },
  { id: 'SFt2', what: 'blanks first when descending', catches: 'SF3 ',
    from: '? Number(a.blank) - Number(b.blank) :', to: '? sign * (Number(a.blank) - Number(b.blank)) :' },
  { id: 'SFt3', what: 'descending the same as ascending', catches: 'SF1 ',
    from: "    const sign = f.sort.dir === 'desc' ? -1 : 1;", to: '    const sign = 1;' },
  { id: 'SFt4', what: 'contains as the whole words, its case kept', catches: 'SF6 ',
    from: '(!cell.blank && lower(cell.words).includes(lower(f.contains)))', to: '(cell.words === f.contains)' },
  { id: 'SFt5', what: 'a range without its top', catches: 'SF7 ',
    from: '  && (!isSet(f.max) || (cell.number !== null && cell.number <= f.max))\n', to: '\n' },
  { id: 'SFt6', what: 'values picked out kept', catches: 'SF8 ',
    from: '  && (!f.out || !f.out.includes(cell.words));', to: ';' },
  { id: 'SFt7', what: 'the search box case-sensitive, the node\'s keys not read', catches: 'SF9 ',
    from: "  const found = (line) => !find || [...line.cells.map((c) => c.words), ...line.row.centre.map((c) => c.text)]\n    .some((w) => lower(w).includes(find));",
    to: "  const found = (line) => !find || line.cells.map((c) => c.words).some((w) => w.includes((f.find || '').trim()));" },
  { id: 'SFt8', what: 'a column of numbers offered as a pick', catches: 'SF7 ',
    from: "  if (said.length && said.every((c) => c.number !== null)) return { kind: 'range', choices: [] };\n", to: '' },
  { id: 'SFt9', what: 'every column a pick, however many values', catches: 'SF6 ',
    from: 'choices.filter(Boolean).length <= PICK_MOST ?', to: 'true ?' },
  { id: 'SFt10', what: 'a sort said as a filter', catches: 'SF10 ',
    from: "filtering: filter !== 'all' || Boolean(find) || tests.length > 0 || Boolean(f.reaches) }", to: "filtering: filter !== 'all' || Boolean(find) || tests.length > 0 || Boolean(f.reaches) || Boolean(f.sort) }" },
  { id: 'SFt11', what: 'Wide\'s Δ not a column of its own', catches: 'SF4 ',
    from: "section.parts[i].delta ? { key: `${columnKey(column)}\\u0000${DELTA}`", to: "false ? { key: `${columnKey(column)}\\u0000${DELTA}`" },
  { id: 'LSm1', what: 'a Long record\'s side by its node, not by its way', catches: 'LS1 ',
    from: 'const at = l.group !== null ? [l.group] : view.groups', to: 'const at = view.groups' },
  { id: 'LSm2', what: 'Long merges records by their edge again - an edge\'s second record dropped', catches: 'LS2 ',
    from: '            record: r.record });', to: '            record: r.edge || r.node });' },
  { id: 'ZM12', what: 'an empty column drawn', catches: 'Z23',
    from: "      if (kindsAll[i] === 'empty') return;", to: '' },
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
  filterSuite(loaded.module);
  return { ran, names: NAMES.slice(), failures: failures.slice() };
}, { baselineNames: base.names, title: `${LF}== table_view mutants (each must be CAUGHT by the check it names) ==` });

// Split by and the point it reads (lead 10-11 W addendum 2 ⑭): reach_table · trend · trend_view, each mutated alone.
const SPLIT_MUTANTS = [
  { id: 'RCm1', what: 'only the ways kept are counted - a cut cell says 50 of 50', catches: 'RC1', file: 'reach_table.js',
    from: '  const total = [...counts.values()].reduce((a, b) => a + b, 0);', to: '  const total = ends.length;' },
  { id: 'RCm2', what: 'the trend reads 50 whatever it is asked', catches: 'RC1', file: 'trend.js',
    from: 'readsOf(index, g.inside, x, column, ways)', to: 'readsOf(index, g.inside, x, column)' },
  { id: 'SPm1', what: 'a point keeps the value itself', catches: 'SP1 ', file: 'reach_table.js',
    from: '.filter(([name, v]) => name !== column.value.name && !isBlank(v))', to: '.filter(([, v]) => !isBlank(v))' },
  { id: 'SPm2', what: 'a walked point carries no point', catches: 'SP2 ', file: 'trend.js',
    from: "claim: (r.when && r.when.claim_id) || '', point: pointOf(column, r.edge) })));", to: "claim: (r.when && r.when.claim_id) || '' })));" },
  { id: 'SPm3', what: 'Split by makes no series', catches: 'SP3 ', file: 'trend.js',
    from: '  const series = frame.split ?', to: '  const series = false ?' },
  { id: 'SPm4', what: 'a split dot in its group\'s colour', catches: 'SP4 ', file: 'trend_view.js',
    from: "    const kind = split ? (p.series === null ? 'is-other' : `is-s${p.series + 1}`)", to: "    const kind = false ? (p.series === null ? 'is-other' : `is-s${p.series + 1}`)" },
  { id: 'SPm5', what: 'a dot\'s title without its point', catches: 'SP4 ', file: 'trend_view.js',
    from: "    const words = [p.source, pointWords(p.point || [])].filter(Boolean).join(' · ');", to: "    const words = p.source;" },
  { id: 'SPm6', what: 'no «Split by» offered', catches: 'SP4 ', file: 'trend_view.js',
    from: '    if (spec.splits && spec.splits.length && spec.onSplit) {', to: '    if (false) {' },
];
const sp = await scoreMutants(SPLIT_MUTANTS, async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  const loaded = await loadWithProbe(path.join(HERE, '..', 'src', 'walk', m.file), {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  const mine = (file, own) => (m.file === file ? loaded.module : own);
  splitSuite(mine('reach_table.js', REACH_MOD), mine('trend.js', TREND_MOD), mine('trend_view.js', TVIEW_MOD));
  return { ran, names: NAMES.slice(), failures: failures.slice() };
}, { baselineNames: base.names, title: `${LF}== split mutants (each must be CAUGHT by the check it names) ==` });

// The stylesheet FW1 reads (owner 10-12: fixed widths), mutated alone; the page as it is.
const STYLE_MUTANTS = [
  { id: 'AXm9', what: 'the counts back in the small grey words', catches: 'AX8',
    from: '.wk-reachtally { color: var(--text); font-size: var(--wk-fs-body);', to: '.wk-reachtally { color: var(--text-dim); font-size: var(--wk-fs-line);' },
  { id: 'AXm5', what: '«Reaches only» on drawn as an outline, as before', catches: 'AX6 ',
    from: '.wk-reachonly.is-on { background: var(--accent); color: var(--accent-contrast); border-color: var(--accent); font-weight: 600; }', to: '' },
  { id: 'FWm2', what: 'the tables back to auto layout', catches: 'FW1 ',
    from: '.wk-table { table-layout: fixed; width: 0;', to: '.wk-table { width: 100%; display: block; overflow-x: auto;' },
  { id: 'WSm1', what: 'a value\'s spaces collapsed again', catches: 'WS1 ',
    from: '.wk-valline > .wk-val, .wk-valline > .wk-centrelabel, .wk-long td { white-space: pre; }', to: '' },
];
const st = await scoreMutants(STYLE_MUTANTS, async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  const loaded = await loadWithProbe(path.join(HERE, '..', 'src', 'walk', 'styles.js'), {
    mutate: (text) => {
      if (!text.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.id}`);
      return text.split(m.from).join(m.to);
    },
  });
  CSS_NOW = loaded.module.WALK_CSS;
  await suite(first.module);
  CSS_NOW = WALK_CSS;
  return { ran, names: NAMES.slice(), failures: failures.slice() };
}, { baselineRan: suiteRan, baselineNames: base.names, title: `${LF}== style mutants (each must be CAUGHT by the check it names) ==` });

const all = MUTANTS.length + TV_MUTANTS.length + SPLIT_MUTANTS.length + STYLE_MUTANTS.length;
const scored = all - defects.wrong - controls.wrong - tv.wrong - sp.wrong - st.wrong;
console.log(`${LF}  ${scored}/${all} scored as intended.`);
const failed = base.failed + (all - scored);
console.log(`ASSERTIONS ${base.ran + all} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
