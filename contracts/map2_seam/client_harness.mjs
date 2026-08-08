// ═══════════════════════════════════════════════════════════════════════════════
// MAP EDITOR 2 SEAMS -- the CLIENT half, scored against the shared contract vectors.
//
//   node contracts/map2_seam/client_harness.mjs [--json]
//
// The file being scored is `contracts/map2_seam/vectors.json`, and it is the same file
// `contracts/map2_seam/test_map2_seam_contract.py` reads. Nothing here hardcodes an
// expectation: every assertion comes out of the contract, against THE SAME expected value the
// server is scored against -- never against the server's answer.
//
// 🔴 THIS HARNESS IMPORTS. IT DOES NOT CUT SOURCE TEXT.
//    Every client symbol is reached with a real `import`. That is possible because
//    `client2/src/map2/` is built to MAP_ALIGNMENT_SPEC 0.3 rule (1) -- takes arguments,
//    returns values, holds no module state -- so import-verifiability is guaranteed by
//    construction rather than by harness work. The consequence that matters: there is no
//    extraction step, so this harness cannot die the way `split_registry_harness.mjs` died at
//    U6, where five symbols were deleted, the slicing threw, and the harness sat dead for
//    weeks with nobody looking.
//
//    A RENAME still kills it -- an import of a symbol that no longer exists throws -- and that
//    is deliberate: EXIT CODE 2, naming the missing symbol, rather than exit 0 having scored
//    nothing. A harness that goes quiet is worse than one that goes red.
//
// 🔴 IT LIVES IN contracts/, NOT client2/tests/.
//    The rename detector scopes `client2/src`, so a harness parked under `client2/tests/` is
//    outside what any rename check looks at. That is measured, not hypothetical.
//
// WHAT A GREEN RUN MEANS. That THE CLIENT meets the contract. The seam is scored only when
// this AND the pytest command have both been run and both are green. Everything measured on
// this box was measured on a DEVELOPMENT box and says nothing about production.
// ═══════════════════════════════════════════════════════════════════════════════

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..');
const CLIENT = join(REPO, 'client2', 'src', 'map2');

const VECTORS = JSON.parse(readFileSync(join(HERE, 'vectors.json'), 'utf8'));
const SHAPES = JSON.parse(readFileSync(join(HERE, 'orientation_shapes.json'), 'utf8'));

// The ONLY place the two sides' spellings are related. Both scorers read it from the contract;
// a scorer holding its own copy would be the second implementation of the mapping.
const AXIS = Object.fromEntries(
  Object.entries(VECTORS.$axis_spelling).filter(([k]) => !k.startsWith('$')));
const SERVER_AXES = Object.keys(AXIS);

const JSON_MODE = process.argv.includes('--json');

// ── scoreboard ──────────────────────────────────────────────────────────────────
const results = { pass: 0, fail: 0, pending: 0, divergence: 0 };
const failures = [];
const pendings = [];
const divergences = [];

function ok(what) { results.pass++; if (!JSON_MODE) console.log(`  ok    ${what}`); }
function bad(what, detail) {
  results.fail++;
  failures.push({ what, detail });
  if (!JSON_MODE) console.log(`  FAIL  ${what}\n        ${String(detail).replace(/\n/g, '\n        ')}`);
}
function pending(axis, why) {
  results.pending++;
  pendings.push({ axis, why });
  if (!JSON_MODE) console.log(`  PEND  ${axis}\n        ${why.replace(/\n/g, '\n        ')}`);
}
function divergent(what, detail) {
  results.divergence++;
  divergences.push({ what, detail });
  if (!JSON_MODE) console.log(`  DIV   ${what}\n        ${detail.replace(/\n/g, '\n        ')}`);
}
function section(title) { if (!JSON_MODE) console.log(`\n${title}`); }

