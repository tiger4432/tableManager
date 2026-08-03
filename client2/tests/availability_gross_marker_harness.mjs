// Harness — the 가용/잔여 cells when the server says a subtraction was never declared.
//
// WHY THIS EXISTS. Server `2c2a777` relaxed the bonding plan's material gating: where a site
// does not declare `transfer_log` / `origin_log` / `fail_sources` / `process_history`, the
// availability is now computed WITHOUT those subtractions and served as a real number instead
// of being demoted. To keep that honest the server emits an optional `inactive_subtractions`
// list. QA measured the client half: the field had ZERO readers, so a gross number rendered
// as a bold bare number — presentationally IDENTICAL to a fully-subtracted one.
// Run: node client2/tests/availability_gross_marker_harness.mjs   (no node_modules — vm sandbox)
//
// WHAT IT SCORES. The REAL `availabilityOfPool` / `availCellHtml` / `remainingCellHtml` /
// `inactiveSubtractionsOf` / `grossRolesOf` / `grossNoteHtml` (transfer_plan.js) and the REAL
// `remainingState` (doe_bands.js), lifted verbatim out of the source and evaluated in a vm
// sandbox — the same technique as `virtual_column_render_harness.mjs`, and for the same
// reason: `transfer_plan.js` imports `config.js`, which touches `window` at module scope.
//
// THE PAIR IS THE POINT. Every render check runs TWICE against payloads that are identical
// except for the presence of `inactive_subtractions`:
//   absent  -> the output must equal a LITERAL string recorded from the pre-change render.
//              A fully-declared site must see no change whatsoever, byte for byte.
//   present -> a marker must appear AND the server's own role spellings must be legible.
// A harness that only fixtured the present path could not tell a marker from a regression.
//
// THE FIXTURE ACTIVATES THE DEFECT AXES. `remaining` differs per BIN (8 vs 3) so picking the
// wrong entry shows; `used` is non-zero (3) so 잔여 != 가용; the inactive list has THREE
// entries in a non-alphabetical order (`transfer_log, origin_log, fail_sources`) so both a
// dropped name and a sort are visible; and one fixture carries `transfer_untracked` AND
// `inactive_subtractions` together, because `≤` and `*` are different claims that can be
// true at the same time and must not collapse into one another.
//
// EXTRACTION ANCHORS ARE THE ONE PLACE SOURCE TEXT IS READ, and this file exits 2 — loudly,
// not green — when one stops matching. A harness that goes quiet because it lost the code is
// worse than no harness.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC = join(ROOT, 'client2', 'src');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

const read = f => readFileSync(join(SRC, f), 'utf8').replace(/\r\n/g, '\n');
const PRISTINE = { tp: read('transfer_plan.js'), doe: read('doe_bands.js') };

// ── extraction ──────────────────────────────────────────────────────────────────

function balanced(src, from, open, close) {
  const i = src.indexOf(open, from);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === open) depth++;
    else if (src[j] === close) { depth--; if (depth === 0) return { start: i, end: j }; }
  }
  return null;
}

function fnFrom(src, label, name) {
  const m = new RegExp(`(?:export\\s+)?(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in ${label}`);
  const b = balanced(src, m.index, '{', '}');
  if (!b) die(`unbalanced braces for ${name} in ${label}`);
  return src.slice(m.index, b.end + 1).replace(/^export\s+/, '');
}

function constFrom(src, label, name) {
  const m = new RegExp(`(?:export\\s+)?const\\s+${name}\\s*=`).exec(src);
  if (!m) die(`const ${name} not found in ${label}`);
  let depth = 0;
  for (let j = m.index; j < src.length; j++) {
    const ch = src[j];
    if (ch === '[' || ch === '{' || ch === '(') depth++;
    else if (ch === ']' || ch === '}' || ch === ')') depth--;
    else if (ch === ';' && depth === 0) return src.slice(m.index, j + 1).replace(/^export\s+/, '');
    else if (ch === '`') {   // skip template literals whole — they hold `;` and braces
      const end = src.indexOf('`', j + 1);
      if (end < 0) die(`unterminated template in const ${name} (${label})`);
      j = end;
    }
  }
  die(`no terminator for const ${name} in ${label}`);
}

