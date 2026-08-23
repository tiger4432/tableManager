# Canonical Ledger 개발·운영 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-08-23 — 은퇴 울타리 표시(§1.1·§1.2) · 범용 매퍼가 시각 Role을 채운다(§0) · 커서 지문과 재-스탬프(§4.2-bis) | **Owner:** Server / Ledger
> **Source-of-truth:** `server/ledger/` · ⛔ `server/ledger_trace_router.py`(**얼어 있다** — §1.1)

이 문서는 **새 소스를 붙이고 백필 결과를 확인하는 방법**만 설명한다.
정확한 필드·인덱스·응답 계약은 [LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md),
선언 순서는 [ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md), 결정 이유는
[CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md), 변경 이력은
[history](../history/README.md)가 소유한다.

> **Ledger V2 전환 주의:** 이 문서의 구 translator/source-kind/migration/reset 설명은 legacy
> 경로의 **역사**와 조회 의미를 이해하기 위한 것이다. 새 Source 설정은 반드시
> [ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md)의 단일 `ledger_config.json`과
> `read` → `prepare` → `map` → `bind` 경로를 따른다.
>
> 🔴 **[2026-08-18] 백필 실행 경로는 하나뿐이다.** 문법별 드라이버 넷과 그것을 고르던
> `mode` selector가 함께 은퇴했다. **선언이 곧 활성화다** — `server/config/ontology/ledger_config.json`의
> `sources`에 있는 소스가 돌고, 없으면 `undeclared_source`로 거절된다. 무엇이 선언돼
> 있는지는 쓰기 없는 dry-run이 답한다(`server/`에서):
> `conda run -n assy_manager python -m ledger.setup` → `config_root`·`setup_version`·
> `readiness`·`sources`를 JSON 한 줄로 낸다.
>
> 아래 §0·§1.1·§4.2에서 ⚰️로 표시한 이름은 **은퇴한 경로**다. 남아 있는 이유는 그 이름을
> 찾는 사람을 여기서 돌려세우기 위해서이고, 실행 지시로 읽지 않는다. 공개 CLI의 `--reset-cursor`와
> `--from`은 별도 승인 없이 `destructive_approval_required`로 거절되며, 이 문서의 옛
> 예를 실행 허가로 읽지 않는다.

---

## 0. 먼저 고를 것

새 소스는 [ONTOLOGY_LEDGER_SETUP §10](./ONTOLOGY_LEDGER_SETUP.md)의 Step 1~9를 따른다.
v2 선언에는 소스 「문법(`kind`)」이 **없다** — 소스 하나가 `relation`·`read`·`prepare`·`map`·
`bind` 다섯 절을 실행 순서대로 **직접** 든다(🔴 2026-08-21 `setup_version: 5`; 옛 `driver`와
`preparer_id`·`mapper_id`·`profile_id` 참조, 그리고 `packs`/`claims` section은 은퇴했다). 고르는 것은 문법이 아니라
**Python을 쓸지 말지**다.

| 소스 모양 | 선택 |
|---|---|
| 출력 컬럼이 상속한 verified join에서 그대로 온다 | Preparer `direct-join@1` — Python 0줄 |
| 업무적 읽기가 `bind` binding만으로 표현된다 | Mapper `declarative-role@1` — Python 0줄 |
| 행을 쪼개거나 도메인 규칙으로 해석해야 한다 | `server/mappers/ledger_v2_*.py`에 전용 mapper 파일 **하나** |
| 정규화·그룹 조립처럼 계산이 필요하다 | `server/ledger/`에 `BaseSourcePreparer` 하위 클래스 |

✅ **[2026-08-23 `189193a4`] 범용 매퍼가 «시각 Role»을 채운다 — 그전에는 못 했다.**
`declarative-role@1`은 모든 binding을 프레임 셀 그대로 읽었으므로 varchar 시각 컬럼을 문자열로
집어 `invalid_time_role`로 거절했고, 전용 매퍼 둘이 각자 변환하며 그 칸을 **가리고** 있었다.
이제 Role kind가 `time`이면 준비 경계가 이미 해석한 `__occurred_at`을 읽는다
([ONTOLOGY_LEDGER_SETUP §7.9](./ONTOLOGY_LEDGER_SETUP.md)). **「Python 0줄」이 시각 있는 소스에
대해 참이 된 것이 이 수리다** — 소유자가 폼만으로 만든 첫 소스가 그것을 요구했다.

