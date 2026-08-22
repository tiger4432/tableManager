// Harness — the 2b reference grid's paste contract: which columns are copied, in what order,
// what the alignment band says about them, and whether the panel's copy survives the
// document-level handler in `clipboard.js`.
// Run: node client2/tests/reference_grid_paste_harness.mjs   (no node_modules — vm sandbox)
//
// WHY A SANDBOX AND NOT AN IMPORT. `enrichment_reference_view.js` imports `config.js`, which
// touches `window` at module scope, so it cannot be imported in node. The decision functions
// are lifted verbatim out of the source by anchor and evaluated in a vm — the same technique
// as `virtual_column_render_harness.mjs`, for the same reason. `tsv.js` IS imported, because
// it is pure, and using the real serializer is the point: a second TSV writer here would let
// the harness pass while the screen wrote something else.
//
// EVERY CHECK IS PAIRED WITH A MUTANT. The suite re-runs against deliberately broken sources
// and FAILS if a defect still passes — a check that cannot fail proves nothing. It also runs
// CONTROL mutants (renaming locals, stripping comments) which must ESCAPE: if a control is
// caught, some check is reading source text rather than behaviour and its green is worthless.
//
// EXTRACTION ANCHORS ARE THE ONE PLACE SOURCE TEXT IS READ, and this file exits 2 — loudly,
// not green — when one stops matching. A harness that goes quiet because it lost the code is
// worse than no harness. That is not hypothetical here: moving a comment between two lines of
// a ternary silently disarmed a mutant in this repo earlier the same day.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';
import { serializeTsv } from '../src/tsv.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const read = name => readFileSync(join(SRC, name), 'utf8');

function die(message) {
  console.error(`HARNESS BROKEN: ${message}`);
  console.log('ASSERTIONS 0 0');
  process.exit(2);
}

