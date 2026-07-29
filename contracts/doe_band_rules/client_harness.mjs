/**
 * Runs the CLIENT's DOE ZONE model against contracts/doe_band_rules/vectors.json.
 *
 * What it pins: the five blocking rules V1-V5, the zone geometry every one of them stands
 * on, the material token grammar, the demand arithmetic, and - the group that matters most
 * to the user - the EXCEL ROUND TRIP (paste TSV -> model -> copy TSV -> identical).
 *
 * Read-only: it never writes to client2/. The modules cannot simply be imported here -
 * `doe_bands.js` imports `./transfer_plan.js`, which imports `./config.js`, which reads
 * `window.location` at module scope. So this slices the named function declarations out of
 * the source TEXT and evaluates them in a vm sandbox. `bandToState` and `prevTo` are
 * extracted from transfer_plan.js rather than re-typed: they are the SINGLE integer
 * classifier and the SINGLE legacy walk, and a harness carrying its own copies would
 * happily pass while the app disagreed with it.
 *
 * FAILS LOUDLY on extraction problems (exit 2). A harness that silently passes when it can
 * no longer find the functions is worse than no harness, because its green result gets
 * cited as evidence.
 *
 * Exit codes: 0 = client matches the contract | 1 = divergence(s) | 2 = harness failure.
 *
 *   node contracts/doe_band_rules/client_harness.mjs
 *   node contracts/doe_band_rules/client_harness.mjs --json
 */
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const VECTORS = join(HERE, 'vectors.json');
const SRC_PLAN = join(ROOT, 'client2', 'src', 'transfer_plan.js');
const SRC_ZONES = join(ROOT, 'client2', 'src', 'doe_bands.js');
const SRC_TSV = join(ROOT, 'client2', 'src', 'tsv.js');
const JSON_OUT = process.argv.includes('--json');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

