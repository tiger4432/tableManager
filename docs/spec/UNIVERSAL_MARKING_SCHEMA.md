# Universal Marking Schema

## 1. 목적

Trend의 시간 구간, 표의 셀, Bond/DT/Wafer 맵의 셀을 같은 `Mark`로 표현한다.
분석 단위는 Base Wafer가 아니라 `Base Wafer × BONDING LEG`다. 같은 Wafer 안의
서로 다른 DOE 구역은 공정 조건과 Core 구성이 달라도 절대 한 집단으로 합치지 않는다.
화면은 선택을 해석하지 않고, 해소기는 Mark를 원장 근거를 통해 온톨로지 주어로 투영한다.
따라서 새 차트·표·맵은 별도 비교 로직 없이 같은 그룹 비교기에 연결된다.

```text
View selection -> Mark -> evidence-backed resolution -> ontology subjects
               -> Marking Group -> process / measurement / context comparison
```

## 2. 정본 객체

```json
{
  "schemaVersion": 4,
  "id": "deterministic-mark-id",
  "groupId": "A",
  "kind": "entity_set | time_range | metric_region | map_cells | claim_filter",
  "subjectType": "WaferLeg",
  "selector": {},
  "origin": { "viewId": "void-trend", "source": "pointer" },
  "createdAt": "2026-08-14T12:00:00+09:00"
}
```

- `id`는 같은 의미의 선택이 같은 값이 되도록 정규화한 뒤 만든다.
- `groupId`는 비교 집단이다. A/B로 제한하지 않는다.
- `subjectType`은 선택 뷰가 주장하는 타입이며, 최종 CHIP 같은 후속 타입을 추측하지 않는다.
- `origin`은 재현과 설명을 위한 출처다. 판정 근거를 대신하지 않는다.

## 3. Selector

### 3.1 Entity set

```json
{
  "ids": ["wafer-leg:v1:WyJXYWZlckxlZyIsIlNZTi1DWC1CVy0wMDEiLCJIQk0tQl9MT1ctUCJd"],
  "identities": [{
    "type": "WaferLeg",
    "keys": { "wafer": "SYN-CX-BW-001", "bonding_leg": "HBM-B_LOW-P" }
  }]
}
```

표 행이나 Trend 점처럼 이미 안정 ID를 가진 선택이다. ID는 정렬·중복 제거한다.
`mark_key`는 `wafer-leg:v1:` 뒤에 canonical UTF-8 JSON 배열
`["WaferLeg", wafer, bonding_leg]`을 unpadded base64url로 인코딩한다. 해소기는 strict
decode 뒤 canonical re-encode가 원문과 같은지 확인한다. 구분자 문자열 결합은 금지한다.
`bonding_leg`는 자유 문자열이며 enum으로 제한하지 않는다.

### 3.2 Time range

```json
{
  "from": "2026-08-01T00:00:00+09:00",
  "to": "2026-08-07T23:59:59+09:00",
  "timezone": "Asia/Seoul",
  "seriesId": "void:all",
  "ids": ["wafer-leg:v1:..."]
}
```

시간 경계와 시간대를 잃지 않는다. 화면이 이미 물질화한 안정 ID는 `ids`에 보존하지만,
서버는 창과 원장 근거를 다시 대조해 응답에 해소 회계를 싣는다.

### 3.3 Metric region

```json
{
  "seriesId": "void:all",
  "metricId": "found_chip_count",
  "xFrom": "2026-08-01T00:00:00Z",
  "xTo": "2026-08-15T00:00:00Z",
  "yMin": 2,
  "yMax": 8,
  "findingKind": "void",
  "ids": ["wafer-leg:v1:..."]
}
```

차트 BBOX는 픽셀 사각형을 정본으로 저장하지 않는다. 선언된 series·metric의 X/Y 데이터 범위와 그 2차원 범위 안에서 실제로 해소된 WaferLeg IDs를 저장한다. 따라서 resize·재조회 뒤에도 같은 온톨로지 주어를 같은 색 영역으로 복원한다. X만 겹치고 Y가 범위를 벗어난 점은 선택하지 않는다.

### 3.4 Map cells

```json
{
  "frame": {
    "table": "bonding_map", "mapId": "LOT_01_03", "stage": "bond",
    "startX": 1, "startY": 1, "yInvert": false
  },
  "cells": [{
    "x": 10, "y": 12, "bondingLeg": "HBM-B_LOW-P",
    "materialId": "CORE-SUPPLY-17"
  }],
  "layer": "supply_material",
  "ids": ["wafer-leg:v1:..."]
}
```

VOID를 포함한 표준 물리 좌표는 `startX=1`, `startY=1`, `yInvert=false`다. 서로 다른 맵을 겹칠 때도 이 선언을 보존하며, 화면이 좌표 원점이나 Y 방향을 추측해서는 안 된다.

셀은 반드시 선언된 frame 안의 정수 좌표다. `mapId` 없는 좌표나 프레임을 넘는 좌표는 거절한다.
유효 다이, 공정 영역, 사용 영역, Supply 자재, 불량 레이어는 선택 출처로 보존하며 서로 대신하지 않는다.
Sorting/Supply Map의 `materialId`는 개별 Transfer 카드를 대체하는 안정 자재 ID이며 색상과 해소 근거에 사용한다.

