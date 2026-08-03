// ── THE map_split_registry ROW: its ONE normal form (client2/src/split_registry_row.js)
//
// A legend row IS a DOE, and a DOE IS one `map_split_registry` row. This module is the
// only place that turns one into the other, in both directions: the read (`parseLegendRegistryRows`),
// the write payload (`buildLegendRegistryUpdates`), the concurrency fingerprint
// (`registryFingerprint`) and the vocabulary-claim signature (`legendRowSignature`) all
// project through the SAME `LEGEND_PAYLOAD_COLUMNS` list and the SAME serialisers. That is
// the property this file exists to make unbreakable: a field that is saved is necessarily a
// field that is compared, so an edit can never be shown on screen and dropped from the save.
//
// It used to live in `map_editor.js`. Everything here is a PURE function of its arguments -
// measured, not assumed: zero reads and zero writes of module state (the legend cluster,
// `gridData`, `selectedTable`, `overlayContract` are all untouched). The stateful half of the
// registry seam - the read/save orchestration and the legend cluster it mutates - deliberately
// stayed in `map_editor.js`, because moving it would mean exporting mutable bindings.
//
// ⚠️ Harnesses slice these functions out of THIS FILE by text and evaluate them in a vm:
//    contracts/legend_map_scope, contracts/band_arithmetic, contracts/doe_band_rules and
//    server/tests/test_install_product_tables.py (which reads the `updates:` literal in
//    `buildLegendRegistryUpdates` statically). Renaming or reshaping anything here is a
//    deliberate act that must re-point them in the same commit.

import { bandToState } from './transfer_plan.js';
import { parseMaterialList, bandsToZones } from './doe_bands.js';
// map_key 자체가 '_' 조인 문자열이고 테이블명에도 '_'가 흔하므로 bk 분리자는 '|' 사용
// (server/config/table_config.json의 composite_key_separator와 반드시 일치해야 함)
const SPLIT_KEY_SEP = '|';

function buildSplitKey(refTable, mapKey, value) {
  return [refTable, mapKey, value].join(SPLIT_KEY_SEP);
}

// ── DOE 모델 (ZONE, 2026-07-27) ─────────────────────────
// legend 행이 곧 DOE다:
//   { value, desc, color, knobs: [{k,v}], stack, mat_1h[], mat_mid[], mat_top[] }
//
// zone 계약 (server/product_tables.py의 map_split_registry.__comment와 같은 글):
//   * `stack` = 그 값의 총 층수. `mat_1h` = 1층, `mat_top` = stack층, `mat_mid` = 그 사이 전부.
//     세 구역이 `1..stack`을 **구성적으로** 덮으므로 겹침·구멍 검사가 사라졌다 — 옮긴 게
//     아니라 어길 방법이 없어졌다. 자세한 것은 docs/spec/MAP_EDITOR_SPEC.md §6.0-bis.
//   * **세 mat_* 컬럼은 원문 토큰의 JSON 배열**이다. 분리자로 이어붙이지 않는다: lot 이름에
//     ':' 도 '_' 도 합법이라 안전한 문자가 없고, 한 번 가정했다가 서로 다른 두 풀이 한 행으로
//     합쳐져 수량이 더해진 적이 있다(doe_bands.js의 `materialPoolKey` 주석).
//   * 자재는 **입력한 원문 문자열 그대로**가 정체다. lot/slot/BIN 파싱은 나중의, 선언된
//     단계이고 저장된 문자열을 움직여서는 안 된다.
//   * **파생값은 저장하지 않는다.** 구역 총량 = 그 값의 칠한 셀 수 × 층 수,
//     자재당 = ceil(총량 / 자재 수). 저장하면 누가 한 칸 더 칠하는 순간 어긋난 채 남는다.
//
// ⚠️ `bands`는 **폐기됐지만 읽기 전용으로 살아 있다.** 서버에 band 모델로 쓰인 실계획이
//    남아 있고, legend 저장은 `replace_map`이다 — 읽지 않으면 그 맵을 여는 순간 화면이
//    비고, 다음 키 입력 한 번이 그 계획을 **빈 집합으로 지운다**. 그래서 `normalizeBands`는
//    지우지 않았다. 다만 **쓰지는 않는다**(새 writer 금지 — product_tables.py의 지시).
function parseJsonCol(raw, fallback) {
  if (raw === null || raw === undefined || raw === '') return fallback;
  if (typeof raw === 'object') return raw;
  try { return JSON.parse(String(raw)); } catch (e) { return fallback; }
}

