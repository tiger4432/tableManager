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
import logging.handlers
import os
import re
import sys
import time
import uuid

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

#: 면(side) 선언 키. 문턱·무게와 **같은 블록**이다 — 이 화면의 판정을 조율하는 자리는 하나다.
SIDES_KEY = "sides"


def load_alignment_sides(cfg: dict) -> list | None:
    """선언된 면만. **선언이 없으면 None이고 그것이 「둘 다」**다.

    🔴 **미선언은 한쪽을 뜻하지 않는다.** 탐색 공간을 좁히는 것은 장비에 대한 주장이고,
       주장은 선언에서 나와야지 기본값에서 상속되면 안 된다 — 문턱이 미선언을 0으로 접지
       않는 것과 **같은 규율**이다(§load_alignment_thresholds). 여기 `("front",)`를 적으면
       그것이 선언을 사칭하는 그럴듯한 기본값이고, 뒷면 웨이퍼가 조용히 후보에서 사라진다.

    읽히지 않는 선언(리스트 아님·빈 리스트·모르는 면)은 선언이 아니다 → None.
    """
    raw = ((cfg or {}).get("alignment") or {}).get(SIDES_KEY)
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        logger.warning("[MapAlignment] '%s' is not a list, ignored: %r", SIDES_KEY, raw)
        return None
    out = [s for s in (str(v) for v in raw) if s in FRAME_SIDES]
    unknown = [v for v in raw if str(v) not in FRAME_SIDES]
    if unknown:
        logger.warning("[MapAlignment] unknown side(s) ignored: %r", unknown)
    if not out:
        logger.warning("[MapAlignment] '%s' declared nothing usable, scoring both: %r",
                       SIDES_KEY, raw)
        return None
    # 선언 순서가 아니라 **어휘 순서**로 정규화한다 - 같은 주장이 두 철자를 갖지 않게.
    return [s for s in FRAME_SIDES if s in out]


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

#: 후보 전용 상태. **「봤는데 졌다」와 「아예 안 봤다」는 다른 사실이다.**
#: 🔴 조작자가 면을 `["front"]`로 좁히면 뒷면 넷은 점수가 낮은 것이 아니라 **채점되지 않았다**.
#:    그 넷을 목록에서 빼면 화면은 네 줄짜리 자신 있는 답을 그리고, 진짜 답이 뒷면일 때
#:    조작자는 그것이 고려조차 안 됐다는 사실을 알 방법이 없다 — 「없음을 0으로 접기」와
#:    같은 계열이고 이 프로젝트를 이미 여러 번 물었다. 그래서 **여덟은 언제나 여덟으로
#:    나가고**, 좁혀진 넷은 이 상태와 사유를 달고 나간다(탐색 공간은 좁아지되 보고는 안 좁는다).
STATE_NOT_CONSIDERED = "not_considered"
TEXT_SIDE_NOT_CONSIDERED = "미채점 - 면 선언 제외"

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
# 🔴 「메타가 없다」의 **다른 두 원인**. `map_overlay.load_map_meta`는 셋 다 None으로 접는데
#    (§map_overlay.META_ACCESS_*), 셋이 한 낱말이면 화면은 언제나 「미등록」을 말한다 —
#    행이 멀쩡히 있는데도. 그리고 이 둘은 맵 하나의 사고가 아니라 **요청 전체의 사고**다.
#
# 🔴 [D5] 이후로는 표찰이 아니라 **안전**의 문제다. 규격 행이 없는 맵은 이제 바닥에서 격자와
#    웨이퍼를 빌려 채점되므로, 메타 테이블을 못 읽으면 서버가 **자기 규격을 선언해 둔 맵까지**
#    미등록으로 착각해 빌린 규격 위에 올린다. 그래서 이 둘은 빌림 **앞에서** 거절한다.
EXCLUDE_META_TABLE_UNDECLARED = "meta_table_undeclared"
EXCLUDE_META_QUERY_FAILED = "meta_query_failed"
# 🔴 **셋째 원인은 서버 코드다.** 가용성 프로브가 자기 센티널을 드라이버에 실어 보내지
#    못하면 질의는 서 보지도 못한 것이라 테이블에 대해 말할 근거가 없다
#    (§map_overlay._probe_key_fault — 2026-08-05에 실제로 이 상태로 배포됐다). 이것을
#    `meta_query_failed`로 접으면 문장이 조작자를 **멀쩡한 스키마**로 보내고,
#    `meta_missing`으로 접으면 **빌림이 열린다**. 그래서 자기 이름을 갖는다.
EXCLUDE_META_PROBE_BROKEN = "meta_probe_broken"
EXCLUDE_GEOMETRY_REFUSED = "geometry_refused"
EXCLUDE_NO_CELLS = "no_cells"
# [D3] **웨이퍼 규격 가정으로도 안 열리는 두 자리.** 격자 치수는 웨이퍼가 아니라 맵의
# 성질이라 바닥에서 빌릴 수 없다 - 한 웨이퍼의 두 맵이 서로 다르게 잘려 있을 수 있고,
# 빌리면 없는 사실을 만든다. 없으면 **무엇이 필요한지 이름을 대고** 거절한다.
EXCLUDE_GRID_DIMS_MISSING = "grid_dims_missing"
EXCLUDE_GRID_DIMS_DIFFER = "grid_dims_differ"
# ═══ [D4] 고쳐야 할 것은 소스 맵이 아니라 **바닥이다** (제품 소유자 확정 2026-08-05) ═══════
#
# 규격 행이 없는 소스 맵은 **정상이다.** 조작자가 정렬을 여는 이유가 바로 그 맵의 규격을
# 모르기 때문이고, 그래서 「미등록이니 등록하고 오라」는 답은 질문에 질문으로 답하는 것이다
# ([D3]이 규격 없는 **행**에 대해 이미 내린 판정과 같은 판정 — 행이 아예 없는 쪽이 오히려
# 더 순수한 같은 경우다).
#
# 🔴 빌릴 바닥이 선언돼 있지 않으면 **거절한다.** 화면 프레임이나 항등 프레임에 얹어
#    「눈으로 보게」 해 주지 않는다 — 근거 없이 그린 좌표는 멀쩡해 보이고 전부 틀리다(I4).
# 🔴 그리고 거절은 **바닥의 이름을 대야 한다.** 종전에는 이 경우 소스 맵 N장이 전부
#    `meta_missing`으로 세어졌다: 선언이 필요한 것은 조작자가 고른 바닥 **한 장**인데
#    소스 맵 N장을 고치러 보내는 문장이다. 15분과 일주일의 차이가 여기서 갈린다.
# 🔴 그래서 이것은 **맵의 사실이 아니라 요청의 사실**이다. 맵마다 세지 않는다 — 응답의
#    `basis_refusal`이 요청 단위로 한 번 말하고, 제외 집계는 이 사유로 부풀지 않는다.
EXCLUDE_BASIS_UNDECLARED = "basis_undeclared"
# [D5] 빌린 격자가 이 맵의 셀을 담지 못한다. **격자를 빌리기 시작한 뒤로 남은 유일한 관문**
# 이고, 「같은 웨이퍼의 부분집합」과 「아예 다른 맵」을 가르는 것이 이것 하나다
# (§cells_outside_grid). 치수 불일치(`grid_dims_differ`)와 **다른 사실이다** — 저쪽은 자기
# 격자를 선언한 맵이 바닥과 어긋난 것이고, 이쪽은 격자를 빌려 놓고 그 안에 안 들어간 것이다.
EXCLUDE_CELLS_OUTSIDE_GRID = "cells_outside_grid"

