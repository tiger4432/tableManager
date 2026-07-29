// ============================================================
// trace.js — G2 추적 리포트 페이지 (trace.html entry)
// - 시드 기점 다중 추적: POST /graph/trace (지시서 확정 계약 — 서버 코드 미참조)
//     요청  {seeds:[{label,identity}], depth:1..3(기본2), time_from?, time_to?, limit}
//     응답  {nodes:[{id,label,identity_key,props}],
//            edges:[{from,to,type,source_name,updated_by,event_time}],
//            seed_ids:[int], missing_seeds:[], truncated}
// - 진입: index 그리드 → trace.html?seeds=<urlencoded JSON [{label, identity}]>
// - 좌: 라벨별 엔티티 그룹 테이블(행 클릭 → graph.html?label=&identity= 새 탭)
//   우: event_time 시간순 타임라인(user provenance 강조) + 구조 엣지 접이식
// - 조립은 전부 클라이언트(응답 ≤1000 노드 유계) — 단, DOM 폭주 방지로 청크 렌더
// - admin/graph_viewer 선례: 자체 모듈 지역 상태 (state.js/dom.js 미임포트)
// ============================================================
import './tokens.css';
import { API_BASE } from './config.js';
import { showToast } from './utils.js';
import { initTheme } from './theme.js';
// [V1 effort instrument] The ONE collector (effort_meter.js). No corrections are written
// here, so nothing carries an `effort` payload — but LEAVING must be counted, or the trip
// grid -> trace -> grid records only its outbound half and the detour looks free.
import { ROUTES, startSession, installGlobalListeners, installNavLinkCounting } from './effort_meter.js';
import {
  SEED_CAP,
  TRACE_LIMIT,
  parseSeedsParam,
  capSeeds,
  buildTraceRequest,
  normalizeMissingSeeds,
  isSeedMissing,
  groupNodesByLabel,
  splitTimeline,
  propsSummary,
  fmtEventTime,
  truncateText,
} from './trace_core.js';

const GROUP_ROW_CHUNK = 100;   // 그룹 테이블 1회 렌더 행 수 (이후 "더 보기")
const TIMELINE_CHUNK = 300;    // 타임라인 1회 렌더 항목 수

const el = (id) => document.getElementById(id);

// HTML 이스케이프 — DB 유래 identity/props/type을 DOM에 넣을 때 필수
const esc = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ── 지역 상태 (싱글턴) ─────────────────────────────────────
const S = {
  seeds: [],            // [{label, identity}]
  depth: 2,
  timeFrom: '',
  timeTo: '',

  nodes: [],
  edges: [],
  nodesById: new Map(),
  seedIds: new Set(),
  missing: [],          // normalize된 missing_seeds
  truncated: false,
  hasResult: false,     // 성공 응답을 한 번이라도 그렸는가 (재실행 실패 시 유지용)

  seq: 0,               // 요청 시퀀스 가드 (stale 응답 폐기)
};

// ── 라벨 → 팔레트 토큰 (graph_viewer와 동일 규약: 등장 순서 고정) ──
const PALETTE_TOKENS = ['--accent', '--accent-2', '--success', '--orange', '--info', '--danger', '--warning'];
const labelPaletteIdx = new Map();

function labelToken(label) {
  if (!labelPaletteIdx.has(label)) {
    labelPaletteIdx.set(label, labelPaletteIdx.size % PALETTE_TOKENS.length);
  }
  return PALETTE_TOKENS[labelPaletteIdx.get(label)];
}

// ── 크로스링크: graph.html 초기 중심 파라미터 ───────────────
function graphUrl(label, identity) {
  return `graph.html?label=${encodeURIComponent(label)}&identity=${encodeURIComponent(identity)}`;
}

function openInViewer(label, identity) {
  window.open(graphUrl(label, identity), '_blank');
}

// ── 상태 화면 전환 ──────────────────────────────────────────
const STATE_IDS = ['state-no-seeds', 'state-loading', 'state-error', 'state-empty', 'report-view'];

function showState(name) {
  for (const id of STATE_IDS) {
    el(id).style.display = (id === name) ? 'flex' : 'none';
  }
  el('meta-bar').style.display = (name === 'report-view') ? 'flex' : 'none';
}

// ── URL 동기화 (새로고침/공유 시 조건 유지) ─────────────────
function syncUrl() {
  const qp = new URLSearchParams();
  qp.set('seeds', JSON.stringify(S.seeds));
  if (S.depth !== 2) qp.set('depth', String(S.depth));
  if (S.timeFrom) qp.set('from', S.timeFrom);
  if (S.timeTo) qp.set('to', S.timeTo);
  window.history.replaceState(null, '', `${window.location.pathname}?${qp.toString()}`);
}

