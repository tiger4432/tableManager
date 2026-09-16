// 「이 컨트롤이 왜 꺼졌나」 — 그 답을 «컨트롤 자기 자리»에 두는 한 좌석.
//
// 🔴 왜 이 파일이 생겼나 (C-120 + C-119 발견 ②, 총괄 2026-09-16 「C-120 과 한 라운드로
//    묶으십시오. 같은 병입니다」). 같은 물음(「왜 못 누르나」)에 답하는 자리가 이 저장소에
//    «넷»이었습니다 — `title` · 옆 문구 · «다른 패널» · «없음». 기준 ④ 그대로입니다:
//    정본이 없으면 다섯째 컨트롤이 또 자기 방식을 고르고, «없음»이 제일 고르기 쉽습니다
//    (아무것도 안 적으면 되니까). 그리고 그 「없음」은 오류를 내지 않습니다.
//
// 🔴 정본은 «지어낸 것이 아닙니다». 메인 그리드의 쓰기 버튼 셋이 이미 이렇게 말하고 있었고
//    (C-107 `write_guard.applyWriteGuards`), 이 파일은 그 «몸통을 옮긴 것»입니다.
//    옮긴 이유는 하나뿐입니다 — 그 함수는 「이 표에 쓸 수 있나」를 묻는 자리라서,
//    「행을 골랐나」를 거기 얹으면 한 함수가 «두 물음»에 답하게 됩니다.
//
// ⛔ 사유의 «철자»는 여기서 짓지 않습니다. 자기 조건의 낱말은 부르는 쪽이 압니다.
//    이 파일이 아는 것은 «어디에 두나»뿐입니다.
// ⛔ 문장을 늘리지 않습니다 — 「거절의 «사유»와 «다음 행동»」 한 줄입니다(상설).

/**
 * 컨트롤을 «사유와 함께» 끕니다. 사유가 빈 문자열이면 켭니다.
 *
 * 🔴 끄는 것과 사유를 «한 줄»로 묶은 것이 요점입니다. 둘을 따로 두면 「끄기만 하고 사유는
 *    안 적기」가 언제나 가능하고, 그것이 오늘 고치는 결함의 모양입니다.
 *
 * 🔴 원래 `title` 을 되돌릴 수 있어야 합니다. 마크업이 «이미» 자기 말을 달고 있는 버튼이
 *    있고(`title="Add Row"`), 덮어쓰기만 하면 다시 켜졌을 때 그 버튼이 «말을 잃습니다».
 *    그 기억이 `data-title-was` 이고, 이제 그 자리가 여기 하나입니다.
 *
 * ⚠️ 스텁도 통과해야 합니다 — 부품 하니스의 문서는 `getAttribute` 가 없을 수 있습니다.
 *    없는 철자를 읽고 던지면 그 하니스는 «자기가 재려던 것을 죽입니다»(상설, 계측).
 */
export function setDisabledReason(el, why) {
  if (!el) return;
  const reason = why || '';
  el.disabled = Boolean(reason);
  if (el.dataset && el.dataset.titleWas === undefined) {
    el.dataset.titleWas = (el.getAttribute && el.getAttribute('title')) || '';
  }
  const back = el.dataset ? el.dataset.titleWas : '';
  if (reason) {
    if (el.setAttribute) el.setAttribute('title', reason);
  } else if (back) {
    if (el.setAttribute) el.setAttribute('title', back);
  } else if (el.removeAttribute) {
    el.removeAttribute('title');
  }
}
