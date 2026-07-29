import './tokens.css';
import './style.css';
import { API_BASE, CURRENT_USER } from './config.js';
import { initTheme } from './theme.js';
import { getLocalTimeString, showToast } from './utils.js';
import { initTransferPlan, notifyMapContext, notifyLegendChanged, notifyPaintCounts, bandToState, stageTargetTables } from './transfer_plan.js';
// The ONE material-list normalizer. The panel parses what the user types with it and the
// storage layer normalizes with it, so the material COUNT on screen and the denominator of
// `ceil(total / n)` in the save can never be two different numbers.
// `ZONES`/`ZONE_LABEL` come with it because COPY HEADER MODE prints the zone group names
// (1H · MID · TOP) into the exported header. INV-ⓐ-4: the words on screen and the words in
// the export are ONE list — a second hardcoded copy here is how "MID" on screen becomes
// "MIDDLE" in the file the factory actually reads.
import { parseMaterialList, bandsToZones, ZONES, ZONE_LABEL, DOE_COLUMNS } from './doe_bands.js';
// [V1 effort instrument] The ONE collector (client2/src/effort_meter.js, owned by Lead PM).
// This file counts NOTHING on its own: no local counters, no second session id, no copy of
// the 1/3/5 weights (those live server-side and are applied at query time). Keystrokes and
// mouse presses come from the module's own page-wide listeners; this file only declares the
// screen transitions it is the only one that can see, and hands the raw counts to the save.
import {
  ROUTES, startSession, installGlobalListeners, installNavLinkCounting, countNav,
  snapshot as effortSnapshot, commitIfRecorded as effortCommitIfRecorded
} from './effort_meter.js';

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
    console.warn(`[Map Editor] paint-rules 조회 실패 (${t}): ${why} — 직전 잠금 규칙을 유지합니다.`);
    showToast(
      `페인트 잠금 규칙을 확인하지 못했습니다 (${t}) — 직전 규칙을 유지합니다. 잠금이 실제와 다를 수 있습니다.`,
      'warning', { dedupeKey: 'paint_rules_unconfirmed' });
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
// map_key 자체가 '_' 조인 문자열이고 테이블명에도 '_'가 흔하므로 bk 분리자는 '|' 사용
// (server/config/table_config.json의 composite_key_separator와 반드시 일치해야 함)
const SPLIT_KEY_SEP = '|';

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

