# 정준 원장 기술 명세 (Canonical Ledger — Technical Specification)

> **Status:** 🟠 부분 최신 | **Last-verified:** 2026-08-19 — 이 라운드에 대조한 것은 **Source-of-truth 목록·§3.8·§3.9·§3.11의 은퇴 서술뿐**이다(단일 파일 셋업·번역기 은퇴 반영). 나머지 절은 2026-08-17 Ledger v2 2단계 malformed-safe 전수 교차검증 `IN_REVIEW` / `NOT_APPROVED`; 현행 실행 경로 `FROZEN_FOR_REDESIGN` — 코드 대조 | **Owner:** Server / Ledger
> **Source-of-truth:** `server/ledger/schema.py`(DDL) · **`server/ledger/setup_bundle.py`**(🔴 **[2026-08-18] 단일 `ledger_config.json` 문법 — `setup_version: 3`, 필수 section **일곱**(`LOGICAL_SECTIONS`) + 선택 `virtual_joins`. **`tables`는 그 일곱에 없다** — 물리 스키마의 정본은 `server/config/table_config.json` 하나다. `manifest.json` 다섯 파일 모양은 은퇴했고, 이 셋업은 이제 **백필 실행 경로에 연결돼 있다**) · `server/ledger/setup.py`(로드 경계 `load_setup` — 구 `cutover_v2.py`/`load_cutover_setup`은 삭제) · `server/ledger/vocabulary.py`(어휘·서명·**걷기 선언**·**롤업 선언** — 🔴 **코드 절반**) · **`server/config/ledger_vocabulary.json`**(🔴 **선언 절반 · `.sample` 폴백 없음**) · `server/ledger/config.py`(수동 문법 검증) · **`server/ledger/source_profile.py`**(현행 동결 Profile 계약) · **`server/ledger/source_profile_builtins.py`**(현행 동결 등록 데이터) · **`server/ledger/source_contract.py`**(선언·번역기·live vocabulary 결합 검사) · **`server/ledger/roleframe.py`**(RoleFrame/Pack compile · 범용 mapper · `SentenceShape`/`ProfileSentences`) · ⚰️ **`translator_pattern.py`·`declared_translator.py`는 트리에 없다**(`e47d325`로 번역기 다섯과 함께 삭제 — §3.8·§3.9의 그 서술은 은퇴한 경로다) · `server/ledger/store.py`(쓰기) · `server/ledger_trace.py`(해결·보행·롤업 철자) · `server/ledger_structure.py`(유형 수준 읽기) · `server/ledger_kinds.py`(종류 목록)
>
> **이번 라운드 (2026-08-15 3차 · 넷째 문법 `declared` + 뿌리 키 롤업 — R-2026-08-15-N ② · R-2026-08-15-O · 갱신 트리거 ②③⑥⑦)**
> **코드 대조 기준 리비전은 `8c236bc`다.**
> **§3.8 신설**: 소스 문법이 **넷**이 됐고 넷째는 🔴 **파이썬 클래스가 «없다»** — 행→원자 사상이 `emit` 선언 그 자체다.
> 계약으로 옮겨 적을 것 넷: **`occurred_at_basis`가 필수이고 기본값이 없으며**(R-…-N ②) `row_created`면 **value payload에 실려 원자에서 읽힌다** ·
> **각 `emit` 규칙의 `rule` 이름이 그대로 파생 이름**이라 provenance가 `#slot_preserving`과 **똑같이 질의된다**(§3.5 ③) ·
> **`when`은 닫힌 집합에서 «정확히 하나»**(0개·2개·오타 전부 거절 — 무시된 연산자는 조건을 «항상 참»으로 만든다) ·
> **`"$col"`이 없는 컬럼을 부르면 «거절»**(빈 값으로 풀지 않는다).
> **§3.7-septies 신설**: `ENTITY_TYPES`가 서명 필드 **둘**(`rolls_up_to`·`root_key`)을 얻었고 🔴 **주어 스코프 읽기는 뿌리 키로 롤업한다** —
> 실측 42개 원자가 웨이퍼 스코프 조회에서 **안 보이던** 간극을 메운다(**응답 «형태»는 한 바이트도 안 바뀌었다**).
> 🔴 **§3.7-sexies ⑨가 «거짓이 됐다»** — 「등재한 낱말을 발화할 번역기가 없다」는 `declared`가 닫았다.
> ⚠️ **`derivation`(R-M ⑤)은 그것과 «다른 것»이고 여전히 미구현**이다 — 섞으면 3류 규율이 2류 주장에 붙는다.
>
> **직전 라운드 (2026-08-15 2차 · 어휘가 «층»으로 갈렸다 — R-2026-08-15-M · 갱신 트리거 ⑦·⑧)** —
> **§3.7-sexies 신설**: 정본이 둘(코드 `PREDICATES` + 선언 `ledger_vocabulary.json`)이고 **묻는 쪽은 전부 병합 뷰 `all_predicates()`를 읽는다**
> (`emittable()`이 모듈 레벨 `EMITTABLE` frozenset을 **대체**했다 — 상수는 import 시점에 얼어붙어 선언을 영원히 못 본다).
> 🔴 **`.sample` 폴백이 «없는 것»이 판정이고**(샘플이 로드되면 아무도 선언 안 한 낱말이 닫힌 어휘에 들어간다),
> 🔴 **`traversable`은 «키의 존재»까지 요구**하며(없으면 「생각 안 했다」와 `None`이 같은 선언이 된다),
> 🔴 **삭제가 없고 `status: retired`뿐**이다(은퇴는 발화를 막지 읽기를 막지 않는다 · DELETE 라우트 0개가 단언된다).
> **§4.7 ⑪ 가산**: `/structure`의 술어 행마다 `origin: code|config`. ⚠️ **정준 층과 개체 타입은 여전히 코드다** —
> 열린 것은 ontology 층 «술어»뿐이고, 넷째 문법 `derivation`은 번역기가 없어 **오늘 등재한 낱말을 발화할 것이 없다**(resolve가 그렇게 보고한다).
>
> **직전 라운드 (2026-08-15 · R&D selection 계측 비교)** — `processed_with` required가
> `step/recipe`로 축소되고 categorical occurrence만 비교한다. 닫힌 어휘에 `measured`
> (`since:4`)가 열렸으며 상태별 value/run 조건과 무값 상태의 value 금지를 gate가 집행한다.
> `/selection/resolve`는 원값·상태 수·분모·mark/evidence를 보존한다.
>
> **직전 라운드 (2026-08-14 3차 · 관측 번역 — R-2026-08-14-D + R-2026-08-14-E ⓐ · 갱신 트리거 ⑦·⑧)** —
> **§3.7 어휘가 «열하나»**(`observed` 하나만 추가 — `since: 3`, subject `Wafer`, `value` 목적어의 `required`에 🔴 **`run_uid`**.
> 🔴 **짝인 `measured`는 «일부러» 미등재**이고 그 부재가 어휘 성장 규율의 적용이다) ·
> **§3.7-quinquies 신설**(🔴 **걷기 의미론이 코드 목록에서 «선언»으로 올라갔다** — `traversable` 3상태(`True`/`False`/**`None`**)와 `direction`,
> 양방향 로드 시점 검사. **`LINEAGE_PREDICATES`는 이제 파생물**이고 **동작 불변이 단언돼 있다**. 🔴 **`degree_cap`은 R-E가 요구했으나 «미선언»** —
> 집행 지점이 재귀 CTE 안이라 지금 선언하면 R-2026-08-13-D의 미끼 필드가 된다) ·
> **§4.8 신설**(`GET /api/ledger/kinds`의 **원장 위치 필드 다섯** — 🔴 **불리언 하나로는 「선언 없음」과 「백필 미실행」이 구별되지 않았다**) ·
> **§5.5-bis 신설**(관측 번역 실측 — **102,177원자 · 거절 0 · 불완전 0**) · **§5.7 정정**(🔴 **「결함 관측은 원장에 아예 없다」가 «거짓»이 됐다**).
>
> **직전 라운드 (2026-08-14 2차 · 구조 뷰 — 읽기 라우트 하나 · 갱신 트리거 ⑦)** — **§3.7-quater 신설**(🔴 **`label_ko`가 «서명 필드»로
> `ENTITY_TYPES`·`PREDICATES` 전 항목에 붙었다** — 낱말은 하나도 안 늘고 안 줄었으며 서명 «의미»도 안 바뀌었다. **집행 지점은 단위 테스트 하나**이고,
> 읽는 쪽이 폴백하므로 그 테스트 말고는 아무것도 빨개지지 않는다) · **§4.7 신설**(`GET /api/ledger/structure` 응답 계약 —
> 🔴 **손으로 적은 노드·엣지 목록이 없다**(생성 + 병합) · 🔴 **상태 낱말 다섯을 «필드로» 낸다** · 🔴 **`atoms: 0` ≠ `atoms: null`** ·
> 🔴 **창은 건수만 좁히고 «선언»은 절대 안 좁힌다** · 층 둘(`ledger`·`mechanism`, M4는 그날 `absent` — **이후 착지, §4.7 ⑤의 정정이 현행**)) ·
> **§5.7 신설**(센서스 비용과 **크기 게이트** — 캐시가 아니다. ⚠️ **버려진 SQL 철자의 비교값과 수가 겹치니 인용 전에 라벨을 볼 것**).
>
> **직전 라운드 (2026-08-14 · 어휘 확장 · 제품 소유자 판정)** — **§3.7 신설**(닫힌 어휘 계약 — **일곱에서 아홉**: `processed_with`·`has_param`,
> 새 개체 타입 **`Recipe`**(🔴 `rev`가 **subject 키 재료**), 그리고 **`value` 목적어의 `required` 검사**가 서명에 **집행 지점**을 붙였다) ·
> **§4.1-bis 신설**(🔴 **「실측이 설정값을 이긴다」에 랭킹 코드가 «한 줄도» 없다** — 계급 경계가 공짜로 사준 것이고, 그 사실이 계약이다).
> 설계 근거는 [architecture/PHYSICS_ONTOLOGY_SETUP §2·§3](../architecture/PHYSICS_ONTOLOGY_SETUP.md).
>
> **직전 라운드 (2026-08-14 · `92547c3` · R-2026-08-13-H-bis)** — 🔴 **§3.3에 있던 「의도적으로 남긴 모양 셋」이 거짓이 됐다.**
> 셋 다 은퇴했고 **§3.3-ter 신설**이 그 자리를 대신한다. 뒤집을 때 틀리기 쉬운 두 곳:
> ① **`screen_molecule`이 「언제나 raise」가 아니다** — 거절만 예외이고 **정당한 무발화의 `[]`는 반환으로 남았다**(테스트로 못박힘) ·
> ③ **셋째는 오늘 «배선»되지 않았다** — 번역기 하나, `backfill.run`의 호출자는 자기 CLI `main()`뿐이라 **동작 변화 0**이고
> 가치는 미래 작성자가 맞을 `RuntimeError` 하나다. §1.5-bis에 **`reasons` 필수** 행 추가, §3.3-bis의 표 두 행 정정.
>
> **그 앞 라운드 (2026-08-13 5차)** — §1.5 커서가 **열둘 → 열셋**(`refusal_reasons`)이고 **§1.5-bis 신설** ·
> **§3.3-bis 신설**: 「원자 하나가 나쁘면 분자 전체」가 **어느 파편에서든**으로 승격됐다(`f313279` · R-H) ·
> **§3.5-bis 신설**: `subject_types` 복수 allow-list가 **문다**(`eb1ae8b` · R-D) ·
> **§6.4-bis 신설**: `/coverage` 응답 확장과 `refusals_unaccounted`의 **부호 계약**(`0198e7e` · R-F).

> **문서 셋의 분업**
> | 문서 | 소유 |
> |---|---|
> | [architecture/CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md) | **WHY** — 왜 이 모양인가 |
> | [guide/ONTOLOGY_LEDGER_SETUP](../guide/ONTOLOGY_LEDGER_SETUP.md) | **WHAT TO DECLARE** — 선언 표 전수 · 순서 · 실물/제안 구분(2026-08-15 신설) |
> | [guide/LEDGER_GUIDE](../guide/LEDGER_GUIDE.md) | **HOW(코드)** — 번역기 쓰는 절차 · 백필 숫자 읽는 법 |
> | **이 문서** | **EXACTLY-WHAT** — 변경이 **조용히 깨뜨리면 안 되는 계약** |
> | [process/LEDGER_RULINGS](../process/LEDGER_RULINGS.md) | **판정** 🔴 정본. 거기 없는 판정은 내려진 적이 없는 것 |
>
> 🔴 **라우트 계약의 서술 정본은 [architecture/backend §2](../architecture/backend.md)이고 이 문서는 그것을 «가리킨다».**
> 여기 §4는 **응답의 의미론**(무엇이 어떤 뜻인가)을 적지 라우트 표를 복제하지 않는다.
>
> ⚠️ **모든 수치는 합성·이 개발 박스 실측이고 운영의 증거가 아니다.** 항목마다 출처 라벨을 달았다.

---

## 1. 물리 스키마 계약

### 1.1 `ledger_events` — 열세 컬럼

봉투 7필드에 원천 사건 상관 필드 둘을 더해 평탄화한 것이다. 평탄화는 `envelope.ROW_COLUMNS` **한 자리**에서만 일어난다
(쓰기와 컬럼 목록이 같은 튜플을 쓰므로, 한쪽에만 컬럼을 더하면 **조용한 값 밀림이 아니라 구문 오류**가 된다).

| 컬럼 | 타입 | NULL | 봉투 필드 |
|---|---|---|---|
| `id` | `UUID` | NOT NULL | `id` (**uuid7 — 워터마크 + 기록시각 내장**) |
| `subject_type` | `TEXT` | NOT NULL | `subject.type` |
| `subject_keys` | `JSONB` | NOT NULL | `subject.keys` (**구조화. 이어붙인 문자열 금지**) |
| `predicate` | `TEXT` | NOT NULL | `predicate` |
| `object_kind` | `TEXT` | NULL 허용 | `object.kind` (`value`\|`entity_ref`\|`event_ref`, **∅ = NULL**) |
| `object_payload` | `JSONB` | NULL 허용 | `object.payload` (**타입 보존**) |
| `occurred_at` | `TIMESTAMPTZ` | NOT NULL | `occurred_at` (**세상의 시각**) |
| `source_who` | `TEXT` | **NOT NULL** | `source.who` |
| `source_translator_ver` | `TEXT` | **NOT NULL** | `source.translator_ver` |
| `source_raw_ref` | `TEXT` | **NOT NULL** | `source.raw_ref` |
| `supersedes` | `UUID` | NULL 허용 | `supersedes` |
| `source_event_id` | `UUID` | **NOT NULL** | 같은 원천 발화 묶음의 불투명 UUIDv5. 해결 우선순위가 아니라 증거 구조 |
| `source_event_state` | `TEXT` | **NOT NULL** | `source_molecule` \| `source_record` \| `legacy_atom` |

🔴 **provenance 셋은 NOT NULL이다.** 누가·어떤 번역기로·어느 원시 행에서 주장했는지 말 못 하는 원자는 증거가 아니다.
(테스트가 이 셋을 nullable로 손복사해 두고 **아무도 안 가진 테이블을 시험하고 있던** 적이 있다.)

**봉투에 있는데 컬럼이 «없는» 것 둘:**

| 없는 것 | 어디 있나 |
|---|---|
| `recorded_at` | **uuid7 `id` 안의 48비트 밀리초.** 컬럼을 되살리면 한 질문에 답이 둘이 된다. 읽는 법은 `uuid7.timestamp_ms()` |
| `molecule_ref`(원시 상관 표지) | **메모리에만.** 게이트가 전부-아니면-전무를 정하고 writer가 `source + ref + occurred_at`의 불투명 `source_event_id`를 만든 뒤 원문은 버린다. 해결기가 읽는 의미 필드가 아니며 컬럼으로 새지 않는다 |
| `derivation` | 컬럼이 아니라 **`source_translator_ver`의 `#` 접미**. §3.5 |

### 1.2 CHECK 제약 — 각각이 «산문으로만 살 뻔한 규칙»이다

| 제약 | 강제하는 규칙 |
|---|---|
| `ck_ledger_object_kind` | `object_kind IS NULL OR object_kind IN ('value','entity_ref','event_ref')` — 슬라이스 1에 pin된 enum |
| `ck_ledger_register_has_no_object` | **`(predicate = 'register') = (object_kind IS NULL)`** — 🔴 **쌍조건(biconditional)이고 «양방향»이다.** 설계는 `register`의 object를 ∅라 하고 pin된 enum에는 ∅ 철자가 없다. 네 번째 값을 발명하지 않고 `object_kind IS NULL`을 **`register`에만** 합법으로 만든 것 — object를 든 register와 object 없는 비-register가 **똑같이** 거절된다 |
| `ck_ledger_objectless_has_no_payload` | `object_kind IS NOT NULL OR object_payload IS NULL` |
| `ck_ledger_subject_keys_is_object` | `jsonb_typeof(subject_keys) = 'object'` — 이어붙인 키가 빈 조각에서 무너져 **운영 17만 행**이 된 사고를 **저장 계층에서**(모든 파이썬 검사 아래에서) 막는다 |
| `ck_ledger_no_self_supersede` | `supersedes IS NULL OR supersedes <> id` — 자기를 대체하는 정정은 해결기가 영원히 따라가는 순환 |
| `ck_ledger_source_event_state` | 새 적재의 사건 경계 철자를 세 값으로 닫는다. 과거 선택 호환은 `legacy_atom`이며 유사 시각으로 추정 병합하지 않는다 |

### 1.3 🔴 `PRIMARY KEY (id, occurred_at)` — 복합인 것이 «선택이 아니다»

**PostgreSQL은 파티션 키가 파티션 테이블의 모든 유니크 제약에 포함될 것을 요구한다.**
`ledger_events`는 `occurred_at`으로 파티션되므로 **`PRIMARY KEY (id)`는 아예 거절된다**
(격리 `assy_qa`, PostgreSQL 18.3에서 실증 — `01452d5`).

그래서 **`id`가 반복되는 행이 «다른» `occurred_at`으로 들어오는 것을 DB가 받아 준다.**
🔴 **그 결과 「`id`가 유일하니 마지막 정렬 층이 언제나 결판낸다」는 논증을 쓸 수 없다.**
전순서가 성립하는 진짜 근거는 §4.3에 있다.

### 1.4 파티션

| 항목 | 값 |
|---|---|
| 방식 | `PARTITION BY RANGE (occurred_at)` — **빈 테이블일 때 첫 문장부터.** `ALTER TABLE ... PARTITION BY`는 없으므로 채워진 테이블에 나중에 붙이는 것은 **전면 재작성**이다 |
| 낟알 | **월 단위**(총괄 판정 `f896020`). 근거: 원자당 673 B에서 연 단위는 한 해가 통째로 한 릴레이션이라 pruning·detach를 무력화한다 |
| 이름 | `ledger_events_YYYY_MM` |
| 경계 | **UTC로 계산하고 «명시 오프셋»을 달아 쓴다.** 오프셋 없는 경계는 **세션의 `TimeZone`**으로 해석되므로, `TZ`가 다른 두 프로세스가 어긋난 파티션을 만들고 **그 틈에 떨어진 행은 INSERT 자체가 실패한다** |
| 생성 시점 | 마이그레이션이 아니라 **번역기가 자기가 쓸 달을 쓰기 직전에**(`schema.ensure_partition`). 존재할 달은 배포일이 아니라 데이터가 정한다. `add_ledger_events.py --months N`으로 미리 열 수 있다 |
| 트랜잭션 | 🔴 **자기 트랜잭션에서 돌고 먼저 커밋한다.** 원자 트랜잭션 안에서 돌다 실패하면 분자까지 롤백되고 운영자는 **DDL 문제를 원자성 거절로 읽는다** |
| 잠금 | `SET LOCAL lock_timeout = '20s'`. §6.3 |

### 1.5 `ledger_translator_cursor` — **열셋** (2026-08-13 `0198e7e`로 열둘 → 열셋)

| 컬럼 | 타입 | 의미론 |
|---|---|---|
| `source` | `TEXT PRIMARY KEY` | 소스 하나당 한 행 |
| `translator_ver` | `TEXT NOT NULL` | **덮어쓴다**(마지막 런의 버전) |
| `cursor_value` | `JSONB NOT NULL` | **덮어쓴다.** `{"event_time": "..."}` — 온전히 처리한 마지막 그룹 |
| `molecules_done` | `BIGINT` | **누적(`+=`)**. 🔴 **본** 분자 전부이고 거절된 것을 **포함**한다 |
| `atoms_written` | `BIGINT` | 누적. 실제 INSERT된 수 |
| `atoms_deduped` | `BIGINT` | 누적. `attempted − inserted` |
| `molecules_refused` | `BIGINT` | 누적. `molecules_done`의 **부분집합** |
| `incomplete_molecules` | `BIGINT` | 누적. **거절이 아니다** — 착지했지만 소스 이벤트의 행이 다 안 온 분자 |
| **`refusal_reasons`** | **`JSONB` NULL 허용** | **`molecules_refused`의 내역.** `{사유: {"count": N, "last_at": "<UTC ISO-8601>"}}`, 사유 하나당 한 항목. **누적**이고 §1.5-bis가 그 계약 전부다 |
| `source_head` / `head_probed_at` | `JSONB` / `TIMESTAMPTZ` | 티어 2 lag 프로브가 **자기 작은 트랜잭션**으로 쓴다 |
| `started_at` / `updated_at` | `TIMESTAMPTZ` | `now()` |

🔴 **카운터는 SET이 아니라 누적이다.** 백필 하나가 커서 한 행에 **여러 배치**를 쓰므로 누적만이 맞을 수 있다.
(SET 의미론은 이 시스템에서 이미 결함이었다 — 한 트랜잭션에 대해 메시지 둘이 와서 뒤엣것이 앞엣것을 덮어
override 카운트가 과소보고된 QA D-1.)

⚠️ **누적은 「이 커서 행이 사는 동안」이지 「이번 런」이 아니다.** `_advance_cursor`는 처음부터
`테이블.컬럼 + EXCLUDED.컬럼`을 써 왔다 — **런 스코프 수를 여기서 읽을 방법은 없고**, 최근성은
`last_at`(내역)과 `updated_at`이 나른다. 화면은 「누적」이라고 말해야 하고 「지난 런의」라고 말하면 안 된다.

### 1.5-bis 🔴 `refusal_reasons` — **내역이지 «두 번째 의견»이 아니다** (2026-08-13 `0198e7e` · R-2026-08-13-F)

거절 사유는 그전까지 **`gate._refusals`(백필 프로세스의 메모리)에만** 있었다.
웹서버는 `server/ledger`를 일부러 import하지 않고 게이트가 쓰는 박동 노트는 서빙되지 않으므로,
**이 DB를 어떻게 읽어도 사유 하나를 낼 수 없었다.** 이 컬럼이 그 읽기다.

| 계약 | 내용 |
|---|---|
| **같은 트랜잭션** | `store._advance_cursor`가 **집계와 내역을 한 문장에** 쓴다. 바깥에 쓰면 둘이 어긋나고, 그 불일치는 **문제를 보여 주려고 만든 화면에서 오경보로 읽힌다** — 자기 장부에 대해 늑대를 외치는 상태 표시줄은 없느니만 못하다 |
| **불변식** | 현재 쓰기가 처음부터 끝까지 소유한 행에서 `sum(count) == molecules_refused`. `test_ledger_l1_pg.py`가 **쓰기 시점에** 못박는다 |
| **누적** | 집계가 누적이므로 내역도 누적이다. **런 스코프 내역을 수명 집계 옆에 두는 것 자체가** 이 판정이 금지하는 불일치다 |
| **`last_at`은 최근성** | 조용해진 사유는 **옛 타임스탬프를 유지**하고, 깨끗한 런은 기존 항목을 **다시 찍지 않는다**(바이트 동일로 남는다) |
| 🔴 **NULL ≠ `{}`** | **NULL** = 「이 행은 컬럼보다 오래됐다」 — 그 집계는 **영원히** 분해될 수 없다(이름은 이미 끝난 프로세스의 메모리에 있었다). **`{}`** = 「현재 쓰기가 이 행을 소유했고 거절이 0건이다」. 둘을 같게 렌더하면 배포 이력이 결함으로 읽힌다 |
| 🔴 **`reasons`는 «인자»이지 기본값이 아니다** | (2026-08-14 `92547c3` · R-H-bis 2) `store.write_batch`와 `store._advance_cursor` **둘 다** `reasons`가 **키워드 전용 필수**이고, **명시적 `None`도 `TypeError`**다. 기본값이 있으면 **아무 말도 안 한 호출부**가 집계만 올리고 이름을 안 남겨, 위 부호 계약에서 **`> 0`(배포 이력, 결함 아님)과 구별되지 않는 「오늘의」 결함**을 만든다. 깨끗한 런의 정당한 값은 **명시적 `{}`** 하나뿐이다. 세부는 §3.3-ter |

**저장은 UTC 문자열**(`store.LedgerStore._NOW_ISO`)이고 **표시 존 변환은 읽는 쪽에서 한 번**만 일어난다
(`ledger_trace._rendered_reasons`) — `occurred_at`과 정확히 같은 규율이다.

🔴 **부호가 클라이언트 계약이다** — `/coverage`의 `refusals_unaccounted`. §6.4-bis.

**배포는 «양방향»으로 방어된다 — 순서를 바라지 않는다.** 이 프로젝트는 `add_frame_confirmation.py`가 적어 둔
「기존 테이블에 붙인 컬럼은 마이그레이션보다 먼저 읽는 프로세스에서 500이다」의 값을 이미 치렀다.

| 방향 | 방어 |
|---|---|
| **쓰기** | `schema.CURSOR_ADDITIONS`를 `ensure_schema`가 적용하고, 그것이 **모든 백필의 첫 단계**다 — 번역기는 **자기가 못 쓰는 표를 만날 수 없다** |
| **읽기** | `ledger_trace.coverage`가 카탈로그에 **어느 컬럼이 있는지 먼저 묻고** 있는 것만 SELECT한다 — 마이그레이션보다 앞선 웹서버가 **답한다** |
| **운영자 진입점** | `server/migrations/add_ledger_refusal_reasons.py`(`--report` / `--reverse`). **DDL의 유일한 철자는 여전히 `ledger/schema.py`**이고 이 스크립트에만 있는 문장은 **역방향뿐**이다(`schema.py`는 계약상 추가 전용이라 DROP이 거기 있을 일이 없다) |

`ALTER TABLE … ADD COLUMN <nullable, DEFAULT 없음>`은 PG 11+에서 **카탈로그만** 바꾼다 — 힙 페이지를 안 건드리고
표 크기와 무관하며 ACCESS EXCLUSIVE는 카탈로그 갱신 동안만이다. 게이트는 `pg_attribute`이므로 **재실행은 DDL도 잠금도 0**이다.

---

## 2. 인덱스 집합 — **모두 가격표가 붙어 있다**

> **실측 라벨**: 이 박스 · PostgreSQL 18.3 · 이 번역기가 실제로 내는 모양의 원자 **300,000개** · `VACUUM ANALYZE` 후.
> 힙은 **312.8 B/원자**(설계가 독립적으로 잰 312.3 B와 0.5% 이내). **총 673 B/원자**(월 단위 파티션 판정의 근거 수치,
> 1,000만 원자 ≈ 6.7 GB).

### 2.1 살아 있는 셋 — 🔴 **admission rule: 이름 붙은 소비자가 있어야 한다**

| 인덱스 | 정의 | 소비자 | 가격 |
|---|---|---|---|
| `uq_ledger_atom` | **UNIQUE** `(occurred_at, predicate, subject_type, subject_keys, coalesce(object_payload,'{}'::jsonb), source_translator_ver, source_raw_ref)` | **멱등성 그물 ②** — `store.insert_atoms`의 `ON CONFLICT DO NOTHING`. 커서가 **첫** 답이고(재실행은 0행을 읽는다) 이것은 **커서를 리셋해도 남는** 답이다 | **284.6 B/원자** — 청구서에서 가장 큰 한 줄(`source_raw_ref` + jsonb 둘을 싣는다). 스키마로 강제되는 멱등성의 값이고, **다시 발견하지 말고 다시 «판정»하라고** 적어 둔 것 |
| `idx_ledger_subject_lot` | `((subject_keys->>'lot'), predicate)` | `ledger_trace`의 재귀 혈통 보행(`subject_keys->>'lot' = :lot AND predicate = ANY(...)`) | ⚠️ **소스에 기록되지 않았다.** 총 673에서 나머지 셋을 빼면 ≈59 B/원자인데 이는 **산술이지 측정이 아니다** — 인용 전 실측할 것 |
| `idx_ledger_register` | `(subject_type, subject_keys) WHERE predicate='register'` | `store.existing_registrations` — 페이지당 1질의. 개체마다 조회하면 천만 행 백필이 **2차식**이 된다 | **16.6 B/원자, 그리고 감소 중**(부분 인덱스라 register는 O(개체), 테이블은 O(원자)) |
| `idx_ledger_register_search` | `GIN ((subject_keys::text) gin_trgm_ops) WHERE predicate='register'` | `GET /api/ledger/entities?q=`의 모든 등록 타입 contains 검색. 인덱스가 없으면 소비자가 전량 JSON 스캔을 **거절**한다 | 개발 DB 자식 인덱스 합계 **656 kB**(2026-08-15 실측). register 개체 수에 비례하며 전체 원자 수로 환산하지 않는다 |
| `idx_ledger_subject_entity` | `(subject_type, subject_keys)` | `GET /api/ledger/explore_entity`의 구조화된 exact subject identity frontier join | 개발 DB 자식 인덱스 합계 **13 MB**(2026-08-15 실측). 모든 원자를 싣는 대가이며 generic entity 탐색의 JSON 전량 스캔을 막는다 |
| `idx_ledger_source_event` | `(source_event_id, occurred_at, id) WHERE source_event_id IS NOT NULL` | `/api/ledger/subgraph`의 Event→Claim exact batch | 가격 재측정 대기. 기존 파티션에는 child별 CONCURRENTLY 후 parent ATTACH |
| `idx_ledger_object_entity` | `((object_payload->>'type'), (object_payload->'keys')) WHERE object_kind='entity_ref'` | `/api/ledger/subgraph`의 Entity←object Claim exact reverse lookup | 가격 재측정 대기. JSON text 전량 스캔으로 강등 금지 |

🔴 **`idx_ledger_subject_lot`의 모양은 취향이 아니라 질의의 성질이 강제한다.** 혈통 보행은
**`occurred_at` 술어를 갖지 않는다**(「이 랏에 대한 전부」에는 시간 경계가 없다) — 그래서
**가지치기가 원리적으로 발화할 수 없고 홉마다 전 파티션을 방문한다.** §5.2가 그 청구서다.
**부모에 선언**하므로 아직 존재하지 않는 파티션까지 PostgreSQL이 상속시킨다.

🔴 **유니크 인덱스가 «해시»가 아니라 «컬럼»인 이유.** 해시 키는 파이썬(쓰기 시점)과 PostgreSQL(인덱스 표현식)이
**똑같이** 계산해야 하는데 둘은 JSON을 다르게 철자한다(`json.dumps(separators=(",",":"))` 대 jsonb의 `::text`).
어긋나면 **조용히** 실패한다 — 모든 행이 새 행으로 보인다. 컬럼 자체에 걸면 두 번째 철자가 없다:
PostgreSQL이 jsonb를 jsonb와 **의미적으로** 비교하고 쓰는 쪽은 아무것도 계산하지 않는다.
`Atom.identity()`는 그 규칙의 **파이썬 쪽 거울**이지 열쇠가 아니다.

🔴 **`coalesce(object_payload, '{}'::jsonb)`인 이유.** PostgreSQL 15 이전 모든 버전에서 유니크 인덱스의 NULL은
서로 **DISTINCT**하다 — 그대로 두면 동일한 `register` 원자 둘이 **둘 다 통과한다.**
빈 객체는 안전한 대역이다(어떤 술어의 서명도 `{}`를 payload로 받지 않으므로 진짜 값과 충돌할 수 없다).

### 2.2 지어졌다가 **제거된** 셋 — 되돌리는 것은 **숫자가 붙은 결정**이다

> 1,000만 원자에서 각각 **≈0.3–0.6 GB**를, 아무것도 답하지 않으려고 **영원히** 낸다.

| 제거된 인덱스 | 가격 | 왜 제거됐나 · 언제 되돌리나 |
|---|---|---|
| `idx_ledger_type_pred_time (subject_type, predicate, occurred_at)` | **64.4 B/원자** | 소비자 0. 보행은 타입이 아니라 **subject 키**로 거른다 |
| `idx_ledger_subject_gin USING gin (subject_keys jsonb_path_ops)` | **38.3 B/원자** | `subject_keys @> '{...}'`을 서빙한다. 🔴 **오늘 그렇게 묻는 소비자가 없다** — 보행은 `subject_keys->>'lot' = ...`을 묻고 **GIN은 그 질문에 답할 수 없다.** `jsonb_path_ops`는 포함(containment)만 지원하는 대신 기본 `jsonb_ops`보다 작다. **`lot` «아닌» 키로 subject를 찾아야 하는 소비자가 생기면** 그때 되돌린다(주 3의 역-반경 질의가 유력한 첫 후보) |
| `idx_ledger_id (id)` | **31.6 B/원자** | **중복이다.** PK가 `(id, occurred_at)`이고 `id`가 **선두**라 워터마크 스캔 `WHERE id > :cursor ORDER BY id`은 이미 파티션마다 인덱스를 갖고 `MergeAppend`로 합친다 |

---

## 3. 쓰기 경로 의미론

### 3.1 🔴 한 트랜잭션 계약

**원자 INSERT + 커서 UPDATE = 커밋 하나** (`store.write_batch`). 커밋 전에 커서를 쓰면 크래시 때 일감을 건너뛰고,
커밋 후에 쓰면 다시 한다. 한 트랜잭션에 넣어야 **「쓰인 원자 == 커서 위치」가 원자적 사실**이 된다.
(파일 인제션의 `record_chunk_progress`가 이미 같은 논증을 했고 그대로 전이된다.)

**커넥션은 반드시 `engine.raw_connection()`.** `database.database`가 Engine 클래스에 `db_safety` 가드를 설치하므로
**테스트 프로세스가 운영 DB에 닿는 것이 불가능**해진다 — 생 `psycopg2.connect`는 그 가드를 그냥 지나간다.

### 3.2 `ON CONFLICT` 비대칭 — 이것이 하중을 받는다

| 대상 | 절 | 왜 |
|---|---|---|
| `ledger_events` | **`ON CONFLICT DO NOTHING`** | 원장은 **append-only**다. 충돌은 「이미 있는 주장」이라는 뜻이고 **덮어쓸 것이 없다.** `DO UPDATE`가 여기 있으면 그 순간 원장에 **가변 필드**가 생기고 §7-①이 무너진다 |
| `ledger_translator_cursor` | **`ON CONFLICT (source) DO UPDATE`**, 카운터는 `테이블.컬럼 + EXCLUDED.컬럼` | 커서는 **진도이지 주장이 아니다.** 그리고 SET이 아니라 **누적**인 것이 §1.5의 이유 |

`insert_atoms`는 **`(attempted, inserted)` 둘을 따로** 돌려주고 **절대 합치지 않는다.**
`attempted > inserted`는 「커서가 이미 끝난 일감을 통과시켰고 인덱스가 알아봤다」는 뜻이고 운영자가 볼 수 있어야 한다.
전송은 `execute_values`(`page_size=1000`) — N번 왕복이 아니라 다중 행 `INSERT` 하나.

### 3.3 분자 원자성

- **트랜잭션 단위 = 온전한 소스 이벤트 N개.** 한 개의 «일부»는 절대 아니다.
- 자르는 것은 `backfill.py`이고, 자르는 자리는 **소스가 주는 경계**(`event_time` 그룹)다:
  페이지가 꽉 찼으면 **꼬리 그룹을 버린다**(안에서는 잘렸는지 알 수 없다) → 버려서 아무것도 안 남으면
  (그룹 하나가 페이지보다 크면) **그 그룹만 통째로** 다시 읽어 단독 처리한다.
- 게이트는 **원자 하나가 나쁘면 분자 전체**를 거절한다. 쓰는 쪽은 **분자만** 받고 원자를 개별로 받지 않으므로
  **파편을 쓸 수 있는 호출 경로가 존재하지 않는다.**

#### 3.3-bis 🔴 상설 규칙 — **어느 «파편»에서든 거절이 발화하면 그 분자는 원자 0개다** (2026-08-13 `f313279` · R-2026-08-13-H)

위 셋째 줄은 **`screen_molecule`에 대해서만** 참이었고, 그것이 결함이었다.
번역기가 자기 원자를 «만드는 도중» 거절하는 자리는 게이트의 심사 **앞**에 있어서 그 보장 밖이었다 —
`_slot_map`이 `None`을 돌려 「거절했다」를 신호했고 한 호출부가 `... or []`로 병합해 **신호가 사라졌다.**
실측: 게이트는 `atomicity_violation`을 세고 로그는 「1행이 아무것도 못 냈다」고 말하는데 **원자 셋이 착지했다**
(그리고 커서는 `molecules_refused=0` 옆에 합이 1인 내역을 들어 `refusals_unaccounted = -1`이 됐다).

**규칙의 승격**: *어느 파편에서든 `gate.refuse`가 발화하면 그 분자는 원자를 0개 기여한다.*
**파편 단위 생존은 `incomplete`의 몫**이고(참이지만 불완전한 발화) 둘을 합치면
「거절됐는데 절반이 저장된 원장」이 된다.

| 기전 | 왜 이 모양인가 |
|---|---|
| `gate.MoleculeRefused` — **예외** | 🔴 **`[]`를 돌려주면 «그 측정만» 초록이 되고 모양은 그대로 남는다.** 값은 다음 사람의 편의 표현식이 다시 삼킨다. **어떤 병합 표현식도 예외를 삼킬 수 없다** — `or []`·`or {}`·맨 `extend`·무시된 반환 전부 |
| `gate.building_molecule(source)` — **스코프** | 규칙이 **읽는 자리**가 아니라 **발화하는 자리**로 옮겨갔다. 그 안에서는 **사유를 가리지 않고 모든** `refuse`가 세고 나서 raise한다 — 내년에 추가되는 헬퍼는 **이 규칙이 있는 줄 몰라도** 자기 분자를 세운다.<br>🔴 **여는 것은 «공유 드라이버»이지 번역기가 아니다**(2026-08-14 `92547c3` · R-H-bis 3, §3.3-ter): `backfill.run`의 분자 루프가 `with`를 들고 **`translator.translate`와 `gate.screen_molecule`을 «같은» 스코프 안에** 감싼다. `_build`의 `molecule_is_open()` 단언은 그래서 **첫 그물이 아니라 둘째 그물**이다 |
| 세고 «나서» raise | 거절은 **누가 예외를 잡든 말든 사실**이다. 순서를 뒤집으면 못 잡힌 예외가 카운터를 지운다 |
| `molecule_is_open()` 단언 | 스코프 **밖**에서는 모든 `refuse`가 **세기만 하고** 실행이 「멈췄어야 할 검사」를 지나 계속 간다 — **같은 삼킴이 한 층 위에서** 재현된다. 그래서 원자를 만드는 본문은 전제를 **가정하지 않고 검사**한다 |
| **일방향 문은 «층마다» 하나** | ⚠️ **2026-08-14 `92547c3` 이후 예외를 다시 값으로 바꾸는 자리는 «둘»이고, 층이 다르다.** ① `lot_event_translator.translate`의 `except` — **번역기가 원자를 만드는 도중** 낸 거절을 `(None, report)`로. ② `backfill.run` 분자 루프의 `except` — **게이트 심사(`screen_molecule`)**가 낸 거절을 `refused = True`로(그리고 그 팔이 `_forget_registers`를 부른다). ①이 아래를 다 잡으므로 ②에 도달하는 것은 심사 거절뿐이다. 🔴 **불변식은 「자리가 하나」가 아니라 «각 문 아래에 삼킬 표현식이 없다»**는 것이다 — `_build` 안에는 여전히 없고, 드라이버 쪽 문은 `pending.extend`보다 **바깥**에 있어 풀림이 원자를 남기지 못한다 |

🔴 **거절된 분자는 자기 «부작용»도 되돌려야 한다.** `register` 원자는 실행 스코프 메모(`registered`)에
**거절 가능한 검사들보다 먼저** 들어간다. 삼킴이 살아 있던 동안은 register가 어차피 쓰였으므로 메모가 참이었다 —
**아무것도 안 쓰이게 되는 순간** 그 랏은 「아무것도 안 쓴 분자」에 의해 등록된 것으로 표시되고
**이후 어떤 분자도 그것을 등록하지 않는다.** 수리는 **분자별 목록**이지 `registered`의 스냅숏이 아니다
(수명 메모를 분자마다 복사하면 천만 행 백필이 **2차식**이 된다).

⚠️ **여기 있던 「의도적으로 남긴 모양 셋」은 2026-08-14 `92547c3`로 «셋 다» 은퇴했다 — §3.3-ter.**
(그 블록은 ① `screen_molecule`의 `[]` 거절 ② `write_batch(reasons=None)` ③ 스코프를 열어야만 물려받는 두 번째 번역기를
「다음 사람이 만날 자리」로 적고 있었다. 지금은 **셋 다 거짓**이고, 뒤집는 방식이 둘에서 다르다.)

**반쪽 착지 없음의 증명 방법** — 명세로 남길 것은 결과가 아니라 **방법**이다:
페이지 안에서 **첫 청크가 이미 INSERT된 뒤** 두 번째 문장이 raise하도록 만들고, **원자 0개가 살아남는지**를 본다.
🔴 그리고 **경계를 걷어냈을 때 원자가 남는지도** 본다 — 그것이 그 테스트가 **빨개질 수 있음**의 증명이다.

⚠️ **그리고 「예외가 던져진다」는 주장은 «공유 주입 하네스 안에서» 할 수 없다** (2026-08-14 `92547c3`).
이 저장소의 주입 하네스 둘은 `AssertionError`를 **성공으로 친다** — **틀린 예외가 던져져도 초록**이다.
그 자리의 증명은 **옛 모양을 실제로 주입해 빨강을 실측**하는 것이고(R-H-bis는 셋 다 그렇게 했다),
단언은 `pytest.raises(<정확한 타입>)` 블록 **밖에서** `caught.value`에 대고 한다 —
블록 «안»에서 호출 뒤에 쓴 단언은 **한 번도 실행되지 않는다.**

#### 3.3-ter 🔴 그 셋의 은퇴 — **그리고 셋째는 오늘 아무것도 «배선»하지 않는다** (2026-08-14 `92547c3` · R-2026-08-13-H-bis)

판정 정본은 [R-H-bis](../process/LEDGER_RULINGS.md)이고 **구현이 판정문을 두 곳에서 더 정확하게 만들었다**(둘 다 채택).
🔴 **옛 문장을 그대로 뒤집으면 새 거짓이 되는 자리가 둘이라, 표의 셋째 열이 이 절의 본론이다.**

| 옛 문장 (거짓이 됨) | 지금 | 🔴 «그대로 뒤집으면» 틀리는 지점 |
|---|---|---|
| ① `screen_molecule`은 거절 시 `[]`를 돌려준다 | **거절 팔만** `gate.refuse` 경유 — 스코프 안이면 `MoleculeRefused`로 풀린다. 스코프 밖에서는 `refuse`가 **세기만** 하므로 `([], report)`로 강등된다(둘째 그물이지 두 번째 계약이 아니다) | 🔴 **「이제 언제나 raise한다」가 아니다.** **정당하게 할 말이 없던 분자**(원자 0개 — 빈 wafer 컬럼의 `track_in`)는 **여전히 `[]`를 «반환»**하고, 그 갈래는 이제 테스트가 못박는다. **거절과 무발화는 다른 문장**이고 둘 다 raise시켰으면 거절 카운터가 **두 가지 뜻**을 갖는다 — §3.5의 카운터가 기대는 바로 그 구분이다 |
| ② `write_batch(reasons=None)` | **기본값 없음 + 키워드 전용**, 명시적 `None`도 `TypeError`. 실제로 `molecules_refused`를 쓰는 `_advance_cursor`도 같다 | 🔴 **기본값 제거«만»으로는 안 됐다.** 본문이 `_json(dict(reasons or {}))`였으므로 `reasons=None` 한 번이 미끼를 **키 하나로** 되살린다. 🔴 그리고 **정수 인자 둘(`refused`·`incomplete`) 뒤에 있어** 위치 인자로는 한 칸 어긋난 값을 받을 수 있었다 — 그래서 키워드 전용이다. `_advance_cursor`까지 간 것은 **판정 letter를 넘은 확장이고 승인**됐다(§1.5-bis) |
| ③ 두 번째 번역기는 **스코프를 열어야만** 물려받는다 | **`backfill.run`의 분자 루프가 연다.** 번역기는 열지 않고 **요구**한다 — 안 열고 부르면 `RuntimeError`이고 그 메시지가 **누가 여는지와 두 줄짜리 철자**를 댄다 | 🔴 **중복 제거가 아니라 «책임의 이동»이다.** 실측 `with gate.building_molecule(` 개수: **전 1**(`lot_event_translator.translate`) / **후 1**(`backfill.run`). **수는 안 줄었다.** 그래서 「옛 사본이 사라졌나」는 **틀린 검사**이고, 맞는 검사는 **「번역기가 아직도 여는가」**(안 연다 — 되돌리면 `DID NOT RAISE RuntimeError`로 빨개진다) |

🔴 **③은 오늘 «동작»을 하나도 안 바꾼다 — 착지했지만 배선되지 않았다.**
번역기 클래스는 **하나**(`LotEventTranslator`)이고, `backfill.run`을 부르는 것은 **자기 파일의 CLI `main()`뿐**이다
(실측 grep — 데몬·라우트·워커·스케줄러 **0**. 나머지 호출자는 테스트 7곳). 오늘의 값어치는 전부
**미래의 두 번째 번역기 작성자가 맞을 `RuntimeError` 하나**이고, 그것이 판정의 의도 그대로이지 미달이 아니다.
⚠️ **그러나 이 문장 없이 「착지」라고만 적으면 다음 사람이 «없는 경로»를 찾아 나선다** — 이 저장소가 이미 치른 값이다.

**①이 «단위 테스트만»으로는 정착되지 않았다는 것이 이 라운드의 측정이다.** 옛 반환형을 주입해 재면
단위는 `DID NOT RAISE MoleculeRefused`로 빨개지지만, 진짜 위험은 드라이버에 있다:
같은 주입을 실 PostgreSQL에 걸면 **게이트는 2를 세는데 드라이버는 0을 센다**(`assert 0 == 2` on `refused_molecules`) —
**세지 않고 잃는** 그 경로가 `refusals_unaccounted`를 **음수**로 미는 것이고(§1.5-bis·§6.4-bis),
단위 테스트는 드라이버가 스코프를 아예 안 열어도 초록이다.

### 3.4 멱등성 — 독립된 그물 **둘**, 각각 증명

| 그물 | 무엇을 덮나 | 어떻게 보이나 |
|---|---|---|
| ① **커서** | 정상 재실행 | 0행 읽음 → 0원자 |
| ② **`uq_ledger_atom`** | **커서를 못 믿는 모든 경우** — 리셋, `--from` 겹침, 크래시 후 그룹 재읽기 | 행은 읽히고 원자는 만들어지는데 `inserted=0 deduped=N` |

🔴 **①만으로 통과하면서 ②가 깨져 있을 수 있고 그 반대도 그렇다.**
이 프로젝트는 **문 둘 중 하나만 닫고 성공을 보고한 수리**(`_get_or_create_row`, 2026-08-11)의 값을 이미 치렀다.
그래서 `test_ledger_l1_pg.py`는 **둘을 따로** 태운다.

### 3.5 게이트 — 거절 분류 체계

**단위는 행이 아니라 분자.** 사유는 **닫힌 집합**(`gate.REFUSAL_REASONS`, **열둘**)이고 호출부가 새 사유를 지어내면 `ValueError`.
번호가 아니라 **이름**인 이유는 그 문자열이 운영자 로그와 `/health`에 그대로 나가기 때문이고,
**이제 커서 행의 `refusal_reasons`에도 그 이름 그대로** 저장된다(§1.5-bis) — 문자열을 개명하면 **저장된 내역과 갈라진다.**

| 사유 상수 | 설계의 원자성 검사 |
|---|---|
| `undeclared_source` · `undeclared_vocabulary` | — (문 앞) |
| `no_occurred_at_declaration` · `missing_occurred_at` | — (§3.6) |
| `no_identity` · `not_true_alone` | ① **홀로 참인가** |
| `atomicity_violation` | ② **반쪽 없이 착지하는가** |
| `undeclared_derivation` | ③ **결론이 아니라 발화를 적었는가** |
| `no_raw_ref` | ④ **`raw_ref`로 재발화 가능한가** |
| `payload_not_preservable` | (봉투) |
| `ambiguous_pair` | 한 행이 짝의 **양쪽**을 채웠다 — 신원이 없는 게 아니라 **둘**이고 행이 어느 쪽인지 말하지 않는다 |
| **`undeclared_subject_type`** | **설계의 넷이 아닌 «다섯째 질문»** — R-2026-08-13-D. §3.5-bis |

#### 3.5-bis `undeclared_subject_type` — **선언이 물어야 한다** (2026-08-13 `eb1ae8b` · R-2026-08-13-D)

**다섯째 질문: 이 원자는 «이 소스가 말하겠다고 한 것»에 대한 것인가?**
소스 선언의 `subject_types`가 그 **외연**이고, 밖에 있는 원자는 다른 검사를 다 통과해도 이 이름으로 거절되고 세어진다.

- **단수 `subject_type`은 은퇴했다** — 번역기 안에서 한 번 대입되고 **아무 데서도 읽히지 않았다**(호출부가 리터럴을 넘긴다).
  `validate()`가 **어느 원자에도 도달하지 않는 값**을 검사하고 있었다. 🔴 **옛 키는 무시되지 않고 «에러»이며
  메시지가 새 이름을 댄다** — 조용히 아무 뜻도 없는 config가 이 판정이 끝내려는 결함 그 자체이므로,
  옛 키를 받아들여 다른 일을 하는 것만은 하면 안 된다.
- 🔴 **단수가 애초에 틀린 모양이었다.** `lot_event` **한 소스**가 개체 타입 **둘**(랏에 대한 주장·웨이퍼에 대한 주장)에
  대한 원자를 만든다 — 실측 `Lot` 689 · `Wafer` 220. 코드는 각 원자의 **사실**을 소유하고 선언은 그 사실의 **허용 범위**를 소유한다.
- **`screen_molecule`의 넷째 인자는 «필수»이고 기본값이 없다.** 기본값이 있으면 호출부가 **아무 말도 안 함으로써** 옛 동작을
  유지할 수 있고, 그것은 미끼 필드가 한 층 위에서 되살아나는 것이다. **빈 집합은 전부 거절**하며 그것이 옳은 방향이다.
- **검사는 `check_subject_keys` «앞»에 온다** — 뒤에 두면 같은 사건이 `no_identity`로 보고되고,
  「이 랏에는 신원이 없다」와 「이 번역기가 설비 이야기를 시작했다」는 **완전히 다른 보고**다.
- ⚠️ **실데이터에 이 거절은 0건이다**(43행 전수 재번역, 878 → 878 주장 동일). 이 사유는 **드리프트 탐지기**이지 오늘의 문제가 아니다.

🔴 **이 판정이 승격시킨 상설 규칙: 선언 필드는 «집행 지점»을 갖거나, 존재하지 않는다.**

**카운터 이름과 그 뜻** (프로세스 수명 내내, `(소스, 사유)`별):

| 카운터 | 뜻 |
|---|---|
| `refusals()` | `{(source, reason): 분자 수}` |
| `rows_refused()` | `{source: 소스 행 수}` — 그래서 아무것도 못 낸 행 |
| `atoms_lost()` | `{source: 원자 수}` — 만들어졌다가 분자와 함께 버려진 것 |
| `incomplete_molecules()` | `{source: 분자 수}` — **거절 아님** |

🔴 **`atoms_lost`는 「얼마나 잃었나」가 아니다.** 원자가 되기 «전»에 거절된 분자는 여기에 **0을 기여하고도**
그 행이 냈을 전부를 잃는다. 첫 실전에서 「1행 거절 · 26원자 미기입 · `atoms_lost=0`」이 실제로 나왔다.
**두 수를 같이 실어야만 계기가 거짓말하지 않는다.**

**③의 기계적 형태**: 원자는 **소스 config가 «선언한»** 파생 이름만 달 수 있다(`config.declared_derivations`가
선언에서 «조립»한다). 그래서 **아무도 선언하지 않은 규칙은 원자를 만들 수 없다.** 빈 집합을 넘기면
전부 거절되는데 그것이 **옳은 방향**이다. 파생은 컬럼이 아니라
**`source_translator_ver`의 `#<derivation>` 접미**로 나른다(열두 번째 컬럼은 판정이지 구현 세부가 아니다) —
그리고 그 결과 `WHERE source_translator_ver LIKE '%#slot_preserving'`이 **질의 가능**해진다.

🔴 **[2026-08-15 3차] `declared` 문법에서는 그 「선언」이 «규칙 이름 그 자체»다**(§3.8). `emit` 규칙 하나의 `rule` 값이
그대로 파생 이름이 되고 **그 밖의 이름은 하나도 합법이 아니다**(`register_entity_types`가 있으면 `first_sight`가 더해진다).
그래서 **config에서 규칙을 지우면 그 파생은 «즉시» 발화 불가**가 되고, 드리프트한 선언은 원자가 아니라 **이름 붙은 거절**을 낸다 —
그리고 `WHERE source_translator_ver LIKE '%#<rule>'`이 손으로 쓴 번역기의 파생과 **똑같이** 질의된다.
🔴 **그러므로 한 소스 안에서 `rule` 이름 중복은 금지다** — 두 규칙이 같은 이름을 쓰면 provenance가 둘을 구별하지 못한다.

**로그 시끄러움**: 1·10·100·1,000·… 번째 발생에만 `WARNING`. 고쳐진 배포와 망가진 배포가 같은 로그를 내면 안 된다.
**샘플 상세는 상한(`MAX_REFUSAL_SAMPLES=20`)이 있고 카운트에는 상한이 없다** — 상세 문자열은 전부 소스 데이터에서 오므로
망가진 피드가 보고서를 무한히 키울 수 있어서는 안 된다.

### 3.6 `occurred_at` 파싱 규칙 — 넷, 그리고 순서

1. 🔴 **도착 시각 대체 금지.** 안 읽히는 시각은 **`None`을 돌려주고 그것은 거절 신호**다. 절대 `now()`가 아니다.
   (그 대체는 스스로를 알리지 않는다 — 모든 원자가 well-formed하고 **역사의 순서만** 틀린다.)
2. **선언된 시간대는 «naive» 텍스트에만 먹인다.** 자기 오프셋을 달고 온 문자열은 **이미 어느 instant인지 말했다.**
   대안 둘 다 스팟 체크를 통과하기 때문에 규칙을 여기 한 번 못박는다:
   `replace(tzinfo=...)`는 벽시계를 유지하고 오프셋을 버려 **조용한 9시간 이동**을 만들고,
   `astimezone(...)`은 instant에 대해 no-op이라 **선언이 참조됐는지 자체를 가린다.**
3. **구분자 넓힘은 «선언된 형식에서 파생»된다.** 선언 형식에서 시(hour) 지시자 직전 구분자 하나를 **한 번** 바꾼 사본,
   그리고 각각에 `%z`를 단 사본 — **총 4후보**. 이것은 문법을 넓히는 것이 아니라 **전송 형태**를 넓히는 것이다:
   🔴 **이 목록 아래에서 두 가지로 읽히는 문자열이 하나도 없으므로 어떤 문자열에도 두 instant가 주어질 수 없다.**
   (`%z`는 `strptime`에서 선택적이지 않으므로 「단 형식」과 「안 단 형식」은 **서로소**다 — 그래서 이것은
   선호 순서가 아니라 **조회**다.) 선언된 철자가 첫 후보라 **핫 경로는 정확히 `strptime` 한 번**을 낸다.
4. **선언 자체가 없으면 소스 전체를 거절한다**(로드 시점). 못 쓰는 시간대 이름도 **폴백이 아니라 예외**다 —
   조용한 UTC 폴백은 방금 고친 결함을 그대로 재현한다. ⚠️ **`Asia/Seoul`은 런타임에 IANA tzdata를 찾는다**
   (`UTC`는 안 찾았다) → `tzdata`가 **배포 의존성**이다.

### 3.7 닫힌 어휘 계약 — **일곱 → 아홉 → 열하나 → 열둘** (2026-08-14 3차 · 제품 소유자 판정 + R-2026-08-14-D · 2026-08-15에 `measured`)

🔴 **[2026-08-15 · R-2026-08-15-M] 정본이 «둘»이 됐다** — `server/ledger/vocabulary.py`의 `PREDICATES`는 이제 **코드가 싣는 절반**이고,
운영자가 선언한 ontology 층 술어는 `server/config/ledger_vocabulary.json`에 산다. **아래 표는 코드 절반이다**(§3.7-sexies가 나머지 절반과 병합 규칙을 소유한다).
이 절은 **조용히 깨지면 안 되는 부분**만 적는다.
🔴 **표의 열에 `traversable`이 있는 것 자체가 이번 라운드의 변경**이다 — 걷기 의미론이 **선언의 일부**가 됐다(§3.7-quinquies).

| 낱말 | 층 | subject | object | `since` | status | `traversable` |
|---|---|---|---|---|---|---|
| `register` | canonical | Lot · Wafer · Product · Equipment · **Recipe** | **∅**(`object_kind IS NULL`) | 1 | active | `False` |
| `pin` | canonical | 위 + Die | `event_ref` | 1 | active | `None` |
| `same_as` | canonical | 위 + Die | `entity_ref` | 1 | **reserved** | `None` |
| `derived_from` | ontology | Lot | `entity_ref`→Lot | 1 | active | 🔴 **`True`** (`subject_to_object`) |
| `slot_map` | ontology | Lot | `entity_ref`→Lot (`from`·`to`·`wafer` 필수) | 1 | active | `False` |
| `has_wafer` | ontology | Lot | `entity_ref`→Wafer (`slot`) | 1 | active | `False` |
| `frame_confirmed` | ontology | Wafer | `value`(**`required` 없음**) | 1 | **reserved** | `None` |
| **`processed_with`** | ontology | Wafer · WaferLeg | `value` · `required` = `step`·`recipe` | **2** | active | `None` |
| **`has_param`** | ontology | Recipe | `value` · `required` = `param`·`value`·`unit` | **2** | active | `None` |
| **`transferred`** | ontology | Wafer | `value` · `required` = `from`·`to` (`die` XOR `qty`는 **발화자 소유**) | **2** | active | `None` |
| **`observed`** | ontology | Wafer · WaferLeg | `value` · `required` = `finding_kind`·`method`·**`run_uid`** | **3** | active | 🔴 **`None`** |
| **`measured`** | ontology | Wafer · WaferLeg | `value` · 공통 `metric`·`unit`·`method`·`state`; `recorded`만 `value`·`run_uid` | **4** | active | 🔴 **`None`** |

🔴 **수가 통제 장치라는 성질은 «완화되지 않았다».** `test_ledger_l1_unit.py::test_v0_vocabulary_is_exactly_seven_words`는
**이름을 그대로 둔 채** 지금 **열둘**을 못박고, **원래 일곱이 여전히 `since: 1`인 것까지** 단언한다.
`measured`는 실제 계측 원자가 selection 비교에 필요해진 2026-08-15에 `since: 4`로 열렸다.
이름을 안 바꾼 것이 의도다: 일곱을 지키던 테스트가 **왜 열둘인지를 적는 자리**여야지,
조용히 완화된 옛 테스트 옆에 새 테스트가 서면 안 된다.
그 docstring이 판정 본문을 들고 있고, 이번 라운드분은 [R-2026-08-14-D](../process/LEDGER_RULINGS.md)를 이름으로 적는다.

- ⚠️ **`transferred`(`530fda6`)는 이 표에 «행이 없었다»** — 2026-08-14 3차 정비에서 등재했다.
  낱말이 코드에 들어왔는데 계약 문서에 안 실린 것은 갱신 트리거 ⑦이 물어야 했던 자리이고,
  🔴 **어휘는 DDL을 안 건드리므로 스키마 감시로는 영원히 안 잡힌다**(그 트리거가 존재하는 이유).
- 🔴 **`observed`의 subject가 `Wafer` «하나»인 것은 판정이다** — `Die`는 **구성형**(웨이퍼 × 격자)이라 등록이 없고,
  발견을 웨이퍼 아래 접어야 「이 웨이퍼의 보이드」가 질의 하나가 된다. 칩 좌표(`die`·`inchip`)는 payload로 간다.
- 🔴 **`run_uid`가 `required`인 것이 «분모 규율의 집행 지점»이다.** 「보이드 3개」는 「몇 개를 봤는데 3개」 없이는 아무 뜻이 없고,
  산문으로만 적혀 있었으면 다음 소스가 그것 없이 쓸 수 있었다. 런을 못 푸는 발견은 **거절**이고 도착 시각으로 도장 찍히지 않는다.
  ⚠️ **비정량 인간 관측**([MI 통일안 §6-ter](../architecture/MI_LEDGER_SCHEMA_PROPOSAL.md))은 자기 정의상 런이 없다 — 그날 이 필드가
  **「분모 없는 관측」을 판정으로 만들도록 강제**한다(조용히 빠진 키가 아니라).
- 🔴 **`class`는 payload이지 컬럼이 아니다**([§6-quater](../architecture/MI_LEDGER_SCHEMA_PROPOSAL.md)) — 도구의 «주장»이고 사람이 뒤집는다.
  값 집합은 종류별 **닫힌 집합**(`finding_kinds`의 `classes`)이고 밖의 값은 이름을 대며 거절된다.
  **합불은 여전히 저장 금지**다(임계는 레시피 파라미터). ⚠️ **`Finding` 개체 타입은 «연기»됐다** —
  관측 둘이 같은 불량 하나를 가리켜야 할 때(재검사 매칭) 필요해지고 그 소비자가 아직 없다([R-2026-08-14-G 3](../process/LEDGER_RULINGS.md)).
- ⚠️ **짝인 `measured`는 «등재하지 않았다»** — [§6-bis](../architecture/MI_LEDGER_SCHEMA_PROPOSAL.md)가 둘을 짝으로 그렸지만
  오늘 그것을 발화하는 것이 없다. 🔴 **짝이 예뻐서 미리 만든 낱말은 미끼 선언**이고, `since: 3`이 「하나만 왔다」를 나른다.

- **`processed_with`는 «예약된» 낱말이 열린 것이다** — 설계 §4.2가 처음부터 예약해 뒀고
  [PHYSICS_ONTOLOGY_SETUP §2](../architecture/PHYSICS_ONTOLOGY_SETUP.md)가 필요를 실증했다(물류와 관측은 있는데 **원인이 살 곳이 없었다**).
- 🔴 **목적어가 `entity_ver`가 아니라 `value`인 것이 판정이다.** 한 공정 런은 **step·설비·레시피 개정·실제 조건을 «동시에»** 지목하므로,
  `entity_ref` 셋으로 쪼개면 **어느 것도 홀로 참이 아니다**(원자성 검사 ①) — 「웨이퍼 W가 B-3에서 처리됐다」는 홀로는 어느 레시피인지 말하지 않고,
  짝은 `occurred_at` 충돌에서 복원해야 한다. **런 하나 = 주장 하나 = 원자 하나.**

#### 3.7-bis 🔴 `value` 목적어의 `required` — **서명이 처음으로 «값»을 문다**

그전까지 `object_kind = "value"`인 원자는 **구조적으로 무검사**였다. 술어가 산문으로 모양을 선언해도 게이트는 아무거나 받았고,
그것이 R-2026-08-13-D가 끝낸 **미끼 선언**의 한 칸 옆이다. 지금은 `check_signature`가 선언된 `required` 필드의 존재를 검사한다.

- ⚠️ **존재(presence) 검사이지 진리값(truthiness) 검사가 «아니다».** `has_param`의 `value`는 정당하게 `0`이고 정당하게 `False`다 —
  진리값 검사는 **사람이 가장 신경 쓴 설정값 둘을 거절**한다. 🔴 **빈 «문자열»은 여전히 거절**한다(설계 §3의 연결 문자열 사고가 온 모양).
- **`required`를 선언하지 않은 술어는 무변경**이다(`frame_confirmed`) — 없는 것과 빈 목록이 같은 뜻인 유일한 자리이고,
  그래서 이 검사는 기존 원자를 하나도 소급 거절하지 않는다.
- **payload가 dict가 아니면 그 자리에서 끝난다**(필드별 보고 없이 한 줄) — 모양이 틀렸는데 필드를 세면 보고가 거짓말한다.

#### 3.7-ter 🔴 `Recipe` — **개정이 subject 키 «재료»다**

`ENTITY_TYPES["Recipe"] = {class: issued, keys: ["recipe", "rev"]}`. 발급형이므로 `register`가 필요하고, `register`·`pin`·`same_as`의 subject 목록에 들어갔다.

🔴 **`rev`가 속성이 아니라 신원인 이유는 append-only 그 자체다.** `rev`가 속성이면 rev5를 적는 유일한 방법이 rev4의 원자를 supersede하는 것이고,
그 순간 **rev4로 실제로 돌았던 모든 웨이퍼의 근거가 도달 불가능**해진다. 키에 넣으면 두 개정은 **두 subject**이고 둘 다 영구히 주장 가능하며,
「rev4와 rev5 사이에 무엇이 바뀌었나」가 **이력 재구성이 아니라 두 subject의 `has_param` 집합 차**가 된다.

⚠️ **`has_param`은 파라미터당 원자 하나**이지 레시피당 파라미터 사전 하나가 아니다 — 개정 diff가 **집합 차**가 되고,
레시피 시트가 잘못 옮겨 적힌 것이 밝혀졌을 때 **파라미터 하나만** supersede할 수 있다.

#### 3.7-quater 🔴 `label_ko` — **서명 필드이고 장식이 아니다** (2026-08-14 2차)

`ENTITY_TYPES`와 `PREDICATES`의 **모든** 항목에 `label_ko`가 붙었다. 🔴 **낱말은 하나도 안 늘고 안 줄었으며, 서명의 의미론도 안 바뀌었다** —
`subject`·`object`·`required`·`qualifiers`는 한 글자도 안 움직였고 **DDL도 게이트도 무관**하다. 그래도 이 절에 적는 이유는
갱신 트리거 ⑦(**어휘 변경 — 서명 추가**)이 정확히 이것이고, **어휘는 컬럼이 아니라서 스키마 감시로는 영원히 안 잡히기** 때문이다.

- **왜 선언에 사는가**: 구조 뷰(§4.7)가 어휘를 그림으로 그리고 라벨을 **여기서** 읽는다. 렌더러 옆에 라벨 지도를 두면
  그 지도가 **어휘의 두 번째 목록**이 되고, 두 목록은 적히는 날엔 일치하므로 **드리프트가 보이지 않는다.**
- 🔴 **집행 지점은 `server/tests/test_ledger_l1_unit.py::test_every_declared_word_carries_a_label` 하나뿐이다.**
  「선언 필드는 집행 지점을 갖거나 존재하지 않는다」(R-2026-08-13-D)의 이번 적용이다.
- ⚠️ **읽는 쪽은 raise하지 않고 원시 이름으로 폴백한다**(`ledger_structure._label`). **그것이 판정이다** — 라벨 없는 낱말은
  화면을 **영어로 강등**시켜야지 비워서는 안 된다. 대가로 **그 테스트 말고는 아무것도 빨개지지 않는다.**

#### 3.7-quinquies 🔴 걷기 의미론 — **코드의 목록이 아니라 «술어의 속성»** (2026-08-14 3차 · R-2026-08-14-E ⓐ)

그전까지 「무엇을 걸을 수 있는가」는 `ledger_trace`의 **리터럴 목록**(`LINEAGE_PREDICATES` 넷)이었다.
지금은 **모든** 술어가 두 필드를 선언하고, 그 목록은 선언에서 **파생**된다.

| `traversable` | 걷기가 하는 일 | 오늘 이 값을 가진 낱말 |
|---|---|---|
| `True` | **인출하고 «통과»한다**(재귀) | `derived_from` |
| `False` | **인출하되 통과 금지** — 주석형. 도달은 하고 거기서 멈춘다 | `register` · `slot_map` · `has_wafer` |
| **`None`** | 🔴 **걷기가 «아예 인출하지 않는다»** | 나머지 일곱(`observed` 포함) |

- 🔴 **`None`은 「미설정」이 아니라 세 번째 «답»이다.** `observed`가 그것을 일부러 든다 —
  [R-2026-08-14-D 부칙 ①](../process/LEDGER_RULINGS.md): 걷기는 **도달한 랏의 주장을 전부** 끌어오는데
  웨이퍼 하나가 관측 수만 건을 이고 있어서, 이 낱말을 인출 집합에 넣으면 **번역기가 처음 성공하는 날 추적 화면이 죽는다.**
  관측은 **범위 지정 요청**(kind·기간)으로만 읽는다(`/siblings`·콘솔의 자기 질의).
- **`direction`**은 닫힌 집합 `{subject_to_object, object_to_subject}`이고 **`traversable: True`일 때만** 허용된다.
  🔴 **검사는 «양방향»이다**: 통과형인데 방향이 없으면 거절, **통과형이 아닌데 방향이 있어도 거절** —
  아무도 안 걷는 엣지의 방향 선언은 실행되지 않는 계약이다(R-2026-08-13-D의 미끼 필드).
- **파생 함수 셋**: `walk_predicates()`(인출 집합 = `traversable is not None`) · `traversable_predicates()`(재귀 집합 = `True`) ·
  `walk_direction(predicate)`. 🔴 **`ledger_trace.LINEAGE_PREDICATES`는 이제 이 파생물이고**,
  재귀가 따르는 낱말은 `traversal_predicate()`가 대어 **두 CTE 모두 SQL 파라미터로 바인드**한다(`'derived_from'` 리터럴이 사라졌다).
  어휘는 **호출 안에서 지연 import**하므로 §4.7 ⑩의 부팅 경로 보증은 그대로다.
- 🔴 **이관의 합격 조건은 «동작 불변»이었고 그것이 단언돼 있다**
  (`test_ledger_observed_unit.py::test_the_walk_vocabulary_is_derived_and_still_says_what_it_said`) —
  선언에서 뽑은 집합이 옛 리터럴과 **한 낱말도 다르지 않아야** 한다. 다르면 그것은 이관이 아니라 **말 없는 동작 변경**이다.
- 🔴 **`degree_cap`(R-E의 셋째 필드)은 «선언되지 않았다» — 추인된 판정이다**([R-2026-08-14-G 2](../process/LEDGER_RULINGS.md)).
  집행 지점이 **재귀 CTE 안**이라, 선언만 하고 읽는 곳이 없으면 「검사되지만 아무 데도 도달하지 않는 필드」가 된다.
  **선언은 물거나, 없어야 한다.** 차수 상한이 서는 라운드에 **자기 측정과 함께** 들어온다.
- **효과**(R-E의 근거): 장비·레시피를 나중에 개체로 세워도 **주석형 선언이 방화벽을 유지**한다.
  새 술어가 걷기에 편입되는 것은 **코드 수정이 아니라 선언 변경 + 어휘 고정 테스트 갱신**이 된다.

#### 3.7-sexies 🔴 어휘가 **층으로 갈렸다** — 정본 둘·병합 뷰 하나 (2026-08-15 · R-2026-08-15-M · 갱신 트리거 ⑦)

**낱말도 서명 의미론도 안 바뀌었다. 바뀐 것은 «어디서 늘리는가»다.**
운영자 절차(무엇을 어느 화면에서 어떻게)는 [ONTOLOGY_LEDGER_SETUP §4](../guide/ONTOLOGY_LEDGER_SETUP.md)가 소유하고, 여기는 **계약**만 적는다.

| 층 | 늘리는 곳 | 왜 |
|---|---|---|
| **정준**(`register`·`pin`·`same_as`) | 🔴 **코드 + 판정만.** 화면에 문이 «없고» 그 부재가 테스트로 고정된다 | 기록의 «문법»이 조용히 자라면 원장이 원장이 아니게 된다 |
| **온톨로지** | ✅ `server/config/ledger_vocabulary.json` (`POST /admin/ledger/save`) | 설계가 처음부터 「append-only로 성장」이라 적어 둔 층이다 |
| **개체 타입**(`ENTITY_TYPES`) | 🔴 **여전히 코드 + 판정만**(2026-08-15 3차에 서명 필드 **둘**이 붙었다 — `rolls_up_to`·`root_key`, §3.7-septies) | 주어의 **신원 키 정의**라 서명 완결 검사로 안전해지지 않는다 |

**① 🔴 「합쳐진 뷰」가 하나이고, 묻는 쪽은 «전부» 그것을 읽는다.**
`vocabulary.all_predicates()`가 코드 절반(`PREDICATES`)과 선언 절반을 병합하고 **항목마다 `origin: "code" | "config"`를 찍는다.**
그 뷰를 읽는 것: `is_declared` · `signature` · `check_signature` · `walk_predicates` · `traversable_predicates` · `walk_direction` ·
`check_walk_declaration` · **`emittable()`**(모듈 레벨 `EMITTABLE` frozenset을 **대체**했다 — 상수는 import 시점에 얼어붙어 선언을 영원히 못 본다).
🔴 **한 곳이라도 `PREDICATES`를 계속 읽으면 그 자리에서만 새 낱말이 «미선언»이 된다** — 게이트가 거절하는데 화면은 보여 주는 식으로 **갈라진다.**
🔴 **`PREDICATES`를 직접 읽어도 되는 곳은 「코드가 싣는 집합」을 «묻는» 자리뿐이다**(v0 고정 테스트가 그것이고, 그래서 그 테스트는 **한 글자도 안 바뀌었다**).

**② 🔴 `.sample` 폴백이 «없다» — 이 저장소의 다른 거의 모든 선언과 반대이고, 그것이 판정이다.**
샘플이 로드되면 **아무도 선언한 적 없는 낱말이 닫힌 어휘에 들어간다.** 저장소의 `.json.sample`은 **모양 설명용이고 로더가 읽지 않는다.**
라이브가 없으면 어휘는 **코드 집합 그대로**다(에러가 아니다).

**③ 🔴 깨진 확장 파일은 «통째로» 무시되고 절대 raise하지 않는다 — 그러나 조용하지도 않다.**
절반만 실린 어휘는 **프로세스마다 다른 낱말을 인정**하므로 부분 로드가 최악의 결말이다. 강등은 `vocabulary.extension_status()`가 들고,
`GET /admin/config/resolve?domain=ledger`(`config_resolve_report.DOMAIN_LEDGER`)가 **사유와 함께** 보고한다.

**④ 🔴 서명 «완결»이 저장 조건이다 — `vocabulary.SIGNATURE_FIELDS` 여덟.**
`label_ko` · `subject` · `object` · `traversable` · `direction` · `since` · `layer` · `status`. 거절 코드는 **닫힌 집합**(`vocabulary.DECL_REFUSALS`)이고
라우트가 그 집합을 화면에 실어 보낸다(클라가 사유 문자열을 지어내지 않는다).

- 🔴 **`traversable`은 «값»이 아니라 «키의 존재»를 요구한다.** 없으면 거절, **명시적 `null`은 수용.**
  그러지 않으면 「걷기를 생각 안 했다」와 「걷기가 절대 인출하지 않는다(`None`)」가 **같은 선언**이 된다(§3.7-quinquies의 삼상태가 그 자리에서 무너진다).
- 🔴 **`traversable: true`는 오늘 «이름 대어» 거절된다**(`traversable_true_unavailable`) — 다른 통과형 낱말이 이미 있을 때.
  `ledger_trace.traversal_predicate()`는 **정확히 하나**를 실행하므로, 둘째를 저장하면 **읽는 날이 아니라 저장하는 날** 죽어야 한다.
  🔴 **거절 시점이 판정이다** — 저장을 받아 두면 추적 화면이 «다음 요청»에 죽고, 그때 원인은 저장한 사람에게서 멀어져 있다.

**⑤ 🔴 삭제 경로가 «없다» — `status: "retired"` + `superseded_by`뿐이고, 그 부재가 단언된다.**
원자가 이미 그 낱말로 누워 있다. **은퇴는 «발화»를 막지 «읽기»를 막지 않는다** — 은퇴한 낱말은 `emittable()`에서 빠지고
`all_predicates()`·`signature()`에는 남는다. `/admin/ledger` 아래 **DELETE 라우트가 0개**임을 테스트가 단언한다.

**⑥ 🔴 미리보기는 공유 캐시를 «건드리지 않는다».** `vocabulary.check_signature_against(sig, …)`는 `check_signature`에 **선언을 손으로 건네는** 형태이고,
`check_predicate_declaration(name, decl, against=)`도 같다. 아직 저장 안 된 서명을 채점하려고 프로세스 캐시에 심으면
**미리보기가 다른 요청의 답을 바꾼다**(그 오염은 저장 실패 뒤에도 남는다).

**⑦ 캐시 교체는 «둘»이고 재기동이 0회다.** `vocabulary.reset_cache()`가 `main.reload_local_process_cache()`와
`chain_ingestion_worker.reload_worker_process_cache()`에 배선됐고, **같은 훅이 `ledger_trace.reset_walk_cache()`도 부른다** —
걷기의 인출 집합이 어휘의 **파생물**이라, 하나만 비우면 **낡은 걷기 집합이 새 낱말 위에서 돈다.**

**⑧ ⚠️ DDL은 여전히 0줄이라 스키마 감시로는 영원히 안 잡힌다.** 집행 지점은 `server/tests/test_ledger_admin_setup.py`이고,
v0 고정 테스트(`test_ledger_l1_unit.py`)는 **코드 집합에 대해** 그대로 산다 — 「선언으로 늘었다」는 `origin`으로 보이지 그 수를 흐리지 않는다.

**⑨ ✅ [2026-08-15 3차 — 닫혔다] 「등재한 낱말을 발화할 번역기가 없다」는 더 이상 참이 아니다.**
직전 판의 이 자리는 「선언으로 술어는 등재되는데 그걸 낼 번역기가 없다」였고, **넷째 문법 `declared`(§3.8)가 그 구멍이다** —
어떤 술어든 `emit` 규칙 하나로 발화되고, `config_resolve_report`의 「발화하는 번역기 없음」은
**그 술어를 내는 `declared` 소스가 선언되는 순간 자동으로 해소된다**(`_ledger_emitted_predicates`가 `emit`의 `predicate`를 읽는다).
⚠️ 🔴 **그것은 `derivation`이 «아니다».** `derivation`(R-2026-08-15-M ⑤)은 여전히 `SOURCE_KINDS`에 없고
`GET /admin/ledger/sources`의 `unsupported_kinds`에 **사유와 함께** 남는다 — 그쪽은 **원장을 «걸어서»** 조건을 평가해
근거 원자 id를 다는 **3류 추론**이고, `declared`는 **눈앞의 소스 행**을 옮기는 2류 발화다.
🔴 **두 판정이 하루 차이로 같은 「넷째」 자리를 말했고 나중 것(브리핑 §6-2 = `declared`)이 정본이다.**
**둘을 섞어 쓰면 3류 규율(근거 원자 필수)이 2류 주장에 붙거나 그 반대가 된다** — 이 문서 어디서도 섞지 않는다.

#### 3.7-septies 🔴 **집계 단위는 «뿌리 키»를 선언한다** — 그리고 읽기가 그 선언으로 모인다 (2026-08-15 3차 · R-2026-08-15-O · 갱신 트리거 ⑦)

`ENTITY_TYPES` 항목이 **선택적 서명 필드 «쌍»**을 얻었다: **`rolls_up_to`**(어느 타입 아래로 접히는가)와 **`root_key`**(그 뿌리의 신원 키 중 무엇을 공유하는가).
오늘 다는 것은 **`WaferLeg` 하나**(`rolls_up_to: "Wafer"` · `root_key: "wafer"`)다.

**① 🔴 왜 필드가 필요했나 — 주어를 가르는 것이 «강제»였기 때문이다.**
한 웨이퍼가 두 압력으로 붙으면 「저압으로 붙었다」와 「고압으로 붙었다」가 **둘 다 참**인데, 주어가 하나면 그 둘은
같은 `(subject, predicate)`에 대한 **경쟁 주장**이 되어 해결기가 **하나를 죽인다.** 주어를 갈라야 둘 다 산다.
**그 대가로 읽기가 갈라졌고, 조용히 그랬다** — 실측(2026-08-15): `subject_type = 'WaferLeg'` 원자 **42개**
(`observed` 18 · `register` 12 · `processed_with` 12(전부 FINAL_BOND) · **뿌리 웨이퍼 6장**)가
**웨이퍼 스코프 조회에서 한 건도 안 보였고**, 화면은 「본딩 조건 차이 없음」으로 읽혔다.

**② 🔴 읽기 계약: 주어 스코프 조회는 `subject_type = %(stype)s`가 아니라 «뿌리 키로 모은다».**
철자는 **하나**여야 한다 — `ledger_trace.rollup_subject_types(root_type)`이 그것이고, 반환은 **뿌리 자신 + 그 뿌리로 접히는 타입 전부**다.
**걷기 집합과 같은 캐시**에 앉고 **`reset_walk_cache()`가 같이 비운다**(어휘의 파생물이므로 하나만 비우면 낡은 집합이 새 선언 위에서 돈다).
오늘 그 철자를 쓰는 읽기 자리는 **셋**이다: `ledger_journey._atoms` · `ledger_walk_contrast._atoms_per_subject` · `ledger_walk_contrast` 걷기의 `atoms` CTE.
🔴 **이것은 «간극을 메우는» 변경이고 응답 형태를 바꾸지 않는다** — 이름이 바뀐 필드도, 재구조화된 블록도 **0개**다.

**③ 🔴 관계는 «선언»이고 절대 «유추»가 아니다.** 「키가 상위집합이면 접는다」로 유추했으면 `Die`의 키(`wafer`,`x`,`y`)도
`Wafer`의 상위집합이라 **다이 원자 전부가 웨이퍼 조회로 접혔을 것이다**(구성상 1.6억 개). 철자의 우연과 집계 단위는 다른 것이다.

**④ 자기 정합은 `vocabulary.check_entity_type_declaration()`이 문다** — 둘 중 하나만 선언 · 없는 타입을 가리키는 `rolls_up_to` ·
**자기 자신으로의 롤업** · **«양쪽» 타입의 키가 아닌 `root_key`** · **뿌리가 또 다른 뿌리를 가리키는 2단 롤업**(미구현)은 전부 위반이다.
🔴 **그 위반들의 공통점이 이 검사가 있는 이유다** — 전부 **에러가 아니라 「추가 행 0개」**로 나타나고,
그 모습은 **이 선언이 고치려던 결함과 구별되지 않는다.**
🔴 **이 검사가 없으면 「선언은 있는데 아무 데도 안 닿는 필드」가 되고, 그것이 R-2026-08-13-D가 끝낸 미끼 필드의 재발이다.**

### 3.8 → **§8로 옮겼다** (2026-08-19 판정 ④)

> ⚰️ **`declared` — ⚰️ `declared` — **파이썬 클래스가 «없는» 문법**.** 이 문법에는 **실행 경로가 없다**. 그래서
> 「쓰기 경로 의미론」의 «구성원»일 수 없고, 3.1→3.11을 차례로 읽는 사람이 살아 있는 열한
> 문법의 동료로 만나서도 안 된다 — **배너는 산문이고 위치는 구조이며, 훑는 독자가 실제로
> 따르는 것은 구조다.**
>
> **본문은 지우지 않았다.** 그 문법으로 쓰인 원자가 원장에 그대로 있고 읽히기 때문이다 —
> 그중 하나를 디버깅하는 사람이 찾을 곳은 이 사양이다. 전문은 **§8 「은퇴한 문법」(이 파일 맨 끝)**.
>
> 🔴 **번호는 비워 두고 3.9~3.11을 당기지 않았다** — 다른 문서 넷이 이 절을 «번호로» 부르고
> 있고(`qa/FEATURE_CHECKLIST.md` A2 · `process/DOC_OWNERSHIP.md` · 이 파일의 머리말·§3.6·§3.7-quater),
> 번호를 당기면 그 인용이 전부 **엉뚱한 절을 가리킨다.** 순서의 빈칸이 낡은 상호참조보다 싸다.

### 3.9 Source Contract — 선언·번역기·어휘의 결합 계약 (2026-08-16)

`ledger_config.json`, 번역기 Python, `vocabulary.py`는 실행 책임이 서로 다르지만
운영자가 답해야 할 질문은 하나다: **「이 소스가 어떤 Claim을 만들 수 있고, 지금 합법인가」**.
`server/ledger/source_contract.py`는 셋을 한 읽기 모델로 컴파일한다.

- `translator`: 선택된 프로필, 분자 단위, 변환 방식, 구현 위치
- `emissions[]`: 표본에 나오지 않은 분기까지 포함한 술어·주어·목적어·payload·파생 전수
- `vocabulary`: 각 가능 발화가 대조된 **현재** 서명
- `configured_by`: 틀렸을 때 고칠 선언 위치
- `state`: 전부 맞으면 `ready`, 하나라도 다르면 `incompatible`

검사는 두 겹이다. 먼저 가능 발화가 해당 소스의 `subject_types`와 허용 파생 안에
있는지 보고, 다음으로 live vocabulary의 주어·목적어 종류·목적어 타입·qualifier·필수
payload와 맞는지 본다. 한 행도 읽지 않고 확정할 수 있는 모순은
`translator_vocabulary_mismatch`로 **드라이런 전** 거절한다.

🔴 **드라이런의 실제 `atoms_rendered`와 Source Contract는 대체 관계가 아니다.** 전자는
선택한 표본에서 진짜 번역기를 실행한 경험적 증거이고, 후자는 표본이 우연히 밟지 않은
갈래까지 포함한 정적 계약이다. 둘 중 하나만 있으면 각각 「죽은 코드」 또는 「표본 밖
오류」를 놓친다.

⚰️ **[2026-08-18/19] 이 절의 Template Method 경로는 은퇴했다.** `translator_pattern.py`도
`examples/grouped_translator_template.py`도 트리에 없고 `POSSIBLE_EMISSIONS`는 `server/`
어디에도 없다(`e47d325`). 복잡한 새 모양의 오늘 자리는 `server/mappers/ledger_v2_*.py`의
`BaseLedgerMapper` 하위 클래스 **파일 하나**이고, 낼 수 있는 문장은
`POSSIBLE_EMISSIONS` 리스트가 아니라 `SentenceShape` 클래스 속성으로 선언한다
([LEDGER_GUIDE §3 ③](../guide/LEDGER_GUIDE.md)).

⚠️ **`translator_vocabulary_mismatch`를 「드라이런 전 거절」로 읽지 말 것.** `source_contract.py`의
컴파일은 그대로 살아 있지만, 그 앞의 `POST /admin/ledger/dry-run`은 소스 미리보기에 대해
`DryRunUnavailable`을 먼저 던진다(`ab8657f` — 태우던 v1 번역기 넷이 은퇴). 그래서 오늘
그 거절에 **도달하는 호출 경로가 없다.** 쓰기 없는 v2 미리보기는
`ledger/setup.py`의 `preview_selected_cursor_batch`이고 **부르는 라우트가 아직 없다.**

### 3.10 `SourceOntologyProfile` 2단계 — Claim Mapping 계약 (2026-08-17)

> **status:** `COMPLETE` · **approval:** `APPROVED`

Profile은 `ledger_config.json`의 기존 `sources`와 나란한 `profiles.<name>`에 둘 수 있다.
`sources`는 현행 실행 계약이고 `profiles`는 실행되지 않는 상위 작성 계약이다.
`validate_profile_section()`은 Profile만 검사하며 `config.load()`의 실행 디스패치에는
연결되지 않는다.

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
      "from": {
        "kind": "constant",
        "value": "source_position",
        "binding_origin": "user_declared",
        "approval_status": "approved"
      },
      "to": {
        "kind": "declared_lookup",
        "lookup_id": "destination_inventory",
        "key": {
          "kind": "column",
          "column": "MOVE_ID",
          "binding_origin": "user_declared",
          "approval_status": "approved"
        },
        "select": "container",
        "binding_origin": "user_declared",
        "approval_status": "approved"
      },
      "occurred_at": {
        "kind": "column",
        "column": "EVENT_TIME",
        "binding_origin": "user_declared",
        "approval_status": "approved"
      }
    }
  }]
}
```

Registry 구조:

```text
PackRegistry
└─ PackDescriptor(pack_id, version)
   └─ ClaimDescriptor(claim_id)
      └─ RoleDescriptor(role_id, kind, required, allowed_binding_kinds,
                        allow_null, symbolic_constants, allowed_constant_types)
```

| 경로 | 계약 |
|---|---|
| `profile_version` | 정수 `1`만 수용. 다른 값은 `unsupported_profile_version` |
| `source` | 비어 있지 않은 원천 이름. 특정 업무 이름에 대한 분기 없음 |
| `packs[]` | `pack_id@version`; 미등록 Pack과 미지원 버전을 구분 |
| `mappings[].mapping_id` | 필수, 공백 금지, Profile 안에서 고유 |
| `mappings[].use` | `pack_id/claim_id`; `packs[]`가 버전을 고정 |
| `mappings[].bind` | Claim이 등록한 Role만 허용하고 required Role 전부 요구 |

Binding kind 등록부:

| kind | 필수 필드 | 검사 |
|---|---|---|
| `column` | `column` | 비어 있지 않은 컬럼명 |
| `constant` | `value` | 키의 명시적 존재; `null`은 Role의 `allow_null`, 나머지는 Role의 symbolic constant 또는 허용 JSON type 계약을 따름 |
| `declared_lookup` | `lookup_id`, `key`, `select` | 2단계에서는 식별자·column/constant key binding·출력 선택의 구조만 검사. 실행과 반환 형상 검사는 3단계 |

모든 정규화 Binding은 설정 출처 `binding_origin`(`user_declared`, `system_suggested`,
`imported`)과 Mapping 승인 상태 `approval_status`(`pending`, `approved`, `rejected`)를
별도 필드로 보존한다. 입력에서 생략하면 각각 `user_declared`, `pending`으로 정규화한다.
`system_suggested`에는 `suggestion_reason`이 필수다. 이 승인은 컬럼 Mapping에만 적용되며
생성될 Claim의 epistemic class를 `confirmed` 또는 `pin`으로 승격시키지 않는다.
정본 Profile의 루트는 `profile_version/source/packs/mappings` 네 필드만 허용한다.
`validate_profile`, `validate_profile_errors`, `serialize_profile`, `validate_profile_section`,
`public_profile_schema`는 이 canonical 계약만 다루며 입력 모양으로 구형 draft를 자동
판별하지 않는다. 구형 6필드 draft는 명시적 `validate_legacy_profile()`에만 격리되어 있고
canonical metadata에도 노출되지 않는다.

`allowed_binding_kinds`는 Role별 허용 binding을 좁히고, Binding kind descriptor의
`allowed_role_kinds`는 `RoleDescriptor.kind` 호환성을 별도로 검사한다. `transfer/movement`
의 `from`은 `kind=position`이며 `source_position`이 Pack에 등록된 symbolic constant라서
통과한다. 다른 임의 문자열은 거절한다. Binding kind 추가는 `BindingKindDescriptor`
등록으로 이루어지고 validator에 source별 조건문을 추가하지 않는다. 임의
Python·SQL·JavaScript·eval/exec와 범용 expression DSL은 지원하지 않는다.

전용 오류는 `unknown_pack`, `unsupported_pack_version`, `unknown_claim`,
`missing_required_role`, `unknown_role`, `invalid_binding`, `duplicate_mapping_id`,
`unsupported_profile_version`이며 모두 `code/path/message`를 가진다.
`validate_profile_errors()`는 여러 오류를 경로·code·message 기준으로 결정적으로 정렬한다.
`validate_profile()`은 그 첫 오류를 `ProfileValidationError`로 발생시킨다.
같은 입력은 두 함수에서 항상 같은 수락/거절 판정을 갖는다.

구조 검증과 실행 가능 판정은 분리한다. `profile_readiness_errors()`와
`require_executable_profile()`은 이미 검증된 `SourceOntologyProfile`만 받고 모든 최상위
Binding과 `declared_lookup.key` 같은 중첩 Binding의 `approval_status`가 `approved`인지
재귀적으로 검사한다. `pending|rejected`는 `binding_not_approved`와 정확한
`mappings[i].bind.<role>[...].approval_status` 경로로 차단한다. 이 gate는 순수 판정이며
compiler·lookup·translator·DB를 호출하지 않는다.

`serialize_profile()`은 Pack, mapping, role, 객체 키를 정규화해 같은 Profile을 같은 UTF-8
JSON 바이트로 직렬화하며 입력을 수정하지 않는다. `public_profile_schema()`는 canonical
Pack/Claim/Role/Binding metadata만 공개하고 구형 Template/type/status metadata를 내보내지
않는다. predicate signature, atom 분해, Claim 계급
번호, translator/derivation 내부명, canonical key 직렬화, provenance envelope는 없다.

🔴 **2단계 경계:** 이 계약 자체에는 compiler, runtime adapter, translator 호출, atom 생성,
UI, Trace, DB 연결, migration, write가 없다. 실행은 다음 3단계 절이 별도로 소유한다.

### 3.11 LedgerFrame Chain mapper 3단계 (2026-08-17)

> **status:** `FROZEN_FOR_REDESIGN` · **approval:** `NOT_APPROVED`

이 절의 추가 구현은 중지됐다. 다음 실행 계약은
[`ledger_v2_redesign_plan_20260817`](../../ledger_v2_redesign_plan_20260817/README.md)의
단계별 승인 뒤에만 변경한다.

v2 목표는 현행 `declared_lookup`/Position 계약을 계승하지 않는다. cursor 뒤 pandas source
preparer가 verified virtual-join rule ID를 상속하고, 완성 EventFrame 이후 compiler는 DB를
읽지 않는다. Registry 등록 데이터는 `server/config/ontology/` config에서만 온다. 목표 계약은
[TARGET_ARCHITECTURE_AND_SSOT](../../ledger_v2_redesign_plan_20260817/TARGET_ARCHITECTURE_AND_SSOT.md)가 정본이다.

정확한 열·실행·실패·마이그레이션 계약은
[LEDGER_FRAME_CHAIN_MAPPER](../architecture/LEDGER_FRAME_CHAIN_MAPPER.md)가 소유한다.

`LedgerFrame v1`은 schema marker와 고정 14열을 가진 pandas DataFrame이다. 각 행은 기존
`Atom` 후보 하나이며 structured identity/payload, source world time, raw provenance,
derivation, deterministic `source_event_id/state`를 보존한다. pandas index는 identity가 아니다.
`None`, 임의 DataFrame, 열/형식 위반은 `LedgerFrameError(code,path,message)`로 거절하며
`empty_ledger_frame()`만 정상 0-Claim 결과다.

등록 mapper는 기존 Chain 함수 모양 `(db, payload, rule=None)`을 따르되 Ledger worker를
사용하지 않는다. config에는 trusted `mapper_id/version`만 선언하며 entry 함수가 속한 mapper
모듈 전체 artifact의 SHA-256이 `source_translator_ver`에 남는다. 기본 registry는 프로세스당
한 번만 구성한다. mapper context에는 등록 lookup과 snapshot 값만 있고 DB
session/cursor/commit은 없다.

canonical Profile mapper는 승인된 Profile의 `column|constant|declared_lookup`을 평가한다.
lookup은 `resolve_many` 등록 adapter만 사용하며 0건·다건을 각각 `lookup_not_found`와
`lookup_not_unique`로 거절한다. Profile 승인 metadata는 Claim epistemic class를 바꾸지 않는다.

기존 source driver가 canonical 실행을 택하려면
`chain_mapper={mapper_id:"canonical-profile",version:1,profile_id:<id>}`를 선언한다.
`validate_profile_section()` 결과의 `<id>`와 driver source가 config load에서 직접 연결되며,
Profile source 불일치와 미등록 ID는 실행 전에 거절된다. 기존 cursor version에는 mapper
fingerprint뿐 아니라 Profile ID와 결정적 serialization hash도 포함한다.

driver가 mapper에 넘기는 `source_event`는 선언된 `row_identity` 집합을 정렬해 계산하므로
행 순서와 pandas index에 독립적이다. dry-run과 execute가 동일한 Profile, lookup registry,
event context 생성 경로를 사용한다.

`destination_inventory` adapter는 표준 `row_id/business_key_val/container` 표를 별도
read-only transaction에서 최대 1000 key씩 읽는다. 다건 판정을 잃지 않도록 key당 최대
두 결과를 보존하며 실제 lookup 실행·반환 형상 검증만 담당한다. migration이나 write는 없다.

일반 `run_registered_mapper()`는 `legacy_atom`을 `legacy_atom_forbidden`으로 거절한다.
허용 문은 명시적 과거 데이터 import 함수 하나이며, 그 함수는 저장·gate·cursor를 소유하지
않는다.

첫 실제 전환 source는 `lot_event`다. 기존 Ledger reader와 `event_time` cursor는 그대로이고
`lot-event@1` Python mapper가 DataFrame을 LedgerFrame으로 변환한다. 이후 gate와
`LedgerStore.write_batch`는 기존 경로다. mapper/schema/gate 실패는 현재 처리 단위를
저장하지 않고 cursor도 이동하지 않는다. ⚰️ **[2026-08-18/19] 「미전환 source는 기존
translator를 유지한다」는 더 이상 참이 아니다** — 유지할 translator가 없다(`e47d325`).
`ledger_config.json`의 `sources`에 없는 이름은 백필이 `undeclared_source`로 거절한다.

격리 PostgreSQL 수락 검사는 canonical Profile의 dry-run → 동일 mapper 후보 → gate →
`LedgerStore` → 기존 cursor를 한 경로에서 통과시킨다. nested Binding의 pending/rejected와
lookup 0건/다건은 dry-run/execute 모두 같은 오류를 내며 Atom 0·cursor 미이동이어야 한다.

---

## 4. 해결·추적 의미론

### 4.1 네 계급 (설계 §6)

```
0 핀(사람) > 1 확정된 체인 주장 > 2 관측 > 3 추론
```

계급 배정은 **선언된 데이터**(`DEFAULT_RESOLVER_CONFIG`)이지 랭킹 함수에 묻힌 `if` 사다리가 아니다 —
§6이 계급 경계를 **불변식**이라 부르고, 인라인으로 철자된 불변식은 **무관한 동점을 고치던 사람에게 편집당한다.**
운영자는 `server/config/ledger_resolver.json`으로 덮을 수 있고(config-over-hardcode)
**망가진 파일은 반쯤 적용되지 않고 시끄럽게 거절**된다(`ResolverConfigError` → 503).

🔴 **`#<derivation>` → 클래스 3.** 원자의 «내용»이 **소스 행에 없는 config 선언 가정**에 의존하면 추론이다.
관례가 아무리 좋아도 결론은 추론이다 — 그리고 **그것이 결정적인 이유**는
나중에 진짜 관측(본딩 로그·인벤토리·손입력)이 다른 대응을 주장했을 때
**사람이 아무것도 풀지 않아도 관측이 자동으로 이겨야** 하기 때문이다.
관례를 관측으로 매기면 **config 가정이 실측을 이기고**, 그것이 레이어링 가치가 막으려는 역전이다.
판정: [R-2026-08-13-A · §12-8](../process/LEDGER_RULINGS.md).

**상설 규칙은 테스트다.** `test_ledger_trace_contract.py::test_every_declared_derivation_is_explicitly_classified`가
번역기 config가 낼 수 있는 파생을 **전수 열거해** 분류되지 않은 것에서 실패한다 —
새 관례는 조용히 2류로 해소되는 대신 **스위트를 빨갛게 만든다.**

### 4.1-bis 🔴 「실측이 설정값을 이긴다」에 **랭킹 코드가 한 줄도 없다** (2026-08-14)

공정 조건에는 **같은 사실의 두 판본**이 있다 — 장비 로그가 발화한 **실측**(`params_actual`)과 레시피가 선언한 **설정값**(`params_setpoint`).
운영이 요구하는 서열은 「실측이 이긴다」이고, **그것을 위해 새로 쓰인 코드는 이 저장소에 없다.**

| 판본 | 어떻게 계급을 받나 | 계급 |
|---|---|---|
| `params_actual` | 그냥 발화다 — `claim_class`의 **기본 팔** | **2 관측** |
| `params_setpoint` | payload에 **`inferred: true`**(`DEFAULT_RESOLVER_CONFIG["inference_payload_flag"]`) | **3 추론** |

🔴 **이것이 §4.1의 「계급 배정은 선언된 데이터」와 §4.2의 「계급이 가장 바깥」이 **함께** 사주는 것이다.**
`claim_rank_key`가 모든 동점 처리를 **계급 «안»에 봉인**하므로, 설정값 원자가 **더 새롭고 더 높은 우선순위 소스에서 왔더라도** 실측을 이길 수 없다.
새 술어가 하나 들어왔는데 **해결기는 한 줄도 안 바뀌었다** — 그것이 이 층 분리가 정확히 사려던 것이다.

- 🔴 **초록 하나로는 아무것도 증명 못 한다.** 두 원자가 모든 랭킹 층에서 같은 답을 내면 **계급 경계를 제거한 해결기도 같은 답**을 내고,
  그 단언은 계급이 아니라 산술에 대한 것이 된다. 그래서 픽스처(`server/scripts/seed_syn_process_ledger.py`)는 **계급 «만»이 결정할 수 있게** 지어져 있다:
  설정값 원자가 **먼저 쓰여** uuid7이 낮고(층 3이 그쪽 편) · `occurred_at`이 **더 늦고**(층 2b도 그쪽 편) · 두 소스 다 미등재라 **층 1이 동점**이다.
- **계급-맹(class-blind) 뮤턴트를 «같이» 돌린다** — 그 뮤턴트는 **반대 답**을 내야 한다.
  실측(`assy_manager`, 2026-08-14): 두 판본을 다 가진 표본 웨이퍼 **149/149에서 실측이 이겼고, 뮤턴트는 149 전부에서 반대로** 골랐다.
  ⚠️ **합성 데이터·이 개발 박스이고 운영의 증거가 아니다.**

### 4.2 계급 «안»의 순서 — 그리고 그것이 **부르는** 프리미티브

`claim_rank_key`는 **`crud.compute_priority_value`와 «같은 연산»이고 일부러 같은 모양**이다.
저쪽은 셀 소스 층을 매기고 이쪽은 원장 주장을 매긴다 — 둘 다 **권위 층이 가장 바깥인 사전식 튜플**이고,
그래서 「동점 처리가 낮은 권위를 높은 권위 위로 올릴 수 없다」가 **검토자의 기억이 아니라 구성상** 참이 된다.

**두 층은 다시 구현하지 않고 «부른다»**:

| 층 | 무엇 |
|---|---|
| 1. 등재 우선순위 | **`crud.get_source_priority`** — 표시 레이어링이 쓰는 **같은** `SOURCE_PRIORITY` 맵(user 0 < collision_merge 1 < pipeline_parser 2 < custom_script 3 < chain_ingestion 4, 미등재 99). 두 번째 랭킹 맵은 `resolve_priority_map`이 막으려고 쓰인 「서열 이원화」 그 자체다 |
| 2b. 시각 정규화 | **`crud.resolution_ingested_at`** — naive/aware 규칙이 이미 들어 있다 |

층 전체: `(계급, 등재 우선순위, 날짜 있음 우선, occurred_at 내림차순, event id 오름차순)`.
`test_ledger_trace.py::test_rank_key_matches_crud_tuple_shape`가 대응을 pin해 **한 규칙이 두 철자로 갈라지지 못하게** 한다.

### 4.3 🔴 전순서(totality)의 근거 — 뻔한 논증이 **못 쓰인다**

뻔한 논증은 「`id`가 유일 PK이니 마지막 층이 언제나 결판낸다」이고 **그것은 틀렸다**(§1.3).
`PRIMARY KEY (id)`가 PostgreSQL에 거절되므로 **같은 `id`가 다른 `occurred_at`으로 들어오는 행을 DB가 받아 준다.**

**그래도 순서는 전순서이고, 근거는 희망이 아니라 제약이다**:
2b에서 동점인 두 주장은 **같은 `occurred_at`**을 갖고, 3에서 동점인 두 주장은 **같은 `id`**를 갖는다.
**둘 다 동점 = 기본 키 위반.** 즉 **층 2b와 3이 «함께» 기본 키**이고, 전순서는
번역기가 무엇을 발행하는지에 대한 가정이 아니라 **DB가 강제하는 것** 위에 앉는다.

### 4.4 홉 상태 기계

```
resolved      승자가 있고 다투는 것이 없다
candidate     승자는 정해졌는데 «다른 답»이 경합했다 (rank/n)
unresolvable  따라갈 답이 없다 (내용이지 에러가 아니다)
```

- 🔴 **`n`은 «경합한 서로 다른 답»의 수이고 계급을 넘어 센다.** 계급은 **어느 답을 따를지**를 정하지
  **불일치가 있었는지**를 정하지 않는다. 낮은 계급이 다른 답을 말했으면 홉은 `candidate`로 읽힌다 —
  서열은 흔들리지 않지만 **뭔가 어긋났다는 것을 운영자가 듣는다.**
- **경합은 «주장 수»가 아니라 «답»에서 잰다.** 같은 부모 랏을 말하는 원자 셋은 **증인 셋이 동의하는 것**이지
  경합이 아니다. 그것을 `candidate`라 부르면 화면이 늑대를 외치는 법을 배운다.
- `unresolvable`의 하위 태그: `[no_claim]` · `[unusable_payload]` · `[unknown_subject]` · `[no_slot_map]`.

⏳ **`contested`는 «분리 예정»이다 — [R-2026-08-13-B](../process/LEDGER_RULINGS.md).**
설계의 투영 어휘에서 이 경우는 `contested`(승자 선언 + 분쟁 생존)이지 `candidate`(n개 중 하나, 승자 미선언)가 아니다.
확정된 3상태 계약 안에서 `candidate`를 우산으로 쓰는 것은 **슬라이스 1에 한해** 허용되고, 조건이 둘이다:
① **`reason`이 진짜 구분을 싣는다**(`contested: class1 over class2` 대 `candidate: rank k of n`)
② **2주차 enum 확장에서 분리된다.** 🔴 **코드의 3상태 enum은 이 라우트 버전의 계약이지 정본 목록이 아니다 —
소비자가 「candidate = 승자 없음」을 하드코딩하면 안 된다.**

⏳ **`basis: {kind, name}`는 가산 필드로 «승격 예정»이다 — [R-2026-08-13-C](../process/LEDGER_RULINGS.md).**
관례/실측 구분이 `reason` 산문에만 살면 소박한 독해(`includes('convention:')`)가 **판정을 뒤집는다**.
상설 원칙: **`reason`은 사람을 위한 산문이고, 화면이 분기해야 하는 사실은 반드시 구조화 필드로 나간다.**
시기는 `contested` 분리와 **같은 커밋**(라우트 계약을 두 번 흔들지 않는다).

### 4.5 보행 알고리즘

홉 하나 = **질문 하나와 그 답**이고, 보행은 그 질문들을 이 순서로 던진다:

```
has_wafer(lot, slot)          이 자리의 웨이퍼는?
derived_from(lot)             이 랏의 부모 랏은?
slot_map(lot -> parent, slot)  부모 랏에서 이 자리는?
```

그래서 끊긴 사슬이 **「짧다」가 아니라 「답 못 한 질문의 이름」**을 낸다.

🔴 **[2026-08-14 3차] 이 질문들의 «목록»이 더 이상 `ledger_trace`에 적혀 있지 않다.** 인출 집합은 어휘의
`traversable` 선언에서 파생되고(§3.7-quinquies), 재귀가 따르는 낱말은 **SQL 파라미터로 바인드**된다.
**답은 한 글자도 안 바뀌었고 그 불변이 단언돼 있다** — 바뀐 것은 「다음 낱말이 걷기에 들어오는 방법」이다(코드 수정 → 선언 변경).
⚠️ **`observed`는 이 그림에 «나타나지 않는다»** — `traversable: None`이라 걷기가 인출조차 하지 않는다(R-D 부칙 ①).

**`terminal_reason`의 닫힌 어휘**: `[root]`(register는 있는데 `derived_from`이 없다 — 기록된 사슬의 끝) ·
`[dead_end]`(`derived_from`도 register도 없다) · `[unknown_subject]`(원장에 원자 0) ·
`[broken]`(`derived_from` 원자는 있는데 부모 랏을 못 준다) · `[cycle]` · `[depth_cap]`(기본 20).
🔴 **`[root]`와 `[dead_end]`가 갈려 있는 것이 요점**이다 — 앞엣것은 기록된 사슬의 끝이고 뒤엣것은 **아무도 안 적은 것**이다.

🔴 **빈 `hops`는 구성상 불가능하고 그것이 기능 전부다.** 원장이 통째로 비어 있어도
「원자 0인 랏」을 지목하는 `unresolvable` 홉 하나와 `terminal_reason`이 나온다. `trace()`가 `assert`로 그 문을 잠근다.

**조회기 둘, 그리고 기본값이 아닌 쪽**: `SqlClaimLookup`(홉별 CTE)이 기본이고
`OneShotSqlClaimLookup`(한 방 재귀 CTE)은 **유지하되 기본이 아니다** — 작은 원장에서 **20.2 ms로 퇴화**한다
(PostgreSQL이 재귀 CTE의 출력 크기를 추정하지 못해 계획이 전 파티션 스캔 위의 Hash Join으로 뒤집힌다).
**큰 원장·깊은 사슬에서만** 유리하다. `InMemoryClaimLookup`은 교체 가능성을 **검사된 성질**로 만든다
(`test_ledger_trace_pg.py`가 같은 추적을 두 조회기에 태워 답이 동일한지 단언한다).

### 4.6 응답 형태 — **동결**

```
{ hops: [{from, to, predicate, state, rank, n, reason, occurred_at, event_id}],
  terminal_reason, generated_at }
```

(**`/coverage`의 형태는 §6.4-bis**이고 그쪽은 pin이 아니라 **가산 확장 중**이다 — 이 동결은 `/trace`의 것이다.)

🔴 **총괄이 pin했고 클라 레인이 이것에 대고 지어졌다. 바꾸는 것은 편집이 아니라 에스컬레이션이다.**
가산 필드는 가능하다(`predicate`가 그렇게 들어왔다 — 없으면 클라가 `has_wafer` 홉과 `derived_from` 홉을
**`reason` 산문을 파싱해야만** 구별할 수 있고, 이 화면의 요점이 「산문은 사람 몫」이다).
**개명·삭제는 아니다.**

**시각은 «선언된» 존으로 렌더한다**(`display_timezone`, 기본 `Asia/Seoul`) — `generated_at`까지 같은 존으로.
🔴 그전에는 `isoformat()`이 그대로 나가 **오프셋이 PostgreSQL 세션의 `TimeZone`**에서 왔다.
`assy_qa`의 기본이 우연히 `Asia/Seoul`이라 수용 기준이 통과했고 **원장이 선언한 것은 아무 일도 안 하고 있었다.**
「UTC로 내보내고 클라가 현지화」는 **fab 기록의 정확성을 보는 사람의 기계로 옮기는 것**이라 기각됐다.
⚠️ **`utils.time_format.LOCAL_TIMEZONE`이 아니다** — 그것은 import 시점에 해석된 **기계의 주변 존**이라 같은 계급의 결함이다.

### 4.7 `GET /api/ledger/structure` — **유형 수준 응답 계약** (2026-08-14 2차 · `server/ledger_structure.py`)

`/trace`가 **인스턴스**(이 랏의 혈통)라면 이쪽은 **유형**이다 — 랏·웨이퍼·보이드는 응답에 **한 건도 없다.**
라우트 표는 [backend §2](../architecture/backend.md)가 소유하고 **여기는 조용히 깨지면 안 되는 의미론만** 적는다.

```
{ generated_at, state, relation, window{…, forced, forced_reason}, cost{…},
  graph { nodes[], edges[], layers[], mechanism{…} },
  vocabulary{…}, kinds{…}, declarations[], cursors[], drift{…} }
```

**① 🔴 손으로 적은 노드·엣지 목록이 «없다» — 그것이 계약이다.**
제품 소유자의 실패 조건이 문장으로 있다: 「하드코딩된 노드/엣지 목록이 응답 어디에든 보이면 실패입니다.」
**선언된 절반**은 `vocabulary.ENTITY_TYPES` × `PREDICATES`에서, **관측된 절반**은 `ledger_events` 한 번의 `GROUP BY`에서
생성되고 **둘을 병합**한다. 그래서 술어를 어휘에 더하면 **라우트를 한 줄도 안 고치고** 엣지가 생긴다.
🔴 **병합이 설계 전부다** — 선언에만 있는 모양과 데이터에만 있는 모양은 **손으로 그린 그림이 영원히 못 내는 답 둘**이다.
채점은 `test_ledger_structure_pg.py::test_the_graph_follows_a_swapped_vocabulary` — **어휘를 통째로 지어낸 낱말로 갈아끼우고**
그림이 따라오는지 본다. 🔴 **진짜 어휘의 리터럴이 파일 어딘가에 하나만 있어도 빨개진다.**

**② 🔴 상태는 «낱말»로 나가고 클라는 세어서 판정하지 않는다** (R-2026-08-13-C — 화면이 분기해야 하는 사실은 구조화 필드).
엣지의 `edge_state`, 노드의 `node_state`, 값은 다섯:

| 낱말 | 정의 | 이것이 «따로» 있는 이유 |
|---|---|---|
| `flowing` | 선언됨 + 원자 있음 | — |
| `declared_only` | 선언됨 + **세었고 0** | 🔴 **정직한 빈 축.** 숨기면 「어휘엔 있는데 아무도 안 쓴다」를 아무도 못 본다 |
| `undeclared` | **원자가 있는데 어휘가 그 모양을 선언 안 함** | **드리프트.** 버리면 온톨로지가 조용히 포크한다 |
| `unmeasured` | **아무도 안 셌다**(관계 부재) | `0`으로 쓰면 「데이터가 없다」는 **거짓 주장**이 된다 |
| `declared_unconsumed` | 선언됨 + **소비자 0** | `declared_only`는 「세었더니 0」, 이쪽은 **«셀 것 자체가 없다»** — 기전 층 |

**③ 🔴 `atoms: 0`과 `atoms: null`은 다른 답이다** — `/kinds`와 **같은 규칙**(한 낱말이 여러 라우트에서 한 뜻).
`0` = 세었고 없다, `null` = 아무도 안 셌다. **선언돼 있고 건수 0인 엣지는 어떤 경우에도 숨기지 않는다.**

**④ 🔴 창(`window`)은 «건수»만 좁히고 «선언»은 절대 안 좁힌다.**
창이 걸려도 선언된 엣지는 전부 응답에 남고 `atoms: 0`이 된다. 🔴 **이것을 뒤집으면 아래 크기 게이트가 ③의 규칙을 무력화한다** —
크기 때문에 창이 «강제»된 응답에서 축이 사라지면, 방어가 정직성을 먹는다. `window.forced`·`forced_reason`은 그때 응답이 스스로 대는 이름이다.

**⑤ 🔴 그림은 «두 층»이고 `graph.layers[]`가 그것을 열거한다** — `ledger`(유형 그래프)와 `mechanism`(M4 기전 그래프).
**두 층의 노드·엣지 필드 이름이 같아 렌더러는 하나다.** 클라는 층 이름을 **알지 않고 열거된 것을 그린다.**
⚠️ **2026-08-14 실측: `mechanism`은 `state: "absent"`다.** [PHYSICS_ONTOLOGY_SETUP §4](../architecture/PHYSICS_ONTOLOGY_SETUP.md)가 완성된 모양을
**제안**하지만 코드가 열 수 있는 선언이 0이다 — config 파일 없음 · 파이썬 dict 없음 · 로더 없음 · 라우트 없음 · 어휘에 `Model` 개체 타입 없음 · **소비자 0.**
응답은 `reason: "no_declaration_file"` + `spec_ref`로 **부재를 말하고, 문서의 제안을 데이터로 옮겨 적지 않는다**(§7의 「선언되지 않은 것에 표현을 지어내지 마라」).
🔴 **이음새는 `server/config/mechanism_models.json`이고 `.sample`은 «일부러» 안 실었다** — 이 프로젝트에서 `.sample`은 **출하된 선언**이라
제안을 그 자리에 두면 **착지한 선언으로 오독된다.** 🔴 **`ledger_link`도 «유도»된다**: 기전 노드는 `Model` 개체 타입을 통해 원장에 닿는데
어휘가 그 타입을 선언하지 않으므로 「붙을 자리가 없다」가 답이고, **`Model`이 선언되는 날 이 문장은 스스로 거짓이 된다.**
✅ **[2026-08-14 · `f52628f`] 앞의 ⚠️ 문단은 «부분적으로» 낡았다** — `server/config/sample/mechanism_models.json.sample`이 착지했고(**모델 셋 · 방향만 있는 엣지 22개 · 코드 0줄 변경**)
그 층은 더 이상 `absent`가 아니다. **[2026-08-14 밤 확정]** 라이브 config도 실재하고 소비자는 **둘**이다 — 이 라우트의 기전 층 + 3관문 랭킹의 기전 관문(`server/mechanism_gate.py`).
🔴 **[2026-08-15 정정] 파일에 `models`라는 블록은 «없다»** — 최상위 예약 키는 `__doc`와 `bindings`뿐이고 **나머지 키 하나하나가 모델**이며(`mechanism_gate.KEY_DOC`/`KEY_BINDINGS`), `signatures`는 **모델 «안»의 키**이고 로더가 읽지 않는다(사람용). 모델은 방향만 나른다 — 방정식은 일부러 없다. **`bindings`**는 필드→물리량이고 🔴 **항목 목록이 아니다**(바인딩 안 된 후보는 좁혀지지 않고 `unknown`을 단다). 선언 방법은 [guide/ONTOLOGY_LEDGER_SETUP §6.1](../guide/ONTOLOGY_LEDGER_SETUP.md).
🔴 **바인딩은 데이터가 실재하는 날 켠다**(`87374a5` — `post_bond_queue_h`가 그 실례. 공백에 바인딩을 지어내지 않는다). 부재 갈래(`no_declaration_file`)는 파일 없는 박스에서 여전히 발화한다.

**⑥ 🔴 등급 분포를 SQL이 «분류하지 않는다» — 그룹 키만 만든다.**
`ledger_trace.claim_class`/`claim_basis`가 권위이고 순수 파이썬이다. `claim_class`의 입력 중 **그룹 컬럼이 아닌 것은 페이로드 플래그 둘뿐**이라
그 둘을 **GROUP KEY로 올리면** 센서스가 **그룹당 한 번 권위를 직접 부를 수 있다.** 그래서 사다리를 재구현하는 코드가 **0줄**이고
`inference_derivations`를 다시 선언하는 사이트는 **양쪽을 동시에** 움직인다(양쪽이 아니라 한쪽뿐이므로).
⚠️ **`claim_basis`의 `rsplit('#', 1)`을 SQL `split_part(…, 2)`로 옮기면 구분자가 둘인 버전 문자열에서 «틀린다»** — 옮기지 말 것.
채점 `test_ledger_structure_pg.py::test_the_class_breakdown_agrees_with_claim_class`.
🔴 **모듈 docstring의 「THE RESOLUTION CLASS IS COMPUTED IN SQL」 절은 «버려진» 철자를 서술한다** — 코드와 `CENSUS_SQL` 주석이 정본이다(§5.7의 마지막 줄).

**⑦ 🔴 등록 엣지는 이름이 아니라 «모양»으로 식별된다** — `object_kind IS NULL`이 존재 주장이다.
`predicate == "register"` 리터럴이 먼저 쓰였고 **어휘를 갈아끼우는 테스트가 잡았다**(등록 낱말의 철자가 다른 어휘에서 카운트가 조용히 `null`로 남았다).
근거는 어휘 자신의 규칙이다 — 목적어가 ∅인 술어가 **하나뿐**이고 `ck_ledger_register_has_no_object`가 그 술어에 **대해서만** 강제한다(§1.2).
⚠️ **합성 타입은 등록이 없는 것이 설계**라 `0`이 아니라 `null`로 남는다.

**⑧ 200이 아닌 결말은 «정확히 셋»이다.**

| 코드 | `reason` | 언제 |
|---|---|---|
| 422 | `/siblings`와 **같은 토큰** | `window` 형식 오류 — 파서 철자가 하나(`ledger_siblings.parse_window`)라 토큰도 하나 |
| 503 | `vocabulary_unreadable` | 어휘 모듈을 못 읽음 = **배포 사실**이라 이름을 대고 답한다 |
| 503 | `resolver_config_refused` | 못 쓰는 표시 존 — `/trace`·`/coverage`와 같은 문 |

🔴 **`ledger_events` 부재는 «에러가 아니다»** — 200 + `state: "absent"`이고 **선언된 절반은 그대로 나간다.**
원장이 없는 박스에도 온톨로지는 있고, **빈 화면을 보고 있는 사람이 바로 그것을 봐야 할 사람**이다.

**⑨ ✅ [2026-08-14 3차 — 뒤집혔다] `kinds` 패널이 이제 «원장 안»을 가리킨다.**
🔴 **종전 서술은 「`measured`·`observed` 같은 술어는 선언된 적이 없고, 모든 종류가 `in_ledger: false`이며 `ledger_edge_ids`가 빈 배열」이었다**
(`3202ac7` 실측). R-2026-08-14-D의 번역이 그것을 **거짓으로 만들었다** — 지금 실측(같은 박스, 같은 라우트):
엣지 **`Wafer|observed|value`**가 `edge_state: "flowing"` · 원자 **102,177** · **전량 등급 `observation`(2류)** ·
`first_at` 2026-08-13T00:00+09:00 ~ `last_at` 2026-11-21T15:25+09:00 · `source_who`로 두 소스가 갈려 보인다.
🔴 **그때의 빈 배열이 「연결 실패」가 아니라 「그런 연결은 없다」는 «답»이었던 것처럼, 지금의 수도 선언과 측정의 합이다** —
`link`/`link_reason`은 여전히 구조화 필드로 사실을 말하고, 오늘은 **다른 사실**을 말한다.
⚠️ **아직 참인 것 둘**: ① `measured`는 **여전히 미선언**이다(발화자 없음 — §3.7) ·
② **`Equipment`·`Product`는 선언돼 있고 원자가 0**이다(설비 신원이 `processed_with`의 **`value` 페이로드 «안»에만** 살고
`entity_ref`로 나온 적이 없어 **고립 노드**로 보인다. 엣지의 `object_fields`가 그것을 화면에서 **보이게** 만든다).
🔴 **「한 렌더러 · 통합 어휘」는 아직도 전제로 삼지 말 것** — 요인 축 8개가 여전히 옆조인이고, R-D 원칙 ④가 그것을 **과도기**로 선언했다.

**⑩ `server/ledger/`는 여전히 부팅 경로에 없다.** 이 모듈은 웹 서버의 라우터가 import하지만
`vocabulary`는 **호출 «안»에서 지연 import**한다. 비용 때문이 아니라([가이드 §0](../guide/LEDGER_GUIDE.md)의 보증을) **글자 그대로 참으로 두기 위해서**다.
🔴 **[2026-08-14 3차] `ledger_trace`도 같은 문법으로 어휘를 쓴다** — 걷기 술어 집합이 선언에서 파생되면서
`ledger_trace`가 `ledger.vocabulary`를 **부르게 됐지만 import는 `_vocabulary()` «안»에 있다.** 보증은 유지되고,
⚠️ **「`ledger_trace`는 `server/ledger/` 패키지를 import하지 않는다」고 «단정»한 서술은 이제 거짓**이다(모듈 최상단이 아닐 뿐이다).

**⑪ ✅ [2026-08-15 · R-2026-08-15-M · 갱신 트리거 ⑧] 술어 행마다 `origin`이 «가산»됐다 — 기존 필드는 하나도 안 바뀌었다.**
`origin: "code" | "config"`가 **`declared_edges`와 어휘 패널 «둘 다»**의 행에 붙고, 두 자리 모두
`PREDICATES`가 아니라 **`vocabulary.all_predicates()`를 순회한다.**
🔴 **그 순회 변경이 없으면 선언으로 등재한 낱말이, 「원장이 무엇을 말할 수 있는가」를 보여 주려고 존재하는 «유일한» 화면에서 안 보인다** —
그리고 **등재됐는데 안 보이는 것은 운영자에게 저장이 실패한 것과 구별되지 않는다.**
🔴 **`origin`은 장식이 아니라 ①의 짝이다** — 이 응답은 손으로 적은 목록이 없다고 약속하므로 독자가 「이 낱말은 어디서 왔나」를 스스로 셀 수 없다. 그래서 응답이 말한다.
⚠️ **`since`로 대신 유추하지 마라** — 그것은 슬라이스 번호이지 출처가 아니다.
⚠️ **`origin`은 «값»이지 상태가 아니다** — ②의 `edge_state` 다섯과 직교이고, `config`라고 해서 덜 선언된 것이 아니다.
**같은 라운드에 `server/ledger_journey.py`의 술어 조회도 병합 뷰로 옮겼다** — 안 옮겼으면 config 낱말만 자기 `label_ko`를 잃고
**한국어가 원시 이름으로 조용히 강등**됐을 것이다(§3.7-quater의 폴백이 그때 잘못된 자리에서 발화한다).

### 4.8 `GET /api/ledger/kinds` — **원장 위치 필드 다섯** (2026-08-14 3차 · `server/ledger_kinds.py` · 갱신 트리거 ⑧)

라우트 표는 [backend §2](../architecture/backend.md)가 소유하고 여기는 **조용히 깨지면 안 되는 의미론**만 적는다.
이 라우트는 원래 **소스 테이블**을 답했다(관측 수·런 수·`observed_by`·`classes`). 관측 번역이 착지하면서
종류마다 **원장 쪽 위치**를 말하는 필드가 다섯 붙었다 — **가산 확장이고 기존 필드는 하나도 안 바뀌었다**
(⚠️ 응답 형태는 `client2/src/case_control_core.js::kindCatalog`가 소비하도록 pin돼 있다).

| 필드 | 계약 |
|---|---|
| `in_ledger` (bool) | 🔴 **선언 사실이지 데이터 사실이 아니다** — `ledger_config.json`의 어떤 소스가 이 종류를 번역한다고 «선언»했나. **질의 0회** |
| `ledger_source` / `ledger_predicate` | 그 소스 이름과 술어(오늘은 `observed` — 철자는 `ledger/config.OBSERVATION_PREDICATE` **한 자리**) |
| `ledger_state` | **측정된 절반.** `/structure`의 낱말을 **일부러 그대로** 쓴다(한 낱말이 여러 라우트에서 한 뜻): `absent` · `declared_only` · `flowing` · `unmeasured` |
| `ledger_atoms` (int \| null) | 그 수. 🔴 **`null`은 `0`이 아니다** — `null` = 「아무도 안 셌다」(관계 부재 또는 이 요청이 살 수 없는 비용), `0` = 「세었고 없다」. 게이트는 `/coverage`·`/kinds`가 이미 쓰는 **256 MB 규칙** |

- 🔴 **불리언 하나로는 부족해서 둘로 나눈 것이 이 확장의 «전부»다.** 번역 전 상태가 정확히 그 반례였다 —
  보이드 91,756건이 소스 테이블에 사는데 `in_ledger: false` 하나뿐이었고, 그 낱말은
  **「아무도 선언하지 않았다」와 「선언은 됐는데 백필을 아직 안 돌렸다」를 구별하지 못했다.** 운영자가 할 일이 정반대인 두 상태다.
- 🔴 **`declared_only`와 `unmeasured`의 구별이 이 프로젝트가 이미 값을 치른 자리다**(`absent-zero-is-not-inert-zero`) —
  「번역기가 한 번도 안 돈 종류」와 「셀 수 없는 종류」를 같은 화면 기호로 그리면 둘 다 「0」으로 읽힌다.
- ⚠️ **이 라우트는 여전히 «아무것도 선언하지 않는다».** 종류의 정의는 `server/finding_kinds.py`,
  어느 소스가 어느 종류를 번역하는지는 `ledger_config.json`이다 — **여기에 세 번째 목록이 생기면 드리프트가 보이지 않게 된다**
  (적히는 날엔 언제나 일치하므로).

### 4.9 `GET /api/ledger/journey` — **주어 «둘» 전용 응답 계약** (2026-08-14 밤 · `server/ledger_journey.py` · 갱신 트리거 ⑧)

라우트 표는 [backend §2](../architecture/backend.md)가 소유하고, 운영자가 읽는 법은 [guide §4.6-quater](../guide/LEDGER_GUIDE.md)다.
여기는 **조용히 깨지면 안 되는 의미론**만 적는다. 이 라우트는 새 사실을 계산하지 않는다 — **원장이 이미 든 원자를 순서로 재배치**한다.

🔴 **[2026-08-15 3차] 그 인출은 «뿌리 키로 롤업»한다**(§3.7-septies · R-2026-08-15-O) — `subject_type` 하나가 아니라
`rollup_subject_types(<주어 타입>)` 전부를 읽는다. 그래서 **웨이퍼 두 장을 물으면 그 웨이퍼의 `WaferLeg` 원자도 같이 온다.**
⚠️ **응답 형태는 이 변경으로 한 바이트도 안 바뀌었다** — 채워진 것은 **빈칸**(§ⓑ의 `segment_absent`가 실제로는 「안 보임」이던 자리)이다.

#### ⓐ 🔴 집단 통계는 **없다. `null`도 아니다.**

| 계약 | 철자 |
|---|---|
| 주어 수 | **정확히 둘.** 아니면 **422 `scope_is_not_a_pair`** + `arity_resolved` + **해결된 주어 이름**. 강등해서 표를 그리지 않는다 — 다섯 열짜리 표가 이 화면이 «치우려던» 그것이다 |
| 없는 필드 | `enrichment` · `enrichment_ci` · `rate` · `rate_delta` · `std_diff` · `case` · `control` · `candidates` · `min_support` — **키가 아예 없다**(실측: 라이브 응답 재귀 키 스캔 0건) |
| `gates` | **두 항목**: `upstream`(「시간상 앞섬」 — `occurred_at` 두 개의 비교라 모집단이 필요 없다) · `mechanism`(「물리 경로 있음」 — 선언의 인용) |
| `statistics` | `{state: "not_applicable", arity: 2, message}` — **셋째 관문이 고장이 아니라 «부재»임을 말하는 자리**다 |

- 🔴 **`null`로 내지 않는 이유가 이 절의 전부다**: 존재하는 필드는 언젠가 렌더되고, **웨이퍼 두 장 위에서 계산된 신뢰구간은 이 프로젝트가 에러보다 나쁘게 치는 「확신에 찬 거짓」**이다.
- 🔴 **`arity: 2`가 «필드»다.** 「`candidates`가 없으니 2장 모양이겠지」로 추론하는 클라는 언젠가 틀린다.
- **3장 이상의 답은 `/siblings?scope=`이고 그 응답은 이 라우트가 생겨도 한 바이트도 안 바뀌었다** — n=2 모양을 집단 통계가 계약에 든 엔드포인트에 «모드»로 접는 것이 위 필드가 `null`로 새는 경로다.

#### ⓑ 🔴 한쪽 값의 상태가 **넷**이고, 그중 **셋이 「없음」처럼 생겼다**

| 상태 | 뜻 | 실측(`assy_manager`, 합성) |
|---|---|---|
| `recorded` | 값이 있다 — **`0`과 `false`를 포함한다** | `SYN-BW-001-01/-02` BONDING의 `params_setpoint.purge_delay_s = 0` |
| `recorded_null` | 소스가 **명시적으로 JSON null을 발화**했다 | ⚠️ **도달 가능하지만 이 박스에서 미실증** — `processed_with` payload의 명시적 null **0건** |
| `not_recorded` | 이 주어는 그 구간을 **걸었는데** 이 경로의 잎이 없다 | `SYN-BW-001-01` vs `-02`의 `params_actual.*`(둘 다 걸은 BONDING) |
| `segment_absent` | 이 주어는 **그 구간 자체를 안 걸었다** | `SYN-BW-101-06`은 `MI_THICKNESS` 원자가 **아예 없고** `-15`는 748.41 µm를 쟀다 |

🔴 **셋을 한 낱말로 접으면 화면이 조용히 거짓말한다** — 「측정 안 함」은 **그 주어 그 구간에 대한 사실**이고 「구간을 안 걸음」은 **다른 사실**이다.
위 두 쌍이 그 구별을 «한 행 안에서» 보여 준다: 같은 BONDING 구간에 `not_recorded`인 잎과 `recorded`인 `0`이 나란히 앉는다.

#### ⓒ 🔴 육하원칙 — **봉투→슬롯 매핑 «하나»**, 그리고 「왜」만 층이 다르다

- 원장은 **다섯**을 답한다(`who`·`when`·`where`·`what`·`how` — 전부 봉투 필드에서. 소유자 정정: 「엄밀히 원장은 누가·언제·어디서·무엇을·어떻게까지」).
  🔴 **술어별 조립 코드가 없다** — 매핑 하나가 모든 술어의 모든 원자에 돈다. **내일 번역된 술어도 같은 카드로 렌더되면 맞게 지은 것이다.**
- 🔴 **「왜」는 인용이지 사실이 아니다.** `layer: "declaration"` · `is_missing_record: **false**` · `citation{config, model, model_version, model_version_state}`.
  ⚠️ `model_version`은 **`null`일 수 있고 그것이 정직한 답이다**(실측: `mechanism_models.json`의 어느 모델도 `version`을 선언하지 않는다 — 「v0」을 지어내지 않는다).
- 🔴 **빈 「왜」는 «선언»의 부재이지 «기록»의 부재가 아니고, 상태가 셋이다**:

| 상태 | 뜻 |
|---|---|
| `answered` | 모델이 경로를 댔다(편향 후보 포함 — 그때 문장은 **「발생 아님」** 꼬리를 단다) |
| `declared_no_path` | **모델이 「아니오」라 답했다** — 물었고 답이 왔다 |
| `not_declared` | **아무도 안 물었다** — 그 물리가 선언된 적이 없다 |

  뒤 둘을 합치면 `mechanism_gate`가 자기 문서에서 네 문단에 걸쳐 거절하는 그 결함이다.
- **여섯 슬롯 전부가 `is_missing_record`를 든다** — 클라 규칙 하나가 여섯을 덮고, 「왜」에는 그 값이 항상 `false`라 **「기록 없음」이 그 자리에 칠해질 수 없다.**
  완결성은 **주장이 아니라 측정**이다(`six_completeness.complete` = 여섯 슬롯 전부가 문장을 든다).

#### ⓓ 🔴 세그먼트 — 서수는 **해결 등급 «안»에서** 매긴다

세그먼트 = **`(step_family, step, ordinal)`**, 키는 `<family>/<step>#<ordinal>`.
`ordinal`은 그 주어의 같은 step 원자들 중 `occurred_at` 순위이되 **`ledger_trace.claim_class` 하나 안에서** 매기고, **묶을 때는 등급을 뺀다.**

- 🔴 **그 절이 하는 일**: 장비 로그와 레시피 책은 **같은 물리적 런**을 다른 순간·다른 등급으로 말한다. 등급 안에서 순위를 매겨야 1번 런이 1번 런과 짝지어지고,
  그러지 않으면 **한 번의 본딩이 두 구간으로 쪼개진다.** 실측: `SYN-BW-101-06`의 BONDING은 08-10 01:05/01:45(장비 로그 · 관측 등급)와 08-12 01:05/01:45(레시피 책 · 추론 등급) — **원자 넷, 런 둘.**
- **한 구간의 두 원자가 한 잎을 두고 다투면** 승자는 `ledger_trace.claim_rank_key`(혈통 해결기와 **같은 전순서**)가 정하고 **패자는 `superseded_by_here`로 실려 나간다** — 「실측이 설정값을 이긴다」의 철자는 이 시스템에 **하나**다(§4.1-bis).
- `position_basis`가 **`observation` \| `inference`** — 그 구간의 «자리»가 실측 시각에서 왔는지 레시피 책의 날짜에서 왔는지. 🔴 **순서가 이 화면의 주된 주장이므로 그것이 거짓말할 수 있는 «유일한 방식»에 이름이 붙어 있다**(실측: `SYN-BW-101-06`의 DIFFUSION은 추론 원자로만 존재하고 그 날짜가 BONDING 뒤라 전공정이 후공정 «아래»에 앉는다 — 응답은 조용히 재정렬하지 않고 `notes[]`로 말한다).
- **step 이름이 payload의 «어디»에 있는지는 선언이다** — `ledger_journey.json`의 `segments` 블록([CONFIG_GUIDE §1](../guide/CONFIG_GUIDE.md)).
  `vocabulary.py`는 `processed_with`의 목적어가 `['step','step_family','eqp','recipe']`를 요구한다고만 말하고 **그중 무엇이 step인지는 말하지 않는다** — 목록의 자리로 읽는 것은 관례이고, 관례는 스키마가 다른 날 깨진다.
- **step 값이 없는 여정 원자는 «버리지 않는다»** — 「(step 기록 없음)」이라는 자기 구간을 얻는다. 무슨 일이 있었나를 보여 주는 화면에서 원자가 사라지는 것이 더 나쁜 답이다.

#### ⓔ 선언 층은 **이름만 붙이고 아무것도 좁히지 않는다**

`ledger_journey.json`(라이브) → `.json.sample`(출하) → 부재 순으로 찾고 **`labels.origin`이 `live`\|`sample`\|`absent`를 말한다**(`mechanism_gate`의 규칙 그대로).
🔴 **이름 블록 셋(`step_labels`·`family_labels`·`field_labels`)은 «아무것도 좁히지 않는다»** — 두 주어 원자의 **모든 잎**이 이름 유무와 무관하게 비교되고, 이름 없는 잎은 **원시 경로로** 렌더된다(정직 우선). 그 셋을 통째로 비워도 **구간·항목·값의 수는 0개 줄어든다.**
🔴 ⚠️ **그러나 `segments` 블록은 다르다 — 그것은 «구조적» 선언이라 없으면 그릴 축이 없다.** 선언된 여정 술어가 하나도 없으면 응답은 200이되 `state: "absent"` · `reason: "no_journey_predicate_declared"`이고 **`segments: []`**다.
**즉 「파일이 없어도 다 나온다」는 이름 층에 대해서만 참이다** — `ledger_journey.py`(및 `.json.sample`)의 산문은 이 구별 없이 「파일을 지워도 구간·항목·값이 안 준다」고 적고 있고, **그 문장은 `segments`에 대해 거짓이다**(코드가 정본 — 총괄 보고 대상).
**부재·깨짐이 예외가 아니라 상태(`labels.state`)인 것은 양쪽 모두 참**이다 — 세부는 [CONFIG_GUIDE §1](../guide/CONFIG_GUIDE.md).

---

### 4.10 R&D Trend와 Composite CHIP 읽기 계약 (2026-08-14)

`GET /api/ledger/trends`는 정식 원장 주어인 **WaferLeg**를 grain으로 삼는다. identity key는
`{wafer,bonding_leg}`이며 동일 Base WF의 서로 다른 LEG를 절대 합치지 않는다. 선언된 종류와
subtype 수를 고정하지 않고 `finding_kinds[]`·`series[]`로 내며, 모든 차트 점과 표 행은
같은 구조화 identity와 `mark_key`를 사용한다. `limit`은 keyset page 예산,
`max_points`는 series별 DB 다운샘플 예산이다. 둘 다 도메인 cardinality 제한이 아니다.
시간 창은 필수(미지정 시 90d를 명시 적용, 최대 366d)이고 `observed` 파티션만 읽는다.
`found_rate` 분자는 원장 `observed`, 분모는 finding 등록부가 선언한 method의
`inspection_run`을 `(base_wafer_id,base_x,base_y) → bonding_map(base,x,y,leg)`로 정확히
결합한 값이다. 검사된 wafer+LEG만 양수 `scan_denominator`를 가지며 발견 0이면
`state=scanned_clean`이다. 관측 부재만으로 clean을 만들지 않으며 numerator/denominator를
응답에 함께 보존한다.
선택 목록과 query 조립의 상세 계약은 [TREND_DECLARATION_GUIDE](./TREND_DECLARATION_GUIDE.md)가
정본이다. 응답은 전체 `selectable_finding_kinds[]`(active/label/subtype/series/metrics)와
실제 `applied_kinds[]`를 분리한다. 선언 없는 종류, 명시적 빈 선택, 비활성 종류는 SQL 전에
거절하며 사용자 SQL을 실행하지 않는다.
Trend Table의 DT/Core 추적 열은 응답 `trace_dimensions[]` 선언과 행별
`traceability.{dt,core}`로 제공한다. Final Bond Wafer에 명시 귀속된 `transferred` component만
분모로 삼아 `ready|partial|absent`, count, component denominator, evidence ID를 계산한다.
page wafer+LEG와 같은 시간창으로 유계화하며 finding 부재를 추적 부재로 해석하지 않는다.

`mark_key`는 `wafer-leg:v1:` 뒤에 canonical UTF-8 JSON 배열
`["WaferLeg",wafer,bonding_leg]`의 unpadded base64url을 붙인다. decode 뒤 canonical
재인코딩이 일치해야 하므로 구분자 충돌이 없다. cursor v2도
`(occurred_at,wafer,bonding_leg)`를 보존한다. 기존 `Wafer` observed atom은 LEG를 추측해
fan-out하지 않고 복합 Trend에서 제외한다. 이는 JSON identity/vocabulary의 additive 확장이므로
DDL migration은 없지만, 생산 translator가 `WaferLeg register/observed/processed_with` 원자를
발화하고 기존 데이터는 declared LEG bridge로 재번역해야 한다.

`GET /api/ledger/composition`은 final CHIP을 `components[]`와 DAG로 답한다. component가
기본 단위이며 각 항목은 안정 id, Core 출처/종류/역할, bonding layer/position,
ordered `transfer_events[]`, 방문한 모든 DT collection, 해소 상태, upstream process
evidence id를 보존한다. `upstream_process.events[]`는 `processed_with`의 step/family,
equipment, recipe, 실제값·설정값 parameter와 원 payload를 그대로 보존하며, 키가 없는 값은
만들지 않는다. 과거 `upstream_process.evidence_ids[]` 이벤트 요약은 하위 호환 필드다.
`core.branch`와 `core.lineage.events[]`는 `has_wafer`/`derived_from`의 다중 parent/path를,
`final_subject_resolution`은 bond-layer의 명시적 `bond_wafer` 후보 전부와
`resolved|contested|absent`를 보존한다. fixture의 answer-key/원인 태그는 계약 입력이 아니다.
**한 CHIP→대표 DT→Core** 모양은 계약 위반이다. assembly는
many-to-many DAG이고 ordered인 것은 component 하나의 이동 경로뿐이다. component를
role/type/layer로 대응시킨 뒤에만 upstream process 차이를 정렬할 수 있으며 구성 차이와
공정 차이는 서로 다른 컬렉션이다.

현행 일반 `transferred` 원자 72,485건 실측에서는 `position`이 null이고 final-chip
component id가 없어 이 계약으로 역추적할 live bridge가 없다. SYN fixture만 새 payload
필드(`component`, `sequence`, 위치)를 발화하며 술어는 기존 `transferred` 그대로다.
새 DDL·구 그래프 저장소는 없다. 다만 물리량 계측을 위해 닫힌 어휘에 `measured`가
`since: 4`로 추가됐고, UI의 `measured_as`는 원장 술어가 아니다.

`POST /api/ledger/selection/resolve`는 [UNIVERSAL_MARKING_SCHEMA](./UNIVERSAL_MARKING_SCHEMA.md)
v4 `WaferLeg` Mark를 원장/선언된 map frame 근거로 FinalChip subjects에 해소하며 응답의
`schemaVersion`과 `schema_version`도 4다. `id/groupId`, 후보 전부,
evidence ID와 path를 보존하며 이름/좌표 유사도로 주어를 만들지 않는다. `map_cells`는
`wafer_map_metadata(target_table,map_id)`와 허용된 source table의 정확한 좌표가 모두
맞아야 한다. 응답 `maps[]`는 frame의 1-based start, `y_invert`, rotation/side 및
valid-die/process/used/supply-material/defect layer를 그대로 싣는다.
Bond map cell의 LEG는 `bonding_log(base_id,bx,by)`와 `bonding_map(base,x,y,leg)`의 정확한
좌표 결합으로만 얻는다. 결과 map projection도 `subject_wafer+subject_leg`로 격리한다. 직접
LEG 근거가 없는 DT/Core cell과 구 `Wafer` mark는 여러 LEG로 펼치지 않으며, 후자는
`legacy_wafer_requires_bonding_leg`로 명시 거절한다.

Process facet은 `(step, recipe, occurrence)`의 발생만 비교한다. `equipment`·`step_family`·
`params_actual`·`params_setpoint`·knob/value는 후보화하지 않으며 수치 비교는 `measured`만 한다.
발생 차이의 0.5 평활 log-odds는 raw effect와 분모를 보존하지만 categorical Process에
기전 수치 binding을 붙이지 않는다.

Measurement facet은 signature의 `metric/unit/method`와 실제 존재하는 linkage만 보존한다.
payload `state`는 `recorded|missing|not_performed|unknown`의 닫힌 집합이고, `recorded`만
`value/run_uid`를 요구한다. 나머지 셋은 `value` 키가 금지된다. 응답 `groups[]`는
`state_counts`, 원값 목록 `values[]`, 단일 원값일 때만 `value`, 분모, WaferLeg mark와
evidence ID를 낸다. 평균·0·null sentinel을 발명하지 않는다. 선택된 주어에 원자가 하나도
없을 때만 명시적 부재 `{state: absent, reason: measured_evidence_absent}`를 낸다.

공정 비교는 subject grain을 보존한다. Core Wafer의 `processed_with`는 component population과
Core type/branch signature를 사용한다. `WaferLeg processed_with`(예: FINAL_BOND)는 analysis-unit
population을 사용하고 Core type/branch를 붙이지 않는다. 후자를 component마다 복제하면
LEG 조건과 Core 종류의 거짓 cross-product 및 잘못된 분모가 생기므로 금지한다. sequence도
component sequence와 `analysis_unit_sequence`를 분리해 unit event를 layer 수만큼 증식하지 않는다.

process/context facet은 top-level과 `groups[]`마다 해당 조건의 component가 실제 귀속된
Final Bond Wafer+LEG `wafer_mark_keys`와 facet별 `evidence_ids`를 함께 낸다. sequence cluster와
difference도 같은 final-wafer mark를 보존한다. 따라서 비교 행→Trend 역마킹은 클라이언트의
이름 결합이나 추가 SQL 없이 수행하며, final bond wafer가 증거에 없으면 mark도 부재다.

## 5. 측정된 특성 — **항목마다 출처 라벨**

> ⚠️ **전부 합성·이 개발 박스다. 운영 증거가 아니다.**

### 5.1 홉 비용은 원장 «크기»에 평평하다
**0.986 → 0.997 ms/홉, 20배 원장에서** (`01452d5`, 합성·이 박스). 랏 단위 추적이 질의 시점 해결로 가는 근거.

### 5.2 🔴 추적 비용은 **파티션 수**를 따라간다
**같은 18,000원자에서 파티션 1개 2.34 ms/추적 대 60개 16.47 ms — 7.0배, 파티션당 +0.24 ms**
(`01452d5`, 합성·이 박스). 혈통 보행은 `occurred_at` 술어를 갖지 않으므로 **가지치기가 원리적으로 발화하지 않고
홉마다 전 파티션을 방문한다.** 월 단위 파티션 판정의 청구서다 — **10년 원장 ≈ 120파티션 ≈ 30 ms/추적.**
월 단위를 뒤집지는 않는다(가지치기·detach는 다른 질의들이 결정한다). 물질화된 투영은 파티션을 걷지 않으므로 이 세금을 안 낸다.

### 5.3 슬롯 단위 혈통은 질의 시점에서 **죽는다**
**인라인 452 ms/건 대 물질화 0.58 ms/건 — 780배이고 20배 원장에 34.8배로 초선형**
(2026-08-12 1000랏 프로브, 합성·이 박스). 설계 §10의 「초기엔 질의 시점 해결」은 **랏 단위 추적에만** 성립한다.
🔴 이것이 `ledger_trace.py`의 3분할(해결기/조회기/보행)이 **구조 요구**인 이유다 — 주 2의 슬롯 작업은
조회기를 물질화된 것으로 **바꾸기만** 하면 되고 해결기는 한 줄도 안 바뀐다.

### 5.4 바이트
힙 **312.8 B/원자**, 총 **673 B/원자** (300,000원자 · `VACUUM ANALYZE` · PG 18.3 · 이 박스).
1,000만 원자 ≈ **6.7 GB**. 인덱스가 청구서의 **더 큰 절반**이다. 항목별은 §2.

### 5.5 백필 규모 — 두 박스, 다른 데이터
| | `assy_qa` (`f896020`) | `assy_manager` (2026-08-13) |
|---|---|---|
| 소스 `lot_event` 행 | 43 | **44** (`split` 28 · `merge` 10 · `track_in` 5 · `123` 1) |
| 원자 | **878** (register 245 · has_wafer 466 · slot_map 148 · derived_from 19) | **909** (has_wafer 491 · register 245 · slot_map 153 · derived_from 20) |
| 파생별 | — | positional_row 491 · first_sight 245 · **slot_preserving 127** · shared_wafer 26 · pair_field 20 |
| 분자 | — | 26 (**거절 1** · 불완전 2) |
| `occurred_at` 폭 | — | 2026-05-03 02:17 ~ 2026-05-21 20:33 **KST**, 파티션 `ledger_events_2026_05` **하나** |
| 추적 가능 랏 | — | **25** (register 랏 수와 일치) |

⚠️ **처리량(초당 원자)은 이 라운드에 따로 기록되지 않았다.** 런이 자기 `result["seconds"]`에 보고하므로
필요하면 그 필드를 인용할 것 — **여기 숫자를 지어 넣지 말 것.**

### 5.5-bis 관측 번역 규모 — **한 소스가 원장을 두 배로 만들었다** (2026-08-14 3차 · `assy_manager` · 합성)

| | `void_obs` | `delam_obs` |
|---|---|---|
| 소스 행 | 91,756 | 10,421 |
| **원자** | **91,756** | **10,421** |
| 거절 / 불완전 | **0 / 0** | **0 / 0** |
| 실행 시간 | 20.8 s | 2.9 s |
| `source_translator_ver` | `void_obs/1/rules:fadf97f0` | `delam_obs/1/rules:a4212d3f` |

🔴 **행 하나 = 원자 하나**이고 그것이 이 문법의 정의다(혈통은 한 사건이 원자 수십 개를 낸다 — §5.5의 26분자 909원자와 비교).
🔴 **거절 0이 「검사가 안 돌았다」는 뜻이 아닌 것**은 반대 팔이 따로 태워져 있기 때문이다(런 미해결 · 미선언 class — [가이드 §3 ⑥](../guide/LEDGER_GUIDE.md)).

**원장 전체**: 84,747 → **186,924원자 · 101,326,848 바이트 · 파티션 다섯**
(`ledger_events_2026_09`~`2026_11`이 **번역기 손에** 생겼다 — 파티션은 배포일이 아니라 **데이터**가 만든다).
`Wafer` 노드의 `atoms_as_subject` **186,206**. ⚠️ **합성·이 박스이고 운영 증거가 아니다.**

### 5.6 재백필 경제
커서 리셋 재실행: **633 시도 / 0 삽입 / 633 dedupe**(`f896020` 당시 `assy_qa`).
시간대 정정 재백필: **878 → 878, `inserted=878 deduped=0`**(`bee1aeb`, `assy_qa`) —
`occurred_at`과 `source_translator_ver`가 **둘 다** dedupe 열쇠에 있고 **둘 다 바뀌었기** 때문이다.
🔴 **두 결과의 차이가 이 인덱스의 의미론 전부다**: 같은 규칙의 재실행은 **전부 걸리고**, 다른 규칙의 재번역은 **전부 통과한다.**

### 5.7 구조 뷰 센서스는 **O(원자)이고, 방어는 캐시가 아니라 크기 게이트다**

**84,747원자 · 두 파티션에서 census 182 ms · 호출 전체 285 ms · 페이로드 59 KB**
(2026-08-14 2차 `3202ac7`, `assy_manager`, 이 박스 — §4.7의 라우트). **원자당 약 2 µs이므로 1,000만 원자에서 ≈ 20 s** —
페이지 로드가 쓸 수 있는 시간을 한참 넘고, **그것이 아래 게이트의 근거다**(가정이 아니라 외삽이라는 점을 떼지 말 것).
🔴 **가지치기는 도울 수 없다** — 이 질의에 `occurred_at` 술어가 없으면 파티션을 전부 방문한다(§5.2와 같은 세금).

**같은 실측이 «이 온톨로지에 대해» 말한 것** (2026-08-14 `3202ac7` · 이 박스 · **픽스처 적재 포함**):
노드 **6** · 엣지 **54**(**흐르는 것 9** · `declared_only` **45**). 🔴 **45가 결함이 아니라 답이다** — 선언된 문법의 대부분이
아직 안 쓰인다는 사실이 처음으로 «보인» 것이고, 그것이 이 라우트를 만든 이유다.
- **`Equipment`·`Product`는 원자 0**(고립 노드) — 설비 신원이 `processed_with`의 **payload 안**에만 살고 `entity_ref`로 나온 적이 없다.
- ✅ **[2026-08-14 3차 — 거짓이 됐다] 「결함 관측은 원장에 «아예 없다»」.** 그 판독 당시엔 `void_obs` 91,756 · `delam_obs` 10,421이
  `finding_kinds`를 통해서만 도달 가능했다. **지금은 엣지 `Wafer|observed|value`가 102,177원자로 흐른다**(§4.7 ⑨ · §5.5-bis).
  🔴 **그리고 그 사실이 이 절의 비용 항목을 움직였다** — 아래 3차 판독.
- ⚠️ **`ledger_config.json`은 소스 «하나»를 선언하는데 원자의 98.9%(84,747 중 83,838)가 그 선언이 이름 대지 않는 `source_who`에서 왔다** —
  생성기(`seed_syn_process_ledger.py`)가 쓴 것이고, **커서 행의 이름은 또 다른 세 번째**다. 응답은 이것을 `undeclared_source:*`로
  **숨기지 않고 보고한다.** 🔴 **픽스처이지 운영 사실이 아니다** — 그러나 **세 이름공간이 어긋난 것은 실재**다.
  - ✅ **[2026-08-14 3차] 새 관측 원자 102,177건은 이 드리프트에 «들어가지 않았다»** — `drift.undeclared_sources`에
    `void_obs`·`delam_obs`가 **없다**(남은 것은 종전의 `syn_eqp_log`·`syn_recipe_book`뿐). 🔴 **「번역기는 자기 소스를 선언한다」**
    (R-2026-08-14-D 2)가 그 결함을 **반복하지 않았다는 증거이고, 그 증거를 내는 것이 이 필드의 존재 이유**다.

- 🔴 **인덱스로 못 없앤다.** 그룹 컬럼이 `subject_type`·`predicate`·`object_payload->>'type'`·`source_who`·`source_translator_ver`이고
  **그 조합을 나르는 인덱스가 없다.** 지어졌다 제거된 셋(§2.2)도 페이로드·출처 컬럼이 없어 **어차피 이 질의를 못 탄다** —
  「인덱스를 되살리면 된다」는 답이 아니다.
- **방어는 선언된 크기 게이트**: 파티션 합계 > `FULL_CENSUS_MAX_BYTES`(256 MB)이면 `LARGE_LEDGER_WINDOW`(`30d`)가 **강제**되고
  응답이 `window.forced`·`forced_reason`으로 말한다. 파티션이 월 단위라 **창이 가지치기를 발화시킨다.**
  🔴 **창은 건수만 좁힌다**(§4.7 ④) — 크기 방어가 「정직한 빈 축」을 먹으면 안 된다.
- 🔴 **캐시하지 않는 것이 판정**이고 근거는 `/coverage`와 같다(§6.4-bis) — 이 화면을 여는 자리가 **백필 직후**라
  캐시는 답이 가장 중요한 순간에 **백필 이전의 구조**를 답한다. 폴링하는 소비자가 생기면 캐시는 **거기에** 둔다.
🔴 **같은 라우트, 관측 번역 이후 (2026-08-14 3차 · 같은 박스)**: 원자 **186,924** · **101,326,848 바이트** · **파티션 다섯**에서
**센서스 85 ms → 438 ms**(그룹 14개). ⚠️ **이 둘은 «같은 라운드에 잰 전·후 쌍»이고 위의 182 ms와 다른 측정이다 — 세 수를 한 줄에 세우지 말 것**(아래 라벨 주의).
🔴 **여전히 `FULL_CENSUS_MAX_BYTES`(256 MB) «아래»라 창이 강제되지 않았다** —
즉 이 화면은 아직 **전 기간 무창(unwindowed)**으로 답하고 있고, 게이트는 **켜진 적이 없지 원자가 늘어서 완화된 것이 아니다.**
⚠️ **원자가 2.2배인데 센서스는 5.2배다** — 원자당 비용이 평평하다고 인용하지 말 것(그룹 수·파티션 수가 함께 움직였다).
바이트가 256 MB에 닿는 날 창이 **자동으로** 강제되고 응답이 `window.forced`로 그렇게 말한다.

- ⚠️ **인용 전에 라벨을 볼 것 — 「285 ms」가 두 뜻으로 돌아다닌다.** 위의 285 ms는 **호출 전체**이고,
  `CENSUS_SQL` 주석의 285 ms는 **버려진 SQL 사다리 철자**의 센서스 값이다(그 비교의 상대는 152 ms).
  그리고 모듈 docstring의 `[SCALE]` 블록은 **철자가 바뀌기 전의 85 ms 쌍**을 아직 들고 있다.
  🔴 **세 수는 같은 것에 대한 세 측정이 아니다.** 어느 것도 다른 것의 갱신본으로 인용하지 말 것.

---

## 6. 실패 모드와 복구

### 6.1 🔴 시간대 선언이 틀렸을 때 — **재백필이지 제자리 UPDATE가 아니다**

**증상이 없다.** 어긋난 instant도 여전히 well-formed하므로 **어떤 가드도 알아챌 수 없다.**
(선언이 `UTC`이던 동안 모든 원자가 9시간 어긋나 있었고 아무것도 항의하지 않았다.)

복구 경로는 **비우고 다시 백필**이다(`bee1aeb`이 실제로 간 길). 🔴 **버전 붙여 공존시키는 것은 «틀린 답»이고 그 이유가 구조적이다**:
해결기는 계급과 `source_who`가 동점이면 **`occurred_at` 내림차순**으로 이긴다.
낡은 집합과 정정 집합은 `source_who='lot_event'`를 공유하고 **틀린 시각이 9시간 «더 늦다»** —
공존시키면 **틀린 원자가 구성상 정정본을 이긴다.**

🔴 **제자리 UPDATE는 애초에 없다** — 원장에 UPDATE 경로가 존재하지 않는다(§7-①).

**결함 주입으로만 잡히는 것 둘**(명세로 남길 값어치가 있는 방법):
① **단언은 instant «와» offset을 둘 다 검사한다** — `astimezone` 철자의 결함은 instant를 보존하므로
instant만 보는 테스트에는 **아예 안 보인다.**
② **주입은 `ledger.store`와 번역기 모듈 «양쪽»에** 걸어야 한다 — 번역기가 `parse_occurred_at`을
자기 이름으로 import해 들고 있어서 **한쪽만 패치하면 성공해 보이는 주입 아래서 진짜 코드가 돈다.**

### 6.2 오염된 트랜잭션 규율

**실패한 DDL 문장은 트랜잭션을 오염시키고, 그 뒤의 모든 질의가 질의와 무관한 이유로 실패한다.**
그래서 이 패키지의 규율은:
- **DDL 전에 카탈로그에 먼저 묻는다**(`to_regclass`) — 예외에서 배우지 않는다.
- **실패 후 재확인 «전»에 롤백은 필수**다.
- 읽기 라우트도 같다: `relation_exists()`가 **요청 트랜잭션을 깨끗하게 유지**한다
  (`UndefinedTable` 하나가 트랜잭션을 오염시키고 그 뒤가 전부 무관해 보이는 이유로 실패한다).

### 6.3 🔴 파티션 DDL 자기 차단 — 이름 붙은 에러 계약

`CREATE TABLE ... PARTITION OF`는 **부모에 ACCESS EXCLUSIVE**를 잡으므로 `ledger_events`의 **모든 열린 리더 뒤에 줄을 선다** —
**같은 프로세스의 리더를 포함해서.** 가설이 아니다: **이 백필의 첫 실행이 실제로 몇 분간 걸렸다.**
psycopg2가 첫 `SELECT`에서 트랜잭션을 암묵적으로 열고 명시적으로 끝낼 때까지 들고 있어서,
페이지 읽기 커넥션이 **idle-in-transaction으로 ACCESS SHARE를 쥔 채** 파티션 DDL을 기다렸다.

**계약 둘:**
1. `backfill.py`가 **쓰기 전에 읽기 트랜잭션을 끝낸다**(`read.rollback()` — 커밋할 것이 없다, 전부 SELECT였다).
2. `SET LOCAL lock_timeout = '20s'`가 **두 번째 그물**이다. 🔴 **자기 차단은 «실패»해야 하고, 무엇을 기다렸는지 말하는
   메시지와 함께여야 한다 — 걸려 멈추면 안 된다.** 멈춘 프로세스는 운영자에게 진단할 것을 아무것도 주지 않는다
   (「계측기는 자기 고장에서 눈이 먼다」).

### 6.4 `ledger_events`가 아예 없을 때

착지 `d78e1ec`. **이 박스의 라이브 라우트(`:8080`)에 대고 재검증됨 — 2026-08-13.**

**판정은 «두 계약» 위에 앉는다: 카탈로그와 SQLSTATE.**

| 자리 | 기전 |
|---|---|
| `/trace` 선조회 | `to_regclass`(`relation_exists`). **raise하지 않고 NULL을 돌려주므로** 요청 트랜잭션이 깨끗하게 유지된다 — `UndefinedTable` 하나가 트랜잭션을 오염시키면 그 뒤 문장이 전부 무관해 보이는 이유로 실패한다 |
| 백스톱(경합) | 선조회와 보행 사이에 릴레이션이 사라지는 경우. **SQLSTATE `42P01`**로 판정한다 — **코드는 어느 언어에서나 코드다** |
| 503 본문 | 🔴 **산문이 아니라 구조**(R-2026-08-13-C). 클라는 `detail.reason`·`detail.state`로 **분기**하고 운영자는 `detail.message`를 읽는다. `state`는 `/coverage`의 어휘를 **일부러 재사용**한다 — 한 낱말이 두 라우트에서 한 뜻 |

🔴 **왜 문자열 매칭을 버렸는가 — 실측이 「뻔한 이야기」를 반증한다.**
옛 갈래(`"does not exist"` 또는 `"UndefinedTable"`)는 **테스트가 하나도 없어 아무도 몰아 본 적이 없었다.**
뮤턴트로 몰아 보니 **그 갈래는 «발화했다»** — 다만 `or`의 **아무것도 보장하지 않는 쪽**에서다.
이 PostgreSQL은 한국어로 말하므로(「…이름의 릴레이션(relation)이 없습니다」) `"does not exist"`는 **이미 죽어 있었고**,
실제로 맞은 것은 **`"UndefinedTable"`** — **SQLAlchemy의 `__str__`이 드라이버 클래스 이름을 접두로 붙이기 때문에만** 나타나는 문자열이다.
생 psycopg2 경로거나 SQLAlchemy가 래핑 에러를 포맷하는 방식이 바뀌면 **배포 사실이 조용히 코드 결함처럼 읽히는 500**이 된다.
**즉 고장나 있던 것이 아니라 «아무것도 보장하지 않는 문자열» 위에 앉아 있었다** — 그것이 옮긴 이유다.

**`GET /api/ledger/coverage`** — 🔴 **부재·공백에도 «에러가 아니라» 200과 `state`를 낸다.**
이 둘이야말로 이 엔드포인트가 존재하는 이유이고, 여기서 raise하면 운영자를 **색깔만 다른 같은 빈 화면** 앞에 되돌려 놓는다.

| `state` | 뜻 |
|---|---|
| `absent` | 마이그레이션 미실행 — 배포 문제 |
| `empty` | 테이블은 있고 원자 0 — 백필 미실행 |
| `ready` | 추적 가능 |

**이 라우트가 가르는 것은 «네 가지 없음»이다.** 원자가 0이면 보행은 모든 랏에 `[unknown_subject]`를 주므로
빈 원장과 진짜 없는 랏이 화면에서 **동일**해진다. `coverage`는 **어느 세계인지**만 말하고
한 랏의 성질(없는 랏 대 혈통 주장 없는 랏)은 **`/trace`가 이미 갈라 답한다**(`[unknown_subject]` 대 `[root] …(register 있음)`) —
**그 판정을 일부러 복제하지 않는다.**

⚠️ `sources`는 `ledger_translator_cursor`에서 온다 — **원장에 누가 썼는지의 자기 등록부**다(§1.5).
`DISTINCT source_who`가 **아닌** 이유가 둘이고 뒤엣것이 더 중요하다: `source_who`에 인덱스가 없어 전량 스캔이고,
**커서 표는 원장이 비어도 답한다** — 「돌았고 전부 거절했다」와 「돈 적이 없다」를 `DISTINCT`는 둘 다 `[]`로 답한다.

### 6.4-bis `/coverage` 응답 형태 — **확장됨** (2026-08-13 `0198e7e`)

```
{ state, lots, sources[], occurred_at:{from,to}, sample[],
  atoms:     {estimate, exact, method, unanalyzed_partitions},
  partitions:{count, list:[{name, bound}]},
  cursors:   [ <커서 행 전체> + refusal_reasons + refusals_unaccounted ],
  last_atom: {occurred_at, recorded_at} }
```

**한 요청이지 둘이 아니다**(R-2026-08-13-F). 상태 표시줄과 어드민 탭이 **같은 본문**을 쓰므로
여기 더해지는 모든 것은 **원자 수에 대해 O(1)**이어야 했다. 오늘 커지는 필드는 `lots` 하나뿐이고
그것은 **원자가 아니라 개체**를 따라간다(부분 인덱스 `idx_ledger_register`를 걷는다).

| 필드 | 어디서 오나 · 그 한계 |
|---|---|
| `atoms.estimate` | ⚠️ **`pg_class.reltuples`의 «추정»이고 `exact`는 «모든» 철자에서 `false`다** — 이 라우트에 행을 세는 갈래가 없다. 파티션 **합**이지 부모에서 읽지 않는다(파티션 부모의 `reltuples`는 0이라 가득 찬 원장을 자신 있게 비었다고 보고한다). 분석된 적 없는 파티션(`reltuples < 0` 또는 `relpages = 0`)은 **0으로 세지 않고** `unanalyzed_partitions`로 «몇 개를 못 봤는지» 말한다 |
| | 🔴 **선택 근거는 «구조»이지 이 박스의 측정이 아니다** — O(1) 대 O(원자). **이 박스는 그 우위를 시연할 수 없다**: 909 원자에서 정확한 `count(*)`는 **0.194 ms**다. 이것을 측정된 승리로 인용하지 말 것 |
| `partitions[].bound` | PostgreSQL이 **렌더한 그대로** 나른다. `FOR VALUES FROM (…) TO (…)`를 여기서 파싱하면 파티션 문법의 **두 번째 철자**가 생긴다 — 화면은 이 모듈의 재해석이 아니라 **DB가 하는 말**을 보여야 한다 |
| `cursors[]` | 커서 표 **전체**. O(소스)라 영원히 몇 행이다. 🔴 **어느 컬럼이 «존재하는지»를 요청마다 카탈로그에 묻는다**(`pg_attribute`) — 마이그레이션보다 앞서 뜬 웹서버가 **500 대신 그 필드 없이** 답한다. `refusal_reasons` 키는 **DB에 컬럼이 있을 때만** 실린다: 언제나 실으면 「서버가 마이그레이션보다 앞섰다」와 「이 행이 컬럼보다 오래됐다」가 **똑같이 렌더**되고, 둘 중 무언가를 실행해서 고칠 수 있는 것은 앞엣것뿐이다 |
| `last_atom.recorded_at` | **uuid7 `id`에서 SQL로 디코드**한다 — 추가 컬럼도 추가 비용도 없다. 🔴 **버전 니블을 먼저 검사**한다(v7이 아닌 id에는 시각이 없고, 그래도 디코드하면 **난수에서 자신 있는 틀린 순간**이 나온다 → NULL이 정직한 답) |

#### 🔴 `refusals_unaccounted` — **부호가 계약이다**

`molecules_refused − sum(refusal_reasons[*].count)`. 클라이언트는 **수가 아니라 부호로 분기**한다.

| 부호 | 뜻 |
|---|---|
| `0` | 내역이 집계를 전부 설명한다. **보통의 답** |
| `> 0` | 컬럼이 생기기 «전»에(또는 `--reverse` 전에) 세어진 거절 — **그 이름은 이미 끝난 프로세스와 함께 사라졌다.** 🔴 **배포 이력이지 결함이 아니다** |
| `< 0` | 내역이 집계를 **초과**한다 = 진짜 장부 결함. **게이트에서 세면서 분자를 거절하지는 않는 경로**가 열렸다는 뜻 |

⚠️ **이 박스의 두 라이브 커서 행은 지금 «1»을 읽는다** — 컬럼이 생기기 전에 세어진 거절 하나(`undeclared_vocabulary`)다.
**화면은 그것을 이력으로 렌더해야 하고 「1건 거절, 사유 없음」으로 렌더하면 안 된다.**

🔴 **음수 갈래는 이론이 아니었다** — 2026-08-13에 실제로 `-1`이 측정됐다(§3.3-bis의 삼킴).
`f313279`가 닫았고 **그래도 갈래는 남긴다**: 그것이 탐지기이고, **부호가 음수인 이유는 삼킴 방향이 위험한 쪽이기 때문이다** —
「원자가 착지하는데 거절이 세어진 것」이 「거절이 안 세어진 것」보다 나쁘다. 다시 음수가 나오면 **같은 모양의 새 경로가 열린 것**이다.

**캐시 없음이 판정이다.** 이 프로젝트는 다른 곳에서 카운트를 5초 캐시하지만(`main.TABLE_COUNT_CACHE`),
이 엔드포인트는 **운영자가 «방금 돌린» 마이그레이션·백필이 먹혔는지**를 묻는 자리다 —
캐시는 답이 가장 중요한 순간에 5초간 `absent`/`empty`를 답한다. 폴링하는 소비자가 생기면 **그쪽에서** 캐시할 것.

**라이브 실측** (`assy_manager`, `:8080`, 2026-08-13 — `0198e7e` **이전** 판독이라 아래 새 필드는 안 보인다):
```
{"state":"ready","lots":25,"sources":["lot_event"],
 "occurred_at":{"from":"2026-05-03T02:17:00+09:00","to":"2026-05-21T20:33:00+09:00"},"sample":[…]}
```
**측정된 비용**(`assy_manager` 웜): 원자 추정 0.374 ms · 파티션 0.331 · 커서 행 0.146 · 마지막 원자 + uuid7 디코드 0.219,
호출 전체 **4.3–4.7 ms**. 별도 프로브 DB(280,000원자 / 100,000랏 / 12파티션, `VACUUM ANALYZE` 후) 전체 **31 ms**,
그중 `count(register)`가 24.06 ms — 🔴 **커지는 것은 그것 하나이고 원자가 아니라 «랏»을 따라간다.**

---

## 7. 명시적 비기능 (Non-features)

**① UPDATE 경로가 «구성상» 없다.** 정정도 철회도 새 원자(`supersedes`)다. `ledger_events`의 유일한 쓰기 문장은
`INSERT ... ON CONFLICT DO NOTHING`이고, 그것이 §3.2의 비대칭이 하중을 받는 이유다.
→ [설계 §3 · §14 「박제」](../architecture/CANONICAL_LEDGER_DESIGN.md)

**② status·processed 컬럼이 없다 — 🔴 가변 필드 0.** 소비자는 자기 커서를 든다(`ledger_translator_cursor`가 그것이다).
같은 이유로 **투영 상태어**(`resolved`·`contested`·`candidate`·`unresolvable`·`pinned`)는
`vocabulary.PROJECTION_ONLY_WORDS`가 **이름으로 거절**한다 — 캐시가 자기 상태를 말하는 낱말이지 원장의 낱말이 아니다.
「이 낱말은 캐시의 것이지 원장의 것이 아니다」는 **무언가가 강제해야만 존재하는 규칙**이다.
→ [설계 §3 「일부러 뺀 것」 · §4.2](../architecture/CANONICAL_LEDGER_DESIGN.md)

**③ 배치/트랜잭션 표지는 «비의미»다.** `molecule_ref`는 컬럼이 아니고 게이트가 쓰고 버린다.
🔴 **해석기가 그것을 읽으면 계약 위반**이며, 이 구현에서는 **새어 나갈 곳 자체가 없다.**
→ [설계 §3 · §14 「표식이 열쇠로」](../architecture/CANONICAL_LEDGER_DESIGN.md)

**④ 텔레메트리는 반입되지 않는다.** 원장은 주장의 기록이지 측정치 저장소가 아니다 — 트레이스는 제 저장소에,
원장엔 파생 주장만 `raw_ref`를 달고. → [설계 §5 규칙 5](../architecture/CANONICAL_LEDGER_DESIGN.md)

**⑤ 보존(retention)은 «미판정»이다** — [설계 §12-4](../architecture/CANONICAL_LEDGER_DESIGN.md), 운영 증가율 숫자 대기.
🔴 **⚠️ 정하기 전에 이것을 볼 것: 파티션 키는 `occurred_at`(세상 시각)이지 기록 시각이 아니다.**
늦게 도착한 오래된 주장은 **오래된 파티션으로 들어간다** — 「N개월 지난 파티션을 detach한다」를 순진하게 걸면
**어제 도착한 원자를 떼어낼 수 있다.** 보존을 `occurred_at`에 거는 것은 「기록한 지 오래된 것을 버린다」가 아니라
**「오래전 일에 대한 기록을 버린다」**이고, 둘은 같은 문장이 아니다.
---

## 8. ⚰️ 은퇴한 문법 — **기록으로만 남는다**

🔴 **사양은 시스템이 «하는 일»을 적고, 기록은 «했던 일»을 적는다.** 아래 문법에는 오늘
실행 경로가 없다. 그런데 그 문법으로 쓰인 원자는 원장에 **남아 있고 읽힌다** — 그래서
계약이 사라지면 그 원자를 설명할 것이 없어진다. 이 절은 그 원자들을 위한 자리이지,
**무엇을 만들지에 대한 지침이 아니다.**

⚠️ **여기 있는 것을 새 소스의 본보기로 삼지 말 것.** 오늘 「코드 0줄」의 자리는
범용 구현 둘이다 — Preparer `direct-join@1` · Mapper `declarative-role@1`
([ONTOLOGY_LEDGER_SETUP §7.3·§7.4](../guide/ONTOLOGY_LEDGER_SETUP.md)).

### 8.1 ⚰️ `declared` — **파이썬 클래스가 «없는» 문법** (2026-08-15 3차 · 브리핑 §6-2 · 갱신 트리거 ②③⑥) — 옛 §3.8


> ⚰️ **[2026-08-18/19 은퇴] 이 절 전체가 이제 «역사»다.** `server/ledger/declared_translator.py`는
> 트리에 **없고**(`e47d325`), 그것을 고르던 `kind` 디스패치와 `_run_declared`도
> `backfill.py`에서 빠졌다(`d7bfcd0`). 아래 ①~⑧의 계약을 **집행하는 실행 경로가 없다**
> — `rows_matching_nothing`도 `server/`에 없다. **선언만으로 코드 0줄 소스를 세우는 오늘의
> 자리는 이것이 아니라** 범용 구현 둘이다: Preparer `direct-join@1`, Mapper
> `declarative-role@1`([ONTOLOGY_LEDGER_SETUP §7.3·§7.4](../guide/ONTOLOGY_LEDGER_SETUP.md)).
> 남겨 둔 이유는 이 문법으로 적재된 옛 원자를 읽을 때 그 payload의 뜻이 여기 적혀 있기
> 때문이다 — **실행 지시로 읽지 않는다.**

**소스 문법이 넷이 됐다**(`SOURCE_KINDS` = `lineage`·`observation`·`transfer`·**`declared`**).
앞의 셋은 「선언 + 번역기 클래스」인데 이것은 **선언이 곧 번역기다** — 새 «모양»의 테이블에 코드가 **0줄**이다.
🔴 **번역기가 «모양»에 속하지 소스에 속하지 않는다는 것이 이 문법의 근거다**(`void_obs`와 `delam_obs`가 번역기 하나를 공유하는 것이 그 증거였다).
운영자용 키 표와 절차는 [ONTOLOGY_LEDGER_SETUP §3.4](../guide/ONTOLOGY_LEDGER_SETUP.md)가 소유하고, **여기는 조용히 깨지면 안 되는 계약만** 적는다.

**① 🔴 `occurred_at_basis`는 «필수»이고 기본값이 없다** (R-2026-08-15-N ②). `claim_time` \| `row_created`.
대장의 세계 시각은 **주장이 성립한 때**여야 하는데 대부분의 대장은 `created_at`만 든다 — **둘 다 합법이고 뜻이 다르므로** 선언이 말해야 한다.
🔴 **기본값을 두면 「언제 참이 됐나」가 조용히 「언제 적재됐나」가 된다.**
`row_created`면 그 사실이 **원자에 실린다**: `object_payload->>'occurred_at_basis'`.
⚠️ **`value` payload에만 실린다** — `entity_ref` payload는 모양(`type`/`keys`/`qualifiers`)이 엄격히 검사돼 **여분 키가 (옳게) 거절**되므로,
그런 원자는 그 사실을 **자기 안이 아니라 선언에** 둔다. **그 비대칭은 나중에 발견될 것이 아니라 여기 이름 붙는다.**

**② 🔴 `when`은 닫힌 집합에서 «정확히 하나»다**(`WHEN_OPERATORS` = `equals`·`not_equals`·`in`·`not_in`·`present`·`absent`).
**0개도 2개도 오타도 전부 로드 시점 거절**이다 — 🔴 **무시된 연산자는 조건을 «항상 참»으로 만들어 아무도 요청하지 않은 원자를 낳는다.**
(가장 비싼 실패 모양이 **거절**이 아니라 **조용한 초과 발화**인 자리라 검사가 관대할 수 없다.)

**③ 🔴 값 참조: `"$col"`은 그 행의 컬럼, 맨 문자열은 리터럴, `"$$"`는 «$» 자체.**
**없는 컬럼을 `$`로 부르면 «거절»이고 빈 값으로 풀지 않는다** — 그러면 「모양은 멀쩡한데 아무것도 안 가리키는 원자」가 나온다.

**④ 파생 이름은 규칙 이름이다** — §3.5 ③의 그 문단. **`rule` 중복은 로드 거절**이다.

**⑤ 🔴 저장 시점에 «선언끼리» 교차 검사한다.** `emit[].subject.type`이 그 소스의 `subject_types` 밖이면 로드 거절이다 —
게이트도 그 원자를 `undeclared_subject_type`으로 **거절하기는 하지만**, 그것은 **행마다 백필 시점에** 일어난다.
🔴 **저장 시점에 알 수 있는 오류를 실행 시점으로 미루지 않는 것**이 이 문법이 존재하는 이유의 절반이다(선언이 곧 프로그램이고, 이 검증이 그 유일한 컴파일러다).

**⑥ 읽기는 `SELECT *`이고 그것이 이 문법에서만 옳다.** 다른 문법은 파이썬 클래스가 이름 지은 필드를 읽지만
이 문법의 컬럼 집합은 **선언을 읽기 전에는 알 수 없다**(`"$leg"`가 운영자의 낱말이다). 선언에서 프로젝션을 조립하려면
중첩 payload에서 `$` 토큰을 파싱해야 하고 **틀리면 컬럼 하나가 빠진 행이 되어 (옳게) 거절**된다. **대장은 본래 작다**(`bonding_map` 1,181행).

**⑦ 규칙에 하나도 안 걸린 행은 «거절이 아니다».** 일부 행만 덮는 대장 선언은 정당하다 —
다만 그 수(`rows_matching_nothing`)가 「1,181행이 왜 원자 40개를 냈나」를 설명하므로 **드라이런이 그것을 보고한다.**

**⑧ ⚠️ 범위 밖: 리스트 열 분해·위치 짝짓기.** `lot_event` 한 행이 `slot_numbers`/`wafer_ids`를 위치로 짝지어
`derived_from` 1 + `has_wafer` 19를 내는 모양이 그 예다. 🔴 **경계는 「어려워서」가 아니라 「선언이 코드보다 읽기 쉬운 지점을 지나서」다** —
그걸 JSON으로 적으면 **디버거도 스택 트레이스도 없는 작은 프로그래밍 언어**가 된다. 그런 모양은 파이썬 번역기를 계속 쓴다.

⚠️ **드라이버는 관측 문법의 것을 «구조 그대로» 쓴다**(키셋 커서 · 한 행 = 한 분자 · 분자 스코프를 **드라이버가** 연다 — R-H-bis 3).
그리고 **소스 «이름»이 곧 관계명**이라(`FROM {source}`) 🔴 **이 문법이 「테이블 아닌 소스」의 문을 열지는 않는다**([LEDGER_GUIDE §3-bis](../guide/LEDGER_GUIDE.md)).


---

## 관련 문서

- **왜** — [architecture/CANONICAL_LEDGER_DESIGN.md](../architecture/CANONICAL_LEDGER_DESIGN.md) §3 어휘/봉투 · §4 어휘 분리 · §5 규칙 · §6 해결 서열 · §7·§7-bis 파생과 실측 · §12 판정 대기
- **어떻게** — [guide/LEDGER_GUIDE.md](../guide/LEDGER_GUIDE.md)
- **판정** — [process/LEDGER_RULINGS.md](../process/LEDGER_RULINGS.md) R-A · R-B · R-C 🔴 정본
- **라우트 계약** — [architecture/backend.md §2](../architecture/backend.md) (**이 문서는 복제하지 않는다**)
- **저장·시각 선언** — [architecture/data_model.md §1.1-ter](../architecture/data_model.md) · **화면** — [architecture/frontend.md §6.1](../architecture/frontend.md)
- **컬럼·키 정준 형식** — [architecture/SCHEMA_CANON.md](../architecture/SCHEMA_CANON.md)
- **운영 실행** — [process/OPERATOR_RUNBOOK.md §6 · §8](../process/OPERATOR_RUNBOOK.md)
- **Trend 종류 선언** — [TREND_DECLARATION_GUIDE](./TREND_DECLARATION_GUIDE.md)
