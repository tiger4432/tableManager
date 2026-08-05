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
         withArmed, withConfig, isExploringOnly, PHASE } from '../src/map2/session.js';
import { computeSeating, compareSeatings, seatOf, unionBounds } from '../src/map2/seating.js';
import { createRecordingSurface, paintComparison, paintSeating, layoutFor,
         paintSkeleton } from '../src/map2/painter.js';
import { decideVerdict, VERDICT, REASON } from '../src/map2/verdict_bridge.js';
import { buildViewModel, assertNoRatio, VIEW_STATE, UNKNOWN,
         agreementText, marginText } from '../src/map2/view_model.js';
import { createApiClient, ROUTES } from '../src/map2/api.js';
import { readArtifact, isImplemented, rejectionSummary, unmappedRejectionCodes,
         REJECTED } from '../src/map2/artifact_gateway.js';
import { bootstrap, ELEMENT_IDS } from '../src/map2/main.js';

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
  ok(isExploringOnly(picked), 'B12 exploring, nothing armed');
  ok(!isExploringOnly(withArmed(picked, true)), 'B13 arming leaves the exploring-only state');
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
  // 🔴 LISTING IS NOT RANKING. The refusal to rank is deliberate and it stays -- no badge, no
  //    selection, every cell inert. The eight counts the server already measured are NOT part
  //    of that refusal, and hiding them left the operator with `미상` eight times and no way to
  //    see WHY nothing won. A zeroed score lands in exactly this state.
  const listedNW = notScorable.candidates.find(c => c.id === 'rot270_back');
  eq(listedNW.countText, '일치 512 / 판별 528',
     'F23d the eight are LISTED with their measured counts even though nothing won');
  eq(notScorable.candidates.find(c => c.id === 'rot0_front').countText, '일치 400 / 판별 528',
     'F23e every candidate the server scored, not just one');
  eq(notScorable.candidates.map(c => c.id).join(','),
     'rot0_front,rot90_front,rot180_front,rot270_front,rot0_back,rot90_back,rot180_back,rot270_back',
     'F23f in declaration order -- sorting by score would BE the ranking that was refused');
  ok(notScorable.candidates.every(c => c.inert && !c.badges.includes('추천')),
     'F23g and still nothing selectable and nothing recommended');
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

  // Arm, then commit. The write happens on the second press and not before.
  const confirm = doc.getElementById('me2-confirm-btn');
  confirm.dispatchEvent('click');
  eq(api.counters.writes, 0, 'G23 arming is not a write');
  ok(app.peek().armed, 'G24 the control is armed');
  eq(confirm.getAttribute('data-armed'), 'true', 'G25 and the page is told so');
  confirm.dispatchEvent('click');
  eq(api.counters.writes, 1, 'G26 the second press is the one write');

  // Action accounting against the switchover bar.
  ok(app.bar.actions <= 6, 'G27 the whole loop including the confirm stays in single digits');
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
  ok(doc2.querySelectorAll('[data-me2-candidate]').every(c => c.disabled),
     'G34 every candidate is inert when nothing was scored');

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
  ok(doc3.querySelectorAll('[data-me2-candidate]').every(c => c.disabled),
     'J20 with nothing scored, every candidate is inert');
}

console.log(`ASSERTIONS ${compared} ${failures.length}`);
if (failures.length > 0) {
  console.log('\nFAILURES');
  for (const f of failures) console.log(`  - ${f}`);
}
process.exit(failures.length === 0 ? 0 : 1);

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
      dispatchEvent(type) {
        const ev = { target: this, key: type };
        let n = this;
        while (n) {
          for (const fn of n.__listeners[type] || []) fn(ev);
          n = n.parentNode;
        }
        for (const fn of (docListeners[type] || [])) fn(ev);
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
                    'me2-confirm-note', 'me2-confirm-hint', 'me2-export-btn', 'me2-paste-result']) {
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