# 표찰이지 문장이 아니다(§compose_refusal).
_EXCLUDE_TEXT = {
    EXCLUDE_META_MISSING: "맵 규격 미등록 (wafer_map_metadata)",
    EXCLUDE_META_TABLE_UNDECLARED: "wafer_map_metadata 테이블 미선언 - 서버가 규격을 읽지 못함",
    EXCLUDE_META_QUERY_FAILED: "wafer_map_metadata 조회 실패 - 서버가 규격을 읽지 못함",
    EXCLUDE_META_PROBE_BROKEN: "서버 내부 오류 - 규격 조회 가능 여부를 확인하지 못함",
    EXCLUDE_GEOMETRY_REFUSED: "칩 규격 미선언 - 좌표 변환 불가",
    EXCLUDE_NO_CELLS: "좌표 0건",
    EXCLUDE_GRID_DIMS_MISSING: "격자 치수(grid_cols/grid_rows) 미등록 - 가정 대상 아님",
    EXCLUDE_GRID_DIMS_DIFFER: "격자 치수가 기준과 다름 - 같은 잘림이 아님",
    EXCLUDE_BASIS_UNDECLARED: "기준 맵 규격 미선언 - 빌려 올 웨이퍼 치수가 없음",
    EXCLUDE_CELLS_OUTSIDE_GRID: "셀이 빌린 격자 밖 - 같은 격자의 부분집합이 아님",
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
REF_REFUSAL_META_TABLE_UNDECLARED = EXCLUDE_META_TABLE_UNDECLARED  # 메타 테이블 미선언
REF_REFUSAL_META_QUERY_FAILED = EXCLUDE_META_QUERY_FAILED          # 메타 조회 실패
REF_REFUSAL_META_PROBE_BROKEN = EXCLUDE_META_PROBE_BROKEN          # 프로브 자신이 못 섬
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
# 「메타를 못 읽었다」 — 데이터의 사고인가, 서버의 사고인가
# ---------------------------------------------------------------------------
# 판정은 `map_overlay.meta_access_state` 하나가 하고, 여기서는 그 토큰을 이 화면의 제외
# 어휘로 옮겨 문장을 붙일 뿐이다. **두 번째 판정이 아니다.**
_META_ACCESS_CODE = {
    map_overlay.META_ACCESS_UNDECLARED: EXCLUDE_META_TABLE_UNDECLARED,
    map_overlay.META_ACCESS_QUERY_FAILED: EXCLUDE_META_QUERY_FAILED,
    map_overlay.META_ACCESS_PROBE_BROKEN: EXCLUDE_META_PROBE_BROKEN,
}

#: 요청 단위 캐시 키 — `_resolve_reference`의 캐시 dict를 그대로 쓴다(키 모양이 겹치지 않는다).
_META_ACCESS_CK = ("meta_access",)


def meta_absence_reason(db, cache: dict = None):
    """메타가 `None`인 **이유**. `(reason_code, detail|None)`.

    반환이 `EXCLUDE_META_MISSING`이면 그때만 「행이 정말 없다」가 참이고, **그때만 규격을
    빌려도 된다**(§score_candidates). 나머지 둘은 그 맵의 사실이 아니라 요청 전체의 사실이라
    호출자가 요청 단위로 한 번 묻고 결과를 모든 맵에 같이 붙인다.

    `cache`: 요청 경계의 dict(`_resolve_reference`와 공유). 없으면 매번 프로브한다.
    ⚠️ 정상 경로에는 질의를 하나도 더하지 않는다 — **메타가 None인 맵이 있을 때만** 부른다
       (`_meta_row_exists`와 같은 규율).
    """
    if cache is not None and _META_ACCESS_CK in cache:
        return cache[_META_ACCESS_CK]
    state, detail = map_overlay.meta_access_state(db)
    out = (_META_ACCESS_CODE.get(state, EXCLUDE_META_MISSING), detail)
    if cache is not None:
        cache[_META_ACCESS_CK] = out
    return out


# 요청 단위 문장. 사람이 읽을 문장은 전부 서버가 만든다(화면은 아무것도 조립하지 않는다).
_META_ACCESS_TEXT = {
    EXCLUDE_META_TABLE_UNDECLARED: (
        "서버가 wafer_map_metadata를 읽지 못했습니다 - 이 테이블이 선언 테이블 목록에 "
        "없습니다(table_config.json). 이번 요청에서는 **모든 맵의 규격 조회가 실패**했으므로, "
        "아래 제외 사유는 데이터가 아니라 서버 설정을 가리킵니다."),
    EXCLUDE_META_QUERY_FAILED: (
        "서버가 wafer_map_metadata를 조회하지 못했습니다 - 테이블/컬럼 상태를 확인하십시오. "
        "이번 요청에서는 **모든 맵의 규격 조회가 실패**했으므로, 아래 제외 사유는 데이터가 "
        "아니라 스키마 상태를 가리킵니다."),
    # 🔴 조작자에게 시킬 일이 **없다.** 데이터도 스키마도 아니고 서버 코드다 — 그렇게
    #    말하지 않으면 멀쩡한 테이블을 뜯으러 간다(2026-08-05에 실제로 그럴 뻔했다).
    EXCLUDE_META_PROBE_BROKEN: (
        "서버가 wafer_map_metadata를 **읽어 보지도 못했습니다** - 가용성 점검 질의 자체가 "
        "서지 않았습니다(서버 결함). 이번 요청의 규격 조회는 하나도 신뢰할 수 없으나, 이것은 "
        "데이터나 스키마의 상태가 아닙니다 - 서버 로그를 첨부해 개발자에게 알리십시오."),
}


def meta_access_block(code: str, detail: str = None):
    """요청 단위 진술. 사고가 아니면 `None`(= 정상, 화면은 아무것도 그리지 않는다).

    🔴 이것이 없으면 조작자는 맵 N장에 대한 N개의 데이터 이야기를 듣는다 - 진실은
       「서버가 자기 테이블을 못 읽는다」 하나인데. 그 오독이 사람을 등록 작업으로 보낸다.
    """
    if code not in _META_ACCESS_TEXT:
        return None
    return {"reason_code": code, "reason": _EXCLUDE_TEXT[code],
            "detail": detail, "text": _META_ACCESS_TEXT[code]}


def stamp_meta_refusal(db, source_maps, cache: dict = None):
    """메타가 None인 맵들에 **왜 None인지**를 찍는다. 요청 단위 진술을 반환(정상이면 None).

    채점기(`score_candidates`)는 DB를 모른다 - 판정에 필요한 사실을 세션 없이 받아야 하고,
    그래서 이유는 여기(요청 경계)에서 한 번 정해져 맵 dict에 실려 들어간다.

    🔴 **표지가 없다는 것이 곧 「행이 정말 없다」의 증거다.** 채점기는 표지가 붙은 맵만
       거절하고 나머지는 빌림으로 보낸다 — 그래서 이 함수를 안 부르면 못 읽은 맵이 조용히
       빌림을 타고, 그것이 [D5] 이후 가장 비싼 실패다.
    """
    if not any(sm.get("meta") is None for sm in source_maps):
        return None
    code, detail = meta_absence_reason(db, cache)
    if code == EXCLUDE_META_MISSING:
        return None                      # 행이 정말 없다 — 표지를 안 붙인다(빌림 허용)
    for sm in source_maps:
        if sm.get("meta") is None:
            sm["meta_refusal"] = code
            sm["meta_refusal_detail"] = detail
    return meta_access_block(code, detail)


# ---------------------------------------------------------------------------
# [D4] 규격 **행이 없는** 맵을 채점 가능한 상태로 만드는 자리
# ---------------------------------------------------------------------------
# 이 함수가 하는 일은 **조립뿐이다.** 기존 두 프리미티브를 순서대로 부른다:
#   ① `map_meta_registrar.synthesize_grid_meta` — 마스크 중립 합성 프레임(에디터 「표준」
#      선택과 필드 단위로 같은 어휘, `auto_registered` 표지 포함). 세 번째 프레임 합성기를
#      만들지 않는다 — 어휘가 셋이 되는 날 셋이 갈린다(I6).
#   ② `map_overlay.assume_phys_from` — 웨이퍼 규격만 바닥에서 빌린다([D3]과 **같은** 규칙·
#      같은 표지·같은 출처 기록).
#
#   ③ 그리고 **격자도 바닥에서 빌린다**(치수 + 시작). 아래 [D5]가 그 판정이고, 종전
#      판정([D4] 초판·스펙 §9.1)의 **반전**이다.
#
# ═══ [D5] 격자도 빌린다 — 스팬은 안전한 쪽이 아니라 **틀린 쪽**이었다 (2026-08-05) ═════════
#
# 종전 판정: 격자 치수는 맵의 성질이라 빌리지 않고 그 맵 자신의 셀에서 유도한다. 그 근거는
# **「한 웨이퍼의 두 맵이 다르게 잘려 있을 수 있다」**였고, 그 걱정 자체는 참이다.
#
# 🔴 **틀린 것은 어느 경우가 전형인가였다** (제품 소유자 2026-08-05): 이 제품에서 소스 맵은
#    보통 같은 격자의 **부분집합**이다 — DT를 일부만 돌리면 격자가 작아진다. 그러므로 셀
#    스팬은 가끔이 아니라 **체계적으로** 과소평가이고, 바닥이 실제 격자를 들고 있다. 드문
#    위험을 피하려고 정상 경우를 거절하고 있었다.
#
# 🔴 **시작 좌표도 같이 빌린다.** 실측(오라클 대조, 45×39 chip 7×8, 부분 맵 467셀):
#      · 치수만 빌리고 start를 셀에서 유도 → **467/467 셀 전부 틀림**
#      · 치수 + start 둘 다 빌림          → **0/467**
#    이유는 산술이다. 부분 맵의 좌표를 자기 최솟값으로 다시 재면 맵 전체가 평행이동한다
#    (여기서는 11칸). 시프트 풀이는 ±3까지만 흡수하므로 그 오차는 조용히 남는다.
#    ⚠️ 그래서 이것은 스펙 §9.1 표의 셋째 줄(「`grid_start_*`는 절대 불가」)에 대한 **두
#       번째 반전**이다. start는 후보가 푸는 미지가 아니다 — 후보는 회전·면만 훑는다.
#
# 🔴 남는 축은 그대로 **절대 불가**다: `rotation`·`side`는 여덟 후보가 푸는 미지 그 자체이고,
#    베끼면 답을 적어 놓고 그 답이 맞는지 묻는 것이 된다.
# 🔴 결과는 **가정이다.** `geometry_declaration`은 `assumed`라고 답하고(표지를 값보다 먼저
#    본다), 이 dict가 `wafer_map_metadata`에 도달하는 경로는 없다 — `assume_phys_from`의
#    불변식을 그대로 승계한다. **격자 절반을 위한 두 번째 표지를 만들지 않는다.**
def _cell_bbox(cells):
    """셀 목록 → `(min_x, min_y, max_x, max_y)`. 읽을 수 있는 좌표가 없으면 None."""
    xs, ys = [], []
    for xy in cells or ():
        try:
            xs.append(int(xy[0]))
            ys.append(int(xy[1]))
        except (TypeError, ValueError, IndexError):
            continue
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def assumed_meta_for_unregistered(cells, basis_meta: dict, basis: dict = None):
    """규격 행이 **없는** 맵의 계산용 메타. 못 만들면 None (= 바닥이 선언이 아니다).

    `basis`: `{"table":..., "map_id":...}` — 어디서 빌렸는지. 표지 값이 되어 payload와
        확정 기록에 그대로 실린다([D3]과 같은 규율).
    """
    bbox = _cell_bbox(cells)
    if bbox is None:
        return None
    import map_meta_registrar
    frame = map_meta_registrar.synthesize_grid_meta(*bbox)
    # [D6] 치수 갈아끼우기는 자기 철자를 갖는다(`assume_grid_from`). 빌릴 것이 없으면
    #      None이므로 합성 프레임을 그대로 쓴다.
    frame = map_overlay.assume_grid_from(frame, basis_meta, basis) or frame
    # [D10-b] 원점 빌리기는 여기서 손으로 하지 않는다 — `synthesize_grid_meta`가 이미
    # `auto_registered`를 달아 두므로 `assume_grid_from`이 그 표지를 읽고 알아서 빌린다.
    # 술어가 한 곳에 있어야 등록기 행과 미등록 맵이 **같은 규칙**을 받는다.
    return map_overlay.assume_phys_from(frame, basis_meta, basis)


# ═══ [D6] 빌림에는 축이 **둘**이고, 서로 다른 질문이다 (제품 소유자 2026-08-05) ═══════════
#
# 종전 코드에서 빌림의 입구는 조건 **하나**였다: `geometry_refusal(meta) is not None`. 그래서
# 규격을 선언한 맵은 빌림을 통째로 건너뛰고 `grid_dims_differ`로 떨어졌다. 그 한 조건이 사실은
# **두 질문**을 답하고 있었고, 제품 소유자의 판정(스펙 §9.5 — 「가정이 선언된 격자도 덮어」)이
# 둘을 갈랐다:
#
#   ① 이 맵은 **자기 웨이퍼 규격을 쟀는가** → 안 쟀으면 phys를 빌린다.
#   ② 이 맵의 **격자가 웨이퍼 전체의 증거인가** → 아니면 격자를 빌린다.
#
# 🔴 **①이 참이어도 ②는 거짓일 수 있다.** 이 제품의 소스 맵(DT)은 웨이퍼의 **일부만** 덮고,
#    메타 행에 들어 있는 격자는 손으로 넣었거나 그 부분 범위에서 유도한 값이다 — 즉 **없는
#    격자와 같은 등급의 불량 수치**(부분집합의 범위를 전체로 착각한 것)다. 선언돼 있다는 것이
#    잰 적이 있다는 증거가 아니고, 조작자는 이미 가정을 **명시로 수락**했다.
#
# 🔴 **그래서 술어가 둘이다.** 한 조건이 두 이유로 참이면 다음 읽는 사람이 반드시 틀린다 —
#    총괄이 이번 라운드에 없애라고 한 모양이 정확히 그것이다.
def phys_needs_basis(meta: dict | None) -> bool:
    """① 이 맵의 **물리 규격**을 바닥에서 빌려야 하는가.

    판정은 `geometry_declaration` 하나가 하고 여기서는 그 토큰에 질문 하나를 물을 뿐이다
    (`geometry_computable`과 같은 계급 — 몸통을 복사하지 않는다).

    🔴 **[D7] `confirmed`도 빌리지 않는다 — 안 그러면 확정이 자기를 지운다.** 확정이 쓴 행의
       phys는 **이미 바닥의 값**이고 출처가 표지에 적혀 있다. 그것을 다시 빌리면 계산 결과는
       바이트 하나 안 바뀌면서 표지만 `phys_assumed_from`으로 덮이고, 그 순간
       `geometry_declaration`은 `assumed`를 답한다 — 확정 다음 조회가 확정 이전과 **구별되지
       않는다.** 이 축이 묻는 것은 「빌려야 하는가」이지 「선언인가」가 아니고, 근거가 이미
       있는 값에 대한 답은 아니오다.
    """
    return map_overlay.geometry_declaration(meta) not in (
        map_overlay.GEOMETRY_DECLARED, map_overlay.GEOMETRY_CONFIRMED)


def grid_needs_basis(meta: dict | None, basis_meta: dict | None) -> bool:
    """② 이 맵의 **격자**를 바닥에서 빌려야 하는가.

    🔴 「이 맵이 격자를 선언했는가」를 묻지 **않는다.** 이 제품에서 소스 맵의 격자 선언은
       자기 가시 범위이지 웨이퍼의 치수가 아니므로 선언 여부가 답을 가르지 못한다(위 [D6]).
       묻는 것은 **「바닥과 다른가」** 하나다 — 같으면 덮어도 값이 안 바뀌므로 빌릴 일이 없고,
       다르면(없는 경우 포함) 바닥이 참이다.

    바닥에 읽을 격자가 없으면 **False** — 빌릴 것이 없으면 이 축은 열리지 않는다. 그때
    호출자는 종전대로 `grid_dims_missing`/`grid_dims_differ`로 이름을 대고 거절한다.

    🔴 [D10] **치수만 비교한다** (총괄 판정 2026-08-06). 종전에는 `_grid_of` 전체를 견줬고
       거기에는 `start_x/start_y`가 들어 있었다. 그래서 **치수가 같고 원점만 다른 맵**이
       빌림을 발동시켰고, 빌림이 그 원점을 바닥의 것으로 덮었다 — 즉 **확정된 원점이 다음
       채점 읽기에서 지워졌다**(실측 2026-08-06: 41x41 동일, 원점만 (0,0) 대 (1,1)인 맵이
       `grid_needs_basis=True`로 빌림을 타고 start가 (1,1)로 되돌아왔다). 결정한 사실을
       다음 패스가 덮어쓰면 아무것도 결정하지 않은 것이다. 원점은 이 맵의 사실이고
       확정이 알아내는 대상이므로, 빌림의 판정에서 빠진다(§map_overlay.assume_grid_from).
    """
    b = map_overlay.grid_dims(basis_meta)
    if b is None:
        return False
    return map_overlay.grid_dims(meta) != b


def borrowed_meta_for(meta: dict, basis_meta: dict, basis: dict = None,
                      need_phys: bool = True, need_grid: bool = True):
    """두 축을 **각각 필요한 만큼만** 빌린 계산용 사본. phys를 빌려야 하는데 못 빌리면 None.

    🔴 **격자를 먼저 빌린다.** `assume_phys_from`은 격자 치수가 없는 메타를 거절하는데,
       그 거절은 격자를 빌리기 전 세계의 규칙이다 — 순서를 뒤집으면 「격자도 규격도 없는 맵」이
       빌릴 수 있는데도 거절된다.
    ⚠️ 축마다 표지가 따로 붙으므로(`phys_assumed_from` / `grid_assumed_from`) 무엇을 빌렸고
       무엇을 안 빌렸는지가 사본 자신에 남는다. 총괄 확답(2026-08-05): **phys를 선언한 맵은
       자기 phys를 그대로 쓴다** — 잰 값을 빌린 값으로 덮을 이유가 없다.
    """
    out = meta
    if need_grid:
        out = map_overlay.assume_grid_from(out, basis_meta, basis) or out
    if need_phys:
        out = map_overlay.assume_phys_from(out, basis_meta, basis)
    return out


# ═══ [D7] 확정이 쓰는 메타 — 새 프레임을 짓지 않고 **채점이 선 프레임**을 다시 낸다 ════════
#
# 🔴 **격자를 그 맵의 셀에서 다시 유도하지 않는다.** 정렬은 그 맵 자신의 셀에서 유도한 격자
#    위에서 돌지 **않았다** — 바닥에서 **빌린** 격자 위에서 돌았고, 부분 맵을 살린 판정 전체가
#    「부분 맵의 자기 셀 범위는 하한이지 격자가 아니다」였다(§`assume_grid_from` [D5]).
#    새로 합성한 격자를 쓰면 **채점이 한 번도 쓴 적 없는 프레임**을 기록하게 되고, 자기를 낳은
#    판정과 어긋나는 메타 행은 행이 없느니만 못하다.
#
# 🔴 **그래서 채점이 쓴 함수를 그대로 부른다** — `assumed_meta_for_unregistered`(규격 행 없음)
#    과 `assume_phys_from`(행은 있는데 규격이 없음). 두 번째 구현을 두지 않는다.
#
# 🔴 **셀을 다시 읽지 않는 이유는 「비싸서」가 아니라 셀이 결과에 도달할 수 없기 때문이다.**
#    `assumed_meta_for_unregistered`에서 bbox가 하는 일은 `synthesize_grid_meta`에 들어가는
#    것뿐인데, 그 출력의 격자는 곧바로 `assume_grid_from`이 **바닥 격자로 덮고**(다르면) 또는
#    이미 같고(같으면), phys 여섯 키는 `assume_phys_from`이 **바닥 값으로 덮는다.** 남는 필드
#    (rotation 0 · side front · y반전 False · auto_registered)는 상수다. 그러므로 bbox가
#    결과에 남기는 흔적은 `grid_assumed_from` 표지의 **유무 하나뿐**이고, 그 표지는 아래에서
#    명시로 단다 — 새로 만들어지는 행의 격자 출처는 두 갈래 모두 바닥이기 때문이다.
#    (`test_frame_confirmation_meta.py`가 서로 다른 bbox들이 그 한 키 말고는 같은 행을 낸다는
#     것을 직접 확인한다 — 산문이 아니라 검사로.)
#    그래서 여기 넘기는 「셀」은 **바닥 격자 상자의 두 모서리**다: 채점이 실제로 본 bbox와
#    다르지만, 위 문단이 그 차이가 출력에 도달할 수 없음을 말하고 검사가 그것을 못 박는다.
def confirmed_meta_for(meta: dict | None, basis_meta: dict | None, basis: dict,
                       frame: str, mark: dict, shift: dict = None,
                       placement: dict = None) -> dict | None:
    """확정 한 건이 맵 하나에 대해 쓰는 `grid_metadata`. 쓸 것이 없으면 None. **순수 함수다.**

    `meta`: 그 맵의 **저장된** 메타(없으면 None). `basis_meta`: 바닥(유효 다이 맵)의 메타.
    `basis`: `{"table","map_id"}`. `frame`: 확정된 프레임(`rot90_front`).
    `mark`: 확정의 신원 — `{table, map_id, confirmation_uid, confirmed_by, confirmed_at}`.

    쓰는 것과 안 쓰는 것, 그리고 이 목록이 이 함수의 내용이다:
      · `rotation`·`side` ← 확정된 프레임. **언제나 쓴다** — 확정된 것이 이것이다.
      · phys 여섯 키 ← 바닥. **그 맵의 기하가 `declared`가 아닐 때만.** 잰 값을 파생 값으로
        덮지 않는다(`assume_phys_from`의 거절과 **같은 조건**이고, 그래서 같은 술어를 쓴다).
      · 격자(치수·시작) ← **채점이 선 프레임.** 행을 새로 만들 때, 그리고 **채점이 격자를
        빌렸을 때**(§[D8] 아래). 격자는 확정된 두 사실 중 어느 쪽도 아니지만, 채점이 빌린
        격자를 안 적으면 이 행은 **채점이 한 번도 쓴 적 없는 조합**을 기록한다.
      · `grid_y_invert` — **손대지 않는다.** 후보 축이 아니라(§`candidate_frames`) 확정된 적이
        없고, 덮으면 그것에 상대적으로 표현된 회전·면의 뜻까지 바뀐다.
      · `auto_registered` — phys를 다시 쓰면 **뗀다**(§[D8]).

    ═══ [D8] 기존 행 갈래도 새 행 갈래와 **같은 판정**을 받는다 (2026-08-06, 보드 #23 감사)
    🔴 종전 이 갈래는 격자를 손대지 않았고, 근거는 「격자는 확정된 사실이 아니다」였다. 그
       문장은 참인데 결론이 틀렸다 — **부분 맵의 등록기 행은 격자로 그 맵의 셀 bbox를 들고
       있고**(`MapMetaCollector`), 그것은 스펙 §9.5가 「하한이지 격자가 아니다」라고 못 박은
       바로 그 값이다. 그래서 채점은 그 맵의 격자를 **빌린다**(`grid_needs_basis` 참). 빌린
       격자를 안 적으면 이 행은 **바닥의 phys + 등록기의 bbox 격자**를 짝지어 기록하는데,
       그 조합 위에서는 아무 채점도 돈 적이 없다.
       실측 2026-08-06(bbox 2,1..6,5 / 바닥 13x13@(0,0)): 채점은 **13x13@(0,0)** 위에서
       돌았고 이 함수는 **5x5@(2,1)**을 적었다. 새 행 갈래가 피하려고 만들어진 결함을 기존
       행 갈래가 그대로 갖고 있었다.
    🔴 그리고 `auto_registered`가 살아남았다. 그 표지는 **phys 여섯 키를 덮는 표지**인데(§D1)
       이 함수가 그 여섯 개를 바닥 값으로 다시 쓰므로, 남겨 두면 **그 여섯에 대한 거짓
       진술**이 된다. `geometry_declaration` 안에서는 확정 표지가 먼저 읽혀 가려지지만,
       표지를 **직접** 읽는 소비자에게는 안 가려진다(`map_editor.js:6459`가 Push마다 그렇게
       읽어 되쓴다).
    ⚠️ 다만 **뗄 때 격자 출처를 대신 대야 한다.** `auto_registered`는 `grid_start_*`을
       설명하던 유일한 표지이기도 해서, 그냥 떼면 start가 `auto_registered`에서 **`declared`로
       올라선다** — 아무도 선언한 적 없는데. 그래서 「격자 출처를 댈 수 있을 때만」 뗀다.
    """
    parsed = parse_frame(frame)
    if parsed is None or not isinstance(basis, dict):
        # 프레임이 없거나 읽히지 않으면 확정의 **주체**가 없다. 아무것도 쓰지 않는다.
        return None
    rot, side = parsed

    if not meta:
        box = map_overlay.grid_box(basis_meta)
        if box is None:
            return None
        lo_x, lo_y, hi_x, hi_y = box
        base = assumed_meta_for_unregistered([(lo_x, lo_y), (hi_x, hi_y)], basis_meta, basis)
        if base is None:
            return None
        # 새로 만들어지는 행의 격자 출처는 두 갈래 모두 바닥이다(§위 블록).
        base[map_overlay.GRID_ASSUMED_KEY] = dict(basis)
    else:
        # [D8] 채점이 이 맵에 대해 무엇을 빌렸는지 묻고, **채점이 쓰는 그 함수**로 같은
        # 사본을 만든다. 축이 둘이라 질문도 둘이다(§phys_needs_basis / §grid_needs_basis).
        # 🔴 phys 쪽만 술어가 다르다: 채점은 「빌려야 하는가」를 묻고(확정된 phys는 아니오),
        #    쓰기는 「여기에 써도 되는가」를 묻는다(**잰 값 위에만** 아니오). 재확정이 같은
        #    바닥에서 값을 다시 유도하고 표지를 다시 찍으려면 뒤엣것이어야 한다.
        need_phys = (map_overlay.geometry_declaration(meta)
                     != map_overlay.GEOMETRY_DECLARED)
        need_grid = grid_needs_basis(meta, basis_meta)
        base = dict(meta)
        if need_phys or need_grid:
            borrowed = borrowed_meta_for(base, basis_meta, basis, need_phys, need_grid)
            # ⚠️ `borrowed_meta_for`의 None은 **「이 맵을 제외하라」**는 채점의 답이다. 쓰기는
            #    제외할 수 없다 — 조작자는 프레임을 확정했고 그 사실은 남아야 한다. 그래서
            #    phys를 못 빌리면 격자만이라도 채점과 같게 맞추고, 나머지는 그대로 둔다.
            if borrowed is None and need_grid:
                borrowed = borrowed_meta_for(base, basis_meta, basis, False, need_grid)
            base = borrowed or base

    # ── 두 갈래 공통 ──────────────────────────────────────────────────────────────
    # 빌림 표지를 **대체**한다. 저장되는 행에 「가정」이 남으면 확정된 파생과 확정되지 않은
    # 추측이 구별되지 않고, 그 구별이 이 표지가 존재하는 이유다(§map_overlay [D7]).
    if base.pop(map_overlay.PHYS_ASSUMED_KEY, None) is not None:
        base[map_overlay.PHYS_CONFIRMED_KEY] = dict(mark or {})
        # [D8] phys를 다시 썼으므로 `auto_registered`는 그 여섯 키에 대해 거짓이 됐다.
        # 격자 출처를 댈 수 있을 때만 뗀다 — 아니면 `grid_start_*`가 `declared`로 새고,
        # 그것이 이 어휘가 막으려는 사칭이다(I4). 못 대는 경우는 「바닥이 phys는 선언했는데
        # 격자는 못 읽히는」 구석 하나뿐이고, 그런 바닥 위에서는 채점 자체가 서지 못한다.
        if not base.get(map_overlay.GRID_ASSUMED_KEY):
            g = map_overlay._grid_of(basis_meta)
            if g is not None and map_overlay._grid_of(base) == g:
                base[map_overlay.GRID_ASSUMED_KEY] = dict(basis)
        if base.get(map_overlay.GRID_ASSUMED_KEY):
            base.pop(map_overlay.AUTO_REGISTERED_KEY, None)
    base["rotation"], base["side"] = rot, side
    # ═══ [D9] **치수는 바닥에서, 원점은 정렬에서** (총괄 판정 2026-08-06) ══════════════
    # [D8]은 **격자 치수**에 대한 논거이고 그대로 선다: 부분 맵의 등록기 격자는 하한이지
    # 격자가 아니므로 바닥의 치수를 빌리는 것이 맞다. **원점은 다른 주장이다** — 바닥의
    # 원점은 *바닥이* 어디서 시작하는지를 말하고, 이 맵의 원점은 **정렬이 알아낸 것**이다.
    # 둘을 한 값으로 접은 것이 위 실측의 오류 ①(반대 방향 한 시프트)이다.
    #
    # 🔴 그리고 이것이 이 화면의 **이름 그대로**다: 좌표계 확정. 원점은 좌표계의 일부이고,
    #    프레임만 확정되고 원점은 정렬 이전의 추측으로 남은 행은 절반만 확정된 것이며,
    #    빠진 절반이 **모든 다이를 움직이는** 절반이다. 그래서 별도 필드를 만들지 않는다 —
    #    「원점은 X인데 X에 이 수를 더해서 읽어라」는 오늘 두 번 값을 치른 바로 그 모양이다.
    #
    # ⚠️ **소비자 노출 — 다음 라운드에서 물을 것**: `client2/src/map_editor.js:6459`가 Push
    #    때마다 `grid_metadata`를 읽어 되쓴다. 확정된 원점을 정렬 이전의 값으로 덮어쓸 수
    #    있는지는 이 파일에서 답할 수 없다. 총괄에 보고했고 이 주석이 그 자리를 표시한다.
    # 🔴 **계산은 하나, 목적지는 둘.** 확정 메타의 `grid_start_x/y`와 확정 기록의 같은 값이
    #    `start_from_placement` **한 번의 반환값**을 나눠 쓴다 — 두 자리가 각자 계산하면 언젠가
    #    갈리고, 그 갈림이 오늘 아침 시프트를 깨뜨린 모양 그대로다(총괄 지시 2026-08-06).
    #    앵커 쌍이 오면 그것이 정본이고, 안 오면 탐색 배치용 유도가 남은 호출자를 받는다.
    # 🔴 **갈래가 둘인 이유는 배치의 종류가 둘이기 때문이다**(§`start_from_placement` ①).
    #    앵커 쌍이 오면 평행이동의 정본은 그 쌍이고 `shift`는 잔차일 뿐이라, `shift`만 읽는
    #    유도는 나머지 평행이동을 통째로 놓친다. 앵커가 없으면(탐색 배치) `shift`가 평행이동
    #    전부이고, 그때 `start_for_placement`는 옳다 — 은퇴하는 것은 그 함수가 아니라
    #    「앵커 배치에도 그것을 쓰던 배선」이다.
    if placement and placement.get("anchor_src") and placement.get("anchor_ref"):
        st = start_from_placement(base, basis_meta,
                                  placement.get("anchor_src"), placement.get("anchor_ref"))
        if st is not None:
            base["grid_start_x"], base["grid_start_y"] = st
    elif shift:
        st = start_for_placement(base, basis_meta, shift)
        if st is not None:
            base["grid_start_x"], base["grid_start_y"] = st
    base[map_overlay.FRAME_CONFIRMED_KEY] = dict(mark or {})
    # ═══ 확정은 **유효 다이 영역도 확정한다** (제품 소유자 2026-08-06) ═══════════════════
    # 「클라 확정 시 메타에 valid die ref 현재 가정한 유효다이영역으로 넣어줘」 ·
    # 「맵 불러올때 유효 맵 안맞잖아」 — 두 문장은 같은 구멍의 쓰기 쪽과 읽기 쪽이다.
    #
    # 🔴 **읽기 경로는 틀린 것이 아니라 몰랐다.** 정렬 화면(`_resolve_reference`)과 맵
    #    에디터(`map_editor.js parseValidDieRef`)는 **둘 다** 이 맵 자신의
    #    `grid_metadata.valid_die_ref`를 읽는다 — 유도가 하나뿐이고 양쪽이 같은 계약 벡터로
    #    채점된다(`contracts/map_seam` · 사용자 지시 2026-08-04 「불러오기는 무조건
    #    valid_die_ref 를 이용하게」). 확정이 그 키를 **안 썼을 뿐**이다. 그래서 고칠 것은
    #    읽기의 해석이 아니라 **기록을 건네주는 것**이고, 읽기 경로는 한 줄도 바뀌지 않는다.
    #
    # 🔴 **쓰기는 기존 계약 심볼로 한다**(`apply_valid_die_ref`). 여기서 키에 직접 대입하면
    #    그것이 두 번째 철자가 되고, 클라의 `applyValidDieRef`와 같은 벡터로 채점되던 규칙
    #    (빈 키는 해제 · 테이블 없는 반쪽 객체 금지 · 나머지 키 보존)이 이쪽에서만 사라진다.
    #
    # 🔴 **없으면 안 쓴다.** 기준 없이 채점된 판(소스가 자기 선언을 따라간 경우)은 실재하는
    #    정상 상태이고, 그때 추측을 적으면 아무도 확정한 적 없는 바닥을 확정으로 만든다.
    #
    # ⚠️ **선례 규칙은 쓰기가 정한다.** 읽기와 쓰기가 같은 키를 쓰므로 확정이 선언을 덮고,
    #    「확정이 선언을 이긴다」가 읽기 시점 분기 없이 성립한다. 덮인 선언의 이력은 확정
    #    기록(`frame_confirmation.reference_table/map_id`)이 보관한다. 종전 선언을 메타 안에
    #    따로 남길지는 총괄 판정 대상이고 여기서 정하지 않았다.
    _ref_id = (basis or {}).get("map_id")
    if _ref_id:
        base = map_overlay.apply_valid_die_ref(
            base, {"table": (basis or {}).get("table") or map_overlay.VALID_DIE_TABLE,
                   "map_id": _ref_id})
    return base


def start_for_placement(framed_meta: dict, target_meta: dict, shift: dict):
    """확정된 배치 → 그 배치를 재현하는 **이 맵 자신의 원점** `(start_x, start_y)`. 못 내면 None.

    ═══ 왜 이 함수가 있는가 (실측 2026-08-06) ═══════════════════════════════════════════
    종전 확정은 **배치를 통째로 버렸다.** 프레임만 적고 원점은 바닥의 것을 그대로 베꼈다.
    실측(바닥 start (1,1) · 맵 start (0,0) — 이 박스에 실재하는 조합):
    채점은 `rot90_front`에 **266/266**과 시프트 `(1,-1)`을 냈는데, 확정을 거쳐 다시 읽으면
    **266개 중 0개**가 채점이 놓은 자리에 앉았고 남은 어긋남은 **일률적으로 `(2,-2)`**,
    정확히 시프트의 **두 배**였다. 오류가 둘이고 서로 더해졌기 때문이다:
      ① 맵의 원점을 바닥의 원점으로 덮어써서 **반대 방향으로 한 시프트** 밀었다.
      ② 채점이 푼 배치를 **한 번도 적용하지 않았다**.
    바닥과 맵이 둘 다 원점 (0,0)이면 시프트가 (0,0)이라 두 오류가 **동시에 사라진다** —
    이 저장소의 모든 픽스처가 그 대조군이고, 그래서 이 결함이 안 보였다.

    ═══ 변환 ═══════════════════════════════════════════════════════════════════════════
    `start = 채점이 쓴 start - L⁻¹(shift)`.

    🔴 **`shift`는 기준의 시각 좌표계에 산다**(회전 이후). 원점은 **맵 자신의 시각 좌표계**에
       산다(회전 이전). 그래서 그냥 더하거나 빼면 안 되고 후보 프레임으로 **역회전**해야 한다.
       실측이 그 대가를 준다 — `start ± (dx,dy)`는 여덟 중 **정확히 둘**에서만 맞는다
       (`rot0_front`에 −, `rot180_front`에 +). 나머지 여섯은 최대 `(10,-8)`까지 어긋나고,
       `rot90_back`·`rot270_back`에서는 하필 **(1,1)** 어긋나 「한 칸 밀렸다」로 보인다.
       눈으로 고치는 사람은 `rot0_front`를 시험하고, 맞는 것을 보고, 출하한다.

    🔴 **L을 손으로 쓰지 않는다.** 변환기 계층(`make_frame_transform`)을 그대로 불러 세 점을
       찍어 선형부를 **읽는다** — bbox·start·y반전 규약이 자동으로 일치한다. 손으로 옮겨 쓰면
       그 셋 중 하나를 놓치고, 이 파일은 그 사고를 이미 두 번 겪었다(QA O3 · B1).
       변환은 아핀이므로 세 점이면 선형부가 완전히 정해진다.

    ✅ **검산은 프레임 불변성이다.** 같은 물리 배치에 대해 이 함수가 내는 원점은 **여덟 후보에서
       모두 같아야 한다** — 원점은 회전 이전의 양이므로 프레임에 의존할 수 없다. 역회전이
       빠졌거나·부호가 틀렸거나·회전이 어긋나면 여덟이 갈린다. 단언 하나가 셋을 다 잡는다
       (`test_the_derived_start_is_the_same_under_all_eight_frames`).
    """
    if not isinstance(shift, dict):
        return None
    dx, dy = shift.get("dx"), shift.get("dy")
    if dx is None or dy is None:
        return None
    g = map_overlay._grid_of(framed_meta)
    if g is None:
        return None
    try:
        tf = map_overlay.make_frame_transform(framed_meta, target_meta)
    except ValueError:
        return None
    # 아핀 변환의 선형부를 **읽는다**. 평행이동(bbox·start)은 차분에서 상쇄된다.
    o, ex, ey = tf(0, 0), tf(1, 0), tf(0, 1)
    a11, a21 = ex[0] - o[0], ex[1] - o[1]
    a12, a22 = ey[0] - o[0], ey[1] - o[1]
    det = a11 * a22 - a12 * a21
    # 여덟 후보의 선형부는 전부 부호 있는 치환행렬이라 행렬식이 ±1이다. 아니면 이 자리의
    # 전제가 깨진 것이므로 **원점을 지어내지 않고 거절한다** — 조용한 오답보다 낫다.
    if det not in (1, -1):
        return None
    u = (a22 * dx - a12 * dy) // det
    v = (a11 * dy - a21 * dx) // det
    return int(g["start_x"]) - u, int(g["start_y"]) - v


def start_from_placement(framed_meta: dict, floor_meta: dict, anchor_src, anchor_ref):
    """확정이 메타에 적을 **소스 맵의 원점** `(start_x, start_y)`. 못 내면 None.

    ═══ WHAT THIS FIELD IS FOR, AND WHY THE PREVIOUS TWO DERIVATIONS WERE WRONG ═══════
    `grid_start_x/y` is read by the LEGACY MAP EDITOR to redraw the map. Its defining
    relation is that editor's own, `client2/src/map_editor.js:2012-2029`:

        db_x = col − box.minC + start_x
        db_y = row − box.minR + start_y          (plain)
        db_y = box.maxR − row + start_y          (invertY)

    So the origin this function returns is **the number that makes the editor's own
    arithmetic put the anchor cell on the anchor die.** Solve those three lines for
    `start` and that is the whole specification. Two earlier derivations answered a
    different question and both shipped displaced maps:

      ① `start_for_placement` (still live, still correct — for the OTHER caller) asks
         "which origin reproduces this placement", and its answer `start − L⁻¹(shift)`
         is right **when the placement is the geometric transform plus `shift`**. Under
         the anchor placement it is not: `shift` there is a RESIDUAL, and the rest of
         the translation comes from the anchor pair, which this formula never reads.
         Measured 2026-08-06 (floor 45x30 @(3,5) · chip 5x8 · src rot270_back invertY
         @(6,9), 240 cells, scored 240/240 with value agreement 240/240): it wrote the
         **floor's origin verbatim, (3,5)**, and **240 of 240 cells drew on the wrong
         die**, displaced by a uniform **(4, 3) — both axes**.
      ② `start_from_anchor` (retired here) computed `floor_start + t` with
         `t = anchor_ref − L·anchor_src`. It adds a translation that lives in the
         REFERENCE's stored space to the REFERENCE's origin and calls the sum the
         SOURCE's origin — three different spaces in one expression. Swept over all
         eight source frames × both invertY × two floor frames (32 combinations): it
         put every cell in the right seat in **0 of 32**.
         `floor_start − t`, proposed the same day, scored **4 of 32** — right only where
         `L` degenerates and the two maps' boxes coincide, which is exactly the shape a
         hand-checked example takes.
      This function: **32 of 32.**

    🔴 **`box.minC`/`box.minR` DO NOT CANCEL.** The tempting derivation subtracts one
       `box.min` from another and cancels them. They are not the same number — one is
       the source frame's box and the other the reference frame's, and a rotation of
       90/270 between the two maps exchanges the axes they sit on. Measured: making the
       editor's origin box the valid-die mask box instead of the circle box (same wafer,
       same dies) moved the required origin from (6,9) to (8,11) — **both axes** — in
       the rot270 case, and left it at (6,9) in the rot90 one. A term that moves on one
       frame and not another is not a term that cancels.

    🔴 **DO NOT HAND-WRITE `L`.** It is read off `make_frame_transform` at three points,
       the same discipline `start_for_placement` and `frame_linear_part` already carry.
       This file has transcribed coordinate algebra wrong twice (QA O3 · B1) and the two
       retired derivations above are the third and fourth.

    ✅ **THE INVARIANT THAT CATCHES A REGRESSION**: the answer does not depend on
       `framed_meta`'s own current origin. Moving it by `D` moves `mft(anchor_src)` by
       `−L·D`, and `L⁻¹` turns that back into `−D`, which cancels the `+D` in the first
       term. Measured across floor origins (3,5) and (0,0) — whose `anchor_ref` differ
       by (3,5) — the returned origin was **(6,9) both times**. If a future edit drops
       the `L⁻¹`, or reads a different meta's grid than the one it fed the transform,
       that invariant breaks and `test_the_written_start_is_where_the_editor_redraws_it`
       goes red.

    ⚠️ **THE FLOOR'S DECLARED ORIGIN IS READ HERE AND NOWHERE IN THE SCORER.** The
       product owner ruled `grid_start_x/y` of the valid-die map meaningless — that
       ruling is about SCORING, where the origin cancels in a difference (measured: 0
       outputs move when it changes). The editor draws the reference WITH that value, so
       the handoff needs it. It arrives through `make_frame_transform(_, floor_meta)`,
       and it cancels against `anchor_ref` (which carries the same origin), which is why
       the invariant above holds. Two layers, not a contradiction.
    """
    g = map_overlay._grid_of(framed_meta)
    if g is None or anchor_src is None or anchor_ref is None:
        return None
    try:
        tf = map_overlay.make_frame_transform(framed_meta, floor_meta)
    except ValueError:
        return None
    o, ex, ey = tf(0, 0), tf(1, 0), tf(0, 1)
    a11, a21 = ex[0] - o[0], ex[1] - o[1]
    a12, a22 = ey[0] - o[0], ey[1] - o[1]
    det = a11 * a22 - a12 * a21
    # 여덟 후보의 선형부는 전부 부호 있는 치환행렬이라 행렬식이 ±1이다. 아니면 이 자리의
    # 전제가 깨진 것이므로 **원점을 지어내지 않고 거절한다** — 조용한 오답보다 낫다.
    if det not in (1, -1):
        return None
    # How far this map's OWN reading of the anchor cell sits from where the alignment
    # seated it. Zero means the declared origin already agrees and nothing moves.
    try:
        here = tf(int(anchor_src[0]), int(anchor_src[1]))
        vx = here[0] - int(anchor_ref[0])
        vy = here[1] - int(anchor_ref[1])
    except (TypeError, ValueError, IndexError):
        return None
    u = (a22 * vx - a12 * vy) // det
    v = (a11 * vy - a21 * vx) // det
    return int(g["start_x"]) + u, int(g["start_y"]) + v


def cells_outside_grid(meta: dict, cells) -> str | None:
    """빌린 격자가 이 맵의 셀을 **담을 수 있는가.** 담으면 None, 아니면 사유(사람 말).

    🔴 **빌리기가 관대한 방향이 된 뒤로 남은 유일한 증거다** ([D5]). 격자를 빌리기 전에는
       치수 불일치(`grid_dims_differ`)가 「같은 웨이퍼가 아니다」를 걸러 냈는데, 이제 소스는
       바닥의 격자를 그대로 받으므로 그 관문이 사라진다. 담김은 그 자리를 **의심이 아니라
       증거로** 대신한다: 셀이 격자 밖에 있다는 것은 두 맵이 같은 격자가 아니라는 **양의
       증거**이고, 그때 프레임 밖에 셀을 앉히는 대신 이름을 대고 거절한다.

    ⚠️ **회전은 아직 미지라 치수 스왑을 허용한다.** 저장 좌표의 가용 범위는 프레임의 *visual*
       치수가 정하고, 90/270 프레임에서 그것은 물리 치수의 스왑이다. 스왑을 안 봐주면 회전된
       **전면(full) 맵**이 거짓 거절된다(실측: 45×39 웨이퍼의 rot90 맵 저장 bbox가 y=41까지
       가는데 rows=39다). 여덟 후보가 회전을 푸는 중이므로, 여기서 회전을 하나로 고정하는
       것은 후보 루프보다 먼저 답을 정하는 것이 된다.
    """
    box = map_overlay.grid_box(meta)
    bbox = _cell_bbox(cells)
    if box is None or bbox is None:
        return None
    lo_x, lo_y, hi_x, hi_y = box
    min_x, min_y, max_x, max_y = bbox
    dims = map_overlay.grid_dims(meta)
    if min_x >= lo_x and min_y >= lo_y:
        if max_x <= hi_x and max_y <= hi_y:
            return None
        # 스왑된 프레임(회전 90/270)의 가용 범위
        if dims and max_x <= lo_x + dims[1] - 1 and max_y <= lo_y + dims[0] - 1:
            return None
    return ("셀 범위 x %d~%d · y %d~%d가 빌린 격자의 인덱스 공간 x %d~%d · y %d~%d를 "
            "벗어납니다 - 같은 격자의 부분집합이 아닙니다"
            % (min_x, max_x, min_y, max_y, lo_x, hi_x, lo_y, hi_y))


#: 규격 행이 없는 맵이 **제안은 되는데 걸리지는 않은** 상태의 사유(사람 말). 제외 표찰
#: (`_EXCLUDE_TEXT[EXCLUDE_GEOMETRY_REFUSED]`)에 붙는 상세이지 두 번째 판정이 아니다.
TEXT_NO_META_ROW = ("wafer_map_metadata에 이 맵의 규격 행이 없습니다 ― 기준 맵의 웨이퍼 "
                    "치수를 빌리면 채점할 수 있습니다")

#: 바닥이 선언이 아닐 때의 **요청 단위** 문장. 사람이 읽을 문장은 전부 서버가 만든다.
TEXT_BASIS_UNDECLARED = ("규격 행이 없는 소스 맵을 채점하려면 기준(유효 다이) 맵의 물리 "
                         "규격이 선언돼 있어야 합니다 ― 빌려 올 웨이퍼 치수가 없습니다. "
                         "고쳐야 할 것은 소스 맵이 아니라 **기준 맵 한 장**입니다.")


def compose_basis_refusal(map_ids, basis: dict = None, why: str = None):
    """바닥 미선언 진술 — **요청 단위로 한 번**. 해당 없으면 None.

    🔴 맵마다 세지 않는다. 소스 맵 N장이 같은 하나의 이유로 못 채점되는 것이고, 그 이유는
       **다른 맵(바닥)의 사실**이다. 제외 집계에 N을 실으면 고칠 것이 N개처럼 보인다.
    """
    ids = list(map_ids or ())
    if not ids:
        return None
    text = TEXT_BASIS_UNDECLARED
    if why:
        text = "%s (기준 맵: %s)" % (text, why)
    return {"reason_code": EXCLUDE_BASIS_UNDECLARED,
            "reason": _EXCLUDE_TEXT[EXCLUDE_BASIS_UNDECLARED],
            "text": text,
            "basis": dict(basis) if basis else None,
            "map_count": len(ids),
            "map_ids": ids}


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


#: 잔차 탐색이 훑을 **자리 수**의 상한. 자리 하나가 소스 셀 수만큼의 비교이므로 곱이 비용이고,
#: 바닥이 클수록 소스도 크다 - 상한 없이 두면 이 자리가 채점 시간을 지배한다. 넘치면 그때까지
#: 최선을 쓰되 **사유를 이름으로 낸다**(§ANCHOR_RESIDUAL_CAPPED): 조용히 포기하면 「앵커가
#: 옳았다」와 「다 못 봤다」가 화면에서 같아진다.
_RESIDUAL_SEAT_CAP = 4096


def _residual_shift(placed_keys, ref_sorted, seats, at, walk_rank=None):
    """앵커가 앉힌 배치 위에 **남은 평행이동**을 푼다 → `(dx, dy, 일치수)`.

    ═══ 왜 이 함수가 필요한가 (실측 2026-08-06) ═══════════════════════════════════════════
    앵커는 주장을 하나 산다: **이 작업이 웨이퍼의 좌상단 유효 다이부터 돌았다.** 그 주장이
    참인 작업에서는 여기서 (0,0)이 나오고 아무것도 달라지지 않는다. 거짓인 작업 - 웨이퍼
    중간부터 도는 부분 DT 맵 - 에서는 맵이 통째로 밀려 앉는데, 종전에는 그 밀림을 **볼 수
    있는 자리가 없었다**: `_anchor_shift`가 내는 시프트가 항등적으로 (0,0)이라
    「앵커가 맞았다」와 「앵커가 틀렸고 아무도 안 고쳤다」가 한 글자도 다르지 않았다.

    실측(바닥 1313다이 · 소스 266셀 · 심은 프레임 `rot90_front`):
        작업이 훑기 1번부터   → 잔차 (0,0)     점유 266/266   (종전과 같다)
        작업이 훑기 43번부터  → 잔차 (13,2)    점유 140→266   판정이 뒤집힌 셀 126
        작업이 훑기 101번부터 → 잔차 (-9,5)    점유 149→266   판정이 뒤집힌 셀 117
        작업이 훑기 401번부터 → 잔차 (-9,14)   점유 141→266   판정이 뒤집힌 셀 125
    그리고 **순번 축은 넷 다 266/266이다** - 훑기가 평행이동에 불변이므로 밀린 맵에서도
    만점이 나온다. 제품 소유자가 본 화면이 정확히 그것이다: 「index로는 잘 되는데
    shift를 무조건 0,0으로 계산함」.

    🔴 **±window 탐색으로는 못 잡는다.** 잔차는 웨이퍼 반지름만큼 클 수 있고, 실측에서
       기본 창(±3)은 셋 다 **창 끝에 붙은 값**을 골랐다((-3,3)·(3,3) 191~206점) - 답이
       창 밖에 있을 때 나오는 그 지문이다. 창을 그만큼 넓히면 (2w+1)²이라 비용이 제곱으로
       는다.

    🔴 그래서 훑는 것은 창이 아니라 **자리**다: 앵커 다이가 앉을 수 있는 곳은 기준의 다이
       뿐이므로 후보 평행이동은 `기준다이 - 지금앉은자리`로 **기준 셀 수만큼**이고, 제곱이
       아니라 일차다.

    ═══ 🔴 점유만으로는 자리를 못 고른다 — 실측이 그 수를 준다 ══════════════════════════
    「전 셀이 바닥 위」를 만족하는 자리가 **하나가 아니다.** 같은 실측(바닥 1313다이 · 소스
    266셀)에서 완전 적중 자리의 수는:

        훑기 1번부터 → **105자리**   43번부터 → **83자리**   101번부터 → **46자리**
        401번부터 → **5자리**        701번부터 → **6자리**

    다섯 경우 모두 참 자리가 그 안에 있지만, 점유는 그중 하나를 고르지 못한다. 여기서
    동점 규칙(원점에 가까운 쪽)으로 넘기면 **데이터가 아니라 규칙이 맵을 놓는 것**이고,
    그것이 이 파일이 [3-0]에서 시프트 탐색을 물러나게 한 바로 그 이유다.

    가르는 것은 **작업의 물리**다: DT 장비는 다이를 훑기 순서대로 **건너뛰지 않고** 짚으므로,
    참 자리에서는 소스가 덮은 다이들의 **기준 훑기 번호가 끊기지 않은 한 구간**이다. 실측 —
    이 판정은 다섯 경우 **전부에서 자리를 정확히 하나로** 좁혔다(`[(0,0)]`). 함께 잰 다른
    후보 판정(「소스 자신의 훑기 순서가 기준의 순서와 일치」)은 23~53자리를 남겨 **가르지
    못했다** - 그래서 그것이 아니라 이것이다.

    ═══ 🔴 그래서 연속성은 **동점 규칙이 아니라 자격**이다 ═══════════════════════════════
    처음에는 순위(점유 → 연속 → 원점근접)로 짰고, 그것이 **점유 축을 통째로 죽였다.** 후보
    프레임마다 완전 적중 자리 수를 세어 보면 이유가 한눈에 보인다(같은 실측, 프레임 8개):

        작업 훑기   완전적중 자리(모든 프레임 동일)   그중 **연속**인 자리
          1번부터            105                    심은 프레임 1 · rot270_front 1 · 나머지 여섯 0
        101번부터             46                    심은 프레임 1 · rot270_front 1 · 나머지 여섯 0
        401번부터              5                    심은 프레임 1 · rot270_front 1 · 나머지 여섯 0

    **완전 적중 자리 수는 여덟 프레임이 전부 같다** - 부분 맵은 어떤 프레임으로 놓아도 같은
    수의 자리에 들어맞기 때문이다. 그러니 점유를 1순위로 두면 여덟이 전부 266으로 올라가
    동점이 되고, 이 파일이 [3-0]에서 시프트 탐색을 물러나게 한 그 포화를 **내가 다시 만든다**
    (실측: 수리 1차 시안에서 여덟 후보 전부 agreement 266).

    연속을 **자격**으로 두면 여섯 프레임은 앵커 자리에 그대로 남아 종전 점유를 유지하고
    (215·225·90·48·38·9), 움직이는 것은 둘뿐이다. 남는 둘은 순번 축이 가른다 - 심은 프레임
    266/266·위반 0 대 `rot270_front` 0/266·위반 265. `rot270_front`가 함께 걸리는 것은
    결함이 아니라 **뒤집힌 훑기도 끊기지 않은 구간**이기 때문이고, 그 겹침을 가르라고
    §[3a-2] 방향 축이 있다.

    ═══ 🔴 그리고 자격 자리가 **유일할 때만** 옮긴다 ═══════════════════════════════════════
    자격을 「만족하는 첫 자리」로 읽었더니 **작은 소스에서 방향 축이 죽었다**(실측: 셀 2개짜리
    소스에서 `test_direction_narrows_a_tie_that_order_alone_cannot`·
    `test_the_floor_is_the_judge_of_a_wrap_not_the_source` 2건 빨강). 이유는 셈으로 나온다 -
    자격은 **소스가 클수록 강하다**: 266셀에서는 자격 자리가 프레임당 정확히 1개인데, 2셀
    짜리 소스에서는 「전 셀이 바닥 위 · 훑기에서 연속」이 바닥 거의 전역에서 성립한다.
    그 상태에서 첫 자리를 고르면 **증거가 아니라 순회 순서가 맵을 옮기는 것**이다.

    그래서 판정은 개수다: 자격 자리가 **정확히 하나면** 데이터가 자리를 정한 것이므로 옮기고,
    **0개거나 2개 이상이면 움직이지 않는다**(0,0). 이 파일이 순위에 대해 지키는 규율
    (판별이 0이면 1등을 뽑지 않는다)을 배치에 대해 그대로 적용한 것이다. 둘째 자격 자리를
    찾는 순간 멈춘다 - 「유일하지 않다」를 알기 위해 나머지를 다 셀 필요가 없다.

    🔴 자격 자리가 없거나 여럿이면 종전 동작과 **한 자도 다르지 않다**. 이 함수는 증거가
       있을 때만 고친다.

    `walk_rank`: `ref_sorted`와 **같은 순서로 정렬된** 기준 다이의 훑기 번호. None이면
        연속성을 물을 수 없으므로 **아무것도 움직이지 않는다**(종전 동작).
    """
    import numpy as np
    n = int(placed_keys.size)
    # 관측 전용 장부. **판정에 안 쓰인다** - 자격 셋이 각각 몇 자리를 통과시켰는지를
    # 화면과 로그가 볼 수 있게 할 뿐이다. 합집합만 보면 「전부 떨어뜨린 관문」과
    # 「한 번도 안 돈 관문」이 밖에서 똑같이 생겼다(제품 소유자 진단 요청 2026-08-06).
    obs = {"state": None, "seats_scanned": 0, "gate1_on_valid_dies": 0,
           "gate2_unbroken_run": 0, "qualifying": 0, "hit": 0,
           "best_hit": 0, "best_tied": 0}
    if n == 0 or ref_sorted.size == 0 or walk_rank is None:
        obs["state"] = RESIDUAL_NO_WALK_RANKS
        return 0, 0, 0, obs
    ax, ay = int(at[0]), int(at[1])
    best = None
    tried = 0
    capped = False
    # 지금 앉은 자리를 **먼저** 본다: 앵커의 주장이 참이면 여기서 끝난다.
    for (sx, sy) in [(ax, ay)] + list(seats or ()):
        dx, dy = int(sx) - ax, int(sy) - ay
        if tried and (dx, dy) == (0, 0):
            continue
        tried += 1
        if tried > _RESIDUAL_SEAT_CAP:
            capped = True
            break
        shifted = placed_keys + dx * _KEY_STRIDE + dy
        idx = np.searchsorted(ref_sorted, shifted)
        idx[idx >= ref_sorted.size] = 0
        hit = int(np.count_nonzero(ref_sorted[idx] == shifted))
        # 🔴 **점유 최고점은 자리를 고르지 못한다 - 포화한다.** 그래서 최고점 하나가 아니라
        #    **최고점에 몇 자리가 묶였는지**를 센다. 실측(바닥 677다이 · 240셀): 최고점
        #    240/240에 후보마다 4~11자리가 묶였다. 「최적 자리」를 하나 지목하는 보고는
        #    그 동점의 임의의 한 원소를 지목하는 것이다.
        if hit > obs["best_hit"]:
            obs["best_hit"], obs["best_tied"] = hit, 1
        elif hit == obs["best_hit"]:
            obs["best_tied"] += 1
        if hit != n:
            continue                      # 자격 ①: 전 셀이 유효 다이 위에 앉아야 한다
        obs["gate1_on_valid_dies"] += 1
        r = walk_rank[idx]
        if int(r.max()) - int(r.min()) + 1 != n:
            continue                      # 자격 ②: 그 다이들이 훑기의 끊기지 않은 한 구간
        obs["gate2_unbroken_run"] += 1
        if best is not None:
            # 자격 ③: 유일해야 한다 - 둘째를 봤으니 안 옮긴다
            obs.update(state=RESIDUAL_NOT_UNIQUE, seats_scanned=tried, qualifying=2)
            return 0, 0, 0, obs
        best = (dx, dy, n)
    obs["seats_scanned"] = tried
    obs["qualifying"] = obs["gate2_unbroken_run"]
    if best is None:
        obs["state"] = RESIDUAL_SEAT_CAP if capped else RESIDUAL_NO_QUALIFYING_SEAT
        return 0, 0, 0, obs
    obs["hit"] = best[2]
    # ①과 ②를 **반환값이 아니라 이름으로** 가른다. 둘 다 `(0,0)`을 내지만 하나는 「앵커가
    # 옳았다」이고 하나는 「고칠 근거가 없었다」다.
    obs["state"] = (RESIDUAL_ANCHOR_HELD if (best[0], best[1]) == (0, 0)
                    else ANCHOR_SEAT_CORRECTED)
    return best[0], best[1], best[2], obs


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


# ---------------------------------------------------------------------------
# 순번(serpentine index) — **절대 기준점**
# ---------------------------------------------------------------------------
# 🔴🔴 [2026-08-06 — 이 축은 틀린 전제 위에 세워져 있었고, 아래가 그 정정이다]
#
#    종전 구현은 **기준 맵의 셀을 훑어** 1..N 정답표를 만들고, 소스에 저장된 순번을 그 표와
#    대조했다. 운영 데이터는 그렇게 매겨지지 않는다 — 제품 소유자 확정:
#
#        「dt index는 1~266 또는 0~255 등이지」 · 「당연히 소스별로 index 매기는거잖아」
#
#    **순번은 그 작업(job)이 실제로 건드린 다이 집합에 대해 매겨진다.** 기준(웨이퍼 전체
#    유효 다이 지도)에 대해서가 아니다. 제품 소유자 단위 실측: 기준 512셀 · 소스 266셀 ·
#    `metric=index` · `reason=no_overlap` — 1..266 수열을 1..512 정답표에 대면 **첫 셀부터
#    끝까지 전부** 어긋난다. 데이터 문제도 config 문제도 아니고 **질문이 틀렸다.**
#
#    올바른 계산: 후보 프레임마다 **소스 자신의 셀을** 그 프레임으로 놓고, **그 셀들을**
#    서펜타인으로 훑어 1..N을 매긴 뒤 저장된 순번과 대조한다. 여덟 후보에서 「어느 행이
#    맨 위인가」와 「그 행의 왼쪽 끝이 어디인가」가 함께 바뀌므로 번호는 통째로 갈린다 —
#    이 축이 만들 가치가 있었던 바로 그 성질이 여기서 나온다.
#
#    합성 실측 2026-08-06 (부분 맵, 이 축이 한 번도 작동한 적 없던 경우):
#    기준 1313셀 · 소스 266셀(52%) · 심은 프레임 `rot90_front` → **정답 266/266, 나머지
#    일곱은 0~22.** 종전 구현이 합성 전체 맵에서 88/87을 냈던 것과 같은 급의 분리를 부분
#    맵에서 재현한다.
#
#    ✅ 그래서 **이 축은 기준을 필요로 하지 않는다.** 종전 주석이 요구하던 「번호는 네가
#       기준으로 꽂은 그 유효 다이 지도에 대해 매겨졌어야 한다」는 데이터의 성질이 아니라
#       **틀린 구현의 결과**였다. 부분 맵은 더 이상 특수한 경우가 아니다.
#
#    ✅ 그리고 **평행이동에 불변이다.** 훑기는 행을 y로 묶고 행 안을 x로 정렬할 뿐이라
#       모든 셀을 (dx,dy)만큼 옮겨도 순서가 한 자도 안 바뀐다(실측: ±1000 오프셋에서
#       266/266 유지). 즉 이 축은 시프트를 **쓰지 않는 것이 아니라 쓸 수가 없다** — 시프트가
#       답을 바꿀 수 없다. 앵커(§_anchor_shift)는 이 축의 부품이 **아니고**, 점유·값 축의
#       평행이동을 정하는 별개의 장치다.
#
#    ✅ 원점은 정규화한다. `0..255`와 `1..266`이 둘 다 실재하므로 **관측된 최솟값을 1로**
#       옮겨 맞춘다 — 절대값은 아무것도 나르지 않고 **순서가 신호 전부**다. 어느 base였는지는
#       진단이 말한다(§_diag_index_block).
#
# ═══ ⚠️ 인접성을 세는 검사는 프레임에 대해 **구조적으로 눈이 멀었다** (2026-08-06) ═════════
# 여덟 후보는 **저장 좌표 격자의 등거리사상(isometry)**이다 — 회전 넷 × 거울 둘. 등거리사상은
# 정의상 거리를 보존하므로, **셀 사이의 거리에서 유도되는 모든 통계는 여덟 후보에서 같은 값**
# 이다. 이웃 거리·인접 개수·군집도·둘레 — 전부.
#
# 실측(클라 레인 2026-08-06, 여덟 후보 전부): 이웃 거리 평균이 **소수점 셋째 자리까지 동일한
# 값 하나**. 같은 데이터에서 방위 서명은 **8/8 서로 다름**.
#
# 🔴 그러므로 **인접성을 채점하는 검사는 프레임에 대해 아무것도 채점하지 않는다.** 그것은
#    픽스처의 사정이 아니라 문제 자체의 성질이고, 앞으로 만들 모든 진단에 걸린다. 클라의
#    첫 오라클이 정확히 여기 빠졌고 음성 대조군 하나가 겨우 잡아냈다 — 서버 쪽 검사도 같은
#    함정에 똑같이 걸릴 수 있으므로 채점이 사는 이 파일에 적어 둔다.
#    방위를 가르려면 **비등거리 양**이어야 한다: 순번 보행 순서(§serpentine_index) · 값 일치
#    (좌표에 값을 묶는다) · 점유 부분집합의 비대칭(스펙 §1이 원은 여덟에 불변이라 말하는 이유).
#
# 점유도 값도 상대적이다: 「이 셀이 유효 다이 위에 있나」·「이 값이 저기 값과 같나」는 둘 다
# **두 미지 사이의 관계**라 어느 쪽도 고정하지 못한다. 순번은 다르다 — 장비가 번호를 매길 때
# 1번은 **정준 방위의 좌상단**이었고, 그 규칙이 이 데이터에서 유일하게 절대적인 것에 걸린
# 진술이다. 그래서 순번은 맞춰 넣을 자유 매개변수가 아니라 **후보를 거는 시험**이다:
# 후보 프레임을 적용한 뒤 「이 셀이 몇 번째로 훑히는가」를 묻고, 여덟이 서로 다른 순서를
# 만들므로 구별은 **구성상** 생긴다.
#
# 🔴 **「1번은 좌상단」은 DT 맵의 규칙이고, core 보행에 적용하면 틀린다**(제품 소유자 확정
#    2026-08-05). DT 목적지에는 그런 원점 규칙이 있다 — 장비가 1번 자리부터 채운다. core
#    웨이퍼에는 없다: 첫 픽은 **bin 1 집합의** 좌상단이지 웨이퍼의 좌상단이 아니고, bin 1의
#    외연은 웨이퍼의 외연이 아니다. 부분집합의 모서리를 웨이퍼의 원점으로 읽는 것이고,
#    그 오독은 조용하다 — 좌표는 멀쩡하고 번호만 통째로 밀린다.
#
#    합성 실측(2026-08-05)이 그 값을 준다: 같은 순번 컬럼이 DT 보행에서 정답 프레임에
#    88/88을 주고, bin으로 묶인 core 보행에서 **4/88**을 준다. 4는 잡음이 아니라 **앵커가
#    틀린 것의 크기**다 — 픽 순서 k와 기준 서펜타인 순위 k가 우연히 겹친 자리의 수다.
#    그 실행에서 8후보 중 틀린 프레임이 1등으로 나온 조합이 2건 있었다.
#
#    그래서 이 축은 **DT 보행 전용**이다. 강제는 두 겹이다: ① `_same_walk`가 선언된 보행
#    밖으로 순번이 따라가지 못하게 막고, ② `alignment.index` 문턱이 없으면 축이 순위를
#    가져가지 않는다. core 쪽 원점은 이 규칙이 아니라 **결함 지문 대조**로 푼다(픽이 결함
#    다이를 건너뛰므로 픽 집합의 구멍이 곧 결함 위치다) — 별개의 기계장치이고 여기 없다.
#
# 🔴 좌상단은 **유도된다, 고르지 않는다** — 그리고 2026-08-06에 그 유도가 바뀌었다.
#    종전에는 훑기가 **기준의 시각 좌표계**에서 돌았고, 그 공간의 「위」는 기준 자신의
#    `grid_y_invert`가 답했다. 지금은 훑기가 **물리(표준) 좌표계**에서 돈다
#    (`map_overlay.make_physical_transform` → `to_standard_coords`: front · rot0 ·
#    start=0 · invert_y=False). 그 좌표계에서는 `cell_to_visual`의 `invert_y=False` 가지가
#    정의상 적용되므로 **가장 작은 y가 맨 위 행이고, 이것은 설정이 아니라 좌표계의 성질**이다.
#    그래서 채점기가 넘기는 `top_is_min_y`는 상수 True다.
#
#    후보 프레임은 **플래그가 아니라 좌표를 통해** 들어온다: 회전·면은 소스 셀을 물리
#    좌표로 보내는 사상 자체를 바꾸므로, 어느 행이 맨 위인지는 이미 좌표에 반영돼 있다.
#    (총괄 가설은 「`top_is_min_y`가 후보 프레임에서 나와야 한다」였는데, 후보 축은
#    회전·면 둘뿐이고 `grid_y_invert`는 후보 축이 **아니다**(§candidate_frames). 그래서
#    그 플래그가 가리킬 후보 값은 존재하지 않는다 — 프레임의 영향은 좌표로 들어온다.)
#
#    🔴 **기준의 시각 좌표계에서 훑으면 조용히 틀린다.** 실측 2026-08-06: 기준이
#    `rotation=90`을 선언한 맵에서 심은 정답이 `rot180_front`인데, 기준 시각 좌표로 훑으면
#    `rot270_front`가 682점으로 1등이고 정답은 3점이다. 물리 좌표로 훑으면 정답이 682다.
#    기준이 `side=back`을 선언한 맵도 같다(`rot270_back` 682 대 정답 22). 어긋남의 크기는
#    정확히 **기준 자신의 프레임**이다. 순번은 기준에 대한 진술이 아니라 정준 방위에 대한
#    진술이므로, 기준의 프레임이 답에 섞이면 안 된다.


def serpentine_index(cells, top_is_min_y: bool = True) -> dict:
    """유효 다이 집합 → `{순번: (x, y)}`. 1부터. **phys도 메타도 안 읽는다.**

    규칙은 셋이고 **셋 다 명시적으로 고정한다** — 하나라도 암묵이면 그 축에서 조용히 틀린다:

    ① **행 순서**: 맨 위 행부터. `top_is_min_y`면 y가 작은 행이 먼저다. 채점기는 물리
       좌표계에서 훑으므로 언제나 True를 넘긴다(§위 주석: 좌표계의 성질이지 설정이 아니다).
    ② **방향 교대**: 첫 행은 왼→오, 다음 행은 오→왼. 교대는 **셀이 있는 행에서만** 일어난다
       (통째로 빈 행은 방문하지 않았으므로 방향을 뒤집지 않는다). 실측(2026-08-05) 이 DB의
       유효 다이 바닥 다섯 장(`CORE/YINV` 927 · `CORE/1X` 854 · `TEST/TEST` 425 ·
       `5N/BASE` 425 · `PRD-A/DT13` 88) 전부 y 범위 안에 **빈 행이 없어** 「격자 행마다
       교대」와 결과가 한 자도 다르지 않다. 원판에는 빈 내부 행이 없으므로 실무에서 이 선택은
       드러나지 않지만, **드러나지 않는 것과 선언하지 않아도 되는 것은 다르다**.
    ③ **행 안의 빈칸은 건너뛴다 — 번호를 먹지 않는다.** 순번은 격자 칸이 아니라 **다이**에
       매겨졌다. 이 규칙은 ②와 달리 **실제로 문다**: 같은 실측에서 `TEST/TEST` 바닥은 행
       안쪽에 구멍이 있는 행을 2개 갖는다. 구멍이 번호를 먹게 두면 그 행 이후 전부가 밀린다.

    반환은 `{index: (x, y)}`다 — 앵커가 「1번이 어디여야 하나」를 그대로 묻는다.
    역방향(좌표→순번)이 필요한 자리는 `serpentine_rank`가 답한다.
    """
    present = {}
    for (x, y) in (cells or ()):
        present.setdefault(int(y), set()).add(int(x))
    rows = sorted(present.keys(), reverse=not top_is_min_y)
    out, i = {}, 1
    for r, y in enumerate(rows):
        # ③ 이 행에 **있는** x만. 없는 칸은 목록에 없으므로 번호를 받지 않는다.
        for x in sorted(present[y], reverse=(r % 2 == 1)):
            out[i] = (x, y)
            i += 1
    return out


def serpentine_rank(cells, top_is_min_y: bool = True) -> dict:
    """같은 훑기의 **역**: `{(x, y): 순번}`. 새 채점이 묻는 방향이 이쪽이다.

    🔴 훑기를 두 번 구현하지 않는다 — `serpentine_index`를 뒤집는다. 순서 규칙이 두 곳에
       살면 둘이 갈리는 날 화면은 멀쩡하고 번호만 틀린다(이 파일이 반복해서 막는 「하나의
       사실에 두 철자」의 계열).

    좌표가 중복되면 **먼저 훑힌 번호가 남는다** — 같은 자리에 두 번 서는 일은 훑기에
    없으므로 중복은 입력의 사실이고, 임의로 고르면 같은 입력이 실행마다 다른 답을 낸다.
    """
    out = {}
    for k, xy in serpentine_index(cells, top_is_min_y=top_is_min_y).items():
        out.setdefault(xy, k)
    return out


#: 앵커가 **왜 안 걸렸는가**. 「안 걸렸다」 하나로 접으면 조작자가 고칠 곳을 못 찾는다 —
#: 순번 컬럼을 선언하는 것과, 단위를 맵 하나로 좁히는 것과, 중복 번호를 고치는 것은
#: 서로 다른 수리다. `None`이면 걸렸다는 뜻이다.
ANCHOR_NO_INDEX = "no_index_values"            # 번호를 실은 셀이 없다
ANCHOR_NO_REFERENCE = "no_reference_cells"     # 기준에 좌상단이라 부를 셀이 없다
ANCHOR_MULTI_MAP = "multiple_source_maps"      # 맵마다 자기 1번이 있어 앵커가 여럿이다
ANCHOR_MIN_NOT_UNIQUE = "minimum_index_not_unique"   # 최소 순번이 두 셀 이상에 있다
ANCHOR_DISABLED = "disabled"                   # 스위치가 꺼져 있다(§ANCHOR_PLACEMENT_ENABLED)

#: 앵커가 **걸리기는 했는데 과녁이 틀렸다**. 앵커의 전제(「이 작업은 웨이퍼 좌상단 다이부터
#: 돌았다」)가 거짓인 작업에서 잔차가 0이 아니고, 그 사실은 위 사유 다섯 중 어느 것도 아니다 -
#: 앵커는 정상적으로 걸렸다. 이름이 없으면 조작자는 「밀렸다」를 눈으로 알아내야 하고,
#: 실제로 그렇게 알아냈다(제품 소유자 2026-08-06: 「shift를 무조건 0,0으로 계산함」).
ANCHOR_SEAT_CORRECTED = "anchor_seat_corrected"

# ═══ 잔차 탐색의 **결과 상태** — `(0,0)`이 네 가지 뜻을 갖고 있었다 (2026-08-06) ═══════════
#
# 🔴 제품 소유자: 「근본적으로 서버가 잘못된 계산을 하고 있음 (shift 0,0 또는 최적이 아닌 값)」.
#    「시프트가 0,0이다」는 **조작자가 행동할 수 있는 증상이 아니었다** — `_residual_shift`가
#    `(0,0)`을 내는 경로가 넷이고 로그가 그 넷을 구별하지 못했기 때문이다:
#      ① 앵커 자리가 **유일하게 자격을 얻었다** — 앵커의 전제가 참이고 옮길 것이 없다(정상)
#      ② 자격 자리가 **하나도 없다** — 옮길 근거가 없어 포기했다
#      ③ 자격 자리가 **둘 이상**이라 데이터가 고르지 못했다
#      ④ 훑기 번호가 없어 **물을 수조차 없었다**
#    ①과 ②는 반환값이 `(0,0,n)` vs `(0,0,0)`로 달랐지만 **호출자가 세 번째 값을 버렸다**
#    (`rdx, rdy, _hit = _residual_shift(...)`), 그리고 진단 줄은 잔차가 **움직였을 때만**
#    찍혔다(§_diag_scoring_block) — 그래서 포기는 아무 소리도 내지 않았다.
#
# 🔴 실측이 그 침묵의 크기를 준다(바닥 677다이 · 부분 작업 240셀 · 훑기 #43부터):
#    후보 `rot90_back`은 **점유 240/240을 내는 자리가 5개** 있는데 자격 ②가 그 다섯을 전부
#    떨어뜨려 `(0,0)`에 남았고, 거기서의 점유는 **134/240**이었다. 화면에는 「시프트 0,0」만
#    나갔다.
#
# ⚠️ **이름을 붙이는 것이지 판정을 바꾸는 것이 아니다.** 자격 셋은 한 글자도 안 바뀐다 —
#    무엇이 일어났는지 말할 수 있게 된 것뿐이고, 그것이 이 라운드가 산 전부다.
RESIDUAL_ANCHOR_HELD = "anchor_seat_held"              # ① 앵커 자리가 유일한 자격 자리였다
RESIDUAL_NO_QUALIFYING_SEAT = "no_qualifying_seat"     # ② 자격 자리 0개 - 근거 없어 안 옮김
RESIDUAL_NOT_UNIQUE = "qualifying_seat_not_unique"     # ③ 자격 자리 2개 이상 - 안 옮김
RESIDUAL_NO_WALK_RANKS = "no_walk_ranks"               # ④ 물을 수 없었다
RESIDUAL_SEAT_CAP = "seat_cap_reached"                 # 상한에 걸려 다 못 봤다(§_RESIDUAL_SEAT_CAP)

#: `ruling.placement` — 평행이동을 **누가 정했는가**. 판정 dict 자신이 나른다:
#: 앵커로 놓인 배치와 탐색으로 놓인 배치는 다른 주장이고, 판정을 옮겨 적는 자리(확정
#: 기록·목록)가 옆 필드를 흘리면 그 구별이 사라진다 — `geometry_assumed`·`metric`과 같은 이유.
PLACEMENT_ANCHOR = "anchor"      # 최소 순번 다이 → 기준 좌상단. 데이터가 정했다
PLACEMENT_SEARCH = "shift_search"  # 겹침 최대화 탐색. 포화하면 동점 규칙이 정한다

#: 🔴 앵커를 통째로 끄는 **단 하나의 스위치**. 총괄이 「점유·값 축까지 앵커로 바꾸는 것은
#:    더 큰 변경이니 몰래 접지 말라」고 못 박았으므로, 되돌림이 한 줄이어야 한다.
#:    False로 두면 순번이 있든 없든 종전 시프트 탐색만 돈다(순번 축은 영향 없음 — 그 축은
#:    평행이동에 불변이다).
ANCHOR_PLACEMENT_ENABLED = True


def _normalised_indices(source_indices, cell_owner):
    """저장된 순번 → **맵마다 1부터 다시 시작하는** 정수 배열 + 「번호가 있는가」 진리값.

    `0..255`와 `1..266`이 둘 다 실재하므로 **관측된 최솟값을 1로** 옮긴다 — 절대값은
    아무것도 나르지 않고 순서가 신호 전부다(제품 소유자 확정 2026-08-06).

    base는 **맵마다** 잡는다. 한 단위에 base가 다른 두 맵이 있으면 전역 최솟값으로
    맞추는 순간 한쪽이 통째로 밀리고, 그 오답은 개수로 안 잡힌다.

    반환 `(idx_k, idx_has, bases)`. 번호를 실은 셀이 하나도 없으면 `(None, None, {})` -
    **없음을 0으로 접지 않는다**(§[3a]).
    """
    import numpy as np
    if not source_indices or not any(k is not None for k in source_indices):
        return None, None, {}
    owner = cell_owner or [0] * len(source_indices)
    raw, flags = [], []
    for k in source_indices:
        try:
            raw.append(None if k is None else int(k))
        except (TypeError, ValueError):
            raw.append(None)
        flags.append(raw[-1] is not None)
    bases = {}
    for i, k in enumerate(raw):
        if k is None:
            continue
        m = owner[i] if i < len(owner) else 0
        bases[m] = k if m not in bases else min(bases[m], k)
    out = [0] * len(raw)
    for i, k in enumerate(raw):
        if k is None:
            continue
        m = owner[i] if i < len(owner) else 0
        out[i] = k - bases[m] + 1
    return np.array(out, dtype="int64"), np.array(flags, dtype=bool), bases


def _index_member(phys, cell_owner, idx_k, idx_has):
    """셀마다 「이 셀이 훑기에서 몇 번째인가 == 저장된 순번인가」.

    훑기는 **맵 단위**로, **그 맵의 셀 전부**를 대상으로 돈다.

    🔴 번호가 없는 셀도 **훑기에는 들어간다.** 순번은 작업이 건드린 다이 집합에 매겨졌고,
       번호 칸이 빈 행도 그 작업이 건드린 다이다 - 빼면 그 뒤 셀이 전부 한 칸씩 당겨져
       번호가 통째로 밀린다(§serpentine_index ③이 격자 구멍에 대해 말하는 것과 같은 계열,
       한 층 위). 채점은 번호가 있는 셀에서만 한다.
    """
    import numpy as np
    hits = np.zeros(len(phys), dtype=bool)
    owner = cell_owner or [0] * len(phys)
    by_map = {}
    for i in range(len(phys)):
        by_map.setdefault(owner[i] if i < len(owner) else 0, []).append(i)
    for rows in by_map.values():
        # 물리(정준) 좌표계에서 훑는다 → 맨 위는 언제나 가장 작은 y(§순번 주석).
        rank = serpentine_rank([phys[i] for i in rows], top_is_min_y=True)
        for i in rows:
            if idx_has[i] and rank.get(tuple(phys[i])) == int(idx_k[i]):
                hits[i] = True
    return hits


def direction_judge(ref_phys):
    """기준 바닥(정준 좌표) → 서펜타인의 **규칙 자체**: 행 방향과 행 범위.

    🔴 **판사는 기준이지 소스가 아니다**(제품 소유자 2026-08-06). 실측이 그 이유를 준다:
       가로로 붙은 두 셀만 있는 소스에서, 1번은 바닥 행 y=20의 x=20에 앉고 **그 행에는
       오른쪽으로 20개가 더 남아 있다**. 소스 자신의 범위로 판정하면 「행이 한 칸 만에
       끝났다」가 되어 아래로 내려가는 것이 정당해 보이고, 그래서 회전된 프레임이 정답과
       구별되지 않는다. 바닥에 남은 20개가 그 내려감을 **불법으로** 만든다.

    반환 `(rows, dir_of, next_row)` — 행별 x 집합 · 행별 진행 방향(+1 오른쪽 / -1 왼쪽) ·
    그 행 다음에 오는 행. 방향은 `serpentine_index`의 ②와 **같은 규칙**(행마다 교대)이고,
    첫 행이 왼→오인 것도 같다 — 두 곳이 갈리면 훑기와 방향 검사가 서로를 부정한다.
    """
    rows = {}
    for (x, y) in (ref_phys or ()):
        rows.setdefault(int(y), set()).add(int(x))
    order = sorted(rows)                       # 정준 좌표계에서 가장 작은 y가 맨 위
    dir_of = {y: (1 if i % 2 == 0 else -1) for i, y in enumerate(order)}
    next_row = {y: (order[i + 1] if i + 1 < len(order) else None)
                for i, y in enumerate(order)}
    return rows, dir_of, next_row


def direction_violations(phys, cell_owner, idx_k, idx_has, judge):
    """연속한 순번 사이의 걸음 중 **서펜타인을 벗어난 것**의 수 → `(위반수, 잰 걸음수)`.

    ═══ 왜 이 축이 필요한가 (실측 2026-08-06) ═══════════════════════════════════════════
    훑기 순서 일치(`index_agreement`)는 **순서만** 본다. 셀이 둘뿐이면 여덟 프레임 중 넷이
    같은 순서를 만들 수 있고, 실제로 그렇다 — 가로 쌍에서 `rot0_front`·`rot180_back`·
    `rot270_front`·`rot270_back`이 **전부 2/2로 동점**이고 판정은 `tie`, 승자 없음이었다.
    걸음의 **방향**은 그 넷을 가른다: 1번에서 2번으로 가는 걸음이 오른쪽인지 아래인지는
    프레임마다 다르고, 바닥이 그중 무엇이 합법인지 안다.

    ═══ 규칙 ══════════════════════════════════════════════════════════════════════════
    ① **같은 행 안**: 걸음의 부호가 그 행의 방향과 같아야 한다.
    ② **행을 바꿈(wrap)**: 두 조건이 **둘 다** 참일 때만 합법이다 —
         · 진행 방향으로 그 행에 **바닥의 다이가 더 남아 있지 않다**(안 남았으면 행이 끝났다), 그리고
         · 옮겨 간 행이 바닥 기준 **바로 다음 행**이다.
    ③ **거리는 세지 않는다, 방향만 센다.** 실측: 같은 행에서 `+4` 건너뛴 걸음도 방향은
       오른쪽이다. 부분 맵의 구멍은 위반이 아니며, 거리를 세면 이 기능이 존재하는 유일한
       모집단(부분 맵)이 통째로 위반 덩어리가 된다.
    ④ **바닥 밖 셀은 판정하지 않는다** — 거기서 행 방향을 물을 수 없다. 그 셀의 문제는
       점유 축이 이미 센다. 세면 같은 사실을 두 축에서 두 번 벌하는 것이다.

    🔴 **작을수록 좋다.** 이 파일의 다른 지표는 전부 클수록 좋으므로, 이 수를 저쪽 문턱에
       섞으면 같은 이름이 반대 방향을 뜻하게 된다(`map_overlay_config.json`이 이미 그 경고를
       적어 두었다: 위반 지표는 자기 선언을 따로 갖는다).
    """
    rows, dir_of, next_row = judge
    if not rows or idx_has is None:
        return None, 0
    owner = cell_owner or [0] * len(phys)
    per_map = {}
    for i in range(len(phys)):
        if i < idx_has.size and idx_has[i]:
            per_map.setdefault(owner[i] if i < len(owner) else 0, []).append(
                (int(idx_k[i]), i))
    bad = steps = 0
    for lst in per_map.values():
        lst.sort()
        for (_ka, ia), (_kb, ib) in zip(lst, lst[1:]):
            ax, ay = int(phys[ia][0]), int(phys[ia][1])
            bx, by = int(phys[ib][0]), int(phys[ib][1])
            if ay not in dir_of:               # ④ 바닥 밖 - 판정하지 않는다
                continue
            steps += 1
            d = dir_of[ay]
            if ay == by:                       # ① 같은 행
                if (bx - ax) * d <= 0:
                    bad += 1
                continue
            # ② 행 바꿈
            left_in_row = any((x > ax) if d > 0 else (x < ax) for x in rows[ay])
            if left_in_row or by != next_row.get(ay):
                bad += 1
    return bad, steps


#: 정준 방위를 정의하는 축 셋. `frame_linear_part`는 축만 읽으므로 이 세 키면 충분하다 —
#: phys도 격자도 필요 없다는 것이 [D11]의 요점이다.
_CANONICAL_AXES = {"rotation": 0, "side": "front", "grid_y_invert": False}


def anchor_cell_of(usable):
    """배치의 기준점이 될 **소스 셀 하나** → `(맵 첨자, (x, y))`. 없으면 None.

    최소 순번을 가진 셀이고, 규칙은 `_anchor_shift`와 **같다**(맵 하나 · 최소가 유일).
    다른 점은 시점뿐이다: 저쪽은 배치가 끝난 뒤 평행이동을 재고, 이쪽은 배치가 **시작되기
    전에** 기준점을 고른다 — 차분으로 놓으려면 기준점이 먼저 있어야 하기 때문이다.
    """
    best = None
    maps_seen = set()
    for mi, sm in enumerate(usable or ()):
        ks = sm.get("_use_indices") or []
        for i, k in enumerate(ks):
            if k is None:
                continue
            try:
                kv = int(k)
            except (TypeError, ValueError):
                continue
            maps_seen.add(mi)
            if best is None or kv < best[0]:
                best = (kv, mi, i, tuple(sm["_use"][i]))
            elif kv == best[0]:
                best = (kv, None, None, None)      # 최소가 유일하지 않다
    if best is None or best[1] is None or len(maps_seen) > 1:
        return None
    return best[1], best[3]


# ═══ 🔴 앵커 평행이동의 두 철자 — 재 봤고, 한쪽은 못 쓴다 (실측 2026-08-06) ══════════════
# 소유자 문언: 「점수 내기 시에는 shift는 t = (anchor_ref − anchor_src), 앵커는 그냥 db좌표
# 그대로」. 이 문장은 두 가지로 읽히고 **둘은 같은 수가 아니다**:
#
#   RAW    `t = anchor_ref − anchor_src`  — 소스 앵커를 **소스 자신의 저장 좌표**로 읽어 뺀다.
#   SEATED `t = anchor_ref − tf(anchor_src)` — 소스 앵커가 **기준 공간에 놓인 자리**를 뺀다.
#          `tf`의 값도 mm가 아니라 저장 좌표이므로 이쪽도 「db좌표 그대로」다. `ec8c0e7`의 식.
#
# 실측(바닥 41x41/300mm 유효다이 · 작업 266셀 · 심은 프레임을 정답으로):
#                                   RAW                      SEATED
#   ① 작업이 웨이퍼 좌상단부터   정답 프레임 점유 **0**      정답 266, 차점 186
#      (심은 rot90_front)        오답이 147·162로 이긴다      여덟이 8개 값으로 갈린다
#   ② 작업이 웨이퍼 중간부터     정답 184, 오답 최고 219     정답 141, 오답 최고 225
#      (start=400)              (정답이 최하위)              (점수가 나빠질 수 있고 축이 어긋난다)
#   ③ 심은 프레임 = rot0_front   **여덟 전부 266 — 동점**    266 대 186, 여덟이 다 다르다
#
# 🔴 RAW는 **공간을 섞는다**: 소스의 저장 공간에서 잰 평행이동을 회전이 끝난 기준 공간의
#    좌표에 더한다. 이 파일은 같은 형태의 식을 이미 한 번 재고 폐기했다 —
#    `start_from_placement` §②(`t = anchor_ref − L·anchor_src`, 32조합 중 0). 그리고 ③은
#    앵커를 도입해 없앤 바로 그 포화다. 그래서 기본값은 SEATED이고, RAW는 총괄이 다시
#    판정할 때 한 줄로 켤 수 있게 스위치로 남긴다.
_ANCHOR_SHIFT_RAW = False


def _anchor_shift(per_candidate, source_indices, cell_owner, reference_top_left,
                  anchor_cell=None):
    """앵커 쌍이 정하는 평행이동 → `({프레임: (dx,dy)}, 사유)`.

    제품 소유자 확정 2026-08-06: 「소스 조각 좌상단이 기준맵 좌상단 되게 하는게 어려움?」 —
    최소 순번 다이는 DT 장비가 **처음 건드린** 다이이고 장비는 유효 다이 영역의 좌상단부터
    시작한다. 그래서 평행이동은 **푸는 값이 아니라 읽는 값**이다.

    ═══ 🔴 값의 정의 (제품 소유자 확정 2026-08-06) ═══════════════════════════════════════════
    「점수 내기 시에는 shift는 t = (anchor_ref − anchor_src), 앵커는 그냥 db좌표 그대로」.
    **두 앵커를 저장 좌표 그대로 읽어 뺀다** — 변환도 mm도 박스도 타지 않는다. 그래서 이 값은
    후보 프레임에 의존하지 않고 여덟이 같은 평행이동을 받는다. 가르는 일은 배치(`tf`)가 한다.

    🔴 종전 식은 `reference_top_left − placed[i_min]`이었고, 배치가 앵커를 미리 구워
       넣은 뒤로 그 뺄셈에는 **뺄 것이 남지 않았다**(항등적으로 `(0,0)`). 그것이 조작자가
       본 「shift 0,0 고정」이고, 동시에 「앵커가 앉힌 자리를 채점해서 늘 만점」이었다.
       배치를 변환 전용으로 되돌리면서 이 식도 소유자의 정의로 되돌린다.

    🔴 걸리지 않는 경우를 **이름으로** 낸다. 앵커가 없다는 사실은 화면이 「탐색으로 놓았다」를
       말하기 위해 필요하고, 사유마다 수리가 다르다(§ANCHOR_*).

    🔴 **맵이 둘 이상이면 걸지 않는다.** 순번은 맵마다 1부터 다시 시작하므로 최소 순번 다이가
       맵 수만큼 있고, 그중 하나를 고르는 규칙은 데이터에 없다 — 지어내면 그것이 두 번째
       임의 배치이고, 이 변경이 없애려는 바로 그것이다.
    """
    if not ANCHOR_PLACEMENT_ENABLED:
        return None, ANCHOR_DISABLED
    if reference_top_left is None:
        return None, ANCHOR_NO_REFERENCE
    if not source_indices or not any(k is not None for k in source_indices):
        return None, ANCHOR_NO_INDEX
    owner = cell_owner or [0] * len(source_indices)
    if len({owner[i] for i in range(len(source_indices))
            if source_indices[i] is not None}) > 1:
        return None, ANCHOR_MULTI_MAP
    numbered = []
    for i, k in enumerate(source_indices):
        if k is None:
            continue
        try:
            numbered.append((int(k), i))
        except (TypeError, ValueError):
            continue
    if not numbered:
        return None, ANCHOR_NO_INDEX
    lowest = min(k for k, _ in numbered)
    at = [i for k, i in numbered if k == lowest]
    if len(at) != 1:
        return None, ANCHOR_MIN_NOT_UNIQUE
    i_min = at[0]
    # 앵커 셀의 **저장 좌표**. 호출자가 `anchor_cell_of`로 이미 고른 것을 넘겨 주고, 규칙이
    # 같으므로 여기 `i_min`과 같은 셀이다 — 그래도 넘어오지 않으면 걸지 않는다(§ANCHOR_*).
    if anchor_cell is None:
        return None, ANCHOR_NO_INDEX
    raw_t = (int(reference_top_left[0]) - int(anchor_cell[0]),
             int(reference_top_left[1]) - int(anchor_cell[1]))
    out = {}
    for c in per_candidate:
        placed = c.get("_placed")
        if not placed or i_min >= len(placed):
            # 이 후보는 좌표를 못 놓았다 - 아래 루프가 `scored=False`로 걸러낸다.
            out[c["frame"]] = (0, 0)
            continue
        out[c["frame"]] = (raw_t if _ANCHOR_SHIFT_RAW else
                           (int(reference_top_left[0]) - int(placed[i_min][0]),
                            int(reference_top_left[1]) - int(placed[i_min][1])))
    return out, None


# ---------------------------------------------------------------------------
# 값 비교 — **철자가 아니라 값을 견준다**
# ---------------------------------------------------------------------------
# 🔴 종전 규칙은 `str(rv) == str(sv)`였고, 라이브에서 그 엄격함이 통째로 물었다(제품 소유자
#    데이터 2026-08-06: 진단 추적이 `compare 2.0 vs '1'`을 찍었다 — 소스 값은 **float**로,
#    기준 값은 문자열로 도착한다). 그러면 **같은 뜻인데 철자가 다른** 자리가 전부 MISS이고,
#    화면에는 「값 일치 0건」이 뜬다. 기하가 멀쩡한데 기하 실패로 읽히는 그 증상이다.
#
# 규칙은 둘이고 **어느 쪽이 발화했는지 진단이 말한다**(§_diag_compare_probe):
#   ① 양쪽이 **평범한 십진수**로 읽히면 수로 견준다 → `2.0` == `'2'` == `2` == `'02'`.
#   ② 아니면 **양끝 공백을 떼고 대소문자를 접어** 문자열로 견준다 → `'B1 '` == `'b1'`.
#
# 🔴 「평범한 십진수」는 `float()`가 받는 것보다 **좁다**. `float('1E1')`은 10.0이고
#    `float('nan')`은 NaN인데, `1E1`은 bin 코드로 실재할 수 있는 철자이고 NaN은 자기 자신과
#    같지 않다. `float()`를 그대로 쓰면 값 어휘가 조용히 넓어져 **다음 라운드의 미스터리**가
#    된다 — 총괄 지시: 「말없이 넓히지 말 것」. 그래서 수용기는 정규식이고, 지수 표기·
#    `nan`·`inf`는 문자열로 남는다.
_PLAIN_NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)$")

