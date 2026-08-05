"""맵 정렬 채점 — 후보 8개를 **한 번에** 채점해 한 payload로 낸다 (스펙 §0.2 층 ⑤·⑥·⑦).

[성격] 이 모듈은 **아무것도 쓰지 않는다.** 스펙 §0.2가 정한 대로 쓰는 층은 ⑧ 하나뿐이고
여기는 그 위가 아니라 아래다 — 후보를 세우고(⑤), 공통 바닥에 올려 대조하고(⑥), 이길
후보가 있는지 판정한다(⑦). 판정 결과를 저장하는 것은 이 모듈의 일이 아니다.

[결정 단위는 맵 하나가 아니라 `(dt_eqp, product)`다]
같은 설비·제품인데 웨이퍼끼리 선언이 어긋난다(실측: 한 단위 안에서 dt_map 메타가 네 프레임으로
갈린다). 그래서 맵 하나를 보고 정하면 같은 단위의 다른 맵이 그 결정을 부정한다. 단위 전체의
셀을 **하나의 바닥에 모아** 채점한다 — 스펙 §0.2 ⑥의 「쌍으로 만들지 말고 공통 공간에 올려라」가
이 뜻이다. 단위 선언의 정본은 `enrichment_rules.json`의 `eqp_product_frame_attribution`이며
`decision_key`가 곧 이 단위다(여기에 컬럼명을 하드코딩하지 않는다).

[🔴 전제 — 후보마다 메타를 통째로 만든다]
스펙 §2 「전제」가 이 모듈에 거는 유일한 강제 조건이다. bbox를 한 번 구해 놓고 그 위에 8개
변환을 얹으면 `_frame_phys_params`의 오프셋 부호 반전이 일어나지 않아 상쇄가 깨지고, 운영 행
`CORE_YINV`가 (2,−1)만큼 조용히 어긋난다. 그래서 후보는 **`source_meta_for_frame`으로 메타를
통째로 만들어** `make_frame_transform`(→ `_frame_transformer` → `_frame_phys_params`)을
그대로 통과시킨다. 이 모듈에 좌표 산식을 다시 쓰지 않는다 — 서버의 좌표 변환 구현은
`map_overlay` 하나다.

[🔴 바운딩박스 근거를 바꾸지 않는다]
`map_overlay._FRAME_TF_CACHE`와 `_CIRCLE_MASK_CACHE`의 키는 `frame_axes(meta)`이고 그 튜플에는
**bbox 근거가 들어 있지 않다.** 이 모듈이 근거를 바꿔 가며 변환기를 만들면 다음 호출자가 앞
호출자의 bbox를 받는다. 그래서 여기서는 근거를 **바꾸지 않는다** — 기준 맵의 프레임을 바닥으로
쓰고, 근거를 인자로 만드는 일은 그 튜플을 먼저 늘린 뒤의 작업이다(스펙 §0.3 순서 2).

[백분율을 만들지 않는다]
후보 지표는 전부 **개수**다. 커버리지 백분율은 실측에서 순위를 뒤집었다(스펙 §3). 분모가
후보마다 다른 값을 비율로 만들면 적게 놓인 후보가 높은 비율을 얻는다. 비율이 필요하면 화면이
두 개수로 만들고, 그 책임을 화면에 남긴다.
"""
import logging
import time

import map_overlay
from dt_map_derivation import parse_frame, source_meta_for_frame

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 후보 어휘 — **철자는 `dt_map_derivation.parse_frame` 하나뿐이다**
# ---------------------------------------------------------------------------
# 8개를 여기서 문자열 리터럴로 나열하면 그 목록이 두 번째 철자가 된다. 대신 축에서 조립하고
# **기존 수용기에 통과시켜** 만든다 — 수용기가 거부하는 철자는 후보가 될 수 없다.
FRAME_ROTATIONS = (0, 90, 180, 270)
FRAME_SIDES = ("front", "back")


def frame_text(rotation: int, side: str) -> str:
    """(회전, 면) → 프레임 문자열. `parse_frame`의 역이다."""
    return "rot%d_%s" % (int(rotation) % 360, side)


def candidate_frames() -> tuple:
    """탐색 공간 전체. 스펙 §2 실측: 운영 경로에서 **정확히 8개**이고 `grid_y_invert`는
    후보 축이 아니다(상쇄되어 별칭이 된다). 단, 그 상쇄는 위 「전제」를 지킬 때만 성립한다."""
    out = []
    for rot in FRAME_ROTATIONS:
        for side in FRAME_SIDES:
            text = frame_text(rot, side)
            if parse_frame(text) is None:          # 수용기가 정본이다
                raise ValueError("candidate frame '%s' is not accepted by parse_frame" % text)
            out.append(text)
    return tuple(out)


CANDIDATE_FRAMES = candidate_frames()

# ---------------------------------------------------------------------------
# 상한 — 응답 크기와 계산량 둘 다에 걸린다 (조용한 절단 금지, 응답에 명시한다)
# ---------------------------------------------------------------------------
MAX_SCORED_CELLS = 20_000      # 단위 전체에서 채점에 쓰는 소스 셀 상한
MAX_PAYLOAD_CELLS = 20_000     # 응답에 실어 보내는 셀 상한 (기준·소스 각각)
SHIFT_WINDOW = 3               # 후보별 정수 시프트 탐색 반경 (±N, 즉 (2N+1)^2 후보)

#: 맵 키 구분자 — `compose_map_id`가 잇고 `map_overlay.map_key_parts`가 자르는 그 글자.
#: 두 자리가 같은 글자를 써야 왕복이 성립하므로 철자는 여기 하나다.
_MAP_KEY_SEPARATOR = "_"

# ---------------------------------------------------------------------------
# 상태 어휘 — 닫혀 있다
# ---------------------------------------------------------------------------
STATE_SCORED = "scored"                # 후보를 채점했고 이긴 후보가 있다
STATE_NO_WINNER = "no_winner"          # 채점은 됐는데 이긴 후보가 없다 (동점 또는 판별 0)
STATE_NOT_SCORABLE = "not_scorable"    # 채점 자체가 성립하지 않는다 (기준 부재·소스 전멸)
STATE_COMPUTING = "computing"          # 예약 — 이 엔드포인트는 동기라 발화하지 않는다

REFERENCE_RESOLVED = "resolved"
REFERENCE_ABSENT = "absent"            # 기준 선언이 없다 (**흔한 경우다**)
REFERENCE_REFUSED = "refused"          # 선언은 있는데 풀리지 않는다

# 기준이 **무엇을 싣고 있는가**. 클라가 모양을 보고 추론하면 안 되는 값이다 — 서버는 값 컬럼을
# 바인딩에서 알고 있고 클라는 셀 배열의 생김새로 짐작할 뿐이다.
#
# 🔴 이 구분이 「승자 없음」의 **사유를 가른다**: 점유만 있는 기준에서 8후보가 같은 다이를
#    차지하면 그것은 진짜 동점이 아니라 **기준이 애초에 구별할 수 없었던 것**이다(실측
#    `core_defect_map LOT-A/05`: 점유는 8후보 동일, 값으로는 374다이 차이). 두 경우에
#    조작자가 할 일이 다르다 — 「기준 발자국이 대칭」과 「기준에 값이 없음」은 다른 수리다.
REFERENCE_KIND_NONE = "none"           # 기준 없음
REFERENCE_KIND_OCCUPANCY = "occupancy" # 점유만 (어느 다이가 있는가)
REFERENCE_KIND_VALUES = "values"       # 점유 + 값

# 제외 사유 — 코드와 사람 말을 한 자리에서 짝지어 둔다. 화면이 사유 문장을 만들지 않는다
# (`/admin/config/resolve` 규율: 사람이 읽을 문장은 전부 서버가 만든다).
EXCLUDE_META_MISSING = "meta_missing"
EXCLUDE_GEOMETRY_REFUSED = "geometry_refused"
EXCLUDE_NO_CELLS = "no_cells"

# 표찰이지 문장이 아니다(§compose_refusal).
_EXCLUDE_TEXT = {
    EXCLUDE_META_MISSING: "맵 규격 미등록 (wafer_map_metadata)",
    EXCLUDE_GEOMETRY_REFUSED: "칩 규격 미선언 - 좌표 변환 불가",
    EXCLUDE_NO_CELLS: "좌표 0건",
}

# 기준(floor) 거절 사유 코드 — **「제안되지 않았다」에는 언제나 이유가 붙는다.**
#
# 🔴 이유 없는 「없음」이 제품 소유자를 수리가 아니라 사람에게 보냈다: 양쪽 반(셀 + 메타 행)이
#    다 있는 바닥이 목록에 없는데, 응답이 말해 준 것은 거절 **개수**와 익명의 예시 문장 하나
#    뿐이었다. 어느 맵이 왜 빠졌는지가 응답에 없으면 화면은 「고장」과 「그 맵은 바닥이 될 수
#    없음」을 구별할 방법이 없다.
#
# 세 개는 `EXCLUDE_*`와 **같은 문자열**이다 — 같은 사실에 두 철자를 두지 않는다(상세 화면의
# 제외 어휘와 목록의 거절 어휘가 갈리면 같은 원인이 두 이름으로 보고된다).
REF_REFUSAL_META_MISSING = EXCLUDE_META_MISSING          # 메타 **행**이 없다
REF_REFUSAL_META_UNREADABLE = "meta_unreadable"          # 행은 있는데 grid_metadata가 비었/깨졌다
REF_REFUSAL_GEOMETRY = EXCLUDE_GEOMETRY_REFUSED          # auto_registered · 키 부재 · 수가 아님
REF_REFUSAL_BINDING = "binding_unresolved"               # 좌표/값 컬럼 바인딩을 유도 못 함
REF_REFUSAL_NO_CELLS = EXCLUDE_NO_CELLS                  # 그 키에 행이 없다
REF_REFUSAL_COORDS_UNREADABLE = "coords_unreadable"      # 행은 있는데 x·y가 수가 아니다
REF_REFUSAL_KEY_UNSPLIT = "key_unsplit"                  # 맵 키가 키 컬럼 수만큼 쪼개지지 않는다
REF_REFUSAL_KEY_AMBIGUOUS = "key_ambiguous"              # 구분자가 더 많아 어디서 잘릴지가 갈린다
REF_REFUSAL_SPEC_MALFORMED = "spec_malformed"            # 명시 지정이 '테이블:맵ID'가 아니다
REF_REFUSAL_DECLARATION = "declaration_unreadable"       # valid_die_ref 선언 자체를 못 읽는다


class _Excluded:
    """제외를 **사유별 집계**로 모은다. 행마다 한 줄씩 내보내면 화면이 소음에 묻히고,
    사유를 빼고 개수만 내보내면 무엇을 고쳐야 하는지가 사라진다."""

    def __init__(self):
        self._n = {}
        self._sample = {}

    def add(self, reason: str, map_id: str, detail: str = None):
        self._n[reason] = self._n.get(reason, 0) + 1
        if reason not in self._sample:
            self._sample[reason] = {"map_id": map_id, "detail": detail}

    def total(self) -> int:
        return sum(self._n.values())

    def as_list(self) -> list:
        out = []
        for reason, n in sorted(self._n.items(), key=lambda kv: -kv[1]):
            s = self._sample.get(reason) or {}
            out.append({"reason_code": reason,
                        "reason": _EXCLUDE_TEXT.get(reason, reason),
                        "count": n,
                        "example_map_id": s.get("map_id"),
                        "example_detail": s.get("detail")})
        return out