export function normalizeBands(raw) {
  const src = Array.isArray(raw) ? raw : [];
  const out = [];
  src.forEach((b, i) => {
    if (!b || typeof b !== 'object') return;
    // seq 정체 규칙은 서버 `_assign_band_seqs`와 **같은 규칙**이어야 한다: 양의 정수 타입만
    // 인정하고 나머지는 위치 폴백. 종전 `Number(b.seq)`는 '2'·true도 통과시켜, 그리드가 쓴
    // 문자열 seq에서 서버는 위치 폴백 · 클라는 2가 되어 같은 구간에 두 이름이 붙었다.
    const rawSeq = b.seq;
    const seq = (typeof rawSeq === 'number' && Number.isInteger(rawSeq) && rawSeq > 0)
      ? rawSeq : (i + 1);
    // `to` 해석은 **transfer_plan의 판정기 하나뿐**이다. 여기서 따로 `Number()`를 돌리면
    // 읽기-수정-쓰기가 값을 조용히 바꾼다 — 실제로 '0x10'이 16으로, '  '가 0으로 저장됐다.
    // 읽을 수 없는 값은 **원문 그대로 보존**한다: 임의로 ''로 만들면 패널이 표시할 근거가
    // 사라져 "틀린 줄 모르는 채" 0층으로 계산된다.
    const toSt = bandToState(b);
    const to = toSt.state === 'ok' ? toSt.value : (toSt.state === 'blank' ? '' : b.to);
    const materials = [];
    (Array.isArray(b.materials) ? b.materials : []).forEach(m => {
      const s = String(m === null || m === undefined ? '' : m).trim();
      if (s && materials.indexOf(s) < 0) materials.push(s);
    });
    out.push({ seq, to, materials });
  });
  // Two bands sharing a seq would make one material set answer to both. Only
  // corrupt data gets here, but repairing it beats aliasing two identities.
  const seen = new Set();
  let next = out.reduce((m, b) => Math.max(m, b.seq), 0) + 1;
  out.forEach(b => { if (seen.has(b.seq)) b.seq = next++; seen.add(b.seq); });
  return out;
}

// 저장 형식은 JSON 객체 {k: v}, 편집 형식은 순서 있는 쌍 배열.
export function normalizeKnobs(raw) {
  if (Array.isArray(raw)) {
    return raw.filter(p => p && typeof p === 'object')
      .map(p => ({
        k: String(p.k === null || p.k === undefined ? '' : p.k),
        v: String(p.v === null || p.v === undefined ? '' : p.v)
      }));
  }
  if (raw && typeof raw === 'object') {
    return Object.entries(raw).map(([k, v]) => ({ k: String(k), v: (v === null || v === undefined) ? '' : String(v) }));
  }
  return [];
}

function knobsToObject(arr) {
  const out = {};
  (Array.isArray(arr) ? arr : []).forEach(p => {
    const k = String((p && p.k) || '').trim();
    if (k) out[k] = (p.v === undefined || p.v === null) ? '' : String(p.v);
  });
  return out;
}

function serializeKnobs(knobs) { return JSON.stringify(knobsToObject(normalizeKnobs(knobs))); }

// ── zone 저장 정규형 ────────────────────────────────────
//
// `stack`은 문자열 컬럼이다. **읽을 수 없는 값은 원문 그대로 보존한다** — 임의로 ''로 만들면
// 패널이 무엇을 고치라고 말할 근거가 사라지고, 그 값은 "틀린 줄 모르는 채" 계산에서 빠진다.
// 판정기는 `bandToState` 하나뿐이다: 정규화기가 자기 나름의 `Number()`를 돌리면
// 읽기-수정-쓰기가 조용히 값을 바꾼다(실제로 '0x10'이 16으로 저장되고 있었다).
function serializeStack(raw) {
  const st = bandToState({ to: raw });
  if (st.state === 'ok') return String(st.value);
  if (st.state === 'blank') return '';
  return String(raw);
}
// 원문 토큰의 JSON 배열. 목록 정규화는 `parseMaterialList` **하나뿐**이다 — 패널의 입력
// 파서와 저장 정규화기가 서로 다른 trim/중복 규칙을 가지면 화면의 자재 수와 `share`의
// 분모가 갈린다(분모가 갈리면 수량이 갈린다).
function serializeMaterials(raw) {
  return JSON.stringify(parseMaterialList(raw));
}