#: `ruling.value_axis` — 값 축이 **이 판정에서 무엇을 했는가**. `index_axis`와 같은 어휘이고
#: 같은 이유로 판정 dict 자신이 나른다. 「쟀는데 순위를 안 냈다」는 조작자에게 필요한 사실이다:
#: 후보 행에는 값 수치가 실려 나가므로, 이 사실이 없으면 화면은 그 수치가 판정을 만들었다고 읽는다.
VALUE_AXIS_RANKING = "ranking"
VALUE_AXIS_REPORTED = "reported"
VALUE_AXIS_ABSENT = "absent"

#: 값 축이 **순위를 못 가져간 이유**. 둘 다 종전에는 `no_overlap`이라는 같은 낱말로 나왔고,
#: 그 낱말은 조작자를 좌표를 고치러 보낸다 — 고칠 것은 값 컬럼 쪽이었다.
VALUE_AXIS_REF_ALL_NULL = "reference_values_all_null"
VALUE_AXIS_DISJOINT = "vocabularies_disjoint"

_VALUE_AXIS_REASON_TEXT = {
    VALUE_AXIS_REF_ALL_NULL: "기준 값 컬럼 전부 NULL - 값 축 순위 제외, 점유로 판정",
    VALUE_AXIS_DISJOINT: "기준·소스 값 어휘 교집합 0 - 값 축 순위 제외, 점유로 판정",
}


def _value_key(v):
    """비교용 정규화 키. `None`은 키가 없다 — 비교 자체가 성립하지 않는다(§values_equal)."""
    if v is None:
        return None
    s = str(v).strip()
    if _PLAIN_NUMBER.match(s):
        return ("n", float(s))
    return ("t", s.casefold())


def values_equal(a, b) -> bool:
    """기준 값과 소스 값이 **같은 것을 뜻하는가**. `None`은 어느 쪽도 못 맞힌다.

    🔴 `None == None`을 참으로 두지 않는다. 「양쪽 다 값이 없다」는 일치가 아니라 **잴 것이
       없었다**이고, 참으로 세면 값이 비어 있는 맵이 여덟 후보에서 만점을 받는다.
    """
    if a is None or b is None:
        return False
    return _value_key(a) == _value_key(b)


# ---------------------------------------------------------------------------
# Scoring diagnostics — one block per scoring run, console **and** align.log
# ---------------------------------------------------------------------------
# This whole section is observability. It reads what the scorer used and prints
# it; it decides nothing. Every value below is either read out of a structure the
# scorer built, or captured at the exact line the scorer used it. Nothing here
# re-derives a scoring answer — a logging path that recomputes can disagree with
# the code it describes, and then there are two implementations to debug.
#
# [why this exists] The operator sat for a day on `metric=values` /
# `reason=no_overlap` / rank: none, and the payload could not tell apart the two
# causes that produce it:
#
#   POSITIONAL  — source cells and reference cells never land on the same
#                 coordinate under any of the eight frames. Geometry is wrong.
#   VOCABULARY  — the cells DO overlap and **no value is equal**, because the
#                 reference's values and the source's are different vocabularies
#                 (a valid-die floor carrying 1/0 against bin codes 3/7). The
#                 geometry is fine and nothing about it needs touching.
#
# Both print as "no overlap". Separating them is the first job of this block:
# every candidate reports positional overlap and value agreement as two
# independent counts, and a single DIAGNOSIS line names which one is at work.
#
# [both destinations, always] Console so the operator can watch a run live;
# `align.log` so they can scroll back after the terminal has scrolled. No flag,
# no config key, no environment variable — one behaviour.
#
# [never fatal] Every entry point here swallows its own failures. A diagnostic
# that can take down the feature it diagnoses is worse than no diagnostic.

#: Next to the process logs (`server/server.log`, `server/watcher.log`), through
#: the same single override point, so an isolated stack cannot append to the
#: user's live file. That directory is where a person already looks for logs, and
#: the web server has proven it writable by keeping its own log there.
_DIAG_LOG_FILENAME = "align.log"
#: 🔴 A test process must not append to the operator's live file. `paths.log_path`
#: already states the discipline for the process logs ("the file a reviewer reads
#: to reconstruct an incident must not carry a drill's lines") and the suite calls
#: `build_alignment_view` directly, so without this the first thing the operator
#: would open contains dozens of synthetic blocks. Detection reuses the existing
#: primitive (`db_safety.under_pytest`) rather than adding a second spelling —
#: and the handler is still exercised, just against a different name.
_DIAG_LOG_FILENAME_TEST = "align_test.log"
#: Bounded on purpose, and the file says at the cut what it dropped
#: (`_RollNoticeHandler`). Two generations survive: the live file and one backup,
#: i.e. at most ~16 MB. Anything older than the backup is gone for good.
_DIAG_MAX_BYTES = 8 * 1024 * 1024
_DIAG_BACKUPS = 1

_DIAG_SAMPLE_VALUES = 10        # distinct values shown per vocabulary
_DIAG_VOCAB_DISTINCT_CAP = 500  # distinct values tracked before we stop counting
_DIAG_VOCAB_SCAN_CAP = 50_000   # values scanned when taking a census
_DIAG_TRACE_CELLS = 5           # worked-example cells per traced candidate
_DIAG_MAP_LINES = 10            # per-map lines before the tail is summarised
_DIAG_CHARS = 48                # one rendered value never exceeds this
_DIAG_CHARS_LONG = 900          # one rendered structure never exceeds this

_DIAG_RULE = "=" * 78

#: 이 프로세스가 살아난 시각의 대리값. 모듈 import는 프로세스 기동 직후에 일어나므로,
#: 「지금 도는 코드가 언제 올라왔나」에 답하기엔 충분하고 추가 의존성이 없다.
_PROCESS_UP_SINCE = time.time()
_BUILD_IDENTITY_CACHE = None


