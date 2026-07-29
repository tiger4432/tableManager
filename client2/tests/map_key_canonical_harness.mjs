// Mock harness - 7b canonical map keys / 7c upper-bound display / M4 phase 1 valid_die_ref.
// Run: node client2/tests/map_key_canonical_harness.mjs [--json] [--emit-7b]
//      (no node_modules - vm sandbox over the source TEXT, same technique as
//       push_gate_harness.mjs and contracts/*/client_harness.mjs)
//
// WHY TEXT EXTRACTION: map_editor.js imports ./config.js, which reads window.location at
// module scope, so the module cannot be imported in node. The functions under test are
// module-private and MUST STAY module-private, so their named declarations are sliced out
// and evaluated in a sandbox with stubs for the module state they touch.
//
// FAILS LOUDLY (exit 2) when a function cannot be extracted. A harness that goes green
// because it could no longer find the code is worse than no harness - its result gets cited.
//
// --emit-7b prints the 7b canonicalisation matrix as JSON on stdout so the SERVER's
// canonical_key_value can be fed the identical inputs and diffed key->value
// (see client2/tests/seam_7b_oracle.py). Self-consistency is not evidence of agreement.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_MAP = join(HERE, '..', 'src', 'map_editor.js');
const SRC_PLAN = join(HERE, '..', 'src', 'transfer_plan.js');
const JSON_OUT = process.argv.includes('--json');
const EMIT_7B = process.argv.includes('--emit-7b');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

