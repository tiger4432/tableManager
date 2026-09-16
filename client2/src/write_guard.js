// WRITE GUARD — 「이 표에 쓸 수 있나」의 «한 규칙».
//
// 🔴 왜 이 파일이 생겼나 (C-107, 소유자 2026-09-13 제안 채택). C-84 가 뷰에서 쓰기를 막을 때
//    좌석을 «하나씩» 덮었고, 그래서 C-102 에서 일곱째(「행 추가」)가 빠진 채로 발견됐습니다.
//    판정 자체는 이미 한 곳이었는데(`tableIsView`), «그 판정을 묻는 일»이 자리마다 손으로
//    적혀 있었습니다 — 두 줄씩 다섯 번. 여덟째 좌석이 생기는 날 또 빠집니다.
//
// ═══ 이 파일이 답하는 둘 ═══════════════════════════════════════════════════════════════
//
// ① 「지금 쓰면 거절되나, 그리고 왜」          -> `writeRefusal()` · `refuseWrite()`
// ② 「쓰는 «컨트롤»들은 지금 어떤 상태인가」   -> `applyWriteGuards()`
//
// 🔴 ②의 목록이 «한 곳»인 것이 이 파일의 요점입니다. 컨트롤이 각자 물으면 새 컨트롤마다 한 번씩
//    빠지고, 빠진 것은 «조용합니다» — 눌리고, 서버까지 가고, 거기서 거절됩니다.
//
// ⚠️ 사유의 철자는 여기서 짓지 «않습니다». `state.js` 의 `VIEW_READ_ONLY_NOTE` 하나이고, 화면의
//    배지도 같은 글자를 씁니다 — 같은 사실에 두 문구를 쓰면 그 둘은 언젠가 갈라집니다.

import { tableIsView, VIEW_READ_ONLY_NOTE } from './state.js';
import { elements } from './dom.js';
// 🔴 C-120. 「꺼짐 + 왜」를 그리는 «몸통»은 이제 여기 있지 않습니다. 이 파일이 답하는 것은
//    「이 표에 쓸 수 있나」이고, 「행을 골랐나」 같은 «다른 물음»이 같은 기제를 쓰기 때문입니다.
//    한 함수가 두 물음에 답하기 시작하면 그것이 다음 라운드의 결함입니다.
import { setDisabledReason } from './disabled_reason.js';

/**
 * 이 화면에서 «쓰는» 컨트롤들. 실측 2026-09-13: 여섯 다 `state.currentTable` 에 씁니다 —
 * 행 추가/삭제는 그 표의 행을, 트랜잭션 적용은 그 표의 셀을, 나머지 셋은
 * `POST /tables/<현재 표>/upload` 로 «그 표»에 인제션합니다(스마트 붙여넣기 포함).
 *
 * 🔴 이름으로 듭니다 — `elements` 는 게터라 «부를 때» 문서를 봅니다. 목록에 이름만 더하면
 *    새 컨트롤이 이 규칙 안으로 들어옵니다.
 */
const WRITE_CONTROLS = [
  'addRowBtn', 'deleteRowBtn', 'txApplyBtn',
  'smartPasteBtn', 'ingestFileBtn', 'folderUploadBtn',
];

/**
 * 쓰기가 거절되는 «사유», 또는 ''(쓸 수 있음).
 *
 * ⚠️ 「모른다」는 거절이 아닙니다 — 옛 서버가 `kind` 를 안 보내면 `tableIsView()` 가 거짓이고,
 *    그때 멀쩡한 표의 편집을 막으면 이 가드가 고장이 됩니다(C-84 의 P3 가 그 단언입니다).
 */
export function writeRefusal() {
  return tableIsView() ? VIEW_READ_ONLY_NOTE : '';
}

/**
 * 쓰기가 거절되면 «사유를 적고» true. 부르는 쪽은 `if (refuseWrite()) return;` 한 줄입니다.
 *
 * 🔴 깔때기 넷이 이 함수를 지납니다(붙여넣기 · 지우기 · 일괄 채우기 · 행 추가). 종전에는 그
 *    두 줄이 자리마다 손으로 적혀 있었고, 한 자리가 «조용한 no-op» 이 되는 것을 막는 것이
 *    그 둘째 줄입니다 — 아무 말 없이 안 되는 것은 고장과 구별되지 않습니다.
 */
export function refuseWrite() {
  const why = writeRefusal();
  if (!why) return false;
  const el = elements.performanceLog;
  if (el) el.textContent = why;
  return true;
}

/**
 * 쓰는 컨트롤들과 «머리의 배지»를 지금 상태로 맞춥니다. 표가 바뀐 «직후»에 부릅니다 —
 * 표의 종류를 아는 첫 자리가 거기입니다(`api.switchTable` 의 `loadSchema` 다음 줄).
 *
 * ⚠️ 마크업이 «이미» 자기 말을 답니다(`title="Add Row"`). 그것을 지우면 표로 돌아왔을 때 버튼이
 *    말을 잃습니다 — 기억했다 되돌립니다.
 */
export function applyWriteGuards() {
  const why = writeRefusal();
  for (const handle of WRITE_CONTROLS) {
    setDisabledReason(elements[handle], why);
  }
  // 🔴 C-107. 그리고 «표 자체»가 그 사실을 말합니다. 종전에는 뷰라는 것이 화면에 «없었고»,
  //    쓰려고 해야 알 수 있었습니다 — 잠긴 컨트롤의 «이유»가 눌러 보기 전에는 안 보입니다.
  const badge = elements.tableKind;
  if (!badge) return;
  badge.textContent = why;
  badge.hidden = !why;
}
