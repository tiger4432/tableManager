// ============================================================
// transfer_plan.js — Universal Transfer Plan M2
// 「2. 전사 계획 & 브러시」 사이드바에 상주하는 계획 워크스페이스 (슬라이드 패널 폐기)
//
//   모드 A (base 맵): 좌 = DOE value 리스트 = 브러시 팔레트 / 우 = 선택 value 상세 + 「코어 맵 열기」
//   모드 B (코어 맵): 좌 = 오버레이 토글 + 브러시     / 우 = 수량 실시간 + 「저장하고 base로」
//
// 모델: DOE = value ↦ { 설명, knob 계획, 층별 배정[] }
//       층별 배정 = { 층범위, 소스(lot|slot), 단위 수량, 사용 영역(코어 맵 페인팅) }
//       → 한 DOE 안에서 층마다 다른 소스·수량을 지정할 수 있다.
//
// 서버 계약 (총괄 고정):
//   GET /api/transfer-plan/stages         — stage 목록(정본 어휘). 구버전 404 → 빌트인 dt/bonding
//   GET /api/transfer-plan/source-summary — 소스 가용. 구버전 404 → M1 core-summary 폴백
//        chips.remaining 은 null 가능(신뢰 불가) + remaining_reliable=false + warnings[source_degraded]
//   GET /api/transfer-plan/validate       — 계획 경고
//   영속화: transfer_plan / transfer_plan_doe / transfer_plan_map (기존 배치 업데이트 경로)
//   [스텁] transfer_plan_doe_layer  — 층별 배정 (서버 신설 예정, 부재 시 초안 모드)
//   [스텁] transfer_plan_source_map — 코어 사용 영역 (map_editor.js가 담당)
//
// 불변 원칙: 서버가 "모른다/못 했다"고 말한 것을 클라가 "이상 없음"으로 바꾸지 않는다.
// ============================================================
import { API_BASE, CURRENT_USER } from './config.js';
import { showToast, getLocalTimeString } from './utils.js';
import './transfer_plan.css';

const DRAFT_PREFIX = 'transfer_plan_draft::';
const LAST_KEY = 'transfer_plan_last';
const M1_DRAFT_PREFIX = 'bonding_plan_draft::';
const M1_MIGRATION_FLAG = 'transfer_plan_m1_migrated';
const DRAFT_VERSION = 3;

const PLAN_TABLE = 'transfer_plan';
const DOE_TABLE = 'transfer_plan_doe';
const DOE_LAYER_TABLE = 'transfer_plan_doe_layer'; // [스텁] 서버 신설 예정
const PLAN_MAP_TABLE = 'transfer_plan_map';

const DOE_COLORS = ['#10b981', '#ef4444', '#3b82f6', '#ec4899', '#f59e0b', '#8b5cf6', '#14b8a6', '#f43f5e', '#06b6d4', '#84cc16', '#a855f7', '#6b7280'];

// 코어 맵 오버레이 후보 (범용 오버레이 기능의 계획용 단축 진입)
const CORE_OVERLAY_SOURCES = [
  { table: 'core_defect_map', label: 'defect' },
  { table: 'eds_fail_map', label: 'EDS fail' },
];

// ⚠️ stage 어휘는 서버 config 선언값이 정본('dt' | 'bonding'). 미선언 값 저장 금지.
const BUILTIN_STAGES = [
  { id: 'dt', name: 'DT 계획 (타깃: Tape 맵)', targetKind: 'tape', hasLayers: false, targetLabel: 'Tape', sourceLabel: 'Wafer', roles: null, builtin: true },
  { id: 'bonding', name: '본딩 계획 (타깃: Base 맵)', targetKind: 'base', hasLayers: true, targetLabel: 'Base', sourceLabel: 'Tape', roles: null, builtin: true },
];
const LEGACY_STAGE_ALIASES = { dt_plan: 'dt', bonding_plan: 'bonding' };

const S = {
  stages: BUILTIN_STAGES,
  stagesStatus: null,
  stage: BUILTIN_STAGES[0].id,
  target: '',
  totalLayers: 0,
  memo: '',
  status: 'draft',
  does: [],              // { id, value, color, description, knobs[], layers[] }
  nextDoeId: 1,
  nextLayerId: 1,
  selectedDoeId: null,
  selectedLayerId: null,
  mode: 'A',             // 'A' = base 맵 / 'B' = 코어 맵
  coreCtx: null,
  paintedCounts: null,
  paintedFrom: null,
  cells: [],
  summaries: new Map(),
  sourceApi: null,
  planTablesSupported: null,
  layerTableSupported: null,
  validateState: null,
  detailSeq: 0, loadSeq: 0, validateSeq: 0,
  savedAt: null,
  serverSavedAt: null,
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

function fmtNum(v) {
  return (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) ? '?' : String(Number(v));
}

// 서버가 신뢰 불가를 null로 표현한다 → "미상". 0과 반드시 구분한다.
function fmtChips(v) {
  if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '<span class="tp-unknown-val">미상</span>';
  return String(Number(v));
}

function curStage() {
  return S.stages.find(x => x.id === S.stage) || S.stages[0] || BUILTIN_STAGES[0];
}
function hasLayers() { return !!curStage().hasLayers; }

function layerSpan(L) {
  const a = Number(L.layer_from), b = Number(L.layer_to);
  if (!Number.isFinite(a) || !Number.isFinite(b) || a <= 0 || b < a) return hasLayers() ? 0 : 1;
  return b - a + 1;
}

function getDoe(id) { return S.does.find(d => d.id === id) || null; }
function getSelectedDoe() { return getDoe(S.selectedDoeId); }
function getLayer(doe, layerId) { return doe ? (doe.layers.find(L => L.id === layerId) || null) : null; }

function buildPlanId() {
  const t = S.target.trim().replace(/\|/g, '_');
  return `${S.stage}__${t}`;
}

function knobsToObject(arr) {
  const out = {};
  (arr || []).forEach(p => {
    const k = String(p.k || '').trim();
    if (k) out[k] = p.v !== undefined && p.v !== null ? String(p.v) : '';
  });
  return out;
}
function knobsToArray(obj) {
  if (!obj || typeof obj !== 'object') return [];
  return Object.entries(obj).map(([k, v]) => ({ k, v: v === null || v === undefined ? '' : String(v) }));
}

function nextDoeColor() {
  const used = new Set(S.does.map(d => d.color));
  for (const c of DOE_COLORS) if (!used.has(c)) return c;
  return DOE_COLORS[S.does.length % DOE_COLORS.length];
}
function nextDoeValue() {
  let n = 1;
  while (S.does.some(d => String(d.value) === `D${n}`)) n++;
  return `D${n}`;
}
function newLayer(from) {
  return { id: S.nextLayerId++, layer_from: from ?? '', layer_to: from ?? '', source: '', qty_per_unit: '', useCells: [], useCount: null };
}

// ── stage ───────────────────────────────────────────────
function normalizeStage(s) {
  if (!s || typeof s !== 'object') {
    if (typeof s === 'string' && s.trim()) s = { stage: s };
    else return null;
  }
  const id = String(s.stage ?? s.id ?? s.key ?? '').trim();
  if (!id) return null;
  const name = String(s.name ?? s.label ?? id);
  let kind = String(s.target_kind ?? s.target ?? s.kind ?? '').toLowerCase();
  if (kind !== 'tape' && kind !== 'base') kind = /^dt|tape/i.test(id) ? 'tape' : 'base';
  const layered = s.has_layers ?? s.layered ?? (kind === 'base');
  return {
    id, name, targetKind: kind, hasLayers: !!layered,
    targetLabel: s.target_label || (kind === 'tape' ? 'Tape' : 'Base'),
    sourceLabel: s.source_label || (kind === 'tape' ? 'Wafer' : 'Tape'),
    roles: s.roles ?? s.role_status ?? null,
  };
}

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
    console.warn('[Transfer Plan] stages fetch failed — builtin fallback:', e);
    S.stages = BUILTIN_STAGES; S.stagesStatus = 'error';
  }
  // 서버가 모르는 stage는 저장 전 강등 — 조용히 바꾸지 않고 반드시 고지한다.
  if (!S.stages.some(x => x.id === S.stage)) {
    const before = S.stage;
    const alias = LEGACY_STAGE_ALIASES[S.stage];
    S.stage = (alias && S.stages.some(x => x.id === alias)) ? alias : S.stages[0].id;
    if (before !== S.stage) {
      showToast(`계획의 stage '${before}'는 서버 미선언 — '${S.stage}'로 표시합니다. 저장하면 stage가 바뀝니다.`, 'warning');
    }
  }
  syncHeaderInputs();
  renderAll();
}

// ── 초안 ────────────────────────────────────────────────
function draftKey(stage, target) { return `${DRAFT_PREFIX}${stage}::${target}`; }

function serializeDraft() {
  return {
    version: DRAFT_VERSION,
    stage: S.stage, target: S.target.trim(), status: S.status,
    total_layers: Number(S.totalLayers) || 0, memo: S.memo || '',
    does: S.does.map(d => ({
      value: String(d.value || '').trim(),
      description: d.description || '',
      knobs: knobsToObject(d.knobs),
      color: d.color || '',
      layers: d.layers.map(L => ({
        layer_from: Number(L.layer_from) || null,
        layer_to: Number(L.layer_to) || null,
        source: String(L.source || '').trim(),
        qty_per_unit: Number(L.qty_per_unit) || 0,
        use_cells: Array.isArray(L.useCells) ? L.useCells : [],
        use_count: L.useCount,
      })),
    })),
    cells: Array.isArray(S.cells) ? S.cells : [],
    painted_counts: S.paintedCounts || null,
    saved_at: new Date().toISOString(),
  };
}

function deserializeDraft(obj) {
  if (!obj || typeof obj !== 'object') return;
  S.status = obj.status === 'confirmed' ? 'confirmed' : 'draft';
  S.totalLayers = Number(obj.total_layers) || 0;
  S.memo = typeof obj.memo === 'string' ? obj.memo : '';
  S.does = (Array.isArray(obj.does) ? obj.does : []).map((d, i) => {
    // v2 초안 하위호환: 층 정보가 DOE에 평탄하게 있던 형태 → 층 배정 1건으로 승격
    let layers;
    if (Array.isArray(d.layers) && d.layers.length > 0) {
      layers = d.layers.map(L => ({
        id: S.nextLayerId++,
        layer_from: L.layer_from ?? '', layer_to: L.layer_to ?? '',
        source: L.source || '', qty_per_unit: L.qty_per_unit ?? '',
        useCells: Array.isArray(L.use_cells) ? L.use_cells : [],
        useCount: L.use_count ?? null,
      }));
    } else {
      layers = [{
        id: S.nextLayerId++,
        layer_from: d.layer_from ?? '', layer_to: d.layer_to ?? '',
        source: d.source || '', qty_per_unit: d.qty_per_unit ?? '',
        useCells: [], useCount: null,
      }];
    }
    return {
      id: S.nextDoeId++,
      value: d.value != null ? String(d.value) : '',
      color: d.color || DOE_COLORS[i % DOE_COLORS.length],
      description: typeof d.description === 'string' ? d.description : '',
      knobs: knobsToArray(d.knobs),
      layers,
    };
  });
  S.cells = Array.isArray(obj.cells) ? obj.cells : [];
  S.paintedCounts = (obj.painted_counts && typeof obj.painted_counts === 'object') ? obj.painted_counts : null;
  S.paintedFrom = S.paintedCounts ? 'draft' : null;
  S.selectedDoeId = S.does.length > 0 ? S.does[0].id : null;
  S.selectedLayerId = (S.does[0] && S.does[0].layers[0]) ? S.does[0].layers[0].id : null;
  S.savedAt = obj.saved_at || null;
}

