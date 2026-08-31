# AssyManager 설정 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-08-31 (§1 에 **「`server/config/` 밖에 사는 선언」 신설** — `server/pacing.json` · `server/ledger/gap_names.json`) · 직전 2026-08-19 (§1 원장 config 행만 재대조) | **Owner:** Lead / Backend
> **Source-of-truth:** `server/config/` · 각 config loader

이 문서는 **설정 파일의 위치, 의존 순서, 반영 확인 방법**만 설명한다.
필드별 키 사전은 [guide/config](./config/README.md), 원장·온톨로지 선언은
[ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md)이 소유한다.

## 1. 한눈에 보기

폴더 역할:

| 경로 | 역할 |
|---|---|
| `server/config/*.json` | 현재 환경의 live config; 대부분 gitignored |
| `server/config/sample/*.json.sample` | 배포 가능한 구조 예시 |
| `server/config/backup/` | 복원용 사본 |
| `docs/guide/config/` | 파일별 키·검증·운영 절차 |

주요 설정:

| 파일 | 지배하는 것 | 상세 |
|---|---|---|
| `database.json` | DB 접속 | [database](./config/database.md) |
| `table_config.json` | 동적 테이블·키·컬럼 타입 | [table_config](./config/table_config.md) |
| `ingestion_settings.json` | 수집 경로·파서·용량 정책 | [ingestion_settings](./config/ingestion_settings.md) |
| `auto_update_control.json` | 수집기 스케줄·활성 상태 | [auto_update_control](./config/auto_update_control.md) |
| `chain_rules.json` | 테이블 간 파생 체인 | [chain_rules](./config/chain_rules.md) |
| `enrichment_rules.json` | 결손 보정 규칙·워크리스트 | [enrichment_rules](./config/enrichment_rules.md) |
| `virtual_join_rules.json` | 조회 시점 가상 조인 | [virtual_join_rules](./config/virtual_join_rules.md) |
| `notation_rules.json` | 키 표기 정규화 | [notation_rules](./config/notation_rules_config.md) |
| `map_overlay_config.json` | 맵 역할·오버레이·라우팅 | [map_overlay](./config/map_overlay_config.md) |
| `maps.json` | 맵 프리셋 | [maps](./config/maps.md) |
| `bonding_plan_config.json` | 본딩 계획 역할 | [bonding_plan](./config/bonding_plan_config.md) |
| `transfer_plan_config.json` | DT/본딩 단계·역할 | [transfer_plan](./config/transfer_plan_config.md) |
| **`ontology/ledger_config.json`** (🔴 파일이 아니라 **디렉터리 `server/config/ontology/`가 root**이고 그 안에 `.json`은 **이 하나뿐**이어야 한다 — 다른 `.json`이 있으면 `unlisted_config_file`로 로드가 거절되며 검사는 **재귀한다**. ⚠️ **이 파일은 gitignored가 아니라 «추적»된다** — 위 「대부분 gitignored」의 예외다) | Source→Ledger→Ontology | [ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md) |
| `effort_metric.json` | 화면 교정 공수 계기 | [effort_metric](./config/effort_metric.md) |
| `suggest_config.json` | 컬럼 추천 | [suggest_config](./config/suggest_config.md) |
| `audit_history_config.json` | 감사 이력 정책 | [audit_history](./config/audit_history_config.md) |

운영 값·비밀번호·실제 경로를 sample이나 문서에 복사하지 않는다.

### 🔴 `server/config/` 밖에 사는 선언 — 그 디렉터리만 훑으면 못 본다 (2026-08-31 신설)

둘은 **현장이 고쳐 쓰는 값이 아니라 제품이 든 표**라서 코드 옆에 살고 **git 에 추적된다**.
그래서 `.sample` 짝이 없고, **디렉터리 훑기로는 안 잡힌다** — 이름으로 지목해야 한다.

| 경로 | 무엇 | 누가 읽나 |
|---|---|---|
| **`server/pacing.json`** | 페이싱 프로파일 `fast`·`slow`·`trickle`(각 `label`·`when`·`units_per_cycle`·`rest_seconds`) — 긴 작업이 옆 질의를 굶기지 않게 «쉬는 리듬» | **둘.** 원장 백필(단위 = **페이지**, 이름은 `ledger_backfill` 의 `pace` 가 고른다) · 파일 인제션(단위 = **청크**, 이름은 **`ingestion_settings.json` 의 `ingestion_pace`** 가 고른다) |
| **`server/ledger/gap_names.json`** | 결측 질문의 **이름과 뜻**(`pairs`·`subject_sides`·`object_sides`) — 찾는 것은 코드가 어휘를 순회해서 하고, 부르는 이름은 이 표가 준다. `_source` 가 그 이름을 정한 명세를 가리킨다 | `server/ledger/gaps.py` → `GET /api/ledger/gaps` |

