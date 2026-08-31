# Trend Declaration Guide

> 🗄️ **SUPERSEDED — 이 문서가 가르치는 라우트·주어 타입·술어가 «전부» 없습니다** (2026-08-29 실측).
> **Status:** 🗄️ Archived | **Last-verified:** 2026-08-29 | **Owner:** Server / Ledger
>
> 무엇이 사라졌나 — `GET /api/ledger/kinds` · `GET /api/ledger/trends` (라우트 둘 다 없음) ·
> `server/finding_kinds.py` / `server/ledger_api/finding_kinds.py` (모듈 없음) ·
> `server/config/finding_kinds.json` (선언 없음) · 주어 타입 `WaferLeg`(선언 안 됨 — `observed@1` 의
> 주어는 `die@1` 하나다) · 술어 `transferred`(선언 안 됨 — 살아 있는 철자는 `transfer@1`).
> §5 의 인덱스 처방 둘은 **어느 원자도 갖지 않는 술어** 위의 부분 인덱스입니다.
>
> 🔴 **여기 적힌 절차를 그대로 따르면 전부 실패합니다.** 오늘 「선언으로 무엇을 늘리나」의
> 정본은 [ONTOLOGY_LEDGER_SETUP](../guide/ONTOLOGY_LEDGER_SETUP.md)(작성) ·
> [LEDGER_GUIDE](../guide/LEDGER_GUIDE.md)(운영) · [PRIMER](../guide/ledger/PRIMER.md)(입문)이고,
> 읽기 라우트의 정본은 [backend §2](../architecture/backend.md) 입니다(**여기에 수를 적지 않습니다** — 이 자리의 「둘뿐」이 2026-08-31에 거짓이 됐습니다).
>
> **살아남는 원리 둘**(다시 쓸 때 여기서 가져갈 것) — ① **§7 「거절은 이름을 댄다」**:
> 미선언·비활성 선택은 조용한 빈 답이 아니라 이름을 댄 422 여야 한다(오늘의 `follow` 가
> 그 규율의 상속자다). ② **§5 「사용자 SQL 은 없다」**: 선언은 값만 bind 하고 SQL 조각을
> 싣지 않는다. 나머지는 **역사 기록**으로만 읽으십시오.
>
> ⚠️ **`docs/_archive/` 이관은 총괄 판정 대상입니다** — 이 레인은 배지만 바꿉니다.

---

> **[아래는 2026-08-15 시점의 서술이며 현재 상태가 아닙니다.]**
> **Status(당시):** Living | **Owner:** Server / Ledger | **Contract:** declaration → validation → parameterized template

## 1. 목적

Trend 항목은 화면이나 라우터의 조건문으로 추가하지 않는다. 사용자가 관리하는
`server/config/finding_kinds.json` 선언을 `server/finding_kinds.py`가 검증하고, 서버가 준비한
유계 SQL template에 값만 bind한다. 선언에 SQL 문자열, JOIN, WHERE 조각을 넣어 실행하는 기능은
제공하지 않는다.

정본 흐름은 다음과 같다.

```text
finding_kinds.json
  → finding_kinds.load() 구조/식별자 검증
  → GET /api/ledger/kinds 선택 목록
  → GET /api/ledger/trends?kinds=... 적용 목록 검증
  → 서버 소유 SQL template + bound parameters
```

## 2. 선언 필드

각 top-level key가 `finding_kind`의 stable ID다.

| 필드 | 필수 | 의미 |
|---|---:|---|
| `label` | 예 | UI 표시명. identity로 사용하지 않는다. |
| `active` | 아니오 | 기본 `true`. `false`면 catalogue에는 남지만 기본/명시 선택은 거절한다. |
| `observed_by` | 예 | 이 종류를 찾는 `inspection_run.method` allowlist. 정확한 denominator 정의다. 빈 배열은 분모가 없다는 명시적 상태다. |
| `observation_table` | 예 | 관측 source table의 plain identifier. translator/catalogue가 사용하며 임의 SQL은 허용하지 않는다. |
| `extent_columns` | 예 | 관측 크기를 말하는 source column 이름 목록. 빈 목록은 거절한다. |
| `unit_column` | 아니오 | source가 단위를 발화하는 column. UI label이나 단위 추측에 쓰지 않는다. |
| `classes` | 아니오 | subtype/dimension의 닫힌 집합. 빈 배열은 subtype 축이 없다는 선언이다. |

