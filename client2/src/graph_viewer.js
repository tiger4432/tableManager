// ============================================================
// Knowledge Graph Subgraph Viewer (graph.html entry)
// - G1 검증 도구: /graph/stats 카운트 → /graph/neighbors k-hop 서브그래프 캔버스
// - admin/map_editor/enrichment 선례: 자체 모듈 지역 상태 (state.js/dom.js 미임포트)
// - API 계약(확정 — 서버 코드 미참조, 이 계약이 전부):
//   GET /graph/stats
//     → {labels:[{label,count}], edge_types:[{type,count}], last_sync}
//   GET /graph/nodes/search?q=&label=&limit=20 (시작일치) → 노드 목록(방어적 파싱)
//   GET /graph/neighbors?label=&identity=&depth=1|2&limit=200
//     → {nodes:[{id,label,identity_key,props}],
//        edges:[{from,to,type,source_name,updated_by,event_time}], truncated}
// - 렌더 규율(map_editor 교훈): 렌더 경로에서 getComputedStyle/스타일 리드 금지 —
//   테마 색은 1회 캐싱 + 'themechange' 재캐싱. 상시 rAF 루프 없음(이벤트 구동 렌더).
// - 레이아웃: 외부 라이브러리 금지 → BFS 동심원(ring) 수제 레이아웃 (≤200 노드 상정).
// ============================================================
import './tokens.css';
import { API_BASE } from './config.js';
import { showToast } from './utils.js';
import { initTheme } from './theme.js';

const NEIGHBOR_LIMIT = 200;   // 서버 하드캡과 동일 (무제한 로드 금지)
const SEARCH_LIMIT = 20;
const CONN_PAGE = 80;         // Connections 테이블 렌더 상한 단위 ("더 보기" 페이지)
const AC_DEBOUNCE_MS = 200;   // 자동완성 debounce
const MIN_SCALE = 0.12;
const MAX_SCALE = 3;

const el = (id) => document.getElementById(id);

// HTML 이스케이프 — DB 유래 identity/props를 DOM에 넣을 때 필수
const esc = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ── 지역 상태 (싱글턴) ─────────────────────────────────────
const S = {
  stats: null,
  depth: 1,

  // 현재 서브그래프
  nodes: [],
  edges: [],
  drawEdges: [],        // 곡률(다중 엣지 분리) 사전 계산본
  truncated: false,
  center: null,         // {label, identity}
  centerId: null,
  pos: new Map(),       // node.id → {x, y} (월드 좌표)
  nodesById: new Map(),
  selectedId: null,
  hoverId: null,

  // 뷰 변환 (screen = world * scale + t)
  view: { scale: 1, tx: 0, ty: 0, cssW: 0, cssH: 0, dpr: 1 },

  // 우측 Connections 테이블 상태
  conn: null,           // {nodeId, rows, shown, partial, loading, truncated, error}
  connSeq: 0,           // 이웃 재조회 stale 가드
  panelCollapsed: false,

  // 요청 시퀀스 가드 (stale 응답 폐기)
  seq: 0,
  acSeq: 0,
  acTimer: null,
  acItems: [],
  acIndex: -1,

  drag: null,           // {sx, sy, tx0, ty0, moved, node}
  ctx: null,
};

// ── 테마 색 캐시 ────────────────────────────────────────────
// 성능 규율: 렌더 루프에서 getComputedStyle 금지 — 1회 캐싱 후 themechange 시에만 재캐싱.
const PALETTE_TOKENS = ['--accent', '--accent-2', '--success', '--orange', '--info', '--danger', '--warning'];
const CACHED_TOKENS = [
  ...PALETTE_TOKENS,
  '--text', '--text-muted', '--text-dim',
  '--bg-inset', '--bg-surface', '--border', '--border-strong',
  '--overwrite', '--focus-ring',
];
let T = null; // { tok: {tokenName: resolvedColor} }

function rebuildThemeColorCache() {
  const cs = getComputedStyle(document.documentElement);
  const tok = {};
  for (const name of CACHED_TOKENS) {
    tok[name] = (cs.getPropertyValue(name) || '').trim() || '#888888';
  }
  T = { tok };
}

const col = (token) => (T ? T.tok[token] : '#888888');

// 라벨 → 팔레트 토큰 (세션 내 등록 순서 고정 — stats 순서 우선이라 결정적)
const labelPaletteIdx = new Map();

function labelToken(label) {
  if (!labelPaletteIdx.has(label)) {
    labelPaletteIdx.set(label, labelPaletteIdx.size % PALETTE_TOKENS.length);
  }
  return PALETTE_TOKENS[labelPaletteIdx.get(label)];
}

const labelColor = (label) => col(labelToken(label));

// ── 포맷 헬퍼 ───────────────────────────────────────────────
const fmtInt = (n) => Number(n || 0).toLocaleString('en-US');

function fmtSync(v) {
  if (v === null || v === undefined || v === '') return '—';
  const raw = (typeof v === 'object')
    ? (v.time || v.synced_at || v.last_event_time || JSON.stringify(v))
    : v;
  const d = new Date(raw);
  if (!Number.isNaN(d.getTime())) {
    const p = (x) => String(x).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }
  return String(raw);
}

const truncate = (s, n) => {
  const str = String(s);
  return str.length > n ? `${str.slice(0, n - 1)}…` : str;
};

// ============================================================
// [1] Stats 첫 화면
// ============================================================
function setStatsState(state, errMsg) {
  el('stats-loading').style.display = state === 'loading' ? 'flex' : 'none';
  el('stats-error').style.display = state === 'error' ? 'flex' : 'none';
  el('stats-empty').style.display = state === 'empty' ? 'flex' : 'none';
  el('stats-content').style.display = state === 'content' ? 'flex' : 'none';
  if (state === 'error') el('stats-error-sub').textContent = errMsg || '';
}

