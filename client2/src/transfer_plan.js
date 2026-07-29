// ============================================================
// transfer_plan.js — 「2. Legend & DOE」 패널
//
//   원칙: **계획 = 지금 열어 편집 중인 그 맵.**
//   bonding_map을 열면 그게 본딩 계획이고, dt_map을 열면 그게 DT 계획이다.
//   stage는 열린 테이블에서 **유도**한다 (서버 config `stages.*.target_map.table`의 역인덱스).
//
//   화면은 세로 두 목록뿐이다:
//     ① DOE LIST  — legend 행 = DOE 행. 행 클릭 = 선택 + 브러시 + 펼침(한 동작).
//     ② 사용 자재 — 자재 ID별 롤업. 행 클릭 = 그 자재의 맵으로 이동(유일한 이동 허브).
//
//   ⭐ [M2.6] **이 파일은 서버에 쓰지 않는다.** 값 하나 = `map_split_registry` 행 하나 =
//      DOE 하나이고, 그 행의 유일한 기록자는 map_editor다(legend 저장 경로 그대로).
//      map_doe / map_doe_source는 폐기됐다. 이 파일은 `controller.getLegend()`로 읽고
//      `controller.updateLegendRow(value, patch)`로만 쓴다 — patch keys are the zone-model
//      row fields (`value`·`desc`·`color`·`stack`·`mat_1h`·`mat_mid`·`mat_top`·`knobs`).
//      저장·삭제·동시성 가드는 전부 그 한 경로에 있다(구현이 둘이면 반드시 갈라진다).
//
//   ⭐ ZONE MODEL — one number, three zones. (The band model — FROM→TO rows, `seq`
//      identity — is retired; `prevTo`/`bandsToZones` below only READ what it wrote.)
//      · STACK = the value's total layer count, stated by the user, never derived.
//      · 1H = layer 1 exactly · TOP = layer STACK exactly · MID = everything between:
//        (1H present ? 2 : 1) … (TOP present ? STACK−1 : STACK). The zones tile 1…STACK
//        by construction — overlap and gap are unstateable.
//      · STACK 0 = MARKER value (상태 표시 값, e.g. BASE FAIL): painted cells state a
//        condition, not a layer assignment. No zones (all render 해당 없음), zero demand,
//        absent from rollup ②; zone content on such a row is the V6 contradiction.
//        Blank STACK is different — blank means "not typed yet" and blocks via V5.
//      · The pure model lives in doe_bands.js; contracts/doe_band_rules pins it on both
//        sides (client harness now, server against the same vectors).
//
//   ⭐ 파생값은 저장하지 않는다.
//      구역 총 소요 = **칠한 셀 수 × 층 수** · 자재당 = **ceil(총 소요 / 자재 수)**.
//      저장하면 누가 한 칸 더 칠하는 순간 어긋난 채 남고 아무도 모른다. 그리고 식의 구현은
//      각각 **하나뿐**이다(저장 `ceil` / 표시 `round`로 갈려 DB 34 · 화면 33이던 결함).
//
//   ⚠️ 검증/경고 표시 일습(수량 부족 판정·교차 초과배정·validate 연동·신뢰 어휘 배지)은
//      사용자 지시로 보류다. 판정 로직은 지우지 않고 아래 §보류 구역에 그대로 두었다.
// ============================================================
import { API_BASE } from './config.js';
import { showToast } from './utils.js';
// The ONE TSV reader/writer, shared with the grid's Ctrl+C/Ctrl+V (client2/src/tsv.js).
import { parseTsv, serializeTsv } from './tsv.js';
// The pure zone model. Every derived number on this screen comes from here, so the panel
// cannot grow a second opinion about a figure it also displays.
import {
  ZONES, ZONE_LABEL, DOE_COLUMNS,
  stackState, midZone, zoneLayers, formatLayerRuns,
  parseMaterialList, serializeMaterialList, parseMaterialToken,
  validateZonePlan, materialRollupRows, remainingState,
  mapPastedGrid, planToGrid,
} from './doe_bands.js';
import './transfer_plan.css';

// [U6] The builtin stage list is DELETED. Stage declarations have exactly ONE source:
// GET /api/transfer-plan/stages (server config/transfer_plan_config.json). An
// unreachable/undeclaring server leaves S.stages empty and every table renders through
// the panel's existing degraded state ("일반 맵 (legend)") — never a client-side guess
// about which tables are plans.

// 소스 종류 → 자재 맵 테이블 폴백 (stage 역인덱스가 비었을 때만)
const SOURCE_TABLE_FALLBACK = { core: 'core_defect_map', tape: 'dt_map' };

// 자재 맵 위에 겹쳐 보는 단축 오버레이 후보
const SOURCE_OVERLAY_SUGGESTIONS = [
  { table: 'core_defect_map', label: 'defect' },
  { table: 'eds_fail_map', label: 'EDS fail' },
];

const S = {
  stages: [],          // [U6] served declarations only — empty until fetchStages answers
  stagesStatus: null,
  ctx: { table: '', mapKey: '', loaded: null, depth: 0, parent: null },
  // legend 미러 = DOE 그 자체
  //   { value, desc, color, knobs:[{k,v}], stack, mat_1h:[str], mat_mid:[str], mat_top:[str] }
  legendRows: [],
  blocks: [],                // 마지막 검증의 차단 목록 (①이 행 옆에, ②가 V3를 그린다)
  counts: {},                // value -> 칠한 셀 수
  activeBrush: '',
  summaries: new Map(),      // 풀 키 -> { status, data, error }
  matMapState: new Map(),    // "table|자재ID" -> true | false | null(미상)
  keyColumns: new Map(),     // table -> { ok, keyColumns, columnTypes }  ([7b] 선언 타입 동반)
  matSeq: 0,
  flash: new Set(),          // 1회성 하이라이트 대상 자재 ID
  navBusy: false,
};

const elp = {};
let controller = null;

// ── 유틸 ────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

// `YYYY-MM-DD H:MM:SS` → `HH:MM`.
// ⚠️ utils.getLocalTimeString은 **시(hour)를 0으로 채우지 않는다**(`... 7:04:09`).
//    고정 오프셋으로 잘라내면 오전 시간대에 `7:04:`가 찍힌다 — 분리자로 자를 것.
function hhmm(ts) {
  const t = String(ts || '').split(' ')[1] || '';
  const p = t.split(':');
  return p.length >= 2 ? `${p[0].padStart(2, '0')}:${p[1]}` : String(ts || '');
}

// 서버가 신뢰 불가를 null로 표현한다 → "미상". 0과 반드시 구분한다.
function fmtChips(v) {
  if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '<span class="tp-unknown-val">미상</span>';
  return String(Number(v));
}

// ── stage 유도 (열린 테이블 → stage) ────────────────────
function normalizeStage(s) {
  if (!s || typeof s !== 'object') return null;
  const id = String(s.name ?? s.stage ?? s.id ?? '').trim();
  if (!id) return null;
  const tm = (s.target_map && typeof s.target_map === 'object') ? s.target_map : {};
  return {
    id,
    name: `${id.toUpperCase()} PLAN`,
    targetTable: String(tm.table || ''),
    targetPreset: String(tm.preset || ''),
    targetKind: String(s.target_kind || ''),
    sourceKind: String(s.source_kind || ''),
    description: s.description || '',
  };
}

// **stage 선택 UI가 없는 이유**: 이 역인덱스가 곧 stage다.
function stageOfTable(table) {
  if (!table) return null;
  return S.stages.find(st => st.targetTable && st.targetTable === table) || null;
}

// 자재(소스) 맵 테이블 유도.
// 이 stage의 source_kind와 같은 target_kind를 가진 stage의 타깃 맵이 곧 자재 맵이다
// (bonding.source_kind=tape → dt.target_kind=tape → dt_map). 새 계약 없음 — 같은 config의 역인덱스.
//
// ⚠️ **조용한 추측 금지 (총괄 지시).** 역인덱스가 비면 하드코딩 폴백을 쓰는데,
//    그 사실을 반드시 드러낸다 — 콘솔 경고 + 자재 목록 하단에 `추정` 칩.
const warnedFallback = new Set();

function sourceTableOf(stage) {
  if (!stage) return { table: null, derived: null };
  const kin = S.stages.find(st => st.targetKind && st.targetKind === stage.sourceKind && st.targetTable);
  if (kin) return { table: kin.targetTable, derived: 'stage' };
  const fb = SOURCE_TABLE_FALLBACK[stage.sourceKind] || null;
  if (fb && !warnedFallback.has(stage.id)) {
    warnedFallback.add(stage.id);
    console.warn(
      `[Legend & DOE] stage '${stage.id}'(source_kind=${stage.sourceKind})의 자재 맵 테이블을 `
      + `stage 선언에서 유도하지 못해 하드코딩 폴백 '${fb}'을 사용합니다. `
      + `서버 transfer_plan_config에 소스 맵 테이블 명시 선언이 필요합니다.`);
  }
  return { table: fb, derived: fb ? 'fallback' : null };
}

// 테이블만 필요한 호출부용 얇은 래퍼
function sourceTableOfStage(stage) { return sourceTableOf(stage).table; }

// [U6] Two different absences (same discipline as the paint-rules fetch):
//   · 404/405 or an empty declaration → "no stages declared" — definite answer, stages = [].
//   · any other failure → "could not confirm" — keep the last KNOWN declaration (initially
//     empty) and retry on the next map-context change. Never a builtin list.
let stagesPromise = null;

async function fetchStages() {
  S.stagesStatus = 'loading';
  try {
    const res = await fetch(`${API_BASE}/api/transfer-plan/stages`);
    if (res.status === 404 || res.status === 405) {
      S.stages = []; S.stagesStatus = 'unsupported';
    } else if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    } else {
      const data = await res.json();
      const arr = Array.isArray(data) ? data : (Array.isArray(data.stages) ? data.stages : []);
      const stages = arr.map(normalizeStage).filter(Boolean);
      S.stages = stages;
      S.stagesStatus = stages.length > 0 ? 'ok' : 'unsupported';
    }
  } catch (e) {
    console.warn('[Legend & DOE] stages fetch failed — keeping last known declaration, will retry on next map switch:', e);
    S.stagesStatus = 'error';
  }
  renderAll();
}

function ensureStages() {
  if (!stagesPromise) stagesPromise = fetchStages();
  return stagesPromise;
}

// [U6] The declared stage TARGET tables, declaration order. map_editor's initial table
// pick consumes this instead of a builtin table-name list; waits for the one in-flight
// stages fetch. Unreachable endpoint ⇒ [] (no plan-table preference — honest absence).
export async function stageTargetTables() {
  await ensureStages();
  return S.stages.map(st => st.targetTable).filter(Boolean);
}

// ============================================================
// 구간(band) 산술 — 각 식의 구현은 **여기 하나뿐**이다.
// 표시와 저장이 같은 함수를 쓰지 않으면 화면과 DB가 반드시 갈라진다.
// ============================================================