def _git_sha() -> str | None:
    """배포가 체크아웃을 기록해 두었으면 그 sha. 아니면 None.

    🔴 **없으면 지어내지 않는다.** 틀린 sha는 없는 sha보다 나쁘다 — 읽는 사람이 그것을
       changelog에 대조하고, 맞는 것처럼 보이는 답을 얻는다. `.git`이 없는 배포는 실재하고
       (아카이브 추출·컨테이너 COPY), 그때는 이 함수가 None을 돌려주고 아래 문장이
       「기록되지 않은 체크아웃」이라고 **사실대로** 말한다.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):                       # server/ → repo root 정도까지만 올라간다
        head = os.path.join(here, ".git", "HEAD")
        try:
            with open(head, "r", encoding="utf-8") as f:
                ref = f.read().strip()
        except OSError:
            here = os.path.dirname(here)
            continue
        if ref.startswith("ref:"):
            path = os.path.join(here, ".git", *ref[4:].strip().split("/"))
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()[:12]
            except OSError:
                return None
        return ref[:12] if ref else None
    return None


def _feature_tokens() -> list:
    """이 빌드가 **실제로 가진** 기능의 이름들.

    🔴 손으로 관리하는 버전 문자열을 만들지 않는다 — 올릴 것을 잊는 순간 거짓말이 되고,
       거짓말하는 버전 문자열은 없는 것보다 나쁘다. 대신 **그 기능을 구현하는 심볼이
       존재하는가**를 묻는다. 심볼이 곧 기능이므로 잊을 수가 없다: 기능을 지우면 토큰이
       같이 사라지고, 기능을 넣으면 토큰이 같이 생긴다.
    """
    out = []
    g = globals()
    if "serpentine_rank" in g and hasattr(map_overlay, "make_physical_transform"):
        out.append("canonical-walk")          # 훑기가 정준 좌표계에서 돈다
    if "_anchor_shift" in g:
        out.append("anchor")                  # 최소 순번 다이로 배치를 결정한다
    if "direction_violations" in g:
        out.append("direction")               # 걸음의 방향으로 동점을 가른다
    if "start_for_placement" in g:
        out.append("confirmed-origin")        # 확정이 원점을 기록한다
    if hasattr(map_overlay, "frame_linear_part"):
        out.append("linear-part")             # 배치의 선형부를 phys 없이 만든다
    # 🔴 상수는 **중첩돼 있다.** dict 리터럴의 키들은 CPython에서 개별 문자열이 아니라
    #    **키 튜플 하나**로 접혀 들어가는 경우가 있어서, 평평하게 `in co_consts`로 물으면
    #    있는 기능을 없다고 답한다(첫 구현이 정확히 그랬다 — 기능은 있는데 토큰이 안 찍혔다).
    #    거짓 음성도 거짓 양성만큼 나쁘다: 읽는 사람이 없는 결함을 찾으러 간다.
    def _has_const(code, needle, depth=0):
        if depth > 3:
            return False
        for k in getattr(code, "co_consts", ()):
            if k == needle:
                return True
            if isinstance(k, tuple) and needle in k:
                return True
            if hasattr(k, "co_consts") and _has_const(k, needle, depth + 1):
                return True
        return False

    try:
        if _has_const(build_alignment_view.__code__, "cell_index"):
            out.append("cell-index-field")    # payload가 셀별 순번을 싣는다
    except Exception:
        pass
    return out


def build_identity() -> str:
    """이 프로세스가 **무엇인지** 한 줄로. 증상에서 유추하지 않아도 되게 한다.

    ═══ 왜 이것이 있는가 (2026-08-06) ═══════════════════════════════════════════════════
    「이 서버에 그 코드가 들어 있나」가 이 스레드에서 여러 라운드를 먹었고, 증상으로
    유추한 답은 **매번 틀렸다**. 그리고 오늘 두 레인이 각각 **커밋보다 여섯 시간 오래된
    프로세스**를 읽고 배포된 코드의 결함이라고 판단했다. 프로세스가 자기 신원을 말하면
    그 질문이 영구히 사라진다 — 지금 읽는 사람에게도, 다음 달에 디버깅할 사람에게도.

    sha를 모르면 **모른다고 적는다**(§_git_sha).
    """
    global _BUILD_IDENTITY_CACHE
    if _BUILD_IDENTITY_CACHE is None:
        sha = _git_sha()
        try:
            mtime = time.strftime("%Y-%m-%d %H:%M:%S",
                                  time.localtime(os.path.getmtime(os.path.abspath(__file__))))
        except OSError:
            mtime = "unknown"
        up = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_PROCESS_UP_SINCE))
        who = ("commit %s" % sha if sha
               else "built from an unrecorded checkout (no .git reachable)")
        _BUILD_IDENTITY_CACHE = (
            "build: %s | map_alignment.py modified %s | process up since %s | features: %s"
            % (who, mtime, up, ",".join(_feature_tokens()) or "<none>"))
    return _BUILD_IDENTITY_CACHE


def _d(v, cap: int = _DIAG_CHARS) -> str:
    """One value, rendered and length-capped.

    `repr()` and not `str()`, deliberately: **the vocabulary question turns on
    type and whitespace, and `str()` erases both.** `3`, `'3'`, `' 3 '` and
    `'3\\n'` all print as `3` under `str()` — exactly the class of mismatch this
    log exists to make visible. `repr()` keeps the quotes, so a string is
    distinguishable from a number and a trailing space is visible inside them,
    and it escapes control characters.

    Not `ascii()`: it escapes Korean to `\\uXXXX` and the operator-facing halves
    of this block (refusals, config comments, refusal reasons) become unreadable.
    Printable non-ASCII therefore survives as itself; where that could hide a
    difference — a full-width space in a *value* — `_d_vocab_text` prints the
    escaped spelling alongside. The console half survives a cp949 terminal
    through `_ConsoleSafeHandler`, not through escaping everything.
    """
    try:
        s = repr(v)
    except Exception:
        try:
            s = ascii(v)
        except Exception:
            s = "<unrenderable %s>" % type(v).__name__
    return s if len(s) <= cap else s[:cap - 3] + "..."


def _d_config(v, cap: int = _DIAG_CHARS_LONG) -> str:
    """A config block as found in the file, with `__`-prefixed comment keys
    elided. The convention is the file's own (`load_alignment_value_weights`
    skips them); eliding them here keeps the *declarations* inside the character
    budget instead of letting one long comment push them past the cut."""
    if isinstance(v, dict):
        kept = {k: (_strip_comments(x) if isinstance(x, dict) else x)
                for k, x in v.items() if not str(k).startswith("__")}
        note = "" if len(kept) == len(v) else "   (__comment keys elided)"
        return _d(kept, cap) + note
    return _d(v, cap)


def _strip_comments(d: dict) -> dict:
    return {k: x for k, x in d.items() if not str(k).startswith("__")}


def _d_arg(v) -> str:
    """A request argument. **Absent is a value here** — half of this week's
    defects were an undeclared thing folding silently into a default, so `None`
    prints as `<absent>` and an empty string prints as the explicit "none" that
    `resolve_source_columns` treats it as."""
    if v is None:
        return "<absent>"
    if isinstance(v, str) and not v.strip():
        return "'' <explicit none>"
    return _d(v)


def _d_vocab(values) -> dict:
    """Census of one side's values: what is there, and **in what form**.

    `compared` is the set the scorer actually intersects — `str(v)`, because
    [3b] compares `str(rv) == str(sv)`. Keeping the raw values *and* their
    compared forms side by side is what lets the diagnosis say whether a
    mismatch is a real difference or only a rendering difference.
    """
    raw, compared, types = [], set(), {}
    seen = set()
    nulls = scanned = 0
    truncated = capped = False
    for v in (values or ()):
        scanned += 1
        if scanned > _DIAG_VOCAB_SCAN_CAP:
            truncated = True
            break
        if v is None:
            nulls += 1
            continue
        tn = type(v).__name__
        types[tn] = types.get(tn, 0) + 1
        try:
            k = (tn, v)
            hash(k)
        except TypeError:
            k = (tn, _d(v))
        if k in seen:
            continue
        if len(seen) >= _DIAG_VOCAB_DISTINCT_CAP:
            capped = True
            continue
        seen.add(k)
        raw.append(v)
        compared.add(str(v))
    return {"n": len(raw), "sample": raw[:_DIAG_SAMPLE_VALUES], "compared": compared,
            "nulls": nulls, "types": types, "truncated": truncated or capped}


def _d_vocab_text(vc: dict) -> str:
    types = " ".join("%s x%d" % (k, n) for k, n in sorted(vc["types"].items()))
    sample = ", ".join(_d(v) for v in vc["sample"])
    # A value carrying printable non-ASCII (a full-width space, an NBSP, a Korean
    # bin code) reads identically to its plain cousin. Where that is possible the
    # escaped spelling goes next to it, because "these two look the same and are
    # not equal" is precisely the question this block answers.
    esc = ""
    try:
        # `ascii()` and `repr()` agree exactly when the value is pure ASCII. They
        # differing is the signal, and it is also the reason to print both.
        if any(ascii(v) != repr(v) for v in vc["sample"]):
            esc = "  escaped=[%s]" % ", ".join(ascii(v) for v in vc["sample"])
    except Exception:
        pass
    return ("distinct=%d%s nulls=%d types=[%s] sample=[%s]%s%s"
            % (vc["n"], "+" if vc["truncated"] else "", vc["nulls"], types or "-",
               sample, " (sample capped)" if vc["n"] > len(vc["sample"]) else "", esc))


def _d_range(cells) -> str:
    """`x=[min,max] y=[min,max] n=N` over a coordinate list. Ranges, never dumps."""
    if not cells:
        return "n=0"
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return "n=%d x=[%d,%d] y=[%d,%d]" % (len(cells), min(xs), max(xs), min(ys), max(ys))


def _d_meta(meta: dict | None) -> list:
    """The metadata row **as it really is**, plus the axes the transform reads.

    Two lines on purpose. The raw dict shows absent keys by their absence; the
    axes tuple shows what the code read in their place — which is where an
    absent `grid_y_invert` silently becomes `False` and nobody sees it.
    """
    if not meta:
        return ["raw=<none> (no wafer_map_metadata row, or grid_metadata unreadable)"]
    try:
        axes = map_overlay.frame_axes(meta)
        axes_t = ("rotation=%s side=%s grid_y_invert=%s start=(%s,%s) grid=%sx%s "
                  "phys(dia,chip_x,chip_y,off_x,off_y,margin)=%s"
                  % (axes[0], _d(axes[1]), axes[2], axes[3], axes[4], axes[5],
                     axes[6], _d(axes[7], 90)))
    except Exception as e:
        axes_t = "<frame_axes failed: %s: %s>" % (type(e).__name__, e)
    return ["raw=%s" % _d(meta, _DIAG_CHARS_LONG),
            "axes(as read by map_overlay.frame_axes)= %s" % axes_t,
            "declaration=%s" % map_overlay.geometry_declaration(meta)]


def _d_frame_phys(meta: dict | None) -> str:
    """The frame-axis phys parameters the wafer engine is actually constructed
    with — the rotation/side sign-and-swap table applied. Called, not copied:
    this is `map_overlay._frame_phys_params`, the same function
    `_frame_transformer` calls with the same meta. If it ever stops being
    reachable, this says so instead of reimplementing the table."""
    try:
        return _d(map_overlay._frame_phys_params(meta), 90)
    except Exception as e:
        return "<unavailable: %s: %s>" % (type(e).__name__, e)


class _RollNoticeHandler(logging.handlers.RotatingFileHandler):
    """Rotating file handler that says **in the file** what it discarded.

    A log that silently drops its beginning is the same defect as a report that
    silently truncates, and this codebase has paid for that shape more than once.
    After every rollover the fresh file opens with a line naming what moved to
    the backup and what is gone for good.
    """

    def doRollover(self):
        super().doRollover()
        try:
            self.stream.write(
                "%s\n=== %s ROLLED OVER at %s: the previous %d bytes are now in "
                "'%s.1'. Anything older than that one backup has been DISCARDED. ===\n"
                % (_DIAG_RULE, os.path.basename(self.baseFilename),
                   time.strftime("%Y-%m-%d %H:%M:%S"), self.maxBytes,
                   os.path.basename(self.baseFilename)))
            self.stream.flush()
        except Exception:
            pass


class _ConsoleSafeHandler(logging.StreamHandler):
    """Console handler that survives a terminal codec it cannot render.

    The console here is cp949 and the block carries Korean server-authored
    sentences. Stock `logging` would swallow the `UnicodeEncodeError` through
    `handleError` and the operator would lose **the whole block** from the half
    they are watching live. Re-encoding with replacement keeps the block; the
    file half (utf-8) is unaffected either way.
    """

    def emit(self, record):
        try:
            super().emit(record)
        except UnicodeEncodeError:
            try:
                enc = getattr(self.stream, "encoding", None) or "ascii"
                self.stream.write(
                    self.format(record).encode(enc, "replace").decode(enc)
                    + self.terminator)
                self.flush()
            except Exception:
                self.handleError(record)
        except Exception:
            self.handleError(record)


_DIAG_LOGGER = None
_DIAG_FILE_PATH = None
_DIAG_FILE_ERROR = None


def _diag_logger():
    """The diagnostics logger: console + `align.log`, and **not** `server.log`.

    `propagate=False` is the reason for the second point. Forty lines per click
    propagated to root would bury the file a reviewer reads to reconstruct an
    incident. Two destinations were asked for and two are wired.

    If the file cannot be opened the console half still runs — production may
    mount things this box does not.
    """
    global _DIAG_LOGGER, _DIAG_FILE_PATH, _DIAG_FILE_ERROR
    if _DIAG_LOGGER is not None:
        return _DIAG_LOGGER
    lg = logging.getLogger("map_alignment.diag")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    for h in list(lg.handlers):
        lg.removeHandler(h)
    # The block formats itself; a per-line prefix would break the worked example
    # a person is meant to check with a pencil.
    fmt = logging.Formatter("%(message)s")
    # `sys.stdout` is None under pythonw / a console-less service host. Falling
    # back to stderr keeps the "console" half alive there instead of turning
    # every emit into a swallowed AttributeError.
    con = _ConsoleSafeHandler(sys.stdout if sys.stdout is not None else sys.stderr)
    con.setFormatter(fmt)
    lg.addHandler(con)
    name = _DIAG_LOG_FILENAME
    try:
        import db_safety
        if db_safety.under_pytest():
            name = _DIAG_LOG_FILENAME_TEST
    except Exception:
        pass
    try:
        import paths
        _DIAG_FILE_PATH = paths.log_path(name)
        fh = _RollNoticeHandler(_DIAG_FILE_PATH, maxBytes=_DIAG_MAX_BYTES,
                                backupCount=_DIAG_BACKUPS, encoding="utf-8")
        fh.setFormatter(fmt)
        lg.addHandler(fh)
    except Exception as e:
        _DIAG_FILE_ERROR = "%s: %s" % (type(e).__name__, e)
        _DIAG_FILE_PATH = None
        logger.warning("[MapAlignment] %s unavailable (%s) - scoring diagnostics go to "
                       "the console only", name, _DIAG_FILE_ERROR)
    _DIAG_LOGGER = lg
    return lg


def _diag_compare_probe(ref_vc: dict, src_vc: dict) -> list:
    """Is the value mismatch a real difference, or only a rendering difference?

    The scorer compares `str(rv) == str(sv)` — exact, after `str()`. That makes
    `3` and `'3'` equal, and leaves `3.0` vs `'3'`, `'3 '` vs `'3'` and `'A'` vs
    `'a'` **unequal**. Whether that strictness is the whole answer is a question
    about this run's data, so it is answered against this run's data: intersect
    the two vocabularies the way the scorer does, then again under normalisations
    the scorer does **not** do. A looser probe finding matches the strict one did
    not is the finding, and it gets named here rather than left for the reader to
    spot in a sample.

    Nothing here feeds scoring. These are probes, printed and discarded.
    """
    a, b = ref_vc["compared"], src_vc["compared"]
    legacy = a & b                                   # 종전 규칙: `str()` 후 정확 일치
    # 지금 채점기가 실제로 쓰는 키. 이 줄이 **채점기와 같은 함수를 부른다** - 진단이 자기
    # 규칙을 따로 구현하면 둘이 갈리는 날 로그가 코드를 설명하지 못한다.
    shared = {_value_key(s) for s in a} & {_value_key(s) for s in b}
    numeric = {k for k in shared if k[0] == "n"}
    lines = [
        "  compare rule      : plain decimals -> NUMERIC  (2.0 == '2' == '02');",
        "                      everything else -> strip() + casefold() TEXT ('B1 ' == 'b1').",
        "                      Scientific notation, nan and inf stay TEXT on purpose - "
        "'1E1' is a spellable bin code.",
        "  shared, old rule (exact str) : %d  %s"
        % (len(legacy), sorted(legacy)[:_DIAG_SAMPLE_VALUES] if legacy else "<none>"),
        "  shared, rule now in force    : %d  (%d numeric, %d text)  %s"
        % (len(shared), len(numeric), len(shared) - len(numeric),
           sorted(str(k[1]) for k in shared)[:_DIAG_SAMPLE_VALUES]
           if shared else "<none>"),
    ]
    if shared and not legacy:
        lines.append(
            "  >> THE NORMALISATION IS LOAD-BEARING HERE: the two vocabularies shared "
            "NOTHING under the old exact-string rule and share %d under the rule now in "
            "force. Every one of those was a MISS before 2026-08-06." % len(shared))
    elif not shared:
        lines.append(
            "  >> The two vocabularies are DISJOINT even after normalisation: no value "
            "of the source can equal any value of the reference at any coordinate under "
            "any frame. This is NOT a geometry problem, and the value axis is demoted "
            "rather than allowed to rank on zeros.")
    return lines


def _diag_trace_lines(c: dict, label: str, reference_meta: dict, shipped: dict = None) -> list:
    """One candidate's worked example: five cells, arithmetic visible.

    Every number is a value the scorer used — the raw coordinate as read, the
    transform's own inputs, the placed coordinate the transform returned, the
    membership answer out of `_membership`'s array, and the two values [3b]
    compared. The one term that is **not** printed is the wafer bounding box:
    it lives inside `WaferMapCoordinateTransformer` and is not reachable here,
    and saying so beats recomputing it into a second implementation.
    """
    rows = c.get("_trace") or []
    lines = ["", "-- worked example (sample of %d cells) : %s  [%s] %s"
             % (len(rows), c["frame"], label, "-" * 12)]
    if not rows:
        lines.append("   <no cells were placed under this candidate - nothing to trace>")
        return lines
    a = rows[0].get("src_axes")
    lines += [
        "   transform in : source axes = %s" % _d(a, 120),
        "                  source frame phys (map_overlay._frame_phys_params) = %s"
        % rows[0].get("src_phys"),
        "                  target axes = %s"
        % _d(map_overlay.frame_axes(reference_meta) if reference_meta else None, 120),
        "                  target frame phys = %s" % _d_frame_phys(reference_meta),
        "                  axes tuple = (rotation, side, grid_y_invert, start_x, "
        "start_y, cols, rows, phys)",
        "                  NOT printed: the wafer bounding-box term, computed inside "
        "WaferMapCoordinateTransformer and not reachable from here.",
        # 🔴 **실린 값을 찍는다, 채점기가 들고 있던 값이 아니라.** 둘이 갈리면 로그는 맞는
        #    수를 보여 주고 화면은 다른 수를 그리는데, 그 조합이 두 기록을 다 읽는 사람에게
        #    가장 나쁘다 - 로그가 화면을 부정하므로 어느 쪽도 못 믿게 된다. 그래서 이 줄은
        #    `c["dx"]`가 아니라 **payload에 실제로 들어간 행**(`out`)에서 읽는다.
        "   placement SHIPPED for this candidate: %s   [%s]"
        % ("-" if shipped is None or shipped.get("shift") is None
           else "(dx=%s, dy=%s)" % (shipped["shift"]["dx"], shipped["shift"]["dy"]),
           "the screen must draw at this offset; it is the offset the scoring used"),
    ]
    member = c.get("member")
    for n, r in enumerate(rows, 1):
        i = r["at"]
        on_ref = None if member is None else bool(member[i])
        probe = r.get("probe")
        # The fallback offset comes from the SHIPPED row when there is one, for the same
        # reason the header line does. `c["dx"]` is the same number today and this line is
        # what would notice the day it stops being.
        sh = (shipped or {}).get("shift") if shipped else None
        if probe is None and sh is not None:
            probe = (r["placed"][0] + sh["dx"], r["placed"][1] + sh["dy"])
        elif probe is None and c.get("dx") is not None:
            probe = (r["placed"][0] + c["dx"], r["placed"][1] + c["dy"])
        lines.append(
            "   cell #%d  map=%s  src(x=%s, y=%s) val=%s"
            % (n, _d(r["map_id"], 24), r["src"][0], r["src"][1], _d(r["val"])))
        lines.append(
            "            -> after transform (x=%s, y=%s)   + shift -> probe (%s, %s)"
            % (r["placed"][0], r["placed"][1],
               "?" if probe is None else probe[0], "?" if probe is None else probe[1]))
        if on_ref is None:
            lines.append("            reference cell at probe? <candidate not scored>")
        elif not on_ref:
            lines.append("            reference cell at probe? NO   -> no value compared")
        elif not r.get("compared"):
            lines.append("            reference cell at probe? YES  -> occupancy only "
                         "(no value axis in this run)")
        else:
            rv, sv = r.get("ref_value"), r.get("src_value")
            lines.append("            reference cell at probe? YES  ref val=%s" % _d(rv))
            lines.append(
                "            compare %s vs %s  ->  %s"
                % (_d(sv), _d(rv), "MATCH" if r.get("verdict") else "MISS"))
    return lines


def _emit_diag(lines):
    """Emit the block as **one** record — one request, one contiguous block.

    One record and not many: `logging` serialises a record per handler, so two
    operators clicking two units cannot braid their runs into each other. And it
    never raises: scoring is a read and a read must not fail because a log did.
    """
    try:
        _diag_logger().info("%s", "\n".join(lines))
    except Exception:
        try:
            logger.warning("[MapAlignment] scoring diagnostics could not be emitted",
                           exc_info=True)
        except Exception:
            pass


def score_candidates(source_maps: list, reference_cells, reference_meta: dict,
                     shift_window: int = SHIFT_WINDOW, cell_cap: int = MAX_SCORED_CELLS,
                     reference_values=None, thresholds: dict = None,
                     assume_reference_geometry: bool = True,
                     reference_ref: dict = None, value_weights: dict = None,
                     sides: list = None, index_thresholds: dict = None,
                     diag: list = None):
    """후보 8개를 **한 호출로** 채점한다. DB를 모른다 — 셀과 메타만 받는다.

    `source_maps`: `[{"map_id": str, "meta": dict, "cells": [(x, y), ...],
                      "values": [v, ...], "indices": [k, ...]}]` — `values`·`indices`는
        있으면 `cells`와 **같은 순서**다.
    `sides`: 채점할 면 목록. `None`이면 **둘 다**(§load_alignment_sides). 좁히면 나머지
        후보는 목록에서 사라지지 않고 `STATE_NOT_CONSIDERED`를 달고 나간다.
    `reference_cells`: 기준(공통 바닥)의 점유 좌표 집합 — 기준 맵 자신의 프레임 좌표다.
    `reference_values`: 기준 셀의 값. `reference_cells`와 같은 순서. 없으면 점유 채점만.
    `thresholds`: `{min_margin_dies, min_discriminating_dies}`. **기본값이 없다** — 선언되지
        않으면 순위를 내지 않는다(`_rule_on`).
    `index_thresholds`: 순번 축 **전용** 문턱(`alignment.index`). 없거나 불완전하면 순번
        수치는 그대로 실려 나가되 **순위를 가져가지 않는다**(§INDEX_THRESHOLD_BLOCK).
        점유·값 문턱과 키를 공유하지 않는 것이 요점이다 — 저쪽을 낮추는 조작이 이 축의
        안전망까지 걷어 가면 안 된다.
    `assume_reference_geometry`: 규격 선언이 없는 소스 맵을 **바닥의 웨이퍼 치수를 빌려**
        채점한다(스펙 §9ⓐ, `map_overlay.assume_phys_from`). **기본값은 True**다.
        명시로 끌 수 있다(`False`) — 가정 없는 답을 보려는 진단은 실재하는 요구다.

        🔴 [기본값 뒤집힘 2026-08-06 — 종전 근거와 그 근거가 성립을 멈춘 이유]
        종전 기본값은 False였고 근거는 이랬다: **「가정은 조작자가 내는 주장이므로 자동으로
        걸면 아무도 주장한 적 없는 가정 위에서 판정이 나온다.」** 그 문장은 **쓰인 시점에
        참이었다** — 그때 payload는 가정이 걸렸다는 사실을 말할 수 없었고, 말할 수 없는
        가정은 실제로 아무도 주장하지 않은 가정이었다. 버튼은 그 침묵의 대역이었다.

        그 전제가 사라졌다. 지금 판정과 통계가 **가정의 출처까지** 싣는다:
        `ruling.geometry_assumed` · `ruling.assumed_map_count` ·
        `stats.assumed_map_ids` · `stats.assumable_map_ids`, 그리고 소스마다
        `geometry_basis`(§geometry_basis_of)가 「무엇 위에서 정렬됐나」에 답한다. 버튼이
        대신 서 있던 정직성이 **버튼과 무관하게 payload 안에 있다.** 그러므로 마찰은
        아무것도 사지 못하면서, 조작자가 **규격을 모르기 때문에 여는 화면**에서 단위마다
        클릭 하나를 물린다. 제품 소유자 확정: 채점은 읽기이고 읽기에는 마찰이 없다.

        🔴 뒤집힌 것은 **기본값이지 기록이 아니다.** 가정이 걸린 판정은 여전히 다른
        사실이고 그 사실은 여전히 판정 dict 자신이 나른다 — 이 파일이 `geometry_assumed`를
        옆 필드가 아니라 판정 안에 넣은 이유가 그대로 유효하다. 근거가 바뀐 것이지
        사라진 것이 아니다.
    `reference_ref`: `{"table":..., "map_id":...}` - 빌린 출처를 기록에 남기기 위한 이름표.
    `value_weights`: `{값: 무게}`. **일치 하나가 몇 다이만큼 세는가**이지 셀의 존재값이 아니다
        (§[3c]). 선언이 없으면 빈 dict이고 채점은 종전과 **한 자도 다르지 않다** —
        조작자가 규칙 하나에만 무게를 걸어도 나머지가 그대로여야 켤 수 있다.

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

    `diag`: **관측 전용** 라인 수집기(§Scoring diagnostics). `None`이면 이 함수는 한 줄도
        만들지 않고 채점은 한 자도 다르지 않다. 리스트를 주면 호출자가 시작한 블록에
        이어 붙인다 — 요청 하나가 기록 하나여야 하므로 여기서 직접 내보내지 않는다.
    """
    import numpy as np
    t0 = time.monotonic()
    excluded = _Excluded()
    _dg = diag if diag is not None else None

    # ═══ [D14] 유효 다이 영역을 **자기 최솟값으로 정규화한다 — 이 한 곳에서만** ═══════════
    # 제품 소유자 확정 2026-08-06: 「유효 다이맵 메타의 start x,y는 무의미함. 유효다이맵 min
    # 값으로 정규화 하면 됨」. 앞선 관측이 그 이유를 준다 - 「유효다이영역 만들 때 오리진을
    # 중심으로 찍어 놓으면 −10~10 이렇게 분포함」이고, 그러면서도 「항상 그런 건 아니고
    # 랜덤이야」. 저장 좌표의 원점이 맵마다 제각각이고 선언이 그것을 말해 주지 않으므로,
    # **어떤 독자도 원점에 대해 아무것도 가정할 수 없다.** 그래서 정규화는 청소가 아니라
    # 이 좌표들이 뜻을 갖는 유일한 방법이다.
    #
    # 🔴 **스펙 §1-0의 「좌표계는 선언되는 것이지 데이터에 맞춰 재계산되는 것이 아니다」를
    #    어기는 것이 아니다** (다음 독자가 반드시 이 반론을 든다 - 총괄 지시로 여기 남긴다).
    #    그 규칙은 **에디터의** 좌표계를 다스린다. 거기서 화면을 맞추려고 좌표를 옮기면
    #    「표시 = 오리진 + DB 값」이 깨진다. 여기서 유효 다이 영역은 그리는 대상이 아니라
    #    **비교의 바닥**이고, 최솟값 정규화는 그 바닥의 정준 대표를 고르는 것이다. 저장된
    #    좌표는 한 자도 바뀌지 않고, 소스의 원 좌표도 그대로이며, 답이 **차분**이므로 선언이
    #    무엇이든 결과가 불변이다 - 선언이 뜻을 잃은 이 데이터에서 사려는 성질이 그것이다.
    #
    # 🔴 **두 번 하지 않는다.** 정규화가 두 곳에 살면 그것이 같은 병의 새 이름이다. 로더
    #    (`_cells_of` → `_to_cells`)는 좌표에 아무 산술도 하지 않고(§_readable_cell: 형변환
    #    하나뿐), 채점이 바닥을 바닥으로 쓰는 자리는 여기 하나다.
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
    #
    # [D3] 그리고 여기가 **가정이 들어오는 유일한 자리**다. 규격 선언이 없는 맵을 그냥
    #      제외하면 「규격을 선언하라」인데, 조작자가 정렬을 도는 이유가 그 규격을 모르기
    #      때문이다 - 질문보다 답을 먼저 요구하는 셈이다(스펙 §9ⓐ). 그래서 바닥이 선언돼
    #      있으면 그 웨이퍼 치수를 **계산에만** 빌려 온다. 빌린 사본은 메모리에만 살고
    #      `geometry_declaration`에 여전히 `declared`가 아니라고 답한다.
    #
    # 🔴 **가정을 요청하지 않아도 「열 수 있었는가」는 센다.** 그 수가 없으면 화면은 막다른
    #    길을 그리고, 조작자는 여기 제안이 있다는 것을 알 방법이 없다.
    basis_ok = (map_overlay.geometry_declaration(reference_meta)
                == map_overlay.GEOMETRY_DECLARED)
    ref_grid = map_overlay.grid_dims(reference_meta) if basis_ok else None
    assumed_ids, offerable_ids, basis_undeclared_ids = [], [], []
    usable = []
    for sm in source_maps:
        meta, mid = sm.get("meta"), sm.get("map_id")
        # 🔴 [D4] 좌표를 **먼저** 본다. 규격 행이 없는 맵의 프레임은 그 맵 자신의 셀에서
        #    나오므로, 셀이 없으면 규격 이전에 잴 것이 없다. 종전 순서(규격 먼저)는 둘 다
        #    없는 맵을 `meta_missing`이라 불렀는데, 고칠 수 있는 쪽은 좌표다.
        if not sm.get("cells"):
            excluded.add(EXCLUDE_NO_CELLS, mid)
            continue
        use_meta = meta
        if not meta:
            # 🔴 **빌리기 전에 「행이 정말 없는가」를 묻는다.** 서버가 메타 테이블을 못 읽어서
            #    None인 것이면 이 맵은 미등록이 아니고, 빌린 규격에 올리는 순간 자기 규격을
            #    선언해 둔 맵이 남의 프레임 위에서 채점된다 - 화면은 멀쩡하고 값만 틀린다.
            #    표지는 호출자가 요청 경계에서 한 번 찍는다(§stamp_meta_refusal).
            if sm.get("meta_refusal"):
                excluded.add(sm["meta_refusal"], mid, sm.get("meta_refusal_detail"))
                continue
            # [D4] **규격 행이 없다 = 정상이다.** 조작자가 정렬을 여는 이유 그 자체이고,
            #      [D3]이 「행은 있는데 규격이 없다」에 내린 판정과 같은 판정을 받는다.
            borrowed = assumed_meta_for_unregistered(
                sm.get("cells"), reference_meta, reference_ref) if basis_ok else None
            if borrowed is None:
                # 🔴 바닥이 선언이 아니면 **거절한다.** 화면/항등 프레임에 얹지 않는다 —
                #    근거 없이 그린 좌표는 멀쩡해 보이고 전부 틀리다. 그리고 이 사실은
                #    맵이 아니라 요청의 사실이라 제외 집계에 세지 않는다(§compose_basis_refusal).
                basis_undeclared_ids.append(mid)
                continue
            # 🔴 [D5] 담김 검사는 **제안보다 먼저**다. 안 들어가는 맵을 제안했다가 켠 뒤에
            #    거절하면 조작자는 한 번 더 눌러 보고 같은 막다른 길에 도착한다.
            outside = cells_outside_grid(borrowed, sm.get("cells"))
            if outside is not None:
                excluded.add(EXCLUDE_CELLS_OUTSIDE_GRID, mid, outside)
                continue
            offerable_ids.append(mid)
            if not assume_reference_geometry:
                excluded.add(EXCLUDE_GEOMETRY_REFUSED, mid, TEXT_NO_META_ROW)
                continue
            use_meta = borrowed
            assumed_ids.append(mid)
        else:
            # [D6] 축이 둘이고 서로 다른 질문이다(§phys_needs_basis / §grid_needs_basis).
            #      종전에는 ①만 물었고, 그래서 규격을 선언한 맵은 격자가 바닥과 어긋나도
            #      빌림을 통째로 건너뛰어 `grid_dims_differ`로 죽었다 — 그 맵이 바로 이
            #      기능이 섬기는 모집단이다(부분 DT 맵).
            need_phys = phys_needs_basis(meta)
            need_grid = grid_needs_basis(meta, reference_meta) if basis_ok else False
            if need_phys or need_grid:
                borrowed = (borrowed_meta_for(meta, reference_meta, reference_ref,
                                              need_phys, need_grid)
                            if basis_ok else None)
                if borrowed is None:
                    # 바닥이 선언돼 있는데도 못 빌리는 경우는 하나뿐이다: 격자 치수가 없다.
                    # 그때는 규격이 아니라 치수를 대라고 말해야 한다 - 사유가 갈려야 수리가 갈린다.
                    if basis_ok and map_overlay.grid_dims(meta) is None:
                        excluded.add(EXCLUDE_GRID_DIMS_MISSING, mid)
                    else:
                        excluded.add(EXCLUDE_GEOMETRY_REFUSED, mid,
                                     map_overlay.geometry_refusal(meta))
                    continue
                # 🔴 [D6] 담김 검사가 **이 모집단까지** 온다. 격자를 덮어쓰는 순간
                #    `grid_dims_differ`가 하던 「같은 웨이퍼가 아니다」 걸러내기가 사라지고,
                #    남는 증거는 담김 하나뿐이다 — 없으면 진짜로 다른 맵이 조용히 앉는다.
                #    격자를 **안** 빌렸으면 빌린 격자가 없으므로 물을 것도 없다.
                if need_grid:
                    outside = cells_outside_grid(borrowed, sm.get("cells"))
                    if outside is not None:
                        excluded.add(EXCLUDE_CELLS_OUTSIDE_GRID, mid, outside)
                        continue
                # 🔴 제안은 **가정을 안 걸어도** 센다. 이 목록이 화면의 버튼이므로, 여기
                #    안 넣으면 이 판정이 섬기려는 바로 그 모집단에서 버튼이 안 나온다.
                offerable_ids.append(mid)
                if not assume_reference_geometry:
                    # 사유는 **어느 축이 열려 있는가**를 말한다. 격자만 어긋난 맵을
                    # `geometry_refused`로 부르면 조작자가 규격을 재러 가는데, 규격은 이미
                    # 선언돼 있다. `grid_dims_differ`는 가정을 요청하지 않은 이 자리에서
                    # 여전히 참이고 여전히 할 일이 있다.
                    if need_phys:
                        excluded.add(EXCLUDE_GEOMETRY_REFUSED, mid,
                                     map_overlay.geometry_refusal(meta))
                    elif map_overlay.grid_dims(meta) is None:
                        excluded.add(EXCLUDE_GRID_DIMS_MISSING, mid)
                    else:
                        excluded.add(EXCLUDE_GRID_DIMS_DIFFER, mid,
                                     "소스 %dx%d · 기준 %dx%d"
                                     % (map_overlay.grid_dims(meta) + ref_grid))
                    continue
                use_meta = borrowed
                assumed_ids.append(mid)
        # 🔴 격자 치수 대조를 후보 루프 **앞**으로 끌어올린다. `make_frame_transform`이
        #    후보마다 같은 답을 내는 검사이고(회전은 `_grid_of`를 바꾸지 않는다), 안에서
        #    터지면 맵 하나 때문에 **여덟 후보 전부**가 죽어 단위 전체가 답을 잃는다.
        #    가정이 모집단을 열면서 이 자리가 훨씬 자주 밟힌다 - 치수는 빌리는 값이 아니라
        #    맵마다 다를 수 있는 값이므로, 어긋난 맵 하나는 그 맵만 빠져야 한다.
        s_grid = map_overlay.grid_dims(use_meta)
        if s_grid is None:
            excluded.add(EXCLUDE_GRID_DIMS_MISSING, mid)
            continue
        if ref_grid and s_grid != ref_grid:
            excluded.add(EXCLUDE_GRID_DIMS_DIFFER, mid,
                         "소스 %dx%d · 기준 %dx%d" % (s_grid + ref_grid))
            continue
        sm["_meta"] = use_meta
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
        # 순번도 **같은 규율로 같이 잘린다**. 좌표와 어긋나면 k번이 남의 자리를 기대하고,
        # 그 오답은 개수로 안 잡힌다(위 값 절단과 같은 계열).
        ks = sm.get("indices") or []
        sm["_use_indices"] = [(ks[i] if i < len(ks) else None)
                              for i in range(len(sm["_use"]))]
        scored_cells += len(sm["_use"])

    # 🔴 기준의 훑기는 이제 **정답표가 아니라 앵커 하나**를 준다(§순번 주석 2026-08-06).
    #    종전에는 이 표가 소스의 k번을 채점하는 정답이었고, 그것이 이 축이 부분 맵에서
    #    0점을 낸 원인이었다. 지금 이 표에서 쓰는 것은 **1번 자리 하나**다 - 「소스의 최소
    #    순번 다이가 유효 다이 영역의 좌상단」이라는 제품 소유자의 규칙이 가리키는 자리.
    #    기준이 없거나 셀이 없으면 앵커도 없고, 그때는 종전 시프트 탐색이 그대로 돈다.
    # 🔴🔴 [2026-08-06] **앵커의 과녁은 「기준 그림의 좌상단」이 아니라 「웨이퍼의 좌상단
    #    다이」다.** 종전에는 기준의 **시각 좌표**를 훑어 1번을 골랐다. 기준이 rot0/front를
    #    선언하면 그 둘이 우연히 같아서 안 보였고, 기준이 회전·면을 선언하는 순간 갈렸다.
    #
    #    실측 2026-08-06(소스 한 장 고정, 바닥만 한 필드씩 바꿔 대조):
    #      바닥 rot0/front  → 과녁 (16,0),  정준 좌상단 (16,0)  · 일치 **200/200**
    #      바닥 rot90       → 과녁 (16,0),  정준 좌상단 (40,16) · 일치 **118/200**
    #      바닥 rot180      → 과녁 (16,0),  정준 좌상단 (24,40)
    #      바닥 rot270      → 과녁 (16,0),  정준 좌상단 (0,24)
    #      바닥 side=back   → 과녁 (16,0),  정준 좌상단 (24,0)  · 일치 **136/200**
    #      바닥 y_invert    → 과녁 (16,40), 정준 좌상단 (16,40) · 일치 200/200 (이 축은 이미 맞다)
    #    제품 소유자: 「특정 유효다이맵으로 하면 밀림」 — 갈리는 필드는 **기준의 rotation·side**다.
    #
    #    🔴 이것은 순번 훑기에서 이미 고친 결함의 **같은 형태**다(§순번 주석: 기준의 시각
    #       공간에서 훑으면 기준 자신의 프레임만큼 조용히 틀린다). 그때는 훑기를 물리 좌표로
    #       옮겼고, **앵커의 과녁은 옮기지 않았다.** 한 파일 안에서 같은 실수를 두 번 했다.
    #
    #    🔴 그리고 **잔차는 이 결함을 못 본다.** 확정→재채점 왕복은 틀린 배치를 그대로
    #       재현하므로 잔차가 (0,0)으로 깨끗하게 나온다 — 48조합 속성 테스트가 초록인 채로
    #       118/200을 통과시켰다. 배치가 옳은지는 **일치 개수**가 답한다(테스트에 추가).
    #
    # ═══ [D11] 정준 좌표는 **선언된 축만으로** 만든다 — mm도 박스도 안 읽는다 ═══════════
    # 기준의 시각 좌표 → 정준 좌표는 **선형 사상 하나**이고, 그 사상은 기준이 선언한
    # 회전·면·y반전에서 전부 나온다(§map_overlay.frame_linear_part). 웨이퍼 원도 칩 피치도
    # 필요 없다 — 그것들은 이 셀 목록을 **만들 때** 이미 제 일을 했다.
    #
    # 🔴 평행이동 상수는 안 만든다. 훑기도 행 묶기도 평행이동에 불변이므로 상수는 답을
    #    바꾸지 못하고, 상수를 구하려는 순간 박스가 다시 들어온다. 소스와 기준이 **같은
    #    사상**을 타므로 둘은 같은 상수만큼 움직이고, 그래서 서로에 대해 정합한다.
    reference_top_left = None
    reference_walk = {}
    reference_walk_rank = None
    _canon_ref = None           # 기준 셀의 정준 좌표. 방향 판정도 이것을 쓴다([3a-2])
    _lc_ref = None              # 기준 시각 → 정준. 소스의 놓인 좌표도 이걸로 정준화한다
    if ref_pairs:
        _lc_ref = map_overlay.frame_linear_part(reference_meta, _CANONICAL_AXES)
        _canon_ref = [map_overlay.apply_linear(_lc_ref, x, y) for (x, y) in ref_pairs]
        reference_walk = serpentine_index(_canon_ref, top_is_min_y=True)
        _first = reference_walk.get(1)
        # 과녁은 **기준의 시각 좌표**로 돌려준다 — 놓인 좌표가 그 공간에 살기 때문이다.
        # 역변환을 새로 쓰지 않고 짝을 되짚는다(손으로 쓴 역변환이 규약을 놓치는 사고를
        # 이 파일이 이미 두 번 겪었다).
        _back = {}
        for _p, _v in zip(_canon_ref, ref_pairs):
            _back.setdefault(_p, _v)
        reference_top_left = _back.get(_first)
        # [D13] 기준 다이마다 **훑기 번호**. `_residual_shift`가 「이 자리에 앉히면 소스가
        # 덮는 다이들이 훑기의 끊기지 않은 한 구간인가」를 묻는 데 쓴다(§_residual_shift).
        # `ref_sorted`와 **같은 순서로** 늘어놓는다 - 저쪽이 searchsorted 첨자로 읽는다.
        _rank_by_canon = {_c: _k for _k, _c in reference_walk.items()}
        _rank_of_key = {}
        for _i, _c in enumerate(_canon_ref):
            _rank_of_key.setdefault(int(ref_keys[_i]), _rank_by_canon.get(_c, 0))
        reference_walk_rank = np.array(
            [_rank_of_key.get(int(_k), 0) for _k in ref_sorted], dtype="int64")

    # [2] 후보마다 **메타를 통째로 만들어** 변환한다 (모듈 상단 전제).
    #
    # 🔴 좁혀진 면은 **목록에서 빠지지 않는다** — 안 본 후보와 져서 밀린 후보를 한 모양으로
    #    내보내면 화면이 「우리는 이걸 고려하지 않았다」를 말할 수 없다(§STATE_NOT_CONSIDERED).
    considered = set(sides) if sides else set(FRAME_SIDES)
    per_candidate = []
    source_values = None
    source_indices = None
    cell_owner = None
    # [D11] 차분 배치의 기준점. **배치보다 먼저** 정해져야 한다 — 차분은 기준점이 있어야
    # 뜻이 생긴다. 앵커가 안 서면 None이고, 그때는 종전 변환 경로가 돈다(박스를 읽는
    # 유일한 갈래이고, 그 갈래에서는 ±3 탐색이 평행이동을 풀므로 출발점이 필요하다).
    _anchor = anchor_cell_of(usable) if reference_top_left is not None else None
    anchor_map_index = _anchor[0] if _anchor else None
    anchor_cell = _anchor[1] if _anchor else None
    for frame in CANDIDATE_FRAMES:
        if parse_frame(frame)[1] not in considered:
            per_candidate.append({"frame": frame, "keys": None, "reason": None,
                                  "not_considered": True})
            continue
        placed = []
        vals = []
        ks = []
        # 순번 훑기가 도는 좌표. **놓인 좌표가 아니라 물리(정준) 좌표**다 - 기준의 프레임이
        # 답에 섞이면 안 되기 때문이고, 실측이 그 크기를 준다(§순번 주석 2026-08-06).
        phys = []
        # 셀이 **어느 맵의 것인가**. 순번은 맵마다 자기 1..N을 다시 시작하므로(제품 소유자:
        # 「소스별로 index 매기는거잖아」) 여러 장을 한 훑기에 담으면 두 작업의 번호가 한
        # 수열로 섞여 둘 다 틀린다. 그래서 훑기는 **맵 단위**로 돈다.
        owner = []
        frame_linear = None
        # 앵커 셀이 **변환만으로** 앉은 자리(시프트 이전). 아래 payload와 잔차가 읽는다.
        anchor_placed = None
        failed = None
        # Worked-example capture. Rows are taken **at the line the scorer places
        # the cell**, so the printed arithmetic is the arithmetic that ran.
        trace = []
        for mi, sm in enumerate(usable):
            if not sm.get("_use"):
                continue
            # 🔴 `_meta`이지 `meta`가 아니다. 가정이 걸린 맵은 **빌린 사본** 위에서 후보를
            #    세운다. 원본(`meta`)은 그대로 남아 있어야 한다 - `declared_frame_of`가 읽는
            #    「이 맵이 적어 둔 것」이 빌린 값으로 오염되면 배지가 남의 선언을 단다.
            src_meta = source_meta_for_frame(sm.get("_meta") or sm["meta"], frame)
            if src_meta is None:
                failed = "프레임 '%s'을 이 맵의 규격에 적용할 수 없습니다" % frame
                break
            # ═══ 🔴 REVERTED 2026-08-06 — 배치는 **변환뿐**이다, 앵커를 미리 굽지 않는다 ═══
            # `ec8c0e7`의 배치를 그대로 되돌린다. `fac206c` 이후의 차분 배치
            #     p = reference_top_left + L·(cell − anchor_cell)
            # 는 앵커를 **배치에 미리 먹였고**, 그 한 줄이 두 가지를 동시에 무너뜨렸다:
            #   ① `_anchor_shift`의 `reference_top_left − placed[i_min]`에 뺄 것이 남지
            #      않아 시프트가 **항등적으로 (0,0)**이다 — 조작자가 본 「shift 0,0 고정」.
            #      `4947a65`가 이 항등식을 정확히 진단하고도 원인을 지우는 대신 잔차를
            #      얹었고, 잔차를 되돌리자 항등식만 남았다.
            #   ② 제품 소유자 2026-08-06: 「미리 앵커를 먹여놓으니 시프트 0이어도
            #      만점이구만」 — 앵커가 앉힌 자리를 그대로 채점하므로 **점수가 나빠질 수
            #      없다.** 만점은 프레임이 옳다는 증거가 아니라 앵커가 그렇게 앉혔다는 뜻이다.
            # 그래서 배치는 변환만 하고, 평행이동은 [3-0]에서 **별도의 값**으로 붙는다.
            try:
                tf = map_overlay.make_frame_transform(src_meta, reference_meta)
                # 순번 축은 기준을 **모른다**. 같은 `src_meta`에서 물리 좌표만 뽑는
                # 별도 사상이고, 거절 규약은 같다(§map_overlay.make_physical_transform).
                ptf = map_overlay.make_physical_transform(src_meta)
            except ValueError as e:
                failed = str(e)
                break
            # 🔴 선형부는 **배치에 쓰이지 않는다 — 화면이 그릴 재료로만 실려 나간다**
            #    (§payload `placement`). 앵커가 선 맵의 것이라야 앵커 쌍과 짝이 맞는다.
            #    `frame_linear_part`가 `tf`의 선형부와 항등인 것은 독립 오라클이 지킨다
            #    (`test_the_linear_part_matches_the_transform`).
            if anchor_cell is not None and mi == anchor_map_index:
                frame_linear = map_overlay.frame_linear_part(src_meta, reference_meta)
            for i, (x, y) in enumerate(sm["_use"]):
                p = tf(x, y)
                if _dg is not None and len(trace) < _DIAG_TRACE_CELLS:
                    trace.append({
                        "map_id": sm.get("map_id"), "at": len(placed),
                        "src": (x, y), "val": sm["_use_values"][i], "placed": p,
                        # The frame-applied source meta is what the transform was
                        # built from; both readings come from that same dict.
                        "src_axes": map_overlay.frame_axes(src_meta),
                        "src_phys": _d_frame_phys(src_meta)})
                placed.append(p)
                # 🔴 앵커 셀이 **변환만으로** 어디 앉는가. `placement.anchor_ref`(화면이
                #    그리는 원점)와 잔차의 기준점이 둘 다 여기서 나온다 — 둘 다 「실제로
                #    앉은 자리」여야 하고, 앵커를 배치에 굽지 않게 된 뒤로 그 자리는
                #    `reference_top_left`가 **아니다**. 종전 두 식은 그 항등식을 전제로
                #    쓰여 있었으므로 여기서 값을 붙잡아 두고 아래에서 다시 유도한다.
                if (anchor_cell is not None and mi == anchor_map_index
                        and (x, y) == tuple(anchor_cell)):
                    anchor_placed = p
                # 순번 훑기의 입력. [D12]가 시프트를 푼 뒤 **앉힌 좌표로 덮어쓴다**.
                phys.append(ptf(x, y))
                owner.append(mi)
                vals.append(sm["_use_values"][i])
                ks.append(sm["_use_indices"][i])
        if failed is not None:
            per_candidate.append({"frame": frame, "keys": None, "reason": failed,
                                  "_trace": trace})
            continue
        # 소스 값은 후보마다 **같은 순서의 같은 셀**이다(좌표만 움직인다). 그래서 한 번만
        # 붙잡아 둔다 — 후보마다 다시 만들면 그 사본들이 갈릴 수 있고, 갈리면 i번째가 서로
        # 다른 셀을 가리키게 된다.
        if source_values is None:
            source_values = vals
        if source_indices is None:
            source_indices = ks
        if cell_owner is None:
            cell_owner = owner
        per_candidate.append({"frame": frame, "keys": _encode(placed), "reason": None,
                              "_trace": trace,
                              # 실어 보낼 배치의 선형부(§payload `placement`).
                              "_linear": frame_linear,
                              # 앵커 셀의 **변환 후·시프트 전** 자리. payload의
                              # `anchor_ref`와 잔차의 기준점이 여기에 시프트를 더해 나온다.
                              "_anchor_placed": anchor_placed,
                              # 순번 훑기의 입력. 후보마다 **다르다** - 회전·면이 바꾸는
                              # 것이 바로 이 좌표이고, 그래서 여덟이 서로 다른 순서를 만든다.
                              # 🔴 앵커가 있으면 [3-0]이 **앉힌 좌표로 덮어쓴다**(§[D12]).
                              "_phys": phys,
                              # 앵커 자리. 놓인 좌표계(기준 시각)에서 잰다 - 앵커가 정하는
                              # 것은 점유·값 축의 **평행이동**이고 그 축들은 그 좌표계에 산다.
                              "_placed": placed,
                              # Post-transform extent. Taken from `placed` before
                              # it is encoded away, so it is the coordinates that
                              # were actually laid on the reference.
                              "_placed_range": (_d_range(placed) if _dg is not None
                                                else None)})

    # [3] 후보별 시프트를 풀고 셀별 진리값을 모은다.
    #
    # 🔴 **놓인 셀이 0건인 후보는 채점된 후보가 아니다.** 소스가 전부 제외되면 여덟 후보가
    #    모두 빈 배열을 놓고 일치 0을 받는다. 그 0은 잰 값이 아니라 **잴 것이 없었다**는 뜻인데,
    #    「채점됨」으로 표시하면 판정기가 여덟 개의 0을 여덟 자 동점으로 읽는다. 그래서 채점
    #    여부는 배열의 존재(`keys is not None`)가 아니라 **크기**로 판정한다 - 앞의 것은
    #    변환기가 거절했는가만 말하고, 잰 것이 있었는가는 말하지 않는다.
    #    빈 배열과 None은 조작자에게 다른 사실이므로 여기서 접지 않고 `scored` 하나로 합류시킨
    #    뒤 `_rule_on`이 `placed_cells`로 다시 가른다.
    # 🔴 [3-0] **순번이 있으면 평행이동은 푸는 값이 아니라 읽는 값이다.**
    #    제품 소유자 확정 2026-08-06: 「소스 조각 좌상단이 기준맵 좌상단 되게」 -
    #    최소 순번 다이가 유효 다이 영역의 좌상단이고, 그 한 쌍이 평행이동을 정한다.
    #
    #    시프트 탐색이 왜 이 자리에서 답을 못 내는가는 잰 값이 있다(합성 실측 2026-08-06,
    #    기준 1313셀 · 소스 266셀): **여덟 후보 전부 일치 266/266, 시프트 (0,0), 그리고
    #    답이 갈리는 셀 0개.** 부분 맵은 어떤 프레임 어떤 평행이동에서도 유효 다이 위에
    #    앉으므로 탐색이 최대화하는 목적함수가 **포화**한다. 포화한 목적함수에서 고른
    #    1등은 데이터가 고른 것이 아니라 동점 처리 규칙(원점에 가까운 쪽)이 고른 것이고,
    #    (0,0)이 맞는 것은 운일 뿐이다. 제품 소유자가 본 것이 정확히 그것이다 -
    #    「화면 보면 어긋나 있는데 오버랩 266이래」.
    #
    #    좌표에 낯선 원점이 섞인 경우(같은 실측, 소스를 (5,-4)만큼 옮겨 둠)는 더 분명하다:
    #    탐색은 여덟 후보 전부 196으로 포화하고 창 끝(±3)에 붙은 시프트를 고르는데,
    #    앵커는 정답 프레임에 266을, 나머지 일곱에 1~186을 준다. **앵커는 포화하지 않는다.**
    #
    #    🔴 그러나 앵커는 **주장을 하나 산다**: 이 작업이 웨이퍼의 좌상단 유효 다이부터
    #    시작했다는 주장. 그 주장이 거짓인 작업(아래쪽 절반만 도는 부분 맵 등)에서는
    #    앵커가 틀린 자리에 맵을 놓는다. 그래서 ⓐ 순번이 있을 때만 걸고, ⓑ 어느 쪽이
    #    돌았는지를 판정이 직접 나르며(`ruling.placement`), ⓒ 되돌리는 스위치를 하나로 둔다.
    anchor_dxy, anchor_reason = _anchor_shift(
        per_candidate, source_indices, cell_owner, reference_top_left, anchor_cell)
    for c in per_candidate:
        if c["keys"] is None or c["keys"].size == 0:
            c.update(dx=None, dy=None, agreement=0, member=None, scored=False)
            continue
        if anchor_dxy is not None:
            # 🔴 [D13→REVERTED 2026-08-06] **여기 오는 값은 이제 진짜 수다.** 배치가 앵커를
            #    미리 굽지 않으므로(§[2]) `_anchor_shift`는 소유자가 정의한
            #    `anchor_ref − anchor_src`를 저장 좌표 그대로 낸다 — 두 앵커가 다르면 0이
            #    아니다. 종전 주석이 「항등적으로 (0,0)」이라 적혀 있던 자리이고, 그 항등식이
            #    조작자의 「shift 0,0 고정」이었다.
            bx, by = anchor_dxy[c["frame"]]
            # 앵커 셀이 **실제로 앉은 자리**. `reference_top_left`가 아니다 — 그것은
            # 과녁이고, 이 값은 결과다. 둘이 같았던 것은 배치가 앵커를 구울 때뿐이다.
            _seat = c.get("_anchor_placed")
            _at = ((reference_top_left[0] + bx, reference_top_left[1] + by)
                   if _seat is None else (_seat[0] + bx, _seat[1] + by))
            # 🔴 네 번째 반환값을 **버리지 않는다.** 종전에는 `_hit`을 버렸고, 그것이
            #    「앵커가 옳았다」와 「자격 자리가 없어 포기했다」를 구별하는 유일한 값이었다
            #    (§RESIDUAL_* 어휘). 버린 결과 두 상태가 화면에서 같은 `shift: 0,0`이 됐다.
            rdx, rdy, _hit, c["_residual"] = _residual_shift(
                c["keys"] + bx * _KEY_STRIDE + by, ref_sorted, ref_pairs, _at,
                reference_walk_rank)
            # ═══ 🔴 REVERTED 2026-08-06 — 같은 날 회귀, 조작자 bisect가 증거 ══════════════
            # 「깃 헤드를 ec8c0e 로 옮기니까 잘되는데」. `ec8c0e7`은 오늘 서버 커밋 셋
            # (`17d8d00`·`fac206c`·`4947a65`) **이전**이다. 그리고 코드가 그 bisect를 좁힌다:
            # `4947a65` 이전의 앵커 갈래는 `dx, dy = anchor_dxy[c["frame"]]`였고 그 값은
            # **항등적으로 (0,0)**이다(그 커밋 자신의 실측). 그러므로 앵커 갈래에서 0이 아닌
            # 시프트를 낼 수 있는 생산자는 `_residual_shift` **하나뿐**이고, 조작자가 본
            # `(5,26)`은 여기서 나왔다.
            #
            # 🔴 **잔차는 내가 구성한 경우(웨이퍼 중간부터 도는 부분 맵)를 잡으려고 넣었고,
            #    실재하는 경우를 깨뜨렸다.** 조작자의 데이터에서는 앵커의 전제가 참이다 —
            #    작업이 웨이퍼 첫 유효 다이부터 시작하므로 앵커 자리가 이미 옳았고, 잔차가
            #    옳게 앉은 맵을 **옮겼다**.
            #
            # ⚠️ **함수와 그 논거 100줄은 지운다 그것을 다시 벌어들이는 라운드가 쓴다.**
            #    지금 바뀌는 것은 **적용하느냐**뿐이다: 관찰은 계속하고(`_residual`가 그대로
            #    실려 나간다) 자리는 앵커의 것을 쓴다. 「다른 자리가 더 맞았을 것」을 조작자가
            #    **보는** 것은 쓸모가 있고, 기계가 **조용히 가져가는** 것이 방금 일어난 일이다.
            if isinstance(c.get("_residual"), dict):
                c["_residual"]["would_move"] = (rdx, rdy)
                c["_residual"]["applied"] = False
            dx, dy = bx, by
        else:
            dx, dy, _hit = _solve_shift(c["keys"], ref_sorted, shift_window)
            # 탐색 갈래에도 이름을 준다 — 창의 크기가 답을 가둘 수 있고(옛 ±3 실패의 지문은
            # **창 끝에 붙은 값**이었다), 그 사실은 수치가 아니라 상태로 읽혀야 한다.
            c["_residual"] = {"state": PLACEMENT_SEARCH, "window": shift_window,
                              "at_window_edge": max(abs(dx), abs(dy)) >= shift_window}
        mem = _membership(c["keys"], ref_sorted, dx, dy)
        c.update(dx=dx, dy=dy, agreement=int(np.count_nonzero(mem)), scored=True,
                 member=mem)
        # ═══ [D12] 정준 좌표는 **앉힌 자리**에서 만든다, 선언된 자리가 아니라 ═══════════════
        # 적대 검수 실측 2026-08-06: 방향 판정이 `_phys`(앵커 이전 좌표)를 읽는 동안 판사는
        # 기준의 행으로 서 있었다. 앵커는 최소 순번 다이를 바닥 좌상단으로 옮기는데 그 이동이
        # 판정에 안 보였고, 판사의 행 방향은 **행 서수로 교대**하므로 홀수 서수 행에 선언된
        # 소스는 「왼쪽」이 합법이 되어 오른쪽 걸음이 전부 위반으로 세어졌다:
        #     행 20(짝수): rot0_front 위반 0 · rot270_front 1 → 좁혀짐
        #     행 21(홀수): rot0_front 위반 1 · rot270_front 1 → **넷 다 1** → 안 좁혀짐
        # 제품 소유자: 「오른쪽 진행이 1등이어야 하는데 270도랑 공동 1등」. 위치의 절반에서
        # 터졌고, 픽스처가 중앙 행(41행 중 20, 짝수)을 골라서 초록이었다.
        #
        # 🔴 그래서 시프트가 **풀린 뒤에** 정준화한다. 놓인 좌표는 기준의 시각 공간에 살므로
        #    기준의 사상(`_lc_ref`)을 한 번 더 태워 정준으로 돌린다 — 두 공간을 섞어 수를
        #    맞추지 않는다. 그 섞기가 오늘 하루를 만든 함정이다.
        if _lc_ref is not None and c.get("_placed") is not None:
            c["_phys"] = [map_overlay.apply_linear(_lc_ref, x + dx, y + dy)
                          for (x, y) in c["_placed"]]

    # [3a] 순번 일치: **이 셀이 몇 번째로 훑히는가 == 저장된 순번인가**, 셀마다.
    #
    # 🔴 **순서 일치는 시프트를 쓰지 않는다 — 쓸 수가 없다.** 훑기는 행을 y로 묶고 행 안을
    #    x로 정렬할 뿐이라 모든 셀을 (dx,dy)만큼 옮겨도 순서가 한 자도 안 바뀐다(실측
    #    2026-08-06: ±1000 오프셋에서 266/266 유지).
    #
    # ⚠️ **이 불변성은 `serpentine_rank`/`_index_member`에만 해당한다.** 방향 판정
    #    (`direction_violations`)은 후보의 행을 **기준의 행**에 대고 그 행의 교대 방향을
    #    읽으므로 평행이동에 **불변이 아니다** — 옮기면 어느 행에 앉는지가 바뀌고 합법
    #    방향도 같이 바뀐다. 새 함수가 이웃의 논거를 물려받았고 그 논거는 따라오지 않았다
    #    (적대 검수 2026-08-06, §[D12]). 그래서 방향 판정은 **앉힌 좌표**를 받는다.
    #
    # 🔴 **훑기는 맵 단위로 돈다.** 순번은 작업마다 자기 1..N을 다시 시작하므로(제품 소유자:
    #    「소스별로 index 매기는거잖아」) 단위에 맵이 둘이면 두 수열을 한 훑기에 담는 순간
    #    둘 다 틀린다. `cell_owner`가 셀마다 어느 맵인지를 나르고, base도 맵마다 따로 잡는다.
    #
    # 🔴 **원점은 관측된 최솟값으로 정규화한다.** `0..255`와 `1..266`이 둘 다 실재하고
    #    절대값은 아무것도 나르지 않는다 - 순서가 신호 전부다. 어느 base였는지는 진단이 말한다.
    #
    # 🔴 **번호를 안 실은 실행과 번호가 다 틀린 실행은 다른 사실이다.** `_use_indices`는 셀
    #    개수만큼 None을 채우므로 「순번 컬럼이 없다」도 비지 않은 리스트로 도착한다 - 그것을
    #    「순번이 있다」로 읽으면 여덟이 일치 0을 받고, 이 축이 가장 강한 축이라 **점유·값
    #    판정을 통째로 밀어내고** 0으로 순위를 낸다. 이 파일이 세 번 경고한 「없음을 0으로
    #    접기」가 새 축에서 재발한 자리이고, 기존 스위트가 이 형태로 25건 빨개져서 잡혔다.
    idx_k, idx_has, index_bases = _normalised_indices(source_indices, cell_owner)
    # 🔴 [2026-08-06] **「일어날 수 없다」와 「일어나면 아무 말도 안 한다」의 조합이 하루를
    #    쓰게 한다.** 아래 크기 가드는 순번 배열과 좌표 배열의 길이가 어긋나면 축을 통째로
    #    끄는데, 종전에는 그 사실이 어디에도 안 남아 `index_axis=absent`만 나갔다 —
    #    「순번 컬럼을 선언 안 했다」와 겉모습이 같다. 사유가 없으면 조작자는 config를
    #    고치러 가고, 고칠 것은 config가 아니다.
    index_size_mismatch = None
    for c in per_candidate:
        if (not c["scored"] or idx_has is None
                or len(c.get("_phys") or ()) != idx_has.size):
            if (c["scored"] and idx_has is not None
                    and len(c.get("_phys") or ()) != idx_has.size):
                index_size_mismatch = (c["frame"], len(c.get("_phys") or ()),
                                       int(idx_has.size))
            c["index_member"] = None
            continue
        c["index_member"] = _index_member(c["_phys"], cell_owner, idx_k, idx_has)

    # [3a-2] 걸음의 **방향**. 순서 일치가 못 가르는 자리를 가른다(§direction_violations).
    #        판사는 기준 바닥이고, 그것은 순번 훑기와 **같은 정준 좌표계**에서 읽는다.
    # 🔴 판사는 **기준의 셀 목록**에서 나온다, phys가 아니라(총괄 판정 2026-08-06 Ruling 1).
    #    묻는 것은 「이 다이 오른쪽에 기준의 다이가 더 있었나」이고, 그것은 셀 집합의 사실이지
    #    밀리미터의 사실이 아니다. 행으로 묶어 min/max x를 잡으면 끝이고, 소스와 기준이 같은
    #    사상(`_lc_ref`)을 타므로 어느 공간이든 **행은 행으로 묶인다** — 절대냐 상대냐가
    #    문제가 되지 않는다. 판사가 phys를 찾아간 것은 셀 목록이 이미 답하는 질문을 물으러
    #    간 것이고, 그것이 이 라운드 전체와 같은 모양이다.
    _judge = direction_judge(_canon_ref) if _canon_ref else None
    for c in per_candidate:
        if c.get("index_member") is None or _judge is None:
            c["index_violations"] = None
            c["index_steps"] = None
            continue
        c["index_violations"], c["index_steps"] = direction_violations(
            c["_phys"], cell_owner, idx_k, idx_has, _judge)

    # [3b] 값 일치: 이 후보가 앉힌 자리의 **기준 값과 소스 값이 같은가**, 셀마다.
    #      기준이나 소스에 값이 없으면 **None이지 0이 아니다.** 0으로 내보내면 「값으로 재
    #      보았고 하나도 안 맞았다」가 되어 「값으로 잴 수 없었다」의 정반대를 말한다.
    #
    # 🔴 [2026-08-06] **「값을 실었다」는 「값을 견줄 수 있다」가 아니다.** `reference.kind`가
    #    `values`인 것은 양쪽에 값 컬럼이 있다는 뜻일 뿐이다. 여기서 갈리는 두 가지를
    #    종전에는 둘 다 못 봤고, 둘 다 **같은 증상**으로 나왔다 - 일치 0 → `no_overlap` →
    #    화면은 기하 실패로 읽는다. 조작자가 하루를 앉아 있던 이유가 그것이다.
    #      ⓐ 기준 값 컬럼이 통째로 NULL이다. `ref_value_at`은 좌표마다 키가 있으므로
    #         **비어 있지 않고**, 값만 전부 None이다 → 종전 관문을 그대로 통과했다.
    #      ⓑ 두 어휘가 하나도 안 겹친다. 유효 다이 바닥의 낱말(`'1'`·`'E1'`)은 bin 코드
    #         (`'B1'`·`'0'`·`'2'`)가 아니다. 어느 프레임 어느 좌표에서도 같을 수 없다.
    #    둘 다 **거절이 아니라 강등**이다(제품 소유자 판정: 기능은 일단 돈다) - 값 축은
    #    수치를 그대로 싣되 순위를 가져가지 않고, 점유로 내려앉으며, 사유를 이름으로 낸다.
    ref_has_value = any(v is not None for v in ref_value_at.values())
    scorable_values = bool(ref_value_at) and ref_has_value and bool(source_values) and \
        any(v is not None for v in source_values)
    # 🔴 어휘 교집합은 **⑴의 정규화를 거친 뒤에** 잰다. 정규화 전 교집합으로 판정하면
    #    `2.0`/`'2'`만 공유하는 실제 데이터를 「겹치는 것 없음」이라 부르고 강등해 버린다 -
    #    방금 고친 결함으로 다음 결함을 만드는 꼴이다.
    value_vocab_shared = None
    if scorable_values:
        ref_keys_v = {_value_key(v) for v in ref_value_at.values() if v is not None}
        src_keys_v = {_value_key(v) for v in source_values if v is not None}
        value_vocab_shared = ref_keys_v & src_keys_v
    value_axis_reason = (
        None if scorable_values and value_vocab_shared
        else VALUE_AXIS_REF_ALL_NULL if bool(ref_value_at) and not ref_has_value
        else VALUE_AXIS_DISJOINT if scorable_values else None)
    for c in per_candidate:
        if not c["scored"] or not scorable_values:
            c["value_member"] = None
            continue
        shifted = c["keys"] + c["dx"] * _KEY_STRIDE + c["dy"]
        hits = np.zeros(c["keys"].size, dtype=bool)
        member = c["member"]
        # Worked-example rows for this candidate, by cell index. Only the traced
        # indices are picked up, and only where a comparison actually happened —
        # a cell that is not on the reference is never compared, and the log says
        # that rather than inventing a verdict for it.
        t_at = ({r["at"]: r for r in (c.get("_trace") or ())}
                if _dg is not None else None)
        for i in np.flatnonzero(member):
            rv = ref_value_at.get(int(shifted[i]))
            sv = source_values[i] if i < len(source_values) else None
            hits[i] = values_equal(rv, sv)
            if t_at is not None and int(i) in t_at:
                key = int(shifted[i])
                t_at[int(i)].update(
                    ref_value=rv, src_value=sv, verdict=bool(hits[i]), compared=True,
                    # Decoded from the very key the lookup used (inverse of
                    # `_encode`), not re-derived from the candidate's shift.
                    probe=(key // _KEY_STRIDE - _KEY_BIAS, key % _KEY_STRIDE - _KEY_BIAS))
        c["value_member"] = hits

    # [3c] 값 가중치 - **일치에 걸리지, 셀의 존재에 걸리지 않는다.**
    #
    # 🔴 이 구분이 이 기능의 전부다. 「이 셀이 기준 위에 있다」는 부분 맵의 모든 셀에 대해
    #    여덟 후보 **모두** 참이므로(실측 2026-08-05: 일치 467 · 판별 0 · 8후보 동일),
    #    거기에 무게를 주면 여덟이 같은 배수로 커지고 순위는 한 자리도 안 움직인다.
    #    후보마다 갈리는 것은 「이 값이 이 자리에서 **맞았는가**」 하나뿐이고, 무게는 거기
    #    걸려야 대칭을 깬다. 그래서 곱하는 대상은 `member`가 아니라 `value_member`다.
    #
    # 무게는 **소스 셀의 값**으로 찾는다. 일치한 자리에서는 기준 값과 소스 값이 같으므로
    # 둘 중 무엇으로 찾아도 같은 수가 나오고, 안 맞은 자리는 애초에 세지 않는다.
    # 선언 없는 값은 1이다. 선언된 0은 0이고, 그 둘은 다른 주장이다(§load_alignment_value_weights).
    #
    # 🔴 값 축이 순위를 못 가져가면 **무게도 걸지 않는다.** 무게는 값 일치를 배로 키우는
    #    장치인데 그 일치가 순위에 안 쓰이면 배수만 늘고 판정은 그대로다 - 그리고 축 이름이
    #    `values_weighted`가 되어 화면이 「무게로 뽑은 1등」이라고 말한다. 안 쓴 축의 이름을
    #    판정에 다는 것은 이 파일이 반복해서 막는 「없는 것을 있다고 말하기」다.
    weights = value_weights or {}
    weight_vec = None
    if weights and scorable_values and value_axis_reason is None:
        weight_vec = np.array(
            [(float(weights.get(str(v), 1.0)) if v is not None else 1.0)
             for v in (source_values or [])], dtype=float)

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
    index_varies = _varies("index_member")
    # 🔴 분모는 **후보와 무관하다.** k번을 가진 셀은 어느 후보에서도 k번을 갖는다 - 후보가
    #    바꾸는 것은 맞았는가지 셀 수가 아니다. 후보마다 분모를 따로 세면 여덟이 서로 다른
    #    분수를 보고하고, 그러면 「높은 비율」이 무엇에 대한 비율인지 화면이 말할 수 없다.
    index_total = 0 if idx_has is None else int(np.count_nonzero(idx_has))
    for c in per_candidate:
        if c["member"] is None or varies is None:
            c["discriminating"] = 0
        else:
            c["discriminating"] = int(np.count_nonzero(c["member"] & varies))
        # 순번 축. **비율이 아니라 분자와 분모 둘 다** 낸다 - 번호는 이 맵이 실제로 그
        # 유효 다이 지도에 대해 매겨졌을 때만 완전 일치이고, 조작자가 고른 기준이 그 지도와
        # 조금 다르면 답은 「높은 비율」이지 「실패」가 아니다. 비율 하나로 접으면 그 차이가
        # 사라지고, 사라진 자리에서 조작자는 기준이 어긋났다는 사실을 알 방법이 없다.
        if c.get("index_member") is None:
            c["index_agreement"] = None
            c["index_discriminating"] = None
            c["index_total"] = None
        else:
            c["index_agreement"] = int(np.count_nonzero(c["index_member"]))
            c["index_discriminating"] = (
                0 if index_varies is None
                else int(np.count_nonzero(c["index_member"] & index_varies)))
            c["index_total"] = index_total
        if c.get("value_member") is None:
            c["value_agreement"] = None
            c["value_discriminating"] = None
        elif weight_vec is None:
            c["value_agreement"] = int(np.count_nonzero(c["value_member"]))
            c["value_discriminating"] = (
                0 if value_varies is None
                else int(np.count_nonzero(c["value_member"] & value_varies)))
        else:
            # 🔴 **분자와 판별수는 같이 움직인다.** 일치만 가중하고 판별수를 개수로 두면
            #    `min_discriminating_dies`가 어제와 다른 것을 세면서 어제와 같은 이름으로
            #    불린다 - 조작자가 안 건드린 문턱의 뜻이 조용히 바뀐다. 두 수는 가중이
            #    걸리면 **둘 다** 「가중 다이」이고, 안 걸리면 **둘 다** 다이 개수다.
            w = _fit_weights(weight_vec, c["value_member"].size)
            c["value_agreement"] = float(w[c["value_member"]].sum())
            c["value_discriminating"] = (
                0.0 if value_varies is None
                else float(w[c["value_member"] & value_varies].sum()))

    # [5] 순위와 판정. **개수만** 낸다 — 백분율을 만들지 않는다(모듈 상단).
    #
    # 🔴 2위는 **채점된 후보 중에서만** 고른다. 채점되지 않은 후보의 일치수 0은 잰 값이 아니라
    #    자리 표시이고, 그것을 2위로 삼으면 혼자 채점된 후보가 자기 일치수를 통째로 「격차」로
    #    보고한다 - 있지도 않은 비교로 만든 수다. 비교할 상대가 없으면 격차는 **null이지 0도,
    #    자기 점수도 아니다**(문턱 비교는 null을 이미 거절로 다룬다).
    scored_i = [i for i, c in enumerate(per_candidate) if c["scored"]]
    out = []
    for i0, c in enumerate(per_candidate):
        others = [per_candidate[i]["agreement"] for i in scored_i if i != i0]
        runner = max(others) if others else None
        v_others = [per_candidate[i]["value_agreement"] for i in scored_i
                    if i != i0 and per_candidate[i]["value_agreement"] is not None]
        v_runner = max(v_others) if v_others else None
        k_others = [per_candidate[i]["index_agreement"] for i in scored_i
                    if i != i0 and per_candidate[i].get("index_agreement") is not None]
        k_runner = max(k_others) if k_others else None
        rot_side = parse_frame(c["frame"])
        # 🔴 안 본 후보는 **못 잰 후보가 아니다.** 셋을 한 낱말로 접으면 화면이 「선언이
        #    빼서 안 봤다」와 「보려 했는데 변환이 거절했다」를 같게 그린다.
        if c.get("not_considered"):
            state = STATE_NOT_CONSIDERED
        elif c["scored"]:
            state = STATE_SCORED
        else:
            state = STATE_NOT_SCORABLE
        out.append({
            "frame": c["frame"],
            "rotation": rot_side[0], "side": rot_side[1],
            "state": state,
            "shift": None if not c["scored"] else {"dx": c["dx"], "dy": c["dy"]},
            "agreement": c["agreement"],
            "discriminating": c["discriminating"],
            # 순번 축. 분자·분모를 **둘 다** 싣는다(§[4]) — 비율은 화면이 만들고 서버는
            # 세는 것만 낸다(모듈 상단: 백분율이 순위를 뒤집은 적이 있다).
            "index_agreement": c.get("index_agreement"),
            "index_discriminating": c.get("index_discriminating"),
            "index_total": c.get("index_total"),
            # 걸음의 방향(§direction_violations). 🔴 **작을수록 좋다** — 이 파일에서 유일하게
            # 방향이 반대인 수이고, 분모(`index_steps`)를 옆에 실어 「0 위반」이 잰 결과인지
            # 잴 것이 없었던 것인지 화면이 구별할 수 있게 한다.
            "index_violations": c.get("index_violations"),
            "index_steps": c.get("index_steps"),
            # ═══ [D11] 화면이 그리는 재료. **서버가 이미 계산한 배치**이지, 클라가 그것을
            #     다시 유도할 파라미터가 아니다. 이 구분이 이 필드의 전부다:
            #       · `rotation`/`side`/`grid_y_invert`/`phys`/`dims`/`start`를 보내면 받는
            #         쪽이 **합성을 다시** 해야 하고, 실제로 틀렸다 — `grid_y_invert`가 어느
            #         프레임이 거울인지를 뒤집는데 클라는 그 순서를 거꾸로 잡았다.
            #       · `linear`는 그 합성의 **결과**다. 다시 할 것이 없으므로 틀릴 것도 없다.
            #     그리기: `placed = anchor_ref + linear · (cell − anchor_src)`.
            #     🔴 거울 여부는 `det(linear) == -1`이고 **따로 싣지 않는다** — 유도되는
            #        사실을 유도원 옆에 두면 언젠가 갈린다.
            #     🔴 `grid_start`는 **여기 없다**(제품 소유자: 「화면에 표시하지는 않되 저장은
            #        하기」). 앵커 쌍 옆에 파생값을 같이 보이면 조작자가 「어느 쪽이 정본인가」를
            #        중재하게 되는데, 둘은 같은 사실의 두 철자다 — 레거시 독자용과 재구성용.
            # 🔴 [D13] 실어 보내는 자리는 **채점이 앉힌 자리**다 — 선언된 과녁이 아니라.
            #    화면은 `anchor_ref + linear·(cell − anchor_src)`로 그리므로, 시프트를 여기
            #    안 더하면 서버는 옮겨서 채점하고 화면은 안 옮겨서 그린다. 그 갈림은 조용하다:
            #    두 그림이 다 그럴듯하고 개수만 안 맞는다(§_residual_shift).
            # 🔴 REVERTED 2026-08-06: 종전 식은 `reference_top_left + (dx,dy)`였고, 그것이
            #    맞았던 것은 배치가 앵커를 구워 `placed[i_min] ≡ reference_top_left`였을
            #    때뿐이다. 배치가 변환 전용으로 돌아온 지금 앵커가 앉는 자리는 **변환이 놓은
            #    자리에 시프트를 더한 값**이고, 과녁(`reference_top_left`)과 다르다. 그래서
            #    유도원을 바꾼다 — 그리는 쪽이 읽는 것은 과녁이 아니라 결과여야 한다.
            "placement": (None if c.get("_linear") is None or anchor_cell is None
                          or c.get("_anchor_placed") is None else {
                "linear": [list(c["_linear"][0]), list(c["_linear"][1])],
                "anchor_src": list(anchor_cell),
                "anchor_ref": [c["_anchor_placed"][0] + (c.get("dx") or 0),
                               c["_anchor_placed"][1] + (c.get("dy") or 0)]}),
            "index_margin": (None if c.get("index_agreement") is None or k_runner is None
                             else int(c["index_agreement"] - k_runner)),
            # 값 지표는 **점유를 대체하지 않는다.** 기준이 값을 안 실으면 점유가 정직한 답이고,
            # 그때 이 셋은 null이다(0이 아니다 — §[3b]).
            "value_agreement": c["value_agreement"],
            "value_discriminating": c["value_discriminating"],
            # 뺄셈이 타입을 정한다. 가중이 없으면 두 항이 int라 종전과 같은 int가 나오고,
            # 가중이 걸리면 float다 - `int()`로 접으면 가중 격차의 소수부가 조용히 잘려
            # 문턱 비교가 실제보다 후하게 통과한다.
            "value_margin": (None if c["value_agreement"] is None or v_runner is None
                             else (c["value_agreement"] - v_runner)),
            # 🔴 **`shift`가 무엇을 뜻하는지는 `shift`가 말하지 못한다.** `(0,0)`은 「앵커가
            #    옳았다」·「자격 자리가 없었다」·「둘 이상이라 못 골랐다」·「물을 수 없었다」
            #    넷 중 하나이고, 넷은 서로 다른 수리를 가리킨다(§RESIDUAL_*). 관측 전용이고
            #    판정에 안 쓰인다 — 화면이 「0,0인데 왜 0,0인가」에 답할 수 있게 하는 것이
            #    이 필드의 전부다.
            "residual": c.get("_residual"),
            "placed": 0 if c["keys"] is None else int(c["keys"].size),
            "margin": (None if not c["scored"] or runner is None
                       else int(c["agreement"] - runner)),
            "reason": (TEXT_SIDE_NOT_CONSIDERED if c.get("not_considered")
                       else c["reason"]),
        })

    # 🔴 축 이름이 **가중 여부까지 나른다.** 옆에 `weighted: true`를 두면 판정을 옮겨 적는
    #    자리(확정 기록·목록)가 그것을 흘리고, 무게 아래 뽑힌 1등이 무게 없이 뽑힌 1등과
    #    같아 보인다 - `geometry_assumed`를 판정 dict 안에 넣은 이유와 같은 이유다.
    #
    # 🔴 순번은 **선언이 있을 때만 이긴다.** 점유와 값은 둘 다 두 미지 사이의 관계라
    #    어느 쪽도 방위를 고정하지 못하지만(그래서 부분 맵에서 판별 0이 났다), 순번은 정준
    #    방위에 대한 절대 진술이다. 약한 축이 강한 축을 이기면 순위는 재현되되 틀린다.
    # 🔴 **컬럼이 있다는 사실은 순위를 가져갈 자격이 아니다.** 종전에는 순번 수치가 하나라도
    #    있으면 축이 순위를 가져갔다 - 「없음을 0으로 접기」의 거울상이고, 이 파일이 경고하는
    #    실패의 같은 형태다: 존재가 판정으로 접혔다. 순번이 다른 질문에 답하는 축인 것은
    #    맞지만, **그 질문이 이 데이터에 성립할 때만** 더 강하다(§INDEX_THRESHOLD_BLOCK).
    #    성립을 코드가 알 수 없으므로 선언이 답한다.
    scorable_indices = any(c.get("index_agreement") is not None for c in per_candidate)
    index_ranks = scorable_indices and index_thresholds_complete(index_thresholds)
    # 🔴 **잰 것과 순위를 낸 것은 다르다** — 값 축도 순번 축과 같은 규율을 받는다.
    #    `scorable_values`는 「비교를 돌렸다」이고, `value_ranks`는 「그 비교가 뜻이 있다」이다.
    #    둘을 한 낱말로 접었던 것이 이 라운드의 결함 ⓐ·ⓑ였다(§[3b]).
    value_ranks = scorable_values and value_axis_reason is None
    metric = (METRIC_INDEX if index_ranks
              else METRIC_VALUES_WEIGHTED if weight_vec is not None
              else METRIC_VALUES if value_ranks else METRIC_OCCUPANCY)
    # 후보들은 **같은 소스 셀을 같은 순서로** 놓으므로 놓인 개수는 후보마다 같다. max는 그 사실에
    # 기대지 않고도 「무엇이든 놓였는가」를 답한다.
    placed_cells = max((int(c["keys"].size) for c in per_candidate
                        if c["keys"] is not None), default=0)
    ex_rows = excluded.as_list()
    # 순위 축이 자기 문턱을 읽는다. 축마다 세는 단위가 다르므로 문턱도 축을 따라간다 —
    # 한 dict를 돌려 쓰면 같은 이름의 수가 축마다 다른 것을 세면서 같은 이름으로 불린다.
    ruling = _rule_on(out, index_thresholds if metric == METRIC_INDEX else thresholds,
                      metric, scoring={
        "placed_cells": placed_cells,
        # 🔴 **「도달했는가」와 「놓였는가」는 다른 수다.** 놓인 좌표는 여덟 후보가 전부 변환을
        #    거절하면 0이 되는데(`keys is None`이라 max가 default 0을 낸다), 그 0은 좌표가
        #    안 왔다는 뜻이 아니라 **거절당했다**는 뜻이다. 이 수를 안 넘기면 판정기는 두
        #    사실을 구별할 재료가 없다 - 실측(2026-08-05) 결과 그래서 `no_candidate_scored`가
        #    그 갈래에서 도달 불가능했고, 기준 맵의 규격이 없어 여덟이 전부 거절된 실행이
        #    「소스 좌표 미도달」로 나갔다. 조작자의 좌표는 멀쩡했고 고칠 것은 기준이었다.
        "scored_cells": scored_cells,
        "source_map_count": len(source_maps),
        "excluded_map_count": excluded.total(),
        "excluded_reason_code": (ex_rows[0]["reason_code"] if ex_rows else None),
    })
    # 🔴 [D3] **가정 아래에서 나온 판정은 다른 사실이다.** 판정 dict 자신이 그 사실을 나른다 -
    #    옆 필드에만 두면 판정을 옮겨 적는 자리(확정 기록·목록)가 그것을 흘린다. 참일 때만
    #    싣는 것이 아니라 **언제나** 싣는다: 없는 키와 False는 받는 쪽에서 같아 보인다.
    # 🔴 **좁힌 탐색 공간은 판정 자신의 사실이다.** 넷 중 1등과 여덟 중 1등은 다른 주장이고,
    #    판정을 옮겨 적는 자리(확정 기록·목록)가 옆 필드를 흘리면 그 구별이 사라진다 -
    #    `geometry_assumed`·`metric`을 판정 dict 안에 넣은 것과 같은 이유다. 참일 때만 싣는
    #    것이 아니라 **언제나** 싣는다: 없는 키와 「둘 다」는 받는 쪽에서 같아 보인다.
    # 🔴 **어휘 순서**로 낸다, 알파벳순이 아니라. `load_alignment_sides`가 이미 어휘 순서로
    #    정규화하는데 여기서 `sorted()`를 쓰면 같은 주장이 `["front","back"]`과
    #    `["back","front"]` 두 철자를 갖는다 - 이 파일이 반복해서 막는 「하나의 사실에 두
    #    철자」이고, 받는 쪽이 목록을 비교하는 순간 같은 선언이 달라 보인다.
    # 🔴 **쟀는데 순위를 안 냈다**는 것은 조작자에게 필요한 사실이다. 후보 행에는 순번
    #    수치가 실려 나가므로, 이 사실이 없으면 화면은 그 수치가 판정을 만들었다고 읽는다.
    #    세 상태를 한 낱말로 접지 않는다: 「잰 것이 없다」·「쟀지만 순위는 안 냈다」·
    #    「이 축이 순위다」는 서로 다른 수리를 부른다(각각 순번 컬럼 선언 / 문턱 선언 / 없음).
    ruling["index_axis"] = (INDEX_AXIS_RANKING if index_ranks
                            else INDEX_AXIS_REPORTED if scorable_indices
                            else INDEX_AXIS_ABSENT)
    # 값 축도 자기 상태를 나른다. 세 상태가 서로 다른 수리를 부른다: 값 컬럼 선언 /
    # 값 컬럼 내용 수리(NULL·어휘) / 없음.
    ruling["value_axis"] = (VALUE_AXIS_RANKING if metric in VALUE_METRICS
                            else VALUE_AXIS_REPORTED if scorable_values
                            else VALUE_AXIS_ABSENT)
    ruling["value_axis_reason"] = value_axis_reason
    # 🔴 **평행이동을 누가 정했는가**는 판정의 사실이다(§PLACEMENT_ANCHOR). 앵커로 놓인
    #    배치와 포화한 탐색이 동점 규칙으로 놓은 배치를 한 모양으로 내보내면, 화면은
    #    「266 일치」를 같은 뜻으로 그린다 - 하나는 데이터가 놓은 것이고 하나는 아니다.
    ruling["placement"] = (PLACEMENT_ANCHOR if anchor_dxy is not None
                           else PLACEMENT_SEARCH)
    ruling["anchor_reason"] = anchor_reason if anchor_dxy is None else None
    # 🔴 **화면이 그리는 자리는 채점이 쓴 자리여야 한다** (제품 소유자 2026-08-06:
    #    「되긴 하는데 화면에 다른 shift가 뜨는 듯, 계산에 사용된 거 말고」).
    #
    #    이 값은 **다시 계산하지 않는다** — 이긴 후보 행에서 **읽는다**. 같은 사실을 두 번
    #    유도하면 그 둘은 갈리고, 이 코드베이스는 오늘 하루에 그 형태로 세 번 물렸다. 그래서
    #    철자는 `candidates[].shift` 하나이고 이것은 그 중 이긴 행을 **가리키는** 사본이다.
    #    관계는 테스트가 단언한다(`test_the_shipped_placement_is_the_scored_placement`):
    #    실린 오프셋으로 멤버십을 다시 재면 실린 `agreement`가 그대로 나와야 한다.
    #
    #    🔴 앵커가 (0,0)을 낼 수도 있고 그것은 **탐색이 아무것도 못 찾아 원점으로 떨어진 것과
    #    다른 사실**이다. 그래서 `placement`가 옆에 함께 실린다 - 수만 보면 두 경우가 같다.
    _win_row = next((o for o in out if o["frame"] == ruling.get("winner")), None)
    ruling["shift"] = (_win_row or {}).get("shift")
    # 🔴 **확정이 원점을 적으려면 앵커 쌍이 있어야 하고, 앵커 쌍은 이 경로로만 그리 간다.**
    #    `/api/maps/alignment/confirm`은 판정을 다시 내지 않는다 — 화면이 `ruling`을 **통째로**
    #    전사해 되돌려 보내는 것이 계약이고(라우트 docstring [D-2] · `map2/decode.js:448`이
    #    키를 가리지 않고 얕은 복사한다), 그래서 여기 붙는 키는 클라를 한 줄도 안 고치고
    #    확정 경로에 도착한다. 승자 행에서 **읽는다** — `shift`와 같은 규율이고, 두 번째
    #    유도를 만들면 그 둘이 갈리는 날 기록된 시프트와 저장된 원점이 다른 배치를 가리킨다.
    #    ⚠️ 이름이 `placement`가 아닌 이유: `ruling["placement"]`는 이미 **낱말**
    #    (`anchor`/`shift_search`)이라 같은 키에 dict을 실으면 그 어휘가 조용히 깨진다.
    ruling["anchor"] = (_win_row or {}).get("placement")
    ruling["sides_considered"] = [s for s in FRAME_SIDES if s in considered]
    ruling["sides_narrowed"] = len(considered) < len(FRAME_SIDES)
    ruling["geometry_assumed"] = bool(assumed_ids)
    ruling["assumed_map_count"] = len(assumed_ids)
    stats = {"scored_cells": scored_cells, "truncated": truncated,
             "cell_cap": cell_cap, "shift_window": shift_window,
             "reference_cells": int(ref_sorted.size),
             "reference_values": len(ref_value_at),
             # 순번 채점의 재료. 🔴 `reference_indices`는 이제 **채점에 안 쓰인다** —
             # 훑기가 소스 자신의 셀 위에서 돌기 때문이다. 남겨 두는 이유는 앵커가 이
             # 훑기의 1번 자리를 쓰기 때문이고, 그 사실이 이 수의 유일한 뜻이다.
             "reference_indices": len(reference_walk),
             "source_indices_usable": index_total,
             # 관측된 순번 base(맵마다). `0..255`인지 `1..266`인지를 화면과 로그가 같이 본다.
             "index_bases": {str(k): v for k, v in (index_bases or {}).items()},
             # 값 축이 순위를 못 가져갔으면 **왜인지**가 stats에도 있다 - 판정만 보는 자리와
             # 통계만 보는 자리가 서로 다른 이야기를 하지 않게.
             "value_axis_reason": value_axis_reason,
             "value_vocab_shared": (None if value_vocab_shared is None
                                    else len(value_vocab_shared)),
             "placement": ruling.get("placement"),
             "anchor_reason": ruling.get("anchor_reason"),
             "source_maps_usable": len(usable),
             "placed_cells": placed_cells,
             # 「가정을 걸었다」와 「가정을 걸 수 있었다」는 다른 수다. 뒤엣것이 없으면 화면은
             # 제안을 그릴 수 없고, 제외된 맵은 그냥 막다른 길로 남는다.
             "assumed_map_ids": list(assumed_ids),
             "assumable_map_ids": list(offerable_ids),
             # [D4] 바닥이 선언이 아니어서 **아예 제안조차 못 한** 맵들. 제외 집계에는
             # 없다 - 이것은 이 맵들의 사실이 아니라 바닥 한 장의 사실이고, 호출자가
             # `compose_basis_refusal`로 요청 단위에 한 번 말한다.
             "basis_undeclared_map_ids": list(basis_undeclared_ids),
             # 「어느 맵이 실제로 바닥에 올라갔나」. `geometry_basis_of`의 유일한 입력이라
             # 화면과 확정 기록이 같은 집합을 본다.
             "usable_map_ids": [sm.get("map_id") for sm in usable],
             "elapsed_ms": (time.monotonic() - t0) * 1000.0}

    if _dg is not None:
        _dg += _diag_scoring_block(
            per_candidate, out, ruling, stats, excluded, metric, scorable_values,
            reference_meta, reference_values, source_values, weight_vec,
            scored_cells, truncated, cell_cap, shift_window, len(ref_sorted),
            len(source_maps), len(usable))
        _dg += _diag_index_block(per_candidate, out, ruling, source_indices,
                                 cell_owner, idx_k, idx_has, index_bases,
                                 reference_top_left, anchor_reason, usable,
                                 index_size_mismatch)
    return out, excluded, ruling, stats


#: 진단이 찍어 보이는 순번 표본 개수. 「처음 몇 개」면 충분하다 — 어긋남은 첫 셀부터 난다.
_DIAG_INDEX_CELLS = 8


def _diag_index_block(per_candidate, out, ruling, source_indices, cell_owner,
                      idx_k, idx_has, index_bases, reference_top_left,
                      anchor_reason, usable, index_size_mismatch=None) -> list:
    """순번 축의 계산을 **그대로 보여 준다** — 훑기가 매긴 번호 대 저장된 번호.

    제품 소유자가 이 파일을 읽어 이 축을 이해하고 있으므로(총괄 지시 2026-08-06), 새 계산은
    말로 설명하지 않고 **숫자로** 보인다: 후보마다 처음 몇 셀의 물리 좌표 · 훑기가 매긴
    번호 · 저장된 번호(정규화 전/후) · 일치 여부.

    관측 전용이다. 여기서 다시 훑는 것은 **채점기가 훑은 그 좌표 배열**(`_phys`)이므로 두
    번째 구현이 아니라 같은 입력의 재출력이고, 값을 하나도 만들지 않는다.
    """
    L = ["", "-- index axis (serpentine over the SOURCE's own dies) --------------------",
         "  computation: place the source's cells under the candidate frame -> canonical",
         "               (physical) coords -> walk them serpentine, top row first, first",
         "               row left-to-right -> that walk position IS the expected index.",
         "               The reference is NOT consulted (changed 2026-08-06); the walk is",
         "               translation-invariant, so no shift enters this axis."]
    # 🔴 크기 어긋남은 **소리를 낸다.** 이 갈래는 config 문제가 아니라 내부 정합 문제이고,
    #    사유 없이 `absent`만 나가면 조작자가 선언을 고치러 간다 - 고칠 것이 거기 없다.
    if index_size_mismatch is not None:
        L.append("  🔴 INTERNAL: the index array and the coordinate array disagree in length "
                 "(frame=%s, cells=%d, indices=%d). The axis was switched off for that "
                 "reason, NOT because an index column is undeclared. This is a server-side "
                 "defect - report it; changing config will not move it."
                 % index_size_mismatch)
    if idx_has is None:
        L.append("  no cell carries an index -> axis dark (null, not zero). "
                 "ruling.index_axis=%s" % ruling.get("index_axis"))
        return L
    import numpy as np
    n_num = int(np.count_nonzero(idx_has))
    raw = [k for k in (source_indices or ()) if k is not None]
    L += ["  cells carrying an index: %d of %d   stored range: %s..%s"
          % (n_num, idx_has.size, min(raw) if raw else "-", max(raw) if raw else "-"),
          "  origin normalised by the OBSERVED MINIMUM, per source map: %s"
          % ({("map[%d] %s" % (m, _d((usable[m] or {}).get("map_id"), 20)
                               if m < len(usable) else "?")): "base %s -> 1" % b
              for m, b in sorted((index_bases or {}).items())} or "-"),
          "  contiguity: %s"
          % ("1..%d with no gaps" % len(set(raw))
             if raw and len(set(raw)) == (max(raw) - min(raw) + 1)
             else "GAPPED - %d distinct values spanning %d; a walk numbers 1..N with no "
                  "gaps, so a gapped column cannot fully agree under ANY frame"
                  % (len(set(raw)), (max(raw) - min(raw) + 1) if raw else 0)),
          "  anchor (min-index die -> reference top-left valid die): %s"
          % ("reference top-left = %s, placement=%s" % (reference_top_left,
                                                        ruling.get("placement"))
             if anchor_reason is None
             else "NOT APPLIED (%s) -> placement=%s" % (anchor_reason,
                                                        ruling.get("placement")))]
    # 🔴 [D13] 잔차는 **소리를 낸다.** 0이 아니라는 것은 「이 작업은 웨이퍼 좌상단부터 돌지
    #    않았다」는 뜻이고, 종전에는 그 사실이 어디에도 안 남아 시프트가 언제나 0,0으로 찍혔다.
    _resid = {o["frame"]: (o.get("shift") or {}) for o in out}
    _moved = {f: (s.get("dx"), s.get("dy")) for f, s in _resid.items()
              if (s.get("dx"), s.get("dy")) not in ((0, 0), (None, None))}
    _would = {f: r["would_move"] for f, r in
              ((c["frame"], c.get("_residual")) for c in per_candidate)
              if isinstance(r, dict) and r.get("would_move") not in (None, (0, 0))}
    if anchor_reason is None and _would:
        # 🔴 REVERTED: 관찰은 하되 적용하지 않는다(§callsite). 이 줄이 「기계가 옮겼다」에서
        #    「기계가 다른 자리를 봤지만 안 옮겼다」로 바뀐 것이 이 라운드의 전부다.
        L.append("  %s: a different seat would have fit (%s) but was NOT applied - the seat "
                 "is the anchor's. Reverted 2026-08-06 after this moved a correctly seated "
                 "map on live data (operator bisect to ec8c0e7)."
                 % (ANCHOR_SEAT_CORRECTED, _would))
    # 🔴 **움직이지 않은 후보도 소리를 낸다.** 종전에는 위 한 줄이 전부라 잔차가 0이면 로그가
    #    조용했고, 그래서 「앵커가 옳았다」와 「자격 자리가 하나도 없어 포기했다」가 운영자에게
    #    같은 침묵이었다. 그 침묵이 「shift 0,0」 신고가 진단으로 바뀌지 못한 이유다.
    #    관문은 **하나씩** 낸다 — 합집합만 보면 전부 떨어뜨린 관문과 안 돈 관문이 똑같이 생겼다.
    _res_rows = [(c["frame"], c.get("_residual")) for c in per_candidate
                 if isinstance(c.get("_residual"), dict)]
    if _res_rows:
        L.append("  residual seat search, per candidate "
                 "(state | seats scanned | gate1 all-cells-on-valid-dies | "
                 "gate2 unbroken-walk-run | best occupancy and how many seats tie there):")
        for frame, r in _res_rows:
            if r.get("state") == PLACEMENT_SEARCH:
                L.append("    %-14s %-26s window=+/-%s%s"
                         % (frame, r["state"], r.get("window"),
                            "  AT WINDOW EDGE - the answer may lie outside the window"
                            if r.get("at_window_edge") else ""))
                continue
            L.append("    %-14s %-26s seats=%-5s gate1=%-5s gate2=%-5s best=%s/%s tied=%s%s"
                     % (frame, r.get("state"), r.get("seats_scanned"),
                        r.get("gate1_on_valid_dies"), r.get("gate2_unbroken_run"),
                        r.get("best_hit"), (out[0]["placed"] if out else "?"),
                        r.get("best_tied"),
                        "   <-- seats scored the maximum but NONE qualified"
                        if (r.get("state") == RESIDUAL_NO_QUALIFYING_SEAT
                            and r.get("gate1_on_valid_dies")) else ""))
    for c, o in zip(per_candidate, out):
        if c.get("index_member") is None:
            continue
        phys = c.get("_phys") or []
        rank_by_map = {}
        owner = cell_owner or [0] * len(phys)
        for i in range(len(phys)):
            rank_by_map.setdefault(owner[i] if i < len(owner) else 0, []).append(i)
        ranks = {}
        for m, rows in rank_by_map.items():
            ranks.update({i: serpentine_rank([phys[j] for j in rows],
                                             top_is_min_y=True).get(tuple(phys[i]))
                          for i in rows})
        shown = [i for i in range(len(phys)) if idx_has[i]][:_DIAG_INDEX_CELLS]
        L.append("  %-14s agreement=%s/%s  discrim=%s%s"
                 % (o["frame"], o.get("index_agreement"), o.get("index_total"),
                    o.get("index_discriminating"),
                    "   <== winner" if ruling.get("winner") == o["frame"] else ""))
        L.append("      %-22s %8s %8s %8s  %s"
                 % ("canonical (x,y)", "walk#", "stored", "norm", "verdict"))
        for i in shown:
            L.append("      %-22s %8s %8s %8s  %s"
                     % (str(tuple(phys[i])), ranks.get(i),
                        source_indices[i], int(idx_k[i]),
                        "MATCH" if c["index_member"][i] else "MISS"))
    return L


def _diag_scoring_block(per_candidate, out, ruling, stats, excluded, metric,
                        scorable_values, reference_meta, reference_values,
                        source_values, weight_vec, scored_cells, truncated,
                        cell_cap, shift_window, ref_cell_count, source_map_count,
                        usable_count) -> list:
    """The scorer's half of the block. Reads what the run produced; decides nothing.

    Kept out of `score_candidates` so the scorer stays the scorer. Every argument
    is a structure the run already built — this function computes no score, no
    ranking and no reason code, and if it were deleted the numbers would not move.
    """
    L = ["", "-- scorer input ------------------------------------------------------------",
         "  source maps: in=%d usable=%d excluded=%d"
         % (source_map_count, usable_count, excluded.total()),
         "  cells reaching the scorer=%d (cap=%d, truncated=%s)  shift_window=+/-%d"
         % (scored_cells, cell_cap, truncated, shift_window),
         "  reference cells (deduped)=%d   reference values indexed=%d"
         % (ref_cell_count, stats.get("reference_values", 0)),
         "  sides considered=%s narrowed=%s   geometry assumed on %d map(s)"
         % (ruling.get("sides_considered"), ruling.get("sides_narrowed"),
            ruling.get("assumed_map_count", 0))]
    for row in excluded.as_list():
        L.append("  EXCLUDED %s x%d (e.g. %s%s)"
                 % (row["reason_code"], row["count"], _d(row["example_map_id"], 32),
                    "" if not row["example_detail"]
                    else ": " + _d(row["example_detail"], 120)))
    for k in ("basis_undeclared_map_ids", "assumed_map_ids", "assumable_map_ids"):
        if stats.get(k):
            L.append("  %s=%s" % (k, _d(stats[k], 160)))

    ref_vc = _d_vocab(reference_values)
    src_vc = _d_vocab(source_values)
    L += ["", "-- value vocabularies ------------------------------------------------------",
          "  reference : %s" % _d_vocab_text(ref_vc),
          "  source    : %s" % _d_vocab_text(src_vc)]
    L += _diag_compare_probe(ref_vc, src_vc)
    L.append("  value axis scorable=%s  (needs reference values AND source values)"
             % scorable_values)
    # 🔴 「쟀다」와 「순위를 냈다」를 한 줄에 같이 둔다. 종전에는 값 수치가 표에 실리는데
    #    그것이 순위를 만들었는지 아닌지를 이 블록이 말하지 않았고, 그래서 어휘가 하나도
    #    안 겹치는 실행이 「기하 실패」로 읽혔다.
    L.append("  value axis in this ruling: %s%s"
             % (ruling.get("value_axis"),
                "" if not ruling.get("value_axis_reason")
                else "  -> DEMOTED: %s (%s). Ranking fell back to %s."
                     % (ruling["value_axis_reason"],
                        _VALUE_AXIS_REASON_TEXT.get(ruling["value_axis_reason"], "?"),
                        ruling.get("metric"))))
    L.append("  shared vocabulary after the scorer's own normalisation: %s"
             % stats.get("value_vocab_shared"))
    if weight_vec is not None:
        L.append("  NOTE value_agreement below is a WEIGHTED sum, not a die count "
                 "(alignment.value_weights is declared).")

    L += ["", "-- candidates (%d) ---------------------------------------------------------"
          % len(out),
          "  %-14s %-16s %-30s %-9s %8s %10s %8s %10s"
          % ("frame", "state", "placed coords (post-transform)", "shift",
             "overlap", "value_hit", "discrim", "v_discrim")]
    import numpy as np
    for c, o in zip(per_candidate, out):
        raw_vh = "-"
        if c.get("value_member") is not None:
            raw_vh = str(int(np.count_nonzero(c["value_member"])))
        sh = ("-" if o.get("shift") is None
              else "(%s,%s)" % (o["shift"]["dx"], o["shift"]["dy"]))
        L.append("  %-14s %-16s %-30s %-9s %8s %10s %8s %10s"
                 % (o["frame"], o["state"],
                    (c.get("_placed_range") or "n=0"), sh,
                    o.get("agreement"), raw_vh, o.get("discriminating"),
                    o.get("value_discriminating")))
        if o.get("reason"):
            L.append("      reason: %s" % _d(o["reason"], 200))

    # Worked example: the top-ranked candidate and one that lost, because a
    # single trace shows what happened and two show what differed.
    a_key = ("index_agreement" if metric == METRIC_INDEX
             else "value_agreement" if metric in VALUE_METRICS else "agreement")
    scored = [(c, o) for c, o in zip(per_candidate, out) if o["state"] == STATE_SCORED]
    if scored:
        win = ruling.get("winner")
        top = next((p for p in scored if p[1]["frame"] == win), None)
        if top is None:
            top = max(scored, key=lambda p: (p[1].get(a_key) or 0, ))
        rest = [p for p in scored if p is not top]
        contrast = max(rest, key=lambda p: (p[1].get("agreement") or 0, )) if rest else None
        # `top[1]` / `contrast[1]` are the SHIPPED rows (`out`), paired with the scorer's own
        # record by `zip` above. Passing them is what lets the trace print the offset that
        # leaves the building rather than the one the scorer happened to hold.
        L += _diag_trace_lines(top[0], "winner" if win else "top by " + metric,
                               reference_meta, top[1])
        if contrast is not None:
            L += _diag_trace_lines(contrast[0], "a loser, for contrast", reference_meta,
                                   contrast[1])

    # ---- the ruling, and WHY it is what it is -------------------------------
    pos_max = max((o.get("agreement") or 0 for c, o in scored), default=0)
    val_max = max((int(np.count_nonzero(c["value_member"]))
                   for c, o in scored if c.get("value_member") is not None), default=None)
    L += ["", "-- DIAGNOSIS ---------------------------------------------------------------",
          "  metric=%s  reason_code=%s  winner=%s  index_axis=%s"
          % (metric, ruling.get("reason_code"), ruling.get("winner"),
             ruling.get("index_axis")),
          "  thresholds actually applied: min_margin_dies=%s min_discriminating_dies=%s "
          "(defaulted: %s)"
          % (ruling.get("min_margin_dies"), ruling.get("min_discriminating_dies"),
             ruling.get("thresholds_defaulted") or "none - declared")]
    if not scored:
        L.append("  CAUSE: NOT SCORED - no candidate placed a single cell. Nothing was "
                 "measured; see the exclusion rows above, not the reference.")
    elif pos_max == 0:
        L.append("  CAUSE: **POSITIONAL**. Best positional overlap across all %d "
                 "candidates is 0 - no source cell lands on any reference cell under "
                 "any frame. Values were never reached. Compare the placed-coordinate "
                 "ranges above against the reference range: this is geometry."
                 % len(scored))
    elif metric in VALUE_METRICS and val_max == 0:
        L.append("  CAUSE: **VOCABULARY**. Cells DO overlap positionally (best=%d of "
                 "%d placed) and value agreement is 0 on every candidate. The geometry "
                 "is landing; the two sides do not speak the same value vocabulary. "
                 "See the vocabulary block above - the answer is there, not in the "
                 "frames." % (pos_max, stats.get("placed_cells", 0)))
    elif val_max is None and metric in VALUE_METRICS:
        L.append("  CAUSE: value axis was selected but no candidate carries a value "
                 "verdict - see 'value axis scorable' above.")
    else:
        L.append("  CAUSE: ranked on %s; best positional overlap=%d, best value "
                 "agreement=%s. If there is no winner the reason_code above names "
                 "which of tie / discrimination / margin stopped it."
                 % (metric, pos_max, val_max))
    return L


METRIC_OCCUPANCY = "occupancy"
METRIC_VALUES = "values"
#: 값 축에 **무게가 걸린 채로** 매긴 순위. 새 필드가 아니라 축 이름의 세 번째 철자다 -
#: 순위를 만든 것이 무엇인지는 판정과 함께 다녀야 하고, 별도 불리언은 옮겨 적히다 흘린다.
METRIC_VALUES_WEIGHTED = "values_weighted"
#: 값 축의 두 철자. 무게는 **어느 필드로 순위를 내는가를 바꾸지 않는다** - 같은
#: `value_*` 필드를 읽고, 그 필드 안의 수가 개수냐 가중 합이냐만 다르다.
VALUE_METRICS = (METRIC_VALUES, METRIC_VALUES_WEIGHTED)
#: 순번 축. 점유·값과 **종류가 다르다** — 저 둘은 두 미지 사이의 관계를 재고, 이것은 정준
#: 방위라는 절대 기준점에 대고 잰다. 그래서 **성립하면** 더 강하지만, 성립 여부는 코드가
#: 알 수 없다 — 같은 순번 컬럼이 자기 보행에서 88/88, 다른 보행에서 4/88이다. 순위를
#: 가져가려면 `alignment.index` 문턱을 선언해야 한다(§INDEX_THRESHOLD_BLOCK).
METRIC_INDEX = "index"

# ---------------------------------------------------------------------------
# 판정 사유 - 「승자 없음」의 **왜**. 여러 자리에서 참조되는 것만 상수로 둔다
# ---------------------------------------------------------------------------
# 🔴 **「아무것도 채점되지 않았다」와 「채점했는데 못 가른다」는 다른 사실이고 다른 수리다.**
#    앞은 증거가 없었다는 뜻이라 조작자가 할 일은 규격을 선언하는 것이고, 뒤는 증거가 실재
#    하는데 후보를 못 가른다는 뜻이라 할 일은 더 나은 기준을 꽂는 것이다. 두 사실이 한 낱말로
#    합쳐지면 조작자는 절반의 경우에 반드시 틀린 곳을 고친다 - 실측(2026-08-05): 소스 맵이
#    칩 규격 미선언으로 전량 제외돼 채점기에 좌표가 **하나도 도달하지 않았는데** 화면은
#    「동점」이라고 말했고, 제품 소유자는 기준을 갈아 끼우러 갔다(고칠 것은 규격 선언이었다).
#
#    그 오진이 일어난 기전은 「없음을 0으로 접기」다. 놓인 셀이 없는 후보 여덟이 모두 일치 0을
#    받고, 그 여덟 개의 0이 **여덟 자 동점**으로 읽혔다. 0 후보가 0점을 받은 것은 8 후보가
#    같은 점수를 받은 것이 아니다(`Number(null) === 0` 계열의 결함, 한 층 위에서).
RULING_NO_CELLS_SCORED = "no_cells_scored"            # 채점기에 좌표가 0건 도달 (소스 전멸)
RULING_NO_CANDIDATE_SCORED = "no_candidate_scored"    # 좌표는 도달, 8후보 전부 변환 거절
RULING_NO_OVERLAP = "no_overlap"                      # 좌표는 놓였는데 기준 위 일치가 0건
RULING_NO_DISCRIMINATION = "no_discrimination"        # 대조는 됐는데 후보가 안 갈린다
RULING_TIE = "tie"                                    # 갈리는데 1위가 둘 이상

#: 판정 문턱. 선언이 정본이다. 선언이 없으면 **개발 기본값으로 순위를 내되, 그 사실을 판정이
#: 나른다**(제품 소유자 지시 2026-08-06: 「가드 제거하고 일단 핵심 기능 구현 확인 1순위,
#: 가드는 구현 확인 후 추가」). 종전에는 미선언이 곧 「순위 없음」이었고, 그 거절 하나로
#: 조작자는 하루 동안 후보 순위를 **한 번도** 본 적이 없다 — 개별로는 옳은 거절 여럿이
#: 모여서 기계가 자기 사용자를 위해 한 번도 돌지 않았다.
#:
#: 🔴 **그래도 0으로 접지는 않는다.** 미선언을 0으로 접으면 「구별 못 함」이 「자신 있는 1등」이
#:    되고(`Number(null) === 0`이 이 프로젝트를 세 번 물었다), 그 1등이 확정되면 저장된
#:    좌표가 상한다 — 그 뒤로는 아래 어디를 봐도 이상해 보이지 않는다. 기본값이 **1**인 것은
#:    타협이 아니라 이 성질 때문이다: 격차 비교는 이미 `max(1, ...)`으로 1을 바닥에 깔고
#:    판별수 > 0은 구조 검사가 이미 세우므로, `{1, 1}`은 조작자가 config에 그렇게 적었을 때와
#:    **한 후보도 다르게 판정하지 않는다.** 즉 기본값은 「무엇이 이기는가」를 바꾸지 않고
#:    「이겼다고 말해도 되는가」만 바꾼다. 20/20 같은 실측 문턱을 코드에 적는 것이야말로
#:    선언 사칭이다(I4) — 그 수는 데이터에서 유도되는 것이고 코드는 그 데이터를 모른다.
#:
#: 🔴 그래서 **사칭을 막는 것은 값이 아니라 표찰이다.** 기본값으로 매긴 순위는 선언으로 매긴
#:    순위와 **다른 사실**이고, 그 사실은 판정 dict 자신이 나른다
#:    (`ruling.thresholds_defaulted` — `geometry_assumed`·`metric`과 같은 계급). 옆 필드에
#:    두면 판정을 옮겨 적는 자리(확정 기록·목록)가 흘린다.
THRESHOLD_KEYS = ("min_margin_dies", "min_discriminating_dies")

#: 미선언 문턱의 **개발 기본값**. 스위치가 아니다 — 켜고 끄는 config 키를 만들면 그것이 두
#: 번째 표면이 되고, 한쪽만 배포되는 날이 반드시 온다(§VALUE_WEIGHTS_KEY와 같은 이유).
#: 한 동작이고, 언제나 같으며, 출처가 붙어서 나간다.
DEFAULT_THRESHOLDS = {"min_margin_dies": 1, "min_discriminating_dies": 1}

#: `ruling.provisional_text` — 기본값으로 매겼다는 **사람이 읽을 한 줄**. 코드가 아니라 문장을
#: 서버가 만드는 것은 `compose_refusal`과 같은 규율이고, 여기서는 이유가 하나 더 있다:
#: 이 사실은 **승자가 났을 때도 참**인데 그때 `compose_refusal`은 아무 문장도 내지 않는다
#: (`state == STATE_SCORED` → None). 즉 화면이 문장을 가장 필요로 하는 경우에 종전의 문장
#: 슬롯은 비어 있다. 그래서 판정 자신이 자기 문장을 들고 다닌다.
TEXT_PROVISIONAL_RANKING = "잠정 순위 - 판정 기준값 미선언 · 기본값 1"


def load_alignment_thresholds(cfg: dict) -> dict:
    """선언된 문턱만. 없는 키는 **0이 아니라 없는 키로** 나간다.

    읽히지 않는 선언(수가 아닌 값)도 선언이 아니다 — 조용히 0으로 접으면 오타 하나가
    「항상 순위를 낸다」로 바뀐다.
    """
    return _read_thresholds((cfg or {}).get("alignment") or {}, "alignment")


def _read_thresholds(raw: dict, where: str) -> dict:
    out = {}
    if not isinstance(raw, dict):
        return out
    for k in THRESHOLD_KEYS:
        v = raw.get(k)
        if v is None:
            continue
        try:
            out[k] = int(v)
        except (TypeError, ValueError):
            logger.warning("[MapAlignment] %s threshold '%s' is not a number, ignored: %r",
                           where, k, v)
    return out


#: 순번 축의 문턱은 **자기 블록에 산다**(`alignment.index`). 점유·값과 키를 공유하지 않는다.
#:
#: 🔴 이것이 「축 하나가 컬럼이 존재한다는 이유로 나머지를 밀어내지 않는다」의 구현이다.
#:    순번 축은 점유·값과 **다른 질문에 답한다** — 저 둘은 두 미지 사이의 관계를 재고 이쪽은
#:    정준 방위에 대고 잰다. 다른 질문에 답하는 축이 더 강한 것은 **그 질문이 이 데이터에
#:    성립할 때뿐**이고, 성립 여부는 코드가 알 수 없다: 같은 순번 컬럼이 자기가 선언된
#:    보행에서는 정답을 88/88로 짚고(합성 실측 2026-08-05) 다른 보행에서는 4/88로 떨어지며
#:    틀린 프레임을 1등으로 낸다. 그래서 순위를 가져가려면 **소리 내어 선언**해야 한다.
#:
#: 🔴 그리고 키를 공유하지 않는 것이 요점의 절반이다. 조작자가 점유 문턱을 다른 문제를
#:    쫓다가 낮추면(실제로 오늘 20 → 1로 낮췄다), 공유 키였다면 그 한 번의 조작이 순번 축의
#:    안전망까지 같이 걷어 간다. 안전망을 내리는 것과 새 축에 순위를 주는 것은 **다른 결정**
#:    이고, 다른 결정은 다른 선언이어야 한다.
INDEX_THRESHOLD_BLOCK = "index"

#: `ruling.index_axis` — 순번 축이 **이 판정에서 무엇을 했는가**. 판정 dict 자신이 나른다:
#: 후보 행에는 순번 수치가 실려 나가므로, 축이 순위를 안 냈다는 사실이 옆 필드에만 있으면
#: 화면은 수치를 보고 그것이 결정했다고 읽는다(`geometry_assumed`·`metric`과 같은 이유).
INDEX_AXIS_ABSENT = "absent"        # 순번을 실은 셀이 없다 — 잰 것이 없다
INDEX_AXIS_REPORTED = "reported"    # 쟀고 실어 보낸다. **순위는 안 냈다**(문턱 미선언)
INDEX_AXIS_RANKING = "ranking"      # 이 판정의 순위 축이다


def load_index_thresholds(cfg: dict) -> dict:
    """`alignment.index`의 문턱만. 없거나 불완전하면 순번 축은 **순위를 내지 않는다.**

    불완전을 0으로 접지 않는 것은 이 파일이 세 번 물린 자리와 같은 계열이다 — 여기서는
    한 걸음 더 간다: 미선언은 「문턱 0」이 아니라 **「이 축은 순위를 가져가지 않는다」**다.
    """
    raw = ((cfg or {}).get("alignment") or {}).get(INDEX_THRESHOLD_BLOCK)
    return _read_thresholds(raw if isinstance(raw, dict) else {}, "alignment.index")


def index_thresholds_complete(th: dict) -> bool:
    """둘 다 있어야 선언이다. 하나만 적은 것은 절반의 안전망이지 선언이 아니다."""
    return bool(th) and all(th.get(k) is not None for k in THRESHOLD_KEYS)


#: 값 가중치 선언 키. 문턱과 **같은 블록**에 산다 - 조작자가 정렬 판정을 조율하는 자리는
#: 하나여야 하고, 두 번째 config 표면을 만들면 한쪽만 배포되는 날이 반드시 온다.
VALUE_WEIGHTS_KEY = "value_weights"


def load_alignment_value_weights(cfg: dict) -> dict:
    """`{값: 무게}`. 선언된 값만 담는다. 선언이 없으면 **빈 dict**이고 그것이 「가중 없음」이다.

    🔴 **0은 선언이고, 없는 키는 선언이 아니다.** `{"1": 0}`은 「이 값은 세지 말라」는
       조작자의 주장이고, 키가 없는 값은 아무 말도 안 한 것이라 기본 1을 받는다. 둘을
       한 낱말로 접으면(`raw.get(k) or 1`) 「무시하라」가 조용히 「보통 무게」가 된다 —
       `Number(null) === 0` 계열이고 이 프로젝트를 이번 주에 두 번 물었다. 그래서 여기서
       0은 **키로 남고**, 조회하는 쪽은 `get(값, 1.0)`으로 없는 키만 기본값을 받는다.

    음수·무한·NaN은 선언으로 받지 않는다. 음수는 「맞은 것이 반증이다」라는 뜻이 되어
    합계를 음수로 만들 수 있고, 그러면 `best <= 0`이 「기준 위 일치 0건」이라고 답한다 -
    참이 아닌 문장이다. 읽히지 않는 선언은 선언이 아니다(§load_alignment_thresholds).
    """
    raw = ((cfg or {}).get("alignment") or {}).get(VALUE_WEIGHTS_KEY)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        logger.warning("[MapAlignment] '%s' is not an object, ignored: %r",
                       VALUE_WEIGHTS_KEY, raw)
        return {}
    out = {}
    for k, v in raw.items():
        if str(k).startswith("__"):        # config 파일의 주석 키 관례
            continue
        try:
            w = float(v)
        except (TypeError, ValueError):
            logger.warning("[MapAlignment] weight for %r is not a number, ignored: %r", k, v)
            continue
        # NaN은 모든 비교가 False라 이 한 줄이 음수·무한과 함께 걸러 낸다.
        if not (0.0 <= w < float("inf")):
            logger.warning("[MapAlignment] weight for %r is not usable, ignored: %r", k, v)
            continue
        out[str(k)] = w
    return out


def _fit_weights(vec, n):
    """무게 벡터를 셀 개수 `n`에 맞춘다. 모자란 자리는 **1**(선언 없음)이다.

    자르기만 하면 뒤 셀이 앞 셀의 무게를 받는다 - 값 절단이 좌표와 함께 잘려야 하는 것과
    같은 계열의 어긋남이고, 총계로는 절대 안 잡힌다(§[2] 절단).
    """
    import numpy as np
    if vec.size == n:
        return vec
    out = np.ones(n, dtype=float)
    m = min(n, vec.size)
    out[:m] = vec[:m]
    return out


def _rule_on(candidates: list, thresholds: dict = None,
             metric: str = METRIC_OCCUPANCY, scoring: dict = None) -> dict:
    """이길 후보가 있는가 — 없으면 **없다고 말한다**(스펙 §0.2 ⑦: 억지 1등 금지).

    이기려면 넷 다 필요하다: 단독 최고 · 판별수 > 0 · 판별수 ≥ 선언된 문턱 · 격차 ≥ 선언된
    문턱. 셋째·넷째가 안전망이고 **config이지 코드가 아니다.**

    🔴 `metric`이 순위 축을 정한다. 기준이 값을 실으면 값으로, 아니면 점유로 매긴다.
       점유는 기준 발자국이 원일 때 **아무 방위 정보도 싣지 않고**(스펙 §1), 그때 벌어지는
       격차는 표본 잡음이다. 그래서 문턱은 잡음 위의 1등을 막는 자리이고, 선언이 없으면
       막을 방법이 없으므로 아예 순위를 내지 않는다.

    `scoring`: 판정이 **자기 옆의 사실과 어긋나지 않게** 하는 재료 -
        `{placed_cells, scored_cells, source_map_count, excluded_map_count,
        excluded_reason_code}`. `scored_cells`는 **채점기에 도달한** 좌표 수이고
        `placed_cells`는 **변환을 통과해 놓인** 좌표 수다. 둘은 여덟 후보가 전부 변환을
        거절할 때 갈리고, 그 갈림이 「소스를 고쳐라」와 「기준을 고쳐라」를 가른다.
        제외 개수는 곁가지 필드가 아니라 판정의 일부다: 「1개 중 1개 제외」가 응답 안에 있는데
        판정이 「동점」이면 화면은 서로를 부정하는 두 문장을 같은 카드에 그리고, 그 카드는
        말을 아끼는 카드보다 나쁘다. 그래서 개수와 지배 사유가 **모든** 판정에 실린다.
    """
    sc = dict(scoring or {})
    # 🔴 문턱 해석을 **맨 위에서** 한다. 「기본값을 썼다」는 승자가 났을 때도 참인데, 승자가
    #    나면 `compose_refusal`은 아무 문장도 내지 않는다(§TEXT_PROVISIONAL_RANKING) - 이
    #    사실이 아래 갈래에만 붙어 있으면 화면이 그것을 가장 필요로 하는 경우에 사라진다.
    th = dict(thresholds or {})
    defaulted = [k for k in THRESHOLD_KEYS if th.get(k) is None]
    for k in defaulted:
        th[k] = DEFAULT_THRESHOLDS[k]
    ctx = {"metric": metric,
           "placed_cells": sc.get("placed_cells"),
           "source_map_count": sc.get("source_map_count"),
           "excluded_map_count": sc.get("excluded_map_count"),
           "excluded_reason_code": sc.get("excluded_reason_code"),
           # 🔴 **언제나 실린다**(빈 목록으로라도). 없는 키와 빈 목록은 받는 쪽에서 같아
           #    보이고, 그 같음이 「선언으로 매긴 순위」와 「기본값으로 매긴 순위」를 한
           #    낱말로 접는다 - `geometry_assumed`를 참일 때만 싣지 않는 것과 같은 이유.
           #    응답 최상위의 `thresholds`는 **config가 말한 것**이고(미선언 키는 없다),
           #    `ruling.min_*`는 **이 판정이 실제로 밟은 바**이며, 이 목록이 둘의 차다.
           "thresholds_defaulted": list(defaulted),
           "provisional_text": (TEXT_PROVISIONAL_RANKING if defaulted else None)}

    live = [c for c in candidates if c["state"] == STATE_SCORED]
    if not live:
        # 🔴 **채점 0건에는 두 원인이 있고 수리가 다르다.** 「좌표가 하나도 도달하지 않았다」는
        #    소스가 전멸했다는 뜻이라 고칠 것은 **선언**이고(제외 사유가 무엇을 선언할지 이미
        #    이름 붙여 두었다), 「도달했는데 여덟 후보가 전부 변환을 거절했다」는 격자 규격이
        #    기준과 맞지 않는다는 뜻이라 고칠 것은 규격 자체다. 한 낱말로 합치면 절반이
        #    틀린 곳으로 간다. `placed_cells`가 없으면(호출자가 안 넘겼으면) 단정하지 않고
        #    기존 낱말을 쓴다 - 모르는 것을 0으로 접지 않는다.
        #
        # 🔴 그 구별을 **놓인 좌표로 물으면 답이 하나뿐이다.** `not live`는 여덟 후보가 전부
        #    빈 배열이거나 None이라는 뜻이고, 그러면 `placed_cells`는 정의상 0이다 - 즉
        #    `no_candidate_scored`는 이 갈래에서 **도달할 수 없었다**(실측 2026-08-05: `not
        #    live`인 모든 조합에서 나온 (placed_cells, reason_code) 쌍은 `(0, no_cells_scored)`
        #    하나뿐). 그래서 기준 맵의 규격이 없어 여덟 후보가 전부 변환을 거절한 실행이
        #    「소스 좌표 미도달」로 나갔다 - 좌표는 도달했고(제외 0건·쓸 수 있는 맵 1장),
        #    거절한 것은 변환기이며, 고칠 것은 소스가 아니라 기준이었다. 참인 문장이 바로
        #    옆에 있었다(`compose_refusal`은 후보의 `reason`을 먼저 읽어 제대로 말하고
        #    있었다) - 어긋난 것은 사유 코드 하나이고, 화면의 표찰은 그 코드에서 나온다.
        #
        #    묻는 수를 **채점기에 도달한 좌표**로 바꾸면 두 사실이 갈린다. 안 넘어왔으면
        #    종전 수로 답한다 - 모르는 것을 0으로 접지 않는다.
        arrived = sc.get("scored_cells")
        if arrived is None:
            arrived = sc.get("placed_cells")
        return dict(ctx, winner=None, margin=None,
                    reason_code=(RULING_NO_CELLS_SCORED if arrived == 0
                                 else RULING_NO_CANDIDATE_SCORED))

    # 무게는 축을 **바꾸지 않는다** - 가중이든 아니든 값 축은 같은 세 필드를 읽는다.
    # 여기서 `== METRIC_VALUES`로 남겨 두면 가중 판정이 조용히 점유 필드로 순위를 낸다.
    if metric == METRIC_INDEX:
        a_key, d_key, m_key = ("index_agreement", "index_discriminating", "index_margin")
    elif metric in VALUE_METRICS:
        a_key, d_key, m_key = ("value_agreement", "value_discriminating", "value_margin")
    else:
        a_key, d_key, m_key = ("agreement", "discriminating", "margin")
    scoreable = [c for c in live if c.get(a_key) is not None]
    if not scoreable:
        return dict(ctx, winner=None, margin=None,
                    reason_code=RULING_NO_CANDIDATE_SCORED)

    best = max(c[a_key] for c in scoreable)
    tops = [c for c in scoreable if c[a_key] == best]
    # ═══ 순번 축의 **동점은 방향이 가른다** (제품 소유자 2026-08-06) ═══════════════════════
    # 「index 순서상 방향이 안 맞잖아」. 순서 일치는 순서만 보므로 셀이 적으면 여러 프레임이
    # 같은 순서를 만든다 — 실측: 가로 쌍에서 넷이 2/2 동점, 판정 `tie`, 승자 없음. 걸음의
    # 방향은 그 넷을 가른다(§direction_violations).
    #
    # 🔴 **대체가 아니라 포섭이다.** 순서를 재현하면서 걸음이 틀린 프레임은 순서도 걸음도
    #    맞는 프레임보다 나빠야 하므로, 순서가 1차이고 방향이 그 안에서 가른다. 순서가 이미
    #    갈렸으면 이 갈래는 발화하지 않는다.
    #
    # 🔴 **문턱은 여기 안 쓴다.** `min_margin_dies`의 단위는 다이 개수이고 위반은 걸음 수라,
    #    한 수를 다른 단위의 문턱에 대면 조작자가 안 건드린 선언의 뜻이 조용히 바뀐다
    #    (`map_overlay_config.json`이 이미 「위반 지표는 자기 선언을 따로 갖는다」고 적어 둠).
    #    그래서 이 갈래는 **자기 결정을 이름으로 신고**하고(`decided_by`), 다이 단위 격차
    #    비교를 건너뛴다 — 건너뛴다는 사실 자체가 판정에 실려 나간다.
    decided_by = None
    if metric == METRIC_INDEX and len(tops) > 1:
        vs = [c.get("index_violations") for c in tops]
        if all(v is not None for v in vs) and len(set(vs)) > 1:
            least = min(vs)
            tops = [c for c in tops if c.get("index_violations") == least]
            decided_by = "direction"
    top = tops[0]
    base = dict(ctx, margin=top.get(m_key),
                discriminating=top.get(d_key),
                min_margin_dies=th.get("min_margin_dies"),
                min_discriminating_dies=th.get("min_discriminating_dies"))

    # 🔴 **구조적 사실을 문턱보다 먼저 말한다.** 문턱과 무관하게 참인 사실을 「기준값 미선언」
    #    으로 덮으면 조작자가 config를 고치러 가서 아무것도 달라지지 않는다.
    #
    # 🔴 그리고 **구조적 사실끼리도 좁은 것이 먼저다.** 순서가 곧 조작자가 가는 곳이다:
    #    ① 아무 후보도 기준 위에 한 셀도 못 놓았다 → 잰 것이 없다. 여덟이 0으로 나란한 것은
    #       동점이 아니다(0 후보가 0점 받은 것과 같은 계열의 오독, 한 층 아래).
    #    ② 대조는 됐는데 셀들의 답이 후보마다 갈리지 않는다 → **기준이 못 가른 것**이다.
    #       이 모듈의 §REFERENCE_KIND 문서가 이미 그렇게 말한다: 점유만 있는 기준에서 여덟이
    #       같은 다이를 차지하면 그것은 진짜 동점이 아니다. 그런데 동점 검사가 먼저 있어서,
    #       가장 흔한 운영 형상(대칭·원 발자국)이 통째로 「동점」으로 나갔다 - 「증거는 실재
    #       하는데 못 갈랐다」고 말한 것이고, 실제로는 증거가 방위를 싣지 않았다.
    #    ③ 갈리기는 하는데 1위가 둘 이상 → **이것만이 동점이다.**
    if best <= 0:
        return dict(base, winner=None, margin=None, reason_code=RULING_NO_OVERLAP)
    if (top.get(d_key) or 0) <= 0:
        return dict(base, winner=None, reason_code=RULING_NO_DISCRIMINATION)
    if len(tops) > 1:
        return dict(base, winner=None, margin=0, reason_code=RULING_TIE,
                    tied=[c["frame"] for c in tops])
    # 🔴 여기 있던 `if missing: no_thresholds` 갈래가 사라졌다. 미선언은 이제 거절이 아니라
    #    **기본값 + 표찰**이고(§THRESHOLD_KEYS), 그래서 이 아래 두 비교는 언제나 수행된다.
    #    선언이 있으면 그 수로, 없으면 1로 - 어느 쪽이든 **같은 코드가 같은 순서로** 잰다.
    if (top.get(d_key) or 0) < th["min_discriminating_dies"]:
        return dict(base, winner=None, reason_code="too_few_discriminating")
    # 🔴 방향이 가른 판정은 **다이 격차 문턱을 밟지 않는다.** 밟으면 언제나 격차 0이라
    #    `margin_too_small`로 죽는다 - 순서가 동점이었다는 것이 이 갈래의 전제이기 때문이다.
    #    건너뛰는 대신 **무엇이 갈랐는지 이름으로 신고**한다: 조작자에게 「다이 격차로 뽑은
    #    1등」과 「걸음 방향으로 뽑은 1등」은 다른 주장이고, 판정 dict가 그것을 나른다.
    if decided_by is None:
        if top.get(m_key) is None or top[m_key] < max(1, th["min_margin_dies"]):
            return dict(base, winner=None, reason_code="margin_too_small")
    return dict(base, winner=top["frame"], reason_code=None, decided_by=decided_by,
                index_violations=top.get("index_violations"),
                index_steps=top.get("index_steps"))


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
    RULING_NO_CANDIDATE_SCORED: "8후보 전부 변환 거절 - 채점 0건",
    # 🔴 이 줄이 없어서 화면이 「동점」이라고 말했다. **없는 것과 나란한 것은 다른 사실이다.**
    RULING_NO_CELLS_SCORED: "채점 0건 - 소스 좌표 미도달",
    RULING_NO_OVERLAP: "기준 위 일치 0건 - 순위 없음",
    RULING_TIE: "동점 - 1위 복수",
    # 🔴 **사실만 대고 끝내면 조작자는 어디를 고칠지 모른다.** 이 사유는 소스 맵의 결함이
    #    아니라 **기준 한 장의 사실**이다 - 이 셀들에 대해 기준의 답이 자리에 따라 안 변하면
    #    무게로도 못 가른다(§[3c]: 여덟이 같은 셀 집합을 맞히면 어떤 배수도 여덟을 같이
    #    키운다). 그래서 수리는 문턱도 무게도 아니고 **다른 기준을 꽂는 것**이며, 문장이
    #    그 자리를 가리켜야 한다. 안 가리키면 조작자는 config를 세 번 고치고 돌아온다.
    RULING_NO_DISCRIMINATION: "기준 발자국 대칭 - 8프레임 구별 불가 · 다른 기준 맵 필요",
    # 🔴 `no_margin`·`no_thresholds`가 여기서 빠졌다. **어느 갈래도 그 코드를 내지 않는다** -
    #    `no_margin`은 처음부터 `_rule_on`에 발화 지점이 없었고(격차 0은 `RULING_TIE`나
    #    `margin_too_small`로 나간다), `no_thresholds`는 미선언이 기본값으로 바뀌면서
    #    도달 불가가 됐다(§THRESHOLD_KEYS). **발화할 수 없는 사유 코드는 어휘 안의 거짓말이고**
    #    (§ASSUMPTION_AVAILABLE에 이미 같은 문장이 있다), 표를 읽는 사람에게 있지도 않은
    #    갈래를 있다고 말한다. 클라의 `verdict.js`는 자기 층에서 `no_thresholds`를 여전히
    #    낼 수 있고 그쪽 어휘는 그쪽 것이다 - 서버가 못 내는 코드를 서버 표에 두지 않을 뿐.
    "too_few_discriminating": "판별 다이 부족 - 순위 없음",
    "margin_too_small": "1-2위 격차 부족 - 순위 없음",
}

#: 값 축으로 매길 때의 「일치 0건」. 같은 사실이 축마다 다른 낱말을 갖는 유일한 자리다 -
#: 점유 0과 값 일치 0은 조작자가 볼 곳이 다르고(좌표 컬럼 vs 값 컬럼), 사유 코드를 둘로
#: 나누면 같은 사실에 철자가 둘이 된다. 그래서 코드는 하나이고 문장만 축을 따라간다.
#:
#: 🔴 `no_discrimination`도 축을 따라간다. 점유 축에서는 「발자국이 대칭」이 참인 진단이지만
#:    값 축에서 그 문장을 내면 발자국을 재러 보내는데, 발자국은 순위에 안 쓰였다. 값 축의
#:    같은 사실은 **기준 값이 여덟 프레임에 같은 답을 준다**는 것이고, 가중 축에서는 거기에
#:    「무게로도 못 깬다」가 붙는다 - 무게를 더 올려 보는 것이 다음 수가 아니라는 뜻이다.
_RULING_TEXT_BY_METRIC = {
    (RULING_NO_OVERLAP, METRIC_VALUES): "값 일치 0건 - 순위 없음",
    (RULING_NO_OVERLAP, METRIC_VALUES_WEIGHTED): "가중 값 일치 0건 - 순위 없음",
    (RULING_NO_DISCRIMINATION, METRIC_VALUES):
        "기준 값이 8프레임에 동일 - 구별 불가 · 다른 기준 맵 필요",
    (RULING_NO_DISCRIMINATION, METRIC_VALUES_WEIGHTED):
        "기준 값이 8프레임에 동일 - 가중으로도 구별 불가 · 다른 기준 맵 필요",
    # 🔴 [2026-08-06] 이 문장이 **두 번 틀렸다.** 종전 「번호가 매겨진 기준 맵 필요」는 있지도
    #    않은 수리를 이름으로 댔고, 그다음 「기준이 번호를 매긴 그 유효 다이 맵과 다름」은
    #    기준을 갈아 끼우라고 말했다 — 그런데 **순번 축은 이제 기준을 아예 안 읽는다**
    #    (§순번 주석 2026-08-06: 훑기는 소스 자신의 셀 위에서 돈다). 기준을 바꿔도 이 수치는
    #    한 자도 안 움직인다. 0건이 실제로 뜻하는 것은 **여덟 프레임 어디에서도 소스의 훑기
    #    순서가 저장된 번호를 재현하지 못했다**는 것이고, 볼 곳은 순번 컬럼 자신이다 —
    #    번호가 이 다이 집합에 대해 매겨진 것이 맞는지, 빠진 행이 있는지.
    (RULING_NO_OVERLAP, METRIC_INDEX):
        "순번 일치 0건 - 8프레임 어디서도 훑기 순서가 저장 번호와 안 맞음 · 순번 컬럼 확인",
    # 순번이 모든 후보에 같은 답을 주는 경우. 🔴 「번호 실린 셀 부족」은 **잰 사실이 아니라
    # 추측**이었다 - 판별 0은 「프레임을 바꿔도 훑기 순서가 안 변한다」는 뜻이고, 셀이 적어서
    # 그럴 수도 있지만 다이 집합이 여덟 프레임에 대칭이어서 그럴 수도 있다. 잰 것만 말하고,
    # 셀 개수는 옆에 이미 있다(`stats.source_indices_usable`).
    (RULING_NO_DISCRIMINATION, METRIC_INDEX):
        "순번이 8프레임에 동일 - 구별 불가",
}


def _ruling_text(ruling: dict) -> str:
    """판정 사유 → 표찰. 축에 따라 갈리는 줄만 `_RULING_TEXT_BY_METRIC`이 덮는다."""
    code = (ruling or {}).get("reason_code")
    keyed = _RULING_TEXT_BY_METRIC.get((code, (ruling or {}).get("metric")))
    return keyed or _RULING_TEXT.get(code, "순위 근거 부족")

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
        # 🔴 여기가 실측으로 드러난 자리다. 기준도 있고 소스도 남아 있는데 **후보가 전부
        #    변환에 실패한** 경우가 있다 — 기준 맵과 소스 맵의 격자 규격이 다르면
        #    `make_frame_transform`이 여덟 후보 모두를 거절한다. 그때 "채점할 좌표가 없다"고
        #    답하면 조작자는 데이터를 의심하며 엉뚱한 곳을 고친다. 실제 사유는 변환기가 이미
        #    문장으로 만들어 놓았으므로 **그것을 그대로 올린다**(두 번째 사유 문장을 짓지 않는다).
        #
        #    🔴 이 검사가 제외 집계보다 **먼저**다. 순서가 반대이면, 맵 일부가 제외되고 남은
        #       맵이 전부 변환 거절된 경우에 「소스 전량 제외」라고 답한다 - 전량이 아니었고,
        #       거절한 것은 변환기였다. 참인 사실이 옆에 있는데 거짓 문장을 고르는 자리다.
        why = next((c.get("reason") for c in (candidates or []) if c.get("reason")), None)
        if why:
            return "8후보 전부 변환 거절 - %s" % why
        # 🔴 **아무것도 채점되지 않았다**는 사실은 제외 개수·사유와 함께 나가야 한다. 제외를
        #    곁가지 필드로만 실으면 화면은 「1개 중 1개 제외」를 콘솔에 두고 판정에는 다른 말을
        #    적는다. 그리고 사유 표찰이 곧 **무엇을 선언해야 하는가**다(`_EXCLUDE_TEXT`:
        #    「칩 규격 미선언」·「맵 규격 미등록」·「좌표 0건」) - 여기서 문장을 새로 짓지 않고
        #    그 표찰을 그대로 올린다.
        rows = excluded.as_list()
        if rows:
            parts = [(e["reason"] if len(rows) == 1 else "%s (%d)" % (e["reason"], e["count"]))
                     for e in rows]
            return ("채점 0건 - 소스 맵 %d개 중 %d개 제외 · %s"
                    % (source_map_count, excluded.total(), " · ".join(parts)))
        return "소스 좌표 0건"
    if state == STATE_NO_WINNER:
        return _ruling_text(ruling)
    return None


# ---------------------------------------------------------------------------
# [D3] 가정 - 제안 문장과, 「이 소스는 무엇 위에서 정렬됐나」의 유일한 철자
# ---------------------------------------------------------------------------
ASSUMPTION_APPLIED = "applied"          # 걸었다. 판정이 이 가정 위에 서 있다
#: 🔴 **뜻이 바뀌었다(2026-08-06). 「아직 안 눌렀다」가 아니라 「명시로 껐다」이다.**
#:    가정이 기본으로 걸리게 된 뒤(§score_candidates 기본값 뒤집힘), 「걸 수 있는데 아직
#:    요청되지 않았다」는 상태는 **자동으로는 발생할 수 없다** - 걸 수 있으면 이미 걸렸다.
#:    남은 발생 경로는 하나뿐이다: 호출자가 `assume_reference_geometry=False`를 **명시로**
#:    넘긴 진단 실행. 그래서 이 토큰은 지워지지 않고 **좁아졌다** - 여전히 참인 문장이 있고
#:    (「껐고, 켰다면 맵 N장이 채점됐다」) 그 문장은 진단하는 사람에게 필요한 정보다.
#:    발화할 수 없는 사유 코드는 어휘 안의 거짓말이지만, 이것은 발화한다.
ASSUMPTION_AVAILABLE = "available"      # 명시로 껐다 - 켰다면 걸렸을 맵이 이만큼 있다
ASSUMPTION_UNAVAILABLE = "unavailable"  # 걸 자리가 없다 (제외가 없거나 바닥이 미선언)


def compose_assumption_offer(state: str, count: int, basis: dict) -> str | None:
    """가정 한 줄. 걸 자리가 없으면 None.

    🔴 **이 문장은 이제 제안이 아니라 고지다.** 종전에는 제외된 맵 앞에서 「규격을
       선언하십시오」라는 막다른 길 대신 누를 것을 내놓는 자리였는데, 가정이 기본으로
       걸리면서 누를 것이 없어졌다 - 이미 걸려 있다. 남은 일은 **무엇을 참이라 치고
       채점했는지 말하는 것**이고, 그것이 가정을 자동으로 걸어도 되는 이유 그 자체다.
       문장은 서버가 만든다(`compose_refusal`과 같은 규율).

    `ASSUMPTION_AVAILABLE`의 문장만 여전히 가정법이다 - 그 상태는 호출자가 명시로 끈
    진단 실행이므로(§ASSUMPTION_AVAILABLE), 「켰다면」이 참인 유일한 자리다.
    """
    if state == ASSUMPTION_UNAVAILABLE or count <= 0:
        return None
    where = "%s / %s" % ((basis or {}).get("table") or "?",
                         (basis or {}).get("map_id") or "?")
    if state == ASSUMPTION_APPLIED:
        return ("맵 %d개를 기준(%s)의 웨이퍼 치수를 빌려 채점 - 동일 웨이퍼 가정이며 "
                "이 맵의 규격 선언이 아님" % (count, where))
    return ("가정 끔 - 맵 %d개는 기준(%s)과 같은 웨이퍼로 가정하면 채점 가능" % (count, where))


def geometry_basis_of(meta: dict | None, excluded_reason: str = None,
                      basis_meta: dict | None = None) -> str:
    """이 소스가 **무엇 위에서** 정렬됐는가 → `map_overlay.GEOMETRY_*` 토큰 하나.

    🔴 **철자는 여기 하나다.** 확정 기록(층 ⑧)이 이 답을 저장하는데, 그 경로가 자기 규칙을
       다시 쓰면 조작자가 본 사실과 기록된 사실이 갈릴 수 있다. 그리고 이 답은 **재채점이
       아니다** - 이미 DB에 있는 두 사실(그 맵의 메타, 제외됐는가)만 읽는다.

    규칙 한 줄: **제외되지 않았는데 자기 기하가 선언이 아니면, 그것은 빌린 기하 위에서
    정렬된 것이다.** 선언 없는 맵이 채점기를 통과하는 경로가 가정 하나뿐이기 때문에 이
    유도는 애매하지 않다(§score_candidates [1]).

    제외된 소스는 **어디에도 정렬되지 않았다.** 그때 답은 그 맵이 스스로 말하는 토큰이고,
    `assumed`가 아니다 - 일어나지 않은 일에 근거를 붙이지 않는다.

    🔴 **[D6] 그 한 줄 규칙이 축 하나만 보고 있었다.** 「선언 없는 맵이 채점기를 통과하는
       경로가 가정 하나뿐」은 빌림의 입구가 조건 하나이던 시절의 참이다. 이제 **phys를 선언한
       맵이 격자만 빌려** 통과할 수 있고, 그 맵에 대해 이 함수는 `declared`라고 답하게 된다 —
       빌린 격자 위에서 나온 정렬이 **선언 위에서 나온 것으로 기록**된다는 뜻이고, 하필 이
       함수의 답이 저장되는 곳이 「나중에 이 가정이 거짓이면 어느 결정이 그 위에 있었나」에
       답하려고 남기는 확정 기록(층 ⑧)이다.

    `basis_meta`: 이번 정렬의 **바닥** 메타. 주면 격자 축까지 유도한다. 안 주면 종전대로
        phys 축만 본다 — 빌림이 phys 축에서만 일어나던 호출자(구 기록)와 답이 같다.
        🔴 요청이 실어 오는 값이 아니라 여기서 **유도한다**(§_geometry_bases의 규율).
    """
    token = map_overlay.geometry_declaration(meta)
    if excluded_reason:
        return token
    # 🔴 [D7] `confirmed`는 **자기 기하**다. 「선언 없는 맵이 통과하는 길은 가정뿐」이라는 위
    #    한 줄은 확정이 생기기 전의 참이고, 지금은 확정된 기하 위에서도 통과한다 —
    #    `phys_needs_basis`가 그것을 빌리지 않으므로 이 실행은 아무것도 빌리지 않았다.
    #    여기서 `assumed`라고 답하면 판정(`ruling.geometry_assumed = false`)과 기여자 행이
    #    한 판 안에서 서로를 부정한다.
    if token not in (map_overlay.GEOMETRY_DECLARED, map_overlay.GEOMETRY_CONFIRMED):
        return map_overlay.GEOMETRY_ASSUMED
    if basis_meta is not None and grid_needs_basis(meta, basis_meta):
        return map_overlay.GEOMETRY_ASSUMED
    return token


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


def _same_walk(out: dict, proposal: dict) -> bool:
    """이 실행이 읽는 x/y가 **선언이 순번을 적어 둔 그 x/y**인가.

    한 낱말로 「보행(walk)」이다. 두 번째 철자를 만들지 않으려고 좌표 이름 비교 하나로
    답한다 - 보행을 별도 식별자로 선언하게 하면 같은 사실에 두 선언이 생기고, 둘이
    갈리는 날 순번은 자기가 말한 적 없는 좌표계를 채점한다.
    """
    return (out.get("x", {}).get("column") == proposal.get("x")
            and out.get("y", {}).get("column") == proposal.get("y"))


def resolve_source_columns(cfg: dict, table: str, model, x_col: str = None,
                           y_col: str = None, value_col: str = None,
                           index_col: str = None) -> dict:
    """이 실행이 실제로 읽을 좌표 삼중항과 **그 값이 어디서 왔는가**.

    `x_col`/`y_col`/`value_col`이 오면 그것이 답이고, 안 오면 선언 바인딩이 **제안**한다.
    컬럼은 테이블의 **실제 스키마**에 대해 검증한다 — `params`를 규칙 자신의 `decision_key`에
    대해 검증하는 것과 같은 규율이고, 없는 컬럼은 조용한 0건이 아니라 거절이다.

    `index_col`: **순번 컬럼**. x·y·value와 **같은 자격**으로 선언한다 - 현장마다 철자가
        다르고(이 박스의 데이터에는 아예 없다), 그 철자를 코드에 적으면 그 순간 이 기능은
        한 현장 전용이 된다. 🔴 **미선언이면 이 축은 돌지 않고 종전 채점이 그대로 선다** —
        없는 컬럼을 추측해서 채우면 조용히 0건 일치가 나오고, 그 0은 「번호가 안 맞았다」로
        읽혀 정반대를 말한다.
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

    # 순번 컬럼. 🔴 **추측하지 않는다** — 값 컬럼과 달리 이름 관례가 없고(현장마다 다르다),
    #    추측이 맞을 확률보다 엉뚱한 수치 컬럼을 순번으로 읽을 확률이 높다. 조작자가 대거나
    #    선언 바인딩이 `index` 키로 적거나 둘 중 하나이고, 없으면 이 축은 없다.
    k = index_col.strip() if isinstance(index_col, str) else index_col
    if isinstance(index_col, str) and not k:
        out["index"] = {"column": None, "origin": COLUMN_ABSENT,
                        "reason": "순번 컬럼 없이 실행"}
    elif k:
        out["index"] = {"column": _named(k, "index"), "origin": COLUMN_CHOSEN, "reason": None}
    elif proposal and proposal.get("index") and not guessed:
        col = proposal["index"]
        if getattr(model, col, None) is None:
            out["index"] = {"column": None, "origin": COLUMN_ABSENT,
                            "reason": "제안된 순번 컬럼 '%s'이 '%s'에 없습니다"
                                      % (col, table)}
        elif not _same_walk(out, proposal):
            # 🔴 **순번은 자기가 선언된 보행(walk)에만 붙는다.** 선언은 `index`를 x·y와
            #    **같은 칸에** 적는다 - 그것이 「이 번호는 이 x/y 보행의 순서다」라는 주장
            #    이고, 다른 보행은 그 주장의 범위 밖이다. `dt_log`는 한 테이블에 두 좌표계를
            #    (dt_x/dt_y와 core_x/core_y) 들고 있으므로 이 구별이 가상이 아니다.
            #    실측(2026-08-05, 합성 픽스처): 같은 dt_index를 DT 보행에 걸면 정답 프레임이
            #    88/88을 받고, 같은 번호를 core 보행에 걸면 정답이 **4/88**을 받으며 후보
            #    8개 중 5개 조합에서 2건은 **틀린 프레임**이 1등으로 나왔다. 번호가 틀린 것이
            #    아니라 **그 보행의 순서가 아닌** 것이고, 축이 답하는 질문 자체가 다르다.
            #    좌표를 덮어쓴 실행(`x_col`/`y_col` 인자)이 바로 그 자리다 - 여기서 막지
            #    않으면 선언 하나가 자기가 말한 적 없는 보행까지 채점한다.
            out["index"] = {
                "column": None, "origin": COLUMN_ABSENT,
                "reason": "순번 컬럼 '%s'은 %s/%s 보행에 선언됐습니다 - 이 실행은 %s/%s로 "
                          "읽으므로 순번 축은 돌지 않습니다"
                          % (col, proposal.get("x"), proposal.get("y"),
                             out["x"]["column"], out["y"]["column"])}
        else:
            out["index"] = {"column": col, "origin": COLUMN_PROPOSED, "reason": None}
    else:
        # 🔴 [2026-08-06] **여기 세 갈래가 한 줄로 나갔다.** 종전에는 셋 다 `reason: None`이라
        #    로그에 `origin=absent`와 빈 사유만 찍혔고, 그래서 「바인딩이 없다」·「index 키가
        #    없다」·「선언이 아니라 유도다」가 화면에서 **구별 불가능**했다. 제품 소유자는 그
        #    빈 줄을 몇 시간 들여다봤고 총괄이 제안한 원인 셋이 전부 그럴듯한 채로 남았다 —
        #    자기 케이스를 구별 못 하는 진단이 config가 아니라 **결함**이다.
        #    사유 문장은 조작자가 코드를 안 읽고 고칠 수 있어야 하므로 **무엇이 · 어디에**
        #    없는지를 이름으로 댄다.
        if not proposal:
            reason = ("순번 축 없음 - table_bindings에 '%s' 항목이 없습니다. "
                      "이 실행이 찾는 키는 rule.source_table 즉 '%s'이고, "
                      "맵 테이블 이름 아래 선언한 바인딩은 읽지 않습니다." % (table, table))
        elif proposal.get("source") != "declared":
            reason = ("순번 축 없음 - '%s' 바인딩이 선언이 아니라 유도값입니다(source=%s). "
                      "유도 바인딩에는 columns 블록이 없어 index를 적을 자리가 없습니다 - "
                      "table_bindings['%s'].columns를 직접 선언하십시오."
                      % (table, proposal.get("source"), table))
        else:
            reason = ("순번 축 없음 - table_bindings['%s'].columns에 index 키가 없습니다. "
                      "x/y/val은 선언돼 있으므로 같은 칸에 index를 더하면 됩니다."
                      % table)
        out["index"] = {"column": None, "origin": COLUMN_ABSENT, "reason": reason}
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
        cell = _readable_cell(x, y)
        if cell is None:
            continue
        out.append(cell)
        vals.append(None if values is None else values[i])
    return (out, vals) if values is not None else out


