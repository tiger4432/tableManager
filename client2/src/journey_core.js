// ============================================================
// journey_core.js — 여정 대조(2장 전용)의 «읽기»
//
// SCENARIO_CONSOLE_BRIEF P0-3 (+ 부칙). ONE QUESTION = ONE URL:
//   ledger.html?view=journey&scope=wafer:<id1>,<id2>[&finding=<kind>]
// 다섯 번째 뷰다 — 페이지도, 모달도, 모드도 아니다.
//
// WHAT IT CONSUMES (측정 완료, :8080 라이브):
//   GET /api/ledger/journey?scope=<axis>:<v1>,<v2>[&finding=<kind>]
//     -> { state, engine:"journey", mode:"contrast", arity:2, headline,
//          finding, window, scope, gates[], statistics{state,message},
//          labels{}, mechanism{}, subject{type,key,column}, subjects[2],
//          segments[], notes[], summary{} }
//
// 🔴 이 화면은 «주어 2개»에서만 존재한다. 다른 arity는 서버가 422로 거절하며
// (`scope_is_not_a_pair`), 그 거절문은 해결된 주어를 이름으로 말한다. 클라는
// 그 거절을 화면으로 옮기지 스스로 첫 둘을 골라 조용히 그리지 않는다.
//
// 🔴 집단 통계는 이 화면에 «없다». 응답의 `statistics.state`가
// `not_applicable`이고 배수·신뢰구간·「우연 아님」 필드는 아예 오지 않는다.
// 이 파일은 그런 값을 «계산하지 않는다» — 없는 것을 지어내면 n=2에 집단을
// 주장하는 것이고, 그게 이 화면이 대체하려는 바로 그 거짓말이다.
//
// 🔴 기계어 금지. 화면에 나가는 이름은 언제나 서버의 `display`/`label`이고,
// `path`·`candidate_key`는 절대 렌더되지 않는다 — `candidate_key`는 딥링크의
// 기계 손잡이(hidden handle)이지 사람이 읽을 문자열이 아니다.
//
// 🔴 이 파일은 `window`·`document`를 만지지 않는다. 순수 함수만 — DOM은
// `journey_view.js`, 페치·세션 가드는 라우터(`ledger_trace.js`)의 몫이다.
// ============================================================

import { STRUCTURE_VIEW, edgeKey } from './ontology_structure_core.js';

export const JOURNEY_VIEW = 'journey';

// ── 원시값의 문 ──────────────────────────────────────────────

/**
 * 🔴 숫자의 유일한 문. `Number(null) === 0`·`Number('') === 0`이 「측정 0」을
 * 화면에 세우는 사고를 여기 한 곳에서 막는다. 진짜 0은 0으로 돌아온다.
 */
export function numOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

const strOrEmpty = (v) => (v === null || v === undefined ? '' : String(v));
const strOrNull = (v) => {
  const s = strOrEmpty(v);
  return s === '' ? null : s;
};
const listOf = (v) => (Array.isArray(v) ? v : []);
const boolOf = (v) => v === true;

// ── URL — 질문 하나 = 주소 하나 ──────────────────────────────

/** 주소창이 묻고 있는 것. `view`는 라우터의 `viewOf`와 같은 철자다. */
export function parseJourneyQuery(params) {
  const get = (k) => {
    const v = params && typeof params.get === 'function' ? params.get(k) : null;
    return v == null ? '' : String(v).trim();
  };
  return {
    view: get('view'),
    scope: get('scope'),
    finding: get('finding'),
    window: get('window'),
  };
}

/** 주소로 되쓰기. 빈 부분은 빼서 기본 질문이 `?view=journey&scope=…`로 남는다. */
export function journeyQuery(question, omit) {
  const q = question || {};
  const parts = [`view=${encodeURIComponent(JOURNEY_VIEW)}`];
  if (q.scope && omit !== 'scope') parts.push(`scope=${encodeURIComponent(q.scope)}`);
  if (q.finding && omit !== 'finding') parts.push(`finding=${encodeURIComponent(q.finding)}`);
  if (q.window && omit !== 'window') parts.push(`window=${encodeURIComponent(q.window)}`);
  return parts.join('&');
}

/**
 * 서버에 보낼 질의. `view`는 화면의 것이지 API의 것이 아니므로 빠진다.
 * 스코프가 없으면 빈 문자열 — 라우터는 그걸로 「아직 안 물었다」를 안다.
 */
