// FORM DEMAND — 「이 칸을 «누가» 설명하고 있나」.
//
// 🔴 이 파일이 생긴 이유: **빈 선언에서 소스를 시작할 수가 없었습니다.** 폼은 열립니다 —
//    스켈레톤이 모양을 그리니까요. 그런데 칸이 «원시 텍스트 상자»로 뜹니다. 「무엇을
//    요구하는가」가 «작성 계획»에서만 오고, 빈 선언의 계획에는 그 소스의 행이 «없기»
//    때문입니다. 그래서 사람은 「빈 상자 열둘」을 보고 무엇을 적을지 알 수 없었습니다.
//
// 🔴 그런데 스켈레톤이 «이미» 압니다 — `required` · `label` · `hint`. 새로 만들 것이
//    없고, 계획이 말 못 할 때 스켈레톤이 «떨어져 받는» 것이 전부입니다.
//
// ⚠️ 상태가 «넷»입니다. 셋으로 접으면 각각 다른 사고가 됩니다:
//    계획 «아직 안 옴»    아직 답이 없습니다 — 「빈 선언」이 아닙니다
//    계획 «비었음»        스켈레톤이 말합니다 — 정상 경로입니다 (새 선언이 여기입니다)
//    계획 «있음»          지금까지의 그 화면입니다
//    🔴 스켈레톤 «없음»   진짜 고장입니다. 텍스트 상자를 그릴 «이유»가 아닙니다 —
//                       모양을 모르는데 상자를 그리면 아무 말이나 받는 칸이 됩니다

/** 계획이 아직 안 왔습니다. 「빈 선언」이 아닙니다. */
export const PLAN_UNREAD = '계획 · 모름';
/** 모양 자체를 못 읽었습니다. 상자를 그릴 이유가 아니라 고장입니다. */
export const SHAPE_MISSING = '모양 없음 · 고장';

/**
 * 이 칸을 무엇이 설명하나.
 *
 * @param {{planned?: boolean, planLoaded?: boolean, hasShape?: boolean,
 *          required?: boolean}} facts
 *        `planned`      이 경로에 «계획 행»이 있나
 *        `planLoaded`   계획 응답이 «왔나» (안 왔으면 「빈 계획」이 아닙니다)
 *        `hasShape`     스켈레톤이 이 자리의 모양을 아나
 *        `required`     스켈레톤이 「필수」라고 했나 (모르면 undefined — 「아니오」가 아닙니다)
 * @returns {{source: 'plan'|'skeleton'|'unread'|'broken', text: string, tone: string}}
 */
export function demandState(facts = {}) {
  if (facts.hasShape === false) {
    // 🔴 먼저 봅니다. 모양을 모르는 자리는 계획이 있든 없든 «고장»이고, 계획 유무로
    //    가리면 그 고장이 「그냥 안 물어본 칸」처럼 보입니다.
    return { source: 'broken', text: SHAPE_MISSING, tone: 'danger' };
  }
  if (facts.planned === true) {
    return { source: 'plan', text: '', tone: '' };
  }
  if (facts.planLoaded === false) {
    return { source: 'unread', text: PLAN_UNREAD, tone: 'muted' };
  }
  // 계획이 왔는데 이 자리에 행이 없습니다 — 새 선언의 정상 모습입니다.
  // 그래서 스켈레톤이 «자기가 아는 것»을 말합니다. 「필수인지 모른다」는 「선택」이 아닙니다.
  if (facts.required === true) return { source: 'skeleton', text: '필수', tone: 'warn' };
  if (facts.required === false) return { source: 'skeleton', text: '선택', tone: 'muted' };
  return { source: 'skeleton', text: '요구 · 모름', tone: 'muted' };
}
