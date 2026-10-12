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
import { unitText } from './ui_words.js';

/** 그리드 열 id. `#` 로 시작해 사용자 열 이름(SQL 식별자)과 부딪히지 않습니다. */
export const LEDGER_COL_ID = '#ledger';
export const LEDGER_HEADER = 'Ledger';
export const NOT_YET = 'Not yet';
export const REFUSED = 'Refused';
export const CHANGED = 'changed';
export const UNVERIFIED = 'unverified';
/** A row's ledger entries, each `{ source, world, changed }` - which source took it, in which world, and whether the row
 *  changed after it was translated (the ledger's own drift judgment, lead 6424227ff): true changed, false not, null no
 *  print to compare (translated before prints were kept) - unknown, not «not changed». */
export const LEDGER_ROWS = 'ledger_rows';
/** The worlds whose declaration or row index the server could not read for this row: a tail «N unknown» and their hover
 *  lines Unknown - not Not yet, and not hiding the Not yet of the worlds read. */
export const LEDGER_UNREAD = 'ledger_worlds_unread';

/** 열이 서는 답. not_source · pending · idle 은 열이 없습니다. */
const SHOWN = new Set(['source', 'refused', 'unknown']);

/** `[]` 가 무엇을 뜻하나는 «표의» 답이 정합니다 — 행이 아닙니다. */
const EMPTY_TEXT = { source: NOT_YET, refused: REFUSED, unknown: UNKNOWN };

/** 이 답으로 이 표에 열이 서나. */
export function ledgerColumnShown(answer, table) {
  return Boolean(answer && table && answer.relation === table && SHOWN.has(answer.state));
}

export const SYNCED = 'synced';

const unreadOf = (row) => [...new Set(Array.isArray(row[LEDGER_UNREAD]) ? row[LEDGER_UNREAD] : [])];
const worldsOf = (entries) => [...new Set(entries.map((e) => e.world))];

/** 한 행의 칸 글자. `operating` 운영 세상 이름 — 그 세상 소스는 이름만(오늘 글자 그대로). `declared` 이 표의 소스들(세상마다).
 *  One word first, whole at the column's width (lead 10-12): changed > Not yet > Unknown > the sources; the worlds not
 *  named and not read ride a short tail, and every world's line is the hover's (`ledgerCellTip`). */
export function ledgerCellText(row, state, operating, declared = []) {
  const entries = row ? row[LEDGER_ROWS] : undefined;
  // 서버가 칸을 안 실었다 = 원장 색인을 못 읽었다. `[]` 로 읽으면 「아직」이라는 주장이 됩니다.
  if (!Array.isArray(entries)) return UNKNOWN;
  const unread = unreadOf(row);
  const unknownTail = unread.length ? [`${unread.length} unknown`] : [];
  const changed = entries.filter((e) => e.changed === true);
  if (changed.length) {
    const worlds = worldsOf(changed);
    const which = worlds.length > 1 ? unitText(worlds.length, 'world')
      : worlds[0] === operating ? changed.map((e) => e.source).join(' · ') : worlds[0];
    return [CHANGED, which, ...unknownTail].join(' · ');
  }
  // No world read took it: Not yet stays though a world was not read (lead 10-12).
  if (!entries.length) return [EMPTY_TEXT[state] || UNKNOWN, ...unknownTail].join(' · ');
  // 이름은 색인의 사실입니다 — 소스가 지금 거절됐어도 예전에 올린 것은 올린 것입니다.
  const worlds = worldsOf(entries).sort((a, b) => (b === operating) - (a === operating));
  const first = entries.filter((e) => e.world === worlds[0]).map((e) => e.source);
  const head = worlds[0] === operating ? first : [...first, worlds[0]];
  const more = worlds.length > 1 ? [`+${unitText(worlds.length - 1, 'world')}`] : [];
  return [...head, ...more, ...unknownTail].join(' · ');
}

/** The hover: a line per world and source, «<world> — <source> — synced/changed/unverified/Not yet/Refused/Unknown». */
export function ledgerCellTip(row, state, operating, declared = []) {
  const entries = row ? row[LEDGER_ROWS] : undefined;
  if (!Array.isArray(entries)) return UNKNOWN;
  const unread = unreadOf(row);
  const status = (e) => (e.changed === true ? CHANGED : e.changed === false ? SYNCED : UNVERIFIED);
  const pairs = declared.map((s) => ({ world: s.world || operating, source: s.source, refused: s.planned === false }));
  for (const e of entries) {
    if (!pairs.some((p) => p.world === e.world && p.source === e.source)) pairs.push({ world: e.world, source: e.source });
  }
  for (const world of unread) if (!pairs.some((p) => p.world === world)) pairs.push({ world, source: null });
  pairs.sort((a, b) => (b.world === operating) - (a.world === operating));
  return pairs.map((p) => {
    const e = entries.find((x) => x.world === p.world && x.source === p.source);
    const word = unread.includes(p.world) ? UNKNOWN : e ? status(e) : p.refused ? REFUSED : (EMPTY_TEXT[state] || UNKNOWN);
    return [p.world, p.source, word].filter(Boolean).join(' — ');
  }).join('\n');
}

/** The row changed after it was translated, by any source that took it. */
export const ledgerRowChanged = (row) => Boolean(row && Array.isArray(row[LEDGER_ROWS]) && row[LEDGER_ROWS].some((e) => e && e.changed === true));

/** 열 정의 — 그리드가 목록의 «맨 끝»에 붙입니다. 열이 없으면 `null`. */
export function ledgerColumnDef(answer, table) {
  if (!ledgerColumnShown(answer, table)) return null;
  const { state, operating, rows: declared } = answer;
  return {
    headerName: LEDGER_HEADER,
    colId: LEDGER_COL_ID,
    editable: false,
    // 서버가 이 칸으로 거르거나 정렬하지 못합니다 — 페이지 안에서만 정렬하면 「전체의 순서」처럼 보입니다.
    sortable: false,
    filter: false,
    floatingFilter: false,
    resizable: true,
    valueGetter: (params) => ledgerCellText(params.data, state, operating, declared),
    tooltipValueGetter: (params) => ledgerCellTip(params.data, state, operating, declared),
    // A changed row stands out of the dim system column (owner 10-12).
    cellClass: (params) => (ledgerRowChanged(params.data) ? 'cell-system-readonly is-ledger-changed' : 'cell-system-readonly'),
  };
}
