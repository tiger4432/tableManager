# R&D Trends and Composite CHIP reverse trace

## 현상

새 조사 화면은 여러 불량 Trend 그래프와 표를 상호 마킹해야 했지만, 기존 `/lots`는
offset 표 계약이고 차트 series·안정 웨이퍼 identity를 함께 주지 않았다. 또한 현행
`transferred` 72,485건을 실측하니 모든 예시의 `position`이 null이고 final CHIP/component
키가 없어, Bonding→여러 DT→여러 Core를 한 선형 여정으로 읽을 수 없었다.

## 근본원인

- Trend 표시 예산과 도메인 cardinality를 분리한 읽기 계약이 없었다.
- 관측 원자에는 finding이 있지만 clean scan 분모는 없으므로 발생률을 원장 관측만으로
  계산하면 미검사를 0으로 바꾸게 된다.
- 기존 transfer fixture는 wafer→DT→package 이동을 말하지만 final CHIP의 10+ component,
  layer/role, 위치, 여러 DT 경로를 식별할 payload가 없었다.

## 해결

- `GET /api/ledger/trends`: 종류/subtype/series를 가변 배열로 제공하고, 차트 점과 표 행에
  같은 stable `WaferLeg{wafer,bonding_leg}` mark key를 싣는다. 표는 composite keyset cursor, series는 DB측 deterministic
  stride로 제한한다. 기본 90d·최대 366d 창을 명시한다.
- `found_rate`는 가짜 수치 대신 `state=absent`와 분모 부재 사유를 낸다.
- `GET /api/ledger/composition`: component별 ordered transfer path와 전체 many-to-many DAG,
  모든 참여 DT, Core type/role/source, bonding layer/position, 해소 상태와 process evidence를
  분리해 제공한다.
- `seed_syn_composite_chip.py`: final CHIP 2개 × 12층, Core type 3종, CHIP당 DT lot 4종 이상,
  DT-A→DT-B 경로, resolved/candidate/unresolvable 사례를 54개 `transferred` 원자로 추가했다.
  재실행은 54개 전량 dedupe됐다. 새 술어·DDL·구 그래프 저장소는 만들지 않았다.

## 검증

- `pytest server/tests/test_ledger_trends.py server/tests/test_ledger_composition.py`:
  **12 passed**.
- 라이브 Trend 30d / max_points=5: 4 series 모두 정확히 5점, 표 cursor page 동작.
- 라이브 composition `SYN-CHIP-DEFECT-001`: component 12, DT collection 15,
  Core type 3, multi-DT component 3, 상태 셋 전부 확인.
- 데이터 적재 1회: inserted 54. 즉시 재실행: inserted 0 / deduped 54.

## 후속: 공정 비교 근거와 final wafer resolver

- `/composition`의 `upstream_process.events[]`가 `processed_with`의 step/family,
  equipment, recipe, actual/setpoint parameter, 원 payload와 evidence ID를 보존한다.
- Core branch와 `has_wafer`/`derived_from` 다중 lineage를 component별로 보존한다.
- bond-layer의 명시적 `bond_wafer`만 사용해 `final_subject_resolution`을
  `resolved|contested|absent`로 답한다. SYN answer-key/cause 태그는 읽지 않는다.
- Trends/composition/SYN-CX 집중 테스트: **24 passed**.

## 2026-08-15: Universal marking과 정확한 clean 분모

- `POST /api/ledger/selection/resolve`가 Universal Mark의 `entity_set/time_range/map_cells`
  를 `id/groupId` 손실 없이 FinalChip 후보와 원장 evidence로 해소한다. map cell은 등록된
  frame table/mapId와 source row의 정확 좌표가 모두 맞을 때만 wafer/material을 얻는다.
- 응답 top-level 및 selection별 `maps[]`는 Bond/DT/Core frame metadata와
  valid-die/process/used/supply-material/void-defect layer를 제공한다. 좌표계 start/Y 방향/
  rotation은 metadata를 그대로 보존한다.
