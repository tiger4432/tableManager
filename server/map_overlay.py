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

[align 판정 규율 — 사용자 확정 2026-07-26: 메타가 정렬의 유일한 근거다]
1. 두 맵 메타로 변환을 **유도할 수 있으면 유도한 대로 적용**한다(origin: "derived").
2. 유도할 근거가 없으면(메타 부재 등) **identity로 간주해 그대로 붙인다**(origin: "identity").
   메타 부재는 실패가 아니라 **등록 누락의 신호**다 — 실패로 만들면 대부분의 맵이 못 붙는다.
3. `align_unavailable`은 "**변환을 계산할 근거가 없을 때**"만 낸다 — 유도된 비-identity
   변환이 있는데 격자 규격이 비호환이라 계산이 불가능한 경우(치수 모순, phys 규격 부재 등).
   [D1 2026-08-04] "phys 규격 부재"에는 **자동 등록된 합성 규격**이 포함된다. 값이 있고
   형식도 온전하지만 아무도 재지 않았으므로 정렬의 근거가 아니다 — 판정의 유일한 철자는
   `geometry_declaration`이다.

> **`align_overrides`(config 선언 · `by_eqp` 분기)는 제거됐다.** 계측으로 잰 어긋남도
> `wafer_map_metadata`에 기록한다 — 별도 오버라이드 레이어를 두지 않는다. 선언 레이어가
> 있으면 "정렬의 근거가 둘"이 되어, 메타와 선언이 어긋났을 때 어느 쪽이 참인지 알 수 없다.

[유도 경로의 변환 산법 — 프레임 합성 (구 B3 한계의 근본 수정)]
유도 경로는 "상대 회전 + 단일 flip"을 **하나의** 변환기로 합성하지 않는다. 그 방식은
`cell_to_physical`의 back 반전 축이 프레임 자신의 회전에 따라 달라지기 때문에(90/270이면
행, 아니면 열) 두 프레임의 반전 축을 하나의 변환으로 표현할 수 없었고, 전수 대조 64조합 중
16개가 조용한 거울상 오답이었다(QA B3 — 당시엔 명시 거절로 막아 두었다).

현재는 **각 맵을 자기 메타로 물리 좌표에 사상한 뒤 타깃 프레임으로 역사상**한다:

    (x,y)_src ──src.cell_to_physical──▶ (xp,yp)_물리 ──dst.physical_to_cell──▶ (x,y)_dst

각 프레임의 반전 축·회전이 자기 메타로 각각 처리되므로 조합 폭발이 사라진다. 따라서 이전의
"면 반전 + 타깃 회전 90/270 거절" 가드는 **불필요해져 제거**했다(과잉 거절이었다).

[격자 치수 규약 — 물리 vs 프레임]
`wafer_map_metadata.grid_cols/grid_rows`는 **물리(canonical) 치수**다. 셀에 저장된 x/y는
**프레임(visual) 좌표**이며 그 치수는 맵 자신의 회전이 90/270이면 물리의 스왑이다. 프레임
합성 경로는 각 맵의 변환기가 자기 `visual_cols/visual_rows`를 스스로 계산하므로 이 구분을
호출자가 신경 쓸 필요가 없다(구 선언 경로는 프레임 치수를 손으로 넘겨야 했고, 그래서
회전 90/270 맵에서 정상 조합이 `align_unavailable`로 거절되는 사고가 났다).

[남은 한계] 두 맵의 `grid_start_x/y` 차이는 identity 경로에서 보정하지 않는다
(라이브는 전부 start=(1,1)). 유도 경로(프레임 합성)는 각 맵의 start를 정확히 반영한다.

[서버의 유일한 좌표 변환 구현이다 — 2026-07-26 일원화]
`bonding_plan.make_align_transform`(bbox 항 없는 사본)은 삭제됐고, 가용량 산출
(`bonding_plan.get_core_summary` · `transfer_plan`)도 이 모듈의 `resolve_map_transform`을
경유한다. 서버에 좌표 변환 구현은 여기 하나뿐이다(렌더용 클라 구현과 합쳐 총 2개).

[페이로드 규율] 셀 목록을 반환하는 유일한 API이므로 상한이 필수다. 캡 도달 시 **응답에 명시**
표기한다(조용한 절단 금지 — QA F2 규율).
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

import paths  # single override point (ASSY_DATA_ROOT)
CONFIG_PATH = paths.config_path("map_overlay_config.json")

MAX_OVERLAY_CELLS = 20_000     # 오버레이 1종당 셀 상한 (초과 시 truncated 표기)
MAX_OVERLAY_SOURCES = 8        # 요청당 소스 맵 개수 상한

STATUS_OK = "ok"
STATUS_ALIGN_UNAVAILABLE = "align_unavailable"
STATUS_SOURCE_MISSING = "source_missing"
STATUS_NO_DATA = "no_data"

ALIGN_ORIGIN_DERIVED = "derived"
ALIGN_ORIGIN_IDENTITY = "identity"
# [구 QA B3] 유도 불가 마커. 프레임 합성 도입으로 **더 이상 발화하지 않는다** —
# 클라가 이미 이 값을 알고 있을 수 있어 상수만 남긴다(응답에는 나오지 않는다).
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
# [7b] Canonical key values — THE one canonicalization for map identity
# composition and pool (lot/slot) binds.
#
# Production defect (2026-07-28): a `number`-declared slot column stores 1, so
# the map identity registered in wafer_map_metadata reads 'LOT_1' — while a
# parsed material token supplies '01' (and a Float column round-trips '1.0').
# Composing or binding with the raw value then misses silently: the meta lookup
# returns None (align degradation) and the availability pool binds count 0.
# Cell-data filters survive because crud casts them by declared column type —
# identity composition and pool binds must go through here for the same reason.
# Do NOT write a second implementation.
# ---------------------------------------------------------------------------

_CANON_INT_RE = re.compile(r"^[+-]?[0-9]+$")


def canonical_key_value(value, col_type):
    """Value + DECLARED column type -> canonical key string.

    - "number": integer-parse -> str, honoring the project's single-integer-judge
      semantics ('01' / '1' / ' 1 ' are the same key; 1.0 -> '1'). A non-integral
      numeric keeps its repr ('7.5'); an unreadable value keeps its trimmed
      original — the lookup misses honestly instead of inventing a key.
    - anything else (string / undeclared): trimmed as-is.
    - None stays None (composition sites decide their own placeholder).
    """
    if value is None:
        return None
    if col_type == "number" and not isinstance(value, bool):
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if value == value and value not in (float("inf"), float("-inf")) \
                    and value.is_integer():
                return str(int(value))
            return str(value).strip()
        s = str(value).strip()
        if _CANON_INT_RE.match(s):
            return str(int(s))
        try:
            f = float(s)
        except (TypeError, ValueError):
            return s
        if f == f and f not in (float("inf"), float("-inf")) and f.is_integer():
            return str(int(f))
        return s
    if isinstance(value, float):
        # A float VALUE is numeric regardless of the declared type — '3.0' is a
        # repr artifact, not data (mirrors crud.clean_str_value, which the
        # registration path pinned before this function existed).
        if value == value and value not in (float("inf"), float("-inf")) \
                and value.is_integer():
            return str(int(value))
    return str(value).strip()


def declared_column_type(table, column):
    """Declared type of `table.column` from the live table_config singleton.

    crud.TABLE_CONFIG is mutated in place on hot reload — always read through
    the module attribute, never a snapshot. None when table/column undeclared
    (canonical_key_value then applies string semantics: trim only)."""
    if not table or not column:
        return None
    from database import crud
    return ((crud.TABLE_CONFIG.get(table) or {}).get("column_types") or {}).get(column)


def canonical_bind_value(table, column, value):
    """`canonical_key_value` with the declared type looked up — the form every
    pool-bind / composition site uses."""
    return canonical_key_value(value, declared_column_type(table, column))


def canonical_role_value(src_cfg, role, value):
    """Pool-bind convenience: role key -> bound column of `src_cfg`
    ({table, columns role-map}) -> canonical by its declared type."""
    if not isinstance(src_cfg, dict):
        return value
    col = (src_cfg.get("columns") or {}).get(role, role)
    return canonical_bind_value(src_cfg.get("table"), col, value)


def compose_map_id(identity_cols, values, binding=None):
    """Join identity components with '_' into a map identity string.

    Each component is canonicalized by the declared type of the corresponding
    column of `binding` ({table, columns role-map}) — the meta row being looked
    up was registered from THAT table's stored values, so the composition must
    canonicalize the same way ('LOT_01' -> 'LOT_1' when slot is number-declared).
    With no binding, components pass through `str()` untouched (no declared type
    to canonicalize against)."""
    parts = []
    for k in identity_cols:
        v = values.get(k, "")
        if isinstance(binding, dict) and isinstance(binding.get("table"), str):
            col = (binding.get("columns") or {}).get(k, k)
            v = canonical_bind_value(binding["table"], col, v)
        parts.append("" if v is None else str(v))
    return "_".join(parts)


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


def _rotation_of(meta: dict | None) -> int:
    try:
        return int((meta or {}).get("rotation", 0) or 0) % 360
    except (TypeError, ValueError):
        return 0


def _grid_of(meta: dict | None) -> dict | None:
    """메타 선언 그대로의 **물리(canonical) 격자 규격**. 응답 `target.grid`가 이것이다."""
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


def grid_dims(meta: dict | None):
    """(cols, rows) 또는 None. 격자 치수만 묻는 자리의 **공개 철자**.

    `_grid_of`를 다시 구현하지 않고 그대로 부른다 — 치수를 읽는 식이 둘이 되면 그 둘이
    갈리는 날 좌표 검사와 제외 판정이 서로 다른 격자를 말한다(I6).
    """
    g = _grid_of(meta)
    return None if g is None else (g["cols"], g["rows"])


def _side_of(meta: dict | None) -> str:
    return str((meta or {}).get("side", "front") or "front")


def _y_invert_of(meta: dict | None) -> bool:
    return bool((meta or {}).get("grid_y_invert"))


PHYS_KEYS = ("phys_wafer_dia", "phys_chip_x", "phys_chip_y",
             "phys_offset_x", "phys_offset_y", "phys_edge_margin")


def _phys_signature(meta: dict | None):
    """웨이퍼 원 규격 서명 — **바이트 그대로**. 하나라도 없으면 None.

    🔴 이 함수는 **출처를 묻지 않는다.** "이 값이 선언인가"는 `geometry_declaration`의
       질문이고 철자는 거기 하나뿐이다. 여기는 "메타가 무슨 값을 말하고 있나"만 답한다 —
       두 질문을 한 함수에 합치면 합성 규격의 **의도된** 답(마스크 중립 = 전 셀 유효)까지
       같이 사라진다(§`circle_die_mask`).
    """
    m = meta or {}
    try:
        vals = tuple(float(m[k]) for k in PHYS_KEYS)
    except (KeyError, TypeError, ValueError):
        return None
    return vals


# ═══ [D1] 자동 등록된 기하는 선언이 아니다 (사용자 판정 2026-08-04) ══════════════════════
#
# 맵에 규격 행이 없으면 두 곳이 **마스크 중립 합성 규격**을 써 넣는다. 둘 다 "원 마스크
# 없음"을 표현할 어휘가 없어 chip 1x1 / offset 0 / 격자 반대각선을 외접하는 지름을 쓴다:
#   · `server/map_meta_registrar.synthesize_grid_meta()` — 인제션 자동 등록
#   · `client2/src/map_editor.js`의 `[fix C]`             — 규격 없는 맵의 「표준」 선택
# 그 값은 **1mm 다이라는 주장이 아니다.** 아무도 재지 않았다는 뜻이다.
#
# 🔴 **읽는 쪽이 그 사실을 몰랐다.** 합성된 1x1 서명은 존재하고 형식도 온전하므로
#    `make_frame_transform`의 유일한 관문("서명이 **없으면** 거절")을 그대로 통과했고,
#    서버는 자동 등록 소스를 실측 타깃에 1mm 피치로 정렬해 **멀쩡해 보이는 좌표**를 냈다.
#    이 저장소가 반복해서 값을 치르는 실패 유형이다 — 화면은 완벽하고 값만 전부 틀리며,
#    셀 개수로는 보이지 않는다.
#
# 🔴 **판정은 값이 아니라 `auto_registered` 표지다.** chip이 1인지 보지 않는다 — 1은
#    합법적인 피치이고, 표지가 곧 값이면 진짜 1mm 다이를 언젠가 조용히 삼킨다.
# 🔴 **레거시 폴백(1x1을 표지로 읽기)은 두지 않는다 — 필요 없다는 것을 셌다.** 실측
#    2026-08-04(운영 DB, 읽기 전용): `wafer_map_metadata` 668행 중 chip 1x1이 320행이고
#    **그 320행이 전부** 표지를 달고 있다. 표지 없는 1x1 행은 **0건**이다. 안 쓰이는
#    폴백은 채점되지 않는 두 번째 판정 경로일 뿐이다.
# 🔴 **철자는 하나다.** 이 질문을 호출자마다 다시 구현하면 「선언인가」의 답이 둘이 되고,
#    그 둘이 갈리는 날이 화면은 멀쩡한 채 값만 틀리는 날이다 — 클라 절반이 정확히 그렇게
#    이 상태에 도달했다(`physDeclaration`이 합성 규격과 실측 규격을 바이트 단위로 같게
#    답했다).
#
# 토큰 어휘는 클라 `physDeclaration`의 `source`와 **같다**. 두 채점기가 어휘를 둘 가지면
# 매핑표가 필요해지고, 매핑표는 답의 두 번째 구현이다.
AUTO_REGISTERED_KEY = "auto_registered"

