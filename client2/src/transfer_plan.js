// ============================================================
// transfer_plan.js — 「2. Legend & DOE」 패널 (재설계 v2)
//
//   원칙: **계획 = 지금 열어 편집 중인 그 맵.**
//   bonding_map을 열면 그게 본딩 계획이고, dt_map을 열면 그게 DT 계획이다.
//   stage는 열린 테이블에서 **유도**한다 (서버 config `stages.*.target_map.table`의 역인덱스).
//   → stage 선택 UI · 타깃 입력 · plan_id 입력 · 모드 A/B · 페인팅 진입/이탈 모달은 전부 폐기.
//
//   화면은 세로 두 목록뿐이다:
//     ① DOE LIST  — legend 행 = DOE 행. 행 클릭 = 선택 + 브러시 + 펼침(한 동작).
//     ② 사용 자재 — DOE별 그룹. 행 클릭 = 그 자재의 맵으로 이동(유일한 이동 허브).
//
//   legend(value/desc/color)의 원천은 map_editor다 — 이 파일은 controller 관문으로만 변조한다.
//   DOE 확장 필드(STACK 구간·총 소요·자재 묶음·knob)는 이 파일이 소유한다.
//
//   ⭐ DOE 행의 단위는 **(값, STACK 구간)** 이다 (서버 계약 §0-2-bis).
//      한 값이 구간을 여러 개 갖고, **구간마다 자재 묶음이 다를 수 있다**:
//        A | H1~H2 | TAPE-X      A | H2~H3 | TAPE-Y      B | H1~H3 | TAPE-X
//      구간 하나 안에서도 라벨은 `1, 2-15, 16`처럼 **다중 범위**를 자유 텍스트로 적을 수 있다
//      (같은 자재 묶음으로 여러 층대를 덮는 경우 — 행을 나눌 필요가 없다).
//
//      구간의 **정체는 `band_seq`(정수 서수), 표기는 `stack_band`(자유 텍스트 비키)** 로 분리된다.
//      · band_seq는 클라가 max+1로 부여하고 **삭제해도 재번호하지 않는다**
//        (재번호하면 자식 map_doe_source가 통째로 고아가 된다).
//      · stack_band는 언제든 고쳐도 그 구간의 자재 묶음이 그대로 붙어 있다.
//
//   ⚠️ 검증/경고 표시 일습(수량 부족 판정·교차 초과배정·validate 연동·신뢰 어휘 배지)은
//      사용자 지시로 **이번 범위에서 보류**다. 판정 로직은 지우지 않고 아래 §보류 구역에
//      그대로 두었으며(호출부만 끊음), 재설계 확정 후 다시 붙인다.
//      지금 표시하는 것은 **서버가 이미 주는 숫자(가용/소요)의 단순 표시**뿐이다.
// ============================================================
import { API_BASE, CURRENT_USER } from './config.js';
import { showToast, getLocalTimeString } from './utils.js';
import './transfer_plan.css';

const DRAFT_PREFIX = 'transfer_plan_draft::';
const DRAFT_VERSION = 5;   // v5: DOE = (값, 구간) 다중 밴드

// 서버 계약 v2 — 계획 헤더 테이블(transfer_plan)은 폐기됐다(plan 역할 소멸).
const DOE_TABLE = 'map_doe';               // bk: ref_table|map_key|doe_value|band_seq
const DOE_SOURCE_TABLE = 'map_doe_source'; // bk: …|band_seq|source_lot|source_slot

// stage 미선언 서버(구버전) 폴백 — target_map.table 역인덱스의 최소 형태
const BUILTIN_STAGES = [
  { id: 'dt', name: 'DT PLAN', targetTable: 'dt_map', targetKind: 'tape', sourceKind: 'core', builtin: true },
  { id: 'bonding', name: 'BONDING PLAN', targetTable: 'bonding_map', targetKind: 'base', sourceKind: 'tape', builtin: true },
];

// 소스 종류 → 자재 맵 테이블 폴백 (stage 역인덱스가 비었을 때만)
const SOURCE_TABLE_FALLBACK = { core: 'core_defect_map', tape: 'dt_map' };

// 자재 맵 위에 겹쳐 보는 단축 오버레이 후보
const SOURCE_OVERLAY_SUGGESTIONS = [
  { table: 'core_defect_map', label: 'defect' },
  { table: 'eds_fail_map', label: 'EDS fail' },
];

const S = {
  stages: BUILTIN_STAGES,
  stagesStatus: null,
  ctx: { table: '', mapKey: '', loaded: null, depth: 0, parent: null },
  legendRows: [],            // map_editor legend 미러 { value, desc, color }
  doe: new Map(),            // value -> Band[]   (Band = {seq, stack, need, materials[], knobs[]})
  openValue: null,           // 펼친 DOE (한 번에 하나)
  counts: {},                // value -> 칠한 셀 수
  activeBrush: '',
  summaries: new Map(),      // "lot|slot" -> { status, data, error }
  matMapState: new Map(),    // "table|lot|slot" -> true | false | null(미상)
  keyColumns: new Map(),     // table -> map_key_columns
  savedAt: null,
  serverSavedAt: null,
  planTablesSupported: null,
  // [B2/C1] 서버 상태를 **성공적으로 읽었는가**. 이것이 참일 때만 replace 쓰기가 허용된다
  // ("화면이 서버본에서 유래한다"가 아니면 replace는 보지 못한 행을 지운다).
  doeServerLoaded: false,
  // How many rows this plan holds on the server, per table. Only used to tell
  // "there is nothing to clear" apart from "we could not express the clear"
  // (replace_map cannot carry an empty set) — never to decide what to delete.
  serverRows: { doe: 0, source: 0 },
  // [M5] 마지막 서버 저장 실패 사유 (헤더에 표시 — "저장됨"으로 위장 금지)
  saveError: null,
  // The last save held a deletion it could not send. Never report that as a
  // completed save — the removed rows are still on the server.
  deleteUnsent: false,
  loadSeq: 0,
  matSeq: 0,
  flash: new Set(),          // 1회성 하이라이트 대상 자재 키
  navBusy: false,
};

const elp = {};
let controller = null;

// ── 유틸 ────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function parseSource(str) {
  const v = String(str || '').trim();
  if (!v) return { lot: '', slot: '' };
  const idx = v.indexOf('|');
  if (idx < 0) return { lot: v, slot: '' };
  return { lot: v.slice(0, idx).trim(), slot: v.slice(idx + 1).trim() };
}

function matLabel(m) { return m.slot ? `${m.lot}|${m.slot}` : String(m.lot); }
function matKey(m) { return `${m.lot}::${m.slot || ''}`; }

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
// ⚠️ **조용한 추측 금지 (총괄 지시).** 역인덱스가 비면(예: dt stage의 source_kind='core'는
//    대응 stage가 없다) 하드코딩 폴백을 쓰는데, 그 사실을 반드시 드러낸다 —
//    콘솔 경고 + 자재 목록 하단에 `추정` 칩. 서버에 명시 선언을 요청해 둔 상태다.
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

async function fetchStages() {
  S.stagesStatus = 'loading';
  try {
    const res = await fetch(`${API_BASE}/api/transfer-plan/stages`);
    if (res.status === 404 || res.status === 405) {
      S.stages = BUILTIN_STAGES; S.stagesStatus = 'unsupported';
    } else if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    } else {
      const data = await res.json();
      const arr = Array.isArray(data) ? data : (Array.isArray(data.stages) ? data.stages : []);
      const stages = arr.map(normalizeStage).filter(Boolean);
      if (stages.length > 0) { S.stages = stages; S.stagesStatus = 'ok'; }
      else { S.stages = BUILTIN_STAGES; S.stagesStatus = 'unsupported'; }
    }
  } catch (e) {
    console.warn('[Legend & DOE] stages fetch failed — builtin fallback:', e);
    S.stages = BUILTIN_STAGES; S.stagesStatus = 'error';
  }
  renderAll();
}

// ── DOE 저장 키 (조립은 여기 한 곳에서만) ────────────────
// 서버 계약 v2 확정: DOE 키가 `ref_table|map_key|doe_value|band_seq`로 이동했다.
// (구 `<stage>__<target>` plan_id 및 transfer_plan 헤더 테이블은 폐기)
function doeScopeReady() { return !!(S.ctx.table && S.ctx.mapKey); }

