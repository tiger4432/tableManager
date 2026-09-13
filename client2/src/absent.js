// ABSENT — 「안 왔다」와 「0이다」를 «다른 글자»로 적는 한 곳.
//
// 🔴 왜 파일이 하나 생겼나: 이 철자는 이미 `chain_queue_panel.countOf` 에 있었고, 이번
//    라운드에 그것을 «여섯 번째» 자리에서 또 쓰게 됐습니다. 여섯 벌을 각자 두면 그중
//    하나가 바뀌는 날 화면 둘이 다른 말을 하고, 그건 오류를 내지 않습니다.
//    (CLAUDE.md 「모든 개발은 근원 템플릿 요소 개발 후 데이터 갈아끼우기」)
//
// 🔴 JS 에서 이 부류가 «조용한» 이유:
//      Number(null) === 0        결측이 0 이 됩니다  — 오류 없음
//      Number('')   === 0        같음
//      Number(undefined) === NaN 그리고 NaN 은 «모든 비교가 거짓»
//      undefined.toLocaleString() 은 «던집니다»
//    그래서 `Number.isFinite(Number(v))` «하나»로는 부족합니다 — null 과 빈 문자열이
//    통과합니다. 그 둘을 «먼저» 걸러야 합니다.
//
// ⛔ 0 으로 대체하지 않습니다. 「없음」은 값이 아니고, 0 은 값입니다.

/** 결측을 적는 «유일한» 글자. 새 문구를 짓지 않습니다. */
export const ABSENT = '—';

/**
 * 「아직 «아무도 안 골랐다»」의 유일한 글자.
 *
 * 🔴 `ABSENT` 와 «다른 글자»입니다. 「—」는 「세었는데 없다」이고 이쪽은 「아직 안 세었다」로,
 *    이 저장소가 세 상태(값 · 0 · 안 물음)를 지키는 자리마다 갈라 온 바로 그 둘입니다.
 * 🔴 문장이 아니라 «값»인 이유: 상설 「화면은 보여 준다, 설명하지 않는다」. 실측(2026-09-13,
 *    R&D 보드): 같은 사실을 여덟 자리가 여덟 «문장»으로 말하고 있었고 — 「…고르면 여기에
 *    나옵니다」·「…찍으면 그립니다」·「…고르십시오」 — 여덟 중 하나가 바뀌면 화면이 여덟 말투로
 *    말하게 됩니다. 다음 행동은 «누를 수 있는 것»이 이미 화면에 있으므로 문장이 필요 없습니다.
 */
export const UNPICKED = '대상 없음';

/**
 * 「이 부품의 주어는 누구인가」를 «값»으로. 마킹 이름 하나이고 문장이 아닙니다.
 *
 * 🔴 세 부품이 각자 「… 이 이 차트의 주어입니다」·「… 이 맵의 주어입니다」·「… 이 목록의
 *    주어입니다」로 적고 있었습니다 — 한 사실, 세 문장. 역할 낱말은 명사 하나로 족하고,
 *    그것이 이 화면의 배지가 이미 쓰는 말투입니다(「읽기 marking:1 · 쓰기 marking:1」).
 */
export function subjectText(marking) {
  return `주어 ${marking || ABSENT}`;
}

/**
 * 이 값이 «세어진 수»인가. `null` · `undefined` · `''` 는 아닙니다 — 셋 다 `Number()` 를
 * 통과하거나(앞의 둘 중 하나는 0 이 되고) NaN 이 됩니다.
 */
export function isCount(v) {
  if (v === null || v === undefined) return false;
  // 🔴 빈 문자열«과 공백뿐인 문자열» 둘 다입니다. Number('   ') 도 0 이고 유한합니다 —
  //    이 하니스가 그 자리를 잡았습니다(첫 판에 '' 만 막고 '   ' 를 놓쳤습니다).
  if (typeof v === 'string' && v.trim() === '') return false;
  return Number.isFinite(Number(v));
}

/** 수면 그 수, 아니면 `—`. 천단위 구분 «없이» — 좁은 칸의 배지용입니다. */
export function countText(v) {
  return isCount(v) ? String(Number(v)) : ABSENT;
}

/** 수면 천단위로 끊어서, 아니면 `—`. 문장 안에 들어가는 수용입니다. */
export function localeCountText(v) {
  return isCount(v) ? Number(v).toLocaleString() : ABSENT;
}
