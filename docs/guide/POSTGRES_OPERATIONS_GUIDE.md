# 🐘 PostgreSQL & pgAdmin4 운영 관리 가이드 (AssyManager)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-13 2차 (**§3.1 「읽기 전용 가드」 재작성** — `1260c9b`. 🔴 **집이 `server/db_safety.py` 하나가 됐고 일곱 스크립트가 전부 그것을 부른다**(「옛 철자 셋」은 없다). **철자 둘은 중복이 아니라 서로 다른 문제의 답**이라 승자 없이 **모드**로 노출한다 — `CONNECT_TIME`(우리가 만든 엔진, 격리 수준과 무관) / `PER_TRANSACTION`(**남에게서 받은 엔진**, 감사 스크립트가 이것을 필요로 한다). ⚠️ **직전 라운드의 「이 셋은 무장 안 됐다」가 절반 틀렸다** — AUTOCOMMIT이 `SET` 앞에 있던 둘은 **실제로 무장돼 있었고**, 그 판정은 코드가 한 번도 돌린 적 없는 모양을 잰 것이다. 고친 이유는 **밖에서 「우연히 맞음」과 「거짓」이 구별되지 않기** 때문. ⚠️ **미해결**: `diagnose_db_health.py`의 `SET TRANSACTION READ ONLY`(첫 트랜잭션만 — 실측 롤백 뒤 CREATE 통과)와 그 docstring의 같은 거짓 주장. 직전 1차: §3.1에 **읽기 전용 가드** 항목 신설 — 🔴 이 문서가 `check_missing_business_key.py`에 대해 「구조적으로 못 쓴다」고 적고 있던 것이 **거짓이었다** — `SET SESSION default_transaction_read_only`는 PostgreSQL이 강제하는 변수가 아니다. 직전 2026-08-11: §3.1에 **접두 중복·미사용 인덱스 회수** 항목 신설 + `--drop-redundant`가 드라이런이 아니라는 경고 추가 — 준비만 됐고 **아직 아무 DB에도 적용하지 않았다**. 직전 2026-08-08: §3.1에 **업무 키가 안 조립된 행의 읽기 전용 사전점검** 항목 신설 — `b2ceb55`. ⚠️ **이 배지는 낡아 있었습니다**: `cc602ed`가 D3 두 절(`uq_bk_<table>` · `--drop-redundant`)을 이미 넣었는데 날짜가 2026-07-31에 멈춰 있었습니다 — **본문이 앞서고 배지가 뒤처지면 독자는 본문을 안 읽습니다.** 직전 2026-07-31: §3.1에 R2 회수 범위 인덱스 `idx_sources_by_source` — `1948338`) | **Owner:** Ops
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

본 문서는 AssyManager의 백엔드 데이터베이스인 PostgreSQL을 운영하고 pgAdmin4를 통해 데이터를 직접 관리하는 방법을 안내합니다.

---

## 1. 🛠️ pgAdmin4 서버 연결 설정

AssyManager 서버에 접속하기 위해 pgAdmin4에서 아래와 같이 서버를 등록하십시오.

- **Name**: `AssyManager_Production` (자유롭게 설정)
- **Connection Tab**:
    - **Host**: `127.0.0.1` (또는 DB 서버 IP)
    - **Port**: `5432`
    - **Maintenance database**: `assy_manager`
    - **Username**: `postgres`
    - **Password**: `admin` (또는 설정하신 비밀번호)

---

## 🔍 2. Raw 데이터 조회 및 SQL 가이드

PostgreSQL은 `data` 컬럼에 **JSONB** 형식을 사용합니다. 아래 연산자를 활용하여 데이터를 조회하십시오.

### 2.1 기본 조회 및 필터링
```sql
-- 특정 테이블의 모든 데이터 조회
SELECT * FROM data_rows 
WHERE table_name = 'raw_table_1' 
ORDER BY business_key_val ASC;

-- 특정 Row ID의 데이터 조회
SELECT * FROM data_rows WHERE row_id = 'your-uuid-here';
```

### 2.2 JSONB 데이터 세부 조회 (핵심)
PostgreSQL의 JSONB 전용 연산자를 사용하여 셀 데이터를 직접 조회할 수 있습니다.
- `->`: JSON 객체/배열 반환
- `->>` : 문자열(Text)로 결과 반환