// 끝 층 판정 — **3상태**이고, `to` 해석의 구현은 이 함수 하나뿐이다.
//
//   blank   : 없음 / null / '' / 공백뿐인 문자열 → 오류가 아니라 "아직 정하지 않음". 층 수 0.
//   ok      : 유한한 JSON 숫자, 또는 공백을 제거한 10진 정수 문자열. |값| ≤ 2^53.
//   invalid : 그 외 전부 — true / [] / {} / '0x10' / '1_0' / '7.5' / '1e3' / NaN / 2^53 초과.
//
// ⚠️ **`Number()` 강제 변환을 쓰지 않는다.** `Number('  ')===0` · `Number([])===0` ·
//    `Number('0x10')===16` · `Number(true)===1` 은 JS의 사고이고, 이식하면 버그가 스펙이 된다.
//    핵심은 값이 아니라 **구조**다: 0으로 읽히면 `prevTo` 걷기가 **거기서 멈추고**, null로
//    읽히면 **건너뛴다**. 그래서 `[10, '  ', 20]`이 화면에서는 20층, 서버에서는 10층이 됐다
//    (한 화면, 두 숫자). blank와 invalid를 걷기에서 **똑같이 건너뛰게** 두는 것이 강제 변환
//    흉내내기로 갈라지는 경우를 통째로 없애는 방법이다. 건너뛰되 **보이게** 한다(renderBand).
//
// 정본 벡터: `contracts/band_arithmetic/vectors.json` — 서버 `_band_to`와 같은 파일에 고정된다.
// 상수·정규식을 함수 안에 두는 것은 의도적이다: 계약 하네스가 이 함수를 **본문만 떼어** 평가하므로
// 규칙이 밖에 있으면 하네스가 검사하는 것과 앱이 실행하는 것이 갈린다.
function bandToState(b) {
  if (!b || typeof b !== 'object') return { value: null, state: 'invalid' };
  const raw = b.to;
  if (raw === null || raw === undefined) return { value: null, state: 'blank' };
  if (typeof raw === 'boolean') return { value: null, state: 'invalid' };
  const MAX_LAYER = 9007199254740992;                       // 2^53 — 계약의 max_layer
  if (typeof raw === 'string') {
    const s = raw.trim();
    if (s === '') return { value: null, state: 'blank' };
    if (!/^[+-]?[0-9]+$/.test(s)) return { value: null, state: 'invalid' };
    // 자릿수를 그대로 비교한다. `Number('9007199254740993')`은 검사가 돌기도 전에 2^53으로
    // 접혀 경계를 통과시킨다 — 문자열 경로에서는 BigInt로 **정확히** 판정할 수 있다.
    let big;
    try { big = BigInt(s); } catch (e) { return { value: null, state: 'invalid' }; }
    if (big > BigInt(MAX_LAYER) || big < -BigInt(MAX_LAYER)) return { value: null, state: 'invalid' };
    return { value: Number(big), state: 'ok' };
  }
  if (typeof raw === 'number') {
    if (!Number.isFinite(raw)) return { value: null, state: 'invalid' };     // NaN · ±Infinity
    if (Math.abs(raw) > MAX_LAYER) return { value: null, state: 'invalid' }; // 1e300 등
    return { value: Math.trunc(raw), state: 'ok' };                          // 0 방향 절사
  }
  return { value: null, state: 'invalid' };                                  // 배열 · 객체 등
}

// map_editor의 `normalizeBands`가 저장 정규형을 만들 때 같은 판정기를 쓴다. 정규화가 자기
// 나름의 `Number()`를 돌리면 **읽기-수정-쓰기가 조용히 값을 바꾼다** (실제로 '0x10'이 16으로
// 저장되고 있었다). 의존 방향은 map_editor → transfer_plan 하나뿐이라 순환이 생기지 않는다.
// ⚠️ `export function bandToState`로 합치지 말 것 — 계약 하네스가 `function NAME(`로 본문을
//    떼어 가므로, 선언 앞에 `export`가 붙으면 추출이 깨진다(하네스는 exit 2로 죽는다).
// ⚠️ `prevTo` is exported for the SAME reason: `doe_bands.js`'s `bandsToZones` needs the
//    retired model's backward walk to read plans that were written with it, and a
//    re-typed copy of "the previous band's `to`" would be a second implementation of a
//    rule `contracts/band_arithmetic/vectors.json` already fixes on both sides.
export { bandToState, prevTo };

// 앞 구간의 끝 층(없으면 0). **배열 위치**가 순서라는 규칙이 여기 한 줄에 들어 있다.
// `ok`인 구간만 걷기를 멈춘다 — blank도 invalid도 건너뛴다.
//
// ⚠️ THIS IS NOW A LEGACY READER, and it is the only band arithmetic left in this file.
//    The panel edits zones (STACK + 1H/MID/TOP), which have no walk at all - a zone's
//    layers come from STACK and the presence of its neighbours, not from its position.
//    What survives is the one job that still exists: reading `map_split_registry.bands`
//    rows that the retired model wrote, so opening such a map does not show an empty plan
//    and let the next `replace_map` delete it. The server still walks the same way, which
//    is why the shared vectors keep pinning it.
//    RETIRED WITH THE MODEL: `bandFrom` · `bandLayers` · `bandTotal` · `bandShare` ·
//    `validateBands` · `sortBands` · `nextBandSeq` · `bandTo`. Their coverage moved to
//    `zoneDemand`/`validateZonePlan` in contracts/doe_band_rules, not away.
function prevTo(bands, i) {
  for (let j = i - 1; j >= 0; j--) {
    const st = bandToState(bands[j]);
    if (st.state === 'ok') return st.value;
  }
  return 0;
}

function paintedOf(value) { return Number(S.counts[value] || 0); }

// 자재 ID는 **원문 그대로가 정체**다(저장 키에 그대로 들어간다).
// 아래 분해는 오직 ① 가용 조회 파라미터 ② 자재 맵 열기의 맵 키 조립에만 쓴다.
// 규칙은 `plan_store.material_identity` {compose:[lot,slot], separator:'_'} —
// **뒤에서부터** 가르므로 앞 필드가 나머지를 흡수한다(`LOT_A_01` → `LOT_A` + `01`).
// ⚠️ 같은 분리자를 쓰는 관례가 셋이다. `map_overlay.build_key_filters`는 반대 방향이다
//    (PRIMITIVES §2). 이쪽이 서버 `_split_material`과 맞아야 하는 이유는 하나다:
//    DOE 패널과 서버 validate가 **같은 자재로 같은 엔드포인트**(`source-summary`)를 묻기
//    때문에, 분해가 갈리면 한 화면에 두 개의 가용치가 생긴다.
//
// [못 풀면 **거부**한다 — 총괄 결정 2026-07-27, PRIMITIVES §2에 등록됨]
// 분리자가 없는 `ABC`, 한쪽이 비는 `ABC_`/`_01`은 `(lot, slot)`으로 풀 수 없다.
// 종전 폴백 `("ABC", "")`는 그대로 `?lot=ABC&slot=`를 조회해 **0을 확정 숫자로 표시**했는데,
// "조회 못 함"과 "잔여 0"이 합쳐지면 부족 경고가 조용히 죽는다(PRIMITIVES §7).
// 반환은 `{lot: null, slot: null}` — 빈 문자열이 아니라 null이라야 호출부가 검사를 잊지 못한다.
function splitMaterialId(id) {
  const s = String(id === null || id === undefined ? '' : id).trim();
  const i = s.lastIndexOf('_');
  if (i < 0) return { lot: null, slot: null };            // 분리자 부재 — 추측하지 않는다
  const lot = s.slice(0, i).trim();
  const slot = s.slice(i + 1).trim();
  if (!lot || !slot) return { lot: null, slot: null };    // 선행/후행 분리자로 한쪽이 빔
  return { lot, slot };
}

// ── legend 행 접근 (원천은 map_editor · 여기선 읽기 전용 미러) ──
function rowOf(value) {
  return S.legendRows.find(r => String(r.value) === String(value)) || null;
}

// DOE 변조의 **유일한 관문**. map_editor가 영속화(로컬 캐시 + 서버 registry 디바운스)를
// 맡으므로 이 파일에는 저장 코드가 없다.
//
// 🔴 EVERY edit path in this file goes through here, and there is no second one. The
//    two-table redesign adds a lot of edit paths (a STACK box and three material fields
//    per row, plus a paste that writes several rows at once); if any of them mutated the
//    mirror directly, the row would look edited and be dropped from the save, because
//    `updateLegendRow` is where `vocab` is cleared and the debounced save is scheduled.
//    `map_editor.reconcileVocabClaims` is the second net under this one - it re-derives
//    the claim from the row's own signature - but a bypass would still skip persistence.
function commitRow(value, patch) {
  const r = controller.updateLegendRow(value, patch);
  if (!r || !r.ok) { showToast((r && r.error) || 'DOE 저장 실패', 'warning'); return false; }
  return true;
}

// ── 자재 가용 — 풀 `(lot, slot, BIN)` 단위 ─────────────────────────────
//
// ⚠️ THE OLD KEY WAS THE RAW STRING AND THAT IS NOW A BUG SOURCE. `splitMaterialId`
//    splits on the last `_`, so `ADFE1H_01:1` used to yield slot `01:1` and the server was
//    asked about a slot that does not exist - a confident 0 for a material that is fine.
//    Identity comes from `parseMaterialToken` now, and the cache key is `materialPoolKey`,
//    which is the same key table ② groups rows by. One identity, one cache, one number.
//    (`splitMaterialId` survives for the map-key assembly path, which is a different
//    convention - PRIMITIVES §2 lists all three and they are not interchangeable.)

// The id used for map-existence probing and for opening the material's map. That path
// assembles a MAP KEY, which has no BIN in it: the BIN is a partition INSIDE one map.
function poolCacheId(pool) {
  return pool.scope === 'lot' ? String(pool.lot) : `${pool.lot}_${pool.slot}`;
}

function summaryKeyFor(pool) {
  const st = stageOfTable(S.ctx.table);
  return `${st ? st.id : S.ctx.table}::${pool.key}`;
}

async function getPoolSummary(pool, force = false) {
  const key = summaryKeyFor(pool);
  const cached = S.summaries.get(key);
  if (!force && cached && (cached.status === 'ok' || cached.status === 'loading')) {
    if (cached.promise) await cached.promise;
    return S.summaries.get(key);
  }
  const st = stageOfTable(S.ctx.table);
  const entry = { status: 'loading' };
  entry.promise = (async () => {
    const params = new URLSearchParams({
      stage: st ? st.id : '',
      lot: String(pool.lot),
      scope: pool.scope === 'lot' ? 'lot' : 'slot',
      bins: String(pool.bin),
    });
    if (pool.scope !== 'lot') params.set('slot', String(pool.slot));
    const res = await fetch(`${API_BASE}/api/transfer-plan/source-summary?${params.toString()}`);
    if (res.ok) {
      const data = await res.json();
      entry.status = 'ok';
      entry.data = (data && typeof data === 'object') ? data : {};
      return;
    }
    const body = await res.json().catch(() => null);
    if (isPlainNotFound(res.status, body)) { entry.status = 'unsupported'; return; }
    entry.status = 'error';
    entry.error = (body && typeof body.detail === 'string') ? body.detail : `HTTP ${res.status}`;
  })().catch(e => { entry.status = 'error'; entry.error = e && e.message ? e.message : String(e); });
  S.summaries.set(key, entry);
  await entry.promise;
  return entry;
}

