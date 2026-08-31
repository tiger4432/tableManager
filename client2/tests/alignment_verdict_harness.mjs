/**
 * ALIGNMENT VERDICT + DECODE -- scores `client2/src/map2/verdict.js` and
 * `client2/src/map2/decode.js`, and uses `client2/tests/oracle/alignment_scoring_oracle.mjs` as an
 * INDEPENDENT EXPECTATION SET (an oracle, not shipping code -- the server scores).
 *
 * 🔴 THIS HARNESS DOES NOT SLICE SOURCE. It `import`s the modules under test. No `node:vm`, no
 *    `sliceFunction`, no `readFileSync` of any `.js` on the baseline path. The modules were
 *    written to take arguments and return values, so importing them is possible by
 *    construction rather than by arrangement (MAP_ALIGNMENT_SPEC 0.3, rule 1).
 *    (`--mutate` DOES read module text, to build in-memory variants imported as data: URIs.
 *    That path never writes a file and never runs on the baseline.)
 *
 * WHAT IS SCORED
 *
 *  A. EIGHT COVERS SIXTEEN. `fixtures/alignment_oracle_cases.json` holds the EXACT composed
 *     stored->physical mapping of all 16 (rotation x side x y-invert) tuples, computed by
 *     importing and running `server/map_overlay._frame_transformer` -- the production path,
 *     not a transcription. This harness checks that the oracle's 8 candidates realise all 16
 *     up to a translation, which is the only claim that licenses dropping `grid_y_invert`
 *     from the candidate list, because a translation is what the shift solver removes.
 *     Both the exact and the modulo-translation counts are reported: quotienting by
 *     translation collapses to 8 BY CONSTRUCTION, so the modulo number alone proves nothing
 *     and the spec records two earlier rounds that were fooled by exactly that.
 *
 *  B. THE START JACOBIAN, PROBED VS PRODUCTION. d(phys)/d(start) is compared tuple by tuple
 *     against production's own answer. The point is not that they agree; it is that the SIGN
 *     FLIPS between tuples, so the retired sentence `phys(start) = phys(0) + (-sx,-sy)` is
 *     scored as false on the tuples where it is false.
 *
 *  C. RECOVERING A DISHONEST DECLARATION. Real cells and real declared geometry, re-expressed
 *     under a different frame by production's own `make_frame_transform`, then labelled with
 *     an orientation nobody wrote them under. The search must find the frame the coordinates
 *     were actually written under and must rank the stored declaration below it.
 *
 *  D. THE VERDICT. Never ranks below the margin threshold; both thresholds evaluated and
 *     neither substituting for the other; the two section-4 causes kept apart; shape parity
 *     with `verdict_placeholder.js` so `verdict_bridge.js` is a one-line swap.
 *
 *  E. THE DECODER. No ratio gets into the client, by name or by value, and the reference-kind
 *     inference is marked as an inference.
 *
 * FIXTURES -- PROVENANCE, NEVER MIXED.
 *   `fixtures/alignment_oracle_cases.json` is derived from a DEVELOPMENT DATABASE and from the
 *   production python path, read-only. Nothing measured from it is a production fact, and the
 *   file says so in its own `provenance` block. Where a case has a DEAD DEFECT AXIS it says
 *   which one, in the case's `note`, rather than leaving a reader to assume full coverage.
 *
 * Run:  node client2/tests/alignment_verdict_harness.mjs [--mutate] [--verbose]
 * Read-only. Exit: 0 green | 1 a check failed | 2 harness failure.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'map2');
const VERBOSE = process.argv.includes('--verbose');

function die(m) {
  console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`);
  process.exit(2);
}

let CASES;
try {
  CASES = JSON.parse(readFileSync(join(HERE, 'fixtures', 'alignment_oracle_cases.json'), 'utf8').replace(/\r\n/g, '\n'));
} catch (e) {
  die(`cannot read fixtures/alignment_oracle_cases.json: ${e.message}`);
}

const verdictMod = await import('../src/map2/verdict.js');
const decodeMod = await import('../src/map2/decode.js');
const oracleMod = await import('./oracle/alignment_scoring_oracle.mjs');
const declMod = await import('../src/map2/declaration.js');
const placeholderMod = await import('../src/map2/verdict_placeholder.js');

// ── the scored body, run once on the baseline and once per mutant ──────────────
function run(V, D, O) {
  const failures = [];
  let compared = 0;
  const ok = (what, cond) => { compared++; if (!cond) failures.push(what); };
  const eq = (what, got, want) => {
    compared++;
    if (!Object.is(got, want)) failures.push(`${what}: got ${fmt(got)}, want ${fmt(want)}`);
  };
  const evidence = [];
  const say = (s) => { evidence.push(s); };

  const frameOf = (meta) => declMod.frameFromDeclaration(meta);

  // ══ A. EIGHT COVERS SIXTEEN ═════════════════════════════════════════════════
  const a16 = CASES.alias16;
  eq('A: production path yields 8 distinct EXACT mappings over 16 tuples',
    a16.distinctExact, 8);
  ok('A: the modulo-translation count is reported too (it collapses by construction, so it '
    + 'cannot be the evidence on its own)', a16.distinctModuloTranslation === 8);

  // Seat the same sample rectangle under each of the oracle's 8 candidates, using layer 4.
  const baseFrame = {
    cols: a16.grid.cols, rows: a16.grid.rows,
    startX: a16.grid.startX, startY: a16.grid.startY,
    rotation: 0, side: 'front', invertY: false,
  };
  const sampleCells = a16.sample.map(([x, y]) => ({ x, y, value: null }));
  const candImages = new Map();
  for (const cand of O.candidateFrames(baseFrame)) {
    const seated = seatViaLayer4(sampleCells, cand.frame);
    candImages.set(cand.id, seated);
  }
  eq('A: the oracle emits exactly 8 candidates', candImages.size, 8);

  let coveredExact = 0;
  let coveredModT = 0;
  const uncovered = [];
  for (const t of a16.tuples) {
    const target = t.image;
    let exact = false;
    let modt = false;
    for (const img of candImages.values()) {
      if (sameExact(img, target)) exact = true;
      if (sameModuloTranslation(img, target)) modt = true;
    }
    if (exact) coveredExact++;
    if (modt) coveredModT++;
    else uncovered.push(`rot${t.rotation}_${t.side}_inv${t.invertY}`);
  }
  eq('A: all 16 production tuples are realised by one of the 8 candidates UP TO A TRANSLATION '
    + '(this is what licenses dropping grid_y_invert; the shift solver removes the translation)',
    coveredModT, 16);
  say(`A: 16 production tuples -> covered exactly ${coveredExact}/16, `
    + `up to translation ${coveredModT}/16; uncovered=[${uncovered.join(',')}]`);

  // ══ B. THE START JACOBIAN ═══════════════════════════════════════════════════
  // Production's own d(phys)/d(start), tuple by tuple. The claim being scored is that it is
  // NOT constant -- the retired sentence said (-sx,-sy) everywhere.
  const jacSet = new Set(a16.tuples.map(t => JSON.stringify(t.jacobian)));
  ok(`B: d(phys)/d(start) is NOT one table for all tuples (measured distinct: ${jacSet.size})`,
    jacSet.size > 1);
  const minusMinus = a16.tuples.filter(t =>
    t.jacobian.dStartX[0] === -1 && t.jacobian.dStartX[1] === 0
    && t.jacobian.dStartY[0] === 0 && t.jacobian.dStartY[1] === -1).length;
  ok(`B: the retired sentence phys(start)=phys(0)+(-sx,-sy) holds on only some tuples `
    + `(measured: ${minusMinus} of 16)`, minusMinus > 0 && minusMinus < 16);
  say(`B: distinct Jacobians over 16 tuples = ${jacSet.size}; `
    + `tuples matching the retired (-sx,-sy) sentence = ${minusMinus}/16`);

  // The oracle PROBES the Jacobian instead of transcribing it. Probed vs production, per
  // candidate. The bounding box does not depend on start, so these must agree exactly even
  // though layer 4 omits the bbox term.
  let jacMatches = 0;
  for (const t of a16.tuples) {
    if (t.invertY) continue;                    // layer 4 does not model inversion (see E below)
    const probed = O.measureStartJacobian(seatViaLayer4,
      Object.assign({}, baseFrame, { rotation: t.rotation, side: t.side }));
    if (!probed.dx) continue;
    const same = probed.dx[0] === t.jacobian.dStartX[0] && probed.dx[1] === t.jacobian.dStartX[1]
      && probed.dy[0] === t.jacobian.dStartY[0] && probed.dy[1] === t.jacobian.dStartY[1];
    if (same) jacMatches++;
    ok(`B: probed Jacobian matches production for rot${t.rotation}_${t.side}`, same);
  }
  say(`B: probed Jacobian agrees with production on ${jacMatches}/8 non-inverted tuples`);

  // ══ C. RECOVERING A DISHONEST DECLARATION ═══════════════════════════════════
  const recoveries = [];
  for (const rc of CASES.recovery) {
    const declaredFrame = frameOf(rc.targetMetaDeclared);
    const refFrame = frameOf(rc.referenceMeta);
    const scored = O.scoreSources({
      sources: [{ id: rc.label, frame: declaredFrame, cells: rc.targetCells }],
      reference: { id: `${rc.label} (reference)`, frame: refFrame, cells: rc.referenceCells },
      config: {},
    });
    const s = scored.sources[0];
    const ranked = s.candidates.slice().sort((a, b) =>
      b.agree - a.agree || a.candidate_id.localeCompare(b.candidate_id));
    const top = ranked[0];
    const second = ranked[1];
    const declared = s.candidates.find(c => c.candidate_id === rc.declaredCandidateId);
    const truth = s.candidates.find(c => c.candidate_id === rc.truthCandidateId);
    recoveries.push({ rc, s, ranked, top, second, declared, truth });

    ok(`C[${rc.label}]: every emitted number is an integer (the runtime guard did not throw)`,
      true);
    eq(`C[${rc.label}]: 8 candidates scored`, s.candidates.length, 8);

    if (rc.distinctValues > 1) {
      eq(`C[${rc.label}]: the winner is the frame the coordinates were WRITTEN under, not the `
        + 'one they are labelled with', top.candidate_id, rc.truthCandidateId);
      ok(`C[${rc.label}]: the stored declaration ranks strictly below the truth `
        + `(declared ${declared.agree} < truth ${truth.agree})`, declared.agree < truth.agree);
      ok(`C[${rc.label}]: the margin over the runner-up is a positive DIE COUNT`,
        Number.isInteger(top.agree - second.agree) && top.agree - second.agree > 0);
    }
    // "How many dies move if you read it with the wrong frame" -- the number a fixture that
    // proves nothing would report as 0.
    const moved = countMoved(rc, declaredFrame, rc.truthCandidateId, rc.declaredCandidateId);
    ok(`C[${rc.label}]: reading the declared frame instead of the true one moves cells `
      + `(measured ${moved} of ${rc.targetCells.length})`, moved > 0);
    say(`C[${rc.label}]: truth=${rc.truthCandidateId} declared=${rc.declaredCandidateId} `
      + `winner=${top.candidate_id} | agree/disc: truth ${truth.agree}/${truth.discriminating}, `
      + `declared ${declared.agree}/${declared.discriminating}, runner-up ${second.candidate_id} `
      + `${second.agree} | margin ${top.agree - second.agree} dies | discriminating set `
      + `${s.discriminatingDies} | distinct seatings ${s.distinctSeatings} | wrong-frame moves `
      + `${moved}/${rc.targetCells.length} cells`);
  }

  // ══ D. THE VERDICT ══════════════════════════════════════════════════════════
  const TH = { min_margin_dies: 5, min_discriminating_dies: 20 };

  // D0. END TO END on the two real cases: scoring counts straight into the decision. This is
  //     the product claim -- everything below it is the decision rule in isolation.
  for (const r of recoveries) {
    const v = V.decideVerdict(r.s.candidates, TH, {
      referenceKind: r.s.referenceKind, distinctSeatings: r.s.distinctSeatings,
    });
    if (r.rc.distinctValues > 1) {
      eq(`D0[${r.rc.label}]: a real dishonest declaration ends in a WINNER`, v.kind, V.VERDICT.WINNER);
      eq(`D0[${r.rc.label}]: and the winner is the truth, not the stored declaration`,
        v.winnerId, r.rc.truthCandidateId);
      ok(`D0[${r.rc.label}]: the stored declaration is ranked, but not first`,
        v.rankedIds.indexOf(r.rc.declaredCandidateId) > 0);
      say(`D0[${r.rc.label}]: verdict=${v.kind} winner=${v.winnerId} margin=${v.marginDies} dies `
        + `discriminating=${v.discriminating} blind=${v.blindCandidates}`);
    } else {
      // Uniform values: front and back put the same thing on the same dies. The honest answer
      // is that they cannot be told apart, and it must NOT be a confident first place.
      eq(`D0[${r.rc.label}]: a reference that cannot separate the candidates yields no ranking`,
        v.kind, V.VERDICT.INDISTINGUISHABLE);
      eq(`D0[${r.rc.label}]: nothing is crowned`, v.winnerId, null);
      ok(`D0[${r.rc.label}]: the tied count is reported (measured ${v.tiedCount})`, v.tiedCount >= 2);
      say(`D0[${r.rc.label}]: verdict=${v.kind} reason=${v.reason} tied=${v.tiedCount} `
        + `margin=${v.marginDies} discriminating=${v.discriminating} blind=${v.blindCandidates}`);
    }
  }

  // D1. shape parity with the placeholder, so the bridge swap is one line.
  const probe = V.decideVerdict(
    [{ candidate_id: 'rot0_front', agree: 100, discriminating: 200 },
     { candidate_id: 'rot90_front', agree: 10, discriminating: 200 }],
    TH, { referenceKind: V.REF_VALUES });
  const placeholderKeys = Object.keys(placeholderMod.decideVerdict(
    [{ candidate_id: 'rot0_front', agree: 1, discriminating: 1 }],
    { min_margin_dies: 0, min_discriminating_dies: 0 }, {}));
  for (const k of placeholderKeys) {
    ok(`D1: the drop-in keeps the placeholder's field \`${k}\``, k in probe);
  }
  for (const k of Object.keys(placeholderMod.VERDICT)) {
    eq(`D1: verdict token \`${k}\` is unchanged`, V.VERDICT[k], placeholderMod.VERDICT[k]);
  }
  for (const k of Object.keys(placeholderMod.REASON)) {
    eq(`D1: reason token \`${k}\` is unchanged`, V.REASON[k], placeholderMod.REASON[k]);
  }
  eq('D1: a clear winner is a winner', probe.kind, V.VERDICT.WINNER);
  eq('D1: winner id', probe.winnerId, 'rot0_front');
  eq('D1: margin is a die count, not a fraction', probe.marginDies, 90);

  // D2. THE RULE. Below the margin threshold, nothing is ranked.
  const tight = V.decideVerdict(
    [{ candidate_id: 'rot0_front', agree: 102, discriminating: 200 },
     { candidate_id: 'rot90_front', agree: 100, discriminating: 200 },
     { candidate_id: 'rot180_front', agree: 99, discriminating: 200 },
     { candidate_id: 'rot270_front', agree: 10, discriminating: 200 }],
    TH, { referenceKind: V.REF_VALUES, distinctSeatings: 8 });
  eq('D2: a 2-die margin under a 5-die threshold is INDISTINGUISHABLE, not a winner',
    tight.kind, V.VERDICT.INDISTINGUISHABLE);
  eq('D2: no winner is named when it is indistinguishable', tight.winnerId, null);
  eq('D2: the tied count is reported', tight.tiedCount, 3);
  eq('D2: with values available, the cause is the SYMMETRIC FOOTPRINT, not a weak reference',
    tight.reason, V.REASON.REFERENCE_FOOTPRINT_SYMMETRIC);

  // D3. The other section 4 cause. Same counts, occupancy-only reference.
  const blind = V.decideVerdict(
    [{ candidate_id: 'rot0_front', agree: 102, discriminating: 200 },
     { candidate_id: 'rot90_front', agree: 100, discriminating: 200 }],
    TH, { referenceKind: V.REF_OCCUPANCY, distinctSeatings: 2 });
  eq('D3: an occupancy-only reference gives the OTHER cause -- the repair differs',
    blind.reason, V.REASON.REFERENCE_NO_VALUES);
  ok('D3: the two causes are different tokens',
    V.REASON.REFERENCE_NO_VALUES !== V.REASON.REFERENCE_FOOTPRINT_SYMMETRIC);
  eq('D3: the blind-candidate count is measured, not assumed', blind.blindCandidates, 0);
  const blind8 = V.decideVerdict(
    Array.from({ length: 8 }, (_, i) => ({ candidate_id: `c${i}`, agree: 100, discriminating: 200 })),
    TH, { referenceKind: V.REF_OCCUPANCY, distinctSeatings: 2 });
  eq('D3: 8 candidates over 2 distinct seatings means 6 are blind -- MEASURED from the seatings',
    blind8.blindCandidates, 6);

  // D4. Both thresholds, and neither standing in for the other.
  const thin = V.decideVerdict(
    [{ candidate_id: 'rot0_front', agree: 9, discriminating: 9 },
     { candidate_id: 'rot90_front', agree: 0, discriminating: 9 }],
    TH, { referenceKind: V.REF_VALUES });
  eq('D4: a 9-die margin over 9 discriminating dies is NOT a decision',
    thin.kind, V.VERDICT.NOT_SCORABLE);
  eq('D4: and it says which threshold failed', thin.reason, V.REASON.TOO_FEW_DISCRIMINATING);
  eq('D4: the margin is still reported, so one threshold cannot hide the other',
    thin.marginDies, 9);
  eq('D4: both threshold values are reported', thin.minDiscriminating, 20);
  eq('D4: both threshold values are reported (margin)', thin.minMargin, 5);
  const both = V.decideVerdict(
    [{ candidate_id: 'a', agree: 3, discriminating: 4 }, { candidate_id: 'b', agree: 2, discriminating: 4 }],
    TH, { referenceKind: V.REF_VALUES });
  ok('D4: when both thresholds fail, both are listed in `reasons`',
    both.reasons.includes(V.REASON.TOO_FEW_DISCRIMINATING)
    && both.reasons.includes(V.REASON.MARGIN_TOO_SMALL));

  // D5. Refusals, and the borrowed degradation vocabulary.
  // 🔴 EACH OF THESE FOUR IS A SEPARATE WAY TO SAY "NOTHING WAS DECLARED", and `Number()`
  //    turns three of them into 0. A threshold of 0 means "always rank", so the sloppy
  //    spelling does not merely lose a check -- it inverts it.
  for (const [label, th] of [
    ['null', null],
    ['{}', {}],
    ['nulls', { min_margin_dies: null, min_discriminating_dies: null }],
    ['empty strings', { min_margin_dies: '', min_discriminating_dies: '' }],
  ]) {
    eq(`D5: thresholds absent as ${label} means no verdict, not a guessed one`,
      V.decideVerdict([{ candidate_id: 'a', agree: 1, discriminating: 1 }], th,
        { referenceKind: V.REF_VALUES }).reason, V.REASON.NO_THRESHOLDS);
  }
  eq('D5: no reference is its own answer',
    V.decideVerdict([], TH, { referenceKind: V.REF_NONE }).reason, V.REASON.NO_REFERENCE);
  eq('D5: a server refusal sentence is passed through verbatim',
    V.decideVerdict([], TH, { refusalDetail: '소스 맵: 물리 규격 미선언' }).refusalDetail,
    '소스 맵: 물리 규격 미선언');
  eq('D5: `align_unavailable` is reused, not respelled',
    V.degradationFor(V.decideVerdict([], TH, { referenceKind: V.REF_NONE })), 'align_unavailable');
  eq('D5: `not_declared` is what a missing threshold degrades to',
    V.degradationFor(V.decideVerdict([{ candidate_id: 'a', agree: 1, discriminating: 1 }],
      null, { referenceKind: V.REF_VALUES })), 'not_declared');
  eq('D5: an indistinguishable verdict degrades to 미상', V.degradationFor(tight), '미상');

  // D6. Determinism: identical counts must not swap places between two calls.
  const twiceA = V.decideVerdict(
    [{ candidate_id: 'rot90_front', agree: 50, discriminating: 100 },
     { candidate_id: 'rot0_front', agree: 50, discriminating: 100 }], TH, { referenceKind: V.REF_VALUES });
  const twiceB = V.decideVerdict(
    [{ candidate_id: 'rot0_front', agree: 50, discriminating: 100 },
     { candidate_id: 'rot90_front', agree: 50, discriminating: 100 }], TH, { referenceKind: V.REF_VALUES });
  eq('D6: ranking is stable regardless of input order',
    twiceA.rankedIds.join(','), twiceB.rankedIds.join(','));

  // ══ E. THE DECODER ══════════════════════════════════════════════════════════
  //
  // 🔴 THE CONTRACT MOVED ON 2026-08-05 AND SO DID THESE EXPECTATIONS. `decode.js` was
  //    retargeted to the live server payload: `per_candidate`->`candidates`,
  //    `candidate_id`->`frame`, `agree`->`agreement`, a `reference` block carrying `[x,y]`
  //    PAIRS, `refusal`, `ruling.winner`, and a `declaration` block. The decoder is not wrong
  //    here; the wire is different, so the expectations follow it.
  //
  // 🔴 AND THE INFERENCE IS GONE, WHICH MAKES THESE ASSERTIONS STRONGER, NOT WEAKER. E1 used
  //    to score "work the kind out from the floor cells, and MARK the guess as a guess". The
  //    wire now declares `reference.kind`, so what is scored instead is that the decoder READS
  //    IT STRAIGHT THROUGH AND NEVER DERIVES IT -- including the two ways a derivation would
  //    creep back: promoting a valued cell list over a declared `occupancy`, and inventing a
  //    kind when the wire did not send one. `KIND_INFERRED` is still exported but must be
  //    unreachable, and that is asserted rather than assumed.
  const goodPayload = {
    state: 'scored',
    candidates: [{ frame: 'rot0_front', agreement: 512, discriminating: 528 },
                 { frame: 'rot90_front', agreement: 400, discriminating: 528 }],
    reference: { kind: 'occupancy', state: 'resolved', cells: [[1, 1], [2, 1]] },
    sources: {
      map_count: 12,
      maps: [{ map_id: 'core_defect_map/LOT-A_05', declared_frame: 'rot0_front',
               declared_frame_source: 'declared', cell_count: 1288 }],
    },
    declaration: {
      frames: { rot0_front: 3, rot270_back: 1 },
      attested_maps: 4, unattested_maps: 8,
      axis_sources: { rotation: 'declared', side: 'indeterminate' },
    },
    ruling: { winner: 'rot270_back' },
    distinct_seatings: 8,
    excluded_total: 5,
    stats: { scored_cells: 528, elapsed_ms: 340.7 },
    refusal: null,
  };
  const withRef = (ref) => D.decodeReferenceView(Object.assign({}, goodPayload, { reference: ref }));

  const dec = D.decodeReferenceView(goodPayload);
  eq('E1: two scorings decoded', dec.scorings.length, 2);
  eq('E1: the wire says `frame`, the screen says `candidate_id`, and the rename happens here',
    dec.scorings[0].candidate_id, 'rot0_front');
  eq('E1: `agreement` lands on `agree`', dec.scorings[0].agree, 512);

  // READ, NEVER DERIVE -- all three wire kinds come through untouched and marked `declared`.
  for (const k of [V.REF_NONE, V.REF_OCCUPANCY, V.REF_VALUES]) {
    const d = withRef({ kind: k, cells: [[1, 1]] });
    eq(`E1: reference.kind "${k}" is read straight off the wire`, d.referenceKind, k);
    eq(`E1: and it is marked as DECLARED, not worked out`, d.referenceKindSource, D.KIND_DECLARED);
  }

  // 🔴 THE OVERRIDE THAT MUST NOT HAPPEN. Cells that look like they carry values do NOT
  //    promote a declared `occupancy` to `values`. This is the exact shape the deleted
  //    inference had, and it is the one that would make the screen confident and wrong: a
  //    `values` verdict says the tie is real, an `occupancy` verdict says get a better
  //    reference, and section 4 is explicit that the repair differs.
  eq('E1: a declared `occupancy` is NOT promoted by cells that look valued',
    withRef({ kind: 'occupancy', cells: [{ x: 1, y: 1, value: 'P' }, [2, 1]] }).referenceKind,
    V.REF_OCCUPANCY);
  // And the mirror: no kind on the wire is NOT filled in from the cells.
  eq('E1: an absent kind is not invented from a full cell list',
    withRef({ cells: [[1, 1], [2, 1], [3, 1]] }).referenceKind, V.REF_NONE);
  eq('E1: and it says the wire did not declare one', withRef({ cells: [[1, 1]] }).referenceKindSource,
    D.KIND_ABSENT);
  eq('E1: an UNRECOGNISED kind is refused, not passed through',
    withRef({ kind: 'circle_only', cells: [[1, 1]] }).referenceKind, V.REF_NONE);

  // 🔴 THE RETIRED TOKEN MUST BE UNREACHABLE. Exported for import compatibility, but if any
  //    payload shape can still produce it, the inference came back under a different name.
  for (const [label, ref] of [
    ['declared occupancy', { kind: 'occupancy', cells: [[1, 1]] }],
    ['declared values', { kind: 'values', cells: [[1, 1]] }],
    ['no kind, valued cells', { cells: [{ x: 1, y: 1, value: 'P' }] }],
    ['no kind, bare cells', { cells: [[1, 1]] }],
    ['no cells at all', {}],
    ['unrecognised kind', { kind: 'circle_only', cells: [[1, 1]] }],
  ]) {
    ok(`E1: KIND_INFERRED is unreachable (${label})`,
      withRef(ref).referenceKindSource !== D.KIND_INFERRED);
  }
  eq('E1: reference cells are counted as [x,y] PAIRS', dec.referenceCellCount, 2);

  // E1b. The declaration block. A COUNT PER FRAME, never a winner: the unit's maps disagree,
  // and picking among declarations is a judgement the client must not make.
  eq('E1b: declared frames arrive as a tally', dec.declaredFrameCounts.rot0_front, 3);
  eq('E1b: the minority declaration is not rounded away', dec.declaredFrameCounts.rot270_back, 1);
  ok('E1b: `declaredFrameCounts` is a map, not a single winner string',
    typeof dec.declaredFrameCounts === 'object');
  eq('E1b: unattested maps are carried, so a unanimous tally still reads as partly unmeasured',
    dec.unattestedMaps, 8);
  eq('E1b: attested maps are carried beside it', dec.attestedMaps, 4);
  eq('E1b: per-axis provenance survives the crossing', dec.axisSources.side, 'indeterminate');
  eq('E1b: a source carries its declared frame', dec.sources[0].declaredFrame, 'rot0_front');
  ok('E1b: AND who wrote it -- the raw frame alone is not evidence',
    dec.sources[0].declaredFrameSource === 'declared');
  eq("E1b: the server's ruling is carried through unchanged, not re-derived",
    dec.rulingWinnerId, 'rot270_back');
  eq('E1b: float milliseconds are rounded, not reported as unmeasured',
    dec.counts.elapsedMs, 341);

  ok('E2: a field NAMED like a ratio is refused', throws(() =>
    D.decodeReferenceView(Object.assign({}, goodPayload, { coverage_pct: 94 }))));
  ok('E2: a ratio nested inside a candidate is refused', throws(() =>
    D.decodeReferenceView(Object.assign({}, goodPayload, {
      candidates: [{ frame: 'rot0_front', agreement: 512, discriminating: 528, fitness: 0.94 }],
    }))));
  // 🔴 THIS ONE IS WHY THE RENAME NEEDED A LOOK RATHER THAN A FIND-AND-REPLACE. The count
  //    guard is keyed on FIELD NAMES, so renaming `agree` to `agreement` on the wire silently
  //    took `agreement` out of its scope -- the fraction would then be dropped by `intOrNull`
  //    as "not an integer" instead of throwing, and a server lane would keep believing its
  //    field was in use. Measured first, then fixed in `decode.js`.
  ok('E2: a count field holding a fraction is refused (under the NEW name)', throws(() =>
    D.decodeReferenceView(Object.assign({}, goodPayload, {
      candidates: [{ frame: 'rot0_front', agreement: 0.97, discriminating: 528 }],
    }))));
  ok('E2: and under every other renamed count field', throws(() =>
    D.decodeReferenceView(Object.assign({}, goodPayload, { excluded_total: 4.5 }))));
  ok('E2: including the ones nested in `stats`', throws(() =>
    D.decodeReferenceView(Object.assign({}, goodPayload, {
      stats: { scored_cells: 527.5, elapsed_ms: 340.7 },
    }))));
  ok('E2: a percentage hidden in a STRING is refused', throws(() =>
    D.decodeReferenceView(Object.assign({}, goodPayload, { refusal: '적합도 94% 입니다' }))));
  ok('E2: the error names the JSON path so the fix goes to the side that can make it', (() => {
    try { D.decodeReferenceView(Object.assign({}, goodPayload, { coverage_pct: 94 })); return false; }
    catch (e) { return Array.isArray(e.paths) && e.paths.some(p => p.includes('coverage_pct')); }
  })());
  ok('E2: `elapsed_ms` is a float on the wire and must NOT be mistaken for a ratio',
    !throws(() => D.decodeReferenceView(goodPayload)));

  // 🔴 E3 SURVIVES THE RENAME UNCHANGED IN MEANING. It is reachable on the new shape via a
  //    candidate whose `agreement` is unusable, and it is the invariant that stops the tie
  //    count shrinking without anything on screen changing.
  const dropped = D.decodeReferenceView(Object.assign({}, goodPayload, {
    candidates: [{ frame: 'rot0_front', agreement: 512, discriminating: 528 },
                 { frame: 'rot90_front', agreement: null, discriminating: 528 }],
  }));
  eq('E3: an unusable scoring is dropped', dropped.scorings.length, 1);
  ok('E3: and the drop is RECORDED, so the tie count cannot shrink silently',
    dropped.rejected.length === 1);
  ok('E3: the record names which candidate went missing',
    dropped.rejected[0].includes('rot90_front'));
  const noFrame = D.decodeReferenceView(Object.assign({}, goodPayload, {
    candidates: [{ frame: 'rot0_front', agreement: 512, discriminating: 528 },
                 { agreement: 400, discriminating: 528 }],
  }));
  eq('E3: a candidate with no frame is dropped too', noFrame.scorings.length, 1);
  ok('E3: and that drop is recorded as well', noFrame.rejected.length === 1);

  const ctx = D.verdictContext(dec);
  eq('E4: the decoder assembles the verdict context, so two call sites cannot disagree',
    ctx.referenceKind, V.REF_OCCUPANCY);
  eq('E4: a `none` reference reaches the verdict as no-reference, end to end',
    V.decideVerdict(dec.scorings, TH,
      D.verdictContext(withRef({ kind: 'none', cells: [] }))).reason, V.REASON.NO_REFERENCE);
  // The wire now carries `distinct_seatings`, so the blind count is DERIVED from a measurement
  // instead of being unavailable. Both halves are scored: derived when it is sent, and still
  // NULL when it is not -- a zero would read as "none are blind", which is a claim nobody made.
  const eightScorings = Array.from({ length: 8 },
    (_, i) => ({ candidate_id: `rot${i}_front`, agree: 100 - i, discriminating: 200 }));
  const blindPayload = Object.assign({}, goodPayload, {
    distinct_seatings: 2,
    candidates: eightScorings.map(s => ({
      frame: s.candidate_id, agreement: s.agree, discriminating: s.discriminating })),
  });
  const blindDec = D.decodeReferenceView(blindPayload);
  eq('E4: `distinct_seatings` crosses the customs post', blindDec.distinctSeatings, 2);
  eq('E4: and 8 candidates over 2 distinct seatings is 6 blind, measured not assumed',
    V.decideVerdict(blindDec.scorings, TH, D.verdictContext(blindDec)).blindCandidates, 6);
  const unmeasured = D.decodeReferenceView(
    Object.assign({}, blindPayload, { distinct_seatings: null }));
  eq('E4: an unmeasured blind count stays NULL rather than becoming 0',
    V.decideVerdict(unmeasured.scorings, TH, D.verdictContext(unmeasured)).blindCandidates, null);

  // ══ G. THE AXIS THE RULING NAMES, AND THE FRAMES NOBODY LOOKED AT ═══════════
  //
  // MEASURED ON THE WIRE, NOT INVENTED. Every number below is what
  // `GET /api/maps/alignment/view?rule=dt_job_lot_slot_attribution&map_table=dt_map
  // &params={"dt_job":"SYN-IDX-FULL-R0"}&reference=valid_die_ref:PRD-A_DT13` served on
  // 2026-08-06, trimmed to the blocks these assertions read. The two axes DISAGREE in it --
  // occupancy ranks rot0_front 88/43 over rot90_front 66/21, the index axis ranks it 88/87 over
  // 1/0 -- which is the only reason this fixture can tell a client that reads the ruled axis
  // from one that reads the first pair it finds. A fixture carrying occupancy alone cannot.
  const INDEX_WIRE = {
    state: 'scored',
    refusal: null,
    reference: { state: 'resolved', kind: 'values', cells: [[1, 1], [2, 1]] },
    sources: { map_count: 1, maps: [{ map_id: 'SYN-IDX-FULL-R0', cell_count: 88 }] },
    declaration: { frames: {}, attested_maps: 0, unattested_maps: 1, axis_sources: {} },
    ruling: {
      metric: 'index', index_axis: 'ranking', winner: 'rot0_front',
      margin: 87, discriminating: 87,
      min_margin_dies: 20, min_discriminating_dies: 20,
      sides_considered: ['front'], sides_narrowed: true, reason_code: null,
    },
    candidates: [
      { frame: 'rot0_front', state: 'scored', agreement: 88, discriminating: 43,
        index_agreement: 88, index_discriminating: 87, index_total: 88, index_margin: 87,
        value_agreement: 0, value_discriminating: 0, placed: 88, margin: 22, reason: null },
      { frame: 'rot0_back', state: 'not_considered', agreement: 0, discriminating: 0,
        index_agreement: null, index_discriminating: null, index_total: null, index_margin: null,
        value_agreement: null, value_discriminating: null, placed: 0, margin: null,
        reason: '미채점 - 면 선언 제외' },
      { frame: 'rot90_front', state: 'scored', agreement: 66, discriminating: 21,
        index_agreement: 1, index_discriminating: 0, index_total: 88, index_margin: -87,
        value_agreement: 0, value_discriminating: 0, placed: 88, margin: -22, reason: null },
      { frame: 'rot180_front', state: 'scored', agreement: 62, discriminating: 17,
        index_agreement: 1, index_discriminating: 0, index_total: 88, index_margin: -87,
        value_agreement: 0, value_discriminating: 0, placed: 88, margin: -26, reason: null },
      { frame: 'rot270_front', state: 'scored', agreement: 66, discriminating: 21,
        index_agreement: 1, index_discriminating: 0, index_total: 88, index_margin: -87,
        value_agreement: 0, value_discriminating: 0, placed: 88, margin: -22, reason: null },
    ],
    stats: { scored_cells: 88, elapsed_ms: 16 },
    excluded_total: 0,
  };
  const idx = D.decodeReferenceView(INDEX_WIRE);
  const byId = new Map(idx.scorings.map(s => [s.candidate_id, s]));

  // G1. WHICH PAIR OF NUMBERS. The occupancy column is still on the wire and is still 88/43;
  //     reading it here is the shipped bug, and it is a DIFFERENT number, not a missing one.
  eq('G1: the ruling names the index axis and the decoder reads it',
    idx.rulingMetric, 'index');
  eq('G1: so the winner\'s agreement is the INDEX count, not the occupancy count',
    byId.get('rot0_front').agree, 88);
  eq('G1: and its discriminating count is the index one (occupancy says 43)',
    byId.get('rot0_front').discriminating, 87);
  eq('G1: a losing frame reads 1 on the index axis, not the 66 occupancy gave it',
    byId.get('rot90_front').agree, 66 - 65);
  eq('G1: and 0 discriminating, not 21', byId.get('rot90_front').discriminating, 0);
  eq('G1: the keys are named so a reader can see WHICH pair was taken',
    idx.rulingScoringKeys.agree, 'index_agreement');

  // The axis table is a mirror of `map_alignment.py:1473-1478`. All four rows, so a metric
  // that stops mapping is red here rather than on one live unit.
  for (const [metric, a, d] of [
    ['index', 'index_agreement', 'index_discriminating'],
    ['values', 'value_agreement', 'value_discriminating'],
    ['values_weighted', 'value_agreement', 'value_discriminating'],
    ['occupancy', 'agreement', 'discriminating'],
    [null, 'agreement', 'discriminating'],
    ['values_ranked', 'agreement', 'discriminating'],   // unrecognised -> the server's own else
  ]) {
    eq(`G1: metric "${metric}" reads \`${a}\``, D.scoringKeysFor(metric).agree, a);
    eq(`G1: metric "${metric}" reads \`${d}\``, D.scoringKeysFor(metric).discriminating, d);
  }
  // A weighted axis is FRACTIONAL on purpose (`map_alignment.py:1109`), and demanding an
  // integer there would drop all eight candidates on every weighted payload.
  const weighted = D.decodeReferenceView(Object.assign({}, INDEX_WIRE, {
    ruling: Object.assign({}, INDEX_WIRE.ruling, { metric: 'values_weighted' }),
    candidates: [{ frame: 'rot0_front', state: 'scored', agreement: 88, discriminating: 43,
                   value_agreement: 41.25, value_discriminating: 12.5 }],
  }));
  eq('G1: a weighted agreement is carried as the fraction it is, not dropped as a non-integer',
    weighted.scorings.length === 1 ? weighted.scorings[0].agree : null, 41.25);

  // G2. A FRAME NOBODY LOOKED AT IS NOT A FRAME THAT LOST. The wire marks the four back frames
  //     `not_considered` and ships placeholder zeroes beside them; reading the zeroes is how
  //     they rendered as `0 / 0` against a winner's 88.
  eq('G2: the excluded frame is KEPT in the report -- narrowing the search must not narrow it',
    idx.scorings.length, 5);
  const skipped = byId.get('rot0_back');
  eq('G2: and it is carried with NO count, never with the placeholder zero',
    skipped.agree, null);
  eq('G2: neither half of the pair is invented', skipped.discriminating, null);
  eq('G2: the server\'s own word for what happened to it survives the crossing',
    skipped.state, D.CAND_NOT_CONSIDERED);
  eq('G2: and its own sentence rides with it, so the screen need not compose one',
    skipped.reason, '미채점 - 면 선언 제외');
  ok('G2: it is NOT reported as a rejected/unusable row -- it is a state, not a decode failure',
    idx.rejected.length === 0);
  // A frame that WAS looked at and could not be measured is the third word, kept apart.
  const refused = D.decodeReferenceView(Object.assign({}, INDEX_WIRE, {
    candidates: [Object.assign({}, INDEX_WIRE.candidates[0],
      { state: 'not_scorable', index_agreement: null, index_discriminating: null, reason: null })],
  }));
  eq('G2: `not_scorable` is its own state, not folded into `not_considered`',
    refused.scorings[0].state, D.CAND_NOT_SCORABLE);
  eq('G2: and it too carries no count', refused.scorings[0].agree, null);

  // G3. THE DECISION USES ONLY WHAT WAS MEASURED. `Number(null) === 0`, so a candidate with no
  //     count can enter the ranking as a zero and become the runner-up whose score sets the
  //     winner's margin. The margin below is the server's own: 88 - 1 = 87, NOT 88 - 0 = 88.
  const idxThresholds = idx.rulingThresholds;
  eq('G3: the ruling carries the thresholds it applied, per axis',
    idxThresholds && idxThresholds.min_discriminating_dies, 20);
  const v = V.decideVerdict(idx.scorings, idxThresholds, D.verdictContext(idx));
  eq('G3: the client reaches the SERVER\'S verdict on the server\'s own axis',
    v.kind, V.VERDICT.WINNER);
  eq('G3: and the same winner', v.winnerId, INDEX_WIRE.ruling.winner);
  eq('G3: and the same margin in dies -- the unconsidered frames did not enter as zeroes',
    v.marginDies, INDEX_WIRE.ruling.margin);
  eq('G3: and the same discriminating count', v.discriminating, INDEX_WIRE.ruling.discriminating);
  eq('G3: exactly the four frames the server scored are ranked', v.rankedIds.length, 4);
  ok('G3: and the excluded frame is not one of them',
    !v.rankedIds.includes('rot0_back'));
  // A half-declared threshold is NO threshold. `verdict.js` refuses to rank without one on
  // purpose, and completing it here would be the invented default that rule exists to stop.
  for (const half of [{ min_margin_dies: 20 }, { min_discriminating_dies: 20 }, {}]) {
    eq(`G3: a ruling carrying ${JSON.stringify(half)} declares no thresholds at all`,
      D.decodeReferenceView(Object.assign({}, INDEX_WIRE,
        { ruling: Object.assign({}, INDEX_WIRE.ruling, {
          min_margin_dies: undefined, min_discriminating_dies: undefined }, half) }
      )).rulingThresholds, null);
  }

  // G4. The integrality guard follows the new names. A fraction under `index_agreement` is the
  //     same defect `agreement: 0.97` was, and must throw rather than be dropped silently.
  ok('G4: a fraction under `index_agreement` is refused, not quietly dropped', throws(() =>
    D.decodeReferenceView(Object.assign({}, INDEX_WIRE, {
      candidates: [Object.assign({}, INDEX_WIRE.candidates[0], { index_agreement: 0.97 })],
    }))));
  ok('G4: but an honest weighted float is NOT refused -- weighted dies are not a ratio',
    !throws(() => D.decodeReferenceView(Object.assign({}, INDEX_WIRE, {
      candidates: [Object.assign({}, INDEX_WIRE.candidates[0], { value_agreement: 41.25 })],
    }))));

  // ══ F. NO RATIO ANYWHERE IN THE ORACLE'S OUTPUT ═════════════════════════════
  for (const r of recoveries) {
    let allInt = true;
    walkNumbers(r.s, (n) => { if (!Number.isInteger(n)) allInt = false; });
    ok(`F[${r.rc.label}]: every number in the scoring result is an integer`, allInt);
  }

  return { compared, failures, evidence };
}

// ── helpers ────────────────────────────────────────────────────────────────────
function seatViaLayer4(cells, frame) {
  // Bound late so a mutant of the oracle still uses the real layer 4.
  return computeSeatingRef(cells, frame);
}
let computeSeatingRef;
{
  const m = await import('../src/map2/seating.js');
  computeSeatingRef = m.computeSeating;
}

function sameExact(seated, target) {
  if (seated.seats.length !== target.length) return false;
  for (let i = 0; i < target.length; i++) {
    if (seated.seats[i].x !== target[i][0] || seated.seats[i].y !== target[i][1]) return false;
  }
  return true;
}

function sameModuloTranslation(seated, target) {
  if (seated.seats.length !== target.length || target.length === 0) return false;
  const dx = target[0][0] - seated.seats[0].x;
  const dy = target[0][1] - seated.seats[0].y;
  for (let i = 0; i < target.length; i++) {
    if (seated.seats[i].x + dx !== target[i][0] || seated.seats[i].y + dy !== target[i][1]) return false;
  }
  return true;
}

/**
 * How many stored cells land on a DIFFERENT die when read under the declared frame instead of
 * the true one. A fixture where this is 0 has verified nothing (map-pm lesson, 2026-07-30).
 */
