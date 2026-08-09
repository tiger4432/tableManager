# DT alignment 결과를 metadata로 적재하는 체인 제안

> **상태:** S1/S2 구현됨 · S3은 Proposal  
> **작성:** 2026-08-09 / Lead PM  
> **결정 대상:** 기존 정렬 엔진의 결과를 DT frame metadata로 저장하는 첫 체인

> S1의 현행 계약은 [`../spec/DT_ALIGNMENT_METADATA_CHAIN_SPEC.md`](../spec/DT_ALIGNMENT_METADATA_CHAIN_SPEC.md)에
> 있다. 이 문서는 `dt_inventory` 항등 chain과 `dt_map replace_map`을 포함한 후속 제안만 보존한다.

## 결론

`/api/maps/alignment/view`의 **응답 계약을 그대로 사용**해 `dt_log`의 `dt_job`별 DT 정렬 결과를
`wafer_map_metadata`에 기록하고, 이를 `dt_inventory.dt_frame` JSON metadata로 승격하는 것이 가장
단순하고 재사용성이 높다.

다만 체인 워커가 HTTP로 자기 서버를 다시 호출하는 방식은 권장하지 않는다. 같은 API 응답을
만드는 읽기 전용 서비스 함수를 route와 mapper가 함께 호출하게 한다. 이렇게 하면 화면과 체인이
같은 판정 결과를 쓰면서도, 별도 HTTP 연결·별도 DB snapshot·URL JSON 인코딩·재시도 오해를
만들지 않는다.

```text
dt_log
  └─ (alignment API-equivalent, read only)
       └─ winner + placement + basis metadata
            └─ confirmed_meta_for(...)  [기존 순수 projector]
                 └─ wafer_map_metadata (target_table=dt_log, dt_job의 DT meta)
                      └─ (예정: 항등 chain) dt_inventory.dt_frame (JSON metadata)
                           └─ (예정: replace_map chain) dt_map 표준 좌표 projection
```

여기서 `wafer_map_metadata`는 `dt_log`의 `dt_job`가 가진 DT map metadata 정본이며, 화면용 임시
저장소가 아니다. map의 회전·면·시작점·물리 격자 정보를 담는다. `dt_inventory.dt_frame`은 그
완전한 JSON metadata를 `dt_job` 단위 업무 정보와 함께 보관하는 통합 projection이다. `dt_map`은
끝까지 `dt_log`에서 재생성 가능한 파생 map으로 유지한다.

## 왜 alignment API 응답을 쓰는가

기존 엔진은 이미 후보 8개 채점, `dt_index` 축 판정, 기준 valid-die map, margin/식별 die 문턱,
placement를 계산한다. 체인이 다시 프레임을 추론하면 화면에서 본 결과와 적재 결과가 갈라진다.
체인은 다음 역할만 맡는다.

1. 결정 단위의 alignment view를 요청한다.
2. 자동 확정 gate를 통과한 winner만 고른다.
3. winner의 frame과 placement를 기존 `map_alignment.confirmed_meta_for()`에 넘긴다.
4. 반환된 완전한 `grid_metadata`를 `wafer_map_metadata`에 upsert한다.

`confirmed_meta_for()`는 이미 후보 frame/placement와 기준 meta를 완전한 `grid_metadata`로
투영하는 순수 함수다. 따라서 체인에서 rotation, side, start 좌표, 물리 격자 계산식을 다시 쓰지
않는다. 기존 `frame_confirmation.record_confirmation()`은 호출하지 않는다.

## Bootstrap 자동확정 실행 계획 (proposal)

### 목표와 현 상태

SYN 표본 8개(좌상/우상 × 0/90/180/270)는 모두 `dt_index`를 갖고 PRD 기준으로
채점할 수 있다. 실측한 `SYN-TL-R0-20260809`는 `winner=rot0_tl`, `metric=index`,
`margin=80`이다. 현재 S1이 쓰지 않는 유일한 사유는 source metadata가 아직 없어
`geometry_assumed=true`인 점이다. margin 또는 discriminating-die 문턱을 낮춰도 이
사유는 바뀌지 않는다.

