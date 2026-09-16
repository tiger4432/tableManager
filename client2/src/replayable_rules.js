// ════════════════════════════════════════════════════════════════════════════
// 「이 표를 트리거로 하는, 다시 돌릴 수 있는 규칙」 — 그리드 배너가 고를 줄의 «목록»
//
// 🔴 왜 자기 파일인가: 이것은 `main.js` 에 살던 `loadChainRuleNames` 의 후계인데,
//    `main.js` 는 node 가 «import 할 수 없습니다» — 최상단에서 ag-grid 와 CSS 를 import 하고
//    마지막 줄에서 `init()` 을 돕니다. 그 파일 안에 두면 이 함수를 재는 길이 «잘라쓰기»뿐이고
//    그것은 금지입니다(소유자 상설 2026-09-02). `source_rows.js`(C-14) · `write_guard.js`(C-107) 가
//    같은 사유로 나온 자리이고, 이 파일은 그 셋째입니다.
// 🔴 답이 «세 상태»입니다: 객체 배열(읽었다) · `[]`(이 표를 트리거로 하는 규칙이 없다) ·
//    `null`(못 읽었다 — 토큰 없음 · 거절 · 모양이 다름). 셋을 둘로 접으면 「403」과 「빈 목록」이
//    화면에서 같아집니다(부품의 그 두 문장이 이 세 상태를 읽습니다).
// ⚠️ 서버가 준 «객체를 그대로» 돌려줍니다. 여기서 고르면 칸이 하나 느는 날 화면이 선언보다
//    «덜» 말합니다 — 무엇을 그릴지는 부품이 정합니다.
// ════════════════════════════════════════════════════════════════════════════
import { API_BASE } from './config.js';
import { ADMIN_TOKEN_HEADER, readAdminToken } from './admin_token.js';

/**
 * 이 표를 트리거로 하는 규칙들. 거르는 것은 «서버»입니다(S-250) — 화면은 묻기만 합니다.
 *
 * 🔴 `row_scoped=true` 를 «항상» 실어 묻습니다 (S-270). 배너가 보내는 payload 에는
 *    `row_ids` «뿐»이고, 그래서 이 화면에서 고를 수 있는 소급은 «전부 행 범위»입니다.
 *    조인의 참조 쪽이 통째 소급에서 거절되는 사유(S-242: 대상 쪽을 한 번 돌리면 덮인다)는
 *    «범위 전체»의 논증이라 여기서는 참이 아닙니다 — 행을 고른 순간 그 규칙이 «유일하게
 *    맞는» 규칙이고, 대상 쪽은 이 그리드에서 고를 수 없는 표를 트리거로 합니다.
 * ⚠️ 이 인자를 빼면 화면은 다시 그 규칙을 «안 보여 주고», 운영자는 조인 체인만 없는
 *    목록을 보게 됩니다 — 소유자가 오늘 아침 신고한 그 모양입니다.
 *
 * @param {string} table
 * @returns {Promise<Array<object>|null>} 읽은 목록, 또는 `null`(못 읽음)
 */
export async function loadReplayableRules(table) {
  // 주어가 없으면 목록도 없습니다. 「표를 아직 안 골랐다」는 「없다」가 아니라 「모른다」입니다.
  if (!table) return null;
  const token = readAdminToken();
  if (!token) return null;
  try {
    const res = await fetch(
      `${API_BASE}/admin/chain/rules/replayable?table=${encodeURIComponent(table)}`
      + '&row_scoped=true',
      { headers: { [ADMIN_TOKEN_HEADER]: token } });
    if (!res.ok) return null;
    const body = await res.json();
    if (!body || body.status !== 'success' || !Array.isArray(body.data)) return null;
    return body.data;
  } catch (e) {
    return null;
  }
}