기본 원칙은 **먼저 범용 구현 둘로 끝나는지 보고, 안 되는 부분만 코드로 쓴다**이다.
구현 클래스는 자기 `implementation_id`/`implementation_version`을 선언하고
`server/ledger/implementations.py`가 **코드에서 발견**한다 — 손으로 유지하는 등록 목록은 없다.

⚰️ **[2026-08-18] 옛 `kind` 문법(`declared`/`lineage`/`transfer`/`observation`)은 백필 경로에서
은퇴했다.** `server/ledger/config.py`의 `SOURCE_KINDS`가 남아 있는 곳은 레거시 선언을 읽는
어드민 dry-run 쪽이고, 백필 드라이버는 하나다. 그 이름을 찾고 있다면 은퇴한 경로다.

## 1. 모듈 지도

### 1.1 쓰기 쪽

🔴 **[2026-08-23 · 은퇴 울타리] 아래 표에서 ⛔가 붙은 것은 «얼어 있다».** 소유자 순서가
① 셋업 완주 → ② 응용 → ③ 은퇴이고, ③이 데려갈 모듈이 파일 «이름»이 아니라 **파일 단위
실측 목록**으로 그어졌다(이름 글롭으로는 넷이 빠져나갔다). **그 위에 새 일을 얹지 않는다** —
계약이 낡아 보여도 갱신 대상이 아니라 기록이다. 목록의 정본은
[PROJECT_STATUS](../process/PROJECT_STATUS.md)의 2026-08-23 10:3x 블록.

| 파일 | 역할 |
|---|---|
| ⛔ `config.py` | 소스 문법 검증과 버전 해시. **얼어 있다**(v1 계통과 함께 ③에서 간다) |
| `source_contract.py` | 선언 → 번역 프로필 → 가능한 Claim → live vocabulary 결합 검사 |
| `runtime_v2.py` · `source_preparation.py` · `roleframe.py` · `source_profile*.py` | **v2 실행 경로** — `prepare` → `map`/RoleFrame → Pack/`bind` |
| `setup_bundle.py` · `setup_registry.py` · `setup.py` | 단일 `ledger_config.json` 검증·compile과 로드 경계(`load_setup`) |
| `implementations.py` | 어떤 `implementation_id`가 실행 가능한지 **코드에서 발견**해 답한다 |
| ⚰️ `*_translator.py` · `translator_pattern.py` · `examples/grouped_translator_template.py` | **파일이 없다.** 이들을 지연 import하던 문법 드라이버 넷이 `backfill.py`에서 빠지고(`d7bfcd0`), 이어서 번역기 다섯과 그것을 재던 테스트가 함께 지워졌다(`e47d325`). `SafeTranslatorTemplate`·`POSSIBLE_EMISSIONS`도 트리에 없다. 이 이름을 찾고 있다면 은퇴한 경로다 — 지금의 대체물은 §0 표의 네 갈래 |
| `gate.py` | 분자 단위 전부-아니면-전무 검사와 거절 계수 |
| `store.py` | 원자 append와 커서 전진을 한 트랜잭션으로 저장 |
| `backfill.py` | 페이지·분자 경계와 **유일한** 실행 드라이버 |
| ⚰️ `dry_run.py` | `POST /admin/ledger/dry-run` 전용. 백필 경로가 **아니다**. 🔴 **[2026-08-18 `ab8657f`] 소스 미리보기는 여기서 사라졌다** — 태우던 v1 번역기 넷이 은퇴하면서 `preview()`가 `DryRunUnavailable`을 던지고 화면은 거절 문장을 받는다. 남은 실물은 `begin_read_only`(쓰기 0을 DB의 거절로 거는 자리)이고, 쓰기 없는 v2 미리보기는 `ledger/setup.py`의 `preview_selected_cursor_batch`인데 **부르는 라우트가 아직 없다** |

### 1.2 읽기 쪽