### 제안: 명시적 reference-geometry bootstrap 정책

일반 gate의 `geometry_assumed == false`는 기본으로 유지한다. 다만 chain rule이 아래
정책을 **명시적으로** 선언할 때만 첫 metadata를 허용한다.

```json
"geometry_bootstrap": "reference_only"
```

허용 조건은 모두 충족해야 한다.

1. source map의 metadata가 완전히 없음. 부분적·깨진 metadata는 bootstrap 대상이 아니라 거절이다.
2. `reference_spec`이 rule에서 명시적으로 선택되었고, reference metadata는 grid와 물리 geometry가 모두 declared 상태다.
3. alignment가 `scored`, `metric=index`, `index_axis=ranking`, winner 존재 상태다.
4. 설정된 margin/discriminating-die 문턱을 통과하고 source/reference payload가 truncation되지 않았다.
5. `confirmed_meta_for()`가 만든 결과의 geometry basis가 reference와 winner/placement/provenance를 모두 기록한다.

이것은 모든 문턱을 해제하는 정책이 아니다. **선언된 PRD reference 하나를 근거로 source의
첫 grid metadata를 만드는 정책**이며, 첫 write 이후 동일 `dt_job`의 다음 채점은
`geometry_assumed=false` 경로를 쓴다. `geometry_bootstrap`이 없거나 값이 다른 모든
기존 rule은 현행 거절 동작을 유지한다.

### 구현 순서

1. `dt_alignment_metadata_mapper._automatic_gate()`에 rule-aware bootstrap branch를 추가한다.
   `geometry_assumed` 외의 gate는 변경하지 않고, 위 조건이 payload에서 검증되지 않으면 no-op한다.
2. `dt_log_to_dt_alignment_metadata` rule에 `geometry_bootstrap: reference_only`를 선언한다.
   SYN의 explicit reference는 실제 metadata key인 `valid_die_ref:PRD-A_DT13`으로 고정한다.
3. `seed_syn_dt_alignment_samples.py`의 expected-result 표기를 alignment candidate notation
   (`rot0_tl` 등)으로 정규화하고, 생성 직후 direct alignment가 각 표본의 expected winner를
   내지 못하면 `--apply`를 거절한다. CSV와 DB 입력은 같은 planner를 사용한다.
4. 이미 처리 완료된 704개 outbox event의 상태를 수동으로 되돌리지 않는다. 동일 mapper와
   chain worker 경로를 사용하는 scoped replay를 `dt_job` prefix/목록으로 추가하고, 그 경로로
   `SYN-*-20260809`만 재처리한다.
5. S1 write가 만든 `wafer_map_metadata(target_table=dt_log,map_id=dt_job)` event가 S2를 통해
   `dt_inventory.dt_frame`까지 복제됐는지 조회한다.

### 완료 판정

| 검증 | 합격 기준 |
| --- | --- |
| Unit | bootstrap이 없는 rule은 `geometry_assumed=true`를 계속 거절한다. |
| Unit | malformed/partial source meta, non-declared reference geometry, no winner, absent index, truncation은 모두 no-op이다. |
| Integration | 8개 SYN job 모두 S1 metadata와 S2 `dt_frame`을 하나씩 갖는다. |
| Oracle | 각 job의 stored `dt_frame` provenance winner가 generator가 선언한 candidate와 일치한다. |
| Replay | scoped replay는 SYN job만 만지며 사람 작성 metadata와 비-SYN outbox 상태를 바꾸지 않는다. |

### 롤백

`geometry_bootstrap` 선언을 제거/false로 바꾸면 다음 신규 ingest부터 bootstrap은 즉시
중지한다. 이미 자동 생성된 metadata는 provenance와 source priority를 유지하므로 삭제하지
않는다. 잘못된 특정 SYN metadata의 재생성은 scoped replay로만 수행한다.

