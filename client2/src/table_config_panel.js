// TABLE CONFIG — 표 하나를 «제품 안에서» 등록합니다.
//
// 🔴 이 파일은 이제 «선언»입니다. 모양은 `raw_registry_panel.js` 가 들고 있고, 여기 남은
//    것은 「이 등록부는 무엇으로 불리는가」뿐입니다 — 상설 「근원 템플릿 요소 개발 후
//    데이터 갈아끼우기」. 체인 규칙이 «둘째»가 되면서 첫째를 템플릿으로 올렸습니다.
//
// 읽는 것: `GET /admin/tables/config/raw`. 쓰는 것: `POST` 같은 주소, «표 하나» 단위.
// 규율 넷(편집 단위 · base 지문 · 서버 낱말 그대로 · 없는 것은 —)은 템플릿이 지킵니다.

import { registryView, RawRegistryPanel } from './raw_registry_panel.js';
import { ABSENT, isBlank } from './absent.js';

/**
 * 🔴 「선언은 됐는데 «물리 표»가 없는 것」을 «고르기 전»에 말합니다.
 *
 * 서버가 이것을 `admin/ledger/relations` 에서 «계속» 내고 있었고 (`missing_relations`),
 * 읽는 화면이 «0» 이었습니다. 그걸 고르면 저장이 `unknown_relation` 으로 거절되는데,
 * 거절은 «고른 뒤»에 옵니다 — 고르기 «전»에 말하는 것이 이 줄의 전부입니다.
 *
 * ⚠️ 세 상태입니다: 못 읽음 · 없음 · 있음.
 *    못 읽었으면 「모름」이고, 없으면 «아무것도 안 그립니다» (경고할 것이 없습니다).
 * ⛔ 문장을 쓰지 않습니다 — 상태는 명사, 이름은 `·` 로 (상설 2026-09-05).
 */
function missingRelations(payload, opts) {
  if (opts && opts.relationsUnread) return { value: 'unread', text: 'Physical table · unknown' };
  const names = Array.isArray(opts && opts.missingRelations) ? opts.missingRelations : null;
  if (!names || !names.length) return null;
  return { value: 'missing', text: `No physical table · ${names.join(' · ')}` };
}

// ═══ Paste columns from a sheet (lead f382dacfb, owner 10-01) ═══════════════════════════════
//
// 🔴 THE TYPE WORDS THE SERVER TELLS APART. There is no list to read: `models.py` builds a column
//    as Float for `number`, DateTime for `datetime` and String for anything else, so an unknown word
//    lands as a string column with nothing said. These three are that rule's names.
export const COLUMN_TYPES = Object.freeze(['string', 'number', 'datetime']);
/** The word row 3 puts under a business key column. */
const KEY_MARK = 'key';

/**
 * Sheet rows -> this table's columns. Row 1 names, row 2 types, row 3 (when it marks anything)
 * `key` under the business key: one is `business_key`, more are `composite_key_source` left to
 * right. What was pasted REPLACES `column_types`, `display_columns` and, with a key row, both key
 * spellings; every other field the document holds stays. Pure.
 * @param {string[][]} rows   what `parseTsv` read
 * @param {object|null} held  the document as it stands
 * @returns {{next: object|null, refused: string[]}}
 */
export function columnsFromPaste(rows, held) {
  const [names = [], types = [], marks = [], ...beyond] = rows || [];
  const width = Math.max(names.length, types.length, marks.length);
  // 🔴 Nothing pasted would write no columns over every column the table has.
  if (!width) return { next: null, refused: ['Nothing pasted'] };
  const keyRow = marks.some((mark) => !isBlank(mark));
  const refused = beyond.map((_, i) => `row ${i + 4}: only names, types and key are read`);
  const seen = new Set();
  for (let i = 0; i < width; i += 1) {
    const name = isBlank(names[i]) ? '' : String(names[i]);
    if (!name) { refused.push(`column ${i + 1}: no name`); continue; }
    const at = `column ${i + 1} (${name})`;
    if (seen.has(name)) refused.push(`${at}: name repeated`);
    seen.add(name);
    const type = isBlank(types[i]) ? '' : String(types[i]);
    if (!COLUMN_TYPES.includes(type)) refused.push(`${at}: unknown type ${type || ABSENT}`);
    if (keyRow && !isBlank(marks[i]) && marks[i] !== KEY_MARK) refused.push(`${at}: ${marks[i]} is not ${KEY_MARK}`);
  }
  if (refused.length) return { next: null, refused };
  const base = held && typeof held === 'object' && !Array.isArray(held) ? held : {};
  const columns = names.slice(0, width).map(String);
  const next = {
    ...base,
    column_types: Object.fromEntries(columns.map((name, i) => [name, String(types[i])])),
    display_columns: columns,
  };
  if (keyRow) {
    const keys = columns.filter((_, i) => marks[i] === KEY_MARK);
    delete next.business_key;
    delete next.composite_key_source;
    if (keys.length === 1) [next.business_key] = keys;
    else next.composite_key_source = keys;
  }
  return { next, refused: [] };
}