def _readable_cell(x, y):
    """`(x, y)`를 정수 좌표로, 못 읽으면 None. **좌표 채택 규칙의 단일 지점**이다.

    나란한 목록(값·순번)을 거르는 쪽이 이 규칙을 따로 쓰면 두 철자가 생기고, 갈리는 순간
    i번째 값이 j번째 셀에 붙는다 — 화면은 멀쩡하고 개수로도 안 잡히는 어긋남이다.
    """
    try:
        return (int(float(x)), int(float(y)))
    except (TypeError, ValueError):
        return None


def _indices_for(rows, at: int):
    """순번 목록을 **좌표와 같은 규칙으로** 거른다(§_readable_cell). 못 읽는 번호는 None.

    🔴 번호 자체가 수가 아니면 그 자리는 **None이지 0이 아니다**. 0으로 접으면 채점기가
       「0번을 기대한 자리에 놓였나」를 묻게 되고, 그것은 「번호가 없다」의 정반대다.
    """
    out = []
    for r in rows:
        if _readable_cell(r[0], r[1]) is None:
            continue
        try:
            out.append(int(float(r[at])))
        except (TypeError, ValueError):
            out.append(None)
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
        out = _load_reference(db, cfg, table, map_id, origin, cap, cache=cache)
        if len(cache) < _REF_CACHE_MAX:
            cache[ck] = out
        return out
    return _load_reference(db, cfg, table, map_id, origin, cap)