const TP_FNS = ['esc', 'summaryKeyFor', 'availabilityOfPool', 'untrackedBoundOf', 'boundText',
  'inactiveSubtractionsOf', 'grossReason', 'isGross', 'grossRolesOf', 'grossNoteHtml',
  'unknownCellHtml', 'availCellHtml', 'remainingCellHtml', 'remainingIsNegative'];

function build(sources) {
  const parts = [
    constFrom(sources.doe, 'doe_bands.js', 'REMAINING_UNKNOWN_REASON'),
    fnFrom(sources.doe, 'doe_bands.js', 'remainingState'),
    constFrom(sources.tp, 'transfer_plan.js', 'UNTRACKED_REASON'),
    constFrom(sources.tp, 'transfer_plan.js', 'GROSS_MARK'),
    ...TP_FNS.map(n => fnFrom(sources.tp, 'transfer_plan.js', n)),
  ];
  // The two stubs are the module's environment, not its logic: `S.summaries` is the fetch
  // cache the harness fills with server payloads, and `stageOfTable` only supplies the cache
  // key prefix. Nothing under test is re-typed here.
  const prelude = `
const S = { summaries: new Map(), ctx: { table: 'dt_map' } };
function stageOfTable() { return { id: 'S1' }; }
`;
  const epilogue = `
const __api = { S, availabilityOfPool, availCellHtml, remainingCellHtml, remainingIsNegative,
  inactiveSubtractionsOf, grossRolesOf, grossNoteHtml, grossReason, isGross,
  esc, UNTRACKED_REASON, GROSS_MARK, remainingState };
`;
  const ctx = vm.createContext({ Number, Array, String, Math, JSON, Map, Set, console });
  try {
    vm.runInContext(prelude + parts.join('\n') + epilogue + '\n__api;', ctx,
      { filename: 'availability_slice.js' });
  } catch (e) { die(`sliced source does not evaluate: ${e && e.message}`); }
  return vm.runInContext('__api', ctx);
}

// ── fixtures ────────────────────────────────────────────────────────────────────
//
// The server's own spelling, in the server's own order. Not alphabetical, and never
// translated: the operator has to find these tokens in `transfer_plan_config.json`, and a
// second client-side spelling would send them looking for a key that does not exist.
const INACTIVE = ['transfer_log', 'origin_log', 'fail_sources'];

const ENTRIES = [
  { bin: 1, remaining: 8, reliable: true },
  { bin: 2, remaining: 3, reliable: true },   // a second, DIFFERENT number on the same map
];
const bins = entries => ({ axis: 'connected', entries });

// A fully-declared site. `remaining_reliable: true` — the same value the relaxed path now
// carries, which is exactly why nothing here may key off it.
const SUM_DECLARED = { remaining_reliable: true, warnings: [], bins: bins(ENTRIES) };
// The relaxed site: byte-for-byte the same numbers, plus the one optional field.
const SUM_RELAXED = { ...SUM_DECLARED, inactive_subtractions: INACTIVE };

// `≤` and `*` at once: `transfer_log` is DECLARED as "none" (so the server sets a real upper
// bound) while `origin_log`/`fail_sources` were never declared at all.
const UB_ENTRY = { bin: 1, remaining: 12, reliable: true,
  transfer_untracked: true, remaining_upper_bound: 12 };
const SUM_BOUND = { remaining_reliable: true, warnings: [], bins: bins([UB_ENTRY]) };
const SUM_BOUND_RELAXED = { ...SUM_BOUND, inactive_subtractions: ['origin_log', 'fail_sources'] };

