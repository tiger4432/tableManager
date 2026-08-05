"""Universal Transfer Plan (M2) — 전사(轉寫) 프레임워크: stage 선언 로더 + 가용 엔진 + 계획 검증.

[역할] 모든 전사 단계(DT: core→tape, bonding: tape→base, …)를 전사 프리미티브
`(stage, 타깃 맵 페인팅, assignments)`의 인스턴스로 다룬다. 신규 단계는
`server/config/transfer_plan_config.json`(사용자 config, gitignored)의 stage 선언만으로
추가된다 — 코드에 실테이블명 하드코딩 금지.

[계획 모델 v2 — "계획 = 지금 열어 편집 중인 그 맵" (사용자 확정 2026-07-26)]
계획이라는 **별도 개체는 존재하지 않는다**. `bonding_map`을 열어 편집하면 그게 BONDING
PLAN이고 `dt_map`을 열면 DT PLAN이다. 따라서:
- **계획 정체성 = `(ref_table, map_key)`** — `plan_id`도 계획 헤더 테이블도 없다.
- **stage는 유도된다** — `stages.*.target_map.table`의 역인덱스(`stage_of_table`).
  사용자가 stage를 고르는 동작은 어디에도 없다.
- **페인팅 결과 = 대상 맵 자신의 셀** — 계획 맵 사본(`transfer_plan_map`)은 폐기됐고,
  값 분포는 대상 맵 테이블에서 직접 group-by한다(`_painted_values`).

[M2.6 — the plan store collapsed into ONE table]
`map_doe` and `map_doe_source` are retired. **One `map_split_registry` row = one legend
value = one DOE condition**, bk = `ref_table|map_key|value`.

[ZONE 모델 2026-07-28 — band 모델을 대체한다]
한 값의 층 구조는 **숫자 하나와 구역 셋**이다. FROM도, TO도, band 행도, 값 집합 스코프도
없다:

    STACK = 그 값의 총 층수      (컬럼 `stack`, **문자열** — 읽을 수 없는 원문을 보존한다)
    1H    = 1층                  (컬럼 `mat_1h`, 원문 토큰의 JSON 배열)
    MID   = 그 사이 전부         (컬럼 `mat_mid`)
    TOP   = STACK층              (컬럼 `mat_top`)
    MID 구역 = (1H 있으면 2, 없으면 1) … (TOP 있으면 STACK−1, 없으면 STACK)

- **세 구역이 `1..STACK`을 구성적으로 덮는다.** 그래서 겹침·구멍·`FROM>TO`·`FROM<1`은
  완화된 것이 아니라 **말할 수 없는 상태**가 됐다. 이 파일에 그 검사가 없는 것은 누락이 아니다.
- **`dt_map`은 퇴화형이지 미완성이 아니다**: STACK 1, MID만. **조용히 통과해야 한다.**
- **파생값은 저장하지 않는다.** 구역 총 소요 = 칠한 셀 수 × 층 수, 자재당 = `ceil(총/자재수)`.
  저장된 총계는 누가 한 칸 더 칠하는 순간 어긋난다.
- **자재 문자열은 적은 그대로가 정체다.** 토큰 문법 `lot["_"slot][":"BIN]`은 **공유 계약**
  (`contracts/doe_band_rules/vectors.json`)이며 `parse_material_token`이 유일한 구현이다.
  분리자 없는 `MID1`은 해석 실패가 아니라 **로트 전체**를 뜻한다.
- **차단 규칙은 V1~V6 여섯 개**이고 `validate_zone_plan`이 판정한다. V5(STACK 판독 불가)가
  **가장 먼저**다 — 다른 모든 판정이 계산할 수 없는 층 수에서 유도되기 때문이다.
- **STACK 0 is a MARKER, not a height** (U9, user 2026-07-28). An explicit 0 declares a
  상태 표시 값 (e.g. BASE FAIL): painted cells state a condition, not a layer assignment.
  No zones, zero demand, absent from the rollup; V6 reports the one contradiction (a marker
  with zone content) and is the ONLY rule a marker row answers to. Blank stays blank (V5) —
  absence is not a declaration.
- **폐기된 `bands` 컬럼은 읽되 쓰지 않는다.** `bands_to_zones`가 세 구역으로 옮기고,
  옮길 수 없는 배치(구간 4개·읽을 수 없는 `to`·역전·1층에서 시작하지 않는 첫 구간)는
  **접지 않고 거부**한다. 접은 뒤 저장하면 `replace_map`이 서버의 진짜 계획을 그 손실
  읽기로 덮는다.
- **참조 구현은 `client2/src/doe_bands.js`**이고 양쪽은 같은 벡터 파일로 고정된다.
  한 언어에만 사는 규칙은 흘러간다 — 미러하되 다시 유도하지 말 것.

[경계 계약 — 총괄 고정]
- GET /api/transfer-plan/stages           : 선언 stage 목록 + 역할 연결 상태
- GET /api/transfer-plan/source-summary   : 단계별 소스 가용
  `{identity, stage, source_kind, sources, chips{total, fail_breakdown{...}, transferred,
    remaining}, history, warnings}` + tape 소스면 `by_core` 동봉(집계만 — 칩 좌표 목록 금지)
  `bins=1,2` 지정 시 `bins` 블록 동봉(BIN별 가용 — §BIN 축). `scope=lot`은 슬롯 없이
  로트 전체를 묻는 형태이며 `chips` 없이 `{slots, bins}`만 답한다.
- GET /api/transfer-plan/validate?ref_table=&map_key=  : 계획 경고 목록
- M1 `GET /api/bonding-plan/core-summary`는 외부 계약 불변 — core-kind 소스 가용의
  인스턴스로 내부 통합(본 모듈이 `bonding_plan.get_core_summary`를 어댑터로 감싼다).

[키 파싱 금지 — v1에서 승계한 불변식] 서버는 `map_key`를 **파싱하지 않는다**. 컬럼 equality
조회에만 쓰고, 맵 셀 조회 시의 분해는 `table_config.map_key_columns` 선언에 따른 공용 규칙
(`map_overlay.build_key_filters`) 하나로만 수행한다. 모듈마다 다른 파싱을 도입하지 말 것.

[stage 어휘] 선언된 stage 이름의 **유일한 정본은 이 config의 `stages` 키**이며
`GET /api/transfer-plan/stages`가 그것을 그대로 노출한다. 미선언 stage는 조용히 매핑하지
않고 `stage_unknown`(effect: validation_skipped)으로 표면화한다.

[stage source 선언 2형]
1. `"source_config_ref": "bonding_plan"` — M1 `bonding_plan_config.json`을 소스 역할
   바인딩으로 재사용(하위호환 경로). core-kind 가용 = M1 집계의 재성형(reshape).
2. inline `"source": {...}` — 일반 역할 엔진:
   - `total_chips` / `transfer_log`(기전사 로그, distinct 칩) / `process_history`(M1 규율)
   - `origin_log`: 칩 단위 출신 귀속(tape 소스의 핵심 — dt_log: 테이프 좌표↔코어 좌표)
   - `fail_sources.{name}`: fail 원천. `frame: "origin"`이면 출신(core) 프레임 fail을
     origin_log 조인으로 타깃(tape) 좌표에 투영("테이프에도 불량 섞임" 처리의 핵심),
     `frame: "self"`면 자기 identity 직접 카운트(M1 맵 모드와 동일).

[보조 역할 선언은 선택이다 — relaxation 2026-08-04, 총괄 board request 2]
`transfer_log`·`origin_log`·`fail_sources`·`process_history`는 **키가 아예 없으면**
상태 `not_declared`(강등 아님)로 두고 그 감산항 없이 가용을 **숫자로** 낸다 — 실 현장은
소스별 부속 테이블을 유지하지 않고 맵 자체에 차감을 표기한다(사용자 확정). 빠진 감산
종류는 응답의 선택 필드 `inactive_subtractions`(리스트)가 명시한다 — 총량이 순량 행세를
하는 침묵이 이 필드가 막는 실패다. 이 필드는 **가용 수치를 내는 모든 응답에 같은 이름으로**
붙는다: 슬롯/로트 요약, M1 `core-summary`, 그리고 그 수치로 판정을 내리는 `validate`까지.
(validate에서도 판정 문자열은 바꾸지 않는다 — 미선언은 사이트의 선언이지 결함이 아니다.)
**선언돼 있으나 깨진** 바인딩(null·오타·테이블 부재)은 종전 강등 그대로다 — 완화는
부재에만 적용된다. `total_chips`는 분모라 계속 필수.

[align 규율 — 정렬의 유일한 근거는 `wafer_map_metadata`다 (사용자 확정 2026-07-26)]
fail 원천의 소스 프레임→canonical(core) 프레임 사상은 **두 맵 메타의 델타에서 유도**한다.
config의 `fail_sources[].align` 선언 레이어는 제거됐다 — 계측으로 잰 어긋남도 메타에 적는다.
투영 조인은 좌표 비교이므로 **변환 미해결 시 raw 좌표로 조용히 계산하지 않고 명시 실패**
(`connected(align_unavailable)`, 카운트 0) — QA F2 취지.
변환 구현은 `map_overlay.resolve_map_transform` **하나뿐**이다(오버레이와 공유). 구
`bonding_plan.make_align_transform`은 저장 좌표의 바운딩박스 규약을 반영하지 않아 삭제됐다.

[스냅샷 규율] config는 요청(작업) 경계에서 1회 로드해 전 구간에 인자로 전달한다.
[확장성] 응답은 집계만(칩 좌표 목록 금지). 좌표 페치는 내부 연산 한정 + 하드캡.
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

import paths  # single override point (ASSY_DATA_ROOT)

# [relaxation 2026-08-04 — board request 2] The absent-role vocabulary is shared
# with M1 and defined ONCE in bonding_plan (same one-predicate discipline as
# `transfer_log_is_declared_none`): an auxiliary role key ABSENT from the source
# block is the site stating "no such table here" — status `not_declared`, its
# subtraction inactive (named in `inactive_subtractions`), NOT a degradation.
# A PRESENT-but-broken declaration keeps every pre-existing demotion.
from bonding_plan import STATUS_NOT_DECLARED, role_is_declared

CONFIG_PATH = paths.config_path("transfer_plan_config.json")

# ---- 하드캡 (무제한 로드 금지 — 1,000만 행 규율) ----
MAX_ORIGIN_POINTS = 100_000   # 타깃(테이프) 1장의 origin_log 칩 페치 상한 (내부 연산용)
MAX_FAIL_POINTS = 100_000     # 코어 1장의 fail 좌표 페치 상한
MAX_BY_CORE = 500             # by_core 분해 응답 상한 (초과분 절단 + 경고)
CORE_ID_SEP = "|"             # by_core.core_id 합성 분리자 (lot|slot — bk 관례 '_' 모호 회피)
MAX_DOE_PER_PLAN = 500        # validate가 다루는 DOE 정의(= 레지스트리 행) 상한
MAX_PLAN_VALUES = 1000        # validate의 페인팅 값 group-by 상한
MAX_SOURCES_PER_DOE = 64      # 구간 1건이 묶을 수 있는 자재 상한
MAX_BANDS_PER_PLAN = 2000     # 계획 전체에서 전개하는 구간 상한 (손상된 blob의 폭주 차단)
# [팬아웃 차단] 위 두 상한의 **곱**이 진짜 상한이 되면 안 된다 — 레지스트리 행 하나가
# 128,000 수요와 그만큼의 소스 요약 조회를 낼 수 있었다(실측: 1.53MB blob 1행).
# 수요 총량과 **서로 다른 소스 수**를 따로 묶어야 조회 비용이 blob 크기를 따라 자라지 않는다.
MAX_DEMANDS_PER_PLAN = 5000        # 계획 전체 수요 상한
MAX_SOURCES_PER_PLAN = 200         # 계획 전체에서 가용을 조회하는 **서로 다른** 소스 상한
MAX_BANDS_BLOB_BYTES = 256 * 1024  # `bands` 컬럼 1건의 파싱 전 크기 상한 (json.loads는 캡 밖이다)
# `to`의 유효 크기 상한. JSON 정수 안전범위를 넘는 값은 층 수가 아니라 손상이며, 여기서
# 막지 않으면 `painted × layers`가 수백 자리 정수가 되어 응답에 실린다.
MAX_LAYER = 2 ** 53
MAX_REGION_CELLS = 100_000    # 소스 사용 영역 셀 상한 (내부 연산용 — 응답에 싣지 않는다)
# ---- BIN 축 (DOE_BAND_MODEL §4-bis) ----
MAX_BIN_VALUES = 200          # 맵 1장의 distinct BIN 값 상한 (group-by — 값 하나당 1행)
MAX_BIN_CELLS = 200_000       # BIN 좌표 페치 상한 (맵 1장. 감산항 교차용 — 응답에 싣지 않는다)
MAX_LOT_SLOTS = 50            # `scope=lot` 팬아웃 상한 (로트 1개 = 보통 25슬롯)

M1_SOURCE_REFS = ("bonding_plan",)   # source_config_ref 허용 값

# ---- ZONE 모델 (2026-07-28, bands를 대체) ----
#
#   STACK = 그 값의 총 층수 · 1H = 1층 · TOP = STACK층 · MID = 그 사이 전부
#   MID 구역 = (1H 있으면 2, 없으면 1) … (TOP 있으면 STACK−1, 없으면 STACK)
#
# 세 구역이 `1..STACK`을 **구성적으로** 덮는다. 그래서 구 모델의 겹침(B5)·구멍(B6)·
# `FROM>TO`(B1)·`FROM<1`(B2)은 완화된 것이 아니라 **말할 수 없는 상태가 됐다** — 이 파일에
# 그 검사가 없는 것은 누락이 아니다. 정본 벡터: `contracts/doe_band_rules/vectors.json`.
ZONES = ("mat_1h", "mat_mid", "mat_top")
ZONE_LABEL = {"mat_1h": "1H", "mat_mid": "MID", "mat_top": "TOP"}

# [M2.6→zone] 계획 저장소는 legend 레지스트리 **하나**다. 역할이 하나라도 빠지면 계획을
# 읽을 수단 자체가 없으므로, 조용히 "구간 없음"으로 통과시키지 않고 plan_store
# 미구성(404)으로 떨어뜨린다 — 미선언 컬럼이 200과 함께 드롭되는 것과 같은 계열의 침묵이다.
# ⚠️ `bands`가 여기서 빠진 것이 이 변경의 핵심이다. 그 컬럼은 폐기됐고 writer가 없으므로
#    **필수 역할일 수 없다.** 다만 실계획이 아직 그 컬럼에 남아 있으므로 아래
#    REGISTRY_LEGACY_ROLE로 **선택 역할**로 계속 읽는다(선언돼 있으면 읽고, 없으면 없는 대로).
REGISTRY_ROLES = ("ref_table", "map_key", "value", "stack", "mat_1h", "mat_mid", "mat_top")

# 폐기 모델의 읽기 전용 역할. 필수가 아니라서 미선언 사이트도 404가 되지 않는다.
REGISTRY_LEGACY_ROLE = "bands"

# --- 역할별 필수 키 (한 자리에서 철자한다) ---------------------------------
# 이 튜플들은 예전에 호출 지점마다 인라인으로 다시 적혀 있었다. dry-run이 「이 선언은
# 받아들여지는가」를 답하려면 **판정자와 똑같은 required**를 봐야 하므로, 사본이 아니라
# 같은 상수를 읽는다 ― 두 번째 철자는 곧 두 개의 진실이 된다.
IDENTITY_ROLES = ("lot", "slot")
ORIGIN_LOG_ROLES = ("lot", "slot", "x", "y",
                    "origin_lot", "origin_slot", "origin_x", "origin_y")
ORIGIN_AREA_MAP_ROLES = ("lot", "slot", "x", "y", "val")
SOURCE_REGION_ROLES = ("ref_table", "map_key", "source_lot", "source_slot", "x", "y")
MAP_METADATA_ROLES = ("target_table", "map_id", "grid_metadata")
BIN_AXIS_ROLES = ("lot", "slot", "x", "y", "bin")
LOT_MEMBERSHIP_ROLES = IDENTITY_ROLES

# 선언이 놓일 수 있는 자리(거절 문장이 "어디를 봤는지" 말할 때 쓴다).
BIN_AXIS_WHERE = "stages.<stage>.bin_map 또는 stages.<stage>.source.bin_map"
LOT_MEMBERSHIP_WHERE = "stages.<stage>.source.lot_membership"

# validate 경고 타입 (계약)
WARN_QTY_SHORTAGE = "qty_shortage"
# [zone 모델] 그 값의 **층 구조를 읽지 못했다**. 이제 이 경고는 폐기 모델(`bands`)에서만
# 나온다 — zone 컬럼은 세 칸이 각각 자기 자재를 지고 있어 "구조를 못 읽는" 상태가 없다.
# `reason`:
#   unreadable      — `bands` blob이 배열로 읽히지 않는다
#   not_a_band      — 배열 안에 구간이 아닌 원소가 섞였다
#   not_convertible — 읽히긴 하는데 **세 구역으로 표현할 수 없다**(구간 4개, `to` 불량,
#                     역전, 첫 구간이 1층에서 시작하지 않음). `detail`이 어느 쪽인지 말한다.
# 🔴 `not_convertible`은 **접어서 통과시키지 않는다.** 4구간을 3구역으로 뭉갠 뒤 그 뭉갠
#    결과를 `replace_map`으로 되쓰면 서버의 진짜 계획이 우리 손실 읽기로 덮인다 — 이 영역이
#    존재하는 이유가 정확히 그 결함이다(`contracts/doe_band_rules` legacy_band_cases).
# 구 reason `incomplete`/`not_increasing`은 **거부로 승격**됐다: 편집 중인 패널에는 "보여
# 주고 표시하고 계속"이 옳았지만, 마이그레이션에서 건너뛰면 스택이 조용히 짧아진다.
# `layer_coverage_gap`은 이름이 바뀐 것이 아니라 **삭제**됐다 — 세 구역이 `1..STACK`을
# 구성적으로 덮으므로 구멍은 말할 수 없는 상태다.
WARN_LAYER_RANGE_INVALID = "layer_range_invalid"
# [zone 모델] V1~V5 차단 규칙 위반. `rule` 필드가 어느 규칙인지 말한다.
# 클라 `doe_bands.validateZonePlan`의 blocks와 **같은 판정**이며 정본은 공유 벡터 파일이다.
WARN_ZONE_RULE_VIOLATION = "zone_rule_violation"
# [zone 모델] 차단은 아니지만 파생 수치를 움직이는 것(W-DUP-MAT: 한 구역 안 자재 중복은
# `ceil(total / n)`의 분모를 이유 없이 바꾼다).
WARN_ZONE_RULE_ADVISORY = "zone_rule_advisory"
# [zone 모델] 토큰은 문법상 정상인데(`MID1` = 로트 전체) 이 엔드포인트가 **가용을 확정
# 숫자로 낼 수 없다**. `scope=lot` 응답에는 `chips`가 없다 — 로트 전체의 `remaining` 하나를
# 지어내지 않겠다는 `get_lot_bin_summary`의 결정 때문이다. 그래서 "해석 실패"가 아니라
# "판정 안 함"으로 이름 붙여 내보낸다. 0으로 접으면 "다 썼다"로 읽힌다.
WARN_SOURCE_SCOPE_UNPRICED = "source_scope_unpriced"
WARN_UNDEFINED_DOE_VALUE = "undefined_doe_value"
# [B2] 페인팅 분포를 못 읽었거나 절단됐다. 수량이 **저장이 아니라 painted에서 유도**되므로
# 이 읽기가 실패하면 모든 required가 0이 되어 부족이 영원히 발화하지 않는다. 구 모델은
# qty_total을 저장에서 읽어 이 실패에 면역이었다 — 유도로 바꾸면서 생긴 새 의존이다.
WARN_PAINTED_UNAVAILABLE = "painted_unavailable"
WARN_DOE_VALUE_UNPAINTED = "doe_value_unpainted"
WARN_SOURCE_FAIL_CHIPS = "source_fail_chips"
WARN_SOURCE_HISTORY_FAIL = "source_history_fail"
WARN_STAGE_UNKNOWN = "stage_unknown"
WARN_SOURCE_UNRESOLVED = "source_unresolved"
# [QA F1] 역할 강등의 표면화 — "조용한 과대 산출" 차단
WARN_SOURCE_DEGRADED = "source_degraded"
WARN_AVAILABILITY_UNRELIABLE = "availability_unreliable"
# [QA F4] 여러 DOE가 한 소스를 나눠 쓸 때의 합산 초과배정
WARN_SOURCE_OVERALLOCATED = "source_overallocated"
# [QA F2] 하드캡 절단의 표면화 (조용한 오답 금지 — F1과 동일 계열)
WARN_RESULT_TRUNCATED = "result_truncated"
# [QA N1] remaining 음수 = 원천 간 모집단 불일치 (불변식 위반)
WARN_NEGATIVE_REMAINING = "negative_remaining"
EFFECT_POPULATION_MISMATCH = "population_mismatch"
# [BIN 축] BIN 분해를 만들 수 없다 — 클라는 `가용`을 숫자로 그리면 안 된다
WARN_BIN_AXIS_UNAVAILABLE = "bin_axis_unavailable"
# [BIN 축] Σ bins.total ≠ chips.total — 두 모집단(맵 셀 / 칩 원천)이 어긋났다
WARN_BIN_POPULATION_MISMATCH = "bin_population_mismatch"
EFFECT_BIN_AXIS_UNAVAILABLE = "bin_axis_unavailable"
# [로트 전개] 슬롯을 세는 원천이 없다 — 빈 목록으로 위장하면 진단면이 "깨끗함"을 보고한다
WARN_LOT_MEMBERSHIP_UNKNOWN = "lot_membership_unknown"
# [로트 전개] 대장 미선언 → 맵이 있는 슬롯만 전개됐다(불일치 진단이 성립하지 않는다)
WARN_LOT_MEMBERSHIP_DEGRADED = "lot_membership_degraded"
# [로트 전개] 대장에는 있는데 맵이 없는 슬롯 — 사람이 그리드에서 고쳐야 할 어긋남
WARN_LOT_SLOT_MAP_MISSING = "lot_slot_map_missing"
EFFECT_LOT_EXPANSION_PARTIAL = "lot_expansion_partial"

# [7c] `"transfer_log": "none"` — the site DECLARES that consumption is not
# recorded (e.g. no bonding-consumption log exists at all). This is a stated
# fact, not a broken binding: status is `connected(untracked)` (NOT degraded),
# remaining stays null but `remaining_upper_bound` (= total − fail) is served
# with its own warning so the client can render "≤N" instead of 미상.
# ONLY the exact string "none" declares this — JSON null stays "missing"
# (null is indistinguishable from an accidental absent-key edit), and every
# other accidental-missing shape behaves exactly as before.
TRANSFER_LOG_NONE = "none"
STATUS_TRANSFER_UNTRACKED = "connected(untracked)"
WARN_TRANSFER_UNTRACKED = "transfer_untracked"
EFFECT_REMAINING_UPPER_BOUND = "remaining_upper_bound"

# BIN 항목 status (계약). **`0`은 이 셋 중 어느 것도 대신할 수 없다** —
# `0`은 "다 썼다"로 읽히고 `bin_absent`는 "그 BIN이 여기 없다"이며, 사용자는 두 경우에
# 서로 다르게 행동해야 한다(DOE_BAND_MODEL §4-bis 🔴).
BIN_OK = "ok"
BIN_ABSENT = "bin_absent"
BIN_UNKNOWN = "unknown"          # 존재는 아는데 수를 신뢰할 수 없다(절단 등)
BIN_SCOPE_SLOT = "slot"
BIN_SCOPE_LOT = "lot"

# 강등 효과 분류 (역할별로 remaining에 미치는 방향이 다르다)
EFFECT_REMAINING_OVERSTATED = "remaining_overstated"   # 감산항(fail/기전사) 과소 → remaining 과대
EFFECT_TOTAL_UNKNOWN = "total_unknown"                 # 분모 자체가 불명 → remaining 무의미
EFFECT_BY_CORE_DEGRADED = "by_core_degraded"           # by_core 분해만 열화 (remaining 무관)
EFFECT_HISTORY_INCOMPLETE = "history_incomplete"       # 이력만 누락 (remaining 무관)


# ---------------------------------------------------------------------------
# config 로더 (파일 경계 스냅샷 — 요청당 1회)
# ---------------------------------------------------------------------------

def load_transfer_plan_config(path: str = None) -> dict:
    """transfer_plan_config.json 로드. 없거나 손상 시 {} (부분 가동 — 에러 아님)."""
    p = path or CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            logger.warning("[TransferPlan] config root is not an object — ignored: %s", p)
            return {}
        return raw
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("[TransferPlan] failed to load config %s: %s", p, e)
        return {}


def get_stages(cfg: dict) -> dict:
    stages = cfg.get("stages")
    return stages if isinstance(stages, dict) else {}


def _valid_binding(src) -> bool:
    """{table, columns} 최소 형태 검증 (bonding_plan._valid_source와 동일 규약)."""
    return (
        isinstance(src, dict)
        and isinstance(src.get("table"), str) and src.get("table")
        and isinstance(src.get("columns"), dict)
    )


def transfer_log_is_declared_none(src) -> bool:
    """[7c / INV-7c-2] Is this `transfer_log` config value the DECLARATION that
    consumption is not recorded anywhere?

    ONLY the exact string `"none"` declares it. `"None"`, `"NONE"`, `" none "`,
    `""`, JSON `null`, an absent key, and a real binding object (even one whose
    table is literally named "none") are NOT declarations — every one of them
    stays accidental-missing and renders 미상, exactly as before 7c existed.

    The strictness is the whole point. A declaration means a human knowingly
    stated "there is no transfer log here", which downgrades the reading to
    `connected(untracked)` and lets a remaining UPPER BOUND be served instead of
    nothing. Promoting a typo would convert an accident into a claim of
    knowledge — a wrong answer indistinguishable from a right one. So: no
    casefolding, no strip(), no truthiness, no membership test.

    The counterpart of `_valid_binding` at the same config boundary: that one
    answers "is this a binding", this one answers "is this the stated absence
    of one". Extracted out of the DB-bound `_summarize_inline` branch so the
    invariant is scoreable without a live fixture (contracts/map_seam). Reads
    the module-level constant at call time, so repointing it (mutation twin in
    server/tests/test_transfer_untracked.py) still disarms every reader.

    🔴 ONE PREDICATE, EVERY READER CALLS IT. Both current readers go through
    here — `_stage_role_statuses` (the /stages role view) and
    `_summarize_inline` (the availability engine). A third reader must CALL
    this, never re-spell `src == TRANSFER_LOG_NONE`: a second spelling is only
    scored by whichever site the contract happens to point at, and the other
    one then drifts unwatched. That is the defect shape this project keeps
    paying for (`bonding_plan`'s private copy of the alignment transform,
    issue #20) and the seam contract exists to end it.
    """
    return isinstance(src, str) and src == TRANSFER_LOG_NONE


def _resolve(src_cfg: dict, required: tuple):
    """바인딩 → (model, {역할키: ORM 컬럼}). 실패 시 (None, None) — missing 부분 가동."""
    import bonding_plan
    if not _valid_binding(src_cfg):
        return None, None
    return bonding_plan._resolve_model_columns(src_cfg, required=required)


def _demote_unresolved(status, cols):
    """[FIX 2026-07-28] Declared-but-unresolved columns must not vanish silently —
    compose the `column_unresolved:<roles>` marker into a connected-status
    (shared mechanics live in bonding_plan next to the resolver)."""
    import bonding_plan
    return bonding_plan._demote_for_unresolved(status, cols)


def _unresolved_of(cols) -> tuple:
    """Declared-but-unresolved role keys of a resolved binding."""
    import bonding_plan
    return bonding_plan._unresolved_roles(cols)


def _fail_filter_status(src_cfg, cols, status="connected"):
    """[N14] Is this source's `fail_values` applicable? -> `(refused, status)`.

    Thin pass-through to `bonding_plan.fail_filter_status` (which owns the
    ruling, next to the resolver) so both frames of `fail_sources` and M1's
    defect/eds_fail roles score against ONE predicate. Reads the attribute at
    call time, so repointing it (the byte-identity twin in
    server/tests/test_optional_role_absence.py) disarms every reader at once."""
    import bonding_plan
    return bonding_plan.fail_filter_status(src_cfg, cols, status)


def _identity_filters(src_cfg, cols, lot, slot):
    """[7b] The (lot, slot) pool bind used by every role query — each value is
    canonicalized by the DECLARED type of the bound column
    (`map_overlay.canonical_key_value` is THE implementation — do not fork it).
    A parsed token '01' must find a number-declared pool storing 1; cell-data
    filters already cast by declared type, this is the same discipline here."""
    import map_overlay
    return [cols["lot"] == map_overlay.canonical_role_value(src_cfg, "lot", lot),
            cols["slot"] == map_overlay.canonical_role_value(src_cfg, "slot", slot)]


# ---------------------------------------------------------------------------
# stage 목록 + 역할 연결 상태 (데이터 쿼리 없음 — 바인딩 해석만)
# ---------------------------------------------------------------------------

def _binding_status(src_cfg, required=("lot", "slot")) -> str:
    if not _valid_binding(src_cfg):
        return "missing"
    model, cols = _resolve(src_cfg, required)
    return "missing" if model is None else _demote_unresolved("connected", cols)


def _aux_role_status(block, key, required=("lot", "slot")) -> str:
    """[relaxation] Auxiliary-role status: an ABSENT key is a declared non-use
    (`not_declared`), a PRESENT value goes through the normal binding judgement
    and keeps every degradation. total_chips must NOT come through here — the
    denominator stays required."""
    if not role_is_declared(block, key):
        return STATUS_NOT_DECLARED
    return _binding_status(block.get(key), required)


def _stage_role_statuses(stage_cfg: dict) -> dict:
    """stage의 소스 역할별 연결 상태 (모델·컬럼 해석만 — 행 조회 없음)."""
    import bonding_plan
    ref = stage_cfg.get("source_config_ref")
    if ref in M1_SOURCE_REFS:
        bp_cfg = bonding_plan.load_bonding_plan_config()
        sources = (bp_cfg.get("sources") or {})
        return {
            "total_chips": _binding_status(sources.get("total_chips")),
            "transfer_log": _aux_role_status(sources, "used_chips"),
            "process_history": _aux_role_status(sources, "process_history"),
            "defect": _aux_role_status(sources, "defect"),
            "eds_fail": _aux_role_status(sources, "eds_fail"),
        }

    source = stage_cfg.get("source") or {}
    out = {
        "total_chips": _binding_status(source.get("total_chips")),
        # [7c] the exact string "none" is a declared state, not a missing binding.
        # Through the shared predicate — never re-spell the comparison here.
        # [relaxation] an absent key is a declared non-use — not_declared.
        "transfer_log": (STATUS_TRANSFER_UNTRACKED
                         if transfer_log_is_declared_none(source.get("transfer_log"))
                         else _aux_role_status(source, "transfer_log")),
        "process_history": _aux_role_status(source, "process_history"),
        "origin_log": _aux_role_status(source, "origin_log"),
    }
    if _valid_binding(source.get("origin_area_map")):
        out["origin_area_map"] = _binding_status(source.get("origin_area_map"))
    fail_sources = source.get("fail_sources") or {}
    if isinstance(fail_sources, dict):
        for name, fs in fail_sources.items():
            out[str(name)] = _binding_status(fs)
    return out


def _plan_store_statuses(cfg: dict) -> dict:
    """계획 저장소 역할 상태.

    [v2] `plan`(헤더)·`map`(계획 맵 사본) 역할은 폐기됐다 — 계획 정체가
    `(ref_table, map_key)`이고 페인팅 결과가 곧 대상 맵 자신의 셀이라 사본이 존재할
    이유가 없다.
    [M2.6] `doe`·`doe_source` 역할도 폐기됐다 — legend 행 하나가 곧 DOE 조건 하나이고
    층 구조는 그 행의 zone 컬럼(`stack`·`mat_1h`·`mat_mid`·`mat_top`)에 있다. 남는 역할은
    레지스트리 하나뿐이다.
    [zone] `bands`는 **필수 역할에서 빠졌다** — 폐기됐고 writer가 없으므로 필수일 수 없다.
    선언돼 있으면 폐기 계획을 읽는 데 계속 쓰고(REGISTRY_LEGACY_ROLE), 없으면 없는 대로
    간다. 그 컬럼 하나 때문에 전 사이트가 404가 되던 상태가 여기서 끝난다.

    `material_identity`는 테이블 바인딩이 아니라 문자열 해석 규칙이라 별도로 판정한다.
    미선언이면 **모든** 자재가 해석 불가가 되어 계획 전체가 unverified로 떨어지므로,
    수요마다 경고를 내기 전에 배선 상태 자체로 드러낸다.
    """
    store = cfg.get("plan_store") or {}
    out = {
        "registry": _binding_status(store.get("registry"), required=REGISTRY_ROLES),
        "material_identity": "connected" if _material_identity_rule(cfg) else "missing",
    }
    if _valid_binding(store.get("source_region")):
        out["source_region"] = _binding_status(
            store.get("source_region"),
            required=SOURCE_REGION_ROLES)
    return out


def stage_of_table(cfg: dict, ref_table: str):
    """맵 테이블 → stage **역인덱스**. 미선언 테이블이면 None.

    [v2 모델의 핵심] 사용자는 stage를 고르지 않는다 — `bonding_map`을 열면 bonding,
    `dt_map`을 열면 dt다. 이 매핑은 이미 `stages.*.target_map.table`에 선언돼 있으므로
    새 계약이 아니라 **기존 선언의 역방향 조회**다.
    """
    if not ref_table:
        return None
    for name, stage_cfg in get_stages(cfg).items():
        if not isinstance(stage_cfg, dict):
            continue
        if ((stage_cfg.get("target_map") or {}).get("table")) == ref_table:
            return name
    return None


def list_stages(cfg: dict) -> dict:
    """GET /api/transfer-plan/stages 응답 본문."""
    stages_out = []
    for name, stage_cfg in get_stages(cfg).items():
        if not isinstance(stage_cfg, dict):
            continue
        stages_out.append({
            "name": name,
            "description": stage_cfg.get("description"),
            "source_kind": stage_cfg.get("source_kind"),
            "target_kind": stage_cfg.get("target_kind"),
            "target_map": stage_cfg.get("target_map") or {},
            "roles": _stage_role_statuses(stage_cfg),
        })
    return {"stages": stages_out, "plan_store": _plan_store_statuses(cfg)}


# ---------------------------------------------------------------------------
# dry-run ― 「이 선언은 받아들여지는가, 아니면 왜 거절되는가」
# ---------------------------------------------------------------------------
#
# 왜 유도와 **같은 라운드**에 존재하는가: 유도는 조용히 틀릴 수 있다. 어느 철자가
# 이겼는지 볼 자리가 없으면, 우리는 「선언이 조용히 먹지 않는」 결함을 「유도가 조용히
# 엉뚱한 컬럼을 골랐다」로 바꿔 놓았을 뿐이다. 그래서 이 경로는 역할마다
# **선언인지 유도인지 + 해석된 실제 컬럼명 + 유도 출처**를 함께 낸다. "됩니다"는 답이
# 아니다.
#
# 선례: `GET /admin/enrichment/auto-confirm/dry-run`. 그쪽은 `ignore_knob=True`로 **꺼진**
# 규칙을 재고, 이쪽은 **아직 안 쓰이는** 선언을 잰다 ― 둘 다 "켜기/쓰기 전에 답해야 하는
# 질문"이라는 같은 형태다. 데이터는 건드리지 않는다(모델·컬럼 해석만, 행 조회 없음).

# 역할 카탈로그 ― (역할키, 필수 튜플, 자리 표기). dry-run과 판정자가 같은 required를
# 본다는 것이 이 표의 존재 이유다.
_STAGE_SOURCE_ROLES = (
    ("map_metadata", MAP_METADATA_ROLES),
    ("total_chips", IDENTITY_ROLES),
    ("transfer_log", IDENTITY_ROLES),
    ("process_history", IDENTITY_ROLES),
    ("origin_log", ORIGIN_LOG_ROLES),
    ("origin_area_map", ORIGIN_AREA_MAP_ROLES),
    ("lot_membership", LOT_MEMBERSHIP_ROLES),
)

# 선택 역할 카탈로그 ― 「없어도 거절되지 않지만, 없으면 **무엇이 꺼지는가**」.
#
# WHY (board N14, 2026-08-04). 필수 역할은 지우면 유도가 메운다 ― 그래서 이 라운드의
# 수리 지침이 「고치지 말고 지워라」가 됐다. 선택 역할은 **절대 유도되지 않는다**
# (부재가 곧 정보이므로 메우면 숫자가 조용히 바뀐다 ― `bonding_plan.DERIVED_ROLE_OF`
# 주석의 load-bearing restriction). 그래서 한 줄 더 지우면 기능이 조용히 꺼진다.
#
# dry-run이 **선언된 줄만** 보여주는 한 그 부재는 어디에도 나타나지 않는다: 지우기 전
# 보고서는 컬럼 5개, 지운 뒤는 4개이고, 어느 필드도 하나가 사라졌다고 말하지 않는다
# (QA F5가 잰 그대로). 부재를 행으로 내는 것이 이 표의 목적이며, 선언 의미론은 아무것도
# 바뀌지 않는다 ― `accepted`도 `reason`도 그대로다. 「이 능력은 지금 꺼져 있다」는
# 사실만 이름을 얻는다.
#
# 등재 기준: **부재가 계산 결과나 경고를 바꾸는** 역할만. 순수 표시용 필드(step/eqp/
# recipe/knobs)는 넣지 않는다 ― 전부 넣으면 이 표는 스키마 덤프가 되고, 진짜 위험한
# 세 줄이 그 안에 묻힌다.
FAIL_SOURCE_ROLE = "fail_sources"
_OPTIONAL_ROLE_EFFECTS = {
    "total_chips": (
        ("x", "총칩 좌표 집합 ― 영역(region)·BIN별 총계를 계산합니다. 없으면 그쪽 "
              "total/remaining이 null이 되고 BIN 항목은 unknown으로 내려갑니다."),
        ("y", "총칩 좌표 집합 ― 영역(region)·BIN별 총계를 계산합니다. 없으면 그쪽 "
              "total/remaining이 null이 되고 BIN 항목은 unknown으로 내려갑니다."),
    ),
    "transfer_log": (
        ("x", "기전사 칩의 **집합** 감산 ― 없으면 카운트만 쓰는 "
              "connected(count_only)로 강등되고 remaining은 상한(≤)만 나갑니다."),
        ("y", "기전사 칩의 **집합** 감산 ― 없으면 카운트만 쓰는 "
              "connected(count_only)로 강등되고 remaining은 상한(≤)만 나갑니다."),
    ),
    "process_history": (
        ("time", "이력 정렬(최근 50건) ― 없으면 정렬 없이 임의의 50건이 나갑니다."),
        ("result", "result_fail 경고(`warnings.result_fail_values`) ― 없으면 공정 실패 "
                   "이력 경고가 한 건도 발화하지 않습니다."),
    ),
    FAIL_SOURCE_ROLE: (
        ("val", "fail 값 필터(`fail_values`) ― 없으면 fail 판정을 내릴 수 없으므로 이 "
                "감산은 0으로 거절되고 소스가 강등됩니다(fail_value_column_absent). "
                "`fail_values`를 선언했다면 이 역할은 사실상 필수입니다."),
        ("x", "fail 칩의 좌표 집합 ― frame=\"origin\"이면 투영 자체가 불가(강등)이고, "
              "frame=\"self\"이면 집합 감산이 카운트 감산으로 내려갑니다."),
        ("y", "fail 칩의 좌표 집합 ― frame=\"origin\"이면 투영 자체가 불가(강등)이고, "
              "frame=\"self\"이면 집합 감산이 카운트 감산으로 내려갑니다."),
    ),
    "registry": (
        (REGISTRY_LEGACY_ROLE,
         "폐기 모델(구 구간 blob)의 읽기 전용 역할 ― 없으면 그 컬럼에 남아 있는 구 형식 "
         "계획의 구간이 읽히지 않습니다(신 모델 계획에는 영향 없음)."),
    ),
}


def _role_dry_run(src, required: tuple, label: str, where: str,
                  optional: tuple = ()) -> dict:
    """역할 1건의 dry-run 항목. **행 조회 없음** ― 모델/컬럼 해석만."""
    import bonding_plan
    from database import models

    reason, detail = bonding_plan.explain_binding_refusal(
        src, required, label=label, where=where)
    declared_cols = (src.get("columns") if isinstance(src, dict) else None) or {}
    effective, derivation = (bonding_plan.resolve_effective_columns(src, required)
                             if isinstance(src, dict) else ({}, {}))
    if not isinstance(effective, dict):
        effective = {}
    table = src.get("table") if isinstance(src, dict) else None
    model = models.DYNAMIC_TABLES.get(table) if isinstance(table, str) else None

    # 필수 역할 ∪ **선언된 역할 전부**. 선택 역할을 빼면 운영자는 자기가 적은 줄의 절반을
    # 이 화면에서 못 본다 ― 그리고 선택 역할이야말로 **유도되지 않는다**(부재가 곧 정보라
    # 절대 메우지 않는다). 그러니 "이건 지워도 유도된다"와 "이건 지우면 기능이 사라진다"를
    # 구별해 보여줘야 한다. `required` 플래그가 그 구별이다.
    columns = {}
    for role in list(required) + [r for r in declared_cols if r not in required]:
        col = effective.get(role, declared_cols.get(role))
        d = derivation.get(role)
        if role in declared_cols:
            origin = "declared"
        elif d and d.get("column"):
            origin = "derived"
        else:
            origin = "absent"
        columns[role] = {
            "column": col,
            "origin": origin,
            "required": role in required,
            # 선택 역할은 유도 대상이 아니다 ― 지우면 그 감산/집계가 조용히 사라진다.
            "derivable": role in required and role in bonding_plan.DERIVED_ROLE_OF,
            # 유도 출처 ― 어느 선언에서 왔는지. "됐다"가 아니라 "어디서 왔다"를 낸다.
            "derived_from": (d or {}).get("source") if origin == "derived" else None,
            "derived_role": (d or {}).get("from_role") if origin == "derived" else None,
            "exists_on_table": (None if (model is None or not col)
                                else getattr(model, str(col), None) is not None),
            # 선언·유도된 줄에는 「꺼진 기능」이 없다. 키는 항상 존재한다 ―
            # 소비자가 분기 없이 읽을 수 있어야 한다.
            "effect": None,
        }

    # [N14] 선택 역할의 **부재를 행으로** 낸다. 선언된 줄만 세면 "지운 줄"은 보고서에서
    # 사라지고, 사라진 것이 무엇이었는지 물을 자리조차 없다. 선언 의미론은 불변이다 ―
    # `accepted`/`reason`은 이 행들과 무관하다.
    #
    # 단, **선언 자체가 없는 역할**에는 내지 않는다. 그 역할은 이미 `declared: false`로
    # 자기 상태를 말했고, 거기에 선택 컬럼 3개를 더 얹으면 「이 사이트가 안 쓰는 것」이
    # 「운영자가 지운 것」을 덮어버린다(라이브 config에서 이 구분 없이 세면 50행이다).
    # 이 표가 답하는 질문은 「내가 지운 그 줄이 무엇이었나」이고, 그 질문은 columns 블록이
    # 존재할 때만 성립한다.
    for role, effect in (optional if isinstance(src, dict) else ()):
        if role in columns:
            continue          # 선언(또는 필수)돼 있으면 이미 자기 행이 있다
        columns[role] = {
            "column": None,
            "origin": "absent",
            "required": False,
            "derivable": False,     # 선택 역할은 유도되지 않는다(부재가 곧 정보다)
            "derived_from": None,
            "derived_role": None,
            "exists_on_table": None,
            "effect": effect,
        }

    # 「선언이 이긴다」의 뒷면: 틀린 선언은 유도가 있어도 계속 이긴다 → 수리법은 *지우기*.
    removable = []
    if model is not None and isinstance(src, dict):
        broken = [r for r in required
                  if effective.get(r) and getattr(model, str(effective[r]), None) is None]
        removable = [{"role": r, "would_derive": c}
                     for r, c in bonding_plan.deletion_hints(src, broken, model)]

    return {
        "role": label,
        "where": where,
        "declared": src is not None,
        "table": table,
        "accepted": reason is None,
        "reason": reason,
        "detail": detail,
        "required": list(required),
        "columns": columns,
        "removable_declarations": removable,
    }


def dry_run(cfg: dict) -> dict:
    """전 역할의 수용/거절 판정 + 어느 철자가 이겼는지. 읽기 전용, 데이터 미조회."""
    import bonding_plan
    BINDING_NOT_REACHED = bonding_plan.BINDING_NOT_REACHED
    stages_out = []
    for name, stage_cfg in get_stages(cfg).items():
        if not isinstance(stage_cfg, dict):
            continue
        source = stage_cfg.get("source") or {}
        roles = [_role_dry_run(_bin_axis_source(stage_cfg), BIN_AXIS_ROLES,
                               "bin_map", f"stages.{name}.bin_map")]
        ref = stage_cfg.get("source_config_ref")
        if ref in M1_SOURCE_REFS:
            # 이 stage는 소스 역할을 M1 config에 위임한다 ― 자기 `source.*`는 **읽히지
            # 않는다**. 그걸 `not_declared`로 내면 운영자에게 "여기를 채워라"라고 말하는
            # 셈이고, 채워도 아무 일도 일어나지 않는다. `not_reached`가 정확히 이 뜻이다.
            import bonding_plan as _bp
            for role, required in _STAGE_SOURCE_ROLES:
                roles.append({
                    "role": role, "where": f"stages.{name}.source.{role}",
                    "declared": source.get(role) is not None, "table": None,
                    "accepted": False, "reason": _bp.BINDING_NOT_REACHED,
                    "detail": (f"이 stage는 소스 역할을 `{ref}` config에 위임합니다"
                               f"(`source_config_ref`) ― `stages.{name}.source.{role}`은 "
                               f"읽히지 않습니다. 이 역할은 bonding_plan_config.json에서 "
                               f"선언하세요."),
                    "required": list(required), "columns": {},
                    "removable_declarations": [],
                })
            stages_out.append({
                "name": name, "source_config_ref": ref,
                "target_map": stage_cfg.get("target_map") or {}, "roles": roles,
            })
            continue
        for role, required in _STAGE_SOURCE_ROLES:
            if role == "transfer_log" and transfer_log_is_declared_none(source.get(role)):
                # [7c] 정확한 문자열 "none"은 선언된 상태지 깨진 바인딩이 아니다.
                roles.append({
                    "role": role, "where": f"stages.{name}.source.{role}",
                    "declared": True, "table": None, "accepted": True,
                    "reason": None,
                    "detail": "소비를 기록하지 않는다고 **선언**돼 있습니다(`\"none\"`).",
                    "required": list(required), "columns": {},
                    "removable_declarations": [],
                })
                continue
            roles.append(_role_dry_run(source.get(role), required, role,
                                       f"stages.{name}.source.{role}",
                                       _OPTIONAL_ROLE_EFFECTS.get(role, ())))
        for fname, fs in (source.get("fail_sources") or {}).items():
            roles.append(_role_dry_run(fs, IDENTITY_ROLES, f"fail_sources.{fname}",
                                       f"stages.{name}.source.fail_sources.{fname}",
                                       _OPTIONAL_ROLE_EFFECTS[FAIL_SOURCE_ROLE]))
        stages_out.append({
            "name": name,
            "source_config_ref": stage_cfg.get("source_config_ref"),
            "target_map": stage_cfg.get("target_map") or {},
            "roles": roles,
        })

    store = cfg.get("plan_store") or {}
    store_roles = [
        _role_dry_run(store.get("registry"), REGISTRY_ROLES,
                      "registry", "plan_store.registry",
                      _OPTIONAL_ROLE_EFFECTS["registry"]),
        _role_dry_run(store.get("source_region"), SOURCE_REGION_ROLES,
                      "source_region", "plan_store.source_region"),
    ]

    every = [r for s in stages_out for r in s["roles"]] + store_roles
    return {
        "config_path": CONFIG_PATH,
        "stages": stages_out,
        "plan_store": store_roles,
        "counts": {
            "total": len(every),
            "accepted": sum(1 for r in every if r["accepted"]),
            "rejected": sum(1 for r in every
                            if not r["accepted"] and r["declared"]
                            and r["reason"] != BINDING_NOT_REACHED),
            "not_declared": sum(1 for r in every if not r["declared"]
                                and r["reason"] != BINDING_NOT_REACHED),
            "not_reached": sum(1 for r in every if r["reason"] == BINDING_NOT_REACHED),
            "derived_columns": sum(
                1 for r in every for c in r["columns"].values()
                if c.get("origin") == "derived"),
            # [N14] 지금 꺼져 있는 **선택** 능력의 수(강등 수가 아니다).
            # ⚠️ `origin == "absent"`만으로 세면 **미선언 필수 역할**까지 딸려 온다 —
            # 라이브 config에서 30 대 4다. 이 카운트가 답하는 질문은 「받아들여지는데도
            # 꺼져 있는 기능이 몇 개인가」이므로 `required is False`가 술어의 절반이다.
            "absent_optional_columns": sum(
                1 for r in every for c in r["columns"].values()
                if c.get("origin") == "absent" and c.get("required") is False),
            "removable_declarations": sum(
                len(r["removable_declarations"]) for r in every),
        },
    }


# ---------------------------------------------------------------------------
# 소스 가용 엔진
# ---------------------------------------------------------------------------

def _status_is_degraded(status) -> bool:
    """역할 상태 문자열이 '강등'인가.

    정상: "connected", "connected(aligned:180)" 등 align 마커만 붙은 경우.
          [7c] "connected(untracked)"도 강등이 **아니다** — 선언된 상태다(전사 기록이
          없다고 사이트가 명시). remaining 처리는 `_summarize_inline`이 별도 규율
          (`WARN_TRANSFER_UNTRACKED` + 상한 제공)로 한다.
          [relaxation] "not_declared"도 강등이 아니다 — 보조 역할 키의 **부재**는
          그런 테이블을 안 쓴다는 사이트의 상태다. 감산 없이 집계하며, 빠진 종류는
          `inactive_subtractions` 필드가 말한다.
    강등: "missing", "unavailable(...)", "connected(align_unavailable)", "connected(area_only)",
          "connected(count_only)"(transfer_log 또는 self-frame fail 원천이 좌표 없이
          카운트만 제공 — 집합 감산 불가),
          "connected(column_unresolved:...)"(선언된 컬럼이 모델에 없음 — config 오타 축),
          "connected(fail_value_column_absent)"([N14] `fail_values`는 선언됐는데 그 값을
          읽을 `val` 역할이 **아예 없음** — 감산항이 통째로 빠진다. 마커 문자열은
          `bonding_plan`의 상수를 읽는다: 두 번째 철자는 곧 두 개의 진실이 된다).
    """
    import bonding_plan
    if not status or status == "connected" or status == STATUS_NOT_DECLARED:
        return False
    if status.startswith("connected("):
        return (("align_unavailable" in status) or ("area_only" in status)
                or ("count_only" in status) or ("column_unresolved" in status)
                or (bonding_plan.FAIL_VALUE_COLUMN_ABSENT in status))
    return True   # missing / unavailable(...) 등


def _degradation_effect(role: str, fail_roles: set) -> str:
    """강등된 역할이 집계에 미치는 효과를 분류한다."""
    if role == "total_chips":
        return EFFECT_TOTAL_UNKNOWN
    if role == "process_history":
        return EFFECT_HISTORY_INCOMPLETE
    if role == "origin_area_map":
        return EFFECT_BY_CORE_DEGRADED
    # transfer_log / origin_log / fail 원천 → 감산항 과소 → remaining 과대
    if role == "transfer_log" or role == "origin_log" or role in fail_roles:
        return EFFECT_REMAINING_OVERSTATED
    return EFFECT_REMAINING_OVERSTATED


def assess_degradation(statuses: dict, fail_roles: set):
    """[QA F1] 역할 상태 → (강등 경고 목록, remaining 신뢰 여부, total 신뢰 여부).

    "부분 가동"은 조용해선 안 된다 — 역할이 무너져 감산항이 0이 되면 remaining이 **과대**로
    부푸는데, 이를 sources 문자열에만 적어두면 소비자(클라·validate)가 정상으로 오인한다.
    따라서 강등은 반드시 warnings에 명시 항목으로 싣고, remaining 자체의 신뢰도를 값으로
    표현한다(신뢰 불가 시 remaining=None — 소비자가 분기 없이는 표시조차 못 하게).
    """
    warnings_out = []
    remaining_reliable = True
    total_reliable = True

    for role in sorted(statuses.keys()):
        status = statuses[role]
        if not _status_is_degraded(status):
            continue
        effect = _degradation_effect(role, fail_roles)
        if effect == EFFECT_TOTAL_UNKNOWN:
            total_reliable = False
            remaining_reliable = False
            detail = f"역할 '{role}' 강등({status}) — 총 칩 수를 알 수 없어 remaining을 산출할 수 없음"
        elif effect == EFFECT_REMAINING_OVERSTATED:
            remaining_reliable = False
            detail = (f"역할 '{role}' 강등({status}) — 해당 집계가 누락되어 "
                      f"remaining이 실제보다 과대일 수 있음")
        elif effect == EFFECT_BY_CORE_DEGRADED:
            detail = f"역할 '{role}' 강등({status}) — by_core 분해만 열화(remaining 영향 없음)"
        else:
            detail = f"역할 '{role}' 강등({status}) — 이력 일부 누락(remaining 영향 없음)"
        warnings_out.append({
            "type": WARN_SOURCE_DEGRADED,
            "role": role,
            "status": status,
            "effect": effect,
            "detail": detail,
        })
    return warnings_out, remaining_reliable, total_reliable


def build_chips_block(total, fail_breakdown, transferred, remaining,
                      remaining_reliable, total_reliable):
    """chips 블록 생성 — 신뢰 불가 시 remaining을 None으로 내린다(오표시 구조적 차단).

    반환: (chips dict, 추가 경고 리스트)

    remaining_upper_bound는 **total이 신뢰 가능할 때만** 싣는다. total까지 강등된 경우의
    계산값은 상한이 아니라 무의미한 값이므로 상한이라 칭하지 않는다.

    [QA N1 불변식] `remaining < 0`은 물리적으로 불가능하다 — 나오면 원천 간 **모집단
    불일치**(마스크 밖 좌표, 중복 행, 프레임 불일치, 백필 과도기 등)라는 뜻이다. 전 역할이
    connected여도 수치는 틀린 것이므로 신뢰 불가로 강등하고 표면화한다. 이 3줄이 원인별
    개별 수정 없이 계열 전체를 막는다.
    """
    extra_warnings = []
    if remaining is not None and remaining < 0:
        remaining_reliable = False
        extra_warnings.append({
            "type": WARN_NEGATIVE_REMAINING,
            "effect": EFFECT_POPULATION_MISMATCH,
            "computed": remaining,
            "detail": (f"remaining이 음수({remaining}) — 감산항이 총칩을 초과했다. "
                       f"원천 간 모집단 불일치(마스크 밖 좌표·중복 행·프레임 불일치·백필 "
                       f"과도기)를 의심해야 하며 이 수치는 신뢰할 수 없다"),
        })

    chips = {
        "total": total,
        "fail_breakdown": fail_breakdown,
        "transferred": transferred,
        "remaining": remaining if remaining_reliable else None,
        "remaining_reliable": remaining_reliable,
    }
    if not remaining_reliable and total_reliable:
        # 감산항만 과소하므로 계산값은 진짜 remaining의 상한이다.
        # (음수 케이스는 상한으로서도 무의미하므로 싣지 않는다 — 진짜 잔여는 0 이상이다.)
        if not (remaining is not None and remaining < 0):
            chips["remaining_upper_bound"] = remaining
    return chips, extra_warnings


def load_source_region(db, cfg: dict, ref_table: str, map_key: str,
                       source_lot: str, source_slot: str):
    """[②] 계획의 '이 소스에서 쓰기로 한 영역'을 셀 집합으로 로드한다.

    ⚠️ **휴면 중 (총괄 지시로 보류)**. `plan_store.source_region` 바인딩이 라이브 config에
    선언돼 있지 않아 이 경로는 항상 None을 반환한다. 배선 누락 결함이 아니다.
    v2 모델에 맞춰 **키만 `(ref_table, map_key, source_lot, source_slot)`로 이동**했다
    (구 키 `plan_id`는 소멸). 살릴지 여부는 자재 맵 왕복 UX 확정 후 결정한다.

    자유 페인팅 결과라 rect로는 표현되지 않으므로 셀 집합 테이블에서 집합으로 읽는다
    (rect는 UX 보조일 뿐 저장 정본이 아니다).
    반환: set[(x, y)] 또는 None(바인딩 미선언/미해석 — 영역 스코프 없음).
    """
    store = (cfg.get("plan_store") or {}).get("source_region")
    model, cols = _resolve(store, required=SOURCE_REGION_ROLES)
    if model is None:
        return None
    import map_overlay
    try:
        rows = (db.query(cols["x"], cols["y"])
                .filter(cols["ref_table"] == ref_table,
                        cols["map_key"] == map_key,
                        # [7b] source identity comes from parsed tokens — canonical bind
                        cols["source_lot"] == map_overlay.canonical_role_value(
                            store, "source_lot", source_lot),
                        cols["source_slot"] == map_overlay.canonical_role_value(
                            store, "source_slot", source_slot))
                .limit(MAX_REGION_CELLS).all())
    except Exception as e:
        logger.warning("[TransferPlan] source_region query failed (%s/%s/%s/%s): %s",
                       ref_table, map_key, source_lot, source_slot, e)
        return None
    if len(rows) >= MAX_REGION_CELLS:
        logger.warning("[TransferPlan] source_region hit hard cap (%d)", MAX_REGION_CELLS)
    return {(int(x), int(y)) for (x, y) in rows if x is not None and y is not None}


def _region_block(total_pts, fail_sets: dict, used_set: set, region: set) -> dict:
    """영역 내 가용 집계 — 전체 집계와 동일한 합집합 의미론을 영역으로 좁힌 것."""
    in_region_total = {p for p in total_pts if p in region} if total_pts is not None else None
    fb = {}
    fail_union = set()
    for name, s in fail_sets.items():
        if s is None:
            fb[name] = None
            continue
        hit = {p for p in s if p in region}
        fb[name] = len(hit)
        fail_union |= hit
    used_hit = {p for p in used_set if p in region}
    block = {
        "cells": len(region),
        "total": len(in_region_total) if in_region_total is not None else None,
        "fail_breakdown": fb,
        "transferred": len(used_hit),
    }
    if in_region_total is not None:
        block["remaining"] = len(in_region_total) - len(fail_union | used_hit)
    else:
        block["remaining"] = None
    return block


def _core_region_counts(db, bp_cfg: dict, lot: str, slot: str, region: set):
    """[②] core-kind(M1 위임) 소스의 영역 내 집계.

    M1 `get_core_summary`는 rect만 받으므로 셀 집합을 넘길 수 없다. M1 config의 역할
    바인딩을 M2 어댑터 형태로 읽어 좌표 집합을 직접 구성한다(정렬은 M1과 동일하게 메타
    델타에서 유도해 canonical 사상 후 교차).

    ⚠️ 어댑터의 `fail_sources`는 **`bonding_plan.CANONICAL_FRAME_ROLES`와 같은 순서**로
    쌓는다 — `_canonical_origin_meta`가 이 순서로 canonical 프레임을 고르므로, 순서가
    다르면 M1 `get_core_summary`와 다른 프레임을 기준 삼아 두 경로의 수치가 갈린다.
    `frame`을 "self"로 두면 canonical 후보가 하나도 없어 dst 메타가 None이 되고, 그러면
    정렬이 통째로 identity로 떨어진다(조용한 오답).
    """
    import bonding_plan

    sources = (bp_cfg.get("sources") or {})
    adapter = {
        "identity": bp_cfg.get("core_identity") or {"compose": ["lot", "slot"]},
        "map_metadata": bp_cfg.get("map_metadata"),
        "fail_sources": {
            k: dict(sources[k], frame="origin")
            for k in bonding_plan.CANONICAL_FRAME_ROLES
            if _valid_binding(sources.get(k))
        },
    }

    # total 좌표
    total_pts = None
    src = sources.get("total_chips")
    model, cols = _resolve(src, required=("lot", "slot"))
    if model is not None and "x" in cols and "y" in cols:
        pts, _tr = _fetch_pairs(db, cols, _identity_filters(src, cols, lot, slot),
                                cap=MAX_REGION_CELLS, tag="region:total")
        total_pts = set(pts)

    # fail 좌표 (align 적용 — canonical 프레임)
    fail_sets = {}
    for name in ("defect", "eds_fail"):
        fs = sources.get(name)
        model, cols = _resolve(fs, required=("lot", "slot"))
        if model is None or "x" not in cols or "y" not in cols:
            fail_sets[name] = None
            continue
        pts, _mk, _tr = _canonical_fail_set(db, adapter, fs, cols, lot, slot)
        fail_sets[name] = pts   # None이면 align 불가 → 영역 집계도 미상

    # 기전사 좌표
    used_set = set()
    src = sources.get("used_chips")
    model, cols = _resolve(src, required=("lot", "slot"))
    if model is not None and "x" in cols and "y" in cols:
        pts, _tr = _fetch_pairs(db, cols, _identity_filters(src, cols, lot, slot),
                                distinct=True, cap=MAX_REGION_CELLS, tag="region:used")
        used_set = set(pts)

    return _region_block(total_pts, fail_sets, used_set, region)


# ---------------------------------------------------------------------------
# BIN 축 — `(자재, BIN)` 단위 가용 (DOE_BAND_MODEL §4-bis)
#
# [왜 필요한가] DT 맵은 하나의 풀이 아니다. BIN으로 분할돼 있고 서로 다른 DOE 값이 **같은
# 맵에서** 다른 BIN을 경쟁 없이 가져간다. BIN을 접으면 `잔여`가 낮게 나오는데 왜인지
# 화면에 보이지 않는다.
#
# [`가용`의 정의 — 확정] `가용(bin)` := **그 BIN 셀들로 스코프한 `remaining`**, 즉
# `|총 ∩ bin| − |(fail ∪ 전사) ∩ bin|`이다. 사용자가 처음 적은 "그 자재·BIN의 DT 맵 셀 수"
# (= 아래 `cells`)가 **아니다**. 근거 셋:
#   ① `잔여 = 가용 − 사용`이 행동 가능하려면 `가용`은 "아직 뽑을 수 있는 좋은 다이 수"여야
#      한다. 총 셀 수는 이미 불량이거나 이미 전사된 다이를 포함하므로, 그것으로 계산한
#      `잔여`는 조용히 덜 주문하는 계획을 만든다 — 스펙이 가장 나쁘다고 못박은 결과다.
#   ② 한 화면에 `가용`이 두 뜻으로 존재할 수 없다. 헤드라인 칩이 이미 `remaining`을 쓴다.
#   ③ **결정적**: 순수 `COUNT(*)`는 신뢰 불가가 될 수 없다. 지시서 ②가 요구한 "BIN별 신뢰
#      플래그"는 감산항(fail·전사)의 완전성에 대한 판정이므로, 셀 수 정의에서는 전파할
#      원천 자체가 존재하지 않는다. 요구 ②가 성립하는 정의는 하나뿐이다.
# 원래 정의도 버리지 않는다 — `cells`로 함께 싣는다(맵이 그 BIN을 몇 칸 칠했는가).
#
# [재사용] 산술은 `_region_block` **그대로**다. BIN은 좌표 부분집합이고 영역도 좌표
# 부분집합이라 구조적으로 같은 연산이며, fail·전사의 합집합 의미론(이중 감산 없음)이
# 자동으로 따라온다. 두 번째 산술 구현을 만들지 않는 것이 요점이다.
# ---------------------------------------------------------------------------

def parse_bin_request(raw):
    """`bins=1,2,7` → `(요청 BIN 리스트|None, 거부된 토큰 리스트)`.

    `None`(요청 없음)과 `[]`(전부 거부됨)은 **다르다**. 전자는 "맵에 있는 BIN을 다 보여라",
    후자는 "물어본 BIN이 하나도 읽히지 않았다"이며 후자에서 빈 목록을 내보내면 호출자가
    "BIN이 없는 맵"으로 오해한다.
    """
    if raw is None:
        return None, []
    s = str(raw).strip()
    if s == "":
        return None, []
    out, refused = [], []
    for tok in s.split(","):
        b = _bin_of(tok)
        if b is None:
            refused.append(tok.strip())
        elif b not in out:
            out.append(b)
    return out, refused


def _bin_axis_source(stage_cfg: dict):
    """이 stage가 제시하는 `bin_map` 선언(둘 중 먼저 읽히는 자리). 없으면 None."""
    stage_cfg = stage_cfg if isinstance(stage_cfg, dict) else {}
    return (stage_cfg.get("bin_map")
            if isinstance(stage_cfg.get("bin_map"), dict)
            else (stage_cfg.get("source") or {}).get("bin_map"))


def _bin_axis_binding(stage_cfg: dict):
    """stage의 `bin_map` 선언 → `(model, cols, src_cfg)`. 미선언/미해석이면
    `(None, None, None)`. src_cfg는 [7b] 캐노니컬 바인드가 선언 타입을 찾는 근거다.

    **컬럼을 추측하지 않는다.** "맵의 `val`이 곧 BIN"으로 박으면 라이브에서 즉시 틀린다 —
    같은 `dt_map.val`을 이 config는 이미 `origin_area_map`의 **코어 식별자**로 선언하고
    있다. 한 컬럼이 두 뜻일 수는 있어도 그건 사이트가 정할 일이지 코드가 정할 일이 아니다.
    선언이 없으면 축은 `unavailable`이고, 그건 결함이 아니라 **아직 배선되지 않음**이다.

    `bin_map`은 stage 자신의 블록에 둔다(`source_config_ref` 위임 경로에도 붙일 수 있게).

    **왜 거절이 여기서 끝나지 않는가**: 이 함수는 여전히 yes/no만 답한다. 사유는
    `_bin_axis_refusal`이 같은 입력으로 만든다 ― 판정 경로에 문장 생성을 섞으면
    정상 경로가 매번 컬럼 목록을 만들게 된다.
    """
    src = _bin_axis_source(stage_cfg)
    model, cols = _resolve(src, required=BIN_AXIS_ROLES)
    return model, cols, (src if model is not None else None)


def _refusal(src, roles, label, where) -> tuple:
    """`explain_binding_refusal`의 얇은 래퍼 ― 문장이 **비어서 나가는 일은 없다**.

    진단기는 성공 시 `(None, None)`을 돌려준다(그 계약을 테스트가 채점한다). 거절
    경로에서 그 값을 그대로 문장에 끼우면 화면에 `None`이 뜬다 ― 사유를 이름 붙이려고
    한 일이 정확히 반대 결과를 낸다. 그래서 정규화는 한 곳에서만 한다.
    """
    import bonding_plan
    why, detail = bonding_plan.explain_binding_refusal(src, roles, label=label, where=where)
    if detail is None:
        return (None, f"`{label}` 바인딩은 해석됐는데 축을 만들지 못했습니다 "
                      f"― 서버 로그를 확인하세요.")
    return why, detail


def _bin_axis_refusal(stage_cfg: dict) -> tuple:
    """왜 이 stage의 BIN 축을 만들지 못했는가 ― `(reason, 한국어 문장)`.

    거절이 자기 사유를 말하지 못하면 운영자에게 남는 일은 이분 탐색뿐이다. 2주 사이
    세 번(보드 O4·O7, 2026-08-04 라이브 `bin_map.columns.x`) 「디스크에는 멀쩡한 선언」이
    조용히 먹지 않았고, 그때마다 화면에 뜬 문장은 똑같이 "선언돼 있지 않습니다"였다 ―
    선언은 있었는데도. 판정은 `bonding_plan`의 리졸버가 그대로 하고, 여기서는 같은
    입력을 다시 걸어 **첫 번째로 실패한 검사**를 문장으로 만든다.
    """
    return _refusal(_bin_axis_source(stage_cfg), BIN_AXIS_ROLES,
                    "bin_map", BIN_AXIS_WHERE)


def _bins_unavailable(detail: str, scope: str, requested=None,
                      reason: str = None) -> dict:
    """축을 만들 수 없을 때의 블록. **`entries`를 빈 배열로 두지 않는다** —
    빈 배열은 "BIN이 하나도 없다"로 읽히고, 그건 우리가 아는 사실이 아니다.

    `detail`은 클라이언트가 **그대로 렌더**하는 사람이 읽을 문장이고(client2
    `transfer_plan.js`의 `bins_unavailable` 경로), `reason`은 그 문장을 분류하는 닫힌
    어휘(`bonding_plan.BINDING_REFUSALS`)다. 선언이 원인이 아닌 거절(질의 실패·상한
    절단 등)에는 `reason`이 없다 ― 어휘 밖 사유에 억지로 단어를 붙이지 않는다.
    """
    return {
        "axis": "unavailable", "detail": detail, "scope": scope,
        "reason": reason,
        "requested": list(requested) if requested else None,
        "entries": None, "truncated": False, "cells_truncated": False,
    }


def _bin_universe(db, cols, filters):
    """맵의 BIN 분포를 **group-by 한 번**으로 센다 (셀 전량 로드 금지).

    반환: `(cells_by_bin, raws_by_bin, unbinned_cells, cells_total, truncated)`.
    `truncated`는 distinct 값이 상한을 넘었다는 뜻이며, 그때는 **부재를 증명할 수 없다**
    (못 본 값 중에 있을 수 있다) — 호출자가 `bin_absent` 대신 `unknown`을 쓴다.
    [재현성] 절단이 가능하면 어떤 행이 살아남는지가 결정적이어야 한다 → ORDER BY.
    """
    from sqlalchemy import func
    rows = (db.query(cols["bin"], func.count())
            .filter(*filters)
            .group_by(cols["bin"])
            .order_by(cols["bin"])
            .limit(MAX_BIN_VALUES + 1).all())
    truncated = len(rows) > MAX_BIN_VALUES
    if truncated:
        logger.warning("[TransferPlan] bin universe hit distinct cap (%d) — absence unprovable",
                       MAX_BIN_VALUES)
        rows = rows[:MAX_BIN_VALUES]

    cells_by_bin, raws_by_bin = {}, {}
    unbinned = 0
    cells_total = 0
    for (raw, cnt) in rows:
        cnt = int(cnt or 0)
        cells_total += cnt
        b = _bin_of(raw)
        if b is None:
            unbinned += cnt          # BIN이 아닌 값 — 조용히 버리지 않고 센다
            continue
        cells_by_bin[b] = cells_by_bin.get(b, 0) + cnt
        raws_by_bin.setdefault(b, []).append(raw)
    return cells_by_bin, raws_by_bin, unbinned, cells_total, truncated


def _bin_cell_sets(db, cols, filters, raws):
    """필요한 BIN들의 좌표 집합만 페치한다. 반환: `({bin: set[(x,y)]}, truncated)`.

    `raws`는 원시 값 목록이라 `'1'`과 `'01'`이 함께 들어오고 둘 다 BIN 1로 접힌다.
    [확장성] 요청 BIN이 지정되면 IN 필터가 걸려 조회 비용이 맵 전체가 아니라 그 BIN들에
    비례한다 — 큰 맵에서 한 BIN만 묻는 것이 싼 질의가 되어야 한다.
    """
    if not raws:
        return {}, False
    rows = (db.query(cols["x"], cols["y"], cols["bin"])
            .filter(*filters, cols["bin"].in_(list(raws)))
            .limit(MAX_BIN_CELLS + 1).all())
    truncated = len(rows) > MAX_BIN_CELLS
    if truncated:
        logger.warning("[TransferPlan] bin cell fetch hit hard cap (%d)", MAX_BIN_CELLS)
        rows = rows[:MAX_BIN_CELLS]
    out = {}
    for (x, y, raw) in rows:
        if x is None or y is None:
            continue
        b = _bin_of(raw)
        if b is None:
            continue
        out.setdefault(b, set()).add((int(x), int(y)))
    return out, truncated


def _bins_block(db, stage_cfg, lot, slot, total_pts, fail_union, used_set,
                requested, refused, base_reliable, chips_total, scope=BIN_SCOPE_SLOT,
                untracked=False, transfer_inactive=False):
    """`(자재, BIN)` 단위 가용 블록. 산술은 `_region_block` 재사용.

    [7c] `untracked=True` = transfer_log가 "none"으로 **선언**됐다. used_set은 빈
    집합이므로 `|bin∩총| − |bin∩fail|`은 진짜 상한이다(감산항이 빠지면 값은 커질
    수만 있다) — 확정 `remaining`으로는 내보내지 않고 `remaining_upper_bound` +
    `transfer_untracked` 플래그로 내보낸다. `transferred`는 가짜 0이 아니라 null.
    `base_reliable`은 **untracked 원인을 제외한** 신뢰도다 — 다른 강등이 겹치면
    상한도 성립을 주장하지 않고 기존 unknown 처리로 떨어진다."""
    model, cols, bin_src = _bin_axis_binding(stage_cfg)
    if model is None:
        # 사유를 이름으로 말한다. 예전 문장은 원인과 무관하게 "선언돼 있지 않습니다"
        # 하나였고, 선언이 **있는데** 컬럼명이 틀린 가장 흔한 경우에 그 문장은 거짓이다.
        why, detail = _bin_axis_refusal(stage_cfg)
        return _bins_unavailable(
            f"BIN별 가용을 계산할 수 없습니다 ― {detail}", scope, requested, reason=why)

    filters = _identity_filters(bin_src, cols, lot, slot)
    try:
        cells_by_bin, raws_by_bin, unbinned, cells_total, uni_trunc = _bin_universe(
            db, cols, filters)
    except Exception as e:
        logger.warning("[TransferPlan] bin universe query failed (%s/%s): %s", lot, slot, e)
        return _bins_unavailable(f"BIN 분포 조회에 실패했습니다: {e}", scope, requested)

    # 좌표는 **필요한 BIN만** 가져온다 — 요청이 없으면 맵에 있는 전부.
    wanted = list(requested) if requested is not None else sorted(cells_by_bin.keys())
    need_raws = [r for b in wanted for r in raws_by_bin.get(b, ())]
    try:
        cell_sets, cell_trunc = _bin_cell_sets(db, cols, filters, need_raws)
    except Exception as e:
        logger.warning("[TransferPlan] bin cell query failed (%s/%s): %s", lot, slot, e)
        return _bins_unavailable(f"BIN 좌표 조회에 실패했습니다: {e}", scope, requested)

    entries = []
    for b in wanted:
        cells = cells_by_bin.get(b, 0)
        if cells == 0:
            if uni_trunc:
                # 부재를 **증명할 수 없다** — 못 본 값 중에 있을 수 있다. 0도 부재도 아니다.
                entries.append({
                    "bin": b, "status": BIN_UNKNOWN, "cells": None, "total": None,
                    "fail_breakdown": None, "transferred": None, "remaining": None,
                    "reliable": False,
                    "reason": (f"BIN 분포가 상한({MAX_BIN_VALUES})으로 절단돼 BIN {b}의 "
                               f"존재 여부를 확인할 수 없습니다."),
                })
            else:
                entries.append({
                    "bin": b, "status": BIN_ABSENT, "cells": 0, "total": None,
                    "fail_breakdown": None, "transferred": None, "remaining": None,
                    "reliable": False,
                    "reason": f"BIN {b}이(가) 이 맵에 없습니다 — 소진된 것이 아닙니다.",
                })
            continue

        block = _region_block(total_pts, {"all_fail": fail_union}, used_set,
                              cell_sets.get(b, set()))
        reasons = []
        if not base_reliable:
            reasons.append("소스 집계가 신뢰 불가로 강등됐습니다")
        if cell_trunc:
            reasons.append(f"BIN 좌표가 상한({MAX_BIN_CELLS})으로 절단됐습니다")
        if total_pts is None:
            reasons.append("총칩 좌표를 알 수 없어 BIN별 총계를 계산할 수 없습니다")
        reliable = not reasons
        entry = {
            "bin": b, "status": BIN_OK if reliable else BIN_UNKNOWN,
            "cells": cells,
            "total": block["total"],
            "fail_breakdown": block["fail_breakdown"],
            # [7c] untracked면 transferred는 미상이다 — used_set이 비어 있어 0이
            # 나오는데 그건 "한 칩도 안 썼다"가 아니라 "기록이 없다"다.
            # [relaxation] transfer_inactive(미선언)도 같은 이유로 미상. 단
            # remaining은 숫자로 남는다 — 감산 없는 가용이 헤드라인과 같은 의미다.
            "transferred": (None if (untracked or transfer_inactive)
                            else block["transferred"]),
            # 🔴 신뢰 불가면 숫자를 내보내지 않는다. `remaining_upper_bound`와 같은 규율:
            #    확정처럼 보이는 수를 준 뒤 플래그로 취소하는 것은 이미 실패한 방식이다.
            "remaining": block["remaining"] if reliable and not untracked else None,
            "reliable": reliable and not untracked,
            "reason": " · ".join(reasons),
        }
        if untracked:
            # [7c] chips 블록과 같은 형태: remaining은 null로 두고 상한을 제 이름으로.
            entry["transfer_untracked"] = True
            if reliable:
                entry["remaining_upper_bound"] = block["remaining"]
                entry["reason"] = ("전사 기록이 '없음'으로 선언됨(transfer_log: none) — "
                                   "잔여는 상한(≤)만 제공")
            # else: 다른 강등이 겹쳤다 — 상한의 성립도 주장하지 않는다(기존 사유가 말한다)
        entries.append(entry)

    out = {
        "axis": "connected", "scope": scope,
        "requested": list(requested) if requested is not None else None,
        "entries": entries,
        "truncated": uni_trunc, "cells_truncated": cell_trunc,
        "unbinned_cells": unbinned, "cells_total": cells_total,
        "population_ref": chips_total,
    }
    if refused:
        out["refused"] = list(refused)
    return out


def _merge_bins_over_slots(blocks, scope, requested, refused):
    """`scope=lot` — 슬롯별 BIN 블록을 합산한다.

    > ### ⚠️ 이 수는 **배분이 아니라 충분성 판정**이다 (사용자 확정 2026-07-27)
    > 실제로는 "첫 장부터 꽉꽉 채워가며" 한 장씩 소진되고 **무엇부터 쓰는지 아무도
    > 기록하지 않는다.** 그래서 풀 합계가 답할 수 있는 질문은 하나뿐이다 —
    > *"이 풀 전체에 충분한가"*(양수면 가능). **"이 웨이퍼가 정확히 N장을 댄다"로
    > 읽히면 안 된다.** 응답의 `basis: "pool_sufficiency"`가 그 해석을 못박는다.
    > 균등 배분처럼 보이는 수를 배분이라고 이름 붙이는 순간, 아무도 지키지 않는 배분을
    > 지킨다고 믿는 계획이 만들어진다.

    합산 규칙 (전부 "조용한 오답 금지"의 같은 계열):
    * `remaining`/`total`/`transferred`는 **모든 기여 슬롯이 신뢰 가능할 때만** 합산한다.
      하나라도 신뢰 불가면 그 BIN은 `unknown` + `remaining=None`이다. 신뢰 가능한 슬롯만
      더한 부분합을 총계처럼 내보내면 잔여 과소 → **부풀린 소요**가 된다.
    * `bin_absent`는 **모든 슬롯에서 없을 때만** 부재다. 한 슬롯에만 있으면 존재한다.
    """
    agg = {}
    for blk in blocks:
        for e in (blk.get("entries") or []):
            a = agg.setdefault(e["bin"], {
                "cells": 0, "total": 0, "transferred": 0, "remaining": 0,
                "fail": 0, "present": False, "reliable": True, "reasons": [],
            })
            if e["status"] != BIN_ABSENT:
                a["present"] = True
            if not e.get("reliable"):
                a["reliable"] = False
                if e.get("reason") and e["reason"] not in a["reasons"]:
                    a["reasons"].append(e["reason"])
                continue
            a["cells"] += int(e.get("cells") or 0)
            a["total"] += int(e.get("total") or 0)
            # [relaxation] a reliable entry may carry transferred=None (transfer
            # log never declared) — the pool sum is then unknown too, never a
            # fake 0 assembled from Nones.
            if e.get("transferred") is None:
                a["transferred"] = None
            elif a["transferred"] is not None:
                a["transferred"] += int(e.get("transferred") or 0)
            a["remaining"] += int(e.get("remaining") or 0)
            a["fail"] += int((e.get("fail_breakdown") or {}).get("all_fail") or 0)

    entries = []
    for b in sorted(agg.keys()):
        a = agg[b]
        if not a["present"]:
            entries.append({
                "bin": b, "status": BIN_ABSENT, "cells": 0, "total": None,
                "fail_breakdown": None, "transferred": None, "remaining": None,
                "reliable": False,
                "reason": f"BIN {b}이(가) 이 로트의 어느 슬롯에도 없습니다 — 소진된 것이 아닙니다.",
            })
            continue
        if not a["reliable"]:
            entries.append({
                "bin": b, "status": BIN_UNKNOWN, "cells": None, "total": None,
                "fail_breakdown": None, "transferred": None, "remaining": None,
                "reliable": False,
                "reason": " · ".join(a["reasons"]) or "일부 슬롯의 집계를 신뢰할 수 없습니다",
            })
            continue
        entries.append({
            "bin": b, "status": BIN_OK, "cells": a["cells"], "total": a["total"],
            "fail_breakdown": {"all_fail": a["fail"]}, "transferred": a["transferred"],
            "remaining": a["remaining"], "reliable": True, "reason": "",
        })

    out = {
        "axis": "connected", "scope": scope,
        # 소비자가 이 수를 무엇으로 읽어야 하는지를 **응답 안에** 적는다.
        "basis": "pool_sufficiency",
        "requested": list(requested) if requested is not None else None,
        "entries": entries,
        "truncated": any(b.get("truncated") for b in blocks),
        "cells_truncated": any(b.get("cells_truncated") for b in blocks),
        "unbinned_cells": sum(int(b.get("unbinned_cells") or 0) for b in blocks),
        "cells_total": sum(int(b.get("cells_total") or 0) for b in blocks),
        "population_ref": sum(int(b.get("population_ref") or 0) for b in blocks),
    }
    if refused:
        out["refused"] = list(refused)
    return out


def _lot_membership_refusal(stage_cfg: dict) -> tuple:
    """왜 자재 대장(`lot_membership`)을 읽지 못했는가 ― `(reason, 한국어 문장)`.

    `bin_map`과 **같은 진단기**를 쓴다. 두 원천이 각자의 문장 규칙을 가지면 운영자가
    두 어휘를 배워야 하고, 하나만 개선되는 순간 나머지가 옛 문장에 남는다.
    """
    stage_cfg = stage_cfg if isinstance(stage_cfg, dict) else {}
    return _refusal((stage_cfg.get("source") or {}).get("lot_membership"),
                    LOT_MEMBERSHIP_ROLES, "lot_membership", LOT_MEMBERSHIP_WHERE)


def _lot_slots(db, stage_cfg, lot):
    """로트의 슬롯 목록. 반환: `(슬롯 리스트|None, truncated, origin)`.

    **`origin`이 이 함수에서 가장 중요한 반환값이다.** 로트 전개는 예쁘게 보여주는 기능이
    아니라 **로트 데이터 품질의 진단면**이다 — "랏이 스플릿됐는데 아직 LOT에 자재가 OVER하게
    있으면" 사람이 그 어긋남을 여기서 보고 그리드에 가서 고친다(핵심가치 ① 교정면).
    그래서 슬롯 목록은 **실제로 전산에 기록된 것**에서 와야지, 맵이 있는 것만 세면 안 된다.
    맵이 없는 슬롯이야말로 봐야 하는 행이기 때문이다.

    | origin | 원천 | 한계 |
    |---|---|---|
    | `membership` | 선언된 `source.lot_membership` (자재 대장) | 없음 — 기록된 그대로 |
    | `map` | BIN 축 맵의 distinct 슬롯 (강등 폴백) | **맵이 있는 슬롯만 보인다** — 진단이 조용히 "깨끗함"으로 보고될 수 있다. 호출자가 경고로 표면화한다 |
    | `None` | 둘 다 없음 | 빈 목록이 **아니라** "이 로트의 구성을 알 수 없음"이다 |

    `by_core`가 `origin_log`(정확) → `origin_area_map`(강등) + `by_core_origin` 마커로 이미
    쓰는 패턴과 같다 — 강등 경로를 없애지 않고 **이름 붙여 내보낸다.**
    """
    import map_overlay
    src = (stage_cfg.get("source") or {}).get("lot_membership")
    model, cols = _resolve(src, required=LOT_MEMBERSHIP_ROLES)
    origin = "membership"
    if model is None:
        model, cols, src = _bin_axis_binding(stage_cfg)
        origin = "map"
    if model is None:
        return None, False, None
    rows = (db.query(cols["slot"])
            .filter(cols["lot"] == map_overlay.canonical_role_value(src, "lot", lot))
            .distinct().order_by(cols["slot"]).limit(MAX_LOT_SLOTS + 1).all())
    truncated = len(rows) > MAX_LOT_SLOTS
    if truncated:
        rows = rows[:MAX_LOT_SLOTS]
    return [r[0] for r in rows if r[0] is not None], truncated, origin


def _reshape_m1_summary(m1: dict, stage_name: str, stage_cfg: dict) -> dict:
    """M1 core-summary(계약 §C) → M2 공통 형태로 재성형 (core-kind 가용의 내부 통합)."""
    chips = m1.get("chips") or {}
    src = m1.get("sources") or {}
    statuses = {
        "total_chips": src.get("total_chips", "missing"),
        "transfer_log": src.get("used_chips", "missing"),
        "process_history": src.get("process_history", "missing"),
        "defect": src.get("defect", "missing"),
        "eds_fail": src.get("eds_fail", "missing"),
    }
    # [QA F1] core-kind 경로도 동일한 강등 노출을 갖는다 — 같은 규율로 표면화한다.
    # ([relaxation] `not_declared`는 강등이 아니므로 assess_degradation이 지나친다 —
    #  M1이 감산항 없이 낸 remaining이 숫자로 그대로 나간다.)
    deg_warnings, remaining_reliable, total_reliable = assess_degradation(
        statuses, fail_roles={"defect", "eds_fail"})
    used_not_declared = statuses["transfer_log"] == STATUS_NOT_DECLARED
    chips_block, inv_warnings = build_chips_block(
        total=chips.get("total", 0),
        fail_breakdown={
            "defect": chips.get("defect", 0),
            "eds_fail": chips.get("eds_fail", 0),
        },
        # [relaxation] 소모 로그 미선언이면 transferred는 미상(0으로 위장 금지)
        transferred=None if used_not_declared else chips.get("used", 0),
        remaining=chips.get("remaining", 0),
        remaining_reliable=remaining_reliable,
        total_reliable=total_reliable,
    )
    out = {
        "identity": m1.get("identity"),
        "stage": stage_name,
        "source_kind": stage_cfg.get("source_kind"),
        "sources": statuses,
        "chips": chips_block,
        "history": m1.get("history") or [],
        "warnings": deg_warnings + inv_warnings + (m1.get("warnings") or []),
    }
    # [relaxation] M1이 감산에서 뺀 종류를 M2 어휘로 개명해 그대로 나른다
    # (used_chips → transfer_log — /stages의 역할 개명과 같은 매핑).
    inactive = [("transfer_log" if r == "used_chips" else r)
                for r in (m1.get("inactive_subtractions") or [])]
    if inactive:
        out["inactive_subtractions"] = inactive
    return out


def _fetch_pairs(db, cols, filters, distinct=False, cap=MAX_FAIL_POINTS, tag=""):
    """(x,y) 좌표 페치. 반환: (좌표 리스트, 캡 도달 여부).

    [QA F2] 캡 도달을 **호출자에게 반환**한다 — 로그로만 남기면 절단된 오답이 정상 응답과
    구별 불가해진다(total은 count()라 절단되지 않아 분자·분모의 모집단이 어긋난다).
    """
    q = db.query(cols["x"], cols["y"]).filter(*filters)
    if distinct:
        q = q.distinct()
    pts = q.limit(cap).all()
    truncated = len(pts) >= cap
    if truncated:
        logger.warning("[TransferPlan] %s point fetch hit hard cap (%d) — counts truncated", tag, cap)
    return [(int(x), int(y)) for (x, y) in pts if x is not None and y is not None], truncated


def _origin_map_id(source_cfg, origin_lot, origin_slot, binding=None) -> str:
    """[7b] Origin map identity, canonicalized per the DECLARED column types of
    the table whose meta is being looked up (`binding` = that source's
    {table, columns}) — the meta row was registered from that table's stored
    values, so 'LOT'/'01' must compose as 'LOT_1' when slot is number-declared.
    THE composer is `map_overlay.compose_map_id` — do not fork it."""
    import map_overlay
    identity_cols = (source_cfg.get("identity") or {}).get("compose") or ["lot", "slot"]
    return map_overlay.compose_map_id(
        identity_cols, {"lot": origin_lot, "slot": origin_slot}, binding)


def _canonical_origin_meta(db, source_cfg, origin_lot, origin_slot,
                           cache: dict = None, meta_cache: dict = None):
    """출신(core) 프레임의 **canonical 맵 메타**를 로드한다.

    canonical = origin_log의 `(origin_x, origin_y)`가 사는 프레임, 즉 코어 웨이퍼 자신의
    맵이다. 좌표를 바인딩한 **첫** `frame == "origin"` 원천(config 선언 순서 — 라이브는
    defect = core_defect_map이 먼저다)이 기준을 정의하며, 그 원천의 메타가 없으면 None을
    돌려준다. **뒤 원천으로 넘어가지 않는다.**

    ⚠️ 넘어가면 회전된 계측 맵이 스스로 기준을 참칭한다. 그러면 소스 == 기준이라 변환이
    identity로 떨어지고, 상태는 `connected`인 채 fail 투영이 통째로 빠진다(조용한 과소
    집계). 기준을 모르면 모른다고 해야 한다 — 호출자가 align_unavailable로 표면화한다.

    격자 규격만이 아니라 메타 전체가 필요하다 — 정렬은 회전·면·y반전·start·치수·phys 전부의
    델타에서 유도되므로, 치수만 넘기면 나머지 축의 차이가 조용히 무시된다.
    """
    if cache is not None and (origin_lot, origin_slot) in cache:
        return cache[(origin_lot, origin_slot)]

    import bonding_plan

    # 프레임을 정의할 수 있는 원천들의 (table, map_id). 아래 두 경로가 **같은 목록**을 본다.
    origin_maps = []
    for fs in (source_cfg.get("fail_sources") or {}).values():
        if not _valid_binding(fs):
            continue
        if (fs.get("frame") or "origin") != "origin":
            continue
        cols = fs.get("columns") or {}
        if "x" not in cols or "y" not in cols:
            continue      # 좌표가 없는 원천은 프레임을 정의할 수 없다
        # [7b] identity canonicalized per the frame-defining table's declared types
        origin_maps.append(
            (fs["table"], _origin_map_id(source_cfg, origin_lot, origin_slot, binding=fs)))

    # [층 ⑧ 2026-08-05] 확정 기록이 있으면 그것이 기준이다. M1 `get_core_summary`와 **같은
    # 함수**를 부른다 — 위 ⚠️와 같은 계급의 사고이기 때문이다. 두 경로가 서로 다른 프레임을
    # 기준 삼으면 같은 웨이퍼의 M1 수치와 M2 수치가 조용히 갈린다.
    meta, _basis = bonding_plan.canonical_basis(db, source_cfg, origin_maps, meta_cache)
    if meta is None:
        # 확정 없음 — 종전 퇴화형 그대로: 선언 순서 첫 원천이 기준을 정의한다.
        for table, map_id in origin_maps:
            meta = bonding_plan.load_map_meta(db, source_cfg, table, map_id, meta_cache)
            break
    if cache is not None:
        cache[(origin_lot, origin_slot)] = meta
    return meta


def _canonical_fail_set(db, source_cfg, fail_cfg, cols, origin_lot, origin_slot,
                        grid_cache: dict = None, meta_cache: dict = None):
    """출신(core) 1장의 fail 좌표를 canonical 프레임 set으로 반환.

    반환: (set[(x,y)], align_marker|None, truncated) — 변환 미해결이면
    (None, "align_unavailable", False).
    """
    import bonding_plan
    import map_overlay

    filters = _identity_filters(fail_cfg, cols, origin_lot, origin_slot)
    fail_values = fail_cfg.get("fail_values")
    if fail_values and "val" in cols:
        filters.append(cols["val"].in_([str(v) for v in fail_values]))

    # [7b] identity canonicalized per the fail table's declared types
    map_id = _origin_map_id(source_cfg, origin_lot, origin_slot, binding=fail_cfg)
    src_meta = bonding_plan.load_map_meta(db, source_cfg, fail_cfg["table"], map_id, meta_cache)
    dst_meta = _canonical_origin_meta(db, source_cfg, origin_lot, origin_slot,
                                      grid_cache, meta_cache)
    if src_meta is not None and dst_meta is None:
        # [비대칭 지식] 이 맵의 프레임은 아는데 기준 프레임을 모른다. 둘 다 모르면
        # identity가 성립하지만(등록 누락), 한쪽만 알 때 identity로 가정할 근거는 없다.
        logger.warning("[TransferPlan] canonical origin frame unregistered while '%s' declares "
                       "its own (%s) — refusing to assume identity",
                       fail_cfg.get("table"), map_id)
        return None, "align_unavailable", False
    try:
        transform, align, _origin, _note = map_overlay.resolve_map_transform(src_meta, dst_meta)
    except ValueError as ve:
        # 치수 불일치·phys 미등록 등 — 조용히 어긋난 좌표를 쓰지 않고 명시 실패로 강등한다.
        logger.warning("[TransferPlan] frame transform unavailable (%s/%s): %s",
                       fail_cfg.get("table"), map_id, ve)
        return None, "align_unavailable", False
    marker = map_overlay.align_status_label(align)

    pts, truncated = _fetch_pairs(db, cols, filters, cap=MAX_FAIL_POINTS,
                                  tag=f"fail:{fail_cfg.get('table')}")
    if transform:
        return {transform(x, y) for (x, y) in pts}, marker, truncated
    return set(pts), marker, truncated


def _collect_history(db, source_cfg, lot, slot):
    """process_history 역할 — M1 규율 그대로: 최근 50건 시간 오름차순 + result fail 경고."""
    import bonding_plan

    src = (source_cfg or {}).get("process_history")
    history, warnings_out = [], []
    if not _valid_binding(src):
        return "missing", history, warnings_out
    model, cols = _resolve(src, required=("lot", "slot"))
    if model is None:
        return "missing", history, warnings_out
    try:
        q = db.query(model).filter(*_identity_filters(src, cols, lot, slot))
        if "time" in cols:
            q = q.order_by(cols["time"].desc())
        rows = q.limit(bonding_plan.HISTORY_LIMIT).all()
        rows.reverse()

        col_names = src["columns"]
        fail_values = set((source_cfg.get("warnings") or {}).get("result_fail_values") or [])
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
                    knobs = knobs_raw  # 파싱 실패 → raw 폴백 (에러 아님 — M1 규율)

            entry = {"step": _get("step"), "eqp": _get("eqp"), "result": _get("result"),
                     "time": _get("time"), "recipe": _get("recipe"), "knobs": knobs}
            history.append(entry)
            if fail_values and entry["result"] in fail_values:
                warnings_out.append({
                    "type": "result_fail",
                    "detail": f"{entry['step']} {entry['result']} @{entry['eqp']} {entry['time']}",
                })
        return _demote_unresolved("connected", cols), history, warnings_out
    except Exception as e:
        logger.warning("[TransferPlan] role 'process_history' query failed: %s", e)
        return "missing", [], []


def _summarize_inline(db, stage_name: str, stage_cfg: dict, lot: str, slot: str,
                      region: set = None, want_bins: bool = False,
                      bin_request=None, bin_refused=None) -> dict:
    """inline source 블록의 일반 가용 집계 (tape-kind의 정본 경로).

    의미론(공통 계약):
    - total: total_chips 행 수(칩 단위 원천 가정 — dt_log는 칩당 1행)
    - transferred: transfer_log distinct (x,y) 칩 수
    - fail_breakdown[name]: fail 원천별 칩 수. frame='origin'이면 origin_log 조인 투영
      (출신 코어 fail → 타깃 좌표), frame='self'면 자기 identity 직접 카운트.
    - remaining = total − |fail 합집합 ∪ transferred| (origin_log가 있을 때. origin_log
      없으면 M1식 감산 폴백: total − Σfail − transferred).
      **정확성 단서**: 이 값은 ①모든 역할이 connected이고 ②하드캡(MAX_*) 미도달이며
      ③total_chips 원천이 칩당 1행 유일할 때만 정확하다. ①②가 깨지면 감산항이 과소해져
      remaining이 **과대**가 되므로 `remaining_reliable: false` + `remaining=None`으로
      내리고 경고를 warnings에 싣는다(QA F1·F2). ③(중복 행)은 현재 미표면화 — 알려진 한계.
    - by_core: 출신별 분해(집계만). 1순위는 origin_log(칩 단위 조인 — fail 포함 정확),
      origin_log 미해석 시 `origin_area_map`(dt_map 영역 귀속: val=코어 식별) 강등 경로로
      total/used만 제공하고 fail은 null(투영 불가 — 좌표 대응이 없으므로 조용히 0으로
      위장하지 않는다).
      **두 경로의 키 집합은 동일**하다: {core_id, core_lot, core_slot, total, fail,
      used, remaining} — 클라의 경로별 분기를 없애기 위함. 경로 구분은 응답 top-level
      `by_core_origin`("log" | "area_map") 마커로 한다. area_map 경로의 core_id는 영역
      맵의 원시 값(불투명 — config가 정한다)이므로 core_lot/core_slot은 null이고, 두
      경로 간 core_id 문자열이 일치할 것을 가정해선 안 된다(응답 내 그룹 키로만 사용).
    """
    source_cfg = stage_cfg.get("source") or {}
    statuses = {}
    warnings_out = []

    truncations = []   # [QA F2] 하드캡 도달 기록 — 응답에 표기하고 신뢰도를 낮춘다
    # [relaxation] 감산 종류 중 **선언 자체가 없어** 집계에 들어가지 않은 것들.
    # 응답 필드 `inactive_subtractions`로 표면화한다 — 총량이 순량처럼 조용히
    # 표시되는 것이 이 필드가 막는 실패다(강등 경고와는 다른 축: 강등 아님).
    inactive_subtractions = []

    # ---- total_chips ----
    total = 0
    src = source_cfg.get("total_chips")
    model, cols = _resolve(src, required=("lot", "slot"))
    if model is None:
        statuses["total_chips"] = "missing"
    else:
        try:
            total = int(db.query(model)
                        .filter(*_identity_filters(src, cols, lot, slot)).count())
            statuses["total_chips"] = _demote_unresolved("connected", cols)
        except Exception as e:
            logger.warning("[TransferPlan] role 'total_chips' query failed: %s", e)
            statuses["total_chips"] = "missing"

    # ---- transfer_log (기전사 — distinct 칩) ----
    used_set = set()
    used_count = 0
    used_count_only = False
    used_untracked = False
    used_not_declared = False
    src = source_cfg.get("transfer_log")
    if not role_is_declared(source_cfg, "transfer_log"):
        # [relaxation 2026-08-04] No transfer_log key at all: the site keeps no
        # consumption log (bonded material is never reused — real-fab feedback).
        # NOT a degradation and NOT the 7c "none" declaration either: remaining
        # is served as a real number computed WITHOUT this subtraction, and the
        # skipped kind is named in `inactive_subtractions`. transferred stays
        # null (unknown — a 0 would read "none used"). A present-but-broken
        # binding (null / typo / missing table) keeps the old `missing` demotion.
        used_not_declared = True
        statuses["transfer_log"] = STATUS_NOT_DECLARED
        inactive_subtractions.append("transfer_log")
    elif transfer_log_is_declared_none(src):
        # [7c] Consumption is DECLARED unrecorded ("none" — the exact string; JSON
        # null stays "missing" because null cannot be told apart from an accidental
        # absent key). Not a degradation: the binding did not break, the site
        # stated a fact. used_set stays empty and used_count 0, so the computed
        # remaining below is a genuine UPPER BOUND (dropping a subtraction term can
        # only raise the value) — served as remaining_upper_bound, never as an
        # exact remaining. transferred is unknown, not 0.
        used_untracked = True
        statuses["transfer_log"] = STATUS_TRANSFER_UNTRACKED
    else:
        model, cols = _resolve(src, required=("lot", "slot"))
        if model is None:
            statuses["transfer_log"] = "missing"
        else:
            try:
                filters = _identity_filters(src, cols, lot, slot)
                if "x" in cols and "y" in cols:
                    pts, trunc = _fetch_pairs(db, cols, filters, distinct=True,
                                              cap=MAX_ORIGIN_POINTS, tag="transfer_log")
                    used_set = set(pts)
                    used_count = len(used_set)
                    if trunc:
                        truncations.append({"role": "transfer_log", "cap": MAX_ORIGIN_POINTS})
                    status = "connected"
                else:
                    # [FIX 2026-07-28] Bound without usable x/y: the count is real but
                    # chip identity is unknown, so the set-based remaining below cannot
                    # subtract these chips (used_set stays empty while `transferred`
                    # displays the count — the phantom-remaining bug). Demote so the
                    # degradation engine nulls remaining and serves the upper bound.
                    used_count = int(db.query(model).filter(*filters).count())
                    used_count_only = True
                    status = "connected(count_only)"
                statuses["transfer_log"] = _demote_unresolved(status, cols)
            except Exception as e:
                logger.warning("[TransferPlan] role 'transfer_log' query failed: %s", e)
                statuses["transfer_log"] = "missing"

    # ---- origin_log (칩 단위 출신 귀속 — by_core·fail 투영의 다리) ----
    origin_rows = None   # [(tx, ty, origin_lot, origin_slot, ox, oy)]
    src = source_cfg.get("origin_log")
    if not role_is_declared(source_cfg, "origin_log"):
        # [relaxation] 미선언 = 출신 귀속 로그가 없는 사이트. 강등이 아니라 부재다 —
        # remaining은 감산식 폴백(total − Σfail − used)으로 **숫자로** 나간다.
        # (frame='origin'으로 **선언된** fail 원천이 있으면 그쪽이 종전대로
        # unavailable(origin_missing) 강등을 받는다 — 선언 간 모순은 계속 표면화.)
        statuses["origin_log"] = STATUS_NOT_DECLARED
        inactive_subtractions.append("origin_log")
        model = None
    else:
        model, cols = _resolve(src, required=ORIGIN_LOG_ROLES)
        if model is None:
            statuses["origin_log"] = "missing"
    if model is not None:
        try:
            q = db.query(cols["x"], cols["y"], cols["origin_lot"], cols["origin_slot"],
                         cols["origin_x"], cols["origin_y"]) \
                 .filter(*_identity_filters(src, cols, lot, slot))
            raw = q.limit(MAX_ORIGIN_POINTS).all()
            if len(raw) >= MAX_ORIGIN_POINTS:
                logger.warning("[TransferPlan] origin_log fetch hit hard cap (%d)", MAX_ORIGIN_POINTS)
                truncations.append({"role": "origin_log", "cap": MAX_ORIGIN_POINTS})
            origin_rows = [
                (int(tx), int(ty), ol, os_, int(ox), int(oy))
                for (tx, ty, ol, os_, ox, oy) in raw
                if tx is not None and ty is not None and ox is not None and oy is not None
            ]
            statuses["origin_log"] = _demote_unresolved("connected", cols)
        except Exception as e:
            logger.warning("[TransferPlan] role 'origin_log' query failed: %s", e)
            origin_rows = None
            statuses["origin_log"] = "missing"

    # ---- fail_sources ----
    fail_breakdown = {}
    fail_union = set()               # 타깃 좌표 기준 fail 칩 합집합
    # [FIX 2026-07-28] Sibling of used_count_only: a self-frame fail source bound
    # without usable x/y on the origin_rows path contributes a count but no set —
    # flag it so by_core stops deriving per-core fail/remaining from a union that
    # is missing those chips.
    fail_count_only = False
    fail_sources = source_cfg.get("fail_sources") or {}
    if not role_is_declared(source_cfg, "fail_sources"):
        # [relaxation] fail 원천이 하나도 선언되지 않았다. 종전에도 감산 없이 조용히
        # 지나갔지만, 이제 그 침묵을 이름으로 바꾼다 — 총량이 순량처럼 보이면 안 된다.
        #
        # [QA B3 fix 2026-08-04] Declaredness goes through the SHARED predicate,
        # never a second spelling. The hand-rolled `isinstance(...) and truthy`
        # test that stood here classified a PRESENT-but-malformed value (null,
        # "None", a wrong-typed value) as absent, collapsing state 2 into state 1:
        # a misconfigured site silently got the relaxed treatment and the marker
        # named a role the operator HAD declared. Present + garbage keeps its
        # pre-relaxation handling — no source resolves, so no fail term enters the
        # arithmetic, and nothing claims the site failed to declare one.
        inactive_subtractions.append("fail_sources")
    # [확장성] 코어별 칩 인덱스를 1회 구축해 투영을 선형화한다
    # (코어마다 origin_rows 전체를 훑으면 O(코어수 × 칩수) — 테이프당 수백 코어에서 폭발)
    rows_by_core = {}
    involved_cores = []
    # [QA F6] canonical(dst) 메타는 코어당 1회만 조회한다 (F7 왕복 수도 일부 완화).
    # meta_cache는 (table, map_id) 단위 — 코어 × fail 원천 수만큼의 재조회를 막는다.
    canonical_grid_cache = {}
    meta_cache = {}
    if origin_rows is not None:
        for (tx, ty, ol, os_, ox, oy) in origin_rows:
            bucket = rows_by_core.get((ol, os_))
            if bucket is None:
                bucket = rows_by_core[(ol, os_)] = []
                involved_cores.append((ol, os_))
            bucket.append((tx, ty, ox, oy))

    for name, fs in (fail_sources.items() if isinstance(fail_sources, dict) else []):
        name = str(name)
        frame = fs.get("frame") or ("origin" if origin_rows is not None else "self")
        model, cols = _resolve(fs, required=("lot", "slot"))
        if model is None:
            statuses[name] = "missing"
            fail_breakdown[name] = 0
            continue

        if frame == "self":
            # 자기 identity 직접 카운트 (M1 맵 모드와 동일 — align은 카운트 불변)
            try:
                filters = _identity_filters(fs, cols, lot, slot)
                fail_values = fs.get("fail_values")
                # [N14 2026-08-04] Counting without the fail filter would count
                # EVERY row as fail — overstating the subtraction (breaks the
                # upper-bound invariant). THE shared predicate rules on both
                # shapes of "no usable `val`": the typo (2026-07-28) and the
                # DELETION the derivation round started advising.
                refused, refusal_status = _fail_filter_status(fs, cols)
                if refused:
                    statuses[name] = _demote_unresolved(refusal_status, cols)
                    fail_breakdown[name] = 0
                    continue
                if fail_values:
                    filters.append(cols["val"].in_([str(v) for v in fail_values]))
                cnt = int(db.query(model).filter(*filters).count())
                fail_breakdown[name] = cnt
                status = "connected"
                if "x" in cols and "y" in cols:
                    pts, trunc = _fetch_pairs(db, cols, filters, cap=MAX_FAIL_POINTS,
                                              tag=f"fail:{name}")
                    fail_union.update(pts)
                    if trunc:
                        truncations.append({"role": name, "cap": MAX_FAIL_POINTS})
                elif origin_rows is not None:
                    # [FIX 2026-07-28] Sibling of the count_only transfer_log fix:
                    # on the origin_rows path remaining is SET-based
                    # (total − |fail_union ∪ used_set|), so a self-frame fail
                    # source without usable x/y feeds fail_breakdown but nothing
                    # into fail_union — the subtraction silently misses these
                    # chips and remaining over-reports (same phantom class).
                    # Demote so the degradation engine nulls remaining.
                    # Upper-bound invariant: the missing points can only SHRINK
                    # the union, and dropping a subtraction term only raises the
                    # computed value, so total − |union| ≥ true remaining — the
                    # served upper bound stays genuine. We deliberately do NOT
                    # subtract cnt instead: chip identity is unknown, so it may
                    # overlap used_set/other fail sources and over-subtract,
                    # which would break the bound downward. The count itself is
                    # real and stays in fail_breakdown (mirror of `transferred`
                    # staying under a count_only transfer_log).
                    fail_count_only = True
                    status = "connected(count_only)"
                # else: fallback path (origin_rows is None) — remaining is the
                # count-based total − Σfail − used, so cnt subtracts correctly
                # without coordinates: stays plain connected, no demotion.
                statuses[name] = _demote_unresolved(status, cols)
            except Exception as e:
                logger.warning("[TransferPlan] fail source '%s' query failed: %s", name, e)
                statuses[name] = "missing"
                fail_breakdown[name] = 0
            continue

        # frame == "origin": 출신 프레임 fail의 투영 — origin_log 필수
        if origin_rows is None:
            statuses[name] = "unavailable(origin_missing)"
            fail_breakdown[name] = 0
            continue
        if "x" not in cols or "y" not in cols:
            # [FIX 2026-07-28] Declared-but-typo x/y gets the honest marker instead
            # of a generic "missing" (both are degraded — the marker names the typo).
            unres_xy = {"x", "y"} & set(_unresolved_of(cols))
            statuses[name] = (_demote_unresolved("connected", cols)
                              if unres_xy else "missing")
            fail_breakdown[name] = 0
            continue
        # Projecting without the fail filter would mark every origin chip as
        # fail. Same predicate as the self-frame branch above — one ruling, both
        # frames (a fix on one frame only is how this class comes back).
        refused, refusal_status = _fail_filter_status(fs, cols)
        if refused:
            statuses[name] = _demote_unresolved(refusal_status, cols)
            fail_breakdown[name] = 0
            continue
        try:
            projected = set()
            status = "connected"
            marker = None
            for (ol, os_) in involved_cores:
                fail_set, mk, trunc = _canonical_fail_set(
                    db, source_cfg, fs, cols, ol, os_,
                    grid_cache=canonical_grid_cache, meta_cache=meta_cache)
                if fail_set is None:
                    # [align 규율] 규격 불명 시 raw 좌표로 조용히 계산하지 않는다
                    status = "connected(align_unavailable)"
                    projected = set()
                    break
                if trunc:
                    truncations.append({"role": name, "cap": MAX_FAIL_POINTS, "core": f"{ol}|{os_}"})
                if mk:
                    marker = mk
                for (tx, ty, ox, oy) in rows_by_core.get((ol, os_), ()):
                    if (ox, oy) in fail_set:
                        projected.add((tx, ty))
            if status == "connected" and marker:
                status = f"connected({marker})"
            statuses[name] = _demote_unresolved(status, cols)
            if status == "connected(align_unavailable)":
                fail_breakdown[name] = 0
            else:
                fail_breakdown[name] = len(projected)
                fail_union.update(projected)
        except Exception as e:
            logger.warning("[TransferPlan] fail source '%s' projection failed: %s", name, e)
            statuses[name] = "missing"
            fail_breakdown[name] = 0

    # ---- remaining ----
    if origin_rows is not None:
        # 칩 단위 정확 집계: fail·기전사 중복 이중 감산 없음
        blocked = fail_union | used_set
        remaining = total - len(blocked)
    else:
        remaining = total - sum(fail_breakdown.values()) - used_count

    # ---- by_core (집계만, 좌표 목록 금지) ----
    # [계약] 두 경로(log/area_map)의 **키 집합은 동일**하다:
    #   {core_id, core_lot, core_slot, total, fail, used, remaining}
    # 클라가 경로별로 분기하지 않게 하기 위함이며, 경로 구분은 by_core_origin 마커로 한다.
    by_core = None
    by_core_origin = None
    by_core_truncated = False
    if origin_rows is not None:
        agg = {}
        for (tx, ty, ol, os_, _ox, _oy) in origin_rows:
            key = (ol, os_)
            a = agg.get(key)
            if a is None:
                a = agg[key] = {"total": 0, "fail": 0, "used": 0, "blocked": 0}
            a["total"] += 1
            is_fail = (tx, ty) in fail_union
            is_used = (tx, ty) in used_set
            if is_fail:
                a["fail"] += 1
            if is_used:
                a["used"] += 1
            if is_fail or is_used:
                a["blocked"] += 1
        by_core = []
        for (ol, os_) in sorted(agg.keys(), key=lambda k: (str(k[0]), str(k[1]))):
            a = agg[(ol, os_)]
            by_core.append({
                "core_id": f"{ol}{CORE_ID_SEP}{os_}",
                "core_lot": ol, "core_slot": os_,
                # [FIX 2026-07-28] count_only transfer_log: chip-level used is
                # unknowable (used_set is empty), so serve null like the fail:null
                # convention of the area_map path — never a fake 0. The remaining
                # derived from it is nulled too (blocked misses the used term, so
                # a bare number here would be the same phantom at per-core level).
                # Sibling: a count_only self-frame fail source leaves its chips
                # out of fail_union, so per-core fail would under-report and the
                # remaining derived from `blocked` would over-report — null both;
                # `used` stays real (it comes from used_set, unaffected).
                # [7c] untracked transfer_log is the declared sibling of
                # count_only: chip-level used is unknowable either way.
                # [relaxation] not_declared nulls `used` too (no log exists), but
                # remaining STAYS a number — it is the availability computed
                # without that subtraction, same semantics as the headline chips.
                "total": a["total"],
                "fail": None if fail_count_only else a["fail"],
                "used": (None if (used_count_only or used_untracked
                                  or used_not_declared) else a["used"]),
                "remaining": (None if (used_count_only or used_untracked
                                       or fail_count_only)
                              else a["total"] - a["blocked"]),
            })
        if len(by_core) > MAX_BY_CORE:
            logger.warning("[TransferPlan] by_core truncated to %d entries", MAX_BY_CORE)
            by_core = by_core[:MAX_BY_CORE]
            by_core_truncated = True
        by_core_origin = "log"
    else:
        # [강등 경로] origin_log 미해석 — 영역 귀속 맵(dt_map: val=코어 식별)으로 분해만 제공.
        # 좌표 대응이 없어 fail 투영은 불가 → fail은 null(0으로 위장 금지).
        area_src = source_cfg.get("origin_area_map")
        model, cols = _resolve(area_src, required=ORIGIN_AREA_MAP_ROLES)
        if model is None:
            if _valid_binding(area_src):
                statuses["origin_area_map"] = "missing"
        else:
            try:
                raw = (db.query(cols["x"], cols["y"], cols["val"])
                       .filter(*_identity_filters(area_src, cols, lot, slot))
                       .limit(MAX_ORIGIN_POINTS).all())
                if len(raw) >= MAX_ORIGIN_POINTS:
                    logger.warning("[TransferPlan] origin_area_map fetch hit hard cap (%d)",
                                   MAX_ORIGIN_POINTS)
                    truncations.append({"role": "origin_area_map", "cap": MAX_ORIGIN_POINTS})
                agg = {}
                for (ax, ay, val) in raw:
                    if ax is None or ay is None or val is None:
                        continue
                    a = agg.get(str(val))
                    if a is None:
                        a = agg[str(val)] = {"total": 0, "used": 0}
                    a["total"] += 1
                    if (int(ax), int(ay)) in used_set:
                        a["used"] += 1
                by_core = []
                for val in sorted(agg.keys()):
                    a = agg[val]
                    by_core.append({
                        # core_id는 영역 맵의 원시 값(config가 정하는 불투명 식별자) —
                        # lot/slot으로 분해할 근거가 없으므로 null(추측 파싱 금지).
                        # [FIX 2026-07-28] count_only transfer_log: used_set is
                        # empty so per-core used (and the remaining derived from
                        # it) is unknowable — null, never a fake 0/total.
                        # [7c] untracked: same nulls as count_only — used_set is empty.
                        # [relaxation] not_declared nulls `used` only; remaining
                        # stays the no-subtraction number (headline semantics).
                        "core_id": val, "core_lot": None, "core_slot": None,
                        "total": a["total"], "fail": None,
                        "used": (None if (used_count_only or used_untracked
                                          or used_not_declared) else a["used"]),
                        "remaining": (None if (used_count_only or used_untracked)
                                      else a["total"] - a["used"]),
                    })
                if len(by_core) > MAX_BY_CORE:
                    by_core = by_core[:MAX_BY_CORE]
                    by_core_truncated = True
                by_core_origin = "area_map"
                statuses["origin_area_map"] = _demote_unresolved("connected(area_only)", cols)
            except Exception as e:
                logger.warning("[TransferPlan] origin_area_map query failed: %s", e)
                statuses["origin_area_map"] = "missing"

    # ---- history ----
    if role_is_declared(source_cfg, "process_history"):
        hist_status, history, hist_warnings = _collect_history(db, source_cfg, lot, slot)
    else:
        # [relaxation] 이력 테이블 미선언 — 감산항은 아니므로 inactive 목록에는 안 싣고,
        # 강등 경고 없이 not_declared로만 표기한다(부재는 결함이 아니다).
        hist_status, history, hist_warnings = STATUS_NOT_DECLARED, [], []
    statuses["process_history"] = hist_status
    warnings_out.extend(hist_warnings)

    # [QA F1] 강등 표면화 — sources 문자열만으로는 소비자가 정상과 구별하지 못한다.
    fail_role_names = set(str(k) for k in fail_sources) if isinstance(fail_sources, dict) else set()
    deg_warnings, remaining_reliable, total_reliable = assess_degradation(
        statuses, fail_roles=fail_role_names)

    # [QA F2] 하드캡 절단도 감산항을 과소하게 만든다 — 강등과 동일 규율로 처리한다.
    # (total은 count()라 절단되지 않으므로 분자·분모의 모집단이 어긋난다 → remaining 과대)
    for t in truncations:
        remaining_reliable = False
        deg_warnings.append({
            "type": WARN_RESULT_TRUNCATED,
            "role": t["role"], "cap": t["cap"],
            "effect": EFFECT_REMAINING_OVERSTATED,
            "detail": (f"역할 '{t['role']}' 조회가 하드캡({t['cap']})에 도달해 절단됨"
                       + (f" [코어 {t['core']}]" if t.get("core") else "")
                       + " — 집계가 과소해져 remaining이 과대일 수 있음"),
        })
    if by_core_truncated:
        deg_warnings.append({
            "type": WARN_RESULT_TRUNCATED,
            "role": "by_core", "cap": MAX_BY_CORE,
            "effect": EFFECT_BY_CORE_DEGRADED,
            "detail": f"by_core 분해가 상한({MAX_BY_CORE})으로 절단됨 — "
                      f"sum(by_core.total)이 chips.total과 일치하지 않는다",
        })

    # [7c] Declared-untracked consumption — applied AFTER the degradation/cap
    # machinery so `bins_base_reliable` captures every OTHER cause: the bins
    # block serves per-bin upper bounds only when untracked is the sole reason.
    bins_base_reliable = remaining_reliable
    if used_untracked:
        remaining_reliable = False   # build_chips_block nulls remaining + serves the bound
        deg_warnings.append({
            "type": WARN_TRANSFER_UNTRACKED,
            "role": "transfer_log",
            "status": STATUS_TRANSFER_UNTRACKED,
            "effect": EFFECT_REMAINING_UPPER_BOUND,
            "detail": ("전사(소모) 기록이 '없음'으로 선언됨(transfer_log: \"none\") — "
                       "잔여는 확정치가 아니라 상한이다. remaining_upper_bound를 "
                       "'≤N'으로 표시하라(미상이 아니다)"),
        })

    chips_block, inv_warnings = build_chips_block(
        total=total,
        fail_breakdown=fail_breakdown,
        # [7c] transferred is unknown under untracked — 0 would read as "none used"
        # [relaxation] same under a never-declared transfer_log (no log exists)
        transferred=None if (used_untracked or used_not_declared) else used_count,
        remaining=remaining,
        remaining_reliable=remaining_reliable,
        total_reliable=total_reliable,
    )
    if inv_warnings:
        remaining_reliable = False   # region_chips.reliable에도 전파
        bins_base_reliable = False   # 모집단 불일치는 untracked와 무관한 실 강등이다

    result = {
        "identity": {"lot": lot, "slot": slot},
        "stage": stage_name,
        "source_kind": stage_cfg.get("source_kind"),
        "sources": statuses,
        "chips": chips_block,
        "history": history,
        "warnings": deg_warnings + inv_warnings + warnings_out,
    }
    if by_core is not None:
        result["by_core"] = by_core
        # 경로 마커 — 클라가 "코어별 불량 미상(영역 귀속 기준)" 안내를 띄울 근거
        result["by_core_origin"] = by_core_origin
        result["by_core_truncated"] = by_core_truncated
    if truncations:
        result["truncated"] = truncations
    if inactive_subtractions:
        # [relaxation — honest degradation] 선언 자체가 없어 집계에서 빠진 감산
        # 종류의 목록. 클라는 당장 무시해도 되지만, 이 필드가 없으면 "총량이 순량
        # 행세"가 침묵이 된다. 전 역할 선언 config의 페이로드는 변하지 않는다
        # (비어 있으면 필드 자체가 없다).
        result["inactive_subtractions"] = inactive_subtractions

    # 총칩 **좌표** 집합 — 영역과 BIN이 같은 것을 쓴다(둘 다 좌표 부분집합 교차).
    total_pts = None
    if region is not None or want_bins:
        if origin_rows is not None:
            total_pts = {(tx, ty) for (tx, ty, _l, _s, _ox, _oy) in origin_rows}
        else:
            src = source_cfg.get("total_chips")
            model, cols = _resolve(src, required=("lot", "slot"))
            if model is not None and "x" in cols and "y" in cols:
                pts, _tr = _fetch_pairs(db, cols, _identity_filters(src, cols, lot, slot),
                                        cap=MAX_REGION_CELLS, tag="region:total")
                total_pts = set(pts)

    # ---- [②] 영역 내 가용 (계획이 이 소스에서 쓰기로 페인팅한 셀 집합으로 스코프) ----
    if region is not None:
        # fail은 원천별 집합을 따로 갖고 있지 않으므로 합집합만 신뢰 가능 —
        # breakdown은 원천별 재계산 없이 합집합 기준 단일 항목으로 제공한다.
        result["region_chips"] = _region_block(
            total_pts, {"all_fail": fail_union}, used_set, region)
        result["region_chips"]["reliable"] = remaining_reliable
        if used_untracked or used_not_declared:
            # [7c] used_set is empty by declaration — the region transferred would
            # be a fake 0 (unknown, not zero). [relaxation] same for a
            # never-declared transfer_log.
            result["region_chips"]["transferred"] = None

    # ---- [BIN 축] `(자재, BIN)` 단위 가용 ----
    if want_bins:
        bins = _bins_block(db, stage_cfg, lot, slot, total_pts, fail_union, used_set,
                           bin_request, bin_refused, bins_base_reliable,
                           chips_block.get("total"), untracked=used_untracked,
                           transfer_inactive=used_not_declared)
        result["bins"] = bins
        result["warnings"] = result["warnings"] + _bin_warnings(bins)
    return result


def _bin_warnings(bins: dict) -> list:
    """BIN 블록에서 파생되는 최상위 경고. 블록 안의 이유와 **중복이 아니라 요약**이다 —
    기존 소비자는 `warnings`만 보고 강등을 판단하므로 거기에도 나타나야 한다."""
    out = []
    if not isinstance(bins, dict):
        return out
    if bins.get("axis") != "connected":
        out.append({
            "type": WARN_BIN_AXIS_UNAVAILABLE,
            "effect": EFFECT_BIN_AXIS_UNAVAILABLE,
            "detail": bins.get("detail") or "BIN별 가용을 계산할 수 없습니다",
        })
        return out
    entries = bins.get("entries") or []
    binned_total = sum(int(e.get("total") or 0) for e in entries if e.get("reliable"))
    ref = bins.get("population_ref")
    # 요청 BIN만 물었으면 부분합이 당연히 작다 — 그건 불일치가 아니다.
    if (bins.get("requested") is None and isinstance(ref, int)
            and not bins.get("truncated") and not bins.get("cells_truncated")
            and all(e.get("reliable") for e in entries) and binned_total != ref):
        out.append({
            "type": WARN_BIN_POPULATION_MISMATCH,
            "effect": EFFECT_POPULATION_MISMATCH,
            "detail": (f"BIN별 총계의 합({binned_total})이 총칩({ref})과 다릅니다 — "
                       f"맵 셀과 칩 원천의 모집단이 어긋났습니다"
                       f"(BIN 없는 셀 {bins.get('unbinned_cells')}칸)"),
        })
    return out


def get_stage_source_summary(db, cfg: dict, stage_name: str, lot: str, slot: str,
                             bp_config: dict = None,
                             ref_table: str = None, map_key: str = None,
                             bins: str = None) -> dict:
    """단계별 소스 가용 집계 — 계약 공통 형태를 생성한다.

    stage 미선언 시 KeyError (라우트가 404로 변환).
    bp_config: source_config_ref 스테이지용 M1 config 스냅샷(미지정 시 여기서 1회 로드 —
    validate처럼 반복 호출하는 상위는 스냅샷을 주입해 작업 경계 1회 로드 규율을 지킨다).
    ref_table/map_key: 계획 맵 정체성(v2 — 구 plan_id 대체). 소스 영역 스코프에만 쓰인다.
    bins: `"1,2"` 형태의 BIN 요청(선택). 지정하면 요청한 BIN이 **전부** 답을 받는다 —
      맵에 없으면 `bin_absent`이며 **절대 `0`이 아니다**(DOE_BAND_MODEL §4-bis 🔴).
      생략하면 맵에 있는 BIN을 전부 나열한다. `bins`를 아예 주지 않으면 BIN 블록도 없다
      (기존 소비자의 응답이 커지지 않는다).
    """
    import bonding_plan

    stages = get_stages(cfg)
    stage_cfg = stages.get(stage_name)
    if not isinstance(stage_cfg, dict):
        raise KeyError(f"stage '{stage_name}' is not declared")

    want_bins = bins is not None
    bin_request, bin_refused = parse_bin_request(bins)

    # [②] 계획이 지정한 소스 사용 영역(자유 페인팅 셀 집합)을 스코프로 소비한다
    region = None
    if ref_table and map_key:
        region = load_source_region(db, cfg, ref_table, map_key, lot, slot)

    ref = stage_cfg.get("source_config_ref")
    if ref in M1_SOURCE_REFS:
        # [내부 통합] M1 core-summary = core-kind 소스 가용의 인스턴스 (외부 계약 불변)
        bp_cfg = bp_config if bp_config is not None else bonding_plan.load_bonding_plan_config()
        m1 = bonding_plan.get_core_summary(db, lot, slot, config=bp_cfg)
        out = _reshape_m1_summary(m1, stage_name, stage_cfg)
        if region is not None:
            out["region_chips"] = _core_region_counts(db, bp_cfg, lot, slot, region)
            out["region_chips"]["reliable"] = out["chips"].get("remaining_reliable", True)
        if want_bins:
            # M1 위임 경로는 좌표 집합을 만들지 않는다(집계만 넘겨받는다). 축을 흉내 내면
            # 감산항 없는 셀 수가 `가용`으로 둔갑하므로 **못 한다고 말한다.**
            out["bins"] = _bins_unavailable(
                "core-kind(M1 위임) 소스는 BIN별 감산을 계산할 좌표 집합을 갖지 않습니다.",
                BIN_SCOPE_SLOT, bin_request)
            out["warnings"] = (out.get("warnings") or []) + _bin_warnings(out["bins"])
        return out

    return _summarize_inline(db, stage_name, stage_cfg, lot, slot, region=region,
                             want_bins=want_bins, bin_request=bin_request,
                             bin_refused=bin_refused)


def get_lot_bin_summary(db, cfg: dict, stage_name: str, lot: str,
                        bins: str = None, bp_config: dict = None) -> dict:
    """`scope=lot` — 로트 **전체**(모든 슬롯)의 BIN별 가용.

    토큰 `MID1:2`는 "MID1 로트의 모든 슬롯, BIN 2"라는 정의된 뜻이다(§4-bis). 슬롯별
    집계를 합산하는 것 말고 더 싼 정직한 답은 없다 — fail 투영이 슬롯마다의 좌표 변환을
    거치므로 SQL로 밀어넣을 수 없다. 그래서 **팬아웃을 상한으로 묶고 절단을 표면화한다.**

    반환에는 **두 가지가 함께** 실린다:
    * `by_slot` — 슬롯 **하나당 한 행**. 이것이 사용자가 실제로 보는 전개 목록이며,
      `map_exists`가 "전산에는 있는데 맵이 없다"를 드러낸다(§로트 전개 진단).
    * `bins` — 슬롯을 가로질러 합산한 **풀 충분성** 수치.

    ⚠️ **`chips` 블록을 싣지 않는다.** 로트 전체의 `remaining` 하나를 만들어 내보내면
    아무도 요청하지 않은 숫자가 기존 필드 이름을 달고 화면에 흘러든다.

    ⚠️ **합산치는 배분이 아니라 충분성 판정이다.** 웨이퍼는 실제로 한 장씩 소진되고 그
    순서를 아무도 기록하지 않는다 — 그래서 이 수는 "이 풀 전체에 충분한가"(양수면 가능)만
    답하며, **"이 웨이퍼가 정확히 N장을 댄다"로 읽혀서는 안 된다.** `basis` 필드가 그것을
    응답 안에 못박는다.
    """
    stages = get_stages(cfg)
    stage_cfg = stages.get(stage_name)
    if not isinstance(stage_cfg, dict):
        raise KeyError(f"stage '{stage_name}' is not declared")

    bin_request, bin_refused = parse_bin_request(bins)
    base = {
        "identity": {"lot": lot, "slot": None},
        "stage": stage_name,
        "source_kind": stage_cfg.get("source_kind"),
        "scope": BIN_SCOPE_LOT,
    }

    slots, slots_truncated, slots_origin = _lot_slots(db, stage_cfg, lot)
    if slots is None:
        # 🔴 빈 목록이 **아니다**. 빈 목록은 "이 로트에 자재가 없다"로 읽히고, 그러면
        #    진단면이 조용히 "깨끗함"을 보고한다 — 정확히 이 기능이 잡으려는 실패다.
        #    두 원천이 **각각 왜** 거절됐는지 말한다. 하나로 뭉친 예전 문장은 자재 대장을
        #    안 쓰는 사이트(정상)와 `bin_map` 컬럼명 오타(결함)를 같은 글자로 보고했다.
        mem_why, mem_detail = _lot_membership_refusal(stage_cfg)
        bin_why, bin_detail = _bin_axis_refusal(stage_cfg)
        bins_block = _bins_unavailable(
            f"로트 전체 가용을 계산할 수 없습니다 ― 슬롯을 셀 원천이 둘 다 없습니다. "
            f"① {mem_detail} ② {bin_detail}",
            BIN_SCOPE_LOT, bin_request, reason=(bin_why or mem_why))
        return dict(base, slots=None, slots_status="unknown", slots_origin=None,
                    by_slot=None, bins=bins_block,
                    warnings=[{"type": WARN_LOT_MEMBERSHIP_UNKNOWN,
                               "effect": EFFECT_BIN_AXIS_UNAVAILABLE,
                               "detail": f"로트 '{lot}'의 구성을 알 수 없습니다 ― "
                                         f"{mem_detail}"}]
                             + _bin_warnings(bins_block))

    warnings_out = []
    if slots_origin == "map":
        # 강등 경로를 없애지 않고 **이름 붙여 내보낸다** — by_core_origin과 같은 규율.
        warnings_out.append({
            "type": WARN_LOT_MEMBERSHIP_DEGRADED,
            "effect": EFFECT_LOT_EXPANSION_PARTIAL,
            "detail": ("자재 대장(`lot_membership`)이 선언돼 있지 않아 **맵이 있는 슬롯만** "
                       "전개했습니다 — 전산에 있는데 맵이 없는 슬롯은 이 목록에 나타나지 "
                       "않으므로, 로트 구성 불일치를 이 화면으로 진단할 수 없습니다"),
        })
    base_out = dict(base, slots=slots, slots_status="connected", slots_origin=slots_origin)

    if slots_truncated:
        # 신뢰 가능한 슬롯만 더한 부분합을 로트 총계처럼 내보내지 않는다.
        bins_block = _bins_unavailable(
            f"로트 '{lot}'의 슬롯이 상한({MAX_LOT_SLOTS})을 넘어 전체를 합산할 수 없습니다.",
            BIN_SCOPE_LOT, bin_request)
        return dict(base_out, slots_truncated=True, by_slot=None, bins=bins_block,
                    warnings=warnings_out + _bin_warnings(bins_block))

    blocks, by_slot = [], []
    inactive_union = []   # [relaxation] 슬롯 요약이 밝힌 비활성 감산 종류의 합집합
    for s in slots:
        one = get_stage_source_summary(db, cfg, stage_name, lot, s,
                                       bp_config=bp_config, bins=bins or "")
        for r in (one.get("inactive_subtractions") or []):
            if r not in inactive_union:
                inactive_union.append(r)
        blk = one.get("bins")
        if not isinstance(blk, dict) or blk.get("axis") != "connected":
            # 한 슬롯이라도 축이 없으면 로트 합은 성립하지 않는다.
            bins_block = _bins_unavailable(
                f"슬롯 '{s}'의 BIN 축을 만들 수 없어 로트 전체를 합산할 수 없습니다: "
                f"{(blk or {}).get('detail')}", BIN_SCOPE_LOT, bin_request)
            return dict(base_out, by_slot=None, bins=bins_block,
                        warnings=warnings_out + _bin_warnings(bins_block))
        blocks.append(blk)
        by_slot.append({
            "slot": s,
            # 대장에는 있는데 맵이 한 칸도 없다 = 사람이 그리드에서 고쳐야 할 어긋남.
            # 0으로 접으면 "다 썼다"로 읽히므로 **존재 여부를 따로 말한다.**
            "map_exists": bool(blk.get("cells_total")),
            "chips_total": (one.get("chips") or {}).get("total"),
            "bins": blk.get("entries"),
        })

    missing_maps = [e["slot"] for e in by_slot if not e["map_exists"]]
    if missing_maps:
        warnings_out.append({
            "type": WARN_LOT_SLOT_MAP_MISSING,
            "effect": EFFECT_LOT_EXPANSION_PARTIAL,
            "slots": missing_maps,
            "detail": (f"로트 '{lot}'의 슬롯 {', '.join(map(str, missing_maps))}에 맵이 "
                       f"없습니다 — 전산 기록과 맵이 어긋났습니다(그리드에서 로트를 "
                       f"수정한 뒤 다시 불러오십시오)"),
        })

    bins_block = _merge_bins_over_slots(blocks, BIN_SCOPE_LOT, bin_request, bin_refused)
    out = dict(base_out, slots_truncated=False, by_slot=by_slot, bins=bins_block,
               warnings=warnings_out + _bin_warnings(bins_block))
    if inactive_union:
        # [relaxation] 로트 합산 수치도 같은 감산 부재 위에서 계산됐다 — 슬롯 응답과
        # 같은 이름으로 말한다(없으면 필드도 없다).
        out["inactive_subtractions"] = inactive_union
    return out


# ---------------------------------------------------------------------------
# 계획 검증 (validate)
# ---------------------------------------------------------------------------

def _plan_store_binding(cfg: dict, role: str, required: tuple):
    store = (cfg.get("plan_store") or {}).get(role)
    model, cols = _resolve(store, required=required)
    return store, model, cols


def _parse_bands(raw):
    """`bands` 컬럼 → `(구간 리스트, 읽었는가, 거부된 원소 수)`.

    읽기 실패(`False`)는 "이 값에 구간이 없다"와 **다르다**. 빈 컬럼은 아직 DOE를 정의하지
    않은 정상적인 legend 행이지만, 손상된 blob은 계획을 통째로 못 읽은 것이다. 둘을 합치면
    장애가 "설정 없음"으로 위장한다 — 이 모듈이 막으려는 바로 그 실패 형태다.

    [객체가 아닌 원소는 **거부**한다 — 총괄 결정 2026-07-27]
    버리되 **조용히 버리지 않는다**: 세어서 호출자에게 돌려주고, 호출자가 표면화한 뒤
    계획을 `unverified`로 내린다. 원소 하나 때문에 그 값의 계획 전체를 못 읽은 것으로
    만들지는 않지만(나머지 구간은 계속 읽는다), 배열 길이가 바뀌면 위치 기반 `seq` 폴백과
    뒤 구간의 `prevTo` 이웃이 함께 밀리므로 **파생 수치가 움직인다** — 그래서 침묵은 안 된다.
    (클라는 `typeof [] === 'object'`라 중첩 배열을 빈 구간으로 살려 둔다. 그리드로만 들어올
    수 있는 입력이라 일치시킬 대상이 없고, 서버는 거부하는 쪽이 옳다.)

    파싱 **전에** 크기를 본다: `json.loads`는 아래 어떤 캡보다도 먼저 실행되므로 여기서
    막지 않으면 20MB blob이 40만 원소로 펼쳐진 뒤에야 상한을 만난다.
    """
    if raw is None or raw == "":
        return [], True, 0
    parsed = raw
    if not isinstance(parsed, list):
        s = str(raw)
        if len(s) > MAX_BANDS_BLOB_BYTES:
            logger.warning("[TransferPlan] bands blob exceeds %d bytes — refused before parse",
                           MAX_BANDS_BLOB_BYTES)
            return [], False, 0
        try:
            parsed = json.loads(s)
        except Exception:
            return [], False, 0
    if not isinstance(parsed, list):
        return [], False, 0
    kept = [b for b in parsed if isinstance(b, dict)]
    return _assign_band_seqs(kept), True, len(parsed) - len(kept)


def _band_seq(raw):
    """선언된 `seq` → 양의 정수, 아니면 None(배열 위치 폴백).

    클라 `normalizeBands`의 `typeof === 'number' && Number.isInteger && > 0` 미러.

    ⚠️ **정수값 float(`2.0`)은 반드시 받아들여야 한다.** `JSON.parse`는 어떤 가드가 돌기도
    **전에** `2.0`을 `2`로 접어버리므로 클라는 그것을 거부할 방법이 물리적으로 없다 —
    타입 검사가 볼 때 이미 정수다. 즉 여기서는 **클라가 움직일 수 없는 쪽**이고, 맞추러
    가야 하는 것은 서버다(`to`의 강제변환 흉내를 거부한 것과는 반대 상황: 저쪽은 클라가
    고칠 수 있었고, 이쪽은 전송 형식 자체의 한계다).
    구 규칙(`isinstance(raw, int)`)은 파이썬 float를 그대로 떨어뜨려 위치 폴백을 썼고,
    같은 구간에 서버·클라가 서로 다른 이름을 붙였다.

    [2^53 위] 값은 그대로 받는다 — `seq`는 **이름일 뿐** 산술에 들어가지 않으므로 `to`처럼
    크기를 묶을 이유가 없다. 다만 double로 정확히 표현되지 않는 값(홀수 > 2^53, `1e300`)은
    `JSON.parse` 단계에서 이미 값이 달라져 양쪽 라벨이 갈린다 — 계약이 **의도적으로 고정하지
    않은 꼬리**이며, 묶으려면 양쪽 동시 변경이 필요하다(벡터 파일 주석 참조).
    """
    if isinstance(raw, bool):
        return None                       # bool은 int의 하위형 — 먼저 걸러야 한다
    if isinstance(raw, int):
        return raw if raw > 0 else None
    if isinstance(raw, float):
        if raw != raw or raw in (float("inf"), float("-inf")):
            return None
        if raw != int(raw):
            return None                   # 2.5 — 클라 Number.isInteger도 거부한다
        v = int(raw)
        return v if v > 0 else None
    return None                           # str·None·list·dict


def _band_materials(band):
    """구간의 자재 목록 → `(자재 문자열 리스트, 거부된 원소 리스트)`.

    문자열은 공백을 제거하고, 빈 값(`None`·`""`·공백뿐)은 **조용히 버린다** — 그건 "자재가
    없다"는 뜻이지 손상이 아니다. 중복은 첫 등장 순서로 접는다(`share`의 분모가 바뀌므로
    파생값에 영향이 있다).

    [문자열이 아닌 원소는 **거부**한다 — 총괄 결정 2026-07-27]
    숫자·bool·배열·객체는 문자열화하지 않는다. 패널은 텍스트 입력으로 문자열만 쓰므로
    이런 값은 제네릭 그리드로만 들어올 수 있고, 그리드 입력에 대한 옳은 답은 "클라와 같은
    방식으로 잘못 읽기"가 아니라 **"읽을 수 없다"**이다. 흉내 낼 대상이 애초에 없다 —
    클라가 그 값을 만든 적이 없기 때문이다. (실제로 양쪽 문자열화는 갈린다:
    `True`/`true`, `42.0`/`42`, `"{'a': 1}"`/`[object Object]`. 어느 쪽도 자재 ID가 아니다.)
    거부는 호출자가 `source_unresolved`로 표면화하고 계획을 `unverified`로 내린다.
    """
    raw = band.get("materials") if isinstance(band, dict) else None
    out, refused = [], []
    for m in (raw if isinstance(raw, list) else []):
        if m is None:
            continue                       # 자재 없음 — 손상이 아니다
        if not isinstance(m, str):
            refused.append(m)
            continue
        s = m.strip()
        if s and s not in out:
            out.append(s)
    return out, refused


def _assign_band_seqs(bands):
    """`seq`를 **계획 안에서 유일**하게 만든다 (클라 `normalizeBands`의 seq 규칙 미러).

    [B1] 구 모델에서 `band_seq`는 복합 business key의 일부라 중복이 구조적으로 불가능했다.
    M2.6에서 `seq`는 브라우저가 쓰는 자유 JSON 안의 필드가 되었고 `bands`는 평범한
    `character varying`이라 제네릭 그리드·`/tables/.../data/updates`로 무엇이든 들어올 수
    있다 — 특히 `map_doe` 9행을 손으로 옮기는 경로가 정확히 충돌을 만든다. 중복 `seq`는
    두 구간을 한 이름으로 뭉개므로 여기서 미리 푼다.
    ⚠️ 이것은 **표시 이름의 충돌**만 없앤다. 집계 판정이 이름의 유일성에 기대면 안 된다
    (아래 source_alloc은 이름이 아니라 **수요 건수**를 센다).
    """
    out = []
    for i, b in enumerate(bands):
        seq = _band_seq(b.get("seq"))
        out.append((b, seq if seq is not None else (i + 1)))
    seen = set()
    nxt = max([s for (_b, s) in out], default=0) + 1
    resolved = []
    for (b, seq) in out:
        if seq in seen:
            seq = nxt
            nxt += 1
        seen.add(seq)
        resolved.append(dict(b, seq=seq))
    return resolved


# `to` 판정 3상태. blank와 invalid는 **prevTo 걷기에서 똑같이 건너뛴다** — 그것이 구조적
# 수정이다(강제 변환 흉내로 갈라지는 경우를 통째로 없앤다). invalid는 건너뛰되 **보고한다**.
BAND_TO_OK = "ok"
BAND_TO_BLANK = "blank"
BAND_TO_INVALID = "invalid"
# STACK-only fourth state (U9): an EXPLICIT 0 declares a marker value (상태 표시 값).
# It never comes out of `_int_state` — layer bounds and BINs still refuse 0 — only
# `stack_state` promotes it. Mirror of client `stackState`'s 'marker'.
STACK_MARKER = "marker"

_INT_STR = re.compile(r"^[+-]?[0-9]+$")


def _int_state(raw):
    """스칼라 하나 → `(정수|None, 상태)`. **이 프로젝트의 유일한 정수 판정기.**

    층 경계(`to`)와 BIN이 **같은 함수**를 쓴다 — DOE_BAND_MODEL §4-bis가 요구하는 바로 그
    것이다("BIN은 층 경계와 같은 정수 판정기로 읽는다"). 숫자 파서가 둘이면 `'0x10'`이
    한쪽에서 16, 다른 쪽에서 0이 된다. 클라 쪽 대응은 `transfer_plan.js`의 `bandToState`
    하나이며 `doe_bands.js`가 그것을 import해서 BIN에 쓴다 — 여기가 그 거울이다.

    [계약 — 클라와 **공유하는 좁힌 스펙**이지 JS 강제변환의 이식이 아니다]
      blank   : None / "" / 공백뿐인 문자열 → 오류 아님, 층 수 0
      ok      : 유한한 JSON 숫자, 또는 공백 제거 후 10진 정수 문자열. |값| ≤ MAX_LAYER
      invalid : 그 외 전부 — True/[]/"0x10"/"1_0"/"H2"/NaN/Infinity/2^53 초과

    ⚠️ **클라의 `Number()`를 흉내 내지 않는다.** `Number("  ") === 0`, `Number([]) === 0`은
    JS 강제변환의 사고이며, 이식하면 버그가 스펙으로 승격된다. 그 값들이 0으로 읽히면
    `prevTo` 걷기가 **거기서 멈추고**, None으로 읽히면 **건너뛴다** — `[10, "  ", 20]`이
    한쪽에선 20층, 다른 쪽에선 10층이 된다(한 화면, 두 숫자). blank와 invalid를 걷기에서
    동일하게 취급하는 것이 그 분기 계열 전체를 없애는 방법이다.
    정본 벡터: `contracts/band_arithmetic/vectors.json` (양쪽이 같은 파일로 고정된다).
    """
    if raw is None:
        return None, BAND_TO_BLANK
    if isinstance(raw, bool):
        return None, BAND_TO_INVALID          # bool은 int의 하위형이라 먼저 걸러야 한다
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None, BAND_TO_BLANK
        if not _INT_STR.match(s):
            return None, BAND_TO_INVALID      # "7.9"·"0x10"·"1_0"·"H2" 전부 여기
        raw = int(s)
    if isinstance(raw, int):
        return (raw, BAND_TO_OK) if abs(raw) <= MAX_LAYER else (None, BAND_TO_INVALID)
    if isinstance(raw, float):
        if raw != raw or raw in (float("inf"), float("-inf")):
            return None, BAND_TO_INVALID
        if abs(raw) > MAX_LAYER:
            return None, BAND_TO_INVALID      # 1e300 등 — 301자리 정수를 required에 넣지 않는다
        return int(raw), BAND_TO_OK           # trunc toward zero
    return None, BAND_TO_INVALID              # list·dict 등


def _band_to(band):
    """구간의 끝 층 → `(값|None, 상태)`. 판정은 전부 `_int_state`가 한다.

    구간이 dict가 아니면 `to`를 꺼낼 수조차 없으므로 invalid다(blank가 아니다 — 손상이다).
    """
    if not isinstance(band, dict):
        return None, BAND_TO_INVALID
    return _int_state(band.get("to"))


def _bin_of(raw):
    """맵 셀의 값 → 정규화된 BIN(양의 정수) 또는 None(= 이 셀은 BIN을 지지 않는다).

    **정규화가 필수인 이유**: 맵의 값 컬럼은 문자열이라 같은 BIN이 `'1'`·`'01'`·`' 1 '`로
    저장될 수 있는데 토큰의 BIN은 정수 `1`이다. 문자열끼리 직접 비교하면 `'01'`로 칠해진
    맵에서 `:1`이 **영원히 `bin_absent`** 가 되고, 그건 "다 썼다"보다 더 나쁜 거짓말이다
    (존재하는 자재를 없다고 한다).

    `< 1`을 버리는 것은 클라 `parseMaterialToken`이 `BIN은 1 이상`을 거부하는 것과 같은
    규칙이다. 정수로 읽히지 않는 값(`'CORE_A'` 등)은 BIN이 아니라 **다른 용도로 칠해진
    셀**이며, 조용히 버리지 않고 `unbinned_cells`로 세어 응답에 싣는다 — 그래야
    `Σ bins.cells < cells_total`이 왜인지 화면에서 설명된다.
    """
    val, state = _int_state(raw)
    if state != BAND_TO_OK or val is None or val < 1:
        return None
    return val


def _prev_to(bands, i):
    """앞 구간의 끝 층(첫 구간 앞은 0).

    **`ok`인 구간만 걷기를 멈춘다** — blank도 invalid도 건너뛴다. 순서를 지는 것은
    **배열 위치**이며 `seq`는 정체일 뿐이라 인접성 판단에 쓰지 않는다.
    """
    for j in range(i - 1, -1, -1):
        val, state = _band_to(bands[j])
        if state == BAND_TO_OK:
            return val
    return 0


# ---------------------------------------------------------------------------
# ZONE 모델 — STACK + 세 구역
#
# 아래 함수들은 `client2/src/doe_bands.js`의 **미러**이며, 양쪽이 같은 파일
# (`contracts/doe_band_rules/vectors.json`)로 고정된다. 한 언어에만 사는 규칙은 흘러간다.
# 미러의 짝: stackState·midZone·zoneLayers·zoneDemand·parseMaterialToken·materialPoolKey·
# validateZonePlan·materialRollupRows·remainingState·bandsToZones·parseMaterialList.
# ---------------------------------------------------------------------------

def parse_material_list(raw):
    """자재 목록 하나 → 원문 토큰 리스트 (공백 제거, 첫 등장 순 중복 제거).

    클라 `parseMaterialList`의 미러. 리스트면 그대로, 문자열이면 **줄바꿈과 쉼표**로 나눈다
    — 엑셀이 따옴표 친 셀 안에 넣는 것이 정확히 줄바꿈이라, 그 원문과 클립보드의 바이트가
    같아 왕복에 변환이 없다.
    ⚠️ 이 함수는 **저장 컬럼을 직접 받지 않는다.** 컬럼은 `JSON.stringify([...])`이라
    `'["MID1","MID3"]'` 형태이고, 여기에 쉼표 분해를 걸면 `'["MID1"'`이 나온다.
    컬럼에서 읽을 때는 반드시 `_zone_tokens`를 거친다(JSON 먼저).
    """
    if isinstance(raw, list):
        out = []
        for v in raw:
            s = str("" if v is None else v).strip()
            if s and s not in out:
                out.append(s)
        return out
    s = str("" if raw is None else raw)
    out = []
    for part in re.split(r"[\n,]", s):
        t = part.strip()
        if t and t not in out:
            out.append(t)
    return out


def _zone_tokens(raw):
    """저장된 zone 컬럼 → `(토큰 리스트, 거부된 원소 리스트)`.

    writer(`map_editor.js legendRowPayload`)는 항상 JSON 배열을 쓴다. 그래서 JSON을 **먼저**
    시도하고, 배열이면 그것이 정답이다. JSON이 아니면 사람이 제네릭 그리드로 손입력한
    텍스트이므로 클라와 같은 줄바꿈/쉼표 분해로 물러선다.

    [문자열이 아닌 원소는 **거부**한다 — `_band_materials`와 같은 규율]
    숫자·bool·객체는 문자열화하지 않는다. 패널은 문자열만 쓰므로 그런 값은 그리드로만 들어올
    수 있고, 그리드 입력에 대한 옳은 답은 "클라와 같은 방식으로 잘못 읽기"가 아니라
    **"읽을 수 없다"**이다(양쪽 문자열화가 `True`/`true`, `42.0`/`42`로 갈린다).
    """
    if raw is None:
        return [], []
    if isinstance(raw, list):
        parsed = raw
    else:
        s = str(raw)
        if not s.strip():
            return [], []
        parsed = None
        if s.lstrip()[:1] == "[":
            if len(s) > MAX_BANDS_BLOB_BYTES:
                logger.warning("[TransferPlan] zone column exceeds %d bytes — refused before parse",
                               MAX_BANDS_BLOB_BYTES)
                return [], [s[:40]]
            try:
                parsed = json.loads(s)
            except Exception:
                parsed = None
        if not isinstance(parsed, list):
            return parse_material_list(s), []
    out, refused = [], []
    for m in parsed:
        if m is None:
            continue                       # 자재 없음 — 손상이 아니다
        if not isinstance(m, str):
            refused.append(m)
            continue
        t = m.strip()
        if t and t not in out:
            out.append(t)
    return out, refused


def _zone_row_get(row, key):
    """zone 행(dict)의 필드. 벡터와 DB 읽기가 같은 접근자를 쓴다."""
    return row.get(key) if isinstance(row, dict) else None


def stack_state(row):
    """행의 STACK → `(값|None, 상태)`. 클라 `stackState`의 미러.

    🔴 **판정기는 `_int_state` 하나다.** 두 번째 숫자 파서가 생기는 순간 `'0x10'`이 한쪽에서
    16, 다른 쪽에서 0이 된다 — 실제로 그렇게 16이 DB에 쓰인 적이 있다.
    `blank`는 오류가 **아니다**(아직 안 적은 값). 다만 저장·검증 시점에는 V5로 차단된다:
    계획이 반쯤 적힌 채 나갈 수는 없다.

    `marker` (U9, user 2026-07-28): an EXPLICIT 0 is a fourth state — the value paints a
    CONDITION (e.g. BASE FAIL), not a layer assignment. No zones, no demand, no rollup row;
    V6 reports the one contradiction (a marker with zone content). Blank is NOT folded into
    it — blank is absence, 0 is a declaration. Only exactly 0: negatives stay `invalid`
    **and keep their value** (the user must be told what to fix).
    """
    val, st = _int_state(_zone_row_get(row, "stack"))
    if st != BAND_TO_OK:
        return None, st
    if val == 0:
        return 0, STACK_MARKER
    if val < 0:
        return val, BAND_TO_INVALID
    return val, BAND_TO_OK


def mid_zone(row):
    """MID 구역의 범위 — STACK과 **나머지 두 구역의 존재 여부**에서 유도된다.

    반환 `{from, to, size, known}`. `known=False`는 STACK을 못 읽었다는 뜻이고, 그때는
    아무것도 층 수를 계산하면 안 된다.
    🔴 `size 0` + `known True`는 "층이 없다"이고 **정상**이다(STACK 2에 1H·TOP만 있는 행).
    `known False`와 절대 같은 것으로 접지 말 것 — 접는 순간 읽지 못한 높이가 조용히 0층을
    기여하고, 16층 스택이 15층이 된다.
    """
    val, st = stack_state(row)
    has_1h = len(parse_material_list(_zone_row_get(row, "mat_1h"))) > 0
    has_top = len(parse_material_list(_zone_row_get(row, "mat_top"))) > 0
    # A marker's extent is KNOWN and EMPTY — like the E-row's 0-layer MID, a real zero,
    # NOT unknowable. Folding the two either makes V5 nag at a declared marker or lets a
    # typo'd height demand nothing behind a clean screen (vectors pin both directions).
    if st == STACK_MARKER:
        return {"from": None, "to": None, "size": 0, "known": True}
    if st != BAND_TO_OK:
        return {"from": None, "to": None, "size": 0, "known": False}
    frm = 2 if has_1h else 1
    to = (val - 1) if has_top else val
    return {"from": frm, "to": to, "size": max(0, to - frm + 1), "known": True}


def zone_layers(row, zone):
    """한 구역이 덮는 층 목록, 또는 계산 불가면 **None**.

    🔴 불가일 때 `[]`가 아니라 `None`인 것이 규칙이다. `[]`는 "0층"이라는 **정상 상태**와
    구별되지 않고, 읽지 못한 높이가 0층으로 합류하는 것이 V5가 존재하는 이유 그 자체다.
    """
    val, st = stack_state(row)
    # Marker: every zone is empty BY CONSTRUCTION ([], not None — a real, known zero),
    # however much content was typed. The content is V6's contradiction to report, not
    # the geometry's to legitimize. `zone_demand` then derives 0 from this for free.
    if st == STACK_MARKER:
        return []
    if st != BAND_TO_OK:
        return None
    present = len(parse_material_list(_zone_row_get(row, zone))) > 0
    if zone == "mat_1h":
        return [1] if present else []
    if zone == "mat_top":
        return [val] if present else []
    z = mid_zone(row)
    return list(range(z["from"], z["to"] + 1))


def zone_demand(row, zone, painted):
    """한 구역의 소요 — `{layers, total, share}`. 클라 `zoneDemand`의 미러.

        총 소요 = (그 값으로 칠한 셀 수) × (그 구역의 층 수)
        자재당  = ceil(총 소요 / 그 구역의 자재 수)

    ⚠️ **올림은 분배되지 않는다** — `ceil(3/2)+ceil(3/2)=4` 이지만 `ceil(6/2)=3`. 그래서
    합을 먼저 내고 나서 나눈다. 한 구역은 **하나의 수요**이며, 이 수를 두 번째로 계산하는
    곳이 생기면 그 자체가 결함이다(저장은 ceil, 표시는 round여서 DB 34 / 화면 33이었던 건).
    """
    span = zone_layers(row, zone)
    if span is None:
        return {"layers": 0, "total": 0, "share": 0}
    layers = len(span)
    total = int(painted or 0) * layers
    mats = parse_material_list(_zone_row_get(row, zone))
    share = (-(-total // len(mats))) if mats else 0
    return {"layers": layers, "total": total, "share": share}


def parse_material_token(raw):
    """자재 토큰 → `{ok, lot, slot, bin, scope, raw, reason}`. 클라 `parseMaterialToken` 미러.

        토큰 ::= 식별자 [ ":" BIN ] · 식별자 ::= lot "_" slot | lot · BIN 생략 → 1

    ⚠️ **`_split_material`과 다른 함수이며, 의도적으로 다르다.** 저쪽은 선언된
    `plan_store.material_identity` 규칙이고 분리자 없는 `ABC`를 거부한다. 이 문법에서
    분리자 없는 `MID1`은 해석 불가가 아니라 **"그 로트 전체"라는 뜻**이다. "추측하지
    않는다"는 원칙은 그대로다 — 진짜 malformed한 토큰(`ABC_`·`_01`·`_`·BIN 실패)은 전부
    여전히 거부한다. 정확히 한 경우만 뜻이 바뀐다(공유 벡터 material_token_cases).

    BIN은 층 경계와 **같은 정수 판정기**(`_int_state`)로 읽는다. 두 번째 숫자 파서가
    `'0x10'`을 한쪽에서 16으로 만들었던 그 자리다.
    """
    def bad(reason):
        return {"ok": False, "lot": None, "slot": None, "bin": None,
                "scope": None, "raw": str(raw if raw is not None else ""), "reason": reason}

    s = str("" if raw is None else raw).strip()
    if s == "":
        return bad("빈 값입니다.")

    # `:`는 **오른쪽에서** 자른다 — 로트 이름에 콜론이 들어갈 수 있다.
    id_part, bin_val = s, 1
    ci = s.rfind(":")
    if ci >= 0:
        id_part = s[:ci].strip()
        bin_part = s[ci + 1:].strip()
        if bin_part == "":
            return bad("':' 뒤에 BIN이 없습니다.")
        v, st = _int_state(bin_part)
        if st != BAND_TO_OK:
            return bad(f"BIN '{bin_part}'을(를) 정수로 읽을 수 없습니다.")
        if v < 1:
            return bad(f"BIN은 1 이상이어야 합니다 (지금 {v}).")
        bin_val = v
    if id_part == "":
        return bad("자재 식별자가 비어 있습니다.")

    # `_`도 오른쪽에서 자르므로 **앞 필드가 나머지를 흡수**한다: LOT_A_01 → LOT_A + 01.
    ui = id_part.rfind("_")
    if ui < 0:
        return {"ok": True, "lot": id_part, "slot": None, "bin": bin_val,
                "scope": "lot", "raw": s, "reason": ""}
    lot, slot = id_part[:ui].strip(), id_part[ui + 1:].strip()
    # 매달린 분리자는 스코프가 아니라 오타다. `ABC_`를 "로트 ABC 전체"로 읽는 것이 이 문법이
    # 여전히 거부하는 그 추측이다.
    if not lot or not slot:
        return bad(f"'{id_part}'을(를) lot_slot으로 나눌 수 없습니다.")
    return {"ok": True, "lot": lot, "slot": slot, "bin": bin_val,
            "scope": "slot", "raw": s, "reason": ""}


def material_pool_key(tok):
    """롤업 행 하나의 안정된 정체 = 풀 `(lot, slot, BIN)`.

    🔴 **`json.dumps`로 만든다. 분리자로 잇지 않는다.** 이어붙이려면 로트 이름에 나올 수 없는
    문자가 필요한데, 후보는 로트 이름에 합법이거나(`|`·`_`·`:`) 도구가 조용히 삭제하는 제어
    문자다. 실제로 U+001F로 이었던 판이 있었고, 문자가 쓰기 과정에서 사라져 `MID1_12:3`과
    `MID11_2:3`이 둘 다 "MID1123"이 됐다 — 무관한 두 풀이 한 행으로 합쳐지고 사용량이
    더해졌다. JSON은 구성요소를 스스로 이스케이프하고, `null`(로트 전체)이 문자열 `"null"`
    (그렇게 이름 붙은 슬롯)과 **구조적으로** 구별된다.
    구분자를 고르고 있다면 그 자체가 이 함수를 쓰라는 신호다.
    """
    if not tok or not tok.get("ok"):
        return None
    slot = None if tok.get("scope") == "lot" else tok.get("slot")
    return json.dumps([tok.get("lot"), slot, tok.get("bin")],
                      separators=(",", ":"), ensure_ascii=False)


def _zone_raw_items(raw):
    """중복 판정용 **원문 그대로의** 항목 목록(중복 제거 없음)."""
    if isinstance(raw, list):
        items = raw
    else:
        s = str("" if raw is None else raw)
        if s.lstrip()[:1] == "[":
            try:
                parsed = json.loads(s)
                items = parsed if isinstance(parsed, list) else re.split(r"[\n,]", s)
            except Exception:
                items = re.split(r"[\n,]", s)
        else:
            items = re.split(r"[\n,]", s)
    return [t for t in (str("" if x is None else x).strip() for x in items) if t]


def validate_zone_plan(rows):
    """V1~V6 + W-DUP-MAT. 반환 `{ok, blocks[], warns[]}` — 클라 `validateZonePlan`의 미러.

      V5  STACK을 양의 정수로 읽을 수 없다      ← **가장 먼저** 판정한다
      V2  STACK 1인데 1H·TOP이 둘 다 있다       ← 두 자재가 같은 1층을 잡는다
      V1  MID 구역이 비어 있지 않은데 MID가 없다 ← 조건부. 구역이 0층이면 발동하지 않는다
      V4  자재 토큰을 읽을 수 없다
      V3  로트 전체와 그 로트의 슬롯이 같은 BIN에 함께 지정됐다  ← **계획 전체**의 성질
      V6  STACK 0(상태 표시 값)인데 구역에 자재가 있다  ← marker rows answer to V6 ALONE.
          A marker's materials are never looked up or demanded, so V4 on them would give a
          second, contradictory instruction (fix the token vs remove the materials) — same
          suppression pattern as V5-suppresses-V1. They are also absent from V3's pool
          scan: a demandless token cannot double-count anything.

    🔴 V5가 먼저인 이유. 구 모델은 값의 높이를 **덮인 층에서 유도**해서, 배정되지 않은 위쪽
       구간이 그냥 max를 낮췄고 다른 규칙은 전부 통과했다 — 16층 스택이 조용히 15층이 됐다.
       zone은 높이를 유도하지 않고 STACK이 **말한다**. 그 구멍이 닫히는 것은 STACK을 읽을 수
       있는 동안뿐이다. 읽지 못한 STACK을 0으로 보거나 건너뛰면 동일한 결함이 멀쩡해 보이는
       화면 뒤에서 재현된다. 그래서 차단이고, 가장 먼저 차단한다.

    구 B1·B2(FROM>TO, FROM<1)·B5(겹침)·B6(구멍)·B4/B9(값 집합 참조)는 **없다.** 완화가
    아니라 세 구역이 `1..STACK`을 구성적으로 덮어 그 상태를 말할 수 없기 때문이다.
    """
    blocks, warns = [], []
    rows = rows or []

    def add(lst, rule, message, **extra):
        entry = {"rule": rule, "message": message}
        entry.update(extra)
        lst.append(entry)

    def zone_label(row, zone):
        v = _zone_row_get(row, "value")
        return f"값 '{'' if v is None else v}'의 {ZONE_LABEL[zone]}"

    for row in rows:
        raw_v = _zone_row_get(row, "value")
        v = str("" if raw_v is None else raw_v)
        val, st = stack_state(row)
        mats = {z: parse_material_list(_zone_row_get(row, z)) for z in ZONES}

        # V6 — the marker contradiction, and the ONLY rule a marker row answers to. Zone
        # content on a 0-stack row means one of the two statements is wrong, and only the
        # user knows which — report it, never silently drop the materials (they may be the
        # half the user meant to keep). The materials are named in the message because the
        # zone cells render disabled (해당 없음) on a marker row client-side, which would
        # otherwise make the offending content invisible.
        if st == STACK_MARKER:
            with_content = [z for z in ZONES if mats[z]]
            if with_content:
                add(blocks, "V6",
                    f"값 '{v}'은(는) STACK 0(상태 표시 값)인데 구역에 자재가 있습니다 — "
                    + " · ".join(f"{ZONE_LABEL[z]}: {', '.join(mats[z])}" for z in with_content)
                    + " — 층이 없는 값은 자재를 가질 수 없습니다. "
                      "STACK을 채우거나 자재를 지우십시오.",
                    value=v, zone=with_content[0])
            continue   # V5/V2/V1/V4/W-DUP-MAT do not fire on a marker row

        if st != BAND_TO_OK:
            shown = "(비어 있음)" if st == BAND_TO_BLANK else json.dumps(
                _zone_row_get(row, "stack"), ensure_ascii=False)
            add(blocks, "V5",
                f"값 '{v}'의 STACK {shown}을(를) 1 이상의 정수로 읽을 수 없습니다 — "
                f"층 구조를 계산할 수 없습니다.", value=v)
        elif val == 1 and mats["mat_1h"] and mats["mat_top"]:
            # V2. STACK 1이면 층은 하나뿐인데 두 구역이 그 층을 함께 잡는다.
            # MID 문제로 보고하지 **않는다** — 여기서 MID 구역은 0층이고, MID를 탓하면
            # 사용자를 유일하게 결백한 칸으로 보내게 된다.
            add(blocks, "V2",
                f"값 '{v}'은(는) STACK 1인데 1H와 TOP이 모두 있습니다 — "
                f"'{mats['mat_1h'][0]}'와(과) '{mats['mat_top'][0]}'이(가) 같은 1층을 잡습니다.",
                value=v, zone="mat_1h")

        # V1 — 조건부이고 그 조건이 전부다. STACK 1 MID단독은 통과(구역 1–1층, MID 있음),
        # STACK 2 + 1H·TOP + MID없음도 통과(구역 0층). 높이를 읽을 수 있을 때만 계산한다:
        # V5가 이미 보고된 행에서 구역을 추측하면 같은 행에 모순된 두 메시지가 나간다.
        # ⚠️ 이 `st == ok` 가드는 지금 **중복이다**(뮤테이션으로 확인: 제거해도 벡터가 전부
        #    통과한다). `mid_zone`이 known=False일 때 size 0을 돌려주므로 아래 조건이 이미
        #    거짓이기 때문이다. 그래도 남긴다 — 억제는 `mid_zone`의 부수효과가 아니라
        #    **이 규칙의 성질**이고, 저쪽이 언젠가 unknown에 다른 size를 돌려주는 순간
        #    이 한 줄이 유일한 방어가 된다. 클라 `validateZonePlan`도 같은 이중 가드다.
        if st == BAND_TO_OK:
            z = mid_zone(row)
            if z["size"] > 0 and not mats["mat_mid"]:
                add(blocks, "V1",
                    f"{zone_label(row, 'mat_mid')} 구역이 "
                    f"{_format_layer_runs(zone_layers(row, 'mat_mid'))}({z['size']}층)인데 "
                    f"비어 있습니다 — 구역이 있으면 MID는 반드시 있어야 합니다.",
                    value=v, zone="mat_mid")

        for z in ZONES:
            # V4 — 못 읽는 토큰은 차단한다. 조회할 수 없으니 그 가용은 영원히 0으로만 보고될
            # 수 있는데, `0`은 "다 썼다"로 읽힌다. 진실은 "해석한 적이 없다"이다.
            for token in mats[z]:
                t = parse_material_token(token)
                if not t["ok"]:
                    add(blocks, "V4",
                        f"{zone_label(row, z)}의 자재 '{token}'을(를) 읽을 수 없습니다 — {t['reason']}",
                        value=v, zone=z)
            # 한 구역 **안**의 중복은 `share`의 분모를 이유 없이 바꾼다. 구역을 가로지르는
            # 중복은 정당하다(같은 로트가 바닥에도 중간에도 들어가는 것은 다른 층의 수요다).
            raw_items = _zone_raw_items(_zone_row_get(row, z))
            dup = [m for i, m in enumerate(raw_items) if raw_items.index(m) != i]
            if dup:
                seen, uniq = set(), []
                for m in dup:
                    if m not in seen:
                        seen.add(m)
                        uniq.append(m)
                add(warns, "W-DUP-MAT",
                    f"{zone_label(row, z)}에 같은 자재가 중복 지정됐습니다: {', '.join(uniq)}",
                    value=v, zone=z)

    # ---- V3: 로트 전체와 그 로트의 슬롯이 같은 BIN에 ----
    # `MID1:2`는 MID1의 모든 슬롯 BIN 2를 덮고 `MID1_03:2`는 슬롯 03 BIN 2를 덮는다. 함께
    # 지정되면 슬롯 03이 두 번 계산되고, 부풀린 수요는 가장 나쁜 순간에 부족으로 나타난다.
    # 같은 로트라도 BIN이 다르면 다른 풀이므로 정상이다.
    #
    # 🔴 이것은 **행 쌍이 아니라 계획 전체의 성질**이다. 두 토큰은 보통 서로 다른 값에 있어서,
    #    행 단위 구현은 이 계획을 통과시키고 이중 계산된 웨이퍼가 나중에 부족으로 튀어나온다.
    # 키는 `json.dumps([lot, bin])` — 로트 이름에 나올 수 없는 문자가 없고, 보이지 않는
    # 분리자는 합법인 것보다 **더 나쁘다**(도구가 지운다). `MID1`+bin`12`와 `MID11`+bin`2`를
    # 지워진 분리자로 이으면 둘 다 "MID112"가 되어, 맞는 계획을 막고 진짜 이중 계산은 놓친다.
    lot_scoped, slot_scoped = {}, {}
    for row in rows:
        # Marker rows are not in this scan: their tokens demand nothing, so pairing one
        # with a real row's slot would block a correct plan over wafers nobody asked for.
        # The content itself is already V6's report.
        if stack_state(row)[1] == STACK_MARKER:
            continue
        raw_v = _zone_row_get(row, "value")
        v = str("" if raw_v is None else raw_v)
        for z in ZONES:
            for token in parse_material_list(_zone_row_get(row, z)):
                t = parse_material_token(token)
                if not t["ok"]:
                    continue                 # V4가 보고한다 — 여기서 이중 보고하지 않는다
                key = json.dumps([t["lot"], t["bin"]], separators=(",", ":"), ensure_ascii=False)
                target = lot_scoped if t["scope"] == "lot" else slot_scoped
                target[key] = {"raw": t["raw"], "value": v, "zone": z}
    for key in sorted(lot_scoped.keys()):
        slot_hit = slot_scoped.get(key)
        if not slot_hit:
            continue
        lot_hit = lot_scoped[key]
        add(blocks, "V3",
            f"자재 '{lot_hit['raw']}'(로트 전체 · 값 '{lot_hit['value']}')와 "
            f"'{slot_hit['raw']}'(그 로트의 슬롯 · 값 '{slot_hit['value']}')이 같은 BIN에 "
            f"함께 지정됐습니다 — 그 슬롯이 두 번 계산됩니다.",
            value=slot_hit["value"], zone=slot_hit["zone"])

    return {"ok": len(blocks) == 0, "blocks": blocks, "warns": warns}


def _format_layer_runs(layers):
    """[13,14,15,19] → "13–15층, 19층". 클라 `formatLayerRuns` 미러."""
    xs = sorted(set(layers or []))
    runs, i = [], 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[j] + 1:
            j += 1
        runs.append(f"{xs[i]}층" if xs[i] == xs[j] else f"{xs[i]}–{xs[j]}층")
        i = j + 1
    return ", ".join(runs)


def material_rollup_rows(rows, painted_of):
    """② 자재 롤업 — **파생 전용**. 클라 `materialRollupRows` 미러.

    행의 정체는 **풀 `(lot, slot, BIN)`**이지 자재 이름이 아니다. 서로 다른 값의 서로 다른
    구역이 한 풀에 합쳐지며, 그것이 이 표가 존재하는 이유다.

    ⚠️ `used`는 **충분성 판정이지 배분이 아니다.** 웨이퍼는 한 장씩 소진되고 그 순서를 아무도
       기록하지 않는다 — 균등 분할은 "이 풀 전체에 충분한가"만 답하며 "이 웨이퍼가 정확히
       N장을 댄다"로 읽혀서는 안 된다.
    구역별 올림 때문에 한 구역의 share 합은 그 구역의 total보다 크다. 의도된 것이다:
    내림·반올림은 부족을 숨기고, 조용히 적게 주문하는 계획이 더 비싸다.
    """
    by_pool = {}
    for row in rows or []:
        # A marker row (STACK 0) is ABSENT from the rollup, not present-with-zero: a
        # "사용 0" row would read as "planned, costs nothing" and invite an availability
        # query for material nobody is demanding. Its painted count is a message, not a
        # multiplier, and its zone content (if any) is V6's contradiction — not inventory.
        if stack_state(row)[1] == STACK_MARKER:
            continue
        raw_v = _zone_row_get(row, "value")
        v = str("" if raw_v is None else raw_v)
        painted = int(painted_of(v) or 0) if callable(painted_of) else int((painted_of or {}).get(v, 0))
        for z in ZONES:
            d = zone_demand(row, z, painted)
            for token in parse_material_list(_zone_row_get(row, z)):
                tok = parse_material_token(token)
                key = material_pool_key(tok)
                if key is None:
                    continue                  # V4가 저장을 막는다 — 여기서 행이 되지는 않는다
                e = by_pool.get(key)
                if e is None:
                    e = by_pool[key] = {"key": key, "lot": tok["lot"],
                                        "slot": None if tok["scope"] == "lot" else tok["slot"],
                                        "bin": tok["bin"], "scope": tok["scope"],
                                        "raw": tok["raw"], "used": 0, "uses": []}
                e["used"] += d["share"]
                # 구역을 use에 남긴다 — 패널이 수요의 출처를 다시 계산하지 않고 말할 수 있다.
                e["uses"].append({"value": v, "zone": z, "layers": d["layers"], "qty": d["share"]})
    return sorted(by_pool.values(),
                  key=lambda e: (str(e["lot"]), str(e["slot"] or ""), e["bin"]))


# 가용을 신뢰할 수 없을 때의 기본 사유. `availabilityOf`가 정확한 사유를 갖고 있으면 그쪽이
# 이긴다 — "이 BIN이 없다"·"서버가 답을 못 준다"·"아직 안 물어봤다"는 서로 다른 상황이고
# 사용자의 행동이 다르다. 하나의 「미상」으로 접으면 숨기는 행위가 무의미해진다.
REMAINING_UNKNOWN_REASON = {
    "bin_absent": "이 맵에 해당 BIN이 없습니다 — 소진된 것이 아닙니다.",
    "loading": "가용을 조회하는 중입니다.",
    "not_queried": "가용을 아직 조회하지 않았습니다.",
}


def remaining_state(availability, used):
    """잔여 = 가용 − 사용, **가용의 신뢰도를 함께 들고** 간다. 클라 `remainingState` 미러.

    🔴 가용을 믿을 수 없으면 잔여는 **절대 숫자가 아니다.** 믿을 수 없는 입력에서 나온 확신에
       찬 수치는 수치가 없는 것보다 나쁘다 — `0`은 "다 썼다"로 읽히지만 진실은 "이 맵에 그
       BIN이 없다"거나 "물어볼 수 없었다"일 수 있다.
    """
    a = availability or {}
    status = a.get("status")

    def unknown(reason):
        return {"value": None, "reliable": False, "reason": reason}

    if status == "bin_absent":
        return unknown(REMAINING_UNKNOWN_REASON["bin_absent"])
    if status is None:
        return unknown(a.get("reason") or REMAINING_UNKNOWN_REASON["not_queried"])
    if status == "loading":
        return unknown(a.get("reason") or REMAINING_UNKNOWN_REASON["loading"])
    if a.get("reliable") is not True or a.get("value") is None:
        return unknown(a.get("reason") or "가용을 신뢰할 수 없습니다.")
    return {"value": int(a["value"]) - int(used or 0), "reliable": True, "reason": ""}


def bands_to_zones(bands):
    """폐기 모델 읽기: `bands` → zone 행. 클라 `bandsToZones` 미러.

    🔴 **왜 존재하는가.** `map_split_registry.bands`에는 band 모델이 쓴 실계획이 들어 있다.
       zone 리더가 그 컬럼을 그냥 무시하면 그 맵을 여는 순간 계획이 비어 보이고, legend
       저장은 `replace_map`이라 그 다음 편집 한 번이 계획을 **빈 집합으로 지운다.** 이
       마이그레이션은 호의가 아니라 불변식이다.

    🔴 **그리고 추측하는 대신 거부한다.** 모든 band 배치가 세 구역으로 표현되지는 않는다
       (구간 4개, 1층에서 시작하지 않는 첫 구간, 읽을 수 없는 `to`, 역전된 `to`). 그런
       경우 `{ok: False}`이며 호출자는 그 값을 "읽을 수 없음"으로 표면화하고 저장을 막아야
       한다 — 4구간을 3구역으로 뭉갠 뒤 그 뭉갠 결과를 서버의 진실 위에 `replace_map`으로
       되쓰는 것이 정확히 "화면은 멀쩡, 값은 틀림" 결함이다.

    사상 규칙:
      n = 1        → MID 단독. 스택 전체를 덮는 한 구간이 곧 "그 사이 전부"이며 1H·TOP은
                     거기서 도려낸 예외다.
      n > 1        1H  = band[0]   (정확히 1층만 덮을 때)
                   TOP = band[n-1] (정확히 STACK층만 덮을 때)
                   MID = 남은 것. 남은 것이 **하나 이하**여야 한다.
    """
    src = bands if isinstance(bands, list) else []
    if not src:
        return {"ok": True, "stack": "", "mat_1h": [], "mat_mid": [], "mat_top": []}
    if len(src) > MAX_BANDS_PER_PLAN:
        # 손상된 blob의 폭주 차단. 이 크기는 어차피 표현 불가이며(구간 4개부터 거부),
        # 여기서 막지 않으면 거부를 결정하기 위해 배열 전체를 걷게 된다.
        return {"ok": False, "reason": f"구간이 상한({MAX_BANDS_PER_PLAN})을 넘습니다."}
    spans = []
    refused_all = []      # 자재로 읽을 수 없는 원소 — 호출자가 표면화한다(조용히 버리지 않는다)
    for i, b in enumerate(src):
        val, st = _band_to(b)
        # 읽을 수 없는 `to`는 **거부**이지 건너뛰기가 아니다. `prevTo`는 건너뛴다 — band를
        # 편집 중인 패널에서는 그게 옳았다(보여 주고, 표시하고, 계속). 여기서 건너뛰면
        # 스택이 조용히 짧아지는데, 마이그레이션이 절대 내면 안 되는 유일한 결과다.
        if st != BAND_TO_OK:
            return {"ok": False, "reason": f"{i + 1}번째 구간의 끝 층을 읽을 수 없습니다."}
        prev = _prev_to(src, i)
        if val <= prev:
            return {"ok": False,
                    "reason": f"{i + 1}번째 구간의 끝 층 {val}이(가) 앞 구간({prev})보다 크지 않습니다."}
        mats, refused = _zone_tokens((b or {}).get("materials"))
        refused_all.extend(refused)
        spans.append({"from": prev + 1, "to": val, "materials": mats})

    stack = spans[-1]["to"]
    if len(spans) == 1:
        return {"ok": True, "stack": stack, "mat_1h": [],
                "mat_mid": spans[0]["materials"], "mat_top": [], "refused": refused_all}
    rest = list(spans)
    h1, top = [], []
    if rest[0]["from"] == 1 and rest[0]["to"] == 1:
        h1 = rest.pop(0)["materials"]
    if rest and rest[-1]["from"] == stack and rest[-1]["to"] == stack:
        top = rest.pop()["materials"]
    if len(rest) > 1:
        return {"ok": False,
                "reason": (f"구간 {len(src)}개는 1H·MID·TOP 세 구역으로 표현할 수 없습니다 — "
                           f"중간 구간이 {len(rest)}개입니다.")}
    return {"ok": True, "stack": stack, "mat_1h": h1,
            "mat_mid": rest[0]["materials"] if rest else [], "mat_top": top,
            "refused": refused_all}


def _material_identity_rule(cfg: dict):
    """자재 ID 문자열을 소스 `(lot, slot)`으로 푸는 **선언된** 규칙. 미선언이면 None.

    자재는 사용자가 입력한 **원문 문자열이 곧 정체**다(`map_editor.js`) — 파싱은 나중 일이고
    파싱 규칙이 바뀌어도 키가 움직여선 안 된다. 그래서 해석은 코드에 박힌 관례가 아니라
    `plan_store.material_identity` 선언으로만 성립한다. 형태는 `_origin_map_id`가 쓰는
    `identity.compose` 관례와 같고 분리자만 더한다.
    """
    rule = (cfg.get("plan_store") or {}).get("material_identity")
    if not isinstance(rule, dict):
        return None
    compose = rule.get("compose")
    if not (isinstance(compose, list) and all(isinstance(c, str) for c in compose)):
        return None
    if not {"lot", "slot"}.issubset(set(compose)):
        return None        # 소스 가용 조회가 요구하는 두 역할이 없으면 규칙이 무의미하다
    return {"compose": list(compose), "separator": str(rule.get("separator") or "_")}


def _split_material(material_id, rule):
    """자재 ID → `(lot, slot)`. 규칙 미선언이거나 안 풀리면 `(None, None)` — 추측 금지.

    [분리 방향] **뒤에서부터** 자르므로 앞 필드가 나머지를 흡수한다 —
    `client2/src/transfer_plan.js`의 `splitMaterialId`(`lastIndexOf('_')`)와 **방향만** 같다.
    풀리지 않는 입력에서는 일부러 갈린다(아래) — "같은 읽기"라고 뭉뚱그리지 말 것.
    ⚠️ `map_overlay.build_key_filters`는 반대(**뒤** 필드가 흡수)이며, 이제 같은 분리자를
    세 관례가 나눠 쓴다 — `PRIMITIVES.md` §2에 등록된 결정을 따른다. 이쪽이 클라와 맞아야
    하는 이유는 하나다: DOE 패널과 이 검증기가 **같은 자재로 같은 엔드포인트**
    (`source-summary`)를 묻기 때문에, 분해가 다르면 한 화면에 두 개의 가용치가 생긴다.

    [분리자가 없으면 **거부**한다 — 총괄 결정 2026-07-27]
    `ABC`는 `(lot, slot)`으로 풀 수 없다. 클라는 `("ABC", "")`를 돌려주고 그대로
    `source-summary?lot=ABC&slot=`를 물어 **0을 숫자로 표시**하는데, 그쪽이 틀린 쪽이다 —
    조회되지 않은 것과 잔여가 0인 것은 다르고, 후자로 보이면 부족 경고가 조용히 죽는다.
    여기서는 해석 실패로 두어 `source_unresolved` + `unverified`가 되게 한다.
    양쪽 필드 모두 공백을 제거한 뒤 판정하므로 `" A _ 01 "`도 `("A", "01")`로 풀린다.
    """
    if rule is None:
        return None, None
    s = str(material_id or "").strip()
    if not s:
        return None, None
    parts = s.rsplit(rule["separator"], len(rule["compose"]) - 1)
    if len(parts) < len(rule["compose"]):
        return None, None            # 분리자 부재 — 추측하지 않는다
    vals = dict(zip(rule["compose"], parts))
    lot, slot = str(vals.get("lot") or "").strip(), str(vals.get("slot") or "").strip()
    if not lot or not slot:
        return None, None            # 선행/후행 분리자로 한쪽이 비면 그것도 해석 실패다
    return lot, slot


def _painted_values(db, ref_table: str, map_key: str, overlay_cfg: dict):
    """대상 맵 **자신의** 셀에서 값 분포를 group-by로 센다 (계획 맵 사본 없음 — v2).

    반환: ({값: 셀 수}, 상태 문자열, 절단 여부). 좌표/키 바인딩은 맵 오버레이와 **동일한
    유도 규칙**을 쓴다(table_config의 map_key_columns + x/y + val 후보 → 선언이 있으면 선언 우선).
    [확장성] 셀을 전량 로드하지 않고 group-by 집계만 한다 — 맵 1장이 수만 셀이다.

    [B2] 세 번째 반환값이 있는 이유: `MAX_PLAN_VALUES` 절단은 이 모듈의 네 번째 캡인데
    유일하게 조용했다. M2.6에서 수량이 **이 dict에서 유도**되므로, 값이 빠지면 그 값의
    required가 0이 되어 부족이 영원히 발화하지 않는다. 호출자가 절단을 알아야 한다.
    [재현성] 절단이 있을 수 있으면 어떤 행이 살아남는지가 결정적이어야 한다 → ORDER BY.
    """
    from sqlalchemy import func
    from database import models
    import map_overlay

    model = models.DYNAMIC_TABLES.get(ref_table)
    if model is None:
        return {}, "missing", False
    binding = map_overlay.resolve_binding(overlay_cfg, ref_table)
    if binding is None:
        return {}, "missing", False
    val_col = getattr(model, binding.get("val") or "", None)
    if val_col is None:
        return {}, "missing", False
    filters = map_overlay.build_key_filters(model, binding, map_key)
    if filters is None:
        return {}, "missing", False
    try:
        rows = (db.query(val_col, func.count())
                .filter(*filters).group_by(val_col).order_by(val_col)
                .limit(MAX_PLAN_VALUES + 1).all())
    except Exception as e:
        logger.warning("[TransferPlan] painted values query failed (%s/%s): %s",
                       ref_table, map_key, e)
        return {}, "missing", False
    truncated = len(rows) > MAX_PLAN_VALUES
    if truncated:
        logger.warning("[TransferPlan] painted values hit cap (%d) for '%s/%s' — "
                       "derived quantities would be understated",
                       MAX_PLAN_VALUES, ref_table, map_key)
        rows = rows[:MAX_PLAN_VALUES]
    painted = {}
    for val, cnt in rows:
        if val is None or str(val).strip() == "":
            continue
        painted[str(val)] = int(cnt)
    return painted, "connected", truncated


def validate_plan(db, cfg: dict, ref_table: str, map_key: str,
                  overlay_cfg: dict = None) -> dict:
    """GET /api/transfer-plan/validate — 경고 목록 생성 (**v2 계획 모델**).

    [정체성] 계획은 `(ref_table, map_key)` — 지금 열어 편집 중인 그 맵 자체다. `plan_id`도
    계획 헤더 테이블도 없다. stage는 `stages.*.target_map.table` 역인덱스로 유도한다.
    [DOE 단위] **레지스트리 행 1개 = legend 값 1개 = DOE 조건 1개.**
    [zone 모델] 층 구조는 `stack` 하나와 세 구역(`mat_1h`/`mat_mid`/`mat_top`)이며, 수량은
    **저장되지 않고 유도된다**: `layers = 그 구역이 덮는 층 수`,
    `total = painted(값) × layers`, `share = ceil(total / 그 구역의 자재 수)`.
    폐기된 `bands` 행은 `bands_to_zones`로 **읽되 표현 불가하면 거부**한다.
    [완화 마커] 판정에 쓰인 가용치가 미선언 감산항(`inactive_subtractions`) 위에서
    계산됐으면 요약 응답과 **같은 이름의 선택 필드**로 그 사실을 함께 낸다 — 판정
    (`status`)은 바꾸지 않는다(총량이 순량 행세를 하는 것만 막는다).

    LookupError: plan_store.registry 미구성 (라우트가 404로 변환).
    """
    reg_src, reg_model, reg_cols = _plan_store_binding(
        cfg, "registry", required=REGISTRY_ROLES)
    if reg_model is None:
        raise LookupError("plan store is not configured (plan_store.registry unresolved)")

    if overlay_cfg is None:
        import map_overlay
        overlay_cfg = map_overlay.load_overlay_config()   # 작업 경계 1회 스냅샷

    stage_name = stage_of_table(cfg, ref_table)
    warnings_out = []

    stage_cfg = get_stages(cfg).get(stage_name) if stage_name else None
    if not isinstance(stage_cfg, dict):
        warnings_out.append({
            "type": WARN_STAGE_UNKNOWN,
            "effect": "validation_skipped",
            "detail": f"맵 테이블 '{ref_table}'을 target_map으로 선언한 stage가 없음 — "
                      f"**수량·가용·fail 검증을 전혀 수행하지 못했다**(경고 없음 = 이상 없음이 아님)",
        })
        stage_cfg = None

    # ---- 계획 로드 (계획 맵 정체성으로 equality 조회 — LIKE 프리픽스 스캔 금지) ----
    # [M2.6] 조회가 한 번이다. 구간·자재가 각각 테이블이던 시절의 2회 조회 + 조인은 사라졌다.
    # [재현성] 절단이 가능한 조회는 정렬이 있어야 어느 행이 살아남는지가 결정적이다 —
    # 없으면 같은 계획이 요청마다 다른 부분집합으로 검증된다.
    reg_rows = (db.query(reg_model)
                .filter(reg_cols["ref_table"] == ref_table,
                        reg_cols["map_key"] == map_key)
                .order_by(reg_cols["value"])
                .limit(MAX_DOE_PER_PLAN + 1).all())
    rows_truncated = len(reg_rows) > MAX_DOE_PER_PLAN
    if rows_truncated:
        logger.warning("[TransferPlan] plan '%s/%s' registry rows exceed cap (%d) — truncated",
                       ref_table, map_key, MAX_DOE_PER_PLAN)
        reg_rows = reg_rows[:MAX_DOE_PER_PLAN]

    def _reg_get(row, role_key):
        name = (reg_src.get("columns") or {}).get(role_key)
        return getattr(row, name, None) if name else None

    plan = []          # zone 행 dict 목록 — 층 구조를 읽어낸 행만
    unreadable = []    # 구조를 읽지 못한 값 (= "구간 없음"이 아니다)
    # [구조 거부] 우리가 정한 형태가 아닌 것을 만났다는 뜻. 저장된 값이 계약의 모양이 아니면
    # 나머지를 읽은 방식도 믿을 근거가 없다 → 계획 전체를 unverified로 내린다
    # (아래 availability_checked).
    structural_refusal = False
    for row in reg_rows:
        v = _reg_get(row, "value")
        if v is None or str(v).strip() == "":
            continue
        v = str(v)
        # zone 컬럼이 이 배포의 정본이다. 세 구역과 STACK을 먼저 읽고, **하나라도 값이
        # 있으면** 그것이 그 행의 계획이다 — 클라 `map_editor.js`의 `hasZone` 판정과 같은
        # 규칙이라 화면과 이 검증기가 같은 행을 같은 모양으로 본다.
        zone_row = {"value": v, "stack": _reg_get(row, "stack")}
        refused_items = []
        for z in ZONES:
            toks, refused = _zone_tokens(_reg_get(row, z))
            zone_row[z] = toks
            refused_items.extend(refused)
        if refused_items:
            # 자재로 읽을 수 없는 원소가 섞였다. 남은 것만으로 배분하면 **분모가 틀린 채**
            # 그럴듯한 수가 나오므로 이 행은 통째로 검증하지 않는다.
            structural_refusal = True
            shown = ", ".join(repr(x) for x in refused_items[:3])
            warnings_out.append({
                "type": WARN_SOURCE_UNRESOLVED, "value": v,
                "refused": len(refused_items),
                "detail": (f"DOE '{v}'의 자재 목록에 문자열이 아닌 원소가 "
                           f"{len(refused_items)}개 있다({shown}) — 자재 ID는 적은 그대로의 "
                           f"문자열이어야 한다. 숫자로 읽어 넘기지 않고 거부했으므로 "
                           f"이 값의 수량은 검증되지 않았다"),
            })
        has_zone = (str(zone_row["stack"] or "").strip() != ""
                    or any(zone_row[z] for z in ZONES))

        if not has_zone:
            # ---- 폐기 모델 읽기 (`bands`) ----
            # 🔴 무시하면 그 맵을 여는 순간 계획이 비어 보이고, legend 저장은 `replace_map`
            #    이라 다음 편집 한 번이 계획을 빈 집합으로 지운다. 읽는 것은 호의가 아니다.
            legacy_col = (reg_src.get("columns") or {}).get(REGISTRY_LEGACY_ROLE)
            bands, readable, dropped = _parse_bands(
                getattr(row, legacy_col, None) if legacy_col else None)
            if not readable:
                unreadable.append(v)
                continue
            if dropped:
                structural_refusal = True
                warnings_out.append({
                    "type": WARN_LAYER_RANGE_INVALID, "value": v,
                    "reason": "not_a_band", "dropped": dropped,
                    "detail": (f"DOE '{v}'의 폐기 구간 목록에 구간이 아닌 원소 {dropped}개가 "
                               f"있어 거부했다 — 배열 길이가 바뀌면 뒤 구간의 시작 층이 함께 "
                               f"밀리므로 이 값의 수치는 검증하지 않았다"),
                })
                continue
            if bands:
                conv = bands_to_zones(bands)
                if not conv.get("ok"):
                    # 🔴 접어서 통과시키지 않는다. 뭉갠 읽기를 저장하면 `replace_map`이
                    #    서버의 진짜 계획을 그 손실 읽기로 덮는다.
                    # ⚠️ 이것은 `structural_refusal`이 **아니다.** 그 플래그는 "우리가 나머지를
                    #    읽은 방식도 믿을 수 없다"는 뜻인데, 여기서 거부되는 것은 이 행 하나이고
                    #    다른 값은 각자의 컬럼에 있어 영향을 받지 않는다. 한 값의 손상으로 계획
                    #    전체의 검증을 죽이면 사용자는 고칠 곳을 한 번에 하나씩만 알게 된다.
                    warnings_out.append({
                        "type": WARN_LAYER_RANGE_INVALID, "value": v,
                        "reason": "not_convertible",
                        "detail": (f"DOE '{v}'의 폐기 구간 정의를 1H·MID·TOP 세 구역으로 "
                                   f"표현할 수 없어 거부했다: {conv.get('reason')} — "
                                   f"접어서 저장하면 계획이 바뀌므로 이 값은 검증하지 않았다"),
                    })
                    continue
                zone_row["stack"] = conv["stack"]
                for z in ZONES:
                    zone_row[z] = conv[z]
                if conv.get("refused"):
                    # 폐기 blob의 자재 목록에 문자열이 아닌 원소가 있었다. 버리되 조용히
                    # 버리지 않는다 — 남은 것만으로 배분하면 분모가 틀린다.
                    structural_refusal = True
                    shown = ", ".join(repr(x) for x in conv["refused"][:3])
                    warnings_out.append({
                        "type": WARN_SOURCE_UNRESOLVED, "value": v,
                        "refused": len(conv["refused"]),
                        "detail": (f"DOE '{v}'의 폐기 구간 자재 목록에 문자열이 아닌 원소가 "
                                   f"{len(conv['refused'])}개 있다({shown}) — 거부했으므로 "
                                   f"이 값의 수량은 검증되지 않았다"),
                    })
        plan.append(zone_row)

    # ---- 페인팅 값 분포 — **대상 맵 자신**에서 (계획 맵 사본 폐기) ----
    painted, painted_status, painted_truncated = _painted_values(
        db, ref_table, map_key, overlay_cfg)
    # [B2] 수량이 이 dict에서 **유도**되므로, 못 읽었거나 절단됐다면 required가 전부 과소하다
    # (0으로 내려가면 `0 > available`이 영원히 거짓이라 부족이 발화하지 않는다). 구 모델은
    # qty_total을 저장에서 읽어 이 실패에 면역이었다 — 유도로 바꾸며 생긴 새 의존이다.
    painted_reliable = (painted_status == "connected") and not painted_truncated

    # DOE로 취급되는 값 = **층 구조를 하나라도 적은** 행(STACK이 비어 있지 않거나 자재가
    # 있는 행). 색만 지정된 legend 행은 아직 DOE가 아니므로 경고로 사용자를 괴롭히지 않는다.
    #
    # 🔴 **이것이 V1~V5를 적용하는 범위이기도 하다 — 클라 호출자와 여기서 갈린다.**
    #    패널(`transfer_plan.js`)은 화면에 있는 legend 행 전부를 `validateZonePlan`에 넘긴다.
    #    이 엔드포인트가 같은 짓을 하면, 계획을 세운 적도 없는 맵의 순수 legend 값마다 V5
    #    (STACK 비어 있음)가 하나씩 나가 진짜 신호를 덮는다 — 자기 자신을 무시하도록 가르치는
    #    검증기가 정확히 이 계약이 막으려는 것이다. **규칙은 바뀌지 않는다**(`validate_zone_plan`
    #    은 벡터 파일 그대로의 미러다). 바뀌는 것은 무엇을 계획으로 볼 것인가이고, 그 판정은
    #    클라의 `hasZone`과 같다.
    plan_rows = [r for r in plan
                 if str(r["stack"] or "").strip() != "" or any(r[z] for z in ZONES)]
    doe_value_set = {r["value"] for r in plan_rows}
    unreadable_set = set(unreadable)

    for v in sorted(unreadable_set):
        warnings_out.append({
            "type": WARN_LAYER_RANGE_INVALID, "value": v, "reason": "unreadable",
            "detail": f"DOE '{v}'의 층 구조를 읽을 수 없음 — 이 값은 검증에서 제외됐다",
        })

    # ---- V1~V5 + W-DUP-MAT (공유 벡터 계약) ----
    # 차단 규칙은 계획 자체의 성질이라 stage·painted와 무관하게 판정한다: 소스를 못 물어봐서
    # 수량을 검증하지 못한 계획도 STACK이 비었는지는 말할 수 있어야 한다.
    zone_verdict = validate_zone_plan(plan_rows)
    for blk in zone_verdict["blocks"]:
        entry = {"type": WARN_ZONE_RULE_VIOLATION, "rule": blk["rule"],
                 "value": blk.get("value"), "detail": blk["message"]}
        if blk.get("zone"):
            entry["zone"] = blk["zone"]
        warnings_out.append(entry)
    for wrn in zone_verdict["warns"]:
        entry = {"type": WARN_ZONE_RULE_ADVISORY, "rule": wrn["rule"],
                 "value": wrn.get("value"), "detail": wrn["message"]}
        if wrn.get("zone"):
            entry["zone"] = wrn["zone"]
        warnings_out.append(entry)

    if not painted_reliable:
        warnings_out.append({
            "type": WARN_PAINTED_UNAVAILABLE,
            "map_status": painted_status,
            "truncated": painted_truncated,
            "cap": MAX_PLAN_VALUES if painted_truncated else None,
            "effect": "validation_skipped",
            "detail": ("대상 맵의 값 분포를 " + ("상한(%d)까지만 읽었다" % MAX_PLAN_VALUES
                       if painted_truncated else "읽지 못했다")
                       + " — 수량은 페인팅 셀 수에서 유도되므로 소요를 산출할 근거가 없다. "
                         "부족 판정을 수행하지 않았다(경고 없음 = 이상 없음이 아님)"),
        })

    # ---- DOE 값-맵 정합 ----
    # 페인팅을 못 읽었으면 이 두 경고는 **사실을 주장할 수 없다** — "칠해졌는데 정의가 없다"도
    # "정의됐는데 안 칠해졌다"도 모두 painted를 근거로 하는 단정이다.
    if painted_reliable:
        # 읽지 못한 값은 빼고 센다: 정의가 **없는** 것이 아니라 **손상된** 것이고, 그건 바로
        # 위에서 이미 말했다. 둘 다 내보내면 뒤엣것이 거짓을 말한다.
        for val in sorted(set(painted.keys()) - doe_value_set - unreadable_set):
            warnings_out.append({
                "type": WARN_UNDEFINED_DOE_VALUE, "value": val,
                "detail": f"맵에 페인팅된 값 '{val}'({painted[val]}칩)의 DOE 정의가 없음",
            })
        for val in sorted(doe_value_set - set(painted.keys())):
            warnings_out.append({
                "type": WARN_DOE_VALUE_UNPAINTED, "value": val,
                "detail": f"DOE '{val}'가 맵에 페인팅되지 않음 (수량 0)",
            })

    # ---- 수량 부족 + 소스 fail 경고 (소스 가용은 (lot,slot)당 1회 캐시) ----
    summary_cache = {}
    bp_snapshot = None
    if stage_cfg is not None and stage_cfg.get("source_config_ref") in M1_SOURCE_REFS:
        import bonding_plan
        bp_snapshot = bonding_plan.load_bonding_plan_config()  # 작업 경계 1회 스냅샷

    def _get_summary(s_lot, s_slot):
        """(lot, slot)당 1회. **실패도 캐시한다** — 안 그러면 계속 실패하는 소스가
        수요마다 재조회되어, 팬아웃이 큰 계획에서 실패 비용이 수요 수만큼 곱해진다.
        반환: (요약 dict, 오류|None)."""
        key = (s_lot, s_slot)
        if key not in summary_cache:
            try:
                summary_cache[key] = (get_stage_source_summary(
                    db, cfg, stage_name, s_lot, s_slot, bp_config=bp_snapshot), None)
            except Exception as e:
                logger.warning("[TransferPlan] source summary failed for (%s,%s): %s",
                               s_lot, s_slot, e)
                summary_cache[key] = (None, e)
        return summary_cache[key]

    # [QA F1] 수량 검증이 실제로 수행됐는지 추적한다 — "검사 안 함"이 "이상 없음"으로
    # 읽히는 것이 이 API의 최대 위험이다(스킵을 침묵으로 두지 않는다).
    any_doe_checked = False
    # [QA F4/B1] (lot, slot) → {required 누계, available, demands 건수, labels[]}
    # ⚠️ `demands`(건수)와 `labels`(표시)는 **다른 것**이다. 예전에는 라벨 집합의 크기로
    # 합산 판정을 게이트했는데, `seq` 중복으로 두 수요가 한 라벨이 되면 `len < 2`가 되어
    # 초과배정 검사가 통째로 꺼졌다(required는 이미 합산돼 있는데도 조용히 통과).
    source_alloc = {}
    truncations = []    # [(role, cap)] — 어떤 상한에 걸렸는지 각각 보고한다
    # [relaxation marker — QA B1] 판정에 실제로 쓰인 가용 수치가 **어떤 감산 없이** 계산됐는지.
    # 이름·모양은 슬롯/로트/M1 요약과 **동일하다**(역할명 리스트, 비면 필드 자체가 없다) —
    # 한 어휘를 두 철자로 나누면 소비자가 두 번 배워야 한다.
    # ⚠️ 이 필드는 판정을 바꾸지 않는다. 미선언은 감춰진 데이터가 아니라 "그 표를 두지
    #    않는다"는 사이트의 선언이고, 그것이 사이트가 가진 최선의 지식이다(총괄 확정
    #    2026-08-04). 그래서 `remaining_reliable`도 `status`도 건드리지 않고, 대신
    #    **무엇을 빼지 않았는지**를 말한다 — 총량이 순량 행세를 하는 침묵만 막는다.
    inactive_subtractions = []

    if stage_cfg is not None and painted_reliable:
        # [zone] 구역 → 수요(demand) 전개. 수량은 **저장돼 있지 않고 여기서 유도된다**:
        #   layers = 그 구역이 덮는 층 수 · total = painted(값) × layers
        #   share  = ceil(total / 그 구역의 자재 수)
        # 산술은 `zone_demand` **하나**가 한다 — 이 루프가 자기 나름의 곱셈을 다시 쓰면
        # 저장은 ceil, 표시는 round여서 DB 34 / 화면 33이었던 그 자리가 다시 열린다.
        # 같은 자재가 여러 구역·여러 값에 걸쳐 있으면 아래 source_alloc이 자연히 합산한다.
        demands = []   # (값, source_lot, source_slot, required, label, 자재 원문)
        stop = False
        # [자재 정체] 분해는 **공유 계약의 토큰 문법**(`parse_material_token`)이 한다:
        #   토큰 ::= lot["_"slot][":"BIN]
        # ⚠️ `plan_store.material_identity`는 **게이트로 남고 파서로는 쓰이지 않는다.** 이유:
        #    ① 클라는 config를 읽지 못하므로 그 규칙은 한쪽에만 사는 규칙이고, 한쪽에만 사는
        #       규칙은 흘러간다 — 그리고 갈리는 순간 한 화면에 두 개의 가용치가 생긴다.
        #    ② `_split_material`(마지막 `_` 기준)은 `ADFE1H_01:3`을 슬롯 `01:3`으로 읽어
        #       존재하지 않는 슬롯을 물어보고 **멀쩡한 자재에 대해 확신에 찬 0**을 낸다.
        #    선언 자체는 여전히 필요하다: 미선언이면 이 배포의 자재 문자열이 lot/slot 모양
        #    이라는 근거가 없으므로 아무것도 조회하지 않고 그렇게 말한다(아래).
        #    ↪ 후속 판단 필요: `separator`/`compose` 값이 이제 파싱에 쓰이지 않으므로,
        #      이 키를 은퇴시킬지 재정의할지는 총괄 결정 사항이다(경계 계약 — /stages 노출).
        material_rule = _material_identity_rule(cfg)
        # 구역은 행당 정확히 셋이라 `MAX_BANDS_PER_PLAN` 계열의 폭주가 구조적으로 없다
        # (행 수는 이미 MAX_DOE_PER_PLAN으로 묶여 있다). 남는 팬아웃 축은 **자재 수**뿐이다.
        for zone_row in plan_rows:
            if stop:
                break
            v = zone_row["value"]
            painted_cells = int(painted.get(v, 0))
            for z in ZONES:
                if stop:
                    break
                materials = list(zone_row[z])
                if not materials:
                    continue        # 그 구역에 자재가 없다 — V1이 필요하면 이미 말했다
                d = zone_demand(zone_row, z, painted_cells)
                label_prefix = f"{v}[{ZONE_LABEL[z]}]"
                if d["layers"] == 0:
                    # 층이 0이면 소요도 0이다. STACK을 못 읽어서 0인 경우는 V5가 이미
                    # 차단했고, 구역이 진짜 0층인 경우(STACK 2 + 1H·TOP의 MID)는 정상이라
                    # 경고할 것이 없다 — 어느 쪽이든 여기서 지어낼 수요가 없다.
                    # Marker rows (STACK 0) land here too: `zone_layers` returns [] for
                    # every zone by construction, so a marker's materials are never
                    # resolved, queried, or demanded — V6 already named the contradiction.
                    continue
                if len(materials) > MAX_SOURCES_PER_DOE:
                    materials = materials[:MAX_SOURCES_PER_DOE]
                    truncations.append(("materials", MAX_SOURCES_PER_DOE))
                    # 절단하면 분모가 달라져 share가 틀리므로 다시 계산한다.
                    d = zone_demand(dict(zone_row, **{z: materials}), z, painted_cells)
                for mat in materials:
                    if len(demands) >= MAX_DEMANDS_PER_PLAN:
                        truncations.append(("demands", MAX_DEMANDS_PER_PLAN))
                        stop = True
                        break
                    if material_rule is None:
                        # 미선언 = 이 배포의 자재 문자열을 소스로 볼 근거가 없다. 추측해서
                        # 조회하지 않고, 검증하지 않았다고 말한다(구 동작과 동일한 취지).
                        warnings_out.append({
                            "type": WARN_SOURCE_UNRESOLVED, "value": v, "material": mat,
                            "detail": (f"DOE '{label_prefix}@{mat}'의 자재를 소스(lot/slot)로 "
                                       f"해석할 수 없음 — plan_store.material_identity 규칙이 "
                                       f"선언되지 않았다 — 수량 검증 불가"),
                        })
                        continue
                    tok = parse_material_token(mat)
                    if not tok["ok"]:
                        # V4가 이미 차단 사유로 보고했다. 여기서는 **수요로 세지 않는다** —
                        # 조회할 수 없는 자재의 가용은 0으로만 보고될 수 있고, 0은
                        # "다 썼다"로 읽힌다.
                        continue
                    if tok["scope"] == "lot":
                        # 문법상 정상이다(= 그 로트 전체). 다만 `scope=lot` 가용 응답에는
                        # `chips`가 없다 — 로트 하나의 `remaining` 숫자를 지어내지 않겠다는
                        # `get_lot_bin_summary`의 결정이다. 그래서 확정 판정을 하지 않고
                        # **판정하지 않았다고 말한다.**
                        warnings_out.append({
                            "type": WARN_SOURCE_SCOPE_UNPRICED, "value": v,
                            "material": mat, "scope": "lot", "zone": z,
                            "required": d["share"],
                            "detail": (f"DOE '{label_prefix}@{mat}'는 로트 전체를 가리킨다 — "
                                       f"이 엔드포인트는 로트 전체의 가용을 확정 숫자로 내지 "
                                       f"않으므로(슬롯 합산은 배분이 아니라 충분성 판정이다) "
                                       f"필요 {d['share']}에 대한 부족 판정을 수행하지 않았다"),
                        })
                        continue
                    demands.append((v, tok["lot"], tok["slot"], d["share"],
                                    f"{label_prefix}@{mat}", mat))

        # [팬아웃] 조회 비용은 수요 수가 아니라 **서로 다른 소스 수**를 따라 자란다.
        # 여기서 묶지 않으면 손상된 blob 하나가 수만 건의 소스 요약을 유발한다.
        for (v, s_lot, s_slot, required, label, mat) in demands:
            # `parse_material_token`이 scope=slot으로 통과시킨 것만 여기 온다 — lot·slot이
            # 둘 다 비어 있지 않음은 그 문법이 이미 보장한다(빈 쪽은 거기서 거부됐다).
            if ((s_lot, s_slot) not in summary_cache
                    and len(summary_cache) >= MAX_SOURCES_PER_PLAN):
                truncations.append(("distinct_sources", MAX_SOURCES_PER_PLAN))
                break
            summary, err = _get_summary(s_lot, s_slot)
            if err is not None:
                warnings_out.append({
                    "type": WARN_SOURCE_UNRESOLVED, "value": v,
                    "detail": f"DOE '{label}' 소스({s_lot},{s_slot}) 가용 조회 실패",
                })
                continue

            chips_block = summary.get("chips") or {}

            # [QA F1] 강등된 가용치로 "부족 아님"을 판정하지 않는다 — 오염된 remaining은
            # 과대이므로 qty_shortage가 발화하지 않아 안전망이 조용히 무너진다.
            if not chips_block.get("remaining_reliable", True):
                degraded_roles = [w.get("role") for w in (summary.get("warnings") or [])
                                  if (w.get("type") == WARN_SOURCE_DEGRADED
                                      and w.get("effect") in (EFFECT_REMAINING_OVERSTATED,
                                                              EFFECT_TOTAL_UNKNOWN))
                                  # [7c] untracked도 판정 불가 사유를 이름으로 말한다
                                  or w.get("type") == WARN_TRANSFER_UNTRACKED]
                ub = chips_block.get("remaining_upper_bound")
                warnings_out.append({
                    "type": WARN_AVAILABILITY_UNRELIABLE, "value": v,
                    "required": required,
                    "degraded_roles": degraded_roles,
                    "remaining_upper_bound": ub,
                    "detail": (f"DOE '{label}' 수량 검증 **판정 불가** — 소스({s_lot},{s_slot})의 "
                               f"역할 강등({', '.join(degraded_roles) or '알 수 없음'})으로 가용치를 "
                               f"신뢰할 수 없음. 필요 {required}"
                               + (f", 가용 상한 {ub}(실제는 이보다 작음)" if ub is not None else "")),
                })
                continue   # 부족/fail 판정 모두 생략 — 오염값 기반 판정 금지

            any_doe_checked = True
            available = int(chips_block.get("remaining") or 0)
            # [QA B1] `available`이 방금 판정에 들어갔다 — 그 수가 어떤 감산 없이 나온
            # 것이라면 여기서 이름을 모은다. 수집 지점이 **게이트 통과 후**인 것은 의도적이다:
            # 판정 불가로 건너뛴 소스의 수치는 아무 판정에도 쓰이지 않았으므로 이 목록은
            # "지금 내가 내는 판정이 딛고 선 수치"만 서술한다.
            for r in (summary.get("inactive_subtractions") or []):
                if r not in inactive_subtractions:
                    inactive_subtractions.append(r)
            # [QA F4] 소스별 합산 누적 — DOE 단독 판정만으로는 분할 초과배정을 못 잡는다.
            # [B1] **건수와 표시 이름을 분리한다.** 합산 판정의 게이트는 `demands`(실제 수요
            # 건수)여야 하며 `labels`(사람이 읽는 목록)의 크기여선 안 된다 — 라벨은 중복될 수
            # 있고, 중복되는 순간 게이트가 꺼져 required는 합산됐는데 검사는 건너뛰게 된다.
            acc = source_alloc.get((s_lot, s_slot))
            if acc is None:
                acc = source_alloc[(s_lot, s_slot)] = {
                    "required": 0, "available": available, "demands": 0, "labels": []}
            acc["required"] += required
            acc["demands"] += 1
            if label not in acc["labels"]:
                acc["labels"].append(label)

            if required > available:
                warnings_out.append({
                    "type": WARN_QTY_SHORTAGE, "value": v, "demand": label,
                    "required": required, "available": available,
                    "detail": (f"DOE '{label}' 수량 부족: 필요 {required} > "
                               f"소스({s_lot},{s_slot}) 가용 {available}"),
                })

            fb = chips_block.get("fail_breakdown") or {}
            fail_total = sum(int(n or 0) for n in fb.values())
            if fail_total > 0 and not any(
                    w.get("type") == WARN_SOURCE_FAIL_CHIPS and w.get("value") == v
                    and w.get("source") == f"{s_lot}|{s_slot}" for w in warnings_out):
                warnings_out.append({
                    "type": WARN_SOURCE_FAIL_CHIPS, "value": v,
                    "source": f"{s_lot}|{s_slot}",
                    "fail_breakdown": fb,
                    "detail": f"DOE '{v}' 소스({s_lot},{s_slot})에 fail 칩 {fail_total}개 "
                              f"({', '.join(f'{k}:{n}' for k, n in fb.items())})",
                })
            for w in (summary.get("warnings") or []):
                if w.get("type") in (WARN_SOURCE_DEGRADED, WARN_RESULT_TRUNCATED,
                                     WARN_TRANSFER_UNTRACKED):
                    continue   # 강등/절단/untracked는 availability_unreliable로 이미 다뤘다
                entry = {
                    "type": WARN_SOURCE_HISTORY_FAIL, "value": v,
                    "source": f"{s_lot}|{s_slot}",
                    "detail": f"DOE '{v}' 소스({s_lot},{s_slot}) 이력 경고: {w.get('detail')}",
                }
                if entry not in warnings_out:
                    warnings_out.append(entry)

        # [QA F4] 소스별 합산 초과배정 — DOE를 따로 보면 각각은 가용 이하인데 합이 넘는 경우.
        # DOE 계획의 정상 형태(한 소스를 여러 조건군이 나눠 씀)라 가장 흔한 초과 형태다.
        # 단독 DOE만 쓰는 소스는 qty_shortage가 이미 정확히 같은 사실을 말하므로 제외한다.
        for (s_lot, s_slot) in sorted(source_alloc.keys(), key=lambda k: (str(k[0]), str(k[1]))):
            acc = source_alloc[(s_lot, s_slot)]
            # [B1] 게이트는 **수요 건수**다. 라벨 수로 세면 `seq` 중복 하나가 검사를 끈다.
            if acc["demands"] < 2 or acc["required"] <= acc["available"]:
                continue
            warnings_out.append({
                "type": WARN_SOURCE_OVERALLOCATED,
                "source_lot": s_lot, "source_slot": s_slot,
                "required_total": acc["required"], "available": acc["available"],
                "demand_count": acc["demands"],
                "doe_values": list(acc["labels"]),
                "detail": (f"소스({s_lot},{s_slot}) 합산 초과배정: 수요 {acc['demands']}건"
                           f"({', '.join(acc['labels'])})의 필요 합계 {acc['required']} > 가용 "
                           f"{acc['available']} — 개별 수요는 각각 가용 이하라 "
                           f"{WARN_QTY_SHORTAGE}로는 잡히지 않는다"),
            })

    # [QA F1] 실제로 **한 건이라도 판정에 도달**했을 때만 검증했다고 말한다. 빈 계획도,
    # stage 미유도도, painted 미확보도, 전 수요가 해석 불가·강등인 경우도 전부 여기서
    # unverified로 떨어진다 — "검사 안 함"이 "이상 없음"으로 새는 경로를 한 줄로 막는다.
    #
    # 구조 거부는 **한 건이라도 있으면** 계획 전체를 내린다. `to`가 비었거나 역전된 것은
    # 정상적인 편집 중 상태라 다른 구간의 검증까지 무효로 만들지 않지만(그 구분은 의도적이다),
    # 저장된 blob이 계약의 모양이 아니라면 우리가 나머지를 읽은 방식도 신뢰할 근거가 없다.
    availability_checked = any_doe_checked and not structural_refusal

    # 계획을 끝까지 읽지 못했으면 통과 판정의 근거가 없다 — **어느 상한에 걸렸는지 각각**
    # 보고한다. 하나로 뭉치면 진단이 거짓말을 한다(자재를 64에서 자르고 "구간 2000"이라 보고).
    if rows_truncated:
        truncations.append(("plan_registry", MAX_DOE_PER_PLAN))
    seen_trunc = set()
    for (role, cap) in truncations:
        if role in seen_trunc:
            continue
        seen_trunc.add(role)
        availability_checked = False
        warnings_out.append({
            "type": WARN_RESULT_TRUNCATED,
            "role": role, "cap": cap,
            "effect": "validation_skipped",
            "detail": (f"'{role}'가 상한({cap})에 걸려 계획을 끝까지 전개하지 못했다 — "
                       f"읽지 못한 부분은 검증되지 않았으므로 경고가 없다고 이상이 없는 것이 아니다"),
        })

    # [QA F1] status는 "검사 안 함"과 "이상 없음"을 절대 같은 값으로 내지 않는다.
    if not availability_checked:
        status_out = "unverified"
    elif warnings_out:
        status_out = "warnings"
    else:
        status_out = "ok"

    out = {
        "ref_table": ref_table,
        "map_key": map_key,
        "stage": stage_name,
        "map_status": painted_status,
        # [M2.6] DOE 조건의 수 = **구간을 가진 값의 수**. 색만 지정된 legend 행은 세지 않는다.
        "doe_count": len(doe_value_set),
        "painted_values": {k: painted[k] for k in sorted(painted.keys())},
        "status": status_out,
        "availability_checked": availability_checked,
        "warnings": warnings_out,
    }
    if inactive_subtractions:
        # [relaxation marker — QA B1] 전 역할이 선언된 config의 응답은 **한 바이트도**
        # 달라지지 않는다(목록이 비면 필드가 없다). 완화된 사이트에서만, `ok`라는 판정이
        # 어떤 감산 위에서 내려진 것인지 소비자가 읽을 수 있게 한다.
        out["inactive_subtractions"] = inactive_subtractions
    return out
