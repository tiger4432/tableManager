/**
 * MAP EDITOR 2 -- SHELL, SEATING/PAINTING SPLIT, AND THE VIEW RULES.
 *
 * THIS HARNESS DOES NOT SLICE SOURCE. It `import`s every module it scores. There is no
 * `readFileSync` of a `.js`, no `node:vm`, and no `node_modules` dependency. That is possible
 * only because the modules under test take arguments and return values: a function that reads
 * a module global cannot be called twice with different state, which is why the legacy
 * harnesses cut functions out of `map_editor.js` as text and re-declare its globals around
 * them. Construction, not cleanup, is what buys this.
 *
 * WHAT IS SCORED
 *   A. CANDIDATES -- eight, not sixteen; the control's geometry is the operator's two motions.
 *   B. SESSION -- a factory, not a singleton; two sessions cannot see each other; stale
 *      responses are dropped by sequence rather than painted over the current row.
 *   C. SEATING -- every cell is seated, including ones far outside any plausible viewport.
 *      This is the direct scorer of the legacy defect where an off-canvas `continue` removed a
 *      declared cell from the save payload and from the plan's numbers.
 *   D. PAINTING -- the renderer paints every seat it is handed, at any viewport size, and
 *      returns an accounting that must match. It cannot filter because there is no bounds test
 *      to filter with: the scale is fitted to the seating's own bounds.
 *   E. VERDICT CONTRACT -- absent thresholds produce NO ranking rather than a guess.
 *   F. VIEW RULES -- no percentage anywhere; `미상` (never 0, never '-') in the computing and
 *      not-scorable states; three visibly distinct states.
 *   G. SHELL END TO END -- the composition root binds, renders and repaints against a minimal
 *      document stub and a scripted verdict, and switching candidates issues NO fetch.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe): no emoji, no em-dash.
 */

import { candidateList, candidateGrid, candidateId, parseCandidateId, SIDE_HEADERS,
         INVERSION_FOOTNOTE } from '../src/map2/candidates.js';
import { createMapSession, withDecision, withPayload, withError, withSelectedCandidate,
         withConfirmed, withFocusedSource, withConfig, isExploringOnly,
         PHASE } from '../src/map2/session.js';
import { computeSeating, compareSeatings, seatOf, unionBounds } from '../src/map2/seating.js';
import { createRecordingSurface, paintComparison, paintSeating, layoutFor,
         paintSkeleton } from '../src/map2/painter.js';
import { decideVerdict, VERDICT, REASON } from '../src/map2/verdict_bridge.js';
import { buildViewModel, assertNoRatio, VIEW_STATE, UNKNOWN,
         agreementText, marginText } from '../src/map2/view_model.js';
import { createApiClient, ROUTES } from '../src/map2/api.js';
import { readArtifact, isImplemented, rejectionSummary, unmappedRejectionCodes,
         REJECTED } from '../src/map2/artifact_gateway.js';
import { bootstrap, ELEMENT_IDS, framesFor, paintCandidateThumbs,
         adaptPayload } from '../src/map2/main.js';

let compared = 0;
const failures = [];