```sql
-- 특정 컬럼('LOT_ID')의 현재 표시 값 조회
SELECT 
    row_id,
    data->'LOT_ID'->>'value' as lot_id_value,
    data->'LOT_ID'->>'updated_by' as last_editor
FROM data_rows 
WHERE table_name = 'raw_table_1';

-- 특정 소스('parser_a')에서 유입된 값만 필터링
SELECT * FROM data_rows 
WHERE data->'STATUS'->'sources'->'parser_a' IS NOT NULL;
```

### 2.3 감사 로그(Audit Log) 추적
```sql
-- 특정 행의 최근 변경 이력 5건 조회
SELECT * FROM audit_logs 
WHERE row_id = 'your-uuid' 
ORDER BY timestamp DESC 
LIMIT 5;

-- 특정 사용자가 수정한 내역 조회
SELECT * FROM audit_logs WHERE updated_by = 'user_id';
```

---

## ⚡ 3. 성능 및 유지보수

### 3.1 인덱스 상태 확인
AssyManager에는 GIN Index와 복합 색인이 설정되어 있습니다.
```sql
-- 테이블에 설정된 모든 인덱스 보기
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'data_rows';
```

> ⚠️ **`create_all`은 이미 존재하는 테이블에 인덱스를 추가하지 않는다.** 새 인덱스를 `models.py`에만 선언하고 아래 스크립트를 돌리지 않으면, 신규 설치에서만 빠르고 **기존 운영 DB에서는 조용히 Seq Scan으로 떨어진다.** 운영 DB에 인덱스를 반영하는 경로는 **둘**이다(둘 다 `CONCURRENTLY` · 멱등 · 무중단):
> - `python server/scripts/setup_db_performance.py` — 성능 인덱스 일체
> - `python server/migrations/add_business_key_unique_index.py --apply` — 업무 키 UNIQUE 인덱스(§3.1-bis)

#### 읽기 전용 가드 — 집은 하나이고, 모드가 둘입니다 (2026-08-13 `1260c9b` · 종전 `b1dd2f0`)

아래 스크립트들의 **사전점검**(플래그 없는 호출)은 아무것도 쓰지 않습니다. **그리고 이제 그것은 의도가 아니라 «PostgreSQL이 되읽어 준» 성질입니다** — 일곱 개 전부가 같은 집을 씁니다.

🔴 **집은 `server/db_safety.py` 하나입니다.** `open_readonly_engine` / `open_readonly_connection` / `readonly_state` / `assert_readonly` / `assert_writable` / `close_readonly_connection`. **스크립트 안에서 이 성질의 철자를 다시 만들지 마십시오** — 이 정리가 벌어진 이유가 「사본은 원본이 틀린 것을 그대로 나른다」이고, 실제로 스크립트 셋이 **각자 발명한 것이 아니라 문서가 옳다고 가르친 철자를 복사**했습니다.

| 모드 | 어떻게 | 누가 쓰나 |
|---|---|---|
| **`CONNECT_TIME`** | `-c default_transaction_read_only=on`을 **연결 옵션**으로, `NullPool` 엔진에. 서버가 이 세션의 첫 트랜잭션이 생기기 **전에** 적용하고 이후 모든 트랜잭션에 다시 적용합니다 — **격리 수준과 무관**해서 가장 강합니다. 대신 **엔진을 우리가 만들어야** 합니다 | 스크립트 여섯 — `migrations/add_business_key_unique_index.py` · `migrations/drop_redundant_layering_indexes.py` · `scripts/dedupe_business_key_rows.py` · `scripts/rebuild_blank_business_keys.py` · `scripts/check_missing_business_key.py` · `scripts/dev_env/snapshot_db.py` |
| **`PER_TRANSACTION`** | `postgresql_readonly=True`(SQLAlchemy 자체 옵션)로 트랜잭션마다 플래그를 세웁니다. **남에게서 받은 엔진**에도 걸립니다(두 번째 엔진도 두 번째 풀도 안 만듭니다) | `scripts/audit_schema_canon.py` — 진입점이 **호출자에게서 엔진을 받으므로** 이쪽이 아니면 안 됩니다 |

