// ABSENT LISTING — 「원천이 «없다»」와 「있는데 «비었다»」를 가르는 «한 곳».
//
// 🔴 상태가 «셋»이고 화면은 «둘»만 알았다:
//      ① 오류   봉투가 오류를 나른다   -> `body_error.errorText` 가 답한다
//      ② 부재   원천 경로가 «없다»     -> 🔴 아무도 안 읽었다. 이 파일이 그 자리다
//      ③ 빔     있는데 «비었다»        -> 「0개」가 «맞는» 답이다
//    ②와 ③이 같은 문장으로 그려지면, 설치가 덜 된 상자가 「아직 아무것도 없음」처럼 보인다.
//    운영자는 그때 «없는 원천»을 찾지 않고 «안 들어온 데이터»를 찾는다.
//
// ⛔ `errorText` 와 «합치지 않는다». 오류와 부재는 «다른 질문»이고, 서버도 다르게 답한다 —
//    부재는 `status: "success"` 다. 실패한 것은 «요청»이 아니기 때문이다
//    (server/listing_absence.py). 한 함수로 접으면 「고장」과 「덜 설치됨」이 다시 같아진다.
// ⛔ 낱말을 «새로 짓지 않는다». `absent` 는 `ledger_trace.COVERAGE_STATES` 의 것이고
//    서버가 이미 그 철자로 보낸다.

//: 서버가 보내는 철자. 여기서 «다시 정의하지 않는다» — 같은 뜻에 두 철자가 생기면
//: 한쪽이 바뀌는 날 화면이 조용히 못 알아본다.
export const LISTING_ABSENT = 'absent';

/**
 * 이 목록의 «원천 경로가 없으면» 그 경로, 아니면 `null`.
 *
 * 🔴 경로를 돌려주는 이유: 운영자가 «고칠 자리»를 그 문자열로 찾는다. 「없음」만 남으면
 *    어디를 봐야 하는지가 사라지고, 그건 「0개」보다 조금 덜 틀린 것뿐이다.
 */
export function absentPath(body) {
  if (!body || typeof body !== 'object') return null;
  if (body.state !== LISTING_ABSENT) return null;
  const path = body.absent_path;
  // 경로가 안 실려 와도 «부재는 부재»다. 빈 문자열을 돌려주면 부르는 쪽이 「아니다」로 읽는다.
  return typeof path === 'string' && path !== '' ? path : LISTING_ABSENT;
}