# ---------------------------------------------------------------------------
# 「지금 적혀 있는 프레임」 — **선언이지 확정이 아니다**
# ---------------------------------------------------------------------------
# 화면의 `현재` 배지가 읽는 값이다. 이름을 조심해서 고른다: `declaration`은 **누가 적어 둔
# 것**이고 `confirmation`은 **누가 결정한 것**이다. 이 payload는 읽기 전용이라 후자를 실을 수
# 없고, 두 낱말이 섞이면 「적혀 있으니 정해진 것」이 되어 아무도 고른 적 없는 프레임이 결정으로
# 승격된다.
#
# 🔴 그리고 적혀 있다고 선언인 것도 아니다. `rotation:0, side:"front"`은 등록기와 스크립트가
#    **아무도 보지 않고** 써 넣는 값이라, 그대로 배지를 달면 「그럴듯한 기본값이 선언을
#    사칭」한다(I4). 그래서 프레임 문자열과 **그 출처 토큰**을 함께 낸다. 출처가 `declared`가
#    아닌 맵은 집계에서 빼고 `unattested_maps`로 따로 센다 — 0으로 접으면 그 맵들이 사라진다.
def declared_frame_of(meta: dict | None) -> dict:
    """맵 메타가 **적어 둔** 프레임과 그 출처. `{frame, source}`.

    `source`는 `map_overlay.orientation_declaration`의 토큰을 그대로 쓴다(어휘는 하나다).
    회전과 면이 **둘 다** `declared`일 때만 `declared`이고, 아니면 둘 중 약한 쪽을 낸다 —
    합쳐진 값은 가장 약한 기여자를 따라간다(스펙 §0.2 ⑨).
    """
    if not meta:
        return {"frame": None, "source": map_overlay.GEOMETRY_ABSENT,
                "axes": {"rotation": map_overlay.GEOMETRY_ABSENT,
                         "side": map_overlay.GEOMETRY_ABSENT}}
    d = map_overlay.orientation_declaration(meta)
    rot, side = d["rotation"], d["side"]
    frame = frame_text(rot["value"], side["value"])
    # 🔴 축별 출처도 같이 낸다 — 합친 토큰만 내면 **절반의 선언이 통째로 사라진다.** 실측
    #    (2026-08-05, DT-EQP-01/PRD-A): 40개 맵이 `rot90_front`을 적어 두었고 회전 90은
    #    아무 기본 경로도 만들지 않는 값이라 선언인데, `side:"front"`은 기본값이라 아니다.
    #    합친 답은 정직하게 「선언 아님」이지만, 그것만 내면 화면은 회전 선언까지 못 쓴다 —
    #    회전 하나만으로도 8후보가 2후보로 줄어든다. 판정은 합친 값이 하고, 화면이 쓸 재료는
    #    축별로 남긴다.
    axes = {"rotation": rot["source"], "side": side["source"]}
    if rot["source"] == side["source"] == map_overlay.GEOMETRY_DECLARED:
        return {"frame": frame, "source": map_overlay.GEOMETRY_DECLARED, "axes": axes}
    weakest = next(t["source"] for t in (rot, side)
                   if t["source"] != map_overlay.GEOMETRY_DECLARED)
    return {"frame": frame, "source": weakest, "axes": axes}


# ---------------------------------------------------------------------------
# 시프트 풀이 + 채점
# ---------------------------------------------------------------------------
# 스펙 §2.1: 공간은 **이산 8 + 후보별 해석 가능한 평행이동**이다. 평행이동은 탐색 대상이
# 아니라 후보마다 겹침을 최대화하도록 **푸는** 값이다.
_KEY_STRIDE = 1 << 20          # (x, y) → 단일 정수. y가 음수여도 되도록 편향을 준다
_KEY_BIAS = 1 << 19


def _encode(pairs):
    import numpy as np
    if not pairs:
        return np.empty(0, dtype="int64")
    arr = np.asarray(pairs, dtype="int64")
    return (arr[:, 0] + _KEY_BIAS) * _KEY_STRIDE + (arr[:, 1] + _KEY_BIAS)


def _solve_shift(placed_keys, ref_sorted, window: int):
    """후보 하나의 정수 시프트를 푼다 → (dx, dy, 일치수, 후보별 일치 벡터).

    겹침을 최대화하는 (dx, dy)를 ±window 안에서 고른다. 동점이면 **원점에 가까운 쪽**을
    고른다 — 임의로 고르면 같은 입력이 실행마다 다른 답을 내고, 그 비재현성은 채점보다
    먼저 신뢰를 깎는다.
    """
    import numpy as np
    best = (0, 0, -1)
    if placed_keys.size == 0 or ref_sorted.size == 0:
        return 0, 0, 0
    for dy in range(-window, window + 1):
        for dx in range(-window, window + 1):
            shifted = placed_keys + dx * _KEY_STRIDE + dy
            idx = np.searchsorted(ref_sorted, shifted)
            idx[idx >= ref_sorted.size] = 0
            hit = int(np.count_nonzero(ref_sorted[idx] == shifted))
            if hit > best[2] or (hit == best[2]
                                 and abs(dx) + abs(dy) < abs(best[0]) + abs(best[1])):
                best = (dx, dy, hit)
    return best


def _membership(placed_keys, ref_sorted, dx, dy):
    """이 후보가 푼 시프트에서 셀마다 「기준 위에 놓였는가」 진리값 벡터."""
    import numpy as np
    if placed_keys.size == 0 or ref_sorted.size == 0:
        import numpy as _np
        return _np.zeros(placed_keys.size, dtype=bool)
    shifted = placed_keys + dx * _KEY_STRIDE + dy
    idx = np.searchsorted(ref_sorted, shifted)
    idx[idx >= ref_sorted.size] = 0
    return ref_sorted[idx] == shifted


def score_candidates(source_maps: list, reference_cells, reference_meta: dict,
                     shift_window: int = SHIFT_WINDOW, cell_cap: int = MAX_SCORED_CELLS,
                     reference_values=None, thresholds: dict = None):
    """후보 8개를 **한 호출로** 채점한다. DB를 모른다 — 셀과 메타만 받는다.

    `source_maps`: `[{"map_id": str, "meta": dict, "cells": [(x, y), ...],
                      "values": [v, ...]}]` — `values`는 있으면 `cells`와 **같은 순서**다.
    `reference_cells`: 기준(공통 바닥)의 점유 좌표 집합 — 기준 맵 자신의 프레임 좌표다.
    `reference_values`: 기준 셀의 값. `reference_cells`와 같은 순서. 없으면 점유 채점만.
    `thresholds`: `{min_margin_dies, min_discriminating_dies}`. **기본값이 없다** — 선언되지
        않으면 순위를 내지 않는다(`_rule_on`).

    반환: `(candidates, excluded, ruling, stats)`.

    [지표가 둘이고, 하나가 다른 하나를 대체하지 않는다]
    **점유**(agreement)는 기준이 값을 싣지 않을 때의 정직한 답이다. 그러나 기준 발자국이
    원이면 점유는 평평한 정도가 아니라 **아무 정보도 없다** — 원은 여덟 프레임 모두에
    불변이므로 어느 프레임으로 읽어도 같은 다이를 덮는다(스펙 §1). 그때 후보 사이에 벌어지는
    격차는 신호가 아니라 표본 잡음이고, 잡음 위에 세운 1등은 거절보다 나쁘다.
    **값 일치**(value_agreement)가 실측으로 작동한 지표다 — `core_defect_map LOT-A/05`에서
    점유는 8후보가 **같은 다이를 차지**해 8자 동점이었고, 값이 진실 `rot270_back`을
    1028/1028로, 선언된 후보를 640으로 갈라 **374다이** 차이를 냈다.
    둘 다 계산해 둘 다 싣고, 순위에 쓰는 쪽은 `reference.kind`가 정한다.

    [판별(discriminating)이 무엇을 세는가 — 이 정의가 §1 정리의 직접 구현이다]
    스펙 §1: 원은 여덟 프레임 모두에 불변이므로 아무것도 기여하지 못하고, **점유 부분집합만이
    동점을 깬다.** 그래서 셀 하나가 후보를 구별하는 것은 그 셀의 「기준 위에 있나」 답이
    후보마다 **같지 않을 때**뿐이다. 후보 k의 판별수 = 그 후보가 맞힌 셀 중 **후보들 사이에서
    답이 갈리는** 셀의 수다. 일치수가 커도 판별수가 0이면 그 점수는 아무 후보도 배제하지
    못한다 — 그때 순위를 매기면 틀린 것을 맞다고 말하는 것이다(§0.2 ⑦). 값 지표도 같은
    정의를 자기 축에서 갖는다(`value_discriminating`).
    """
    import numpy as np
    t0 = time.monotonic()
    excluded = _Excluded()

    ref_pairs = sorted(reference_cells or ())
    ref_keys = _encode(ref_pairs)
    ref_sorted = np.unique(ref_keys)
    # 기준 값을 **좌표로** 찾을 수 있게 해 둔다. 같은 좌표가 두 번 오면 먼저 온 것을 남긴다 —
    # 임의로 고르면 같은 입력이 실행마다 다른 답을 낸다.
    ref_value_at = {}
    if reference_values:
        by_pair = {}
        for (xy, v) in zip(reference_cells or (), reference_values):
            by_pair.setdefault(tuple(xy), v)
        for i, pair in enumerate(ref_pairs):
            ref_value_at.setdefault(int(ref_keys[i]), by_pair.get(tuple(pair)))

    # [1] 기하 거절은 **후보와 무관하다** — 회전·면은 `geometry_declaration`을 바꾸지 않는다.
    #     그래서 후보 루프 밖에서 한 번만 판정한다(8배 비용을 치를 이유가 없다).
    usable = []
    for sm in source_maps:
        meta, mid = sm.get("meta"), sm.get("map_id")
        if not meta:
            excluded.add(EXCLUDE_META_MISSING, mid)
            continue
        if not sm.get("cells"):
            excluded.add(EXCLUDE_NO_CELLS, mid)
            continue
        why = map_overlay.geometry_refusal(meta)
        if why is not None:
            excluded.add(EXCLUDE_GEOMETRY_REFUSED, mid, why)
            continue
        usable.append(sm)

    scored_cells = 0
    truncated = False
    for sm in usable:
        room = cell_cap - scored_cells
        if room <= 0:
            truncated = True
            sm["_use"] = []
            continue
        if len(sm["cells"]) > room:
            truncated = True
            sm["_use"] = list(sm["cells"])[:room]
        else:
            sm["_use"] = list(sm["cells"])
        # 값은 좌표와 **같은 길이로 같이 잘린다**. 따로 자르면 절단 이후의 셀이 옆 셀의
        # 값을 받고, 그 오답은 개수로 안 잡힌다.
        vs = sm.get("values") or []
        sm["_use_values"] = [(vs[i] if i < len(vs) else None)
                             for i in range(len(sm["_use"]))]
        scored_cells += len(sm["_use"])

    # [2] 후보마다 **메타를 통째로 만들어** 변환한다 (모듈 상단 전제).
    per_candidate = []
    source_values = None
    for frame in CANDIDATE_FRAMES:
        placed = []
        vals = []
        failed = None
        for sm in usable:
            if not sm.get("_use"):
                continue
            src_meta = source_meta_for_frame(sm["meta"], frame)
            if src_meta is None:
                failed = "프레임 '%s'을 이 맵의 규격에 적용할 수 없습니다" % frame
                break
            try:
                tf = map_overlay.make_frame_transform(src_meta, reference_meta)
            except ValueError as e:
                failed = str(e)
                break
            for i, (x, y) in enumerate(sm["_use"]):
                placed.append(tf(x, y))
                vals.append(sm["_use_values"][i])
        if failed is not None:
            per_candidate.append({"frame": frame, "keys": None, "reason": failed})
            continue
        # 소스 값은 후보마다 **같은 순서의 같은 셀**이다(좌표만 움직인다). 그래서 한 번만
        # 붙잡아 둔다 — 후보마다 다시 만들면 그 사본들이 갈릴 수 있고, 갈리면 i번째가 서로
        # 다른 셀을 가리키게 된다.
        if source_values is None:
            source_values = vals
        per_candidate.append({"frame": frame, "keys": _encode(placed), "reason": None})

    # [3] 후보별 시프트를 풀고 셀별 진리값을 모은다.
    for c in per_candidate:
        if c["keys"] is None:
            c.update(dx=None, dy=None, agreement=0, member=None)
            continue
        dx, dy, hit = _solve_shift(c["keys"], ref_sorted, shift_window)
        c.update(dx=dx, dy=dy, agreement=int(hit),
                 member=_membership(c["keys"], ref_sorted, dx, dy))

    # [3b] 값 일치: 이 후보가 앉힌 자리의 **기준 값과 소스 값이 같은가**, 셀마다.
    #      기준이나 소스에 값이 없으면 **None이지 0이 아니다.** 0으로 내보내면 「값으로 재
    #      보았고 하나도 안 맞았다」가 되어 「값으로 잴 수 없었다」의 정반대를 말한다.
    scorable_values = bool(ref_value_at) and bool(source_values) and \
        any(v is not None for v in source_values)
    for c in per_candidate:
        if c["keys"] is None or not scorable_values:
            c["value_member"] = None
            continue
        shifted = c["keys"] + c["dx"] * _KEY_STRIDE + c["dy"]
        hits = np.zeros(c["keys"].size, dtype=bool)
        member = c["member"]
        for i in np.flatnonzero(member):
            rv = ref_value_at.get(int(shifted[i]))
            sv = source_values[i] if i < len(source_values) else None
            hits[i] = rv is not None and sv is not None and str(rv) == str(sv)
        c["value_member"] = hits

    # [4] 판별: 셀마다 후보들의 답이 갈리는가. 길이가 같은 후보들끼리만 비교할 수 있고,
    #     실제로 같다 — 같은 소스 셀 목록을 같은 순서로 놓았으므로 i번째가 같은 셀이다.
    #     값 축도 **자기 축에서** 같은 정의를 갖는다: 값이 갈리는 셀만이 값으로 후보를 가른다.
    def _varies(field):
        alive = [c for c in per_candidate if c.get(field) is not None]
        if not alive:
            return None
        n = alive[0][field].size
        if not n or not all(c[field].size == n for c in alive):
            return None
        stack = np.vstack([c[field] for c in alive])
        return stack.any(axis=0) & ~stack.all(axis=0)

    varies = _varies("member")
    value_varies = _varies("value_member")
    for c in per_candidate:
        if c["member"] is None or varies is None:
            c["discriminating"] = 0
        else:
            c["discriminating"] = int(np.count_nonzero(c["member"] & varies))
        if c.get("value_member") is None:
            c["value_agreement"] = None
            c["value_discriminating"] = None
        else:
            c["value_agreement"] = int(np.count_nonzero(c["value_member"]))
            c["value_discriminating"] = (
                0 if value_varies is None
                else int(np.count_nonzero(c["value_member"] & value_varies)))

    # [5] 순위와 판정. **개수만** 낸다 — 백분율을 만들지 않는다(모듈 상단).
    agrees = [c["agreement"] for c in per_candidate]
    vagrees = [c["value_agreement"] for c in per_candidate]
    out = []
    for i0, c in enumerate(per_candidate):
        others = [a for i, a in enumerate(agrees) if i != i0]
        runner = max(others) if others else 0
        v_others = [a for i, a in enumerate(vagrees) if i != i0 and a is not None]
        v_runner = max(v_others) if v_others else 0
        rot_side = parse_frame(c["frame"])
        out.append({
            "frame": c["frame"],
            "rotation": rot_side[0], "side": rot_side[1],
            "state": STATE_NOT_SCORABLE if c["keys"] is None else STATE_SCORED,
            "shift": None if c["dx"] is None else {"dx": c["dx"], "dy": c["dy"]},
            "agreement": c["agreement"],
            "discriminating": c["discriminating"],
            # 값 지표는 **점유를 대체하지 않는다.** 기준이 값을 안 실으면 점유가 정직한 답이고,
            # 그때 이 셋은 null이다(0이 아니다 — §[3b]).
            "value_agreement": c["value_agreement"],
            "value_discriminating": c["value_discriminating"],
            "value_margin": (None if c["value_agreement"] is None
                             else int(c["value_agreement"] - v_runner)),
            "placed": 0 if c["keys"] is None else int(c["keys"].size),
            "margin": None if c["keys"] is None else int(c["agreement"] - runner),
            "reason": c["reason"],
        })

    metric = METRIC_VALUES if scorable_values else METRIC_OCCUPANCY
    ruling = _rule_on(out, thresholds, metric)
    stats = {"scored_cells": scored_cells, "truncated": truncated,
             "cell_cap": cell_cap, "shift_window": shift_window,
             "reference_cells": int(ref_sorted.size),
             "reference_values": len(ref_value_at),
             "source_maps_usable": len(usable),
             "elapsed_ms": (time.monotonic() - t0) * 1000.0}
    return out, excluded, ruling, stats