function normalizeBands(raw) {
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
function normalizeKnobs(raw) {
  if (Array.isArray(raw)) {
    return raw.filter(p => p && typeof p === 'object')
      .map(p => ({ k: String(p.k === null || p.k === undefined ? '' : p.k),
                   v: String(p.v === null || p.v === undefined ? '' : p.v) }));
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
function normalizeLegendItem(item) {
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
function cloneLegend(arr) {
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
function registryFingerprint(rows) {
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
function buildLegendRegistryUpdates(refTable, mapKey, legendArr, user, nowStr) {
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
function parseLegendRegistryRows(result, dedupeByValue) {
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
function getMissingDescValues(pushedValues, legendArr) {
  return (pushedValues || []).filter(v => {
    const item = (legendArr || []).find(l => String(l.value) === String(v));
    return !item || !(item.desc || '').trim();
  });
}

function formatLegendMetaText(meta) {
  if (!meta || (!meta.updated_by && !meta.updated_at)) return '서버 미저장';
  return `${meta.updated_by || 'system'} · ${meta.updated_at || ''}`;
}

// ---------------------------------------------------------------------------
// [7b] Canonical key values — THE client-side half of map identity.
//
// Production defect (2026-07-28): a `number`-declared slot column stores 1, so the identity
// registered in wafer_map_metadata reads 'LOT_1' — while a parsed material token supplies
// '01' (and a Float column round-trips '1.0'). Composing with the raw value then misses
// silently: the cell data opens (crud casts data filters by declared column type) while the
// meta lookup returns nothing, so the map "has no spec" and alignment degrades to identity.
//
// The server half is live (`map_overlay.canonical_key_value`, `ab6ac02`). THIS IS THE MIRROR
// OF THAT FUNCTION and the two must agree value-for-value — the whole defect was the two
// sides disagreeing. Do not fork it, and do not add a second canonicalisation anywhere in
// the client: `composeMapId` / `decomposeMapKey` / `canonicalMapKey` are its only use forms.
//
// Known deliberate deviations from the Python (none of them key-shaped values):
//   · a JS boolean stringifies 'true', Python 'True'.
//   · Python accepts underscore digit separators ('1_0' -> '10'); '_' is the key separator
//     here, so a part can never legitimately contain one and we preserve the original.
//   · integers beyond Number.MAX_SAFE_INTEGER: the digit walk below is exact for any length,
//     but a value that arrived as a JS number was already lossy before we saw it.
// ---------------------------------------------------------------------------

const CANON_INT_RE = /^[+-]?[0-9]+$/;
// DECIMAL floats only. `Number('0x10')` is 16 while Python's `float('0x10')` raises, so
// using Number() as the readability test would canonicalise '0x10' to '16' — inventing a
// value the server never stores. Unreadable must stay unreadable (trimmed original).
const CANON_FLOAT_RE = /^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/;

// str(int(s)) without parseInt — exact for arbitrarily long digit strings.
function canonIntString(s) {
  const neg = s[0] === '-';
  let d = (s[0] === '+' || s[0] === '-') ? s.slice(1) : s;
  d = d.replace(/^0+/, '');
  if (d === '') d = '0';
  return (neg && d !== '0') ? `-${d}` : d;
}

// Value + DECLARED column type -> canonical key string.
//   · "number": integer-parse ('01' / ' 1 ' / '1.0' are the same key). A non-integral numeric
//     keeps its repr ('7.5'); an UNREADABLE value keeps its trimmed original — the lookup
//     misses honestly instead of inventing a key.
//   · anything else (string / undeclared): trimmed as-is. Padding may be meaningful.
//   · null/undefined stay null (composition sites decide their own placeholder).
function canonicalKeyValue(value, colType) {
  if (value === null || value === undefined) return null;
  if (colType === 'number' && typeof value !== 'boolean') {
    if (typeof value === 'number') {
      if (Number.isFinite(value) && Number.isInteger(value)) return String(value);
      return String(value).trim();
    }
    const s = String(value).trim();
    if (CANON_INT_RE.test(s)) return canonIntString(s);
    if (CANON_FLOAT_RE.test(s)) {
      const f = Number(s);
      if (Number.isFinite(f) && Number.isInteger(f)) return String(f);
    }
    return s;
  }
  if (typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value)) {
    // A float VALUE is numeric regardless of the declared type — '3.0' is a repr artifact,
    // not data (mirrors the server, which pinned this against crud.clean_str_value).
    return String(value);
  }
  return String(value).trim();
}

// Identity components joined with '_'. Each component is canonicalised by the DECLARED type
// of its column, because the meta row being looked up was registered from that column's
// stored value and must be composed the same way.
function composeMapId(keyColumns, values, columnTypes) {
  const types = columnTypes || {};
  const vals = values || {};
  return (Array.isArray(keyColumns) ? keyColumns : []).map(k => {
    const v = canonicalKeyValue(vals[k], types[k]);
    return (v === null || v === undefined) ? '' : String(v);
  }).join('_');
}

// The inverse of composeMapId — mirrors the server's `build_key_filters` split exactly:
// the LAST column absorbs the remainder, so a lot name containing '_' survives.
function decomposeMapKey(keyColumns, mapKey, columnTypes) {
  const cols = Array.isArray(keyColumns) ? keyColumns : (keyColumns ? [keyColumns] : []);
  const types = columnTypes || {};
  const out = {};
  if (cols.length === 0) return out;
  const key = String(mapKey === null || mapKey === undefined ? '' : mapKey);
  const parts = key.split('_');
  if (parts.length < cols.length) {
    // Undecomposable — match the whole key against the first column (server parity).
    out[cols[0]] = canonicalKeyValue(key, types[cols[0]]);
    return out;
  }
  const head = parts.slice(0, cols.length - 1);
  const tail = parts.slice(cols.length - 1).join('_');
  [...head, tail].forEach((v, i) => { out[cols[i]] = canonicalKeyValue(v, types[cols[i]]); });
  return out;
}

// A map key string in its canonical spelling. Decompose then recompose — the round-trip
// identity is exactly what makes this idempotent, so applying it twice cannot drift.
function canonicalMapKey(keyColumns, mapKey, columnTypes) {
  const cols = Array.isArray(keyColumns) ? keyColumns : [];
  const raw = String(mapKey === null || mapKey === undefined ? '' : mapKey);
  if (cols.length === 0 || raw === '') return raw;
  const parts = decomposeMapKey(cols, raw, columnTypes);
  // Undecomposable: decomposeMapKey put the WHOLE key on the first column. Recomposing
  // would append empty tails and invent a different key, so return that single canonical
  // form instead — the honest answer for a key that does not fit the declared shape.
  if (Object.keys(parts).length < cols.length) {
    const only = parts[cols[0]];
    return (only === null || only === undefined) ? raw : String(only);
  }
  return composeMapId(cols, parts, columnTypes);
}

function getMapIdFromMeta(metaDict) {
  if (!metaDict) return 'default_map';

  let mapKeyCols = tableSchema.map_key_columns;
  if (!mapKeyCols || !Array.isArray(mapKeyCols) || mapKeyCols.length === 0) {
    if (tableSchema.composite_key_source && Array.isArray(tableSchema.composite_key_source)) {
      mapKeyCols = tableSchema.composite_key_source.filter(col => !['x', 'y', 'val', 'die_id', 'code', 'grid_metadata'].includes(col.toLowerCase()));
    }
  }

  // [7b] The declared types come from the SAME table whose rows registered the meta row, so
  // composing here canonicalises identically to the registration side. Columns the user left
  // blank are dropped before composing (long-standing behaviour — a blank must not become an
  // empty component), so composeMapId is fed only the columns that are actually present.
  const colTypes = (tableSchema && tableSchema.column_types) || {};
  if (mapKeyCols && mapKeyCols.length > 0) {
    const present = mapKeyCols.filter(col => {
      const v = metaDict[col];
      return v !== undefined && v !== null && String(v).trim() !== '';
    });
    if (present.length > 0) return composeMapId(present, metaDict, colTypes);
  }

  const allCols = Object.keys(metaDict).filter(col => {
    const v = metaDict[col];
    return v !== undefined && v !== null && String(v).trim() !== '';
  });
  return allCols.length > 0 ? composeMapId(allCols, metaDict, colTypes) : 'default_map';
}

function debounce(func, wait = 200) {
  let timeout;
  return function(...args) {
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
  
  el.presetSelect = document.getElementById('preset-select');
  el.btnSavePreset = document.getElementById('btn-save-preset');
  el.btnDeletePreset = document.getElementById('btn-delete-preset');
  // [M4②] 유효 다이 지정 — 물리 규격 블록의 한 줄. 오버레이 소스 선택기와 같은 이유로
  // **별도 DOM**이다: 이쪽을 조작해도 switchTable/selectedTable/gridData는 건드리지 않는다.
  el.validDieRefTable = document.getElementById('valid-die-ref-table');
  el.validDieRefKey = document.getElementById('valid-die-ref-key');
  el.validDieRefList = document.getElementById('valid-die-ref-list');
  
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

  // Fit the (square) grid to the available workspace on any size change.
  // ResizeObserver also covers container-only resizes (split panels) that window 'resize' misses.
  window.addEventListener('resize', fitGridToWorkspace);
  if (window.ResizeObserver && el.mapWorkspace) {
    new ResizeObserver(() => fitGridToWorkspace()).observe(el.mapWorkspace);
  }
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
  // [M4②] 지정 칸. `change`(blur/Enter)에서만 재해석한다 — 타이핑마다 네트워크를 타면
  // 조회 동선에 마찰이 생긴다. 자동완성 목록은 포커스 시 1회 지연 로드한다.
  if (el.validDieRefKey) {
    el.validDieRefKey.addEventListener('change', onValidDieRefChanged);
    el.validDieRefKey.addEventListener('focus', populateValidDieRefList);
  }
  if (el.validDieRefTable) {
    el.validDieRefTable.addEventListener('change', () => {
      validDieRefTableTouched = true;   // [F1] 의도는 **오직 여기서만** 세워진다
      populateValidDieRefList();
      // 키가 비어 있으면 테이블만 바꾼 것은 아직 선언이 아니다 — 해석하지 않는다.
      if (el.validDieRefKey && el.validDieRefKey.value.trim() !== '') onValidDieRefChanged();
    });
  }
  fetchAndRenderPresets();
  
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
  if (el.btnCopyExcel) el.btnCopyExcel.addEventListener('click', copyGridToExcel);

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
  [el.physWaferDia, el.physChipX, el.physChipY, el.physOffsetX, el.physOffsetY, el.physEdgeMargin].forEach(input => {
    if (input) {
      input.addEventListener('change', () => scheduleRenderGridCanvas());
      input.addEventListener('input', () => scheduleRenderGridCanvas());
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

  const box = getWaferBoundingBox(currentRotation, currentSide);
  const c_zero = box.minC - startX;
  const r_zero = !invertY ? (box.minR - startY) : (box.maxR + startY);
  const hasZeroZero = (c_zero >= 0 && c_zero < visualCols) && (r_zero >= 0 && r_zero < visualRows);

  const physical = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
  const visual = getVisualCoords(c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
  const coordKey = `${physical.x}_${physical.y}`;

  const isOriginCell = hasZeroZero 
    ? (visual.x === 0 && visual.y === 0) 
    : (visual.x === startX && visual.y === startY);

  // [M4①] 유효 다이 판정. 참조가 없으면 `isValidDieAt`이 원 판정을 그대로 돌려주므로
  // 선언 없는 맵의 동작은 `2a9f6c4`와 한 글자도 다르지 않다.
  const completelyInside = isValidDieAt(physical.x, physical.y,
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

  const physConfig = getTransformedPhysicalConfig(currentRotation, currentSide);
  const cellW = rect.width / visualCols;
  const cellH = rect.height / visualRows;
  const { shiftX, shiftY } = getScreenShift(physConfig, cellW, cellH);

  const c = Math.floor((xRel - shiftX) / cellW);
  const r = Math.floor((yRel - shiftY) / cellH);

  if (c >= 0 && c < visualCols && r >= 0 && r < visualRows && gridCells2D[r]?.[c]) {
    return gridCells2D[r][c];
  }

  return getGridCellObject(c, r, visualCols, visualRows, physConfig, rect.width, rect.height);
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
        // [M4②] 유효 다이 지정의 테이블 칸도 같은 목록이다. 첫 옵션(값 '')은
        // "이 맵의 테이블 승계" = 선언을 **문자열 형태**로 저장하는 경로이며,
        // 이음매 벡터 `string_inherits_home_table`이 그 형태를 고정하고 있다.
        if (el.validDieRefTable) {
          el.validDieRefTable.innerHTML = '<option value="">(이 맵의 테이블)</option>';
          mapTables.forEach(table => {
            const o = document.createElement('option');
            o.value = table;
            o.textContent = table;
            el.validDieRefTable.appendChild(o);
          });
        }
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
      clearOverlayLayers();
      showToast('테이블이 바뀌어 오버레이를 해제했습니다.', 'info');
    }

    // 테이블이 바뀌면 이전 맵의 정체성 핀은 무효다 (Push 대상이 달라진다)
    setLoadedIdentity(null, null);
    // [M4①] 유효 다이 마스크도 이전 맵의 것이다 — 위 ⓑ가 오버레이에 적용되는 이유와
    // 똑같이 적용된다. 남겨 두면 새 테이블의 격자가 남의 마스크로 재단된다.
    validDie = { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };
    renderValidDieChip();
    // [M4②] 지정 칸도 이전 맵의 것이다. 남겨 두면 다음 Push가 **남의 선언**을 이 맵에 쓴다.
    syncValidDieRefControls();
    // 새 테이블의 자동완성 캐시를 버려 다음 포커스에서 다시 읽게 한다 — 전환 중에 그 테이블에
    // 맵이 추가됐을 수 있고, 자동완성이 없는 것보다 **없는 맵을 제안하는 것**이 나쁘다.
    validDieListCache.delete(tableName);
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
    
    formGroup.appendChild(label);
    formGroup.appendChild(input);
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
  // (dropdown title) + a toast. No new control.
  if (served && served.source === 'fallback_guess') {
    el.colMapVal.title = `값 컬럼 '${served.val}'은(는) 추측입니다 — map_overlay_config.table_bindings에 선언하십시오.`;
    showToast(
      `${selectedTable}: 값 컬럼 '${served.val}'은(는) 후보에 없어 추측으로 선택했습니다 — `
      + `map_overlay_config.table_bindings에 선언을 권장합니다.`,
      'warning', { dedupeKey: `binding_guess_${selectedTable}` });
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
// ⚠️ 동기 실행 전용. fn 안에서 await 하면 그 사이 다른 코드가 뒤집힌 프레임을 보게 된다.
let physFrameOverride = null;

// 기존 규약 `parseFloat(input.value) || 기본값`을 그대로 유지한다(0 → 기본값).
function physNum(key, domEl, dflt) {
  if (physFrameOverride && physFrameOverride[key] !== undefined && physFrameOverride[key] !== null) {
    const ov = parseFloat(physFrameOverride[key]);
    if (Number.isFinite(ov)) return ov || dflt;
  }
  const v = domEl ? parseFloat(domEl.value) : NaN;
  return v || dflt;
}

function gridDimNum(key, domEl, dflt) {
  if (physFrameOverride && physFrameOverride[key] !== undefined && physFrameOverride[key] !== null) {
    const ov = parseInt(physFrameOverride[key], 10);
    if (Number.isFinite(ov)) return ov || dflt;
  }
  const v = parseInt(domEl ? domEl.value : '', 10);
  return v || dflt;
}

function withPhysFrame(frame, fn) {
  const prev = physFrameOverride;
  physFrameOverride = frame || null;
  try { return fn(); } finally { physFrameOverride = prev; }
}

function getPhysicalCoords(colVisual, rowVisual, cols, rows, rotation, side) {
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // ⚠️ Do not read the physical spec (chip/offset) straight from the DOM here — that bypasses
  //    the frame window (physFrameOverride) and would silently contaminate source-frame math
  //    with on-screen values. Go through physNum() if you ever need them.
  //    (Four unused leftovers were removed: this is a per-cell, per-frame hot path, so their
  //     four parseFloat calls were pure waste.)

  // Get screen-space shift for the current rotation in cell units
  const physConfig = getTransformedPhysicalConfig(rotation, side);
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

  // Convert back to physical grid coordinate (xp, yp)
  const xp = Math.round(xRot + (cols - 1) / 2.0);
  const yp = Math.round(yRot + (rows - 1) / 2.0);

  return { x: xp, y: yp };
}

function getCellFromPhysicalCoords(xp, yp, cols, rows, rotation, side) {
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  let xRot = xp - (cols - 1) / 2.0;
  let yRot = yp - (rows - 1) / 2.0;

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
  const physConfig = getTransformedPhysicalConfig(rotation, side);
  const { shiftX, shiftY } = getScreenShift(physConfig, 1.0, 1.0);

  const colVisual = xScreenWafer + (visualCols - 1) / 2.0 - shiftX;
  const rowVisual = yScreenWafer + (visualRows - 1) / 2.0 - shiftY;

  return { c: Math.round(colVisual), r: Math.round(rowVisual) };
}

function getCellFromVisualCoords(xv, yv, cols, rows, rotation, side, invertY, startX, startY) {
  const box = getWaferBoundingBox(rotation, side);
  
  const c = xv - startX + box.minC;

  let r = 0;
  if (!invertY) {
    r = yv - startY + box.minR;
  } else {
    r = box.maxR - (yv - startY);
  }

  return { c, r };
}

let boundingBoxCache = {};

function getWaferBoundingBox(rotation, side) {
  // 프레임 창이 열려 있으면 소스 메타 값이, 아니면 화면 컨트롤 값이 읽힌다.
  // 캐시 키를 해석된 실값으로 만들어야 두 프레임의 바운딩박스가 서로를 덮어쓰지 않는다.
  const dia = physNum('waferDia', el.physWaferDia, 300);
  const cx = physNum('chipX', el.physChipX, 2.5);
  const cy = physNum('chipY', el.physChipY, 2.5);
  const ox = physNum('offsetX', el.physOffsetX, 0.0);
  const oy = physNum('offsetY', el.physOffsetY, 0.0);
  const em = physNum('edgeMargin', el.physEdgeMargin, 3.0);

  const cols = gridDimNum('cols', el.gridCols, 10);
  const rows = gridDimNum('rows', el.gridRows, 10);
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  const key = `${rotation}_${side}_${visualCols}_${visualRows}_${dia}_${cx}_${cy}_${ox}_${oy}_${em}`;
  if (boundingBoxCache[key]) {
    return boundingBoxCache[key];
  }

  const physConfig = getTransformedPhysicalConfig(rotation, side);
  const width = 700;
  const height = 700;

  let minC = 9999, maxC = -9999;
  let minR = 9999, maxR = -9999;
  let insideCount = 0;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      if (isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height)) {
        insideCount++;
        if (c < minC) minC = c;
        if (c > maxC) maxC = c;
        if (r < minR) minR = r;
        if (r > maxR) maxR = r;
      }
    }
  }

  const box = {
    minC: minC === 9999 ? 0 : minC,
    maxC: maxC === -9999 ? 0 : maxC,
    minR: minR === 9999 ? 0 : minR,
    maxR: maxR === -9999 ? 0 : maxR
  };

  boundingBoxCache[key] = box;
  return box;
}

function getVisualCoords(colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY) {
  const box = getWaferBoundingBox(rotation, side);

  const xv = colVisual - box.minC + startX;

  let yv = 0;
  if (!invertY) {
    yv = rowVisual - box.minR + startY;
  } else {
    yv = box.maxR - rowVisual + startY;
  }

  return { x: xv, y: yv };
}

function getTransformedPhysicalConfig(currentRotation, currentSide) {
  const waferDia = physNum('waferDia', el.physWaferDia, 300);
  const edgeMargin = physNum('edgeMargin', el.physEdgeMargin, 3.0);
  const effectiveRadius = Math.max(0, (waferDia / 2.0) - edgeMargin);
  const origChipX = physNum('chipX', el.physChipX, 2.5);
  const origChipY = physNum('chipY', el.physChipY, 2.5);
  let origOffsetX = physNum('offsetX', el.physOffsetX, 0.0);
  let origOffsetY = physNum('offsetY', el.physOffsetY, 0.0);

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
  const physConfig = getTransformedPhysicalConfig(currentRotation, currentSide);
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
//    `getVisualCoords`가 그걸로 **DB에 저장되는 x/y**를 만든다. 유효 다이 집합을 bbox에
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

// [M4② F1] 테이블 select의 현재 값이 **사용자의 의도**인가. `change` 리스너에서만 참이 되고
// `syncValidDieRefControls`(앱이 raw로 되맞추는 자리)에서만 거짓이 된다.
// 🔴 이 플래그가 필요한 이유: 선언된 테이블이 목록에 없으면(스키마 조회 1회 실패·권한·오타)
//    sync가 select를 ''로 **강제**한다. 그 ''를 "사용자가 홈 테이블로 바꿨다"로 읽으면
//    아무것도 건드리지 않은 Push가 선언된 테이블을 조용히 지운다 — 홈 테이블에 같은 키가
//    있으면 **다른 맵**이 유효 다이 기준이 되고 화면은 정상으로 보인다.
//    앱이 스스로 강제한 컨트롤 값에서 의도를 유추하지 않는다.
let validDieRefTableTouched = false;

// [M4② F3] 유효 다이 해석의 **세대 번호**. `overlaySeq`와 같은 프리미티브다(§오버레이).
// ①에서는 로드가 한 번 await하는 게 전부였지만 ②에서 해석이 **사용자 주도로 반복** 호출되므로
// 늦게 도착한 해석이 새 상태를 덮는 경로가 생겼다: `TPL_A`(느림) → `TPL_B`(빠름) 순서로
// 시작하면 A가 나중에 착지해 basis도 입력칸도 A로 되돌리고 Push가 A를 쓴다.
// 상태를 갈아치우는 쪽(`resolveValidDie` 진입 · 저작 진입)이 이 번호를 올리고,
// 착지 시점에 자기 번호가 낡았으면 **아무것도 하지 않는다**(last-write-wins가 아니라 최신-승).
let validDieResolveSeq = 0;

// 선언의 해석. **순수 함수** — 네트워크를 타지 않으므로 계약 벡터로 바로 채점된다.
// 반환: null(선언 없음) | {table, mapKey} | {unreadable: true, reason}
//
// 규칙 하나로 말하면: **`null`/부재만 "선언 없음"이고, 그 외에는 전부 선언이다.**
// 읽을 수 없는 선언을 "선언 없음"으로 접으면 오타 하나가 조용히 원 기하로 되돌아간다 —
// 틀린 답과 맞는 답이 구별되지 않는 바로 그 상태다.
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
    return { table: home, mapKey: s };
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
  const table = (t === null || t === undefined || String(t).trim() === '') ? home : String(t).trim();
  if (!table) return bad('valid_die_ref의 대상 테이블을 알 수 없습니다.');
  return { table, mapKey: key };
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
// `physFrameOverride`가 열려 있으면 마스크를 적용하지 않는다: 프레임 창 안의 계산은
// **소스 맵의 좌표계**를 푸는 중이고, 거기에 타깃 맵의 유효 다이 집합을 먹이면
// 조용히 다른 맵의 마스크로 소스를 재단하게 된다.
//
// 🔴 `ref`는 원과 **교집합하지 않는다**. 교집합은 보수적으로 보이지만 템플릿이 유효하다고
//    선언한 다이를 조용히 버린다 — INV-M4-2가 막는 결함이 정확히 그것이다.
// `state`는 `validDieBasis`와 같은 선택 인자다(읽는 지점만 바뀐다, 쓰지 않는다).
function isValidDieAt(physX, physY, circleInside, state) {
  if (physFrameOverride) return circleInside;
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
// 🔴 **새 기하식은 한 줄도 없다.** 물리 좌표는 렌더·로드·오버레이가 쓰는 그 `getPhysicalCoords`,
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
  const cols = gridDimNum('cols', el.gridCols, 10);
  const rows = gridDimNum('rows', el.gridRows, 10);
  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  const physConfig = getTransformedPhysicalConfig(currentRotation, currentSide);
  const width = el.gridCanvas ? Math.floor(el.gridCanvas.getBoundingClientRect().width || 700) : 700;
  const height = el.gridCanvas ? Math.floor(el.gridCanvas.getBoundingClientRect().height || 700) : 700;

  const keys = new Set();
  const filled = [];
  let outsideCircle = 0;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      const p = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
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
// 화면 컨트롤 두 칸이 **뜻하는** 지정. 읽는 곳이 둘(Push 결정 · 즉시 재해석)이므로
// 같은 수를 두 곳에서 만들지 않기 위해 여기 하나로 모은다.
// [F1] 테이블은 사용자가 select를 건드렸을 때만 컨트롤에서 읽는다. 건드리지 않았으면
//      **저장된 원문이 말하는 테이블**이 여전히 사용자의 지정이다(위 플래그 주석 참조).
function validDieRefFromControls() {
  const shown = validDieRefDisplay(validDie ? validDie.raw : undefined);
  const key = (el.validDieRefKey && el.validDieRefKey.value ? el.validDieRefKey.value : '').trim();
  const table = validDieRefTableTouched
    ? (el.validDieRefTable && el.validDieRefTable.value ? el.validDieRefTable.value : '').trim()
    : shown.table;
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

  cols = Math.max(5, Math.min(100, cols));
  rows = Math.max(5, Math.min(100, rows));

  if (el.gridCols) el.gridCols.value = cols;
  if (el.gridRows) el.gridRows.value = rows;

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
  if (preset.phys_offset_x !== undefined && el.physOffsetX) el.physOffsetX.value = preset.phys_offset_x;
  if (preset.phys_offset_y !== undefined && el.physOffsetY) el.physOffsetY.value = preset.phys_offset_y;
  if (preset.phys_edge_margin !== undefined && el.physEdgeMargin) el.physEdgeMargin.value = preset.phys_edge_margin;

  if (preset.rotation !== undefined) currentRotation = preset.rotation;
  if (preset.side !== undefined) currentSide = preset.side;

  boundingBoxCache = {};
  updateOrientationUI();
  applyPhysicalGeometry();
  scheduleRenderGridCanvas();
  updateLegendCounts();
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
      showToast(`규격 프리셋 '${presetName}' 저장 완료`, 'success');
    } else {
      const errorData = await res.json().catch(() => ({ detail: res.statusText }));
      alert(`Failed to save custom geometry preset: ${errorData.detail || res.statusText}`);
    }
  } catch (err) {
    console.error('[Map Presets] Error saving preset:', err);
    alert(`Error saving custom preset to server: ${err.message}`);
  }
}

async function deleteCustomPreset() {
  if (!el.presetSelect) return;
  const val = el.presetSelect.value;
  if (!val) return;

  const preset = serverPresets[val];
  if (!preset || !preset.is_custom) return;

  if (!confirm(`Are you sure you want to delete custom preset '${preset.name}' from server?`)) return;

  try {
    const res = await fetch(`${API_BASE}/api/map-presets/${val}`, {
      method: 'DELETE'
    });

    if (res.ok) {
      await fetchAndRenderPresets();
      el.presetSelect.value = '';
      if (el.btnDeletePreset) el.btnDeletePreset.style.display = 'none';
      showToast(`규격 프리셋 '${preset.name}' 삭제 완료`, 'success');
    } else {
      const errorData = await res.json().catch(() => ({ detail: res.statusText }));
      alert(`Failed to delete preset from server: ${errorData.detail || res.statusText}`);
    }
  } catch (err) {
    console.error('[Map Presets] Error deleting preset:', err);
    alert(`Error deleting preset from server: ${err.message}`);
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

  const box = getWaferBoundingBox(currentRotation, currentSide);
  const isXMirrored = (currentSide === 'back' && !isRotated90or270);
  const isYMirrored = (currentSide === 'back' && isRotated90or270);

  const c_zero = isXMirrored ? (box.maxC + startX) : (box.minC - startX);
  let r_zero = 0;
  if (!invertY) {
    r_zero = !isYMirrored ? (box.minR - startY) : (box.maxR + startY);
  } else {
    r_zero = !isYMirrored ? (box.maxR + startY) : (box.minR - startY);
  }
  const hasZeroZero = (c_zero >= 0 && c_zero < visualCols) && (r_zero >= 0 && r_zero < visualRows);

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

  const cellW = width / visualCols;
  const cellH = height / visualRows;

  const tStart = performance.now();

  const physConfig = getTransformedPhysicalConfig(currentRotation, currentSide);
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

  const startC = Math.min(-visualCols, Math.floor(-shiftX / cellW) - 2);
  const endC = Math.max(2 * visualCols, Math.ceil((width - shiftX) / cellW) + 2);
  const startR = Math.min(-visualRows, Math.floor(-shiftY / cellH) - 2);
  const endR = Math.max(2 * visualRows, Math.ceil((height - shiftY) / cellH) + 2);

  for (let r = startR; r <= endR; r++) {
    for (let c = startC; c <= endC; c++) {
      const x0 = c * cellW + shiftX;
      const y0 = r * cellH + shiftY;

      if (x0 + cellW < 0 || x0 > width || y0 + cellH < 0 || y0 > height) continue;

      // [M4①] 물리 좌표는 아래에서 어차피 만든다. 판정에 필요하므로 여기로 끌어올렸다 —
      // 판정용 좌표를 따로 만들면 같은 좌표의 계산이 둘이 된다.
      const physical = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
      const completelyInside = isValidDieAt(physical.x, physical.y,
        isCellInsideWaferFast(c, r, visualCols, visualRows, physConfig, width, height));
      const isMatrixCell = completelyInside || (c >= -visualCols && c < 2 * visualCols && r >= -visualRows && r < 2 * visualRows);

      if (!isMatrixCell) {
        ctx.fillStyle = C.outBg;
        ctx.fillRect(x0, y0, cellW, cellH);
        ctx.strokeStyle = C.line;
        ctx.lineWidth = 0.5;
        ctx.strokeRect(x0, y0, cellW, cellH);
        continue;
      }

      const visual = getVisualCoords(c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
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

  // 6. Physical Wafer Circles (FIXED at Wafer Center 0,0 at Canvas Center)
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
    const boxX = minC * cellW + shiftX;
    const boxY = minR * cellH + shiftY;
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
    const hX = currentHoverCell.c * cellW + shiftX;
    const hY = currentHoverCell.r * cellH + shiftY;
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
    const box = getWaferBoundingBox(currentRotation, currentSide);
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
const DRAFT_VERSION = 3;

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
    await loadExistingMap({ quiet: true });
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
  const mapKey = getMapIdFromMeta(dict);
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

// What a legend row LOOKS like, ignoring who last wrote it. `canonRegistryRow` is the
// one normal form in this file; `eventtime` is dropped because it is server bookkeeping,
// not something the user typed - comparing it would make every row look edited.
function legendRowSignature(item) {
  const c = canonRegistryRow(item);
  // The SAME list the write payload is built from. Not a hand-picked subset: a field that
  // is saved but not signed here is a field whose edit is silently dropped from the save.
  return LEGEND_PAYLOAD_COLUMNS.map(k => c[k]).join(FP_UNIT);
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
    draftBase = { table: selectedTable, mapKey, registryFp: legendReplaceScope.fingerprint,
                  cellsFp: cellsDigest(gridData) };
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
  'zone-columns-missing': '서버 DOE 저장소에 층 구조(STACK·1H·MID·TOP) 컬럼이 아직 없습니다 — 지금 저장하면 그 컬럼들이 버려진 채 계획 전체가 교체되어 **층 구조가 사라집니다.** 그래서 저장하지 않았습니다. 서버가 갱신되면 자동으로 다시 시도합니다.',
  'legacy-unreadable': '이 계획에는 새 층 구조로 옮길 수 없는 **폐기된 구간 배치**가 남아 있습니다 — 지금 저장하면 그 구간들이 3구역으로 뭉개진 채 서버 원본을 덮어 **지금 남아 있는 정보가 사라집니다.** 그래서 저장하지 않았습니다. 해당 값의 STACK·구역을 직접 채우면 풀립니다.',
  'unknown-server-state': '서버 DOE 상태를 확인하지 못해 **저장을 보류**했습니다 — 편집은 이 브라우저에만 있습니다. 맵을 다시 열면 재시도합니다.',
  conflict: '다른 사람이 이 계획을 변경했습니다 — 저장하지 않았습니다. 맵을 다시 불러온 뒤 편집하십시오.',
  adopted: '서버에 저장된 계획을 불러왔습니다. 그 사이 편집한 내용은 서버에 반영되지 않았습니다.',
  error: 'DOE·legend 서버 저장 실패 — 이 편집은 팀에 공유되지 않았습니다 (로컬 초안만).',
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
        showToast('중복된 범례 값이 존재합니다.', 'warning');
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
    console.warn(`[Map Editor] wafer_map_metadata 중복: ${table} · ${mapId} — ${rows.length}건`);
    showToast(`맵 규격 레코드가 중복되어 있습니다 (${table} · ${mapId}) — 첫 행을 적용합니다.`, 'warning');
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
async function loadExistingMap(opts = {}) {
  const quiet = !!opts.quiet;
  // [M4①] 이전 맵의 유효 다이 마스크를 먼저 버린다. 이 로드가 어느 경로로 끝나든
  // — 취소·0건·예외 — 남은 마스크가 **다른 맵**의 유효 다이를 주장하는 일이 없어야 한다.
  // 성공 경로는 아래에서 이 맵의 선언으로 다시 세운다.
  validDie = { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };
  renderValidDieChip();
  syncValidDieRefControls();   // [M4②] 지정 칸도 함께 비운다 — 아래 성공 경로가 다시 세운다
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

  if (!hasFilter) {
    if (quiet) showToast('맵 키가 비어 있어 로드할 수 없습니다.', 'warning');
    else alert('기존 맵 데이터를 로드하기 위해 하나 이상의 메타데이터 필드 값을 입력하십시오.');
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
    // 기준 맵이 통째로 바뀌므로 이전 맵 기준으로 정렬된 오버레이는 무효다
    if (overlayLayers.length > 0) {
      clearOverlayLayers();
      showToast('기준 맵이 교체되어 오버레이를 해제했습니다.', 'info');
    }
    let count = 0;
    
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

    let loadedGridMeta = null;
    let loadedMapKey = null; // split registry 적용을 위해 맵 식별자를 함수 스코프로 유지

    // 1. Try fetching from dedicated wafer_map_metadata table
    try {
      const filterMetaDict = {};
      Object.keys(filterModel).forEach(col => {
        if (filterModel[col] && filterModel[col].filter) {
          filterMetaDict[col] = filterModel[col].filter;
        }
      });
      const mapIdStr = getMapIdFromMeta(filterMetaDict);
      if (mapIdStr && mapIdStr !== 'default_map') {
        loadedMapKey = mapIdStr;
        loadedGridMeta = await fetchGridMetaFor(selectedTable, mapIdStr);
      }
    } catch (e) {
      console.warn('[Map Editor] Dedicated wafer_map_metadata table fetch skipped:', e);
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

    let userChoice = null; // 'standard' | 'current' | 'meta'

    // 자동 로드(프레임 진입)에서 조회 결과가 0건이면 좌표계 선택 모달을 띄우지 않는다 —
    // 아직 만들지 않은 자재 맵이므로 물어볼 좌표가 없다.
    if (opts.allowEmpty && minX === 9999 && !loadedGridMeta) {
      // [F4] "not built yet" is only true when the table really had no rows. Rows that
      // exist but yielded no parseable coordinate are a column-selection problem and
      // must be said out loud, not folded into "empty map".
      if (fetchedRows > 0) {
        showToast(
          `${selectedTable}: ${fetchedRows}행을 받았지만 좌표로 해석된 셀이 0개입니다. x/y 컬럼 선택을 확인하세요.`,
          'warning');
      }
      return { count: 0, empty: true };
    }

    if (!loadedGridMeta && minX !== 9999) {
      // Choice modal triggers for maps with no grid metadata records
      userChoice = await new Promise((resolve) => {
        // [fix C] The default's behavior changed (data bounding box, no mask in
        // effect) — keep the highlighted button honest. Label set here in JS because
        // the semantics it describes are decided in this branch (JS-only fix batch).
        el.btnChoiceStandard.textContent = '📐 표준 — 데이터 전체 사각 격자 (마스크 없음, Rot 0°)';
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

        const cleanup = () => {
          el.choiceModal.style.display = 'none';
          el.btnChoiceStandard.removeEventListener('click', onStandard);
          el.btnChoiceCurrent.removeEventListener('click', onCurrent);
          el.btnChoiceCancel.removeEventListener('click', onCancel);
        };

        el.btnChoiceStandard.addEventListener('click', onStandard);
        el.btnChoiceCurrent.addEventListener('click', onCurrent);
        el.btnChoiceCancel.addEventListener('click', onCancel);
      });

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

    // Determine grid properties based on choice
    let cols, rows, startX, startY, invertY, rotation, side;

    if (userChoice === 'standard') {
      cols = (maxX >= minX) ? (maxX - minX + 1) : 10;
      rows = (maxY >= minY) ? (maxY - minY + 1) : 10;
      startX = 0;
      startY = 0;
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

      boundingBoxCache = {};
    } else {
      // Use current UI settings
      cols = parseInt(el.gridCols.value, 10) || 10;
      rows = parseInt(el.gridRows.value, 10) || 10;
      startX = parseInt(el.gridStartX.value, 10) || 0;
      startY = parseInt(el.gridStartY.value, 10) || 0;
      invertY = el.gridYInvert.checked;
      rotation = currentRotation;
      side = currentSide;
    }

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

            // If standard system was selected, shift coordinates so minX, minY maps to 0,0
            if (userChoice === 'standard') {
              xNum = xNum - minX;
              yNum = yNum - minY;
            }

            const cell = getCellFromVisualCoords(xNum, yNum, cols, rows, rotation, side, invertY, startX, startY);
            const c = cell.c;
            const r = cell.r;

            const physical = getPhysicalCoords(c, r, cols, rows, rotation, side);
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

    // Auto detect legend from unique values
    if (uniqueVals.size > 0) {
      const predefinedColors = LEGEND_PALETTE; // [U6] the one palette — no second copy
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
            chosenColor = '#' + Math.floor(Math.random()*16777215).toString(16).padStart(6, '0');
          }

          usedColors.add(chosenColor);
          newLegend.push(normalizeLegendItem({
            value: v,
            desc: dr ? String(dr.desc || '') : (v === '1' ? 'GOOD' : (v === '0' ? 'FAIL' : `BIN ${v}`)),
            color: chosenColor
          }));
        }
      });

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

        // ── 초안 우선순위 ────────────────────────────────────────────────────
        // 저장되지 못한 편집(차단 검증에 걸린 계획이 대표적이다)은 브라우저에만 있다.
        // 기반 지문이 그대로면 그 사이 아무도 쓰지 않았으므로 초안이 더 새 것이다.
        // 어긋나면 **누가 썼다** — 적용하면 남의 저장을 지운다. 적용하지 않고, 버리지도 않고,
        // 사실을 드러낸다.
        let staleDraftKept = false;   // [fix A] see the persist below
        const draft = readDoeDraft(selectedTable, loadedMapKey);
        if (draft) {
          const doeFresh = draft.registryFp !== null && draft.registryFp === serverFp;
          const cellsFresh = draft.cellsFp !== null && draft.cellsFp === serverCellsFp;
          const restoredDoe = doeFresh ? applyDoeDraftRecord(draft) : false;
          const restoredCells = cellsFresh ? applyDraftCells(draft.cells) : 0;
          if (restoredDoe || restoredCells > 0) {
            // Restored edits are still unsaved edits - they exist only in this browser
            // until [⚡ Push]. Without this the chip reads "saved" after the very refresh
            // the draft just survived.
            legendDirty = true;
            showToast(`저장되지 않은 편집을 복구했습니다 — ${restoredDoe ? 'DOE' : ''}`
              + `${restoredDoe && restoredCells ? ' · ' : ''}${restoredCells ? `셀 ${restoredCells}개` : ''}`
              + ' (이 브라우저의 초안). 아직 서버에 반영되지 않았습니다.', 'warning',
              { dedupeKey: 'draft_restored' });
          }
          // 기반이 어긋난 초안이 실제로 내용을 갖고 있을 때만 말한다 — 빈 초안까지 알리면
          // 신호가 죽는다.
          const hasDoe = draft.doe && Object.keys(draft.doe).length > 0;
          const hasCells = draft.cells && Object.keys(draft.cells).length > 0;
          staleDraftKept = (!doeFresh && hasDoe) || (!cellsFresh && hasCells);
          if (staleDraftKept) {
            showToast('이 맵이 이 브라우저의 초안 이후에 변경됐습니다 — 초안을 적용하지 않고 '
              + '서버본을 표시합니다. 초안은 지우지 않았습니다.', 'warning',
              { dedupeKey: 'draft_stale' });
          }
        }
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
        showToast('DOE 정의(registry) 조회에 실패했습니다 — 이 맵에서는 서버 저장을 보류합니다'
          + `${hadDraft ? ' (이 브라우저의 초안을 표시 중)' : ''}. 맵을 다시 열면 재시도합니다 (${read.error || '알 수 없음'})`,
          'warning', { dedupeKey: 'legend_registry_load_failed' });
      }
    }

    // [M4①] 유효 다이의 근거를 이 맵의 메타에서 정한다. 선언이 없으면 `circle`로 돌아가
    // 종전과 완전히 같이 동작하고, 있으면 참조 맵을 해석해 그것만을 근거로 삼는다.
    // 렌더보다 **먼저** 놓는다 — 나중에 두면 원 기준으로 한 번 그린 뒤 마스크 기준으로
    // 다시 그리는 깜빡임이 생기고, 그 사이 프레임은 틀린 유효 다이를 보여준다.
    // [M4②] 홈 키를 함께 넘긴다 — 자기 참조(A→A)를 끊는 데 필요하다. `setLoadedIdentity`가
    // 아직 호출되지 않은 시점이므로 그 함수가 쓰는 것과 **같은 식**으로 만든다.
    await resolveValidDie(loadedGridMeta, selectedTable, loadedMapKey || getCurrentMapKey());

    renderGridCanvas();
    // [가드 ①] 로드 순간 편집 정체성을 고정하고 맵 키 입력을 잠근다.
    setLoadedIdentity(selectedTable, loadedMapKey || getCurrentMapKey());
    notifyMapContext();
    recordLastOpenMap();   // refresh returns here (no-op inside a material frame)
    // [F4] N rows fetched but 0 cells parsed = the NaN filter dropped everything —
    // warn with the likely cause instead of a green success naming "0셀".
    if (fetchedRows > 0 && count === 0) {
      showToast(
        `${selectedTable} · ${loadedMapKey || ''} — ${fetchedRows}행을 받았지만 좌표로 해석된 셀이 0개입니다. `
        + `x/y 컬럼 선택을 확인하세요.`, 'warning');
    } else if (quiet) showToast(`${selectedTable} · ${loadedMapKey || ''} — ${count}셀 로드`, 'success');
    else showToast(`${selectedTable} · ${loadedMapKey || ''} — ${count}셀 로드 완료`, 'success');
    return { count, mapKey: loadedMapKey };
  } catch (err) {
    console.error(err);
    if (quiet) showToast('맵 로드 실패 — 테이블/맵 키를 확인하십시오.', 'error');
    else alert('맵 로드 실패: 해당 테이블 또는 메타데이터 값을 다시 확인하십시오.');
    return { count: 0, error: true };
  } finally {
    el.btnLoadMap.textContent = '📂 Load Existing Map';
    el.btnLoadMap.disabled = false;
  }
}

function clearGrid() {
  if (!confirm('격자 내의 모든 입력 값을 삭제하시겠습니까?')) return;
  gridData = {};
  loadedFCells.clear();
  renderGridCanvas();
}

function fillGrid() {
  if (!activeBrush) {
    alert('페인팅 브러쉬를 먼저 선택하십시오.');
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
      const physical = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
      const key = `${physical.x}_${physical.y}`;
      const rendered = gridCells2D && gridCells2D[r] ? gridCells2D[r][c] : null;
      const inside = rendered
        ? rendered.inside
        : isValidDieAt(physical.x, physical.y, isCellInsideWafer(c, r, visualCols, visualRows));
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
    showToast(`칠할 수 있는 셀이 없습니다 — ${skippedOutside}칸이 모두 유효 다이 밖입니다. `
      + `물리 규격(직경·칩 크기)이나 유효 다이 맵을 먼저 확인하십시오.`, 'warning');
  } else if (skippedOutside > 0) {
    showToast(`${filled}칸을 '${activeBrush}'로 칠했습니다 `
      + `(유효 다이 밖 ${skippedOutside}칸 제외 — 저장되지 않는 셀입니다).`, 'success');
  }
}

// ----------------------------------------------------
// PUSH Map Data to Backend
// ----------------------------------------------------

// [Gate 4 - log-shaped push target] Columns the push payload can NEVER carry or
// that the server manages itself. Union of the two existing classifications:
// the schema endpoint's appended system tail + row identity (main.py:get_table_schema)
// and the write path's skip list (crud.py apply_row_update_internal system_cols,
// which also skips id/updated_by). grid_metadata is included because pushMapData
// serializes it explicitly whenever the column exists.
const PUSH_SYSTEM_COLUMNS = [
  'created_at', 'updated_at', 'row_id', 'id', 'updated_by', 'business_key_val',
  'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at',
  'grid_metadata'
];

// [Gate 4] Which of the target table's declared columns would a map push DESTROY?
// A ⚡ Push is `replace_map`: every row in the map-key scope is deleted, then rewritten
// from rows that carry only (map keys, x, y, val). Any other data column on the target
// (a log table's business key, timestamps-as-data, second coordinate pairs, equipment
// columns ...) comes back NULL on every row - viewing such a table as a map is fine,
// pushing into it is destruction.
//
// A column is COVERED (survives the push) iff it is:
//   - a map_key_column (written as the constant map scope),
//   - the currently bound x / y / val column,
//   - a system column the server manages (PUSH_SYSTEM_COLUMNS),
//   - the business_key WHEN it is composite-derived from covered columns only -
//     crud.apply_row_update_internal recomputes it from composite_key_source on
//     write, so e.g. bonding_map's pkg_id (base_x_y) survives even though the
//     payload never carries it. dt_log's dt_id has no composite source: not covered.
// Everything else in schema.columns is an unprotected data column -> refuse.
function getUnprotectedPushColumns(schema, xCol, yCol, valCol) {
  const cols = Array.isArray(schema && schema.columns) ? schema.columns : [];
  const covered = new Set([
    ...(Array.isArray(schema && schema.map_key_columns) ? schema.map_key_columns : []),
    xCol, yCol, valCol,
    ...PUSH_SYSTEM_COLUMNS
  ]);
  const bk = schema && schema.business_key;
  const src = Array.isArray(schema && schema.composite_key_source) ? schema.composite_key_source : [];
  if (bk && src.length > 0 && src.every(c => covered.has(c))) covered.add(bk);
  return cols.filter(c => !covered.has(c));
}

// [Gate 4] Full gate decision for one push target. One function so the harness
// executes the same branch pushMapData acts on:
//   'clean'   - no data columns outside the map contract: no gate friction at all.
//   'confirm' - extras exist BUT the site declared `map_push_ok: true` on the table
//               (table_config -> /schema): one loss-acknowledging confirm, then proceed.
//   'block'   - extras exist and no declaration: hard refusal.
function logShapedPushDecision(schema, xCol, yCol, valCol) {
  const extras = getUnprotectedPushColumns(schema, xCol, yCol, valCol);
  if (extras.length === 0) return { mode: 'clean', extras };
  return { mode: (schema && schema.map_push_ok === true) ? 'confirm' : 'block', extras };
}

async function pushMapData() {
  // [Data-protection gate 4 - log-shaped target] Fourth member of the gate family
  // (zone-columns-missing / legacy-unreadable / frame-contrast): refuse, don't confirm.
  // Placed before every dialog - the user should not answer a single question on a
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
        return;
      }
    } else {
      console.warn(`[Map Editor] push refused - '${selectedTable}' is log-shaped: `
        + `${extraDataCols.length} data column(s) outside the map contract would be `
        + `destroyed by replace_map: ${extraDataCols.join(', ')}`);
      alert(
        `적재를 중단했습니다 — '${selectedTable}'은(는) 맵 전용 테이블이 아닙니다(로그형 구조).\n\n`
        + `이 테이블에는 맵 계약(맵 키 + X/Y/값) 밖의 데이터 컬럼이 ${extraDataCols.length}개 있습니다:\n`
        + `· ${shown}\n\n`
        + `덮어쓰기 적재(Clean Replace)는 대상 범위의 실제 행을 전부 삭제한 뒤 격자 셀(키·좌표·값)만으로 `
        + `다시 쓰므로, 위 컬럼의 값이 전부 파괴됩니다.\n`
        + `이 테이블은 맵 조회(오버레이 소스)로만 사용하십시오. 적재가 필요하면 전용 맵 테이블을 만들어 사용해야 합니다.`
      );
      return;
    }
  }
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
    alert('데이터 적재를 위해 하나 이상의 메타데이터 필드 값을 입력하십시오.');
    return;
  }

  const xCol = el.colMapX.value;
  const yCol = el.colMapY.value;
  const valCol = el.colMapVal.value;

  const xType = tableSchema.column_types[xCol] || 'number';
  const yType = tableSchema.column_types[yCol] || 'number';
  const valType = tableSchema.column_types[valCol] || 'string';

  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert.checked;

  // Always construct grid metadata object & JSON string for dedicated wafer_map_metadata table
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
  // [M4①→②] 이 객체는 화면 컨트롤에서 **처음부터 다시** 만들어진다. ①에서는 선언에 대응하는
  // 컨트롤이 없어 원문(raw)을 그대로 되썼고, ②에서 그 컨트롤이 생겼다 — 이제 파괴적 재구성이
  // 선언 **옆**이 아니라 선언 **위**를 지나므로, 무엇을 쓸지는 두 함수가 나눠 정한다:
  //   `validDieRefForPush()`  — 사용자가 바꿨는가(모르면 원문을 손대지 않는다)
  //   `applyValidDieRef()`    — 바꿨다면 무엇을 쓰는가(이음매가 채점하는 순수 쓰기)
  // 선언이 없고 사용자가 칸을 건드리지 않은 맵은 `keep` + raw 부재 → 페이로드가 `2a9f6c4`와
  // **바이트 단위로 같다**(INV-1, effort 하네스가 페이로드로 단언한다).
  //   `validDieRefPayload()`   — 그 결정을 저장 페이로드로 바꾼다(순수 함수, 계약이 채점한다)
  const validDieDecision = validDieRefForPush();
  const gridMetaOut = validDieRefPayload(gridMeta, validDieDecision,
    validDie ? validDie.raw : undefined);
  const gridMetaStr = JSON.stringify(gridMetaOut);

  const updates = [];

  // [F2] 이 순회의 술어(`inside` && 값 있음)는 `eachSavableCell` 하나뿐이고, 화면의 수량도
  // 같은 함수를 지난다. 여기에 술어를 다시 쓰면 "화면 34 · DB 33"이 되돌아온다.
  eachSavableCell((cellObj, val) => {
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
  const nonEmptyOnGrid = Object.keys(gridData).filter(k => (gridData[k] || '') !== '').length;
  const droppedNonEmpty = nonEmptyOnGrid - updates.length;
  if (droppedNonEmpty > 0) {
    console.warn(`[Map Editor] push refused - frame covers ${updates.length}/${nonEmptyOnGrid} non-empty cells (${droppedNonEmpty} would be deleted by replace_map)`);
    alert(
      `적재를 중단했습니다 — 현재 프레임이 맵 전체를 덮지 못합니다.\n\n`
      + `값이 있는 셀 ${nonEmptyOnGrid}개 중 ${droppedNonEmpty}개가 현재 격자 범위·웨이퍼 영역 밖에 있어 `
      + `이번 적재에 담기지 않습니다. 이대로 적재하면 덮어쓰기(Clean Replace) 과정에서 `
      + `해당 ${droppedNonEmpty}개 셀이 서버에서 삭제됩니다.\n\n`
      + `격자 크기·시작 좌표·회전·물리 규격을 맵 전체가 보이도록 맞춘 뒤 다시 시도하십시오.`
    );
    return;
  }

  if (updates.length === 0) {
    alert('적재할 데이터가 격자에 존재하지 않습니다. 먼저 셀들을 칠해 주십시오.');
    return;
  }

  // [Split Registry] push 대상 값 중 split 서술이 비어있는 값 경고 (자연어 기록 누락 방지 관문)
  const pushedValues = Array.from(new Set(updates.map(u => String(u.updates[valCol]))));
  const missingDescVals = getMissingDescValues(pushedValues, legend);
  if (missingDescVals.length > 0) {
    const preview = missingDescVals.slice(0, 10).join(', ') + (missingDescVals.length > 10 ? ' …' : '');
    const okMissing = confirm(
      `split 서술(Description)이 없는 값 ${missingDescVals.length}개 — 그래도 저장하시겠습니까?\n` +
      `대상 값: [${preview}]\n\n` +
      `서술은 실험 split 조건의 자연어 기록으로, 팀 공유·검색·온톨로지 승격에 사용됩니다.`
    );
    if (!okMissing) return;
  }

  // [C5] 덮어쓰기 대상 맵을 확인문에 명시한다. replace_map은 이 맵 키의 기존 행을
  // 전량 삭제 후 재기록하므로, 테이블명만 보여주면 "어느 맵이 지워지는지" 알 수 없다.
  const targetMapId = getMapIdFromMeta(metaValues) || 'default_map';
  // [M4②] 원 밖으로 나가는 셀은 **말한다**. 새 확인창이 아니라 이미 있는 확인문의 한 줄이며,
  // 근거가 원인 맵(오늘의 모든 맵)에서는 이 줄이 존재하지 않는다 — 확인문이 글자 하나
  // 바뀌지 않는다는 뜻이다(INV-1). 유효 다이 저작·참조 중에만, 실제로 나가는 셀이 있을 때만.
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
      // [재설계 v2] Push 성공 = 이 프레임의 편집이 서버에 적재됨 (뒤로가기 경고 해제)
      framePushed = true;
      notifyMapContext();
      recordLastOpenMap();   // a just-created key becomes the refresh target too
      // [F5] 방금 만든 템플릿이 지정 칸 자동완성에 **없는** 상태를 없앤다. 캐시가
      // `switchTable`에서만 비워져 있었는데, 템플릿을 만들고 곧바로 다른 맵에서 지정하는
      // 흐름은 같은 테이블에 머문다(가장 흔한 동선).
      validDieListCache.delete(selectedTable);

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
        showToast(`DOE·split 서술 registry 저장 완료 (${legendSaved.count}건)`, 'success');
      } else if (legendSaved.reason !== 'adopted' && legendSaved.reason !== 'conflict'
                 && legendSaved.reason !== 'unknown-server-state') {
        // adopted/conflict/unknown 은 applyLegendSaveResult가 이미 정확히 알렸다 —
        // 여기서 "오프라인 캐시"로 덮어 말하면 원인이 사라진다.
        showToast('DOE·split 서술 registry 저장 실패 — 오프라인 캐시에만 보관됨', 'warning');
      }

      if (metaPushFailed) {
        // 셀은 들어갔지만 **규격이 저장되지 않았다** — 다음 로드/오버레이가 틀린 메타로 계산된다
        showToast(`셀 ${result.updated_count || result.count || updates.length}건은 적재됐으나 `
          + `**맵 규격(회전·면) 저장에 실패**했습니다 (${metaPushFailed}) — 다시 Push하십시오.`, 'error');
      } else {
        showToast(`적재 완료 — ${result.updated_count || result.count || updates.length}건 (bk 중복은 자동 병합)`, 'success');
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
    alert(`데이터 적재 실패: ${err.message}`);
  } finally {
    el.btnPushMap.textContent = '⚡ Push Map Data';
    el.btnPushMap.disabled = false;
  }
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
      const p = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide);
      if (isValidDieAt(p.x, p.y, isCellInsideWafer(c, r, visualCols, visualRows))) {
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
    alert(`격자 상에 E${target} 조건에 부합하는 셀이 존재하지 않습니다.`);
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
  showToast(`E1/E2 자동 페인팅 완료 — E1 ${e1Count}셀 · E2 ${e2Count}셀`, 'success');
}

function fillSelectedCells() {
  if (!activeBrush) {
    alert('페인팅 브러쉬를 먼저 선택하십시오.');
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

function copyHeaderEnabled() {
  return !!(el.copyHeaderToggle && el.copyHeaderToggle.checked);
}

// 상단 헤더의 열 그룹. Base는 이 맵의 정체(7b canonical 맵 키)이고, 나머지 셋은 DOE가
// 선언한 구역별 자재다. 자재 토큰은 **원문 그대로** 나간다 — `lot_slot:BIN`이 정체이고,
// 화면 칩이 보기 좋게 접어 보여주는 것은 그림일 뿐이다(transfer_plan §materialChipHtml).
function copyHeaderGroups() {
  const groups = [{ label: 'Base', value: getCurrentMapKey() || '' }];
  ZONES.forEach(z => {
    const seen = [];
    legend.forEach(item => {
      parseMaterialList(item[z]).forEach(tok => { if (seen.indexOf(tok) < 0) seen.push(tok); });
    });
    groups.push({ label: ZONE_LABEL[z], value: seen.join(', ') });
  });
  return groups;
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

function copyGridToExcel() {
  // 🔴 종전 가드 `if (!gridCells2D)`는 **한 번도 발화하지 않는 죽은 코드**였다:
  //    `gridCells2D`는 `{}`로 초기화되고 `{}`는 truthy다. 격자가 없어도 통과해서 빈 표를
  //    조용히 클립보드에 실었다. 조용한 빈 결과보다 사유를 붙인 거부가 낫다.
  const cellCount = gridCells2D
    ? Object.keys(gridCells2D).reduce((n, r) => n + Object.keys(gridCells2D[r] || {}).length, 0)
    : 0;
  if (cellCount === 0) {
    showToast('격자가 아직 만들어지지 않았습니다 — 맵을 먼저 불러오거나 격자를 생성하십시오.', 'warning');
    return;
  }

  const { visualCols, visualRows } = getVisualGridDimensions();
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
  const AUX_W = 4;                                   // VALUE · COUNT · STACK · DESC
  const GAP_W = 1;                                   // 격자와 보조표 사이 한 칸
  const auxHead = [colHeaderWord('value'), 'COUNT', colHeaderWord('stack'), colHeaderWord('desc')];
  const totalCols = headerOn ? Math.max(visualCols + GAP_W + AUX_W, groups.length * 2) : visualCols;

  const headCellStyle = `border: 1px solid ${lineHex}; background-color: ${outHex}; color: ${textEmptyHex};`
    + ' font-size: 10pt; font-weight: bold; text-align: center; vertical-align: middle; padding: 2px 6px;';
  const headValStyle = `border: 1px solid ${lineHex}; background-color: ${surface};`
    + ' font-size: 10pt; text-align: center; vertical-align: middle; padding: 2px 6px;';
  const gapStyle = 'border: none;';

  // 보조표 r번째 줄(0 = 머리줄)의 4칸 + 앞의 빈 칸. 없으면 빈 칸만.
  const auxCells = (i) => {
    let cells = `<td style="${gapStyle}"></td>`;
    const fields = (i === 0)
      ? auxHead
      : (auxRows[i - 1] ? [auxRows[i - 1].value, String(auxRows[i - 1].count), auxRows[i - 1].stack, auxRows[i - 1].desc] : null);
    for (let k = 0; k < AUX_W; k++) {
      if (!fields) { cells += `<td style="${gapStyle}"></td>`; continue; }
      const style = (i === 0) ? headCellStyle : headValStyle;
      cells += `<td style="${style}">${escapeHtmlAttr(fields[k])}</td>`;
    }
    return cells;
  };
  const auxTsv = (i) => {
    const fields = (i === 0)
      ? auxHead
      : (auxRows[i - 1] ? [auxRows[i - 1].value, String(auxRows[i - 1].count), auxRows[i - 1].stack, auxRows[i - 1].desc] : null);
    return fields ? ['', ...fields] : ['', '', '', '', ''];
  };
  const auxLines = headerOn ? auxRows.length + 1 : 0;   // 머리줄 포함

  // HTML table for rich formatting in Excel (Border + Fill Colors)
  let html = '<table style="border-collapse: collapse; text-align: center; font-family: Arial, sans-serif;">';

  if (headerOn) {
    // TITLE = 이 복사본이 **어느 맵인지**. 앱이 이미 로드 토스트에서 쓰는 표기와 같은 식이다
    // (`${selectedTable} · ${mapKey}`) — 인쇄물에 붙는 이름과 화면이 부르는 이름을 갈라 놓지
    // 않기 위해서다. 맵 키는 `getCurrentMapKey`(7b canonical)에서만 나온다.
    const titleKey = getCurrentMapKey() || '';
    const title = [selectedTable || '', titleKey].filter(Boolean).join(' · ');
    html += `<tr><td colspan="${totalCols}" style="border: none; font-size: 13pt; font-weight: bold;`
      + ` text-align: left; padding: 4px 2px;">${escapeHtmlAttr(title)}</td></tr>`;
    let groupRow = '<tr>';
    groups.forEach(g => {
      groupRow += `<td style="${headCellStyle}">${escapeHtmlAttr(g.label)}</td>`;
      groupRow += `<td style="${headValStyle}">${escapeHtmlAttr(g.value)}</td>`;
    });
    for (let k = groups.length * 2; k < totalCols; k++) groupRow += `<td style="${gapStyle}"></td>`;
    html += `${groupRow}</tr>`;
    matrix.push([title].concat(new Array(Math.max(0, totalCols - 1)).fill('')).join('\t'));
    const groupCells = [];
    groups.forEach(g => { groupCells.push(g.label, g.value); });
    while (groupCells.length < totalCols) groupCells.push('');
    matrix.push(groupCells.join('\t'));
  }

  // Helper for text color contrast
  const getContrastColor = (hexcolor) => {
    if (!hexcolor || hexcolor.charAt(0) !== '#') return '#000000';
    const r = parseInt(hexcolor.substr(1,2),16);
    const g = parseInt(hexcolor.substr(3,2),16);
    const b = parseInt(hexcolor.substr(5,2),16);
    const yiq = ((r*299)+(g*587)+(b*114))/1000;
    return (yiq >= 128) ? '#000000' : '#ffffff';
  };

  const box = getWaferBoundingBox(currentRotation, currentSide);
  const centerC = Math.floor((box.minC + box.maxC) / 2);
  const centerR = Math.floor((box.minR + box.maxR) / 2);

  const dx = (currentSide === 'front') ? 1 : -1;
  let screenDx = 0;
  let screenDy = 0;

  if (currentRotation === 0) { screenDx = dx; screenDy = 0; }
  else if (currentRotation === 90) { screenDx = 0; screenDy = dx; }
  else if (currentRotation === 180) { screenDx = -dx; screenDy = 0; }
  else if (currentRotation === 270) { screenDx = 0; screenDy = -dx; }

  let notchR = -1;
  let notchC = -1;

  if (currentRotation === 0) {
    // Bottom Notch: 1 row below box.maxR
    notchR = box.maxR + 1;
    notchC = centerC + screenDx;
  } else if (currentRotation === 180) {
    // Top Notch: 1 row above box.minR
    notchR = box.minR - 1;
    notchC = centerC + screenDx;
  } else if (currentRotation === 90) {
    // Left Notch: 1 col left of box.minC
    notchC = box.minC - 1;
    notchR = centerR + screenDy;
  } else if (currentRotation === 270) {
    // Right Notch: 1 col right of box.maxC
    notchC = box.maxC + 1;
    notchR = centerR + screenDy;
  }

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
    html += '</tr>';
    matrix.push(rowCells.join('\t'));
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
    html += `${rowHtml}</tr>`;
    matrix.push(rowCells.join('\t'));
  }

  html += '</table>';
  const tsv = matrix.join('\n');

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
  showToast('클립보드에 쓰지 못했습니다 — 브라우저가 복사를 막았습니다. 표를 클릭한 뒤 다시 시도하십시오.', 'error');
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
    const c = getCellFromVisualCoords(xn, yn, cols, rows, currentRotation, currentSide, invertY, startX, startY);
    const physical = getPhysicalCoords(c.c, c.r, cols, rows, currentRotation, currentSide);
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
      : `<span class="bc-up">${escapeHtmlAttr(t)}</span><span class="bc-sep">›</span>`).join('')
    + `<span class="bc-why">뒤로가면 편집 상태·오버레이·스크롤이 복원됩니다</span>`;
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
  const dirty = !framePushed && frameTouched && gridData && Object.keys(gridData).length > 0;
  if (dirty && !confirm(
    `이 맵을 [⚡ Push]로 저장하지 않았습니다.\n\n` +
    `[확인] 저장하지 않고 돌아가기\n[취소] 이 화면에 남기`
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
// `getCellFromVisualCoords` → `getPhysicalCoords` 두 줄을, 소스 프레임을 씌운 채 실행할 뿐이다.
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
let overlayLayers = [];        // { id, sourceTable, sourceKey, cells:Map(physKey->val), count, color, visible, status, alignApplied, truncated }
let activeOverlayLayers = [];  // 그리기 대상(visible)만 추린 캐시 — 렌더 루프에서 재계산 금지
let overlaySeq = 1;

function recomputeActiveOverlays() {
  activeOverlayLayers = overlayLayers.filter(o => o.visible && o.cells && o.cells.size > 0);
}

// 셀 하나에 대한 오버레이 마커 — 레이어별 색 점을 우상단에 나란히 찍는다.
function drawOverlayMarkers(ctx, coordKey, x0, y0, cellW, cellH) {
  const r = Math.max(1.5, Math.min(cellW, cellH) * 0.13);
  let idx = 0;
  for (let i = 0; i < activeOverlayLayers.length; i++) {
    const layer = activeOverlayLayers[i];
    if (!layer.cells.has(coordKey)) continue;
    const cx = x0 + cellW - r - 1.5 - idx * (r * 2 + 1.5);
    const cy = y0 + r + 1.5;
    if (cx < x0) break; // 셀이 너무 작아 더 못 찍음
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, 2 * Math.PI);
    ctx.fillStyle = layer.color;
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 0.8;
    ctx.stroke();
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
  };
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
  return withPhysFrame(f, () => ({
    cols: gridDimNum('cols', el.gridCols, 10),
    rows: gridDimNum('rows', el.gridRows, 10),
    startX: f.startX, startY: f.startY,
    invertY: !!f.invertY, rotation: Number(f.rotation) || 0,
    side: f.side === 'back' ? 'back' : 'front',
    waferDia: physNum('waferDia', el.physWaferDia, 300),
    chipX: physNum('chipX', el.physChipX, 2.5),
    chipY: physNum('chipY', el.physChipY, 2.5),
    offsetX: physNum('offsetX', el.physOffsetX, 0.0),
    offsetY: physNum('offsetY', el.physOffsetY, 0.0),
    edgeMargin: physNum('edgeMargin', el.physEdgeMargin, 3.0),
  }));
}

function frameAxesKey(rf) {
  return [rf.rotation, rf.side, rf.invertY ? 1 : 0, rf.startX, rf.startY, rf.cols, rf.rows,
          rf.waferDia, rf.chipX, rf.chipY, rf.offsetX, rf.offsetY, rf.edgeMargin].join('|');
}

// ── 변환의 전부 ──────────────────────────────────────────────
// 소스 **원본 셀** → 물리 키 Map.
// 아래 두 줄은 메인 로드(loadExistingMap의 셀 루프)와 **같은 함수·같은 인자 순서**이며,
// 다른 점은 단 하나 — 규격을 소스 자신의 프레임에서 읽는다는 것뿐이다.
// 결과인 물리 키는 화면 컨트롤에 불변이므로, 이후 사용자가 무엇을 돌리든
// 렌더가 메인 맵과 오버레이를 **같은 규칙으로 함께** 움직인다.
function projectCellsToPhys(cells, frame) {
  const f = frame || currentFrame();
  const { cols, rows, rotation, side, invertY, startX, startY } = f;
  return withPhysFrame(f, () => {
    const map = new Map();
    (Array.isArray(cells) ? cells : []).forEach(c => {
      const xn = Number(c.x);
      const yn = Number(c.y);
      if (!Number.isFinite(xn) || !Number.isFinite(yn)) return;
      const cell = getCellFromVisualCoords(xn, yn, cols, rows, rotation, side, invertY, startX, startY);
      const p = getPhysicalCoords(cell.c, cell.r, cols, rows, rotation, side);
      map.set(`${p.x}_${p.y}`, (c.val === undefined || c.val === null) ? '' : String(c.val));
    });
    return map;
  });
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
  const set = (basis, keys, reason, ref) => {
    if (stale()) return validDie;
    validDie = { basis, keys, reason: reason || '', ref: ref || null, raw };
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

  const parsed = parseValidDieRef(meta, targetTable);
  if (parsed === null) return set('circle', null, '', null);          // 선언 없음 = 종전 그대로
  if (parsed.unreadable) return refuse(null, parsed.reason);

  const ref = { table: parsed.table, mapKey: parsed.mapKey };
  try {
    // [7b] 참조된 맵 키도 캐노니컬화한다 — 여기서만 원문을 쓰면 이 라운드가 고친 그 결함이
    // 유효 다이 경로로 그대로 재현된다.
    const spec = await fetchMapKeySpec(ref.table);
    if (spec.ok && spec.keyColumns.length > 0) {
      ref.mapKey = canonicalMapKey(spec.keyColumns, ref.mapKey, spec.columnTypes);
    }

    const binding = await fetchServedBinding(ref.table);
    if (!binding) {
      return refuse(ref, `${ref.table}: 좌표 바인딩을 서버가 해석해 주지 못했습니다.`);
    }
    if (binding.source === 'fallback_guess') {
      // 오버레이 경로와 같은 규율(§5.6-bis) — 추측한 컬럼으로 마스크를 만들면 그 마스크는
      // 미끼다. 그리는 것보다 더 나쁘다: 보이지 않는 채로 페인팅을 막거나 허용한다.
      return refuse(ref, `${ref.table}: 값/좌표 컬럼이 추측(fallback_guess)뿐입니다.`);
    }

    const refMeta = await fetchGridMetaFor(ref.table, ref.mapKey);   // 실패는 throw
    const refFrame = frameFromMeta(refMeta);
    if (!refFrame) {
      // 미등록도 여기서는 거절이다. 오버레이는 규격이 없으면 "무보정"이라고 **화면에
      // 적어서** 알리지만, 마스크는 보이지 않는 기계장치라 같은 폴백이 조용해진다.
      return refuse(ref, `${ref.table} · ${ref.mapKey}: 참조 맵의 규격(wafer_map_metadata)이 없습니다.`);
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
      return refuse(ref, `${ref.table} · ${ref.mapKey}: 참조 맵에 좌표로 읽히는 셀이 없습니다.`);
    }

    // 격자 규격 호환성 — 물리 좌표는 정준 격자의 인덱스다. 치수가 다르면 같은 인덱스가
    // 같은 다이가 아니므로 겹칠 근거가 없다(§5.1의 그 관문과 같은 판정).
    const refResolved = resolveFrame(refFrame);
    const hereResolved = resolveFrame(currentFrame());
    if (refResolved.cols !== hereResolved.cols || refResolved.rows !== hereResolved.rows) {
      return refuse(ref,
        `격자 규격이 다릅니다 — 참조 ${refResolved.cols}x${refResolved.rows} vs 현재 ${hereResolved.cols}x${hereResolved.rows}.`);
    }

    const keys = new Set(projectCellsToPhys(cells, refFrame).keys());
    if (keys.size === 0) {
      return refuse(ref, `${ref.table} · ${ref.mapKey}: 참조 맵을 물리 좌표로 투영한 결과가 비었습니다.`);
    }
    return set('ref', keys, '', ref);
  } catch (e) {
    return refuse(ref, `${ref.table} · ${ref.mapKey}: ${e && e.message ? e.message : String(e)}`);
  }
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
    chip.title = '유효 다이 맵을 만드는 중입니다: 격자 전체가 후보이고, **칠한 셀이 곧 유효 다이**입니다.\n'
      + '⚡ Push로 저장한 뒤, 다른 맵의 「유효 다이 맵」 칸에 이 맵 키를 넣으면 그 맵의 판정 근거가 됩니다.\n'
      + '맵을 다시 불러오거나 테이블을 바꾸면 저작 상태는 해제됩니다.';
  } else if (basis === 'ref') {
    const r = validDie.ref || {};
    chip.textContent = `🎯 유효 다이: ${r.table || ''} · ${r.mapKey || ''} (${validDie.keys.size})`;
    chip.title = '이 맵의 유효 다이는 참조된 맵이 정합니다 — 웨이퍼 원은 판정에 참여하지 않습니다.';
  } else {
    chip.textContent = '⚠️ 유효 다이 맵 미해석';
    chip.title = `유효 다이 맵을 해석하지 못했습니다: ${validDie.reason}\n`
      + '판정 근거를 확인하기 전까지 이 맵의 유효 다이 표시를 믿지 마십시오.';
  }
}

// ── [M4 phase 2] 지정/해제 컨트롤 ────────────────────────────────────────────────
// 새 패널도 모달도 아니다 — 물리 규격 블록(§2, 원 기하가 사는 자리)에 한 줄이다.
// **읽기는 무마찰**: 값을 보여 주는 데 확인창이 없다. **쓰기는 1회 확인**: 저장은 기존 ⚡ Push
// 확인 하나뿐이고 여기서 따로 묻지 않는다.
function syncValidDieRefControls() {
  const shown = validDieRefDisplay(validDie ? validDie.raw : undefined);
  if (el.validDieRefKey && el.validDieRefKey.value !== shown.key) el.validDieRefKey.value = shown.key;
  if (el.validDieRefTable) {
    // 선언된 테이블이 목록에 없으면(권한·오타) 옵션을 만들지 않는다 — 없는 것을 있는 것처럼
    // 보여 주지 않는다. 그 경우 select는 '(이 맵의 테이블)'에 남고 raw는 그대로 보존된다.
    const has = Array.from(el.validDieRefTable.options).some(o => o.value === shown.table);
    el.validDieRefTable.value = has ? shown.table : '';
  }
  // [F1] 앱이 컨트롤을 raw로 되맞췄다 = 대기 중인 사용자 의도가 없다. 이 한 줄이 없으면
  //      위 강제값이 다음 Push에서 "사용자가 고른 홈 테이블"로 읽힌다.
  validDieRefTableTouched = false;
}

// 지정 칸이 바뀌었다 = 판정 근거가 바뀌었다. 즉시 다시 해석해 **화면에서 확인**할 수 있게 한다.
// 저장은 아니다 — 저장은 ⚡ Push다. `resolveValidDie`가 `validDie.raw`를 새 값으로 세우므로
// 이후 Push가 쓰는 값과 화면이 보는 값이 갈라질 수 없다(같은 수를 두 곳에서 만들지 않는다).
async function onValidDieRefChanged() {
  // [F1] Push와 **같은 함수**로 컨트롤을 읽는다. 여기서만 select를 직접 읽으면 목록에 없는
  //      테이블이 키 편집 한 번에 사라져(재해석이 raw를 문자열로 바꿔 놓는다) 같은 결함이
  //      다른 문으로 되돌아온다.
  const { table, key } = validDieRefFromControls();
  const meta = {};
  if (key !== '') meta.valid_die_ref = (table === '') ? key : { table, map_id: key };
  await resolveValidDie(meta, selectedTable,
    (loadedIdentity && loadedIdentity.mapKey) ? loadedIdentity.mapKey : getCurrentMapKey());
  renderGridCanvas();
  if (key === '') {
    showToast('유효 다이 지정을 해제했습니다 — 원 기하로 되돌아갑니다. ⚡ Push로 저장하십시오.',
      'info', { dedupeKey: 'valid_die_cleared' });
  }
}

// [목록·재사용] 이 테이블에 규격이 등록된 맵 키를 지정 칸의 자동완성으로 내려 준다.
// 새 목록 패널을 만들지 않는다 — 이미 있는 입력칸의 `datalist`다. 조회 실패는 조용히 넘어간다
// (자동완성이 비는 것은 데이터 오답이 아니라 편의 부재이므로 토스트로 방해하지 않는다).
const validDieListCache = new Map();
async function populateValidDieRefList() {
  if (!el.validDieRefList) return;
  const table = (el.validDieRefTable && el.validDieRefTable.value ? el.validDieRefTable.value : '')
    .trim() || selectedTable;
  if (!table) return;
  let ids = validDieListCache.get(table);
  if (!ids) {
    try {
      const filters = { target_table: { filterType: 'text', type: 'equals', filter: String(table) } };
      const res = await fetch(`${API_BASE}/tables/wafer_map_metadata/data`
        + `?limit=${VALID_DIE_LIST_LIMIT}&filters=${encodeURIComponent(JSON.stringify(filters))}`);
      if (!res.ok) return;
      const result = await res.json();
      const rows = (result && Array.isArray(result.data)) ? result.data : [];
      ids = rows.map(r => (r.data && r.data.map_id ? r.data.map_id.value : null))
        .filter(v => v !== null && v !== undefined && String(v).trim() !== '')
        .map(String);
      validDieListCache.set(table, ids);
    } catch (e) { return; }
  }
  el.validDieRefList.innerHTML = '';
  ids.forEach(id => {
    const o = document.createElement('option');
    o.value = id;
    el.validDieRefList.appendChild(o);
  });
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
    showToast('이 맵은 이미 다른 유효 다이 맵을 참조합니다 — 유효 다이 맵 자신은 참조를 가질 수 '
      + '없습니다(체인 1단계). 「유효 다이 맵」 칸을 비운 뒤 다시 시도하십시오.', 'error');
    return;
  }
  const tpl = buildValidDieTemplate(shape);
  if (tpl.keys.size === 0) {
    showToast('격자 규격을 읽지 못해 템플릿을 만들 수 없습니다 — 물리 규격을 먼저 적용하십시오.', 'error');
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
    showToast(`유효 다이 저작을 시작했습니다 — 격자 전체 ${tpl.keys.size}칸이 후보입니다 `
      + `(현재 칠해진 셀 ${painted}개는 그대로 둡니다).`, 'success');
    return;
  }

  if (!activeBrush) {
    // fillGrid와 **같은 전제, 같은 문구** — 칠하는 연산의 규칙은 하나다.
    alert('페인팅 브러쉬를 먼저 선택하십시오.');
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
  showToast(`유효 다이 템플릿 생성 — ${tpl.filled.length}칸을 '${activeBrush}'로 칠했습니다`
    + `${tpl.outsideCircle > 0 ? ` (웨이퍼 원 밖 ${tpl.outsideCircle}칸 포함)` : ''}. `
    + `지울 셀을 우클릭으로 깎아낸 뒤 ⚡ Push로 저장하십시오.`, 'success');
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
  const srcFrame = frameFromMeta(sourceMeta) || currentFrame();
  const tgtMetaFrame = frameFromMeta(targetMeta);
  const tgtFrame = tgtMetaFrame || currentFrame();
  const srcResolved = resolveFrame(srcFrame);
  const tgtResolved = resolveFrame(tgtFrame);

  // ⑥ 웨이퍼 격자 규격 호환성. 물리 좌표는 cols×rows 정준 격자의 인덱스라
  //    치수가 다르면 같은 인덱스가 같은 다이를 가리키지 않는다 (서버와 같은 명시 거절).
  if (srcResolved.cols !== tgtResolved.cols || srcResolved.rows !== tgtResolved.rows) {
    return fail(
      `${sourceTable}: 웨이퍼 격자 규격이 다릅니다 — 소스 ${srcResolved.cols}x${srcResolved.rows} vs `
      + `타깃 ${tgtResolved.cols}x${tgtResolved.rows}. 같은 웨이퍼 규격이 아니면 물리 좌표를 맞출 근거가 없습니다.`,
      'align_unavailable');
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
  if (srcResolved.chipX !== tgtResolved.chipX || srcResolved.chipY !== tgtResolved.chipY
      || srcResolved.offsetX !== tgtResolved.offsetX || srcResolved.offsetY !== tgtResolved.offsetY
      || srcResolved.waferDia !== tgtResolved.waferDia || srcResolved.edgeMargin !== tgtResolved.edgeMargin) {
    diffs.push('웨이퍼 물리 규격 상이(바운딩박스 재계산)');
  }
  // [F4] Cells whose projected physical coordinate falls outside the canonical wafer grid
  //      [0,cols) x [0,rows). Reporting the raw source row count as "N chips" hides them:
  //      they are excluded from import (importOverlayToGrid rule 3) and are not push targets.
  //      NOTE: this is deliberately NOT "will not be painted". The render loop sweeps a 3x3
  //      tile window (:1658-1671), so an out-of-grid cell may still be painted in the margin
  //      depending on canvas size — that is viewport-dependent and not a stable thing to claim.
  //      Grid membership is frame-defined and stable, so that is what we report.
  const projected = projectCellsToPhys(cells, srcFrame);
  let outside = 0;
  projected.forEach((_v, k) => {
    const i = k.indexOf('_');
    const px = Number(k.slice(0, i));
    const py = Number(k.slice(i + 1));
    if (!(px >= 0 && px < tgtResolved.cols && py >= 0 && py < tgtResolved.rows)) outside++;
  });
  const missingPhys = !sourceMeta ? '소스 맵 규격 미등록 — 현재 화면 규격으로 해석'
    : (frameFromMeta(sourceMeta) && [srcFrame.waferDia, srcFrame.chipX, srcFrame.chipY,
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
    note: [diffs.length ? `프레임 정규화: ${diffs.join(', ')}` : '', missingPhys, targetNote,
      outside ? `격자 밖 ${outside}칩 — 웨이퍼 격자를 벗어나 가져오기에서 제외됩니다` : ''].filter(Boolean).join(' · ')
      || (identical ? '소스와 타깃의 좌표계가 완전히 같습니다 (변환 없음)' : ''),
  };

  const layer = {
    id: overlaySeq++,
    sourceTable: String(sourceTable),
    sourceKey: String(sourceKey),
    rawCells: cells,      // **소스 원본 좌표** — 재투영의 유일한 원천
    frame: srcFrame,      // 그 좌표가 사는 프레임 (소스 자신의 메타)
    cells: projected,
    count: projected.size,   // physical keys actually placed — not the raw row count, which over-reports on key collision
    outside,
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
  // 같은 소스의 실패 잔존 행이 있으면 성공 행으로 교체한다 (재시도 성공)
  overlayLayers = overlayLayers.filter(o => !(o.failed && o.sourceTable === layer.sourceTable && o.sourceKey === layer.sourceKey));
  overlayLayers.push(layer);
  recomputeActiveOverlays();
  renderOverlayList();
  scheduleRenderGridCanvas();
  return { layer };
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

// 규격이 바뀌면 원본(rawCells)을 **소스 프레임으로** 재투영한다.
//
// 소스 메타가 완전하면 재투영은 항등이다(물리 키는 화면 조작에 불변). 그러나 소스 메타에
// 물리 항목이 빠져 있으면 그 항목은 **현재 화면 값으로 폴백**하므로 결과가 화면에 의존한다.
// [C7] 그래서 시그니처에 **물리 파라미터를 반드시 포함**한다 — 빠뜨리면 chip_x/offset 등을
// 바꿨을 때 재투영이 일어나지 않아 오버레이가 조용히 어긋난 자리를 가리킨다.
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
    o.cells = projectCellsToPhys(o.rawCells, o.frame);
  });
  recomputeActiveOverlays();
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
  const note = String(o.align.note || '');
  const rot = Number(o.align.rotation) || 0;
  // 무엇에 맞춰 정렬했는가 — 등록 규격(wafer_map_metadata)인가, 지금 화면의 격자 설정인가.
  // 후자를 전자처럼 보여주면 "규격대로 맞췄다"는 거짓 진술이 된다(빈 맵 오버레이의 기본 상태).
  const basis = o.align.targetBasis === 'screen'
    ? '<span class="ov-chip dim" title="타깃 맵의 등록 규격이 없어 **현재 화면의 격자 설정**을 기준으로 겹쳤습니다. 화면 규격을 바꾸면 정렬도 함께 바뀝니다.">화면기준</span>'
    : '';
  if (origin === 'identity') {
    return `<span class="ov-chip dim" title="${escapeHtmlAttr(note || '좌표 보정 없이 그대로 겹쳤습니다')}">무보정</span>${basis}`;
  }
  // derived(및 그 외 비-identity) = 보정 적용됨. 회전은 0일 수 있으므로 있을 때만 덧붙인다.
  const label = rot ? `정렬됨 ${rot}°` : '정렬됨';
  return `<span class="ov-chip ok" title="${escapeHtmlAttr(note || o.alignText || '소스 맵의 좌표계가 달라 소스 메타 프레임으로 해석해 물리 좌표에 맞췄습니다')}">${escapeHtmlAttr(label)}</span>${basis}`;
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

  let applied = 0, locked = 0, outside = 0, blank = 0;
  const values = new Set();
  o.cells.forEach((val, key) => {
    const sv = (val === null || val === undefined) ? '' : String(val).trim();
    if (sv === '') { blank++; return; }
    if (!insideKeys.has(key)) { outside++; return; }
    if (isProtectedFCell(key)) { locked++; return; }   // ② 잠금 셀은 덮지 않는다
    gridData[key] = sv;                                 // 겹치는 셀은 덮어쓰기 (총괄 지시 기본값)
    values.add(sv);
    applied++;
  });

  if (applied === 0) {
    showToast(`가져온 셀이 없습니다 (잠금 ${locked} · 격자 밖 ${outside} · 빈 값 ${blank}).`, 'warning');
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
  if (added.length > 0) parts.push(`legend ${added.length}종 추가`);
  showToast(`${o.sourceTable} · ${o.sourceKey} → ${parts.join(' · ')} — 아직 서버에 저장되지 않았습니다. [⚡ Push]로 적재하십시오.`, 'success');
}

// legend에 없는 값들을 추가하고 추가된 값 배열을 반환
// ([U6] declared default_legend 우선, 다음은 공용 팔레트 규칙 — autoAddLegendValue 하나로 간다)
function ensureLegendValues(values) {
  const added = [];
  values.forEach(v => {
    if (autoAddLegendValue(v, '')) added.push(String(v));
  });
  if (added.length > 0) saveLegendToStorage(); // 로컬 캐시만 — 서버 registry는 Push 시점에
  return added;
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
  box.innerHTML = overlayLayers.map(o => `
    <div class="ov-row ${o.failed ? 'err' : ''} ${(!o.failed && !o.visible) ? 'off' : ''}" data-id="${o.id}">
      <span class="ov-dot" style="background:${escapeHtmlAttr(o.color)}"></span>
      <span class="ov-name" title="${escapeHtmlAttr(o.sourceTable + ' · ' + o.sourceKey + (o.reason ? ' — ' + o.reason : ''))}">
        <b>${escapeHtmlAttr(o.sourceTable)}</b><br><span class="ov-key">${escapeHtmlAttr(o.sourceKey)}</span>
      </span>
      <span class="ov-meta">${o.failed ? '' : `${o.count}칩 `}${overlayAlignChip(o)}${o.truncated ? `<span class="ov-chip warn" title="서버 상한 ${escapeHtmlAttr(String(o.cap || '?'))}">일부만</span>` : ''}</span>
      <span class="ov-btns">
        ${o.failed ? '' : `<button type="button" class="ov-btn ov-import" data-act="import" title="이 오버레이의 셀을 현재 편집 맵으로 가져옵니다 (잠금 셀 제외 · Push 전까지 서버 반영 없음)">↓</button>`}
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
        else showToast(`오버레이 재시도 성공: ${o.sourceTable} · ${o.sourceKey}`, 'success');
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
    const t = r.layer.truncated ? ' (일부만 표시 — 서버 절단)' : '';
    showToast(`오버레이 추가: ${r.layer.sourceTable} · ${r.layer.sourceKey} — ${r.layer.count}칩${t}`, 'success');
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