# 작업 단위 캐시 상한 — 넘치면 그냥 안 담는다(최악이 중복 해석 1회이고 오답은 아니다,
# `map_overlay._VALID_DIE_CACHE_MAX`와 같은 규율).
_REF_CACHE_MAX = 256


def _load_reference(db, cfg: dict, table: str, map_id: str, origin: str, cap: int,
                    cache: dict = None) -> dict:
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
        # 🔴 그 앞에 **서버가 메타 테이블 자체를 못 읽는 경우**가 있다. 그때는
        #    `_meta_row_exists`도 같은 이유로 False를 돌려주므로(모델 부재·질의 실패를
        #    False로 접는다) 두 갈래 판정이 통째로 「미등록」쪽으로 넘어간다. [D5] 이후로는
        #    이 오진이 특히 비싸다 — 바닥이 안 풀리면 소스 맵들이 `basis_undeclared`가 되어
        #    「기준 맵의 규격을 선언하십시오」라고 말하는데, 그 기준은 이미 선언돼 있다.
        access_code, access_detail = meta_absence_reason(db, cache)
        if access_code != EXCLUDE_META_MISSING:
            return _refuse(access_code, _META_ACCESS_TEXT[access_code]
                           + ("" if not access_detail else " (%s)" % access_detail))
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