🔴 **모드를 잘못 고르는 것은 구멍이 아니라 «거절»입니다.** 안 맞는 모드는 무장 안 된 연결을 낳고 `assert_readonly`가 그것을 거절합니다 — **평결은 어느 갈래가 돌았는지가 아니라 서버가 `SHOW transaction_read_only`로 답한 값에서 나옵니다.** 답하지 못하는 연결도 거절입니다. 쓰기용 짝(`assert_writable`)은 `--apply` 갈래 **안에서만** 열리므로 점검만 하는 실행은 쓰기 가능한 연결을 프로세스 어디에도 만들지 않습니다.

🔴 **왜 옛 철자로는 부족한가**: `default_transaction_read_only`와 `transaction_read_only`는 **다른 변수**이고, PostgreSQL이 실제로 강제하는 것은 뒤엣것입니다. 평범한 격리 수준에서 `SET SESSION default_transaction_read_only = on`은 **그 문장 자신이 시작한 암묵 트랜잭션 안**에 앉으므로 그 트랜잭션은 옛 기본값을 그대로 듭니다 — 실측 `transaction_read_only = off`, **CREATE / INSERT / UPDATE 셋 다 수락**, 그러는 내내 `default_transaction_read_only`는 `on`이라고 답합니다. 「세웠으니 됐다」가 아니라 **강제되는 쪽을 되읽어야** 답이 나옵니다.

⚠️ **정정 — 직전 라운드가 「이 셋은 무장 안 됐다」고 적은 것은 절반이 틀렸습니다.** `drop_redundant_layering_indexes.py`와 `rebuild_blank_business_keys.py`는 `SET` **앞에서** 연결을 `execution_options(isolation_level="AUTOCOMMIT")`으로 바꾸고 있었고, **그 순서에서는 실제로 무장됐습니다**(실측: 롤백 전후 모두 쓰기 거절). **아무것도 잘못 쓰인 적이 없습니다.** 종전 판정은 **코드가 한 번도 돌린 적 없는 모양**(평범한 격리 수준)을 잰 것입니다. 🔴 **그래도 고친 이유**: 그 AUTOCOMMIT은 `CREATE INDEX CONCURRENTLY`가 트랜잭션 블록에서 못 돌기 때문에 있었지 안전성과 무관했고 — **무관한 이유로 지우는 순간 가드가 조용히 풀립니다** — 되읽기가 없으면 「우연히 맞음」과 「거짓」이 **스크립트 안에서 완전히 같아 보입니다.** `check_missing_business_key.py`는 AUTOCOMMIT이 없어 **정말로 꺼져 있었지만**, 그 파일엔 쓰기 문장이 하나도 없습니다 — **결함은 사건이 아니라 주장이었습니다.**

⚠️ **저장소 전체는 아직 아닙니다.** `scripts/diagnose_db_health.py`는 `SET TRANSACTION READ ONLY`를 씁니다 — **첫 트랜잭션만** 덮으므로 실측에서 롤백 뒤 `off`이고 **CREATE가 통과**했는데, docstring은 여전히 「세션이 고정된다」고 말합니다. **운영자가 실 DB에 겨눌 수 있는 진단 도구**입니다. `diagnose_slow_after_ingest.py`·`diagnose_wal_headroom.py`는 기전은 맞지만 **되읽지 않고** 이 집을 공유하지 않습니다.

채점: `server/tests/test_readonly_guard.py`(실서버 대상 — 문 일곱을 각 스크립트가 여는 방식 그대로 열어 플래그 되읽기 + CREATE/INSERT/UPDATE 거절 + **명시적 롤백 뒤에도 거절** + 같은 엔진의 두 번째 연결도 거절, 그리고 **쓰기 가능 엔진에서 같은 세 문장이 성공하고 UPDATE 값이 되읽히는 대조군**. 대조군이 없으면 「가드가 막았다」와 「쓰기 자체가 깨졌다」를 구별할 수 없습니다). 🔴 **주입은 단계별입니다** — 되읽기만 제거하면 **14개가 통과**(연결 옵션이 여전히 무장), 연결 핀만 제거하면 문 7 중 6 빨강, 둘 다 제거하되 한쪽 팔만 고장 내면 23 실패인데 **감사 스크립트는 초록**(다른 갈래이기 때문). 재사용 관점은 [PRIMITIVES §6](../architecture/PRIMITIVES.md).

#### 업무 키 UNIQUE 인덱스 (`uq_bk_<table>`) — 2026-08-07 D3