export function journeyFetchQuery(question) {
  const q = question || {};
  const scope = strOrEmpty(q.scope);
  if (!scope) return '';
  const parts = [`scope=${encodeURIComponent(scope)}`];
  if (q.finding) parts.push(`finding=${encodeURIComponent(q.finding)}`);
  if (q.window) parts.push(`window=${encodeURIComponent(q.window)}`);
  return parts.join('&');
}

/**
 * 스코프 문자열의 두 조각. `wafer:A,B` → `{axis:'wafer', values:['A','B']}`.
 *
 * 🔴 여기서 개수를 «고치지» 않는다. 3개가 오면 3개로 읽고 화면이 그렇게
 * 말한다 — 앞의 둘만 조용히 그리는 것이 소유자가 「이게 뭔 공정인지 어떻게
 * 알아」라고 한 그 부류의 침묵이다.
 */
export function parseScope(scope) {
  const raw = strOrEmpty(scope);
  const at = raw.indexOf(':');
  if (at < 0) return { axis: '', values: raw ? [raw] : [] };
  const axis = raw.slice(0, at).trim();
  const values = raw.slice(at + 1).split(',').map((s) => s.trim()).filter(Boolean);
  return { axis, values };
}

// ── 응답의 상태 ──────────────────────────────────────────────

const STATES = new Set(['ready', 'empty', 'absent']);

export function journeyState(body) {
  const s = body && body.state != null ? String(body.state) : '';
  return STATES.has(s) ? s : (body ? 'unknown' : 'absent');
}

// ── 육하원칙 — 부칙의 여섯 슬롯 ──────────────────────────────

/**
 * 여섯 물음의 «순서»는 소유자가 말한 순서다: 누가·언제·어디서·무엇을·어떻게·왜.
 * 서버 키와의 대응만 여기 한 곳에 있고, 술어별 조립 코드는 어디에도 없다 —
 * 처음 보는 술어의 원자도 같은 여섯 슬롯으로 렌더돼야 맞게 지은 것이다.
 */
export const SIX_ORDER = ['who', 'when', 'where', 'what', 'how', 'why'];

/**
 * 한 슬롯의 읽기.
 *
 * 🔴 「답 없음」에는 두 종류가 있고 이 함수의 존재 이유가 그것이다.
 *   - `is_missing_record: true` → 원장의 결측. 「기록 없음」. 상태다.
 *   - 그 외의 미답(왜 슬롯의 미선언) → 선언의 부재. 「물리 모델에 아직 없음」.
 * 둘은 다른 층의 사건이라 다른 문구·다른 색으로 나가야 하고, 이 구분이
 * `tone`이다. 하나로 합치면 「우리가 안 적었다」와 「세상이 아직 선언 안 됐다」가
 * 같은 얼굴이 된다.
 *
 * 🔴 그리고 그 «둘째»를 서버의 사유 낱말로 «지목하지 않는다» — 여기서도,
 * 주석에서도. 분기는 `answered`와 `is_missing_record` 두 필드로만 서고, 사유
 * 낱말은 데이터로 들어와 `state`에 실려 나갈 뿐 이 파일의 어휘가 아니다.
 * (config-resolve 이음매의 상설 금지 INV-F9-7과 같은 규율: 낱말을 적어 두는
 * 순간 클라가 「무엇이 미선언인가」에 대한 자기 의견을 갖고, 그때부터 양쪽이
 * 어긋나도 서버 테스트는 전부 초록이다.)
 */
function readSixSlot(id, raw) {
  const src = raw && typeof raw === 'object' ? raw : null;
  const state = strOrEmpty(src && src.state);
  const missing = boolOf(src && src.is_missing_record);
  const answered = state === 'answered';
  const layer = strOrEmpty(src && src.layer);
  const citation = src && src.citation && typeof src.citation === 'object' ? {
    config: strOrNull(src.citation.config),
    model: strOrNull(src.citation.model),
    version: strOrNull(src.citation.model_version),
    versionState: strOrEmpty(src.citation.model_version_state),
  } : null;
  return {
    id,
    question: strOrEmpty(src && src.question) || id,
    about: strOrEmpty(src && src.about),
    state: state || 'unknown',
    answered,
    isMissingRecord: missing,
    // 🔴 세 값뿐이고 세 값이어야 한다. `missing`(원장의 결측)과
    // `undeclared`(선언의 부재)를 한 톤으로 묶으면 부칙 정정이 무효가 된다.
    tone: answered ? 'answered' : (missing ? 'missing' : 'undeclared'),
    // 서버의 문장 그대로. 답이 없을 때도 서버가 그 «없음»을 문장으로 말한다.
    text: strOrEmpty(src && src.text),
    message: strOrNull(src && src.message),
    // 왜만 다른 급이다 — 관측된 사실이 아니라 선언된 물리의 인용.
    isDeclaration: layer === 'declaration',
    citation,
    saidBy: listOf(src && src.said_by).map(strOrEmpty).filter(Boolean),
    model: strOrNull(src && src.model),
    path: listOf(src && src.path),
    verdict: strOrEmpty(src && src.verdict),
  };
}

