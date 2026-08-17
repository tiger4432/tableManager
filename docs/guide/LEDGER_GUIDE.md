# Canonical Ledger 개발·운영 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-08-16 | **Owner:** Server / Ledger
> **Source-of-truth:** `server/ledger/` · `server/ledger_trace_router.py`

이 문서는 **새 소스를 붙이고 백필 결과를 확인하는 방법**만 설명한다.
정확한 필드·인덱스·응답 계약은 [LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md),
선언 순서는 [ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md), 결정 이유는
[CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md), 변경 이력은
[history](../history/README.md)가 소유한다.

> **Ledger V2 전환 주의:** 이 문서의 구 translator/source-kind/migration/reset 설명은 legacy
> 호환 경로의 역사와 조회 의미를 이해하기 위한 것이다. 새 Source 설정은 반드시
> [ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md)의 V2 manifest 6파일과
> Preparer → Role mapper → Pack/Profile 경로를 따른다. 공개 CLI의 `--reset-cursor`와
> `--from`은 현재 별도 승인 없이 `destructive_approval_required`로 거절되며, 이 문서의 옛
> 예를 실행 허가로 읽지 않는다.

---

## 0. 먼저 고를 것

| 소스 모양 | 선택 |
|---|---|
| 한 행에서 Claim 1~N개를 만들 수 있음 | `kind: "declared"` — Python 작성 없음 |
| 여러 행을 묶거나 위치를 짝지어야 함 | 기존 `lineage`·`transfer`, 또는 Template Method |
| 외부 관계를 조회해 시각·신원을 확정해야 함 | 기존 `observation`, 또는 Template Method |
| 원장을 걸어 새 사실을 추론 | 아직 미구현인 `derivation`; 소스 번역과 구분 |

기본 원칙은 **가능하면 `declared`, 필요한 경우에만 Python 번역기**다.

## 1. 모듈 지도

### 1.1 쓰기 쪽

| 파일 | 역할 |
|---|---|
| `config.py` | 소스 문법 검증과 버전 해시 |
| `source_contract.py` | 선언 → 번역 프로필 → 가능한 Claim → live vocabulary 결합 검사 |
| `declared_translator.py` | `emit` 선언 실행 |
| `translator_pattern.py` | Python 번역기의 공통 안전 수명주기 |
| `examples/grouped_translator_template.py` | 새 그룹형 번역기의 복사 템플릿 |
| `gate.py` | 분자 단위 전부-아니면-전무 검사와 거절 계수 |
| `store.py` | 원자 append와 커서 전진을 한 트랜잭션으로 저장 |
| `backfill.py` | 페이지·분자 경계·번역기 실행 |
| `dry_run.py` | 실제 번역기를 읽기 전용 트랜잭션에서 미리 실행 |

### 1.2 읽기 쪽

| 질문 | API |
|---|---|
| 원장 준비 상태 | `GET /api/ledger/coverage` |
| 특정 개체 추적 | `GET /api/ledger/trace` |
| 구조와 선언·관측 차이 | `GET /api/ledger/structure` |
| 결함 종류와 원장 상태 | `GET /api/ledger/kinds` |
| 두 주어의 공정 차이 | `GET /api/ledger/journey` |
| 증거 서브그래프 | `GET /api/ledger/subgraph` |

파라미터와 응답 계약은 [backend §2](../architecture/backend.md)가 정본이다.

## 2. 쓰기 경로

```text
source rows
  → config validation
  → Source Contract validation
  → molecule grouping
  → claim drafts / atoms
  → gate screening
  → ledger_events + cursor commit
```

- **분자**는 혼자 참이어야 하는 최소 묶음이다. 한 파편이 틀리면 전체를 거절한다.
- `source_raw_ref`는 원천 행으로 돌아갈 수 있어야 한다.
- `occurred_at`은 세계에서 사실이 성립한 시각이다. 적재 시각으로 대신하지 않는다.
- 원자와 커서는 같은 트랜잭션에 저장한다.