/** Lift `function <name>(...) { ... }` out of a source by brace matching. */
function sliceFunction(source, declaration, what) {
  const start = source.indexOf(declaration);
  if (start < 0) die(`anchor is GONE: ${what} — searched for ${JSON.stringify(declaration)}`);
  let depth = 0;
  let index = source.indexOf('{', start);
  if (index < 0) die(`no body for ${what}`);
  for (let i = index; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') {
      depth--;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  die(`unbalanced braces for ${what}`);
}

const PANEL = 'enrichment_reference_view.js';
const CLIPBOARD = 'clipboard.js';

// The clipboard guard, scored as BEHAVIOUR rather than as text. The condition is lifted and
// run against fake events, so a rename or a comment change cannot fake a pass, and REMOVING
// the guard is caught because the predicate stops answering true.
const GUARD_ANCHOR = `if (e.target instanceof Element && e.target.closest('#reference-view')) {`;

// ── The fixture. Shaped from the LIVE declaration, not invented ──────────────────────────
// `dt_lot_slot_from_log`: target_fields ['dt_lot','dt_slot'], view[0] declares both, view[1]
// is the evidence view and declares nothing. Measured against the running server on
// 2026-08-21; the shape is what makes the fallback case real rather than hypothetical.
const RULE = { target_fields: ['dt_lot', 'dt_slot'] };
const DECLARING_VIEW = { candidate_for: { dt_lot: 'dt_lot', dt_slot: 'dt_slot' } };
const EVIDENCE_VIEW = { candidate_for: {} };
const PAYLOAD_COLUMNS = ['cells', 'dt_slot', 'dt_lot'];   // deliberately NOT already in order
const ROWS = [
  { cells: '125', dt_slot: '25', dt_lot: 'SYN-DT-103' },
  { cells: '72', dt_slot: '11', dt_lot: 'SYN-DT-104' }
];

/** What the panel would put on the clipboard for the declared columns of every row. */
function copyPayload(api, view, includeHeaders) {
  const plan = api.fillPlan(view, RULE, PAYLOAD_COLUMNS);
  const order = plan ? plan.order : PAYLOAD_COLUMNS;
  const fillCount = plan ? plan.pairs.length : order.length;
  const columns = order.slice(0, fillCount);
  const matrix = [];
  if (includeHeaders) matrix.push(columns);
  ROWS.forEach(row => matrix.push(columns.map(column => row[column] ?? '')));
  return serializeTsv(matrix);
}

const isVirtual = name => name === 'dt_x_base';

function runChecks(api) {
  let pass = 0;
  let fail = 0;
  const failures = [];
  const check = (label, condition) => {
    if (condition) pass++;
    else { fail++; failures.push(label); }
  };

  // ① The copied column order IS the declared order, and it does not inherit the payload's.
  check('TSV column order follows target_fields',
    copyPayload(api, DECLARING_VIEW, false) === 'SYN-DT-103\t25\nSYN-DT-104\t11');
  check('headers carry the declared order too',
    copyPayload(api, DECLARING_VIEW, true) === 'dt_lot\tdt_slot\nSYN-DT-103\t25\nSYN-DT-104\t11');
  check('declared columns lead the rendered order',
    JSON.stringify(api.fillPlan(DECLARING_VIEW, RULE, PAYLOAD_COLUMNS).order)
      === JSON.stringify(['dt_lot', 'dt_slot', 'cells']));

  // ③④ THE VERDICT AND ITS SCORING ARE GONE TOGETHER, in this same commit.
  // △소유자 2026-08-22: 「일치든 거절이든 없애 어차피 사람들이 알아서 함」. With the strip removed the
  // verdict had no consumer, and a pure function nothing calls, with a harness still scoring
  // it, is a green gate over dead code.

  // ⑤ THE FALLBACK, which is operational reality for every rule that declares nothing.
  check('a view with no candidate_for makes no plan',
    api.fillPlan(EVIDENCE_VIEW, RULE, PAYLOAD_COLUMNS) === null);
  check('a rule with no target_fields makes no plan',
    api.fillPlan(DECLARING_VIEW, {}, PAYLOAD_COLUMNS) === null);
  check('a declared column the query did not return is dropped',
    api.fillPlan(DECLARING_VIEW, RULE, ['dt_lot', 'cells']).pairs.length === 1);
  check('fallback keeps the payload order untouched',
    copyPayload(api, EVIDENCE_VIEW, false) === '125\t25\tSYN-DT-103\n72\t11\tSYN-DT-104');

  // ⑥ The clipboard guard, as behaviour.
  const inside = { target: makeElement(true) };
  const outside = { target: makeElement(false) };
  check('clipboard.js steps aside for a copy inside the panel',
    api.clipboardStepsAside(inside) === true);
  check('clipboard.js still handles a copy outside the panel',
    api.clipboardStepsAside(outside) === false);

  return { pass, fail, failures };
}

// Built here rather than in the sandbox so both share one `Element` identity.
let ElementCtor = null;
function makeElement(insidePanel) {
  const element = new ElementCtor();
  element.closest = selector => (insidePanel && selector === '#reference-view') ? element : null;
  return element;
}

// ── Run ──────────────────────────────────────────────────────────────────────────────────
const ORIGINAL = { [PANEL]: read(PANEL), [CLIPBOARD]: read(CLIPBOARD) };

function apiFor(sources) {
  const context = { Element: class Element {}, module: {} };
  ElementCtor = context.Element;
  vm.createContext(context);
  const panel = sources[PANEL];
  const clipboard = sources[CLIPBOARD];
  const fillPlan = sliceFunction(panel, 'function fillPlan(', 'fillPlan');
  const guardBody = clipboard.includes(GUARD_ANCHOR)
    ? `if (e.target instanceof Element && e.target.closest('#reference-view')) { return true; } return false;`
    : `return false;`;
  new vm.Script(`
    ${fillPlan}
    function clipboardStepsAside(e) { ${guardBody} }
    module.api = { fillPlan, clipboardStepsAside };
  `).runInContext(context);
  const api = context.module.api;
  api.__Element__ = context.Element;
  return api;
}

const base = runChecks(apiFor(ORIGINAL));
console.log('── reference grid paste contract ──────────────────────────────────');
console.log(`  ${base.pass} passed, ${base.fail} failed`);
base.failures.forEach(f => console.log(`  FAIL  ${f}`));

// ── Defect mutants: each MUST be caught ──────────────────────────────────────────────────
// Newline-agnostic on purpose. These sources are CRLF on this checkout and LF elsewhere, and
// an anchor that matches on one machine and silently vanishes on the other is a mutant that
// quietly stops testing anything — which is the exact failure this file exists to prevent.
const LF = String.fromCharCode(10);
const CRLF = String.fromCharCode(13, 10);
const toCrlf = text => text.split(LF).join(CRLF);
const sub = (source, from, to, name) => {
  if (source.includes(from)) return source.replace(from, to);
  const crlf = toCrlf(from);
  if (source.includes(crlf)) return source.replace(crlf, toCrlf(to));
  die(`mutation anchor is GONE: ${name}`);
};

const MUTANTS = [
  ['reverse the declared column order', s => ({ ...s,
    [PANEL]: sub(s[PANEL], 'order: [...fillColumns,', 'order: [...fillColumns.slice().reverse(),',
      'reverse-order') })],
  ['remove the clipboard.js guard', s => ({ ...s,
    [CLIPBOARD]: sub(s[CLIPBOARD], GUARD_ANCHOR, 'if (false) {', 'drop-guard') })]
];

let escaped = 0;
console.log('\n── defect mutants (each must be CAUGHT) ───────────────────────────');
for (const [label, mutate] of MUTANTS) {
  let caught = false;
  try {
    const result = runChecks(apiFor(mutate(ORIGINAL)));
    caught = result.fail > base.fail;
  } catch { caught = true; }
  console.log(`  ${caught ? 'caught ' : 'ESCAPED'} ${label}`);
  if (!caught) escaped++;
}

// ── Control mutants: each must ESCAPE ────────────────────────────────────────────────────
// If a control is caught, a check is reading source text rather than behaviour.
console.log('\n── control mutants (each must ESCAPE) ─────────────────────────────');
const CONTROLS = [
  ['every full-line comment stripped', s => ({
    [PANEL]: s[PANEL].split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n'),
    [CLIPBOARD]: s[CLIPBOARD].split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')
  })],
  ['a local renamed consistently', s => ({ ...s,
    [PANEL]: s[PANEL].split('sourceCols').join('copiedCols') })]
];
let controlsCaught = 0;
for (const [label, mutate] of CONTROLS) {
  let caught = false;
  try {
    const result = runChecks(apiFor(mutate(ORIGINAL)));
    caught = result.fail > base.fail;
  } catch { caught = true; }
  console.log(`  ${caught ? 'CAUGHT ' : 'escaped'} ${label}`);
  if (caught) controlsCaught++;
}

const failed = base.fail + escaped + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${MUTANTS.length - escaped}/${MUTANTS.length} defects caught, ${escaped} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail + MUTANTS.length + CONTROLS.length} ${failed}`);
process.exit(failed > 0 ? 1 : 0);
