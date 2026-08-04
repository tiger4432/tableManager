// Harness - the enrichment conveyor's queue arithmetic and its ordering rule.
// Run: node client2/tests/enrichment_queue_partition_harness.mjs
//
// WHY THIS EXISTS [N36, 2026-08-04].
//   `queue_filters` stopped demanding a non-blank decision key, so the progress bar's
//   numerator and denominator finally count ONE population (rows whose targets are
//   blank). The server half of that is scored by `server/tests/test_enrichment.py`.
//   What lands ONLY on the client is the consequence: blank-key rows now appear in
//   the worklist, they cannot be judged there, and the conveyor is consumed
//   front-first in row_id order - so without an ordering rule they sit at the head
//   and are hit over and over.
//
//   P1  A ROW WITHOUT ITS KEYS IS DEMOTED, NEVER DROPPED. `partitionQueueRows` puts
//       every keyed row ahead of every keyless one. Dropping them would be the defect
//       the user overruled; leaving them in place would wedge the conveyor.
//   P2  ROW_ID ORDER SURVIVES INSIDE EACH PARTITION. The conveyor's invariant is
//       "consume from the front"; this changes WHICH rows are at the front, not that
//       the server's order governs.
//   P3  BLANKNESS IS THE SHARED SPELLING. Every decision key must be non-blank, and
//       blank means null / undefined / '' / whitespace - the same fold the server's
//       `clean_str_value` applies. `.some` instead of `.every`, or a missing trim, and
//       a half-keyed row is treated as workable.
//   P4  "판단키 없음 N건" IS A MEASUREMENT, NOT A GUESS. It is remainder minus the
//       server's keyed total. When the server sends no keyed total (an older build),
//       the honest answer is to say nothing - NOT to render "0건", which is a claim.
//   P5  THE PROGRESS LABEL SAYS WHAT THE VALUE IS. Both sides are row counts, so the
//       unit is rows. "keys" was true only while `composite_key_source == decision_key`
//       on every live rule, which the loader does not require.
//
// EVERY CHECK IS PAIRED WITH A MUTANT, and the suite FAILS if a defect still passes -
// a check that cannot fail proves nothing. Two CONTROLS must ESCAPE; if a control is
// caught, some check is reading source text instead of behaviour.
//
// Exit codes: 0 = green | 1 = a check failed or a defect escaped | 2 = harness failure.
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'enrichment.js');

const die = (msg) => {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
};

if (!existsSync(SRC_PATH)) die(`no source at ${SRC_PATH}`);
const PRISTINE = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

