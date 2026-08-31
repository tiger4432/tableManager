/**
 * M4 CLIENT-ONLY SURFACE — deliberately NOT a second scorer.
 *
 * `contracts/map_seam/client_harness.mjs` scores INV-M4-1 and INV-M4-2 as of 2026-07-29:
 * the basis vocabulary for every case, passthrough in both polarities, `ref_cell_wins` for
 * every declared cell, `circle_cell_loses`, and the fixture-activity guards. **Do not restate
 * any of that here.** Re-deriving the same answers in a file that agrees with itself is how a
 * round gets reported as "83 matched, 0 diverged" while the real contract has divergences.
 *
 * What is left is what the seam contract structurally does NOT own, and each entry says why:
 *
 *   read_only      Neither function may write. The harness injects module state and reads a
 *                  return value; a function that also MUTATED that state would score green
 *                  and corrupt the next case. Nothing in the contract can see it.
 *   access_shapes  The harness reads the basis through the module global `validDie`. That is
 *                  only a valid measurement if the global and the explicit `state` argument
 *                  are the same code path. This is the check that licenses the harness's
 *                  chosen access shape.
 *   frame_window   `physFrameOverride` suspending the mask is a CLIENT invariant (the frame
 *                  stack has no server counterpart), so the seam has no vector for it. It is
 *                  MAP_EDITOR_SPEC §5.1: inside a frame window the SOURCE map's coordinate
 *                  system is being solved, and cutting it with THIS map's mask stencils one
 *                  map with another's — screen fine, stored coordinates wrong.
 *   chip           The rename's only user-visible surface. A basis string that matches no
 *                  branch renders the refusal chip for a perfectly resolved reference while
 *                  every number stays right. The harness never touches the DOM.
 *
 * Symbols are sliced with the HARNESS'S OWN slicer, lifted from its source rather than
 * reimplemented, so a change to how the contract extracts symbols reaches this file too.
 *
 *   node client2/tests/m4_symbol_extractability_probe.mjs
 *   node client2/tests/m4_symbol_extractability_probe.mjs --mutate
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const HARNESS = join(ROOT, 'contracts', 'map_seam', 'client_harness.mjs');
const VECTORS = join(ROOT, 'contracts', 'map_seam', 'vectors.json');
const MAP_SRC = readFileSync(join(ROOT, 'client2', 'src', 'map_editor.js'), 'utf8').replace(/\r\n/g, '\n');
const spec = JSON.parse(readFileSync(VECTORS, 'utf8').replace(/\r\n/g, '\n'));

// ── The harness's OWN slicer, lifted rather than reimplemented ──────────────────────────
const sliceFunction = (() => {
  const src = readFileSync(HARNESS, 'utf8').replace(/\r\n/g, '\n');
  const m = /\nfunction sliceFunction\(source, name\) \{[\s\S]*?\n\}/.exec(src);
  if (!m) {
    console.error('PROBE FAILURE: could not lift sliceFunction out of client_harness.mjs.');
    console.error('The harness changed shape. Re-read it before trusting anything below.');
    process.exit(2);
  }
  const box = { die: (msg) => { throw new Error(msg); } };
  vm.createContext(box);
  vm.runInContext(`${m[0]}\nglobalThis.__slice = sliceFunction;`, box);
  return box.__slice;
})();

const ROLES = {
  valid_die_basis: 'validDieBasis',      // contract client_symbols.valid_die_basis
  valid_die_at: 'isValidDieAt',          // contract client_symbols.valid_die_at
  render_chip: 'renderValidDieChip',     // not a seam symbol — the user-visible surface
};

function build(mutator) {
  const pieces = [];
  for (const [role, fn] of Object.entries(ROLES)) {
    let code = sliceFunction(MAP_SRC, fn);
    if (!code) return { error: `'${fn}' (role ${role}) is NOT extractable by the harness slicer` };
    pieces.push(mutator ? mutator(role, code) : code);
  }
  // Same sandbox shape the contract harness uses for these symbols.
  const sandbox = {
    console, validDie: { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
  };
  vm.createContext(sandbox);
  try { vm.runInContext(pieces.join('\n'), sandbox); }
  catch (e) { return { error: `extracted sources did not evaluate: ${e && e.message}` }; }
  for (const fn of Object.values(ROLES)) {
    if (typeof sandbox[fn] !== 'function') return { error: `'${fn}' did not evaluate to a function` };
  }
  return { sandbox };
}

// The canonical vocabulary is READ FROM THE CONTRACT, never spelled out here — a literal
// would be a second declaration of the very thing this round unified.
const VOCAB = [...new Set((spec.valid_die_basis_cases || [])
  .filter(c => c.expect_source).map(c => c.expect_source))];

function runChecks(sandbox) {
  const out = [];
  const A = (name, expected, actual, note) => out.push({
    name, ok: JSON.stringify(expected) === JSON.stringify(actual), expected, actual, note: note || '',
  });
  const { validDieBasis, isValidDieAt, renderValidDieChip } = sandbox;
  const refState = (cells) => ({
    basis: 'ref', keys: new Set(cells.map(([x, y]) => `${x}_${y}`)),
    reason: '', ref: { table: 't', mapKey: 'k' }, raw: 'TPL_1',
  });

  A('vocabulary/contract_has_three_states', 3, VOCAB.length, VOCAB.join('|'));

  // --- read_only ----------------------------------------------------------------------
  // A value snapshot is NOT enough: `v.reason = v.reason || ''` writes without changing the
  // value and a before/after comparison calls it clean. The write itself is what matters, so
  // the state is handed over behind a Proxy that records every set/delete.
  {
    const writes = [];
    const track = (obj, tag) => new Proxy(obj, {
      set(t, p, v) { writes.push(`${tag}.${String(p)}=`); return Reflect.set(t, p, v); },
      defineProperty(t, p, d) { writes.push(`${tag}.def:${String(p)}`); return Reflect.defineProperty(t, p, d); },
      deleteProperty(t, p) { writes.push(`${tag}.del:${String(p)}`); return Reflect.deleteProperty(t, p); },
    });

    const raw = refState([[1, 1], [2, 2]]);
    const keysBefore = [...raw.keys].sort().join(',');
    const st = track(raw, 'arg');
    validDieBasis(st);
    isValidDieAt(null, 1, 1, false, st);
    isValidDieAt(null, 99, 99, true, st);
    A('read_only/argument_state_untouched', [], writes.slice());
    A('read_only/argument_keyset_untouched', keysBefore, [...raw.keys].sort().join(','));

    writes.length = 0;
    const mod = track({ basis: 'circle', keys: null, reason: '', ref: null, raw: undefined }, 'module');
    sandbox.validDie = mod;
    validDieBasis(); isValidDieAt(null, 1, 1, true); isValidDieAt(null, 1, 1, false);
    A('read_only/module_state_untouched', [], writes.slice());
    // The binding too: `validDie = {...v}` writes nothing THROUGH the proxy, it replaces it.
    A('read_only/module_binding_not_reassigned', true, sandbox.validDie === mod);
    sandbox.validDie = { basis: 'circle', keys: null, reason: '', ref: null };
  }

  // --- access_shapes: this is what licenses the harness's global-stub measurement -------
  {
    const probes = [[1, 1, false], [40, 40, false], [3, 3, true], [0, 0, true]];
    for (const st of [refState([[1, 1], [40, 40]]),
                      { basis: 'circle', keys: null, reason: '', ref: null },
                      { basis: 'refused', keys: null, reason: 'X', ref: null },
                      null]) {
      sandbox.validDie = st;
      const viaGlobal = [...probes.map(([x, y, c]) => isValidDieAt(null, x, y, c)), validDieBasis()];
      sandbox.validDie = { basis: 'circle', keys: null, reason: '', ref: null };   // poisoned
      const viaArg = [...probes.map(([x, y, c]) => isValidDieAt(null, x, y, c, st)), validDieBasis(st)];
      A(`access_shapes/global_equals_argument(${st ? st.basis : 'null'})`, viaGlobal, viaArg,
        'the harness reads the global; the two must be one code path, not two');
    }
    sandbox.validDie = { basis: 'circle', keys: null, reason: '', ref: null };
  }

  // --- frame_window: a CLIENT invariant, no seam vector exists ---------------------------
  {
    const st = refState([[1, 1]]);
    sandbox.validDie = st;
    // The frame ARRIVES AS AN ARGUMENT now, so the window is opened by passing it rather than
    // by assigning a module binding. Keeping the old assignment would leave a fixture that
    // sets state nothing reads -- still green, and measuring nothing.
    const WINDOW_FRAME = { waferDia: 300, chipX: 2.5, chipY: 2.5 };
    // Inside the window the caller's circle verdict must survive untouched in BOTH polarities:
    // (9,9) is undeclared and would be masked out; (1,1) is declared and would be forced in.
    const inWindow = [isValidDieAt(WINDOW_FRAME, 9, 9, true), isValidDieAt(WINDOW_FRAME, 1, 1, false)];
    const outside = [isValidDieAt(null, 9, 9, true), isValidDieAt(null, 1, 1, false)];
    A('frame_window/mask_suspended_inside_override', [true, false], inWindow,
      'SPEC §5.1 — solving the SOURCE frame; this map\'s mask must not cut it');
    A('frame_window/window_actually_changes_the_answer', true,
      JSON.stringify(inWindow) !== JSON.stringify(outside),
      `outside the window the same two probes give ${JSON.stringify(outside)} — if these matched, the check would be inert`);
    sandbox.validDie = { basis: 'circle', keys: null, reason: '', ref: null };
  }

  // --- chip: the rename's only user-visible surface --------------------------------------
  {
    const chipFor = (state) => {
      const nodes = new Map();
      const mk = (id) => ({ id, className: '', textContent: '', title: '', style: {}, parentNode: null });
      const host = mk('paint-lock-indicator');
      host.parentNode = { insertBefore: (n) => { n.parentNode = host.parentNode; nodes.set(n.id, n); } };
      nodes.set(host.id, host);
      sandbox.document = { getElementById: (id) => nodes.get(id) || null, createElement: () => mk('') };
      sandbox.validDie = state;
      sandbox.renderValidDieChip();
      sandbox.validDie = { basis: 'circle', keys: null, reason: '', ref: null };
      const chip = nodes.get('valid-die-indicator');
      return chip ? { shown: chip.style.display !== 'none', text: chip.textContent } : { shown: false, text: '' };
    };
    const circle = chipFor({ basis: 'circle', keys: null, reason: '', ref: null });
    A('chip/circle_adds_no_control', { shown: false, text: '' }, circle,
      'a map with no declaration must not grow a control — UI complexity budget');
    const ref = chipFor(refState([[1, 1], [2, 2]]));
    A('chip/ref_names_the_reference', true, ref.shown && /유효 다이/.test(ref.text) && /\(2\)/.test(ref.text), ref.text);
    A('chip/ref_is_not_the_refusal_chip', false, /미해석/.test(ref.text), ref.text);
    const refused = chipFor({ basis: 'refused', keys: null, reason: 'X', ref: { table: 't', mapKey: 'k' } });
    A('chip/refused_says_so', true, refused.shown && /미해석/.test(refused.text), refused.text);
  }
  return out;
}

// ── Run ─────────────────────────────────────────────────────────────────────────────────
const built = build(null);
if (built.error) { console.error(`PROBE FAILURE: ${built.error}`); process.exit(2); }
const results = runChecks(built.sandbox);
const bad = results.filter(r => !r.ok);
console.log('M4 client-only surface (the seam contract scores INV-M4-1/M4-2 — run client_harness.mjs)');
console.log(`  slicer : lifted from ${HARNESS}`);
console.log(`  vocab  : ${VOCAB.join('|')}   (read from vectors.valid_die_basis_cases)`);
console.log(`  checks : ${results.length}, ${bad.length} failed\n`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${results.length} ${bad.length}`);
for (const r of results) {
  console.log(`  ${r.ok ? 'ok  ' : 'FAIL'} ${r.name}${r.note ? `   (${r.note})` : ''}`);
  if (!r.ok) {
    console.log(`         expected: ${JSON.stringify(r.expected)}`);
    console.log(`         actual  : ${JSON.stringify(r.actual)}`);
  }
}

// ── Mutation controls ───────────────────────────────────────────────────────────────────
if (process.argv.includes('--mutate')) {
  // ── Mutation anchors: presence AND uniqueness, refusing at exit 2 ───────────────────────
  // Adopted from `geometry_origin_reseat_harness.mjs`, which has carried this for longer.
  // 🔴 A `replace` on a NON-UNIQUE anchor lands on the first match and the mutant is then
  //    "caught" by whatever that unrelated site broke -- a green mutation score containing a
  //    kill nobody chose. Measured in this repo 2026-08-05.
  // 🔴 An UNAPPLIED mutant is not a caught mutant. Re-point a stale anchor; never delete it.
  function once(src, find, repl) {
    const i = src.indexOf(find);
    if (i < 0) die(`mutation anchor not found: ${find.slice(0, 80)}`);
    if (src.indexOf(find, i + 1) >= 0) die(`mutation anchor is not unique: ${find.slice(0, 80)}`);
    return src.slice(0, i) + repl + src.slice(i + find.length);
  }

  const MUTANTS = [
    // Deliberately a VALUE-PRESERVING write: this is the mutant a before/after snapshot
    // cannot see, and the reason the read_only check uses a Proxy.
    { id: 'basis_normalises_in_place', why: 'the reader writes back the same value — invisible to a snapshot, still a write',
      f: (role, code) => role === 'valid_die_basis'
        ? once(code, "if (!v) return 'circle';", "if (!v) return 'circle';\n  v.reason = v.reason || '';") : code },
    // Placed on the `ref` path where `v` is guaranteed non-null, so the kill is attributable
    // to the read_only check rather than to an incidental TypeError.
    { id: 'at_mutates_argument', why: 'the judgement stamps the state it was handed — corrupts the next case',
      f: (role, code) => role === 'valid_die_at'
        ? once(code, 'return v.keys.has(`${physX}_${physY}`);',
          "v.reason = 'cached';\n  return v.keys.has(`${physX}_${physY}`);") : code },
    { id: 'at_reassigns_module_binding', why: 'the judgement caches a derived state over the module binding',
      f: (role, code) => role === 'valid_die_at'
        ? once(code, 'const v = (state === undefined) ? validDie : state;',
          'const v = (state === undefined) ? validDie : state;\n  validDie = { ...v };') : code },
    { id: 'argument_ignored', why: 'the explicit state argument is dropped — the two access shapes diverge',
      f: (role, code) => role === 'valid_die_at'
        ? once(code, 'const v = (state === undefined) ? validDie : state;', 'const v = validDie;') : code },
    { id: 'frame_window_ignored', why: 'target mask applied while solving the source frame',
      f: (role, code) => role === 'valid_die_at'
        ? once(code, 'if (frame) return circleInside;', '') : code },
    { id: 'chip_gates_on_retired_spelling', why: "chip still branches on basis === 'map'",
      f: (role, code) => role === 'render_chip' ? once(code, "basis === 'ref'", "basis === 'map'") : code },
  ];
  console.log('\n  MUTATION CONTROLS — a surviving mutant means the check above it is inert.\n');
  let inert = 0;
  for (const m of MUTANTS) {
    const b = build(m.f);
    let killedBy = [];
    if (b.error) killedBy = [`build: ${b.error}`];
    else { try { killedBy = runChecks(b.sandbox).filter(r => !r.ok).map(r => r.name); }
           catch (e) { killedBy = [`threw: ${e && e.message}`]; } }
    if (killedBy.length === 0) inert++;
    console.log(`  ${killedBy.length ? 'KILLED  ' : 'SURVIVED'} ${m.id}  — ${m.why}`);
    if (killedBy.length) console.log(`           by: ${killedBy.join(', ')}`);
  }
  console.log(`\n  ${MUTANTS.length - inert}/${MUTANTS.length} mutants killed.`);
  if (inert) process.exit(1);
}
process.exit(bad.length ? 1 : 0);
