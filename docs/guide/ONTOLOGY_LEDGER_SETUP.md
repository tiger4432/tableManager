# Ontology Ledger 셋업 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-08-17 Source Profile 2단계 `IN_PROGRESS` / `NOT_APPROVED` | **Owner:** Server / Ledger + Ontology
> **Source-of-truth:** `server/ledger/config.py` · `server/ledger/source_profile.py` · `server/ledger/source_profile_builtins.py` · `server/ledger/vocabulary.py` · `server/config/`

이 문서는 **어떤 선언을 어떤 순서로 준비해야 원장이 도는지**만 설명한다.
세부 필드 계약은 [LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md), Python
번역기 작성법은 [LEDGER_GUIDE](./LEDGER_GUIDE.md)가 소유한다.

## 0. 핵심 원칙

1. 소스 테이블, 원장 선언, 번역기, vocabulary는 실행 책임은 달라도 **Source Contract 하나**로 검증한다.
2. 세계 시각·주어 타입·원천 참조를 추측하지 않는다. 모르면 거절한다.
3. 한 행→Claim 1~N이면 `declared`; 묶기·짝짓기·외부 조회가 필요할 때만 Python을 쓴다.
4. live config는 `server/config/*.json`, 배포 예시는 `server/config/sample/*.json.sample`이다.
5. 정준 predicate와 entity type은 코드 소유다. 온톨로지 predicate만 append-only config 확장을 허용한다.

## 1. 선언 파일

| 선언 | 역할 | 부재 시 |
|---|---|---|
| `ledger_config.json` | 기존 `sources`: 실행 문법·시각·컬럼·주어·발화 규칙. 선택적 `profiles`: 상위 Source Ontology Profile | 실행은 아직 `sources`만 읽으므로 해당 수동 소스가 없으면 거절 |
| `ledger_vocabulary.json` | 온톨로지 predicate 확장 | 코드 어휘만 사용; sample 자동 로드 안 함 |
| `finding_kinds.json` | 결함 종류·분모·관측 테이블·class | 코드 기본값 사용 |
| `mechanism_models.json` | 후보와 물리 기전의 방향 그래프 | 기전 관문이 부재 상태를 반환 |
| `siblings_axes.json` | 마킹·모집단·요인 축 | 대조 엔진이 선언 부재를 반환 |
| `ledger_journey.json` | 공정 segment와 표시 이름 | journey가 부재 상태를 반환 |
| `table_config.json` | 원천 테이블·컬럼·키 | 테이블/컬럼 검증 실패 |

`ontology_mapping.json`은 2026-08-16에 실행 트리에서 제거됐다. 옛 예시는 [archive](../_archive/retired_graph_sync/README.md)에만 있다.

## 2. 빈 환경 셋업 순서

1. 원천 테이블과 키·인덱스를 `table_config.json`에 선언한다.
2. 원장 테이블을 만든다.
3. `ledger_config.json`에 소스를 한 장 선언한다.
4. 필요하면 온톨로지 predicate와 finding kind를 선언한다.
5. 어드민 Source Contract와 dry-run을 통과시킨다.
6. 선언을 저장한 뒤 백필한다.
7. `coverage`, `structure`, `trace` 순서로 확인한다.

마이그레이션:

```bash
conda run -n assy_manager python server/migrations/add_ledger_events.py
conda run -n assy_manager python server/migrations/add_ledger_refusal_reasons.py
```

백필:

```bash
cd server
conda run -n assy_manager python -m ledger.backfill --source <source>
```

주요 플래그:

| 플래그 | 용도 |
|---|---|
| `--reset-cursor` | 처음부터 재번역 |
| `--from <cursor>` | 지정 위치 다음부터 시작; 철자는 source kind마다 다름 |
| `--fetch-rows N` | 원천 페이지 크기 |
| `--max-batches N` | 시험 실행의 배치 상한 |
| `--config <path>` | 다른 선언 파일 사용 |

## 3. `ledger_config.json`

### 3.0 Source kind 선택

