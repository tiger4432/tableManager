// S-19 «화면 절반» — 「원점이 «물러난» 맵을 화면이 말하나」가 닫혔나.
//
// 🔴 이 하니스는 «대상을 import 합니다» — 판정이 `origin_basis.js` 에 살아서 DOM 없이
//    «화면이 말하는 문장 그대로»를 잽니다.
// 🔴 그리고 나르개(`decode.js`)와 적응(`adaptPayload`)도 «같이» 잽니다. 셋 중 하나만 되면
//    화면은 그대로이고, 그게 「소스에 있고 브라우저엔 없다」의 모양입니다.
// 🔴 판별식 표본은 총괄이 서버 절반에서 쓴 그것입니다 — 「다른 칸이 «전부 같은데» 원점만
//    다른 두 맵」. 두 표본이 다른 칸에서도 갈리면 그 표본은 판별식이 아닙니다.
//
// Run: node client2/tests/map2_origin_basis_harness.mjs
import {
  originBoxNote,
  ORIGIN_BASIS_MASK,
  ORIGIN_BASIS_CIRCLE,
  ORIGIN_BASIS_MASK_OFF_GRID,
  ORIGIN_BASIS_ABSENT,
} from '../src/map2/origin_basis.js';
import { sourceFrameAttestation } from '../src/map2/attestation.js';
import { decodeReferenceView } from '../src/map2/decode.js';
import { adaptPayload } from '../src/map2/main.js';

let pass = 0, fail = 0;
const failed = [];
function ok(cond, name) {
  if (cond) { pass++; console.log(`  OK   ${name}`); }
  else { fail++; failed.push(name); console.log(`  BAD  ${name}`); }
}

const spell = (id) => `frame(${id})`;

console.log('-- the judgement itself ----------------------------------------------');
// 🔴 ㉠ THE ROUND'S SENTENCE. The two rows are identical except for the one token, so if the
//    judgement read anything else these two would come out the same -- which is the defect.
const onMask = { origin_basis: ORIGIN_BASIS_MASK };
const offGrid = { origin_basis: ORIGIN_BASIS_MASK_OFF_GRID };
ok(originBoxNote(offGrid).note !== '', 'A1 a map whose origin fell back to the circle SAYS so');
ok(originBoxNote(onMask).note === '', 'A2 ...and a map whose box stood on the mask says nothing');
// 🔴 A3 WAS NEARLY VACUOUS AS FIRST WRITTEN. 'the two differ' stays true when the two are
//    SWAPPED, so the M1 mutant (fire on `mask`) left it green while A1/A2 caught it. What it
//    now asserts is a property nothing else here covers: the note depends on THAT FIELD
//    ALONE. A row that differs in everything else must still read the same, or some other
//    field has quietly become part of this judgement.
ok(originBoxNote({
  origin_basis: ORIGIN_BASIS_MASK_OFF_GRID, confirmed_by_person: true,
  stored_candidate_id: 'rot0_front', confirmed_candidate_id: 'rot90_front',
  geometry: 'declared', geometry_basis: 'assumed',
}).note === originBoxNote(offGrid).note,
  'A3 the note follows origin_basis ALONE — every other field left it unmoved');
// CONTROL: the two inputs differ in exactly one field, so A1..A3 cannot pass for another reason.
ok(Object.keys(onMask).length === 1 && Object.keys(offGrid).length === 1,
  'A4 CONTROL: the two rows differ ONLY in origin_basis');
// 🔴 The sentence must NOT name the origin mask-based -- that is the false sentence ruling 36
//    forbids, and it is what the operator already believes.
ok(!originBoxNote(offGrid).note.includes('기준'),
  'A5 ...and it does not call the fallen-back origin the mask-based one (ruling 36)');
ok(originBoxNote(offGrid).basis === ORIGIN_BASIS_MASK_OFF_GRID,
  'A6 the basis and the note come from ONE return value, so they cannot drift');

console.log('\n-- the three that must stay silent (무회귀) ---------------------------');
ok(originBoxNote({ origin_basis: ORIGIN_BASIS_CIRCLE }).note === '',
  'B1 `circle` says nothing — it is normal and common, and a note there is noise on most maps');
ok(originBoxNote({ origin_basis: ORIGIN_BASIS_ABSENT }).note === '',
  'B2 `absent` says nothing — no grid is another part of the rows story');