/** 인용 꼬리 — 왜 슬롯에만 붙는다. 「모델 vN 기준」 또는 「선언 없음」. */
export function citationText(slot) {
  if (!slot || !slot.citation) return '';
  const c = slot.citation;
  if (c.model && c.version) return `모델 ${c.model} ${c.version} 기준`;
  if (c.model) return `모델 ${c.model} 기준`;
  if (c.versionState === 'undeclared') return `${c.config || '기전 선언'} — 선언 없음`;
  return c.config || '';
}

// ── 한 항목 = 한 카드 ────────────────────────────────────────

function readSide(raw) {
  const s = raw && typeof raw === 'object' ? raw : null;
  const state = strOrEmpty(s && s.state);
  return {
    state: state || 'unknown',
    // 🔴 `recorded`가 아닌 모든 상태는 «값 없음»이지 «0»이 아니다.
    present: state === 'recorded',
    value: numOrNull(s && s.value),
    text: strOrNull(s && s.text),
    claimClass: strOrNull(s && s.claim_class),
    claimClassLabel: strOrNull(s && s.claim_class_label),
    occurredAt: strOrNull(s && s.occurred_at),
    sourceWho: strOrNull(s && s.source_who),
    atomId: strOrNull(s && s.atom_id),
    contested: boolOf(s && s.contested),
    // 한쪽만 기록됐을 때 서버가 «왜 없는지»를 말한다 — 빈칸으로 두지 않는다.
    message: strOrNull(s && s.message),
  };
}

function readGate(raw) {
  const g = raw && typeof raw === 'object' ? raw : null;
  if (!g) return null;
  return {
    verdict: strOrEmpty(g.verdict) || 'unknown',
    message: strOrNull(g.message),
    reason: strOrNull(g.reason),
    basis: strOrNull(g.basis),
    model: strOrNull(g.model),
    role: strOrNull(g.role),
    path: listOf(g.path),
    hops: numOrNull(g.hops),
  };
}

/**
 * 기전 경로를 사람이 읽는 줄로.
 *
 * 🔴 방향 기호(`dir`)는 «찍지 않는다». `+`/`-`/`u`가 어느 간선에 붙는지를
 * 클라가 다시 해석하면 없는 물리를 주장하게 된다 — 서버의 왜 문장이 이미
 * 방향 없이 경로만 말하므로 화면도 같은 절제를 지킨다.
 */
export function pathText(path) {
  const nodes = listOf(path).map((p) => strOrEmpty(p && p.node)).filter(Boolean);
  return nodes.length ? nodes.join(' → ') : '';
}

/**
 * 카드의 정렬 등급 — 그리고 이것이 「편향이 원인과 같은 급으로 보이면 안 된다」의
 * 구현이다.
 *   0 = 선언된 인과 경로 있음 (원인 후보)
 *   1 = 경로 선언 없음 (사실이되 해석 없음)
 *   2 = 관측 편향 후보 (발생 아님) — 언제나 맨 아래, 언제나 꼬리표
 */
export function itemRank(item) {
  if (item.biasCandidate) return 2;
  if (item.gates.mechanism && item.gates.mechanism.verdict === 'pass') return 0;
  return 1;
}

/**
 * 같은 등급 안에서의 순서 — 서버의 `role`이 정한다.
 *
 * 🔴 카드의 주제는 「어떻게(값의 차이)」다. 등급이 같을 때 `content`(무엇이
 * 어떻게 달랐나)가 `actor`(누가 돌렸나)보다 먼저 와야 한다 — 이것을 안 두면
 * 두께 계측 구간의 대표 항목이 「장비」가 되어, 브리핑이 요구한 「#06 측정 없음
 * · #15 748.41µm」 대신 장비 이름 두 개가 올라온다(스모크에서 실제로 그랬다).
 * `segment`는 걷기의 부기(공정명·계열)라 맨 뒤다.
 */
const ROLE_ORDER = { content: 0, actor: 1, segment: 2 };
export function roleRank(item) {
  const r = ROLE_ORDER[item && item.role];
  return r === undefined ? 1 : r;
}