GEOMETRY_DECLARED = "declared"                  # 누군가 쟀다
GEOMETRY_AUTO_REGISTERED = "auto_registered"    # 값은 있지만 선언이 아니다
GEOMETRY_ABSENT = "absent"                      # 여섯 키 중 하나 이상이 없다
GEOMETRY_UNPARSABLE = "unparsable"              # 키는 있는데 수가 아니다

# ═══ [D3] 빌려 온 웨이퍼 규격 — 선언이 아니고, 선언이 될 수도 없다 (2026-08-05) ═════════
#
# 제품 소유자가 지적한 순환: **규격이 선언돼야 채점하는데, 조작자가 정렬을 도는 이유가
# 바로 그 맵의 규격을 모르기 때문**이다. 답을 먼저 내놓으라고 요구하는 셈이다.
#
# 총괄 판정(스펙 §9ⓐ): 소스 맵에 규격 선언이 없고 조작자가 **선언된 바닥**을 골랐으면,
# 둘이 같은 웨이퍼의 치수를 공유한다고 **가정하고** 채점한다. 「이 둘은 같은 웨이퍼다」는
# 애초에 두 맵을 정렬하는 전제이므로 조작자가 낼 자격이 있는 주장이다.
#
# 🔴 **그 값은 소스 메타에 쓰지 않는다.** 쓰는 순간 그것은 누군가 잰 값처럼 읽히고,
#    나중에 아무도 그것이 가정이었다는 것을 알 수 없다 — I4가 말하는 사칭의 정확한 형태다.
#    그래서 여기서 하는 일은 **계산용 사본 하나를 메모리에 만드는 것**뿐이고, 그 사본은
#    표지를 달고 다니며 `geometry_declaration`에 **`declared`가 아니라고** 대답한다.
#
# 🔴 **표지는 값보다 먼저 보고, `auto_registered`보다도 먼저 본다.** 빌린 사본은 여섯 키를
#    전부 바닥 값으로 덮었으므로 그 아래 값들은 더 이상 등록기가 쓴 것이 아니다. 다만
#    방위 축(`rotation`/`side`/`grid_y_invert`/`grid_start_*`)의 `auto_registered` 표지는
#    **그대로 남는다** — 빌린 것은 웨이퍼 규격뿐이고 방위는 손대지 않기 때문이다.
#
# ⚠️ 이 토큰은 클라 `physDeclaration`의 어휘에 **없다**. 클라는 빌린 메타를 만들지 않으므로
#    생성할 수 없고(빌리기는 서버 정렬 경로 안에서만 일어난다), 정렬 payload가 실어 보내는
#    출처 문자열로만 만난다.
PHYS_ASSUMED_KEY = "phys_assumed_from"          # {"table":..., "map_id":...} — 어디서 빌렸나
GEOMETRY_ASSUMED = "assumed"                    # 값은 바닥에서 빌려 왔다 — 선언이 아니다

# 사유는 **사람이 읽는 자리에서 한 번만** 사람 말로 옮긴다(클라 `7ea2c2f`와 같은 규율).
# 판정은 `geometry_declaration`이 이미 끝냈고 여기서는 표시만 한다 — 두 번째 판정이 아니다.
_GEOMETRY_REFUSAL_TEXT = {
    GEOMETRY_AUTO_REGISTERED: (
        "물리 규격이 자동 등록된 합성값입니다(chip 1x1은 '웨이퍼 원 마스크 없음'을 뜻하는 "
        "합성 어휘이지 1mm 다이가 아닙니다) ― 칩 크기를 잰 적이 없습니다"),
    GEOMETRY_ABSENT: (
        "물리 규격(phys_wafer_dia/chip_x/chip_y/offset_x/offset_y/edge_margin)이 "
        "미등록입니다"),
    GEOMETRY_UNPARSABLE: (
        "물리 규격(phys_*) 값이 수로 읽히지 않습니다"),
    GEOMETRY_ASSUMED: (
        "물리 규격을 기준 맵에서 빌려 온 값입니다 ― 이 맵에 대한 선언이 아닙니다"),
}


def geometry_declaration(meta: dict | None) -> str:
    """**이 맵의 물리 기하가 「선언」인가** — 그 질문의 유일한 철자.

    반환은 위 다섯 토큰 중 하나이며 그중 넷은 클라 `physDeclaration`의 `source`와 같은
    어휘다(`GEOMETRY_ASSUMED`는 서버 정렬 경로에서만 생긴다 — §[D3]).
    `GEOMETRY_DECLARED`가 아니면 그 기하는 **이 맵의 선언**이 아니다.

    ⚠️ 표지를 **값보다 먼저** 본다. 표지의 뜻이 "아래 값들은 증거가 아니다"이므로 값을
       먼저 읽어 통과시키면 표지가 아무것도 하지 않는다.
    """
    m = meta if isinstance(meta, dict) else {}
    if m.get(PHYS_ASSUMED_KEY):
        return GEOMETRY_ASSUMED
    if m.get(AUTO_REGISTERED_KEY) is True:
        return GEOMETRY_AUTO_REGISTERED
    for k in PHYS_KEYS:
        v = m.get(k)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return GEOMETRY_ABSENT
        try:
            float(v)
        except (TypeError, ValueError):
            return GEOMETRY_UNPARSABLE
    return GEOMETRY_DECLARED


def geometry_refusal(meta: dict | None) -> str | None:
    """기하가 선언이 **아닌** 이유(사람 말). 선언이면 None.

    판정은 하지 않는다 — `geometry_declaration`을 호출해 그 토큰에 문장을 붙일 뿐이다.

    ⚠️ 「선언인가」와 「계산할 근거가 있는가」는 **다른 질문**이다. 빌린 규격은 선언이
       아니지만 좌표는 만들어 낸다 — 그 질문은 `geometry_computable`이 답한다.
    """
    token = geometry_declaration(meta)
    if token == GEOMETRY_DECLARED:
        return None
    return _GEOMETRY_REFUSAL_TEXT[token]


def geometry_computable(meta: dict | None) -> str | None:
    """좌표를 계산할 **근거**가 있는가 — 없으면 사유(사람 말), 있으면 None.

    `declared`와 `assumed` 둘 다 근거가 된다. 가정은 조작자가 낸 주장이고 그 주장 아래에서
    나온 답은 **주장과 함께** 기록되므로(payload·확정 기록), 근거이면서 선언은 아니다.

    🔴 두 번째 판정이 아니다 — 판정은 `geometry_declaration` 하나가 하고 여기서는 그 토큰에
       질문 하나를 더 물을 뿐이다. 몸통을 복사하면 두 답이 갈리는 날이 온다(I6).
    """
    if geometry_declaration(meta) == GEOMETRY_ASSUMED:
        return None
    return geometry_refusal(meta)


def assume_phys_from(meta: dict | None, basis_meta: dict | None,
                     basis: dict = None) -> dict | None:
    """소스 메타 + **바닥에서 빌린 웨이퍼 규격** → 계산용 사본. 못 빌리면 None.

    🔴 **아무것도 쓰지 않는다.** 반환은 새 dict이고 호출자는 이것을 DB에 넣지 않는다.
       이 함수가 만든 값이 `wafer_map_metadata`에 도달하는 경로는 저장소에 없어야 한다 —
       그것이 있으면 가정이 선언으로 승격되고, 나중에 아무도 둘을 구별할 수 없다.

    `basis`: `{"table":..., "map_id":...}` — 어디서 빌렸는지. 표지 값이 되어 payload와
        확정 기록에 그대로 실린다. 「나중에 이 가정이 거짓으로 밝혀지면 어느 결정이 그
        위에 서 있었나」가 물어질 수 있어야 하고, 그러려면 출처가 기록에 있어야 한다.

    빌리지 **않는** 것 — 이 목록이 이 함수의 내용이다:
      · `grid_cols`/`grid_rows` — 맵의 성질이지 웨이퍼의 성질이 아니다. 한 웨이퍼의 두 맵이
        서로 다르게 잘려 있을 수 있으므로 빌리면 없는 사실을 만든다. 없으면 **빌리지 않고
        거절**한다(호출자가 이름을 대고 거절한다).
      · `rotation`/`side`/`grid_start_*`/`grid_y_invert` — **풀고 있는 미지 그 자체다.**
        바닥의 프레임을 베끼는 것은 답을 먼저 적어 놓고 그 답이 맞는지 묻는 것이다.
        (실측은 `test_map_alignment_assumption.py`가 들고 있다 — 두 축 모두 채점이 보는
         좌표를 통째로 옮긴다.)

    거절하는 경우:
      · 소스 기하가 이미 `declared` — 잰 값을 빌린 값으로 덮지 않는다. 가정은 **빈 자리**에만
        들어간다.
      · 바닥 기하가 `declared`가 아님 — 가정 위에 가정을 쌓지 않는다.
      · 소스에 격자 치수가 없음 — 위 목록의 첫 줄.
    """
    if not isinstance(meta, dict) or not isinstance(basis_meta, dict):
        return None
    if geometry_declaration(meta) == GEOMETRY_DECLARED:
        return None
    if geometry_declaration(basis_meta) != GEOMETRY_DECLARED:
        return None
    if _grid_of(meta) is None:
        return None
    sig = _phys_signature(basis_meta)
    if sig is None:                                   # 도달 불가 — declared가 이미 보장한다
        return None
    out = dict(meta)
    for k, v in zip(PHYS_KEYS, sig):
        out[k] = v
    out[PHYS_ASSUMED_KEY] = dict(basis or {}) or True
    return out


# ═══ [D2] 방위 축에는 출처가 없다 (2026-08-05) ═══════════════════════════════════════════
#
# `_rotation_of:235` · `_side_of:257` · `_y_invert_of:261` · `_grid_of:250-251`은 **키 부재 ·
# 파싱 실패 · 명시적 선언을 같은 값으로** 돌려준다. 그래서 「rotation 0」과 「아무도 회전을
# 읽은 적이 없다」가 하류에서 **관측 불가능하게 같다.** 실측(2026-08-05, 운영 `wafer_map_metadata`
# 668행, 읽기 전용): rotation이 그 상태인 행이 516행이다.
#
# 🔴 **판정 규칙은 한 줄이고 다섯 축에 같다:**
#      저장된 값이 **키가 없을 때 리더가 만들어 내는 값과 같으면** 그 값은 선언의 증거가
#      아니다.
#    리더의 부재 기본값이 곧 그 축의 **무증거 값**이다 — 두 경우가 같은 값을 내므로, 값만
#    보고 둘을 가를 방법이 원리적으로 없다. 반대로 값이 그것과 **다르면** 누군가 골랐다는
#    증거가 된다(어떤 쓰기 경로도 무증거 상태에서 그 값을 만들지 않는다).
#
# 🔴 **어휘는 하나다.** `geometry_declaration`의 네 토큰을 그대로 쓴다(같은 문자열, 별칭
#    상수를 새로 만들지 않는다 — I6). 다만 방위 축에는 기하 축에 **없는** 경우가 하나 있어
#    토큰이 하나 늘어난다:
#
#      `indeterminate` — 값은 있고 형식도 온전한데 **아무도 골랐다는 증거가 없다.**
#
#    기하 축에는 이 칸이 비어 있다. `synthesize_grid_meta`가 phys를 쓸 때 **반드시**
#    `auto_registered` 표지를 같이 쓰고, 실측으로 표지 없는 합성 phys 행이 0건이기 때문이다
#    (§geometry_declaration). 방위 축은 그렇지 않다 — 표지를 안 달고 방위를 기본값으로
#    써 넣는 쓰기 경로가 **실재한다**:
#      · `server/ingestion_workspace/*/auto_update/generate_*.py` — `rotation:0, side:"front",
#        grid_y_invert:False`를 상수로 쓰고 표지는 없다(core_defect_map:131-137,
#        eds_fail_map:139-145, dt_map:86-93).
#      · `client2/src/map_editor.js:6270 buildPushGridMetadata` — 화면 컨트롤을 그대로 쓴다.
#        초기값이 `currentRotation = 0`(`:66`) / front / 미체크이므로, 조작자가 방위를
#        **한 번도 보지 않아도** Push 한 번이 `rotation:0`을 써 넣는다.
#    그러므로 「표지가 없다」는 방위 축에서 선언의 증거가 되지 못한다. 이 칸을 `declared`에
#    접으면 I4(그럴듯한 기본값이 선언을 사칭)이고, `absent`에 접으면 거짓이다 — 키는 실재하고
#    소비자는 그 값을 쓴다. 그래서 **자기 토큰**이다.
#
# ⚠️ `indeterminate`는 「선언되지 않았다」가 아니라 **「구별할 수 없다」**이다. 조작자가 실제로
#    0도를 골랐어도 같은 토큰이 나온다. 증거가 그것뿐이므로 그 이상은 말할 수 없다.
#
# ⚠️ **표지의 권한은 축마다 다르다** — 기하 축과 갈리는 유일한 지점이고, 이유가 있다.
#    `auto_registered`는 `PHYS_KEYS` 여섯 개를 덮는 표지다(스펙 §9ⓒ). 방위 축에 그 표지를
#    적용하는 것은 확장이고, 확장이 성립하는 범위는 **`synthesize_grid_meta`가 실제로 쓸 수
#    있었던 값**까지다(`map_meta_registrar.py:184-194`):
#      · rotation · side · grid_y_invert → **언제나 0 / "front" / False.** 그러므로 표지가
#        붙었는데 `rotation:90`이면 그것을 쓴 것은 등록기가 아니다(에디터가 표지를 승계한 채
#        방위만 바꾼 경우 — `map_editor.js:6292`). 그때 `auto_registered`라고 답하면 거짓이다.
#      · grid_start_x · grid_start_y → **관측된 최소 좌표**다. 값이 무엇이든 등록기가 쓸 수
#        있었으므로 표지가 그대로 설명한다. 여기서 "1이 아니니 사람이 골랐다"고 읽으면 등록기의
#        bbox 스캔 결과를 선언으로 승격시킨다.
#    (실측 2026-08-05: 표지 320행 중 rotation/side/y반전이 무증거 값이 아닌 행은 0건 — 지금은
#     이 구분이 census를 바꾸지 않는다. 그래도 명시해 두는 쪽을 택한다, 조용히 갈릴 자리라서.)
#
# 🔴 **이 함수는 DB를 모른다.** 층 ③(선언)은 순수여야 한다(스펙 §0.2). `cell_sources`의
#    `source_name`을 읽으면 「누가 이 blob을 마지막으로 썼나」는 알 수 있지만 그것은 **축
#    단위가 아니라 컬럼 단위**이고, 순수 함수를 DB 세션에 묶는 대가로 축 단위 답을 못 얻는다.
ORIENTATION_INDETERMINATE = "indeterminate"   # 값은 있으나 선언의 증거가 없다

