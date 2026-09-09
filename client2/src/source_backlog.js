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
//        refused   {source, relation, measured_at, refused: "no_row_id", remedy: "<what to declare>"}
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
// ⛔ 시각을 «다시 쓰지» 않습니다. `measured_at` 은 서버가 준 그대로 — 여기서 「몇 분 전」으로
//    바꾸면 이 화면이 시계의 두 번째 저자가 되고, 새로 안 고친 화면은 그 수를 현재형으로 말합니다.
// ═══════════════════════════════════════════════════════════════════════════════

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
export function censusRefusal(census) {
  const src = census && typeof census === 'object' ? census : null;
  if (!src || !src.refused) return null;
  return { reason: String(src.refused), remedy: src.remedy ? String(src.remedy) : '' };
}

/**
 * @param {object} census `sources[].census`, 서버가 준 그대로
 * @returns {{name: string, text: string, method: string}[]} 칸 넷. 안 센 칸은 `text` 가 «빈 문자열»
 */
export function backlogCells(census) {
  const src = census && typeof census === 'object' ? census : {};
  const cells = BACKLOG_FIELDS.map((name) => {
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
  });
  const at = src[MEASURED_AT];
  cells.push({ name: MEASURED_AT, text: at == null ? '' : String(at), method: '' });
  return cells;
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