def _diag_request_block(req_id, rule, key_values, map_table, src_table, map_key_cols,
                        args: dict, cfg: dict, columns: dict, thresholds, sides,
                        value_weights, index_thresholds, reference, source_maps) -> list:
    """The request's half of the block: **what arrived and what was read**.

    Inputs before interpretation, then the interpretation next to them on
    adjacent lines. The config blocks print as found in the file *and* as parsed,
    because an undeclared key folding silently into a default is the shape of
    half of this week's defects and only the two lines together show it.
    """
    L = [_DIAG_RULE,
         # 🔴 신원이 **맨 위**에 온다. 이 줄을 찾으려고 블록을 스크롤해야 하면, 「그 코드가
         #    들어 있나」를 묻는 사람이 여전히 증상부터 읽게 된다.
         build_identity(),
         "MAP ALIGNMENT SCORING   req=%s   %s"
         % (req_id, time.strftime("%Y-%m-%d %H:%M:%S")),
         "unit: rule=%s  key=%s  map_table=%s  source_table=%s  map_key_columns=%s"
         % (_d(rule.get("name")), _d(key_values, 200), _d(map_table), _d(src_table),
            _d(map_key_cols, 120)),
         _DIAG_RULE,
         "-- request, as it reached the scorer ---------------------------------------",
         "  (the HTTP query layer lives in server/main.py and is not visible from here;",
         "   these are the argument values build_alignment_view was called with)"]
    for k in ("reference_spec", "x_col", "y_col", "value_col", "include_cells",
              "cell_cap", "assume_reference_geometry"):
        L.append("  %-26s = %s" % (k, _d_arg(args.get(k))))

    raw_align = (cfg or {}).get("alignment")
    all_binds = (cfg or {}).get("table_bindings") or {}
    raw_bind = all_binds.get(src_table)
    L += ["", "-- config, as found in the file --------------------------------------------",
          "  alignment block            = %s" % _d_config(raw_align),
          # 🔴 The binding that is read is the **rule's source_table** one, and
          #    nothing else. A binding declared under the map table (`dt_map`) is
          #    never read by anything: an operator can populate the column,
          #    declare the binding and see no change at all. Printing the keys
          #    that exist next to the key that is used makes that mistake visible
          #    instead of invisible.
          "  table_bindings keys in config = %s" % _d(sorted(all_binds.keys()), 200),
          "  table_bindings key READ       = %s  (= rule.source_table; a binding "
          "under any other key is not read)" % _d(src_table),
          "  table_bindings[%s] = %s" % (_d(src_table, 20), _d_config(raw_bind)),
          "  alignment.index declared? %s"
          % ("no - the index axis was not asked for"
             if not isinstance((raw_align or {}).get(INDEX_THRESHOLD_BLOCK), dict)
             else "yes - so 'index_axis' at the DIAGNOSIS says whether it could stand"),
          "", "-- config, as parsed -------------------------------------------------------",
          "  thresholds      = %s   (missing keys are absent, NOT zero; what the ruling "
          "actually applied is printed at the DIAGNOSIS)" % _d(thresholds, 120),
          "  sides           = %s   (None = score both)" % _d(sides, 60),
          "  value_weights   = %s   ({} = no weighting)" % _d(value_weights, 200),
          "  index block     = %s   (incomplete = the index axis reports but does not "
          "rank)" % _d(index_thresholds, 120),
          "", "-- columns this run reads --------------------------------------------------",
          "  binding proposal (map_overlay.resolve_binding_info) = %s"
          % _d(columns.get("proposal"), 200)]
    for role in ("x", "y", "value", "index"):
        c = columns.get(role) or {}
        L.append("  %-6s column=%-18s origin=%-9s %s"
                 % (role, _d(c.get("column"), 18), c.get("origin"),
                    "" if not c.get("reason") else "reason: " + _d(c["reason"], 160)))

    L += ["", "-- reference (the common floor) --------------------------------------------",
          "  state=%s source=%s table=%s map_id=%s"
          % (reference.get("state"), _d(reference.get("source")),
             _d(reference.get("table")), _d(reference.get("map_id"))),
          "  reason_code=%s  reason=%s"
          % (reference.get("reason_code"), _d(reference.get("reason"), 300)),
          "  cells: %s   truncated=%s"
          % (_d_range(reference.get("cells")), reference.get("truncated")),
          "  carries values: kind=%s  (values list len=%d)"
          % (reference.get("kind"), len(reference.get("values") or ())),
          "  grid box=%s" % _d(map_overlay.grid_dims(reference.get("meta")))]
    L += ["  meta " + t for t in _d_meta(reference.get("meta"))]
    L.append("  values: %s" % _d_vocab_text(_d_vocab(reference.get("values"))))

    L += ["", "-- source maps -------------------------------------------------------------",
          "  maps=%d  cells(total)=%d"
          % (len(source_maps), sum(len(sm["cells"]) for sm in source_maps))]
    for sm in source_maps[:_DIAG_MAP_LINES]:
        L.append("  map=%s  %s" % (_d(sm["map_id"], 32), _d_range(sm["cells"])))
        L.append("       values: %s" % _d_vocab_text(_d_vocab(sm.get("values"))))
        if sm.get("indices"):
            L.append("       indices: %d carried, %d readable"
                     % (len(sm["indices"]),
                        sum(1 for k in sm["indices"] if k is not None)))
        L += ["       meta " + t for t in _d_meta(sm.get("meta"))]
        if sm.get("meta_refusal"):
            L.append("       meta_refusal=%s %s" % (sm["meta_refusal"],
                                                    _d(sm.get("meta_refusal_detail"), 160)))
    if len(source_maps) > _DIAG_MAP_LINES:
        L.append("  ... and %d more map(s) not printed (per-map lines are capped at %d)"
                 % (len(source_maps) - _DIAG_MAP_LINES, _DIAG_MAP_LINES))
    return L