// legend 항목의 정규형 (DOE 필드 포함). 로드 경로가 여러 갈래라 한 곳에서만 만든다.
//
// `vocab` = PROVENANCE. true means "this row is a brush SUGGESTION borrowed from the
// table's shared value vocabulary - no map has claimed it". It exists because the two
// registry reads produce rows that look identical on screen but mean opposite things:
// a map-scoped read returns rows this map owns, a table-wide read returns rows that
// belong to OTHER map keys. Without the mark, a legend seeded table-wide flowed into a
// `replace_map` write and became the opened map's whole plan (see fetchRegistryRows).
// It is cleared the moment the map vouches for the value - its registry row, its painted
// cells, or the user editing the row - and it is never persisted to the server.
export function normalizeLegendItem(item) {
  const it = item || {};
  return {
    value: String(it.value === null || it.value === undefined ? '' : it.value),
    desc: String(it.desc || ''),
    color: (it.color !== null && it.color !== undefined && String(it.color) !== '') ? String(it.color) : '#6b7280',
    knobs: normalizeKnobs(it.knobs),
    stack: (it.stack === null || it.stack === undefined) ? '' : it.stack,
    mat_1h: parseMaterialList(it.mat_1h),
    mat_mid: parseMaterialList(it.mat_mid),
    mat_top: parseMaterialList(it.mat_top),
    // 폐기 모델의 흔적. 마이그레이션이 실패한 행에서만 값이 남고(그 행은 저장이 막힌다),
    // 정상 마이그레이션된 행에서는 비어 있다. **쓰기 대상이 아니다.**
    legacyBands: Array.isArray(it.legacyBands) ? normalizeBands(it.legacyBands) : [],
    legacyReason: String(it.legacyReason || ''),
    vocab: it.vocab === true,
  };
}

// legend 배열 깊은 복사 — 자재 목록·knobs가 배열이라 얕은 복사는 프레임 스냅샷과 화면이
// 같은 배열을 공유하게 만든다(한쪽 편집이 다른 쪽을 조용히 오염시킨다).
export function cloneLegend(arr) {
  return (Array.isArray(arr) ? arr : []).map(l => {
    const n = normalizeLegendItem(l);
    n.knobs = n.knobs.map(p => ({ ...p }));
    n.mat_1h = n.mat_1h.slice();
    n.mat_mid = n.mat_mid.slice();
    n.mat_top = n.mat_top.slice();
    n.legacyBands = n.legacyBands.map(b => ({ seq: b.seq, to: b.to, materials: b.materials.slice() }));
    return n;
  });
}

// ── 저장되는 컬럼의 목록. 한 곳에서만 만든다. ─────────────────────────────────
//
// 🔴 THIS LIST IS THE GATE, and that is why it is a list rather than five hand-written
//    field references. Three things read it: the write payload, the concurrency
//    fingerprint, and `legendRowSignature` (which is what DERIVES a vocabulary claim when
//    an edit path forgets to declare one). Previously each of the three spelled the fields
//    out separately. Add a column to the writer alone and the consequence is not a missing
//    column - it is that an edit touching ONLY that column is invisible to
//    `reconcileVocabClaims`, so the user's typing stays on screen and is dropped from the
//    save that was supposed to carry it. Visible, plausible, wrong.
//
//    With one list, a saved field is NECESSARILY a compared field. That is the difference
//    between documenting the rule and making it unbreakable.
const LEGEND_PAYLOAD_COLUMNS = ['value', 'split_desc', 'color', 'knobs', 'stack', 'mat_1h', 'mat_mid', 'mat_top'];

// legend 행 -> 저장 컬럼 맵. 키는 **DB 컬럼 이름**이다.
// ⚠️ `bands`는 여기 없다. 폐기됐고 새 writer를 만들지 않는다(product_tables.py의 지시).
function legendRowPayload(item) {
  const it = item || {};
  return {
    value: String(it.value === null || it.value === undefined ? '' : it.value).trim(),
    split_desc: String(it.desc === null || it.desc === undefined ? '' : it.desc).trim(),
    color: (it.color !== null && it.color !== undefined && String(it.color) !== '') ? String(it.color) : '#6b7280',
    knobs: serializeKnobs(it.knobs),
    stack: serializeStack(it.stack),
    mat_1h: serializeMaterials(it.mat_1h),
    mat_mid: serializeMaterials(it.mat_mid),
    mat_top: serializeMaterials(it.mat_top),
  };
}

