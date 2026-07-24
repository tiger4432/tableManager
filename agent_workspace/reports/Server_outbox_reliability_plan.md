# [Server PM 구현계획서] 체인 outbox 신뢰성 후속수정 (F1/F2/F3)

> **발신:** Server PM | **수신:** 총괄 PM(lead) | **작성:** 2026-07-24
> **상태:** 계획서(코드 미수정). 총괄 검수·사용자 승인 후 구현 착수.
> **근거 원천:** `task/chain_outbox_latency.md §총괄 검수 결과`(F1~F5).
> **경계 계약:** 이벤트명·페이로드 형태 전부 불변. 신규 이벤트 없음. REST 시그니처 불변.

---

## 0. 검수 주장 재확인 (코드 대조 결과)

각 결함을 코드로 직접 재검증했다. **F1/F2/F3 모두 실재**하며, 라인 인용에 경미한 오프셋과 F3의 조치 방향에 정정 1건이 있다.

| # | 검수 인용 | 실제 확인 | 판정 |
|---|---|---|---|
| F1 timeout | `worker:111` | `chain_ingestion_worker.py:111` `requests.post(url, json=payload, timeout=3)` | ✅ 정확 |
| F1 삼킴 | `worker:124` | 실제 삼킴은 `:114-115`(`post_event_async` except)와 `:128-129`(`_dispatch_broadcasts` except). `:124`는 docstring 라인 | ✅ 실체 정확(라인 오프셋) |
| F1 재시도 없음 | `worker:403` | 발사는 `:404` `dispatch_broadcasts_bg(...)`. 그 위 커밋 `:401`, `processed_chain=True` `:399`. `:403`은 주석 | ✅ 실체 정확(라인 오프셋) |
| F2 그룹별 독립태스크 | `worker:404` | `dispatch_broadcasts_bg`가 `for tx_id in group_order`(`:381`) 루프 **내부**에서 그룹마다 호출 → `asyncio.create_task`(`:135`)로 독립 발사. 그룹 간 도착순서 미보장 | ✅ 정확 |
| F3 인덱스 미매칭 | `models.py:92`·`setup:64` vs `worker:531` | 인덱스는 `models.py:93`·`setup_db_performance.py:65` 모두 `((payload->>'transaction_id'))`(→ `->>`, text). 쿼리 `:531`은 `.as_string()` → `CAST(payload -> 'transaction_id' AS VARCHAR)`(`->` + CAST). 식이 달라 플래너가 인덱스 미사용 | ✅ 정확 |

### ⚠️ 검수 정정 2건

1. **F3 조치 정정 — 인덱스 측 대안이 틀렸다.** 검수는 "인덱스를 `((payload->>'transaction_id')::varchar)`로 맞춰라"를 제시하나, 이는 현재 쿼리의 `.as_string()`(= `CAST(payload **->** 'transaction_id' AS VARCHAR)`)과 **여전히 불일치**한다(`->>` vs `->`+CAST). 즉 인덱스를 그렇게 바꿔도 안 탄다. **자기정합적 해법은 쿼리를 `->>`로 바꾸는 방향뿐**이며, 이 경우 **기존 인덱스(`->>`)를 그대로 맞아 마이그레이션 불필요**. → F3는 쿼리 단독 수정으로 확정.

2. **F3 구현 함정 — `.astext` 직접 사용 위험.** 검수/지시서가 제안한 "쿼리를 `.astext`로"는 컬럼 타입이 `JSON().with_variant(JSONB, "postgresql")`(models.py:68)라 ORM 속성 레벨 comparator가 **제네릭 `JSON`**이다. 제네릭 JSON comparator에는 `.astext`가 없어(`AttributeError` 위험) 그대로는 실패할 수 있다. → **`type_coerce(payload, JSONB)['transaction_id'].astext`**로 JSONB comparator를 강제해 `->>`로 컴파일해야 안전. (구현 시 컴파일 SQL 실측 필수.)

---

## 1. F1 — 통지 유실 무복구 stale 제거 (설계 선택)