// ── symbol resolution ───────────────────────────────────────────────────────────
// An UNLISTED CALLEE makes its CALLER unevaluable, and silently. Resolve everything first, and
// exit 2 with the name if anything is gone. Do not degrade to "0 assertions, exit 0".
async function loadModule(file, wanted) {
  let mod;
  try {
    mod = await import(`file:///${join(CLIENT, file).replace(/\\/g, '/')}`);
  } catch (e) {
    console.error(
      `\nRENAME OR DELETION DETECTED (exit 2)\n`
      + `  client2/src/map2/${file} did not import: ${e.message}\n`
      + `  This harness scores nothing until that is resolved. It exits 2 rather than 0 on\n`
      + `  purpose: a harness that goes quiet is indistinguishable from a passing one.`);
    process.exit(2);
  }
  const missing = wanted.filter(n => mod[n] === undefined);
  if (missing.length) {
    console.error(
      `\nRENAME OR DELETION DETECTED (exit 2)\n`
      + `  client2/src/map2/${file} no longer exports: ${missing.join(', ')}\n`
      + `  These are listed in vectors.json client_symbols. Either they were renamed -- in\n`
      + `  which case update the contract WITH the rename, in the same commit -- or the lane\n`
      + `  has not landed them yet, in which case say so in the contract rather than letting\n`
      + `  the harness die silently.`);
    process.exit(2);
  }
  return mod;
}

const decl = await loadModule('declaration.js', [
  'frameFromDeclaration', 'geometryDeclaration', 'noEvidenceValue', 'visualDimensions',
  'ORIENTATION_AXES', 'DECLARATION_TOKENS', 'VALUE_CAN_INDICATE_PROVENANCE']);
const seating = await loadModule('seating.js', ['seatOf', 'computeSeating', 'compareSeatings']);
const cand = await loadModule('candidates.js', ['candidateList', 'parseCandidateId']);

// excel_io.js is a lane in flight. Missing is PENDING, not exit 2 -- a vector authored before
// its implementation is the point of writing it early.
let excel = null;
try {
  excel = await import(`file:///${join(CLIENT, 'excel_io.js').replace(/\\/g, '/')}`);
} catch { /* reported below */ }

// ═══════════════════════════════════════════════════════════════════════════════
// S1  THE DECLARATION VOCABULARY
// ═══════════════════════════════════════════════════════════════════════════════
section('S1  declaration vocabulary -- agreement cases');

const sameValue = (a, b) => Object.is(a, b);

for (const c of VECTORS.orientation_agreement_cases.cases) {
  const frame = decl.frameFromDeclaration(c.meta);
  let clean = true;

  for (const [serverAxis, want] of Object.entries(c.expect || {})) {
    const clientAxis = AXIS[serverAxis];
    const got = frame.axes[clientAxis];
    if (!got) {
      bad(`${c.id} / ${serverAxis}`, `the client frame has no axis '${clientAxis}'`);
      clean = false; continue;
    }
    if (got.source !== want.source) {
      bad(`${c.id} / ${serverAxis} source`,
        `expected '${want.source}', got '${got.source}'\nwhy: ${c.$why}\nkills: ${c.$kills}`);
      clean = false;
    }
    if (!sameValue(got.value, want.value)) {
      bad(`${c.id} / ${serverAxis} value`,
        `expected ${JSON.stringify(want.value)}, got ${JSON.stringify(got.value)}. `
        + 'The VALUE is what the reader will actually use, so a matching token with a '
        + 'different value is still a divergence.');
      clean = false;
    }
    // The module's own stated invariant, and the swap it exists to prevent: `frame.<axis>`
    // must be the DECLARED value, never the post-`|| dflt` legacy fold. Sourcing the flat
    // fields from `legacy` would delete the module's purpose while leaving every parity
    // assertion green.
    if (!sameValue(frame[clientAxis], got.value)) {
      bad(`${c.id} / ${serverAxis} flat field`,
        `frame.${clientAxis} is ${JSON.stringify(frame[clientAxis])} but `
        + `frame.axes.${clientAxis}.value is ${JSON.stringify(got.value)}. `
        + 'The flat field must be the declared value, not the legacy fold.');
      clean = false;
    }
  }

  for (const [serverAxis, wantSource] of Object.entries(c.expect_source_only || {})) {
    const got = frame.axes[AXIS[serverAxis]];
    if (got.source !== wantSource) {
      bad(`${c.id} / ${serverAxis} source`, `expected '${wantSource}', got '${got.source}'`);
      clean = false;
    }
  }
  if (clean) ok(c.id);
}

