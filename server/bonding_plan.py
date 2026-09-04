"""본딩 실험계획(M1) — 역할 바인딩 config 로더 + 코어 집계 코어.

[역할] map editor "본딩 실험계획 Info 창"(조회 전용)의 서버측 집계 엔진.
`server/config/bonding_plan_config.json`(사용자 config, gitignored)이 역할(role)→실테이블
바인딩을 정의하고, 이 모듈은 그 바인딩만 경유해 집계한다 — 실테이블명 하드코딩 금지
(실 운영 테이블명 상이 대응).

[경계 계약 — 총괄 고정] GET /api/bonding-plan/core-summary 응답 형태는 지시서
Server_bonding_plan_m1_task.md §C. 칩 좌표 목록은 절대 반환하지 않는다(집계만).
[relaxation 2026-08-04 — 총괄 board request 2] 보조 역할 선언은 **선택**이다:
config에 키가 아예 없으면 상태 `not_declared`(강등 아님)이고 그 감산항 없이 집계한다.
감산에서 빠진 종류는 응답의 선택 필드 `inactive_subtractions`(역할명 리스트)가 말한다.
선언돼 있으나 깨진 바인딩은 종전 그대로 `missing` 강등 — 완화는 부재에만 적용된다.

[align — 정렬의 유일한 근거는 `wafer_map_metadata`다 (사용자 확정 2026-07-26)]
defect/EDS 계측 맵은 코어 맵과 좌표계가 다를 수 있다(회전·면·start·치수·물리 규격).
그 차이는 **각 맵이 자기 메타에 이미 선언**하고 있으므로, 소스 프레임 → canonical(CORE)
프레임 변환은 **두 메타의 델타에서 유도**한다. config의 `sources[].align` 선언 레이어는
제거됐다 — 계측으로 잰 어긋남도 메타에 기록한다.

  canonical 프레임 = 맵 모드 역할 중 메타가 등록된 첫 번째(total_chips → defect → eds_fail)
  변환 = map_overlay.resolve_map_transform(소스 메타, canonical 메타)

**변환 구현은 이 모듈에 없다.** 구 `normalize_align`/`make_align_transform`은 `map_overlay`
의 프레임 합성 경로(`visual_to_physical` → `physical_to_visual`)로 대체돼 삭제됐다. 그
사본은 저장 좌표가 **웨이퍼 원으로 자른 바운딩박스 상대값**이라는 규약을 반영하지 않아,
bbox가 0이 아닌 맵(원에 잘리는 실격자)에서 거울 변환이 끼면 전 셀이 `2·minC`만큼 어긋났다.

[스냅샷 규율] config는 요청(작업) 경계에서 1회 로드해 전 구간에 인자로 전달한다.
맵 메타도 요청 경계에서 1회 캐시한다(역할 × 요청 = 고정 소수 — N+1 금지).
"""
import math
import json
import logging
import os

logger = logging.getLogger(__name__)

import paths  # single override point (ASSY_DATA_ROOT)
CONFIG_PATH = paths.config_path("bonding_plan_config.json")

ROLES = ("process_history", "defect", "eds_fail", "used_chips", "total_chips")

# [relaxation 2026-08-04 — board request 2] An auxiliary role key that is ABSENT
# from the config is a site-level statement "we do not keep such a table", not a
# broken binding. Real fabs mark deductions on the map itself and never maintain
# per-lot fail/consumption side tables — forcing those declarations demoted every
# availability figure to 미상. Absent auxiliary roles now read `not_declared`
# (NOT a degradation) and their subtraction is simply inactive; the payload names
# the inactive kinds in `inactive_subtractions` so "gross shown as net" is never
# silent. A role key that IS present but broken (null, typo, missing table)
# keeps every pre-existing degradation — the relaxation applies ONLY to absence.
# `total_chips` is exempt: without the denominator there is no availability.
STATUS_NOT_DECLARED = "not_declared"
# M1 subtraction-role kinds (remaining = total − defect − eds_fail − used).
SUBTRACTION_ROLES = ("defect", "eds_fail", "used_chips")
HISTORY_LIMIT = 50          # history 최근 N건 상한 (계약)
MAX_REGION_RECTS = 50       # region 사각형 개수 상한 (페이로드/연산 방어)
MAX_REGION_POINTS = 100_000  # 영역 교차용 내부 좌표 페치 하드캡 (무제한 로드 금지)

# canonical(CORE) 프레임 후보 — **좌표를 바인딩한 첫 역할**이 기준 프레임을 정의한다.
# 코어 웨이퍼 자신의 맵이 앞에 오도록 정렬돼 있다(used_chips의 (cx,cy)가 사는 프레임).
#
# 🔴 이것은 **퇴화형이고 폴백이다**(스펙 §0.2 층 ⑧). N항 합의 결정 — 다른 모든 소스를 어느
# 프레임 위로 옮기는가 — 을 config 선언 순서에 맡기고 기록도 판도 소스 목록도 남기지 않는다.
# 확정 기록이 있으면 `canonical_basis`가 먼저 답하고 이 튜플은 **상의되지 않는다**. 여기
# 남아 있는 이유는 확정이 없는 단위가 계속 계획을 낼 수 있어야 하기 때문이며, 그때
# payload의 `frame_basis`가 「이 길로 왔다」를 말한다.
CANONICAL_FRAME_ROLES = ("total_chips", "defect", "eds_fail")

# 기준 프레임의 **출처** 이름. 상태 어휘가 아니라 「어느 길로 왔나」다.
BASIS_CONFIRMATION = "confirmation"   # 층 ⑧의 확정 기록이 기준을 지목했다
BASIS_ROLE_ORDER = "role_order"       # 확정이 없어 위 튜플 순서로 골랐다 (퇴화형)


# ---------------------------------------------------------------------------
# config 로더 (파일 경계 스냅샷 — 요청당 1회)
# ---------------------------------------------------------------------------

def load_bonding_plan_config(path: str = None) -> dict:
    """bonding_plan_config.json을 로드한다. 없거나 손상 시 {} (부분 가동 — 에러 아님)."""
    p = path or CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            logger.warning("[BondingPlan] config root is not an object — ignored: %s", p)
            return {}
        return raw
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("[BondingPlan] failed to load config %s: %s", p, e)
        return {}


def _valid_source(src) -> bool:
    return (
        isinstance(src, dict)
        and isinstance(src.get("table"), str) and src.get("table")
        and isinstance(src.get("columns"), dict)
    )


def role_is_declared(block, key) -> bool:
    """[relaxation] Did the site declare this role AT ALL?

    ONE PREDICATE, EVERY READER CALLS IT (same discipline as
    `transfer_log_is_declared_none`): only a key that is truly absent from the
    block is a non-declaration. A present key with ANY value — null, a garbage
    string, a binding with a typo — is a declaration, and a broken declaration
    keeps its pre-existing degradation (`missing` etc.). Absence is the normal
    state at real sites; presence is a claim that must resolve.
    """
    return isinstance(block, dict) and key in block