# 방위 축 — `frame_axes`의 앞 다섯 성분과 같은 순서다(같은 축 집합의 두 번째 철자를 만들지
# 않기 위해 순서까지 맞춘다).
ORIENTATION_KEYS = ("rotation", "side", "grid_y_invert", "grid_start_x", "grid_start_y")


def _read_rotation(raw):
    """(정규화 값, 읽혔는가). 리더 `_rotation_of`와 같은 정규화(`int` 후 mod 360).

    90의 배수가 아니면 **읽히지 않은 것으로 본다.** `_frame_phys_params:392`가 90/180/270이
    아닌 값을 전부 rot-0 분기로 흘리므로, 45는 값이 아니라 조용한 0이다.
    """
    try:
        v = int(raw) % 360
    except (TypeError, ValueError):
        return None, False
    return v, v in (0, 90, 180, 270)


def _read_side(raw):
    """리더 `_side_of`는 문자열을 그대로 통과시키고, `_frame_phys_params`는 `== "back"`만
    본다. 그래서 `"Back"`은 조용히 front가 된다 — 값이 아니라 파싱 실패로 답한다."""
    v = str(raw)
    return v, v in ("front", "back")


def _read_y_invert(raw):
    """리더 `_y_invert_of`는 `bool(raw)`다 — 문자열 `"false"`가 **True**가 된다.
    참/거짓을 진짜로 담은 표현(진리값, 0/1)만 읽혔다고 본다."""
    if isinstance(raw, bool):
        return raw, True
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw), True
    return None, False


def _read_grid_start(raw):
    """리더 `_grid_of`는 `int(...)`이고, 실패하면 격자 전체가 None이 되어 정렬이 거절된다."""
    try:
        return int(raw), True
    except (TypeError, ValueError):
        return None, False


# 축 → (리더와 같은 파서, **리더의 부재 기본값**, **등록기가 이 값을 쓸 수 있었는가**,
#        **값이 「선언 없음」을 가리킬 수 있는가**).
#
# 두 번째 성분의 출처는 리더 그 자체다: `_rotation_of:237`(0) · `_side_of:258`("front") ·
# `_y_invert_of:262`(False) · `_grid_of:250-251`(1). 여기 상수를 손으로 적은 것이 아니라
# 리더가 부재에서 만들어 내는 값을 옮긴 것이다 — 리더가 바뀌면 이 표도 같이 바뀌어야 한다
# (`test_orientation_declaration.py`가 그 일치를 리더에게 직접 물어 채점한다).
#
# 세 번째 성분은 `synthesize_grid_meta`의 치역이다(위 ⚠️).
#
# 🔴 네 번째 성분 — **start에는 값으로 하는 판정이 없다**(총괄 확정 2026-08-05).
#    무증거 값 규칙(Rule N)은 「키가 없을 때 리더가 만드는 값과 같으면 증거가 아니다」인데,
#    그 추론은 **키가 없을 수 있을 때만** 성립한다. start는 668행 중 부재가 0건이고, 등록기가
#    쓰는 값이 상수가 아니라 **관측된 최소 좌표**라 어떤 값도 등록기의 서명이 될 수 없다.
#    그래서 start는 표지만이 출처를 가른다: 표지 있으면 `auto_registered`, 없으면 값이
#    무엇이든 `declared`. `indeterminate`는 start에 발생하지 않는다.
#    (이 성분이 없으면 서버는 1을 무증거로, 클라는 0을 무증거로 읽어 668행 중 660행의
#     출처 판정이 서로 뒤집힌다 — 같은 규칙의 두 구현이 만드는 어긋남이다.)
_ORIENTATION_READERS = {
    "rotation":      (_read_rotation,   0,       lambda v: v == 0,       True),
    "side":          (_read_side,       "front", lambda v: v == "front", True),
    "grid_y_invert": (_read_y_invert,   False,   lambda v: v is False,   True),
    "grid_start_x":  (_read_grid_start, 1,       lambda v: True,         False),
    "grid_start_y":  (_read_grid_start, 1,       lambda v: True,         False),
}


def orientation_declaration(meta: dict | None) -> dict:
    """**이 맵의 방위가 「선언」인가** — 축마다, 그 질문의 유일한 철자.

    반환: `{축: {"value": 값, "source": 토큰}}`. 다섯 축 전부가 항상 들어 있다.
    `value`는 **리더가 실제로 쓸 값**이므로(부재·파싱실패면 무증거 값) 호출자가 판정과
    무관하게 그대로 쓸 수 있다 — 값과 출처를 한 번에 주는 것이 이 층의 계약이다(스펙 §0.2 ③).
    모양(`{value, source}`)과 토큰 문자열은 클라 `physDeclaration`(`map_editor.js:1509`)과
    같다. 두 채점기가 어휘를 둘 가지면 매핑표가 필요해지고, 매핑표는 답의 두 번째 구현이다.
    """
    m = meta if isinstance(meta, dict) else {}
    marked = m.get(AUTO_REGISTERED_KEY) is True
    out = {}
    for axis, (reader, absent_default, synth_could_write,
               value_can_indicate_absence) in _ORIENTATION_READERS.items():
        raw = m.get(axis)
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            out[axis] = {"value": absent_default, "source": GEOMETRY_ABSENT}
            continue
        value, ok = reader(raw)
        if not ok:
            out[axis] = {"value": absent_default, "source": GEOMETRY_UNPARSABLE}
        elif marked and synth_could_write(value):
            out[axis] = {"value": value, "source": GEOMETRY_AUTO_REGISTERED}
        elif not value_can_indicate_absence or value != absent_default:
            out[axis] = {"value": value, "source": GEOMETRY_DECLARED}
        else:
            out[axis] = {"value": value, "source": ORIENTATION_INDETERMINATE}
    return out


_ORIENTATION_AXIS_LABEL = {
    "rotation": "회전", "side": "면", "grid_y_invert": "y반전",
    "grid_start_x": "시작 X", "grid_start_y": "시작 Y",
}

# 사유는 **사람이 읽는 자리에서 한 번만** 사람 말로 옮긴다(`_GEOMETRY_REFUSAL_TEXT`와 같은
# 규율). 판정은 `orientation_declaration`이 이미 끝냈고 여기서는 표시만 한다.
_ORIENTATION_REFUSAL_TEXT = {
    GEOMETRY_AUTO_REGISTERED: "자동 등록 때 채워진 값입니다 ― 아무도 재지 않았습니다",
    GEOMETRY_ABSENT: "키가 없습니다",
    GEOMETRY_UNPARSABLE: "값이 읽히지 않습니다",
    ORIENTATION_INDETERMINATE: (
        "값은 있으나 키가 없을 때와 **같은 값**이라, 누가 그렇게 선언한 것인지 "
        "아무도 읽지 않은 것인지 구별할 수 없습니다"),
}


def orientation_refusal(meta: dict | None) -> str | None:
    """방위가 선언이 **아닌** 축과 그 이유(사람 말). 다섯 축 전부 선언이면 None.

    판정은 하지 않는다 — `orientation_declaration`을 호출해 토큰에 문장을 붙일 뿐이다.

    🔴 **아직 아무도 부르지 않는다.** 이 함수를 좌표 경로에 꽂는 것은 동작 변경이고
       (거절이 늘어난다), 그 규모를 먼저 재기로 했다 — 단계 B의 결정이다.
    """
    decl = orientation_declaration(meta)
    parts = [f"{_ORIENTATION_AXIS_LABEL[axis]}: {_ORIENTATION_REFUSAL_TEXT[d['source']]}"
             for axis, d in decl.items() if d["source"] != GEOMETRY_DECLARED]
    if not parts:
        return None
    return " · ".join(parts)


def frame_axes(meta: dict | None):
    """맵 프레임을 정의하는 **축 전부**:
    (회전, 면, y반전, start_x, start_y, cols, rows, phys 서명).

    오버레이 정렬의 지름길(identity 판정)은 **이 튜플이 완전히 같을 때만** 허용된다.
    한 축이라도 다른데 지름길을 타면 전 셀이 어긋난 좌표를 `status: ok`로 내보내게 된다
    (QA O3/B1/M4 — 조용한 오답의 전형).

    [M4] 격자 치수와 phys 규격까지 포함한다. 치수가 빠져 있으면 규격이 다른 두 맵이
    지름길로 통과해 버리고(변환 경로의 치수 검사를 우회), phys가 빠져 있으면 웨이퍼 원
    크롭(바운딩박스)이 다른 두 맵이 무보정으로 붙는다.

    [D3] 빌린 규격도 **값으로** 들어간다(표지는 안 넣는다). 변환기가 쓰는 것은 값뿐이라
    같은 바닥에서 빌린 두 맵이 같은 변환기를 공유하는 것이 맞고, 표지를 축으로 넣으면
    튜플 폭만 늘고 답은 그대로다. 「빌린 값인가」는 좌표가 아니라 기록의 질문이다.

    [D1] phys는 **바이트 그대로**(`_phys_signature`) 넣는다 — 여기에 출처 규칙을 섞지
    않는다. 이 튜플이 완전히 같다는 것은 **선언된 모든 축이 일치**한다는 뜻이고, 그때
    변환은 항등이므로 피치가 무엇이든(재었든 합성이든) 답이 달라질 수 없다. "재지 않은
    값으로 아무것도 하지 않는 것"은 거절할 대상이 아니다. 표지를 축으로 넣으면 실측
    2026-08-04 기준 바뀌는 쌍이 **0건**이면서(표지 없는 1x1 행이 0건이므로) 튜플 폭만
    늘어난다. 거절은 실제로 좌표를 옮기는 자리 하나에서 한다(§`make_frame_transform`).
    """
    g = _grid_of(meta) or {}
    return (_rotation_of(meta), _side_of(meta), _y_invert_of(meta),
            g.get("start_x", 1), g.get("start_y", 1),
            g.get("cols"), g.get("rows"), _phys_signature(meta))


def _frame_phys_params(meta: dict):
    """물리 규격 → **프레임 좌표계 규격**. 웨이퍼 마스크(bbox)는 프레임 격자 위에서 도는
    계산이므로 규격도 프레임 축으로 바꿔 넣어야 한다.

    [왜 필요한가 — QA A1] `PhysicalWaferEngine.is_cell_inside_wafer(c, r, cols, rows)`는
    `x_mm = (c-cc)*chip_x + off_x`, `y_mm = (cr-r)*chip_y + off_y`로 격자 인덱스를 mm로
    바꾼다. 여기서 (c, r)은 **프레임** 인덱스이므로 `chip_x`는 프레임 x축의 피치여야 한다.
    회전 90/270 프레임에서는 그 축이 물리 y축이므로 피치가 **스왑**된다. 메타 값을 그대로
    넣으면 회전 맵의 bbox가 통째로 어긋나고, 저장 좌표가 bbox 상대값이라 전 셀이 어긋난다.

    [유도] `WaferMapCoordinateTransformer.cell_to_physical`이 정의하는 frame→physical
    사상에 엔진의 mm 식을 대입해 항별로 맞춘 결과다. rot 90을 예로 들면
    frame(c,r) → phys(r, VC-1-c)이므로
        x_phys = (cr-r)*cx + Ox ,  y_phys = (c-cc)*cy + Oy
    이고, 엔진이 프레임에서 계산하는 X = (c-cc)*chip_x + off_x 를 y_phys에,
    Y = (cr-r)*chip_y + off_y 를 x_phys에 맞추면 (chip_x, chip_y) = (cy, cx),
    (off_x, off_y) = (Oy, -oox)가 나온다. 노름은 성분 부호에 불변이므로 부호는
    상쇄 항으로만 남는다. 4회전 × front/back 8조합 전부 이 방식으로 확인했다.

    | rotation | (chip_x, chip_y) | (off_x, off_y) |
    |---|---|---|
    | 0   | (cx, cy) | ( oox,  ooy) |
    | 90  | (cy, cx) | ( ooy, -oox) |
    | 180 | (cx, cy) | (-oox, -ooy) |
    | 270 | (cy, cx) | (-ooy,  oox) |

    `oox`는 back에서 부호가 뒤집힌다(`cell_to_physical`이 회전 **전에** 면 반전을 적용하며,
    그 반전이 물리 x축을 뒤집기 때문). 라이브 오프셋이 0/0.1mm라 부호 항은 현재 거의
    발현하지 않지만 스왑 항은 발현한다 — 둘 다 넣어야 재발이 없다.

    ⚠️ 이 보정은 **`map_overlay` 안에 가둔다.** `WaferMapCoordinateTransformer`·
    `PhysicalWaferEngine` 자체는 손대지 않는다 — `bonding_plan.py`가 같은 클래스를
    엔진 없이 공유하므로 부작용 위험이 있다(QA 권고 ②).
    """
    dia, chip_x, chip_y, off_x, off_y, margin = _phys_signature(meta)
    oox = -off_x if _side_of(meta) == "back" else off_x
    ooy = off_y
    rot = _rotation_of(meta)
    if rot == 90:
        return dia, chip_y, chip_x, ooy, -oox, margin
    if rot == 180:
        return dia, chip_x, chip_y, -oox, -ooy, margin
    if rot == 270:
        return dia, chip_y, chip_x, -ooy, oox, margin
    return dia, chip_x, chip_y, oox, ooy, margin