### 1.1 문제 정밀 서술
- 성공 그룹: `processed_chain=True`(:399) → `commit`(:401) → `dispatch_broadcasts_bg`(:404) fire-and-forget.
- 통지 실패(웹서버 재시작/타임아웃/3s 초과)는 `:114-115`·`:128-129`에서 로깅만 하고 삼킴.
- 이미 `processed_chain=True`라 워커 큐(`processed_chain==False`, :500)에서 **영구 제외** → 재발사 경로 전무.
- 결과: **DB는 교정되었으나 그리드는 영영 구값.** 핵심가치 #3(실시간 신뢰 전파) 직접 훼손.

### 1.2 (A) 전달상태 추적 vs (B) 주기적 안전망 — 트레이드오프

| 축 | (A) `broadcast_at` 추적 | (B) 주기적 refresh 안전망 |
|---|---|---|
| 감지 정확도 | **정밀** — 미전달 행만 식별 | coarse — 전달 성공 여부 구분 불가 |
| 스키마 변경 | `broadcast_at` 컬럼 + 부분 인덱스 마이그레이션 필요 | 없음 |
| 정상(전달성공) 경로 비용 | 그룹당 UPDATE 1회(broadcast_at 스탬프). 서버측·저비용 | 없음 |
| 재발사 비용 | 미전달 행에만 refresh(희소). 스윕은 `broadcast_at IS NULL` 부분 인덱스로 O(미전달) | **활동 테이블마다 tick마다 refresh 재발사** — 전달 성공해도 발사 |
| 내구성(워커 재시작) | DB `broadcast_at IS NULL`이 마커 → **재시작 후에도 복구** | 활동집합을 DB에서 유도해야 내구성 확보(in-memory면 재시작 시 유실) |
| 1000만행·다중클라 확장성 | 정상경로 세금 ≈ 0(빈 부분인덱스). **버스트에도 우아하게 감쇠** | **정상경로에도 (행수×클라수×tick)에 비례한 재fetch 세금**. 버스트 중 델타+refresh 이중 부하 |
| 구현 복잡도 | 중(bg 태스크에 세션·event_ids 전달) | 저(스키마 무변경) |

**핵심 판단:** (A)의 "정밀성"은 *감지*에서 나온다. *복구 페이로드*는 두 방식 모두 사실상 테이블 단위 `batch_refresh_required`로 수렴한다(ephemeral broadcast_messages를 스윕 시점에 정확 재구성하려면 페이로드를 행마다 저장해야 하고, 이는 1000만행 규모에서 스키마 bloat). 따라서 최적은 **"감지는 A, 복구는 batch_refresh_required"** 조합이다.

### 1.3 ⭐ Server PM 권고안: **(A) `broadcast_at` 추적 + 복구는 table-level `batch_refresh_required`**

**한줄 근거:** (B)는 정상(전달성공 99%+) 경로에도 활동 테이블 전체를 tick마다 재fetch시켜 (행수×클라수)에 비례하는 상시 세금을 물고, 이 세금이 정확히 버스트 인제션(F1/F2 표적 시나리오) 피크에 델타 브로드캐스트와 겹쳐 이중 부하가 된다. (A)는 정상 경로 비용이 빈 부분인덱스로 사실상 0이고, 미전달 행에만 희소하게 refresh하며, `broadcast_at IS NULL`이 DB에 남아 **워커 재시작에도 eventual delivery를 보장**한다. `[확장성 최우선]`(1000만행) 규칙과 #3 모두에서 (A)가 우월.

> 지시서의 총괄 성향("B에서 출발, 부족하면 A최소형 승격")에 대해: **B는 활동 테이블을 durable하게 유도하려면 결국 outbox를 시간창 쿼리해야 하고, 그럼에도 전달 성공/실패를 구분 못 해 상시 redundant refresh를 남긴다.** 즉 B는 확장성 세금 때문에 곧 A로 교체될 공산이 크므로, 처음부터 **A최소형(감지=broadcast_at, 복구=refresh)**으로 직행하기를 권고한다. 이것이 지시서가 승격 목표로 지목한 바로 그 "A의 최소형(실패 행만 마킹+재발사)"이다.

