// ═══════════════════════════════════════════════════════════════════════════════
// C-43 ② — 맵 셀을 «어떻게 물어보나». 한 자리.
//
// 🔴 THE MAIN LOAD WAS PAYING FOR A COUNT NOBODY DREW. It asked without `defer_total`, so the
//    server counted the same filter over the same table a second time, and the person opening
//    the map waited for both scans. The count was there for one reason — to notice truncation
//    — and the overlay loader already had a way to notice it that costs nothing: ask for ONE
//    MORE than the cap and see whether that one arrives.
//
// 🔴 AND THE CAP HAD TWO AUTHORS. The main load spelled `2000` inline; the overlay kept
//    `OVERLAY_CELL_LIMIT = 2000` with a comment saying 「메인 로드와 같은 상한」. A comment is
//    not a mechanism: the two would drift the first time either moved. They pass through this
//    module now.
//
// ⛔ 판단 로직은 여기 없습니다. 이 파일은 「무엇을 묻나」와 「잘렸나」뿐이고, 잘린 뒤에 무엇을
//    하느냐(강등·거절)는 부르는 쪽의 것입니다 — 두 부르는 쪽이 «다르게» 답하기 때문입니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 한 번에 읽는 셀 행의 상한. 메인 로드와 오버레이 로드가 «같은 수»를 씁니다. */
export const CELL_LIMIT = 2000;

/**
 * 셀 조회의 쿼리 문자열 — `?` 뒤 전부.
 *
 * 🔴 `defer_total=true` 가 이 함수의 요점입니다. 없으면 서버가 같은 필터로 COUNT 를 한 번 더
 *    돌리고, 그 시간은 맵을 여는 사람이 «두 번» 기다리는 시간입니다.
 * 🔴 `limit` 이 상한보다 «하나 더»인 것도 요점입니다 — 그 하나가 절단의 «증거»이고, 그래서
 *    `total` 이 null 이어도 판정이 그대로입니다.
 *
 * @param {object} filterModel AG-Grid 필터 모델, 서버가 받는 그대로
 */
export function cellQuery(filterModel) {
  return `limit=${CELL_LIMIT + 1}&defer_total=true`
    + `&filters=${encodeURIComponent(JSON.stringify(filterModel))}`;
}

/**
 * 잘렸나 — «행 수»로.
 *
 * ⚠️ 상한과 «같은» 수는 잘린 것이 아닙니다. 정확히 상한만큼 있는 표는 온전히 온 것이고,
 *    그것을 절단으로 읽으면 멀쩡한 맵이 「모름」으로 강등됩니다.
 */
export function cellsTruncated(rows) {
  return (Array.isArray(rows) ? rows.length : 0) > CELL_LIMIT;
}

/** 그릴 행 — 상한까지. 하나 더 달라고 한 그 하나는 «판정용»이지 그릴 것이 아닙니다. */
export function cellsToDraw(rows) {
  return (Array.isArray(rows) ? rows : []).slice(0, CELL_LIMIT);
}
