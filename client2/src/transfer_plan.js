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
//      `controller.updateLegendRow(value, { bands, knobs })`로만 쓴다 — 저장·삭제·동시성
//      가드는 전부 그 한 경로에 있다(구현이 둘이면 반드시 갈라진다).
//
//   ⭐ 구간(band) 모델 — **연속 스택, 구간당 숫자 하나.**
//      · 첫 구간은 무조건 1층에서 시작한다.
//      · 이후 구간의 시작은 **앞 구간의 끝 + 1**이고 편집할 수 없다.
//      · 그래서 사용자가 입력하는 값은 구간당 **끝 층(`to`) 하나**뿐이다 —
//        스택 전체가 *끊는 지점 목록*이다. `1, 2-15, 16`은 **구간 3개**다.
//      · 층 수 = `to_i − to_(i−1)` (뺄셈 한 번, 라벨 파싱 없음).
//      · **순서 = 배열 위치 · 정체 = `seq`.** `to`를 고치면 위치가 따라 움직이지만 `seq`는
//        절대 바뀌지 않는다 — seq를 재번호하면 자재가 조용히 남의 구간으로 따라간다.
//
//   ⭐ 파생값은 저장하지 않는다.
//      구간 총 소요 = **칠한 셀 수 × 층 수** · 자재당 = **ceil(총 소요 / 자재 수)**.
//      저장하면 누가 한 칸 더 칠하는 순간 어긋난 채 남고 아무도 모른다. 그리고 식의 구현은
//      각각 **하나뿐**이다(저장 `ceil` / 표시 `round`로 갈려 DB 34 · 화면 33이던 결함).
//
//   ⚠️ 검증/경고 표시 일습(수량 부족 판정·교차 초과배정·validate 연동·신뢰 어휘 배지)은
//      사용자 지시로 보류다. 판정 로직은 지우지 않고 아래 §보류 구역에 그대로 두었다.
// ============================================================
import { API_BASE } from './config.js';
import { showToast } from './utils.js';
import './transfer_plan.css';

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
  // legend 미러 = DOE 그 자체 { value, desc, color, knobs:[{k,v}], bands:[{seq,to,materials:[str]}] }
  legendRows: [],
  openValue: null,           // 펼친 DOE (한 번에 하나)
  counts: {},                // value -> 칠한 셀 수
  activeBrush: '',
  summaries: new Map(),      // 자재 ID -> { status, data, error }
  matMapState: new Map(),    // "table|자재ID" -> true | false | null(미상)
  keyColumns: new Map(),     // table -> map_key_columns
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

// 값만 필요한 호출부용 얇은 래퍼. **blank와 invalid는 둘 다 null**이다 — 산술에서 구분되지
// 않는 것이 계약이고, 구분이 필요한 곳(표시)은 `bandToState`를 직접 쓴다.
function bandTo(b) { return bandToState(b).value; }

// map_editor의 `normalizeBands`가 저장 정규형을 만들 때 같은 판정기를 쓴다. 정규화가 자기
// 나름의 `Number()`를 돌리면 **읽기-수정-쓰기가 조용히 값을 바꾼다** (실제로 '0x10'이 16으로
// 저장되고 있었다). 의존 방향은 map_editor → transfer_plan 하나뿐이라 순환이 생기지 않는다.
// ⚠️ `export function bandToState`로 합치지 말 것 — 계약 하네스가 `function NAME(`로 본문을
//    떼어 가므로, 선언 앞에 `export`가 붙으면 추출이 깨진다(하네스는 exit 2로 죽는다).
export { bandToState };

// 앞 구간의 끝 층(없으면 0). **배열 위치**가 순서라는 규칙이 여기 한 줄에 들어 있다.
// `ok`인 구간만 걷기를 멈춘다 — blank도 invalid도 건너뛴다.
function prevTo(bands, i) {
  for (let j = i - 1; j >= 0; j--) {
    const st = bandToState(bands[j]);
    if (st.state === 'ok') return st.value;
  }
  return 0;
}

// 시작 층 = 앞 구간의 끝 + 1. 유도값이라 편집 대상이 아니다.
function bandFrom(bands, i) { return prevTo(bands, i) + 1; }