`business_key_val`의 유일성을 **데이터베이스가 강제**하게 한다(배경·의미는 [data_model §3.1](../architecture/data_model.md)). 없으면 프로세스 둘이 같은 키를 동시에 쓸 때 **한 업무 키에 두 행이 조용히** 생긴다(재현된 창 2.4초).

🔴 **먼저 읽기 전용 사전점검부터 돌린다. 운영에 중복이 하나라도 있으면 `CREATE UNIQUE INDEX`는 실패한다.**

```bash
# ① 사전점검 — 아무것도 쓰지 않는다(연결이 읽기 전용임을 «되읽어 증명»한다 — 아래 「읽기 전용 가드」)
conda run -n assy_manager python server/migrations/add_business_key_unique_index.py

# ② 반영
conda run -n assy_manager python server/migrations/add_business_key_unique_index.py --apply
```

- **테이블마다 먼저 세고 나서 만든다.** 중복이 있는 테이블은 **이름·중복 키 수·잉여 행 수·문제 키 예시**와 함께 거부되고 **나머지 테이블은 계속 진행한다** — 전체 중단도, 조용한 건너뛰기도 아니다. 거부된 테이블은 중복을 정리한 뒤 재실행한다(재실행은 무해하다 — 이미 만들어진 것은 `already_enforced`로 지나간다).
- **업무 키가 NULL인 행은 여러 개여도 된다**(빈 행 추가 기능이 그런 행을 만든다). 막히지 않는 것이 정상이다.
- ⚠️ **취소된 CONCURRENTLY 빌드의 INVALID 잔해가 이름을 잡고 있으면 `IF NOT EXISTS`가 영원히 건너뛴다.** 이 스크립트는 그 상태를 `refused_invalid_index`로 **따로 이름 붙여** 보고하고 `DROP INDEX CONCURRENTLY <이름>;`을 제시한다. 아무것도 스스로 드롭하지 않는다.

#### 업무 키가 **안 조립된** 행 — 읽기 전용 사전점검 (2026-08-07 `b2ceb55`)

위 유니크 인덱스가 막는 것은 **키가 겹치는** 행이고, 이것은 **키가 아예 없는** 행이다. 대량 인제션에서 원본 `composite_key_source` 컬럼은 다 찼는데 `business_key_val`만 빈 행이 보고됐다(제품 소유자 2026-08-07).

```bash
conda run -n assy_manager python server/scripts/check_missing_business_key.py
conda run -n assy_manager python server/scripts/check_missing_business_key.py --table dt_log
```

- **아무것도 쓰지 않는다 — 그리고 이제 그것이 «증명»된다**(2026-08-13 `1260c9b`). 종전 이 자리에는 *「세션이 `default_transaction_read_only = on`으로 고정돼 **구조적으로** 못 쓴다」*라고 적혀 있었고 **그 보증은 성립하지 않았다**(그 변수는 PostgreSQL이 강제하는 변수가 아니다 — 위 「읽기 전용 가드」). 🔴 **이 스크립트의 가드는 실측에서 정말로 꺼져 있었다**(`transaction_read_only=off`, 쓰기 셋 다 수락). **그래도 아무것도 쓰인 적은 없다 — 이 파일에는 쓰기 문장이 하나도 없기 때문이다.** 지금은 `db_safety`의 `CONNECT_TIME` 문을 쓰고 **되읽기로 거절**한다. 채우는 일은 **별개 라운드**다.
- 답하는 것은 셋이다: **① 몇 행인가**(규모) **② 재료가 있는가**(키 컬럼이 비어 있으면 어떤 스크립트도 못 만든다 — 사람이 값을 넣어야 한다) **③ 채우면 기존 행과 충돌하는가**(같은 재료를 가진 행이 이미 키를 갖고 있으면 그 둘은 중복이다).
- ⚠️ **③이 잡히면 유니크 인덱스는 그것을 거절하고, 인덱스가 없으면 조용히 둘이 된다. 어느 행이 사는지는 사람이 정한다** — `audit_logs`·`cell_sources` 귀속이 그 선택을 따라간다.
- 🔴 **이 스크립트는 키를 조합하지 않는다.** 조합의 정본은 `crud.assemble_composite_business_key`이고, 여기서 문자열을 이어 붙이면 그것이 **두 번째 철자**가 되어 조합 규칙이 바뀌는 날 이 스크립트만 옛 규칙으로 남는다. 그래서 「재료가 있는가」와 「같은 재료가 이미 키를 갖는가」만 센다 — **그 둘은 조합 규칙과 무관하게 참**이다.