METRIC_OCCUPANCY = "occupancy"
METRIC_VALUES = "values"

#: 판정 문턱. **코드에 기본값을 두지 않는다.** 여기 숫자를 하나 적으면 그것이 선언을 사칭하는
#: 그럴듯한 기본값이고(I4), 그 사칭의 대가가 정확히 이 라운드가 닫고 있는 실패다 —
#: 미선언을 0으로 접으면 「구별 못 함」이 「자신 있는 1등」이 된다(`Number(null) === 0`이
#: 이 프로젝트를 세 번 물었다). 선언이 없으면 **순위를 내지 않는다.**
THRESHOLD_KEYS = ("min_margin_dies", "min_discriminating_dies")


def load_alignment_thresholds(cfg: dict) -> dict:
    """선언된 문턱만. 없는 키는 **0이 아니라 없는 키로** 나간다.

    읽히지 않는 선언(수가 아닌 값)도 선언이 아니다 — 조용히 0으로 접으면 오타 하나가
    「항상 순위를 낸다」로 바뀐다.
    """
    raw = (cfg or {}).get("alignment") or {}
    out = {}
    for k in THRESHOLD_KEYS:
        v = raw.get(k)
        if v is None:
            continue
        try:
            out[k] = int(v)
        except (TypeError, ValueError):
            logger.warning("[MapAlignment] threshold '%s' is not a number, ignored: %r", k, v)
    return out


def _rule_on(candidates: list, thresholds: dict = None,
             metric: str = METRIC_OCCUPANCY) -> dict:
    """이길 후보가 있는가 — 없으면 **없다고 말한다**(스펙 §0.2 ⑦: 억지 1등 금지).

    이기려면 넷 다 필요하다: 단독 최고 · 판별수 > 0 · 판별수 ≥ 선언된 문턱 · 격차 ≥ 선언된
    문턱. 셋째·넷째가 안전망이고 **config이지 코드가 아니다.**

    🔴 `metric`이 순위 축을 정한다. 기준이 값을 실으면 값으로, 아니면 점유로 매긴다.
       점유는 기준 발자국이 원일 때 **아무 방위 정보도 싣지 않고**(스펙 §1), 그때 벌어지는
       격차는 표본 잡음이다. 그래서 문턱은 잡음 위의 1등을 막는 자리이고, 선언이 없으면
       막을 방법이 없으므로 아예 순위를 내지 않는다.
    """
    live = [c for c in candidates if c["state"] == STATE_SCORED]
    if not live:
        return {"winner": None, "margin": None, "metric": metric,
                "reason_code": "no_candidate_scored"}

    a_key = "value_agreement" if metric == METRIC_VALUES else "agreement"
    d_key = "value_discriminating" if metric == METRIC_VALUES else "discriminating"
    m_key = "value_margin" if metric == METRIC_VALUES else "margin"
    scoreable = [c for c in live if c.get(a_key) is not None]
    if not scoreable:
        return {"winner": None, "margin": None, "metric": metric,
                "reason_code": "no_candidate_scored"}

    th = dict(thresholds or {})
    missing = [k for k in THRESHOLD_KEYS if th.get(k) is None]

    best = max(c[a_key] for c in scoreable)
    tops = [c for c in scoreable if c[a_key] == best]
    top = tops[0]
    base = {"metric": metric, "margin": top.get(m_key),
            "discriminating": top.get(d_key),
            "min_margin_dies": th.get("min_margin_dies"),
            "min_discriminating_dies": th.get("min_discriminating_dies")}

    if len(tops) > 1:
        return dict(base, winner=None, margin=0, reason_code="tie",
                    tied=[c["frame"] for c in tops])
    # 🔴 **구조적 사실을 문턱보다 먼저 말한다.** 동점과 판별 0은 문턱과 무관하게 참이고
    #    (§1 정리: 판별이 0이면 그 점수는 여덟 후보 모두에 똑같이 붙는다), 그 사실을
    #    「기준값 미선언」으로 덮으면 조작자가 config를 고치러 가서 아무것도 달라지지 않는다.
    if (top.get(d_key) or 0) <= 0:
        return dict(base, winner=None, reason_code="no_discrimination")
    if missing:
        return dict(base, winner=None, reason_code="no_thresholds", missing=missing)
    if (top.get(d_key) or 0) < th["min_discriminating_dies"]:
        return dict(base, winner=None, reason_code="too_few_discriminating")
    if top.get(m_key) is None or top[m_key] < max(1, th["min_margin_dies"]):
        return dict(base, winner=None, reason_code="margin_too_small")
    return dict(base, winner=top["frame"], reason_code=None)


# ---------------------------------------------------------------------------
# 거절문 — **서버가 만든다**
# ---------------------------------------------------------------------------
# `/admin/config/resolve`와 같은 규율이다: 클라이언트는 사유를 자기 규칙으로 유도하지 않고
# 서버가 만든 문장을 그대로 렌더한다. 클라가 문장을 만들기 시작하면 그것이 두 번째 판정
# 구현이 되고, 두 판정이 갈리는 날 화면은 멀쩡한 채 값만 틀린다.
# 문장이 아니라 **표찰**이다. 「축 - 없는 것」에서 멈춘다.
# 금지 어투: `~를 지지합니다` `~가 수행되었습니다` `~이 존재하지 않습니다` `~하시겠습니까`.
# 짧게 만들되 **사실은 안 버린다** — 줄일 것은 군더더기이지 정보가 아니다.
_RULING_TEXT = {
    "no_candidate_scored": "후보 채점 0건",
    "tie": "동점 - 판별 불가",
    "no_discrimination": "기준 발자국이 대칭 - 8프레임 구별 불가",
    "no_margin": "1-2위 격차 0 - 순위 없음",
    # 문턱은 **선언**이므로 미선언은 「0」이 아니라 「모름」이다. 문장이 그렇게 말한다.
    "no_thresholds": "판정 기준값 미선언 - 순위 없음",
    "too_few_discriminating": "판별 다이 부족 - 순위 없음",
    "margin_too_small": "1-2위 격차 부족 - 순위 없음",
}

# 🔴 목록(`build_alignment_worklist`)과 상세(`build_alignment_view`)가 **같은 사실에 같은
#    문장을 낸다.** 두 자리에 따로 적으면 그것이 두 번째 철자이고, 한쪽만 고쳐지는 날 같은
#    단위가 목록과 상세에서 다른 말을 한다. 그래서 낱말은 여기 하나뿐이다.
TEXT_REFERENCE_ABSENT = "기준 없음 - 유효 다이 맵 미지정"
TEXT_REFERENCE_REFUSED = "기준 해석 실패"


def compose_refusal(state: str, reference: dict, excluded: _Excluded,
                    ruling: dict, source_map_count: int, candidates: list = None) -> str:
    """사람이 읽을 한 문장. 답이 있으면 None.

    무엇이 없어서 답이 없는지를 **이름으로** 댄다 — 조작자에게 필요한 유일한 정보가
    「무엇을 고치면 되는가」이고, 빈 결과나 0점은 그 답을 주지 못한다.
    """
    if state == STATE_SCORED:
        return None
    if state == STATE_NOT_SCORABLE:
        if reference.get("state") == REFERENCE_ABSENT:
            return TEXT_REFERENCE_ABSENT
        if reference.get("state") == REFERENCE_REFUSED:
            return "%s - %s" % (TEXT_REFERENCE_REFUSED,
                                reference.get("reason") or "사유 미상")
        if source_map_count == 0:
            return "소스 맵 0건"
        parts = ["%s (%d)" % (e["reason"], e["count"]) for e in excluded.as_list()]
        if parts:
            return "소스 전량 제외 - " + " · ".join(parts)
        # 🔴 여기가 실측으로 드러난 자리다. 기준도 있고 소스도 남아 있는데 **후보가 전부
        #    변환에 실패한** 경우가 있다 — 기준 맵과 소스 맵의 격자 규격이 다르면
        #    `make_frame_transform`이 여덟 후보 모두를 거절한다. 그때 "채점할 좌표가 없다"고
        #    답하면 조작자는 데이터를 의심하며 엉뚱한 곳을 고친다. 실제 사유는 변환기가 이미
        #    문장으로 만들어 놓았으므로 **그것을 그대로 올린다**(두 번째 사유 문장을 짓지 않는다).
        why = next((c.get("reason") for c in (candidates or []) if c.get("reason")), None)
        if why:
            return "8후보 전부 변환 거절 - %s" % why
        return "소스 좌표 0건"
    if state == STATE_NO_WINNER:
        return _RULING_TEXT.get(ruling.get("reason_code"), "순위 근거 부족")
    return None


# ---------------------------------------------------------------------------
# DB 조립 — 여기서만 DB를 안다. 위의 채점기는 셀과 메타만 받는다.
# ---------------------------------------------------------------------------
# 소비자는 `client2/map_editor2.html`(`client2/src/map2/`)이다. 요청 한 번이 화면 하나에
# 필요한 전부를 낸다 — 후보 전환은 **클라 리페인트**여야 하고, 후보마다 왕복하면 조작 3회 /
# 30초 예산이 상호작용만으로 소진된다.

def _binding_of(cfg: dict, table: str):
    b = map_overlay.resolve_binding(cfg, table)
    if b is None:
        raise ValueError("테이블 '%s'의 맵 좌표 바인딩을 유도할 수 없습니다" % table)
    return b


