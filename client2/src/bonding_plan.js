// ============================================================
// bonding_plan.js — 본딩 실험계획 M1 (map editor 우측 슬라이드 Info 패널, 조회 전용)
//
// API 계약 (총괄 고정 — 임의 변경 금지):
//   GET /api/bonding-plan/core-summary?lot=<>&slot=<>[&region=<URL인코딩 JSON>]
//     → { identity, sources(역할별 connected|missing),
//         chips{total,defect,eds_fail,used,remaining},
//         region_chips{...}(영역 요청 시),
//         history[{step,eqp,result,time,recipe,knobs{}}], warnings[] }
//   region 형식: {"rects":[{"x1","y1","x2","y2"}]} (칩 좌표, 복수 사각형 합집합)
//   코어 자동완성: GET /graph/nodes/search?label=Wafer&q= (그래프 검색 재사용)
//   Base 자동완성: 동일 API, label=Base
//
// 서버 graceful: 구버전 서버(엔드포인트 부재 404)면 "미지원" 빈 상태 안내로 강등.
// 영속화: M1은 localStorage 초안(base 식별자 키) — M2에서 관리 테이블로 승격 예정.
//   (map_split registry의 localStorage→서버 승격 전례를 따르는 평탄한 직렬화 구조)
// 영역 지정: map_editor.js의 startRegionSelection(프리셋 규격 영역 선택 모드)에 위임.
// ============================================================
import { API_BASE } from './config.js';
import { showToast } from './utils.js';
import './bonding_plan.css';

const DRAFT_PREFIX = 'bonding_plan_draft::';
const LAST_BASE_KEY = 'bonding_plan_last_base';
const DRAFT_VERSION = 1;

let editor = null; // map_editor 주입 API: { startRegionSelection }

const S = {
  open: false,
  base: '',
  totalLayers: 0,
  memo: '',
  rows: [],            // { id, layer_from, layer_to, core('lot|slot'), qty, core_region, base_region }
  nextRowId: 1,
  selectedRowId: null,
  serverSupported: null, // null=미확인 / true / false(구버전 — graceful)
  summaries: new Map(),  // summaryKey -> { status: loading|ok|error|unsupported, data, error }
  detailSeq: 0,
  compareSeq: 0,
  compareState: null,    // null | 'loading' | 'unsupported' | { cores:[], rows:[], mismatch:n }
  savedAt: null,
};

const elp = {}; // 패널 내부 DOM 참조

// ── 유틸 ────────────────────────────────────────────────
function esc(s) {
  return String(s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

function parseCore(str) {
  const v = String(str || '').trim();
  if (!v) return { lot: '', slot: '' };
  const idx = v.indexOf('|');
  if (idx < 0) return { lot: v, slot: '' };
  return { lot: v.slice(0, idx).trim(), slot: v.slice(idx + 1).trim() };
}

function layerCount(row) {
  const a = Number(row.layer_from);
  const b = Number(row.layer_to);
  if (!Number.isFinite(a) || !Number.isFinite(b) || a <= 0 || b < a) return 0;
  return b - a + 1;
}

function getSelectedRow() {
  return S.rows.find(r => r.id === S.selectedRowId) || null;
}

function fmtNum(v) {
  return (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) ? '?' : String(Number(v));
}

// ── 초안(localStorage) 직렬화 — M2 서버 승격 대비 평탄 구조 ──
function serializeDraft() {
  return {
    version: DRAFT_VERSION,
    base: S.base.trim(),
    total_layers: Number(S.totalLayers) || 0,
    memo: S.memo || '',
    assignments: S.rows.map(r => {
      const { lot, slot } = parseCore(r.core);
      return {
        layer_from: Number(r.layer_from) || null,
        layer_to: Number(r.layer_to) || null,
        core_lot: lot,
        core_slot: slot,
        qty_per_layer: Number(r.qty) || 0,
        core_region: r.core_region || null,
        base_region: r.base_region || null,
      };
    }),
    saved_at: new Date().toISOString(),
  };
}

function deserializeDraft(obj) {
  if (!obj || typeof obj !== 'object') return;
  S.totalLayers = Number(obj.total_layers) || 0;
  S.memo = typeof obj.memo === 'string' ? obj.memo : '';
  S.rows = (Array.isArray(obj.assignments) ? obj.assignments : []).map(a => ({
    id: S.nextRowId++,
    layer_from: a.layer_from ?? '',
    layer_to: a.layer_to ?? '',
    core: a.core_lot ? (a.core_slot ? `${a.core_lot}|${a.core_slot}` : a.core_lot) : '',
    qty: a.qty_per_layer ?? '',
    core_region: (a.core_region && Array.isArray(a.core_region.rects)) ? a.core_region : null,
    base_region: (a.base_region && Array.isArray(a.base_region.rects)) ? a.base_region : null,
  }));
  S.selectedRowId = S.rows.length > 0 ? S.rows[0].id : null;
  S.savedAt = obj.saved_at || null;
}

let saveTimer = null;
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveDraft, 500);
}

function saveDraft() {
  const base = S.base.trim();
  if (!base) { updateDraftBadge(); return; }
  try {
    const draft = serializeDraft();
    localStorage.setItem(DRAFT_PREFIX + base, JSON.stringify(draft));
    localStorage.setItem(LAST_BASE_KEY, base);
    S.savedAt = draft.saved_at;
    updateDraftBadge();
  } catch (e) {
    console.warn('[Bonding Plan] draft save failed:', e);
  }
}

function loadDraft(base) {
  try {
    const raw = localStorage.getItem(DRAFT_PREFIX + base);
    if (!raw) return false;
    deserializeDraft(JSON.parse(raw));
    return true;
  } catch (e) {
    console.warn('[Bonding Plan] draft load failed:', e);
    return false;
  }
}

