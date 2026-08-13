# 정준 원장 기술 명세 (Canonical Ledger — Technical Specification)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-13 (원장/성능 라운드 `4f46c25..f313279`) | **Owner:** Server / Ledger
> **Source-of-truth:** `server/ledger/schema.py`(DDL) · `server/ledger/store.py`(쓰기) · `server/ledger_trace.py`(해결·보행)
>
> **이번 라운드 (2026-08-13 5차)** — §1.5 커서가 **열둘 → 열셋**(`refusal_reasons`)이고 **§1.5-bis 신설** ·
> **§3.3-bis 신설**: 「원자 하나가 나쁘면 분자 전체」가 **어느 파편에서든**으로 승격됐다(`f313279` · R-H) ·
> **§3.5-bis 신설**: `subject_types` 복수 allow-list가 **문다**(`eb1ae8b` · R-D) ·
> **§6.4-bis 신설**: `/coverage` 응답 확장과 `refusals_unaccounted`의 **부호 계약**(`0198e7e` · R-F).

> **문서 셋의 분업**
> | 문서 | 소유 |
> |---|---|
> | [architecture/CANONICAL_LEDGER_DESIGN](../architecture/CANONICAL_LEDGER_DESIGN.md) | **WHY** — 왜 이 모양인가 |
> | [guide/LEDGER_GUIDE](../guide/LEDGER_GUIDE.md) | **HOW** — 소스 붙이는 절차 · 백필 운영 |
> | **이 문서** | **EXACTLY-WHAT** — 변경이 **조용히 깨뜨리면 안 되는 계약** |
> | [process/LEDGER_RULINGS](../process/LEDGER_RULINGS.md) | **판정** 🔴 정본. 거기 없는 판정은 내려진 적이 없는 것 |
>
> 🔴 **라우트 계약의 서술 정본은 [architecture/backend §2](../architecture/backend.md)이고 이 문서는 그것을 «가리킨다».**
> 여기 §4는 **응답의 의미론**(무엇이 어떤 뜻인가)을 적지 라우트 표를 복제하지 않는다.
>
> ⚠️ **모든 수치는 합성·이 개발 박스 실측이고 운영의 증거가 아니다.** 항목마다 출처 라벨을 달았다.

---

## 1. 물리 스키마 계약

### 1.1 `ledger_events` — 열한 컬럼

봉투 7필드를 평탄화한 것이다. 평탄화는 `envelope.ROW_COLUMNS` **한 자리**에서만 일어난다
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

🔴 **provenance 셋은 NOT NULL이다.** 누가·어떤 번역기로·어느 원시 행에서 주장했는지 말 못 하는 원자는 증거가 아니다.
(테스트가 이 셋을 nullable로 손복사해 두고 **아무도 안 가진 테이블을 시험하고 있던** 적이 있다.)

**봉투에 있는데 컬럼이 «없는» 것 둘:**

| 없는 것 | 어디 있나 |
|---|---|
| `recorded_at` | **uuid7 `id` 안의 48비트 밀리초.** 컬럼을 되살리면 한 질문에 답이 둘이 된다. 읽는 법은 `uuid7.timestamp_ms()` |
| `molecule_ref`(상관 표지) | **메모리에만.** 게이트가 전부-아니면-전무를 정하는 데만 쓰고 버린다. 🔴 컬럼이 아니므로 **새어 나갈 곳이 없다** |
| `derivation` | 컬럼이 아니라 **`source_translator_ver`의 `#` 접미**. §3.5 |

### 1.2 CHECK 제약 — 각각이 «산문으로만 살 뻔한 규칙»이다

| 제약 | 강제하는 규칙 |
|---|---|
| `ck_ledger_object_kind` | `object_kind IS NULL OR object_kind IN ('value','entity_ref','event_ref')` — 슬라이스 1에 pin된 enum |
| `ck_ledger_register_has_no_object` | **`(predicate = 'register') = (object_kind IS NULL)`** — 🔴 **쌍조건(biconditional)이고 «양방향»이다.** 설계는 `register`의 object를 ∅라 하고 pin된 enum에는 ∅ 철자가 없다. 네 번째 값을 발명하지 않고 `object_kind IS NULL`을 **`register`에만** 합법으로 만든 것 — object를 든 register와 object 없는 비-register가 **똑같이** 거절된다 |
| `ck_ledger_objectless_has_no_payload` | `object_kind IS NOT NULL OR object_payload IS NULL` |
| `ck_ledger_subject_keys_is_object` | `jsonb_typeof(subject_keys) = 'object'` — 이어붙인 키가 빈 조각에서 무너져 **운영 17만 행**이 된 사고를 **저장 계층에서**(모든 파이썬 검사 아래에서) 막는다 |
| `ck_ledger_no_self_supersede` | `supersedes IS NULL OR supersedes <> id` — 자기를 대체하는 정정은 해결기가 영원히 따라가는 순환 |

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
| `gate.building_molecule(source)` — **스코프** | 규칙이 **읽는 자리**가 아니라 **발화하는 자리**로 옮겨갔다. 그 안에서는 **사유를 가리지 않고 모든** `refuse`가 세고 나서 raise한다 — 내년에 추가되는 헬퍼는 **이 규칙이 있는 줄 몰라도** 자기 분자를 세운다 |
| 세고 «나서» raise | 거절은 **누가 예외를 잡든 말든 사실**이다. 순서를 뒤집으면 못 잡힌 예외가 카운터를 지운다 |
| `molecule_is_open()` 단언 | 스코프 **밖**에서는 모든 `refuse`가 **세기만 하고** 실행이 「멈췄어야 할 검사」를 지나 계속 간다 — **같은 삼킴이 한 층 위에서** 재현된다. 그래서 원자를 만드는 본문은 전제를 **가정하지 않고 검사**한다 |
| **일방향 문은 `translate` 하나** | `lot_event_translator.translate`가 `try/except MoleculeRefused`로 예외를 **다시 값으로** 바꾸는 유일한 자리다. `_build`에는 그것을 삼킬 수 있는 표현식이 존재하지 않는다 |

