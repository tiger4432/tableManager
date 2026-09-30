/**
 * Ledger form: a role's attributes inherited from its source, read-only (lead 619befe8c, implementer
 * 37c714205). The form is the real `renderSkeletonForm`, fed the server's skeleton
 * (fixtures/authoring_skeleton.json) and the server's plan for the sample's `dt_job`
 * (fixtures/authoring_inherited_plan.json, both captured by the scripts beside them), every branch open.
 *
 *   I  where the plan says a role inherits: the source path the value comes from, in the
 *      declaration's own words, then one step under it each inherited member drawn read-only - no control in it -
 *      while the map's add row (the override) stays and its own row is not drawn twice
 *   C  the same form without that row draws no block; the plan's list-valued shape rows draw none
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc, walk } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { declarationShape } from '../src/ontology_skeleton.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VIEW = path.join(HERE, '..', 'src', 'ontology_explorer_view.js');
const SKELETON = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'authoring_skeleton.json'), 'utf8'));
const PLAN = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'authoring_inherited_plan.json'), 'utf8'));
const SAMPLE = JSON.parse(readFileSync(
  path.join(HERE, '..', '..', 'server', 'config', 'sample', 'ledger_config.json.sample'), 'utf8'));
const RAW = SAMPLE.sources.dt_job;
const SECTION = (SKELETON.authorable_kinds.find((k) => k.id === 'source_plan') || {}).section;
const INHERITED = PLAN.fields.filter((row) => (row.ground || {}).rule === 'inherited_from_source');
const ROLE = 'bind.mappings.counted.bind.subject.attributes';

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
// The form as the author has it: editable, the plan's rows answered by path.
const liveContext = (fields) => ({
  schema: { skeleton: SKELETON.skeleton, authorable_kinds: SKELETON.authorable_kinds }, readOnly: false,
  planRow: (at) => fields.find((row) => row.path === `${PLAN.base}${at ? '.' + at : ''}`) || null,
  plannedMembers: () => [], covering: () => null,
  deref: (item) => (item && item.use ? (SKELETON.skeleton.defs || {})[item.use] : item), declared: () => [],
  rolesNear: () => [], usedElsewhere: () => [], renderRow: () => null, suggest: (row) => row,
  hot: [], expanded: ALL_OPEN, absolute: (at) => `${PLAN.base}.${at}`, planLoaded: true,
});
const nodeAt = (form, at) => walk(form).find((n) => cls(n, 'oe-node') && n.dataset.path === at) || null;
const rowsLabelled = (el, label) => walk(el).filter((n) => cls(n, 'oe-node-row')
  && walk(n).some((m) => cls(m, 'oe-node-name') && m._text === label));

function suite(view) {
  const draw = (fields) => view.renderSkeletonForm(liveContext(fields),
    declarationShape(SKELETON.skeleton, SECTION), '', RAW, 0, 'dt_job');
  console.log('\n-- I. inherited, read-only --');
  ok('I0 the plan says two roles inherit (else the rest proves nothing)', INHERITED.length === 2
    && INHERITED.some((row) => row.path === `${PLAN.base}.${ROLE}`), INHERITED.map((row) => row.path).join(', '));
  const form = draw(PLAN.fields);
  const map = nodeAt(form, ROLE);
  const header = map ? rowsLabelled(map, 'Inherited from') : [];
  eq('I1 the source path it comes from, in the declaration\'s words',
    header.length ? (walk(header[0]).find((n) => cls(n, 'oe-planned-from')) || {})._text : '(none)',
    'bind › entities › dtjob@1 › attributes');
  const row = INHERITED.find((r) => r.path === `${PLAN.base}.${ROLE}`);
  const members = Object.keys(row.value).map((key) => nodeAt(form, `${ROLE}.${key}`));
  eq('I2 each inherited member is drawn with its value', members.map((n) => (n ? n.textContent.includes(
    row.value[n.dataset.path.split('.').pop()].column) : false)).join(','), Object.keys(row.value).map(() => 'true').join(','));
  const inside = members.filter(Boolean).flatMap((n) => walk(n));
  const controls = inside.filter((n) => ['INPUT', 'SELECT', 'TEXTAREA'].includes(n.tagName)
    || (n.tagName === 'BUTTON' && n.dataset.action !== 'toggle-field'));
  eq('I3 no control inside an inherited member (only its fold)', controls.map((n) => n.tagName + ':' + n.dataset.action).join(',') || 0, 0);
  const own = map ? rowsLabelled(map, 'This slot') : [];
  const add = map ? walk(map).filter((n) => n.dataset && n.dataset.action === 'form-name' && n.dataset.value === ROLE) : [];
  eq('I4 the map\'s own row is not drawn twice, and its add row (the override) stays', `${own.length}|${add.length}`, '0|1');
  const depthOf = (el) => Number(el ? el.style.getPropertyValue('--oe-depth') : NaN);
  const memberRow = members[0] ? walk(members[0]).find((n) => cls(n, 'oe-node-row')) : null;
  eq('I5 the members sit one step under that line, not beside it as the map\'s own',
    header.length ? depthOf(memberRow) - depthOf(header[0]) : '(none)', 1);

  console.log('\n-- C. contrast --');
  const without = draw(PLAN.fields.filter((r) => r !== row));
  const bare = nodeAt(without, ROLE);
  eq('C1 without that plan row: no block, no member',
    `${bare ? rowsLabelled(bare, 'Inherited from').length : 'no map'}|${Object.keys(row.value).filter((key) => nodeAt(without, `${ROLE}.${key}`)).length}`, '0|0');
  eq('C2 across the whole form only the plan\'s inherited rows draw a block (list-valued shape rows do not)',
    rowsLabelled(form, 'Inherited from').length, INHERITED.length);
  return { ran, failed: failedList.slice() };
}

const load = async (mutate) => (await loadWithProbe(VIEW, mutate ? { mutate } : {})).module;

const MUTANTS = [
  { name: 'the-live-context-draws-it', catches: ['I3'],
    from: '  const read = readContext(context.schema, context.expanded);\n', to: '  const read = context;\n' },
  { name: 'no-source-path', catches: ['I1'],
    from: "  const rows = [treeRow(depth + 1, 'Inherited from', [],", to: "  const rows = [treeRow(depth + 1, 'Value', []," },
  { name: 'own-row-drawn-too', catches: ['I4'],
    from: '  if (given) box.append(...renderPlannedValue(context, node, path, given, depth));\n  else {\n',
    to: '  if (given) box.append(...renderPlannedValue(context, node, path, given, depth));\n  {\n' },
  { name: 'members-beside-the-line', catches: ['I5'],
    from: '                                     row.value[key], depth + 2, key);', to: '                                     row.value[key], depth + 1, key);' },
  { name: 'a-list-read-as-a-value', catches: ['C2'],
    from: "    && typeof row.value === 'object' && !Array.isArray(row.value) ? row : null;",
    to: "    && typeof row.value === 'object' ? row : null;" },
];

const main = async () => {
  console.log('== baseline ==');
  const result = suite(await load());
  const BASE_NAMES = NAMES.slice();
  console.log(`\n${result.ran - result.failed.length} passed, ${result.failed.length} failed.`);
  if (result.failed.length) { console.log(`ASSERTIONS ${result.ran} ${result.failed.length}`); process.exit(1); }
  const { wrong } = await scoreMutants(MUTANTS, async (m) => {
    const swap = (t) => { if (!t.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.name}`); return t.split(m.from).join(m.to); };
    let view;
    try { view = await load(swap); } catch (err) { console.error(`HARNESS FAILURE: ${err.message}`); process.exit(2); }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    try { suite(view); } catch (err) { failedList.push(`threw: ${err.message}`); } finally { console.log = real; }
    return { failures: failedList, ran };
  }, { baselineRan: result.ran, baselineNames: BASE_NAMES,
       title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
  console.log(`\nASSERTIONS ${result.ran} ${result.failed.length}`);
  process.exit(wrong ? 1 : 0);
};

main();