- ⚠️ **`ingestion_pace` 는 `ingestion_settings.json` 에 있고 값은 `pacing.json` 이 정의한다** — 두 파일을 함께 봐야 뜻이 완성된다. 프로파일 이름을 지우면 그것을 고른 인제션이 «경고 후 전속력»으로 떨어지고, 백필은 **거절**한다(같은 오타에 반응이 다르다).
- ⚠️ **`gap_names.json` 과 원장 선언이 어긋나면 라우트가 «양방향으로» 거절한다** — 이름 없는 질문도, 질문 없는 이름도 오류다. 술어를 선언에서 지우면 이 표에서도 지워야 한다.
- ⚠️ **읽기 시점**: 페이싱은 **실행 시작마다 한 번**(도는 중 편집은 그 실행에 안 듣고, 재기동은 필요 없다). 결측 이름 표는 요청마다 읽는다.
- 상세는 [backend §4.1](../architecture/backend.md)(페이싱) · [backend §2](../architecture/backend.md)(`/api/ledger/gaps`).

### DB에 저장되는 설정성 데이터

일부 설정은 JSON이 아니라 제품 테이블이 소유한다. 대표적으로 맵 분할·확정 기록은
마이그레이션이나 제품 API로 관리하며 `table_config.json`에 손으로 복제하지 않는다.

### 폐지된 것 — 워크스페이스 `config.json`

워크스페이스별 `config.json`을 설정 정본으로 사용하지 않는다. 살아 있는 소비자가 없는
설정은 sample에 남아 있어도 사용하지 않는다.

### 파일이 아닌 설정 원천

- 환경 변수: 관리자 토큰·프로세스 포트 등 배포 비밀
- DB 카탈로그: 실제 테이블·컬럼 존재
- 제품 테이블: 사용자가 UI/API로 확정한 상태

JSON 선언과 이 원천을 섞어 한쪽에서 다른 쪽을 추측하지 않는다.

## 2. 의존 순서

```text
database
  → table_config
    → ingestion
      → chain / enrichment / virtual join
        → map & transfer plan
          → ledger & ontology analysis
```

- 테이블·컬럼이 먼저, 그것을 참조하는 규칙이 나중이다.
- `table_config` 선언만으로 물리 DB 컬럼이 이미 생겼다고 가정하지 않는다.
- 파생 config는 원천 config의 기본값을 복사하지 말고 resolver 결과를 사용한다.
- 원장 소스 선언은 실제 relation·column을 확인한 뒤 작성한다.

## 3. 시나리오별 체크리스트

### S1. 새 테이블 추가

1. `table_config.json`에 business key, `column_types`, 표시 이름을 선언한다.
2. reload 후 물리 테이블·컬럼을 `information_schema`로 확인한다.
3. 파서/수집기 입력을 연결한다.
4. 체인·가상 조인·원장 소스가 필요하면 각각 별도 선언한다.

### S2. 새 맵 테이블 추가

S1에 더해 map key, 좌표 컬럼, map metadata, valid-die 참조를 선언한다. 정렬과 오버레이는
[MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md)과 §5.8-bis를 따른다.

### S3. 수집기 추가·토글

`auto_update_control.json`에 스케줄과 활성 상태를 두고, parser/source가
`ingestion_settings.json`과 일치하는지 확인한다. 토글 후 heartbeat와 ingestion log를 본다.

### S4. 원장 온톨로지를 확장할 때

`ontology_mapping.json` 기반 그래프 materializer는 코드와 설정에서 제거됐다. 현재 확장은
[ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md)을 따른다.

### S5. 대형 파일 임계 조정

임계와 worker budget은 `ingestion_settings.json`에서 조정한다. 변경 후 작은 파일과 임계
초과 파일을 각각 넣어 lane 선택·재시도·메모리 상한을 확인한다.

### S6. 본딩/전사 계획 원천 변경

`bonding_plan_config.json`과 `transfer_plan_config.json`의 역할 바인딩만 실제 테이블로
교체한다. `/admin/transfer-plan/dry-run`에서 선언·유도·거절 사유를 확인하고 코드에
현장 테이블명을 추가하지 않는다.

### S7. Enrichment 규칙 추가

판단키, 후보 원천, 자동 확정 조건을 선언한다. `/admin/config/resolve?domain=enrichment`와
auto-confirm dry-run으로 효과와 예상 건수를 확인한다.

### S8. Chain 규칙 추가

생산자→소비자 방향과 business key를 확인하고 dry-run/replay로 과거 행에 적용될 범위를
본다. 순환이나 자기 트리거 규칙을 허용하지 않는다.

### S9. 맵 정렬 화면 활성화

소스·타깃 map metadata와 역할 바인딩을 먼저 확정한다. 기준 프레임이 없으면 화면에서
프레임을 지어내지 않고 worklist로 남긴다.

## 4. 적용·검증 규율

### 4.1 리로드 매트릭스

| 변경 | 일반 반영 방식 |
|---|---|
| `table_config.json` | watcher 또는 `/admin/reload-configs`; 물리 ALTER 여부 별도 확인 |
| `ingestion_settings.json`의 `external_sources` | watcher **재기동**. 런타임 reload는 새 바인딩 추가만 시도하며 기존 경로·파서·옵션 교체와 제거는 하지 않음 |
| 규칙·바인딩 config | `/admin/reload-configs` 후 resolve 조회 |
| 프로세스 수명 캐시 | 강제 reload 지원 여부 확인, 없으면 해당 프로세스 재기동 |
| `database.json`·환경 변수 | 전체 프로세스 재기동 |

