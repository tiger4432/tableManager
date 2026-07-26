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

[유도 경로의 변환 산법 — 프레임 합성 (구 B3 한계의 근본 수정)]
유도 경로는 "상대 회전 + 단일 flip"을 **하나의** 변환기로 합성하지 않는다. 그 방식은
`cell_to_physical`의 back 반전 축이 프레임 자신의 회전에 따라 달라지기 때문에(90/270이면
행, 아니면 열) 두 프레임의 반전 축을 하나의 변환으로 표현할 수 없었고, 전수 대조 64조합 중
16개가 조용한 거울상 오답이었다(QA B3 — 당시엔 명시 거절로 막아 두었다).

현재는 **각 맵을 자기 메타로 물리 좌표에 사상한 뒤 타깃 프레임으로 역사상**한다:

    (x,y)_src ──src.cell_to_physical──▶ (xp,yp)_물리 ──dst.physical_to_cell──▶ (x,y)_dst

각 프레임의 반전 축·회전이 자기 메타로 각각 처리되므로 조합 폭발이 사라진다. 따라서 이전의
"면 반전 + 타깃 회전 90/270 거절" 가드는 **불필요해져 제거**했다(과잉 거절이었다).

[격자 치수 규약 — 물리 vs 프레임 (실사고 원인)]
`wafer_map_metadata.grid_cols/grid_rows`는 **물리(canonical) 치수**다. 셀에 저장된 x/y는
**프레임(visual) 좌표**이며 그 치수는 맵 자신의 회전이 90/270이면 물리의 스왑이다.
`bonding_plan.make_align_transform`은 `src_grid`로 **프레임 치수**를 받으므로, 메타 값을
그대로 넘기면 회전 90/270 맵에서 치수 불일치 오판이 난다(라이브 사고: `test`/AAA(rot 270,
29x25)를 `bonding_map`/aa123_a에 겹칠 때 "source 29x25 rotated 270 maps to 25x29, but
canonical grid is 29x25"로 **정상 조합이 align_unavailable로 거절**). `_frame_grid_of`가
메타 → 프레임 치수 변환을 담당하며, 선언(override) 경로도 이것을 쓴다.

[남은 한계] 두 맵의 `grid_start_x/y` 차이는 identity 경로에서 보정하지 않는다
(라이브는 전부 start=(1,1)). 유도 경로(프레임 합성)는 각 맵의 start를 정확히 반영한다.

[변환 어댑터] 선언(override) 경로는 `bonding_plan.make_align_transform` 재사용 — 순수 인덱스
변환만 사용하며 엔진 마스크/타원 fallback은 참여하지 않는다(QA 감사 F1·F2).

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


def _frame_grid_of(meta: dict | None) -> dict | None:
    """맵 **자기 프레임(visual) 격자 규격** — 셀 x/y가 실제로 사는 좌표계의 치수.

    맵 자신의 회전이 90/270이면 물리 치수의 스왑이다(`WaferMapCoordinateTransformer`의
    `visual_cols/visual_rows` 규약과 동일). `make_align_transform`이 `src_grid`/`dst_grid`로
    기대하는 것이 이 치수이며, 메타의 물리 치수를 그대로 넘기면 회전 맵에서 오판이 난다.
    """
    g = _grid_of(meta)
    if g is None:
        return None
    if _rotation_of(meta) in (90, 270):
        g = dict(g, cols=g["rows"], rows=g["cols"])
    return g


def _side_of(meta: dict | None) -> str:
    return str((meta or {}).get("side", "front") or "front")


def _y_invert_of(meta: dict | None) -> bool:
    return bool((meta or {}).get("grid_y_invert"))


PHYS_KEYS = ("phys_wafer_dia", "phys_chip_x", "phys_chip_y",
             "phys_offset_x", "phys_offset_y", "phys_edge_margin")


def _phys_signature(meta: dict | None):
    """웨이퍼 원 규격 서명. 하나라도 없으면 None(= 바운딩박스를 재현할 수 없다)."""
    m = meta or {}
    try:
        vals = tuple(float(m[k]) for k in PHYS_KEYS)
    except (KeyError, TypeError, ValueError):
        return None
    return vals


def frame_axes(meta: dict | None):
    """맵 프레임을 정의하는 **축 전부**:
    (회전, 면, y반전, start_x, start_y, cols, rows, phys 서명).

    오버레이 정렬의 지름길(identity 판정)은 **이 튜플이 완전히 같을 때만** 허용된다.
    한 축이라도 다른데 지름길을 타면 전 셀이 어긋난 좌표를 `status: ok`로 내보내게 된다
    (QA O3/B1/M4 — 조용한 오답의 전형).

    [M4] 격자 치수와 phys 규격까지 포함한다. 치수가 빠져 있으면 규격이 다른 두 맵이
    지름길로 통과해 버리고(변환 경로의 치수 검사를 우회), phys가 빠져 있으면 웨이퍼 원
    크롭(바운딩박스)이 다른 두 맵이 무보정으로 붙는다.
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
      - **phys 파라미터 부재** — 바운딩박스를 재현할 수 없으면 좌표를 보증할 수 없다
    """
    from utils.coordinate_transformer import WaferMapCoordinateTransformer

    s_phys, t_phys = _grid_of(source_meta), _grid_of(target_meta)
    if not s_phys or not t_phys:
        raise ValueError("frame transform requires both map grid metas")
    if (s_phys["cols"], s_phys["rows"]) != (t_phys["cols"], t_phys["rows"]):
        raise ValueError(
            f"physical grid dims differ: source {s_phys['cols']}x{s_phys['rows']} vs "
            f"target {t_phys['cols']}x{t_phys['rows']} — 같은 웨이퍼 규격이 아니다")
    if _phys_signature(source_meta) is None or _phys_signature(target_meta) is None:
        raise ValueError(
            "phys 규격(phys_wafer_dia/chip_x/chip_y/offset_x/offset_y/edge_margin) 미등록 "
            "— 셀 좌표의 기준인 웨이퍼 바운딩박스를 재현할 수 없어 정렬을 보증할 수 없다")

    src_tf = _frame_transformer(source_meta, s_phys)
    dst_tf = _frame_transformer(target_meta, t_phys)

    def to_target(x, y):
        return dst_tf.physical_to_visual(*src_tf.visual_to_physical(int(x), int(y)))

    return to_target


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
    return (bonding_plan.normalize_align({"rotation": rel_rot, "flip": flip}),
            ALIGN_ORIGIN_DERIVED, note)


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


# 값 컬럼 후보 (앞선 것 우선). 어느 것도 없으면 좌표·키가 아닌 첫 컬럼으로 폴백.
VAL_CANDIDATES = ("val", "value", "leg", "grade", "result", "code", "split", "doe")

# 레이어링/시스템 컬럼 — val 후보에서 제외한다
_SYSTEM_COLUMNS = frozenset({
    "row_id", "business_key_val", "created_at", "updated_at",
    "is_graph_synced", "needs_graph_rollback", "graph_synced_at",
})


def derive_table_binding(table: str) -> dict | None:
    """`table_config` 선언에서 맵 좌표 바인딩을 **자동 유도**한다. 불가하면 None.

    [왜 유도가 정본인가] `map_overlay_config.table_bindings`에 선언된 맵만 겹칠 수 있으면
    "모든 맵을 universal하게 겹쳐 본다"는 요구와 정면으로 어긋난다(신규 맵 테이블이 조용히
    실패한다 — 라이브 사고: `test` 미선언으로 "소스 맵을 찾을 수 없습니다"). 맵의 좌표계는
    이미 `table_config`가 선언하고 있으므로(`map_key_columns` + x/y 컬럼) 거기서 유도하고,
    config 선언은 **예외 보정용**(컬럼명이 관례와 다른 `dt_log`/`bonding_log` 등)으로만 둔다.

    - key_columns: `map_key_columns` 정본. 미선언이면 lot/slot 둘 다 있을 때만 관례 폴백.
    - x/y: 리터럴 `x`/`y` 컬럼. 없으면 유도 실패(관례 밖 이름은 선언으로 보정).
    - val: `VAL_CANDIDATES` 우선, 없으면 키·좌표·시스템이 아닌 첫 컬럼.
    """
    from database import crud

    tcfg = (crud.TABLE_CONFIG or {}).get(table)
    if not isinstance(tcfg, dict):
        return None
    types = tcfg.get("column_types") or {}
    if "x" not in types or "y" not in types:
        return None

    key_cols = tcfg.get("map_key_columns")
    if isinstance(key_cols, str):
        key_cols = [key_cols]
    if not (isinstance(key_cols, list) and key_cols):
        key_cols = ["lot", "slot"] if ("lot" in types and "slot" in types) else None
    if not key_cols:
        return None

    excluded = set(key_cols) | {"x", "y", tcfg.get("business_key")} | _SYSTEM_COLUMNS
    val = next((c for c in VAL_CANDIDATES if c in types and c not in excluded), None)
    if val is None:
        val = next((c for c in types if c not in excluded), None)

    return {"x": "x", "y": "y", "val": val, "key_columns": list(key_cols)}


def resolve_binding(cfg: dict, table: str) -> dict | None:
    """테이블의 좌표 컬럼 바인딩. **config 선언 > table_config 유도** 순. 둘 다 없으면 None.

    None은 "이 테이블은 맵으로 해석할 수 없다"는 뜻이며 호출자가 명시 실패로 표면화한다
    (관례 값으로 조용히 추측해 0건을 정상처럼 내보내지 않는다)."""
    bindings = (cfg.get("table_bindings") or {})
    b = bindings.get(table)
    if isinstance(b, dict) and b.get("columns"):
        return dict(b["columns"])
    return derive_table_binding(table)


def build_key_filters(model, binding: dict, map_key: str):
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

        binding = resolve_binding(cfg, s_table)
        if binding is None:
            entry["status"] = STATUS_SOURCE_MISSING
            entry["detail"] = (
                f"'{s_table}'의 맵 좌표 바인딩을 유도할 수 없음 — table_config에 x/y 컬럼과 "
                f"map_key_columns(또는 lot/slot)가 있어야 하며, 컬럼명이 관례와 다르면 "
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
        align, origin, note = resolve_align(cfg, s_table, source_meta, target_meta, eqp)

        transform = None
        try:
            if origin == ALIGN_ORIGIN_DERIVED:
                # [정본 경로] 두 메타로 프레임을 각각 물리에 사상해 합성한다.
                # ⚠️ `align`(표시용 요약)이 identity로 보여도 **반드시 합성한다** — 회전·면이
                # 같아도 y반전이나 start가 다르면 변환이 필요하고, 여기서 요약을 보고
                # 건너뛰면 정확히 QA O3의 조용한 오답이 된다.
                transform = make_frame_transform(source_meta, target_meta)
            elif align and not align.get("is_identity"):
                # [선언 override 경로] 사용자가 못 박은 변환 — 프레임 치수로 넘긴다
                # (메타의 물리 치수를 그대로 넘기면 회전 90/270 맵에서 오판난다).
                src_grid = _frame_grid_of(source_meta)
                if not src_grid:
                    entry["status"] = STATUS_ALIGN_UNAVAILABLE
                    entry["detail"] = f"'{s_table}' 격자 규격 미등록 — 변환을 계산할 수 없음"
                    entry["align_applied"] = align_applied_payload(align, origin, note)
                    overlays.append(entry)
                    continue
                transform = bonding_plan.make_align_transform(
                    align, src_grid, _frame_grid_of(target_meta))
        except ValueError as ve:
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