function readItem(raw, index) {
  const it = raw && typeof raw === 'object' ? raw : {};
  const gatesRaw = it.gates && typeof it.gates === 'object' ? it.gates : {};
  const six = {};
  const unanswered = [];
  for (const id of SIX_ORDER) {
    const slot = readSixSlot(id, it.six && it.six[id]);
    six[id] = slot;
    if (!slot.answered) unanswered.push(id);
  }
  const item = {
    index,
    // 🔴 화면에 나가지 않는다. 딥링크의 기계 손잡이일 뿐 — 사람은 `display`를 읽는다.
    candidateKey: strOrNull(it.candidate_key),
    rawPath: strOrNull(it.path),
    display: strOrEmpty(it.display) || strOrEmpty(it.label) || '항목',
    unit: strOrNull(it.unit),
    labelState: strOrEmpty(it.label_state),
    role: strOrEmpty(it.role),
    verdict: strOrEmpty(it.verdict) || 'unknown',
    A: readSide(it.A),
    B: readSide(it.B),
    gates: {
      upstream: readGate(gatesRaw.upstream),
      mechanism: readGate(gatesRaw.mechanism),
    },
    biasCandidate: boolOf(it.bias_candidate),
    six,
    sixUnanswered: unanswered,
    // 서버의 자기 채점. 부칙의 «완결»은 여섯이 다 답한 것이 아니라 여섯이 다
    // «말해진» 것이다 — 답 없음도 말해졌으면 완결이다.
    sixComplete: boolOf(it.six_completeness && it.six_completeness.complete),
  };
  item.rank = itemRank(item);
  item.mechanismPath = pathText(item.gates.mechanism && item.gates.mechanism.path);
  return item;
}

// ── 한 구간 ──────────────────────────────────────────────────

/** 앵커 — 배지가 구간으로 스크롤하는 데 쓰는 «주소». 인덱스가 유일성을 보장한다. */
export function segmentAnchor(key, index) {
  const safe = strOrEmpty(key).replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
  return `jseg-${index}-${safe || 'segment'}`;
}

function readAgreement(raw) {
  const a = raw && typeof raw === 'object' ? raw : {};
  const diff = a.differing && typeof a.differing === 'object' ? a.differing : {};
  return {
    actors: strOrEmpty(a.actors),
    content: strOrEmpty(a.content),
    // 🔴 접힘의 근거는 «동일성»(장비·레시피·rev)이지 «완전 일치»가 아니다.
    // 실데이터에서 바이트 단위로 같은 구간은 8개 중 0개라, 엄밀 일치로 접으면
    // 여덟 장이 전부 카드로 열려 — 이 설계가 벗어나려던 바로 그 더미가 된다.
    foldable: boolOf(a.foldable),
    basis: strOrEmpty(a.fold_basis),
    basisLabel: strOrEmpty(a.fold_basis_label),
    agreeingActors: listOf(a.agreeing_actors).map((x) => ({
      display: strOrEmpty(x && x.display),
      text: strOrEmpty(x && x.text),
    })).filter((x) => x.display || x.text),
    differing: {
      total: numOrNull(diff.total),
      numeric: numOrNull(diff.numeric),
      other: numOrNull(diff.other),
      mechanismBound: numOrNull(diff.mechanism_bound),
    },
    mechanismBoundDiverged: numOrNull(a.mechanism_bound_diverged),
    // 접힌 줄이 «밑에 있는 것 전부를 회계»하는 문장. 서버가 쓴 그대로.
    sentence: strOrNull(a.sentence),
  };
}

/**
 * 구간의 «모양» — 이 화면의 유일한 배치 결정.
 *
 *   folded  : 동일성 일치. 회색 한 줄 + 남은 차이를 이름으로 말함. 숨기지 않음.
 *   missing : 한쪽만 걸었음. 한 줄, 「결측은 상태」.
 *   card    : 갈라짐. 사실 문장 + 값 나란히.
 */
function shapeOf(verdict, agreement, foldLine) {
  if (verdict === 'one_sided') return 'missing';
  if (agreement.foldable && foldLine) return 'folded';
  // 🔴 접기로 판정됐는데 접을 «문장»이 없으면 카드로 연다. 회계하지 못하는
  // 한 줄로 접는 것은 「155.712와 154.152는 같음」이라는 작은 거짓말이다.
  return 'card';
}

