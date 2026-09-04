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