| 질문 | API |
|---|---|
| 원장 준비 상태 | `GET /api/ledger/coverage` |
| ⛔ 특정 개체 추적 | `GET /api/ledger/trace` (`ledger_trace.py` — **얼어 있다**) |
| ⛔ 구조와 선언·관측 차이 | `GET /api/ledger/structure` (`ledger_structure.py` — **얼어 있다**) |
| 결함 종류와 원장 상태 | `GET /api/ledger/kinds` |
| ⛔ 두 주어의 공정 차이 | `GET /api/ledger/journey` (`ledger_journey.py` — **얼어 있다**) |
| 증거 서브그래프 | `GET /api/ledger/subgraph` (`ledger_subgraph.py` — **얼지 않았다.** 응용 라운드가 여기 위에서 자란다) |

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

[ONTOLOGY_LEDGER_SETUP §10](./ONTOLOGY_LEDGER_SETUP.md)의 Step 1~9에 따라
`ledger_config.json`을 작성한다. 물리 컬럼명은 `sources.<id>`의 `relation`·`read`와
`prepare`/`map`의 `input_columns`에만 두고 **구현 코드에는 넣지 않는다.**

### ③ 전용 mapper 작성 — 파일 하나

범용 `declarative-role@1`로 표현할 수 없을 때만 쓴다. `server/mappers/ledger_v2_*.py`에
`BaseLedgerMapper` 하위 클래스를 두고 세 가지만 쓴다.

1. `implementation_id` / `implementation_version` — 클래스가 자기를 선언한다
2. **말할 수 있는 문장들** — `SentenceShape` 클래스 속성. 🔴 **속성명이 곧 그 문장의
   별명이고, 그것이 config의 `bind.mappings` 키다**(2026-08-21 `e795c706`)
3. `interpret_unit()` — 한 source event를 읽어 `RoleEmission`을 낸다

🔴 **mapper는 선언의 이름을 하나도 모른다.** predicate 철자(`has_wafer@1`)도 entity type
이름(`Lot@1`)도 이 파일에 없다 — 그것들은 배포마다 바뀌는 운영자의 낱말이고, 「다른 스키마의
운영 환경에서 코드 0줄」이 완성 조건이기 때문이다. mapper가 아는 것은 **자기가 그 문장을
부르는 별명**이고, 그 별명이 어느 술어가 되는지는 `bind.mappings.<별명>.predicate` 한 칸
옆에 있다 — 그 술어가 채워야 할 Role까지 정한다(`9b6c5da`로 `use`와 `packs`가 함께 갔다). 배선을 대신해 주는 것은 `ledger.roleframe.ProfileSentences`다.

🔴 **문장 해석은 탐색이 아니라 조회다** (2026-08-21 `e795c706`). 종전에는 목적어 유무 → qualifier
집합 → subject type → object type 순으로 비교하고 **마지막에야** 이름을 봤다. 그런데 이름은
양쪽이 이미 합의하고 있던 유일한 것이었다 — mapper가 `SentenceShape` 속성으로 선언하고
config가 그것을 키로 쓴다. 그래서 `_sentence_signature`·`_ambiguous_sentences`·`has_object`와
`say()`가 받던 `subject_type`/`object_type` selector가 **표현할 수 없는 상태가 돼서** 함께
없어졌다. `mapping_id`와 `sentence`는 이름 둘을 쓰던 같은 문자열이었고, mapper가 실제로
선언하는 쪽이 살아남았다.

`lot_event`의 split slot-carry와 merge slot-join은 predicate·주어·목적어·qualifier가 전부
같고 계산 규칙만 다르다 — 이제는 그냥 별명이 `split_slot_carry`·`merge_slot_join` 둘이다.
구조 탐색이 **실제로** 실패하던 자리는 `FIRST_SIGHT` 쪽이었다: 같은 소스가 두 번 말하는데
구조로는 안 갈라져 `subject_type`을 넘겨야 했다. 지금은 `first_sight_holder`·`first_sight_item`
두 이름이고 selector 인자는 할 일이 없다.