const keyText = (d) => {
  const parts = Array.isArray(d.composite_key_source) ? d.composite_key_source : [];
  const single = isBlank(d.business_key) ? '' : String(d.business_key);
  const joined = parts.join(' + ');
  return single && joined ? `${single} (${joined})` : (single || joined || ABSENT);
};
// 🔴 A ROW'S IDENTITY is the composite when there is one, else the business key column (crud's key
//    assembly: with both, the joined value is written back into the business key column).
const identityOf = (d) => JSON.stringify(
  Array.isArray(d.composite_key_source) && d.composite_key_source.length ? d.composite_key_source
    : (isBlank(d.business_key) ? [] : [String(d.business_key)]));

/**
 * What saving `after` changes in the table `before` describes: columns dropped, types changed, the
 * key, and whether the rows' identity moves. A table that does not exist yet has nothing to lose. Pure.
 * @returns {string[]}
 */
export function columnChanges(before, after) {
  if (!before || typeof before !== 'object' || Array.isArray(before)) return [];
  const now = after && typeof after === 'object' && !Array.isArray(after) ? after : {};
  const was = before.column_types && typeof before.column_types === 'object' ? before.column_types : {};
  const types = now.column_types && typeof now.column_types === 'object' ? now.column_types : {};
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const lines = [];
  const dropped = Object.keys(was).filter((name) => !has(types, name));
  if (dropped.length) lines.push(`Dropped · ${dropped.join(' · ')}`);
  for (const name of Object.keys(was)) {
    if (has(types, name) && was[name] !== types[name]) lines.push(`Type · ${name} · ${was[name]} → ${types[name]}`);
  }
  if (keyText(before) !== keyText(now)) lines.push(`Key · ${keyText(before)} → ${keyText(now)}`);
  if (identityOf(before) !== identityOf(now)) lines.push('Existing rows change identity');
  return lines;
}

/** 이 등록부의 낱말. 도메인 이름이 사는 자리는 «여기 하나»입니다. */
export const TABLE_REGISTRY = Object.freeze({
  listKey: 'tables',
  nameKey: 'table',
  cls: 'table-config',
  extra: missingRelations,
  // C-86 ①. 템플릿이 자란 것을 이 등록부도 «선언 한 줄»로 받습니다 — 둘째를 손으로 그리지
  // 않는다는 상설 그대로입니다. 서버가 새 이름을 받는지 «재서» 켭니다: `save_table_config_raw`
  // 는 얕은 병합이라 없던 키를 만듭니다(이름이 비었을 때만 `table_name_required` 로 거절).
  addLabel: 'Add table',
  // 이 라우트는 스켈레톤을 «안 싣습니다» — 그래서 폼이 없고 화면은 오늘 그대로입니다.
  paste: Object.freeze({ read: columnsFromPaste, changes: columnChanges }),
});

/**
 * @param {object|null} payload  `/admin/tables/config/raw` 의 응답, 또는 null
 * @param {{unavailable?: string, refusal?: object, saved?: object}} [opts]
 */
export function tableConfigView(payload, opts = {}) {
  return registryView(payload, opts, TABLE_REGISTRY);
}

/**
 * @param {HTMLElement} mount
 * @param {{doc?: Document, onOpen?: Function, onSave?: Function}} [deps]
 */
export class TableConfigPanel extends RawRegistryPanel {
  constructor(mount, deps = {}) {
    super(mount, deps, TABLE_REGISTRY);
  }
}