_FRAME_TF_CACHE = {}
_FRAME_TF_CACHE_MAX = 512


def _frame_transformer(meta: dict, grid: dict):
    """메타 → 좌표 변환기(웨이퍼 엔진 포함). 프레임 서명 단위로 캐시한다.

    바운딩박스 계산이 격자 전 셀을 훑으므로(`get_wafer_bounding_box`) 요청마다 재계산하면
    소스 8종 × 왕복에서 비용이 쌓인다. 서명이 같으면 결과가 같으므로 안전하게 재사용된다.
    """
    from utils.coordinate_transformer import WaferMapCoordinateTransformer
    from utils.physical_wafer_engine import PhysicalWaferEngine

    key = frame_axes(meta)
    tf = _FRAME_TF_CACHE.get(key)
    if tf is not None:
        return tf

    dia, chip_x, chip_y, off_x, off_y, margin = _frame_phys_params(meta)
    engine = PhysicalWaferEngine(
        wafer_diameter_mm=dia, chip_size_x_mm=chip_x, chip_size_y_mm=chip_y,
        edge_exclusion_mm=margin, offset_x_mm=off_x, offset_y_mm=off_y)
    tf = WaferMapCoordinateTransformer(
        cols=grid["cols"], rows=grid["rows"],
        start_x=grid["start_x"], start_y=grid["start_y"],
        rotation=_rotation_of(meta), side=_side_of(meta),
        invert_y=_y_invert_of(meta), physical_engine=engine)
    tf.get_wafer_bounding_box()          # 캐시에 넣기 전에 bbox를 확정해 둔다
    if len(_FRAME_TF_CACHE) >= _FRAME_TF_CACHE_MAX:
        _FRAME_TF_CACHE.clear()
    _FRAME_TF_CACHE[key] = tf
    return tf


def make_frame_transform(source_meta: dict, target_meta: dict):
    """소스 프레임 좌표 → 타깃 프레임 좌표 (**각 맵을 물리 좌표 경유로 합성**).

    모든 축을 **하나의 파이프라인**에서 처리한다 — 축마다 별도 분기를 두면 조합에서 새고,
    실제로 두 번 샜다(회전/면만 처리하다 y반전·start 누락 → QA O3, 그다음 바운딩박스
    누락 → QA B1):

        (x,y)_src ──src.visual_to_physical──▶ (xp,yp)_물리 ──dst.physical_to_visual──▶ (x,y)_dst

    [저장 규약의 정본은 클라다 — QA B1]
    셀에 저장된 x/y는 단순한 `셀인덱스 + start`가 아니라 **웨이퍼 원으로 자른 바운딩박스
    상대 좌표**다(`xv = c - box.minC + start_x`). `box`는 phys 파라미터(웨이퍼 지름·칩
    크기·오프셋·edge margin)로 원 밖 셀을 제외해 얻는다. 이 항을 빼고 `c = x - start_x`로
    되돌리면 두 항이 **합성 선형부가 +1일 때만 상쇄**되고, 거울(면 반전·회전 조합)이 끼면
    가산되어 `2·minC`만큼 어긋난다 — 라이브에서 12쌍이 그렇게 조용히 틀렸다.

    그래서 좌표 왕복을 손으로 쓰지 않고 **`WaferMapCoordinateTransformer`의 visual 계층을
    그대로 쓴다**(`visual_to_physical` / `physical_to_visual`). 클라가 미러링하는 바로 그
    알고리즘이므로 bbox·start·y반전 세 항이 자동으로 규약과 일치한다. 손으로 옮겨 쓰면
    y반전 하나만 해도 규약은 `max_r - (yv - start_y)`인데 `(rows-1) - r`로 쓰기 쉽다.

    [명시 실패] 다음은 그리지 않고 ValueError를 낸다(조용한 오답 < 소리 나는 실패):
      - 메타 부재 / 격자 규격 부재
      - 물리 격자 치수 불일치 (같은 웨이퍼 규격이 아님)
      - **기하를 계산에 쓸 근거가 없음**(`geometry_computable`) — 값이 없거나(absent),
        수가 아니거나(unparsable), **있지만 아무도 재지 않았거나**(auto_registered).
        셋 다 같은 결론이다: 바운딩박스를 재현할 근거가 없으면 좌표를 보증할 수 없다.
        🔴 세 번째가 [D1]이 더한 것이다. 종전 관문은 "서명이 **없으면**"이었고 합성된
           1x1 서명은 존재하며 형식도 온전하므로 그대로 통과했다(§geometry_declaration).
        🔴 [D3] 관문이 묻는 것은 **선언인가가 아니라 근거가 있는가**다. 바닥에서 빌린
           규격(`assumed`)은 선언이 아니지만 근거는 된다 — 그 사실은 삼키지 않고 payload와
           확정 기록이 함께 나른다(`map_alignment`·`frame_confirmation`).
    """
    from utils.coordinate_transformer import WaferMapCoordinateTransformer

    s_phys, t_phys = _grid_of(source_meta), _grid_of(target_meta)
    if not s_phys or not t_phys:
        raise ValueError("frame transform requires both map grid metas")
    if (s_phys["cols"], s_phys["rows"]) != (t_phys["cols"], t_phys["rows"]):
        raise ValueError(
            f"physical grid dims differ: source {s_phys['cols']}x{s_phys['rows']} vs "
            f"target {t_phys['cols']}x{t_phys['rows']} — 같은 웨이퍼 규격이 아니다")
    # [D1] 양쪽 다 **이름을 대고** 거절한다. 어느 쪽 맵을 고쳐야 하는지가 조작자에게
    # 필요한 유일한 정보이고, 빈 결과나 그럴듯한 결과는 에러보다 나쁘다.
    refusals = [f"{role} 맵: {why}"
                for role, why in (("소스", geometry_computable(source_meta)),
                                  ("타깃", geometry_computable(target_meta)))
                if why is not None]
    if refusals:
        raise ValueError(
            " · ".join(refusals)
            + " ― 셀 좌표의 기준인 웨이퍼 바운딩박스를 재현할 수 없어 정렬을 보증할 수 "
              "없습니다. 해당 맵의 물리 규격(칩 크기·웨이퍼 지름)을 선언한 뒤 다시 "
              "시도하십시오.")

    src_tf = _frame_transformer(source_meta, s_phys)
    dst_tf = _frame_transformer(target_meta, t_phys)

    def to_target(x, y):
        return dst_tf.physical_to_visual(*src_tf.visual_to_physical(int(x), int(y)))

    return to_target


# ---------------------------------------------------------------------------
# align 결정 (메타 유도 → identity) — 선언 레이어는 없다
# ---------------------------------------------------------------------------

def _align_summary(rotation: int, flip: str) -> dict:
    """표시용 align 요약. **좌표 변환에는 쓰이지 않는다**(`make_frame_transform` 소관).

    구 `bonding_plan.normalize_align`의 자리를 대신하지만 파서가 아니다 — 입력이 config
    문자열이 아니라 두 메타의 차이로 계산된 값이라 검증/강등 로직이 필요 없다.
    """
    return {"rotation": int(rotation) % 360, "flip": flip,
            "offset_x": 0, "offset_y": 0,
            "is_identity": (int(rotation) % 360 == 0 and flip == "none")}


def align_status_label(align: dict | None) -> str | None:
    """상태 문자열용 align 마커 (예: 'aligned:180', 'aligned:180,flip-x').

    가용량 API(`bonding_plan` / `transfer_plan`)의 `sources[role]` 문자열에 붙는다 —
    "정렬을 적용했다"를 사람이 읽을 수 있게 표면화하는 용도이며, 없으면 무보정과 구분되지
    않는다. 변환 소유 모듈이 마커도 소유한다(구 `bonding_plan.align_status_label` 이관).
    """
    if not align or align.get("is_identity"):
        return None
    parts = []
    if align["rotation"]:
        parts.append(str(align["rotation"]))
    if align["flip"] != "none":
        parts.append(f"flip-{align['flip']}")
    if align.get("offset_x") or align.get("offset_y"):
        parts.append("offset")
    return "aligned:" + ",".join(parts)


def resolve_align(source_meta: dict | None, target_meta: dict | None):
    """소스→타깃 align을 **두 맵의 메타만으로** 결정한다.

    반환: (align_summary|None, origin, note|None). None이면 identity.
    origin은 "derived" 또는 "identity" 둘뿐이다 — 선언(override) 레이어가 없으므로
    "declared"/"default"는 더 이상 발생하지 않는다.
    """
    note = None

    if source_meta is None or target_meta is None:
        # 규격을 모른다 = 돌릴 각도를 모른다가 아니라 "차이가 없다고 볼 수밖에 없다" →
        # identity로 간주해 붙인다(선언 부재를 실패로 만들지 않는다).
        return None, ALIGN_ORIGIN_IDENTITY, "맵 메타 부재 — identity로 간주"

    # [지름길 조건 — 네 축 전부 동일할 때만] 회전·면만 비교하면 y반전이나 start 차이가
    # 있는 맵이 그대로 붙어 **전 셀이 균일하게 어긋난 채 status: ok**가 된다(QA O3).
    s_axes, t_axes = frame_axes(source_meta), frame_axes(target_meta)
    if s_axes == t_axes:
        return None, ALIGN_ORIGIN_IDENTITY, None

    rel_rot = (s_axes[0] - t_axes[0]) % 360
    flip = "x" if s_axes[1] != t_axes[1] else "none"

    # 회전·면 밖의 축(y반전·start)은 표시용 요약으로 표현할 수 없으므로 note로 밝힌다 —
    # 클라가 "정렬 0°"만 보고 '아무것도 안 했다'로 읽지 않게 한다.
    extra = []
    if s_axes[2] != t_axes[2]:
        extra.append(f"y반전({s_axes[2]}→{t_axes[2]})")
    if (s_axes[3], s_axes[4]) != (t_axes[3], t_axes[4]):
        extra.append(f"시작좌표({s_axes[3]},{s_axes[4]})→({t_axes[3]},{t_axes[4]})")
    if s_axes[7] != t_axes[7]:
        extra.append("웨이퍼 규격 상이(바운딩박스 재계산)")
    note = ("프레임 정규화 적용: " + ", ".join(extra)) if extra else None

    # [주의] 여기서 만드는 align은 **표시용 요약**이다(클라의 "180° 정렬됨" 배지). 실제 좌표
    # 변환은 `make_frame_transform`이 두 메타로 직접 합성하며 이 요약을 쓰지 않는다 —
    # 상대 회전 + 단일 flip으로는 두 프레임의 반전 축을 표현할 수 없기 때문이다(구 QA B3).
    return _align_summary(rel_rot, flip), ALIGN_ORIGIN_DERIVED, note


def resolve_map_transform(source_meta: dict | None, target_meta: dict | None):
    """**서버의 단일 좌표 변환 진입점.** 메타 → (변환 함수, 표시 요약, origin, note).

    반환 `transform`이 None이면 identity(그대로 붙인다). 변환이 필요한데 계산할 근거가
    없으면 `ValueError` — 호출자가 `align_unavailable`로 표면화한다(조용한 오답 금지).

    오버레이(그리기)와 가용량 산출(`bonding_plan`/`transfer_plan`)이 **같은 이 함수**를
    쓴다. 갈라지면 화면과 수치가 서로 다른 좌표계를 말하게 되고, 그 불일치는 둘 중 하나가
    틀렸을 때에만 드러나므로 조용히 오래 산다.
    """
    align, origin, note = resolve_align(source_meta, target_meta)
    transform = None
    if origin == ALIGN_ORIGIN_DERIVED:
        # ⚠️ `align`(표시용 요약)이 identity로 보여도 **반드시 합성한다** — 회전·면이 같아도
        # y반전이나 start가 다르면 변환이 필요하고, 요약을 보고 건너뛰면 QA O3의 조용한 오답.
        transform = make_frame_transform(source_meta, target_meta)
    return transform, align, origin, note


def _pure_translation(source_meta, target_meta, origin):
    """순수 평행이동인 경우의 (dx, dy). 아니면 None.

    회전·면·y반전이 모두 같고 start만 다를 때만 변환이 평행이동으로 **정확히** 표현된다.
    다른 경우에 offset을 채우면 클라가 틀린 수치를 표시하므로 채우지 않는다.
    """
    if origin != ALIGN_ORIGIN_DERIVED:
        return None
    s, t = frame_axes(source_meta), frame_axes(target_meta)
    # 회전·면·y반전이 같고 **격자/phys 규격도 같아야**(= 바운딩박스가 동일해야) 남는 차이가
    # start뿐이고, 그때만 변환이 평행이동으로 정확히 표현된다.
    if s[:3] != t[:3] or s[5:] != t[5:]:
        return None
    return (t[3] - s[3], t[4] - s[4])