### 1.4 F1 구현 상세 (승인 시)

**(a) 대상 파일:라인/메서드**
- `server/database/models.py:72` 부근 — `DatabaseOutbox`에 컬럼 추가.
- `server/database/models.py:79-88` `_outbox_index_list` — 부분 인덱스 추가.
- `server/scripts/setup_db_performance.py:57-66` 인덱스 목록 — 동일 부분 인덱스 추가(운영 DB 반영 경로 일치).
- `server/chain_ingestion_worker.py:123-137` `_dispatch_broadcasts`/`dispatch_broadcasts_bg` — 시그니처에 event_ids·session_factory 추가, 전달 성공 시 broadcast_at 스탬프.
- `server/chain_ingestion_worker.py:395-404` 성공 분기 — 스탬프 규칙(무-메시지 그룹은 즉시 스탬프).
- `server/chain_ingestion_worker.py:446-505` 워커 메인 루프 — F1 스윕 블록 추가(reload 체크와 동일한 throttle 패턴).

**(b) 구체적 변경 내용**
1. `models.py`: `processed_chain` 아래에
   `broadcast_at = Column(DateTime(timezone=True), nullable=True)` 추가.
2. `models.py` `_outbox_index_list`에
   `Index("idx_outbox_undelivered", "id", postgresql_where=text("processed_chain = true AND status = 'SUCCESS' AND broadcast_at IS NULL"))` 추가. (미전달 행만 색인 → 정상 상태에서 거의 빈 인덱스.)
3. `setup_db_performance.py`에 동일 인덱스 CREATE 항목 추가(문자열식 동일하게).
4. `dispatch_broadcasts_bg(messages)` → `dispatch_broadcasts_bg(pending_broadcasts, session_factory)`로 변경. `pending_broadcasts`는 **F2와 통합**하여 `[(event_ids, messages), ...]`를 group_order대로 담는다(§2 참조). bg 태스크는 각 그룹 메시지를 **순차 전송**하고, 그룹의 **모든 메시지 HTTP 성공 시에만** 새 짧은 세션으로 `UPDATE database_outbox SET broadcast_at=now() WHERE id IN (event_ids)` 실행. 일부라도 실패하면 broadcast_at NULL 유지 → 스윕이 회수.
5. 성공 분기(:397-404): `broadcast_messages`가 **빈 그룹**(체인 no-op 등)은 통지 대상이 없으므로 커밋 시 `broadcast_at=now()`를 함께 설정(스윕 무한재발사 방지). 메시지 있는 그룹만 broadcast_at NULL로 커밋 후 bg 경로.
6. 메인 루프에 스윕 블록(throttle `SWEEP_INTERVAL≈5.0`, `last_sweep_ts` 패턴은 :472-479 reload throttle 복제):
   ```
   미전달 = db.query(...).filter(processed_chain==True, status=="SUCCESS",
             broadcast_at==None, created_at < now()-interval '5s')
             .order_by(id).limit(500).all()
   ```
   `created_at < now()-5s` grace로 in-flight 정상 전달과의 경합 회피. 미전달 행을 `_group_target_tables` 재사용으로 target_table 유도 → **테이블당 1건 dedup**된 `batch_refresh_required` 발사 → 성공 시 해당 행들 `broadcast_at=now()` 스탬프(재발사 종료). 발사는 fire-and-forget 유지(스윕도 commit 경로 밖).

**(c) 사이드이펙트·경계 계약 영향**
- 경계 계약: **불변.** 신규 이벤트 없음 — 복구는 기존 `batch_refresh_required`(models 대조: worker:305 형태 `{event, table_name, change_count, transaction_id}`) 재사용.
- 컬럼 추가는 append-only, 기존 행 NULL 허용 → 기존 데이터 무결성 영향 없음. `data_preservation_and_signature_change.md` 관점 레이어링(CellSource/priority) 무관.
- bg 태스크가 DB 세션을 새로 잡음 → 커넥션 풀 여유 확인 필요(스윕+bg 스탬프 동시성). 짧은 세션 즉시 close로 완화.
- 기존 outbox 행(broadcast_at 없던 과거 SUCCESS 행)은 마이그레이션 시 `broadcast_at`을 `created_at` 등으로 백필하지 않으면 스윕이 전량 회수 시도 → **백필 필수**(아래 (d)).

