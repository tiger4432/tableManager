// ═══════════════════════════════════════════════════════════════════════════════
// C-42 — 「이 소스, 돌 게 있나」를 한 줄로.
//
// 🔴 THE QUESTION IS THE OWNER'S, ASKED IN PRODUCTION: 「파티션 로그만 뜨고 아무 말 없는데
//    돌 게 있는 건가」. The screen could say a source was declared, saved, verified and
//    refused — and could not say whether anything was WAITING.
//
// 🔴 THE SHAPE IS THE ONE THE ROUTE ACTUALLY SENDS, read off `GET /api/ledger/declaration`
//    on 2026-09-09 rather than off the sentence describing it. Per source, `sources[].census`:
//        counted   {source, relation, measured_at,
//                   relation_rows: {estimate, exact, method, measured_at}, indexed_rows: …, not_yet: …}
//        refused   {source, relation, measured_at, refused: "source_refused", remedy: "<the loader's sentence>"}
//        absent    no `census` key at all
//    Measured on this box: 15 sources, 11 counted, 4 REFUSED. The refusal is a third of the
//    population and it is not in any description of this shape — a reader who only had the
//    sentence would have drawn four blanks for those and called it 「아직 안 셌다」.
//
// 🔴 FOUR STATES, AND THREE OF THEM ARE EASY TO COLLAPSE:
//        키 없음       아직 아무도 안 셌다        -> 빈 칸
//        refused      «셀 수가 없다» + 고칠 자리  -> 사유를 이름으로. 빈 칸이 «아니다»
//        0            셌고, 돌 게 없다           -> 「0」
//        N            셌고, N 남았다             -> 「N」
//    「못 센다」와 「안 셌다」를 같은 빈 칸으로 그리면, 고칠 수 있는 것을 «기다리게» 만듭니다.
//
// 🔴 `estimate` 는 «수»이고 `exact` 는 그 수의 «성질»입니다. `measured()` 가 이 봉투를 만든
//    이유가 주석에 적혀 있습니다 — 「약 1,300만」이 「1,300만」이 되는 것을 막는 것. 그래서
//    exact 가 아니면 값 앞에 «≈» 하나가 붙습니다. 문장이 아니라 기호 하나입니다.
//
// ⛔ 「몇 분 전」으로 바꾸지 않습니다 — 새로 안 고친 화면이 그 수를 현재형으로 말합니다.
//    🔴 현지 벽시계로는 «옮깁니다»(총괄 bed890af2: 같은 사실의 시각이 UTC 와 현지 «둘»이었습니다).
//    옮기는 저자는 `server_time.js` 하나이고, 못 읽는 문자열은 서버 글자 그대로 냅니다.
// 🔴 이름은 서버가 줍니다 — 봉투의 `census_names` (`backfill.CENSUS_NAMES`). 없으면 키 그대로.
// ═══════════════════════════════════════════════════════════════════════════════

import { localShortOrAsSent } from './server_time.js';
import { NOT_MEASURED } from './absent.js';

/** 정확하지 않은 수 앞에 붙는 «기호 하나». 문장이 아닙니다. */
const ESTIMATE_MARK = '≈';

/**
 * 계약의 세 이름 — 순서까지 이것이 정본입니다.
 *
 * 🔴 화면이 이름을 «번역하지 않습니다». 라벨은 서버의 키 그대로이고(판정 177), 옮기면 서버가
 *    키를 바꾸는 날 화면이 «옛 이름으로» 옳아 보입니다.
 */
export const BACKLOG_FIELDS = Object.freeze(['relation_rows', 'indexed_rows', 'not_yet']);

/** 「언제 잰 값인가」 — 네 번째 칸. 수가 아니라 «그 수의 시각»입니다. */
export const MEASURED_AT = 'measured_at';

/**
 * 셀 수 «없는» 소스인가 — 그렇다면 «왜», 그리고 고칠 자리는 서버가 이미 문장으로 적었습니다.
 *
 * 🔴 문지기의 문장을 «그대로» 나릅니다(S-39 와 같은 규율). 여기서 다시 쓰면 조작자가 고칠
 *    자리를 잃고, 사전을 만들면 다음 사유가 생기는 날 화면이 그것을 모르는 채 빠뜨립니다.
 */
export function censusRefusal(census, names = {}) {
  const src = census && typeof census === 'object' ? census : null;
  if (!src || !src.refused) return null;
  const reason = String(src.refused);
  return { reason, name: nameOf(names, reason), remedy: src.remedy ? String(src.remedy) : '' };
}

const nameOf = (names, key) => (names && typeof names[key] === 'string' && names[key]) || key;

/** 봉투 하나 -> 칸 하나. 인구조사의 수와 «수정 누락»의 수가 이 함수 «하나»를 지납니다. */
function countCell(src, name) {
  // ⚠️ 「키가 있나」로 봅니다. 참/거짓으로 보면 «0 이 사라집니다» — 그리고 0 은 이 화면이
  //    가장 말하고 싶어 하는 답(「다 돌았다」)입니다.
  const box = Object.prototype.hasOwnProperty.call(src, name) ? src[name] : undefined;
  if (!box || typeof box !== 'object') return { name, text: '', method: '' };
  // 🔴 「어떻게 잰 수인가」는 «수와 같이» 나릅니다. `count(*)` 와 `pg_class.reltuples` 는
  //    같은 픽셀로 그리면 안 되는 두 사실이고, `≈` 는 그중 «추정이라는 것»만 말합니다 —
  //    «무엇으로» 쟀는지는 서버 낱말 그대로 실려야 조작자가 그 수를 믿을지 정합니다.
  //    ⚠️ 다섯째 칸을 만들지 «않습니다» — 칸이 아니라 그 칸에 «붙는» 사실입니다.
  const method = box.method == null ? '' : String(box.method);
  const count = Number(box.estimate);
  if (!Number.isFinite(count)) return { name, text: '', method };
  // 🔴 `exact` 가 «명시적으로 거짓»일 때만 표시합니다. 키가 없으면 「말 안 함」이고,
  //    말 안 한 것을 「추정」으로 그리는 것도 지어내는 것입니다.
  const mark = box.exact === false ? ESTIMATE_MARK : '';
  return { name, text: `${mark}${count}`, method };
}

