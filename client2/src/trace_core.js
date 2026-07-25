// ============================================================
// trace_core.js — G2 추적 리포트 순수 로직 (DOM/네트워크 무관)
// - trace.js(리포트 페이지)와 trace_launch.js(index 진입점)가 공유
// - 의존성 없음(CSS/DOM 임포트 금지) → node 단독 테스트 가능
// - identity 조립 규칙은 서버 G1 `compose_identity`의 클라이언트 미러:
//   "|" 조인 + 이스케이프("\"→"\\", "|"→"\|") + float 정수 안정화(3.0→"3")
//   (서버 코드 미참조 — G1 확정 계약 문서 기준. 변경 시 총괄 경유 동기화 필수)
// ============================================================

export const SEED_CAP = 20;          // 지시서 고정: 시드 상한
export const TRACE_LIMIT = 1000;     // /graph/trace limit (응답 ≤1000 노드 상정)

// ── identity 조립 (서버 compose_identity 미러) ──────────────

/** 단일 식별자 파트 정규화. 결손(null/undefined/공백)은 null 반환. */
export function normalizeIdentityPart(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === 'number') {
    // JS Number는 3.0 === 3 → String()이 이미 "3" (float 정수 안정화와 합치)
    return Number.isFinite(v) ? String(v) : null;
  }
  const s = String(v).trim();
  if (s === '') return null;
  // float 정수 안정화 미러: "3.0" / "3.00" → "3" (숫자형 문자열만)
  const m = s.match(/^(-?\d+)\.0+$/);
  return m ? m[1] : s;
}

/** 파이프/백슬래시 이스케이프 — ("A|B","C") ≠ ("A","B|C") 보장 미러 */
export function escapeIdentityPart(s) {
  return s.replace(/\\/g, '\\\\').replace(/\|/g, '\\|');
}

/**
 * identity_columns 값 배열 → identity_key 문자열.
 * 파트 중 하나라도 결손이면 null (시드 생성 불가 행).
 */
export function composeIdentity(values) {
  if (!Array.isArray(values) || values.length === 0) return null;
  const parts = [];
  for (const v of values) {
    const p = normalizeIdentityPart(v);
    if (p === null) return null;
    parts.push(escapeIdentityPart(p));
  }
  return parts.join('|');
}

// ── 시드 목록 ───────────────────────────────────────────────

/** 시드 동일성 키 (label + identity) */
export function seedKey(seed) {
  return JSON.stringify([seed.label, seed.identity]);
}

/** 중복 제거(순서 보존) 후 상한 적용 → {seeds, dropped} */
export function capSeeds(seeds, cap = SEED_CAP) {
  const seen = new Set();
  const unique = [];
  for (const s of seeds) {
    const k = seedKey(s);
    if (seen.has(k)) continue;
    seen.add(k);
    unique.push(s);
  }
  return { seeds: unique.slice(0, cap), dropped: Math.max(0, unique.length - cap) };
}

/**
 * URL ?seeds= (urlencoded JSON [{label, identity}]) 방어적 파싱.
 * @returns {{seeds: Array<{label:string, identity:string}>, invalid: number}}
 */
export function parseSeedsParam(raw) {
  if (!raw) return { seeds: [], invalid: 0 };
  let arr;
  try {
    arr = JSON.parse(raw);
  } catch (e) {
    return { seeds: [], invalid: 1 };
  }
  if (!Array.isArray(arr)) return { seeds: [], invalid: 1 };
  const seeds = [];
  let invalid = 0;
  for (const e of arr) {
    const ok = e && typeof e === 'object'
      && typeof e.label === 'string' && e.label.trim() !== ''
      && e.identity !== null && e.identity !== undefined && String(e.identity) !== '';
    if (!ok) { invalid++; continue; }
    seeds.push({ label: e.label.trim(), identity: String(e.identity) });
  }
  return { seeds, invalid };
}

/**
 * 응답 missing_seeds 정규화 — 형태 미상정 방어:
 * {label, identity} 객체 | "Label:identity" 문자열 | 기타 → {label, identity}
 */
export function normalizeMissingSeeds(missing) {
  if (!Array.isArray(missing)) return [];
  return missing.map((x) => {
    if (x && typeof x === 'object') {
      return {
        label: String(x.label ?? ''),
        identity: String(x.identity ?? x.identity_key ?? ''),
      };
    }
    const s = String(x ?? '');
    const i = s.indexOf(':');
    if (i > 0) return { label: s.slice(0, i), identity: s.slice(i + 1) };
    return { label: '', identity: s };
  });
}

/** 시드가 missing 목록에 있는지 (label 미상('')인 missing은 identity만 비교) */
export function isSeedMissing(seed, missingList) {
  return missingList.some((m) => (m.label === '' || m.label === seed.label)
    && m.identity === seed.identity);
}