Trend의 subject identity는 원장 `observed` atom의 정식 `WaferLeg`와 exact keys
`{wafer,bonding_leg}`다. 같은 Base WF라도 LEG가 다르면 별도 분석 단위다. 응답은
`{type:"WaferLeg", keys:{wafer,bonding_leg}, mark_key:"wafer-leg:v1:..."}`를 차트와 표에
똑같이 싣는다. mark suffix는 canonical UTF-8 JSON 배열
`["WaferLeg",wafer,bonding_leg]`의 unpadded base64url이며 strict decode/재인코딩으로
충돌을 막는다. label, LOT 이름, 문자열 concat, 좌표 유사도로 mark를 만들지 않는다.

시간축은 `ledger_events.occurred_at`이며 관측 번역 시 `inspection_run.observed_at`에서 온다.
source row의 적재/수정 시각을 관측 시각으로 대체하지 않는다.

## 3. 지표와 clean 의미

| 지표 | 정의 |
|---|---|
| `event_count` | 유계 시간창의 `observed` atom 수 |
| `found_chip_count` | payload의 선언된 die/position identity distinct 수 |
| `scan_denominator` | 같은 wafer+LEG와 finding kind에 대해 `observed_by` method가 일치한 `inspection_run` 행 수. LEG는 정확 좌표의 `bonding_map`에서 얻는다. |
| `found_rate` | `found_chip_count / scan_denominator`. 분모가 없으면 null/absent이며 임의 모집단을 쓰지 않는다. |

`scanned_clean`은 `inspection_run`에는 있으나 관측 numerator가 0인 wafer+LEG만 해당한다.
관측 행이 없다는 사실만으로 clean을 만들지 않는다. 스캔 증거가 없으면 `no_denominator`이며
0으로 표시하지 않는다. subtype은 `classes` 선언과 atom payload의 `class`가 함께 있을 때만
별도 series가 된다.

## 4. 선택 API

`GET /api/ledger/kinds`는 선언된 종류를 데이터 유무와 관계없이 모두 제공한다.
`GET /api/ledger/trends`는 다음 선택 계약을 함께 반환한다.

```json
{
  "selectable_finding_kinds": [
    {
      "id": "void",
      "label": "보이드",
      "active": true,
      "selectable": true,
      "subject_type": "WaferLeg",
      "subtypes": [],
      "series": [{"id": "void:all", "subtype": null, "label": "전체"}],
      "metrics": [
        {"id": "event_count", "state": "ready"},
        {"id": "found_chip_count", "state": "ready"},
        {"id": "found_rate", "state": "ready",
         "numerator": "found_chip_count", "denominator": "scan_denominator"}
      ]
    }
  ],
  "applied_kinds": ["void"]
}
```

`kinds` query가 없으면 active 선언 전체를 적용한다. `kinds=void,delam`은 그 종류만 적용한다.
명시적 빈 선택, 미등록 ID, 비활성 ID는 SQL 실행 전에 422로 거절한다. `limit`과
`max_points`는 표시 예산일 뿐 종류 cardinality 제한이 아니다.

## 5. SQL 안전 계약

서버 template은 두 bounded source를 조립한다.