def align_applied_payload(align, origin, note=None, translation=None) -> dict:
    """클라가 '180° 정렬됨' 같은 표시를 할 수 있도록 실제 적용 변환을 담는다."""
    if not align or align.get("is_identity"):
        payload = {"rotation": 0, "flip": "none", "offset": {"x": 0, "y": 0},
                   "origin": origin or ALIGN_ORIGIN_IDENTITY}
        if translation:
            payload["offset"] = {"x": translation[0], "y": translation[1]}
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


# Value-column candidates (earlier wins) — DOCUMENTED DEFAULT only.
# `map_overlay_config.value_column_candidates` overrides this when declared, so every
# consumer must go through resolve_value_column_candidates(cfg); reading this tuple
# directly re-creates the hardcode this default exists to replace. When none of the
# candidates match, the first non-key/non-coordinate/non-system column is the fallback.
DEFAULT_VAL_CANDIDATES = ("val", "value", "leg", "grade", "result", "code", "split", "doe")


def resolve_value_column_candidates(cfg: dict) -> list:
    """Ordered value-column candidate list — declared beats default.

    `value_column_candidates` in map_overlay_config.json is an ordered array of
    column names used to auto-detect which column carries a map's value. Absent
    (or not a usable list of non-empty strings) -> DEFAULT_VAL_CANDIDATES, the
    documented default. GET /api/maps/paint-rules serves this RESOLVED list so
    the client keeps no candidate list of its own.
    """
    declared = (cfg or {}).get("value_column_candidates")
    if isinstance(declared, list):
        names = [c for c in declared if isinstance(c, str) and c.strip()]
        if names:
            return names
    return list(DEFAULT_VAL_CANDIDATES)


def get_default_legend(cfg: dict):
    """Declared default legend rows (verbatim) or None — honest absence.

    `default_legend` in map_overlay_config.json declares the legend rows a map
    gets when the server has no registry rows for it
    (row shape: {"value", "desc", "color", "locked"}). Absent -> None: no default
    semantics exist and the client renders bare values with palette colors — the
    server never invents rows the user did not declare.
    """
    legend = (cfg or {}).get("default_legend")
    return legend if isinstance(legend, list) else None

# 레이어링/시스템 컬럼 — val 후보에서 제외한다
_SYSTEM_COLUMNS = frozenset({
    "row_id", "business_key_val", "created_at", "updated_at",
    "is_graph_synced", "needs_graph_rollback", "graph_synced_at",
})


def _derive_table_binding_full(table: str, val_candidates=None):
    """유도 코어 — `(binding|None, guessed)`를 반환한다.

    `guessed=True`는 값 컬럼이 **후보 매칭이 아니라 추측**이라는 뜻이다(첫 비-키/비-좌표/
    비-시스템 컬럼). [F2] 이 추측은 데이터 경로에는 절대 나가지 않는다 — 공개
    `derive_table_binding`은 이 경우 None(명시 거부)이고, 추측은 클라 전달용
    `resolve_binding_info`에서만 `"source": "fallback_guess"`로 **표기되어** 나간다
    (클라가 엉뚱한 컬럼을 조용히 렌더하는 대신 경고할 수 있게).
    """
    from database import crud

    candidates = DEFAULT_VAL_CANDIDATES if val_candidates is None else val_candidates

    tcfg = (crud.TABLE_CONFIG or {}).get(table)
    if not isinstance(tcfg, dict):
        return None, False
    types = tcfg.get("column_types") or {}
    if "x" not in types or "y" not in types:
        return None, False

    key_cols = tcfg.get("map_key_columns")
    if isinstance(key_cols, str):
        key_cols = [key_cols]
    if not (isinstance(key_cols, list) and key_cols):
        key_cols = ["lot", "slot"] if ("lot" in types and "slot" in types) else None
    if not key_cols:
        return None, False

    excluded = set(key_cols) | {"x", "y", tcfg.get("business_key")} | _SYSTEM_COLUMNS
    val = next((c for c in candidates if c in types and c not in excluded), None)
    guessed = False
    if val is None:
        val = next((c for c in types if c not in excluded), None)
        if val is None:
            return None, False
        guessed = True

    return {"x": "x", "y": "y", "val": val, "key_columns": list(key_cols)}, guessed


def derive_table_binding(table: str, val_candidates=None) -> dict | None:
    """`table_config` 선언에서 맵 좌표 바인딩을 **자동 유도**한다. 불가하면 None.

    [왜 유도가 정본인가] `map_overlay_config.table_bindings`에 선언된 맵만 겹칠 수 있으면
    "모든 맵을 universal하게 겹쳐 본다"는 요구와 정면으로 어긋난다(신규 맵 테이블이 조용히
    실패한다 — 라이브 사고: `test` 미선언으로 "소스 맵을 찾을 수 없습니다"). 맵의 좌표계는
    이미 `table_config`가 선언하고 있으므로(`map_key_columns` + x/y 컬럼) 거기서 유도하고,
    config 선언은 **예외 보정용**(컬럼명이 관례와 다른 `dt_log`/`bonding_log` 등)으로만 둔다.

    - key_columns: `map_key_columns` 정본. 미선언이면 lot/slot 둘 다 있을 때만 관례 폴백.
    - x/y: 리터럴 `x`/`y` 컬럼. 없으면 유도 실패(관례 밖 이름은 선언으로 보정).
    - val: resolved candidates only (val_candidates arg; None -> DEFAULT_VAL_CANDIDATES —
      callers holding a cfg must pass resolve_value_column_candidates(cfg)). [F2] 후보가
      하나도 안 맞으면 **유도 실패(None)**다 — x/y 부재와 같은 명시 거부. 과거의 "첫
      데이터 컬럼 추측"은 데이터 경로에서 제거됐고, `resolve_binding_info`가
      `"source": "fallback_guess"`로 표기해 서빙할 때만 존재한다.
    """
    binding, guessed = _derive_table_binding_full(table, val_candidates)
    if binding is None or guessed:
        return None
    return binding


def resolve_binding(cfg: dict, table: str) -> dict | None:
    """테이블의 좌표 컬럼 바인딩. **config 선언 > table_config 유도** 순. 둘 다 없으면 None.

    None은 "이 테이블은 맵으로 해석할 수 없다"는 뜻이며 호출자가 명시 실패로 표면화한다
    (관례 값으로 조용히 추측해 0건을 정상처럼 내보내지 않는다)."""
    bindings = (cfg.get("table_bindings") or {})
    b = bindings.get(table)
    if isinstance(b, dict) and b.get("columns"):
        return dict(b["columns"])
    return derive_table_binding(table, resolve_value_column_candidates(cfg))


def resolve_binding_info(cfg: dict, table: str) -> dict | None:
    """[F1] 클라 전달용 RESOLVED 바인딩 + 출처 — `GET /api/maps/paint-rules`가 서빙한다.

    우선순위는 데이터 경로(`resolve_binding`)와 동일: **선언 > 유도**. 반환 형태는
    `{"x", "y", "val", "key_columns": [...], "source": "declared"|"derived"|"fallback_guess"}`,
    해석 불가면 None. 선언 바인딩의 누락 키는 데이터 경로가 실제로 쓰는 기본값
    (x/y/val 리터럴, key_columns=[lot, slot])으로 채워 **효력 그대로**를 서빙한다.

    [F2] 데이터 경로와 유일하게 다른 점: 후보 밖 값 컬럼 추측이 여기서는 나가되 **반드시**
    `"source": "fallback_guess"`로 표기된다 — 클라는 이 표지를 보고 경고해야 하며,
    선언/유도 바인딩처럼 신뢰하고 조용히 렌더하면 안 된다(데이터 경로는 이 경우 거부).
    """
    b = (cfg.get("table_bindings") or {}).get(table)
    if isinstance(b, dict) and b.get("columns"):
        cols = dict(b["columns"])
        key_cols = cols.get("key_columns") or ["lot", "slot"]
        if isinstance(key_cols, str):
            key_cols = [key_cols]
        return {"x": cols.get("x", "x"), "y": cols.get("y", "y"),
                "val": cols.get("val", "val"),
                "key_columns": list(key_cols), "source": "declared"}
    binding, guessed = _derive_table_binding_full(
        table, resolve_value_column_candidates(cfg))
    if binding is None:
        return None
    binding["source"] = "fallback_guess" if guessed else "derived"
    return binding


def map_key_parts(binding: dict, map_key: str):
    """map_key(관례상 `_`로 조인된 복합 키) → `[(키 컬럼, 원문 조각)]`.

    **분해 규칙의 단일 지점**이다. `build_key_filters`(셀 필터)와 `canonical_map_key`
    (정체성 문자열)가 이것을 공유한다 — 갈라지면 같은 선언이 셀은 찾고 메타는 못 찾는
    (또는 그 반대의) 상태가 조용히 생긴다.
    """
    key_cols = binding.get("key_columns") or ["lot", "slot"]
    if isinstance(key_cols, str):
        key_cols = [key_cols]
    parts = str(map_key).split("_")
    if len(parts) < len(key_cols):
        # 분해 불가 — 단일 컬럼으로 통째 매칭 시도
        return [(key_cols[0], str(map_key))]
    # 마지막 컬럼이 나머지를 흡수(랏 이름에 '_'가 있는 경우 방어)
    head = parts[:len(key_cols) - 1]
    tail = "_".join(parts[len(key_cols) - 1:])
    return list(zip(key_cols, head + [tail]))


def build_key_filters(model, binding: dict, map_key: str):
    """map_key를 key_columns에 분해해(`map_key_parts`) 셀 필터를 만든다.

    [7b] Each decomposed part is a parsed token: it binds through
    `canonical_bind_value` so a padded '01' still finds a number-declared
    column storing 1 (cell-data filters already cast by declared type — this
    is the same discipline for map-key binds)."""
    table_name = getattr(model, "__tablename__", None) \
        or getattr(getattr(model, "__table__", None), "name", None)
    filters = []
    for name, val in map_key_parts(binding, map_key):
        col = getattr(model, name, None)
        if col is None:
            return None
        filters.append(col == canonical_bind_value(table_name, name, val))
    return filters


def canonical_map_key(table: str, binding: dict, map_key: str) -> str:
    """선언·파싱된 map_key → **실제로 저장돼 있는 정체성** 문자열.

    [왜 필요한가 — 7b가 남긴 마지막 구멍] `compose_map_id`는 **조각으로부터** 키를 만들 때
    캐노니컬화한다. 그런데 이미 조립된 키 문자열이 밖에서 들어오면(선언·파싱 산물) 그
    문자열은 캐노니컬하지 않을 수 있다 — `number` 선언 slot에 저장된 1은 메타가 `LOT_1`로
    등록되는데 선언은 `LOT_01`을 준다. 셀 필터는 `build_key_filters`가 컬럼 타입으로
    캐스팅해 살아남지만, `load_map_meta`는 `map_id` **문자열 정확 일치**라 조용히 빗나간다
    (= "메타는 있는데 아무도 못 찾는다").

    분해는 `map_key_parts`, 값 정규화는 `canonical_bind_value` → `canonical_key_value`.
    **두 번째 정규화 구현이 아니다** — 기존 두 함수의 조합일 뿐이다. 읽을 수 없는 조각은
    트림한 원문을 그대로 두어 조회가 정직하게 빗나간다(키를 지어내지 않는다).
    """
    out = []
    for name, val in map_key_parts(binding, map_key):
        cv = canonical_bind_value(table, name, val)
        out.append("" if cv is None else str(cv))
    return "_".join(out)