# ---------------------------------------------------------------------------
# region 파싱/클램프
# ---------------------------------------------------------------------------

def parse_region(region_str: str) -> list[tuple[int, int, int, int]]:
    """region 파라미터(URL 디코딩된 JSON 문자열) → [(x1,y1,x2,y2)] (정규화: x1<=x2, y1<=y2).

    형식 위반 시 ValueError (라우트가 400으로 변환).
    """
    try:
        data = json.loads(region_str)
    except Exception:
        raise ValueError("region must be a valid JSON object")
    if not isinstance(data, dict) or not isinstance(data.get("rects"), list):
        raise ValueError('region must be {"rects": [{"x1","y1","x2","y2"}]}')
    rects_raw = data["rects"]
    if len(rects_raw) > MAX_REGION_RECTS:
        raise ValueError(f"region rects exceed limit ({MAX_REGION_RECTS})")
    rects = []
    for r in rects_raw:
        if not isinstance(r, dict):
            raise ValueError("each rect must be an object")
        try:
            x1, y1, x2, y2 = int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("each rect requires numeric x1,y1,x2,y2")
        rects.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
    return rects


def clamp_rects(rects, grid: dict | None):
    """맵 메타 규격(치수 범위)을 존중 — 범위 밖 rect는 격자 경계로 클램프한다.

    grid가 없으면(메타 미등록) 클램프 없이 원본 반환. 클램프 후 빈 rect는 제거.
    """
    if not grid:
        return list(rects)
    min_x = int(grid.get("start_x", 1))
    min_y = int(grid.get("start_y", 1))
    max_x = min_x + int(grid.get("cols", 0)) - 1
    max_y = min_y + int(grid.get("rows", 0)) - 1
    out = []
    for (x1, y1, x2, y2) in rects:
        cx1, cy1 = max(x1, min_x), max(y1, min_y)
        cx2, cy2 = min(x2, max_x), min(y2, max_y)
        if cx1 <= cx2 and cy1 <= cy2:
            out.append((cx1, cy1, cx2, cy2))
    return out


def _point_in_rects(x, y, rects) -> bool:
    for (x1, y1, x2, y2) in rects:
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True
    return False


# ---------------------------------------------------------------------------
# 맵 메타(격자 규격) 로드 — config의 map_metadata 블록 경유 (하드코딩 금지)
# ---------------------------------------------------------------------------

def load_map_meta(db, config: dict, target_table: str, map_id: str,
                  cache: dict = None) -> dict | None:
    """(target_table, map_id)의 `grid_metadata` **원본 dict**를 읽는다. 없으면 None.

    `map_overlay.load_map_meta`와 같은 것을 읽지만 테이블·컬럼명을 config의 `map_metadata`
    블록에서 받는다(현장 테이블명 상이 대응 — 하드코딩 금지). 정렬은 이 dict 전체(회전·면·
    y반전·start·치수·phys 6종)에서 유도되므로 격자 치수만 잘라 쓰면 안 된다.

    cache: 요청 경계 스냅샷 딕셔너리. 같은 (table, map_id)를 역할·코어마다 다시 조회하면
    N+1이 된다 — 호출자가 요청당 하나를 만들어 넘긴다.
    """
    key = (target_table, map_id)
    if cache is not None and key in cache:
        return cache[key]

    meta = None
    meta_cfg = config.get("map_metadata")
    if _valid_source(meta_cfg):
        from database import models
        model = models.DYNAMIC_TABLES.get(meta_cfg["table"])
        if model is not None:
            cols_map = meta_cfg["columns"]
            t_col = cols_map.get("target_table", "target_table")
            id_col = cols_map.get("map_id", "map_id")
            g_col = cols_map.get("grid_metadata", "grid_metadata")
            try:
                row = (
                    db.query(getattr(model, g_col))
                    .filter(getattr(model, t_col) == target_table,
                            getattr(model, id_col) == map_id)
                    .first()
                )
                if row and row[0]:
                    meta = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except Exception as e:
                logger.warning("[BondingPlan] map meta load failed (%s/%s): %s",
                               target_table, map_id, e)
                meta = None
    if not isinstance(meta, dict):
        meta = None
    if cache is not None:
        cache[key] = meta
    return meta


def load_grid_meta(db, config: dict, target_table: str, map_id: str,
                   cache: dict = None) -> dict | None:
    """격자 규격만 필요한 호출자용 축약 — {"cols","rows","start_x","start_y"} 또는 None.

    region rect 클램프처럼 **좌표 변환이 아닌** 용도 전용이다. 변환에는 메타 전체가
    필요하므로 `load_map_meta`를 쓴다.
    """
    import map_overlay
    return map_overlay._grid_of(load_map_meta(db, config, target_table, map_id, cache))


# ---------------------------------------------------------------------------
# 기준(canonical) 프레임의 근거 — 층 ⑧을 읽는 **유일한** 자리
# ---------------------------------------------------------------------------

