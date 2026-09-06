// BODY ERROR — 「이 본문이 «오류를 나르나»」에 답하는 한 곳.
//
// 🔴 왜 «성질»을 묻나. F-10 수리는 「`error` 라는 «칸»이 있나」를 물었다 — 그건 «기제»다.
//    그 검사를 옆 라우트에 «그대로 복사»하면 컴파일되고 돌고 «아무것도 안 잡는다».
//    같은 사실을 «다른 봉투»로 나르기 때문이고, 그 침묵이 이 파일이 있는 이유다.
//
// 잰 봉투는 «둘»이다 (2026-09-07):
//   봉투 A  {status: "success"|"error", message, data?}    main.py admin 계열
//           🔵 «성공에도» status 가 있다 -> 판별자는 칸 이름이 아니라 그 «값»이다
//   봉투 B  {…, error: null|"ClassName: msg"}              ledger_admin 계열
//           🔴 `error` 키는 «성공에도 있다» (값이 null) -> 판별자는 「참인가」이지
//              「있는가」가 «아니다». `'error' in body` 로 물으면 «성한 응답이 전부» 오류가 된다
//
// ⛔ 서버 응답을 개명하지 않는다. 각 봉투는 «자기 안에서» 일관하고, 통일하면 봉투 A 에
//    같은 말을 하는 칸이 «둘» 생긴다 — 그게 기준 ④ 그 자체다 (총괄 판정 22, 2026-09-07).
// ⛔ 「없음」은 오류가 «아니다». `absent_listing` 의 답은 status 가 success 이고, 그건
//    「원천이 없다」는 «사실»이지 실패가 아니다 (server/listing_absence.py).

//: 봉투 A 가 실패라고 «말은 했는데» 사유 칸이 빈 경우. 여기서 null 을 돌려주면
//: 「오류 없음」을 «단언»하게 된다 — 아는 것(실패했다)과 모르는 것(왜)을 갈라 적는다.
export const UNSAID = '사유 미상';

/**
 * 본문이 오류를 나르면 «그 사유 문장», 아니면 `null`.
 *
 * 🔴 `data` 를 읽기 «전»에 부른다. 빈 목록을 쥐여 주는 것이 이 병의 기제다 —
 *    화면은 오류를 그리지 않고 「선언된 것이 없다」를 그린다.
 */
export function errorText(body) {
  if (!body || typeof body !== 'object') return null;
  // 봉투 A. `status` 가 없는 본문은 여기 안 걸린다 — 봉투 B 가 그렇다.
  if (body.status === 'error') {
    const said = String(body.message == null ? '' : body.message).trim();
    return said || UNSAID;
  }
  // 봉투 B. 「있는가」가 아니라 「참인가」다 (위 주석).
  if (body.error) return String(body.error);
  return null;
}