let saveTimer = null;
function scheduleSave() { clearTimeout(saveTimer); saveTimer = setTimeout(saveDraft, 500); }

function saveDraft() {
  const target = S.target.trim();
  if (!target) { renderHeaderBadges(); return; }
  try {
    const draft = serializeDraft();
    localStorage.setItem(draftKey(S.stage, target), JSON.stringify(draft));
    localStorage.setItem(LAST_KEY, JSON.stringify({ stage: S.stage, target }));
    S.savedAt = draft.saved_at;
    renderHeaderBadges();
  } catch (e) { console.warn('[Transfer Plan] draft save failed:', e); }
}

function loadDraft(stage, target) {
  try {
    const raw = localStorage.getItem(draftKey(stage, target));
    if (!raw) return false;
    deserializeDraft(JSON.parse(raw));
    return true;
  } catch (e) { console.warn('[Transfer Plan] draft load failed:', e); return false; }
}

function offerM1Migration() {
  try {
    if (localStorage.getItem(M1_MIGRATION_FLAG)) return;
    const oldKeys = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(M1_DRAFT_PREFIX)) oldKeys.push(k);
    }
    if (oldKeys.length === 0) return;
    localStorage.setItem(M1_MIGRATION_FLAG, '1');
    const ok = confirm(
      `M1 본딩 실험계획 초안 ${oldKeys.length}건이 이 브라우저에 남아 있습니다.\n` +
      `전사 계획(본딩 stage) 초안으로 변환하시겠습니까?\n\n` +
      `층 배정 행 → DOE(D1, D2, …)의 층별 배정으로 옮깁니다. 기존 M1 초안은 지우지 않습니다.`
    );
    if (!ok) return;
    let migrated = 0;
    oldKeys.forEach(k => {
      try {
        const old = JSON.parse(localStorage.getItem(k));
        if (!old || typeof old !== 'object') return;
        const target = String(old.base || k.slice(M1_DRAFT_PREFIX.length)).trim();
        if (!target) return;
        const newKey = draftKey('bonding', target);
        if (localStorage.getItem(newKey)) return;
        const does = (Array.isArray(old.assignments) ? old.assignments : []).map((a, i) => ({
          value: `D${i + 1}`, description: '', knobs: {}, color: DOE_COLORS[i % DOE_COLORS.length],
          layers: [{
            layer_from: a.layer_from ?? null, layer_to: a.layer_to ?? null,
            source: a.core_lot ? (a.core_slot ? `${a.core_lot}|${a.core_slot}` : a.core_lot) : '',
            qty_per_unit: a.qty_per_layer ?? 0, use_cells: [], use_count: null,
          }],
        }));
        localStorage.setItem(newKey, JSON.stringify({
          version: DRAFT_VERSION, stage: 'bonding', target, status: 'draft',
          total_layers: Number(old.total_layers) || 0,
          memo: typeof old.memo === 'string' ? old.memo : '',
          does, cells: [], painted_counts: null, saved_at: new Date().toISOString(),
        }));
        migrated++;
      } catch (e) { /* 개별 초안 파손 */ }
    });
    if (migrated > 0) showToast(`M1 초안 ${migrated}건을 전사 계획 초안으로 변환했습니다.`, 'success');
  } catch (e) { /* localStorage 미가용 */ }
}