#### PK를 그대로 복제한 인덱스 정리 (`--drop-redundant`) — 2026-08-07 D3

`Column(..., primary_key=True, index=True)`가 만들던 **PK 인덱스의 사본**을 회수한다. 이 워크스테이션 실측 **29개·382.3MB**(최대 `ix_cell_sources_id` 314MB). 읽는 곳이 없고 쓰기마다 유지된다.

```bash
conda run -n assy_manager python server/migrations/add_business_key_unique_index.py                    # 목록만
conda run -n assy_manager python server/migrations/add_business_key_unique_index.py --drop-redundant   # 회수
```

- 대상은 **하드코딩 목록이 아니라 매번 `pg_index`로 다시 증명**한다 — 키 컬럼·opclass·collation·access method가 PK 인덱스와 **모두** 같고, 부분/표현식/INVALID가 아닌 것만. 여기에 더해 이름이 SQLAlchemy 자동 생성형(`ix_*`)이어야 하며, **사람이 이름 붙인 인덱스는 구조가 같아도 보고만 하고 드롭하지 않는다.**
- 두 절은 서로 독립이다 — 한쪽만 실행해도 된다.
- 🔴 **`--drop-redundant`는 드라이런이 아니라 실제로 드롭한다.** 읽기 전용 사전점검은 **플래그 없는** 호출이다(위 첫 줄). 이름이 「redundant를 드롭한다」이므로 `--apply`가 따로 필요할 것처럼 읽히지만 아니다.

#### 접두 중복·미사용 인덱스 회수 (`drop_redundant_layering_indexes.py`) — 2026-08-11

위 `--drop-redundant`의 **자매 스크립트**이고 대상 계급이 다르다. 저쪽은 「PK 인덱스의 사본」만, 이쪽은 `cell_sources`/`cell_overwrites`/`audit_logs`의 **① 넓은 인덱스의 진짜 왼쪽 접두사** ② **읽는 곳이 없는 인덱스**다.

```bash
conda run -n assy_manager python server/migrations/drop_redundant_layering_indexes.py           # 사전점검(읽기 전용 — 되읽어 증명, 위 「읽기 전용 가드」)
conda run -n assy_manager python server/migrations/drop_redundant_layering_indexes.py --apply   # 회수
```

- 🔴 **접두 관계는 「같은 컬럼을 갖는다」가 아니라 「같은 순서로 갖는다」이다.** `(a,b,c)`는 `(a,b,c,d)`가 대신 서 주지만 `(b,a,c,d)`는 절대 아니다. 그래서 `pg_index`의 **indkey·indclass·indcollation·indoption(정렬 방향)** 네 축을 전부 대조한다 — `indoption`을 빼면 `(a, b DESC)`를 `(a, b)`의 중복으로 잘못 드롭한다.
- 🔴 **[2026-08-13 `1260c9b`] 연결이 하나가 아니라 «둘»이다.** 종전에는 **같은 연결**이 인덱스를 찾고 드롭했고, 두 모드를 가르는 것이 플래그 하나뿐이었다. 지금은 세는 패스가 **양쪽 모드 모두에서** PostgreSQL이 쓰기를 거절하는 연결 위에서 돌고, `--apply`가 **별개의 두 번째** 연결을 연다 — 점검 실행은 프로세스 어디에도 쓰기 가능한 연결이 없고, `--apply`도 **판정을 내린 그 연결로는** 실수로라도 DDL을 낼 수 없다(`add_business_key_unique_index.run`과 같은 모양).
- 🔴 **구조적 중복성은 플래너 행동을 예측하지 못한다.** 2026-08-11 실측: `idx_overwrites_lookup`은 UNIQUE `idx_overwrites_lookup_col`의 **진짜 접두사인데도**, 숨기자 플래너는 넓은 쪽이 아니라 `ix_cell_overwrites_row_id`를 골랐고 **1.81배 느려졌다**(45→113 버퍼). 그래서 이 스크립트는 **접두사라는 이유만으로 드롭하지 않는다** — 사람이 판정한 목록만 드롭하고, **드롭하지 않는 접두 중복 인덱스도 전부 이름으로 출력**한다(숨지 못하게).
- **「읽는 곳이 없다」는 카탈로그가 답할 수 없다** — 코드 전수 조사가 근거이고 `idx_scan`은 **거절 게이트**로만 쓴다. 게다가 갓 복원한 DB에서는 PK를 포함해 **모든** 카운터가 0이므로, 같은 테이블의 다른 인덱스 스캔 합이 0이면 **증거 없음으로 판정하고 거절**한다.
- 되돌리는 `CREATE INDEX CONCURRENTLY` 문을 **드롭하기 전에** 출력한다.