# ---------------------------------------------------------------------------
# 좌표 삼중항 — **원시 단위**. 선언 바인딩은 그것을 채우는 프리셋이다
# ---------------------------------------------------------------------------
# 제품 소유자 지시(2026-08-05): 「가장 원시적인 단위로 일한다 — `CORE FRAME`이라는 **이름**이
# 아니라 `CORE_X`·`CORE_Y`·`C_BN`. 그 원시값을 받는 단일 상태 함수를 만들고, config로 몰고,
# **그 다음에** 그것을 덮어쓰는 프리셋 단축을 얹는다.」
#
# 🔴 그래서 관계가 뒤집힌다. 예전에는 `_binding_of(cfg, src_table)`이 **정본**이었고 조작자는
#    좌표 컬럼을 고를 수 없었다 — `dt_log`의 선언 바인딩이 `dt_x`/`dt_y`로 고정돼 있어서,
#    `map_table=core_wafer_map`으로 열면 **core 맵 ID 아래에 dt 좌표가 모였다.** 화면은
#    멀쩡하고 값만 틀리는 상태이고(I3), 클라에 컬럼 선택기를 붙이면 **아무것도 하지 않는
#    컨트롤**이 된다. 지금은 컬럼이 인자이고 선언 바인딩은 **제안**이다.
#
# 🔴 그리고 제안과 선택은 응답에서 구별된다. 둘을 같은 모양으로 내보내면 화면이 「누가
#    골랐다」와 「서버가 채워 넣었다」를 같게 그리고, 그 순간 기본값이 선언을 사칭한다(I4).
COLUMN_CHOSEN = "chosen"        # 조작자가 이름을 댔다
COLUMN_PROPOSED = "proposed"    # 선언 바인딩(프리셋)이 채웠다 — 고른 것이 아니다
COLUMN_ABSENT = "absent"        # 아무것도 대지 않았다

# 값 컬럼이 없는 것은 **결함이 아니라 다른 질문**이다. 값이 없으면 답할 수 있는 것은 점유뿐이고,
# 점유는 평평하다 — 실측 `core_defect_map LOT-A/05`에서 8후보가 **같은 다이를 차지**했고
# (점유로는 8자 동점) 값 일치가 **374다이 차이**로 갈랐다. 그래서 이 구별은 장식이 아니다.
_REFERENCE_KIND_STRENGTH = {REFERENCE_KIND_NONE: 0,
                            REFERENCE_KIND_OCCUPANCY: 1,
                            REFERENCE_KIND_VALUES: 2}

_VALUE_GUESS_REASON = ("값 컬럼 제안 없음 - 선언된 후보와 맞는 컬럼이 없어 추측만 가능합니다"
                       " (추측은 데이터 경로에 쓰지 않습니다)")


def resolve_source_columns(cfg: dict, table: str, model, x_col: str = None,
                           y_col: str = None, value_col: str = None) -> dict:
    """이 실행이 실제로 읽을 좌표 삼중항과 **그 값이 어디서 왔는가**.

    `x_col`/`y_col`/`value_col`이 오면 그것이 답이고, 안 오면 선언 바인딩이 **제안**한다.
    컬럼은 테이블의 **실제 스키마**에 대해 검증한다 — `params`를 규칙 자신의 `decision_key`에
    대해 검증하는 것과 같은 규율이고, 없는 컬럼은 조용한 0건이 아니라 거절이다.
    """
    proposal = map_overlay.resolve_binding_info(cfg, table)
    # [F2] 후보 밖 추측 값 컬럼은 데이터 경로에 나가지 않는다(`derive_table_binding` 규율).
    # 제안으로도 쓰지 않는다 — 제안은 조작자가 그대로 눌러 확정할 수 있는 값이어야 한다.
    guessed = bool(proposal) and proposal.get("source") == "fallback_guess"

    def _named(col, role):
        if getattr(model, col, None) is None:
            raise ValueError("테이블 '%s'에 컬럼 '%s'이 없습니다 - %s 좌표로 쓸 수 없습니다"
                             % (table, col, role))
        return col

    out = {}
    for role, chosen in (("x", x_col), ("y", y_col)):
        c = chosen.strip() if isinstance(chosen, str) else chosen
        if c:
            out[role] = {"column": _named(c, role), "origin": COLUMN_CHOSEN}
        elif proposal and proposal.get(role):
            out[role] = {"column": _named(proposal[role], role), "origin": COLUMN_PROPOSED}
        else:
            out[role] = {"column": None, "origin": COLUMN_ABSENT}

    # 🔴 세 가지를 말할 수 있어야 한다: **고른다** · **제안을 받는다** · **없이 간다**.
    #    생략(None)이 「제안해 달라」를 뜻하므로, 생략만으로는 셋째를 말할 수 없다 — 그러면
    #    선언이 값 컬럼을 가진 테이블(`dt_log`)에서 조작자는 점유 전용 실행을 요청할 방법이
    #    없고, 그 실행이야말로 「승자 없음」이 진짜 동점인지 기준이 못 가른 것인지를 재는
    #    자리다. 그래서 **빈 문자열이 명시적 「없음」**이다(`?value_col=`).
    v = value_col.strip() if isinstance(value_col, str) else value_col
    if isinstance(value_col, str) and not v:
        out["value"] = {"column": None, "origin": COLUMN_ABSENT,
                        "reason": "값 컬럼 없이 실행 - 점유만으로 대조합니다"}
    elif v:
        # 고른 것은 **엄격히** 검증한다 — 조작자가 이름을 댔는데 조용히 없는 것으로 접으면
        # 오타가 「값 없이 채점」으로 위장한다.
        out["value"] = {"column": _named(v, "value"), "origin": COLUMN_CHOSEN, "reason": None}
    elif proposal and proposal.get("val") and not guessed:
        # 제안은 다르다. `resolve_binding_info`는 선언에 없는 키를 **데이터 경로가 실제로
        # 쓰는 기본값**(리터럴 `val`)으로 채워 서빙하므로, 값 컬럼을 선언하지 않은 현장의
        # 제안은 실재하지 않는 컬럼을 가리킨다. 그것은 잘못된 선언이 아니라 **값 컬럼이
        # 없다는 뜻**이고(데이터 경로 `_cells_of`도 같은 판정을 한다), 거절이 아니라
        # 점유 전용으로 내려앉는다.
        col = proposal["val"]
        if getattr(model, col, None) is None:
            out["value"] = {"column": None, "origin": COLUMN_ABSENT,
                            "reason": "제안된 값 컬럼 '%s'이 '%s'에 없습니다 - 점유만으로 "
                                      "대조합니다" % (col, table)}
        else:
            out["value"] = {"column": col, "origin": COLUMN_PROPOSED, "reason": None}
    else:
        out["value"] = {"column": None, "origin": COLUMN_ABSENT,
                        "reason": (_VALUE_GUESS_REASON if guessed else None)}
    out["proposal"] = proposal
    return out


def comparison_kind(reference_kind: str, source_value_column) -> str:
    """이 실행이 **실제로 무엇으로 대조할 수 있는가**. 기준과 소스 중 약한 쪽을 따라간다.

    합쳐진 답이 가장 약한 기여자를 따라가는 것은 이 저장소의 기존 규칙이고(스펙 §0.2 ⑨,
    `frame_confirmation.weakest_contributor`), 여기서도 같은 규칙이다 — 기준이 값을 실어도
    소스에 값 컬럼이 없으면 값으로 대조할 방법이 없다.

    ⚠️ 이것은 **천장이지 실행 보고가 아니다.** 오늘 `score_candidates`는 점유만 쓴다(스펙 §3의
       「값 일치」 지표는 아직 없다). 그래서 이 값이 말하는 것은 「값으로 갈릴 수 있었나」이고,
       「승자 없음」이 진짜 동점인지 **기준이 애초에 구별할 수 없었던 것**인지를 가른다.
    """
    if reference_kind == REFERENCE_KIND_NONE:
        return REFERENCE_KIND_NONE
    if not source_value_column:
        return REFERENCE_KIND_OCCUPANCY
    return reference_kind


def _to_cells(rows, values=None):
    """좌표를 정수로. `values`가 오면 **같은 순서로** 값 목록도 함께 걸러 낸다.

    🔴 값은 좌표와 **같은 인덱스**에 있어야 한다. 좌표가 하나 버려질 때 값을 안 버리면 그
       뒤의 모든 셀이 옆 셀의 값을 받는다 — 화면은 멀쩡하고 값만 어긋나는 상태(I3)이고,
       개수로는 절대 안 잡힌다. 그래서 두 목록을 한 루프에서 같이 만든다.
    """
    out, vals = [], []
    for i, (x, y) in enumerate(rows):
        try:
            out.append((int(float(x)), int(float(y))))
        except (TypeError, ValueError):
            continue
        vals.append(None if values is None else values[i])
    return (out, vals) if values is not None else out


def _cells_of(db, cfg: dict, table: str, map_id: str, cap: int):
    """(table, map_id) 한 맵의 좌표 목록. 상한 초과는 **조용히 자르지 않고** 알린다."""
    from database import models
    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        raise ValueError("테이블 '%s'을 찾을 수 없습니다" % table)
    b = _binding_of(cfg, table)
    x_col = getattr(model, b.get("x", "x"), None)
    y_col = getattr(model, b.get("y", "y"), None)
    if x_col is None or y_col is None:
        raise ValueError("테이블 '%s'에 좌표 컬럼이 없습니다" % table)
    filters = map_overlay.build_key_filters(model, b, map_id)
    if filters is None:
        raise ValueError("맵 키 '%s'을 '%s'의 컬럼에 바인딩하지 못했습니다" % (map_id, table))
    # 값 컬럼이 **바인딩에 선언돼 있고 실재하면** 값을 싣는다. 이 사실이 곧 `reference_kind`이고,
    # 서버가 아는 것을 클라가 모양으로 추론하게 두지 않는다.
    val_col = getattr(model, b.get("val", "val"), None) if b.get("val") else None
    cols = [x_col, y_col] + ([val_col] if val_col is not None else [])
    rows = db.query(*cols).filter(*filters).limit(cap + 1).all()
    truncated = len(rows) > cap
    rows = rows[:cap]
    kind = REFERENCE_KIND_VALUES if val_col is not None else REFERENCE_KIND_OCCUPANCY
    # 🔴 값을 **읽고 버리지 않는다.** 이 함수는 예전에 값 컬럼을 SELECT해 놓고 좌표만
    #    돌려주었고, 그래서 `reference.kind: "values"`는 아무도 쓰지 않는 선언이었다.
    #    그러는 동안 채점은 점유만 봤는데, 점유는 평평할 뿐 아니라 **원 마스크 위에서는
    #    아무 방위 정보도 싣지 않는다**(원은 여덟 프레임 모두에 불변 — 스펙 §1). 그
    #    상태에서 나온 격차는 신호가 아니라 표본 잡음이고, 잡음으로 만든 자신 있는 1등은
    #    거절보다 나쁘다.
    values = [(r[2] if val_col is not None else None) for r in rows]
    cells, values = _to_cells([(r[0], r[1]) for r in rows], values)
    return cells, values, truncated, kind


def _ref_state(state, **kw):
    base = {"state": state, "source": None, "table": None, "map_id": None,
            "cells": [], "values": [], "count": 0,
            # 사유는 **코드와 문장 둘 다** 나간다. 코드는 화면이 분기하는 것이고 문장은
            # 사람이 읽는 것이며, 클라가 문장에서 코드를 유도하기 시작하면 그것이 두 번째
            # 판정 구현이 된다(`unscorable_reasons`와 같은 규율).
            "reason_code": None, "reason": None, "truncated": False,
            "kind": REFERENCE_KIND_NONE}
    base.update(kw)
    return base


def _resolve_reference(db, cfg: dict, spec: str, source_maps: list, cap: int,
                       cache: dict = None) -> dict:
    """공통 바닥을 정한다 — **꽂아 넣는 것이지 못 박는 것이 아니다**(스펙 §4).

    셋 다 정상 상태다: 명시 지정 · 맵이 선언한 유효 다이 참조 · **없음**. 세 번째가 운영에서
    가장 흔하다 — 그래서 「없음」은 0점이 아니라 **자기 상태**로 나간다. 0점으로 내보내면
    화면이 「채점했는데 0점」으로 읽고, 그것은 「잴 것이 없었다」와 정반대의 진술이다.

    `cache`: 요청 경계에서 호출자가 만들어 넘기는 dict. 해석된 `(table, map_id)` 뒤에 오는
    질의(메타 · 셀)만 memoize한다 — 목록 화면은 같은 기준을 단위마다 다시 묻고, 그 반복은
    N+1이지 새 정보가 아니다. **어느 기준이 이기는가**는 단위마다 다시 정한다(캐시하지
    않는다) — 그 판정은 그 단위의 소스 맵 선언에 달려 있다.
    """
    table = map_id = origin = None
    if spec:
        if ":" not in spec:
            return _ref_state(REFERENCE_REFUSED,
                              reason_code=REF_REFUSAL_SPEC_MALFORMED,
                              reason="기준 지정은 '테이블:맵ID' 형식이어야 합니다")
        table, map_id = (p.strip() for p in spec.split(":", 1))
        origin = "explicit"
    else:
        for sm in source_maps:
            if not sm.get("meta"):
                continue
            ref, err = map_overlay.parse_valid_die_ref(sm["meta"],
                                                      default_table=sm.get("table"))
            if err:
                return _ref_state(REFERENCE_REFUSED, source="valid_die_ref",
                                  reason_code=REF_REFUSAL_DECLARATION, reason=err)
            if ref:
                table, map_id, origin = ref["table"], ref["map_id"], "valid_die_ref"
                break
    if not table or not map_id:
        return _ref_state(REFERENCE_ABSENT)

    if cache is not None:
        ck = ("ref", table, map_id, origin, cap)
        if ck in cache:
            return cache[ck]
        out = _load_reference(db, cfg, table, map_id, origin, cap)
        if len(cache) < _REF_CACHE_MAX:
            cache[ck] = out
        return out
    return _load_reference(db, cfg, table, map_id, origin, cap)