function readSegment(raw, index, inferredKeys) {
  const s = raw && typeof raw === 'object' ? raw : {};
  const step = s.step && typeof s.step === 'object' ? s.step : {};
  const key = strOrEmpty(s.key);
  const agreement = readAgreement(s.agreement);
  const foldLine = strOrNull(s.fold_line);
  const verdict = strOrEmpty(s.verdict) || 'unknown';
  const items = listOf(s.items).map(readItem);
  const counts = s.item_counts && typeof s.item_counts === 'object' ? s.item_counts : {};
  const presence = s.presence && typeof s.presence === 'object' ? s.presence : {};
  const when = s.when && typeof s.when === 'object' ? s.when : {};

  // 갈라진 항목만 카드가 된다. 나머지 68개는 사라지지 않고 «같음» 목록으로
  // 접힘 밑에 남아, 접힌 줄이 회계하는 대상이 된다.
  const cards = items.filter((it) => it.verdict === 'diverged' || it.verdict === 'one_sided')
    .sort((a, b) => (a.rank - b.rank) || (roleRank(a) - roleRank(b)) || (a.index - b.index));
  const same = items.filter((it) => it.verdict === 'same');

  return {
    key,
    index,
    anchor: segmentAnchor(key, index),
    ordinal: numOrNull(s.ordinal),
    position: numOrNull(s.position),
    // 화면에 나가는 이름 — 언제나 이것. `predicate`는 딥링크로만 쓰인다.
    display: strOrEmpty(s.display) || strOrEmpty(step.label) || strOrEmpty(step.name) || '구간',
    //: 「2회차」 — `markRuns`가 «중복될 때만» 채운다. 기본은 빈 문자열.
    runText: '',
    predicate: strOrEmpty(s.predicate),
    predicateLabel: strOrEmpty(s.predicate_label),
    stepName: strOrEmpty(step.name),
    stepLabel: strOrEmpty(step.label),
    stepLabelState: strOrEmpty(step.label_state),
    family: strOrEmpty(step.family),
    familyLabel: strOrEmpty(step.family_label),
    verdict,
    presence: { A: strOrEmpty(presence.A), B: strOrEmpty(presence.B) },
    when: {
      A: when.A || null,
      B: when.B || null,
      gapSeconds: numOrNull(when.gap_seconds),
    },
    positionBasis: strOrEmpty(s.position_basis),
    // 🔴 서버가 「이 구간의 자리는 실측이 아니라 추론에서 왔다」고 말한 목록에
    // 들었는가. 순서를 물리 순서로 읽지 말라는 경고는 그 구간 «위»에 붙어야 한다.
    positionInferred: inferredKeys.has(key),
    agreement,
    foldLine,
    shape: shapeOf(verdict, agreement, foldLine),
    // 카드의 첫 줄. 서버가 쓴 사실 문장 그대로 — 클라가 다시 조립하지 않는다.
    sentence: strOrNull(s.sentence),
    itemCounts: {
      total: numOrNull(counts.total),
      same: numOrNull(counts.same),
      diverged: numOrNull(counts.diverged),
      oneSided: numOrNull(counts.one_sided),
    },
    cards,
    same,
    items,
  };
}

// ── 배지 ─────────────────────────────────────────────────────

const CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨', '⑩',
  '⑪', '⑫', '⑬', '⑭', '⑮', '⑯', '⑰', '⑱', '⑲', '⑳'];

export function ordinalMark(n) {
  return CIRCLED[n - 1] || `${n}.`;
}

/**
 * 머리의 갈림 배지 — 클릭하면 그 구간으로 스크롤한다.
 *
 * 문구는 명사형이다: 「갈림 ① 후공정 · 본딩 — 압력」. 값은 배지에 넣지 않는다 —
 * 배지는 목차이지 답이 아니고, 4자리 소수 두 개가 들어가면 목차가 아니게 된다.
 */
export function badgesOf(segments) {
  const out = [];
  let n = 0;
  for (const seg of segments) {
    if (seg.shape === 'folded') continue;
    n += 1;
    const lead = seg.cards[0];
    // 🔴 맨 앞 카드지, 아무 카드나가 아니다. `cards`는 이미 등급순이라 편향
    // 후보는 절대 배지에 이름을 올리지 못한다 — 목차에서부터 원인처럼 읽히면
    // 카드에서 아무리 낮춰도 늦다.
    const tail = seg.shape === 'missing' ? '한쪽만' : (lead ? lead.display : '');
    const name = seg.runText ? `${seg.display} ${seg.runText}` : seg.display;
    out.push({
      anchor: seg.anchor,
      key: seg.key,
      mark: ordinalMark(n),
      text: tail ? `갈림 ${ordinalMark(n)} ${name} — ${tail}` : `갈림 ${ordinalMark(n)} ${name}`,
      tone: seg.shape === 'missing' ? 'missing' : 'diverged',
    });
  }
  return out;
}

