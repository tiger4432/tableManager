# Canonical Ledger 개발·운영 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-08-31 (§1.2 라우트가 «둘»에서 «셋»으로 — `gaps` 신설 · `declaration` 에 `sources` 절 · **§4.1-bis 페이싱 · §4.1-ter 범위 재번역 신설**) · 직전 2026-08-29 밤 (§1.2 `/subgraph` 에 대조 쌍 `reach`/`reachable`) | **Owner:** Server / Ledger
> **Source-of-truth:** `server/config/ontology/ledger_config.json`(선언) · `server/ledger/`

이 문서는 **새 소스를 붙이고 백필 결과를 확인하는 방법**만 설명한다.
필드·인덱스·응답 계약은 [LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md),
선언 작성 순서는 [ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md), 결정 이유는
[CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md), 변경 이력은
[history](../history/README.md)가 소유한다.

## 🏛️ 기둥 둘

```
① 원장은 «선언» 위에 서 있다   선언 파일 «하나»가 entities · vocabulary · sources 를 전부 정한다
                            개정 6: 노드는 «선언된 엔터티»뿐, 엣지는 «선언된 술어»뿐이다
② 답은 «walk» 이 한다         읽기측은 마킹에서 걸어 서브그래프를 만든다. 차트는 그것을 보는 창이다
```

🔴 **「원자가 «전부» 선언에서 났다」고 적지 마라 — 선언이 그것을 약속하지 않는다.**
자세한 것은 아래 §4.1 의 두 번째 문. 종전 이 자리에 그 문장이 실측 수와 함께 있었다.

🔴 **선언이 곧 활성화다.** `sources` 에 있는 소스가 돌고, 없으면 `undeclared_source` 로 거절된다
(원자 0 · 커서 미이동 — 조용한 0건 성공이 아니다). 「선언은 해 두고 꺼 놓기」는 없다.

---

## 0. 먼저 고를 것 — 문법이 아니라 「Python 을 쓸지 말지」

소스 하나가 `relation` · `read` · `prepare` · `map` · `bind` 를 **실행 순서대로 직접** 든다.
소스 「문법(kind)」을 고르는 축은 없다.

| 소스 모양 | 선택 |
|---|---|
| 출력 컬럼이 상속한 verified join 에서 그대로 온다 | Preparer `direct-join@1` — Python 0줄 |
| 업무적 읽기가 `bind` 만으로 표현된다 | Mapper `declarative-role@1` — Python 0줄 |
| 행을 쪼개거나 도메인 규칙으로 해석해야 한다 | `server/mappers/ledger_v2_*.py` 에 전용 mapper 파일 **하나** |
| 정규화·그룹 조립처럼 계산이 필요하다 | `server/ledger/` 에 `BaseSourcePreparer` 하위 클래스 |

**먼저 범용 구현 둘로 끝나는지 보고, 안 되는 부분만 코드로 쓴다.**
구현 클래스는 자기 `implementation_id`/`implementation_version` 을 선언하고
`server/ledger/implementations.py` 가 **코드에서 발견**한다 — 손으로 유지하는 등록 목록은 없다.
`declarative-role@1` 은 시각 Role 도 채운다(Role kind 가 `time` 이면 준비 경계가 이미 해석한
`__occurred_at` 을 읽는다). 그래서 「Python 0줄」이 시각 있는 소스에도 참이다.

## 1. 모듈 지도

### 1.1 쓰기 쪽

| 파일 | 역할 |
|---|---|
| `setup_bundle.py` · `setup_registry.py` · `setup.py` | 선언 «검증·compile» 과 로드 경계 |
| `config.py` | 선언 로더(`load`)와 소스별 접근자 |
| `source_contract.py` | 선언 → 프로필 → 가능한 발화 → 선언의 서명 결합 검사 |
| `source_preparation.py` · `runtime_v2.py` · `roleframe.py` · `source_profile*.py` | 실행 경로 — `prepare` → `map`/RoleFrame → `bind` |
| `implementations.py` | 어떤 `implementation_id` 가 실행 가능한지 코드에서 발견해 답한다 |
| `gate.py` | 분자 단위 전부-아니면-전무 검사와 거절 계수 |
| `store.py` | 원자 append 와 커서 전진을 «한 트랜잭션»으로 |
| `backfill.py` | 페이지·분자 경계와 **선언을 거치는 유일한** 실행 드라이버 |
| `dry_run.py` | `POST /admin/ledger/dry-run` 전용. 백필 경로가 «아니다» |