# 작업 단위 캐시 상한 — 넘치면 그냥 안 담는다(최악이 중복 해석 1회이고 오답은 아니다,
# `map_overlay._VALID_DIE_CACHE_MAX`와 같은 규율).
_REF_CACHE_MAX = 256


def _load_reference(db, cfg: dict, table: str, map_id: str, origin: str, cap: int) -> dict:
    """해석된 기준 하나를 실제로 읽는다. `_resolve_reference`의 꼬리 — **여기 하나뿐이다.**

    거절은 **언제나 사유 코드를 달고** 나간다(`REF_REFUSAL_*`). 이 함수가 목록(카탈로그)과
    상세(`/view`) 양쪽의 유일한 판정자이므로, 여기서 코드를 붙이면 두 화면이 같은 낱말로
    같은 원인을 말한다 — 목록에서 「제안 안 됨」을 본 조작자가 상세를 열어 **다른 이유**를
    듣는 일이 생기지 않는다.
    """
    def _refuse(code, reason):
        return _ref_state(REFERENCE_REFUSED, source=origin, table=table, map_id=map_id,
                          reason_code=code, reason=reason)

    meta = map_overlay.load_map_meta(db, table, map_id)
    if not meta:
        # 🔴 「행이 없다」와 「행은 있는데 grid_metadata가 비었/깨졌다」는 조작자에게
        #    **정반대의 수리**다(등록하라 vs 다시 재라). `load_map_meta`는 둘 다 None을
        #    돌려주므로 여기서 갈라 준다 — 갈라 주지 않으면 등록돼 있는 맵을 두고
        #    「등록되지 않았습니다」라고 말하게 되고, 그 문장은 참이 아니다.
        if _meta_row_exists(db, table, map_id):
            return _refuse(REF_REFUSAL_META_UNREADABLE,
                           "기준 맵 '%s · %s'의 wafer_map_metadata 행은 있으나 "
                           "grid_metadata가 비어 있거나 읽히지 않습니다" % (table, map_id))
        return _refuse(REF_REFUSAL_META_MISSING,
                       "기준 맵 '%s · %s'의 규격이 wafer_map_metadata에 등록되지 않았습니다"
                       % (table, map_id))
    why = map_overlay.geometry_refusal(meta)
    if why is not None:
        return _refuse(REF_REFUSAL_GEOMETRY, "기준 맵 '%s · %s': %s" % (table, map_id, why))
    try:
        cells, values, truncated, kind = _cells_of(db, cfg, table, map_id, cap)
    except ValueError as e:
        return _refuse(REF_REFUSAL_BINDING, str(e))
    if not cells:
        code, reason = _no_cell_refusal(db, cfg, table, map_id)
        return _refuse(code, reason)
    out = _ref_state(REFERENCE_RESOLVED, source=origin, table=table, map_id=map_id,
                     cells=cells, values=values, count=len(cells),
                     truncated=truncated, kind=kind)
    out["meta"] = meta
    return out


def _meta_row_exists(db, table: str, map_id: str) -> bool:
    """메타 **행**이 있는가. 거절 경로에서만 부른다(정상 경로에는 질의를 하나도 더하지 않는다)."""
    from database import models
    model = models.DYNAMIC_TABLES.get(map_overlay.META_TABLE)
    if model is None:
        return False
    try:
        return (db.query(getattr(model, "map_id"))
                  .filter(getattr(model, "target_table") == table,
                          getattr(model, "map_id") == map_id).first()) is not None
    except Exception:
        return False


def _no_cell_refusal(db, cfg: dict, table: str, map_id: str):
    """좌표 0건일 때 **무엇이 0건인가**를 가른다. `(reason_code, 문장)`.

    같은 증상에 원인이 셋이고 수리가 셋 다 다르다:

    ⓐ 그 키에 행이 정말 없다 — 셀을 넣어야 한다.
    ⓑ 행은 있는데 x·y가 수가 아니다 — 데이터를 고쳐야 한다. 개수로는 절대 안 보인다.
    ⓒ **엉뚱한 곳을 봤다.** `compose_map_id`는 키 값들을 '_'로 잇고 `map_key_parts`는
      **마지막 컬럼이 나머지를 흡수**하도록 자른다. 그래서 첫 키 컬럼 값에 '_'가 들어가는
      순간 왕복이 깨진다 — product 'A_B' + type 'C'가 'A_B_C'로 저장되고, 되읽을 때는
      product 'A' / type 'B_C'로 갈려 아무 셀도 만나지 못한다. 양쪽 반이 다 있는데도
      제안되지 않는 바닥의 가장 조용한 원인이 이것이다.

    그래서 문장에 **무엇에 바인딩해 조회했는지**를 적는다. 조작자가 'product=A, type=B_C'를
    보는 순간 ⓒ는 자명해지고, 그 사실은 개수나 코드만으로는 절대 전달되지 않는다.
    """
    bound, key_cols, tokens = None, [], 1
    try:
        b = _binding_of(cfg, table)
        key_cols = list(b.get("key_columns") or [])
        parts = map_overlay.map_key_parts(b, map_id)
        bound = ", ".join("%s='%s'" % (n, v) for n, v in parts)
        tokens = len(str(map_id).split(_MAP_KEY_SEPARATOR))
    except ValueError:
        key_cols = []
    where = (" (조회 조건: %s)" % bound) if bound else ""
    n_rows = _count_cells(db, cfg, table, map_id)
    if n_rows:
        return (REF_REFUSAL_COORDS_UNREADABLE,
                "기준 맵 '%s · %s'의 행에 읽을 수 있는 좌표가 없습니다 — x·y가 수가 "
                "아닙니다%s" % (table, map_id, where))
    if key_cols and tokens < len(key_cols):
        return (REF_REFUSAL_KEY_UNSPLIT,
                "기준 맵 '%s · %s'의 키가 맵 키 컬럼 %s(으)로 분해되지 않습니다%s"
                % (table, map_id, key_cols, where))
    # 🔴 키 컬럼이 하나면 **모호할 수 없다** — 마지막 컬럼이 나머지를 흡수한다는 규칙이 곧
    #    「전부를 그 하나에 준다」가 되어 왕복이 언제나 성립한다(`dt_job='MID_01'`). 여기에
    #    상한 검사를 걸면 정상 키를 모호하다고 고발하게 되고, 그 오진은 없는 결함을 세운다.
    if len(key_cols) >= 2 and tokens > len(key_cols):
        return (REF_REFUSAL_KEY_AMBIGUOUS,
                "기준 맵 '%s · %s'의 키에 '%s'가 맵 키 컬럼 수보다 많아 어디서 잘릴지가 "
                "갈립니다 — 마지막 컬럼이 나머지를 흡수하므로 첫 키 컬럼 값에는 '%s'가 "
                "들어갈 수 없습니다 (맵 키 컬럼 %s)%s"
                % (table, map_id, _MAP_KEY_SEPARATOR, _MAP_KEY_SEPARATOR,
                   key_cols, where))
    return (REF_REFUSAL_NO_CELLS,
            "기준 맵 '%s · %s'에 좌표가 없습니다%s" % (table, map_id, where))


def _map_key_columns(cfg: dict, table: str):
    from database import crud
    info = crud.TABLE_CONFIG.get(table) or {}
    cols = info.get("map_key_columns")
    if not cols:
        raise ValueError("맵 테이블 '%s'에 map_key_columns 선언이 없습니다" % table)
    return list(cols)


def compose_map_id(values) -> str:
    """맵 키 컬럼 값들 → 맵 ID. **목록과 상세가 같은 문자열을 만들어야 한다** — 목록이 센 맵과
    상세가 여는 맵이 다른 이름을 가지면 개수가 조용히 갈린다. 그래서 철자는 여기 하나다.

    ⚠️ 이 조인은 **되돌릴 수 없을 수 있다.** `map_overlay.map_key_parts`는 마지막 컬럼이
       나머지를 흡수하도록 자르므로, 첫 키 컬럼 값에 구분자가 들어가면 왕복이 깨진다
       (`('A_B','C')` → `'A_B_C'` → `('A','B_C')`). 그 경우 셀 조회는 아무것도 만나지
       못하고, `_no_cell_refusal`이 `key_ambiguous`로 그 사실을 이름 붙여 내보낸다.
    """
    return _MAP_KEY_SEPARATOR.join("" if v is None else str(v) for v in values)