// A relaxed site that still cannot produce a number for this BIN.
const SUM_RELAXED_NULL = { remaining_reliable: true, warnings: [],
  bins: bins([{ bin: 1, remaining: null, reliable: true }]),
  inactive_subtractions: ['transfer_log'] };

const POOL = { key: 'P1', lot: 'L1', slot: '01', bin: 1, scope: 'slot' };
const POOL2 = { key: 'P2', lot: 'L1', slot: '01', bin: 2, scope: 'slot' };
const USED = 3;   // non-zero, so 잔여 (5) is a different number from 가용 (8)

// ── the pre-change render, recorded literally ───────────────────────────────────
// These are what the screen printed BEFORE this change. The absent-field path must still
// produce them character for character.
const WAS_AVAIL = '<b>8</b>';
const WAS_LEFT = '<span class="ap">≈</span>5';
const WAS_AVAIL_BIN2 = '<b>3</b>';

function seed(api, pool, payload) {
  api.S.summaries.set(`S1::${pool.key}`, { status: 'ok', data: payload });
}

function suite(sources) {
  const api = build(sources);
  let pass = 0, fail = 0;
  const failed = [];
  const ok = (name, cond, detail) => {
    if (cond) pass++;
    else { fail++; failed.push(`${name}${detail === undefined ? '' : ` — ${detail}`}`); }
  };
  const eq = (name, got, want) => ok(name, got === want, `got ${JSON.stringify(got)} want ${JSON.stringify(want)}`);

  // ── PATH A: field ABSENT. Byte-identical to today. ────────────────────────────
  seed(api, POOL, SUM_DECLARED);
  seed(api, POOL2, SUM_DECLARED);
  const avA = api.availabilityOfPool(POOL);
  const avA2 = api.availabilityOfPool(POOL2);
  eq('A/avail cell is the pre-change string', api.availCellHtml(avA), WAS_AVAIL);
  eq('A/avail cell for the other BIN is the pre-change string', api.availCellHtml(avA2), WAS_AVAIL_BIN2);
  eq('A/remaining cell is the pre-change string', api.remainingCellHtml(avA, USED), WAS_LEFT);
  ok('A/inactive is an empty array, never undefined',
    Array.isArray(avA.inactive) && avA.inactive.length === 0, JSON.stringify(avA.inactive));
  ok('A/footnote adds nothing', api.grossNoteHtml(api.grossRolesOf([avA, avA2])) === '');
  ok('A/no marker anywhere', !api.availCellHtml(avA).includes(api.GROSS_MARK)
    && !api.remainingCellHtml(avA, USED).includes(api.GROSS_MARK));

  // ── PATH B: field PRESENT. Same numbers, marked. ──────────────────────────────
  seed(api, POOL, SUM_RELAXED);
  seed(api, POOL2, SUM_RELAXED);
  const avB = api.availabilityOfPool(POOL);
  const avB2 = api.availabilityOfPool(POOL2);
  const cellB = api.availCellHtml(avB);
  const leftB = api.remainingCellHtml(avB, USED);

  ok('B/the number itself is unchanged', avB.value === 8 && cellB.includes('>8<'), cellB);
  ok('B/avail carries the marker', cellB.includes(api.GROSS_MARK), cellB);
  ok('B/remaining carries the marker too', leftB.includes(api.GROSS_MARK), leftB);
  ok('B/remaining still shows the derived number', leftB.includes('>5<') || leftB.includes('≈</span>5'), leftB);
  ok('B/the marker is NOT the ≤ convention', api.GROSS_MARK !== '≤' && !cellB.includes('≤'), cellB);
  ok('B/nothing is demoted to 미상', !cellB.includes('미상') && !leftB.includes('미상'));

  // The vocabulary is the server's. Every role it named must be legible, verbatim, in the
  // hover text of BOTH cells — the client never invents a second spelling.
  INACTIVE.forEach(role => {
    ok(`B/avail tooltip names ${role} verbatim`, cellB.includes(role), cellB);
    ok(`B/remaining tooltip names ${role} verbatim`, leftB.includes(role), leftB);
  });

  // The readable half: the footnote, at body size, in the server's order.
  const note = api.grossNoteHtml(api.grossRolesOf([avB, avB2]));
  ok('B/footnote is emitted', note !== '');
  INACTIVE.forEach(role => ok(`B/footnote names ${role} verbatim`, note.includes(role), note));
  ok('B/footnote keeps the server order',
    note.indexOf('transfer_log') < note.indexOf('origin_log')
    && note.indexOf('origin_log') < note.indexOf('fail_sources'), note);
  ok('B/footnote points at the same mark the cell uses', note.includes(api.GROSS_MARK));
  ok('B/footnote says the real remainder can be smaller', note.includes('적을 수 있습니다'), note);

  // 🔴 The rendering must NOT be tied to the reliability axis. After the relaxation the
  // server calls this number reliable, and it means it.
  ok('B/server still calls it reliable', avB.reliable === true);
  ok('B/marked even though reliable is true', api.isGross(avB) === true);

  // The union is ONE implementation (footnote and toast read the same list).
  const union = api.grossRolesOf([avB, avB2, avA]);
  eq('B/union deduplicates across pools', union.length, 3);
  eq('B/union is the server list in order', union.join(','), INACTIVE.join(','));

  // ── PATH C: ≤ and * are different claims and both can be true ─────────────────
  seed(api, POOL, SUM_BOUND);
  const avC0 = api.availabilityOfPool(POOL);
  const cellC0 = api.availCellHtml(avC0);
  eq('C/declared-untracked without relaxation is the pre-change ≤ render',
    cellC0, `<b class="tp-bound" title="${api.esc(api.UNTRACKED_REASON)}">≤12</b>`);

  seed(api, POOL, SUM_BOUND_RELAXED);
  const avC = api.availabilityOfPool(POOL);
  const cellC = api.availCellHtml(avC);
  ok('C/≤ survives when a subtraction is also inactive', cellC.includes('≤12'), cellC);
  ok('C/and the marker is added, not substituted', cellC.includes(api.GROSS_MARK), cellC);
  ok('C/the marker names the inactive roles, not the untracked one',
    cellC.includes('origin_log') && cellC.includes('fail_sources'), cellC);
  ok('C/remaining keeps both', api.remainingCellHtml(avC, USED).includes('≤9')
    && api.remainingCellHtml(avC, USED).includes(api.GROSS_MARK));

  // ── PATH D: null-safety. A relaxed path that has no number must not print one. ─
  seed(api, POOL, SUM_RELAXED_NULL);
  const avD = api.availabilityOfPool(POOL);
  const cellD = api.availCellHtml(avD);
  const leftD = api.remainingCellHtml(avD, USED);
  eq('D/null remaining stays null', avD.value, null);
  ok('D/null renders 미상, never 0', cellD.includes('미상') && !/>0</.test(cellD), cellD);
  ok('D/no "null" or "NaN" reaches the screen',
    !/null|NaN|undefined/.test(cellD + leftD), cellD + ' | ' + leftD);
  ok('D/remaining of an unknown avail is also 미상', leftD.includes('미상'), leftD);
  ok('D/remainingState never coerces a null availability to 0',
    api.remainingState({ status: 'ok', value: null, reliable: true }, 3).value === null);
  ok('D/remainingState never coerces a null availability into a shortage',
    api.remainingState({ status: 'ok', value: null, reliable: true }, 3).reliable === false);

  // ── PATH E: a malformed field must not invent, crash, or leak ─────────────────
  eq('E/a string field yields no roles', api.inactiveSubtractionsOf({ inactive_subtractions: 'transfer_log' }).length, 0);
  eq('E/an object field yields no roles', api.inactiveSubtractionsOf({ inactive_subtractions: { a: 1 } }).length, 0);
  eq('E/a missing field yields no roles', api.inactiveSubtractionsOf({}).length, 0);
  eq('E/blank and null entries are dropped',
    api.inactiveSubtractionsOf({ inactive_subtractions: ['transfer_log', '', null, '  origin_log  '] }).join(','),
    'transfer_log,origin_log');
  ok('E/no role name is invented',
    api.inactiveSubtractionsOf({ inactive_subtractions: [] }).length === 0);
  ok('E/html in a role name is escaped in the footnote',
    !api.grossNoteHtml(['<img>']).includes('<img>'), api.grossNoteHtml(['<img>']));

  // ── PATH F: the shortage highlight is unchanged (no false alarm, no new red) ───
  seed(api, POOL, SUM_RELAXED);
  const avF = api.availabilityOfPool(POOL);
  ok('F/a positive gross remainder is not painted red', api.remainingIsNegative(avF, 3) === false);
  ok('F/a negative gross remainder still is', api.remainingIsNegative(avF, 99) === true);

  return { pass, fail, failed };
}

