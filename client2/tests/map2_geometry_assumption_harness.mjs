/**
 * MAP EDITOR 2 -- THE BORROWED WAFER GEOMETRY: THE OFFER, THE ACT, AND THE MARK IT LEAVES.
 *
 * THIS HARNESS DOES NOT SLICE SOURCE. It `import`s every module it scores.
 *
 * THE DEFECT IT EXISTS FOR: the server can score a source map that declares no physical spec by
 * borrowing the reference floor's wafer dimensions, and the client could not name what had
 * happened. The offer was emitted into nothing and the screen stayed a dead end.
 *
 * 🔴 THE ACT WAS REMOVED ON 2026-08-06 (product owner: 「가정 적용은 자동으로 되게해」).
 *    The server applies the borrowing by default, this client sends the parameter in neither
 *    direction, and the accept control is gone -- it was a control for an act nobody performed,
 *    because the `available` state that would have shown it can no longer occur.
 *
 * ⚠️ SO THIS FILE NOW SCORES ONE THING ABOVE ALL: **THAT REMOVING CONSENT DID NOT REMOVE
 *    NOTICE.** Automatic is a decision about who agrees, not about who is told. Nobody consents
 *    per unit any more and the answer still rests on a borrowed wafer, so every disclosure has
 *    to arrive with nobody having pressed anything -- which makes sections E-G stricter than
 *    they were, not looser. If a later round shrinks one of them, that turns 「automatic」 into
 *    「silent」, and this file is where it should go red.
 *
 * WHAT IS SCORED
 *   A. THE VOCABULARY -- `assumed` is a token both sides know. A borrowed geometry that the
 *      client cannot name is sorted into some other bucket while every server test stays green.
 *   B. THE ASSUMPTION IS AUTOMATIC AND THIS CLIENT NEVER ASKS -- no question field, no query
 *      parameter, in either direction. (Was 「NOTHING ASSUMES BY DEFAULT」; re-pointed rather
 *      than deleted, because a removed false claim leaves no record that the default moved.)
 *   C+D. NOTHING LATCHES -- a borrowing does not follow the operator to the next unit, floor or
 *      table. The worry outlived the feature: it is now about the server's answer rather than
 *      the client's claim, and five assertions about the ACT have no successor, named in place.
 *   E. `requested` IS NOT `applied` -- decoded from the wire, where the distinction still lives.
 *   F. THE MARK -- one line (the server's own sentence, naming the floor), a per-map basis, a
 *      workbench hook, and a disclosure on the one write.
 *   G. END TO END WITH NO CLICK -- every mark above, reached on first paint.
 *   H. PICKING THE FLOOR BY HAND -- still one fetch, still no claim on the wire.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe): no emoji, no em-dash.
 */

import { ASSUMED, DECLARED, ABSENT, DECLARATION_TOKENS,
         COMPUTABLE_TOKENS } from '../src/map2/declaration.js';
import { decodeReferenceView, verdictContext,
         ASSUMPTION_APPLIED, ASSUMPTION_AVAILABLE, ASSUMPTION_UNAVAILABLE,
         isAssumedGeometry, isDeclaredGeometry } from '../src/map2/decode.js';
import { createMapSession, withQuestion, withCatalog, withDecision, withPayload,
         resolveQuestion, EMPTY_QUESTION, BINDING_DECLARED } from '../src/map2/session.js';
import { buildViewModel, assertNoRatio, VIEW_STATE, WORDS } from '../src/map2/view_model.js';
import { createApiClient } from '../src/map2/api.js';
import { bootstrap, adaptPayload } from '../src/map2/main.js';
import { decideVerdict } from '../src/map2/verdict_bridge.js';

