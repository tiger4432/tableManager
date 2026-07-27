/**
 * Runs the CLIENT's DOE band validator against contracts/doe_band_rules/vectors.json.
 *
 * What it pins: the eight blocking rules B1-B8, the per-value expansion they all depend
 * on, and the demand arithmetic for a band that references several values.
 *
 * Read-only: it never writes to client2/. `client2/src/doe_bands.js` cannot simply be
 * imported here - it imports `./transfer_plan.js`, which imports `./config.js`, which
 * reads `window.location` at module scope. So this slices the named function
 * declarations out of the source TEXT and evaluates them in a vm sandbox, exactly like
 * contracts/band_arithmetic. `bandToState` is extracted from transfer_plan.js rather
 * than re-typed: it is the SINGLE boundary classifier, and a harness carrying its own
 * copy would happily pass while the app disagreed with it.
 *
 * FAILS LOUDLY on extraction problems (exit 2). A harness that silently passes when it
 * can no longer find the functions is worse than no harness.
 *
 * Exit codes: 0 = client matches the contract | 1 = divergence(s) | 2 = harness failure.
 *
 *   node contracts/doe_band_rules/client_harness.mjs
 *   node contracts/doe_band_rules/client_harness.mjs --json
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const VECTORS = join(HERE, 'vectors.json');
const SRC_PLAN = join(ROOT, 'client2', 'src', 'transfer_plan.js');
const SRC_BANDS = join(ROOT, 'client2', 'src', 'doe_bands.js');
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

/** Slice a multi-line `const NAME = { ... };` out of source by brace matching. */
function extractObjectConst(source, name, file) {
  const m = new RegExp(`(^|\\n)\\s*const\\s+${name}\\s*=\\s*\\{`).exec(source);
  if (!m) die(`could not extract object const '${name}' from ${file}`);
  let i = source.indexOf('{', m.index), depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') { depth--; if (depth === 0) return `const ${name} = ${source.slice(source.indexOf('{', m.index), i + 1)};`; }
  }
  die(`unbalanced braces in '${name}'`);
}

function extractConst(source, name, file) {
  const m = new RegExp(`(^|\\n)\\s*const\\s+${name}\\s*=[^\\n]*`).exec(source);
  if (!m) die(`could not extract const '${name}' from ${file}`);
  return m[0];
}

const planSrc = readFileSync(SRC_PLAN, 'utf8');
const bandsSrc = readFileSync(SRC_BANDS, 'utf8');

// The single classifier must genuinely be single. If doe_bands.js ever stops importing it
// from transfer_plan.js, this harness would be comparing the app against a classifier the
// app no longer uses - so verify the import is still there before trusting the extraction.
if (!/import\s*\{[^}]*\bbandToState\b[^}]*\}\s*from\s*['"]\.\/transfer_plan\.js['"]/.test(bandsSrc)) {
  die("doe_bands.js no longer imports `bandToState` from ./transfer_plan.js. Either the boundary classifier was duplicated (which is the defect this contract exists to prevent) or the import was reshaped. Resolve deliberately.");
}

const NEEDED = ['boundState', 'expandBandValues', 'formatLayerRuns', 'bandLabel',
                'parseMaterialToken', 'materialPoolKey', 'bandLayerSpan', 'buildCoverage',
                'validateBandPlan', 'bandDemand', 'materialRollupRows', 'remainingState',
                'remapBandValues'];

const sandbox = { console };
vm.createContext(sandbox);
try {
  vm.runInContext([
    extractFunction(planSrc, 'bandToState', 'transfer_plan.js'),
    extractConst(bandsSrc, 'SCOPE_ALL', 'doe_bands.js'),
    extractObjectConst(bandsSrc, 'REMAINING_UNKNOWN_REASON', 'doe_bands.js'),
    ...NEEDED.map(n => extractFunction(bandsSrc, n, 'doe_bands.js')),
  ].join('\n'), sandbox);
} catch (e) {
  die(`extracted sources did not evaluate: ${e && e.message}`);
}
for (const fn of ['bandToState', ...NEEDED]) {
  if (typeof sandbox[fn] !== 'function') die(`'${fn}' did not evaluate to a function`);
}