async function loadStats() {
  setStatsState('loading');
  try {
    const res = await fetch(`${API_BASE}/graph/stats`);
    if (!res.ok) throw new Error(`GET /graph/stats → HTTP ${res.status}`);
    const data = await res.json();
    S.stats = {
      labels: Array.isArray(data.labels) ? data.labels : [],
      edge_types: Array.isArray(data.edge_types) ? data.edge_types : [],
      last_sync: data.last_sync,
    };
    renderStats();
  } catch (err) {
    setStatsState('error', String(err.message || err));
  }
}

function renderStats() {
  const { labels, edge_types, last_sync } = S.stats;
  const totalNodes = labels.reduce((a, x) => a + (Number(x.count) || 0), 0);
  const totalEdges = edge_types.reduce((a, x) => a + (Number(x.count) || 0), 0);

  // 팔레트 등록: stats의 라벨 순서를 세션 기준으로 고정 (캔버스/레전드/카드 색 일치)
  labels.forEach((x) => labelToken(x.label));

  // label 셀렉트 재구성 (선택 유지)
  const sel = el('label-select');
  const kept = sel.value;
  sel.innerHTML = '<option value="">ALL LABELS</option>'
    + labels.map((x) => `<option value="${esc(x.label)}">${esc(x.label)}</option>`).join('');
  if (kept && labels.some((x) => x.label === kept)) sel.value = kept;

  if (totalNodes === 0 && totalEdges === 0) {
    setStatsState('empty');
    return;
  }

  el('hero-nodes').textContent = fmtInt(totalNodes);
  el('hero-nodes-sub').textContent = `${labels.length} labels`;
  el('hero-edges').textContent = fmtInt(totalEdges);
  el('hero-edges-sub').textContent = `${edge_types.length} edge types`;
  el('hero-sync').textContent = fmtSync(last_sync);

  el('label-block-count').textContent = `${labels.length} labels`;
  el('label-cards').innerHTML = labels.map((x) => `
    <div class="label-card" data-label="${esc(x.label)}" role="button" tabindex="0"
         title="이 라벨로 검색 필터 설정">
      <span class="label-dot" style="background: var(${labelToken(x.label)})"></span>
      <span class="label-name">${esc(x.label)}</span>
      <span class="label-count">${fmtInt(x.count)}</span>
    </div>`).join('')
    || '<div class="props-empty">라벨이 없습니다</div>';

  const maxEdge = Math.max(1, ...edge_types.map((x) => Number(x.count) || 0));
  el('edge-block-count').textContent = `${edge_types.length} types`;
  el('edge-rows').innerHTML = edge_types.map((x) => `
    <div class="edge-row">
      <span class="edge-name" title="${esc(x.type)}">${esc(x.type)}</span>
      <span class="edge-bar-track"><span class="edge-bar" style="width: ${Math.max(2, Math.round(((Number(x.count) || 0) / maxEdge) * 100))}%"></span></span>
      <span class="edge-count">${fmtInt(x.count)}</span>
    </div>`).join('')
    || '<div class="props-empty">엣지가 없습니다</div>';

  // 라벨 카드 클릭/키보드 → 검색 필터 설정
  el('label-cards').querySelectorAll('.label-card').forEach((card) => {
    const pick = () => {
      el('label-select').value = card.dataset.label;
      el('identity-input').focus();
    };
    card.addEventListener('click', pick);
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); }
    });
  });

  setStatsState('content');
}

// ── 뷰 전환 ────────────────────────────────────────────────
function showStatsView() {
  el('graph-view').style.display = 'none';
  el('stats-view').style.display = 'block';
  el('back-to-graph-btn').style.display = S.nodes.length ? 'inline-flex' : 'none';
}

function showGraphView() {
  el('stats-view').style.display = 'none';
  el('graph-view').style.display = 'flex';
  updateCanvasSize();
}

// ============================================================
// [2] 서브그래프 조회 + 동심원 레이아웃
// ============================================================
function setCanvasOverlay(state, text, sub) {
  const overlay = el('canvas-overlay');
  if (state === 'hide') { overlay.style.display = 'none'; return; }
  overlay.style.display = 'flex';
  el('canvas-overlay-spinner').style.display = state === 'loading' ? 'block' : 'none';
  el('canvas-overlay-icon').style.display = state === 'loading' ? 'none' : 'block';
  el('canvas-overlay-icon').textContent = state === 'error' ? '🚧' : '🕳️';
  el('canvas-overlay-text').textContent = text || '';
  el('canvas-overlay-sub').textContent = sub || '';
}

// ── URL 동기화: ?label=&identity= (trace.html 크로스링크와 동일 관례) ──
// 검색/시드 이동마다 push → 브라우저 뒤로가기가 이전 중심으로 자연 복귀.
function syncUrl(label, identity, mode) {
  if (mode === 'none') return;
  const next = `${window.location.pathname}?label=${encodeURIComponent(label)}&identity=${encodeURIComponent(identity)}`;
  if (window.location.pathname + window.location.search === next) return; // 동일 중심 재조회 → 히스토리 오염 방지
  try {
    if (mode === 'replace') window.history.replaceState({ label, identity }, '', next);
    else window.history.pushState({ label, identity }, '', next);
  } catch (e) { /* pushState 불가 환경(file:// 등) 방어 — URL 동기화만 포기 */ }
}