function doeRowKey(value, seq) {
  return `${S.ctx.table}|${S.ctx.mapKey}|${value}|${seq}`;
}
function doeSourceRowKey(value, seq, lot, slot) {
  return `${S.ctx.table}|${S.ctx.mapKey}|${value}|${seq}|${lot}|${slot || ''}`;
}
function draftKey() { return `${DRAFT_PREFIX}${S.ctx.table}::${S.ctx.mapKey}`; }

// ── DOE 확장 레코드 = 밴드(구간) 배열 ────────────────────
function blankBand(seq) { return { seq, stack: '', need: '', materials: [], knobs: [] }; }

// value -> Band[] (없으면 빈 배열 생성). 밴드가 0개인 값은 "구간 미정의"로 표시된다.
function getBands(value) {
  const v = String(value);
  if (!S.doe.has(v)) S.doe.set(v, []);
  return S.doe.get(v);
}

// band_seq는 **max+1**. 삭제해도 재번호하지 않는다 — 재번호는 자식 행 전체 re-key다.
function nextBandSeq(bands) {
  return bands.reduce((m, b) => Math.max(m, Number(b.seq) || 0), 0) + 1;
}

function addBand(value) {
  const bands = getBands(value);
  const b = blankBand(nextBandSeq(bands));
  bands.push(b);
  return b;
}

function getBand(value, seq) {
  return getBands(value).find(b => Number(b.seq) === Number(seq)) || null;
}

// knob 배열 ↔ 객체 (서버 knobs 컬럼은 JSON 문자열이다)
function knobsToObject(arr) {
  const out = {};
  (arr || []).forEach(p => {
    const k = String(p.k || '').trim();
    if (k) out[k] = p.v === undefined || p.v === null ? '' : String(p.v);
  });
  return out;
}
function knobsToArray(obj) {
  if (!obj || typeof obj !== 'object') return [];
  return Object.entries(obj).map(([k, v]) => ({ k, v: v === null || v === undefined ? '' : String(v) }));
}

// 한 구간이 자재 **1매당** 배정하는 수량. 서버에 저장되는 `map_doe_source.qty`가 바로 이 값이다.
//
// ⚠️ **단일 구현이어야 한다.** 저장부와 표시부가 각자 계산하면 화면 숫자와 DB가 갈라진다 —
//    실제로 갈라져 있었다(저장 `Math.ceil` vs 자재 목록 `Math.round`). 총 100 / 3매면
//    DB에는 34가 저장되는데 화면은 33을 보여줬다. 서버 규약이 올림이므로 올림이 정본이고,
//    내림/반올림은 부족분을 숨긴다.
function bandShare(b) {
  const n = (b && Array.isArray(b.materials)) ? b.materials.length : 0;
  return n > 0 ? Math.ceil((Number(b.need) || 0) / n) : 0;
}

// 값 단위 파생 요약 (접힌 행·자재 그룹에서 공용)
function doeSummary(value) {
  const bands = getBands(value);
  const needSum = bands.reduce((a, b) => a + (Number(b.need) || 0), 0);
  const matCount = bands.reduce((a, b) => a + b.materials.length, 0);
  const stacks = bands.map(b => b.stack || '—').filter(Boolean);
  return { bands, needSum, matCount, stacks };
}

// ── 초안 (localStorage: 전체 충실도) ────────────────────
let saveTimer = null;
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => { saveDraft(); scheduleServerSave(); }, 500);
}

function saveDraft() {
  if (!doeScopeReady()) return;
  try {
    const does = {};
    S.doe.forEach((bands, v) => {
      does[v] = bands.map(b => ({
        seq: Number(b.seq) || 1,
        stack: b.stack || '',
        need: b.need === '' || b.need === null ? '' : Number(b.need) || 0,
        materials: (b.materials || []).map(m => ({ lot: m.lot, slot: m.slot || '' })),
        knobs: knobsToObject(b.knobs),
      }));
    });
    const draft = { version: DRAFT_VERSION, table: S.ctx.table, map_key: S.ctx.mapKey, does, saved_at: new Date().toISOString() };
    localStorage.setItem(draftKey(), JSON.stringify(draft));
    S.savedAt = draft.saved_at;
    renderPlanHead();
  } catch (e) {
    // 초안이 이 패널의 1차 저장소다 — 조용히 삼키면 사용자는 저장된 줄 알고 편집을 잃는다.
    // (실제로 이 catch가 리팩터링 중 누락된 헬퍼를 가려 저장이 통째로 죽어 있었다.)
    console.warn('[Legend & DOE] draft save failed:', e);
    showToast(`DOE 초안 저장 실패 — 편집이 보관되지 않았습니다 (${e && e.message ? e.message : e})`,
      'error', { dedupeKey: 'doe_draft_save_failed' });
  }
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(draftKey());
    if (!raw) return false;
    const obj = JSON.parse(raw);
    if (!obj || typeof obj !== 'object' || !obj.does) return false;
    S.doe = new Map();
    Object.entries(obj.does).forEach(([v, d]) => {
      // v4 이하 초안(단일 구간 객체) 하위호환 — 밴드 1개로 승격
      const arr = Array.isArray(d) ? d : [d];
      S.doe.set(String(v), arr.map((b, i) => ({
        seq: Number(b.seq) || (i + 1),
        stack: String(b.stack || ''),
        need: b.need === '' || b.need === null || b.need === undefined ? '' : Number(b.need) || 0,
        materials: Array.isArray(b.materials)
          ? b.materials.map(m => ({ lot: String(m.lot || ''), slot: String(m.slot || '') })).filter(m => m.lot) : [],
        knobs: knobsToArray(b.knobs),
      })));
    });
    S.savedAt = obj.saved_at || null;
    return true;
  } catch (e) { console.warn('[Legend & DOE] draft load failed:', e); return false; }
}

// ── 자재 가용 (source-summary) ──────────────────────────
function summaryKey(lot, slot) {
  const st = stageOfTable(S.ctx.table);
  return `${st ? st.id : S.ctx.table}::${lot}::${slot || ''}`;
}
function isPlainNotFound(status, body) {
  return (status === 405) || (status === 404 && (!body || body.detail === 'Not Found'));
}