// ============================================================
// [1] 추적 실행
// ============================================================
async function runTrace() {
  if (!S.seeds.length) {
    S.hasResult = false;
    showState('state-no-seeds');
    renderSeedChips();
    return;
  }

  const seq = ++S.seq;
  if (!S.hasResult) {
    showState('state-loading');
    el('loading-sub').textContent =
      `seeds ${S.seeds.length} · depth ${S.depth}${S.timeFrom || S.timeTo ? ' · 시간 범위 적용' : ''}`;
  }

  try {
    const body = buildTraceRequest({
      seeds: S.seeds,
      depth: S.depth,
      timeFrom: S.timeFrom,
      timeTo: S.timeTo,
      limit: TRACE_LIMIT,
    });
    const res = await fetch(`${API_BASE}/graph/trace`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const err = await res.json();
        if (err && err.detail) detail = `${detail} — ${typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)}`;
      } catch (e) { /* 본문 없는 오류 응답 */ }
      throw new Error(detail);
    }
    const data = await res.json();
    if (seq !== S.seq) return; // stale 응답 폐기

    S.nodes = Array.isArray(data.nodes) ? data.nodes : [];
    S.edges = Array.isArray(data.edges) ? data.edges : [];
    S.nodesById = new Map(S.nodes.map((n) => [n.id, n]));
    S.seedIds = new Set(Array.isArray(data.seed_ids) ? data.seed_ids : []);
    S.missing = normalizeMissingSeeds(data.missing_seeds);
    S.truncated = !!data.truncated;

    renderSeedChips(); // missing 경고 반영
    syncUrl();

    if (!S.nodes.length) {
      S.hasResult = false;
      showState('state-empty');
      if (S.missing.length) {
        showToast(`시드 ${S.missing.length}개를 그래프에서 찾지 못했습니다`, 'warning');
      }
      return;
    }

    S.hasResult = true;
    renderReport();
    showState('report-view');
  } catch (err) {
    if (seq !== S.seq) return;
    const msg = String(err.message || err);
    if (S.hasResult) {
      // 재실행 실패: 기존 리포트를 잃지 않고 토스트로만 알림 (graph_viewer 선례)
      showToast(`추적 실패: ${msg}`, 'error');
    } else {
      showState('state-error');
      el('error-sub').textContent = msg;
    }
  }
}

// ============================================================
// [2] 시드 칩
// ============================================================
function renderSeedChips() {
  const wrap = el('seed-chips');
  if (!S.seeds.length) {
    wrap.innerHTML = '<span style="font-size:0.74rem;color:var(--text-dim);">시드 없음</span>';
    el('seed-count').textContent = '';
    return;
  }
  wrap.innerHTML = S.seeds.map((s, i) => {
    const missing = isSeedMissing(s, S.missing);
    return `
    <span class="seed-chip${missing ? ' chip-missing' : ''}"
          title="${esc(s.label)}:${esc(s.identity)}${missing ? ' — 그래프에서 찾을 수 없습니다' : ''}">
      ${missing ? '<span class="chip-warn">⚠</span>' : ''}
      <span class="chip-label">${esc(s.label)}</span>
      <span class="chip-id">${esc(s.identity)}</span>
      <button class="chip-remove" data-idx="${i}" title="이 시드 제거" aria-label="시드 제거">✕</button>
    </span>`;
  }).join('');
  el('seed-count').textContent = `${S.seeds.length}/${SEED_CAP}`;

  wrap.querySelectorAll('.chip-remove').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = Number(btn.dataset.idx);
      S.seeds.splice(idx, 1);
      renderSeedChips();
      runTrace(); // 시드 변경 즉시 재추적 (시드 0개면 no-seeds 상태로)
    });
  });
}

// ============================================================
// [3] 리포트 렌더 (메타 + 그룹 + 타임라인)
// ============================================================
function renderReport() {
  const groups = groupNodesByLabel(S.nodes, S.edges, S.seedIds);
  const { timed, structural } = splitTimeline(S.edges);

  // 메타 바
  el('meta-summary').innerHTML =
    `${S.nodes.length.toLocaleString('en-US')} nodes · ${S.edges.length.toLocaleString('en-US')} edges`
    + ` · depth ${S.depth}`
    + ` · <span class="chip-accent">⦿ seed ${S.seedIds.size}</span>`;
  el('truncated-badge').style.display = S.truncated ? 'inline-block' : 'none';
  const missingBadge = el('missing-badge');
  if (S.missing.length) {
    missingBadge.textContent = `⚠ 미발견 시드 ${S.missing.length}개`;
    missingBadge.style.display = 'inline-block';
  } else {
    missingBadge.style.display = 'none';
  }

  renderGroups(groups);
  renderTimeline(timed, structural);
}