각 파일의 정확한 반영 방식은 하위 키 사전이 소유한다.

### 4.2 `/admin/reload-configs`가 하는 일 / 안 하는 일

하는 일: 프로세스별 config cache 교체와 일부 누락 테이블 생성.

보장하지 않는 일:

- 기존 테이블의 모든 컬럼·인덱스 ALTER
- 과거 파생값 재계산
- 이미 적재된 원장 Claim 재번역
- 잘못된 선언의 자동 수정

### 4.2-bis 선언의 효과 조회

`GET /admin/config/resolve`는 선언을 `effective`, `ineffective`, `rejected`로 나누고
서버가 만든 사유를 돌려준다. reload 성공 응답만 보고 설정이 적용됐다고 판단하지 않는다.

도메인별 dry-run이 있으면 함께 사용한다. dry-run은 예상 효과를 보여 줄 뿐 live config를
쓰지 않는다.

### 4.3 물리 반영 검증

`GET /tables/{table}/schema`는 config 뷰일 수 있으므로 물리 존재의 증거가 아니다.
테이블·컬럼·인덱스는 `information_schema`와 PostgreSQL catalog에서 확인한다.

### 4.4 Config watcher 발화 조건

watcher가 모든 파일을 감시한다고 가정하지 않는다. 원자적 교체, 수정 시각, 대상 파일
목록을 확인한다. watcher 대상이 아니면 admin reload 또는 재기동이 필요하다.

## 5. 파일별 상세

### 5.1 `table_config.json`

[table_config 키 사전](./config/table_config.md). 컬럼 설명 주석은 선언이 아니다;
`column_types`에 없는 컬럼은 쓰기 경로에서 빠질 수 있다.

### 5.2 `enrichment_rules.json`

[enrichment_rules 키 사전](./config/enrichment_rules.md).

### 5.3 `chain_rules.json`

[chain_rules 키 사전](./config/chain_rules.md).

### 5.4 `auto_update_control.json`

[auto_update_control 키 사전](./config/auto_update_control.md).

### 5.5 기타 운영 설정

- [ingestion_settings](./config/ingestion_settings.md)
- [effort_metric](./config/effort_metric.md)
- [suggest_config](./config/suggest_config.md)
- [audit_history_config](./config/audit_history_config.md)
- [notation_rules](./config/notation_rules_config.md)

### 5.6 `bonding_plan_config.json`

[bonding_plan 키 사전](./config/bonding_plan_config.md). 역할의 부재·거절·연결 상태를 구분한다.

### 5.7 `transfer_plan_config.json`

[transfer_plan 키 사전](./config/transfer_plan_config.md). stage와 role을 선언하며, 현장
테이블명은 이 config가 소유한다.

### 5.8-bis `map_overlay_config.json`

[map_overlay 키 사전](./config/map_overlay_config.md). overlay source, paint rule,
preset routing을 선언한다. 물리 정렬은 map metadata가 소유한다.

### 5.8-ter 기능별 필요 테이블

| 기능 | 최소 관계 |
|---|---|
| 원장 혈통 | source event relation |
| 결함 분석 | inspection run + observation relation |
| DT/Core 추적 | transfer event + inventory/trace relation |
| 맵 오버레이 | source map + target map + map metadata |

실제 이름은 `table_config`와 각 역할 config에서 정한다.

### 5.9 `maps.json`

[maps 키 사전](./config/maps.md). 가능하면 UI/API로 관리하고 운영 값을 sample에 덮어쓰지 않는다.

## 6. 함정 모음

- live, sample, backup을 같은 폴더·같은 이름 규칙으로 섞지 않는다.
- 선언된 컬럼과 물리 컬럼을 같은 사실로 취급하지 않는다.
- 설정 reload와 과거 데이터 replay를 같은 작업으로 취급하지 않는다.
- 하드코딩 기본값으로 잘못된 선언을 성공시키지 않는다.
- config를 두 파일에 중복 선언하지 않는다; 상속·유도 결과를 서빙한다.
- 은퇴 config를 sample이 존재한다는 이유로 활성화하지 않는다.
- 운영 비밀과 실제 경로를 문서·sample·history에 남기지 않는다.

## 7. 새 환경 부트스트랩

1. `database.json`과 환경 변수를 설정한다.
2. `table_config.json`으로 원천 테이블을 선언하고 물리 스키마를 확인한다.
3. ingestion과 auto-update를 연결한다.
4. chain·enrichment·virtual join을 필요한 것만 선언한다.
5. map/transfer plan 역할을 실제 테이블에 바인딩한다.
6. 원장을 사용할 경우 [ONTOLOGY_LEDGER_SETUP §2](./ONTOLOGY_LEDGER_SETUP.md)를 수행한다.
7. reload 후 resolve·dry-run·catalog로 세 층을 각각 확인한다.