// registry 행의 **유일한 정규형**. 동시성 검사의 양쪽이 모두 이 함수를 통과한다 —
// 서버에서 읽은 행과 지금 보내려는 페이로드. "같은 행"의 구현이 둘이면 진짜 충돌을
// 놓치거나 없는 충돌을 만들어낸다.
function canonRegistryRow(r) {
  const it = r || {};
  const p = legendRowPayload(it);
  p.eventtime = String(it.eventtime === null || it.eventtime === undefined ? '' : it.eventtime);
  return p;
}

const FP_UNIT = '';   // ASCII unit separator - cannot occur in a typed field
const FP_ROW = '';    // ASCII record separator
export function registryFingerprint(rows) {
  return (Array.isArray(rows) ? rows : [])
    .map(canonRegistryRow)
    .sort((a, b) => (a.value < b.value ? -1 : (a.value > b.value ? 1 : 0)))
    .map(c => LEGEND_PAYLOAD_COLUMNS.map(k => c[k]).concat([c.eventtime]).join(FP_UNIT))
    .join(FP_ROW);
}

// PUT /tables/map_split_registry/data/updates 페이로드 빌더 (순수 함수 — 하니스 검증 대상)
//
// ⚠️ This payload is written with `replace_map`, so it IS the map's whole plan. A row here
//    that belongs to another map key does not merely appear in the wrong place - it becomes
//    this map's DOE. Hence the `vocab` filter: an unclaimed vocabulary brush is never
//    written. This is the last line of defence and it is a pure function on purpose
//    (contracts/legend_map_scope/client_harness.mjs asserts it).
export function buildLegendRegistryUpdates(refTable, mapKey, legendArr, user, nowStr) {
  if (!refTable || !mapKey || !Array.isArray(legendArr)) return [];
  return legendArr
    .filter(item => item && item.vocab !== true)
    .filter(item => item && item.value !== undefined && item.value !== null && String(item.value).trim() !== '')
    .map(item => {
      const value = String(item.value).trim();
      const bk = buildSplitKey(refTable, mapKey, value);
      // ⚠️ THE COLUMN NAMES ARE SPELLED OUT AS A LITERAL, DELIBERATELY, and the values all
      //    come from the shared projection. Both halves of that sentence are load-bearing:
      //
      //    * literal KEYS, because `server/tests/test_install_product_tables.py` reads this
      //      object statically to prove every column written here is declared in
      //      product_tables.py. Building it with `Object.assign`/spread hides the names from
      //      that reader - the test then either fails outright or, worse, passes while
      //      checking fewer columns than the code writes.
      //    * shared VALUES, because the serialisation rules (stack tri-state, material
      //      lists as JSON arrays) must be identical to what the fingerprint and the vocab
      //      signature compare, or an edit is saved in a form the comparison cannot see.
      //
      //    The remaining risk - adding a column to `legendRowPayload` and forgetting it
      //    here - is closed by contracts/legend_map_scope, which asserts that every entry
      //    of LEGEND_PAYLOAD_COLUMNS actually appears in a built payload.
      const p = legendRowPayload(item);
      return {
        business_key_val: bk,
        updates: {
          split_key: bk,
          ref_table: refTable,
          map_key: mapKey,
          value: p.value,
          split_desc: p.split_desc,
          color: p.color,
          knobs: p.knobs,
          stack: p.stack,
          mat_1h: p.mat_1h,
          mat_mid: p.mat_mid,
          mat_top: p.mat_top,
          eventtime: nowStr
        },
        source_name: 'user',
        updated_by: user
      };
    });
}