## 3. 새 소스 붙이는 법 — 코드 쪽

### ① 어휘 검사

기존 predicate와 entity type으로 표현할 수 있는지 먼저 본다. 새 predicate는
주어·목적어·필수 payload·걷기 정책까지 완결된 서명으로 선언해야 한다.
개체 타입은 아직 코드 소유이며 운영 config에서 추가할 수 없다.

### ② 선언 작성

[ONTOLOGY_LEDGER_SETUP §3](./ONTOLOGY_LEDGER_SETUP.md)에 따라 소스 한 장을 작성한다.
물리 컬럼명은 `columns`에만 두고 번역기 코드에는 넣지 않는다.

### ③ 번역기 작성 — Template Method

`declared`로 표현할 수 없을 때만
`server/ledger/examples/grouped_translator_template.py`를 복사하고 네 블록만 바꾼다.

1. 소스·프로필 이름
2. `POSSIBLE_EMISSIONS` — 낼 수 있는 Claim 전수
3. `iter_molecules` — 행을 분자로 묶는 규칙
4. `claim_drafts` — 분자에서 도메인 Claim을 만드는 규칙

시각 해석, raw reference, first-sight register, 게이트 호출, 늦은 거절 시 register
메모 롤백은 `SafeTranslatorTemplate`이 맡는다. 예제는 런타임에 등록돼 있지 않으므로
복사만 해서는 0행을 쓴다. 새 프로필 등록과 backfill 페이지 경계 연결은 명시적으로 한다.

### ④ 파생과 출처

- `derivation` 이름은 소스 선언의 허용 목록과 일치해야 한다.
- 같은 의미 규칙을 바꾸면 `source_translator_ver`가 바뀐다.
- 소스 이름을 코드에 하드코딩하지 말고 실행 중인 source를 provenance에 쓴다.

### ⑤ 픽스처

픽스처도 `gate → store` 경로를 사용한다. 게이트를 우회한 합성 데이터로는 실제
번역 경로를 검증할 수 없다. 합성 여부는 payload 또는 source 버전에서 식별 가능해야 한다.

### ⑥ 검증

최소 검증은 다음 네 가지다.

1. Source Contract가 모든 가능 발화를 `ready`로 판정한다.
2. dry-run의 실제 `atoms_rendered`가 기대 모양과 맞고 쓰기가 0이다.
3. 정상 분자는 전부 저장되고 잘못된 분자는 전부 거절되며 반쪽이 남지 않는다.
4. 재실행 시 커서·dedupe·provenance가 의도한 대로 동작한다.

기본 테스트:

```bash
pytest server/tests/test_ledger_source_contract.py
pytest server/tests/test_ledger_l1_unit.py
```

PostgreSQL 전용 테스트는 skip 수를 확인하고 별도로 실행한다.

## 3-bis. 테이블이 아닌 소스

생성기·계산 결과·외부 API처럼 관계명이 없는 소스는 `ledger_config.json`의 테이블
문법으로 위장하지 않는다. 생산 코드가 자기 source 선언과 `POSSIBLE_EMISSIONS`를
소유하되, 출력은 같은 `gate → store` 경로를 통과시킨다. 원천 참조는 재현 가능한
질의나 입력 식별자를 담아야 한다.

## 4. 운영

### 4.1 설치·백필

마이그레이션과 선언 순서는 [ONTOLOGY_LEDGER_SETUP §2](./ONTOLOGY_LEDGER_SETUP.md)가
소유한다. 백필 명령은 소스 문법과 무관하게 하나다.

```bash
cd server
conda run -n assy_manager python -m ledger.backfill --source <source>
```

### 4.2 어떤 경로가 도는가

`--source`는 이름만 고른다. 실제 드라이버는 해당 선언의 `kind`가 정한다.
운영자가 번역기 클래스 이름을 지정하지 않는다.

### 4.3 재실행 의미