/**
 * 같은 공정을 두 번 지났을 때, 두 구간을 이름으로 구별해 준다.
 *
 * 🔴 이 웨이퍼들은 플라즈마 세정을 두 번, 본딩을 두 번 지났다. 축에 「후공정 ·
 * 본딩」이 두 줄 똑같이 서면 조작자는 어느 것이 어느 회차인지 알 수 없고,
 * 배지 두 개는 아예 같은 글자가 된다. 회차는 서버의 `ordinal`이며 클라가 세지
 * 않는다 — 다만 «중복될 때만» 붙인다. 한 번뿐인 공정에 「1회차」를 다는 것은
 * 없는 반복을 암시하는 소음이다.
 */
function markRuns(segments) {
  const seen = new Map();
  for (const s of segments) seen.set(s.display, (seen.get(s.display) || 0) + 1);
  for (const s of segments) {
    s.runText = (seen.get(s.display) > 1 && s.ordinal !== null) ? `${s.ordinal}회차` : '';
  }
  return segments;
}

// ── 딥링크 ───────────────────────────────────────────────────

/**
 * 구간명 클릭 → 구조 뷰의 그 술어 자리.
 *
 * 🔴 구조 뷰의 선택 키는 `subject_type|predicate|object_kind` 세 조각이고,
 * 여정 응답은 앞의 둘만 준다 (`subject.type` + `segments[].predicate`).
 * 셋째가 없을 때 «지어내지» 않는다 — 링크는 구조 뷰로 가되 아무것도 선택하지
 * 않고, `resolved:false`가 화면에 그 사실을 말하게 한다. 서버가
 * `segments[].object_kind`(또는 완성된 `edge_key`)를 보내는 날, 이 함수는
 * 한 줄도 안 고치고 하이라이트로 살아난다.
 */
export function structureHref(subjectType, segment) {
  const st = strOrEmpty(subjectType);
  const pred = strOrEmpty(segment && segment.predicate);
  const kind = strOrEmpty(segment && segment.objectKind);
  const bare = `?view=${encodeURIComponent(STRUCTURE_VIEW)}`;
  if (!st || !pred || !kind) return { href: bare, resolved: false };
  const key = edgeKey(st, pred, kind);
  return {
    href: `${bare}&edge=${encodeURIComponent(key)}#edge-${encodeURIComponent(key)}`,
    resolved: true,
  };
}

/**
 * 「물리 경로 있음」 클릭 → 구조 뷰의 기전 그래프.
 *
 * 🔴 구조 뷰의 기전 행은 `data-model`은 달고 있으나 `id`가 없어, 지금은 모형
 * 하나를 찍어 스크롤할 앵커가 없다. 링크는 기전 그래프가 있는 화면으로 가고,
 * 프래그먼트는 그 앵커가 생기는 날 바로 맞는 이름으로 미리 붙여 둔다 —
 * 없는 앵커는 브라우저가 조용히 무시하므로 오늘도 깨지지 않는다.
 */
export function mechanismHref(model) {
  const m = strOrEmpty(model);
  const bare = `?view=${encodeURIComponent(STRUCTURE_VIEW)}`;
  if (!m) return { href: bare, resolved: false };
  return { href: `${bare}#mech-${encodeURIComponent(m)}`, resolved: false };
}

// ── 주어 ─────────────────────────────────────────────────────

function readSubject(raw) {
  const s = raw && typeof raw === 'object' ? raw : {};
  const out = s.outcome && typeof s.outcome === 'object' ? s.outcome : null;
  return {
    slot: strOrEmpty(s.slot),
    id: strOrEmpty(s.id),
    label: strOrEmpty(s.label) || strOrEmpty(s.id),
    subjectType: strOrEmpty(s.subject_type),
    observedAt: strOrNull(s.observed_at),
    observedAtState: strOrEmpty(s.observed_at_state),
    atoms: numOrNull(s.atoms),
    atomsTruncated: boolOf(s.atoms_truncated),
    outcome: out ? {
      kind: strOrEmpty(out.kind),
      label: strOrEmpty(out.label),
      scanned: numOrNull(out.scanned),
      found: numOrNull(out.found),
      state: strOrEmpty(out.state),
      attributed: boolOf(out.attributed_to_segment),
      message: strOrNull(out.message),
    } : null,
  };
}