### 1.2 읽기 쪽

**라우트는 «셋»이다** (실측 2026-08-31 — `server/ledger_trace_router.py` 의 `@router.get` 전수).
🔴 **[2026-08-31] 종전 이 자리는 「둘」이었고 그것이 거짓이 됐다** — `gaps` 가 붙었다.
⚠️ **그래도 «데이터»에 답하는 것은 `subgraph` 하나다** — 나머지 둘은 «선언에 대해» 답한다.

| 질문 | API |
|---|---|
| 마킹에서 걸어 서브그래프 | `GET /api/ledger/subgraph` |
| 선언 자체 (원장을 안 읽는다) | `GET /api/ledger/declaration` — 🆕 **`sources[]` 절이 붙었다**: `{source, relation, emits[], scope_columns[]}`. `scope_columns` 가 곧 범위 재번역(§4.1-ter)이 허용하는 그 목록이다. 🔴 **못 읽으면 키를 «비우지 않고 뺀다»**(부재 = 「모른다」, 빈 배열 = 「없다」) |
| **무엇이 아직 «없나»** | 🆕 `GET /api/ledger/gaps` — 인자 없으면 질문 «이름»만(DB 접근 0), `?name=` 이면 그 하나를 «잰다»(읽기 전용). 찾는 것은 코드가 **어휘를 순회**해서 하고, 부르는 이름은 `server/ledger/gap_names.json` 이 준다 — **코드에 도메인 낱말이 없다**. 「0」이 세 갈래(정말 없음 · 표본이 다 못 봄 · 해당 없음)로 갈려 나오고 `count_kind` 가 함께 온다 |

⚰️ **[2026-08-28] 종전 이 표에 있던 나머지 여덟은 «없다»** — `subgraph/table` · `structure` ·
`trends` · `lot_map` · `composition` · `siblings` · `kinds` · `selection/resolve`, 그리고 그 앞의
`trace` · `explore` · `explore_entity` · `coverage` · `journey` · `lots`.
**전부 «키를 받는» 라우트였다**: 키를 받으면 키마다 한 번씩 불릴 수밖에 없고, 마킹을 받으면
마킹 «전체»에 한 번 답한다. 답을 늘리는 것은 «선언»이지 갈래가 아니다.
⚠️ 이 주소들은 410 을 «안» 답한다 — SPA 폴백이 index.html 을 200 으로 준다.

파라미터와 응답 계약은 [backend §2](../architecture/backend.md) 가 정본이다.

## 2. 쓰기 경로

```text
source rows
  → 선언 검증 (setup_bundle)
  → Source Contract 검증
  → 분자 묶기 (read.unit)
  → 원자 (prepare → map → bind)
  → 게이트 검사
  → ledger_events + 커서 커밋
```

- **분자**는 혼자 참이어야 하는 최소 묶음이다. 한 파편이 틀리면 전체를 거절한다.
- `source_raw_ref` 는 원천 행으로 돌아갈 수 있어야 한다.
- `occurred_at` 은 «세계에서 사실이 성립한 시각»이다. 적재 시각으로 대신하지 않는다.
- 원자와 커서는 같은 트랜잭션에 저장한다.

## 3. 새 소스 붙이는 법

### ① 낱말 검사

선언의 `vocabulary` 와 `entities` 로 표현할 수 있는지 먼저 본다.
새 술어는 주어·목적어 모양·수식어까지 완결된 서명으로 «선언»해야 한다.
🔴 **낱말도 개체 타입도 선언 소유다.** 코드에 목록이 없다 —
지금 이 환경이 아는 것은 `GET /api/ledger/declaration` 이 답한다.

### ② 선언 작성

[ONTOLOGY_LEDGER_SETUP §10](./ONTOLOGY_LEDGER_SETUP.md) 을 따른다.
물리 컬럼명은 `sources.<id>` 의 `relation`·`read` 와 `prepare`/`map` 의 `input_columns` 에만
두고 **구현 코드에는 넣지 않는다.**

### ③ 전용 mapper — 파일 하나

범용 `declarative-role@1` 로 표현할 수 없을 때만. `server/mappers/ledger_v2_*.py` 에
`BaseLedgerMapper` 하위 클래스를 두고 세 가지만 쓴다.