// 서버 가용 응답의 **단일 해석 지점**. 반환: { status, value, reliable, reason }
//
// 가용량은 서버가 계산한다(SPEC §6.1). 클라는 읽기만 한다 — 두 번째 계산을 만들면 같은
// 숫자의 구현이 둘이 되고 반드시 갈라진다.
//
// 🔴 BIN 축은 **선언**이다. `data.bins.entries`에서 이 BIN의 항목을 찾는다:
//      status ok         -> 그 항목의 remaining
//      status bin_absent -> "이 맵에 이 BIN이 없다" (0이 아니다 — remainingState가 구분한다)
//      status unknown    -> 절단 등으로 수를 신뢰할 수 없다
//      항목이 없음/축 미구성 -> 미상. **chips.remaining으로 대체하지 않는다** — 그것은 이
//      자재 전체(모든 BIN)의 수이고, 한 BIN의 가용으로 쓰면 조용히 과대 보고가 된다.
function availabilityOfPool(pool) {
  // [7c] 반환 형태에 `bound`가 **항상** 있다(없으면 null). 어떤 갈래에서만 빠지면 소비자가
  // `undefined`와 "상한 없음"을 구분하려 들게 되고, 그 순간 판정이 둘로 갈린다.
  const entry = S.summaries.get(summaryKeyFor(pool));
  if (!entry) return { status: null, value: null, reliable: false, bound: null, reason: '아직 조회하지 않음' };
  if (entry.status !== 'ok') {
    return {
      status: entry.status, value: null, reliable: false, bound: null,
      reason: entry.status === 'loading' ? '조회 중'
        : (entry.status === 'unsupported' ? '이 서버는 가용 집계를 제공하지 않습니다'
          : (entry.error || '가용 조회 실패')),
    };
  }
  const data = entry.data || {};
  const degraded = (Array.isArray(data.warnings) ? data.warnings : [])
    .map(w => String((w && (w.type || w.code)) || w))
    .filter(t => t === 'source_degraded' || t === 'availability_unreliable');

  const block = data.bins;
  if (!block || typeof block !== 'object' || block.axis !== 'connected' || !Array.isArray(block.entries)) {
    const why = (block && block.detail) ? String(block.detail) : 'BIN별 가용을 서버가 주지 않았습니다';
    return { status: 'bins_unavailable', value: null, reliable: false, bound: null, reason: why };
  }
  const hit = block.entries.find(e => e && Number(e.bin) === Number(pool.bin));
  if (!hit) {
    return { status: 'bin_absent', value: null, reliable: false, bound: null, reason: '이 맵에 해당 BIN이 없습니다 — 소진된 것이 아닙니다.' };
  }
  if (hit.status === 'bin_absent') {
    return { status: 'bin_absent', value: null, reliable: false, bound: null, reason: hit.reason || '이 맵에 해당 BIN이 없습니다 — 소진된 것이 아닙니다.' };
  }
  const reasons = [];
  if (hit.reliable !== true) reasons.push(hit.reason || '서버 판정: 이 BIN의 잔여 신뢰 불가');
  if (hit.remaining === null || hit.remaining === undefined) reasons.push('서버가 잔여 값을 주지 않았습니다');
  if (degraded.length > 0) reasons.push(`소스 강등(${degraded.join(', ')})`);
  // [7c] 선언된 미추적 소비 — 사이트가 "전사 기록이 없다"고 선언한 상태(SPEC §6.2-bis).
  // 미상이 아니라 **상한**을 아는 상태다. 상한이 있으면 아래 reason은 강등 문구가 아니라
  // 상한의 근거로 읽힌다 — 그래서 문구를 따로 세운다.
  const bound = untrackedBoundOf(hit);
  return {
    status: 'ok',
    value: (hit.remaining === null || hit.remaining === undefined) ? null : Number(hit.remaining),
    reliable: reasons.length === 0,
    bound,
    reason: bound !== null ? UNTRACKED_REASON : reasons.join(' · '),
  };
}

// ── [7c] 선언된 미추적 소비 (transfer_log: "none") ───────────────────────────
//
// 서버가 `used_set`을 통째로 갖지 못한 **선언된** 상태다. 감산항 하나가 빠졌으므로 값은
// 커질 수만 있고, 그래서 서버가 주는 `remaining_upper_bound`는 진짜 상한이다(SPEC §6.2-bis).
//
// 🔴 **상한은 서버가 계산한다. 여기서 총−fail을 다시 계산하지 않는다** — 같은 수의 구현이
//    둘이 되면 반드시 갈라진다(저장 `ceil` / 표시 `round`로 DB 34 · 화면 33이던 사건).
//    이 함수의 유일한 숫자 출처는 `remaining_upper_bound` 필드 그 자체다.
//
// 🔴 **선언은 정확히 boolean `true`뿐이다.** `'true'`·`1`·`'none'`·`'None'`·`null`·`''`은
//    전부 선언이 아니라 사고성 미상으로 남는다. 서버가 config에서 `"none"` **문자열만**
//    선언으로 받는 것과 같은 규율이고(오타가 지식으로 승격되면 안 된다), 클라가 느슨하게
//    받으면 그 엄격함이 이 화면에서 무효가 된다.
const UNTRACKED_REASON = '전사(소모) 기록이 없다고 선언된 사이트입니다 — 기전사 미차감이라 실제 잔여는 이 값 이하입니다.';

function untrackedBoundOf(entry) {
  if (!entry || typeof entry !== 'object') return null;
  if (entry.transfer_untracked !== true) return null;
  const n = entry.remaining_upper_bound;
  if (typeof n !== 'number' || !Number.isFinite(n)) return null;
  return n;
}

// 상한의 표기. **맨숫자로 찍지 않는다** — 데이터가 갖지 못한 정밀도를 주장하게 된다.
function boundText(bound) {
  if (bound === null || bound === undefined || typeof bound !== 'number' || !Number.isFinite(bound)) return '';
  return `≤${bound}`;
}

function isPlainNotFound(status, body) {
  return (status === 405) || (status === 404 && (!body || body.detail === 'Not Found'));
}

// ── 자재 맵 존재 여부 ───────────────────────────────────
function matMapCacheKey(table, id) { return `${table}|${id}`; }

// [7b] 자재 ID로 맵 키 값을 만든다. 값은 **선언 타입으로 캐노니컬화**해서 내보낸다 —
// number 선언 slot에 저장된 1을 자재 토큰의 '01'로 조회하면 맵이 있는데도 "맵 없음"이
// 뜬다(운영 실증). 캐노니컬화 구현은 map_editor 하나뿐이고 여기서는 컨트롤러로 받아
// 쓴다(이 파일에 사본을 두면 맵 정체성에 대한 의견이 둘이 된다).
async function materialKeySpec(table) {
  let spec = S.keyColumns.get(table);
  if (!spec) {
    spec = (controller && controller.fetchMapKeySpec)
      ? await controller.fetchMapKeySpec(table)
      : { ok: false, keyColumns: [], columnTypes: {} };
    S.keyColumns.set(table, spec || { ok: false, keyColumns: [], columnTypes: {} });
  }
  return S.keyColumns.get(table);
}

function canonKey(value, colType) {
  const fn = controller && controller.canonicalKeyValue;
  if (!fn) return (value === null || value === undefined) ? value : String(value).trim();
  return fn(value, colType);
}

async function materialMetaValues(table, id) {
  const spec = await materialKeySpec(table);
  const cols = (spec && spec.keyColumns) || [];
  const types = (spec && spec.columnTypes) || {};
  const out = {};
  if (cols.length === 0) return out;
  // 맵 키 컬럼이 하나면 자재 ID **원문이 곧 맵 키**다 — 분해 해석이 끼지 않는다.
  // (캐노니컬화는 해석이 아니라 같은 값의 표기 통일이므로 여기서도 적용한다.)
  if (cols.length === 1) { out[cols[0]] = String(canonKey(String(id), types[cols[0]]) ?? id); return out; }
  const { lot, slot } = splitMaterialId(id);
  // 해석 실패면 **빈 필터**를 돌려준다 → `probeMapExists`가 null(=미상)을 준다.
  // 여기서 억지로 조회하면 "맵 없음"이 나오는데, 그건 "확인 못 했다"의 위장이다.
  if (lot === null || slot === null) return out;
  out[cols[0]] = String(canonKey(lot, types[cols[0]]) ?? lot);
  out[cols[1]] = String(canonKey(slot, types[cols[1]]) ?? slot);
  return out;
}

async function probeMaterialMap(table, id, force = false) {
  const ck = matMapCacheKey(table, id);
  if (!force && S.matMapState.has(ck)) return S.matMapState.get(ck);
  const metaValues = await materialMetaValues(table, id);
  const exists = (controller && controller.probeMapExists)
    ? await controller.probeMapExists(table, metaValues) : null;
  S.matMapState.set(ck, exists);
  return exists;
}