| `kind` | 분자 | 적합한 소스 |
|---|---|---|
| `lineage` | 같은 사건을 말하는 행 묶음 | split·merge·track-in |
| `observation` | 원천 한 행 | void·delam 등 검사 발견 |
| `transfer` | 선언한 group 값 하나 | DT·bonding 이동 job |
| `declared` | 원천 한 행 | inventory·mapping·reference table |

`kind` 생략은 기존 호환을 위해 `lineage`다. 새 선언에는 항상 명시한다.

모든 kind의 공통 핵심:

- `occurred_at_column`, `occurred_at_timezone`: 세계 시각과 해석 기준
- `subject_types`: 이 소스가 발화할 수 있는 주어 타입의 허용 목록
- `register_entity_types`: first-sight `register`가 필요한 발급형 타입
- `columns`: 논리 이름 → 물리 컬럼
- `watermark` 또는 kind별 cursor 선언

### 3.1 `lineage`

추가 핵심 키:

- `columns`: `row_identity`, `lot`, `event_type`, `parent_lot`, `child_lot`, `slots`, `wafers`
- `vocabulary.<event_type>.lineage`: `parent_child` 또는 `none`
- `vocabulary.<event_type>.slot_pairing`: `shared_wafer`, `slot_preserving`, `none`
- `emit_has_wafer`, `emit_register`: 이벤트별 발화 여부

행의 부모·자식·위치 목록이 한 사건으로 함께 참일 때 사용한다.

### 3.2 `observation`

추가 핵심 키:

- `finding_kind`: 관측하는 결함 종류
- `run`: 검사 run 관계, key, method
- `watermark.columns`: 유일하고 인덱스가 있는 키셋
- `columns`: `row_identity`, `wafer`, `run_key`; 좌표·extent·unit·class는 선택
- `synthetic`: 합성 관측일 때만 명시

관측 시각과 분모는 run에서 확정한다. run을 못 찾으면 발견 행의 적재 시각으로 대체하지 않고 거절한다.

### 3.3 `transfer`

추가 핵심 키:

- `group`: 사건을 묶는 컬럼과 결정적 행 순서
- `container`: 목적지 lot·slot을 확정하는 관계, 또는 명시적 `relation: null`
- `columns`: `row_identity`, `group_key`, `wafer`; 기록값 보존용 lot·slot은 선택

다이별 원천 행을 모두 점 노드로 만들지 않고 job×source wafer 단위 Claim으로 접는다.
개별 좌표는 `source_raw_ref`를 통해 원천으로 돌아가 조회한다.

### 3.4 `declared`

`emit[]`가 곧 행→Claim 프로그램이다. 리스트 분해·행 묶기·외부 조회가 필요하면 이 문법을 늘리지 말고 §3.5의 Python 프로필을 쓴다.

필수 핵심:

| 키 | 뜻 |
|---|---|
| `occurred_at_basis` | `claim_time` 또는 `row_created`; 기본값 없음 |
| `watermark.columns` | 편집을 놓치지 않는 키셋 |
| `columns` | 최소 `row_identity`; `emit`의 `$컬럼`이 참조하는 컬럼 포함 |
| `emit[].rule` | provenance에 남는 파생 이름 |
| `emit[].predicate` | 발화 predicate |
| `emit[].class` | `observation` 또는 `inference` |
| `emit[].subject` | type과 key 표현식 |
| `emit[].object` | `entity_ref`, `value`, 또는 없음 |
| `emit[].when` | 닫힌 연산자 중 정확히 하나; 선택 |

`$column`은 현재 행의 컬럼 값, 일반 문자열은 리터럴이다. 없는 컬럼 참조와 알 수 없는 연산자는 저장 전에 거절한다.

### 3.5 Source Contract

작성자는 세 파일을 따로 추론하지 않고 다음 한 흐름으로 확인한다.

1. `GET /admin/ledger/sources`에서 source kind와 번역 프로필을 고른다.
2. `GET /admin/ledger/relations?q=&limit=`에서 실제 테이블·컬럼을 확인한다.
3. 선언을 작성하고 `POST /admin/ledger/dry-run`을 실행한다.
4. `source_contract.state == "ready"`와 실제 `atoms_rendered`를 모두 확인한다.
5. 반환된 token으로 `POST /admin/ledger/save`를 호출한다.
6. `GET /admin/config/resolve?domain=ledger`로 적용 상태를 확인한다.

