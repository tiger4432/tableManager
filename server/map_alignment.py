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
                     shift_window: int = SHIFT_WINDOW, cell_cap: int = MAX_SCORED_CELLS):
    """후보 8개를 **한 호출로** 채점한다. DB를 모른다 — 셀과 메타만 받는다.

    `source_maps`: `[{"map_id": str, "meta": dict, "cells": [(x, y), ...]}]`
    `reference_cells`: 기준(공통 바닥)의 점유 좌표 집합 — 기준 맵 자신의 프레임 좌표다.

    반환: `(candidates, excluded, ruling, stats)`.

    [판별(discriminating)이 무엇을 세는가 — 이 정의가 §1 정리의 직접 구현이다]
    스펙 §1: 원은 여덟 프레임 모두에 불변이므로 아무것도 기여하지 못하고, **점유 부분집합만이
    동점을 깬다.** 그래서 셀 하나가 후보를 구별하는 것은 그 셀의 「기준 위에 있나」 답이
    후보마다 **같지 않을 때**뿐이다. 후보 k의 판별수 = 그 후보가 맞힌 셀 중 **후보들 사이에서
    답이 갈리는** 셀의 수다. 일치수가 커도 판별수가 0이면 그 점수는 아무 후보도 배제하지
    못한다 — 그때 순위를 매기면 틀린 것을 맞다고 말하는 것이다(§0.2 ⑦).
    """
    import numpy as np
    t0 = time.monotonic()
    excluded = _Excluded()

    ref_keys = _encode(sorted(reference_cells or ()))
    ref_sorted = np.unique(ref_keys)

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
        scored_cells += len(sm["_use"])

    # [2] 후보마다 **메타를 통째로 만들어** 변환한다 (모듈 상단 전제).
    per_candidate = []
    for frame in CANDIDATE_FRAMES:
        placed = []
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
            for (x, y) in sm["_use"]:
                placed.append(tf(x, y))
        if failed is not None:
            per_candidate.append({"frame": frame, "keys": None, "reason": failed})
            continue
        per_candidate.append({"frame": frame, "keys": _encode(placed), "reason": None})

    # [3] 후보별 시프트를 풀고 셀별 진리값을 모은다.
    for c in per_candidate:
        if c["keys"] is None:
            c.update(dx=None, dy=None, agreement=0, member=None)
            continue
        dx, dy, hit = _solve_shift(c["keys"], ref_sorted, shift_window)
        c.update(dx=dx, dy=dy, agreement=int(hit),
                 member=_membership(c["keys"], ref_sorted, dx, dy))

    # [4] 판별: 셀마다 후보들의 답이 갈리는가. 길이가 같은 후보들끼리만 비교할 수 있고,
    #     실제로 같다 — 같은 소스 셀 목록을 같은 순서로 놓았으므로 i번째가 같은 셀이다.
    live = [c for c in per_candidate if c["member"] is not None]
    varies = None
    if live:
        n = live[0]["member"].size
        if all(c["member"].size == n for c in live) and n:
            stack = np.vstack([c["member"] for c in live])
            varies = stack.any(axis=0) & ~stack.all(axis=0)
    for c in per_candidate:
        if c["member"] is None or varies is None:
            c["discriminating"] = 0
        else:
            c["discriminating"] = int(np.count_nonzero(c["member"] & varies))

    # [5] 순위와 판정. **개수만** 낸다 — 백분율을 만들지 않는다(모듈 상단).
    agrees = [c["agreement"] for c in per_candidate]
    out = []
    for c in per_candidate:
        others = [a for i, a in enumerate(agrees) if per_candidate[i] is not c]
        runner = max(others) if others else 0
        rot_side = parse_frame(c["frame"])
        out.append({
            "frame": c["frame"],
            "rotation": rot_side[0], "side": rot_side[1],
            "state": STATE_NOT_SCORABLE if c["keys"] is None else STATE_SCORED,
            "shift": None if c["dx"] is None else {"dx": c["dx"], "dy": c["dy"]},
            "agreement": c["agreement"],
            "discriminating": c["discriminating"],
            "placed": 0 if c["keys"] is None else int(c["keys"].size),
            "margin": None if c["keys"] is None else int(c["agreement"] - runner),
            "reason": c["reason"],
        })

    ruling = _rule_on(out)
    stats = {"scored_cells": scored_cells, "truncated": truncated,
             "cell_cap": cell_cap, "shift_window": shift_window,
             "reference_cells": int(ref_sorted.size),
             "source_maps_usable": len(usable),
             "elapsed_ms": (time.monotonic() - t0) * 1000.0}
    return out, excluded, ruling, stats


