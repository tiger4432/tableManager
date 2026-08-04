/**
 * MAP SEAM — the CLIENT half, scored against contracts/map_seam/vectors.json.
 *
 * The same file `contracts/map_seam/test_seam_contract.py` reads. Both sides are scored
 * against the CONTRACT, never against each other: that is the whole mechanism. In the round
 * that shipped as `2a9f6c4` each side was correct in isolation and the round trip was not
 * scored until review, which cost a full extra round.
 *
 * Read-only: it never writes to client2/. The functions it needs are module-private, and
 * this harness must not change that, so it slices the named declarations out of the source
 * text and evaluates them in a vm sandbox with stubs for the module state they touch.
 *
 * MISSING SYMBOLS follow the SHARED status vocabulary in `vectors.json` -> `symbol_status`,
 * which `test_seam_contract.py::_server_symbol` implements identically. That table is the
 * definition; this is its client half, and the two must not drift — two scorers with two
 * vocabularies is a mapping table waiting to be written, and a mapping table is a second
 * implementation of the answer. (They HAD drifted for part of 2026-07-29: this side treated
 * `pending` and `required` alike while the server distinguished them.)
 *   `live`     — existed. Absent means RENAMED or reshaped: exit 2, nothing was compared.
 *   `pending`  — contract-first; the implementation has not landed yet and is not overdue.
 *                Reported by name with owner and blocked invariants, and the run stays GREEN.
 *                It expires by itself: once the symbol appears it is scored automatically,
 *                and leaving `status: pending` on a landed symbol is then a HARD FAILURE
 *                (STALE PENDING) — because an absent `pending` symbol is forgiven by design,
 *                so a stale one would silently forgive a later rename too.
 *   `required` — the contract needs it and it has not landed. NOT LANDED, exit 1.
 *
 * Exit codes: 0 = client meets the contract | 1 = divergence / not landed / stale pending
 *             | 2 = harness failure.
 *
 *   node contracts/map_seam/client_harness.mjs
 *   node contracts/map_seam/client_harness.mjs --json
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const VECTORS = join(HERE, 'vectors.json');
const SRC = {
  'client2/src/map_editor.js': readFileSync(join(ROOT, 'client2', 'src', 'map_editor.js'), 'utf8'),
  // The 7b canonicalisation moved out of map_editor.js into its own module (map-key
  // extraction round). vectors.json names the file per symbol, so a symbol that moves
  // again is a one-line vectors edit — but it MUST be edited: `client_symbols.<role> names
  // an unknown file` and `sliceFunction -> null` both die here rather than skip the axis.
  'client2/src/map_key.js': readFileSync(join(ROOT, 'client2', 'src', 'map_key.js'), 'utf8'),
  'client2/src/transfer_plan.js': readFileSync(join(ROOT, 'client2', 'src', 'transfer_plan.js'), 'utf8'),
};

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

/** Slice `function NAME(...) { ... }` out of source by brace matching. Null if absent.
 *  A leading `export ` is accepted and EXCLUDED from the slice — the pieces are evaluated
 *  inside a vm script, where an export statement is a SyntaxError. Extracted modules
 *  (client2/src/map_key.js) export their symbols; map_editor.js keeps them module-private,
 *  and this contract must be able to slice either spelling. */
function sliceFunction(source, name) {
  const decl = new RegExp(`(?:^|\\n)\\s*(?:export\\s+)?(function\\s+${name}\\s*\\()`);
  const m = decl.exec(source);
  if (!m) return null;
  const start = m.index + m[0].length - m[1].length;
  let i = source.indexOf('{', start + m[1].length - 1);
  if (i < 0) return null;
  let depth = 0;
  for (; i < source.length; i++) {
    const c = source[i];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return source.slice(start, i + 1); }
  }
  die(`unbalanced braces while extracting '${name}'`);
}

/** Slice a single-line `const NAME = ...;` declaration. */
function sliceConst(source, name) {
  const re = new RegExp(`(^|\\n)(const\\s+${name}\\s*=[^\\n]*)`);
  const m = re.exec(source);
  return m ? m[2] : null;
}

const spec = JSON.parse(readFileSync(VECTORS, 'utf8'));

// ── Symbol manifest ────────────────────────────────────────────────────────────────────
// The manifest lives in the VECTOR file, not here, so renaming a function is a contract
// edit rather than a quiet harness patch.
// The SHARED status vocabulary — `vectors.json` -> `symbol_status` holds the table, and
// `test_seam_contract.py::_server_symbol` implements the same three states. Two scorers with
// two vocabularies is a mapping table waiting to be written, and a mapping table is a second
// implementation of the answer.
//   live     absent -> RENAMED/REMOVED, exit 2 (nothing compared)   | present -> scored
//   pending  absent -> PENDING, reported, NOT a failure             | present -> scored + STALE
//   required absent -> NOT LANDED, exit 1                           | present -> scored
const notLanded = [];   // `required` and absent — overdue
const pendingSymbols = []; // `pending` and absent — contract-first, quiet by design
const stalePending = []; // `pending` but PRESENT — the promise to promote, come due
const pieces = [];
const have = new Set();
for (const c of spec.client_consts || []) {
  const code = sliceConst(SRC[c.file], c.name);
  if (!code) {
    die(`const '${c.name}' is gone from ${c.file}. The canonicalizer it backs cannot be `
      + `evaluated, so nothing would be compared. Update vectors.json client_consts.`);
  }
  pieces.push(code);
  // ...and publish it on the sandbox global. A top-level `const` in `vm.runInContext` lives in
  // the script's lexical scope, so the extracted functions see it but the SCORER cannot — and a
  // scorer that needs the value (e.g. the fixed valid-die table an expectation is stated in)
  // would otherwise have to re-type it here, which is the stale copy this whole file exists to
  // refuse. Function declarations already land on the global; this gives consts the same reach.
  pieces.push(`globalThis[${JSON.stringify(c.name)}] = ${c.name};`);
}
for (const [role, m] of Object.entries(spec.client_symbols)) {
  if (role === '$comment') continue;
  const source = SRC[m.file];
  if (source === undefined) die(`client_symbols.${role} names an unknown file: ${m.file}`);
  const meta = { role, fn: m.fn, file: m.file, why: m.$why || '',
    owner: m.$owner || 'unassigned', blocks: m.$blocks || '', shape: m.$shape || '' };
  const code = sliceFunction(source, m.fn);
  if (code) {
    pieces.push(code); have.add(role);
    // PROPERTY 3 of `symbol_status`: the symbol landed, so the declaration owes a promotion.
    // Not bookkeeping — while it reads `pending` an ABSENT symbol is forgiven, so a later
    // rename of this now-landed function would be forgiven too and the axis would go
    // unscored behind a green run. The vectors are already being scored either way.
    if (m.status === 'pending') stalePending.push(meta);
    continue;
  }
  if (m.status === 'live') {
    die(`'${m.fn}' is gone from ${m.file} — renamed, removed, or reshaped. The contract names `
      + `it in vectors.json client_symbols.${role}. Update that manifest deliberately; do `
      + `not delete the check, and do NOT demote it to \`pending\` to silence this: `
      + `\`pending\` means 'not written yet', not 'was here and left'.`);
  }
  if (m.status === 'pending') {
    // QUIET BY DESIGN, and the only state that is. These vectors were written before the
    // implementation on purpose, so having nothing to score yet is the intended condition
    // rather than a regression. Rendering it red teaches people to ignore a red suite.
    if (!meta.owner || meta.owner === 'unassigned' || !meta.blocks) {
      die(`client_symbols.${role} is \`pending\` without an $owner and $blocks. A pending `
        + `axis is allowed to be quiet only because someone owns it and the cost of the wait `
        + `is written down; without those it is an anonymous hole with better manners.`);
    }
    pendingSymbols.push(meta);
    continue;
  }
  notLanded.push(meta);
}

