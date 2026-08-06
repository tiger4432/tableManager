import './tokens.css';
import './style.css';
import { API_BASE, CURRENT_USER, MAP_SPEC_SAVE_TIMEOUT_MS } from './config.js';
import { initTheme } from './theme.js';
import { getLocalTimeString, showToast } from './utils.js';
import { initTransferPlan, notifyMapContext, notifyLegendChanged, notifyPaintCounts, stageTargetTables } from './transfer_plan.js';
// The ONE material-list normalizer. The panel parses what the user types with it and the
// storage layer normalizes with it, so the material COUNT on screen and the denominator of
// `ceil(total / n)` in the save can never be two different numbers.
// `ZONES`/`ZONE_LABEL` come with it because COPY HEADER MODE prints the zone group names
// (1H · MID · TOP) into the exported header. INV-ⓐ-4: the words on screen and the words in
// the export are ONE list — a second hardcoded copy here is how "MID" on screen becomes
// "MIDDLE" in the file the factory actually reads.
// [F1ⓑ] `columnIdByHeader`/`looksLikeHeader`/`mapPastedGrid`은 **붙여넣기 쪽**이 쓴다. 보조표를
// 되읽을 때 두 번째 열 판정기를 만들지 않기 위해서다 — 로스터(`IGNORED_HEADERS`, COUNT를
// IGNORE로 보내는 그 목록)와 이름 매칭이 이미 있고, DOE 패널이 그것으로 붙여넣기를 받는다.
import {
  parseMaterialList, bandsToZones, ZONES, ZONE_LABEL, DOE_COLUMNS,
  columnIdByHeader, looksLikeHeader, mapPastedGrid,
} from './doe_bands.js';
// THE ONLY TSV reader in this codebase (client2/src/tsv.js). 엑셀의 인용 규칙(탭·줄바꿈을 품은
// 셀)을 아는 유일한 구현이고, 그리드 화면과 DOE 패널이 이미 이것을 쓴다. 여기서 `split('\t')`을
// 손으로 쓰면 이 저장소에 **세 번째** 클립보드 파서가 생긴다.
// [MEDIUM-2] `serializeTsv`도 여기서 온다. 복사가 `join('\t')`으로 평문을 만들고 붙여넣기가
// `parseTsv`로 읽으면 **쓰는 규칙과 읽는 규칙이 다르다** — 그 비대칭이 DESC의 인용부호 하나로
// 왕복을 깨뜨렸다(아래 copyGridToExcel의 측정 주석). 계약은 `parseTsv(serializeTsv(g)) === g`다.
import { parseTsv, serializeTsv } from './tsv.js';
// [V1 effort instrument] The ONE collector (client2/src/effort_meter.js, owned by Lead PM).
// This file counts NOTHING on its own: no local counters, no second session id, no copy of
// the 1/3/5 weights (those live server-side and are applied at query time). Keystrokes and
// mouse presses come from the module's own page-wide listeners; this file only declares the
// screen transitions it is the only one that can see, and hands the raw counts to the save.
import {
  ROUTES, startSession, installGlobalListeners, installNavLinkCounting, countNav,
  snapshot as effortSnapshot, commitIfRecorded as effortCommitIfRecorded
} from './effort_meter.js';
// [7b] THE ONE map-identity canonicaliser (client2/src/map_key.js). It used to live in this
// file; it is a pure leaf that calls nothing here, and the server half
// (`map_overlay.canonical_key_value` / `compose_map_id` / `build_key_filters`) is scored
// against it value-for-value by client2/tests/seam_7b_oracle.py. Do not re-spell any of it
// locally — a second opinion about map identity is the exact defect these functions closed.
import {
  canonicalKeyValue, composeMapId, decomposeMapKey, canonicalMapKey, getMapIdFromMeta,
} from './map_key.js';
// The ONE map_split_registry row normal form (client2/src/split_registry_row.js). It used
// to live here; it is a pure leaf over its arguments, and the SAME projection
// (LEGEND_PAYLOAD_COLUMNS) feeds the write payload, the concurrency fingerprint and the
// vocabulary signature. Do not re-spell any of it locally: a saved field that is not a
// compared field is an edit shown on screen and dropped from the save.
import {
  normalizeBands, normalizeKnobs, normalizeLegendItem, cloneLegend, registryFingerprint,
  buildLegendRegistryUpdates, parseLegendRegistryRows, getMissingDescValues,
  formatLegendMetaText, legendRowSignature,
} from './split_registry_row.js';
// [Gate 4] THE push-column contract (client2/src/push_columns.js). It used to live here; it
// is a pure leaf over its arguments, and it is the answer to "which columns would a
// `replace_map` into this table destroy" for BOTH consumers in this file — the push gate and
// the metadata search-column filter. Do not re-spell the roster locally: the schema
// endpoint's system tail and the write path's skip list are ONE list, and a second copy is
// how a column stops being protected on one screen while staying protected on the other.
import {
  PUSH_SYSTEM_COLUMNS, getUnprotectedPushColumns, logShapedPushDecision,
} from './push_columns.js';

let tables = [];
let selectedTable = '';
let tableSchema = null;
let gridData = {}; // key: "x_y" -> value (physical coordinates)
let legend = [];
let activeBrush = '';
let isMouseDown = false;
let isRightDrag = false;

// Rotation & Side Mirroring States
let currentRotation = 0; // 0, 90, 180, 270
let currentSide = 'front'; // 'front', 'back'
let isOriginMode = false; // Origin designation mode state
let isBoxDragging = false; // Bounding box drag selection state
let boxStartCell = null; // Start cell reference for bounding box
let lastSelectionBox = null; // Track coordinates of current selection bounding box
let gridCells2D = []; // 2D reference array of cell metadata objects [row][col]
let dragType = null; // 'paint' | 'erase'
let selectedEdgeTargetMap = null; // Track active E1/E2 edge selection map
let loadedFCells = new Set(); // Track physical keys of cells loaded with value 'F'

// ----------------------------------------------------
// 페인트 잠금 규칙 — 단일 관문 (하드코딩 금지, config 주입형)
// 종래에는 값 'F'가 코드 곳곳에 박혀 있었다. 잠금 판정을 여기 한 곳으로 모으고
// 서버 선언을 주입받을 수 있게 한다. 서버 계약 확정 전에는 builtin 기본값으로 동작.
//   기대 형태: { locked_values: ["F", ...], case_sensitive: bool }
// ----------------------------------------------------
// 계약: 잠금 값은 **서버 config가 정본**이다. 클라는 'F' 같은 값을 하드코딩하지 않는다.
// 기본값은 "잠금 없음"(enabled:false) — 선언이 없으면 아무것도 잠그지 않는다.
const NO_PAINT_LOCK = { enabled: false, blocking_values: [], from_overlay: [], message: '' };
let paintLockConfig = { ...NO_PAINT_LOCK, source: 'default' };

// 값 자체가 잠금 대상인가 (맵 로드 시 잠금 셀 판별)
function isLockedValue(val) {
  if (!paintLockConfig.enabled) return false;
  if (val === undefined || val === null) return false;
  const s = String(val).trim();
  if (s === '') return false;
  const list = Array.isArray(paintLockConfig.blocking_values) ? paintLockConfig.blocking_values : [];
  return list.some(v => String(v) === s);
}

// 오버레이 기준 잠금: 선언된 오버레이에 셀이 있는 좌표는 칠할 수 없다.
function isOverlayLocked(key) {
  if (!paintLockConfig.enabled) return false;
  const from = Array.isArray(paintLockConfig.from_overlay) ? paintLockConfig.from_overlay : [];
  if (from.length === 0) return false;
  return overlayLayers.some(o => from.includes(o.sourceTable) && o.cells && o.cells.has(key));
}

function paintLockMessage() {
  return paintLockConfig.message || '이 좌표는 잠금 규칙에 의해 칠할 수 없습니다.';
}

// 이 좌표를 편집(페인트/지우기)할 수 없는가 — 전 편집 경로의 단일 관문
function isProtectedFCell(key) {
  return loadedFCells.has(key) || isOverlayLocked(key);
}

// 서버 선언 주입 지점
function applyPaintLockConfig(payload) {
  const rules = (payload && typeof payload === 'object')
    ? (payload.rules && typeof payload.rules === 'object' ? payload.rules : payload) : null;
  if (!rules) return false;
  paintLockConfig = {
    enabled: rules.enabled === true,
    blocking_values: Array.isArray(rules.blocking_values) ? rules.blocking_values.map(String) : [],
    from_overlay: Array.isArray(rules.from_overlay) ? rules.from_overlay.map(String) : [],
    message: typeof rules.message === 'string' ? rules.message : '',
    source: 'server',
  };
  return true;
}

// [U6] Served map defaults, riding on the same paint-rules response (config-level —
// identical for every table): the RESOLVED value-column candidate list and the declared
// default legend. null until the first successful fetch. The client keeps NO copy of the
// server defaults, so "not fetched yet / unreachable" must behave as "cannot
// auto-detect" and "one empty seed row" — never as a builtin list.
let overlayContract = null; // { valueColumnCandidates: string[], defaultLegend: array|null }

// [F1] Served coordinate binding, PER TABLE — the paint-rules response now carries the
// server-RESOLVED binding for its `table` param (declared table_bindings win, else
// table_config derivation): {x, y, val, key_columns[], source}. This cache is the single
// client-side source for "which columns are the map coordinates" — both the load-path
// dropdown preselect and the overlay path read it. The client keeps NO derivation copy
// (the old local deriveMapBinding and the case-insensitive x/y matcher are gone): one
// matcher, server-side, same answer everywhere.
//   value: normalized binding object, or null = server says unresolvable (honest refusal).
//   absent key: never asked / fetch failed — consumers must not guess.
const servedBindingCache = new Map();

// Normalize the served shape (snake_case key_columns -> keyColumns) and refuse malformed
// payloads. `source` outside the known vocabulary degrades to 'derived' (no special UI).
function normalizeServedBinding(b) {
  if (!b || typeof b !== 'object') return null;
  const kc = Array.isArray(b.key_columns)
    ? b.key_columns.filter(c => typeof c === 'string' && c !== '') : [];
  if (typeof b.x !== 'string' || typeof b.y !== 'string'
    || typeof b.val !== 'string' || kc.length === 0) return null;
  return {
    x: b.x, y: b.y, val: b.val, keyColumns: kc,
    source: (b.source === 'declared' || b.source === 'fallback_guess') ? b.source : 'derived',
  };
}

// [F1] Fetch the served binding for an arbitrary table (overlay sources are not the
// selected table, so this cannot ride on fetchPaintRules). Same endpoint; the paint-rule
// part of the response is deliberately ignored here — locks belong to the selected table
// only. Success (including "server says null") is cached; failures throw and cache nothing.
async function fetchServedBinding(table) {
  if (servedBindingCache.has(table)) return servedBindingCache.get(table);
  const res = await fetch(`${API_BASE}/api/maps/paint-rules?table=${encodeURIComponent(table)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const cfg = await res.json();
  const b = normalizeServedBinding(cfg.binding);
  servedBindingCache.set(table, b);
  return b;
}

// GET /api/maps/paint-rules?table= — 잠금 선언의 정본.
//
// 🔴 [M2 수정] 종전에는 **모든 실패**(네트워크 끊김·500·타임아웃)에서 잠금을 통째로 비웠다.
//    잠금은 8개 편집 경로가 강제하는 안전장치인데, 일시적 네트워크 오류 한 번으로
//    **전면 fail-open**되면서 UI에는 아무 신호도 없었다 — 사용자는 불량 셀 위를
//    칠할 수 있게 된 줄 모른다.
//
// ✅ 새 규율: "선언이 없다"(404/405)와 "확인하지 못했다"(그 외 실패)를 구분한다.
//    · 404/405 → 선언 없음. 잠금 해제가 정답이다(조용히).
//    · 그 외    → **직전 잠금 값을 유지**하고(무방비 개방 금지) 사용자에게 알린다.
async function fetchPaintRules(table) {
  const t = table || selectedTable;
  if (!t) return;
  const degrade = (why) => {
    // 이전 잠금 값을 그대로 들고 간다 — 모르는 상태에서 여는 것보다 닫아 두는 쪽이 안전하다
    paintLockConfig = { ...paintLockConfig, source: 'stale' };
    // The toolbar chip (`⚠ 잠금 규칙 미확인`) is the on-screen signal and it PERSISTS; a toast
    // that fades said the same thing a third time. Diagnosis goes to the console.
    console.log(`[Map Editor] paint-rules 조회 실패 (${t}): ${why} — 직전 잠금 규칙을 유지합니다.`);
    updatePaintLockIndicator();
  };
  try {
    const res = await fetch(`${API_BASE}/api/maps/paint-rules?table=${encodeURIComponent(t)}`);
    if (res.status === 404 || res.status === 405) {
      paintLockConfig = { ...NO_PAINT_LOCK, source: 'unsupported' };
      recomputeLockedCells();
      updatePaintLockIndicator();
      return;
    }
    if (!res.ok) { degrade(`HTTP ${res.status}`); return; }
    const cfg = await res.json();
    // [U6] Cache the served defaults for every consumer (value-column auto-detect,
    // empty-map seed, auto-added legend colors). Only a response that actually carries
    // the candidate list updates the cache — an older server leaves it as it was.
    if (Array.isArray(cfg.value_column_candidates)) {
      overlayContract = {
        valueColumnCandidates: cfg.value_column_candidates.filter(
          c => typeof c === 'string' && c.trim() !== ''),
        defaultLegend: Array.isArray(cfg.default_legend) ? cfg.default_legend : null,
      };
    }
    // [F1] The same response carries the resolved binding for this table — cache it for
    // the dropdown preselect (fillColumnDropdowns reads the cache synchronously after
    // switchTable awaits this round-trip). Only a response that actually has the field
    // updates the cache: an older server must not erase a previously served answer.
    if ('binding' in cfg) servedBindingCache.set(t, normalizeServedBinding(cfg.binding));
    if (applyPaintLockConfig(cfg)) {
      // 잠금 값이 바뀌었으므로 현재 맵의 잠금 셀 집합을 다시 계산한다
      recomputeLockedCells();
      if (paintLockConfig.enabled) {
        console.info('[Map Editor] paint rules:', paintLockConfig.blocking_values, paintLockConfig.from_overlay);
      }
    }
    updatePaintLockIndicator();
  } catch (e) { degrade(e && e.message ? e.message : String(e)); }
}

// 잠금 상태를 툴바에 상시 노출한다 — "확인 못 함"이 화면에 남아야 신호가 산다.
function updatePaintLockIndicator() {
  const el2 = document.getElementById('paint-lock-indicator');
  if (!el2) return;
  const stale = paintLockConfig.source === 'stale';
  const on = paintLockConfig.enabled;
  if (!stale && !on) { el2.style.display = 'none'; return; }
  el2.style.display = '';
  el2.className = 'plock-chip' + (stale ? ' stale' : '');
  el2.textContent = stale
    ? '⚠ 잠금 규칙 미확인'
    : `🔒 잠금 ${paintLockConfig.blocking_values.join(',')}`;
  el2.title = stale
    ? '페인트 잠금 규칙 조회에 실패해 직전 값을 쓰고 있습니다 — 맵을 다시 로드하면 재조회합니다.'
    : '이 값의 셀은 편집할 수 없습니다 (서버 선언).';
}

// 현재 gridData 기준으로 값-잠금 셀 집합 재구성 (선언이 바뀌었을 때)
function recomputeLockedCells() {
  loadedFCells = new Set();
  if (!paintLockConfig.enabled) { scheduleRenderGridCanvas(); return; }
  Object.keys(gridData).forEach(k => { if (isLockedValue(gridData[k])) loadedFCells.add(k); });
  scheduleRenderGridCanvas();
}

// 초기 DOE — **분기는 둘뿐이다** (사용자 지시 2026-07-28):
//
//   그 (ref_table, map_key)에 registry 행이 있다  →  **그것만** 로드
//   없다                                        →  **빈 DOE 한 줄**, VALUE = 1
//
// 세 번째 분기는 없다. 테이블 전체 어휘 시딩도, 네 개짜리 기본 팔레트(1/0/2/3
// GOOD/FAIL/EMPTY/REWORK)도, `map_legend_<table>` 캐시 폴백도 전부 사라졌다. 쓰는 사람에게는
// **자기가 넣은 적 없는 값이 네 개 있는 화면**이었고, 그것은 결함과 구별되지 않는다 —
// 실제로 두 번 결함으로 보고됐다. 아무도 요청하지 않았는데 결함처럼 읽히는 기능은 결함이다.
//
// STACK·자재는 비워 둔다. 사용자가 치기 전에 층 구조를 지어내면 그것이 곧 "사용자가 만든 적
// 없는 계획"이 되고, 이 도메인이 없애려는 결함 그 자체다. 비어 있으면 V5가 그 사실을 말한다.
// [U6] The "no registry rows" seed is SERVED now: paint-rules carries the site's declared
// `default_legend` (map_overlay_config.json), and that declaration is what an empty map
// opens with. Undeclared/unreachable → the one empty row below. That is not a third
// branch — it is the "nothing declared" arm of the same two-branch rule, and it happens
// to coincide with the current live declaration. The client never invents richer rows.
const EMPTY_DOE_SEED = [
  { value: '1', desc: '', color: '#10b981' }
];

function defaultLegendRows() {
  const declared = (overlayContract && Array.isArray(overlayContract.defaultLegend))
    ? overlayContract.defaultLegend : null;
  return (declared && declared.length > 0) ? declared : EMPTY_DOE_SEED;
}

// [U6] Declared default_legend row for one value — the lookup dictionary consulted when
// a value is AUTO-added to the legend (autopaint E1/E2, unknown pasted/imported values,
// map-load legend build). Declared row wins color/desc; else the palette rule.
function declaredLegendRow(value) {
  const rows = (overlayContract && Array.isArray(overlayContract.defaultLegend))
    ? overlayContract.defaultLegend : [];
  return rows.find(r => r && String(r.value) === String(value)) || null;
}

// ----------------------------------------------------
// Split Registry (map_split_registry) — legend의 서버 영속화
// value description = 실험 split 조건의 자연어 기록.
// 서버(제네릭 테이블 API)가 SSOT, localStorage는 오프라인 캐시로 강등.
//
// [M2.6] **하나의 값 = 하나의 행 = 하나의 DOE.** map_doe / map_doe_source는 폐기됐고
// 구간(bands)과 knob이 이 행으로 접혀 들어왔다. 그래서 이 파일이 DOE의 **유일한 기록자**다 —
// 같은 행을 두 모듈이 쓰면 replace_map이 서로의 컬럼을 지운다.
// ----------------------------------------------------
const SPLIT_REGISTRY_TABLE = 'map_split_registry';

let legendMeta = {}; // legend value -> { updated_by, updated_at } (registry 조회/저장 메타)
// (자동 저장 디바운스 타이머는 2026-07-28에 제거됐다 — 서버 쓰기는 Push 하나뿐이다)
// { table, mapKey, fingerprint } | null - the ONE map whose registry rows we have
// actually read, together with what they were when we read them. One object because
// it is one claim: "the screen came from this map's rows, and they looked like this".
//   * grant of `replace_map` authority - only a legend that came from this map's own
//     registry may be used to replace it;
//   * baseline of the concurrency check - the write re-reads and refuses if the
//     server no longer matches, instead of silently erasing another session's rows.
// Cleared whenever the claim stops being true (table switch, failed/truncated read,
// map unloaded).
let legendReplaceScope = null;
// value -> legendRowSignature at the moment the table-wide vocabulary seeded it. Lets
// `reconcileVocabClaims` DERIVE "the user changed this row" instead of trusting every
// edit path to say so. Rebuilt on each vocabulary load; empty means nothing was borrowed.
let legendVocabularySeed = new Map();
// { table, mapKey } | null - another session changed this plan under us. Blocks every
// registry write for that map until a reload puts the screen back on server state.
// Degrading to an upsert instead would push our stale bands over theirs.
let legendConflict = null;
// Last registry write outcome, surfaced by the panel header (getPlanSaveState).
let legendSaveState = { status: 'idle', at: '', error: '' };

function debounce(func, wait = 200) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

// Initialize DOM elements when loaded
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  // [V1 effort instrument] First, so no press or keystroke on this page is missed. The
  // module's listeners are capture-phase and passive - they never preventDefault, never
  // stopPropagation, and therefore cannot reorder or short-circuit anything below.
  // Counting is page-wide by design: a click that MISSES a tiny control is real wasted
  // effort and must score, which is precisely the waste the queued DOE round will remove.
  startSession();
  installGlobalListeners();
  // Leaving this page for another screen (「← Back to Grid」) is a full page load - nothing
  // survives it. The shared helper owns the href -> route-id mapping and skips downloads
  // and external links, so this file keeps no link table of its own. `from` is the static
  // page route: leaving the editor is context-losing at any frame depth, so the depth
  // qualifier would change the analysis label but never the score.
  installNavLinkCounting(ROUTE_MAIN);
  initDOMElements();
  initMouseDragEvents();
  // [재설계 v2] Legend & DOE 패널 — 컨트롤러 주입 (함수 선언은 호이스팅됨).
  //   계획이라는 별도 개체는 없다. 패널은 "지금 열린 맵의 legend"를 편집할 뿐이고,
  //   그 legend 행이 곧 DOE다. 모드·모달·플로팅 바는 전부 폐기됐다.
  initTransferPlan({
    // legend(= DOE) 원천은 map_editor다 — 패널은 이 관문으로만 변조한다.
    // ⚠️ 깊은 복사다: bands/knobs는 배열이라 얕게 넘기면 패널의 제자리 수정이
    //    영속화를 거치지 않고 원본을 바꿔 "화면은 됐는데 저장이 안 된" 상태가 된다.
    getLegend: () => cloneLegend(legend),
    getPlanSaveState,
    getActiveBrush: () => activeBrush,
    getCounts: computeLegendCounts,
    // Selection alone changes no counts - updateLegendCounts here scanned every grid
    // cell (O(cells)) on each mousedown in the panel and added visible click latency.
    // Counts refresh where they actually change: the paint paths.
    setBrush: (v) => { selectBrush(String(v)); },
    addLegendRow: addLegendRowForPanel,
    updateLegendRow: updateLegendRowForPanel,
    deleteLegendRow: deleteLegendRowForPanel,
    // 맵 정체성 (좌측 패널이 단일 원천 — stage는 여기서 유도된다)
    getMapContext: () => ({
      table: selectedTable,
      mapKey: getCurrentMapKey(),
      loaded: loadedIdentity ? { ...loadedIdentity } : null,
      depth: editorFrames.length,
      parent: editorFrames.length > 0 ? frameTitle(editorFrames[editorFrames.length - 1]) : null,
    }),
    // 편집 스택 (자재 맵 왕복)
    openMapFrame,
    goBack: popMapFrame,
    // 오버레이 (기존 엔진 그대로)
    addOverlayForSource,
    listOverlays: listOverlayLayers,
    removeOverlay: removeOverlayLayer,
    toggleOverlay: toggleOverlayLayer,
    clearOverlays: clearOverlayLayers,
    // 자재 맵 조회 헬퍼
    fetchMapKeyColumns,
    // [7b] The panel composes map keys too (material id -> that material's map). It gets the
    // key columns AND their declared types from the one cached schema read, plus THE
    // canonicaliser itself — a second copy over there would be a second opinion about map
    // identity, which is the defect this round exists to remove.
    fetchMapKeySpec,
    canonicalKeyValue,
    probeMapExists,
  });
  await loadTablesList();
  // Refresh must land back on the last open map, not the initial screen. Runs after the
  // table list exists; walks the manual LOAD path so the DOE/cell draft precedence
  // (readDoeDraft inside loadExistingMap) does its existing job on the reopened map.
  await restoreLastOpenMap();
});

// Cache DOM Elements
const el = {};
function initDOMElements() {
  el.tableSelect = document.getElementById('map-table-select');
  el.metadataContainer = document.getElementById('metadata-fields-container');
  el.gridCols = document.getElementById('grid-cols');
  el.gridRows = document.getElementById('grid-rows');
  el.gridStartX = document.getElementById('grid-start-x');
  el.gridStartY = document.getElementById('grid-start-y');
  el.gridYInvert = document.getElementById('grid-y-invert');
  el.showAnnotations = document.getElementById('show-annotations');

  el.physWaferDia = document.getElementById('phys-wafer-dia');
  el.physChipX = document.getElementById('phys-chip-x');
  el.physChipY = document.getElementById('phys-chip-y');
  el.physOffsetX = document.getElementById('phys-offset-x');
  el.physOffsetY = document.getElementById('phys-offset-y');
  el.physEdgeMargin = document.getElementById('phys-edge-margin');
  el.btnApplyPhysGeom = document.getElementById('btn-apply-phys-geom');

  el.colMapX = document.getElementById('col-map-x');
  el.colMapY = document.getElementById('col-map-y');
  el.colMapVal = document.getElementById('col-map-val');

  el.btnLoadMap = document.getElementById('btn-load-map');
  // 오버레이 전용 소스 선택기 — 메인 테이블 셀렉터(el.tableSelect)와 **다른 DOM**이며,
  // 이쪽을 조작해도 switchTable/selectedTable/gridData는 절대 건드리지 않는다.
  el.overlaySrcTable = document.getElementById('overlay-src-table');
  el.overlaySrcKey = document.getElementById('overlay-src-key');
  el.overlaySrcKeyList = document.getElementById('overlay-src-key-list');
  el.btnAddOverlay = document.getElementById('btn-add-overlay');
  el.btnAddLegend = document.getElementById('btn-add-legend');
  el.legendList = document.getElementById('legend-list');

  el.activeBrushVal = document.getElementById('active-brush-val');
  el.gridStatusCoords = document.getElementById('grid-status-coords');
  el.btnSetOrigin = document.getElementById('btn-set-origin');
  el.btnSelectE1 = document.getElementById('btn-select-e1');
  el.btnSelectE2 = document.getElementById('btn-select-e2');
  el.btnAutoPaintE1E2 = document.getElementById('btn-autopaint-e1e2');
  el.btnFillSelected = document.getElementById('btn-fill-selected');
  el.btnClearSelected = document.getElementById('btn-clear-selected');
  el.btnClearGrid = document.getElementById('btn-clear-grid');
  el.btnFillGrid = document.getElementById('btn-fill-grid');
  el.btnPushMap = document.getElementById('btn-push-map');
  // [2] 규격만 저장. Push의 이웃이지 대체가 아니다 — 셀을 쓰지 않는 쪽이다.
  el.btnSaveMapSpec = document.getElementById('btn-save-map-spec');

  el.presetSelect = document.getElementById('preset-select');
  el.btnSavePreset = document.getElementById('btn-save-preset');
  el.btnDeletePreset = document.getElementById('btn-delete-preset');
  // [M4②] 유효 다이 지정 — 물리 규격 블록의 한 줄. 오버레이 소스 선택기와 같은 이유로
  // **별도 DOM**이다: 이쪽을 조작해도 switchTable/selectedTable/gridData는 건드리지 않는다.
  // [1-a] The table picker is GONE — the storage table is fixed to `VALID_DIE_TABLE`.
  // [1-b] 🎯 APPLY·💾 SAVE 두 버튼도 GONE. 남는 컨트롤은 키 칸 하나뿐이다.
  el.validDieRefKey = document.getElementById('valid-die-ref-key');
  el.validDieRefList = document.getElementById('valid-die-ref-list');
  el.validDieRefSelect = document.getElementById('valid-die-ref-select');

  el.btnSelectMenu = document.getElementById('btn-select-menu');
  el.selectMenuDropdown = document.getElementById('select-menu-dropdown');
  el.btnOpsMenu = document.getElementById('btn-ops-menu');
  el.opsMenuDropdown = document.getElementById('ops-menu-dropdown');
  el.selectionActionsContainer = document.getElementById('selection-actions-container');
  el.btnCopyExcel = document.getElementById('btn-copy-excel');
  el.copyHeaderToggle = document.getElementById('map-copy-header-toggle');

  el.choiceModal = document.getElementById('choice-modal');
  el.btnChoiceStandard = document.getElementById('btn-choice-standard');
  el.btnChoiceCurrent = document.getElementById('btn-choice-current');
  el.btnChoiceCancel = document.getElementById('btn-choice-cancel');

  el.gridCanvas = document.getElementById('grid-canvas');
  el.waferCanvas = document.getElementById('wafer-grid-canvas');
  el.gridWrapper = document.getElementById('grid-wrapper');
  el.gridNotch = document.getElementById('grid-notch');
  el.mapWorkspace = document.getElementById('map-workspace');
  el.sideIndicator = document.getElementById('side-indicator');
  el.cellAspectNote = document.getElementById('cell-aspect-note');

  // Fit the (square) grid to the available workspace on any size change.
  // ResizeObserver also covers container-only resizes (split panels) that window 'resize' misses.
  window.addEventListener('resize', fitGridToWorkspace);
  if (window.ResizeObserver && el.mapWorkspace) {
    new ResizeObserver(() => fitGridToWorkspace()).observe(el.mapWorkspace);
  }
  initPlanSidebarResizer();
  updateSideIndicator();

  // Bind Events
  el.tableSelect.addEventListener('change', (e) => {
    // [V1 effort instrument] Counted on the USER's handler, not inside switchTable():
    // the boot paths (loadTablesList's initial pick, restoreLastOpenMap) call that
    // function directly and must not score - the session has not moved anywhere yet.
    // switchTable assigns selectedTable before its try block, so the move always happens.
    countNav(effortRoute(), effortRoute());
    switchTable(e.target.value);
  });

  if (el.btnSelectMenu && el.selectMenuDropdown) {
    el.btnSelectMenu.addEventListener('click', (e) => {
      e.stopPropagation();
      const isVisible = el.selectMenuDropdown.style.display === 'flex';
      el.selectMenuDropdown.style.display = isVisible ? 'none' : 'flex';
      if (el.opsMenuDropdown) el.opsMenuDropdown.style.display = 'none';
    });
  }

  if (el.btnOpsMenu && el.opsMenuDropdown) {
    el.btnOpsMenu.addEventListener('click', (e) => {
      e.stopPropagation();
      const isVisible = el.opsMenuDropdown.style.display === 'flex';
      el.opsMenuDropdown.style.display = isVisible ? 'none' : 'flex';
      if (el.selectMenuDropdown) el.selectMenuDropdown.style.display = 'none';
    });
  }

  document.addEventListener('click', () => {
    if (el.selectMenuDropdown) el.selectMenuDropdown.style.display = 'none';
    if (el.opsMenuDropdown) el.opsMenuDropdown.style.display = 'none';
  });

  if (el.selectMenuDropdown) {
    el.selectMenuDropdown.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }
  if (el.opsMenuDropdown) {
    el.opsMenuDropdown.addEventListener('click', (e) => {
      e.stopPropagation();
    });
  }

  if (el.presetSelect) {
    el.presetSelect.addEventListener('change', loadSelectedPreset);
  }
  if (el.btnSavePreset) {
    el.btnSavePreset.addEventListener('click', saveCustomPreset);
  }
  if (el.btnDeletePreset) {
    el.btnDeletePreset.addEventListener('click', deleteCustomPreset);
  }
  // [M4②] 지정 칸. 자동완성 목록은 포커스 시 1회 지연 로드한다 — 조회 동선은 무마찰이다.
  //
  // ── [1-b] 무엇이 적용을 일으키는가 (사용자 지시 2026-08-04, 🎯 APPLY 삭제) ─────────────
  // 사용자의 불만은 한 문장이다: **"타이핑하면서 중간에 바뀌는게 불편했던것."** 그러니
  // 판정 기준도 하나다 — 그 제스처가 「확정」인가, 아니면 확정이 아닌 것의 부작용인가.
  //
  //   select `change`   = 확정이다. 목록에서 하나를 고르는 행위는 이산적이고 되돌릴 것이
  //                       없으며, 바로 위 「⚙️ Geometry Presets」가 이미 같은 규칙으로 산다.
  //                       APPLY가 있던 자리를 여기가 가져간다.
  //   입력칸 `keydown` Enter = 확정이다. 한 줄 입력칸에서 Enter는 「이 값이다」 외의 뜻이 없다.
  //
  // 🔴 **입력칸에 `change`(=blur)를 달지 않는다.** `change`는 확정처럼 보이지만 실제로는
  //    「여기서 나갔다」에서도 난다 — 값을 확인하려고 캔버스를 클릭하거나 Tab으로 다음 칸에
  //    가는 것만으로 기하 메타가 갈아끼워지고 셀이 다시 앉는다. 3-a가 없앤 그 동작이다.
  // 🔴 **`input`에도 달지 않는다.** 그것이 곧 사용자가 말한 "타이핑 중"이다.
  // 🔴 **IME 조합 중의 Enter는 Enter가 아니다.** 한글 조합을 확정하는 Enter까지 적용으로
  //    읽으면, 한국어 UI에서 정확히 저 불만이 되돌아온다. `isComposing`/keyCode 229로 뺀다.
  if (el.validDieRefKey) {
    el.validDieRefKey.addEventListener('focus', populateValidDieRefList);
    // [1-a] 입력칸을 직접 고쳤으면 어느 컨트롤이 맞는지 다시 판정한다 — 목록에 없는 키를
    //       타이핑하면 select로는 표현할 수 없으므로 입력칸이 유지돼야 한다.
    //       **다시 그릴 뿐 적용하지 않는다.**
    el.validDieRefKey.addEventListener('input', renderValidDieKeyControl);
    el.validDieRefKey.addEventListener('keydown', (e) => {
      if (!e || e.key !== 'Enter') return;
      if (e.isComposing || e.keyCode === 229) return;
      onValidDieRefChanged();
    });
  }
  // [1-b] 드롭다운은 값을 옮기고 **곧바로 적용한다.** 값의 정본은 `#valid-die-ref-key`
  //       하나이므로 순서가 계약이다: 먼저 그 칸에 적고, 그 다음에 적용을 부른다.
  //       `onValidDieRefChanged`는 `validDieRefFromControls()`로 그 칸을 읽으므로,
  //       순서가 뒤집히면 직전 값이 적용된다.
  if (el.validDieRefSelect) {
    el.validDieRefSelect.addEventListener('change', () => {
      if (el.validDieRefKey) el.validDieRefKey.value = el.validDieRefSelect.value;
      onValidDieRefChanged();
    });
  }
  fetchAndRenderPresets();
  // [1-a] 프리셋 목록과 **같은 시점**에 채운다. 종전에는 입력칸 `focus`가 유일한 계기였는데,
  //       드롭다운은 focus 전에 이미 보이므로 그 시점으로는 영영 비어 있게 된다.
  populateValidDieRefList();

  const inputsToRedraw = [el.gridCols, el.gridRows, el.gridStartX, el.gridStartY, el.gridYInvert, el.showAnnotations];
  inputsToRedraw.forEach(input => {
    input.addEventListener('change', () => {
      // Validate bounds
      if (input === el.gridCols || input === el.gridRows) {
        let v = parseInt(input.value, 10);
        if (isNaN(v) || v < 1) input.value = 1;
        if (v > 100) input.value = 100;

        // Auto-disable annotation display on large grids (>400 cells) to prevent rendering bottleneck
        const currentCols = parseInt(el.gridCols.value, 10) || 10;
        const currentRows = parseInt(el.gridRows.value, 10) || 10;
        if (currentCols * currentRows > 400 && el.showAnnotations) {
          el.showAnnotations.checked = false;
        }
        // [규칙 ④] 격자 치수도 기하 편집이다 — **물리 규격 한 칸을 고치는 것과 같은 연산**이라
        // 반응도 같은 함수 하나다(§reseatCellsToStoredCoords · §onPhysicalGeometryEdit).
        //
        // 🔴 치수가 바뀌면 두 가지가 함께 움직이고, 저장 좌표가 갈리는 것은 그 **차이**다:
        //    ① 원점 상자 — 원의 반지름은 칸 수로 고정인데 중심이 `visualCols / 2`라 격자가
        //       넓어지면 원 전체가 옆으로 미끄러진다.
        //    ② 다이 인덱스 자체 — `getDieIndex`가 웨이퍼 중심 기준이라
        //       (`colVisual − (visualCols − 1) / 2` + 짝수 보정) **셀의 키**도 함께 바뀐다.
        //    둘이 같은 양만큼 움직이면 서로 상쇄돼 아무 일도 없고, 어긋나면 **격자 전체**가
        //    다시 번호를 받는다. 실측(2026-07-31, 생산 프레임 3개 × 각 축 ±1~±3): 36건 중
        //    16건이 어긋났고, 어긋난 16건은 예외 없이 셀의 **100%**였다(261/261 · 273/273 ·
        //    461/461). 나머지 20건에서 이 반응이 옮기는 셀은 **측정된 0**이다.
        // ⚠️ "상자가 안 움직였으면 반응할 것도 없다"는 참이 아니다 — QERWER 23→22열은
        //    `box.minC`가 2에서 그대로인데 261칸 전부가 다시 번호를 받았다.
        // ⚠️ 이 호출은 `#grid-y-invert`·`#grid-start-x/y`(같은 배열에 있는 규칙 ⑤·START)에는
        //    닿지 않는다. 반응 자신도 그 축이 다르면 거절하지만, 애초에 부르지 않는다.
        reseatCellsToStoredCoords(cellsSeatedUnder);
      } else if (input === el.gridStartX || input === el.gridStartY) {
        let v = parseInt(input.value, 10);
        if (isNaN(v)) input.value = 0;
      }
      scheduleRenderGridCanvas();
    });
  });

  // 메인 Load는 언제나 교체 로드다 (오버레이 분기 없음 — 겹치기는 전용 블록이 담당)
  el.btnLoadMap.addEventListener('click', async () => {
    // [V1 effort instrument] Same reason as the table dropdown: instrument the user's
    // handler, never loadExistingMap() itself - restoreLastOpenMap (boot) and
    // openMapFrame (which counts its own frame push) both call it and must not
    // double-count. Scored AFTER the result because a load the user cancelled or one
    // that failed moved no screen; the press itself is already counted as a mouse event.
    const from = effortRoute();
    const r = await loadExistingMap();
    if (r && !r.cancelled && !r.error) countNav(from, effortRoute());
  });
  if (el.btnAddOverlay) el.btnAddOverlay.addEventListener('click', handleAddOverlayClick);
  if (el.overlaySrcKey) el.overlaySrcKey.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); handleAddOverlayClick(); }
  });
  // [키 자동완성] 유효 다이 지정 칸과 **같은 규칙**이다: 포커스 시 1회 지연 로드, 타이핑마다
  // 네트워크를 타지 않는다. 소스 테이블을 바꾸면 목록의 모집단이 바뀌므로 다시 읽는다 —
  // 이전 테이블의 키가 남아 있으면 **낡아 보이지 않는 낡은 목록**이 된다.
  if (el.overlaySrcKey) el.overlaySrcKey.addEventListener('focus', populateOverlayKeyList);
  if (el.overlaySrcTable) el.overlaySrcTable.addEventListener('change', populateOverlayKeyList);
  // [키 자동완성] 메인 로드의 메타 입력칸은 테이블마다 **재생성**된다. 그래서 노드가 아니라
  // **컨테이너 한 곳**에 위임으로 단다 — 재생성이 몇 번 일어나도 리스너는 이 두 개뿐이고,
  // 새로 만들어진 입력칸도 별도 배선 없이 그대로 동작한다. (`focus`는 버블링하지 않으므로
  // `focusin`이다.) `input`은 서버가 목록을 **자른 경우에만** 다시 묻는다 — 완전한 목록의
  // 좁히기는 브라우저 몫이라 요청이 0회다.
  if (el.metadataContainer) {
    el.metadataContainer.addEventListener('focusin', onMetaInputSuggest);
    el.metadataContainer.addEventListener('input',
      debounce(onMetaInputSuggest, KEY_SUGGEST_DEBOUNCE_MS));
  }
  const btnClearOv = document.getElementById('btn-clear-overlays');
  if (btnClearOv) btnClearOv.addEventListener('click', clearOverlayLayers);
  renderOverlayList();
  // 잠금 선언은 테이블별이므로 switchTable에서도 재조회한다
  if (el.btnAddLegend) el.btnAddLegend.addEventListener('click', () => addLegendRowForPanel());
  el.btnSetOrigin.addEventListener('click', () => {
    isOriginMode = !isOriginMode;
    if (isOriginMode) {
      el.btnSetOrigin.classList.add('active');
      el.btnSetOrigin.style.borderColor = 'var(--color-secondary)';
      el.btnSetOrigin.style.color = 'var(--color-secondary)';
      el.gridCanvas.classList.add('origin-mode-active');
    } else {
      el.btnSetOrigin.classList.remove('active');
      el.btnSetOrigin.style.borderColor = '';
      el.btnSetOrigin.style.color = '';
      el.gridCanvas.classList.remove('origin-mode-active');
    }
  });
  el.btnClearGrid.addEventListener('click', clearGrid);
  el.btnFillGrid.addEventListener('click', fillGrid);
  el.btnPushMap.addEventListener('click', pushMapData);
  if (el.btnSaveMapSpec) el.btnSaveMapSpec.addEventListener('click', saveMapSpecOnly);
  if (el.btnCopyExcel) el.btnCopyExcel.addEventListener('click', copyGridToExcel);
  // [F1ⓑ] 되붙이기. 새 버튼도 새 메뉴 항목도 아니다 — 클립보드는 네이티브 `paste` 이벤트에서만
  // 읽을 수 있으므로(운영은 평문 HTTP = `navigator.clipboard` 부재) 동선은 Ctrl+V 하나뿐이다.
  // 순 추가 컨트롤 0개. DOE 패널의 붙여넣기가 먼저 처리한 이벤트는 `defaultPrevented`로 비킨다.
  document.addEventListener('paste', onMapGridPaste);

  // [F1ⓐ] 체크박스 상태의 영속화. **새 저장 기계장치를 만들지 않는다** — 그리드 화면의
  // `Copy Header` 토글이 이미 `localStorage['copyHeader']`에 같은 방식으로 붙어 있고
  // (`main.js:90` 읽기 / `main.js:528` 쓰기), 이건 그 프리미티브의 맵 화면 사본이다.
  // 초안(`saveDoeDraft`)에 얹지 않은 이유는 두 가지다: 초안은 지문이 어긋나면 **적용되지
  // 않고**, ⚡ Push 성공 시 `clearDoeDraft`가 지운다 — 사용자 설정이 저장 한 번에
  // 조용히 꺼지는 동작이 된다.
  if (el.copyHeaderToggle) {
    try { el.copyHeaderToggle.checked = localStorage.getItem(COPY_HEADER_KEY) === 'true'; }
    catch (e) { /* 저장소를 못 읽어도 기본값(꺼짐)으로 동작한다 */ }
    el.copyHeaderToggle.addEventListener('change', () => {
      try { localStorage.setItem(COPY_HEADER_KEY, String(el.copyHeaderToggle.checked)); }
      catch (e) { /* 기억하지 못할 뿐, 이번 복사는 체크 상태대로 나간다 */ }
    });
  }
  if (el.btnApplyPhysGeom) el.btnApplyPhysGeom.addEventListener('click', applyPhysicalGeometry);

  // Physical input triggers: use change event for typing completion and scheduleRenderGridCanvas for rAF throttling
  //
  // [규칙 ④] 규격 한 칸을 고치는 것도 원점 상자를 움직인다. 유효 다이 선언이 없는 맵에서
  // 유효 다이 영역은 곧 웨이퍼 원이므로, 여기서 일어나는 일은 참조를 지정하는 것과 **같은
  // 연산**이다 — 그래서 같은 함수를 부른다(새 컨트롤 0개, 새 확인창 0개).
  //
  // ⚠️ 이 리스너는 변경 **전** 상태를 스스로 잡을 수 없다: `input`/`change`는 DOM 값이 이미
  //    바뀐 뒤에 뜬다. 그래서 직전 렌더가 남긴 기록(`cellsSeatedUnder`)이 옛 좌표계다.
  //
  // ═══════════════════════════════════════════════════════════════════════════════
  // [규칙 ④-b] **OFFSET은 CHIP 피치를 넘지 못한다.**
  //
  // 🔴 **오프셋의 뜻은 하나이고, 두 소비자가 갈리지 않는다.** 오프셋은 다이 격자를 웨이퍼
  //    원에 대해 물리 mm만큼 밀어 놓는다. 정본은 서버다
  //    (`PhysicalWaferEngine.get_cell_physical_mm`: `x_mm = (c − cc)·chip_x + off_x`).
  //    이 파일의 `getScreenShift`는 회전 4 × 면 2 = 8조합 전부에서 서버의
  //    `map_overlay._frame_phys_params` 표와 항별로 같은 답을 낸다 — 측정: 같은 칸의
  //    웨이퍼 mm가 off 0/5/11에서 0.000/5.000/11.000으로 서버 식과 글자 그대로 일치.
  //    그러므로 사용자가 본 드리프트는 **정의의 불일치가 아니다.**
  //
  // 🔴 **피치를 넘는 오프셋은 새 기하가 아니라 번호 다시 매기기다.** 다이 격자는 피치 주기라
  //    `off += chipX`는 칸 c를 예전 칸 c+1의 자리에 앉힌다: 다이가 놓이는 mm 집합은 글자
  //    그대로 같고 인덱스만 1씩 옮겨간다(측정: off 0/11/22에서 캔버스 칸 14가 다이 인덱스
  //    0/1/2, mm 0/11/22). 표현할 수 있는 기하는 `|off| ≤ 피치` 안에 전부 들어 있다.
  //
  // 🔴 **드리프트의 정체는 그 옮겨간 번호다.** 원점 상자는 **선언된 격자 안에서만** 훑는다 —
  //    클라(`getWaferBoundingBox`의 `r < visualRows / c < visualCols`)도 서버
  //    (`WaferMapCoordinateTransformer.get_wafer_bounding_box`의 같은 두 줄)도 같다.
  //    그런데 렌더 루프는 캔버스를 덮을 만큼 격자를 **연장해서** 그린다(§renderGridCanvas의
  //    `startC`/`endC`). 그래서 오프셋이 커지면 원 안의 다이는 c < 0에 계속 나타나는데 상자는
  //    0에서 멈추고, 그 차이가 그대로 ORIGIN과 유효 다이 사이의 거리가 된다.
  //    측정(dia 300 · chip 11×13 · 29×25): off 33mm에서 1칸, 50mm에서 3칸, 80mm에서 6칸.
  //    ⚡ 그리고 저장 좌표가 **같은 수만큼 통째로** 어긋난다(die(−3,−2)의 x가 10 → 7).
  //    화면은 멀쩡한데 값이 틀리는, 이 도메인이 존재하는 그 결함이다.
  //
  // 🔴 **그래서 상자를 넓히지 않고 오프셋을 막는다.** 상자를 무한 격자로 넓히면 서버의 상자와
  //    갈라져 이음매가 깨진다(불변식 ①). 반대로 파생 격자는 `ceil(2R/chip) + 2`로 **양쪽에
  //    한 칸씩** 여유를 두도록 정의돼 있으니, 피치 1개가 곧 그 예산이다. 측정된 드리프트
  //    개시점은 2피치(≈23.7mm)라 1피치 상한은 2배 여유를 남긴다.
  //
  // ⚠️ **선언된 메타는 손대지 않는다.** 서버가 준 프레임을 조용히 고쳐 쓰면 그 맵의 저장
  //    좌표가 통째로 재해석된다(불변식 ③). 그래서 이 관문은 **사용자가 값을 확정할 때**
  //    (`change`)만 작동하고, 프리셋·메타 적용 경로는 지나간다. 라이브 프리셋의 최대
  //    오프셋은 10mm(chip 11mm)라 오늘 이 관문에 걸리는 저장 값은 없다.
  // ⚠️ `input`에는 걸지 않는다 — 타이핑 중에 자르면 "12"를 치는 도중 "1"에서 잘린다.
  // ⚠️ `physNum`이 아니라 DOM을 직접 읽는다. 이것은 **화면 컨트롤**의 관문이고, 프레임 창
  //    (소스 메타)의 규격은 절대 고쳐 쓰지 않는다.
  // ═══════════════════════════════════════════════════════════════════════════════
  const clampOffsetToPitch = (input, pitchInput, label, pitchLabel) => {
    if (!input || !pitchInput) return null;
    const v = parseFloat(input.value);
    const pitch = Math.abs(parseFloat(pitchInput.value));
    if (!Number.isFinite(v) || !Number.isFinite(pitch) || pitch <= 0) return null;
    if (Math.abs(v) <= pitch) return null;
    const next = v > 0 ? pitch : -pitch;
    input.value = String(next);
    return `${label} ${v} → ${next} (${pitchLabel} ${pitch}mm)`;
  };

  const onPhysicalGeometryEdit = (ev) => {
    // [D1] 조작자가 칩 칸을 고쳤다면 그 값은 이제 **선언이다** — 합성 규격 표지를 끈다.
    //      칩 칸에서만 끈다: OFFSET이나 마진을 만지는 것은 칩 피치를 잰 것이 아니고,
    //      거기서까지 끄면 아무도 선언하지 않은 피치가 선언으로 승격된다.
    if (ev && ev.target && (ev.target === el.physChipX || ev.target === el.physChipY)) {
      markGeometryAutoRegistered(false);
    }
    if (!ev || ev.type === 'change') {
      const capped = [
        clampOffsetToPitch(el.physOffsetX, el.physChipX, 'OFFSET X', 'CHIP X'),
        clampOffsetToPitch(el.physOffsetY, el.physChipY, 'OFFSET Y', 'CHIP Y'),
      ].filter(Boolean);
      if (capped.length > 0) {
        showToast(`OFFSET은 CHIP 크기를 넘을 수 없습니다 — ${capped.join(' / ')}. `
          + '칩 피치를 넘는 오프셋은 같은 격자에 번호만 다시 매기고, '
          + 'ORIGIN을 유효 다이 영역 밖으로 밀어냅니다.', 'warning');
      }
    }
    reseatCellsToStoredCoords(cellsSeatedUnder);
    scheduleRenderGridCanvas();
  };
  [el.physWaferDia, el.physChipX, el.physChipY, el.physOffsetX, el.physOffsetY, el.physEdgeMargin].forEach(input => {
    if (input) {
      input.addEventListener('change', onPhysicalGeometryEdit);
      input.addEventListener('input', onPhysicalGeometryEdit);
    }
  });

  if (el.btnSelectE1) el.btnSelectE1.addEventListener('click', () => selectEdgeCells(1));
  if (el.btnSelectE2) el.btnSelectE2.addEventListener('click', () => selectEdgeCells(2));
  if (el.btnAutoPaintE1E2) el.btnAutoPaintE1E2.addEventListener('click', autoPaintE1E2);
  if (el.btnFillSelected) el.btnFillSelected.addEventListener('click', fillSelectedCells);
  if (el.btnClearSelected) el.btnClearSelected.addEventListener('click', clearSelectedCells);

  // Dynamic Metadata Inputs change triggers
  el.colMapX.addEventListener('change', () => {
    renderMetadataInputs();
    scheduleRenderGridCanvas();
  });
  el.colMapY.addEventListener('change', () => {
    renderMetadataInputs();
    scheduleRenderGridCanvas();
  });
  el.colMapVal.addEventListener('change', () => {
    renderMetadataInputs();
    scheduleRenderGridCanvas();
  });

  // Rotation Buttons
  document.querySelectorAll('.btn-rot').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.btn-rot').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentRotation = parseInt(btn.dataset.rot, 10);
      scheduleRenderGridCanvas();
    });
  });

  // Wafer Side Radios
  document.querySelectorAll('input[name="wafer-side"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      currentSide = e.target.value;
      updateSideIndicator();
      scheduleRenderGridCanvas();
    });
  });

  // Prevent right-click context menu on canvas
  el.gridCanvas.addEventListener('contextmenu', (e) => e.preventDefault());
}

function getGridCellObject(c, r, visualCols, visualRows, physConfig, width, height) {
  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert ? el.gridYInvert.checked : false;

  // 🔴 (0,0)이 어느 칸인가는 **원점 상자**가 답한다 — `getCanvasCellFromDb`의 본문에
  //    dbX=0, dbY=0을 대입한 그 식이고, 상자도 같은 `getWaferBoundingBox(회전, 면)` 하나다.
  //    새 유도가 아니라 **같은 식의 특수값**이므로 두 갈래로 갈릴 수 없다.
  // ⚠️ 여기서 `getCanvasCellFromDb`를 **부르지 않는다.** 이 함수를 소스 텍스트에서
  //    슬라이스해 vm 샌드박스로 실행하는 하네스가 둘이고(company_roundtrip ·
  //    copy_header_count), 모듈 전역 의존이 하나 늘 때마다 그 둘이 ReferenceError로 죽는다 —
  //    실측: `da8f390`이 이 한 줄로 둘을 죽였고, 같은 커밋의 `getWaferBoundingBox`
  //    주석(§1903)이 정확히 그 이유로 헬퍼 추출을 거부하고 있었다.
  const zeroBox = getWaferBoundingBox(null, currentRotation, currentSide);
  const zeroC = 0 - startX + zeroBox.minC;
  const zeroR = invertY ? (zeroBox.maxR - (0 - startY)) : (0 - startY + zeroBox.minR);
  const hasZeroZero = (zeroC >= 0 && zeroC < visualCols) && (zeroR >= 0 && zeroR < visualRows);

  const physical = getDieIndex(null, c, r, cols, rows, currentRotation, currentSide);
  const visual = getDbCoords(null, c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
  const coordKey = `${physical.x}_${physical.y}`;

  const isOriginCell = hasZeroZero
    ? (visual.x === 0 && visual.y === 0)
    : (visual.x === startX && visual.y === startY);

  // [M4①] 유효 다이 판정. 참조가 없으면 `isValidDieAt`이 원 판정을 그대로 돌려주므로
  // 선언 없는 맵의 동작은 `2a9f6c4`와 한 글자도 다르지 않다.
  const completelyInside = isValidDieAt(null, physical.x, physical.y,
    isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height));

  return {
    c, r, x: visual.x, y: visual.y, px: physical.x, py: physical.y,
    key: coordKey, inside: completelyInside, isOrigin: isOriginCell
  };
}

function getGridCellFromMouseEvent(e) {
  const canvasTarget = el.waferCanvas || el.gridCanvas;
  if (!canvasTarget) return null;
  const rect = canvasTarget.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  const xRel = e.clientX - rect.left;
  const yRel = e.clientY - rect.top;

  if (xRel < 0 || xRel > rect.width || yRel < 0 || yRel > rect.height) return null;

  const physConfig = getTransformedPhysicalConfig(null, currentRotation, currentSide);
  // [C1] 렌더와 **같은 함수**로 셀 크기를 얻는다. 마우스가 자기 산술을 가지면 화면과
  //      클릭이 갈리고, 그것은 "화면은 멀쩡한데 값이 틀린" 결함의 정확한 형태다.
  const { cellW, cellH, padX, padY } = cellMetrics(rect.width, rect.height, visualCols, visualRows, physConfig);
  const { shiftX, shiftY } = getScreenShift(physConfig, cellW, cellH);

  const c = Math.floor((xRel - shiftX - padX) / cellW);
  const r = Math.floor((yRel - shiftY - padY) / cellH);

  // 🔴 격자 밖은 **셀이 아니다.** 여백을 채우는 칸은 맵이 선언하지 않은 좌표이므로
  //    클릭·드래그·원점 지정 어느 것도 그 위에서 일어나지 않는다. `null`을 돌려주면
  //    호출부 셋(mousedown·mousemove·handleCellClick)이 전부 이미 있는 `if (!cell) return`
  //    으로 멈춘다 — 새 관문을 세 곳에 심지 않는다.
  //    `gridCells2D`가 격자 밖을 담지 않는 것(§renderGridCanvas 격자 밖)과 **둘 다** 필요하다:
  //    이쪽은 쓰기 동선을, 저쪽은 세기·저장 동선을 막는다.
  if (c < 0 || c >= visualCols || r < 0 || r >= visualRows) return null;

  if (gridCells2D[r]?.[c]) return gridCells2D[r][c];

  return getGridCellObject(c, r, visualCols, visualRows, physConfig, rect.width, rect.height);
}

// ── [1dⓗ] 「2. Legend & DOE」 폭 조절 + 폭 기억 ────────────────────────────────
//
// 🔴 새 스플리터를 쓰지 않는다. 이 프로젝트의 스플리터는 두 조각으로 이미 존재하고
//    (`.split-resizer` / `body.resizing-active` — style.css), 그리드 화면의
//    `#main-split-resizer`가 같은 두 조각을 쓴다. 여기서는 그 **표현 계층을 그대로**
//    쓰고, 드래그 산술만 이 화면의 것으로 붙인다.
//    main.js의 드래그 블록 자체를 호출하지 못하는 이유를 밝혀 둔다: 그것은
//    `initEventListeners` 안의 클로저이고 `#main-split-resizer`·`state.gridApi`(AG-Grid
//    컬럼 재맞춤)에 묶여 있으며 export되지 않는다. 그 파일은 client-pm 소관이라 이 라운드에
//    추출 리팩터를 넣지 않았다 — 공용 함수로 승격하는 것은 별건으로 제안한다.
//
// 🔴 폭의 저장 위치는 CSS 변수 하나(`--plan-sidebar-w`)다. 요소의 인라인 width로 쓰면
//    transfer_plan.css가 선언한 "폭의 유일한 출처"가 깨지고, 그 변수를 읽는 다른 규칙이
//    생기는 순간 화면과 계산이 갈린다.
// 🔴 하한·상한을 이 파일에 숫자로 적지 않는다. 380/760은 CSS의 min-width/max-width가
//    소유하고(그 근거 — DESC 85px 가독 하한 — 도 거기 적혀 있다), 여기서는 계산된 값을
//    읽어 쓴다. 같은 수를 두 곳에서 적으면 반드시 갈라진다.
const PLAN_SIDEBAR_W_KEY = 'mapPlanSidebarW';

function planSidebarBounds(aside) {
  const cs = getComputedStyle(aside);
  const lo = parseFloat(cs.minWidth);
  const hi = parseFloat(cs.maxWidth);
  return {
    lo: Number.isFinite(lo) ? lo : 0,
    hi: Number.isFinite(hi) ? hi : Infinity,
  };
}

function applyPlanSidebarWidth(aside, px) {
  const { lo, hi } = planSidebarBounds(aside);
  const w = Math.round(Math.min(hi, Math.max(lo, px)));
  document.documentElement.style.setProperty('--plan-sidebar-w', `${w}px`);
  return w;
}

function initPlanSidebarResizer() {
  const aside = document.getElementById('plan-sidebar');
  const grip = document.getElementById('plan-split-resizer');
  if (!aside || !grip) return;

  // 복원. 저장된 값도 **지금의** 경계로 다시 자른다 — 상한이 줄어든 뒤에도 옛 값이
  // 그대로 살아나 패널이 화면을 밀어내는 일이 없어야 한다.
  try {
    const saved = parseFloat(localStorage.getItem(PLAN_SIDEBAR_W_KEY) || '');
    if (Number.isFinite(saved) && saved > 0) applyPlanSidebarWidth(aside, saved);
  } catch (e) { /* 저장소를 못 읽으면 스타일시트 기본 폭으로 뜬다 */ }

  let dragging = false;
  // 기억할 숫자는 `applyPlanSidebarWidth`가 **이미 계산해서 화면에 쓴** 그 값이다.
  // 저장 시점에 computed width를 다시 읽으면 같은 수의 출처가 둘이 되고, 그 둘이 갈리는
  // 것이 이 도메인의 대표 결함이다(저장 ceil / 표시 round로 DB 34 · 화면 33).
  let appliedW = null;

  const onMove = (e) => {
    if (!dragging) return;
    // 손잡이가 패널의 **왼쪽** 모서리에 있으므로 폭은 (패널 우측 끝 − 커서)다.
    // 오른쪽 끝을 기준으로 잡으면 창 폭이나 가로 스크롤 위치에 흔들리지 않는다.
    appliedW = applyPlanSidebarWidth(aside, aside.getBoundingClientRect().right - e.clientX);
  };

  const stop = () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove('resizing-active');
    grip.classList.remove('dragging');
    // 드래그가 **끝날 때** 한 번만 기억한다. 매 mousemove마다 쓰면 localStorage 동기
    // 쓰기가 드래그를 얼어붙게 한다(이 파일이 페인팅에서 같은 함정을 이미 적어 뒀다).
    if (appliedW === null) return;         // 눌렀다 뗐을 뿐 — 폭이 바뀌지 않았다
    try { localStorage.setItem(PLAN_SIDEBAR_W_KEY, String(appliedW)); }
    catch (e) { /* 기억하지 못할 뿐, 이번 세션의 폭은 그대로다 */ }
  };

  grip.addEventListener('mousedown', (e) => {
    dragging = true;
    appliedW = null;
    document.body.classList.add('resizing-active');
    grip.classList.add('dragging');
    e.preventDefault();          // 드래그 중 텍스트 선택 방지
  });
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', stop);

  // 기억된 폭을 되돌리는 유일한 길. 새 컨트롤이 아니라 같은 손잡이의 더블클릭이고,
  // 손잡이의 title이 그렇게 말한다. 없으면 사용자가 기억을 지울 방법이 없다.
  grip.addEventListener('dblclick', () => {
    document.documentElement.style.removeProperty('--plan-sidebar-w');
    try { localStorage.removeItem(PLAN_SIDEBAR_W_KEY); } catch (e) { /* 무해 */ }
  });
}

let currentHoverCell = null;

function initMouseDragEvents() {
  window.addEventListener('mousedown', (e) => {
    isMouseDown = true;
    isRightDrag = (e.button === 2);
  });

  const canvasTarget = el.waferCanvas || el.gridCanvas;
  if (canvasTarget) {
    canvasTarget.addEventListener('mousedown', (e) => {
      e.preventDefault();
      const cell = getGridCellFromMouseEvent(e);
      if (!cell) return;

      if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';

      if (isOriginMode) {
        handleCellClick(cell, e);
        return;
      }

      const isRight = (e.button === 2 || e.buttons === 2);
      isBoxDragging = true;
      boxStartCell = cell;
      dragType = isRight ? 'erase' : 'paint';
      lastSelectionBox = { minC: cell.c, maxC: cell.c, minR: cell.r, maxR: cell.r };

      scheduleRenderGridCanvas();
    });

    canvasTarget.addEventListener('mouseleave', () => {
      if (currentHoverCell !== null) {
        currentHoverCell = null;
        scheduleRenderGridCanvas();
      }
    });

    canvasTarget.addEventListener('mousemove', (e) => {
      const cell = getGridCellFromMouseEvent(e);
      if (cell === currentHoverCell && !isBoxDragging) return;
      currentHoverCell = cell;

      if (cell) {
        const val = gridData[cell.key] || '';
        el.gridStatusCoords.textContent = `Cursor: (${cell.x}, ${cell.y}) = ${val !== '' ? val : 'Empty'}`;
      } else {
        // 격자 밖(여백을 채우는 칸) 위에는 좌표가 없다. 종전 값을 남겨 두면 커서가 맵을
        // 벗어난 뒤에도 마지막 셀을 가리키는 것처럼 읽힌다. HTML의 초기 문구로 되돌린다.
        el.gridStatusCoords.textContent = 'Cursor: -';
      }

      if (isBoxDragging && boxStartCell && cell) {
        const c1 = boxStartCell.c;
        const r1 = boxStartCell.r;
        const c2 = cell.c;
        const r2 = cell.r;

        const minC = Math.min(c1, c2);
        const maxC = Math.max(c1, c2);
        const minR = Math.min(r1, r2);
        const maxR = Math.max(r1, r2);

        if (lastSelectionBox &&
          lastSelectionBox.minC === minC && lastSelectionBox.maxC === maxC &&
          lastSelectionBox.minR === minR && lastSelectionBox.maxR === maxR) {
          return;
        }

        lastSelectionBox = { minC, maxC, minR, maxR };
        scheduleRenderGridCanvas();
      } else if (!isBoxDragging) {
        scheduleRenderGridCanvas();
      }
    });
  }

  window.addEventListener('mouseup', () => {
    isMouseDown = false;
    isRightDrag = false;

    if (isBoxDragging) {
      if (boxStartCell && lastSelectionBox) {
        const { minC, maxC, minR, maxR } = lastSelectionBox;

        for (let r = minR; r <= maxR; r++) {
          for (let c = minC; c <= maxC; c++) {
            const cell = gridCells2D[r]?.[c];
            if (!cell) continue;

            const key = cell.key;
            if (isProtectedFCell(key)) continue;

            if (dragType === 'erase') {
              gridData[key] = '';
            } else if (dragType === 'paint') {
              if (!cell.inside) continue;

              const existingVal = gridData[key] || '';
              const isSingleClick = (minC === maxC && minR === maxR);
              if (!isSingleClick && existingVal !== '') {
                continue;
              }

              if (activeBrush !== undefined && activeBrush !== null) {
                gridData[key] = activeBrush;
              }
            }
          }
        }
      }

      if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';

      isBoxDragging = false;
      boxStartCell = null;
      lastSelectionBox = null;
      dragType = null;

      updateLegendCounts();
      scheduleRenderGridCanvas();
      scheduleCellDraft();
    }
  });
}

// Fetch tables list
async function loadTablesList() {
  try {
    const res = await fetch(`${API_BASE}/tables`);
    const data = await res.json();
    el.tableSelect.innerHTML = '';

    if (data.tables && data.tables.length > 0) {
      // Fetch schema for all tables and filter ONLY map tables that have map_key_columns configured
      const mapTables = [];
      for (const tableName of data.tables) {
        try {
          const sRes = await fetch(`${API_BASE}/tables/${tableName}/schema`);
          if (sRes.ok) {
            const schema = await sRes.json();
            const keys = schema.map_key_columns || [];
            if (Array.isArray(keys) && keys.length > 0) {
              mapTables.push(tableName);
            }
          }
        } catch (e) {
          console.warn(`Failed to fetch schema for ${tableName}:`, e);
        }
      }

      if (mapTables.length > 0) {
        mapTables.forEach(table => {
          const option = document.createElement('option');
          option.value = table;
          option.textContent = table;
          el.tableSelect.appendChild(option);
        });
        // 오버레이 소스 선택기는 **별도 DOM**에 같은 목록을 채운다.
        // 같은 셀렉터를 재사용하면 소스를 고르는 행위가 switchTable을 타서
        // 편집 중인 맵이 초기화된다(실제 사용자 보고 결함) — 그래서 분리한다.
        if (el.overlaySrcTable) {
          el.overlaySrcTable.innerHTML = '';
          mapTables.forEach(table => {
            const o = document.createElement('option');
            o.value = table;
            o.textContent = table;
            el.overlaySrcTable.appendChild(o);
          });
        }
        // [1-a] The valid-die designation used to get the SAME table list here. It does not
        // any more: its storage table is fixed to `VALID_DIE_TABLE`, so there is nothing to
        // choose. The map-key datalist is what narrows the choice now, and it asks
        // `wafer_map_metadata` for that one table (`populateValidDieRefList`).
        // [U6] Auto select the first map table that is a declared stage TARGET
        // (GET /api/transfer-plan/stages — the same declaration the plan panel derives
        // its stages from), otherwise the first map table. No builtin table-name list:
        // an unreachable stages endpoint just means no plan-table preference.
        const stageTables = await stageTargetTables();
        const startTable = mapTables.find(t => stageTables.includes(t)) || mapTables[0];
        el.tableSelect.value = startTable;
        await switchTable(startTable);
      } else {
        el.tableSelect.innerHTML = '<option value="">No map tables available (map_key_columns missing)</option>';
      }
    } else {
      el.tableSelect.innerHTML = '<option value="">No tables available</option>';
    }
  } catch (err) {
    console.error('Failed to load tables', err);
    el.tableSelect.innerHTML = '<option value="">Connection Error</option>';
  }
}

// Switch current working table & load schema
async function switchTable(tableName) {
  selectedTable = tableName;
  const paintRulesReady = fetchPaintRules(tableName); // 잠금 선언은 맵 테이블별 — 전환 시 재조회
  try {
    const res = await fetch(`${API_BASE}/tables/${tableName}/schema`);
    tableSchema = await res.json();

    // [U6] Value-column auto-detect and the empty-map seed both consume the served
    // defaults that ride on the paint-rules response, so wait for that round-trip
    // (runs in parallel with the schema fetch above; fetchPaintRules never throws —
    // on failure the cached contract simply stays as it was).
    await paintRulesReady;

    // Fill advanced column selectors
    fillColumnDropdowns();

    // Render Dynamic Metadata Inputs
    renderMetadataInputs();

    // [확인창 제거] 테이블 전환은 **언제나 clean switch**다 — 묻지 않는다.
    //   ⓐ 재설계 모델에서 테이블 전환 = 다른 계획으로 이동이므로, 이전 맵의 셀을 들고 가는 것이
    //      의미상 틀리다.
    //   ⓑ 셀을 유지한 채 Push하면 **다른 테이블에 남의 맵 데이터가 적재**된다(C5 계열 사고 경로).
    // 편집 내용이 사라지는 사실은 모달이 아니라 토스트 한 줄로만 알린다.
    const hadWorkingMap = gridData && Object.keys(gridData).length > 0;

    // 대상 테이블의 legend 초기화 후 격자 초기화.
    // 이 시점에는 **맵이 없다** — 메타 입력 전이라 map_key가 존재하지 않는다. 규칙상 그때의
    // 답은 하나뿐이다: **빈 DOE 한 줄.** 종전에는 테이블 전체 어휘를 읽어 브러시로 깔았고,
    // 그것이 "내가 넣은 적 없는 값이 화면에 있다"의 원천이었다.
    // 맵 단위 legend는 맵을 실제로 여는 loadExistingMap에서 재적용된다.
    seedEmptyDoe();
    renderLegendTable();
    gridData = {};
    loadedFCells.clear();
    // Overlays belong to the previous table's frame, so ⓑ above applies to them
    // verbatim: an overlay left behind stays importable, and importing it writes
    // the old table's values into this one. Clearing gridData alone did not close
    // that path. Matches what a map load already does.
    if (overlayLayers.length > 0) {
      // [1e] The overlay list sits in the left block with its own count, so the release is
      // already on screen and the toast just repeats it. Unlike the grid reset toasted below,
      // this one is REVERSIBLE — the user can simply overlay again.
      console.debug(`[map] table switch released ${overlayLayers.length} overlay layer(s)`);
      clearOverlayLayers();
    }

    // 테이블이 바뀌면 이전 맵의 정체성 핀은 무효다 (Push 대상이 달라진다)
    setLoadedIdentity(null, null);
    // ⚠️ THE VALID-DIE DESIGNATION IS **NOT** RESET HERE — CLEAR SITE 1 OF 3, DELETED.
    //    User ruling (2026-08-04): 「고유 메타를 가진 맵을 불러오기 전까지 유효 다이영역
    //    초기화 금지」. The designation survives until a map that carries its OWN valid-die
    //    declaration is loaded; that map's declaration replaces it, and nothing else clears it.
    //    The workflow is SET-THEN-LOAD: the user picks the designation and then opens the map
    //    it applies to. The three statements that stood here ([M4①]/[M4②]) assumed the
    //    opposite order, so merely changing the TABLE — with no load at all — threw the
    //    designation away. That is how the user finally pinned this down.
    // 🔴 The deleted comment argued from ⓑ (an overlay left behind writes the OLD table's
    //    values into this one). That argument does not transfer: an overlay is a set of VALUES
    //    that a later import can push into the new table, whereas a designation is a MASK that
    //    only decides which dice are valid. It changes where cells sit (§getWaferBoundingBox
    //    keys the origin box off `basis === 'ref'`), which is exactly what the user is asking
    //    for when they carry it into the map they chose it for.
    // 🔴 The remaining hazard — switch table, do NOT load, Push to a different map — was
    //    weighed and closed by the user: nobody performs it, and a loaded map with its own
    //    declaration replaces the carried one anyway. No Push confirmation is added, and no
    //    "deliberate vs leftover" discriminator exists; there is no state that could tell
    //    them apart and inventing one is the complexity the UI rule forbids.
    // 새 테이블의 자동완성 캐시를 버려 다음 포커스에서 다시 읽게 한다 — 전환 중에 그 테이블에
    // 맵이 추가됐을 수 있고, 자동완성이 없는 것보다 **없는 맵을 제안하는 것**이 나쁘다.
    mapKeyListCache.delete(tableName);
    // 메타 입력칸의 컬럼 값 캐시도 같은 이유로 버린다. 입력칸과 datalist 자체는
    // renderMetadataInputs의 innerHTML=''로 이미 사라지므로, 남는 것은 이 캐시뿐이다.
    dropColumnValueCache(tableName);
    renderGridCanvas();
    notifyMapContext();
    if (hadWorkingMap) {
      showToast(`'${tableName}'(으)로 전환 — 편집 중이던 격자는 초기화되었습니다.`, 'info');
    }
  } catch (err) {
    console.error('Schema fetch failed', err);
  }
}

function renderMetadataInputs() {
  const container = el.metadataContainer;
  if (!container || !tableSchema) return;
  // [B1] 재생성으로 날아갈 현재 입력값을 먼저 붙든다 (아래에서 같은 컬럼에 되돌려 준다)
  const prevMetaValues = {};
  document.querySelectorAll('[id^="meta-input-"]').forEach(i => {
    prevMetaValues[i.id.replace('meta-input-', '')] = i.value;
  });
  container.innerHTML = '';

  const cols = tableSchema.columns || [];
  const xCol = el.colMapX ? el.colMapX.value : 'x';
  const yCol = el.colMapY ? el.colMapY.value : 'y';
  const valCol = el.colMapVal ? el.colMapVal.value : 'val';

  // Determine map_id search columns
  let searchCols = tableSchema.map_key_columns;
  if (!searchCols || !Array.isArray(searchCols) || searchCols.length === 0) {
    if (tableSchema.composite_key_source && Array.isArray(tableSchema.composite_key_source)) {
      searchCols = tableSchema.composite_key_source.filter(col =>
        !['x', 'y', 'val', 'die_id', 'code', 'grid_metadata'].includes(col.toLowerCase()) &&
        col !== xCol && col !== yCol && col !== valCol
      );
    }
  }
  if (!searchCols || searchCols.length === 0) {
    if (tableSchema.business_key && !['x', 'y', 'val', 'die_id', 'code'].includes(tableSchema.business_key.toLowerCase())) {
      searchCols = [tableSchema.business_key];
    }
  }

  // Fallback: system cols filter (same classification the push gate uses -
  // one list, one answer; see PUSH_SYSTEM_COLUMNS)
  if (!searchCols || searchCols.length === 0) {
    searchCols = cols.filter(col => !PUSH_SYSTEM_COLUMNS.includes(col) && col !== xCol && col !== yCol && col !== valCol);
  }

  searchCols.forEach(col => {
    if (!cols.includes(col)) return;
    const colType = tableSchema.column_types[col] || 'string';
    const formGroup = document.createElement('div');
    formGroup.className = 'control-group-vertical';

    const label = document.createElement('label');
    label.htmlFor = `meta-input-${col}`;
    label.textContent = `${col} (${colType})`;

    const input = document.createElement('input');
    input.type = 'text';
    input.id = `meta-input-${col}`;
    input.className = 'glass-input w-full';
    input.placeholder = `${col} 검색어 입력`;
    // [키 자동완성] 이 칸이 이미 가진 값을 제안한다. datalist는 **제약하지 않는다** —
    // 목록에 없는 값을 타이핑해 Load하는 경로는 종전과 완전히 같다.
    input.setAttribute('list', `meta-list-${col}`);
    // 목록을 **입력칸과 같은 그룹 안에** 만든다. 이 컨테이너는 위에서 innerHTML=''로 통째
    // 지워지므로 목록도 함께 사라진다 = 이전 테이블의 값이 살아남을 자리가 없다. 바깥(body
    // 등)에 두면 id는 살아 있고 내용만 낡는데, **낡은 목록은 낡아 보이지 않아** 없는 것보다
    // 나쁘다. 배선도 컨테이너 위임이라 재생성에도 리스너가 쌓이지 않는다(initDOMElements).
    const dataList = document.createElement('datalist');
    dataList.id = `meta-list-${col}`;

    formGroup.appendChild(label);
    formGroup.appendChild(input);
    formGroup.appendChild(dataList);
    container.appendChild(formGroup);
  });

  // [B1] 이 함수는 container.innerHTML=''로 메타 입력을 **재생성**한다.
  // X/Y/Val 컬럼 드롭다운을 바꾸면 여기로 들어와 **사용자가 입력해 둔 맵 키가 통째로 날아간다.**
  // 잠금(readOnly)은 조회 마찰이라 폐지했지만, **값 소실은 별개 결함**이므로 계속 고친다.
  Object.entries(prevMetaValues).forEach(([col, val]) => {
    const input = document.getElementById(`meta-input-${col}`);
    if (input && val !== '') input.value = val;
  });
}

function getBaseColumnName() {
  if (!tableSchema) return 'base';
  const compositeSources = tableSchema.composite_key_source || [];
  // Base is usually the first non-coordinate key source
  const baseCol = compositeSources.find(c => c !== 'x' && c !== 'y');
  return baseCol || 'base';
}

function fillColumnDropdowns() {
  if (!tableSchema) return;
  const cols = tableSchema.columns || [];

  const populate = (dropdown) => {
    dropdown.innerHTML = '';
    cols.forEach(col => {
      if (col === 'created_at' || col === 'updated_at') return;
      const option = document.createElement('option');
      option.value = col;
      option.textContent = col;
      dropdown.appendChild(option);
    });
  };

  populate(el.colMapX);
  populate(el.colMapY);
  populate(el.colMapVal);

  // [F1/F3] Preselect all three from the SERVED binding (paint-rules `binding`,
  // cached by fetchPaintRules — switchTable awaits that round-trip before calling here).
  // Column matching happens server-side ONCE (declared table_bindings win, else
  // table_config derivation); the former client matchers — a case-insensitive x/y name
  // matcher plus a candidate-list val matcher — are gone. They were second and third
  // matchers over the same question and could disagree with the server (F3). Declared
  // bindings (tx/ty, UPPERCASE columns) now preselect too, which no client convention
  // matcher could do. No served binding -> no auto-select, first column stays: the
  // dropdowns themselves remain the manual escape hatch.
  const served = servedBindingCache.get(selectedTable) || null;
  const pick = (dropdown, col) => { if (col && cols.includes(col)) dropdown.value = col; };
  if (served) {
    pick(el.colMapX, served.x);
    pick(el.colMapY, served.y);
    pick(el.colMapVal, served.val);
  }
  // [F2] "fallback_guess" = the server could not match any value-column candidate and
  // guessed the first data column. The data paths refuse to use a guess, so the user
  // must not trust it silently either — warning-tone hint on the existing control
  // (dropdown title). No new control, and no toast: the title sits ON the guess.
  if (served && served.source === 'fallback_guess') {
    el.colMapVal.title = `추측된 값 컬럼 — map_overlay_config.table_bindings에 선언하십시오.`;
    console.log(`[Map Editor] ${selectedTable}: value column '${served.val}' is a fallback_guess`);
  } else {
    el.colMapVal.title = '';
  }
}

// ----------------------------------------------------
// Coordinates Mapping Calculation
// ----------------------------------------------------

// ── [변환 일원화] 프레임 창(frame window) ─────────────────────────────
// 좌표 변환 함수들은 규격(치수·물리 파라미터)을 **화면 컨트롤(DOM)** 에서 읽는다.
// 오버레이는 소스 맵을 **소스 자신의 메타 프레임**으로 해석해야 하므로, 그 계산 동안만
// 읽기 지점을 갈아끼운다. 이것이 오버레이 전용 변환식을 새로 쓰지 않기 위한 유일한 장치다 —
// 변환식은 이 파일에 **하나뿐**이고, 메인 로드는 "프레임 == 현재 화면 컨트롤"인 특수 케이스다.
//
// ⚠️ 종전의 「동기 실행 전용」 경고는 사라졌다 — 프레임이 모듈 상태였을 때는 `await` 한 번이
//    다른 코드에 뒤집힌 프레임을 보여 줄 수 있었기 때문인데, 인자는 그럴 수가 없다.

// 기존 규약 `parseFloat(input.value) || 기본값`을 그대로 유지한다(0 → 기본값).
//
// ═══ [S2.1] THE FRAME IS AN ARGUMENT, NOT MODULE STATE ═══════════════════════════════════
//
// These two used to read `physFrameOverride` off the module. A function that reads module
// state cannot be called twice with different state, which is why every harness that scores
// them has to cut them out of this file as TEXT and rebuild the module's globals around them.
// The frame now arrives as the first argument and nothing about the ANSWER changed: the
// caller passes exactly the value the function used to read, at the same synchronous instant.
//
// 🔴 `null` AND `undefined` ARE DIFFERENT ANSWERS, and collapsing them would undo the point.
//    `null` = "no frame, read the screen" — a deliberate answer, and the main-load case.
//    `undefined` = the caller forgot. The module binding used to apply the window
//    AUTOMATICALLY, so forgetting was impossible; an argument makes it possible for the first
//    time. If a missed call site silently fell back to the screen, the canvas would draw
//    perfectly and the stored coordinate would be wrong — this file's signature defect, and
//    the exact reason the frame window exists at all. So it is loud.
// ⚠️ The throw is a backstop, not the protection. The protection is that every call site was
//    enumerated and given an explicit argument; the throw only catches a future one.
function physNum(frame, key, domEl, dflt) {
  if (frame === undefined) {
    throw new Error(`physNum('${String(key)}'): frame argument missing. Pass the frame that is `
      + `in scope, or \`null\` to read the screen controls on purpose.`);
  }
  if (frame && frame[key] !== undefined && frame[key] !== null) {
    const ov = parseFloat(frame[key]);
    if (Number.isFinite(ov)) return ov || dflt;
  }
  const v = domEl ? parseFloat(domEl.value) : NaN;
  return v || dflt;
}

// `physNum`의 격자 쌍둥이 — 같은 규약, 같은 인자 순서다(§physNum의 `undefined` 대 `null`).
function gridDimNum(frame, key, domEl, dflt) {
  if (frame === undefined) {
    throw new Error(`gridDimNum('${String(key)}'): frame argument missing. Pass the frame that `
      + `is in scope, or \`null\` to read the screen controls on purpose.`);
  }
  if (frame && frame[key] !== undefined && frame[key] !== null) {
    const ov = parseInt(frame[key], 10);
    if (Number.isFinite(ov)) return ov || dflt;
  }
  const v = parseInt(domEl ? domEl.value : '', 10);
  return v || dflt;
}

// `physNum`의 쌍둥이 — **같은 조회 순서를 돌지만 찾은 것을 그대로 보고한다.**
//
// 🔴 **기본값 뒤에 선 관문은 원리적으로 작동하지 않는다.** `physNum`은 `return v || dflt`로
//    끝나므로 그 출력만 보는 검사는 「선언 없음」·「파싱 불가」·「0으로 선언」·「진짜 그 값」을
//    구별할 수 없다 — 넷이 전부 같은 수로 도착한다. 실측(QA): 소스 메타에 `phys_chip_x`가
//    없거나 `""`/`"abc"`면 **타깃의 화면 피치**로 접혀서 600칸 중 570칸이 틀린 칸에 앉는데
//    `chipX > 0` 검사는 그대로 통과했다. 음수만 걸렸다.
// 🔴 그래서 이 함수는 **수를 돌려주지 않고 사실을 돌려준다.** 관문은 값이 아니라 `source`를
//    읽는다. `physNum` 자체는 손대지 않는다 — 그 폴백 규약에 모듈 전체가 얹혀 있다.
//
// 반환 `{ value, source }`:
//   'frame'      — 프레임 창(소스 메타)이 쓸 수 있는 수를 선언했다
//   'screen'     — 프레임은 말이 없고 화면 컨트롤이 값을 냈다  ← 규칙 6에서 이것이 위험이다
//   'unparsable' — 값은 있는데 수가 아니다 (value = null)
//   'absent'     — 어느 쪽도 값을 내놓지 않는다 (value = null)
//   'auto_registered' — 값은 **있지만 선언이 아니다**: 아무도 재지 않은 합성 규격이다
//                       (value = null — 아래 §자동 등록 규격)
//
// ═══ [D1] 자동 등록된 규격은 선언이 아니다 (사용자 판정 2026-08-04) ═══════════════════
//
// 맵에 규격 행이 없으면 두 곳이 **마스크 중립 합성 규격**을 만들어 넣는다. 둘 다 물리량을
// 「없음」으로 표현할 어휘가 없어서 chip 1x1 / offset 0 / 격자 반대각선을 외접하는 지름을
// 쓴다 — 원 마스크가 아무 셀도 자르지 않게 하려는 것이지, 1mm 다이를 주장하는 게 아니다:
//   · `server/map_meta_registrar.synthesize_grid_meta()` — 인제션 자동 등록
//   · 이 파일의 `[fix C]` 분기                            — 규격 없는 맵의 「표준」 선택
//
// 🔴 **읽는 쪽이 그 사실을 몰랐다.** `physDeclaration`은 합성 규격과 사람이 잰 1mm 선언을
//    **바이트 단위로 같게** 답했고, 그래서 「피치 미선언」을 잡으려고 만든 관문이 통과했다.
//    실측 2026-08-04: 등록된 668행 중 320행(47.9%)이 합성 규격이다.
//
// 🔴 **판정은 값이 아니라 `auto_registered` 표지다** — chip이 1인지 보지 않는다. 1은 합법적인
//    값이라(5x5 다이가 실재한다) 그것을 표지로 쓰면 언젠가 진짜 1mm 다이를 조용히 삼킨다.
//    표지는 자기가 표지라고 말하고, 측정값과 혼동될 수 없다.
// 🔴 **레거시 폴백(chip 1x1을 표지로 읽기)은 두지 않는다 — 필요 없다는 것을 셌다.** 실측:
//    chip 1x1인 320행이 **전부** `auto_registered: true`를 달고 있고, 표지 없이 1x1인 행은
//    **0건**이다. 안 쓰이는 폴백은 채점되지 않는 두 번째 판정 경로일 뿐이다.
// 🔴 **두 축을 함께 본다**(표지는 규격 전체에 붙는다). 1 x 8 같은 진짜 이방성 선언은
//    표지가 없으므로 여기 걸리지 않는다.
//
// ⚠️ **표지가 사는 곳은 값이 사는 곳과 같아야 한다.** 프레임 창에서는 프레임 객체가,
//    화면에서는 그 값을 담은 입력칸 자신(`dataset`)이 들고 있다 — 모듈 상태를 만들지
//    않으려는 것이기도 하지만(천장 여유 0), 무엇보다 값과 표지가 갈라지면 표지가 낡는다.
//    조작자가 칩 칸을 고치는 순간 표지는 사라진다(§`markGeometryAutoRegistered`).
// 🔴 **프레임 창 안에서는 프레임만 답한다.** 화면 표지를 함께 보면 자동 등록 맵을 열어 둔 채
//    남의 맵을 오버레이할 때 그 **소스**의 진짜 규격이 「선언 없음」으로 뒤집힌다 — 표지는
//    맵마다의 사실이지 세션의 사실이 아니다.
// 🔴 **두 축 모두에 표지가 있어야 한다.** 한 축만 보면 나머지 한 축에 쓰는 코드가 아무것도
//    하지 않게 되고, 안 읽히는 쓰기는 조용히 낡는다(둘이 갈라져도 아무도 모른다).
function geometryIsAutoRegistered(frame) {
  if (frame === undefined) {
    throw new Error('geometryIsAutoRegistered: frame argument missing. Pass the frame that is '
      + 'in scope, or `null` to read the screen mark on purpose.');
  }
  if (frame) return frame.autoRegistered === true;
  if (!el) return false;
  const dx = el.physChipX ? el.physChipX.dataset : null;
  const dy = el.physChipY ? el.physChipY.dataset : null;
  return !!(dx && dy && dx.autoRegistered === '1' && dy.autoRegistered === '1');
}

// 「이 컨트롤이 **아무 말도 하지 않았는가**」 — 이 질문의 유일한 철자.
//
// 🔴 빈 문자열은 침묵이지 값이 아니다. 서버 `map_overlay.geometry_declaration:387`과
//    `map2/declaration.js isSilent`가 이미 같은 답을 내고, 여기가 그 클라 절반이다. 종전에는
//    `physDeclaration` 안의 클로저 하나에만 있었고, 이번 라운드에 **격자 컨트롤 쪽에서 같은
//    질문이 다시 필요해졌다** — 거기서 두 번째로 적었으면 이 저장소의 재발 결함 계급을 이
//    라운드가 스스로 한 건 더 만드는 셈이었다.
function controlIsSilent(raw) {
  return raw === undefined || raw === null || String(raw).trim() === '';
}

function physDeclaration(frame, key, domEl) {
  if (frame === undefined) {
    throw new Error('physDeclaration: frame argument missing. Pass the frame that is in scope, '
      + 'or `null` to read the screen controls on purpose.');
  }
  const read = (raw, source) => {
    if (controlIsSilent(raw)) return null;
    const n = parseFloat(raw);
    return Number.isFinite(n) ? { value: n, source } : { value: null, source: 'unparsable' };
  };
  // 🔴 **여기가 유일한 철자다.** 호출자가 이 질문을 다시 구현하면 「선언인가」의 답이 둘이 되고,
  //    그 둘이 갈리는 날은 화면이 멀쩡한 채로 값만 틀리는 날이다.
  if ((key === 'chipX' || key === 'chipY') && geometryIsAutoRegistered(frame)) {
    return { value: null, source: 'auto_registered' };
  }
  if (frame && Object.prototype.hasOwnProperty.call(frame, key)) {
    const fromFrame = read(frame[key], 'frame');
    if (fromFrame) return fromFrame;
  }
  return read(domEl ? domEl.value : null, 'screen') || { value: null, source: 'absent' };
}

// 화면 쪽 표지의 **유일한 쓰기 지점**. 칩 입력칸에 붙인다 — 규칙이 읽는 값이 거기 있다.
// 켜는 곳: 합성 규격을 화면에 앉히는 두 자리(메타 로드 · `[fix C]`).
// 끄는 곳: 사람이 규격을 선언하는 모든 자리(프리셋 적용 · 칩 칸 직접 편집 · 표지 없는 메타).
function markGeometryAutoRegistered(on) {
  [el.physChipX, el.physChipY].forEach(input => {
    if (!input || !input.dataset) return;
    if (on) input.dataset.autoRegistered = '1';
    else delete input.dataset.autoRegistered;
  });
}

// ═══ [D4] 프레임 절반에도 출처가 있어야 한다 (2026-08-05) ══════════════════════════════
//
// `auto_registered`가 닫은 구멍의 **격자 쪽 쌍둥이**다. 규격 행이 없거나 START를 못 읽는 맵은
// 좌표계 선택 모달로 가고(`98b48e9`), 거기서 고른 프레임을 `buildPushGridMetadata`가
// `wafer_map_metadata`에 **표지 없는 평범한 선언으로** 써 넣었다. 실측 페이로드:
//   · 선언 없음 + 📐 표준     → `auto_registered: true` (phys 표지만, 격자 축은 그 표지가 덮는다)
//   · 선언 없음 + ⚙️ 현재 패널 → **표지가 하나도 없다**
//   · 진짜 선언된 메타         → 위 행과 **바이트 단위로 같다**
// 그래서 아무도 선언한 적 없는 프레임이 선언과 구별 불가능해지고, 그 상태가 영구히 누적됐다.
//
// 🔴 **토큰을 새로 만들지 않았다.** 여섯 토큰(`declared`/`auto_registered`/`absent`/
//    `unparsable`/`indeterminate`/`assumed`)은 전부 「이 **축의 값**이 어떤 종류의 증거인가」에
//    답한다. 여기서 없던 것은 축에 대한 답이 아니라 **행에 대한 사실**이다 — 「선택이
//    일어났는가」. 사람이 고른 프레임은 좁은 뜻에서 정말 `declared`이므로 토큰을 바꾸면 거짓이
//    되고, `indeterminate`로 접으면 「골랐다는 증거가 없다」는 정반대의 거짓이 된다.
// 🔴 그래서 형식은 **`phys_assumed_from`과 같다**(`map_overlay.py:351`): 있을 때만 있는 키이고,
//    값이 **어디서 왔는지**를 말한다. `"data"` = 이 맵의 셀 bbox(📐 표준) · `"panel"` = 에디터
//    좌측 패널(⚙️ 현재 패널). 판정을 바꾸지 않으므로 `isFrameUsable`도 `geometryDeclaration`도
//    손대지 않는다 — 늘어난 것은 **관측 가능성**뿐이다.
//
// ⚠️ **낡지 않는 사실만 담는다.** 이 표지는 「지금 칸에 든 수를 누가 쳤는가」가 아니라
//    **「이 맵이 선언을 갖기 전에 프레임이 어디서 왔는가」**다. 조작자가 나중에 칸을 고쳐도
//    그 사실은 참으로 남으므로 편집 리스너가 필요 없고, 그래서 지우는 자리는 하나뿐이다 —
//    표지 없는 메타를 불러올 때(§`resolveGridFrame` `meta` 분기, `markGeometryAutoRegistered`와
//    **같은 양방향 규율**: 안 지우면 직전 맵의 표지가 남아 진짜 선언을 「고른 것」으로 읽는다).
// ⚠️ 표지가 사는 곳은 값이 사는 곳과 같다 — 프레임의 원점이 START 칸에 있으므로 표지도 거기
//    붙인다(모듈 상태를 만들지 않는다: `MODULE_STATE` 천장 여유 0). 두 축 모두에 쓰고 두 축
//    모두를 읽는다: 한 축만 읽으면 나머지 한 축의 쓰기가 조용히 낡는다.
function markFrameChosen(from) {
  [el.gridStartX, el.gridStartY].forEach(input => {
    if (!input || !input.dataset) return;
    if (from) input.dataset.frameChosen = String(from);
    else delete input.dataset.frameChosen;
  });
}

// 프레임 표지의 **유일한 독법.** 🔴 프레임 창 안에서는 프레임만 답한다 — 화면 표지를 함께 보면
// 고른 프레임의 맵을 열어 둔 채 남의 맵을 오버레이할 때 그 **소스**의 출처가 뒤집힌다
// (§`geometryIsAutoRegistered`와 같은 이유이고, 같은 순서로 묻는다).
function frameChosenFrom(frame) {
  if (frame === undefined) {
    throw new Error('frameChosenFrom: frame argument missing. Pass the frame that is in scope, '
      + 'or `null` to read the screen marks on purpose.');
  }
  if (frame) return frame.frame_chosen_from || null;
  if (!el) return null;
  const dx = el.gridStartX ? el.gridStartX.dataset : null;
  const dy = el.gridStartY ? el.gridStartY.dataset : null;
  if (!dx || !dy || !dx.frameChosen) return null;
  return dx.frameChosen === dy.frameChosen ? dx.frameChosen : null;
}

// ═══════════════════════════════════════════════════════════════════════════════
// 물리 키의 **원점**. 웨이퍼 중심이다 — 격자 크기가 아니다.
//
// 🔴 종전에는 `xp = round(xRot + (cols-1)/2)`였다. 입력 `xRot`은 이미 웨이퍼 중심 기준인데
//    출력만 **이 맵 자신의 격자 중심**으로 되기준했으므로, 물리 키의 뜻이 "웨이퍼 중심에서
//    몇 칸"이 아니라 "이 격자의 몇 번째 칸"이 됐다. 그래서 23x23과 45x45는 같은 다이를
//    11만큼 다른 키로 불렀고(중심 11 대 22), 오버레이·유효 다이 마스크가 그만큼 밀렸다.
//
// 🔴 **그냥 지우면 안 된다 — 패리티가 남는다.** 격자 칸 수가 짝수면 웨이퍼 중심은 칸의
//    경계에 앉고 홀수면 칸의 한가운데에 앉는다. 그 반 칸은 좌표계의 선택이 아니라 다이
//    격자의 물리적 사실이다. 되기준 항을 통째로 없애면 짝수 격자에서 `Math.round`가 그 반
//    칸을 삼켜 `getCanvasCellFromDieIndex`와의 왕복이 한 칸 어긋난다(운영 데이터 실측:
//    214개 맵 중 163개가 짝수 치수를 갖는다). 그래서 남기는 것은 **크기가 아니라 패리티**다.
//
// ⚠️ 그 결과 새 키 == 옛 키 − `Math.floor((cols-1)/2)`로 **정확히 정수 평행이동**이다.
//    왕복 항등은 한 글자도 약해지지 않고, 사라지는 것은 격자 **크기** 의존뿐이다.
// ⚠️ 이 함수와 `getCanvasCellFromDieIndex`는 서로의 역함수다. 한쪽만 바꾸면 로드가 놓은
//    칸과 렌더가 읽는 칸이 갈린다 — 화면은 멀쩡한데 값이 틀리는 그 상태다.
// ⚠️ **헬퍼 함수로 빼지 않는다.** 이 두 함수를 슬라이스해 실행하는 하네스가 넷이고, 모듈
//    전역 의존이 하나 늘 때마다 넷이 전부 ReferenceError로 죽는다(§getWaferBoundingBox의
//    같은 경고 — 이 라운드에서 실제로 한 번 죽였다). 그래서 패리티 항은 인라인이다.
// ═══════════════════════════════════════════════════════════════════════════════
function getDieIndex(frame, colVisual, rowVisual, cols, rows, rotation, side) {
  if (frame === undefined) {
    throw new Error('getDieIndex: frame argument missing. Pass the frame that is in '
      + 'scope, or `null` to read the screen controls on purpose.');
  }
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // ⚠️ Do not read the physical spec (chip/offset) straight from the DOM here — that bypasses
  //    the frame window (physFrameOverride) and would silently contaminate source-frame math
  //    with on-screen values. Go through physNum() if you ever need them.
  //    (Four unused leftovers were removed: this is a per-cell, per-frame hot path, so their
  //     four parseFloat calls were pure waste.)

  // Get screen-space shift for the current rotation in cell units
  const physConfig = getTransformedPhysicalConfig(frame, rotation, side);
  const { shiftX, shiftY } = getScreenShift(physConfig, 1.0, 1.0);

  // Screen cell position relative to wafer center
  const xScreenWafer = colVisual - (visualCols - 1) / 2.0 + shiftX;
  const yScreenWafer = rowVisual - (visualRows - 1) / 2.0 + shiftY;

  // Rotate screen cell relative to wafer center by -rotation (to map screen coordinates to physical coordinates)
  let xRot = xScreenWafer;
  let yRot = yScreenWafer;

  if (rotation === 0) {
    xRot = xScreenWafer;
    yRot = yScreenWafer;
  } else if (rotation === 90) {
    // -90 deg CCW = 90 deg CW: X' = Y, Y' = -X
    xRot = yScreenWafer;
    yRot = -xScreenWafer;
  } else if (rotation === 180) {
    xRot = -xScreenWafer;
    yRot = -yScreenWafer;
  } else if (rotation === 270) {
    // -270 deg CCW = 90 deg CCW: X' = -Y, Y' = X
    xRot = -yScreenWafer;
    yRot = xScreenWafer;
  }

  if (side === 'back') {
    xRot = -xRot;
  }

  // Convert back to a physical coordinate (xp, yp) — WAFER-CENTRE relative (see the block
  // comment above). The term kept is the PARITY of the grid, never its size.
  const xp = Math.round(xRot + (Math.abs(Math.round(cols)) % 2 === 0 ? 0.5 : 0));
  const yp = Math.round(yRot + (Math.abs(Math.round(rows)) % 2 === 0 ? 0.5 : 0));

  // 🔴 [규칙 6] `xCells`/`yCells`는 **반올림 직전의 그 값**이다 — 웨이퍼 중심에서 몇 칸인지,
  //    소수점까지. 밀리미터가 아니다(§묘비 ⑫): 여기에 `chipX`/`chipY`를 곱한 것이 mm다.
  //    새 유도가 아니라 **이 함수가 이미 계산해 놓고 버리던 조각**이며, 이것을 돌려주는 것이
  //    오버레이 전용 변환식을 쓰지 않고 규칙 6을 얻는 유일한 방법이다:
  //    반올림된 `xp`만으로는 mm를 되만들 수 없다. 오프셋의 **칸 미만 잔여**(칩 피치로 나눈
  //    나머지)가 반올림에 삼켜져 있고, 그 잔여를 다시 세우려면 회전·면 부호표를 두 번째로
  //    쓰게 된다 — 이 도메인에서 그 표는 이미 여러 번 틀렸다.
  // ⚠️ 소비자는 `.x`/`.y`만 읽으면 종전과 완전히 같다(가산 필드).
  return { x: xp, y: yp, xCells: xRot, yCells: yRot };
}

function getCanvasCellFromDieIndex(frame, xp, yp, cols, rows, rotation, side) {
  if (frame === undefined) {
    throw new Error('getCanvasCellFromDieIndex: frame argument missing. Pass the frame that is in '
      + 'scope, or `null` to read the screen controls on purpose.');
  }
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // The exact inverse of getDieIndex — the same origin term, or the round trip splits.
  let xRot = xp - (Math.abs(Math.round(cols)) % 2 === 0 ? 0.5 : 0);
  let yRot = yp - (Math.abs(Math.round(rows)) % 2 === 0 ? 0.5 : 0);

  if (side === 'back') {
    xRot = -xRot;
  }

  // Rotate back to screen coordinates
  let xScreenWafer = xRot;
  let yScreenWafer = yRot;

  if (rotation === 0) {
    xScreenWafer = xRot;
    yScreenWafer = yRot;
  } else if (rotation === 90) {
    xScreenWafer = -yRot;
    yScreenWafer = xRot;
  } else if (rotation === 180) {
    xScreenWafer = -xRot;
    yScreenWafer = -yRot;
  } else if (rotation === 270) {
    xScreenWafer = yRot;
    yScreenWafer = -xRot;
  }

  // Get screen-space shift for the current rotation in cell units
  const physConfig = getTransformedPhysicalConfig(frame, rotation, side);
  const { shiftX, shiftY } = getScreenShift(physConfig, 1.0, 1.0);

  const colVisual = xScreenWafer + (visualCols - 1) / 2.0 - shiftX;
  const rowVisual = yScreenWafer + (visualRows - 1) / 2.0 - shiftY;

  return { c: Math.round(colVisual), r: Math.round(rowVisual) };
}

// ═══════════════════════════════════════════════════════════════════════════════
// [규칙 6] **웨이퍼 중심 기준 물리 밀리미터.** 다이 인덱스와 길이 사이의 유일한 다리다.
//
// 🔴 **이것은 §0 규약 ⑤가 금지한 그 곱셈이 아니다.** 금지된 것은 `dbX * 피치`다 —
//    저장 좌표는 `c − box.minC + startX`, 즉 **오리진(START) 기준 칸수**라 원점이 웨이퍼
//    중심이 아니고 bbox·START에 실려 있다. 거기에 피치를 곱하면 없는 결함이 만들어진다
//    (그렇게 추론한 라운드가 실제로 기각됐다).
//    다이 인덱스는 **다른 양**이다: `getDieIndex`가 만드는 수는 이미 「웨이퍼 중심에서 몇
//    칸」이고 그 칸의 크기가 곧 칩 피치다(`35e84c3`가 원점을 격자 중심에서 웨이퍼 중심으로
//    옮긴 이유가 이것이다). 렌더가 웨이퍼 원을 `effectiveRadius / chipX` 칸으로 그리는 그
//    환산과 **같은 환산**이고, 새 유도가 아니다.
//
// 🔴 **패리티는 `getDieIndex`의 그 항이다.** 격자 칸 수가 짝수면 웨이퍼 중심이 칸 경계에
//    앉으므로 인덱스 0의 다이는 중심에서 반 칸 떨어져 있다. 이 반 칸을 빼지 않으면 짝수
//    격자와 홀수 격자를 겹칠 때 **모든 셀이 반 칸씩** 밀린다(실측 축: 소스 rows=59(홀),
//    타깃 rows=30(짝)). 두 함수가 같은 식을 인라인으로 갖는 이유는 §getDieIndex와 같다 —
//    이 둘을 슬라이스해 실행하는 하네스가 모듈 전역 의존 하나에 죽는다.
//
// ⚠️ 곱하는 피치는 **선언된(회전 전) 물리 피치**다. `getTransformedPhysicalConfig`가
//    90/270에서 스왑한 화면 피치가 아니다 — `getDieIndex`가 이미 화면을 물리 축으로
//    되돌려 놓았고, 그 결과 x는 `chipX`의 격자에, y는 `chipY`의 격자에 산다.
//
// 🔴 **격자의 기준점은 `getDieIndex`에게 묻는다 — 다시 유도하지 않는다.** 아래 `L`은 캔버스
//    칸 (0,0) 하나를 그 함수에 넣어 얻은 답이고(`ix0`는 반올림된 인덱스, `ux0`는 반올림 전
//    연속값), 다이 격자는 간격 1의 정수 격자이므로 이 기준점 **하나가 격자 전체를 정한다**.
//    패리티·회전 부호표·오프셋 부호표가 여기에 한 줄도 없는 이유가 이것이다: 전부
//    `getDieIndex` 안에 있고, 이 모듈에는 그 함수가 하나뿐이다.
// ═══════════════════════════════════════════════════════════════════════════════
function frameDieLattice(frame) {
  const f = frame || currentFrame();
  {
    const p = getDieIndex(f, 0, 0, f.cols, f.rows, f.rotation, f.side);
    return {
      ix0: p.x, iy0: p.y, ux0: p.xCells, uy0: p.yCells,
      chipX: physNum(f, 'chipX', el.physChipX, 2.5),
      chipY: physNum(f, 'chipY', el.physChipY, 2.5),
    };
  }
}

// 다이 인덱스 → 그 다이 **중심**의 절대 웨이퍼 mm.
function dieIndexToWaferMm(ix, iy, L) {
  if (!L || !(L.chipX > 0) || !(L.chipY > 0)) return null;
  return { mmX: (L.ux0 + (ix - L.ix0)) * L.chipX, mmY: (L.uy0 + (iy - L.iy0)) * L.chipY };
}

// 위의 역함수 — 단 **나머지를 버리지 않는다.**
//   몫  = 그 점을 담는 다이 인덱스 (`getDieIndex`가 그 칸에 매기는 바로 그 번호)
//   나머지 = 그 다이 **안에서의** 위치, `[0, 피치)` 밀리미터.
//
// 🔴 나머지는 **절대 길이라서 피치에 의존한다.** 7mm 칩 안의 3mm와 15mm 칩 안의 3mm는 다른
//    자리다. 그래서 칩 내 좌표는 맵 사이에서 그대로 옮길 수 없고 **반드시 절대 mm를 거쳐
//    다시 나눠야** 한다. 지금 그리는 것은 없지만(결함 in-chip 표기가 앞으로 온다) 여기서
//    버리면 그 경로를 나중에 통째로 다시 열어야 한다.
function waferMmToDieCell(mmX, mmY, L) {
  if (!L || !(L.chipX > 0) || !(L.chipY > 0)) return null;
  const dx = mmX / L.chipX - L.ux0;
  const dy = mmY / L.chipY - L.uy0;
  const nx = Math.round(dx);
  const ny = Math.round(dy);
  return {
    ix: L.ix0 + nx, iy: L.iy0 + ny,
    rx: (dx - nx + 0.5) * L.chipX, ry: (dy - ny + 0.5) * L.chipY,
  };
}

function getCanvasCellFromDb(frame, dbX, dbY, cols, rows, rotation, side, invertY, startX, startY) {
  if (frame === undefined) {
    throw new Error('getCanvasCellFromDb: frame argument missing. Pass the frame that is in scope, or `null` '
      + 'to read the screen controls on purpose.');
  }
  const box = getWaferBoundingBox(frame, rotation, side);

  const c = dbX - startX + box.minC;

  let r = 0;
  if (!invertY) {
    r = dbY - startY + box.minR;
  } else {
    r = box.maxR - (dbY - startY);
  }

  return { c, r };
}

let boundingBoxCache = {};

// ═══════════════════════════════════════════════════════════════════════════════
// 좌표계의 **원점 상자**. `getDbCoords`가 `dbX = c − box.minC + startX`로 화면 표기이자
// DB에 저장되는 x/y를 만들고, `getCanvasCellFromDb`가 그 정확한 역함수로 로드 배치를 한다.
// 그래서 이 상자 하나가 "start_x/start_y가 어느 칸에 놓이는가"를 정한다.
//
// 🔴 **기준은 유효 다이 영역이다** (사용자 확정 2026-07-30, 판정 기준 ③④):
//    「start_x/start_y = 유효 다이 영역의 최소 열·행」 ·
//    「오리진 = start_x/y가 놓였을 때 (0,0)으로 읽히는 칸」.
//    종전에는 원 기하만 훑었다. 원 bbox는 회전·반전에 거의 불변인데 유효 다이 영역은 그렇지
//    않아서, 회전할 때마다 마스크의 최소 열이 startX가 놓인 칸에서 멀어졌다 — 「회전 할때마다
//    origin이 틀어지네」의 정체다(실측: DTWWER → BASE_4E에서 (4,3)).
//
// 🔴 **판정을 새로 쓰지 않는다.** 원 판정은 `isCellInsideWaferFast`, 마스크 판정은
//    `isValidDieAt` — 렌더 루프가 부르는 바로 그 두 함수를 같은 인자·같은 순서로 부른다.
//    순회도 하나뿐이다(원 상자와 마스크 상자를 같은 루프에서 함께 누적한다).
//
// 🔴 **프레임 창(`physFrameOverride`) 안에서는 원이다.** `isValidDieAt`이 이미 그렇게 답한다:
//    창 안의 계산은 **소스 맵의 좌표계**를 푸는 중이고, 거기에 타깃 맵의 마스크를 먹이면
//    조용히 다른 맵의 마스크로 소스를 재단하게 된다. 그래서 오버레이와 유효 다이 참조 해석
//    (`projectCellsToPhys`)은 이 변경 전과 한 글자도 다르지 않게 동작한다.
//
// 🔴 **저작 캔버스(`template`)도 원이다.** 저작 중의 마스크는 격자 전체이므로 상자가 격자
//    전체가 되고, 그러면 저작 모드에 들어가는 것만으로 화면의 모든 좌표가 다시 매겨진다.
//    저작은 "무엇을 칠하느냐"이지 좌표계의 선언이 아니다. `refused`도 같다 — 해석하지 못한
//    선언으로 좌표계를 바꾸지 않는다.
//
// ⚠️ 마스크가 이 격자 안에 한 칸도 없으면 원 상자로 돌아간다. 빈 상자는 `{0,0,0,0}`으로
//    무너져 좌표계 전체를 조용히 옮긴다 — 미상은 0이 아니다.
//
// ⚠️ 로드와 렌더가 **같은 상자**를 보는 것이 안전의 근거다. `c − box.minC + startX`(렌더)와
//    `dbX − startX + box.minC`(로드)는 같은 상자에서만 역함수이고, 그때 Push가 쓰는 좌표는
//    로드가 읽은 좌표와 항등이다. 그래서 `loadExistingMap`은 셀을 놓기 **전에**
//    `resolveValidDie`를 끝낸다(사용자 지시의 순서: 유효 다이맵 → 오리진 → 셀 위치).
// ═══════════════════════════════════════════════════════════════════════════════

// `opts.circleOnly` — 마스크와 무관하게 **원 기하**의 상자를 묻는다. 유일한 소비자는
// `computeNotchCell`이다: 노치는 웨이퍼의 물리 특징이자 클립보드 프레임 지문이라, 유효 다이
// 해석의 성패(네트워크 1회 실패)에 따라 지문이 흔들리면 정상 붙여넣기가 엉뚱한 사유로 거절된다.
function getWaferBoundingBox(frame, rotation, side, opts) {
  if (frame === undefined) {
    throw new Error('getWaferBoundingBox: frame argument missing. Pass the frame that is in '
      + 'scope, or `null` to read the screen controls on purpose.');
  }
  // 프레임 창이 **상자까지** 실어 나르면 그것이 이 창의 상자다. 창은 "규격을 어디서 읽는가"를
  // 갈아끼우는 장치이고(§withPhysFrame), 원점 상자는 그 규격의 산물이므로 같은 창에 실린다.
  //
  // 🔴 **두 번째 상자 정의가 아니다.** 창에 실리는 상자는 언제나 이 함수가 앞서 만들어 낸
  //    바로 그 상자다(§seatingSnapshot이 붙들어 둔 것). 상자가 **무엇인가**는 여전히 이 함수
  //    하나만 답하고, 창은 "그때 그 답"을 다시 제시할 뿐이다.
  // 🔴 다시 계산해서 얻을 수 **없는** 이유: 근거가 유효 다이 맵일 때 창 안에서는
  //    `isValidDieAt`이 원으로 답하므로(§isValidDieAt) 옛 마스크 상자는 원리적으로
  //    재구성되지 않는다. 그래서 붙들어 두는 것 말고 다른 방법이 없다.
  // ⚠️ `circleOnly`가 이 창보다 세다. 노치는 마스크와 무관한 물리 특징을 묻는 자리라
  //    (§computeNotchCell) 마스크에서 유래한 상자를 받으면 지문이 흔들린다.
  if (frame && frame.box && !(opts && opts.circleOnly)) {
    return frame.box;
  }
  // 프레임 창이 열려 있으면 소스 메타 값이, 아니면 화면 컨트롤 값이 읽힌다.
  // 캐시 키를 해석된 실값으로 만들어야 두 프레임의 바운딩박스가 서로를 덮어쓰지 않는다.
  const dia = physNum(frame, 'waferDia', el.physWaferDia, 300);
  const cx = physNum(frame, 'chipX', el.physChipX, 2.5);
  const cy = physNum(frame, 'chipY', el.physChipY, 2.5);
  const ox = physNum(frame, 'offsetX', el.physOffsetX, 0.0);
  const oy = physNum(frame, 'offsetY', el.physOffsetY, 0.0);
  const em = physNum(frame, 'edgeMargin', el.physEdgeMargin, 3.0);

  const cols = gridDimNum(frame, 'cols', el.gridCols, 10);
  const rows = gridDimNum(frame, 'rows', el.gridRows, 10);
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // 이 상자가 어느 근거로 만들어지는가 — 캐시 키의 첫 항이다.
  // 'C' = 원 기하(circle · refused · template · 프레임 창 안) · 'V<세대>' = 해석된 유효 다이 맵.
  //
  // 🔴 **세대 번호**를 쓴다. 셀 **개수**로 태그를 만들면 같은 크기의 다른 참조가 서로의 상자를
  //    덮어써서, 지정을 바꿔도 좌표계가 이전 참조 그대로 남는다. `ref`를 만드는 유일한 자리가
  //    `resolveValidDie`이고 그 함수는 진입마다 이 번호를 올린다.
  // ⚠️ 프레임 창 안은 `isValidDieAt`이 이미 원으로 답하므로 **결과**는 어차피 원이다. 태그가
  //    실제로 사는 이유는 캐시 **슬롯**이다: 창의 규격이 화면 값으로 폴백하면 키의 나머지가
  //    마스크 항목과 글자 그대로 같아져, 창이 채운 원 상자를 편집기가 마스크 상자로 받는다.
  // ⚠️ 별도 함수로 빼지 않는다. 이 함수를 슬라이스해 실행하는 하네스가 넷이고, 모듈 전역
  //    의존이 하나 늘 때마다 넷이 전부 ReferenceError로 죽는다 — 실측: 이 라운드에서 그렇게
  //    세 하네스가 죽었고, `loadExistingMap`의 catch가 그것을 "0셀 로드"로 삼켰다.
  const maskDeclaresTheFrame = !(opts && opts.circleOnly)
    && !frame
    && validDieBasis() === 'ref';
  const tag = maskDeclaresTheFrame ? `V${validDieResolveSeq}` : 'C';
  const key = `${tag}_${rotation}_${side}_${visualCols}_${visualRows}_${dia}_${cx}_${cy}_${ox}_${oy}_${em}`;
  if (boundingBoxCache[key]) {
    return boundingBoxCache[key];
  }

  const physConfig = getTransformedPhysicalConfig(frame, rotation, side);
  const width = 700;
  const height = 700;

  const useMask = (tag !== 'C');

  let minC = 9999, maxC = -9999;
  let minR = 9999, maxR = -9999;
  let insideCount = 0;
  // 마스크 누적기. 같은 순회 안에서 함께 센다 — 두 번째 전수 순회를 만들지 않기 위해서다.
  let mMinC = 9999, mMaxC = -9999;
  let mMinR = 9999, mMaxR = -9999;
  let maskCount = 0;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      const circleInside = isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height);
      if (circleInside) {
        insideCount++;
        if (c < minC) minC = c;
        if (c > maxC) maxC = c;
        if (r < minR) minR = r;
        if (r > maxR) maxR = r;
      }
      if (useMask) {
        // 렌더 루프가 쓰는 것과 **같은 두 줄**이다(§renderGridCanvas 5b 위). 물리 좌표를
        // 여기서 따로 만들지 않으면 판정할 수 없고, 따로 만드는 식은 그 함수 하나뿐이다.
        const p = getDieIndex(frame, c, r, cols, rows, rotation, side);
        if (isValidDieAt(frame, p.x, p.y, circleInside)) {
          maskCount++;
          if (c < mMinC) mMinC = c;
          if (c > mMaxC) mMaxC = c;
          if (r < mMinR) mMinR = r;
          if (r > mMaxR) mMaxR = r;
        }
      }
    }
  }

  if (useMask && maskCount === 0) {
    // 마스크가 이 격자 안에 한 칸도 앉지 않았다. 사용자 판정 「밀리게 그냥 보여주기」는
    // 밀린 마스크를 그대로 보이라는 것이지, 좌표계를 0으로 무너뜨리라는 뜻이 아니다.
    console.warn('[Map Editor] valid-die mask has no cell inside the current grid — '
      + 'origin box falls back to the wafer circle (coordinates unchanged)');
  }

  const src = (useMask && maskCount > 0)
    ? { minC: mMinC, maxC: mMaxC, minR: mMinR, maxR: mMaxR }
    : { minC, maxC, minR, maxR };

  const box = {
    minC: src.minC === 9999 ? 0 : src.minC,
    maxC: src.maxC === -9999 ? 0 : src.maxC,
    minR: src.minR === 9999 ? 0 : src.minR,
    maxR: src.maxR === -9999 ? 0 : src.maxR
  };

  boundingBoxCache[key] = box;
  return box;
}

function getDbCoords(frame, colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY) {
  if (frame === undefined) {
    throw new Error('getDbCoords: frame argument missing. Pass the frame that is in scope, or `null` '
      + 'to read the screen controls on purpose.');
  }
  const box = getWaferBoundingBox(frame, rotation, side);

  const dbX = colVisual - box.minC + startX;

  let dbY = 0;
  if (!invertY) {
    dbY = rowVisual - box.minR + startY;
  } else {
    dbY = box.maxR - rowVisual + startY;
  }

  return { x: dbX, y: dbY };
}

// ═══════════════════════════════════════════════════════════════════════════════
// 화면의 셀이 **지금 앉아 있는 좌표계**. 상자 하나와 그 상자를 낳은 축 전부다.
//
// 🔴 이것은 상자에 대한 **두 번째 진실이 아니다.** 상자가 무엇인가는 `getWaferBoundingBox`
//    하나만 답한다. 여기 담기는 것은 그 함수가 이미 내놓은 답이고, 뜻은 "무엇이 옳은가"가
//    아니라 **"셀이 마지막으로 어디에 앉았는가"**다. 둘을 대조해 화해시켜야 하는 상황이
//    생긴다면 그건 설계가 틀린 것이므로 화해시키지 말고 보고할 것.
//
// 🔴 이 기록이 **필요한** 이유는 물리 규격 입력의 리스너가 변경 **전** 상태를 잡을 수 없기
//    때문이다 — `input`/`change`는 DOM 값이 이미 바뀐 뒤에 뜬다. 유효 다이 지정 경로는
//    `resolveValidDie`가 스스로 변경 전후를 감싸므로 그 문제가 없었다.
//
// ⚠️ 축은 **cols/rows/회전/면/invertY/START + 물리 규격 전부**다. 이 객체를 그대로
//    `withPhysFrame`에 넘겨 옛 좌표계를 다시 열기 때문에, 키 이름은 `currentFrame`·
//    `frameFromMeta`가 쓰는 그 이름이어야 한다(`physNum`/`gridDimNum`이 그 이름으로 읽는다).
// ═══════════════════════════════════════════════════════════════════════════════
let cellsSeatedUnder = null;

function seatingSnapshot(frame) {
  if (frame === undefined) {
    throw new Error('seatingSnapshot: frame argument missing. Pass the frame that is in scope, '
      + 'or `null` to record the screen seating on purpose.');
  }
  if (!el || !el.gridCols || !el.gridRows || !el.gridStartX || !el.gridStartY) return null;
  // 창 안에서 부르면 소스 맵의 좌석을 이 화면의 좌석으로 기록하게 된다. 그런 호출자는 없지만,
  // 생기는 날 조용히 틀리는 대신 아무것도 기록하지 않는다.
  // 프레임을 받으면 소스 맵의 좌석을 이 화면의 좌석으로 기록하게 된다.
  // ⚠️ **이 가드는 지금 어떤 호출자도 실행하지 않는다** — 전 호출자가 `null`을 넘긴다. 변이로
  //    지워도 빨개지는 하네스가 없다(측정 2026-08-06). 없는 호출자를 막는 방어라 그것이
  //    정상이고, 채점되지 않는다는 사실을 여기 적어 둔다.
  if (frame) return null;
  return {
    cols: gridDimNum(frame, 'cols', el.gridCols, 10),
    rows: gridDimNum(null, 'rows', el.gridRows, 10),
    rotation: currentRotation,
    side: currentSide,
    invertY: !!(el.gridYInvert && el.gridYInvert.checked),
    startX: parseInt(el.gridStartX.value, 10) || 0,
    startY: parseInt(el.gridStartY.value, 10) || 0,
    waferDia: physNum(null, 'waferDia', el.physWaferDia, 300),
    chipX: physNum(null, 'chipX', el.physChipX, 2.5),
    chipY: physNum(null, 'chipY', el.physChipY, 2.5),
    offsetX: physNum(null, 'offsetX', el.physOffsetX, 0.0),
    offsetY: physNum(null, 'offsetY', el.physOffsetY, 0.0),
    edgeMargin: physNum(null, 'edgeMargin', el.physEdgeMargin, 3.0),
    box: getWaferBoundingBox(null, currentRotation, currentSide),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// [규칙 ④] **원점 상자가 셀 밑에서 움직였을 때의 유일한 반응.**
//
// 붙드는 것은 **저장 좌표**이고 움직이는 것은 **캔버스 칸**이다(사용자 확정:「db 좌표
// 보존이야」). 셀이 칸을 붙들면 근거가 바뀔 때 읽는 번호가 바뀌고, ⚡ Push가 그 새 번호를
// 쓴다 — 화면은 한 픽셀도 움직이지 않은 채 DB의 좌표가 갈리는, 이 도메인이 존재하는 그 결함이다.
//
// 🔴 **근거가 무엇이든 같은 반응이다.** 유효 다이 선언이 없는 맵에서 유효 다이 영역은 곧
//    웨이퍼 원이므로(사용자 확정 2026-07-31:「유효 다이 없이 기하 프리셋 변경도 유효 다이
//    영역을 원 기하 내부로 변경하므로」), 기하 프리셋을 바꾸는 것과 참조를 지정하는 것은
//    **같은 연산**이지 닮은 연산이 아니다. 그래서 함수도 하나다 — 마스크가 선언된 맵에서
//    이 함수는 0칸을 옮기는데, 그건 가정이 아니라 **측정된** 0이다(마스크 상자는 셀과 함께
//    평행이동하므로 저장 좌표가 애초에 변하지 않는다).
//
// 🔴 **방향(회전·반전·Y반전)과 START는 반대 연산이다**(규칙 ⑤: 다이를 붙들고 번호를 옮긴다).
//    그 축이 하나라도 다르면 이 반응은 **아무것도 하지 않는다.** 기하 반응이 회전에서 뜨면
//    규칙 ④가 규칙 ⑤를 덮어쓴다.
//
// 🔴 **새 변환식은 한 줄도 없다.** 옛 좌표계는 `withPhysFrame`으로 다시 열고(불변식 ①:
//    규격을 읽는 지점만 갈아끼우고 같은 함수를 실행한다), 그 안에서 도는 것은 로드·렌더가
//    쓰는 `getCanvasCellFromDieIndex`·`getDbCoords`이며, 되앉히는 것은 그 둘의 역함수인
//    `getCanvasCellFromDb`·`getDieIndex`다.
//
// ⚠️ 호출자는 기록을 **캐시하지 않는다.** 반드시 부르는 시점에 `cellsSeatedUnder`를 읽어야
//    한다 — 이 함수가 끝날 때마다 기록을 갱신하므로, 한 번의 사용자 조작이 이 반응을 두 번
//    타도(규격 교체 → 파생 치수, 그다음 마스크 적합 확장) 두 걸음이 이어 붙어 저장 좌표가
//    보존된다. 미리 잡아 둔 옛 기록을 두 번째 걸음에 넘기면 같은 이동을 두 번 적용한다.
//
// 반환: null(반응 없음) | { moved, offGrid, visC, visR, held }
// ═══════════════════════════════════════════════════════════════════════════════
function reseatCellsToStoredCoords(was) {
  const now = seatingSnapshot(null);
  if (now) cellsSeatedUnder = now;
  if (!was || !now) return null;
  if (was.rotation !== now.rotation || was.side !== now.side || was.invertY !== now.invertY
    || was.startX !== now.startX || was.startY !== now.startY) return null;

  const touched = new Set([...Object.keys(gridData), ...loadedFCells,
  ...(serverCellKeys && serverCellKeys.keys ? serverCellKeys.keys : [])]);
  if (touched.size === 0) return null;

  // (1) 각 셀이 **옛 좌표계에서** 말하던 저장 좌표를 되찾는다.
  const held = new Map();
  {
    touched.forEach(k => {
      const [px, py] = String(k).split('_').map(Number);
      if (!Number.isFinite(px) || !Number.isFinite(py)) return;
      const at = getCanvasCellFromDieIndex(was, px, py, was.cols, was.rows, was.rotation, was.side);
      held.set(k, getDbCoords(was, at.c, at.r, was.cols, was.rows, was.rotation, was.side,
        was.invertY, was.startX, was.startY));
    });
  }

  // (2) 그 저장 좌표가 **새 좌표계에서** 가리키는 칸으로 다시 앉힌다.
  const isRot = (now.rotation === 90 || now.rotation === 270);
  const visC = isRot ? now.rows : now.cols;
  const visR = isRot ? now.cols : now.rows;
  let offGrid = 0;
  const seatOf = new Map();
  held.forEach((v, k) => {
    const cell = getCanvasCellFromDb(null, v.x, v.y, now.cols, now.rows, now.rotation, now.side,
      now.invertY, now.startX, now.startY);
    if (cell.c < 0 || cell.c >= visC || cell.r < 0 || cell.r >= visR) offGrid++;
    const p = getDieIndex(null, cell.c, cell.r, now.cols, now.rows, now.rotation, now.side);
    seatOf.set(k, `${p.x}_${p.y}`);
  });
  let moved = 0;
  seatOf.forEach((to, from) => { if (to !== from) moved++; });
  if (moved > 0) {
    const at = (k) => seatOf.get(k) || k;
    const next = {};
    Object.keys(gridData).forEach(k => { next[at(k)] = gridData[k]; });
    gridData = next;
    loadedFCells = new Set([...loadedFCells].map(at));
    // 서버 셀 집합도 같이 옮긴다. 옮기지 않으면 서버에서 온 셀이 「보낸 적 없음」으로 읽혀
    // 정리 경로가 실재하는 행을 지우자고 제안한다(불변식 ③).
    if (serverCellKeys && serverCellKeys.keys) {
      serverCellKeys.keys = new Set([...serverCellKeys.keys].map(at));
    }
  }
  return { moved, offGrid, visC, visR, held: held.size };
}

// [S2.3] `frame` first, same contract as `physNum`: `null` = read the screen deliberately,
// `undefined` = the caller forgot. This function is the only place the six physical axes are
// turned into a config object, so it is on the path of every coordinate the editor computes —
// which is why the frame has to reach it as a value rather than be picked up from the module.
//
// ⚠️ `currentRotation`/`currentSide` SHADOW two module bindings of the same name. That is
//    pre-existing and deliberately left alone this round (behaviour must not change), but it
//    is a trap for anyone reading the body: inside here those names are the ARGUMENTS.
function getTransformedPhysicalConfig(frame, currentRotation, currentSide) {
  if (frame === undefined) {
    throw new Error('getTransformedPhysicalConfig: frame argument missing. Pass the frame that '
      + 'is in scope, or `null` to read the screen controls on purpose.');
  }
  const waferDia = physNum(frame, 'waferDia', el.physWaferDia, 300);
  const edgeMargin = physNum(frame, 'edgeMargin', el.physEdgeMargin, 3.0);
  const effectiveRadius = Math.max(0, (waferDia / 2.0) - edgeMargin);
  const origChipX = physNum(frame, 'chipX', el.physChipX, 2.5);
  const origChipY = physNum(frame, 'chipY', el.physChipY, 2.5);
  let origOffsetX = physNum(frame, 'offsetX', el.physOffsetX, 0.0);
  let origOffsetY = physNum(frame, 'offsetY', el.physOffsetY, 0.0);

  if (currentSide === 'back') {
    origOffsetX = -origOffsetX;
  }

  let chipX = origChipX;
  let chipY = origChipY;
  if (currentRotation === 90 || currentRotation === 270) {
    chipX = origChipY;
    chipY = origChipX;
  }

  return {
    waferDia,
    effectiveRadius,
    radiusSq: effectiveRadius * effectiveRadius,
    chipX,
    chipY,
    origChipX,
    origChipY,
    origOffsetX,
    origOffsetY,
    rotation: currentRotation,
    side: currentSide
  };
}

function getScreenShift(physConfig, cellW, cellH) {
  if (!physConfig) return { shiftX: 0, shiftY: 0 };
  const { origOffsetX, origOffsetY, origChipX, origChipY, rotation } = physConfig;
  const chipX = origChipX || 2.5;
  const chipY = origChipY || 2.5;

  let shiftX = 0;
  let shiftY = 0;

  if (rotation === 0) {
    shiftX = (origOffsetX / chipX) * cellW;
    shiftY = -(origOffsetY / chipY) * cellH;
  } else if (rotation === 90) {
    shiftX = (origOffsetY / chipY) * cellW;
    shiftY = (origOffsetX / chipX) * cellH;
  } else if (rotation === 180) {
    shiftX = -(origOffsetX / chipX) * cellW;
    shiftY = (origOffsetY / chipY) * cellH;
  } else if (rotation === 270) {
    shiftX = -(origOffsetY / chipY) * cellW;
    shiftY = -(origOffsetX / chipX) * cellH;
  }

  return { shiftX, shiftY };
}

// ═══════════════════════════════════════════════════════════════════════════════
// [C1] 셀 하나가 화면에서 차지하는 픽셀. **밀리미터당 픽셀이 두 축에서 같다** —
// 그래야 웨이퍼 외곽이 원으로 그려진다.
//
// 🔴 THE DEFECT. 종전에는 `cellW = width / visualCols`, `cellH = height / visualRows`라
//    두 축의 mm/px가 서로 달랐다. 그래서 셀은 언제나 정사각형이었고 원은
//    `cellW/chipX != cellH/chipY`인 순간 타원이 됐다 — 즉 칩 피치가 정사각이 아니거나
//    캔버스 종횡비가 격자 종횡비와 다르면 **언제나**. 실측(chipX 9 · chipY 11 · 15x11 격자):
//    700x700 캔버스에서 rx/ry = 0.8963, 900x380에서 2.1228.
//    원을 그리는 코드로는 못 고친다: 타원의 원인은 **셀**이고, 셀을 고치면 원은 저절로
//    원이 된다. 그 대가로 `phys_chip_x != phys_chip_y`인 맵의 셀은 직사각형이 된다 —
//    부작용이 아니라 요청된 결과다(사용자: "셀이 정사각형이고 원이 찌그러짐").
//
// 🔴 **피치를 지어내지 않는다.** 선언이 없으면 종횡비를 알 수 없고, 한 축을 다른 축으로
//    메우는 것이 「화면은 완벽히 정렬되는데 값은 전부 틀린」 그 결함이다(실측 570/600 —
//    §오버레이 피치 관문). 그래서 판정은 `physDeclaration`이지 `physNum`의 출력이 아니다:
//    후자는 기본값 2.5를 접은 뒤라 「선언 없음」이 관측 불가능하다(§physDeclaration).
//    선언이 없으면 **종전 동작 그대로**를 돌려주고(`isotropic: false`), 화면이 미상을 말한다.
//
// 🔴 격자는 캔버스 **중앙**에 앉는다(`padX`/`padY`). 그래서 격자 중심 == 캔버스 중심이
//    유지되고, `isCellInsideWaferFast`의 판정식에서 픽셀 항이 그대로 상쇄된다:
//      dx/effRadX = [(c − visualCols/2)·chipX + offsetX] / effectiveRadius   (순수 mm)
//    즉 **어느 칸이 유효 다이인가는 이 변경으로 한 칸도 바뀌지 않는다.** 그래서
//    `isCellInsideWaferFast`는 손대지 않는다 — 그 함수의 크기 불변성(§8127)에
//    `getWaferBoundingBox`(700x700 고정)와 `canvasSeatKeys`가 얹혀 있다.
//
// ⚠️ 순수 함수다. 이 파일의 module-state 천장은 여유가 0이므로 상태를 만들지 않는다.
// ═══════════════════════════════════════════════════════════════════════════════
function cellMetrics(width, height, visualCols, visualRows, physConfig) {
  // [C2] 폴백에는 웨이퍼 기준 축척이 없다 — 두 축의 mm/px가 애초에 다르므로 붙일 자리가
  //      없다. `waferAnchored: false`는 그 사실 그대로다(지름 선언 여부에 대한 주장이
  //      아니다 — 그 구별은 `isotropic`이 이미 말한다).
  const anisotropicFallback = {
    cellW: width / visualCols, cellH: height / visualRows,
    padX: 0, padY: 0, isotropic: false, waferAnchored: false,
  };
  if (!(visualCols > 0) || !(visualRows > 0) || !(width > 0) || !(height > 0)) return anisotropicFallback;
  const dx = physDeclaration(null, 'chipX', el.physChipX);
  const dy = physDeclaration(null, 'chipY', el.physChipY);
  if (!(dx.value > 0) || !(dy.value > 0)) return anisotropicFallback;
  // 회전된 규격을 쓴다 — `visualCols`도 회전된 축이라 둘이 같은 방향을 가리켜야 한다.
  const chipX = physConfig ? physConfig.chipX : 0;
  const chipY = physConfig ? physConfig.chipY : 0;
  if (!(chipX > 0) || !(chipY > 0)) return anisotropicFallback;

  // px per mm, 두 축 공통.
  //
  // [C2] 축척의 기준은 **웨이퍼**다 — 격자가 아니다. (사용자 2026-08-04: "원크기도 항상
  //      일정하게 — 지금 원크기 변함".) 웨이퍼는 맵마다 같은 물리 객체이므로 화면에서의
  //      크기도 같아야 한다. 종전에는 축척이 격자에서만 나와서(`sGrid`) 누가 어떻게 격자를
  //      끊었는지가 원의 크기를 정했다. 실측(캔버스 700x700, 선언 지름 300mm 동일):
  //        20x20 격자 피치 6mm → 원 반지름 875.000px
  //        40x40 격자 피치 3mm → 875.000px      (같은 격자 범위, 다른 치수)
  //        52x52 격자 피치 6mm → 336.538px      ← 같은 웨이퍼가 2.6배 다르게 그려졌다
  //      기준을 지름으로 옮기면 원이 캔버스의 고정 비율을 차지하고, 격자가 그 원에 대해
  //      상대적으로 그려져 **격자가 웨이퍼의 얼마를 덮는가**가 화면에 남는다. 종전 규칙은
  //      그 정보를 매번 지웠다(격자가 늘 캔버스를 꽉 채웠으므로).
  //
  // 🔴 `effectiveRadius`가 아니라 `waferDia`다. 전자는 edge margin(공정 파라미터)을 이미
  //    접고 있어서, margin 3mm와 5mm로 선언된 **같은** 300mm 웨이퍼가 서로 다른 크기로
  //    그려진다. "같은 웨이퍼는 같아 보인다"가 글자 그대로 참이 되는 쪽은 지름이다.
  //
  // 🔴 **`min(sGrid, sWafer)`이지 `sWafer`가 아니다. 이건 미관이 아니라 데이터다.**
  //    `renderGridCanvas`의 캔버스 밖 `continue`는 `gridCells2D` 등록보다 **앞**에 있다.
  //    그래서 캔버스를 넘친 선언 칸은 등록되지 않고 → `eachSavableCell`의 정의역 밖이 되어
  //    **저장 페이로드에서 조용히 사라진다.** `s <= sGrid`를 지키면 `padX`/`padY >= 0`이
  //    보장되어 선언된 격자는 언제나 캔버스 안이다. 격자가 웨이퍼보다 크면 격자가 축척을
  //    잡고 원이 작아지는데, 그것은 지어낸 것이 아니라 참인 사실이다(그 격자는 웨이퍼보다
  //    크다). 잘라 그리는 선택지는 이 도메인이 941060f에서 닫은 「아무도 안 보는 곳에
  //    숨는다」와 같은 부류라 택하지 않는다.
  //
  // 🔴 **지름을 지어내지 않는다.** 선언이 없을 때 `physNum`의 기본값 300으로 메우면, 그
  //    지어낸 물리량이 렌더 전체를 지배하면서 화면은 완벽히 정렬된 채로 값만 틀린다.
  //    선언이 없으면 종전 규칙(`sGrid`)으로 그대로 물러나고 화면이 그렇게 말한다
  //    (`waferAnchored: false` → `renderGridCanvas`의 수동 표기).
  const sGrid = Math.min(width / (visualCols * chipX), height / (visualRows * chipY));
  const dd = physDeclaration(null, 'waferDia', el.physWaferDia);
  const waferAnchored = dd.value > 0;
  // 캔버스 짧은 변 대비 웨이퍼 **지름**의 고정 비율. 남는 6%는 원의 선 두께와 격자
  // 외곽선이 앉을 자리다 — 원이 캔버스 가장자리에 닿아 잘려 보이지 않게 한다.
  const sWafer = waferAnchored ? (Math.min(width, height) * 0.94) / dd.value : Infinity;
  const s = Math.min(sGrid, sWafer);
  const cellW = chipX * s;
  const cellH = chipY * s;
  return {
    cellW, cellH,
    padX: (width - visualCols * cellW) / 2,
    padY: (height - visualRows * cellH) / 2,
    isotropic: true,
    waferAnchored,
  };
}

function isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width = 700, height = 700) {
  if (physConfig && physConfig.chipX > 0 && physConfig.chipY > 0 && physConfig.effectiveRadius > 0 && width > 0 && height > 0) {
    const cellW = width / visualCols;
    const cellH = height / visualRows;

    const { shiftX, shiftY } = getScreenShift(physConfig, cellW, cellH);

    const x0 = c * cellW + shiftX;
    const y0 = r * cellH + shiftY;

    const centerX = width / 2.0;
    const centerY = height / 2.0;

    const effRadX = (physConfig.effectiveRadius / physConfig.chipX) * cellW;
    const effRadY = (physConfig.effectiveRadius / physConfig.chipY) * cellH;

    const corners = [
      { x: x0, y: y0 },
      { x: x0 + cellW, y: y0 },
      { x: x0, y: y0 + cellH },
      { x: x0 + cellW, y: y0 + cellH }
    ];

    for (const corner of corners) {
      const dx = corner.x - centerX;
      const dy = corner.y - centerY;
      const normDistSq = (dx * dx) / (effRadX * effRadX) + (dy * dy) / (effRadY * effRadY);
      if (normDistSq > 1.0) {
        return false;
      }
    }

    return true;
  }

  return false;
}

function isCellInsideWafer(c, r, visualCols, visualRows) {
  const physConfig = getTransformedPhysicalConfig(null, currentRotation, currentSide);
  const width = el.gridCanvas ? Math.floor(el.gridCanvas.getBoundingClientRect().width || 700) : 700;
  const height = el.gridCanvas ? Math.floor(el.gridCanvas.getBoundingClientRect().height || 700) : 700;
  return isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height);
}

// ═══════════════════════════════════════════════════════════════════════════════
// [M4 phase 1] 유효 다이의 근거 — `valid_die_ref` 소비
//
// 원 기하는 "어느 칸이 실물 다이인가"의 **판정자**였다. M4는 그것을 생성기로 강등하고
// 판정을 **맵 하나**에 넘긴다: 유효 다이도 맵이며, 마스크 편집이 곧 페인팅이다.
// 이 단계(①)는 **소비만** 한다 — 프리셋=템플릿 생성기(②)와 `inside`에서 원 은퇴(③)는
// 별개 라운드다.
//
// 🔴 **가산적 공존이 수용 기준이다.** `valid_die_ref`가 없는 맵은 `2a9f6c4`와 완전히 같이
//    동작해야 한다. 그래서 판정은 `isValidDieAt` 한 곳에서만 갈라지고, 참조가 없으면
//    호출자가 이미 계산해 둔 원 판정을 **그대로** 돌려준다.
//
// 🔴 **바운딩 박스는 건드리지 않는다.** `getWaferBoundingBox`는 유효 셀 집합의 최소 사각형이고
//    `getDbCoords`가 그걸로 **DB에 저장되는 x/y**를 만든다. 유효 다이 집합을 bbox에
//    먹이면 같은 맵의 좌표가 조용히 다른 수로 재해석된다 — 화면은 멀쩡한데 값이 틀리는
//    그 결함이다. 좌표계는 방향·물리 규격에서만 파생된다(SPEC §5.0 불변식).
//    그래서 `getWaferBoundingBox`는 계속 `isCellInsideWaferFast`(원)를 직접 부른다.
//
// 상태 3종 — 이름은 서버 `map_overlay.resolve_valid_die_basis`의 `source`와 **글자 그대로
// 같다**(`contracts/map_seam/vectors.json`이 정본). 한 이음매에 두 어휘가 흐르면
// `declared` vs `derived` 때처럼 어느 쪽이 진짜인지 아무도 모르게 된다:
//   circle  — 선언이 없다. `2a9f6c4` 그대로.
//   ref     — 참조가 해석됐다. 그 맵이 **유일한** 근거이고 원은 참여하지 않는다.
//   refused — 선언은 있는데 해석하지 못했다. 조용히 원으로 되돌아가지 않는다:
//             이유를 칩·토스트·콘솔 세 곳에 남긴다(§아래 renderValidDieChip).
// ═══════════════════════════════════════════════════════════════════════════════
// raw = 메타에 실린 `valid_die_ref` 원문(키 자체가 없으면 undefined). Push 시 그대로 되쓴다.
let validDie = { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };

// [1-a] THE STORAGE TABLE OF A VALID-DIE MAP. Fixed, not chosen (user ruling 2026-08-04):
// "유효 다이 맵을 저장하는 테이블은 valid_die_ref라는 테이블로 항상 고정 ... 불러오기는
//  무조건 valid_die_ref 를 이용하게".
//
// 🔴 The ruling covers BOTH sides now — authoring AND loading. The previous round pinned only
//    authoring and left `parseValidDieRef` honouring whatever table a stored reference names;
//    the user re-stated the requirement and it is explicit, so the reader is pinned too.
//    What that costs, stated plainly rather than discovered later: the 8 declarations written
//    before this ruling name `bonding_map`/`dt_map`, and their keys do not exist in
//    `valid_die_ref`. They will REFUSE by name (§resolveReferenceSpec) — they will not fall
//    back to circle geometry and they will not render an empty mask. The user ruled that
//    losing those dev-environment masks is acceptable; a mask that is silently wrong is not.
// 🔴 Reading is pinned; WRITING still preserves the declared bytes. An untouched legacy row is
//    never rewritten (`validDieRefForPush` keeps `raw` verbatim), so `valid_die_push_decision_
//    cases` still expects `tpl_map` back out of the payload while `valid_die_ref_parse_cases`
//    expects `valid_die_ref` on the way in. Those two are no longer the same number, which is
//    exactly why the seam scores them through two different readers.
// (The former `validDieRefTableTouched` flag lived here. It existed only to tell a user-chosen
//  table apart from one the app forced into a <select>; with the <select> gone there is no
//  such ambiguity, and its invariant — an untouched declaration is never rewritten — now rests
//  on the key comparison in `validDieRefFromControls`.)
const VALID_DIE_TABLE = 'valid_die_ref';

// [M4② F3] 유효 다이 해석의 **세대 번호**. `overlaySeq`와 같은 프리미티브다(§오버레이).
// ①에서는 로드가 한 번 await하는 게 전부였지만 ②에서 해석이 **사용자 주도로 반복** 호출되므로
// 늦게 도착한 해석이 새 상태를 덮는 경로가 생겼다: `TPL_A`(느림) → `TPL_B`(빠름) 순서로
// 시작하면 A가 나중에 착지해 basis도 입력칸도 A로 되돌리고 Push가 A를 쓴다.
// 상태를 갈아치우는 쪽(`resolveValidDie` 진입 · 저작 진입)이 이 번호를 올리고,
// 착지 시점에 자기 번호가 낡았으면 **아무것도 하지 않는다**(last-write-wins가 아니라 최신-승).
let validDieResolveSeq = 0;

// 선언의 해석. **순수 함수** — 네트워크를 타지 않으므로 계약 벡터로 바로 채점된다.
// 반환: null(선언 없음) | {table, mapKey, declaredTable} | {unreadable: true, reason}
//
// 규칙 하나로 말하면: **`null`/부재만 "선언 없음"이고, 그 외에는 전부 선언이다.**
// 읽을 수 없는 선언을 "선언 없음"으로 접으면 오타 하나가 조용히 원 기하로 되돌아간다 —
// 틀린 답과 맞는 답이 구별되지 않는 바로 그 상태다.
//
// [1-a] `table`은 **언제나** `VALID_DIE_TABLE`이다(사용자 지시: "불러오기는 무조건
// valid_die_ref 를 이용하게"). 선언이 이름 붙인 테이블은 버리지 않고 `declaredTable`로
// 함께 돌려준다 — 해석이 실패했을 때 "키가 틀렸다"와 "키는 맞는데 여기 없다"는 서로 다른
// 수리를 요구하므로, 거절문이 그 둘을 구별해 말할 수 있어야 한다.
// `currentTable`은 이제 조회 대상을 정하지 **않는다**. 선언이 원래 무엇을 뜻했는지(맨
// 문자열 = "내 테이블의 맵")를 되살려 `declaredTable`에 담는 데만 쓴다 — 지운 정보를
// 나중에 추측으로 복원하는 일을 만들지 않기 위해서다.
function parseValidDieRef(meta, currentTable) {
  if (!meta || typeof meta !== 'object') return null;
  if (!('valid_die_ref' in meta)) return null;
  const raw = meta.valid_die_ref;
  if (raw === null || raw === undefined) return null;
  const bad = (reason) => ({ unreadable: true, reason });
  const home = String(currentTable || '');

  if (typeof raw === 'string') {
    const s = raw.trim();
    if (s === '') return bad('valid_die_ref가 비어 있습니다 — 맵 키가 없으면 유효 다이를 판정할 근거가 없습니다.');
    // PINNED READ (string form). Pre-ruling this meant "a map in MY table"; that meaning is
    // kept as `declaredTable` for the refusal message and NOT as the lookup target.
    return { table: VALID_DIE_TABLE, mapKey: s, declaredTable: home };
  }
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    return bad(`valid_die_ref의 형태를 읽을 수 없습니다 (${typeof raw}) — {table, map_id} 또는 맵 키 문자열이어야 합니다.`);
  }
  // `target_table`은 wafer_map_metadata가 실제로 쓰는 컬럼명이고 `table`은 그 짧은 이름이다 —
  // 같은 한 쌍을 가리키는 두 이름이라 둘 다 받는다. 그 밖의 이름은 추측하지 않는다.
  const t = raw.table !== undefined ? raw.table : raw.target_table;
  const k = raw.map_id !== undefined ? raw.map_id : raw.map_key;
  const key = (k === null || k === undefined) ? '' : String(k).trim();
  if (key === '') {
    return bad('valid_die_ref에 map_id가 없습니다 — 어느 맵을 가리키는지 알 수 없습니다.');
  }
  // 종전에는 여기서 테이블이 비면 「대상 테이블을 알 수 없습니다」로 거절했다. 고정 이후
  // 대상은 알 수 없어질 수가 없으므로 그 가지는 사라진다 — 그 결과 이음매의 선언된
  // 불일치 하나(`object_no_table_no_home`: 서버는 ref, 클라는 error)가 **닫힌다**.
  const declaredTable = (t === null || t === undefined || String(t).trim() === '') ? home : String(t).trim();
  // PINNED READ (object form). 선언이 어느 테이블을 이름 붙였든 조회는 valid_die_ref다.
  return { table: VALID_DIE_TABLE, mapKey: key, declaredTable };
}

// 지금 유효 다이를 무엇으로 판정하고 있는가. 셀 0개로 해석된 참조는 **해석된 것이 아니다** —
// 온 웨이퍼가 무효라는 답은 답이 아니라 사고다.
//
// `state`는 선택 인자다. 넘기지 않으면 모듈 상태 `validDie`를 읽고, 넘기면 그것을 읽는다.
// 분기가 갈라지는 게 아니라 **읽는 지점만** 바뀐다 — `physNum`이 `physFrameOverride`로
// 규격 출처를 갈아끼우는 것과 같은 형태다(SPEC §5.1). 이 인자 덕분에 이음매 하네스는
// 모듈 상태를 세팅하지 않고도 INV-M4-1/M4-2를 채점할 수 있다. **읽기만 한다.**
// [M4 phase 2] 네 번째 값 `template`이 붙었다 — **저작 중인 캔버스**다.
// 계약 어휘(`circle`/`ref`/`refused`)는 그대로다: 저 셋은 **저장된 메타에서 유도되는** 값이고
// `resolveValidDie`는 저 셋 외의 값을 절대 만들지 않는다(하네스가 소스로 단언한다).
// `template`은 메타에서 나올 수 없는 화면 상태이므로 이음매 벡터(`valid_die_basis_cases`)가
// 채점하는 집합은 한 글자도 변하지 않는다.
function validDieBasis(state) {
  const v = (state === undefined) ? validDie : state;
  if (!v) return 'circle';
  if (v.basis === 'ref' || v.basis === 'template') {
    return (v.keys && v.keys.size > 0) ? v.basis : 'refused';
  }
  return v.basis === 'refused' ? 'refused' : 'circle';
}

// 유효 다이 판정. 호출자가 **이미 계산한** 물리 좌표와 원 판정을 받는다 —
// 여기서 좌표를 다시 만들면 변환 구현이 둘이 된다(SPEC §5.1 "변환은 클라 단일 구현").
//
// **프레임이 있으면 마스크를 적용하지 않는다**: 프레임 창 안의 계산은 **소스 맵의 좌표계**를
// 푸는 중이고, 거기에 타깃 맵의 유효 다이 집합을 먹이면 조용히 다른 맵의 마스크로 소스를
// 재단하게 된다. 판정은 한 글자도 안 바뀌었고, 그 사실이 **모듈 상태가 아니라 인자로**
// 도착하게 됐을 뿐이다.
//
// 🔴 `ref`는 원과 **교집합하지 않는다**. 교집합은 보수적으로 보이지만 템플릿이 유효하다고
//    선언한 다이를 조용히 버린다 — INV-M4-2가 막는 결함이 정확히 그것이다.
//
// ⚠️ **두 선택적으로 보이는 인자는 같은 모양이 아니다.** `state`는 `validDieBasis`와 같은
//    **맨 뒤·선택** 인자가 맞다(읽는 지점만 바뀐다, 쓰지 않는다). `frame`은 그렇지 않다 —
//    **맨 앞·필수**이고 `undefined`면 던진다. 둘을 같은 규약으로 읽으면 다음 사람이 틀린
//    쪽을 고른다:
//      · `state === undefined` → 모듈의 `validDie`로 폴백한다. **정상 동작이다.**
//      · `frame === undefined` → 호출자가 잊은 것이다. 폴백하면 화면 규격으로 조용히 접혀
//        「화면은 멀쩡한데 저장값이 틀린」 상태가 되므로, 폴백하지 않고 던진다.
//        `null`은 잊은 게 아니라 **답**이다 — 「프레임 없음, 이 맵의 마스크를 걸어라」.
function isValidDieAt(frame, physX, physY, circleInside, state) {
  if (frame === undefined) {
    throw new Error('isValidDieAt: frame argument missing. Pass the frame that is in scope, '
      + 'or `null` to apply this map mask on purpose.');
  }
  if (frame) return circleInside;
  const v = (state === undefined) ? validDie : state;
  const b = validDieBasis(v);
  if (b !== 'ref' && b !== 'template') return circleInside;
  return v.keys.has(`${physX}_${physY}`);
}

// ═══════════════════════════════════════════════════════════════════════════════
// [M4 phase 2] 유효 다이 맵의 **저작** — 원 기하를 판정자에서 생성기로
//
// ①이 소비만 했다면 ②는 그 참조 대상을 **만든다**. 만드는 방법은 새 편집기가 아니라
// 이미 있는 것 셋을 잇는 것뿐이다:
//   프리셋 경로(규격) → 이 생성기(마스크 + 초기 채움) → 기존 페인팅 → 기존 ⚡ Push
//
// 🔴 **저작 캔버스는 언제나 격자 전체다.** 원 안쪽만 열면 원으로 표현 못 하는 기하를
//    영원히 만들 수 없고(dt 맵은 테이프 위라 300mm 원 제약이 없다), 저장된 템플릿을
//    **다시 열어 편집**할 수도 없다(원 밖 셀이 `inside=false`가 되어 Push의 대비 관문이
//    맵 전체를 거절한다). 그래서 원/사각의 차이는 **무엇을 칠해 두느냐**뿐이다.
//
// 🔴 **새 기하식은 한 줄도 없다.** 물리 좌표는 렌더·로드·오버레이가 쓰는 그 `getDieIndex`,
//    원 판정은 그 `isCellInsideWaferFast`다. 두 번째 구현을 만들면 화면과 저장값이 갈라진다.
//
// 🔴 **바운딩 박스는 여전히 원에서 나온다.** 마스크는 `isValidDieAt`(판정)에만 들어가고
//    `getWaferBoundingBox`(좌표계)에는 들어가지 않는다 — SPEC §5.7의 그 경계 그대로다.
//    그래서 원 밖 셀의 저장 좌표는 원 기준 bbox로 계산되고(음수가 될 수 있다), 같은 메타로
//    되읽으면 정확히 같은 물리 키로 돌아온다(INV-3이 키→값으로 대조한다).
//
// 반환: { keys: Set<물리키> — 저작 캔버스(격자 전체),
//         filled: string[]  — 이번 프리셋이 칠할 셀,
//         outsideCircle: number — 그중 원 밖 개수(정직한 확인문에 쓴다) }
// ═══════════════════════════════════════════════════════════════════════════════
function buildValidDieTemplate(shape) {
  const cols = gridDimNum(null, 'cols', el.gridCols, 10);
  const rows = gridDimNum(null, 'rows', el.gridRows, 10);
  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  const physConfig = getTransformedPhysicalConfig(null, currentRotation, currentSide);
  const width = el.gridCanvas ? Math.floor(el.gridCanvas.getBoundingClientRect().width || 700) : 700;
  const height = el.gridCanvas ? Math.floor(el.gridCanvas.getBoundingClientRect().height || 700) : 700;

  const keys = new Set();
  const filled = [];
  let outsideCircle = 0;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      const p = getDieIndex(null, c, r, cols, rows, currentRotation, currentSide);
      const key = `${p.x}_${p.y}`;
      keys.add(key);
      const circleInside = isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height);
      const wanted = (shape === 'circle') ? circleInside : true;
      if (!wanted) continue;
      filled.push(key);
      if (!circleInside) outsideCircle++;
    }
  }
  return { keys, filled, outsideCircle };
}

// 선언 원문 → 화면 컨트롤 두 칸. `validDieRefForPush`의 정확한 역함수여야 한다.
// 읽을 수 없는 선언도 **보여준다** — 지워 버리면 사용자는 자기가 무엇을 잘못 썼는지조차
// 볼 수 없다(①이 raw를 붙든 이유와 같다).
function validDieRefDisplay(raw) {
  if (raw === null || raw === undefined) return { table: '', key: '' };
  if (typeof raw === 'string') return { table: '', key: raw };
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const t = raw.table !== undefined ? raw.table : raw.target_table;
    const k = raw.map_id !== undefined ? raw.map_id : raw.map_key;
    if (k !== undefined && k !== null) {
      return { table: (t === undefined || t === null) ? '' : String(t), key: String(k) };
    }
  }
  if (typeof raw === 'number' || typeof raw === 'boolean') return { table: '', key: String(raw) };
  try { return { table: '', key: JSON.stringify(raw) }; } catch (e) { return { table: '', key: String(raw) }; }
}

// 선언의 **쓰기** — `contracts/map_seam` 역할 `apply_valid_die_ref`. 서버 `apply_valid_die_ref`와
// 같은 벡터(`valid_die_authoring_cases`)로 채점된다.
//
// 순수 함수다. `meta`를 **변형하지 않는다** — 변형하면 편집 취소 경로가 이미 바뀐 메타를
// 들고 있게 된다.
// `ref`: `null`(해제) | 맵 키 문자열 | `{table, map_id}`.
//
// 🔴 **빈 키는 해제다.** 비운 입력칸을 그대로 흘려보내면 `valid_die_ref: ""`가 저장되고,
//    파서 규칙상 그것은 **선언**이라 그 맵은 영구히 `refused`가 된다 — 되돌릴 UI가 없다.
// 🔴 **테이블 없는 객체는 만들지 않는다.** `{map_id: k}`는 서버/클라가 서로 다르게 읽기로
//    **기록된** 유일한 형태다(`valid_die_ref_home_divergence_cases`). 저작 시점에는 자기
//    테이블을 알고 있으므로 그런 반쪽 선언을 제조할 이유가 없다 — 문자열 승계형으로 쓴다.
// 🔴 **나머지 키는 손대지 않는다.** 아는 필드로 메타를 다시 짜면 모르는 키가 사라지고,
//    `v || dflt`로 베끼면 선언된 `phys_edge_margin: 0`이 3.0이 되어 참조만 지운 맵의
//    웨이퍼 마스크가 움직인다(D1과 같은 falsy 치환, 한 층 위).
function applyValidDieRef(meta, ref) {
  const out = { ...(meta && typeof meta === 'object' ? meta : {}) };
  const clear = () => { delete out.valid_die_ref; return out; };
  if (ref === null || ref === undefined) return clear();

  if (typeof ref === 'string') {
    const k = ref.trim();
    return k === '' ? clear() : (out.valid_die_ref = k, out);
  }
  if (typeof ref === 'object' && !Array.isArray(ref)) {
    const t = ref.table !== undefined ? ref.table : ref.target_table;
    const kRaw = ref.map_id !== undefined ? ref.map_id : ref.map_key;
    const k = (kRaw === null || kRaw === undefined) ? '' : String(kRaw).trim();
    if (k === '') return clear();
    const table = (t === null || t === undefined) ? '' : String(t).trim();
    out.valid_die_ref = (table === '') ? k : { table, map_id: k };
    return out;
  }
  // 우리가 만들지 않은 형태는 만들지 않는다 — 해제로 읽는 편이 조용히 저장하는 것보다 낫다.
  return clear();
}

// Push가 선언에 대해 무엇을 하는가 — **이 함수 하나가 정한다.**
//   { keep: true }               — 화면이 저장된 원문을 그대로 되비춘다 → 원문을 손대지 않는다
//   { keep: false, ref: ... }    — 사용자가 실제로 바꿨다 → `applyValidDieRef`가 쓴다
//
// 🔴 `keep`이 있는 이유: `{target_table, map_key}` 별칭이나 숫자 `5` 같은 **우리가 저작하지
//    않은 형태**를, 사용자가 손대지도 않았는데 저장 한 번으로 고쳐 쓰지 않기 위해서다.
//    읽지 못한 선언을 조용히 문자열로 바꾸면 사용자는 자기 오타가 무엇이었는지 볼 수 없다.
//    (선언 없는 맵은 `keep` + raw 부재 = 페이로드가 `2a9f6c4`와 바이트 단위로 같다.)
// 🔴 모듈 상태가 아니라 **컨트롤을 읽는** 이유: `change`는 blur에서 나고 그 처리는 비동기다.
//    상태만 읽으면 "입력하고 곧장 Push"가 직전 값을 저장한다.
// 화면 컨트롤이 **뜻하는** 지정. 읽는 곳이 셋(Push 결정 · APPLY · SAVE)이므로 같은 수를
// 세 곳에서 만들지 않기 위해 여기 하나로 모은다.
//
// [1-a] 테이블은 이제 **고르는 것이 아니라 정해진 것**이다. 그래도 무조건
//       `VALID_DIE_TABLE`을 돌려주면 안 된다 — 그러면 이 규칙 이전에 다른 테이블로 저작된
//       선언이, 사용자가 아무것도 건드리지 않은 저장 한 번에 `valid_die_ref` 쪽으로
//       **조용히 옮겨진다**(그 테이블에 같은 키가 있으면 다른 맵이 근거가 되고 화면은
//       정상으로 보인다 — `valid_die_push_decision_cases`가 기록한 그 결함 그대로다).
//       그래서 판정은 하나다: **키를 건드렸는가.**
//         · 키가 저장된 원문의 표시와 같다  → 사용자는 이 선언을 손대지 않았다.
//           테이블도 원문이 말하는 그대로 둔다 → 아래에서 `keep`이 되어 원문이 보존된다.
//         · 키가 다르다(새로 골랐거나 타이핑했다) → 그것은 **새 지정**이고, 새 지정의
//           테이블은 언제나 `VALID_DIE_TABLE`이다.
function validDieRefFromControls() {
  const shown = validDieRefDisplay(validDie ? validDie.raw : undefined);
  const key = (el.validDieRefKey && el.validDieRefKey.value ? el.validDieRefKey.value : '').trim();
  const table = (key === shown.key) ? shown.table : VALID_DIE_TABLE;
  return { shown, table, key };
}

function validDieRefForPush() {
  const raw = validDie ? validDie.raw : undefined;
  const { shown, table: curTable, key: curKey } = validDieRefFromControls();
  // [F2] 선언은 **있는데** 표시가 비었다 — `""`·`null`·빈 키 객체. 컨트롤이 변하지 않으니
  //      비교로는 `keep`이 되고, 그러면 `""`가 그대로 다시 저장돼 그 맵은 파서 규칙상
  //      영구히 `refused`가 된다. 이 UI가 바로 그것을 되돌리는 유일한 길이므로,
  //      "표시할 수 없는 선언"은 여기서 **해제**로 읽어 Push가 키를 정규화해 빼내게 한다.
  //      (입력칸에 무엇이든 쳤다면 그것이 지정이므로 아래 일반 경로가 처리한다.)
  if (raw !== undefined && shown.key === '' && curKey === '') return { keep: false, ref: null };
  if (curTable === shown.table && curKey === shown.key) return { keep: true };
  if (curKey === '') return { keep: false, ref: null };                   // 해제
  // [1-a] 문자열 승계형. `validDieRefFromControls`가 테이블을 고정한 뒤로 **UI에서는 이 가지에
  //       닿지 않는다**(빈 테이블은 「손대지 않음」과 같은 뜻이라 바로 위 `keep`이 먼저 잡는다).
  //       그래도 지우지 않는다: 이 함수는 순수 함수로 따로 채점되고, 승계형은 저장 포맷에
  //       여전히 유효한 형태다(`parseValidDieRef`가 읽는다). 없애면 형태 하나가 채점되지 않는다.
  if (curTable === '') return { keep: false, ref: curKey };               // 테이블 승계(문자열)
  return { keep: false, ref: { table: curTable, map_id: curKey } };
}

// 결정 → **실제로 저장되는 페이로드**. Push 지점(`pushMapData`)이 이 함수만 부른다.
//
// 🔴 여기 있는 이유: 이 두 줄이 DOM에 묶인 함수 안에 살면 채점기가 **같은 두 줄을 다시
//    타이핑**해야 하고, 그 사본은 불변식이 금지하는 구현에도 통과한다(오늘 아침
//    `transfer_log_is_declared_none` 추출과 같은 이유). 축을 테스트 가능하게 만드는 것은
//    테스트가 아니라 추출이다.
// 🔴 `keep` + raw 부재는 `gridMeta`를 **그대로** 돌려준다 — 복사본이 아니다. 여기서 사본을
//    만들면 선언 없는 맵의 페이로드가 `2a9f6c4`와 바이트 단위로 같다는 INV-1의 근거가
//    "같은 키를 같은 순서로 다시 만들었다"로 바뀐다.
// 인자: gridMeta = 컨트롤에서 재구성된 grid_metadata · decision = `validDieRefForPush()`
//       raw = `validDie.raw`(선언 원문, 없으면 undefined)
function validDieRefPayload(gridMeta, decision, raw) {
  if (decision && decision.keep) {
    return (raw !== undefined) ? { ...gridMeta, valid_die_ref: raw } : gridMeta;
  }
  return applyValidDieRef(gridMeta, decision ? decision.ref : null);
}

// [2] 📐 규격만 저장의 **읽고-고쳐-쓴다**의 「고친다」. 순수 함수 — 둘 다 변형하지 않는다.
//
// 인자: stored = 서버에 이미 있는 grid_metadata(없으면 null) · gridMetaOut =
//       `buildPushGridMetadata`가 화면 컨트롤에서 만든 규격(⚡ Push가 보내는 바로 그 객체)
//
// 🔴 **화면이 모르는 키는 살아남는다.** 규격 행은 이 에디터가 모델링하는 것보다 많은 것을
//    실을 수 있고, 아는 필드로 다시 짜 넣으면 모르는 키가 조용히 사라진다. Push는 셀까지
//    통째로 갈아엎으므로 그 파괴가 눈에 띄지만, 규격만 저장은 **화면이 한 픽셀도 움직이지
//    않은 채** 남의 필드를 지운다 — 이 도메인이 존재하는 그 결함이라 병합이 기본값이다.
// 🔴 **`valid_die_ref`만은 부재가 결정이다.** 나머지 키와 달리 이 키가 `gridMetaOut`에
//    없다는 것은 "모른다"가 아니라 **"지운다"**는 뜻이다(`applyValidDieRef`의 해제가
//    `delete`로 표현된다). 단순 spread로 끝내면 저장된 옛 선언이 되살아나서, 방금 해제한
//    지정이 저장 한 번에 부활하고 그 맵은 계속 참조 근거로 그려진다.
function mergeStoredGridMeta(stored, gridMetaOut) {
  const base = (stored && typeof stored === 'object' && !Array.isArray(stored)) ? stored : {};
  const src = (gridMetaOut && typeof gridMetaOut === 'object') ? gridMetaOut : {};
  const out = { ...base, ...src };
  if (!('valid_die_ref' in src)) delete out.valid_die_ref;
  return out;
}

// [INV-6] 참조 체인은 **1홉**이다 — `contracts/map_seam` 역할 `valid_die_chain_error`.
// 서버 `valid_die_chain_error`와 같은 벡터(`valid_die_chain_cases`)로 채점된다.
//
//   자기 참조 A→A  — 그 맵의 저장된 셀이 그 맵의 유효성 기준이 된다. 정의상 항상 참이라
//                    아무 말도 하지 않는 답이면서, 칩에는 **정상 해석**으로 보인다.
//   2단계 A→B(→C)  — B의 저장 셀을 쓰지만 B는 자기 유효 다이가 C의 것이라고 선언했다.
//                    A가 받는 집합은 아무도 선언한 적 없는 집합이다.
// 순환 A→B→A는 별도 규칙이 필요 없다: B가 선언했으므로 A가 거절한다. 방문 집합도, 재귀
// 깊이도 만들지 않는다 — 두 번째 답을 만드는 일이기 때문이다.
//
// 🔴 "선언"의 뜻은 파서와 **같다**: `null`/부재만 부재이고 나머지는 전부 선언이다.
//    `if (refMeta.valid_die_ref)`(falsy 검사)는 `0`·`false`·`''`을 부재로 접어 틀린다.
//    깨진 2단계 선언을 "선언 없음"으로 접는 것도 같은 실수다(INV-5가 금지하는 조용한 폴백).
// 🔴 **정규화를 여기서 하지 않는다.** `ref.mapKey`/`home.mapKey`는 호출자가 이미
//    `canonicalMapKey`를 태운 정준 정체성이다. 여기서 다시 다듬으면 정규화가 둘이 되고,
//    `slot: string`에서 정당한 `LOT_01` 참조가 자기 참조로 오판된다(INV-7).
// 인자: ref = {table, mapKey}(해석·정준화 완료) · refMeta = 참조 맵의 grid_metadata(미상이면 null)
//       home = 선언한 맵의 {table, mapKey}
// 반환: 사유 문자열(위법) | null(적법)
function validDieChainError(ref, refMeta, home) {
  const r = ref || {};
  const h = home || {};
  if (r.table !== undefined && h.table !== undefined
    && String(r.table) === String(h.table) && String(r.mapKey) === String(h.mapKey)) {
    return `자기 자신(${r.table} · ${r.mapKey})을 유효 다이 맵으로 지정했습니다 — `
      + `맵이 자기 셀로 자기 유효성을 정하면 항상 참이라 아무것도 판정하지 못합니다. `
      + `다른 맵을 지정하거나 지정을 비우십시오.`;
  }
  // 규격을 모르는 것은 체인 문제가 아니다 — 그 실패는 상류(align_unavailable)가 이미 말한다.
  if (!refMeta || typeof refMeta !== 'object') return null;
  if (!('valid_die_ref' in refMeta)) return null;
  const inner = refMeta.valid_die_ref;
  if (inner === null || inner === undefined) return null;
  const shown = validDieRefDisplay(inner);
  return `참조 맵(${r.table} · ${r.mapKey})이 스스로 또 다른 유효 다이 맵`
    + `(${shown.table || r.table} · ${shown.key})을 참조합니다 — 참조 체인은 1단계까지만 `
    + `허용합니다. 유효 다이 맵 자신은 valid_die_ref를 갖지 않아야 합니다.`;
}

function applyPhysicalGeometry() {
  const waferDia = el.physWaferDia ? parseFloat(el.physWaferDia.value) : 300;
  const edgeMargin = el.physEdgeMargin ? parseFloat(el.physEdgeMargin.value) : 3.0;
  const effectiveRadius = Math.max(0, (waferDia / 2.0) - edgeMargin);

  const chipX = el.physChipX ? parseFloat(el.physChipX.value) : 2.5;
  const chipY = el.physChipY ? parseFloat(el.physChipY.value) : 2.5;

  if (chipX <= 0 || chipY <= 0 || effectiveRadius <= 0) return;

  let cols = Math.ceil((2.0 * effectiveRadius) / chipX) + 2;
  let rows = Math.ceil((2.0 * effectiveRadius) / chipY) + 2;

  if (cols % 2 === 0) cols += 1;
  if (rows % 2 === 0) rows += 1;

  // [H5] 상한은 `frameDimBounds()` 하나에서 온다 — 채택 경로(`frameDimError`)가 쓰는 그 정의다.
  // 하한 5는 다른 것이다(파생 치수의 최소값이고, 참조 맵이 선언한 작은 치수는 정직하게 받는다).
  const dimMax = frameDimBounds().max;
  cols = Math.max(5, Math.min(dimMax, cols));
  rows = Math.max(5, Math.min(dimMax, rows));

  if (el.gridCols) el.gridCols.value = cols;
  if (el.gridRows) el.gridRows.value = rows;

  // [규칙 ④] 파생 치수가 **자리를 잡은 뒤에** 셀을 자기 저장 좌표에서 다시 앉힌다. 순서가
  // 전부다: 옛 치수로 앉히면 렌더가 새 치수로 좌표를 되만들어 저장 좌표가 조용히 옮겨간다.
  // 렌더보다도 앞이어야 한다 — 렌더가 기록을 갱신하므로, 그 뒤에 물으면 비교할 옛 좌표계가
  // 남아 있지 않다.
  //
  // 🔴 기록은 **여기서 읽는다.** 호출자(`applyPresetObject`)가 미리 잡아 두면 안 된다
  //    (§reseatCellsToStoredCoords의 마지막 ⚠️).
  reseatCellsToStoredCoords(cellsSeatedUnder);

  renderGridCanvas();
}

// ----------------------------------------------------
// Value Counts & Preset Functions
// ----------------------------------------------------
let serverPresets = {};

// [M4②] 저작 진입점이 규격 프리셋 목록에 얹히므로, 두 종류의 항목이 한 select에 산다.
// 접두사가 그 둘을 가른다 — 프리셋 키에 이 접두사를 쓰지 않는 한 충돌하지 않는다.
const VALID_DIE_TEMPLATE_PREFIX = 'valid-die-template:';
const VALID_DIE_TEMPLATE_OPTIONS = [
  ['circle', '원 기하로 채우기 (현재 규격)'],
  ['rect', '격자 전체(사각)로 채우기'],
  ['open', '채우지 않고 격자 전체 열기 (기존 템플릿 편집)'],
];
// 지정 칸 자동완성이 읽을 맵 규격 행 수. 자동완성은 편의이므로 상한이 곧 목록의 끝이다.
const VALID_DIE_LIST_LIMIT = 500;

function updateOrientationUI() {
  document.querySelectorAll('.btn-rot').forEach(btn => {
    const rotVal = parseInt(btn.dataset.rot, 10);
    if (rotVal === currentRotation) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  document.querySelectorAll('input[name="wafer-side"]').forEach(radio => {
    if (radio.value === currentSide) {
      radio.checked = true;
    } else {
      radio.checked = false;
    }
  });
  updateSideIndicator();
}

async function fetchAndRenderPresets() {
  if (!el.presetSelect) return;
  try {
    const res = await fetch(`${API_BASE}/api/map-presets`);
    if (res.ok) {
      const data = await res.json();
      serverPresets = data.presets || {};
    }
  } catch (err) {
    console.error('[Map Presets] Failed to fetch map presets:', err);
  }
  // [M4②] 렌더는 조회 성공 여부와 **무관하게** 한다. 종전에는 성공 분기 안에 있었는데,
  // 유효 다이 저작 진입점이 이 목록에 사는 지금 그 배치는 "프리셋 API가 죽으면 저작 경로도
  // 사라진다"는 뜻이 된다 — 서버 프리셋이 0건이어도 저작은 클라 기하만으로 가능하다.
  renderPresetDropdown();
}

function renderPresetDropdown() {
  if (!el.presetSelect) return;
  el.presetSelect.innerHTML = '<option value="">-- Select Geometry Preset --</option>';

  const builtins = [];
  const customs = [];

  Object.entries(serverPresets).forEach(([key, p]) => {
    if (p.is_custom) {
      customs.push({ key, ...p });
    } else {
      builtins.push({ key, ...p });
    }
  });

  if (builtins.length > 0) {
    const optGroupBuiltin = document.createElement('optgroup');
    optGroupBuiltin.label = 'Built-in Geometry Presets';
    builtins.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.key;
      opt.textContent = p.name;
      optGroupBuiltin.appendChild(opt);
    });
    el.presetSelect.appendChild(optGroupBuiltin);
  }

  if (customs.length > 0) {
    const optGroupCustom = document.createElement('optgroup');
    optGroupCustom.label = 'Custom Geometry Presets';
    customs.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.key;
      opt.textContent = `⭐ ${p.name}`;
      optGroupCustom.appendChild(opt);
    });
    el.presetSelect.appendChild(optGroupCustom);
  }

  // [M4②] 저작 진입점은 **이 드롭다운**이다 — 새 버튼도 새 패널도 만들지 않는다.
  // 프리셋이 규격의 생성기이듯, 여기 세 줄은 유효 다이 집합의 생성기다("원 기하를
  // 판정자에서 생성기로"의 UI 표현). 선택 하나가 곧 실행이고, 선택 뒤 값은 비워
  // 남는다 — 규격 프리셋과 달리 이것은 **상태가 아니라 동작**이기 때문이다.
  const optGroupTpl = document.createElement('optgroup');
  optGroupTpl.label = '🧩 유효 다이 맵 만들기 (템플릿)';
  VALID_DIE_TEMPLATE_OPTIONS.forEach(([shape, label]) => {
    const opt = document.createElement('option');
    opt.value = `${VALID_DIE_TEMPLATE_PREFIX}${shape}`;
    opt.textContent = label;
    optGroupTpl.appendChild(opt);
  });
  el.presetSelect.appendChild(optGroupTpl);
}

// 프리셋 객체를 물리 규격/방향 UI에 적용 (프리셋 셀렉트와 무관하게 재사용 —
// 영역 선택 모드가 CORE/BASE 프리셋 규격 강제 시에도 동일 경로를 탄다)
function applyPresetObject(preset) {
  if (!preset) return;
  if (preset.phys_wafer_dia !== undefined && el.physWaferDia) {
    const diaStr = String(preset.phys_wafer_dia);
    if (['300', '200', '150'].includes(diaStr)) {
      el.physWaferDia.value = diaStr;
    } else {
      let opt = el.physWaferDia.querySelector(`option[value="${diaStr}"]`);
      if (!opt) {
        opt = document.createElement('option');
        opt.value = diaStr;
        opt.textContent = `${diaStr} mm (Custom)`;
        el.physWaferDia.appendChild(opt);
      }
      el.physWaferDia.value = diaStr;
    }
  }
  if (preset.phys_chip_x !== undefined && el.physChipX) el.physChipX.value = preset.phys_chip_x;
  if (preset.phys_chip_y !== undefined && el.physChipY) el.physChipY.value = preset.phys_chip_y;
  // [D1] 프리셋은 **선언이다** — 사람이 고른 규격이므로 자동 등록 표지를 끈다. 합성 규격을
  //      앉히는 유일한 호출자(`[fix C]`)는 이 호출 **뒤에** 표지를 다시 켠다. 여기서 끄지
  //      않으면 자동 등록 맵에서 프리셋을 고른 순간 표지가 살아남아, 사람이 방금 선언한
  //      피치가 「선언 없음」으로 읽힌다.
  markGeometryAutoRegistered(false);
  if (preset.phys_offset_x !== undefined && el.physOffsetX) el.physOffsetX.value = preset.phys_offset_x;
  if (preset.phys_offset_y !== undefined && el.physOffsetY) el.physOffsetY.value = preset.phys_offset_y;
  if (preset.phys_edge_margin !== undefined && el.physEdgeMargin) el.physEdgeMargin.value = preset.phys_edge_margin;

  // ═══ A GEOMETRY PRESET IS A STATEMENT ABOUT GEOMETRY. ORIENTATION IS THE OPERATOR'S. ═══
  //
  // 🔴 THE DEFECT. These two lines used to read
  //        if (preset.rotation !== undefined) currentRotation = preset.rotation;
  //        if (preset.side !== undefined) currentSide = preset.side;
  //    and every stored preset declares rot 0 / front, so applying ANY preset to a rotated or
  //    back-side map silently reset it. `getDieIndex` reads rotation and side, so the
  //    physical key of every cell changed and with it the coordinate ⚡ Push writes.
  //    Specimen `aa123_a` + preset `4A`: byte-identical physical spec, unchanged grid,
  //    unchanged bounding box, **173 of 187 dies renumbered**, and Push proceeded — the
  //    contrast gate sees only cells that leave the grid or the circle, and none did.
  //    The control with exactly these two lines deleted changed nothing else.
  //
  // 🔴 THE OPERATOR ALREADY OWNS ORIENTATION, through the rotate buttons and the front/back
  //    radios. A preset re-asserting it is the screen moving without consent, which is the one
  //    thing this domain forbids. So it is not moved — not here, and not on any caller's
  //    behalf (`loadSelectedPreset`, `applyRoutedPreset`, the material-frame empty-map open,
  //    and the 표준 branch's no-mask spec all reach this one function).
  //
  // ⚠️ `maps.json` is operator-editable, so a preset CAN still declare an orientation. It is
  //    read and ignored — never silently. Announcing after the fact is legitimate precisely
  //    because nothing changed; it is a report that the screen stayed put, not notice of a
  //    move. Reads stay frictionless: one info toast, no dialog, no new control.
  const declaredRot = (preset.rotation === undefined || preset.rotation === null)
    ? null : (Number(preset.rotation) || 0);
  const declaredSide = (preset.side === 'back' || preset.side === 'front') ? preset.side : null;
  const ignoredRot = (declaredRot !== null && declaredRot !== currentRotation) ? declaredRot : null;
  const ignoredSide = (declaredSide !== null && declaredSide !== currentSide) ? declaredSide : null;
  if (ignoredRot !== null || ignoredSide !== null) {
    const sideWord = (s) => (s === 'back' ? '뒷면' : '앞면');
    const declared = [ignoredRot !== null ? `${ignoredRot}°` : '',
    ignoredSide !== null ? sideWord(ignoredSide) : ''].filter(Boolean).join(' · ');
    console.info(`[Map Editor] preset '${preset.name || ''}' declares orientation `
      + `(rotation=${declaredRot}, side=${declaredSide}); NOT applied — the screen keeps `
      + `rotation=${currentRotation}, side=${currentSide}. Orientation belongs to the operator's `
      + 'rotate/flip controls, and changing it here renumbers every cell.');
    showToast(`규격만 적용했습니다 — 이 프리셋이 선언한 방향(${declared})은 적용하지 않았습니다. `
      + `회전·면은 화면의 ${currentRotation}° · ${sideWord(currentSide)} 그대로이고, 셀 좌표도 `
      + `그대로입니다.`, 'info', { dedupeKey: 'preset_orientation_ignored' });
  }

  boundingBoxCache = {};
  updateOrientationUI();
  applyPhysicalGeometry();
  scheduleRenderGridCanvas();
  updateLegendCounts();
}

// ── [F5c] 로드 시 기본 규격 라우팅 ─────────────────────────────────────────────
// "이 맵을 **어떤 물리 규격으로 여는가**"의 선언된 답. 순서를 정하는 것은 서버
// (`GET /api/maps/preset-routing`, server-pm `50bddda`)이고 클라는 그 답을 **적용만**
// 한다 — 여기에 두 번째 판정을 쓰면 라우팅 규칙이 두 곳에서 살게 된다.
//
// 🔴 **절대 순서: `wafer_map_metadata` > 라우팅 > 패널.** 서버는 규격이 등록된 맵에
//    `meta_present` + preset null을 답하므로 그것만으로도 안전하지만, 클라는 그보다
//    앞서 **묻지도 않는다**(호출부의 `!loadedGridMeta` 가드). 저장된 규격을 이미 손에
//    쥔 상태에서 조회하면 "그 답을 무시한다"는 규율이 코드 한 줄의 성실함에 걸린다 —
//    조회 자체를 하지 않는 것이 구조적 보증이다(INV-F5c-2).
// 🔴 **`status !== 'ok'`이면 아무것도 적용하지 않는다**(INV-F5c-1). 서버가 프리셋을
//    주지 않은 것을 클라가 그럴듯한 것으로 메우면 안 된다 — 틀린 규격은 `inside`를
//    바꾸고, `inside`는 저장 가능 집합을 바꾼다.
// 🔴 **빗나감은 정상 경로지 경고가 아니다.** 제품코드 조회 테이블은 운영에만 있고
//    불완전하다는 것이 이 설계의 전제다. 미선언·불일치·조회 실패는 토스트를 띄우지
//    않고 `lookup.status`와 함께 콘솔에만 남긴다 — 운영자가 찾아볼 때 보이는 자리다.
// 🔴 **로드당 1회**(INV-F5c-3). 렌더당도, 셀당도 아니다. 호출부는 `loadExistingMap`
//    안의 한 곳뿐이다.
// 라우팅은 **첫 열기의 기본값**이고 진짜로 만드는 것은 첫 ⚡ Push다 — 그래서 끄는
// 스위치를 만들지 않았다(순 추가 컨트롤 0개). 사용자는 Push 전에 무엇이든 바꿀 수 있다.
//
// 반환: 적용한 경우 응답 객체, 그 외 null. (호출부는 성공/실패로 분기하지 않는다.)
async function applyRoutedPreset(table, mapKey) {
  const t = String(table || '').trim();
  const k = (mapKey === null || mapKey === undefined) ? '' : String(mapKey).trim();
  if (t === '' || k === '') return null;   // 물어볼 정체성이 없다 — 요청도 만들지 않는다
  let resp = null;
  try {
    const res = await fetch(`${API_BASE}/api/maps/preset-routing`
      + `?table=${encodeURIComponent(t)}&map_key=${encodeURIComponent(k)}`);
    if (!res.ok) {
      // 조회 실패는 "선언이 없다"가 아니라 "확인 못 했다"이지만, 라우팅의 부재는 기존
      // 동작(패널 그대로)과 같으므로 강등할 것이 없다. 조용히 콘솔에만 남긴다.
      console.info(`[Map Editor][F5c] preset routing unavailable (HTTP ${res.status}) — `
        + 'opening with the panel spec, as before');
      return null;
    }
    resp = await res.json();
  } catch (e) {
    console.info('[Map Editor][F5c] preset routing request failed — opening with the panel spec, '
      + `as before (${e && e.message ? e.message : String(e)})`);
    return null;
  }
  const status = resp && resp.status ? String(resp.status) : '';
  const lookup = (resp && resp.lookup) ? resp.lookup : {};
  if (status !== 'ok' || !resp.preset) {
    console.info(`[Map Editor][F5c] no routing applied (${status || 'no status'}) — `
      + `${resp && resp.detail ? resp.detail : ''} `
      + `[lookup declared=${!!lookup.declared} status=${lookup.status || '-'} `
      + `product_code=${lookup.product_code || '-'}]`);
    return null;
  }
  // 적용한다 = 화면이 바뀐다. 바뀌는 것은 조용히 넘어가지 않는다.
  applyPresetObject(resp.preset);
  const m = resp.matched_by || {};
  console.info(`[Map Editor][F5c] routed '${t}/${resp.canonical_map_key || k}' -> preset `
    + `'${resp.preset_key}' by ${m.stage || '?'}:${m.rule || '?'} (lot=${m.lot || '-'}, `
    + `product_code=${m.product_code || '-'}) [lookup status=${lookup.status || '-'}]`);
  showToast(`규격을 라우팅했습니다 — '${(resp.preset && resp.preset.name) || resp.preset_key}' `
    + `(규칙: ${m.rule || resp.preset_key}). 저장된 규격이 없는 맵의 기본값이며, `
    + `⚡ Push 전에 자유롭게 바꿀 수 있습니다.`, 'info', { dedupeKey: 'preset_routing_applied' });
  return resp;
}

function loadSelectedPreset() {
  if (!el.presetSelect) return;
  const val = el.presetSelect.value;
  if (!val) {
    if (el.btnDeletePreset) el.btnDeletePreset.style.display = 'none';
    return;
  }
  // [M4②] 저작 항목은 규격을 적용하지 않는다 — 선택 즉시 실행하고 select를 비운다.
  if (val.startsWith(VALID_DIE_TEMPLATE_PREFIX)) {
    const shape = val.slice(VALID_DIE_TEMPLATE_PREFIX.length);
    el.presetSelect.value = '';
    if (el.btnDeletePreset) el.btnDeletePreset.style.display = 'none';
    enterValidDieAuthoring(shape);
    return;
  }

  const preset = serverPresets[val];
  if (preset) {
    applyPresetObject(preset);
    if (el.btnDeletePreset) {
      el.btnDeletePreset.style.display = preset.is_custom ? 'inline-block' : 'none';
    }
  }
}

async function saveCustomPreset() {
  const presetName = prompt('Enter custom geometry preset name:', `Geometry Preset ${new Date().toLocaleDateString()}`);
  if (!presetName) return;

  let diaVal = 300;
  if (el.physWaferDia) {
    if (el.physWaferDia.value === 'custom') {
      diaVal = parseFloat(prompt('Enter custom wafer diameter (mm):', '300')) || 300;
    } else {
      diaVal = parseFloat(el.physWaferDia.value) || 300;
    }
  }

  const payload = {
    name: presetName,
    phys_wafer_dia: diaVal,
    phys_chip_x: el.physChipX ? (parseFloat(el.physChipX.value) || 2.5) : 2.5,
    phys_chip_y: el.physChipY ? (parseFloat(el.physChipY.value) || 2.5) : 2.5,
    phys_offset_x: el.physOffsetX ? (parseFloat(el.physOffsetX.value) || 0.0) : 0.0,
    phys_offset_y: el.physOffsetY ? (parseFloat(el.physOffsetY.value) || 0.0) : 0.0,
    phys_edge_margin: el.physEdgeMargin ? (parseFloat(el.physEdgeMargin.value) || 3.0) : 3.0,
    rotation: currentRotation,
    side: currentSide
  };

  try {
    const res = await fetch(`${API_BASE}/api/map-presets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const data = await res.json();
      await fetchAndRenderPresets();
      if (el.presetSelect && data.preset_key) {
        el.presetSelect.value = data.preset_key;
        loadSelectedPreset();
      }
      // [1e] Success confirmation. The dropdown is re-rendered with the just-saved preset
      // selected, so the result is on screen; failure still speaks via the alert below.
      console.debug(`[map] preset saved: ${presetName} (${data.preset_key})`);
    } else {
      const errorData = await res.json().catch(() => ({ detail: res.statusText }));
      alert(`프리셋 저장 실패 — ${errorData.detail || res.statusText}`);
    }
  } catch (err) {
    console.error('[Map Presets] Error saving preset:', err);
    alert(`프리셋 저장 실패 — ${err.message}`);
  }
}

async function deleteCustomPreset() {
  if (!el.presetSelect) return;
  const val = el.presetSelect.value;
  if (!val) return;

  const preset = serverPresets[val];
  if (!preset || !preset.is_custom) return;

  if (!confirm(`프리셋 '${preset.name}'을(를) 서버에서 삭제합니다. 계속하시겠습니까?`)) return;

  try {
    const res = await fetch(`${API_BASE}/api/map-presets/${val}`, {
      method: 'DELETE'
    });

    if (res.ok) {
      await fetchAndRenderPresets();
      el.presetSelect.value = '';
      if (el.btnDeletePreset) el.btnDeletePreset.style.display = 'none';
      // [1e] Success confirmation. Disappearing from the list IS the result.
      console.debug(`[map] preset deleted: ${preset.name} (${val})`);
    } else {
      const errorData = await res.json().catch(() => ({ detail: res.statusText }));
      alert(`프리셋 삭제 실패 — ${errorData.detail || res.statusText}`);
    }
  } catch (err) {
    console.error('[Map Presets] Error deleting preset:', err);
    alert(`프리셋 삭제 실패 — ${err.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// [F2] 저장될 셀의 **유일한 정의**. 화면 수량과 저장 수량이 갈리던 자리가 여기다.
//
// 🔴 THE DEFECT. `computeLegendCounts` walked `gridData` — a flat physical-key map that
//    knows nothing about `inside`. `🎨 Fill All` painted the whole rectangle, so on a
//    circle-based map ~21%의 셀이 원 밖에 칠해졌고 화면 수량이 그것까지 셌다. 그 셀들은
//    ① 캔버스에 색이 나오지도 않고(`cellFillColor`가 `!inside`면 outBg를 돌려준다)
//    ② `pushMapData`가 직렬화하지도 않는다. 즉 **보이지도 않고 저장되지도 않는 셀이
//    DOE 산술의 입력이 되고 있었다.**
//
// 🔴 그래서 술어는 하나다: `pushMapData`가 `updates`를 만드는 그 순회를 여기로 옮기고
//    Push·범례 뱃지·DOE 패널·COPY HEADER MODE의 COUNT가 **모두 이 함수를 통과한다**.
//    두 곳에서 각자 세면 저장이 `ceil`, 표시가 `round`였던 그 계급이 다시 생긴다.
//
// ⚠️ `gridCells2D`가 정의역이라는 것이 규칙의 일부다. 렌더가 만들지 않은 셀은 Push도
//    직렬화하지 않으므로(그 상태는 대비 관문이 잡는다), 세지 않는 것이 정확하다.
//    빈 값 판정은 Push가 쓰던 식(`(v || '') !== ''`)을 **글자 그대로** 옮겼다 — 여기서
//    표현을 "개선"하면 그 개선분만큼 화면과 저장이 갈린다.
// ═══════════════════════════════════════════════════════════════════════════════
function eachSavableCell(fn) {
  if (!gridCells2D) return;
  Object.keys(gridCells2D).forEach(rStr => {
    const r = parseInt(rStr, 10);
    if (!gridCells2D[r]) return;
    Object.keys(gridCells2D[r]).forEach(cStr => {
      const c = parseInt(cStr, 10);
      const cellObj = gridCells2D[r][c];
      if (!cellObj || !cellObj.inside) return;   // Skip blocked outside-wafer cells
      const val = gridData[cellObj.key] || '';
      if (val === '') return;                    // replace_map cleans the map: empty carries nothing
      fn(cellObj, val);
    });
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// [F2b] 저장되지 않는 셀의 **분류**. `eachSavableCell`의 여집합이고, 두 모집단은 좌표만으로
// 정확히 갈린다:
//
//   격자 밖 — 그 키에 cellObj 자체가 없다. 현재 프레임이 맵을 덮지 못한다는 뜻이고
//             `replace_map`이 그 행들을 지운다. **진짜 절단 방어**(H2)이므로 거부는 그대로다.
//   원  밖 — cellObj는 있는데 `inside`가 거짓이다. 그리지도 세지도 저장하지도 않는 셀이다.
//             프레임을 아무리 맞춰도 사라지지 않으므로 "격자 크기를 맞추라"는 안내는
//             **작동할 수 없다** — 그래서 자기 문장이 필요하다.
//
// 🔴 원 밖은 다시 둘로 갈린다. 출처를 모르면(`serverCellKeySet() === null`) 전부 남긴다 —
//    서버 상태를 모르면 지우지 않는다(불변식 ③). 정리 가능한 것은 **서버가 보낸 적 없음이
//    증명된** 키뿐이다.
//
// ⚠️ 판정은 새로 만들지 않는다. 정의역(`gridCells2D`)·`inside`·빈 값 식은 `eachSavableCell`이
//    쓰는 그것과 글자 그대로 같고, 세 수의 합 + 저장 대상 수 == `nonEmptyOnGrid`가 항등이다.
// ═══════════════════════════════════════════════════════════════════════════════
function classifyUnsavableCells() {
  const insideByKey = new Map();
  Object.keys(gridCells2D || {}).forEach(rStr => {
    Object.keys(gridCells2D[rStr] || {}).forEach(cStr => {
      const co = gridCells2D[rStr][cStr];
      if (co) insideByKey.set(co.key, !!co.inside);
    });
  });
  const known = serverCellKeySet();
  const offGrid = [], outsideRetained = [], outsideStray = [];
  Object.keys(gridData).forEach(k => {
    if ((gridData[k] || '') === '') return;    // eachSavableCell과 같은 빈 값 식
    const inside = insideByKey.get(k);
    if (inside === undefined) { offGrid.push(k); return; }
    if (inside) return;                        // 저장 대상 — eachSavableCell이 가져간다
    if (known && !known.has(k)) outsideStray.push(k);
    else outsideRetained.push(k);
  });
  return { offGrid, outsideRetained, outsideStray };
}

// 🔴 [MEDIUM-1] "이만큼이면 ⚡ Push가 거절한다"의 **정의는 여기 하나뿐이다.**
//
// `pushMapData`는 `offGrid + outsideRetained`로 거절을 판정하는데, 종전에는 채택 안내가
// 거기에 `outsideStray`까지 더한 수를 세어 놓고 **같은 문장**("이 상태로는 저장할 수 없어
// Push가 거절합니다")을 말했다. 실측: 토스트가 4, Push 알림이 2 — 같은 격자에 대해 두 수.
// 게다가 stray는 거절이 아니라 **정리 제안**이라는 다른 대화상자로 가므로, 큰 수를 보고
// 겁먹은 사용자가 Push를 눌러 보면 다른 수와 다른 안내가 나온다.
// 세 모집단을 합치는 식이 둘이면 반드시 갈린다 — 그래서 이름을 붙여 한 곳에 둔다.
//
// ⚠️ 지금 소비자는 `pushMapData` **하나뿐**이다(두 번째였던 채택 안내는 F8에서 사라졌다).
//    그래도 이름을 지우지 않는다 — 갈릴 수 있다는 사실이 사라진 것이 아니라 두 번째 소비자가
//    사라진 것뿐이고, 다음에 세는 곳이 생기면 그 곳이 이 함수를 부르면 된다.
function pushBlockingCount(u) {
  return u.offGrid.length + u.outsideRetained.length;
}

// 격자의 value별 셀 수. legend에 없는 값도 세어 "정의되지 않은 value"를 드러낸다.
function computeLegendCounts() {
  const counts = {};
  legend.forEach(item => { counts[item.value] = 0; });
  eachSavableCell((cellObj, val) => { counts[val] = (counts[val] || 0) + 1; });
  return counts;
}

function updateLegendCounts() {
  const counts = computeLegendCounts();

  legend.forEach(item => {
    const badge = document.getElementById(`legend-count-${item.value}`);
    if (badge) {
      const qty = counts[item.value] || 0;
      badge.textContent = qty;
      badge.style.color = qty > 0 ? 'var(--color-primary)' : 'var(--text-dim)';
    }
  });

  // [재설계 v2] DOE 패널의 "칠함" 수치 동기화.
  // 전체 재렌더가 아니라 숫자 텍스트만 패치한다(수만 셀 조작 중에도 프리징 금지).
  notifyPaintCounts(counts);
}

// ----------------------------------------------------
// Rendering Functions
// ----------------------------------------------------

// ── 캔버스 테마 색 캐시 ─────────────────────────────────────
// 성능 규율: 렌더 루프(수만 셀)에서 getComputedStyle 호출 금지.
// 최초 1회 캐싱 후, 테마 전환(themechange) 시에만 재캐싱한다 (tokens.css --canvas-* 토큰).
let themeColors = null;

function rebuildThemeColorCache() {
  const cs = getComputedStyle(document.documentElement);
  const v = (name, fallback) => (cs.getPropertyValue(name) || '').trim() || fallback;
  themeColors = {
    outBg: v('--canvas-out-bg', '#e2e6ec'),               // 매트릭스/웨이퍼 밖 셀 배경
    line: v('--canvas-line', 'rgba(31, 39, 51, 0.10)'),   // 기본 격자선
    lineStrong: v('--canvas-line-strong', 'rgba(31, 39, 51, 0.16)'), // 원 내부 격자선
    insideEmpty: v('--canvas-inside-empty', 'rgba(23, 114, 69, 0.06)'), // 원 내부 빈 셀 채움
    textEmpty: v('--canvas-text-empty', 'rgba(71, 83, 107, 0.8)'),   // 좌표 표기(원 내부)
    textOut: v('--canvas-text-out', 'rgba(91, 103, 121, 0.45)'),     // 좌표 표기(원 외부)
    waferEdge: v('--canvas-wafer-edge', 'rgba(31, 39, 51, 0.7)'),    // 웨이퍼 외곽 원
    wmFront: v('--canvas-wm-front', 'rgba(26, 102, 208, 0.09)'),     // FRONT 워터마크
    wmBack: v('--canvas-wm-back', 'rgba(138, 90, 0, 0.09)'),         // BACK 워터마크
    accent: v('--accent', '#1a66d0'),
    success: v('--success', '#177245'),
    warning: v('--warning', '#8a5a00'),
    danger: v('--danger', '#c22f2f'),
    // 캔버스 전용 반투명 토큰. 범용 `--danger-weak`는 라이트에서 #fdecec(불투명)이라
    // erase 프리뷰(:2522)와 원점 하이라이트(:2425)가 맵을 흰 박스로 덮었다 — 다크에서만
    // 반투명이라 여태 안 잡혔다. CSS 배경 16곳이 쓰는 범용 토큰은 건드리지 않는다.
    dangerWeak: v('--canvas-danger-fill', 'rgba(194, 47, 47, 0.15)'),
    rangeFill: v('--range-fill', 'rgba(26, 102, 208, 0.14)'),
    surface: v('--bg-surface', '#ffffff'),
  };
}

function getThemeColors() {
  if (!themeColors) rebuildThemeColorCache();
  return themeColors;
}

// 범례에 없는 값으로 칠해진 셀의 색. 페인팅은 범례에 없는 값도 받아들이므로(붙여넣기·자동
// 페인팅·개명 잔여) 이 경우는 실제로 생긴다.
const UNLISTED_VALUE_FILL = '#10b981';

// 🔴 셀 채움색의 **유일한 판정**. 캔버스와 엑셀 내보내기가 같은 함수를 부른다.
//    갈라져 있던 동안 화면은 UNLISTED_VALUE_FILL로 칠하고 내보내기는 "빈 셀" 색을 써서,
//    엑셀 파일이 조용히 다른 내용을 담았다 (INV-1c-3). "보이는 대로"가 요구사항이다.
function cellFillColor(val, inside, colorMap, C) {
  if (!inside) return C.outBg;
  if (val !== '') return colorMap[val] || UNLISTED_VALUE_FILL;
  return C.insideEmpty;
}

// ── CSS 색 → 엑셀이 읽는 #rrggbb ────────────────────────────────────────────
// 테마 토큰의 상당수가 `rgba(...)`다. CF_HTML 경로는 rgba를 이해하지 못해 그 셀이 **하얗게**
// 나가므로, 알파를 배경색 위에 합성해 불투명 hex로 눌러 준다.
function parseCssColor(c) {
  const s = String(c === null || c === undefined ? '' : c).trim();
  let m = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(s);
  if (m) return { r: parseInt(m[1] + m[1], 16), g: parseInt(m[2] + m[2], 16), b: parseInt(m[3] + m[3], 16), a: 1 };
  m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(s);
  if (m) return { r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16), a: 1 };
  m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[,/]\s*([\d.]+))?\s*\)$/i.exec(s);
  if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  return null;
}

function toExcelHex(color, backdrop, fallback) {
  const c = parseCssColor(color);
  if (!c) return fallback;
  const bg = parseCssColor(backdrop) || { r: 255, g: 255, b: 255, a: 1 };
  const a = Math.max(0, Math.min(1, c.a));
  const mix = (x, y) => Math.max(0, Math.min(255, Math.round(x * a + y * (1 - a))));
  const h = n => n.toString(16).padStart(2, '0');
  return `#${h(mix(c.r, bg.r))}${h(mix(c.g, bg.g))}${h(mix(c.b, bg.b))}`;
}

// 테마 전환 시: 색 캐시 재빌드 + 캔버스 1회 재렌더 (theme.js 'themechange' 구독)
document.addEventListener('themechange', () => {
  rebuildThemeColorCache();
  scheduleRenderGridCanvas();
});

let isRenderScheduled = false;

function scheduleRenderGridCanvas() {
  if (isRenderScheduled) return;
  isRenderScheduled = true;
  requestAnimationFrame(() => {
    isRenderScheduled = false;
    renderGridCanvas();
  });
}

// Update the FRONT/BACK indicator chip (DOM, outside the grid). Cheap; call directly
// on every side change so the label is instant even if the canvas re-render is throttled.
function updateSideIndicator() {
  if (!el.sideIndicator) return;
  const isBack = (currentSide === 'back');
  el.sideIndicator.textContent = isBack ? 'BACK · 뒷면' : 'FRONT · 앞면';
  el.sideIndicator.classList.toggle('side-back', isBack);
  el.sideIndicator.classList.toggle('side-front', !isBack);
}

// Size the (square) grid wrapper to fill the available workspace, then re-render.
// Square-fit avoids distorting the circular wafer; min(availW,availH) never overflows,
// so it won't fight the workspace scrollbars (no ResizeObserver feedback loop).
function fitGridToWorkspace() {
  const ws = el.mapWorkspace;
  const wrapper = el.gridWrapper;
  if (!ws || !wrapper) { scheduleRenderGridCanvas(); return; }
  const cs = getComputedStyle(ws);
  const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
  const padY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
  const availW = ws.clientWidth - padX;
  const availH = ws.clientHeight - padY;
  const side = Math.max(200, Math.floor(Math.min(availW, availH)));
  wrapper.style.width = `${side}px`;
  wrapper.style.height = `${side}px`;
  scheduleRenderGridCanvas();
}

function renderGridCanvas() {
  if (!el.waferCanvas || !el.gridCanvas) return;

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert.checked;

  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // 🔴 **(0,0)이 어느 칸인가는 좌표 함수의 역함수가 답한다.** 종전에는 이 자리가 그 유도를
  //    손으로 다시 썼고, 그 사본에는 `getDbCoords`에 **없는** x/y 미러 항이 있었다
  //    (`isXMirrored`/`isYMirrored`). 원 bbox가 대칭인 동안만 우연히 같은 답이 나왔고,
  //    마우스 경로(`getGridCellObject`)는 이미 미러 항 없이 계산하고 있어 두 경로가 실제로
  //    갈려 있었다. 원점 상자가 유효 다이 기준이 되면 그 우연은 성립하지 않는다.
  const zero = getCanvasCellFromDb(null, 0, 0, cols, rows, currentRotation, currentSide, invertY, startX, startY);
  const hasZeroZero = (zero.c >= 0 && zero.c < visualCols) && (zero.r >= 0 && zero.r < visualRows);

  // 지금 그리는 이 좌표계가 곧 "셀이 앉은 자리"다(§cellsSeatedUnder). 여기 한 줄이 기록의
  // 유지를 **잊을 수 없게** 만든다: 회전이든 로드든 프레임 복귀든, 좌표계를 바꾸는 모든 경로는
  // 렌더로 끝나므로 다음 기하 편집은 언제나 직전 화면과 대조된다. 상자는 바로 윗줄이 이미
  // 물어 캐시에 얹어 둔 그 상자라 추가 순회가 없다.
  cellsSeatedUnder = seatingSnapshot(null) || cellsSeatedUnder;

  gridCells2D = {};

  const rect = el.gridCanvas.getBoundingClientRect();
  const width = Math.floor(rect.width || 700);
  const height = Math.floor(rect.height || 700);

  if (width <= 0 || height <= 0) return;

  const dpr = window.devicePixelRatio || 1;
  el.waferCanvas.width = width * dpr;
  el.waferCanvas.height = height * dpr;

  // 규격이 바뀌었으면 오버레이 좌표를 먼저 재계산 (어긋난 위치 표시 방지)
  syncOverlayGeometry();

  const ctx = el.waferCanvas.getContext('2d');
  ctx.save();
  ctx.scale(dpr, dpr);

  ctx.clearRect(0, 0, width, height);

  // 테마 색 캐시 (렌더 루프 내 getComputedStyle 금지 — 캐시만 참조)
  const C = getThemeColors();

  const tStart = performance.now();

  const physConfig = getTransformedPhysicalConfig(null, currentRotation, currentSide);

  // [C1] 셀 픽셀 크기의 **유일한 계산**. 마우스 경로(`getGridCellFromMouseEvent`)가 같은
  //      함수를 부른다 — 같은 수를 두 곳에서 계산하면 반드시 갈라진다.
  const { cellW, cellH, padX, padY, isotropic, waferAnchored } = cellMetrics(width, height, visualCols, visualRows, physConfig);
  const showAnno = el.showAnnotations ? el.showAnnotations.checked : true;

  const colorMap = {};
  legend.forEach(item => {
    colorMap[item.value] = item.color;
  });

  const fontPx = Math.max(8, Math.min(13, Math.floor(cellH * 0.45)));
  ctx.font = `bold ${fontPx}px "JetBrains Mono", monospace`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  const { shiftX, shiftY } = getScreenShift(physConfig, cellW, cellH);

  // 격자 (0,0)의 화면 원점. `padX/padY`가 격자를 캔버스 중앙에 앉힌다(§cellMetrics).
  const originX = shiftX + padX;
  const originY = shiftY + padY;

  const startC = Math.min(-visualCols, Math.floor(-originX / cellW) - 2);
  const endC = Math.max(2 * visualCols, Math.ceil((width - originX) / cellW) + 2);
  const startR = Math.min(-visualRows, Math.floor(-originY / cellH) - 2);
  const endR = Math.max(2 * visualRows, Math.ceil((height - originY) / cellH) + 2);

  for (let r = startR; r <= endR; r++) {
    for (let c = startC; c <= endC; c++) {
      const x0 = c * cellW + originX;
      const y0 = r * cellH + originY;

      if (x0 + cellW < 0 || x0 > width || y0 + cellH < 0 || y0 > height) continue;

      // ═══ 격자 밖 — **맵이 아니다.** ═══════════════════════════════════════════
      // `grid_cols`/`grid_rows`는 선언된 규격이다. 그 밖의 칸은 맵이 선언하지 않은 좌표이므로
      // 존재하지도, 쓰이지도, 세어지지도 않아야 한다. 여기서 `continue`하는 한 줄이 그 셋을
      // 전부 보장한다 — `gridCells2D`에 들어가지 않으면 `eachSavableCell`(범례 수량 · DOE
      // 수량 · ⚡Push 직렬화 · 엑셀)의 정의역 밖이고, 마우스·박스드래그·좌표표 붙여넣기·
      // 오버레이 가져오기가 전부 `gridCells2D`를 거쳐 쓰기 때문이다.
      //
      // 🔴 종전에는 이 칸들이 `isMatrixCell`(밴드 −visualCols..2·visualCols)로 통과해
      //    셀 객체를 받았다. 실측: 15x11 격자에서 56칸, 9x7 격자(원이 격자를 넘는 규격)에서
      //    36칸이 등록됐고 그중 36칸이 `inside`였다 — 즉 **칠하면 저장되고 세어졌다.**
      //    이 라운드가 여백을 만들면 그 인구가 커지므로 여기서 닫는다.
      // 🔴 경계에서 추측하지 않는다: 선언된 격자 안이라고 **말할 수 없으면** 밖이다.
      //
      // ⚠️ 눈에도 달라야 한다. 「맵 밖」과 「맵 안인데 값이 없음」은 다른 사실이다.
      //    격자 밖은 **채움 없이 격자선만** 잇는다(선언된 칸은 언제나 채움이 있다 —
      //    범례색 · `insideEmpty` · `outBg`). 여기에 아래 ⑥의 격자 외곽선이 더해진다.
      const onGrid = (c >= 0 && c < visualCols && r >= 0 && r < visualRows);
      if (!onGrid) {
        ctx.strokeStyle = C.line;
        ctx.lineWidth = 0.5;
        ctx.strokeRect(x0, y0, cellW, cellH);
        continue;
      }

      // [M4①] 물리 좌표는 아래에서 어차피 만든다. 판정에 필요하므로 여기로 끌어올렸다 —
      // 판정용 좌표를 따로 만들면 같은 좌표의 계산이 둘이 된다.
      const physical = getDieIndex(null, c, r, cols, rows, currentRotation, currentSide);
      const completelyInside = isValidDieAt(null, physical.x, physical.y,
        isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height));

      const visual = getDbCoords(null, c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
      const coordKey = `${physical.x}_${physical.y}`;
      const val = gridData[coordKey] || '';

      const isOriginCell = hasZeroZero
        ? (visual.x === 0 && visual.y === 0)
        : (visual.x === startX && visual.y === startY);

      const cellObj = {
        c, r, x: visual.x, y: visual.y, px: physical.x, py: physical.y,
        key: coordKey, inside: completelyInside, isOrigin: isOriginCell
      };
      if (!gridCells2D[r]) gridCells2D[r] = {};
      gridCells2D[r][c] = cellObj;

      // 1. Fill cell background
      // 범례 색은 사용자 데이터(테마 불변) — 미등록 값만 기본 범례색 폴백.
      // 판정은 `cellFillColor` 하나뿐이다: 엑셀 내보내기가 같은 함수를 부른다.
      ctx.fillStyle = cellFillColor(val, completelyInside, colorMap, C);
      ctx.fillRect(x0, y0, cellW, cellH);

      // 2. Stroke grid border across ALL cells (inside and outside wafer)
      ctx.strokeStyle = completelyInside ? C.lineStrong : C.line;
      ctx.lineWidth = 0.5;
      ctx.strokeRect(x0, y0, cellW, cellH);

      // 3. Wafer inside boundary cell outline
      if (completelyInside) {
        ctx.strokeStyle = C.success;
        ctx.lineWidth = 1.2;
        ctx.strokeRect(x0 + 0.5, y0 + 0.5, cellW - 1, cellH - 1);
      }

      // 4. Origin cell highlight
      if (isOriginCell) {
        ctx.fillStyle = C.dangerWeak;
        ctx.fillRect(x0, y0, cellW, cellH);
        ctx.strokeStyle = C.danger;
        ctx.lineWidth = 2.0;
        ctx.strokeRect(x0 + 1, y0 + 1, cellW - 2, cellH - 2);
      }

      // 5. Annotations text (Dynamic font size fitting)
      const textToDraw = val !== '' ? String(val) : (showAnno ? `${visual.x},${visual.y}` : '');
      if (textToDraw) {
        const len = textToDraw.length;
        const maxFontW = (cellW * 0.85) / Math.max(1, len * 0.58);
        const maxFontH = cellH * 0.35;
        const fontPx = Math.max(5, Math.min(12, Math.floor(Math.min(maxFontW, maxFontH))));

        ctx.font = `bold ${fontPx}px "JetBrains Mono", monospace`;
        // 값 셀 텍스트: 채도 높은 범례색 위 흰색 고정(테마 불변), 좌표 표기: 테마 토큰
        ctx.fillStyle = val !== '' ? '#ffffff' : (completelyInside ? C.textEmpty : C.textOut);
        ctx.fillText(textToDraw, x0 + cellW / 2, y0 + cellH / 2);
      }

      // 5b. [Overlay] Layer cells are keyed by **physical coordinate** — projectCellsToPhys
      //     projected them through the source map's own frame — and coordKey in this loop is
      //     the same physical key, so nothing is transformed here. When the on-screen geometry
      //     changes, the main map and the overlay move together under the same rule.
      //     Cell values are never overwritten; only markers are drawn on top.
      if (activeOverlayLayers.length > 0) {
        drawOverlayMarkers(ctx, coordKey, x0, y0, cellW, cellH);
      }
    }
  }

  // 5c. 선언된 격자의 외곽선. **여백이 실제로 생겼을 때만** 그린다 — 여백이 0이면 격자가
  //     캔버스를 정확히 채우므로 이 선은 캔버스 테두리와 겹쳐 아무 정보도 더하지 않는다.
  //     여백이 있을 때는 「여기까지가 이 맵이다」를 한 획으로 말한다. 격자 밖 칸의 색조
  //     차이(채움 없음)만으로는 라이트 테마에서 미묘하고, 가독성은 이 프로젝트에서 기능이다.
  if (padX > 0.5 || padY > 0.5) {
    ctx.strokeStyle = C.lineStrong;
    ctx.lineWidth = 1.5;
    ctx.strokeRect(originX, originY, visualCols * cellW, visualRows * cellH);
  }

  // 6. Physical Wafer Circles (FIXED at Wafer Center 0,0 at Canvas Center)
  //    🔴 여기에는 고칠 것이 없다 — 반지름은 `(mm / chipX) * cellW`이고 `cellMetrics`가
  //       `cellW = chipX * s`를 주므로 두 반지름이 **구조적으로** `mm * s`로 같아진다.
  //       원이 원인 것이 우연이 아니라 항등이 되는 자리가 여기다.
  const waferCenterX = width / 2.0;
  const waferCenterY = height / 2.0;

  // A. White Outer Silicon Wafer Edge Circle (Full Diameter, e.g. 300mm)
  const outerRadX = ((physConfig.waferDia / 2.0) / physConfig.chipX) * cellW;
  const outerRadY = ((physConfig.waferDia / 2.0) / physConfig.chipY) * cellH;

  ctx.beginPath();
  if (typeof ctx.ellipse === 'function') {
    ctx.ellipse(waferCenterX, waferCenterY, outerRadX, outerRadY, 0, 0, 2 * Math.PI);
  } else {
    ctx.arc(waferCenterX, waferCenterY, outerRadX, 0, 2 * Math.PI);
  }
  ctx.strokeStyle = C.waferEdge;
  ctx.lineWidth = 2.0;
  ctx.stroke();

  // B. Green Edge Exclusion Boundary Circle (Effective Radius, e.g. 147mm = 150mm - Edge Exclusion)
  const effRadX = (physConfig.effectiveRadius / physConfig.chipX) * cellW;
  const effRadY = (physConfig.effectiveRadius / physConfig.chipY) * cellH;

  ctx.beginPath();
  if (typeof ctx.ellipse === 'function') {
    ctx.ellipse(waferCenterX, waferCenterY, effRadX, effRadY, 0, 0, 2 * Math.PI);
  } else {
    ctx.arc(waferCenterX, waferCenterY, effRadX, 0, 2 * Math.PI);
  }
  ctx.strokeStyle = C.success;
  ctx.lineWidth = 2.0;
  ctx.setLineDash([6, 4]);
  ctx.stroke();
  ctx.setLineDash([]);

  // C. Centering Offset Marker Point (Drawn at center of shifted chip grid array)
  const gridCenterX = waferCenterX + shiftX;
  const gridCenterY = waferCenterY + shiftY;
  if (physConfig.offsetX !== 0 || physConfig.offsetY !== 0) {
    ctx.beginPath();
    ctx.arc(gridCenterX, gridCenterY, 4, 0, 2 * Math.PI);
    ctx.fillStyle = C.warning;
    ctx.fill();
    ctx.strokeStyle = C.surface;
    ctx.lineWidth = 1.0;
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(gridCenterX - 8, gridCenterY);
    ctx.lineTo(gridCenterX + 8, gridCenterY);
    ctx.moveTo(gridCenterX, gridCenterY - 8);
    ctx.lineTo(gridCenterX, gridCenterY + 8);
    ctx.strokeStyle = C.warning;
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }

  // 7. Selection Box overlay
  if (isBoxDragging && lastSelectionBox) {
    const { minC, maxC, minR, maxR } = lastSelectionBox;
    const boxX = minC * cellW + originX;
    const boxY = minR * cellH + originY;
    const boxW = (maxC - minC + 1) * cellW;
    const boxH = (maxR - minR + 1) * cellH;

    const isErase = (dragType === 'erase');
    ctx.fillStyle = isErase ? C.dangerWeak : C.rangeFill;
    ctx.fillRect(boxX, boxY, boxW, boxH);

    ctx.strokeStyle = isErase ? C.danger : C.accent;
    ctx.lineWidth = 2.0;
    ctx.strokeRect(boxX + 1, boxY + 1, boxW - 2, boxH - 2);
  }

  // 8. Hover Cell highlight
  if (currentHoverCell && !isBoxDragging) {
    const hX = currentHoverCell.c * cellW + originX;
    const hY = currentHoverCell.r * cellH + originY;
    ctx.strokeStyle = C.accent;
    ctx.lineWidth = 2.0;
    ctx.strokeRect(hX + 1, hY + 1, cellW - 2, cellH - 2);
  }

  // 9. FRONT / BACK translucent watermark (display-only overlay, centered)
  //    Faint large label showing the current observation side. Purely visual:
  //    it draws centered text only and touches NO cell data / gridCells2D / hit-test,
  //    so it never affects mouse->cell mapping. Font/alignment state is isolated
  //    via save/restore so it doesn't leak into the next render pass.
  //    FRONT = sky blue, BACK = amber (matches the DOM #side-indicator chip).
  {
    const isBack = (currentSide === 'back');
    const sideWord = isBack ? 'BACK' : 'FRONT';
    const wmColor = isBack ? C.wmBack : C.wmFront;
    const wmFont = Math.max(40, Math.floor(width * 0.16));

    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `900 ${wmFont}px "JetBrains Mono", monospace`;
    ctx.fillStyle = wmColor;
    ctx.fillText(sideWord, width / 2, height / 2);
    ctx.restore();
  }

  ctx.restore();

  // [C1] 종횡비를 모른다는 **사실**의 표기. 미상은 1:1이 아니다 — 선언이 없을 때 화면이
  //      말없이 정사각 셀을 그리면 조작자는 그것을 규격으로 읽는다.
  // [C2] 지름 미선언도 같은 부류라 **같은 표기 자리**를 쓴다 — 새 영역·모드·컨트롤 없음.
  //      지름 표기는 등방 분기에서만 나온다: 폴백에서는 `waferAnchored`가 언제나 false라
  //      (붙일 축척 자체가 없다) 지름을 선언했는데도 미선언이라고 말하게 된다. 폴백
  //      상태는 위 종횡비 표기가 이미 말하고 있다.
  // [D1] 자동 등록 규격은 **자기 문장을 갖는다.** 「Chip X/Y 미선언」은 이 경우에 거짓으로
  //      읽힌다 — 입력칸에는 1이 보이므로 조작자는 선언이 있다고 읽고, 왜 원이 사라졌는지
  //      알 길이 없다. 새 컨트롤이 아니라 이미 있는 이 표기 자리의 세 번째 문구다.
  if (el.cellAspectNote) {
    const notes = [];
    if (!isotropic) {
      notes.push(geometryIsAutoRegistered(null)
        ? '기하 규격 미선언 (자동 등록된 합성 규격) — 칩 크기를 잰 적이 없어 웨이퍼 원을 그리지 않습니다'
        : '셀 종횡비 미상 (Chip X/Y 미선언) — 원이 찌그러져 보입니다');
    } else if (!waferAnchored) notes.push('웨이퍼 지름 미선언 — 원 크기가 격자에 따라 달라집니다');
    el.cellAspectNote.style.display = notes.length > 0 ? '' : 'none';
    el.cellAspectNote.textContent = notes.join(' · ');
  }

  updateNotchPosition();
  updateLegendCounts();
}

function handleCellClick(cell, event) {
  if (!cell) return;
  const c = cell.c !== undefined ? cell.c : 0;
  const r = cell.r !== undefined ? cell.r : 0;
  const key = cell.key;

  if (isProtectedFCell(key)) {
    return;
  }

  if (isOriginMode) {
    const box = getWaferBoundingBox(null, currentRotation, currentSide);
    const invertY = el.gridYInvert ? el.gridYInvert.checked : false;

    const newStartX = box.minC - c;
    const newStartY = !invertY ? (box.minR - r) : (r - box.maxR);

    el.gridStartX.value = newStartX;
    el.gridStartY.value = newStartY;

    isOriginMode = false;
    el.btnSetOrigin.classList.remove('active');
    el.btnSetOrigin.style.borderColor = '';
    el.btnSetOrigin.style.color = '';
    el.gridCanvas.classList.remove('origin-mode-active');

    scheduleRenderGridCanvas();
    return;
  }

  let isRight = isRightDrag;
  if (event) {
    isRight = (event.button === 2 || event.buttons === 2);
  }

  if (isRight) {
    gridData[key] = '';
  } else {
    if (activeBrush !== undefined && activeBrush !== null) {
      const existingVal = gridData[key] || '';
      if (!event && existingVal !== '') {
        return;
      }
      gridData[key] = activeBrush;
    }
  }

  updateLegendCounts();
  scheduleRenderGridCanvas();
  // 그림이 곧 계획이다 — 칠한 셀 수가 모든 파생 수량의 입력이므로, 새로고침으로 그림이
  // 사라지면 계획의 수량도 함께 사라진다.
  scheduleCellDraft();
}

function updateCellStyles(cell, val) {
  const match = legend.find(item => item.value === val);
  if (match && val !== '') {
    cell.style.backgroundColor = match.color;
    cell.style.borderColor = 'var(--border-strong)';
  } else {
    cell.style.backgroundColor = 'var(--bg-inset)';
    cell.style.borderColor = 'var(--border)';
  }
}

// ----------------------------------------------------
// V-Notch Orientation & Offsets
// ----------------------------------------------------
function updateNotchPosition() {
  if (!el.gridNotch) return;

  el.gridNotch.className = 'wafer-notch';
  el.gridNotch.textContent = 'D';

  let positionClass = '';
  if (currentRotation === 0) positionClass = 'notch-bottom';
  else if (currentRotation === 90) positionClass = 'notch-left';
  else if (currentRotation === 180) positionClass = 'notch-top';
  else if (currentRotation === 270) positionClass = 'notch-right';
  el.gridNotch.classList.add(positionClass);

  const offset = 24; // px shift
  el.gridNotch.style.left = '';
  el.gridNotch.style.right = '';
  el.gridNotch.style.top = '';
  el.gridNotch.style.bottom = '';
  el.gridNotch.style.transform = '';

  const dx = (currentSide === 'front') ? 1 : -1;
  let screenDx = 0;
  let screenDy = 0;

  if (currentRotation === 0) { screenDx = dx; screenDy = 0; }
  else if (currentRotation === 90) { screenDx = 0; screenDy = dx; }
  else if (currentRotation === 180) { screenDx = -dx; screenDy = 0; }
  else if (currentRotation === 270) { screenDx = 0; screenDy = -dx; }

  if (currentRotation === 0) { // Bottom
    el.gridNotch.style.bottom = '2px';
    const shift = screenDx * offset;
    el.gridNotch.style.left = `calc(50% + ${shift}px)`;
    el.gridNotch.style.transform = 'translateX(-50%)';
  } else if (currentRotation === 180) { // Top
    el.gridNotch.style.top = '2px';
    const shift = screenDx * offset;
    el.gridNotch.style.left = `calc(50% + ${shift}px)`;
    el.gridNotch.style.transform = 'translateX(-50%)';
  } else if (currentRotation === 90) { // Left
    el.gridNotch.style.left = '2px';
    const shift = screenDy * offset;
    el.gridNotch.style.top = `calc(50% + ${shift}px)`;
    el.gridNotch.style.transform = 'translateY(-50%)';
  } else if (currentRotation === 270) { // Right
    el.gridNotch.style.right = '2px';
    const shift = screenDy * offset;
    el.gridNotch.style.top = `calc(50% + ${shift}px)`;
    el.gridNotch.style.transform = 'translateY(-50%)';
  }
}

// ----------------------------------------------------
// Legend / Palette Management
// ----------------------------------------------------
// [U6] THE palette, in one place. It used to be written out three times (panel [+ 값],
// unknown imported values, map-load legend build) — three copies of the same twelve
// colors is how they drift. Colors are a client styling choice, not server data; only
// per-VALUE colors/descs come from the served default_legend (declaredLegendRow).
const LEGEND_PALETTE = ['#10b981', '#ef4444', '#3b82f6', '#ec4899', '#f59e0b', '#8b5cf6',
  '#14b8a6', '#f43f5e', '#06b6d4', '#84cc16', '#a855f7', '#6b7280'];

function pickUnusedColor() {
  const used = new Set(legend.map(l => l.color));
  return LEGEND_PALETTE.find(c => !used.has(c))
    || '#' + Math.floor(Math.random() * 16777215).toString(16).padStart(6, '0');
}

// [U6] The ONE way a value gets auto-added to the legend. Declared default_legend row
// wins (its color/desc); else fallbackDesc + the palette rule. Returns true only when a
// row was actually added — callers decide how to persist/render.
function autoAddLegendValue(value, fallbackDesc) {
  const v = String(value);
  if (legend.some(item => String(item.value) === v)) return false;
  const dr = declaredLegendRow(v);
  legend.push(normalizeLegendItem({
    value: v,
    desc: dr ? String(dr.desc || '') : String(fallbackDesc || ''),
    color: (dr && dr.color) ? String(dr.color) : pickUnusedColor(),
  }));
  return true;
}
// 빈 DOE 한 줄. **"registry 행이 없다"의 유일한 답**이고, 그 답의 구현도 여기 하나뿐이다.
//
// `vocab: true`로 표시하고 서명을 남기는 것은 여전히 의미가 있다 — 어휘 시딩이 사라져도 이
// 자리표시 행은 남기 때문이다. 사용자가 손대지 않은 자리표시가 registry 행을 만들어서는
// 안 되고(그러면 "만든 적 없는 계획"이 서버에 생긴다), 한 글자라도 치거나 그 값으로 칠하는
// 순간 `reconcileVocabClaims`가 그것을 이 맵의 것으로 판정해 저장한다.
function seedEmptyDoe() {
  legendMeta = {};
  legend = cloneLegend(defaultLegendRows());
  legendVocabularySeed = new Map();
  legend.forEach(l => { l.vocab = true; legendVocabularySeed.set(String(l.value), legendRowSignature(l)); });
  activeBrush = legend.length > 0 ? legend[0].value : '';
}

// ⚠️ 종전에 여기에 `map_legend_<table>` 캐시가 있었다. **테이블 키인데 계획은 맵 단위**라,
//    맵 A에서 만든 값이 맵 B를 열었을 때 화면에 남는 두 번째 시딩 경로였다. 2026-07-28의
//    규칙("행이 있으면 그것만, 없으면 빈 줄 하나")은 그런 경로를 금지하므로 **읽기를 지웠고,
//    쓰기도 지웠다** — 아무도 읽지 않는 캐시는 다음 사람에게 함정이다. 이미 브라우저에 남아
//    있는 것은 아래에서 능동적으로 치운다(남겨 두면 예전 코드가 돌아왔을 때 되살아난다).
//    오프라인 복구는 **맵 단위**인 `saveDoeDraft`가 맡는다 — 그쪽은 스코프가 맞다.
function saveLegendToStorage() {
  try { localStorage.removeItem(`map_legend_${selectedTable}`); } catch (e) { /* 지우기 실패는 무해 */ }
  saveDoeDraft();
}

// ── DOE 맵 단위 초안 (서버 저장 실패 시 편집을 잃지 않기 위한 것) ──
// 적용은 **registry 조회가 실패했을 때만**이다. 조회에 성공했다면 서버가 정본이고,
// 그 위에 초안을 덮으면 다른 세션의 저장이 조용히 지워진다.
function doeDraftKey(table, mapKey) { return `map_doe_draft::${table}::${mapKey}`; }

// 🔴 초안의 우선순위 규칙 — 이 규칙이 없으면 초안이 남의 최신 저장을 조용히 덮는다.
//
// 초안은 **아직 서버가 받아들이지 않은 내 편집**일 때만 이긴다. 그것을 증명하는 방법은 하나뿐:
// 초안을 뜰 때 기반이 된 서버 상태의 지문을 함께 저장하고, 다시 열 때 그 지문이 그대로인지
// 본다. 지문이 같으면 그 사이 아무도 쓰지 않았으므로 초안이 엄격히 더 새 것이다. 다르면
// **누가 썼다** — 그때 초안을 적용하면 남의 저장을 지우는 것이고, 이것은 이미 저장 경로에서
// 막고 있는 것(`legendReplaceScope` + fingerprint)과 정확히 같은 사고다. 그래서:
//
//   지문 일치      → 초안 적용 (내 편집이 서버보다 새 것)
//   지문 불일치    → **적용하지 않는다. 그리고 조용히 버리지도 않는다** — 화면은 서버본,
//                    사실은 토스트로 드러내고 초안은 저장소에 남긴다.
//   서버 조회 실패 → 비교할 대상이 없다. 초안을 보여주고 저장은 보류한다(종전 동작).
//   저장 성공      → 초안을 지운다. 저장을 넘겨 살아남은 초안은 다음 로드에서 유령 편집이 된다.
//
// ⚠️ 이 초안이 **하중을 받게 된 것은 오늘부터**다. 차단 검증(V1–V5)이 붙으면서 잘못된 계획은
//    저장이 나가지 않고, 그동안 사용자의 작업은 **브라우저에만** 있다. 검증이 엄격할수록
//    초안에만 존재하는 시간이 길어지고, 새로고침 한 번의 비용이 커진다.
//
// 맵 셀도 같은 규율이다. 셀의 서버 상태는 registry가 아니라 맵 테이블이므로 지문도 따로
// 뜬다(로드된 셀의 결정적 요약). 두 지문 중 하나라도 어긋나면 그 쪽은 적용하지 않는다.
// v4 ― 물리 키의 원점이 격자 인덱스에서 **웨이퍼 중심**으로 바뀌었다(§getDieIndex).
// 초안은 `cells`를 물리 키로 저장하므로, v3 초안을 그대로 복원하면 값들이 **다른 칸**에
// 앉는다. 마이그레이션하지 않고 버린다 ― 저장 안 된 작업 한 번을 다시 그리는 쪽이,
// 좌표가 조용히 옮겨간 맵을 복원하는 것보다 낫다.
const DRAFT_VERSION = 4;

// 결정적 요약. 암호학적 강도가 필요 없다 — "그 사이에 바뀌었나"만 답하면 되고, 같은 입력이
// 같은 값을 내는 것과 두 브라우저가 같은 규칙을 쓰는 것만 지켜지면 된다 (FNV-1a).
function cellsDigest(cells) {
  const keys = Object.keys(cells || {}).filter(k => String(cells[k] ?? '') !== '').sort();
  let h = 0x811c9dc5;
  for (const k of keys) {
    const s = JSON.stringify([k, cells[k]]);
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  }
  return `${keys.length}:${(h >>> 0).toString(16)}`;
}

// 이 맵을 열었을 때 서버가 갖고 있던 것. 초안의 기반 지문이고, 새 초안을 뜰 때마다 여기서
// 읽어 함께 저장한다. null이면 서버본에서 유래한 화면이 아니다(= 초안의 기반을 증명할 수 없다).
let draftBase = null;   // { table, mapKey, registryFp, cellsFp } | null

// [F2b] 같은 로드가 돌려준 **셀 키 집합**. `draftBase`의 셀 판(版)이고 같은 규율을 진다:
// 서버 상태를 모르면 null이며, null이면 아무것도 지우지 않는다(불변식 ③).
//
// 🔴 이것이 "정리(cleanup)"의 유일한 근거다. 유효 다이 밖 셀에는 출처가 **두 가지**다 —
//    ① 옛 `Fill All`이 사각형 전체를 칠하며 남긴 흔적(서버에 없다) ② 파서가 인제션한 맵이
//    현재 물리 규격의 마스크를 벗어난 경우(서버에 있다). 좌표만 보면 둘은 구별되지 않고,
//    ②를 지운 뒤 Push하면 `replace_map`이 그 행들을 **서버에서 삭제한다**(불변식 ④, H2와
//    같은 계급의 파괴). 그래서 정리는 "서버가 보낸 적 없다"가 증명된 키에만 허용한다.
let serverCellKeys = null;   // { table, mapKey, keys: Set<string> } | null

// 지금 화면의 맵에 대해 서버 셀 집합을 신뢰할 수 있는가. 정체는 `loadedIdentity`가 지고
// 있으므로(프레임 스택이 스냅샷으로 함께 옮긴다) 여기서 다시 만들지 않고 대조만 한다.
function serverCellKeySet() {
  if (!serverCellKeys || !loadedIdentity) return null;
  if (serverCellKeys.table !== loadedIdentity.table) return null;
  if (serverCellKeys.mapKey !== loadedIdentity.mapKey) return null;
  return serverCellKeys.keys;
}

function saveDoeDraft() {
  const mapKey = getCurrentMapKey();
  if (!selectedTable || !mapKey) return;
  try {
    const doe = {};
    legend.forEach(l => {
      const zoned = String(l.stack ?? '').trim() !== ''
        || (l.mat_1h && l.mat_1h.length) || (l.mat_mid && l.mat_mid.length) || (l.mat_top && l.mat_top.length);
      if (zoned || (l.knobs && l.knobs.length)) {
        doe[l.value] = {
          knobs: normalizeKnobs(l.knobs),
          stack: (l.stack === null || l.stack === undefined) ? '' : l.stack,
          mat_1h: parseMaterialList(l.mat_1h),
          mat_mid: parseMaterialList(l.mat_mid),
          mat_top: parseMaterialList(l.mat_top),
        };
      }
    });
    const base = (draftBase && draftBase.table === selectedTable && draftBase.mapKey === mapKey)
      ? draftBase : null;
    localStorage.setItem(doeDraftKey(selectedTable, mapKey), JSON.stringify({
      v: DRAFT_VERSION,
      at: getLocalTimeString(),
      // 기반 지문. 없으면(`null`) 이 초안은 서버본에서 유래하지 않았다는 뜻이고, 로드 때
      // 비교할 수 없으므로 **서버 조회가 실패했을 때만** 쓰인다.
      registryFp: base ? base.registryFp : null,
      cellsFp: base ? base.cellsFp : null,
      doe,
      // 맵 셀 — 사용자 지시 2026-07-28 ("맵도"). 새로고침으로 그림이 사라지면 계획의 모든
      // 파생 수량(칠한 셀 수 × 층 수)이 함께 사라진다.
      cells: { ...gridData },
    }));
  } catch (e) {
    console.warn('[Map Editor] DOE draft save failed:', e);
  }
}

function readDoeDraft(table, mapKey) {
  try {
    const raw = localStorage.getItem(doeDraftKey(table, mapKey));
    if (!raw) return null;
    const d = JSON.parse(raw);
    if (!d || typeof d !== 'object') return null;
    // v3 이전 초안은 기반 지문이 없다. 버리지 않고 "기반 미상"으로 받는다 — 서버 조회가
    // 실패했을 때의 복구 경로에서는 여전히 쓸모가 있고, 성공했을 때는 적용되지 않는다.
    if (d.v !== DRAFT_VERSION) return { v: 0, doe: d, cells: null, registryFp: null, cellsFp: null };
    return d;
  } catch (e) { return null; }
}

function clearDoeDraft(table, mapKey) {
  try { localStorage.removeItem(doeDraftKey(table, mapKey)); } catch (e) { /* 무해 */ }
}

// ── Last-open map — the ENTRY POINT survives refresh, not just the content ──────────
// The draft system keeps what was drawn; this record keeps WHICH map was open (user
// 2026-07-28: "새로 고침하면 그냥 아예 처음창으로 가는데"). Depth-0 identity only —
// a material frame is a journey, not a home, so frame loads never overwrite it.
const LAST_OPEN_KEY = 'map_editor_last_open';

function recordLastOpenMap() {
  if (editorFrames.length > 0) return;   // material frame — keep the root map's record
  try {
    const metaValues = {};
    document.querySelectorAll('[id^="meta-input-"]').forEach(input => {
      const val = input.value.trim();
      if (val) metaValues[input.id.replace('meta-input-', '')] = val;
    });
    if (!selectedTable || Object.keys(metaValues).length === 0) return;
    localStorage.setItem(LAST_OPEN_KEY, JSON.stringify({
      v: 1, table: selectedTable, metaValues, at: getLocalTimeString(),
    }));
  } catch (e) { /* recording must never break a load */ }
}

// Boot restore. Walks the EXACT manual path — table select + switchTable + meta inputs +
// loadExistingMap({quiet}) — so draft precedence, missing-key behavior (opens empty, key
// created on ⚡ Push) and identity pinning are the same code, not a parallel restore path.
// Any failure falls back to the initial screen; boot never raises an error dialog.
async function restoreLastOpenMap() {
  let rec = null;
  try { rec = JSON.parse(localStorage.getItem(LAST_OPEN_KEY) || 'null'); } catch (e) { return; }
  if (!rec || rec.v !== 1 || !rec.table || !rec.metaValues
    || Object.keys(rec.metaValues).length === 0) return;
  // Table gone (renamed/removed/no longer a map table) — initial screen, silently.
  if (!el.tableSelect || !Array.from(el.tableSelect.options).some(o => o.value === rec.table)) return;
  // Double-load guard: loadExistingMap only disables the button during its own fetch,
  // so cover the whole restore (including switchTable) to keep the user from racing it.
  if (el.btnLoadMap) el.btnLoadMap.disabled = true;
  el.tableSelect.disabled = true;
  try {
    if (rec.table !== selectedTable) {
      el.tableSelect.value = rec.table;
      await switchTable(rec.table);
    }
    Object.entries(rec.metaValues).forEach(([col, val]) => {
      const input = document.getElementById(`meta-input-${col}`);
      if (input) input.value = val === null || val === undefined ? '' : String(val);
    });
    // 부팅 복원만이 초안을 되살린다 — 새로고침은 「하던 것을 돌려달라」가 맞다.
    await loadExistingMap({ quiet: true, restoreDraft: true });
  } catch (e) {
    console.warn('[Map Editor] last-open restore failed — staying on the initial screen:', e);
  } finally {
    el.tableSelect.disabled = false;
    if (el.btnLoadMap) { el.btnLoadMap.disabled = false; el.btnLoadMap.textContent = '📂 Load Existing Map'; }
  }
}

// 초안을 화면에 적용한다. **우선순위 판정은 호출부가 한다** — 이 함수는 적용만 한다.
function applyDoeDraftRecord(draft) {
  const doe = (draft && draft.doe) || {};
  let applied = false;
  legend.forEach(l => {
    const d = doe[l.value];
    if (!d) return;
    // "applied" must mean "this draft CHANGED the screen", not "this draft had content".
    // A draft is re-saved right after a successful registry save (saveLegendToServer),
    // so after Push + refresh the draft is identical to the server rows - reporting that
    // as a restored edit would resurrect a phantom "unsaved" chip and toast on every
    // reload of a map that has a plan. Legend rows here are already normalized
    // (applyRegistryRowsToLegend / normalizeLegendItem), so the projection compares
    // like with like.
    const before = JSON.stringify([l.knobs, l.stack, l.mat_1h, l.mat_mid, l.mat_top]);
    l.knobs = normalizeKnobs(d.knobs);
    // A draft written by the retired band model is migrated on read, exactly like the
    // server column - and refused the same way if it cannot be expressed. A draft is a
    // recovery path, so it is the last place that may quietly reshape a plan.
    const z = Array.isArray(d.bands) ? bandsToZones(normalizeBands(d.bands)) : null;
    const src = (z && z.ok) ? z : d;
    l.stack = (src.stack === null || src.stack === undefined) ? '' : src.stack;
    l.mat_1h = parseMaterialList(src.mat_1h);
    l.mat_mid = parseMaterialList(src.mat_mid);
    l.mat_top = parseMaterialList(src.mat_top);
    if (z && !z.ok) { l.legacyBands = normalizeBands(d.bands); l.legacyReason = z.reason; }
    if (JSON.stringify([l.knobs, l.stack, l.mat_1h, l.mat_mid, l.mat_top]) !== before) applied = true;
  });
  // 값 자체가 초안에만 있는 경우 — 사용자가 [+ 값]으로 만들고 아직 저장이 안 나갔다.
  Object.keys(doe).forEach(v => {
    if (legend.some(l => String(l.value) === String(v))) return;
    legend.push(normalizeLegendItem({ ...doe[v], value: v, vocab: false }));
    applied = true;
  });
  return applied;
}

// 초안의 맵 셀을 적용한다. 잠긴 셀은 건드리지 않는다 — 페인트 잠금은 초안보다 위다.
function applyDraftCells(cells) {
  if (!cells || typeof cells !== 'object') return 0;
  let n = 0;
  Object.keys(cells).forEach(k => {
    if (isProtectedFCell(k)) return;
    const v = cells[k];
    if (gridData[k] === v) return;
    gridData[k] = v;
    n++;
  });
  return n;
}

// ── Split Registry 서버 IO ──────────────────────────

// 현재 메타 입력값들로 맵 식별자(map_key) 해석 — 미입력이면 null (push 시 일괄 저장으로 미룸)
function getCurrentMapKey() {
  const dict = {};
  document.querySelectorAll('[id^="meta-input-"]').forEach(input => {
    const col = input.id.replace('meta-input-', '');
    const val = input.value.trim();
    if (val !== '') dict[col] = val;
  });
  if (Object.keys(dict).length === 0) return null;
  const mapKey = getMapIdFromMeta(dict, tableSchema);
  return (mapKey && mapKey !== 'default_map') ? mapKey : null;
}

// The registry is keyed (ref_table, map_key, value). There is exactly ONE legitimate read
// of it now:
//
//   'map' - one map's own rows. The ONLY read, and the only one that may back a
//           `replace_map` write.
//
// ⚠️ 'vocabulary' (every map key in the table, deduped by value) WAS the second one, and it
//    is GONE (2026-07-28). It backed the "no map open yet" brush palette, which the user
//    reported twice as a defect - a panel that opens with values nobody entered is
//    indistinguishable from a bug. The rule is now two branches with no third: this map's
//    rows if it has any, one empty DOE row if it does not (`seedEmptyDoe`).
//
// THE SCOPE IS STILL SPELLED, and the list still exists with one member on purpose. The
// original defect was not "there were two modes" - it was that the mode was INFERRED from
// `mapKey == null`. Two call sites passed null for a reason that was true where they stood,
// the read silently became table-wide, and the resulting legend sat under an opened map
// indistinguishable from that map's own rows. Saving it wrote another map's values in - and
// because the write is `replace_map`, they became this map's plan. A named scope that
// refuses anything it does not recognise is what closed that, and it stays closed whether
// the list has one entry or two.
const REGISTRY_SCOPES = ['map'];
async function fetchRegistryRows(scope, refTable, mapKey) {
  if (REGISTRY_SCOPES.indexOf(scope) < 0) throw new Error(`unknown registry scope '${scope}'`);
  if (scope === 'map' && !mapKey) throw new Error('registry scope "map" requires a map key');
  const filters = { ref_table: { filterType: 'text', type: 'equals', filter: refTable } };
  if (scope === 'map') filters.map_key = { filterType: 'text', type: 'equals', filter: mapKey };
  const url = `${API_BASE}/tables/${SPLIT_REGISTRY_TABLE}/data?limit=500&filters=${encodeURIComponent(JSON.stringify(filters))}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`split registry fetch failed (HTTP ${res.status})`);
  const result = await res.json();
  // A truncated read is not a read. The legend save is a `replace_map` write, so
  // saving a set built from a partial response would delete the rows we never
  // saw. Fail the load instead - the caller falls back to the cache and, because
  // the load failed, never claims replace authority.
  if (result && typeof result.total === 'number' && result.total > (Array.isArray(result.data) ? result.data.length : 0)) {
    throw new Error(`split registry response truncated (${result.total} > ${(result.data || []).length})`);
  }
  // ⚠️ `false`, always, and the parameter is kept rather than removed. The map scope must
  //    NEVER dedupe: dedupe was the vocabulary mode's collapse across map keys, and doing
  //    it here would MASK a broken `map_key` filter - a widened read would come back as a
  //    plausible one-row-per-value legend instead of an obviously wrong pile.
  return parseLegendRegistryRows(result, false);
}

// 같은 조회를 예외 없이 쓰는 형태. 로드·저장 양쪽이 이 한 함수만 쓴다 —
// 조회 규율(절단 = 실패)의 구현이 둘로 갈리면 한쪽만 방어된다.
async function readRegistryScope(refTable, mapKey) {
  try {
    return { ok: true, rows: await fetchRegistryRows('map', refTable, mapKey) };
  } catch (e) {
    return { ok: false, rows: [], error: e && e.message ? e.message : String(e) };
  }
}

// A CLAIM IS DERIVED, NOT ONLY DECLARED.
//
// `vocab` is cleared explicitly at three intent points (registry match, painted cell,
// panel edit). That was one gate away from a silent data-loss bug: any NEW edit path that
// forgets to clear the mark leaves the user's typing on screen and drops it from the save
// - visible, plausible, and wrong. The DOE redesign adds a whole second table of edit
// paths, so the mark cannot be the only mechanism.
//
// So the claim is also RECOMPUTED from facts no edit path can avoid producing:
//   * the value is painted on this map's grid, or
//   * the row no longer matches the vocabulary row it was borrowed from.
// A forgotten gate is now harmless: the moment the row differs from its seed, it is
// claimed. `reconcileVocabClaims` runs at both points that matter (opening a map, and
// immediately before building the write payload), so nothing can slip between them.
function reconcileVocabClaims() {
  const painted = new Set();
  Object.keys(gridData).forEach(k => {
    const v = String(gridData[k] === null || gridData[k] === undefined ? '' : gridData[k]).trim();
    if (v) painted.add(v);
  });
  legend.forEach(item => {
    if (!item.vocab) return;
    if (painted.has(String(item.value))) { item.vocab = false; return; }
    // Marked rows always have a seed - `mark()` writes both together and the frame
    // snapshot carries both. So a marked row with NO seed means its value was renamed
    // away from the key it was borrowed under, which is an edit; and a seed that no
    // longer matches means the row was edited in place. Either way it is this map's now.
    const seed = legendVocabularySeed.get(String(item.value));
    if (seed === undefined || seed !== legendRowSignature(item)) item.vocab = false;
  });
}

// 서버 registry 행을 화면 legend에 반영한다 (로드·저장중 채택 공용).
// ⚠️ registry에 없는 값의 DOE 필드는 **비운다**. knobs/bands는 (테이블, 맵 키) 하나의
//    것이라, 같은 테이블의 다른 맵을 열었을 때 앞 맵의 스택이 남아 있으면
//    화면은 멀쩡한데 값이 틀린다.
// ⚠️ 그리고 **이 맵이 보증하지 않는 vocabulary 행은 화면에서 내린다.** 맵이 열려 있는 동안
//    legend는 "이 맵의 registry 행 ∪ 이 맵이 칠한 값"과 정확히 같아야 한다 — 남의 맵에서
//    온 브러시가 남아 있으면 화면은 멀쩡한데 저장이 그 값을 이 맵의 계획으로 만든다.
function applyRegistryRowsToLegend(rows) {
  const byValue = new Map((rows || []).map(r => [String(r.value), r]));
  legendMeta = {};
  reconcileVocabClaims();
  const kept = [];
  legend.forEach(item => {
    const r = byValue.get(String(item.value));
    if (r) {
      if (r.desc) item.desc = r.desc;
      if (r.color) item.color = r.color;
      item.knobs = normalizeKnobs(r.knobs);
      item.stack = (r.stack === null || r.stack === undefined) ? '' : r.stack;
      item.mat_1h = parseMaterialList(r.mat_1h);
      item.mat_mid = parseMaterialList(r.mat_mid);
      item.mat_top = parseMaterialList(r.mat_top);
      item.legacyBands = Array.isArray(r.legacyBands) ? r.legacyBands : [];
      item.legacyReason = String(r.legacyReason || '');
      item.vocab = false;   // this map's own registry row - it is claimed now
      legendMeta[item.value] = { updated_by: r.updated_by, updated_at: r.updated_at };
      byValue.delete(String(item.value));
    } else {
      if (item.vocab) return;   // borrowed from another map key, unclaimed here - drop it
      item.knobs = [];
      item.stack = '';
      item.mat_1h = []; item.mat_mid = []; item.mat_top = [];
      item.legacyBands = []; item.legacyReason = '';
    }
    kept.push(item);
  });
  legend = kept;
  byValue.forEach(r => {
    legend.push(normalizeLegendItem({ ...r, vocab: false }));
    legendMeta[r.value] = { updated_by: r.updated_by, updated_at: r.updated_at };
  });
  // An empty palette cannot be painted with. Fall back to the generic defaults, still
  // marked `vocab` so they are shown but not written until the map claims them.
  if (legend.length === 0) {
    legend = cloneLegend(defaultLegendRows()).map(l => ({ ...l, vocab: true }));
  }
  if (legend.length > 0 && !legend.some(l => l.value === activeBrush)) {
    activeBrush = legend[0].value;
  }
}

// ⚠️ `loadLegendVocabulary`는 **삭제됐다** (2026-07-28). 테이블 전체 어휘를 읽어 브러시로
//    깔던 함수이고, 그것이 "내가 넣은 적 없는 값이 화면에 있다"의 원천이었다. 남은 두 분기는
//    `applyRegistryRowsToLegend`(행이 있을 때)와 `seedEmptyDoe`(없을 때)뿐이다.
//    'vocabulary' registry 스코프도 호출자가 없어져 `REGISTRY_SCOPES`에서 함께 내렸다 —
//    부르는 사람이 없는 스코프는 다음 사람이 "이건 되는구나"로 읽는 함정이다.

// Save the whole legend (= the whole DOE) of one map to the registry.
//
// The unit of this write is a map's ENTIRE set of values, so it is a `replace_map`
// write (scope = map_key_columns = ref_table|map_key): a value, a band or a material
// the user removed is simply absent from the set, and that alone deletes it on the
// server. There is no separate delete step to forget to run.
//
// Three things gate it, and each one exists because losing them cost real data:
//
//  0. SCOPE (`vocab`) - only values THIS map vouches for are in the payload at all.
//     `legendReplaceScope` below is a claim about the READ ("we saw this map's rows"),
//     not about the payload, so it cannot see a legend row borrowed from another map
//     key: the read is correctly scoped and the authority correctly granted while the
//     screen still carries someone else's values. That gap is what spread one map's
//     DOE across ten bonding_map keys. buildLegendRegistryUpdates drops `vocab` rows,
//     and the map's own painted cells clear the mark first.
//  1. AUTHORITY (`legendReplaceScope`) - only a legend that came from THIS map's own
//     registry rows may replace them. Replacing with a screen that never read the map
//     would delete rows we never saw.
//  2. TRUNCATION - a partial read is not a read (fetchRegistryRows throws), and a
//     failed read blocks the write instead of downgrading it. Downgrading to an upsert
//     used to be safe when the row held only desc/color; now the row holds the plan,
//     so an upsert from an unverified screen would overwrite bands we never saw.
//  3. CONCURRENCY (M2.6) - `replace_map` purges the whole scope, so with several people
//     on one plan the later save erases the other's values silently. Before replacing we
//     re-read and compare against the fingerprint we loaded. Different = refuse and say
//     so. One extra read on the write path; one row per value makes it cheap.
//
// Returns { ok, reason } - the caller turns `reason` into what the user is told.
async function saveLegendToServer(mapKeyOverride) {
  const mapKey = mapKeyOverride || getCurrentMapKey();
  if (!selectedTable || !mapKey) return { ok: false, reason: 'no-map-key' };

  if (legendConflict && legendConflict.table === selectedTable && legendConflict.mapKey === mapKey) {
    return { ok: false, reason: 'conflict' };
  }

  // 🔴 ZONE COLUMNS MUST PHYSICALLY EXIST BEFORE THIS WRITE IS ALLOWED.
  //
  // `stack`/`mat_1h`/`mat_mid`/`mat_top` are DECLARED in server/product_tables.py but the
  // physical ALTER is a separate step. If they are not there yet, crud.py drops them from
  // the payload - and this write is `replace_map`, so the scope is replaced by rows that
  // carry desc/color/knobs and NO LAYER STRUCTURE. The screen would still look right until
  // the next load. That is the whole plan, deleted, with a green "자동 저장" chip.
  //
  // Refusing here costs nothing: reading and editing still work, and the moment the column
  // appears the next debounced save goes out on its own. This is invariant ③ ("서버 상태를
  // 모르면 쓰지도 지우지도 않는다") applied to the schema instead of to the rows, and it
  // reuses the existing `unknown-server-state` treatment - no new control, no new panel.
  const zoneCols = await probeZoneColumns();
  if (zoneCols !== true) return { ok: false, reason: 'zone-columns-missing' };

  // A row we could not express as three zones must not be written. `bandsToZones` refused
  // it precisely because collapsing it would change the plan, and this write would then
  // replace the server's real bands with our lossy reading of them.
  const unreadable = legend.filter(l => l && l.vocab !== true && Array.isArray(l.legacyBands) && l.legacyBands.length > 0);
  if (unreadable.length > 0) return { ok: false, reason: 'legacy-unreadable', error: unreadable.map(l => `${l.value}: ${l.legacyReason}`).join(' · ') };

  // The one read that both the authority check and the concurrency check need.
  const read = await readRegistryScope(selectedTable, mapKey);
  if (!read.ok) return { ok: false, reason: 'unknown-server-state', error: read.error };

  const hasAuthority = !!legendReplaceScope
    && legendReplaceScope.table === selectedTable
    && legendReplaceScope.mapKey === mapKey;

  if (!hasAuthority) {
    if (read.rows.length > 0) {
      // The screen never saw this map's rows and the server has some. Adopt them and
      // end this cycle WITHOUT writing - the same C1 discipline as before: recovering
      // the read does not retroactively make the screen a server-derived set.
      applyRegistryRowsToLegend(read.rows);
      legendReplaceScope = { table: selectedTable, mapKey, fingerprint: registryFingerprint(read.rows) };
      renderLegendTable();
      renderGridCanvas();
      return { ok: false, reason: 'adopted' };
    }
    // Read succeeded and the scope is empty - there is nothing we could delete unseen.
    legendReplaceScope = { table: selectedTable, mapKey, fingerprint: registryFingerprint([]) };
  } else if (registryFingerprint(read.rows) !== legendReplaceScope.fingerprint) {
    legendConflict = { table: selectedTable, mapKey };
    return { ok: false, reason: 'conflict' };
  }

  const nowStr = getLocalTimeString();
  // Last chance to notice a claim before the payload is built. Deliberately AFTER every
  // possible edit path and immediately BEFORE buildLegendRegistryUpdates, so a row the
  // user changed through a path that forgot the gate is still saved.
  reconcileVocabClaims();
  const updates = buildLegendRegistryUpdates(selectedTable, mapKey, legend, CURRENT_USER, nowStr);
  if (updates.length === 0) return { ok: false, reason: 'empty' };
  // The rows that are actually going. Derived from `updates`, not recomputed from
  // `legend`, so the baseline fingerprint below cannot cover a row the payload filtered
  // out - that mismatch would make the very next save report a conflict with nobody there.
  const sentValues = new Set(updates.map(u => String(u.updates.value)));
  const sent = legend.filter(item => sentValues.has(String(item.value)));
  try {
    // [V1 effort instrument] No `effort` field: this registry write is the second half of
    // ONE human action whose counts already rode with the cell push in pushMapData.
    // Reporting here too would double-bill it. See that call site for the single point.
    const res = await fetch(`${API_BASE}/tables/${SPLIT_REGISTRY_TABLE}/data/updates`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates, replace_map: true })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    // `replace_map` purged the scope and wrote exactly this payload, so the server
    // now holds it - that is the new baseline. Both sides go through
    // canonRegistryRow, so "what we sent" and "what we would read back" are the
    // same normal form and a second save in a row cannot see a phantom conflict.
    legendReplaceScope = {
      table: selectedTable, mapKey,
      // The whole item, not a hand-listed projection of it: `canonRegistryRow` already
      // knows which columns count (LEGEND_PAYLOAD_COLUMNS), and re-listing them here is
      // how a new column ends up in the payload but not in the baseline - which surfaces
      // as "다른 사람이 이 계획을 변경했습니다" on the very next save, with nobody there.
      fingerprint: registryFingerprint(sent.map(item => ({ ...item, eventtime: nowStr }))),
    };
    sent.forEach(item => {
      legendMeta[item.value] = { updated_by: CURRENT_USER, updated_at: nowStr };
    });
    // 🔴 저장이 받아들여졌으므로 초안의 기반이 **여기**로 옮겨간다. 새 기반을 세우지 않으면
    //    다음 초안이 낡은 지문을 들고 다니게 되고, 그 초안은 다시 열 때 "누가 썼다"로 오판돼
    //    적용되지 않는다 — 있지도 않은 충돌로 사용자의 편집이 버려지는 경로다.
    //    셀 지문은 지금 화면 그대로다: Push 전이라 서버 맵은 움직이지 않았다.
    draftBase = {
      table: selectedTable, mapKey, registryFp: legendReplaceScope.fingerprint,
      cellsFp: cellsDigest(gridData)
    };
    // 저장을 넘겨 살아남은 초안은 다음 로드에서 유령 편집이 된다. 지운 뒤 곧바로 현재
    // 상태를 새 기반으로 다시 뜬다(셀은 아직 서버로 나가지 않았으므로 초안이 유일한 사본이다).
    clearDoeDraft(selectedTable, mapKey);
    saveDoeDraft();
    renderLegendMetaOnly();
    return { ok: true, at: nowStr, count: updates.length };
  } catch (e) {
    console.warn('[Map Editor] split registry save skipped (offline?):', e);
    return { ok: false, reason: 'error', error: e && e.message ? e.message : String(e) };
  }
}

// 이 배포의 registry 테이블에 zone 컬럼이 **물리적으로** 있는가. `true` | `false` | `null`(미상)
// 한 세션에 한 번만 묻는다. 실패는 캐시하지 않는다 — 한 번의 네트워크 실패가 그 세션 내내
// 저장을 막으면 그것도 조용한 데이터 유실이다(fetchMapKeyColumns의 [M5] 교훈과 같은 형태).
let zoneColumnsPresent = null;

// ⚠️ `/schema`는 **선언**을 돌려준다(config의 display_columns), 물리 컬럼이 아니다. 선언만
//    보고 통과시키면 ALTER 전에도 초록불이 켜지고, 그때 저장은 정확히 우리가 막으려는
//    파괴적 write가 된다. 그래서 실제 행 하나를 읽어 **셀 키 집합**을 본다: 제네릭 데이터
//    API는 물리 컬럼당 셀 하나를 돌려주므로 그 키가 물리 스키마의 증거다.
//    테이블이 비어 있으면 증거가 없다 — 그때만 선언으로 물러선다(지울 것도 없는 상태다).
const ZONE_COLUMNS = ['stack', 'mat_1h', 'mat_mid', 'mat_top'];
async function probeZoneColumns() {
  if (zoneColumnsPresent !== null) return zoneColumnsPresent;
  try {
    const res = await fetch(`${API_BASE}/tables/${SPLIT_REGISTRY_TABLE}/data?limit=1`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();
    const first = (result && Array.isArray(result.data) && result.data[0]) ? (result.data[0].data || {}) : null;
    if (first) {
      zoneColumnsPresent = ZONE_COLUMNS.every(c => Object.prototype.hasOwnProperty.call(first, c));
    } else {
      const sres = await fetch(`${API_BASE}/tables/${SPLIT_REGISTRY_TABLE}/schema`);
      if (!sres.ok) throw new Error(`HTTP ${sres.status}`);
      const schema = await sres.json();
      const cols = Array.isArray(schema.columns) ? schema.columns : [];
      zoneColumnsPresent = ZONE_COLUMNS.every(c => cols.indexOf(c) >= 0);
    }
    if (zoneColumnsPresent === false) {
      console.warn(`[Map Editor] ${SPLIT_REGISTRY_TABLE}에 zone 컬럼(${ZONE_COLUMNS.join(', ')})이 없습니다 — `
        + 'DOE 저장을 보류합니다. 선언은 server/product_tables.py에 있으나 물리 ALTER가 아직 실행되지 않았습니다.');
    }
    return zoneColumnsPresent;
  } catch (e) {
    console.warn('[Map Editor] zone 컬럼 확인 실패 — 캐시하지 않고 다음 저장에 재시도:', e);
    return null;      // 미상. 저장은 보류되지만 다음 시도에서 다시 묻는다.
  }
}

// 저장 결과 → 사용자 문구 (한 곳에서만). 패널 헤더 칩과 토스트가 같은 판정을 쓴다.
const LEGEND_SAVE_MESSAGE = {
  // ⚠️ 이 둘은 **계획이 틀려서가 아니라 저장이 데이터를 지우기 때문에** 막는다.
  //    미완성 계획은 그대로 저장된다(사용자 지시 2026-07-28: "그냥 doe 무효인대로 저장해") —
  //    V1–V5는 행 옆에 사유를 띄우고 서버 `validate`가 보고할 뿐, 저장을 막지 않는다.
  //    문구도 "무효"가 아니라 **무엇이 사라지는지**를 말한다.
  //    한 줄이고, `**`는 쓰지 않는다 — 토스트는 마크다운을 렌더하지 않아 별표가 그대로 나갔다.
  'zone-columns-missing': '층 구조 컬럼이 서버에 없어 저장 보류 — 서버 갱신 후 자동 재시도합니다.',
  'legacy-unreadable': '폐기된 구간 배치가 남아 저장 보류 — 해당 값의 STACK·구역을 채우십시오.',
  'unknown-server-state': '서버 DOE 상태 미확인으로 저장 보류 — 맵을 다시 열면 재시도합니다.',
  conflict: '다른 사람이 이 계획을 바꿨습니다 — 저장하지 않았습니다. 맵을 다시 불러오십시오.',
  adopted: '서버 계획을 불러왔습니다 — 그 사이 편집한 내용은 반영되지 않았습니다.',
  error: 'DOE·legend 저장 실패 — 로컬 초안만 남았습니다.',
};

function applyLegendSaveResult(r) {
  if (r.ok) {
    legendSaveState = { status: 'ok', at: r.at || '', error: '' };
  } else if (r.reason === 'no-map-key' || r.reason === 'empty') {
    return;   // 맵 키 미확정은 실패가 아니다 (push 때 일괄 저장)
  } else {
    legendSaveState = { status: r.reason === 'adopted' ? 'ok' : r.reason, at: '', error: r.error || '' };
    const msg = LEGEND_SAVE_MESSAGE[r.reason];
    if (msg) showToast(msg, r.reason === 'adopted' ? 'warning' : (r.reason === 'error' ? 'error' : 'warning'),
      { dedupeKey: `legend_save_${r.reason}` });
  }
  notifyLegendChanged();
}

// ⚠️ `scheduleLegendServerSave`는 **삭제됐다** (사용자 지시 2026-07-28: "변경 시 자동 저장을
//    하지마"). 800ms 디바운스로 서버에 쓰던 경로이고, 이제 서버 쓰기는 명시 저장 하나뿐이다.
//
//    이것이 검증 게이트 문제를 정리한다. 자동 저장을 V1–V5로 막으면 **타이핑 도중** 저장이
//    조용히 안 나가는 상태가 생기는데, 사람은 그 순간 저장을 기대하지 않았으므로 알 방법이
//    없다. 명시 저장은 그 문제가 없다 — 아무도 키를 치는 도중에 저장 버튼을 누르지 않는다.
//    그래서 지금은 V1–V5가 저장을 막고, 막힌 이유는 고칠 자리(행 옆)에 이미 떠 있다.
//
// 저장되지 않은 편집이 있는가. 화면이 이것을 보여줘야 한다 — 자동 저장이 있을 때는 아무도
// 궁금해할 필요가 없었지만 이제는 궁금해진다.
let legendDirty = false;

// 패널 헤더가 읽는 저장 상태 (판정은 위 한 곳에서만 만들어진다)
function getPlanSaveState() {
  const mapKey = getCurrentMapKey();
  if (legendConflict && legendConflict.table === selectedTable && legendConflict.mapKey === mapKey) {
    return { status: 'conflict', at: '', error: LEGEND_SAVE_MESSAGE.conflict, dirty: legendDirty };
  }
  return { ...legendSaveState, dirty: legendDirty };
}

// legend 변조의 단일 영속화 관문.
//
// 🔴 서버에 쓰지 않는다. 여기서 하는 일은 **초안 저장**뿐이다. 그리고 자동 저장이 사라진
//    지금, 그 초안이 세션과 작업 손실 사이에 서 있는 유일한 것이다 — 종전에는 저장 안 된
//    편집의 수명이 1초 미만이었지만 이제는 계획 하나를 짓는 시간 전체다.
function persistLegend() {
  legendDirty = true;
  frameTouched = true;   // [fix E] a legend commit is an edit of this frame
  saveLegendToStorage();
}

// ⚠️ 저장 버튼은 **만들지 않았다** (사용자 지시 2026-07-28: "어차피 push map data때 다
//    저장하잖아. 저장은 이거면 충분해"). `pushMapData`가 이미 유일한 서버 쓰기 경로이고,
//    이 파일이 스스로 그렇게 적어 두었다("규율 ①에 따라 Push 전에는 서버에 아무것도 쓰지
//    않는다"). 자동 저장은 그 규율을 어기고 있던 쪽이었다 — 지운 것이지 옮긴 것이 아니다.
//    저장을 위해 추가된 컨트롤은 **0개**다.

// ── 페인팅의 초안 저장 ────────────────────────────────
//
// 측정 결과(2026-07-28): **페인팅은 자동 저장을 타고 있지 않았다.** 셀은 `gridData`에 직접
// 쓰이고 `persistLegend`를 부르지 않으며, 서버로는 ⚡ Push로만 나간다. 그래서 자동 저장
// 제거가 페인팅에서 빼앗아 간 것은 없다 — 대신 **새로고침 생존("맵도")을 위해 없던 writer를
// 여기서 만든다.**
//
// 디바운스가 필요한 이유는 포커스가 아니라 양이다: 드래그 한 번에 수천 셀이 바뀌고, 셀마다
// localStorage에 쓰면 페인팅이 얼어붙는다.
let cellDraftTimer = null;
function scheduleCellDraft() {
  legendDirty = true;
  frameTouched = true;   // [fix E] a grid-cell write is an edit of this frame
  clearTimeout(cellDraftTimer);
  cellDraftTimer = setTimeout(() => { saveDoeDraft(); notifyLegendChanged(); }, 400);
}


// 행 DOM을 유지한 채 수정자·시각 라인만 갱신 (textarea 포커스 보존)
function renderLegendMetaOnly() {
  notifyLegendChanged();
  if (!el.legendList) return;
  el.legendList.querySelectorAll('.legend-row').forEach(row => {
    const line = row.querySelector('.legend-meta-line');
    if (line) line.textContent = formatLegendMetaText(legendMeta[row.dataset.value]);
  });
}

// [삭제됨] legend 마이그레이션 제안(`maybeOfferLegendMigration`).
//   맵을 여는 **읽기 경로**에 confirm 대화상자를 세웠고, 묻는 내용도 내부 개념("split registry")
//   이라 맵을 여는 사람에게 아무 의미가 없었다. 규율은 **읽기 무마찰 · 쓰기 1회 확인**이다.
//   대체 동작은 아래 loadExistingMap의 "registry 0건" 분기 — 묻지 않고 DOE를 깨끗이 초기화한다.
//   (`map_split_migrated_*` localStorage 플래그도 함께 폐기됐다.)

// [재설계 v2] 가시 legend UI는 우측 「2. Legend & DOE」 패널이 담당한다.
// 이 함수는 legend 변경을 패널에 통지하고, (남아 있다면) 구 테이블 DOM도 갱신한다.
function renderLegendTable() {
  notifyLegendChanged();
  // [N2] Overlay dots take their colour from the legend, so a legend edit has to recount the
  // overlay rows' "no legend colour" chip. (The canvas needs no hook: it reads the legend on
  // every paint, and every legend mutation already repaints it.)
  if (overlayLayers.length > 0) renderOverlayList();
  if (!el.legendList) {
    // 구 legend 테이블은 폐기됐다 — 활성 브러시 표기만 유지한다
    const item = legend.find(l => l.value === activeBrush);
    if (el.activeBrushVal) {
      el.activeBrushVal.textContent = item ? `${item.value} (${item.desc})` : 'None';
      el.activeBrushVal.style.color = item ? item.color : 'var(--text-dim)';
    }
    updateLegendCounts();
    return;
  }
  el.legendList.innerHTML = '';
  legend.forEach((item, index) => {
    const row = document.createElement('tr');
    row.className = 'legend-row';
    row.dataset.value = item.value;
    if (activeBrush === item.value) {
      row.classList.add('legend-row-active');
      el.activeBrushVal.textContent = `${item.value} (${item.desc})`;
      el.activeBrushVal.style.color = item.color;
    }

    row.addEventListener('click', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.classList.contains('btn-delete')) return;
      selectBrush(item.value);
    });

    // Value column
    const tdVal = document.createElement('td');
    const inputVal = document.createElement('input');
    inputVal.type = 'text';
    inputVal.className = 'glass-input';
    inputVal.style.padding = '6px 10px';
    inputVal.style.fontSize = '0.9rem';
    inputVal.style.width = '100%';
    inputVal.value = item.value;
    inputVal.addEventListener('change', (e) => {
      const oldVal = item.value;
      const newVal = e.target.value.trim();
      if (!newVal) {
        inputVal.value = oldVal;
        return;
      }
      // Check duplicate values
      const exists = legend.some((l, idx) => idx !== index && l.value === newVal);
      if (exists) {
        showToast('중복된 범례 값입니다.', 'warning');
        inputVal.value = oldVal;
        return;
      }
      item.value = newVal;
      // Remap grid values from oldVal to newVal
      remapGridValues(oldVal, newVal);
      if (activeBrush === oldVal) {
        activeBrush = newVal;
        row.dataset.value = newVal;
        el.activeBrushVal.textContent = `${newVal} (${item.desc})`;
      } else {
        row.dataset.value = newVal;
      }
      // 값 rename = registry에는 신규 bk 행 생성 (구 값 행은 서버에 이력으로 잔존)
      delete legendMeta[oldVal];
      persistLegend();
      renderGridCanvas();
    });
    tdVal.appendChild(inputVal);

    // [N2-b] 이 값이 **이 맵의 계획이 아니라 겹쳐 본 오버레이에서 들어온 것**이면 그렇게 적는다
    // (사용자 판정 2026-08-04). legend는 이 맵의 split registry를 서술하는 표이고, 맵이 담지
    // 않은 값을 담은 값과 구별 없이 늘어놓는 것은 맵에 대한 조용한 거짓 진술이다.
    // 컨트롤이 아니라 **글자**다 — 새 버튼·토글 0개, 글자 크기도 라벨 토큰 그대로다.
    const srcs = legendOverlaySources(item);
    if (srcs.length > 0) {
      const tag = document.createElement('span');
      tag.className = 'legend-src-tag';
      tag.textContent = srcs.length === 1
        ? `오버레이 · ${srcs[0]}`
        : `오버레이 · ${srcs[0]} 외 ${srcs.length - 1}`;
      tag.title = `오버레이 출처 ${srcs.join(' / ')} — 칠하기 전까지 [⚡ Push] 대상이 아닙니다.`;
      tdVal.appendChild(tag);
    }

    // Description column — 자연어 split 조건 서술 (여러 줄 textarea, 자동 확장)
    const tdDesc = document.createElement('td');
    const inputDesc = document.createElement('textarea');
    inputDesc.className = 'glass-input legend-desc-input';
    inputDesc.rows = 1;
    inputDesc.placeholder = '실험 split 조건 서술…';
    inputDesc.style.padding = '6px 10px';
    inputDesc.style.fontSize = '0.9rem';
    inputDesc.style.width = '100%';
    inputDesc.style.resize = 'none';
    inputDesc.style.overflow = 'hidden';
    inputDesc.style.lineHeight = '1.4';
    inputDesc.style.fontFamily = 'inherit';
    inputDesc.style.display = 'block';
    inputDesc.value = item.desc;
    const autoGrowDesc = () => {
      inputDesc.style.height = 'auto';
      inputDesc.style.height = `${Math.min(Math.max(inputDesc.scrollHeight, 32), 120)}px`;
    };
    inputDesc.addEventListener('input', autoGrowDesc);
    inputDesc.addEventListener('focus', autoGrowDesc);
    requestAnimationFrame(autoGrowDesc);
    inputDesc.addEventListener('change', (e) => {
      item.desc = e.target.value.trim();
      persistLegend();
      if (activeBrush === item.value) {
        el.activeBrushVal.textContent = `${item.value} (${item.desc})`;
      }
    });
    tdDesc.appendChild(inputDesc);

    // 마지막 수정자·시각 (서버 registry 메타 — 미저장 시 '서버 미저장')
    const metaLine = document.createElement('div');
    metaLine.className = 'legend-meta-line';
    metaLine.style.fontSize = '0.7rem';
    metaLine.style.color = 'var(--text-muted)';
    metaLine.style.marginTop = '3px';
    metaLine.style.whiteSpace = 'nowrap';
    metaLine.style.overflow = 'hidden';
    metaLine.style.textOverflow = 'ellipsis';
    metaLine.textContent = formatLegendMetaText(legendMeta[item.value]);
    tdDesc.appendChild(metaLine);

    // Color indicator and Picker column
    const tdColor = document.createElement('td');
    tdColor.style.textAlign = 'center';

    const colorIndicator = document.createElement('span');
    colorIndicator.className = 'legend-color-indicator';
    colorIndicator.style.backgroundColor = item.color;

    // Hidden color picker
    const colorInput = document.createElement('input');
    colorInput.type = 'color';
    colorInput.className = 'legend-color-input';
    colorInput.style.display = 'none';
    colorInput.value = item.color;

    colorIndicator.addEventListener('click', () => colorInput.click());
    colorInput.addEventListener('input', (e) => {
      const col = e.target.value;
      item.color = col;
      colorIndicator.style.backgroundColor = col;
      if (activeBrush === item.value) {
        el.activeBrushVal.style.color = col;
      }
      persistLegend();
      renderGridCanvas();
    });

    tdColor.appendChild(colorIndicator);
    tdColor.appendChild(colorInput);

    // Delete column
    const tdDel = document.createElement('td');
    const btnDel = document.createElement('button');
    btnDel.className = 'glass-page-btn btn-delete hover-danger';
    btnDel.style.padding = '2px 6px';
    btnDel.innerHTML = '&times;';
    btnDel.addEventListener('click', () => {
      if (legend.length <= 1) {
        showToast('최소 하나의 범례 정의가 필요합니다.', 'warning');
        return;
      }
      const deletedVal = item.value;
      legend.splice(index, 1);
      delete legendMeta[deletedVal]; // 서버 registry 행은 이력으로 잔존 (삭제 API 미사용)
      persistLegend();
      // Remove all elements in gridData matching deleted value
      Object.keys(gridData).forEach(k => {
        if (gridData[k] === deletedVal) gridData[k] = '';
      });
      if (activeBrush === deletedVal) {
        activeBrush = legend[0].value;
      }
      renderLegendTable();
      renderGridCanvas();
      scheduleCellDraft();
    });
    tdDel.appendChild(btnDel);

    // Count column
    const tdCount = document.createElement('td');
    tdCount.style.textAlign = 'center';
    tdCount.style.fontWeight = 'bold';
    tdCount.id = `legend-count-${item.value}`;
    tdCount.textContent = '0';
    tdCount.style.color = 'var(--text-muted)';

    row.appendChild(tdVal);
    row.appendChild(tdDesc);
    row.appendChild(tdCount);
    row.appendChild(tdColor);
    row.appendChild(tdDel);

    el.legendList.appendChild(row);
  });
  updateLegendCounts();
}

function selectBrush(val) {
  activeBrush = val;

  // Find matching legend item
  const item = legend.find(l => l.value === val);
  if (el.activeBrushVal) {
    if (item) {
      el.activeBrushVal.textContent = `${item.value} (${item.desc})`;
      el.activeBrushVal.style.color = item.color;
    } else {
      el.activeBrushVal.textContent = 'None';
      el.activeBrushVal.style.color = 'var(--text-dim)';
    }
  }
  // NO notifyLegendChanged() here. Selecting a brush changes no legend data, and the
  // panel renders nothing from the active brush - but notify triggers renderDoeList's
  // full innerHTML rebuild. The panel fires setBrush on MOUSEDOWN inside its rows, so
  // that rebuild used to destroy the very input being clicked before the browser could
  // focus it: the first click into any DOE field died ("클릭 반응이 굼뜨다").
  if (!el.legendList) return;

  // Toggle active styling on existing row elements without tearing down DOM
  const rows = el.legendList.querySelectorAll('.legend-row');
  rows.forEach(row => {
    if (row.dataset.value === val) {
      row.classList.add('legend-row-active');
    } else {
      row.classList.remove('legend-row-active');
    }
  });
}

// ── [재설계 v2] 「2. Legend & DOE」 패널이 쓰는 legend 변조 관문 ──────────
// legend 배열은 map_editor 소유다. 패널은 아래 3개 함수로만 변조하며,
// 영속화(로컬 캐시 + split registry 디바운스)와 캔버스 재렌더는 여기서 일괄 처리한다.
function addLegendRowForPanel() {
  let nextVal = 1;
  while (legend.some(item => String(item.value) === `D${nextVal}`)) nextVal++;
  const value = `D${nextVal}`;
  // [U6] Same auto-add path as every other new value (declared row → palette rule).
  autoAddLegendValue(value, '');
  persistLegend();
  renderLegendTable();
  return value;
}

function updateLegendRowForPanel(value, patch) {
  const item = legend.find(l => String(l.value) === String(value));
  if (!item || !patch) return { ok: false, error: 'legend 행을 찾을 수 없습니다.' };
  if (patch.value !== undefined) {
    const nv = String(patch.value).trim();
    if (!nv) return { ok: false, error: 'value는 비울 수 없습니다.' };
    if (nv !== String(item.value)) {
      if (legend.some(l => l !== item && String(l.value) === nv)) {
        return { ok: false, error: '중복된 value입니다.' };
      }
      const oldVal = String(item.value);
      item.value = nv;
      remapGridValues(oldVal, nv);
      if (activeBrush === oldVal) activeBrush = nv;
      delete legendMeta[oldVal];
      // 값 이름이 바뀌어도 bands/knobs는 같은 행에 그대로 붙어 있다 —
      // DOE가 값 행 자체이므로 별도 이사가 필요 없다(구 map_doe 시절엔 필요했다).
    }
  }
  if (patch.desc !== undefined) item.desc = String(patch.desc);
  if (patch.color !== undefined) item.color = String(patch.color);
  // The user typed into this row, so it is this map's - even if it arrived as a borrowed
  // vocabulary brush. Without this, an edit to such a row would be shown and silently
  // never saved.
  item.vocab = false;
  // DOE 필드는 패널이 만든 새 배열로 통째 교체한다 (제자리 수정 금지 — getLegend가 복사본이다)
  if (patch.knobs !== undefined) item.knobs = normalizeKnobs(patch.knobs);
  if (patch.stack !== undefined) item.stack = (patch.stack === null || patch.stack === undefined) ? '' : patch.stack;
  // The three zones are walked from ONE list, so a fourth zone (or a rename) cannot be
  // handled here and forgotten in the payload, the signature, or the renderer.
  ['mat_1h', 'mat_mid', 'mat_top'].forEach(z => {
    if (patch[z] !== undefined) item[z] = parseMaterialList(patch[z]);
  });
  // Any structural edit means the row is no longer the retired band arrangement we could
  // not express - the user has replaced it. Keeping the marker would block the save of a
  // row that is now perfectly expressible.
  if (patch.stack !== undefined || patch.mat_1h !== undefined || patch.mat_mid !== undefined || patch.mat_top !== undefined) {
    item.legacyBands = []; item.legacyReason = '';
  }
  persistLegend();
  renderLegendTable();
  renderGridCanvas();
  return { ok: true, value: String(item.value) };
}

function deleteLegendRowForPanel(value) {
  const idx = legend.findIndex(l => String(l.value) === String(value));
  if (idx < 0) return { ok: false, error: 'legend 행을 찾을 수 없습니다.' };
  if (legend.length <= 1) return { ok: false, error: '최소 하나의 정의가 필요합니다.' };
  const deletedVal = String(legend[idx].value);
  legend.splice(idx, 1);
  delete legendMeta[deletedVal];
  // The registry row goes away with the next legend save: that save is a
  // `replace_map` write of the whole legend, so a value dropped here is simply
  // absent from the set and the server purges it. See saveLegendToServer.
  Object.keys(gridData).forEach(k => { if (gridData[k] === deletedVal) gridData[k] = ''; });
  if (activeBrush === deletedVal) activeBrush = legend[0].value;
  persistLegend();
  renderLegendTable();
  renderGridCanvas();
  scheduleCellDraft();
  return { ok: true };
}

// 자재 맵 조회 헬퍼 (패널이 "맵 ✓ / 맵 없음"과 프레임 진입에 사용)
const mapKeyColumnCache = new Map();
// [7b] The cache now holds the DECLARED COLUMN TYPES alongside the key columns, because a
// map key cannot be canonicalised without them and both come from the same one request.
// `ok:false` means "could not confirm" — canonicalisation then degrades to trim-only, which
// is the pre-7b behaviour: it may miss, but it never invents a key.
async function fetchMapKeySpec(table) {
  if (mapKeyColumnCache.has(table)) return mapKeyColumnCache.get(table);
  try {
    const res = await fetch(`${API_BASE}/tables/${table}/schema`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const schema = await res.json();
    const spec = {
      ok: true,
      keyColumns: Array.isArray(schema.map_key_columns) ? schema.map_key_columns : [],
      columnTypes: (schema.column_types && typeof schema.column_types === 'object') ? schema.column_types : {},
    };
    mapKeyColumnCache.set(table, spec);   // 성공한 결과만 캐시한다
    return spec;
  } catch (e) {
    // [M5] 종전에는 실패 결과 []를 캐시에 박고 무효화하지 않아, 그 세션 내내
    // 해당 자재 맵이 "맵 없음"으로 오표시됐다. 실패는 캐시하지 않는다.
    console.warn(`[Map Editor] ${table} 스키마 조회 실패 — 캐시하지 않고 다음 호출에 재시도:`, e);
    return { ok: false, keyColumns: [], columnTypes: {} };
  }
}

async function fetchMapKeyColumns(table) {
  return (await fetchMapKeySpec(table)).keyColumns;
}

// 자재 맵 존재 여부. 조회 실패는 null(=미상)로 돌려준다 — "없음"으로 위장하지 않는다.
async function probeMapExists(table, metaValues) {
  try {
    const filters = {};
    Object.entries(metaValues || {}).forEach(([col, val]) => {
      if (val === null || val === undefined || String(val).trim() === '') return;
      filters[col] = { filterType: 'text', type: 'equals', filter: String(val) };
    });
    if (Object.keys(filters).length === 0) return null;
    const res = await fetch(`${API_BASE}/tables/${table}/data?limit=1&filters=${encodeURIComponent(JSON.stringify(filters))}`);
    if (!res.ok) return null;
    const result = await res.json();
    return !!(result && Array.isArray(result.data) && result.data.length > 0);
  } catch (e) {
    return null;
  }
}

function remapGridValues(oldVal, newVal) {
  Object.keys(gridData).forEach(k => {
    if (isProtectedFCell(k)) return;
    if (gridData[k] === oldVal) {
      gridData[k] = newVal;
    }
  });
  // 값 이름 변경도 셀을 바꾼다 — `persistLegend`는 legend만 저장하므로 초안의 cells는
  // 여기서 따로 갱신해야 새로고침 후에도 이름이 바뀐 채로 남는다.
  scheduleCellDraft();
}

// ----------------------------------------------------
// Load Map & Grid Actions
// ----------------------------------------------------

// [버그 수정] wafer_map_metadata는 **맵 하나가 아니라 (테이블, 맵 ID) 쌍**으로 식별된다.
// 같은 map_id가 여러 테이블에 존재할 수 있다(실측: map_id='AAA'가 bonding_map_AAA(0°)와
// test_AAA(270°) 두 행). 종전 코드는 `map_id`만으로 걸고 limit=1을 써서 **엉뚱한 테이블의
// 규격**을 집어왔고, 270° 맵이 0°로 로드되어 좌표가 격자 밖으로 삐져나갔다.
// → 반드시 target_table과 함께 건다. (map_pk = `<table>_<map_id>`도 같은 쌍의 표현이지만,
//    테이블명/맵ID에 '_'가 섞이면 분해가 모호해지므로 두 컬럼 동시 등가 필터가 정론이다.)
async function fetchGridMetaFor(table, mapId) {
  if (!table || !mapId) return null;
  const metaFilter = {
    target_table: { filterType: 'text', type: 'equals', filter: String(table) },
    map_id: { filterType: 'text', type: 'equals', filter: String(mapId) },
  };
  const res = await fetch(`${API_BASE}/tables/wafer_map_metadata/data?limit=2&filters=${encodeURIComponent(JSON.stringify(metaFilter))}`);
  // 🔴 [M2 fix] Same discipline as fetchPaintRules — distinguish "there is no declaration"
  //    from "we could not confirm". This used to return null on every failure, and the overlay
  //    path read that null as "spec not registered" and silently fell back to the on-screen
  //    frame (identity). A single 500 then placed markers at the wrong coordinates while the
  //    chip displayed "무보정 / 소스 맵 규격 미등록" — a reason that is simply false.
  //    · 404/405 → server has no such spec table. "No declaration" is the correct reading (null).
  //    · anything else → could not confirm. Throw and let the caller decide.
  if (res.status === 404 || res.status === 405) return null;
  if (!res.ok) throw new Error(`맵 규격 조회 실패 (HTTP ${res.status})`);
  const result = await res.json();
  const rows = (result && Array.isArray(result.data)) ? result.data : [];
  if (rows.length === 0) return null;
  if (rows.length > 1) {
    // 쌍으로 걸었는데도 2건 이상이면 서버 데이터가 중복된 것이다 — 조용히 첫 행을 쓰지 않는다
    // 화면에서 고칠 수 없는 서버 데이터 문제다 — 진단은 콘솔로 간다.
    console.log(`[Map Editor] wafer_map_metadata 중복: ${table} · ${mapId} — ${rows.length}건, 첫 행 적용`);
  }
  const metaStr = rows[0].data?.grid_metadata?.value;
  if (!metaStr) return null;
  try { return JSON.parse(metaStr); } catch (e) {
    console.warn('[Map Editor] grid_metadata 파싱 실패:', e);
    return null;
  }
}
// opts.quiet     — 완료/실패 alert 대신 토스트 (프레임 진입 등 자동 로드용)
// opts.allowEmpty — 0건이어도 실패로 보지 않고 빈 격자로 남긴다 (미구축 자재 맵)
// opts.restoreDraft — 미저장 초안을 화면에 되살린다. **기본값은 false: 맵을 로드하면
//                   로드한 맵이 나온다.** 사용자 신고(2026-08-06): 「맵 로딩하면 미저장
//                   초안 복구하지 말고 그냥 로딩한 걸로 다시 띄워, 초안 복구는
//                   새로고침할 때만」. 켜는 곳은 `restoreLastOpenMap`(부팅 복원) 하나뿐이다.
//
// 🔴 **`quiet`에 얹지 않는다.** `quiet`는 「차단형 대화상자를 띄우지 않는다」는 표시 결정이고,
//    복구는 데이터 결정이다. 얹으면 복구가 표시 플래그의 부작용이 되고, 다음에 조용한
//    호출부를 추가하는 사람이 자기가 내린 적 없는 복구 결정을 물려받는다. 호출부가
//    **의도를 말하게** 한다.
// 🔴 **적용하지 않는 것과 지우는 것은 다르다.** 초안은 `(table, mapKey)`로 키가 잡혀
//    그대로 남는다 — 맵 A를 편집하고 맵 B를 로드해도 A의 초안은 A의 키 아래 그대로다.
//
// ── The steps of a load ────────────────────────────────────────────────────────────────
// The seven `stepName()` calls below are module-scope functions defined immediately AFTER
// this one, in call order. Each one takes what it needs as an ARGUMENT and RETURNS a value:
// none of them reads or writes module state. Every module-state write on the load path is
// therefore in this function, where the sequence can be read on one screen.
//   ① collectMapKeyFilterModel       meta input boxes  -> the query filter
//   ② scanCoordinateBounds           response rows     -> the stored-coordinate bbox
//   ③ resolveDeclaredGridMeta        wafer_map_metadata -> the spec (unconfirmed = refuse)
//   ④ promptCoordinateChoice         no declaration    -> which coordinate system to use
//   ⑤ resolveGridFrame               that choice       -> cols/rows/START/rotation/side
//   ⑥ deriveLegendFromCellValues     the cells' values -> the legend rows
//   ⑦ restoreDoeDraftWithPrecedence  server baseline   -> which draft may be applied
// Three blocks resisted and stayed inline; each says why where it sits.
async function loadExistingMap(opts = {}) {
  const quiet = !!opts.quiet;
  const restoreDraft = !!opts.restoreDraft;
  // ── [fix E-3] 미저장 편집 가드 — **이 함수가 무엇이든 하기 전에** 묻는다 ─────────────
  //
  // 사용자 신고(2026-08-04): 유효 다이를 지정한 뒤 📂 Load Existing Map을 누르면 지정이
  // 조용히 풀린다. 아래 [M4①] 블록이 첫 세 줄에서 무조건 버리는데, 그 앞에 묻는 곳이
  // 없었다. 뒤로가기는 묻고 교체 로드는 묻지 않는, **같은 질문의 두 번째 철자** 문제다.
  //
  // 🔴 **[M4①]의 초기화를 약화시키지 않는다.** 그 블록의 이유는 옳다 — 이 로드가 어느
  //    경로로 끝나든 이전 맵의 마스크가 다른 맵을 주장하면 안 된다. 여기서 하는 일은
  //    「버리기 전에 묻는다」뿐이고, 승낙하면 그 초기화는 종전과 한 글자도 다르지 않게
  //    실행된다.
  // 🔴 **위치가 계약이다.** 필터 수집(`collectMapKeyFilterModel`)보다도, 버튼 라벨
  //    교체보다도, 요청보다도 앞이다. 이미 변하기 시작한 상태에 대해 묻는 확인창은
  //    사용자가 취소해도 되돌릴 것이 남는다. 거절은 **완전한 중단**이어야 한다.
  // 🔴 **`quiet`가 곧 「비대화형 호출」이다** — 새 플래그를 만들지 않는다. 이 파일에서
  //    `quiet`는 이미 "사용자에게 차단형 대화상자를 띄우지 않는다"는 뜻으로 쓰이고
  //    (아래 `hasFilter` 갈래의 `alert` ↔ `showToast`), 비대화형 호출부가 정확히 그
  //    플래그를 켜서 부른다. 두 호출부 모두 물을 이유가 없다:
  //      · `restoreLastOpenMap`(부팅 복원) — `init()` 중이라 사용자가 편집할 기회가
  //        아직 없었다. 있을 수 없는 편집을 두고 묻는 확인창이 된다.
  //      · `openMapFrame`(자재 프레임 진입) — 바로 앞에서 `snapshotEditorState()`가
  //        `validDie`·`frameTouched`·`framePushed`를 담아 프레임 스택에 넣었고, 복귀가
  //        그대로 되돌린다. **잃는 것이 없다.** 그리고 실제로 잃을 수 있는 지점인
  //        복귀에서는 `popMapFrame`이 같은 질문을 이미 한다.
  //    반환 형태는 위 `hasFilter` 거절과 **같다** — 호출부(`:641`)가 `r.cancelled`로
  //    이동 계측을 거르므로, 화면이 움직이지 않은 것이 그대로 계측에 반영된다.
  if (!quiet) {
    const notice = unsavedWorkNotice();
    if (notice && !confirm(
      `다른 맵을 불러오면 지금 화면의 편집이 사라집니다.\n\n` + notice +
      `\n[확인] 저장하지 않고 불러오기\n[취소] 이 화면에 남기`
    )) return { count: 0, cancelled: true };
  }
  // ⚠️ THE VALID-DIE DESIGNATION IS **NOT** WIPED ON THE WAY IN — CLEAR SITE 2 OF 3, DELETED.
  //    The [M4①] block that stood here dropped the mask in this function's first three
  //    statements, unconditionally, before a single byte had been read from the server. Its
  //    stated reason was "whichever way this load ends, a leftover mask must not claim to be
  //    ANOTHER map's valid die". Under the user's ruling that reason is inverted: the mask is
  //    not a leftover, it is the designation the user chose FOR the map they are about to
  //    open, and the load is the second half of one gesture.
  // 🔴 WHAT THIS BUYS ON THE FAILURE EXITS, which is what the old block was really for. It
  //    wiped FIRST so that every exit below (no map key · spec-read refusal · empty · the
  //    cancelled coordinate modal · the catch) landed on circle geometry. They now land on
  //    the user's own designation instead — a state they chose, not a state nobody chose. The
  //    strongest case is the very first exit (맵 키가 비어 있음): it returns before `gridData`
  //    is cleared, so cells are still on screen, and the wipe used to strip the designation
  //    from under them. That exit is now a complete no-op, which is what a refused load owes.
  // 🔴 The replacement it promised ("성공 경로는 아래에서 이 맵의 선언으로 다시 세운다") is
  //    still there and is now the ONLY writer — see the guarded `resolveValidDie` below. It
  //    fires exactly when the loaded map declares a valid die, and only then.

  const { filterModel, hasFilter } = collectMapKeyFilterModel();   // ①

  if (!hasFilter) {
    if (quiet) showToast('맵 키가 비어 있습니다.', 'warning');
    else alert('맵 키를 하나 이상 입력하십시오.');
    return { count: 0, cancelled: true };
  }

  const xCol = el.colMapX.value;
  const yCol = el.colMapY.value;
  const valCol = el.colMapVal.value;

  el.btnLoadMap.textContent = '📂 Loading...';
  el.btnLoadMap.disabled = true;

  const url = `${API_BASE}/tables/${selectedTable}/data?limit=2000&filters=${encodeURIComponent(JSON.stringify(filterModel))}`;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('API fetch failed');
    const result = await res.json();
    // [F4] Rows fetched vs cells parsed are different numbers: rows whose x/y are not
    // numeric under the SELECTED columns fall through the NaN filters below. When that
    // gap is total (N rows, 0 cells) the load must not read as a success — the almost
    // certain cause is a wrong x/y dropdown selection, and a green "0셀 로드 완료"
    // hides it.
    const fetchedRows = (result && Array.isArray(result.data)) ? result.data.length : 0;

    // Reset local cache & loaded F cells protection set
    gridData = {};
    loadedFCells.clear();
    // [F2b] 서버 셀 집합도 함께 버린다. 이 로드가 예외로 끝나면 기록은 null로 남고, null이면
    // 정리는 제공되지 않는다 — 앞 맵의 집합으로 이 맵의 셀을 "서버에 없다"고 판정하는 것이
    // 정확히 H2가 저지른 종류의 오답이다.
    serverCellKeys = null;
    // 기준 맵이 통째로 바뀌므로 이전 맵 기준으로 정렬된 오버레이는 무효다
    if (overlayLayers.length > 0) {
      // [1e] The load path is a read and reads stay frictionless. The release shows up as
      // the overlay block's count, and undoing it costs one [＋ 겹치기].
      console.debug(`[map] map replace released ${overlayLayers.length} overlay layer(s)`);
      clearOverlayLayers();
    }
    let count = 0;

    const { minX, minY, maxX, maxY } = scanCoordinateBounds(result, xCol, yCol);   // ②

    // ③ 선언 해석. **확인 실패는 선언 없음이 아니다** — 그 판정과 두 개의 중단 지점이 모두
    //   `resolveDeclaredGridMeta` 안에 있고, 여기서는 「중단이면 중단한다」만 읽으면 된다.
    const declared = await resolveDeclaredGridMeta(selectedTable, tableSchema, filterModel, result);
    if (!declared.ok) return declared.refusal;
    const loadedGridMeta = declared.gridMeta;
    const loadedMapKey = declared.mapKey; // split registry 적용을 위해 맵 식별자를 함수 스코프로 유지

    // [F5c] 저장된 규격이 **없을 때만** 라우팅에 묻는다. 절대 순서
    // `wafer_map_metadata` > 라우팅 > 패널의 첫 번째 부등호가 이 한 줄의 가드다
    // (INV-F5c-2). 여기가 이 함수의 **유일한** 호출부이므로 로드당 정확히 1회다
    // (INV-F5c-3). 셀 좌표 해석보다 앞에 두는 이유: 아래 'current'/'standard' 분기가
    // 좌측 패널을 읽으므로, 라우팅이 패널을 정한 뒤여야 "라우팅 > 패널"이 성립한다.
    if (!loadedGridMeta) {
      await applyRoutedPreset(selectedTable, loadedMapKey || getCurrentMapKey());
    }

    let userChoice = null; // 'standard' | 'current' | 'meta'

    // 자동 로드(프레임 진입)에서 조회 결과가 0건이면 좌표계 선택 모달을 띄우지 않는다 —
    // 아직 만들지 않은 자재 맵이므로 물어볼 좌표가 없다.
    if (opts.allowEmpty && minX === 9999 && !loadedGridMeta) {
      // [F4] "not built yet" is only true when the table really had no rows. Rows that
      // exist but yielded no parseable coordinate are a column-selection problem and
      // must be said out loud, not folded into "empty map".
      if (fetchedRows > 0) {
        showToast(`${selectedTable}: ${fetchedRows}행 중 좌표로 읽힌 셀 0개 — X/Y 컬럼을 확인하십시오.`,
          'warning');
      }
      return { count: 0, empty: true };
    }

    if (!loadedGridMeta && minX !== 9999) {
      // Choice modal triggers for maps with no grid metadata records
      userChoice = await promptCoordinateChoice(el);   // ④

      if (userChoice === 'cancel') {
        el.btnLoadMap.textContent = '📂 Load Existing Map';
        el.btnLoadMap.disabled = false;
        return { count: 0, cancelled: true };
      }
    } else if (loadedGridMeta) {
      userChoice = 'meta';
    } else {
      userChoice = 'current';
    }

    // ⑤ Determine grid properties based on choice
    const resolvedFrame =
      resolveGridFrame(userChoice, loadedGridMeta, minX, minY, maxX, maxY, el, currentRotation, currentSide);
    // 🔴 `null` = 고를 수 없는 선택지였다(패널의 칸이 비어 있다, §`readGridFrameControls`).
    //    취소와 **같은 자리**로 접는다: 새 분기도 새 상태도 만들지 않고, 사유는 이미 말했다.
    if (!resolvedFrame) {
      el.btnLoadMap.textContent = '📂 Load Existing Map';
      el.btnLoadMap.disabled = false;
      return { count: 0, cancelled: true };
    }
    let { cols, rows, startX, startY, invertY, rotation, side } = resolvedFrame;
    // ⚠️ `resolveGridFrame` owns no module state, so the `meta` branch's cache
    //    invalidation is issued here — the same statement at the same point in the
    //    sequence (nothing between here and the unconditional invalidate below reads it).
    if (userChoice === 'meta') boundingBoxCache = {};

    // Sync state variables and input values back to UI panel BEFORE mapping cell coordinates
    el.gridCols.value = cols;
    el.gridRows.value = rows;
    el.gridStartX.value = startX;
    el.gridStartY.value = startY;
    el.gridYInvert.checked = invertY;
    currentRotation = rotation;
    currentSide = side;
    boundingBoxCache = {}; // Invalidate bounding box cache so getWaferBoundingBox calculates with new dimensions

    // [부수 수정] 회전 버튼·면 라디오·**툴바 FRONT/BACK 칩**을 한 번에 동기화한다.
    // 종전에는 라디오만 갱신하고 `updateSideIndicator()`를 부르지 않아,
    // side=back인 맵을 로드해도 툴바 칩이 "FRONT · 앞면"으로 남아 **거짓 표기**가 됐다.
    // (라디오 해제도 하지 않아 이전 선택이 남는 경로도 있었다 — updateOrientationUI가 둘 다 처리한다.)
    updateOrientationUI();

    // ═══ 유효 다이 → 오리진 → 셀 위치. 이 순서가 사용자 지시다(2026-07-30) ═════════════
    // 「유효 다이맵은 현재 회전 반전 세팅으로 가져오고 거기서 오리진 다시 계산해서 셀 위치 계산」
    //
    // 🔴 **셀을 한 칸도 놓기 전에** 끝나야 한다. 아래 루프는 `getCanvasCellFromDb`로 셀을
    //    배치하고 렌더는 `getDbCoords`로 좌표를 되만드는데, 그 둘은 **같은 원점 상자에서만**
    //    역함수다(§getWaferBoundingBox). 마스크가 셀 배치 뒤에 앉으면 배치는 원 기준으로,
    //    표기와 Push는 유효 다이 기준으로 계산되어 저장 좌표가 조용히 옮겨간다.
    //    종전에는 이 호출이 렌더 직전(약 200줄 아래)에 있었다 — 마스크가 판정에만 쓰이던
    //    동안에는 충분했지만, 이제 마스크가 좌표계를 정하므로 그 자리는 늦다.
    //
    // 🔴 회전·면·격자 컨트롤이 **위에서 이미 확정된 뒤**여야 한다(바로 위 동기화 블록):
    //    정렬 경보가 `currentFrame()`을 읽어 참조 프레임과 원점을 비교한다.
    // ── CLEAR SITE 3 OF 3, GUARDED. This is the one that survives naive fixes. ───────────
    // Deleting the two direct wipes above is NOT enough, and measuring that was the whole
    // point: with both of them suppressed the control was still blanked, because this call
    // reaches `set('circle', null, '', null)` whenever `parseValidDieRef` answers null, and
    // `set` ends with `syncValidDieRefControls()`. The wipe arrived through the resolver.
    //
    // 🔴 WHAT COUNTS AS "이 맵이 고유 메타를 가졌다" — the ruling is decided HERE, once, and
    //    it is decided by the function that already owns that word. `parseValidDieRef`
    //    returns null for **absence only** (no meta object · no `valid_die_ref` key · the key
    //    present but null/undefined) and returns a declaration for everything else, an
    //    unreadable one included ("null/부재만 선언 없음이고 그 외에는 전부 선언이다", §2287).
    //    So a `wafer_map_metadata` row that says nothing about valid-die is treated exactly
    //    like no row at all — both leave the user's designation standing. That is the
    //    intended reading: the user is mid-setup, matching geometry by hand, and a row that
    //    is silent on valid-die has not declared anything to replace it with.
    //    An UNREADABLE declaration still replaces (with a refusal): the map did declare, and
    //    silently keeping the previous mask there would be the "wrong answer indistinguish-
    //    able from the right one" state this file refuses everywhere else.
    // 🔴 **NO SECOND SPELLING.** The predicate is one call to the same pure function the
    //    resolver itself calls with the same two arguments — not a re-implementation of
    //    "does this meta declare a valid die". Two spellings of one predicate is how the two
    //    unsaved-work doors came to disagree (§unsavedWorkNotice), and it is not repeated.
    // 🔴 ORDERING IS UNCHANGED. Whatever survives is settled before the cell placement loop —
    //    strictly earlier than before, in fact, since a carried designation was already
    //    settled when the load began. That matters because `getWaferBoundingBox` keys the
    //    origin box off `basis === 'ref'`, so a carried designation moves where cells land.
    //    That is the requested behaviour, not a side effect: the user picked the mask for
    //    this map. `cols`/`rows` are still re-read below for the declared case.
    if (parseValidDieRef(loadedGridMeta, selectedTable) !== null) {
      await resolveValidDie(loadedGridMeta, selectedTable, loadedMapKey || getCurrentMapKey());
    }
    // 근거가 바뀌면 원점 상자도 바뀐다 — 위 동기화가 비운 캐시는 원 기준으로 다시 채워졌을
    // 수 있다. 태그가 키를 갈라 주지만, 여기서 한 번 더 비워 이전 맵의 항목을 남기지 않는다.
    boundingBoxCache = {};
    // 🔴 [규칙 ①-b] **치수를 되읽는다.** 유효 다이 해석이 참조의 규격을 들여오면서 격자를
    //    그 규격에서 다시 파생시켰을 수 있다(§set의 (a)/(b)). 아래 셀 배치 루프와 그 뒤의
    //    `getDieIndex`가 **옛 치수**로 돌면, 렌더는 새 치수로 좌표를 되만드는데 배치는
    //    옛 치수로 이뤄져 저장 좌표가 조용히 옮겨간다 ― 화면은 멀쩡한데 값이 틀린 그 상태다.
    //    (읽는 지점은 `renderGridCanvas`·`currentFrame`과 같은 컨트롤 하나뿐이다.)
    // ⚠️ START X,Y는 되읽지 않는다 — 아무도 덮어쓰지 않는다(바로 아래 주석).
    cols = gridDimNum(null, 'cols', el.gridCols, 10);
    rows = gridDimNum(null, 'rows', el.gridRows, 10);
    // ⚠️ 여기서 START X,Y를 컨트롤에서 되읽지 **않는다.** 되읽는 줄이 잠시 있었는데, 그것은
    //    `resolveValidDie`가 START를 덮어쓰던 (B) 안의 잔재였다. 사용자 확정은 (A)다 ―
    //    「START X,Y는 바뀌면 안됨」. 아무도 덮어쓰지 않으므로 지역 변수 `startX`와 컨트롤은
    //    이미 같은 값이고, 되읽기는 DOM에서 같은 수를 두 번째로 만들어 내는 일일 뿐이다.

    const uniqueVals = new Set();

    if (result && result.data) {
      result.data.forEach(row => {
        const rowData = row.data || {};
        const xVal = rowData[xCol]?.value;
        const yVal = rowData[yCol]?.value;
        const val = rowData[valCol]?.value;

        if (xVal !== undefined && yVal !== undefined) {
          let xNum = parseInt(xVal, 10);
          let yNum = parseInt(yVal, 10);
          if (!isNaN(xNum) && !isNaN(yNum)) {
            const strVal = val !== null ? String(val).trim() : '';
            count++;

            if (strVal !== '') {
              uniqueVals.add(strVal);
            }

            // 🔴 NO SHIFT. A cell is placed where its STORED coordinate says — the frame's
            //    origin (`startX`/`startY`, set to the data's minimum for the 📐 표준 choice
            //    above) carries the offset, and `getCanvasCellFromDb` applies it. The
            //    deleted `xNum -= minX` renumbered the cell instead, which the frame then had
            //    no record of, so Push wrote the renumbered coordinate back.
            const cell = getCanvasCellFromDb(null, xNum, yNum, cols, rows, rotation, side, invertY, startX, startY);
            const c = cell.c;
            const r = cell.r;

            const physical = getDieIndex(null, c, r, cols, rows, rotation, side);
            const gridKey = `${physical.x}_${physical.y}`;
            gridData[gridKey] = strVal;

            // 잠금 판정은 config 관문(isLockedValue)만 사용 — 값 하드코딩 금지
            if (isLockedValue(strVal)) {
              loadedFCells.add(gridKey);
            }
          }
        }
      });
    }

    // [F2b] 서버가 이 맵으로 돌려준 셀 키를 여기서 붙든다 — `gridData`가 **정확히 서버의
    // 답**인 유일한 지점이다(초안 복원·페인트는 아직 지나지 않았다).
    // 🔴 절단된 응답은 불완전한 집합이므로 **모른다로 강등한다**(불변식 ④): 상한을 넘긴
    //    맵에서 "서버에 없다"는 판정은 거짓이 될 수 있고, 그 거짓 위에서 정리하면 실재하는
    //    행이 다음 Push에서 삭제된다. split registry 조회가 절단을 실패로 강등하는 것과
    //    같은 규칙이다(readRegistryScope).
    const cellsTruncated = !!(result && typeof result.total === 'number'
      && result.total > (Array.isArray(result.data) ? result.data.length : 0));
    if (cellsTruncated) {
      console.warn(`[Map Editor] cell load truncated (${result.total} > ${result.data.length}) — `
        + 'server cell set demoted to unknown; outside-wafer cleanup will not be offered');
    } else {
      serverCellKeys = {
        table: selectedTable,
        mapKey: loadedMapKey || getCurrentMapKey(),
        keys: new Set(Object.keys(gridData)),
      };
    }

    // Auto detect legend from unique values
    if (uniqueVals.size > 0) {
      // ⑥ [U6] the one palette — no second copy
      const newLegend = deriveLegendFromCellValues(uniqueVals, legend, LEGEND_PALETTE);

      // Update legend array and rebuild the legend table. Deliberately NOT persisted here:
      // saveLegendToStorage() -> saveDoeDraft() at this point would overwrite this map's
      // draft with the just-loaded SERVER state (cells included, base fingerprints not yet
      // established) BEFORE the draft-precedence block below has read it - that destroyed
      // every painted-cell draft on reload (H1, 2026-07-28). The load path persists once,
      // inside the registry block below, after the draft has been read and applied.
      legend = newLegend;

      // Auto select the first legend item as the active brush
      if (legend.length > 0) {
        activeBrush = legend[0].value;
      } else {
        activeBrush = '';
      }
      renderLegendTable();
    }

    // [fix B] The unsaved-edit flag is per-map state: a successful load re-establishes
    // it from scratch. Without this reset, map A's flag survived into map B and the
    // header chip read "● 저장 안 됨" on a map with zero edits. Order matters: the
    // draft restores below (both registry branches) re-mark it AFTER this line, so a
    // restored draft still shows as unsaved — exactly the H1 guarantee.
    legendDirty = false;
    // [Split Registry] 서버에 기록된 이 맵의 split 서술·색을 최우선 적용.
    // 값 일치 항목은 override, 그리드에 없지만 registry에 정의된 값은 브러시로 추가 노출.
    legendReplaceScope = null;   // the claim below is about to be re-established, or lost
    if (loadedMapKey) {
      const read = await readRegistryScope(selectedTable, loadedMapKey);
      if (read.ok) {
        // Read succeeded (0 rows is a complete answer too), so the on-screen legend is
        // now this map's registry merged into it: it may replace this map's rows, and
        // what we just read is the baseline the concurrency check compares against.
        // 값·색뿐 아니라 **이 맵에 없는 값의 knobs/bands를 비우는 것**까지
        // applyRegistryRowsToLegend 한 곳에서 한다 (앞 맵의 스택 잔재 차단).
        //
        // [U6-1] A 0-cell load on the SAME table skips the paint-derived legend rebuild
        // above (`uniqueVals.size > 0` guard), so the previous map's non-vocab rows are
        // still on screen here and apply() would keep them — the new map inherited the
        // old plan (QA repro: AAA's F/2/D1/D2 shown for QA_EMPTY_U6). Reset to the seed
        // arm first, exactly what the table-switch flow does; apply() then merges the
        // registry answer into THIS map's baseline. Only here, under read.ok: a FAILED
        // read must keep the screen as-is (unknown-server-state is not "empty"), and
        // the draft-precedence block below still runs after and wins as before.
        if (uniqueVals.size === 0) seedEmptyDoe();
        applyRegistryRowsToLegend(read.rows);
        const serverFp = registryFingerprint(read.rows);
        const serverCellsFp = cellsDigest(gridData);
        legendReplaceScope = { table: selectedTable, mapKey: loadedMapKey, fingerprint: serverFp };
        legendConflict = null;          // 화면이 다시 서버본에서 유래한다
        legendSaveState = { status: 'idle', at: '', error: '' };
        // 이 지점이 초안의 **기반**이다: 지금 서버가 갖고 있는 것.
        draftBase = { table: selectedTable, mapKey: loadedMapKey, registryFp: serverFp, cellsFp: serverCellsFp };

        // ⑦ 초안 우선순위 — 기반 지문 대조와 두 개의 토스트는
        //    `restoreDoeDraftWithPrecedence` 안에 있다. 여기서는 그 답이 두 개의
        //    모듈 상태(legendDirty · 아래 persist)에 어떻게 닿는지만 읽으면 된다.
        // 🔴 초안 복구는 **부팅 복원에서만** 일어난다(§opts.restoreDraft). 평범한 로드는
        //    방금 읽은 서버본을 그대로 보여 준다 — 「로드한 맵이 나온다」가 계약이다.
        //    초안은 지우지 않는다: 이 맵의 키 아래 그대로 남아 다음 새로고침이 되살린다.
          //   🔴 `staleDraftKept: true` — AND IT IS LOAD-BEARING, NOT COSMETIC.
          //      `staleDraftKept` reads like a description ("a stale draft was kept") but the
          //      ONLY thing it does is `if (!staleDraftKept) saveLegendToStorage()` below, and
          //      that persist RE-BASELINES this map's draft slot to the server state just read.
          //      Skipping the restore puts us in exactly the situation the flag exists for:
          //      a draft may hold content and we did NOT apply it. Reporting `false` here let
          //      the persist run and **overwrite the operator's unsaved edits with the server
          //      copy** — deleting the very draft this change promised to keep, and closing the
          //      refresh that was supposed to recover it (measured 2026-08-06: slot A lost
          //      `9_1`, `10_2` on a plain load).
          //   ⚠️ Gating a step does not gate what its RETURN VALUE feeds. This value reaches a
          //      persist, not just a toast.
        const restored = restoreDraft
          ? restoreDoeDraftWithPrecedence(selectedTable, loadedMapKey, serverFp, serverCellsFp)
          : { restoredUnsavedEdits: false, staleDraftKept: true };
        // Restored edits are still unsaved edits - they exist only in this browser
        // until [⚡ Push]. Without this the chip reads "saved" after the very refresh
        // the draft just survived.
        if (restored.restoredUnsavedEdits) legendDirty = true;
        const staleDraftKept = restored.staleDraftKept;   // [fix A] see the persist below
        // [fix A] This persist re-baselines the draft slot to the just-loaded server
        // state. In the stale-mismatch case that overwrote the very draft the toast
        // above had just promised to keep ("초안은 지우지 않았습니다") — and the
        // priority contract at saveDoeDraft (지문 불일치 → 적용하지 않되 버리지도
        // 않는다) says the draft stays in storage, where the registry-read-failure
        // path below can still surface it. Keep the promise: skip the persist while a
        // stale draft is being preserved. (The user's next edit legitimately
        // overwrites the slot — a single draft slot protects the newest edits.)
        if (!staleDraftKept) saveLegendToStorage();
        renderLegendTable();
      } else {
        // Read failed or was truncated -> the on-screen legend is NOT this map's
        // registry, so it must never replace it, and it must not be upserted over
        // either: the row now carries the plan. Keep the local DOE draft on screen so
        // the user's typing is not lost, and say plainly that saving is on hold.
        legendReplaceScope = null;
        // 비교할 서버본이 없다. 기반 지문을 검사할 수 없으므로 초안을 보여주되, 이 화면은
        // 서버본에서 유래하지 않았으므로 `draftBase`는 세우지 않는다 — 이 상태에서 뜬 초안은
        // 다음 로드에서 "기반 미상"이 되어 서버 조회 성공 시 적용되지 않는다. 그게 맞다.
        draftBase = null;
        const draft = readDoeDraft(selectedTable, loadedMapKey);
        const hadDraft = draft ? applyDoeDraftRecord(draft) : false;
        const hadDraftCells = (draft && draft.cells) ? applyDraftCells(draft.cells) > 0 : false;
        // [fix B] the reset above must not leave the chip claiming "saved" for draft
        // content the server never received — same honesty as the read-ok branch.
        if (hadDraft || hadDraftCells) legendDirty = true;
        legendSaveState = { status: 'unknown-server-state', at: '', error: read.error || '' };
        renderLegendTable();
        console.warn('[Map Editor] split registry apply skipped:', read.error);
        showToast(`DOE registry 조회 실패로 서버 저장 보류${hadDraft ? ' (초안 표시 중)' : ''} — 맵을 다시 여십시오.`,
          'warning', { dedupeKey: 'legend_registry_load_failed' });
      }
    }

    // [M4①] 유효 다이의 근거는 **셀 배치 전에** 이미 정해졌다(위 「유효 다이 → 오리진 →
    // 셀 위치」 블록). 여기서 다시 부르지 않는다 — 두 번 해석하면 늦게 착지한 쪽이 원점 상자를
    // 바꿔, 이미 배치된 셀과 다른 좌표계로 렌더가 돌아간다.
    // [M4②] 홈 키를 함께 넘기는 이유(자기 참조 A→A 차단)와 `setLoadedIdentity`보다 앞선다는
    // 사실도 그 블록에 적혀 있다.
    renderGridCanvas();
    // [가드 ①] 로드 순간 편집 정체성을 고정하고 맵 키 입력을 잠근다.
    setLoadedIdentity(selectedTable, loadedMapKey || getCurrentMapKey());
    // [F4] `serverRead` — this line is where the server was JUST READ. Re-loading the same
    // map leaves the identity unchanged, so the panel's `changed` test alone never refreshed
    // its derived columns (material-map presence, availability). Measured: a reload fired 0
    // existence probes, so a material with 261 rows on the server kept reading `MAP X`.
    notifyMapContext({ serverRead: true });
    recordLastOpenMap();   // refresh returns here (no-op inside a material frame)
    // [F4] N rows fetched but 0 cells parsed = the NaN filter dropped everything —
    // warn with the likely cause instead of a green success naming "0셀".
    if (fetchedRows > 0 && count === 0) {
      showToast(`${selectedTable}: ${fetchedRows}행 중 좌표로 읽힌 셀 0개 — X/Y 컬럼을 확인하십시오.`,
        'warning');
    } else {
      // [1e] A successful load IS the screen: the grid renders, the legend badges and the
      // DOE 「칠함」 column carry the cell counts, and the identity chip names table + map key.
      // Nothing to add on a read path. Failure and partial failure are still toasted by the
      // two branches above and by the catch.
      console.debug(`[map] loaded ${selectedTable} · ${loadedMapKey || ''} — ${count} cells`);
    }
    return { count, mapKey: loadedMapKey };
  } catch (err) {
    console.error(err);
    if (quiet) showToast('맵 로드 실패 — 테이블·맵 키를 확인하십시오.', 'error');
    else alert('맵 로드 실패 — 테이블·맵 키를 확인하십시오.');
    return { count: 0, error: true };
  } finally {
    el.btnLoadMap.textContent = '📂 Load Existing Map';
    el.btnLoadMap.disabled = false;
  }
}

// ══ The steps of loadExistingMap ═════════════════════════════════════════════════════════
// In call order. NONE of these reads or writes module state: everything they need arrives as
// an argument and everything they decide leaves as a return value. That is not decoration —
// it is what lets the reader of `loadExistingMap` above see every module-state write on the
// load path without opening any of them, and it is what would let one of them move to its own
// file later without an accessor pair.
// ═════════════════════════════════════════════════════════════════════════════════════════

// ① 메타 입력칸 → 조회 필터. 값이 하나도 없으면 `hasFilter === false`이고, 호출부가
//    「맵 키가 비었다」로 되돌린다 — 여기서는 판정하지 않는다.
function collectMapKeyFilterModel() {
  const filterModel = {};
  const metaInputs = document.querySelectorAll('[id^="meta-input-"]');
  let hasFilter = false;

  metaInputs.forEach(input => {
    const col = input.id.replace('meta-input-', '');
    const val = input.value.trim();
    if (val) {
      hasFilter = true;
      filterModel[col] = {
        filterType: 'text',
        type: 'equals',
        filter: val
      };
    }
  });

  return { filterModel, hasFilter };
}

// ② 응답 행 → 저장 좌표의 bbox. 파싱되는 셀이 하나도 없으면 초기 센티넬(minX 9999)이 그대로
//    돌아가고, 호출부는 그 값으로 「해석된 셀 0개」를 가른다. 센티넬은 계약의 일부다.
function scanCoordinateBounds(result, xCol, yCol) {
  // Pre-calculate coordinate bounds first
  let maxX = -9999;
  let maxY = -9999;
  let minX = 9999;
  let minY = 9999;

  if (result && result.data) {
    result.data.forEach(row => {
      const rowData = row.data || {};
      const xVal = rowData[xCol]?.value;
      const yVal = rowData[yCol]?.value;
      if (xVal !== undefined && yVal !== undefined) {
        const xNum = parseInt(xVal, 10);
        const yNum = parseInt(yVal, 10);
        if (!isNaN(xNum) && !isNaN(yNum)) {
          if (xNum > maxX) maxX = xNum;
          if (yNum > maxY) maxY = yNum;
          if (xNum < minX) minX = xNum;
          if (yNum < minY) minY = yNum;
        }
      }
    });
  }

  return { minX, minY, maxX, maxY };
}

// ③ wafer_map_metadata 해석 → `{ ok: true, gridMeta, mapKey }`,
//    또는 확인 실패 시 `{ ok: false, refusal }` (호출부가 그 값을 그대로 반환한다).
async function resolveDeclaredGridMeta(selectedTable, tableSchema, filterModel, result) {
  let loadedGridMeta = null;
  let loadedMapKey = null; // split registry 적용을 위해 맵 식별자를 함수 스코프로 유지

  // 🔴 **"확인 못 했다"는 "선언이 없다"가 아니다.** `fetchGridMetaFor`는 404/405만 "선언
  //    없음"(null)으로 답하고 나머지는 **던진다** — 그 규율이 여기서 끝나면 안 된다. 아래
  //    한 자리로 모아 두는 이유는, 읽지 못한 선언이 흘러가 닿는 곳이 하나이기 때문이다:
  //    `loadedGridMeta = null` → 「선언 없는 맵」 → 좌표계 선택 모달 → 📐 표준이 START와
  //    격자를 **데이터 bbox로 재선언**하고, `pushMapData`가 그 값을 `grid_start_x/y`에
  //    **영속화**한다. 표시만 틀리는 것이 아니라 저장된 정렬 기준이 바뀐다.
  //    실측(HTTP 500을 정확히 1회 주입): 선언 (1,-6)·21x21 맵이 (5,-1)·8x7이 되고 46셀 중
  //    **41셀이 다른 물리 다이**에 앉았으며 토스트는 **0건**이었다.
  const refuseUnconfirmedMeta = (reason, err) => {
    console.error(`[Map Editor] wafer_map_metadata could not be confirmed for `
      + `${selectedTable} · ${loadedMapKey || ''} (${reason}) — refusing the load. An `
      + 'unconfirmed declaration must NOT be read as an absent one: the 📐 표준 branch '
      + 'would re-declare grid_start_x/y to the data bounding box and ⚡ Push would '
      + 'persist it.', err || '');
    showToast(`맵 규격 미확인으로 로드 중단 — ${reason}. 잠시 후 다시 시도하십시오.`, 'error');
    return { count: 0, error: true, metaUnconfirmed: true };
  };

  // 1. Try fetching from dedicated wafer_map_metadata table
  let metaReadError = null;
  try {
    const filterMetaDict = {};
    Object.keys(filterModel).forEach(col => {
      if (filterModel[col] && filterModel[col].filter) {
        filterMetaDict[col] = filterModel[col].filter;
      }
    });
    const mapIdStr = getMapIdFromMeta(filterMetaDict, tableSchema);
    if (mapIdStr && mapIdStr !== 'default_map') {
      loadedMapKey = mapIdStr;
      // ⚠️ 조회의 실패만 여기서 붙든다. 바깥 catch는 `getMapIdFromMeta`처럼 조회가 **아닌**
      //    것의 실패를 위한 자리이고, 그것은 종전대로 "선언 없음"으로 흘러간다.
      try {
        loadedGridMeta = await fetchGridMetaFor(selectedTable, mapIdStr);
      } catch (e) {
        metaReadError = e;
      }
    }
  } catch (e) {
    console.warn('[Map Editor] Dedicated wafer_map_metadata table fetch skipped:', e);
  }

  // 🔴 셀 레벨 폴백보다 **앞이다.** 조회 1회 실패를 폐기 스킴(`grid_metadata`)으로 메우는
  //    것도 "확인 못 한 것을 확인한 것처럼 쓰는" 같은 동작이다(불변식 ②).
  if (metaReadError) {
    // ⚠️ 사유는 `fetchGridMetaFor`가 던진 문구를 **그대로** 쓴다. 여기서 한 겹 더 감싸면
    //    「규격 조회 실패 (맵 규격 조회 실패 (HTTP 500))」처럼 같은 말이 두 번 나온다.
    return { ok: false, refusal: refuseUnconfirmedMeta(
      (metaReadError && metaReadError.message) ? metaReadError.message : '맵 규격 조회 실패',
      metaReadError) };
  }

  // 2. Fallback to cell-level grid_metadata
  if (!loadedGridMeta && result && result.data) {
    const firstWithMeta = result.data.find(row => row.data && row.data['grid_metadata'] && row.data['grid_metadata'].value);
    if (firstWithMeta) {
      try {
        loadedGridMeta = JSON.parse(firstWithMeta.data['grid_metadata'].value);
      } catch (e) {
        console.error('Failed to parse fallback grid_metadata:', e);
      }
    }
  }

  // 🔴 **선언이 있는데 START를 읽을 수 없다 → 선언이 아예 없는 맵과 같은 곳으로 보낸다**
  //    (총괄 판정 2026-08-05). 그 자리는 아래 ④ **좌표계 선택 모달**이다.
  //
  //    지켜야 하는 것은 「모르면 0」이라는 조용한 번역을 막는 것 하나뿐이고, 모달은 거절과
  //    **최소한 같은 정도로** 그것을 막으면서 맵을 열어 둔다. 운영자가 에디터를 여는 이유가
  //    바로 규격을 모르기 때문이므로, 열리지 않는 것은 답이 아니다.
  //    실측(2026-08-05, `push_after_choice_probe`):
  //      · `grid_start_x` 키 부재 → 종전 44셀이 `NaN_NaN` **한 칸**으로 접혔다.
  //      · `grid_start_x: null`  → NaN이 하나도 없이 44셀이 **전부 다른 칸**에 앉았고
  //        (`Number(null) === 0`), 로드는 성공을 알렸으며 ⚡ Push가 `grid_start_x: 0`을
  //        `wafer_map_metadata`에 **영속화**했다. 토스트는 0건. 이쪽이 더 위험하다 —
  //        화면이 멀쩡하다.
  //    모달 경로에는 그 두 결함이 **원리적으로** 없다: 좌표계를 정하는 것이 선언이 아니라
  //    운영자의 선택이고, 두 선택지 모두 읽을 수 있는 수를 낸다(📐 표준 = 데이터 bbox,
  //    현재 설정 = 화면 컨트롤). 그리고 고른 프레임은 로드 직후 좌측 패널에 **그대로 표시**
  //    되므로 Push 전에 눈에 보인다.
  //
  // 🔴 **`refuseUnconfirmedMeta`(조회 실패)와 같은 자리로 보내지 않는다 — 두 사실은 다르다.**
  //    조회 실패는 선언이 **무엇인지 모르는** 상태라, 고른 프레임을 Push가 쓰면 실재하는
  //    선언을 덮는다. 여기서는 선언을 **읽었고** 그 선언에 원점이 없다는 것을 안다.
  //
  // 🔴 **메타를 반쯤 살려 두지 않는다.** 원점 없는 `grid_cols`/`rotation`을 운영자가 고른
  //    원점과 섞으면 아무도 선언한 적 없고 아무도 고른 적 없는 프레임이 나온다 — 이 파일이
  //    도처에서 거절하는 그 상태다. 그래서 `null`을 돌려 **아래 경로가 「선언 없는 맵」과
  //    한 글자도 다르지 않게** 흐르도록 한다(라우팅 프리셋도 그래서 여기서부터 적용된다 —
  //    쓸 수 없는 규격 행은 `wafer_map_metadata`의 답이 아니므로 「규격 > 라우팅 > 패널」의
  //    첫 부등호를 통과한 것이 아니다).
  //
  // ⚠️ `null`·`''`은 0이 아니다(`Number(null) === 0`). 값의 **부재**와 0을 가르는 것이
  //    이 술어의 전부이므로 `Number()` 하나로 판정하지 않는다. 이 술어가 없으면 위에 적은
  //    `grid_start_x: null` 실측이 그대로 돌아온다 — 지우지 말 것.
  if (loadedGridMeta) {
    const declaredNum = (v) => (v === null || v === undefined || v === ''
      ? null : (Number.isFinite(Number(v)) ? Number(v) : null));
    const sx = declaredNum(loadedGridMeta.grid_start_x);
    const sy = declaredNum(loadedGridMeta.grid_start_y);
    if (sx === null || sy === null) {
      console.warn(`[Map Editor] ${selectedTable} · ${loadedMapKey || ''}: the spec row declares `
        + `no readable origin (grid_start_x=${JSON.stringify(loadedGridMeta.grid_start_x)}, `
        + `grid_start_y=${JSON.stringify(loadedGridMeta.grid_start_y)}) — routing to the `
        + 'coordinate-choice modal, exactly as for a map with no spec row at all. The rest of '
        + 'this row is dropped ON PURPOSE: a declared grid size on a chosen origin is a frame '
        + 'nobody declared and nobody chose.');
      // 조회 동선의 확인창은 아니다(모달이 곧 그 자리다) — 왜 묻는지만 말한다.
      showToast('맵 규격에 START X,Y가 없습니다 — 좌표계를 선택하십시오.', 'warning');
      return { ok: true, gridMeta: null, mapKey: loadedMapKey };
    }
    loadedGridMeta.grid_start_x = sx;
    loadedGridMeta.grid_start_y = sy;
  }

  return { ok: true, gridMeta: loadedGridMeta, mapKey: loadedMapKey };
}

// ④ 선언이 없는 맵의 좌표계 선택 모달 → 'standard' | 'current' | 'cancel'.
//    `el`을 인자로 받는다 — 이 단계가 손대는 유일한 바깥 것이고, 그래서 시그니처가 말한다.
function promptCoordinateChoice(el) {
  return new Promise((resolve) => {
    // [fix C] The default's behavior changed (data bounding box, no mask in
    // effect) — keep the highlighted button honest. Label set here in JS because
    // the semantics it describes are decided in this branch (JS-only fix batch).
    // 🔴 이 버튼은 좌측 패널의 START X,Y를 **버린다**(`startX = minX`, resolveGridFrame).
    //    그것이 이 선택지의 요점이지 부작용이 아니므로 라벨이 말하게 한다 — 운영자의 선언이
    //    사라지는 유일한 자리이고, 새 컨트롤도 확인창도 늘리지 않는 방법이다.
    el.btnChoiceStandard.textContent = '📐 표준 — START 재선언 · 마스크 없음 · Rot 0°';
    el.choiceModal.style.display = 'flex';

    const onStandard = () => {
      cleanup();
      resolve('standard');
    };
    const onCurrent = () => {
      cleanup();
      resolve('current');
    };
    const onCancel = () => {
      cleanup();
      resolve('cancel');
    };
    // 🔴 [1d④] THIS PROMISE HAD EXACTLY THREE EXITS AND ALL THREE WERE BUTTONS.
    //    A modal with no dismissal affordance can be left UNANSWERED, and an
    //    unanswered promise never settles — so every `await openMapFrame(...)`
    //    above it stays pending forever, along with whatever latch the caller set
    //    in a `try` whose `finally` can now never run (transfer_plan's `S.navBusy`:
    //    every material row went dead and said nothing). Escape is the standard
    //    dismissal for this shape and adds no control to the screen; the point is
    //    that the promise ALWAYS settles, so "abandoned" collapses into "cancelled"
    //    and the caller's cleanup runs.
    //    ⚠️ Backdrop click is deliberately NOT wired: a stray click on the scrim
    //    while reading the two options would cancel the load mid-decision, and
    //    Escape already guarantees settlement. One exit is enough to close the hole.
    const onKeyDown = (ev) => {
      if (ev.key === 'Escape') { ev.preventDefault(); onCancel(); }
    };

    const cleanup = () => {
      el.choiceModal.style.display = 'none';
      el.btnChoiceStandard.removeEventListener('click', onStandard);
      el.btnChoiceCurrent.removeEventListener('click', onCurrent);
      el.btnChoiceCancel.removeEventListener('click', onCancel);
      document.removeEventListener('keydown', onKeyDown, true);
    };

    el.btnChoiceStandard.addEventListener('click', onStandard);
    el.btnChoiceCurrent.addEventListener('click', onCurrent);
    el.btnChoiceCancel.addEventListener('click', onCancel);
    // Capture phase: the editor binds plenty of keyboard handlers and this one must
    // win while the scrim is up (the modal owns the screen at that moment).
    document.addEventListener('keydown', onKeyDown, true);
  });
}

// ⑤ 선택 → 격자·원점·회전·면. 셋 중 **정확히 하나**가 프레임을 정한다는 사실이 이 함수의
//    전부다. `boundingBoxCache` 무효화는 호출부가 한다 — 이 단계는 모듈 상태에 쓰지 않는다.
function resolveGridFrame(userChoice, loadedGridMeta, minX, minY, maxX, maxY, el, currentRotation, currentSide) {
  let cols, rows, startX, startY, invertY, rotation, side;

  if (userChoice === 'standard') {
    cols = (maxX >= minX) ? (maxX - minX + 1) : 10;
    rows = (maxY >= minY) ? (maxY - minY + 1) : 10;
    // 🔴 THE ORIGIN IS THE DATA'S OWN MINIMUM, NOT ZERO. This used to read `startX = 0`
    //    while the cell loop below subtracted `minX` from every stored coordinate, and
    //    nothing ever added it back: the frame said "column 0 of this grid is DB x=0"
    //    while the cells had been renumbered as if it were DB x=minX. Since
    //    `getDbCoords` (what ⚡ Push serializes, via `cellObj.x`) is the exact inverse
    //    of `getCanvasCellFromDb` (what the load places with), the two lines are ONE
    //    quantity — so the screen's in-cell label AND the pushed x/y were both the shifted
    //    number. Measured on real data: 1,923 drawn cells across four metadata-less maps,
    //    451 of them reaching Push, and the screen could not reveal it because the label
    //    is the recomputed coordinate and is drawn on empty cells only.
    //
    // ⚠️ Declaring the origin instead of shifting the cells places EVERY cell on exactly
    //    the same canvas square as before — `c = dbX - startX + box.minC` is unchanged when
    //    `dbX` and `startX` move together. Nothing on screen moves; what changes is that the
    //    coordinate the screen states, and therefore the one Push writes, is now the stored
    //    one. That is the whole fix: no compensation at Push, which is not touched.
    startX = minX;
    startY = minY;
    invertY = false;
    rotation = 0;
    side = 'front';
    // [fix C — lead design 2026-07-28] No default choice may produce an un-pushable
    // map. The default frame for a metadata-less map is the rectangular bounding box
    // of the data with NO circle mask in effect: previously the left panel's physical
    // spec (wafer circle) stayed live under this choice, its mask marked corner cells
    // inside:false, and the contrast guard in pushMapData then refused every push
    // (H2 repro: 1293 rows -> 379 covered). The mask predicate has no off switch, so
    // "no mask" is expressed in its own vocabulary: chip 1x1 / offset 0 / margin 3
    // (the panel defaults for offset/margin) and a wafer diameter whose effective
    // radius circumscribes the grid's half-diagonal — every cell corner is then
    // strictly inside the ellipse, so all cells are pushable. applyPresetObject is
    // the existing spec-writer (it owns the dia <select>'s custom-option handling);
    // the bbox cols/rows set below overwrite its derived grid dims. Circle-mask
    // presets remain available through the "current left panel settings" choice.
    const halfDiag = Math.sqrt(cols * cols + rows * rows) / 2;   // mm == cell units at chip 1x1
    applyPresetObject({
      phys_wafer_dia: Math.max(300, Math.ceil(2 * (halfDiag + 4))),
      phys_chip_x: 1, phys_chip_y: 1,
      phys_offset_x: 0, phys_offset_y: 0,
      phys_edge_margin: 3,
    });
    // [D1] 이 규격은 **아무도 재지 않았다.** 서버의 `synthesize_grid_meta`가 같은 값을
    //      `auto_registered: true`와 함께 저장하는 것과 같은 사실이고, 여기서는 저장 행이
    //      아직 없으므로 표지가 화면(입력칸)에 산다. `applyPresetObject`가 방금 껐으므로
    //      **반드시 그 뒤**여야 한다. ⚡ Push가 이 표지를 payload에 실어(§buildPushGrid
    //      Metadata) 왕복 후에도 남는다 — 안 그러면 Push 한 번이 합성 규격을 선언으로 승격한다.
    markGeometryAutoRegistered(true);
    // [D4] 격자·원점도 아무도 선언하지 않았다 — 데이터의 bbox에서 **파생된** 수다(등록기의
    //      `synthesize_grid_meta`가 하는 것과 같은 계산). phys 표지가 격자 축까지 덮기는
    //      하지만, 그 표지는 「등록기가 썼다」는 뜻이라 **조작자가 물음에 답했다**는 사실을
    //      담지 못한다. 어느 결정이 이 프레임 위에 서 있었는지 나중에 물을 수 있어야 한다.
    markFrameChosen('data');
  } else if (userChoice === 'meta') {
    cols = loadedGridMeta.grid_cols;
    rows = loadedGridMeta.grid_rows;
    startX = loadedGridMeta.grid_start_x;
    startY = loadedGridMeta.grid_start_y;
    invertY = loadedGridMeta.grid_y_invert;
    rotation = loadedGridMeta.rotation || 0;
    side = loadedGridMeta.side || 'front';

    if (loadedGridMeta.phys_wafer_dia !== undefined && el.physWaferDia) el.physWaferDia.value = loadedGridMeta.phys_wafer_dia;
    if (loadedGridMeta.phys_chip_x !== undefined && el.physChipX) el.physChipX.value = loadedGridMeta.phys_chip_x;
    if (loadedGridMeta.phys_chip_y !== undefined && el.physChipY) el.physChipY.value = loadedGridMeta.phys_chip_y;
    if (loadedGridMeta.phys_offset_x !== undefined && el.physOffsetX) el.physOffsetX.value = loadedGridMeta.phys_offset_x;
    if (loadedGridMeta.phys_offset_y !== undefined && el.physOffsetY) el.physOffsetY.value = loadedGridMeta.phys_offset_y;
    if (loadedGridMeta.phys_edge_margin !== undefined && el.physEdgeMargin) el.physEdgeMargin.value = loadedGridMeta.phys_edge_margin;
    // [D1] 저장된 표지를 화면으로 옮긴다. **양방향이다** — 표지가 없는 메타를 불러오면
    //      직전 맵의 표지가 남아 진짜 선언을 「선언 없음」으로 읽게 되므로 반드시 끈다.
    markGeometryAutoRegistered(loadedGridMeta.auto_registered === true);
    // [D4] 프레임 표지도 **양방향으로** 옮긴다 — 같은 이유다. 표지 없는(=진짜 선언된) 메타를
    //      불러왔는데 직전 맵의 표지가 남으면, 아무도 고른 적 없는 선언이 「고른 것」으로 읽힌다.
    markFrameChosen(loadedGridMeta.frame_chosen_from || null);
  } else {
    // [2] 화면 컨트롤 독법은 `readGridFrameControls` 하나다 — 여기서 다시 파싱하면 같은
    //     질문의 두 번째 철자가 되고, 종전에는 그 두 철자가 갈리기도 전에 **둘 다** 빈 칸을
    //     0으로 지어냈다(`parseInt('') || 0`).
    const panel = readGridFrameControls(el);
    if (panel.silent.length > 0) {
      // 🔴 빈 칸은 답이 아니다. 지어낸 0으로 좌표계를 세우면 셀은 전부 다른 다이에 앉고
      //    화면은 멀쩡하다 — 이 도메인이 존재하는 이유 그 자체다. 새 확인창을 늘리지 않고
      //    이 선택지 자체를 거절한다(호출부가 취소와 같은 자리로 접는다).
      showToast(`${panel.silent.join(' · ')} 칸이 비어 있어 좌표계를 정할 수 없습니다 — `
        + `값을 채우고 다시 불러오십시오.`, 'error');
      return null;
    }
    cols = panel.cols;
    rows = panel.rows;
    startX = panel.startX;
    startY = panel.startY;
    invertY = panel.invertY;
    rotation = currentRotation;
    side = currentSide;
    // [D4] 이 프레임은 **이 맵이 선언한 것이 아니다** — 조작자가 좌측 패널을 그대로 쓰라고
    //      답한 것이고, 패널은 직전 맵의 잔상일 수도 있다. 표지가 없으면 Push 한 번이 그것을
    //      선언과 바이트 단위로 같게 만들고, 그 사실은 영영 돌아오지 않는다.
    markFrameChosen('panel');
  }

  return { cols, rows, startX, startY, invertY, rotation, side };
}

// ⑥ 셀 값 집합 → legend 행 배열. `legend`(현재 화면)와 팔레트를 인자로 받아 **새 배열을
//    돌려줄 뿐** 대입은 호출부가 한다 — 「어느 시점에 화면의 legend가 바뀌는가」가 한 줄로
//    읽혀야 하기 때문이다(H1의 자리).
function deriveLegendFromCellValues(uniqueVals, legend, predefinedColors) {
  const newLegend = [];
  const usedColors = new Set();

  // First, try to match and preserve existing legend items
  uniqueVals.forEach(v => {
    const existingItem = legend.find(item => item.value === v);
    if (existingItem) {
      // This map's own cells carry the value, so it is no longer a borrowed
      // vocabulary brush - it is part of this map and must be saved with it.
      existingItem.vocab = false;
      newLegend.push(existingItem);
      usedColors.add(existingItem.color);
    }
  });

  // For new unique values, assign description and unique color.
  // [U6] A declared default_legend row wins its color/desc; only undeclared values
  // walk the palette and get the generic BIN-style description.
  let colorIdx = 0;
  uniqueVals.forEach(v => {
    const exists = newLegend.some(item => item.value === v);
    if (!exists) {
      const dr = declaredLegendRow(v);
      let chosenColor = (dr && dr.color) ? String(dr.color) : '';
      // Find next unused color from predefined colors list
      while (!chosenColor && colorIdx < predefinedColors.length) {
        const candidate = predefinedColors[colorIdx++];
        if (!usedColors.has(candidate)) {
          chosenColor = candidate;
        }
      }
      if (!chosenColor) {
        // Fallback to random color if all predefined are used
        chosenColor = '#' + Math.floor(Math.random() * 16777215).toString(16).padStart(6, '0');
      }

      usedColors.add(chosenColor);
      newLegend.push(normalizeLegendItem({
        value: v,
        desc: dr ? String(dr.desc || '') : (v === '1' ? 'GOOD' : (v === '0' ? 'FAIL' : `BIN ${v}`)),
        color: chosenColor
      }));
    }
  });

  return newLegend;
}

// ⑦ 초안 우선순위 — 저장되지 못한 편집(차단 검증에 걸린 계획이 대표적이다)은 브라우저에만
//    있다. 기반 지문이 그대로면 그 사이 아무도 쓰지 않았으므로 초안이 더 새 것이다.
//    어긋나면 **누가 썼다** — 적용하면 남의 저장을 지운다. 적용하지 않고, 버리지도 않고,
//    사실을 드러낸다.
//    반환: `restoredUnsavedEdits`(→ legendDirty) · `staleDraftKept`(→ persist 보류).
function restoreDoeDraftWithPrecedence(selectedTable, loadedMapKey, serverFp, serverCellsFp) {
  let staleDraftKept = false;   // [fix A] see the persist at the call site
  let restoredUnsavedEdits = false;
  const draft = readDoeDraft(selectedTable, loadedMapKey);
  if (draft) {
    const doeFresh = draft.registryFp !== null && draft.registryFp === serverFp;
    const cellsFresh = draft.cellsFp !== null && draft.cellsFp === serverCellsFp;
    const restoredDoe = doeFresh ? applyDoeDraftRecord(draft) : false;
    const restoredCells = cellsFresh ? applyDraftCells(draft.cells) : 0;
    if (restoredDoe || restoredCells > 0) {
      restoredUnsavedEdits = true;
      showToast(`미저장 초안 복구 — ${restoredDoe ? 'DOE' : ''}`
        + `${restoredDoe && restoredCells ? ' · ' : ''}${restoredCells ? `셀 ${restoredCells}개` : ''}`
        + ' (서버 미반영)', 'warning', { dedupeKey: 'draft_restored' });
    }
    // 기반이 어긋난 초안이 실제로 내용을 갖고 있을 때만 말한다 — 빈 초안까지 알리면
    // 신호가 죽는다.
    const hasDoe = draft.doe && Object.keys(draft.doe).length > 0;
    const hasCells = draft.cells && Object.keys(draft.cells).length > 0;
    staleDraftKept = (!doeFresh && hasDoe) || (!cellsFresh && hasCells);
    if (staleDraftKept) {
      showToast('초안보다 서버본이 최신 — 초안을 적용하지 않았습니다 (지우지도 않았습니다).',
        'warning', { dedupeKey: 'draft_stale' });
    }
  }
  return { restoredUnsavedEdits, staleDraftKept };
}

function clearGrid() {
  if (!confirm('격자 내의 모든 입력 값을 삭제하시겠습니까?')) return;
  gridData = {};
  loadedFCells.clear();
  // 🔴 이 두 줄이 없었다. 편집 경로는 열 곳이 넘는데 **여기만** writer를 부르지 않아
  //    (PRIMITIVES §1 "모든 편집 경로가 초안 writer를 불러야 한다" 위반):
  //      ① Clear Grid → 새로고침 → 낡은 초안에서 격자가 통째로 되살아났다
  //      ② 범례·DOE 뱃지가 지워진 셀을 계속 세고 있었다(화면 수량 ≠ 실제, F2와 같은 계급)
  //    `deleteLegendValue`(4018)와 같은 순서·같은 세 줄이다.
  updateLegendCounts();
  renderGridCanvas();
  scheduleCellDraft();
}

function fillGrid() {
  if (!activeBrush) {
    alert('페인팅 브러쉬를 먼저 고르십시오.');
    return;
  }
  if (!confirm(`격자 전체를 현재 선택한 값 '${activeBrush}'(으)로 채우시겠습니까?`)) return;

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;

  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // [F2] 유효 다이 **밖은 칠하지 않는다.** 종전에는 사각 전체를 칠했고 그 셀들은
  //   ① 캔버스에 색이 나오지 않으며(`cellFillColor`가 `!inside`면 outBg)
  //   ② `pushMapData`가 직렬화하지 않고
  //   ③ 그런데도 대비 관문의 분모(`nonEmptyOnGrid`)에는 들어간다
  // 즉 원 기반 맵에서 Fill All 한 번이 그 맵의 Push를 **영구 거절 상태로 만들었다**
  // (값 있는 셀 N개 중 21%가 "밖" → droppedNonEmpty > 0 → 적재 중단). 격자 크기를 아무리
  // 맞춰도 풀리지 않는다 — 셀이 격자 밖이 아니라 원 밖이기 때문이다.
  //
  // 🔴 판정은 새로 만들지 않는다. 렌더가 만든 셀 객체가 있으면 그것을 읽고, 없으면
  //    `getGridCellObject`가 쓰는 것과 **같은 두 함수**(`isValidDieAt`·`isCellInsideWafer`)를
  //    같은 순서로 부른다. 세 번째 기하식은 한 줄도 없다.
  //    저작 캔버스(`basis === 'template'`)에서는 마스크가 격자 전체이므로 이 필터가
  //    아무것도 걸러내지 않는다 — M4② 저작 동선은 글자 하나 바뀌지 않는다.
  let filled = 0;
  let skippedOutside = 0;
  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      const physical = getDieIndex(null, c, r, cols, rows, currentRotation, currentSide);
      const key = `${physical.x}_${physical.y}`;
      const rendered = gridCells2D && gridCells2D[r] ? gridCells2D[r][c] : null;
      const inside = rendered
        ? rendered.inside
        : isValidDieAt(null, physical.x, physical.y, isCellInsideWafer(c, r, visualCols, visualRows));
      if (!inside) { skippedOutside++; continue; }
      if (isProtectedFCell(key)) continue;
      gridData[key] = activeBrush;
      filled++;
    }
  }

  renderGridCanvas();
  scheduleCellDraft();

  // 정직한 결과 보고. 새 컨트롤도 확인창도 아니고, 이미 있는 토스트 한 줄이다.
  // 0칸은 반드시 말해야 한다 — 아무 일도 일어나지 않은 것과 구별되지 않으면 사용자는
  // 같은 버튼을 계속 누른다(규격이 없는 맵에서는 원 판정이 전부 false다).
  if (filled === 0) {
    showToast(`칠할 셀이 없습니다 — ${skippedOutside}칸 모두 유효 다이 밖입니다.`, 'warning');
  } else if (skippedOutside > 0) {
    // [1e] This branch is only reached when `skippedOutside > 0`, i.e. the message says
    // "some cells will not be saved" — yet it rendered as a green success. Tone corrected
    // to warning (spotted while auditing toasts this round).
    showToast(`${filled}칸 칠함 — 유효 다이 밖 ${skippedOutside}칸 제외(저장 안 됨)`, 'warning');
  }
}

// ----------------------------------------------------
// PUSH Map Data to Backend
// ----------------------------------------------------

// [Gate 4] The push-column contract moved to `client2/src/push_columns.js` (see its header).
// It is a pure leaf over its arguments — the only group in this file with no module-mutable
// dependency — so the three harnesses that scored it now `import` the module instead of
// slicing this file's text. Do not re-spell any of it locally: a second opinion about which
// columns a `replace_map` destroys is the exact defect gate 4 closed.

async function pushMapData() {
  // [Data-protection gate 4] The refusal itself is `confirmLogShapedPushTarget` (below);
  // it is FIRST for the reason recorded there — the user must not answer a single
  // question on a push that cannot be allowed. Moving this call changes WHEN a push is
  // refused, which is a behaviour change, not a move.
  if (!confirmLogShapedPushTarget(tableSchema, el, selectedTable)) return;
  // [Push 가드 — 유일하게 남긴 정체성 마찰] 로드한 맵과 적재 대상이 **실제로 어긋났을 때만** 1회 묻는다.
  // replace_map은 맵 키 일치 행을 전량 삭제 후 재기록하므로, 키가 어긋난 채 적재하면
  // 남의 실맵이 통째로 사라진다(이슈 #14ⓐ와 뿌리 동일).
  // 키가 같으면 아무것도 묻지 않는다 — 정상 흐름은 무마찰이다.
  const mismatch = currentIdentityMismatch();
  if (mismatch && !confirm(
    `로드한 맵과 적재 대상이 다릅니다.\n\n`
    + `· 로드: ${loadedIdentity.table} · ${loadedIdentity.mapKey}\n`
    + `· 적재: ${mismatch.table} · ${mismatch.mapKey || '(비어 있음)'}\n\n`
    + `계속하면 적재 대상 맵의 기존 셀이 전량 삭제되고 현재 격자로 대체됩니다. 계속하시겠습니까?`
  )) {
    return;
  }
  const metaRead = collectMetaFieldValues(tableSchema);
  if (!metaRead.ok) return;
  const metaValues = metaRead.metaValues;

  const xCol = el.colMapX.value;
  const yCol = el.colMapY.value;
  const valCol = el.colMapVal.value;

  const xType = tableSchema.column_types[xCol] || 'number';
  const yType = tableSchema.column_types[yCol] || 'number';
  const valType = tableSchema.column_types[valCol] || 'string';

  // [2] 컨트롤 독법은 `readGridFrameControls` 하나다 — 📐 규격만 저장이 같은 함수를 읽는다.
  // 🔴 빈 칸은 0이 아니다(§`gridFrameControlNum`). 지어낸 0을 실어 보내면 `replace_map`이
  //    맵 전량을 그 좌표계로 재기록한다 — 되돌릴 수 없는 자리에서 없는 선언을 만드는 셈이다.
  const panel = readGridFrameControls(el);
  if (panel.silent.length > 0) {
    showToast(`${panel.silent.join(' · ')} 칸이 비어 있어 적재하지 않았습니다 — `
      + `빈 칸을 0으로 지어내 저장하지 않습니다.`, 'error');
    return;
  }
  const { cols, rows, startX, startY, invertY } = panel;

  // The wafer_map_metadata record this push would write — built from the panel controls
  // read just above. See `buildPushGridMetadata` (below) for the M4①→② note on why the
  // object is reconstructed from scratch and who decides what `valid_die_ref` becomes.
  const pushMeta = buildPushGridMetadata(cols, rows, startX, startY, invertY,
    el, currentRotation, currentSide, validDie);
  const gridMetaOut = pushMeta.gridMetaOut;
  const gridMetaStr = pushMeta.gridMetaStr;

  const updates = [];
  const serializedKeys = [];   // [F2b] 실제로 직렬화된 셀의 물리 키 — 성공 시 서버 셀 집합이 된다

  // [F2] 이 순회의 술어(`inside` && 값 있음)는 `eachSavableCell` 하나뿐이고, 화면의 수량도
  // 같은 함수를 지난다. 여기에 술어를 다시 쓰면 "화면 34 · DB 33"이 되돌아온다.
  eachSavableCell((cellObj, val) => {
    serializedKeys.push(cellObj.key);
    let valParsed = valType === 'number' ? Number(val) : val;

    let xParsed = xType === 'number' ? parseInt(cellObj.x, 10) : String(cellObj.x);
    let yParsed = yType === 'number' ? parseInt(cellObj.y, 10) : String(cellObj.y);

    const rowUpdates = {
      [xCol]: xParsed,
      [yCol]: yParsed,
      [valCol]: valParsed,
      ...metaValues
    };

    if (tableSchema.column_types && tableSchema.column_types['grid_metadata']) {
      rowUpdates['grid_metadata'] = gridMetaStr;
    }

    const updateItem = {
      updates: rowUpdates,
      source_name: 'user',
      updated_by: CURRENT_USER
    };
    updates.push(updateItem);
  });

  // [Data-protection gate - contrast guard] Non-empty cells the loop above skipped
  // (outside the wafer circle, or at coordinates the current grid does not even contain)
  // would not merely be missing from this push: replace_map deletes every row of this map
  // key first, so a payload that covers less than the screen DESTROYS the remainder.
  // Metadata-less maps opened under a guessed default frame are the known case (H2,
  // 2026-07-28: 1293 rows -> 379). Refuse instead of destroying - third member of the
  // gate family (zone-columns-missing / legacy-unreadable): each blocks a write that
  // would delete data it never serialized. Counted with the loop's own emptiness
  // predicate ((v || '') !== ''), so cells the user deliberately erased ('') are not
  // "dropped" and an identical-count push passes with zero friction.
  //
  // [F2b] 그 한 수를 **두 모집단으로 쪼갠다.** 합은 종전의 `droppedNonEmpty`와 같고 거부의
  // 강도도 같지만, 안내가 원인을 가리킬 수 있게 된다. 종전에는 원 밖 셀에도 "격자 크기·
  // 시작 좌표·회전·물리 규격을 맞추라"고 말했는데 — 그 셀들은 격자 밖이 아니라 원 밖이라
  // **그 안내대로 해도 절대 풀리지 않는다.** 게다가 F2 이후 범례가 그 셀을 세지 않으므로
  // 화면에 원인의 흔적이 하나도 남지 않는다. 쪼개는 것이지 무르게 하는 게 아니다.
  const nonEmptyOnGrid = Object.keys(gridData).filter(k => (gridData[k] || '') !== '').length;
  const unsavable = classifyUnsavableCells();
  const strayKeys = unsavable.outsideStray;
  // 서버 데이터를 지울 수 있는 모집단 — 종전과 **같은** 거부.
  // [MEDIUM-1] 합은 `pushBlockingCount` 하나에서만 나온다. 종전엔 채택 알림이 같은 함수를
  // 써서 **두 소비자가 갈릴 수 있는 것**이 이 규율의 요지였는데, 그 알림은 삭제됐고(94b9baa)
  // 지금은 소비자가 하나다 — 규율은 유지한다(두 번째 소비자가 생기면 여기서 갈라진다).
  const blocking = pushBlockingCount(unsavable);
  if (blocking > 0) {
    console.warn(`[Map Editor] push refused - frame covers ${updates.length}/${nonEmptyOnGrid} non-empty cells `
      + `(${blocking} would be deleted by replace_map: ${unsavable.offGrid.length} off-grid, `
      + `${unsavable.outsideRetained.length} outside-wafer of unproven origin; ${strayKeys.length} stray)`);
    alert(
      `적재를 중단했습니다 — 현재 프레임이 맵 전체를 덮지 못합니다.\n\n`
      + `값이 있는 셀 ${nonEmptyOnGrid}개 중 ${blocking}개가 현재 격자 범위·웨이퍼 영역 밖에 있어 `
      + `이번 적재에 담기지 않습니다. 이대로 적재하면 덮어쓰기(Clean Replace) 과정에서 `
      + `해당 ${blocking}개 셀이 서버에서 삭제됩니다.\n\n`
      + `격자 크기·시작 좌표·회전·물리 규격을 맵 전체가 보이도록 맞춘 뒤 다시 시도하십시오.`
      + (strayKeys.length > 0
        ? `\n\n(이와 별개로, 서버에 저장된 적 없는 유효 다이 밖 셀 ${strayKeys.length}개도 격자에 남아 있습니다. `
        + `위를 먼저 해결하면 정리 방법을 안내합니다.)`
        : '')
    );
    return;
  }
  // 서버가 보낸 적 없음이 증명된 유효 다이 밖 셀만 남았다 — 지워도 서버에서 사라질 것이
  // 없으므로, 프레임을 고치라는 안내 대신 **한 번 눌러 정리하는 길**을 준다.
  // 새 패널도 새 모드도 아니다: 이미 있던 거부 대화상자가 쓰기 1회 확인이 될 뿐이다.
  if (strayKeys.length > 0) {
    console.warn(`[Map Editor] push blocked by ${strayKeys.length} stray outside-wafer cells `
      + `(never rendered, never counted, never on the server) - offering cleanup`, strayKeys.slice(0, 20));
    if (!confirm(
      `적재를 중단했습니다 — 저장할 수 없는 셀 ${strayKeys.length}개가 격자에 남아 있습니다.\n\n`
      + `이 셀들은 격자 밖이 아니라 웨이퍼의 유효 다이 밖에 있습니다. 그래서 화면에 색이 나오지 않고 `
      + `범례·DOE 수량에도 잡히지 않으며, 서버에 저장된 적도 없습니다. `
      + `격자 크기·시작 좌표·회전을 맞추는 것으로는 사라지지 않습니다 — 가장 흔한 원인은 `
      + `예전 🎨 Fill All이 격자 사각형 전체를 칠하면서 남긴 흔적입니다.\n\n`
      + `· 이 좌표들이 원래 유효 다이여야 한다면: [취소] 후 물리 규격(직경·칩 크기·엣지 마진)이나 `
      + `유효 다이 지정을 넓혀 다시 시도하십시오.\n`
      + `· 아니라면 [확인]을 눌러 이 ${strayKeys.length}개 셀만 격자에서 지우십시오. `
      + `유효 다이 안쪽 셀과 서버에 저장된 데이터는 그대로입니다. 정리한 뒤 ⚡ Push를 다시 눌러 주십시오.`
    )) return;
    strayKeys.forEach(k => { delete gridData[k]; });
    renderGridCanvas();
    scheduleCellDraft();   // 초안에서도 지운다 — 새로고침으로 되살아나면 정리가 아니다
    showToast(`유효 다이 밖 ${strayKeys.length}칸 정리 — ⚡ Push를 다시 누르십시오.`, 'success');
    return;
  }

  if (updates.length === 0) {
    alert('격자에 적재할 셀이 없습니다 — 먼저 칠하십시오.');
    return;
  }

  // [Split Registry] push 대상 값 중 split 서술이 비어있는 값 경고 (자연어 기록 누락 방지 관문)
  if (!confirmMissingSplitDescriptions(updates, valCol, legend)) return;

  // [C5] 덮어쓰기 대상 맵을 확인문에 명시한다. replace_map은 이 맵 키의 기존 행을
  // 전량 삭제 후 재기록하므로, 테이블명만 보여주면 "어느 맵이 지워지는지" 알 수 없다.
  const targetMapId = getMapIdFromMeta(metaValues, tableSchema) || 'default_map';
  const outsideNote = outsideCircleNoteForPush(cols, rows, currentRotation, gridCells2D, gridData);
  if (!confirm(
    `총 ${updates.length}건의 활성 맵 데이터를 덮어쓰기 적재(Clean Replace)하시겠습니까?\n\n` +
    `· 대상 테이블: ${selectedTable}\n` +
    `· 대상 맵 키: ${targetMapId}\n` + outsideNote + `\n` +
    `⚠️ 이 맵 키의 기존 셀은 전부 삭제된 뒤 현재 격자 내용으로 대체됩니다.`
  )) {
    return;
  }

  el.btnPushMap.textContent = '⚡ Pushing...';
  el.btnPushMap.disabled = true;

  const mapIdStr = targetMapId;
  let metaPushFailed = null;   // [M5] 맵 규격(회전/면) 저장 실패를 성공 알림에 섞이지 않게 붙든다

  console.group('%c🚀 [Map Editor API] PUSH MAP DATA EXECUTED', 'color: #3b82f6; font-weight: bold; font-size: 13px;');
  console.log('📌 Target Table:', selectedTable);
  console.log('📌 Map ID:', mapIdStr);
  console.log('📌 Cell Update Count:', updates.length);
  console.log('📌 Grid Metadata Payload:', gridMetaOut);   // 실제로 직렬화되는 그 객체

  // Always push dedicated wafer_map_metadata record
  try {
    const metaPayload = {
      updates: [{
        business_key_val: `${selectedTable}_${mapIdStr}`,
        updates: {
          map_pk: `${selectedTable}_${mapIdStr}`,
          target_table: selectedTable,
          map_id: mapIdStr,
          grid_metadata: gridMetaStr
        },
        source_name: 'user',
        updated_by: CURRENT_USER
      }]
    };
    // [V1 effort instrument] No `effort` field here on purpose. This is the same batch
    // endpoint, so adding one would be accepted and would bill the user's clicks a second
    // time under a different table. The cell push (2/2) is the single reporting point.
    console.log('📤 [API Request 1/2] Header Metadata:', `${API_BASE}/tables/wafer_map_metadata/data/updates`, metaPayload);
    const metaRes = await fetch(`${API_BASE}/tables/wafer_map_metadata/data/updates`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(metaPayload)
    });
    console.log('📥 [API Response 1/2] Status:', metaRes.status);
    // [M5] 종전에는 status를 검사하지 않아 500이어도 catch에 안 걸렸고,
    // 본 Push는 "적재 완료"를 알렸다 → **회전/면 규격이 저장 안 된 채 성공으로 보인다.**
    // (다음 오버레이가 틀린 메타로 정렬되는 경로이므로 조용히 넘기면 안 된다.)
    if (!metaRes.ok) metaPushFailed = `HTTP ${metaRes.status}`;
  } catch (e) {
    console.warn('[Map Editor] Dedicated wafer_map_metadata push skipped/warn:', e);
    metaPushFailed = e && e.message ? e.message : String(e);
  }

  const payload = {
    updates: updates,
    silent: false,
    replace_map: true,
    // [V1 effort instrument] Raw interaction counts for this correction unit ride the
    // EXISTING batch update - no extra request, no new endpoint. This is the one place
    // the map editor reports effort: the wafer_map_metadata PUT above and the split
    // registry PUT in saveLegendToServer deliberately carry none, or one human action
    // would be counted three times. snapshot() does not reset; only commit() does.
    effort: effortSnapshot()
  };

  try {
    console.log(`📤 [API Request 2/2] Cell Data (${updates.length} rows):`, `${API_BASE}/tables/${selectedTable}/data/updates`, payload);
    const res = await fetch(`${API_BASE}/tables/${selectedTable}/data/updates`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      const result = await res.json();
      console.log('📥 [API Response 2/2] Success Result:', result);
      console.groupEnd();

      // [V1 effort instrument] The counts above rode WITH this request - reset here and
      // nowhere else, and ONLY if the server says it actually recorded them. `res.ok` is
      // not proof: a re-push of an unchanged map returns 200 with change_count 0 and
      // writes no effort row, so committing on ok alone would delete the effort that push
      // cost. Every failure path (non-ok status, network throw, and every gate that
      // returned before the request) likewise leaves the counters untouched, because retry
      // effort is real human effort and must land on the push that finally succeeds. Also
      // deliberately BEFORE the legend/registry write below: that write is a separate
      // request that cannot un-commit these cells, and leaving the counters alive for it
      // would bill the same clicks to the next push as well.
      effortCommitIfRecorded(result);

      // 새로 만든 맵도 이 시점부터 정체성이 확정된다 → 이후 Push는 가드 아래 놓인다
      // (setLoadedIdentity가 framePushed를 초기화하므로 반드시 먼저 호출한다)
      if (!loadedIdentity) setLoadedIdentity(selectedTable, mapIdStr);
      // [F2b] 방금 적재한 셀은 이제 **서버에 있다.** 기록을 갱신하지 않으면, 이 다음에
      // 사용자가 물리 규격을 줄여 그 셀들이 원 밖이 되었을 때 "서버가 보낸 적 없다"로
      // 오판해 정리 대상이 되고, 그 다음 Push가 실재하는 행을 지운다.
      serverCellKeys = {
        table: selectedTable,
        mapKey: (loadedIdentity && loadedIdentity.mapKey) || mapIdStr,
        keys: new Set(serializedKeys),   // 직렬화 루프가 실제로 담은 그 키들
      };
      // [재설계 v2] Push 성공 = 이 프레임의 편집이 서버에 적재됨 (뒤로가기 경고 해제)
      framePushed = true;
      // [F4] `serverRead` — a successful push is FIRST-HAND evidence about server state.
      // `mapKeyListCache.delete` just below already drops its cache on exactly this
      // ground, and `serverCellKeys` above is refreshed on it too. The material-map
      // presence cache was simply a THIRD cache nobody had wired to that evidence.
      notifyMapContext({ serverRead: true });
      recordLastOpenMap();   // a just-created key becomes the refresh target too
      // [F5] 방금 만든 템플릿이 지정 칸 자동완성에 **없는** 상태를 없앤다. 캐시가
      // `switchTable`에서만 비워져 있었는데, 템플릿을 만들고 곧바로 다른 맵에서 지정하는
      // 흐름은 같은 테이블에 머문다(가장 흔한 동선).
      // ⚠️ `dde342c` folded this cache into `populateMapKeyDatalist` and renamed it, but
      // missed this call site — `validDieListCache` was never declared, so every
      // successful Push threw a ReferenceError here and everything below (including the
      // Split Registry legend save) never ran. Found by the user on 2026-07-31, in the
      // live editor; no harness could see it because they slice functions, not the module.
      mapKeyListCache.delete(selectedTable);

      // [Split Registry] 맵과 계획의 동행 — push 성공 시 legend(=DOE) 일괄 서버 저장.
      //
      // ⚠️ 「원자적」이라고 적혀 있었으나 **원자적이지 않다** (2026-07-28 실측). 셀이 먼저
      //    `replace_map`으로 커밋되고 registry 저장은 그 뒤에 별도 요청으로 나가므로, 아래
      //    실패 분기가 존재한다는 사실 자체가 반례다 — 셀은 들어갔는데 계획은 안 들어간 상태가
      //    실제로 만들어진다(그때 그렇게 토스트한다). 말과 동작이 다른 주석은 하루를 태운
      //    결함 계열이라 문구를 고쳤다. 진짜 보장은 **순서**다: 맵이 서버에 들어간 뒤에만
      //    계획을 쓴다.
      //
      // ⚠️ 계획이 **미완성이어도 그대로 저장한다.** V1–V5는 보고이지 관문이 아니다.
      //    저장을 막는 것은 `saveLegendToServer` 안의 두 가지뿐이고, 그 둘은 계획이 틀려서가
      //    아니라 **저장이 지금 있는 데이터를 지우기 때문에** 막는다.
      saveLegendToStorage();
      const legendSaved = await saveLegendToServer(mapIdStr);
      if (legendSaved.ok) legendDirty = false;
      applyLegendSaveResult(legendSaved);
      if (legendSaved.ok) {
        // 저장된 행 수는 저장한 쪽이 센다 — legend.length로 다시 세면 아직 이 맵의 것이 아닌
        // vocabulary 브러시까지 포함해 **DB에 없는 수를 보고**하게 된다.
        // [1e] Success confirmation. The plan-head chip flips to 「저장됨 HH:MM」 and STAYS
        // there, which beats a toast that fades. Failure is toasted by the branch below.
        console.debug(`[map] split registry saved — ${legendSaved.count} rows`);
      } else if (legendSaved.reason !== 'adopted' && legendSaved.reason !== 'conflict'
        && legendSaved.reason !== 'unknown-server-state') {
        // adopted/conflict/unknown 은 applyLegendSaveResult가 이미 정확히 알렸다 —
        // 여기서 "오프라인 캐시"로 덮어 말하면 원인이 사라진다.
        showToast('DOE·split 서술 registry 저장 실패 — 오프라인 캐시에만 보관됨', 'warning');
      }

      if (metaPushFailed) {
        // 셀은 들어갔지만 **규격이 저장되지 않았다** — 다음 로드/오버레이가 틀린 메타로 계산된다
        showToast(`셀 ${result.updated_count || result.count || updates.length}건 적재 · 맵 규격 저장 실패 `
          + `(${metaPushFailed}) — 다시 Push하십시오.`, 'error');
      } else {
        showToast(`적재 완료 — ${result.updated_count || result.count || updates.length}건`, 'success');
      }
    } else {
      const errData = await res.json().catch(() => ({}));
      console.error('❌ [API Response 2/2] Error Payload:', errData);
      console.groupEnd();
      throw new Error(errData.detail || 'Push failed');
    }
  } catch (err) {
    console.error('❌ [API Error]', err);
    console.groupEnd();
    alert(`데이터 적재 실패 — ${err.message}`);
  } finally {
    el.btnPushMap.textContent = '⚡ Push Map Data';
    el.btnPushMap.disabled = false;
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// `pushMapData`'s named steps — moved out of it verbatim, nothing else.
//
// ⚠️ WHAT DID **NOT** MOVE, AND WHY. Read this before cutting anything else out of
//    `pushMapData`: the write-set table licenses far more than the harnesses allow,
//    and none of the four refusals below is visible in it.
//    (Anchor strings are described here, never reproduced — a second copy of an
//     anchor in this file is a landmine for the next `String.replace`.)
//
//  · THE SERIALIZATION LOOP stays inline. `copy_header_count_harness`'s
//    `pushLoopUsesSharedPredicate()` slices the source TEXT of the region that begins
//    at the `updates` array declaration and ends at the contrast gate's first line,
//    then asserts the region calls `eachSavableCell(` and contains no second `inside`
//    predicate (INV-F2). Move the loop and that region stops being the push loop —
//    the assertion goes vacuous while staying green. That is the "화면 34 · DB 33"
//    class the shared predicate was introduced to close.
//
//  · THE CONTRAST / STRAY-CLEANUP GATE stays inline. The SAME harness slices it
//    between those two exact source lines and RUNS it verbatim inside its own
//    `runPushGate(updates)` wrapper. Both anchor lines, their order, and every
//    identifier between them are load-bearing: a name its sandbox does not define is
//    a `die()` — "nothing was compared" — not a red assertion.
//
//  · THE `wafer_map_metadata` PUT AND THE CELL-PUT EPILOGUE stay inline.
//    `effort_instrument_harness`'s mutations M1/M2/M3/M3b/M8 anchor on INDENTED text
//    inside them (at 2, 4, 6, 8 and 10 spaces). Lifting either block to module scope
//    re-indents those lines by one level, every one of those mutations then fails to
//    apply, and that harness treats a mutation that did not apply as a hard FAIL.
//
//  · `mapKeyListCache.delete(...)` stays where it is, inside the success branch.
//    Cache invalidation living in the write path is coupling worth removing, but
//    moving it is a behaviour question, not a move.
// ════════════════════════════════════════════════════════════════════════════════

// [Data-protection gate 4 - log-shaped target] Fourth member of the gate family
// (zone-columns-missing / legacy-unreadable / frame-contrast): refuse, don't confirm.
// Called before every dialog - the user should not answer a single question on a
// push that cannot be allowed. Near-miss 2026-07-28: dt_log opened as a map (works
// for viewing), ⚡ Push would have replace_map'ed the scoped REAL log rows into
// editor-fabricated (key, x, y, val) cells - dt_id, eventtime, core lot/slot, cx/cy,
// dt_eqp all gone.
//
// ONE declared exception (`map_push_ok: true` in the table's table_config entry,
// served via /schema): sites with a real editor-overwrite flow into such tables
// (R&D manual measurements into eds_fail_map / core_defect_map) get a single
// loss-acknowledging confirm instead of the block. The declaration is the site
// saying "the loss is understood and intended here" - absent, the hard refusal
// stands. Removing the declaration re-locks the table (production cutover).
//
// Returns false = do not push. Which mode refuses, and what each one says, is
// `logShapedPushDecision`'s answer, unchanged.
function confirmLogShapedPushTarget(tableSchema, el, selectedTable) {
  const gate4 = logShapedPushDecision(
    tableSchema, el.colMapX.value, el.colMapY.value, el.colMapVal.value);
  if (gate4.mode !== 'clean') {
    const extraDataCols = gate4.extras;
    const shown = extraDataCols.slice(0, 8).join(', ')
      + (extraDataCols.length > 8 ? ` 외 ${extraDataCols.length - 8}개` : '');
    if (gate4.mode === 'confirm') {
      console.warn(`[Map Editor] push into '${selectedTable}' with map_push_ok declared - `
        + `${extraDataCols.length} data column(s) outside the map contract will be lost on `
        + `replaced rows: ${extraDataCols.join(', ')}`);
      if (!confirm(
        `이 테이블('${selectedTable}')은 맵 계약 외 컬럼(${extraDataCols.length}개: ${shown})을 갖고 있습니다.\n\n`
        + `이 Push로 교체되는 행들의 그 컬럼 값이 소실됩니다. 계속하시겠습니까?`
      )) {
        return false;
      }
    } else {
      console.warn(`[Map Editor] push refused - '${selectedTable}' is log-shaped: `
        + `${extraDataCols.length} data column(s) outside the map contract would be `
        + `destroyed by replace_map: ${extraDataCols.join(', ')}`);
      alert(
        `적재 중단 — '${selectedTable}'은(는) 맵 전용 테이블이 아닙니다(로그형).\n\n`
        + `Clean Replace가 파괴할 맵 계약 밖 컬럼 ${extraDataCols.length}개:\n· ${shown}`
      );
      return false;
    }
  }
  return true;
}

// The metadata panel, read as it stands. `ok:false` = the push must stop because the
// table declares metadata fields and the operator filled none of them in; a table with
// no such fields at all (`metaInputs.length === 0`) is NOT stopped, which is why the
// emptiness test carries that second term.
function collectMetaFieldValues(tableSchema) {
  const metaInputs = document.querySelectorAll('[id^="meta-input-"]');
  const metaValues = {};
  let hasMeta = false;

  metaInputs.forEach(input => {
    const col = input.id.replace('meta-input-', '');
    const val = input.value.trim();
    if (val !== '') {
      hasMeta = true;
      const colType = tableSchema.column_types[col] || 'string';
      metaValues[col] = colType === 'number' ? Number(val) : val;
    }
  });

  if (!hasMeta && metaInputs.length > 0) {
    alert('맵 키를 하나 이상 입력하십시오.');
    return { ok: false, metaValues };
  }
  return { ok: true, metaValues };
}

// Always construct grid metadata object & JSON string for dedicated wafer_map_metadata table.
// (`standard_frame_origin_harness` re-derives this same shape from the same controls and
//  cites this function by name — the two must not drift apart.)
//
// [M4①→②] 이 객체는 화면 컨트롤에서 **처음부터 다시** 만들어진다. ①에서는 선언에 대응하는
// 컨트롤이 없어 원문(raw)을 그대로 되썼고, ②에서 그 컨트롤이 생겼다 — 이제 파괴적 재구성이
// 선언 **옆**이 아니라 선언 **위**를 지나므로, 무엇을 쓸지는 두 함수가 나눠 정한다:
//   `validDieRefForPush()`  — 사용자가 바꿨는가(모르면 원문을 손대지 않는다)
//   `applyValidDieRef()`    — 바꿨다면 무엇을 쓰는가(이음매가 채점하는 순수 쓰기)
// 선언이 없고 사용자가 칸을 건드리지 않은 맵은 `keep` + raw 부재 → 페이로드가 `2a9f6c4`와
// **바이트 단위로 같다**(INV-1, effort 하네스가 페이로드로 단언한다).
//   `validDieRefPayload()`   — 그 결정을 저장 페이로드로 바꾼다(순수 함수, 계약이 채점한다)
// [2] 격자 프레임 컨트롤의 **유일한 독법.** ⚡ Push와 📐 규격만 저장은 같은 규격 객체를
// 만들어야 하므로, 두 곳에서 각자 파싱하면 안 된다 — 한쪽이 `|| 10`이고 한쪽이 `|| 1`이면
// 같은 화면이 두 개의 규격을 저장하고, 저장이 `ceil`·표시가 `round`였던 그 계급이 된다.
// [2b] 「이 칸이 말을 했는가」의 **유일한 철자.**
//
// 🔴 빈 칸은 0이 아니다. 아무 말도 하지 않은 것이다. `parseInt('') || 0`은 그 침묵을 **선언된
//    0으로 승격**시켰고, 실측으로 그 0이 `grid_start_x: 0`으로 DB에 도달했다 — 화면은 멀쩡했다.
//    빈 칸이었다는 사실이 저장 페이로드 어디에도 남지 않으므로 사후에 알아낼 방법도 없다.
// 🔴 **관용은 그대로 둔다.** 읽힌 값의 해석은 종전과 바이트 단위로 같다(`parseInt` → `|| dflt`).
//    여기서 엄격해지면 이미 저장된 선언의 뜻이 바뀌고, 그것은 이 라운드의 질문이 아니다.
//    바뀌는 것은 **지어내던 자리 하나**뿐이다: 읽히지 않으면 수 대신 `null`을 낸다.
// ⚠️ `null`이지 기본값이 아니다. 소비자가 검사를 잊으면 `null`은 페이로드에서 그대로 눈에
//    띄고 서버 `int(None)`이 거절하지만, 0은 조용히 통과해 남의 좌표계를 덮는다.
function gridFrameControlNum(input, dflt) {
  const raw = input ? input.value : undefined;
  if (controlIsSilent(raw)) return null;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) ? (n || dflt) : null;
}

// [2] 격자 프레임 컨트롤의 **유일한 독법**은 이 함수 하나다 — ⚡ Push · 📐 규격만 저장 ·
// 좌표계 선택의 `current` 분기(§`resolveGridFrame`) 셋이 같은 함수를 부른다. 종전에는
// `current` 분기가 같은 질문을 `parseInt(...) || N`으로 **다시** 물었고, 두 철자가 갈리기도
// 전에 **둘 다** 빈 칸을 지어냈다.
// `silent`는 아무 말도 하지 않은 칸의 **이름**이다 — 거절문이 어느 칸인지 말할 수 있어야 한다.
function readGridFrameControls(el) {
  const frame = {
    cols: gridFrameControlNum(el.gridCols, 10),
    rows: gridFrameControlNum(el.gridRows, 10),
    startX: gridFrameControlNum(el.gridStartX, 0),
    startY: gridFrameControlNum(el.gridStartY, 0),
    invertY: el.gridYInvert.checked,
  };
  frame.silent = [['cols', '격자 COLS'], ['rows', '격자 ROWS'],
    ['startX', 'START X'], ['startY', 'START Y']]
    .filter(([k]) => frame[k] === null).map(([, label]) => label);
  return frame;
}

function buildPushGridMetadata(cols, rows, startX, startY, invertY,
  el, currentRotation, currentSide, validDie) {
  const gridMeta = {
    grid_cols: cols,
    grid_rows: rows,
    grid_start_x: startX,
    grid_start_y: startY,
    grid_y_invert: invertY,
    rotation: currentRotation,
    side: currentSide,
    phys_wafer_dia: el.physWaferDia ? (parseFloat(el.physWaferDia.value) || 300) : 300,
    phys_chip_x: el.physChipX ? (parseFloat(el.physChipX.value) || 2.5) : 2.5,
    phys_chip_y: el.physChipY ? (parseFloat(el.physChipY.value) || 2.5) : 2.5,
    phys_offset_x: el.physOffsetX ? (parseFloat(el.physOffsetX.value) || 0.0) : 0.0,
    phys_offset_y: el.physOffsetY ? (parseFloat(el.physOffsetY.value) || 0.0) : 0.0,
    phys_edge_margin: el.physEdgeMargin ? (parseFloat(el.physEdgeMargin.value) || 3.0) : 3.0
  };
  // [D1] 합성 규격이면 **표지도 함께 저장한다.** 이 함수는 화면 컨트롤에서 규격을 처음부터
  //      다시 짓는데, 표지에 대응하는 컨트롤이 없어서 종전에는 Push 한 번이 표지를 지웠다 —
  //      그러면 자동 등록 행이 조용히 「사람이 선언한 규격」으로 승격되고, 등록기는 이미
  //      존재하는 행을 다시 쓰지 않으므로(absent-only) 그 사실은 영영 돌아오지 않는다.
  //      🔴 표지가 없는 맵의 payload는 이 줄로 **한 바이트도 바뀌지 않는다**(INV-1).
  if (geometryIsAutoRegistered(null)) gridMeta.auto_registered = true;
  // [D4] 프레임을 **고른** 맵이면 그 사실도 함께 저장한다. `phys_assumed_from`과 같은 형식:
  //      있을 때만 있고, 값이 어디서 왔는지를 말한다. 🔴 표지가 없는 맵의 payload는 이 두 줄로
  //      **한 바이트도 바뀌지 않는다**(INV-1) — 오늘의 모든 선언된 맵이 그 경우다.
  const chosenFrom = frameChosenFrom(null);
  if (chosenFrom) gridMeta.frame_chosen_from = chosenFrom;
  const validDieDecision = validDieRefForPush();
  const gridMetaOut = validDieRefPayload(gridMeta, validDieDecision,
    validDie ? validDie.raw : undefined);
  const gridMetaStr = JSON.stringify(gridMetaOut);
  return { gridMetaOut, gridMetaStr };
}

// [Split Registry] Returns false = the operator declined to save values whose split
// description is still empty. Reporting, not a validity ruling: the plan is saved
// incomplete if they say yes.
function confirmMissingSplitDescriptions(updates, valCol, legend) {
  const pushedValues = Array.from(new Set(updates.map(u => String(u.updates[valCol]))));
  const missingDescVals = getMissingDescValues(pushedValues, legend);
  if (missingDescVals.length > 0) {
    const preview = missingDescVals.slice(0, 10).join(', ') + (missingDescVals.length > 10 ? ' …' : '');
    const okMissing = confirm(
      `split 서술이 없는 값 ${missingDescVals.length}개 — 그래도 저장하시겠습니까?\n` +
      `· ${preview}`
    );
    if (!okMissing) return false;
  }
  return true;
}

// [M4②] 원 밖으로 나가는 셀은 **말한다**. 새 확인창이 아니라 이미 있는 확인문의 한 줄이며,
// 근거가 원인 맵(오늘의 모든 맵)에서는 이 줄이 존재하지 않는다 — 확인문이 글자 하나
// 바뀌지 않는다는 뜻이다(INV-1). 유효 다이 저작·참조 중에만, 실제로 나가는 셀이 있을 때만.
// Returns '' when there is nothing to say, so the confirm text is byte-identical then.
function outsideCircleNoteForPush(cols, rows, currentRotation, gridCells2D, gridData) {
  let outsideNote = '';
  if (validDieBasis() !== 'circle') {
    const isRot = (currentRotation === 90 || currentRotation === 270);
    const visualCols = isRot ? rows : cols;
    const visualRows = isRot ? cols : rows;
    let n = 0;
    Object.keys(gridCells2D).forEach(rStr => {
      Object.keys(gridCells2D[rStr] || {}).forEach(cStr => {
        const co = gridCells2D[rStr][cStr];
        if (!co || !co.inside) return;
        if ((gridData[co.key] || '') === '') return;
        if (!isCellInsideWafer(co.c, co.r, visualCols, visualRows)) n++;
      });
    });
    if (n > 0) outsideNote = `· 웨이퍼 원 밖 셀: ${n}건 (유효 다이 근거가 원이 아닙니다)\n`;
  }
  return outsideNote;
}

// ----------------------------------------------------
// E1/E2 Batch Actions
// ----------------------------------------------------
function getEdgeClassification() {
  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // 1. Build inside wafer map
  const isInside = Array.from({ length: visualRows }, () => Array(visualCols).fill(false));
  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      // [M4①] E1/E2는 "유효 다이의 외곽"이다 — 원의 외곽이 아니다. 판정 근거가 맵으로
      // 바뀌면 침식 기준도 같이 바뀌어야 하고, 안 그러면 마스크와 엣지가 어긋난다.
      const p = getDieIndex(null, c, r, cols, rows, currentRotation, currentSide);
      if (isValidDieAt(null, p.x, p.y, isCellInsideWafer(c, r, visualCols, visualRows))) {
        isInside[r][c] = true;
      }
    }
  }

  // 2. BFS Distance Transform from outside cells to compute exact layer depth
  const dist = Array.from({ length: visualRows }, () => Array(visualCols).fill(Infinity));
  const queue = [];

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (!isInside[r][c]) {
        dist[r][c] = 0;
        queue.push({ r, c });
      }
    }
  }

  const dRow = [-1, 1, 0, 0];
  const dCol = [0, 0, -1, 1];

  let head = 0;
  while (head < queue.length) {
    const { r, c } = queue[head++];
    const currentDist = dist[r][c];

    for (let i = 0; i < 4; i++) {
      const nr = r + dRow[i];
      const nc = c + dCol[i];

      if (nr >= 0 && nr < visualRows && nc >= 0 && nc < visualCols) {
        if (dist[nr][nc] === Infinity) {
          dist[nr][nc] = currentDist + 1;
          queue.push({ r: nr, c: nc });
        }
      }
    }
  }

  // 3. Classify E1 (Distance == 1) and E2 (Distance == 2)
  const isE1 = Array.from({ length: visualRows }, () => Array(visualCols).fill(false));
  const isE2 = Array.from({ length: visualRows }, () => Array(visualCols).fill(false));

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (isInside[r][c]) {
        if (dist[r][c] === 1) {
          isE1[r][c] = true;
        } else if (dist[r][c] === 2) {
          isE2[r][c] = true;
        }
      }
    }
  }

  return { isE1, isE2 };
}

function getVisualGridDimensions() {
  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  return {
    visualCols: isRotated90or270 ? rows : cols,
    visualRows: isRotated90or270 ? cols : rows
  };
}

function selectEdgeCells(target) {
  const { isE1, isE2 } = getEdgeClassification();
  const targetMap = target === 1 ? isE1 : isE2;
  const { visualCols, visualRows } = getVisualGridDimensions();

  let count = 0;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (targetMap[r] && targetMap[r][c]) {
        count++;
      }
    }
  }

  if (count > 0) {
    selectedEdgeTargetMap = targetMap;
    if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'flex';
    el.gridStatusCoords.textContent = `Selected ${count} E${target} cells`;
  } else {
    selectedEdgeTargetMap = null;
    if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
    alert(`E${target} 조건에 맞는 셀이 없습니다.`);
  }
  scheduleRenderGridCanvas();
}

function autoPaintE1E2() {
  // [U6] No hardcoded E1/E2 colors: declared default_legend row first, else the shared
  // palette rule — the same path every auto-added value takes (autoAddLegendValue).
  let legendUpdated = false;
  if (autoAddLegendValue('E1', 'Edge 1 (Outermost)')) legendUpdated = true;
  if (autoAddLegendValue('E2', 'Edge 2 (Inner Outer)')) legendUpdated = true;
  if (legendUpdated) {
    persistLegend();
    renderLegendTable();
  }

  const { isE1, isE2 } = getEdgeClassification();
  const { visualCols, visualRows } = getVisualGridDimensions();

  let e1Count = 0;
  let e2Count = 0;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      const cell = gridCells2D[r]?.[c];
      if (!cell) continue;
      const key = cell.key;
      if (isProtectedFCell(key)) continue;

      if (isE1[r] && isE1[r][c]) {
        gridData[key] = 'E1';
        e1Count++;
      } else if (isE2[r] && isE2[r][c]) {
        gridData[key] = 'E2';
        e2Count++;
      }
    }
  }

  scheduleRenderGridCanvas();
  scheduleCellDraft();
  // [1e] The canvas and the legend badges already carry what was painted, so the success
  // report goes to the console. But ZERO cells must still be said out loud — the same rule
  // `fillGrid` keeps: if it looks identical to nothing happening, users keep pressing.
  if (e1Count === 0 && e2Count === 0) {
    showToast('E1/E2로 칠할 셀이 없습니다.', 'warning');
  } else {
    console.debug(`[map] E1/E2 auto-paint — E1 ${e1Count} cells · E2 ${e2Count} cells`);
  }
}

function fillSelectedCells() {
  if (!activeBrush) {
    alert('페인팅 브러쉬를 먼저 고르십시오.');
    return;
  }
  if (!selectedEdgeTargetMap) return;

  const { visualCols, visualRows } = getVisualGridDimensions();

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (selectedEdgeTargetMap[r] && selectedEdgeTargetMap[r][c]) {
        const cell = gridCells2D[r]?.[c];
        if (cell && !isProtectedFCell(cell.key)) {
          gridData[cell.key] = activeBrush;
        }
      }
    }
  }

  selectedEdgeTargetMap = null;
  if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
  scheduleRenderGridCanvas();
  scheduleCellDraft();
}

function clearSelectedCells() {
  if (!selectedEdgeTargetMap) return;

  const { visualCols, visualRows } = getVisualGridDimensions();

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (selectedEdgeTargetMap[r] && selectedEdgeTargetMap[r][c]) {
        const cell = gridCells2D[r]?.[c];
        if (cell && !isProtectedFCell(cell.key)) {
          gridData[cell.key] = '';
        }
      }
    }
  }

  selectedEdgeTargetMap = null;
  if (el.selectionActionsContainer) el.selectionActionsContainer.style.display = 'none';
  scheduleRenderGridCanvas();
  scheduleCellDraft();
}

// ── 클립보드 쓰기 — **비보안 컨텍스트에서 동작하는 유일한 경로** ────────────────────
//
// 🔴 `navigator.clipboard`는 이 앱에 없다. 운영은 LAN 평문 HTTP = 비보안 컨텍스트라
//    `navigator.clipboard`가 통째로 `undefined`다. 종전 코드는 그 undefined에 `.writeText`를
//    부르고, catch가 **같은 식을 한 번 더** 불러 결국 한글 alert로 끝났다 — 사용자가 본
//    그 팝업이다. 규약은 `clipboard.js`(그리드 복사)가 이미 지키고 있던 것과 같다:
//    **copy 이벤트의 `e.clipboardData`**.
//
//    버튼 클릭에는 사용자의 copy 키 입력이 없으므로 이벤트를 합성한다 — 화면 밖 편집 가능
//    노드를 선택하고 `document.execCommand('copy')`로 copy 이벤트를 일으킨 뒤, 그 이벤트에서
//    내용을 갈아끼운다. Windows가 `text/html`을 CF_HTML로 매핑하므로 엑셀이 서식을 읽는다.
//
//    사용자의 기존 선택 영역은 복원한다. 복사 한 번이 사용자가 잡아 둔 선택을 날리면 안 된다.
function writeClipboardRich(html, text) {
  const sel = window.getSelection ? window.getSelection() : null;
  const saved = (sel && sel.rangeCount > 0) ? sel.getRangeAt(0).cloneRange() : null;
  // The hidden holder has to TAKE focus to receive the copy, and removing it drops focus on
  // <body>. Harmless from the toolbar button (nothing had focus), but a keyboard caller
  // would come back to a page that lost its focused control, so put it back.
  const prevActive = document.activeElement;

  const holder = document.createElement('div');
  holder.setAttribute('contenteditable', 'true');
  holder.setAttribute('aria-hidden', 'true');
  holder.style.cssText = 'position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;overflow:hidden;';
  holder.textContent = ' ';
  document.body.appendChild(holder);

  let served = false;
  const onCopy = (e) => {
    if (!e.clipboardData) return;      // 갈아끼우지 못하면 served=false로 남아 정직하게 실패한다
    e.clipboardData.setData('text/html', html);
    e.clipboardData.setData('text/plain', text);
    e.preventDefault();
    served = true;
  };

  let fired = false;
  document.addEventListener('copy', onCopy, true);
  try {
    if (sel) {
      const range = document.createRange();
      range.selectNodeContents(holder);
      sel.removeAllRanges();
      sel.addRange(range);
    }
    holder.focus();
    fired = document.execCommand('copy');
  } catch (err) {
    console.debug('[map] execCommand copy threw', err);
  } finally {
    document.removeEventListener('copy', onCopy, true);
    holder.remove();
    // 포커스를 먼저 되돌리고 선택을 되돌린다 — 순서가 반대면 포커스 이동이 방금 복원한 선택을 지운다.
    if (prevActive && prevActive !== document.body && prevActive.focus && document.contains(prevActive)) {
      try { prevActive.focus({ preventScroll: true }); } catch (_) { /* not focusable anymore */ }
    }
    if (sel) {
      sel.removeAllRanges();
      if (saved) sel.addRange(saved);
    }
  }
  return fired && served;
}

// ═══════════════════════════════════════════════════════════════════════════════
// [F1ⓐ] COPY HEADER MODE — 사용자 회사의 실제 본딩맵 양식
//
// 켜면 `📋 Copy to Excel`이 격자와 함께 두 블록을 더 싣는다:
//   상단 헤더  TITLE + 열 그룹 (Base · 1H · MID · TOP)
//   우측 보조표 VALUE | COUNT | STACK | DESC
//
// 🔴 **보조표의 출처가 둘이다.** COUNT는 격자 **집계**이고 STACK·DESC는 표①(DOE)의
//    **선언**이다. 집계 쪽은 `computeLegendCounts` — 범례 뱃지·DOE 패널·Push가 쓰는 그
//    함수 그대로다. 여기서 따로 세면 한 화면에 두 개의 수량이 생긴다(F2가 바로 그 결함).
// 🔴 **열 그룹 이름은 DOE 선언에서 나온다**(INV-ⓐ-4): `ZONE_LABEL`·`DOE_COLUMNS`.
//    화면이 "MID"라 쓰는데 내보내기가 다른 단어를 쓰면 공장이 읽는 파일이 갈라진다.
// 🔴 **끄면 가산성이 성립한다**(INV-ⓐ-1): 아래 격자 루프는 `headerOn`이 거짓일 때
//    종전과 **같은 문자열을 같은 순서로** 이어 붙인다. 하네스가 HEAD 출력과 바이트 비교한다.
// ═══════════════════════════════════════════════════════════════════════════════
const COPY_HEADER_KEY = 'mapCopyHeader';

// 보조표 머리글. `DOE_COLUMNS`가 정본이므로 DOE 패널이 쓰는 단어와 **같은 단어**가 나간다
// (INV-ⓐ-4). transfer_plan의 `colHeader`와 같은 한 줄이고, 같은 배열을 읽는다.
function colHeaderWord(id) {
  const c = DOE_COLUMNS.find(x => x.id === id);
  return c ? c.header : id;
}

// 보조표 머리줄의 네 단어, 순서대로. `copyGridToExcel`이 찍는 그 목록이고, 읽는 쪽의 정지
// 조건이 "첫 칸은 VALUE다"라는 사실도 여기서 나온다(`auxHeaderInLine` 주석 참조).
function auxHeadWords() {
  return [colHeaderWord('value'), 'COUNT', colHeaderWord('stack'), colHeaderWord('desc')];
}

function copyHeaderEnabled() {
  return !!(el.copyHeaderToggle && el.copyHeaderToggle.checked);
}

// 첫 열 그룹의 이름. 값이 `getCurrentMapKey()`(= `composeMapId(map_key_columns, …)`)에서
// 나오므로 **이름도 같은 선언에서 나와야 한다.**
// 🔴 여기는 `'Base'` 하드코딩이었다. `base`는 `bonding_map`의 컬럼명일 뿐인데 📋 Copy to
//    Excel은 모든 맵 테이블에 있어서, `dt_map`(map_key_columns = lot·slot)에서 내보내면
//    헤더가 `Base | LOTID_03` 으로 나왔다 — 이름과 값이 다른 테이블을 가리키는 상태다.
//    나머지 세 라벨이 `ZONE_LABEL`에서 오는 것과 같은 규율이다(INV-ⓐ-4).
// 합성 규칙도 값과 맞춘다: `composeMapId`가 '_'로 잇는 복합 키는 이름도 '_'로 잇는다
// (lot·slot → `Lot_Slot`). 선언이 없으면 컬럼명을 주장하지 않고 역할명으로 물러선다.
function mapKeyGroupLabel() {
  const cols = (tableSchema && Array.isArray(tableSchema.map_key_columns))
    ? tableSchema.map_key_columns.filter(c => c && String(c).trim() !== '') : [];
  if (cols.length === 0) return 'MAP KEY';
  return cols.map(c => {
    const s = String(c).trim();
    return s.charAt(0).toUpperCase() + s.slice(1);
  }).join('_');
}

// 상단 헤더의 열 그룹. 첫 칸은 이 맵의 정체(7b canonical 맵 키)이고, 나머지 셋은 DOE가
// 선언한 구역별 자재다. 자재 토큰은 **원문 그대로** 나간다 — `lot_slot:BIN`이 정체이고,
// 화면 칩이 보기 좋게 접어 보여주는 것은 그림일 뿐이다(transfer_plan §materialChipHtml).
function copyHeaderGroups() {
  const groups = [{ label: mapKeyGroupLabel(), value: getCurrentMapKey() || '' }];
  ZONES.forEach(z => {
    const seen = [];
    legend.forEach(item => {
      parseMaterialList(item[z]).forEach(tok => { if (seen.indexOf(tok) < 0) seen.push(tok); });
    });
    groups.push({ label: ZONE_LABEL[z], value: seen.join(', ') });
  });
  return groups;
}

// ═══════════════════════════════════════════════════════════════════════════════
// 열 폭 정책 — **한 곳**. 상단 헤더와 우측 보조표가 같은 규칙을 쓴다.
//
// 🔴 THE DEFECT. 헤더 칸이 맵 셀 하나로 나갔다. 맵 셀은 32px 정사각이라 `MIDLOT_01`은
//    **글자가 들어갈 자리 자체가 없다** (사용자 2026-07-29: "MAP CELL과 셀 크기 동일").
//    회사 실제 양식은 각 그룹이 여러 열에 걸쳐 **병합**돼 있고 그래서 긴 라벨이 읽힌다.
//
// 🔴 균등 분배는 답이 아니다. 라벨 길이가 제각각이라 `1H`와 `MIDLOT_01`에 같은 폭을 주면
//    긴 쪽이 다시 잘린다. 폭은 **글자 수에서** 나오고, 남는 열은 그 폭에 **비례해** 나눈다.
//
// ⚠️ 어떤 분배를 하든 **모든 행의 열 합계가 정확히 같아야 한다.** 하나라도 어긋나면 엑셀이
//    표 전체를 밀어 버린다 — 그래서 분배는 최대 잔여법으로 합을 정확히 맞추고, 격자 행도
//    `totalCols`까지 채운다. 이건 미관이 아니라 산출물의 정합성이다.
//
// 픽셀 상수는 **아래 격자 <td>가 실제로 쓰는 수**와 같아야 한다(32px, padding 6px×2).
// 다르면 이 계산 전체가 조용한 거짓말이 된다.
// ═══════════════════════════════════════════════════════════════════════════════
const HDR_COL_PX = 32;     // 격자 셀 한 칸의 폭 — 아래 `width: 32px`와 같은 수
const HDR_PAD_PX = 12;     // headCellStyle/headValStyle의 좌우 padding 합 (6px × 2)
const HDR_CHAR_PX = 7;     // 10pt Arial bold 한 글자의 보수적 폭
const HDR_MIN_SPAN = 2;    // 빈 라벨도 맵 셀 하나로는 내보내지 않는다
const HDR_MAX_SPAN = 8;    // 문장 길이의 DESC 하나가 표를 인쇄 한 장 밖으로 밀지 않도록
// [F1ⓑ] 격자와 보조표 사이의 빈 칸. **읽기 쪽이 격자 폭을 이 상수로 되찾는다**
// (`gridWidth = VALUE의 열 위치 − HDR_GAP_COLS`). 쓰기가 2로 늘고 읽기가 1로 남으면 붙여넣은
// 격자가 통째로 한 칸 밀린다 — 그래서 지역 상수(`GAP_W`)에서 여기로 올라왔다. 하나여야 한다.
const HDR_GAP_COLS = 1;

// 이 글자가 잘리지 않으려면 맵 셀 몇 칸이 필요한가.
function headerSpanFor(text) {
  const len = String(text === null || text === undefined ? '' : text).length;
  const span = Math.ceil((len * HDR_CHAR_PX + HDR_PAD_PX) / HDR_COL_PX);
  return Math.min(HDR_MAX_SPAN, Math.max(HDR_MIN_SPAN, span));
}

// `total`개의 열을 최소 폭을 보장하며 **길이에 비례해** 나눈다.
// 🔴 합은 정확히 `total`이다(최대 잔여법). 내림만 하면 몇 열이 증발해 행이 ragged해진다.
// `total`이 최소 합보다 작으면 최소 폭을 그대로 돌려준다 — 그때는 호출부가 `total`을 그
// 합으로 올려 **모든 행을 함께** 넓힌다(헤더만 넓히면 제목 행이 데이터 행보다 길어진다).
function distributeSpans(texts, total) {
  const mins = texts.map(headerSpanFor);
  const base = mins.reduce((a, b) => a + b, 0);
  if (base === 0 || total <= base) return mins;
  const surplus = total - base;
  const share = mins.map(m => surplus * m / base);
  const out = mins.map((m, i) => m + Math.floor(share[i]));
  const order = share.map((s, i) => ({ i, frac: s - Math.floor(s) }))
    .sort((a, b) => (b.frac - a.frac) || (a.i - b.i));
  let used = out.reduce((a, b) => a + b, 0);
  for (let k = 0; used < total; k++) { out[order[k % order.length].i]++; used++; }
  return out;
}

// 우측 보조표 4열의 폭. 열마다 **그 열의 가장 긴 내용**에서 나온다 — 머리글만 보면
// `DESC`(4자)가 4자 폭을 받고 그 아래 문장이 전부 잘린다.
function auxColumnSpans(auxHead, auxRows) {
  const col = k => [auxHead[k]].concat(
    (auxRows || []).map(r => [r.value, String(r.count), r.stack, r.desc][k]));
  return [0, 1, 2, 3].map(k => col(k).reduce((m, t) => Math.max(m, headerSpanFor(t)), 0));
}

// 우측 보조표의 행. 선언(legend)이 순서를 정하고, 거기에 없는데 **칠해진** 값은 뒤에 붙인다 —
// 화면에 색이 있는데 표에는 없는 값은 "보이는 대로"를 깨고, 그 셀들은 실제로 저장된다.
function copyHeaderAuxRows(counts) {
  const rows = legend.map(item => ({
    value: String(item.value),
    count: counts[item.value] || 0,
    stack: (item.stack === null || item.stack === undefined) ? '' : String(item.stack),
    desc: item.desc || '',
  }));
  const declared = new Set(rows.map(r => r.value));
  Object.keys(counts).forEach(v => {
    if (!declared.has(v) && counts[v] > 0) rows.push({ value: v, count: counts[v], stack: '', desc: '' });
  });
  return rows;
}

// [F1ⓑ] 이 복사본의 TITLE 문자열. **조립기는 하나다** — 복사가 쓰고 붙여넣기가 대조하므로,
// 두 곳에서 각자 조립하면 "정체가 같은데 글자가 다르다"로 붙여넣기가 거부된다.
function copyTitleText() {
  return [selectedTable || '', getCurrentMapKey() || ''].filter(Boolean).join(' · ');
}

// [F1ⓑ] 노치 'D' 표식이 놓이는 화면 좌표. 종전에는 `copyGridToExcel` 안에 인라인으로 있었고,
// 붙여넣기가 **같은 수**를 알아야 해서 여기로 올라왔다(오버레이 규율과 같다 — 두 번째 구현 금지).
//
// 🔴 이 좌표는 (회전, 면, bbox)의 함수다. 그래서 붙여넣기에서 이것이 **프레임 지문**이 된다:
//    복사가 rot 0/front에서 나왔는데 화면이 rot 180이면 노치가 반대쪽 행에 있고, 그 불일치가
//    "치수는 같은데 프레임이 다르다"(rot 0 vs 180, front vs back)를 잡는 유일한 신호다.
//
// 🔴 [P0-2] 격자 밖이면 `null`이다 — **주석이 그렇게 약속했고 코드는 그러지 않았다.**
//    rot 0의 노치는 `box.maxR + 1`이므로 마스크가 없는 프레임(bbox가 격자를 꽉 채우는
//    경우 = `loadExistingMap`의 📐 표준 기본값이 **모든** 메타 없는 맵에 적용하는 그 프레임)
//    에서는 `visualRows`와 같아 격자를 벗어난다. 네 회전이 모두 그렇다(180 → -1, 90 → -1,
//    270 → visualCols). 그런데 종전에는 격자 밖 좌표를 그대로 돌려주었고, 호출부는 그것을
//    "지문 있음"으로 다룰 수도 있었다. 없는 것을 0으로 읽으면 안 되므로 여기서 `null`로
//    말한다 — 이 파일의 규율(미상 ≠ 0)이 여기에도 그대로 적용된다.
function computeNotchCell(rotation, side) {
  // 🔴 **원 상자로 묻는다.** 노치는 웨이퍼의 물리 특징이고, 이 좌표는 클립보드의 프레임
  //    지문이다. 유효 다이 기준 상자를 쓰면 참조 해석이 한 번 실패한 세션에서 지문이 조용히
  //    달라져, 정상적인 붙여넣기가 "회전·면이 다릅니다"라는 무관한 사유로 거절된다.
  //    (지문이 canvas 좌표라는 점은 변하지 않는다 — 원점 상자는 좌표의 **번호 매기기**만
  //     정하므로 노치 칸의 위치와 서로 간섭하지 않는다.)
  const box = getWaferBoundingBox(null, rotation, side, { circleOnly: true });
  const centerC = Math.floor((box.minC + box.maxC) / 2);
  const centerR = Math.floor((box.minR + box.maxR) / 2);
  const dx = (side === 'front') ? 1 : -1;
  let screenDx = 0;
  let screenDy = 0;
  if (rotation === 0) { screenDx = dx; screenDy = 0; }
  else if (rotation === 90) { screenDx = 0; screenDy = dx; }
  else if (rotation === 180) { screenDx = -dx; screenDy = 0; }
  else if (rotation === 270) { screenDx = 0; screenDy = -dx; }

  let cell = null;
  if (rotation === 0) cell = { r: box.maxR + 1, c: centerC + screenDx };        // Bottom notch
  else if (rotation === 180) cell = { r: box.minR - 1, c: centerC + screenDx }; // Top notch
  else if (rotation === 90) cell = { r: centerR + screenDy, c: box.minC - 1 };  // Left notch
  else if (rotation === 270) cell = { r: centerR + screenDy, c: box.maxC + 1 }; // Right notch
  if (!cell) return null;
  // 격자 범위는 회전이 적용된 **화면** 치수다 — 노치 좌표도 화면 좌표이므로 같은 축으로 잰다.
  // ⚠️ 축은 **인자 `rotation`**에서 뽑는다. `getVisualGridDimensions()`는 모듈의
  //    `currentRotation`을 읽으므로, 화면과 다른 회전을 물어보면 좌표는 그 회전으로 계산하고
  //    경계는 화면 회전으로 재는 자기모순이 생긴다(하네스 실측: rot 270을 rot-0 화면에서
  //    물었을 때 격자 밖 좌표가 null이 아니라 좌표로 돌아왔다). `getWaferBoundingBox`가
  //    바로 위에서 쓰는 것과 같은 유도식이다.
  const cols = gridDimNum(null, 'cols', el.gridCols, 10);
  const rows = gridDimNum(null, 'rows', el.gridRows, 10);
  const isRot = (rotation === 90 || rotation === 270);
  const visualCols = isRot ? rows : cols;
  const visualRows = isRot ? cols : rows;
  if (cell.r < 0 || cell.r >= visualRows || cell.c < 0 || cell.c >= visualCols) return null;
  return cell;
}

// 🔴 [MEDIUM-3] 지문이 **실제로 그려지는** 자리. 복사와 붙여넣기가 이 한 함수를 쓴다.
//
// 종전에는 두 술어가 갈려 있었다: 복사는 `isNotchCell && val === ''`일 때만 'D'를 찍고
// (값이 있는 셀을 표식으로 덮지 않는 것은 옳다), 붙여넣기는 노치가 격자 안이면 **무조건**
// 'D'를 요구했다. 그래서 노치 자리가 칠해진 맵 — M4의 사각 유효 다이 저작 경로가 만드는
// 바로 그 형태 — 은 복사는 되고 되붙이기는 영구히 거부됐다("회전·면이 다릅니다"라는, 원인과
// 무관한 사유로). 역방향도 있었다: 값이 진짜 'D'인 셀은 붙여넣기가 표식으로 보고 조용히
// 비웠다 — 왕복마다 셀 하나 손실.
//
// 규칙 한 줄로 통일한다: **지문은 격자 안이고 비어 있는 노치 셀에만 존재한다.**
// 그래서 값이 있는 노치 셀은 지문 없음(= P0-2의 거부 대상)이 되고, 값 'D'는 데이터로 남는다.
function notchMarkCell(rotation, side) {
  const n = computeNotchCell(rotation, side);
  if (!n) return null;
  const cell = gridCells2D[n.r] ? gridCells2D[n.r][n.c] : null;
  // 렌더가 만들지 않은 셀은 복사도 'D'를 찍는다(`copyGridToExcel`의 else 갈래) — 지문이 있다.
  if (cell && (gridData[cell.key] || '') !== '') return null;
  return n;
}

function copyGridToExcel() {
  // 🔴 종전 가드 `if (!gridCells2D)`는 **한 번도 발화하지 않는 죽은 코드**였다:
  //    `gridCells2D`는 `{}`로 초기화되고 `{}`는 truthy다. 격자가 없어도 통과해서 빈 표를
  //    조용히 클립보드에 실었다. 조용한 빈 결과보다 사유를 붙인 거부가 낫다.
  const cellCount = gridCells2D
    ? Object.keys(gridCells2D).reduce((n, r) => n + Object.keys(gridCells2D[r] || {}).length, 0)
    : 0;
  if (cellCount === 0) {
    showToast('격자가 없습니다 — 맵을 먼저 불러오십시오.', 'warning');
    return;
  }

  const { visualCols, visualRows } = getVisualGridDimensions();
  // 🔴 [MEDIUM-2] 이 배열은 **행 배열의 배열**이고, 평문은 마지막에 `serializeTsv` 한 번으로
  //    만든다. 종전에는 각 행을 `rowCells.join('\t')`으로 즉시 문자열로 만들었고 — 즉 쓰는
  //    쪽은 인용을 모르고 읽는 쪽(`parseTsv`)은 엑셀 인용 규칙을 아는 상태였다. 실측 왕복:
  //      · DESC `"고온" 조건`  → 되붙이면 `고온 조건` (인용부호가 사라진 채 legend에 기록됨)
  //      · DESC `1H<TAB>비교`  → 되붙이면 `1H`로 절단
  //      · `"` 또는 줄바꿈을 품은 셀 → 열/행 수가 어긋나 「행 수가 다릅니다」·「회전·면이
  //        다릅니다」로 거부 → 운영자는 원인(DESC 한 글자)과 무관한 격자 크기·회전을 만진다.
  const matrix = [];

  // 화면과 같은 색을 쓴다. 내보내기 전용 하드코딩 색(#DAF2D0·#f8fafc)은 다크 테마 화면을
  // 라이트 색으로 내보내고 있었다 (INV-1c-4).
  const C = getThemeColors();
  const surface = C.surface;
  const colorMap = {};
  legend.forEach(item => { colorMap[item.value] = item.color; });

  const outHex = toExcelHex(C.outBg, surface, '#f1f3f6');
  const insideEmptyHex = toExcelHex(C.insideEmpty, surface, surface);
  const textEmptyHex = toExcelHex(C.textEmpty, insideEmptyHex, '#333333');
  const textOutHex = toExcelHex(C.textOut, outHex, '#888888');
  const lineHex = toExcelHex(C.waferEdge, surface, '#222222');
  const lineWeakHex = toExcelHex(C.line, surface, '#d1d5db');

  // ── COPY HEADER MODE 준비 ────────────────────────────────────────────────────
  // 꺼져 있으면 아래 세 값은 어디에도 쓰이지 않고, 문자열 조립 경로는 종전 그대로다.
  const headerOn = copyHeaderEnabled();
  //  COUNT의 출처. 화면 뱃지·DOE 패널·⚡ Push와 **같은 함수**다(F2 수렴점).
  const auxRows = headerOn ? copyHeaderAuxRows(computeLegendCounts()) : [];
  const groups = headerOn ? copyHeaderGroups() : [];
  const GAP_W = HDR_GAP_COLS;                        // 격자와 보조표 사이 한 칸 (읽기와 공유)
  const auxHead = auxHeadWords();
  // VALUE · COUNT · STACK · DESC 는 이제 **각자의 폭**을 갖는다 (종전에는 넷 다 32px 한 칸).
  const auxColSpans = headerOn ? auxColumnSpans(auxHead, auxRows) : [1, 1, 1, 1];
  const AUX_W = auxColSpans.reduce((a, b) => a + b, 0);
  // 상단 헤더 칸들(라벨·값이 번갈아)의 폭. 종전 `groups.length * 2`는 **칸마다 한 열**이라는
  // 뜻이었고 그것이 바로 이 결함이었다 — 이제 폭은 글자에서 나온다.
  const groupTexts = [];
  groups.forEach(g => { groupTexts.push(g.label, g.value); });
  const groupMinCols = groupTexts.map(headerSpanFor).reduce((a, b) => a + b, 0);
  // 표 전체의 열 수. 격자+보조표가 넓으면 헤더가 그 폭을 나눠 갖고, 헤더가 더 넓어야 하면
  // (열 3~5개짜리 좁은 격자) 표 전체가 그만큼 넓어진다. 어느 쪽이든 **모든 행이 이 수와 같다.**
  const totalCols = headerOn ? Math.max(visualCols + GAP_W + AUX_W, groupMinCols) : visualCols;
  // 🔴 [상단 병합의 범위] 병합은 **맵 격자에서 끝난다.** 종전에는 TITLE과 그룹 띠가 둘 다
  //    `totalCols`(= 격자 + 간격 + 보조표)에 걸쳐, 인쇄물에서 제목 줄과 그룹 띠가 **DOE 보조표
  //    위를 지나갔다** — 실측: 9열 맵에서 병합 18열, 51열 맵에서 병합 60열.
  //    남는 열은 병합하지 않고 **개별 빈 칸**으로 채우므로 행 폭은 여전히 `totalCols`다
  //    (위 ⚠️의 "모든 행의 열 합계가 같아야 한다"는 그대로 지켜진다).
  // ⚠️ 하한은 `groupMinCols`다. 라벨이 들어갈 최소 폭보다 격자가 좁으면(열 3~5개) 띠를 격자에
  //    맞춰 깎는 것은 `MIDLOT_01`을 다시 자르는 일 — 이 폭 정책이 존재하는 그 결함이다.
  //    그래서 그때는 종전 폭을 그대로 쓴다(= 이 라운드에서 아무것도 바뀌지 않는다).
  const headerBandCols = headerOn ? Math.max(visualCols, groupMinCols) : visualCols;
  const groupSpans = headerOn ? distributeSpans(groupTexts, headerBandCols) : [];

  const headCellStyle = `border: 1px solid ${lineHex}; background-color: ${outHex}; color: ${textEmptyHex};`
    + ' font-size: 10pt; font-weight: bold; text-align: center; vertical-align: middle; padding: 2px 6px;';
  const headValStyle = `border: 1px solid ${lineHex}; background-color: ${surface};`
    + ' font-size: 10pt; text-align: center; vertical-align: middle; padding: 2px 6px;';
  const gapStyle = 'border: none;';

  // 보조표 r번째 줄(0 = 머리줄)의 4칸 + 앞의 빈 칸. 없으면 빈 칸만.
  // 네 칸은 각자 `auxColSpans[k]`만큼 **병합**된다 — 폭이 열마다 다르므로 빈 줄도 같은
  // 폭으로 자리를 지켜야 아래위 칸이 어긋나지 않는다.
  const auxFields = (i) => (i === 0)
    ? auxHead
    : (auxRows[i - 1] ? [auxRows[i - 1].value, String(auxRows[i - 1].count), auxRows[i - 1].stack, auxRows[i - 1].desc] : null);
  const auxCells = (i) => {
    // 간격 칸의 **개수도** `HDR_GAP_COLS`에서 나온다. 종전에는 여기와 `auxTsv`가 각각 리터럴
    // 한 칸을 찍었고, 폭 계산(`totalCols`)만 상수를 썼다 — 읽기 쪽이 `VALUE 위치 − 간격`으로
    // 격자 폭을 되찾으므로, 그 리터럴과 상수가 갈리는 순간 붙여넣은 격자가 통째로 밀린다.
    let cells = new Array(HDR_GAP_COLS).fill(`<td style="${gapStyle}"></td>`).join('');
    const fields = auxFields(i);
    for (let k = 0; k < 4; k++) {
      const span = ` colspan="${auxColSpans[k]}"`;
      if (!fields) { cells += `<td${span} style="${gapStyle}"></td>`; continue; }
      const style = (i === 0) ? headCellStyle : headValStyle;
      cells += `<td${span} style="${style}">${escapeHtmlAttr(fields[k])}</td>`;
    }
    return cells;
  };
  // 평문에는 병합이 없다 — 글자는 그 칸의 첫 열에 놓고 나머지 열은 빈 칸으로 채운다.
  // 그래야 TSV의 열 수가 HTML의 colspan 합과 **같아진다**.
  const auxTsv = (i) => {
    const fields = auxFields(i);
    const out = new Array(HDR_GAP_COLS).fill('');      // 격자와 보조표 사이 (읽기와 공유하는 상수)
    for (let k = 0; k < 4; k++) {
      out.push(fields ? fields[k] : '');
      for (let j = 1; j < auxColSpans[k]; j++) out.push('');
    }
    return out;
  };
  const auxLines = headerOn ? auxRows.length + 1 : 0;   // 머리줄 포함

  // HTML table for rich formatting in Excel (Border + Fill Colors)
  let html = '<table style="border-collapse: collapse; text-align: center; font-family: Arial, sans-serif;">';

  if (headerOn) {
    // TITLE = 이 복사본이 **어느 맵인지**. 앱이 이미 로드 토스트에서 쓰는 표기와 같은 식이다
    // (`${selectedTable} · ${mapKey}`) — 인쇄물에 붙는 이름과 화면이 부르는 이름을 갈라 놓지
    // 않기 위해서다. 맵 키는 `getCurrentMapKey`(7b canonical)에서만 나온다.
    const title = copyTitleText();
    // 병합이 끝난 뒤의 남는 열. 병합이 아니라 **빈 칸 하나씩**이라 행 폭만 맞추고 표식은
    // 격자 밖으로 나가지 않는다. `gapStyle`은 격자↔보조표 간격 칸이 쓰는 그 스타일이다.
    const bandPad = new Array(Math.max(0, totalCols - headerBandCols))
      .fill(`<td style="${gapStyle}"></td>`).join('');
    html += `<tr><td colspan="${headerBandCols}" style="border: none; font-size: 13pt; font-weight: bold;`
      + ` text-align: left; padding: 4px 2px;">${escapeHtmlAttr(title)}</td>${bandPad}</tr>`;
    // 🔴 여기가 사용자가 본 그 줄이다. 종전에는 칸마다 `<td>` 하나 = 맵 셀 한 칸(32px)이라
    //    `MIDLOT_01`이 들어갈 자리가 없었다. 이제 각 칸이 `colspan`으로 병합되고, 폭은
    //    글자 수에 비례한다. 짝수 칸이 라벨·홀수 칸이 값이라는 순서는 그대로다(INV-ⓐ-4).
    let groupRow = '<tr>';
    groupTexts.forEach((t, i) => {
      const style = (i % 2 === 0) ? headCellStyle : headValStyle;
      groupRow += `<td colspan="${groupSpans[i]}" style="${style}">${escapeHtmlAttr(t)}</td>`;
    });
    html += `${groupRow}${bandPad}</tr>`;
    matrix.push([title].concat(new Array(Math.max(0, totalCols - 1)).fill('')));
    const groupCells = [];
    groupTexts.forEach((t, i) => {
      groupCells.push(t);
      for (let k = 1; k < groupSpans[i]; k++) groupCells.push('');
    });
    // 평문에는 병합이 없으므로 `bandPad`의 빈 칸도 여기서는 그냥 빈 열이다. 띠가 격자에서
    // 끝난 뒤로 이 채움은 실제로 동작한다(종전에는 분배가 `totalCols`를 정확히 채워 무동작).
    while (groupCells.length < totalCols) groupCells.push('');
    matrix.push(groupCells);
  }

  // Helper for text color contrast
  const getContrastColor = (hexcolor) => {
    if (!hexcolor || hexcolor.charAt(0) !== '#') return '#000000';
    const r = parseInt(hexcolor.substr(1, 2), 16);
    const g = parseInt(hexcolor.substr(3, 2), 16);
    const b = parseInt(hexcolor.substr(5, 2), 16);
    const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
    return (yiq >= 128) ? '#000000' : '#ffffff';
  };

  // 노치 좌표는 `notchMarkCell` 하나에서 나온다 — 붙여넣기가 프레임 지문으로 **같은 함수**를
  // 쓴다. null이면 이 프레임에는 지문이 없다(격자 밖이거나 그 셀에 값이 있다).
  const notch = notchMarkCell(currentRotation, currentSide);
  const notchR = notch ? notch.r : -1;
  const notchC = notch ? notch.c : -1;

  for (let r = 0; r < visualRows; r++) {
    const rowCells = [];
    html += '<tr>';
    for (let c = 0; c < visualCols; c++) {
      const cell = gridCells2D[r]?.[c];
      const isNotchCell = (r === notchR && c === notchC);

      if (cell) {
        const key = cell.key;
        let val = gridData[key] || '';
        const isInside = cell.inside;

        if (isNotchCell && val === '') {
          val = 'D';
        }
        rowCells.push(val);

        let style = 'width: 32px; height: 32px; font-size: 10pt; font-weight: bold; text-align: center; vertical-align: middle;';

        if (isNotchCell && val === 'D') {
          // Notch D indicator cell 1 row below valid wafer area
          style += ` border: 2px solid ${lineHex}; background-color: #a855f7; color: #ffffff; font-size: 11pt;`;
        } else if (isInside) {
          // 1. Thick border & background color formatting for valid wafer cells.
          //    채움색은 **캔버스와 같은 판정기**를 지난다 — 범례에 없는 값이 빈 칸으로 나가던
          //    결함(INV-1c-3)은 여기서 색을 따로 구하던 데서 나왔다.
          const bgHex = cellFillColor(val, true, colorMap, C);
          style += ` border: 2px solid ${lineHex};`;
          if (val !== '') {
            style += ` background-color: ${bgHex}; color: ${getContrastColor(bgHex)};`;
          } else {
            style += ` background-color: ${insideEmptyHex}; color: ${textEmptyHex};`;
          }
        } else {
          style += ` border: 1px dashed ${lineWeakHex}; background-color: ${outHex}; color: ${textOutHex};`;
        }

        html += `<td style="${style}">${val}</td>`;
      } else {
        const val = isNotchCell ? 'D' : '';
        rowCells.push(val);
        const style = isNotchCell
          ? `border: 2px solid ${lineHex}; background-color: #a855f7; color: #ffffff; font-weight: bold; text-align: center; vertical-align: middle;`
          : `border: 1px dashed ${lineWeakHex}; background-color: ${outHex};`;
        html += `<td style="${style}">${val}</td>`;
      }
    }
    // [F1ⓐ] 우측 보조표. 끄면 이 두 줄은 실행되지 않고 출력은 종전과 바이트로 같다.
    if (headerOn && r < auxLines) {
      html += auxCells(r);
      auxTsv(r).forEach(f => rowCells.push(f));
    }
    // 이 행을 `totalCols`까지 채운다. 끄면 `totalCols === visualCols`라 아무 일도 없다
    // (INV-ⓐ-1 바이트 동일성). 켰을 때 보조표가 끝난 아래쪽 행들은 종전에 **짧은 채로**
    // 나갔고, ragged한 표는 엑셀에서 열이 밀린다.
    for (let k = rowCells.length; k < totalCols; k++) {
      html += `<td style="${gapStyle}"></td>`;
      rowCells.push('');
    }
    html += '</tr>';
    matrix.push(rowCells);
  }

  // 보조표가 격자보다 길면(값 수 > 행 수) 남는 줄을 격자 아래로 흘린다 — 잘라내면
  // 표에서 값이 조용히 사라진다.
  for (let i = visualRows; i < auxLines; i++) {
    let rowHtml = '<tr>';
    const rowCells = [];
    for (let c = 0; c < visualCols; c++) {
      rowHtml += `<td style="${gapStyle}"></td>`;
      rowCells.push('');
    }
    rowHtml += auxCells(i);
    auxTsv(i).forEach(f => rowCells.push(f));
    for (let k = rowCells.length; k < totalCols; k++) {
      rowHtml += `<td style="${gapStyle}"></td>`;
      rowCells.push('');
    }
    html += `${rowHtml}</tr>`;
    matrix.push(rowCells);
  }

  html += '</table>';
  // [MEDIUM-2] 인용은 여기 한 번. `parseTsv(serializeTsv(g)) === g`가 tsv.js의 선언된 계약이고,
  // 붙여넣기가 `parseTsv`로 읽으므로 이 한 줄이 왕복 항등의 근거다.
  const tsv = serializeTsv(matrix);

  if (writeClipboardRich(html, tsv)) {
    if (el.btnCopyExcel) {
      const originalText = el.btnCopyExcel.textContent;
      el.btnCopyExcel.textContent = '✅ Copied to Excel!';
      setTimeout(() => { el.btnCopyExcel.textContent = originalText; }, 1500);
    }
    console.debug(`[map] copied ${visualRows}x${visualCols} grid to clipboard (html+plain)`);
    return;
  }
  // 정직한 실패. 조용히 성공한 척하면 사용자는 낡은 클립보드 내용을 엑셀에 붙인다.
  showToast('복사 실패 — 표를 클릭한 뒤 다시 시도하십시오.', 'error');
}

// ═══════════════════════════════════════════════════════════════════════════════
// [F1ⓑ] 회사 양식 되붙이기 — 왕복의 나머지 절반
//
// INV-F1ⓑ-1: COPY HEADER MODE로 복사한 맵을 그대로 되붙이면 격자가 **셀 하나까지 같다**
//             (빈 칸 포함). 아래의 모든 규칙은 이 한 문장을 정직하게 만들기 위해 있다.
//
// ── 왜 `text/plain`을 읽는가 (rich vs plain, 명시적 결정) ─────────────────────────
// 복사는 `text/html`과 `text/plain`을 **둘 다** 싣는다. 읽는 쪽은 **평문**이다:
//   ① 이 저장소의 TSV 리더는 `tsv.js`의 `parseTsv` **하나뿐**이고 엑셀의 인용 규칙(탭·줄바꿈을
//      품은 셀)을 아는 것도 그것뿐이다. HTML을 읽으려면 표 파서를 새로 써야 하는데, 그것이
//      곧 **두 번째 격자 파서**다 — `compose_map_id`가 세 개였을 때와 같은 형태.
//   ② 사용자가 실제로 되붙이는 것은 **엑셀을 거친 표**다. 엑셀이 내보내는 HTML은 mso 조건부
//      주석·중첩 표·rowspan이 섞인 넓은 표면이고, 우리가 쓴 colspan과 같다는 보장이 없다.
//   ③ 대가는 명시한다: 평문에는 병합이 없으므로 **colspan 구조는 "글자 뒤의 빈 칸"이라는
//      관례로만** 남는다. 그래서 아래 INV-F1ⓑ-3이 부수적 규칙이 아니라 **핵심 규칙**이다.
//   (`navigator.clipboard`는 운영에서 `undefined`다 — 읽기도 `paste` 이벤트의
//    `e.clipboardData`뿐이고, 그래서 붙여넣기는 **버튼이 될 수 없다**. Ctrl+V가 유일한 동선이다.)
//
// INV-F1ⓑ-3: **머리 띠의 빈 칸은 "왼쪽 칸의 연장"이지 "빈 열"이 아니다.**
//   보조표는 `VALUE(3열) COUNT(2열) STACK(2열) DESC(6열)`처럼 열마다 폭이 다르고, 평문에서는
//   `VALUE ␣ ␣ COUNT ␣ STACK ␣ DESC ␣ ␣ ␣ ␣ ␣`로 도착한다. 데이터 줄도 **같은 자리**에 놓인다.
//   그래서 읽기는 **머리줄에서 배운 열 위치**로만 읽는다. 빈 칸을 걷어내고 압축하면
//   `['F','12','','FAIL']`이 `['F','12','FAIL']`이 되어 **DESC가 STACK으로 들어간다** — 화면은
//   멀쩡하고 값만 틀리는, 이 도메인의 그 결함이다.
//
// 🔴 상단 그룹 띠(`Base | 4B12 | 1H | ... `)는 **읽지 않는다.** 그룹 칸의 값은 비어 있을 수
//    있고(그 구역에 자재가 없는 맵), 평문에서 "빈 칸"과 "연장"은 구별되지 않는다 — 폭을 복원하려면
//    글자를 알아야 하고 글자를 읽으려면 폭을 알아야 하는 순환이다. 그래서 정체 확인은 **TITLE
//    한 칸**(항상 첫 열)으로 하고, 그룹 띠는 그리기로만 남긴다. 읽을 수 없는 것을 읽은 척하지 않는다.
//
// INV-F1ⓑ-4: **서버에 아무것도 쓰지 않는다.** 붙여넣기는 화면을 만들 뿐이고 저장은 ⚡ Push다.
//    새 쓰기 경로도 자동 저장도 없다(규율: 읽기 무마찰 · 쓰기 1회 확인).
// ═══════════════════════════════════════════════════════════════════════════════

const pasteBlank = (f) => String(f === null || f === undefined ? '' : f).trim() === '';
const pasteAt = (line, i) => {
  const v = (line || [])[i];
  return (v === null || v === undefined) ? '' : String(v);
};

// 이 줄이 보조표의 **머리줄**인가. 판정기는 새로 만들지 않는다 — `columnIdByHeader`(로스터
// 포함)와 `looksLikeHeader`가 DOE 패널 붙여넣기에서 쓰는 그 함수들이고, `COUNT`를 `IGNORE`로
// 보내는 것도 그 로스터다(INV-F1ⓑ-2: COUNT는 알아보되 **버린다** — 칠한 셀 수는 격자에서 센다).
//
// 오른쪽에서 왼쪽으로 훑는다: 보조표는 줄의 **꼬리**에 있고, 왼쪽의 격자 셀(`1`·`F` 같은 값)은
// 아는 열 이름이 아니므로 거기서 멈춘다. 중간의 빈 칸은 병합의 연장이라 건너뛴다.
//
// 🔴 [MEDIUM-4] 그리고 **`VALUE`에서 멈춘다.** 이 한 줄이 이번 라운드의 수리다.
//    `VALUE`는 보조표의 첫 칸이므로(`auxHeadWords()[0]` — 쓰는 쪽의 배치 그대로) 그 왼쪽은
//    무조건 격자다. 이 종료 조건이 없으면 `columnIdByHeader(f) === null`만 남는데, `5a14e77`이
//    ②→① 왕복을 위해 로스터에 `MAT·BIN·MAP·가용·사용·잔여`를 실은 뒤로는 **격자 셀의 값이
//    그 단어이면 스캔이 멈추지 않았다**: 마지막 격자 열이 `BIN`인 맵에서 `gridWidth`가 9 대신
//    7로 나오고 붙여넣기가 「열 수가 다릅니다」로 거부됐다(실측 2026-07-30). 사유가 원인을
//    가리키지 않으므로 운영자는 멀쩡한 격자 크기·회전을 만진다.
//    ⚠️ 로스터를 좁히는 방식(머리글 네 단어만 통과)도 시도했으나 **버렸다**: `COUNT`는 진짜
//       머리글 단어여서 그 방식으로는 `COUNT`로 칠한 격자 셀을 막을 수 없고, VALUE 종료가
//       있으면 나머지 단어도 전부 막힌다. 증명되지 않는 두 번째 가드는 두지 않는다
//       (하네스: 로스터를 되돌리는 변이가 GREEN으로 남았다 = 그 가드는 채점되지 않는다).
function auxHeaderInLine(line) {
  const width = (line || []).length;
  const positions = [];
  for (let i = width - 1; i >= 0; i--) {
    const f = pasteAt(line, i);
    if (pasteBlank(f)) continue;                    // 병합 연장 · 꼬리 채움
    if (columnIdByHeader(f) === null) break;        // 격자 셀 — 보조표는 여기서 끝난다
    positions.unshift(i);
    if (columnIdByHeader(f) === 'value') break;     // VALUE = 보조표의 첫 칸. 왼쪽은 격자다.
  }
  if (positions.length < 2) return null;
  const words = positions.map(i => pasteAt(line, i).trim());
  if (!looksLikeHeader(words)) return null;
  const ids = words.map(columnIdByHeader);
  // 🔴 `VALUE`가 없으면 보조표가 아니다. 이 조건이 없으면 **상단 그룹 띠**가 머리줄로 오인된다:
  //    자재가 없는 맵에서는 그 줄의 마지막 비어 있지 않은 칸들이 라벨 `1H`·`MID`·`TOP`이고,
  //    셋 다 `DOE_COLUMNS`의 헤더 단어라 `looksLikeHeader`를 그대로 통과한다. 그러면 격자 폭이
  //    그룹 띠에서 계산돼 **표 전체가 어긋난다**.
  if (ids.indexOf('value') < 0) return null;
  return { positions, words, ids };
}

/**
 * [F1ⓑ] 회사 양식 블록을 읽는다. **순수 함수** — DOM도 모듈 상태도 읽지 않는다.
 *
 * 돌려주는 것:
 *   ok / reason      읽을 수 있었나, 아니면 왜 못 읽었나
 *   headerMode       상단 헤더 + 보조표가 실린 복사본인가
 *   title            `테이블 · 맵키` (헤더가 없으면 null — "미상"이지 빈 문자열이 아니다)
 *   gridWidth        격자의 열 수. **보조표 `VALUE`의 열 위치에서 간격 한 칸을 뺀 값**이고,
 *                    이 한 줄이 INV-F1ⓑ-3의 핵심이다 — 병합을 잘못 읽으면 여기가 틀리고
 *                    격자 전체가 조용히 밀린다.
 *   rows             격자 영역만 잘라낸 줄들(각 줄은 gridWidth로 패딩). 프레임 대조는 호출부.
 *   auxWords/auxRecords  보조표 머리줄 단어와 데이터 줄들 — **머리줄에서 배운 열 위치로** 읽는다.
 */
function readCompanyMapBlock(text) {
  // 빈 줄을 버리지 않는다(`dropBlankLines` 없음): 값이 하나도 없는 격자 줄은 **자리를 지키는
  // 데이터**이고, 버리면 그 아래 줄이 통째로 위로 올라온다.
  const lines = parseTsv(text, { trimCells: true });
  if (lines.length === 0) return { ok: false, reason: '클립보드가 비어 있습니다.' };

  let auxLine = -1;
  let aux = null;
  for (let i = 0; i < lines.length; i++) {
    const hit = auxHeaderInLine(lines[i]);
    if (hit) { auxLine = i; aux = hit; break; }
  }

  let gridStart = 0;
  let gridWidth = 0;
  let title = null;
  const headerMode = auxLine >= 0;

  if (headerMode) {
    // 보조표 머리줄은 **격자 0행에 올라탄다**(`auxFields(0) = auxHead`). 그래서 그 줄이 곧
    // 격자의 첫 줄이고, 그 위 두 줄이 TITLE과 그룹 띠다.
    if (auxLine < 2) {
      return { ok: false, reason: '표의 윗줄(제목·그룹 머리)이 없습니다 — 표 전체를 복사하십시오.' };
    }
    gridStart = auxLine;
    gridWidth = aux.positions[0] - HDR_GAP_COLS;
    if (gridWidth <= 0) {
      return { ok: false, reason: '격자 없이 보조표만 붙여넣었습니다 — DOE 표는 오른쪽 DOE 패널에 붙여넣으십시오.' };
    }
    title = pasteAt(lines[auxLine - 2], 0).trim();
  } else {
    // 헤더 없이 격자만 복사한 경우. 같은 코드가 그대로 처리하고, **정체는 미상으로 남는다**.
    gridWidth = lines.reduce((m, l) => Math.max(m, (l || []).length), 0);
    if (gridWidth <= 0) return { ok: false, reason: '읽을 수 있는 격자가 없습니다.' };
  }

  const rows = [];
  for (let i = gridStart; i < lines.length; i++) {
    const out = [];
    for (let c = 0; c < gridWidth; c++) out.push(pasteAt(lines[i], c).trim());
    rows.push(out);
  }

  let auxRecords = null;
  if (headerMode) {
    auxRecords = [];
    const valueSlot = aux.ids.indexOf('value');
    for (let i = gridStart + 1; i < lines.length; i++) {
      // 🔴 **머리줄에서 배운 위치로** 읽는다. 비어 있지 않은 칸을 모으는(압축) 읽기는
      //    STACK이 빈 줄에서 DESC를 STACK 자리로 밀어 넣는다 — INV-F1ⓑ-3.
      const rec = aux.positions.map(p => pasteAt(lines[i], p).trim());
      if (pasteBlank(rec[valueSlot])) break;   // 보조표가 끝났다(그 아래는 빈 칸 채움)
      auxRecords.push(rec);
    }
  }

  return {
    ok: true, reason: '', headerMode, title, gridWidth, rows,
    auxWords: aux ? aux.words.slice() : null,
    auxRecords,
  };
}

/**
 * [F1ⓑ] 읽은 블록이 **지금 이 화면의 프레임**에 놓일 수 있는가. 순수 함수 —
 * `frame = { visualCols, visualRows, title, notch }`만 받는다.
 *
 * 🔴 최선 노력 배치를 하지 않는다. 규격이 안 맞으면 **사유를 붙여 거부**한다. 밀린 격자도
 *    여전히 유효한 격자로 보이기 때문에, 여기서 통과시키면 아무도 못 잡는다.
 */
function checkPasteAgainstFrame(parsed, frame) {
  if (!parsed || !parsed.ok) return { ok: false, reason: parsed ? parsed.reason : '읽지 못했습니다.' };

  if (parsed.gridWidth !== frame.visualCols) {
    return {
      ok: false, reason: `열 수가 다릅니다 — 복사본 ${parsed.gridWidth}열, 현재 화면 ${frame.visualCols}열`
    };
  }
  if (parsed.rows.length < frame.visualRows) {
    return {
      ok: false, reason: `행 수가 다릅니다 — 복사본 ${parsed.rows.length}행, 현재 화면 ${frame.visualRows}행`
    };
  }
  for (let i = frame.visualRows; i < parsed.rows.length; i++) {
    if (parsed.rows[i].some(f => f !== '')) {
      return {
        ok: false, reason: `복사본이 현재 화면보다 깁니다 — ${i + 1}번째 행에 값이 있는데 격자는 ${frame.visualRows}행입니다`
      };
    }
  }
  // 정체. TITLE이 없는 복사본(헤더 미포함)은 "다르다"가 아니라 **미상**이므로 통과시키되,
  // 호출부가 확인창에서 그 사실을 말한다.
  if (parsed.title !== null && parsed.title !== '' && frame.title && parsed.title !== frame.title) {
    return { ok: false, reason: `다른 맵의 복사본입니다 — 복사본 「${parsed.title}」, 현재 화면 「${frame.title}」.` };
  }
  // 프레임 지문. 노치 'D'의 자리는 (회전, 면, bbox)의 함수라, 치수가 같은 채로 프레임만 바뀐
  // 경우(rot 0↔180, front↔back)를 잡는 **유일한** 신호다.
  const n = frame.notch;
  const notchOnGrid = !!n && n.r >= 0 && n.r < frame.visualRows && n.c >= 0 && n.c < parsed.gridWidth;
  if (notchOnGrid && parsed.rows[n.r][n.c] !== 'D') {
    return {
      ok: false, reason: `복사할 때의 회전·면이 지금과 다릅니다 — 노치 표식(D)이 `
        + `${n.r + 1}행 ${n.c + 1}열에 있어야 하는데 「${parsed.rows[n.r][n.c] || '빈 칸'}」입니다.`
    };
  }
  // 🔴 [P0-2] 지문이 **없으면 거부한다.** 종전에는 통과시키고 확인창에 경고 한 줄을 넣었는데,
  //    그 한 줄은 다섯 줄 중 하나였고 회전·면은 치수를 보존하므로 다른 관문이 하나도 걸리지
  //    않는다. 실측: 12x10 격자(마스크 없음, 노치 r10 = 격자 밖)에서 rot 0 복사본을 rot 180
  //    화면에 붙여넣으면 ok=true · notchVerified=false로 통과하고 **물리 키 120개 전부의 값이
  //    바뀐다** — 격자가 통째로 뒤집혀 쓰인다. 복사·회전·Ctrl+V는 전부 평범한 조작이다.
  //    이 파일의 규율은 확인할 수 없는 배치를 **거부**하는 것이다(위 블록 주석: "최선 노력
  //    배치를 하지 않는다"). 노치는 치수 보존 프레임 변경의 유일한 신호이므로, 그 부재는
  //    "괜찮다"가 아니라 "확인할 수 없다"다.
  if (!notchOnGrid) {
    return {
      ok: false, notchVerified: false,
      reason: '노치 표식(D)이 격자 밖이라 복사본의 회전·면을 대조할 수 없습니다'
    };
  }
  return { ok: true, reason: '', notchVerified: true };
}

// [F1ⓑ] 격자 되쓰기. **빈 칸도 쓴다** — 왕복 항등은 "값이 있는 셀을 옮긴다"가 아니라
// "격자가 같아진다"이므로, 복사본에서 비어 있던 셀은 화면에서도 비워야 한다.
//
// 🔴 **노치 'D'는 데이터가 아니라 그림이다.** 복사가 빈 셀에 찍어 넣은 표식이라(`val === ''`일
//    때만 찍힌다), 그대로 되쓰면 원래 없던 셀 값이 하나 생긴다. 그 자리는 웨이퍼 bbox 밖이라
//    `inside`가 거짓 → 화면에 색도 안 나오고 Push가 직렬화하지도 않는데 대비 관문의 분모에는
//    들어간다 = **붙여넣기 한 번이 그 맵의 Push를 영구 거절 상태로 만든다**(Fill All과 같은 계급).
//    그래서 알아보고 버린다 — `COUNT`와 같은 처리다.
function applyPastedGridRows(parsed, frame) {
  const stats = { set: 0, cleared: 0, unchanged: 0, blocked: 0, noCell: 0, notchDropped: 0 };
  const n = frame.notch;
  for (let r = 0; r < frame.visualRows; r++) {
    for (let c = 0; c < frame.visualCols; c++) {
      const cell = gridCells2D[r] ? gridCells2D[r][c] : null;
      if (!cell) { stats.noCell++; continue; }      // 렌더가 만들지 않은 셀 — 저장 대상도 아니다
      let v = parsed.rows[r][c];
      if (n && r === n.r && c === n.c && v === 'D') { v = ''; stats.notchDropped++; }
      const cur = gridData[cell.key] || '';
      if (v === cur) { stats.unchanged++; continue; }
      // 편집 금지 좌표의 단일 관문. 페인팅·지우기가 쓰는 그것과 같은 함수다.
      if (isProtectedFCell(cell.key)) { stats.blocked++; continue; }
      gridData[cell.key] = v;
      if (v === '') stats.cleared++; else stats.set++;
    }
  }
  return stats;
}

// [F1ⓑ] 확인창이 말하는 수. **실제로 놓일 셀 수**여야 한다 — 노치 'D'는 그림이라 버려지므로
// 여기서 빼지 않으면 "178칸"이라 말하고 177칸을 놓는다(실측 2026-07-30, 실맵 4B12). 작지만
// 확인창의 수를 못 믿게 만드는 종류이고, 「화면 34 · DB 33」과 같은 계급이다.
function pastedCellCount(parsed, frame) {
  const n = frame.notch;
  const drawn = (n && n.r >= 0 && n.r < frame.visualRows && n.c >= 0 && n.c < parsed.gridWidth
    && parsed.rows[n.r][n.c] === 'D') ? 1 : 0;
  return parsed.rows.slice(0, frame.visualRows)
    .reduce((sum, row) => sum + row.filter(v => v !== '').length, 0) - drawn;
}

// [F1ⓑ] 보조표 → DOE 행. **패치 적용은 legend 변조 관문(`updateLegendRowForPanel`)을 지난다** —
// 이 파일에 legend를 직접 만지는 두 번째 경로를 만들지 않기 위해서다.
//
// 🔴 정체는 **VALUE**다. DOE 패널의 붙여넣기는 "포커스한 행부터 순서대로"라 VALUE가 개명이지만,
//    이 양식은 **값으로 주소를 매긴 표**라 VALUE가 키다. 그래서 개명은 하지 않는다 —
//    라벨을 키로 삼으면 한 글자 수정에 하위 데이터가 고아가 된다는 그 규율의 반대 방향이다.
// 🔴 **지우지 않는다.** 복사본에 없는 값은 "삭제하라"가 아니라 "이 복사본이 말하지 않은 것"이다.
//    삭제는 DOE 패널의 삭제 버튼이 하고, 그것만이 Push에서 registry 행을 없앨 권한을 갖는다.
// COLOR는 이 양식에 없다 — 기존 값은 자기 색을 유지하고, 새 값은 공용 팔레트 경로가 배정한다.
function applyPastedAuxRows(parsed) {
  const stats = { updated: 0, added: 0, skipped: 0, countsIgnored: 0 };
  if (!parsed.auxRecords || parsed.auxRecords.length === 0) return stats;
  // 열 판정·COUNT 폐기는 전부 `mapPastedGrid`가 한다(머리줄이 있으므로 이름 매칭 경로).
  const grid = [parsed.auxWords.slice()].concat(parsed.auxRecords.map(r => r.slice()));
  const mapped = mapPastedGrid(grid, 'value');
  stats.countsIgnored = (parsed.auxWords || []).filter(w => columnIdByHeader(w) === 'IGNORE').length;

  mapped.rows.forEach(patch => {
    const name = String(patch.value === undefined ? '' : patch.value).trim();
    if (name === '') { stats.skipped++; return; }
    if (!legend.some(l => String(l.value) === name)) {
      // 새 값. 자동 추가 경로는 하나뿐이다(선언된 default_legend 행 → 공용 팔레트 규칙).
      if (autoAddLegendValue(name, patch.desc !== undefined ? String(patch.desc).trim() : '')) {
        stats.added++;
        persistLegend();
      }
    }
    const rest = {};
    if (patch.desc !== undefined) rest.desc = String(patch.desc).trim();
    if (patch.stack !== undefined) rest.stack = String(patch.stack).trim();
    if (Object.keys(rest).length === 0) return;
    const res = updateLegendRowForPanel(name, rest);
    if (res && res.ok) stats.updated++; else stats.skipped++;
  });
  return stats;
}

// ═══════════════════════════════════════════════════════════════════════════════
// [1d] 좌표 표 붙여넣기 — 엑셀 2차원 표(머리줄 = X, 첫 열 = Y)
//
// INV-1d-1: **머리글의 수는 DB 좌표다.** 화면 위치가 아니다. (x,y)가 어느 칸에 앉는가는
//           `getCanvasCellFromDb`가 답한다 — 로드(`loadExistingMap`)가 서버 행을 놓을 때
//           쓰는 **바로 그 함수**이고, 이 파일에 좌표 변환의 두 번째 구현은 없다(불변식 ①).
//           그래서 START X/Y·Y반전·회전·면이 무엇이든 값은 **같은 다이**에 앉는다. 화면이
//           회전하면 그 다이가 놓인 칸이 바뀔 뿐이다.
//
// INV-1d-2: **위치 기반 경로(F1ⓑ)와 배타적이다.** 회사 양식 되붙이기는 화면 행·열로 주소를
//           매기고 이 경로는 좌표로 매긴다. 둘을 가르는 것은 아래 구조 술어 하나뿐이고,
//           술어가 「이 판정기의 것이 아니다」(`none`)라고 답하면 종전 경로가 **한 글자도
//           다르지 않게** 처리한다.
//
// INV-1d-3: **애매하면 거부한다.** 좌표 표처럼 생겼는데 확신할 수 없으면 사유를 붙여
//           거부하고, 최선 노력 배치를 하지 않는다. 틀린 좌표계로 놓인 격자도 여전히
//           멀쩡한 격자로 보이기 때문에 여기서 통과시키면 아무도 못 잡는다.
//
// ── 술어: 원점을 **두 번 유도해 일치할 때만** 채택한다 ─────────────────────────────
// `server/parsers/html_topology_parser.py`(HTMLMatrixMapParser)의 규율을 그대로 옮긴 것이다.
// 그쪽은 병합(rowspan/colspan)을 볼 수 있고 이쪽은 평문이라 판정 재료가 다르지만, **두 유도의
// 사각지대가 서로 반대편에 있어서 일치가 곧 증거**라는 구조는 같다:
//
//   ⓐ 줄 모양(위에서 아래로) — `coordRulerTicks`. 첫 칸이 좌표가 **아니고**, 그 오른쪽으로
//      빈 칸 없이 정수가 2개 이상 이어지며 **강한 단조**(증가 또는 감소)인 줄.
//      사각지대: 진짜 눈금 줄 **위**에 같은 모양의 잡줄(`SLOT 2 3 6 …`)이 있으면 그것이 이긴다.
//   ⓑ 열 모양(아래에서 위로) — 첫 열이 정수인 줄들의 **맨 위 − 1**.
//      사각지대: 격자 위쪽 첫 열에 정수가 하나라도 있으면 원점이 머리 띠로 끌려 올라간다.
//
// 둘은 서로 **다른 입력에서** 틀리므로 불일치는 「이 파서가 아는 모양이 아니다」라는 뜻이다.
// 그때는 승자를 고르지 않고 **사유를 붙여 거부**한다. x·y는 이 맵의 업무 키라, 그럴듯해
// 보이는 틀린 원점은 성능이 떨어진 파싱이 아니라 **존재하지 않는 좌표에 맵 전체를 철하는 것**이다.
//
// 🔴 **강한 단조는 장식이 아니라 판별력의 핵심이다.** 이것이 없으면 값이 전부 정수인 작은
//    격자(마스크 없는 📐 표준 프레임)가 좌표 표로 오인될 수 있다. 축이 같은 좌표를 두 번
//    말하는 일은 원리적으로 없으므로, 이 조건은 좌표 표에는 공짜이고 값 격자에는 치명적이다.
// ⚠️ ⓐ·ⓑ가 **둘 다** 없으면 거부가 아니라 `none`이다 — 평범한 블록을 붙여넣은 것이고, 이
//    경로는 소비자가 둘인 자리다(참조 파서는 소비자가 하나라 그 경우도 거부한다).
// ═══════════════════════════════════════════════════════════════════════════════

const COORD_MIN_TICKS = 2;

// 좌표로 읽히는가. `parseInt`를 쓰지 않는다 — `parseInt('3A')`는 3이고, 그러면 `3A`가 축
// 눈금으로 통과한다. 좌표는 **정수 전체**여야 한다.
const coordInt = (s) => {
  const t = String(s === null || s === undefined ? '' : s).trim();
  return /^[+-]?\d+$/.test(t) ? parseInt(t, 10) : null;
};

const coordMonotonic = (nums) => {
  if (nums.length < 2) return false;
  const up = nums[1] > nums[0];
  for (let i = 1; i < nums.length; i++) {
    if (up ? !(nums[i] > nums[i - 1]) : !(nums[i] < nums[i - 1])) return false;
  }
  return true;
};

// ⓐ 이 줄이 X축 눈금 줄인가. 모양으로만 판정한다.
function coordRulerTicks(line) {
  const width = (line || []).length;
  if (width < 1 + COORD_MIN_TICKS) return null;
  // 모서리 칸은 좌표가 아니다(비었거나 `X\Y` 같은 라벨). 여기가 정수면 그 줄은 데이터 줄이다.
  if (coordInt(pasteAt(line, 0)) !== null) return null;
  const ticks = [];
  for (let c = 1; c < width; c++) {
    const f = pasteAt(line, c);
    if (pasteBlank(f)) {
      // 눈금 시작 전의 빈 칸은 불가(눈금은 1열에서 시작한다). 시작 후의 빈 칸은
      // **꼬리 패딩일 때만** 허용한다 — 중간에 구멍이 나면 눈금 없는 열이 생긴다.
      if (ticks.length === 0) return null;
      for (let d = c; d < width; d++) if (!pasteBlank(pasteAt(line, d))) return null;
      break;
    }
    const v = coordInt(f);
    if (v === null) return null;
    ticks.push({ c, v });
  }
  if (ticks.length < COORD_MIN_TICKS) return null;
  if (!coordMonotonic(ticks.map(t => t.v))) return null;
  return ticks;
}

/**
 * [1d] 클립보드 평문을 좌표 표로 읽는다. **순수 함수** — DOM도 모듈 상태도 읽지 않는다.
 *
 * 돌려주는 것:
 *   kind    'none'   이 판정기의 것이 아니다 → 호출부는 종전 위치 기반 경로로 간다
 *           'refuse' 좌표 표처럼 생겼는데 신뢰할 수 없다 → 사유를 사용자에게 말한다
 *           'ok'     읽었다
 *   cells   [{ x, y, value }] — x·y는 **DB 좌표**, 화면 위치가 아니다
 *   values  빈 칸이 아닌 값의 중복 없는 목록(legend 보충용)
 *   minX/maxX/minY/maxY  표가 말하는 구간. 이 구간 **밖은 건드리지 않는다**.
 */
function readCoordTableBlock(text) {
  const lines = parseTsv(text, { trimCells: true });
  let lastContent = -1;
  for (let r = 0; r < lines.length; r++) {
    if ((lines[r] || []).some(f => !pasteBlank(f))) lastContent = r;
  }
  if (lastContent < 0) return { kind: 'none' };

  // ⓐ 줄 모양 — 위에서 아래로, 첫 번째 눈금 모양 줄.
  let topAnchor = null;
  let topTicks = null;
  for (let r = 0; r <= lastContent; r++) {
    const t = coordRulerTicks(lines[r]);
    if (t) { topAnchor = r; topTicks = t; break; }
  }

  // ⓑ 열 모양 — 첫 열이 좌표인 줄들. 그 맨 위의 **한 줄 위**가 눈금 줄이어야 한다.
  // ⚠️ 부재는 `null`이지 `-1`이 아니다. `yRows[0] === 0`(첫 줄부터 첫 열이 정수)은 「눈금 줄이
  //    있을 자리가 없다」는 뜻이고, 그것은 좌표 표가 아니라 **값이 전부 정수인 평범한 격자**의
  //    모양이다. 둘을 `-1` 하나로 뭉뚱그리면 그 격자가 「엇갈림」으로 거부돼, 종전에 잘 되던
  //    붙여넣기가 사유 없이 막힌다.
  const yRows = [];
  for (let r = 0; r <= lastContent; r++) {
    if (coordInt(pasteAt(lines[r], 0)) !== null) yRows.push(r);
  }
  const bottomAnchor = (yRows.length >= COORD_MIN_TICKS && yRows[0] >= 1) ? yRows[0] - 1 : null;

  // 🔴 **눈금 줄이 없으면 거부가 아니라 양보다**(INV-1d-2). 좌표 표를 좌표 표이게 하는 것은
  //    눈금 줄이고, 그것이 없으면 여기에는 거부할 좌표 표가 애초에 없다 — 첫 열에 정수가 몇 개
  //    있을 뿐이고, **그것은 맵 격자의 평범한 모습이다**(값이 `1`인 칸이 왼쪽 열에 이어진 맵).
  //    실측 위험: 이 조건을 「ⓑ만 있어도 거부」로 두면 머리글 없이 격자만 복사한 정상 되붙이기가
  //    사유 없이 막힌다(원 밖이라 0행 0열은 비어 있고, 그 아래 왼쪽 열은 값으로 채워져 있다).
  //    거부는 **ⓐ가 발화한 뒤에만** 의미가 있다.
  if (topAnchor === null) return { kind: 'none' };

  const refuse = (reason) => ({ kind: 'refuse', reason });

  if (bottomAnchor === null) {
    return refuse(`${topAnchor + 1}번째 줄 아래 첫 열에 Y 좌표가 2개 이상 없습니다`);
  }
  if (topAnchor !== bottomAnchor) {
    return refuse(`X축 줄 판정이 엇갈립니다 — 줄 모양은 ${topAnchor + 1}번째, `
      + `첫 열 Y 좌표는 ${bottomAnchor + 1}번째 줄. 표만 복사하십시오`);
  }
  for (let r = 0; r < topAnchor; r++) {
    if ((lines[r] || []).some(f => !pasteBlank(f))) {
      return refuse(`좌표 표 위 ${r + 1}번째 줄에 표가 아닌 내용이 있습니다`);
    }
  }
  for (let i = 1; i < yRows.length; i++) {
    if (yRows[i] !== yRows[i - 1] + 1) {
      return refuse(`${yRows[i - 1] + 2}번째 줄의 첫 칸이 Y 좌표가 아닙니다`);
    }
  }
  if (yRows[yRows.length - 1] !== lastContent) {
    return refuse(`좌표 표 아래 ${lastContent + 1}번째 줄에 표가 아닌 내용이 있습니다`);
  }
  const yVals = yRows.map(r => coordInt(pasteAt(lines[r], 0)));
  if (!coordMonotonic(yVals)) {
    return refuse('Y 좌표가 한 방향으로 이어지지 않습니다');
  }

  // 눈금이 없는 열에 값이 있으면 그 값은 **놓을 자리가 없다**. 조용히 버리지 않는다.
  const tickCols = new Set(topTicks.map(t => t.c));
  for (let i = 0; i < yRows.length; i++) {
    const line = lines[yRows[i]] || [];
    for (let c = 1; c < line.length; c++) {
      if (!tickCols.has(c) && !pasteBlank(pasteAt(line, c))) {
        return refuse(`${yRows[i] + 1}번째 줄 ${c + 1}번째 칸의 열에 X 좌표가 없습니다`);
      }
    }
  }

  const cells = [];
  const values = [];
  const seen = new Set();
  for (let i = 0; i < yRows.length; i++) {
    const line = lines[yRows[i]];
    for (const t of topTicks) {
      const value = pasteAt(line, t.c).trim();
      cells.push({ x: t.v, y: yVals[i], value });
      if (value !== '' && !seen.has(value)) { seen.add(value); values.push(value); }
    }
  }
  const xVals = topTicks.map(t => t.v);
  return {
    kind: 'ok', reason: '', cells, values,
    minX: Math.min(...xVals), maxX: Math.max(...xVals),
    minY: Math.min(...yVals), maxY: Math.max(...yVals),
    nx: xVals.length, ny: yVals.length,
  };
}

// [1d] 지금 이 화면이 앉아 있는 좌표계. 값을 **새로 유도하지 않는다** — `getGridCellObject`가
// 컨트롤을 읽는 그 여섯 줄 그대로다.
function currentCoordFrame() {
  const { visualCols, visualRows } = getVisualGridDimensions();
  return {
    cols: parseInt(el.gridCols.value, 10) || 10,
    rows: parseInt(el.gridRows.value, 10) || 10,
    rotation: currentRotation,
    side: currentSide,
    invertY: el.gridYInvert ? el.gridYInvert.checked : false,
    startX: parseInt(el.gridStartX.value, 10) || 0,
    startY: parseInt(el.gridStartY.value, 10) || 0,
    visualCols, visualRows,
  };
}

/**
 * [1d] 좌표 표 → **위치 기반 격자**. 표가 덮지 않는 칸은 현재 값을 그대로 실어 「변화 없음」이
 * 되게 한다. 그래서 되쓰기는 `applyPastedGridRows` **하나**가 계속 담당한다 — 이 파일에
 * `gridData`에 쓰는 두 번째 경로를 만들지 않는다.
 *
 * 🔴 (x,y) → (c,r)는 `getCanvasCellFromDb` 한 줄이다. 로드가 쓰는 그 함수이므로 이 붙여넣기의
 *    좌표계는 서버가 돌려준 셀의 좌표계와 정의상 같다.
 * 🔴 `placed`/`cleared`는 **되쓰기가 쓸 판정식과 같은 식**으로 센다(현재 값과 다른가 ·
 *    잠금 셀인가). 확인창의 수와 실제 놓인 수가 갈라지는 「화면 34 · DB 33」을 원천에서 막는다.
 */
function planCoordPaste(coord, cf) {
  const rows = [];
  for (let r = 0; r < cf.visualRows; r++) {
    const line = [];
    for (let c = 0; c < cf.visualCols; c++) {
      const cell = gridCells2D[r] ? gridCells2D[r][c] : null;
      line.push(cell ? (gridData[cell.key] || '') : '');
    }
    rows.push(line);
  }

  const offGrid = [];
  let placed = 0;
  let cleared = 0;
  coord.cells.forEach(t => {
    const at = getCanvasCellFromDb(null, t.x, t.y, cf.cols, cf.rows, cf.rotation, cf.side,
      cf.invertY, cf.startX, cf.startY);
    const onGrid = at.r >= 0 && at.r < cf.visualRows && at.c >= 0 && at.c < cf.visualCols;
    if (!onGrid) {
      // 빈 칸은 놓을 것이 없으므로 격자 밖이어도 해가 없다. 값이 있는데 자리가 없으면
      // **그 값은 사라진다** — 그것이 거부 사유다(호출부가 판정한다).
      if (t.value !== '') offGrid.push({ x: t.x, y: t.y, c: at.c, r: at.r });
      return;
    }
    const cell = gridCells2D[at.r] ? gridCells2D[at.r][at.c] : null;
    rows[at.r][at.c] = t.value;
    if (!cell) return;                                   // 렌더가 만들지 않은 셀 — 되쓰기도 건너뛴다
    const cur = gridData[cell.key] || '';
    if (t.value === cur) return;
    if (isProtectedFCell(cell.key)) return;              // 잠금 — 되쓰기도 막는다
    if (t.value === '') cleared++; else placed++;
  });
  return { rows, placed, cleared, offGrid };
}

// [F1ⓑ] 붙여넣기 동선. **새 컨트롤은 0개다** — 그리고 그것은 선택이 아니라 물리적 제약이다:
// 버튼에서는 클립보드를 읽을 수 없고(`navigator.clipboard`가 운영에서 `undefined`,
// `execCommand('paste')`는 웹 콘텐츠에서 차단), 네이티브 `paste` 이벤트만 내용을 준다.
function onMapGridPaste(e) {
  // DOE 패널(`transfer_plan.onPlanPaste`)이 먼저 처리한 붙여넣기는 그쪽 것이다.
  if (e.defaultPrevented) return;
  // 입력 칸 안의 붙여넣기는 그 칸의 것이다(그리드 화면의 paste 핸들러와 같은 가드).
  const a = document.activeElement;
  if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.hasAttribute('contenteditable'))) return;

  const text = e.clipboardData ? e.clipboardData.getData('text/plain') : '';
  if (!text || text.indexOf('\t') < 0) return;   // 한 칸짜리 붙여넣기는 가로채지 않는다

  // [1d] 좌표 표인가. 판정은 **구조**로만 하고(§readCoordTableBlock), 애매하면 사유를 붙여
  // 거부한다. `none`이면 이 판정기의 것이 아니라는 뜻이라 아래 위치 기반 경로가 종전 그대로
  // 처리한다 — 평범한 블록의 동선은 이 분기 하나를 지나갈 뿐 한 글자도 달라지지 않는다.
  const coord = readCoordTableBlock(text);
  if (coord.kind === 'refuse') {
    e.preventDefault();
    showToast(`붙여넣기를 취소했습니다 — ${coord.reason}`, 'error');
    return;
  }
  const isCoord = coord.kind === 'ok';

  const parsed = isCoord ? null : readCompanyMapBlock(text);
  const { visualCols, visualRows } = getVisualGridDimensions();
  const frame = {
    visualCols, visualRows,
    title: copyTitleText(),
    // 복사가 표식을 찍는 그 자리(`notchMarkCell`). 지문이 없으면 null이고, 그때 아래
    // `checkPasteAgainstFrame`은 **거부**한다 — 확인만 못 한 채 통과시키지 않는다(P0-2).
    //
    // 🔴 좌표 표에는 이 지문이 **필요 없다.** 노치가 필요한 이유는 위치 기반 복사본이 자리를
    //    화면 행·열로만 말하기 때문이고(회전·면은 치수를 보존하므로 다른 관문이 못 잡는다),
    //    좌표 표는 자기 자리를 x·y로 **직접 말한다**. 프레임이 달라지면 값이 앉는 **칸**이
    //    바뀔 뿐 **다이**는 그대로다 — 그것이 「db 좌표로 읽기」의 뜻이다.
    notch: notchMarkCell(currentRotation, currentSide),
  };

  let plan = null;
  let lines = null;

  if (isCoord) {
    const cf = currentCoordFrame();
    plan = planCoordPaste(coord, cf);
    if (plan.offGrid.length > 0) {
      e.preventDefault();
      const f0 = plan.offGrid[0];
      showToast(`붙여넣기 취소 — 표의 좌표 X ${coord.minX}~${coord.maxX} · Y ${coord.minY}~${coord.maxY}가 `
        + `격자를 벗어납니다 (${plan.offGrid.length}칸, 예: x=${f0.x} y=${f0.y})`, 'error');
      return;
    }
    e.preventDefault();
    lines = [
      '좌표 표 붙여넣기 (DB 좌표 기준)',
      `X ${coord.minX}~${coord.maxX} · Y ${coord.minY}~${coord.maxY} 구간 ${coord.nx}×${coord.ny}칸만 바꿉니다 `
        + `(${plan.placed}칸 입력 · ${plan.cleared}칸 비움)`,
      '서버 기록 없음 — 저장은 [⚡ Push Map Data]',
    ];
  } else {
    const verdict = checkPasteAgainstFrame(parsed, frame);
    if (!verdict.ok) {
      // 격자 모양이 전혀 아닌 클립보드(다른 화면에서 긁어온 표)는 조용히 지나간다 —
      // 여기서 토스트를 띄우면 아무 붙여넣기에나 경고가 뜬다.
      if (parsed.ok) {
        e.preventDefault();
        showToast(`붙여넣기를 취소했습니다 — ${verdict.reason}`, 'error');
      }
      return;
    }
    e.preventDefault();

    const painted = pastedCellCount(parsed, frame);
    const auxCount = parsed.auxRecords ? parsed.auxRecords.length : 0;
    lines = [
      parsed.title ? `「${parsed.title}」 복사본 붙여넣기` : '머리글 없음 — 어느 맵의 복사본인지 미상',
      `격자 ${visualCols}×${visualRows} 전체를 교체합니다 (값 있는 셀 ${painted}칸, 나머지는 비움)`,
      auxCount > 0 ? `DOE ${auxCount}행(VALUE·STACK·DESC)도 함께 적용` : '',
      // [P0-2] 종전의 「⚠ 회전·면은 대조하지 못했습니다」 줄은 **삭제**했다. 지금은 대조하지
      // 못하면 `checkPasteAgainstFrame`이 거부하므로 여기까지 오는 복사본은 전부 대조를 통과한
      // 것이고, 그 문구는 절대 뜨지 않는 죽은 줄이 된다(살아 보이는 죽은 코드 금지).
      '서버 기록 없음 — 저장은 [⚡ Push Map Data]',
    ].filter(Boolean);
  }

  // 쓰기 1회 확인. 화면을 갈아 끼우므로 [🧹 Clear Grid]·[🎨 Fill All]과 같은 급이고,
  // 확인창은 **경로가 둘이어도 하나**다. 서버에 아무것도 안 나간다는 것을 여기서 말한다
  // (INV-F1ⓑ-4 · INV-1d-1).
  if (!confirm(`${lines.join('\n')}\n\n계속하시겠습니까?`)) return;

  // 🔴 되쓰기는 **한 함수**다. 좌표 경로는 표를 위치 격자로 먼저 옮겨 놓고(§planCoordPaste)
  //    같은 함수에 넘긴다 — `gridData`에 쓰는 두 번째 경로를 만들지 않기 위해서다.
  //    노치 표식은 좌표 표에 없으므로 그 갈래를 꺼 둔다(`notch: null`).
  const gridStats = plan
    ? applyPastedGridRows({ rows: plan.rows }, Object.assign({}, frame, { notch: null }))
    : applyPastedGridRows(parsed, frame);
  // 좌표 표에는 보조표가 없다. 대신 legend에 없는 값은 **공용 자동 추가 관문**으로 채운다
  // (`ensureLegendValues` → `autoAddLegendValue`) — 위치 기반 경로가 보조표에서 얻는 것을
  // 이 경로는 격자 값에서 얻는다. 두 번째 팔레트 규칙을 만들지 않는다.
  const auxStats = plan
    ? { updated: 0, added: ensureLegendValues(coord.values).length, skipped: 0, countsIgnored: 0 }
    : applyPastedAuxRows(parsed);

  renderLegendTable();
  updateLegendCounts();
  renderGridCanvas();
  scheduleCellDraft();

  // 저장되지 않을 셀은 **보고한다** — 조용히 버리지도, 조용히 남기지도 않는다(INV-F1ⓑ-5).
  // 분류기는 새로 만들지 않는다: `classifyUnsavableCells`가 Push 관문이 쓰는 그것이고,
  // 「서버가 보낸 적 없음이 증명된」 키만 stray로 갈라 준다.
  const un = classifyUnsavableCells();
  const notes = [];
  if (gridStats.blocked > 0) notes.push(`잠금 셀 ${gridStats.blocked}칸은 그대로 두었습니다`);
  if (un.offGrid.length > 0) notes.push(`격자 밖 ${un.offGrid.length}칸`);
  if (un.outsideRetained.length > 0) notes.push(`유효 다이 밖 ${un.outsideRetained.length}칸(서버 출처 미확인 — 남겨 둠)`);
  if (un.outsideStray.length > 0) notes.push(`유효 다이 밖 ${un.outsideStray.length}칸(서버에 없던 셀)`);
  // [1e] Speak only when there is something to say. With `notes` empty this is a pure
  // success confirmation whose result is already visible in the grid, the legend and the DOE
  // table (and the paste passed a confirm already). With `notes` present it carries facts
  // about cells that will NOT be saved, so it stays a toast.
  const pasteMsg = `붙여넣기 완료 — ${gridStats.set}칸 입력 · ${gridStats.cleared}칸 비움`
    + `${auxStats.updated + auxStats.added > 0
      ? (plan ? ` · legend ${auxStats.added}행 추가` : ` · DOE ${auxStats.updated + auxStats.added}행`) : ''}`
    + `${notes.length ? ` (${notes.join(' · ')})` : ''}`;
  if (notes.length) showToast(pasteMsg, 'warning');
  else console.debug(`[map] ${pasteMsg}`);
  console.debug(plan ? '[map] pasted coordinate table' : '[map] pasted company block', {
    gridStats, auxStats, unsavable: {
      offGrid: un.offGrid.length, outsideRetained: un.outsideRetained.length, outsideStray: un.outsideStray.length
    }
  });
}

// ====================================================
// [재설계 v2] 편집 프레임 스택 + 로드 정체성 핀
//
//   "계획 = 지금 열어 편집 중인 그 맵." 별도 계획 맵 사본(transfer_plan_map)은 없다.
//   자재 맵으로의 이동은 모드 전환이 아니라 **맵을 하나 더 연 것**이다 —
//   현재 편집 상태를 프레임으로 push 하고, 뒤로가기로 pop 해 그대로 복원한다.
//
//   ⚠️ 복원 대상에 overlayLayers·캔버스 스크롤이 포함된다.
//      (구 모드 전환은 진입/이탈 양쪽에서 clearOverlayLayers()를 불러 오버레이를 전멸시켰고,
//       스크롤은 스냅샷에 아예 없었다 — 두 누락 모두 여기서 해소한다.)
// ====================================================
let editorFrames = [];       // 편집 프레임 스택 (깊이 N)

// [V1 effort instrument] Route ids for countNav(). Deliberately TABLE-AGNOSTIC: the served
// allowlist declares the plan -> material-map detour ONCE instead of once per stage table,
// and a new stage table needs no config edit to be classified correctly.
//   `map_editor`           - the main (depth 0) editing surface
//   `map_editor:material`  - a material-map frame stacked on top of it (depth >= 1)
// Transitions this file emits, and why each is a screen move at all:
//   map_editor > map_editor            table switch / map load: grid wiped, DOE reseeded,
//                                      overlays cleared, identity pin voided
//   map_editor > map_editor:material   frame push (the user's "DOE -> dt map routing")
//   map_editor:material > map_editor   frame pop - state restored VERBATIM by
//                                      snapshotEditorState/restoreEditorState
//   map_editor > grid                  full page load; nothing survives
// Classification is NOT decided here. Every one of these defaults to COUNTED; only the
// served config can declare a transition context-preserving.
const ROUTE_MAIN = ROUTES.MAP_EDITOR;
const ROUTE_MATERIAL = `${ROUTES.MAP_EDITOR}:material`;
function effortRoute() {
  return editorFrames.length > 0 ? ROUTE_MATERIAL : ROUTE_MAIN;
}
let loadedIdentity = null;   // { table, mapKey } — 로드 순간 고정되는 정체성 핀
let framePushed = false;     // 현재 프레임에서 Push 했는가 (뒤로가기 경고용)
// [fix E] Edited since this frame's map was opened (grid-cell write or legend commit).
// framePushed starts false at frame open, so `!framePushed && cells>0` alone made
// merely VIEWING a non-empty material map prompt on back. The back-confirm now
// requires an actual edit. Set by the two persistence gateways every editing path
// already funnels through (persistLegend / scheduleCellDraft); reset alongside
// framePushed in setLoadedIdentity. Draft restores deliberately do NOT set it: the
// restored content survives in the draft slot, so backing out loses nothing.
let frameTouched = false;

// ── 미저장 편집 가드 — 판정과 권유 문구를 만드는 **한 곳** ──────────────────────────────
//
// [fix E-3] 이 함수가 존재하는 이유는 판정이 두 번 철자되어 **두 문이 서로 다른 답을 냈기**
// 때문이다. 뒤로가기(`popMapFrame`)는 물었고, 맵 교체 로드(`loadExistingMap`)는 묻지도 않고
// 첫 세 줄에서 선언을 버렸다 — 같은 미저장 선언이 한 문에서는 지켜지고 다른 문에서는
// 사라졌다. 문이 세 번째로 늘어도 판정을 다시 쓸 일이 없도록, 「미저장인가」와 「어느 저장을
// 권하는가」를 여기서만 만든다. 이것이 이 라운드의 실제 교훈이다: 같은 질문의 두 번째 철자.
//
// 반환값이 곧 판정이다 — 깨끗하면 `null`(= 묻지 않는다), 미저장이면 확인문에 넣을 **권유
// 한 줄**. 상황을 말하는 첫 문장은 부르는 쪽이 쓴다: 「나가는 것」과 「덮어쓰는 것」은 다른
// 일이고, 그 둘을 같은 문장으로 말하면 사용자는 무슨 일이 일어나는지 알 수 없다.
function unsavedWorkNotice() {
  if (framePushed || !frameTouched) return null;
  // ⚡ Push는 `replace_map`(셀 전량 재기록)이다. 셀을 하나도 건드리지 않은 변경에 그것을
  // 권하면 사람들은 모든 것을 Push로 배운다. `legendDirty`가 셀·legend 초안 작업의 기존
  // 기록이고(선언 경로를 제외한 모든 `frameTouched` 지점이 같은 호흡으로 세운다), 그것이
  // 없다는 것은 이 편집이 **선언뿐**이라는 뜻이다.
  return legendDirty
    ? `· 셀 값이 바뀌었습니다 — [⚡ Push]로 저장하십시오.\n`
    : `· 셀은 하나도 바뀌지 않았습니다 — [📐 규격만 저장]이면 충분합니다.\n`;
}

function snapshotEditorState() {
  const metaValues = {};
  document.querySelectorAll('[id^="meta-input-"]').forEach(input => {
    metaValues[input.id.replace('meta-input-', '')] = input.value;
  });
  return {
    selectedTable,
    tableSchema,
    // [보존 누락 ①] 오버레이 레이어 — 돌아오면 겹쳐 보던 맵이 그대로 있어야 한다
    overlayLayers: overlayLayers.slice(),
    overlayGeomSig,
    // [보존 누락 ②] 캔버스 스크롤 위치
    scrollLeft: el.mapWorkspace ? el.mapWorkspace.scrollLeft : 0,
    scrollTop: el.mapWorkspace ? el.mapWorkspace.scrollTop : 0,
    loadedIdentity: loadedIdentity ? { ...loadedIdentity } : null,
    // The legend below was restored from this map's registry, so its replace
    // authority belongs with it. Dropping it here would silently downgrade the
    // parent map to upsert-only after a round trip = deletions stop sticking.
    legendReplaceScope: legendReplaceScope ? { ...legendReplaceScope } : null,
    // A conflict is a fact about the parent map's server state, not about the frame
    // we are entering. Dropping it here would let a round trip clear the refusal.
    legendConflict: legendConflict ? { ...legendConflict } : null,
    legendSaveState: { ...legendSaveState },
    // [fix B/E] Per-frame edit state must survive the round trip: without these a
    // material-map detour cleared the parent's unsaved-edit chip (legendDirty) and
    // its back-guard baseline (frameTouched) on return.
    legendDirty,
    frameTouched,
    framePushed,
    tableSelectValue: el.tableSelect ? el.tableSelect.value : '',
    gridData: { ...gridData },
    loadedFCells: new Set(loadedFCells),
    legend: cloneLegend(legend),
    // The seed travels with the legend it describes. Without it, coming back from a
    // material-map frame would leave marked rows with no seed to compare against, and
    // `reconcileVocabClaims` would read every one of them as edited - re-opening the
    // contamination path one round trip later.
    legendVocabularySeed: new Map(legendVocabularySeed),
    legendMeta: { ...legendMeta },
    activeBrush,
    metaValues,
    colX: el.colMapX ? el.colMapX.value : '',
    colY: el.colMapY ? el.colMapY.value : '',
    colVal: el.colMapVal ? el.colMapVal.value : '',
    gridCols: el.gridCols.value,
    gridRows: el.gridRows.value,
    gridStartX: el.gridStartX.value,
    gridStartY: el.gridStartY.value,
    gridYInvert: el.gridYInvert.checked,
    showAnnotations: el.showAnnotations ? el.showAnnotations.checked : true,
    physWaferDia: el.physWaferDia ? el.physWaferDia.value : '300',
    physChipX: el.physChipX ? el.physChipX.value : '2.5',
    physChipY: el.physChipY ? el.physChipY.value : '2.5',
    physOffsetX: el.physOffsetX ? el.physOffsetX.value : '0',
    physOffsetY: el.physOffsetY ? el.physOffsetY.value : '0',
    physEdgeMargin: el.physEdgeMargin ? el.physEdgeMargin.value : '3',
    rotation: currentRotation,
    side: currentSide,
    // [M4①] 유효 다이의 근거는 **그 맵의** 성질이다. 프레임 왕복에서 들고 다니지 않으면
    // 자재 맵에서 돌아왔을 때 부모 맵이 자식의 마스크로 재단된다 — 화면은 멀쩡하고
    // 값만 틀리는 그 결함이다. Set은 얕게 넘겨도 안전하다(해석 이후 불변).
    validDie: validDie ? { ...validDie } : null,
  };
}

function restoreEditorState(s) {
  selectedTable = s.selectedTable;
  tableSchema = s.tableSchema;
  if (el.tableSelect) el.tableSelect.value = s.tableSelectValue;
  if (tableSchema) {
    fillColumnDropdowns();
    if (s.colX && el.colMapX) el.colMapX.value = s.colX;
    if (s.colY && el.colMapY) el.colMapY.value = s.colY;
    if (s.colVal && el.colMapVal) el.colMapVal.value = s.colVal;
    renderMetadataInputs();
    Object.entries(s.metaValues).forEach(([col, val]) => {
      const input = document.getElementById(`meta-input-${col}`);
      if (input) input.value = val;
    });
  }
  el.gridCols.value = s.gridCols;
  el.gridRows.value = s.gridRows;
  el.gridStartX.value = s.gridStartX;
  el.gridStartY.value = s.gridStartY;
  el.gridYInvert.checked = s.gridYInvert;
  if (el.showAnnotations) el.showAnnotations.checked = s.showAnnotations;
  if (el.physWaferDia) el.physWaferDia.value = s.physWaferDia;
  if (el.physChipX) el.physChipX.value = s.physChipX;
  if (el.physChipY) el.physChipY.value = s.physChipY;
  if (el.physOffsetX) el.physOffsetX.value = s.physOffsetX;
  if (el.physOffsetY) el.physOffsetY.value = s.physOffsetY;
  if (el.physEdgeMargin) el.physEdgeMargin.value = s.physEdgeMargin;
  currentRotation = s.rotation;
  currentSide = s.side;
  boundingBoxCache = {};
  updateOrientationUI();

  gridData = { ...s.gridData };
  loadedFCells = new Set(s.loadedFCells);
  legend = cloneLegend(s.legend);
  legendVocabularySeed = new Map(s.legendVocabularySeed || []);
  legendMeta = { ...s.legendMeta };
  activeBrush = s.activeBrush;

  // [보존 누락 ①] 오버레이 복원 — 규격이 함께 복원되므로 물리 키 재계산은 시그니처 비교로 판정
  overlayLayers = Array.isArray(s.overlayLayers) ? s.overlayLayers.slice() : [];
  overlayGeomSig = s.overlayGeomSig || '';
  syncOverlayGeometry();
  recomputeActiveOverlays();
  renderOverlayList();

  loadedIdentity = s.loadedIdentity ? { ...s.loadedIdentity } : null;
  legendReplaceScope = s.legendReplaceScope ? { ...s.legendReplaceScope } : null;
  legendConflict = s.legendConflict ? { ...s.legendConflict } : null;
  legendSaveState = s.legendSaveState ? { ...s.legendSaveState } : { status: 'idle', at: '', error: '' };
  legendDirty = !!s.legendDirty;     // [fix B/E] restored with the frame they describe
  frameTouched = !!s.frameTouched;
  framePushed = !!s.framePushed;
  // [M4①] 마스크도 그 프레임의 것으로 되돌린다. 캡처하지 않은 옛 상태에서 되돌아오는
  // 경우(`validDie` 부재)는 선언 없음으로 읽어 종전 동작이 된다.
  validDie = s.validDie ? { ...s.validDie } : { basis: 'circle', keys: null, reason: '', ref: null };
  // 마스크는 이제 **원점 상자의 근거**이기도 하다(§getWaferBoundingBox). 위쪽의 캐시 비우기는
  // 이 복원보다 앞이라, 그 사이에 계산된 항목은 떠나는 프레임의 근거로 만들어져 있다.
  boundingBoxCache = {};
  renderValidDieChip();
  // [M4②] 지정 칸은 마스크와 같은 프레임의 것이다 — 되돌리지 않으면 부모 맵으로 돌아온 뒤
  // Push가 자재 맵의 선언을 부모에 쓴다.
  syncValidDieRefControls();

  renderLegendTable();
  renderGridCanvas();

  // [보존 누락 ②] 스크롤은 캔버스 레이아웃 확정 뒤에 복원해야 값이 살아남는다
  if (el.mapWorkspace) {
    requestAnimationFrame(() => {
      el.mapWorkspace.scrollLeft = s.scrollLeft || 0;
      el.mapWorkspace.scrollTop = s.scrollTop || 0;
    });
  }
}

// 저장된 grid_metadata 객체를 에디터 규격 UI에 적용 (loadExistingMap 'meta' 분기 미러)
function applyGridMetaObject(meta) {
  if (!meta || typeof meta !== 'object') return;
  if (meta.grid_cols !== undefined) el.gridCols.value = meta.grid_cols;
  if (meta.grid_rows !== undefined) el.gridRows.value = meta.grid_rows;
  if (meta.grid_start_x !== undefined) el.gridStartX.value = meta.grid_start_x;
  if (meta.grid_start_y !== undefined) el.gridStartY.value = meta.grid_start_y;
  if (meta.grid_y_invert !== undefined) el.gridYInvert.checked = !!meta.grid_y_invert;
  currentRotation = meta.rotation || 0;
  currentSide = meta.side || 'front';
  if (meta.phys_wafer_dia !== undefined && el.physWaferDia) el.physWaferDia.value = meta.phys_wafer_dia;
  if (meta.phys_chip_x !== undefined && el.physChipX) el.physChipX.value = meta.phys_chip_x;
  if (meta.phys_chip_y !== undefined && el.physChipY) el.physChipY.value = meta.phys_chip_y;
  if (meta.phys_offset_x !== undefined && el.physOffsetX) el.physOffsetX.value = meta.phys_offset_x;
  if (meta.phys_offset_y !== undefined && el.physOffsetY) el.physOffsetY.value = meta.phys_offset_y;
  if (meta.phys_edge_margin !== undefined && el.physEdgeMargin) el.physEdgeMargin.value = meta.phys_edge_margin;
  boundingBoxCache = {};
  updateOrientationUI();
}

// 맵 종류(tape/base/core)에 맞는 규격 프리셋 탐색 (M1 전례: key -> name 순 정규식)
function findPresetByKind(kind) {
  const table = {
    tape: [/tape/i, /dt/i],
    base: [/base/i, /bond/i],
    core: [/core/i, /eds/i, /defect/i],
  };
  const patterns = table[String(kind || '').toLowerCase()] || [];
  if (patterns.length === 0) return null;
  for (const re of patterns) {
    const byKey = Object.entries(serverPresets).find(([key]) => re.test(key));
    if (byKey) return { key: byKey[0], ...byKey[1] };
  }
  for (const re of patterns) {
    const byName = Object.entries(serverPresets).find(([, p]) => p && re.test(String(p.name || '')));
    if (byName) return { key: byName[0], ...byName[1] };
  }
  return null;
}

// visual 좌표 셀들을 현재 그리드 규격으로 gridData에 반영 (loadExistingMap 좌표 경로 재사용)
function applyCellsToGrid(cells) {
  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert.checked;
  let count = 0;
  (Array.isArray(cells) ? cells : []).forEach(cell => {
    const xn = Number(cell.x);
    const yn = Number(cell.y);
    const val = cell.val !== null && cell.val !== undefined ? String(cell.val).trim() : '';
    if (!Number.isFinite(xn) || !Number.isFinite(yn) || val === '') return;
    const c = getCanvasCellFromDb(null, xn, yn, cols, rows, currentRotation, currentSide, invertY, startX, startY);
    const physical = getDieIndex(null, c.c, c.r, cols, rows, currentRotation, currentSide);
    gridData[`${physical.x}_${physical.y}`] = val;
    count++;
  });
  return count;
}

// 현재 격자에서 계획 셀 수집 (pushMapData와 동일 기준: inside && 값 있는 셀, visual 좌표)
// [F2] 기준을 다시 쓰지 않는다 — `eachSavableCell`이 그 기준의 유일한 구현이다. 종전의
// 손으로 옮겨 적은 사본은 빈 값 판정이 Push와 미묘하게 달랐다(숫자 0의 처리).
function collectPlanCells() {
  const cells = [];
  const counts = {};
  eachSavableCell((cellObj, val) => {
    cells.push({ x: cellObj.x, y: cellObj.y, val });
    counts[val] = (counts[val] || 0) + 1;
  });
  return { cells, counts };
}

// ── 로드 정체성 (Push 가드 전용 — 조회 흐름에는 일절 개입하지 않는다) ────────
//
// 규율: **읽기는 무마찰, 쓰기는 1회 확인.**
//   맵 키를 바꿔가며 과거 맵을 훑는 조회 동선(키 입력 → Load → 다시 다른 키 → Load …)에는
//   잠금·해제·확인·경고가 **한 번도 끼어들지 않는다.** 종전의 상시 잠금(readOnly)과
//   좌측 정체성 핀은 그 마찰의 원인이라 제거했다.
//
//   대신 loadedIdentity는 계속 추적한다 — 오직 Push(쓰기) 직전 1회 확인에만 쓴다.
//   Push는 replace_map이라 맵 키가 어긋나면 **남의 맵 셀이 전량 삭제**되기 때문이다.
function currentIdentityMismatch() {
  if (!loadedIdentity) return null;
  const curKey = getCurrentMapKey() || '';
  if (selectedTable === loadedIdentity.table && curKey === loadedIdentity.mapKey) return null;
  return { table: selectedTable, mapKey: curKey };
}

function setLoadedIdentity(table, mapKey) {
  loadedIdentity = (table && mapKey) ? { table: String(table), mapKey: String(mapKey) } : null;
  // Replace authority belongs to ONE map. The moment the loaded map is not the map
  // whose registry we read, the claim is void - a `replace_map` legend write under a
  // stale scope would purge another map's rows. A fresh grant survives because
  // loadExistingMap grants it for exactly the identity it then pins here.
  if (!loadedIdentity || !legendReplaceScope
    || legendReplaceScope.table !== loadedIdentity.table
    || legendReplaceScope.mapKey !== loadedIdentity.mapKey) {
    legendReplaceScope = null;
  }
  framePushed = false;
  frameTouched = false;   // [fix E] a (re)load starts a clean edit baseline for the frame
}

// ── 편집 프레임 스택 (자재 맵 왕복) ──────────────────────────
function frameTitle(f) {
  const key = (f && f.loadedIdentity) ? f.loadedIdentity.mapKey : '(미로드)';
  return `${f ? f.selectedTable : ''} · ${key}`;
}

function currentFrameTitle() {
  return `${selectedTable} · ${loadedIdentity ? loadedIdentity.mapKey : (getCurrentMapKey() || '(미로드)')}`;
}

function renderBreadcrumb() {
  const bar = document.getElementById('map-breadcrumb');
  if (!bar) return;
  if (editorFrames.length === 0) { bar.style.display = 'none'; bar.innerHTML = ''; return; }
  bar.style.display = 'flex';
  const trail = editorFrames.map(frameTitle).concat([currentFrameTitle()]);
  bar.innerHTML = `<button type="button" class="bc-back" id="btn-frame-back">← 뒤로</button>`
    + trail.map((t, i) => (i === trail.length - 1)
      ? `<span class="bc-cur">${escapeHtmlAttr(t)}</span>`
      : `<span class="bc-up">${escapeHtmlAttr(t)}</span><span class="bc-sep">›</span>`).join('');
  const back = bar.querySelector('#btn-frame-back');
  if (back) back.addEventListener('click', () => popMapFrame());
}

// 확인 프롬프트 없이 테이블만 갈아끼운다 (switchTable의 "맵 유지?" 질문 우회 —
// 프레임 진입은 사용자가 이미 "그 자재 맵을 열겠다"고 명시한 동작이다).
async function switchTableQuiet(tableName) {
  selectedTable = tableName;
  const paintRulesReady = fetchPaintRules(tableName);
  const res = await fetch(`${API_BASE}/tables/${tableName}/schema`);
  tableSchema = await res.json();
  // [F1] The dropdown preselect reads the served-binding cache that this round-trip
  // fills. Fire-and-forget here would let the frame's auto-load run with the FIRST
  // column selected as x/y — a silent 0-cell (or wrong-column) load. Runs in parallel
  // with the schema fetch above; fetchPaintRules never throws.
  await paintRulesReady;
  fillColumnDropdowns();
  renderMetadataInputs();
  // An empty DOE, not the map's legend - and this is not a shortcut. openMapFrame fills the
  // meta inputs AFTER this returns, so no map key exists yet at this line; the map-scoped
  // legend arrives with the loadExistingMap that follows.
  seedEmptyDoe();
  renderLegendTable();
  gridData = {};
  loadedFCells.clear();
}

// 자재 맵(또는 임의의 맵)을 새 프레임으로 연다.
//   spec = { table, metaValues:{col:val}, presetKind }
// 맵이 없으면 빈 격자 + 규격 프리셋으로 열린다 — "만들러 간다"와 "고치러 간다"가 같은 동작.
async function openMapFrame(spec) {
  if (!spec || !spec.table) return { ok: false, error: '대상 테이블이 없습니다.' };
  if (editorFrames.length >= 4) return { ok: false, error: '편집 스택이 너무 깊습니다 (최대 4단).' };
  // [V1 effort instrument] Captured BEFORE the push - effortRoute() reads editorFrames.length.
  const navFrom = effortRoute();
  const frame = snapshotEditorState();

  try {
    editorFrames.push(frame);
    loadedIdentity = null;
    legendReplaceScope = null;   // the new frame has not read any registry yet
    legendConflict = null;       // and it carries no conflict of its own yet
    legendSaveState = { status: 'idle', at: '', error: '' };
    overlayLayers = [];
    recomputeActiveOverlays();
    renderOverlayList();

    if (el.tableSelect) {
      if (!Array.from(el.tableSelect.options).some(o => o.value === spec.table)) {
        const opt = document.createElement('option');
        opt.value = spec.table;
        opt.textContent = spec.table;
        el.tableSelect.appendChild(opt);
      }
      el.tableSelect.value = spec.table;
    }
    await switchTableQuiet(spec.table);

    Object.entries(spec.metaValues || {}).forEach(([col, val]) => {
      const input = document.getElementById(`meta-input-${col}`);
      if (input) input.value = val === null || val === undefined ? '' : String(val);
    });

    const r = await loadExistingMap({ quiet: true, allowEmpty: true });
    if (r && r.cancelled) {
      // [fix G] The user dismissed the load (frame-choice modal / empty map key).
      // This used to fall through as "map not built yet" — a frame opened on an EMPTY
      // grid with a false "맵이 아직 없습니다" toast, or rolled back with no feedback
      // at all. Roll the frame back exactly like a failed entry, and SAY so once.
      const f = editorFrames.pop();
      if (f) restoreEditorState(f);
      renderBreadcrumb();
      notifyMapContext();
      showToast('맵 열기를 취소했습니다 — 이전 화면으로 돌아갑니다.', 'info');
      return { ok: false, cancelled: true };
    }
    if (!r || r.count === 0) {
      // 미구축 자재 — 빈 격자 + 규격 프리셋
      const preset = findPresetByKind(spec.presetKind);
      if (preset) applyPresetObject(preset);
      const key = getCurrentMapKey();
      setLoadedIdentity(spec.table, key);
      renderGridCanvas();
      showToast(`${spec.table} · ${key || ''} — 맵이 아직 없습니다. 빈 격자로 열었습니다.`, 'info');
    }
    // [V1 effort instrument] Only here: both success shapes (map loaded / opened empty)
    // reach this line, while the cancel branch above and the catch below rolled the frame
    // back and returned already - a frame that never opened is not a screen move. The
    // nested loadExistingMap deliberately does NOT count; this ONE call is the transition.
    countNav(navFrom, ROUTE_MATERIAL);
    renderBreadcrumb();
    notifyMapContext();
    return { ok: true };
  } catch (e) {
    // 진입 실패 시 프레임을 되돌린다 (반쯤 열린 상태로 두지 않는다)
    const f = editorFrames.pop();
    if (f) restoreEditorState(f);
    renderBreadcrumb();
    notifyMapContext();
    return { ok: false, error: e && e.message ? e.message : String(e) };
  }
}

function popMapFrame() {
  if (editorFrames.length === 0) return false;
  // [fix E] Prompt only when this frame was actually edited since it opened AND the
  // edits were not pushed. A merely-viewed non-empty material map goes back silently.
  // [fix E-2] THE CELL-COUNT TERM IS GONE. It was a stand-in for "this frame holds work",
  // written before `frameTouched` existed — back then the predicate really was
  // `!framePushed && cells>0`, and that is what made mere VIEWING prompt. Once an actual edit
  // is required, the count only SUBTRACTS truth, and it subtracted it in three live shapes:
  //   · `clearGrid()` sets `gridData = {}` and drafts — "delete every value in the grid",
  //     then back, discarded in silence;
  //   · a valid-die declaration on a map with no painted cells (a template map, or a map
  //     being declared before it is filled) — unsaved work with zero cells by construction;
  //   · the stray-key cleanup (:5853) can empty the object the same way.
  // Viewing still cannot prompt, because viewing sets neither flag.
  // [fix E-3] The predicate and the writer advice now come from `unsavedWorkNotice()`, so the
  // map-replacing LOAD asks the identical question. Only the first sentence is written here,
  // because leaving and overwriting are different things to be told.
  const notice = unsavedWorkNotice();
  if (notice && !confirm(
    `이 맵의 편집을 저장하지 않았습니다.\n\n` + notice +
    `\n[확인] 저장하지 않고 돌아가기\n[취소] 이 화면에 남기`
  )) return false;

  const from = { table: selectedTable, mapKey: loadedIdentity ? loadedIdentity.mapKey : (getCurrentMapKey() || ''), pushed: framePushed };
  const frame = editorFrames.pop();
  restoreEditorState(frame);
  // [V1 effort instrument] After the pop, so effortRoute() reports the depth we landed on
  // (depth 0 -> `map_editor`, a nested frame -> `map_editor:material`). Not reached when
  // the unsaved-edit confirm above was declined - the user stayed put.
  countNav(ROUTE_MATERIAL, effortRoute());
  renderBreadcrumb();
  notifyMapContext({ returnedFrom: from });
  return true;
}

// ====================================================
// [범용] 맵 오버레이 엔진 — **클라 단일 변환 구현** (총괄 아키텍처 결정 2026-07-26)
//
//   소스 원본 (x,y) ─[소스 자신의 메타 프레임]─▶ 물리 좌표 ─[타깃의 현재 화면 컨트롤]─▶ 셀
//
// 오버레이 = "다른 맵을 격자 대신 레이어에 로드하는 것". 그 이상도 이하도 아니다.
// 따라서 오버레이 전용 변환 코드는 **없다** — 메인 로드(loadExistingMap)가 쓰는
// `getCanvasCellFromDb` → `getDieIndex` 두 줄을, 소스 프레임을 씌운 채 실행할 뿐이다.
// 메인 로드는 "소스 메타 == 현재 컨트롤"인 특수 케이스다.
//
// [왜 서버 정렬을 그만두는가] 서버는 *가져오는 순간* 저장된 메타로 정렬을 끝내 타깃 프레임
// 좌표로 내려줬고, 클라는 이중 변환 금지 규약으로 재변환하지 않았다. 그래서 화면 컨트롤
// (rot·side·invertY·start·치수·물리 파라미터) 수정이 서버에 전달될 경로가 없었고 정렬이
// **저장된 메타 시점에 굳었다** — "클라에서 변환 수정해도 오버레이는 안 따라오네"의 정체.
// 게다가 서버/클라 두 구현이 어긋나 결함이 두 번 났다(QA B1·A1). 구현이 하나면 그 부류가 소멸한다.
//
// [gridData가 물리 키인 것이 정합의 열쇠]
// gridData는 `${px}_${py}`(물리 키)로 저장되고 렌더가 매 프레임 (c,r)→물리로 되짚어 그린다.
// 오버레이 셀도 **같은 물리 키**로 들고 있으면, 사용자가 화면 컨트롤을 어떻게 돌리든
// 메인 맵과 **같은 규칙으로 같이** 움직인다. 물리 키는 소스 메타만으로 결정되므로
// 화면 조작에 불변이고, 화면 조작은 렌더 단계에서 양쪽에 똑같이 적용된다.
//
// [정렬의 유일한 근거는 wafer_map_metadata다 — 사용자 확정 2026-07-26]
// 서버의 선언 레이어(`align_overrides`)는 제거됐다. 계측으로 잰 어긋남도 메타에 기록하므로,
// 소스 메타를 읽는 것만으로 보정이 이미 반영된다. 따라서 "서버에 보정 선언이 있는지" 묻던
// probe 관문(`probeAlignDeclaration`)도 함께 사라졌다 — 물어볼 대상이 없어졌기 때문이다.
// ====================================================
const OVERLAY_COLORS = ['#ef4444', '#3b82f6', '#f59e0b', '#a855f7', '#14b8a6', '#ec4899'];
// { id, sourceTable, sourceKey, rawCells, frame, mmItems, color, visible, status, align,
//   alignApplied, truncated, cap,
//   ── 좌석(§reseatOverlayLayer, 화면 프레임의 함수) ──
//   items:Map(dieKey -> [{val, rx, ry, mmX, mmY, srcX, srcY}]) · cells:Map(dieKey -> val|null)
//   count(칩) · cellCount(칸) · fanout · multiCells · outside · seatNote · seatAxes · seatChip }
let overlayLayers = [];
let activeOverlayLayers = [];  // 그리기 대상(visible)만 추린 캐시 — 렌더 루프에서 재계산 금지
let overlaySeq = 1;

function recomputeActiveOverlays() {
  activeOverlayLayers = overlayLayers.filter(o => o.visible && o.cells && o.cells.size > 0);
}

// ── [N2] AN OVERLAY DOT IS FILLED WITH THE COLOUR OF THE VALUE IT ANSWERS FOR ────────────
// 🟩 THE LEGEND IS THE ONLY COLOUR SOURCE. No second colour dictionary is created:
//    (1) the open map's own `legend` row -- literally the colour the legend table on screen
//        is showing right now (those rows are this map's `map_split_registry` rows);
//    (2) failing that, the served `map_overlay_config.default_legend` (`declaredLegendRow`).
//    Neither -> `null`, and `null` is a FACT: nobody declared a colour for this value.
//
// 🔴 `pickUnusedColor()` IS NOT CALLED HERE. That function INVENTS a colour, so calling it
//    would dress an undeclared value in a confident colour: the screen looks fine and the
//    meaning is wrong, which is the whole class of defect this domain exists to stop. When
//    there is no declaration we draw the absence (an unfilled dot).
function legendColorForValue(val) {
  if (val === null || val === undefined) return null;
  const v = String(val);
  if (v === '') return null;
  const own = legend.find(item => String(item.value) === v);
  if (own && own.color) return String(own.color);
  // ⚠️ Named `declared`, not `dr`, on purpose: `autoAddLegendValue` holds a BYTE-IDENTICAL
  //    `const dr = declaredLegendRow(v);` line, and a harness mutation replaces the FIRST
  //    match -- it would land on that line instead of this one and pass while measuring
  //    nothing. That is a silent hole, not a style preference.
  const declared = declaredLegendRow(v);
  return (declared && declared.color) ? String(declared.color) : null;
}

// The fill for one dot. 🔴 FILLED ONLY WHEN THERE IS EXACTLY ONE VALUE TO ANSWER WITH.
// When a cell received several source chips and is too small to show them apart, using
// `list[0]`'s colour is precisely the REPRESENTATIVE the user rejected: it discards the rest
// while looking confident. So "unfilled" carries exactly one meaning -- THIS DOT DOES NOT
// NAME A SINGLE DECLARED COLOUR -- and a solid dot always means one source chip whose value
// the legend declares. The two reasons behind an unfilled dot (undeclared value / several
// values) are told apart in WORDS by the chips on the layer row.
function overlayMarkerFill(list) {
  if (!Array.isArray(list) || list.length !== 1) return null;
  return legendColorForValue(list[0].val);
}

// [C3] 한 축에서 마커가 차지하는 반지름. **그 축의 칸 치수에서만** 나온다 — 두 치수를
//      가진 칸을 스칼라 하나로 대신하지 않는다.
//   - 바닥값(`floorPx`): 아주 작은 칸에서도 뭔가 보이게 한다.
//   - 반 칸 상한: 바닥값이 칸을 넘어 **이웃 칸 위에** 그려지는 것을 막는다. 남의 칸에 앉은
//     마커는 그 칸의 값을 말하는 것으로 읽히므로, 이건 미관이 아니라 오독 방지다.
// 함수로 두는 이유는 네 자리(1:1 반지름 x2, 펼침 반지름 x2)가 상수를 **복사**하지 않고
// 같은 정의를 실행하도록 하기 위해서다.
function markerAxisRadius(cellPx, frac, floorPx) {
  return Math.min(cellPx / 2, Math.max(floorPx, cellPx * frac));
}

// Draw one dot. The RING is the layer colour, so whatever the fill turns out to be, which
// overlay a dot belongs to is still readable -- position cannot carry that, because the 1:1
// branch's slot index is only consumed by the layers that actually drew in this cell. The
// white halo sits between the two so a dot never disappears into a cell painted the same
// colour as its own value.
// [C3] `radY`는 선택이다 — 주지 않으면 `radX`와 같아 **원**이 되고, 그때 그리는 호출은
//      한 글자도 바뀌지 않는다(정사각 칸 = 운영 대다수의 경로).
function paintOverlayDot(ctx, cx, cy, radX, fill, ringColor, radY) {
  const ry = (radY === undefined) ? radX : radY;
  ctx.beginPath();
  // 칸이 직사각이면 마커도 직사각이다. `ellipse`가 없는 컨텍스트에서는 원으로 물러난다 —
  // 웨이퍼 원을 그리는 자리가 이미 쓰는 같은 폴백이다(새 프리미티브를 만들지 않는다).
  if (radX !== ry && typeof ctx.ellipse === 'function') ctx.ellipse(cx, cy, radX, ry, 0, 0, 2 * Math.PI);
  else ctx.arc(cx, cy, radX, 0, 2 * Math.PI);
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 1.6;
  ctx.stroke();
  ctx.strokeStyle = ringColor;
  ctx.lineWidth = 0.8;
  ctx.stroke();
}

// 셀 하나에 대한 오버레이 마커 — 레이어별 점을 우상단에 나란히 찍는다.
//
// 🔴 [규칙 6] **1:1이면 점의 자리가 종전과 한 픽셀도 다르지 않다.** 한 칸이 소스 여러 칸을
//    받을 때만 (타깃 셀이 더 굵을 때) 점을 **하나로 합치지 않고 각자의 칩 내 위치에 따로**
//    찍는다. 합쳐 버리면 6칩을 받은 칸과 1칩을 받은 칸이 화면에서 구별되지 않는다 — 값
//    하나를 자신 있게 보여 주면서 나머지를 버리는 그 상태다.
// ⚠️ [N2] What changed is the FILL, not the position (see `overlayMarkerFill` above). No new
//    screen, mode or modal, and no new control: the marker layer that already existed now
//    takes its colour from the legend instead of one flat colour per layer.
function drawOverlayMarkers(ctx, coordKey, x0, y0, cellW, cellH) {
  // [C3] 마커는 **칸 자신의 비례**를 따른다 — 짧은 변이 아니다. (운영 회귀 보고 2026-08-04:
  //      "메인 맵은 멀쩡한데 오버레이 마커만 아주 작게 나온다".)
  //
  // 🔴 THE DEFECT (941060f 회귀). 반지름이 `Math.max(1.5, Math.min(cellW, cellH) * 0.13)`
  //    이라 **짧은 변 하나가** 마커 전체를 인질로 잡았다. 941060f 이전에는 셀이
  //    `width/cols` x `height/rows`라 거의 정사각이었고 `min()`이 무해했는데, 그 라운드가
  //    `phys_chip_x != phys_chip_y`인 맵의 셀을 진짜 직사각형으로 만들었다 — 그게 요청된
  //    결과였다. 실측(캔버스 700x700, 20x20 격자):
  //        피치  6x6   셀 35.00x35.00px → 마커 9.10x9.10px  (26.0%W / 26.0%H)
  //        피치  2x18  셀  3.89x35.00px → 마커 3.00x3.00px  (바닥값 1.5에 붙었다)
  //        피치 0.6x18 셀  1.17x35.00px → 마커가 **하나도 그려지지 않았다** (아래 참조)
  //    메인 격자가 멀쩡한 이유는 칸이 자기 사각형을 채우기 때문이다. 한 축으로 크기를
  //    정하는 원만 무너졌다.
  //
  // 🔴 그래서 축마다 **그 축의 치수로** 잰다: 마커는 두 축 각각에서 칸의 같은 비율을
  //    차지한다. 정사각 칸이면 `rx == ry`라 종전 원과 한 픽셀도 다르지 않다.
  //    타원인 이유 — ① 칸을 채우는 사각형은 칸 자신의 범례색과 겹쳐 읽히지 않는다.
  //    ② 기하평균 같은 단일 스칼라는 결국 두 치수를 스칼라 하나로 대신하는 **같은** 결함이고,
  //    1:9에서 sqrt(3.89*35)=11.7px가 되어 3.89px 폭 칸을 넘는다. 타원만이 어떤 비율에서도
  //    칸을 넘지 않으면서 1:1에서 종전 원으로 정확히 퇴화한다.
  const rx = markerAxisRadius(cellW, 0.13, 1.5);
  const ry = markerAxisRadius(cellH, 0.13, 1.5);
  // 칸 안쪽 여백. 종전에는 1.5px 고정이었는데, 1.5px보다 얇은 칸에서는 앵커가 칸 왼쪽
  // **밖으로** 나가 아래 `cx < x0`이 걸려 마커가 아예 그려지지 않았다(실측 0.6x18).
  // 칸이 15px 이상이면 정확히 종전 1.5px다.
  const insetX = Math.min(1.5, cellW * 0.1);
  const insetY = Math.min(1.5, cellH * 0.1);
  let idx = 0;
  for (let i = 0; i < activeOverlayLayers.length; i++) {
    const layer = activeOverlayLayers[i];
    const list = layer.items ? layer.items.get(coordKey) : null;
    if (!list || list.length === 0) continue;

    // 칸 안에 여럿 — 각자의 나머지(칩 내 mm)가 그대로 자리가 된다.
    // 칸이 점 여럿을 담기에 너무 작으면 대표를 고르는 대신 **종전 한 점**으로 물러난다
    // (자리를 지어내지 않는다 — 목록은 레이어 행의 수가 계속 말한다).
    // [C3] **축마다 그 축이 실제로 필요한 것에 대고 잰다.** 종전 `cellW >= 10 && cellH >= 10`은
    //      위 반지름과 같은 `min` 사고라 얇은 칸에서 펼침을 통째로 껐다 — 6칩을 받은 칸이
    //      1칩 받은 칸과 화면에서 구별되지 않는 상태로 되돌아갔다(실측: 피치 2x18과 18x2에서
    //      3점이 1점으로 붕괴). 넓고 낮은 칸은 가로로 벌리면 그만이고, 그러기 위해 세로가
    //      보태야 할 것은 없다. 그래서 **한 축이라도** 여유가 있으면 펼친다.
    //      ⚠️ 이건 순수한 확장이다 — 종전에 펼치던 칸은 전부 그대로 펼친다.
    const roomy = list.length > 1 && (cellW >= 10 || cellH >= 10) && layer.seatAxes && layer.seatChip;
    if (roomy) {
      const rrx = markerAxisRadius(cellW, 0.10, 1.2);
      const rry = markerAxisRadius(cellH, 0.10, 1.2);
      const A = layer.seatAxes;
      for (let k = 0; k < list.length; k++) {
        const it = list[k];
        // 물리 축 기준 칸 중심으로부터의 비율 → 화면 축 비율.
        // 🔴 회전식을 여기에 다시 쓰지 않는다. `A`는 `getCanvasCellFromDieIndex`가
        //    (0,0)/(1,0)/(0,1)에 대해 내놓은 답의 차분이다(§reseatOverlayLayer).
        const fx = it.rx / layer.seatChip.x - 0.5;
        const fy = it.ry / layer.seatChip.y - 0.5;
        const sx = fx * A.xc + fy * A.yc;
        const sy = fx * A.xr + fy * A.yr;
        const cx = x0 + (0.5 + sx) * cellW;
        const cy = y0 + (0.5 + sy) * cellH;
        // [N2] Here one dot IS one source chip, so there is exactly one value to answer
        //      with. This is not choosing a representative -- it is that chip's own value.
        paintOverlayDot(ctx, cx, cy, rrx, overlayMarkerFill([it]), layer.color, rry);
      }
      continue;
    }

    const cx = x0 + cellW - rx - insetX - idx * (rx * 2 + insetX);
    const cy = y0 + ry + insetY;
    if (cx < x0) break; // 셀이 너무 작아 더 못 찍음
    // [N2] When `list` holds several items `overlayMarkerFill` answers null and the dot is
    //      left unfilled, because no single value may be picked to stand for the rest. This
    //      is the colour half of the user's "list them all" ruling.
    paintOverlayDot(ctx, cx, cy, rx, overlayMarkerFill(list), layer.color, ry);
    idx++;
  }
}

// ── 프레임 기술자 ────────────────────────────────────────────
// 좌표계를 정의하는 축 전부: 치수·시작좌표·y반전·회전·면 + 물리 파라미터.
// 메타에 없는 물리 항목은 undefined로 남겨 두면 프레임 창에서 **현재 화면 값으로 폴백**한다
// (그래서 물리 파라미터가 기하 시그니처에 반드시 들어가야 한다 — 아래 currentGeomSignature).
function frameFromMeta(meta) {
  if (!meta || typeof meta !== 'object') return null;
  const num = (v) => {
    if (v === undefined || v === null || v === '') return undefined;
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  };
  const cols = num(meta.grid_cols);
  const rows = num(meta.grid_rows);
  if (cols === undefined || rows === undefined) return null;   // 치수 없는 메타는 프레임이 아니다
  return {
    cols, rows,
    startX: num(meta.grid_start_x) !== undefined ? num(meta.grid_start_x) : 0,
    startY: num(meta.grid_start_y) !== undefined ? num(meta.grid_start_y) : 0,
    invertY: !!meta.grid_y_invert,
    rotation: Number(meta.rotation) || 0,
    side: meta.side === 'back' ? 'back' : 'front',
    waferDia: num(meta.phys_wafer_dia),
    chipX: num(meta.phys_chip_x),
    chipY: num(meta.phys_chip_y),
    offsetX: num(meta.phys_offset_x),
    offsetY: num(meta.phys_offset_y),
    edgeMargin: num(meta.phys_edge_margin),
    // [D1] 표지도 프레임에 실린다. 이 줄이 없으면 오버레이 경로에서 표지가 **화이트리스트에
    //      걸러져** 사라지고, 소스의 합성 1x1이 진짜 피치로 읽힌다(§physDeclaration).
    //      `num()`을 태우지 않는다 — 이것은 수가 아니라 사실이다.
    autoRegistered: meta.auto_registered === true,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// [H5] 격자 치수의 **정의역**. 새 수를 만드는 것이 아니다 — 편집기가 이미 선언해 둔 값이다:
// `map_editor.html`의 `#grid-cols`/`#grid-rows`가 `min="1" max="100"`이고, 파생 치수를 쓰는
// `applyPhysicalGeometry`도 같은 상한으로 clamp한다. 함수로 두는 이유는 두 소비자가 상수를
// **복사**하지 않고 같은 정의를 실행해서 공유하도록 하기 위해서다.
//
// ⚠️ 이 가드의 근거는 F8(채택 폐지, `61440e6`)에서 **바뀌었다.** 종전 근거는 "채택 1회가 격자
//    전수 순회를 4회 돈다"였는데 채택 자체가 없어졌다. 그런데 가드는 두 근거로 살아남는다:
//
//    ① 비용 — 채택은 없어도 `projectCellsToPhys(cells, refFrame)`은 **참조의 치수로** 프레임
//       창을 열고, 그 안에서 `getWaferBoundingBox`가 `visualCols × visualRows`를 훑어
//       `minC/minR/maxR`을 구한다. 1024x1024 메타 행 하나면 그 자리에서 104만 칸을 도는
//       동기 루프이고 취소 수단이 없다. 참조 **셀**은 `OVERLAY_CELL_LIMIT`이 막는데 참조
//       **치수**는 아무도 막지 않았다.
//    ② 정확성 — 이쪽이 이제 더 무겁다. 아래 `frameDimError`는 0·음수·비정수도 막는다.
//       막지 않으면 `gridDimNum`이 0을 기본값 10으로 읽고 `parseInt`가 45.5를 45로 읽어,
//       마스크가 **참조가 선언한 적 없는 인덱스 공간**에서 만들어진다 — 화면은 멀쩡한데 값이
//       틀린 그 상태다.
// ═══════════════════════════════════════════════════════════════════════════════
function frameDimBounds() { return { min: 1, max: 100 }; }

// 치수가 그 정의역 안인가. 사유 문자열을 돌려준다(문제가 없으면 빈 문자열).
// 🔴 clamp하지 않는다. 잘라 넣으면 참조 맵의 인덱스 공간과 다른 격자로 마스크를 만들고,
//    그것이 바로 이 도메인이 존재하는 이유인 '화면은 멀쩡한데 값이 틀린' 상태다.
// ⚠️ 정수도 요구한다. `frameFromMeta`는 `45.5`도 받는데 `gridDimNum`은 `parseInt`로 45로
//    읽는다 — 해석과 선언이 갈린다. `0`도 같다: `gridDimNum`의 `ov || dflt`가 0을 기본값
//    10으로 조용히 바꾼다.
function frameDimError(frame) {
  const b = frameDimBounds();
  const bad = (n, name) => (!Number.isInteger(n) || n < b.min || n > b.max) ? `${name}=${n}` : '';
  const errs = [bad(frame.cols, 'grid_cols'), bad(frame.rows, 'grid_rows')].filter(Boolean);
  return errs.length ? `${errs.join(', ')} (허용: ${b.min}~${b.max} 정수)` : '';
}

// 현재 화면 컨트롤도 그냥 하나의 프레임이다 (물리 항목은 undefined = DOM 그대로).
function currentFrame() {
  return {
    cols: parseInt(el.gridCols.value, 10) || 10,
    rows: parseInt(el.gridRows.value, 10) || 10,
    startX: parseInt(el.gridStartX.value, 10) || 0,
    startY: parseInt(el.gridStartY.value, 10) || 0,
    invertY: !!(el.gridYInvert && el.gridYInvert.checked),
    rotation: currentRotation,
    side: currentSide,
  };
}

// 프레임의 모든 축을 실값으로 확정한다(undefined → 현재 화면 값). 축 비교의 유일한 근거.
function resolveFrame(frame) {
  const f = frame || currentFrame();
  return ({
    cols: gridDimNum(f, 'cols', el.gridCols, 10),
    rows: gridDimNum(f, 'rows', el.gridRows, 10),
    startX: f.startX, startY: f.startY,
    invertY: !!f.invertY, rotation: Number(f.rotation) || 0,
    side: f.side === 'back' ? 'back' : 'front',
    waferDia: physNum(f, 'waferDia', el.physWaferDia, 300),
    chipX: physNum(f, 'chipX', el.physChipX, 2.5),
    chipY: physNum(f, 'chipY', el.physChipY, 2.5),
    offsetX: physNum(f, 'offsetX', el.physOffsetX, 0.0),
    offsetY: physNum(f, 'offsetY', el.physOffsetY, 0.0),
    edgeMargin: physNum(f, 'edgeMargin', el.physEdgeMargin, 3.0),
  });
}

function frameAxesKey(rf) {
  return [rf.rotation, rf.side, rf.invertY ? 1 : 0, rf.startX, rf.startY, rf.cols, rf.rows,
  rf.waferDia, rf.chipX, rf.chipY, rf.offsetX, rf.offsetY, rf.edgeMargin].join('|');
}

// ── 변환의 전부 ──────────────────────────────────────────────
// 소스 **원본 셀** → 다이 인덱스 + 물리 mm 항목 배열.
// 아래 두 줄은 메인 로드(loadExistingMap의 셀 루프)와 **같은 함수·같은 인자 순서**이며,
// 다른 점은 단 하나 — 규격을 소스 자신의 프레임에서 읽는다는 것뿐이다.
//
// 🔴 mm는 **세 번째 변환이 아니다.** 회전·반전·오프셋은 전부 `getDieIndex` 안에서 끝나고,
//    여기서 더하는 것은 「그 칸 번호가 몇 mm인가」라는 **단위 환산 하나**뿐이다
//    (§dieIndexToWaferMm). 오버레이 전용 변환식을 쓰지 않는다는 계약이 이 구조다.
// ⚠️ 피치가 없으면 `mm`이 null인 항목이 나온다 — 여기서 거절하지 않는다. 거절 문구를 쓰는
//    자리는 호출자(오버레이)이고, 유효 다이 해석은 mm를 아예 보지 않기 때문이다.
function projectCellsToWaferMm(cells, frame) {
  const f = frame || currentFrame();
  const { cols, rows, rotation, side, invertY, startX, startY } = f;
  {
    const chipX = physNum(f, 'chipX', el.physChipX, 2.5);
    const chipY = physNum(f, 'chipY', el.physChipY, 2.5);
    const out = [];
    (Array.isArray(cells) ? cells : []).forEach(c => {
      const xn = Number(c.x);
      const yn = Number(c.y);
      if (!Number.isFinite(xn) || !Number.isFinite(yn)) return;
      const cell = getCanvasCellFromDb(f, xn, yn, cols, rows, rotation, side, invertY, startX, startY);
      const p = getDieIndex(f, cell.c, cell.r, cols, rows, rotation, side);
      out.push({
        srcX: xn, srcY: yn,
        ix: p.x, iy: p.y,
        // 🔴 mm는 **반올림 전** 연속값에서 만든다(`p.xCells`). 반올림된 `p.x`에서 되만들면
        //    오프셋의 칸 미만 잔여가 빠져 모든 셀이 그만큼 밀린다 — 실측: 이 fixture에서
        //    1836칸 중 1789칸이 틀린 타깃 칸에 앉았다.
        mm: (chipX > 0 && chipY > 0) ? { mmX: p.xCells * chipX, mmY: p.yCells * chipY } : null,
        val: (c.val === undefined || c.val === null) ? '' : String(c.val),
      });
    });
    return out;
  }
}

// 소스 **원본 셀** → 물리 키 Map. 시그니처도 의미도 종전 그대로다(유효 다이 해석의 입력).
// 🔴 **같은 수를 두 번 계산하지 않는다** — 위 함수가 이미 만든 인덱스를 키로 옮길 뿐이다.
//    마지막 값이 이긴다는 충돌 규약도 배열 순서가 곧 삽입 순서라 종전과 같다.
function projectCellsToPhys(cells, frame) {
  const map = new Map();
  projectCellsToWaferMm(cells, frame).forEach(it => { map.set(`${it.ix}_${it.iy}`, it.val); });
  return map;
}

// ── [규칙 6] 물리 mm 항목을 **타깃 프레임의 칸에 앉힌다** ─────────────────────────
// 반환 `Map(다이키 → 항목 배열)`. 🔴 **대표값을 고르지 않는다**(사용자 확정 ⓒ「전부 나열」):
// 타깃 피치가 소스보다 굵으면 한 칸이 소스 여러 칸을 받는데(실측 최대 6), 대표를 고르면
// 나머지를 조용히 버리면서 **한 값을 자신 있게** 보여 준다.
// 항목에 실리는 `rx`/`ry`는 그 칸 **안에서의** mm 위치다(§waferMmToDieCell).
//
// ⚠️ 앉히는 기준은 **지금 화면의 프레임**이다. 렌더 루프가 읽는 좌표계가 그것이기 때문이고,
//    그래서 화면 규격이 바뀌면 `syncOverlayGeometry`가 이 함수를 다시 돌려야 한다
//    (종전 다이 인덱스 키는 화면에 불변이었지만 **mm 좌석은 피치의 함수다**).
function seatWaferMmInFrame(items, frame) {
  const f = frame || currentFrame();
  const seated = new Map();
  const L = frameDieLattice(f);
  let duplicates = 0;
  (Array.isArray(items) ? items : []).forEach(it => {
    if (!it.mm) return;
    const t = waferMmToDieCell(it.mm.mmX, it.mm.mmY, L);
    if (!t) return;
    const key = `${t.ix}_${t.iy}`;
    const list = seated.get(key);
    const entry = {
      val: it.val, rx: t.rx, ry: t.ry, mmX: it.mm.mmX, mmY: it.mm.mmY,
      srcX: it.srcX, srcY: it.srcY
    };
    if (!list) { seated.set(key, [entry]); return; }
    // 🔴 **같은 물리 위치의 같은 값은 정보가 아니다** — 소스에 같은 행이 두 번 있을 뿐이다.
    //    접어 넣지 않으면 피치가 **같은** 맵도 fanout 2가 되어 「여러 값」으로 가져오기에서
    //    제외된다(종전 코드는 마지막 값을 그대로 썼다). 위치가 같은데 값이 다르면 그것은
    //    중복이 아니라 **충돌**이므로 둘 다 남긴다 — 그때 고르는 것이 곧 버리는 것이다.
    const twin = list.find(e => e.mmX === entry.mmX && e.mmY === entry.mmY);
    if (twin && twin.val === entry.val) { duplicates++; return; }
    list.push(entry);
  });
  return { seated, duplicates };
}

// 지금 화면의 캔버스가 만들어 내는 다이 키 — `all`(격자의 모든 칸)과 `inside`(웨이퍼/유효
// 다이 안쪽 칸). 🔴 **「격자 밖」의 유일한 근거이고, 그 근거는 `inside`다.**
//
// 🔴 종전 판정 `0 <= px < cols`는 다이 인덱스의 원점이 격자 중심이던 시절의 술어이고
//    `35e84c3` 이후로 거짓이다 — 실측: 소스와 타깃 프레임이 **완전히 같은** 오버레이에서
//    402칩 중 277칩을 「격자 밖」으로 보고했다(진실은 0).
// 🔴 **세는 집합과 문장이 같은 인구를 가리켜야 한다.** 「가져오기에서 제외됩니다」라고 말하려면
//    [↓ 가져오기]가 실제로 거르는 집합을 세야 한다. 그 집합은 `gridCells2D[].inside`,
//    즉 `isValidDieAt(…, isCellInsideWaferFast(…))`이다. 격자 안이지만 원 밖인 칸이 있으므로
//    `all`로 세면 0을 보고하면서 가져오기는 조용히 건너뛴다(QA 실측: 297칸 중 36칸).
// 🔴 **프레임 창을 열지 않는다.** 창 안에서는 `isValidDieAt`이 원으로 답하므로(§isValidDieAt)
//    타깃 **자신의** 마스크가 빠져 버린다 — 그러면 이 집합은 가져오기가 쓰는 그 집합이 아니다.
//    좌석 프레임은 언제나 화면이고 화면 값은 창 없이 그대로 읽힌다.
// ⚠️ 판정 좌표계는 700x700 픽셀인데(§isCellInsideWaferFast) **그 술어는 크기 불변**이다:
//    `cellW`가 분자·분모에서 상쇄된다. 실측(캔버스 200/431/700/1024/1600 정사각 + 900x380
//    비정사각) 600칸 전부 판정이 같다. 그래서 여기서 센 수는 렌더가 볼 수와 같다.
// ⚠️ 격자 전수 순회다(실측 40x40 = 13ms, 100x100 = 59ms). 레이어마다 다시 돌면 규격 입력
//    한 타에 6배가 붙으므로 캐시한다. 키는 **해석된 축 전부 + 마스크 세대**다 — 마스크는
//    프레임과 따로 바뀌므로 축만으로는 무효화되지 않는다.
// ⚠️ 저작 중(`template`)에는 캐시하지 않는다. 붓질은 세대 번호를 올리지 않아 **어떤 키로도**
//    무효화되지 않기 때문이다.
let seatKeyCache = { key: '', sets: null };
function canvasSeatKeys() {
  const f = resolveFrame(currentFrame());
  const basis = validDieBasis();
  const ck = `${frameAxesKey(f)}|${basis}|${validDieResolveSeq}`;
  const cacheable = (basis !== 'template');
  if (cacheable && seatKeyCache.sets && seatKeyCache.key === ck) return seatKeyCache.sets;

  const rot90 = (f.rotation === 90 || f.rotation === 270);
  const visualCols = rot90 ? f.rows : f.cols;
  const visualRows = rot90 ? f.cols : f.rows;
  const physConfig = getTransformedPhysicalConfig(null, f.rotation, f.side);
  const all = new Set();
  const inside = new Set();
  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      const p = getDieIndex(null, c, r, f.cols, f.rows, f.rotation, f.side);
      const k = `${p.x}_${p.y}`;
      all.add(k);
      if (isValidDieAt(null, p.x, p.y, isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, 700, 700))) {
        inside.add(k);
      }
    }
  }
  const sets = { all, inside };
  if (cacheable) seatKeyCache = { key: ck, sets };
  return sets;
}

// ── [M4 phase 1] 참조된 유효 다이 맵의 해석 ─────────────────────────────────
//
// 새 기하식은 한 줄도 쓰지 않는다. 이미 있는 프리미티브만 순서대로 쓴다:
//   fetchMapKeySpec(7b 캐노니컬화) → fetchServedBinding(§5.6-bis) → fetchGridMetaFor(§5.0)
//   → frameFromMeta → projectCellsToPhys(§5.1의 그 두 줄)
// 오버레이가 하는 일과 구조적으로 같은 연산이며, 다른 점은 **결과를 그리지 않고
// 마스크로 쓴다**는 것뿐이다.
//
// 🔴 해석에 실패하면 조용히 원으로 되돌아가지 않는다. basis를 `refused`로 두고
//    이유를 남긴다 — 틀린 답과 맞는 답이 구별되지 않는 상태를 만들지 않기 위해서다.
// `homeMapKey` — 선언한 맵 자신의 키. [M4② INV-6] 자기 참조 판정에만 쓴다.
async function resolveValidDie(meta, targetTable, homeMapKey) {
  // 원문을 그대로 붙든다. Push가 메타를 **처음부터 다시 만들기** 때문에, 여기서 붙들지
  // 않으면 유효 다이를 선언한 맵을 한 번 저장하는 것만으로 그 선언이 사라진다.
  // 읽지 못한 선언도 보존한다 — 지워 버리면 사용자는 자기가 무엇을 잘못 썼는지조차
  // 볼 수 없게 된다(검증 경로가 사용자의 데이터를 파괴해서는 안 된다).
  const raw = (meta && typeof meta === 'object' && ('valid_die_ref' in meta))
    ? meta.valid_die_ref : undefined;
  // [F3] 이 해석의 세대. 착지 시점에 최신이 아니면 화면 상태를 건드리지 않는다 —
  // 토스트도 띄우지 않는다(이미 지나간 지정에 대한 경고는 지금 화면과 무관하다).
  const mySeq = ++validDieResolveSeq;
  const stale = () => mySeq !== validDieResolveSeq;
  // ═══ 셀 위치 계산 ― 붙드는 것은 **저장 좌표**, 움직이는 것은 **캔버스 칸** ═══════════
  // 사용자 지적: 「캔버스 좌표를 보존하고 있어 셀이」. 그것이 결함이다. 근거가 바뀌면
  // `box.minC`가 셀 밑에서 움직이는데 셀이 칸을 붙들고 있어서 읽는 번호가 바뀌었다
  // (bonding_map 4E → DT에서 `5,5`가 `2,3`이 됐다). 붙들 것은 번호이고 칸은 파생이다.
  //
  // 🔴 로드 경로에서는 **아무 일도 하지 않는다.** `loadExistingMap`이 `gridData`(:4602)·
  //    `loadedFCells`(:4603)·`serverCellKeys`(:4607)를 `resolveValidDie`(:4866)보다 먼저
  //    비우므로 집합이 비어 무비용이고, 로드는 이미 옳다(사용자 QA 통과). 여기가 고치는 것은
  //    **화면에 이미 앉아 있는 셀** ― 지정/해제/변경뿐이다.
  let screenShift = null;   // 화면이 실제로 움직인 양. 토스트가 쓰는 수는 이것이다.
  // 재배치 결과는 담아 두고 **1~6 다음에** 찍는다. `set`은 로그 블록보다 먼저 돌기 때문이다.
  let placementNote = '';
  // 격자가 넓어졌는가. 로그 블록이 읽는다(토스트는 늘리지 않는다 ― UI 규율).
  let maskFitNote = null;
  // `physPreset` — [규칙 ①] 「맵 기하 재로드」. 유효 다이 영역을 불러올 때 이 맵의 기하 메타를
  // **참조 자신의 것**으로 갈아끼운다(WF 직경·셀 크기·offset). 여기서 받는 이유가 전부다:
  // 기하를 바꾸면 원점 상자가 움직이고, 상자가 움직이면 셀은 자기 좌표를 따라 함께 움직여야
  // 한다(규칙 ④). 그 포착-변경-재배치가 이미 이 함수 안에 있으므로 **반응 지점이 하나로
  // 유지된다** ― 아래 (1)의 포착과 (2)의 재배치 사이에 끼우는 것이 유일하게 옳은 자리다.
  // 밖에서 미리 적용하면 (1)이 이미 바뀐 기하로 좌표를 되찾아 좌표가 조용히 옮겨간다.
  //
  // ⚠️ **치수는 여기로 넘기지 않는다 ― 규격에서 파생시킨다.** 삭제된 프레임 채택 함수
  //    (94b9baa)가 거절당한 것은 참조가 **선언한** cols/rows를 베끼면서 셀은 캔버스 칸에
  //    그대로 둬서 273칸 전부의 좌표를 움직였기 때문이다. 지금 하는 일은 그것이 아니다:
  //    치수는 갈아끼운 규격에서 `applyPhysicalGeometry`가 **파생**하고(불변식: 격자 크기는
  //    방향·물리 규격에서 파생되며 데이터 좌표 범위에서 역산하지 않는다), 셀은 아래 (2)가
  //    **자기 저장 좌표에서** 다시 앉힌다. 파생과 재배치는 한 쌍이고, 한쪽만 하면 그것이
  //    거절당한 그 동작이다.
  const set = (basis, keys, reason, ref, physPreset) => {
    if (stale()) return validDie;
    const fc = gridDimNum(null, 'cols', el.gridCols, 10);
    const fr = gridDimNum(null, 'rows', el.gridRows, 10);
    const fsx = parseInt(el.gridStartX.value, 10) || 0;
    const fsy = parseInt(el.gridStartY.value, 10) || 0;
    const fiv = !!(el.gridYInvert && el.gridYInvert.checked);
    // 좌표 (startX,startY)가 앉는 칸 = 마스크의 시작 칸. 이동량의 근거는 이 한 함수다.
    // ⚠️ 치수를 **인자로** 받는다. 아래에서 격자가 넓어질 수 있으므로 전/후를 같은 치수로
    //    재면 이동량이 거짓이 된다(토스트가 그 수를 사용자에게 보여 준다).
    const seat0 = (c, r) => getCanvasCellFromDb(null, fsx, fsy, c, r,
      currentRotation, currentSide, fiv, fsx, fsy);

    // (1) 근거를 바꾸기 **전에** 좌석 기록이 옛 좌표계를 가리키고 있어야 한다. 평소에는 직전
    //     렌더가 이미 남겨 두었고(§cellsSeatedUnder), 한 번도 그리지 않았으면 지금 잡는다.
    //     되찾기 자체는 이 안에서 하지 않는다 ― 그 구현은 `reseatCellsToStoredCoords` 하나다.
    // ⚠️ 아래에서 `applyPresetObject`가 규격을 갈아끼우면 그 안의 `applyPhysicalGeometry`가
    //    **같은 반응을 먼저 한 걸음** 돌린다. 그래서 여기서 기록을 지역 변수에 캐시해 두면
    //    안 된다 ― 마지막 반응은 반드시 그 시점의 `cellsSeatedUnder`를 읽어야 두 걸음이
    //    이어 붙는다. 넷 이동량은 아래에서 좌석 집합의 차이로 잰다.
    const seatsBefore = new Set([...Object.keys(gridData), ...loadedFCells,
    ...(serverCellKeys && serverCellKeys.keys ? serverCellKeys.keys : [])]);
    if (!cellsSeatedUnder) cellsSeatedUnder = seatingSnapshot(null);
    const wasSeat = seat0(fc, fr);

    validDie = { basis, keys, reason: reason || '', ref: ref || null, raw };
    // [규칙 ①] 기하 재로드. `validDie` 대입과 **같은 순간**에 둔다 ― 둘 다 원점 상자를 움직이는
    // 변경이고, 아래 (2)가 그 둘을 한 번에 흡수한다.
    //
    // 🔴 **(a) 규격을 갈아끼우면 격자도 그 규격에서 다시 파생된다.** `applyPresetObject`는
    //    규격을 쓰는 기존 프리미티브라 재사용하고(직경 select의 custom 옵션 처리가 그 안에
    //    있다), 그 함수는 마지막에 `applyPhysicalGeometry()`를 불러 **새 규격에서 cols/rows를
    //    다시 유도해 써넣는다.** 그 유도가 곧 [규칙 ①-b]「격자는 유효 다이 맵 기하에 맞게
    //    변경」이다 ― 참조가 선언한 수를 베끼는 것이 아니라 규격이 낳는 수다.
    //    종전 두 줄은 이 유도값을 옛 치수로 되돌렸다(사용자 QA: 「기하 안바뀜」).
    // 🔴 **파생만 하고 끝내면 그것이 거절당한 동작이다.** 치수가 바뀌면 같은 칸이 다른 좌표를
    //    낳으므로, 아래 (2)의 재배치가 **반드시 같은 호출 안에서** 뒤따라야 한다. 셀은 칸이
    //    아니라 자기 저장 좌표를 붙든다(규칙 ④).
    if (physPreset) {
      applyPresetObject(physPreset);
      // 🔴 **(b) 파생 격자가 마스크를 온전히 담는가.** 담지 못할 때만, 담을 때까지만 넓힌다
      //    ― 「유효 다이가 온전히 보이게」의 구현이다. 담고 있으면 한 칸도 늘리지 않는다.
      // 🔴 **새 기하식은 한 줄도 없다.** 마스크 키를 칸으로 되돌리는 것은 렌더·재배치가 쓰는
      //    바로 그 역함수(`getCanvasCellFromDieIndex`)이고, 여기서 두 번째 구현을 쓰면 화면과
      //    저장값이 갈라진다(불변식 ①: 변환 구현은 하나다).
      // ⚠️ NOT INLINE ANY MORE — and the note that said it had to be is re-pointed, not deleted.
      //    It read: "a helper would make the harnesses that slice `resolveValidDie` die with a
      //    ReferenceError on one module-global dependency". The price is one name in two slice
      //    lists (`geometry_origin_reseat` / `valid_die_frame_adoption` SYMBOLS), and omitting it
      //    is LOUD, not silently green: the refusal reason becomes `is not defined` and both
      //    harnesses go red. `fitGridToMask` takes everything it reads as an argument.
      if (keys && keys.size > 0) {
        maskFitNote = fitGridToMask(keys, el, currentRotation, currentSide);
      }
      boundingBoxCache = {};
    }
    // 재배치가 쓸 치수는 **바뀐 뒤의** 것이다. 위 블록이 격자를 다시 파생시켰을 수 있고,
    // 옛 치수로 앉히면 렌더가 새 치수로 좌표를 되만들어 저장 좌표가 조용히 옮겨간다.
    const nc = gridDimNum(null, 'cols', el.gridCols, 10);
    const nr = gridDimNum(null, 'rows', el.gridRows, 10);

    // 🔴 **캐시를 반드시 비운다.** `getWaferBoundingBox`의 캐시 태그는 `V<validDieResolveSeq>`
    //    인데 그 번호는 `resolveValidDie` **진입 시** 한 번 오른다(위 `mySeq`). 그래서 진입과
    //    이 대입 사이에 상자를 한 번이라도 물으면 **옛 마스크로 만든 상자가 새 번호의 키에**
    //    실린다. 바로 위 `wasSeat`가 그 질문을 하므로, 비우지 않으면 아래 배치와 이후 렌더가
    //    전부 캐시 적중으로 **옛 마스크의 상자**를 받는다 ― 마스크는 새것을 그리는데 좌표계는
    //    옛것이라 원점이 어긋나 보인다. 지난 라운드가 정확히 이렇게 무너졌다.
    boundingBoxCache = {};

    // (2) 각 셀을 **자기 저장 좌표에서** 새 좌표계가 주는 칸으로 앉힌다 ― 기하 프리셋 편집이
    //     타는 것과 **같은 함수**다(§reseatCellsToStoredCoords). 유효 다이 영역이 원에서
    //     오든 선언된 마스크에서 오든 원점 상자가 움직였다는 사실은 하나이므로 반응도 하나다.
    //
    // 🔴 인자는 **지금** 읽는다. 위 `applyPresetObject`가 규격을 갈아끼웠다면 그 안에서 이미
    //    한 걸음이 돌았고, 이 호출은 그 뒤 격자 확장분만 마저 흡수한다. 미리 잡아 둔 옛 기록을
    //    넘기면 같은 이동을 두 번 적용한다.
    const placed = reseatCellsToStoredCoords(cellsSeatedUnder);
    const moved = summariseReseat(seatsBefore, placed, nc, nr, gridData, loadedFCells, serverCellKeys);
    if (moved.netMoved > 0) {
      placementNote = moved.note;
      if (basis !== 'ref') console.log(placementNote);   // ref는 1~6 뒤에 찍는다
    }
    const nowSeat = seat0(nc, nr);
    if (nowSeat.c !== wasSeat.c || nowSeat.r !== wasSeat.r) {
      screenShift = { dc: nowSeat.c - wasSeat.c, dr: nowSeat.r - wasSeat.r };
    }
    renderValidDieChip();
    syncValidDieRefControls();   // [M4②] 지정 컨트롤은 언제나 raw를 되비춘다
    return validDie;
  };
  const refuse = (ref, reason) => {
    if (stale()) return validDie;
    console.warn(`[Map Editor][M4] valid_die_ref 해석 실패 — ${reason}`);
    showToast(`유효 다이 맵을 해석하지 못했습니다 — ${reason}`, 'error');
    return set('refused', null, reason, ref);
  };

  // [F6] 이 해석이 편집기 프레임을 갈아끼웠는가. 세웠으면 마스크가 앉은 뒤에 알린다.
  // [F8] 치수 차이는 **사실**이지 채택이 아니다. 화면은 그대로 두고 한 번 알린다.
  let dimsDiffer = null;
  // 정렬의 축. `dimsDiffer`와 **독립**이다 — 같은 크기에서도 원점이 어긋날 수 있고
  // (`MID_01 ← 4MAIN_DT`가 그 실측 사례다), 그 반대도 성립한다.
  let originDiffer = null;

  const parsed = parseValidDieRef(meta, targetTable);
  if (parsed === null) return set('circle', null, '', null);          // 선언 없음 = 종전 그대로
  if (parsed.unreadable) return refuse(null, parsed.reason);

  const ref = { table: parsed.table, mapKey: parsed.mapKey };
  // [1-a] 이 선언은 고정 이전에 **다른 테이블**을 이름 붙였는가. 붙였다면 해석 실패의
  // 이유가 「키가 틀렸다」가 아니라 「키는 맞는데 이 테이블에 없다」일 수 있고, 그 둘은
  // 수리가 다르다. 성공하면 아무 말도 하지 않는다(읽기는 무마찰).
  const redirectNote = (parsed.declaredTable && parsed.declaredTable !== VALID_DIE_TABLE)
    ? ` (이 지정은 원래 「${parsed.declaredTable}」을(를) 가리켰지만, 유효 다이 맵은 언제나 `
      + `${VALID_DIE_TABLE}에서 읽습니다 — 그 맵을 ${VALID_DIE_TABLE}에 등록하거나 키를 고치십시오.)`
    : '';
  try {
    // [7b/§5.6-bis/§5.0] the reference map resolved to a frame, or a reason it could not be.
    const rspec = await resolveReferenceSpec(ref);
    if (!rspec.ok) return refuse(ref, rspec.reason + redirectNote);
    const spec = rspec.spec;
    const binding = rspec.binding;
    const refMeta = rspec.refMeta;
    const refFrame = rspec.refFrame;
    // [H5] 치수를 **셀을 한 건도 읽기 전에** 검사한다. 근거는 `frameDimBounds` 위 주석에
    // 정본이 있다 — 여기 있던 「전수 순회 4회(계획 2 + 비용 2)」는 채택·재배치 기계장치의
    // 비용이었고 그 기계장치는 삭제됐다(61440e6 + 94b9baa). 남은 근거 둘: `projectCellsToPhys`가
    // **참조 치수**로 프레임 창을 열고 그 안에서 `getWaferBoundingBox`가 전수 순회하므로 네 자리
    // 치수 하나로 탭이 굳는 것은 그대로이고, 0·음수·비정수는 `gridDimNum`/`parseInt`가
    // **참조가 선언한 적 없는 인덱스 공간**으로 읽어 마스크가 조용히 틀린다. clamp하지 않는다.
    const dimErr = frameDimError(refFrame);
    if (dimErr) {
      return refuse(ref, `${ref.table} · ${ref.mapKey}: 참조 맵이 선언한 격자 치수가 편집기가 다룰 수 `
        + `있는 범위를 벗어났습니다 — ${dimErr}. 이 치수를 그대로 채택하면 격자 계산이 그만큼 커져 `
        + `화면이 응답하지 않습니다. 참조 맵의 wafer_map_metadata에 있는 grid_cols/grid_rows를 `
        + `확인하십시오(자동 등록된 행이면 잘못 추정된 값일 수 있습니다).`);
    }
    // [M4② INV-6] 셀을 한 건도 읽기 전에 체인부터 끊는다. 규격을 받은 직후가 이 판정이
    // 가능해지는 가장 이른 지점이고, 여기서 막으면 순환 참조가 네트워크를 타지도 못한다.
    //
    // 홈 키도 **같은 정규화 한 번**을 태워서 넘긴다(`canonicalMapKey`, 7b). 자기 참조는
    // 철자가 아니라 정체성의 문제라, `LOT_01`과 `LOT_1`이 같은 맵인지는 선언된 컬럼 타입이
    // 정한다 — 그 판단을 가드 안에서 다시 하면 정규화가 둘이 된다(INV-7).
    const homeSpec = (ref.table === targetTable) ? spec : await fetchMapKeySpec(targetTable);
    let homeKey = homeMapKey === undefined || homeMapKey === null ? '' : String(homeMapKey);
    if (homeKey !== '' && homeSpec.ok && homeSpec.keyColumns.length > 0) {
      homeKey = canonicalMapKey(homeSpec.keyColumns, homeKey, homeSpec.columnTypes);
    }
    const chain = validDieChainError(ref, refMeta, { table: targetTable, mapKey: homeKey });
    if (chain) return refuse(ref, chain);

    const filters = buildKeyFilters(binding.keyColumns, ref.mapKey, spec.columnTypes);
    const url = `${API_BASE}/tables/${ref.table}/data?limit=${OVERLAY_CELL_LIMIT + 1}`
      + `&filters=${encodeURIComponent(JSON.stringify(filters))}`;
    const res = await fetch(url);
    if (!res.ok) return refuse(ref, `${ref.table}: 참조 맵 셀 조회 실패 (HTTP ${res.status}).`);
    const result = await res.json();
    const rows = Array.isArray(result && result.data) ? result.data : [];
    // 절단은 실패로 강등한다 — 잘린 집합으로 만든 마스크는 실제보다 **작은** 유효 다이
    // 집합이고, 그 차이는 화면에 나타나지 않는다.
    if (rows.length > OVERLAY_CELL_LIMIT) {
      return refuse(ref, `${ref.table} · ${ref.mapKey}: 참조 맵이 ${OVERLAY_CELL_LIMIT}행을 넘어 절단됐습니다.`);
    }

    const cells = [];
    rows.forEach(row => {
      const d = row.data || {};
      const xn = parseInt(d[binding.x] ? d[binding.x].value : undefined, 10);
      const yn = parseInt(d[binding.y] ? d[binding.y].value : undefined, 10);
      if (Number.isFinite(xn) && Number.isFinite(yn)) cells.push({ x: xn, y: yn });
    });
    if (cells.length === 0) {
      // [1-a] 규격은 있는데 셀이 없다 — 이것도 「여기서 찾지 못했다」이므로 같은 어휘로 말한다.
      return refuse(ref, `이 유효 다이 맵을 ${VALID_DIE_TABLE}에서 찾을 수 없습니다 — 키 `
        + `「${ref.mapKey}」의 규격은 있으나 좌표로 읽히는 셀이 한 건도 없습니다.${redirectNote}`);
    }

    // 격자 규격 호환성 — 물리 좌표는 정준 격자의 인덱스다. 치수가 다르면 같은 인덱스가
    // 같은 다이가 아니다.
    //
    // 이 자리는 세 번 답이 바뀌었고, 그 이력을 남겨 둔다(다음 라운드가 처음부터 다시
    // 유도하지 않도록):
    //   ① 종전 — 치수가 다르면 **거절**. 운영자는 이미 `wafer_map_metadata`에 선언돼 있는
    //      값을 손으로 다시 입력해야 했다.
    //   ② [F6] — 거절 대신 **격자를 참조 맵 크기로 열었다**(채택). 그러자 같은 칸이 다른
    //      DB 좌표를 낳아, 좌표를 지키려면 셀을 재배치해야 했고, 새 프레임이 만들지 못하는
    //      좌표 앞에서는 셀을 버리거나 번호를 다시 매기는 수밖에 없었다.
    //   ③ [F8, 지금] — **아무것도 채택하지 않는다.** 아래 블록이 그 이유다.
    // 회전·면 차이는 여기 오지도 않는다: 물리 키가 회전 불변이라 변환이 이미 처리한다.
    const refResolved = resolveFrame(refFrame);
    const hereResolved = resolveFrame(currentFrame());
    // ═══ [F8] 치수가 달라도 **아무것도 채택하지 않는다** — 사용자 지시 2026-07-30 ══════════
    // 「그리드 크기가 달라도 좌표는 db값 그대로 보존하고 화면 표기 밀리게 그냥 보여주기」.
    //
    // 🔴 이 결정의 근거는 데이터 모델이다. 셀에 저장된 좌표라는 것은 **없다** — `gridData`는
    //    `물리 키 → 값`뿐이고, DB의 x/y는 Push 시점에 `cellObj.x/.y`(= 현재 프레임으로 렌더가
    //    유도한 좌표)에서 만들어진다(`pushMapData`의 직렬화 루프). 그래서 "좌표를 보존한다"는
    //    말의 유일한 구현은 **칸을 그대로 두는 것**이고, 격자 치수·원점을 건드리지 않는 것이
    //    곧 그것이다. 치수를 채택하면 같은 칸이 다른 좌표를 낳는다 — 그것이 F6이 재배치라는
    //    기계장치를 만들어 막으려던 것이고, 재배치는 새 프레임이 만들지 못하는 좌표 앞에서
    //    셀을 버리거나(삭제) 번호를 다시 매기는(재좌표화) 수밖에 없었다. 둘 다 금지다.
    //
    // 🔴 **마스크는 이것과 무관하게 옳다.** 마스크 키는 `projectCellsToPhys(cells, refFrame)`이
    //    참조 자신의 프레임으로 만든다(아래) — 화면 컨트롤을 읽지 않는다. 채택이 하던 일은
    //    타깃의 인덱스 공간을 참조의 것과 **맞춰** 마스크가 겹쳐 보이게 하는 것뿐이었다.
    //    맞추지 않으면 마스크는 밀려 보인다. 사용자가 요구한 것이 정확히 그 화면이다.
    //
    // ⚠️ 그래서 이 분기는 **말만 한다.** 밀림은 원인이 화면에 남지 않는 종류의 차이라
    //    (격자는 멀쩡해 보이고 마스크만 어긋난다) 조용하면 운영자가 데이터를 의심한다.
    //    확인창이 아니라 토스트 1회다 — 읽기는 무마찰(UI 규율).
    // ═══ 정렬의 축은 **원점 셀**이지 격자 크기가 아니다 ════════════════════════════════
    //
    // 🔴 종전에는 이 경보가 **치수만** 비교했다. 그래서 `MID_01 ← 4MAIN_DT`(둘 다 23×23,
    //    시작 좌표 (1,1) 대 (−4,−3))에서 마스크가 5열·4행 밀려 앉는데 **아무 말도 하지
    //    않았다.** 크기가 같다는 것은 정렬이 같다는 뜻이 아니다 — 같은 DB 좌표가 같은 다이를
    //    가리키는지를 정하는 것은 **원점**이다.
    //
    // 🔴 판정은 **새 기하식 없이** 한다. `projectCellsToPhys`는 마스크 키를 만드는 바로 그
    //    함수이므로, 셀 하나(DB 0,0)를 두 프레임으로 각각 투영해서 물리 키를 비교하면
    //    "마스크가 겹치는가"를 마스크와 **같은 규칙으로** 묻게 된다(불변식 ①: 변환 구현은
    //    하나다. 프레임 창만 갈아끼운다). 캔버스 좌표로 비교하면 안 된다 — 물리 키는 회전
    //    불변이라 회전만 다른 참조는 실제로 겹치는데 캔버스 열은 다르고, 그러면 **거짓 경보**가
    //    난다(이 파일이 아래에서 "회전·면 차이는 여기 오지도 않는다"고 적어 둔 그 이유다).
    //
    // ⚠️ 치수 비교는 **지우지 않고 남긴다.** 원점이 같아도 격자 범위가 다르면 참조 마스크의
    //    일부가 이 격자 밖에 앉는다 — 밀림과는 다른 사실이고, 운영자가 지금 받고 있는 정보다.
    //    둘 중 어느 쪽이 성립했는지는 문구가 구분해서 말한다.
    // ⚠️ 원점 어긋남은 여기서 재지 않는다. 종전에는 `projectCellsToPhys([{x:0,y:0}], frame)`을
    //    두 프레임으로 돌려 물리 다이를 비교했는데, 그 비교는 **마스크를 격자 중심으로 다시
    //    앉히기 전**의 인덱스 공간에서 이뤄져 화면과 무관한 수를 냈다(실측: 화면은 중앙에
    //    맞아 있는데 「31칸·8행 어긋남」을 찍었다). 마스크가 앉은 뒤에 한 번만 잰다(아래).
    // ⚠️ 치수 비교는 **`set`이 격자를 다시 파생시킨 뒤에** 잰다(아래 로그 블록). 여기서 재면
    //    아직 옛 치수를 들고 있어, 파생으로 이미 같아진 치수를 「다릅니다」라고 말한다 ―
    //    화면과 어긋나는 진단은 진단이 아니다.

    // ═══ 유효 다이 맵이 좌표계의 중심이다 (사용자 확정 2026-07-30) ═══════════════════
    // 「유효 다이 로드 시 유효 다이 맵을 중심으로 회전, 반전 적용. Y INVERT 여부 맞추어서
    //   유효 다이 영역 X,Y 최솟값이 START X,Y가 되게 좌표계 및 ORIGIN CELL 설정.
    //   유효 다이 맵이 원 기하 중심이 되는 스킴.」
    //
    // 🔴 종전에는 `projectCellsToPhys(cells, refFrame)` 하나로 끝냈다. 그 함수가 만드는 물리
    //    인덱스의 원점은 **격자 중심** `(cols-1)/2`다. 참조 23x23(중심 11)과 이 맵 45x45(중심
    //    22)는 서로 다른 인덱스 공간이라 같은 키가 같은 다이가 아니었다 ― 마스크가 좌상단으로
    //    밀려 앉고 오리진 셀만 중앙에 남은 실측 화면의 원인이 이것이다.
    // 🔴 그래서 회전·반전의 중심을 **마스크 자신**으로 옮긴다: 마스크 집합의 중심이 이 격자의
    //    중심에 오도록 통째로 평행이동한다. 그러면 두 인덱스 공간이 마스크 위에서 만나고,
    //    격자 중심을 축으로 도는 기존 회전이 곧 마스크를 축으로 도는 회전이 된다.
    //    새 기하식은 없다 ― `projectCellsToPhys`의 결과에 정수 평행이동 하나를 얹을 뿐이다.
    const rawKeys = [...projectCellsToPhys(cells, refFrame).keys()];
    if (rawKeys.length === 0) {
      return refuse(ref, `${ref.table} · ${ref.mapKey}: 참조 맵을 물리 좌표로 투영한 결과가 비었습니다.`);
    }
    // ⚠️ 이 셋은 **지정 전** 화면이다. 로그 2)는 「현재 메타값」이라는 이름 그대로 그것을
    //    말하고, 지정 뒤의 격자는 아래 로그 블록이 컨트롤에서 다시 읽는다(`postCols/postRows`).
    const hereCols = gridDimNum(null, 'cols', el.gridCols, 10);
    const hereRows = gridDimNum(null, 'rows', el.gridRows, 10);
    const hereInvertY = !!(el.gridYInvert && el.gridYInvert.checked);
    const mask = deriveMaskKeys(rawKeys);
    const maskCx = mask.maskCx;
    const maskCy = mask.maskCy;
    const shiftX = mask.shiftX;
    const shiftY = mask.shiftY;
    const keys = mask.keys;

    // 🔴 유효 다이 영역의 X,Y 최솟값이 START X,Y다. 최솟값의 출처는 **참조 맵 자신의 좌표**다 ―
    //    이 캔버스에서 읽은 좌표를 쓰면 그 좌표가 이미 START로 만들어진 값이라 순환한다.
    //    Y 반전은 여기서 갈리지 않는다: `getDbCoords`가 START Y를 반전 시 아래 끝
    //    (box.maxR), 아닐 때 위 끝(box.minR)에 놓으므로 어느 쪽이든 START Y는 그 영역의
    //    최소 Y 좌표다. 갈리는 것은 값이 아니라 **어느 행에 놓이는가**이고 그것은 이미 하나의
    //    함수가 정한다(로그 4·6이 어느 행인지 찍는다).
    const refMinX = Math.min(...cells.map(c => c.x));
    const refMinY = Math.min(...cells.map(c => c.y));

    // [규칙 ①] 「유효 다이 영역은 맵 기하 메타와 한 몸」 ― 참조의 기하를 함께 들여온다.
    // 여섯 물리 값뿐이다. 격자 치수는 넘기지 않고 `set`이 이 규격에서 **파생**한다(§set의 (a)).
    const out = set('ref', keys, '', ref, {
      phys_wafer_dia: refResolved.waferDia,
      phys_chip_x: refResolved.chipX,
      phys_chip_y: refResolved.chipY,
      phys_offset_x: refResolved.offsetX,
      phys_offset_y: refResolved.offsetY,
      phys_edge_margin: refResolved.edgeMargin,
    });

    // ── 사용자 QA용 6점 로그. cp949로 인코딩 불가한 문자가 하나라도 들어가면 한국어 콘솔의
    //    로깅 핸들러가 줄 전체를 버리므로 em dash(U+2014)·이모지를 쓰지 않는다(U+2015 사용).
    if (!stale()) {
      const diag = diagnoseDesignationAlignment(refResolved, hereResolved, refMinX, refMinY,
        hereInvertY, el, currentRotation, currentSide);
      dimsDiffer = diag.dimsDiffer;
      originDiffer = diag.originDiffer;
      const box = diag.box;
      const gridCx = diag.gridCx;
      const gridCy = diag.gridCy;
      const sx = diag.sx, sy = diag.sy;
      const zero = diag.zero;
      const startRow = diag.startRow;
      console.log(`[유효다이] 1) 유효 다이맵 ― 참조 ${ref.table} / ${ref.mapKey}, 셀 ${cells.length}칸, `
        + `참조 프레임 ${refFrame.cols}x${refFrame.rows} start(${refFrame.startX},${refFrame.startY}) `
        + `rot=${refFrame.rotation} ${refFrame.side} yInvert=${refFrame.invertY}`);
      console.log(`[유효다이] 2) 현재 메타값 ― 이 맵 ${hereCols}x${hereRows} `
        + `start(${hereResolved.startX},${hereResolved.startY}) rot=${currentRotation} ${currentSide} `
        + `yInvert=${hereInvertY}`
        + (maskFitNote
          ? ` / 지정 후 격자 ${maskFitNote.to} (참조 규격에서 파생${maskFitNote.from !== maskFitNote.to ? `, 마스크를 담도록 ${maskFitNote.from}에서 넓힘` : ''}${maskFitNote.off > 0 ? `, 아직 ${maskFitNote.off}칸이 격자 밖` : ''})`
          : ''));
      console.log(`[유효다이] 3) 회전 중심 좌표 ― 마스크 중심 (${maskCx},${maskCy}), `
        + `격자 중심 (${gridCx},${gridCy}), 마스크 평행이동 (${shiftX},${shiftY})`);
      console.log(`[유효다이] 4) 반전 중심 축 ― X 미러 ${currentSide === 'back'
        ? `있음 (물리 x = ${gridCx} 기준)` : '없음 (front)'}, `
        + `Y 반전 ${hereInvertY ? '있음 (아래 끝이 START Y)' : '없음 (위 끝이 START Y)'}`);
      console.log(`[유효다이] 5) 캔버스 내 유효 다이 범위 ― 열 ${box.minC}~${box.maxC}, `
        + `행 ${box.minR}~${box.maxR}, ${keys.size}칸`);
      console.log(`[유효다이] 6) 오리진 캔버스 좌표 ― 열 ${zero.c}, 행 ${zero.r}. `
        + `선언된 START(${sx},${sy}) 는 열 ${box.minC} / 행 ${startRow} 에 놓임 `
        + `(참조 맵이 부르는 최솟값 ${refMinX},${refMinY})`);
      if (placementNote) console.log(placementNote);
    }
    // [F8] 밀림을 알린다. 대가를 셀 것이 없으므로(`classifyUnsavableCells`를 부르지 않는다)
    // 마스크가 앉은 뒤여야 할 이유도 없지만, 지정이 실제로 성립한 뒤에만 말하는 것이 맞다.
    if ((originDiffer || dimsDiffer) && !stale()) {
      // 사유는 성립한 것만 말한다 ― 원점과 치수는 서로 독립이고, 둘 다 어긋날 수도 있다.
      // ⚠️ **cp949를 벗어나는 문자를 쓰지 않는다.** 운영 콘솔이 한국어 Windows 콘솔이라
      //    em dash(U+2014) 한 글자에 로깅 핸들러가 **줄 전체를 버린다** ― 이 진단은 그동안
      //    사용자 화면에 한 번도 도착하지 않았다. U+2015(―)를 쓴다.
      // 🔴 문구가 말하는 두 절반을 구분한다: **좌표는 바뀌지 않는다**(START X,Y는 운영자의
      //    선언이고 편집기가 건드리지 않는다), 그러나 **표시는 움직인다**(마스크가 참조의
      //    원점 기준으로 다시 앉으므로 셀과 마스크가 화면에서 함께 이동한다).
      // 🔴 **두 수는 다른 것을 잰다. 섞어 쓰면 안 된다.**
      //    `originDiffer` ― 참조가 자기 최소 다이를 뭐라 부르는가 vs 이 맵의 선언된 START.
      //                     프레임 정렬의 사실이고, 데이터를 움직이는 양이 **아니다**.
      //    `screenShift`  ― 이번 지정으로 셀과 마스크가 화면에서 실제로 움직인 칸 수.
      //    실측 사례(4E → DT)에서 전자는 (1,1)인데 후자는 (-3,-2)였다. 종전 문구는 전자를
      //    「어긋남」으로 내놓아 사용자가 본 이동량과 맞지 않았다.
      const why = [
        originDiffer ? `참조가 부르는 최솟값 ${originDiffer.there} 과 이 맵의 선언된 START `
          + `${originDiffer.here} 이 다릅니다` : '',
        dimsDiffer ? `격자 치수가 다릅니다 (참조 ${dimsDiffer.there} · 이 맵 ${dimsDiffer.here})` : '',
      ].filter(Boolean).join(' · ');
      console.info('[Map Editor][F8] valid-die reference is not aligned with the editor frame ― '
        + (originDiffer ? `the reference calls its minimum die (${originDiffer.there}) while this map's `
          + `declared START is (${originDiffer.here}), a gap of (${originDiffer.dx},${originDiffer.dy}); ` : '')
        + (dimsDiffer ? `grid ${dimsDiffer.there} != ${dimsDiffer.here}; ` : '')
        + 'NOTHING adopted and NO coordinate changed ― grid_start_x/y stay as declared, so the x/y '
        + 'Push writes are untouched. The mask is re-centred on this grid, so cells and mask moved '
        + 'together on SCREEN only.');
      showToast(`유효 다이 참조 맵이 이 맵과 정렬되지 않아 마스크가 밀려 있습니다 ― `
        + `${why}. 좌표는 하나도 바뀌지 않았고 ⚡ Push가 기록할 x/y도 그대로입니다. `
        + (screenShift
          ? `셀과 마스크는 화면에서 ${Math.abs(screenShift.dc)}칸·${Math.abs(screenShift.dr)}행 `
          + `함께 이동했습니다 ― 각 셀은 자기 좌표가 가리키는 칸으로 다시 앉았습니다.`
          : `셀이 앉는 칸은 이번에 바뀌지 않았습니다.`),
        'info', { dedupeKey: 'valid_die_frame_differs' });
    }
    return out;
  } catch (e) {
    // 🔴 **이 catch는 예상된 실패의 자리가 아니다.** 조회·데이터·계약 실패는 전부 위에서
    //    저자가 쓴 문구로 이미 거절했다(`refuse`). 여기까지 오는 것은 대개 **프로그래머
    //    오류**다 — 그리고 그 `e.message`를 그대로 사유로 흘리면 "거절은 사유를 가진다"는
    //    계약을 **스택 트레이스가 만족시킨다.** 실측(F6 라운드): 하네스가 함수 하나를
    //    추출 목록에서 빠뜨렸을 때 칩의 사유가 `<함수명> is not defined`가
    //    됐고, 그것은 형식상 "비지 않은 사유"였다. 운영자에게는 아무것도 설명하지 않고,
    //    데이터 문제라고 오해할 여지만 준다(그래서 엉뚱한 데이터를 고치러 간다).
    //    ⚠️ 사유를 **지우지는 않는다** — 원문은 괄호에 남기고 콘솔에 전체 오류를 남긴다
    //    (§PRIMITIVES "읽을 수 없는 값은 지어내지 말고 원문으로": 증거를 없애면 무엇을
    //     고쳐야 하는지가 사라진다). 바꾸는 것은 **부류를 이름 붙이는 것**뿐이다.
    //    판정은 `e.name`으로 한다 — `instanceof`는 realm이 다르면(하네스의 vm 샌드박스,
    //    iframe) 조용히 거짓이 되어 이 분류 자체가 꺼진다.
    const detail = (e && e.message) ? e.message : String(e);
    const internal = !!e && (e.name === 'TypeError' || e.name === 'ReferenceError'
      || e.name === 'RangeError' || e.name === 'SyntaxError');
    if (internal) {
      console.error('[Map Editor][M4] valid_die_ref 해석 중 내부 오류 (프로그램 결함)', e);
      return refuse(ref, `${ref.table} · ${ref.mapKey}: 유효 다이 해석 중 내부 오류가 발생했습니다 `
        + `— 맵 데이터의 문제가 아니라 프로그램 결함입니다. 데이터를 고치려 하지 마시고 `
        + `개발자 콘솔의 오류와 함께 알려 주십시오 (${detail}).`);
    }
    return refuse(ref, `${ref.table} · ${ref.mapKey}: ${detail}`);
  }
}

// ── [R5 step ①] Does the derived grid hold the whole mask? ───────────────────────────────
// Lifted out of `resolveValidDie`'s `set` closure verbatim. It takes every binding it reads as
// an argument (`el`, `currentRotation`, `currentSide` deliberately shadow the module bindings of
// the same name), so it reads NO module state: the body is byte-identical to what ran inline.
// Returns the note the diagnostic log prints; the caller owns the assignment.
function fitGridToMask(keys, el, currentRotation, currentSide) {
  const dimMax = frameDimBounds().max;
  // 축별 위반 수. 두 축을 따로 세는 이유는 넓힐 치수를 **측정으로** 고르기 위해서다.
  const missAt = (c, r) => {
    const rot90 = (currentRotation === 90 || currentRotation === 270);
    const vC = rot90 ? r : c, vR = rot90 ? c : r;
    let col = 0, row = 0;
    keys.forEach(k => {
      const [px, py] = String(k).split('_').map(Number);
      if (!Number.isFinite(px) || !Number.isFinite(py)) return;
      const at = getCanvasCellFromDieIndex(null, px, py, c, r, currentRotation, currentSide);
      if (at.c < 0 || at.c >= vC) col++;
      if (at.r < 0 || at.r >= vR) row++;
    });
    return { col, row, any: col + row };
  };
  let gc = gridDimNum(null, 'cols', el.gridCols, 10);
  let gr = gridDimNum(null, 'rows', el.gridRows, 10);
  const fromC = gc, fromR = gr;
  let miss = missAt(gc, gr);
  // 한 번에 한 칸. 키가 덮는 범위는 치수에 대해 **중첩 단조**다(치수 +1은 한쪽 끝에
  // 정확히 한 칸을 더한다), 그래서 위반이 난 축만 늘리면 최소 치수에서 멈춘다.
  // 멈추는 이유는 하나여야 한다 ― **편집기의 치수 정의역**(H5, `frameDimBounds`).
  // 걸음 수 상한은 그 정의역에서 나온 값이라(두 축 × 상한) 실제로 멈추는 것은 언제나
  // 치수 쪽이고, 걸음 수는 무한 루프를 막는 안전핀일 뿐이다. 상한에 닿으면 **더 넓히지
  // 않고 멈추고 사유를 남긴다** ― 조용히 자라지도, 잘라 내지도 않는다.
  for (let step = 0; miss.any > 0 && step < 2 * dimMax; step++) {
    // 열을 정하는 치수는 rot 90/270에서 rows, 그 밖에서는 cols다 ― 이 파일이 도처에서
    // 쓰는 `visualCols = isRotated90or270 ? rows : cols` 한 줄의 결과일 뿐이다.
    const rot90 = (currentRotation === 90 || currentRotation === 270);
    let grew = false;
    if (miss.col > 0) {
      if (rot90) { if (gr < dimMax) { gr += 1; grew = true; } }
      else if (gc < dimMax) { gc += 1; grew = true; }
    }
    if (miss.row > 0) {
      if (rot90) { if (gc < dimMax) { gc += 1; grew = true; } }
      else if (gr < dimMax) { gr += 1; grew = true; }
    }
    if (!grew) break;
    miss = missAt(gc, gr);
  }
  if (gc !== fromC || gr !== fromR) {
    if (el.gridCols) el.gridCols.value = gc;
    if (el.gridRows) el.gridRows.value = gr;
  }
  const maskFitNote = { from: `${fromC}x${fromR}`, to: `${gc}x${gr}`, off: miss.any, total: keys.size };
  if (miss.any > 0) {
    console.warn(`[Map Editor][M4] the valid-die mask does not fit the grid: ${miss.any} of `
      + `${keys.size} mask cells stay off the canvas at ${gc}x${gr} (editor dimension `
      + `ceiling ${dimMax}). NOT grown further and NOT clipped ― the cells keep their `
      + 'stored coordinates and the ones outside the grid are reported by the Push gate.');
  }
  return maskFitNote;
}

// ── [R5 step ②] How many seats did this designation actually move? ──────────────────────
// The net count, taken as a set difference over PHYSICAL seat keys — see the comment it
// carries. Every binding it reads is an argument, so it reads no module state; the caller
// keeps the `netMoved > 0` branch, so the control flow at the call site is unchanged.
function summariseReseat(seatsBefore, placed, nc, nr, gridData, loadedFCells, serverCellKeys) {
  // 넷 이동량 ― 이 호출 전체에서 자리를 옮긴 셀 수. 걸음마다 세면 서로 상쇄되는 두 걸음이
  // 「N칸 이동 후 N칸 이동」으로 읽혀 사용자에게 거짓 수를 준다. 좌석은 물리 키이므로
  // 집합 차이가 곧 이동한 셀이다.
  const seatsAfter = new Set([...Object.keys(gridData), ...loadedFCells,
  ...(serverCellKeys && serverCellKeys.keys ? serverCellKeys.keys : [])]);
  let netMoved = 0;
  seatsBefore.forEach(k => { if (!seatsAfter.has(k)) netMoved++; });
  let note = '';
  if (netMoved > 0) {
    note = `[유효다이] 7) 셀 재배치 ― ${netMoved}칸을 저장된 좌표에서 다시 앉힘 `
      + `(격자 ${placed ? placed.visC : nc}x${placed ? placed.visR : nr}, `
      + `격자 밖으로 나간 셀 ${placed ? placed.offGrid : 0}칸). `
      + `번호는 그대로이고 앉는 칸만 바뀜`;
  }
  return { netMoved, note };
}

// ── [R5 step ③] The reference map's key spec, coordinate binding, metadata and frame ─────
// One await chain, three refusals, no module state (STATE# 0). `ref` is passed in and its
// `mapKey` is canonicalised IN PLACE exactly as before. A refusal is returned as a REASON, not
// taken: `refuse` writes module state and stays with the orchestrator that owns those writes.
// `fetchGridMetaFor` still throws on failure and the rejection still lands in the caller's
// catch — that classification is what `M9b`/`M9c` score.
async function resolveReferenceSpec(ref) {
  // [7b] 참조된 맵 키도 캐노니컬화한다 — 여기서만 원문을 쓰면 이 라운드가 고친 그 결함이
  // 유효 다이 경로로 그대로 재현된다.
  const spec = await fetchMapKeySpec(ref.table);
  if (spec.ok && spec.keyColumns.length > 0) {
    ref.mapKey = canonicalMapKey(spec.keyColumns, ref.mapKey, spec.columnTypes);
  }

  const binding = await fetchServedBinding(ref.table);
  if (!binding) {
    return { ok: false, reason: `${ref.table}: 좌표 바인딩을 서버가 해석해 주지 못했습니다.` };
  }
  if (binding.source === 'fallback_guess') {
    // 오버레이 경로와 같은 규율(§5.6-bis) — 추측한 컬럼으로 마스크를 만들면 그 마스크는
    // 미끼다. 그리는 것보다 더 나쁘다: 보이지 않는 채로 페인팅을 막거나 허용한다.
    return { ok: false, reason: `${ref.table}: 값/좌표 컬럼이 추측(fallback_guess)뿐입니다.` };
  }

  const refMeta = await fetchGridMetaFor(ref.table, ref.mapKey);   // 실패는 throw
  const refFrame = frameFromMeta(refMeta);
  if (!refFrame) {
    // 미등록도 여기서는 거절이다. 오버레이는 규격이 없으면 "무보정"이라고 **화면에
    // 적어서** 알리지만, 마스크는 보이지 않는 기계장치라 같은 폴백이 조용해진다.
    //
    // [1-a] NAMED REFUSAL. 고정된 로드 경로에서 가장 흔해진 실패가 바로 이것이다 —
    // 고정 이전에 저작된 선언의 키는 `valid_die_ref`에 없다. 거절문은 **찾은 키를
    // 이름으로 말한다**: 빈 마스크는 데이터처럼 보이는 거짓말이라 그보다 낫다.
    return { ok: false, notFound: true,
      reason: `이 유효 다이 맵을 ${VALID_DIE_TABLE}에서 찾을 수 없습니다 — 키 「${ref.mapKey}」로 `
        + `등록된 맵 규격(wafer_map_metadata)이 없습니다.` };
  }
  return { ok: true, spec, binding, refMeta, refFrame };
}

// ── [R5 step ④] The mask key set, and its centre ────────────────────────────────────────
// Moved verbatim, translation term included. The zeroed shift and the warning that explains
// why it must stay zero travel together — separating the number from its reason is how it got
// revived once already.
function deriveMaskKeys(rawKeys) {
  const pxs = rawKeys.map(k => Number(String(k).split('_')[0]));
  const pys = rawKeys.map(k => Number(String(k).split('_')[1]));
  const maskCx = (Math.min(...pxs) + Math.max(...pxs)) / 2;
  const maskCy = (Math.min(...pys) + Math.max(...pys)) / 2;
  // 🔴 **평행이동하지 않는다.** da8f390이 여기에 평행이동을 넣은 이유는 `projectCellsToPhys`가
  //    키를 **각 프레임 자신의 격자 중심**으로 만들어서 23x23 참조와 45x45 맵이 같은 키를
  //    다른 다이로 불렀기 때문이다. 그 원인은 이제 없다(§getDieIndex: 키의 원점이
  //    웨이퍼 중심이다). 참조와 이 맵은 같은 좌표계에 있고, 맞출 것이 남아 있지 않다.
  // ⚠️ 되살리지 마라. 평행이동은 마스크의 **bbox 중점**을 격자 중심에 끌어다 놓는데, 웨이퍼
  //    위에서 실제로 치우쳐 앉은 유효 다이 영역은 그 조작으로 자기 다이에서 벗어난다 —
  //    사용자 규칙 ①「유효 다이 영역은 항상 물리 WF 내 상대 위치를 보존한다」에 정면으로
  //    어긋난다. 실측(bonding_map/DTWWER <- BASE_4E, 메타가 완전히 동일한 실데이터를
  //    독립 오라클로 대조): 평행이동이 (0,1)을 만들어 262칸 중 21칸이 틀린 다이에 앉았다.
  //    0으로 두면 262칸이 오라클과 정확히 일치한다.
  const shiftX = 0;
  const shiftY = 0;
  const keys = new Set(rawKeys.map(k => {
    const [px, py] = String(k).split('_').map(Number);
    return `${px + shiftX}_${py + shiftY}`;
  }));
  return { maskCx, maskCy, shiftX, shiftY, keys };
}

// ── [R5 step ⑤] What differs between the reference map and this one, AFTER the designation ─
// The two axes are independent — the origin can be off at the same size, and the same origin
// can carry a different size — so both are measured and each is reported only if it holds.
// Measured on the POST-designation grid (`set` may have re-derived it from the reference
// spec): a diagnosis solved with the old dimensions explains a screen the user is not looking
// at. STATE# 0 — the panel arrives as `el`, the orientation as arguments.
function diagnoseDesignationAlignment(refResolved, hereResolved, refMinX, refMinY,
  hereInvertY, el, currentRotation, currentSide) {
  const box = getWaferBoundingBox(null, currentRotation, currentSide);
  // 지정이 **끝난 뒤의** 격자. `set`이 참조 규격에서 다시 파생시켰을 수 있으므로 아래
  // 진단은 전부 이 수로 푼다 ― 옛 치수로 푼 진단은 화면과 다른 것을 설명한다.
  const postCols = gridDimNum(null, 'cols', el.gridCols, 10);
  const postRows = gridDimNum(null, 'rows', el.gridRows, 10);
  // 격자 중심을 **키 공간**으로 읽는다. 물리 키가 웨이퍼 중심 기준이 된 뒤로 그 중점은
  // 곧 패리티 항이다 — `getDieIndex`가 쓰는 바로 그 식이다(홀수 0, 짝수 0.5).
  const gridCx = (Math.abs(Math.round(postCols)) % 2 === 0 ? 0.5 : 0);
  const gridCy = (Math.abs(Math.round(postRows)) % 2 === 0 ? 0.5 : 0);
  // [F8] 치수 차이는 파생이 끝난 **뒤에** 잰다. 파생으로 같아졌다면 말할 것이 없다.
  let dimsDiffer = null;
  if (refResolved.cols !== postCols || refResolved.rows !== postRows) {
    dimsDiffer = {
      here: `${postCols}x${postRows}`,
      there: `${refResolved.cols}x${refResolved.rows}`
    };
  }
  // 🔴 **선언된 START로 푼다.** START X,Y는 운영자의 선언이고 편집기가 바꾸지 않는다
  //    (사용자 확정 2026-07-30: 「START X,Y는 바뀌면 안됨」). 그래서 마스크의 최소 열이
  //    읽는 값은 참조의 최솟값이 아니라 **이 맵이 선언한 START**이고, 오리진 셀은
  //    `box.minC - startX`에 선다.
  const sx = hereResolved.startX, sy = hereResolved.startY;
  const zero = getCanvasCellFromDb(null, 0, 0, postCols, postRows,
    currentRotation, currentSide, hereInvertY, sx, sy);
  const startRow = hereInvertY ? box.maxR : box.minR;
  // 정렬 차이는 **마스크가 앉은 뒤** 한 번만 잰다. 참조는 자기 최소 다이를
  // (refMinX,refMinY)로 부르고 이 맵은 같은 칸을 (sx,sy)로 부른다 ― 그 차이가 어긋남이다.
  let originDiffer = null;
  if (sx !== refMinX || sy !== refMinY) {
    originDiffer = {
      dx: sx - refMinX, dy: sy - refMinY,
      there: `${refMinX},${refMinY}`, here: `${sx},${sy}`
    };
  }
  return { box, postCols, postRows, gridCx, gridCy, dimsDiffer, originDiffer, sx, sy, zero, startRow };
}

// 근거가 원이 아닐 때만 보이는 한 줄. 새 패널·모드·모달이 아니라 이미 있는 상태바
// 칩(`plock-chip`, 페인트 잠금 표시)과 **같은 형태·같은 자리**다 — 선언 없는 맵에서는
// 존재조차 하지 않으므로 기존 화면의 복잡도는 0만큼 늘어난다.
function renderValidDieChip() {
  const host = document.getElementById('paint-lock-indicator');
  if (!host || !host.parentNode) return;
  let chip = document.getElementById('valid-die-indicator');
  const basis = validDieBasis();
  if (basis === 'circle') { if (chip) chip.style.display = 'none'; return; }
  if (!chip) {
    chip = document.createElement('span');
    chip.id = 'valid-die-indicator';
    chip.className = 'plock-chip';
    host.parentNode.insertBefore(chip, host.nextSibling);
  }
  chip.style.display = '';
  if (basis === 'template') {
    // [M4②] 저작 중. 새 패널·모드 표시가 아니라 이미 있는 이 칩의 네 번째 문구다.
    chip.textContent = `🧩 유효 다이 저작 중 — 격자 전체 ${validDie.keys.size}칸`;
    chip.title = '칠한 셀이 곧 유효 다이입니다 — [⚡ Push]로 저장하십시오.';
  } else if (basis === 'ref') {
    const r = validDie.ref || {};
    chip.textContent = `🎯 유효 다이: ${r.table || ''} · ${r.mapKey || ''} (${validDie.keys.size})`;
    chip.title = '유효 다이 근거: 참조 맵 (웨이퍼 원 아님)';
  } else {
    chip.textContent = '⚠️ 유효 다이 맵 미해석';
    chip.title = `해석 실패: ${validDie.reason}`;
  }
}

// ── [M4 phase 2] 지정/해제 컨트롤 ────────────────────────────────────────────────
// 새 패널도 모달도 아니다 — 물리 규격 블록(§2, 원 기하가 사는 자리)에 한 줄이다.
// **읽기는 무마찰**: 값을 보여 주는 데 확인창이 없다. **쓰기는 1회 확인**: 저장은 기존 ⚡ Push
// 확인 하나뿐이고 여기서 따로 묻지 않는다.
// [1-a] 컨트롤은 한 칸(키)뿐이다. 테이블 select를 되맞추던 블록은 사라졌고, 그것이 만들던
//       모호함(앱이 강제한 ''인가 사용자가 고른 ''인가)도 함께 사라졌다.
//       선언이 `valid_die_ref` 아닌 테이블을 가리키는 경우 — 이 규칙 이전에 저작된 것들 —
//       그 사실은 **거절문**이 말한다(`resolveValidDie`의 `redirectNote`). 칩이 아니다:
//       로드가 고정된 뒤로 칩의 `r.table`은 언제나 `valid_die_ref`라서 원 선언을 말할 수
//       없고, 저 사실이 필요한 순간은 정확히 해석이 실패했을 때뿐이다.
//       입력칸에 없는 정보를 만들어 넣지 않고, 있는 표시 자리를 쓴다(새 컨트롤 0개).
function syncValidDieRefControls() {
  const shown = validDieRefDisplay(validDie ? validDie.raw : undefined);
  if (el.validDieRefKey && el.validDieRefKey.value !== shown.key) el.validDieRefKey.value = shown.key;
  renderValidDieKeyControl();
}

// ── [1-a] 키 컨트롤의 **형태**를 정한다 — 드롭다운인가 입력칸인가 ──────────────────────
//
// 사용자 요청: "valid die 리스트를 datalist 말고 preset과 같은 형식으로". 형태는 위
// 「⚙️ Geometry Presets」의 `<select>`와 같게 하되, 그 형태가 **잃게 만드는 것**을 잃지
// 않는다: datalist는 제안이라 목록에 없는 키도 타이핑해 열 수 있고, `<select>`는 제약이라
// 열 수 없다. 그 차이가 실제로 문제가 되는 상황은 셋이고, 셋 다 이미 관측 가능하다:
//   ① truncated   — 서버가 "등록된 맵이 더 있다"고 말했다. 목록은 모집단이 아니다.
//   ② unavailable — 조회가 실패했다. 목록이 비어 있는 것은 「없다」는 뜻이 아니다.
//   ③ 지금 지정된 키가 목록에 없다 — 고정 이전에 저작된 선언이 정확히 이 경우다.
//      여기서 `<select>`를 내밀면 그 키를 **표시할 수조차 없어** 컨트롤이 "-- 원 기하 --"로
//      보인다. 지정이 있는 맵을 지정이 없는 것처럼 보여 주는 것 — 화면은 멀쩡한데 값이
//      틀리는 그 결함이라, 이 조건이 없으면 이 변경 자체가 결함이 된다.
// 셋 중 하나라도 참이면 입력칸을 유지한다. 사용자가 고를 것은 없다 — **어느 컨트롤이
// 보이는가가 곧 "이 목록이 전부인가"의 답**이다. 순 컨트롤 증가는 0이다(동시에 하나만 보인다).
//
// 🔴 **값의 정본은 `#valid-die-ref-key` 하나다.** select는 고른 값을 그 칸에 적을 뿐이고,
//    `validDieRefFromControls`·`validDieRefForPush`·APPLY·SAVE는 전부 그 칸만 읽는다.
//    select에서 따로 값을 읽으면 저장이 보는 수와 화면이 보는 수가 갈라진다.
// 🔴 옵션 집합은 datalist에서 **그대로** 가져온다. 두 번째 조회도, 두 번째 목록도 없다.
function renderValidDieKeyControl() {
  const sel = el.validDieRefSelect;
  const inp = el.validDieRefKey;
  const list = el.validDieRefList;
  if (!sel || !inp || !list) return;

  const keys = Array.from(list.options || []).map(o => o.value)
    .filter(v => v !== null && v !== undefined && String(v).trim() !== '');
  const state = (inp.dataset && inp.dataset.suggest) ? inp.dataset.suggest : '';
  const cur = (inp.value || '').trim();

  const listIsWholePopulation = (state === '');          // ①②의 부정
  const curIsSelectable = (cur === '' || keys.indexOf(cur) !== -1);   // ③의 부정
  const useSelect = listIsWholePopulation && curIsSelectable && keys.length > 0;

  // 옵션은 매번 다시 그린다 — 목록이 갱신됐는데 옵션이 낡으면 그 낡음은 보이지 않는다.
  sel.innerHTML = '';
  const none = document.createElement('option');
  none.value = '';
  // 🔴 빈 선택은 빈 입력칸과 **정확히 같은 뜻**이다: 지정 없음 = 웨이퍼 원 기하.
  //    그 등가가 이 변경을 안전하게 만드는 유일한 근거라 문구로도 못 박는다.
  none.textContent = '-- 원 기하 (지정 없음) --';
  sel.appendChild(none);
  keys.forEach(k => {
    const o = document.createElement('option');
    o.value = k;
    o.textContent = k;
    sel.appendChild(o);
  });
  sel.value = curIsSelectable ? cur : '';

  sel.style.display = useSelect ? '' : 'none';
  inp.style.display = useSelect ? 'none' : '';
}

// ══ 적용 — 지정을 **화면에** 적용한다. 저장하지 않는다 ═══════════════════════════════════
//
// [3-a→1-b] 함수도 계약도 **한 글자도 바뀌지 않았다.** 세 번째로 바뀐 것은 부르는 사람뿐이다:
//       ① 처음 = 키 입력칸의 `change`(blur/Enter) → 값을 확인하려고 나가기만 해도 적용됐다.
//       ② 3-a  = 🎯 APPLY 버튼 클릭.
//       ③ 지금 = 드롭다운 `change`(고르는 것이 곧 확정) · 입력칸 Enter(치는 중이 아니라 친 뒤).
//       APPLY 버튼이 사라진 이유는 ①이 되살아나서가 아니라 그 반대다 — 키 칸이 `<select>`가
//       된 뒤로 「고르기」 자체가 이산적 확정이라 버튼이 더할 것이 없어졌다(사용자 지시).
//       그래서 board 규칙 ①(유효 다이 영역을 불러오면 이 맵의 기하 메타를 그 유효 다이의
//       것으로 갈아끼운다)과 규칙 ④(유효 영역이 바뀌어도 저장된 셀 좌표는 바뀌지 않는다)는
//       그대로다 — 둘 다 `resolveValidDie` 안에 있고 그 함수는 손대지 않았다.
//       규칙 ①의 구현은 `set(..., physPreset)`의 `applyPresetObject` + `fitGridToMask`,
//       규칙 ④의 구현은 그 직후의 `reseatCellsToStoredCoords`다(셀은 칸이 아니라 자기
//       저장 좌표를 붙든다).
//
// 저장은 아니다 — 저장은 📐 규격만 저장(규격 블록) 또는 ⚡ Push(맵 전체)다. `resolveValidDie`가
// `validDie.raw`를 새 값으로 세우므로 이후 저장이 쓰는 값과 화면이 보는 값이 갈라질 수 없다.
async function onValidDieRefChanged() {
  // [F1] 저장 결정과 **같은 함수**로 컨트롤을 읽는다. 여기서만 따로 읽으면 두 수가 갈라진다.
  const { table, key } = validDieRefFromControls();
  const meta = {};
  if (key !== '') meta.valid_die_ref = (table === '') ? key : { table, map_id: key };
  await resolveValidDie(meta, selectedTable,
    (loadedIdentity && loadedIdentity.mapKey) ? loadedIdentity.mapKey : getCurrentMapKey());
  renderGridCanvas();
  // [fix E-2] APPLYING A DECLARATION IS AN EDIT OF THIS FRAME. `frameTouched` was set by the
  // two cell/legend gateways only, so a valid-die pick left the frame marked CLEAN and
  // `popMapFrame` discarded it with no prompt (live regression, 2026-08-04). Marking belongs
  // HERE because this is the one funnel every applying gesture reaches — the `<select>`
  // `change` and the key input's Enter both call it, and so does any future caller.
  // 🔴 NOT inside `resolveValidDie`: the load path calls that function too, and marking there
  //    would make a merely-VIEWED map prompt on the way back — the complaint [fix E] closed.
  // 🔴 `legendDirty` is deliberately NOT set. That flag means "cells or legend hold unsaved
  //    draft work", and the back-prompt reads its ABSENCE to name 📐 규격만 저장 instead of
  //    ⚡ Push. Setting it here would make every declaration change advertise the expensive
  //    writer, and would also light the plan-head unsaved chip for a plan nobody touched.
  // `framePushed` is cleared on the same ground the overlay import clears it (:10498): an
  // edit made after a successful Push means the screen again holds something the server
  // does not have, and the guard has to come back to life for it.
  frameTouched = true;
  framePushed = false;
  if (key === '') {
    showToast('유효 다이 지정을 해제했습니다 — 원 기하. [📐 규격만 저장] 또는 [⚡ Push]로 저장하십시오.',
      'info', { dedupeKey: 'valid_die_cleared' });
  }
}

// ══ 📐 규격만 저장 — 규격 **블록**을 쓴다. 셀은 하나도 쓰지 않는다 ═══════════════════════
//
// [2] 사용자 지시(2026-08-04): "맵 에디터에 메타만 저장하는 기능 필요",
//     "현재 설정된 테이블과 맵 아이디로 메타만 저장필요".
//     이것은 지워진 💾 SAVE의 **일반형**이다. 그쪽은 `valid_die_ref` 한 필드만 썼고, 그
//     한 필드는 ⚡ Push가 이미 함께 실어 나르므로 얻는 것이 없어 삭제됐다. 없던 것은
//     **규격 블록 전체**를 셀 없이 저장하는 길이다 — 격자·시작 좌표·회전·면·물리 규격.
//     ⚡ Push는 `replace_map`이라 맵 전량 재기록을 통과해야 하는데, 셀이 하나도 바뀌지
//     않은 상태에서 그것을 요구하는 것은 불변식 ④(불완전한 집합에서 replace_map은
//     파괴적이다)를 매번 다시 굴리는 일이다.
//
// 🔴 **새 라우트는 없다.** 💾 SAVE가 쓰던 그 PUT(`wafer_map_metadata/data/updates`)이다.
//    그 엔드포인트는 `business_key_val`로 upsert한다(`crud._get_or_create_row`, 응답의
//    `inserted`가 그 증거) — 그래서 **없는 행을 만드는 것도 같은 호출**이고, 서버는 한
//    줄도 바뀌지 않는다.
// 🔴 **규격 객체의 조립기는 하나다.** `buildPushGridMetadata` — ⚡ Push가 부르는 그 함수다.
//    여기서 객체를 다시 짜면 "규격이 무엇인가"의 철자가 둘이 되고, 그것이 이 저장소의
//    재발 결함 계급이다. 컨트롤 독법도 `readGridFrameControls` 하나를 공유한다.
// 🔴 **읽고-고쳐-쓴다(불변식 ③).** 조회 실패(throw)에 쓰면 안 된다 — 빈 객체 위에 얹으면
//    남의 필드가 한 번의 저장으로 사라진다. 병합은 `mergeStoredGridMeta`(순수 함수).
// 🔴 **정체성은 지금 화면의 컨트롤이다**(사용자 지시). `loadedIdentity`가 아니다 — 맵을
//    열고 키를 바꿔 새 정체성으로 기하를 등록하는 것이 이 기능의 쓰임이다. 대신 그래서
//    오타 하나가 **없던 맵을 등록**할 수 있으므로, 확인문이 대상과 신규/갱신을 이름으로
//    말한다. 그 신규/갱신은 추정이 아니라 **읽어서** 정한다(위의 `stored`).
//
// UI 규율: 읽기는 무마찰, **쓰기는 1회 확인**. 확인창은 정확히 하나이고, 격자 밖으로
// 밀려나는 셀 수는 그 하나 안에 있다(뒤에 알려주는 것은 알려주지 않은 것과 같다).
async function saveMapSpecOnly() {
  const table = selectedTable;
  if (!table) {
    showToast('맵 테이블을 먼저 고르십시오.', 'error');
    return;
  }
  // `getCurrentMapKey`는 맵 키 칸이 비었거나 'default_map'이면 null을 준다. ⚡ Push는 그
  // 자리에서 'default_map'으로 물러서지만, 규격 등록은 **자리 표시자 정체성에 행을 만드는
  // 일**이라 물러서지 않는다 — 여기서 만든 행은 영구히 진짜 등록처럼 보인다.
  const mapKey = getCurrentMapKey();
  if (!mapKey) {
    showToast('맵 키 칸을 채워야 규격을 저장할 수 있습니다 — 어느 맵의 규격으로 등록할지 '
      + '알 수 없습니다.', 'error');
    return;
  }

  // 읽기가 먼저다. 신규/갱신 판정도, 병합의 재료도 이 한 번의 조회에서 나온다.
  let stored;
  try {
    stored = await fetchGridMetaFor(table, mapKey);
  } catch (e) {
    showToast(`맵 규격을 확인하지 못해 저장을 중단했습니다 — ${(e && e.message) ? e.message : e}. `
      + `잠시 후 다시 시도하십시오(아무것도 기록되지 않았습니다).`, 'error');
    return;
  }
  const isNew = (stored === null);

  // 🔴 빈 칸은 0이 아니다(§`gridFrameControlNum`) — ⚡ Push와 **같은** 술어로 묻는다. 이 저장은
  //    셀을 지우지 않지만 격자·원점을 등록하므로, 지어낸 0은 DB에 그대로 있는 셀에서 주소를
  //    빼앗는다(아래 `offGrid`가 세는 바로 그 계급을 스스로 만드는 셈이다).
  const panel = readGridFrameControls(el);
  if (panel.silent.length > 0) {
    showToast(`${panel.silent.join(' · ')} 칸이 비어 있어 규격을 저장하지 않았습니다 — `
      + `빈 칸을 0으로 지어내 등록하지 않습니다.`, 'error');
    return;
  }
  const { cols, rows, startX, startY, invertY } = panel;
  const pushMeta = buildPushGridMetadata(cols, rows, startX, startY, invertY,
    el, currentRotation, currentSide, validDie);
  const next = mergeStoredGridMeta(stored, pushMeta.gridMetaOut);

  // ── 격자 밖으로 밀려나는 셀 ──────────────────────────────────────────────────────────
  // 이 저장은 셀을 지우지 않는다. 그런데도 세는 이유: 격자·시작 좌표가 좁아지면 **DB에
  // 그대로 있는 셀이 이 맵으로는 더 이상 주소를 갖지 못한다.** 셀 데이터는 한 바이트도
  // 바뀌지 않고 프레임이 밑에서 빠져나가는, 941060f가 닫은 그 계급이다.
  // 판정은 새로 만들지 않는다 — `classifyUnsavableCells().offGrid`가 이미 "그 키에
  // cellObj 자체가 없다 = 현재 프레임이 덮지 못한다"의 유일한 정의다.
  // 🔴 셀 수를 말할 수 있는 것은 **화면의 셀이 이 정체성에서 온 경우뿐**이다. 키를 바꿔
  //    다른 정체성으로 등록하는 중이라면 화면의 셀은 그 맵의 셀이 아니므로, 0을 보여
  //    주면 "밀려나는 셀이 없다"는 거짓말이 된다. 셀 수 대신 셀 수 없음을 말한다.
  const sameIdentity = !!(loadedIdentity && loadedIdentity.table === table
    && loadedIdentity.mapKey === mapKey);
  const offGrid = sameIdentity ? classifyUnsavableCells().offGrid.length : null;
  let orphanLine;
  if (!sameIdentity) {
    orphanLine = `· 이 식별자로 불러온 셀이 화면에 없어, 격자 밖으로 밀려나는 셀 수는 `
      + `셀 수 없습니다.\n`;
  } else if (offGrid > 0) {
    orphanLine = `\n⚠️ 이 규격으로는 값이 있는 셀 ${offGrid}건이 격자 범위 밖에 놓입니다.\n`
      + `   그 셀들은 서버에서 삭제되지 않지만, 이 맵으로는 더 이상 불러올 수 없게 됩니다.\n`
      + `   (격자 크기·시작 좌표를 되돌려 다시 저장하면 그대로 되살아납니다.)\n\n`;
  } else {
    orphanLine = `· 격자 밖으로 밀려나는 셀: 없음\n`;
  }

  const shownNext = validDieRefDisplay(next.valid_die_ref);
  const vdLine = ('valid_die_ref' in next)
    ? `「${shownNext.table || VALID_DIE_TABLE} · ${shownNext.key}」`
    : '지정 없음 (웨이퍼 원 기하)';
  if (!confirm(
    `맵 규격만 기록합니다 — 셀은 하나도 쓰지 않습니다.\n\n`
    + `· 대상 테이블: ${table}\n`
    + `· 대상 맵 키: ${mapKey}\n`
    + `· ${isNew
      ? '이 식별자에는 등록된 규격이 없습니다 — 규격을 **새로 등록**합니다.'
      : '등록된 규격을 **갱신**합니다.'}\n`
    + orphanLine
    + `\n· 격자 ${cols} × ${rows} · 시작 (${startX}, ${startY}) · 회전 ${currentRotation}° · ${currentSide}\n`
    + `· 유효 다이 맵: ${vdLine}\n\n`
    + `계속하시겠습니까?`
  )) {
    return;
  }

  const payload = {
    updates: [{
      business_key_val: `${table}_${mapKey}`,
      updates: {
        map_pk: `${table}_${mapKey}`,
        target_table: table,
        map_id: mapKey,
        grid_metadata: JSON.stringify(next),
      },
      source_name: 'user',
      updated_by: CURRENT_USER,
    }]
  };
  // [V1 effort instrument] `effort`를 싣지 않는다 — ⚡ Push의 셀 요청 하나가 유일한 보고
  // 지점이고, 같은 배치 엔드포인트에 또 실으면 같은 클릭이 두 번 청구된다.
  const btn = el.btnSaveMapSpec;
  const label = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '📐 Saving...'; }
  // ── 응답이 오지 않는 경우 ────────────────────────────────────────────────────────────
  // 🔴 **버튼 복구는 `finally`에 있다. 그러니 버튼이 멈춰 있다는 것은 `finally`에 닿지
  //    못했다는 뜻이고, 그 길은 하나뿐이다 — `await fetch(...)`가 영원히 끝나지 않는 것.**
  //    2026-08-04 실사용 신고가 정확히 이것이었다: 버튼은 "Saving..."에 멈춰 있는데
  //    **저장은 성공해 있었다.** 연결을 삼키는 경로(응답을 완료하지도 거절하지도 않는
  //    프록시, 드롭하는 방화벽, 반열림 NAT)에서 나는 고장이고, 같은 환경이 WebSocket을
  //    CONNECTING에 붙잡아 두는 그 고장이다(`WS_CONNECT_TIMEOUT_MS` 참조).
  //    `AbortController` 유무를 먼저 보는 것은 `value_suggest.js`의 선례를 따른 것이다.
  const abort = (typeof AbortController === 'function') ? new AbortController() : null;
  let timedOut = false;
  const timeoutTimer = abort
    ? setTimeout(() => { timedOut = true; abort.abort(); }, MAP_SPEC_SAVE_TIMEOUT_MS)
    : null;
  try {
    const res = await fetch(`${API_BASE}/tables/wafer_map_metadata/data/updates`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      ...(abort ? { signal: abort.signal } : {}),
    });
    if (!res.ok) {
      showToast(`맵 규격 저장 실패 (HTTP ${res.status}) — 아무것도 기록되지 않았습니다.`, 'error');
      return;
    }
    // 저장이 성립했으므로 **저장된 원문**이 바뀌었다. `validDie.raw`를 그 값으로 맞춘다:
    // 맞추지 않으면 곧이어 누른 ⚡ Push가 같은 변경을 「사용자 편집」으로 한 번 더 쓴다.
    // basis·keys·마스크는 건드리지 않는다 — 저장은 적용이 아니다(그래서 칩도 그대로다).
    validDie = { ...validDie, raw: ('valid_die_ref' in next) ? next.valid_die_ref : undefined };
    // [fix E-2] ...and for the same reason, the back-guard's baseline moves too. Without this
    // the reworded prompt lies: it tells the user 📐 규격만 저장 is enough, and then asks
    // again after they did exactly that. Only the SPEC is saved here, so the flag is dropped
    // only when nothing else is outstanding — `legendDirty` is the existing record of cell
    // and legend draft work, which this write does not carry. (Before this change the two
    // flags were set in the same breath everywhere, so this condition can never fire for a
    // pre-existing path: it is reachable only from a declaration-only edit.)
    if (!legendDirty) frameTouched = false;
    syncValidDieRefControls();
    showToast(`${table} · ${mapKey} 맵 규격 ${isNew ? '새로 등록' : '갱신'} — 셀 기록 0건`, 'success');
  } catch (e) {
    // 🔴 **「실패했다」와 「됐는지 모르겠다」는 다른 사실이고, 다르게 읽혀야 한다.**
    //    종전 문구는 어떤 예외에서든 "아무것도 기록되지 않았습니다"라고 단언했다. 응답을
    //    잃은 쓰기에 대해 그것은 **위험한 방향으로** 틀린다 — 이번 신고에서 쓰기는 실제로
    //    성공해 있었다. "기록되지 않았다"고 들은 사용자는 다시 시도하거나, 더 나쁘게는
    //    편집이 사라진 줄 알고 낡은 화면에서 처음부터 다시 만든다.
    //    브라우저에서 실제로 구분되는 것은 **「서버가 답을 줬다」(위 `!res.ok`)와 「답을
    //    받지 못했다」(여기)** 까지다. 네트워크 오류는 전송 전 거절일 수도 전송 후 응답
    //    유실일 수도 있고 JS는 그 둘을 구분하지 못한다 — 그래서 시간 초과든 네트워크
    //    오류든 "확인이 필요합니다"로 말한다. 편한 문구가 아니라 **구분할 수 있는 것**에서
    //    문구를 가져온다.
    //    두 갈래를 나누는 것은 원인이 다르기 때문이다. 시간 초과는 몇 초를 기다렸는지가
    //    사용자에게 의미 있는 사실이고, 그 자리에 예외 메시지("The user aborted a request")를
    //    보여 주는 것은 아무 말도 안 하는 것과 같다.
    if (timedOut) {
      showToast(`맵 규격 저장 — ${Math.round(MAP_SPEC_SAVE_TIMEOUT_MS / 1000)}초 안에 응답이 `
        + `오지 않았습니다. 저장됐는지 확인이 필요합니다 — 화면을 새로 고쳐 규격을 확인한 뒤 `
        + `다시 시도하십시오.`, 'error');
    } else {
      showToast(`맵 규격 저장 — 응답을 받지 못했습니다 (${(e && e.message) ? e.message : e}). `
        + `저장됐는지 확인이 필요합니다 — 화면을 새로 고쳐 규격을 확인하십시오.`, 'error');
    }
  } finally {
    // 타이머는 성공 경로에서도 반드시 꺼진다. 살아남은 타이머는 이 저장이 끝난 뒤에
    // `abort()`를 부르는데, 그 컨트롤러는 이미 아무 요청도 붙들고 있지 않다 — 지금은
    // 무해하지만, 컨트롤러를 재사용하는 다음 편집에서는 남의 요청을 끊는다.
    if (timeoutTimer !== null) clearTimeout(timeoutTimer);
    if (btn) { btn.disabled = false; btn.textContent = label; }
  }
}

// ══ [키 자동완성] 입력칸이 이미 가진 값을 datalist로 내려 준다 ═══════════════════════
//
// 새 패널·모드·모달·토글은 **0개**다. 세 자리 모두 이미 있는 입력칸의 `list=` 하나뿐이고,
// datalist는 제안만 할 뿐 입력을 제약하지 않는다 — 목록에 없는 키를 타이핑해 여는 경로는
// 오늘과 문자 하나까지 동일하다. 이 층은 편의이지 검증기가 아니다.
//
// ── 모집단이 둘이다. 그 둘은 같은 질문이 아니라서 조회도 둘이다 ────────────────────
//  ① 맵 키(오버레이 · 유효 다이 지정) = `wafer_map_metadata`에 **규격이 등록된** 맵의 map_id.
//     메타 없는 키를 제안하면 안 되는 이유가 두 자리에서 **서로 다르다**:
//       · 유효 다이 지정 — 메타가 없으면 **거절된다**(`:7925`, "참조 맵의 규격이 없습니다").
//         반드시 실패할 키를 제안하는 목록은 목록이 없는 것보다 나쁘다.
//       · 오버레이 — 거절되지 **않는다.** 규격이 없으면 `무보정`으로 그려지고 칩이
//         "소스 맵 규격 미등록 — 현재 화면 규격으로 해석"이라고 적는다(`:8767`,`:8815`).
//         이쪽이 더 나쁘다: 실패가 아니라 **틀린 정렬을 그려 놓고 그린다**. 제안 목록이
//         조용한 오정렬로 가는 지름길이 돼선 안 된다.
//     ⚠️ 종전 주석은 이 둘을 합쳐 오버레이도 "반드시 실패한다"고 적었다 — 오버레이는
//        실패하지 않는다. 결론(메타 모집단을 쓴다)은 같지만 근거가 달라서 남긴다.
//  ② 메인 로드의 메타 입력칸 = 대상 테이블 **그 컬럼에 저장된 값**(F3 값 제안 엔드포인트,
//     `server/value_suggest.py`). 메인 로드는 셀을 컬럼 필터로 여는 것이지 메타 등록을
//     요구하지 않는다 — 여기서 ①을 쓰면 열 수 있는 맵을 목록에서 빼먹는다.
//  두 모집단을 하나로 합치면 어느 쪽이든 **없는 것을 있다고 하거나 있는 것을 없다고** 한다.
//
// ── 세 가지 상태를 구분한다. 빈 목록 하나로 뭉개지 않는다 ──────────────────────────
//  complete    → 이 목록이 전부다. 이후 좁히기는 브라우저가 하므로 추가 요청이 0회다.
//  truncated   → 서버가 자른 목록이다. 자른 목록을 브라우저가 좁히면 "이게 전부"라고
//                거짓말하게 되므로, 입력할 때마다 접두사로 **서버에 다시 묻는다**.
//  unavailable → 서버가 **보지 못했다**(인덱스 부재·INVALID·타임아웃, 또는 HTTP 실패).
//                값을 만들지 않고, 캐시하지 않고(다음 포커스에서 재시도), 사유를 남긴다.
//                이 셋을 "제안 없음"으로 합치면 운영자는 **데이터가 비었다**고 읽는다.
// 상태는 입력칸 자신의 `title`과 `data-suggest`에 남긴다 — 새 UI를 만들지 않기 위해서다.
// 읽기 동선이므로 토스트도 확인창도 없다.
//
// ── [2026-08-04] 목록이 **있는데도** 그리드로 나가서 키를 복사해 오는 이유 ─────────────
// 사용자 보고: "드롭박스가 있으나 여전히 MAP KEY를 찾기가 힘들다." 검색(retrieval)은
// 이미 되고 있었고 남은 문제는 **식별(recognition)**이었다. 실측 두 가지가 그 이유다:
//  ⓐ 목록에 **순서가 없다.** 서버 행 순서 그대로 내려보내고 있었고, 그건 정렬이 아니다 —
//     `eds_fail_map` 80키 중 인접 역전 36 / `core_defect_map` 80키 중 35 / `bonding_map`
//     32키 중 13. 훑을 수 없는 목록은 목록이 아니다. → `compareMapKeys`(숫자 인식 정렬).
//  ⓑ 후보가 **맨 키 문자열뿐**이라 어느 것이 내가 찾는 맵인지 말해 주지 않는다. 반면 그
//     맵의 등록 규격은 이미 손에 있다 — `wafer_map_metadata` 행을 통째로 받아 `map_id`만
//     빼고 버리고 있었다. → `mapSpecSummary`가 그 행의 `grid_metadata`를 한 줄로 접어
//     option의 `label`에 붙인다. **후보당 추가 요청 0회.**
//     식별력 실측(2026-08-04): `bonding_map` 32키/서로 다른 규격 25 · `bonding_log`
//     120키/21 · `dt_map` 146키/12. 규격이 갈리는 자리가 곧 **잘못 고르면 조용히 어긋나는**
//     자리라, 라벨이 가장 필요한 곳과 가장 잘 듣는 곳이 같다.
//
// ── 썸네일(사용자 제안)을 그림으로 만들지 않은 이유 ─────────────────────────────────
//  1. 네이티브 `<datalist>`의 팝업은 **브라우저가 그린다.** option에 hover 훅도, DOM도,
//     CSS도 걸 수 없다 — 그림을 걸 자리가 물리적으로 없다. 그림을 넣으려면 datalist를
//     **자체 드롭다운으로 교체**해야 하고, 그건 새 기제·새 영역이며 "이미 있는 입력칸의
//     `list=` 하나"라는 이 층의 전제를 통째로 버리는 일이다.
//  2. 그림은 **셀**을 요구한다. 후보는 `core_wafer_map`에서 200개고 맵 하나가 40×40이다.
//     팝업 한 번에 후보당 1요청이 붙는 설계는 어떤 형태로도 허용되지 않는다.
//  3. 그림이 말해 줬을 것 — 격자 크기·회전·앞뒷면 — 은 `grid_metadata`에 **이미 있다.**
//     라벨이 그걸 0요청으로 말한다. 그림은 그 위에 비용만 얹는다.
//  4. 그림도 못 푸는 것: 같은 로트의 두 슬롯은 규격이 같고 셀 값만 다르다. 팝업 크기의
//     그림으로는 구별되지 않는다. 그 경우의 진짜 판별자는 **로트 접두사**이고, 정렬된
//     목록 + 브라우저 좁히기가 이미 그것을 한다.

const KEY_SUGGEST_DEBOUNCE_MS = 120;
// 메타 입력칸 자동완성이 한 번에 받아 오는 값 개수. 서버 기본(default_limit)과 같은 50 —
// 이 목록은 브라우저가 좁히므로 상한이 곧 후보 집합이고, 잘리면 위 truncated 규칙이 받는다.
const COLUMN_VALUE_LIST_LIMIT = 50;

// 입력칸의 원래 title을 보존한 채 자동완성 상태만 덧붙인다. title을 통째로 덮으면
// 원래 설명(무엇을 넣는 칸인지)이 사라진다 — 편의를 얹다가 설명을 지우지 않는다.
function markSuggestState(input, state, note) {
  if (!input || !input.dataset) return;
  if (input.dataset.suggestTitleBase === undefined) {
    input.dataset.suggestTitleBase = input.title || '';
  }
  const base = input.dataset.suggestTitleBase;
  if (state) input.dataset.suggest = state;
  else delete input.dataset.suggest;
  input.title = note ? (base ? `${base}\n${note}` : note) : base;
}

// 늦게 도착한 답이 **더 새로운 답을 덮지 못하게** 한다. 목록마다 세대를 세고, 자기 세대가
// 아직 최신일 때만 쓴다 — 오버레이 소스 테이블을 빠르게 두 번 바꾸면 느린 첫 응답이 나중에
// 착지해 두 번째 테이블의 목록을 **첫 테이블 것으로** 되돌린다. 그 목록은 낡아 보이지 않는다.
// (`value_suggest.js`가 셀 에디터에서 같은 이유로 시퀀스를 쓴다: abort는 이미 큐에 들어간
//  마이크로태스크에 대해 동기적이지 않으므로 "누가 마지막으로 물었는가"만이 확실하다.)
const listFillSeq = new WeakMap();
function claimListFill(listEl) {
  const n = (listFillSeq.get(listEl) || 0) + 1;
  listFillSeq.set(listEl, n);
  return () => listFillSeq.get(listEl) === n;
}

// An item is a plain string, or `{ value, label }`. The `label` is ANNOTATION, never data:
// the browser still puts `value` — and only `value` — into the field when the operator picks
// a row, so annotating a candidate cannot change one byte of what gets typed or loaded.
// A missing/blank label emits NO attribute at all rather than an empty one: `label=""` makes
// some engines render an empty second column, i.e. it would SAY something about a map whose
// spec we do not have.
function fillDatalist(listEl, values) {
  if (!listEl) return;
  listEl.innerHTML = '';
  values.forEach(v => {
    const o = document.createElement('option');
    if (v && typeof v === 'object') {
      o.value = v.value;
      if (v.label) o.label = v.label;
    } else {
      o.value = v;
    }
    listEl.appendChild(o);
  });
}

// ── ① 맵 키 모집단 ──────────────────────────────────────────────────────────────
// **완전한 목록만** 캐시한다. 잘린 목록을 캐시하면 그 뒤로 영영 잘린 목록을 "전부"로 내민다.
const mapKeyListCache = new Map();

// 맵 키는 사람이 읽는 식별자라 **숫자를 숫자로** 비교해야 한다. 순수 사전순은 `_10`을 `_2`
// 앞에 놓는데, 슬롯이 1~25인 로트에서는 그것만으로 목록이 못 읽을 물건이 된다.
// (실측 2026-08-04: 서버가 주는 순서는 정렬이 아니다 — `eds_fail_map` 80키에 인접 역전 36,
//  `core_defect_map` 80키에 35, `bonding_map` 32키에 13. 후보를 눈으로 훑을 수 없으면
//  운영자는 그리드로 나가 키를 복사해 온다. 그 왕복이 이 정렬이 없애려는 것이다.)
function compareMapKeys(a, b) {
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

// 후보 하나가 **어떤 모양의 맵인가**를 한 줄로 요약한다. 셀을 한 칸도 읽지 않는다 —
// 재료는 이미 받아 온 `wafer_map_metadata` 행의 `grid_metadata`뿐이고, 지금까지는 `map_id`만
// 빼고 전부 버리고 있었다. 그래서 후보당 추가 요청이 **0회**다(썸네일 판단의 근거).
// 규격을 읽지 못하면 **아무 말도 하지 않는다** — 「모른다」를 「이렇다」로 바꾸지 않는다.
function mapSpecSummary(rawGridMeta) {
  if (!rawGridMeta) return '';
  let m;
  try {
    m = (typeof rawGridMeta === 'string') ? JSON.parse(rawGridMeta) : rawGridMeta;
  } catch (e) {
    return '';
  }
  if (!m || typeof m !== 'object') return '';
  const cols = Number(m.grid_cols), rows = Number(m.grid_rows);
  if (!Number.isFinite(cols) || !Number.isFinite(rows) || cols <= 0 || rows <= 0) return '';
  const parts = [`${cols}×${rows}`];
  const rot = Number(m.rotation);
  if (Number.isFinite(rot) && rot !== 0) parts.push(`회전 ${rot}°`);
  if (String(m.side || '').toLowerCase() === 'back') parts.push('뒷면');
  if (m.grid_y_invert === true) parts.push('Y반전');
  return parts.join(' · ');
}

async function populateMapKeyDatalist(table, listEl, input) {
  if (!listEl || !table) return;
  const isCurrent = claimListFill(listEl);
  const cached = mapKeyListCache.get(table);
  if (cached) { markSuggestState(input, '', ''); fillDatalist(listEl, cached); return; }
  let items, total, rowCount;
  try {
    const filters = { target_table: { filterType: 'text', type: 'equals', filter: String(table) } };
    const res = await fetch(`${API_BASE}/tables/wafer_map_metadata/data`
      + `?limit=${VALID_DIE_LIST_LIMIT}&filters=${encodeURIComponent(JSON.stringify(filters))}`);
    if (!res.ok) {
      if (!isCurrent()) return;   // 낡은 실패가 새 질문의 상태를 덮지 못한다
      // 서버가 답을 주지 못했다. 빈 목록으로 남기면 "이 테이블에는 등록된 맵이 없다"로 읽힌다.
      markSuggestState(input, 'unavailable',
        `맵 키 목록을 읽지 못했습니다 (HTTP ${res.status}) — 키는 직접 입력할 수 있습니다.`);
      return;
    }
    const result = await res.json();
    if (!isCurrent()) return;   // 이 목록에 대한 더 새로운 질문이 이미 있다
    const rows = (result && Array.isArray(result.data)) ? result.data : [];
    rowCount = rows.length;
    total = Number(result && result.total);
    // 값(=키)과 라벨(=그 맵의 등록 규격)을 **같은 행에서** 만든다. 라벨을 위해 추가 조회를
    // 하지 않는다는 성질이 여기서 성립한다.
    items = rows.map(r => {
      const d = r && r.data;
      const id = (d && d.map_id) ? d.map_id.value : null;
      if (id === null || id === undefined || String(id).trim() === '') return null;
      const meta = (d && d.grid_metadata) ? d.grid_metadata.value : null;
      return { value: String(id), label: mapSpecSummary(meta) };
    }).filter(Boolean).sort((a, b) => compareMapKeys(a.value, b.value));
  } catch (e) {
    if (!isCurrent()) return;   // 낡은 실패가 새 질문의 상태를 덮지 못한다
    markSuggestState(input, 'unavailable',
      `맵 키 목록 조회 실패 — ${(e && e.message) ? e.message : e}`);
    return;
  }
  if (Number.isFinite(total) && total > rowCount) {
    // 절단은 성공이 아니다(INV-④와 같은 규율): 목록이 모집단인 척하지 못하게 사실을 남긴다.
    markSuggestState(input, 'truncated',
      `등록된 맵 ${total}개 중 ${items.length}개만 목록에 있습니다 — 없는 키도 직접 입력할 수 있습니다.`);
  } else if (items.length === 0) {
    // [1-a] **성공했는데 0건**이다. 종전에는 이 자리가 `markSuggestState(input, '', '')` —
    // 즉 침묵이었고, 침묵은 「목록이 고장났다」와 구별되지 않는다. 상태는 여전히 완전
    // (`complete`)이므로 캐시도 하고 select도 쓸 수 있지만, **말은 한다**.
    markSuggestState(input, '',
      `${table}에 등록된 맵이 아직 없습니다 — 조회는 성공했고 정말로 0건입니다.`);
    mapKeyListCache.set(table, items);
  } else {
    markSuggestState(input, '', '');
    mapKeyListCache.set(table, items);
  }
  fillDatalist(listEl, items);
}

// 유효 다이 지정 칸 — 같은 자리, 같은 함수. [1-a] 모집단만 **한 테이블로 고정**됐다:
// 종전에는 테이블 select(비면 캔버스 테이블)를 읽었고, 이제는 언제나 `VALID_DIE_TABLE`이다.
// 두 번째 조회 기제를 만들지 않는다 — `populateMapKeyDatalist`가 그대로 `complete` /
// `truncated` / `unavailable` 세 상태를 구분해 준다. 특히 조회 실패를 빈 목록으로 뭉개지
// 않는다: 「못 봤다」가 「없다」로 읽히면 운영자는 있는 맵을 없다고 판단한다.
async function populateValidDieRefList() {
  await populateMapKeyDatalist(VALID_DIE_TABLE, el.validDieRefList, el.validDieRefKey);
  // [1-a] 모집단이 확정된 **직후에** 컨트롤 형태를 다시 정한다. 목록과 상태가 둘 다
  //       갖춰진 가장 이른 지점이고, 여기서 하지 않으면 드롭다운은 영영 빈 채로 남는다.
  renderValidDieKeyControl();
}

// 오버레이 소스 키 칸 — 모집단이 같으므로 **같은 함수**다. 오버레이 전용 조회를 새로 쓰지 않는다.
async function populateOverlayKeyList() {
  const table = el.overlaySrcTable ? el.overlaySrcTable.value : '';
  return populateMapKeyDatalist(table, el.overlaySrcKeyList, el.overlaySrcKey);
}

// ── ② 컬럼 값 모집단 (메인 로드의 메타 입력칸) ───────────────────────────────────
// 캐시는 **완전한 답**만 담는다: `{prefix, values}`. 서버의 긴 접두사 답은 짧은 접두사 답의
// 부분집합이므로, 캐시된 접두사를 연장하는 입력은 브라우저의 datalist 좁히기로 정확히 답이
// 된다(요청 0회). 잘린 답은 부분집합 성질이 성립하지 않아 절대 담지 않는다.
const columnValueComplete = new Map();  // 'table::column' -> { prefix, values }
const columnValueRefused = new Map();   // 4xx: 제안 대상이 아닌 컬럼 (평범한 입력칸으로 남는다)
const columnValueTruncated = new Set(); // 잘린 컬럼 — 입력할 때마다 접두사로 다시 묻는다

function colValueKey(table, column) { return `${table}::${column}`; }

// 테이블 전환 시 그 테이블의 학습·캐시를 버린다. 남겨 두면 전환 중에 추가된 값이 영영
// 제안되지 않고, 무엇보다 **낡은 목록은 낡아 보이지 않는다**.
function dropColumnValueCache(table) {
  const prefix = `${table}::`;
  Array.from(columnValueComplete.keys()).forEach(k => {
    if (k.startsWith(prefix)) columnValueComplete.delete(k);
  });
  Array.from(columnValueRefused.keys()).forEach(k => {
    if (k.startsWith(prefix)) columnValueRefused.delete(k);
  });
  Array.from(columnValueTruncated).forEach(k => {
    if (k.startsWith(prefix)) columnValueTruncated.delete(k);
  });
}

// 캐시된 완전한 답을 이 접두사에 그대로 쓸 수 있는가. 클라가 목록을 **거르지는 않는다** —
// 거르기는 브라우저 datalist가 하고, 여기서는 "그 목록이 여전히 상위집합인가"만 묻는다.
function canReuseComplete(cachedPrefix, prefix) {
  return prefix.length >= cachedPrefix.length
    && prefix.toLowerCase().startsWith(cachedPrefix.toLowerCase());
}

async function populateColumnValueDatalist(table, column, listEl, input, prefix) {
  if (!listEl || !table || !column) return;
  const isCurrent = claimListFill(listEl);
  const key = colValueKey(table, column);
  // 제안 대상이 아닌 컬럼(미선언·datetime·물리 부재)은 **오늘과 똑같은** 평범한 입력칸이다.
  if (columnValueRefused.get(key)) return;
  const pfx = String(prefix == null ? '' : prefix);
  const snap = columnValueComplete.get(key);
  if (snap && canReuseComplete(snap.prefix, pfx)) {
    markSuggestState(input, '', '');
    fillDatalist(listEl, snap.values);
    return;
  }
  let body;
  try {
    const res = await fetch(`${API_BASE}/tables/${encodeURIComponent(table)}`
      + `/columns/${encodeURIComponent(column)}/values`
      + `?prefix=${encodeURIComponent(pfx)}&limit=${COLUMN_VALUE_LIST_LIMIT}`);
    if (res.status === 400 || res.status === 404) {
      // "제안 대상이 아니다"는 실패가 아니라 **선언**이다. 조용히 평범한 입력칸으로 남긴다.
      columnValueRefused.set(key, true);
      markSuggestState(input, '', '');
      return;
    }
    if (!res.ok) {
      if (!isCurrent()) return;   // 낡은 실패가 새 질문의 상태를 덮지 못한다
      markSuggestState(input, 'unavailable',
        `값 목록을 읽지 못했습니다 (HTTP ${res.status}) — 값은 직접 입력할 수 있습니다.`);
      return;
    }
    body = await res.json();
  } catch (e) {
    if (!isCurrent()) return;   // 낡은 실패가 새 질문의 상태를 덮지 못한다
    markSuggestState(input, 'unavailable',
      `값 목록 조회 실패 — ${(e && e.message) ? e.message : e}`);
    return;
  }
  if (!isCurrent()) return;   // 이 목록에 대한 더 새로운 질문이 이미 있다
  // 서버가 **답을 못 낸** 경우. `values: []`와 생김새가 같아서, 여기서 합치면 운영자는
  // "이 컬럼에 값이 없다"로 읽는다 — 서버는 값이 없다고 말한 적이 없다.
  // 캐시하지 않는다: 인덱스는 나중에 만들어질 수 있고 다음 포커스가 그것을 알아내야 한다.
  if (body && body.unavailable_reason) {
    columnValueTruncated.delete(key);
    columnValueComplete.delete(key);
    fillDatalist(listEl, []);
    markSuggestState(input, 'unavailable',
      `값 제안을 사용할 수 없습니다 — ${body.unavailable_reason}`);
    console.debug('[map] value suggest unavailable:', table, column, body.unavailable_reason);
    return;
  }
  const values = Array.isArray(body && body.values) ? body.values.map(v => String(v)) : [];
  if (body && body.truncated) {
    columnValueTruncated.add(key);
    columnValueComplete.delete(key);
    markSuggestState(input, 'truncated',
      `값이 많아 앞의 ${values.length}개만 내려왔습니다 — 더 입력하면 다시 좁혀 가져옵니다.`);
  } else {
    columnValueTruncated.delete(key);
    columnValueComplete.set(key, { prefix: pfx, values });
    markSuggestState(input, '', '');
  }
  fillDatalist(listEl, values);
}

// 메타 입력칸의 위임 핸들러. 입력칸이 재생성돼도 이 함수는 컨테이너에 그대로 붙어 있으므로
// 리스너가 쌓이지 않는다(노드당 배선 0개).
function onMetaInputSuggest(e) {
  const input = e && e.target;
  if (!input || !input.id || input.id.indexOf('meta-input-') !== 0) return;
  const column = input.id.slice('meta-input-'.length);
  const listEl = document.getElementById(`meta-list-${column}`);
  if (!listEl) return;
  // 완전한 목록을 이미 받은 컬럼은 타이핑에 요청을 만들지 않는다 — 좁히기는 브라우저 몫이다.
  if (e.type === 'input' && !columnValueTruncated.has(colValueKey(selectedTable, column))) return;
  populateColumnValueDatalist(selectedTable, column, listEl, input, input.value || '');
}

// ── [M4 phase 2] 템플릿 생성 = 저작 캔버스를 열고 프리셋 모양을 칠한다 ──────────────
// 진입점은 **기존 규격 프리셋 드롭다운**이다(새 컨트롤 0개). 선택 하나가 곧 실행이다.
function enterValidDieAuthoring(shape) {
  // [INV-6를 저작 쪽에서도] 참조를 가진 맵을 템플릿으로 만들면 그 템플릿을 가리키는 순간
  // 2단계 체인이 된다. 만들 수 있게 해 두고 나중에 거절하는 것보다, 만들 수 없게 하는 편이
  // 사용자에게 정직하다.
  // [F3] 모듈 상태 **와** 입력칸을 둘 다 본다. `validDie.raw`만 보면, blur의 `change`가
  //      시작한 재해석이 첫 await에서 양보한 사이에 이 가드가 **낡은 상태**를 읽고 통과한다 —
  //      그 뒤 해석이 착지하면 저작 중인 템플릿 맵에 참조가 남아 2단계 체인이 된다.
  //      (컨트롤은 아직 해석되지 않은 사용자의 지정이므로 상태보다 새롭다.)
  const pendingRefKey = (el.validDieRefKey && el.validDieRefKey.value ? el.validDieRefKey.value : '').trim();
  if (pendingRefKey !== '' || (validDie && validDie.raw !== undefined && validDie.raw !== null)) {
    showToast('「유효 다이 맵」 칸을 비우십시오 — 참조 체인은 1단계까지입니다.', 'error');
    return;
  }
  const tpl = buildValidDieTemplate(shape);
  if (tpl.keys.size === 0) {
    showToast('격자 규격 미확인 — 물리 규격을 먼저 적용하십시오.', 'error');
    return;
  }
  const painted = Object.keys(gridData).filter(k => (gridData[k] || '') !== '').length;

  if (shape === 'open') {
    // 저장된 템플릿을 **다시 열어 편집**하는 경로. 칠하지 않는다 — 지운 셀이 되살아나면
    // 편집이 아니라 초기화다.
    validDieResolveSeq++;   // [F3] 진행 중인 해석은 이제 낡았다 — 착지해도 이 상태를 못 덮는다
    validDie = { basis: 'template', keys: tpl.keys, reason: '', ref: null, raw: undefined };
    renderValidDieChip();
    renderGridCanvas();
    showToast(`유효 다이 저작 시작 — 격자 전체 ${tpl.keys.size}칸이 후보 (칠한 ${painted}칸 유지)`, 'success');
    return;
  }

  if (!activeBrush) {
    // fillGrid와 **같은 전제, 같은 문구** — 칠하는 연산의 규칙은 하나다.
    alert('페인팅 브러쉬를 먼저 고르십시오.');
    return;
  }
  // 쓰기(화면 파괴) 1회 확인 — 지울 것이 있을 때만 묻는다. 빈 격자에서는 무마찰이다.
  if (painted > 0 && !confirm(
    `유효 다이 템플릿(${shape === 'circle' ? '원 기하' : '격자 전체'})을 생성하면 `
    + `현재 칠해진 셀 ${painted}개가 '${activeBrush}'(으)로 덮어써집니다.\n\n`
    + `이미 만들어 둔 템플릿을 편집하려면 「채우지 않고 격자 전체 열기」를 사용하십시오.\n\n계속하시겠습니까?`
  )) {
    return;
  }

  validDieResolveSeq++;   // [F3] 위와 같다 — 상태를 갈아치우는 쪽이 세대를 올린다
  validDie = { basis: 'template', keys: tpl.keys, reason: '', ref: null, raw: undefined };
  // 🔴 `gridData = {}`로 밀지 않는다. 보호 셀(페인트 잠금)은 아래 채움 루프가 건너뛰므로,
  //    통째로 비우면 그 셀들은 **값을 잃은 채 다시 칠할 수도 없는 상태**가 된다.
  //    잠금은 저작보다 우선한다 — `fillGrid`가 지키는 규칙과 같다.
  const nextData = {};
  Object.keys(gridData).forEach(k => { if (isProtectedFCell(k)) nextData[k] = gridData[k]; });
  tpl.filled.forEach(k => { if (!isProtectedFCell(k)) nextData[k] = activeBrush; });
  gridData = nextData;

  renderValidDieChip();
  updateLegendCounts();
  renderGridCanvas();
  scheduleCellDraft();
  showToast(`유효 다이 템플릿 — ${tpl.filled.length}칸 칠함`
    + `${tpl.outsideCircle > 0 ? ` (원 밖 ${tpl.outsideCircle}칸 포함)` : ''} — 우클릭으로 깎은 뒤 [⚡ Push]`, 'success');
}

// 실패한 오버레이도 목록에 **행으로 남긴다**. 토스트만 띄우고 끝내면
// "왜 안 겹쳤는지"가 화면에서 증발하고, 사용자는 데이터가 없는 것으로 오해한다.
function pushFailedOverlay(sourceTable, sourceKey, status, reason, targetOverride) {
  const dup = overlayLayers.find(o => o.failed && o.sourceTable === sourceTable && o.sourceKey === sourceKey);
  if (dup) { dup.status = status; dup.reason = reason; renderOverlayList(); return dup; }
  const layer = {
    id: overlaySeq++,
    sourceTable: String(sourceTable), sourceKey: String(sourceKey),
    rawCells: [], cells: new Map(), count: 0, frame: null,
    color: 'var(--danger)', visible: false,
    failed: true, status: String(status || 'error'), reason: String(reason || ''),
    align: null, alignApplied: false, alignText: '', truncated: false, cap: null,
    targetOverride: targetOverride || null,
  };
  overlayLayers.push(layer);
  recomputeActiveOverlays();
  renderOverlayList();
  return layer;
}

// ── 소스 맵 읽기 (메인 로드와 같은 REST 경로) ──────────────────────
// 메인 로드는 `/tables/{t}/data` + `wafer_map_metadata`를 (target_table, map_id) 쌍으로 읽는다.
// 오버레이도 정확히 그 두 경로만 쓴다 — 좌표는 **원본 그대로** 받아 클라가 변환한다.
// [F1] 좌표 바인딩(어느 컬럼이 x/y/val/key인가)은 서버가 해석해 서빙한다
// (paint-rules `binding` — fetchServedBinding). 종전의 클라 로컬 유도(deriveMapBinding
// + 스키마 조회)는 삭제됐다: 서버 매처의 복사본이라 답이 어긋날 수 있었고(F3),
// 선언 바인딩(tx/ty·대문자 등 관례 밖 컬럼)을 아예 볼 수 없었다.
const OVERLAY_CELL_LIMIT = 2000;   // 메인 로드(loadExistingMap)와 같은 상한

// map_key('_' 조인)를 key_columns에 분해 — 마지막 컬럼이 나머지를 흡수(랏 이름의 '_' 방어).
// [7b] Decomposition is `decomposeMapKey` — the same split the server's `build_key_filters`
// performs, canonicalised by the same declared types. Cell filters survived the 7b defect
// only because crud casts them by column type; going through the shared decomposition means
// the filter and the meta lookup can no longer disagree about what this key means.
function buildKeyFilters(keyColumns, mapKey, columnTypes) {
  const parts = decomposeMapKey(keyColumns, mapKey, columnTypes);
  const filters = {};
  Object.keys(parts).forEach(col => {
    filters[col] = { filterType: 'text', type: 'equals', filter: String(parts[col] ?? '') };
  });
  return filters;
}

// 오버레이 추가. 성공하면 {layer}, 실패하면 {error} 반환 (조용한 실패 금지 — 목록에도 남는다).
//
// ⚠️ **불변 조건**: 이 함수는 편집 중인 맵을 **어떤 방식으로도 건드리지 않는다.**
//    selectedTable / tableSchema / gridData / legend / 규격 / 브러시 / 메타 입력을 읽기만 하고
//    쓰지 않으며, switchTable·renderMetadataInputs 경로를 타지 않는다.
async function addOverlayLayer(sourceTable, sourceKey, targetOverride) {
  const targetTable = (targetOverride && targetOverride.table) || selectedTable;
  // The target key is used for **one thing only**: looking up the target's registered spec
  // (wafer_map_metadata). Two different values used to be conflated here:
  //   · which map is actually on the canvas → `loadedIdentity` (pinned at load time)
  //   · what is typed into the meta inputs  → `getCurrentMapKey()`
  // [F2] Only the first may drive a spec lookup. Typing a key without loading it must not make
  // the gate judge against another map's spec.
  //
  // No loaded map ⇒ there is no registered target spec to look up. That is **not** a refusal:
  // the frame then comes from the live on-screen grid controls (`currentFrame()`), which is the
  // very state a bonding plan starts in — blank canvas, EDS/defect overlaid before anything is
  // painted. The old guard here made that impossible.
  const targetKey = (targetOverride && targetOverride.key)
    || ((loadedIdentity && loadedIdentity.table === targetTable) ? loadedIdentity.mapKey : '');
  if (!sourceTable || !sourceKey) return { error: '오버레이 대상 맵 식별자가 없습니다.' };
  if (!targetTable) return { error: '현재 캔버스의 테이블을 알 수 없습니다.' };
  const fail = (msg, status, extra) => {
    pushFailedOverlay(sourceTable, sourceKey, status || 'error', msg, targetOverride);
    return { error: msg, status, ...(extra || {}) };
  };
  const errText = (e) => (e && e.message ? e.message : String(e));

  // ① 소스 테이블의 좌표 바인딩 — 서버 해석본을 서빙받는다 ([F1] paint-rules `binding`,
  //    선언 table_bindings > table_config 유도, 클라 복사본 없음. 메인 로드의 드롭다운
  //    프리셀렉트와 같은 캐시·같은 답이다).
  //
  // 여기가 예전에는 ②였다. 앞에 있던 "서버에 계측 보정(align override)이 선언돼 있는지"
  // probe 관문은 서버의 선언 레이어와 함께 제거됐다 — 정렬의 근거가 메타 하나로 좁혀져
  // 보정이 소스 메타에 이미 들어 있으므로, 따로 물어볼 선언이 존재하지 않는다.
  let binding;
  try {
    binding = await fetchServedBinding(sourceTable);
  } catch (e) {
    return fail(`${sourceTable}: 좌표 바인딩 조회 실패 — ${errText(e)}`, 'error');
  }
  if (!binding) {
    return fail(
      `${sourceTable}: 맵 좌표 바인딩을 해석할 수 없습니다 — table_config에 x/y 컬럼, ` +
      `map_key_columns(또는 lot/slot), 값 컬럼 후보가 있어야 합니다. 컬럼명이 관례와 다르면 ` +
      `map_overlay_config.table_bindings에 선언하십시오.`,
      'binding_unavailable');
  }
  // [F2] A guessed value column never reaches this data path — same discipline as the
  // server, whose data paths refuse what resolve_binding_info marks "fallback_guess".
  // Overlaying a guess paints a decoy: the canvas looks right while the values come
  // from an arbitrary column. Refuse loudly with the remedy. (The LOAD path may still
  // preselect a guess — there the user sees and confirms the dropdown; here nobody
  // would.)
  if (binding.source === 'fallback_guess') {
    return fail(
      `${sourceTable}: 값 컬럼을 확정할 수 없습니다 — 후보에 없는 '${binding.val}' 추측뿐입니다. ` +
      `엉뚱한 값이 겹쳐 보이는 것을 막기 위해 겹치지 않습니다. map_overlay_config.table_bindings에 ` +
      `값 컬럼을 선언하십시오.`,
      'binding_unavailable');
  }

  // [7b] ①-bis Canonicalise the source key BEFORE it is used for anything. It is used twice —
  // the cell filters and the `wafer_map_metadata` lookup — and only the first survived the raw
  // spelling (crud casts data filters by declared type; `map_id` is a plain string column and
  // does not). That asymmetry is precisely the reported symptom: **the data opened and the
  // metadata looked absent.** One normalisation here fixes both uses and keeps them agreeing.
  // A schema we could not confirm leaves the key untouched — the pre-7b behaviour, which may
  // miss but never invents a key.
  const srcSpec = await fetchMapKeySpec(sourceTable);
  const srcKeyColumns = (srcSpec.keyColumns && srcSpec.keyColumns.length > 0)
    ? srcSpec.keyColumns : binding.keyColumns;
  if (srcSpec.ok) sourceKey = canonicalMapKey(srcKeyColumns, sourceKey, srcSpec.columnTypes);

  // ② source cells + ③ source/target specs — the same two REST paths the main load uses.
  //    A failed cell fetch and a failed spec fetch are different reasons. Collapsing them into
  //    one catch would report "could not confirm the spec" as "cell fetch failed", so split them
  //    with allSettled. Requests still go out in parallel — no extra round trip.
  let rows, sourceMeta, targetMeta;
  const filters = buildKeyFilters(binding.keyColumns, sourceKey, srcSpec.columnTypes);
  const cellUrl = `${API_BASE}/tables/${sourceTable}/data?limit=${OVERLAY_CELL_LIMIT + 1}`
    + `&filters=${encodeURIComponent(JSON.stringify(filters))}`;
  const [cellR, sMetaR, tMetaR] = await Promise.allSettled([
    fetch(cellUrl),
    fetchGridMetaFor(sourceTable, sourceKey),
    fetchGridMetaFor(targetTable, targetKey),
  ]);
  try {
    if (cellR.status === 'rejected') throw cellR.reason;
    if (!cellR.value.ok) throw new Error(`HTTP ${cellR.value.status}`);
    const result = await cellR.value.json();
    rows = Array.isArray(result && result.data) ? result.data : [];
  } catch (e) {
    return fail(`${sourceTable}: 셀 조회 실패 — ${errText(e)}`, 'error');
  }
  // 🔴 A failed spec *fetch* is not "spec not registered". Falling back to identity without
  //    confirming puts markers at silently wrong coordinates and leaves the chip showing
  //    "무보정 · 규격 미등록" — a false reason. Surface it as a failure row and do not draw.
  //    The row keeps its retry button, so this is recoverable.
  if (sMetaR.status === 'rejected') {
    return fail(
      `${sourceTable}: 소스 맵 규격(wafer_map_metadata)을 확인하지 못했습니다 — ${errText(sMetaR.reason)}. ` +
      `규격을 모르는 채로 겹치면 좌표가 조용히 어긋나므로 겹치지 않습니다.`,
      'meta_unavailable');
  }
  if (tMetaR.status === 'rejected') {
    return fail(
      `${targetTable}: 타깃 맵 규격(wafer_map_metadata)을 확인하지 못했습니다 — ${errText(tMetaR.reason)}. ` +
      `기준 프레임을 모르는 채로 겹치면 좌표가 조용히 어긋나므로 겹치지 않습니다.`,
      'meta_unavailable');
  }
  sourceMeta = sMetaR.value;
  targetMeta = tMetaR.value;

  let truncated = false;
  if (rows.length > OVERLAY_CELL_LIMIT) { rows = rows.slice(0, OVERLAY_CELL_LIMIT); truncated = true; }

  const cells = [];
  rows.forEach(row => {
    const d = row.data || {};
    const xn = parseInt(d[binding.x] ? d[binding.x].value : undefined, 10);
    const yn = parseInt(d[binding.y] ? d[binding.y].value : undefined, 10);
    if (!Number.isFinite(xn) || !Number.isFinite(yn)) return;
    const v = (binding.val && d[binding.val]) ? d[binding.val].value : null;
    cells.push({ x: xn, y: yn, val: v });
  });
  if (cells.length === 0) return fail(`${sourceTable}: 겹칠 셀이 없습니다.`, 'no_data');

  // ④ 프레임 확정. 소스 메타가 없으면 **현재 화면 규격으로 해석(identity)** 한다 —
  //    서버 규율 3과 동일(선언 부재는 실패가 아니다). 대신 칩에 "무보정"으로 드러난다.
  //    타깃도 같은 규칙이다. 타깃 규격이 없으면(미로드이거나 미등록) 프레임은 **화면 컨트롤**이
  //    되며, 그 사실은 아래 targetBasis로 칩에 드러난다 — 등록 규격과 섞어 보이면 안 된다.
  const srcMetaFrame = frameFromMeta(sourceMeta);
  const srcFrame = srcMetaFrame || currentFrame();
  const tgtMetaFrame = frameFromMeta(targetMeta);
  const tgtFrame = tgtMetaFrame || currentFrame();
  const srcResolved = resolveFrame(srcFrame);
  const tgtResolved = resolveFrame(tgtFrame);
  // 🔴 **앉히는 프레임은 지금 화면이다** — 마커를 그리는 렌더 루프가 읽는 좌표계가 그것이기
  //    때문이다. `tgtResolved`(등록 규격)는 아래 ⑦의 **보고**에만 쓴다. 둘이 다르면 그 사실은
  //    이미 `targetBasis` 칩이 말한다.
  const seatFrame = resolveFrame(currentFrame());

  // ⑤-bis [H5] 격자 치수의 **정의역**. 규칙 6이 없앤 것은 「치수가 같아야 한다」는 *규격* 관문이지
  //    이 *온전성* 관문이 아니다. `projectCellsToWaferMm`은 소스 치수로 프레임 창을 열고 그 안에서
  //    `getWaferBoundingBox`가 격자를 전수 순회하므로, `grid_cols/rows = 1024`인 메타 행 하나면
  //    취소 수단 없는 동기 루프가 104만 칸을 돈다. 셀 수는 `OVERLAY_CELL_LIMIT`이 막는데 **치수는
  //    아무도 막지 않는다** — 종전에는 치수 일치 관문이 우연히 이것까지 막고 있었다.
  const srcDimErr = frameDimError(srcResolved);
  const seatDimErr = frameDimError(seatFrame);
  if (srcDimErr || seatDimErr) {
    return fail(
      `${sourceTable}: 격자 치수가 편집기의 정의역 밖입니다 — `
      + [srcDimErr ? `소스 ${srcDimErr}` : '', seatDimErr ? `타깃 ${seatDimErr}` : ''].filter(Boolean).join(' · '),
      'align_unavailable');
  }

  // ⑥ [규칙 6] 물리 좌표를 세울 수 있는가. **치수가 다른 것은 더 이상 거절 사유가 아니다** —
  //    셀 크기가 다르면 격자 치수도 당연히 다르고, 그 둘을 겹치는 것이 이 규칙이다.
  //    남는 전제는 **칩 피치를 알 수 있는가** 하나다: 피치가 없으면 칸 번호를 길이로 바꿀 수
  //    없고, 그러면 「WF 내 물리 좌표」라는 기준 자체가 없다.
  //
  // 🔴 **판정은 `resolveFrame`의 출력을 보지 않는다.** 그 값은 `physNum`이 이미 기본값으로
  //    접어 놓은 뒤라 「선언 없음」이 관측 불가능하다(§physDeclaration). 여기서 읽는 것은
  //    **어디서 온 값인가**라는 사실이다.
  const pitchFacts = (frame) => ({
    x: physDeclaration(frame, 'chipX', el.physChipX),
    y: physDeclaration(frame, 'chipY', el.physChipY),
  });
  const srcPitch = pitchFacts(srcFrame);
  const seatPitch = pitchFacts(null);          // null = 화면 컨트롤 그대로
  const unusable = (p) => !(p.x.value > 0) || !(p.y.value > 0);
  if (unusable(srcPitch) || unusable(seatPitch)) {
    // [D1] `source`를 그대로 흘리면 조작자가 읽는 문장에 `auto_registered`라는 내부 열거값이
    //      섞인다. 사유는 사람이 읽는 자리이므로 한 번만 사람 말로 옮긴다 — 판정은 위
    //      `unusable`이 이미 끝냈고 여기서는 **표시만** 한다(두 번째 판정이 아니다).
    const sayOne = (d) => (d.value !== null ? String(d.value)
      : d.source === 'auto_registered' ? '미선언(자동 등록된 합성 규격)' : d.source);
    const say = (p) => `${sayOne(p.x)}x${sayOne(p.y)}`;
    const autoNote = (srcPitch.x.source === 'auto_registered' || seatPitch.x.source === 'auto_registered')
      ? ` 자동 등록된 규격은 칩 크기를 잰 적이 없어(합성값) 정렬 근거가 되지 못합니다 — `
        + `해당 맵의 물리 규격을 선언한 뒤 다시 시도하십시오.`
      : '';
    return fail(
      `${sourceTable}: 칩 크기(phys_chip_x/phys_chip_y)를 확정할 수 없습니다 — `
      + `소스 ${say(srcPitch)} · 타깃 ${say(seatPitch)}. `
      + `셀 크기를 모르면 웨이퍼 내 물리 위치를 맞출 근거가 없으므로 겹치지 않습니다.${autoNote}`,
      'align_unavailable');
  }
  // 🔴 **프레임을 선언한 소스는 그 프레임의 피치도 선언해야 한다.** 소스 메타가 격자를
  //    선언했는데 칩 크기만 비어 있으면 `physNum`이 **타깃의 화면 피치**로 메꾼다 — 그러면
  //    두 맵이 같은 칸 크기라고 주장하는 셈이라 화면은 완벽히 정렬돼 보이고 값은 전부 틀린다
  //    (실측 570/600). 소스 메타가 아예 없는 경우는 다르다: 그때 프레임은 **화면으로
  //    해석하겠다는 명시적 선택**이고(위 ④) 칩에 그렇게 적힌다.
  if (srcMetaFrame && (srcPitch.x.source !== 'frame' || srcPitch.y.source !== 'frame')) {
    return fail(
      `${sourceTable}: 소스 맵이 격자(${srcResolved.cols}x${srcResolved.rows})는 선언했는데 `
      + `칩 크기를 선언하지 않았습니다(phys_chip_x=${srcPitch.x.source}, phys_chip_y=${srcPitch.y.source}). `
      + `그대로 겹치면 타깃의 셀 크기를 소스의 것으로 가정하게 되어 화면은 맞아 보이고 좌표가 전부 `
      + `어긋납니다. wafer_map_metadata에 셀 크기를 등록하십시오.`,
      'meta_unavailable');
  }

  // ⑦ 정렬 요약(표시용). **모든 축**을 비교해 identity/derived를 가른다 —
  //    rotation/flip만 보면 y반전·START만 다른 정상 케이스를 "무보정"으로 오표시한다.
  const identical = frameAxesKey(srcResolved) === frameAxesKey(tgtResolved);
  const diffs = [];
  if (srcResolved.rotation !== tgtResolved.rotation) diffs.push(`회전(${srcResolved.rotation}°→${tgtResolved.rotation}°)`);
  if (srcResolved.side !== tgtResolved.side) diffs.push(`면(${srcResolved.side}→${tgtResolved.side})`);
  if (srcResolved.invertY !== tgtResolved.invertY) diffs.push(`y반전(${srcResolved.invertY}→${tgtResolved.invertY})`);
  if (srcResolved.startX !== tgtResolved.startX || srcResolved.startY !== tgtResolved.startY) {
    diffs.push(`시작좌표(${srcResolved.startX},${srcResolved.startY})→(${tgtResolved.startX},${tgtResolved.startY})`);
  }
  // [규칙 6] 셀 크기는 **따로 말한다** — 겹치기의 근거를 정하는 축이라 「물리 규격 상이」라는
  // 뭉뚱그린 문구에 섞이면 조작자가 실제 값을 못 본다. 나머지 물리 항목은 바운딩박스에만
  // 영향을 주므로 종전 문구 그대로다.
  if (srcResolved.chipX !== seatFrame.chipX || srcResolved.chipY !== seatFrame.chipY) {
    diffs.push(`셀 크기(${srcResolved.chipX}x${srcResolved.chipY}mm→${seatFrame.chipX}x${seatFrame.chipY}mm)`);
  }
  if (srcResolved.offsetX !== tgtResolved.offsetX || srcResolved.offsetY !== tgtResolved.offsetY
    || srcResolved.waferDia !== tgtResolved.waferDia || srcResolved.edgeMargin !== tgtResolved.edgeMargin) {
    diffs.push('웨이퍼 물리 규격 상이(바운딩박스 재계산)');
  }
  const missingPhys = !sourceMeta ? '소스 맵 규격 미등록 — 현재 화면 규격으로 해석'
    : (srcMetaFrame && [srcFrame.waferDia, srcFrame.chipX, srcFrame.chipY,
    srcFrame.offsetX, srcFrame.offsetY, srcFrame.edgeMargin].some(v => v === undefined)
      ? '소스 물리 규격 일부 미등록 — 현재 화면 값으로 대체' : '');
  // 타깃 프레임의 근거가 **등록 규격**인지 **지금 화면**인지. 두 상태를 같은 칩으로 보이면
  // "규격에 맞춰 정렬됨"과 "지금 화면에 맞춰 정렬됨"이 구분되지 않는다.
  const targetBasis = tgtMetaFrame ? 'spec' : 'screen';
  const targetNote = tgtMetaFrame ? ''
    : (targetKey ? `타깃 맵 규격 미등록(${targetTable} · ${targetKey}) — 현재 화면 격자 설정 기준`
      : '기준 맵 미로드 — 현재 화면 격자 설정 기준');
  const align = {
    origin: identical ? 'identity' : 'derived',
    targetBasis,
    rotation: ((srcResolved.rotation - tgtResolved.rotation) % 360 + 360) % 360,
    flip: srcResolved.side !== tgtResolved.side ? 'x' : 'none',
    offset: { x: 0, y: 0 },
    // 🔴 좌석에 딸린 수(격자 밖·n:1)는 여기 넣지 않는다 — 그 수들은 화면 규격이 바뀔 때마다
    //    달라지는데 이 문자열은 추가 시점에 한 번만 만들어져 조용히 낡는다. 좌석 쪽 문구는
    //    `seatNote`가 재좌석마다 다시 쓴다.
    note: [diffs.length ? `프레임 정규화: ${diffs.join(', ')}` : '', missingPhys, targetNote]
      .filter(Boolean).join(' · ')
      || (identical ? '소스와 타깃의 좌표계가 완전히 같습니다 (변환 없음)' : ''),
  };

  const layer = {
    id: overlaySeq++,
    sourceTable: String(sourceTable),
    sourceKey: String(sourceKey),
    rawCells: cells,      // **소스 원본 좌표** — 재투영의 유일한 원천
    frame: srcFrame,      // 그 좌표가 사는 프레임 (소스 자신의 메타)
    // [규칙 6] 웨이퍼 내 절대 mm 항목. 화면 규격에 **불변**이므로 여기서 한 번만 만든다.
    mmItems: projectCellsToWaferMm(cells, srcFrame),
    color: OVERLAY_COLORS[(overlayLayers.length) % OVERLAY_COLORS.length],
    visible: true,
    status: 'ok',
    align,
    // 정렬 적용 여부의 유일한 근거는 origin이다 (rotation/flip은 표시용 요약일 뿐)
    alignApplied: align.origin !== 'identity',
    alignText: [align.note, `origin=${align.origin}`, `rot=${align.rotation}°`, `flip=${align.flip}`]
      .filter(Boolean).join(' · '),
    truncated,
    cap: truncated ? OVERLAY_CELL_LIMIT : null,
  };
  // 좌석(cells/items/count/outside/fanout)은 **화면 프레임**의 함수다 — 여기서도, 규격이
  // 바뀔 때도 같은 함수 하나가 만든다.
  reseatOverlayLayer(layer);
  // 같은 소스의 실패 잔존 행이 있으면 성공 행으로 교체한다 (재시도 성공)
  overlayLayers = overlayLayers.filter(o => !(o.failed && o.sourceTable === layer.sourceTable && o.sourceKey === layer.sourceKey));
  overlayLayers.push(layer);
  // [N2-b] 겹치면 그 층의 값들이 legend/DOE 목록에 **뜬다**(사용자 요청 2026-08-04).
  // 그 전까지 `ensureLegendValues`의 호출자는 **가져오기 하나뿐**이었고, 그래서 겹치기만 한
  // 값은 `legendColorForValue`가 답을 못 찾아 **속 빈 점**으로 그려졌다 — 값별 색 기능이
  // 명세대로 동작하면서 "아무것도 안 된 것"처럼 보인 이유가 이것이다.
  // 🔴 `vocab: true`다. 이 맵은 이 값들을 칠한 적이 없다 — 목록에는 뜨되 Push 페이로드에는
  //    들어가지 않는다(규율 ①: 서버에 가는 것은 [⚡ Push] 성공 시점의 registry뿐).
  // 🔴 층을 **제거해도 되돌리지 않는다.** 되돌리기는 "사용자가 방금 지정한 색을 조용히
  //    버리는" 쪽 실패로 곧장 간다. 남겨 두는 쪽의 비용은 목록 한 줄뿐이고 그마저도 이미
  //    수명이 정해져 있다: vocab 행은 저장 페이로드에서 빠지고(`buildLegendRegistryUpdates`),
  //    맵을 다시 열 때 청구되지 않은 것은 화면에서 내려간다(`applyRegistryRowsToLegend`).
  //    반대로 사용자가 색을 주거나 그 값으로 칠하면 `reconcileVocabClaims`가 이 맵의 것으로
  //    승격시키므로, "되돌려도 안전한 행"은 **아무도 본 적 없는 행**뿐이다.
  const seeded = ensureLegendValues(overlayLayerValues(layer), { vocab: true });
  if (seeded.length > 0) {
    // 가져오기 경로와 같은 뒷정리다 — 값 잠금 선언이 새 값을 보호 집합에 편입해야 하고,
    // legend 표는 방금 생긴 행을 보여야 한다. 하나라도 빠지면 화면이 낡는다.
    recomputeLockedCells();
    renderLegendTable();
  }
  recomputeActiveOverlays();
  renderOverlayList();
  scheduleRenderGridCanvas();
  return { layer, seeded };
}

function removeOverlayLayer(id) {
  overlayLayers = overlayLayers.filter(o => o.id !== id);
  recomputeActiveOverlays();
  renderOverlayList();
  scheduleRenderGridCanvas();
}

function toggleOverlayLayer(id) {
  const o = overlayLayers.find(x => x.id === id);
  if (!o) return;
  o.visible = !o.visible;
  recomputeActiveOverlays();
  renderOverlayList();
  scheduleRenderGridCanvas();
}

function clearOverlayLayers() {
  overlayLayers = [];
  recomputeActiveOverlays();
  renderOverlayList();
  scheduleRenderGridCanvas();
}

// ── [규칙 6] 레이어를 **지금 화면의 칸에 앉힌다** ────────────────────────────────
// 추가 시점과 규격 변경 시점이 **같은 함수 하나**를 부른다. 둘로 나뉘어 있던 종전 구조에서는
// 추가 때 센 수(격자 밖 N칩)가 규격 변경 뒤에도 그대로 남아 화면과 어긋났다.
//
// 🔴 **대표값을 고르지 않는다.** 한 칸이 소스 여러 칸을 받으면 `cells`의 값은 `null`이고
//    항목 전부는 `items`에 남는다. 대표를 고르면 나머지를 조용히 버리면서 한 값을 자신
//    있게 보여 주게 된다(사용자 확정 ⓒ「전부 나열」).
function reseatOverlayLayer(o) {
  if (!o || o.failed) return;
  const seat = resolveFrame(currentFrame());
  const { seated, duplicates } = seatWaferMmInFrame(o.mmItems, seat);
  const seatKeys = canvasSeatKeys();

  const cells = new Map();
  let chips = 0, outside = 0, fanout = 1, multiCells = 0, fanCells = 0, conflictCells = 0;
  seated.forEach((list, key) => {
    chips += list.length;
    if (list.length > fanout) fanout = list.length;
    // 🔴 「여럿」에는 **두 가지 다른 사연**이 있고 문구가 그것을 구별해야 한다:
    //    자리가 서로 다르면 → 타깃 셀이 굵어서 생긴 진짜 n:1 (규칙 6)
    //    자리가 같은데 값이 다르면 → 소스에 같은 좌표가 두 번 (중복 행 충돌, 피치와 무관)
    if (list.length > 1) {
      multiCells++;
      const spots = new Set(list.map(e => `${e.mmX}_${e.mmY}`));
      if (spots.size > 1) fanCells++;
      if (spots.size < list.length) conflictCells++;
    }
    // 🔴 `inside`로 센다 — [↓ 가져오기]가 거르는 그 집합이다(§canvasSeatKeys).
    if (!seatKeys.inside.has(key)) outside += list.length;
    cells.set(key, list.length === 1 ? list[0].val : null);
  });

  // 물리 축 → 화면 축의 2x2 변환. 🔴 **회전식을 새로 쓰지 않는다** — 이미 있는
  // `getCanvasCellFromDieIndex`에 (0,0)/(1,0)/(0,1)을 넣고 그 답의 차분을 읽을 뿐이다.
  // 정수 격자 사상이라 성분은 0/±1이고 패리티 항은 차분에서 상쇄된다.
  o.seatAxes = (() => {
    const o0 = getCanvasCellFromDieIndex(seat, 0, 0, seat.cols, seat.rows, seat.rotation, seat.side);
    const oX = getCanvasCellFromDieIndex(seat, 1, 0, seat.cols, seat.rows, seat.rotation, seat.side);
    const oY = getCanvasCellFromDieIndex(seat, 0, 1, seat.cols, seat.rows, seat.rotation, seat.side);
    return { xc: oX.c - o0.c, xr: oX.r - o0.r, yc: oY.c - o0.c, yr: oY.r - o0.r };
  })();
  o.seatChip = { x: seat.chipX, y: seat.chipY };

  o.items = seated;
  o.cells = cells;          // 값 조회용(1:1일 때만 값, 여럿이면 null) — 존재 판정은 종전 그대로
  o.count = chips;          // **칩 수**(소스 다이 수). 칸 수는 cellCount다
  o.cellCount = seated.size;
  o.fanout = fanout;
  o.multiCells = multiCells;
  o.fanCells = fanCells;
  o.conflictCells = conflictCells;
  o.dupCollapsed = duplicates;
  o.outside = outside;
  o.seatNote = [
    outside ? `격자 밖 ${outside}칩 — [↓ 가져오기] 제외` : '',
    fanCells ? `타깃 셀이 더 굵어 한 칸이 최대 ${fanout}칩 — ${fanCells}칸이 여러 다이의 값을 받음` : '',
    conflictCells ? `같은 좌표에 다른 값 ${conflictCells}칸 (소스 중복 행)` : '',
    duplicates ? `같은 행 ${duplicates}건 병합 (버린 값 없음)` : '',
    multiCells ? `여러 값을 받은 ${multiCells}칸 — [↓ 가져오기] 제외 (점으로는 남아 있음)` : '',
  ].filter(Boolean).join(' · ');
}

// 규격이 바뀌면 레이어를 **다시 앉힌다**.
//
// 🔴 [규칙 6] 종전에는 소스 프레임으로 재투영만 했다. 다이 인덱스 키는 화면에 불변이었기
//    때문인데, **mm 좌석은 화면 피치의 함수다** — chip_x를 바꾸면 같은 mm가 다른 칸에
//    앉는다. 그래서 재좌석은 선택이 아니라 필수다.
// [C7] 시그니처에 **물리 파라미터가 반드시 들어간다** — 빠뜨리면 chip_x/offset 등을 바꿨을
// 때 재좌석이 일어나지 않아 오버레이가 조용히 어긋난 자리를 가리킨다.
let overlayGeomSig = '';

function currentGeomSignature() {
  return [
    el.gridCols ? el.gridCols.value : '',
    el.gridRows ? el.gridRows.value : '',
    el.gridStartX ? el.gridStartX.value : '',
    el.gridStartY ? el.gridStartY.value : '',
    el.gridYInvert ? (el.gridYInvert.checked ? 1 : 0) : 0,
    currentRotation, currentSide,
    el.physWaferDia ? el.physWaferDia.value : '',
    el.physChipX ? el.physChipX.value : '',
    el.physChipY ? el.physChipY.value : '',
    el.physOffsetX ? el.physOffsetX.value : '',
    el.physOffsetY ? el.physOffsetY.value : '',
    el.physEdgeMargin ? el.physEdgeMargin.value : '',
  ].join('|');
}

function syncOverlayGeometry() {
  if (overlayLayers.length === 0) { overlayGeomSig = currentGeomSignature(); return; }
  const sig = currentGeomSignature();
  if (sig === overlayGeomSig) return;
  overlayGeomSig = sig;
  overlayLayers.forEach(o => {
    if (o.failed) return;
    reseatOverlayLayer(o);
  });
  recomputeActiveOverlays();
  renderOverlayList();
}

// ── 오버레이 목록 UI (메인 로드와 분리된 전용 블록) ──
// 정렬 상태를 **칩으로 항상 노출**한다. 종전에는 alignApplied일 때만 표기해
// "정렬 안 함(identity)"과 "정렬 실패(align_unavailable)"가 구분되지 않았다.
// ⚠️ **정렬 여부는 `origin`으로만 판단한다 — rotation/flip으로 판단하지 마라.**
// 좌표축 6종(회전·거울상·Y반전·START X/Y·치수·물리 규격)을 한 파이프라인에서 처리하므로
// `origin: "derived"`인데 `rotation: 0, flip: "none"`인 경우가 **정상적으로 존재한다**
// (Y반전이나 시작좌표만 보정된 경우). 회전값으로 분기하면 그런 보정을 "무보정"으로 표시해
// 조용한 오답이 된다 — 실증: test/QQ → bonding_map/QQ 80셀이 전부 (-11,-13) 어긋나 있었는데
// 구 판정에서는 `identity`로 보였다.
// `offset`도 마찬가지다 — 순수 평행이동일 때만 실값을 갖고 회전이 섞이면 0이므로,
// offset==0을 "보정 없음"의 근거로 쓰지 않는다.
function overlayAlignChip(o) {
  if (o.failed) {
    return `<span class="ov-chip bad" title="${escapeHtmlAttr(o.reason || '')}">${escapeHtmlAttr(o.status)}</span>`;
  }
  if (!o.align) return '<span class="ov-chip dim" title="정렬 정보가 없습니다">align 미상</span>';
  const origin = String(o.align.origin || '');
  // 🔴 좌석 쪽 문구(`seatNote`)는 **재좌석마다 다시 쓰인 것**이고 프레임 비교 문구(`note`)는
  //    추가 시점의 것이다. 둘을 합쳐야 칩의 설명이 지금 화면과 어긋나지 않는다.
  const note = [String(o.align.note || ''), String(o.seatNote || '')].filter(Boolean).join(' · ');
  const rot = Number(o.align.rotation) || 0;
  // 무엇에 맞춰 정렬했는가 — 등록 규격(wafer_map_metadata)인가, 지금 화면의 격자 설정인가.
  // 후자를 전자처럼 보여주면 "규격대로 맞췄다"는 거짓 진술이 된다(빈 맵 오버레이의 기본 상태).
  const basis = o.align.targetBasis === 'screen'
    ? '<span class="ov-chip dim" title="타깃 규격 미등록 — 현재 화면의 격자 설정 기준">화면기준</span>'
    : '';
  if (origin === 'identity') {
    return `<span class="ov-chip dim" title="${escapeHtmlAttr(note || '좌표 보정 없음')}">무보정</span>${basis}`;
  }
  // derived(및 그 외 비-identity) = 보정 적용됨. 회전은 0일 수 있으므로 있을 때만 덧붙인다.
  const label = rot ? `정렬됨 ${rot}°` : '정렬됨';
  return `<span class="ov-chip ok" title="${escapeHtmlAttr(note || o.alignText || '소스 메타 프레임으로 해석해 물리 좌표에 맞춤')}">${escapeHtmlAttr(label)}</span>${basis}`;
}

// 한 칸이 값을 여럿 받았을 때의 상태 칩. 🔴 **라벨이 사연을 구별한다** — 소스에 같은 좌표가
// 두 번 있어서 생긴 「여럿」에 「타깃 셀이 더 굵어」라고 적으면 그것은 거짓이고, 조작자는 셀
// 크기를 의심하며 엉뚱한 곳을 고치게 된다. 상세는 `seatNote`가 재좌석마다 다시 쓴다.
function overlayFanChip(o) {
  if (o.failed || !(o.multiCells > 0)) return '';
  const label = o.fanCells > 0 ? `최대 ${o.fanout}:1` : '중복 좌표';
  return `<span class="ov-chip warn" title="${escapeHtmlAttr(o.seatNote || '')}">${escapeHtmlAttr(label)}</span>`;
}

// [N2] The values for which the legend declares no colour. The canvas leaves those dots
// unfilled, but AN UNFILLED DOT ALONE CANNOT SAY WHICH of the two reasons applies
// ("undeclared value" vs "several values in one cell"). Words make that distinction, and the
// several-values half is already spoken by `overlayFanChip` above.
// 🔴 Recounted from the live legend, never cached at add time. The moment the user adds one
//    of these values to the legend this chip must shrink; a captured count goes quietly stale
//    and a stale count is indistinguishable from a defect.
function overlayUnlistedValues(o) {
  return [...overlayLayerValues(o)].filter(v => !legendColorForValue(v));
}

function overlayLegendChip(o) {
  const miss = overlayUnlistedValues(o);
  if (miss.length === 0) return '';
  const shown = miss.slice(0, 8).join(', ') + (miss.length > 8 ? ' ...' : '');
  const tip = `범례 미선언 — 속이 빈 점으로 그립니다 · ${shown}`;
  return `<span class="ov-chip warn" title="${escapeHtmlAttr(tip)}">범례 밖 ${miss.length}종</span>`;
}

// ── [신규] 오버레이 → 실맵 가져오기 ────────────────────────
// 겹쳐 본 오버레이의 셀을 **현재 편집 중인 맵(gridData)** 으로 반영한다.
// 구 "테이블 전환 시 이월"을 대체하며 더 안전하다 — 오버레이 셀은 이미 **물리 키**로
// 배치돼 있고(o.cells: 물리키→값) gridData도 같은 물리 키라 **재변환이 없다**.
//
// 규율 4가지:
//   ① 서버 반영 없음 — gridData만 바꾼다. 실제 적재는 사용자가 [⚡ Push]를 눌러야 일어난다.
//   ② 페인트 잠금 존중 — isProtectedFCell(값 잠금 F / 선언 오버레이 잠금)은 덮지 않고 건너뛴다.
//   ③ 격자 밖 셀 제외 — push 대상이 아니므로 반영해도 유령이 된다.
//   ④ 정체성 불변 — selectedTable / 맵 키 / 규격을 **건드리지 않는다**(오버레이 경로 분리 원칙).
function importOverlayToGrid(id) {
  const o = overlayLayers.find(x => x.id === id);
  if (!o || o.failed || !o.cells || o.cells.size === 0) {
    showToast('가져올 셀이 없는 오버레이입니다.', 'warning');
    return;
  }
  // ③ 현재 격자의 "웨이퍼 안" 물리키 집합 (gridCells2D는 렌더 결과물이라 최신화 후 사용)
  renderGridCanvas();
  const insideKeys = new Set();
  if (gridCells2D) {
    Object.keys(gridCells2D).forEach(rStr => {
      const row = gridCells2D[rStr];
      if (!row) return;
      Object.keys(row).forEach(cStr => {
        const cell = row[cStr];
        if (cell && cell.inside) insideKeys.add(cell.key);
      });
    });
  }

  let applied = 0, locked = 0, outside = 0, blank = 0, multi = 0;
  const values = new Set();
  o.cells.forEach((val, key) => {
    // ⑤ [규칙 6] 한 칸이 소스 여러 칸을 받았으면 **가져오지 않는다.** `gridData`는 칸당 값
    //    하나이므로 여기서 무언가를 쓰려면 대표를 골라야 하는데, 그것이 사용자가 거절한
    //    바로 그 동작이다(나머지를 조용히 버리면서 한 값을 자신 있게 쓴다). 값은 `o.items`에
    //    전부 남아 있고, 건너뛴 수는 아래 토스트가 말한다.
    if (val === null) { multi++; return; }
    const sv = (val === undefined) ? '' : String(val).trim();
    if (sv === '') { blank++; return; }
    if (!insideKeys.has(key)) { outside++; return; }
    if (isProtectedFCell(key)) { locked++; return; }   // ② 잠금 셀은 덮지 않는다
    gridData[key] = sv;                                 // 겹치는 셀은 덮어쓰기 (총괄 지시 기본값)
    values.add(sv);
    applied++;
  });

  if (applied === 0) {
    showToast(`가져온 셀이 없습니다 (잠금 ${locked} · 격자 밖 ${outside} · 빈 값 ${blank}`
      + (multi ? ` · 여러 값 ${multi}` : '') + ').', 'warning');
    return;
  }

  // legend 병합 — 없는 값은 추가해야 칠해진 것이 화면에 보인다.
  // ⚠️ 여기서는 **로컬 캐시만** 갱신한다(persistLegend의 서버 디바운스 저장을 타지 않음).
  //    규율 ①에 따라 Push 전에는 서버에 아무것도 쓰지 않는다 — registry 저장은 pushMapData 성공 시.
  const added = ensureLegendValues(values);

  // 값 잠금 선언이 있으면 새로 들어온 F 등도 보호 집합에 편입해야 일관된다
  recomputeLockedCells();
  renderLegendTable();
  renderGridCanvas();
  scheduleCellDraft();
  framePushed = false; // 미저장 편집이 생겼다 — 뒤로가기 가드가 작동해야 한다

  const parts = [`${applied}셀 반영`];
  if (locked > 0) parts.push(`${locked}셀 건너뜀(잠금)`);
  if (outside > 0) parts.push(`${outside}셀 건너뜀(격자 밖)`);
  if (multi > 0) parts.push(`${multi}셀 건너뜀(한 칸에 여러 값)`);
  if (added.length > 0) parts.push(`legend ${added.length}종 추가`);
  const msg = `${o.sourceTable} · ${o.sourceKey} → ${parts.join(' · ')}`;
  // [1e] Speak ONLY when cells were skipped — those are "I pressed import and this did not
  // arrive", a reason the user needs. If everything landed, the result is on the canvas and
  // "not saved yet" is already stated by the plan-head chip, so no toast is layered on top.
  if (locked > 0 || outside > 0) {
    showToast(`${msg} — 저장은 [⚡ Push]`, 'warning');
  } else {
    console.debug(`[map] overlay imported — ${msg}`);
  }
}

// legend에 없는 값들을 추가하고 추가된 값 배열을 반환
// ([U6] declared default_legend 우선, 다음은 공용 팔레트 규칙 — autoAddLegendValue 하나로 간다)
//
// `opts.vocab`은 **이 맵이 보증하지 않는 값**이라는 표시다(2026-08-04). 두 호출자의 차이는
// 이 플래그 하나뿐이고, 그래서 두 번째 함수를 만들지 않는다:
//   · 가져오기(`importOverlayToGrid`)는 셀을 **이 맵에 칠한다** → 이 맵의 값이다(vocab 아님).
//   · 오버레이 얹기(`addOverlayLayer`)는 **남의 맵을 겹쳐 볼 뿐** 이 맵을 바꾸지 않는다 →
//     legend에 뜨되 이 맵의 계획인 척해서는 안 된다. `vocab: true` + 시드 서명이 정확히
//     그것을 뜻하고, 그 뜻을 이미 온 시스템이 지킨다: `buildLegendRegistryUpdates`가 vocab
//     행을 **페이로드에서 뺀다**(= Push해도 서버에 안 간다), `applyRegistryRowsToLegend`가
//     맵을 다시 열 때 청구되지 않은 vocab 행을 **화면에서 내린다**, 그리고
//     `reconcileVocabClaims`가 그 값으로 **칠하거나 행을 고치는 순간** 이 맵의 것으로 승격한다.
//     즉 "목록에는 뜨지만 아무것도 저장하지 않는다"가 새 기계장치 없이 성립한다.
function ensureLegendValues(values, opts) {
  const asVocab = !!(opts && opts.vocab);
  const added = [];
  values.forEach(v => {
    if (autoAddLegendValue(v, '')) {
      const sv = String(v);
      added.push(sv);
      if (asVocab) {
        const row = legend.find(l => String(l.value) === sv);
        // 표시와 시드는 **함께** 쓴다 — `reconcileVocabClaims`는 시드 없는 vocab 행을
        // "개명된 것"으로 읽어 즉시 청구로 승격시킨다(= 저장 대상이 된다).
        if (row) { row.vocab = true; legendVocabularySeed.set(sv, legendRowSignature(row)); }
      }
    }
  });
  if (added.length > 0) saveLegendToStorage(); // 로컬 캐시만 — 서버 registry는 Push 시점에
  return added;
}

// 한 오버레이 층이 실어 온 **서로 다른 값들**. `overlayUnlistedValues`가 쓰던 순회를 여기로
// 올렸다 — 같은 집합을 두 곳에서 다시 걸으면 한쪽만 고쳐지는 날이 온다.
// 한 legend 행이 **오버레이에서 들어온 것**인가, 그리고 어느 층에서인가.
//
// 🔴 저장하지 않고 **유도한다.** 행에 `sourceTable`/`sourceKey` 필드를 얹는 쪽이 쉬워 보이지만
//    두 곳에서 곧장 틀린다: ① 그 필드는 registry 페이로드·서명(`LEGEND_PAYLOAD_COLUMNS`)과
//    얽혀 「저장되는 필드는 비교되는 필드」 성질을 깨고, ② 층을 뗀 뒤에도 낡은 출처가 행에
//    남아 화면이 멀쩡한 채로 거짓을 말한다. 유도는 매 렌더에서 **지금 얹혀 있는 층**만 본다.
//
// 판정 규칙과 그 근거(사용자 판정 2026-08-04의 엣지 케이스들이 여기서 전부 떨어진다):
//  · `vocab !== true`  → **이 맵의 값이다. 표시하지 않는다.** registry에서 온 행과 사용자가
//    청구한 행은 `vocab: false`이므로, 같은 값이 맵에도 있고 오버레이에도 있으면 맵이 이긴다
//    (색 충돌도 같은 이유로 맵의 선언이 이긴다 — `autoAddLegendValue`가 기존 행을 안 건드린다).
//  · 두 층이 같은 값을 실어 오면 legend 행은 **하나**고, 여기서 출처만 둘로 세어 적는다.
//  · 사용자가 색을 주면 행 서명이 시드와 달라져 `reconcileVocabClaims`가 `vocab`을 내린다 →
//    그 순간부터 이 함수는 빈 배열을 돌려주고 표시가 사라진다. **그게 맞다**: 색을 준 값은
//    이 맵의 것이고, 그 뒤 층을 떼도 남아야 한다(= 지정한 색이 조용히 사라지지 않는다).
//  · 손대지 않은 채 층만 떼면 표시는 사라지지만 `vocab`은 남는다 — Push 페이로드에 안 들어가고
//    맵을 다시 열 때 내려간다. 「오버레이(해제됨)」 같은 문구를 만들지 않는 이유는
//    `seedEmptyDoe`의 기본 어휘 행도 `vocab: true`라서, 그 문구가 그쪽에는 거짓이 되기 때문이다.
function legendOverlaySources(item) {
  if (!item || item.vocab !== true) return [];
  const v = String(item.value);
  // 실패한 층을 여기서 다시 거르지 않는다 — `overlayLayerValues`가 이미 빈 집합을 돌려주고,
  // 「실패한 층은 아무 값도 나르지 않는다」의 구현은 한 곳이어야 한다. (실측: 여기에 `!o.failed`를
  // 겹쳐 두면 그 조건을 지워도 답이 안 바뀌어, 하네스 변이가 정당하게 살아남는다 = 무의미한 가드.)
  return overlayLayers
    .filter(o => overlayLayerValues(o).has(v))
    .map(o => `${o.sourceTable} · ${o.sourceKey}`);
}

function overlayLayerValues(o) {
  const out = new Set();
  if (!o || o.failed || !o.items) return out;
  o.items.forEach(list => list.forEach(it => {
    const v = (it.val === null || it.val === undefined) ? '' : String(it.val);
    if (v === '') return;                       // 빈 값은 색을 원한 적이 없다
    out.add(v);
  }));
  return out;
}

function renderOverlayList() {
  const countBadge = document.getElementById('overlay-count');
  if (countBadge) countBadge.textContent = String(overlayLayers.length);
  const clearBtn = document.getElementById('btn-clear-overlays');
  if (clearBtn) clearBtn.style.display = overlayLayers.length > 0 ? '' : 'none';

  const box = document.getElementById('overlay-list');
  if (!box) return;
  if (overlayLayers.length === 0) {
    // 겹친 것이 없으면 목록은 화면을 차지하지 않는다
    box.innerHTML = '';
    return;
  }
  // [출처 표기] 한 층이 **어느 테이블의 어느 키**에서 왔는지는 색이 아니라 **글자로** 말한다.
  // 색은 N2(`41b17ee`)부터 값을 뜻하게 됐으므로 정체까지 겸할 수 없다.
  // 🔴 이 두 조각은 종전에도 DOM에 있었다 — 안 보였을 뿐이다. `.ov-row`가 flex이고
  //    `.ov-name`만 `min-width: 0`이라, 폭이 모자라면 **줄어들 수 있는 유일한 상자**가
  //    이것이었다. 게다가 `overflow: hidden`에 `text-overflow`가 없어서 잘린 티도 안 났다.
  //    선언값으로 계산한 실제 예산(330px 사이드바 → `.ov-row` 내부 254px, 점 11 + 버튼 76
  //    + 간격 15): 칩이 하나만 붙어도 이름 상자에 남는 폭이 0~40px다. 즉 "출처가 안 뜬다"는
  //    체감은 정확했고, 원인은 렌더러가 아니라 레이아웃이었다.
  //    그래서 출처는 이제 **칩과 폭을 다투지 않는 자기 줄**을 갖고(아래 CSS의 grid areas),
  //    긴 키는 잘리는 대신 **줄바꿈**한다 — 식별자는 생략하면 식별자가 아니다.
  //    컨트롤은 늘지 않았다: 추가된 것은 `<span>` 두 개뿐이다.
  box.innerHTML = overlayLayers.map(o => `
    <div class="ov-row ${o.failed ? 'err' : ''} ${(!o.failed && !o.visible) ? 'off' : ''}" data-id="${o.id}">
      <span class="ov-dot" style="background:${escapeHtmlAttr(o.color)}"></span>
      <span class="ov-name" title="${escapeHtmlAttr(o.sourceTable + ' · ' + o.sourceKey + (o.reason ? ' — ' + o.reason : ''))}">
        <span class="ov-src">${escapeHtmlAttr(o.sourceTable)}</span><span class="ov-key">${escapeHtmlAttr(o.sourceKey)}</span>
      </span>
      <span class="ov-meta">${o.failed ? '' : `${o.count}칩${(o.fanout > 1) ? `→${o.cellCount}칸 ` : ' '}`}${overlayAlignChip(o)}${overlayFanChip(o)}${overlayLegendChip(o)}${o.truncated ? `<span class="ov-chip warn" title="서버 상한 ${escapeHtmlAttr(String(o.cap || '?'))}">일부만</span>` : ''}</span>
      <span class="ov-btns">
        ${o.failed ? '' : `<button type="button" class="ov-btn ov-import" data-act="import" title="현재 맵으로 가져오기 (잠금 셀 제외 · Push 전까지 서버 반영 없음)">↓</button>`}
        <button type="button" class="ov-btn" data-act="${o.failed ? 'retry' : 'toggle'}" title="${o.failed ? '다시 시도' : '표시/숨김'}">${o.failed ? '↻' : (o.visible ? '👁' : '🚫')}</button>
        <button type="button" class="ov-btn ov-del" data-act="del" title="제거">✕</button>
      </span>
    </div>`).join('');
  box.querySelectorAll('.ov-row').forEach(row => {
    const id = Number(row.dataset.id);
    row.querySelectorAll('.ov-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const act = btn.dataset.act;
        if (act === 'del') { removeOverlayLayer(id); return; }
        if (act === 'toggle') { toggleOverlayLayer(id); return; }
        if (act === 'import') { importOverlayToGrid(id); return; }
        // retry — 같은 소스로 재조회 (성공하면 실패 행이 성공 행으로 교체된다)
        const o = overlayLayers.find(x => x.id === id);
        if (!o) return;
        btn.disabled = true;
        const r = await addOverlayLayer(o.sourceTable, o.sourceKey, o.targetOverride || undefined);
        if (r && r.error) showToast(r.error, r.unsupported ? 'warning' : 'error');
        // [1e] Exactly as the comment above states — on success the failed row is REPLACED
        // by a success row. The result is in the list, so a toast says it twice.
        else console.debug(`[map] overlay retry ok: ${o.sourceTable} · ${o.sourceKey}`);
      });
    });
  });
}

function escapeHtmlAttr(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

// ── 오버레이 전용 블록 (메인 Load와 완전히 분리) ──
// 메인 [📂 Load] = 항상 교체 로드 / 여기 [＋ 겹치기] = 항상 겹치기.
// 모드 상태도 확인 다이얼로그도 없다 — **어느 버튼을 눌렀는지가 곧 의도**라 숨은 상태가 없다.
async function handleAddOverlayClick() {
  const table = el.overlaySrcTable ? el.overlaySrcTable.value : '';
  const key = el.overlaySrcKey ? el.overlaySrcKey.value.trim() : '';
  if (!table || !key) {
    showToast('겹칠 맵의 테이블과 맵 키를 입력하십시오.', 'warning');
    return;
  }
  // 빈 격자에서도 겹칠 수 있다 — 본딩 계획은 **맵이 없는 상태에서 시작**하고, EDS/defect를
  // 먼저 겹쳐 보고 나서 칠한다. 기준은 지금 화면의 격자 설정이며 그 사실은 칩(화면기준)에 뜬다.
  el.btnAddOverlay.disabled = true;
  el.btnAddOverlay.textContent = '정렬 중…';
  const r = await addOverlayLayer(table, key);
  el.btnAddOverlay.disabled = false;
  el.btnAddOverlay.textContent = '＋ 겹치기';
  if (r.error) {
    // 실패도 목록에 행으로 남는다 — 토스트로 흘리면 "왜 안 겹쳤는지"가 화면에서 증발한다
    showToast(r.error, r.unsupported ? 'warning' : 'error');
  } else {
    // [1e] Truncation is a DEGRADATION (§7: with total > rows we cannot claim to know the
    // server's state), so "you are seeing only part of the source" must be said. A complete
    // load shows up as a row plus its chip count in the overlay list, so it goes to console.
    const head = `오버레이 추가: ${r.layer.sourceTable} · ${r.layer.sourceKey} — ${r.layer.count}칩`;
    if (r.layer.truncated) showToast(`${head} (일부만 표시 — 서버 절단)`, 'warning');
    else console.debug(`[map] ${head}`);
    if (el.overlaySrcKey) el.overlaySrcKey.value = '';
  }
}

// ====================================================
// [재설계 v2] 자재 맵 오버레이 헬퍼
//   자재(core/tape) 맵 위에 defect/EDS를 겹쳐 보는 단축 경로.
//   프레임 안에서도 일반 오버레이 엔진을 그대로 쓴다(별도 모드 없음).
// ====================================================
const CORE_CANONICAL_TABLE = 'core_defect_map';

async function addOverlayForSource(sourceTable, lot, slot) {
  // [7b] Compose through the shared canonicaliser instead of raw string interpolation. This
  // is the exact site the production defect came in through: a material token supplies '01'
  // for a number-declared slot, and `LOT_01` never matched the stored `LOT_1`.
  // (`addOverlayLayer` normalises again — the operation is idempotent by INV-7b-4, so the
  // double application is harmless and each site stays correct on its own.)
  const spec = await fetchMapKeySpec(sourceTable);
  const cols = spec.keyColumns || [];
  let key;
  if (slot && cols.length >= 2) {
    key = composeMapId([cols[0], cols[1]], { [cols[0]]: lot, [cols[1]]: slot }, spec.columnTypes);
  } else if (slot) {
    key = `${lot}_${slot}`;   // key columns unknown — leave the conventional spelling alone
  } else {
    const only = cols.length >= 1 ? canonicalKeyValue(lot, spec.columnTypes[cols[0]]) : null;
    key = (only === null || only === undefined) ? String(lot) : only;
  }
  const targetTable = selectedTable || CORE_CANONICAL_TABLE;
  // 타깃 키는 넘기지 않는다 — addOverlayLayer가 loadedIdentity(로드 시점 확정)에서 유도한다.
  // 종전 `getCurrentMapKey() || key`는 미로드 상태에서 **소스 키를 타깃 키로 위조**해,
  // 존재하지도 않는 (타깃테이블, 소스키) 규격을 조회하게 만들었다.
  return addOverlayLayer(sourceTable, key, { table: targetTable });
}

function listOverlayLayers() {
  return overlayLayers.map(o => ({
    id: o.id, sourceTable: o.sourceTable, sourceKey: o.sourceKey,
    count: o.count, visible: o.visible, color: o.color,
    alignApplied: o.alignApplied, truncated: o.truncated,
  }));
}