// ── 렌더: 계획 헤더 ─────────────────────────────────────
//
// 저장 상태는 map_editor가 판정한다(getPlanSaveState) — 저장하는 쪽과 표시하는 쪽이
// 각자 판단하면 "저장됨"이 실패를 덮는다.
function renderPlanHead() {
  const box = elp.head;
  if (!box) return;
  const st = stageOfTable(S.ctx.table);
  const child = S.ctx.depth > 0;
  // [U6] "일반 맵" can also mean "stage declarations were unreachable" — say so in the
  // tooltip instead of silently degrading (no new control; retried on next map switch).
  const noStageTitle = S.stagesStatus === 'error'
    ? ' title="전사 stage 선언을 조회하지 못했습니다 — 계획 기능이 잠시 비활성일 수 있습니다 (맵 전환 시 재시도)."'
    : '';
  const stageBadge = child
    ? '<span class="tp-stage-badge material">자재 맵</span>'
    : (st ? `<span class="tp-stage-badge">${esc(st.name)}</span>`
          : `<span class="tp-stage-badge none"${noStageTitle}>일반 맵 (legend)</span>`);

  // ── 저장 상태. 자동 저장이 없으므로 화면이 이것을 말해야 한다. ───────────────
  //
  // 🔴 검증(V1–V5)은 여기 없다 — 미완성 계획도 그대로 저장되므로(사용자 지시 2026-07-28)
  //    "차단"과 "저장 가능"을 구분할 필요가 사라졌다. 규칙은 고칠 자리(행 옆)에만 뜬다.
  //
  //   ① 저장이 데이터를 지운다  → 막는다. **무엇이 사라지는지**를 말한다(무효가 아니다).
  //   ② 저장 안 된 편집이 있다  → [⚡ Push]가 저장한다는 것과, **탭을 닫아도 남는다**는 것을
  //                              함께 말한다. 후자를 빼면 사람은 불안해서 아무 때나 Push하게
  //                              되고, 그게 습관이 되면 초안의 의미가 사라진다.
  //   ③ 저장됨               → 시각.
  const ss = (controller && controller.getPlanSaveState) ? controller.getPlanSaveState() : { status: 'idle' };
  const dirtyTail = '<br><br>편집은 이 브라우저에 초안으로 보관됩니다 — <b>탭을 닫거나 새로고침해도 사라지지 않습니다.</b> 서버에는 [⚡ Push Map Data]가 맵과 함께 올립니다.';
  let savedChip;
  if (ss.status === 'conflict') {
    savedChip = '<span class="tp-chip bad" title="다른 사람이 이 계획을 바꿨습니다. 지금 저장하면 그 편집이 지워지므로 저장을 막았습니다 — 맵을 다시 불러오십시오.">⚠ 다른 사람이 변경함 · 다시 불러오기</span>';
  } else if (ss.status === 'zone-columns-missing') {
    savedChip = '<span class="tp-chip bad" title="서버 DOE 저장소에 STACK·1H·MID·TOP 컬럼이 아직 없습니다. 지금 저장하면 그 컬럼들이 버려진 채 계획 전체가 교체되어 층 구조가 사라집니다 — 그래서 저장하지 않았습니다. 계획이 틀려서가 아닙니다. 서버가 갱신되면 자동으로 다시 시도합니다.'
      + esc(dirtyTail.replace(/<[^>]+>/g, '')) + '">⚠ 저장하면 층 구조가 사라짐 · 보류</span>';
  } else if (ss.status === 'legacy-unreadable') {
    savedChip = `<span class="tp-chip bad" title="지금 저장하면 폐기된 구간 배치가 3구역으로 뭉개진 채 서버 원본을 덮어, 지금 남아 있는 정보가 사라집니다 — 그래서 저장하지 않았습니다. 계획이 틀려서가 아닙니다.&#10;${esc(ss.error || '')}">⚠ 저장하면 구간 정보가 사라짐 · 보류</span>`;
  } else if (ss.status === 'unknown-server-state') {
    savedChip = `<span class="tp-chip warn" title="${esc(ss.error || '서버 조회 실패')}">⚠ 서버 상태 미확인 · 저장 보류</span>`;
  } else if (ss.status === 'error') {
    savedChip = `<span class="tp-chip bad" title="${esc(ss.error || '')}">⚠ 서버 저장 실패</span>`;
  } else if (ss.dirty) {
    savedChip = `<span class="tp-chip warn" title="아직 서버에 올라가지 않은 편집이 있습니다.${dirtyTail}">● 저장 안 됨 · [⚡ Push]로 저장</span>`;
  } else if (ss.status === 'ok' && ss.at) {
    savedChip = `<span class="tp-chip ok" title="맵과 함께 서버에 저장됐습니다.">저장됨 ${esc(hhmm(ss.at))}</span>`;
  } else {
    savedChip = '<span class="tp-chip dim" title="편집하면 초안으로 보관되고, [⚡ Push Map Data]가 맵과 함께 서버에 올립니다.">변경 없음</span>';
  }
  const idTxt = S.ctx.table ? `${S.ctx.table}${S.ctx.mapKey ? ' · ' + S.ctx.mapKey : ''}` : '맵 미로드';

  box.innerHTML = `
    <div class="tp-head-l1">
      ${stageBadge}
      <span class="tp-chip mono">${esc(idTxt)}</span>
      ${savedChip}
    </div>
    <div class="tp-head-l2">
      ${child && S.ctx.parent ? `<span>상위 <b>${esc(S.ctx.parent)}</b>에서 이동</span>` : ''}
      ${st && !child ? `<span>자재 <b>${esc(st.sourceKind || '-')}</b></span>` : ''}
      <span class="tp-chip dim" style="margin-left:auto;">stage는 열린 테이블에서 유도됨</span>
    </div>`;
}

// ============================================================
// ① 값 정의 — 한 행 = 두 줄
//
// WHY TWO LINES. Seven fields cannot share one visual line here. The sidebar's usable
// width is 405px and the measured minimum of the seven cells is 511px (1H 103 · MID 172 ·
// TOP 96 · COLOR 22 · VALUE 40 · STACK 34 · 삭제 16 · gaps 28) - 106px short before DESC
// gets a single pixel. So line 1 is identity (COLOR·VALUE·STACK·DESC·칠함) and line 2 is
// structure (1H·MID·TOP).
//
// 🔴 AND THAT IS WHY THE PASTE CONTRACT IS AN INDEX, NOT A DIRECTION. "the cell to the
//    right" and "the next contract column" are different things in a two-line layout. The
//    contract lives in `DOE_COLUMNS`; the layout is free to change without touching it.
//
// 칸의 세 상태, and they must not look alike:
//   · 비움      — 점선. 채울 수 있다. 치면 층 구조가 바뀐다.
//   · 해당 없음 — 실선 + 빗금 + `disabled`. **구조상 존재하지 않는 층**이다. The cell states
//                 its own precondition IN TEXT ("STACK을 2 이상으로"), not in a `title`:
//                 a tooltip is invisible to keyboard and touch users, who are exactly the
//                 people most likely to get stuck. And we do NOT raise STACK for them - a
//                 screen that edits a number nobody typed is the defect class this project
//                 has spent the week removing.
//   · 채움      — 앞에 계산된 층 범위가 조용히 붙는다 (파생값이지 입력이 아니다).
// ============================================================

// The zone cell's chip overlay and the raw textarea are the SAME element stack, swapped by
// `:focus-within` in CSS. Never by replacing the DOM: replacing it while the user is in the
// field destroys the caret and the selection, and the reactive "MID dies when STACK
// becomes 1" behaviour fires on every keystroke.
function zoneCellHtml(row, zone) {
  const st = stackState(row);
  const tokens = parseMaterialList(row[zone]);
  const na = zoneIsInapplicable(row, zone);
  const raw = esc(serializeMaterialList(tokens));

  if (na.inapplicable) {
    // `disabled` gives us "no caret, no focus ring, no tab order" without swapping the
    // node out. The reason is rendered as TEXT inside the cell.
    return `<span class="tp-zc na" data-zone="${zone}">
      <textarea class="tp-zc-raw" data-zone="${zone}" disabled></textarea>
      <span class="tp-zc-chips" aria-hidden="true">
        ${na.layers === 0 ? '<span class="tp-lr zero">0층</span>' : ''}
        <span class="tp-na-t">해당 없음 · ${esc(na.fix)}</span>
      </span></span>`;
  }

  const layers = zoneLayers(row, zone) || [];
  const lr = (st.state === 'ok' && layers.length > 0)
    ? `<span class="tp-lr">${esc(formatLayerRuns(layers).replace(/층/g, ''))}</span>` : '';
  const chips = tokens.map(t => materialChipHtml(t)).join('');
  const empty = tokens.length === 0;
  const blocked = empty && zone === 'mat_mid' && st.state === 'ok' && midZone(row).size > 0;

  return `<span class="tp-zc${empty ? ' empty' : ''}${blocked ? ' bad' : ''}" data-zone="${zone}">
    <textarea class="tp-zc-raw" data-zone="${zone}" placeholder="${esc(ZONE_PLACEHOLDER[zone])}">${raw}</textarea>
    <span class="tp-zc-chips" aria-hidden="true">${lr}${
      empty ? `<span class="tp-emp${blocked ? ' bad' : ''}">${blocked ? '— 비어 있음' : '— 비움'}</span>` : chips
    }</span></span>`;
}

// 비면 어떻게 되는지를 placeholder가 말한다 — 이것도 title이 아니라 보이는 글자다.
const ZONE_PLACEHOLDER = {
  mat_1h: '비우면 MID가 1층부터',
  mat_mid: '자재',
  mat_top: '비우면 MID가 STACK까지',
};

// A zone whose layer does not exist. Derived from STACK and the other two zones, so it
// changes live as the user types - which is how the screen SHOWS that the rule is
// conditional instead of explaining it in a footnote.
//   · STACK 1 이고 MID가 그 1층을 잡았다        -> 1H·TOP은 들어갈 층이 없다
//   · 1H와 TOP이 STACK의 두 끝을 다 가져갔다    -> MID 구역이 0층이다
// Returns { inapplicable, layers, fix } - `fix` is the visible instruction.
function zoneIsInapplicable(row, zone) {
  const st = stackState(row);
  // A marker row (STACK 0 = 상태 표시 값) has no layers at all, so every zone renders as
  // 해당 없음 — same treatment as a structurally absent layer, because that is what it is.
  // The fix text names the precondition, visibly, like the other na cells.
  if (st.state === 'marker') return { inapplicable: true, layers: null, fix: 'STACK 0 = 상태 표시 값 (층 없음)' };
  if (st.state !== 'ok') return { inapplicable: false, layers: null, fix: '' };
  const has = z => parseMaterialList(row[z]).length > 0;
  if (zone === 'mat_mid') {
    const z = midZone(row);
    if (z.size === 0) return { inapplicable: true, layers: 0, fix: `STACK ${st.value}의 층을 1H·TOP이 모두 가져갔습니다` };
    return { inapplicable: false, layers: z.size, fix: '' };
  }
  // 1H / TOP only vanish at STACK 1, and only when MID already holds the single layer.
  // At STACK 1 with 1H+TOP and no MID the answer is NOT "inapplicable" - it is V2, a real
  // conflict the user has to resolve, and hiding one of the two cells would hide the fix.
  if (st.value === 1 && has('mat_mid')) {
    return { inapplicable: true, layers: null, fix: 'STACK을 2 이상으로' };
  }
  return { inapplicable: false, layers: null, fix: '' };
}

// A material chip. `_✱` marks where the slot WOULD be, so a vertical scan splits at the
// same character position; BIN is drawn even at its default 1 so an unspoken default never
// disappears from the screen.
//
// ⚠️ 칩은 그림이다. 원문은 `MID1`이고 저장되는 것도 `MID1`이다 - `MID1_✱:1`을 저장하면
//    `_✱`라는 슬롯을 가진 로트가 생긴다. 복사도 원문만 나간다(planRowToRecord).
function materialChipHtml(rawToken) {
  const t = parseMaterialToken(rawToken);
  if (!t.ok) {
    return `<span class="tp-mc bad" title="${esc(t.reason)}">${esc(rawToken)}</span>`;
  }
  const lotWide = t.scope === 'lot';
  return `<span class="tp-mc${lotWide ? ' lotwide' : ''}"><span class="lot">${esc(t.lot)}</span>${
    lotWide ? '<span class="st">_✱</span>' : `<span class="lot">_${esc(t.slot)}</span>`
  }<span class="bn${t.bin !== 1 ? ' hi' : ''}">:${t.bin}</span></span>`;
}

// The plan as the pure model sees it. ONE conversion point: every derived number on this
// screen comes from `doe_bands.js` applied to this object, so the panel cannot grow a
// second opinion about a value it also displays.
function planOf() {
  return { values: S.legendRows };
}