// Module state the extracted functions read. Everything else is pure.
//   tableSchema            — served by GET /schema/{table} (map_key_columns + column_types)
//   el / physFrameOverride — the two metadata sources physNum consults
//   S / summaryKeyFor      — transfer_plan module state; the key derivation is not the
//                            contract, so it is stubbed rather than dragged in.
const sandbox = {
  console, tableSchema: {}, el: {}, physFrameOverride: null,
  S: { summaries: new Map(), ctx: {} },
  summaryKeyFor: () => 'K',
  // The M4 branch point's state. `let validDie` (map_editor.js:1870) is not a const, so it is
  // not sliceable — and it should not be: the whole point of scoring the branch is to drive it
  // through the states the contract names.
  validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
  // The Push boundary's other piece of module state. Like `validDie` it is a `let`, so it is
  // not sliceable — and it should not be: it records whether the USER opened the table
  // select, and driving the decision through its two values is the whole point. The app sets
  // it in exactly one place (the select's `change` listener) and clears it in exactly one
  // place (`syncValidDieRefControls`), so the harness stands in for the DOM event and lets
  // the extracted functions do everything else.
  validDieRefTableTouched: false,
};
vm.createContext(sandbox);
try {
  vm.runInContext(pieces.join('\n'), sandbox);
} catch (e) {
  die(`extracted sources did not evaluate: ${e && e.message}`);
}
// FN is a PROXY, not a plain object, and that is load-bearing. Reaching for a role the
// manifest does not define used to yield `undefined`, and calling it threw a TypeError that
// `attempt()` swallowed into a string — so a harness bug was reported as a client divergence,
// or (outside attempt()) as a raw stack trace that reads like a tooling problem rather than a
// finding. A harness that crashes reports NOTHING while looking like somebody else's fault.
// Every miss now dies with the role name and says whose bug it is.
const _fn = {};
for (const role of have) {
  const name = spec.client_symbols[role].fn;
  if (typeof sandbox[name] !== 'function') die(`'${name}' did not evaluate to a function`);
  _fn[role] = sandbox[name];
}
const FN = new Proxy(_fn, {
  get(t, role) {
    if (typeof role === 'symbol') return undefined;
    if (role in t) return t[role];
    if (role in spec.client_symbols) {
      die(`symbol role '${role}' (${spec.client_symbols[role].fn}) is declared in `
        + `vectors.json client_symbols but did not land, and the scorer reached for it anyway. `
        + `Guard the call site with the NOT LANDED list instead of calling it.`);
    }
    die(`the scorer asked for symbol role '${role}', which vectors.json client_symbols does `
      + `NOT define. This is a HARNESS bug, not a client divergence — nothing was compared. `
      + `Add the role to the manifest or fix the call site.`);
  },
});

// ── Scoring ────────────────────────────────────────────────────────────────────────────
const failures = [];
let compared = 0;
const scored = new Set();
const rec = (group, name, field, expected, actual) => {
  compared++;
  scored.add(group);
  if (JSON.stringify(expected) !== JSON.stringify(actual)) {
    failures.push({ group, name, field, expected, actual });
  }
};
const cases = (g) => (spec[g] || []).filter(c => 'name' in c);
const attempt = (f) => { try { return f(); } catch (e) { return `THREW ${e && e.message}`; } };
// A THROWN extraction is not an answer, and any assertion whose shape can SWALLOW the marker
// must say so explicitly. Measured 2026-07-29: `validDieChainError` calls a helper that was
// missing from the manifest, so it threw on every chain refusal — and because the assertion
// was "a refusal carries a non-empty reason", the exception text WAS a non-empty string and
// the whole group went green. A defect that gave both refusal kinds the same reason survived
// that. `threw()` is what makes the marker fatal instead of convenient.
const threw = (v) => typeof v === 'string' && v.startsWith('THREW ');

// ── Known-defect pins (see vectors.json `known_defects`) ───────────────────────────────
// STRICT, and the strictness is the point. A pinned assertion is green ONLY while the client
// still produces the recorded wrong value. Fix the defect and the pin goes red IN THE OTHER
// DIRECTION, because a pin that has quietly stopped asserting anything is worse than the
// defect it names: it is a vector that can no longer fail.
const DEFECTS = spec.known_defects || {};
const pinned = [];
// Axes this scorer deliberately does NOT claim, listed so the gap is visible in the report
// instead of being invisible in the count. An assertion that re-types the value it is
// checking passes against an implementation that no longer produces it.
const unscoreable = [];
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const clone = (v) => JSON.parse(JSON.stringify(v === undefined ? null : v));

// A group whose SYMBOL has not landed is neither "scored" nor "unwired": it is wired and
// blocked. Without this distinction the group-completeness check below would exit 2 —
// HARNESS FAILURE — for a contract failure, which points the reader at the wrong file. The
// group is marked scored so completeness passes, and the blockage is reported by name.
const unscoredGroups = [];
const requireRoles = (group, roles, invariant) => {
  const missing = roles.filter(r => !have.has(r));
  if (!missing.length) return true;
  scored.add(group);
  unscoredGroups.push({ group, invariant,
    missing: missing.map(r => `${spec.client_symbols[r].fn} (role ${r})`) });
  return false;
};

/** Record an assertion that a named known defect is expected to fail. */
const recPinned = (group, name, field, contract, actual, pin, pinnedValue) => {
  compared++;
  scored.add(group);
  const d = DEFECTS[pin.defect];
  if (!d) {
    failures.push({ group, name, field, kind: 'unregistered_pin',
      expected: `a registered known_defects entry named '${pin.defect}'`,
      actual: `'${pin.defect}' is not in known_defects — an anonymous red wearing an id` });
    return;
  }
  // A pin that agrees with the contract asserts nothing: it would be a way to make any vector
  // permanently green by writing the same value twice.
  if (eq(contract, pinnedValue)) {
    failures.push({ group, name, field, kind: 'vacuous_pin',
      expected: `${pin.defect}: client_actual to DIFFER from the contract value`,
      actual: `both are ${JSON.stringify(contract)} — the pin cancels the vector` });
    return;
  }
  if (eq(actual, pinnedValue)) {
    pinned.push({ group, name, field, defect: pin.defect, contract, actual, site: d.site });
    return;
  }
  if (eq(actual, contract)) {
    failures.push({ group, name, field, kind: 'stale_pin',
      expected: `${pin.defect} still failing as recorded: ${JSON.stringify(pinnedValue)}`,
      actual: `${JSON.stringify(actual)} — the CONTRACT value. ${pin.defect} (${d.site}) looks `
        + `FIXED, so this pin has stopped asserting anything. Delete $client_known_defect from `
        + `'${name}' and let the contract value stand.` });
    return;
  }
  failures.push({ group, name, field, kind: 'pin_drift',
    expected: `${pin.defect} failing as recorded: ${JSON.stringify(pinnedValue)}`,
    actual: `${JSON.stringify(actual)} — neither the contract value nor the recorded one. `
      + `${pin.defect} (${d.site}) CHANGED SHAPE; re-measure before touching the pin.` });
};

// --- 7b canonical values (INV-7b-1 / 7b-2) ---------------------------------------------
// `canonical_value_server_only_cases` is NOT scored here, and the reason is a transport fact
// rather than an exemption: the client's key values arrive as DOM input strings and JSON
// text, so a Python bool or a None cannot reach this function. Scoring them would pin
// cross-language coercion trivia (`String(true)` vs `str(True)`) no real input can produce.
for (const c of cases('canonical_value_cases')) {
  const got = attempt(() => FN.canonical_key_value(c.value, c.declared_type));
  rec('canonical_value_cases', c.name, 'canonical', c.expect, got === undefined ? null : got);
}
// DERIVED structural guard, mirroring the server: INV-7b-2 means nothing unless some input
// lands on different keys under the two declarations.
{
  const byValue = new Map();
  for (const c of cases('canonical_value_cases')) {
    if (!byValue.has(c.value)) byValue.set(c.value, {});
    byValue.get(c.value)[String(c.declared_type)] = c.expect;
  }
  const differing = [...byValue].filter(([, m]) => m.number !== undefined
    && m.string !== undefined && m.number !== m.string).map(([v]) => v);
  rec('canonical_value_cases', 'INV-7b-2_types_differ', 'has_distinguishing_vector',
    true, differing.length > 0);
  for (const v of differing) {
    rec('canonical_value_cases', `INV-7b-2_declared_type_is_read(${v})`, 'differs',
      true, FN.canonical_key_value(v, 'number') !== FN.canonical_key_value(v, 'string'));
  }
}

// --- 7b composition (INV-7b-3 — THE SEAM) ----------------------------------------------
const withSchema = (c, fn) => {
  sandbox.tableSchema = {
    map_key_columns: c.key_columns,
    column_types: c.column_types || {},
    composite_key_source: [],
  };
  return fn();
};
// `getMapIdFromMeta` takes the schema as its second argument since 7b moved to its own
// module (it used to read map_editor's module-global `tableSchema`). `withSchema` still
// builds the SAME object on the sandbox and it is handed straight in, so what is scored
// here — the schema the editor holds when it composes — is unchanged.
const composeApp = (c, values) => withSchema(c, () => FN.compose_from_meta(values, sandbox.tableSchema));
const composePrim = (c, values) => FN.compose_primitive(c.key_columns, values, c.column_types || {});