// ── mutants ─────────────────────────────────────────────────────────────────────

function sub(src, from, to, tag) {
  if (!src.includes(from)) die(`mutant anchor '${tag}' no longer matches`);
  return src.replace(from, to);
}

const DEFECTS = [
  ['stop reading the field at all', s => ({ ...s,
    tp: sub(s.tp, `  const raw = data && data.inactive_subtractions;`,
      `  const raw = null;`, 'no-read') })],
  ['tie the marker to the reliability axis', s => ({ ...s,
    tp: sub(s.tp, `  return !!(av && Array.isArray(av.inactive) && av.inactive.length > 0);`,
      `  return !!(av && Array.isArray(av.inactive) && av.inactive.length > 0 && av.reliable !== true);`,
      'tied-to-reliable') })],
  ['borrow the ≤ convention', s => ({ ...s,
    tp: sub(s.tp, `const GROSS_MARK = '*';`, `const GROSS_MARK = '≤';`, 'borrow-le') })],
  ['mark 가용 but leave 잔여 bare', s => ({ ...s,
    tp: sub(s.tp, `function remainingCellHtml(av, used) {\n  const gross = isGross(av);`,
      `function remainingCellHtml(av, used) {\n  const gross = false;`, 'left-bare') })],
  ['mark the fully-declared path too', s => ({ ...s,
    tp: sub(s.tp, `  return !!(av && Array.isArray(av.inactive) && av.inactive.length > 0);`,
      `  return !!(av && Array.isArray(av.inactive));`, 'mark-everything') })],
  ['let a non-array field through', s => ({ ...s,
    tp: sub(s.tp, `  if (!Array.isArray(raw)) return [];`, `  if (raw == null) return [];`,
      'non-array') })],
  ['keep blank entries as roles', s => ({ ...s,
    tp: sub(s.tp, `.filter(r => r !== '');`, `;`, 'blank-roles') })],
  ['sort the union', s => ({ ...s,
    tp: sub(s.tp, `  return out;\n}\n\n// ②의 각주`, `  return out.sort();\n}\n\n// ②의 각주`, 'sorted') })],
  ['stop deduplicating the union', s => ({ ...s,
    tp: sub(s.tp, `av.inactive.forEach(r => { if (!out.includes(r)) out.push(r); });`,
      `av.inactive.forEach(r => out.push(r));`, 'dupes') })],
  ['emit the footnote for a fully-declared site', s => ({ ...s,
    tp: sub(s.tp, `  if (!grossRoles || grossRoles.length === 0) return '';`, ``, 'always-note') })],
  ['drop the role names from the footnote', s => ({ ...s,
    tp: sub(s.tp, '${\n          grossRoles.map(r => `<code class="tp-gross-role">${esc(r)}</code>`).join(\' · \')}',
      '${grossRoles.length}종', 'nameless-note') })],
  ['drop the role names from the cell tooltip', s => ({ ...s,
    tp: sub(s.tp, `이 사이트가 선언하지 않아 집계에서 빠진 감산: \${\n    inactive.join(', ')}.`,
      `이 사이트가 선언하지 않아 집계에서 빠진 감산이 있습니다.`, 'nameless-tip') })],
  ['stop escaping a role name into the footnote', s => ({ ...s,
    tp: sub(s.tp, '`<code class="tp-gross-role">${esc(r)}</code>`',
      '`<code class="tp-gross-role">${r}</code>`', 'unescaped') })],
  ['coerce a null remaining to 0', s => ({ ...s,
    tp: sub(s.tp, `    value: (hit.remaining === null || hit.remaining === undefined) ? null : Number(hit.remaining),`,
      `    value: Number(hit.remaining || 0),`, 'null-to-zero') })],
  ['let the ≤ branch swallow the marker', s => ({ ...s,
    tp: sub(s.tp, '${boundText(av.bound)}</b>${mark}`', '${boundText(av.bound)}</b>`', 'bound-swallow') })],
  ['drop inactive from the ok branch of the interpreter', s => ({ ...s,
    tp: sub(s.tp, `    bound,\n    inactive,\n    reason:`, `    bound,\n    inactive: [],\n    reason:`,
      'ok-branch') })],
  ['paint a positive gross remainder red', s => ({ ...s,
    tp: sub(s.tp, `  const rem = remainingState(av, used);\n  return rem.reliable && rem.value < 0;`,
      `  const rem = remainingState(av, used);\n  return rem.reliable && (rem.value < 0 || isGross(av));`,
      'false-alarm') })],
];