let compared = 0;
const failures = [];
function ok(cond, what) { compared++; if (!cond) failures.push(what); }
function eq(actual, expected, what) {
  compared++;
  if (actual !== expected) {
    failures.push(`${what}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// ── the wire, as the server actually serves it ──────────────────────────────────
// `server/map_alignment.py:1366-1373` for the block, `:797-812` for the sentence, `:815-834`
// for the per-map basis. The sentence is copied verbatim rather than paraphrased: this harness
// scores that the client RENDERS the server's words, so inventing my own here would score the
// client against a sentence nobody serves.
const FLOOR = { table: 'core_wafer_map', map_id: 'LOT-A_05' };
const OFFER_TEXT = '맵 3개는 기준(core_wafer_map / LOT-A_05)과 같은 웨이퍼로 가정하면 채점 가능'
  + ' - 가정은 기록에 남고 규격으로 저장되지 않음';
const APPLIED_TEXT = '맵 3개를 기준(core_wafer_map / LOT-A_05)의 웨이퍼 치수를 빌려 채점'
  + ' - 동일 웨이퍼 가정이며 이 맵의 규격 선언이 아님';

function wire(over) {
  const o = over || {};
  return {
    unit: { rule: 'r', decision_key: { dt_eqp: 'E', product: 'P' },
            source_table: 'dt_log', map_table: 'dt_map', map_key_columns: ['dt_job'] },
    state: o.state || 'scored',
    refusal: o.refusal === undefined ? null : o.refusal,
    reference: { state: 'resolved', kind: 'values', source: 'declared',
                 table: FLOOR.table, map_id: FLOOR.map_id, count: 500, cells: [] },
    sources: {
      map_count: 2, usable_map_count: 2, cell_count: 4, cells: [], truncated: false,
      maps: o.maps || [
        { map_id: 'M1', cell_count: 2, declared_frame: 'rot0_front',
          declared_frame_source: 'declared', geometry: DECLARED, geometry_basis: DECLARED },
        { map_id: 'M2', cell_count: 2, declared_frame: null,
          declared_frame_source: null, geometry: ABSENT, geometry_basis: ASSUMED },
      ],
    },
    candidates: [
      { frame: 'rot0_front', agreement: 512, discriminating: 528 },
      { frame: 'rot90_front', agreement: 300, discriminating: 528 },
    ],
    declaration: { frames: { rot0_front: 1 }, unanimous: false, frame: null,
                   attested_maps: 1, unattested_maps: 1, axis_sources: {} },
    ruling: { winner: 'rot0_front', margin: 212, reason_code: null,
              geometry_assumed: o.geometry_assumed === true },
    assumption: o.assumption === undefined
      ? { state: ASSUMPTION_AVAILABLE, requested: false, basis: { ...FLOOR },
          map_count: 3, map_ids: ['M2', 'M3', 'M4'], text: OFFER_TEXT }
      : o.assumption,
    excluded: o.excluded || [],
    excluded_total: o.excluded_total === undefined ? 1 : o.excluded_total,
    stats: { scored_cells: 528, elapsed_ms: 12 },
  };
}

const THRESHOLDS = { min_margin_dies: 20, min_discriminating_dies: 40 };

// ════════════════════════════════════════════════════════════════════════════════
// A. THE VOCABULARY -- CONFIRMED, NOT ASSUMED
// ════════════════════════════════════════════════════════════════════════════════
// This is the check the brief asked to CONFIRM rather than perform blind. `assumed` was already
// in `declaration.js` when this lane arrived (the frame-declaration lane landed it, with the
// reasoning at `declaration.js:113-140`). Scored here anyway: a token that is present today and
// silently dropped tomorrow is the same divergence, and only an assertion notices.
ok(DECLARATION_TOKENS.includes(ASSUMED),
   'A1 `assumed` is in the shared provenance vocabulary');
eq(ASSUMED, 'assumed', 'A2 spelled byte-identically to server/map_overlay.GEOMETRY_ASSUMED');
ok(COMPUTABLE_TOKENS.includes(ASSUMED) && COMPUTABLE_TOKENS.includes(DECLARED),
   'A3 `assumed` is COMPUTABLE -- a map scored on borrowed geometry was scored');
ok(!COMPUTABLE_TOKENS.includes(ABSENT),
   'A4 and computability did not become "anything that is not absent"');

// ════════════════════════════════════════════════════════════════════════════════
// B. THE ASSUMPTION IS AUTOMATIC -- AND THIS CLIENT NEVER ASKS
// ════════════════════════════════════════════════════════════════════════════════
// 🔴 THIS SECTION SAID 「NOTHING ASSUMES BY DEFAULT」 AND THAT BECAME FALSE ON 2026-08-06.
//    It is RE-POINTED rather than deleted: a false claim removed leaves nothing behind, while a
//    false claim re-pointed records that the default changed and when. What changed is the
//    server -- `get_map_alignment_view(..., assume_reference_geometry: bool = True, ...)` -- on
//    a product owner ruling that the borrowing apply automatically. The client half followed by
//    LOSING ITS KNOB ENTIRELY: no accept control, no question field, no query parameter.
//
// ⚠️ WHAT IS SCORED HERE IS CONSENT, NOT NOTICE. That the borrowing happens without anyone
//    pressing anything is this section; that the operator is TOLD it happened is sections E-G,
//    and those got stricter, not looser. Automatic is a decision about consent.
ok(!('assumeReferenceGeometry' in EMPTY_QUESTION),
   'B1 the question tuple has no assume field at all -- there is nothing to set');

const sent = [];
function recordingClient() {
  return createApiClient({
    baseUrl: '',
    fetchImpl: (url) => {
      sent.push(String(url));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(wire()) });
    },
  });
}
const REQ = { rule: 'r', mapTable: 'dt_map', params: { dt_eqp: 'E', product: 'P' } };

await recordingClient().loadReferenceView({ ...REQ });
ok(!sent[0].includes('assume_reference_geometry'),
   'B2 an ordinary view request carries no assume parameter at all -- omitted, not sent false');

// 🔴 INVERTED ON 2026-08-06, AND THE INVERSION IS THE PIN. This used to read 「B3 the claim,
//    once made, is on the wire」. There is no way to make the claim any more: the transport
//    dropped the parameter, so even a caller that passes `true` sends nothing. That is what
//    makes the server's default the only thing in force, in ONE place, rather than two halves
//    that can disagree.
sent.length = 0;
await recordingClient().loadReferenceView({ ...REQ, assumeReferenceGeometry: true });
ok(!sent[0].includes('assume_reference_geometry'),
   'B3 even a caller that passes `true` puts NO parameter on the wire -- the knob is gone');

// The old loop guarded a `=== true` branch against truthy junk unlocking a claim. The branch is
// gone, so these can no longer discriminate between a strict check and a sloppy one -- they now
// pin the simpler fact that NO input shape reaches the wire. Kept rather than dropped: someone
// re-adding a coercion here is exactly the regression worth catching, and it costs nothing.
for (const junk of ['true', 1, {}, 'yes', false]) {
  sent.length = 0;
  await recordingClient().loadReferenceView({ ...REQ, assumeReferenceGeometry: junk });
  ok(!sent[0].includes('assume_reference_geometry'),
     `B4 no caller input (${JSON.stringify(junk)}) can put the parameter back on the wire`);
}

// ════════════════════════════════════════════════════════════════════════════════
// C + D. THE ACT, AND THAT IT DOES NOT LATCH
// ════════════════════════════════════════════════════════════════════════════════
const CATALOG = {
  tables: [{ table: 'dt_map', label: 'dt_map' }, { table: 'core_wafer_map', label: 'core_wafer_map' }],
  columns: { dt_map: ['dt_x', 'dt_y', 'c_bn'], core_wafer_map: ['core_x', 'core_y', 'c_bn'] },
  columnTypes: { dt_map: { dt_x: 'number', dt_y: 'number' },
                 core_wafer_map: { core_x: 'number', core_y: 'number' } },
  binding: { dt_map: { x: 'dt_x', y: 'dt_y', val: 'c_bn', source: BINDING_DECLARED },
             core_wafer_map: { x: 'core_x', y: 'core_y', val: null, source: BINDING_DECLARED } },
  references: { dt_map: [{ value: `${FLOOR.table}:${FLOOR.map_id}`, mapId: FLOOR.map_id,
                           kind: 'values', cellCount: 500 },
                         { value: 'core_wafer_map:OTHER', mapId: 'OTHER',
                           kind: 'values', cellCount: 400 }],
                core_wafer_map: [] },
};

// 🔴 THE ACT IS GONE, SO FIVE OF THESE TEN HAVE NO SUCCESSOR. Named rather than absorbed
//    into the floor, because 「the count went down」 and 「the coverage went down」 are different
//    facts and only one of them is true here:
//      C1  accepting sets the claim                 -- nothing accepts.
//      C2  accepting RE-ASKS                        -- nothing accepts.
//      C3  the previous answer is dropped, not re-labelled -- nothing accepts.
//      D5  a VALUE column does not clear the claim  -- there is no claim to keep.
//    (C5 IS re-pointed rather than lost: it asked whether the claim survived a null picker, and
//     it now asks whether the field is absent from a resolved question at all.)
//    What they scored was the ACT. The act was removed on a product owner ruling, so the
//    assertions are not stale, they are about a feature that no longer exists.
//
//    D1 / D3 / D4 DO have successors and they are below, because the WORRY survives the
//    feature: 「a borrowing must not silently follow the operator to the next unit」 is now
//    about the server's answer instead of the client's claim, and it is if anything more
//    urgent -- nobody consents per unit any more.
const base = withCatalog(createMapSession({ config: THRESHOLDS }), CATALOG);

// C4 stands unchanged: it is about `resolveQuestion` and never was about the claim.
const noPicker = resolveQuestion({ ...EMPTY_QUESTION, mapTable: 'dt_map',
                                   columns: { x: 'dt_x', y: 'dt_y', val: null } }, CATALOG);
eq(noPicker.reference, null, 'C4 no floor is picked (the ordinary state)');
ok(!('assumeReferenceGeometry' in noPicker),
   'C5 and a resolved question carries no assume field -- the tuple lost the axis, not the value');

// D1's SUCCESSOR. The claim used to die with the row; now it is the APPLIED state that must,
// and it dies for a stronger reason -- `withDecision` drops the payload, so the borrowing
// cannot be re-rendered under the next unit's labels at all.
const askedWithFloor = withQuestion(base, { mapTable: 'dt_map',
                                            reference: `${FLOOR.table}:${FLOOR.map_id}` });
// Built here rather than reusing `appliedWire` below: that constant is declared later in the
// file, and a `const` referenced before its line throws at run time rather than hoisting.
const borrowedAnswer = wire({ geometry_assumed: true,
  assumption: { state: ASSUMPTION_APPLIED, requested: false, basis: { ...FLOOR },
                map_count: 3, map_ids: ['M2'], text: APPLIED_TEXT } });
const seeded = withPayload(askedWithFloor, borrowedAnswer, askedWithFloor.requestSeq);
ok(seeded.payload, 'D1a a unit scored on a borrowed wafer has its answer in hand');
const nextRow = withDecision(seeded, { eqp: 'E2', product: 'P2' });
eq(nextRow.payload, null,
   'D1 the borrowing does not follow the operator to the next row -- the answer it rode on is '
   + 'dropped, not re-labelled');
eq(nextRow.question.mapTable, seeded.question.mapTable,
   'D2 and the rest of the set-up survives the row change, as before');

// D3 / D4's SUCCESSORS. Moving the floor or the table still RE-ASKS. That was the mechanism
// that took the claim off; the mechanism is what mattered and it is still here.
const movedFloor = withQuestion(seeded, { reference: 'core_wafer_map:OTHER' });
ok(movedFloor.requestSeq > seeded.requestSeq && movedFloor.payload === null,
   'D3 moving the floor re-asks and drops the answer -- a borrowing from THAT floor cannot be '
   + 'shown under this one');
const movedTable = withQuestion(seeded, { mapTable: 'core_wafer_map' });
ok(movedTable.requestSeq > seeded.requestSeq && movedTable.payload === null,
   'D4 moving the table re-asks and drops the answer -- likewise for THOSE maps');

// ════════════════════════════════════════════════════════════════════════════════
// E + F. THE DECODE AND THE MARK
// ════════════════════════════════════════════════════════════════════════════════
const offered = decodeReferenceView(wire());
eq(offered.assumption.state, ASSUMPTION_AVAILABLE, 'E1 an untaken offer reads as available');
ok(offered.assumption.offered, 'E2 and is actionable');
ok(!offered.assumption.applied, 'E3 and has not been taken');
eq(offered.assumption.basisTable, undefined, 'E4 the basis is a record, not flat fields');
eq(offered.assumption.basis.table, FLOOR.table, 'E5 the offer names the floor it borrows from');
eq(offered.assumption.basis.mapId, FLOOR.map_id, 'E6 including which map on it');
eq(offered.assumption.mapCount, 3, 'E7 and how many maps it covers');
eq(offered.assumption.text, OFFER_TEXT, 'E8 the sentence is the server, verbatim');
eq(offered.geometryAssumed, false, 'E9 nothing was assumed, so the ruling says so');

const appliedWire = wire({
  geometry_assumed: true,
  assumption: { state: ASSUMPTION_APPLIED, requested: true, basis: { ...FLOOR },
                map_count: 3, map_ids: ['M2', 'M3', 'M4'], text: APPLIED_TEXT },
});
const applied = decodeReferenceView(appliedWire);
ok(applied.assumption.applied, 'E10 an applied assumption reads as applied');
ok(!applied.assumption.offered, 'E11 and is no longer an offer -- the act was performed');
eq(applied.geometryAssumed, true, 'E12 the ruling carries the fact about itself');

// 🔴 REQUESTED IS NOT APPLIED. A request on a unit whose floor does not resolve comes back
//    `unavailable`, and reading the request back as the state would report a borrowing that
//    never happened -- a screen confident about a wafer nobody borrowed from.
const refusedWire = wire({
  assumption: { state: ASSUMPTION_UNAVAILABLE, requested: true, basis: null,
                map_count: 0, map_ids: [], text: null },
});
const refused = decodeReferenceView(refusedWire);
ok(!refused.assumption.applied && !refused.assumption.offered,
   'E13 asking on a unit with nothing to borrow from is not a borrowing');
eq(refused.assumption.requested, true, 'E14 but the request is still recorded, not erased');
eq(refused.assumption.text, null, 'E15 and there is no sentence to show');

// Per map: what it says about itself vs what this run stood on.
const m1 = offered.sources.find(s => s.id === 'M1');
const m2 = offered.sources.find(s => s.id === 'M2');
eq(m1.geometry, DECLARED, 'F1 a declared map says so');
ok(isDeclaredGeometry(m1), 'F2 and stood on its own declaration');
eq(m2.geometry, ABSENT, 'F3 a borrowing map declares nothing of its own');
eq(m2.geometryBasis, ASSUMED, 'F4 and the run stood on borrowed dimensions');
ok(isAssumedGeometry(m2) && !isDeclaredGeometry(m2),
   'F5 the two questions stay split -- borrowed is not declared, and not a refusal either');

// A token neither side agreed on must be NAMED, not bucketed. This is the failure mode the
// brief pointed at: the server grows a word, the client sorts it into whatever catches it, and
// every server test stays green.
const alien = decodeReferenceView(wire({
  maps: [{ map_id: 'M9', cell_count: 1, declared_frame: null, declared_frame_source: null,
           geometry: 'borrowed_ish', geometry_basis: 'borrowed_ish' }],
}));
eq(alien.sources[0].geometryBasis, null, 'F6 an unknown provenance token is dropped, not kept');
ok(alien.rejected.some(r => r.includes('borrowed_ish')),
   'F7 and named out loud, so the fix goes to the side that can make it');

const badState = decodeReferenceView(wire({
  assumption: { state: 'maybe', requested: false, basis: { ...FLOOR },
                map_count: 1, map_ids: ['M2'], text: 'x' },
}));
eq(badState.assumption.state, ASSUMPTION_UNAVAILABLE,
   'F8 an unrecognised assumption state falls back to "nothing on offer", never to an offer');
ok(badState.rejected.some(r => r.includes('maybe')), 'F9 and is named');

const nameless = decodeReferenceView(wire({
  assumption: { state: ASSUMPTION_AVAILABLE, requested: false, basis: null,
                map_count: 2, map_ids: ['M2', 'M3'], text: 'x' },
}));
ok(!nameless.assumption.offered,
   'F10 an offer with no floor named is not an offer -- "borrow from somewhere" is not a claim');
ok(nameless.rejected.some(r => r.includes('no basis')), 'F11 and is named');

// ── the view model ──────────────────────────────────────────────────────────────
function ready(rawPayload, question) {
  let s = withCatalog(createMapSession({ config: THRESHOLDS }), CATALOG);
  if (question) s = withQuestion(s, question);
  s = withDecision(s, { eqp: 'E', product: 'P' });
  const adapted = adaptPayload(rawPayload);
  s = withPayload(s, adapted, s.requestSeq);
  return buildViewModel({ session: s, verdict: decideVerdict(adapted.per_candidate, THRESHOLDS,
                                                             adapted.__context) });
}

const vmOffer = ready(wire());
eq(vmOffer.assumption.line, OFFER_TEXT, 'F12 the offer is ONE line and it is the server\'s');
ok(vmOffer.assumption.line.includes(FLOOR.map_id),
   'F13 which names the floor -- not summarised away');
// 🔴 THE VIEW MODEL NO LONGER EXPOSES `offered`, AND THE DECODER STILL DOES. That split is
//    the assertion: `decode` describes THE WIRE (the server can still emit `available`, and a
//    client that did not know the word would push it to `rejected`), while this layer describes
//    THE SCREEN -- and the screen has no accept control. E2 above still pins the decoded half.
ok(!('offered' in vmOffer.assumption),
   'F14 the view model offers no control affordance -- there is nothing to accept');
eq(vmOffer.assumption.word, '', 'F15 an untaken offer is not a mark on the answer');
eq(vmOffer.confirm.geometryAssumed, false, 'F16 and the write discloses nothing');

const vmApplied = ready(appliedWire);
eq(vmApplied.assumption.line, APPLIED_TEXT,
   'F17 an applied assumption keeps saying so, in the server\'s words');
eq(vmApplied.assumption.word, WORDS.geometryAssumed, 'F18 plus a one-word mark for tight slots');
eq(vmApplied.assumption.basisLabel, `${FLOOR.table}:${FLOOR.map_id}`,
   'F19 the basis is spelled the way /view takes it back');
ok(!('offered' in vmApplied.assumption),
   'F20 and an applied borrowing exposes none either -- same field, gone in both states');
ok(vmApplied.confirm.geometryAssumed && vmApplied.confirm.note.includes(WORDS.geometryAssumed),
   'F21 the ONE write discloses that its geometry was borrowed');
ok(vmApplied.confirm.enabled,
   'F22 and is NOT blocked -- the claim is the operator\'s to make; blocking would rebuild the '
   + 'dead end this capability exists to open');
eq(vmApplied.state, VIEW_STATE.SCORED_WINNER, 'F23 a borrowed geometry still produces a verdict');
assertNoRatio(vmApplied);
compared++;

// The disclosure outranks "unchanged", and neither is lost.
const stored = ready({ ...appliedWire,
  declaration: { ...appliedWire.declaration, unanimous: true, unattested_maps: 0 } });
ok(stored.confirm.note.startsWith(WORDS.geometryAssumed),
   'F24 which geometry the answer rests on leads the confirm note');

// ════════════════════════════════════════════════════════════════════════════════
// G. END TO END THROUGH THE SHELL -- NOBODY PRESSES ANYTHING, AND THE SCREEN STILL SAYS SO
// ════════════════════════════════════════════════════════════════════════════════
// 🔴 THIS SECTION USED TO BE 「one click, one fetch, the flag on the wire」. There is no
//    click (product owner 2026-08-06), so FOUR assertions have no successor and are named
//    rather than absorbed:
//      G4  an offer is not painted as a warning  -- the un-warned `available` state cannot
//                                                   occur, so there is no offer to under-paint.
//      G5  accepting costs exactly ONE fetch     -- nothing accepts.
//      G6  that request carries the claim        -- no request carries it; B3 pins that.
//      G9  the control is gone after the act     -- the control is gone before the act.
//    And G2 is REPLACED, not lost: it checked that the sentence merely `includes` the floor id;
//    G7b/G7c now pin the server's sentence BYTE FOR BYTE, which is strictly stronger and is the
//    assertion that matters once nobody has agreed to anything.
//    Everything else got STRICTER, because the disclosures now have to arrive with nobody
//    having done anything: what used to be reached by a click must now be true on first paint.
{
  const doc = makeDocument();
  const asked = [];
  const app = bootstrap({
    document: doc,
    api: { confirmFrame: () => Promise.resolve({}) },
  });
  app.setLoader((decision, question) => {
    // The question is recorded WHOLE, so a field creeping back in is visible here and not only
    // at the transport.
    asked.push(question);
    return Promise.resolve(appliedWire);
  });
  app.setConfig(THRESHOLDS);
  app.setCatalog(CATALOG);
  app.selectDecision({ eqp: 'E', product: 'P' });
  await settle();

  const note = doc.getElementById('me2-question-note');
  ok(!('assumeReferenceGeometry' in asked[0]),
     'G1 the request carries no assume field -- the server default is the only thing in force');
  ok(doc.getElementById('me2-assume-accept') === null,
     'G3 THERE IS NO ACCEPT CONTROL -- a control for an act nobody performs');
  eq(app.missing.length, 0,
     'G3b and the shell does not bind one either -- removed from both halves, not orphaned');

  // 🔴 EVERY DISCLOSURE BELOW IS REACHED WITHOUT A CLICK, AND THAT IS THE POINT OF THE
  //    ROUND. Removing consent must not remove notice: nobody agreed to this borrowing per
  //    unit, so the screen carries the whole weight of saying it happened.
  eq(doc.getElementById('me2-workbench').getAttribute('data-me2-assumed'), 'true',
     'G7 the result region is marked as standing on a borrowed wafer');
  ok(note.textContent.includes(FLOOR.map_id),
     'G7b the SERVER sentence is on screen and NAMES THE FLOOR the dimensions came from');
  eq(note.textContent, APPLIED_TEXT,
     'G7c verbatim -- not summarised to 가정 적용, which would drop which two maps');
  eq(note.getAttribute('data-me2-note-tone'), 'caution',
     'G8 and the line is a warning, because numbers rest on it');
  eq(doc.getElementById('me2-confirm-note').textContent.includes(WORDS.geometryAssumed), true,
     'G10 the write discloses it');

  const rows = doc.querySelectorAll('[data-me2-source]');
  const borrowed = rows.find(r => r.getAttribute('data-source-field') === 'M2');
  const own = rows.find(r => r.getAttribute('data-source-field') === 'M1');
  ok(borrowed && borrowed.getAttribute('data-me2-geometry-basis') === ASSUMED,
     'G11 the map that borrowed says so, per row');
  ok(borrowed && borrowed.getAttribute('data-me2-proposed') === 'true',
     'G12 wearing the SAME proposal shape as a guessed column pair -- not a second language');
  ok(own && own.getAttribute('data-me2-proposed') === 'false',
     'G13 and the map that measured its own geometry does not');
}

// ════════════════════════════════════════════════════════════════════════════════
// H. PICKING THE FLOOR BY HAND -- STILL ONE FETCH, STILL NO CLAIM ON THE WIRE
// ════════════════════════════════════════════════════════════════════════════════
// 🔴 THIS SECTION WAS 「PICK THE FLOOR BY HAND, THEN ACCEPT」. The second motion no longer
//    exists, so SEVEN assertions have no successor -- named, not absorbed:
//      H5  the offer survived the pick, so there is a control    -- there is no control.
//      H6  accepting after a manual pick is ONE re-ask           -- nothing accepts.
//      H7  the claim survives the click in this order            -- no click, no claim.
//      H8  it is a BOOLEAN at the transport edge                 -- nothing crosses the edge.
//      H9  the claim reaches the URL                             -- B3 pins that it cannot.
//      H10 the floor is still on the same request                -- H3 pins the floor alone.
//      H11 non-boolean junk is refused at the question           -- the question has no field.
//    The FIRST motion survives whole, and it is what this file still has to score: picking a
//    floor is a real operator act with a real cost, and it must not smuggle a claim along.
{
  const doc = makeDocument();
  const seenAtLoader = [];
  const sentUrls = [];
  const app = bootstrap({ document: doc, api: { confirmFrame: () => Promise.resolve({}) } });
  const client = createApiClient({
    baseUrl: '',
    fetchImpl: (url) => {
      sentUrls.push(String(url));
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve(sentUrls.length >= 2 ? appliedWire : wire()),
      });
    },
  });
  // The page entry's own loader, copied in shape from `map_editor2.js`. It no longer forwards
  // any assume flag, because the question no longer has one to forward.
  app.setLoader((decision, question) => {
    seenAtLoader.push(question);
    return client.loadReferenceView({
      rule: 'r',
      mapTable: question.mapTable,
      params: { dt_eqp: decision.eqp, product: decision.product },
      xCol: question.columns.x, yCol: question.columns.y, valCol: question.columns.val,
      reference: question.reference || undefined,
      includeCells: true,
    });
  });
  app.setConfig(THRESHOLDS);
  app.setCatalog(CATALOG);
  app.selectDecision({ eqp: 'E', product: 'P' });
  await settle();

  const refSelect = doc.getElementById('me2-reference-select');
  const fetchesBeforePick = app.bar.fetches;
  refSelect.value = `${FLOOR.table}:${FLOOR.map_id}`;
  refSelect.dispatchEvent('change');
  await settle();
  eq(app.bar.fetches - fetchesBeforePick, 1, 'H1 picking the floor costs exactly one fetch');
  ok(!('assumeReferenceGeometry' in seenAtLoader[1]),
     'H2 and the question it asks with carries no assume field');
  ok(sentUrls[1].includes('reference=') && sentUrls[1].includes(encodeURIComponent(FLOOR.map_id)),
     'H3 the picked floor is on the wire');
  ok(!sentUrls[1].includes('assume_reference_geometry'),
     'H4 and no claim rides along with it -- in EITHER direction, so the server default stands');
}

// ════════════════════════════════════════════════════════════════════════════════
// I. THE REFUSAL KEEPS ITS MEASUREMENTS
// ════════════════════════════════════════════════════════════════════════════════
// THE DEFECT: the operator read `격자 치수가 기준과 다름 - 같은 잘림이 아님` and could not tell
// WHICH grid was wrong or BY HOW MUCH -- which is the entire content of that message. The
// numbers are served: the exclusion tally carries them per reason as `example_detail`
// (`server/map_alignment.py:654-655` for this one, `:387-389` for `cells_outside_grid`). What
// the client rendered was `payload.refusal`, and `compose_refusal` builds that sentence out of
// the reason LABELS only (`:1062-1067`) -- so the measurement was in the payload, one field
// away, and the decoder read nothing but `excluded_total`.
//
// SCORED THROUGH THE SHELL, not against the view model alone: the loss was at the last hop.
const GRID_LABEL = '격자 치수가 기준과 다름 - 같은 잘림이 아님';
const GRID_DETAIL = '소스 45x39 · 기준 44x39';
const OUTSIDE_LABEL = '셀이 빌린 격자 밖 - 같은 격자의 부분집합이 아닙니다';
const OUTSIDE_DETAIL = '셀 범위 x 0~44 · y 0~40이 빌린 격자의 인덱스 공간 x 0~43 · y 0~38를 '
  + '벗어납니다 - 같은 격자의 부분집합이 아닙니다';
const NO_CELLS_LABEL = '좌표 0건';
// The server's sentence, as `compose_refusal` composes it: labels and counts, no measurements.
const REFUSAL_SENTENCE = `채점 0건 - 소스 맵 5개 중 5개 제외 · ${GRID_LABEL} (3) · `
  + `${OUTSIDE_LABEL} (1) · ${NO_CELLS_LABEL} (1)`;

function refusedTallyWire(rows) {
  return wire({
    state: 'not_scorable',
    refusal: REFUSAL_SENTENCE,
    excluded: rows,
    excluded_total: rows.reduce((n, r) => n + (r.count || 0), 0),
  });
}

const TALLY = [
  { reason_code: 'grid_dims_differ', reason: GRID_LABEL, count: 3,
    example_map_id: 'M2', example_detail: GRID_DETAIL },
  { reason_code: 'cells_outside_grid', reason: OUTSIDE_LABEL, count: 1,
    example_map_id: 'M3', example_detail: OUTSIDE_DETAIL },
  // No measurement to carry: `좌표 0건` is complete as a label. It must contribute NO line
  // rather than an empty one, or every refusal grows a trail of separators.
  { reason_code: 'no_cells', reason: NO_CELLS_LABEL, count: 1,
    example_map_id: 'M4', example_detail: null },
];

{
  const doc = makeDocument();
  const logged = [];
  doc.defaultView.console = { log: (...a) => logged.push(a.map(String).join(' ')) };
  const app = bootstrap({ document: doc, api: { confirmFrame: () => Promise.resolve({}) } });
  app.setLoader(() => Promise.resolve(refusedTallyWire(TALLY)));
  app.setConfig(THRESHOLDS);
  app.setCatalog(CATALOG);
  app.selectDecision({ eqp: 'E', product: 'P' });
  await settle();

  const shown = doc.getElementById('me2-refusal').textContent;
  ok(shown.includes(GRID_DETAIL),
     'I1 THE MEASUREMENT REACHES THE SCREEN -- the operator can see which grid is wrong and '
     + 'by how much, not merely that one is');
  ok(shown.startsWith(REFUSAL_SENTENCE),
     'I2 and the server\'s sentence still leads, byte for byte -- nothing was re-worded');
  ok(shown.includes(OUTSIDE_DETAIL),
     'I3 the other measured reason rides the SAME path -- one renderer, not one per reason');
  ok(!shown.includes(' ·  ') && !shown.endsWith(' · '),
     'I4 a reason with nothing to measure contributes no empty line');
  // The console keeps what the line cannot hold: which map was the example, per reason.
  //
  // 🔴 SCORED ON THE TALLY LINE, NOT ON THE MAP ID APPEARING ANYWHERE. `M2`..`M4` are also the
  //    assumption block's `map_ids`, so `record.includes('M2')` was green before this lane
  //    touched anything -- an assertion that cannot fail is not a check. The whole composed row
  //    is matched instead, including the reason that has NO measurement: an unmeasured reason
  //    must still be recorded with its example map, which is the only place that fact survives.
  const record = logged.join(' | ');
  ok(record.includes(`제외 · ${NO_CELLS_LABEL} · 1개 · 예: M4`),
     'I5 the console records the whole tally row, example map included, even for a reason '
     + 'that carries no measurement');
  ok(record.includes(GRID_DETAIL), 'I6 and carries the measurement whole');
}

// The view model keeps the two apart: `detail` is the server's sentence and nothing is appended
// INTO it. A harness already scores that field as verbatim, and folding the measurements in
// would leave that assertion passing while the field stopped being what it claims.
{
  const vm = ready(refusedTallyWire(TALLY));
  eq(vm.state, VIEW_STATE.NOT_SCORABLE, 'I7 the run is refused');
  eq(vm.cause.detail, REFUSAL_SENTENCE, 'I8 `detail` is the server sentence, unchanged');
  eq((vm.cause.measurements || []).length, 2,
     'I9 and the measurements are a separate LIST -- one entry per reason that had one');
  eq((vm.cause.measurements || [])[0], GRID_DETAIL,
     'I10 in the order the server ranked them, never re-sorted here');

  // 🔴 NO ALLOW-LIST OF REASON CODES. A reason this client has never heard of still arrives with
  //    the server's own label and the server's own measurement; keying the render on a known set
  //    would make the next server reason silently measurement-less, which is this defect again.
  const alienTally = [{ reason_code: 'wafer_lot_mismatch', reason: '알 수 없는 사유',
                        count: 2, example_map_id: 'M9', example_detail: '소스 LOT-A · 기준 LOT-B' }];
  const alien = ready(refusedTallyWire(alienTally));
  eq((alien.cause.measurements || [])[0], '소스 LOT-A · 기준 LOT-B',
     'I11 an unknown reason code keeps its measurement');

  const bare = ready(wire({ state: 'not_scorable', refusal: REFUSAL_SENTENCE }));
  eq((bare.cause.measurements || []).length, 0,
     'I12 a payload with no tally measures nothing rather than inventing a placeholder');
  eq(bare.cause.detail, REFUSAL_SENTENCE, 'I13 and the sentence is unaffected');
}

console.log(`ASSERTIONS ${compared} ${failures.length}`);
if (failures.length > 0) {
  console.log('\nFAILURES');
  for (const f of failures) console.log(`  - ${f}`);
}
process.exit(failures.length === 0 ? 0 : 1);

// ────────────────────────────────────────────────────────────────────────────────
function settle() {
  return Promise.resolve().then(() => {}).then(() => {}).then(() => {}).then(() => {});
}

/** The minimal document. Not jsdom: this harness runs with no `node_modules`. */
function makeDocument() {
  const registry = new Map();
  const docListeners = {};

  function makeEl(tag) {
    const el = {
      tagName: String(tag).toUpperCase(), children: [], attrs: {}, style: {}, className: '',
      hidden: false, disabled: false, type: '', value: '', parentNode: null, __listeners: {},
      setAttribute(k, v) { this.attrs[k] = String(v); },
      getAttribute(k) {
        return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
      },
      removeAttribute(k) { delete this.attrs[k]; },
      appendChild(n) { n.parentNode = this; this.children.push(n); return n; },
      insertBefore(n, ref) {
        const at = this.children.indexOf(ref);
        n.parentNode = this;
        if (at < 0) this.children.push(n); else this.children.splice(at, 0, n);
        return n;
      },
      addEventListener(type, fn) { (this.__listeners[type] = this.__listeners[type] || []).push(fn); },
      dispatchEvent(type, key) {
        const ev = { target: this, key: key === undefined ? type : key };
        let n = this;
        while (n) { for (const fn of n.__listeners[type] || []) fn(ev); n = n.parentNode; }
        for (const fn of (docListeners[type] || [])) fn(ev);
      },
      closest(sel) {
        let n = this;
        while (n) { if (matches(n, sel)) return n; n = n.parentNode; }
        return null;
      },
    };
    let ownText = '';
    Object.defineProperty(el, 'textContent', {
      get() {
        return this.children.length > 0 ? this.children.map(c => c.textContent).join('') : ownText;
      },
      set(v) { ownText = String(v); this.children.length = 0; },
    });
    return el;
  }

  function matches(node, sel) {
    if (!node || !node.attrs) return false;
    const byId = /^#([A-Za-z0-9_-]+)$/.exec(sel);
    if (byId) return node.attrs.id === byId[1];
    const m = /^\[([^\]=]+)(?:="([^"]*)")?\]$/.exec(sel);
    if (!m) return false;
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

  const body = withQuery(makeEl('body'));
  const doc = {
    body, documentElement: makeEl('html'), __listeners: docListeners,
    createElement: (tag) => withQuery(makeEl(tag)),
    createElementNS: (_ns, tag) => withQuery(makeEl(tag)),
    getElementById: (id) => registry.get(id) || null,
    addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
    querySelectorAll: (sel) => collect(body, sel, []),
    querySelector: (sel) => collect(body, sel, [])[0] || null,
    defaultView: { console: { log() {} }, getComputedStyle: () => ({ getPropertyValue: () => '' }) },
  };

  function node(tag, id, attrs) {
    const n = withQuery(makeEl(tag));
    if (id) { n.setAttribute('id', id); registry.set(id, n); }
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    return n;
  }

  for (const id of ['me2-rule-select', 'me2-table-select', 'me2-col-x', 'me2-col-y',
                    'me2-col-value', 'me2-reference-select']) {
    body.appendChild(node('select', id));
  }
  // 🔴 `me2-assume-accept` IS NO LONGER AUTHORED HERE, and its removal from this list is
  //    part of the change rather than tidying. The button was deleted from the page on
  //    2026-08-06; a stub that kept authoring it would hand `getElementById` a node the real
  //    document does not have, and G3 -- 「there is no accept control」 -- would fail against a
  //    node this file invented. The older note here warned about the mirror image of exactly
  //    this: a stub that authors its own node passes forever after someone deletes the button.
  //    It is the same rule read the other way, and it bit within the hour.
  for (const id of ['me2-columns-confirm', 'me2-confirm-btn']) {
    body.appendChild(node('button', id));
  }
  for (const id of ['me2-workbench', 'me2-worklist-rows', 'me2-worklist-rows-unscorable',
                    'me2-worklist-search', 'me2-worklist-empty', 'me2-worklist-meta',
                    'me2-worklist-boundary', 'me2-worklist-boundary-label', 'me2-question-note',
                    'me2-badge-session', 'me2-badge-unscorable', 'me2-badge-remaining',
                    'me2-picture-svg', 'me2-layer-floor', 'me2-layer-miss', 'me2-layer-onlyone',
                    'me2-layer-alone', 'me2-picture-caption', 'me2-refusal',
                    'me2-verdict-headline', 'me2-source-list', 'me2-sources-meta',
                    'me2-metric-conflict', 'me2-confirm-sentence', 'me2-confirm-note',
                    // The footer, bound since 2026-08-06 to carry the refusal state.
                    'me2-confirmbar',
                    'me2-confirm-hint', 'me2-export-btn', 'me2-paste-result',
                    // The rank picture, bound since 2026-08-06 (third census: the stub).
                    'me2-index-control', 'me2-index-colour', 'me2-index-legend',
                    'me2-index-bar', 'me2-index-min', 'me2-index-max', 'me2-index-note']) {
    body.appendChild(node('div', id));
  }
  for (const attr of ['data-me2-picture-meta', 'data-me2-top-agree', 'data-me2-top-discriminating',
                      'data-me2-margin-dies', 'data-me2-maps-total', 'data-me2-maps-excluded']) {
    const slot = node('span', null, { [attr]: '' });
    slot.textContent = 'AUTHORED';
    body.appendChild(slot);
  }
  const head = registry.get('me2-verdict-headline');
  const num = node('span', null, { 'data-me2-verdict': '' });
  num.textContent = 'AUTHORED';
  head.appendChild(num);

  // The page publishes the source row inside a <template>; the shell clones it per map. Without
  // it no source row exists at all, and the per-map marker could not be scored.
  const tpl = node('template', 'me2-source-row-template');
  const tplRoot = withQuery(makeEl('div'));
  const row = node('button', null, { 'data-me2-source': '', 'data-source-field': '' });
  row.appendChild(node('span', null, { 'data-me2-source-value': '' }));
  row.appendChild(node('span', null, { 'data-me2-agree': '' }));
  row.appendChild(node('span', null, { 'data-me2-discriminating': '' }));
  tplRoot.appendChild(row);
  tplRoot.appendChild(node('div', null, { 'data-me2-candidates-for': '' }));
  tpl.content = { cloneNode: () => cloneOf(tplRoot) };
  body.appendChild(tpl);

  function cloneOf(src) {
    const copy = withQuery(makeEl(src.tagName));
    copy.attrs = { ...src.attrs };
    delete copy.attrs.id;
    for (const child of src.children) copy.appendChild(cloneOf(child));
    return copy;
  }

  return doc;
}