for (const c of cases('compose_cases')) {
  // Both the primitive and the application-level composer: the editor calls the latter, and
  // a canonicalisation that lives only in the primitive would be dead code at the seam.
  rec('compose_cases', c.name, 'map_id/primitive', c.expect_map_id,
    attempt(() => composePrim(c, c.values)));
  rec('compose_cases', c.name, 'map_id/getMapIdFromMeta', c.expect_map_id,
    attempt(() => composeApp(c, c.values)));
}
{
  const block = cases('compose_cases').filter(c => c.name.startsWith('slot_number_'));
  const keys = new Set(block.map(c => attempt(() => composeApp(c, c.values))));
  rec('compose_cases', 'INV-7b-1_all_number_spellings', 'distinct_keys', 1, keys.size);
}
for (const c of cases('compose_divergence_cases')) {
  rec('compose_divergence_cases', c.name, 'client_map_id', c.expect_client,
    attempt(() => composeApp(c, c.values)));
}

// --- 7b decomposition (INV-7b-4) -------------------------------------------------------
const decomposePrim = (c, key) => FN.decompose_primitive(c.key_columns, key, c.column_types || {});
const decomposeFilters = (c, key) => withSchema(c, () => {
  const out = FN.decompose_filters(c.key_columns, key, c.column_types || {});
  const flat = {};
  for (const [k, v] of Object.entries(out || {})) flat[k] = v && v.filter !== undefined ? v.filter : v;
  return flat;
});
for (const c of cases('decompose_cases')) {
  rec('decompose_cases', c.name, 'parts', c.expect, attempt(() => decomposePrim(c, c.map_id)));
  // The cell-filter consumer too: a key that finds the CELLS but not the META is the 7b
  // defect's exact shape, so the split must not fork between the two paths.
  rec('decompose_cases', c.name, 'filters', c.expect, attempt(() => decomposeFilters(c, c.map_id)));
}
// Round trip DERIVED from compose_cases — a hand-written round-trip table is how an inverse
// quietly stops being one.
for (const c of cases('compose_cases')) {
  const composed = attempt(() => composePrim(c, c.values));
  const back = attempt(() => decomposePrim(c, composed));
  const expected = {};
  for (const k of c.key_columns) {
    expected[k] = FN.canonical_key_value(c.values[k], (c.column_types || {})[k] ?? undefined);
  }
  rec('compose_cases', c.name, 'roundtrip', expected, back);
}
for (const c of cases('decompose_lossy_cases')) {
  const composed = attempt(() => composePrim(c, c.compose_values));
  rec('decompose_lossy_cases', c.name, 'composed', c.composed, composed);
  rec('decompose_lossy_cases', c.name, 'decomposed', c.expect_decomposed,
    attempt(() => decomposePrim(c, composed)));
}
for (const c of cases('canonical_map_key_cases')) {
  const once = attempt(() => FN.canonical_map_key(c.key_columns, c.map_key, c.column_types || {}));
  rec('canonical_map_key_cases', c.name, 'canonical', c.expect, once);
  // DERIVED idempotence: the output IS the lookup key, so a second application must not move
  // it — otherwise 'canonical' depends on how many boundaries the value crossed.
  rec('canonical_map_key_cases', c.name, 'idempotent', once,
    attempt(() => FN.canonical_map_key(c.key_columns, once, c.column_types || {})));
}

// --- 7c the bound and its rendering (INV-7c-1 / 7c-2) ----------------------------------
for (const c of cases('remaining_display_cases')) {
  const bound = attempt(() => FN.untracked_bound(c.entry));
  rec('remaining_display_cases', c.name, 'bound', c.expect_bound, bound);
  rec('remaining_display_cases', c.name, 'text', c.expect_text, attempt(() => FN.bound_text(bound)));
  // The load-bearing NEGATIVE, derived so it also covers cases added later.
  if (c.expect_bound !== null) {
    const text = attempt(() => FN.bound_text(bound));
    rec('remaining_display_cases', c.name, 'not_a_bare_number',
      true, String(text) !== String(c.expect_bound));
    rec('remaining_display_cases', c.name, 'marks_the_bound', true, String(text).includes('≤'));
  }
}
for (const c of cases('untracked_flag_cases')) {
  const entry = { remaining: null, remaining_upper_bound: 12, reliable: false, status: 'ok' };
  if (c.flag !== null) entry.transfer_untracked = c.flag;
  rec('untracked_flag_cases', c.name, 'bound', c.expect_bound, attempt(() => FN.untracked_bound(entry)));
}
// `availabilityOfPool` is the client's documented single interpretation point. Only the
// NEGATIVE is asserted, deliberately: requiring a particular new field would be this harness
// designing the client. What it may never do is manufacture a number the server withheld —
// a second computation of `total − fail` on this side is the divergence 7c exists to prevent.
for (const c of cases('remaining_display_cases')) {
  const e = c.entry || {};
  if (e.remaining !== null && e.remaining !== undefined) continue;
  sandbox.S.summaries = new Map([['K', {
    status: 'ok',
    data: { warnings: [], bins: { axis: 'connected', entries: [{ bin: 1, ...e }] } },
  }]]);
  const got = attempt(() => FN.availability_of_pool({ key: 'p', bin: 1 })) || {};
  rec('availability_of_pool', c.name, 'value_stays_null', null,
    got.value === undefined ? null : got.value);
}

// --- M4 declaration reader (INV-M4-3) --------------------------------------------------
// Field names differ across the seam by language convention (`map_id` server / `mapKey`
// client); the shapes are normalised here and the TABLE and KEY are what get compared,
// because that pair is what a lookup actually uses.
const parseOutcome = (meta, home) => {
  const r = FN.parse_valid_die_ref(meta, home);
  if (r === null || r === undefined) return { kind: 'none' };
  if (r.unreadable === true) return { kind: 'error' };
  return { kind: 'ref', table: r.table, key: r.mapKey };
};
for (const c of cases('valid_die_ref_parse_cases')) {
  const got = attempt(() => parseOutcome(c.meta, c.home_table));
  rec('valid_die_ref_parse_cases', c.name, 'kind', c.expect, (got || {}).kind);
  if (c.expect === 'ref') {
    rec('valid_die_ref_parse_cases', c.name, 'table', c.expect_table, (got || {}).table);
    rec('valid_die_ref_parse_cases', c.name, 'key', c.expect_key, (got || {}).key);
  }
}
// DERIVED: only null/absent may mean 'no declaration'. If an unreadable declaration ever
// collapsed into `none`, one typo would silently restore circle geometry.
for (const c of cases('valid_die_ref_parse_cases')) {
  const got = attempt(() => parseOutcome(c.meta, c.home_table));
  const declared = Object.prototype.hasOwnProperty.call(c.meta, 'valid_die_ref')
    && c.meta.valid_die_ref !== null;
  rec('valid_die_ref_parse_cases', c.name, 'only_null_is_absence',
    !declared, (got || {}).kind === 'none');
}
for (const c of cases('valid_die_ref_home_divergence_cases')) {
  const got = attempt(() => parseOutcome(c.meta, c.home_table));
  rec('valid_die_ref_home_divergence_cases', c.name, 'client_kind', c.expect_client, (got || {}).kind);
}