```sql
WITH declared(kind, method) AS (
  SELECT kind, method
  FROM jsonb_to_recordset(:kind_methods::jsonb) AS d(kind text, method text)
),
scans AS MATERIALIZED (
  SELECT r.base_wafer_id AS wafer, bm.leg::text AS bonding_leg, d.kind,
         max(r.observed_at) AS scan_at, count(*) AS scan_denominator
  FROM inspection_run r
  JOIN bonding_map bm ON bm.base=r.base_wafer_id
                     AND bm.x=r.base_x AND bm.y=r.base_y
  JOIN declared d ON d.method = r.method
  WHERE r.observed_at >= :from AND r.observed_at < :to
  GROUP BY r.base_wafer_id, bm.leg::text, d.kind
),
observed AS MATERIALIZED (
  SELECT subject_keys->>'wafer' AS wafer,
         subject_keys->>'bonding_leg' AS bonding_leg,
         object_payload->>'finding_kind' AS kind,
         nullif(object_payload->>'class', '') AS subtype,
         occurred_at,
         coalesce(object_payload->'die', object_payload->'position') AS die
  FROM ledger_events
  WHERE subject_type='WaferLeg' AND predicate = 'observed'
    AND occurred_at >= :from AND occurred_at < :to
    AND object_payload->>'finding_kind' = ANY(:kinds)
)
SELECT ...
FROM scans FULL OUTER JOIN observed ...;
```

`:from`, `:to`, `:kinds`, `:kind_methods`, cursor, page/point budget은 모두 bind parameter다.
table identifier가 필요한 catalogue/translator 경로는 registry의 plain identifier 검사를 통과한
`observation_table` allowlist만 사용한다. 사용자 입력 SQL, column expression, JOIN fragment,
정렬문을 실행하지 않는다.

기본 창은 90일, 최대 366일이다. Trend Table은 `(occurred_at, wafer, bonding_leg)` keyset cursor와
`LIMIT`을 사용하며 OFFSET을 쓰지 않는다. series는 DB에서 deterministic stride로 줄이고
원래 wafer 수를 downsampling metadata에 남긴다.

권장 plan/index는 다음과 같다.

- `ledger_events`: 시간 partition pruning + active `subject_type='WaferLeg' AND predicate='observed'` 경로 + finding kind/wafer/LEG projection.
- `inspection_run`: `(method, observed_at, base_wafer_id, base_x, base_y)` 유계 denominator lookup.
- `bonding_map`: exact `(base,x,y)` lookup과 반환 `leg`. LEG 문자열을 추측하거나 inspection row에 가상 컬럼을 만들지 않는다.
- observation source: `run_uid` join index. extent 조건을 추가할 때만 선언된 expression index를 별도 검토한다.
- 배포 전 `EXPLAIN (ANALYZE, BUFFERS)`로 실제 기간/종류 수를 측정한다. 10M 행에서 JSON payload scan이 비싸면 검증된 expression index 또는 materialized read model을 추가하되 계약은 유지한다.

## 6. 새 finding 추가 예시

예를 들어 `crack`을 AOI가 검사하고 source가 `crack_obs`라면 다음과 같이 선언한다.

```json
{
  "crack": {
    "label": "크랙",
    "active": true,
    "observed_by": ["aoi"],
    "observation_table": "crack_obs",
    "extent_columns": ["length_um", "width_um"],
    "unit_column": "unit",
    "classes": ["edge", "center"]
  }
}
```

추가 절차는 다음과 같다.

1. source table과 `inspection_run.method='aoi'`의 identity/time 계약을 정의한다.
2. translator config가 `crack_obs → predicate='observed', finding_kind='crack'`을 선언하도록 한다.
3. `run_uid`를 통해 관측 row와 inspection denominator가 연결되는지 검증한다.
4. registry를 reload하고 `/api/ledger/kinds`에서 데이터 0건이어도 `crack`이 보이는지 확인한다.
5. `/api/ledger/trends?kinds=crack`에서 `applied_kinds`, edge/center series, numerator와 denominator를 확인한다.
6. SQL plan이 시간 조건과 인덱스를 사용하는지 확인하고 route/refusal/clean-zero 테스트를 추가한다.

종류별 CTE를 사용해야 하는 다른 분석 경로는 `finding_kinds.population_ctes("crack")`가 만드는
`kind_run → kind_finding → kind_found/kind_scanned/kind_clean/kind_unscanned` 골격을 사용한다.
핵심 식은 `clean = scanned EXCEPT found`이며 `NOT EXISTS(finding)`가 아니다.

## 7. 검증과 거절

