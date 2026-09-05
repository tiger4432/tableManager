// GAP CATALOGUE — 「있을 수 없는 것」과 「없는 것」이 갈리는지.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). Pure module.
//
// 🔴 THE THREE THIS FILE EXISTS FOR:
//   ① 🔴 공허함. 「선언상 애초에 생길 수 없다」와 「생길 수 있는데 없다」가 같은 줄로 보이면
//      운영자가 «선언이 금지한 데이터»를 채우러 갑니다. 부재 부류 중 비용이 가장 구체적인
//      자리이고, 그래서 총계에서도 갈립니다 -- 「격차 20」과 「격차 14 · 공허 6」은 다른 문장.
//   ② 없는 «쪽». 주어 쪽이 빈 것과 목적어 쪽이 빈 것은 «반대 행동»이다.
//   ③ 「거절」과 「못 물어봄」은 다르다. 거절은 작성자의 물음(이름을 어디 적나)이고
//      못 물어봄은 아직 답이 없다는 뜻이다. 합치면 둘 다 못 고친다.
//
// Run: node client2/tests/gap_catalogue_harness.mjs
import { gapCatalogueView, GAPS_UNREAD, SIDE_LABELS } from '../src/gap_catalogue.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}

// Shapes copied from `ledger/gaps.questions`' own appends.
const PAIR = { form: 'pair', type: 'wafer@1', present: ['inspected@1'],
               absent: ['processed_with@1'], name: '검사만 된 웨이퍼',
               meaning: '검사는 있고 공정 기록이 없습니다', vacuous: false };
const SUBJ = { form: 'subject_side', type: 'die@1', present: [],
               absent: ['bonded_from@1'], name: '계보 없는 다이',
               action: '본딩 기록을 적재하십시오', vacuous: false };
const OBJ_VACUOUS = { form: 'object_side', type: null, present: [], absent: ['register@1'],
                      name: '해당 없음',
                      action: '없음 — 목적이 노드가 아니라 가리킬 것이 없습니다',
                      vacuous: true };
const NAMES = { mode: 'names', count: 3, gaps: [PAIR, SUBJ, OBJ_VACUOUS] };

// ═══ ① 공허함이 갈린다 ═════════════════════════════════════════════════════════════
console.log('\n[1] declared-impossible is not the same as absent');
{
  const v = gapCatalogueView(NAMES);
  eq('a real gap is not vacuous', v.rows[0].vacuous, false);
  eq('one the declaration forbids says so', v.rows[2].vacuous, true);
  // 🔴 ① THE COUNT. Mixing them sends the operator looking for data that cannot exist.
  eq('the total separates them', v.text, '격차 2 · 공허 1');
  eq('with nothing vacuous the line stays one number',
    gapCatalogueView({ gaps: [PAIR, SUBJ] }).text, '격차 2');
  // A missing flag is not a claim that it is possible; it is just not marked vacuous,
  // which is what the detector means by leaving it off.
  const { vacuous, ...noFlag } = OBJ_VACUOUS;
  eq('an absent flag is read as not-vacuous, never as vacuous',
    gapCatalogueView({ gaps: [noFlag] }).rows[0].vacuous, false);
  eq('a non-boolean flag is not coerced',
    gapCatalogueView({ gaps: [{ ...PAIR, vacuous: 'true' }] }).rows[0].vacuous, false);
}

// ═══ ② 없는 «쪽» — 반대 행동이라 반대 낱말 ═══════════════════════════════════════════
console.log('\n[2] which side is empty, in three different words');
{
  const v = gapCatalogueView(NAMES);
  eq('a mismatched pair says so', v.rows[0].side, SIDE_LABELS.pair);
  eq('an empty subject side says so', v.rows[1].side, SIDE_LABELS.subject_side);
  eq('an empty object side says so', v.rows[2].side, SIDE_LABELS.object_side);
  ok('the three are three different words',
    new Set([SIDE_LABELS.pair, SIDE_LABELS.subject_side,
             SIDE_LABELS.object_side]).size === 3);
  // 🔴 A form this client has no word for is SHOWN, not dropped. Dropping it makes the
  //    screen shorter the day the detector gains a kind, and nothing says so.
  eq('an unknown form is passed through rather than swallowed',
    gapCatalogueView({ gaps: [{ ...PAIR, form: 'new_kind' }] }).rows[0].side, 'new_kind');
  eq('...and the row is still counted', gapCatalogueView(
    { gaps: [{ ...PAIR, form: 'new_kind' }] }).rows.length, 1);
}

// ═══ ③ 이름 + 다음 행동, 그리고 술어 목록은 «안» 그린다 ═════════════════════════════
console.log('\n[3] the name and what to do, and not the fourth fact');
{
  const v = gapCatalogueView(NAMES);
  eq('the name the spec gave it', v.rows[1].name, '계보 없는 다이');
  eq('a one-sided gap carries its action', v.rows[1].action, '본딩 기록을 적재하십시오');
  eq('a pair carries its meaning in the same slot', v.rows[0].action,
    '검사는 있고 공정 기록이 없습니다');
  // ⛔ The fourth fact -- which predicates are present and which absent, by name -- was
  //    ruled off-screen. If it ever appears here, this assertion is what says so.
  ok('the predicate lists are not carried',
    v.rows.every((row) => !('present' in row) && !('absent' in row)));
}

// ═══ ④ 거절 · 못 물어봄 · 빈 목록 — 셋 ═══════════════════════════════════════════════
console.log('\n[4] refused, unasked, and genuinely empty are three');
{
  eq('nothing asked yet', gapCatalogueView(null).text, GAPS_UNREAD);
  eq('...and it is not a refusal', gapCatalogueView(null).refused, false);

  // 🔴 The 503 the route raises when the declaration and the spec disagree. It is the
  //    AUTHOR's question and its sentence already names form, type and predicate.
  const refused = gapCatalogueView(NAMES, {
    refusal: { reason: 'gap_table_mismatch',
               message: 'the declaration asks questions the spec has not named: '
                        + 'subject side of observed@1 on die@1' } });
  eq('a refusal says so', refused.refused, true);
  ok('...keeps the server\'s sentence verbatim',
    refused.text.includes('subject side of observed@1 on die@1'));
  eq('...keeps the machine reason too', refused.reason, 'gap_table_mismatch');
  eq('...and draws no rows, because the list is a different question', refused.rows, []);
  ok('a refusal is not read as 「no gaps」', refused.read === false);

  // A genuinely empty catalogue IS an answer, and it is not 「모름」.
  const none = gapCatalogueView({ mode: 'names', count: 0, gaps: [] });
  eq('an empty catalogue was read', none.read, true);
  eq('...and says zero rather than 「모름」', none.text, '격차 0');
  ok('the three are three different texts',
    new Set([gapCatalogueView(null).text, refused.text, none.text]).size === 3);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