// 층 수 = to_i − to_(i−1). 뺄셈 한 번 — 라벨을 파싱하지 않는다.
function bandLayers(bands, i) {
  const st = bandToState(bands[i]);
  return st.state === 'ok' ? Math.max(0, st.value - prevTo(bands, i)) : 0;
}

function paintedOf(value) { return Number(S.counts[value] || 0); }

// 구간 총 소요 = 칠한 셀 수 × 층 수. **저장하지 않는다** — 맵을 더 칠하면 따라 움직인다.
function bandTotal(value, bands, i) { return paintedOf(value) * bandLayers(bands, i); }

// 자재 1매당 배분 = ceil(총 소요 / 자재 수). 내림/반올림은 부족분을 숨긴다.
function bandShare(value, bands, i) {
  const b = bands[i];
  const n = (b && Array.isArray(b.materials)) ? b.materials.length : 0;
  return n > 0 ? Math.ceil(bandTotal(value, bands, i) / n) : 0;
}

// 각 `to`는 앞 구간의 `to`보다 **커야** 한다 (같거나 작으면 빈 구간·역전).
// 반환: 오류 문구 또는 ''(정상).
function validateBands(bands) {
  let last = 0;
  for (let i = 0; i < bands.length; i++) {
    const t = bandTo(bands[i]);
    if (t === null) continue;
    if (t < 1) return `끝 층은 1 이상이어야 합니다.`;
    if (t <= last) return `끝 층 ${t}은(는) 앞 구간의 끝 층 ${last}보다 커야 합니다.`;
    last = t;
  }
  return '';
}

// 배열 위치가 스택 순서이므로 `to`가 바뀌면 위치도 따라간다.
// ⚠️ **`seq`는 절대 손대지 않는다.** 자재가 seq에 매달려 있어서, 재정렬이 seq를
//    재번호하면 자재가 조용히 남의 구간으로 따라간다(순서 ≠ 정체).
function sortBands(bands) {
  return bands.slice().sort((a, b) => {
    const ta = bandTo(a), tb = bandTo(b);
    if (ta === null && tb === null) return 0;
    if (ta === null) return 1;     // 미입력은 항상 뒤
    if (tb === null) return -1;
    return ta - tb;
  });
}

function nextBandSeq(bands) {
  return bands.reduce((m, b) => Math.max(m, Number(b.seq) || 0), 0) + 1;
}

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
function bandsOf(value) {
  const r = rowOf(value);
  return (r && Array.isArray(r.bands)) ? r.bands : [];
}
function knobsOf(value) {
  const r = rowOf(value);
  return (r && Array.isArray(r.knobs)) ? r.knobs : [];
}

// DOE 변조의 **유일한 관문**. map_editor가 영속화(로컬 캐시 + 서버 registry 디바운스)를
// 맡으므로 이 파일에는 저장 코드가 없다.
function commitBands(value, bands) {
  const r = controller.updateLegendRow(value, { bands });
  if (!r || !r.ok) { showToast((r && r.error) || 'DOE 저장 실패', 'warning'); return false; }
  return true;
}
function commitKnobs(value, knobs) {
  const r = controller.updateLegendRow(value, { knobs });
  if (!r || !r.ok) { showToast((r && r.error) || 'knob 저장 실패', 'warning'); return false; }
  return true;
}

// ── 자재 가용 (source-summary) ──────────────────────────
function summaryKey(id) {
  const st = stageOfTable(S.ctx.table);
  return `${st ? st.id : S.ctx.table}::${id}`;
}
function isPlainNotFound(status, body) {
  return (status === 405) || (status === 404 && (!body || body.detail === 'Not Found'));
}