def _rule_on(candidates: list) -> dict:
    """이길 후보가 있는가 — 없으면 **없다고 말한다**(스펙 §0.2 ⑦: 억지 1등 금지).

    이기려면 셋 다 필요하다: 단독 최고 일치수 · 차점자보다 1 이상 앞섬 · 판별수 > 0.
    셋째가 §1 정리다 — 판별이 0이면 그 일치수는 여덟 후보 모두에 똑같이 붙는 값이라
    아무것도 배제하지 못한다.
    """
    live = [c for c in candidates if c["state"] == STATE_SCORED]
    if not live:
        return {"winner": None, "margin": None, "reason_code": "no_candidate_scored"}
    best = max(c["agreement"] for c in live)
    tops = [c for c in live if c["agreement"] == best]
    if len(tops) > 1:
        return {"winner": None, "margin": 0, "reason_code": "tie",
                "tied": [c["frame"] for c in tops]}
    top = tops[0]
    if top["discriminating"] <= 0:
        return {"winner": None, "margin": top["margin"], "reason_code": "no_discrimination"}
    if top["margin"] is None or top["margin"] < 1:
        return {"winner": None, "margin": top["margin"], "reason_code": "no_margin"}
    return {"winner": top["frame"], "margin": top["margin"], "reason_code": None}


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
}


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
            return "기준 없음 - 유효 다이 맵 미지정"
        if reference.get("state") == REFERENCE_REFUSED:
            return "기준 해석 실패 - %s" % (reference.get("reason") or "사유 미상")
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


def _to_cells(rows):
    out = []
    for (x, y) in rows:
        try:
            out.append((int(float(x)), int(float(y))))
        except (TypeError, ValueError):
            continue
    return out


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
    return _to_cells([(r[0], r[1]) for r in rows]), truncated, kind


def _ref_state(state, **kw):
    base = {"state": state, "source": None, "table": None, "map_id": None,
            "cells": [], "count": 0, "reason": None, "truncated": False,
            "kind": REFERENCE_KIND_NONE}
    base.update(kw)
    return base