def get_overlay(db, cfg: dict, target_table: str, target_key: str,
                sources: list, cell_cap: int = MAX_OVERLAY_CELLS) -> dict:
    """타깃 맵 프레임 좌표로 정렬된 오버레이 셀들을 반환한다."""
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

        binding = resolve_binding(cfg, s_table)
        if binding is None:
            entry["status"] = STATUS_SOURCE_MISSING
            entry["detail"] = (
                f"'{s_table}'의 맵 좌표 바인딩을 유도할 수 없음 — table_config에 x/y 컬럼, "
                f"map_key_columns(또는 lot/slot), 그리고 값 컬럼 후보"
                f"(value_column_candidates 중 하나)가 있어야 하며, 컬럼명이 관례와 다르면 "
                f"map_overlay_config.table_bindings에 선언해야 한다")
            entry["align_applied"] = align_applied_payload(None, ALIGN_ORIGIN_IDENTITY)
            overlays.append(entry)
            continue
        x_col = getattr(model, binding.get("x", "x"), None)
        y_col = getattr(model, binding.get("y", "y"), None)
        val_col = getattr(model, binding.get("val", "val"), None)
        if x_col is None or y_col is None:
            entry["status"] = STATUS_SOURCE_MISSING
            entry["detail"] = f"'{s_table}'에 좌표 컬럼이 없음"
            entry["align_applied"] = align_applied_payload(None, ALIGN_ORIGIN_IDENTITY)
            overlays.append(entry)
            continue

        filters = build_key_filters(model, binding, key)
        if filters is None:
            entry["status"] = STATUS_SOURCE_MISSING
            entry["detail"] = f"'{s_table}'의 키 컬럼 바인딩 해석 실패"
            entry["align_applied"] = align_applied_payload(None, ALIGN_ORIGIN_IDENTITY)
            overlays.append(entry)
            continue

        source_meta = load_map_meta(db, s_table, key)
        try:
            transform, align, origin, note = resolve_map_transform(source_meta, target_meta)
        except ValueError as ve:
            align, origin, note = resolve_align(source_meta, target_meta)
            entry["status"] = STATUS_ALIGN_UNAVAILABLE
            entry["detail"] = f"격자 규격 비호환: {ve}"
            entry["align_applied"] = align_applied_payload(align, origin, note)
            overlays.append(entry)
            continue

        entry["align_applied"] = align_applied_payload(
            align, origin, note,
            translation=_pure_translation(source_meta, target_meta, origin))

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
# [M4 phase 1] valid_die_ref — 유효 다이 집합은 "그 맵 자체"다
#
# 원 기하는 판정자에서 **생성기로 강등**된다. 테이프에 붙은 dt 맵은 300mm 제약이 없어
# 원으로 표현할 수 없는 유효 다이 형상을 가지는데, 지금은 그것을 저장할 자리가 없다.
# phase 1은 `wafer_map_metadata.grid_metadata`에 **가산적 선언 하나**를 들이고 그것을
# 소비한다 — 선언이 없는 맵은 이전과 완전히 동일하게 동작한다.
#
#     "valid_die_ref": {"table": "<맵 테이블>", "map_id": "<맵 키>"}   (table 생략 가능)
#     "valid_die_ref": "<맵 키>"                                      (테이블은 승계)
#
# 테이블을 생략하면 **선언한 맵 자신의 테이블을 승계**한다(같은 테이블의 다른 맵 —
# 제품 템플릿 맵 — 을 가리키는 것이 가장 흔한 사용이다). 문법·거절 문구는 클라
# `parseValidDieRef`와 문자 그대로 같으며 정본은 `contracts/map_seam/vectors.json`이다.
#
# [phase 2에서 더해진 것] 선언을 **쓰는** 짝(`apply_valid_die_ref`)과 **1홉 제한**
# (`valid_die_chain_error`, 규율 ⑤). 둘 다 계약 심볼이며 클라의 `applyValidDieRef` ·
# `validDieChainError`와 같은 벡터로 채점된다.
#
# [규율 다섯 — 하나라도 어기면 조용한 오답이 된다]
#  ① 선언이 없으면 이 코드는 **아무 일도 하지 않는다.** 판정에 참여하지 않고, 기존 경로가
#     읽는 어떤 값(`frame_axes`·`_grid_of`·`_phys_signature`)에도 새 키가 섞이지 않는다.
#  ② 선언이 있으면 **참조 맵이 답의 전부**다. 원 기하는 답에 참여하지 않는다.
#     (참조 맵을 선언 맵의 프레임으로 옮기는 정렬에는 여전히 프레임 규격이 쓰인다 —
#      그것은 좌표계 문제이지 유효성 판정이 아니며, 원을 `inside`에서 은퇴시키는 것은
#      phase 3의 몫이다.)
#  ③ 참조를 풀 수 없으면 **사유를 붙여 거절**한다. 절대 원 기하로 조용히 되돌아가지
#     않는다 — 조용한 폴백은 틀린 답을 맞은 답과 구별할 수 없게 만든다.
#  ④ 참조 키는 7b 캐노니컬화(`canonical_key_value`)를 **경유**한다. 여기서는
#     `build_key_filters`를 그대로 써서 그 경유를 구조적으로 보장한다 — 두 번째
#     정규화 구현을 만들지 않는다.
#  ⑤ [INV-M4-6] 참조 체인은 **1홉**이다. 유효 다이 맵도 맵이라 자기 참조(A→A)와 2단계
#     (A→B→C)가 구조적으로 가능한데, 전자는 동어반복이고 후자는 **아무도 선언한 적 없는
#     집합**(B의 저장 셀)을 답으로 내놓는다. 둘 다 정상 해석처럼 보이므로 ③과 같은
#     규율로 거절한다 — 사유를 붙여 `refused`, 원 기하로 되돌아가지 않는다.
#
# [값이 아니라 존재다] 참조 맵에 **행이 있는 셀이 유효 다이**다. 값으로 거르지 않는다
# (값 기반 필터가 필요해지면 그때 선언을 늘린다 — 지금 지어내지 않는다).
#
# [쓰기 경로를 막지 않는다] 선언이 망가져 있어도 메타 행 저장은 거절하지 않는다.
# 사용자의 교정을 계기가 막아선 안 된다 — 잘못은 **읽는 시점에** 사유와 함께 드러낸다.
# ---------------------------------------------------------------------------

VALID_DIE_REF_KEY = "valid_die_ref"

# [1-a] THE READ PIN (user ruling 2026-08-04: "불러오기는 무조건 valid_die_ref 를 이용하게").
# A valid-die map is ALWAYS read from this table, whatever the declaration names. The client
# pinned its half in `c97b319` (`map_editor.js` const `VALID_DIE_TABLE`, contract role
# `client_consts`); this is the server half, and until it landed the two sides named DIFFERENT
# maps for the same legacy row — the server resolved a bare string against the declaring map's
# own table while the client looked here (recorded as an OPEN divergence in
# `contracts/map_seam/vectors.json` -> `valid_die_ref_parse_cases`).
#
# 🔴 THE STRING COLLISION IS A COINCIDENCE, NOT A DEFINITION. `VALID_DIE_REF_KEY` is the
#    grid_metadata KEY and `VALID_DIE_TABLE` is the storage TABLE; they happen to spell the
#    same. Two names because they are two things — collapsing them would make renaming either
#    one silently rename the other.
#
# The name is not invented here: `product_tables.PRODUCT_TABLES` declares `valid_die_ref` as a
# PRODUCT-OWNED table (same ruling), and `test_valid_die_ref.py` asserts this constant is one
# of its keys so the two cannot drift.
VALID_DIE_TABLE = "valid_die_ref"

# 셀 목록을 만드는 연산이므로 상한이 필수다(MAX_OVERLAY_CELLS와 같은 규율·같은 크기 —
# 300mm/2.5mm 웨이퍼가 14,400셀이라 실 격자는 여유롭게 들어온다). 초과 시 **자르지 않고
# 거절**한다: 잘린 유효 다이 집합은 "맞아 보이는 틀린 집합"이라 절단이 곧 오답이다.
MAX_VALID_DIE_CELLS = 20_000

# 작업 단위 캐시 상한. 넘치면 그냥 비운다 — 최악이 중복 해석 1회이고 오답은 아니다
# (`_FRAME_TF_CACHE`·`map_meta_registrar._known_present`와 같은 규율).
_VALID_DIE_CACHE_MAX = 64

STATUS_NOT_DECLARED = "not_declared"      # 선언 자체가 없다 (실패가 아니다)
STATUS_REF_UNAVAILABLE = "ref_unavailable"  # 참조는 찾았으나 신뢰할 집합을 만들 수 없다


def load_map_meta_cached(db, target_table: str, map_id: str, cache=None):
    """`load_map_meta` + 작업 단위 스냅샷 캐시(`bonding_plan.load_map_meta`와 같은 규율).

    같은 (table, map_id)를 한 작업 안에서 여러 번 조회하면 N+1이 된다. cache는 호출자가
    작업(요청) 경계에서 하나 만들어 넘긴다. None이면 캐시 없이 매번 조회한다.
    """
    if cache is None:
        return load_map_meta(db, target_table, map_id)
    k = ("meta", target_table, map_id)
    if k not in cache:
        cache[k] = load_map_meta(db, target_table, map_id)
    return cache[k]


def parse_valid_die_ref(meta: dict | None, default_table: str = None):
    """`grid_metadata`의 valid_die_ref 선언 → `({"table","map_id","declared_table"}|None, error|None)`.

    반환 조합은 셋뿐이다:
      (None, None)  — 선언이 없다. 호출자는 **이전과 똑같이** 행동해야 한다.
      (ref,  None)  — 해석됐다.
      (None, error) — 선언은 있는데 읽을 수 없다. 호출자는 사유를 붙여 거절한다.

    문법(계약 — `contracts/map_seam/` · 클라 `parseValidDieRef`와 문자 그대로 같다):

        "TPL_1"                         맵 키 문자열.
        {"table": t, "map_id": k}       `target_table`/`map_key`도 같은 뜻으로 받는다
                                        (전자는 wafer_map_metadata의 실제 컬럼명, 후자는 별칭).
                                        **map_id는 필수**.

    [1-a] **조회 테이블은 언제나 `VALID_DIE_TABLE`이다.** 선언이 어느 테이블을 이름 붙였든
    (또는 생략해 자기 테이블을 승계했든) `table`은 고정 상수이고, 선언이 원래 뜻했던 테이블은
    **버리지 않고** `declared_table`로 함께 돌려준다. 지운 정보를 나중에 추측으로 복원하는
    일을 만들지 않기 위해서다 — 해석이 실패했을 때 "키가 틀렸다"와 "키는 맞는데 여기 없다"는
    서로 다른 수리를 요구하므로, 거절문이 그 둘을 구별해 말할 수 있어야 한다
    (`valid_die_redirect_note`). 클라 `parseValidDieRef`의 `declaredTable`과 같은 값이다.

    `default_table`은 이제 **조회 대상을 정하지 않는다.** 맨 문자열 선언이 원래 뜻했던 것
    ("내 테이블의 맵")을 `declared_table`에 담는 데만 쓴다.

    ⚠️ **`null`/부재만 "선언 없음"이고 그 밖은 전부 선언이다.** 읽을 수 없는 선언을 "선언
    없음"으로 접으면 오타 하나가 조용히 원 기하로 되돌아간다 — 틀린 답과 맞는 답이 구별되지
    않는 바로 그 상태다. 그래서 형태 위반은 (None, None)이 아니라 (None, error)다.
    """
    raw = (meta or {}).get(VALID_DIE_REF_KEY)
    if raw is None:
        return None, None

    home = str(default_table).strip() if default_table else None

    if isinstance(raw, str):
        map_id = raw.strip()
        if not map_id:
            return None, ("valid_die_ref가 비어 있다 — 맵 키가 없으면 유효 다이를 판정할 "
                          "근거가 없다")
        # PINNED READ (string form). 고정 이전에 이 형태는 "내 테이블의 맵"을 뜻했다 —
        # 그 뜻은 조회 대상이 아니라 `declared_table`로만 남는다.
        return {"table": VALID_DIE_TABLE, "map_id": map_id,
                "declared_table": home}, None

    if not isinstance(raw, dict):
        return None, (f"valid_die_ref의 형태를 읽을 수 없다({type(raw).__name__}) — "
                      f'{{"table", "map_id"}} 또는 맵 키 문자열이어야 한다')

    t = raw.get("table", raw.get("target_table"))
    k = raw.get("map_id", raw.get("map_key"))
    map_id = "" if k is None else str(k).strip()
    if not map_id:
        return None, ("valid_die_ref에 map_id가 없다 — 어느 맵을 가리키는지 알 수 없다")
    declared = str(t).strip() if (t is not None and str(t).strip()) else home
    # PINNED READ (object form). 선언이 어느 테이블을 이름 붙였든 조회는 VALID_DIE_TABLE이다.
    return {"table": VALID_DIE_TABLE, "map_id": map_id,
            "declared_table": declared}, None


def valid_die_redirect_note(ref) -> str:
    """[1-a] 이 선언은 고정 이전에 **다른 테이블**을 이름 붙였는가 — 붙였으면 거절문에 덧붙일
    한 문장을 돌려준다(아니면 빈 문자열).

    해석 실패의 이유가 「키가 틀렸다」인지 「키는 맞는데 이 테이블에 없다」인지는 **수리가
    다르다**. 성공하면 아무 말도 하지 않는다 — 읽기는 무마찰이고, 성공한 조회에 대해 어디서
    읽었는지 설명할 이유가 없다(규율: 개별로는 조용하고 실패할 때만 이름을 댄다).

    클라 `resolveValidDie`의 `redirectNote`와 같은 문장이다.
    """
    declared = (ref or {}).get("declared_table") if isinstance(ref, dict) else None
    if not declared or str(declared) == VALID_DIE_TABLE:
        return ""
    return (f" (이 지정은 원래 「{declared}」을(를) 가리켰지만, 유효 다이 맵은 언제나 "
            f"{VALID_DIE_TABLE}에서 읽습니다 — 그 맵을 {VALID_DIE_TABLE}에 등록하거나 "
            f"키를 고치십시오.)")


def valid_die_ref_display(raw):
    """저장된 **원문 바이트**가 무엇을 말하는가 → `{"table", "map_id"}` (테이블 미지정은 "").

    계약 심볼(`contracts/map_seam` 역할 `valid_die_ref_display`) · 클라
    `validDieRefDisplay`의 짝이다. **`parse_valid_die_ref`와 다른 질문에 답한다:**

      `parse_valid_die_ref`  — "어디서 읽을 것인가." 고정 이후 답은 언제나 `VALID_DIE_TABLE`.
      `valid_die_ref_display` — "무엇이 저장돼 있는가." 고정과 무관한 **바이트 그대로**.

    🔴 이 구분이 없으면 "쓰기는 선언된 테이블을 보존한다"가 **반증 불가능**해진다 — 저장 결과를
       고정된 파서로 되읽으면 무엇을 썼든 `valid_die_ref`가 나오기 때문이다. 저작 계약
       (`valid_die_authoring_cases`)의 `expect_table`은 그래서 이 함수로 채점된다.

    읽을 수 없는 원문도 **버리지 않고** 보이는 대로 key에 담는다(숫자·불리언·그 밖). 예쁘게
    다듬으면 사용자가 자기 오타를 볼 수 없다.
    """
    if raw is None:
        return {"table": "", "map_id": ""}
    if isinstance(raw, str):
        return {"table": "", "map_id": raw}
    if isinstance(raw, dict):
        t = raw.get("table", raw.get("target_table"))
        k = raw.get("map_id", raw.get("map_key"))
        if k is not None:
            return {"table": "" if t is None else str(t), "map_id": str(k)}
    if isinstance(raw, (int, float)):        # bool is an int here, deliberately
        return {"table": "", "map_id": str(raw)}
    try:
        return {"table": "", "map_id": json.dumps(raw, ensure_ascii=False)}
    except (TypeError, ValueError):
        return {"table": "", "map_id": str(raw)}