async function getSourceSummary(lot, slot, force = false) {
  const key = summaryKey(lot, slot);
  const cached = S.summaries.get(key);
  if (!force && cached && (cached.status === 'ok' || cached.status === 'loading')) {
    if (cached.promise) await cached.promise;
    return S.summaries.get(key);
  }
  const st = stageOfTable(S.ctx.table);
  const entry = { status: 'loading' };
  entry.promise = (async () => {
    const params = new URLSearchParams({ stage: st ? st.id : '', lot: lot || '', slot: slot || '' });
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

// 서버 가용 응답의 **단일 해석 지점**.
//
// 가용량은 서버가 계산한다(`가용 = 총 − (fail ∪ transferred)`, SPEC §6.1). 클라는 읽기만 한다 —
// 여기에 두 번째 계산을 만들면 같은 숫자의 구현이 둘이 되고 반드시 갈라진다.
//
// 신뢰 표기 3층 방어(SPEC §6.2)를 **전부** 통과시킨다. 서버는 역할 바인딩이 강등되면
//   remaining: null · remaining_reliable: false · warnings[source_degraded]
// 셋을 함께 내려보낸다. 하나라도 서면 숫자를 확정값처럼 보여주지 않는다.
// 반환: { status, value, reliable, reason }
function availabilityOf(lot, slot) {
  const entry = S.summaries.get(summaryKey(lot, slot));
  if (!entry) return { status: null, value: null, reliable: false, reason: '아직 조회하지 않음' };
  if (entry.status !== 'ok') {
    return {
      status: entry.status, value: null, reliable: false,
      reason: entry.status === 'loading' ? '조회 중'
        : (entry.status === 'unsupported' ? '이 서버는 가용 집계를 제공하지 않습니다'
          : (entry.error || '가용 조회 실패')),
    };
  }
  const data = entry.data || {};
  const chips = data.chips || {};
  const raw = chips.remaining;
  const value = (raw === null || raw === undefined || Number.isNaN(Number(raw))) ? null : Number(raw);
  const flag = (data.remaining_reliable !== undefined) ? data.remaining_reliable : chips.remaining_reliable;
  const degraded = (Array.isArray(data.warnings) ? data.warnings : [])
    .map(w => String((w && (w.type || w.code)) || w))
    .filter(t => t === 'source_degraded' || t === 'availability_unreliable');
  const reasons = [];
  if (value === null) reasons.push('서버가 잔여 값을 주지 않았습니다');
  if (flag === false) reasons.push('서버 판정: 잔여 신뢰 불가');
  if (degraded.length > 0) reasons.push(`소스 강등(${degraded.join(', ')})`);
  return { status: 'ok', value, reliable: reasons.length === 0, reason: reasons.join(' · ') };
}

// 확정된 숫자만 필요한 호출부(왕복 전후 변화 감지)용 얇은 래퍼. 신뢰 불가는 null이다.
function availableOf(lot, slot) {
  const a = availabilityOf(lot, slot);
  return a.reliable ? a.value : null;
}

// ── 자재 맵 존재 여부 ───────────────────────────────────
function matMapCacheKey(table, m) { return `${table}|${m.lot}|${m.slot || ''}`; }

async function materialMetaValues(table, m) {
  let cols = S.keyColumns.get(table);
  if (!cols) {
    cols = controller && controller.fetchMapKeyColumns ? await controller.fetchMapKeyColumns(table) : [];
    S.keyColumns.set(table, cols || []);
  }
  const out = {};
  if (!cols || cols.length === 0) return out;
  if (cols.length === 1) { out[cols[0]] = m.slot ? `${m.lot}_${m.slot}` : m.lot; return out; }
  out[cols[0]] = m.lot;
  out[cols[1]] = m.slot || '';
  return out;
}

async function probeMaterialMap(table, m, force = false) {
  const ck = matMapCacheKey(table, m);
  if (!force && S.matMapState.has(ck)) return S.matMapState.get(ck);
  const metaValues = await materialMetaValues(table, m);
  const exists = (controller && controller.probeMapExists)
    ? await controller.probeMapExists(table, metaValues) : null;
  S.matMapState.set(ck, exists);
  return exists;
}

// ── 렌더: 계획 헤더 ─────────────────────────────────────
function renderPlanHead() {
  const box = elp.head;
  if (!box) return;
  const st = stageOfTable(S.ctx.table);
  const child = S.ctx.depth > 0;
  const stageBadge = child
    ? '<span class="tp-stage-badge material">자재 맵</span>'
    : (st ? `<span class="tp-stage-badge">${esc(st.name)}</span>`
          : '<span class="tp-stage-badge none">일반 맵 (legend)</span>');
  // [M5] "자동 저장 HH:MM"은 **로컬 초안**의 시각이다. 서버 저장이 실패했는데 이것만
  // 보여주면 사용자는 서버에 있다고 믿는다 → 실패·미확인 상태를 우선 표시한다.
  let savedChip;
  if (S.saveError) {
    savedChip = `<span class="tp-chip bad" title="${esc(S.saveError)}">⚠ 서버 저장 실패 · 초안만</span>`;
  } else if (S.deleteUnsent) {
    // Covering an unsent deletion with "자동 저장 HH:MM" is how a delete evaporates silently.
    savedChip = '<span class="tp-chip bad" title="마지막 항목까지 지운 상태는 서버에 보낼 수 없어 삭제가 반영되지 않았습니다 — 항목을 하나라도 남기면 저장됩니다">⚠ 삭제 미반영</span>';
  } else if (stageOfTable(S.ctx.table) && S.ctx.depth === 0 && S.planTablesSupported !== false && !S.doeServerLoaded) {
    savedChip = '<span class="tp-chip warn" title="서버 DOE 조회에 실패했습니다 — 잔재 정리를 하지 않습니다">⚠ 서버 상태 미확인</span>';
  } else {
    const savedTxt = S.savedAt
      ? `자동 저장 ${new Date(S.savedAt).toTimeString().slice(0, 5)}`
      : (S.serverSavedAt ? `서버 ${esc(S.serverSavedAt)}` : '변경 시 자동 저장');
    savedChip = `<span class="tp-chip dim" title="legend와 동일한 디바운스 자동 업서트">${esc(savedTxt)}</span>`;
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

// ── 렌더: DOE LIST (= legend) ───────────────────────────
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
    box.innerHTML = '<div class="tp-empty">정의된 값이 없습니다. 우상단 [+ DOE]로 만드세요.</div>';
    return;
  }

  box.innerHTML = S.legendRows.map(row => {
    const v = String(row.value);
    const open = S.openValue === v;
    const brush = S.activeBrush === v;
    return `<div class="tp-doe ${open ? 'open' : ''} ${brush ? 'on' : ''}" data-v="${esc(v)}">
      <div class="tp-doe-row">
        <span class="tp-caret">▶</span>
        <span class="tp-sw" style="background:${esc(row.color || '#6b7280')}">${esc(v)}</span>
        <span class="tp-doe-body">
          <span class="tp-doe-l1">${esc(row.desc || '(설명 없음)')}${brush ? '<span class="tp-brush-tag">브러시</span>' : ''}</span>
          <span class="tp-doe-l2" data-count-for="${esc(v)}">${esc(doeLine2(v, planMode))}</span>
        </span>
      </div>
      ${open ? renderDoeDetail(row, planMode) : '<div class="tp-doe-detail-stub"></div>'}
    </div>`;
  }).join('');

  bindDoeList(box, planMode);
}

// 접힌 행의 2번째 줄. 구간이 여러 개면 개수·합계로 접어 보여준다(행이 세로로 자라지 않게).
function doeLine2(value, planMode) {
  const painted = Number(S.counts[value] || 0);
  if (!planMode) return `칠함 ${painted}`;
  const { bands, needSum, matCount, stacks } = doeSummary(value);
  if (bands.length === 0) return `구간 없음 · ${painted} / —`;
  if (bands.length === 1) {
    const b = bands[0];
    const matTxt = b.materials.length === 0 ? '자재 미지정'
      : (b.materials.length === 1 ? matLabel(b.materials[0]) : `${matLabel(b.materials[0])} 외 ${b.materials.length - 1}매`);
    return `STACK ${b.stack || '—'} · ${matTxt} · ${painted} / ${b.need === '' ? '—' : b.need}`;
  }
  return `구간 ${bands.length}개 [${stacks.join(' / ')}] · 자재 ${matCount}매 · ${painted} / ${needSum || '—'}`;
}

// 밴드(구간) 카드 하나 — STACK 라벨 + 총 소요 + 자재 묶음 + knob
function renderBand(b, single) {
  return `<div class="tp-band" data-seq="${b.seq}">
    <div class="tp-asg-l1">
      <span class="tp-fld"><label>STACK 구간</label>
        <input class="glass-input mono tp-b-stack" value="${esc(b.stack || '')}"
          placeholder="1, 2-15, 16" title="자유 입력 — 쉼표로 여러 구간을 적을 수 있습니다 (예: 1, 2-15, 16)" /></span>
      <span class="tp-fld"><label>총 소요</label>
        <input class="glass-input mono tp-b-need" type="number" min="0" value="${esc(b.need === '' ? '' : b.need)}" /></span>
      ${single ? '' : '<button type="button" class="tp-band-del" title="이 구간 삭제">🗑</button>'}
    </div>
    <div class="tp-matchips">
      ${b.materials.map((m, i) => `<span class="tp-matchip">${esc(matLabel(m))}<button type="button" class="tp-mat-del" data-i="${i}" title="묶음에서 제거">✕</button></span>`).join('')}
      <span class="tp-matchip add tp-mat-add">＋ 자재</span>
    </div>
    <div class="tp-mat-addbox" style="display:none;">
      <span class="bp-ac-wrap"><input class="glass-input mono tp-mat-input" placeholder="lot|slot" autocomplete="off" /></span>
      <button type="button" class="glass-page-btn tp-mat-ok">추가</button>
    </div>
    <div class="tp-knobs">
      ${b.knobs.map((p, i) => `<span class="tp-knob" data-ki="${i}">
        <input class="tp-knob-k" placeholder="knob" value="${esc(p.k || '')}" />
        <span>=</span>
        <input class="tp-knob-v" placeholder="값" value="${esc(p.v || '')}" />
        <button type="button" class="tp-knob-del" title="삭제">✕</button></span>`).join('')}
      <button type="button" class="glass-page-btn tp-knob-add">+ knob</button>
    </div>
  </div>`;
}

function renderDoeDetail(row, planMode) {
  const v = String(row.value);
  const bands = getBands(v);
  const planFields = planMode ? `
    <div class="tp-sec">
      <div class="tp-sec-h"><span>STACK 구간 · 자재</span>
        <button type="button" class="glass-page-btn tp-band-add" title="이 값에 구간을 하나 더 추가 (구간마다 다른 자재를 쓸 때)">+ 구간</button></div>
      ${bands.length === 0
        ? '<div class="tp-hint">구간이 없습니다. [+ 구간]으로 만드세요.</div>'
        : bands.map(b => renderBand(b, bands.length === 1)).join('')}
      <span class="tp-hint">한 칸에 <b>쉼표로 여러 구간</b>(<span class="mono">1, 2-15, 16</span>)을 적으면 같은 자재 묶음으로 여러 층대를 덮습니다.
        구간마다 <b>자재가 다르면</b> [+ 구간]으로 행을 나누십시오.</span>
    </div>` : '';

  return `<div class="tp-doe-detail">
    <div class="tp-sec">
      <div class="tp-asg-l1">
        <span class="tp-fld"><label>VALUE (페인팅 값)</label>
          <input class="glass-input mono tp-d-val" value="${esc(v)}" /></span>
        <span class="tp-fld"><label>색</label>
          <input type="color" class="tp-d-color" value="${esc(row.color || '#6b7280')}" /></span>
      </div>
    </div>
    ${planFields}
    <div class="tp-sec">
      <div class="tp-sec-h"><span>설명 (split registry 서술과 동일 필드)</span>
        <button type="button" class="tp-doe-del" title="이 값 삭제">🗑</button></div>
      <textarea class="glass-input tp-d-desc" rows="2" placeholder="이 값이 무슨 조건인지">${esc(row.desc || '')}</textarea>
    </div>
  </div>`;
}

function bindDoeList(box, planMode) {
  box.querySelectorAll('.tp-doe').forEach(node => {
    const v = node.dataset.v;
    const row = node.querySelector('.tp-doe-row');
    // 행 클릭 = ① 선택 ② 브러시 전환 ③ 펼침 — 한 동작으로 셋 다. 한 번에 하나만 펼친다.
    row.addEventListener('click', () => {
      S.openValue = (S.openValue === v) ? null : v;
      if (controller && controller.setBrush) controller.setBrush(v);
      S.activeBrush = v;
      renderDoeList();
      renderMaterialPane();
    });

    const detail = node.querySelector('.tp-doe-detail');
    if (!detail) return;
    detail.addEventListener('click', e => e.stopPropagation());

    const valIn = detail.querySelector('.tp-d-val');
    valIn.addEventListener('change', () => {
      const nv = valIn.value.trim();
      if (!nv || nv === v) { valIn.value = v; return; }
      const r = controller.updateLegendRow(v, { value: nv });
      if (!r.ok) { showToast(r.error, 'warning'); valIn.value = v; return; }
      // DOE 밴드도 새 value로 이사시킨다 (안 하면 구간·자재가 통째로 유실된다)
      const bands = getBands(v);
      S.doe.set(nv, bands); S.doe.delete(v);
      if (S.openValue === v) S.openValue = nv;
      scheduleSave();
    });
    detail.querySelector('.tp-d-color').addEventListener('change', e => {
      controller.updateLegendRow(v, { color: e.target.value });
    });
    detail.querySelector('.tp-d-desc').addEventListener('change', e => {
      controller.updateLegendRow(v, { desc: e.target.value.trim() });
    });
    detail.querySelector('.tp-doe-del').addEventListener('click', () => {
      if (!confirm(`값 '${v}'을(를) 삭제할까요? (격자에서 이 값이 지워집니다)`)) return;
      const r = controller.deleteLegendRow(v);
      if (!r.ok) { showToast(r.error, 'warning'); return; }
      S.doe.delete(v);
      if (S.openValue === v) S.openValue = null;
      scheduleSave();
    });

    if (!planMode) return;

    const addBtn = detail.querySelector('.tp-band-add');
    if (addBtn) addBtn.addEventListener('click', () => {
      addBand(v);            // band_seq = max+1 (재번호 없음)
      scheduleSave(); renderDoeList(); renderMaterialPane();
    });

    detail.querySelectorAll('.tp-band').forEach(bandNode => {
      const seq = Number(bandNode.dataset.seq);
      const b = getBand(v, seq);
      if (!b) return;

      bandNode.querySelector('.tp-b-stack').addEventListener('change', e => {
        b.stack = e.target.value.trim();       // 라벨은 비키 — 고쳐도 자재 묶음이 유지된다
        scheduleSave(); renderDoeList(); renderMaterialPane();
      });
      bandNode.querySelector('.tp-b-need').addEventListener('change', e => {
        b.need = e.target.value === '' ? '' : (Number(e.target.value) || 0);
        scheduleSave(); renderDoeList(); renderMaterialPane();
      });
      const delBtn = bandNode.querySelector('.tp-band-del');
      if (delBtn) delBtn.addEventListener('click', () => {
        const bands = getBands(v);
        const i = bands.findIndex(x => Number(x.seq) === seq);
        if (i >= 0) bands.splice(i, 1);        // ⚠️ 남은 밴드의 seq는 **재번호하지 않는다**
        scheduleSave(); renderDoeList(); refreshMaterials();
      });

      bandNode.querySelectorAll('.tp-mat-del').forEach(btn => {
        btn.addEventListener('click', () => {
          b.materials.splice(Number(btn.dataset.i), 1);
          scheduleSave(); renderDoeList(); refreshMaterials();
        });
      });
      const addChip = bandNode.querySelector('.tp-mat-add');
      const addBox = bandNode.querySelector('.tp-mat-addbox');
      if (addChip && addBox) {
        const input = addBox.querySelector('.tp-mat-input');
        const commit = () => {
          const { lot, slot } = parseSource(input.value);
          if (!lot) return;
          if (b.materials.some(m => m.lot === lot && (m.slot || '') === (slot || ''))) {
            showToast('이미 이 구간의 묶음에 있는 자재입니다.', 'warning'); return;
          }
          b.materials.push({ lot, slot });
          scheduleSave(); renderDoeList(); refreshMaterials();
        };
        addChip.addEventListener('click', () => {
          addBox.style.display = 'flex';
          input.focus();
          attachAutocomplete(input, sourceNodeLabel(), val => { input.value = val; commit(); });
        });
        addBox.querySelector('.tp-mat-ok').addEventListener('click', commit);
        input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); commit(); } });
      }

      const knobAdd = bandNode.querySelector('.tp-knob-add');
      if (knobAdd) knobAdd.addEventListener('click', () => { b.knobs.push({ k: '', v: '' }); scheduleSave(); renderDoeList(); });
      bandNode.querySelectorAll('.tp-knob').forEach(kn => {
        const ki = Number(kn.dataset.ki);
        kn.querySelector('.tp-knob-k').addEventListener('change', e => { if (b.knobs[ki]) { b.knobs[ki].k = e.target.value; scheduleSave(); } });
        kn.querySelector('.tp-knob-v').addEventListener('change', e => { if (b.knobs[ki]) { b.knobs[ki].v = e.target.value; scheduleSave(); } });
        kn.querySelector('.tp-knob-del').addEventListener('click', () => { b.knobs.splice(ki, 1); scheduleSave(); renderDoeList(); });
      });
    });
  });
}

