// ═══════════════════════════════════════════════════════════════════════════════
// S-46 — 「미검증」이 «왜» 미검증인가. 값에서 읽는다.
//
// 🔴 그 배지는 세 가지를 «한 낱말»로 덮고 있었다. 서버는 셋을 이미 «값으로» 가른다
//    (`config_explorer_service` 의 소스별 상태):
//      record 없음            -> `ran_at: null`, `stale: false`   「이 소스로 아직 실행 안 됨」
//      record 있고 해시 다름   -> `stale: true`                     「선언 변경됨」(이미 그렸다)
//      record 있고 해시 같음   -> `status: 'verified'`              배지 없음
//    앞의 둘은 조작자에게 «다른 다음 행동»이다 — 하나는 「한 번 돌려 보라」이고 하나는
//    「고친 뒤 다시 돌려 보라」다. 한 낱말로 덮으면 그 차이가 사라진다.
//
// ⛔ 문장을 짓지 않는다. 여기서 하는 것은 「어느 상태인가」를 값에서 고르는 것뿐이고,
//    상태가 «셋 밖»이면 오늘 그리던 낱말을 그대로 둔다 — 모르는 것을 아는 척하지 않는다.
// ═══════════════════════════════════════════════════════════════════════════════

const UNVERIFIED = '● 미검증';
const CHANGED = '● 미검증 · 선언 변경됨';
/** 「한 번도 안 돌았다」 — 「돌았는데 안 맞는다」와 다음 행동이 다르다. */
const NEVER_RAN = '● 미검증 · 이 소스로 아직 실행 안 됨';

/**
 * @param {object} verified 소스별 상태 레코드, 서버가 준 그대로
 * @returns {string} 배지 낱말. 「검증됨」이거나 레코드가 없으면 «빈 문자열»
 */
export function verificationNote(verified) {
  if (!verified || typeof verified !== 'object') return '';
  if (verified.status === 'verified') return '';
  // 🔴 `stale` 이 먼저다. 그 쪽은 `ran_at` 을 «들고» 있으므로, 순서가 바뀌면
  //    「선언 변경됨」이 「아직 실행 안 됨」에 먹힌다 — 정확히 반대 지시가 된다.
  if (verified.stale === true) return CHANGED;
  // ⚠️ 「한 번도 안 돌았다」는 «두 값이 함께» 말한다: 돌린 적이 없고(`ran_at` 없음),
  //    낡은 것도 아니다(`stale` 아님). `ran_at` 하나만 보면 옛 서버의 «키 없음»과 섞인다.
  if (verified.ran_at == null && verified.stale === false) return NEVER_RAN;
  return UNVERIFIED;
}
