// Harness — the 2b reference grid's paste contract: which columns are copied, in what order,
// and whether the panel's copy survives the document-level handler in `clipboard.js`.
// Run: node client2/tests/reference_grid_paste_harness.mjs
//
// 🔴 C-62 — THIS FILE USED TO SLICE, AND THE REASON IT GAVE WAS FALSE. Verbatim, from the
//    header it carried until today: 「`enrichment_reference_view.js` imports `config.js`, which
//    touches `window` at module scope, so it cannot be imported in node」. Measured 2026-09-10:
//    `node -e "await import('./src/enrichment_reference_view.js')"` and the same for
//    `clipboard.js` BOTH succeed. The standing rule (owner, 2026-09-02) says that a subject
//    which cannot be imported is itself the defect; the converse is what applies here — once it
//    CAN be imported, slicing has no reason left, and a stale reason is the most durable kind.
//
//    What slicing cost while it stood: it scores the SHAPE OF THE LETTERS. The clipboard guard
//    was checked by looking for one anchor STRING in the file and, if present, running a
//    predicate this harness had written itself. Re-spelling the guard would have reddened
//    correct code; re-writing it wrongly in the same spelling would have passed. Neither is a
//    measurement of behaviour. Both functions are now IMPORTED and CALLED.
//
// EVERY CHECK IS STILL PAIRED WITH A MUTANT, and the mutants changed mechanism with the
// conversion: `lib/probe.mjs` loads the subject WHOLE with the mutation applied to its source,
// so a mutant that fails to parse fails loudly instead of scoring as "caught". Two defects must
// be CAUGHT, two CONTROLS (stripped comments, a consistently renamed local) must ESCAPE — if a
// control is caught, some check is reading source text rather than behaviour.
//
// ⛔ The copy's 「starts with the original bytes」 assertion that the appending bridge needs is
//    NOT here, and its absence is correct rather than a gap: the base run imports the real
//    module directly, so there is no copy to prove anything about. The probe's own guards are
//    scored by `probe_mechanism_harness.mjs`.
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { serializeTsv } from '../src/tsv.js';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const PANEL_PATH = join(SRC, 'enrichment_reference_view.js');
const CLIPBOARD_PATH = join(SRC, 'clipboard.js');

// `Element` is a browser global the guard tests against. It is installed BEFORE the subjects
// load, and both the fake events and the subject see the SAME constructor — two identities
// would make `instanceof` answer false for reasons that have nothing to do with the guard.
class Element {}
globalThis.Element = Element;
// Both subjects reach `document` through `dom.js`'s getters at CALL time, never at load, so a
// minimal one is enough and nothing is patched inside the subject.
globalThis.document = globalThis.document
  || { getElementById: () => null, querySelector: () => null, addEventListener() {},
       createElement: () => ({ style: {}, classList: { add() {}, remove() {} },
                               appendChild() {}, setAttribute() {}, addEventListener() {} }) };

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

function makeElement(insidePanel) {
  const element = new Element();
  element.closest = selector => (insidePanel && selector === '#reference-view') ? element : null;
  return element;
}

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

  // ⑥ The clipboard guard, as behaviour — the REAL exported predicate, called.
  check('clipboard.js steps aside for a copy inside the panel',
    api.clipboardStepsAside({ target: makeElement(true) }) === true);
  check('clipboard.js still handles a copy outside the panel',
    api.clipboardStepsAside({ target: makeElement(false) }) === false);

  return { pass, fail, failures };
}

// ── Run ──────────────────────────────────────────────────────────────────────────────────
// The base run is a PLAIN IMPORT of both modules. No copy, no probe, no text.
const panelModule = await import('../src/enrichment_reference_view.js');
const clipboardModule = await import('../src/clipboard.js');
const REAL = {
  fillPlan: panelModule.fillPlan,
  clipboardStepsAside: clipboardModule.isReferenceSidebarCopy,
};

const base = runChecks(REAL);
console.log('── reference grid paste contract ──────────────────────────────────');
console.log(`  ${base.pass} passed, ${base.fail} failed`);
base.failures.forEach(f => console.log(`  FAIL  ${f}`));

/**
 * Load ONE of the two subjects with a mutation applied, and pair it with the real other one.
 *
 * 🔴 The probe refuses a `mutate` that matched nothing, so an anchor that stops matching is a
 *    LOUD exit rather than a mutant that quietly stopped testing anything. That is not
 *    hypothetical here: this file's predecessor recorded that moving a comment between two
 *    lines of a ternary silently disarmed one of its mutants.
 */
async function apiWith(which, mutate, tag) {
  const panel = which === 'panel'
    ? (await loadWithProbe(PANEL_PATH, { mutate, tag })).module
    : panelModule;
  const clipboard = which === 'clipboard'
    ? (await loadWithProbe(CLIPBOARD_PATH, { mutate, tag })).module
    : clipboardModule;
  return { fillPlan: panel.fillPlan, clipboardStepsAside: clipboard.isReferenceSidebarCopy };
}

// ── Defect mutants: each MUST be caught ──────────────────────────────────────────────────
const MUTANTS = [
  ['reverse the declared column order', 'panel',
    s => s.replace('order: [...fillColumns,', 'order: [...fillColumns.slice().reverse(),')],
  ['remove the clipboard.js guard', 'clipboard',
    s => s.replace("e.target instanceof Element && e.target.closest('#reference-view')", 'false')],
];

// 🔴 A MUTANT THAT THROWS IS A HOLE, NOT A CATCH. The predecessor counted a throw as caught,
//    which cannot tell 「the checks noticed the defect」 from 「the module stopped loading」 —
//    and after the conversion the second is the likelier accident, because a mutation now
//    reaches a whole module rather than a fragment. A throw is reported by name and scored as
//    an ESCAPE, so it has to be fixed rather than banked.
let escaped = 0;
console.log('\n── defect mutants (each must be CAUGHT) ───────────────────────────');
for (const [label, which, mutate] of MUTANTS) {
  let caught = false;
  let threw = null;
  try {
    const result = runChecks(await apiWith(which, mutate, label.replace(/\W+/g, '_')));
    caught = result.fail > base.fail;
  } catch (err) { threw = err; }
  console.log(`  ${caught ? 'caught ' : 'ESCAPED'} ${label}`
    + (threw ? `  ⛔ THREW instead of failing a check: ${threw.message}` : ''));
  if (!caught) escaped++;
}

// ── Control mutants: each must ESCAPE ────────────────────────────────────────────────────
// If a control is caught, a check is reading source text rather than behaviour.
console.log('\n── control mutants (each must ESCAPE) ─────────────────────────────');
const CONTROLS = [
  ['every full-line comment stripped from the panel', 'panel',
    s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
  ['a local renamed consistently', 'panel',
    s => s.split('fillColumns').join('declaredCols')],
];
let controlsCaught = 0;
for (const [label, which, mutate] of CONTROLS) {
  let caught = false;
  let threw = null;
  try {
    const result = runChecks(await apiWith(which, mutate, label.replace(/\W+/g, '_')));
    caught = result.fail > base.fail;
  } catch (err) { caught = true; threw = err; }
  console.log(`  ${caught ? 'CAUGHT ' : 'escaped'} ${label}`
    + (threw ? `  ⛔ THREW: ${threw.message}` : ''));
  if (caught) controlsCaught++;
}

const failed = base.fail + escaped + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${MUTANTS.length - escaped}/${MUTANTS.length} defects caught, ${escaped} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail + MUTANTS.length + CONTROLS.length} ${failed}`);
process.exit(failed > 0 ? 1 : 0);