function countMoved(rc, declaredFrame, truthId, declaredId) {
  const asTruth = seatUnder(rc.targetCells, declaredFrame, truthId);
  const asDeclared = seatUnder(rc.targetCells, declaredFrame, declaredId);
  let moved = 0;
  for (let i = 0; i < asTruth.length; i++) {
    if (asTruth[i].x !== asDeclared[i].x || asTruth[i].y !== asDeclared[i].y) moved++;
  }
  return moved;
}

function seatUnder(cells, frame, candId) {
  // The second axis is the WALK now (`tl`/`tr`), not the mirror. A walk moves no cell, so
  // both seat as `front`; `front`/`back` stay accepted because recorded vectors and stored
  // confirmations still spell it that way (`parse_frame` carries the same legacy).
  const m = /^rot(0|90|180|270)_(front|back|tl|tr)$/.exec(candId);
  if (!m) throw new Error(`seatUnder: '${candId}' is not a frame token`);
  const f = Object.assign({}, {
    cols: frame.cols, rows: frame.rows, startX: frame.startX, startY: frame.startY,
    invertY: !!frame.invertY,
  }, { rotation: Number(m[1]), side: m[2] === 'back' ? 'back' : 'front' });
  return computeSeatingRef(cells.map(([x, y, value]) => ({ x, y, value })), f).seats;
}