section('S1  declaration vocabulary -- DECLARED DIVERGENCES');
if (!JSON_MODE) {
  console.log('  (these are not agreement. Each records what BOTH sides answer today and asks');
  console.log('   the lead PM which one is the contract. Green here means "still diverging as');
  console.log('   recorded", never "fine".)');
}

for (const c of VECTORS.orientation_divergence_cases.cases) {
  const frame = decl.frameFromDeclaration(c.meta);
  const axes = c.$also ? [c.axis, 'grid_start_y'] : [c.axis];
  let held = true;
  for (const serverAxis of axes) {
    const got = frame.axes[AXIS[serverAxis]];
    if (got.source !== c.client.source || !sameValue(got.value, c.client.value)) {
      held = false;
      bad(`${c.id} / ${serverAxis}`,
        `the CLIENT's half of a recorded divergence changed.\n`
        + `recorded: ${JSON.stringify(c.client)}\n`
        + `now:      ${JSON.stringify({ value: got.value, source: got.source })}\n`
        + `server side of this divergence: ${JSON.stringify(c.server)}\n`
        + 'If this was a deliberate fix, move the case into orientation_agreement_cases; '
        + 'leaving it here makes the contract lie about the seam.');
    }
  }
  if (held) {
    divergent(c.id,
      `server ${JSON.stringify(c.server)}  vs  client ${JSON.stringify(c.client)}\n`
      + `${c.$failure_scenario || c.$why}`);
  }
}

section('S1  declaration vocabulary -- production census');
{
  const census = {};
  for (const axis of SERVER_AXES) census[axis] = {};
  for (const shape of SHAPES.shapes) {
    const frame = decl.frameFromDeclaration(shape.meta);
    for (const serverAxis of SERVER_AXES) {
      const tok = frame.axes[AXIS[serverAxis]].source;
      census[serverAxis][tok] = (census[serverAxis][tok] || 0) + shape.count;
    }
  }
  const expect = VECTORS.orientation_census.expect;
  for (const axis of SERVER_AXES) {
    const got = census[axis], want = expect[axis];
    const keys = new Set([...Object.keys(got), ...Object.keys(want)]);
    const same = [...keys].every(k => got[k] === want[k]);
    if (same) ok(`census / ${axis}  ${JSON.stringify(got)}`);
    else bad(`census / ${axis}`,
      `expected ${JSON.stringify(want)}\nmeasured ${JSON.stringify(got)}\n`
      + VECTORS.orientation_census.$expect_notes[0]);
  }
  const total = SHAPES.shapes.reduce((a, s) => a + s.count, 0);
  if (total === SHAPES.$row_total) ok(`census covers ${total} rows`);
  else bad('census population', `the shapes file no longer covers ${SHAPES.$row_total} rows (${total})`);
}

