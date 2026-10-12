// ═══════════════════════════════════════════════════════════════════════════════
// LEDGER COLUMN — 그리드 행마다 「원장에 올라갔나 · 어느 소스가」 (총괄 f3bc02f6e · 533a386c6 ·
// fb4dda078, 자리는 소유자 「맨 끝」 cdf11b222).
//
// 🔴 「이 표가 원장 소스인가」는 여기서 묻지 않습니다 — GridSourceLabel.answer() 가 답하고 이 파일은
//    그 답을 «받습니다». 칸(`LEDGER_ROWS`)의 유무로 짐작하지 않습니다.
// 🔴 답은 «그 표의» 답일 때만 씁니다. 표를 바꾸면 그리드가 먼저 그려지고 라벨은 그 뒤에 새 표를
//    압니다 — 이전 표의 답으로 열을 세우면 한 박자 동안 거짓입니다.
//
// NO DOM, NO STATE. node 가 import 해서 채점합니다.
// ═══════════════════════════════════════════════════════════════════════════════

import { UNKNOWN } from './absent.js';

/** 그리드 열 id. `#` 로 시작해 사용자 열 이름(SQL 식별자)과 부딪히지 않습니다. */
export const LEDGER_COL_ID = '#ledger';
export const LEDGER_HEADER = 'Ledger';
export const NOT_YET = 'Not yet';
export const REFUSED = 'Refused';
export const CHANGED = 'changed';
/** A row's ledger entries, each `{ source, world, changed }` - which source took it, in which world, and whether the row
 *  changed after it was translated (the ledger's own drift judgment, lead 6424227ff). */
export const LEDGER_ROWS = 'ledger_rows';

/** 열이 서는 답. not_source · pending · idle 은 열이 없습니다. */
const SHOWN = new Set(['source', 'refused', 'unknown']);

/** `[]` 가 무엇을 뜻하나는 «표의» 답이 정합니다 — 행이 아닙니다. */
const EMPTY_TEXT = { source: NOT_YET, refused: REFUSED, unknown: UNKNOWN };

/** 이 답으로 이 표에 열이 서나. */
export function ledgerColumnShown(answer, table) {
  return Boolean(answer && table && answer.relation === table && SHOWN.has(answer.state));
}

/** An entry's words: its source, its world when not the operating one, «changed» when the row moved after translation. */
const entryText = (entry, operating) => [entry.source, entry.world && entry.world !== operating ? entry.world : null,
  entry.changed ? CHANGED : null].filter(Boolean).join(' · ');

/** 한 행의 칸 글자. `operating` 운영 세상 이름 — 그 세상 소스는 이름만(오늘 글자 그대로). */
export function ledgerCellText(row, state, operating) {
  const entries = row ? row[LEDGER_ROWS] : undefined;
  // 서버가 칸을 안 실었다 = 원장 색인을 못 읽었다. `[]` 로 읽으면 「아직」이라는 주장이 됩니다.
  if (!Array.isArray(entries)) return UNKNOWN;
  // 이름은 색인의 사실입니다 — 소스가 지금 거절됐어도 예전에 올린 것은 올린 것입니다.
  if (entries.length) return entries.map((entry) => entryText(entry, operating)).join(' · ');
  return EMPTY_TEXT[state] || UNKNOWN;
}

/** The row changed after it was translated, by any source that took it. */
export const ledgerRowChanged = (row) => Boolean(row && Array.isArray(row[LEDGER_ROWS]) && row[LEDGER_ROWS].some((e) => e && e.changed));

/** 열 정의 — 그리드가 목록의 «맨 끝»에 붙입니다. 열이 없으면 `null`. */
export function ledgerColumnDef(answer, table) {
  if (!ledgerColumnShown(answer, table)) return null;
  const { state, operating } = answer;
  return {
    headerName: LEDGER_HEADER,
    colId: LEDGER_COL_ID,
    editable: false,
    // 서버가 이 칸으로 거르거나 정렬하지 못합니다 — 페이지 안에서만 정렬하면 「전체의 순서」처럼 보입니다.
    sortable: false,
    filter: false,
    floatingFilter: false,
    resizable: true,
    valueGetter: (params) => ledgerCellText(params.data, state, operating),
    // A changed row stands out of the dim system column (owner 10-12).
    cellClass: (params) => (ledgerRowChanged(params.data) ? 'cell-system-readonly is-ledger-changed' : 'cell-system-readonly'),
  };
}
