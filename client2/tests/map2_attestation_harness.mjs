// F-19 — 「같은 맵을 오버레이는 확정됨, 워크리스트는 pending」이 닫혔나.
//
// 🔴 이 하니스는 «대상을 import 합니다». 판정이 `main.js` 의 클로저에서 `attestation.js` 로
//    나왔기 때문에 DOM 없이 «화면이 말하는 문장 그대로»를 잽니다.
// 🔴 그리고 나르개(`decode.js`)와 적응(`adaptPayload`)도 «같이» 잽니다 — 셋 중 하나만 되면
//    화면은 그대로이고, 그게 「소스에 있고 브라우저엔 없다」의 모양입니다.
//
// Run: node client2/tests/map2_attestation_harness.mjs
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
// 🔴 ㉠ THE ROUND'S SENTENCE. Both rows carry the SAME token and the SAME frame; only the new
//    boolean differs. If the judgement read the token alone, these two would be identical —
//    which is precisely the defect.
const chain = { stored_candidate_id: null, confirmed_candidate_id: 'rot90_front', confirmed_by_person: false };
const person = { stored_candidate_id: null, confirmed_candidate_id: 'rot90_front', confirmed_by_person: true };
const aChain = sourceFrameAttestation(chain, spell);
const aPerson = sourceFrameAttestation(person, spell);
ok(aPerson.mark === true && aPerson.text.startsWith('✓'), 'A1 a person-confirmed map keeps the confirm mark');
ok(aChain.mark === false && !aChain.text.includes('✓'), 'A2 a chain-stamped map is NOT called confirmed');
ok(aChain.text === 'frame(rot90_front)', 'A3 ...and still shows its frame, which is true of it');
ok(aChain.text !== '고르지 않음', 'A4 ...rather than falling through to 고르지 않음, which would be a new false sentence');
ok(aChain.attest === 'attested' && aPerson.attest === 'confirmed', 'A5 the attribute follows the same one decision');

// CONTROL: the two inputs really do differ in only the one field, so A1/A2 cannot pass for
// some other reason.
ok(chain.confirmed_candidate_id === person.confirmed_candidate_id
  && chain.stored_candidate_id === person.stored_candidate_id,
  'A6 CONTROL: the two rows differ ONLY in confirmed_by_person');

console.log('\n-- the states that must not move -------------------------------------');
const declared = sourceFrameAttestation(
  { stored_candidate_id: 'rot0_front', confirmed_candidate_id: null, confirmed_by_person: false }, spell);
ok(declared.attest === 'declared' && declared.text === 'frame(rot0_front)' && declared.mark === false,
  'B1 a declared map reads exactly as before, with no mark');
const none = sourceFrameAttestation({ stored_candidate_id: null, confirmed_candidate_id: null }, spell);
ok(none.attest === 'none' && none.text === '고르지 않음', 'B2 a map with neither still reads 고르지 않음');
// 🔴 A DECLARED map that ALSO carries a confirmation keeps reading `declared` — that was the
//    behaviour before (`!declared &&`) and this round does not change it.
const both = sourceFrameAttestation(
  { stored_candidate_id: 'rot0_front', confirmed_candidate_id: 'rot90_front', confirmed_by_person: true }, spell);
ok(both.attest === 'declared' && both.mark === false, 'B3 declared still wins over a confirmation');
// ⚠️ ABSENT IS NOT TRUE. An older server that never sends the field must not mint a
//    confirmation nobody made.
const missing = sourceFrameAttestation({ stored_candidate_id: null, confirmed_candidate_id: 'rot90_front' }, spell);
ok(missing.mark === false, 'B4 a missing confirmed_by_person is NOT a confirmation');
const stringy = sourceFrameAttestation(
  { stored_candidate_id: null, confirmed_candidate_id: 'rot90_front', confirmed_by_person: 'true' }, spell);
ok(stringy.mark === false, 'B5 ...and neither is the STRING "true"');

console.log('\n-- the carrier: does the boolean survive the wire and the adapter? ----');
const decoded = decodeReferenceView({
  reference: { cells: [] },
  sources: {
    maps: [
      { map_id: 'm1', declared_frame: 'rot90_front', declared_frame_source: 'confirmed', confirmed_by_person: true },
      { map_id: 'm2', declared_frame: 'rot90_front', declared_frame_source: 'confirmed', confirmed_by_person: false },
      { map_id: 'm3', declared_frame: 'rot90_front', declared_frame_source: 'confirmed' },
    ],
  },
}).sources;
ok(decoded.length === 3, 'C0 three rows decoded — else the rest is vacuous');
ok(decoded[0].confirmedByPerson === true, 'C1 decode carries a person confirmation through');
ok(decoded[1].confirmedByPerson === false, 'C2 ...and carries its absence through as false');
ok(decoded[2].confirmedByPerson === false, 'C3 ...and a MISSING field decodes as false, not undefined');

// 🔴 THE MIDDLE LINK. decode carrying it and the judgement reading it are not enough — the
//    adapter builds the row the screen actually reads, and if the boolean stops there the
//    screen is unchanged while both ends look correct. `adaptPayload` decodes internally, so
//    it takes the RAW payload.
console.log('\n-- the adapter: does the row the screen reads carry it? ---------------');
const RAW = {
  reference: { cells: [] },
  sources: {
    cells: [[0, 0]],
    maps: [
      { map_id: 'm1', declared_frame: 'rot90_front', declared_frame_source: 'confirmed', confirmed_by_person: true },
      { map_id: 'm2', declared_frame: 'rot90_front', declared_frame_source: 'confirmed', confirmed_by_person: false },
    ],
  },
};
const adapted = adaptPayload(RAW).sources;
ok(adapted.length === 2, `D0 two rows adapted — else the rest is vacuous (saw ${adapted.length})`);
ok(adapted[0].confirmed_by_person === true && adapted[1].confirmed_by_person === false,
  'D1 the adapter carries the boolean onto the row the screen reads');
ok(adapted[0].confirmed_candidate_id === 'rot90_front' && adapted[1].confirmed_candidate_id === 'rot90_front',
  'D2 ...and the FRAME is unchanged for both, which is what must not regress');
// End to end: raw wire -> adapter -> judgement, the whole path the screen walks.
ok(sourceFrameAttestation(adapted[0], spell).mark === true
  && sourceFrameAttestation(adapted[1], spell).mark === false,
  'D3 end to end: the same wire that said 확정됨 for both now separates them');

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