def apply_valid_die_ref(meta: dict | None, ref) -> dict:
    """선언의 **쓰기** — `parse_valid_die_ref`의 짝이자 계약 심볼(`contracts/map_seam`
    역할 `apply_valid_die_ref`). 클라 `applyValidDieRef`와 **같은 벡터**로 채점된다.

    순수 함수다. `meta`를 **변형하지 않고** 새 dict를 반환한다 — 변형하면 편집 취소 경로가
    이미 바뀐 메타를 들고 있게 된다.
    `ref`: None(해제) | 맵 키 문자열 | `{"table","map_id"}`(`target_table`/`map_key` 별칭).

    🔴 **빈 키는 해제다.** 비운 입력칸을 그대로 흘려보내면 `valid_die_ref: ""`가 저장되고,
       파서 규칙상 그것은 **선언**이라 그 맵은 영구히 `refused`가 된다. `valid_die_ref`는
       `grid_metadata` JSON 안에 살아 다른 편집기가 없으므로 되돌릴 길이 없다.
    🔴 **테이블 없는 객체는 만들지 않는다.** `{"map_id": k}`는 서버/클라가 서로 다르게 읽기로
       **기록된** 유일한 형태다(`valid_die_ref_home_divergence_cases`). 저작 시점에는 자기
       테이블을 아니까 그런 반쪽 선언을 제조할 이유가 없다 — 문자열 승계형으로 쓴다.
    🔴 **나머지 키는 손대지 않는다.** 아는 필드로 메타를 다시 짜면 모르는 키(`binding` 등)가
       사라지고, `v or dflt`로 베끼면 선언된 `phys_edge_margin: 0`이 3.0이 되어 참조만 지운
       맵의 웨이퍼 마스크가 움직인다.
    """
    out = dict(meta) if isinstance(meta, dict) else {}

    def _clear():
        out.pop(VALID_DIE_REF_KEY, None)
        return out

    if ref is None:
        return _clear()

    if isinstance(ref, str):
        map_id = ref.strip()
        if not map_id:
            return _clear()
        out[VALID_DIE_REF_KEY] = map_id
        return out

    if isinstance(ref, dict):
        t = ref.get("table", ref.get("target_table"))
        k = ref.get("map_id", ref.get("map_key"))
        map_id = "" if k is None else str(k).strip()
        if not map_id:
            return _clear()
        table = "" if t is None else str(t).strip()
        out[VALID_DIE_REF_KEY] = map_id if not table else {"table": table,
                                                           "map_id": map_id}
        return out

    # 우리가 저작하지 않는 형태(숫자·불리언·리스트)는 만들지 않는다 — 해제로 읽는 편이
    # 읽을 수 없는 선언을 새로 쓰는 것보다 낫다.
    return _clear()


def valid_die_chain_error(ref, ref_meta, home):
    """[INV-M4-6] 참조 체인은 **1홉**이다 — 계약 심볼(`contracts/map_seam` 역할
    `valid_die_chain_error`). 클라 `validDieChainError`와 **같은 벡터**로 채점된다.

    순수 함수다(DB 없음). 거절할 두 형태:

      자기 참조 A→A   그 맵의 저장된 셀이 그 맵의 유효성 기준이 된다. 존재하는 셀은 전부
                     유효이고 없는 셀은 전부 무효 — 정의상 항상 참이라 아무 판정도 하지
                     않으면서, 칩에는 **정상 해석**으로 보인다.
      2단계 A→B(→C)  B의 저장 셀을 쓰지만 B는 자기 유효 다이가 C의 것이라고 선언했다.
                     A가 받는 집합은 **아무도 선언한 적 없는 집합**이다.

    순환 A→B→A는 별도 규칙이 필요 없다: B가 선언했으므로 A가 거절한다. 방문 집합도 재귀
    깊이도 만들지 않는다 — 이미 답한 질문에 두 번째 답을 만드는 일이기 때문이다.

    🔴 "선언"의 뜻은 파서와 **같다**: `None`/부재만 부재이고 나머지는 전부 선언이다.
       `if ref_meta.get(...)` (falsy 검사)는 `0`·`False`·`""`를 부재로 접어 틀리고,
       `parse(...)[0] is not None`은 **깨진** 2단계 선언을 부재로 접어 틀린다(INV-M4-3이
       금지하는 조용한 폴백, 한 층 아래).
    🔴 **정규화를 여기서 하지 않는다.** `ref`/`home`의 키는 호출자가 이미 `canonical_map_key`를
       태운 정준 정체성이다. 여기서 다시 다듬으면 정규화가 둘이 되고, `slot: string`에서
       정당한 `LOT_01` 참조가 자기 참조로 오판된다(INV-M4-4가 금지).

    인자: `ref` = 해석·정준화가 끝난 `{"table","map_id"}` · `ref_meta` = 참조 맵의
          `grid_metadata`(미상이면 None) · `home` = 선언한 맵의 `{"table","map_id"}`
    반환: 사유 문자열(위법) | None(적법)
    """
    r = ref if isinstance(ref, dict) else {}
    h = home if isinstance(home, dict) else {}
    r_table, h_table = r.get("table"), h.get("table")

    if (r_table is not None and h_table is not None
            and str(r_table) == str(h_table)
            and str(r.get("map_id")) == str(h.get("map_id"))):
        return (f"자기 자신({r_table} · {r.get('map_id')})을 유효 다이 맵으로 지정했습니다 — "
                f"맵이 자기 셀로 자기 유효성을 정하면 항상 참이라 아무것도 판정하지 "
                f"못합니다. 다른 맵을 지정하거나 지정을 비우십시오.")

    # 참조 맵의 규격을 모르는 것은 체인 문제가 아니다 — 그 실패는 상류
    # (`align_unavailable`)가 이미 말한다. 한 상태에 어휘를 둘 주지 않는다.
    if not isinstance(ref_meta, dict) or VALID_DIE_REF_KEY not in ref_meta:
        return None
    inner = ref_meta[VALID_DIE_REF_KEY]
    if inner is None:
        return None

    # 문자열이 아닌 선언은 **원형 그대로**(repr) 보여준다. 예쁘게 다듬으면 `0`이나
    # `{"nonsense": true}` 같은 **망가진** 2단계 선언이 멀쩡해 보이고, 사용자는 자기가
    # 무엇을 잘못 썼는지 볼 수 없다(①이 raw를 붙든 이유와 같다).
    shown = inner if isinstance(inner, str) else repr(inner)
    return (f"참조 맵({r_table} · {r.get('map_id')})이 스스로 또 다른 유효 다이 맵"
            f"({shown})을 참조합니다 — 참조 체인은 1단계까지만 허용합니다. "
            f"유효 다이 맵 자신은 valid_die_ref를 갖지 않아야 합니다.")


# ---------------------------------------------------------------------------
# 판정 근거의 단일 분기점 (계약 심볼 — `contracts/map_seam/vectors.json`)
# ---------------------------------------------------------------------------

SOURCE_CIRCLE = "circle"     # 선언 없음 — `2a9f6c4` 그대로
SOURCE_REF = "ref"           # 참조 맵이 **유일한** 근거
SOURCE_REFUSED = "refused"   # 선언은 있는데 풀지 못했다 — 원으로 되돌아가지 않는다

_CIRCLE_MASK_CACHE = {}
_CIRCLE_MASK_CACHE_MAX = 256


def circle_die_mask(meta: dict | None):
    """원 기하가 인정하는 **프레임 셀 인덱스** `(c, r)` 집합 — `2a9f6c4`의 답 그대로.

    좌표계는 `PhysicalWaferEngine.is_cell_inside_wafer(c, r, C, R)`의 것이다(프레임 격자,
    회전 90/270이면 치수 스왑). 규격이 미등록이라 재현할 수 없으면 None — 지어내지 않는다.

    [스케일] 격자 전 셀 1회 훑기(실 격자는 최대 100×100 안팎)이고 `frame_axes` 단위로
    캐시된다. 셀 단위 반복 호출로 떨어지는 경로는 없다.

    [D1] 여기는 **출처를 묻지 않는다** — 정렬 관문과 다른 질문이기 때문이다. 정렬은
    "이 피치를 근거로 남의 좌표계로 옮겨도 되는가"를 묻고 합성값은 근거가 못 되지만,
    이 함수는 "이 기하가 무슨 셀을 인정하는가"를 묻는다. 합성 규격은 격자 반대각선을
    외접하는 지름을 골라 **전 셀 유효**를 말하도록 만들어진 것이고(마스크 중립), 그게
    정확히 그 규격이 옳게 말할 수 있는 한 가지다. 여기서 None을 돌려주면 그 의도된
    답까지 버리게 되고, 클라(`isCellInsideWaferFast`)는 여전히 전 셀 유효라고 답하므로
    없던 이음새 불일치가 생긴다.
    """
    grid = _grid_of(meta)
    if grid is None or _phys_signature(meta) is None:
        return None

    key = frame_axes(meta)
    hit = _CIRCLE_MASK_CACHE.get(key)
    if hit is not None:
        return hit

    from utils.physical_wafer_engine import PhysicalWaferEngine
    dia, chip_x, chip_y, off_x, off_y, margin = _frame_phys_params(meta)
    engine = PhysicalWaferEngine(
        wafer_diameter_mm=dia, chip_size_x_mm=chip_x, chip_size_y_mm=chip_y,
        edge_exclusion_mm=margin, offset_x_mm=off_x, offset_y_mm=off_y)
    rot = _rotation_of(meta)
    cols, rows = ((grid["rows"], grid["cols"]) if rot in (90, 270)
                  else (grid["cols"], grid["rows"]))
    mask = frozenset(
        (c, r) for r in range(rows) for c in range(cols)
        if engine.is_cell_inside_wafer(c, r, cols, rows))

    if len(_CIRCLE_MASK_CACHE) >= _CIRCLE_MASK_CACHE_MAX:
        _CIRCLE_MASK_CACHE.clear()
    _CIRCLE_MASK_CACHE[key] = mask
    return mask


def _basis_from_resolver(result):
    """resolver 반환값 → `(cells|None, reason)`. 세 형태를 받는다:

      None                             풀지 못했다
      {"status", "cells", "detail"}    `resolve_valid_die_set`의 반환(그대로 꽂힌다)
      [(x, y), ...] / set / frozenset  셀 집합

    **셀 0개는 해석된 것이 아니다** — "온 웨이퍼가 무효"는 답이 아니라 사고다.
    """
    if result is None:
        return None, "참조 맵을 해석하지 못했다"
    if isinstance(result, dict):
        if result.get("status") != STATUS_OK:
            return None, (result.get("detail")
                          or f"참조 해석 실패 ({result.get('status')})")
        cells = result.get("cells") or ()
    else:
        cells = result
    try:
        basis = frozenset((int(x), int(y)) for (x, y) in cells)
    except (TypeError, ValueError) as e:
        return None, f"참조 맵의 좌표를 읽을 수 없다: {e}"
    if not basis:
        return None, "참조 맵에 셀이 0건 — '유효 다이 0개'가 아니라 '아직 적재되지 않았다'로 읽는다"
    return basis, ""


def resolve_valid_die_basis(meta: dict | None, resolver=None, table: str = None) -> dict:
    """**유효 다이를 무엇으로 판정할 것인가** — 근거가 갈리는 유일한 지점. 순수 함수(DB 없음).

    반환 `{"basis", "source", "reason"}`:

      source `circle`   선언이 없다 → `2a9f6c4` 그대로. basis는 원 마스크(`circle_die_mask`,
                        프레임 셀 인덱스)이며 규격 미등록이면 None이다 — 호출자가 이미
                        자기 원 판정을 갖고 있으므로 열거는 편의일 뿐이다. reason은 "".
      source `ref`      참조가 풀렸다 → basis = resolver가 준 집합 **그대로**.
                        🔴 **원과 교집합하지 않는다.** 교집합은 보수적으로 보이지만 템플릿이
                        유효라고 선언한 다이를 조용히 떨어뜨린다 — 그게 이 라운드가 없애려는
                        결함이다.
      source `refused`  선언은 있는데 풀지 못했다 → basis None, reason 비지 않음.
                        🔴 **원으로 되돌아가지 않는다.** 조용한 폴백은 틀린 답을 맞은 답과
                        구별할 수 없게 만든다.

    `resolver`: `ref({"table","map_id"})`를 받아 셀 집합(또는 `resolve_valid_die_set`의
    반환 dict, 또는 풀지 못했으면 None)을 주는 콜러블. 좌표계는 **resolver가 책임진다** —
    호출자의 좌표계로 이미 옮겨진 집합을 준다는 뜻이다(원 분기가 프레임 인덱스를 주는 것과
    같은 공간이어야 두 근거가 한 자리에서 교체 가능하다).
    """
    ref, err = parse_valid_die_ref(meta, default_table=table)
    if err is not None:
        return {"basis": None, "source": SOURCE_REFUSED, "reason": err}
    if ref is None:
        return {"basis": circle_die_mask(meta), "source": SOURCE_CIRCLE, "reason": ""}
    # [1-a] 거절문은 **키와 원래 가리키던 테이블을 이름으로** 댄다. 고정 이후 실패의 가장
    # 흔한 원인이 "그 맵은 있는데 valid_die_ref에는 없다"이고, 그것은 오타와 수리가 다르다.
    note = valid_die_redirect_note(ref)
    if resolver is None:
        return {"basis": None, "source": SOURCE_REFUSED,
                "reason": (f"valid_die_ref '{VALID_DIE_TABLE} · {ref['map_id']}' 선언이 "
                           f"있으나 참조를 풀 해석기가 주어지지 않았다") + note}
    try:
        result = resolver(ref)
    except Exception as e:                       # noqa: BLE001 — 해석 실패는 거절이다
        return {"basis": None, "source": SOURCE_REFUSED,
                "reason": f"참조 해석 중 오류: [{type(e).__name__}] {e}" + note}
    basis, reason = _basis_from_resolver(result)
    if basis is None:
        return {"basis": None, "source": SOURCE_REFUSED,
                "reason": (reason or f"참조 맵 '{VALID_DIE_TABLE} · {ref['map_id']}'을 "
                                     f"해석하지 못했다") + note}
    return {"basis": basis, "source": SOURCE_REF, "reason": ""}