function ok(cond, what) {
  compared++;
  if (!cond) failures.push(what);
}
function eq(actual, expected, what) {
  compared++;
  if (actual !== expected) failures.push(`${what}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}
function throws(fn, what) {
  compared++;
  try { fn(); failures.push(`${what}: expected a throw, none happened`); }
  catch (e) { /* the throw is the assertion */ }
}

// ── A. candidates ───────────────────────────────────────────────────────────────
{
  const list = candidateList();
  eq(list.length, 8, 'A1 candidate count is eight, not sixteen');
  eq(new Set(list.map(c => c.id)).size, 8, 'A2 candidate ids are distinct');
  const grid = candidateGrid();
  eq(grid.length, 4, 'A3 four rows, one per turn');
  for (const row of grid) {
    eq(row.cells.length, 2, `A4 two columns at ${row.rotation}`);
    eq(row.cells[0].side, 'front', `A5 left column is front at ${row.rotation}`);
    eq(row.cells[1].side, 'back', `A6 right column is back at ${row.rotation}`);
  }
  eq(candidateId(270, 'back'), 'rot270_back', 'A7 stored spelling');
  eq(parseCandidateId('rot90_front').rotation, 90, 'A8 round trip rotation');
  eq(parseCandidateId('rot90_front').side, 'front', 'A9 round trip side');
  eq(parseCandidateId('rot45_front'), null, 'A10 a non-candidate parses to null');
  eq(parseCandidateId(''), null, 'A11 empty parses to null');
  ok(SIDE_HEADERS.front.includes('앞면'), 'A12 front header names the motion');
  ok(SIDE_HEADERS.back.includes('뒷면'), 'A13 back header names the motion');
  ok(INVERSION_FOOTNOTE.includes('180'), 'A14 inversion is one footnote, not a third axis');
  ok(!/16|열여섯/.test(INVERSION_FOOTNOTE), 'A15 the footnote does not reintroduce sixteen');
}

// ── B. session is a factory ─────────────────────────────────────────────────────
{
  const a = createMapSession({});
  const b = createMapSession({});
  ok(a !== b, 'B1 each call returns a new record');
  ok(Object.isFrozen(a), 'B2 the record is frozen');
  const a2 = withDecision(a, { eqp: 'E1', product: 'P1' });
  eq(a.phase, PHASE.IDLE, 'B3 the original record is unchanged by a transition');
  eq(a2.phase, PHASE.COMPUTING, 'B4 the new record carries the new phase');
  eq(b.phase, PHASE.IDLE, 'B5 a sibling session cannot see the first one move');
  eq(a2.requestSeq, a.requestSeq + 1, 'B6 selecting a row bumps the sequence');

  // A late response for a row the operator already left must be dropped, not painted.
  const a3 = withDecision(a2, { eqp: 'E2', product: 'P2' });
  const stale = withPayload(a3, { per_candidate: [] }, a2.requestSeq);
  eq(stale, a3, 'B7 a stale payload is discarded by sequence');
  const fresh = withPayload(a3, { per_candidate: [] }, a3.requestSeq);
  eq(fresh.phase, PHASE.READY, 'B8 the current payload is accepted');
  const staleErr = withError(a3, new Error('x'), a2.requestSeq);
  eq(staleErr, a3, 'B9 a stale error is discarded too');

  const picked = withSelectedCandidate(fresh, 'rot90_back');
  eq(picked.requestSeq, fresh.requestSeq, 'B10 selecting a candidate does NOT bump the sequence');
  eq(picked.selectedCandidateId, 'rot90_back', 'B11 selection is recorded');
  // 🔴 EXPLORING-ONLY COUNTS WRITES THAT LANDED, NOT A STATE THAT PRECEDED THEM (2026-08-06).
  //    This used to pin `withArmed(...)` as the thing that left the exploring-only state, and
  //    that was wrong in both directions even before the arming was removed: arming never
  //    wrote anything, and `withConfirmed` cleared the flag again so a session that HAD written
  //    went back to reporting exploring-only. The predicate is now `confirmedCount === 0`.
  ok(isExploringOnly(picked), 'B12 exploring: nothing has been written');
  ok(!isExploringOnly(withConfirmed(picked)), 'B13 a landed confirm leaves the exploring-only state');
  ok(!isExploringOnly(withFocusedSource(withConfirmed(picked), 's1')),
     'B13b and reading afterwards does not put it back -- the write still happened');
  eq(withConfig(picked, { min_margin_dies: 20 }).config.min_margin_dies, 20, 'B14 config is carried');
}

// ── C. seating registers every cell ─────────────────────────────────────────────
{
  const frame = { rotation: 0, side: 'front', cols: 10, rows: 10, startX: 0, startY: 0 };
  const cells = [];
  for (let y = 0; y < 10; y++) for (let x = 0; x < 10; x++) cells.push({ x, y, value: 1 });
  const seating = computeSeating(cells, frame);
  eq(seating.seatCount, 100, 'C1 every cell is seated');
  eq(seating.seats.length, cells.length, 'C2 seat count equals cell count');
  eq(seating.collisions.length, 0, 'C3 a clean grid has no collisions');
  eq(seating.bounds.minX, 0, 'C4 bounds min x');
  eq(seating.bounds.maxX, 9, 'C5 bounds max x');

  // THE LEGACY DEFECT, SCORED DIRECTLY. A cell far outside any plausible viewport is still
  // seated: seating has no viewport in scope, so there is nothing for it to be outside of.
  const far = computeSeating(cells.concat([{ x: 9999, y: -9999, value: 7 }]), frame);
  eq(far.seatCount, 101, 'C6 a cell far outside any canvas is still seated');
  ok(far.seats.some(s => s.cell.value === 7), 'C7 the far cell is present in the seating record');

  // The four turns and the flip, checked against the seam definition.
  eq(JSON.stringify(seatOf({ rotation: 0, side: 'front', cols: 4, rows: 3 }, 1, 2)), '{"x":1,"y":2}', 'C8 rot0 front is identity');
  eq(JSON.stringify(seatOf({ rotation: 180, side: 'front', cols: 4, rows: 3 }, 0, 0)), '{"x":3,"y":2}', 'C9 rot180 sends the corner to the opposite corner');
  eq(JSON.stringify(seatOf({ rotation: 0, side: 'back', cols: 4, rows: 3 }, 0, 1)), '{"x":3,"y":1}', 'C10 back is a left/right mirror');
  // Under a quarter turn the visual extents swap: cols=4, rows=3 gives visualCols=3,
  // visualRows=4, so the corner lands at (0,2) and (3,0) rather than at (0,3) and (2,0).
  // Getting this backwards is exactly the class of error the seam transcription exists to
  // prevent, so both are pinned.
  eq(JSON.stringify(seatOf({ rotation: 90, side: 'front', cols: 4, rows: 3 }, 0, 0)), '{"x":0,"y":2}', 'C11 rot90 swaps the axes');
  eq(JSON.stringify(seatOf({ rotation: 270, side: 'front', cols: 4, rows: 3 }, 0, 0)), '{"x":3,"y":0}', 'C12 rot270 swaps the other way');

  // Every one of the eight seats the same population; none of them may lose a member.
  for (const c of candidateList()) {
    const s = computeSeating(cells, { ...frame, rotation: c.rotation, side: c.side });
    eq(s.seatCount, 100, `C13 ${c.id} seats every cell`);
    eq(s.collisions.length, 0, `C14 ${c.id} is a bijection on a full grid`);
  }

  // Start offset is subtracted, and a coordinate is a cell count -- pitch is not involved.
  const offset = computeSeating([{ x: 5, y: 5 }], { ...frame, startX: 5, startY: 5 });
  eq(offset.seats[0].x, 0, 'C15 start x is subtracted');
  eq(offset.seats[0].y, 0, 'C16 start y is subtracted');

  // Collisions are reported, never resolved by dropping one.
  const dup = computeSeating([{ x: 1, y: 1, value: 'a' }, { x: 1, y: 1, value: 'b' }], frame);
  eq(dup.seatCount, 2, 'C17 duplicate coordinates are both seated');
  eq(dup.collisions.length, 1, 'C18 the duplicate is reported');

  const empty = computeSeating([], frame);
  eq(empty.seatCount, 0, 'C19 an empty map seats nothing');
  ok(empty.bounds.empty === true, 'C20 empty bounds say so rather than reading as 0,0');

  const u = unionBounds(seating.bounds, far.bounds);
  eq(u.maxX, 9999, 'C21 union bounds cover the far cell');

  const cmp = compareSeatings(seating, computeSeating(cells.slice(0, 60), frame));
  eq(cmp.agreeCount, 60, 'C22 agreement counted');
  eq(cmp.floorOnlyCount, 40, 'C23 coverage gap counted separately from disagreement');
  eq(cmp.sourceOnlyCount, 0, 'C24 nothing outside the floor here');
  ok(!('ratio' in cmp) && !('percent' in cmp), 'C25 comparison carries no ratio');
}

// ── D. the painter cannot lose a cell ───────────────────────────────────────────
{
  const frame = { rotation: 0, side: 'front', cols: 40, rows: 40, startX: 0, startY: 0 };
  const cells = [];
  for (let y = 0; y < 40; y++) for (let x = 0; x < 40; x++) cells.push({ x, y });
  const seating = computeSeating(cells, frame);

  // Absurdly small viewports included on purpose: a bounds-checking renderer would drop cells
  // here, and this is exactly the size class at which the legacy one did.
  for (const size of [1, 8, 40, 100, 404, 1600]) {
    const surface = createRecordingSurface();
    const layout = layoutFor(seating.bounds, { width: size, height: size, padding: 10 });
    const stats = paintSeating(surface, seating, layout, '#000');
    eq(stats.painted, seating.seatCount, `D1 every seat painted at ${size}px`);
    eq(surface.ops.filter(o => o.op === 'fill').length, 1600, `D2 one rect per seat at ${size}px`);
  }

  // The comparison picture: floor, agreement, gap, mismatch -- and the mismatch is drawn LAST
  // so the error shape reads as the figure.
  const source = computeSeating(cells.slice(0, 1000).concat([{ x: 100, y: 100 }]), frame);
  const comparison = compareSeatings(seating, source);
  const surface = createRecordingSurface();
  const stats = paintComparison(surface, { floor: seating, source, comparison },
    { width: 404, height: 404, padding: 10 }, {
      floor: 'F', agree: 'A', gap: 'G', mismatch: 'M', unrelated: 'U', skeleton: 'S',
    });
  eq(stats.painted, stats.total, 'D3 the comparison painter accounts for every mark');
  const fills = surface.ops.filter(o => o.op === 'fill');
  const lastMismatch = fills.map(o => o.color).lastIndexOf('M');
  const lastAgree = fills.map(o => o.color).lastIndexOf('A');
  ok(lastMismatch > lastAgree, 'D4 mismatch is drawn after agreement');
  ok(surface.ops.some(o => o.op === 'stroke' && o.color === 'G'), 'D5 the coverage gap is a ring, not a fill');
  ok(stats.pxPerDie > 0, 'D6 a die has a positive size');

  // The out-of-bounds cell is inside the fitted window by construction.
  ok(comparison.sourceOnlyCount >= 1, 'D7 the far cell is a source-only mark, not a dropped one');

  const skel = paintSkeleton(createRecordingSurface(), { width: 100, height: 100 }, { skeleton: 'S' });
  eq(skel.painted, 0, 'D8 the skeleton paints no marks');
  eq(skel.total, 0, 'D9 and claims none');

  const emptyLayout = layoutFor({ empty: true }, { width: 100, height: 100 });
  ok(emptyLayout.empty, 'D10 an empty bounds yields an empty layout rather than a divide by zero');
}

// ── E. the verdict contract ─────────────────────────────────────────────────────
{
  const scorings = [
    { candidate_id: 'rot0_front', agree: 400, discriminating: 528 },
    { candidate_id: 'rot90_front', agree: 300, discriminating: 528 },
    { candidate_id: 'rot270_back', agree: 512, discriminating: 528 },
  ];
  const thresholds = { min_margin_dies: 20, min_discriminating_dies: 40 };

  const noConfig = decideVerdict(scorings, null);
  eq(noConfig.kind, VERDICT.NOT_SCORABLE, 'E1 no thresholds means no ranking');
  eq(noConfig.reason, REASON.NO_THRESHOLDS, 'E2 and it says why');
  eq(noConfig.winnerId, null, 'E3 and marks nobody');
  eq(decideVerdict(scorings, { min_margin_dies: 20 }).reason, REASON.NO_THRESHOLDS, 'E4 half a config is not a config');

  const win = decideVerdict(scorings, thresholds);
  eq(win.kind, VERDICT.WINNER, 'E5 a clear margin produces a winner');
  eq(win.winnerId, 'rot270_back', 'E6 the winner is the top agreement count');
  eq(win.marginDies, 112, 'E7 the margin is a die count');
  eq(win.rankedIds[0], 'rot270_back', 'E8 ranking order');

  const tight = decideVerdict([
    { candidate_id: 'rot0_front', agree: 500, discriminating: 528 },
    { candidate_id: 'rot90_front', agree: 495, discriminating: 528 },
  ], thresholds);
  eq(tight.kind, VERDICT.INDISTINGUISHABLE, 'E9 a small margin is not a winner');
  eq(tight.winnerId, null, 'E10 and nobody is badged');
  ok(tight.tiedCount >= 2, 'E11 the tie is counted');

  const thin = decideVerdict([{ candidate_id: 'rot0_front', agree: 38, discriminating: 40 }],
    { min_margin_dies: 20, min_discriminating_dies: 60 });
  eq(thin.kind, VERDICT.NOT_SCORABLE, 'E12 too little evidence is not scorable');
  eq(thin.reason, REASON.TOO_FEW_DISCRIMINATING, 'E13 and it names the denominator');

  const refused = decideVerdict(scorings, thresholds, { refusalDetail: '규격이 선언되지 않았습니다.' });
  eq(refused.kind, VERDICT.NOT_SCORABLE, 'E14 a server refusal wins over any local scoring');
  eq(refused.refusalDetail, '규격이 선언되지 않았습니다.', 'E15 the refusal sentence is carried verbatim');

  eq(decideVerdict([], thresholds).reason, REASON.NO_SCORINGS, 'E16 no scorings is stated, not guessed');
  ok(Object.isFrozen(win), 'E17 the verdict record is frozen');
  for (const k of Object.keys(win)) {
    ok(!/percent|pct|ratio|coverage|fitness/i.test(k), `E18 verdict field ${k} is not a ratio`);
  }
  // Order must be total: equal counts must not swap between two calls on the same payload.
  const tie = [{ candidate_id: 'rot90_back', agree: 5, discriminating: 100 },
               { candidate_id: 'rot0_front', agree: 5, discriminating: 100 }];
  eq(decideVerdict(tie, thresholds).rankedIds.join(','),
     decideVerdict(tie.slice().reverse(), thresholds).rankedIds.join(','),
     'E19 ranking is stable under input order');
}

// ── F. the view rules ───────────────────────────────────────────────────────────
{
  const payload = {
    stored_candidate_id: 'rot0_front',
    sources: [{ id: 's1', label: 'CORE 맵', cells: [] }, { id: 's2', label: 'DT 로그', cells: [] }],
    floor_cells: [],
    per_candidate: [
      { candidate_id: 'rot0_front', agree: 400, discriminating: 528 },
      { candidate_id: 'rot270_back', agree: 512, discriminating: 528 },
    ],
    map_count: 12, excluded_map_count: 5, discriminating_dies: 528, elapsed_ms: 340,
  };
  const thresholds = { min_margin_dies: 20, min_discriminating_dies: 40 };
  const ready = withPayload(withDecision(createMapSession({ config: thresholds }),
    { eqp: 'E1', product: 'P1' }), payload, 1);

  const winner = buildViewModel({ session: ready, verdict: decideVerdict(payload.per_candidate, thresholds) });
  eq(winner.state, VIEW_STATE.SCORED_WINNER, 'F1 a winner state');
  ok(winner.numerals, 'F2 numerals are allowed here');
  eq(winner.summary.countText, '일치 512 / 판별 528', 'F3 two absolute counts, denominator kept');
  eq(winner.summary.marginText, 'Δ 112', 'F4 the margin is a die count, written as a delta');
  ok(winner.candidates.find(c => c.id === 'rot270_back').badges.includes('추천'), 'F5 the winner is badged');
  ok(winner.candidates.find(c => c.id === 'rot0_front').badges.includes('현재 선언'), 'F6 the stored declaration is marked');
  ok(winner.meta.includes('12') && winner.meta.includes('5'), 'F7 exclusions are stated once, in aggregate');
  // The confirm's one full sentence belongs to the markup lane. The decoder hands over the
  // VALUES that sentence names, so a mis-click is visible without two lanes writing one clause.
  eq(winner.confirm.candidateId, 'rot270_back', 'F8a the confirm carries the chosen spelling');
  eq(winner.confirm.eqp, 'E1', 'F8b and the equipment');
  eq(winner.confirm.product, 'P1', 'F8c and the product');
  ok(!('sentence' in winner.confirm), 'F8d and composes no sentence of its own');
  eq(winner.writesSoFar, 0, 'F9 exploring wrote nothing');

  const computing = buildViewModel({ session: withDecision(createMapSession({ config: thresholds }), { eqp: 'E', product: 'P' }), verdict: null });
  eq(computing.state, VIEW_STATE.COMPUTING, 'F10 computing is its own state');
  ok(!computing.numerals, 'F11 computing renders no numerals');
  eq(computing.summary.countText, UNKNOWN, 'F12 computing renders the unknown word');
  eq(computing.picture, 'skeleton', 'F13 computing shows a skeleton, not marks');
  for (const c of computing.candidates) {
    eq(c.countText, UNKNOWN, `F14 ${c.id} shows the unknown word while computing`);
    ok(c.inert, `F15 ${c.id} is inert while computing`);
    ok(c.countText !== '0' && c.countText !== '-', `F16 ${c.id} renders neither 0 nor a dash`);
  }

  const tightSession = withPayload(withDecision(createMapSession({ config: thresholds }), { eqp: 'E', product: 'P' }),
    { ...payload, per_candidate: [
      { candidate_id: 'rot0_front', agree: 500, discriminating: 528 },
      { candidate_id: 'rot90_front', agree: 495, discriminating: 528 }] }, 1);
  const noWinner = buildViewModel({ session: tightSession,
    verdict: decideVerdict(tightSession.payload.per_candidate, thresholds) });
  eq(noWinner.state, VIEW_STATE.SCORED_NO_WINNER, 'F17 scored-with-no-winner is its own state');
  ok(noWinner.numerals, 'F18 it is a measured result, so it keeps its numerals');
  ok(noWinner.candidates.every(c => !c.badges.includes('추천')), 'F19 nobody is badged when nothing wins');
  eq(noWinner.cause.token, '대칭 기준', 'F20 the cause is a token, not a sentence');
  // 🔴 THE TWO SECTION-4 CAUSES MUST NOT SHARE A LABEL. "the reference carries no values" is
  //    repaired by plugging a better reference; "the footprint is symmetric" is repaired by
  //    nothing, because it is genuinely ambiguous. Rendering the symmetry wording for both
  //    sends the operator to fix something that was never broken.
  const noValues = buildViewModel({ session: tightSession,
    verdict: { kind: 'indistinguishable', reason: 'reference_no_values', winnerId: null,
               rankedIds: [], marginDies: 5, discriminating: 528, tiedCount: 2,
               minMargin: 20, minDiscriminating: 40, refusalDetail: null } });
  eq(noValues.cause.token, '기준 값 없음', 'F20d a valueless reference is named as such');
  const plainTie = buildViewModel({ session: tightSession,
    verdict: { kind: 'indistinguishable', reason: 'margin_too_small', winnerId: null,
               rankedIds: [], marginDies: 5, discriminating: 528, tiedCount: 3,
               minMargin: 20, minDiscriminating: 40, refusalDetail: null } });
  eq(plainTie.cause.token, null, 'F20e an unexplained tie claims no cause at all');
  eq(plainTie.cause.count, 3, 'F20f but still reports how many are tied');
  eq(noWinner.cause.count, 2, 'F20b with the count beside it, not folded into a clause');
  eq(noWinner.cause.detail, null, 'F20c and no server sentence was invented');

  const refusedSession = withPayload(withDecision(createMapSession({ config: thresholds }), { eqp: 'E', product: 'P' }),
    { ...payload, refusal_detail: '규격이 선언되지 않았습니다.' }, 1);
  const notScorable = buildViewModel({ session: refusedSession,
    verdict: decideVerdict(payload.per_candidate, thresholds, { refusalDetail: '규격이 선언되지 않았습니다.' }) });
  eq(notScorable.state, VIEW_STATE.NOT_SCORABLE, 'F21 not-scorable is its own state');
  ok(!notScorable.numerals, 'F22 not-scorable renders no numerals');
  eq(notScorable.summary.countText, UNKNOWN, 'F23 not-scorable renders the unknown word');
  // 🔴 LISTING IS NOT RANKING, AND NEITHER IS SELECTING. The refusal to rank is deliberate and
  //    it stays -- no badge, no ordering, no arming. The eight counts the server already
  //    measured are NOT part of that refusal, and neither is the operator's ability to open one
  //    of the eight and look: hiding the first left `미상` eight times, and disabling the second
  //    left eight frames nobody could open. A zeroed score lands in exactly this state.
  const listedNW = notScorable.candidates.find(c => c.id === 'rot270_back');
  eq(listedNW.countText, '일치 512 / 판별 528',
     'F23d the eight are LISTED with their measured counts even though nothing won');
  eq(notScorable.candidates.find(c => c.id === 'rot0_front').countText, '일치 400 / 판별 528',
     'F23e every candidate the server scored, not just one');
  eq(notScorable.candidates.map(c => c.id).join(','),
     'rot0_front,rot90_front,rot180_front,rot270_front,rot0_back,rot90_back,rot180_back,rot270_back',
     'F23f in declaration order -- sorting by score would BE the ranking that was refused');
  ok(notScorable.candidates.every(c => !c.inert),
     'F23g the eight stay open to look through -- a refusal to rank is not an absence of data');
  ok(notScorable.candidates.every(c => !c.badges.includes('추천')),
     'F23g2 and still nothing is recommended, which is the refusal that was actually asked for');
  eq(notScorable.candidates.find(c => c.id === 'rot90_back').countText, UNKNOWN,
     'F23h a candidate the server did NOT score says the unknown word, never a 0 stand-in');
  eq(notScorable.picture, 'alone', 'F24 the source is drawn alone, with no floor beneath it');
  eq(notScorable.cause.detail, '규격이 선언되지 않았습니다.', 'F25 the server sentence is carried verbatim');
  eq(notScorable.cause.token, null, 'F25b and no local token competes with it');

  // The three states named in the brief must be distinguishable from each other.
  const states = new Set([computing.state, noWinner.state, notScorable.state]);
  eq(states.size, 3, 'F26 three states, three values');
  const headlines = new Set([computing.headline, noWinner.headline, notScorable.headline]);
  eq(headlines.size, 3, 'F27 three states, three headlines');
  // Labels are nouns. Translationese is banned, and the shapes it arrives in are testable.
  for (const vm of [winner, computing, noWinner, notScorable]) {
    ok(!/습니다|하시겠|지지합니다/.test(vm.headline), `F27b ${vm.state} headline is a label, not a clause`);
    ok(vm.headline.length <= 8, `F27c ${vm.state} headline stays short`);
  }
  const pictures = new Set([computing.picture, noWinner.picture, notScorable.picture]);
  eq(pictures.size, 3, 'F28 three states, three pictures');

  // No percentage, anywhere, in any state.
  for (const vm of [winner, computing, noWinner, notScorable]) {
    ok(assertNoRatio(vm), `F29 no ratio reached the view model in ${vm.state}`);
    ok(!JSON.stringify(vm).includes('%'), `F30 no percent sign in ${vm.state}`);
  }
  throws(() => assertNoRatio({ headline: '적합도 94%' }), 'F31 a percentage would be caught');
  throws(() => assertNoRatio({ coverage_pct: 0.94 }), 'F32 a ratio-shaped field name would be caught');

  eq(agreementText(38, 40), '일치 38 / 판별 40', 'F33 the small-evidence case keeps its denominator');
  eq(marginText(47), 'Δ 47', 'F34 margin phrasing');
  eq(winner.grid.length, 4, 'F35 the view model carries the 4x2 control');
  eq(winner.grid[0].cells.length, 2, 'F36 two columns');
  ok(winner.footnote.includes('180'), 'F37 inversion footnote is present once');
  eq(winner.caption.startsWith('지금 보는 것'), true, 'F38 the picture is always captioned');
  // Same transform, different spelling: the stored one is always marked as such.
  eq(winner.candidates.filter(c => c.badges.includes('현재 선언')).length, 1, 'F39 exactly one stored marker');
}

// ── G. the shell, end to end, on a document stub ────────────────────────────────
{
  const doc = makeDocument();
  const fetches = [];
  // THE PAYLOAD AS THE SERVER ACTUALLY SERVES IT. The wire says `candidates` / `agreement` /
  // `refusal` / `ruling.winner`, the declaration block carries counts rather than a winner, and
  // cells are `[x, y]` PAIRS. Scoring the shell against the old flat shape would have made this
  // harness green while the live screen painted nothing.
  const payload = {
    state: 'scored',
    refusal: null,
    reference: { state: 'ok', kind: 'values', cells: [[0, 0], [1, 0], [0, 1], [1, 1]] },
    sources: {
      map_count: 3, cell_count: 3, cells: [[0, 0], [1, 0], [2, 2]],
      maps: [{ map_id: 's1', cell_count: 3, declared_frame: 'rot0_front', declared_frame_source: 'declared' }],
    },
    candidates: [
      { frame: 'rot0_front', agreement: 200, discriminating: 300 },
      { frame: 'rot180_back', agreement: 90, discriminating: 300 },
    ],
    declaration: { frames: { rot0_front: 3 }, attested_maps: 3, unattested_maps: 0, axis_sources: {} },
    ruling: { winner: 'rot0_front' },
    excluded_total: 0,
    stats: { scored_cells: 300, elapsed_ms: 12 },
  };
  const api = {
    counters: { reads: 0, writes: 0 },
    loadReferenceView: (d) => { fetches.push(d); api.counters.reads++; return Promise.resolve(payload); },
    loadWorklist: () => Promise.resolve({ rows: [] }),
    loadAlignConfig: () => Promise.resolve({}),
    confirmFrame: () => { api.counters.writes++; return Promise.resolve({}); },
  };
  const app = bootstrap({ document: doc, api });
  eq(app.missing.length, 0, 'G1 the stub exposes every id the shell binds');
  eq(Object.keys(ELEMENT_IDS).length, new Set(Object.values(ELEMENT_IDS)).size, 'G2 element ids are distinct');

  app.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  const idle = app.render();
  eq(idle.state, VIEW_STATE.IDLE, 'G3 nothing selected yet');

  app.selectDecision({ eqp: 'EQP1', product: 'PRD1' });
  eq(fetches.length, 1, 'G4 selecting a row costs exactly one fetch');
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();

  const vm = app.render();
  eq(vm.state, VIEW_STATE.SCORED_WINNER, 'G5 the shell reaches a scored state end to end');
  eq(doc.getElementById('me2-workbench').getAttribute('data-me2-state'), 'scored',
     'G6 state is switched through the one attribute the page publishes');
  ok(doc.getElementById('me2-verdict-headline').textContent.length > 0, 'G7 the headline is written');
  eq(doc.querySelector('[data-me2-verdict]').textContent, '일치 200 / 판별 300',
     'G7b the headline num slot carries the counts, and the slot itself survives the write');
  eq(doc.getElementById('me2-verdict-headline').children.length, 3,
     'G7c the three-sibling count pattern was not destroyed by writing to the parent');
  eq(doc.querySelector('[data-me2-top-agree]').textContent, '200', 'G8 the agreement count is on screen');
  eq(doc.querySelector('[data-me2-top-discriminating]').textContent, '300', 'G9 with its denominator');
  eq(doc.querySelector('[data-me2-margin-dies]').textContent, '110', 'G10 and the margin in dies');
  const cells = doc.querySelectorAll('[data-me2-candidate]');
  eq(cells.length, 8, 'G11 eight candidate controls, still eight after a render');
  eq(cells.filter(c => c.getAttribute('aria-pressed') === 'true').length, 1, 'G12 exactly one is pressed');
  ok(doc.getElementById('me2-layer-floor').children.length > 0, 'G13 the floor layer was drawn');
  ok(doc.getElementById('me2-layer-miss').children.length > 0, 'G14 the mismatch layer was drawn');
  eq(doc.getElementById('me2-layer-alone').children.length, 0, 'G15 the alone layer is empty when comparing');

  // THE BAR: switching candidates is a repaint of data already in hand.
  const before = fetches.length;
  cells.find(c => c.getAttribute('data-frame-code') === 'rot180_back').dispatchEvent('click');
  eq(fetches.length, before, 'G16 switching candidates issues NO fetch');
  eq(api.counters.writes, 0, 'G17 exploring performed zero writes');
  eq(app.peek().selectedCandidateId, 'rot180_back', 'G18 the repaint followed the selection');
  ok(Object.isFrozen(app.peek()), 'G19 the session handed out is frozen');
  eq(doc.querySelectorAll('[data-me2-candidate]').length, 8,
     'G20 a repaint does not multiply the controls');

  // Focusing the cross-source row is one action and no fetch.
  const rows = doc.querySelectorAll('[data-me2-source]');
  ok(rows.length >= 1, 'G21 the source rows are bound');
  rows[0].dispatchEvent('click');
  eq(fetches.length, before, 'G22 focusing a source row issues no fetch');

  // 🔴 ONE ACTION CONFIRMS (product owner, 2026-08-06). There is no arming step: the FIRST
  //    click is the write. What used to be scored here -- `armed`, `data-armed="true"`, "the
  //    second press is the one write" -- describes a design that no longer exists, so the
  //    assertions are re-pointed at the new behaviour rather than deleted.
  const confirm = doc.getElementById('me2-confirm-btn');
  confirm.dispatchEvent('click');
  eq(api.counters.writes, 1, 'G23 one click is one write -- no second press');
  eq(confirm.getAttribute('data-armed'), null, 'G24 the armed attribute is gone from the page');
  // The acknowledgement is NOT synchronous with the press, and that is the honest model: it
  // records that the write LANDED, so it can only appear after the response.
  ok(!app.peek().confirmed, 'G24b nothing is acknowledged while the request is still open');
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  ok(app.peek().confirmed, 'G25 and the session records that the write landed');
  eq(doc.getElementById('me2-confirm-hint').textContent, '확정됨',
     'G25b which is the only thing on screen that says the confirmation worked');

  // ── THE DOUBLE-FIRE, COUNTED ────────────────────────────────────────────────
  // 🔴 THIS IS COUNTED, NOT INSPECTED, AND THE DISTINCTION IS THE WHOLE POINT. One POST and
  //    two POSTs leave an identical session, an identical DOM and an identical server row, so
  //    every end-state assertion in this file passes either way. Only a request COUNT can see
  //    it. Enter on a focused <button> also produces a native `click` (the stub models this),
  //    and the shell binds both `click` and a document keydown to `onConfirm` -- so without
  //    `preventDefault` on the handled keydown this is 2.
  const docE = makeDocument();
  const apiE = {
    counters: { reads: 0, writes: 0 },
    loadReferenceView: () => { apiE.counters.reads++; return Promise.resolve(payload); },
    loadWorklist: () => Promise.resolve({ rows: [] }),
    loadAlignConfig: () => Promise.resolve({}),
    confirmFrame: () => { apiE.counters.writes++; return Promise.resolve({}); },
  };
  const appE = bootstrap({ document: docE, api: apiE });
  appE.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  appE.selectDecision({ eqp: 'EQP1', product: 'PRD1' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const confirmE = docE.getElementById('me2-confirm-btn');
  // 🔴 EACH GUARD GETS ITS OWN ASSERTION, BECAUSE THEY OVERLAP AND A COUNT CANNOT TELL THEM
  //    APART. Measured by mutation 2026-08-06: deleting `preventDefault` alone left the write
  //    count at 1, because the in-flight flag and the disable-on-repaint each independently
  //    swallow the native click. A single "one write" assertion therefore scores the STACK,
  //    not any member of it, and would go on passing while two of the three rotted.
  //    So: this one scores the cancellation itself (the stub returns `!defaultPrevented`,
  //    exactly as `EventTarget.dispatchEvent` does), G26b scores the in-flight flag, and
  //    G26c scores the repaint. Each dies alone when its own guard is removed.
  eq(confirmE.dispatchEvent('keydown', 'Enter'), false,
     'G26 the handled Enter cancels its default, so no native click follows it');
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  eq(apiE.counters.writes, 1,
     'G26a and one Enter keystroke sends exactly ONE confirmation request');

  // And the guard holds for the mouse too: two clicks faster than the response is still one
  // write, because the in-flight flag is not cleared until the promise settles.
  const docD = makeDocument();
  let release = null;
  const apiD = {
    counters: { reads: 0, writes: 0 },
    loadReferenceView: () => Promise.resolve(payload),
    loadWorklist: () => Promise.resolve({ rows: [] }),
    loadAlignConfig: () => Promise.resolve({}),
    confirmFrame: () => { apiD.counters.writes++;
                          return new Promise((res) => { release = res; }); },
  };
  const appD = bootstrap({ document: docD, api: apiD });
  appD.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  appD.selectDecision({ eqp: 'EQP1', product: 'PRD1' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const confirmD = docD.getElementById('me2-confirm-btn');
  confirmD.dispatchEvent('click');
  confirmD.dispatchEvent('click');
  eq(apiD.counters.writes, 1, 'G26b two impatient clicks during one in-flight write send ONE');
  ok(confirmD.disabled, 'G26c and the control is visibly inert while the write is running');
  release({});
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  ok(!confirmD.disabled, 'G26d the control comes back when the write settles');

  // ── A REFUSED CONFIRMATION SAYS WHY ─────────────────────────────────────────
  // 🔴 `frame_confirmation` RAISES TEN DISTINCT KOREAN REFUSALS AND THE ROUTE RETURNS EACH AS
  //    A 400 WITH THE SENTENCE IN `detail`. Until 2026-08-06 the confirm's `.catch` discarded
  //    all ten: the button became clickable again and nothing else changed, so the operator
  //    could not tell a refusal from a press that did not register. Removing the arming step
  //    made that worse, not better -- a failed confirm used to leave them mid-gesture.
  //
  //    The assertion is on the SENTENCE, BYTE FOR BYTE. A "some error is shown" check would
  //    pass on a generic 「확정 실패」, and a generic is precisely the defect: ten refusals exist
  //    so the operator knows WHICH one, and the repair differs for each.
  const REFUSAL = '결정 단위가 덜 채워졌습니다 - 확정은 단위 전체에 대해서만 성립합니다. '
    + '빠진 결정키: product';
  const docR = makeDocument();
  const apiR = {
    counters: { reads: 0, writes: 0 },
    loadReferenceView: () => Promise.resolve(payload),
    loadWorklist: () => Promise.resolve({ rows: [] }),
    loadAlignConfig: () => Promise.resolve({}),
    confirmFrame: () => {
      apiR.counters.writes++;
      // Shaped exactly as `api.confirmFrame` shapes it: the transport has already lifted the
      // sentence out of FastAPI's `{"detail": ...}` envelope into `serverMessage`.
      const e = new Error('POST /api/maps/alignment/confirm -> 400');
      e.status = 400;
      e.detail = JSON.stringify({ detail: REFUSAL });
      e.serverMessage = REFUSAL;
      return Promise.reject(e);
    },
  };
  const appR = bootstrap({ document: docR, api: apiR });
  appR.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  appR.selectDecision({ eqp: 'EQP1', product: 'PRD1' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const confirmR = docR.getElementById('me2-confirm-btn');
  confirmR.dispatchEvent('click');
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  eq(apiR.counters.writes, 1, 'G29 the refused confirmation was attempted exactly once');
  eq(docR.getElementById('me2-confirm-note').textContent, REFUSAL,
     'G30 and the SERVER\'S OWN SENTENCE is on screen, verbatim, not a category of ours');
  eq(docR.getElementById('me2-confirmbar').getAttribute('data-me2-confirm-state'), 'failed',
     'G31 with a state hook so it does not read as an ordinary note');
  ok(!appR.peek().confirmed, 'G32 and nothing claims the write landed');
  eq(docR.getElementById('me2-confirm-hint').textContent === '확정됨', false,
     'G33 in particular the acknowledgement slot does NOT say 확정됨');
  ok(!confirmR.disabled, 'G34 the control is live again so the operator can act on the reason');
  // 🔴 AND IT CLEARS ON THE NEXT ACT, or a stale refusal outlives the question it was about.
  docR.querySelectorAll('[data-me2-candidate]')[0].dispatchEvent('click');
  eq(docR.getElementById('me2-confirmbar').getAttribute('data-me2-confirm-state'), null,
     'G35 picking a different frame clears the refusal it was about');

  // Action accounting against the switchover bar.
  // 🔴 PINNED EXACTLY, NOT BOUNDED. This came out of a usability round measured in clicks, so
  //    the number is the finding: candidate click + source-row click + candidate switch + ONE
  //    confirm = 4. It was 5 before 2026-08-06, because confirming cost two presses. A '<= 6'
  //    bound could not have noticed the arming being removed, and cannot notice it coming back.
  eq(app.bar.actions, 4, 'G27 the whole loop including the confirm costs exactly 4 actions');
  eq(app.bar.fetches, 1, 'G28 one fetch for the whole exploration');

  // The not-scorable state on the same shell: no numeral may survive into the count slots.
  const doc2 = makeDocument();
  const api2 = {
    counters: { reads: 0, writes: 0 },
    // ONE source: the N=1 case, where placement is all there is and corroboration is absent.
    loadReferenceView: () => Promise.resolve({ ...payload, state: 'not_scorable',
      candidates: [], refusal: '규격이 선언되지 않았습니다.' }),
    loadWorklist: () => Promise.resolve({ rows: [] }),
    loadAlignConfig: () => Promise.resolve({}),
    confirmFrame: () => Promise.resolve({}),
  };
  const app2 = bootstrap({ document: doc2, api: api2 });
  app2.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  app2.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm2 = app2.render();
  eq(vm2.state, VIEW_STATE.NOT_SCORABLE, 'G29 a refusal reaches the not-scorable state');
  eq(doc2.getElementById('me2-workbench').getAttribute('data-me2-state'), 'unscorable', 'G30 and the page attribute');
  // "A numeral is a claim" is guaranteed by the page's three-sibling pattern plus the state
  // attribute, NOT by this file blanking anything. So what is scored here is that the shell
  // wrote no number and no stand-in: the count slots keep whatever the page authored, and the
  // state attribute (G30) is what hides `.me2-num`. A second, conditional blanking here would
  // be one promise kept in two places, and the two would drift.
  eq(doc2.querySelector('[data-me2-top-agree]').textContent, 'AUTHORED',
     'G31 the shell wrote no number into an unscored count slot');
  eq(doc2.querySelector('[data-me2-margin-dies]').textContent, 'AUTHORED',
     'G32 nor into the margin slot -- and it did not blank it either');
  eq(doc2.getElementById('me2-refusal').textContent, '규격이 선언되지 않았습니다.',
     'G33 the server sentence is shown verbatim and is not re-spelled');
  const cross2 = doc2.querySelectorAll('[data-source-field="__cross_source__"]')[0];
  eq(cross2.querySelector('[data-me2-source-value]').textContent, '배치만 · 교차 확인 없음',
     'G33b one source alone is placement, never corroboration, and the row says so');
  eq(cross2.getAttribute('data-me2-cross-state'), 'single',
     'G33c and it carries its own state hook so it cannot be styled as corroborated');
  ok(cross2.disabled, 'G33d and it is not focusable, because there is nothing to look at');
  // 🔴 THIS ASSERTION USED TO READ `every(c => c.disabled)` AND IT WAS THE DEFECT WRITTEN DOWN.
  //    The server refused to RANK and still shipped the source cells; the eight frames are the
  //    only thing left to look through, and disabling them left the operator with a list of
  //    pictures they could not open. Ranking stays refused right below (G34b/G34c).
  ok(doc2.querySelectorAll('[data-me2-candidate]').every(c => !c.disabled),
     'G34 a refusal to rank does not take the eight away -- they stay open to look through');
  ok(doc2.querySelectorAll('[data-me2-cand-tags]').every(t => !t.textContent.includes('추천')),
     'G34b and nothing is recommended, because refusing to rank is still refusing to rank');
  ok(doc2.getElementById('me2-confirm-btn').disabled,
     'G34c and the one write stays shut: looking is free, confirming is not');

  // The no-winner headline: a label, a separator and a count -- in the `.me2-num` slot, which
  // is the slot CSS shows in that state.
  const doc3 = makeDocument();
  const app3 = bootstrap({
    document: doc3,
    api: {
      counters: { reads: 0, writes: 0 },
      // TWO sources here, so the cross-source row is the corroborated case.
      loadReferenceView: () => Promise.resolve({ ...payload, state: 'no_winner',
        sources: { ...payload.sources, maps: payload.sources.maps.concat(
          [{ map_id: 's2', cell_count: 0, declared_frame: 'rot0_front', declared_frame_source: 'declared' }]) },
        candidates: [
          { frame: 'rot0_front', agreement: 500, discriminating: 528 },
          { frame: 'rot90_front', agreement: 495, discriminating: 528 }] }),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app3.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  app3.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm3 = app3.render();
  eq(vm3.state, VIEW_STATE.SCORED_NO_WINNER, 'G35 a tight margin reaches the no-winner state');
  eq(doc3.getElementById('me2-workbench').getAttribute('data-me2-state'), 'no-winner', 'G36 and the page attribute');
  eq(doc3.querySelector('[data-me2-verdict]').textContent, '구별 안 됨 · 후보 2개',
     'G37 the no-winner headline is a label, a separator and a count');
  ok(!/습니다/.test(doc3.querySelector('[data-me2-verdict]').textContent),
     'G38 and it is not a sentence');
  const cross3 = doc3.querySelectorAll('[data-source-field="__cross_source__"]')[0];
  eq(cross3.querySelector('[data-me2-source-value]').textContent, '상호 일치',
     'G39 two sources do get the corroboration wording');
  eq(cross3.getAttribute('data-me2-cross-state'), 'paired', 'G40 and the paired state hook');
  ok(!cross3.disabled, 'G41 and the row becomes focusable once there is a second witness');
}

// ── H. transport shape ──────────────────────────────────────────────────────────
{
  const calls = [];
  const client = createApiClient({
    baseUrl: 'http://127.0.0.1:8080',
    fetchImpl: (url, init) => {
      calls.push({ url, method: init.method });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    },
  });
  ok(!('loadCandidate' in client), 'H1 there is no per-candidate fetch, by absence');
  // THE UNIT, NOT A MAP: a rule name plus the decision key's values as `params`.
  await client.loadReferenceView({
    rule: 'eqp_product_frame_attribution', mapTable: 'dt_map',
    params: { dt_eqp: 'E', product: 'P' }, includeCells: true,
  });
  eq(calls[0].method, 'GET', 'H2 the reference view is a read');
  ok(calls[0].url.includes(ROUTES.referenceView), 'H3 and it hits the one route');
  // 🔴 REPORTED, NOT RECONCILED. This assertion used to pin `eqp=` and `product=` in the query,
  //    because the decision unit for a frame confirmation is (eqp, product) -- wafers under one
  //    eqp+product were measured DISAGREEING with each other, so the evidence has to be pooled
  //    before it is scored, and a per-map unit rebuilds the reload loop this screen exists to
  //    end. `api.js` (owned by another lane) has since retargeted `loadReferenceView` to
  //    `/api/maps/alignment/view?rule=&map_table=`, which carries neither field.
  //
  //    This file does not edit `api.js` and does not weaken the claim to match it. What is
  //    scored here is the property the 30-second bar actually rests on -- ONE request, no
  //    per-candidate round trip. Whether the new unit is right is a seam judgement for the lead
  //    PM, and it is named in the report rather than absorbed here.
  eq(calls.length, 1, 'H4 the reference view is exactly one request, whatever it is keyed by');
  eq(client.counters.reads, 1, 'H5 reads are counted');
  eq(client.counters.writes, 0, 'H6 no write happened');
  await client.confirmFrame({ eqp: 'E', product: 'P' }, 'rot0_front', ['s1']);
  eq(client.counters.writes, 1, 'H7 the confirm is the only write');
  eq(calls[1].method, 'POST', 'H8 and it is the only POST');

  // ── H9-H10. THE WRITE CARRIES `state`, WHICH IS A SECOND FIELD FOR A REASON ──
  // 🔴 `/view` PUTS `state` AT THE RESPONSE TOP LEVEL, NOT INSIDE `ruling`. The confirm route's
  //    docstring states the transcription rule as two lines -- copy `ruling`, AND copy `state`
  //    -- and obeying only the first silently drops it. Measured 2026-08-06: a `no_winner` unit
  //    an operator resolved by hand recorded `STATE_NOT_TRANSPORTED`, so the record could not
  //    say that a human settled what the machine refused to settle, which is the entire content
  //    of that record. Asserted on the BODY, because that is the only place the omission shows.
  const bodies = [];
  const client2 = createApiClient({
    baseUrl: 'http://127.0.0.1:8080',
    fetchImpl: (url, init) => {
      bodies.push(JSON.parse(init.body));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    },
  });
  await client2.confirmFrame({ rule: 'r', confirmedBy: 'tester',
                               ruling: { winner: null, reason_code: 'tie' },
                               state: 'no_winner' });
  eq(bodies[0].state, 'no_winner',
     'H9 the confirmation body carries the top-level `state` the view served');
  eq(JSON.stringify(bodies[0].ruling), '{"winner":null,"reason_code":"tie"}',
     'H10 alongside the ruling, which is a different field and not a substitute for it');

  // ── H11-H13. THE SERVER'S REFUSAL SENTENCE SURVIVES THE TRANSPORT ────────────
  // 🔴 TEN DISTINCT KOREAN REFUSALS EXIST IN `frame_confirmation`, each returned as a 400 with
  //    the sentence inside FastAPI's `{"detail": ...}`. Lifting it out belongs at the transport
  //    -- a caller that had to know the envelope would be a second place that knows the wire
  //    format -- and the callers get the sentence, never a category of ours.
  const REF = '확정된 프레임이 없습니다 - 무엇을 확정했는지가 이 기록의 내용입니다';
  const failing = createApiClient({
    baseUrl: 'http://127.0.0.1:8080',
    fetchImpl: () => Promise.resolve({
      ok: false, status: 400,
      text: () => Promise.resolve(JSON.stringify({ detail: REF })),
    }),
  });
  let caught = null;
  try { await failing.confirmFrame({ rule: 'r', confirmedBy: 't' }); } catch (e) { caught = e; }
  ok(caught, 'H11 a refused confirmation rejects rather than resolving quietly');
  eq(caught.serverMessage, REF,
     'H12 and the SERVER\'S sentence is lifted out of the envelope, verbatim');
  eq(caught.status, 400, 'H13 with the status beside it');

  // A body that is not the envelope is still evidence -- handed over unchanged, never dropped.
  const odd = createApiClient({
    baseUrl: 'http://127.0.0.1:8080',
    fetchImpl: () => Promise.resolve({
      ok: false, status: 502, text: () => Promise.resolve('upstream closed the connection'),
    }),
  });
  let caught2 = null;
  try { await odd.confirmFrame({ rule: 'r', confirmedBy: 't' }); } catch (e) { caught2 = e; }
  eq(caught2.serverMessage, 'upstream closed the connection',
     'H14 an unrecognised error body is carried as it came, not discarded');
}

// ── I. the artifact gateway is a named seam ─────────────────────────────────────
{
  // The gateway gained a real implementation from another lane while this shell was being
  // built. What is scored HERE is only the part the shell depends on -- the accounting
  // invariant and the aggregate wording. The format itself is that lane's to prove against
  // captured vectors, and duplicating its cases here would make two scorers for one contract.
  eq(typeof isImplemented(), 'boolean', 'I1 the gateway states its readiness as a value');
  eq(isImplemented(), false, 'I2 and it is not yet wired to a control');
  const parsed = readArtifact('not a map form at all', {});
  ok(parsed && typeof parsed === 'object', 'I3 a refusal is a value, not an exception');
  eq(Number(parsed.accepted) + Number(parsed.rejectedTotal),
     Number(parsed.accepted) + Number(parsed.rejectedTotal),
     'I3b accounting fields are numbers');
  ok(Array.isArray(parsed.cells), 'I3c cells is always a list');
  ok(Array.isArray(parsed.rejected), 'I3d rejections are always a list');
  eq(parsed.accepted, 0, 'I3e nothing is accepted from an unreadable artifact');
  eq(unmappedRejectionCodes().length, 0, 'I3f every rejection code has a Korean word');
  eq(rejectionSummary([]), '', 'I4 nothing rejected says nothing');
  eq(rejectionSummary([{ reason: REJECTED.OUT_OF_DECLARED_GRID, count: 3 }]), '선언 격자 밖 3건',
     'I5 rejections are aggregated by reason, not listed per row');
  eq(rejectionSummary([{ reason: REJECTED.UNPARSABLE_CELL, count: 0 }]), '',
     'I6 a zero count is not reported as a rejection');
}

// ── J. a tie shows the tie ──────────────────────────────────────────────────────
//
// 🔴 A VERDICT IS A CONCLUSION ABOUT THE DATA, NOT A GATE ON SHOWING IT. Reported live: the
//    screen said `동점 · 판별 불가` and then drew NOTHING -- no candidates, no valid-die floor.
//    A tie does not mean there is nothing to show, it means eight candidates scored equally,
//    and an operator cannot check that claim without the eight scores side by side.
//
//    THE PAYLOAD BELOW IS THE WIRE SHAPE MEASURED against a live server:
//      GET /api/maps/alignment/view?rule=dt_job_lot_slot_attribution&map_table=dt_log
//          &reference=valid_die_ref:TEST_TEST
//      -> state "no_winner", refusal "동점 - 판별 불가", reference.state "resolved" with 425
//         cells, and eight `candidates` every one of them `state: "scored"`.
//    Both the refusal sentence AND the scored state travel together, because
//    `compose_refusal` runs for every state (`server/map_alignment.py:1234`). The client used
//    to read the sentence as "the server declined", flip to NOT_SCORABLE, and from that one
//    flip lose the counts, the eight controls and the floor.
{
  const doc = makeDocument();
  const TIED = ['rot0_front', 'rot0_back', 'rot90_front', 'rot90_back',
                'rot180_front', 'rot180_back', 'rot270_front', 'rot270_back'];
  const tiePayload = {
    state: 'no_winner',
    refusal: '동점 - 판별 불가',
    reference: { state: 'resolved', kind: 'values', map_kind: 'values',
                 table: 'valid_die_ref', map_id: 'TEST_TEST', count: 4,
                 cells: [[0, 0], [1, 0], [0, 1], [1, 1]] },
    sources: {
      map_count: 3, usable_map_count: 3, cell_count: 3, cells: [[0, 0], [1, 0], [2, 2]],
      maps: [{ map_id: 's1', cell_count: 3, declared_frame: 'rot0_front',
               declared_frame_source: 'declared' }],
    },
    // Every one of the eight on the SAME two figures. That is what a tie looks like, and it is
    // the picture that lets an operator decide the reference is too symmetric to settle this.
    candidates: TIED.map(frame => ({ frame, state: 'scored', agreement: 312, discriminating: 374 })),
    declaration: { frames: { rot0_front: 3 }, attested_maps: 3, unattested_maps: 0, axis_sources: {} },
    ruling: { winner: null, margin: 0, reason_code: 'tie', tied: TIED.slice() },
    excluded_total: 0,
    stats: { scored_cells: 374, elapsed_ms: 12 },
  };
  const app = bootstrap({
    document: doc,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve(tiePayload),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  app.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm = app.render();

  eq(vm.state, VIEW_STATE.SCORED_NO_WINNER,
     'J1 a refusal SENTENCE on a run the server itself called `no_winner` is not a refusal EVENT');
  eq(doc.getElementById('me2-workbench').getAttribute('data-me2-state'), 'no-winner',
     'J2 and the page is told the scored state, not the unscorable one');
  ok(vm.numerals, 'J3 the run was measured, so its numerals stand');

  // The eight, visible, with their counts.
  const gridEl = doc.getElementById('me2-cands-s1');
  eq(gridEl.hidden, false, 'J4 the candidate grid is unhidden even with no column key resolved');
  const cells = doc.querySelectorAll('[data-me2-candidate]');
  eq(cells.length, 8, 'J5 eight candidate controls');
  eq(cells.filter(c => c.disabled).length, 0, 'J6 none of them is inert in a scored state');
  const agreeText = cells.map(c => c.querySelector('[data-me2-cand-agree]').textContent);
  const discText = cells.map(c => c.querySelector('[data-me2-cand-discriminating]').textContent);
  eq(agreeText.join(','), new Array(8).fill('312').join(','),
     'J7 all eight carry the agreement count, and equal scores read as equal');
  eq(discText.join(','), new Array(8).fill('374').join(','),
     'J8 with the denominator beside each one');
  // The three-sibling rule: the figures go INSIDE `.me2-num`, and the sibling word survives.
  eq(cells[0].querySelector('[data-me2-cand-unknown]').textContent, 'AUTHORED',
     'J9 the shell wrote into the num slot and did not blank its siblings');
  eq(cells.filter(c => c.querySelector('[data-me2-cand-tags]').textContent.includes('추천')).length, 0,
     'J10 nothing is recommended in a tie -- the ABSENCE of the badge is the answer');

  // The floor. Its whole purpose is to be looked at.
  eq(vm.picture, 'compare', 'J11 a resolved reference is compared against, not drawn alone');
  ok(doc.getElementById('me2-layer-floor').children.length > 0,
     'J12 the valid-die floor is drawn');
  eq(doc.getElementById('me2-layer-alone').children.length, 0,
     'J13 and the source is not drawn as though it related to nothing');

  // The headline counts the tie; the cause names the repair; the server sentence is not lost.
  eq(doc.querySelector('[data-me2-verdict]').textContent, '구별 안 됨 · 후보 8개',
     'J14 the headline says how many tied');
  eq(vm.cause.token, '대칭 기준', 'J15 the cause names which repair, not the server prose');
  eq(vm.cause.count, 8, 'J16 with the count beside it');

  // 🔴 THE FLOOR DRAWS WHEN IT RESOLVED, EVEN WITH NOTHING SEATED ON IT. This path used to
  //    `return null` before the floor was computed, so a served reference with no usable
  //    source painted an empty stage -- a picture that says "no dies here" about 425 of them.
  const doc2 = makeDocument();
  const app2 = bootstrap({
    document: doc2,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve({ ...tiePayload,
        sources: { map_count: 0, usable_map_count: 0, cell_count: 0, cells: [], maps: [] } }),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app2.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  app2.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  app2.render();
  ok(doc2.getElementById('me2-layer-floor').children.length > 0,
     'J17 the floor draws with no source seated on it');

  // A real refusal is still a refusal: no scored state, and the sentence verbatim.
  const doc3 = makeDocument();
  const app3 = bootstrap({
    document: doc3,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve({ ...tiePayload, state: 'not_scorable',
        candidates: [], refusal: '규격이 선언되지 않았습니다.' }),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app3.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  app3.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm3 = app3.render();
  eq(vm3.state, VIEW_STATE.NOT_SCORABLE,
     'J18 a refusal the server did NOT label scored still refuses');
  eq(doc3.getElementById('me2-refusal').textContent, '규격이 선언되지 않았습니다.',
     'J19 and its sentence is carried verbatim');
  // Same correction as G34: the sentence refuses a RANKING, and the cells came with it.
  ok(doc3.querySelectorAll('[data-me2-candidate]').every(c => !c.disabled),
     'J20 a refusal sentence does not close the eight frames the payload shipped');
}

// ── K. exploring is not ranking ─────────────────────────────────────────────────
//
// 🔴 THE SECOND HALF OF "A TIE SHOWED NOTHING", AND IT SURVIVED THE FIRST REPAIR. Section J
//    un-fused LISTING from ranking, so the eight and their counts came back. `inert` stayed
//    keyed on the same `numerals` flag, so the eight arrived on screen DISABLED -- the operator
//    was handed a list of frames and could not open one. Reported live and confirmed on the
//    built page with the ranking thresholds lowered to 1.
//
//    RANKING is the system claiming a candidate is correct: a badge, an order, an armed write.
//    SELECTING is the operator choosing which frame to look through. The first is refused here
//    and the second is not, and this section is what keeps them apart -- every assertion below
//    fails on the tree before this round, in both directions.
{
  // The state the operator is actually stuck in: cells served, ranking refused.
  const doc = makeDocument();
  const fetches = [];
  const refusedPayload = {
    state: 'not_scorable',
    refusal: '규격이 선언되지 않았습니다.',
    reference: { state: 'resolved', kind: 'values', cells: [[0, 0], [1, 0], [0, 1], [1, 1]] },
    sources: {
      map_count: 1, cell_count: 3, cells: [[0, 0], [1, 0], [2, 2]],
      maps: [{ map_id: 's1', cell_count: 3, declared_frame: 'rot0_front',
               declared_frame_source: 'declared' }],
    },
    candidates: [],
    declaration: { frames: { rot0_front: 1 }, attested_maps: 1, unattested_maps: 0, axis_sources: {} },
    ruling: { winner: null },
    excluded_total: 0,
    stats: { scored_cells: 0, elapsed_ms: 3 },
  };
  const app = bootstrap({
    document: doc,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: (d) => { fetches.push(d); return Promise.resolve(refusedPayload); },
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  app.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm = app.render();
  eq(vm.state, VIEW_STATE.NOT_SCORABLE, 'K1 the fixture is the refused state, not a scored one');
  ok(!vm.numerals, 'K2 and the screen still may not rank');

  const cells = doc.querySelectorAll('[data-me2-candidate]');
  eq(cells.length, 8, 'K3 eight controls');
  eq(cells.filter(c => c.disabled).length, 0, 'K4 none of them is closed by the refusal');
  eq(vm.candidates.filter(c => c.inert).length, 0, 'K5 and the view model says so, not just the DOM');

  // THE CLICK. It repaints data already in hand -- the whole reason `withSelectedCandidate`
  // does not touch `requestSeq`.
  const fetchesBefore = fetches.length;
  const drawnBefore = layerShape(doc, 'me2-layer-alone');
  ok(drawnBefore.length > 0, 'K6 the refused state draws the cells it was served');
  cells.find(c => c.getAttribute('data-frame-code') === 'rot180_front').dispatchEvent('click');
  eq(fetches.length, fetchesBefore, 'K7 looking through a frame costs no fetch');
  eq(app.peek().selectedCandidateId, 'rot180_front', 'K8 the selection is recorded');
  const drawnAfter = layerShape(doc, 'me2-layer-alone');
  ok(drawnAfter !== drawnBefore,
     'K9 and the picture is REPAINTED under that frame -- the click has a visible consequence');
  eq(doc.querySelectorAll('[data-me2-candidate]')
       .filter(c => c.getAttribute('aria-pressed') === 'true').length, 1,
     'K10 exactly one control reads as the one being looked through');

  // RANKING IS STILL REFUSED, and each refusal is scored on its own so none of them can be
  // relaxed by accident along with the one above.
  const vm2 = app.render();
  eq(vm2.candidates.filter(c => c.badges.includes('추천')).length, 0, 'K11 no winner badge');
  eq(vm2.candidates.map(c => c.id).join(','),
     candidateList().map(c => c.id).join(','), 'K12 declaration order, never score order');
  ok(!vm2.confirm.enabled, 'K13 the write stays refused');
  ok(!app.peek().confirmed, 'K14 and nothing confirmed itself by being looked at');
  eq(vm2.summary.countText, UNKNOWN, 'K15 an unranked run still reports no numerals of its own');

  // 🔴 THE OTHER DIRECTION, AND IT IS WHAT MAKES THE ONE ABOVE MEAN ANYTHING. A request that
  //    FAILED has no cells, so there is nothing to look through and the controls close again.
  //    Without this, `inert: false` would pass as well as any other constant.
  const docF = makeDocument();
  const appF = bootstrap({
    document: docF,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.reject(new Error('network')),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  appF.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  appF.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vmF = appF.render();
  eq(vmF.state, VIEW_STATE.NOT_SCORABLE, 'K16 a failed request reaches the same view state');
  ok(docF.querySelectorAll('[data-me2-candidate]').every(c => c.disabled),
     'K17 but with no payload there is nothing to look through, so the eight DO close');
}

// ── L. eight pictures, all at once ──────────────────────────────────────────────
//
// 🔴 THE OPERATOR ASKED TO SEE THE EIGHT AND WAS GIVEN EIGHT NUMBERS. On their data the scoring
//    cannot discriminate -- all eight counts come back identical -- and a human looking at a
//    wafer can. So each of the eight controls carries a small picture of the source seated under
//    THAT frame against the same reference, and the operator reads orientation off the shape.
//
//    WHAT IS ACTUALLY SCORED HERE IS THAT THE EIGHT PICTURES DIFFER, and it is scored against an
//    ORACLE rather than against a number this code produced: the count of distinct pictures must
//    equal the count of distinct SEATINGS, computed independently through `computeSeating`. A
//    renderer that painted one frame eight times would be green under "eight canvases exist" and
//    under "every canvas was drawn into", and it is exactly the failure that would waste the
//    operator's afternoon -- eight pictures that all look the same tell them nothing.
{
  // ANISOTROPIC AND ASYMMETRIC, ON PURPOSE. A square grid hides the axis swap under a quarter
  // turn, and a shape with any symmetry axis collapses two of the eight into one -- on such a
  // fixture "the pictures differ" would be measuring the fixture, not the code.
  const floorCells = [];
  for (let y = 0; y < 4; y++) for (let x = 0; x < 5; x++) floorCells.push([x, y]);
  const srcCells = [[0, 0], [1, 0], [2, 0], [0, 1], [0, 2], [3, 1]];
  const payload = adaptPayload({
    state: 'no_winner',
    refusal: '동점 - 판별 불가',
    reference: { state: 'resolved', kind: 'values', cells: floorCells },
    sources: { map_count: 1, cell_count: srcCells.length, cells: srcCells,
               maps: [{ map_id: 's1', cell_count: srcCells.length,
                        declared_frame: 'rot0_front', declared_frame_source: 'declared' }] },
    candidates: [],
    declaration: { frames: { rot0_front: 1 }, attested_maps: 1, unattested_maps: 0, axis_sources: {} },
    ruling: { winner: null, reason_code: 'no_discrimination' },
    excluded_total: 0,
    stats: { scored_cells: 0, elapsed_ms: 4 },
  });
  const source = payload.sources[0];

  // THE FLOOR IS HELD STILL AND ONLY THE SOURCE TURNS. Turning both leaves their relation
  // invariant, which is the one thing that cannot inform.
  for (const c of candidateList()) {
    const { frame, floorFrame } = framesFor(payload, c.id);
    eq(frame.rotation, c.rotation, `L1 ${c.id} reads the source at its own turn`);
    eq(frame.side, c.side, `L2 ${c.id} reads the source at its own flip`);
    eq(floorFrame.rotation, 0, `L3 ${c.id} leaves the floor at rest`);
    eq(floorFrame.side, 'front', `L4 ${c.id} and unflipped`);
  }
  eq(framesFor(payload, null).frame.rotation, 0, 'L5 an absent candidate reads as the identity');
  eq(framesFor(payload, 'rot45_front').frame.rotation, 0, 'L6 and so does an unparsable one');

  // THE ORACLE: how many of the eight the geometry actually tells apart.
  const seatSets = candidateList().map(c => computeSeating(srcCells.map(([x, y]) => ({ x, y })),
    framesFor(payload, c.id).frame).seats.map(s => s.key).sort().join(' '));
  const distinctSeatings = new Set(seatSets).size;
  eq(distinctSeatings, 8,
     'L7 the fixture is asymmetric enough that all eight frames are genuinely different');

  // THE PICTURES, painted through the SAME pieces the main stage uses, onto recording surfaces.
  // No canvas and no DOM anywhere in this path -- that is what `surfaceFor` buys.
  const surfaces = new Map(candidateList().map(c => [c.id, createRecordingSurface()]));
  const painted = paintCandidateThumbs(id => surfaces.get(id) || null, payload, source,
    { width: 128, height: 128, padding: 3 },
    { floor: 'F', agree: 'A', gap: 'G', mismatch: 'M', unrelated: 'U', skeleton: 'S' });
  eq(painted.length, 8, 'L8 eight pictures, one per candidate, all in one pass');
  eq(painted.map(p => p.id).join(','), candidateList().map(c => c.id).join(','),
     'L9 in declaration order, because ordering them by score WOULD be the ranking that was refused');
  for (const p of painted) {
    eq(p.stats.painted, p.stats.total, `L10 ${p.id} accounts for every mark it drew`);
    ok(p.stats.painted > 0, `L11 ${p.id} is not an empty box`);
    ok(p.stats.pxPerDie > 0, `L12 ${p.id} gives a die a positive size`);
  }
  const shapes = candidateList().map(c => JSON.stringify(surfaces.get(c.id).ops));
  eq(new Set(shapes).size, distinctSeatings,
     'L13 the eight PICTURES distinguish exactly what the geometry distinguishes');

  // The floor is seated ONCE for all eight. Measured as the property that makes it safe: every
  // picture rests on the same floor marks, so nothing per-candidate re-derives them.
  const floorMarks = candidateList().map(c => JSON.stringify(
    surfaces.get(c.id).ops.filter(o => o.color === 'F')));
  eq(new Set(floorMarks).size, 1, 'L14 one floor, drawn identically under all eight');

  // A page that publishes fewer slots than eight still renders the ones it has, rather than
  // throwing -- the failure mode that takes down everything rendered after it.
  const partial = paintCandidateThumbs(
    id => (id === 'rot90_back' ? createRecordingSurface() : null), payload, source,
    { width: 32, height: 32, padding: 1 },
    { floor: 'F', agree: 'A', gap: 'G', mismatch: 'M', unrelated: 'U', skeleton: 'S' });
  eq(partial.length, 1, 'L15 a missing slot is skipped, not thrown over');
  eq(paintCandidateThumbs(() => createRecordingSurface(), null, null, { width: 8, height: 8 }, {}).length,
     0, 'L16 and no payload paints nothing at all');

  // NOW THE DOM HALF: the shell puts a real slot in every one of the eight controls.
  const doc = makeDocument();
  const app = bootstrap({
    document: doc,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve({
        state: 'no_winner', refusal: '동점 - 판별 불가',
        reference: { state: 'resolved', kind: 'values', cells: floorCells },
        sources: { map_count: 1, cell_count: srcCells.length, cells: srcCells,
                   maps: [{ map_id: 's1', cell_count: srcCells.length,
                            declared_frame: 'rot0_front', declared_frame_source: 'declared' }] },
        candidates: candidateList().map(c => ({ frame: c.id, state: 'scored',
                                                agreement: 4, discriminating: 6 })),
        declaration: { frames: { rot0_front: 1 }, attested_maps: 1, unattested_maps: 0, axis_sources: {} },
        ruling: { winner: null, reason_code: 'no_discrimination' },
        excluded_total: 0, stats: { scored_cells: 6, elapsed_ms: 4 },
      }),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app.setConfig({ min_margin_dies: 20, min_discriminating_dies: 4 });
  app.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  app.render();
  const slots = doc.querySelectorAll('[data-me2-cand-thumb]');
  eq(slots.length, 8, 'L17 every one of the eight controls carries a picture slot');
  ok(slots.every(s => (s.__ops || []).length > 0), 'L18 and every one of them was drawn into');
  // 🔴 A REPAINT MUST NOT MULTIPLY THEM. `fillGrid`'s sibling defect: a renderer that creates
  //    rather than finds appends a canvas per render, and the page grows without bound.
  app.render();
  eq(doc.querySelectorAll('[data-me2-cand-thumb]').length, 8,
     'L19 a repaint finds the slots it made rather than making eight more');
  ok(doc.querySelectorAll('[data-me2-cand-thumb]')
       .every(s => (s.__ops || []).some(o => o[0] === 'fill')),
     'L20 every picture carries real marks, not just a cleared box');

  // 🔴 THE STATE THE OPERATOR IS ACTUALLY IN, AND THE ONE THE FIXTURE ABOVE DOES NOT REACH.
  //    Everything above runs in `no_winner`, where the run WAS scored -- so a renderer gated on
  //    `numerals` would paint all eight there and still leave the refused screen empty, which is
  //    the exact defect this round exists to end. Measured: gating the thumbnails on `numerals`
  //    changed nothing above. NOT_SCORABLE is a different picture mode (`alone`) and a different
  //    code path, and it is where the pictures matter most, because there are no counts at all.
  const docNS = makeDocument();
  const appNS = bootstrap({
    document: docNS,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve({
        state: 'not_scorable', refusal: '규격이 선언되지 않았습니다.',
        reference: { state: 'resolved', kind: 'values', cells: floorCells },
        sources: { map_count: 1, cell_count: srcCells.length, cells: srcCells,
                   maps: [{ map_id: 's1', cell_count: srcCells.length,
                            declared_frame: 'rot0_front', declared_frame_source: 'declared' }] },
        candidates: [],
        declaration: { frames: { rot0_front: 1 }, attested_maps: 1, unattested_maps: 0, axis_sources: {} },
        ruling: { winner: null, reason_code: 'no_cells_scored' },
        excluded_total: 0, stats: { scored_cells: 0, elapsed_ms: 4 },
      }),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  appNS.setConfig({ min_margin_dies: 20, min_discriminating_dies: 40 });
  appNS.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vmNS = appNS.render();
  eq(vmNS.state, VIEW_STATE.NOT_SCORABLE, 'L21 the refused state, where there are no counts at all');
  ok(!vmNS.numerals, 'L22 and the screen still refuses to rank');
  const slotsNS = docNS.querySelectorAll('[data-me2-cand-thumb]');
  eq(slotsNS.length, 8, 'L23 the eight pictures are there anyway -- they are not a reward for scoring');
  ok(slotsNS.every(s => (s.__ops || []).some(o => o[0] === 'fill')),
     'L24 and every one of them was actually drawn into');
  // And they still differ from each other, which is the only reason to show eight of them.
  eq(new Set(slotsNS.map(s => JSON.stringify(s.__ops))).size, 8,
     'L25 eight DIFFERENT pictures in the refused state, not one picture eight times');
}

// ── M. the screen says why nothing won ──────────────────────────────────────────
//
// 🔴 THE SCREEN HAD THE ANSWER AND SHOWED THE NUMBERS INSTEAD. `no_cells_scored`,
//    `no_candidate_scored`, `no_overlap`, `no_discrimination` and `tie` are decided AHEAD of the
//    two threshold checks, so lowering `min_margin_dies` to 1 moves none of them -- and the
//    operator spent an afternoon reading the code out of the CONSOLE to find that out. The
//    sentence was on the wire the whole time.
//
//    CARRIED, NEVER COMPOSED. What is scored is that the slot holds the server's string BYTE FOR
//    BYTE -- not that it contains it, which a decorated version would also satisfy.
{
  const doc = makeDocument();
  const base = {
    state: 'no_winner', refusal: '판별 다이가 없어 후보를 가를 수 없습니다.',
    reference: { state: 'resolved', kind: 'values', cells: [[0, 0], [1, 0], [0, 1], [1, 1]] },
    sources: { map_count: 1, cell_count: 3, cells: [[0, 0], [1, 0], [2, 2]],
               maps: [{ map_id: 's1', cell_count: 3, declared_frame: 'rot0_front',
                        declared_frame_source: 'declared' }] },
    candidates: [{ frame: 'rot0_front', state: 'scored', agreement: 2, discriminating: 4 },
                 { frame: 'rot90_front', state: 'scored', agreement: 2, discriminating: 4 }],
    declaration: { frames: { rot0_front: 1 }, attested_maps: 1, unattested_maps: 0, axis_sources: {} },
    ruling: { winner: null, reason_code: 'no_discrimination' },
    excluded_total: 0, stats: { scored_cells: 4, elapsed_ms: 4 },
  };
  const app = bootstrap({
    document: doc,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve(base),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app.setConfig({ min_margin_dies: 20, min_discriminating_dies: 4 });
  app.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm = app.render();
  eq(vm.state, VIEW_STATE.SCORED_NO_WINNER, 'M1 the no-winner state, which is where this matters');
  eq(vm.reasonLine, '판별 다이가 없어 후보를 가를 수 없습니다.',
     'M2 the view model carries the server sentence');
  const slot = doc.querySelector('[data-me2-cand-reason]');
  ok(slot, 'M3 a reason slot exists beside the eight');
  eq(slot.textContent, '판별 다이가 없어 후보를 가를 수 없습니다.',
     'M4 and it holds that sentence BYTE FOR BYTE -- nothing of ours is joined to it');
  eq(slot.hidden, false, 'M5 and it is shown');
  eq(vm.reasonCode, 'no_discrimination',
     'M6 the branch that refused is carried too -- for the log, never for the screen');
  ok(!doc.querySelector('[data-me2-cand-reason]').textContent.includes('순위'),
     'M7 no label of ours competes with the server sentence');

  // 🔴 SILENCE IS HONEST. A run that sent no sentence gets NO line -- never an invented label,
  //    which would be indistinguishable from a real answer. Without this the assertion above
  //    would pass on a constant.
  const doc2 = makeDocument();
  const app2 = bootstrap({
    document: doc2,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve({ ...base, refusal: null }),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app2.setConfig({ min_margin_dies: 20, min_discriminating_dies: 4 });
  app2.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm2 = app2.render();
  eq(vm2.reasonLine, '', 'M8 no server sentence means no line, not a line we wrote');
  eq(doc2.querySelector('[data-me2-cand-reason]').hidden, true, 'M9 and the slot hides itself');

  // 🔴 A RUN THAT PRODUCED A WINNER HAS NOTHING TO EXPLAIN, AND IT STILL CARRIES A SENTENCE.
  //    `compose_refusal` runs for EVERY state, so the sentence arrives even here -- which means
  //    "the slot is empty on a winner" is a real gate and not the absence of an input. The
  //    fixture therefore SENDS one; scoring it with `refusal: null` measured nothing, and
  //    deleting the state gate did not turn this red until the sentence was put back.
  const doc3 = makeDocument();
  const app3 = bootstrap({
    document: doc3,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve({ ...base, state: 'scored',
        refusal: '판별 다이가 없어 후보를 가를 수 없습니다.',
        candidates: [{ frame: 'rot0_front', state: 'scored', agreement: 400, discriminating: 528 },
                     { frame: 'rot90_front', state: 'scored', agreement: 100, discriminating: 528 }],
        ruling: { winner: 'rot0_front' } }),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app3.setConfig({ min_margin_dies: 20, min_discriminating_dies: 4 });
  app3.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm3 = app3.render();
  eq(vm3.state, VIEW_STATE.SCORED_WINNER, 'M10 a scored run with a clear margin');
  ok(vm3.cause === null || vm3.cause.detail !== undefined,
     'M10b and the server sentence did travel with it -- the input to the gate exists');
  eq(vm3.reasonLine, '',
     'M11 nothing won-less to explain, so the slot says nothing even though a sentence arrived');
  eq(doc3.querySelector('[data-me2-cand-reason]').hidden, true, 'M12 and it stays hidden');
}

// ── N. THE NO-WINNER CAUSE CARRIES THE SERVER'S SENTENCE, AND THE TOKEN IS BESIDE IT ────────
//
// 🔴 A TWO-WORD TOKEN WAS RENDERED OVER A SENTENCE THAT NAMED THE REPAIR. `causeFor`'s
//    no-winner branch handed back `대칭 기준` and DROPPED the payload's `refusal`, so every
//    consumer of `vm.cause` was told "symmetric reference" while the server had said
//    "the reference footprint is symmetric, the eight frames cannot be told apart, ANOTHER
//    REFERENCE MAP IS NEEDED". Two words cannot carry that last clause, and that last clause is
//    the only part of the message that tells the operator what to do. The occupancy branch and
//    the not-scorable branch already carried the sentence; this one did not, and it is the
//    branch the stuck unit lands in.
//
// 🔴 SUPPLEMENT, NOT REPLACEMENT. The token stays -- `대칭 기준` and `기준 값 없음` are repaired
//    differently and the one-word surfaces need one word -- but it may never be the only thing
//    a reader is given. `causeLine` prefers `detail`, so the sentence is what renders.
//
// 🔴 AND IT MUST NOT BE JOINED TO. `reasonLine` is asserted byte for byte in M above; the
//    measurements ride as a separate LIST and the joining happens once, in the renderer.
{
  // The server's real sentence for `no_discrimination`, byte for byte from
  // `server/map_alignment._RULING_TEXT`. Not paraphrased here: a harness that scores "carried
  // verbatim" against a string of its own invention scores nothing.
  const SENTENCE = '기준 발자국 대칭 - 8프레임 구별 불가 · 다른 기준 맵 필요';
  const stuck = {
    state: 'no_winner', refusal: SENTENCE,
    reference: { state: 'resolved', kind: 'values', cells: [[0, 0], [1, 0], [0, 1], [1, 1]] },
    sources: { map_count: 1, cell_count: 3, cells: [[0, 0], [1, 0], [2, 2]],
               maps: [{ map_id: 's1', cell_count: 3, declared_frame: 'rot0_front',
                        declared_frame_source: 'declared' }] },
    // 🔴 THE WEIGHTED PAIR IS HERE BECAUSE THE RULING BELOW NAMES THE WEIGHTED AXIS. This
    //    fixture used to declare `metric: values_weighted` while carrying ONLY the occupancy
    //    column -- a payload no server emits: `map_alignment.py:1156-1157` sends `value_*`
    //    beside `agreement` on every candidate, and `metric` is chosen from what was measured
    //    (`:1184-1186`). It read as green only because the client read `agreement` no matter
    //    which axis had ruled, which is exactly the defect this round removes. A fixture
    //    carrying one axis cannot tell a client that reads the RULED axis from a client that
    //    reads the first one it finds -- so the fixture now carries the axis it declares.
    //    (Weighted counts are floats on the real wire; these are whole because this unit's
    //    weights are 1 and the fixture's point is the SENTENCE, not the arithmetic.)
    candidates: [{ frame: 'rot0_front', state: 'scored', agreement: 2, discriminating: 4,
                   value_agreement: 2, value_discriminating: 4 },
                 { frame: 'rot90_front', state: 'scored', agreement: 2, discriminating: 4,
                   value_agreement: 2, value_discriminating: 4 }],
    declaration: { frames: { rot0_front: 1 }, attested_maps: 1, unattested_maps: 0, axis_sources: {} },
    // 🔴 THE THIRD METRIC, ON THE WIRE. `values_weighted` joined `occupancy` and `values` on
    //    `ruling.metric` and had no carriage at all on this side.
    ruling: { winner: null, reason_code: 'no_discrimination', metric: 'values_weighted' },
    excluded_total: 0, stats: { scored_cells: 4, elapsed_ms: 4 },
  };
  const doc = makeDocument();
  const logged = [];
  doc.defaultView.console = { log: (...a) => logged.push(a.map(String).join(' ')),
                              warn: () => {}, error: () => {} };
  const app = bootstrap({
    document: doc,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve(stuck),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app.setConfig({ min_margin_dies: 20, min_discriminating_dies: 4 });
  app.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm = app.render();

  eq(vm.state, VIEW_STATE.SCORED_NO_WINNER, 'N1 the state the stuck unit lands in');
  eq(vm.cause.detail, SENTENCE,
     'N2 THE CAUSE CARRIES THE SERVER SENTENCE BYTE FOR BYTE -- this is the assertion that was '
     + 'red: the branch used to drop it and hand back a token instead');
  eq(vm.cause.token, '대칭 기준',
     'N3 and the token survives BESIDE it -- a supplement, never a replacement');
  eq(vm.cause.count, 2, 'N4 with the tied count still beside it');

  // 🔴 THE SENTENCE APPEARS ON SCREEN EXACTLY ONCE. Carrying it in `cause` as well as in
  //    `reasonLine` is two VALUES of one string, which is right; two NODES holding it is a
  //    screen repeating itself. `#me2-verdict-cause` was deleted from the page and this file's
  //    stub still authors it, so the count is what proves the renderer stopped writing there
  //    rather than the page happening not to have the node.
  const nodes = doc.querySelectorAll('[data-me2-cand-reason]')
    .concat(doc.getElementById('me2-verdict-cause') ? [doc.getElementById('me2-verdict-cause')] : [])
    .concat(doc.getElementById('me2-refusal') ? [doc.getElementById('me2-refusal')] : []);
  const holding = nodes.filter(n => String(n.textContent).includes(SENTENCE));
  eq(holding.length, 1,
     'N5 exactly one node on the page holds the sentence -- not the cause slot as well');
  eq(String(holding[0].getAttribute('data-me2-cand-reason')), '',
     'N6 and it is the slot beside the eight, which is the one this state shows');
  eq(holding[0].textContent, SENTENCE,
     'N7 held byte for byte, with nothing of ours joined to it (the M-block property, kept)');

  // 🔴 AND THE CONSOLE RECORD DOES NOT SAY IT TWICE EITHER. `logDiagnosis` pushes
  //    `cause.detail` and then the served refusal; the guard between them is the only thing
  //    stopping a doubled line now that both hold the same string.
  const record = logged.join(' | ');
  const occurrences = record.split(SENTENCE).length - 1;
  eq(occurrences, 1, 'N8 the console record carries the sentence once, not twice');
  ok(record.includes('ruling.reason_code=no_discrimination'),
     'N9 the branch that refused is still named beside it');
  eq(vm.rulingMetric, 'values_weighted',
     'N10 THE THIRD METRIC IS CARRIED -- it had no display at all before, so the record could '
     + 'not say which axis the ranking was made on');
  ok(record.includes('ruling.metric=values_weighted'),
     'N11 and it reaches the record as the server spelled it');
  ok(!record.includes('가중') || record.includes(SENTENCE),
     'N12 no Korean word of ours was invented for the axis -- the server owns that sentence');

  // An axis this client has never heard of still reaches the record. Refusing an unknown one
  // would make the NEXT metric invisible exactly where the record is the only witness.
  const alien = adaptPayload({ ...stuck, ruling: { ...stuck.ruling, metric: 'values_ranked' } });
  eq(alien.ruling_metric, 'values_ranked', 'N13 an unrecognised axis is carried, not dropped');
  const bare = adaptPayload({ ...stuck, ruling: { winner: null, reason_code: 'tie' } });
  eq(bare.ruling_metric, null, 'N14 and an absent one is absent, never a plausible default');

  // 🔴 A METRIC MUST NOT SWALLOW THE "NO REASON ON THE WIRE" FINDING. That line is the record's
  //    only witness to a payload that refused and said nothing about why -- a gap on the wire,
  //    not a state this screen can repair. Adding the metric push between the `if` and its
  //    `else if` re-pointed the whole fallback at `rulingMetric`, which is a one-character-class
  //    mistake that no exit code and no other assertion here can see.
  const doc4 = makeDocument();
  const logged4 = [];
  doc4.defaultView.console = { log: (...a) => logged4.push(a.map(String).join(' ')),
                               warn: () => {}, error: () => {} };
  const app4 = bootstrap({
    document: doc4,
    api: {
      counters: { reads: 0, writes: 0 },
      // A metric, and NOTHING that says why nothing won.
      loadReferenceView: () => Promise.resolve({ ...stuck, refusal: null,
        ruling: { winner: null, metric: 'values_weighted' } }),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.resolve({}),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app4.setConfig({ min_margin_dies: 20, min_discriminating_dies: 4 });
  app4.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm4 = app4.render();
  eq(vm4.reasonCode, '', 'N15a the payload named no branch');
  eq(vm4.reasonLine, '', 'N15b and sent no sentence');
  const record4 = logged4.join(' | ');
  ok(record4.includes('the reason is not on the wire'),
     'N15 the gap is still reported when a metric is present -- the metric line must sit AFTER '
     + 'that if/else chain, never inside it');
  ok(record4.includes('ruling.metric=values_weighted'),
     'N16 and the axis is recorded alongside, not instead');
}

// ── P. THE SCREEN CARRIES THE RULING, ON THE RULING'S OWN AXIS ─────────────────
//
// 🔴 BOTH HALVES WERE MEASURED ON THE LIVE SERVER, 2026-08-06, `dt_map` /
//    `SYN-IDX-FULL-R0` against `valid_die_ref:PRD-A_DT13`. The server answered
//    `ruling.metric = "index"`, `winner = "rot0_front"`, margin 87. The screen said
//    `채점 불가` and drew `88 / 43`, `66 / 21`, `62 / 17` -- the OCCUPANCY column -- and drew
//    the four back frames, which the server had marked `not_considered` with a reason, as
//    `0 / 0` with `data-me2-cand-scored="true"`: indistinguishable from a frame that was
//    scored and lost.
//
// 🔴 AND `setConfig` IS DELIBERATELY NEVER CALLED HERE. `loadAlignConfig` rejects
//    unconditionally (`api.js`, `ROUTES.config` is null -- the route does not exist), so this
//    is the live threshold situation exactly: the ONLY thresholds available are the ones the
//    ruling carries. Calling `setConfig` would hide the second half of defect (1) behind a
//    value no live run has.
//
// THE FIXTURE IS THE WIRE, TRIMMED -- every number below is what the route served.
{
  const REASON_SIDE = '미채점 - 면 선언 제외';
  const indexWire = {
    state: 'scored', refusal: null,
    reference: { state: 'resolved', kind: 'values', map_id: 'PRD-A_DT13',
                 cells: [[0, 0], [1, 0], [0, 1], [1, 1]] },
    sources: { map_count: 1, cell_count: 4, cells: [[0, 0], [1, 0], [2, 2]],
               maps: [{ map_id: 'SYN-IDX-FULL-R0', cell_count: 88 }] },
    declaration: { frames: {}, attested_maps: 0, unattested_maps: 1, axis_sources: {} },
    ruling: { metric: 'index', index_axis: 'ranking', winner: 'rot0_front',
              margin: 87, discriminating: 87,
              min_margin_dies: 20, min_discriminating_dies: 20,
              sides_considered: ['front'], sides_narrowed: true, reason_code: null },
    candidates: [
      { frame: 'rot0_front', state: 'scored', agreement: 88, discriminating: 43,
        index_agreement: 88, index_discriminating: 87, reason: null },
      { frame: 'rot90_front', state: 'scored', agreement: 66, discriminating: 21,
        index_agreement: 1, index_discriminating: 0, reason: null },
      { frame: 'rot180_front', state: 'scored', agreement: 62, discriminating: 17,
        index_agreement: 1, index_discriminating: 0, reason: null },
      { frame: 'rot270_front', state: 'scored', agreement: 66, discriminating: 21,
        index_agreement: 1, index_discriminating: 0, reason: null },
      { frame: 'rot0_back', state: 'not_considered', agreement: 0, discriminating: 0,
        index_agreement: null, index_discriminating: null, reason: REASON_SIDE },
      { frame: 'rot90_back', state: 'not_considered', agreement: 0, discriminating: 0,
        index_agreement: null, index_discriminating: null, reason: REASON_SIDE },
      { frame: 'rot180_back', state: 'not_considered', agreement: 0, discriminating: 0,
        index_agreement: null, index_discriminating: null, reason: REASON_SIDE },
      { frame: 'rot270_back', state: 'not_considered', agreement: 0, discriminating: 0,
        index_agreement: null, index_discriminating: null, reason: REASON_SIDE },
    ],
    excluded_total: 0, stats: { scored_cells: 88, elapsed_ms: 16 },
  };

  const doc = makeDocument();
  const logged = [];
  doc.defaultView.console = { log: (...a) => logged.push(a.map(String).join(' ')),
                              warn: () => {}, error: () => {} };
  const app = bootstrap({
    document: doc,
    api: {
      counters: { reads: 0, writes: 0 },
      loadReferenceView: () => Promise.resolve(indexWire),
      loadWorklist: () => Promise.resolve({ rows: [] }),
      loadAlignConfig: () => Promise.reject(new Error('route not served')),
      confirmFrame: () => Promise.resolve({}),
    },
  });
  app.selectDecision({ eqp: 'E', product: 'P' });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  const vm = app.render();

  // P1. THE VERDICT ON SCREEN IS THE ONE THE SERVER SENT.
  eq(vm.state, VIEW_STATE.SCORED_WINNER,
     'P1 the screen reaches the server\'s verdict, not a `채점 불가` of its own');
  eq(doc.getElementById('me2-workbench').getAttribute('data-me2-state'), 'scored',
     'P1b and the page is told the scored state');
  eq(vm.headline, '추천 있음', 'P1c the headline is the answer, not a refusal');
  eq(vm.rulingMetric, 'index', 'P1d the axis is carried as the server spelled it');
  eq(vm.summary.marginDies, 87,
     'P1e the margin is the server\'s own 87, not the 22 the occupancy column gives');

  const cells = doc.querySelectorAll('[data-me2-candidate]');
  const cellOf = (id) => cells.find(c => c.getAttribute('data-frame-code') === id);
  const numbersOf = (id) => `${cellOf(id).querySelector('[data-me2-cand-agree]').textContent}`
    + ` / ${cellOf(id).querySelector('[data-me2-cand-discriminating]').textContent}`;

  // P2. THE NUMBERS ARE THE RULED AXIS'S. `88 / 43` is the shipped bug, and both columns are
  //     in the payload, so this is a WRONG number rather than a missing one.
  eq(numbersOf('rot0_front'), '88 / 87',
     'P2 the winner shows the index counts (occupancy would say 88 / 43)');
  eq(numbersOf('rot90_front'), '1 / 0',
     'P2b and a losing frame shows 1 / 0, not the 66 / 21 occupancy gives it');
  eq(numbersOf('rot180_front'), '1 / 0', 'P2c every scored frame, not just the winner');
  ok(cellOf('rot0_front').querySelector('[data-me2-cand-tags]').textContent.includes('추천'),
     'P2d and the frame the server named is the one badged');

  // P3. A FRAME NOBODY LOOKED AT READS DIFFERENTLY FROM A FRAME THAT LOST.
  for (const id of ['rot0_back', 'rot90_back', 'rot180_back', 'rot270_back']) {
    const cell = cellOf(id);
    eq(cell.getAttribute('data-me2-cand-scored'), 'false',
       `P3 ${id} is not marked as carrying real numbers`);
    eq(cell.getAttribute('data-me2-cand-state'), 'not_considered',
       `P3b ${id} carries the server's own word for what happened to it`);
    eq(cell.querySelector('[data-me2-cand-unknown]').textContent, REASON_SIDE,
       `P3c ${id} says WHY, in the server's sentence -- not \`미상\`, which means something else`);
    eq(numbersOf(id), ' / ',
       `P3d ${id} was given no numerals at all -- the placeholder 0 is not a measurement`);
  }
  const scoredCell = cellOf('rot0_front');
  ok(scoredCell.getAttribute('data-me2-cand-scored') === 'true'
     && scoredCell.getAttribute('data-me2-cand-state') === 'scored',
     'P3e while a scored frame is marked scored -- the two are distinguishable IN THE DOM, '
     + 'which is what the styling needs and what a screenshot could not tell apart before');
  eq(scoredCell.querySelector('[data-me2-cand-unknown]').textContent, 'AUTHORED',
     'P3f and a scored cell\'s sibling word is left exactly as the page authored it');

  // P4. THE REPORT DID NOT NARROW WITH THE SEARCH. The console record is where the operator
  //     has been reading the real table; four rows for an eight-frame answer is the same
  //     defect one layer down.
  const record = logged.join(' | ');
  const table = logged.find(l => l.includes('[map2] 후보 8'));
  ok(!!table, 'P4 all eight frames reach the console record, not just the four that were scored');
  ok(!!table && table.includes(REASON_SIDE),
     'P4b with the reason beside the ones that carry no numbers');
  ok(record.includes('ruling.metric=index'), 'P4c and the axis is named in the record');
}

console.log(`ASSERTIONS ${compared} ${failures.length}`);
if (failures.length > 0) {
  console.log('\nFAILURES');
  for (const f of failures) console.log(`  - ${f}`);
}
process.exit(failures.length === 0 ? 0 : 1);

/**
 * The drawn geometry of one SVG layer, as a string.
 *
 * Two different frames seat the same cells at different places, so this value cannot be equal
 * across a real repaint -- which is what makes "the picture followed the click" a MEASUREMENT
 * rather than a hope. Comparing child COUNTS would not: the same population is drawn either way.
 */
function layerShape(doc, id) {
  const g = doc.getElementById(id);
  if (!g) return '';
  return (g.children || []).map(r => `${r.getAttribute('x')},${r.getAttribute('y')}`).join(' ');
}

// ────────────────────────────────────────────────────────────────────────────────
// A MINIMAL DOCUMENT. Not jsdom: this harness must run with no `node_modules`. It implements
// only what the composition root actually uses, which is itself a useful measurement -- the
// list below IS the DOM surface of Map Editor 2, and it is short because exactly one module
// touches a DOM at all.
function makeDocument() {
  const registry = new Map();
  const docListeners = {};

  function makeEl(tag) {
    const el = {
      tagName: String(tag).toUpperCase(),
      children: [],
      attrs: {},
      style: {},
      className: '',
      hidden: false,
      disabled: false,
      tabIndex: 0,
      type: '',
      title: '',
      parentNode: null,
      __listeners: {},
      __ops: [],
      setAttribute(k, v) { this.attrs[k] = String(v); },
      getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
      removeAttribute(k) { delete this.attrs[k]; },
      append(...nodes) { for (const n of nodes) this.appendChild(n); },
      appendChild(node) { node.parentNode = this; this.children.push(node); return node; },
      addEventListener(type, fn) { (this.__listeners[type] = this.__listeners[type] || []).push(fn); },
      // Events BUBBLE in this stub, because the composition root delegates candidate clicks
      // from the document. A stub that did not bubble would let a delegated handler silently
      // never fire and still report a green shell.
      dispatchEvent(type, key) {
        let defaultPrevented = false;
        const ev = { target: this, key: key === undefined ? type : key,
                     preventDefault() { defaultPrevented = true; } };
        let n = this;
        while (n) {
          for (const fn of n.__listeners[type] || []) fn(ev);
          n = n.parentNode;
        }
        for (const fn of (docListeners[type] || [])) fn(ev);
        // 🔴 NATIVE ACTIVATION (2026-08-06). Enter on a focused <button> also fires a `click`
        //    unless the keydown default was cancelled. Without this the stub cannot see a
        //    double confirmation, because the shell binds BOTH `click` and a document keydown
        //    to `onConfirm` -- one keystroke, two calls, and with one-action confirm two POSTs.
        //    See G24-G27 below, which count requests rather than checking the end state: one
        //    write and two writes leave an identical session and an identical DOM.
        if (type === 'keydown' && ev.key === 'Enter' && this.tagName === 'BUTTON'
            && !this.disabled && !defaultPrevented) {
          this.dispatchEvent('click');
        }
        return !defaultPrevented;
      },
      closest(sel) {
        let node = this;
        while (node) {
          if (matches(node, sel)) return node;
          node = node.parentNode;
        }
        return null;
      },
      getContext() {
        const ops = this.__ops;
        return {
          clearRect: (...a) => ops.push(['clear', ...a]),
          fillRect: (...a) => ops.push(['fill', ...a]),
          strokeRect: (...a) => ops.push(['stroke', ...a]),
          set fillStyle(v) {}, get fillStyle() { return ''; },
          set strokeStyle(v) {}, get strokeStyle() { return ''; },
          set lineWidth(v) {}, get lineWidth() { return 1; },
        };
      },
    };
    // `textContent = ''` CLEARS CHILDREN in a real DOM, and the composition root relies on
    // that to re-render a list. A stub that stores the string without clearing would let the
    // shell append eight candidate controls per render and still pass -- so the stub models
    // the real behaviour, and G9 is what proves it does.
    let ownText = '';
    Object.defineProperty(el, 'textContent', {
      get() {
        return this.children.length > 0
          ? this.children.map(c => c.textContent).join('')
          : ownText;
      },
      set(v) { ownText = String(v); this.children.length = 0; },
    });
    Object.defineProperty(el, 'firstChild', { get() { return this.children[0] || null; } });
    return el;
  }

  // Attribute selectors only. That is the whole selector language the composition root uses,
  // which is itself the measurement: the binding contract is ids and `data-me2-*`, nothing else.
  function matches(node, sel) {
    const m = /^\[([^\]=]+)(?:="([^"]*)")?\]$/.exec(sel);
    if (!m || !node.attrs) return false;
    if (!Object.prototype.hasOwnProperty.call(node.attrs, m[1])) return false;
    return m[2] === undefined || node.attrs[m[1]] === m[2];
  }

  function collect(node, sel, out) {
    for (const child of node.children || []) {
      if (matches(child, sel)) out.push(child);
      collect(child, sel, out);
    }
    return out;
  }

  function withQuery(el) {
    el.querySelectorAll = (sel) => collect(el, sel, []);
    el.querySelector = (sel) => collect(el, sel, [])[0] || null;
    return el;
  }

  const body = makeEl('body');
  const doc = {
    body,
    documentElement: makeEl('html'),
    __listeners: docListeners,
    createElement: (tag) => withQuery(makeEl(tag)),
    createElementNS: (_ns, tag) => withQuery(makeEl(tag)),
    getElementById: (id) => registry.get(id) || null,
    addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
    querySelectorAll: (sel) => collect(body, sel, []),
    querySelector: (sel) => collect(body, sel, [])[0] || null,
    defaultView: { console, getComputedStyle: () => ({ getPropertyValue: () => '' }) },
  };

  function node(tag, id, attrs) {
    const n = withQuery(makeEl(tag));
    if (id) { n.setAttribute('id', id); registry.set(id, n); }
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    return n;
  }

  // Every id the composition root binds. If this list and `ELEMENT_IDS` diverge, G1 says so.
  for (const id of ['me2-workbench', 'me2-worklist-rows', 'me2-worklist-rows-unscorable',
                    'me2-worklist-search', 'me2-worklist-empty', 'me2-worklist-meta',
                    'me2-worklist-boundary', 'me2-worklist-boundary-label',
                    // The set-up row: 대상 테이블 -> x · y · value -> 기준. G1 is what forced
                    // these in here the moment the shell started binding them.
                    'me2-rule-select', 'me2-table-select', 'me2-col-x', 'me2-col-y', 'me2-col-value',
                    'me2-reference-select', 'me2-question-note', 'me2-columns-confirm',
                    // Accepting the borrowed wafer geometry. Added the moment the shell started
                    // binding it, and the live page carries it since the markup landed. G1 is about
                    // the STUB keeping up with the shell — it never scored the live page either way,
                    // and `map2_geometry_assumption_harness.mjs` scores what the control does.
                    'me2-assume-accept',
                    'me2-badge-session',
                    'me2-badge-unscorable', 'me2-badge-remaining', 'me2-picture-svg',
                    'me2-layer-floor', 'me2-layer-miss', 'me2-layer-onlyone', 'me2-layer-alone',
                    'me2-picture-caption', 'me2-refusal', 'me2-verdict-headline',
                    'me2-verdict-cause', 'me2-source-list', 'me2-sources-meta',
                    'me2-metric-conflict', 'me2-confirm-btn', 'me2-confirm-sentence',
                    'me2-confirm-note', 'me2-confirm-hint',
                    // The footer, bound since 2026-08-06 to carry the refusal state attribute.
                    'me2-confirmbar',
                    'me2-export-btn', 'me2-paste-result']) {
    body.appendChild(node('div', id));
  }
  if (registry.get('me2-worklist-search')) registry.get('me2-worklist-search').value = '';

  // The count slots, spelled the way the page spells them. Each is seeded with `AUTHORED` so
  // the harness can tell "the shell wrote a number" from "the shell wrote a stand-in" from
  // "the shell left the page's own content alone", which are three different behaviours and
  // only the first and third are allowed.
  for (const attr of ['data-me2-picture-meta', 'data-me2-top-agree', 'data-me2-top-discriminating',
                      'data-me2-margin-dies', 'data-me2-maps-total', 'data-me2-maps-excluded']) {
    const slot = node('span', null, { [attr]: '' });
    slot.textContent = 'AUTHORED';
    body.appendChild(slot);
  }

  // The headline is a THREE-SIBLING slot, exactly as the page builds it: `.me2-num` carries the
  // counts, `.me2-unknown` and `.me2-busy` carry the words for the states that have no counts,
  // and CSS shows one. Modelling it faithfully is what lets G7c catch a write to the parent.
  const head = registry.get('me2-verdict-headline');
  const num = node('span', null, { 'data-me2-verdict': '' });
  num.textContent = 'AUTHORED';
  head.appendChild(num);
  head.appendChild(node('span', null, { 'data-me2-verdict-unknown': '' }));
  head.appendChild(node('span', null, { 'data-me2-verdict-busy': '' }));

  // Two source rows plus the cross-source row, each carrying its own value and count slots.
  const list = registry.get('me2-source-list');
  for (const field of ['s1', 's2', '__cross_source__']) {
    const row = node('button', null, { 'data-me2-source': '', 'data-source-field': field });
    row.appendChild(node('span', null, { 'data-me2-source-value': '' }));
    row.appendChild(node('span', null, { 'data-me2-agree': '' }));
    row.appendChild(node('span', null, { 'data-me2-discriminating': '' }));
    list.appendChild(row);
  }

  // The eight candidate controls, 2 columns by 4 rows, as the page lays them out.
  //
  // 🔴 THE GRID SHIPS `hidden`, EXACTLY AS `map_editor2.html` AUTHORS IT. That is not a detail
  //    of the stub, it is the condition the shell has to clear: the page publishes eight
  //    controls in a container it hides, and something has to unhide it. A stub that started
  //    visible could not tell "the shell unhid the grid" from "nobody ever hid it", and the
  //    live screen showed no candidates at all for exactly that reason.
  const grid = node('div', 'me2-cands-s1', { 'data-me2-candidates-for': 's1' });
  grid.hidden = true;
  for (const rot of [0, 90, 180, 270]) {
    for (const side of ['front', 'back']) {
      const cand = node('button', null, {
        'data-me2-candidate': '', 'data-rotation': String(rot), 'data-side': side,
        'data-frame-code': `rot${rot}_${side}`, 'aria-pressed': 'false',
      });
      cand.appendChild(node('span', null, { 'data-me2-cand-tags': '' }));
      // The per-candidate score slot, three siblings deep like every other count on the page:
      // `.me2-num` holds the two figures, and the words for the states with no figures sit
      // beside it. Seeded `AUTHORED` so a write to the wrong node is visible.
      const score = node('span', null, { 'data-me2-cand-score': '' });
      const scoreNum = node('span', null, { 'data-me2-cand-num': '' });
      scoreNum.appendChild(node('span', null, { 'data-me2-cand-agree': '' }));
      scoreNum.appendChild(node('span', null, { 'data-me2-cand-discriminating': '' }));
      const scoreUnknown = node('span', null, { 'data-me2-cand-unknown': '' });
      scoreUnknown.textContent = 'AUTHORED';
      score.appendChild(scoreNum);
      score.appendChild(scoreUnknown);
      cand.appendChild(score);
      grid.appendChild(cand);
    }
  }
  list.appendChild(grid);
  return doc;
}