function sourceNodeLabel() {
  const st = stageOfTable(S.ctx.table);
  if (!st) return 'Wafer';
  return st.sourceKind === 'core' ? 'Wafer' : 'Tape';
}

// ── 렌더: 사용 자재 (자재 ID가 키, 이동 허브) ─────────────
//
// 사용자의 시점은 **자재**다: "이 테이프, 얼마 남았고 어디에 얼마나 썼나."
// 그래서 행의 단위는 (값, 구간)이 아니라 **자재 ID(lot|slot)** 하나다. 종전처럼 (값, 구간)으로
// 묶으면 같은 자재가 여러 그룹에 흩어져, 그 자재의 총 사용량이 화면 어디에도 없었다
// (실데이터: `TOP`이 값 1·구간 16에 12개, 값 F·구간 16에 10개 — 합 22를 아무도 보여주지 않았다).
// (값, 구간)은 사라지지 않고 그 자재를 소비한 **자리**로 행 안에 접혀 들어간다.
function materialRollup() {
  const st = stageOfTable(S.ctx.table);
  if (!st || S.ctx.depth > 0) return [];
  const byMat = new Map();   // matKey -> { lot, slot, used, uses[] }
  S.legendRows.forEach(row => {
    const v = String(row.value);
    getBands(v).forEach(b => {
      if (b.materials.length === 0) return;
      const qty = bandShare(b);   // 저장되는 map_doe_source.qty와 같은 식 (단일 구현)
      b.materials.forEach(m => {
        const k = matKey(m);
        if (!byMat.has(k)) byMat.set(k, { lot: m.lot, slot: m.slot || '', used: 0, uses: [] });
        const e = byMat.get(k);
        e.used += qty;
        e.uses.push({ value: v, color: row.color, seq: b.seq, stack: b.stack, qty });
      });
    });
  });
  // 자재 ID 순 — 목록이 편집 순서에 따라 튀지 않게 한다
  return [...byMat.values()].sort((a, b) => (a.lot === b.lot
    ? String(a.slot).localeCompare(String(b.slot))
    : String(a.lot).localeCompare(String(b.lot))));
}