// --- M4 baseline (INV-M4-1) ------------------------------------------------------------
// Through the client's REAL parse chain, not a hand-built physConfig: the parse is part of
// the seam. Each case runs through BOTH metadata sources `physNum` consults — the frame
// override and the DOM inputs — so a divergence cannot be dismissed as an artefact of how
// the harness fed the values in.
{
  const KEYS = { waferDia: 'wafer_dia', edgeMargin: 'edge_margin', chipX: 'chip_x', chipY: 'chip_y', offsetX: 'offset_x', offsetY: 'offset_y' };
  const DOM = { waferDia: 'physWaferDia', edgeMargin: 'physEdgeMargin', chipX: 'physChipX', chipY: 'physChipY', offsetX: 'physOffsetX', offsetY: 'physOffsetY' };
  for (const c of cases('mask_baseline_cases')) {
    const [C, R] = (c.rotation === 90 || c.rotation === 270) ? [c.rows, c.cols] : [c.cols, c.rows];
    for (const via of ['frame_override', 'dom_inputs']) {
      sandbox.physFrameOverride = null;
      sandbox.el = {};
      if (via === 'frame_override') {
        sandbox.physFrameOverride = {};
        for (const [k, v] of Object.entries(KEYS)) sandbox.physFrameOverride[k] = c.declared[v];
      } else {
        for (const [k, v] of Object.entries(KEYS)) sandbox.el[DOM[k]] = { value: String(c.declared[v]) };
      }
      // A case may carry a NAMED known defect (vectors.json `known_defects`). Where it does,
      // the assertion is scored strictly against the RECORDED wrong value instead of the
      // contract value — see recPinned. The mask evidence stays in the vector either way, so
      // a reader sees the actual disagreement and not just a label.
      const pin = c.$client_known_defect || null;
      const pc = FN.phys_config(c.rotation, c.side);
      const recRadius = (pin && pin.client_actual
        && pin.client_actual.effective_radius_mm !== undefined)
        ? (n, f, exp, act) => recPinned('mask_baseline_cases', n, f, exp, act, pin,
            pin.client_actual.effective_radius_mm)
        : (n, f, exp, act) => rec('mask_baseline_cases', n, f, exp, act);
      recRadius(`${c.name}/${via}`, 'effective_radius_mm', c.effective_radius_mm, pc.effectiveRadius);
      for (const canvas of (c.canvas || [700])) {
        const mask = [];
        for (let r = 0; r < R; r++) {
          let row = '';
          for (let col = 0; col < C; col++) row += FN.circle_mask(col, r, C, R, pc, canvas, canvas) ? '#' : '.';
          mask.push(row);
        }
        if (pin && pin.client_actual && pin.client_actual.mask) {
          recPinned('mask_baseline_cases', `${c.name}/${via}@${canvas}px`, 'mask',
            c.mask, mask, pin, pin.client_actual.mask);
        } else {
          rec('mask_baseline_cases', `${c.name}/${via}@${canvas}px`, 'mask', c.mask, mask);
        }
      }
    }
  }
  // ANISOTROPY GUARD — the axis is asserted by RUNNING the swap, not by trusting two literals
  // to disagree. Rotation permutes the declared pitches into the frame axes; a client that
  // applies them unpermuted moves zero cells, and until 2026-07-29 it moved zero cells across
  // EVERY vector in this group (nine declare a square chip, and the one anisotropic case is
  // pinned to an empty mask by D1). Nominal coverage is the failure this whole file exists to
  // prevent, so the group now has to prove the question is being asked.
  {
    const quarter = cases('mask_baseline_cases')
      .filter(c => (c.rotation === 90 || c.rotation === 270)
        && c.declared.chip_x !== c.declared.chip_y);
    // A PINNED case cannot carry this axis: its mask is empty on both sides of the swap, so a
    // pitch-blind client passes it. The guard therefore demands a LIVE anisotropic quarter turn.
    rec('mask_baseline_cases', 'INV-M4-1_anisotropy_active', 'live_quarter_turn_with_unequal_pitch',
      true, quarter.some(c => !c.$client_known_defect));
    for (const c of quarter) {
      if (c.$client_known_defect) continue;
      const [C, R] = [c.rows, c.cols];
      const maskFor = (d) => {
        sandbox.physFrameOverride = {
          waferDia: d.wafer_dia, edgeMargin: d.edge_margin, chipX: d.chip_x,
          chipY: d.chip_y, offsetX: d.offset_x, offsetY: d.offset_y,
        };
        const pc = FN.phys_config(c.rotation, c.side);
        const out = [];
        for (let r = 0; r < R; r++) {
          let row = '';
          for (let col = 0; col < C; col++) row += FN.circle_mask(col, r, C, R, pc, 700, 700) ? '#' : '.';
          out.push(row);
        }
        return out;
      };
      const swapped = { ...c.declared, chip_x: c.declared.chip_y, chip_y: c.declared.chip_x };
      rec('mask_baseline_cases', `${c.name}/pitch_swap`, 'mask_moves',
        true, JSON.stringify(maskFor(c.declared)) !== JSON.stringify(maskFor(swapped)));
    }
  }

  sandbox.physFrameOverride = null;
  sandbox.el = {};
}