def build_alignment_view(db, cfg: dict, rule: dict, key_values: dict, map_table: str,
                         reference_spec: str = None, include_cells: bool = True,
                         cell_cap: int = MAX_PAYLOAD_CELLS,
                         x_col: str = None, y_col: str = None,
                         value_col: str = None) -> dict:
    """한 결정 단위의 정렬 화면 payload **전부**를 한 번에 만든다. 읽기 전용이다.

    후보 8개의 채점이 같은 응답에 들어간다. 후보를 바꾸는 것은 네트워크가 아니라 리페인트여야
    하기 때문이고, 그 요구가 이 함수의 모양을 결정했다.

    `x_col`/`y_col`/`value_col`: **읽을 좌표 삼중항**. 이것이 원시 단위이고, 생략하면 선언
    바인딩이 제안한다(`resolve_source_columns`). 응답 `unit.columns`가 축마다 고른 것인지
    제안받은 것인지를 말한다.
    """
    from database import models

    t0 = time.monotonic()
    src_table = rule["source_table"]
    src_model = models.DYNAMIC_TABLES.get(src_table)
    if src_model is None:
        raise ValueError("소스 테이블 '%s'을 찾을 수 없습니다" % src_table)
    if models.DYNAMIC_TABLES.get(map_table) is None:
        raise ValueError("맵 테이블 '%s'을 찾을 수 없습니다" % map_table)

    # 맵 단위는 **맵 테이블이 선언한 것**을 쓴다 — 여기 컬럼명을 적으면 네 번째 철자가 된다.
    map_key_cols = _map_key_columns(cfg, map_table)

    filters = []
    for col, val in (key_values or {}).items():
        attr = getattr(src_model, col, None)
        if attr is None:
            raise ValueError("소스 테이블 '%s'에 결정키 컬럼 '%s'이 없습니다" % (src_table, col))
        filters.append(attr == val)

    key_attrs = [getattr(src_model, c, None) for c in map_key_cols]
    if any(a is None for a in key_attrs):
        raise ValueError("소스 테이블 '%s'이 맵 키 컬럼 %s을 갖고 있지 않습니다"
                         % (src_table, map_key_cols))
    ids = [compose_map_id(r)
           for r in db.query(*key_attrs).filter(*filters).distinct().all()]

    # 🔴 좌표 컬럼은 **인자**다. 예전에는 여기서 `_binding_of`가 정본이라 `dt_log`의 선언
    #    바인딩(`dt_x`/`dt_y`)이 `map_table`과 무관하게 이겼고, `core_wafer_map`으로 열면
    #    core 맵 ID 아래에 dt 좌표가 모였다.
    columns = resolve_source_columns(cfg, src_table, src_model, x_col, y_col, value_col)
    if not columns["x"]["column"] or not columns["y"]["column"]:
        raise ValueError("소스 테이블 '%s'의 좌표 컬럼을 정할 수 없습니다 - x/y를 "
                         "지정하십시오" % src_table)
    x_attr = getattr(src_model, columns["x"]["column"])
    y_attr = getattr(src_model, columns["y"]["column"])

    v_attr = (getattr(src_model, columns["value"]["column"])
              if columns["value"]["column"] else None)

    source_maps = []
    src_truncated = False
    for mid in ids:
        mfilters = list(filters)
        for i, c in enumerate(map_key_cols):
            part = mid if len(map_key_cols) == 1 else mid.split("_")[i]
            mfilters.append(getattr(src_model, c) == part)
        q_cols = [x_attr, y_attr] + ([v_attr] if v_attr is not None else [])
        rows = db.query(*q_cols).filter(*mfilters).limit(cell_cap + 1).all()
        if len(rows) > cell_cap:
            src_truncated = True
            rows = rows[:cell_cap]
        cells, cvals = _to_cells([(r[0], r[1]) for r in rows],
                                 [(r[2] if v_attr is not None else None) for r in rows])
        source_maps.append({"map_id": mid, "table": map_table,
                            "meta": map_overlay.load_map_meta(db, map_table, mid),
                            "cells": cells, "values": cvals})

    reference = _resolve_reference(db, cfg, reference_spec, source_maps, cell_cap)
    thresholds = load_alignment_thresholds(cfg)

    candidates, excluded, ruling, stats = [], _Excluded(), {"winner": None}, {}
    if reference["state"] == REFERENCE_RESOLVED:
        candidates, excluded, ruling, stats = score_candidates(
            source_maps, reference["cells"], reference["meta"],
            reference_values=reference.get("values"), thresholds=thresholds)
        if ruling.get("winner"):
            state = STATE_SCORED
        elif any(c["state"] == STATE_SCORED for c in candidates):
            state = STATE_NO_WINNER
        else:
            state = STATE_NOT_SCORABLE
    else:
        # 기준이 없으면 채점 자체가 성립하지 않는다. 그래도 **왜 제외됐는지는 센다** —
        # 기준을 꽂았을 때 무엇이 남는지를 조작자가 미리 알아야 고칠 순서를 정할 수 있다.
        state = STATE_NOT_SCORABLE
        for sm in source_maps:
            if not sm.get("meta"):
                excluded.add(EXCLUDE_META_MISSING, sm["map_id"])
            elif not sm.get("cells"):
                excluded.add(EXCLUDE_NO_CELLS, sm["map_id"])
            else:
                why = map_overlay.geometry_refusal(sm["meta"])
                if why is not None:
                    excluded.add(EXCLUDE_GEOMETRY_REFUSED, sm["map_id"], why)

    pooled = []
    if include_cells:
        for sm in source_maps:
            if len(pooled) >= cell_cap:
                src_truncated = True
                break
            for xy in sm["cells"]:
                if len(pooled) >= cell_cap:
                    src_truncated = True
                    break
                pooled.append([xy[0], xy[1]])

    # 단위 안에서 맵들이 **서로 다른 프레임을 적어 두고 있을 수 있다** — 그 어긋남이 이 화면이
    # 맵 하나가 아니라 단위로 도는 이유다. 그래서 하나로 접지 않고 프레임별 개수로 낸다.
 
    _df_cache = {}

    def _df(sm):
        k = id(sm)
        if k not in _df_cache:
            _df_cache[k] = declared_frame_of(sm.get("meta"))
        return _df_cache[k]

    import collections as _c
    tally = _c.Counter()
    axis_tally = {"rotation": _c.Counter(), "side": _c.Counter()}
    unattested = 0
    for sm in source_maps:
        info = _df(sm)
        for ax in ("rotation", "side"):
            axis_tally[ax][info["axes"][ax]] += 1
        if info["source"] == map_overlay.GEOMETRY_DECLARED and info["frame"]:
            tally[info["frame"]] += 1
        else:
            unattested += 1
    for c in candidates:
        c["declared_by_maps"] = int(tally.get(c["frame"], 0))

    return {
        "unit": {"rule": rule.get("name"), "decision_key": dict(key_values or {}),
                 "source_table": src_table, "map_table": map_table,
                 "map_key_columns": map_key_cols,
                 # 무엇을 읽었나, 그리고 **누가 정했나**. 제안(proposed)과 선택(chosen)을
                 # 같은 모양으로 내보내면 화면이 둘을 같게 그리고 기본값이 선언을 사칭한다.
                 "columns": columns},
        "state": state,
        "refusal": compose_refusal(state, reference, excluded, ruling, len(source_maps),
                                   candidates),
        "reference": {
            "state": reference["state"],
            # 이 실행이 **대조에 쓸 수 있는 것**. 소스에 값 컬럼이 없으면 기준이 값을 실어도
            # 점유뿐이다 — 그리고 점유는 평평하다(실측: 8후보가 같은 다이를 차지). 이 값이
            # 「승자 없음」의 사유를 가른다.
            "kind": comparison_kind(reference.get("kind", REFERENCE_KIND_NONE),
                                    columns["value"]["column"]),
            # 기준 맵 **자신이** 싣고 있는 것. 위 값과 갈릴 수 있고, 갈린 이유가 소스 쪽이라는
            # 사실을 여기서만 알 수 있다 — 접으면 조작자가 기준 맵을 의심한다.
            "map_kind": reference.get("kind", REFERENCE_KIND_NONE),
            "source": reference.get("source"),
            "table": reference.get("table"), "map_id": reference.get("map_id"),
            "count": reference.get("count", 0), "reason": reference.get("reason"),
            "truncated": reference.get("truncated", False),
            "cells": ([[x, y] for (x, y) in reference.get("cells") or ()]
                      if include_cells else []),
        },
        "sources": {
            "map_count": len(source_maps),
            "usable_map_count": stats.get("source_maps_usable", 0),
            "cell_count": sum(len(sm["cells"]) for sm in source_maps),
            "cells": pooled, "truncated": src_truncated, "cell_cap": cell_cap,
            "maps": [dict({"map_id": sm["map_id"], "cell_count": len(sm["cells"])},
                          declared_frame=_df(sm)["frame"],
                          declared_frame_source=_df(sm)["source"])
                     for sm in source_maps],
        },
        "candidates": candidates,
        # 적혀 있는 것. **결정이 아니다** (§declared_frame_of).
        "declaration": {
            "frames": dict(tally),
            "unanimous": len(tally) == 1 and unattested == 0,
            "frame": (next(iter(tally)) if len(tally) == 1 and unattested == 0 else None),
            "attested_maps": int(sum(tally.values())),
            "unattested_maps": int(unattested),
            # 축별 집계는 **단위 수준에만** 둔다. 맵마다 축 dict를 실으면 40맵에서 셀 없는
            # payload가 6.5KB -> 11.2KB로 늘고(+72%), 늘어난 것은 정보가 아니라 같은 두 낱말의
            # 40회 반복이다. 어느 맵이 미검증인지는 `maps[].declared_frame_source`가 이미 말한다.
            "axis_sources": {ax: dict(c) for ax, c in axis_tally.items()},
        },
        "ruling": ruling,
        # 문턱은 **서버 config의 선언**이다. 미선언 키는 실리지 않는다 — null로 실으면
        # 받는 쪽의 `Number(null)`이 0이 되어 「모름」이 「문턱 0」으로 바뀐다.
        "thresholds": thresholds,
        "excluded": excluded.as_list(),
        "excluded_total": excluded.total(),
        "stats": dict(stats, build_ms=(time.monotonic() - t0) * 1000.0),
    }


# ---------------------------------------------------------------------------
# 작업 목록 (worklist) — 「어느 단위를 열 것인가」
# ---------------------------------------------------------------------------
# 소비자는 `client2/map_editor2.html`의 목록이다. 상세(`build_alignment_view`)의 색인이지
# 상세의 축소판이 아니다 — 색인이 색인하는 것보다 무거우면 그것은 설계 오류다.
#
# 🔴 **이 함수는 프레임 필드를 모른다** (제품 소유자 지시 2026-08-05: primitive → function →
#    config → preset). `core_frame`/`dt_frame`은 **이름**이고 단위는 좌표 컬럼이다. 목록이
#    답하는 것은 이름과 무관한 네 가지뿐이다: 어떤 단위가 있는가 · 확정됐는가 · 채점이
#    가능한가 · 맵 몇 장이 모이는가. 어느 좌표 컬럼을 읽을지는 **상세에서** 고른다.
#    이름을 여기 실으면 그것이 그 사실이 적히는 두 번째 자리가 된다.
#
# 🔴 **골격은 규칙 자신의 `derived_table`이다.** 단위 목록을 소스 테이블에서 GROUP BY로
#    만들면 1,000만 행 기준으로 요청마다 풀스캔이 된다. 그 표는 이미 규칙이 단위마다 한 행씩
#    materialize해 둔 것이고(`aggregations`), 인리치먼트 대기열이 보는 것과 **같은 표**라
#    두 화면이 서로 다른 단위 집합을 말할 수 없다.

STATE_UNIT_PENDING = "pending"
STATE_UNIT_CONFIRMED = "confirmed"
STATE_UNIT_UNSCORABLE = "unscorable"

#: 화면이 구별하는 상태는 셋뿐이고 **닫혀 있다**. 약한 순서 — 롤업이 필요한 자리에서
#: 「가장 약한 것을 따라간다」(스펙 §0.2 ⑨)를 쓰려면 서열이 값이어야 한다.
UNIT_STATE_STRENGTH = {STATE_UNIT_UNSCORABLE: 0,
                       STATE_UNIT_PENDING: 1,
                       STATE_UNIT_CONFIRMED: 2}

REASON_NO_MAPS = "no_maps"
REASON_MAP_KEYS_UNAVAILABLE = "map_keys_unavailable"
REASON_REFERENCE_ABSENT = "reference_absent"
REASON_REFERENCE_REFUSED = "reference_refused"

# 사유 표찰. 나머지 둘(`meta_missing`·`geometry_refused`)은 **상세의 제외 어휘를 그대로
# 쓴다** — 목록의 「채점 불가」는 상세가 셀 제외 사유로 이미 이름 붙인 것과 같은 사실이고,
# 여기서 다시 이름 지으면 같은 사실에 낱말이 둘이 된다.
_WORKLIST_REASON_TEXT = dict(_EXCLUDE_TEXT)
_WORKLIST_REASON_TEXT.update({
    REASON_NO_MAPS: "맵 0건",
    REASON_MAP_KEYS_UNAVAILABLE: "소스 테이블에 맵 키 컬럼 없음",
    REASON_REFERENCE_ABSENT: TEXT_REFERENCE_ABSENT,
    REASON_REFERENCE_REFUSED: TEXT_REFERENCE_REFUSED,
})

MAX_WORKLIST_UNITS = 2_000        # 한 요청이 판정하는 단위 상한 (초과는 truncated로 명시)
MAX_WORKLIST_MAP_ROWS = 100_000   # (단위, 맵) 쌍 상한 — 맵 모집단 규모에 비례한다
DEFAULT_WORKLIST_LIMIT = 200      # 응답에 싣는 행 수 기본값
_META_CHUNK = 1_000               # IN 절 청킹

#: 화면이 이름 붙일 수 있는 정렬 키. 규칙이 `list_columns`를 선언하면 그것도 더해진다
#: (여기 컬럼명을 적지 않는다).
_BASE_SORT_KEYS = ("unit_key", "state", "map_count", "usable_map_count", "confirmed_at")


def worklist_sort_keys(rule: dict) -> list:
    out = list(_BASE_SORT_KEYS)
    for c in (rule.get("list_columns") or []):
        if c not in out:
            out.append(c)
    return out


def map_table_catalog(src_model, src_table: str) -> list:
    """선언된 맵 테이블과 **이 소스가 실제로 그 단위로 모을 수 있는가**.

    지금까지 조작자가 `map_table`을 고를 방법이 없었다. 목록은 어차피 이 표로 요청을
    검증해야 하므로(선언 없는 테이블은 400) 같은 표를 응답에 싣는 것이 공짜다 — 첫 렌더
    전에 왕복을 하나 더 두거나, 클라가 목록을 복사해 갖는 것보다 낫다.
    """
    from database import crud
    out = []
    for table, info in (crud.TABLE_CONFIG or {}).items():
        cols = (info or {}).get("map_key_columns")
        if not cols:
            continue
        missing = [c for c in cols if getattr(src_model, c, None) is None]
        out.append({
            "table": table,
            "map_key_columns": list(cols),
            "selectable": not missing,
            "reason": (None if not missing else
                       "소스 '%s'에 맵 키 컬럼 없음 - %s" % (src_table, ", ".join(missing))),
        })
    return sorted(out, key=lambda r: (not r["selectable"], r["table"]))


def coordinate_column_catalog(cfg: dict, src_table: str) -> dict:
    """좌표로 쓸 수 있는 **실제 컬럼**과, 지금 선언이 가리키는 쌍.

    🔴 컬럼 쌍을 이름 규칙(`*_x`/`*_y`)으로 짝지어 주지 않는다. 그것은 선언이 아니라 추측이고,
       추측한 짝을 응답에 실으면 그 순간 그것이 선언 행세를 한다(I4). 후보를 나열하고
       **짝짓기는 조작자에게 남긴다** — 이것이 「원시 단위로 일한다」의 뜻이다.
    """
    from database import crud
    types = (crud.TABLE_CONFIG.get(src_table) or {}).get("column_types") or {}
    numeric = sorted(c for c, t in types.items()
                     if str(t).strip().lower() in ("number", "int", "integer", "float",
                                                   "numeric", "double"))
    return {
        "table": src_table,
        "numeric_columns": numeric,
        # 오늘 서버가 스스로 고르는 쌍. 상세(`build_alignment_view`)가 **이것만** 읽는다.
        "declared_binding": map_overlay.resolve_binding_info(cfg, src_table),
    }