🔴 **거절된 분자는 자기 «부작용»도 되돌려야 한다.** `register` 원자는 실행 스코프 메모(`registered`)에
**거절 가능한 검사들보다 먼저** 들어간다. 삼킴이 살아 있던 동안은 register가 어차피 쓰였으므로 메모가 참이었다 —
**아무것도 안 쓰이게 되는 순간** 그 랏은 「아무것도 안 쓴 분자」에 의해 등록된 것으로 표시되고
**이후 어떤 분자도 그것을 등록하지 않는다.** 수리는 **분자별 목록**이지 `registered`의 스냅숏이 아니다
(수명 메모를 분자마다 복사하면 천만 행 백필이 **2차식**이 된다).

⚠️ **의도적으로 남긴 모양 셋** — 오늘 아무것도 안 깨뜨리지만 다음 사람이 만날 자리다:
① `screen_molecule`은 거절 시 여전히 `[]`를 돌려준다(오늘은 반쪽 착지가 불가능하지만
`atoms.extend(screen_molecule(...)[0])`을 쓰는 호출부는 **아무것도 안 쓰고 아무것도 안 센다**)
② `write_batch(reasons=None)`은 0 아닌 집계 옆에 빈 내역을 써서 **양(+)의 부호**로 나타난다 —
**배포 이력의 옷을 입은 결함**이다 ③ 두 번째 번역기는 **스코프를 열어야만** 이 원칙을 물려받는다
(발견 가능하지만 구조적이지는 않다).

**반쪽 착지 없음의 증명 방법** — 명세로 남길 것은 결과가 아니라 **방법**이다:
페이지 안에서 **첫 청크가 이미 INSERT된 뒤** 두 번째 문장이 raise하도록 만들고, **원자 0개가 살아남는지**를 본다.
🔴 그리고 **경계를 걷어냈을 때 원자가 남는지도** 본다 — 그것이 그 테스트가 **빨개질 수 있음**의 증명이다.

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

---

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

### 5.6 재백필 경제
커서 리셋 재실행: **633 시도 / 0 삽입 / 633 dedupe**(`f896020` 당시 `assy_qa`).
시간대 정정 재백필: **878 → 878, `inserted=878 deduped=0`**(`bee1aeb`, `assy_qa`) —
`occurred_at`과 `source_translator_ver`가 **둘 다** dedupe 열쇠에 있고 **둘 다 바뀌었기** 때문이다.
🔴 **두 결과의 차이가 이 인덱스의 의미론 전부다**: 같은 규칙의 재실행은 **전부 걸리고**, 다른 규칙의 재번역은 **전부 통과한다.**

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

## 관련 문서

- **왜** — [architecture/CANONICAL_LEDGER_DESIGN.md](../architecture/CANONICAL_LEDGER_DESIGN.md) §3 어휘/봉투 · §4 어휘 분리 · §5 규칙 · §6 해결 서열 · §7·§7-bis 파생과 실측 · §12 판정 대기
- **어떻게** — [guide/LEDGER_GUIDE.md](../guide/LEDGER_GUIDE.md)
- **판정** — [process/LEDGER_RULINGS.md](../process/LEDGER_RULINGS.md) R-A · R-B · R-C 🔴 정본
- **라우트 계약** — [architecture/backend.md §2](../architecture/backend.md) (**이 문서는 복제하지 않는다**)
- **저장·시각 선언** — [architecture/data_model.md §1.1-ter](../architecture/data_model.md) · **화면** — [architecture/frontend.md §6.1](../architecture/frontend.md)
- **컬럼·키 정준 형식** — [architecture/SCHEMA_CANON.md](../architecture/SCHEMA_CANON.md)
- **운영 실행** — [process/OPERATOR_RUNBOOK.md §6 · §8](../process/OPERATOR_RUNBOOK.md)