function renderDoeList() {
  const box = elp.list;
  if (!box) return;
  const st = stageOfTable(S.ctx.table);
  const planMode = !!st && S.ctx.depth === 0;

  if (!S.ctx.table) {
    box.innerHTML = '<div class="tp-empty">좌측 「1. Map Search &amp; Load」에서 맵을 열면 그 맵의 legend(= DOE)가 여기 표시됩니다.</div>';
    return;
  }
  if (S.legendRows.length === 0) {
    box.innerHTML = '<div class="tp-empty">정의된 값이 없습니다. 우상단 [+ 값]으로 만드세요.</div>';
    return;
  }

  const v = planMode ? validateZonePlan(planOf()) : { ok: true, blocks: [], warns: [] };
  S.blocks = v.blocks;
  const byValue = new Map();
  v.blocks.forEach(b => {
    if (!b.value) return;
    if (!byValue.has(b.value)) byValue.set(b.value, []);
    byValue.get(b.value).push(b);
  });

  // 머리줄 글자 = **엑셀에 적을 열 이름 그대로**. 이름으로 맞추기가 되려면 화면이 보여 주는
  // 단어와 파서가 찾는 단어가 같아야 하므로, 둘 다 DOE_COLUMNS에서 나온다.
  const head = planMode ? `
    <div class="tp-ch-row l1">
      <span class="drv" title="색은 앱이 소유합니다 — 엑셀 열 계약에 없습니다(붙여넣기·복사 모두 제외). 엑셀의 셀 채우기는 클립보드 텍스트로 이동하지 않습니다.">COLOR*</span>
      <span>${esc(colHeader('value'))}</span>
      <span class="r">${esc(colHeader('stack'))}</span><span>${esc(colHeader('desc'))}</span>
      <span class="r drv" title="맵에서 이 값으로 칠해진 셀 수 — 파생값이라 엑셀 열 계약에 없습니다(붙여넣기·복사 모두 제외).">칠함*</span><span></span>
    </div>
    <div class="tp-ch-row l2">
      <span>${esc(colHeader('mat_1h'))} — 1층</span>
      <span>${esc(colHeader('mat_mid'))} — 그 사이 (구역 있으면 필수)</span>
      <span>${esc(colHeader('mat_top'))} — STACK층</span>
    </div>` : '';

  box.innerHTML = head + S.legendRows.map(row => {
    const val = String(row.value);
    const blocks = byValue.get(val) || [];
    const legacy = Array.isArray(row.legacyBands) && row.legacyBands.length > 0;
    const zoneBad = new Set(blocks.map(b => b.zone).filter(Boolean));
    const l2 = planMode ? `<div class="tp-v-l2">${
      ZONES.map(z => zoneCellHtml(row, z)).join('')
    }</div>` : '';
    const msgs = blocks.map(b => `<div class="tp-blk"><span class="rid">${esc(b.rule)}</span><span>${esc(b.message)}</span></div>`).join('')
      + (legacy ? `<div class="tp-blk"><span class="rid">폐기</span><span>${esc(row.legacyReason)} — 이 값의 STACK·구역을 직접 채우면 저장이 풀립니다. (원래 구간: ${
        esc(row.legacyBands.map(b => b.to).join(' / '))})</span></div>` : '');
    const stSt = stackState(row);
    return `<div class="tp-vrow${blocks.length || legacy ? ' bad' : ''}" data-v="${esc(val)}">
      <div class="tp-v-l1">
        <input type="color" class="tp-sw" data-f="color" value="${esc(row.color || '#6b7280')}" />
        <input class="tp-gi vin" data-f="value" value="${esc(val)}" />
        ${planMode ? `<input class="tp-gi stk${(stSt.state === 'ok' || stSt.state === 'marker') ? '' : ' bad'}" data-f="stack" inputmode="numeric"
          value="${esc(row.stack === null || row.stack === undefined ? '' : String(row.stack))}" placeholder="총 층수" />` : ''}
        <input class="tp-gi din" data-f="desc" value="${esc(row.desc || '')}" placeholder="이 값이 무슨 조건인지" />
        <span class="tp-pnt" data-count-for="${esc(val)}">${paintedOf(val)}</span>
        <button type="button" class="tp-del" title="이 값 삭제 (격자에서 이 값이 지워지고 층 구조도 함께 사라집니다)">🗑</button>
      </div>
      ${l2}${msgs}
    </div>`;
  }).join('') + (planMode ? `
    <div class="tp-foot-note">
      <b>STACK</b>=총 층수 · <b>STACK 0 = 상태 표시 값</b>(예: BASE FAIL — 층·자재·소요 없음) ·
      <b>MID 구역 = (1H 있으면 2, 없으면 1) … (TOP 있으면 STACK−1, 없으면 STACK)</b> ·
      <b>구역이 0층이면 MID는 필요 없습니다</b><br>
      자재는 줄바꿈 또는 쉼표로 나눔 · <code>lot_slot:BIN</code> · <code>lot:BIN</code>=로트 전체 · BIN 생략=1
    </div>` : '');

  bindDoeList(box, planMode);
}

function colHeader(id) {
  const c = DOE_COLUMNS.find(x => x.id === id);
  return c ? c.header : id;
}

// ── 반응성. DOM을 갈아끼우지 않고 클래스만 토글한다. ──────────────────────────
//
// STACK·1H·TOP 중 하나가 바뀌면 같은 행의 다른 칸이 입력 가능 ↔ 불가능으로 바뀐다. If this
// ran through `renderDoeList()` the user would lose the caret on every keystroke, so it
// patches the three zone cells of ONE row in place. The model is not touched here - that
// happens on `change` through `commitRow`, the single gate.
function refreshRowZones(node, row) {
  ZONES.forEach(z => {
    const cell = node.querySelector(`.tp-zc[data-zone="${z}"]`);
    if (!cell) return;
    const ta = cell.querySelector('.tp-zc-raw');
    const na = zoneIsInapplicable(row, z);
    const st = stackState(row);
    const tokens = parseMaterialList(row[z]);
    cell.classList.toggle('na', na.inapplicable);
    cell.classList.toggle('empty', !na.inapplicable && tokens.length === 0);
    const blocked = tokens.length === 0 && z === 'mat_mid' && st.state === 'ok' && midZone(row).size > 0;
    cell.classList.toggle('bad', blocked);
    if (ta) ta.disabled = na.inapplicable;
    const chips = cell.querySelector('.tp-zc-chips');
    if (!chips) return;
    if (na.inapplicable) {
      chips.innerHTML = `${na.layers === 0 ? '<span class="tp-lr zero">0층</span>' : ''}<span class="tp-na-t">해당 없음 · ${esc(na.fix)}</span>`;
      return;
    }
    const layers = zoneLayers(row, z) || [];
    const lr = (st.state === 'ok' && layers.length > 0)
      ? `<span class="tp-lr">${esc(formatLayerRuns(layers).replace(/층/g, ''))}</span>` : '';
    chips.innerHTML = lr + (tokens.length === 0
      ? `<span class="tp-emp${blocked ? ' bad' : ''}">${blocked ? '— 비어 있음' : '— 비움'}</span>`
      : tokens.map(t => materialChipHtml(t)).join(''));
  });
}

// The row the panel considers "selected" - it is whatever has focus. No checkbox column,
// no selection mode, no new control: selection IS focus.
function focusedRowValue() {
  const el = document.activeElement;
  if (!el || !elp.list || !elp.list.contains(el)) return '';
  const row = el.closest('.tp-vrow');
  return row ? row.dataset.v : '';
}
function focusedColumnId() {
  const el = document.activeElement;
  if (!el || !elp.list || !elp.list.contains(el)) return DOE_COLUMNS[0].id;
  const z = el.getAttribute && el.getAttribute('data-zone');
  if (z) return z;
  const f = el.getAttribute && el.getAttribute('data-f');
  return f || DOE_COLUMNS[0].id;
}

function bindDoeList(box, planMode) {
  box.querySelectorAll('.tp-vrow').forEach(node => {
    const v = node.dataset.v;

    // 행을 만지면 곧 브러시. 클릭 = 선택 + 브러시 (펼침은 없다 — 접히는 것이 없다).
    node.addEventListener('mousedown', () => {
      if (controller && controller.setBrush) { controller.setBrush(v); S.activeBrush = v; }
    });

    node.querySelector('[data-f="color"]').addEventListener('change', e => {
      commitRow(v, { color: e.target.value });
    });
    node.querySelector('[data-f="desc"]').addEventListener('change', e => {
      commitRow(v, { desc: e.target.value.trim() });
    });

    const valIn = node.querySelector('[data-f="value"]');
    valIn.addEventListener('change', () => {
      const nv = valIn.value.trim();
      if (!nv || nv === v) { valIn.value = v; return; }
      const r = controller.updateLegendRow(v, { value: nv });
      if (!r.ok) { showToast(r.error, 'warning'); valIn.value = v; return; }
      // 값 이름이 바뀌어도 층 구조는 같은 행에 그대로 붙어 있다 — zone 모델에는 값을 이름으로
      // 가리키는 참조가 없으므로(구간 모델의 `values[]`가 사라졌다) 개명 전파가 필요 없다.
    });

    node.querySelector('.tp-del').addEventListener('click', () => {
      if (!confirm(`값 '${v}'을(를) 삭제할까요? (격자에서 이 값이 지워지고 층 구조도 함께 사라집니다)`)) return;
      const r = controller.deleteLegendRow(v);
      if (!r.ok) showToast(r.error, 'warning');
    });

    if (!planMode) return;

    const stk = node.querySelector('[data-f="stack"]');
    if (stk) {
      // `input` -> 화면만 (반응성) · `change` -> 모델. Two events, two jobs: the live one
      // never persists and the persisting one never runs per keystroke.
      stk.addEventListener('input', () => {
        const draft = { ...rowOf(v), stack: stk.value };
        const s = stackState(draft).state;
        stk.classList.toggle('bad', s !== 'ok' && s !== 'marker');   // 0 = marker, not an error
        refreshRowZones(node, draft);
      });
      stk.addEventListener('change', () => {
        // 입력도 **같은 판정기**를 통과한다. 읽을 수 없는 값은 거부하지 않고 원문 그대로
        // 저장한다 — 그래야 패널이 무엇을 고치라고 말할 수 있고, V5가 그것을 말한다.
        commitRow(v, { stack: stk.value.trim() });
      });
    }

    node.querySelectorAll('.tp-zc-raw').forEach(ta => {
      const zone = ta.dataset.zone;
      ta.addEventListener('input', () => {
        const draft = { ...rowOf(v) };
        draft[zone] = parseMaterialList(ta.value);
        refreshRowZones(node, draft);
      });
      ta.addEventListener('change', () => {
        // `parseMaterialList` accepts newline OR comma and is the SAME function the
        // storage layer normalizes with, so the material count on screen and the
        // denominator of `ceil(total / n)` in the save cannot be two different numbers.
        commitRow(v, { [zone]: parseMaterialList(ta.value) });
      });
    });
  });
}