def declared_map_pairs(sources_cfg: dict, map_id_for) -> list:
    """이 계획이 좌표를 바인딩한 소스들의 `(table, map_id)`. 확정 조회의 입력이다.

    좌표를 바인딩한 소스만 담는다 — 좌표가 없는 역할(process_history)은 어떤 프레임에도
    살지 않으므로 「이 맵이 그 합의에 올라갔나」를 물을 대상이 아니다. 순서는 `ROLES`
    선언 순서라 실행마다 같다. 개수는 역할 수 이하이므로 상수다.
    """
    seen, out = set(), []
    for role in ROLES:
        src = (sources_cfg or {}).get(role)
        if not _valid_source(src):
            continue
        cols = src["columns"]
        if "x" not in cols or "y" not in cols:
            continue
        key = (src["table"], map_id_for(src))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def canonical_basis(db, config: dict, map_pairs, meta_cache: dict = None):
    """기준 프레임을 **확정 기록에서** 가져온다 → `(meta|None, basis)`.

    🔴 THE 결정 지점이다. 스펙 §0.2의 사슬(좌표계 확정 → 얼라인 → 다이 맵 → 계획)에서 계획이
    층 ⑧을 읽는 자리는 여기 하나이고, `bonding_plan`·`transfer_plan` 두 경로가 같은 함수를
    부른다 — 두 경로가 서로 다른 프레임을 기준 삼으면 같은 웨이퍼의 수치가 갈린다.

    `meta`가 None이면 호출자는 **종전 퇴화형**(`CANONICAL_FRAME_ROLES` 선언 순서)으로 간다.
    그때도 `basis`는 왜 그 길로 갔는지를 담는다. 어휘는 새로 만들지 않는다:
      `not_declared`        확정이 없다 / 확정은 있는데 기준(공통 바닥)을 선언하지 않았다
      `mapping_unavailable` 기준은 선언돼 있는데 그 선언을 읽지 못했다
    둘을 한 단어로 접으면 운영자가 없는 선언을 채우러 간다(`config_resolve_report` §어휘).

    ⚠️ 재파생을 하지 않는다. 확정이 바뀌었을 때 어느 줄을 다시 만들지는
    `frame_trigger_scope`+`SCOPE_ROW_CAP` · `chain_replay` R1/R2 · `plan_retraction` 셋과
    `frame_confirmation.derived_cell_scope`가 이미 풀었고, 넷째 철자를 만들지 않는다.
    이 함수는 **조회 시점에** 무엇이 기준인지 답할 뿐이다.
    """
    import frame_confirmation

    roles = list(CANONICAL_FRAME_ROLES)
    try:
        header = frame_confirmation.live_confirmation_for_maps(db, map_pairs)
    except Exception as e:
        # 확정 표를 못 읽는 것이 계획을 못 내는 것은 아니다 — 물러나되 **말한다**.
        logger.warning("[BondingPlan] frame confirmation lookup failed: %s", e)
        return None, {"kind": BASIS_ROLE_ORDER,
                      "reason": BINDING_MAPPING_UNAVAILABLE, "roles": roles}
    if header is None:
        return None, {"kind": BASIS_ROLE_ORDER,
                      "reason": STATUS_NOT_DECLARED, "roles": roles}

    basis = {"kind": BASIS_ROLE_ORDER, "roles": roles,
             "confirmation_uid": header.confirmation_uid, "version": header.version}
    ref_table, ref_map_id = header.reference_table, header.reference_map_id
    if not ref_table:
        # 확정은 있는데 **무엇 위에 올려놓고 정했는지**가 비어 있다. 기준 없이 채점한 판은
        # 계획에 기준을 줄 수 없다 (`map_alignment.REFERENCE_ABSENT`는 흔한 상태다).
        basis["reason"] = STATUS_NOT_DECLARED
        return None, basis

    meta = load_map_meta(db, config, ref_table, ref_map_id or "", meta_cache)
    if meta is None:
        basis["reason"] = BINDING_MAPPING_UNAVAILABLE
        basis["reference"] = {"table": ref_table, "map_id": ref_map_id}
        return None, basis

    return meta, {
        "kind": BASIS_CONFIRMATION,
        "confirmation_uid": header.confirmation_uid,
        "version": header.version,
        "reference": {"table": ref_table, "map_id": ref_map_id},
        # 합쳐진 것은 최약 기여자를 따라간다(스펙 §0.2 ⑨). 계산은 층 ⑧이 쓰기 시점에 굳혀
        # 뒀고 여기서 다시 유도하지 않는다.
        "warrant": frame_confirmation.warrant_of(header),
        "weakest": {"source_name": header.weakest_source,
                    "priority": header.weakest_priority},
    }


# ---------------------------------------------------------------------------
# 집계 코어
# ---------------------------------------------------------------------------

class _ResolvedColumns(dict):
    """role-key -> ORM column map, plus `unresolved`: role keys that were DECLARED
    in the config but whose column name does not exist on the model.

    [FIX 2026-07-28] A declared-then-missing optional column used to be silently
    skipped, turning a config typo (e.g. "x": "cxx") into silent aggregate
    corruption. The resolver cannot demote a status itself (it does not know the
    role), so it carries the evidence and each status-setting site composes it via
    `_demote_for_unresolved`. Omitting an optional column entirely is still fine —
    only declared-but-unresolved lands here.
    """
    __slots__ = ("unresolved",)

    def __init__(self, mapping=(), unresolved=()):
        super().__init__(mapping)
        self.unresolved = tuple(unresolved)


def _unresolved_roles(cols) -> tuple:
    """Declared-but-unresolved role keys of a resolved binding ('()' when clean)."""
    return tuple(getattr(cols, "unresolved", ()) or ())


def compose_status_marker(status, marker):
    """Compose one demotion marker into a connected-status.

    THE composer for the `connected(...)` vocabulary (`connected(area_only)`,
    `connected(align_unavailable)`, `connected(column_unresolved:x,y)`): a
    bare `connected` gains parentheses, an already-marked one gains a
    comma-separated term, and an already-degraded status
    (`missing` / `unavailable(...)`) is left exactly as it was. Extracted so a
    second demotion cause cannot grow a second spelling of the same string
    surgery - the defect shape issue #20 keeps producing.
    """
    if not isinstance(status, str) or not status.startswith("connected"):
        return status
    if status == "connected":
        return f"connected({marker})"
    if status.startswith("connected(") and status.endswith(")"):
        return status[:-1] + "," + marker + ")"
    return status


def _demote_for_unresolved(status, cols):
    """Compose the `column_unresolved:<roles>` marker into a connected-status.

    The binding still answers, but a DECLARED column vanished, so the status
    must say so instead of reading `connected`.
    """
    unres = _unresolved_roles(cols)
    if not unres:
        return status
    return compose_status_marker(
        status, "column_unresolved:" + ",".join(sorted(str(r) for r in unres)))


# A `fail_values` list was declared with NO usable `val` column to read it from.
# Sibling of `column_unresolved`, and deliberately a DIFFERENT word: that one
# means "you named a column and the table does not have it" (repair: fix or
# delete the name), this one means "there is no name at all" (repair: declare
# one). Same consequence, different instruction.
FAIL_VALUE_COLUMN_ABSENT = "fail_value_column_absent"


def fail_filter_status(src_cfg, cols, status):
    """Can this source's `fail_values` be applied? -> `(refused, status)`.

    🔴 ONE PREDICATE, EVERY FAIL-COUNTING READER CALLS IT. There are three
    (`bonding_plan.get_core_summary`'s defect/eds_fail roles, and both frames of
    `transfer_plan`'s `fail_sources`), and before board N14 they each spelled
    their own half of the question.

    THE RULING. `fail_values` says WHICH values mean fail; `val` says WHERE to
    read them. Without `val` the question "is this row a fail" is unanswerable -
    and unanswerable is not YES. Counting without the predicate marks the ENTIRE
    pool as fail, which overstates the subtraction and breaks the upper-bound
    invariant the whole availability engine rests on. So: refuse, serve 0, and
    demote - the same discipline as `align_unavailable`.

    Two shapes reach one verdict, each keeping its own name so the operator is
    told what to DO:
      * declared but the column is not on the table -> `column_unresolved:val`
        (composed by `_demote_for_unresolved`, unchanged since 2026-07-28).
      * not declared at all -> `fail_value_column_absent`. This is the shape
        board N14 opened: `8817dde`/`ba65c59` taught operators that deleting a
        declaration is the repair, which is true for a REQUIRED role (derivation
        fills it back) and silently destructive one line further down, because
        an OPTIONAL role is never derived. Deleting `val` used to turn 0 fail
        chips into every chip while the payload still said `reliable: true`.

    A source that declares NO `fail_values` is untouched: the table itself is
    the fail list and counting the whole pool is the point.
    """
    if not (isinstance(src_cfg, dict) and src_cfg.get("fail_values")):
        return False, status
    if cols is not None and "val" in cols:
        return False, status
    if "val" in _unresolved_roles(cols):
        return True, status
    return True, compose_status_marker(status, FAIL_VALUE_COLUMN_ABSENT)