// opts.history: 'push'(기본) | 'replace'(초기 쿼리 파라미터 진입) | 'none'(popstate 복원)
async function explore(label, identity, opts = {}) {
  const seq = ++S.seq;
  showGraphView();
  setCanvasOverlay('loading', `${label}:${identity} 이웃 조회 중... (depth ${S.depth})`);
  try {
    const params = new URLSearchParams({
      label, identity, depth: String(S.depth), limit: String(NEIGHBOR_LIMIT),
    });
    const res = await fetch(`${API_BASE}/graph/neighbors?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (seq !== S.seq) return; // stale 응답 폐기

    const nodes = Array.isArray(data.nodes) ? data.nodes : [];
    if (!nodes.length) {
      setCanvasOverlay('empty', '노드를 찾을 수 없습니다', `${label}:${identity}`);
      return;
    }

    S.nodes = nodes;
    S.edges = Array.isArray(data.edges) ? data.edges : [];
    S.truncated = !!data.truncated;
    S.nodesById = new Map(nodes.map((n) => [n.id, n]));

    const center = nodes.find((n) => n.label === label && n.identity_key === identity) || nodes[0];
    S.centerId = center.id;
    S.center = { label: center.label, identity: center.identity_key };
    S.selectedId = center.id;
    S.hoverId = null;

    // 검색바를 현 중심과 동기화 (depth 전환·재탐색 시 일관 — 라벨 미존재 옵션이면 ALL 폴백)
    el('identity-input').value = center.identity_key;
    el('label-select').value = center.label;
    if (el('label-select').value !== center.label) el('label-select').value = '';

    prepareEdges();
    layoutGraph();
    updateCanvasSize();
    fitView();
    setCanvasOverlay('hide');
    renderCanvas();
    renderGraphMeta();
    renderLegend();
    syncUrl(center.label, center.identity_key, opts.history || 'push');
    selectNode(center, { expand: false }); // 중심 노드 선택 + Connections 테이블 (center는 로컬 데이터 완결)
  } catch (err) {
    if (seq !== S.seq) return;
    const msg = String(err.message || err);
    if (S.nodes.length) {
      // 기존 그래프 유지 + 토스트 (탐색 이동 실패 시 화면을 잃지 않음)
      setCanvasOverlay('hide');
      showToast(`이웃 조회 실패: ${msg}`, 'error');
    } else {
      setCanvasOverlay('error', '이웃 조회에 실패했습니다', msg);
    }
  }
}

// 다중 엣지(같은 노드쌍, 다른 타입) 곡률 분리 사전 계산
function prepareEdges() {
  S.drawEdges = S.edges.map((e) => ({ ...e, curve: 0, self: e.from === e.to }));
  const groups = new Map();
  for (const e of S.drawEdges) {
    if (e.self) continue;
    const key = e.from < e.to ? `${e.from}|${e.to}` : `${e.to}|${e.from}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(e);
  }
  for (const g of groups.values()) {
    g.forEach((e, i) => {
      let off = Math.ceil(i / 2) * 26 * (i % 2 === 1 ? 1 : -1); // 0, +26, -26, +52...
      if (e.from > e.to) off = -off; // 방향 무관 일관 곡률
      e.curve = off;
    });
  }
}

// BFS 동심원 레이아웃: 중심 0, k-hop → 반지름 k 링. 부모 각도 순 정렬로 교차 완화.
function layoutGraph() {
  S.pos.clear();
  const adj = new Map();
  const addAdj = (a, b) => {
    if (!adj.has(a)) adj.set(a, new Set());
    adj.get(a).add(b);
  };
  for (const e of S.edges) {
    if (e.from === e.to) continue;
    addAdj(e.from, e.to);
    addAdj(e.to, e.from);
  }

  const depthOf = new Map([[S.centerId, 0]]);
  const parentOf = new Map();
  const queue = [S.centerId];
  while (queue.length) {
    const cur = queue.shift();
    for (const nb of (adj.get(cur) || [])) {
      if (depthOf.has(nb)) continue;
      depthOf.set(nb, depthOf.get(cur) + 1);
      parentOf.set(nb, cur);
      queue.push(nb);
    }
  }

  // 링 구성 (BFS 미도달 노드는 최외곽 링 — 방어)
  let maxDepth = 0;
  for (const d of depthOf.values()) maxDepth = Math.max(maxDepth, d);
  const rings = [];
  for (const n of S.nodes) {
    const d = depthOf.has(n.id) ? depthOf.get(n.id) : maxDepth + 1;
    if (!rings[d]) rings[d] = [];
    rings[d].push(n);
  }

  const angleOf = new Map([[S.centerId, -Math.PI / 2]]);
  S.pos.set(S.centerId, { x: 0, y: 0 });

  let prevRadius = 0;
  for (let k = 1; k < rings.length; k++) {
    const ring = rings[k] || [];
    if (!ring.length) continue;
    // 반지름: 링 간 최소 간격 + 노드 수에 따른 원주 확보 (최소 호 길이 72)
    const radius = Math.max(prevRadius + 130, (ring.length * 72) / (2 * Math.PI));
    prevRadius = radius;
    // 부모 각도 → 라벨 → identity 순 정렬 (부모 근처 배치 근사)
    ring.sort((a, b) => {
      const pa = angleOf.get(parentOf.get(a.id));
      const pb = angleOf.get(parentOf.get(b.id));
      const aa = pa === undefined ? Math.PI : pa;
      const ab = pb === undefined ? Math.PI : pb;
      if (aa !== ab) return aa - ab;
      if (a.label !== b.label) return a.label < b.label ? -1 : 1;
      return String(a.identity_key) < String(b.identity_key) ? -1 : 1;
    });
    const step = (2 * Math.PI) / ring.length;
    // 첫 노드를 그 부모 각도에 정렬해 링 전체를 회전 (그룹-부모 방위 일치)
    const baseAngle = angleOf.get(parentOf.get(ring[0].id));
    const start = (baseAngle === undefined ? -Math.PI / 2 : baseAngle);
    ring.forEach((n, i) => {
      const a = start + i * step;
      angleOf.set(n.id, a);
      S.pos.set(n.id, { x: radius * Math.cos(a), y: radius * Math.sin(a) });
    });
  }
}

// 현재 레이아웃을 캔버스에 맞춤 (여백 포함, 과확대 방지)
function fitView() {
  const { cssW, cssH } = S.view;
  if (!cssW || !cssH || !S.pos.size) return;
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  for (const p of S.pos.values()) {
    minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
  }
  const pad = 90; // 노드 반경 + identity 라벨 여유
  const bw = (maxX - minX) + pad * 2;
  const bh = (maxY - minY) + pad * 2;
  const scale = Math.min(Math.max(Math.min(cssW / bw, cssH / bh), MIN_SCALE), 1.3);
  S.view.scale = scale;
  S.view.tx = cssW / 2 - ((minX + maxX) / 2) * scale;
  S.view.ty = cssH / 2 - ((minY + maxY) / 2) * scale;
}

// ============================================================
// [3] 캔버스 렌더 (이벤트 구동 — 상시 루프 없음)
// ============================================================
function updateCanvasSize() {
  const wrap = el('canvas-wrap');
  const canvas = el('graph-canvas');
  if (!wrap || !canvas) return;
  const cssW = wrap.clientWidth;
  const cssH = wrap.clientHeight;
  if (!cssW || !cssH) return;
  const dpr = window.devicePixelRatio || 1;
  if (S.view.cssW === cssW && S.view.cssH === cssH && S.view.dpr === dpr) return;
  S.view.cssW = cssW;
  S.view.cssH = cssH;
  S.view.dpr = dpr;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
}

function renderCanvas() {
  const ctx = S.ctx;
  if (!ctx || !S.view.cssW) return;
  const { cssW, cssH, dpr, scale, tx, ty } = S.view;

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  ctx.translate(tx, ty);
  ctx.scale(scale, scale);

  drawEdgesPass(ctx, scale);
  drawNodesPass(ctx, scale);
}

function drawEdgesPass(ctx, scale) {
  const showLabels = scale >= 0.55;
  ctx.lineJoin = 'round';
  for (const e of S.drawEdges) {
    const p1 = S.pos.get(e.from);
    const p2 = S.pos.get(e.to);
    if (!p1 || !p2) continue;
    const isUser = e.source_name === 'user'; // provenance 강조 (사용자 확정 지식)
    const color = isUser ? col('--overwrite') : col('--border-strong');
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = isUser ? 2.4 : 1.2;

    if (e.self) {
      // 셀프 루프: 노드 위 소원
      ctx.beginPath();
      ctx.arc(p1.x, p1.y - 16, 9, 0, 2 * Math.PI);
      ctx.stroke();
      continue;
    }

    const mx = (p1.x + p2.x) / 2;
    const my = (p1.y + p2.y) / 2;
    const dx = p2.x - p1.x;
    const dy = p2.y - p1.y;
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;
    const cx = mx + nx * e.curve;
    const cy = my + ny * e.curve;

    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.quadraticCurveTo(cx, cy, p2.x, p2.y);
    ctx.stroke();

    // 화살촉 (방향: control → target, 노드 테두리 앞에서 멈춤)
    const tr = (e.to === S.centerId ? 11 : 7) + 3;
    const adx = p2.x - cx;
    const ady = p2.y - cy;
    const alen = Math.hypot(adx, ady) || 1;
    const tipX = p2.x - (adx / alen) * tr;
    const tipY = p2.y - (ady / alen) * tr;
    const ang = Math.atan2(ady, adx);
    const asz = isUser ? 8 : 6.5;
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX - asz * Math.cos(ang - 0.42), tipY - asz * Math.sin(ang - 0.42));
    ctx.lineTo(tipX - asz * Math.cos(ang + 0.42), tipY - asz * Math.sin(ang + 0.42));
    ctx.closePath();
    ctx.fill();

    // 타입 라벨 (곡선 중점 t=0.5) — 축소 상태에선 노이즈라 생략
    if (showLabels) {
      const qx = 0.25 * p1.x + 0.5 * cx + 0.25 * p2.x;
      const qy = 0.25 * p1.y + 0.5 * cy + 0.25 * p2.y;
      ctx.font = '10px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.lineWidth = 3;
      ctx.strokeStyle = col('--bg-inset'); // 텍스트 할로 (배경색)
      const text = truncate(e.type, 22);
      ctx.strokeText(text, qx, qy - 6);
      ctx.fillStyle = isUser ? col('--overwrite') : col('--text-dim');
      ctx.fillText(text, qx, qy - 6);
    }
  }
}