| 실행 | 의미 |
|---|---|
| 같은 선언으로 재실행 | 커서 이후만 읽음; 끝났으면 0행 |
| `--reset-cursor` | 처음부터 다시 읽고 동일 provenance는 dedupe |
| 선언 변경 후 `--reset-cursor` | 새 `source_translator_ver`의 새 주장으로 기록될 수 있음 |

선언 변경 전에는 dry-run 결과와 영향 범위를 다시 확인한다.

### 4.4 숫자 읽기

- `rows_read`: 원천에서 읽은 행
- `molecules`: 독립 판정 단위
- `molecules_refused`: 전체 거절된 분자
- `molecules_incomplete`: 원천 일부가 아직 도착하지 않은 분자
- `atoms`: 통과한 Claim 수
- `rows_matching_nothing`: `declared` 규칙 어디에도 걸리지 않은 행

행 수와 원자 수는 같을 필요가 없다. 분자 수와 거절 수를 함께 봐야 한다.

### 4.5 정정

원장은 append-only다. 번역 오류는 과거 행을 UPDATE하지 않고 선언·번역기를 고친 뒤
새 provenance로 재백필한다. 기존 주장을 읽기에서 어떻게 밀어낼지는 해결 규칙이나
`supersedes` 계약으로 다룬다.

### 4.6 화면과 API

상태는 `coverage → structure → trace` 순서로 확인한다. 화면이 비었다고 바로 데이터
부재로 판단하지 말고 `absent`·`empty`·`ready` 상태를 구분한다.

#### 4.6-bis Structure

`/structure`는 선언과 실제 원장을 병합한다. `declared_only`는 선언됐지만 아직 원자가
없다는 뜻이고 `undeclared`는 원장에 있으나 현재 선언이 설명하지 못한다는 뜻이다.

#### 4.6-ter Kinds

`/kinds`의 `in_ledger`는 선언 여부, `ledger_state`와 `ledger_atoms`는 관측 상태다.
`null`은 측정 불가 또는 관계 부재이고 `0`은 측정했지만 원자가 없다는 뜻이다.

#### 4.6-quater Journey

`/journey`는 정확히 두 주어의 공정 구간을 순서대로 비교한다. 값 상태는 최소한
`recorded`, `recorded_null`, `not_recorded`, `segment_absent`를 구분한다. 같은 구간은
접고 실제로 다른 항목만 강조한다.

#### 4.6-quinquies Trend

Trend는 선언된 finding kind와 실제 검사 분모를 사용한다. 관측 부재를 0% 불량으로
표시하지 않는다. 시간 마킹은 trace·journey·map의 같은 주어 선택으로 이어져야 한다.

### 4.7 합성·픽스처 데이터 걷어내기

삭제 대상은 파일 목록이 아니라 provenance 술어로 정한다.

- 원장: 해당 `source_translator_ver` prefix 또는 명시적 synthetic 표지
- 커서: 같은 `source`
- 원천/보조 테이블: 생성기가 소유한 식별자나 method
- 셀 provenance가 있다면 해당 `updated_by`/source layer

실행 전 각 술어의 건수를 따로 세고, 운영 데이터와 겹치지 않음을 확인한다.

## 5. 원장이 일부러 하지 않는 것

- 원천 데이터를 정규화해 고쳐 쓰지 않는다.
- 관측 부재를 깨끗함으로 바꾸지 않는다.
- 모든 defect point를 기본 추적에 펼치지 않는다.
- claim 해결 결과를 원장 행 위에 덮어쓰지 않는다.
- 샘플 dry-run만으로 번역기의 모든 분기가 안전하다고 주장하지 않는다.

## 관련 문서

- [ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md) — 선언·배포 순서
- [LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md) — 저장·어휘·API 계약
- [backend §2](../architecture/backend.md) — 라우트 계약
- [LEDGER_RULINGS](../process/LEDGER_RULINGS.md) — 판정