// --- M4 the branch point, CLIENT side (INV-M4-1 / INV-M4-2) ----------------------------
// Added 2026-07-29. This group was SERVER_ONLY until the client grew `validDieBasis` +
// `isValidDieAt`, which left the two most load-bearing M4 invariants scored on exactly one
// side of a SEAM contract — the blind spot this file exists to close.
//
// The client's branch takes module STATE where the server's takes (meta, resolver). The state
// is derived through the CLIENT'S OWN reader wherever it can be: `parseValidDieRef` decides
// circle-vs-declared here exactly as the app's resolver does at map_editor.js:5686, so this is
// not a second copy of the resolution rules. All the harness supplies is the RESOLVER OUTCOME
// the vector already names — the one thing the network walk decides and a scorer cannot.
{
  const KEY = (x, y) => `${x}_${y}`;
  const VOCAB = ['circle', 'ref', 'refused'];
  const group = cases('valid_die_basis_cases');

  const stateFor = (c) => {
    const parsed = FN.parse_valid_die_ref(c.meta, 'seam_map');
    if (parsed === null || parsed === undefined) {
      return { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };
    }
    if (parsed.unreadable) {
      // `parsed.reason` VERBATIM — no `|| fallback`. A default here would substitute a string
      // the harness wrote for one the client stopped producing, and `reason_nonempty` would
      // then be scoring the fixture. (That is the same falsy-substitution shape as D1, which
      // is a reminder that the pattern is easy to write without noticing: a mutation emptying
      // this reason survived until the fallback was removed.)
      return { basis: 'refused', keys: null, reason: parsed.reason, ref: null,
        raw: c.meta.valid_die_ref };
    }
    const ref = { table: parsed.table, mapKey: parsed.mapKey };
    if (c.resolver === 'cells') {
      // NOTE the empty-cells case: state is `ref` with zero keys ON PURPOSE. Deriving
      // `refused` from that is the branch point's own second gate (map_editor.js:1912), and
      // it is real logic worth scoring — 'zero cells' is 'not loaded yet', and accepting it
      // would invalidate the user's entire map silently.
      return { basis: 'ref', keys: new Set((c.resolver_cells || []).map(([x, y]) => KEY(x, y))),
        reason: '', ref, raw: c.meta.valid_die_ref };
    }
    // The reason is labelled as a FIXTURE string on purpose: the app builds the real one
    // inside the async `resolveValidDie`, out of any scorer's reach. Nothing asserts it.
    return { basis: 'refused', keys: null, ref, raw: c.meta.valid_die_ref,
      reason: `<fixture; the app builds this in resolveValidDie — resolver:${c.resolver}>` };
  };

  // The state is injected using the CANONICAL vocabulary, which makes the stored token
  // contract surface rather than an internal detail. That is deliberate and it is a Lead PM
  // ruling: `resolve_valid_die_basis` already returns circle|ref|refused, and one seam may not
  // carry two vocabularies — a mapping table between them would be a second implementation of
  // the answer. A half-done rename therefore fails here, loudly, which is the intent.
  sandbox.physFrameOverride = null;
  for (const c of group) {
    sandbox.validDie = stateFor(c);
    rec('valid_die_basis_cases', c.name, 'source', c.expect_source,
      attempt(() => FN.valid_die_basis()));
  }

  // INV-M4-1 — additive coexistence. With no declaration the judgement is a PURE PASSTHROUGH
  // of the circle answer the caller already computed. Both polarities: an implementation that
  // returned `true` unconditionally would satisfy the positive half on its own.
  const circleCase = group.find(c => c.expect_source === 'circle');
  if (circleCase) {
    sandbox.validDie = stateFor(circleCase);
    for (const circleInside of [true, false]) {
      rec('valid_die_basis_cases', circleCase.name, `passthrough(circle=${circleInside})`,
        circleInside, attempt(() => FN.valid_die_at(3, 4, circleInside)));
    }
  }

  // INV-M4-2 — the referenced map is the SOLE basis. Two directions, and both are required:
  //   declared but outside the circle  -> valid   (not INTERSECTED with circle geometry)
  //   inside the circle but undeclared -> invalid (not UNIONED with it either)
  // One direction alone passes against the wrong implementation. This is also what catches a
  // partial rename: if `isValidDieAt` still gates on `!== 'map'` while `validDieBasis` returns
  // 'ref', every cell falls through to circle geometry and the reference never applies —
  // while the chip reports a happily resolved reference.
  const refCase = group.find(c => c.expect_source === 'ref' && c.resolver === 'cells'
    && (c.resolver_cells || []).length > 0);
  if (refCase) {
    sandbox.validDie = stateFor(refCase);
    for (const [x, y] of refCase.resolver_cells) {
      rec('valid_die_basis_cases', refCase.name, `ref_cell_wins(${x},${y})`, true,
        attempt(() => FN.valid_die_at(x, y, false)));
    }
    const declared = new Set(refCase.resolver_cells.map(([x, y]) => KEY(x, y)));
    let probe = null;
    for (let x = 0; x <= 64 && !probe; x++) {
      for (let y = 0; y <= 64 && !probe; y++) if (!declared.has(KEY(x, y))) probe = [x, y];
    }
    rec('valid_die_basis_cases', refCase.name, `circle_cell_loses(${probe[0]},${probe[1]})`,
      false, attempt(() => FN.valid_die_at(probe[0], probe[1], true)));
  }

  // Fixture-inactivity guard. Same discipline as doe_band_rules' paired-case guard: if the
  // group loses either arm, the surviving vectors pass against an implementation that has no
  // branch at all, and the group still LOOKS like coverage.
  rec('valid_die_basis_cases', 'INV-M4-1_fixture_active', 'has_no_declaration_case',
    true, Boolean(circleCase));
  rec('valid_die_basis_cases', 'INV-M4-2_fixture_active', 'has_resolved_ref_case',
    true, Boolean(refCase));
  rec('valid_die_basis_cases', 'INV-M4-2_fixture_active', 'ref_case_has_out_of_circle_cell',
    true, Boolean(refCase && refCase.resolver_cells.some(([x, y]) => x > 20 || y > 20)));
  rec('valid_die_basis_cases', 'one_vocabulary', 'sources_are_canonical',
    [], group.map(c => c.expect_source).filter(s => !VOCAB.includes(s)));

  // DECLARED DIVERGENCE — what the client RENDERS on `refused`. The server answers
  // {source:'refused', basis:None} and draws nothing; a canvas has no such state, so the
  // client renders the pre-M4 circle and says so in three places. Scoring the source string
  // alone would let that visible refusal decay into a silent circle fallback with the
  // contract still green — INV-M4-3's failure mode through the back door.
  for (const c of cases('valid_die_refused_render_divergence_cases')) {
    sandbox.validDie = stateFor(c);
    const basis = attempt(() => FN.valid_die_basis());
    rec('valid_die_refused_render_divergence_cases', c.name, 'client_basis',
      c.expect_client_basis, basis);
    // The verdict passes THROUGH — both polarities, or an implementation that hard-returns
    // `true` satisfies half of it and blanks nothing.
    rec('valid_die_refused_render_divergence_cases', c.name, 'verdict_passthrough',
      [true, false],
      [attempt(() => FN.valid_die_at(1, 1, true)), attempt(() => FN.valid_die_at(1, 1, false))]);
    // SURFACING, property 1: `renderValidDieChip` hides the chip on exactly one condition,
    // `basis === 'circle'`. A refusal reporting 'circle' would draw a clean wafer with no
    // chip at all — the silent fallback wearing the right answer's face.
    rec('valid_die_refused_render_divergence_cases', c.name, 'chip_is_shown(basis!=circle)',
      true, basis !== 'circle');
    // SURFACING, property 2: the chip title, the toast and the console line are all built
    // from `reason`.
    //
    // SCORED ONLY WHERE IT IS REAL. On the `resolver_unreachable` route the reason is built
    // inside the async `resolveValidDie`, so the only string available here is one this
    // harness wrote into its own fixture — asserting it would score the fixture, not the
    // client. A mutation that emptied the app's resolver reason SURVIVED an earlier draft
    // that did exactly that. The route is listed as runtime verification instead.
    if (c.$reason_source === 'resolver_unreachable') {
      unscoreable.push({ group: 'valid_die_refused_render_divergence_cases', name: c.name,
        field: 'reason_nonempty',
        why: 'the reason is produced inside the async resolveValidDie; no scorer can reach it '
          + 'and neither harness covers it — verify at runtime.' });
    } else {
      rec('valid_die_refused_render_divergence_cases', c.name, 'reason_nonempty',
        c.expect_client_reason_nonempty,
        Boolean(sandbox.validDie.reason && sandbox.validDie.reason.length > 0));
    }
  }

  sandbox.validDie = { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };
}

// --- M4 ref key canonicalisation (INV-M4-4) --------------------------------------------
// The expected value is not trusted as a literal: it is asserted to be the answer the 7b
// canonicalizer already gives for the mirrored case. A second normalisation surfaces here.
for (const c of cases('valid_die_ref_canonical_cases')) {
  rec('valid_die_ref_canonical_cases', c.name, 'resolved', c.expect_resolved,
    attempt(() => FN.canonical_map_key(c.key_columns, c.declared_ref_key, c.column_types || {})));
  const mirror = cases('canonical_map_key_cases').find(m => m.name === c.mirrors_case);
  rec('valid_die_ref_canonical_cases', c.name, 'mirror_exists', true, Boolean(mirror));
  if (mirror) {
    rec('valid_die_ref_canonical_cases', c.name, 'mirror_shares_declaration',
      mirror.column_types, c.column_types);
  }
}

