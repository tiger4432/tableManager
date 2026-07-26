"""본딩 실험계획(M1) — 역할 바인딩 config 로더 + 코어 집계 코어.

[역할] map editor "본딩 실험계획 Info 창"(조회 전용)의 서버측 집계 엔진.
`server/config/bonding_plan_config.json`(사용자 config, gitignored)이 역할(role)→실테이블
바인딩을 정의하고, 이 모듈은 그 바인딩만 경유해 집계한다 — 실테이블명 하드코딩 금지
(실 운영 테이블명 상이 대응).

[경계 계약 — 총괄 고정] GET /api/bonding-plan/core-summary 응답 형태는 지시서
Server_bonding_plan_m1_task.md §C. 칩 좌표 목록은 절대 반환하지 않는다(집계만).

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
import json
import logging
import os

logger = logging.getLogger(__name__)

import paths  # single override point (ASSY_DATA_ROOT)
CONFIG_PATH = paths.config_path("bonding_plan_config.json")

ROLES = ("process_history", "defect", "eds_fail", "used_chips", "total_chips")
HISTORY_LIMIT = 50          # history 최근 N건 상한 (계약)
MAX_REGION_RECTS = 50       # region 사각형 개수 상한 (페이로드/연산 방어)
MAX_REGION_POINTS = 100_000  # 영역 교차용 내부 좌표 페치 하드캡 (무제한 로드 금지)

# canonical(CORE) 프레임 후보 — **좌표를 바인딩한 첫 역할**이 기준 프레임을 정의한다.
# 코어 웨이퍼 자신의 맵이 앞에 오도록 정렬돼 있다(used_chips의 (cx,cy)가 사는 프레임).
CANONICAL_FRAME_ROLES = ("total_chips", "defect", "eds_fail")


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
# 집계 코어
# ---------------------------------------------------------------------------

def _resolve_model_columns(source_cfg: dict, required: tuple):
    """소스 config → (model, {역할키: ORM 컬럼}) 해석. 실패 시 (None, None) → missing."""
    from database import models
    model = models.DYNAMIC_TABLES.get(source_cfg["table"])
    if model is None:
        return None, None
    resolved = {}
    for role_key, col_name in source_cfg["columns"].items():
        col = getattr(model, col_name, None)
        if col is None:
            if role_key in required:
                return None, None
            continue
        resolved[role_key] = col
    if any(k not in resolved for k in required):
        return None, None
    return model, resolved


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
    map_id = "_".join(str(identity_vals.get(k, "")) for k in identity_cols)

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
    canonical_meta = None
    for role in CANONICAL_FRAME_ROLES:
        src = sources_cfg.get(role)
        if _valid_source(src) and "x" in src["columns"] and "y" in src["columns"]:
            canonical_meta = load_map_meta(db, cfg, src["table"], map_id, meta_cache)
            break
    canonical_grid = map_overlay._grid_of(canonical_meta)

    clamped_rects = clamp_rects(rects, canonical_grid) if rects is not None else None

    # ---- 맵 모드 카운트 소스 3종 (defect / eds_fail / total_chips) ----
    map_roles = {"defect": "defect", "eds_fail": "eds_fail", "total_chips": "total"}
    for role, count_key in map_roles.items():
        src = sources_cfg.get(role)
        if not _valid_source(src):
            statuses[role] = "missing"
            continue
        model, cols = _resolve_model_columns(src, required=("lot", "slot"))
        if model is None:
            statuses[role] = "missing"
            continue

        # [정렬] 소스 메타 ↔ canonical 메타의 델타에서 유도한다(선언 레이어 없음).
        # 변환을 만들 수 없으면(치수 비호환·phys 미등록) 조용히 raw 좌표로 계산하지 않고
        # align_unavailable로 표면화한다.
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

        filters = [cols["lot"] == lot, cols["slot"] == slot]
        fail_values = src.get("fail_values")
        if fail_values and "val" in cols:
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
                            if px is None or py is None:
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

        statuses[role] = status

    # ---- used_chips (본딩 로그 — 좌표 있으면 distinct 칩, 없으면 행 수) ----
    src = sources_cfg.get("used_chips")
    if not _valid_source(src):
        statuses["used_chips"] = "missing"
    else:
        model, cols = _resolve_model_columns(src, required=("lot", "slot"))
        if model is None:
            statuses["used_chips"] = "missing"
        else:
            filters = [cols["lot"] == lot, cols["slot"] == slot]
            try:
                if "x" in cols and "y" in cols:
                    pts = _fetch_points(db, cols, filters, distinct_pairs=True)
                    pts = [(int(px), int(py)) for (px, py) in pts if px is not None and py is not None]
                    counts["used"] = len(set(pts))
                    if region_counts is not None:
                        region_counts["used"] = sum(
                            1 for (px, py) in set(pts) if _point_in_rects(px, py, clamped_rects)
                        )
                else:
                    counts["used"] = int(db.query(model).filter(*filters).count())
                    if region_counts is not None:
                        region_counts["used"] = 0
                statuses["used_chips"] = "connected"
            except Exception as e:
                logger.warning("[BondingPlan] role 'used_chips' query failed: %s", e)
                statuses["used_chips"] = "missing"
                counts["used"] = 0

    # ---- process_history (최근 50건, 시간 오름차순) + warnings ----
    src = sources_cfg.get("process_history")
    if not _valid_source(src):
        statuses["process_history"] = "missing"
    else:
        model, cols = _resolve_model_columns(src, required=("lot", "slot"))
        if model is None:
            statuses["process_history"] = "missing"
        else:
            try:
                q = db.query(model).filter(cols["lot"] == lot, cols["slot"] == slot)
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
                statuses["process_history"] = "connected"
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
    if region_counts is not None:
        region_counts["remaining"] = (
            region_counts["total"] - region_counts["defect"]
            - region_counts["eds_fail"] - region_counts["used"]
        )
        result["region_chips"] = region_counts
    return result