⚠️ **한 `SentenceShape`를 두 별명에 묶지 않는다.** 그러면 클래스가 `ambiguous_sentence_shape`로
거절한다(`roleframe.SentenceShape.__set_name__`). 문장 둘이면 shape 둘이지, shape 하나에
이름을 붙여 가르는 것이 아니다.

📌 `subject_type_of()`/`object_type_of()`는 **남아 있지만 라이브 호출자가 0이다** — 별명
아래서는 entity type 철자를 물을 일이 없어졌다. 지우는 것은 mapper 대상 기능을 없애는 일이라
범위 밖으로 두고 보고됐다(`80185133`).

시각 해석·raw reference·게이트 호출·거절 격리는 `BaseLedgerMapper.map()` 경계와 공유
드라이버(`backfill.run`)가 맡는다. `server/ledger/implementations.py`는 편집하지 않는다 —
그 모듈이 클래스를 **발견**한다.

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

생성기·계산 결과·외부 API처럼 관계명이 없는 소스는 `ledger_config.json`의 relation
문법으로 위장하지 않는다. `sources.<id>.relation`은 `table_config.json`에 선언된 표여야
하고, 없는 이름을 적으면 `unknown_relation`으로 거절된다. 생산 코드가 자기 source 선언과
낼 수 있는 Claim 전수를 소유하되, 출력은 같은 `gate → store` 경로를 통과시킨다. 원천
참조는 재현 가능한 질의나 입력 식별자를 담아야 한다.

## 4. 운영

### 4.1 설치·백필

선언 작성 순서는 [ONTOLOGY_LEDGER_SETUP §10](./ONTOLOGY_LEDGER_SETUP.md)이 소유하고,
**마이그레이션 명령은 [OPERATOR_RUNBOOK §6](../process/OPERATOR_RUNBOOK.md)이 소유한다**
(설정 가이드는 v2 선언 작성 전용이라 마이그레이션을 다루지 않는다). 백필 명령은 소스
문법과 무관하게 하나다.

```bash
cd server
conda run -n assy_manager python -m ledger.backfill --source <source>
```

### 4.2 어떤 경로가 도는가 — 하나뿐이다

`--source`는 **이름만** 고른다. 운영자가 번역기 클래스 이름을 지정하는 일은 없다.
🔴 **[2026-08-18] 드라이버는 하나다.** 문법별 드라이버 넷과 그것을 고르던 selector가 함께
은퇴했다. 백필은 `server/config/ontology/ledger_config.json`의 `sources`를 보고, 이름이
거기 있으면 그 소스를 돌린다.

**선언이 곧 활성화다** — `sources`에 있으면 돈다. 「선언은 해 두고 꺼 놓기」를 하던
`dataflows/chains.json`의 `mode`/`parity_status`는 없다.

이름이 `sources`에 없으면 `REFUSE_UNDECLARED_SOURCE`(`"undeclared_source"`)로 **거절**된다
(원자 0 · 커서 미이동 — 조용한 0건 성공이 아니다).

무엇이 선언돼 있는지는 쓰기 없는 dry-run이 답한다.

```bash
cd server
conda run -n assy_manager python -m ledger.setup
```

이 문서는 소스 이름도 개수도 적지 않는다 — 위 명령의 `sources` 배열이 정본이다.

### 4.2-bis 커서 지문(fingerprint) — 선언을 고치면 커서가 서는 자리 (2026-08-22)

소스마다 **cursor fingerprint**가 있다(`setup_registry.source_cursor_fingerprint`). 저장된
지문과 현재 선언의 지문이 다르면 그 소스의 커서는 `cursor_snapshot_reset_required`로 **선다** —
「원자를 다르게 만들 수 있는 선언이 바뀌었으니 사람이 보라」는 뜻이다.

🔴 **이 지문은 «크게» 잡는 것이 기본이고, 예외는 오늘 둘뿐이다.**
`prepare.input_columns`와 `map.input_columns`는 **해시 재료에서 빠져 있다**(`91f9afde`) —
넓히면 SELECT만 넓어지고 매퍼 입력은 그대로라 **원자가 같은 원자**이고, 좁히면 지문이 아니라
`roleframe`의 `missing_mapper_input`이 **쓰기 전에** 이름 대어 거절하기 때문이다. 이 예외가
필요해진 이유는 [작성 화면의 전체-켜짐 기본값](./ONTOLOGY_LEDGER_SETUP.md)이 **모든 소스의 첫
저장마다** 이 두 칸을 건드리기 때문이다. **다른 키를 여기 더하지 마라** — 예외마다 코드에 그
두 방향 증명이 붙어 있고, 없으면 넣지 않는다.