def _valid_die_refused(ref, status, detail):
    """거절 응답. **`cells` 키를 절대 싣지 않는다** — 소비자가 실수로라도 폴백 집합을
    읽을 수 없게 만드는 것이 규율 ③의 구조적 보장이다.

    [1-a] 모든 거절 경로가 지나는 **한 자리**이므로 여기서 두 가지를 한다:
      ① 선언이 원래 다른 테이블을 가리켰으면 그 사실을 사유에 덧붙인다
         (`valid_die_redirect_note`) — 거절 문구를 만드는 자리마다 다시 쓰면 하나가 빠진다.
      ② **이름을 대서** 로그에 남긴다. 빈 마스크는 데이터처럼 보이는 거짓말이고, 그 거짓말은
         조용해서 위험하다 — 화면에는 개별로 조용하되 로그에는 키·고정 테이블·선언 테이블이
         이름으로 남아 집계로 셀 수 있어야 한다.
    """
    note = valid_die_redirect_note(ref)
    if note and detail and note not in detail:
        detail = f"{detail}{note}"
    r = dict(ref) if ref else None
    logger.warning(
        "[ValidDie] REFUSED status=%s table=%s key=%s declared_table=%s :: %s",
        status, (r or {}).get("table"), (r or {}).get("map_id"),
        (r or {}).get("declared_table"), detail)
    return {"declared": True, "ref": r,
            "status": status, "detail": detail, "align_applied": None}


def resolve_valid_die_set(db, cfg: dict, target_table: str, target_key: str,
                          target_meta: dict = None, cache: dict = None,
                          cell_cap: int = MAX_VALID_DIE_CELLS) -> dict:
    """선언 맵의 유효 다이 집합을 **선언 맵 자신의 프레임 좌표로** 해석한다.

    반환:
      {"declared": bool, "ref": {...}|None, "status": ..., "detail": str|None,
       "align_applied": {...}|None, "cells": frozenset[(x,y)], "count": int}
      — `cells`/`count`는 **status == "ok"일 때만** 존재한다.

    status 어휘(기존 강등 어휘를 그대로 쓴다):
      `not_declared`      선언 없음 — 실패가 아니다. 호출자는 종전 동작을 유지한다.
      `ok`                참조 맵이 답이다.
      `source_missing`    참조를 찾거나 해석할 수 없다(테이블·바인딩·키·선언 형태).
      `align_unavailable` 참조 맵을 이 맵의 프레임으로 옮길 근거가 없다(규격 미등록·치수 불일치).
      `ref_unavailable`   참조는 찾았으나 신뢰할 집합을 만들 수 없다 — 상한 초과, 또는
                          [INV-M4-6] 자기 참조·2단계 체인(`valid_die_chain_error`).
      `no_data`           참조 맵에 셀이 0건 — **"유효 다이가 없다"로 읽지 않는다.**
                          거의 언제나 "아직 적재되지 않았다"이고, 0건을 답으로 삼으면
                          사용자의 맵 전체를 무효로 만든다.

    [규격 미등록 참조를 identity로 붙이지 않는 이유] 선언은 메타 안에 살므로 **선언한
    맵의 프레임은 언제나 안다.** 참조 맵 메타만 없는 비대칭 상태에서 identity를 가정하면
    180° 돌아간 템플릿을 무보정으로 받아들이게 된다(`bonding_plan`의 canonical 프레임
    규율과 같은 판단 — 숫자/집합으로 나가는 답에는 "무보정"을 드러낼 자리가 없다).

    [스케일] 참조 1건당 셀 조회 **1회**. cache는 `(참조, 선언 맵 프레임 축)`으로 키를
    잡으므로 같은 참조를 같은 프레임에 쓰는 맵이 여럿이어도 해석은 한 번이다. 셀 단위
    조회로 떨어지는 경로는 없다.
    """
    if target_meta is None:
        target_meta = load_map_meta_cached(db, target_table, target_key, cache)

    ref, err = parse_valid_die_ref(target_meta, default_table=target_table)
    if err is not None:
        return _valid_die_refused(None, STATUS_SOURCE_MISSING, err)
    if ref is None:
        return {"declared": False, "ref": None, "status": STATUS_NOT_DECLARED,
                "detail": None, "align_applied": None}

    # [INV-M4-6] 자기 참조 판정은 **선언한 맵에 종속**이므로 캐시 키가 그것을 담아야 한다.
    # 값 자체(참조 맵의 셀)는 `(참조, 프레임)`에만 종속이라 여러 맵이 한 해석을 공유하는데,
    # 자기 참조 거절이 그 공유 항목에 실리면 같은 프레임에서 같은 맵을 참조한 **다른** 맵이
    # 하지도 않은 자기 참조로 거절된다. 같은 테이블일 때만 덧붙인다 — 정체성은 (테이블, 키)
    # 쌍이므로 테이블이 다르면 자기 참조가 성립할 수 없고, 교차 테이블 공유는 그대로 남는다.
    cache_key = ("vdref", ref["table"], ref["map_id"], frame_axes(target_meta))
    if (ref["table"] or target_table) == target_table:
        cache_key += (target_key,)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    out = _resolve_valid_die_uncached(
        db, cfg, ref, target_meta, cell_cap,
        home={"table": target_table, "map_id": target_key})

    if cache is not None:
        if len(cache) >= _VALID_DIE_CACHE_MAX:
            cache.clear()
        cache[cache_key] = out
    return out


def _resolve_valid_die_uncached(db, cfg, ref, target_meta, cell_cap, home=None):
    from database import models

    # [1-a] `ref["table"]`은 `parse_valid_die_ref`가 고정한 `VALID_DIE_TABLE`이다. 고정 이전에
    # 여기 있던 「대상 테이블을 알 수 없다」 가지는 **삭제됐다** — 고정된 대상은 알 수 없어질 수
    # 가 없으므로 그 가지는 도달할 수 없는 죽은 분기이고, 살아 있는 것처럼 보이는 죽은 분기는
    # 거짓말이다. 클라도 같은 이유로 같은 가지를 지웠다(`parseValidDieRef`).
    ref_table, ref_key = ref["table"], ref["map_id"]

    model = models.DYNAMIC_TABLES.get(ref_table)
    if model is None:
        return _valid_die_refused(
            ref, STATUS_SOURCE_MISSING,
            f"유효 다이 저장 테이블 '{ref_table}'이 등록되지 않았다 — 유효 다이 맵은 언제나 "
            f"이 테이블에서 읽으므로, 등록되지 않으면 **모든** valid_die_ref 선언이 거절된다 "
            f"(table_config에 제품 소유 테이블 '{ref_table}'을 설치하십시오)")

    # 바인딩 해석은 데이터 경로와 **같은 규칙**을 탄다(선언 > table_config 유도).
    # 두 번째 유도기를 만들지 않는다(§5.6-bis가 없앤 바로 그 중복).
    binding = resolve_binding(cfg, ref_table)
    if binding is None:
        return _valid_die_refused(
            ref, STATUS_SOURCE_MISSING,
            f"'{ref_table}'의 맵 좌표 바인딩을 유도할 수 없음 — table_config에 x/y 컬럼, "
            f"map_key_columns(또는 lot/slot), 값 컬럼 후보가 있어야 하며, 컬럼명이 관례와 "
            f"다르면 map_overlay_config.table_bindings에 선언해야 한다")

    x_col = getattr(model, binding.get("x", "x"), None)
    y_col = getattr(model, binding.get("y", "y"), None)
    if x_col is None or y_col is None:
        return _valid_die_refused(
            ref, STATUS_SOURCE_MISSING, f"'{ref_table}'에 좌표 컬럼이 없음")

    # [INV-M4-4] 선언 키를 **저장된 정체성으로** 캐노니컬화한다. 셀 필터는
    # `build_key_filters`가 컬럼 타입 캐스팅으로 살아남지만 `load_map_meta`는 map_id
    # 문자열 정확 일치라, 이것을 빼면 'LOT_01' 선언이 셀은 찾고 규격은 못 찾아
    # align_unavailable로 조용히 거절된다. 정규화 구현은 `canonical_key_value` 하나다.
    ref_key = canonical_map_key(ref_table, binding, ref_key)
    # [1-a] `declared_table`을 **함께 옮긴다.** 여기서 떨어뜨리면 이 아래 모든 거절이 선언이
    # 원래 무엇을 가리켰는지 말하지 못하고, 그 정보는 이 시점 이후 어디에도 남아 있지 않다.
    ref = {"table": ref_table, "map_id": ref_key,
           "declared_table": ref.get("declared_table")}

    filters = build_key_filters(model, binding, ref_key)
    if filters is None:
        return _valid_die_refused(
            ref, STATUS_SOURCE_MISSING, f"'{ref_table}'의 키 컬럼 바인딩 해석 실패")

    ref_meta = load_map_meta(db, ref_table, ref_key)

    # [INV-M4-6] 1홉 제한. 판정은 순수 술어 `valid_die_chain_error`가 하고 여기서는
    # **이미 로드한 메타를 넘겨줄 뿐**이다 — 참조 1건당 추가 조회 0회(셀 단위 경로 없음).
    # 자기 참조는 참조 맵 메타 유무와 무관하므로 `ref_meta is None` 판정보다 앞에 둔다:
    # A→A는 "규격 미등록"이 아니라 "자기 자신"이라고 말해야 고칠 데가 보인다.
    # home 키는 **참조 키와 같은 정준화**(`canonical_map_key`)를 거쳐야 'LOT_01 vs LOT_1'
    # 자기 참조를 놓치지 않는다. 테이블이 다르면 정체성 쌍이 이미 갈리므로 정준화하지 않는다
    # (바인딩이 참조 테이블의 것이라 그대로 쓸 수 없기도 하다).
    home = home if isinstance(home, dict) else {}
    home_table, home_key = home.get("table"), home.get("map_id")
    if home_table == ref_table and home_key is not None:
        home_key = canonical_map_key(ref_table, binding, home_key)
    chain_error = valid_die_chain_error(
        ref, ref_meta, {"table": home_table, "map_id": home_key})
    if chain_error:
        return _valid_die_refused(ref, STATUS_REF_UNAVAILABLE, chain_error)

    if ref_meta is None:
        return _valid_die_refused(
            ref, STATUS_ALIGN_UNAVAILABLE,
            f"이 유효 다이 맵을 찾을 수 없다 — 키 '{ref_key}'의 규격이 '{ref_table}' 이름으로 "
            f"wafer_map_metadata에 미등록. 선언한 맵의 프레임은 아는데 참조 맵의 프레임을 "
            f"몰라, 무보정으로 가정하면 회전·반전된 템플릿을 그대로 받아들이게 된다")

    try:
        transform, align, origin, note = resolve_map_transform(ref_meta, target_meta)
    except ValueError as ve:
        return _valid_die_refused(
            ref, STATUS_ALIGN_UNAVAILABLE,
            f"참조 맵 '{ref_table}/{ref_key}'을 이 맵의 프레임으로 옮길 수 없음: {ve}")

    try:
        rows = db.query(x_col, y_col).filter(*filters).limit(cell_cap + 1).all()
    except Exception as e:
        logger.warning("[ValidDie] ref cell query failed (%s/%s): %s",
                       ref_table, ref_key, e)
        return _valid_die_refused(
            ref, STATUS_SOURCE_MISSING, f"참조 맵 '{ref_table}/{ref_key}' 셀 조회 실패")

    if len(rows) > cell_cap:
        logger.warning("[ValidDie] %s/%s exceeds the cell cap (%d) — refused",
                       ref_table, ref_key, cell_cap)
        return _valid_die_refused(
            ref, STATUS_REF_UNAVAILABLE,
            f"참조 맵 '{ref_table}/{ref_key}'의 셀이 상한({cell_cap})을 초과 — "
            f"잘라낸 유효 다이 집합은 틀린 집합이므로 답하지 않는다")

    cells = set()
    for row in rows:
        rx, ry = row[0], row[1]
        if rx is None or ry is None:
            continue
        cells.add(transform(rx, ry) if transform else (int(rx), int(ry)))

    if not cells:
        return _valid_die_refused(
            ref, STATUS_NO_DATA,
            f"참조 맵 '{ref_table}/{ref_key}'에 셀이 없음 — '유효 다이 0개'가 아니라 "
            f"'아직 적재되지 않았다'로 읽는다(0건을 답으로 삼으면 이 맵 전체가 무효가 된다)")

    return {
        "declared": True,
        "ref": dict(ref),
        "status": STATUS_OK,
        "detail": None,
        "align_applied": align_applied_payload(
            align, origin, note,
            translation=_pure_translation(ref_meta, target_meta, origin)),
        "cells": frozenset(cells),
        "count": len(cells),
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