// ── core-summary API (경계 계약의 소비측 — 방어적 파싱) ──
function summaryKey(lot, slot, region) {
  return `${lot}${slot}${region ? JSON.stringify(region) : ''}`;
}

async function getCoreSummary(lot, slot, region, force = false) {
  const key = summaryKey(lot, slot, region);
  const cached = S.summaries.get(key);
  if (!force && cached && (cached.status === 'ok' || cached.status === 'loading')) {
    if (cached.promise) await cached.promise;
    return S.summaries.get(key);
  }
  const entry = { status: 'loading' };
  entry.promise = (async () => {
    const params = new URLSearchParams({ lot: lot || '', slot: slot || '' });
    if (region && Array.isArray(region.rects) && region.rects.length > 0) {
      params.set('region', JSON.stringify(region));
    }
    const res = await fetch(`${API_BASE}/api/bonding-plan/core-summary?${params.toString()}`);
    if (res.status === 404 || res.status === 405) {
      const body = await res.json().catch(() => null);
      // FastAPI 기본 404({"detail":"Not Found"}) = 엔드포인트 부재(구버전 서버) → graceful
      if (!body || body.detail === 'Not Found' || res.status === 405) {
        S.serverSupported = false;
        entry.status = 'unsupported';
        return;
      }
      entry.status = 'error';
      entry.error = typeof body.detail === 'string' ? body.detail : 'HTTP 404';
      return;
    }
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      entry.status = 'error';
      entry.error = (body && typeof body.detail === 'string') ? body.detail : `HTTP ${res.status}`;
      return;
    }
    const data = await res.json();
    S.serverSupported = true;
    entry.status = 'ok';
    entry.data = (data && typeof data === 'object') ? data : {};
  })().catch(e => {
    entry.status = 'error';
    entry.error = e && e.message ? e.message : String(e);
  });
  S.summaries.set(key, entry);
  await entry.promise;
  return entry;
}

// sources 방어적 정규화: {role: 'connected'|'missing'} | [{role,status}] | {role:{status}}
function normalizeSources(src) {
  const out = [];
  if (!src) return out;
  if (Array.isArray(src)) {
    src.forEach(s => {
      if (s && (s.role || s.name)) out.push({ role: s.role || s.name, status: String(s.status || s.state || 'connected') });
    });
  } else if (typeof src === 'object') {
    Object.entries(src).forEach(([role, v]) => {
      const status = typeof v === 'string' ? v : String((v && (v.status || v.state)) || 'connected');
      out.push({ role, status });
    });
  }
  return out;
}

function isFailResult(h) {
  return String((h && h.result) || '').toUpperCase().includes('FAIL');
}

// ── 행 단위 파생 상태 (수량·경고 계산) ───────────────────
function rowStats(row) {
  const { lot, slot } = parseCore(row.core);
  const layers = layerCount(row);
  const qty = Number(row.qty) || 0;
  const need = qty * layers;
  const entry = lot ? S.summaries.get(summaryKey(lot, slot, null)) : null;
  const regionEntry = (lot && row.core_region) ? S.summaries.get(summaryKey(lot, slot, row.core_region)) : null;

  let remaining = null;
  let basis = '전체';
  if (regionEntry && regionEntry.status === 'ok') {
    const rc = regionEntry.data.region_chips || null;
    if (rc && rc.remaining !== undefined && rc.remaining !== null) {
      remaining = Number(rc.remaining);
      basis = '영역';
    }
  }
  if (remaining === null && entry && entry.status === 'ok' && entry.data.chips
      && entry.data.chips.remaining !== undefined && entry.data.chips.remaining !== null) {
    remaining = Number(entry.data.chips.remaining);
  }

  const hasFail = !!(entry && entry.status === 'ok' && (entry.data.history || []).some(isFailResult));
  const missing = (entry && entry.status === 'ok')
    ? normalizeSources(entry.data.sources).filter(s => s.status !== 'connected')
    : [];
  const shortage = (remaining !== null && need > 0 && remaining < need);
  return { lot, slot, layers, qty, need, remaining, basis, hasFail, missing, shortage, entry, regionEntry };
}

// ── 렌더러들 ─────────────────────────────────────────────
function updateDraftBadge() {
  if (!elp.draftBadge) return;
  if (S.savedAt) {
    const t = new Date(S.savedAt);
    const hh = String(t.getHours()).padStart(2, '0');
    const mm = String(t.getMinutes()).padStart(2, '0');
    elp.draftBadge.textContent = `초안 · ${hh}:${mm} 보관됨`;
  } else {
    elp.draftBadge.textContent = '초안';
  }
}

function syncHeaderInputs() {
  if (elp.baseInput) elp.baseInput.value = S.base;
  if (elp.totalLayers) elp.totalLayers.value = S.totalLayers || '';
  if (elp.memo) elp.memo.value = S.memo;
}

