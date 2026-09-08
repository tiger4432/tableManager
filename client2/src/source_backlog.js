// ═══════════════════════════════════════════════════════════════════════════════
// C-42 — 「이 소스, 돌 게 있나」를 한 줄로.
//
// 🔴 THE QUESTION IS THE OWNER'S, ASKED IN PRODUCTION: 「파티션 로그만 뜨고 아무 말 없는데
//    돌 게 있는 건가」. The screen could say a source was declared, saved, verified and
//    refused — and could not say whether anything was WAITING. So the operator watched a log
//    scroll and had no way to tell a busy system from an idle one.
//
// 🔴 FOUR NAMES, AND THEY ARE THE CONTRACT. `rows_total` · `rows_past_cursor` ·
//    `rows_before_cursor` · `caught_up`. The server half (S-69) emits these; this file spells
//    them once and the screen prints the name it was given, so a rename shows up as a blank
//    column rather than as a number quietly attached to the wrong label.
//
// 🔴 THREE STATES, AND THE THIRD IS WHY THIS FILE EXISTS. A key that is ABSENT means nobody
//    has counted yet; a key that is `0` means somebody counted and the answer was none. Those
//    are opposite instructions — 「아직 모른다」 versus 「돌 게 없다」 — and drawing the first
//    as 0 tells an operator the queue is empty when the truth is that nothing has looked.
//
// ⛔ 문장을 짓지 않습니다. `rows_before_cursor` 가 0 보다 크면 값 «옆»에 낱말 하나(「커서 앞」)
//    가 붙습니다 — 그 수가 「밀린 것」이 아니라 「커서가 지나가 버려 못 보는 것」이라는 사실은
//    수만으로는 안 보이고, 그 하나를 설명으로 늘리면 화면이 다시 산문이 됩니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 커서가 이미 지나가서 이 실행이 «못 보는» 행이라는 표지. 사유 한 낱말, 문장 아님. */
const BEHIND_MARK = '커서 앞';
/** `caught_up` 의 두 낱말. 조작자의 물음이 「돌 게 있나」라 「남음」이 그 답의 낱말입니다. */
const CAUGHT_UP = '따라잡음';
const HAS_WORK = '남음';

/**
 * 계약의 네 이름 — 순서까지 이것이 정본입니다.
 *
 * 🔴 화면이 이름을 «번역하지 않습니다». 라벨은 서버가 보낸 키 그대로이고, 한국어는 값 쪽의
 *    낱말(위 셋)에만 씁니다 — 이름을 옮기면 서버가 키를 바꾸는 날 화면이 «옛 이름으로»
 *    옳아 보입니다.
 */
export const BACKLOG_FIELDS = Object.freeze([
  'rows_total', 'rows_past_cursor', 'rows_before_cursor', 'caught_up',
]);

/**
 * @param {object} status 소스별 현황 레코드, 서버가 준 그대로
 * @returns {{name: string, text: string, note: string}[]} 칸 넷. 안 센 칸은 `text` 가 «빈 문자열»
 */
export function backlogCells(status) {
  const src = status && typeof status === 'object' ? status : {};
  return BACKLOG_FIELDS.map((name) => {
    const raw = Object.prototype.hasOwnProperty.call(src, name) ? src[name] : undefined;
    if (raw === undefined || raw === null) return { name, text: '', note: '' };
    if (name === 'caught_up') {
      // ⚠️ 참/거짓 «만» 답입니다. 다른 것이 오면 「안 셈」으로 둡니다 — 아무 값이나 참으로
      //    접으면 「따라잡음」이 서버가 한 적 없는 말이 됩니다.
      if (raw === true) return { name, text: CAUGHT_UP, note: '' };
      if (raw === false) return { name, text: HAS_WORK, note: '' };
      return { name, text: '', note: '' };
    }
    const count = Number(raw);
    if (!Number.isFinite(count)) return { name, text: '', note: '' };
    // 🔴 「커서 앞」은 «0 보다 클 때만». 0 에도 붙이면 그 낱말이 「이 칸의 제목」이 되고,
    //    제목은 이미 이름이 하고 있습니다.
    const note = name === 'rows_before_cursor' && count > 0 ? BEHIND_MARK : '';
    return { name, text: String(count), note };
  });
}

/**
 * 그릴 것이 하나라도 있나 — 없으면 화면은 «그 줄 자체를» 안 그립니다.
 *
 * 🔴 빈 줄을 그리면 「안 셌다」가 「셌는데 빈칸 넷」처럼 보입니다. 서버 절반(S-69)이 오기
 *    전의 오늘 화면이 «바이트 동일»해야 하는 이유도 이것입니다.
 */
export function hasBacklog(status) {
  return backlogCells(status).some((cell) => cell.text !== '');
}