// ============================================================
// ② 자재 롤업 — 전부 파생. 여기서 입력받는 것은 없다.
//
// 행의 정체는 **풀** `(lot, slot, BIN)`이지 자재 이름이 아니다. A DT map is not one pool:
// it is partitioned by BIN, and two values can draw different BINs from the same map
// without competing. Collapse BIN and 잔여 comes out low with no visible cause.
//
// 사용 is a SUFFICIENCY CHECK, NOT AN ALLOCATION. Wafers are consumed one at a time in an
// order nobody records, so the even split answers exactly one question - "is there enough
// across this pool" - and says nothing about which wafer goes where. The screen says so
// three ways: every number carries `≈`, 잔여 carries it too, and the header says it once.
// ============================================================

function rollupRows() {
  const st = stageOfTable(S.ctx.table);
  if (!st || S.ctx.depth > 0) return [];
  return materialRollupRows(planOf(), paintedOf);
}

// 미상은 0이 아니다. `{value, reliable, reason}`을 그대로 받아 숫자를 숨기고 이유를 말한다 —
// 숫자만 넘기면 미상이 0으로 붕괴하고, 0은 "다 썼다"로 읽힌다.
function unknownCellHtml(state, extraClass) {
  return `<span class="tp-unk ${extraClass || ''}" title="${esc(state.reason || '')}">미상</span>`;
}

// [7c] 가용 칸. 확정 수 → 굵은 수 · 선언된 미추적 → `≤N` · 그 외 → 미상.
// 두 렌더 경로(전체 재렌더 / 카운트 텍스트 패치)가 **이 함수 하나**를 쓴다.
function availCellHtml(av) {
  if (av.status === null || av.status === 'loading') return '<span class="tp-unk">…</span>';
  if (av.bound !== null && av.bound !== undefined) {
    return `<b class="tp-bound" title="${esc(UNTRACKED_REASON)}">${boundText(av.bound)}</b>`;
  }
  return av.reliable ? `<b>${av.value}</b>` : unknownCellHtml(av, 'w');
}

// [7c] 잔여 칸. 상한 − 확정 사용량은 여전히 진짜 상한이다(알려진 상수를 상한에서 뺀 것).
// 뺄셈은 `remainingState` **하나**만 쓴다 — 확정 갈래와 상한 갈래가 각자 빼면 그 순간
// 같은 수의 구현이 둘이 된다. 상한 갈래는 합성 입력을 만들어 같은 함수에 통과시키고,
// 확정 수처럼 보이지 않도록 표기만 `≤`로 감싼다.
function remainingCellHtml(av, used) {
  if (av.bound !== null && av.bound !== undefined) {
    const b = remainingState({ status: 'ok', value: av.bound, reliable: true }, used);
    return `<span class="tp-bound" title="${esc(UNTRACKED_REASON)}">${boundText(b.value)}</span>`;
  }
  const rem = remainingState(av, used);
  return rem.reliable ? `<span class="ap">≈</span>${rem.value}` : unknownCellHtml(rem, 'w');
}

// 음수 강조는 확정 잔여에만 붙인다 — 상한이 음수라는 것은 "부족이 확정"이 아니라
// "가장 낙관적으로 봐도 부족"이라는 뜻이므로 같은 빨강을 쓰되 판정 문구는 붙이지 않는다.
function remainingIsNegative(av, used) {
  if (av.bound !== null && av.bound !== undefined) {
    return remainingState({ status: 'ok', value: av.bound, reliable: true }, used).value < 0;
  }
  const rem = remainingState(av, used);
  return rem.reliable && rem.value < 0;
}

function renderMaterialPane() {
  const box = elp.matPane;
  if (!box) return;
  const st = stageOfTable(S.ctx.table);

  if (S.ctx.depth > 0) {
    // 자재 맵을 연 상태 — 허브 대신 이 맵에서 할 일을 안내한다
    box.style.display = 'flex';
    box.innerHTML = `
      <div class="tp-pane-h"><span class="no">📦</span><span class="nm">자재 맵 편집 중</span>
        <span class="sp"></span>
        <button type="button" class="tp-btn" id="tp-frame-back">← 돌아가기</button></div>
      <div class="tp-pane-b">
        <p class="tp-hint">이 맵도 실맵입니다 — 오버레이·페인팅·<b>⚡ Push</b>가 그대로 동작합니다.
          맵 키 잠금과 정체성 핀도 동일하게 적용됩니다.</p>
        <div class="tp-ov-suggest">
          <span class="tp-hint">겹쳐 보기:</span>
          ${SOURCE_OVERLAY_SUGGESTIONS.map(s => `<button type="button" class="tp-btn tp-ov-add" data-tbl="${esc(s.table)}">＋ ${esc(s.label)}</button>`).join('')}
        </div>
      </div>`;
    const back = box.querySelector('#tp-frame-back');
    if (back) back.addEventListener('click', () => controller.goBack());
    box.querySelectorAll('.tp-ov-add').forEach(btn => {
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        const parts = String(S.ctx.mapKey || '').split('_');
        const r = await controller.addOverlayForSource(btn.dataset.tbl, parts[0], parts[1] || '');
        btn.disabled = false;
        if (r && r.error) showToast(r.error, r.unsupported ? 'warning' : 'error');
      });
    });
    return;
  }

  const pools = rollupRows();
  if (!st || pools.length === 0) {
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  box.style.display = 'flex';

  const { table: srcTable, derived: srcDerived } = sourceTableOf(st);
  // V3 (로트 전체 + 그 로트의 슬롯)의 메시지는 ②에만 있다 — 두 토큰이 한 화면에 같이 보이는
  // 곳이 여기뿐이기 때문이다. ①에서는 서로 다른 행이라 어디 붙여도 반쪽이 된다.
  const clashes = (S.blocks || []).filter(b => b.rule === 'V3');
  const clashTokens = new Set();
  clashes.forEach(b => { if (b.message) clashTokens.add(b.message); });

  const rows = pools.map(p => {
    const av = availabilityOfPool(p);
    const exists = srcTable ? S.matMapState.get(matMapCacheKey(srcTable, poolCacheId(p))) : null;
    const bad = clashes.some(c => c.value && p.uses.some(u => u.value === c.value));
    const availHtml = availCellHtml(av);
    // 전개된 슬롯 행은 그리지 않는다: 슬롯별 배분을 그리는 순간 화면이 매 단위 할당을
    // 주장하게 된다. 배분은 풀 단위로만 존재한다.
    const where = p.uses.map(u => `${u.value}·${ZONE_LABEL[u.zone]}`).join(' + ');
    return `<div class="tp-pool${bad ? ' clash' : ''}" data-pool="${esc(p.key)}" data-id="${esc(poolCacheId(p))}">
      <div class="tp-r2" title="클릭 → ${esc(p.raw)}의 맵">
        <span class="tp-matcell">${materialChipHtml(p.raw)}<span class="go">→</span></span>
        <span class="tp-mapb ${exists === true ? 'ok' : (exists === false ? 'no' : 'unk')}"
          title="${exists === true ? '자재 맵 있음' : (exists === false ? '자재 맵을 찾지 못했습니다' : '맵 유무를 확인하지 못했습니다')}">${
          exists === true ? 'O' : (exists === false ? 'X' : '?')}</span>
        <span class="tp-num avail">${availHtml}</span>
        <span class="tp-num share" title="${esc(where)}"><span class="ap">≈</span>${p.used}</span>
        <span class="tp-num left${remainingIsNegative(av, p.used) ? ' neg' : ''}">${
          remainingCellHtml(av, p.used)}</span>
      </div>
      <div class="tp-knob" title="이 자재를 쓰는 값들의 knob을 모은 파생 표시입니다 — 여기서는 편집하지 않습니다.">${
        knobChipsFor(p) || '<span class="tp-emp">— knob 없음</span>'}</div>
    </div>`;
  }).join('');

  box.innerHTML = `
    <div class="tp-pane-h"><span class="no">②</span><span class="nm">자재 롤업</span>
      <span class="sub">행 클릭 → 그 자재의 맵</span>
      <span class="sp"></span>
      <span class="tp-cnt">${pools.length} 풀</span>
      <button type="button" class="tp-btn" id="tp-mat-refresh">↻ 가용</button></div>
    <div class="tp-pane-b">
      <div class="tp-ch-row"><span>MAT</span><span class="c">MAP</span>
        <span class="r">가용</span><span class="r">사용<span class="ap">≈</span></span><span class="r">잔여<span class="ap">≈</span></span></div>
      ${rows}
      ${clashes.map(c => `<div class="tp-blk"><span class="rid">V3</span><span>${esc(c.message)}</span></div>`).join('')}
      <div class="tp-foot-note">
        <b>사용<span class="ap">≈</span></b>은 실제 소비가 아닙니다 — 이 풀의 총 소요를 자재 수로
        <b>균등 분배한 가정값</b>입니다. <b>충분한지</b> 보는 용도이며, 어느 매를 먼저 쓰는지는 이 화면이 말하지 않습니다.<br>
        <b>미상</b>은 <b>0이 아닙니다.</b> 가용이 미상·신뢰 불가면 <b>잔여도 미상</b>입니다.${
        srcTable ? ` · 대상 <b>${esc(srcTable)}</b>${srcDerived === 'fallback'
          ? ' <span class="tp-chip warn" title="stage 선언에서 유도하지 못해 하드코딩 폴백을 씁니다 — 서버에 명시 선언 요청됨">추정</span>' : ''}`
        : ' · <b class="tp-mat-nosrc">자재 맵 테이블 미상 — stage 선언 확인 필요</b>'}
      </div>
    </div>`;

  box.querySelector('#tp-mat-refresh').addEventListener('click', () => refreshMaterials(true));
  box.querySelectorAll('.tp-pool').forEach(r => {
    r.addEventListener('click', () => openMaterial(r.dataset.id));
  });
  S.flash.clear();
}

// knob은 값 층위에 저장돼 있고(map_split_registry.knobs), ②는 그것을 자재 기준으로 **모아
// 보여주기만** 한다.
// ⚠️ 편집 경로를 만들지 않았다. 자재 층위 knob에는 선언된 저장 자리가 없고, 저장할 곳이 없는
//    입력 칸은 사용자의 타이핑을 조용히 버린다 — 이 도메인이 없애려는 결함 그 자체다.
//    자재 층위 knob 편집은 서버에 저장 자리가 선언된 뒤에 붙인다.
function knobChipsFor(pool) {
  const seen = new Map();
  (pool.uses || []).forEach(u => {
    const row = rowOf(u.value);
    ((row && row.knobs) || []).forEach(p => {
      const k = String((p && p.k) || '').trim();
      if (!k) return;
      const label = String(p.v || '').trim() ? `${k}=${p.v}` : k;
      if (!seen.has(label)) seen.set(label, true);
    });
  });
  return [...seen.keys()].map(l => `<span class="tp-kc"><span class="h">#</span>${esc(l)}</span>`).join('');
}