1. `implementation_id` / `implementation_version` — 클래스가 자기를 선언한다
2. **말할 수 있는 문장들** — `SentenceShape` 클래스 속성.
   🔴 **속성명이 곧 그 문장의 별명이고, 그것이 선언의 `bind.mappings` 키다**
3. `interpret_unit()` — 한 source event 를 읽어 `RoleEmission` 을 낸다

🔴 **mapper 는 선언의 이름을 하나도 모른다.** 술어 철자도 개체 타입 이름도 이 파일에 없다 —
그것들은 배포마다 바뀌는 운영자의 낱말이고, 「다른 스키마의 운영 환경에서 코드 0줄」이
완성 조건이기 때문이다. mapper 가 아는 것은 **자기가 그 문장을 부르는 별명**이고,
그 별명이 어느 술어가 되는지는 `bind.mappings.<별명>.predicate` 한 칸이 정한다.
배선은 `ledger.roleframe.ProfileSentences` 가 한다.

⚠️ **한 `SentenceShape` 를 두 별명에 묶지 않는다** — `ambiguous_sentence_shape` 로 거절된다.
문장 둘이면 shape 둘이지, shape 하나에 이름을 붙여 가르는 것이 아니다.

🔴 **[2026-08-31] 전용 mapper 가 «못 하는» 것 하나 — 주어의 키가 둘 이상이면 안 된다.**
mapper 가 넘기는 Entity 참조는 **식별 키를 «하나»만 나른다**(거절은 `roleframe._entity_value`
가 낸다: 「a mapper-supplied Entity reference carries one identity key」). 그래서 주어가
키 «둘»인 타입이면 그 문장은 **전용 mapper 로 쓸 수 없고 원자가 0 이 된다** — 오류 없이,
그냥 아무것도 안 만들어진다.
**처방은 mapper 를 고치는 것이 아니라 «소스를 하나 더 만드는» 것이다** — 그 두 키를 컬럼으로
펼친 **뷰**를 만들고, 그 뷰를 읽는 소스를 범용 `declarative-role@1` 로 선언한다.
실례: 좌석↔웨이퍼 문장이 그렇게 옮겨 갔다(뷰 `lot_slot_wafer` ← `server/scripts/create_lot_slot_wafer_view.py`,
새 소스 하나 · 술어 하나). 옮기면서 옛 mapper 의 문장 셋이 은퇴했다.
⚠️ **「원자가 0 인데 거절도 0」이면 이 계급을 먼저 의심하라** — 주어의 키 개수를 세는 것이 가장 빠르다.

시각 해석·raw reference·게이트 호출·거절 격리는 `BaseLedgerMapper.map()` 경계와
`backfill.run` 이 맡는다. `implementations.py` 는 편집하지 않는다 — 그 모듈이 클래스를 «발견»한다.

### ④ 파생과 출처

- `derivation` 이름은 소스 선언의 허용 목록과 일치해야 한다.
- 같은 의미 규칙을 바꾸면 `source_translator_ver` 가 바뀐다.
- 소스 이름을 코드에 하드코딩하지 말고 실행 중인 source 를 provenance 에 쓴다.

### ⑤ 픽스처

픽스처도 `gate → store` 경로를 쓴다. 게이트를 우회한 합성 데이터로는 실제 경로를 검증할 수 없다.
합성 여부는 payload 또는 source 버전에서 식별 가능해야 한다.

### ⑥ 검증

```bash
cd server && conda run -n assy_manager python -m pytest tests/test_ledger_source_contract.py tests/test_ledger_l1_unit.py
```

최소 넷: Source Contract 가 모든 가능 발화를 `ready` 로 판정 · dry-run 의 `atoms_rendered` 가
기대 모양이고 쓰기 0 · 정상 분자는 전부 저장되고 잘못된 분자는 전부 거절되며 반쪽이 안 남음 ·
재실행 시 커서·dedupe·provenance 가 의도대로. PostgreSQL 전용 테스트는 skip 수를 확인하고
별도로 돌린다.

## 3-bis. 테이블이 아닌 소스

생성기·계산 결과·외부 API 처럼 관계명이 없는 소스는 relation 문법으로 위장하지 않는다.
`sources.<id>.relation` 은 `table_config.json` 에 선언된 표여야 하고, 없는 이름은
`unknown_relation` 으로 거절된다. 생산 코드가 자기 source 선언과 낼 수 있는 발화 전수를
소유하되, 출력은 같은 `gate → store` 경로를 통과시킨다.