# --- binding refusal vocabulary (borrowed, not invented) -------------------
# The words are the project's existing honest-degradation vocabulary, reused so
# a reader of one refusal already knows what the word means elsewhere:
#   `not_declared`            = config_resolve_report.REASON_NOT_DECLARED
#   `mapping_unavailable`     = config_resolve_report.REASON_MAPPING_UNAVAILABLE
#   `candidate_column_missing`= enrichment_candidates.REASON_CANDIDATE_COLUMN_MISSING
# They are spelled here rather than imported so this module keeps no dependency
# on the admin-report or enrichment stacks; `test_binding_refusal.py` pins each
# one equal to its canonical definition, so an upstream rename cannot leave a
# second spelling behind (the defect shape issue #20 keeps producing).
BINDING_NOT_DECLARED = "not_declared"
BINDING_MAPPING_UNAVAILABLE = "mapping_unavailable"
BINDING_COLUMN_MISSING = "candidate_column_missing"
# `not_reached` = config_resolve_report.REASON_NOT_REACHED. A declaration that a
# switch upstream stops the reader from ever consulting - a stage delegating its
# source roles via `source_config_ref` never reads its own `source.*` block, so
# calling those "not declared" would invite an operator to fill in a block that
# is not consulted. Never produced by `explain_binding_refusal` (which judges one
# declaration in isolation); it belongs to callers that know the switch.
BINDING_NOT_REACHED = "not_reached"
BINDING_REFUSALS = (BINDING_NOT_DECLARED, BINDING_MAPPING_UNAVAILABLE,
                    BINDING_COLUMN_MISSING, BINDING_NOT_REACHED)

# How many of the table's real column names to offer back. The point is "did you
# mean one of these", not a schema dump - a 60-column table would bury the
# sentence that matters.
_REFUSAL_COLUMN_HINTS = 24


def _model_column_names(model) -> list:
    """Real ORM attribute names of a dynamic model, sorted."""
    try:
        return sorted(c.key for c in model.__table__.columns)
    except Exception:            # pragma: no cover - defensive
        return []


# ---------------------------------------------------------------------------
# Derivation - the coordinate/value columns are already declared ONCE, elsewhere
# ---------------------------------------------------------------------------
#
# WHY. `transfer_plan_config` asked the operator to retype, role by role, an
# answer the system already had: `map_overlay_config.json` declares
#   "dt_log": {"columns": {"x": "dt_x", "y": "dt_y", "val": "c_bn", ...}}
# and the plan config asked for `x`/`y`/`bin` again. That retyping is precisely
# where the 2026-08-04 typo landed (`"x": "x"` on a table with `dt_x`). This is
# a third spelling of one fact, not a missing feature.
#
# NO NEW MECHANISM. `map_overlay.resolve_binding_info` already does this job -
# declaration first, `table_config` derivation second, with the winning source
# labelled. `map_overlay_config`'s own comment states the rule being implemented
# here: declare only where columns depart from the convention, because a
# DUPLICATE declaration hides whether the derivation path still works.
#
# WHAT IS NOT DERIVED, on purpose:
#   * `lot` / `slot` (and every other key role). Overlay keys `dt_log` by
#     `dt_job`; the plan keys it by `dt_lot`/`dt_slot`. That difference is real
#     information about purpose, not a convention anyone can infer.
#   * `origin_x` / `origin_y` - a SECOND coordinate pair on the same table. The
#     map binding describes one pair and cannot say which.
#   * ANY role the caller did not mark `required`. This is the load-bearing
#     restriction. An OPTIONAL x/y that the config omits is already information
#     every reader acts on: `transfer_plan._summarize_inline` reads a
#     transfer_log without x/y as `connected(count_only)`, and
#     `_canonical_frame` skips a role that declares no coordinates. Filling
#     those would silently convert a count-only site into set subtraction and
#     change the numbers. Absence is only ever filled where absence would
#     otherwise be a refusal.
DERIVED_ROLE_OF = {"x": "x", "y": "y", "val": "val", "bin": "val"}

# Where a filled column came from, for the operator-facing report. Not a new
# vocabulary - these are `map_overlay.resolve_binding_info`'s own `source`
# values, passed through rather than renamed.
DERIVATION_DECLARED = "map_overlay_declared"
DERIVATION_DERIVED = "map_overlay_derived"
DERIVATION_UNAVAILABLE = "unavailable"

_OVERLAY_MEMO = {"stamp": None, "cfg": None}