// ── 모델 ─────────────────────────────────────────────────────

/**
 * @param body 서버 응답 (없으면 null)
 * @param question `parseJourneyQuery` 출력
 * @param refusal 거절 읽기 `{status, reason, message, subjects[]}` (있으면)
 */
export function journeyModel({ body, question, refusal } = {}) {
  const q = question || {};
  const asked = parseScope(q.scope);
  const state = journeyState(body);
  const served = state === 'ready' && body && typeof body === 'object';

  // 🔴 거절은 «내용»이다. 주어가 하나로 풀렸다는 사실은 화면이 말해야 하는
  // 답이지 감출 오류가 아니다 — 서버가 해결된 주어를 이름으로 말해 주므로
  // 화면도 그 이름을 그대로 옮긴다.
  const refused = refusal && typeof refusal === 'object' ? {
    status: numOrNull(refusal.status),
    reason: strOrEmpty(refusal.reason),
    message: strOrEmpty(refusal.message),
    arityRequired: numOrNull(refusal.arity_required),
    arityResolved: numOrNull(refusal.arity_resolved),
    subjects: listOf(refusal.subjects).map(strOrEmpty).filter(Boolean),
    axis: strOrEmpty(refusal.axis),
  } : null;

  const inferredKeys = new Set();
  let biasNote = null;
  for (const note of listOf(served ? body.notes : [])) {
    const kind = strOrEmpty(note && note.note);
    if (kind === 'position_from_inference_only') {
      for (const k of listOf(note.segments)) inferredKeys.add(strOrEmpty(k));
    }
    if (kind === 'bias_candidates') biasNote = strOrNull(note.message);
  }

  const segments = markRuns(
    listOf(served ? body.segments : []).map((s, i) => readSegment(s, i, inferredKeys)));
  const subjects = listOf(served ? body.subjects : []).map(readSubject);
  const summaryRaw = served && body.summary && typeof body.summary === 'object' ? body.summary : {};
  const statsRaw = served && body.statistics && typeof body.statistics === 'object' ? body.statistics : {};
  const subjectRaw = served && body.subject && typeof body.subject === 'object' ? body.subject : {};

  const pairText = subjects.length === 2
    ? `${subjects[0].label} vs ${subjects[1].label}`
    : asked.values.join(' vs ');

  return {
    state,
    served,
    refused,
    engine: strOrEmpty(served ? body.engine : ''),
    arity: numOrNull(served ? body.arity : null),
    generatedAt: strOrNull(served ? body.generated_at : null),
    asked,
    question: { view: JOURNEY_VIEW, scope: strOrEmpty(q.scope), finding: strOrEmpty(q.finding) },

    subjectType: strOrEmpty(subjectRaw.type),
    subjects,
    pairText,

    // 서버가 쓴 한 줄 요약 — 「같은 길 N구간, 갈라진 곳 M곳」. 클라가 다시 세지
    // 않는다. 두 곳에서 센 수는 언젠가 어긋나고, 어긋나면 어느 쪽이 맞는지
    // 화면 위에서는 알 길이 없다.
    headline: strOrNull(served ? body.headline : null),

    finding: served && body.finding ? {
      kind: strOrEmpty(body.finding.kind),
      label: strOrEmpty(body.finding.label),
      declared: boolOf(body.finding.declared),
    } : null,

    gates: listOf(served ? body.gates : []).map((g) => ({
      id: strOrEmpty(g && g.id),
      label: strOrEmpty(g && g.label),
      basis: strOrEmpty(g && g.basis),
      doc: strOrEmpty(g && g.doc),
    })),

    // 🔴 계산하지 않는다. 서버가 「성립하지 않는다」고 «말한» 것을 옮길 뿐이다.
    statistics: {
      state: strOrEmpty(statsRaw.state),
      notApplicable: strOrEmpty(statsRaw.state) === 'not_applicable',
      message: strOrNull(statsRaw.message),
    },

    labels: served && body.labels ? {
      state: strOrEmpty(body.labels.state),
      config: strOrEmpty(body.labels.config),
      origin: strOrEmpty(body.labels.origin),
      message: strOrNull(body.labels.message),
    } : null,

    mechanism: served && body.mechanism ? {
      state: strOrEmpty(body.mechanism.state),
      config: strOrEmpty(body.mechanism.config),
      message: strOrNull(body.mechanism.message),
      bindingCount: numOrNull(body.mechanism.binding_count),
    } : null,

    segments,
    badges: badgesOf(segments),
    biasNote,
    notes: listOf(served ? body.notes : []).map((n) => ({
      note: strOrEmpty(n && n.note),
      message: strOrEmpty(n && n.message),
    })).filter((n) => n.message),

    summary: {
      segments: numOrNull(summaryRaw.segments),
      folded: numOrNull(summaryRaw.folded),
      opened: numOrNull(summaryRaw.opened),
      same: numOrNull(summaryRaw.same),
      diverged: numOrNull(summaryRaw.diverged),
      oneSided: numOrNull(summaryRaw.one_sided),
      foldBasis: strOrEmpty(summaryRaw.fold_basis),
    },
  };
}