function renderMaterialPane() {
  const box = elp.matPane;
  if (!box) return;
  const mats = materialRollup();
  const st = stageOfTable(S.ctx.table);

  if (S.ctx.depth > 0) {
    // 자재 맵을 연 상태 — 허브 대신 이 맵에서 할 일을 안내한다
    box.style.display = 'flex';
    box.innerHTML = `
      <div class="tp-mat-head"><b>📦 자재 맵 편집 중</b>
        <button type="button" class="glass-page-btn" id="tp-frame-back">← 돌아가기</button></div>
      <div class="tp-mat-body">
        <p class="tp-hint">이 맵도 실맵입니다 — 오버레이·페인팅·<b>⚡ Push</b>가 그대로 동작합니다.
          맵 키 잠금과 정체성 핀도 동일하게 적용됩니다.</p>
        <div class="tp-ov-suggest">
          <span class="tp-hint">겹쳐 보기:</span>
          ${SOURCE_OVERLAY_SUGGESTIONS.map(s => `<button type="button" class="glass-page-btn tp-ov-add" data-tbl="${esc(s.table)}">＋ ${esc(s.label)}</button>`).join('')}
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

  if (!st || mats.length === 0) {
    // 계획 대상이 아닌 맵이거나 자재 0건 → 자재 영역은 자리를 차지하지 않는다
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  box.style.display = 'flex';

  const { table: srcTable, derived: srcDerived } = sourceTableOf(st);
  const sel = S.openValue || S.activeBrush || '';
  const rows = mats.map(m => {
    const av = availabilityOf(m.lot, m.slot);
    // 신뢰 불가는 **숫자를 보여주지 않는다** — 강등된 값을 확정값처럼 보이면 계획이 틀린다.
    const availHtml = (av.status === null || av.status === 'loading')
      ? '<span class="tp-unknown-val">…</span>'
      : (av.reliable
        ? `<b>${av.value}</b>`
        : `<span class="tp-unknown-val" title="${esc(av.reason + (av.value === null ? '' : ` (서버 원값 ${av.value})`))}">미상</span>`);
    const exists = srcTable ? S.matMapState.get(matMapCacheKey(srcTable, m)) : null;
    const mapChip = exists === true ? '<span class="tp-chip ok">맵 ✓</span>'
      : (exists === false ? '<span class="tp-chip warn">맵 없음</span>'
        : '<span class="tp-chip dim">맵 미상</span>');
    // "어디에 몇 개씩" — 이 자재를 소비한 (값, 구간)과 그 수량. 항상 펼쳐 둔다(읽기 무마찰).
    const uses = m.uses.map(u => `<span class="tp-use ${sel && sel === u.value ? 'on' : ''}"
        title="DOE ${esc(u.value)} · STACK ${esc(u.stack || '—')} 에 ${u.qty}개 배정">
        <i style="background:${esc(u.color || '#6b7280')}"></i>${esc(u.value)}·${esc(u.stack || '—')} <b>${u.qty}</b></span>`).join('');
    const on = !!sel && m.uses.some(u => u.value === sel);
    return `<div class="tp-mat-row ${on ? 'on' : ''}" data-lot="${esc(m.lot)}" data-slot="${esc(m.slot || '')}" title="클릭 = 이 자재의 맵 열기">
      ${S.flash.has(matKey(m)) ? '<span class="tp-flash go"></span>' : ''}
      <div class="tp-mat-l1">
        <span class="tp-mat-id">${esc(matLabel(m))}</span>
        <span class="tp-mat-qty">가용 ${availHtml} · 사용 <b>${m.used}</b></span>
        ${mapChip}
      </div>
      <div class="tp-uses">${uses}</div>
    </div>`;
  }).join('');

  box.innerHTML = `
    <div class="tp-mat-head"><b>📦 사용 자재 <span class="tp-chip">${mats.length}</span></b>
      <button type="button" class="glass-page-btn" id="tp-mat-refresh">↻ 가용 재조회</button></div>
    <div class="tp-mat-scroll">${rows}</div>
    <div class="tp-mat-hint">가용 = 서버 집계(총 − fail ∪ 전사) · 사용 = 이 계획이 배정한 합 · 행 클릭 = 그 자재의 맵을 엽니다${
      srcTable
        ? ` · 대상 <b>${esc(srcTable)}</b>${srcDerived === 'fallback'
            ? ' <span class="tp-chip warn" title="stage 선언에서 유도하지 못해 하드코딩 폴백을 씁니다 — 서버에 명시 선언 요청됨">추정</span>'
            : ''}`
        : ' · <b class="tp-mat-nosrc">자재 맵 테이블 미상 — stage 선언 확인 필요</b>'
    }</div>`;

  box.querySelector('#tp-mat-refresh').addEventListener('click', () => refreshMaterials(true));
  box.querySelectorAll('.tp-mat-row').forEach(r => {
    r.addEventListener('click', () => openMaterial(r.dataset.lot, r.dataset.slot));
  });
  // 선택된 DOE를 쓰는 첫 자재를 시야로 (필터 금지 — 전체가 보여야 한다)
  const onRow = box.querySelector('.tp-mat-row.on');
  if (onRow) onRow.scrollIntoView({ block: 'nearest' });
  S.flash.clear();
}

// ── 자재 맵 왕복 ────────────────────────────────────────
async function openMaterial(lot, slot) {
  if (S.navBusy) return;
  const st = stageOfTable(S.ctx.table);
  const table = sourceTableOfStage(st);
  if (!table) { showToast('자재 맵 테이블을 알 수 없습니다 (stage 선언 확인 필요).', 'warning'); return; }
  const m = { lot, slot: slot || '' };
  S.navBusy = true;
  try {
    const metaValues = await materialMetaValues(table, m);
    if (Object.keys(metaValues).length === 0) {
      showToast(`${table}의 맵 키 컬럼을 읽지 못했습니다.`, 'error'); return;
    }
    const r = await controller.openMapFrame({
      table, metaValues,
      presetKind: st.sourceKind === 'core' ? 'core' : 'tape',
    });
    if (!r || !r.ok) showToast(`자재 맵 열기 실패: ${(r && r.error) || '알 수 없음'}`, 'error');
  } finally {
    S.navBusy = false;
  }
}

// ★ 왕복의 보상 — 복귀 시 **그 자재만** 재조회해 수량·맵 유무를 갱신하고,
//   값이 실제로 바뀌었을 때만 1회 하이라이트한다(매번 번쩍이면 신호가 죽는다).
async function rewardAfterReturn(from) {
  if (!from || !from.mapKey) return;
  const st = stageOfTable(S.ctx.table);
  const table = sourceTableOfStage(st);
  if (!table || from.table !== table) return;

  // 맵 키(lot_slot)를 자재 식별자로 되돌린다
  const cols = S.keyColumns.get(table) || [];
  const parts = String(from.mapKey).split('_');
  const m = (cols.length >= 2 && parts.length >= 2)
    ? { lot: parts.slice(0, parts.length - 1).join('_'), slot: parts[parts.length - 1] }
    : { lot: from.mapKey, slot: '' };

  const before = { avail: availableOf(m.lot, m.slot), exists: S.matMapState.get(matMapCacheKey(table, m)) };
  const entry = await getSourceSummary(m.lot, m.slot, true);
  const exists = await probeMaterialMap(table, m, true);
  const after = { avail: availableOf(m.lot, m.slot), exists };

  if (entry && entry.status === 'error') {
    showToast(`자재 ${matLabel(m)} 가용 재조회 실패 — 미상으로 표시합니다. [↻ 가용 재조회]로 다시 시도하십시오.`, 'warning');
  }
  // 자재 ID가 행의 키이므로 점멸 대상도 자재 하나다 (종전엔 그룹마다 중복 등록해야 했다)
  if (before.avail !== after.avail || before.exists !== after.exists) {
    S.flash.add(matKey(m));
  }
  renderMaterialPane();
}

// 자재 목록의 가용·맵 유무 일괄 갱신.
// 롤업이 이미 자재 ID로 접혀 있으므로 중복 조회 방어가 따로 필요 없다(종전 `seen` Map 폐기).
async function refreshMaterials(force = false) {
  const seq = ++S.matSeq;
  const st = stageOfTable(S.ctx.table);
  const table = sourceTableOfStage(st);
  const mats = materialRollup();
  if (mats.length === 0) { renderMaterialPane(); return; }
  renderMaterialPane();
  await Promise.all(mats.map(async m => {
    await getSourceSummary(m.lot, m.slot, force);
    if (table) await probeMaterialMap(table, m, force);
  }));
  if (seq !== S.matSeq) return;
  renderMaterialPane();
}

// ── 자동완성 (그래프 노드) ──────────────────────────────
function attachAutocomplete(input, label, onPick) {
  if (input.dataset.acBound === '1') return;
  input.dataset.acBound = '1';
  const wrap = input.closest('.bp-ac-wrap') || input.parentElement;
  if (!wrap) return;
  const list = document.createElement('div');
  list.className = 'bp-ac-list';
  list.style.display = 'none';
  wrap.appendChild(list);
  let seq = 0, timer = null;
  const hide = () => { list.style.display = 'none'; };
  const search = async (q) => {
    const my = ++seq;
    try {
      const params = new URLSearchParams({ q, label, limit: '15' });
      const res = await fetch(`${API_BASE}/graph/nodes/search?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (my !== seq) return;
      const items = (Array.isArray(data) ? data : (data.nodes || data.results || data.items || []))
        .filter(x => x && x.identity_key !== undefined);
      if (!items.length) list.innerHTML = `<div class="bp-ac-empty">일치 노드 없음 (label=${esc(label)}) — 수기 입력 가능</div>`;
      else {
        list.innerHTML = items.map(x => `<div class="bp-ac-item" data-v="${esc(String(x.identity_key))}">${esc(String(x.identity_key))}</div>`).join('');
        list.querySelectorAll('.bp-ac-item').forEach(item => {
          item.addEventListener('mousedown', e => { e.preventDefault(); hide(); onPick(item.dataset.v); });
        });
      }
      list.style.display = 'block';
    } catch (e) { if (my === seq) hide(); }
  };
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { hide(); return; }
    timer = setTimeout(() => search(q), 200);
  });
  input.addEventListener('blur', () => setTimeout(hide, 120));
  input.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
}