## HTTP 호출과 내부 API-equivalent 비교

| 방식 | 장점 | 문제 | 제안 |
| --- | --- | --- | --- |
| 체인 mapper가 `GET /api/maps/alignment/view`를 HTTP 호출 | 실제 외부 응답과 완전히 같은 직관 | 워커 transaction과 다른 DB snapshot, loopback 장애/timeout, params JSON 직렬화, HTTP 실패가 mapper 실패로 섞임 | 사용하지 않음 |
| route와 mapper가 공통 `build_alignment_view` facade 호출 | 동일 응답 schema, 동일 DB session, 네트워크 없음, 단위 테스트 쉬움 | route의 rule/config 검증을 작은 공통 함수로 이동해야 함 | **채택** |

구체적으로는 `resolve_alignment_view_for_chain(db, rule_name, key_values, map_table, ...)` 같은
읽기 전용 facade를 둔다. public route는 query를 검증한 뒤 이 facade를 호출하고, mapper도 같은
facade를 호출한다. facade의 반환 JSON shape은 `/api/maps/alignment/view`와 동일하게 유지한다.
따라서 운영자가 API 화면에서 확인한 `ruling`이 체인의 입력과 같은 계약이 된다.

## 체인 1: `dt_log → wafer_map_metadata`

### 범위와 식별자

- trigger: `dt_log`의 CREATE/EDIT
- 정렬 결정 단위: alignment rule이 선언한 `decision_key` (초기 후보는 `eqp_product_frame_attribution`의 `(dt_eqp, product)`)
- metadata 논리 대상: `dt_log`의 DT meta, 식별자는 `dt_job`
- 현재 물리 저장 대상: `wafer_map_metadata`의 `target_table = "dt_log"`, `map_id = dt_job`
- 출력: 대상 `dt_job`마다 한 건의 `wafer_map_metadata.grid_metadata` upsert
- `dt_log`/`dt_map` 외 원천에도 붙일 수 있도록 target table, map id column, metadata field는 chain rule 설정값으로 선언한다. 초기 DT 설정만 위 값으로 둔다.

한 결정 단위가 여러 `dt_job`을 포함할 수 있으므로, 채점은 결정 단위로 한 번 하되 metadata 쓰기는
영향받은 `dt_job`별로 한다. Core는 아직 이 체인 범위가 아니다. `core_frame`은 Core용 독립 scorer와
결정 키가 준비된 뒤 별도 chain으로 같은 일반 구조를 재사용한다.

### 자동 확정 gate

다음이 모두 참일 때만 metadata를 쓴다. 실패는 오류가 아니라 `no-op`이며, 어떤 조건 때문에
보류했는지는 worker log/관측값으로 남긴다.

```text
ruling.state == "scored"
ruling.winner 존재
ruling.metric == "index"
ruling.index_axis == "ranking"
ruling.geometry_assumed == false
ruling.thresholds_defaulted == false
source/reference가 truncated되지 않음
```

margin이나 문턱은 chain이 별도 상수로 재판정하지 않는다. alignment view가 이미 config의 문턱을
반영한 결과를 낸다. 특히 `dt_index` 값이 없어 `index_axis="absent"`로 값 축에 강등된 경우는
`no_winner`의 margin을 낮춰 통과시키지 않으며, 위 gate에서 명시적으로 보류한다.

### metadata 생성과 provenance

`ruling.by_frame[winner]`에서 placement/shift를 얻고, reference/basis meta와 함께
`confirmed_meta_for()`를 호출한다. 결과는 최소한 다음 의미를 가진다.

- grid geometry: `grid_cols`, `grid_rows`, `grid_start_x`, `grid_start_y`
- orientation: `rotation`, `side`, `grid_y_invert`
- 확정 mark: rule, 결정 키, winner, 채점 시각, engine version 또는 input fingerprint