// ── 문구 ─────────────────────────────────────────────────────

/**
 * 한 변의 값 표기. 기록이 없으면 「기록 없음」 — 빈칸도, 대시도, 0도 아니다.
 * (부칙: 「결측은 여섯 어느 자리든 「기록 없음」으로 표기(빈칸·생략 금지)」)
 */
export function sideText(side) {
  if (!side) return '기록 없음';
  if (side.present && side.text) return side.text;
  if (side.text) return side.text;
  return '기록 없음';
}

/**
 * 구간 문장에서 구간 «이름»을 뺀 나머지.
 *
 * 🔴 파싱이 아니라 접두사 «동등 비교»다. 서버 문장은 「<구간명> — <나머지>」
 * 모양이고, 축의 줄은 구간명을 이미 자기 칸에 그린다. 접두사가 정확히 맞을
 * 때만 잘라 내고, 안 맞으면 문장을 통째로 보여 준다 — 문장이 살짝 중복되는
 * 것은 읽기 불편할 뿐이지만, 정규식으로 잘라 내다 틀리면 «없는 사실»이 된다.
 */
export function sentenceTail(segment) {
  const s = strOrEmpty(segment && segment.sentence);
  const pre = `${strOrEmpty(segment && segment.display)} — `;
  return s.startsWith(pre) ? s.slice(pre.length) : s;
}

/** 시간 간격을 사람 말로. 초는 초로, 분은 분으로 — 반올림해서 0을 만들지 않는다. */
export function gapText(seconds) {
  const n = numOrNull(seconds);
  if (n === null) return '';
  const abs = Math.abs(n);
  // 🔴 0은 「0초 차이」가 아니라 「동시」다. 두 기록이 같은 시각이라는 것은
  // 아주 작은 차이가 아니라 차이 없음이고, 서버의 언제 슬롯도 그렇게 쓴다.
  if (abs === 0) return '동시';
  if (abs < 60) return `${abs}초 차이`;
  if (abs < 3600) return `${Math.round(abs / 60)}분 차이`;
  if (abs < 86400) return `${(abs / 3600).toFixed(1)}시간 차이`;
  return `${(abs / 86400).toFixed(1)}일 차이`;
}

const GATE_TONE = {
  pass: 'pass',
  fail: 'fail',
  unknown: 'unknown',
  bias_candidate: 'bias',
};

/**
 * 관문 칩 하나의 읽기. 「발생 아님」은 별도 톤이다 — 통과와 같은 색이면 안 된다.
 *
 * 🔴 관문 라벨은 «통과했을 때의 뜻»으로 쓰여 있다(「물리 경로 있음」·「시간상
 * 앞섬」). 그래서 통과와 불통과에는 그대로 쓰되, «모르는» 상태에 그 라벨을
 * 물음표만 붙여 재사용하면 안 된다 — 화면에서 「? 물리 경로 있음」은 경로가
 * 있다고 반쯤 주장하는 문장으로 읽힌다(브라우저에서 실제로 그렇게 보였다).
 * 모를 때는 서버가 «무엇을 모르는지» 쓴 문장을 그대로 쓴다. 서버가 아무 말도
 * 안 했을 때만 부칙의 낱말 «모름»으로 떨어진다.
 */
export function gateChip(axis, gate) {
  if (!gate) return null;
  const tone = GATE_TONE[gate.verdict] || 'unknown';
  const label = strOrEmpty(axis && axis.label) || strOrEmpty(axis && axis.id);
  let text;
  if (tone === 'pass') text = `✓ ${label}`;
  else if (tone === 'bias') text = '발생 아님 — 관측 편향';
  else if (tone === 'fail') text = `✗ ${label}`;
  else text = gate.message ? `? ${gate.message}` : `? ${label} 모름`;
  return { id: strOrEmpty(axis && axis.id), tone, text, title: gate.message || (axis && axis.doc) || '' };
}