// ── 서버 영속화 (계약 v2 — 키 조립은 doeRowKey/doeSourceRowKey 두 함수에서만) ──
function looksLikeMissingTable(status, body) {
  if (status === 404 || status === 405) return true;
  const detail = body && typeof body.detail === 'string' ? body.detail : '';
  return /not\s*found|없|unknown table|존재하지/i.test(detail);
}

// A DOE save is one write of the plan's COMPLETE set, so it goes out as `replace_map`:
// the server purges everything in scope (map_key_columns = ref_table|map_key, declared
// in server/product_tables.py) and writes what we sent. Removing a value, a band or a
// material is therefore expressed by its absence - there is no separate delete step.
async function putUpdates(table, updates, replaceMap) {
  const res = await fetch(`${API_BASE}/tables/${table}/data/updates`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates, replace_map: !!replaceMap }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const err = new Error((body && typeof body.detail === 'string') ? body.detail : `HTTP ${res.status}`);
    err.missingTable = looksLikeMissingTable(res.status, body);
    throw err;
  }
  return res.json().catch(() => ({}));
}

function cellVal(rowData, col) {
  const c = rowData ? rowData[col] : undefined;
  return c && typeof c === 'object' ? c.value : undefined;
}

// STACK 라벨은 **자유 텍스트 그대로 저장**한다. 파싱하지 않는다 —
// `1, 2-15, 16` / `H1~H2` / `바닥` 어느 표기든 사용자가 쓰던 대로 보관하는 것이 계약이다.
// (수치 해석이 필요한 검증은 서버 몫이고, 이번 범위에서는 보류 상태다.)

let serverSaveTimer = null;
function scheduleServerSave() {
  clearTimeout(serverSaveTimer);
  serverSaveTimer = setTimeout(() => { saveDoeToServer(); }, 1200);
}