// GET /tables/map_split_registry/data 응답 → legend 행 배열 (순수 함수 — 하니스 검증 대상)
// 셀 계약 준수: 각 컬럼은 {value, is_overwrite, priority_source, updated_by, ...} 객체로 읽는다.
// dedupeByValue=true(테이블 단위 조회)면 value 중복 시 updated_at 최신 행이 이긴다.
export function parseLegendRegistryRows(result, dedupeByValue) {
  const rows = [];
  if (result && Array.isArray(result.data)) {
    result.data.forEach(row => {
      const d = row.data || {};
      const value = d.value?.value;
      if (value === undefined || value === null || String(value).trim() === '') return;
      // ── zone 컬럼이 정본, `bands`는 폐기 모델의 읽기 폴백 ──────────────────
      // 폴백이 필요한 이유는 호의가 아니라 불변식이다: legend 저장은 `replace_map`이라
      // band 모델로 쓰인 계획을 읽지 못하면 그 맵을 여는 순간 화면이 비고, 다음 편집
      // 한 번이 그 계획을 **빈 집합으로 지운다**.
      // 그리고 세 구역으로 **표현할 수 없는** 배치는 추측하지 않는다 — 원문을 들고 와서
      // 저장을 막는다(`legacyReason`). 접어 넣고 replace_map으로 덮는 것이 바로
      // "화면은 멀쩡한데 값이 틀린" 결함이다.
      const zoneCols = {
        stack: d.stack?.value,
        mat_1h: parseJsonCol(d.mat_1h?.value, []),
        mat_mid: parseJsonCol(d.mat_mid?.value, []),
        mat_top: parseJsonCol(d.mat_top?.value, []),
      };
      const hasZone = String(zoneCols.stack ?? '').trim() !== ''
        || parseMaterialList(zoneCols.mat_1h).length > 0
        || parseMaterialList(zoneCols.mat_mid).length > 0
        || parseMaterialList(zoneCols.mat_top).length > 0;
      const legacy = hasZone ? [] : normalizeBands(parseJsonCol(d.bands?.value, []));
      const migrated = (legacy.length > 0) ? bandsToZones(legacy) : null;
      const zone = (migrated && migrated.ok)
        ? { stack: migrated.stack, mat_1h: migrated.mat_1h, mat_mid: migrated.mat_mid, mat_top: migrated.mat_top }
        : zoneCols;

      rows.push({
        value: String(value).trim(),
        desc: d.split_desc?.value != null ? String(d.split_desc.value) : '',
        color: d.color?.value != null && String(d.color.value) !== '' ? String(d.color.value) : '#6b7280',
        knobs: normalizeKnobs(parseJsonCol(d.knobs?.value, {})),
        stack: zone.stack,
        mat_1h: parseMaterialList(zone.mat_1h),
        mat_mid: parseMaterialList(zone.mat_mid),
        mat_top: parseMaterialList(zone.mat_top),
        legacyBands: (migrated && !migrated.ok) ? legacy : [],
        legacyReason: (migrated && !migrated.ok) ? migrated.reason : '',
        map_key: d.map_key?.value != null ? String(d.map_key.value) : '',
        // The registry has no updated_by COLUMN (crud.py's system_cols skips it, so it could
        // only ever be NULL). The platform already carries who touched the cell.
        updated_by: d.split_desc?.updated_by || d.value?.updated_by || 'system',
        eventtime: d.eventtime?.value != null ? String(d.eventtime.value) : '',
        updated_at: d.updated_at?.value || ''
      });
    });
  }
  if (!dedupeByValue) return rows;
  const byValue = new Map();
  rows.forEach(r => {
    const prev = byValue.get(r.value);
    if (!prev || String(r.updated_at) > String(prev.updated_at)) byValue.set(r.value, r);
  });
  return Array.from(byValue.values());
}

// push 대상 값 중 split 서술이 비어있는 값 추출 (순수 함수 — 하니스 검증 대상)
export function getMissingDescValues(pushedValues, legendArr) {
  return (pushedValues || []).filter(v => {
    const item = (legendArr || []).find(l => String(l.value) === String(v));
    return !item || !(item.desc || '').trim();
  });
}

export function formatLegendMetaText(meta) {
  if (!meta || (!meta.updated_by && !meta.updated_at)) return '서버 미저장';
  return `${meta.updated_by || 'system'} · ${meta.updated_at || ''}`;
}

// What a legend row LOOKS like, ignoring who last wrote it. `canonRegistryRow` is the
// one normal form in this file; `eventtime` is dropped because it is server bookkeeping,
// not something the user typed - comparing it would make every row look edited.
export function legendRowSignature(item) {
  const c = canonRegistryRow(item);
  // The SAME list the write payload is built from. Not a hand-picked subset: a field that
  // is saved but not signed here is a field whose edit is silently dropped from the save.
  return LEGEND_PAYLOAD_COLUMNS.map(k => c[k]).join(FP_UNIT);
}