### 3.5 Ontology claim filter

```json
{
  "predicate": "processed_with",
  "signature": {
    "step": "BOND_PREP", "equipment": "EQ-B03",
    "source": "params_actual", "parameter": "pressure_MPa", "value": 0.55
  },
  "ids": ["wafer-leg:v1:..."],
  "evidenceIds": ["evidence:ledger-atom-id"]
}
```

`claim_filter`는 대조 목록의 설비·레시피·실측값·맥락을 클릭할 때 생긴다. 화면의 행 번호가 아니라 온톨로지 술어와 값, 그 값을 발화한 근거, 근거 체인으로 해소된 주어를 가진다. `ids`는 서버가 근거로 해소한 결과이며 브라우저가 문자열을 추측해 채우지 않는다. 같은 Mark를 Trend·Table·Map에 투영하므로 어느 화면에서 시작해도 같은 WF가 같은 색으로 보인다.

## 4. 그룹 연산

- 같은 그룹의 기본 연산은 합집합이다.
- `replace`는 그 그룹만 교체하고 다른 그룹은 보존한다.
- `subtract`는 같은 안정 Mark만 제거한다.
- 그룹 비교는 각 그룹의 분모, 해소/후보/경합/해소 불가 수를 함께 표시한다.
- 빈 값은 `missing`, `not_performed`, `unknown`, `contradiction`을 합치지 않는다.

## 5. 온톨로지 해소 계약

해소기는 각 Mark마다 다음을 반환한다.

```json
{
  "markId": "...",
  "groupId": "A",
  "state": "resolved | candidate | contested | unresolvable",
  "subjects": [{ "type": "FinalChip", "id": "SYN-CX-CHIP-001" }],
  "evidenceIds": ["ledger-atom-id"],
  "path": ["WaferLeg", "Bond", "DT", "Core", "FinalChip"]
}
```

이름 유사도나 화면 위치만으로 주어를 만들지 않는다. 물리 좌표는 선언된
`bonding_map(base,x,y,leg)`를 통해서만 WaferLeg로 올라간다. 기존 `wafer:*` mark 하나를
여러 LEG로 자동 확장하지 않는다. 증거가 없으면 빈 `subjects`와 사유가 답이다.

## 6. 비교 투영

해소된 그룹은 세 패싯으로만 첫 화면에 투영한다.

- `Process`: 순서·반복·생략·recipe/equipment/actual knob의 집단 차이
- `Measurement`: 값·단위·시각·분모와 결측 상태
- `Context`: LOT/SLOT/JOB/product/transfer 및 부가 정보

첫 화면은 차이가 큰 항목과 다음 확인만 보인다. 개별 다이와 원장 행은 증거 상세에서 펼친다.

## 7. 성능 및 안전

- 브라우저는 현재 창의 ID만 보유하고 전체 원장을 스캔하지 않는다.
- 시간/공간 해소와 집계는 서버에서 bounded query로 수행한다.
- 늦은 응답은 request id와 abort signal로 폐기한다.
- Mark snapshot은 JSON 직렬화 가능하며 `schemaVersion`을 반드시 포함한다.

## 8. 놀라움과 메타 액션

### 8.1 경험적 이탈

마킹 그룹 A/B의 차이는 항목 타입에 맞게 계산한다.

- 범주/공정 발생: 0.5 평활을 둔 두 집단 log-odds 차이
- 수치/계측: 두 집단 중앙값 차이를 pooled MAD로 나눈 강건 효과크기
- 공정 순서: 동일 구간끼리 정렬한 뒤 삽입·삭제·치환·반복의 정규화 거리
- 결측: 값 차이에 섞지 않고 상태별 분모 차이로 별도 계산

표본수와 해소율을 곱해 작은 집단이나 후보 경로가 큰 놀라움으로 과장되지 않게 한다.

### 8.2 물리 온톨로지 관문

`mechanism_models.json`의 binding과 방향 경로를 인용한다.

- `pass`: 관측 필드가 물리량에 binding되고 finding까지 형성 경로가 있다.
- `observation_bias`: 발생 원인이 아니라 관측 편향 후보로 분리한다.
- `fail`: 선언된 모델에 경로가 없으므로 물리 원인 순위에서 제외한다.
- `unknown`: binding 또는 모델이 없으며 점수를 0으로 만들지 않는다.

방향만 선언된 모델에서 수치 기대값이나 안전 DOE 범위를 만들지 않는다.
화면의 `Surprise`는 경험적 이탈, 해소율, 물리 관문을 함께 표시하고 원점수를 보존한다.

### 8.3 다음 메타 액션

액션은 실행 전 제안이며, 예상 정보 이득으로 정렬한다.

- `collect_missing`: 누락/미실시/미상을 분류했을 때 분리되는 가설 수와 회복되는 분모
- `doe`: 선언된 제어 knob가 서로 다른 물리 경로의 예측을 가를 때만 제안

정보 이득은 “해당 액션 이후 줄어들 것으로 예상되는 가설 엔트로피”다.
제어 가능성·안전 범위가 선언되지 않으면 DOE 조건을 발명하지 않고 `확인 필요`로 둔다.
