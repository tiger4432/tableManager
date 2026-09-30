/**
 * The ledger form's grammar (owner 09-30 「세로 여백이 너무 많고」 · 「뭐가 클릭해야되는건지 뭐가 설명인지」 ·
 * 「무슨 의미인지」; lead 8fd2f185d · 7602a4a83 · 482288b12). The rows are the real `renderAuthoringRow`
 * on the server's own plan (fixtures/authoring_inherited_plan.json); the CSS is the canon file, read
 * by selector — the two causes the lead found are CSS declarations.
 *
 *   L  a folded one-value field is one line: the bare card lays its parts out in a row, the folded
 *      button reads from the left and is not a 36px box (the global rule), and the folded line is the
 *      value only — the ground is the open card's
 *   P  what is pressed looks pressable and what explains does not: an explaining word has no box, a
 *      fold is a link-coloured word, the folded value wears the input's surface, no tier word in a head
 *   W  no word only this code knows (482288b12): the state word is the same open or folded, no tier word,
 *      no «This slot», a ground's path in the declaration's words, no «removability not measured»,
 *      and a switched-off field holding an empty list is not drawn (115134f12)
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
const SKEL = path.join(HERE, '..', 'src', 'ontology_skeleton.js');
const CSS = path.join(HERE, '..', 'src', 'ontology_explorer.css');
const PLAN = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'authoring_inherited_plan.json'), 'utf8'));
// A derived row the server grounds, with a value that is not a mapping: the ordinary folded one-liner.
const GROUNDED = PLAN.fields.find((row) => row.state === 'derived' && row.ground && row.ground.text
  && (typeof row.value !== 'object' || Array.isArray(row.value)));

const SKELETON = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'authoring_skeleton.json'), 'utf8'));
const SAMPLE = JSON.parse(readFileSync(
  path.join(HERE, '..', '..', 'server', 'config', 'sample', 'ledger_config.json.sample'), 'utf8'));
const RAW = SAMPLE.sources.dt_job;
const SECTION = (SKELETON.authorable_kinds.find((k) => k.id === 'source_plan') || {}).section;
// The implementer's `when` on group_by is not in the skeleton yet, so this copy carries one: a record
// holding both `unit` and `group_by` asks for group_by only when unit is `group`.
const GATED = JSON.parse(JSON.stringify(SKELETON.skeleton));
let gatedFields = 0;
(function gate(node) {
  if (!node || typeof node !== 'object') return;
  const fields = Array.isArray(node.fields) ? node.fields : [];
  const groupBy = fields.find((f) => f && f.key === 'group_by');
  if (groupBy && fields.some((f) => f && f.key === 'unit')) { groupBy.when = { field: 'unit', is: 'group' }; gatedFields += 1; }
  for (const child of Object.values(node)) gate(child);
})(GATED);
// A plain leaf the plan answers (its state word is 「Declared」), for the open/folded comparison.
const LEAF = PLAN.fields.find((row) => row.path === `${PLAN.base}.relation`);
// Every branch open; every field folded by the rule (field folds are keyed by the plan's path).
const ALL_OPEN_BRANCHES = new Proxy({}, { get: (_t, k) => (String(k).startsWith('bundle.') ? undefined : true) });
const liveContext = (view, expanded) => ({
  schema: { skeleton: SKELETON.skeleton, authorable_kinds: SKELETON.authorable_kinds }, readOnly: false,
  planRow: (p) => PLAN.fields.find((row) => row.path === `${PLAN.base}${p ? '.' + p : ''}`) || null,
  plannedMembers: () => [], covering: () => null,
  deref: (item) => (item && item.use ? (SKELETON.skeleton.defs || {})[item.use] : item), declared: () => [],
  rolesNear: () => [], usedElsewhere: () => [],
  renderRow: (row, node, bare = false) => view.renderAuthoringRow(row, expanded, null, bare, null),
  suggest: (row) => row, hot: [], expanded, absolute: (p) => `${PLAN.base}.${p}`, planLoaded: true,
});

globalThis.document = makeDoc('light');

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

// One rule's declarations, by its exact selector line (comments out).
const rule = (css, selector) => {
  const at = css.indexOf(`\n${selector} {`);
  if (at < 0) return null;
  const body = css.slice(css.indexOf('{', at) + 1, css.indexOf('}', at));
  return body.replace(/\/\*[\s\S]*?\*\//g, '');
};
const decl = (body, prop) => {
  const m = body && new RegExp(`(?:^|[;{\\s])${prop}\\s*:\\s*([^;}]+)`).exec(body);
  return m ? m[1].trim() : null;
};

function suite(view, css, skel) {
  console.log('\n-- L. a folded one-value field is one line --');
  ok('L0 the fixture has a grounded derived row (else the rest proves nothing)', Boolean(GROUNDED), 'none');
  eq('L1 the bare folded card lays its parts out in a row',
    decl(rule(css, '#ontology-explorer-root .oe-field.is-bare.is-folded'), 'flex-direction'), 'row');
  const folded = rule(css, '#ontology-explorer-root .oe-field-folded');
  eq('L2 the folded value reads from the left, is one line high and wraps - not the global 36px centred nowrap box',
    `${decl(folded, 'justify-content')}|${decl(folded, 'height')}|${decl(folded, 'min-height')}|${decl(folded, 'white-space')}`,
    'flex-start|auto|0|normal');
  const shut = view.renderAuthoringRow(GROUNDED, {}, null, true);
  const line = walk(shut).find((n) => cls(n, 'oe-field-folded'));
  eq('L3 the folded line is the value only', line ? line.children.map((c) => c.className).join(',') : '(no line)', 'oe-folded-value');
  const open = view.renderAuthoringRow(GROUNDED, { [GROUNDED.path]: true }, null, true);
  ok('L4 the open card still says why the value is what it is',
    walk(open).some((n) => n._text === GROUNDED.ground.text), GROUNDED.ground.text);

  console.log('\n-- P. what is pressed looks pressable, what explains does not --');
  const words = rule(css, ':is(#ontology-explorer-root, .oe-skeleton-form) :is(.oe-tier, .oe-node-badge)');
  eq('P1 a word that explains has no box and is the canon\'s dim ink (the state word, a demand, a node\'s kind)',
    `${decl(words, 'border')}|${decl(words, 'padding')}|${decl(words, 'color')}`, '0|0|var(--oe-muted)');
  const fold = rule(css, ':is(#ontology-explorer-root, .oe-skeleton-form) .oe-node-fold,\n:is(#ontology-explorer-root, .oe-skeleton-form) .oe-node-folded');
  eq('P2 a fold is a link-coloured word, one line high', `${decl(fold, 'color')}|${decl(fold, 'height')}`, 'var(--oe-accent)|auto');
  eq('P3 the folded value wears the input\'s surface', `${decl(folded, 'border')}|${decl(folded, 'background')}`,
    '1px solid var(--oe-line)|var(--oe-surface)');
  const heads = [shut, open, view.renderAuthoringRow(GROUNDED, {}, null, false)]
    .flatMap((card) => walk(card).filter((n) => cls(n, 'oe-field-head')));
  eq('P4 no tier word in any card\'s head (bare, open, or outside the tree)',
    heads.length ? heads.flatMap((hd) => walk(hd).filter((n) => cls(n, 'oe-tier'))).length : '(no head)', 0);
  eq('P5 a chip nobody can press has no box', decl(rule(css, '#ontology-explorer-root .oe-chip:not(.oe-pick)'), 'border-color'), 'transparent');
  eq('P6 an empty head in a tree row takes no room',
    decl(rule(css, '#ontology-explorer-root .oe-field.is-bare .oe-field-head:empty'), 'display'), 'none');

  console.log('\n-- W. no word only this code knows --');
  const at = LEAF.path.slice(PLAN.base.length + 1);
  const form = (expanded) => view.renderSkeletonForm(liveContext(view, expanded),
    declarationShape(SKELETON.skeleton, SECTION), '', RAW, 0, 'dt_job');
  const stateOf = (tree) => {
    const node = walk(tree).find((n) => cls(n, 'oe-node') && n.dataset.path === at);
    const row = node && node.children.find((c) => cls(c, 'oe-node-row'));
    const st = row && row.children.find((c) => cls(c, 'oe-node-state'));
    return st ? st.textContent : '(no row)';
  };
  const folded2 = form(ALL_OPEN_BRANCHES);
  const opened = form(new Proxy({}, { get: (_t, k) => (k === LEAF.path ? true : ALL_OPEN_BRANCHES[k]) }));
  eq('W1 the state column says the same word folded and opened (not the tier word)',
    `${stateOf(folded2)}|${stateOf(opened)}`, 'Declared|Declared');
  const TIERS = new Set(PLAN.fields.map((r) => r.tier));
  const states = walk(opened).filter((n) => cls(n, 'oe-node-state')).map((n) => n.textContent).filter(Boolean);
  ok('W2 no tier word in any state column', states.length > 5 && !states.some((s) => TIERS.has(s)),
    `${states.length} states, tiers seen: ${states.filter((s) => TIERS.has(s)).join(',')}`);
  eq('W3 no row is named «This slot»', walk(opened).filter((n) => cls(n, 'oe-node-name') && n._text === 'This slot').length, 0);
  const paths = walk(open).filter((n) => cls(n, 'oe-ground-from')).map((n) => n._text);
  ok('W4 a ground names where it comes from in the declaration\'s words, not the bundle path',
    paths.length > 0 && paths.every((p) => !p.startsWith('bundle') && p.includes('›')), paths.join(' | '));
  const unmeasured = view.renderAuthoringRow({ ...GROUNDED, disposition: 'unmeasured' }, { [GROUNDED.path]: true }, null, true);
  eq('W5 the unmeasured line is gone (its refusals are drawn on their own rows)',
    walk(unmeasured).filter((n) => /Refusals remain|removability/.test(n._text || '')).length, 0);
  const gatedForm = (groupBy) => view.renderSkeletonForm(
    { ...liveContext(view, ALL_OPEN_BRANCHES), schema: { skeleton: GATED, authorable_kinds: SKELETON.authorable_kinds } },
    declarationShape(GATED, SECTION), '', { ...RAW, read: { ...RAW.read, unit: 'row', group_by: groupBy } }, 0, 'dt_job');
  const drawn = (tree) => walk(tree).some((n) => cls(n, 'oe-node') && n.dataset.path === 'read.group_by');
  eq('W6 a switched-off field holding an empty list is not drawn (unit row, group_by [])',
    gatedFields > 0 ? drawn(gatedForm([])) : '(no gated field)', false);
  eq('W7 holding a value it is still drawn, so the save shows it going (unit row, group_by [lot])',
    drawn(gatedForm(['lot'])), true);
  const field = { key: 'group_by', when: { field: 'unit', is: 'group' } };
  eq('W8 the predicate the form asks: an empty list or string holds nothing, a list or 0 holds a value',
    ['[]', '"  "', '["lot"]', '0'].map((v) => skel.fieldApplies(field, { unit: 'row' }, JSON.parse(v))).join('|'),
    'false|false|true|true');
  return { ran, failed: failedList.slice() };
}

const cssText = (mutate) => {
  const text = readFileSync(CSS, 'utf8').replace(/\r\n/g, '\n');
  return mutate ? mutate(text) : text;
};
const loadFrom = async (file, mutate) => (await loadWithProbe(file, mutate ? { mutate: (t) => mutate(t.replace(/\r\n/g, '\n')) } : {})).module;
const load = (mutate) => loadFrom(VIEW, mutate);

const MUTANTS = [
  { name: 'the-bare-card-stacks-again', catches: ['L1'], file: CSS,
    from: '.oe-field.is-bare.is-folded { flex-direction: row;', to: '.oe-field.is-bare.is-folded { flex-direction: column;' },
  { name: 'the-global-button-rule-wins', catches: ['L2'], file: CSS,
    from: '  justify-content: flex-start; height: auto; min-height: 0; white-space: normal;\n', to: '\n' },
  { name: 'a-word-wears-a-box-again', catches: ['P1'], file: CSS,
    from: '  padding: 0; border: 0; background: transparent; color: var(--oe-muted);',
    to: '  padding: 3px 10px; border: 1px solid var(--oe-line); background: transparent; color: var(--oe-muted);' },
  { name: 'the-explaining-word-is-half-ink', catches: ['P1'], file: CSS,
    from: '  padding: 0; border: 0; background: transparent; color: var(--oe-muted);',
    to: '  padding: 0; border: 0; background: transparent; color: var(--oe-ink-meta);' },
  { name: 'a-read-only-chip-wears-a-box', catches: ['P5'], file: CSS,
    from: '.oe-chip:not(.oe-pick) { border-color: transparent; }', to: '.oe-chip:not(.oe-pick) { border-color: var(--oe-line); }' },
  { name: 'the-empty-head-takes-a-gap', catches: ['P6'], file: CSS,
    from: '.oe-field.is-bare .oe-field-head:empty { display: none; }', to: '.oe-field.is-bare .oe-field-head:empty { }' },  { name: 'the-fold-goes-grey', catches: ['P2'], file: CSS,
    from: '  color: var(--oe-accent); padding: 0 var(--space-1); height: auto;', to: '  color: var(--oe-muted); padding: 0 var(--space-1); height: auto;' },
  { name: 'the-folded-value-looks-like-text', catches: ['P3'], file: CSS,
    from: '  border: 1px solid var(--oe-line); background: var(--oe-surface); padding: var(--space-1) var(--space-2);',
    to: '  border: 1px solid transparent; background: transparent; padding: var(--space-1) var(--space-2);' },
  { name: 'the-tier-chip-comes-back', catches: ['P4'], file: VIEW,
    from: "  if (!bare) head.append(h('b', '', row.label));\n",
    to: "  if (!bare) head.append(h('b', '', row.label));\n  head.append(h('i', `oe-tier oe-tier--${row.tier}`, row.tier));\n" },
  { name: 'the-open-row-says-its-tier', catches: ['W1', 'W2'], file: VIEW,
    from: "    state = h('i', 'oe-tier oe-tier--' + planned.tier, fold.word);",
    to: "    state = h('i', 'oe-tier oe-tier--' + planned.tier, fold.open ? planned.tier : fold.word);" },
  { name: 'this-slot-is-back', catches: ['W3'], file: VIEW,
    from: "  return treeRow(depth + 1, '', [],\n                 context.renderRow(own,",
    to: "  return treeRow(depth + 1, 'This slot', [],\n                 context.renderRow(own," },
  { name: 'the-bundle-path-is-back', catches: ['W4'], file: VIEW,
    from: "    box.append(h('code', 'oe-ground-from', trail.join(' › ')));", to: "    box.append(h('code', 'oe-ground-from', from));" },
  { name: 'unmeasured-is-said-again', catches: ['W5'], file: VIEW,
    from: "      act.append(h('span', '', 'Default · can be overridden'));\n    }\n",
    to: "      act.append(h('span', '', 'Default · can be overridden'));\n    } else if (row.disposition === 'unmeasured') {\n"
      + "      act.append(h('span', '', 'Refusals remain · removability not measured'));\n    }\n" },
  { name: 'an-empty-list-is-held', catches: ['W8'], file: SKEL,
    from: '  if (!isBlank(held)) return true;', to: '  if (held !== undefined) return true;' },
  { name: 'the-form-skips-the-gate', catches: ['W6'], file: VIEW,
    from: '    if (!fieldApplies(field, held, current)) continue;\n', to: '\n' },
  { name: 'the-ground-rides-the-folded-line', catches: ['L3'], file: VIEW,
    from: "    if (!bare) line.append(h('i', 'oe-folded-why', fold.reason));\n",
    to: "    if (!bare) line.append(h('i', 'oe-folded-why', fold.reason));\n    if (row.ground?.text) line.append(h('small', 'oe-folded-ground', row.ground.text));\n" },
];

const main = async () => {
  console.log('== baseline ==');
  const base = suite(await load(), cssText(), await loadFrom(SKEL));
  const BASE_NAMES = NAMES.slice();
  console.log(`\n${base.ran - base.failed.length} passed, ${base.failed.length} failed.`);
  if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
  const { wrong } = await scoreMutants(MUTANTS, async (m) => {
    const swap = (t) => { if (!t.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.name}`); return t.split(m.from).join(m.to); };
    let view, css, skel;
    try {
      view = m.file === VIEW ? await load(swap) : await load();
      css = m.file === CSS ? cssText(swap) : cssText();
      skel = m.file === SKEL ? await loadFrom(SKEL, swap) : await loadFrom(SKEL);
    } catch (err) { console.error(`HARNESS FAILURE: ${err.message}`); process.exit(2); }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    try { suite(view, css, skel); } finally { console.log = real; }
    return { failures: failedList, ran };
  }, { baselineRan: base.ran, baselineNames: BASE_NAMES,
       title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
  console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
  process.exit(wrong ? 1 : 0);
};

main();