⚠️ **라이브 `table_config.json` 은 gitignore 라 선언이 그 박스에만 산다.**
커밋에 들어가는 것은 `server/config/sample/table_config.json.sample` 뿐이므로,
다른 곳에서 돌리려면 거기서 다시 선언해야 한다.
표를 «선언하는 것»이 표를 만든다 — config watcher 가 `create_missing_dynamic_tables` 를
부르므로 마이그레이션을 쓰지 않는다. ⚠️ 그 경로가 만드는 업무키 인덱스는 UNIQUE 가 아니다.

## 4. 운영

### 4.1 백필

```bash
cd server
conda run -n assy_manager python -m ledger.backfill --source <source>
```

`--source` 는 **이름만** 고른다.
마이그레이션 명령은 [OPERATOR_RUNBOOK §6](../process/OPERATOR_RUNBOOK.md) 이 소유한다.

🔴 **「드라이버는 하나뿐이다」는 «선언을 거치는 길»에만 참이다** (실측 2026-08-29).
`store.write_batch` 를 직접 부르는 파일이 `server/scripts/` 에 «일곱» 있다 —
`seed_syn_complex_composite` · `seed_syn_composite_chip` · `seed_syn_journey_atoms` ·
`seed_syn_lot_excursion` · `seed_syn_process_ledger` · `seed_syn_split_merge_pressure` ·
`seed_syn_world`. 그 문으로 들어온 원자는 **선언에 이름이 없어서 walk 의 주어가 되지 못한다.**
정당한 호출자는 `server/ledger/runtime_v2.py` «하나»이고, 상설 규율은
**「표에 원천 데이터를 넣고 그걸로 원장」** 이다. 새로 `write_batch` 를 부르고 싶어지면
멈추고 올린다 — 답은 대개 「표를 만들어라」다.

무엇이 선언돼 있는지는 «쓰기 없는» dry-run 이 답한다:

```bash
cd server
conda run -n assy_manager python -m ledger.setup
```

`config_root` · `setup_version` · `readiness` · `sources` 를 JSON 한 줄로 낸다.
**이 문서는 소스 이름도 개수도 적지 않는다** — 그 `sources` 배열이 정본이다.

⚠️ `--reset-cursor` 와 `--from` 은 별도 승인 없이 `destructive_approval_required` 로 거절된다.

#### 4.1-bis 도는 동안 옆 질의를 굶기지 않기 — `--pace` (2026-08-31 신설)

```bash
conda run -n assy_manager python -m ledger.backfill --source <source> --pace slow
```

`fast`(기본 · 오늘까지의 행동 그대로) · `slow` · `trickle`. 선언은 **`server/pacing.json` 하나**이고
**파일 인제션도 같은 표를 읽는다**(그쪽 이름은 `ingestion_settings.json` 의 `ingestion_pace`).
백필의 한 사이클 단위는 **페이지**이고 인제션은 **청크**다 — 표가 정하는 것은 «리듬»이지 «양»이 아니다.
모르는 이름은 **거절**한다(오타를 안은 채 전속력으로 도는 것을 막는다).
⚠️ 도는 중에 그 파일을 고쳐도 **그 실행에는 안 듣는다** — 읽기가 실행 시작마다 한 번이다.
🔴 **CLI 도움말이 `ledger/pacing.json` 이라 적지만 실제 경로는 `server/pacing.json` 이다**(2026-08-31 실측).

#### 4.1-ter 범위를 정해 다시 번역하기 — `--scope-column` (2026-08-31 신설)

해석을 고쳤는데 이미 적재된 원자가 옛 해석 그대로일 때, **전부 다시**와 **그냥 둔다** 사이의 셋째 길이다.

```bash
# 드라이런 — 무엇을 회수하고 무엇을 다시 만들지만 답한다. 한 줄도 안 쓴다
conda run -n assy_manager python -m ledger.backfill --source <source> \
    --scope-column <컬럼> --scope-values a,b,c
# 실행
… --apply
```