**(d) 마이그레이션/인덱스**
- 컬럼 추가: `ALTER TABLE database_outbox ADD COLUMN broadcast_at timestamptz NULL;`
- **백필(중요):** 기존 `processed_chain=true` 행이 스윕에 걸리지 않도록
  `UPDATE database_outbox SET broadcast_at = COALESCE(processed_at, created_at) WHERE processed_chain = true;` (1000만행 대비 **1000행 청킹** 또는 `WHERE broadcast_at IS NULL AND id BETWEEN ...` 범위 배치로 실행).
- 부분 인덱스 `idx_outbox_undelivered` CREATE(위 식). `CREATE INDEX CONCURRENTLY` 권장(운영 무중단).
- create_all 경로(models.py)와 setup_db_performance.py **양쪽** 반영.

**(e) 테스트 계획**
- 단위(SQLite 가능 범위): 성공 그룹 커밋 후 broadcast_at 스탬프 로직, 무-메시지 그룹 즉시 스탬프, 스윕 쿼리 필터 정확성(모킹). 부분 인덱스는 SQLite에서 일반 인덱스로 생성되므로 로직만 검증.
- 통합(psycopg2/Postgres CI): 통지 실패 주입(`/internal/events/broadcast`가 실패 반환) → broadcast_at NULL 유지 → 스윕이 grace 후 `batch_refresh_required` 발사·broadcast_at 스탬프 → 재발사 멈춤(eventual delivery 실측). 워커 재시작 시나리오: 미전달 상태에서 재시작 후 스윕 복구 확인.
- `EXPLAIN ANALYZE`로 `idx_outbox_undelivered` 사용 확인(대량 SUCCESS 누적 하에서도 스윕이 부분인덱스만 타는지).

---

## 2. F2 — 그룹 간 브로드캐스트 순서 보존 (F1과 통합 구현)

**(a) 대상:** `chain_ingestion_worker.py:397-404`(성공 분기), `:362-444` `process_pending_groups`, `:123-137` dispatch 함수군.