// ── source-summary (M2 → M1 폴백) ───────────────────────
function summaryKey(lot, slot) { return `${S.stage}::${lot}::${slot}`; }
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
  const entry = { status: 'loading' };
  entry.promise = (async () => {
    if (S.sourceApi !== 'm1' && S.sourceApi !== false) {
      const params = new URLSearchParams({ stage: S.stage, lot: lot || '', slot: slot || '' });
      const res = await fetch(`${API_BASE}/api/transfer-plan/source-summary?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        S.sourceApi = 'm2'; entry.status = 'ok'; entry.api = 'm2';
        entry.data = (data && typeof data === 'object') ? data : {};
        return;
      }
      const body = await res.json().catch(() => null);
      if (!isPlainNotFound(res.status, body)) {
        entry.status = 'error';
        entry.error = (body && typeof body.detail === 'string') ? body.detail : `HTTP ${res.status}`;
        return;
      }
      S.sourceApi = 'm1';
    }
    const params = new URLSearchParams({ lot: lot || '', slot: slot || '' });
    const res = await fetch(`${API_BASE}/api/bonding-plan/core-summary?${params.toString()}`);
    if (res.ok) {
      const m1 = await res.json().catch(() => null) || {};
      const c = m1.chips || {};
      entry.status = 'ok'; entry.api = 'm1';
      entry.data = {
        identity: m1.identity, sources: m1.sources,
        chips: { total: c.total, fail_breakdown: { defect: c.defect, eds_fail: c.eds_fail }, transferred: c.used, remaining: c.remaining },
        history: m1.history, warnings: m1.warnings,
      };
      return;
    }
    const body = await res.json().catch(() => null);
    if (isPlainNotFound(res.status, body)) { S.sourceApi = false; entry.status = 'unsupported'; return; }
    entry.status = 'error';
    entry.error = (body && typeof body.detail === 'string') ? body.detail : `HTTP ${res.status}`;
  })().catch(e => { entry.status = 'error'; entry.error = e && e.message ? e.message : String(e); });
  S.summaries.set(key, entry);
  await entry.promise;
  return entry;
}

// ── sources 상태 등급 (거짓 초록 금지의 근원) ─────────────
function normalizeSources(src) {
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

function classifySourceStatus(rawStatus) {
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

function classifiedSources(src) {
  return normalizeSources(src).map(s => ({ role: s.role, ...classifySourceStatus(s.status) }));
}

function sourceBadgeHtml(s) {
  const cls = s.severity === 'degraded' ? 'degraded' : (s.severity === 'missing' ? 'missing' : (s.severity === 'unknown' ? 'unknown' : ''));
  let suffix = '';
  if (s.severity === 'missing') suffix = ' · 미연결';
  else if (s.severity === 'degraded' || s.severity === 'unknown') suffix = ` · ${esc(s.status)}`;
  else if (/^connected\(/i.test(s.status)) suffix = ` · ${esc(s.status.replace(/^connected\(/i, '').replace(/\)$/, ''))}`;
  return `<span class="bp-src ${cls}" title="${esc(`${s.role}: ${s.status}${s.note ? ' — ' + s.note : ''}`)}">${esc(s.role)}${suffix}</span>`;
}

function remainingReliability(data) {
  if (!data || typeof data !== 'object') return { reliable: true, reasons: [] };
  const reasons = [];
  classifiedSources(data.sources)
    .filter(s => s.severity === 'degraded' || s.severity === 'missing')
    .forEach(s => reasons.push(`${s.role}: ${s.status}`));
  const chips = data.chips || {};
  const flag = (data.remaining_reliable !== undefined) ? data.remaining_reliable
    : (chips.remaining_reliable !== undefined ? chips.remaining_reliable : undefined);
  if (flag === false) reasons.push('서버: remaining 신뢰 불가');
  // 서버가 값을 아예 주지 않은 경우(null)도 신뢰 불가로 취급한다
  if (chips.remaining === null || chips.remaining === undefined) reasons.push('서버: 잔여 값 미제공(미상)');
  if (data.truncated && typeof data.truncated === 'object' && Object.keys(data.truncated).length > 0) {
    reasons.push(`응답 절단: ${Object.keys(data.truncated).join(', ')}`);
  }
  if (data.by_core_truncated) reasons.push('by_core 절단');
  (Array.isArray(data.warnings) ? data.warnings : []).forEach(w => {
    const n = normalizeWarning(w);
    if (n.type === 'source_degraded' || n.type === 'availability_unreliable') {
      reasons.push(`${n.type}${n.detail ? ': ' + n.detail : ''}`);
    }
  });
  return { reliable: reasons.length === 0 && flag !== false, reasons };
}

function isFailResult(h) { return String((h && h.result) || '').toUpperCase().includes('FAIL'); }

function sumFailBreakdown(fb) {
  if (fb === null || fb === undefined) return null;
  if (typeof fb === 'number') return fb;
  if (typeof fb !== 'object') return null;
  let sum = 0, any = false;
  Object.values(fb).forEach(v => { const n = Number(v); if (Number.isFinite(n)) { sum += n; any = true; } });
  return any ? sum : null;
}

// ── 서버 warning ────────────────────────────────────────
const VERIFICATION_SKIP_TYPES = ['stage_unknown', 'source_unresolved'];
const WARN_SEVERITY = {
  stage_unknown: 'critical', source_unresolved: 'critical', client_parse_error: 'critical',
  source_degraded: 'high', availability_unreliable: 'high', source_overallocated: 'high',
  qty_shortage: 'high', source_fail_chips: 'high', truncated: 'high',
  layer_coverage_gap: 'normal', doe_value_unpainted: 'normal', undefined_doe_value: 'normal',
};

function normalizeWarning(w) {
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

function renderWarningHtml(w) {
  const sev = WARN_SEVERITY[w.type] || 'unknown';
  const icon = (sev === 'critical') ? '🚨' : (sev === 'high' ? '⚠️' : (sev === 'unknown' ? '❔' : '•'));
  const known = Object.prototype.hasOwnProperty.call(WARN_SEVERITY, w.type);
  return `<span class="tp-warn tp-warn-${sev}" title="${esc(known ? w.type : w.type + ' (클라이언트가 모르는 경고 유형 — 원문 표시)')}">`
    + `${icon} <b>${esc(w.type)}</b>${w.detail ? ' — ' + esc(w.detail) : ''}</span>`;
}

// ── 파생 상태 ───────────────────────────────────────────
function layerStats(L) {
  const { lot, slot } = parseSource(L.source);
  const units = hasLayers() ? layerSpan(L) : 1;
  const qty = Number(L.qty_per_unit) || 0;
  const need = qty * units;
  const entry = lot ? S.summaries.get(summaryKey(lot, slot)) : null;

  let remaining = null;
  let remainingKnown = false;
  if (entry && entry.status === 'ok' && entry.data.chips
      && entry.data.chips.remaining !== undefined && entry.data.chips.remaining !== null) {
    remaining = Number(entry.data.chips.remaining);
    remainingKnown = Number.isFinite(remaining);
  }
  const rel = (entry && entry.status === 'ok') ? remainingReliability(entry.data) : { reliable: true, reasons: [] };
  const hasFail = !!(entry && entry.status === 'ok' && (entry.data.history || []).some(isFailResult));
  const problemSources = (entry && entry.status === 'ok')
    ? classifiedSources(entry.data.sources).filter(s => s.severity !== 'ok') : [];
  const shortage = (remainingKnown && rel.reliable && need > 0 && remaining < need);
  // 잔여가 미상이거나 오염 가능하면 "충족"이라고 단정하지 않는다
  const shortageUnverifiable = (need > 0 && !shortage && (!rel.reliable || !remainingKnown)
    && !!entry && entry.status === 'ok');
  const useCount = (L.useCount === null || L.useCount === undefined) ? null : Number(L.useCount);
  const useMismatch = (useCount !== null && need > 0 && useCount !== need);

  return { lot, slot, units, qty, need, remaining, remainingKnown, hasFail, problemSources,
    remainingReliable: rel.reliable, unreliableReasons: rel.reasons, shortage, shortageUnverifiable,
    useCount, useMismatch, entry };
}

function doeStats(d) {
  const per = d.layers.map(layerStats);
  const need = per.reduce((a, s) => a + s.need, 0);
  const painted = (S.paintedCounts && typeof S.paintedCounts === 'object')
    ? (Number(S.paintedCounts[String(d.value)]) || 0) : null;
  // 페인팅 셀 수는 계획 '총량'과 대조 (층수 반영 — 층당 수량과 직접 비교하면 상시 오탐)
  const paintMismatch = (painted !== null && need > 0 && painted !== need);
  return {
    per, need, painted, paintMismatch,
    shortage: per.some(s => s.shortage),
    shortageUnverifiable: per.some(s => s.shortageUnverifiable),
    hasFail: per.some(s => s.hasFail),
    anyUnreliable: per.some(s => s.entry && s.entry.status === 'ok' && !s.remainingReliable),
    loaded: per.some(s => s.entry && s.entry.status === 'ok'),
    problemSources: per.flatMap(s => s.problemSources),
  };
}

// ── 렌더: 헤더 ──────────────────────────────────────────
function renderHeaderBadges() {
  if (elp.draftBadge) {
    if (S.savedAt) {
      const t = new Date(S.savedAt);
      elp.draftBadge.textContent = `초안 · ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
    } else elp.draftBadge.textContent = '초안';
  }
  if (elp.statusBadge) {
    const confirmed = S.status === 'confirmed';
    elp.statusBadge.textContent = confirmed ? '확정됨' : 'draft';
    elp.statusBadge.className = 'bp-badge' + (confirmed ? ' bp-badge-confirmed' : '');
  }
  if (elp.serverLine) {
    if (S.planTablesSupported === false) {
      elp.serverLine.textContent = '🔌 서버 관리 테이블 미지원 — 초안 모드로 보관 중';
    } else if (S.serverSavedAt) {
      elp.serverLine.textContent = `💾 서버 저장됨 · ${S.serverSavedAt} · ${S.status === 'confirmed' ? '확정' : 'draft'}`;
    } else {
      elp.serverLine.textContent = '서버 저장 전 — [저장]으로 관리 테이블에 승격됩니다.';
    }
  }
}

function renderStageSelect() {
  if (!elp.stageSelect) return;
  elp.stageSelect.innerHTML = S.stages.map(st =>
    `<option value="${esc(st.id)}" ${st.id === S.stage ? 'selected' : ''}>${esc(st.name)}</option>`).join('');
}

function syncHeaderInputs() {
  if (elp.targetInput) {
    elp.targetInput.value = S.target;
    elp.targetInput.placeholder = `${curStage().targetLabel} 노드 검색`;
  }
  if (elp.totalLayers) elp.totalLayers.value = S.totalLayers || '';
  if (elp.layersField) elp.layersField.style.display = hasLayers() ? '' : 'none';
  if (elp.memo) elp.memo.value = S.memo;
}

// ── 렌더: 모드 바 ───────────────────────────────────────
function renderModeBar() {
  const box = elp.modeBar;
  if (!box) return;
  const st = curStage();
  if (S.mode === 'B' && S.coreCtx) {
    box.className = 'tp-mode-bar mode-b';
    box.innerHTML = `<span class="tp-mode-tag">모드 B · 코어 맵</span>
      <span class="tp-mode-info"><b>${esc(S.coreCtx.value)}</b> 소스 <b>${esc(S.coreCtx.lot)}${S.coreCtx.slot ? '|' + esc(S.coreCtx.slot) : ''}</b>의 사용 영역을 칠하는 중</span>`;
  } else {
    box.className = 'tp-mode-bar mode-a';
    const painting = controller && controller.isPlanMode && controller.isPlanMode();
    box.innerHTML = `<span class="tp-mode-tag">모드 A · ${esc(st.targetKind === 'tape' ? 'TAPE' : 'BASE')} 맵</span>
      <span class="tp-mode-info">${painting ? 'DOE value를 타깃 맵에 칠하는 중 — 좌측 목록이 브러시입니다.' : 'DOE를 정의하고 [🖌 맵 페인팅]으로 칠합니다.'}</span>`;
  }
}

// ── 렌더: 검증 ──────────────────────────────────────────
function renderValidation() {
  const box = elp.validation;
  if (!box) return;
  const T = Number(S.totalLayers) || 0;

  let stripHtml = '', covText = '';
  if (hasLayers()) {
    if (T > 0 && T <= 500) {
      const counts = new Array(T + 1).fill(0);
      S.does.forEach(d => d.layers.forEach(L => {
        const a = Number(L.layer_from), b = Number(L.layer_to);
        if (!Number.isFinite(a) || !Number.isFinite(b)) return;
        for (let i = Math.max(1, a); i <= Math.min(T, b); i++) counts[i]++;
      }));
      const gaps = [], overlaps = [];
      let segs = '';
      for (let i = 1; i <= T; i++) {
        const cls = counts[i] === 0 ? 'gap' : (counts[i] > 1 ? 'overlap' : 'cov');
        if (counts[i] === 0) gaps.push(i);
        if (counts[i] > 1) overlaps.push(i);
        segs += `<div class="bp-cov-seg ${cls}" title="층 ${i}: ${counts[i]}건"></div>`;
      }
      stripHtml = `<div class="bp-coverage-strip">${segs}</div>`;
      const list = a => a.slice(0, 12).join(', ') + (a.length > 12 ? ' …' : '');
      covText = `<div class="bp-coverage-text">커버리지 1–${T}층 · `
        + (gaps.length ? `공백 ${gaps.length}층 (${list(gaps)})` : '공백 없음') + ' · '
        + (overlaps.length ? `겹침 ${overlaps.length}층 (${list(overlaps)})` : '겹침 없음') + '</div>';
    } else covText = '<div class="bp-coverage-text">총 층수를 입력하면 층 커버리지를 검증합니다.</div>';
  }

  const vs = S.validateState;
  const vWarns = (vs && typeof vs === 'object' && Array.isArray(vs.warnings)) ? vs.warnings.map(normalizeWarning) : [];
  const skipWarns = vWarns.filter(w => VERIFICATION_SKIP_TYPES.includes(w.type));
  // 서버가 명시한 unverified / availability_checked:false 도 "검사 못 함"이다
  const serverUnverified = !!(vs && typeof vs === 'object'
    && (vs.unverified || vs.availabilityChecked === false));
  const verificationSkipped = skipWarns.length > 0 || serverUnverified;
  const validateBroken = !!(vs && typeof vs === 'object' && vs.broken);
  const trusted = !verificationSkipped && !validateBroken;

  const stats = S.does.map(doeStats);
  const loaded = stats.filter(s => s.loaded).length;
  const shortage = stats.filter(s => s.shortage).length;
  const fails = stats.filter(s => s.hasFail).length;
  const paintMis = stats.filter(s => s.paintMismatch).length;
  const unreliable = stats.filter(s => s.anyUnreliable).length;

  let qtyBadge;
  if (loaded === 0) qtyBadge = '<span class="bp-vbadge">수량 부족 미조회</span>';
  else if (shortage > 0) qtyBadge = `<span class="bp-vbadge bad">수량 부족 ${shortage}</span>`;
  else if (!trusted) qtyBadge = '<span class="bp-vbadge warn" title="서버 검증이 수행되지 않았습니다">수량 부족 <b>검증 스킵</b></span>';
  else if (unreliable > 0) qtyBadge = `<span class="bp-vbadge warn" title="잔여가 미상/과대일 수 있는 DOE ${unreliable}건">수량 부족 <b>확인 불가</b> (${unreliable})</span>`;
  else qtyBadge = '<span class="bp-vbadge ok">수량 부족 0</span>';

  const failBadge = loaded === 0 ? '<span class="bp-vbadge">FAIL 이력 미조회</span>'
    : `<span class="bp-vbadge ${fails > 0 ? 'bad' : (trusted ? 'ok' : 'warn')}">FAIL 이력 ${fails}${trusted ? '' : ' ⚠'}</span>`;
  const paintBadge = S.paintedCounts
    ? `<span class="bp-vbadge ${paintMis > 0 ? 'warn' : 'ok'}">페인팅 불일치 ${paintMis}</span>`
    : '<span class="bp-vbadge">페인팅 미집계</span>';

  const skipReasons = skipWarns.map(w => `${w.type}${w.detail ? ' — ' + w.detail : ''}`);
  if (serverUnverified) {
    if (vs.unverified) skipReasons.push('서버 status: unverified (검사하지 못함)');
    if (vs.availabilityChecked === false) skipReasons.push('availability_checked: false — 수량·fail 검증 미수행');
  }
  const skipBanner = verificationSkipped
    ? `<div class="tp-skip-banner">🚨 <b>서버 검증이 수행되지 않았습니다</b>
        <div class="tp-skip-why">${skipReasons.map(r => `<span>${esc(r)}</span>`).join('')}</div>
        <div class="tp-skip-note">아래는 <b>검증 통과가 아니라 미검증</b>입니다.</div></div>` : '';

  let validateHtml = '';
  if (vs === 'loading') validateHtml = '<div class="bp-hint-line">서버 검증 조회 중…</div>';
  else if (vs === 'unsupported') validateHtml = '<div class="tp-validate-note warn">validate API 미지원 (구버전) — <b>서버 검증 미수행</b>.</div>';
  else if (vs === 'unsaved') validateHtml = '<div class="tp-validate-note">아직 서버에 저장되지 않은 계획입니다 — [저장] 후 검증됩니다.</div>';
  else if (vs && typeof vs === 'object') {
    if (vs.broken) validateHtml = `<div class="tp-validate-note bad">⚠️ <b>서버 검증 결과를 읽지 못했습니다</b> — 미검증으로 간주하십시오.
      <div class="tp-skip-why"><span>${esc(vs.brokenReason || '응답 파싱 실패')}</span></div></div>`;
    else if (vWarns.length) validateHtml = `<div class="bp-server-warns">${vWarns.map(renderWarningHtml).join('')}</div>`;
    // 경고가 0건이어도 unverified면 절대 초록으로 표시하지 않는다
    else if (verificationSkipped) validateHtml = '<div class="tp-validate-note warn">경고는 없으나 <b>검증이 수행되지 않았습니다</b> (unverified).</div>';
    else validateHtml = '<div class="tp-validate-note ok">서버 검증 경고 없음 ✓</div>';
  }

  box.innerHTML = skipBanner
    + `<div class="bp-vbadges">${qtyBadge}${failBadge}${paintBadge}</div>`
    + stripHtml + covText + validateHtml
    + (S.target.trim() ? '<div><button type="button" class="glass-btn bp-mini-btn" id="tp-validate-btn">서버 검증 실행</button></div>' : '');
  const vb = box.querySelector('#tp-validate-btn');
  if (vb) vb.addEventListener('click', () => refreshValidate(true));
}

async function refreshValidate(force = false) {
  if (!S.target.trim()) { S.validateState = null; return; }
  if (!force && S.validateState === 'unsupported') { renderValidation(); return; }
  const seq = ++S.validateSeq;
  S.validateState = 'loading';
  renderValidation();
  try {
    const params = new URLSearchParams({ plan_id: buildPlanId() });
    const res = await fetch(`${API_BASE}/api/transfer-plan/validate?${params.toString()}`);
    if (seq !== S.validateSeq) return;
    if (res.ok) {
      // 파싱 실패를 삼키지 않는다 — 삼키면 "경고 0건 = 초록"으로 뒤집힌다.
      let data;
      try { data = await res.json(); }
      catch (pe) {
        S.validateState = { broken: true, brokenReason: `응답 파싱 실패: ${pe && pe.message ? pe.message : pe}`, warnings: [] };
        renderValidation(); return;
      }
      const warns = Array.isArray(data) ? data : ((data && (data.warnings || data.items)) || []);
      if (!Array.isArray(warns)) {
        S.validateState = { broken: true, brokenReason: '응답에 warnings 배열이 없습니다', warnings: [] };
      } else {
        // status: ok | warnings | unverified. unverified는 "이상 없음"이 아니라 "검사 못 함".
        const st = (data && typeof data === 'object') ? String(data.status || '') : '';
        S.validateState = {
          warnings: warns,
          serverStatus: st,
          unverified: st === 'unverified',
          availabilityChecked: (data && data.availability_checked !== undefined)
            ? !!data.availability_checked : null,
        };
      }
    } else {
      const body = await res.json().catch(() => null);
      const detail = (body && typeof body.detail === 'string') ? body.detail : '';
      if (isPlainNotFound(res.status, body)) S.validateState = 'unsupported';
      else if (res.status === 404) S.validateState = 'unsaved';   // 미저장 계획의 정상 404
      else S.validateState = { broken: true, brokenReason: `validate 조회 실패 (HTTP ${res.status})${detail ? ' — ' + detail : ''}`, warnings: [] };
    }
  } catch (e) {
    if (seq !== S.validateSeq) return;
    S.validateState = { broken: true, brokenReason: `validate 조회 실패: ${e && e.message ? e.message : e}`, warnings: [] };
  }
  renderValidation();
}

// ── 렌더: 좌열 ──────────────────────────────────────────
function renderLeft() {
  const box = elp.left;
  if (!box) return;
  if (S.mode === 'B') { renderLeftCoreMode(box); return; }

  const header = `<div class="tp-col-head"><span>DOE (value) · 브러시</span>
    <button type="button" class="glass-btn bp-mini-btn" id="tp-add-doe">+ DOE</button></div>`;
  if (S.does.length === 0) {
    box.innerHTML = header + `<div class="bp-empty-hint">DOE가 없습니다. [+ DOE]로 조건군을 만드세요.<br>
      각 DOE 안에서 <b>층마다 다른 소스·수량</b>을 지정할 수 있습니다.</div>`;
    bindAddDoe(box);
    return;
  }
  const rows = S.does.map(d => {
    const s = doeStats(d);
    const sel = S.selectedDoeId === d.id;
    const warn = s.shortage || s.hasFail || s.paintMismatch || s.anyUnreliable || s.problemSources.length > 0;
    const uniqSrc = [...new Set(d.layers.map(L => L.source).filter(Boolean))];
    const layerTxt = hasLayers()
      ? d.layers.map(L => (L.layer_from && L.layer_to) ? `${L.layer_from}–${L.layer_to}` : '?').join(', ')
      : '단일';
    const chips = [];
    if (s.shortage) chips.push('<span class="tp-mini-chip bad">수량 부족</span>');
    if (s.anyUnreliable) chips.push('<span class="tp-mini-chip warn">잔여 미상</span>');
    if (s.hasFail) chips.push('<span class="tp-mini-chip bad">FAIL</span>');
    if (s.paintMismatch) chips.push(`<span class="tp-mini-chip warn">🖌 ${s.painted}≠${s.need}</span>`);
    return `<div class="tp-doe-row ${sel ? 'selected' : ''} ${warn ? 'warn' : ''}" data-id="${d.id}">
      <span class="tp-doe-swatch" style="background:${esc(d.color)}" title="${esc(d.description || d.value)}">${esc(d.value)}</span>
      <span class="tp-doe-body">
        <span class="tp-doe-line1">${esc(uniqSrc.length ? uniqSrc.join(' · ') : '소스 미지정')}</span>
        <span class="tp-doe-line2">층 ${esc(layerTxt)} · 총 ${s.need || 0}칩${s.painted !== null ? ` · 칠함 ${s.painted}` : ''}</span>
        ${chips.length ? `<span class="tp-doe-chips">${chips.join('')}</span>` : ''}
      </span>
    </div>`;
  }).join('');
  box.innerHTML = header + `<div class="tp-doe-list">${rows}</div>`
    + '<div class="bp-coverage-text">행 클릭 = 선택 + 브러시 전환</div>';

  bindAddDoe(box);
  box.querySelectorAll('.tp-doe-row').forEach(row => {
    row.addEventListener('click', () => {
      const id = Number(row.dataset.id);
      selectDoe(id);
      const d = getDoe(id);
      if (d && controller && controller.isPlanMode && controller.isPlanMode() && controller.setBrush) {
        controller.setBrush(String(d.value));
      }
    });
  });
}

function bindAddDoe(box) {
  const b = box.querySelector('#tp-add-doe');
  if (!b) return;
  b.addEventListener('click', () => {
    const last = S.does[S.does.length - 1];
    const lastLayer = last && last.layers[last.layers.length - 1];
    const from = (hasLayers() && lastLayer && Number(lastLayer.layer_to) > 0) ? Number(lastLayer.layer_to) + 1 : (hasLayers() ? 1 : '');
    const d = {
      id: S.nextDoeId++, value: nextDoeValue(), color: nextDoeColor(),
      description: '', knobs: [], layers: [newLayer(from)],
    };
    S.does.push(d);
    S.selectedDoeId = d.id;
    S.selectedLayerId = d.layers[0].id;
    scheduleSave();
    renderLeft(); renderRight(); renderValidation();
  });
}

function renderLeftCoreMode(box) {
  const ctx = S.coreCtx || {};
  const overlays = (controller && controller.listOverlays) ? controller.listOverlays() : [];
  const ovRows = CORE_OVERLAY_SOURCES.map(src => {
    const on = overlays.find(o => o.sourceTable === src.table);
    return `<div class="tp-ov-row">
      <button type="button" class="glass-btn bp-mini-btn ${on ? 'on' : ''}" data-tbl="${esc(src.table)}" data-id="${on ? on.id : ''}">
        ${on ? '✓' : '＋'} ${esc(src.label)}</button>
      ${on ? `<span class="tp-ov-meta"><i style="background:${esc(on.color)}"></i>${on.count}칩${on.alignApplied ? ' · 정렬됨' : ''}${on.truncated ? ' · 일부만' : ''}</span>` : ''}
    </div>`;
  }).join('');

  box.innerHTML = `<div class="tp-col-head"><span>오버레이 &amp; 브러시</span></div>
    <div class="bp-hint-line">불량 맵을 겹쳐 보며 사용 영역을 고릅니다. 좌표는 <b>서버가 정렬</b>합니다.</div>
    <div class="tp-ov-list">${ovRows}</div>
    <div class="tp-brush-note">
      <span class="tp-doe-swatch" style="background:${esc(ctx.color || '#10b981')}">USE</span>
      <span>드래그 = 사용 영역 칠하기 · 우클릭 드래그 = 지우기</span>
    </div>`;

  box.querySelectorAll('.tp-ov-row button').forEach(btn => {
    btn.addEventListener('click', async () => {
      const tbl = btn.dataset.tbl;
      const id = btn.dataset.id;
      if (id) { if (controller.removeOverlay) controller.removeOverlay(Number(id)); renderLeft(); return; }
      btn.disabled = true;
      const r = await controller.addOverlayForCore(tbl, ctx.lot, ctx.slot);
      btn.disabled = false;
      if (r && r.error) showToast(r.error, r.unsupported ? 'warning' : 'error');
      renderLeft();
    });
  });
}

// ── 렌더: 우열 ──────────────────────────────────────────
function renderRight() {
  const box = elp.right;
  if (!box) return;
  if (S.mode === 'B') { renderRightCoreMode(box); return; }

  const d = getSelectedDoe();
  if (!d) {
    box.innerHTML = '<div class="bp-empty-hint">DOE를 선택하면 상세(층별 배정·knob·설명)를 편집합니다.</div>';
    return;
  }
  const st = curStage();
  const s = doeStats(d);
  const layered = hasLayers();

  const layerRows = d.layers.map(L => {
    const ls = layerStats(L);
    const sel = S.selectedLayerId === L.id;
    const rangeInputs = layered
      ? `<input class="tp-l-from glass-input" type="number" min="1" placeholder="from" value="${esc(L.layer_from ?? '')}" title="시작 층" />
         <span class="bp-dash">–</span>
         <input class="tp-l-to glass-input" type="number" min="1" placeholder="to" value="${esc(L.layer_to ?? '')}" title="끝 층" />`
      : '<span class="tp-l-single">단일</span>';
    const warnChips = [];
    if (ls.shortage) warnChips.push(`<span class="tp-mini-chip bad">잔여 ${fmtNum(ls.remaining)} &lt; 소요 ${ls.need}</span>`);
    if (ls.shortageUnverifiable) warnChips.push('<span class="tp-mini-chip warn">충족 확인 불가</span>');
    if (ls.useMismatch) warnChips.push(`<span class="tp-mini-chip warn">사용영역 ${ls.useCount} ≠ 소요 ${ls.need}</span>`);
    ls.problemSources.forEach(p => warnChips.push(
      `<span class="tp-mini-chip ${p.severity === 'degraded' ? 'bad' : 'warn'}" title="${esc(p.role + ': ' + p.status)}">${esc(p.role)} · ${esc(p.status)}</span>`));
    return `<div class="tp-layer-row ${sel ? 'selected' : ''}" data-lid="${L.id}">
      <div class="tp-layer-l1">
        ${rangeInputs}
        <span class="bp-ac-wrap tp-l-srcwrap"><input class="tp-l-src glass-input" placeholder="${esc(st.sourceLabel)} lot|slot" value="${esc(L.source ?? '')}" autocomplete="off" /></span>
        <input class="tp-l-qty glass-input" type="number" min="0" placeholder="${layered ? '층당' : '수량'}" value="${esc(L.qty_per_unit ?? '')}" title="단위 수량" />
        <button type="button" class="bp-tool tp-l-del" title="이 층 배정 삭제">🗑</button>
      </div>
      <div class="tp-layer-l2">
        <span class="tp-layer-stat">소요 ${ls.need || 0} · 잔여 ${ls.remainingKnown ? ls.remaining : '<span class="tp-unknown-val">미상</span>'}${ls.useCount !== null ? ` · 사용영역 ${ls.useCount}칩` : ''}</span>
        <button type="button" class="glass-btn bp-mini-btn tp-open-core" ${ls.lot ? '' : 'disabled'} title="이 소스의 코어 맵을 열어 사용 영역을 칠합니다">🎨 코어 맵 열기</button>
      </div>
      ${warnChips.length ? `<div class="tp-layer-warn">${warnChips.join('')}</div>` : ''}
    </div>`;
  }).join('');

  const knobRows = (d.knobs || []).map((p, ki) => `
    <div class="tp-knob-row" data-ki="${ki}">
      <input class="tp-knob-k glass-input" placeholder="knob" value="${esc(p.k ?? '')}" />
      <input class="tp-knob-v glass-input" placeholder="값" value="${esc(p.v ?? '')}" />
      <button type="button" class="bp-tool tp-knob-del" title="삭제">✕</button>
    </div>`).join('');

  box.innerHTML = `
    <div class="tp-col-head">
      <span class="tp-doe-swatch" style="background:${esc(d.color)}">${esc(d.value)}</span>
      <input class="tp-d-val glass-input" value="${esc(d.value)}" title="DOE value (페인팅 값)" />
      <input type="color" class="tp-d-color" value="${esc(d.color)}" title="맵 팔레트 색" />
      <button type="button" class="bp-tool bp-tool-del tp-d-del" title="DOE 삭제">🗑</button>
    </div>
    <div class="tp-sec">
      <div class="tp-sec-head"><span>층별 배정${layered ? ' (층마다 다른 소스·수량 가능)' : ''}</span>
        <button type="button" class="glass-btn bp-mini-btn tp-add-layer">+ 배정</button></div>
      <div class="tp-layer-list">${layerRows}</div>
      <div class="bp-coverage-text">DOE 총 소요 <b>${s.need || 0}</b>칩${s.painted !== null ? ` · 타깃 맵에 칠한 셀 <b>${s.painted}</b>` : ''}</div>
    </div>
    <div class="tp-sec">
      <div class="tp-sec-head"><span>knob 계획</span><button type="button" class="glass-btn bp-mini-btn tp-knob-add">+ knob</button></div>
      <div class="tp-knob-rows">${knobRows || '<div class="bp-hint-line">계획 knob 없음</div>'}</div>
    </div>
    <div class="tp-sec">
      <label class="tp-lbl">설명 (레전드·split registry 서술로 연동)</label>
      <textarea class="tp-d-desc glass-input" rows="2" placeholder="이 DOE의 실험 조건">${esc(d.description ?? '')}</textarea>
    </div>
    <div id="tp-src-detail"></div>`;

  bindRightEvents(box, d);
  renderSourceDetail();
}

function bindRightEvents(box, d) {
  const fire = () => { scheduleSave(); renderLeft(); renderRight(); renderValidation(); };

  const valIn = box.querySelector('.tp-d-val');
  valIn.addEventListener('change', () => {
    const nv = valIn.value.trim(), ov = String(d.value || '');
    if (nv === ov) return;
    if (!nv) { valIn.value = ov; return; }
    if (S.does.some(x => x.id !== d.id && String(x.value) === nv)) {
      showToast('중복된 DOE value입니다.', 'warning'); valIn.value = ov; return;
    }
    d.value = nv;
    if (Array.isArray(S.cells)) S.cells.forEach(c => { if (String(c.val) === ov) c.val = nv; });
    if (S.paintedCounts && Object.prototype.hasOwnProperty.call(S.paintedCounts, ov)) {
      S.paintedCounts[nv] = S.paintedCounts[ov]; delete S.paintedCounts[ov];
    }
    fire();
  });
  box.querySelector('.tp-d-color').addEventListener('input', e => { d.color = e.target.value; scheduleSave(); renderLeft(); });
  box.querySelector('.tp-d-del').addEventListener('click', () => {
    if (!confirm(`DOE '${d.value}'를 삭제할까요? (저장 시 서버에서도 제거됩니다)`)) return;
    const idx = S.does.findIndex(x => x.id === d.id);
    S.does.splice(idx, 1);
    S.selectedDoeId = S.does.length ? S.does[Math.min(idx, S.does.length - 1)].id : null;
    fire();
  });
  box.querySelector('.tp-d-desc').addEventListener('change', e => { d.description = e.target.value.trim(); scheduleSave(); });
  box.querySelector('.tp-add-layer').addEventListener('click', () => {
    const last = d.layers[d.layers.length - 1];
    const from = (hasLayers() && last && Number(last.layer_to) > 0) ? Number(last.layer_to) + 1 : (hasLayers() ? 1 : '');
    const L = newLayer(from);
    d.layers.push(L); S.selectedLayerId = L.id;
    fire();
  });
  box.querySelector('.tp-knob-add').addEventListener('click', () => { d.knobs.push({ k: '', v: '' }); fire(); });
  box.querySelectorAll('.tp-knob-row').forEach(kr => {
    const ki = Number(kr.dataset.ki);
    kr.querySelector('.tp-knob-k').addEventListener('change', e => { if (d.knobs[ki]) { d.knobs[ki].k = e.target.value; scheduleSave(); } });
    kr.querySelector('.tp-knob-v').addEventListener('change', e => { if (d.knobs[ki]) { d.knobs[ki].v = e.target.value; scheduleSave(); } });
    kr.querySelector('.tp-knob-del').addEventListener('click', () => { d.knobs.splice(ki, 1); fire(); });
  });

  box.querySelectorAll('.tp-layer-row').forEach(row => {
    const lid = Number(row.dataset.lid);
    const L = getLayer(d, lid);
    if (!L) return;
    row.addEventListener('click', e => {
      if (e.target.closest('input, button')) return;
      S.selectedLayerId = lid; renderRight();
    });
    const from = row.querySelector('.tp-l-from');
    const to = row.querySelector('.tp-l-to');
    const src = row.querySelector('.tp-l-src');
    const qty = row.querySelector('.tp-l-qty');
    if (from) from.addEventListener('change', () => { L.layer_from = from.value; fire(); });
    if (to) to.addEventListener('change', () => { L.layer_to = to.value; fire(); });
    qty.addEventListener('change', () => { L.qty_per_unit = qty.value; fire(); });
    src.addEventListener('change', () => {
      if (L.source !== src.value.trim()) {
        L.source = src.value.trim(); S.selectedLayerId = lid;
        scheduleSave(); refreshDetail(); renderLeft();
      }
    });
    attachAutocomplete(src, curStage().sourceLabel, v => {
      L.source = v; S.selectedLayerId = lid;
      scheduleSave(); refreshDetail(); renderLeft();
    });
    row.querySelector('.tp-l-del').addEventListener('click', () => {
      if (d.layers.length <= 1) { showToast('최소 1개의 배정이 필요합니다.', 'warning'); return; }
      d.layers.splice(d.layers.findIndex(x => x.id === lid), 1);
      fire();
    });
    const openBtn = row.querySelector('.tp-open-core');
    if (openBtn) openBtn.addEventListener('click', () => openCoreMap(d, L));
  });
}

// 선택 층의 소스 상세
function renderSourceDetail() {
  const box = document.getElementById('tp-src-detail');
  if (!box) return;
  const d = getSelectedDoe();
  const L = getLayer(d, S.selectedLayerId) || (d && d.layers[0]);
  if (!d || !L) { box.innerHTML = ''; return; }
  const { lot, slot } = parseSource(L.source);
  if (!lot) { box.innerHTML = '<div class="bp-hint-line">배정에 소스를 입력하면 가용을 조회합니다.</div>'; return; }
  const entry = S.summaries.get(summaryKey(lot, slot));
  if (!entry || entry.status === 'loading') { box.innerHTML = '<div class="bp-hint-line">소스 가용 조회 중…</div>'; return; }
  if (entry.status === 'unsupported' || entry.status === 'error') {
    const msg = entry.status === 'unsupported'
      ? '🔌 서버가 소스 가용 API를 제공하지 않습니다 (구버전).'
      : `조회 실패: ${esc(entry.error || '')}`;
    box.innerHTML = `<div class="bp-empty-hint">${msg}
      <div style="margin-top:6px;"><button type="button" class="glass-btn bp-mini-btn" id="tp-retry">다시 시도</button></div></div>`;
    box.querySelector('#tp-retry').addEventListener('click', () => refreshDetail(true));
    return;
  }

  const data = entry.data || {};
  const chips = data.chips || {};
  const ls = layerStats(L);
  const sources = classifiedSources(data.sources);
  const apiBadge = entry.api === 'm1' ? '<span class="bp-src unknown" title="M1 core-summary 폴백">M1 폴백</span>' : '';
  const relHtml = ls.remainingReliable ? '' :
    `<div class="tp-unreliable">⚠️ <b>잔여 수치를 신뢰할 수 없습니다</b> — fail 집계 누락/미제공으로 과대일 수 있습니다.
      <div class="tp-unreliable-why">${ls.unreliableReasons.map(r => `<span>${esc(r)}</span>`).join('')}</div></div>`;
  const fb = (chips.fail_breakdown && typeof chips.fail_breakdown === 'object') ? chips.fail_breakdown : null;
  const fbChips = fb ? `<div class="bp-src-badges">${Object.entries(fb).map(([k, v]) =>
    `<span class="bp-src ${Number(v) > 0 ? 'missing' : ''}">${esc(k)} ${fmtChips(v)}</span>`).join('')}</div>` : '';
  const warns = (Array.isArray(data.warnings) ? data.warnings : []).map(normalizeWarning);

  box.innerHTML = `<div class="bp-detail-card">
    <div class="bp-src-badges">${apiBadge}${sources.map(sourceBadgeHtml).join('')}</div>
    ${relHtml}
    <div class="bp-chips-line">잔여 <span class="rem">${fmtChips(chips.remaining)}</span>${
      (chips.remaining === null || chips.remaining === undefined) && chips.remaining_upper_bound !== undefined && chips.remaining_upper_bound !== null
        ? ` <span class="tp-unknown-val">(상한 ${esc(String(chips.remaining_upper_bound))} — 실제는 이보다 작음)</span>` : ''}
      = 총 ${fmtChips(chips.total)} − fail류 ${fmtChips(sumFailBreakdown(chips.fail_breakdown))} − 기전사 ${fmtChips(chips.transferred)}</div>
    ${fbChips}
    ${warns.length ? `<div class="bp-server-warns">${warns.map(renderWarningHtml).join('')}</div>` : ''}
    ${renderByCoreTable(data.by_core, data.by_core_origin)}
  </div>`;
}

// ── by_core (7키 단일 렌더러) ───────────────────────────
function coreDisplayName(row) {
  const lot = row.core_lot, slot = row.core_slot;
  if (lot !== null && lot !== undefined && String(lot) !== '') {
    return (slot !== null && slot !== undefined && String(slot) !== '') ? `${lot}|${slot}` : String(lot);
  }
  return (row.core_id !== null && row.core_id !== undefined) ? String(row.core_id) : '—';
}

function renderByCoreTable(byCore, origin) {
  if (!Array.isArray(byCore) || byCore.length === 0) return '';
  const isArea = String(origin || '') === 'area_map';
  const badge = isArea
    ? '<span class="bp-src missing" title="칩 단위 DT 로그 없음 — DT 맵 영역 귀속으로 분해">영역 귀속 기준</span>'
    : (String(origin || '') === 'log' ? '<span class="bp-src">DT 로그 기준</span>' : '');
  const td = v => (v === null || v === undefined || v === '')
    ? '<td class="tp-unknown">미상</td>' : `<td>${esc(String(v))}</td>`;
  const body = byCore.map(r0 => {
    const r = (r0 && typeof r0 === 'object') ? r0 : {};
    return `<tr><td>${esc(coreDisplayName(r))}</td>${td(r.total)}${td(r.fail)}${td(r.used)}${td(r.remaining)}</tr>`;
  }).join('');
  return `<div class="bp-muted" style="margin-top:4px;">코어 분해 (by_core)</div>
    ${badge ? `<div class="bp-src-badges">${badge}</div>` : ''}
    <div class="tp-bycore-wrap"><table class="bp-compare-table">
      <thead><tr><th class="bp-key-col">코어</th><th>총</th><th>fail</th><th>기전사</th><th>잔여</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
}

// ── 모드 B 우열: 수량 실시간 ────────────────────────────
function renderRightCoreMode(box) {
  const ctx = S.coreCtx;
  if (!ctx) { box.innerHTML = ''; return; }
  const d = getDoe(ctx.doeId);
  const L = getLayer(d, ctx.layerId);
  const entry = S.summaries.get(summaryKey(ctx.lot, ctx.slot));
  const live = (ctx.liveCount === undefined || ctx.liveCount === null) ? null : ctx.liveCount;

  let availHtml = '<div class="bp-hint-line">소스 가용 조회 중…</div>';
  if (entry && entry.status === 'ok') {
    const c = entry.data.chips || {};
    const rel = remainingReliability(entry.data);
    const fb = (c.fail_breakdown && typeof c.fail_breakdown === 'object') ? c.fail_breakdown : {};
    availHtml = `
      <div class="bp-chips-line">총 ${fmtChips(c.total)} − defect ${fmtChips(fb.defect)} − EDS ${fmtChips(fb.eds_fail)} − 기사용 ${fmtChips(c.transferred)}
        <br>= 가용 <span class="rem">${fmtChips(c.remaining)}</span></div>
      ${rel.reliable ? '' : `<div class="tp-unreliable">⚠️ <b>가용 수치 신뢰 불가</b>
        <div class="tp-unreliable-why">${rel.reasons.map(r => `<span>${esc(r)}</span>`).join('')}</div></div>`}
      <div class="bp-src-badges">${classifiedSources(entry.data.sources).map(sourceBadgeHtml).join('')}</div>`;
  } else if (entry && entry.status === 'unsupported') {
    availHtml = '<div class="bp-hint-line">서버가 소스 가용 API를 제공하지 않습니다 (구버전).</div>';
  } else if (entry && entry.status === 'error') {
    availHtml = `<div class="bp-hint-line">가용 조회 실패: ${esc(entry.error || '')}</div>`;
  }

  const need = L ? layerStats(L).need : 0;
  box.innerHTML = `
    <div class="tp-col-head"><span>수량 실시간</span></div>
    <div class="bp-detail-card">${availHtml}</div>
    <div class="bp-detail-card">
      <div class="bp-chips-line">칠한 영역 <span class="rem">${live === null ? '—' : live}</span>칩${need > 0 ? ` · 이 배정의 소요 ${need}` : ''}</div>
      ${(live !== null && need > 0 && live !== need)
        ? `<div class="bp-need-line bad">⚠️ 칠한 영역 ${live} ≠ 소요 ${need}</div>`
        : (live !== null && need > 0 ? '<div class="bp-hint-line">소요와 일치</div>' : '')}
      <div class="bp-hint-line">※ "칠한 영역 <b>내 가용</b>"(불량 제외 실사용 가능 수)은 서버 계약 확정 후 연동됩니다.</div>
    </div>
    <div class="tp-save-row">
      <button type="button" class="glass-btn bp-mini-btn tp-confirm-btn" id="tp-core-save">💾 저장하고 base로</button>
      <button type="button" class="glass-btn bp-mini-btn" id="tp-core-cancel">← 취소하고 base로</button>
    </div>`;

  box.querySelector('#tp-core-save').addEventListener('click', () => closeCoreMap(true));
  box.querySelector('#tp-core-cancel').addEventListener('click', () => closeCoreMap(false));
}

// ── 모드 전환 ───────────────────────────────────────────
async function openCoreMap(d, L) {
  if (!controller || !controller.enterCorePaint) { showToast('맵 에디터 컨트롤러 미연결', 'error'); return; }
  const { lot, slot } = parseSource(L.source);
  if (!lot) { showToast('이 배정의 소스를 먼저 입력하세요.', 'warning'); return; }
  if (!S.target.trim()) { showToast('타깃 식별자를 먼저 입력하세요.', 'warning'); return; }
  saveDraft();
  S.coreCtx = { doeId: d.id, layerId: L.id, lot, slot, value: String(d.value), color: d.color, liveCount: L.useCount ?? null };
  S.mode = 'B';
  renderAll();
  getSourceSummary(lot, slot).then(() => { if (S.mode === 'B') renderRight(); });
  const ok = await controller.enterCorePaint({
    planId: buildPlanId(), doeValue: String(d.value), lot, slot, color: d.color,
    draftCells: Array.isArray(L.useCells) ? L.useCells : [],
    onSave: (res) => {
      S.mode = 'A'; S.coreCtx = null;
      if (res) {
        L.useCells = res.cells || [];
        L.useCount = res.count ?? (res.cells ? res.cells.length : null);
        if (res.saved) showToast(`사용 영역 저장 완료 — ${L.useCount}칩`, 'success');
        else showToast(`사용 영역을 서버에 저장하지 못했습니다: ${res.reason || '알 수 없음'} (초안 보관)`, 'warning');
      }
      scheduleSave(); renderAll();
    },
    onCancel: () => { S.mode = 'A'; S.coreCtx = null; renderAll(); showToast('코어 맵 편집을 취소했습니다.', 'info'); },
    onCountChange: (n) => { if (S.coreCtx) { S.coreCtx.liveCount = n; renderRight(); } },
  });
  if (!ok) { S.mode = 'A'; S.coreCtx = null; renderAll(); showToast('코어 맵 진입 실패', 'error'); }
}

function closeCoreMap(save) {
  if (controller && controller.finishCorePaint) controller.finishCorePaint(save);
}

// ── 타깃 맵 페인팅 (모드 A) ─────────────────────────────
async function enterPaintMode() {
  if (!controller || !controller.enterPlanPaint) { showToast('맵 에디터 컨트롤러 미연결', 'error'); return; }
  if (controller.isActive && controller.isActive()) { showToast('이미 페인팅 모드입니다.', 'warning'); return; }
  const target = S.target.trim();
  if (!target) { showToast('타깃 식별자를 먼저 입력하세요.', 'warning'); return; }
  const legendRows = S.does.filter(d => String(d.value || '').trim() !== '').map(d => ({
    value: String(d.value).trim(),
    desc: d.description || Object.entries(knobsToObject(d.knobs)).map(([k, v]) => `${k}=${v}`).join(', '),
    color: d.color || '#6b7280',
  }));
  if (legendRows.length === 0) { showToast('DOE를 먼저 정의하세요.', 'warning'); return; }
  saveDraft();
  const st = curStage();
  const sel = getSelectedDoe();
  const ok = await controller.enterPlanPaint({
    planId: buildPlanId(), planLabel: `${st.name} · ${target}`, targetKind: st.targetKind,
    legendRows, activeValue: sel ? String(sel.value) : legendRows[0].value,
    draftCells: S.cells,
    onFinish: (result) => {
      S.paintedCounts = (result && result.counts) || {};
      S.cells = (result && result.cells) || [];
      S.paintedFrom = 'paint';
      scheduleSave(); renderAll(); refreshValidate();
      const total = Object.values(S.paintedCounts).reduce((a, b) => a + (Number(b) || 0), 0);
      showToast(`페인팅 완료 — 총 ${total}셀${result && result.pushed ? ' (서버 push됨)' : ''}`, 'success');
    },
    onCancel: (info) => {
      renderAll();
      if (info && info.pushed) {
        // 이미 서버에 적재된 뒤의 취소 — "미반영"이라 말하면 거짓이다.
        showToast('⚠️ 취소했지만 이미 [⚡ Push]로 서버에 저장된 뒤였습니다 — 자동 되돌림은 없습니다.', 'warning');
        refreshPaintedCountsFromServer(); refreshValidate();
      } else showToast('페인팅을 취소했습니다 (맵 변경 미반영).', 'info');
    },
  });
  if (!ok) showToast('페인팅 모드 진입 실패', 'error');
  renderModeBar();
}

async function refreshPaintedCountsFromServer() {
  if (!S.target.trim() || S.planTablesSupported === false) return;
  try {
    const filters = { plan_id: { filterType: 'text', type: 'equals', filter: buildPlanId() } };
    const res = await fetch(`${API_BASE}/tables/${PLAN_MAP_TABLE}/data?limit=2000&filters=${encodeURIComponent(JSON.stringify(filters))}`);
    if (!res.ok) return;
    const result = await res.json();
    const counts = {}; const cells = [];
    (result && Array.isArray(result.data) ? result.data : []).forEach(row => {
      const d = row.data || {};
      const v = d.val?.value, x = d.x?.value, y = d.y?.value;
      if (v === undefined || v === null || String(v).trim() === '') return;
      const sv = String(v).trim();
      counts[sv] = (counts[sv] || 0) + 1;
      if (x !== undefined && y !== undefined) cells.push({ x: Number(x), y: Number(y), val: sv });
    });
    S.paintedCounts = counts; S.paintedFrom = 'server';
    if (cells.length > 0) S.cells = cells;
    scheduleSave(); renderAll();
  } catch (e) { /* 표시값은 이전 상태 유지 */ }
}

// ── 상세 조회 ───────────────────────────────────────────
async function refreshDetail(force = false) {
  const d = getSelectedDoe();
  const L = getLayer(d, S.selectedLayerId) || (d && d.layers[0]);
  renderSourceDetail();
  if (!L) return;
  const { lot, slot } = parseSource(L.source);
  if (!lot) return;
  const seq = ++S.detailSeq;
  await getSourceSummary(lot, slot, force);
  if (seq !== S.detailSeq) return;
  renderRight(); renderLeft(); renderValidation();
}

function selectDoe(id) {
  if (S.selectedDoeId !== id) {
    S.selectedDoeId = id;
    const d = getDoe(id);
    S.selectedLayerId = d && d.layers[0] ? d.layers[0].id : null;
    renderLeft(); renderRight();
  }
  refreshDetail();
}

// ── 자동완성 ────────────────────────────────────────────
function attachAutocomplete(input, label, onPick) {
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
          item.addEventListener('mousedown', e => { e.preventDefault(); input.value = item.dataset.v; hide(); onPick(item.dataset.v); });
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

// ── 서버 영속화 ─────────────────────────────────────────
function looksLikeMissingTable(status, body) {
  if (status === 404 || status === 405) return true;
  const detail = body && typeof body.detail === 'string' ? body.detail : '';
  return /not\s*found|없|unknown table|존재하지/i.test(detail);
}

async function putUpdates(table, updates) {
  const res = await fetch(`${API_BASE}/tables/${table}/data/updates`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates }),
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

// 삭제·개명된 DOE 잔재 제거 (유령 DOE가 validate를 영구 오염시키는 것 방지)
async function pruneServerDoes(planId, keepValues) {
  const result = { pruned: 0, prunedValues: [], failed: null };
  try {
    const filters = { plan_id: { filterType: 'text', type: 'equals', filter: planId } };
    const res = await fetch(`${API_BASE}/tables/${DOE_TABLE}/data?limit=500&filters=${encodeURIComponent(JSON.stringify(filters))}`);
    if (!res.ok) { result.failed = `기존 DOE 조회 실패 (HTTP ${res.status})`; return result; }
    const data = await res.json();
    const rows = (data && Array.isArray(data.data)) ? data.data : [];
    if (typeof data.total === 'number' && data.total > rows.length) {
      result.failed = `기존 DOE ${data.total}건 중 ${rows.length}건만 조회됨 — 정리 생략`; return result;
    }
    const keep = new Set(keepValues.map(String));
    const stale = rows.filter(r => {
      const v = cellVal(r.data || {}, 'doe_value');
      return v !== undefined && v !== null && !keep.has(String(v));
    });
    if (stale.length === 0) return result;
    const ids = stale.map(r => r.row_id).filter(Boolean);
    if (ids.length !== stale.length) { result.failed = 'row_id 누락 — 정리 생략'; return result; }
    const del = await fetch(`${API_BASE}/tables/${DOE_TABLE}/rows/batch_delete`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ row_ids: ids, user_name: CURRENT_USER }),
    });
    if (!del.ok) { result.failed = `DOE 정리 삭제 실패 (HTTP ${del.status})`; return result; }
    result.pruned = ids.length;
    result.prunedValues = stale.map(r => String(cellVal(r.data || {}, 'doe_value')));
  } catch (e) { result.failed = `DOE 정리 실패: ${e && e.message ? e.message : e}`; }
  return result;
}

// [B2] 층 배정 잔재 제거 — DOE prune(C4)의 형제 문제.
// 클라가 현재 층만 PUT하고 삭제하지 않으면 서버는 doe_key 접두로 남은 행까지 수요로
// 펼친다(층 1–3 → 1로 축소해도 @L1@L2@L3 수요 유지 → 거짓 source_overallocated,
// 층 커버리지가 잔재를 "배정됨"으로 세어 gap 경고가 침묵).
async function pruneServerDoeLayers(planId, keepLayerKeys) {
  const result = { pruned: 0, failed: null };
  const prefix = `${planId}|`;
  try {
    const filters = { doe_key: { filterType: 'text', type: 'startsWith', filter: prefix } };
    let res = await fetch(`${API_BASE}/tables/${DOE_LAYER_TABLE}/data?limit=2000&filters=${encodeURIComponent(JSON.stringify(filters))}`);
    let data = res.ok ? await res.json() : null;
    // startsWith 미지원 서버 대비: 전체 조회 후 클라에서 접두 필터
    if (!data || !Array.isArray(data.data)) {
      res = await fetch(`${API_BASE}/tables/${DOE_LAYER_TABLE}/data?limit=2000`);
      if (!res.ok) { result.failed = `층 배정 조회 실패 (HTTP ${res.status})`; return result; }
      data = await res.json();
    }
    const all = Array.isArray(data.data) ? data.data : [];
    // 응답이 절단됐으면 diff가 불완전 → 과삭제 방지를 위해 중단
    if (typeof data.total === 'number' && data.total > all.length) {
      result.failed = `층 배정 ${data.total}건 중 ${all.length}건만 조회됨 — 정리 생략`;
      return result;
    }
    const keep = new Set(keepLayerKeys.map(String));
    const stale = all.filter(r => {
      const d = r.data || {};
      const dk = String(cellVal(d, 'doe_key') ?? '');
      if (!dk.startsWith(prefix)) return false;          // 다른 계획 보호
      const lk = String(cellVal(d, 'layer_key') ?? '');
      return lk !== '' && !keep.has(lk);
    });
    if (stale.length === 0) return result;
    const ids = stale.map(r => r.row_id).filter(Boolean);
    if (ids.length !== stale.length) { result.failed = 'row_id 누락 — 정리 생략'; return result; }
    const del = await fetch(`${API_BASE}/tables/${DOE_LAYER_TABLE}/rows/batch_delete`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ row_ids: ids, user_name: CURRENT_USER }),
    });
    if (!del.ok) { result.failed = `층 배정 정리 삭제 실패 (HTTP ${del.status})`; return result; }
    result.pruned = ids.length;
  } catch (e) { result.failed = `층 배정 정리 실패: ${e && e.message ? e.message : e}`; }
  return result;
}

async function savePlanToServer(status) {
  const target = S.target.trim();
  if (!target) { showToast('타깃 식별자를 먼저 입력하세요.', 'warning'); return; }
  if (S.does.some(d => String(d.value || '').trim() === '')) {
    showToast('value가 비어있는 DOE가 있습니다.', 'warning'); return;
  }
  const planId = buildPlanId();
  const nowStr = getLocalTimeString();
  const nextStatus = status || S.status || 'draft';
  const tgt = parseSource(target);

  const headerUpdates = [{
    business_key_val: planId,
    updates: {
      plan_id: planId, stage: S.stage, target_lot: tgt.lot, target_slot: tgt.slot,
      status: nextStatus, memo: S.memo || '', updated_by: CURRENT_USER, eventtime: nowStr,
    },
    source_name: 'user', updated_by: CURRENT_USER,
  }];

  const activeDoes = S.does.filter(d => String(d.value || '').trim() !== '');
  // DOE 헤더행: 대표값(첫 배정) + 전체 층 범위. 층별 상세는 layer 테이블이 정본.
  const doeUpdates = activeDoes.map(d => {
    const value = String(d.value).trim();
    const bk = `${planId}|${value}`;
    const first = d.layers[0] || {};
    const src = parseSource(first.source);
    const froms = d.layers.map(L => Number(L.layer_from) || 0).filter(n => n > 0);
    const tos = d.layers.map(L => Number(L.layer_to) || 0).filter(n => n > 0);
    return {
      business_key_val: bk,
      updates: {
        doe_key: bk, plan_id: planId, doe_value: value,
        source_lot: src.lot, source_slot: src.slot,
        qty_per_unit: Number(first.qty_per_unit) || 0,
        layer_from: froms.length ? Math.min(...froms) : 0,
        layer_to: tos.length ? Math.max(...tos) : 0,
        knobs: JSON.stringify(knobsToObject(d.knobs)),
        description: d.description || '',
        updated_by: CURRENT_USER, eventtime: nowStr,
      },
      source_name: 'user', updated_by: CURRENT_USER,
    };
  });

  // 층별 배정 — transfer_plan_doe_layer (bk `doe_key|layer`, composite [doe_key, layer])
  // ⚠️ 스키마의 `layer`는 **단일 정수**다. UI의 층 범위는 층마다 1행으로 펼쳐 저장한다.
  const layerUpdates = [];
  activeDoes.forEach(d => {
    const value = String(d.value).trim();
    const doeKey = `${planId}|${value}`;
    d.layers.forEach(L => {
      const src = parseSource(L.source);
      const qty = Number(L.qty_per_unit) || 0;
      const a = Number(L.layer_from) || 0;
      const b = Number(L.layer_to) || 0;
      const layers = (hasLayers() && a > 0 && b >= a) ? Array.from({ length: b - a + 1 }, (_, i) => a + i) : [0];
      layers.forEach(n => {
        const bk = `${doeKey}|${n}`;
        layerUpdates.push({
          business_key_val: bk,
          updates: {
            layer_key: bk, doe_key: doeKey, layer: n,
            source_lot: src.lot, source_slot: src.slot,
            qty, note: '',
            updated_by: CURRENT_USER, eventtime: nowStr,
          },
          source_name: 'user', updated_by: CURRENT_USER,
        });
      });
    });
  });

  try {
    if (doeUpdates.length > 0) await putUpdates(DOE_TABLE, doeUpdates);
    // 층 테이블은 미신설일 수 있다 — 실패해도 계획 저장 자체는 진행(층 상세는 초안 유지)
    let layerPrune = { pruned: 0, failed: null };
    if (S.layerTableSupported !== false) {
      try {
        if (layerUpdates.length > 0) await putUpdates(DOE_LAYER_TABLE, layerUpdates);
        S.layerTableSupported = true;
        // [B2] 업서트 성공 후 잔재(축소된 범위·삭제된 DOE의 층) 제거.
        // layerUpdates가 0건이어도 과거 잔재는 지워야 하므로 무조건 수행한다.
        layerPrune = await pruneServerDoeLayers(planId, layerUpdates.map(u => u.updates.layer_key));
      } catch (le) {
        if (le && le.missingTable) {
          S.layerTableSupported = false;
          showToast(`층별 배정 테이블(${DOE_LAYER_TABLE})이 아직 없습니다 — 층 상세는 브라우저 초안에만 보관됩니다.`, 'warning');
        } else throw le;
      }
    }
    const prune = await pruneServerDoes(planId, doeUpdates.map(u => u.updates.doe_value));
    // 헤더(status)는 마지막에 커밋 — 먼저 확정하면 DOE 실패 시 서버/화면이 갈라진다
    await putUpdates(PLAN_TABLE, headerUpdates);

    S.planTablesSupported = true;
    S.status = nextStatus;
    S.serverSavedAt = nowStr;
    saveDraft(); renderHeaderBadges();
    const cleaned = [prune.pruned ? `DOE ${prune.pruned}` : '', layerPrune.pruned ? `층 ${layerPrune.pruned}` : '']
      .filter(Boolean).join('·');
    showToast(`계획 저장 완료 (${nextStatus === 'confirmed' ? '확정' : 'draft'} · DOE ${doeUpdates.length}건`
      + (cleaned ? ` · 잔재 정리 ${cleaned})` : ')'), 'success');
    if (prune.failed) showToast(`⚠️ 삭제·개명 DOE 정리 실패 — 유령 DOE가 검증을 오염시킬 수 있습니다. (${prune.failed})`, 'warning');
    if (layerPrune.failed) showToast(`⚠️ 층 배정 잔재 정리 실패 — 삭제된 층이 수요로 남아 수량 검증이 부풀 수 있습니다. (${layerPrune.failed})`, 'warning');
    if (prune.prunedValues.length > 0 && S.paintedCounts) {
      const orphan = prune.prunedValues.filter(v => Number(S.paintedCounts[v]) > 0);
      if (orphan.length) showToast(`⚠️ 계획 맵에 삭제된 DOE 값의 셀이 남아 있습니다: ${orphan.join(', ')}`, 'warning');
    }
    refreshValidate();
  } catch (e) {
    if (e && e.missingTable) {
      S.planTablesSupported = false; renderHeaderBadges();
      showToast('서버가 transfer_plan 테이블을 제공하지 않습니다 (구버전) — 초안 모드 유지.', 'warning');
    } else {
      showToast(`서버 저장 실패: ${e && e.message ? e.message : e} — [↻ 로드]로 서버 상태를 확인하십시오.`, 'error');
    }
  }
}

async function loadPlanFromServer(planId) {
  try {
    const filters = { plan_id: { filterType: 'text', type: 'equals', filter: planId } };
    const res = await fetch(`${API_BASE}/tables/${PLAN_TABLE}/data?limit=1&filters=${encodeURIComponent(JSON.stringify(filters))}`);
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      if (looksLikeMissingTable(res.status, body)) { S.planTablesSupported = false; return 'unsupported'; }
      return 'error';
    }
    const result = await res.json();
    S.planTablesSupported = true;
    if (!result || !Array.isArray(result.data) || result.data.length === 0) return 'none';
    const h = result.data[0].data || {};
    S.status = String(cellVal(h, 'status') || 'draft') === 'confirmed' ? 'confirmed' : 'draft';
    const memo = cellVal(h, 'memo');
    S.memo = memo !== undefined && memo !== null ? String(memo) : '';
    S.serverSavedAt = String(cellVal(h, 'eventtime') || cellVal(h, 'updated_at') || '');
    // total_layers 컬럼은 서버 스키마에 없으므로 로컬 값을 유지한다

    const dres = await fetch(`${API_BASE}/tables/${DOE_TABLE}/data?limit=500&filters=${encodeURIComponent(JSON.stringify(filters))}`);
    let doeRows = [];
    if (dres.ok) {
      const dd = await dres.json();
      doeRows = (dd && Array.isArray(dd.data) ? dd.data : []).map(r => r.data || {});
    }

    // 층별 배정 — 층 행이 하나라도 있으면 그 DOE의 수량 계산은 층 배정이 정본이다.
    // 스키마는 층당 1행이므로, 연속된 동일 (소스, 수량) 구간을 범위로 접어 UI에 올린다.
    const layersByValue = new Map();
    try {
      // 이 테이블은 doe_key(= plan_id|value)로 걸린다 — plan_id 컬럼이 없다
      const lres = await fetch(`${API_BASE}/tables/${DOE_LAYER_TABLE}/data?limit=2000`);
      if (lres.ok) {
        S.layerTableSupported = true;
        const ld = await lres.json();
        const raw = new Map(); // value -> [{layer, source, qty}]
        (ld && Array.isArray(ld.data) ? ld.data : []).forEach(r => {
          const x = r.data || {};
          const dk = String(cellVal(x, 'doe_key') ?? '');
          if (!dk.startsWith(planId + '|')) return; // 다른 계획의 행 제외
          const v = dk.slice(planId.length + 1);
          if (!v) return;
          const lot = cellVal(x, 'source_lot'), slot = cellVal(x, 'source_slot');
          const lotS = lot == null ? '' : String(lot), slotS = slot == null ? '' : String(slot);
          if (!raw.has(v)) raw.set(v, []);
          raw.get(v).push({
            layer: Number(cellVal(x, 'layer')) || 0,
            source: lotS ? (slotS ? `${lotS}|${slotS}` : lotS) : '',
            qty: Number(cellVal(x, 'qty')) || 0,
          });
        });
        raw.forEach((items, v) => {
          items.sort((a, b) => a.layer - b.layer);
          const folded = [];
          items.forEach(it => {
            const prev = folded[folded.length - 1];
            if (prev && prev.source === it.source && prev.qty === it.qty && it.layer === prev.to + 1) {
              prev.to = it.layer; // 연속 + 동일 조건 → 범위 확장
            } else {
              folded.push({ from: it.layer, to: it.layer, source: it.source, qty: it.qty });
            }
          });
          layersByValue.set(v, folded.map(f => ({
            id: S.nextLayerId++,
            layer_from: f.from || '', layer_to: f.to || '',
            source: f.source, qty_per_unit: f.qty || '',
            useCells: [], useCount: null,
          })));
        });
      } else S.layerTableSupported = false;
    } catch (e) { S.layerTableSupported = false; }

    const colorByValue = new Map();
    try {
      const regFilters = {
        ref_table: { filterType: 'text', type: 'equals', filter: PLAN_MAP_TABLE },
        map_key: { filterType: 'text', type: 'equals', filter: planId },
      };
      const rres = await fetch(`${API_BASE}/tables/map_split_registry/data?limit=500&filters=${encodeURIComponent(JSON.stringify(regFilters))}`);
      if (rres.ok) {
        const rr = await rres.json();
        (rr && Array.isArray(rr.data) ? rr.data : []).forEach(row => {
          const x = row.data || {};
          const v = cellVal(x, 'value'), color = cellVal(x, 'color');
          if (v != null && color) colorByValue.set(String(v), String(color));
        });
      }
    } catch (e) { /* 팔레트 폴백 */ }

    S.does = doeRows.map((x, i) => {
      const value = String(cellVal(x, 'doe_value') ?? '');
      let knobs = {};
      try { const raw = cellVal(x, 'knobs'); if (raw) knobs = JSON.parse(String(raw)); } catch (e) { /* 파손 */ }
      let layers = layersByValue.get(value);
      if (!layers || layers.length === 0) {
        const lot = cellVal(x, 'source_lot'), slot = cellVal(x, 'source_slot');
        const lotS = lot == null ? '' : String(lot), slotS = slot == null ? '' : String(slot);
        layers = [{
          id: S.nextLayerId++,
          layer_from: Number(cellVal(x, 'layer_from')) || '',
          layer_to: Number(cellVal(x, 'layer_to')) || '',
          source: lotS ? (slotS ? `${lotS}|${slotS}` : lotS) : '',
          qty_per_unit: Number(cellVal(x, 'qty_per_unit')) || '',
          useCells: [], useCount: null,
        }];
      }
      layers.sort((a, b) => (Number(a.layer_from) || 0) - (Number(b.layer_from) || 0));
      return {
        id: S.nextDoeId++, value,
        color: colorByValue.get(value) || DOE_COLORS[i % DOE_COLORS.length],
        description: String(cellVal(x, 'description') ?? ''),
        knobs: knobsToArray(knobs), layers,
      };
    }).filter(d => d.value !== '');
    S.selectedDoeId = S.does.length ? S.does[0].id : null;
    S.selectedLayerId = (S.does[0] && S.does[0].layers[0]) ? S.does[0].layers[0].id : null;
    return 'loaded';
  } catch (e) {
    console.warn('[Transfer Plan] server load failed:', e);
    return 'error';
  }
}

// ── 계획 전환 ───────────────────────────────────────────
function resetPlanState() {
  S.does = []; S.selectedDoeId = null; S.selectedLayerId = null;
  S.cells = []; S.paintedCounts = null; S.paintedFrom = null;
  S.status = 'draft'; S.totalLayers = 0; S.memo = '';
  S.savedAt = null; S.serverSavedAt = null;
  S.validateState = null;
}

async function activatePlan(opts = {}) {
  const target = S.target.trim();
  if (!target) return;
  const seq = ++S.loadSeq;
  const planId = buildPlanId();
  let from = null;
  if (S.planTablesSupported !== false) {
    const r = await loadPlanFromServer(planId);
    if (seq !== S.loadSeq) return;
    if (r === 'loaded') from = 'server';
    // 조회 실패를 "계획 없음"과 동일 취급하면 저장된 계획이 사라진 것처럼 보인다
    else if (r === 'error') showToast('서버 계획 조회에 실패했습니다 — 초안으로 대체합니다(서버에 계획이 있을 수 있음).', 'warning');
  }
  if (!from && loadDraft(S.stage, target)) from = 'draft';
  if (from) {
    S.validateState = null;
    syncHeaderInputs(); renderAll(); refreshDetail(); refreshValidate();
    if (from === 'server') { refreshPaintedCountsFromServer(); showToast(`'${target}' 계획을 서버에서 로드했습니다.`, 'info'); }
    else showToast(`'${target}' 초안을 복원했습니다.`, 'info');
  } else if (opts.keepEdits) {
    scheduleSave(); renderAll();
  } else {
    resetPlanState(); syncHeaderInputs(); renderAll(); scheduleSave();
  }
}

function onTargetChanged(v) {
  const target = String(v || '').trim();
  const prev = S.target.trim();
  if (target === prev) return;
  if (prev) saveDraft();
  S.target = target;
  S.serverSavedAt = null;
  if (!target) { renderHeaderBadges(); return; }
  try { localStorage.setItem(LAST_KEY, JSON.stringify({ stage: S.stage, target })); } catch (e) { /* noop */ }
  activatePlan({ keepEdits: true });
}

function onStageChanged(v) {
  if (v === S.stage) return;
  if (S.target.trim()) saveDraft();
  S.stage = v;
  S.summaries = new Map(); // stage별 가용이 다름
  S.serverSavedAt = null;
  syncHeaderInputs();
  if (S.target.trim()) activatePlan({ keepEdits: false });
  else renderAll();
}

// ── 골격 ────────────────────────────────────────────────
function renderAll() {
  renderStageSelect(); renderHeaderBadges(); renderModeBar();
  renderValidation(); renderLeft(); renderRight();
}

function buildWorkspace(root) {
  root.innerHTML = `
  <div class="tp-ws">
    <div class="tp-head">
      <div class="tp-head-row">
        <select id="tp-stage-select" class="glass-input tp-stage"></select>
        <span class="bp-badge bp-badge-draft" id="tp-draft-badge">초안</span>
        <span class="bp-badge" id="tp-status-badge">draft</span>
      </div>
      <div class="tp-head-row">
        <span class="bp-ac-wrap tp-target-wrap"><input id="tp-target-input" class="glass-input" type="text" placeholder="타깃 노드 검색" autocomplete="off" /></span>
        <span class="tp-field-inline" id="tp-layers-field">
          <label for="tp-total-layers" title="서버 스키마에 total_layers 컬럼이 없어 브라우저 초안에만 보관됩니다.">층수(로컬)</label>
          <input id="tp-total-layers" class="glass-input" type="number" min="1" max="500" placeholder="8" />
        </span>
      </div>
      <div class="tp-head-row">
        <button type="button" class="glass-btn bp-mini-btn" id="tp-save-btn">💾 저장</button>
        <button type="button" class="glass-btn bp-mini-btn tp-confirm-btn" id="tp-confirm-btn">✅ 확정</button>
        <button type="button" class="glass-btn bp-mini-btn" id="tp-reload-btn">↻ 로드</button>
        <button type="button" class="glass-btn bp-mini-btn tp-paint-enter" id="tp-paint-btn">🖌 맵 페인팅</button>
      </div>
      <div class="bp-hint-line" id="tp-server-line"></div>
      <textarea id="tp-memo" class="glass-input tp-memo" rows="1" placeholder="계획 메모"></textarea>
    </div>
    <div class="tp-mode-bar" id="tp-mode-bar"></div>
    <div id="tp-validation"></div>
    <div class="tp-cols">
      <div class="tp-col tp-col-left" id="tp-left"></div>
      <div class="tp-col tp-col-right" id="tp-right"></div>
    </div>
  </div>`;

  elp.stageSelect = root.querySelector('#tp-stage-select');
  elp.draftBadge = root.querySelector('#tp-draft-badge');
  elp.statusBadge = root.querySelector('#tp-status-badge');
  elp.targetInput = root.querySelector('#tp-target-input');
  elp.layersField = root.querySelector('#tp-layers-field');
  elp.totalLayers = root.querySelector('#tp-total-layers');
  elp.memo = root.querySelector('#tp-memo');
  elp.serverLine = root.querySelector('#tp-server-line');
  elp.modeBar = root.querySelector('#tp-mode-bar');
  elp.validation = root.querySelector('#tp-validation');
  elp.left = root.querySelector('#tp-left');
  elp.right = root.querySelector('#tp-right');

  elp.stageSelect.addEventListener('change', () => onStageChanged(elp.stageSelect.value));
  elp.targetInput.addEventListener('change', () => onTargetChanged(elp.targetInput.value));
  attachAutocomplete(elp.targetInput, curStage().targetLabel, v => onTargetChanged(v));
  elp.totalLayers.addEventListener('change', () => { S.totalLayers = elp.totalLayers.value; scheduleSave(); renderValidation(); });
  elp.memo.addEventListener('input', () => { S.memo = elp.memo.value; scheduleSave(); });

  root.querySelector('#tp-save-btn').addEventListener('click', () => savePlanToServer('draft'));
  root.querySelector('#tp-confirm-btn').addEventListener('click', () => {
    if (confirm('이 계획을 확정(confirmed)으로 저장할까요?')) savePlanToServer('confirmed');
  });
  root.querySelector('#tp-paint-btn').addEventListener('click', enterPaintMode);
  root.querySelector('#tp-reload-btn').addEventListener('click', async () => {
    if (!S.target.trim()) { showToast('타깃 식별자를 먼저 입력하세요.', 'warning'); return; }
    const r = await loadPlanFromServer(buildPlanId());
    if (r === 'loaded') { syncHeaderInputs(); renderAll(); refreshDetail(); refreshValidate(); refreshPaintedCountsFromServer(); showToast('서버 계획을 로드했습니다.', 'success'); }
    else if (r === 'none') showToast('서버에 저장된 계획이 없습니다.', 'info');
    else if (r === 'unsupported') { renderHeaderBadges(); showToast('서버가 transfer_plan 테이블을 제공하지 않습니다.', 'warning'); }
    else showToast('서버 계획 로드 실패.', 'error');
  });
}

export function initTransferPlan(paintController) {
  controller = paintController || null;
  const root = document.getElementById('transfer-plan-root');
  if (!root) { console.warn('[Transfer Plan] mount point missing (#transfer-plan-root)'); return; }
  buildWorkspace(root);

  const btn = document.getElementById('btn-transfer-plan');
  if (btn) btn.addEventListener('click', () => {
    const sb = document.getElementById('plan-sidebar');
    if (sb) sb.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    if (elp.targetInput) elp.targetInput.focus();
  });

  offerM1Migration();
  try {
    const raw = localStorage.getItem(LAST_KEY);
    if (raw) {
      const last = JSON.parse(raw);
      if (last && last.stage && last.target && loadDraft(last.stage, last.target)) {
        S.stage = LEGACY_STAGE_ALIASES[last.stage] || last.stage;
        S.target = last.target;
      }
    }
  } catch (e) { /* localStorage 미가용 */ }

  syncHeaderInputs();
  renderAll();
  fetchStages();
}