function walkNumbers(node, visit, seen) {
  const marks = seen || new Set();
  if (typeof node === 'number') { visit(node); return; }
  if (!node || typeof node !== 'object' || marks.has(node)) return;
  marks.add(node);
  if (Array.isArray(node)) { node.forEach(v => walkNumbers(v, visit, marks)); return; }
  for (const k of Object.keys(node)) walkNumbers(node[k], visit, marks);
}

function throws(fn) { try { fn(); return false; } catch (e) { return true; } }
function fmt(v) { return typeof v === 'string' ? `"${v}"` : String(v); }

// ── baseline ───────────────────────────────────────────────────────────────────
const base = run(verdictMod, decodeMod, oracleMod);
if (VERBOSE || base.failures.length) {
  for (const e of base.evidence) console.log(`  ${e}`);
}
for (const f of base.failures) console.log(`  FAIL  ${f}`);
console.log(`${base.failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${base.compared} assertions, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);

// ── mutation ───────────────────────────────────────────────────────────────────
// 🔴 A MUTANT THAT COULD NOT BE APPLIED IS NOT A CAUGHT MUTANT. A stale anchor makes `apply`
//    throw, and a throw scored as a kill reports a perfect run over a mutant that was never
//    introduced. So an unapplied mutant STOPS the run (this exact mistake is recorded in
//    `frame_declaration_harness.mjs`).
if (process.argv.includes('--mutate')) {
  const FILES = {
    verdict: join(SRC, 'verdict.js'),
    decode: join(SRC, 'decode.js'),
    oracle: join(HERE, 'oracle', 'alignment_scoring_oracle.mjs'),
  };
  const TEXT = {};
  for (const k of Object.keys(FILES)) TEXT[k] = readFileSync(FILES[k], 'utf8').replace(/\r\n/g, '\n');

  const swap = (from, to) => (src) => {
    if (!src.includes(from)) throw new Error(`anchor not found: ${from.slice(0, 70)}`);
    return src.split(from).join(to);
  };

  const MUTANTS = [
    { name: 'M1 oracle: the solved shift gets the WRONG SIGN', target: 'oracle',
      apply: swap('seatKey(bucket[i][0] - s.x, bucket[i][1] - s.y)',
                  'seatKey(s.x - bucket[i][0], s.y - bucket[i][1])') },
    { name: 'M2 verdict: a RANKING is emitted below the margin threshold', target: 'verdict',
      apply: swap("if (reasons.includes(REASON.MARGIN_TOO_SMALL)) {",
                  "if (false && reasons.includes(REASON.MARGIN_TOO_SMALL)) {") },
    { name: 'M3 decode: a PERCENTAGE is let through (the name check is defanged)', target: 'decode',
      apply: swap('  for (const w of pathWords(path)) if (RATIO_WORDS.has(w)) return true;',
                  '  for (const w of pathWords(path)) if (false && RATIO_WORDS.has(w)) return true;') },
    // 🔴 M3b PINS THE BUG THAT ACTUALLY SHIPPED. The word check used to be a SUBSTRING test,
    //    and `decla-RATIO-n` matched it, so every live payload threw on six integer tallies.
    //    A regression to substring matching must go red, not merely look stricter.
    { name: 'M3b decode: the ratio check regresses to SUBSTRING matching (decla-ratio-n)',
      target: 'decode',
      apply: swap('    if (looksLikeARatio(path)) bad.push(`${path} (name)`);',
                  '    if (/percent|pct|ratio|coverage|fitness/i.test(path)) bad.push(`${path} (name)`);') },
    { name: 'M4 oracle: the DISCRIMINATING SUBSET is dropped (every die counted)', target: 'oracle',
      apply: swap('else if (token !== first) { discriminating.add(k); break; }',
                  'else if (token !== first) { break; }') },
    { name: 'M5 verdict: one THRESHOLD SUBSTITUTES for the other', target: 'verdict',
      apply: swap('if (discriminating < minDiscriminating) reasons.push(REASON.TOO_FEW_DISCRIMINATING);',
                  'if (discriminating < minMargin) reasons.push(REASON.TOO_FEW_DISCRIMINATING);') },
    // 🔴 M6 AND M7 ARE A PAIR, AND M6 ALONE WOULD HAVE BEEN A FAKE KILL. The first version of
    //    this slot merely DELETED `assertIntegerCounts`, and it SURVIVED -- correctly, because
    //    no fixture emits a non-integer, so the deleted guard had nothing to catch. A mutant
    //    that removes a guard nothing triggers proves the guard is untested, not that it
    //    works. So the percentage is actually introduced: M6 checks the module's own runtime
    //    guard bites, M7 removes that guard too and checks the harness catches it anyway.
    { name: 'M6 oracle: a COVERAGE PERCENTAGE is emitted per candidate', target: 'oracle',
      apply: swap('      seatedCells: b.seated.seatCount,',
                  '      seatedCells: b.seated.seatCount,\n'
                  + '      coverage: (agree * 100) / Math.max(1, disc),') },
    { name: 'M7 oracle: a COVERAGE PERCENTAGE is emitted AND the runtime guard is removed',
      target: 'oracle',
      apply: (src) => {
        let s = swap('      seatedCells: b.seated.seatCount,',
          '      seatedCells: b.seated.seatCount,\n'
          + '      coverage: (agree * 100) / Math.max(1, disc),')(src);
        return swap('  assertIntegerCounts(result);', '  /* guard removed */')(s);
      } },
    // 🔴 M8..M11 ARE THE FOUR SHIPPED BUGS, PUT BACK. Each was measured on the live server on
    //    2026-08-06 before it was fixed, so these are not hypotheses about how the code could
    //    break -- they are the code as it was, and a green run over any of them would mean
    //    section G is decoration.
    { name: 'M8 decode: the RULED AXIS is ignored and the occupancy pair is read regardless',
      target: 'decode',
      apply: (src) => {
        let s = swap('  if (metric === METRIC_INDEX) {', '  if (false) {')(src);
        return swap('  if (metric === METRIC_VALUES || metric === METRIC_VALUES_WEIGHTED) {',
                    '  if (false) {')(s);
      } },
    { name: 'M9 decode: THE SHIPPED PAIR -- the candidate state is ignored AND the axis is, so '
          + 'a frame nobody considered reads as a frame that scored zero',
      target: 'decode',
      apply: (src) => {
        let s = swap('  if (metric === METRIC_INDEX) {', '  if (false) {')(src);
        s = swap('  if (metric === METRIC_VALUES || metric === METRIC_VALUES_WEIGHTED) {',
                 '  if (false) {')(s);
        return swap('    if (state !== null && CAND_UNMEASURED.has(state)) {',
                    '    if (false) {')(s);
      } },
    { name: 'M10 verdict: `isScorable` regresses to Number(), so an ABSENT count enters the '
          + 'ranking as a measured zero', target: 'verdict',
      apply: (src) => {
        let s = swap('    && finiteOrNull(s.agree) !== null',
                     '    && Number.isFinite(Number(s.agree))')(src);
        return swap('    && finiteOrNull(s.discriminating) !== null',
                    '    && Number.isFinite(Number(s.discriminating))')(s);
      } },
    { name: 'M11 decode: the thresholds the ruling applied are dropped, so this side re-decides '
          + 'against nothing', target: 'decode',
      apply: swap('    rulingThresholds: decodeThresholds(p && p.ruling),',
                  '    rulingThresholds: null,') },
    { name: 'CONTROL verdict: a comment is reworded (must SURVIVE)', target: 'verdict',
      apply: swap('// Reason CODES, not sentences.', '// Reason codes, not sentences.') },
  ];

  console.log('\n== mutation ==');
  let scored = 0;
  for (const m of MUTANTS) {
    const isControl = m.name.startsWith('CONTROL');
    let mutated;
    try { mutated = m.apply(TEXT[m.target]); } catch (e) {
      die(`mutant "${m.name}" could not be applied: ${e.message}. `
        + 'An unapplied mutant is not a caught mutant.');
    }
    let killed;
    let detail = '';
    // Relative imports inside a data: URI cannot resolve, so the mutated text is rebased onto
    // absolute file URLs first. Without this every mutant would "die" on an import error and
    // the whole section would be theatre -- a green count over code that never ran.
    const rebased = rebase(mutated, m.target);
    try {
      const url = 'data:text/javascript;base64,' + Buffer.from(rebased, 'utf8').toString('base64');
      const mod = await import(url);
      const V = m.target === 'verdict' ? mod : verdictMod;
      const D = m.target === 'decode' ? mod : decodeMod;
      const O = m.target === 'oracle' ? mod : oracleMod;
      const out = run(V, D, O);
      killed = out.failures.length > 0;
      detail = killed ? `${out.failures.length} failure(s), first: ${out.failures[0]}` : '';
      if (out.compared < base.compared) {
        detail += ` [WARNING: ran ${out.compared} of ${base.compared} assertions]`;
      }
    } catch (err) {
      killed = true;
      detail = `threw: ${String(err && err.message).slice(0, 110)}`;
    }
    if (killed !== isControl) scored++;
    console.log(`  ${killed ? 'CAUGHT  ' : 'SURVIVED'}  ${m.name}`);
    if (detail) console.log(`            ${detail}`);
  }
  console.log(`\n  ${scored}/${MUTANTS.length} scored as intended.`);
  if (scored !== MUTANTS.length) process.exit(1);
}

function rebase(text, target) {
  const dir = target === 'oracle' ? join(HERE, 'oracle') : SRC;
  return text.replace(/from '(\.[^']*)'/g, (_m, rel) => {
    const abs = new URL(rel, `file:///${join(dir, 'x').replace(/\\/g, '/')}`).href;
    return `from '${abs}'`;
  });
}

process.exit(base.failures.length === 0 ? 0 : 1);