Source Contract가 보여 주는 것:

- `translator`: 실행 프로필·분자 단위·구현 위치
- `emissions[]`: 표본에 없는 분기까지 포함한 가능한 Claim 전수
- `vocabulary`: 각 Claim이 맞춰야 하는 현재 서명
- `configured_by`: 불일치 때 고칠 선언 위치
- `issues`: source 허용 범위 또는 vocabulary와의 충돌

dry-run의 실제 원자는 표본 증거이고 Source Contract는 전체 가능성 검사다. 둘 다 통과해야 한다.

새 Python 모양은 [LEDGER_GUIDE §3 ③](./LEDGER_GUIDE.md)의 Template Method를 사용한다.

### 3.6 Source Ontology Profile 2단계

> **status:** `IN_PROGRESS` · **approval:** `NOT_APPROVED`
> **remaining_acceptance:** 사용자 재승인

새 상위 선언은 `ledger_config.json`의 기존 `sources` **옆** `profiles`에 둘 수 있다.
Profile은 업무별 고정 필드가 아니라 Pack Claim의 Role과 원천 binding을 연결한다.
정확한 계약은 [LEDGER_TECHNICAL_SPEC §3.10](../spec/LEDGER_TECHNICAL_SPEC.md)이 소유한다.

```json
{
  "profile_version": 1,
  "source": "movement_rows",
  "packs": ["transfer@1"],
  "mappings": [{
    "mapping_id": "movement",
    "use": "transfer/movement",
    "bind": {
      "subject": {
        "kind": "column",
        "column": "ITEM_ID",
        "binding_origin": "system_suggested",
        "approval_status": "approved",
        "suggestion_reason": "matched the declared source identity"
      },
      "from": {"kind": "constant", "value": "source_position"},
      "to": {
        "kind": "declared_lookup",
        "lookup_id": "destination_inventory",
        "key": "column:MOVE_ID",
        "select": "container"
      },
      "occurred_at": "column:EVENT_TIME"
    }
  }]
}
```

검증·직렬화 진입점:

- `validate_profile`: Pack/Claim/Role와 binding 계약 검사, 첫 오류 예외 반환
- `validate_profile_errors`: 모든 오류를 `code/path/message` 순서가 결정적인 목록으로 반환
- `serialize_profile`: 정규화된 Profile의 결정적 JSON 생성
- `validate_profile_section`: 수동 `sources`를 건드리지 않고 `profiles`만 검사
- `public_profile_schema`: Pack/Claim/Role/Binding 공개 metadata

지원 binding은 `column`, `constant`, `declared_lookup`뿐이다. 정규화 결과에는
`binding_origin`(`user_declared|system_suggested|imported`)과
`approval_status`(`pending|approved|rejected`)가 항상 별도로 남는다. 생략 기본값은
`user_declared`와 `pending`이고, `system_suggested`에는 `suggestion_reason`이 필수다.
`approved`는 컬럼 Mapping 승인일 뿐 Claim을 `confirmed`나 `pin`으로 올리지 않는다.
`from`의 `source_position`은 Pack에 등록된 symbolic constant이며 임의 위치 문자열은
거절된다. `declared_lookup`은 여기서 구조만 검사하고 실행·반환 형상 검사는 3단계다.
임의 Python·SQL·JavaScript·expression 실행은 없다.

⚠️ `config.load()`는 계속 기존 `sources`만 실행한다. Profile compiler·runtime adapter·
translator 실행은 아직 없으므로 수동 선언을 제거하거나 Profile만 두고 백필하면 안 된다.

## 4. Vocabulary

- 정준 predicate와 entity type: `server/ledger/vocabulary.py`
- 온톨로지 predicate 확장: `server/config/ledger_vocabulary.json`
- 합쳐진 실행 뷰: `vocabulary.all_predicates()`

새 predicate 선언은 최소 `layer`, `status`, `subject`, `object`, `traversable`을 완결해야 한다.
`traversable: true`는 재귀 통과, `false`는 도달만, `null`은 걷기 인출 제외다.
기존 predicate는 삭제하지 않고 `retired`와 `superseded_by`로 은퇴시킨다.

