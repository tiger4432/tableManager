"""Universal Transfer Plan (M2) — 전사(轉寫) 프레임워크: stage 선언 로더 + 가용 엔진 + 계획 검증.

[역할] 모든 전사 단계(DT: core→tape, bonding: tape→base, …)를 전사 프리미티브
`(stage, 타깃 맵 페인팅, assignments)`의 인스턴스로 다룬다. 신규 단계는
`server/config/transfer_plan_config.json`(사용자 config, gitignored)의 stage 선언만으로
추가된다 — 코드에 실테이블명 하드코딩 금지.

[계획 모델 v2 — "계획 = 지금 열어 편집 중인 그 맵" (사용자 확정 2026-07-26)]
계획이라는 **별도 개체는 존재하지 않는다**. `bonding_map`을 열어 편집하면 그게 BONDING
PLAN이고 `dt_map`을 열면 DT PLAN이다. 따라서:
- **계획 정체성 = `(ref_table, map_key)`** — `plan_id`도 계획 헤더 테이블도 없다.
- **stage는 유도된다** — `stages.*.target_map.table`의 역인덱스(`stage_of_table`).
  사용자가 stage를 고르는 동작은 어디에도 없다.
- **페인팅 결과 = 대상 맵 자신의 셀** — 계획 맵 사본(`transfer_plan_map`)은 폐기됐고,
  값 분포는 대상 맵 테이블에서 직접 group-by한다(`_painted_values`).
- **DOE 행의 단위는 `(값, STACK 구간)`** — 한 값이 여러 구간을 가질 수 있다(사용자 스케치:
  `A|H1~H2`, `A|H2~H3`, `B|H1~H3`). 따라서 저장 키는
  **`ref_table|map_key|doe_value|band_seq`** 이며, 소스 묶음은 그 **구간 아래에** 붙는다
  (구간마다 다른 자재 묶음이 가능해야 한다).
- **`band_seq`는 키, `stack_band`는 라벨이다.** 구간 표기는 자유 텍스트라(`1`/`2-11`/`H1~H2`)
  키에 넣을 수 없다 — ①bk 조립이 구분자 `|`를 이스케이프하지 않아 값에 `|`가 섞이면 키가
  모호해지고(`crud._build_composite_key`) ②키 컬럼이 바뀌면 행이 **re-key**되므로
  (`crud.py` 업데이트 경로) 라벨을 고치는 순간 DOE 행의 정체가 바뀌어 하위 자재 행이
  고아가 된다. 그래서 정체는 **클라가 부여하는 정수 서수(`band_seq`)** 가 지고, 사람이 읽는
  표기는 비키 컬럼(`stack_band`)에 둔다 — 라벨을 자유롭게 고쳐도 묶음이 따라온다.
- **값 단위 속성은 `map_split_registry`가 이미 갖는다** — `split_desc`(설명)·`color`는 동일
  키 앞부분(`ref_table|map_key|value`)으로 1:N 조인된다. `map_doe`에 중복 저장하지 않는다.
- **소스는 묶음(pool)** — 한 구간에 여러 매가 붙으므로(사용자 확정: "한 매당 500칩이면
  4매 묶어서 투입") 소스 테이블의 bk에 **소스 차원**이 들어간다. 매별 소요는 지정 대상이
  아니라 구간 총 소요의 균등 배분이다. 구 `doe_layer`의 "층마다 소스 1개" 차원은 소멸했다.

[경계 계약 — 총괄 고정]
- GET /api/transfer-plan/stages           : 선언 stage 목록 + 역할 연결 상태
- GET /api/transfer-plan/source-summary   : 단계별 소스 가용
  `{identity, stage, source_kind, sources, chips{total, fail_breakdown{...}, transferred,
    remaining}, history, warnings}` + tape 소스면 `by_core` 동봉(집계만 — 칩 좌표 목록 금지)
- GET /api/transfer-plan/validate?ref_table=&map_key=  : 계획 경고 목록
- M1 `GET /api/bonding-plan/core-summary`는 외부 계약 불변 — core-kind 소스 가용의
  인스턴스로 내부 통합(본 모듈이 `bonding_plan.get_core_summary`를 어댑터로 감싼다).

[키 파싱 금지 — v1에서 승계한 불변식] 서버는 `map_key`를 **파싱하지 않는다**. 컬럼 equality
조회에만 쓰고, 맵 셀 조회 시의 분해는 `table_config.map_key_columns` 선언에 따른 공용 규칙
(`map_overlay.build_key_filters`) 하나로만 수행한다. 모듈마다 다른 파싱을 도입하지 말 것.

[stage 어휘] 선언된 stage 이름의 **유일한 정본은 이 config의 `stages` 키**이며
`GET /api/transfer-plan/stages`가 그것을 그대로 노출한다. 미선언 stage는 조용히 매핑하지
않고 `stage_unknown`(effect: validation_skipped)으로 표면화한다.

[stage source 선언 2형]
1. `"source_config_ref": "bonding_plan"` — M1 `bonding_plan_config.json`을 소스 역할
   바인딩으로 재사용(하위호환 경로). core-kind 가용 = M1 집계의 재성형(reshape).
2. inline `"source": {...}` — 일반 역할 엔진:
   - `total_chips` / `transfer_log`(기전사 로그, distinct 칩) / `process_history`(M1 규율)
   - `origin_log`: 칩 단위 출신 귀속(tape 소스의 핵심 — dt_log: 테이프 좌표↔코어 좌표)
   - `fail_sources.{name}`: fail 원천. `frame: "origin"`이면 출신(core) 프레임 fail을
     origin_log 조인으로 타깃(tape) 좌표에 투영("테이프에도 불량 섞임" 처리의 핵심),
     `frame: "self"`면 자기 identity 직접 카운트(M1 맵 모드와 동일).

[align 규율 — 정렬의 유일한 근거는 `wafer_map_metadata`다 (사용자 확정 2026-07-26)]
fail 원천의 소스 프레임→canonical(core) 프레임 사상은 **두 맵 메타의 델타에서 유도**한다.
config의 `fail_sources[].align` 선언 레이어는 제거됐다 — 계측으로 잰 어긋남도 메타에 적는다.
투영 조인은 좌표 비교이므로 **변환 미해결 시 raw 좌표로 조용히 계산하지 않고 명시 실패**
(`connected(align_unavailable)`, 카운트 0) — QA F2 취지.
변환 구현은 `map_overlay.resolve_map_transform` **하나뿐**이다(오버레이와 공유). 구
`bonding_plan.make_align_transform`은 저장 좌표의 바운딩박스 규약을 반영하지 않아 삭제됐다.

[스냅샷 규율] config는 요청(작업) 경계에서 1회 로드해 전 구간에 인자로 전달한다.
[확장성] 응답은 집계만(칩 좌표 목록 금지). 좌표 페치는 내부 연산 한정 + 하드캡.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

import paths  # single override point (ASSY_DATA_ROOT)
CONFIG_PATH = paths.config_path("transfer_plan_config.json")

# ---- 하드캡 (무제한 로드 금지 — 1,000만 행 규율) ----
MAX_ORIGIN_POINTS = 100_000   # 타깃(테이프) 1장의 origin_log 칩 페치 상한 (내부 연산용)
MAX_FAIL_POINTS = 100_000     # 코어 1장의 fail 좌표 페치 상한
MAX_BY_CORE = 500             # by_core 분해 응답 상한 (초과분 절단 + 경고)
CORE_ID_SEP = "|"             # by_core.core_id 합성 분리자 (lot|slot — bk 관례 '_' 모호 회피)
MAX_DOE_PER_PLAN = 500        # validate가 다루는 DOE 정의 상한
MAX_PLAN_VALUES = 1000        # validate의 페인팅 값 group-by 상한
MAX_SOURCES_PER_DOE = 64      # DOE 1건이 묶을 수 있는 자재(소스) 행 상한
MAX_REGION_CELLS = 100_000    # 소스 사용 영역 셀 상한 (내부 연산용 — 응답에 싣지 않는다)

M1_SOURCE_REFS = ("bonding_plan",)   # source_config_ref 허용 값

# validate 경고 타입 (계약)
WARN_QTY_SHORTAGE = "qty_shortage"
WARN_LAYER_RANGE_INVALID = "layer_range_invalid"
WARN_LAYER_COVERAGE_GAP = "layer_coverage_gap"
WARN_UNDEFINED_DOE_VALUE = "undefined_doe_value"
WARN_DOE_VALUE_UNPAINTED = "doe_value_unpainted"
WARN_SOURCE_FAIL_CHIPS = "source_fail_chips"
WARN_SOURCE_HISTORY_FAIL = "source_history_fail"
WARN_STAGE_UNKNOWN = "stage_unknown"
WARN_SOURCE_UNRESOLVED = "source_unresolved"
# [QA F1] 역할 강등의 표면화 — "조용한 과대 산출" 차단
WARN_SOURCE_DEGRADED = "source_degraded"
WARN_AVAILABILITY_UNRELIABLE = "availability_unreliable"
# [QA F4] 여러 DOE가 한 소스를 나눠 쓸 때의 합산 초과배정
WARN_SOURCE_OVERALLOCATED = "source_overallocated"
# [QA F2] 하드캡 절단의 표면화 (조용한 오답 금지 — F1과 동일 계열)
WARN_RESULT_TRUNCATED = "result_truncated"
# [QA N1] remaining 음수 = 원천 간 모집단 불일치 (불변식 위반)
WARN_NEGATIVE_REMAINING = "negative_remaining"
EFFECT_POPULATION_MISMATCH = "population_mismatch"

# 강등 효과 분류 (역할별로 remaining에 미치는 방향이 다르다)
EFFECT_REMAINING_OVERSTATED = "remaining_overstated"   # 감산항(fail/기전사) 과소 → remaining 과대
EFFECT_TOTAL_UNKNOWN = "total_unknown"                 # 분모 자체가 불명 → remaining 무의미
EFFECT_BY_CORE_DEGRADED = "by_core_degraded"           # by_core 분해만 열화 (remaining 무관)
EFFECT_HISTORY_INCOMPLETE = "history_incomplete"       # 이력만 누락 (remaining 무관)


# ---------------------------------------------------------------------------
# config 로더 (파일 경계 스냅샷 — 요청당 1회)
# ---------------------------------------------------------------------------

def load_transfer_plan_config(path: str = None) -> dict:
    """transfer_plan_config.json 로드. 없거나 손상 시 {} (부분 가동 — 에러 아님)."""
    p = path or CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            logger.warning("[TransferPlan] config root is not an object — ignored: %s", p)
            return {}
        return raw
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("[TransferPlan] failed to load config %s: %s", p, e)
        return {}


def get_stages(cfg: dict) -> dict:
    stages = cfg.get("stages")
    return stages if isinstance(stages, dict) else {}


def _valid_binding(src) -> bool:
    """{table, columns} 최소 형태 검증 (bonding_plan._valid_source와 동일 규약)."""
    return (
        isinstance(src, dict)
        and isinstance(src.get("table"), str) and src.get("table")
        and isinstance(src.get("columns"), dict)
    )


def _resolve(src_cfg: dict, required: tuple):
    """바인딩 → (model, {역할키: ORM 컬럼}). 실패 시 (None, None) — missing 부분 가동."""
    import bonding_plan
    if not _valid_binding(src_cfg):
        return None, None
    return bonding_plan._resolve_model_columns(src_cfg, required=required)


# ---------------------------------------------------------------------------
# stage 목록 + 역할 연결 상태 (데이터 쿼리 없음 — 바인딩 해석만)
# ---------------------------------------------------------------------------

def _binding_status(src_cfg, required=("lot", "slot")) -> str:
    if not _valid_binding(src_cfg):
        return "missing"
    model, cols = _resolve(src_cfg, required)
    return "missing" if model is None else "connected"


def _stage_role_statuses(stage_cfg: dict) -> dict:
    """stage의 소스 역할별 연결 상태 (모델·컬럼 해석만 — 행 조회 없음)."""
    import bonding_plan
    ref = stage_cfg.get("source_config_ref")
    if ref in M1_SOURCE_REFS:
        bp_cfg = bonding_plan.load_bonding_plan_config()
        sources = (bp_cfg.get("sources") or {})
        return {
            "total_chips": _binding_status(sources.get("total_chips")),
            "transfer_log": _binding_status(sources.get("used_chips")),
            "process_history": _binding_status(sources.get("process_history")),
            "defect": _binding_status(sources.get("defect")),
            "eds_fail": _binding_status(sources.get("eds_fail")),
        }

    source = stage_cfg.get("source") or {}
    out = {
        "total_chips": _binding_status(source.get("total_chips")),
        "transfer_log": _binding_status(source.get("transfer_log")),
        "process_history": _binding_status(source.get("process_history")),
        "origin_log": _binding_status(source.get("origin_log")),
    }
    if _valid_binding(source.get("origin_area_map")):
        out["origin_area_map"] = _binding_status(source.get("origin_area_map"))
    fail_sources = source.get("fail_sources") or {}
    if isinstance(fail_sources, dict):
        for name, fs in fail_sources.items():
            out[str(name)] = _binding_status(fs)
    return out


def _plan_store_statuses(cfg: dict) -> dict:
    """계획 저장소 역할 상태.

    [v2 모델] `plan`(헤더)·`map`(계획 맵 사본) 역할은 **폐기**됐다 — 계획 정체가
    `(ref_table, map_key)`이고 페인팅 결과가 곧 대상 맵 자신의 셀이라 사본이 존재할
    이유가 없다. 남는 것은 DOE 정의와 그 소스 묶음뿐이다.
    """
    store = cfg.get("plan_store") or {}
    out = {
        "doe": _binding_status(store.get("doe"),
                               required=("ref_table", "map_key", "doe_value", "band_seq")),
    }
    # 소스 묶음(pool)은 선택 — 선언됐을 때만 상태를 노출한다(미선언은 결함이 아님)
    if _valid_binding(store.get("doe_source")):
        out["doe_source"] = _binding_status(
            store.get("doe_source"),
            required=("ref_table", "map_key", "doe_value", "band_seq",
                      "source_lot", "source_slot"))
    if _valid_binding(store.get("source_region")):
        out["source_region"] = _binding_status(
            store.get("source_region"),
            required=("ref_table", "map_key", "source_lot", "source_slot", "x", "y"))
    return out


def stage_of_table(cfg: dict, ref_table: str):
    """맵 테이블 → stage **역인덱스**. 미선언 테이블이면 None.

    [v2 모델의 핵심] 사용자는 stage를 고르지 않는다 — `bonding_map`을 열면 bonding,
    `dt_map`을 열면 dt다. 이 매핑은 이미 `stages.*.target_map.table`에 선언돼 있으므로
    새 계약이 아니라 **기존 선언의 역방향 조회**다.
    """
    if not ref_table:
        return None
    for name, stage_cfg in get_stages(cfg).items():
        if not isinstance(stage_cfg, dict):
            continue
        if ((stage_cfg.get("target_map") or {}).get("table")) == ref_table:
            return name
    return None


def list_stages(cfg: dict) -> dict:
    """GET /api/transfer-plan/stages 응답 본문."""
    stages_out = []
    for name, stage_cfg in get_stages(cfg).items():
        if not isinstance(stage_cfg, dict):
            continue
        stages_out.append({
            "name": name,
            "description": stage_cfg.get("description"),
            "source_kind": stage_cfg.get("source_kind"),
            "target_kind": stage_cfg.get("target_kind"),
            "target_map": stage_cfg.get("target_map") or {},
            "roles": _stage_role_statuses(stage_cfg),
        })
    return {"stages": stages_out, "plan_store": _plan_store_statuses(cfg)}


# ---------------------------------------------------------------------------
# 소스 가용 엔진
# ---------------------------------------------------------------------------

def _status_is_degraded(status) -> bool:
    """역할 상태 문자열이 '강등'인가.

    정상: "connected", "connected(aligned:180)" 등 align 마커만 붙은 경우.
    강등: "missing", "unavailable(...)", "connected(align_unavailable)", "connected(area_only)".
    """
    if not status or status == "connected":
        return False
    if status.startswith("connected("):
        return ("align_unavailable" in status) or ("area_only" in status)
    return True   # missing / unavailable(...) 등


def _degradation_effect(role: str, fail_roles: set) -> str:
    """강등된 역할이 집계에 미치는 효과를 분류한다."""
    if role == "total_chips":
        return EFFECT_TOTAL_UNKNOWN
    if role == "process_history":
        return EFFECT_HISTORY_INCOMPLETE
    if role == "origin_area_map":
        return EFFECT_BY_CORE_DEGRADED
    # transfer_log / origin_log / fail 원천 → 감산항 과소 → remaining 과대
    if role == "transfer_log" or role == "origin_log" or role in fail_roles:
        return EFFECT_REMAINING_OVERSTATED
    return EFFECT_REMAINING_OVERSTATED


def assess_degradation(statuses: dict, fail_roles: set):
    """[QA F1] 역할 상태 → (강등 경고 목록, remaining 신뢰 여부, total 신뢰 여부).

    "부분 가동"은 조용해선 안 된다 — 역할이 무너져 감산항이 0이 되면 remaining이 **과대**로
    부푸는데, 이를 sources 문자열에만 적어두면 소비자(클라·validate)가 정상으로 오인한다.
    따라서 강등은 반드시 warnings에 명시 항목으로 싣고, remaining 자체의 신뢰도를 값으로
    표현한다(신뢰 불가 시 remaining=None — 소비자가 분기 없이는 표시조차 못 하게).
    """
    warnings_out = []
    remaining_reliable = True
    total_reliable = True

    for role in sorted(statuses.keys()):
        status = statuses[role]
        if not _status_is_degraded(status):
            continue
        effect = _degradation_effect(role, fail_roles)
        if effect == EFFECT_TOTAL_UNKNOWN:
            total_reliable = False
            remaining_reliable = False
            detail = f"역할 '{role}' 강등({status}) — 총 칩 수를 알 수 없어 remaining을 산출할 수 없음"
        elif effect == EFFECT_REMAINING_OVERSTATED:
            remaining_reliable = False
            detail = (f"역할 '{role}' 강등({status}) — 해당 집계가 누락되어 "
                      f"remaining이 실제보다 과대일 수 있음")
        elif effect == EFFECT_BY_CORE_DEGRADED:
            detail = f"역할 '{role}' 강등({status}) — by_core 분해만 열화(remaining 영향 없음)"
        else:
            detail = f"역할 '{role}' 강등({status}) — 이력 일부 누락(remaining 영향 없음)"
        warnings_out.append({
            "type": WARN_SOURCE_DEGRADED,
            "role": role,
            "status": status,
            "effect": effect,
            "detail": detail,
        })
    return warnings_out, remaining_reliable, total_reliable


def build_chips_block(total, fail_breakdown, transferred, remaining,
                      remaining_reliable, total_reliable):
    """chips 블록 생성 — 신뢰 불가 시 remaining을 None으로 내린다(오표시 구조적 차단).

    반환: (chips dict, 추가 경고 리스트)

    remaining_upper_bound는 **total이 신뢰 가능할 때만** 싣는다. total까지 강등된 경우의
    계산값은 상한이 아니라 무의미한 값이므로 상한이라 칭하지 않는다.

    [QA N1 불변식] `remaining < 0`은 물리적으로 불가능하다 — 나오면 원천 간 **모집단
    불일치**(마스크 밖 좌표, 중복 행, 프레임 불일치, 백필 과도기 등)라는 뜻이다. 전 역할이
    connected여도 수치는 틀린 것이므로 신뢰 불가로 강등하고 표면화한다. 이 3줄이 원인별
    개별 수정 없이 계열 전체를 막는다.
    """
    extra_warnings = []
    if remaining is not None and remaining < 0:
        remaining_reliable = False
        extra_warnings.append({
            "type": WARN_NEGATIVE_REMAINING,
            "effect": EFFECT_POPULATION_MISMATCH,
            "computed": remaining,
            "detail": (f"remaining이 음수({remaining}) — 감산항이 총칩을 초과했다. "
                       f"원천 간 모집단 불일치(마스크 밖 좌표·중복 행·프레임 불일치·백필 "
                       f"과도기)를 의심해야 하며 이 수치는 신뢰할 수 없다"),
        })

    chips = {
        "total": total,
        "fail_breakdown": fail_breakdown,
        "transferred": transferred,
        "remaining": remaining if remaining_reliable else None,
        "remaining_reliable": remaining_reliable,
    }
    if not remaining_reliable and total_reliable:
        # 감산항만 과소하므로 계산값은 진짜 remaining의 상한이다.
        # (음수 케이스는 상한으로서도 무의미하므로 싣지 않는다 — 진짜 잔여는 0 이상이다.)
        if not (remaining is not None and remaining < 0):
            chips["remaining_upper_bound"] = remaining
    return chips, extra_warnings


def load_source_region(db, cfg: dict, ref_table: str, map_key: str,
                       source_lot: str, source_slot: str):
    """[②] 계획의 '이 소스에서 쓰기로 한 영역'을 셀 집합으로 로드한다.

    ⚠️ **휴면 중 (총괄 지시로 보류)**. `plan_store.source_region` 바인딩이 라이브 config에
    선언돼 있지 않아 이 경로는 항상 None을 반환한다. 배선 누락 결함이 아니다.
    v2 모델에 맞춰 **키만 `(ref_table, map_key, source_lot, source_slot)`로 이동**했다
    (구 키 `plan_id`는 소멸). 살릴지 여부는 자재 맵 왕복 UX 확정 후 결정한다.

    자유 페인팅 결과라 rect로는 표현되지 않으므로 셀 집합 테이블에서 집합으로 읽는다
    (rect는 UX 보조일 뿐 저장 정본이 아니다).
    반환: set[(x, y)] 또는 None(바인딩 미선언/미해석 — 영역 스코프 없음).
    """
    store = (cfg.get("plan_store") or {}).get("source_region")
    model, cols = _resolve(store, required=("ref_table", "map_key",
                                            "source_lot", "source_slot", "x", "y"))
    if model is None:
        return None
    try:
        rows = (db.query(cols["x"], cols["y"])
                .filter(cols["ref_table"] == ref_table,
                        cols["map_key"] == map_key,
                        cols["source_lot"] == source_lot,
                        cols["source_slot"] == source_slot)
                .limit(MAX_REGION_CELLS).all())
    except Exception as e:
        logger.warning("[TransferPlan] source_region query failed (%s/%s/%s/%s): %s",
                       ref_table, map_key, source_lot, source_slot, e)
        return None
    if len(rows) >= MAX_REGION_CELLS:
        logger.warning("[TransferPlan] source_region hit hard cap (%d)", MAX_REGION_CELLS)
    return {(int(x), int(y)) for (x, y) in rows if x is not None and y is not None}


def _region_block(total_pts, fail_sets: dict, used_set: set, region: set) -> dict:
    """영역 내 가용 집계 — 전체 집계와 동일한 합집합 의미론을 영역으로 좁힌 것."""
    in_region_total = {p for p in total_pts if p in region} if total_pts is not None else None
    fb = {}
    fail_union = set()
    for name, s in fail_sets.items():
        if s is None:
            fb[name] = None
            continue
        hit = {p for p in s if p in region}
        fb[name] = len(hit)
        fail_union |= hit
    used_hit = {p for p in used_set if p in region}
    block = {
        "cells": len(region),
        "total": len(in_region_total) if in_region_total is not None else None,
        "fail_breakdown": fb,
        "transferred": len(used_hit),
    }
    if in_region_total is not None:
        block["remaining"] = len(in_region_total) - len(fail_union | used_hit)
    else:
        block["remaining"] = None
    return block


def _core_region_counts(db, bp_cfg: dict, lot: str, slot: str, region: set):
    """[②] core-kind(M1 위임) 소스의 영역 내 집계.

    M1 `get_core_summary`는 rect만 받으므로 셀 집합을 넘길 수 없다. M1 config의 역할
    바인딩을 M2 어댑터 형태로 읽어 좌표 집합을 직접 구성한다(정렬은 M1과 동일하게 메타
    델타에서 유도해 canonical 사상 후 교차).

    ⚠️ 어댑터의 `fail_sources`는 **`bonding_plan.CANONICAL_FRAME_ROLES`와 같은 순서**로
    쌓는다 — `_canonical_origin_meta`가 이 순서로 canonical 프레임을 고르므로, 순서가
    다르면 M1 `get_core_summary`와 다른 프레임을 기준 삼아 두 경로의 수치가 갈린다.
    `frame`을 "self"로 두면 canonical 후보가 하나도 없어 dst 메타가 None이 되고, 그러면
    정렬이 통째로 identity로 떨어진다(조용한 오답).
    """
    import bonding_plan

    sources = (bp_cfg.get("sources") or {})
    adapter = {
        "identity": bp_cfg.get("core_identity") or {"compose": ["lot", "slot"]},
        "map_metadata": bp_cfg.get("map_metadata"),
        "fail_sources": {
            k: dict(sources[k], frame="origin")
            for k in bonding_plan.CANONICAL_FRAME_ROLES
            if _valid_binding(sources.get(k))
        },
    }

    # total 좌표
    total_pts = None
    src = sources.get("total_chips")
    model, cols = _resolve(src, required=("lot", "slot"))
    if model is not None and "x" in cols and "y" in cols:
        pts, _tr = _fetch_pairs(db, cols, [cols["lot"] == lot, cols["slot"] == slot],
                                cap=MAX_REGION_CELLS, tag="region:total")
        total_pts = set(pts)

    # fail 좌표 (align 적용 — canonical 프레임)
    fail_sets = {}
    for name in ("defect", "eds_fail"):
        fs = sources.get(name)
        model, cols = _resolve(fs, required=("lot", "slot"))
        if model is None or "x" not in cols or "y" not in cols:
            fail_sets[name] = None
            continue
        pts, _mk, _tr = _canonical_fail_set(db, adapter, fs, cols, lot, slot)
        fail_sets[name] = pts   # None이면 align 불가 → 영역 집계도 미상

    # 기전사 좌표
    used_set = set()
    src = sources.get("used_chips")
    model, cols = _resolve(src, required=("lot", "slot"))
    if model is not None and "x" in cols and "y" in cols:
        pts, _tr = _fetch_pairs(db, cols, [cols["lot"] == lot, cols["slot"] == slot],
                                distinct=True, cap=MAX_REGION_CELLS, tag="region:used")
        used_set = set(pts)

    return _region_block(total_pts, fail_sets, used_set, region)


def _reshape_m1_summary(m1: dict, stage_name: str, stage_cfg: dict) -> dict:
    """M1 core-summary(계약 §C) → M2 공통 형태로 재성형 (core-kind 가용의 내부 통합)."""
    chips = m1.get("chips") or {}
    src = m1.get("sources") or {}
    statuses = {
        "total_chips": src.get("total_chips", "missing"),
        "transfer_log": src.get("used_chips", "missing"),
        "process_history": src.get("process_history", "missing"),
        "defect": src.get("defect", "missing"),
        "eds_fail": src.get("eds_fail", "missing"),
    }
    # [QA F1] core-kind 경로도 동일한 강등 노출을 갖는다 — 같은 규율로 표면화한다.
    deg_warnings, remaining_reliable, total_reliable = assess_degradation(
        statuses, fail_roles={"defect", "eds_fail"})
    chips_block, inv_warnings = build_chips_block(
        total=chips.get("total", 0),
        fail_breakdown={
            "defect": chips.get("defect", 0),
            "eds_fail": chips.get("eds_fail", 0),
        },
        transferred=chips.get("used", 0),
        remaining=chips.get("remaining", 0),
        remaining_reliable=remaining_reliable,
        total_reliable=total_reliable,
    )
    return {
        "identity": m1.get("identity"),
        "stage": stage_name,
        "source_kind": stage_cfg.get("source_kind"),
        "sources": statuses,
        "chips": chips_block,
        "history": m1.get("history") or [],
        "warnings": deg_warnings + inv_warnings + (m1.get("warnings") or []),
    }


def _fetch_pairs(db, cols, filters, distinct=False, cap=MAX_FAIL_POINTS, tag=""):
    """(x,y) 좌표 페치. 반환: (좌표 리스트, 캡 도달 여부).

    [QA F2] 캡 도달을 **호출자에게 반환**한다 — 로그로만 남기면 절단된 오답이 정상 응답과
    구별 불가해진다(total은 count()라 절단되지 않아 분자·분모의 모집단이 어긋난다).
    """
    q = db.query(cols["x"], cols["y"]).filter(*filters)
    if distinct:
        q = q.distinct()
    pts = q.limit(cap).all()
    truncated = len(pts) >= cap
    if truncated:
        logger.warning("[TransferPlan] %s point fetch hit hard cap (%d) — counts truncated", tag, cap)
    return [(int(x), int(y)) for (x, y) in pts if x is not None and y is not None], truncated


def _origin_map_id(source_cfg, origin_lot, origin_slot) -> str:
    identity_cols = (source_cfg.get("identity") or {}).get("compose") or ["lot", "slot"]
    vals = {"lot": origin_lot, "slot": origin_slot}
    return "_".join(str(vals.get(k, "")) for k in identity_cols)


def _canonical_origin_meta(db, source_cfg, origin_lot, origin_slot,
                           cache: dict = None, meta_cache: dict = None):
    """출신(core) 프레임의 **canonical 맵 메타**를 로드한다.

    canonical = origin_log의 `(origin_x, origin_y)`가 사는 프레임, 즉 코어 웨이퍼 자신의
    맵이다. 좌표를 바인딩한 **첫** `frame == "origin"` 원천(config 선언 순서 — 라이브는
    defect = core_defect_map이 먼저다)이 기준을 정의하며, 그 원천의 메타가 없으면 None을
    돌려준다. **뒤 원천으로 넘어가지 않는다.**

    ⚠️ 넘어가면 회전된 계측 맵이 스스로 기준을 참칭한다. 그러면 소스 == 기준이라 변환이
    identity로 떨어지고, 상태는 `connected`인 채 fail 투영이 통째로 빠진다(조용한 과소
    집계). 기준을 모르면 모른다고 해야 한다 — 호출자가 align_unavailable로 표면화한다.

    격자 규격만이 아니라 메타 전체가 필요하다 — 정렬은 회전·면·y반전·start·치수·phys 전부의
    델타에서 유도되므로, 치수만 넘기면 나머지 축의 차이가 조용히 무시된다.
    """
    if cache is not None and (origin_lot, origin_slot) in cache:
        return cache[(origin_lot, origin_slot)]

    import bonding_plan
    map_id = _origin_map_id(source_cfg, origin_lot, origin_slot)
    meta = None
    for fs in (source_cfg.get("fail_sources") or {}).values():
        if not _valid_binding(fs):
            continue
        if (fs.get("frame") or "origin") != "origin":
            continue
        cols = fs.get("columns") or {}
        if "x" not in cols or "y" not in cols:
            continue      # 좌표가 없는 원천은 프레임을 정의할 수 없다
        meta = bonding_plan.load_map_meta(db, source_cfg, fs["table"], map_id, meta_cache)
        break
    if cache is not None:
        cache[(origin_lot, origin_slot)] = meta
    return meta


def _canonical_fail_set(db, source_cfg, fail_cfg, cols, origin_lot, origin_slot,
                        grid_cache: dict = None, meta_cache: dict = None):
    """출신(core) 1장의 fail 좌표를 canonical 프레임 set으로 반환.

    반환: (set[(x,y)], align_marker|None, truncated) — 변환 미해결이면
    (None, "align_unavailable", False).
    """
    import bonding_plan
    import map_overlay

    filters = [cols["lot"] == origin_lot, cols["slot"] == origin_slot]
    fail_values = fail_cfg.get("fail_values")
    if fail_values and "val" in cols:
        filters.append(cols["val"].in_([str(v) for v in fail_values]))

    map_id = _origin_map_id(source_cfg, origin_lot, origin_slot)
    src_meta = bonding_plan.load_map_meta(db, source_cfg, fail_cfg["table"], map_id, meta_cache)
    dst_meta = _canonical_origin_meta(db, source_cfg, origin_lot, origin_slot,
                                      grid_cache, meta_cache)
    if src_meta is not None and dst_meta is None:
        # [비대칭 지식] 이 맵의 프레임은 아는데 기준 프레임을 모른다. 둘 다 모르면
        # identity가 성립하지만(등록 누락), 한쪽만 알 때 identity로 가정할 근거는 없다.
        logger.warning("[TransferPlan] canonical origin frame unregistered while '%s' declares "
                       "its own (%s) — refusing to assume identity",
                       fail_cfg.get("table"), map_id)
        return None, "align_unavailable", False
    try:
        transform, align, _origin, _note = map_overlay.resolve_map_transform(src_meta, dst_meta)
    except ValueError as ve:
        # 치수 불일치·phys 미등록 등 — 조용히 어긋난 좌표를 쓰지 않고 명시 실패로 강등한다.
        logger.warning("[TransferPlan] frame transform unavailable (%s/%s): %s",
                       fail_cfg.get("table"), map_id, ve)
        return None, "align_unavailable", False
    marker = map_overlay.align_status_label(align)

    pts, truncated = _fetch_pairs(db, cols, filters, cap=MAX_FAIL_POINTS,
                                  tag=f"fail:{fail_cfg.get('table')}")
    if transform:
        return {transform(x, y) for (x, y) in pts}, marker, truncated
    return set(pts), marker, truncated


def _collect_history(db, source_cfg, lot, slot):
    """process_history 역할 — M1 규율 그대로: 최근 50건 시간 오름차순 + result fail 경고."""
    import bonding_plan

    src = (source_cfg or {}).get("process_history")
    history, warnings_out = [], []
    if not _valid_binding(src):
        return "missing", history, warnings_out
    model, cols = _resolve(src, required=("lot", "slot"))
    if model is None:
        return "missing", history, warnings_out
    try:
        q = db.query(model).filter(cols["lot"] == lot, cols["slot"] == slot)
        if "time" in cols:
            q = q.order_by(cols["time"].desc())
        rows = q.limit(bonding_plan.HISTORY_LIMIT).all()
        rows.reverse()

        col_names = src["columns"]
        fail_values = set((source_cfg.get("warnings") or {}).get("result_fail_values") or [])
        for row in rows:
            def _get(role_key):
                name = col_names.get(role_key)
                return getattr(row, name, None) if name else None

            knobs_raw = _get("knobs")
            knobs = knobs_raw
            if isinstance(knobs_raw, str) and knobs_raw.strip():
                try:
                    knobs = json.loads(knobs_raw)
                except Exception:
                    knobs = knobs_raw  # 파싱 실패 → raw 폴백 (에러 아님 — M1 규율)

            entry = {"step": _get("step"), "eqp": _get("eqp"), "result": _get("result"),
                     "time": _get("time"), "recipe": _get("recipe"), "knobs": knobs}
            history.append(entry)
            if fail_values and entry["result"] in fail_values:
                warnings_out.append({
                    "type": "result_fail",
                    "detail": f"{entry['step']} {entry['result']} @{entry['eqp']} {entry['time']}",
                })
        return "connected", history, warnings_out
    except Exception as e:
        logger.warning("[TransferPlan] role 'process_history' query failed: %s", e)
        return "missing", [], []


def _summarize_inline(db, stage_name: str, stage_cfg: dict, lot: str, slot: str,
                      region: set = None) -> dict:
    """inline source 블록의 일반 가용 집계 (tape-kind의 정본 경로).

    의미론(공통 계약):
    - total: total_chips 행 수(칩 단위 원천 가정 — dt_log는 칩당 1행)
    - transferred: transfer_log distinct (x,y) 칩 수
    - fail_breakdown[name]: fail 원천별 칩 수. frame='origin'이면 origin_log 조인 투영
      (출신 코어 fail → 타깃 좌표), frame='self'면 자기 identity 직접 카운트.
    - remaining = total − |fail 합집합 ∪ transferred| (origin_log가 있을 때. origin_log
      없으면 M1식 감산 폴백: total − Σfail − transferred).
      **정확성 단서**: 이 값은 ①모든 역할이 connected이고 ②하드캡(MAX_*) 미도달이며
      ③total_chips 원천이 칩당 1행 유일할 때만 정확하다. ①②가 깨지면 감산항이 과소해져
      remaining이 **과대**가 되므로 `remaining_reliable: false` + `remaining=None`으로
      내리고 경고를 warnings에 싣는다(QA F1·F2). ③(중복 행)은 현재 미표면화 — 알려진 한계.
    - by_core: 출신별 분해(집계만). 1순위는 origin_log(칩 단위 조인 — fail 포함 정확),
      origin_log 미해석 시 `origin_area_map`(dt_map 영역 귀속: val=코어 식별) 강등 경로로
      total/used만 제공하고 fail은 null(투영 불가 — 좌표 대응이 없으므로 조용히 0으로
      위장하지 않는다).
      **두 경로의 키 집합은 동일**하다: {core_id, core_lot, core_slot, total, fail,
      used, remaining} — 클라의 경로별 분기를 없애기 위함. 경로 구분은 응답 top-level
      `by_core_origin`("log" | "area_map") 마커로 한다. area_map 경로의 core_id는 영역
      맵의 원시 값(불투명 — config가 정한다)이므로 core_lot/core_slot은 null이고, 두
      경로 간 core_id 문자열이 일치할 것을 가정해선 안 된다(응답 내 그룹 키로만 사용).
    """
    source_cfg = stage_cfg.get("source") or {}
    statuses = {}
    warnings_out = []

    truncations = []   # [QA F2] 하드캡 도달 기록 — 응답에 표기하고 신뢰도를 낮춘다

    # ---- total_chips ----
    total = 0
    src = source_cfg.get("total_chips")
    model, cols = _resolve(src, required=("lot", "slot"))
    if model is None:
        statuses["total_chips"] = "missing"
    else:
        try:
            total = int(db.query(model).filter(cols["lot"] == lot, cols["slot"] == slot).count())
            statuses["total_chips"] = "connected"
        except Exception as e:
            logger.warning("[TransferPlan] role 'total_chips' query failed: %s", e)
            statuses["total_chips"] = "missing"

    # ---- transfer_log (기전사 — distinct 칩) ----
    used_set = set()
    used_count = 0
    src = source_cfg.get("transfer_log")
    model, cols = _resolve(src, required=("lot", "slot"))
    if model is None:
        statuses["transfer_log"] = "missing"
    else:
        try:
            filters = [cols["lot"] == lot, cols["slot"] == slot]
            if "x" in cols and "y" in cols:
                pts, trunc = _fetch_pairs(db, cols, filters, distinct=True,
                                          cap=MAX_ORIGIN_POINTS, tag="transfer_log")
                used_set = set(pts)
                used_count = len(used_set)
                if trunc:
                    truncations.append({"role": "transfer_log", "cap": MAX_ORIGIN_POINTS})
            else:
                used_count = int(db.query(model).filter(*filters).count())
            statuses["transfer_log"] = "connected"
        except Exception as e:
            logger.warning("[TransferPlan] role 'transfer_log' query failed: %s", e)
            statuses["transfer_log"] = "missing"

    # ---- origin_log (칩 단위 출신 귀속 — by_core·fail 투영의 다리) ----
    origin_rows = None   # [(tx, ty, origin_lot, origin_slot, ox, oy)]
    src = source_cfg.get("origin_log")
    model, cols = _resolve(src, required=("lot", "slot", "x", "y",
                                          "origin_lot", "origin_slot", "origin_x", "origin_y"))
    if model is None:
        statuses["origin_log"] = "missing"
    else:
        try:
            q = db.query(cols["x"], cols["y"], cols["origin_lot"], cols["origin_slot"],
                         cols["origin_x"], cols["origin_y"]) \
                 .filter(cols["lot"] == lot, cols["slot"] == slot)
            raw = q.limit(MAX_ORIGIN_POINTS).all()
            if len(raw) >= MAX_ORIGIN_POINTS:
                logger.warning("[TransferPlan] origin_log fetch hit hard cap (%d)", MAX_ORIGIN_POINTS)
                truncations.append({"role": "origin_log", "cap": MAX_ORIGIN_POINTS})
            origin_rows = [
                (int(tx), int(ty), ol, os_, int(ox), int(oy))
                for (tx, ty, ol, os_, ox, oy) in raw
                if tx is not None and ty is not None and ox is not None and oy is not None
            ]
            statuses["origin_log"] = "connected"
        except Exception as e:
            logger.warning("[TransferPlan] role 'origin_log' query failed: %s", e)
            origin_rows = None
            statuses["origin_log"] = "missing"

    # ---- fail_sources ----
    fail_breakdown = {}
    fail_union = set()               # 타깃 좌표 기준 fail 칩 합집합
    fail_sources = source_cfg.get("fail_sources") or {}
    # [확장성] 코어별 칩 인덱스를 1회 구축해 투영을 선형화한다
    # (코어마다 origin_rows 전체를 훑으면 O(코어수 × 칩수) — 테이프당 수백 코어에서 폭발)
    rows_by_core = {}
    involved_cores = []
    # [QA F6] canonical(dst) 메타는 코어당 1회만 조회한다 (F7 왕복 수도 일부 완화).
    # meta_cache는 (table, map_id) 단위 — 코어 × fail 원천 수만큼의 재조회를 막는다.
    canonical_grid_cache = {}
    meta_cache = {}
    if origin_rows is not None:
        for (tx, ty, ol, os_, ox, oy) in origin_rows:
            bucket = rows_by_core.get((ol, os_))
            if bucket is None:
                bucket = rows_by_core[(ol, os_)] = []
                involved_cores.append((ol, os_))
            bucket.append((tx, ty, ox, oy))

    for name, fs in (fail_sources.items() if isinstance(fail_sources, dict) else []):
        name = str(name)
        frame = fs.get("frame") or ("origin" if origin_rows is not None else "self")
        model, cols = _resolve(fs, required=("lot", "slot"))
        if model is None:
            statuses[name] = "missing"
            fail_breakdown[name] = 0
            continue

        if frame == "self":
            # 자기 identity 직접 카운트 (M1 맵 모드와 동일 — align은 카운트 불변)
            try:
                filters = [cols["lot"] == lot, cols["slot"] == slot]
                fail_values = fs.get("fail_values")
                if fail_values and "val" in cols:
                    filters.append(cols["val"].in_([str(v) for v in fail_values]))
                cnt = int(db.query(model).filter(*filters).count())
                fail_breakdown[name] = cnt
                statuses[name] = "connected"
                if "x" in cols and "y" in cols:
                    pts, trunc = _fetch_pairs(db, cols, filters, cap=MAX_FAIL_POINTS,
                                              tag=f"fail:{name}")
                    fail_union.update(pts)
                    if trunc:
                        truncations.append({"role": name, "cap": MAX_FAIL_POINTS})
            except Exception as e:
                logger.warning("[TransferPlan] fail source '%s' query failed: %s", name, e)
                statuses[name] = "missing"
                fail_breakdown[name] = 0
            continue

        # frame == "origin": 출신 프레임 fail의 투영 — origin_log 필수
        if origin_rows is None:
            statuses[name] = "unavailable(origin_missing)"
            fail_breakdown[name] = 0
            continue
        if "x" not in cols or "y" not in cols:
            statuses[name] = "missing"
            fail_breakdown[name] = 0
            continue
        try:
            projected = set()
            status = "connected"
            marker = None
            for (ol, os_) in involved_cores:
                fail_set, mk, trunc = _canonical_fail_set(
                    db, source_cfg, fs, cols, ol, os_,
                    grid_cache=canonical_grid_cache, meta_cache=meta_cache)
                if fail_set is None:
                    # [align 규율] 규격 불명 시 raw 좌표로 조용히 계산하지 않는다
                    status = "connected(align_unavailable)"
                    projected = set()
                    break
                if trunc:
                    truncations.append({"role": name, "cap": MAX_FAIL_POINTS, "core": f"{ol}|{os_}"})
                if mk:
                    marker = mk
                for (tx, ty, ox, oy) in rows_by_core.get((ol, os_), ()):
                    if (ox, oy) in fail_set:
                        projected.add((tx, ty))
            if status == "connected" and marker:
                status = f"connected({marker})"
            statuses[name] = status
            if status == "connected(align_unavailable)":
                fail_breakdown[name] = 0
            else:
                fail_breakdown[name] = len(projected)
                fail_union.update(projected)
        except Exception as e:
            logger.warning("[TransferPlan] fail source '%s' projection failed: %s", name, e)
            statuses[name] = "missing"
            fail_breakdown[name] = 0

    # ---- remaining ----
    if origin_rows is not None:
        # 칩 단위 정확 집계: fail·기전사 중복 이중 감산 없음
        blocked = fail_union | used_set
        remaining = total - len(blocked)
    else:
        remaining = total - sum(fail_breakdown.values()) - used_count

    # ---- by_core (집계만, 좌표 목록 금지) ----
    # [계약] 두 경로(log/area_map)의 **키 집합은 동일**하다:
    #   {core_id, core_lot, core_slot, total, fail, used, remaining}
    # 클라가 경로별로 분기하지 않게 하기 위함이며, 경로 구분은 by_core_origin 마커로 한다.
    by_core = None
    by_core_origin = None
    by_core_truncated = False
    if origin_rows is not None:
        agg = {}
        for (tx, ty, ol, os_, _ox, _oy) in origin_rows:
            key = (ol, os_)
            a = agg.get(key)
            if a is None:
                a = agg[key] = {"total": 0, "fail": 0, "used": 0, "blocked": 0}
            a["total"] += 1
            is_fail = (tx, ty) in fail_union
            is_used = (tx, ty) in used_set
            if is_fail:
                a["fail"] += 1
            if is_used:
                a["used"] += 1
            if is_fail or is_used:
                a["blocked"] += 1
        by_core = []
        for (ol, os_) in sorted(agg.keys(), key=lambda k: (str(k[0]), str(k[1]))):
            a = agg[(ol, os_)]
            by_core.append({
                "core_id": f"{ol}{CORE_ID_SEP}{os_}",
                "core_lot": ol, "core_slot": os_,
                "total": a["total"], "fail": a["fail"], "used": a["used"],
                "remaining": a["total"] - a["blocked"],
            })
        if len(by_core) > MAX_BY_CORE:
            logger.warning("[TransferPlan] by_core truncated to %d entries", MAX_BY_CORE)
            by_core = by_core[:MAX_BY_CORE]
            by_core_truncated = True
        by_core_origin = "log"
    else:
        # [강등 경로] origin_log 미해석 — 영역 귀속 맵(dt_map: val=코어 식별)으로 분해만 제공.
        # 좌표 대응이 없어 fail 투영은 불가 → fail은 null(0으로 위장 금지).
        area_src = source_cfg.get("origin_area_map")
        model, cols = _resolve(area_src, required=("lot", "slot", "x", "y", "val"))
        if model is None:
            if _valid_binding(area_src):
                statuses["origin_area_map"] = "missing"
        else:
            try:
                raw = (db.query(cols["x"], cols["y"], cols["val"])
                       .filter(cols["lot"] == lot, cols["slot"] == slot)
                       .limit(MAX_ORIGIN_POINTS).all())
                if len(raw) >= MAX_ORIGIN_POINTS:
                    logger.warning("[TransferPlan] origin_area_map fetch hit hard cap (%d)",
                                   MAX_ORIGIN_POINTS)
                    truncations.append({"role": "origin_area_map", "cap": MAX_ORIGIN_POINTS})
                agg = {}
                for (ax, ay, val) in raw:
                    if ax is None or ay is None or val is None:
                        continue
                    a = agg.get(str(val))
                    if a is None:
                        a = agg[str(val)] = {"total": 0, "used": 0}
                    a["total"] += 1
                    if (int(ax), int(ay)) in used_set:
                        a["used"] += 1
                by_core = []
                for val in sorted(agg.keys()):
                    a = agg[val]
                    by_core.append({
                        # core_id는 영역 맵의 원시 값(config가 정하는 불투명 식별자) —
                        # lot/slot으로 분해할 근거가 없으므로 null(추측 파싱 금지).
                        "core_id": val, "core_lot": None, "core_slot": None,
                        "total": a["total"], "fail": None, "used": a["used"],
                        "remaining": a["total"] - a["used"],
                    })
                if len(by_core) > MAX_BY_CORE:
                    by_core = by_core[:MAX_BY_CORE]
                    by_core_truncated = True
                by_core_origin = "area_map"
                statuses["origin_area_map"] = "connected(area_only)"
            except Exception as e:
                logger.warning("[TransferPlan] origin_area_map query failed: %s", e)
                statuses["origin_area_map"] = "missing"

    # ---- history ----
    hist_status, history, hist_warnings = _collect_history(db, source_cfg, lot, slot)
    statuses["process_history"] = hist_status
    warnings_out.extend(hist_warnings)

    # [QA F1] 강등 표면화 — sources 문자열만으로는 소비자가 정상과 구별하지 못한다.
    fail_role_names = set(str(k) for k in fail_sources) if isinstance(fail_sources, dict) else set()
    deg_warnings, remaining_reliable, total_reliable = assess_degradation(
        statuses, fail_roles=fail_role_names)

    # [QA F2] 하드캡 절단도 감산항을 과소하게 만든다 — 강등과 동일 규율로 처리한다.
    # (total은 count()라 절단되지 않으므로 분자·분모의 모집단이 어긋난다 → remaining 과대)
    for t in truncations:
        remaining_reliable = False
        deg_warnings.append({
            "type": WARN_RESULT_TRUNCATED,
            "role": t["role"], "cap": t["cap"],
            "effect": EFFECT_REMAINING_OVERSTATED,
            "detail": (f"역할 '{t['role']}' 조회가 하드캡({t['cap']})에 도달해 절단됨"
                       + (f" [코어 {t['core']}]" if t.get("core") else "")
                       + " — 집계가 과소해져 remaining이 과대일 수 있음"),
        })
    if by_core_truncated:
        deg_warnings.append({
            "type": WARN_RESULT_TRUNCATED,
            "role": "by_core", "cap": MAX_BY_CORE,
            "effect": EFFECT_BY_CORE_DEGRADED,
            "detail": f"by_core 분해가 상한({MAX_BY_CORE})으로 절단됨 — "
                      f"sum(by_core.total)이 chips.total과 일치하지 않는다",
        })

    chips_block, inv_warnings = build_chips_block(
        total=total,
        fail_breakdown=fail_breakdown,
        transferred=used_count,
        remaining=remaining,
        remaining_reliable=remaining_reliable,
        total_reliable=total_reliable,
    )
    if inv_warnings:
        remaining_reliable = False   # region_chips.reliable에도 전파

    result = {
        "identity": {"lot": lot, "slot": slot},
        "stage": stage_name,
        "source_kind": stage_cfg.get("source_kind"),
        "sources": statuses,
        "chips": chips_block,
        "history": history,
        "warnings": deg_warnings + inv_warnings + warnings_out,
    }
    if by_core is not None:
        result["by_core"] = by_core
        # 경로 마커 — 클라가 "코어별 불량 미상(영역 귀속 기준)" 안내를 띄울 근거
        result["by_core_origin"] = by_core_origin
        result["by_core_truncated"] = by_core_truncated
    if truncations:
        result["truncated"] = truncations

    # ---- [②] 영역 내 가용 (계획이 이 소스에서 쓰기로 페인팅한 셀 집합으로 스코프) ----
    if region is not None:
        total_pts = None
        if origin_rows is not None:
            total_pts = {(tx, ty) for (tx, ty, _l, _s, _ox, _oy) in origin_rows}
        else:
            src = source_cfg.get("total_chips")
            model, cols = _resolve(src, required=("lot", "slot"))
            if model is not None and "x" in cols and "y" in cols:
                pts, _tr = _fetch_pairs(db, cols, [cols["lot"] == lot, cols["slot"] == slot],
                                        cap=MAX_REGION_CELLS, tag="region:total")
                total_pts = set(pts)
        # fail은 원천별 집합을 따로 갖고 있지 않으므로 합집합만 신뢰 가능 —
        # breakdown은 원천별 재계산 없이 합집합 기준 단일 항목으로 제공한다.
        result["region_chips"] = _region_block(
            total_pts, {"all_fail": fail_union}, used_set, region)
        result["region_chips"]["reliable"] = remaining_reliable
    return result


def get_stage_source_summary(db, cfg: dict, stage_name: str, lot: str, slot: str,
                             bp_config: dict = None,
                             ref_table: str = None, map_key: str = None) -> dict:
    """단계별 소스 가용 집계 — 계약 공통 형태를 생성한다.

    stage 미선언 시 KeyError (라우트가 404로 변환).
    bp_config: source_config_ref 스테이지용 M1 config 스냅샷(미지정 시 여기서 1회 로드 —
    validate처럼 반복 호출하는 상위는 스냅샷을 주입해 작업 경계 1회 로드 규율을 지킨다).
    ref_table/map_key: 계획 맵 정체성(v2 — 구 plan_id 대체). 소스 영역 스코프에만 쓰인다.
    """
    import bonding_plan

    stages = get_stages(cfg)
    stage_cfg = stages.get(stage_name)
    if not isinstance(stage_cfg, dict):
        raise KeyError(f"stage '{stage_name}' is not declared")

    # [②] 계획이 지정한 소스 사용 영역(자유 페인팅 셀 집합)을 스코프로 소비한다
    region = None
    if ref_table and map_key:
        region = load_source_region(db, cfg, ref_table, map_key, lot, slot)

    ref = stage_cfg.get("source_config_ref")
    if ref in M1_SOURCE_REFS:
        # [내부 통합] M1 core-summary = core-kind 소스 가용의 인스턴스 (외부 계약 불변)
        bp_cfg = bp_config if bp_config is not None else bonding_plan.load_bonding_plan_config()
        m1 = bonding_plan.get_core_summary(db, lot, slot, config=bp_cfg)
        out = _reshape_m1_summary(m1, stage_name, stage_cfg)
        if region is not None:
            out["region_chips"] = _core_region_counts(db, bp_cfg, lot, slot, region)
            out["region_chips"]["reliable"] = out["chips"].get("remaining_reliable", True)
        return out

    return _summarize_inline(db, stage_name, stage_cfg, lot, slot, region=region)


# ---------------------------------------------------------------------------
# 계획 검증 (validate)
# ---------------------------------------------------------------------------

def _plan_store_binding(cfg: dict, role: str, required: tuple):
    store = (cfg.get("plan_store") or {}).get(role)
    model, cols = _resolve(store, required=required)
    return store, model, cols


def _num(v, default=None):
    if v is None or v == "":
        return default
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return default


def _band_range(band):
    """STACK 구간 표기에서 수치 범위를 **읽을 수 있으면** 읽는다. 못 읽으면 None.

    [규율] 표기는 강제하지 않는다(사용자 확정) — `1` / `2-11` / `H1~H2` 무엇이든 받는다.
    커버리지 검증은 수치로 읽히는 구간에만 적용되고, 나머지는 조용히 불참한다(경고 신설 금지).
    """
    if band is None:
        return None
    s = str(band).strip()
    if not s:
        return None
    for sep in ("-", "~", ".."):
        if sep in s:
            a, _, b = s.partition(sep)
            lo, hi = _num(a.strip()), _num(b.strip())
            if lo is None or hi is None:
                return None
            return int(lo), int(hi)
    v = _num(s)
    return (int(v), int(v)) if v is not None else None


def _painted_values(db, ref_table: str, map_key: str, overlay_cfg: dict):
    """대상 맵 **자신의** 셀에서 값 분포를 group-by로 센다 (계획 맵 사본 없음 — v2).

    반환: ({값: 셀 수}, 상태 문자열). 좌표/키 바인딩은 맵 오버레이와 **동일한 유도 규칙**을
    쓴다(table_config의 map_key_columns + x/y + val 후보 → 선언이 있으면 선언 우선).
    [확장성] 셀을 전량 로드하지 않고 group-by 집계만 한다 — 맵 1장이 수만 셀이다.
    """
    from sqlalchemy import func
    from database import models
    import map_overlay

    model = models.DYNAMIC_TABLES.get(ref_table)
    if model is None:
        return {}, "missing"
    binding = map_overlay.resolve_binding(overlay_cfg, ref_table)
    if binding is None:
        return {}, "missing"
    val_col = getattr(model, binding.get("val") or "", None)
    if val_col is None:
        return {}, "missing"
    filters = map_overlay.build_key_filters(model, binding, map_key)
    if filters is None:
        return {}, "missing"
    try:
        rows = (db.query(val_col, func.count())
                .filter(*filters).group_by(val_col).limit(MAX_PLAN_VALUES).all())
    except Exception as e:
        logger.warning("[TransferPlan] painted values query failed (%s/%s): %s",
                       ref_table, map_key, e)
        return {}, "missing"
    painted = {}
    for val, cnt in rows:
        if val is None or str(val).strip() == "":
            continue
        painted[str(val)] = int(cnt)
    return painted, "connected"


def validate_plan(db, cfg: dict, ref_table: str, map_key: str,
                  overlay_cfg: dict = None) -> dict:
    """GET /api/transfer-plan/validate — 경고 목록 생성 (**v2 계획 모델**).

    [정체성] 계획은 `(ref_table, map_key)` — 지금 열어 편집 중인 그 맵 자체다. `plan_id`도
    계획 헤더 테이블도 없다. stage는 `stages.*.target_map.table` 역인덱스로 유도한다.
    [DOE 행 단위] `(doe_value, band_seq)` — 한 값이 여러 STACK 구간을 갖는다.
    [소스 묶음] 한 **구간**에 소스가 여러 매 붙는다(pool). 매별 소요는 지정 대상이 아니라
    **구간 총 소요의 균등 배분**이며, 행에 `qty`가 명시돼 있으면 그것이 우선한다.

    LookupError: plan_store.doe 미구성 (라우트가 404로 변환).
    """
    doe_src, doe_model, doe_cols = _plan_store_binding(
        cfg, "doe", required=("ref_table", "map_key", "doe_value", "band_seq"))
    if doe_model is None:
        raise LookupError("plan store is not configured (plan_store.doe unresolved)")

    if overlay_cfg is None:
        import map_overlay
        overlay_cfg = map_overlay.load_overlay_config()   # 작업 경계 1회 스냅샷

    stage_name = stage_of_table(cfg, ref_table)
    warnings_out = []

    stage_cfg = get_stages(cfg).get(stage_name) if stage_name else None
    if not isinstance(stage_cfg, dict):
        warnings_out.append({
            "type": WARN_STAGE_UNKNOWN,
            "effect": "validation_skipped",
            "detail": f"맵 테이블 '{ref_table}'을 target_map으로 선언한 stage가 없음 — "
                      f"**수량·가용·fail 검증을 전혀 수행하지 못했다**(경고 없음 = 이상 없음이 아님)",
        })
        stage_cfg = None

    # ---- DOE 정의 로드 (계획 맵 정체성으로 equality 조회 — LIKE 프리픽스 스캔 금지) ----
    doe_rows = (db.query(doe_model)
                .filter(doe_cols["ref_table"] == ref_table,
                        doe_cols["map_key"] == map_key)
                .limit(MAX_DOE_PER_PLAN + 1).all())
    if len(doe_rows) > MAX_DOE_PER_PLAN:
        logger.warning("[TransferPlan] plan '%s/%s' DOE rows exceed cap (%d) — truncated",
                       ref_table, map_key, MAX_DOE_PER_PLAN)
        doe_rows = doe_rows[:MAX_DOE_PER_PLAN]

    def _doe_get(row, role_key):
        name = (doe_src.get("columns") or {}).get(role_key)
        return getattr(row, name, None) if name else None

    # ---- 소스 묶음(pool) 로드 — (DOE값, 구간) → [자재 행] ----
    # [v2] bk에 **구간 차원 + 소스 차원**이 들어간다: 한 값이 여러 구간을 갖고, 한 구간에
    # 여러 매를 묶어 투입하기 때문(사용자 확정: "한 매당 500칩이면 4매 묶어서 투입").
    # 묶음이 구간 아래 붙으므로 구간마다 다른 자재 조합을 지정할 수 있다.
    src_binding, src_model, src_cols = _plan_store_binding(
        cfg, "doe_source",
        required=("ref_table", "map_key", "doe_value", "band_seq",
                  "source_lot", "source_slot"))
    pool_by_band = {}
    if src_model is not None:
        try:
            s_rows = (db.query(src_model)
                      .filter(src_cols["ref_table"] == ref_table,
                              src_cols["map_key"] == map_key)
                      .limit(MAX_DOE_PER_PLAN * MAX_SOURCES_PER_DOE).all())
            scols = src_binding.get("columns") or {}

            def _sget(row, key):
                name = scols.get(key)
                return getattr(row, name, None) if name else None

            for r in s_rows:
                v = _sget(r, "doe_value")
                if v is None:
                    continue
                pool_by_band.setdefault((str(v), _num(_sget(r, "band_seq"))), []).append({
                    "source_lot": _sget(r, "source_lot"),
                    "source_slot": _sget(r, "source_slot"),
                    "qty": _num(_sget(r, "qty")),
                    "note": _sget(r, "note"),
                })
        except Exception as e:
            logger.warning("[TransferPlan] doe_source load failed for '%s/%s': %s",
                           ref_table, map_key, e)
            pool_by_band = {}

    # ---- 페인팅 값 분포 — **대상 맵 자신**에서 (계획 맵 사본 폐기) ----
    painted, painted_status = _painted_values(db, ref_table, map_key, overlay_cfg)

    doe_values = []
    for row in doe_rows:
        v = _doe_get(row, "doe_value")
        if v is not None:
            doe_values.append(str(v))
    doe_value_set = set(doe_values)

    # ---- DOE 값-맵 정합 ----
    for val in sorted(set(painted.keys()) - doe_value_set):
        warnings_out.append({
            "type": WARN_UNDEFINED_DOE_VALUE, "value": val,
            "detail": f"맵에 페인팅된 값 '{val}'({painted[val]}칩)의 DOE 정의가 없음",
        })
    for val in sorted(doe_value_set - set(painted.keys())):
        warnings_out.append({
            "type": WARN_DOE_VALUE_UNPAINTED, "value": val,
            "detail": f"DOE '{val}'가 맵에 페인팅되지 않음 (수량 0)",
        })

    # ---- STACK 구간 커버리지 (수치로 읽히는 구간만 참여 — 표기 강제 없음) ----
    # (한 값이 여러 구간 행을 가지므로 구간은 행 단위로 수집된다 — 값 단위가 아니다)
    layered = []
    for row in doe_rows:
        v = str(_doe_get(row, "doe_value"))
        band = _doe_get(row, "stack_band")
        rng = _band_range(band)
        if rng is None:
            continue
        lf, lt = rng
        if lf > lt:
            warnings_out.append({
                "type": WARN_LAYER_RANGE_INVALID, "value": v, "band": band,
                "detail": f"DOE '{v}' STACK 구간 역전: {lf} > {lt}",
            })
            continue
        layered.append((v, lf, lt))
    if layered:
        covered = set()
        for (_v, lf, lt) in layered:
            covered.update(range(lf, lt + 1))
        max_layer = max(covered)
        missing_layers = sorted(set(range(1, max_layer + 1)) - covered)
        if missing_layers:
            warnings_out.append({
                "type": WARN_LAYER_COVERAGE_GAP,
                "detail": f"STACK 커버리지 공백: 1..{max_layer} 중 {missing_layers} 구간에 배정된 DOE 없음",
            })

    # ---- 수량 부족 + 소스 fail 경고 (소스 가용은 (lot,slot)당 1회 캐시) ----
    summary_cache = {}
    bp_snapshot = None
    if stage_cfg is not None and stage_cfg.get("source_config_ref") in M1_SOURCE_REFS:
        import bonding_plan
        bp_snapshot = bonding_plan.load_bonding_plan_config()  # 작업 경계 1회 스냅샷

    def _get_summary(s_lot, s_slot):
        key = (s_lot, s_slot)
        if key not in summary_cache:
            summary_cache[key] = get_stage_source_summary(
                db, cfg, stage_name, s_lot, s_slot, bp_config=bp_snapshot)
        return summary_cache[key]

    # [QA F1] 수량 검증이 실제로 수행됐는지 추적한다 — "검사 안 함"이 "이상 없음"으로
    # 읽히는 것이 이 API의 최대 위험이다(스킵을 침묵으로 두지 않는다).
    availability_checked = stage_cfg is not None
    any_doe_checked = False
    source_alloc = {}   # [QA F4] (lot, slot) → {required 누계, available, does[]}

    if stage_cfg is not None:
        # [v2] DOE 행(= 값×구간) → 수요(demand) 목록. 구간 총 소요를 묶음 매 수로
        # **균등 배분**하되, 행에 qty가 명시돼 있으면 그것이 우선한다(부분 선언 허용).
        # 같은 자재가 여러 구간·여러 값에 걸쳐 있으면 아래 source_alloc이 자연히 합산한다.
        demands = []   # (doe_value, source_lot, source_slot, required, label)
        for row in doe_rows:
            v = str(_doe_get(row, "doe_value"))
            seq = _num(_doe_get(row, "band_seq"))
            band_label = _doe_get(row, "stack_band") or (seq if seq is not None else "")
            total = _num(_doe_get(row, "qty_total"), default=0) or 0
            pool = pool_by_band.get((v, seq)) or []
            if not pool:
                warnings_out.append({
                    "type": WARN_SOURCE_UNRESOLVED, "value": v, "band": band_label,
                    "detail": f"DOE '{v}[{band_label}]'에 사용 자재(소스 묶음)가 "
                              f"선언되지 않음 — 수량 검증 불가",
                })
                continue
            n = len(pool)
            share = -(-int(total) // n) if total else 0   # 올림 배분 (부족 과소평가 방지)
            for entry in pool:
                q = entry["qty"] if entry["qty"] is not None else share
                label = (f"{v}[{band_label}]@"
                         f"{entry['source_lot']}|{entry['source_slot']}")
                demands.append((v, entry["source_lot"], entry["source_slot"],
                                int(q or 0), label))

        for (v, s_lot, s_slot, required, label) in demands:
            if not s_lot or not s_slot:
                warnings_out.append({
                    "type": WARN_SOURCE_UNRESOLVED, "value": v,
                    "detail": f"DOE '{label}'의 소스(lot/slot) 미지정 — 수량 검증 불가",
                })
                continue
            try:
                summary = _get_summary(s_lot, s_slot)
            except Exception as e:
                logger.warning("[TransferPlan] source summary failed for (%s,%s): %s", s_lot, s_slot, e)
                warnings_out.append({
                    "type": WARN_SOURCE_UNRESOLVED, "value": v,
                    "detail": f"DOE '{label}' 소스({s_lot},{s_slot}) 가용 조회 실패",
                })
                continue

            chips_block = summary.get("chips") or {}

            # [QA F1] 강등된 가용치로 "부족 아님"을 판정하지 않는다 — 오염된 remaining은
            # 과대이므로 qty_shortage가 발화하지 않아 안전망이 조용히 무너진다.
            if not chips_block.get("remaining_reliable", True):
                degraded_roles = [w.get("role") for w in (summary.get("warnings") or [])
                                  if w.get("type") == WARN_SOURCE_DEGRADED
                                  and w.get("effect") in (EFFECT_REMAINING_OVERSTATED,
                                                          EFFECT_TOTAL_UNKNOWN)]
                ub = chips_block.get("remaining_upper_bound")
                warnings_out.append({
                    "type": WARN_AVAILABILITY_UNRELIABLE, "value": v,
                    "required": required,
                    "degraded_roles": degraded_roles,
                    "remaining_upper_bound": ub,
                    "detail": (f"DOE '{label}' 수량 검증 **판정 불가** — 소스({s_lot},{s_slot})의 "
                               f"역할 강등({', '.join(degraded_roles) or '알 수 없음'})으로 가용치를 "
                               f"신뢰할 수 없음. 필요 {required}"
                               + (f", 가용 상한 {ub}(실제는 이보다 작음)" if ub is not None else "")),
                })
                continue   # 부족/fail 판정 모두 생략 — 오염값 기반 판정 금지

            any_doe_checked = True
            available = int(chips_block.get("remaining") or 0)
            # [QA F4] 소스별 합산 누적 — DOE 단독 판정만으로는 분할 초과배정을 못 잡는다
            acc = source_alloc.get((s_lot, s_slot))
            if acc is None:
                acc = source_alloc[(s_lot, s_slot)] = {
                    "required": 0, "available": available, "does": []}
            acc["required"] += required
            if label not in acc["does"]:
                acc["does"].append(label)

            if required > available:
                warnings_out.append({
                    "type": WARN_QTY_SHORTAGE, "value": v, "demand": label,
                    "required": required, "available": available,
                    "detail": (f"DOE '{label}' 수량 부족: 필요 {required} > "
                               f"소스({s_lot},{s_slot}) 가용 {available}"),
                })

            fb = chips_block.get("fail_breakdown") or {}
            fail_total = sum(int(n or 0) for n in fb.values())
            if fail_total > 0 and not any(
                    w.get("type") == WARN_SOURCE_FAIL_CHIPS and w.get("value") == v
                    and w.get("source") == f"{s_lot}|{s_slot}" for w in warnings_out):
                warnings_out.append({
                    "type": WARN_SOURCE_FAIL_CHIPS, "value": v,
                    "source": f"{s_lot}|{s_slot}",
                    "fail_breakdown": fb,
                    "detail": f"DOE '{v}' 소스({s_lot},{s_slot})에 fail 칩 {fail_total}개 "
                              f"({', '.join(f'{k}:{n}' for k, n in fb.items())})",
                })
            for w in (summary.get("warnings") or []):
                if w.get("type") in (WARN_SOURCE_DEGRADED, WARN_RESULT_TRUNCATED):
                    continue   # 강등/절단은 availability_unreliable로 이미 다뤘다(중복 방지)
                entry = {
                    "type": WARN_SOURCE_HISTORY_FAIL, "value": v,
                    "source": f"{s_lot}|{s_slot}",
                    "detail": f"DOE '{v}' 소스({s_lot},{s_slot}) 이력 경고: {w.get('detail')}",
                }
                if entry not in warnings_out:
                    warnings_out.append(entry)

        # [QA F4] 소스별 합산 초과배정 — DOE를 따로 보면 각각은 가용 이하인데 합이 넘는 경우.
        # DOE 계획의 정상 형태(한 소스를 여러 조건군이 나눠 씀)라 가장 흔한 초과 형태다.
        # 단독 DOE만 쓰는 소스는 qty_shortage가 이미 정확히 같은 사실을 말하므로 제외한다.
        for (s_lot, s_slot) in sorted(source_alloc.keys(), key=lambda k: (str(k[0]), str(k[1]))):
            acc = source_alloc[(s_lot, s_slot)]
            if len(acc["does"]) < 2 or acc["required"] <= acc["available"]:
                continue
            warnings_out.append({
                "type": WARN_SOURCE_OVERALLOCATED,
                "source_lot": s_lot, "source_slot": s_slot,
                "required_total": acc["required"], "available": acc["available"],
                "doe_values": list(acc["does"]),
                "detail": (f"소스({s_lot},{s_slot}) 합산 초과배정: 수요 {len(acc['does'])}건"
                           f"({', '.join(acc['does'])})의 필요 합계 {acc['required']} > 가용 "
                           f"{acc['available']} — 개별 수요는 각각 가용 이하라 "
                           f"{WARN_QTY_SHORTAGE}로는 잡히지 않는다"),
            })

    # DOE가 있는데 단 하나도 실제 판정에 도달하지 못했으면 "검증했다"고 말할 수 없다.
    if doe_rows and not any_doe_checked:
        availability_checked = False

    # [QA F1] status는 "검사 안 함"과 "이상 없음"을 절대 같은 값으로 내지 않는다.
    if not availability_checked:
        status_out = "unverified"
    elif warnings_out:
        status_out = "warnings"
    else:
        status_out = "ok"

    return {
        "ref_table": ref_table,
        "map_key": map_key,
        "stage": stage_name,
        "map_status": painted_status,
        "doe_count": len(doe_rows),
        "painted_values": {k: painted[k] for k in sorted(painted.keys())},
        "status": status_out,
        "availability_checked": availability_checked,
        "warnings": warnings_out,
    }