function sliceBalanced(src, startIdx, open, close) {
  let i = src.indexOf(open, startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const ch = src[j];
    if (ch === open) depth++;
    else if (ch === close) { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}

function makeExtractor(path) {
  const src = readFileSync(path, 'utf8');
  return {
    src,
    fn(name) {
      const m = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
      if (!m) die(`function ${name} not found in ${path}`);
      const out = sliceBalanced(src, m.index, '{', '}');
      if (!out) die(`unbalanced braces for ${name} in ${path}`);
      return out;
    },
    konst(name) {
      const m = new RegExp(`const\\s+${name}\\s*=`).exec(src);
      if (!m) die(`const ${name} not found in ${path}`);
      let depth = 0;
      for (let j = m.index; j < src.length; j++) {
        const ch = src[j];
        if (ch === '[' || ch === '{' || ch === '(') depth++;
        else if (ch === ']' || ch === '}' || ch === ')') depth--;
        else if (ch === ';' && depth === 0) return src.slice(m.index, j + 1);
      }
      die(`no terminator for const ${name} in ${path}`);
    },
  };
}

const M = makeExtractor(SRC_MAP);
const P = makeExtractor(SRC_PLAN);

// ── sandbox ────────────────────────────────────────────────────────────────────
// Module state the extracted functions read. Tests mutate these directly, which is the
// point: the real functions must be reading the real module state, not a private copy.
const ctx = {
  console,
  physFrameOverride: null,
  currentRotation: 0,
  currentSide: 'front',
  validDie: null,
  el: {},
};
vm.createContext(ctx);

try {
  vm.runInContext([
    // 7b - the one canonicalisation and its two users
    M.konst('CANON_INT_RE'),
    M.fn('canonicalKeyValue'),
    M.fn('composeMapId'),
    M.fn('canonIntString'),
    M.konst('CANON_FLOAT_RE'),
    M.fn('decomposeMapKey'),
    M.fn('canonicalMapKey'),
    // M4 phase 1
    M.fn('parseValidDieRef'),
    M.fn('validDieBasis'),
    M.fn('isValidDieAt'),
    // 7c - untracked declaration reading (transfer_plan.js)
    P.fn('untrackedBoundOf'),
    P.fn('boundText'),
    `globalThis.__h = { canonicalKeyValue, composeMapId, decomposeMapKey, canonicalMapKey,
       parseValidDieRef, validDieBasis, isValidDieAt, untrackedBoundOf, boundText };`,
  ].join('\n\n'), ctx);
} catch (e) {
  die(`sandbox evaluation failed - ${e && e.message ? e.message : e}`);
}
const H = ctx.__h;

// ── assertion plumbing ─────────────────────────────────────────────────────────
let pass = 0;
const failures = [];
function check(inv, name, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; if (!JSON_OUT && !EMIT_7B) console.log(`  ok   [${inv}] ${name}`); }
  else {
    failures.push({ inv, name, actual, expected });
    if (!JSON_OUT && !EMIT_7B) console.log(`  FAIL [${inv}] ${name}\n        actual   ${a}\n        expected ${e}`);
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// INV-7b-1 / INV-7b-2 - the canonicalisation matrix.
// The two declared types MUST behave differently; a matrix where they agree everywhere
// would pass against an implementation that ignores the declared type entirely.
// ════════════════════════════════════════════════════════════════════════════════
const CANON_MATRIX = [
  // [value, declared_type, expected]
  ['01', 'number', '1'],
  ['1', 'number', '1'],
  [' 1 ', 'number', '1'],
  ['1.0', 'number', '1'],
  [1, 'number', '1'],
  [1.0, 'number', '1'],
  ['007', 'number', '7'],
  ['-01', 'number', '-1'],
  ['+01', 'number', '1'],
  ['7.5', 'number', '7.5'],
  ['0x10', 'number', '0x10'],      // unreadable -> trimmed original, never invented
  ['LOT', 'number', 'LOT'],
  ['', 'number', ''],
  ['  ', 'number', ''],
  // string / undeclared: TRIM ONLY. '01' must survive as '01'.
  ['01', 'string', '01'],
  [' 01 ', 'string', '01'],
  ['1', 'string', '1'],
  ['01', null, '01'],
  ['01', undefined, '01'],
  [' A_B ', 'string', 'A_B'],
  [1.0, 'string', '1'],            // a float VALUE is numeric whatever the declared type
  [true, 'number', 'true'],        // bool is not a number here (mirrors the server guard)
];
CANON_MATRIX.forEach(([v, t, exp]) => {
  check('7b-1/2', `canonicalKeyValue(${JSON.stringify(v)}, ${JSON.stringify(t)})`,
    H.canonicalKeyValue(v, t), exp);
});
// The differential itself, stated as its own assertion.
check('7b-2', "declared types differ: '01' number vs string",
  [H.canonicalKeyValue('01', 'number'), H.canonicalKeyValue('01', 'string')], ['1', '01']);

// INV-7b-1 at the composition level - the four spellings compose ONE map_id.
const NUM_TYPES = { lot: 'string', slot: 'number' };
const SPELLINGS = [
  { lot: 'LOT', slot: '01' },
  { lot: 'LOT', slot: '1' },
  { lot: 'LOT', slot: ' 1 ' },
  { lot: 'LOT', slot: '1.0' },
  { lot: 'LOT', slot: 1 },
];
const composed = SPELLINGS.map(v => H.composeMapId(['lot', 'slot'], v, NUM_TYPES));
check('7b-1', 'LOT_01 / LOT_1 / LOT_ 1  / LOT_1.0 compose to one map_id',
  Array.from(new Set(composed)), ['LOT_1']);

// INV-7b-2 at the composition level - a string-declared slot keeps its padding.
const STR_TYPES = { lot: 'string', slot: 'string' };
check('7b-2', 'string-declared slot keeps 01',
  H.composeMapId(['lot', 'slot'], { lot: 'LOT', slot: '01' }, STR_TYPES), 'LOT_01');
check('7b-2', 'string-declared 01 and 1 are DIFFERENT maps',
  H.composeMapId(['lot', 'slot'], { lot: 'LOT', slot: '01' }, STR_TYPES)
  !== H.composeMapId(['lot', 'slot'], { lot: 'LOT', slot: '1' }, STR_TYPES), true);
// No declared types at all = trim only (client must not assume number).
check('7b-2', 'undeclared types canonicalise as string',
  H.composeMapId(['lot', 'slot'], { lot: 'LOT', slot: '01' }, {}), 'LOT_01');
// Missing component -> empty part, exactly like the server's values.get(k, "").
check('7b-2', 'missing component becomes an empty part',
  H.composeMapId(['lot', 'slot'], { lot: 'LOT' }, STR_TYPES), 'LOT_');

// ════════════════════════════════════════════════════════════════════════════════
// INV-7b-4 - decompose is the inverse of compose.
// Round-tripping compose->decompose->compose is NOT enough on its own (a defective f and
// its own inverse both pass), so the per-column decomposition is checked key->value too.
// ════════════════════════════════════════════════════════════════════════════════
const RT = [
  { cols: ['lot', 'slot'], types: NUM_TYPES, values: { lot: 'LOT', slot: '01' },
    id: 'LOT_1', parts: { lot: 'LOT', slot: '1' } },
  // lot containing '_' - the tail-absorption rule, which is where a naive split breaks.
  { cols: ['lot', 'slot'], types: NUM_TYPES, values: { lot: 'A_B', slot: '2' },
    id: 'A_B_2', parts: { lot: 'A', slot: 'B_2' } },
  { cols: ['pkg_id', 'base'], types: { pkg_id: 'string', base: 'string' },
    values: { pkg_id: 'P1', base: '07' }, id: 'P1_07', parts: { pkg_id: 'P1', base: '07' } },
  // single key column - the whole key is the value, '_' has no meaning
  { cols: ['lot'], types: { lot: 'string' }, values: { lot: 'A_B_C' },
    id: 'A_B_C', parts: { lot: 'A_B_C' } },
];
RT.forEach(t => {
  const id = H.composeMapId(t.cols, t.values, t.types);
  check('7b-4', `compose ${JSON.stringify(t.values)}`, id, t.id);
  const parts = H.decomposeMapKey(t.cols, id, t.types);
  check('7b-4', `decompose ${t.id} key->value`, parts, t.parts);
  check('7b-4', `recompose ${t.id} == original`, H.composeMapId(t.cols, parts, t.types), t.id);
});
// Decomposition canonicalises too, so a hand-typed padded key finds the stored map.
check('7b-4', 'decompose canonicalises a hand-typed LOT_01',
  H.decomposeMapKey(['lot', 'slot'], 'LOT_01', NUM_TYPES), { lot: 'LOT', slot: '1' });
// Fewer parts than columns -> whole key against the first column (server parity).
check('7b-4', 'undecomposable key falls back to first column whole',
  H.decomposeMapKey(['lot', 'slot'], 'SOLO', NUM_TYPES), { lot: 'SOLO' });

// canonicalMapKey - the production form: normalise a key string in place. IDEMPOTENT, which
// is what makes it safe to apply at more than one site on the same value.
const CMK = [
  ['LOT_01 -> LOT_1', ['lot', 'slot'], 'LOT_01', NUM_TYPES, 'LOT_1'],
  ['LOT_1 unchanged', ['lot', 'slot'], 'LOT_1', NUM_TYPES, 'LOT_1'],
  ['string slot keeps padding', ['lot', 'slot'], 'LOT_01', STR_TYPES, 'LOT_01'],
  // The tail absorbs 'B_02' as ONE token, and 'B_02' is not an integer, so it is preserved.
  // This is the SERVER's behaviour too (build_key_filters joins the tail before binding), and
  // parity matters more here than tidiness: a lot name containing '_' makes the per-column
  // split ambiguous on BOTH sides, identically.
  ['tail absorption keeps a non-integer tail whole', ['lot', 'slot'], 'A_B_02', NUM_TYPES, 'A_B_02'],
  ['tail absorption canonicalises an integer tail', ['lot', 'slot'], 'A_02', NUM_TYPES, 'A_2'],
  ['undecomposable key is NOT given empty tails', ['lot', 'slot'], 'SOLO', NUM_TYPES, 'SOLO'],
  ['no key columns -> untouched', [], 'LOT_01', NUM_TYPES, 'LOT_01'],
  ['empty key -> untouched', ['lot', 'slot'], '', NUM_TYPES, ''],
];
CMK.forEach(([label, cols, key, types, exp]) => {
  const once = H.canonicalMapKey(cols, key, types);
  check('7b-4', `canonicalMapKey: ${label}`, once, exp);
  check('7b-4', `canonicalMapKey idempotent: ${label}`, H.canonicalMapKey(cols, once, types), exp);
});

// DIFFERENTIAL: how many of these vectors would change under the OLD (raw join) behaviour?
// If this is 0 the fixture proves nothing, exactly the failure my memory file records.
const rawJoin = (cols, v) => cols.map(c => (v[c] === undefined || v[c] === null ? '' : String(v[c]))).join('_');
// The EXACT count is asserted, not just ">0": '01', ' 1 ' and '1.0' were composed wrong by
// the old raw join; '1' and the numeric 1 were already right. Naming the number means a
// fixture that quietly stops exercising the defect fails here instead of going green.
const drift = SPELLINGS.filter(v => rawJoin(['lot', 'slot'], v) !== 'LOT_1').length;
check('7b-1', 'fixture activates the defect axis (3 of 5 spellings were composed wrong before)',
  drift, 3);

// ════════════════════════════════════════════════════════════════════════════════
// INV-7c-1 / 7c-2 / 7c-3 - the upper bound is READ, never inferred and never recomputed.
// ════════════════════════════════════════════════════════════════════════════════
const UNTRACKED_CASES = [
  // [label, bins entry, expected bound]
  ['declared untracked with a bound', { bin: 1, transfer_untracked: true, remaining_upper_bound: 34, remaining: null, reliable: false }, 34],
  ['bound of 0 is a real bound', { bin: 1, transfer_untracked: true, remaining_upper_bound: 0, remaining: null, reliable: false }, 0],
  // INV-7c-2 - only the exact boolean true is a declaration.
  ['string "true" is NOT a declaration', { bin: 1, transfer_untracked: 'true', remaining_upper_bound: 34 }, null],
  ['1 is NOT a declaration', { bin: 1, transfer_untracked: 1, remaining_upper_bound: 34 }, null],
  ['"none" is NOT a declaration', { bin: 1, transfer_untracked: 'none', remaining_upper_bound: 34 }, null],
  ['"None" is NOT a declaration', { bin: 1, transfer_untracked: 'None', remaining_upper_bound: 34 }, null],
  ['"NONE" is NOT a declaration', { bin: 1, transfer_untracked: 'NONE', remaining_upper_bound: 34 }, null],
  ['null is NOT a declaration', { bin: 1, transfer_untracked: null, remaining_upper_bound: 34 }, null],
  ['"" is NOT a declaration', { bin: 1, transfer_untracked: '', remaining_upper_bound: 34 }, null],
  ['absent flag is NOT a declaration', { bin: 1, remaining_upper_bound: 34 }, null],
  ['false is NOT a declaration', { bin: 1, transfer_untracked: false, remaining_upper_bound: 34 }, null],
  // Declared but no bound served (server withholds it when another degradation overlaps).
  ['declared without a bound stays unknown', { bin: 1, transfer_untracked: true, remaining_upper_bound: null }, null],
  ['declared with absent bound stays unknown', { bin: 1, transfer_untracked: true }, null],
  ['declared with a non-numeric bound stays unknown', { bin: 1, transfer_untracked: true, remaining_upper_bound: 'many' }, null],
  ['declared with NaN bound stays unknown', { bin: 1, transfer_untracked: true, remaining_upper_bound: NaN }, null],
  ['not an object', null, null],
];
UNTRACKED_CASES.forEach(([label, entry, exp]) => {
  check('7c-2', label, H.untrackedBoundOf(entry), exp);
});
// INV-7c-1 - the rendered form is the bound, never a bare number.
check('7c-1', 'bound renders as <=N', H.boundText(34), '≤34');
check('7c-1', 'bound of 0 renders as <=0', H.boundText(0), '≤0');
check('7c-1', 'negative bound still renders as a bound', H.boundText(-3), '≤-3');
check('7c-1', 'no bound has no text', H.boundText(null), '');
check('7c-1', 'undefined bound has no text', H.boundText(undefined), '');
// INV-7c-3 - the client NEVER computes total-fail. It reads what the server served.
// Proven structurally: untrackedBoundOf's only numeric source is remaining_upper_bound.
check('7c-3', 'client reads the served bound verbatim (no arithmetic of its own)',
  H.untrackedBoundOf({ bin: 1, transfer_untracked: true, remaining_upper_bound: 34,
    total: 999, fail: 999 }), 34);

// ════════════════════════════════════════════════════════════════════════════════
// INV-M4-1 / M4-2 / M4-3 - valid_die_ref is additive; absent means byte-identical.
// ════════════════════════════════════════════════════════════════════════════════
// ONE rule, so there is no arbitrary line: absent / null / undefined = not declared.
// Everything else IS a declaration, and a declaration that cannot be read is REFUSED.
// Folding an unreadable declaration back into "not declared" would be the silent fallback
// to circle geometry that INV-M4-3 exists to forbid.
const REF_CASES = [
  ['absent -> null', {}, 'bonding_map', null],
  ['null -> null', { valid_die_ref: null }, 'bonding_map', null],
  ['undefined -> null', { valid_die_ref: undefined }, 'bonding_map', null],
  ['empty string -> refusal', { valid_die_ref: '' }, 'bonding_map', 'unreadable'],
  ['bare string = same table', { valid_die_ref: 'TMPL_1' }, 'bonding_map',
    { table: 'bonding_map', mapKey: 'TMPL_1' }],
  ['{table,map_id}', { valid_die_ref: { table: 'die_template_map', map_id: 'T_1' } }, 'bonding_map',
    { table: 'die_template_map', mapKey: 'T_1' }],
  ['{target_table,map_id} names the same pair', { valid_die_ref: { target_table: 'die_template_map', map_id: 'T_1' } }, 'bonding_map',
    { table: 'die_template_map', mapKey: 'T_1' }],
  ['{map_id} only = same table', { valid_die_ref: { map_id: 'T_1' } }, 'bonding_map',
    { table: 'bonding_map', mapKey: 'T_1' }],
  // Unrecognisable shapes are REFUSED, not guessed into something plausible.
  ['object with no map id -> refusal', { valid_die_ref: { table: 'die_template_map' } }, 'bonding_map', 'unreadable'],
  ['number -> refusal', { valid_die_ref: 7 }, 'bonding_map', 'unreadable'],
  ['array -> refusal', { valid_die_ref: ['a', 'b'] }, 'bonding_map', 'unreadable'],
  ['true -> refusal', { valid_die_ref: true }, 'bonding_map', 'unreadable'],
  ['whitespace-only -> refusal', { valid_die_ref: '   ' }, 'bonding_map', 'unreadable'],
];
REF_CASES.forEach(([label, meta, table, exp]) => {
  const r = H.parseValidDieRef(meta, table);
  const got = (r && r.unreadable) ? 'unreadable' : r;
  check('M4-1/3', label, got, exp);
  if (got === 'unreadable') {
    check('M4-3', `${label}: refusal carries a stated reason`, !!(r.reason && r.reason.length > 0), true);
  }
});
check('M4-1', 'no meta at all -> null (2a9f6c4 behaviour)', H.parseValidDieRef(null, 'bonding_map'), null);

// INV-M4-1: the basis is 'circle' for every map that declares nothing.
ctx.validDie = null;
check('M4-1', "basis with no state is 'circle'", H.validDieBasis(), 'circle');
ctx.validDie = { basis: 'circle', keys: null, reason: '', ref: null };
check('M4-1', "basis with no ref is 'circle'", H.validDieBasis(), 'circle');
// The vocabulary is `circle|ref|refused`, byte-identical to server
// `map_overlay.resolve_valid_die_basis` and to `contracts/map_seam/vectors.json`. One seam
// carrying two spellings is how the `declared`/`derived` confusion started; it is not a
// cosmetic choice, so it is asserted rather than assumed.
// INV-M4-2: a resolved ref is the basis.
ctx.validDie = { basis: 'ref', keys: new Set(['0_0']), reason: '', ref: { table: 't', mapKey: 'k' } };
check('M4-2', "resolved ref reports basis 'ref'", H.validDieBasis(), 'ref');
// INV-M4-3: an unresolvable ref is its own state - never silently 'circle'.
ctx.validDie = { basis: 'refused', keys: null, reason: '규격 조회 실패', ref: { table: 't', mapKey: 'k' } };
check('M4-3', "unresolvable ref reports basis 'refused', NOT 'circle'", H.validDieBasis(), 'refused');
// A resolved-but-empty key set is not a resolution: an all-invalid wafer is not an answer.
ctx.validDie = { basis: 'ref', keys: new Set(), reason: '', ref: { table: 't', mapKey: 'k' } };
check('M4-3', 'empty key set does not count as basis ref', H.validDieBasis(), 'refused');
// The retired spellings must NOT resolve to a live state. If `map` still meant `ref`, a
// half-renamed caller would keep working and the two vocabularies would coexist unnoticed.
ctx.validDie = { basis: 'map', keys: new Set(['0_0']), reason: '', ref: { table: 't', mapKey: 'k' } };
check('M4-2', "retired spelling 'map' is not a live basis", H.validDieBasis(), 'circle');
ctx.validDie = { basis: 'unresolved', keys: null, reason: 'X', ref: { table: 't', mapKey: 'k' } };
check('M4-3', "retired spelling 'unresolved' is not a live basis", H.validDieBasis(), 'circle');

// ── the zero-regression assertion, stated exactly ──────────────────────────────
// INV-M4-1: with no valid_die_ref, isValidDieAt must return the circle verdict it was
// handed, for EVERY input, with no exception. Anything else is a regression on 388k maps.
const CIRCLE_STATES = [
  null,
  { basis: 'circle', keys: null, reason: '', ref: null },
  { basis: 'circle', keys: new Set(['0_0']), reason: '', ref: null },  // stale keys must not leak
];
let passthroughOk = true;
CIRCLE_STATES.forEach(st => {
  ctx.validDie = st;
  for (let x = -2; x <= 2; x++) {
    for (let y = -2; y <= 2; y++) {
      if (H.isValidDieAt(x, y, true) !== true) passthroughOk = false;
      if (H.isValidDieAt(x, y, false) !== false) passthroughOk = false;
    }
  }
});
check('M4-1', 'no ref: isValidDieAt is the identity on the circle verdict (75 pairs)', passthroughOk, true);

// INV-M4-2: with a resolved ref, the MAP decides and the circle verdict is ignored - in
// BOTH directions. Checking only one direction would pass an implementation that ORs or
// ANDs the two, which is exactly "circle still participates".
ctx.validDie = { basis: 'ref', keys: new Set(['1_1', '2_2']), reason: '', ref: { table: 't', mapKey: 'k' } };
check('M4-2', 'in mask, circle says outside -> valid', H.isValidDieAt(1, 1, false), true);
check('M4-2', 'in mask, circle says inside -> valid', H.isValidDieAt(1, 1, true), true);
check('M4-2', 'not in mask, circle says inside -> INVALID (circle does not participate)',
  H.isValidDieAt(5, 5, true), false);
check('M4-2', 'not in mask, circle says outside -> invalid', H.isValidDieAt(5, 5, false), false);
// DIFFERENTIAL: the fixture must contain a cell where mask and circle DISAGREE, otherwise
// it cannot tell "map is the basis" from "circle is the basis".
check('M4-2', 'fixture activates the defect axis (mask and circle disagree somewhere)',
  H.isValidDieAt(1, 1, false) !== false || H.isValidDieAt(5, 5, true) !== true, true);

// The frame window must suspend the mask: inside withPhysFrame we are solving the SOURCE
// map's coordinates, and applying THIS map's mask there cuts one map with another's stencil.
ctx.physFrameOverride = { cols: 10, rows: 10 };
check('M4-2', 'frame window suspends the mask (circle verdict passes through)',
  [H.isValidDieAt(5, 5, true), H.isValidDieAt(1, 1, false)], [true, false]);
ctx.physFrameOverride = null;

// INV-M4-3: a refused ref must NOT quietly behave like a resolved one, and must not
// blank the wafer either - the basis reports 'refused' and the verdict stays the
// pre-M4 one, which is stated on screen rather than assumed.
//
// NOTE for the seam: this is a DECLARED DIVERGENCE from the server, not agreement. Server
// `resolve_valid_die_basis` answers `{source:'refused', basis: None}` - it can return "no
// mask" because nothing is being drawn. The client cannot: a canvas with no mask is not a
// renderable state, so it renders the pre-M4 circle and marks the refusal in three places
// (chip, toast, console). What it must never do is CLAIM the ref, which is what the basis
// string asserts here.
ctx.validDie = { basis: 'refused', keys: null, reason: 'X', ref: { table: 't', mapKey: 'k' } };
check('M4-3', 'refused: verdict passes through, basis says so',
  [H.isValidDieAt(1, 1, true), H.isValidDieAt(1, 1, false), H.validDieBasis()],
  [true, false, 'refused']);
ctx.validDie = null;

// ── output ─────────────────────────────────────────────────────────────────────
if (EMIT_7B) {
  process.stdout.write(JSON.stringify(
    CANON_MATRIX.map(([v, t, exp]) => ({
      value: v, type: t, expected: exp, client: H.canonicalKeyValue(v, t),
    })), null, 2) + '\n');
  process.exit(failures.length ? 1 : 0);
}
if (JSON_OUT) {
  console.log(JSON.stringify({ pass, fail: failures.length, failures }, null, 2));
} else {
  console.log(`\n${failures.length ? 'FAIL' : 'PASS'} — ${pass} passed, ${failures.length} failed`);
}
process.exit(failures.length ? 1 : 0);