function extractFunction(source, name, file) {
  const decl = new RegExp(`(^|\\n)\\s*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) die(`could not extract function '${name}' from ${file} - it was renamed, removed, or reshaped. Update this harness deliberately; do not delete the check.`);
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = source.indexOf('{', m.index + m[0].length - 1);
  if (i < 0) die(`found '${name}' in ${file} but no body`);
  let depth = 0;
  for (; i < source.length; i++) {
    const c = source[i];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return source.slice(start, i + 1); }
  }
  die(`unbalanced braces while extracting '${name}' from ${file}`);
}

/** Slice a multi-line `const NAME = { ... };` / `[ ... ];` out of source by matching. */
function extractBracketed(source, name, open, close, file) {
  const m = new RegExp(`(^|\\n)\\s*const\\s+${name}\\s*=\\s*\\${open}`).exec(source);
  if (!m) die(`could not extract const '${name}' from ${file}`);
  const from = source.indexOf(open, m.index);
  let i = from, depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === open) depth++;
    else if (source[i] === close) { depth--; if (depth === 0) return `const ${name} = ${source.slice(from, i + 1)};`; }
  }
  die(`unbalanced ${open}${close} in '${name}'`);
}

function extractConst(source, name, file) {
  const m = new RegExp(`(^|\\n)\\s*const\\s+${name}\\s*=[^\\n]*`).exec(source);
  if (!m) die(`could not extract const '${name}' from ${file}`);
  return m[0];
}

const planSrc = readFileSync(SRC_PLAN, 'utf8');
const zoneSrc = readFileSync(SRC_ZONES, 'utf8');
const tsvSrc = readFileSync(SRC_TSV, 'utf8');

// ── THE SINGLE-READER GATES. Asserted before anything is compared, because every
//    comparison below is meaningless if the app is running a different parser than the one
//    this file extracts.
if (!/import\s*\{[^}]*\bbandToState\b[^}]*\}\s*from\s*['"]\.\/transfer_plan\.js['"]/.test(zoneSrc)) {
  die("doe_bands.js no longer imports `bandToState` from ./transfer_plan.js. Either the integer classifier was duplicated (which is the defect this contract exists to prevent) or the import was reshaped. Resolve deliberately.");
}
if (!/import\s*\{[^}]*\bprevTo\b[^}]*\}\s*from\s*['"]\.\/transfer_plan\.js['"]/.test(zoneSrc)) {
  die("doe_bands.js no longer imports `prevTo`. The legacy band walk that `bandsToZones` needs is pinned by contracts/band_arithmetic and must not be re-typed here - two implementations of 'the previous band's to' is exactly the divergence that file exists to prevent.");
}
// The panel must not have grown its own TSV reader beside the shared one.
if (!/import\s*\{[^}]*\bparseTsv\b[^}]*\}\s*from\s*['"]\.\/tsv\.js['"]/.test(planSrc)) {
  die("transfer_plan.js no longer imports `parseTsv` from ./tsv.js. A second clipboard implementation is how this project got a Ctrl+C that did nothing on the intranet.");
}
// And neither must the grid.
{
  const clipSrc = readFileSync(join(ROOT, 'client2', 'src', 'clipboard.js'), 'utf8');
  if (!/import\s*\{[^}]*\bparseTsv\b[^}]*\}\s*from\s*['"]\.\/tsv\.js['"]/.test(clipSrc)) {
    die("clipboard.js no longer imports `parseTsv` from ./tsv.js - the grid and the DOE panel would be reading Excel differently.");
  }
  // Comments are stripped first: these files DOCUMENT the prohibition, and a check that
  // fired on its own warning would have to be deleted to get a green run - which is how a
  // guard gets removed for the wrong reason.
  const stripComments = s => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1');
  for (const [file, s] of [['clipboard.js', clipSrc], ['transfer_plan.js', planSrc], ['tsv.js', tsvSrc]]) {
    if (/navigator\s*\.\s*clipboard/.test(stripComments(s))) {
      die(`\`navigator.clipboard\` is CALLED in ${file}. Production is plain-HTTP LAN - a non-secure context - where it is undefined. Everything must go through \`e.clipboardData\` on the native event.`);
    }
  }
}
// 🔴 THE RETIRED WRITER. `bands` is read-only now; a new writer would put the plan in two
//    places at once and `replace_map` would let them erase each other.
{
  const editorSrc = readFileSync(join(ROOT, 'client2', 'src', 'map_editor.js'), 'utf8');
  if (/\bfunction\s+serializeBands\s*\(/.test(editorSrc)) {
    die("map_editor.js has a `serializeBands` again. `map_split_registry.bands` is RETIRED (product_tables.py: 'Do not add a new writer') - it may be read for migration and never written.");
  }
  if (!/\bLEGEND_PAYLOAD_COLUMNS\b/.test(editorSrc)) {
    die("map_editor.js lost `LEGEND_PAYLOAD_COLUMNS`. That one list is what makes the write payload, the concurrency fingerprint and `legendRowSignature` cover the same fields - split them apart and an edit to a column that is saved but not signed is silently dropped from the save that was supposed to carry it.");
  }
}

const NEEDED_ZONES = [
  'boundState', 'stackState', 'midZone', 'zoneLayers', 'zoneLabel', 'formatLayerRuns',
  'parseMaterialList', 'serializeMaterialList',
  'parseMaterialToken', 'materialPoolKey',
  'validateZonePlan', 'zoneDemand', 'materialRollupRows', 'remainingState',
  'columnIdByHeader', 'looksLikeHeader', 'leadingBlankColumnDropped', 'mapPastedGrid',
  'planRowToRecord', 'planToGrid', 'bandsToZones',
];
const NEEDED_TSV = ['normalizeNewlines', 'parseTsv', 'needsQuote', 'quoteField', 'serializeTsv'];

const sandbox = { console };
vm.createContext(sandbox);
try {
  vm.runInContext([
    extractFunction(planSrc, 'bandToState', 'transfer_plan.js'),
    extractFunction(planSrc, 'prevTo', 'transfer_plan.js'),
    extractConst(tsvSrc, 'QUOTE', 'tsv.js'),
    extractConst(tsvSrc, 'TAB', 'tsv.js'),
    ...NEEDED_TSV.map(n => extractFunction(tsvSrc, n, 'tsv.js')),
    extractBracketed(zoneSrc, 'ZONES', '[', ']', 'doe_bands.js'),
    extractBracketed(zoneSrc, 'ZONE_LABEL', '{', '}', 'doe_bands.js'),
    extractBracketed(zoneSrc, 'DOE_COLUMNS', '[', ']', 'doe_bands.js'),
    extractBracketed(zoneSrc, 'IGNORED_HEADERS', '[', ']', 'doe_bands.js'),
    extractBracketed(zoneSrc, 'ROLLUP_COLUMNS', '[', ']', 'doe_bands.js'),
    extractBracketed(zoneSrc, 'REMAINING_UNKNOWN_REASON', '{', '}', 'doe_bands.js'),
    ...NEEDED_ZONES.map(n => extractFunction(zoneSrc, n, 'doe_bands.js')),
  ].join('\n'), sandbox);
} catch (e) {
  die(`extracted sources did not evaluate: ${e && e.message}`);
}
for (const fn of ['bandToState', 'prevTo', ...NEEDED_TSV, ...NEEDED_ZONES]) {
  if (typeof sandbox[fn] !== 'function') die(`'${fn}' did not evaluate to a function`);
}
// `const` bindings in a vm script are not properties of the sandbox object, so the zone
// list is fetched by evaluating its name. Taken from the source, never re-typed here: a
// harness that carried its own zone list would keep passing after a zone was added.
const ZONES = vm.runInContext('ZONES', sandbox);
if (!Array.isArray(ZONES) || ZONES.length !== 3) die(`ZONES did not evaluate to a 3-element array (got ${JSON.stringify(ZONES)})`);

const spec = JSON.parse(readFileSync(VECTORS, 'utf8'));
const failures = [];
let compared = 0;
const rec = (group, name, field, expected, actual) => {
  compared++;
  if (JSON.stringify(expected) !== JSON.stringify(actual)) failures.push({ group, name, field, expected, actual });
};
const ruleSet = list => [...new Set((list || []).map(x => x.rule))].sort();
const CONSUMED = new Set();
// Contract keys that are NOT `*_cases` groups - the ignore roster is a set, not a case list.
// Tracked separately because the `*_cases` gate below compares against `_cases` keys only,
// and a key that neither gate covers is precisely how an axis goes quiet.
const CONSUMED_OTHER = new Set();

// ── stack: the 3-state height ---------------------------------------------------------
CONSUMED.add('stack_cases');
for (const c of spec.stack_cases) {
  if (!c.name) continue;
  let st;
  try { st = sandbox.stackState({ stack: c.stack }); } catch (e) { st = { state: `THREW ${e.message}` }; }
  rec('stack', c.name, 'state', c.state, st.state);
  rec('stack', c.name, 'value', c.value, st.value);
}

// ── zone geometry ---------------------------------------------------------------------
// Guard against an inert fixture. If every row carried all three zones, the `has1H ? 2 : 1`
// and `hasTop ? STACK-1 : STACK` branches would never be exercised and this whole group
// would prove nothing about the one formula it exists to pin.
CONSUMED.add('zone_extent_cases');
{
  const rows = spec.zone_extent_cases.filter(c => c.row).map(c => c.row);
  const no1h = rows.filter(r => (r.mat_1h || []).length === 0).length;
  const noTop = rows.filter(r => (r.mat_top || []).length === 0).length;
  if (no1h === 0 || noTop === 0) {
    die(`fixture is inert: ${no1h} rows without 1H and ${noTop} without TOP. Both must be non-zero or the MID extent formula is only ever evaluated on one branch.`);
  }
}
for (const c of spec.zone_extent_cases) {
  if (!c.row) continue;
  let z;
  try { z = sandbox.midZone(c.row); } catch (e) { z = `THREW ${e.message}`; }
  rec('zone', c.name, 'mid extent', c.mid, z);
  for (const [zone, expect] of Object.entries(c.layers)) {
    let got;
    try { got = sandbox.zoneLayers(c.row, zone); } catch (e) { got = `THREW ${e.message}`; }
    if (expect === null) {
      // 🔴 null (cannot be computed) must never look like [] (covers no layers).
      rec('zone', c.name, `${zone} is null, not []`, 'null', got === null ? 'null' : JSON.stringify(got));
    } else if (expect.length === 0) {
      rec('zone', c.name, `${zone} is [] (a real, empty extent)`, '[]', JSON.stringify(got));
    } else {
      const [first, last, len] = expect;
      rec('zone', c.name, `${zone} first/last/length`, [first, last, len],
        Array.isArray(got) ? [got[0], got[got.length - 1], got.length] : got);
    }
  }
}

// ── blocking rules ---------------------------------------------------------------------
CONSUMED.add('plan_cases');
{
  // The conditional-V1 pair is the only thing that separates a correct implementation from
  // an unconditional `MID required`. If either half vanishes, this file stops proving it.
  const pass = spec.plan_cases.some(c => c.name === 'empty_mid_zone_passes_with_no_mid');
  const block = spec.plan_cases.some(c => c.name === 'non_empty_mid_zone_with_no_mid_blocks');
  if (!pass || !block) die('fixture is inert: V1 needs BOTH an empty-MID-zone pass and a non-empty-MID-zone block. With only one of them an unconditional rule passes every case.');
  const dt = spec.plan_cases.some(c => c.name === 'dt_map_plan_is_silent');
  if (!dt) die('fixture is inert: the dt_map degenerate case (STACK 1, MID only) must be pinned as SILENT, or a validator that nags at it would pass.');
  // The marker (STACK 0) axis needs the same pair: a bare marker pinned SILENT and a
  // marker-with-content pinned V6. With only one half, either "0 is still invalid" or
  // "V6 never fires" passes every remaining case.
  const markerPass = spec.plan_cases.some(c => c.name === 'marker_row_alone_is_silent');
  const markerV6 = spec.plan_cases.some(c => c.name === 'marker_with_zone_content_reports_the_contradiction');
  if (!markerPass || !markerV6) die('fixture is inert: the marker axis needs BOTH a silent bare-marker case and a V6 contradiction case.');
}
for (const c of spec.plan_cases) {
  if (!c.values) continue;
  let r;
  try { r = sandbox.validateZonePlan({ values: c.values }); }
  catch (e) { failures.push({ group: 'rules', name: c.name, field: 'threw', expected: 'a result', actual: e.message }); compared++; continue; }
  rec('rules', c.name, 'blocks', [...c.expect_blocks].sort(), ruleSet(r.blocks));
  rec('rules', c.name, 'warns', [...c.expect_warns].sort(), ruleSet(r.warns));
  rec('rules', c.name, 'ok', c.expect_blocks.length === 0, r.ok);
  const vague = (r.blocks || []).filter(b => !b.message || b.message.length < 8);
  rec('rules', c.name, 'every block carries a message', [], vague.map(b => b.rule));
}

// ── material tokens: the BIN grammar ----------------------------------------------------
CONSUMED.add('material_token_cases');
for (const c of spec.material_token_cases) {
  if (c.raw === undefined) continue;
  let t;
  try { t = sandbox.parseMaterialToken(c.raw); } catch (e) { t = { ok: `THREW ${e.message}` }; }
  if (c.distinct_from !== undefined) {
    const other = sandbox.parseMaterialToken(c.distinct_from);
    rec('token', c.name, 'pool keys differ', true,
      sandbox.materialPoolKey(t) !== sandbox.materialPoolKey(other));
    continue;
  }
  rec('token', c.name, 'ok', c.ok, t.ok);
  if (!c.ok) {
    rec('token', c.name, 'fields are null on refusal', [null, null, null, null], [t.lot, t.slot, t.bin, t.scope]);
    rec('token', c.name, 'refusal names a reason', true, typeof t.reason === 'string' && t.reason.length > 3);
    continue;
  }
  rec('token', c.name, 'lot', c.lot, t.lot);
  rec('token', c.name, 'slot', c.slot, t.slot);
  rec('token', c.name, 'bin', c.bin, t.bin);
  rec('token', c.name, 'scope', c.scope, t.scope);
}

// ── demand -------------------------------------------------------------------------------
CONSUMED.add('demand_cases');
for (const c of spec.demand_cases) {
  if (!c.row) continue;
  let actual;
  try { actual = sandbox.zoneDemand(c.row, c.zone, c.painted); } catch (e) { actual = `THREW ${e.message}`; }
  rec('demand', c.name, 'layers/total/share', c.expect, actual);
  // Where the vector states the wrong answer explicitly, prove we do not produce it.
  if (c.wrong_if_rounded !== undefined) {
    rec('demand', c.name, 'share is NOT the rounded value', true, actual && actual.share !== c.wrong_if_rounded);
  }
  if (c.wrong_if_floored !== undefined) {
    rec('demand', c.name, 'share is NOT the floored value', true, actual && actual.share !== c.wrong_if_floored);
  }
}

// ── rollup: row identity is the POOL (lot, slot, bin) -------------------------------------
CONSUMED.add('rollup_cases');
for (const c of spec.rollup_cases) {
  if (!c.values) continue;
  const paintedOf = v => Number((c.painted || {})[v] || 0);
  let rows;
  try { rows = sandbox.materialRollupRows({ values: c.values }, paintedOf); } catch (e) { rows = `THREW ${e.message}`; }
  // Compare pool COMPONENTS, not the opaque key string: the key is a JSON encoding chosen
  // for collision-freedom, and asserting it verbatim would pin an implementation detail.
  rec('rollup', c.name, 'pools and 사용', c.expect,
    Array.isArray(rows) ? rows.map(r => ({ pool: [r.lot, r.slot, r.bin], used: r.used })) : rows);
  if (Array.isArray(rows)) {
    rec('rollup', c.name, 'every pool key is distinct', rows.length, new Set(rows.map(r => r.key)).size);
  }
}

// ── 잔여: reliability propagates, it is never computed away --------------------------------
CONSUMED.add('remaining_cases');
for (const c of spec.remaining_cases) {
  if (!c.availability) continue;
  let r;
  try { r = sandbox.remainingState(c.availability, c.used); } catch (e) { r = `THREW ${e.message}`; }
  rec('remaining', c.name, 'value/reliable', c.expect,
    r && typeof r === 'object' ? { value: r.value, reliable: r.reliable } : r);
  if (c.expect.reliable === false) {
    rec('remaining', c.name, 'unreliable answers carry a reason', true,
      typeof r.reason === 'string' && r.reason.length > 3);
  }
  if (c.reason_contains) {
    rec('remaining', c.name, `reason names "${c.reason_contains}"`, true,
      typeof r.reason === 'string' && r.reason.includes(c.reason_contains));
  }
  if (Array.isArray(c.reason_differs_from)) {
    const mine = r.reason;
    const others = c.reason_differs_from.map(a => sandbox.remainingState(a, c.used).reason);
    rec('remaining', c.name, 'reason is distinct from every other unreliable case',
      others.map(() => true), others.map(o => o !== mine));
    rec('remaining', c.name, 'the other reasons are distinct from each other too',
      others.length, new Set(others).size);
  }
}

// ── TSV core ------------------------------------------------------------------------------
CONSUMED.add('tsv_cases');
for (const c of spec.tsv_cases) {
  if (!c.name) continue;
  if (c.text !== undefined && c.grid !== undefined) {
    let g;
    try { g = sandbox.parseTsv(c.text, {}); } catch (e) { g = `THREW ${e.message}`; }
    rec('tsv', c.name, 'parse', c.grid, g);
  }
  if (c.text_out !== undefined) {
    let s;
    try { s = sandbox.serializeTsv(c.grid); } catch (e) { s = `THREW ${e.message}`; }
    rec('tsv', c.name, 'serialize', c.text_out, s);
    // Serialization must be readable by our own parser, for every case.
    rec('tsv', c.name, 'serialize -> parse is the identity', c.grid, sandbox.parseTsv(s, {}));
  }
}

// ── paste mapping --------------------------------------------------------------------------
CONSUMED.add('paste_cases');
for (const c of spec.paste_cases) {
  if (!c.grid) continue;
  let m;
  try { m = sandbox.mapPastedGrid(c.grid, c.start); } catch (e) { m = `THREW ${e.message}`; }
  rec('paste', c.name, 'header detected', c.header, m.header);
  rec('paste', c.name, 'rows', c.expect, m.rows);
  rec('paste', c.name, 'cells past the contract', c.wide, m.wide);
  if (c.droppedLeading !== undefined) {
    rec('paste', c.name, 'leading blank column dropped', c.droppedLeading, m.droppedLeading);
  }
}

// ── 🔴 THE IGNORE ROSTER, AS A SET ----------------------------------------------------------
//
// The loop above scores WORDS. This scores the SET, and the two are not the same check:
// `COUNT` was added to `IGNORED_HEADERS` on 2026-07-29 and all 331 assertions stayed green,
// because a harness only scores the vectors it holds. Membership is the axis that was
// missing - a word added here silently DROPS a column of the user's paste, and a word
// removed here silently turns a heading row into a data row. Neither is visible on screen.
// It has since fired for real: on 2026-07-30 the roster went 4 -> 13 and this was the ONE
// assertion of 362 that diverged. Nothing else in the contract noticed nine new words.
//
// `IGNORED_HEADERS` is lifted from doe_bands.js (see the extract block above), never
// re-typed: a harness carrying its own roster would agree with itself forever.
CONSUMED_OTHER.add('ignored_headers');
{
  const spec_ = spec.ignored_headers;
  if (!spec_ || !Array.isArray(spec_.members) || spec_.members.length === 0) {
    die("vectors.json has no usable `ignored_headers.members`. That key IS the roster assertion - without it the contract is back to scoring three sample words and calling the set covered.");
  }
  const LIVE = vm.runInContext('IGNORED_HEADERS', sandbox);
  if (!Array.isArray(LIVE)) die('IGNORED_HEADERS did not evaluate to an array');

  // Sorted arrays, not Sets: the failure line has to SHOW which word appeared or vanished.
  rec('ignore-roster', 'IGNORED_HEADERS membership', 'the exact set',
    [...spec_.members].sort(), [...LIVE].sort());
  // Set equality hides a duplicated entry; length catches it. A duplicate is harmless today
  // and is the shape a careless merge leaves behind, so it should be seen, not tolerated.
  rec('ignore-roster', 'IGNORED_HEADERS', 'has no duplicate entry', LIVE.length, new Set(LIVE).size);

  // Membership is a list; `IGNORE` is a behaviour. Pin both, or a roster could be correct
  // while the predicate that reads it is not.
  for (const w of spec_.members) {
    rec('ignore-roster', `'${w}'`, 'routes to IGNORE', 'IGNORE', sandbox.columnIdByHeader(w));
  }
  for (const w of (spec_.also_ignored_after_trim_and_case_fold || [])) {
    rec('ignore-roster', `'${w}'`, 'still routes to IGNORE after trim + case fold', 'IGNORE', sandbox.columnIdByHeader(w));
  }
  // 🔴 The half that stops `() => 'IGNORE'` from passing everything above. An UNKNOWN word
  //    must answer null, not IGNORE - if it answered IGNORE, `looksLikeHeader` would accept
  //    any two-column block of ordinary data as a heading and eat the user's first row.
  for (const w of (spec_.never_ignored || [])) {
    const got = sandbox.columnIdByHeader(w);
    rec('ignore-roster', `'${w}'`, 'is not ignored', false, got === 'IGNORE');
  }

  // A roster entry that shadows a contract column would DELETE that column from every
  // pasted heading. Both lists come from the source, so this cannot be satisfied by editing
  // the contract file alone.
  const DOE = vm.runInContext('DOE_COLUMNS', sandbox);
  const contractWords = new Set(DOE.map(c => String(c.header).toUpperCase()));
  const shadowing = LIVE.filter(w => contractWords.has(String(w).trim().toUpperCase()));
  rec('ignore-roster', 'IGNORED_HEADERS', 'shadows no contract column', [], shadowing);

  // 🔴 CROSS-SOURCE. Both lists are lifted from doe_bands.js, so this cannot be satisfied by
  //    editing the contract file. `ROLLUP_COLUMNS` is what `rollupToGrid` emits as the ②
  //    heading; if a rollup column is renamed and the roster is not followed, the ②→① paste
  //    silently turns that heading into a data row - the COUNT defect, one rename later.
  const ROLLUP = vm.runInContext('ROLLUP_COLUMNS', sandbox);
  const upper = new Set(LIVE.map(w => String(w).trim().toUpperCase()));
  rec('ignore-roster', 'ROLLUP_COLUMNS', 'every emitted ② heading word is on the roster',
    [], ROLLUP.filter(w => !upper.has(String(w).trim().toUpperCase())));

  // 🔴 THE PREPARATORY TRIPWIRE. The eight ② words are on the roster for a round trip that
  //    IS NOT WIRED: `rollupToGrid` is exported and imported by nobody (measured 2026-07-30,
  //    and `ignored_headers.$why` ③ says so in writing). This is not a defect and must not
  //    read as one - it is a pin on a stated precondition. The day someone wires it, this
  //    goes red with the note above as the landing spot, and the right response is to update
  //    that note and this expectation together. Scope is the APP (client2/src + client2/tests);
  //    a contract harness reading the symbol is not the app using it.
  {
    const scan = [join(ROOT, 'client2', 'src'), join(ROOT, 'client2', 'tests')];
    const stripComments = s => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1');
    const importers = [];
    for (const dir of scan) {
      let names = [];
      try { names = readdirSync(dir); } catch { die(`cannot read ${dir} while measuring rollupToGrid importers`); }
      for (const n of names) {
        if (!/\.(mjs|js)$/.test(n) || n === 'doe_bands.js') continue;
        if (/\brollupToGrid\b/.test(stripComments(readFileSync(join(dir, n), 'utf8')))) importers.push(n);
      }
    }
    rec('ignore-roster', 'rollupToGrid (the ② → ① round trip)',
      'importers in client2/src + client2/tests — 0 means DECLARED BUT UNWIRED, which is what the roster note claims',
      [], importers);
  }

  // ── The header-row boundary. Membership says which WORDS are ignored; this says which
  //    ROWS are headings, and that is where a roster entry actually costs something. The
  //    negative rows die if `looksLikeHeader` is ever loosened from "every cell resolves"
  //    to "any cell resolves" - the refactor that would turn nine extra words into silent
  //    data loss. The positive rows are the reason those nine words exist at all.
  const bounds = (spec_.header_row_boundary || []).filter(c => Array.isArray(c.row));
  if (bounds.length === 0) {
    die("`ignored_headers.header_row_boundary` is missing or empty. It is the only place the COST of a roster entry is scored - membership alone cannot tell you whether a widened roster eats a data row.");
  }
  if (!bounds.some(c => c.header === true) || !bounds.some(c => c.header === false)) {
    die('fixture is inert: `header_row_boundary` needs BOTH a heading row and a non-heading row. With one direction only, a predicate that answers the same thing every time passes.');
  }
  if (!bounds.some(c => c.header === false && c.row.some(w => LIVE.includes(w)))) {
    die('fixture is inert: no NEGATIVE `header_row_boundary` row carries a roster word. Without one, nothing scores the bound that keeps the roster cheap - a row containing an ignored word beside real data must still be data.');
  }
  for (const c of bounds) {
    rec('ignore-roster', `row ${JSON.stringify(c.row)}`, 'is a heading row', c.header, sandbox.looksLikeHeader(c.row));
  }

  // Inertness guards. The negative list proves nothing if it is all contract columns (which
  // resolve by name anyway) or all unknown words.
  const neg = spec_.never_ignored || [];
  const unknownNeg = neg.filter(w => String(w).trim() !== '' && !contractWords.has(String(w).trim().toUpperCase()));
  if (unknownNeg.length === 0) {
    die('fixture is inert: `never_ignored` contains no UNRECOGNISED word. Contract columns resolve by name regardless, so without an unknown word this list never tests that an unknown word stays unknown - which is the case that eats the first data row.');
  }
  if (!neg.some(w => contractWords.has(String(w).trim().toUpperCase()))) {
    die('fixture is inert: `never_ignored` contains no CONTRACT column, so it never proves a roster entry cannot swallow one.');
  }
}

// ── 🔴 THE EXCEL ROUND TRIP. The user's actual requirement. ---------------------------------
//
// This is the group a unit test of the parser alone cannot cover: each half can be correct
// and the pair still lose a column, a quote, or a raw token. So the whole path runs -
// text -> parse -> map -> legend rows -> planToGrid -> serialize - and the OUTPUT TEXT is
// compared, not an intermediate structure.
CONSUMED.add('roundtrip_cases');
function tsvToRows(tsv) {
  const grid = sandbox.parseTsv(tsv, { trimCells: true });
  const mapped = sandbox.mapPastedGrid(grid, 'value');
  return mapped.rows.map(patch => {
    const row = { value: '', desc: '', stack: '', mat_1h: [], mat_mid: [], mat_top: [] };
    if (patch.value !== undefined) row.value = String(patch.value).trim();
    if (patch.desc !== undefined) row.desc = String(patch.desc).trim();
    if (patch.stack !== undefined) row.stack = String(patch.stack).trim();
    for (const z of ZONES) if (patch[z] !== undefined) row[z] = sandbox.parseMaterialList(patch[z]);
    return row;
  });
}
for (const c of spec.roundtrip_cases) {
  if (!c.tsv) continue;
  let out, out2;
  try {
    out = sandbox.serializeTsv(sandbox.planToGrid(tsvToRows(c.tsv)));
    out2 = sandbox.serializeTsv(sandbox.planToGrid(tsvToRows(out)));
  } catch (e) { out = `THREW ${e.message}`; out2 = out; }
  rec('roundtrip', c.name, 'paste -> copy', c.expect_tsv !== undefined ? c.expect_tsv : c.tsv, out);
  // The SECOND trip must always be an identity. A normalising first pass (comma -> newline)
  // is allowed exactly once; if the text kept changing, copy/paste would never converge.
  rec('roundtrip', c.name, 'the second trip is an identity', out, out2);
  for (const bad of (c.forbid_in_output || [])) {
    rec('roundtrip', c.name, `output does not contain rendering "${bad}"`, false, String(out).includes(bad));
  }
}
// The round trip is only evidence if the fixture actually carries the shapes that break it.
{
  const all = spec.roundtrip_cases.map(c => c.tsv || '').join('');
  if (!all.includes('"')) die('fixture is inert: no round-trip case contains an Excel-quoted cell, so the quoting half of the contract is untested.');
  if (!/\n[^\t\n]*\t\t/.test(all) && !/\t\t/.test(all)) die('fixture is inert: no round-trip case contains an empty middle cell, so a column shift would survive.');
}

// ── legacy band migration -------------------------------------------------------------------
CONSUMED.add('legacy_band_cases');
for (const c of spec.legacy_band_cases) {
  if (!c.bands) continue;
  let z;
  try { z = sandbox.bandsToZones(c.bands); } catch (e) { z = `THREW ${e.message}`; }
  rec('legacy', c.name, 'ok', c.expect.ok, z && z.ok);
  if (c.expect.ok) {
    rec('legacy', c.name, 'zones', [c.expect.stack, c.expect.mat_1h, c.expect.mat_mid, c.expect.mat_top],
      z && z.ok ? [z.stack, z.mat_1h, z.mat_mid, z.mat_top] : z);
  } else {
    rec('legacy', c.name, 'a refusal says why', true, !!(z && typeof z.reason === 'string' && z.reason.length > 8));
  }
}
{
  const refusals = spec.legacy_band_cases.filter(c => c.expect && c.expect.ok === false).length;
  if (refusals < 3) die('fixture is inert: fewer than three REFUSAL cases. A migration that always answers is the defect - it would collapse an inexpressible plan and then replace_map the collapse over the server truth.');
}

// ── the unwired gate: a vector group nobody reads is a contract that silently lost an axis ---
{
  const present = new Set(Object.keys(spec).filter(k => k.endsWith('_cases')));
  const missing = [...present].filter(k => !CONSUMED.has(k));
  if (missing.length > 0) {
    die(`vector group(s) present but consumed by nothing: ${missing.join(', ')}. Write the comparison or delete the group - an unread group is a contract axis that quietly stopped being checked.`);
  }
  const extra = [...CONSUMED].filter(k => !present.has(k));
  if (extra.length > 0) die(`this harness reads group(s) that no longer exist: ${extra.join(', ')}`);

  // 🔴 AND THE SAME GATE FOR EVERYTHING THAT IS NOT A `*_cases` GROUP.
  //
  // `ignored_headers` is a SET, not a list of cases, so it cannot be named `*_cases` - the
  // server half (server/tests/test_doe_zone_model.py) asserts the `*_cases` key set equals
  // its own registry, and a new group there would turn `pytest server/tests/` red for a
  // client-only axis the server cannot score. Naming it `ignored_headers` keeps pytest green
  // AND puts it outside the gate above, so it needs this one. Any future non-case key is
  // caught the same way: add it here or the harness refuses to report.
  const others = Object.keys(spec).filter(k => !k.endsWith('_cases') && !k.startsWith('$') && k !== 'version');
  const unread = others.filter(k => !CONSUMED_OTHER.has(k));
  if (unread.length > 0) {
    die(`contract key(s) present but consumed by nothing: ${unread.join(', ')}. A key nobody reads is an axis that quietly stopped being checked - write the comparison or delete the key.`);
  }
  const goneOther = [...CONSUMED_OTHER].filter(k => !others.includes(k));
  if (goneOther.length > 0) die(`this harness reads contract key(s) that no longer exist: ${goneOther.join(', ')}`);
}

// ---------------------------------------------------------------------------
if (JSON_OUT) {
  console.log(JSON.stringify({ compared, failed: failures.length, failures }, null, 2));
} else if (failures.length === 0) {
  console.log(`DOE zone rules: OK (${compared} assertions)`);
  console.log('  vectors : contracts/doe_band_rules/vectors.json');
  console.log('  rules   : V1 MID required when its zone is non-empty · V2 STACK 1 with both ends ·');
  console.log('            V3 whole lot + its own slot in one BIN · V4 unreadable material token ·');
  console.log('            V5 STACK not a positive integer (carries the retired B9 hazard) ·');
  console.log('            V6 marker (STACK 0) with zone content — markers answer to V6 alone');
  // The roster is PRINTED FROM THE SOURCE, not spelled out in this string. The previous
  // banner said "COLOR and 칠함" while the array already held 칠함* and later COUNT - a
  // hand-written summary of a list is a second copy of that list, and it drifted.
  console.log('  excel   : VALUE·STACK·DESC·1H·MID·TOP — outside the contract but recognised');
  console.log(`            in a heading row: ${vm.runInContext('IGNORED_HEADERS', sandbox).join(' · ')} (set pinned by ignored_headers)`);
} else {
  console.log(`DOE zone rules: ${failures.length} DIVERGENCE(S) of ${compared} assertions\n`);
  for (const f of failures) {
    console.log(`  [${f.group}] ${f.name} :: ${f.field}`);
    console.log(`      expected: ${JSON.stringify(f.expected)}`);
    console.log(`      actual  : ${JSON.stringify(f.actual)}`);
  }
}
process.exit(failures.length === 0 ? 0 : 1);