ok(originBoxNote({ origin_basis: ORIGIN_BASIS_MASK }).note === '',
  'B3 `mask` says nothing — it stood where it was meant to');
// ⚠️ ABSENT FIELD MEANS EXACTLY ONE THING: an older server. Not 0, not 모름.
ok(originBoxNote({}).note === '' && originBoxNote({}).basis === null,
  'B4 a MISSING field draws nothing and invents no value (old server)');
ok(originBoxNote(null).note === '', 'B5 ...and neither does a missing row');
// 🔴 A FIFTH VALUE MUST NOT DRAW. The four are the servers whole set today; an unknown token
//    is something this client has not been taught, and attaching a sentence to it is the quiet
//    kind of wrong.
ok(originBoxNote({ origin_basis: 'something_new' }).note === '',
  'B6 an UNKNOWN value draws nothing rather than borrowing the fallback sentence');

console.log('\n-- the two judgements must not fold into one another ------------------');
// 🔴 CRITERION ④. One map can be person-confirmed AND have a fallen-back origin. If either
//    judgement swallowed the other, one of these two facts would silently disappear.
const both = { stored_candidate_id: null, confirmed_candidate_id: 'rot90_front',
               confirmed_by_person: true, origin_basis: ORIGIN_BASIS_MASK_OFF_GRID };
ok(sourceFrameAttestation(both, spell).mark === true,
  'C1 a fallen-back origin does not cost the map its confirm mark');
ok(originBoxNote(both).note !== '',
  'C2 ...and a person confirmation does not silence the origin note');
ok(sourceFrameAttestation({ ...both, origin_basis: ORIGIN_BASIS_MASK }, spell).text
   === sourceFrameAttestation(both, spell).text,
  'C3 the attestation sentence does not move when the origin basis does');

console.log('\n-- the carrier: does the token survive the wire? ----------------------');
const RAW_MAPS = [
  { map_id: 'm1', declared_frame: 'rot90_front', declared_frame_source: 'confirmed',
    confirmed_by_person: true, origin_basis: 'mask' },
  { map_id: 'm2', declared_frame: 'rot90_front', declared_frame_source: 'confirmed',
    confirmed_by_person: true, origin_basis: 'mask_off_grid' },
  { map_id: 'm3', declared_frame: 'rot90_front', declared_frame_source: 'confirmed',
    confirmed_by_person: true },
];
const decoded = decodeReferenceView({ reference: { cells: [] }, sources: { maps: RAW_MAPS } }).sources;
ok(decoded.length === 3, 'D0 three rows decoded — else the rest is vacuous');
ok(decoded[0].originBasis === 'mask', 'D1 decode carries the token through');
ok(decoded[1].originBasis === 'mask_off_grid', 'D2 ...including the one value that draws');
ok(decoded[2].originBasis === null, 'D3 ...and a MISSING field decodes as null, not undefined');

// 🔴 THE MIDDLE LINK. decode carrying it and the judgement reading it are not enough -- the
//    adapter builds the row the screen actually reads, and if the token stops there both ends
//    look correct while the screen is unchanged.
console.log('\n-- the adapter: does the row the screen reads carry it? ---------------');
const adapted = adaptPayload({
  reference: { cells: [] },
  sources: { cells: [[0, 0]], maps: RAW_MAPS },
}).sources;
ok(adapted.length === 3, `E0 three rows adapted — else the rest is vacuous (saw ${adapted.length})`);
ok(adapted[0].origin_basis === 'mask' && adapted[1].origin_basis === 'mask_off_grid',
  'E1 the adapter carries the token onto the row the screen reads');
ok(adapted[2].origin_basis === null, 'E2 ...and carries the old servers absence as null');
// 🔴 무회귀: the fields the row already drew are untouched by this round.
ok(adapted[0].confirmed_candidate_id === 'rot90_front'
   && adapted[1].confirmed_candidate_id === 'rot90_front'
   && adapted[0].confirmed_by_person === true && adapted[1].confirmed_by_person === true,
  'E3 the frame and the confirmation are unchanged for both — this round only ADDS a sentence');
// End to end: raw wire -> adapter -> judgement, the whole path the screen walks.
ok(originBoxNote(adapted[1]).note !== '' && originBoxNote(adapted[0]).note === '',
  'E4 end to end: the same wire that said nothing now separates the two maps');
ok(originBoxNote(adapted[2]).note === '',
  'E5 ...and an old servers payload still draws nothing at the end of that path');

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