function renderValidation() {
  const box = elp.validation;
  if (!box) return;
  const T = Number(S.totalLayers) || 0;

  // 층 커버리지 (1~총층: 공백/겹침)
  let stripHtml = '';
  let covText = '';
  if (T > 0 && T <= 500) {
    const counts = new Array(T + 1).fill(0);
    S.rows.forEach(r => {
      const a = Number(r.layer_from), b = Number(r.layer_to);
      if (!Number.isFinite(a) || !Number.isFinite(b)) return;
      for (let L = Math.max(1, a); L <= Math.min(T, b); L++) counts[L]++;
    });
    const gaps = [], overlaps = [];
    let segs = '';
    for (let L = 1; L <= T; L++) {
      const cls = counts[L] === 0 ? 'gap' : (counts[L] > 1 ? 'overlap' : 'cov');
      if (counts[L] === 0) gaps.push(L);
      if (counts[L] > 1) overlaps.push(L);
      segs += `<div class="bp-cov-seg ${cls}" title="층 ${L}: ${counts[L]}건 배정"></div>`;
    }
    stripHtml = `<div class="bp-coverage-strip">${segs}</div>`;
    const list = (arr) => arr.slice(0, 12).join(', ') + (arr.length > 12 ? ' …' : '');
    covText = `<div class="bp-coverage-text">커버리지 1–${T}층 · `
      + (gaps.length ? `공백 ${gaps.length}층 (${list(gaps)})` : '공백 없음')
      + ' · '
      + (overlaps.length ? `겹침 ${overlaps.length}층 (${list(overlaps)})` : '겹침 없음')
      + '</div>';
  } else {
    covText = '<div class="bp-coverage-text">총 층수를 입력하면 층 커버리지를 검증합니다.</div>';
  }

  // 경고 3종 배지 (수량 / FAIL / 조건 이탈)
  const stats = S.rows.map(rowStats);
  const loaded = stats.filter(st => st.entry && st.entry.status === 'ok').length;
  const shortage = stats.filter(st => st.shortage).length;
  const fails = stats.filter(st => st.hasFail).length;
  let mismatchBadge;
  if (S.compareState && typeof S.compareState === 'object' && Array.isArray(S.compareState.rows)) {
    const n = S.compareState.mismatch;
    mismatchBadge = `<span class="bp-vbadge ${n > 0 ? 'warn' : 'ok'}">조건 이탈 ${n}</span>`;
  } else {
    mismatchBadge = '<span class="bp-vbadge" title="knob 비교를 로드하면 계산됩니다">조건 이탈 미계산</span>';
  }
  const badges = `<div class="bp-vbadges">
    <span class="bp-vbadge ${shortage > 0 ? 'bad' : (loaded > 0 ? 'ok' : '')}">수량 부족 ${loaded > 0 ? shortage : '미조회'}</span>
    <span class="bp-vbadge ${fails > 0 ? 'bad' : (loaded > 0 ? 'ok' : '')}">FAIL 이력 ${loaded > 0 ? fails : '미조회'}</span>
    ${mismatchBadge}
  </div>`;

  box.innerHTML = badges + stripHtml + covText;
}

function regionBtnLabel(which, region) {
  const n = (region && Array.isArray(region.rects)) ? region.rects.length : 0;
  const name = which === 'core' ? '▦ core 영역' : '▦ base 부착';
  return `${name} <b>${n}</b>`;
}

function drawThumb(canvas, region) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  const rects = (region && Array.isArray(region.rects)) ? region.rects : [];
  const cs = getComputedStyle(document.documentElement);
  const accent = (cs.getPropertyValue('--accent') || '').trim() || '#1a66d0';
  const border = (cs.getPropertyValue('--border') || '').trim() || '#d7dce4';
  if (!rects.length) {
    ctx.strokeStyle = border;
    ctx.setLineDash([3, 3]);
    ctx.strokeRect(1.5, 1.5, W - 3, H - 3);
    ctx.setLineDash([]);
    return;
  }
  const x1 = Math.min(...rects.map(r => r.x1));
  const x2 = Math.max(...rects.map(r => r.x2));
  const y1 = Math.min(...rects.map(r => r.y1));
  const y2 = Math.max(...rects.map(r => r.y2));
  const spanX = Math.max(1, x2 - x1 + 1);
  const spanY = Math.max(1, y2 - y1 + 1);
  const pad = 3;
  const sx = (W - pad * 2) / spanX;
  const sy = (H - pad * 2) / spanY;
  rects.forEach(r => {
    const rx = pad + (r.x1 - x1) * sx;
    const ry = pad + (r.y1 - y1) * sy;
    const rw = Math.max(2, (r.x2 - r.x1 + 1) * sx);
    const rh = Math.max(2, (r.y2 - r.y1 + 1) * sy);
    ctx.globalAlpha = 0.28;
    ctx.fillStyle = accent;
    ctx.fillRect(rx, ry, rw, rh);
    ctx.globalAlpha = 1.0;
    ctx.strokeStyle = accent;
    ctx.lineWidth = 1;
    ctx.strokeRect(rx + 0.5, ry + 0.5, rw - 1, rh - 1);
  });
}

function rowStatusHtml(st) {
  if (!st.lot) return '<span class="bp-row-status">core 미입력</span>';
  if (!st.entry) return '<span class="bp-row-status">미조회</span>';
  if (st.entry.status === 'loading') return '<span class="bp-row-status">조회 중…</span>';
  if (st.entry.status === 'unsupported') return '<span class="bp-row-status">서버 미지원</span>';
  if (st.entry.status === 'error') return '<span class="bp-row-status bad">조회 실패</span>';
  const cls = st.shortage ? 'bad' : 'ok';
  const rem = fmtNum(st.remaining);
  return `<span class="bp-row-status ${cls}">잔여 ${rem}${st.basis === '영역' ? '(영역)' : ''} / 소요 ${st.need || '?'}</span>`;
}