이 mark는 폐기 예정인 `confirmation_uid`나 `frame_confirmation` row를 참조하지 않는다. 현행
`grid_metadata`의 확정 mark 공간에 `source: "chain_alignment"`와 위 provenance를 넣는다.
자동 meta는 갱신 가능하다. 같은 `dt_job`의 ingest는 한 transaction으로 outbox에 들어오며, ingest
완료 판단은 enrich 경로가 담당한다. 따라서 완료 이벤트가 도착할 때마다 최신 입력으로 재채점하여
gate를 통과하면 같은 `dt_job` metadata를 upsert한다. 동일 input fingerprint면 no-op으로 하되,
fingerprint가 달라진 자동 meta는 갱신한다. 수동 declared meta를 자동 체인이 덮어쓸지 여부만
source priority 정책으로 명시한다(기본 제안: 수동 declared meta는 보존).

## 후속 체인과 의존성

### 체인 2: `wafer_map_metadata → dt_inventory` (구현됨)

`dt_frame`을 frame 이름 문자열로 두지 않고 **JSON metadata 타입으로 승격**한다. `grid_metadata`와
같은 타입의 완전한 metadata를 `dt_inventory.dt_frame`으로 항등 복사한다. lot/slot 및 core 식별값의 enrich는 같은
`dt_inventory` row에 일반 chain/enrichment로 합류할 수 있다. 이 단계가 `dt_inventory`를 DT/Core
업무 메타의 통합 조회점으로 만든다.

### 체인 3: `dt_log + dt_inventory → dt_map` (예정)

표준 좌표 `front`, rotation `0`, `start=(1,1)` map은 이 단계에서만 만든다. 원본 `dt_log`는 바꾸지
않고, map의 `dt_job` scope를 purge 후 재생성하는 `replace_map` batch가 필요하다.

현재 generic chain worker는 mapper의 update들을 target table별 일반 `GeneralUpdateBatch`로 묶으며
`replace_map`과 scope를 전달하지 않는다. 따라서 이 기능은 체인 1의 선행조건이 아니다. 체인 3을
켜기 전에 mapper 반환 envelope에 `batches[] = {target_table, scope, replace_map, updates}`를 추가하고,
rule의 `allow_replace_map: true` 및 `dt_map.map_key_columns == ["dt_job"]`를 검증하는 확장이 필요하다.

## 구현 순서와 검증

1. alignment route와 mapper가 함께 쓸 read-only facade를 만들고, 현재 API 응답 snapshot test를 고정한다.
2. DT metadata chain mapper 하나를 추가한다. 입력 fixture에서 winner/placement와 최종 metadata를 검증한다.
3. `dt_index` 없음, `geometry_assumed`, truncated, margin 부족 각각이 **쓰기 없이 보류**되는 테스트를 추가한다.
4. 동일 이벤트 재처리 시 metadata가 변하지 않는 idempotency와, manual metadata 미덮어쓰기를 검증한다.
5. 그 다음에만 metadata→inventory 항등 chain, 마지막으로 replace-map contract를 설계·검증한다.

## 반영된 결정과 남은 정책

- metadata의 논리 target은 `dt_log`의 `dt_job`별 DT meta이며, 현재 저장 주소는 `wafer_map_metadata(dt_log/dt_job)`다.
- `dt_inventory.dt_frame`은 JSON metadata 타입으로 승격한다.
- 자동 metadata는 입력 fingerprint가 달라지고 gate를 통과하면 갱신한다.
- `dt_job` ingest 완료는 enrich가 같은 transaction의 outbox에 넣는 완료 이벤트를 사용한다.
- 남은 정책은 수동 declared meta와 자동 meta가 충돌할 때의 source priority뿐이다. 기본 제안은 수동값 보존이다.

이 문서는 설계 제안이다. `frame_confirmation` 삭제, chain rule 활성화, schema 변경, mapper 구현은 이 결정이
확정되기 전에는 수행하지 않는다.