// legend와 동일한 규율의 디바운스 자동 업서트 ([저장]/[확정] 버튼 폐기).
// 저장 단위: map_doe 1행 = (값, 구간) · map_doe_source 1행 = (값, 구간, 자재)
async function saveDoeToServer() {
  if (!doeScopeReady() || S.planTablesSupported === false) return;
  if (!stageOfTable(S.ctx.table) || S.ctx.depth > 0) return; // 계획 대상 맵에서만

  // [B2 형제 결함] 서버 상태를 모르면 **삭제뿐 아니라 쓰기도 하면 안 된다.**
  // 실측(주입 테스트): 로드 실패 후 편집하면 band_seq가 1부터 다시 매겨져
  // 서버의 기존 `…|F|1` 행을 **덮어써** stack_band·qty_total이 날아갔다.
  // 삭제만 막고 쓰기를 허용하면 데이터 소실 경로가 그대로 남는다.
  if (!S.doeServerLoaded) {
    const seq = S.loadSeq;
    // 일시적 장애였을 수 있으니 **한 번 회복을 시도**한다
    const retry = await loadDoeFromServer();
    if (seq !== S.loadSeq) return;   // 재시도 중 맵이 바뀌었다 — 이전 맵의 응답을 채택하지 않는다
    if (!retry.ok) {
      S.saveError = `서버 상태 미확인 — 저장 보류 (${retry.error || '조회 실패'})`;
      renderPlanHead();
      showToast(
        '서버 DOE 상태를 확인하지 못해 **서버 저장을 보류**했습니다 — 편집은 브라우저 초안에만 있습니다. '
        + '맵을 다시 로드하면 재시도합니다.',
        'warning', { dedupeKey: 'doe_save_deferred' });
      return;
    }
    if (retry.unsupported) { S.saveError = null; renderPlanHead(); return; }  // 계획 저장 미지원 서버 = 초안 모드
    // [C1] 회복 성공 — 화면은 **서버 상태를 한 번도 보지 못한 초안**이다.
    // 그 초안으로 업서트·prune을 하면 서버본을 덮어쓰고 차집합 전부를 지운다.
    // → 서버본을 채택하고 **이 저장 사이클은 쓰기 없이 끝낸다.**
    //   그 사이 편집분은 조용히 버리지 않는다 — 브라우저 초안에 그대로 남아 있고, 사실만 알린다.
    adoptServerDoe(retry);
    S.saveError = null;
    renderAll();
    showToast(
      '서버 계획을 불러왔습니다. 조회 실패 중 편집한 내용은 서버에 반영되지 않았고 브라우저 초안에 남아 있습니다.',
      'warning', { dedupeKey: 'doe_server_recovered' });
    return;
  }

  const nowStr = getLocalTimeString();
  // 이 저장 사이클이 속한 맵. 헤더 칩은 **현재 맵**의 상태를 말하므로, 저장 중 맵이 바뀌면
  // 이 사이클의 결과로 새 맵 헤더를 오염시키면 안 된다(토스트는 맵 스코프가 아니라 그대로 알린다).
  const saveSeq = S.loadSeq;
  const saveScope = `${S.ctx.table} · ${S.ctx.mapKey}`;

  const doeUpdates = [];
  const srcUpdates = [];
  S.legendRows.forEach(row => {
    const v = String(row.value);
    getBands(v).forEach(b => {
      const seq = Number(b.seq) || 1;
      doeUpdates.push({
        business_key_val: doeRowKey(v, seq),
        updates: {
          doe_key: doeRowKey(v, seq),
          ref_table: S.ctx.table, map_key: S.ctx.mapKey,
          doe_value: v, band_seq: seq,
          stack_band: b.stack || '',        // 자유 텍스트 라벨 (비키)
          qty_total: Number(b.need) || 0,
          knobs: JSON.stringify(knobsToObject(b.knobs)),
          note: '',
          updated_by: CURRENT_USER, eventtime: nowStr,
        },
        source_name: 'user', updated_by: CURRENT_USER,
      });
      // 자재 묶음은 값이 아니라 **구간**에 붙는다 — band_seq를 반드시 함께 쓴다.
      // 빠뜨리면 서버가 그 구간의 묶음을 못 찾아 source_unresolved가 뜬다.
      // [M6] 배분식은 `bandShare` 하나뿐이다 — 자재 목록이 보여주는 수량과 여기 저장되는
      //      `qty`가 같은 함수에서 나와야 화면과 DB가 갈라지지 않는다.
      const share = bandShare(b);
      b.materials.forEach(m => {
        srcUpdates.push({
          business_key_val: doeSourceRowKey(v, seq, m.lot, m.slot),
          updates: {
            source_key: doeSourceRowKey(v, seq, m.lot, m.slot),
            ref_table: S.ctx.table, map_key: S.ctx.mapKey,
            doe_value: v, band_seq: seq,
            source_lot: m.lot, source_slot: m.slot || '',
            qty: share, note: '',
            updated_by: CURRENT_USER, eventtime: nowStr,
          },
          source_name: 'user', updated_by: CURRENT_USER,
        });
      });
    });
  });

  // `replace_map` takes its scope from updates[0], so an EMPTY set is not a write the
  // server can act on - it would silently leave the plan's rows in place. That is a
  // deletion we cannot express, and it must not be reported as a completed save.
  // (Reachable: drop the last material of every band -> srcUpdates is empty.)
  const cannotExpress = (doeUpdates.length === 0 && S.serverRows.doe > 0)
    || (srcUpdates.length === 0 && S.serverRows.source > 0);

  try {
    if (doeUpdates.length > 0) await putUpdates(DOE_TABLE, doeUpdates, true);
    if (srcUpdates.length > 0) await putUpdates(DOE_SOURCE_TABLE, srcUpdates, true);
    S.planTablesSupported = true;
    S.serverSavedAt = nowStr;
    S.saveError = null;
    // What the plan now holds on the server. Used only to tell "nothing to clear"
    // apart from "we could not express the clear" above - never to decide what to delete.
    if (doeUpdates.length > 0) S.serverRows.doe = doeUpdates.length;
    if (srcUpdates.length > 0) S.serverRows.source = srcUpdates.length;

    // The header chip speaks for the CURRENT map, so a cycle that outlived a map
    // switch must not write to it. The toast is not map-scoped and names its map.
    if (saveSeq === S.loadSeq) S.deleteUnsent = cannotExpress;
    if (cannotExpress) {
      showToast(`${saveScope} — 마지막 항목까지 지운 상태는 서버에 보낼 수 없어 **삭제가 반영되지 않았습니다.** `
        + '항목을 하나라도 남기면 저장됩니다.',
        'warning', { dedupeKey: 'doe_delete_unsent' });
    }
    renderPlanHead();
  } catch (e) {
    if (e && e.missingTable) {
      S.planTablesSupported = false;
      S.saveError = null;   // 미지원 서버는 실패가 아니라 초안 모드다
      renderPlanHead();
      return;
    }
    // [M5] saveDraft와 **같은 규율** — 저장 실패를 조용히 삼키면
    // 사용자는 "자동 저장됨"을 보면서 서버에 없는 편집을 계속하게 된다.
    S.saveError = e && e.message ? e.message : String(e);
    console.warn('[Legend & DOE] server upsert failed:', e);
    showToast(`DOE 서버 저장 실패 — 이 편집은 브라우저 초안에만 있습니다 (${S.saveError})`,
      'error', { dedupeKey: 'doe_server_save_failed' });
    renderPlanHead();
  }
}

// [removed] `pruneScoped` — the client-side difference-and-delete step.
//
// It existed because a DOE save was an upsert, which can only add and overwrite, so
// something had to go back and delete what the user removed. That second step was
// conditional, and when it did not run the removal simply did not happen.
//
// The platform already had the operation: `replace_map` (crud.py, apply_batch_updates)
// purges a table's rows inside the map's scope and rewrites them in one transaction.
// It needed `map_key_columns` to know that scope, which map_doe / map_doe_source /
// map_split_registry did not declare - so it could never have worked, and the
// difference was computed beside it instead. The declaration now lives in
// server/product_tables.py and deletion falls out of the write.
//
// The C1 invariant survives this, in a simpler form: it was "only delete the
// difference if the screen came from the server"; it is now "only replace if the
// screen came from the server" (S.doeServerLoaded, checked once before the write).

// 서버에서 DOE 밴드·자재를 복원한다.
// ⚠️ **로컬 초안 유무와 무관하게 항상 호출된다** — 초안이 있다고 건너뛰면
//    다른 세션이 저장한 계획을 못 본 채 그 위에 replace를 걸어 지워버린다.
// 반환: { ok, rowCount } — ok=false면 호출부가 그 사실을 **상태로 보존**해야 한다.
async function loadDoeFromServer() {
  if (!doeScopeReady()) return { ok: false, rowCount: 0 };
  const filters = {
    ref_table: { filterType: 'text', type: 'equals', filter: S.ctx.table },
    map_key: { filterType: 'text', type: 'equals', filter: S.ctx.mapKey },
  };
  const qs = `limit=500&filters=${encodeURIComponent(JSON.stringify(filters))}`;
  try {
    const res = await fetch(`${API_BASE}/tables/${DOE_TABLE}/data?${qs}`);
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      if (looksLikeMissingTable(res.status, body)) {
        // 테이블 자체가 없다 = 이 서버는 계획 저장을 지원하지 않는다(초안 모드). 실패가 아니다.
        S.planTablesSupported = false;
        return { ok: true, rowCount: 0, unsupported: true };
      }
      return { ok: false, rowCount: 0, error: `HTTP ${res.status}` };
    }
    S.planTablesSupported = true;
    const data = await res.json();
    const rows = (data && Array.isArray(data.data)) ? data.data : [];
    if (typeof data.total === 'number' && data.total > rows.length) {
      // 절단된 응답으로 서버 상태를 안다고 주장하면 안 된다 → 로드 실패로 취급
      return { ok: false, rowCount: rows.length, error: `응답 절단 (${data.total} > ${rows.length})` };
    }

    const byValue = new Map();
    rows.forEach(r => {
      const x = r.data || {};
      const v = String(cellVal(x, 'doe_value') ?? '');
      if (!v) return;
      let knobs = {};
      try { const raw = cellVal(x, 'knobs'); if (raw) knobs = JSON.parse(String(raw)); } catch (e) { /* 파손 */ }
      if (!byValue.has(v)) byValue.set(v, []);
      byValue.get(v).push({
        seq: Number(cellVal(x, 'band_seq')) || 1,
        stack: String(cellVal(x, 'stack_band') ?? ''),
        need: Number(cellVal(x, 'qty_total')) || '',
        materials: [],
        knobs: knobsToArray(knobs),
      });
    });

    // 자재 묶음을 (값, 구간)에 붙인다 — 이 조회도 실패하면 로드 전체를 실패로 본다
    const sres = await fetch(`${API_BASE}/tables/${DOE_SOURCE_TABLE}/data?${qs}`);
    if (!sres.ok) return { ok: false, rowCount: rows.length, error: `source HTTP ${sres.status}` };
    const sd = await sres.json();
    const srows = (sd && Array.isArray(sd.data)) ? sd.data : [];
    if (typeof sd.total === 'number' && sd.total > srows.length) {
      return { ok: false, rowCount: rows.length, error: `source 응답 절단` };
    }
    srows.forEach(r => {
      const x = r.data || {};
      const v = String(cellVal(x, 'doe_value') ?? '');
      const seq = Number(cellVal(x, 'band_seq')) || 1;
      const lot = cellVal(x, 'source_lot');
      if (!v || !lot) return;
      const band = (byValue.get(v) || []).find(b => Number(b.seq) === seq);
      if (!band) return;   // 고아 행 — 재번호 금지 규율이 지켜지면 발생하지 않는다
      const slot = cellVal(x, 'source_slot');
      band.materials.push({ lot: String(lot), slot: slot == null ? '' : String(slot) });
    });

    // ★ [C1] 이 함수는 **조회만 한다.** S.doeServerLoaded를 여기서 세우면
    //    "서버에 요청이 성공했다"가 "화면이 서버본이다"로 잘못 승격된다(회복 재시도 경로).
    //    권한은 채택 지점(adoptServerDoe)에서 화면 반영과 **원자적으로** 얻는다.
    if (rows.length === 0) return { ok: true, rowCount: 0, srcCount: srows.length };

    const loaded = new Map();
    byValue.forEach((bands, v) => {
      bands.sort((a, b) => a.seq - b.seq);
      loaded.set(v, bands);
    });
    S.serverSavedAt = String(cellVal(rows[0].data || {}, 'eventtime') || '');
    return { ok: true, rowCount: rows.length, srcCount: srows.length, doe: loaded };
  } catch (e) {
    return { ok: false, rowCount: 0, error: e && e.message ? e.message : String(e) };
  }
}

