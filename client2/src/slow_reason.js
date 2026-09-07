// S-7 ① — 「왜 느린가」의 독자 «하나».
//
// 🔴 서버가 «문장까지» 만들어 보냅니다 — `value_suggest.py` 가 `slow_reason` 에
//    「응답이 Nms 걸렸습니다 (예산 Mms) — <다음 행동>」 을 실어, 그 파일 자기 주석이
//    「`slow_reason` is what makes it actionable」이라 적어 뒀습니다. 읽는 자리가 «0» 이었습니다.
//    등급 2 — 화면이 «거짓»을 말하는 게 아니라, 문장이 화면 «앞»에 놓여 있는데 안 듭니다.
//
// ⛔ 문구를 «짓지» 않습니다. 서버 문장을 «그대로** 냅니다 — 화면이 다시 쓰면 그것이 둘째 저자이고,
//    서버가 임계값을 바꾸는 날 두 문장이 갈라집니다.
// ⛔ `elapsed_ms` 를 보고 화면이 «느리다고 판정»하지 않습니다. 그 경계는 서버의 «선언»(`warn_ms`)에
//    있고, 화면이 지어내면 그 순간 임계가 둘이 됩니다.
//
// 🔴 세 상태를 «합치지 않습니다** (판정 82·84):
//      키 «없음»   안 쟀다        — 이 라우트는 아직 시간을 안 냅니다
//      `null`      쟀다, 안 느림  — 재고서 「느리지 않다」고 «말한» 것입니다
//      문장        쟀다, 느림     — 그리는 것은 이것 «하나»입니다
//    오늘 앞의 둘은 «둘 다 침묵»입니다. 그래도 합치지 않는 이유는, 합치는 순간 서버가
//    「안 잼」과 「안 느림」을 가르는 날 화면이 그 구별을 «영영 못 받기» 때문입니다.

/** 「이 응답이 느렸다고 서버가 «말했나»」 — 그리고 그 말이 무엇이었나. */
export function slowReasonNote(container) {
  if (!container || typeof container !== 'object') {
    return { state: 'unmeasured', text: '' };
  }
  // 🔴 키의 «있음»으로 가릅니다. `undefined` 는 「이 라우트가 그 말을 안 한다」이고,
  //    실린 `null` 은 「재 봤고 안 느렸다」입니다 — 두 문장이 다릅니다.
  if (!('slow_reason' in container)) return { state: 'unmeasured', text: '' };
  const said = container.slow_reason;
  if (said === null || said === undefined) return { state: 'not_slow', text: '' };
  // ⚠️ 실렸는데 «문장이 아닌» 것은 「안 느림」이 아닙니다 — 잰 것은 맞고 값을 못 읽은 것입니다.
  //    「안 느림」으로 접으면 화면이 «서버가 안 한 말»을 하게 됩니다. 그리지 않되, 이름은 따로 둡니다.
  if (typeof said !== 'string' || said.trim() === '') {
    return { state: 'unreadable', text: '' };
  }
  // 🔴 «그대로**. 자르지도, 다듬지도, 접두어를 붙이지도 않습니다.
  return { state: 'slow', text: said };
}