function drawNodesPass(ctx, scale) {
  const showAllIds = scale >= 0.5;
  ctx.font = '11px "JetBrains Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  for (const n of S.nodes) {
    const p = S.pos.get(n.id);
    if (!p) continue;
    const isCenter = n.id === S.centerId;
    const isSelected = n.id === S.selectedId;
    const isHover = n.id === S.hoverId;
    const r = isCenter ? 11 : 7;
    const color = labelColor(n.label);

    // 선택/호버 할로 링
    if (isSelected || isHover) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 5, 0, 2 * Math.PI);
      ctx.strokeStyle = isSelected ? col('--accent') : col('--border-strong');
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // 중심 노드: 라벨색 외곽 링 (자기 궤도 표시)
    if (isCenter) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 9, 0, 2 * Math.PI);
      ctx.strokeStyle = color;
      ctx.globalAlpha = 0.35;
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = col('--bg-surface');
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // identity 라벨 — 축소 상태에선 중심/선택/호버만 (시각 노이즈 억제)
    if (showAllIds || isCenter || isSelected || isHover) {
      const text = truncate(n.identity_key, 20);
      const y = p.y + r + 6;
      ctx.lineWidth = 3;
      ctx.strokeStyle = col('--bg-inset');
      ctx.strokeText(text, p.x, y);
      ctx.fillStyle = (isCenter || isSelected) ? col('--text') : col('--text-muted');
      ctx.fillText(text, p.x, y);
    }
  }
}