// --- M4② authoring: SET AND UNSET (INV-M4-1 save path / INV-M4-5) ----------------------
// The client is where this bites hardest. `buildGridMeta` rebuilds the metadata object FROM
// SCREEN CONTROLS on every Push, so a declaration with no control is destroyed by one save —
// phase 1 papered over that with a single passthrough line, and phase 2 gives the field a
// control, which puts the destructive rebuild ON the path instead of beside it.
//
// Scored THROUGH THE CLIENT'S OWN READER. The writer's output is handed to
// `parseValidDieRef` and `validDieBasis` — the same two functions the app consults at
// map_editor.js:5785 — and the contract asks what the result MEANS, never what shape it has.
// The contract does not get to pick between the string form and the object form.
if (requireRoles('valid_die_authoring_cases', ['apply_valid_die_ref'],
  'INV-M4-1 (save path) / INV-M4-5 — set and unset')) {
  const G = 'valid_die_authoring_cases';
  const applyOps = (base, ops) => {
    let meta = base;
    for (const op of ops) {
      meta = ('clear' in op) ? FN.apply_valid_die_ref(meta, null)
        : FN.apply_valid_die_ref(meta, op.set);
    }
    return meta;
  };
  // The state is derived through `parseValidDieRef`, which is exactly how the app decides
  // circle-vs-declared. Nothing here writes a basis the harness invented.
  const basisState = (meta, home) => {
    const parsed = FN.parse_valid_die_ref(meta, home);
    if (parsed === null || parsed === undefined) {
      return { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };
    }
    if (parsed.unreadable) {
      return { basis: 'refused', keys: null, reason: parsed.reason, ref: null,
        raw: meta.valid_die_ref };
    }
    return { basis: 'ref', keys: new Set(['0_0']), reason: '',
      ref: { table: parsed.table, mapKey: parsed.mapKey }, raw: meta.valid_die_ref };
  };

  for (const c of cases(G)) {
    const out = attempt(() => applyOps(clone(c.base_meta), c.ops));
    rec(G, c.name, 'did_not_throw', false, threw(out) ? out : false);
    // A case carrying `$client_measured` records THIS side's answer so the OTHER scorer can
    // print both when they disagree. Re-asserting it here would score the fixture, so what is
    // scored instead is that the recording is still TRUE — a stale record would hand the
    // server scorer a client answer the client stopped giving, and the divergence report
    // would name two answers, one of which nobody produces.
    if (c.$client_measured) {
      const got = (out && typeof out === 'object')
        ? attempt(() => parseOutcome(out, c.home_table)) : { kind: `THREW/${out}` };
      rec(G, c.name, 'recorded_client_answer_is_current',
        c.$client_measured.reads_back_as, (got || {}).kind);
    }
    const got = (out && typeof out === 'object') ? attempt(() => parseOutcome(out, c.home_table)) : { kind: `THREW/${out}` };
    rec(G, c.name, 'reads_back_as', c.expect_read, (got || {}).kind);
    if (c.expect_read === 'ref') {
      rec(G, c.name, 'table', c.expect_table, (got || {}).table);
      rec(G, c.name, 'key', c.expect_key, (got || {}).key);
    }
    if ('expect_source' in c) {
      rec(G, c.name, 'branch_source', c.expect_source,
        attempt(() => FN.valid_die_basis(basisState(out, c.home_table))));
    }
    // DERIVED, over every case. `""` / `"   "` / `{map_id: ""}` are all things a cleared form
    // field produces and the reader calls every one a DECLARATION — so the map is refused
    // permanently, and `valid_die_ref` has no other editor.
    rec(G, c.name, 'never_writes_an_unreadable_declaration', true,
      (got || {}).kind !== 'error');
    // The object form with NO table is the one shape the two sides are RECORDED to read
    // differently (valid_die_ref_home_divergence_cases.object_no_table_no_home). Authoring
    // knows the declaring map's table at write time, so it must never manufacture it.
    const stored = (out && typeof out === 'object') ? out.valid_die_ref : undefined;
    const tablelessObject = stored !== null && typeof stored === 'object'
      && !Array.isArray(stored)
      && !String((stored.table !== undefined ? stored.table : stored.target_table) || '').trim();
    rec(G, c.name, 'no_tableless_object', false, tablelessObject);
    // Everything else in the payload is not this writer's to touch. The falsy declarations in
    // the base metas are the point: `phys_edge_margin: 0` turned into 3.0 by a `v || dflt`
    // rebuild MOVES THE WAFER MASK of a map that was only having its reference cleared —
    // known defect D1's shape, one layer up, and just as silent.
    const strip = (m) => { const o = { ...(m || {}) }; delete o.valid_die_ref; return o; };
    rec(G, c.name, 'other_keys_preserved', strip(c.base_meta), strip(out));
    // A mutating writer breaks Cancel: the abandoned edit is already in the in-memory meta.
    const arg = clone(c.base_meta);
    attempt(() => applyOps(arg, c.ops));
    rec(G, c.name, 'input_not_mutated', clone(c.base_meta), arg);
    // A clear that leaves debris, or a set that accumulates, only shows on the second apply —
    // and in an editor the second apply is one extra click.
    rec(G, c.name, 'idempotent_in_last_op',
      clone(attempt(() => applyOps(clone(c.base_meta), c.ops))),
      clone(attempt(() => applyOps(clone(c.base_meta), [...c.ops, c.ops[c.ops.length - 1]]))));
  }
  // Fixture-inactivity guard. A group that only SETS passes against a writer with no clear
  // path at all, which is the unrecoverable state INV-M4-5 exists to prevent.
  const cs = cases(G);
  rec(G, 'INV-M4-5_fixture_active', 'has_an_unset_case',
    true, cs.some(c => c.ops.some(op => 'clear' in op)));
  rec(G, 'INV-M4-5_fixture_active', 'has_a_set_clear_set_case',
    true, cs.some(c => c.ops.length >= 3));
  rec(G, 'INV-M4-1_fixture_active', 'base_meta_declares_a_falsy_value',
    true, cs.some(c => Object.values(c.base_meta).some(v => v === 0 || v === false || v === '')));
}

// --- M4② the one-hop limit (INV-M4-6) --------------------------------------------------
if (requireRoles('valid_die_chain_cases', ['valid_die_chain_error', 'valid_die_ref_display'],
  'INV-M4-6 — self-reference and two-level chains are refusals')) {
  const G = 'valid_die_chain_cases';
  // Canonicalised through the ALREADY-SCORED 7b primitive, not through a literal in the
  // vector: `canonicalMapKey` is what `resolveValidDie` uses, so running it here is what
  // makes "the guard compares canonical identities" an assertion rather than a claim.
  const chainRef = (c) => ({
    table: c.ref_table,
    mapKey: c.key_columns
      ? FN.canonical_map_key(c.key_columns, c.declared_ref_key, c.column_types || {})
      : c.declared_ref_key,
  });
  const chainHome = (c) => ({ table: c.home.table, mapKey: c.home.map_id });
  const errFor = (c) => attempt(() => FN.valid_die_chain_error(chainRef(c), c.ref_meta, chainHome(c)));

  for (const c of cases(G)) {
    const err = errFor(c);
    // FIRST, and before anything reads the value: an extraction that THREW is not a refusal.
    // Without this the two assertions below are satisfied by an exception — measured, see
    // `threw()` above.
    rec(G, c.name, 'did_not_throw', false, threw(err) ? err : false);
    // `null` and `undefined` both mean "no error" in JS; Python has only None, so the two
    // sides are held to the same MEANING rather than to the same literal.
    rec(G, c.name, 'is_legal', c.expect === 'ok', err === null || err === undefined);
    if (c.expect === 'refused') {
      // A refusal nobody can read is a silent failure with extra steps — INV-M4-3's rule,
      // one layer down.
      rec(G, c.name, 'reason_nonempty', true,
        typeof err === 'string' && !threw(err) && err.trim().length > 0);
    }
  }
  // The two refusals are different problems with different fixes (re-point the reference vs.
  // flatten the template). The WORDING is deliberately not pinned — that would freeze a
  // user-facing string into a contract; what is pinned is that they can be told apart.
  {
    const byKind = {};
    for (const c of cases(G)) {
      if (c.expect !== 'refused') continue;
      (byKind[c.expect_kind] = byKind[c.expect_kind] || new Set()).add(errFor(c));
    }
    const self = [...(byKind.self_reference || [])];
    const chain = [...(byKind.chain || [])];
    rec(G, 'reasons', 'both_kinds_present', true, self.length > 0 && chain.length > 0);
    rec(G, 'reasons', 'kinds_do_not_share_a_reason', [],
      self.filter(r => chain.includes(r)));
  }
  // The mirrored pair, asserted by RUNNING it. The second polarity is the load-bearing one:
  // a guard carrying its own normalisation reports a self-reference where there is an
  // ordinary one, and a second normalisation is what INV-M4-4 forbids.
  for (const c of cases(G)) {
    if (!c.mirrors_case) continue;
    const mirror = cases('canonical_map_key_cases').find(m => m.name === c.mirrors_case);
    rec(G, c.name, 'mirror_exists', true, Boolean(mirror));
    if (mirror) rec(G, c.name, 'mirror_shares_declaration', mirror.column_types, c.column_types);
  }
  {
    const pair = cases(G).filter(c => c.mirrors_case);
    rec(G, 'canonicalisation_pair', 'both_polarities_present',
      ['ok', 'refused'].sort(), [...new Set(pair.map(c => c.expect))].sort());
    rec(G, 'canonicalisation_pair', 'shares_one_declared_key_and_home',
      [1, 1], [new Set(pair.map(c => c.declared_ref_key)).size,
        new Set(pair.map(c => c.home.map_id)).size]);
  }
  rec(G, 'one_vocabulary', 'refusal_kinds_are_canonical', [],
    cases(G).filter(c => c.expect === 'refused')
      .map(c => c.expect_kind).filter(k => !['self_reference', 'chain'].includes(k)));

  // NOT SCOREABLE HERE, listed rather than counted. Both are real coverage gaps and neither
  // is a reason to loosen an assertion elsewhere.
  unscoreable.push({ group: G, name: 'resolveValidDie', field: 'guard_is_consulted_and_refuses',
    why: 'that `resolveValidDie` actually calls the guard after fetching the referenced meta, '
      + 'and REFUSES rather than falling back to circle, happens inside an async network walk '
      + 'no scorer can reach — verify at runtime (the server half of the same wiring IS scored, '
      + 'by test_a_chain_refusal_reaches_the_branch_point_as_refused).' });
  unscoreable.push({ group: G, name: 'caller_canonicalisation', field: 'identities_arrive_canonical',
    why: 'the canonicalisation performed above is the SCORER\'S; that the CALLER does it before '
      + 'consulting the guard is network-bound. Covered at the resolver by '
      + 'valid_die_ref_canonical_cases (INV-M4-4) instead of being claimed twice here.' });
}