function renderRows() {
  const box = elp.rows;
  if (!box) return;
  if (S.rows.length === 0) {
    box.innerHTML = '<div class="bp-empty-hint">배정이 없습니다. [+ 배정 추가]로 층 범위·코어를 배정하세요.<br>'
      + '행 = (시작층–끝층, core lot|slot, 층당 수량, core 사용 영역, base 부착 영역)</div>';
    return;
  }
  box.innerHTML = S.rows.map((row, i) => {
    const st = rowStats(row);
    const warn = st.shortage || st.hasFail || st.missing.length > 0;
    const warnChips = [];
    if (st.shortage) warnChips.push(`<span class="bp-warn-chip">⚠️ 수량 부족 (잔여 ${fmtNum(st.remaining)} &lt; 소요 ${st.need})</span>`);
    if (st.hasFail) warnChips.push('<span class="bp-warn-chip">⚠️ FAIL 이력</span>');
    st.missing.forEach(m => warnChips.push(`<span class="bp-warn-chip missing">${esc(m.role)} 미연결</span>`));
    return `
    <div class="bp-row ${S.selectedRowId === row.id ? 'selected' : ''} ${warn ? 'warn' : ''}" data-id="${row.id}">
      <div class="bp-row-line1">
        <span class="bp-row-idx">${i + 1}</span>
        <input class="bp-in-lf glass-input" type="number" min="1" title="시작 층" placeholder="from" value="${esc(row.layer_from ?? '')}" />
        <span class="bp-dash">–</span>
        <input class="bp-in-lt glass-input" type="number" min="1" title="끝 층" placeholder="to" value="${esc(row.layer_to ?? '')}" />
        <span class="bp-ac-wrap bp-core-wrap"><input class="bp-in-core glass-input" placeholder="core lot|slot" value="${esc(row.core)}" autocomplete="off" /></span>
        <input class="bp-in-qty glass-input" type="number" min="0" title="층당 수량" placeholder="층당" value="${esc(row.qty ?? '')}" />
      </div>
      <div class="bp-row-line2">
        <button type="button" class="bp-region-btn" data-which="core">${regionBtnLabel('core', row.core_region)}</button>
        <canvas class="bp-thumb" data-which="core" width="54" height="36"></canvas>
        <button type="button" class="bp-region-btn" data-which="base">${regionBtnLabel('base', row.base_region)}</button>
        <canvas class="bp-thumb" data-which="base" width="54" height="36"></canvas>
        ${rowStatusHtml(st)}
        <span class="bp-row-tools">
          <button type="button" class="bp-tool" data-act="up" title="위로">↑</button>
          <button type="button" class="bp-tool" data-act="down" title="아래로">↓</button>
          <button type="button" class="bp-tool bp-tool-del" data-act="del" title="행 삭제">🗑</button>
        </span>
      </div>
      ${warnChips.length ? `<div class="bp-row-warnline">${warnChips.join('')}</div>` : ''}
    </div>`;
  }).join('');

  // 이벤트 배선 + 썸네일
  box.querySelectorAll('.bp-row').forEach(rowEl => {
    const id = Number(rowEl.dataset.id);
    const row = S.rows.find(r => r.id === id);
    if (!row) return;

    rowEl.addEventListener('click', (e) => {
      if (e.target.closest('input, button, canvas')) return;
      selectRow(id);
    });

    const inLf = rowEl.querySelector('.bp-in-lf');
    const inLt = rowEl.querySelector('.bp-in-lt');
    const inCore = rowEl.querySelector('.bp-in-core');
    const inQty = rowEl.querySelector('.bp-in-qty');

    inLf.addEventListener('change', () => { row.layer_from = inLf.value; onRowFieldChanged(row); });
    inLt.addEventListener('change', () => { row.layer_to = inLt.value; onRowFieldChanged(row); });
    inQty.addEventListener('change', () => { row.qty = inQty.value; onRowFieldChanged(row); });
    inCore.addEventListener('change', () => {
      if (row.core !== inCore.value.trim()) {
        row.core = inCore.value.trim();
        onRowCoreChanged(row);
      }
    });
    attachAutocomplete(inCore, 'Wafer', (v) => {
      row.core = v;
      onRowCoreChanged(row);
    });

    rowEl.querySelectorAll('.bp-region-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        selectRow(id, { skipFetch: true });
        pickRegion(id, btn.dataset.which);
      });
    });

    rowEl.querySelectorAll('.bp-tool').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const act = btn.dataset.act;
        const idx = S.rows.findIndex(r => r.id === id);
        if (act === 'del') {
          S.rows.splice(idx, 1);
          if (S.selectedRowId === id) S.selectedRowId = S.rows.length ? S.rows[Math.min(idx, S.rows.length - 1)].id : null;
        } else if (act === 'up' && idx > 0) {
          [S.rows[idx - 1], S.rows[idx]] = [S.rows[idx], S.rows[idx - 1]];
        } else if (act === 'down' && idx < S.rows.length - 1) {
          [S.rows[idx + 1], S.rows[idx]] = [S.rows[idx], S.rows[idx + 1]];
        }
        scheduleSave();
        renderRows();
        renderValidation();
        renderDetail();
      });
    });

    rowEl.querySelectorAll('.bp-thumb').forEach(cv => {
      drawThumb(cv, cv.dataset.which === 'core' ? row.core_region : row.base_region);
    });
  });
}

// 포커스가 행 입력에 있는 동안에는 재렌더로 포커스를 깨지 않는다
function safeRenderRows() {
  if (elp.rows && elp.rows.contains(document.activeElement)) return;
  renderRows();
}

function onRowFieldChanged(row) {
  scheduleSave();
  renderRows();
  renderValidation();
  if (S.selectedRowId === row.id) renderDetail();
}

function onRowCoreChanged(row) {
  scheduleSave();
  S.compareState = null; // 코어 구성 변경 → 비교 무효화
  renderCompare();
  renderRows();
  if (S.selectedRowId === row.id) refreshDetail();
  else renderValidation();
}

function selectRow(id, opts = {}) {
  if (S.selectedRowId !== id) {
    S.selectedRowId = id;
    renderRows();
  }
  if (!opts.skipFetch) refreshDetail();
}