- Process 비교는 exact schema cluster, common spans, repeat/order/insert/delete/substitution/
  schema-branch/ambiguous-order/record-absent 차이와 evidence를 제공한다.
- Process/context facet과 sequence cluster/difference에 실제 Final Bond Wafer mark와 facet별
  evidence를 추가해 비교 리스트 클릭→Trend 새 색 역마킹을 추가 SQL 없이 지원한다.
- 범주형 Surprise는 0.5-smoothed log-odds raw effect에 coverage/reliability를 곱하고,
  mechanism gate는 별도 필드로 유지한다. 미연결은 0이 아니라 `unknown`이다.
- Trend는 등록된 inspection method의 `inspection_run`을 분모로 사용한다. 발견 없는
  scanned wafer만 `scanned_clean` 0이고 numerator/denominator를 함께 낸다.
- Trend 응답은 CONFIG 등록부의 전체 `selectable_finding_kinds[]`와 실제
  `applied_kinds[]`를 분리한다. 명시적 빈·미등록·비활성 선택은 SQL 전에 거절한다.
- 종류 추가 절차와 검증된 SQL template 계약을 `TREND_DECLARATION_GUIDE.md`에 문서화했다.
- Trend 응답에 `trace_dimensions[]`와 행별 `traceability.{dt,core}`를 추가했다. Final Bond
  Wafer의 명시적 transferred component만 분모로 삼고 page wafer+시간창으로 유계화한다.
- SYN-CX 라이브 응답에서 6 Base WF × 2 LEG = 12 analysis unit, found 6/scanned_clean 6, Core ready 12,
  DT partial 12를 확인했다.
- 집중 테스트 **50 passed**, 라이브 PostgreSQL에서 Trend와 SYN-CX selection/trace SQL 실행 완료.

## 2026-08-15: Base WF + Bonding LEG grain 승격

- vocabulary에 별도 issued subject `WaferLeg` exact keys `{wafer,bonding_leg}`를 추가했다.
  기존 `Wafer` identity에 undeclared key를 끼우지 않았다.
- collision-free mark는 `wafer-leg:v1:` + canonical JSON 배열의 unpadded base64url이며
  Trend cursor v2는 `(occurred_at,wafer,bonding_leg)`를 보존한다.
- inspection denominator는 `(base_wafer_id,base_x,base_y)`를
  `bonding_map(base,x,y,leg)`에 정확 결합한다. Wafer-only 관측은 LEG로 fan-out하지 않는다.
- selection response를 schema v4로 올리고 legacy Wafer-only mark는
  `legacy_wafer_requires_bonding_leg`로 명시 거절한다. map projection과 defect layer도 LEG별로
  격리했다.
- `WaferLeg processed_with` FINAL_BOND 이벤트를 Core component event와 분리했다. 따라서
  LEG 조건에 Core type/branch가 cross-product되지 않고 분석단위 분모를 사용한다. sequence도
  component sequence와 analysis-unit sequence를 분리해 한 unit event가 layer 수만큼 복제되지 않는다.
- 라이브 12-unit A/B 검증에서 top physics Surprise는 FINAL_BOND
  `pressure_MPa=0.55` 대 `0.90`, 분모 6/6, mark 6/0, `void_formation/pass`였다.
- focused selection/trend/vocabulary 테스트 **110 passed**.

## 남은 공백

- 일반 생산 transfer 원자는 position/final component identity가 없어 새 composition 계약이
  `empty`를 답한다. 실 피드가 같은 payload를 발화하기 전 SYN 이외 reverse trace는 불가하다.
- final CHIP defect observation을 bonding layer/component로 공간 귀속하는 실측 bridge는 아직
  없다. 구성 trace와 defect/no-defect Trend는 연결 키가 생길 때까지 별도 증거로 남는다.
- JSON payload 경로 질의는 시간 파티션으로 유계화했지만 전용 expression index/rollup이 없다.
  10M 규모 전에는 실제 workload로 인덱스 가격을 재고 문서화해야 한다.