#### 재교정률 인덱스 (`idx_audit_user_recorrection`)
어드민 Overview의 재교정률([data_model §2.3](../architecture/data_model.md))이 쓰는 부분 커버링 인덱스. **없으면 `/dashboard/summary`가 `audit_logs` 전량을 훑는다**(2026-07-27 실측: 2,628,453행/1.6GB에서 512ms).

```sql
-- 존재 확인
SELECT indexname FROM pg_indexes
WHERE tablename = 'audit_logs' AND indexname = 'idx_audit_user_recorrection';
```
없으면 `setup_db_performance.py`를 실행한다. 인덱스가 없어도 대시보드가 느려지지는 않는다(1500ms `statement_timeout` + 60초 캐시로 방어) — 대신 그 칸이 `—`로 비고 사유가 표시된다. 즉 **`—`가 계속 보이면 이 인덱스를 의심할 것.**

#### 상호작용 점수 인덱스 (`uq_effort_transaction` · `idx_effort_window`)
**정본 계기**(완료까지의 상호작용 점수, [data_model §2.4](../architecture/data_model.md))가 쓰는 인덱스 2종. `interaction_effort_logs`는 신규 테이블이므로 **신규 설치에서는 `create_all`이 테이블과 인덱스를 함께 만든다** — 이 절이 필요한 경우는 **테이블만 먼저 생긴 DB**(구버전 기동 이력이 있는 운영 DB)다. 그 경우 `create_all`은 인덱스를 추가하지 않으므로 위 경고가 그대로 적용된다.

```sql
-- 존재 확인 (2건 모두 나와야 정상)
SELECT indexname FROM pg_indexes
WHERE tablename = 'interaction_effort_logs';
```

| 인덱스 | 없으면 생기는 일 |
|---|---|
| `uq_effort_transaction` (UNIQUE) | **tx당 1행 불변식이 깨진다.** 클라 재시도가 같은 공수를 두 번 기록해 그 세션의 평균이 조용히 왜곡된다 — 숫자가 틀렸다는 신호가 어디에도 뜨지 않으므로 가장 위험하다 |
| `idx_effort_window` (커버링) | 창 집계가 Seq Scan으로 떨어진다. 대시보드는 느려지지 않고(1500ms timeout + 60초 캐시) 그 칸이 `—`로 빈다 |

없으면 `setup_db_performance.py`(Step 3.7)를 실행한다. `uq_effort_transaction` **생성이 실패하면 이미 중복 `transaction_id` 행이 있다는 뜻**이므로, 스크립트 출력의 `Failed to create uq_effort_transaction`을 그냥 넘기지 말 것 — 중복을 먼저 정리해야 한다.

```sql
-- 중복 확인 (정상이면 0행)
SELECT transaction_id, count(*) FROM interaction_effort_logs
GROUP BY transaction_id HAVING count(*) > 1;
```

#### R2 회수 범위 인덱스 (`idx_sources_by_source`) — 2026-07-31 `1948338`

「이 소스가 이 테이블에서 주장하는 셀은 무엇인가」를 좁히는 **유일한** 인덱스. R2 회수(`chain_replay.count_withdrawable`/`withdraw_source`)와 그 카운트를 **요청 경로에서** 내놓는 `GET /admin/retroactive/withdraw/count`([BACKFILL_GUIDE §7](./BACKFILL_GUIDE.md))가 소비자다.

```sql
-- 존재 + 유효성 확인
SELECT ci.relname AS indexname,
       i.indisvalid AND i.indisready AS usable,
       pg_size_pretty(pg_relation_size(ci.oid)) AS size
FROM pg_index i
JOIN pg_class ci ON ci.oid = i.indexrelid
WHERE ci.relname = 'idx_sources_by_source';
```

