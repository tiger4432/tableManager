// REDO COST — 「이 저장이 무엇을 다시 돌리나」를 «한 줄»로 읽는 한 곳 (C-96 / S-143).
//
// 🔴 왜 자기 모듈인가. 이 봉투(`{op, params, sources, count}`)의 «카드» 독자는 이미
//    `retroactive_view.js` 에 있습니다. 그런데 그 파일의 헬퍼들은 «꼬리표 붙은 칸»을 냅니다 —
//    `{src:'server'|'value'|'chrome'|'count', text}` — 그 화면이 「이 글자를 누가 썼나」를
//    픽셀로 구별하기 때문입니다. 초안 편집기는 그 규율을 «안 씁니다»(옆의 `막는 것 없음` 도
//    평문입니다). 거기에 맞추려고 꼬리표를 평문으로 «납작하게» 만들면, 그 파일이 지키는 것을
//    그 파일 안에서 깨는 것이 됩니다. 그래서 판정 하나에 모듈 하나 — 이 저장소가 `absent.js`
//    ·`truncation.js`·`match_count.js` 로 이미 쓰는 모양입니다.
//
// 🔴 재료는 «이미» 화면 손에 있었습니다. 서버가 `draft["redo"]` 를 초안 레코드에 싣고
//    (`config_explorer_service.py`), 그 레코드가 화면의 `state.draft` 입니다. 없던 것은
//    «읽는 쪽»뿐이고, 그것이 「착지는 배선이 아니다」의 실물입니다 — S-143 은 수를 착지시켰고
//    아무도 그것을 읽을 수 없었습니다.
//
// ⛔ 문장을 짓지 않습니다. 값 · 서버의 이름 · 서버의 낱말뿐입니다.

import { ABSENCE_WORDS } from './count_with_absence.js';

/** 서버가 쓴 낱말이면 그 글자, 아니면 null. 빈 문자열은 «안 쓴 것»입니다. */
function word(value) {
  if (value === null || value === undefined) return null;
  const s = String(value).trim();
  return s === '' ? null : s;
}

/**
 * @param {object|null|undefined} redo  초안 레코드의 `redo` 칸 그대로
 * @returns {string|null} 버튼 옆에 설 한 줄, 또는 «그릴 것 없음»
 *
 * 🔴 세 상태이고, 첫째가 이 함수가 있는 이유입니다:
 *   ① `null` — 아무도 «안 물었다»(요청에 세션이 없었다). `null` 을 돌려주고 화면은 비용에
 *      대해 «아무 말도 하지 않습니다». 「다시 돌 것 없음」으로 그리면 안 물어본 것을 답으로
 *      만들고, 그건 이 저장소가 매 라운드 가르는 바로 그 두 상태입니다.
 *   ② 수 — 셌다. 서버가 붙인 이름(`affected_label`)과 그 수.
 *   ③ `absence` 낱말 — 「셀 수 있지만 이 자리에서 안 셌다」(`not_counted_here`) 또는
 *      「정말 없다」(`truly_none`). 토큰을 «화면 낱말»로 옮기는 자리는
 *      `count_with_absence.js` 의 `ABSENCE_WORDS` «하나»이고, 이 파일은 그것을 «부릅니다».
 *      ⚠️ 여기엔 원래 「서버의 낱말 그대로 싣는다 — 번역하면 그 구별이 제 손에 들어온다」고
 *         적혀 있었습니다. «위험은 옳았고 처방이 틀렸습니다» — 그대로 실으면 운영자가
 *         `not_counted_here` 라는 «영어 토큰»을 읽습니다. 구별을 지키는 길은 «안 옮기는 것»이
 *         아니라 «옮기는 자리를 하나로» 두는 것이고, 그 자리는 «이미» 있었습니다 —
 *         같은 화면(`ontology_explorer_view.js`)이 그 표를 이미 import 하고 있었습니다.
 *         모르는 토큰은 그 표가 «그대로» 내보냅니다 — 새 낱말이 조용히 사라지지 않습니다.
 *
 * ⚠️ `count_kind` 는 «정확하지 않을 때만» 실립니다. 표본이나 상한을 정확한 수처럼 보이게 두는
 *    것이 이 저장소가 계속 막아 온 거짓이고(`retroactive_view.js` 가 같은 낱말을 알약으로
 *    그립니다), `exact` 를 적는 것은 아무것도 안 더하는 주저리입니다.
 */
export function redoCostText(redo) {
  if (!redo || typeof redo !== 'object') return null;
  const parts = [];
  // ⚠️ 배열이 «아니면» 세지 않습니다 — 「소스 0」은 「소스가 없다」이고, 「안 실렸다」가 아닙니다.
  if (Array.isArray(redo.sources)) parts.push(`소스 ${redo.sources.length}`);
  const count = redo.count && typeof redo.count === 'object' ? redo.count : {};
  const label = word(count.affected_label);
  const affected = Number.isInteger(count.affected) ? count.affected : null;
  if (label && affected !== null) {
    parts.push(`${label} ${affected}`);
    const kind = word(count.count_kind);
    if (kind && kind !== 'exact') parts.push(kind);
  } else {
    const absence = word(count.absence);
    if (absence) {
      parts.push(Object.prototype.hasOwnProperty.call(ABSENCE_WORDS, absence)
        ? ABSENCE_WORDS[absence] : absence);
    }
  }
  return parts.length ? parts.join(' · ') : null;
}