// ── 오버레이 DOM (메타/레전드) — 데이터 로드 시에만 갱신 ──
function renderGraphMeta() {
  const chip = el('graph-meta-chip');
  chip.innerHTML = `${fmtInt(S.nodes.length)} nodes · ${fmtInt(S.edges.length)} edges · depth ${S.depth}`
    + ` · <span class="chip-accent">⦿ ${esc(S.center.label)}:${esc(truncate(S.center.identity, 28))}</span>`;
  el('truncated-badge').style.display = S.truncated ? 'inline-block' : 'none';
}

function renderLegend() {
  const counts = new Map();
  for (const n of S.nodes) counts.set(n.label, (counts.get(n.label) || 0) + 1);
  const hasUserEdge = S.edges.some((e) => e.source_name === 'user');
  const rows = [...counts.entries()].map(([label, c]) => `
    <div class="legend-row">
      <span class="label-dot" style="background: var(${labelToken(label)})"></span>
      <span>${esc(label)}</span><span style="opacity:.6">${fmtInt(c)}</span>
    </div>`);
  if (hasUserEdge) {
    rows.push('<div class="legend-row"><span class="legend-user"></span><span>user provenance</span></div>');
  }
  const legend = el('graph-legend');
  legend.innerHTML = rows.join('');
  legend.style.display = rows.length ? 'flex' : 'none';
}

// ============================================================
// [4] Node Inspector (우측 패널) — 선택 노드 정보 + Connections 테이블
// ============================================================

// 서브그래프(또는 재조회 응답)에서 특정 노드의 연결 행 추출
// 행 = {dir: 'in'|'out'|'self', type, other(노드), edge}
function connectionRows(nodeId, edges, nodesById) {
  const rows = [];
  for (const e of edges) {
    const isOut = e.from === nodeId;
    const isIn = e.to === nodeId;
    if (!isOut && !isIn) continue;
    if (e.from === e.to) {
      const self = nodesById.get(nodeId);
      if (self) rows.push({ dir: 'self', type: e.type, other: self, edge: e });
      continue;
    }
    const other = nodesById.get(isOut ? e.to : e.from);
    if (!other) continue; // truncated 응답 방어 (끝점 노드 미포함 엣지)
    rows.push({ dir: isOut ? 'out' : 'in', type: e.type, other, edge: e });
  }
  rows.sort((a, b) => {
    if (a.type !== b.type) return a.type < b.type ? -1 : 1;
    if (a.other.label !== b.other.label) return a.other.label < b.other.label ? -1 : 1;
    return String(a.other.identity_key).localeCompare(String(b.other.identity_key));
  });
  return rows;
}

// 대표 props 요약: 앞쪽 2개 key=value (테이블 한 줄용, esc는 호출부에서)
function propsSummary(props) {
  if (!props || typeof props !== 'object') return '';
  const parts = [];
  for (const [k, v] of Object.entries(props)) {
    if (v === null || v === undefined || v === '') continue;
    const val = typeof v === 'object' ? JSON.stringify(v) : String(v);
    parts.push(`${k}=${truncate(val, 16)}`);
    if (parts.length >= 2) break;
  }
  return truncate(parts.join(' '), 52);
}

// 노드 선택 = 패널 갱신 + Connections 구성. 비중심 노드는 로컬 단면을 먼저
// 보여주고 depth-1 재조회(label+identity — node_id 아님)로 전체 이웃을 보강.
function selectNode(node, opts = {}) {
  S.selectedId = node.id;
  if (opts.expand !== false && S.panelCollapsed) setPanelCollapsed(false);

  const isCenter = node.id === S.centerId;
  S.connSeq++; // 이전 노드의 in-flight 재조회 무효화
  S.conn = {
    nodeId: node.id,
    rows: connectionRows(node.id, S.edges, S.nodesById),
    shown: CONN_PAGE,
    partial: !isCenter,   // 비중심: 로드된 서브그래프의 단면일 수 있음
    loading: !isCenter,
    truncated: isCenter ? S.truncated : false,
    error: null,
  };
  renderNodePanel(node);
  renderCanvas();
  if (!isCenter) fetchNodeConnections(node);
}

