# Selection comparison gets a canonical measurement contract

## 현상

`POST /api/ledger/selection/resolve`의 Measurement는 원장에 계측 원자가 있어도 항상
`measured_predicate_not_declared` 한 행만 반환했다. 반대로 Process는
`processed_with.params_actual/params_setpoint`의 모든 숫자를 후보화해 STEP/RCP 발생 비교와
물리 계측 비교를 한 범주에 섞었다. `missing`, `not_performed`, `unknown`을 숫자 없이 보존할
원장 서명도 없었다.

## 근본 원인

- 닫힌 vocabulary에는 `observed`만 열려 있고 물리량 값의 짝인 `measured`가 없었다.
- selection resolver는 `processed_with`만 조회하고 Measurement를 하드코딩된 absent로 만들었다.
- Process signature가 장비·family·actual/setpoint·parameter/value에 결합돼 있었다.
- value 목적어의 공통 `required` 검사만으로는 상태별로 value를 요구/금지할 수 없었다.

## 해결

- canonical predicate `measured`(`since:4`)를 열었다. UI의 `measured_as`는 category 이름으로만
  유지한다.
- payload 공통 필드는 `metric/unit/method/state`다. `recorded`만 `value/run_uid`를 요구하고,
  `missing/not_performed/unknown`은 `value` 키 자체를 금지한다. 이 조건은 vocabulary의
  선언형 `state_contract`를 공통 `check_signature`가 집행한다.
- selection은 시간 창과 선택된 Core Wafer/WaferLeg에 한정해 `measured`를 조회한다.
  facet은 metric signature별로 `groups[].state_counts`, 원값 `values[]`, 분모,
  WaferLeg reverse-mark key와 atom evidence ID를 보존한다. 평균·0·null sentinel은 만들지 않는다.
  선택 범위에 원자가 0개인 경우만 `absent/measured_evidence_absent`다.
- `processed_with` required를 `step/recipe`로 단순화했다. Process facet과 sequence token은
  `(step, recipe, occurrence)`만 사용하며 equipment/family/actual/setpoint/knob/value를 내지 않는다.
  기존 원자의 extra payload는 gate 호환을 위해 허용하지만 후보 계약에는 참여하지 않는다.

핵심 계약:

```python
{"predicate": "measured",
 "object_payload": {"metric": "film_thickness", "unit": "nm",
                    "method": "ellipsometry", "state": "recorded",
                    "value": 1180.0, "run_uid": "MI:..."}}

{"predicate": "measured",
 "object_payload": {"metric": "film_thickness", "unit": "nm",
                    "method": "ellipsometry", "state": "not_performed"}}
```

## 영향 범위와 사이드 이펙트

- DDL, 쓰기 저장소, Outbox, WebSocket, 클라이언트 셀 계약은 바꾸지 않았다.
- SQL 둘은 기존 selection 시간창과 요청 subject 집합을 그대로 사용해 전량 스캔/N+1을 만들지 않는다.
- component와 analysis-unit grain은 계속 분리해 WaferLeg 사건을 layer 수만큼 복제하지 않는다.
- Process 기전 numeric binding/DOE 후보는 의도적으로 폐기됐다. 수치는 Measurement만 담당한다.

## 검증

- `test_ledger_l1_unit.py + test_ledger_selection.py`: **101 passed**.
- 위 둘 + `test_syn_complex_composite.py`: **129 passed**.
- `python -m py_compile server/ledger_selection.py server/ledger/vocabulary.py`: 통과.
- 전체 `server/tests`는 약 88%까지 진행했으나 여러 비집중 실패가 누적된 상태에서 총괄 지시로
  장시간 실행을 중단했다. 따라서 전체 통과를 주장하지 않는다. selection/vocabulary/SYN
  집중 129건은 별도 실행에서 전부 통과했다.