// ── 코어 상세 (행 선택 시 core-summary 조회) ─────────────
async function refreshDetail(force = false) {
  const row = getSelectedRow();
  renderDetail();
  if (!row) return;
  const { lot, slot } = parseCore(row.core);
  if (!lot) return;
  const seq = ++S.detailSeq;
  const jobs = [getCoreSummary(lot, slot, null, force)];
  if (row.core_region) jobs.push(getCoreSummary(lot, slot, row.core_region, force));
  await Promise.all(jobs);
  if (seq !== S.detailSeq) return; // 검색 세션 가드 — stale 응답 폐기
  renderDetail();
  safeRenderRows();
  renderValidation();
}

function unsupportedHtml() {
  return `<div class="bp-empty-hint">🔌 서버가 본딩 실험계획 API(core-summary)를 아직 제공하지 않습니다 (구버전).<br>
    서버 업데이트·재기동 후 <b>다시 시도</b>하세요. 층 배정·영역·메모 초안은 계속 편집/보관됩니다.
    <div style="margin-top:8px;"><button type="button" class="glass-btn" id="bp-retry-btn">다시 시도</button></div></div>`;
}

function bindRetry(box) {
  const btn = box.querySelector('#bp-retry-btn');
  if (btn) btn.addEventListener('click', () => refreshDetail(true));
}

function renderDetail() {
  const box = elp.detail;
  if (!box) return;
  const row = getSelectedRow();
  if (elp.detailCore) elp.detailCore.textContent = row && row.core ? `· ${row.core}` : '';

  if (!row) {
    box.innerHTML = '<div class="bp-empty-hint">배정 행을 선택하면 해당 코어의 수량·공정 이력을 조회합니다.</div>';
    return;
  }
  const { lot, slot } = parseCore(row.core);
  if (!lot) {
    box.innerHTML = '<div class="bp-empty-hint">이 행의 core lot|slot을 입력하면 core-summary를 조회합니다.</div>';
    return;
  }
  const entry = S.summaries.get(summaryKey(lot, slot, null));
  if (!entry || entry.status === 'loading') {
    box.innerHTML = '<div class="bp-empty-hint">core-summary 조회 중…</div>';
    return;
  }
  if (entry.status === 'unsupported') {
    box.innerHTML = unsupportedHtml();
    bindRetry(box);
    return;
  }
  if (entry.status === 'error') {
    box.innerHTML = `<div class="bp-empty-hint">조회 실패: ${esc(entry.error || '')}
      <div style="margin-top:8px;"><button type="button" class="glass-btn" id="bp-retry-btn">다시 시도</button></div></div>`;
    bindRetry(box);
    return;
  }

  const data = entry.data || {};
  const st = rowStats(row);
  const chips = data.chips || {};
  const sources = normalizeSources(data.sources);

  // 소스 연결 배지 (missing 역할 = "미연결")
  const srcHtml = sources.length
    ? `<div class="bp-src-badges">${sources.map(s =>
        `<span class="bp-src ${s.status !== 'connected' ? 'missing' : ''}">${esc(s.role)}${s.status !== 'connected' ? ' · 미연결' : ''}</span>`
      ).join('')}</div>`
    : '';

  // 수량 라인: 잔여 = 총 − defect − EDS − 기사용
  const chipsHtml = `<div class="bp-chips-line">잔여 <span class="rem">${fmtNum(chips.remaining)}</span>
    = 총 ${fmtNum(chips.total)} − defect ${fmtNum(chips.defect)} − EDS ${fmtNum(chips.eds_fail)} − 기사용 ${fmtNum(chips.used)}</div>`;

  // 영역 요약 (region 파라미터 재조회 결과)
  let regionHtml = '';
  if (row.core_region && Array.isArray(row.core_region.rects) && row.core_region.rects.length > 0) {
    const rEntry = S.summaries.get(summaryKey(lot, slot, row.core_region));
    const n = row.core_region.rects.length;
    if (rEntry && rEntry.status === 'ok' && rEntry.data.region_chips) {
      regionHtml = `<div class="bp-region-line">▦ core 사용 영역: ${n} rects · 영역 내 가용 ${fmtNum(rEntry.data.region_chips.remaining)}칩</div>`;
    } else if (rEntry && rEntry.status === 'loading') {
      regionHtml = `<div class="bp-region-line">▦ core 사용 영역: ${n} rects · 영역 재조회 중…</div>`;
    } else {
      regionHtml = `<div class="bp-region-line">▦ core 사용 영역: ${n} rects · 영역 가용 미확인</div>`;
    }
  }

  // 소요 = 층당 수량 × 층 수
  let needHtml = '';
  if (st.need > 0) {
    const remTxt = st.remaining === null ? '?' : st.remaining;
    const basisTxt = st.basis === '영역' ? ' (영역 기준)' : '';
    if (st.shortage) {
      needHtml = `<div class="bp-need-line bad">⚠️ 잔여 ${remTxt}${basisTxt} &lt; 소요 ${st.need} = 층당 ${st.qty} × ${st.layers}층 — ${st.need - st.remaining}칩 부족</div>`;
    } else {
      needHtml = `<div class="bp-need-line">소요 ${st.need} = 층당 ${st.qty} × ${st.layers}층 · 잔여 ${remTxt}${basisTxt} 충족</div>`;
    }
  } else {
    needHtml = '<div class="bp-region-line">층 범위·층당 수량을 입력하면 소요/잔여를 검증합니다.</div>';
  }

  // 서버 경고
  const warns = Array.isArray(data.warnings) ? data.warnings : [];
  const warnsHtml = warns.length
    ? `<div class="bp-server-warns">${warns.map(w => `<span>⚠️ ${esc(typeof w === 'string' ? w : JSON.stringify(w))}</span>`).join('')}</div>`
    : '';

  // 공정 이력 타임라인 (FAIL 강조, 클릭 시 knob 목록 확장)
  const history = Array.isArray(data.history) ? data.history : [];
  const historyHtml = history.length
    ? `<div class="bp-history">${history.map((h, i) => {
        const fail = isFailResult(h);
        const knobs = (h && h.knobs && typeof h.knobs === 'object') ? Object.entries(h.knobs) : [];
        return `<div class="bp-step ${fail ? 'bp-step-fail' : ''}" data-idx="${i}" title="클릭: knob 목록">
          <div class="bp-step-head">
            <span class="bp-step-name">${esc(h.step ?? '?')}</span>
            ${h.result !== undefined && h.result !== null ? `<span class="bp-step-result">${esc(h.result)}</span>` : ''}
            ${h.eqp ? `<span class="bp-step-eqp">${esc(h.eqp)}</span>` : ''}
            ${h.recipe ? `<span class="bp-step-recipe">${esc(h.recipe)}</span>` : ''}
            ${h.time ? `<span class="bp-step-time">${esc(h.time)}</span>` : ''}
          </div>
          <div class="bp-knobs">${knobs.length
            ? knobs.map(([k, v]) => `<span class="bp-knob-chip">${esc(k)} · ${esc(v)}</span>`).join('')
            : '<span class="bp-knob-chip">knob 없음</span>'}</div>
        </div>`;
      }).join('')}</div>`
    : '<div class="bp-region-line">공정 이력이 없습니다.</div>';

  const identity = data.identity ? `<div class="bp-mono bp-muted">${esc(typeof data.identity === 'string' ? data.identity : JSON.stringify(data.identity))}</div>` : '';

  box.innerHTML = `<div class="bp-detail-card">
    ${identity}
    ${srcHtml}
    ${chipsHtml}
    ${regionHtml}
    ${needHtml}
    ${warnsHtml}
  </div>
  <div class="bp-detail-card">
    <div class="bp-muted">공정 이력 (step 클릭 → knob 목록)</div>
    ${historyHtml}
  </div>`;

  box.querySelectorAll('.bp-step').forEach(stepEl => {
    stepEl.addEventListener('click', () => stepEl.classList.toggle('open'));
  });
}