// ── 좌: 라벨별 엔티티 그룹 ──────────────────────────────────
function renderGroups(groups) {
  el('groups-meta').textContent = `${groups.length} labels · ${S.nodes.length} entities`;
  const body = el('groups-body');
  body.innerHTML = '';
  for (const g of groups) {
    body.appendChild(buildGroupBlock(g));
  }
}

function buildGroupBlock(group) {
  const block = document.createElement('div');
  block.className = 'group-block';
  block.innerHTML = `
    <div class="group-header">
      <span class="label-dot" style="background: var(${labelToken(group.label)})"></span>
      <span class="group-name">${esc(group.label)}</span>
      <span class="group-count">${group.count}</span>
      ${group.seedCount ? `<span class="group-seed-count">⦿ seed ${group.seedCount}</span>` : ''}
    </div>
    <table class="group-table"><tbody></tbody></table>
  `;
  const tbody = block.querySelector('tbody');

  let rendered = 0;
  const renderChunk = () => {
    const slice = group.rows.slice(rendered, rendered + GROUP_ROW_CHUNK);
    const frag = document.createDocumentFragment();
    for (const r of slice) {
      frag.appendChild(buildGroupRow(r));
    }
    tbody.appendChild(frag);
    rendered += slice.length;
    const oldMore = block.querySelector('.group-more');
    if (oldMore) oldMore.remove();
    if (rendered < group.rows.length) {
      const more = document.createElement('button');
      more.className = 'group-more';
      more.textContent = `▾ ${group.rows.length - rendered}개 더 보기`;
      more.addEventListener('click', renderChunk);
      block.appendChild(more);
    }
  };
  renderChunk();
  return block;
}

function buildGroupRow({ node, degree, isSeed }) {
  const tr = document.createElement('tr');
  tr.className = 'group-row';
  tr.title = `${node.label}:${node.identity_key} — 그래프 뷰어에서 열기`;
  tr.innerHTML = `
    <td class="row-identity">${isSeed ? '<span class="seed-mark" title="시드 노드">⦿</span>' : ''}${esc(node.identity_key)}</td>
    <td class="row-degree" title="이 서브그래프 내 연결 엣지 수">${degree} ⇄</td>
    <td class="row-props" title="${esc(propsSummary(node.props, 8))}">${esc(propsSummary(node.props))}</td>
    <td class="row-open">🕸️ 열기</td>
  `;
  tr.addEventListener('click', () => openInViewer(node.label, node.identity_key));
  return tr;
}

// ── 우: 타임라인 + 구조 관계 ────────────────────────────────
function nodeRefHtml(id) {
  const n = S.nodesById.get(id);
  if (!n) return `<span class="tl-node" style="cursor:default" title="응답에 없는 노드 (limit 절단 가능)">#${esc(id)}</span>`;
  return `<span class="tl-node" data-node-id="${esc(id)}" title="${esc(n.label)}:${esc(n.identity_key)} — 그래프 뷰어에서 열기">`
    + `<span class="tl-node-label">${esc(n.label)}</span>${esc(truncateText(n.identity_key, 26))}</span>`;
}

function provenanceBadgeHtml(edge) {
  const src = edge.source_name === null || edge.source_name === undefined ? '' : String(edge.source_name);
  const by = edge.updated_by ? ` · by ${String(edge.updated_by)}` : '';
  if (src === 'user') {
    // 사람이 검증한 지식 — 최우선 강조 (그리드 overwrite 시맨틱과 동일 토큰)
    return `<span class="tl-badge badge-user" title="사용자 확정 관계${esc(by)}">👤 user</span>`;
  }
  if (!src) return '';
  return `<span class="tl-badge" title="provenance: ${esc(src)}${esc(by)}">${esc(truncateText(src, 16))}</span>`;
}

function buildEdgeItem(edge, timeText) {
  const div = document.createElement('div');
  div.className = `tl-item${edge.source_name === 'user' ? ' tl-user' : ''}`;
  div.innerHTML = `
    ${timeText ? `<span class="tl-time">${esc(timeText)}</span>` : ''}
    <span class="tl-flow">
      ${nodeRefHtml(edge.from)}
      <span class="tl-arrow">→</span>
      <span class="tl-type" title="${esc(edge.type)}">${esc(truncateText(edge.type, 24))}</span>
      <span class="tl-arrow">→</span>
      ${nodeRefHtml(edge.to)}
      ${provenanceBadgeHtml(edge)}
    </span>
  `;
  div.querySelectorAll('.tl-node[data-node-id]').forEach((span) => {
    span.addEventListener('click', () => {
      const n = S.nodesById.get(coerceId(span.dataset.nodeId));
      if (n) openInViewer(n.label, n.identity_key);
    });
  });
  return div;
}