// --- M4② THE LAST DECISION BEFORE THE DATABASE (client-only) ---------------------------
// Added after a QA NO-GO. `valid_die_authoring_cases` scores the PURE WRITER and was read —
// wrongly, by this harness's author — as scoring the write path. A pure writer only decides
// WHAT to write once something decided a write should happen, and that decision lives in
// `validDieRefForPush`, which was in no contract. A HIGH defect lived in the gap: an
// out-of-list declaration table is forced to `''` by `syncValidDieRefControls`, read as "the
// user picked the home table" here, and an UNTOUCHED Push silently demoted a cross-table
// declaration to a bare key.
//
// 🔴 THE CONTROLS ARE NEVER SET DIRECTLY. The round harness did `el.validDieRefTable.value =
// table`, which skips `syncValidDieRefControls` entirely and asserts a state the app cannot
// produce — green, and blind to the whole contract between the two functions. Here the
// fixture supplies only what the APP supplies (the stored raw and the option LIST), then
// calls the app's own sync, then applies a user edit only where a user really would.
if (requireRoles('valid_die_push_decision_cases',
  ['valid_die_ref_for_push', 'valid_die_ref_from_controls', 'sync_valid_die_ref_controls',
    'apply_valid_die_ref'],
  'INV-M4-1 / INV-M4-5 at the Push boundary — what actually reaches the DB')) {
  const G = 'valid_die_push_decision_cases';
  const ABSENT = '$absent';

  for (const c of cases(G)) {
    const raw = c.raw === ABSENT ? undefined : c.raw;
    // Module state and the option list — the app's two inputs, and the only two the fixture
    // is allowed to write.
    sandbox.validDie = { basis: 'circle', keys: null, reason: '', ref: null, raw };
    // 2026-08-04: ONE control. The table <select> and the touched flag that disambiguated it
    // are gone with the ruling that fixes the storage table; the fixture writes the stored raw
    // and nothing else.
    sandbox.el = { validDieRefKey: { value: 'STALE' } };
    // THE APP'S OWN PATH fills the control. Whatever it puts there is what a user would see —
    // pre-dirtying it means a sync that fails to overwrite is caught rather than inherited.
    const synced = attempt(() => FN.sync_valid_die_ref_controls());
    rec(G, c.name, 'sync_did_not_throw', false, threw(synced) ? synced : false);
    // A user edit is the ONE thing that may write a control value, because that is literally
    // what a user does. `user_edit: null` means the user touched nothing at all.
    if (c.user_edit) sandbox.el.validDieRefKey.value = c.user_edit.key;

    const decision = attempt(() => FN.valid_die_ref_for_push());
    rec(G, c.name, 'decision_did_not_throw', false, threw(decision) ? decision : false);
    if ('expect_keep' in c) {
      // Asserted alongside the readback, not instead of it: without this the glue below could
      // absorb a change in what `keep` means and the group would stay green.
      rec(G, c.name, 'keep', c.expect_keep, (decision || {}).keep);
    }

    // The composition is RUN, not re-typed. It used to be three duplicated lines here with a
    // `pending` symbol asking for the extraction; `validDieRefPayload` landed 2026-07-29 and
    // the copy was deleted in the same pass. An extraction that lands while the scorer keeps
    // its copy buys nothing — the copy is the thing that goes stale.
    const base = { grid_cols: 6, grid_rows: 6, phys_edge_margin: 0 };
    const payload = attempt(() => FN.valid_die_ref_payload(base, decision, raw));

    const got = (payload && typeof payload === 'object')
      ? attempt(() => parseOutcome(payload, c.home_table)) : { kind: `THREW/${payload}` };
    rec(G, c.name, 'saved_reads_as', c.expect_saved_reads_as, (got || {}).kind);
    if (c.expect_saved_reads_as === 'ref') {
      rec(G, c.name, 'saved_table', c.expect_table, (got || {}).table);
      rec(G, c.name, 'saved_key', c.expect_key, (got || {}).key);
    }
    if ('expect_payload_has_key' in c) {
      // The byte-identity half of INV-M4-1: an undeclared map's payload must not GROW a key.
      rec(G, c.name, 'payload_has_valid_die_ref_key', c.expect_payload_has_key,
        Boolean(payload && typeof payload === 'object'
          && Object.prototype.hasOwnProperty.call(payload, 'valid_die_ref')));
    }
    if (c.expect_payload_is_the_same_object) {
      // `===`, NOT a value comparison, and the difference is the whole assertion. INV-M4-1
      // says an undeclared, untouched map's payload is byte-identical to `2a9f6c4` — that is
      // a claim about the OBJECT, not about a rebuild that happens to agree. A deep-equal
      // check passes against an implementation that returns `{ ...gridMeta }`, which turns
      // "we did not touch it" into "we reconstructed the same keys in the same order" — a
      // weaker claim wearing the same green.
      rec(G, c.name, 'payload_is_the_untouched_grid_meta_object', true, payload === base);
    }
    // The rest of the payload is not this path's to touch, on any branch.
    const strip = (m) => { const o = { ...(m || {}) }; delete o.valid_die_ref; return o; };
    rec(G, c.name, 'other_keys_preserved', base, strip(payload));
  }

  // Fixture-inactivity guards. Each names a wrong implementation that survives without it.
  {
    const cs = cases(G);
    const untouched = cs.filter(c => !c.user_edit);
    const FIXED = sandbox.VALID_DIE_TABLE;
    if (typeof FIXED !== 'string' || FIXED === '') {
      die('VALID_DIE_TABLE did not evaluate in the sandbox — declare it in client_consts.');
    }
    // THE DEFECT'S OWN AXIS, re-anchored 2026-08-04. It used to be "is the declared table in
    // the option list"; with the list gone it is "does the declared table agree with the FIXED
    // one". Lose the pair and an implementation that rewrites every disagreeing row — the way
    // this ruling is most naturally mis-implemented — passes.
    const crossTable = untouched.filter(c => c.raw && typeof c.raw === 'object' && c.raw.table);
    const onFixed = crossTable.filter(c => c.raw.table === FIXED);
    const offFixed = crossTable.filter(c => c.raw.table !== FIXED);
    rec(G, 'QA_NO_GO_axis_active', 'has_untouched_save_with_a_NON_fixed_declared_table',
      true, offFixed.length > 0);
    rec(G, 'QA_NO_GO_axis_active', 'has_untouched_save_with_the_FIXED_declared_table',
      true, onFixed.length > 0);
    rec(G, 'QA_NO_GO_axis_active', 'both_halves_expect_their_own_table_back',
      [true], [onFixed.length > 0 && offFixed.length > 0
        && onFixed.every(c => c.expect_table === c.raw.table)
        && offFixed.every(c => c.expect_table === c.raw.table)]);
    // ...and the other direction, without which "never rewrite" is satisfied by never writing.
    const rekeyed = cs.filter(c => c.user_edit && c.user_edit.key
      && c.raw && typeof c.raw === 'object' && c.raw.table && c.raw.table !== FIXED
      && c.user_edit.key !== c.raw.map_id);
    rec(G, 'QA_NO_GO_axis_active', 'has_a_rekey_that_must_LAND_on_the_fixed_table',
      [true], [rekeyed.length > 0 && rekeyed.every(c => c.expect_table === FIXED)]);
    rec(G, 'fixture_active', 'has_an_untouched_push', true, untouched.length > 0);
    rec(G, 'fixture_active', 'has_a_user_edit', true, cs.some(c => c.user_edit));
    rec(G, 'fixture_active', 'has_an_empty_string_raw', true, cs.some(c => c.raw === ''));
    rec(G, 'fixture_active', 'has_a_null_raw', true, cs.some(c => c.raw === null));
    rec(G, 'fixture_active', 'has_an_absent_raw', true, cs.some(c => c.raw === ABSENT));
    // A retype of the SAME key is not an edit. Without this case the group cannot tell
    // "the user typed" from "the value changed", and merely focusing the field repoints a map.
    rec(G, 'fixture_active', 'has_a_retype_of_the_unchanged_key',
      true, cs.some(c => c.user_edit && c.raw && typeof c.raw === 'object'
        && c.user_edit.key === c.raw.map_id));
    // Lose this and the identity claim degrades to deep-equality without anything saying so:
    // every remaining assertion in the group is satisfied by an implementation that copies.
    rec(G, 'fixture_active', 'has_an_object_identity_case',
      true, cs.some(c => c.expect_payload_is_the_same_object));
  }

  sandbox.validDie = { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };
  sandbox.el = {};
}