const spec = JSON.parse(readFileSync(VECTORS, 'utf8'));
const failures = [];
let compared = 0;
const rec = (group, name, field, expected, actual) => {
  compared++;
  if (JSON.stringify(expected) !== JSON.stringify(actual)) failures.push({ group, name, field, expected, actual });
};
const ruleSet = list => [...new Set((list || []).map(x => x.rule))].sort();

// --- expansion --------------------------------------------------------------------
for (const c of spec.expansion_cases) {
  if (!c.band) continue;
  let actual;
  try { actual = sandbox.expandBandValues(c.band, c.defined); } catch (e) { actual = `THREW ${e.message}`; }
  rec('expansion', c.name, 'values', c.expect, actual);
}

// --- span: "cannot be computed" (null) must never look like "empty range" ([]) ------
for (const c of spec.span_cases) {
  if (!c.band) continue;
  let span;
  try { span = sandbox.bandLayerSpan(c.band); } catch (e) { span = `THREW ${e.message}`; }
  if (c.expect === null) {
    rec('span', c.name, 'is null (not an empty array)', 'null', span === null ? 'null' : JSON.stringify(span));
  } else {
    const [first, last, len] = c.expect;
    rec('span', c.name, 'first/last/length', c.expect,
      Array.isArray(span) ? [span[0], span[span.length - 1], span.length] : span);
  }
}

// --- rules ------------------------------------------------------------------------
// Guard against an inert fixture: if no plan case mixes scope widths, a per-row
// implementation would pass every one of them and this file would prove nothing.
{
  const mixes = spec.plan_cases.filter(c =>
    (c.bands || []).some(b => Array.isArray(b.values) && b.values.length > 1)
    && (c.bands || []).some(b => Array.isArray(b.values) && b.values.length === 1));
  if (mixes.length === 0) {
    die('fixture is inert: no plan case contains both a multi-value band and a single-value band, so a per-ROW validator would pass every case and the per-value rule would be untested.');
  }
}
for (const c of spec.plan_cases) {
  if (!c.bands) continue;
  let r;
  try { r = sandbox.validateBandPlan({ values: c.values.map(v => ({ value: v })), bands: c.bands }); }
  catch (e) { failures.push({ group: 'rules', name: c.name, field: 'threw', expected: 'a result', actual: e.message }); compared++; continue; }
  rec('rules', c.name, 'blocks', [...c.expect_blocks].sort(), ruleSet(r.blocks));
  rec('rules', c.name, 'warns', [...c.expect_warns].sort(), ruleSet(r.warns));
  rec('rules', c.name, 'ok', c.expect_blocks.length === 0, r.ok);
  // every reported block must carry a message that names something concrete
  const vague = (r.blocks || []).filter(b => !b.message || b.message.length < 8);
  rec('rules', c.name, 'every block carries a message', [], vague.map(b => b.rule));
}

// --- material tokens: the BIN grammar -----------------------------------------------
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
    // a refusal must be null everywhere and must SAY why - '' would let a caller forget
    rec('token', c.name, 'fields are null on refusal', [null, null, null, null],
      [t.lot, t.slot, t.bin, t.scope]);
    rec('token', c.name, 'refusal names a reason', true, typeof t.reason === 'string' && t.reason.length > 3);
    continue;
  }
  rec('token', c.name, 'lot', c.lot, t.lot);
  rec('token', c.name, 'slot', c.slot, t.slot);
  rec('token', c.name, 'bin', c.bin, t.bin);
  if (c.scope !== 'lot_or_slot_ignored') rec('token', c.name, 'scope', c.scope, t.scope);
}