// ── 요청 본문 ───────────────────────────────────────────────

/** datetime-local 값("YYYY-MM-DDTHH:mm")에 초 보정 */
export function withSeconds(v) {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(v) ? `${v}:00` : v;
}

/** POST /graph/trace 요청 본문 조립 (빈 시간 범위는 생략) */
export function buildTraceRequest({ seeds, depth, timeFrom, timeTo, limit = TRACE_LIMIT }) {
  const body = { seeds, depth, limit };
  if (timeFrom) body.time_from = withSeconds(timeFrom);
  if (timeTo) body.time_to = withSeconds(timeTo);
  return body;
}

// ── 응답 조립 (그룹 테이블 + 타임라인) ──────────────────────

/**
 * 라벨별 엔티티 그룹.
 * @param {Array} nodes  [{id,label,identity_key,props}]
 * @param {Array} edges  [{from,to,...}]
 * @param {Set}   seedIdSet  응답 seed_ids
 * @returns [{label, count, seedCount, rows:[{node, degree, isSeed}]}]
 *  - 행 정렬: 시드 우선 → degree 내림 → identity 오름
 *  - 그룹 정렬: 시드 보유 그룹 우선(시드 수 내림) → 노드 수 내림 → 라벨 오름
 */
export function groupNodesByLabel(nodes, edges, seedIdSet) {
  const degree = new Map();
  for (const e of edges) {
    degree.set(e.from, (degree.get(e.from) || 0) + 1);
    if (e.to !== e.from) degree.set(e.to, (degree.get(e.to) || 0) + 1);
  }
  const byLabel = new Map();
  for (const n of nodes) {
    const label = String(n.label ?? '');
    if (!byLabel.has(label)) byLabel.set(label, []);
    byLabel.get(label).push({
      node: n,
      degree: degree.get(n.id) || 0,
      isSeed: seedIdSet.has(n.id),
    });
  }
  const groups = [...byLabel.entries()].map(([label, rows]) => {
    rows.sort((a, b) => {
      if (a.isSeed !== b.isSeed) return a.isSeed ? -1 : 1;
      if (a.degree !== b.degree) return b.degree - a.degree;
      return String(a.node.identity_key) < String(b.node.identity_key) ? -1 : 1;
    });
    return {
      label,
      count: rows.length,
      seedCount: rows.filter((r) => r.isSeed).length,
      rows,
    };
  });
  groups.sort((a, b) => {
    if (a.seedCount !== b.seedCount) return b.seedCount - a.seedCount;
    if (a.count !== b.count) return b.count - a.count;
    return a.label < b.label ? -1 : 1;
  });
  return groups;
}

/**
 * 엣지를 타임라인(event_time 있음, 시간 오름차순)과 구조 관계(없음)로 분리.
 * @returns {{timed: Array<{edge, t:number}>, structural: Array}}
 */
export function splitTimeline(edges) {
  const timed = [];
  const structural = [];
  for (const e of edges) {
    const raw = e.event_time;
    const t = (raw === null || raw === undefined || raw === '') ? NaN : new Date(raw).getTime();
    if (Number.isNaN(t)) structural.push(e);
    else timed.push({ edge: e, t });
  }
  timed.sort((a, b) => {
    if (a.t !== b.t) return a.t - b.t;
    if (a.edge.type !== b.edge.type) return String(a.edge.type) < String(b.edge.type) ? -1 : 1;
    return String(a.edge.from) < String(b.edge.from) ? -1 : 1;
  });
  structural.sort((a, b) => {
    if (a.type !== b.type) return String(a.type) < String(b.type) ? -1 : 1;
    return String(a.from) < String(b.from) ? -1 : 1;
  });
  return { timed, structural };
}

// ── 표시 헬퍼 ───────────────────────────────────────────────

/** props 요약: 앞 max개 "k: v" + 초과분 "+N" (null/객체 값은 뒤로) */
export function propsSummary(props, max = 3) {
  if (!props || typeof props !== 'object') return '';
  const entries = Object.entries(props);
  const scalar = entries.filter(([, v]) => v !== null && v !== undefined && typeof v !== 'object');
  const shown = scalar.slice(0, max)
    .map(([k, v]) => `${k}: ${truncateText(String(v), 24)}`);
  const rest = entries.length - shown.length;
  if (rest > 0) shown.push(`+${rest}`);
  return shown.join(' · ');
}

export function truncateText(s, n) {
  const str = String(s);
  return str.length > n ? `${str.slice(0, n - 1)}…` : str;
}

/** event_time → 로컬 "YYYY-MM-DD HH:MM:SS" (파싱 불가 시 원문) */
export function fmtEventTime(raw) {
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return String(raw);
  const p = (x) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
    + `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