개체 타입은 신원 키 정의까지 포함하므로 아직 config 확장 대상이 아니다.

## 5. Finding kind

한 종류는 다음을 선언한다.

- `observed_by`: 검사 분모가 되는 method
- `observation_table`: 발견 테이블
- `extent_columns`: 크기 필드
- `classes`: 허용 class 집합
- `label`: 화면 이름

관측 부재와 검사 후 0건을 구분하려면 `observed_by`가 반드시 정확해야 한다. 합불 임계는 finding kind에 저장하지 않는다.

## 6. 분석 화면용 선언

이 파일들은 원장을 쓰지 않고 분석 해상도를 높인다. 부재는 오류가 아니라 명시적 상태다.

### 6.1 `mechanism_models.json`

모델은 `finding_kind`, `role`, `target`, `nodes`, 방향 있는 `edges`, `bindings`를 가진다.
방정식이나 데이터에 없는 인과를 채워 넣지 않는다. binding은 실제 candidate 경로가 생긴 뒤 연결한다.

### 6.2 `siblings_axes.json`

`geometry`는 모집단 단위, `attribution[]`는 관계와 join, `axes[]`는 비교 축을 선언한다.
식별자 축은 `rank: false`로 원인 랭킹에서 제외하되 마킹에는 계속 사용한다.

### 6.3 `ledger_journey.json`

- `segments`: 어떤 predicate와 payload 경로가 공정 순서를 만드는지
- `step_labels`, `family_labels`, `field_labels`: 표시 이름과 단위

`segments`는 구조 선언이라 비우면 journey가 `absent`가 된다. label 블록은 표시 전용이라 비워도 데이터와 항목 수는 바뀌지 않아야 한다.

## 7. 은퇴한 설정

구 graph materializer와 매핑 로더는 제거됐다. 현재 온톨로지는 원장 어휘와 Claim이며, 구조 뷰는 선언과 원장에서 생성한다.

## 8. 현재 경계

| 물리 층 | 상태 | 현재 이음새 |
|---|---|---|
| WF 공정·레시피 Claim | 착지 | `processed_with`, `has_param`, `Recipe` |
| 칩 이동 Claim | 착지 | `transferred` + `kind: "transfer"` |
| 기전 방향 그래프 | 착지 | `mechanism_models.json` + `mechanism_gate.py` |
| 구조형 `BondLine`·물리량 타입 사전 | 제안 | 실행 어휘·로더 없음 |
| 물리 시나리오의 자동 Action 산출 | 제안 | 현행 Enrich Action과 별도 판정 필요 |

- 온톨로지 predicate 확장은 config로 가능하다.
- entity type 추가와 신원 키 변경은 아직 코드·판정 영역이다.
- 소스 행 번역은 `declared` 또는 Python 프로필로 가능하다.
- 원장을 걸어 새 추론 Claim을 만드는 `derivation` 문법은 아직 미구현이다.

## 9. 알려진 제약

- finding 모집단의 일부 관계 이름은 여전히 코드 상수다.
- 서로 다른 두 분석 경로가 같은 모집단 규칙을 별도로 조립하는 구간이 있다.
- 새 source kind를 추가하려면 프로필 등록, Source Contract emissions, backfill 페이지 경계를 함께 구현해야 한다.

## 10. 완료 확인

| 확인 | 기대 |
|---|---|
| `/api/ledger/coverage` | `ready`; 거절·커서 상태 설명 가능 |
| `/api/ledger/structure` | 선언과 관측의 차이가 상태로 보임 |
| `/api/ledger/trace` | 원천으로 돌아가는 경로와 끊긴 이유가 보임 |
| `/api/ledger/kinds` | 종류별 선언·원자·분모 상태가 구분됨 |
| Source Contract | `ready`, issues 없음 |
| dry-run | 실제 원자 모양 확인, writes 0 |

## 11. 문서 경계

- 이 문서: 선언과 셋업 순서
- [LEDGER_GUIDE](./LEDGER_GUIDE.md): Python 번역기와 운영
- [LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md): 정확한 계약
- [backend](../architecture/backend.md): API 라우트·파라미터
- [history](../history/README.md): 사고·측정·변경 이력