// data-* 문자열 → 원래 id 타입 복원 (응답 id는 int 계약이나 방어적으로 문자열도 수용)
function coerceId(raw) {
  if (S.nodesById.has(raw)) return raw;
  const num = Number(raw);
  return S.nodesById.has(num) ? num : raw;
}

function renderTimeline(timed, structural) {
  el('timeline-meta').textContent =
    `${timed.length} events${structural.length ? ` · 구조 ${structural.length}` : ''}`;

  // 타임라인 (event_time 오름차순, 청크 렌더)
  const list = el('tl-list');
  list.innerHTML = '';
  if (!timed.length) {
    list.innerHTML = '<div class="tl-empty">event_time이 있는 엣지가 없습니다<br>(아래 구조 관계 목록을 확인하세요)</div>';
  } else {
    let rendered = 0;
    const renderChunk = () => {
      const slice = timed.slice(rendered, rendered + TIMELINE_CHUNK);
      const frag = document.createDocumentFragment();
      for (const { edge } of slice) {
        frag.appendChild(buildEdgeItem(edge, fmtEventTime(edge.event_time)));
      }
      const oldMore = list.querySelector('.tl-more');
      if (oldMore) oldMore.remove();
      list.appendChild(frag);
      rendered += slice.length;
      if (rendered < timed.length) {
        const more = document.createElement('button');
        more.className = 'tl-more';
        more.textContent = `▾ 이후 이벤트 ${timed.length - rendered}건 더 보기`;
        more.addEventListener('click', renderChunk);
        list.appendChild(more);
      }
    };
    renderChunk();
  }

  // 구조 관계 접이식 (열 때 1회 지연 렌더 — 초기 DOM 경량 유지)
  const block = el('structural-block');
  const structBody = el('structural-body');
  structBody.innerHTML = '';
  block.open = false;
  if (!structural.length) {
    block.style.display = 'none';
  } else {
    block.style.display = 'block';
    el('struct-count').textContent = `${structural.length}건`;
    let filled = false;
    block.addEventListener('toggle', () => {
      if (!block.open || filled) return;
      filled = true;
      const frag = document.createDocumentFragment();
      for (const edge of structural) {
        frag.appendChild(buildEdgeItem(edge, ''));
      }
      structBody.appendChild(frag);
    });
  }
}

// ============================================================
// [4] 초기화
// ============================================================
function initControls() {
  el('depth-select').addEventListener('change', () => {
    const d = parseInt(el('depth-select').value, 10);
    S.depth = (d >= 1 && d <= 3) ? d : 2;
    runTrace(); // depth는 즉시 재추적 (graph_viewer 선례)
  });

  el('time-from').addEventListener('change', () => { S.timeFrom = el('time-from').value; });
  el('time-to').addEventListener('change', () => { S.timeTo = el('time-to').value; });

  el('time-clear-btn').addEventListener('click', () => {
    el('time-from').value = '';
    el('time-to').value = '';
    S.timeFrom = '';
    S.timeTo = '';
    runTrace();
  });

  el('run-btn').addEventListener('click', runTrace);
  el('retry-btn').addEventListener('click', runTrace);
}

function init() {
  initTheme();
  // [V1 effort instrument] Before any listener can fire. Invisible — no UI, no badge.
  startSession();
  installGlobalListeners();
  installNavLinkCounting(ROUTES.TRACE);
  initControls();

  // URL 파라미터: seeds(필수) + depth/from/to(재방문 복원)
  const qp = new URLSearchParams(window.location.search);
  const { seeds: parsed, invalid } = parseSeedsParam(qp.get('seeds'));
  if (invalid > 0) {
    showToast(`시드 파라미터 ${invalid}건이 형식 오류로 무시되었습니다`, 'warning');
  }
  const { seeds, dropped } = capSeeds(parsed, SEED_CAP);
  if (dropped > 0) {
    showToast(`시드 상한 ${SEED_CAP}개 — 앞 ${SEED_CAP}개만 추적합니다 (${dropped}개 제외)`, 'warning');
  }
  S.seeds = seeds;

  const d = parseInt(qp.get('depth') || '2', 10);
  S.depth = (d >= 1 && d <= 3) ? d : 2;
  el('depth-select').value = String(S.depth);

  const from = qp.get('from') || '';
  const to = qp.get('to') || '';
  if (from) { S.timeFrom = from; el('time-from').value = from; }
  if (to) { S.timeTo = to; el('time-to').value = to; }

  renderSeedChips();
  runTrace();
}

init();