- 🔴 **기존 `idx_sources_lookup_source`가 이 일을 대신하지 못한다.** 그쪽 키 순서는 `(table_name, row_id, column_name, source_name)`이라 **`source_name`이 마지막**이고, `(table_name, source_name)` 술어로는 쓸 수 없다. 없으면 플래너는 `cell_sources` **전량 스캔**으로 떨어진다 — 실측 근거(행 수·소요·버퍼·버려진 행 수)는 `server/database/models.py`의 이 인덱스 주석과 `server/scripts/setup_db_performance.py` Step 3.10에 **기록돼 있으니 그쪽을 읽을 것**(여기 사본을 두지 않는다).
- **키 순서가 계약이다** — `column_name`이 **세 번째**라야 `--columns` 허용목록이 인덱스 내부 Filter가 아니라 **`Index Cond`의 일부**가 되고, `row_id`가 **네 번째**라야 회수 1단계(`(row_id, column_name)` 조회)가 **커버링**이 된다. 커버링이 아니면 플래너가 매치당 heap fetch와 Seq Scan을 저울질하다 **다시 Seq Scan을 고를 수 있다.**
- **두 곳에 선언돼 있고 둘 다 고쳐야 한다** — `models.py`(신규 설치의 `create_all`)와 `setup_db_performance.py` Step 3.10(**기존 DB의 유일한 경로**). 위 ⚠️ 경고가 그대로 적용된다.
- **스크립트는 만든 뒤 플래너가 실제로 그것을 골랐는지까지 검사한다**(Step 3.11). 검사 술어는 `chain_replay._claimed_filter` — **서빙되는 질의를 만드는 그 빌더**에서 컴파일하므로 검증한 계획과 서빙되는 계획이 갈릴 수 없고, 프로브 쌍은 합성 리터럴이 아니라 **데이터에서 가장 큰 실제 `(table_name, source_name)`**이다. 인덱스 **이름이 계획에 나타나는지**까지 따로 본다(다른 인덱스가 만든 그럴듯한 계획은 이 인덱스를 죽은 무게로 남긴다).
- ⚠️ **`WITHDRAW_PLAN_MIN_ROWS` 미만이면 실패가 아니라 `NOT VERIFIED`**를 찍는다. 작은 표에서 Seq Scan은 **옳은 계획**이고, 거기서 우는 검사는 운영자가 검사를 무시하게 만든다. 표가 커진 뒤 다시 돌릴 것.
- 이 인덱스는 **아무것도 대체하지 않는다** — 기존 UNIQUE 복합 인덱스는 업서트의 충돌 대상이라 그대로 필요하다.

#### 값 제안 접두 인덱스 (`idx_suggest_<테이블>_<컬럼>`) — F3

입력 제안(`GET /tables/{t}/columns/{c}/values`)이 쓰는 인덱스. **이 계열은 `models.py`에 선언되어 있지 않고, `setup_db_performance.py`(Step 3.8)가 유일한 생성 경로다.** 이유가 둘 겹친다 — ⓐ `create_all`은 기존 테이블에 인덱스를 추가하지 않는다(위 경고), ⓑ 정의에 쓰이는 `COLLATE "C"`가 PostgreSQL 전용이라 테스트 스위트의 sqlite `create_all`이 깨진다.

**왜 일반 btree로는 안 되는가 (이 DB에서 실측):** 이 데이터베이스의 콜레이션은 `Korean_Korea.949`다. **비-C 콜레이션에서 btree는 `LIKE '접두%'`를 범위로 만들지 못한다** — 플래너는 인덱스를 고르고도 전 엔트리를 Filter로 버린다.

```
-- 기존 idx_bonding_map_base(일반 btree)만 있을 때, base LIKE 'C%'
Index Only Scan using idx_bonding_map_base
  Index Cond: (base IS NOT NULL)
  Filter: ((base)::text ~~ 'C%'::text)
  Rows Removed by Filter: 1755308        -- 값 3개를 얻는 데 232ms
```

`(lower(col) COLLATE "C", col COLLATE "C")` 인덱스에서는 같은 질의가 `Index Cond: lower(base) >= 'c' AND < 'd'` / **0.2ms**가 된다. 두 번째 키는 값 1개당 seek 1회로 걷는 커서(`(lower(col), col) > (직전 lower, 직전 값)`)를 인덱스 탐색으로 만든다. `number` 선언 컬럼은 콜레이션이 개입하지 않으므로 **일반 btree `(col)`** 이다.