// ── knob 비교 뷰 (공통 step × 코어, 값 상이 셀 하이라이트) ──
function uniqueCores() {
  const seen = new Set();
  const out = [];
  S.rows.forEach(r => {
    const { lot, slot } = parseCore(r.core);
    if (!lot) return;
    const label = slot ? `${lot}|${slot}` : lot;
    if (seen.has(label)) return;
    seen.add(label);
    out.push({ lot, slot, label });
  });
  return out;
}

function buildKnobCompare(perCore) {
  // perCore: [{ label, data }] — step명 기준 마지막 이력의 knobs 사용
  const stepMaps = perCore.map(x => {
    const m = new Map();
    (x.data.history || []).forEach(h => {
      if (h && h.step !== undefined && h.step !== null) m.set(String(h.step), (h.knobs && typeof h.knobs === 'object') ? h.knobs : {});
    });
    return m;
  });
  let common = null;
  stepMaps.forEach(m => {
    const names = new Set(m.keys());
    common = common === null ? names : new Set([...common].filter(n => names.has(n)));
  });
  const rows = [];
  [...(common || [])].forEach(step => {
    const keys = new Set();
    stepMaps.forEach(m => Object.keys(m.get(step) || {}).forEach(k => keys.add(k)));
    if (keys.size === 0) {
      rows.push({ step, knob: '(knob 없음)', vals: stepMaps.map(() => '—'), mismatch: false });
      return;
    }
    [...keys].forEach(k => {
      const vals = stepMaps.map(m => {
        const kn = m.get(step) || {};
        return (kn[k] !== undefined && kn[k] !== null) ? String(kn[k]) : '—';
      });
      const distinct = new Set(vals);
      rows.push({ step, knob: k, vals, mismatch: distinct.size > 1 });
    });
  });
  return rows;
}

async function loadCompare() {
  const cores = uniqueCores();
  if (cores.length === 0) {
    showToast('배정된 코어가 없습니다.', 'warning');
    return;
  }
  S.compareState = 'loading';
  renderCompare();
  const seq = ++S.compareSeq;
  const entries = await Promise.all(cores.map(c => getCoreSummary(c.lot, c.slot, null)));
  if (seq !== S.compareSeq) return;
  if (entries.every(e => e.status === 'unsupported')) {
    S.compareState = 'unsupported';
    renderCompare();
    renderValidation();
    return;
  }
  const ok = cores.map((c, i) => ({ label: c.label, data: entries[i].status === 'ok' ? entries[i].data : null }))
    .filter(x => x.data);
  const rows = ok.length >= 1 ? buildKnobCompare(ok) : [];
  S.compareState = {
    cores: ok.map(x => x.label),
    skipped: cores.length - ok.length,
    rows,
    mismatch: rows.filter(r => r.mismatch).length,
  };
  renderCompare();
  renderValidation();
  safeRenderRows();
}

