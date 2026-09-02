// ═══════════════════════════════════════════════════════════════════════════════
// TRUNCATION — 「잘렸나」를 «상한과 돌아온 행»으로만 답하는 한 곳
//
// 🔴 `total` 을 «받지 않습니다». 받는 순간 이 파일을 쓰는 요청이 전수 count 를 다시
//    치러야 하고, 그것이 이 라운드가 없애려는 비용입니다 (카운트가 첫 화면의 66~95%).
//    상한+1 로 요청해서 «한 행 더 왔나»를 보면 `total` 과 «같은 정확도»입니다.
//
// 🔴 판별식은 «정확히 상한만큼» 왔을 때입니다. 상한으로 요청하고 `length >= cap` 으로 보면
//    딱 맞는 정상 응답을 «절단»으로 읽습니다 -- 그러면 온전한 맵이 「불완전」으로 강등되고,
//    화면은 있는 것을 없다고 말합니다. 그래서 상한«+1»로 묻고 `>` 로 봅니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 상한+1 로 요청할 때 쓸 `limit`. 「하나 더 왔나」를 볼 수 있게 «한 행»만 더 청합니다. */
export function fetchLimitFor(cap) {
  return cap + 1;
}

/** 잘렸나. `rows` 는 «돌아온 그대로»여야 합니다 (자르기 «전»). */
export function isTruncated(rows, cap) {
  if (!Number.isFinite(cap) || cap < 0) return false;
  return (Array.isArray(rows) ? rows.length : 0) > cap;
}

/** 상한까지만. 상한+1 로 청했으므로 그 «한 행»은 신호이지 데이터가 아닙니다 --
 *  안 자르면 화면이 상한을 «하나 넘겨» 그립니다. */
export function withinCap(rows, cap) {
  if (!Array.isArray(rows)) return [];
  if (!Number.isFinite(cap) || cap < 0) return rows;
  return rows.length > cap ? rows.slice(0, cap) : rows;
}
