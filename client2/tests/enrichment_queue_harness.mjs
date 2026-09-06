// ENRICHMENT QUEUE — 「큐를 «어떻게 청하나»」. 철자 하나, 판본 신호 하나.
//
// ═══ 🔴 이 파일이 왜 «새로» 생겼나 (2026-09-06) ═══
// 총괄 판정으로 `src/enrichment.js` 와 그것을 «유일한 주어»로 삼던 하니스들이 나갔습니다.
// 그런데 넷 중 «하나»(`enrichment_queue_partition_harness`)는 주어가 «둘»이었습니다 —
// 죽은 `enrichment.js` 와, **출하되는** `src/enrichment_queue.js`.
//
//   `enrichment_queue.js`  admin.js:13 이 `queueQuery` 를 «진짜로» import 합니다
//                          94줄 · DOM 없음 · 의존 없음 -> 그냥 import 하면 되는 모듈입니다
//
// 🔴 그래서 그 하니스를 통째로 지우면 «살아 있는 코드의 채점»이 같이 사라집니다.
//    판정문의 조건 ④ 가 그 자리입니다 — 「그 파일이 유일하게 아는 것이 있으면 «옮길 것»이지
//    지울 것이 아니다」. 이 파일이 그 «옮긴 것»입니다.
//
// 🔵 그리고 옮기면서 잘라쓰기가 «사라집니다»: 종전에는 이 단언들이 `new Function` 으로
//    조립한 조각 위에서 돌았고, 지금은 «출하되는 모듈 그 자체»를 import 합니다.
//
// ═══ 무엇을 지키나 ═══
//   P6  큐는 «이름»으로 청해진다 — 철자 하나. `?enrichment_queue=<rule>[&..._scope=...]`
//   🔴 그리고 «판본 신호»가 있다: `queue_predicate` 의 «부재»가 「옛 서버」를 뜻한다.
//      옛 서버에는 scope 를 못 물어보고, 물어볼 수 없으면 «넓히지 말고» null 이어야 한다 —
//      조건 없는 요청은 «표 전체»이고, 그건 「모른다」가 아니라 «틀린 답»입니다.
//
// Run: node client2/tests/enrichment_queue_harness.mjs
import * as Q from '../src/enrichment_queue.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  ok   ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}`); console.log(`       got  ${g}`); console.log(`       want ${w}`); }
}

// ── 픽스처. 살아 있는 모양: 타깃 «둘» — 옛 연접 철자가 «원리»가 아니라 «운영»에서
//    틀렸던 이유가 그것입니다. ──────────────────────────────────────────────────────
const PREDICATE = {
  param: 'enrichment_queue',
  value: 'dt job attribution',           // 공백이 있어서 인코딩이 «가정»이 아니라 «채점»됩니다
  scope_param: 'enrichment_queue_scope',
  scopes: ['queue', 'keyed', 'blank_key', 'resolved'],
};
const LEGACY_FILTERS = {
  dt_lot_confirmed: { type: 'blank' },
  dt_slot_confirmed: { type: 'blank' },
};
const RULE = {
  name: 'dt job attribution',
  derived_table: 'dt_job_attribution',
  decision_key: ['equipment', 'event_time'],
  target_fields: ['dt_lot_confirmed', 'dt_slot_confirmed'],
  queue_filters: LEGACY_FILTERS,
  queue_predicate: PREDICATE,
};
/** 옛 서버: `queue_predicate` 가 «아예 없습니다». 그 부재가 판본 신호입니다. */
const OLD_RULE = { ...RULE, queue_predicate: undefined };
/** 더 옛것: `queue_filters` 조차 안 짭니다. */
const ANCIENT_RULE = { ...OLD_RULE, queue_filters: undefined };
/** 타깃도 필터도 없음: 보낼 «조건»이 없고, 조건 없는 요청은 표 «전체»입니다. */
const NO_TARGET_RULE = { ...ANCIENT_RULE, target_fields: [] };
/** predicate 는 내는데 blank_key scope 는 «안 내는» 서버. */
const NARROW_RULE = { ...RULE, queue_predicate: { ...PREDICATE, scopes: ['queue'] } };

// ── ① 계기가 «눈이 멀지» 않았는지 ────────────────────────────────────────────────
//
// 🔴 모듈이 안 열리거나 이름이 바뀌면 아래 전부가 «공허하게» 굴러갑니다.
console.log('\n[0] the module is there and answers');
{
  eq('queueQuery is exported', typeof Q.queueQuery, 'function');
  eq('hasQueuePredicate is exported', typeof Q.hasQueuePredicate, 'function');
  // 🔴 서버가 내는 낱말입니다. 여기 손으로 적는 것이 «계약»이고, 어긋나면 조용히 빈 큐가 됩니다.
  eq('the blank-key scope is spelled as the server publishes it',
    Q.QUEUE_SCOPE_BLANK_KEY, 'blank_key');
}

// ── ② P6 — 요청 그 자체. 철자 하나, 판본 신호 하나 ──────────────────────────────
console.log('\n[P6] the queue is asked for by name, in one spelling');
{
  const NAMED = 'enrichment_queue=dt%20job%20attribution';
  eq('a new server is asked by name',
    Q.queueQuery(RULE), `${NAMED}&enrichment_queue_scope=queue`);
  eq('the blank-key scope rides the same request',
    Q.queueQuery(RULE, 'blank_key'), `${NAMED}&enrichment_queue_scope=blank_key`);
  eq('the rule name is encoded', Q.queueQuery(RULE).includes('dt job'), false);
  eq('a new server is never asked with a filter dict',
    Q.queueQuery(RULE).includes('filters='), false);
  eq('hasQueuePredicate is the version signal',
    [Q.hasQueuePredicate(RULE), Q.hasQueuePredicate(OLD_RULE)], [true, false]);
  eq('an old server falls back to its own queue_filters',
    Q.queueQuery(OLD_RULE), `filters=${encodeURIComponent(JSON.stringify(LEGACY_FILTERS))}`);
  // 🔴 여기가 이 파일의 «판별식»입니다: 못 물어보는 것은 «넓히지» 않고 답을 안 냅니다.
  eq('an old server cannot be asked for a scope', Q.queueQuery(OLD_RULE, 'blank_key'), null);
  eq('an older server still gets the shape composed from its targets',
    Q.queueQuery(ANCIENT_RULE), `filters=${encodeURIComponent(JSON.stringify(LEGACY_FILTERS))}`);
  eq('no targets and no filters is unanswerable, not unconditioned',
    Q.queueQuery(NO_TARGET_RULE), null);
  eq('an unpublished scope is unanswerable, not widened',
    Q.queueQuery(NARROW_RULE, 'blank_key'), null);
  eq('and the plain queue still works on that same server',
    Q.queueQuery(NARROW_RULE), `${NAMED}&enrichment_queue_scope=queue`);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