section('S1  declaration vocabulary -- structural');
{
  // Rule N compares against WHAT THE READER INVENTS. If the no-evidence table is a second
  // transcription, it drifts the first time a default moves and nothing says so.
  let clean = true;
  for (const clientAxis of ['rotation', 'side', 'invertY', 'startX', 'startY']) {
    const viaHelper = decl.noEvidenceValue(clientAxis);
    const viaEmpty = decl.frameFromDeclaration({}).axes[clientAxis].value;
    if (!sameValue(viaHelper, viaEmpty)) {
      clean = false;
      bad(`noEvidenceValue(${clientAxis})`,
        `${JSON.stringify(viaHelper)} != the value an absent key actually produces `
        + `(${JSON.stringify(viaEmpty)}). The no-evidence value must be ASKED OF THE READER, `
        + 'not written down twice.');
    }
  }
  if (clean) ok('no-evidence values are read out of the reader, not restated');

  // The WHOLE-META verdict. A different question from the per-axis cases above, and measured
  // to be one they cannot answer: deleting the borrow branch from this port left every
  // orientation case green while the two sides answered differently on the same meta.
  for (const c of VECTORS.geometry_declaration_cases.cases) {
    const got = decl.geometryDeclaration(c.meta);
    if (got === c.expect) {
      ok(`geometry verdict / ${c.id}`);
    } else {
      bad(`geometry verdict / ${c.id}`,
        `expected '${c.expect}', got '${got}'\nwhy: ${c.$why}\nkills: ${c.$kills}`);
    }
  }

  const tokens = new Set(decl.DECLARATION_TOKENS);
  // `assumed` joined 2026-08-05 (MAP_ALIGNMENT_SPEC 9.1): a source map with no declared wafer
  // spec is scored on the reference floor's, and the token says the verdict stands on a
  // borrowed one. The list is pinned rather than counted -- "there are N" is not the
  // invariant, "these exact words, on both sides" is.
  // `confirmed` joined 2026-08-06 (`map_overlay.py` [D7]): a source map MATCHING a per-product
  // valid-die map is evidence it shares that product's wafer geometry, so a confirmed match
  // makes the geometry a DERIVATION rather than an assumption -- ranked above `assumed`, below
  // `declared`, because nobody measured the map itself.
  //
  // 🔴 THIS LITERAL IS THE THIRD PLACE THE VOCABULARY IS WRITTEN DOWN, AND IT IS WHY THIS
  //    UPDATE IS A HAND EDIT. `declaration.js` holds the list, this line holds a copy, and
  //    `test_map2_seam_contract.test_token_vocabulary_is_five_and_shared` holds a THIRD copy
  //    that names five constants one by one -- so the server could grow `assumed` and then
  //    `confirmed` with nothing anywhere going red. Pinning is right; three independent pins
  //    are not. Moving the vocabulary into vectors.json and having both runners read it is
  //    boarded as its own change and is deliberately NOT done here.
  const want = new Set(['declared', 'auto_registered', 'absent', 'unparsable', 'indeterminate',
                        'assumed', 'confirmed']);
  if (tokens.size === want.size && [...want].every(t => tokens.has(t))) {
    ok('token vocabulary is the shared set');
  } else {
    bad('token vocabulary',
      `client tokens ${JSON.stringify([...tokens])} != the shared set `
      + `${JSON.stringify([...want])}. The server's constants must change in the same commit, `
      + 'or the two sides need a mapping table -- and a mapping '
      + 'table is the second spelling this contract exists to prevent.');
  }

  // The 2026-08-05 start ruling, in code: start is NOT on the value-test list.
  const valueTested = new Set(decl.VALUE_CAN_INDICATE_PROVENANCE);
  if (!valueTested.has('startX') && !valueTested.has('startY')) {
    ok('start axes are marker-only (the 2026-08-05 ruling)');
  } else {
    bad('start provenance',
      'startX / startY appear in VALUE_CAN_INDICATE_PROVENANCE. The ruling is that provenance '
      + 'for start comes from the MARKER ONLY. Running the value test there puts the two sides '
      + 'in DIFFERENT buckets from the SAME rule -- the server reader invents 1 and the client '
      + 'reader invents 0, which inverted the verdict on 660 of 668 rows.');
  }

  // The exported rotation domain must actually gate the parser, or it is decoration. This is
  // the client-internal half of the `rotation_forty_five` divergence.
  const fortyFive = decl.frameFromDeclaration({ rotation: 45 }).axes.rotation;
  if (fortyFive.source === 'declared' && fortyFive.value === 45) {
    divergent('rotation domain is exported but not enforced',
      "declaration.js exports ROTATIONS = [0, 90, 180, 270] with the comment '45 is a number, "
      + "not a rotation', and rotationAxis does not consult it: a stored 45 comes back as "
      + "{value: 45, source: 'declared'}. visualDimensions then silently treats it as 0. This "
      + 'is a SECOND SPELLING INSIDE ONE MODULE, not only a cross-side one. The server answers '
      + "{value: 0, source: 'unparsable'} for the same input.");
  } else {
    ok('rotation domain gates the parser');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// S2  THE COORDINATE ROUND TRIP AND THE BOUNDING-BOX BASIS
// ═══════════════════════════════════════════════════════════════════════════════
section('S2  coordinate round trip -- the box and the mirror');
{
  const group = VECTORS.frame_basis_cases;
  const declared = group.client_expected_failure;
  let agreed = 0, diverged = 0;
  const detail = [];

  for (const c of group.cases) {
    const m = c.meta;
    // INPUTS ONLY -- no expected value in this file was touched.
    // The `phys_*` fields were being dropped here. A bounding box is the extent of the wafer
    // CIRCLE across the grid, so without a diameter, a chip pitch and an edge exclusion there
    // is no circle and no box can exist -- the seating layer had no way to compute the term
    // this group pins, whatever its implementation. Passing the fixture's own physical spec
    // through is what lets the client answer the question the contract is asking.
    const frame = {
      rotation: m.rotation, side: m.side,
      cols: m.grid_cols, rows: m.grid_rows,
      startX: m.grid_start_x, startY: m.grid_start_y,
      invertY: m.grid_y_invert,
      phys_wafer_dia: m.phys_wafer_dia,
      phys_chip_x: m.phys_chip_x, phys_chip_y: m.phys_chip_y,
      phys_offset_x: m.phys_offset_x, phys_offset_y: m.phys_offset_y,
      phys_edge_margin: m.phys_edge_margin,
    };
    const cells = c.expect_seats.map(p => ({ x: p.stored[0], y: p.stored[1] }));
    const got = seating.computeSeating(cells, frame);
    for (let i = 0; i < c.expect_seats.length; i++) {
      const want = c.expect_seats[i].seat;
      const seat = got.seats[i];
      if (seat.x === want[0] && seat.y === want[1]) agreed++;
      else {
        diverged++;
        detail.push(`${c.id} stored(${c.expect_seats[i].stored}) contract[${want}] `
          + `client[${seat.x},${seat.y}]`);
      }
    }
  }

  // 🔴 THE RESOLVED PATH, ADDED 2026-08-05 WHEN THE DIVERGENCE ACTUALLY CLOSED.
  //    This branch was missing, and its absence was itself a small instance of what this
  //    contract is about: the harness could express "the defect is here", and "the defect
  //    disappeared and you forgot to say so" -- but not "the defect is gone". So the moment
  //    the fix landed, removing the declaration crashed on `declared.name` instead of going
  //    green. A mechanism that can only ratchet one way stops being trusted the first time
  //    someone has to work around it, and the workaround is always to re-declare the
  //    divergence. `client_divergence_closed` keeps the record of what was wrong.
  if (!declared) {
    if (diverged === 0) {
      ok(`frame_basis: all ${agreed} pinned seats agree`,
        'The box term and the y mirror are both in `seating.js`. This group was a declared '
        + 'divergence at 14 of 14 wrong; the record of what it was is kept in '
        + '`client_divergence_closed`.');
    } else {
      bad(`frame_basis: ${diverged} of ${agreed + diverged} pinned seats diverge`,
        'This group is scored as AGREEMENT -- no divergence is declared for it -- so a '
        + 'mismatch here is a regression, not a known gap:\n' + detail.join('\n'));
    }
  } else if (diverged > 0 && agreed === 0) {
    // The declared, NAMED expected failure. Not an anonymous permanent red.
    divergent(`${declared.name} (${diverged} pinned seats, all divergent)`,
      `symbol: ${declared.symbol}   owner: ${declared.owner}\n`
      + declared.$two_omissions.join('\n') + '\n'
      + detail.slice(0, 6).join('\n') + '\n'
      + `measured full-fixture mismatch: ${JSON.stringify(declared.measured_mismatch)}`);
  } else if (diverged === 0) {
    // The direction that must fail: the defect is gone and the contract still declares it.
    bad(`${declared.name} -- THE DECLARED DIVERGENCE HAS DISAPPEARED`,
      'Every pinned seat now agrees with the contract, which means seating.js grew the box '
      + 'term and the y mirror. That is the fix, and it is good news -- but this group is '
      + 'still declared as a divergence, so the contract now lies about the seam. Move '
      + '`client_expected_failure` out of vectors.json and score this group as agreement. '
      + 'This assertion exists so that switch cannot be forgotten.');
  } else {
    bad(`${declared.name} -- PARTIALLY fixed`,
      `${agreed} pinned seats now agree and ${diverged} still diverge:\n`
      + detail.join('\n') + '\n'
      + 'A partial fix is the dangerous state: the omission that remains is invisible on the '
      + 'fixtures that now pass. Both terms -- the bbox offset AND the y mirror -- are needed, '
      + 'and their shifts differ per branch, so a fixture exercising one under-reports the other.');
  }

  // `seatOf` alone is a faithful transcription of `cell_to_physical` and is scored on its own,
  // so the report can say WHICH half is wrong. This is the point of splitting the layer.
  let seatOfClean = true;
  for (const c of group.cases) {
    const m = c.meta;
    const frame = { rotation: m.rotation, side: m.side, cols: m.grid_cols, rows: m.grid_rows };
    const quarter = m.rotation === 90 || m.rotation === 270;
    const vc = quarter ? m.grid_rows : m.grid_cols;
    const vr = quarter ? m.grid_cols : m.grid_rows;
    // Corner identity that holds for every one of the eight frames: the four corners of the
    // visual grid map onto the four corners of the physical grid, bijectively.
    const corners = [[0, 0], [vc - 1, 0], [0, vr - 1], [vc - 1, vr - 1]];
    const seen = new Set(corners.map(([cc, rr]) => {
      const p = seating.seatOf(frame, cc, rr);
      return `${p.x},${p.y}`;
    }));
    if (seen.size !== 4) {
      seatOfClean = false;
      bad(`seatOf / ${c.id}`,
        `the four grid corners collapsed onto ${seen.size} seats. seatOf is not a bijection `
        + 'under this frame, which means the rotation or the side mirror is applied about the '
        + 'wrong axis. Under a quarter turn the side flip lands on ROWS, not columns.');
    }
  }
  if (seatOfClean) ok('seatOf is a bijection on grid corners under all fixture frames');

  // The omission, named directly rather than inferred from the seat mismatch, so the report
  // says WHY and not only THAT.
  const probe = seating.computeSeating(
    [{ x: 5, y: 5 }],
    { rotation: 0, side: 'front', cols: 9, rows: 9, startX: 0, startY: 0, invertY: true });
  const probeNoInvert = seating.computeSeating(
    [{ x: 5, y: 5 }],
    { rotation: 0, side: 'front', cols: 9, rows: 9, startX: 0, startY: 0, invertY: false });
  if (probe.seats[0].y === probeNoInvert.seats[0].y) {
    divergent('computeSeating ignores invertY entirely',
      'The same stored coordinate seats identically with invertY true and false. The y mirror '
      + 'is not applied at all -- the identifier does not occur in seating.js. declaration.js '
      + 'produces the axis and nothing consumes it, so a y-inverted map is drawn unmirrored '
      + 'while the server mirrors it: EVERY row lands somewhere else.');
  } else {
    ok('computeSeating reads invertY');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// S3  SCORING -- the client's share is an ABSENCE
// ═══════════════════════════════════════════════════════════════════════════════
section('S3  scoring -- the client does not score (ruling, 2026-08-05)');
{
  // The candidate set is the ONE scoring axis that IS a round trip: the screen and the scorer
  // must not disagree about what candidate 3 is.
  const ids = cand.candidateList().map(c => c.id);
  if (ids.length === 8 && new Set(ids).size === 8) ok(`candidate set is 8 distinct ids`);
  else bad('candidate set', `expected 8 distinct ids, got ${JSON.stringify(ids)}`);

  const unparseable = ids.filter(id => cand.parseCandidateId(id) === null);
  if (unparseable.length === 0) ok('every candidate id round-trips through parseCandidateId');
  else bad('candidate id round trip', `these do not parse: ${unparseable.join(', ')}`);

  // Compare against the server's set WITHOUT importing python: the server's spelling is
  // `rot<deg>_<walk start>` and the contract states the expected shape. The pytest half asserts
  // the server's CANDIDATE_FRAMES equals its own 8; this half asserts the client's equals the
  // same strings. Two halves, one expectation -- which is what makes it a seam assertion.
  //
  // 🔴 UPDATED 2026-08-08 with the axis, not to make a red bar green. The second axis stopped
  //    being the mirror (`front`/`back`) and became the corner the equipment numbered its walk
  //    from (`tl`/`tr`), server-side in `map_alignment.candidate_frames`. The mirror spellings
  //    stay READABLE on both halves (`parse_frame` / `parseCandidateId`) because stored
  //    confirmations hold them -- they are simply no longer candidates.
  const expected = [];
  for (const rot of [0, 90, 180, 270]) for (const start of ['tl', 'tr'])
    expected.push(`rot${rot}_${start}`);
  const same = ids.length === expected.length && expected.every(e => ids.includes(e));
  if (same) ok('client candidate ids equal the stored spelling the server scores');
  else bad('candidate id vocabulary',
    `client ${JSON.stringify(ids)} vs the stored spelling ${JSON.stringify(expected)}. `
    + 'A screen listing its own eight and a server scoring its own eight is the second '
    + 'spelling of the same question.');

  // A DUPLICATE GUARD. The ruling is that the server scores and the client does not; a client
  // scorer would be the second implementation of the answer, and the day the two disagree is
  // the day the screen is healthy and the number is wrong.
  const scorerish = [];
  for (const [name, mod] of [['declaration.js', decl], ['seating.js', seating],
                             ['candidates.js', cand]]) {
    for (const key of Object.keys(mod)) {
      if (/^(score|rank|solveShift|enumerateCandidates|winner)/i.test(key)) {
        scorerish.push(`${name}:${key}`);
      }
    }
  }
  if (scorerish.length === 0) ok('no client module exports a candidate scorer');
  else bad('a second scorer appeared on the client',
    `${scorerish.join(', ')}\nThe ruling of 2026-08-05 is that the SERVER scores and the `
    + 'client does not. Scoring on both sides is not redundancy; it is two answers to one '
    + 'question, and only one of them is on screen.');

  // `compareSeatings` is allowed -- it is comparison, not scoring -- but it must return COUNTS
  // ONLY. Measured: a coverage ratio ranks a correctly-oriented candidate one cell off (94%)
  // BELOW three wrongly-oriented ones (98/97/95%).
  const a = seating.computeSeating([{ x: 0, y: 0 }, { x: 1, y: 0 }],
    { rotation: 0, side: 'front', cols: 4, rows: 4, startX: 0, startY: 0 });
  const b = seating.computeSeating([{ x: 0, y: 0 }],
    { rotation: 0, side: 'front', cols: 4, rows: 4, startX: 0, startY: 0 });
  const cmp = seating.compareSeatings(a, b);
  const ratioKeys = Object.keys(cmp).filter(k => /pct|percent|ratio|coverage/i.test(k));
  const fractional = Object.entries(cmp)
    .filter(([, v]) => typeof v === 'number' && v > 0 && v < 1);
  if (ratioKeys.length === 0 && fractional.length === 0) {
    ok('compareSeatings returns counts only, never a ratio');
  } else {
    bad('a ratio reached the comparison result',
      `${JSON.stringify([...ratioKeys, ...fractional.map(([k]) => k)])}\n`
      + 'A coverage percentage provably inverts the ranking. A number nobody ranks on today '
      + 'is a number somebody ranks on next quarter.');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// S4  THE EXCEL FORM
// ═══════════════════════════════════════════════════════════════════════════════
section('S4  excel form');
if (!excel) {
  pending('excel_io round trip',
    'client2/src/map2/excel_io.js did not import. The vectors are authored and waiting; a '
    + 'vector waiting for an implementation is useful, an implementation with no vector is '
    + 'what got us here.');
} else {
  const renameInv = VECTORS.excel_form_cases.$invariants_pinned_now[0];
  const got = excel.INGESTION_RENAME;
  if (!got) {
    bad('INGESTION_RENAME', 'excel_io.js no longer exports INGESTION_RENAME');
  } else {
    const want = renameInv.expect;
    const same = Object.keys(want).every(k => got[k] === want[k])
      && Object.keys(got).length === Object.keys(want).length;
    if (same) ok('INGESTION_RENAME matches the read-only ingestion parser (duplicate guard)');
    else bad('INGESTION_RENAME drifted',
      `client ${JSON.stringify(got)} vs the parser's ${JSON.stringify(want)}\n`
      + '`dev_env/ingestion_workspace/` is READ ONLY, so the client is the side that must '
      + 'follow. The pytest half reads the parser source and asserts the same pair.');
  }

  if (typeof excel.readMapForm !== 'function' || typeof excel.writeMapForm !== 'function') {
    pending('excel_io round trip', 'readMapForm / writeMapForm are not both exported yet');
  } else {
    pending('excel form round trip against a real operator artefact',
      'dev_env/ingestion_workspace/bonding_map/archives/ is EMPTY on this box, so nothing was '
      + 'round-tripped against a file an operator actually produced. A synthetic round trip '
      + 'proves the code is self-consistent -- which a re-implementation that copied the '
      + 'legacy defects would also be. Owner: the excel_io lane.');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// S5  align_applied.origin -- UNSCORED ON THIS SIDE, AND SAID SO
// ═══════════════════════════════════════════════════════════════════════════════
section('S5  align_applied.origin');
{
  const consumers = VECTORS.align_origin_cases.client_consumers_fail_open;
  pending('align_applied.origin -- client consumers',
    'Both consumers live in client2/src/map_editor.js, which is FROZEN and which this contract '
    + 'may not edit:\n' + consumers.$sites.map(s => '  ' + s).join('\n')
    + '\nReaching them needs either a module with heavy DOM state (impossible) or an assertion '
    + 'on source TEXT -- the technique that killed three harnesses this round. Re-typing the '
    + 'comparison here would score nothing: the copy would also pass the wrong inputs.\n'
    + 'FAILURE SCENARIO IF LEFT: ' + consumers.$failure_scenario + '\n'
    + 'WHAT WOULD SCORE IT: one exported pure predicate, e.g. alignWasApplied(origin).');
}

// ═══════════════════════════════════════════════════════════════════════════════
section('unscored axes (declared in the contract)');
for (const a of VECTORS.unscored_axes.axes) {
  if (a.axis.includes('client consumers')) continue;   // already reported above
  pending(a.axis, `${a.why}\nWHAT WOULD SCORE IT: ${a.what_would_score_it}`);
}

// ═══════════════════════════════════════════════════════════════════════════════
if (JSON_MODE) {
  console.log(JSON.stringify({ results, failures, divergences, pendings }, null, 2));
} else {
  console.log(`\n${'='.repeat(78)}`);
  console.log(`pass ${results.pass}   fail ${results.fail}   `
    + `declared-divergence ${results.divergence}   pending ${results.pending}`);
  console.log(
    'A declared divergence is NOT agreement. It records that the two sides answer differently\n'
    + 'today, with both answers pinned, and it is the lead PM who decides which one becomes the\n'
    + 'contract. Pending does not block the suite; it blocks round completion.');
  console.log('='.repeat(78));
}

process.exit(results.fail === 0 ? 0 : 1);
