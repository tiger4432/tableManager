"""본딩 실험계획(M1) — 역할 바인딩 config 로더 + 코어 집계 코어.

[역할] map editor "본딩 실험계획 Info 창"(조회 전용)의 서버측 집계 엔진.
`server/config/bonding_plan_config.json`(사용자 config, gitignored)이 역할(role)→실테이블
바인딩을 정의하고, 이 모듈은 그 바인딩만 경유해 집계한다 — 실테이블명 하드코딩 금지
(실 운영 테이블명 상이 대응).

[경계 계약 — 총괄 고정] GET /api/bonding-plan/core-summary 응답 형태는 지시서
Server_bonding_plan_m1_task.md §C. 칩 좌표 목록은 절대 반환하지 않는다(집계만).

[align — canonical frame 규약] defect/EDS 계측 맵은 코어 맵과 좌표계가 다를 수 있다
(회전·플립·오프셋). 맵 모드 소스의 `align` 블록이 소스 프레임→canonical(CORE) 프레임
변환을 선언하고, 집계는 로드 단에서 좌표를 canonical로 사상한 뒤 영역 교차를 계산한다.
회전/면반전 불변식은 기존 맵 에디터 자산(utils.coordinate_transformer)을 재사용한다.
  - 단순형: {"rotation": 180, "flip": "none|x|y", "offset": {"x": 0, "y": 0}}
  - 확장형: {"default": {...단순형...}, "by_eqp": {"METRO-A": {...}}}
    → M1은 default만 적용, by_eqp는 파싱만 통과(M2 장비별 적용 예약).
  - 변환 함수(make_align_transform)는 align 파라미터를 외부 주입받는다 —
    M2 "align 보정 모드"(시험 align 오버레이)가 동일 경로를 재사용한다.

[스냅샷 규율] config는 요청(작업) 경계에서 1회 로드해 전 구간에 인자로 전달한다.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "bonding_plan_config.json")

ROLES = ("process_history", "defect", "eds_fail", "used_chips", "total_chips")
HISTORY_LIMIT = 50          # history 최근 N건 상한 (계약)
MAX_REGION_RECTS = 50       # region 사각형 개수 상한 (페이로드/연산 방어)
MAX_REGION_POINTS = 100_000  # 영역 교차용 내부 좌표 페치 하드캡 (무제한 로드 금지)

VALID_ROTATIONS = (0, 90, 180, 270)
VALID_FLIPS = ("none", "x", "y")


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
# align 정규화/변환 (M2 재사용 대비: align 파라미터 외부 주입형)
# ---------------------------------------------------------------------------

def normalize_align(raw) -> dict | None:
    """align 블록(단순형/확장형)을 정규 dict로 변환한다. 미선언/무효 → None(identity).

    반환: {"rotation": int, "flip": str, "offset_x": int, "offset_y": int,
           "is_identity": bool, "by_eqp": dict}
    확장형의 by_eqp는 파싱만 통과시켜 보존한다(M1 집계는 default만 적용 — M2 예약).
    """
    if not isinstance(raw, dict):
        return None

    by_eqp = {}
    base = raw
    if "default" in raw or "by_eqp" in raw:
        base = raw.get("default")
        if isinstance(raw.get("by_eqp"), dict):
            by_eqp = raw["by_eqp"]
        if not isinstance(base, dict):
            base = {}

    rotation = base.get("rotation", 0)
    try:
        rotation = int(rotation)
    except (TypeError, ValueError):
        rotation = 0
    if rotation not in VALID_ROTATIONS:
        logger.warning("[BondingPlan] invalid align rotation %r — coerced to 0", base.get("rotation"))
        rotation = 0

    flip = base.get("flip", "none")
    if flip not in VALID_FLIPS:
        logger.warning("[BondingPlan] invalid align flip %r — coerced to 'none'", base.get("flip"))
        flip = "none"

    offset = base.get("offset") or {}
    if not isinstance(offset, dict):
        offset = {}
    try:
        off_x = int(offset.get("x", 0) or 0)
        off_y = int(offset.get("y", 0) or 0)
    except (TypeError, ValueError):
        off_x, off_y = 0, 0

    return {
        "rotation": rotation,
        "flip": flip,
        "offset_x": off_x,
        "offset_y": off_y,
        "is_identity": (rotation == 0 and flip == "none" and off_x == 0 and off_y == 0),
        "by_eqp": by_eqp,
    }


def align_status_label(align: dict | None) -> str | None:
    """sources 상태 문자열용 align 마커 (예: 'aligned:180', 'aligned:180,flip-x,offset')."""
    if not align or align.get("is_identity"):
        return None
    parts = []
    if align["rotation"]:
        parts.append(str(align["rotation"]))
    if align["flip"] != "none":
        parts.append(f"flip-{align['flip']}")
    if align["offset_x"] or align["offset_y"]:
        parts.append("offset")
    return "aligned:" + ",".join(parts)


def make_align_transform(align: dict | None, src_grid: dict, dst_grid: dict = None):
    """소스 프레임 좌표 → canonical 프레임 좌표 변환 함수를 생성한다.

    align은 외부 주입(config default든 M2 시험값이든 동일 경로 — M2 align 보정 모드 재사용).
    src_grid: 소스 자기 프레임 격자 규격 {"cols","rows","start_x","start_y"} — **grid meta에서
    읽는다**(프리셋은 phys 규격만 보유 — QA 감사 지시 §3). dst_grid: canonical 프레임 규격
    (미지정 시 src와 동일 규격 가정).

    회전·면반전 산법은 utils.coordinate_transformer.WaferMapCoordinateTransformer.cell_to_physical
    재사용(맵 에디터와 동일 불변식) — **순수 인덱스 변환만 사용**하며 엔진 마스크/타원 fallback
    (`is_inside_wafer`/bbox — QA 감사 F1·F2의 결함 지점)은 이 경로에 참여하지 않는다.
    - transformer 생성자 cols/rows는 canonical(물리) 치수 규약: rot 90/270에서 소스 자기 프레임
      치수는 canonical의 스왑이므로 src_grid 치수를 스왑해 전달한다(비정방 격자 정합).
    - flip 'y'는 변환기 시각 계층(invert_y) 소관이라 cell 단 pre-flip으로 보충.
    - offset은 canonical 사상 후 가산(칩 인덱스 단위 — phys 오프셋 불변 관례와 별개 축).
    """
    if not align or align.get("is_identity"):
        return lambda x, y: (int(x), int(y))

    src_cols = int(src_grid.get("cols", 0))
    src_rows = int(src_grid.get("rows", 0))
    src_start_x = int(src_grid.get("start_x", 1))
    src_start_y = int(src_grid.get("start_y", 1))
    if src_cols <= 0 or src_rows <= 0:
        raise ValueError("align transform requires positive source grid dims")

    dst = dst_grid or {}
    dst_start_x = int(dst.get("start_x", src_start_x))
    dst_start_y = int(dst.get("start_y", src_start_y))

    from utils.coordinate_transformer import WaferMapCoordinateTransformer

    rotation = align["rotation"]
    # canonical(물리) 치수 = rot 90/270이면 소스 자기 프레임 치수의 스왑
    if rotation in (90, 270):
        phys_cols, phys_rows = src_rows, src_cols
    else:
        phys_cols, phys_rows = src_cols, src_rows

    # canonical(dst) 프레임 치수가 선언돼 있으면 회전 관계와 정합해야 한다 (불명확한 사상 방지)
    dst_cols = int(dst.get("cols", 0))
    dst_rows = int(dst.get("rows", 0))
    if dst_cols and dst_rows and (dst_cols != phys_cols or dst_rows != phys_rows):
        raise ValueError(
            f"align frame dims mismatch: source {src_cols}x{src_rows} rotated {rotation} "
            f"maps to {phys_cols}x{phys_rows}, but canonical grid is {dst_cols}x{dst_rows}"
        )

    transformer = WaferMapCoordinateTransformer(
        cols=phys_cols,
        rows=phys_rows,
        rotation=rotation,
        side="back" if align["flip"] == "x" else "front",
    )

    flip_y = align["flip"] == "y"
    off_x, off_y = align["offset_x"], align["offset_y"]
    visual_rows = transformer.visual_rows

    def to_canonical(x, y):
        c = int(x) - src_start_x
        r = int(y) - src_start_y
        if flip_y:
            r = (visual_rows - 1) - r
        xp, yp = transformer.cell_to_physical(c, r)
        return xp + dst_start_x + off_x, yp + dst_start_y + off_y

    return to_canonical


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

def load_grid_meta(db, config: dict, target_table: str, map_id: str) -> dict | None:
    """wafer_map_metadata 관례 테이블에서 (target_table, map_id)의 격자 규격을 읽는다.

    반환: {"cols","rows","start_x","start_y"} 또는 None(메타 미등록/블록 미선언).
    """
    meta_cfg = config.get("map_metadata")
    if not _valid_source(meta_cfg):
        return None
    from database import models
    model = models.DYNAMIC_TABLES.get(meta_cfg["table"])
    if model is None:
        return None
    cols_map = meta_cfg["columns"]
    t_col = cols_map.get("target_table", "target_table")
    id_col = cols_map.get("map_id", "map_id")
    g_col = cols_map.get("grid_metadata", "grid_metadata")
    try:
        row = (
            db.query(getattr(model, g_col))
            .filter(getattr(model, t_col) == target_table, getattr(model, id_col) == map_id)
            .first()
        )
    except Exception as e:
        logger.warning("[BondingPlan] grid meta query failed (%s/%s): %s", target_table, map_id, e)
        return None
    if not row or not row[0]:
        return None
    try:
        meta = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return {
            "cols": int(meta["grid_cols"]),
            "rows": int(meta["grid_rows"]),
            "start_x": int(meta.get("grid_start_x", 1)),
            "start_y": int(meta.get("grid_start_y", 1)),
        }
    except Exception as e:
        logger.warning("[BondingPlan] grid meta parse failed (%s/%s): %s", target_table, map_id, e)
        return None


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

    # ---- canonical 격자 규격: align 없는 맵 모드 소스(코어 프레임)의 메타 우선 ----
    canonical_grid = None
    for role in ("total_chips", "defect", "eds_fail"):
        src = sources_cfg.get(role)
        if _valid_source(src) and normalize_align(src.get("align")) is None:
            canonical_grid = load_grid_meta(db, cfg, src["table"], map_id)
            if canonical_grid:
                break

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

        align = normalize_align(src.get("align"))
        status = "connected"
        marker = align_status_label(align)
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
                    transform = None
                    align_ok = True
                    if align and not align.get("is_identity"):
                        # [QA 감사 §3] align 규격은 프리셋이 아니라 grid meta에서 읽는다
                        src_grid = load_grid_meta(db, cfg, src["table"], map_id) or canonical_grid
                        try:
                            if src_grid:
                                transform = make_align_transform(align, src_grid, canonical_grid)
                            else:
                                align_ok = False
                        except ValueError as ve:
                            logger.warning("[BondingPlan] align transform build failed for '%s': %s", role, ve)
                            align_ok = False
                    if not align_ok:
                        # [QA 감사 F2 취지] 규격 불명 시 조용히(raw 좌표로) 계산하지 않고 명시 실패
                        status = "connected(align_unavailable)"
                        region_counts[count_key] = 0
                        logger.warning(
                            "[BondingPlan] align declared for '%s' but frame spec unresolved (%s/%s) — region count omitted",
                            role, src["table"], map_id,
                        )
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