def _resolve_reference(db, cfg: dict, spec: str, source_maps: list, cap: int) -> dict:
    """공통 바닥을 정한다 — **꽂아 넣는 것이지 못 박는 것이 아니다**(스펙 §4).

    셋 다 정상 상태다: 명시 지정 · 맵이 선언한 유효 다이 참조 · **없음**. 세 번째가 운영에서
    가장 흔하다 — 그래서 「없음」은 0점이 아니라 **자기 상태**로 나간다. 0점으로 내보내면
    화면이 「채점했는데 0점」으로 읽고, 그것은 「잴 것이 없었다」와 정반대의 진술이다.
    """
    table = map_id = origin = None
    if spec:
        if ":" not in spec:
            return _ref_state(REFERENCE_REFUSED,
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
                return _ref_state(REFERENCE_REFUSED, source="valid_die_ref", reason=err)
            if ref:
                table, map_id, origin = ref["table"], ref["map_id"], "valid_die_ref"
                break
    if not table or not map_id:
        return _ref_state(REFERENCE_ABSENT)

    meta = map_overlay.load_map_meta(db, table, map_id)
    if not meta:
        return _ref_state(REFERENCE_REFUSED, source=origin, table=table, map_id=map_id,
                          reason=("기준 맵 '%s · %s'의 규격이 wafer_map_metadata에 "
                                  "등록되지 않았습니다" % (table, map_id)))
    why = map_overlay.geometry_refusal(meta)
    if why is not None:
        return _ref_state(REFERENCE_REFUSED, source=origin, table=table, map_id=map_id,
                          reason="기준 맵 '%s · %s': %s" % (table, map_id, why))
    try:
        cells, truncated, kind = _cells_of(db, cfg, table, map_id, cap)
    except ValueError as e:
        return _ref_state(REFERENCE_REFUSED, source=origin, table=table, map_id=map_id,
                          reason=str(e))
    if not cells:
        return _ref_state(REFERENCE_REFUSED, source=origin, table=table, map_id=map_id,
                          reason="기준 맵 '%s · %s'에 좌표가 없습니다" % (table, map_id))
    out = _ref_state(REFERENCE_RESOLVED, source=origin, table=table, map_id=map_id,
                     cells=cells, count=len(cells), truncated=truncated, kind=kind)
    out["meta"] = meta
    return out


def _map_key_columns(cfg: dict, table: str):
    from database import crud
    info = crud.TABLE_CONFIG.get(table) or {}
    cols = info.get("map_key_columns")
    if not cols:
        raise ValueError("맵 테이블 '%s'에 map_key_columns 선언이 없습니다" % table)
    return list(cols)


def build_alignment_view(db, cfg: dict, rule: dict, key_values: dict, map_table: str,
                         reference_spec: str = None, include_cells: bool = True,
                         cell_cap: int = MAX_PAYLOAD_CELLS) -> dict:
    """한 결정 단위의 정렬 화면 payload **전부**를 한 번에 만든다. 읽기 전용이다.

    후보 8개의 채점이 같은 응답에 들어간다. 후보를 바꾸는 것은 네트워크가 아니라 리페인트여야
    하기 때문이고, 그 요구가 이 함수의 모양을 결정했다.
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
    ids = ["_".join("" if v is None else str(v) for v in r)
           for r in db.query(*key_attrs).filter(*filters).distinct().all()]

    src_binding = _binding_of(cfg, src_table)
    x_attr = getattr(src_model, src_binding.get("x", "x"), None)
    y_attr = getattr(src_model, src_binding.get("y", "y"), None)
    if x_attr is None or y_attr is None:
        raise ValueError("소스 테이블 '%s'에 좌표 컬럼이 없습니다" % src_table)

    source_maps = []
    src_truncated = False
    for mid in ids:
        mfilters = list(filters)
        for i, c in enumerate(map_key_cols):
            part = mid if len(map_key_cols) == 1 else mid.split("_")[i]
            mfilters.append(getattr(src_model, c) == part)
        rows = db.query(x_attr, y_attr).filter(*mfilters).limit(cell_cap + 1).all()
        if len(rows) > cell_cap:
            src_truncated = True
            rows = rows[:cell_cap]
        source_maps.append({"map_id": mid, "table": map_table,
                            "meta": map_overlay.load_map_meta(db, map_table, mid),
                            "cells": _to_cells(rows)})

    reference = _resolve_reference(db, cfg, reference_spec, source_maps, cell_cap)

    candidates, excluded, ruling, stats = [], _Excluded(), {"winner": None}, {}
    if reference["state"] == REFERENCE_RESOLVED:
        candidates, excluded, ruling, stats = score_candidates(
            source_maps, reference["cells"], reference["meta"])
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
                 "map_key_columns": map_key_cols},
        "state": state,
        "refusal": compose_refusal(state, reference, excluded, ruling, len(source_maps),
                                   candidates),
        "reference": {
            "state": reference["state"],
            "kind": reference.get("kind", REFERENCE_KIND_NONE),
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
        "excluded": excluded.as_list(),
        "excluded_total": excluded.total(),
        "stats": dict(stats, build_ms=(time.monotonic() - t0) * 1000.0),
    }