// CONTROLS: each must ESCAPE. If one is caught, a check is reading source text rather than
// behaviour. Locals only, and deliberately NOT the names this file extracts by.
const RENAMES = [
  [/\bhit\b/g, 'binEntry'], [/\bblock\b/g, 'axisBlock'], [/\bdegraded\b/g, 'demoted'],
  [/\bmark\b/g, 'footMark'], [/\bgross\b/g, 'untotalled'], [/\braw\b/g, 'declared'],
];
const stripComments = src => src.split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n');

const CONTROLS = [
  ['consistent rename of locals across both sliced modules', s => {
    const r = t => RENAMES.reduce((acc, [re, to]) => acc.replace(re, to), t);
    return { tp: r(s.tp), doe: r(s.doe) };
  }],
  ['every full-line comment stripped from both sliced modules', s => ({
    tp: stripComments(s.tp), doe: stripComments(s.doe) })],
];

// ── run ─────────────────────────────────────────────────────────────────────────

const base = suite(PRISTINE);
console.log(`[baseline] ${base.pass} passed, ${base.fail} failed`);
if (base.failed.length) console.error(`  ${base.failed.join('\n  ')}`);

let caught = 0, escaped = 0;
const escapedNames = [];
console.log(`\n── defect mutants (each must be CAUGHT) ────────────────────────────`);
for (const [name, mutate] of DEFECTS) {
  let r;
  try { r = suite(mutate(PRISTINE)); }
  catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}  (${r.failed[0]})`); }
  else { escaped++; escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
const controlsCaughtNames = [];
console.log(`\n── control mutants (each must ESCAPE) ──────────────────────────────`);
for (const [name, mutate] of CONTROLS) {
  let r;
  try { r = suite(mutate(PRISTINE)); }
  catch (e) { r = { fail: 1, failed: [`threw: ${e && e.message}`] }; }
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; controlsCaughtNames.push(`${name} (${r.failed[0]})`); console.log(`  CAUGHT  ${name}  (${r.failed[0]})`); }
}

if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);
if (controlsCaughtNames.length) console.error(`\ncontrols that were caught (a check is reading source text):\n  ${controlsCaughtNames.join('\n  ')}`);

const bad = base.fail + escaped + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; `
  + `${caught}/${DEFECTS.length} defects caught, ${escaped} escaped; `
  + `${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
