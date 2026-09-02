// ═══════════════════════════════════════════════════════════════════════════════
// MATCH COUNT — 「몇 건인가」를 «세 상태»로 답하는 한 곳
//
// 🔴 개수는 «늦게 옵니다» (소유자 승인 2026-09-02). 행을 먼저 그리고, 개수는 두 번째 요청이
//    오면 채웁니다. 그래서 화면은 이제 «세 가지»를 구별해야 합니다:
//       숫자   `Matches: 12`     센 결과
//       null   `Matches: …`      «아직 모릅니다» -- 세는 중
//       0      `Matches: 0`      «진짜 없습니다»
//    null 을 0 으로 그리면 「일치 없음」이라는 «거짓»이고, 빈칸으로 두면 고장으로 읽힙니다.
//
// 🔴 이 파일이 생긴 이유: 「Matches:」를 쓰는 자리가 «다섯»이었습니다 --
//       api.js:256(캐시) · api.js:313 · timeline.js:1051(캐시) · timeline.js:1112 · main.js:1119
//    하나만 고치면 나머지 넷이 «그 경로에서만» 「Matches: null」을 찍습니다. 그건 0 도 빈칸도
//    아니면서 「세는 중」도 아닌 세 번째 거짓말입니다. 그래서 «부류»로 옮깁니다.
//
// NO DOM GLOBALS beyond the element handed in. 맨 node 로 채점됩니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 「아직 모른다」의 표기. 0 과도 빈칸과도 달라야 합니다. */
export const COUNTING = '…';

/** 센 수인가. `null`·`undefined`·NaN 은 «아닙니다». */
export function isCounted(total) {
  return typeof total === 'number' && Number.isFinite(total);
}

/** 화면에 적을 한 줄. */
export function matchCountText(total) {
  return `Matches: ${isCounted(total) ? total : COUNTING}`;
}

/** 다섯 자리가 부르는 «한 함수». 표기와 표지를 같이 답니다. */
export function setMatchCount(el, total) {
  if (!el) return;
  el.textContent = matchCountText(total);
  // 글자만으로도 구별되지만 표지도 답니다 -- 세는 중인 수는 «아직 쓸 수 없는» 수입니다.
  if (el.classList) el.classList.toggle('is-counting', !isCounted(total));
}

/** 페이지 컨트롤이 무엇을 보여야 하는가. DOM 을 모르므로 «수»로만 답합니다.
 *
 * 🔴 `Math.ceil(null / limit) || 1` 은 «1» 입니다. 그러면 아직 안 센 표가 「1쪽뿐」이 되고
 *    `currentPage >= totalPages` 가 참이 되어 «다음이 꺼집니다» -- 세는 중에는 다음 쪽으로
 *    갈 수 없게 됩니다. 「모른다」와 「1쪽뿐」은 «다른 상태»입니다.
 */
export function pagingView(total, currentSkip, pageLimit) {
  const currentPage = Math.floor(currentSkip / pageLimit) + 1;
  const counted = isCounted(total);
  const totalPages = counted ? (Math.ceil(total / pageLimit) || 1) : null;
  return {
    currentPage,
    totalPages,
    totalPagesText: counted ? String(totalPages) : COUNTING,
    prevDisabled: currentPage === 1,
    // 모르는 동안은 «켜 둡니다». 수가 오면 그때 판정합니다.
    nextDisabled: counted ? currentPage >= totalPages : false,
  };
}