// ============================================================
// 엑셀 ⇄ 왕복. 이 화면의 목적이다.
//
// 🔴 `navigator.clipboard`는 쓸 수 없다. 운영은 LAN 평문 HTTP = 비보안 컨텍스트라
//    **undefined**다. 모든 것이 네이티브 이벤트의 `e.clipboardData`를 지난다. 그래서 이
//    화면에는 클립보드를 호출하는 버튼이 하나도 없다 — `⇄ 엑셀`은 버튼이 아니라 **표시**다.
//
// 계약은 픽셀이 아니라 TSV에 있다. 일곱 칸이 화면에서 한 줄로 그려지든 두 줄로 그려지든
// 파서는 모른다 — 채우기는 **논리 인덱스** 기준이지 "화면에서 오른쪽 칸"이 아니다.
// ============================================================

function planClipboardActive() {
  return !!stageOfTable(S.ctx.table) && S.ctx.depth === 0;
}

// 붙여넣기는 **거절하지 않는다.** 3열만 복사해도 받는다. 거절이 안전한 건 맞지만 "쉽게"가
// 지배 요구이고, 3열 붙여넣기를 "7열이어야 합니다"로 되돌리면 사람은 엑셀로 돌아가 표를 다시
// 만든다 — 그 순간 이 화면의 목적이 사라진다. 진짜 위험(열 어긋남)은 머리줄 이름 매칭이 없앤다.
function onPlanPaste(e) {
  if (!planClipboardActive()) return;
  const text = e.clipboardData ? e.clipboardData.getData('text/plain') : '';
  if (!text) return;
  const grid = parseTsv(text, { trimCells: true });
  if (grid.length === 0) return;
  // 1×1은 가로채지 않는다 — 자재 한 칸에 토큰 하나를 붙여넣는 것은 평범한 입력이고,
  // 여기서 가로채면 읽기·입력 동선에 마찰이 생긴다.
  if (grid.length === 1 && grid[0].length === 1) return;
  e.preventDefault();

  const startCol = focusedColumnId();
  const focused = focusedRowValue();
  const startRow = Math.max(0, S.legendRows.findIndex(r => String(r.value) === focused));
  const mapped = mapPastedGrid(grid, startCol);

  let applied = 0;
  mapped.rows.forEach((patch, i) => {
    const idx = startRow + i;
    let target = S.legendRows[idx];
    if (!target) {
      // 부족하면 만든다. 만드는 것도 map_editor의 관문을 지난다.
      const created = controller.addLegendRow && controller.addLegendRow();
      if (!created) return;
      S.legendRows = controller.getLegend();
      target = S.legendRows[S.legendRows.length - 1];
      if (!target) return;
    }
    let name = String(target.value);
    // 개명이 먼저다 — 나머지 패치는 새 이름 아래로 들어가야 한다.
    if (patch.value !== undefined && String(patch.value).trim() && String(patch.value).trim() !== name) {
      const r = controller.updateLegendRow(name, { value: String(patch.value).trim() });
      if (r && r.ok) name = String(patch.value).trim();
    }
    // COLOR is app-owned and outside the contract: `DOE_COLUMNS` has no `color`, so
    // `patch.color` cannot exist. A new value gets a colour assigned by `addLegendRow`;
    // an existing one keeps the one it has. (사용자 지시 2026-07-28 — 엑셀의 셀 채우기는
    // `text/plain`으로 이동하지 않으므로 색 열은 어차피 빈 칸이나 잡음으로 도착한다.)
    const rest = {};
    if (patch.desc !== undefined) rest.desc = String(patch.desc).trim();
    if (patch.stack !== undefined) rest.stack = String(patch.stack).trim();
    ZONES.forEach(z => { if (patch[z] !== undefined) rest[z] = parseMaterialList(patch[z]); });
    if (Object.keys(rest).length > 0) commitRow(name, rest);
    S.legendRows = controller.getLegend();
    applied++;
  });

  // 붙여넣기는 저장이 아니다 — 화면에 다 보이고, 검증은 행 옆에 붙는다. 그래도 몇 줄이
  // 들어갔는지는 말해야 한다: 조용한 대량 변경은 되돌릴 근거조차 안 남긴다.
  showToast(`값 ${applied}개를 붙여넣었습니다${mapped.header ? ' (머리줄 이름으로 맞춤)' : ''}`
    + `${mapped.droppedLeading ? ' · 앞의 빈 열(색)은 건너뛰었습니다' : ''}`
    + `${mapped.wide > 0 ? ` · 계약 밖 칸 ${mapped.wide}개는 무시했습니다` : ''}`, 'info');
  renderDoeList();
  refreshMaterials();
}

// 복사는 **원문 토큰만** 나간다. `_✱`·`≈`·「미상」·「해당 없음」·「칠함」은 전부 렌더링이고,
// TSV에 나가면 다시 붙여넣을 수 없는 표가 된다.
function onPlanCopy(e) {
  if (!planClipboardActive()) return;
  const el = document.activeElement;
  if (!el || !elp.pane1 || !elp.pane1.contains(el)) return;
  // 필드 안에서 글자를 선택해 복사하는 것은 평범한 복사다 — 가로채지 않는다.
  const sel = window.getSelection && window.getSelection();
  if (sel && !sel.isCollapsed) return;
  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
    if (typeof el.selectionStart === 'number' && el.selectionStart !== el.selectionEnd) return;
  }
  e.preventDefault();
  const v = focusedRowValue();
  const rows = v ? S.legendRows.filter(r => String(r.value) === v) : S.legendRows;
  e.clipboardData.setData('text/plain', serializeTsv(planToGrid(rows)));
}

// ── 자재 맵 왕복 ────────────────────────────────────────
async function openMaterial(id) {
  if (S.navBusy) return;
  const st = stageOfTable(S.ctx.table);
  const table = sourceTableOfStage(st);
  if (!table) { showToast('자재 맵 테이블을 알 수 없습니다 (stage 선언 확인 필요).', 'warning'); return; }
  S.navBusy = true;
  try {
    let metaValues = await materialMetaValues(table, id);
    if (Object.keys(metaValues).length === 0) {
      // LOAD parity (user 2026-07-28): an id that does not split into (lot, slot) must
      // still ROUTE - the raw id becomes the first key column's filter, exactly what
      // typing only that field in "1. Map Search & Load" does. A key with no rows then
      // opens as an empty grid (openMapFrame allowEmpty) and is created on ⚡ Push.
      // NOTE: probeMaterialMap keeps returning null (미상) for these ids on purpose -
      // guessing is fine for navigation the user asked for, not for an existence claim.
      const spec = await materialKeySpec(table);
      const cols = (spec && spec.keyColumns) || [];
      if (cols.length === 0) {
        showToast(`${table}의 맵 키 컬럼을 읽지 못했습니다.`, 'error'); return;
      }
      // [7b] 라우팅 값도 캐노니컬화한다 — 여기서 원문 '01'을 넣으면 에디터의 메타 입력이
      // '01'로 채워지고, 그 입력으로 조합된 map_key가 저장본 'LOT_1'을 다시 빗나간다.
      metaValues = { [cols[0]]: String(canonKey(String(id), (spec.columnTypes || {})[cols[0]]) ?? id) };
    }
    const r = await controller.openMapFrame({
      table, metaValues,
      presetKind: st.sourceKind === 'core' ? 'core' : 'tape',
    });
    // [fix G] A user-cancelled frame open is not a failure — the editor already
    // toasted the cancellation; an extra "열기 실패" here would call it an error.
    if (!r || (!r.ok && !r.cancelled)) showToast(`자재 맵 열기 실패: ${(r && r.error) || '알 수 없음'}`, 'error');
  } finally {
    S.navBusy = false;
  }
}

// ★ 왕복의 보상 — 복귀 시 **그 자재만** 재조회해 수량·맵 유무를 갱신한다.
async function rewardAfterReturn(from) {
  if (!from || !from.mapKey) return;
  const st = stageOfTable(S.ctx.table);
  const table = sourceTableOfStage(st);
  if (!table || from.table !== table) return;
  const id = String(from.mapKey);
  const pools = rollupRows().filter(p => poolCacheId(p) === id);
  if (pools.length === 0) return;
  let failed = false;
  await Promise.all(pools.map(async p => {
    const entry = await getPoolSummary(p, true);
    if (entry && entry.status === 'error') failed = true;
  }));
  await probeMaterialMap(table, id, true);
  if (failed) {
    showToast(`자재 ${id} 가용 재조회 실패 — 미상으로 표시합니다. [↻ 가용]으로 다시 시도하십시오.`, 'warning');
  }
  renderMaterialPane();
}

// 자재 목록의 가용·맵 유무 일괄 갱신.
//
// `force` is true on exactly one path: the [↻ 가용] button. That press must produce
// visible feedback even when every number stays 미상 — before this toast, a refresh whose
// answer was "the server refuses BIN-scoped availability" repainted the same 미상 cells
// and the button read as dead (U8, user: "가용 버튼 눌러도 업데이트 안됨"). The per-cell
// reason still lives in the 미상 tooltip; the toast names the dominant one out loud.
async function refreshMaterials(force = false) {
  const seq = ++S.matSeq;
  const st = stageOfTable(S.ctx.table);
  const table = sourceTableOfStage(st);
  const pools = rollupRows();
  renderMaterialPane();
  if (pools.length === 0) return;
  await Promise.all(pools.map(async p => {
    await getPoolSummary(p, force);
    if (table) await probeMaterialMap(table, poolCacheId(p), force);
  }));
  if (seq !== S.matSeq) return;   // a newer refresh superseded this one — its toast too
  renderMaterialPane();
  if (force) {
    const unknownReasons = [];
    pools.forEach(p => {
      const av = availabilityOfPool(p);
      if (!(av.reliable === true && av.value !== null && av.value !== undefined)) {
        unknownReasons.push(av.reason || '이유 미상');
      }
    });
    if (unknownReasons.length === 0) {
      showToast(`가용 조회 완료 — ${pools.length}개 풀`, 'info');
    } else {
      // One line, the most common reason. The full per-pool reason is on each 미상 cell.
      const tally = new Map();
      unknownReasons.forEach(r => tally.set(r, (tally.get(r) || 0) + 1));
      const dominant = [...tally.entries()].sort((a, b) => b[1] - a[1])[0][0];
      showToast(`가용 조회 완료 — ${pools.length}개 풀 중 ${unknownReasons.length}개 미상: ${dominant}`, 'warning');
    }
  }
}

// ── 골격 ────────────────────────────────────────────────
//
// 표 둘. 세 번째 표면도, 모드도, 모달도 없다. ①·②는 `flex:1 1 0`으로 정확히 반씩 나누고
// **각자 스크롤한다** — 카드에 `flex:none`이 없으면 내용이 길어질 때 스크롤되지 않고
// 찌그러진다(이전 시안에서 696px→211px로 실측된 함정).
function renderAll() {
  renderPlanHead();
  renderDoeList();
  renderMaterialPane();
}