- 🔴 **커서를 «안» 움직인다.** 커서 행은 위치만이 아니라 누적 계수(`molecules_done`·`atoms_written` …)를 들기 때문에, 이미 지나온 행을 다시 쓰면서 그것을 더하면 **진행도가 앞으로 뛴다.** 그래서 커서 «문장을 통째로» 건너뛴다.
- 🔴 **범위 컬럼은 «그 소스가 읽는 컬럼»이어야 한다.** 아니면 `scope_column_not_declared` 로 **허용 목록을 대며** 거절하고, 값이 비면 `scope_values_empty` 로 거절한다 — 「아무것도 안 고르는 범위」를 통과시키면 «전체»가 돈다.
- ⚠️ **`scope` 는 `limit` 이 아니다** — 「어느 행」이지 「몇 행」이 아니고, 페이징 술어를 대체하지 않고 AND 로 걸린다.
- 🔴 **회수와 재생성이 «두 커밋»이라 그 사이에서 죽을 수 있다** — 원자가 빠진 채 아직 안 돌아온 상태로 남는다. 그래서 어드민 등록부에서 이 연산은 **취소 불가**이고, **복구는 「같은 범위를 다시 돌리는 것」**이다.
- 어드민 표면(연산 `ledger_rescope`)·취소 규약은 [BACKFILL_GUIDE §7](./BACKFILL_GUIDE.md), 재사용 관점은 [PRIMITIVES §1](../architecture/PRIMITIVES.md).

### 4.2 커서 지문 — 선언을 고치면 커서가 서는 자리

소스마다 **cursor fingerprint** 가 있다(`setup_registry.source_cursor_fingerprint`).
저장된 지문과 현재 선언의 지문이 다르면 그 소스의 커서는 `cursor_snapshot_reset_required` 로
**선다** — 「원자를 다르게 만들 수 있는 선언이 바뀌었으니 사람이 보라」는 뜻이다.

🔴 **지문은 «크게» 잡는 것이 기본이고, 예외는 둘뿐이다.**
`prepare.input_columns` 와 `map.input_columns` 는 해시 재료에서 빠져 있다 — 넓히면 SELECT 만
넓어지고 매퍼 입력은 그대로라 «원자가 같은 원자»이고, 좁히면 지문이 아니라 `roleframe` 의
`missing_mapper_input` 이 **쓰기 전에** 이름 대어 거절하기 때문이다.
**다른 키를 여기 더하지 마라** — 예외마다 코드에 그 두 방향 증명이 붙어 있다.

지문만 교체하는 전용 도구:

```bash
cd server
conda run -n assy_manager python scripts/ledger_restamp_cursor.py
```

`--apply` 를 붙이면 저장된 지문만 교체한다. 붙이지 않으면 보고만 하고 쓰기가 0이다.

- **커서 «위치»는 안 건드린다.** 실행 전후로 커서 위치와 원자 수가 그대로인 것이 수용 조건이다.
- 반쯤 만든 소스가 있어도 돈다 — strict 로드를 먼저 시도하고 실패하면 관용 읽기로 폴백하며,
  컴파일 안 된 소스는 «경로와 함께 이름을 대고» 건너뛴다(조용한 skip 이 아니다).

### 4.3 재실행 의미

| 실행 | 의미 |
|---|---|
| 같은 선언으로 재실행 | 커서 이후만 읽음; 끝났으면 0행 |
| `--reset-cursor` | 처음부터 다시 읽고 동일 provenance 는 dedupe |
| 선언 변경 후 `--reset-cursor` | 새 `source_translator_ver` 의 «새 주장»으로 기록될 수 있음 |

### 4.4 숫자 읽기

`rows_read`(원천에서 읽은 행) · `molecules`(독립 판정 단위) · `molecules_refused` ·
`molecules_incomplete`(원천 일부가 아직 안 온 분자) · `atoms`(통과한 원자) ·
`rows_matching_nothing`.
행 수와 원자 수는 같을 필요가 없다 — 분자 수와 거절 수를 «함께» 본다.

### 4.5 정정

원장은 append-only 다. 해석 오류는 과거 행을 UPDATE 하지 않고 선언·mapper 를 고친 뒤
새 provenance 로 재백필한다. 기존 주장을 읽기에서 어떻게 밀어낼지는 해소 규칙이나
`supersedes` 계약으로 다룬다.

🆕 **[2026-08-31] 그 「재백필」에 «범위» 버전이 생겼다** — §4.1-ter. 전부 다시 돌리지 않고
**선언된 컬럼 하나로 좁혀** 그 범위의 원자만 회수하고 다시 만든다. 커서는 안 움직인다.