/** 봉투의 `census_names` — 서버 한 자리의 이름표. 없으면 빈 표(그러면 키가 그려집니다). */
export function censusNames(body) {
  const src = body && body.census_names;
  if (!src || typeof src !== 'object' || Array.isArray(src)) return Object.freeze({});
  const out = {};
  for (const key of Object.keys(src)) if (typeof src[key] === 'string') out[key] = src[key];
  return Object.freeze(out);
}

/**
 * @param {object} census `sources[].census`, 서버가 준 그대로
 * @param {object} [names] `censusNames(body)`
 * @returns {{name: string, label: string, text: string, method: string}[]} 칸 넷. 안 센 칸은 `text` 가 «빈 문자열»
 */
export function backlogCells(census, names = {}) {
  const src = census && typeof census === 'object' ? census : {};
  const cells = BACKLOG_FIELDS.map((name) => countCell(src, name));
  const at = src[MEASURED_AT];
  cells.push({ name: MEASURED_AT, text: at == null ? '' : localShortOrAsSent(at), method: '' });
  return cells.map((cell) => ({ ...cell, label: nameOf(names, cell.name) }));
}

/**
 * «원장이 못 본 수정»의 두 수(서버 `rows_drifted` · `rows_unprinted`, 구현자 6b698fe2d). 사람이 돌린
 * census 만 셉니다 — 주기 census 는 안 셉니다. 둘은 «따로» 그립니다: 지문 없음은 누락이 아닙니다.
 */
export const DRIFT_FIELDS = Object.freeze(['rows_drifted', 'rows_unprinted']);

/** 0 이 아니면 «눈에 띄는» 수 — 누락 쪽 하나뿐입니다(총괄 c21cba507). */
const DRIFT_ALARM = 'rows_drifted';

/**
 * 한 소스의 «수정 누락» 줄 (총괄 c21cba507). 수는 서버 기록 그대로이고, 안 센 수는 `NOT_MEASURED`.
 * 시각은 «그 두 수의» `measured_at` 입니다 — census 전체의 시각이 아닙니다.
 * 다음 명령은 기록의 `next_step` 그대로입니다(서버 66570d724, 저자 하나). 그것이 없는 기록(옛 서버)은
 * 명령 줄이 없습니다 — 화면이 CLI 를 철자하지 않습니다.
 *
 * @returns {null | {cells: {name, label, text, method, counted, alarm}[], at: string, atLabel: string, next: string}}
 *   거절된 census 는 null — 거절 줄이 이미 「셀 수 없다」를 말합니다.
 */
export function driftLine(census, names = {}) {
  const src = census && typeof census === 'object' ? census : {};
  if (censusRefusal(src)) return null;
  const cells = DRIFT_FIELDS.map((name) => {
    const cell = countCell(src, name);
    const counted = cell.text !== '';
    return { ...cell, text: counted ? cell.text : NOT_MEASURED, counted, label: nameOf(names, name),
      alarm: name === DRIFT_ALARM && counted && Number(src[name].estimate) > 0 };
  });
  const stamped = DRIFT_FIELDS.map((name) => src[name])
    .find((box) => box && typeof box === 'object' && box.measured_at != null);
  return {
    cells,
    at: stamped ? localShortOrAsSent(stamped.measured_at) : '',
    atLabel: nameOf(names, MEASURED_AT),
    next: typeof src.next_step === 'string' ? src.next_step : '',
  };
}

/**
 * 그릴 것이 하나라도 있나 — 없으면 화면은 «그 줄 자체를» 안 그립니다.
 *
 * 🔴 거절도 «그릴 것»입니다. 셀 수 없다는 사실은 조작자가 고칠 수 있는 것이고, 빈 줄로
 *    두면 「아직 안 돌았나 보다」로 읽혀 아무도 안 고칩니다.
 */
export function hasBacklog(census) {
  if (censusRefusal(census)) return true;
  return backlogCells(census).some((cell) => cell.text !== '');
}

/**
 * `GET /api/ledger/declaration` 의 봉투 -> `{소스 이름: census}`.
 *
 * 🔴 C-47, 기준 ④ 「같은 기능에 «두 경로» 없음」. 이 지도를 «두 화면»이 씁니다 — 탐색기의
 *    인스펙터 한 줄과 대시보드의 소스 표. 각자 `body.sources` 를 풀면 서버가 그 칸의 이름을
 *    바꾸는 날 «한쪽만» 빈 지도가 되고, 그것은 「안 쟀다」와 «같은 픽셀»이라 아무도 못 봅니다.
 * ⚠️ 못 읽은 것은 «빈 지도»입니다 — 소스마다 「안 쟀다」이지 「세 봤더니 0」이 아닙니다.
 *    그래서 여기서 «지어내지» 않습니다: census 키가 없는 행은 지도에 «안 들어갑니다».
 */
export function censusBySource(body) {
  const rows = body && Array.isArray(body.sources) ? body.sources : [];
  const bySource = {};
  for (const row of rows) if (row && row.source && row.census) bySource[row.source] = row.census;
  return bySource;
}