function buildWorkspace(root) {
  root.innerHTML = `
    <div class="tp-plan-head" id="tp-head"></div>
    <div class="tp-split">
      <div class="tp-pane" id="tp-pane1">
        <div class="tp-pane-h">
          <span class="no">①</span><span class="nm">값 정의</span>
          <span class="sp"></span>
          <span class="tp-xl" title="엑셀 표를 그대로 붙여넣습니다 (Ctrl+V).
열 순서 — VALUE · STACK · DESC · 1H · MID · TOP
머리줄을 같이 복사하면 이름으로 맞춥니다 — 열 순서가 달라도, 일부만 복사해도 됩니다.
Ctrl+C — 포커스한 값(없으면 전체)이 같은 형태의 TSV로 나갑니다.
「COLOR」와 「칠함」은 계약 밖입니다 — 붙여넣기·복사 양쪽에서 빠집니다.
엑셀 표에 색 열이 있어도 됩니다: 머리줄이 있으면 이름으로 빠지고, 없으면 앞의 빈 열을 건너뜁니다."><b>⇄</b> 엑셀</span>
          <button type="button" class="tp-btn" id="tp-add-value">+ 값</button>
        </div>
        <div class="tp-pane-b" id="tp-list"></div>
      </div>
      <div class="tp-pane t2" id="tp-mat-pane" style="display:none;"></div>
    </div>`;
  elp.head = root.querySelector('#tp-head');
  elp.pane1 = root.querySelector('#tp-pane1');
  elp.list = root.querySelector('#tp-list');
  elp.matPane = root.querySelector('#tp-mat-pane');
  root.querySelector('#tp-add-value').addEventListener('click', () => {
    if (controller && controller.addLegendRow) controller.addLegendRow();
  });
  // 클립보드는 ① 안에서만 듣는다. 문서 전역에 걸면 그리드의 핸들러와 다툰다.
  // `⇄ 엑셀`은 표시이지 버튼이 아니다 — 클릭 핸들러가 없다(비보안 컨텍스트 제약).
  elp.pane1.addEventListener('paste', onPlanPaste);
  elp.pane1.addEventListener('copy', onPlanCopy);
}

// ── map_editor → 패널 통지 (export) ─────────────────────

// 맵 정체성이 바뀌었다 (테이블 전환 / 맵 로드 / 프레임 push·pop / push 성공).
// ⚠️ [M2.6] 서버 조회는 여기서 하지 않는다 — legend(= DOE) 로드·채택·가드는 전부
//    map_editor의 registry 경로에 있고, 이 함수는 그 결과를 그리기만 한다.
export function notifyMapContext(info = {}) {
  if (!controller || !controller.getMapContext) return;
  const c = controller.getMapContext();
  const changed = (c.table !== S.ctx.table) || ((c.mapKey || '') !== (S.ctx.mapKey || '')) || (c.depth !== S.ctx.depth);
  S.ctx = {
    table: c.table || '',
    mapKey: (c.loaded && c.loaded.mapKey) || c.mapKey || '',
    loaded: c.loaded, depth: c.depth || 0, parent: c.parent || null,
  };
  if (changed) S.flash.clear();
  if (controller.getLegend) S.legendRows = controller.getLegend();
  renderAll();
  if (changed) {
    // [U6] A transient stages failure must not degrade the whole session — retry until
    // a definite answer (declaration or 404/405) arrives.
    if (S.stagesStatus === 'error') stagesPromise = fetchStages();
    refreshMaterials();
    // ★ 왕복 보상 — 복귀 직후 그 자재만 재조회
    if (info.returnedFrom) rewardAfterReturn(info.returnedFrom);
  }
}

// legend(값·설명·색·knobs·층 구조·브러시)가 바뀌었다.
export function notifyLegendChanged() {
  if (!controller || !controller.getLegend) return;
  S.legendRows = controller.getLegend();
  S.activeBrush = controller.getActiveBrush ? controller.getActiveBrush() : '';
  renderPlanHead();
  renderDoeList();
  renderMaterialPane();
}

// 페인팅 카운트 변경 — 전체 재렌더 금지, **파생 숫자 텍스트만** 패치한다.
// 소요·배분이 칠한 셀 수에서 나오므로 이 경로가 곧 "그림이 곧 계획"의 구현이다.
// (수만 셀 조작 중 재렌더는 프리징을 만든다 — 그래서 텍스트만 건드린다.)
export function notifyPaintCounts(counts) {
  S.counts = counts || {};
  if (!elp.list) return;
  elp.list.querySelectorAll('[data-count-for]').forEach(node => {
    node.textContent = paintedOf(node.getAttribute('data-count-for'));
  });
  if (elp.matPane && elp.matPane.style.display !== 'none') {
    // ②의 사용·잔여는 **같은 함수**로 다시 계산한다(`materialRollupRows`). 여기에 두 번째
    // 계산을 두면 DB 34 · 화면 33 사건이 그대로 재현된다 — 저장이 `ceil`, 표시가 `round`
    // 였을 때 정확히 그렇게 갈라졌다.
    const byKey = new Map(rollupRows().map(p => [p.key, p]));
    elp.matPane.querySelectorAll('.tp-pool').forEach(node => {
      const p = byKey.get(node.getAttribute('data-pool'));
      if (!p) return;
      const share = node.querySelector('.tp-num.share');
      if (share) share.innerHTML = `<span class="ap">≈</span>${p.used}`;
      // [7c] 상한 표기도 이 경로를 지난다 — 두 렌더 경로가 `remainingCellHtml` 하나를
      // 쓰므로, 셀을 칠하는 도중에만 `≤`가 사라지는 식의 갈림이 생길 수 없다.
      const av = availabilityOfPool(p);
      const left = node.querySelector('.tp-num.left');
      if (left) {
        left.classList.toggle('neg', remainingIsNegative(av, p.used));
        left.innerHTML = remainingCellHtml(av, p.used);
      }
    });
  }
}

export function initTransferPlan(paintController) {
  controller = paintController || null;
  const root = document.getElementById('transfer-plan-root');
  if (!root) { console.warn('[Legend & DOE] mount point missing (#transfer-plan-root)'); return; }
  buildWorkspace(root);
  renderAll();
  ensureStages(); // may already be in flight via stageTargetTables() — one fetch, not two
}

// ============================================================
// §보류 구역 — 검증/경고 판정 (사용자 지시로 이번 범위에서 **미연결**)
//
//   아래 함수들은 M2에서 만든 판정 로직이다. 재설계 후 다시 붙일 예정이라
//   **삭제하지 않고** 보관한다. 현재 어떤 렌더러도 이들을 호출하지 않는다.
//   재연결 시 유의: DOE 모델이 `{stack, need}` → `{seq, to, materials[]}`로 바뀌었고
//   소요·배분은 **파생**이므로, 수량 판정은 bandTotal/bandShare를 호출해 써야 한다.
//
//   보류 항목: 수량 부족 판정 · 교차 초과배정 · validate 연동 · 신뢰 어휘 4단 배지 ·
//              STACK 커버리지 스트립 · 검증 스킵 배너 · by_core 분해표
// ============================================================

// eslint-disable-next-line no-unused-vars
function __held_normalizeSources(src) {
  const out = [];
  if (!src) return out;
  if (Array.isArray(src)) {
    src.forEach(s => { if (s && (s.role || s.name)) out.push({ role: s.role || s.name, status: String(s.status || s.state || 'connected') }); });
  } else if (typeof src === 'object') {
    Object.entries(src).forEach(([role, v]) => {
      const status = typeof v === 'string' ? v : String((v && (v.status || v.state)) || 'connected');
      out.push({ role, status });
    });
  }
  return out;
}

// eslint-disable-next-line no-unused-vars
function __held_classifySourceStatus(rawStatus) {
  const status = String(rawStatus === undefined || rawStatus === null ? '' : rawStatus).trim();
  if (status === '' || status === 'connected') return { severity: 'ok', status: status || 'connected', note: '' };
  if (status === 'missing') return { severity: 'missing', status, note: '역할 미연결' };
  if (/^unavailable\(/i.test(status) || /align_unavailable/i.test(status)) {
    return { severity: 'degraded', status, note: 'fail 집계 누락 — 잔여가 과대일 수 있음' };
  }
  if (/^connected\(/i.test(status)) {
    const inner = status.replace(/^connected\(/i, '').replace(/\)$/, '');
    return { severity: 'ok', status, note: /area_only/i.test(inner) ? 'by_core 강등(집계는 유효)' : '' };
  }
  return { severity: 'unknown', status, note: '알 수 없는 상태 — 서버 원문' };
}

// eslint-disable-next-line no-unused-vars
function __held_remainingReliability(data) {
  if (!data || typeof data !== 'object') return { reliable: true, reasons: [] };
  const reasons = [];
  __held_normalizeSources(data.sources)
    .map(s => ({ role: s.role, ...__held_classifySourceStatus(s.status) }))
    .filter(s => s.severity === 'degraded' || s.severity === 'missing')
    .forEach(s => reasons.push(`${s.role}: ${s.status}`));
  const chips = data.chips || {};
  const flag = (data.remaining_reliable !== undefined) ? data.remaining_reliable
    : (chips.remaining_reliable !== undefined ? chips.remaining_reliable : undefined);
  if (flag === false) reasons.push('서버: remaining 신뢰 불가');
  if (chips.remaining === null || chips.remaining === undefined) reasons.push('서버: 잔여 값 미제공(미상)');
  if (data.truncated && typeof data.truncated === 'object' && Object.keys(data.truncated).length > 0) {
    reasons.push(`응답 절단: ${Object.keys(data.truncated).join(', ')}`);
  }
  if (data.by_core_truncated) reasons.push('by_core 절단');
  return { reliable: reasons.length === 0 && flag !== false, reasons };
}

// eslint-disable-next-line no-unused-vars
const __HELD_WARN_SEVERITY = {
  stage_unknown: 'critical', source_unresolved: 'critical', client_parse_error: 'critical',
  source_degraded: 'high', availability_unreliable: 'high', source_overallocated: 'high',
  qty_shortage: 'high', source_fail_chips: 'high', truncated: 'high',
  layer_coverage_gap: 'normal', doe_value_unpainted: 'normal', undefined_doe_value: 'normal',
};

// eslint-disable-next-line no-unused-vars
function __held_normalizeWarning(w) {
  if (typeof w === 'string') return { type: w, detail: '', raw: w };
  if (w && typeof w === 'object') {
    const type = String(w.type ?? w.code ?? w.kind ?? '').trim() || '(무형식)';
    const extras = Object.entries(w)
      .filter(([k]) => !['type', 'code', 'kind', 'detail', 'message', 'msg'].includes(k))
      .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`);
    const detail = String(w.detail ?? w.message ?? w.msg ?? '');
    return { type, detail: [detail, extras.join(' · ')].filter(Boolean).join(' · '), raw: w };
  }
  return { type: '(무형식)', detail: String(w), raw: w };
}

// eslint-disable-next-line no-unused-vars
async function __held_refreshValidate(planId) {
  // GET /api/transfer-plan/validate?plan_id=... — 서버가 ref_table+map_key 파라미터로
  // 이전하는 중이라 재연결은 서버 계약 확정 후에 한다.
  const params = new URLSearchParams({ plan_id: planId });
  const res = await fetch(`${API_BASE}/api/transfer-plan/validate?${params.toString()}`);
  return res.ok ? res.json() : null;
}

// eslint-disable-next-line no-unused-vars
function __held_fmtChips(v) { return fmtChips(v); }