def binding_ambiguity(rule: dict, coord: dict) -> list:
    """확정 대상(무엇에 쓰는가)과 좌표 컬럼(어떻게 읽는가) 사이에 **선언이 없는 자리**.

    둘은 다른 것이다. 그런데 규칙이 확정 대상을 둘 이상 선언하고 소스 테이블에도 좌표 후보가
    둘 이상 있으면, 어느 대상이 어느 컬럼 쌍에서 나오는지를 **아무 선언도 말하지 않는다.**
    이름이 닮은 것은 우연이지 선언이 아니다. 여기서 풀지 않고 **사실만 보고한다.**
    """
    out = []
    targets = list(rule.get("target_fields") or [])
    numeric = list(coord.get("numeric_columns") or [])
    binding = coord.get("declared_binding") or {}
    if len(targets) > 1 and len(numeric) > 2:
        out.append({
            "code": "target_to_columns_undeclared",
            "detail": ("확정 대상 %d개, 좌표 후보 컬럼 %d개 - 둘을 잇는 선언 없음. "
                       "좌표 컬럼은 조작자가 고릅니다" % (len(targets), len(numeric))),
        })
    if binding and binding.get("x") and binding.get("y"):
        rest = [c for c in numeric if c not in (binding.get("x"), binding.get("y"))]
        if rest:
            # 이 항목은 **사라지지 않고 참인 상태를 말하도록 바뀌었다.** 예전 이름은
            # `declared_binding_pins_one_pair`였고 그때는 실제로 고정이었다 — 상세가
            # `_binding_of`를 정본으로 읽어 나머지 후보가 도달 불가였다. 지금은 제안이라
            # 이름도 그렇게 바꾼다. 「고정」이라 부르면서 제안을 가리키는 것이 두 번째 철자다.
            out.append({
                "code": "declared_binding_proposes_one_pair",
                "detail": ("선언된 좌표 바인딩이 %s/%s를 제안합니다 - 나머지 후보(%s)는 "
                           "상세 조회에 x_col/y_col로 지정해야 읽힙니다"
                           % (binding.get("x"), binding.get("y"), ", ".join(rest))),
            })
    return out


def _chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ---------------------------------------------------------------------------
# 꽂을 수 있는 기준(floor) 목록 — **선언된 것이 아니라 실제로 풀리는 것**
# ---------------------------------------------------------------------------
# 기준이 파라미터인 이유가 「꽂아 넣는 것이지 못 박는 것이 아니다」(스펙 §4)인데, 무엇을 꽂을
# 수 있는지 아무도 답하지 않아 화면의 선택기가 비어 있었다.
#
# 🔴 **선언된 것을 그대로 나열하면 안 된다.** 실측(개발 박스): `valid_die_ref` 선언 8건 중
#    **0건**이 풀린다. 그 여덟을 목록에 올리면 고를 수 없는 이름이 여덟 개 뜨고, 조작자는
#    선택기 자체를 믿지 않게 된다. 그래서 이 목록은 **해석을 실제로 통과한 것만** 담는다.
#
# 🔴 **빈 목록은 오류가 아니다.** 맵 모집단의 절반은 애초에 바닥이 될 수 없다(320/668이
#    `auto_registered`). 그래서 「봤는데 없다」와 「보지 못했다」를 상태로 가른다 — 빈 배열
#    하나로 두 사실을 같이 말하면 화면이 고장과 정상을 구별할 방법이 없다.
REFERENCE_CATALOG_SERVED = "served"          # 조회했다. items가 비어도 그건 답이다
REFERENCE_CATALOG_UNAVAILABLE = "unavailable"  # 조회 자체가 불가 (메타 표 부재 등)

#: 한 요청이 검사하는 후보 바닥 수 상한. 바닥은 제품·타입 단위라 실제로는 훨씬 적다.
MAX_REFERENCE_CANDIDATES = 50


#: 바닥이 저장되는 테이블들. 오늘은 하나이고, 그것이 **고정된 읽기**(1-a 판정)의 결과다.
def floor_tables() -> list:
    """바닥 셀이 실제로 저장돼 있는 테이블 목록. 오늘은 `VALID_DIE_TABLE` 하나다.

    선언이 어느 테이블을 이름 붙였든 `parse_valid_die_ref`가 읽기를 여기로 고정한다. 목록을
    리스트로 두는 이유는 그 고정이 언젠가 풀릴 때 **응답 형태를 바꾸지 않기 위해서**다 —
    항목은 이미 `table`을 달고 나가므로 여러 테이블이 섞여도 클라는 그대로 읽는다.
    """
    return [map_overlay.VALID_DIE_TABLE]


def resolve_reference_catalog(db, cfg: dict, table: str = None,
                              cap: int = MAX_REFERENCE_CANDIDATES) -> dict:
    """지금 이 서버에서 **실제로 바닥이 되는** 맵들.

    🔴 **이 답은 규칙(rule)과 무관하다.** 어느 바닥이 풀리는가는 맵 테이블의 성질이지 지금
       작업 중인 인리치먼트 규칙의 성질이 아니다. 이 목록이 워크리스트 응답에만 실려 있던
       동안, 정렬 규칙을 아직 선언하지 않은 운영은 양쪽 반이 다 있는 바닥을 **볼 수 없었다** —
       워크리스트가 아무것도 답하지 못하면서 이 목록까지 같이 데려갔기 때문이다. 그래서
       `GET /api/maps/alignment/references`가 규칙 없이도 같은 답을 낸다. 계산은 이 함수
       하나이고 호출자가 둘이다(라우트 · 워크리스트) — **두 번째 해석 경로를 만들지 않는다.**

    `table`: **보고 대상 테이블 필터**다(선택). 없으면 바닥을 담을 수 있는 모든 테이블.
       ⚠️ 이것은 `map_table` 좁히기가 **아니다** — 어느 맵 테이블을 정렬 중인지는 어느 바닥이
       풀리는가를 바꾸지 않으므로 후보 집합을 그것으로 좁히지 않는다. 격자가 맞는지는 단위마다
       다른 판정이라(`make_frame_transform`은 격자가 다르면 거절한다) 여기서는 **격자를 실어
       보내고 판정은 하지 않는다**.

    🔴 판정은 `_load_reference` **하나**가 한다. 여기서 "풀리는가"를 다시 구현하면 목록이
       고를 수 있다고 한 것을 상세가 거절하는 날이 온다.

    [`kind`는 `/view`의 `reference.kind`와 **같은 어휘**다] 같은 사실에 두 철자를 두지 않는다.
    다만 도달 가능한 값이 다르다 — `/view`에서는 단위에 기준이 아예 없을 수 있어 `none`이
    나오지만, 이 목록의 항목은 **구성상 전부 풀린 것**이라 `none`은 절대 나오지 않는다.

    [`not_offered`] 제안되지 않은 후보는 **이름과 사유를 달고** 나간다. 개수만 내보내면
    조작자는 자기 맵이 왜 없는지 알 길이 없고, 그때 조작자가 가는 곳은 수리가 아니라 사람이다.
    `cell_count`는 여기서도 `COUNT(*)`다 — 셀이 **있는데도** 제안되지 않았다는 사실 자체가
    가장 중요한 단서이기 때문이다(셀 0건과 「셀은 있는데 좌표가 안 읽힘」은 다른 수리다).
    """
    from database import models

    meta_model = models.DYNAMIC_TABLES.get(map_overlay.META_TABLE)
    tables = floor_tables()
    if table is not None:
        tables = [t for t in tables if t == table]
    base = {"state": REFERENCE_CATALOG_SERVED, "table": map_overlay.VALID_DIE_TABLE,
            "filter": table, "items": [], "not_offered": [],
            "examined": 0, "rejected": 0, "rejected_example": None,
            "truncated": False, "reason": None}
    if meta_model is None:
        return dict(base, state=REFERENCE_CATALOG_UNAVAILABLE,
                    reason="맵 규격 표(%s) 미등록" % map_overlay.META_TABLE)
    if not tables:
        # 봤는데 없다 — 조회 불가가 아니다. 필터가 고정된 바닥 테이블을 지운 것이고, 그
        # 사실을 말해 준다(빈 배열 하나로는 「고장」과 구별되지 않는다).
        return dict(base, reason="바닥은 '%s'에서만 읽습니다 — '%s'에는 바닥이 저장되지 "
                                 "않습니다" % (map_overlay.VALID_DIE_TABLE, table))

    tt, mid = getattr(meta_model, "target_table"), getattr(meta_model, "map_id")
    items, not_offered, examined, truncated = [], [], 0, False
    for ftable in tables:
        remaining = cap - examined
        if remaining <= 0:
            truncated = True
            break
        rows = (db.query(mid).filter(tt == ftable).order_by(mid)
                  .limit(remaining + 1).all())
        if len(rows) > remaining:
            truncated, rows = True, rows[:remaining]
        for (map_id,) in rows:
            examined += 1
            # cap=1: **풀리는가와 어떤 종류인가**만 묻는다. 셀을 다 끌어오면 목록 한 번에
            # 바닥 수 x 2만 셀을 읽게 되고, 그것은 색인이 색인 대상보다 무거워지는 자리다.
            ref = _resolve_reference(db, cfg, "%s:%s" % (ftable, map_id), [], 1)
            if ref["state"] != REFERENCE_RESOLVED:
                not_offered.append({
                    "table": ftable,
                    "map_id": map_id,
                    "reason_code": ref.get("reason_code"),
                    "reason": ref.get("reason"),
                    "cell_count": _count_cells(db, cfg, ftable, map_id),
                })
                continue
            meta = ref.get("meta") or {}
            grid = map_overlay._grid_of(meta)
            items.append({
                "table": ftable,
                "map_id": map_id,
                # 🔴 값을 싣는 바닥과 점유만 있는 바닥은 **다른 제안**이다. 점유는 평평하고,
                #    기준 발자국이 원이면 방위 정보를 아예 싣지 않는다(스펙 §1). 고르기 전에
                #    보여야 한다 — 한 판 돌려 보고 알게 되면 그 한 판이 낭비다.
                "kind": ref.get("kind"),
                "cell_count": _count_cells(db, cfg, ftable, map_id),
                "grid": (None if grid is None
                         else {"cols": grid["cols"], "rows": grid["rows"]}),
            })
    return dict(base, items=items, not_offered=not_offered, examined=examined,
                rejected=len(not_offered),
                rejected_example=(not_offered[0]["reason"] if not_offered else None),
                truncated=truncated)


def _count_cells(db, cfg: dict, table: str, map_id: str):
    """바닥의 크기. 세는 것이지 끌어오는 것이 아니다 — 4셀짜리 바닥은 고를 이유가 없고,
    그 사실을 알려면 개수만 있으면 된다."""
    from database import models
    from sqlalchemy import func as _func
    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        return None
    try:
        b = _binding_of(cfg, table)
        filters = map_overlay.build_key_filters(model, b, map_id)
        if filters is None:
            return None
        return int(db.query(_func.count()).select_from(model).filter(*filters).scalar() or 0)
    except Exception:
        return None


def _load_metas(db, map_table: str, map_ids) -> dict:
    """맵 규격을 **한 번에** 읽는다. 맵마다 `load_map_meta`를 부르면 N+1이고, 목록의 N은
    단위가 아니라 **맵 모집단**이다(개발 박스 실측: 단위 4개에 core 맵 544장)."""
    from database import models
    import json as _json
    model = models.DYNAMIC_TABLES.get(map_overlay.META_TABLE)
    if model is None:
        return {}
    out = {}
    tt, mid = getattr(model, "target_table"), getattr(model, "map_id")
    gm = getattr(model, "grid_metadata")
    for part in _chunks(map_ids, _META_CHUNK):
        for row in db.query(mid, gm).filter(tt == map_table, mid.in_(part)).all():
            raw = row[1]
            if not raw:
                out[row[0]] = None
                continue
            try:
                out[row[0]] = _json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                out[row[0]] = None
    return out


def _live_confirmations(db, rule_name: str, unit_keys) -> dict:
    """단위별 현행 확정. **읽기만 한다.** 없으면 그 단위에 키가 없다."""
    from database import models
    out = {}
    fc = models.FrameConfirmation
    for part in _chunks(unit_keys, _META_CHUNK):
        rows = (db.query(fc)
                  .filter(fc.rule_name == rule_name, fc.unit_key.in_(part),
                          fc.superseded_by.is_(None))
                  .order_by(fc.version.desc()).all())
        for r in rows:
            out.setdefault(r.unit_key, r)
    return out