def build_alignment_view(db, cfg: dict, rule: dict, key_values: dict, map_table: str,
                         reference_spec: str = None, include_cells: bool = True,
                         cell_cap: int = MAX_PAYLOAD_CELLS,
                         x_col: str = None, y_col: str = None,
                         value_col: str = None, index_col: str = None,
                         assume_reference_geometry: bool = True) -> dict:
    """한 결정 단위의 정렬 화면 payload **전부**를 한 번에 만든다. 읽기 전용이다.

    후보 8개의 채점이 같은 응답에 들어간다. 후보를 바꾸는 것은 네트워크가 아니라 리페인트여야
    하기 때문이고, 그 요구가 이 함수의 모양을 결정했다.

    `x_col`/`y_col`/`value_col`: **읽을 좌표 삼중항**. 이것이 원시 단위이고, 생략하면 선언
    바인딩이 제안한다(`resolve_source_columns`). 응답 `unit.columns`가 축마다 고른 것인지
    제안받은 것인지를 말한다.

    `assume_reference_geometry`: 규격 선언이 없는 소스 맵을 **기준의 웨이퍼 치수를 빌려**
    채점한다(스펙 §9ⓐ). **기본이 켜짐**이고 명시로 끌 수 있다 — 근거와 그 근거가 바뀐 이유는
    §score_candidates에 있다(한 곳에만 쓴다). 응답의 `assumption`이 걸었는지·무엇에서
    빌리는지를 말하고, 끄면 `state='available'`로 「껐고 이만큼이 걸릴 수 있었다」를 말한다.
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
    # 🔴 `index_col`을 **넘긴다.** 2026-08-06까지 이 호출은 인자 넷이었고, 그래서
    #    `resolve_source_columns`가 받아서 검증까지 하는 `index_col`이 운영 경로에서
    #    **죽어 있었다** - 순번 컬럼을 댈 방법이 선언 바인딩 하나뿐이었고, 조작자가
    #    「이 컬럼이 번호다」라고 말할 자리가 없었다. `_same_walk`의 주석은 그 덮어쓰기
    #    경로가 있다고 **가정하고** 쓰여 있다(「좌표를 덮어쓴 실행이 바로 그 자리다」) —
    #    가정만 있고 배선이 없었다.
    columns = resolve_source_columns(cfg, src_table, src_model, x_col, y_col, value_col,
                                     index_col)
    if not columns["x"]["column"] or not columns["y"]["column"]:
        raise ValueError("소스 테이블 '%s'의 좌표 컬럼을 정할 수 없습니다 - x/y를 "
                         "지정하십시오" % src_table)
    x_attr = getattr(src_model, columns["x"]["column"])
    y_attr = getattr(src_model, columns["y"]["column"])

    v_attr = (getattr(src_model, columns["value"]["column"])
              if columns["value"]["column"] else None)
    # 순번 컬럼. `resolve_source_columns`가 **보행 범위까지 판정한 뒤** 넘겨준 것이라
    # 여기서 다시 묻지 않는다 - 두 번째 판정을 두면 그 둘이 갈리는 날이 온다(§_same_walk).
    k_attr = (getattr(src_model, columns["index"]["column"])
              if columns.get("index", {}).get("column") else None)

    source_maps = []
    src_truncated = False
    for mid in ids:
        mfilters = list(filters)
        for i, c in enumerate(map_key_cols):
            part = mid if len(map_key_cols) == 1 else mid.split("_")[i]
            mfilters.append(getattr(src_model, c) == part)
        # 열 순서를 **여기 한 곳에서** 정하고 아래가 그 순서로 읽는다. 조건부 열이 둘이라
        # 인덱스를 상수로 적으면 값 컬럼이 없는 실행에서 순번이 값 자리를 읽는다.
        q_cols = [x_attr, y_attr]
        v_at = k_at = None
        if v_attr is not None:
            v_at = len(q_cols)
            q_cols.append(v_attr)
        if k_attr is not None:
            k_at = len(q_cols)
            q_cols.append(k_attr)
        rows = db.query(*q_cols).filter(*mfilters).limit(cell_cap + 1).all()
        if len(rows) > cell_cap:
            src_truncated = True
            rows = rows[:cell_cap]
        cells, cvals = _to_cells([(r[0], r[1]) for r in rows],
                                 [(r[v_at] if v_at is not None else None) for r in rows])
        sm = {"map_id": mid, "table": map_table,
              "meta": map_overlay.load_map_meta(db, map_table, mid),
              "cells": cells, "values": cvals}
        if k_at is not None:
            # 🔴 순번은 좌표와 **같은 순서·같은 길이**여야 한다. `_to_cells`가 좌표를 거르면
            #    (수가 아닌 x·y) 남은 순번이 옆 셀에 붙고, 그 오답은 개수로 안 잡힌다.
            #    그래서 좌표와 **함께** 거른다.
            sm["indices"] = _indices_for(rows, k_at)
        source_maps.append(sm)

    # 🔴 메타가 None인 맵이 하나라도 있으면 **왜 None인지**를 요청 단위로 한 번 가른다.
    #    [D5] 이후 이것은 표찰이 아니라 관문이다 - 표지가 없어야만 아래 채점기가 규격을
    #    빌린다(§stamp_meta_refusal).
    req_cache = {}
    meta_access = stamp_meta_refusal(db, source_maps, req_cache)

    reference = _resolve_reference(db, cfg, reference_spec, source_maps, cell_cap,
                                   cache=req_cache)
    thresholds = load_alignment_thresholds(cfg)
    # 무게도 **문턱과 같은 선언**이다 - 같은 블록에서 같이 읽고, 없으면 없는 채로 내려간다.
    value_weights = load_alignment_value_weights(cfg)
    # 면도 같은 블록의 같은 규율이다. `None`이면 **둘 다**이고, 좁혀도 후보 여덟은
    # 여덟으로 나간다(§STATE_NOT_CONSIDERED).
    sides = load_alignment_sides(cfg)
    # 순번 축 문턱은 **자기 블록**에서 읽는다. 점유·값 문턱과 키를 공유하면 저쪽을 낮추는
    # 조작이 이 축의 안전망까지 걷어 간다(§INDEX_THRESHOLD_BLOCK).
    index_thresholds = load_index_thresholds(cfg)

    # Scoring diagnostics. Built as one list and emitted as one record at the end
    # so a request is a block: operators click several units in a row and the runs
    # must not braid. Costs nothing anybody notices - this is an operator screen,
    # one request per click, not a hot path.
    _diag_logger()                      # so the header can name the file it writes to
    req_id = uuid.uuid4().hex[:8]
    diag = _diag_request_block(
        req_id, rule, key_values, map_table, src_table, map_key_cols,
        {"reference_spec": reference_spec, "x_col": x_col, "y_col": y_col,
         "value_col": value_col, "include_cells": include_cells, "cell_cap": cell_cap,
         "assume_reference_geometry": assume_reference_geometry},
        cfg, columns, thresholds, sides, value_weights, index_thresholds,
        reference, source_maps)
    if meta_access:
        diag.append("  META ACCESS INCIDENT: %s" % _d(meta_access, 300))

    candidates, excluded, ruling, stats = [], _Excluded(), {"winner": None}, {}
    if reference["state"] == REFERENCE_RESOLVED:
        candidates, excluded, ruling, stats = score_candidates(
            source_maps, reference["cells"], reference["meta"],
            reference_values=reference.get("values"), thresholds=thresholds,
            assume_reference_geometry=assume_reference_geometry,
            reference_ref={"table": reference.get("table"),
                           "map_id": reference.get("map_id")},
            value_weights=value_weights, sides=sides,
            index_thresholds=index_thresholds, diag=diag)
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
        basis_undeclared = []
        for sm in source_maps:
            if not sm.get("cells"):
                excluded.add(EXCLUDE_NO_CELLS, sm["map_id"])
            elif sm.get("meta_refusal"):
                # 서버가 못 읽은 것이지 이 맵이 미등록인 것이 아니다 — 바닥 이야기로 접으면
                # 「기준을 선언하라」가 되고, 그것도 참이 아니다.
                excluded.add(sm["meta_refusal"], sm["map_id"], sm.get("meta_refusal_detail"))
            elif not sm.get("meta"):
                # 🔴 [D4] **`meta_missing`이 아니다.** 여기서 그 낱말을 쓰면 소스 맵 N장을
                #    고치러 보내는데, 규격 행이 없는 것은 정상이고 선언이 필요한 것은 조작자가
                #    고를 바닥 한 장이다. 그 사실은 요청 단위로 한 번만 말한다.
                basis_undeclared.append(sm["map_id"])
            else:
                why = map_overlay.geometry_refusal(sm["meta"])
                if why is not None:
                    excluded.add(EXCLUDE_GEOMETRY_REFUSED, sm["map_id"], why)
        stats["basis_undeclared_map_ids"] = basis_undeclared
        # 🔴 이 루프가 채점기와 **같은 세 관문**을 돌렸으므로 남은 수는 잰 값이다. 예전에는
        #    이 갈래에서 `stats`가 비어 `usable_map_count`가 `stats.get(..., 0)`의 기본값 0으로
        #    나갔다 - 아무것도 안 재고 「쓸 수 있는 맵 0장」이라고 말한 것이고, 기준만 꽂으면
        #    채점될 단위를 조작자가 가망 없는 단위로 읽었다.
        # 바닥 미선언으로 막힌 맵은 **제외 집계에 없으므로** 여기서 따로 뺀다 - 안 빼면
        # 「쓸 수 있다」에 못 채점한 맵이 섞인다.
        stats["source_maps_usable"] = (len(source_maps) - excluded.total()
                                       - len(basis_undeclared))
        diag += ["", "-- DIAGNOSIS --------------------------------------------------------"
                     "-------",
                 "  CAUSE: NOT SCORABLE - the scorer never ran. The reference did not "
                 "resolve (state=%s, reason_code=%s), so there was no common floor to "
                 "lay the source cells on. Fix the reference; the frames were never "
                 "compared." % (reference["state"], reference.get("reason_code")),
                 "  reference reason: %s" % _d(reference.get("reason"), 400),
                 "  would-be-usable source maps if a reference were declared: %d"
                 % stats["source_maps_usable"]]
        for row in excluded.as_list():
            diag.append("  EXCLUDED %s x%d (e.g. %s)"
                        % (row["reason_code"], row["count"],
                           _d(row["example_map_id"], 32)))

    # ═══ 셀 배열은 **평행 배열 셋**이다 — 좌표 / 순번 / 소유 맵 ══════════════════════════
    # 제품 소유자 요청 2026-08-06: 정렬 화면의 셀을 **순번으로 칠한다**(서펜타인 위의 무지개).
    # 틀린 프레임은 보행 순서가 통째로 갈리므로 한눈에 보인다 — 이 축이 만들 가치가 있었던
    # 바로 그 성질을 그림으로 옮기는 것이다.
    #
    # 🔴 **`cells`의 계약은 건드리지 않는다.** 셀 하나를 `[x, y, k]`로 늘리면 이미 그 배열을
    #    읽는 자리가 전부 깨진다. 같은 순서·같은 길이의 **별도 배열**로 실어 보낸다.
    #
    # 🔴 **정규화된 순위를 싣는다, 원본 컬럼 값이 아니라.** base가 실제로 갈린다(`0..255` 대
    #    `1..266`). 클라가 다시 정규화하면 **같은 수를 두 번 계산**하는 것이고, 이 프로젝트는
    #    그 형태로 이미 값을 치렀다. 철자는 `_normalised_indices` 하나이고 채점기가 쓰는 그
    #    함수를 그대로 부른다 — 여기서 base를 다시 구하지 않는다.
    #
    # 🔴 **번호 없는 행은 `null`이지 `0`이 아니다.** 0은 「1번 다이」로 칠해진다. 번호가 없는
    #    다이도 보행에는 들어가지만 색은 없다(§_index_member의 같은 구분).
    #
    # 🔴 **`cell_map`은 선택 사항이 아니다.** `pooled`는 맵들을 이어 붙이는데 순번은 맵마다
    #    1부터 다시 시작한다(제품 소유자: 「소스별로 index 매기는거잖아」). 소유 정보 없이 한
    #    배열에 담으면 **독립된 두 보행 위에 램프 하나**를 그리게 되고, 그 그림은 자신 있게
    #    틀린다 — 이 라운드가 채점에서 없앤 결함과 정확히 같은 것을 색으로 재현하는 셈이다.
    pooled = []
    pooled_raw_k = []
    pooled_map = []
    if include_cells:
        for mi, sm in enumerate(source_maps):
            if len(pooled) >= cell_cap:
                src_truncated = True
                break
            ks = sm.get("indices") or []
            for j, xy in enumerate(sm["cells"]):
                if len(pooled) >= cell_cap:
                    src_truncated = True
                    break
                pooled.append([xy[0], xy[1]])
                pooled_raw_k.append(ks[j] if j < len(ks) else None)
                pooled_map.append(mi)

    # base 정규화는 **맵마다** 돈다(`pooled_map`이 소유를 나른다). 채점기와 같은 함수다.
    _pk, _phas, _pbases = _normalised_indices(pooled_raw_k, pooled_map)
    # 🔴 **절단된 풀은 완전한 보행이 아니다.** 그때 이 필드는 **통째로 null**이다 — 원소가
    #    null인 것(「이 다이는 번호가 없다」)과 필드가 null인 것(「완전한 보행을 못 준다」)은
    #    받는 쪽에서 다른 사실이고, 접으면 잘린 램프가 완전한 램프처럼 그려진다.
    if src_truncated or _phas is None:
        pooled_index = None if src_truncated else [None] * len(pooled)
    else:
        pooled_index = [(int(_pk[i]) if _phas[i] else None) for i in range(len(pooled))]

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

    # [D3] 가정의 상태 - **걸었나 · 걸 수 있나 · 무엇에서 빌리나.** 세 번째가 없으면 나중에
    # 「이 판정은 무엇을 참이라 치고 나왔나」에 답할 수 없다.
    assumed_ids = list(stats.get("assumed_map_ids") or ())
    assumable_ids = list(stats.get("assumable_map_ids") or ())
    _aligned = set(stats.get("usable_map_ids") or ())
    a_basis = ({"table": reference.get("table"), "map_id": reference.get("map_id")}
               if reference["state"] == REFERENCE_RESOLVED else None)
    if assumed_ids:
        a_state = ASSUMPTION_APPLIED
    elif assumable_ids:
        a_state = ASSUMPTION_AVAILABLE
    else:
        a_state = ASSUMPTION_UNAVAILABLE
    a_ids = assumed_ids or assumable_ids
    # [D4] 바닥이 선언이 아니라 **제안조차 못 한** 맵들 — 요청 단위로 한 번. 여기가 「고쳐야
    # 할 것은 소스 맵 N장이 아니라 바닥 한 장」을 말하는 유일한 자리다.
    if reference["state"] == REFERENCE_REFUSED:
        basis_why = reference.get("reason")
    elif reference["state"] == REFERENCE_ABSENT:
        basis_why = TEXT_REFERENCE_ABSENT
    else:
        basis_why = map_overlay.geometry_refusal(reference.get("meta"))
    # 🔴 `a_basis`가 아니라 **기준이 무엇이었든 그 이름**을 싣는다. 거절된 기준도 이름은
    #    있고, 조작자에게 필요한 것이 정확히 그 이름이다("어느 맵을 선언해야 하나").
    basis_refusal = compose_basis_refusal(
        stats.get("basis_undeclared_map_ids"),
        ({"table": reference.get("table"), "map_id": reference.get("map_id")}
         if reference.get("table") else None),
        basis_why)
    assumption = {
        "state": a_state,
        "requested": bool(assume_reference_geometry),
        "basis": a_basis if a_state != ASSUMPTION_UNAVAILABLE else None,
        "map_count": len(a_ids),
        "map_ids": a_ids,
        "text": compose_assumption_offer(a_state, len(a_ids), a_basis),
    }

    payload = {
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
            # 🔴 코드도 같이 낸다. `_ref_state`는 "코드와 문장 둘 다" 내보내기로 돼 있는데
            #    이 자리가 문장만 실어, 화면이 분기하려면 문장에서 코드를 유도해야 했다 —
            #    그것이 두 번째 판정 구현이다. 목록(`unscorable_reasons`)은 이미 코드를 낸다.
            "reason_code": reference.get("reason_code"),
            "truncated": reference.get("truncated", False),
            "cells": ([[x, y] for (x, y) in reference.get("cells") or ()]
                      if include_cells else []),
        },
        "sources": {
            "map_count": len(source_maps),
            "usable_map_count": stats.get("source_maps_usable", 0),
            "cell_count": sum(len(sm["cells"]) for sm in source_maps),
            "cells": pooled, "truncated": src_truncated, "cell_cap": cell_cap,
            # 순번 페인팅용 평행 배열(§pooled 위 블록). `cells`와 **같은 순서·같은 길이**다.
            #   · `cell_index` — 맵 안에서 1부터인 **정규화된 순위**. 원소 null = 그 행에
            #     번호가 없었다. **필드 자체가 null** = 풀이 잘려 완전한 보행이 아니다.
            #   · `cell_map` — `sources.maps[]`의 첨자. 순번이 맵마다 다시 시작하므로 이것
            #     없이는 이어 붙인 배열에 램프를 그릴 수 없다.
            "cell_index": pooled_index,
            "cell_map": pooled_map,
            # `geometry`는 **이 맵이 스스로 말하는 기하 출처**이고 `geometry_basis`는
            # **이번 실행이 실제로 무엇 위에 올렸나**다. 둘을 한 필드로 접으면 가정이
            # 선언처럼 보이거나(I4) 가정이 사라진다. 뒤엣것의 철자는 `geometry_basis_of`
            # 하나이고 확정 기록도 같은 함수를 부른다.
            "maps": [dict({"map_id": sm["map_id"], "cell_count": len(sm["cells"])},
                          declared_frame=_df(sm)["frame"],
                          declared_frame_source=_df(sm)["source"],
                          geometry=map_overlay.geometry_declaration(sm.get("meta")),
                          # [D6] 바닥 메타를 함께 넘긴다 — 격자만 빌린 맵은 phys가 `declared`
                          # 여서 이 인자 없이는 「선언 위에 섰다」고 답한다.
                          geometry_basis=geometry_basis_of(
                              sm.get("meta"),
                              None if sm["map_id"] in _aligned else "not_aligned",
                              reference.get("meta")))
                     for sm in source_maps],
        },
        "candidates": candidates,
        # [D3] 가정은 **판정 옆이 아니라 판정과 함께** 산다. `ruling.geometry_assumed`가
        # 판정 자신의 사실이고, 이 블록은 그 가정의 내용(무엇에서, 몇 장, 제안인가)이다.
        "assumption": assumption,
        # [D4] 가정을 **걸 수조차 없었던** 이유 — 바닥이 선언이 아니다. `None`이면 해당 없음.
        # 요청 단위의 사실이라 여기 하나뿐이고, 제외 집계는 이 사유로 부풀지 않는다.
        "basis_refusal": basis_refusal,
        # 🔴 **요청 전체의 사고**를 요청 단위에 한 번 말한다. `None`이면 정상 - 화면은
        #    아무것도 그리지 않는다. 값이 있으면 아래 제외 집계는 데이터의 이야기가 아니고,
        #    이번 요청에서는 **아무 맵도 규격을 빌리지 않았다**(§stamp_meta_refusal).
        "meta_access": meta_access,
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
    diag += ["",
             "-- what the screen will show -----------------------------------------------",
             "  state=%s  refusal=%s" % (payload["state"], _d(payload["refusal"], 300)),
             "  reference.kind=%s (what this run can compare)   reference.map_kind=%s "
             "(what the reference map itself carries)"
             % (payload["reference"]["kind"], payload["reference"]["map_kind"]),
             _DIAG_RULE,
             "END req=%s   build=%.1fms   diagnostics file: %s"
             % (req_id, payload["stats"]["build_ms"],
                _DIAG_FILE_PATH or ("<console only: %s>" % _DIAG_FILE_ERROR)),
             _DIAG_RULE, ""]
    _emit_diag(diag)
    return payload


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
        try:
            rows = (db.query(mid).filter(tt == ftable).order_by(mid)
                      .limit(remaining + 1).all())
        except Exception as e:
            # 🔴 메타 테이블을 못 읽으면 **카탈로그만 비는 것이 아니라 목록 전체가 500이었다**
            #    (이 질의가 `build_alignment_worklist`의 꼬리에서 돈다). 그러면 「무엇이 왜
            #    안 되는가」가 통째로 사라지고, 화면은 정렬 기능 자체가 죽은 것으로 읽는다.
            #    모델 부재와 **같은 상태**로 접는다 — 둘 다 「바닥 목록을 낼 수 없다」이고,
            #    원인의 이름은 `meta_access`가 요청 단위로 따로 말한다.
            logger.error("[MapAlignment] reference catalog query failed (%s): %s", ftable, e)
            return dict(base, state=REFERENCE_CATALOG_UNAVAILABLE,
                        reason="맵 규격 표(%s)를 조회하지 못했습니다"
                               % map_overlay.META_TABLE)
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
        try:
            rows = db.query(mid, gm).filter(tt == map_table, mid.in_(part)).all()
        except Exception as e:
            # 🔴 조용히 {}로 접지 않는다 — 로그는 error로 남기고, 호출자가
            #    `meta_absence_reason`으로 **이름을 붙여** 응답에 싣는다. 예외를 그대로
            #    올리면 목록이 500이 되어 「무엇이 왜 안 되는가」가 통째로 사라진다.
            logger.error("[MapAlignment] meta batch query failed (%s): %s", map_table, e)
            return out
        for row in rows:
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
    # 🔴 상세 화면과 **같은 갈래**를 목록에서도 낸다. 메타를 못 읽은 맵이 하나라도 있으면
    #    그 이유를 요청 단위로 한 번 묻고(캐시 공유) 지배적 사유의 낱말로 쓴다 — 목록이
    #    「미등록」이라 하고 상세가 「테이블 미선언」이라 하면 같은 원인이 두 이름을 갖는다.
    meta_missing_code, meta_missing_detail = EXCLUDE_META_MISSING, None
    if any(metas.get(m) is None for m in all_ids):
        meta_missing_code, meta_missing_detail = meta_absence_reason(db, ref_cache)
    meta_access = meta_access_block(meta_missing_code, meta_missing_detail)
    meta_readable = meta_missing_code == EXCLUDE_META_MISSING
    reasons = {}
    by_state = {STATE_UNIT_PENDING: 0, STATE_UNIT_CONFIRMED: 0, STATE_UNIT_UNSCORABLE: 0}
    for u in units:
        ids = per_unit_maps.get(u["_tuple"], set())
        u["map_count"] = len(ids)
        # 🔴 [D7] 묻는 것은 「선언인가」가 아니라 **「빌리지 않고 채점되는가」**이고, 그 술어의
        #    철자는 `phys_needs_basis` 하나다. 확정된 기하는 빌릴 필요가 없으므로 여기 든다 —
        #    안 그러면 목록이 「쓸 수 없는 맵」이라 부르는 단위를 상세가 확정된 기하 위에서
        #    채점한다(목록이 상세와 갈리는 것은 어느 방향이든 갈리는 것이다).
        usable = [m for m in ids
                  if metas.get(m) is not None and not phys_needs_basis(metas[m])]
        u["usable_map_count"] = len(usable)
        # [D3] **가정으로 열릴 수 있는 맵의 수** - 기하 선언은 없지만 격자 치수는 있어서
        # 바닥을 꽂으면 「같은 웨이퍼」 가정 아래 채점되는 맵들이다(스펙 §9ⓐ).
        # 🔴 `state`·`reason_code`는 **건드리지 않는다.** 목록은 바닥을 풀지 않은 채로
        #    이 수를 세므로 「가정이 실제로 걸린다」고 말할 수 없다 - 그것은 상세가 바닥을
        #    풀고 나서야 아는 사실이다. 여기서 상태를 바꾸면 목록이 상세보다 많이 주장한다.
        # 🔴 [D5] **규격 행이 없는 맵도 센다.** [D4]까지는 행 없는 맵이 채점 대상이 아니라
        #    제외하는 것이 맞았지만, 지금은 그 맵이 바로 이 기능이 섬기는 모집단이다 - 빼면
        #    목록이 「가망 없음」이라 말하는 단위가 상세에서는 열린다(목록이 상세보다 적게
        #    주장하는 것도 갈리는 것이다).
        #    ⚠️ 격자 치수 조건은 **행이 있는 맵에만** 건다. 행이 없으면 격자를 바닥에서
        #       빌리므로 셀이 답을 갖고 있고, 목록은 셀을 읽지 않는다.
        #    ⚠️ 담김(§cells_outside_grid)은 여기서 확인할 수 없다 - 셀 bbox가 필요하다.
        #       그래서 이 수는 여전히 **상한**이고, 상세가 정본이다(기존 규율 그대로).
        #    🔴 그리고 **서버가 메타를 못 읽었으면 하나도 세지 않는다.** 그때 모든 맵이
        #       `metas.get(m) is None`이라 이 식은 「전부 가정 가능」이라고 답하는데, 그것은
        #       읽지 못한 것을 부재로 읽은 결과다 — 잰 적 없는 수를 초대장으로 내보낸다.
        #    🔴 [D7] 여기도 같은 술어다. 확정된 기하를 「가정으로 열 수 있는 맵」으로 세면
        #       이미 답이 있는 단위에 초대장을 보내는 것이고, 조작자는 누르고 나서 아무것도
        #       바뀌지 않는 것을 본다.
        u["assumable_map_count"] = 0 if not meta_readable else sum(
            1 for m in ids
            if metas.get(m) is None
            or (phys_needs_basis(metas[m])
                and map_overlay.grid_dims(metas[m]) is not None))
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
            reason = (meta_missing_code if n_missing * 2 >= len(ids)
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
        # 상세와 **같은 자리·같은 모양**. `None`이면 정상 (§meta_access_block).
        "meta_access": meta_access,
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
        # 🔴 `assumable_map_count`는 [D3]에 계산돼 놓고 **응답에 실리지 않았다** — 저장소
        #    전체에 소비자가 0건이었고(클라 포함), 그래서 「목록이 조작자를 초대한다」는
        #    설계가 실제로는 배선된 적이 없다. 세어 놓고 안 보내는 수는 없는 수와 같다.
        "units": [dict({"key": u["key"], "unit_key": u["unit_key"], "state": u["state"],
                        "reason_code": u["reason_code"], "map_count": u["map_count"],
                        "usable_map_count": u["usable_map_count"],
                        "assumable_map_count": u["assumable_map_count"],
                        "confirmation": u["confirmation"]}, **u["extras"])
                  for u in page],
        "stats": {"build_ms": (time.monotonic() - t0) * 1000.0,
                  "map_pairs": sum(len(s) for s in per_unit_maps.values()),
                  "metas_read": len(metas)},
    }