function renderCompare() {
  const box = elp.compare;
  if (!box) return;
  const cs = S.compareState;
  if (!cs) {
    box.innerHTML = '<div class="bp-empty-hint">[비교 로드]를 누르면 배정 코어들이 공통으로 거친 step의 knob을 표로 비교합니다.<br>값이 다른 셀만 하이라이트(조건 이탈 경고)됩니다.</div>';
    return;
  }
  if (cs === 'loading') {
    box.innerHTML = '<div class="bp-empty-hint">코어별 core-summary 수집 중…</div>';
    return;
  }
  if (cs === 'unsupported') {
    box.innerHTML = unsupportedHtml();
    bindRetry(box);
    return;
  }
  if (!cs.cores.length) {
    box.innerHTML = '<div class="bp-empty-hint">비교 가능한 코어 요약이 없습니다 (조회 실패/데이터 없음).</div>';
    return;
  }
  if (!cs.rows.length) {
    box.innerHTML = `<div class="bp-empty-hint">코어 ${cs.cores.length}개가 공통으로 거친 step이 없습니다.</div>`;
    return;
  }
  const head = `<tr><th class="bp-key-col">step</th><th class="bp-key-col">knob</th>${cs.cores.map(c => `<th>${esc(c)}</th>`).join('')}</tr>`;
  const body = cs.rows.map(r =>
    `<tr><td class="bp-key-col">${esc(r.step)}</td><td class="bp-key-col">${esc(r.knob)}</td>`
    + r.vals.map(v => `<td class="${r.mismatch ? 'bp-mismatch' : ''}">${esc(v)}</td>`).join('')
    + '</tr>'
  ).join('');
  const note = `<div class="bp-coverage-text">공통 step ${new Set(cs.rows.map(r => r.step)).size}개 · 조건 이탈 ${cs.mismatch}셀행`
    + (cs.skipped ? ` · 요약 미확보 코어 ${cs.skipped}개 제외` : '') + '</div>';
  box.innerHTML = `${note}<table class="bp-compare-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

// ── 영역 지정 (map_editor 영역 선택 모드 위임) ───────────
function pickRegion(rowId, which) {
  const row = S.rows.find(r => r.id === rowId);
  if (!row) return;
  if (!editor || typeof editor.startRegionSelection !== 'function') return;
  if (which === 'core' && !parseCore(row.core).lot) {
    showToast('core lot|slot을 먼저 입력하세요.', 'warning');
    return;
  }
  const key = which === 'core' ? 'core_region' : 'base_region';
  const label = which === 'core'
    ? `코어 ${row.core} 사용 영역`
    : `Base ${S.base.trim() || '(미지정)'} 부착 영역`;
  setOpen(false); // 캔버스 시야 확보 — 완료/취소 시 재개방
  editor.startRegionSelection({
    kind: which,
    label,
    initialRects: (row[key] && row[key].rects) || [],
    onFinish: (rects) => {
      setOpen(true);
      if (rects === null) return; // 취소 — 변경 없음
      row[key] = rects.length > 0 ? { rects } : null;
      scheduleSave();
      renderRows();
      if (which === 'core' && S.selectedRowId === row.id) {
        refreshDetail(true); // region 파라미터 재조회 (영역 내 가용칩)
      } else {
        renderValidation();
      }
    },
  });
}

// ── 자동완성 (그래프 search API 재사용 — seq 가드 + debounce) ──
function attachAutocomplete(input, label, onPick) {
  const wrap = input.closest('.bp-ac-wrap') || input.parentElement;
  if (!wrap) return;
  const list = document.createElement('div');
  list.className = 'bp-ac-list';
  list.style.display = 'none';
  wrap.appendChild(list);
  let seq = 0;
  let timer = null;

  const hide = () => { list.style.display = 'none'; };

  const search = async (q) => {
    const mySeq = ++seq;
    try {
      const params = new URLSearchParams({ q, label, limit: '15' });
      const res = await fetch(`${API_BASE}/graph/nodes/search?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (mySeq !== seq) return;
      const items = (Array.isArray(data) ? data : (data.nodes || data.results || data.items || []))
        .filter(x => x && x.identity_key !== undefined);
      if (!items.length) {
        list.innerHTML = `<div class="bp-ac-empty">일치 노드 없음 (label=${esc(label)}) — 수기 입력 가능</div>`;
      } else {
        list.innerHTML = items.map(x =>
          `<div class="bp-ac-item" data-v="${esc(String(x.identity_key))}">${esc(String(x.identity_key))}</div>`
        ).join('');
        list.querySelectorAll('.bp-ac-item').forEach(item => {
          item.addEventListener('mousedown', (e) => {
            e.preventDefault(); // blur로 리스트가 닫히기 전 선택 확정
            input.value = item.dataset.v;
            hide();
            onPick(item.dataset.v);
          });
        });
      }
      list.style.display = 'block';
    } catch (e) {
      if (mySeq === seq) hide(); // 그래프 검색 미가용 — 수기 입력 폴백 (graceful)
    }
  };

  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { hide(); return; }
    timer = setTimeout(() => search(q), 200);
  });
  input.addEventListener('blur', () => setTimeout(hide, 120));
  input.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
}

// ── base 전환/초안 복원 ─────────────────────────────────
function onBaseChanged(newBase) {
  const base = String(newBase || '').trim();
  const prev = S.base.trim();
  if (base === prev) return;
  if (prev) saveDraft(); // 이전 base 초안 확정 저장
  S.base = base;
  if (!base) { updateDraftBadge(); return; }
  try { localStorage.setItem(LAST_BASE_KEY, base); } catch (e) { /* noop */ }
  if (loadDraft(base)) {
    showToast(`'${base}' 초안을 복원했습니다.`, 'info');
    S.compareState = null;
    syncHeaderInputs();
    renderAll();
    refreshDetail();
  } else {
    scheduleSave(); // 현재 편집 내용을 새 base 키로 이어서 보관
    renderValidation();
  }
}

// ── 패널 골격 / 진입점 ──────────────────────────────────
function setOpen(open) {
  S.open = !!open;
  if (!elp.panel) return;
  elp.panel.classList.toggle('open', S.open);
  elp.panel.setAttribute('aria-hidden', S.open ? 'false' : 'true');
}