- `label`, `observation_table`, `extent_columns` 부재: registry load 거절.
- `observed_by` key 부재: 빈 목록과 다르므로 load 거절.
- malformed `classes`: load 거절.
- plain identifier가 아닌 observation table: SQL 조립 전 거절.
- 미등록 kind: `unknown_finding_kind` 422.
- 명시적 빈 kind 선택: `empty_trend_kinds` 422.
- 비활성 kind 선택: `inactive_finding_kind` 422.
- 무계/366일 초과 기간, 잘못된 cursor/limit/max_points: 422.
- relation 부재는 거짓 0이 아니라 `state: absent`이며 선언 목록은 유지한다.

화면은 `selectable_finding_kinds`로 selector/series/metric label을 만들고,
`applied_kinds`로 실제 질문을 표시해야 한다. 코드에 `void` 전용 카드나 고정 Trend 개수를
두지 않는다.

## 8. DT/Core Trace 열

Trend 응답의 `trace_dimensions[]`가 추적 열을 선언한다. 현행 선언은 `dt_trace`와
`core_trace`이며 각 항목은 label, `ontology_path`, 허용 상태
`ready|partial|absent`를 가진다. UI는 열 이름과 상태를 하드코딩하지 않는다.

각 Trend Table 행은 다음 근거를 포함한다.

```json
{
  "traceability": {
    "dt": {"state": "partial", "count": 11, "component_denominator": 12,
           "evidence_ids": ["evidence:..."]},
    "core": {"state": "ready", "count": 12, "component_denominator": 12,
             "evidence_ids": ["evidence:..."]}
  }
}
```

분모는 Final Bond Wafer+LEG로 명시 귀속된 `transferred` component 수다. Core count는 그
component가 실제 source Wafer subject를 가진 수, DT count는 같은 component의 유계 transfer
event에 선언된 `dt_slot`/`dt_lot` 증거가 있는 수다. count=분모면 ready, 0<count<분모면
partial, 증거 0이면 absent다. Final component transfer 자체가 없으면 분모 0과
`final_component_transfer_absent`를 반환한다. finding 부재를 trace 부재나 clean으로 바꾸지 않는다.

추적 SQL은 Trend page가 확정된 뒤 그 page의 `{wafer,bonding_leg}` JSON recordset과 동일
시간창에만 실행한다. 첫 단계는 `predicate='transferred'`에서
`to.keys.base_wafer_id`와 `to.keys.bonding_leg`를 page unit에 정확 결합해 final
component를 찾고, 둘째 단계만 해당 stable component/final-chip ID의 transfer event를 읽는다.
사용자 입력 JSON path나 SQL fragment는 받지 않는다. 규모가 커지면 다음 expression index의
실제 비용을 `EXPLAIN (ANALYZE, BUFFERS)`로 검증한다.

```sql
CREATE INDEX ... ON ledger_events
  ((object_payload->'to'->'keys'->>'base_wafer_id'),
   (object_payload->'to'->'keys'->>'bonding_leg'), occurred_at)
  WHERE predicate = 'transferred';

CREATE INDEX ... ON ledger_events
  ((object_payload->'component'->>'final_chip_id'),
   (object_payload->'component'->>'component_id'), occurred_at)
  WHERE predicate = 'transferred';
```

인덱스는 migration과 운영 측정 없이 자동 생성하지 않는다. 응답 page 상한은 200이고,
trace query의 subject cardinality 상한도 그 page와 같다.

## 9. 호환성과 이행

`WaferLeg`는 기존 `Wafer`에 몰래 key를 추가한 것이 아니라 vocabulary에 등록된 별도 issued
subject다. `register`, `observed`, `processed_with`가 이 주어를 허용한다. 원장 identity와
keys가 JSON이므로 DDL migration은 없지만 translator/backfill은 실제 LEG 근거를 발화해야 한다.
기존 Wafer-only observation을 같은 wafer의 모든 LEG로 fan-out하면 분모와 원인을 복제하므로
금지한다. 그런 원자는 복합 Trend에서 제외되며 selection은
`unresolvable/legacy_wafer_requires_bonding_leg`를 답한다. cursor는 v2 composite payload만
받고 구 wafer-only cursor는 422다.