// ── Extraction: anchored at a real declaration, never at a bare name ─────────────
function sliceBalanced(src, startIdx, open, close) {
  const i = src.indexOf(open, startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === open) depth++;
    else if (src[j] === close) { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}
function fn(src, name) {
  const m = new RegExp(`(?:export\\s+)?(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in enrichment.js - renamed or reshaped.`);
  const body = sliceBalanced(src, m.index, '{', '}');
  if (!body) die(`unbalanced braces for ${name}`);
  return body.replace(/^export\s+/, '');
}

const RULE = { decision_key: ['equipment', 'event_time'], target_fields: ['wafer_id'] };
const row = (id, equipment, event_time) => ({
  row_id: id,
  data: {
    equipment: { value: equipment, is_overwrite: false, priority_source: 'pipeline_parser' },
    event_time: { value: event_time, is_overwrite: false, priority_source: 'pipeline_parser' },
    wafer_id: { value: null, is_overwrite: false, priority_source: null },
  },
});

// Build a live scope out of the real function texts plus the minimum stubs the
// header renderer touches. Nothing here re-implements the logic under test.
function build(src) {
  const parts = ['cellVal', 'hasDecisionKeys', 'partitionQueueRows', 'updateHeaderStats']
    .map(n => fn(src, n)).join('\n\n');
  const els = new Map();
  const el = (id) => {
    if (!els.has(id)) els.set(id, { id, textContent: '', title: '', style: {},
      classList: { toggle() {}, add() {}, remove() {} } });
    return els.get(id);
  };
  const S = { rule: RULE, totalBlank: 0, totalAll: null, totalKeyed: null,
              blankKeyCount: 0, doneCount: 0 };
  // eslint-disable-next-line no-new-func
  const make = new Function('el', 'S', `${parts}\nreturn {cellVal, hasDecisionKeys, `
    + `partitionQueueRows, updateHeaderStats};`);
  return { api: make(el, S), S, el, els };
}

// ── Scoring ─────────────────────────────────────────────────────────────────────
let quiet = false;
function suite(src) {
  let pass = 0, fail = 0; const failed = [];
  const check = (name, actual, expected) => {
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a === e) { pass++; return; }
    fail++; failed.push(name);
    if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  };

  let ctx;
  try { ctx = build(src); }
  catch (e) { return { pass, fail: fail + 1, failed: [`build threw: ${e && e.message}`] }; }
  const { api, S, el } = ctx;

  // P1/P2 - demotion, and row_id order preserved inside each partition.
  const mixed = [row(1, '', 'T1'), row(2, 'EQP1', 'T2'), row(3, '', ''), row(4, 'EQP2', 'T4')];
  check('P1 keyed rows lead',
    api.partitionQueueRows(mixed, RULE).map(r => r.row_id), [2, 4, 1, 3]);
  check('P1 nothing is dropped', api.partitionQueueRows(mixed, RULE).length, 4);
  const allKeyed = [row(7, 'A', 'T'), row(8, 'B', 'T'), row(9, 'C', 'T')];
  check('P2 an all-keyed page is returned untouched',
    api.partitionQueueRows(allKeyed, RULE).map(r => r.row_id), [7, 8, 9]);
  check('P2 an all-keyless page keeps row_id order',
    api.partitionQueueRows([row(5, '', ''), row(6, '', '')], RULE).map(r => r.row_id), [5, 6]);

  // P3 - the shared blankness spelling.
  check('P3 both keys present', api.hasDecisionKeys(row(1, 'EQP1', 'T1'), RULE), true);
  check('P3 one key missing is NOT keyed', api.hasDecisionKeys(row(1, 'EQP1', ''), RULE), false);
  check('P3 whitespace is blank', api.hasDecisionKeys(row(1, 'EQP1', '   '), RULE), false);
  check('P3 null is blank', api.hasDecisionKeys(row(1, null, 'T1'), RULE), false);
  check('P3 undefined is blank', api.hasDecisionKeys(row(1, undefined, 'T1'), RULE), false);

  // P4 - the named aggregate is a measurement.
  S.totalAll = 10; S.totalBlank = 7; S.totalKeyed = 5;
  api.updateHeaderStats();
  check('P4 blank-key count = remainder - keyed', S.blankKeyCount, 2);
  check('P4 the badge names it', el('blankkey-badge').textContent, '⚠️ 판단키 없음 2건');
  check('P4 the badge is shown', el('blankkey-badge').style.display, 'inline-block');
  S.totalKeyed = 7;
  api.updateHeaderStats();
  check('P4 zero blank-key rows hides the badge', el('blankkey-badge').style.display, 'none');
  S.totalKeyed = null;              // older server: no keyed total at all
  api.updateHeaderStats();
  check('P4 an unknown keyed total claims nothing', S.blankKeyCount, 0);
  check('P4 and renders no badge', el('blankkey-badge').style.display, 'none');

  // P5 - the label states the unit the value actually carries.
  S.totalAll = 10; S.totalBlank = 4; S.totalKeyed = 4;
  api.updateHeaderStats();
  check('P5 progress is counted in rows', el('progress-text').textContent, '6 / 10 행');
  check('P5 percentage tracks the same two numbers', el('progress-percent').textContent, '60%');
  // The N36 shape itself: every row unanswered must read 0%, not 100%.
  S.totalAll = 2; S.totalBlank = 2; S.totalKeyed = 0;
  api.updateHeaderStats();
  check('P5 [N36] all-unanswered reads 0%', el('progress-percent').textContent, '0%');
  check('P5 [N36] and every one of them is named', S.blankKeyCount, 2);

  return { pass, fail, failed };
}