// 비중심 노드의 전체 1-hop 이웃 재조회 → Connections 테이블 보강
async function fetchNodeConnections(node) {
  const seq = ++S.connSeq;
  try {
    const params = new URLSearchParams({
      label: node.label, identity: node.identity_key, depth: '1', limit: String(NEIGHBOR_LIMIT),
    });
    const res = await fetch(`${API_BASE}/graph/neighbors?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (seq !== S.connSeq || !S.conn || S.conn.nodeId !== node.id) return; // stale 폐기
    const nodes = Array.isArray(data.nodes) ? data.nodes : [];
    const edges = Array.isArray(data.edges) ? data.edges : [];
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const self = nodes.find((n) => n.label === node.label && n.identity_key === node.identity_key);
    if (self) {
      S.conn.rows = connectionRows(self.id, edges, byId);
      S.conn.partial = false;
      S.conn.truncated = !!data.truncated;
    }
    S.conn.loading = false;
    renderConnBlock();
  } catch (err) {
    if (seq !== S.connSeq || !S.conn || S.conn.nodeId !== node.id) return;
    S.conn.loading = false;
    S.conn.error = String(err.message || err); // 로컬 단면은 유지 — 실패해도 화면을 잃지 않음
    renderConnBlock();
  }
}

// Connections 블록만 부분 재렌더 (재조회 완료/더 보기)
function renderConnBlock() {
  const block = el('conn-block');
  if (!block || !S.conn) return;
  const c = S.conn;
  const total = c.rows.length;
  const shown = Math.min(c.shown, total);

  let badge = '';
  if (c.loading) badge = '<span class="conn-badge">전체 이웃 조회 중…</span>';
  else if (c.error) badge = '<span class="conn-badge conn-warn" title="전체 이웃 조회 실패 — 서브그래프 단면 표시 중">단면 · 조회 실패</span>';
  else if (c.partial) badge = '<span class="conn-badge">서브그래프 단면</span>';
  else if (c.truncated) badge = `<span class="conn-badge conn-warn">LIMIT ${NEIGHBOR_LIMIT}</span>`;

  const header = `<div class="detail-block-header conn-header"><span>Connections · ${fmtInt(total)}</span>${badge}</div>`;

  let body;
  if (!total) {
    body = c.loading
      ? '<div class="props-empty">연결 조회 중…</div>'
      : `<div class="props-empty">${c.error ? `연결 조회 실패: ${esc(c.error)}` : '연결된 노드가 없습니다'}</div>`;
  } else {
    const rowsHtml = c.rows.slice(0, shown).map((r) => {
      const o = r.other;
      const dir = r.dir === 'out'
        ? '<span class="conn-dir out" title="outgoing">→</span>'
        : r.dir === 'in'
          ? '<span class="conn-dir in" title="incoming">←</span>'
          : '<span class="conn-dir" title="self-loop">⟲</span>';
      const time = r.edge.event_time ? fmtSync(r.edge.event_time) : '';
      const summary = propsSummary(o.props);
      const sub = [esc(o.label), summary ? esc(summary) : '', time ? esc(time) : '']
        .filter(Boolean).join(' · ');
      const isUser = r.edge.source_name === 'user';
      return `<tr class="conn-row${isUser ? ' conn-user' : ''}" tabindex="0" role="button"
           data-label="${esc(o.label)}" data-identity="${esc(o.identity_key)}"
           title="클릭 → 이 노드를 새 검색 시드로 재조회">
        <td class="conn-rel">${dir}<span class="conn-type">${esc(truncate(r.type, 18))}</span></td>
        <td class="conn-node">
          <span class="conn-id"><span class="label-dot" style="background: var(${labelToken(o.label)})"></span>${esc(o.identity_key)}</span>
          <span class="conn-sub">${sub}</span>
        </td>
      </tr>`;
    }).join('');
    body = `<div class="conn-scroll"><table class="conn-table"><tbody>${rowsHtml}</tbody></table></div>`;
    if (shown < total) {
      body += `<button type="button" class="conn-more" id="conn-more-btn">더 보기 (남은 ${fmtInt(total - shown)})</button>`;
    }
  }

  block.innerHTML = header + body;

  // 행 클릭/Enter → 검색 시드 연동 (explore = 서브그래프 재로드 + URL push + 검색바 반영)
  block.querySelectorAll('.conn-row').forEach((tr) => {
    const go = () => explore(tr.dataset.label, tr.dataset.identity);
    tr.addEventListener('click', go);
    tr.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); }
    });
  });
  const more = el('conn-more-btn');
  if (more) {
    more.addEventListener('click', () => {
      S.conn.shown += CONN_PAGE;
      renderConnBlock();
    });
  }
}

function renderNodePanel(node) {
  const empty = el('node-empty');
  const detail = el('node-detail');
  if (!node) {
    empty.style.display = 'flex';
    detail.style.display = 'none';
    el('node-panel-meta').textContent = '';
    return;
  }
  empty.style.display = 'none';
  detail.style.display = 'flex';
  el('node-panel-meta').textContent = `id ${node.id}`;

  const isCenter = node.id === S.centerId;
  const inDeg = S.edges.filter((e) => e.to === node.id).length;
  const outDeg = S.edges.filter((e) => e.from === node.id).length;

  const props = (node.props && typeof node.props === 'object') ? node.props : {};
  const propKeys = Object.keys(props);
  const propRows = propKeys.map((k) => {
    const v = props[k];
    let out;
    let cls = 'prop-val';
    if (v === null || v === undefined) { out = '∅'; cls += ' prop-null'; }
    else if (typeof v === 'object') out = esc(JSON.stringify(v));
    else out = esc(v);
    return `<tr><td class="prop-key">${esc(k)}</td><td class="${cls}">${out}</td></tr>`;
  }).join('');

  detail.innerHTML = `
    <div class="node-id-block">
      <div class="node-chips">
        <span class="node-label-chip">
          <span class="label-dot" style="background: var(${labelToken(node.label)})"></span>${esc(node.label)}
        </span>
        ${isCenter ? '<span class="center-chip">⦿ CENTER</span>' : ''}
      </div>
      <div class="node-identity">${esc(node.identity_key)}</div>
    </div>

    ${isCenter ? '' : '<button type="button" id="node-seed-btn" class="glass-btn node-seed-btn" title="이 노드를 새 검색 시드로 재조회">🔍 이 노드 중심으로 탐색</button>'}

    <div class="detail-block">
      <div class="detail-block-header">Props</div>
      ${propKeys.length
        ? `<table class="props-table">${propRows}</table>`
        : '<div class="props-empty">props 없음</div>'}
    </div>

    <div class="detail-block" id="conn-block"></div>

    <div class="detail-block">
      <div class="detail-block-header">Subgraph Degree</div>
      <table class="props-table">
        <tr><td class="prop-key">in</td><td class="prop-val">${fmtInt(inDeg)}</td></tr>
        <tr><td class="prop-key">out</td><td class="prop-val">${fmtInt(outDeg)}</td></tr>
      </table>
    </div>

    <div class="node-hint">연결 행 클릭 = 그 노드로 재검색 · 캔버스 더블클릭 = 중심 이동</div>
  `;

  const seedBtn = el('node-seed-btn');
  if (seedBtn) seedBtn.addEventListener('click', () => explore(node.label, node.identity_key));

  renderConnBlock();
}

// ── 패널 접기/펼치기 (캔버스 잠식 방지 — ResizeObserver가 캔버스 재조정) ──
function setPanelCollapsed(v) {
  S.panelCollapsed = v;
  el('node-panel').classList.toggle('collapsed', v);
  const btn = el('panel-collapse-btn');
  btn.textContent = v ? '«' : '»';
  btn.title = v ? '패널 펼치기' : '패널 접기';
  btn.setAttribute('aria-expanded', v ? 'false' : 'true');
}

// ============================================================
// [5] 캔버스 인터랙션 (팬/줌/클릭/호버)
// ============================================================
function nodeAtScreen(mx, my) {
  const { scale, tx, ty } = S.view;
  let best = null;
  let bestD = Infinity;
  for (const n of S.nodes) {
    const p = S.pos.get(n.id);
    if (!p) continue;
    const sx = p.x * scale + tx;
    const sy = p.y * scale + ty;
    const r = Math.max((n.id === S.centerId ? 11 : 7) * scale + 6, 11);
    const d = Math.hypot(mx - sx, my - sy);
    if (d <= r && d < bestD) { best = n; bestD = d; }
  }
  return best;
}

// 클릭 = 선택 + 우측 Connections 테이블 (즉시 재조회하지 않음 — 캔버스 맥락 유지)
// 중심 이동은 더블클릭 / 패널 "이 노드 중심으로 탐색" 버튼 / 테이블 행 클릭.
function onNodeClick(node) {
  selectNode(node, { expand: true });
}

function initCanvasEvents() {
  const canvas = el('graph-canvas');

  canvas.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    S.drag = {
      sx: e.clientX,
      sy: e.clientY,
      tx0: S.view.tx,
      ty0: S.view.ty,
      moved: false,
      node: nodeAtScreen(e.offsetX, e.offsetY),
    };
    canvas.classList.add('dragging');
  });

  window.addEventListener('mousemove', (e) => {
    if (!S.drag) return;
    const dx = e.clientX - S.drag.sx;
    const dy = e.clientY - S.drag.sy;
    if (!S.drag.moved && Math.hypot(dx, dy) < 4) return;
    S.drag.moved = true;
    S.view.tx = S.drag.tx0 + dx;
    S.view.ty = S.drag.ty0 + dy;
    renderCanvas();
  });

  window.addEventListener('mouseup', () => {
    if (!S.drag) return;
    const { moved, node } = S.drag;
    S.drag = null;
    canvas.classList.remove('dragging');
    if (!moved && node) onNodeClick(node);
  });

  canvas.addEventListener('mousemove', (e) => {
    if (S.drag) return;
    const hit = nodeAtScreen(e.offsetX, e.offsetY);
    const hitId = hit ? hit.id : null;
    canvas.classList.toggle('on-node', !!hit);
    if (hitId !== S.hoverId) {
      S.hoverId = hitId;
      renderCanvas();
    }
  });

  // 더블클릭 = 그 노드 중심으로 재조회 (기존 단일클릭 재조회의 대체 경로)
  canvas.addEventListener('dblclick', (e) => {
    const hit = nodeAtScreen(e.offsetX, e.offsetY);
    if (hit && hit.id !== S.centerId) explore(hit.label, hit.identity_key);
  });

  canvas.addEventListener('mouseleave', () => {
    if (S.hoverId !== null) {
      S.hoverId = null;
      renderCanvas();
    }
  });

  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const next = Math.min(Math.max(S.view.scale * factor, MIN_SCALE), MAX_SCALE);
    const k = next / S.view.scale;
    // 커서 기준 줌
    S.view.tx = e.offsetX - (e.offsetX - S.view.tx) * k;
    S.view.ty = e.offsetY - (e.offsetY - S.view.ty) * k;
    S.view.scale = next;
    renderCanvas();
  }, { passive: false });

  // 리사이즈 → backing store 재설정 + 재렌더 (이벤트 구동, 상시 루프 없음)
  const ro = new ResizeObserver(() => {
    if (el('graph-view').style.display === 'none') return;
    updateCanvasSize();
    renderCanvas();
  });
  ro.observe(el('canvas-wrap'));
}

// ============================================================
// [6] 검색바: label 셀렉트 + identity 자동완성 + depth 토글
// ============================================================
async function searchNodes(q, label) {
  const params = new URLSearchParams({ q, limit: String(SEARCH_LIMIT) });
  if (label) params.set('label', label);
  const res = await fetch(`${API_BASE}/graph/nodes/search?${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  const items = Array.isArray(data) ? data : (data.nodes || data.results || data.items || []);
  return items.filter((x) => x && x.identity_key !== undefined);
}

function hideAcList() {
  el('ac-list').style.display = 'none';
  el('identity-input').setAttribute('aria-expanded', 'false');
  S.acItems = [];
  S.acIndex = -1;
}

function renderAcList(items) {
  const list = el('ac-list');
  S.acItems = items;
  S.acIndex = -1;
  if (!items.length) {
    list.innerHTML = '<div class="ac-empty">일치하는 노드가 없습니다</div>';
  } else {
    list.innerHTML = items.map((x, i) => `
      <div class="ac-item" role="option" aria-selected="false" data-idx="${i}">
        <span class="ac-dot" style="background: var(${labelToken(x.label)})"></span>
        <span class="ac-id">${esc(x.identity_key)}</span>
        <span class="ac-label">${esc(x.label || '')}</span>
      </div>`).join('');
    list.querySelectorAll('.ac-item').forEach((item) => {
      item.addEventListener('mousedown', (e) => {
        e.preventDefault(); // input blur 방지
        chooseAcItem(Number(item.dataset.idx));
      });
    });
  }
  list.style.display = 'block';
  el('identity-input').setAttribute('aria-expanded', 'true');
}

function setAcActive(idx) {
  const list = el('ac-list');
  S.acIndex = idx;
  list.querySelectorAll('.ac-item').forEach((item, i) => {
    item.classList.toggle('active', i === idx);
    item.setAttribute('aria-selected', i === idx ? 'true' : 'false');
    if (i === idx) item.scrollIntoView({ block: 'nearest' });
  });
}

function chooseAcItem(idx) {
  const item = S.acItems[idx];
  if (!item) return;
  el('identity-input').value = item.identity_key;
  if (item.label) el('label-select').value = item.label;
  hideAcList();
  explore(item.label, item.identity_key);
}

function onIdentityInput() {
  const q = el('identity-input').value.trim();
  if (S.acTimer) clearTimeout(S.acTimer);
  if (!q) { hideAcList(); return; }
  S.acTimer = setTimeout(async () => {
    const seq = ++S.acSeq;
    try {
      const items = await searchNodes(q, el('label-select').value);
      if (seq !== S.acSeq) return; // stale 폐기
      if (document.activeElement !== el('identity-input')) return;
      renderAcList(items);
    } catch (err) {
      if (seq !== S.acSeq) return;
      hideAcList();
    }
  }, AC_DEBOUNCE_MS);
}

// 탐색 버튼/Enter: 제안 미선택 시 검색으로 label 확정 후 조회
async function exploreFromInput() {
  const q = el('identity-input').value.trim();
  if (!q) {
    showToast('identity를 입력하세요', 'warning');
    el('identity-input').focus();
    return;
  }
  hideAcList();
  try {
    const items = await searchNodes(q, el('label-select').value);
    const hit = items.find((x) => x.identity_key === q) || items[0];
    if (!hit) {
      showToast(`'${q}' 와 일치하는 노드가 없습니다`, 'warning');
      return;
    }
    explore(hit.label, hit.identity_key);
  } catch (err) {
    showToast(`노드 검색 실패: ${String(err.message || err)}`, 'error');
  }
}

function setDepth(d) {
  if (S.depth === d) return;
  S.depth = d;
  el('depth-1').classList.toggle('active', d === 1);
  el('depth-2').classList.toggle('active', d === 2);
  el('depth-1').setAttribute('aria-pressed', d === 1 ? 'true' : 'false');
  el('depth-2').setAttribute('aria-pressed', d === 2 ? 'true' : 'false');
  // 중심이 있으면 새 깊이로 즉시 재조회
  if (S.center) explore(S.center.label, S.center.identity);
}

function initSearchBar() {
  const input = el('identity-input');
  input.addEventListener('input', onIdentityInput);
  input.addEventListener('keydown', (e) => {
    const open = el('ac-list').style.display !== 'none';
    if (e.key === 'ArrowDown' && open && S.acItems.length) {
      e.preventDefault();
      setAcActive((S.acIndex + 1) % S.acItems.length);
    } else if (e.key === 'ArrowUp' && open && S.acItems.length) {
      e.preventDefault();
      setAcActive((S.acIndex - 1 + S.acItems.length) % S.acItems.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (open && S.acIndex >= 0) chooseAcItem(S.acIndex);
      else exploreFromInput();
    } else if (e.key === 'Escape') {
      hideAcList();
    }
  });
  input.addEventListener('blur', () => {
    // mousedown(선택)이 먼저 처리되도록 지연 클로즈
    setTimeout(hideAcList, 120);
  });

  el('label-select').addEventListener('change', () => {
    if (input.value.trim()) onIdentityInput();
  });

  el('explore-btn').addEventListener('click', exploreFromInput);
  el('depth-1').addEventListener('click', () => setDepth(1));
  el('depth-2').addEventListener('click', () => setDepth(2));
}

// ============================================================
// 초기화
// ============================================================
function init() {
  initTheme();
  rebuildThemeColorCache();
  // 테마 전환: 색 캐시 재빌드 + 캔버스 1회 재렌더 (DOM 오버레이는 CSS var라 자동 추종)
  document.addEventListener('themechange', () => {
    rebuildThemeColorCache();
    renderCanvas();
  });

  S.ctx = el('graph-canvas').getContext('2d');
  initCanvasEvents();
  initSearchBar();

  el('stats-btn').addEventListener('click', () => {
    showStatsView();
    loadStats(); // 라이브 검증용 — 돌아올 때마다 신선한 카운트
  });
  el('back-to-graph-btn').addEventListener('click', showGraphView);
  el('panel-collapse-btn').addEventListener('click', () => setPanelCollapsed(!S.panelCollapsed));
  el('stats-retry-btn').addEventListener('click', loadStats);
  el('stats-empty-retry-btn').addEventListener('click', loadStats);
  el('stats-refresh-btn').addEventListener('click', loadStats);

  loadStats();

  // 쿼리 파라미터 초기 중심 (trace.html 크로스링크 계약): ?label=&identity=
  // stats 로드는 그대로 병행 — renderStats는 기존 select 값을 보존하므로 경쟁 무해.
  const qp = new URLSearchParams(window.location.search);
  const qpLabel = (qp.get('label') || '').trim();
  const qpIdentity = (qp.get('identity') || '').trim();
  if (qpLabel && qpIdentity) explore(qpLabel, qpIdentity, { history: 'replace' });

  // 뒤로가기/앞으로가기 → URL의 중심으로 복원 (push 없이 재조회)
  window.addEventListener('popstate', () => {
    const p = new URLSearchParams(window.location.search);
    const l = (p.get('label') || '').trim();
    const i = (p.get('identity') || '').trim();
    if (l && i) {
      explore(l, i, { history: 'none' });
    } else {
      S.seq++; // in-flight explore 무효화
      showStatsView();
    }
  });
}

init();
