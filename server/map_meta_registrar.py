"""`wafer_map_metadata` identity and the mask-neutral synthetic frame.

[2026-09-07 은퇴] 이 모듈은 원래 인제션 두 경로(파일 워처·체인 워커)가 만든 맵에
메타 행을 **자동으로 지어 넣는** 자리였다(M3, `MapMetaCollector`). 소유자 지시로
그 **쓰는 쪽**이 은퇴했다 — 메타는 발행 폼과 파일로만 들어온다.

남은 셋은 그 때도 **쓰는 일과 무관하게** 쓰이던 것들이다:
  `META_TABLE` · `compose_map_id` · `meta_business_key`   메타 업서트 규칙·확정 기록의 신원
  `synthesize_grid_meta`                                정렬의 「미등록 맵을 무엇으로 가정하나」
⚠️ `synthesize_grid_meta` 는 `map_alignment.assumed_meta_for_unregistered` 가 부른다 —
   그곳 주석(:433)이 「세 번째 프레임 합성기를 만들지 않는다」고 적어 둔 그 함수다.
   재는 자리지 «쓰는 자리»가 아니므로 은퇴 밖이다.
⚠️ 표지 `auto_registered` 와 그 독자들도 그대로다 — 이미 쓰인 행들이 «들고 있는»
   기록 어휘이고, 지우면 그 행들이 「declared」로 거짓이 된다.
"""
import math

META_TABLE = "wafer_map_metadata"


def compose_map_id(key_columns, row: dict, table_name: str = None):
    """Canonical map_id composition: map_key_columns values joined with '_'.

    [7b DONE 2026-07-29] Routed through the shared canonicalization
    (`map_overlay.canonical_bind_value` — declared column type governs):
    registration and lookup must compose the SAME identity, or a raw pre-cast
    '01' in a number-declared key column registers 'LOT_01' while the stored
    cell casts to 1 and every consumer looks up 'LOT_1'. With no table_name
    (or no declaration) the behavior is the previous `clean_str_value` pin:
    trim + integral-float folding. Divergence from the editor kept deliberate:
    the editor drops EMPTY key parts and joins the rest; here a missing/empty
    part disqualifies the row (returns None) — ingestion must not guess a
    partial identity it would then register meta for.
    """
    import map_overlay
    parts = []
    for col in key_columns:
        p = map_overlay.canonical_bind_value(table_name, col, row.get(col))
        if p is None or p == "":
            return None
        parts.append(p)
    return "_".join(parts)


def meta_business_key(target_table: str, map_id: str) -> str:
    """The `wafer_map_metadata` business key for one map — THE spelling.

    `wafer_map_metadata` declares `composite_key_source = [target_table, map_id]`, so this
    mirrors crud's composite assembly and reads the separator from the declaration rather
    than repeating it. Extracted 2026-08-06 because a second writer appeared
    (`frame_confirmation` records a confirmed coordinate system) and two spellings of an
    identity is how one writer creates the row the other cannot find.
    """
    from database import crud
    sep = (crud.TABLE_CONFIG.get(META_TABLE) or {}).get("composite_key_separator", "_")
    return "%s%s%s" % (crud.clean_str_value(target_table), sep,
                       crud.clean_str_value(map_id))


def _to_grid_int(v):
    """Parse a cell coordinate to an integral grid index; None if not integral."""
    if v is None:
        return None
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    i = int(f)
    return i if f == i else None


def synthesize_grid_meta(min_x: int, min_y: int, max_x: int, max_y: int) -> dict:
    """The mask-neutral synthetic frame (editor 표준 choice vocabulary).

    Field-for-field mirror of map_editor.js [fix C]: chip 1x1 / offset 0 /
    margin 3 and a wafer diameter whose effective radius circumscribes the
    grid's half-diagonal, so every cell corner is strictly inside the mask
    ellipse and the whole map stays pushable. `auto_registered: true` marks
    provenance (additive field — every consumer reads known keys only).
    """
    cols = max_x - min_x + 1
    rows = max_y - min_y + 1
    half_diag = math.sqrt(cols * cols + rows * rows) / 2.0
    return {
        "grid_cols": cols,
        "grid_rows": rows,
        "grid_start_x": min_x,
        "grid_start_y": min_y,
        "grid_y_invert": False,
        "rotation": 0,
        "side": "front",
        "phys_wafer_dia": max(300, math.ceil(2 * (half_diag + 4))),
        "phys_chip_x": 1,
        "phys_chip_y": 1,
        "phys_offset_x": 0,
        "phys_offset_y": 0,
        "phys_edge_margin": 3,
        "auto_registered": True,
    }