🔴 **그 예외를 들이면 모든 지문이 «한 번» 움직인다** — 정규 JSON이 값이 비어 있어도 키를 실어
왔기 때문이다. 흡수는 전용 도구가 한다.

```bash
cd server
conda run -n assy_manager python scripts/ledger_restamp_cursor.py            # 보고만 (쓰기 0)
conda run -n assy_manager python scripts/ledger_restamp_cursor.py --apply    # 저장된 지문만 교체
```

- **커서 «위치»는 안 건드린다.** 저장된 문자열만 바꾸므로 행을 다시 읽지 않고 원자를 다시 내지
  않는다. 실행 전후로 커서 위치와 원자 수가 그대로인지 확인하는 것이 이 도구의 수용 조건이다.
- 🔴 **반쯤 만든 소스가 있어도 돈다** — strict 로드를 먼저 시도하고, 실패하면 explorer가 쓰는
  **관용 읽기로 폴백**한다. 컴파일 안 된 소스는 **경로와 함께 이름을 대고** 건너뛴다(조용한
  skip이 아니다). 우회 플래그는 없다. 작성 화면이 켜져 있는 동안 번들이 통째로 컴파일되는 일이
  드물어서, 그렇지 않으면 **사람이 일하는 바로 그때** 이 도구가 멈춘다.

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

원장은 append-only다. 해석 오류는 과거 행을 UPDATE하지 않고 선언·mapper를 고친 뒤
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

#### 4.7-bis 픽스처에게 «자기 표»를 주는 것이 필터를 가르치는 것보다 싸다 (2026-08-23 `347c9069`)

전사(die transfer) 픽스처는 처음에 `dt_log`에 썼고, 그 표를 읽는 소스가 **거절**했다 —
데이터가 틀려서가 아니라 **소스가 남의 행까지 읽었기 때문**이다(`dt_cell_key`로 정렬하니 첫
행이 `b_wx` 없는 옛 행이고, 그 컬럼이 빈 행이 3만 4천이었다). 수리는 소스에 필터를 가르치는
것이 아니라 **전사 로그에 자기 relation을 주는 것**이었다: `dt_transfer_log`(선언 12컬럼).

- 🔴 **표를 «선언하는 것»이 표를 만든다** — config watcher가 modify에서
  `create_missing_dynamic_tables`를 부르므로 **마이그레이션을 쓰지 않는다.** ⚠️ 그 경로가
  만드는 업무키 인덱스는 **UNIQUE가 아니다**(기존 마이그레이션이 그 자리를 덮는다).
- 🔴 **라이브 `table_config.json`은 gitignore라 선언이 이 박스에만 산다** — 커밋에 들어간 것은
  `server/config/sample/table_config.json.sample`뿐이고, **다른 곳에서 돌리려면 거기서 다시
  선언해야 한다.** 같은 날 선언 둘이 조용히 죽은 것이 그 실패다.
- 🔴 **롤백은 목록이 아니라 술어 하나**로, **키를 쓴 것과 같은 상수**에서 만든다(그래야 드리프트가
  불가능하다). 지우는 것은 원시 DELETE가 아니라 **소스·오버라이트를 캐스케이드하고 이력을 쓰는
  경로**로 명시적 row id를 태운다 — 원시 삭제는 그것들을 고아로 남긴다.
- 씨더: `server/scripts/seed_syn_die_transfer.py`. 채우기 순서를 **다시 구현하지 않고**
  `map_alignment.serpentine_index`를 부른다(그 docstring이 두 번째 구현을 금지한다). 기하는
  `valid_die_ref`에서 오고 생성하지 않는다. `--apply` 외에 **두 번째 명시 플래그**가 있어야
  쓴다(라이브 DB 쓰기 가드 — 요구된 적 없고 총괄이 걷어낼 수 있다).

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