// ── Defects that must be CAUGHT ─────────────────────────────────────────────────
const DEFECTS = [
  ['no demotion (blank-key rows wedge the conveyor head)',
    s => s.replace('rows.forEach(r => (hasDecisionKeys(r, rule) ? keyed : keyless).push(r));\n  return keyed.concat(keyless);',
                   'rows.forEach(r => keyed.push(r));\n  return keyed.concat(keyless);')],
  ['partition reverses row_id order inside a partition',
    s => s.replace('return keyed.concat(keyless);', 'return keyed.reverse().concat(keyless);')],
  ['ANY key non-blank counts as keyed (.some for .every)',
    s => s.replace('(rule.decision_key || []).every(col =>', '(rule.decision_key || []).some(col =>')],
  ['whitespace key counts as keyed (no trim)',
    s => s.replace("String(cellVal(row, col)).trim() !== ''", "String(cellVal(row, col)) !== ''")],
  ['an unknown keyed total is rendered as a count',
    s => s.replace('S.blankKeyCount = (S.totalKeyed === null) ? 0 : Math.max(0, remaining - S.totalKeyed);',
                   'S.blankKeyCount = Math.max(0, remaining - (S.totalKeyed || 0));')],
  ['progress label claims keys again',
    s => s.replace('${S.totalAll.toLocaleString()} 행', '${S.totalAll.toLocaleString()} keys')],
  ['blank-key badge shown even at zero',
    s => s.replace("bkBadge.style.display = S.blankKeyCount > 0 ? 'inline-block' : 'none';",
                   "bkBadge.style.display = 'inline-block';")],
];

// ── Controls that must ESCAPE (else a check is reading source text) ─────────────
const CONTROLS = [
  ['local rename inside partitionQueueRows',
    s => s.replace('const keyed = [], keyless = [];', 'const aa = [], bb = [];')
          .replace('rows.forEach(r => (hasDecisionKeys(r, rule) ? keyed : keyless).push(r));',
                   'rows.forEach(r => (hasDecisionKeys(r, rule) ? aa : bb).push(r));')
          .replace('return keyed.concat(keyless);', 'return aa.concat(bb);')],
  ['comments stripped', s => s.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n')],
];

const base = suite(PRISTINE);
if (base.fail) console.error(`\nbaseline failures:\n  ${base.failed.join('\n  ')}`);

quiet = true;
let caught = 0; const escaped = [];
for (const [name, mutate] of DEFECTS) {
  const mutated = mutate(PRISTINE);
  if (mutated === PRISTINE) die(`defect "${name}" changed nothing - its anchor no longer matches. `
    + `An inert mutant is a check that cannot fail.`);
  let r;
  try { r = suite(mutated); } catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail > 0) caught++; else escaped.push(name);
}
let controlsCaught = 0; const controlsCaughtNames = [];
for (const [name, mutate] of CONTROLS) {
  const mutated = mutate(PRISTINE);
  if (mutated === PRISTINE) die(`control "${name}" changed nothing - it proves nothing.`);
  let r;
  try { r = suite(mutated); } catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail > 0) { controlsCaught++; controlsCaughtNames.push(`${name} (${r.failed[0]})`); }
}
quiet = false;

if (escaped.length) console.error(`\ndefects that escaped:\n  ${escaped.join('\n  ')}`);
if (controlsCaughtNames.length) {
  console.error(`\ncontrols that were caught (a check is reading source text):\n  `
    + controlsCaughtNames.join('\n  '));
}

const bad = base.fail + escaped.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects `
  + `caught, ${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} `
  + `controls escaped.`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