def _overlay_config_snapshot() -> dict:
    """`map_overlay_config.json`, memoized on the file's (mtime_ns, size).

    A resolver runs several times per request, so re-reading the file on each
    call would be a per-role disk hit exactly in the configs that adopt the
    shorter form - the ones this change is meant to reward. Keying the memo on
    the file stamp keeps hot-reload (a saved edit changes mtime) while giving
    one read per edit instead of one per role.
    """
    import map_overlay
    path = map_overlay.CONFIG_PATH
    try:
        st = os.stat(path)
        stamp = (path, st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = (path, None, None)
    if _OVERLAY_MEMO["stamp"] != stamp:
        _OVERLAY_MEMO["cfg"] = map_overlay.load_overlay_config(path)
        _OVERLAY_MEMO["stamp"] = stamp
    return _OVERLAY_MEMO["cfg"] or {}


def _map_binding_for(table: str):
    """`(binding|None, source)` for a table, via map_overlay's resolver.

    A `fallback_guess` value column is REFUSED for the value role: map_overlay
    already keeps that guess out of its own data path (`derive_table_binding`
    returns None when guessed) and serves it only as a labelled hint. Feeding a
    guessed column into an availability count would produce a number nobody
    declared - the silent-wrong-answer shape this project keeps paying for. The
    x/y of a guessed binding are still literal or declared, so they stay usable.
    """
    import map_overlay
    info = map_overlay.resolve_binding_info(_overlay_config_snapshot(), table)
    if not isinstance(info, dict):
        return None, DERIVATION_UNAVAILABLE
    src = info.get("source")
    if src == "declared":
        return info, DERIVATION_DECLARED
    if src == "derived":
        return info, DERIVATION_DERIVED
    # fallback_guess: usable for coordinates, never for the value column.
    return {"x": info.get("x"), "y": info.get("y"), "val": None}, DERIVATION_DERIVED


def resolve_effective_columns(source_cfg: dict, required: tuple):
    """`(columns, derivation)` - declared columns plus fills for ABSENT REQUIRED
    derivable roles.

    EXPLICIT ALWAYS WINS, and nothing else changes. A config that declares every
    required role gets its own `columns` mapping back UNCHANGED (same object
    identity, so iteration order and content are byte-identical downstream) and
    an empty `derivation`. Operators never have to edit anything; only a config
    that OMITS a role sees any new behaviour.

    `derivation` is `{role: {"column": str|None, "source": str, "from_role": str,
    "table": str}}` - kept so the dry-run route can show WHICH spelling won
    rather than just "it worked".
    """
    columns = source_cfg.get("columns")
    if not isinstance(columns, dict):
        return columns, {}
    wanted = [r for r in (required or ())
              if r in DERIVED_ROLE_OF and r not in columns]
    if not wanted:
        return columns, {}          # fully declared -> identical object, no fill

    table = source_cfg.get("table")
    binding, source = _map_binding_for(table) if isinstance(table, str) else (None,
                                                                             DERIVATION_UNAVAILABLE)
    out = dict(columns)
    derivation = {}
    for role in wanted:
        col = (binding or {}).get(DERIVED_ROLE_OF[role])
        derivation[role] = {"column": col,
                            "source": source if col else DERIVATION_UNAVAILABLE,
                            "from_role": DERIVED_ROLE_OF[role],
                            "table": table}
        if col:
            out[role] = col
    return out, derivation


def explain_binding_refusal(src_cfg, required: tuple, label: str,
                            where: str = None) -> tuple:
    """왜 이 `{table, columns}` 선언이 해석되지 않았는가 ― `(reason, 한국어 문장)`.

    해석에 성공하면 `(None, None)`.

    WHY THIS EXISTS. `_resolve_model_columns` answers yes/no, and every caller
    used to turn that `no` into one generic sentence ("...가 선언돼 있지 않습니다").
    That sentence is a lie in the most common case: the declaration IS there and
    one column name inside it is wrong. Three times in two weeks a valid-looking
    declaration silently did not take (board O4, board O7, and the 2026-08-04
    live report where `bin_map.columns.x = "x"` named a column `dt_log` does not
    have). A refusal that cannot name its own cause makes every one of those a
    manual bisect. So the refusal names the check that failed, what it looked
    for, and what it found instead.

    THE PREDICATE IS NOT DUPLICATED HERE. The accept/reject decision stays in
    `_resolve_model_columns`; this function only re-walks the same inputs to
    describe the first failing check. If the two ever disagree the sentence is
    wrong but the behaviour is not - and `test_binding_refusal.py` scores them
    against each other so the disagreement cannot go unseen.

    cp949: the console is the delivery path for half of these, so the sentences
    carry no emoji and no U+2014 em dash (U+2015 `―` is safe).
    """
    from database import models

    at = f" (읽는 자리: {where})" if where else ""

    # 1) 선언 자체가 없다. 이것은 결함이 아니라 "이 축을 안 쓴다"는 상태다.
    if src_cfg is None:
        return (BINDING_NOT_DECLARED,
                f"`{label}` 선언이 없습니다{at}. "
                f"이 축을 쓰려면 `table`과 `columns`("
                f"{', '.join(str(r) for r in required)})를 선언해야 합니다.")

    # 2) 선언은 있는데 읽을 수 있는 형태가 아니다.
    if not isinstance(src_cfg, dict):
        return (BINDING_MAPPING_UNAVAILABLE,
                f"`{label}` 선언이 객체가 아닙니다{at}: 읽힌 값은 "
                f"{json.dumps(src_cfg, ensure_ascii=False, default=str)}입니다. "
                f"`{{\"table\": ..., \"columns\": {{...}}}}` 형태여야 합니다.")
    table = src_cfg.get("table")
    columns = src_cfg.get("columns")
    if not (isinstance(table, str) and table):
        return (BINDING_MAPPING_UNAVAILABLE,
                f"`{label}` 선언에 `table`(비어 있지 않은 문자열)이 없습니다{at}: "
                f"읽힌 값은 {json.dumps(table, ensure_ascii=False, default=str)}입니다.")
    if not isinstance(columns, dict):
        return (BINDING_MAPPING_UNAVAILABLE,
                f"`{label}` 선언의 `columns`가 객체가 아닙니다{at}: 읽힌 값은 "
                f"{json.dumps(columns, ensure_ascii=False, default=str)}입니다. "
                f"`{{역할: 실제컬럼명}}` 형태여야 합니다.")

    # 3) 테이블이 table_config.json에 없다 ― "테이블 먼저, 규칙은 그 다음" 함정.
    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        known = sorted(models.DYNAMIC_TABLES.keys())
        return (BINDING_MAPPING_UNAVAILABLE,
                f"`{label}`이(가) 가리키는 테이블 `{table}`이(가) table_config.json에 "
                f"선언돼 있지 않습니다{at}. 선언된 테이블: "
                f"{', '.join(known) if known else '(없음 ― 아직 로드되지 않았습니다)'}.")

    # 4) 필수 역할 키 자체가 columns에 없다.
    #    유도가 메운 역할은 여기서 빠진다 ― 생략은 이제 "관례를 쓰겠다"는 뜻이다.
    #    유도가 **실패한** 역할은 조용히 사라지지 않고 자기 이름으로 거절된다.
    effective, derivation = resolve_effective_columns(src_cfg, required)
    absent_roles = [r for r in required if r not in effective]
    if absent_roles:
        failed = [r for r in absent_roles if r in derivation]
        if failed:
            # 생략했는데 유도도 못 했다. 침묵이 최악이므로 무엇을 어디서 찾았는지 말한다.
            return (BINDING_MAPPING_UNAVAILABLE,
                    f"`{label}`의 필수 역할 {', '.join(str(r) for r in failed)}이(가) "
                    f"선언돼 있지 않고 유도도 되지 않았습니다{at}. "
                    f"`{table}`의 맵 바인딩(map_overlay_config.json의 `table_bindings`, "
                    f"없으면 table_config.json의 x/y 관례)에서 "
                    f"{', '.join(DERIVED_ROLE_OF[r] for r in failed)}을(를) 찾지 "
                    f"못했습니다. 해당 역할을 직접 선언하거나 `{table}`의 맵 바인딩을 "
                    f"선언하세요.")
        return (BINDING_NOT_DECLARED,
                f"`{label}`의 `columns`에 필수 역할 "
                f"{', '.join(str(r) for r in absent_roles)}이(가) 없습니다{at}. "
                f"선언된 역할: "
                f"{', '.join(str(k) for k in columns) if columns else '(없음)'} / "
                f"필요한 역할: {', '.join(str(r) for r in required)}. "
                f"(유도 대상 역할: {', '.join(sorted(DERIVED_ROLE_OF))})")

    # 5) 역할은 선언됐는데 그 이름의 컬럼이 테이블에 없다 ― 라이브에서 가장 흔한 원인.
    bad = [(r, effective[r]) for r in required
           if getattr(model, str(effective[r]), None) is None]
    if bad:
        real = _model_column_names(model)
        shown = real[:_REFUSAL_COLUMN_HINTS]
        more = "" if len(real) <= _REFUSAL_COLUMN_HINTS else f" 외 {len(real) - len(shown)}개"
        pairs = ", ".join(f"{r} → `{c}`" for r, c in bad)
        # 「선언이 이기는」 규칙 때문에, 틀린 선언은 유도가 있어도 계속 이긴다.
        # 그러면 고치는 법이 **지우는 것**이 되는데, 그 말을 안 해주면 운영자는
        # 막다른 길에 선다. 지웠을 때 무엇이 유도될지까지 같이 말한다.
        removable = deletion_hints(src_cfg, [r for r, _c in bad], model)
        tail = ""
        if removable:
            tail = (" 이 역할들은 선언을 **지우면** 유도로 해결됩니다: "
                    + ", ".join(f"{r} → `{c}`" for r, c in removable)
                    + f" (`{table}`의 맵 바인딩에서 유도).")
        return (BINDING_COLUMN_MISSING,
                f"`{label}`의 필수 역할이 가리키는 컬럼이 테이블 `{table}`에 없습니다{at}: "
                f"{pairs}. `{table}`의 실제 컬럼: {', '.join(shown)}{more}.{tail}")

    # 6) 여기까지 왔는데 해석이 실패했다면 규칙이 갈라진 것이다.
    model2, cols = _resolve_model_columns(src_cfg, required=required)
    if model2 is None:
        return (BINDING_MAPPING_UNAVAILABLE,
                f"`{label}` 선언을 해석하지 못했습니다{at}: 개별 검사는 모두 통과했으므로 "
                f"바인딩 규칙이 갈라졌습니다. 서버 로그를 확인하세요.")
    return (None, None)


def deletion_hints(src_cfg: dict, roles, model) -> list:
    """선언을 지웠을 때 **유도로 해결될** 역할들 ― `[(role, 유도될 컬럼)]`.

    「명시 선언이 항상 이긴다」는 규칙의 뒷면이다. 틀린 철자가 적혀 있으면 유도가 존재해도
    계속 진다 ― 그래서 이 파일의 올바른 수리는 *고치기*가 아니라 *지우기*다. 그 말을
    거절 문장과 dry-run 양쪽이 하지 않으면 운영자는 「유도가 있다는데 왜 안 되지」에서
    멈춘다. 실제로 2026-08-04 라이브 파일이 정확히 그 상태다(`"x": "x"`).
    """
    out = []
    for role in roles:
        if role not in DERIVED_ROLE_OF:
            continue
        probe = {"table": src_cfg.get("table"),
                 "columns": {k: v for k, v in (src_cfg.get("columns") or {}).items()
                             if k != role}}
        eff, _d = resolve_effective_columns(probe, (role,))
        col = (eff or {}).get(role)
        if col and getattr(model, str(col), None) is not None:
            out.append((role, col))
    return out


def _resolve_model_columns(source_cfg: dict, required: tuple):
    """소스 config → (model, {역할키: ORM 컬럼}) 해석. 실패 시 (None, None) → missing.

    반환 cols는 `_ResolvedColumns` — 선언됐으나 미해석된 옵션 컬럼을 `.unresolved`로
    실어 나른다(required 미해석은 종전대로 바인딩 전체 실패).

    [derivation] 선언에서 **빠진 필수 역할**만 맵 바인딩으로 메운다
    (`resolve_effective_columns`). 전부 선언된 config는 같은 dict 객체를 그대로 돌려받아
    반복 순서까지 동일하다 ― 기존 config의 동작은 바이트 단위로 불변이다."""
    from database import models
    model = models.DYNAMIC_TABLES.get(source_cfg["table"])
    if model is None:
        return None, None
    columns, _derivation = resolve_effective_columns(source_cfg, required)
    resolved = {}
    unresolved = []
    for role_key, col_name in columns.items():
        col = getattr(model, col_name, None)
        if col is None:
            if role_key in required:
                return None, None
            unresolved.append(str(role_key))
            continue
        resolved[role_key] = col
    if any(k not in resolved for k in required):
        return None, None
    return model, _ResolvedColumns(resolved, unresolved)


def _finite_point(px, py):
    """Is this ONE (x, y) usable as a coordinate?

    🔴 `is not None` IS NOT THAT TEST, AND THAT IS THE DEFECT. A coordinate column is
    `double precision`, so its missing marker on the ORM path is `None` - but a NaN is
    NOT None, it walks straight through such a guard, and the `int()` two lines later
    raises `cannot convert float NaN to integer`. That is the error class the owner hit
    in production on 2026-09-04, in a different place.

    Infinities are excluded for the same reason one line up: `int(inf)` raises too, and a
    coordinate that is infinite is not a coordinate.

    ⚠️ The ordinary write path cannot put a NaN here - `crud.cast_value_by_type` refuses
    nan/inf into a numeric column, and says why. This guards the rows that did not come
    that way, which this repository knows it has: seed scripts have written table rows
    directly. A screen that 500s on one such row is a worse answer than a count that
    skips it, and skipping is what this function already does for `None`.
    """
    if px is None or py is None:
        return False
    return (not (isinstance(px, float) and not math.isfinite(px))
            and not (isinstance(py, float) and not math.isfinite(py)))


def _fetch_points(db, cols, filters, distinct_pairs=False):
    """(x,y) 좌표 페치 — 하드캡 MAX_REGION_POINTS (좌표는 응답에 싣지 않는 내부 연산용)."""
    q = db.query(cols["x"], cols["y"]).filter(*filters)
    if distinct_pairs:
        q = q.distinct()
    pts = q.limit(MAX_REGION_POINTS).all()
    if len(pts) >= MAX_REGION_POINTS:
        logger.warning("[BondingPlan] region point fetch hit hard cap (%d) — counts may be truncated", MAX_REGION_POINTS)
    return pts


def get_core_summary(db, lot: str, slot: str, rects=None, config: dict = None) -> dict:
    """코어 (lot, slot) 집계 — 계약 §C 응답 dict를 생성한다.

    rects: parse_region 결과(canonical 칩 좌표계) 또는 None.
    config: 요청 경계 스냅샷(미지정 시 여기서 1회 로드).
    """
    import map_overlay

    cfg = config if config is not None else load_bonding_plan_config()
    sources_cfg = cfg.get("sources") or {}

    identity_cols = (cfg.get("core_identity") or {}).get("compose") or ["lot", "slot"]
    identity_vals = {"lot": lot, "slot": slot}

    def _map_id_for(src):
        # [7b] Map identity canonicalized per the looked-up table's DECLARED
        # column types — meta was registered from that table's stored values, so
        # a parsed token '01' must compose as '1' when slot is number-declared.
        # THE composer is map_overlay.compose_map_id (no second implementation).
        return map_overlay.compose_map_id(identity_cols, identity_vals, src)

    statuses = {}
    counts = {"total": 0, "defect": 0, "eds_fail": 0, "used": 0}
    region_counts = {"total": 0, "defect": 0, "eds_fail": 0, "used": 0} if rects is not None else None
    history = []
    warnings_out = []
    meta_cache = {}          # 요청 경계 스냅샷 — 같은 (table, map_id) 재조회 금지

    # ---- canonical(CORE) 프레임 ----
    # 좌표를 바인딩한 **첫** 맵 모드 역할이 기준 프레임을 정의한다. 그 역할의 메타가
    # 없으면 canonical은 None으로 남는다 — **뒤 역할로 넘어가지 않는다.**
    #
    # ⚠️ 넘어가면, 회전된 계측 맵이 스스로 기준을 참칭한다. 그러면 소스 == 기준이 되어
    # 변환이 identity로 떨어지고, 상태는 `connected`인 채 좌표가 어긋난 과소 집계가 된다
    # (조용한 오답). 기준을 모르면 모른다고 해야 한다 — 아래에서 align_unavailable이 된다.
    #
    # [층 ⑧ 2026-08-05] 확정 기록이 있으면 **그것이 답이고** 아래 퇴화형 루프는 상의되지
    # 않는다. 없으면 종전 경로 그대로다 — 다만 조용히 같아 보이면 안 되므로 어느 길로
    # 왔는지를 payload의 `frame_basis`가 말한다.
    canonical_meta, frame_basis = canonical_basis(
        db, cfg, declared_map_pairs(sources_cfg, _map_id_for), meta_cache)
    if canonical_meta is None:
        for role in CANONICAL_FRAME_ROLES:
            src = sources_cfg.get(role)
            if _valid_source(src) and "x" in src["columns"] and "y" in src["columns"]:
                canonical_meta = load_map_meta(db, cfg, src["table"], _map_id_for(src),
                                               meta_cache)
                break
    canonical_grid = map_overlay._grid_of(canonical_meta)

    # [중간 등급] 확정 위에 서 있지만 그 판의 최약 기여자가 서열 미등재면 「정렬은 됐는데
    # 근거가 약함」이다. 종전에는 `connected`와 `connected(align_unavailable)` 둘뿐이라 이
    # 상태를 어느 한쪽으로 반올림할 수밖에 없었다. **여섯째 토큰을 만들지 않고** 이미 있는
    # `not_declared`를 마커로 얹는다 — 그 단어의 뜻(선언이 없다) 그대로다.
    warrant_marker = (STATUS_NOT_DECLARED
                      if frame_basis.get("warrant") == STATUS_NOT_DECLARED else None)

    clamped_rects = clamp_rects(rects, canonical_grid) if rects is not None else None

    # ---- 맵 모드 카운트 소스 3종 (defect / eds_fail / total_chips) ----
    map_roles = {"defect": "defect", "eds_fail": "eds_fail", "total_chips": "total"}
    for role, count_key in map_roles.items():
        src = sources_cfg.get(role)
        if not _valid_source(src):
            # [relaxation] absent auxiliary declaration = the site keeps no such
            # table → not a degradation. total_chips stays required (denominator).
            statuses[role] = ("missing"
                              if (role == "total_chips"
                                  or role_is_declared(sources_cfg, role))
                              else STATUS_NOT_DECLARED)
            continue
        model, cols = _resolve_model_columns(src, required=("lot", "slot"))
        if model is None:
            statuses[role] = "missing"
            continue

        # [정렬] 소스 메타 ↔ canonical 메타의 델타에서 유도한다(선언 레이어 없음).
        # 변환을 만들 수 없으면(치수 비호환·phys 미등록) 조용히 raw 좌표로 계산하지 않고
        # align_unavailable로 표면화한다.
        map_id = _map_id_for(src)          # [7b] per-table canonical identity
        src_meta = load_map_meta(db, cfg, src["table"], map_id, meta_cache)
        transform = None
        align, align_ok = None, True
        if src_meta is not None and canonical_meta is None:
            # [비대칭 지식] 이 맵의 프레임은 아는데 **기준 프레임을 모른다**. 둘 다 모르면
            # "차이가 없다고 볼 수밖에 없다"(identity)가 성립하지만, 한쪽만 알 때 identity로
            # 가정하는 건 근거가 없다 — 회전 180 맵을 무보정으로 세는 조용한 오답이 된다.
            logger.warning("[BondingPlan] canonical frame unregistered while '%s' declares its "
                           "own (%s/%s) — refusing to assume identity", role, src["table"], map_id)
            align_ok = False
        else:
            try:
                transform, align, _origin, _note = map_overlay.resolve_map_transform(
                    src_meta, canonical_meta)
            except ValueError as ve:
                logger.warning("[BondingPlan] frame transform unavailable for '%s' (%s/%s): %s",
                               role, src["table"], map_id, ve)
                align, align_ok = None, False

        if not align_ok:
            # 카운트(total/defect/eds)는 변환 불변이라 유효하지만, 좌표를 canonical로 옮길
            # 수 없다는 사실은 region 조회 여부와 무관하게 드러나야 한다.
            status = "connected(align_unavailable)"
        else:
            status = "connected"
            marker = map_overlay.align_status_label(align)
            if marker:
                status = f"connected({marker})"
            # 정렬이 성립한 경우에만 붙인다 — 정렬 자체가 안 됐으면 「정렬됐으나 약함」은
            # 참이 아니고, 그 상태는 이미 `align_unavailable`이 말한다.
            if warrant_marker:
                status = compose_status_marker(status, warrant_marker)

        # [7b] pool binds canonicalized by the bound column's declared type
        filters = [cols["lot"] == map_overlay.canonical_role_value(src, "lot", lot),
                   cols["slot"] == map_overlay.canonical_role_value(src, "slot", slot)]
        fail_values = src.get("fail_values")
        # [N14 2026-08-04] Counting without the fail-value filter would count
        # EVERY row as fail. THE predicate decides, for both shapes of "no usable
        # `val`" (declared-but-unresolvable, and deleted) - see
        # `fail_filter_status`. Same discipline as align_unavailable: refuse,
        # serve 0, demote.
        refused, refusal_status = fail_filter_status(src, cols, status)
        if refused:
            statuses[role] = _demote_for_unresolved(refusal_status, cols)
            counts[count_key] = 0
            if region_counts is not None:
                region_counts[count_key] = 0
            continue
        if fail_values:
            filters.append(cols["val"].in_([str(v) for v in fail_values]))

        try:
            counts[count_key] = int(db.query(model).filter(*filters).count())

            if region_counts is not None:
                if "x" in cols and "y" in cols:
                    if not align_ok:
                        # [QA 감사 F2 취지] 규격 불명 시 조용히(raw 좌표로) 계산하지 않는다
                        region_counts[count_key] = 0
                    else:
                        pts = _fetch_points(db, cols, filters)
                        n = 0
                        for (px, py) in pts:
                            if not _finite_point(px, py):
                                continue
                            cx, cy = transform(px, py) if transform else (int(px), int(py))
                            if _point_in_rects(cx, cy, clamped_rects):
                                n += 1
                        region_counts[count_key] = n
                else:
                    # 좌표 미바인딩 소스는 영역 교차 불가 — 0으로 집계 (보고서 명시)
                    region_counts[count_key] = 0
        except Exception as e:
            logger.warning("[BondingPlan] role '%s' query failed: %s", role, e)
            statuses[role] = "missing"
            counts[count_key] = 0
            if region_counts is not None:
                region_counts[count_key] = 0
            continue

        statuses[role] = _demote_for_unresolved(status, cols)

    # ---- used_chips (본딩 로그 — 좌표 있으면 distinct 칩, 없으면 행 수) ----
    src = sources_cfg.get("used_chips")
    if not _valid_source(src):
        statuses["used_chips"] = ("missing"
                                  if role_is_declared(sources_cfg, "used_chips")
                                  else STATUS_NOT_DECLARED)
    else:
        model, cols = _resolve_model_columns(src, required=("lot", "slot"))
        if model is None:
            statuses["used_chips"] = "missing"
        else:
            # [7b] canonical pool bind
            filters = [cols["lot"] == map_overlay.canonical_role_value(src, "lot", lot),
                       cols["slot"] == map_overlay.canonical_role_value(src, "slot", slot)]
            try:
                if "x" in cols and "y" in cols:
                    pts = _fetch_points(db, cols, filters, distinct_pairs=True)
                    pts = [(int(px), int(py)) for (px, py) in pts
                           if _finite_point(px, py)]
                    counts["used"] = len(set(pts))
                    if region_counts is not None:
                        region_counts["used"] = sum(
                            1 for (px, py) in set(pts) if _point_in_rects(px, py, clamped_rects)
                        )
                else:
                    counts["used"] = int(db.query(model).filter(*filters).count())
                    if region_counts is not None:
                        region_counts["used"] = 0
                statuses["used_chips"] = _demote_for_unresolved("connected", cols)
            except Exception as e:
                logger.warning("[BondingPlan] role 'used_chips' query failed: %s", e)
                statuses["used_chips"] = "missing"
                counts["used"] = 0

    # ---- process_history (최근 50건, 시간 오름차순) + warnings ----
    src = sources_cfg.get("process_history")
    if not _valid_source(src):
        statuses["process_history"] = ("missing"
                                       if role_is_declared(sources_cfg, "process_history")
                                       else STATUS_NOT_DECLARED)
    else:
        model, cols = _resolve_model_columns(src, required=("lot", "slot"))
        if model is None:
            statuses["process_history"] = "missing"
        else:
            try:
                # [7b] canonical pool bind
                q = db.query(model).filter(
                    cols["lot"] == map_overlay.canonical_role_value(src, "lot", lot),
                    cols["slot"] == map_overlay.canonical_role_value(src, "slot", slot))
                if "time" in cols:
                    q = q.order_by(cols["time"].desc())
                rows = q.limit(HISTORY_LIMIT).all()
                rows.reverse()  # 시간 오름차순 (계약)

                col_names = src["columns"]
                fail_values = set((cfg.get("warnings") or {}).get("result_fail_values") or [])
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
                            knobs = knobs_raw  # 파싱 실패 → raw 문자열 폴백 (에러 아님)

                    entry = {
                        "step": _get("step"),
                        "eqp": _get("eqp"),
                        "result": _get("result"),
                        "time": _get("time"),
                        "recipe": _get("recipe"),
                        "knobs": knobs,
                    }
                    history.append(entry)

                    if fail_values and entry["result"] in fail_values:
                        warnings_out.append({
                            "type": "result_fail",
                            "detail": f"{entry['step']} {entry['result']} @{entry['eqp']} {entry['time']}",
                        })
                statuses["process_history"] = _demote_for_unresolved("connected", cols)
            except Exception as e:
                logger.warning("[BondingPlan] role 'process_history' query failed: %s", e)
                statuses["process_history"] = "missing"

    # ---- remaining = total − defect − eds_fail − used (missing 역할은 0으로 계산) ----
    counts["remaining"] = counts["total"] - counts["defect"] - counts["eds_fail"] - counts["used"]

    result = {
        "identity": {"lot": lot, "slot": slot},
        "sources": {role: statuses.get(role, "missing") for role in ROLES},
        "chips": counts,
        "history": history,
        "warnings": warnings_out,
    }
    # [relaxation — honest degradation] subtraction kinds that were never
    # declared did not enter the remaining arithmetic. Name them instead of
    # letting a gross figure pose as net. Field is present only when non-empty
    # (fully-declared configs keep a byte-identical payload).
    inactive = [r for r in SUBTRACTION_ROLES
                if statuses.get(r) == STATUS_NOT_DECLARED]
    if inactive:
        result["inactive_subtractions"] = inactive
    # [층 ⑧] 이 계획이 **무엇 위에 서 있는가**. 확정 기록이 지목했는지, 확정이 없어 config
    # 선언 순서(퇴화형)로 골랐는지. **항상 싣는다** — 퇴화형이 확정과 똑같이 보이는 것이
    # 바로 이 사슬이 없애려는 상태다. 기존 키는 한 글자도 바뀌지 않는 추가 전용 필드다.
    result["frame_basis"] = frame_basis
    if region_counts is not None:
        region_counts["remaining"] = (
            region_counts["total"] - region_counts["defect"]
            - region_counts["eds_fail"] - region_counts["used"]
        )
        result["region_chips"] = region_counts
    return result