// [C1] 서버본 **채택** — replace 권한(doeServerLoaded)이 생기는 유일한 지점이다.
// 불변식: `doeServerLoaded === true` ⇒ `S.doe`는 서버본에서 유래했다.
// 그래서 이 화면이 만든 집합으로 그 맵을 replace해도 보지 못한 행을 지우지 않는다.
function adoptServerDoe(r) {
  if (r && r.doe instanceof Map && r.doe.size > 0) S.doe = r.doe;
  S.serverRows = { doe: (r && r.rowCount) || 0, source: (r && r.srcCount) || 0 };
  S.doeServerLoaded = true;
  // Adopting the server copy puts the screen back on server state, so anything the
  // last save failed to delete is visible again — the warning has served its purpose.
  S.deleteUnsent = false;
}

// ── 골격 ────────────────────────────────────────────────
function renderAll() {
  renderPlanHead();
  renderDoeList();
  renderMaterialPane();
}

function buildWorkspace(root) {
  root.innerHTML = `
    <div class="tp-scroll" id="tp-scroll">
      <div class="tp-plan-head" id="tp-head"></div>
      <div class="tp-doe-list" id="tp-list"></div>
    </div>
    <div class="tp-mat-pane" id="tp-mat-pane" style="display:none;"></div>`;
  elp.head = root.querySelector('#tp-head');
  elp.list = root.querySelector('#tp-list');
  elp.matPane = root.querySelector('#tp-mat-pane');
}

// ── map_editor → 패널 통지 (export) ─────────────────────

// 맵 정체성이 바뀌었다 (테이블 전환 / 맵 로드 / 프레임 push·pop / push 성공).
export function notifyMapContext(info = {}) {
  if (!controller || !controller.getMapContext) return;
  const c = controller.getMapContext();
  const changed = (c.table !== S.ctx.table) || ((c.mapKey || '') !== (S.ctx.mapKey || '')) || (c.depth !== S.ctx.depth);
  S.ctx = {
    table: c.table || '',
    mapKey: (c.loaded && c.loaded.mapKey) || c.mapKey || '',
    loaded: c.loaded, depth: c.depth || 0, parent: c.parent || null,
  };
  if (changed) {
    const seq = ++S.loadSeq;
    S.doe = new Map();
    S.openValue = null;
    S.savedAt = null;
    S.serverSavedAt = null;
    S.saveError = null;
    S.flash.clear();
    // [B2] 맵이 바뀌면 "서버 상태를 안다"는 주장은 무효다 — 다시 확인하기 전엔 replace 금지
    S.doeServerLoaded = false;
    S.serverRows = { doe: 0, source: 0 };
    S.deleteUnsent = false;    // 이전 맵의 경고를 새 맵 헤더로 이월하지 않는다

    if (S.ctx.table && S.ctx.mapKey) {
      const hadDraft = loadDraft();
      renderAll();
      (async () => {
        // [B2 ⓒ] **로컬 초안이 있어도 서버 로드를 건너뛰지 않는다.**
        // 건너뛰면 다른 세션이 저장한 계획을 못 본 채 prune이 그것을 잔재로 오인한다.
        if (stageOfTable(S.ctx.table) && S.ctx.depth === 0) {
          const r = await loadDoeFromServer();
          if (seq !== S.loadSeq) return;
          if (!r.ok) {
            // [B2 ⓑ] 실패를 **상태로 보존** — 이후 저장이 이 사실을 보고 prune을 건너뛴다
            S.doeServerLoaded = false;
            showToast(
              `서버 DOE 조회 실패 — 편집은 브라우저 초안에만 보관되고, 서버 잔재 정리도 하지 않습니다 (${r.error || '알 수 없음'})`,
              'warning', { dedupeKey: 'doe_server_load_failed' });
          } else {
            // 서버에 행이 있으면 **공유 테이블이 정본**이다 (다른 세션 저장분 보호).
            // 로컬 초안이 달랐다면 사용자에게 알린다 — 조용히 버리지 않는다.
            // [C1] 채택과 prune 권한 획득은 adoptServerDoe 한 지점에서만 일어난다(seq 가드 통과 후).
            const draftHadContent = hadDraft && [...S.doe.values()].some(bands => bands.length > 0);
            const hadServerRows = r.doe instanceof Map && r.doe.size > 0;
            adoptServerDoe(r);
            if (hadServerRows) {
              showToast(draftHadContent
                ? '서버에 저장된 DOE 정의를 불러왔습니다 — 브라우저 초안 대신 서버본을 표시합니다.'
                : '서버에서 DOE 정의를 복원했습니다.', 'info');
            }
          }
          // 서버 0건 + 초안 있음 → 초안 유지(미저장 로컬 작업). 서버 0건을 **읽어서 확인**했으므로
          // 그 위에 replace를 거는 것은 안전하다(보지 못한 행이 없다).
          renderAll();
        }
        if (seq !== S.loadSeq) return;
        refreshMaterials();
      })();
      // ★ 왕복 보상 — 복귀 직후 그 자재만 재조회
      if (info.returnedFrom) rewardAfterReturn(info.returnedFrom);
      return;
    }
  }
  renderAll();
}

// legend(값·설명·색·브러시)가 바뀌었다.
export function notifyLegendChanged() {
  if (!controller || !controller.getLegend) return;
  S.legendRows = controller.getLegend();
  S.activeBrush = controller.getActiveBrush ? controller.getActiveBrush() : '';
  renderDoeList();
  renderMaterialPane();
}

// 페인팅 카운트 변경 — 전체 재렌더 금지, 숫자 텍스트만 패치한다.
export function notifyPaintCounts(counts) {
  S.counts = counts || {};
  if (!elp.list) return;
  const planMode = !!stageOfTable(S.ctx.table) && S.ctx.depth === 0;
  elp.list.querySelectorAll('[data-count-for]').forEach(node => {
    node.textContent = doeLine2(node.getAttribute('data-count-for'), planMode);
  });
}

export function initTransferPlan(paintController) {
  controller = paintController || null;
  const root = document.getElementById('transfer-plan-root');
  if (!root) { console.warn('[Legend & DOE] mount point missing (#transfer-plan-root)'); return; }
  buildWorkspace(root);
  renderAll();
  fetchStages();
}

// ============================================================
// §보류 구역 — 검증/경고 판정 (사용자 지시로 이번 범위에서 **미연결**)
//
//   아래 함수들은 M2에서 만든 판정 로직이다. 재설계 후 다시 붙일 예정이라
//   **삭제하지 않고** 보관한다. 현재 어떤 렌더러도 이들을 호출하지 않는다.
//   재연결 시 유의: DOE 모델이 `layers[]` → `{stack, need, materials[]}`로 바뀌었으므로
//   layerStats/doeStats는 새 모델에 맞춰 재작성해야 한다(형태만 참고).
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