```sql
-- 존재 + **유효성** 확인. indisvalid/indisready를 안 보면 죽은 인덱스를 정상으로 읽는다.
SELECT ci.relname AS indexname,
       i.indisvalid AND i.indisready AS usable,
       pg_size_pretty(pg_relation_size(ci.oid)) AS size,
       pg_get_indexdef(i.indexrelid) AS indexdef
FROM pg_index i
JOIN pg_class ci ON ci.oid = i.indexrelid
JOIN pg_namespace n ON n.oid = ci.relnamespace
WHERE n.nspname = 'public' AND ci.relname LIKE 'idx_suggest_%'
ORDER BY usable, indexname;    -- usable=false가 위로 온다
```

> ⚠️ **`usable = false`(INVALID)는 인덱스가 없는 것보다 나쁘다.** 플래너는 그 인덱스를 절대 쓰지 않는데, 스크립트의 `CREATE INDEX IF NOT EXISTS`는 **이름이 있으므로 건너뛴다** — 몇 번을 재실행해도 안 고쳐지고 그 컬럼의 제안은 영구히 시간 초과다. 아래 ⚠️ CONCURRENTLY 항목이 그 도달 경로다(멈춘 줄 알고 Ctrl+C → INVALID 인덱스 잔존). 복구는 `REINDEX INDEX CONCURRENTLY <이름>;` 또는 `DROP INDEX CONCURRENTLY <이름>;` 후 스크립트 재실행. 스크립트도 Step 3.8 시작에서 이 목록을 먼저 출력한다.

- **대상 선정은 config가 결정한다** — [config/suggest_config](./config/suggest_config.md)의 `index_min_rows`(기본 10,000행 이상 테이블) / `index_columns`(강제 지정) / `index_exclude`(제외). 정책 구현은 `server/value_suggest.py` `index_targets` **한 곳**뿐이다.
- **없으면 그 컬럼의 제안이 조용히 느려지지 않고 꺼진다** — 응답이 `values: []` + `unavailable_reason`이 된다. 드롭다운이 비면 **먼저 이 사유 문자열을 볼 것.** 사유는 `index_targets` 정책에 직접 물어서 만들어지므로 상황마다 다르다:
  - 대상인데 없다 → `… server/scripts/setup_db_performance.py 를 실행하세요.`
  - `index_exclude`에 있다 → 재실행해도 안 만들어진다고 말하고 제외 해제를 지시
  - `index_columns[테이블]`이 선언돼 있고 이 컬럼이 목록 밖 → 목록 추가를 지시
  - `index_min_rows` 미만 테이블 → 추정 행 수와 함께 `index_columns`에 명시 선언하라고 지시
  - 이름은 있는데 INVALID → `REINDEX`/`DROP` 명령을 그대로 제시(위 ⚠️ 참조)
- 스크립트는 **대상에서 빠진 잔존 인덱스를 삭제하지 않고 DROP 문만 출력**한다(config 로드가 일시 실패한 상태에서 일괄 DROP이 도는 사고 방지). 출력의 `Orphaned suggestion indices` 목록은 사람이 판단해 실행한다.
- ⚠️ **`CREATE INDEX CONCURRENTLY`는 열려 있는 트랜잭션을 기다린다.** 워커가 `idle in transaction`으로 떠 있으면 이 스텝이 멈춘 것처럼 보인다. `pg_stat_activity`로 확인할 것.

### 3.2 데이터베이스 백업 및 복구 (Command Line)
pgAdmin의 [Backup/Restore] 메뉴를 사용하거나 아래 커맨드를 활용하십시오.

**백업 (Backup)**
```bash
pg_dump -U postgres -d assy_manager > assy_manager_backup.sql
```

**복구 (Restore)**
```bash
psql -U postgres -d assy_manager -f assy_manager_backup.sql
```

---

## 🛡️ 4. 주의 사항 (Best Practices)
- **Direct Update 지양**: pgAdmin에서 직접 `UPDATE` 쿼리를 실행하면 애플리케이션의 `AuditLog`가 생성되지 않아 이력 추적이 불가능해집니다. 가능한 한 서버 API를 통해 수정하십시오.
- **Large Query**: 1,000만 행 규모에서 `SELECT *` 조회 시 pgAdmin이 멈출 수 있으므로 항상 `LIMIT` 절을 사용하십시오.

---
*AssyManager Operations Guide v1.0 | 2026.04.18*