### 4.6 화면과 API 읽는 법

🔴 **화면이 비었다고 데이터 부재로 읽지 않는다.** 「없다」는 다섯 가지다:

```
안 골랐다  ·  그런 종류가 없다  ·  서버가 답할 수 없다  ·  걸었는데 비었다  ·  «잘렸다»
```

- `/structure` — 선언된 절반과 센서스 절반을 «병합»한다.
  `declared_only` 는 「선언됐지만 원자가 없다」, `undeclared` 는 「원장에 있는데 선언이
  설명 못 한다」(= 드리프트). `atoms: 0`(세었고 없다)과 `atoms: null`(아무도 안 셌다)은 다른 답이다.
- `/kinds` — `in_ledger` 는 선언 여부, `ledger_state`/`ledger_atoms` 는 관측 상태다.
- `/trends` — 선언된 finding kind 와 실제 검사 분모를 쓴다. **관측 부재를 0% 불량으로 표시하지 않는다.**
- `/subgraph` — `node_limit` 에 걸린 «잘림»을 «부재»로 읽지 않는다. 응답이 잘림을 표시한다.
  🔴 **[2026-08-29] 대조 블록도 같은 규율을 진다.** `propagation.ranked[]` 의 항목마다
  `reach`(닿은 씨앗 수)와 **`reachable`(그 «타입»에 닿을 수 있었던 씨앗 수 = 분모)** 이
  «쌍»으로 나온다. `reach 0 / reachable 0` 은 **「길이 없었다」= 미검사**이고,
  `reach 0 / reachable 2` 라야 「닿을 수 있었는데 아니었다」= **진짜 차이**다.
  둘을 같은 픽셀로 그리면 화면이 미검사를 발견으로 바꾼다. 계약은
  [LEDGER_EVIDENCE_SUBGRAPH_SPEC §4.2-bis](../spec/LEDGER_EVIDENCE_SUBGRAPH_SPEC.md).

### 4.7 합성·픽스처 데이터 걷어내기

삭제 대상은 파일 목록이 아니라 **provenance 술어**로 정한다: 원장은 해당
`source_translator_ver` prefix 또는 명시적 synthetic 표지, 커서는 같은 `source`,
원천 표는 생성기가 소유한 식별자. 실행 전 각 술어의 «건수»를 따로 세고 운영 데이터와
겹치지 않음을 확인한다.

🔴 **픽스처에게 «자기 표»를 주는 것이 소스에 필터를 가르치는 것보다 싸다.**
전사 픽스처를 남의 표에 쓰자 그 표를 읽는 소스가 «남의 행까지 읽어» 거절했다.
수리는 전사 로그에 자기 relation 을 준 것이었다.
🔴 **롤백은 목록이 아니라 «술어 하나»**로, 키를 쓴 것과 «같은 상수»에서 만든다.
지우는 것은 원시 DELETE 가 아니라 소스·오버라이트를 캐스케이드하고 이력을 쓰는 경로로 태운다 —
원시 삭제는 그것들을 고아로 남긴다.
씨더(`server/scripts/seed_syn_die_transfer.py`)는 채우기 순서를 다시 구현하지 않고
`map_alignment.serpentine_index` 를 부르며, 기하는 `valid_die_ref` 에서 온다.

## 5. 원장이 «일부러» 하지 않는 것

- 원천 데이터를 정규화해 고쳐 쓰지 않는다.
- 관측 부재를 «깨끗함»으로 바꾸지 않는다.
- 모든 발견 낱개를 기본 걷기에 펼치지 않는다.
- 해소 결과를 원장 행 위에 덮어쓰지 않는다.
- 샘플 dry-run 만으로 모든 분기가 안전하다고 주장하지 않는다.

## 관련 문서

- [ONTOLOGY_LEDGER_SETUP](./ONTOLOGY_LEDGER_SETUP.md) — 선언·배포 순서
- [LEDGER_TECHNICAL_SPEC](../spec/LEDGER_TECHNICAL_SPEC.md) — 저장·API 계약
- [PRIMER](./ledger/PRIMER.md) — 한 행이 원자가 되기까지, 실물로
- [backend §2](../architecture/backend.md) — 라우트 계약
- [LEDGER_RULINGS](../process/LEDGER_RULINGS.md) — 판정
