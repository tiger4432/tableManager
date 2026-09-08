// ═══════════════════════════════════════════════════════════════════════════════
// C-42 — 「이 소스, 돌 게 있나」를 한 줄로.
//
// 🔴 THE QUESTION IS THE OWNER'S, ASKED IN PRODUCTION: 「파티션 로그만 뜨고 아무 말 없는데
//    돌 게 있는 건가」. The screen could say a source was declared, saved, verified and
//    refused — and could not say whether anything was WAITING.
//
// 🔴 THREE NAMES, AND THEY REPLACED THE CURSOR'S FOUR (2026-09-09, S-69 → S-76). The earlier
//    contract was `rows_past_cursor` · `rows_before_cursor` · `caught_up`, and every one of
//    those words belonged to a cursor world that the S-76 round retired. Renaming them would
//    have kept the old question alive under new spelling; they are GONE and the place now
//    holds what the source actually has:
//        rows_total      the table's rows
//        rows_indexed    how many of them the ledger has taken
//        rows_remaining  what is left
//
// 🔴 `rows_remaining` IS READ, NEVER COMPUTED. It is N − M today and that is exactly why the
//    temptation is there — and the day the server's definition stops being plain subtraction
//    (an index that lags, rows a view excludes, a filtered scope) a client that did the
//    arithmetic would go on drawing a confident number that disagrees with the ledger, with
//    no error anywhere. A second author for one fact is the failure this file exists inside.
//
// 🔴 THREE STATES, AND THE THIRD IS WHY THIS FILE EXISTS. A key that is ABSENT means nobody
//    has counted yet; a key that is `0` means somebody counted and the answer was none. Those
//    are opposite instructions — 「아직 모른다」 versus 「돌 게 없다」 — and drawing the first
//    as 0 tells an operator the queue is empty when the truth is that nothing has looked.
//
// ⛔ 문구를 짓지 않습니다. 세 수가 나란히 있으면 「돌 게 있나」는 «남은 수»가 답합니다.
//    설명이 필요하다고 느껴지면 그건 이름이 틀린 것이지 문장이 모자란 것이 아닙니다.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 계약의 세 이름 — 순서까지 이것이 정본입니다.
 *
 * 🔴 화면이 이름을 «번역하지 않습니다». 라벨은 서버가 보낼 키 그대로이고, 이름을 옮기면
 *    서버가 키를 바꾸는 날 화면이 «옛 이름으로» 옳아 보입니다.
 * ⚠️ 오늘 서버는 이 셋을 «아직 안 보냅니다»(S-58 과 합쳐 구현자 ②·⑦ 사이). 그래서 이 파일은
 *    계약이고, 픽스처가 그 계약의 «유일한 재료»입니다 — 배선은 서버가 실은 뒤입니다.
 *
 * 🔴 그리고 «이름이 갈릴 수 있습니다» — 판정으로 올렸습니다. 지시(09-09 08:33)는 위 셋을
 *    지목했는데, 여섯 분 뒤 서버가 착지시킨 것은 다른 철자입니다:
 *      `d91fba43  ledger/backfill  report["relation_rows"] · ["indexed_rows"] · ["not_yet"]`
 *    그쪽은 CLI 보고의 낱말이고 이 줄이 읽을 «선언 응답»은 아직 없으므로 둘이 같은 이름이
 *    될지 «정해지지 않았습니다». 이 배열이 그 답의 «유일한 자리»라 바꾸는 것은 한 줄입니다 —
 *    다른 어떤 파일에도 이 낱말들이 적혀 있지 않습니다.
 */
export const BACKLOG_FIELDS = Object.freeze(['rows_total', 'rows_indexed', 'rows_remaining']);

/**
 * @param {object} status 소스별 현황 레코드, 서버가 준 그대로
 * @returns {{name: string, text: string}[]} 칸 셋. 안 센 칸은 `text` 가 «빈 문자열»
 */
export function backlogCells(status) {
  const src = status && typeof status === 'object' ? status : {};
  return BACKLOG_FIELDS.map((name) => {
    // ⚠️ 「키가 있나」로 봅니다. `src[name]` 의 참/거짓으로 보면 «0 이 사라집니다» — 그리고 0 은
    //    이 화면이 가장 말하고 싶어 하는 답(「다 돌았다」)입니다.
    const raw = Object.prototype.hasOwnProperty.call(src, name) ? src[name] : undefined;
    if (raw === undefined || raw === null) return { name, text: '' };
    const count = Number(raw);
    if (!Number.isFinite(count)) return { name, text: '' };
    return { name, text: String(count) };
  });
}

/**
 * 그릴 것이 하나라도 있나 — 없으면 화면은 «그 줄 자체를» 안 그립니다.
 *
 * 🔴 빈 줄을 그리면 「안 셌다」가 「셌는데 빈칸 셋」처럼 보입니다. 서버가 이 셋을 싣기 전의
 *    오늘 화면이 «바이트 동일»해야 하는 이유도 이것입니다.
 */
export function hasBacklog(status) {
  return backlogCells(status).some((cell) => cell.text !== '');
}