// ── Group completeness ─────────────────────────────────────────────────────────────────
// The failure of an individual vector is caught above. This catches a whole GROUP being
// added and never wired in, which would be silent — and silence is the failure this harness
// exists to prevent.
const SERVER_ONLY = {
  canonical_value_server_only_cases:
    'Python-typed inputs (bool, None) that cannot reach the client: its key values arrive as DOM strings and JSON text.',
  chips_bound_cases:
    'Scored against the pure server function `transfer_plan.build_chips_block`. The client has no counterpart and must not grow one — a second `total − fail` here is the divergence 7c exists to prevent.',
  transfer_log_declaration_cases:
    'The site config never reaches the client; the client reads the flag on the response instead (see untracked_flag_cases).',
  // `valid_die_basis_cases` USED to sit here, with the reason "the basis branch is server-side
  // this round". It stopped being true when `validDieBasis` + `isValidDieAt` landed, and the
  // entry did not, so INV-M4-1 and INV-M4-2 were scored on one side of a seam contract while
  // this map still read like a deliberate decision. Retiring an exemption is part of landing
  // the code that invalidates it.
};
const unwired = Object.keys(spec)
  .filter(k => k.endsWith('_cases'))
  .filter(k => !scored.has(k) && !SERVER_ONLY[k]);
if (unwired.length) {
  console.error(`HARNESS FAILURE: vector group(s) present but never scored: ${unwired.join(', ')}`);
  console.error('Wire them in, or declare them in SERVER_ONLY with a reason. Silence is the failure mode.');
  process.exit(2);
}

// ── Report ─────────────────────────────────────────────────────────────────────────────
// PENDING is deliberately NOT in this sum — that is the whole concession, and the reason it
// is safe is `stalePending`, which is. See `symbol_status` in vectors.json.
const bad = failures.length + notLanded.length + stalePending.length;
if (process.argv.includes('--json')) {
  console.log(JSON.stringify(
    { compared, failed: failures.length, failures, notLanded, pending: pendingSymbols,
      stalePending, unscoredGroups, pinned, unscoreable }, null, 2));
} else {
  console.log('map seam contract — client side');
  console.log(`  vectors : ${VECTORS}`);
  console.log(`  compared: ${compared} assertions`);
  if (pinned.length) {
    const byDefect = new Map();
    for (const p of pinned) {
      if (!byDefect.has(p.defect)) byDefect.set(p.defect, []);
      byDefect.get(p.defect).push(p);
    }
    console.log(`\n  PINNED KNOWN DEFECTS — ${pinned.length} assertion(s) failing AS RECORDED.`);
    console.log('  These are not passes. Each is a named, attributed disagreement that this');
    console.log('  round deliberately did not fix; if the defect is fixed the pin goes RED.');
    for (const [id, list] of byDefect) {
      const d = DEFECTS[id] || {};
      console.log(`\n    ${id}  ${d.title || ''}`);
      console.log(`        site  : ${d.site || '?'}`);
      console.log(`        owner : ${d.owner || 'unassigned'}`);
      if (d.clears_when) console.log(`        clears: ${d.clears_when}`);
      for (const p of list) {
        console.log(`      · [${p.group}] ${p.name} ${p.field}`);
        console.log(`          contract: ${JSON.stringify(p.contract)}`);
        console.log(`          client  : ${JSON.stringify(p.actual)}`);
      }
    }
  }
  if (stalePending.length) {
    console.log(`\n  STALE PENDING — ${stalePending.length} symbol(s) HAVE LANDED but vectors.json`);
    console.log('  still calls them `pending`. Their vectors are already being scored (the');
    console.log('  manifest looks the symbol up rather than trusting the field), so this is a');
    console.log('  one-word edit: set "status": "live".');
    console.log('  It is not bookkeeping. While the entry reads `pending`, an ABSENT symbol is');
    console.log('  forgiven — so a later rename of this now-landed function would be forgiven');
    console.log('  too, and the axis would go unscored behind a green run.');
    for (const s of stalePending) console.log(`    ${s.fn}  (${s.file})  role ${s.role}`);
  }
  if (pendingSymbols.length) {
    console.log(`\n  PENDING — ${pendingSymbols.length} symbol(s) not written yet. NOT A FAILURE.`);
    console.log('  These vectors were authored CONTRACT-FIRST, so having nothing to score yet is');
    console.log('  the intended condition, not a regression: the implementer is scored against a');
    console.log('  spec nobody reverse-engineered from their own code. They begin scoring the');
    console.log('  moment the symbol appears — no promotion needed for that to happen.');
    console.log('  What IS unscored in the meantime is listed under each entry.');
    for (const n of pendingSymbols) {
      console.log(`\n    ${n.fn}  (${n.file})`);
      console.log(`        owner : ${n.owner}`);
      if (n.blocks) console.log(`        blocks: ${n.blocks}`);
      if (n.shape) console.log(`        shape : ${n.shape}`);
    }
  }
  if (notLanded.length) {
    console.log(`\n  NOT LANDED — ${notLanded.length} required symbol(s) absent; those invariants are UNSCORED.`);
    console.log('  `required` means OVERDUE, not merely unscheduled — an unscheduled axis is');
    console.log('  declared `pending` by the Lead PM and reported above instead.');
    console.log('  This is a CONTRACT failure, not a harness failure. It is not skipped and not');
    console.log('  xfailed: a contract the code does not meet yet is a red contract, and a');
    console.log('  comfortable green is how the previous round shipped two HIGH defects to review.');
    for (const n of notLanded) {
      console.log(`\n    ${n.fn}  (${n.file})`);
      console.log(`        owner : ${n.owner}`);
      if (n.blocks) console.log(`        blocks: ${n.blocks}`);
      if (n.shape) console.log(`        shape : ${n.shape}`);
    }
  }
  // Reported at TOP LEVEL, not nested under NOT LANDED. It used to sit inside that block,
  // which meant a `pending` symbol would populate this list and print nothing — the blast
  // radius of the wait would have been invisible in exactly the state that is allowed to be
  // green. Whichever status blocks a group, the cost of the block is stated.
  if (unscoredGroups.length) {
    console.log('\n  GROUPS LEFT UNSCORED by the absent symbols above (wired, blocked — NOT unwired):');
    for (const g of unscoredGroups) {
      console.log(`    ${g.group}  [${g.invariant}]`);
      console.log(`        waiting on: ${g.missing.join(', ')}`);
    }
  }
  if (unscoreable.length) {
    console.log(`\n  NOT SCOREABLE HERE — ${unscoreable.length} axis/axes this harness refuses`);
    console.log('  to claim. Listed rather than counted: an assertion that re-types the value it');
    console.log('  checks passes against an implementation that stopped producing it.');
    for (const u of unscoreable) {
      console.log(`    [${u.group}] ${u.name} ${u.field}`);
      console.log(`        ${u.why}`);
    }
  }
  const qualifier = pinned.length ? ' (outside the pinned defects above)' : '';
  if (failures.length === 0) {
    console.log(`\n  result  : ${notLanded.length
      ? 'no divergence in what COULD be scored (see NOT LANDED above)'
      : `MATCHES the contract${qualifier}`}`);
  } else {
    console.log(`\n  result  : ${failures.length} DIVERGENCE(S)${qualifier} — the client does not meet the contract\n`);
    for (const f of failures) {
      console.log(`    [${f.group}] ${f.name} ${f.field}${f.kind ? `   <${f.kind.toUpperCase()}>` : ''}`);
      console.log(`        contract: ${JSON.stringify(f.expected)}`);
      console.log(`        client  : ${JSON.stringify(f.actual)}`);
    }
    console.log(`\n  The server side is pinned to the same file by contracts/map_seam/test_seam_contract.py.`);
    console.log(`  Where the two answers differ, the CONTRACT decides — not whichever side was written first.`);
  }
  console.log('\n  DECLARED DIVERGENCES (not agreement) — green here means each side still gives');
  console.log('  ITS OWN documented answer, not that the two answers match:');
  console.log('    compose_divergence_cases            missing key component: client drops it,');
  console.log('                                        registrar refuses the row, overlay pads "".');
  console.log('    valid_die_ref_home_divergence_cases ref with no table and no home table:');
  console.log('                                        server resolves, client refuses.');
  console.log('    valid_die_refused_render_*          on `refused` the server draws NOTHING');
  console.log('                                        (basis=None); the client cannot, so it');
  console.log('                                        renders the pre-M4 circle AND surfaces');
  console.log('                                        the refusal. The surfacing is pinned,');
  console.log('                                        not just the source string.');
}
process.exit(bad ? 1 : 0);