**(b) 변경 내용:**
- 성공 그룹마다 `dispatch_broadcasts_bg`를 **즉발하지 않고**, `process_pending_groups` 지역 리스트 `pending_broadcasts: List[(event_ids, messages)]`에 group_order대로 append.
- 그룹 데이터 커밋(:401)은 **그룹별 유지**(내구성). 브로드캐스트만 지연.
- 루프 종료 후(=:444 return 직전) **단일** `dispatch_broadcasts_bg(pending_broadcasts, session_factory)` 1회 발사. bg 태스크(`_dispatch_broadcasts`)는 `pending_broadcasts`를 **순서대로**, 각 그룹의 메시지도 순서대로(삭제→upsert, 기존 `:125` 순차 유지) 전송. → 그룹 간·그룹 내 도착순서 모두 group_order로 직렬화.
- 여전히 commit 경로 밖(#2 지연 이득 유지) — 발사는 배치 처리 완료 후 fire-and-forget.

**(c) 사이드이펙트·경계 계약:** 경계 불변. 호출부(:559 `failed_any = await process_pending_groups(...)`) **시그니처 무변경**(dispatch를 함수 내부로 흡수). 그룹 간 통지가 배치 완료까지 미세 지연되나(수 ms~배치시간), commit은 즉시라 데이터 지연 아님.

**(d) 마이그레이션:** 없음.

**(e) 테스트:** 동일 target_table 성공 그룹 2개 → 통지가 group_order대로 순차 도착(모킹된 post 순서 캡처)로 검증. F1 스탬프와 결합: 순차 전송 중 중간 그룹 실패 시 그 그룹만 broadcast_at NULL 유지 검증.

---

## 3. F3 — `idx_outbox_txid` 실사용 (쿼리 단독 수정)

**(a) 대상:** `chain_ingestion_worker.py:531`.

**(b) 변경 내용:**
- 현재: `DatabaseOutbox.payload['transaction_id'].as_string() == last_tx_id` → `CAST(payload -> 'transaction_id' AS VARCHAR)`.
- 변경: `type_coerce(DatabaseOutbox.payload, JSONB)['transaction_id'].astext == last_tx_id` → `payload ->> 'transaction_id'`. 기존 인덱스식(`(payload->>'transaction_id')`)과 **일치** → 인덱스 사용.
- import 추가: `from sqlalchemy import type_coerce`, `from sqlalchemy.dialects.postgresql import JSONB`(파일 상단 import 정리 확인).
- **주의:** `.astext` 직접 호출(제네릭 JSON comparator) 회피 — 반드시 `type_coerce(..., JSONB)` 경유. 구현 시 `str(query.statement.compile(dialect=postgresql.dialect()))`로 `->>` 컴파일 실측.

**(c) 사이드이펙트·경계:** 없음. 결과 동일(text 비교), 인덱스만 타게 됨. 인덱스·마이그레이션 변경 불필요(정정 §0 참조).

**(d) 마이그레이션:** 없음(기존 인덱스 재사용).

**(e) 테스트:** Postgres CI에서 `EXPLAIN ANALYZE` — 변경 전 Seq Scan/필터, 변경 후 `idx_outbox_txid` Index Scan 확인. 대량 미처리 누적(예: 100k+ 미처리 행) 하에서 스캔비용 대조.

---

## 4. F4/F5 문서화 + 히스토리 정정 (구현과 함께)

- `docs/architecture/event_driven_backend.md`: HOL 가드는 **동일 target_table 정적 추정 기반**이며 **매퍼가 다른 테이블을 read해 계산하는 교차 테이블 의존은 순서 보장 안 됨**(F4), 3회 격리 후 후속이 미적용 선행 위에서 계산될 수 있음(F5) 명시.
- 히스토리 정정: `docs/history/20260724_230117...:31` "순서 보존"은 **그룹 내부 한정**이며 그룹 간 역전(F2)은 본 수정 전까지 존재했음을 후속 이력에 기재. 통지 유실 무복구(F1)와 복구경로(broadcast_at 스윕) 추가 기록.

---

## 5. 착수 순서 / 승인 필요 결정 포인트

**순서:** F1(+F2 통합) → F3 → F4/F5 문서 → 런타임 검증.

**승인 필요:**
1. ⭐ **F1 방식 = (A) `broadcast_at` 추적** 채택 여부(지시서 총괄 성향은 B 우선). 본 PM은 확장성 근거로 A 직행 권고.
2. F1 복구 페이로드를 **table-level `batch_refresh_required`**로 확정(exact-delta 재구성 안 함) 승인.
3. F3 구현을 **`type_coerce(JSONB).astext`**로 하고 지시서의 `.astext` 직접·인덱스측 대안을 폐기하는 정정 승인.
4. 마이그레이션 백필(`broadcast_at ← processed_at/created_at`, 청킹) 운영 실행 승인.

---

## 6. 예상 리스크

- **커넥션 풀 압박:** 스윕 쿼리 + bg 스탬프 세션이 워커 풀 소비 → grace/throttle/짧은세션으로 완화, 풀 크기 실측 필요.
- **백필 누락 시 대량 오발사:** 기존 SUCCESS 행 broadcast_at NULL이면 스윕이 전량 refresh → 반드시 백필 후 인덱스/스윕 활성화.
- **스윕 grace 경합:** grace(5s)가 너무 짧으면 정상 in-flight 전달을 미전달로 오인해 중복 refresh. 실측으로 조정.
- **F3 컴파일 불일치:** `type_coerce` 없이 `.astext` 직접 시 AttributeError. 컴파일 SQL 실측 게이트 필수.
- **SQLite 테스트 한계:** 부분/표현식 인덱스·JSONB astext는 Postgres 전용 → 인덱스 실사용·eventual delivery는 psycopg2 CI에서만 최종 검증 가능(코드만으로 단정 불가).
