/**
 * The ledger form's grammar (owner 09-30 「세로 여백이 너무 많고」 · 「뭐가 클릭해야되는건지 뭐가 설명인지」 ·
 * 「무슨 의미인지」; lead 8fd2f185d · 7602a4a83 · 482288b12). The rows are the real `renderAuthoringRow`
 * on the server's own plan (fixtures/authoring_inherited_plan.json); the CSS is the canon file, read
 * by selector — the two causes the lead found are CSS declarations.
 *
 *   L  a folded one-value field is one line: the bare card lays its parts out in a row, the folded
 *      button reads from the left and is not a 36px box (the global rule), and the folded line is the
 *      value only — the ground is the open card's
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc, walk } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VIEW = path.join(HERE, '..', 'src', 'ontology_explorer_view.js');
const CSS = path.join(HERE, '..', 'src', 'ontology_explorer.css');
const PLAN = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'authoring_inherited_plan.json'), 'utf8'));
// A derived row the server grounds, with a value that is not a mapping: the ordinary folded one-liner.
const GROUNDED = PLAN.fields.find((row) => row.state === 'derived' && row.ground && row.ground.text
  && (typeof row.value !== 'object' || Array.isArray(row.value)));

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

function suite(view, css) {
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
  return { ran, failed: failedList.slice() };
}

const cssText = (mutate) => {
  const text = readFileSync(CSS, 'utf8').replace(/\r\n/g, '\n');
  return mutate ? mutate(text) : text;
};
const load = async (mutate) => (await loadWithProbe(VIEW, mutate ? { mutate: (t) => mutate(t.replace(/\r\n/g, '\n')) } : {})).module;

const MUTANTS = [
  { name: 'the-bare-card-stacks-again', catches: ['L1'], file: CSS,
    from: '.oe-field.is-bare.is-folded { flex-direction: row;', to: '.oe-field.is-bare.is-folded { flex-direction: column;' },
  { name: 'the-global-button-rule-wins', catches: ['L2'], file: CSS,
    from: '  justify-content: flex-start; height: auto; min-height: 0; white-space: normal;\n', to: '\n' },
  { name: 'the-ground-rides-the-folded-line', catches: ['L3'], file: VIEW,
    from: "    if (!bare) line.append(h('i', 'oe-folded-why', fold.reason));\n",
    to: "    if (!bare) line.append(h('i', 'oe-folded-why', fold.reason));\n    if (row.ground?.text) line.append(h('small', 'oe-folded-ground', row.ground.text));\n" },
];

const main = async () => {
  console.log('== baseline ==');
  const base = suite(await load(), cssText());
  const BASE_NAMES = NAMES.slice();
  console.log(`\n${base.ran - base.failed.length} passed, ${base.failed.length} failed.`);
  if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
  const { wrong } = await scoreMutants(MUTANTS, async (m) => {
    const swap = (t) => { if (!t.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.name}`); return t.split(m.from).join(m.to); };
    let view, css;
    try {
      view = m.file === VIEW ? await load(swap) : await load();
      css = m.file === CSS ? cssText(swap) : cssText();
    } catch (err) { console.error(`HARNESS FAILURE: ${err.message}`); process.exit(2); }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    try { suite(view, css); } finally { console.log = real; }
    return { failures: failedList, ran };
  }, { baselineRan: base.ran, baselineNames: BASE_NAMES,
       title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
  console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
  process.exit(wrong ? 1 : 0);
};

main();
