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
 * TWO KINDS OF MISSING SYMBOL, AND THEY MEAN DIFFERENT THINGS:
 *   `status: live`     in vectors.client_symbols — exists today. If it cannot be found it
 *                      was RENAMED or reshaped: exit 2, harness failure, nothing compared.
 *   `status: required` — the contract needs it and the client has not landed it. A contract
 *                      failure, not a harness failure: the dependent groups are reported
 *                      NOT LANDED, per invariant, and the run exits 1.
 * Neither is ever green.
 *
 * Exit codes: 0 = client meets the contract | 1 = divergence(s)/not landed | 2 = harness failure.
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
  'client2/src/transfer_plan.js': readFileSync(join(ROOT, 'client2', 'src', 'transfer_plan.js'), 'utf8'),
};

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

/** Slice `function NAME(...) { ... }` out of source by brace matching. Null if absent. */
function sliceFunction(source, name) {
  const decl = new RegExp(`(^|\\n)\\s*function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) return null;
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = source.indexOf('{', m.index + m[0].length - 1);
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
const notLanded = [];
const pieces = [];
const have = new Set();
for (const c of spec.client_consts || []) {
  const code = sliceConst(SRC[c.file], c.name);
  if (!code) {
    die(`const '${c.name}' is gone from ${c.file}. The canonicalizer it backs cannot be `
      + `evaluated, so nothing would be compared. Update vectors.json client_consts.`);
  }
  pieces.push(code);
}
for (const [role, m] of Object.entries(spec.client_symbols)) {
  if (role === '$comment') continue;
  const source = SRC[m.file];
  if (source === undefined) die(`client_symbols.${role} names an unknown file: ${m.file}`);
  const code = sliceFunction(source, m.fn);
  if (code) { pieces.push(code); have.add(role); continue; }
  if (m.status === 'live') {
    die(`'${m.fn}' is gone from ${m.file} — renamed, removed, or reshaped. The contract names `
      + `it in vectors.json client_symbols.${role}. Update that manifest deliberately; do `
      + `not delete the check.`);
  }
  notLanded.push({ role, fn: m.fn, file: m.file, why: m.$why || '' });
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
const composeApp = (c, values) => withSchema(c, () => FN.compose_from_meta(values));
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
const bad = failures.length + notLanded.length;
if (process.argv.includes('--json')) {
  console.log(JSON.stringify(
    { compared, failed: failures.length, failures, notLanded, pinned, unscoreable }, null, 2));
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
  if (notLanded.length) {
    console.log(`\n  NOT LANDED — ${notLanded.length} required symbol(s) absent; those invariants are UNSCORED:`);
    for (const n of notLanded) {
      console.log(`    ${n.fn}  (${n.file})`);
      if (n.why) console.log(`        ${n.why}`);
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
