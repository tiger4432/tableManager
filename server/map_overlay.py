"""범용 맵 오버레이 (S1') — 임의의 맵을 임의의 맵 캔버스 위에 정렬해 겹쳐 보는 인프라.

[성격] 이것은 **계획(transfer plan) 전용 기능이 아니다.** 어떤 맵 테이블이든 다른 맵 위에
겹쳐 볼 수 있는 일반 능력이고, 계획 UI는 그 소비자 중 하나일 뿐이다. 따라서 특정 테이블명을
하드코딩하지 않으며, 엔드포인트도 맵 네임스페이스(`/api/maps/overlay`)에 둔다.

[정렬의 정본 — 맵 자신의 규격에서 자동 유도]
각 맵은 이미 `wafer_map_metadata.grid_metadata`에 **자기 좌표계**를 선언하고 있다
(`grid_cols/rows`, `grid_start_x/y`, `rotation`, `side`). 따라서 소스→타깃 변환은 별도
선언 없이 **두 맵의 메타 차이로 유도**된다:

    상대 회전 = (source.rotation − target.rotation) mod 360
    상대 플립 = source.side != target.side 이면 x 반전

이것이 "map meta가 서로 달라도 align해서 붙게"의 구현이다. align을 계획 config에 적어두면
그 계획에서만 붙으므로 범용성이 깨진다 — 맵의 속성에서 유도하는 편이 옳다.
(예: `eds_fail_map`은 메타 rotation 180, `core_defect_map`은 0 → 상대 180이 자동 유도된다.)

[align 판정 규율 — 총괄 확정]
1. 두 맵 메타로 변환을 **유도할 수 있으면 유도한 대로 적용**한다(origin: "derived").
2. override config에 선언이 있으면 그것이 우선한다(origin: "declared"/"default").
3. 유도할 근거가 없으면(메타 부재 등) **identity로 간주해 그대로 붙인다**(origin: "identity").
   선언 부재는 실패가 아니다 — 그렇게 처리하면 대부분의 맵이 못 붙는다.
4. `align_unavailable`은 "**변환을 계산할 근거가 없을 때**"만 낸다 — 유도/선언된 비-identity
   변환이 있는데 격자 규격이 비호환이라 계산이 불가능한 경우(치수 모순 등).
`by_eqp` 선언이 있고 해당 장비 키가 없으면 `default`로, `default`도 없으면 identity로 폴백하되
그 사실을 status에 **정보성으로만** 표기한다(차단하지 않는다).

[알려진 한계 — 정직한 단서 (QA 재검수 B3/O2/O3)]
1. **면 반전 + 타깃 회전 90/270은 유도 불가**다. `cell_to_physical`의 back 반전 축이 프레임
   자신의 회전에 따라 달라져(90/270이면 행, 아니면 열) "상대 회전 + 단일 flip" 하나로는 두
   프레임의 반전 축을 표현할 수 없다. 이 조합은 `align_unavailable`로 **거절**한다 —
   전수 대조(64조합)에서 16개가 조용한 거울상 오답이었기 때문이다. 근본 수정(각 프레임을
   물리 좌표로 각각 사상 후 합성)은 백로그.
2. `grid_cols/rows`를 **프레임 치수**로 해석한다. 맵 자신이 90/270 회전인데 메타에 물리
   치수로 적혀 있으면 비정방 격자에서 과도한 `align_unavailable`이 날 수 있다(정방 격자는 무해).
3. 두 맵의 `grid_start_x/y` 차이는 현재 보정하지 않는다(라이브는 전부 start=(1,1)).

[변환 어댑터] `bonding_plan.make_align_transform` 재사용 — 순수 인덱스 변환만 사용하며
엔진 마스크/타원 fallback은 참여하지 않는다(QA 감사 F1·F2). 90/270은 치수 스왑 규약.

[페이로드 규율] 셀 목록을 반환하는 유일한 API이므로 상한이 필수다. 캡 도달 시 **응답에 명시**
표기한다(조용한 절단 금지 — QA F2 규율).
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "map_overlay_config.json")

MAX_OVERLAY_CELLS = 20_000     # 오버레이 1종당 셀 상한 (초과 시 truncated 표기)
MAX_OVERLAY_SOURCES = 8        # 요청당 소스 맵 개수 상한

STATUS_OK = "ok"
STATUS_ALIGN_UNAVAILABLE = "align_unavailable"
STATUS_SOURCE_MISSING = "source_missing"
STATUS_NO_DATA = "no_data"

ALIGN_ORIGIN_DECLARED = "declared"
ALIGN_ORIGIN_DEFAULT = "default"
ALIGN_ORIGIN_DERIVED = "derived"
ALIGN_ORIGIN_IDENTITY = "identity"
# [QA B3] 유도를 포기하고 명시 거절할 때의 마커 (조용한 오답 < 소리 나는 실패)
ALIGN_ORIGIN_UNRESOLVABLE = "unresolvable"


def load_overlay_config(path: str = None) -> dict:
    """map_overlay_config.json 로드. 없으면 {} (전 기능 기본값 동작 — 에러 아님)."""
    p = path or CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("[MapOverlay] failed to load config %s: %s", p, e)
        return {}


# ---------------------------------------------------------------------------
# 맵 메타 조회 (테이블명 하드코딩 금지 — wafer_map_metadata 관례)
# ---------------------------------------------------------------------------

META_TABLE = "wafer_map_metadata"


def load_map_meta(db, target_table: str, map_id: str) -> dict | None:
    """(target_table, map_id)의 grid_metadata 원본 dict를 반환한다. 없으면 None."""
    from database import models
    model = models.DYNAMIC_TABLES.get(META_TABLE)
    if model is None:
        return None
    try:
        row = (db.query(getattr(model, "grid_metadata"))
               .filter(getattr(model, "target_table") == target_table,
                       getattr(model, "map_id") == map_id)
               .first())
    except Exception as e:
        logger.warning("[MapOverlay] meta query failed (%s/%s): %s", target_table, map_id, e)
        return None
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except Exception:
        return None


def _grid_of(meta: dict | None) -> dict | None:
    if not meta:
        return None
    try:
        return {
            "cols": int(meta["grid_cols"]),
            "rows": int(meta["grid_rows"]),
            "start_x": int(meta.get("grid_start_x", 1)),
            "start_y": int(meta.get("grid_start_y", 1)),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# align 결정 (선언 우선 → 메타 유도 → identity)
# ---------------------------------------------------------------------------

def resolve_align(cfg: dict, source_table: str, source_meta: dict | None,
                  target_meta: dict | None, eqp: str = None):
    """소스→타깃 align을 결정한다. 반환: (normalized_align|None, origin, note|None).

    normalized_align은 bonding_plan.normalize_align 형태(None이면 identity).
    """
    import bonding_plan

    note = None
    overrides = (cfg.get("align_overrides") or {})
    decl = overrides.get(source_table)
    if isinstance(decl, dict):
        # by_eqp 우선 — 키가 없으면 default로, default도 없으면 identity로 폴백(차단 금지)
        if eqp and isinstance(decl.get("by_eqp"), dict) and eqp in decl["by_eqp"]:
            return bonding_plan.normalize_align(decl["by_eqp"][eqp]), ALIGN_ORIGIN_DECLARED, None
        if "by_eqp" in decl or "default" in decl:
            if eqp and isinstance(decl.get("by_eqp"), dict) and eqp not in decl["by_eqp"]:
                note = f"by_eqp에 '{eqp}' 선언이 없어 default로 폴백"
            base = decl.get("default")
            if isinstance(base, dict):
                return bonding_plan.normalize_align(base), ALIGN_ORIGIN_DEFAULT, note
            return None, ALIGN_ORIGIN_IDENTITY, (note or "default 선언이 없어 identity로 간주")
        return bonding_plan.normalize_align(decl), ALIGN_ORIGIN_DECLARED, None

    # 선언이 없으면 두 맵의 자기 규격 차이로 유도한다
    if source_meta is None or target_meta is None:
        # 규격을 모른다 = 돌릴 각도를 모른다가 아니라 "차이가 없다고 볼 수밖에 없다" →
        # identity로 간주해 붙인다(선언 부재를 실패로 만들지 않는다).
        return None, ALIGN_ORIGIN_IDENTITY, "맵 메타 부재 — identity로 간주"

    def _rot(m):
        try:
            return int(m.get("rotation", 0) or 0) % 360
        except (TypeError, ValueError):
            return 0

    rel_rot = (_rot(source_meta) - _rot(target_meta)) % 360
    s_side = str(source_meta.get("side", "front") or "front")
    t_side = str(target_meta.get("side", "front") or "front")
    flip = "x" if s_side != t_side else "none"

    if rel_rot == 0 and flip == "none":
        return None, ALIGN_ORIGIN_IDENTITY, None

    # [QA B3 가드] 면 반전 + 타깃 회전 90/270 조합은 **유도할 수 없다**.
    # 이유: cell_to_physical의 back 반전 축이 그 프레임 자신의 회전에 따라 달라진다
    # (90/270이면 행 반전, 아니면 열 반전 — coordinate_transformer). 따라서 "상대 회전 +
    # 단일 flip"이라는 하나의 합성 변환으로는 두 프레임 각각의 반전 축을 표현할 수 없고,
    # 조용히 거울상으로 어긋난 좌표가 나온다(QA 전수 대조: 64조합 중 16개 오답, status는 ok).
    # 근본 수정(각 프레임을 물리 좌표로 각각 사상 후 합성)은 백로그 — 그때까지는
    # **조용한 오답 대신 명시 거절**한다(F1 규율).
    if flip != "none" and _rot(target_meta) in (90, 270):
        return (None, ALIGN_ORIGIN_UNRESOLVABLE,
                f"면 반전(source side={s_side} ≠ target side={t_side})과 타깃 회전"
                f"({_rot(target_meta)}°)이 겹쳐 변환을 유도할 수 없음 — 반전 축이 프레임마다 다르다")

    return (bonding_plan.normalize_align({"rotation": rel_rot, "flip": flip}),
            ALIGN_ORIGIN_DERIVED, None)


def align_applied_payload(align, origin, note=None) -> dict:
    """클라가 '180° 정렬됨' 같은 표시를 할 수 있도록 실제 적용 변환을 담는다."""
    if not align or align.get("is_identity"):
        payload = {"rotation": 0, "flip": "none", "offset": {"x": 0, "y": 0},
                   "origin": origin or ALIGN_ORIGIN_IDENTITY}
    else:
        payload = {
            "rotation": align["rotation"],
            "flip": align["flip"],
            "offset": {"x": align["offset_x"], "y": align["offset_y"]},
            "origin": origin,
        }
    if note:
        payload["note"] = note
    return payload


# ---------------------------------------------------------------------------
# 오버레이 조회
# ---------------------------------------------------------------------------

def parse_sources(spec: str) -> list:
    """`sources` 파라미터 파싱: "table" 또는 "table:key" 의 CSV.

    key 생략 시 타깃 key를 승계한다(같은 lot/slot의 다른 계측 맵이 가장 흔한 사용).
    """
    out = []
    for item in (spec or "").split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            table, key = item.split(":", 1)
            out.append((table.strip(), key.strip() or None))
        else:
            out.append((item, None))
        if len(out) > MAX_OVERLAY_SOURCES:
            raise ValueError(f"sources exceed limit ({MAX_OVERLAY_SOURCES})")
    if not out:
        raise ValueError("sources parameter is required")
    return out


def _table_binding(cfg: dict, table: str) -> dict:
    """테이블의 좌표 컬럼 바인딩. config 선언 우선, 없으면 관례(lot/slot/x/y/val) 추론."""
    bindings = (cfg.get("table_bindings") or {})
    b = bindings.get(table)
    if isinstance(b, dict) and b.get("columns"):
        return dict(b["columns"])
    return {"x": "x", "y": "y", "val": "val", "key_columns": ["lot", "slot"]}


def _key_filters(model, binding: dict, map_key: str):
    """map_key(관례상 `_`로 조인된 복합 키)를 key_columns에 분해해 필터를 만든다."""
    key_cols = binding.get("key_columns") or ["lot", "slot"]
    if isinstance(key_cols, str):
        key_cols = [key_cols]
    parts = str(map_key).split("_")
    if len(parts) < len(key_cols):
        # 분해 불가 — 단일 컬럼으로 통째 매칭 시도
        col = getattr(model, key_cols[0], None)
        if col is None:
            return None
        return [col == map_key]
    # 마지막 컬럼이 나머지를 흡수(랏 이름에 '_'가 있는 경우 방어)
    head = parts[:len(key_cols) - 1]
    tail = "_".join(parts[len(key_cols) - 1:])
    values = head + [tail]
    filters = []
    for name, val in zip(key_cols, values):
        col = getattr(model, name, None)
        if col is None:
            return None
        filters.append(col == val)
    return filters


def get_overlay(db, cfg: dict, target_table: str, target_key: str,
                sources: list, eqp: str = None, cell_cap: int = MAX_OVERLAY_CELLS) -> dict:
    """타깃 맵 프레임 좌표로 정렬된 오버레이 셀들을 반환한다."""
    import bonding_plan
    from database import models

    target_meta = load_map_meta(db, target_table, target_key)
    target_grid = _grid_of(target_meta)

    overlays = []
    for (s_table, s_key) in sources:
        key = s_key or target_key
        entry = {
            "source_table": s_table,
            "source_key": key,
            "cells": [],
            "count": 0,
            "truncated": False,
            "align_applied": None,
            "status": STATUS_OK,
        }

        model = models.DYNAMIC_TABLES.get(s_table)
        if model is None:
            entry["status"] = STATUS_SOURCE_MISSING
            entry["detail"] = f"테이블 '{s_table}'을 찾을 수 없음"
            entry["align_applied"] = align_applied_payload(None, ALIGN_ORIGIN_IDENTITY)
            overlays.append(entry)
            continue

        binding = _table_binding(cfg, s_table)
        x_col = getattr(model, binding.get("x", "x"), None)
        y_col = getattr(model, binding.get("y", "y"), None)
        val_col = getattr(model, binding.get("val", "val"), None)
        if x_col is None or y_col is None:
            entry["status"] = STATUS_SOURCE_MISSING
            entry["detail"] = f"'{s_table}'에 좌표 컬럼이 없음"
            entry["align_applied"] = align_applied_payload(None, ALIGN_ORIGIN_IDENTITY)
            overlays.append(entry)
            continue

        filters = _key_filters(model, binding, key)
        if filters is None:
            entry["status"] = STATUS_SOURCE_MISSING
            entry["detail"] = f"'{s_table}'의 키 컬럼 바인딩 해석 실패"
            entry["align_applied"] = align_applied_payload(None, ALIGN_ORIGIN_IDENTITY)
            overlays.append(entry)
            continue

        source_meta = load_map_meta(db, s_table, key)
        align, origin, note = resolve_align(cfg, s_table, source_meta, target_meta, eqp)

        # [QA B3] 유도 불가 조합은 그리지 않고 거절한다 — 거울상 오답을 조용히 내보내지 않는다.
        if origin == ALIGN_ORIGIN_UNRESOLVABLE:
            entry["status"] = STATUS_ALIGN_UNAVAILABLE
            entry["detail"] = note
            entry["align_applied"] = align_applied_payload(None, ALIGN_ORIGIN_UNRESOLVABLE, note)
            overlays.append(entry)
            continue

        transform = None
        if align and not align.get("is_identity"):
            src_grid = _grid_of(source_meta)
            if not src_grid:
                # 비-identity 변환이 필요한데 소스 격자 규격을 모른다 = 계산 근거 없음
                entry["status"] = STATUS_ALIGN_UNAVAILABLE
                entry["detail"] = f"'{s_table}' 격자 규격 미등록 — 변환을 계산할 수 없음"
                entry["align_applied"] = align_applied_payload(align, origin, note)
                overlays.append(entry)
                continue
            try:
                transform = bonding_plan.make_align_transform(align, src_grid, target_grid)
            except ValueError as ve:
                entry["status"] = STATUS_ALIGN_UNAVAILABLE
                entry["detail"] = f"격자 규격 비호환: {ve}"
                entry["align_applied"] = align_applied_payload(align, origin, note)
                overlays.append(entry)
                continue

        entry["align_applied"] = align_applied_payload(align, origin, note)

        try:
            cols = [x_col, y_col] + ([val_col] if val_col is not None else [])
            rows = db.query(*cols).filter(*filters).limit(cell_cap + 1).all()
        except Exception as e:
            logger.warning("[MapOverlay] cell query failed (%s/%s): %s", s_table, key, e)
            entry["status"] = STATUS_SOURCE_MISSING
            entry["detail"] = "셀 조회 실패"
            overlays.append(entry)
            continue

        if len(rows) > cell_cap:
            rows = rows[:cell_cap]
            entry["truncated"] = True
            entry["cap"] = cell_cap
            logger.warning("[MapOverlay] %s/%s truncated at %d cells", s_table, key, cell_cap)

        cells = []
        for row in rows:
            rx, ry = row[0], row[1]
            if rx is None or ry is None:
                continue
            val = row[2] if len(row) > 2 else None
            cx, cy = transform(rx, ry) if transform else (int(rx), int(ry))
            cells.append({"x": cx, "y": cy, "val": val})
        entry["cells"] = cells
        entry["count"] = len(cells)
        if not cells:
            entry["status"] = STATUS_NO_DATA
        overlays.append(entry)

    return {
        "target": {
            "table": target_table,
            "key": target_key,
            "grid": target_grid,
        },
        "overlays": overlays,
        "cell_cap": cell_cap,
    }


# ---------------------------------------------------------------------------
# 페인트 잠금 선언 (S2) — 서버 config가 정본, 클라는 읽어서 적용
# ---------------------------------------------------------------------------

def get_paint_rules(cfg: dict, table: str = None) -> dict:
    """맵 단위 페인트 잠금 규칙을 반환한다.

    [계약] 어떤 값이 페인팅을 막는지는 **서버 config가 정본**이며 클라는 이 선언을 읽어
    적용한다(클라 하드코딩 금지). 선언이 없으면 잠금 없음(enabled: false)이 기본 —
    "F면 못 칠한다" 같은 규칙이 코드에 박혀 있으면 사용자가 바꿀 수 없다.

    반환: {"enabled": bool, "blocking_values": [...], "from_overlay": [...], "message": str}
    """
    rules = (cfg.get("paint_lock") or {})
    default = rules.get("*") if isinstance(rules.get("*"), dict) else {}
    specific = rules.get(table) if table and isinstance(rules.get(table), dict) else {}
    merged = dict(default)
    merged.update(specific)
    return {
        "enabled": bool(merged.get("enabled", False)),
        "blocking_values": [str(v) for v in (merged.get("blocking_values") or [])],
        "from_overlay": [str(v) for v in (merged.get("from_overlay") or [])],
        "message": merged.get("message") or "이 셀은 잠금 값이라 페인팅할 수 없습니다.",
    }