async function getSourceSummary(id, force = false) {
  const key = summaryKey(id);
  const cached = S.summaries.get(key);
  if (!force && cached && (cached.status === 'ok' || cached.status === 'loading')) {
    if (cached.promise) await cached.promise;
    return S.summaries.get(key);
  }
  const st = stageOfTable(S.ctx.table);
  const { lot, slot } = splitMaterialId(id);
  if (lot === null || slot === null) {
    // 해석 실패는 **조회하지 않는다.** `?lot=ABC&slot=`를 물으면 서버가 0을 돌려주고
    // 화면은 그것을 확정 잔여로 보여준다 — 부족 경고가 조용히 죽는 경로다.
    const entry = { status: 'unresolved' };
    S.summaries.set(key, entry);
    return entry;
  }
  const entry = { status: 'loading' };
  entry.promise = (async () => {
    const params = new URLSearchParams({ stage: st ? st.id : '', lot, slot });
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
// 반환: { status, value, reliable, reason }
function availabilityOf(id) {
  const entry = S.summaries.get(summaryKey(id));
  if (!entry) return { status: null, value: null, reliable: false, reason: '아직 조회하지 않음' };
  if (entry.status !== 'ok') {
    return {
      status: entry.status, value: null, reliable: false,
      reason: entry.status === 'loading' ? '조회 중'
        : (entry.status === 'unresolved' ? '자재 ID를 lot·slot으로 나눌 수 없어 조회하지 않았습니다 (형식: lot_slot)'
          : (entry.status === 'unsupported' ? '이 서버는 가용 집계를 제공하지 않습니다'
            : (entry.error || '가용 조회 실패'))),
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
function availableOf(id) {
  const a = availabilityOf(id);
  return a.reliable ? a.value : null;
}

// ── 자재 맵 존재 여부 ───────────────────────────────────
function matMapCacheKey(table, id) { return `${table}|${id}`; }

async function materialMetaValues(table, id) {
  let cols = S.keyColumns.get(table);
  if (!cols) {
    cols = controller && controller.fetchMapKeyColumns ? await controller.fetchMapKeyColumns(table) : [];
    S.keyColumns.set(table, cols || []);
  }
  const out = {};
  if (!cols || cols.length === 0) return out;
  // 맵 키 컬럼이 하나면 자재 ID **원문이 곧 맵 키**다 — 해석이 끼지 않는다.
  if (cols.length === 1) { out[cols[0]] = String(id); return out; }
  const { lot, slot } = splitMaterialId(id);
  // 해석 실패면 **빈 필터**를 돌려준다 → `probeMapExists`가 null(=미상)을 준다.
  // 여기서 억지로 조회하면 "맵 없음"이 나오는데, 그건 "확인 못 했다"의 위장이다.
  if (lot === null || slot === null) return out;
  out[cols[0]] = lot;
  out[cols[1]] = slot;
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
  const stageBadge = child
    ? '<span class="tp-stage-badge material">자재 맵</span>'
    : (st ? `<span class="tp-stage-badge">${esc(st.name)}</span>`
          : '<span class="tp-stage-badge none">일반 맵 (legend)</span>');

  const ss = (controller && controller.getPlanSaveState) ? controller.getPlanSaveState() : { status: 'idle' };
  let savedChip;
  if (ss.status === 'conflict') {
    savedChip = '<span class="tp-chip bad" title="다른 사람이 이 계획을 바꿨습니다. 지금 저장하면 그 편집이 지워지므로 저장을 막았습니다 — 맵을 다시 불러오십시오.">⚠ 다른 사람이 변경함 · 다시 불러오기</span>';
  } else if (ss.status === 'unknown-server-state') {
    savedChip = `<span class="tp-chip warn" title="${esc(ss.error || '서버 조회 실패')}">⚠ 서버 상태 미확인 · 저장 보류</span>`;
  } else if (ss.status === 'error') {
    savedChip = `<span class="tp-chip bad" title="${esc(ss.error || '')}">⚠ 서버 저장 실패</span>`;
  } else if (ss.status === 'ok' && ss.at) {
    savedChip = `<span class="tp-chip dim" title="legend와 같은 디바운스 자동 저장">자동 저장 ${esc(hhmm(ss.at))}</span>`;
  } else {
    savedChip = '<span class="tp-chip dim" title="legend와 같은 디바운스 자동 저장">변경 시 자동 저장</span>';
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

// 접힌 행의 2번째 줄. 전부 파생값이라 페인팅과 함께 즉시 따라 움직인다.
function doeLine2(value, planMode) {
  const painted = paintedOf(value);
  if (!planMode) return `칠함 ${painted}`;
  const bands = bandsOf(value);
  if (bands.length === 0) return `칠함 ${painted} · 구간 없음`;
  const top = bands.reduce((m, b) => { const t = bandTo(b); return Math.max(m, t === null ? 0 : t); }, 0);
  const total = bands.reduce((a, b, i) => a + bandTotal(value, bands, i), 0);
  const mats = new Set();
  bands.forEach(b => (b.materials || []).forEach(m => mats.add(m)));
  return `칠함 ${painted} · 구간 ${bands.length}개 (1–${top || '?'}층) · 자재 ${mats.size}매 · 소요 ${total}`;
}

// 파생 숫자 한 줄 — 사용자가 머릿속으로 곱하지 않도록 **식을 그대로 보여준다**.
function bandCalcText(value, bands, i) {
  // 읽을 수 없는 끝 층은 0층으로 세되 **왜 0인지**를 이 줄에서 말한다.
  // (틀린 숫자보다 나쁜 것은 틀린 줄 모르는 숫자다.)
  if (bandToState(bands[i]).state === 'invalid') {
    return '끝 층을 숫자로 읽을 수 없어 이 구간은 0층으로 셉니다 — 끝 층을 다시 입력하세요.';
  }
  const layers = bandLayers(bands, i);
  if (layers <= 0) return '끝 층을 입력하면 소요가 계산됩니다.';
  const painted = paintedOf(value);
  const total = bandTotal(value, bands, i);
  const n = (bands[i].materials || []).length;
  const share = bandShare(value, bands, i);
  return `칠함 ${painted} × ${layers}층 = 소요 ${total}`
    + (n > 0 ? ` · 자재 ${n}매 → 매당 ${share}` : ' · 자재 미지정');
}

// 밴드(구간) 카드 하나 — 사용자가 입력하는 값은 **끝 층 하나**뿐이다.
function renderBand(value, bands, i) {
  const b = bands[i];
  const from = bandFrom(bands, i);
  const st = bandToState(b);
  const layers = bandLayers(bands, i);
  // 3상태를 **이미 있는 한 줄 안에서** 구분한다 — 새 영역·모달을 만들지 않는다.
  // 읽을 수 없는 값은 원문을 그대로 보여준다: 무엇을 고쳐야 하는지가 곧 값 자체다.
  let rangeTxt;
  if (st.state === 'ok') {
    rangeTxt = `${from}–${st.value}층 <b>${layers}층</b>`;
  } else if (st.state === 'blank') {
    rangeTxt = `${from}층 ~ <span class="tp-unknown-val">미정</span>`;
  } else {
    const shown = String(JSON.stringify(b.to));
    const clipped = shown.length > 24 ? `${shown.slice(0, 24)}…` : shown;   // 한 줄을 넘기지 않는다
    rangeTxt = `${from}층 ~ <span class="tp-unknown-val bad" title="저장된 끝 층 값 ${esc(shown)} 을(를) 숫자로 읽을 수 없습니다. 이 구간은 0층으로 세고, 다음 구간은 이 구간을 건너뛰어 계산합니다. 아래 [끝 층]에 숫자를 넣으면 고쳐집니다.">읽을 수 없는 값 ${esc(clipped)}</span>`;
  }
  return `<div class="tp-band${st.state === 'invalid' ? ' bad' : ''}" data-i="${i}" data-seq="${b.seq}">
    <div class="tp-band-l1">
      <span class="tp-band-range" title="시작 층은 앞 구간의 끝 + 1로 자동 결정됩니다 (편집 불가)">${rangeTxt}</span>
      <span class="tp-fld"><label>끝 층</label>
        <input class="glass-input mono tp-b-to" type="number" min="1" step="1" value="${st.state === 'ok' ? st.value : ''}"
          title="이 구간이 끝나는 층. 다음 구간은 여기 +1에서 시작합니다." /></span>
      <button type="button" class="tp-band-del" title="이 구간 삭제 (아래 구간이 당겨지고 자재는 각자 구간에 남습니다)">🗑</button>
    </div>
    <div class="tp-matchips">
      ${(b.materials || []).map((m, mi) => `<span class="tp-matchip" title="${esc(m)}">${esc(m)}<button type="button" class="tp-mat-del" data-i="${mi}" title="묶음에서 제거">✕</button></span>`).join('')}
      <span class="tp-matchip add tp-mat-add">＋ 자재</span>
    </div>
    <div class="tp-mat-addbox" style="display:none;">
      <span class="bp-ac-wrap"><input class="glass-input mono tp-mat-input" placeholder="자재 ID (적은 그대로 저장됩니다)" autocomplete="off" /></span>
      <button type="button" class="glass-page-btn tp-mat-ok">추가</button>
    </div>
    <div class="tp-band-calc" data-band-calc="${i}">${esc(bandCalcText(value, bands, i))}</div>
  </div>`;
}

function renderDoeDetail(row, planMode) {
  const v = String(row.value);
  const bands = Array.isArray(row.bands) ? row.bands : [];
  const knobs = Array.isArray(row.knobs) ? row.knobs : [];
  const planFields = planMode ? `
    <div class="tp-sec">
      <div class="tp-sec-h"><span>STACK 구간 · 자재</span>
        <button type="button" class="glass-page-btn tp-band-add" title="구간을 하나 더 추가합니다 (끝 층만 입력하면 됩니다)">+ 구간</button></div>
      ${bands.length === 0
        ? '<div class="tp-hint">구간이 없습니다. [+ 구간]으로 만드세요 — 첫 구간은 <b>1층</b>에서 시작합니다.</div>'
        : bands.map((b, i) => renderBand(v, bands, i)).join('')}
      <span class="tp-hint">스택은 <b>끊는 지점 목록</b>입니다. 구간마다 <b>끝 층</b>만 적으면 시작 층·층 수·소요는 자동으로 나옵니다
        (<span class="mono">1 / 15 / 16</span> = 1층, 2–15층, 16층).</span>
    </div>
    <div class="tp-sec">
      <div class="tp-sec-h"><span>knob (이 값의 DOE 조건)</span>
        <button type="button" class="glass-page-btn tp-knob-add">+ knob</button></div>
      <div class="tp-knobs">
        ${knobs.map((p, i) => `<span class="tp-knob" data-ki="${i}">
          <input class="tp-knob-k" placeholder="knob" value="${esc(p.k || '')}" />
          <span>=</span>
          <input class="tp-knob-v" placeholder="값" value="${esc(p.v || '')}" />
          <button type="button" class="tp-knob-del" title="삭제">✕</button></span>`).join('')}
      </div>
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
    const rowEl = node.querySelector('.tp-doe-row');
    // 행 클릭 = ① 선택 ② 브러시 전환 ③ 펼침 — 한 동작으로 셋 다. 한 번에 하나만 펼친다.
    rowEl.addEventListener('click', () => {
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
      // DOE는 값 행 자체다 — 구간·자재는 같은 행에 그대로 붙어 있어 이사가 필요 없다.
      if (S.openValue === v) S.openValue = nv;
    });
    detail.querySelector('.tp-d-color').addEventListener('change', e => {
      controller.updateLegendRow(v, { color: e.target.value });
    });
    detail.querySelector('.tp-d-desc').addEventListener('change', e => {
      controller.updateLegendRow(v, { desc: e.target.value.trim() });
    });
    detail.querySelector('.tp-doe-del').addEventListener('click', () => {
      if (!confirm(`값 '${v}'을(를) 삭제할까요? (격자에서 이 값이 지워지고 구간·자재도 함께 사라집니다)`)) return;
      const r = controller.deleteLegendRow(v);
      if (!r.ok) { showToast(r.error, 'warning'); return; }
      if (S.openValue === v) S.openValue = null;
    });

    if (!planMode) return;

    const addBtn = detail.querySelector('.tp-band-add');
    if (addBtn) addBtn.addEventListener('click', () => {
      const bands = bandsOf(v).map(cloneBand);
      // seq = max+1, 끝 층은 미입력. 미입력은 정렬에서 항상 뒤로 간다.
      bands.push({ seq: nextBandSeq(bands), to: '', materials: [] });
      if (commitBands(v, bands)) refreshMaterials();
    });

    detail.querySelectorAll('.tp-band').forEach(bandNode => {
      const i = Number(bandNode.dataset.i);

      bandNode.querySelector('.tp-b-to').addEventListener('change', e => {
        const bands = bandsOf(v).map(cloneBand);
        if (!bands[i]) return;
        // 입력도 **같은 판정기**를 통과한다. 여기서 따로 `Number()`를 쓰면 화면이 읽는 규칙과
        // 사용자가 만드는 값의 규칙이 갈린다(예: 종전 코드는 '7.5'를 조용히 7로 바꿔 저장했다).
        const st = bandToState({ to: e.target.value.trim() });
        if (st.state === 'invalid') {
          showToast('끝 층은 정수로 입력하세요.', 'warning'); renderDoeList(); return;
        }
        bands[i].to = st.state === 'ok' ? st.value : '';
        // 위치는 `to`를 따라가고 seq는 그대로 — 자재가 자기 구간에 남는 이유다.
        const sorted = sortBands(bands);
        const err = validateBands(sorted);
        if (err) { showToast(err, 'warning'); renderDoeList(); return; }
        if (commitBands(v, sorted)) refreshMaterials();
      });

      bandNode.querySelector('.tp-band-del').addEventListener('click', () => {
        const bands = bandsOf(v).map(cloneBand);
        bands.splice(i, 1);          // ⚠️ 남은 구간의 seq는 **재번호하지 않는다**
        if (commitBands(v, bands)) refreshMaterials();
      });

      bandNode.querySelectorAll('.tp-mat-del').forEach(btn => {
        btn.addEventListener('click', () => {
          const bands = bandsOf(v).map(cloneBand);
          if (!bands[i]) return;
          bands[i].materials.splice(Number(btn.dataset.i), 1);
          if (commitBands(v, bands)) refreshMaterials();
        });
      });

      const addChip = bandNode.querySelector('.tp-mat-add');
      const addBox = bandNode.querySelector('.tp-mat-addbox');
      if (addChip && addBox) {
        const input = addBox.querySelector('.tp-mat-input');
        const commit = () => {
          const id = String(input.value || '').trim();   // 원문 그대로가 정체다
          if (!id) return;
          const bands = bandsOf(v).map(cloneBand);
          if (!bands[i]) return;
          if (bands[i].materials.indexOf(id) >= 0) {
            showToast('이미 이 구간의 묶음에 있는 자재입니다.', 'warning'); return;
          }
          bands[i].materials.push(id);
          if (commitBands(v, bands)) refreshMaterials();
        };
        addChip.addEventListener('click', () => {
          addBox.style.display = 'flex';
          input.focus();
          attachAutocomplete(input, sourceNodeLabel(), val => { input.value = val; commit(); });
        });
        addBox.querySelector('.tp-mat-ok').addEventListener('click', commit);
        input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); commit(); } });
      }
    });

    // knob은 **값 층위**다 (구간별이 아니다).
    const knobAdd = detail.querySelector('.tp-knob-add');
    if (knobAdd) knobAdd.addEventListener('click', () => {
      commitKnobs(v, knobsOf(v).concat([{ k: '', v: '' }]));
    });
    detail.querySelectorAll('.tp-knob').forEach(kn => {
      const ki = Number(kn.dataset.ki);
      const patch = (field, val) => {
        const knobs = knobsOf(v).map(p => ({ ...p }));
        if (!knobs[ki]) return;
        knobs[ki][field] = val;
        commitKnobs(v, knobs);
      };
      kn.querySelector('.tp-knob-k').addEventListener('change', e => patch('k', e.target.value));
      kn.querySelector('.tp-knob-v').addEventListener('change', e => patch('v', e.target.value));
      kn.querySelector('.tp-knob-del').addEventListener('click', () => {
        const knobs = knobsOf(v).map(p => ({ ...p }));
        knobs.splice(ki, 1);
        commitKnobs(v, knobs);
      });
    });
  });
}

function cloneBand(b) {
  return { seq: b.seq, to: b.to, materials: Array.isArray(b.materials) ? b.materials.slice() : [] };
}

function sourceNodeLabel() {
  const st = stageOfTable(S.ctx.table);
  if (!st) return 'Wafer';
  return st.sourceKind === 'core' ? 'Wafer' : 'Tape';
}

// ── 렌더: 사용 자재 (자재 ID가 키, 이동 허브) ─────────────
//
// 사용자의 시점은 **자재**다: "이 테이프, 얼마 남았고 어디에 얼마나 썼나."
// 그래서 행의 단위는 (값, 구간)이 아니라 **자재 ID** 하나다. (값, 구간)은 사라지지 않고
// 그 자재를 소비한 **자리**로 행 안에 접혀 들어간다.
function materialRollup() {
  const st = stageOfTable(S.ctx.table);
  if (!st || S.ctx.depth > 0) return [];
  const byMat = new Map();   // 자재 ID -> { id, used, uses[] }
  S.legendRows.forEach(row => {
    const v = String(row.value);
    const bands = Array.isArray(row.bands) ? row.bands : [];
    bands.forEach((b, i) => {
      const mats = Array.isArray(b.materials) ? b.materials : [];
      if (mats.length === 0) return;
      const qty = bandShare(v, bands, i);   // 화면과 저장이 같은 함수를 쓴다 (단일 구현)
      mats.forEach(id => {
        if (!byMat.has(id)) byMat.set(id, { id, used: 0, uses: [] });
        const e = byMat.get(id);
        e.used += qty;
        e.uses.push({ value: v, color: row.color, seq: b.seq, from: bandFrom(bands, i), to: bandTo(b), qty });
      });
    });
  });
  // 자재 ID 순 — 목록이 편집 순서에 따라 튀지 않게 한다
  return [...byMat.values()].sort((a, b) => String(a.id).localeCompare(String(b.id)));
}

function useLabel(u) { return u.to === null ? `${u.from}층~?` : `${u.from}–${u.to}층`; }

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
    const av = availabilityOf(m.id);
    // 신뢰 불가는 **숫자를 보여주지 않는다** — 강등된 값을 확정값처럼 보이면 계획이 틀린다.
    const availHtml = (av.status === null || av.status === 'loading')
      ? '<span class="tp-unknown-val">…</span>'
      : (av.reliable
        ? `<b>${av.value}</b>`
        : `<span class="tp-unknown-val" title="${esc(av.reason + (av.value === null ? '' : ` (서버 원값 ${av.value})`))}">미상</span>`);
    const exists = srcTable ? S.matMapState.get(matMapCacheKey(srcTable, m.id)) : null;
    const mapChip = exists === true ? '<span class="tp-chip ok">맵 ✓</span>'
      : (exists === false ? '<span class="tp-chip warn">맵 없음</span>'
        : '<span class="tp-chip dim">맵 미상</span>');
    // "어디에 몇 개씩" — 이 자재를 소비한 (값, 구간)과 그 수량. 항상 펼쳐 둔다(읽기 무마찰).
    const uses = m.uses.map((u, ui) => `<span class="tp-use ${sel && sel === u.value ? 'on' : ''}"
        data-use-for="${esc(m.id)}" data-use-i="${ui}"
        title="DOE ${esc(u.value)} · ${esc(useLabel(u))} 에 ${u.qty}개 배정">
        <i style="background:${esc(u.color || '#6b7280')}"></i>${esc(u.value)}·${esc(useLabel(u))} <b>${u.qty}</b></span>`).join('');
    const on = !!sel && m.uses.some(u => u.value === sel);
    return `<div class="tp-mat-row ${on ? 'on' : ''}" data-id="${esc(m.id)}" title="클릭 = 이 자재의 맵 열기">
      ${S.flash.has(m.id) ? '<span class="tp-flash go"></span>' : ''}
      <div class="tp-mat-l1">
        <span class="tp-mat-id">${esc(m.id)}</span>
        <span class="tp-mat-qty">가용 ${availHtml} · 사용 <b data-mat-used="${esc(m.id)}">${m.used}</b></span>
        ${mapChip}
      </div>
      <div class="tp-uses">${uses}</div>
    </div>`;
  }).join('');

  box.innerHTML = `
    <div class="tp-mat-head"><b>📦 사용 자재 <span class="tp-chip">${mats.length}</span></b>
      <button type="button" class="glass-page-btn" id="tp-mat-refresh">↻ 가용 재조회</button></div>
    <div class="tp-mat-scroll">${rows}</div>
    <div class="tp-mat-hint">가용 = 서버 집계(총 − fail ∪ 전사) · 사용 = 칠한 셀 × 층 수를 자재 수로 나눈 합(올림) · 행 클릭 = 그 자재의 맵을 엽니다${
      srcTable
        ? ` · 대상 <b>${esc(srcTable)}</b>${srcDerived === 'fallback'
            ? ' <span class="tp-chip warn" title="stage 선언에서 유도하지 못해 하드코딩 폴백을 씁니다 — 서버에 명시 선언 요청됨">추정</span>'
            : ''}`
        : ' · <b class="tp-mat-nosrc">자재 맵 테이블 미상 — stage 선언 확인 필요</b>'
    }</div>`;

  box.querySelector('#tp-mat-refresh').addEventListener('click', () => refreshMaterials(true));
  box.querySelectorAll('.tp-mat-row').forEach(r => {
    r.addEventListener('click', () => openMaterial(r.dataset.id));
  });
  // 선택된 DOE를 쓰는 첫 자재를 시야로 (필터 금지 — 전체가 보여야 한다)
  const onRow = box.querySelector('.tp-mat-row.on');
  if (onRow) onRow.scrollIntoView({ block: 'nearest' });
  S.flash.clear();
}

// ── 자재 맵 왕복 ────────────────────────────────────────
async function openMaterial(id) {
  if (S.navBusy) return;
  const st = stageOfTable(S.ctx.table);
  const table = sourceTableOfStage(st);
  if (!table) { showToast('자재 맵 테이블을 알 수 없습니다 (stage 선언 확인 필요).', 'warning'); return; }
  S.navBusy = true;
  try {
    const metaValues = await materialMetaValues(table, id);
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

  // 맵 키가 곧 자재 ID의 표기다(자재 ID 원문이 맵 키로 해석돼 열렸으므로).
  const id = String(from.mapKey);
  const before = { avail: availableOf(id), exists: S.matMapState.get(matMapCacheKey(table, id)) };
  const entry = await getSourceSummary(id, true);
  const exists = await probeMaterialMap(table, id, true);
  const after = { avail: availableOf(id), exists };

  if (entry && entry.status === 'error') {
    showToast(`자재 ${id} 가용 재조회 실패 — 미상으로 표시합니다. [↻ 가용 재조회]로 다시 시도하십시오.`, 'warning');
  }
  if (before.avail !== after.avail || before.exists !== after.exists) S.flash.add(id);
  renderMaterialPane();
}

// 자재 목록의 가용·맵 유무 일괄 갱신.
async function refreshMaterials(force = false) {
  const seq = ++S.matSeq;
  const st = stageOfTable(S.ctx.table);
  const table = sourceTableOfStage(st);
  const mats = materialRollup();
  if (mats.length === 0) { renderMaterialPane(); return; }
  renderMaterialPane();
  await Promise.all(mats.map(async m => {
    await getSourceSummary(m.id, force);
    if (table) await probeMaterialMap(table, m.id, force);
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
  if (changed) {
    S.openValue = null;
    S.flash.clear();
  }
  if (controller.getLegend) S.legendRows = controller.getLegend();
  renderAll();
  if (changed) {
    refreshMaterials();
    // ★ 왕복 보상 — 복귀 직후 그 자재만 재조회
    if (info.returnedFrom) rewardAfterReturn(info.returnedFrom);
  }
}

// legend(값·설명·색·knobs·bands·브러시)가 바뀌었다.
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
  const planMode = !!stageOfTable(S.ctx.table) && S.ctx.depth === 0;
  elp.list.querySelectorAll('[data-count-for]').forEach(node => {
    node.textContent = doeLine2(node.getAttribute('data-count-for'), planMode);
  });
  if (S.openValue) {
    const bands = bandsOf(S.openValue);
    elp.list.querySelectorAll('[data-band-calc]').forEach(node => {
      const i = Number(node.getAttribute('data-band-calc'));
      if (bands[i]) node.textContent = bandCalcText(S.openValue, bands, i);
    });
  }
  if (elp.matPane && elp.matPane.style.display !== 'none') {
    const mats = materialRollup();
    const byId = new Map(mats.map(m => [m.id, m]));
    elp.matPane.querySelectorAll('[data-mat-used]').forEach(node => {
      const m = byId.get(node.getAttribute('data-mat-used'));
      if (m) node.textContent = m.used;
    });
    elp.matPane.querySelectorAll('[data-use-for]').forEach(node => {
      const m = byId.get(node.getAttribute('data-use-for'));
      const u = m && m.uses[Number(node.getAttribute('data-use-i'))];
      const b = u && node.querySelector('b');
      if (b) b.textContent = u.qty;
    });
  }
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