def _unit_maps(db, src_model, decision_key: list, map_key_cols: list,
               narrow: list, cap: int):
    """(단위, 맵) 쌍 — **한 질의**. 반환 `{unit_tuple: set(map_id)}`와 truncated.

    행 수는 소스 로그 행 수가 아니라 **서로 다른 맵의 수**에 비례한다(DISTINCT가 DB에서
    접힌다). 그래도 상한을 두고 넘으면 **조용히 자르지 않고 알린다** — 잘린 맵 집합에서 센
    개수는 「맞아 보이는 틀린 수」다.
    """
    key_attrs = [getattr(src_model, c) for c in decision_key]
    map_attrs = [getattr(src_model, c) for c in map_key_cols]
    rows = (db.query(*key_attrs, *map_attrs).filter(*narrow)
              .distinct().limit(cap + 1).all())
    truncated = len(rows) > cap
    rows = rows[:cap]
    n = len(decision_key)
    out = {}
    for r in rows:
        unit = tuple("" if v is None else str(v) for v in r[:n])
        out.setdefault(unit, set()).add(compose_map_id(r[n:]))
    return out, truncated


def build_alignment_worklist(db, cfg: dict, rule: dict, map_table: str,
                             key_values: dict = None, q: str = None,
                             sort: str = "unit_key", order: str = "asc",
                             limit: int = DEFAULT_WORKLIST_LIMIT, offset: int = 0,
                             unit_cap: int = MAX_WORKLIST_UNITS) -> dict:
    """결정 단위 목록. **읽기 전용이다.**

    한 단위에 대해 답하는 것은 넷뿐이다 — 키 값 · 상태 · 맵 몇 장 · 정렬 재료. 상태 어휘는
    `pending` / `confirmed` / `unscorable` 셋으로 닫혀 있고, `unscorable`이 **가장 흔한
    경우**다(개발 박스 실측: 668개 메타 중 320개가 `auto_registered`, `valid_die_ref` 선언
    8개 중 0개 해석). 그래서 그것은 0도 null도 아닌 **자기 상태**이고 **사유를 달고 나간다**
    — 0으로 내보내면 화면이 「채점했는데 0점」으로 읽고, 그것은 「잴 것이 없었다」의 정반대다.

    검색·정렬은 **서버가 한다.** 단위 수는 클라가 통제하는 어떤 값에도 묶여 있지 않으므로
    전량을 내려 브라우저에서 거르는 설계는 규모에서 먼저 깨진다.
    """
    from database import models
    from sqlalchemy import func as _func
    import frame_confirmation

    t0 = time.monotonic()
    rule_name = rule.get("name")
    decision_key = list(rule.get("decision_key") or [])
    if not decision_key:
        raise ValueError("규칙 '%s'에 decision_key 선언이 없습니다" % rule_name)
    src_table = rule["source_table"]
    derived_table = rule.get("derived_table")

    src_model = models.DYNAMIC_TABLES.get(src_table)
    if src_model is None:
        raise ValueError("소스 테이블 '%s'을 찾을 수 없습니다" % src_table)
    derived_model = models.DYNAMIC_TABLES.get(derived_table)
    if derived_model is None:
        raise ValueError("파생 테이블 '%s'을 찾을 수 없습니다" % derived_table)
    if models.DYNAMIC_TABLES.get(map_table) is None:
        raise ValueError("맵 테이블 '%s'을 찾을 수 없습니다" % map_table)

    map_key_cols = _map_key_columns(cfg, map_table)
    missing_key = [c for c in map_key_cols if getattr(src_model, c, None) is None]

    # ---- [1] 골격: 파생 표에서 단위를 읽는다 (행 = 단위) -------------------------------
    key_attrs = []
    for c in decision_key:
        a = getattr(derived_model, c, None)
        if a is None:
            raise ValueError("파생 테이블 '%s'에 결정키 컬럼 '%s'이 없습니다"
                             % (derived_table, c))
        key_attrs.append(a)
    list_cols = [c for c in (rule.get("list_columns") or [])
                 if getattr(derived_model, c, None) is not None]
    list_attrs = [getattr(derived_model, c) for c in list_cols]

    filters = []
    for col, val in (key_values or {}).items():
        a = getattr(derived_model, col, None)
        if a is None:
            raise ValueError("파생 테이블 '%s'에 결정키 컬럼 '%s'이 없습니다"
                             % (derived_table, col))
        filters.append(a == val)
    needle = (q or "").strip()
    if needle:
        from sqlalchemy import String, cast, or_
        pattern = "%" + needle + "%"
        filters.append(or_(*[cast(a, String).ilike(pattern) for a in key_attrs]))

    matched = db.query(_func.count()).select_from(derived_model).filter(*filters).scalar()
    rows = (db.query(*key_attrs, *list_attrs).filter(*filters)
              .distinct().limit(unit_cap + 1).all())
    units_truncated = len(rows) > unit_cap
    rows = rows[:unit_cap]

    nk = len(decision_key)
    units = []
    for r in rows:
        vals = ["" if v is None else str(v) for v in r[:nk]]
        units.append({
            "key": dict(zip(decision_key, vals)),
            "_tuple": tuple(vals),
            "extras": {c: r[nk + i] for i, c in enumerate(list_cols)},
        })

    # ---- [2] 확정 — 「현행 행이 있는가」가 곧 confirmed다 -------------------------------
    for u in units:
        u["unit_key"] = frame_confirmation.compose_unit_key(rule, u["key"])
    live = _live_confirmations(db, rule_name, [u["unit_key"] for u in units])

    # ---- [3] 이 단위들의 맵과 그 규격 (질의 2개) ---------------------------------------
    maps_truncated = False
    per_unit_maps = {}
    if units and not missing_key:
        narrow = []
        if filters:
            # 단위 집합으로 좁힌다. 컬럼별 IN은 과대근사지만 DISTINCT 결과에서 정확히
            # 걸러지고, 튜플 IN과 달리 모든 백엔드에서 같은 뜻이다.
            for i, c in enumerate(decision_key):
                vs = sorted({u["_tuple"][i] for u in units})
                a = getattr(src_model, c, None)
                if a is not None and vs:
                    narrow.append(a.in_(vs))
        per_unit_maps, maps_truncated = _unit_maps(
            db, src_model, decision_key, map_key_cols, narrow, MAX_WORKLIST_MAP_ROWS)
        wanted = {u["_tuple"] for u in units}
        per_unit_maps = {k: v for k, v in per_unit_maps.items() if k in wanted}

    all_ids = set()
    for s in per_unit_maps.values():
        all_ids |= s
    metas = _load_metas(db, map_table, all_ids) if all_ids else {}

    # ---- [4] 단위마다 판정 -------------------------------------------------------------
    ref_cache = {}
    reasons = {}
    by_state = {STATE_UNIT_PENDING: 0, STATE_UNIT_CONFIRMED: 0, STATE_UNIT_UNSCORABLE: 0}
    for u in units:
        ids = per_unit_maps.get(u["_tuple"], set())
        u["map_count"] = len(ids)
        usable = [m for m in ids
                  if metas.get(m) is not None
                  and map_overlay.geometry_declaration(metas[m])
                  == map_overlay.GEOMETRY_DECLARED]
        u["usable_map_count"] = len(usable)
        header = live.get(u["unit_key"])
        u["confirmation"] = (None if header is None else {
            "version": header.version,
            "confirmed_by": header.confirmed_by,
            "confirmed_at": (header.confirmed_at.isoformat()
                             if header.confirmed_at else None),
        })

        reason = None
        if header is not None:
            state = STATE_UNIT_CONFIRMED
        elif missing_key:
            state, reason = STATE_UNIT_UNSCORABLE, REASON_MAP_KEYS_UNAVAILABLE
        elif not ids:
            state, reason = STATE_UNIT_UNSCORABLE, REASON_NO_MAPS
        elif not usable:
            # 남은 것이 전부 제외 — **어느 제외가 지배적인가**를 그대로 말한다. 상세의
            # 제외 어휘와 같은 코드라 목록과 상세가 같은 낱말을 쓴다.
            n_missing = sum(1 for m in ids if metas.get(m) is None)
            state = STATE_UNIT_UNSCORABLE
            reason = (EXCLUDE_META_MISSING if n_missing * 2 >= len(ids)
                      else EXCLUDE_GEOMETRY_REFUSED)
        else:
            ref = _resolve_reference(
                db, cfg, None,
                [{"meta": metas.get(m), "table": map_table} for m in sorted(ids)],
                1, cache=ref_cache)
            if ref["state"] == REFERENCE_ABSENT:
                state, reason = STATE_UNIT_UNSCORABLE, REASON_REFERENCE_ABSENT
            elif ref["state"] == REFERENCE_REFUSED:
                state, reason = STATE_UNIT_UNSCORABLE, REASON_REFERENCE_REFUSED
            else:
                state = STATE_UNIT_PENDING
        u["state"], u["reason_code"] = state, reason
        by_state[state] += 1
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1

    # ---- [5] 정렬 → 자르기. 집계는 **자르기 전** 전량에서 낸다 --------------------------
    sort_keys = worklist_sort_keys(rule)
    key = sort if sort in sort_keys else "unit_key"
    reverse = str(order or "asc").lower() == "desc"

    def _sk(u):
        if key == "state":
            return (UNIT_STATE_STRENGTH.get(u["state"], 0), u["unit_key"])
        if key == "confirmed_at":
            return ((u["confirmation"] or {}).get("confirmed_at") or "", u["unit_key"])
        if key in ("map_count", "usable_map_count"):
            return (u[key], u["unit_key"])
        if key in u["extras"]:
            v = u["extras"][key]
            return (float(v) if isinstance(v, (int, float)) else 0.0, u["unit_key"])
        return (u["unit_key"], "")

    units.sort(key=_sk, reverse=reverse)
    start = max(0, int(offset or 0))
    page = units[start:start + max(1, int(limit or DEFAULT_WORKLIST_LIMIT))]

    coord = coordinate_column_catalog(cfg, src_table)
    references = resolve_reference_catalog(db, cfg)
    return {
        "unit": {
            "rule": rule_name,
            "decision_key": decision_key,
            "source_table": src_table,
            "derived_table": derived_table,
            "map_table": map_table,
            "map_key_columns": map_key_cols,
        },
        # 조작자가 고르는 것들. 라우트가 어차피 이 표로 요청을 검증하므로 응답에 싣는 것이
        # 공짜이고, 클라가 자기 사본을 갖는 것보다 낫다.
        "selection": {
            "map_tables": map_table_catalog(src_model, src_table),
            "coordinates": coord,
            # 꽂을 수 있는 바닥. `map_tables`와 같은 이유로 여기 탄다 — 첫 렌더 전에 왕복을
            # 하나 더 두는 것보다 낫고, 이 목록은 단위·검색·페이지와 무관한 상수라 목록
            # 요청마다 다시 계산해도 같은 답이다.
            "references": references,
            "ambiguity": binding_ambiguity(rule, coord),
        },
        "states": [STATE_UNIT_PENDING, STATE_UNIT_CONFIRMED, STATE_UNIT_UNSCORABLE],
        "totals": {
            "matched": int(matched or 0),
            "judged": len(units),
            "returned": len(page),
            "by_state": by_state,
            # 화면이 경계 아래로 가라앉히고 **한 번만 이름 부르는** 수. 클라가 세지 않는다.
            "unscorable": by_state[STATE_UNIT_UNSCORABLE],
            "units_truncated": units_truncated,
            "maps_truncated": maps_truncated,
            "unit_cap": unit_cap,
        },
        # 사유는 **집계로** 낸다. 행마다 문장을 실으면 목록이 색인하는 것보다 무거워지고,
        # 늘어난 것은 정보가 아니라 같은 문장의 N회 반복이다. 행은 코드만 갖는다.
        "unscorable_reasons": [
            {"reason_code": c, "reason": _WORKLIST_REASON_TEXT.get(c, c), "count": n}
            for c, n in sorted(reasons.items(), key=lambda kv: -kv[1])
        ],
        "sort": {"key": key, "order": "desc" if reverse else "asc",
                 "available": sort_keys},
        "query": {"q": needle or None, "params": dict(key_values or {})},
        "units": [dict({"key": u["key"], "unit_key": u["unit_key"], "state": u["state"],
                        "reason_code": u["reason_code"], "map_count": u["map_count"],
                        "usable_map_count": u["usable_map_count"],
                        "confirmation": u["confirmation"]}, **u["extras"])
                  for u in page],
        "stats": {"build_ms": (time.monotonic() - t0) * 1000.0,
                  "map_pairs": sum(len(s) for s in per_unit_maps.values()),
                  "metas_read": len(metas)},
    }
