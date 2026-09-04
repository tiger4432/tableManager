// ═══════════════════════════════════════════════════════════════════════════════
// RESCOPE HANDOFF — 그리드가 «고른 범위»를 어드민의 소급 적용 블록으로 넘기는 한 자리.
//
// 🔴 URL 질의에 «안 싣습니다» (총괄 지시). 범위 값은 길고, 주소창은 데이터를 두는 자리가
//    아닙니다 -- 브라우저 이력·서버 로그·어깨 너머로 새어 나갑니다.
//
// 🔴 «한 번 쓰고 한 번 먹습니다». 남겨 두면 다음에 어드민을 열었을 때 «지금 고른 적 없는»
//    범위가 채워져 있고, 운영자는 그것이 자기가 고른 것이라고 읽습니다. 그게 이 화면이
//    반복해서 막아 온 부류(「없는 것을 있는 것처럼」)의 쓰기 판입니다.
//
// 🔴 sessionStorage 가 아니라 localStorage 입니다. 오늘 링크는 같은 탭이지만 새 탭으로
//    여는 순간 sessionStorage 는 «따라가지 않고», 그때 넘김은 오류 없이 조용히 사라집니다.
//    (새 탭은 자기 세션입니다. 이 문장을 반대편에서 적어 둔 `trace_launch.js` 는
//     2026-09-04 은퇴로 사라졌습니다 — 이유는 그대로고 참조할 사본만 없습니다.)
// ═══════════════════════════════════════════════════════════════════════════════

const KEY = 'assy.rescope.handoff.v1';

/** 그리드가 씁니다. 저장소가 막혀 있으면 «조용히 실패하지 않고» false 를 돌려줍니다. */
export function putRescopeHandoff(payload, store) {
  const target = store || (typeof localStorage !== 'undefined' ? localStorage : null);
  if (!target || !payload || !payload.op) return false;
  try {
    target.setItem(KEY, JSON.stringify({ ...payload, at: Date.now() }));
    return true;
  } catch (err) {
    return false;
  }
}

/**
 * 어드민이 «한 번» 읽고 «지웁니다». 두 번째 호출은 null 입니다 -- 그게 「지금 넘어온 것」과
 * 「예전에 넘어와 남아 있던 것」을 가르는 유일한 방법입니다.
 */
export function takeRescopeHandoff(store) {
  const target = store || (typeof localStorage !== 'undefined' ? localStorage : null);
  if (!target) return null;
  let raw = null;
  try {
    raw = target.getItem(KEY);
    target.removeItem(KEY);
  } catch (err) {
    return null;
  }
  if (!raw) return null;
  try {
    const got = JSON.parse(raw);
    return got && got.op ? got : null;
  } catch (err) {
    // 깨진 것을 «빈 것»으로 읽지 않습니다 -- 이미 지웠으므로 다음 번엔 깨끗합니다.
    return null;
  }
}