// --- rollup: row identity is the POOL (lot, slot, bin) ------------------------------
for (const c of spec.rollup_cases) {
  if (!c.bands) continue;
  const paintedOf = v => Number((c.painted || {})[v] || 0);
  let rows;
  try {
    rows = sandbox.materialRollupRows({ values: c.values.map(v => ({ value: v })), bands: c.bands }, paintedOf);
  } catch (e) { rows = `THREW ${e.message}`; }
  // Compare pool COMPONENTS, not the opaque key string. The key uses an invisible unit
  // separator on purpose (a lot name may contain '|' or '_'), so asserting it verbatim
  // would pin an implementation detail and be unreadable in review.
  rec('rollup', c.name, 'pools and 사용', c.expect,
    Array.isArray(rows) ? rows.map(r => ({ pool: [r.lot, r.slot, r.bin], used: r.used })) : rows);
  if (Array.isArray(rows)) {
    rec('rollup', c.name, 'every pool key is distinct', rows.length, new Set(rows.map(r => r.key)).size);
  }
}

// --- 잔여: reliability propagates, it is never computed away ------------------------
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
  // Distinctness alone cannot catch a collapse into the generic "신뢰할 수 없습니다" -
  // that fallback is distinct from every other reason too. So the content is pinned:
  // a missing BIN must be NAMED as a missing BIN. Wording is free; the token is not.
  if (c.reason_contains) {
    rec('remaining', c.name, `reason names "${c.reason_contains}"`, true,
      typeof r.reason === 'string' && r.reason.includes(c.reason_contains));
  }
  // Hiding the number is necessary but not sufficient: the user has to be able to tell
  // "that BIN is not in this map" from "the server would not answer" from "not asked yet".
  // Collapse them into one generic reason and the red rule stops informing anything.
  if (Array.isArray(c.reason_differs_from)) {
    const mine = r.reason;
    const others = c.reason_differs_from.map(a => sandbox.remainingState(a, c.used).reason);
    rec('remaining', c.name, 'reason is distinct from every other unreliable case',
      others.map(() => true), others.map(o => o !== mine));
    rec('remaining', c.name, 'the other reasons are distinct from each other too',
      others.length, new Set(others).size);
  }
}

// --- rename propagation --------------------------------------------------------------
for (const c of spec.rename_cases) {
  if (!c.bands) continue;
  let out;
  try { out = sandbox.remapBandValues(c.bands, c.from, c.to); } catch (e) { out = `THREW ${e.message}`; }
  rec('rename', c.name, 'value sets', c.expect,
    Array.isArray(out) ? out.map(b => b.values) : out);
}

// --- demand -----------------------------------------------------------------------
for (const c of spec.demand_cases) {
  if (!c.band) continue;
  const paintedOf = v => Number((c.painted || {})[v] || 0);
  let actual;
  try { actual = sandbox.bandDemand(c.band, paintedOf, c.defined); } catch (e) { actual = `THREW ${e.message}`; }
  rec('demand', c.name, 'layers/total/share', c.expect, actual);
  // where the vector states the wrong answer explicitly, prove we do not produce it
  if (c.wrong_if_summed_per_value !== undefined) {
    rec('demand', c.name, 'share is NOT the per-value sum', true,
      actual && actual.share !== c.wrong_if_summed_per_value);
  }
}

// ---------------------------------------------------------------------------
if (JSON_OUT) {
  console.log(JSON.stringify({ compared, failed: failures.length, failures }, null, 2));
} else if (failures.length === 0) {
  console.log(`DOE band rules: OK (${compared} assertions)`);
  console.log('  vectors : contracts/doe_band_rules/vectors.json');
  console.log('  rules   : B1 reversal · B2 from<1 · B3 unreadable · B4 undefined value ·');
  console.log('            B5 overlap · B6 gap · B7 no/unreadable material · B8 uncovered value ·');
  console.log('            B9 band scoped to nothing · B10 whole lot + its own slot in one BIN');
} else {
  console.log(`DOE band rules: ${failures.length} DIVERGENCE(S) of ${compared} assertions\n`);
  for (const f of failures) {
    console.log(`  [${f.group}] ${f.name} :: ${f.field}`);
    console.log(`      expected: ${JSON.stringify(f.expected)}`);
    console.log(`      actual  : ${JSON.stringify(f.actual)}`);
  }
}
process.exit(failures.length === 0 ? 0 : 1);