function renderAll() {
  updateDraftBadge();
  renderValidation();
  renderRows();
  renderDetail();
  renderCompare();
}

function buildPanel(root) {
  root.innerHTML = `
  <aside id="bonding-plan-panel" class="bp-panel" aria-hidden="true">
    <header class="bp-header">
      <div class="bp-header-title">
        <h2>🧪 본딩 실험계획</h2>
        <span class="bp-badge bp-badge-draft" id="bp-draft-badge">초안</span>
        <span class="bp-badge bp-badge-m1">M1 조회 전용</span>
      </div>
      <button type="button" class="bp-close" id="bp-close" title="패널 닫기">✕</button>
    </header>
    <p class="bp-subnote">계획 저장(관리 테이블)은 다음 단계(M2)에서 지원됩니다 — 현재는 Base 식별자를 키로 이 브라우저(localStorage)에 초안이 자동 보관/복원됩니다.</p>
    <div class="bp-scroll">
      <section class="bp-section">
        <div class="bp-field-grid">
          <div class="bp-field bp-ac-wrap" style="grid-column: span 2;">
            <label for="bp-base-input">Base 식별자</label>
            <input id="bp-base-input" class="glass-input" type="text" placeholder="Base 노드 검색 (label=Base)" autocomplete="off" />
          </div>
          <div class="bp-field">
            <label for="bp-total-layers">총 층수</label>
            <input id="bp-total-layers" class="glass-input" type="number" min="1" max="500" placeholder="예: 8" />
          </div>
        </div>
        <div class="bp-field">
          <label for="bp-memo">실험 메모 (자연어)</label>
          <textarea id="bp-memo" class="glass-input" rows="2" placeholder="실험 목적·조건·특이사항 자유 기술"></textarea>
        </div>
      </section>
      <section class="bp-section">
        <h3>검증</h3>
        <div id="bp-validation"></div>
      </section>
      <section class="bp-section">
        <div class="bp-section-head">
          <h3>층 범위 배정</h3>
          <button type="button" class="glass-btn" id="bp-add-row" style="padding: 4px 12px; font-size: 0.76rem;">+ 배정 추가</button>
        </div>
        <div id="bp-rows"></div>
      </section>
      <section class="bp-section">
        <h3>코어 상세 <span class="bp-muted bp-mono" id="bp-detail-core"></span></h3>
        <div id="bp-detail"></div>
      </section>
      <section class="bp-section">
        <div class="bp-section-head">
          <h3>knob 비교 (공통 step)</h3>
          <button type="button" class="glass-btn" id="bp-compare-btn" style="padding: 4px 12px; font-size: 0.76rem;">비교 로드</button>
        </div>
        <div id="bp-compare"></div>
      </section>
    </div>
  </aside>`;

  elp.panel = root.querySelector('#bonding-plan-panel');
  elp.draftBadge = root.querySelector('#bp-draft-badge');
  elp.baseInput = root.querySelector('#bp-base-input');
  elp.totalLayers = root.querySelector('#bp-total-layers');
  elp.memo = root.querySelector('#bp-memo');
  elp.validation = root.querySelector('#bp-validation');
  elp.rows = root.querySelector('#bp-rows');
  elp.detail = root.querySelector('#bp-detail');
  elp.detailCore = root.querySelector('#bp-detail-core');
  elp.compare = root.querySelector('#bp-compare');

  root.querySelector('#bp-close').addEventListener('click', () => setOpen(false));
  root.querySelector('#bp-add-row').addEventListener('click', () => {
    const last = S.rows[S.rows.length - 1];
    const nextFrom = last && Number(last.layer_to) > 0 ? Number(last.layer_to) + 1 : 1;
    const row = {
      id: S.nextRowId++,
      layer_from: nextFrom,
      layer_to: '',
      core: '',
      qty: '',
      core_region: null,
      base_region: null,
    };
    S.rows.push(row);
    S.selectedRowId = row.id;
    scheduleSave();
    renderRows();
    renderValidation();
    renderDetail();
    const coreInput = elp.rows.querySelector(`.bp-row[data-id="${row.id}"] .bp-in-core`);
    if (coreInput) coreInput.focus();
  });
  root.querySelector('#bp-compare-btn').addEventListener('click', loadCompare);

  elp.baseInput.addEventListener('change', () => onBaseChanged(elp.baseInput.value));
  attachAutocomplete(elp.baseInput, 'Base', (v) => onBaseChanged(v));
  elp.totalLayers.addEventListener('change', () => {
    S.totalLayers = elp.totalLayers.value;
    scheduleSave();
    renderValidation();
    safeRenderRows();
    renderDetail();
  });
  elp.memo.addEventListener('input', () => {
    S.memo = elp.memo.value;
    scheduleSave();
  });
}

export function initBondingPlan(editorApi) {
  editor = editorApi || {};
  const root = document.getElementById('bonding-plan-root');
  const btn = document.getElementById('btn-bonding-plan');
  if (!root || !btn) {
    console.warn('[Bonding Plan] mount points missing (bonding-plan-root / btn-bonding-plan)');
    return;
  }
  buildPanel(root);

  btn.addEventListener('click', () => {
    setOpen(!S.open);
    if (S.open && getSelectedRow()) refreshDetail();
  });

  // 마지막 편집 base의 초안 복원 (패널은 닫힌 상태 유지)
  try {
    const lastBase = localStorage.getItem(LAST_BASE_KEY);
    if (lastBase && loadDraft(lastBase)) {
      S.base = lastBase;
    }
  } catch (e) { /* localStorage 미가용 — 초안 없이 시작 */ }

  syncHeaderInputs();
  renderAll();
}
