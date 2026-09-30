/**
 * Ledger form: where an edit sits (lead 619befe8c). The form is the real `renderSkeletonForm`, fed the
 * server's skeleton (fixtures/authoring_skeleton.json, captured by the script beside it) and the
 * sample's own `die_inspection`, every branch open.
 *
 *   G  a row — and a one-of's own row — at depth N carries N guides
 *   T  a node's trail is the declaration path's own words — section, id, each step — root first;
 *      every step lands on the deepest drawn node at or above it (owner's choice, via the lead)
 *   P  the path bar: steps in order, the last is where the hand is, a step asks to go to its path,
 *      seated in a new mount it draws the same trail, two bars do not cross
 *   W  the path bar's code names none of the skeleton's words (the population is printed: the canary)
 *
 * The controller's wiring (focus -> bar, the tinted parent, the sticky seat) is looked at in the
 * browser, not here: this stub has no layout.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc, walk } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { declarationShape } from '../src/ontology_skeleton.js';
import { splitBundlePath } from '../src/ontology_path.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VIEW = path.join(HERE, '..', 'src', 'ontology_explorer_view.js');
const BAR = path.join(HERE, '..', 'src', 'path_bar.js');
const CAPTURE = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'authoring_skeleton.json'), 'utf8'));
const SAMPLE = JSON.parse(readFileSync(
  path.join(HERE, '..', '..', 'server', 'config', 'sample', 'ledger_config.json.sample'), 'utf8'));
const RAW = SAMPLE.sources.die_inspection;
const SECTION = (CAPTURE.authorable_kinds.find((k) => k.id === 'source_plan') || {}).section;

const doc = makeDoc('light');
globalThis.document = doc;

let ran = 0;
let failedList = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failedList.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);
const cls = (n, c) => ` ${n.className || ''} `.includes(` ${c} `);

const ALL_OPEN = new Proxy({}, { get: () => true });
const contextFor = (skeleton) => ({
  schema: {}, readOnly: true, planRow: () => null, plannedMembers: () => [], covering: () => null,
  deref: (item) => (item && item.use ? (skeleton.defs || {})[item.use] : item), declared: () => [],
  rolesNear: () => [], usedElsewhere: () => [], renderRow: () => null, suggest: (row) => row,
  hot: [], expanded: ALL_OPEN, absolute: (at) => at,
});
const depthOf = (el) => Number(el.style.getPropertyValue('--oe-depth') || 0);
const guidesIn = (el) => walk(el).filter((n) => cls(n, 'oe-node-guide')).length;

function suite(view, bar) {
  console.log('\n-- G. guides: one per ancestor --');
  const form = view.renderSkeletonForm(contextFor(CAPTURE.skeleton),
    declarationShape(CAPTURE.skeleton, SECTION), '', RAW, 0, 'die_inspection');
  const rows = walk(form).filter((n) => cls(n, 'oe-node-row'));
  const deepest = Math.max(...rows.map(depthOf));
  ok('G1 the real form is drawn deep (else the rest proves nothing)', rows.length > 50 && deepest >= 5,
    `${rows.length} rows, deepest ${deepest}`);
  const off = rows.filter((r) => guidesIn(r) !== depthOf(r));
  eq('G2 every row at depth N carries N guides', off.length, 0);
  const ONE_OF = { defs: {}, root: { kind: 'record', fields: [{ key: 'outer', node: { kind: 'record', fields: [
    { key: 'pick', node: { kind: 'oneOf', branches: {
      alpha: { kind: 'record', fields: [{ key: 'x', node: { kind: 'leaf' } }] },
      beta: { kind: 'record', fields: [] } } } }] } }] } };
  const small = view.renderSkeletonForm(contextFor(ONE_OF), ONE_OF.root, '', { outer: { pick: { alpha: { x: '1' } } } }, 0, 'root');
  const head = walk(small).find((n) => cls(n, 'oe-node-head'));
  eq('G3 a one-of\'s own row keeps the stair and its guides', head ? `${depthOf(head)}|${guidesIn(head)}` : '(none)', '2|2');

  console.log('\n-- T. the trail is the declaration path\'s own words --');
  const HEAD = [SECTION, 'die_inspection'];
  const target = walk(form).find((n) => cls(n, 'oe-node') && /subject\.entity_type$/.test(n.dataset.path || ''));
  const trail = target ? view.nodeTrail(target, HEAD) : [];
  const ancestors = [];
  for (let n = target; n; n = n.parentNode) if (n.nodeType === 1 && cls(n, 'oe-node') && n.dataset.path !== undefined) ancestors.unshift(n);
  const spelled = target ? [...HEAD, ...splitBundlePath(target.dataset.path).map(String)] : [];
  eq('T1 root first, the node last', trail.length ? `${trail[0].path}|${trail[trail.length - 1].path}` : '(none)',
    `|${target && target.dataset.path}`);
  eq('T2 the words are the section, the id, then each step of the path', trail.map((s) => s.label).join(' > '),
    spelled.join(' > '));
  eq('T3 one word per step, the head included', trail.length, spelled.length);
  eq('T4 the ends read as the declaration spells them', trail.length ? `${trail[0].label}|${trail[trail.length - 1].label}` : '',
    `${SECTION}|entity_type`);
  const paths = new Set(ancestors.map((n) => n.dataset.path));
  ok('T5 every step lands on a drawn node on the way, never deeper than itself',
    trail.length > 0 && trail.every((step, i) => paths.has(step.path)
      && splitBundlePath(step.path).length <= Math.max(0, i - HEAD.length + 1)),
    JSON.stringify(trail.map((s) => s.path)));
  const leafX = walk(small).find((n) => cls(n, 'oe-node') && /\.x$/.test(n.dataset.path || ''));
  const xTrail = leafX ? view.nodeTrail(leafX, ['s', 'root']) : [];
  const branch = xTrail.find((st) => st.label === 'alpha');
  eq('T6 a one-of\'s branch word has no row, and goes to the one-of', branch ? branch.path : '(none)', 'outer.pick');

  console.log('\n-- P. the path bar --');
  const TRAIL = [{ path: '', label: 'root' }, { path: 'a', label: 'A' }, { path: 'a.b', label: 'B' }];
  const picks = [];
  const mount = doc.createElement('div');
  const one = new bar.PathBar(mount, { doc, onPick: (p) => picks.push(p) });
  one.show(TRAIL);
  const steps = (m) => walk(m).filter((n) => cls(n, 'oe-path-step'));
  eq('P1 the steps in order, a separator between each', `${steps(mount).map((s) => s.textContent).join('|')}|${walk(mount).filter((n) => cls(n, 'oe-path-sep')).length}`, 'root|A|B|2');
  eq('P2 only the last is where the hand is', steps(mount).map((s) => s.getAttribute('aria-current') || '-').join(','), '-,-,true');
  steps(mount)[1].dispatch('click');
  steps(mount)[2].dispatch('click');
  eq('P3 a step asks to go to its own path; the last asks nothing', picks.join(','), 'a');
  const again = doc.createElement('div');
  one.attach(again);
  eq('P4 seated in a new mount, it draws the same trail', steps(again).map((s) => s.textContent).join('|'), 'root|A|B');
  const mount2 = doc.createElement('div');
  const two = new bar.PathBar(mount2, { doc, onPick: () => {} });
  two.show([{ path: 'z', label: 'Z' }]);
  eq('P5 two bars do not cross', `${steps(again).map((s) => s.textContent).join('|')}/${steps(mount2).map((s) => s.textContent).join('|')}`, 'root|A|B/Z');
  eq('P6 a shrunk step keeps its whole word one hover away', steps(again).map((s) => s.getAttribute('title')).join('|'), 'root|A|B');

  console.log('\n-- W. the bar names no declaration word --');
  const words = new Set();
  const collect = (n) => {
    if (Array.isArray(n)) n.forEach(collect);
    else if (n && typeof n === 'object') for (const [k, v] of Object.entries(n)) {
      if ((k === 'key' || k === 'label') && typeof v === 'string') words.add(v);
      collect(v);
    }
  };
  collect(CAPTURE.skeleton);
  const JS = new Set(['class', 'object', 'function', 'return', 'const', 'let', 'new', 'this', 'if', 'else', 'for', 'import', 'export', 'default', 'true', 'false', 'null', 'type']);
  const code = bar.__source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  const population = [...words].filter((w) => !JS.has(w));
  const shown = population.filter((w) => walk(form).some((n) => n.textContent === w)).length;
  ok('W1 the population is the skeleton\'s, and the form draws its words (the canary)', population.length > 20 && shown > 5,
    `${population.length} words, ${shown} drawn`);
  const named = population.filter((w) => new RegExp(`(?<![A-Za-z0-9_])${w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_])`).test(code));
  eq('W2 the path bar\'s code names none of them', named.join(',') || 0, 0);
  console.log(`  (population ${population.length}, drawn in the form ${shown})`);

  return { ran, failed: failedList.slice() };
}

const load = async (file, mutate) => {
  const got = await loadWithProbe(file, mutate ? { mutate: (t) => mutate(t.replace(/\r\n/g, '\n')) } : {});
  return got.module;
};
// The bar's module, and the text it was built from — W scans the text the mutant actually runs.
const barModule = async (mutate) => {
  const text = readFileSync(BAR, 'utf8').replace(/\r\n/g, '\n');
  const m = await load(BAR, mutate);
  return { PathBar: m.PathBar, __source: mutate ? mutate(text) : text };
};

const MUTANTS = [
  { name: 'one-guide-too-many', catches: ['G2'], file: VIEW,
    from: '  for (let i = 0; i < depth; i += 1) {', to: '  for (let i = 0; i <= depth; i += 1) {' },
  { name: 'the-one-of-row-has-no-guides', catches: ['G3'], file: VIEW,
    from: '  if (depth > 0) head.appendChild(depthGuides(depth));\n', to: '' },
  { name: 'the-head-words-are-dropped', catches: ['T2', 'T3', 'T4'], file: VIEW,
    from: '    ...head.map((word) =>', to: '    ...[].map((word) =>' },
  { name: 'every-step-lands-on-the-node-itself', catches: ['T5', 'T6'], file: VIEW,
    from: '  const landing = (count) => drawn.filter((node) => stepsOf(node) <= count).pop() || drawn[0];',
    to: '  const landing = () => drawn[drawn.length - 1];' },
  { name: 'a-step-asks-for-the-root', catches: ['P3'], file: BAR,
    from: "go.addEventListener('click', () => this.onPick(step.path));",
    to: "go.addEventListener('click', () => this.onPick(this.trail[0].path));" },
  { name: 'the-last-step-asks-too', catches: ['P3'], file: BAR,
    from: "      else if (go.addEventListener) go.addEventListener('click'", to: "      if (go.addEventListener) go.addEventListener('click'" },
  { name: 'a-new-seat-stays-empty', catches: ['P4'], file: BAR,
    from: '    this.mount = mount || null;\n    this.render();\n', to: '    this.mount = mount || null;\n' },
  { name: 'the-bar-spells-a-section', catches: ['W2'], file: BAR,
    from: "    bar.className = 'oe-path-bar';", to: "    bar.className = 'oe-path-bar'; bar.dataset.from = 'mappings';" },
];

const main = async () => {
  console.log('== baseline ==');
  const base = suite(await load(VIEW), await barModule());
  const BASE_NAMES = NAMES.slice();
  console.log(`\n${base.ran - base.failed.length} passed, ${base.failed.length} failed.`);
  if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
  const { wrong } = await scoreMutants(MUTANTS, async (m) => {
    const swap = (t) => { if (!t.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.name}`); return t.split(m.from).join(m.to); };
    let view;
    let barMods;
    try {
      view = m.file === VIEW ? await load(VIEW, swap) : await load(VIEW);
      barMods = m.file === BAR ? await barModule(swap) : await barModule();
    } catch (err) {
      console.error(`HARNESS FAILURE: ${err.message}`);
      process.exit(2);
    }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    try { suite(view, barMods); } finally { console.log = real; }
    return { failures: failedList, ran };
  }, { baselineRan: base.ran, baselineNames: BASE_NAMES,
       title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
  console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
  process.exit(wrong ? 1 : 0);
};

main();
