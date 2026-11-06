// THE REFUSAL SEAT - a refused answer's sentence, the server's own (moved out of api.js so a page without the grid,
// the Tables page, reads it through the same function; api.js imports it back).

/**
 * 거절의 «사유» — 서버가 문장을 보냈으면 그것이고, 아니면 상태를 이름 댑니다.
 *
 * 🔴 자리가 «하나»입니다: 쓰기(`addRows`)와 읽기(`fetchData` · 행 이동 `navigatorStep3`)가 같은 답을 내야 하고, 각자
 *    적으면 한쪽이 조용히 달라집니다. 그리고 이 함수는 «던지지 않습니다» — 거절은 예외가
 *    아니라 «답»이고, 던지면 그 문장이 콘솔로만 갑니다.
 * ⚠️ 답은 «문장»일 때만입니다 — `detail` 이 문자열이거나, 멈춘 읽기(503 grid_read_stopped, adae5832a)처럼
 *    `detail.message` 가 문자열일 때. FastAPI 의 기본 422 는 `detail` 이 목록이라, 그대로 그리면
 *    화면이 「[object Object]」를 말합니다.
 *
 * @param {Response} res 거절한 응답
 * @param {string} whenSilent 서버가 문장을 «안 보냈을» 때 화면이 댈 이름
 */
export async function refusalText(res, whenSilent) {
  const said = await refusalSaid(res);
  return said || `${whenSilent} (HTTP ${res.status})`;
}

/** 거절에 서버가 실은 문장 — 없으면 ''. 미룬 수의 실패(fillMatchCount)도 이것을 읽습니다. */
export async function refusalSaid(res) {
  const body = await res.json().catch(() => null);
  const detail = body ? body.detail : null;
  const said = typeof detail === 'string' ? detail
    : (detail && typeof detail.message === 'string' ? detail.message : '');
  return said;
}
