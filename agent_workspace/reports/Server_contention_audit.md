# Server 5-프로세스 경합(Contention) 전수 점검 보고서

> **작성:** Server PM · 2026-07-25 | **모드:** 분석 전용(코드 수정 없음)
> **시나리오:** 수십만 건 file ingestion 진행 중 + 다수 사용자 동시 사용
> **점검 대상:** ①File Ingestion Watcher ②User API(main.py) ③Chain Ingestion Worker ④Graph Sync Worker(:8090) ⑤Auto-Update Scheduler
> **검증 방법:** 코드 전수 추적(파일:라인) + 런타임 실측(psycopg2 read-only 조회, import 재현 실험). 실측값은 본문에 "실측" 표기.

---

## 0. 실측 환경 스냅샷 (2026-07-25, read-only 조회)

| 항목 | 실측값 |
|---|---|
| PostgreSQL `max_connections` | **100** |
| 현재 접속 수(유휴 시) | 9 |
| `database_outbox` 행 수 / 크기 | **2,705,513행 / 4,862 MB** (DB 전체 11 GB의 44%) |
| outbox 인덱스 개수 / 크기 | **10개** (pkey 122MB, `ix_database_outbox_id` 124MB, `ix_..._event_uuid` 224MB, `ix_..._status` 44MB, `ix_..._processed_chain` 37MB, `idx_outbox_txid` 29MB, `idx_outbox_unprocessed` 10MB, `idx_outbox_pending` 6.4MB, `idx_outbox_reload`/`idx_outbox_undelivered` 16kB) |
| outbox 중복 이벤트 그룹(동일 tx+row+event가 2건 이상) | **1,259,076 그룹** — 사실상 데이터 이벤트 전량이 ×2 중복 |
| `cell_sources` / `audit_logs` | 7,156,139행 / 1,478,877행 |
| `pg_stat_database.deadlocks` | 0 (통계 리셋 이후) |
| xact_rollback / temp_bytes | 214,957회 / 63 GB (대형 정렬 스필 존재) |

---

## 1. 경합 리스크 목록 (심각도순)

### [C-1] 🔴 최고 — uvicorn 이벤트 루프 동결: async 핸들러 내 동기 DB 호출 (실측 증거 있음)

- **실측 증거 (2026-07-25 07:01, 라이브 로그):** 웹서버 access 로그 07:01:35.930→43.086 **약 7초 공백** 후 밀린 응답 일괄 flush(broadcast POST 200, PUT ×2, GET /audit_logs/recent). 그 사이 체인 워커 `/internal/events/broadcast` POST가 3s read timeout(`notify=3000ms ok=False`) → 5s 뒤 스윕이 회수(refresh 오버헤드 발생). 단일 이벤트 루프 블로킹의 전형 패턴.
- **원인 핸들러 특정 (코드 근거):** `main.py`의 다수 엔드포인트가 **`async def`이면서 동기 SQLAlchemy를 루프 위에서 직접 호출**한다. 동결 시각에 완료된 요청과 대조하면 유력 용의자는 ①이다.
  1. **`PUT /tables/{t}/data/updates`** — `main.py:1653`은 `run_in_threadpool`로 업서트를 격리했으나(무죄), **`main.py:1665` `fetch_and_merge_metadata(db, ...)`는 async 핸들러 본문에서 동기 실행** — 구현(`main.py:461-580`)은 cell_overwrites 쿼리 + O(행×컬럼) 파이썬 병합 루프. 대량 인제션으로 DB가 느려진 상태에서 이 쿼리·루프가 수 초 → **루프 전체 동결**. PUT ×2가 동시에 있었으므로 직렬로 2배. 이후 `async_broadcast`(1683-1716)의 대형 `json.dumps`도 루프 위에서 실행되어 가중.
  2. **`GET /audit_logs/recent`** — `main.py:631` **`def`(sync) → threadpool 실행이므로 루프 동결에는 무죄**. 단, 자체 지연 요인(캐시 미스 시 그룹 집계 + `main.py:665` 행별 `get_deleted_row_business_key` N+1)은 별도 존재.
  3. **`POST /internal/events/broadcast`** — `main.py:2787-2806` async: 요청 body JSON 파싱 + `audit_cache.add_logs_batch`가 루프 위. 페이로드가 크면(아래 C-5·C-7) 단독으로도 수 초 동결 가능.
- **async+동기DB 패턴 전수 분포 (main.py 3,079줄 조사 결과):**
  - `DELETE /tables/{t}/rows/{row_id}` `main.py:1112-1116` (crud.delete_row 동기)
  - `POST /tables/{t}/rows/batch_delete` `main.py:1133-1145` — 동기 crud + **`main.py:1145` 삭제행별 `get_deleted_row_business_key` N+1 쿼리를 루프 위에서** (대량 삭제 시 최악의 블로커)
  - `POST /tables/{t}/rows` `main.py:1588-1601` (create_empty_rows_batch + AuditLog 조회 동기)
  - `PUT .../data/updates` `main.py:1665` (상기)
  - `DELETE .../sources/{source}` `main.py:1868`, `PUT .../priority` `main.py:1891`
  - `PUT /tables/{t}/cells/priority/batch` `main.py:1953·1964` (배치 crud + `fetch_and_merge_metadata(include_sources=True)` 둘 다 동기)
  - `POST /tables/{t}/cells/sources/delete/batch` `main.py:2017·2028` (동일 패턴)
  - `GET .../sources` `main.py:1825`, `POST /admin/auto-update/run-now` `main.py:2723` (소형)
  - 조회 계열(`GET /tables/{t}/data` 901, export 1267, audit 631/676 등)은 `def`(sync)라 threadpool 격리 — 무죄.
- **예상 증상:** 인제션·대량 편집 중 웹서버 전체(모든 GET/PUT/WS/내부 브로드캐스트)가 수 초 단위로 멈춤 → 체인 통지 3s 타임아웃 → 스윕 오버 리프레시 → 클라이언트 재조회 폭주로 악순환.
- **권장 조치(제안만):** ① 위 목록의 async 핸들러를 `def`(threadpool)로 전환하거나 동기 구간(`fetch_and_merge_metadata`, N+1 루프)을 `run_in_threadpool`로 이관. ② `batch_delete`의 N+1은 AuditLog 일괄 IN 쿼리로 통합. ③ 대형 `json.dumps`·`audit_cache` 갱신도 threadpool 이관 검토. ④ 루프 lag 계측(예: asyncio loop monitor) 추가 후 재실측.

### [C-2] 🔴 높음 — before_flush 리스너 2중 등록 → **outbox 이벤트 전량 ×2 중복 발행 (실측 확인)**

- **시나리오:** 웹서버·워처 프로세스가 `database.database`와 `server.database.database`를 **서로 다른 모듈 경로로 이중 import** → `@event.listens_for(Session, "before_flush")`(`database/database.py:40`)가 전역 Session 클래스에 **2회 등록** → 모든 동적 테이블 flush마다 `stage_event`가 2번 실행되어 outbox 행이 2건씩 적재.
- **코드 근거:** `server/main.py:93` `from directory_watcher import ...`(모듈 레벨, DECOUPLED여도 실행) → `parsers/directory_watcher.py:14` `from server.database.database import SessionLocal`. 워처 프로세스도 동일(`run_watcher.py:17`은 `database.database`, directory_watcher는 `server.database.database`). `DYNAMIC_TABLES`는 sys 싱글턴(`models.py:165-167`)으로 공유되어 **두 리스너 모두** isinstance 매치.
- **실측:** import 재현 실험에서 `event.contains(Session,'before_flush', fn)` 두 함수 모두 True, class-level 리스너 2개. 라이브 DB에서 **동일 (transaction_id,row_id,event_type) 2건 이상 그룹 1,259,076개** — 데이터 이벤트 사실상 전량 중복.
- **예상 증상:** outbox 쓰기량·인덱스 유지비 **2배**(4.9GB의 절반가량이 중복), 체인 워커 부하 2배(그룹당 이벤트 2배 파싱, 비-배치 규칙이면 **매퍼 2회 실행**), tx 보완쿼리(20000 LIMIT)의 절반을 중복이 소모. 결과가 멱등 업서트라 데이터 오염은 가려져 있으나 수십만 건 인제션 시 처리시간·용량을 정확히 2배로 늘린다.
- **권장 조치:** ① import 경로 단일화(`directory_watcher.py`를 `database.*` 상대 경로로 통일) 또는 ② 리스너 등록을 sys 싱글턴 가드로 멱등화(`if not hasattr(sys, "_outbox_listener_registered")`). ③ 기존 중복 행은 별도 정리 스크립트(오프피크)로.

### [C-3] 🔴 높음 — outbox 무한 성장 + 이벤트당 인덱스 10종·3버전 쓰기 증폭 (실측 확인)

- **시나리오:** 처리 완료된 outbox를 삭제/보관하는 경로가 **없다**(코드 전수 grep — purge/cleanup 없음). 이벤트 1건 = ①INSERT(PENDING) ②status/processed_chain UPDATE ③broadcast_at UPDATE = **행 버전 3개**, 각 버전이 **인덱스 10종** 유지비를 유발(부분 인덱스도 PENDING 시점엔 전부 매치). 페이로드에 전체 행 데이터 스냅샷 포함(`database/database.py:87-121`) → 수십만 건 인제션이면 outbox 쓰기량 ≈ 본 데이터 쓰기량과 동급.
- **실측:** 2.7M행/4,862MB(DB의 44%), dead tuple 79,390. 레거시 중복 인덱스 존재: `ix_database_outbox_id`(124MB)는 pkey(122MB)와 완전 중복, `ix_..._event_uuid` 224MB(사용처 확인 못함), `ix_..._status`(44MB)·`ix_..._processed_chain`(37MB)은 부분 인덱스(`idx_outbox_pending`·`idx_outbox_unprocessed`)와 역할 중복.
- **의뢰서 축 #8 답변:** 신규 4종(`idx_outbox_reload`16kB·`idx_outbox_undelivered`16kB·`idx_outbox_unprocessed`10MB·`idx_outbox_txid`29MB) 자체는 소형이며 조회 이득이 유지비를 압도 — **문제는 신규 4종이 아니라 레거시 비부분 인덱스 4종(429MB)과 무한 보존**. `data_rows`의 GIN/trgm(`models.py:35-38`)은 동적 테이블 인제션 경로(`DYNAMIC_TABLES`)와 무관 — 동적 테이블에는 GIN 없음(`models.py:235-238`), 해당 축 쓰기 증폭 없음.
- **권장 조치:** ① 보존기간 기반 주기 purge(예: SUCCESS+broadcast_at NOT NULL & 7일 경과 → 청크 DELETE 또는 파티셔닝). ② 레거시 중복 인덱스 4종 DROP 검토(마이그레이션 1건). ③ C-2 해소로 유입량 반감.

### [C-4] 🟠 중~높음 — 대량 인제션이 체인 큐를 독점: 사용자 편집 체인 반응 HOL(head-of-line) 지연

- **시나리오:** 체인 워커는 outbox의 **모든** 미처리 이벤트를 id 순으로 소비한다(`chain_ingestion_worker.py:758-760`, LIMIT 200). 수십만 건 인제션이 만든 이벤트(파일당 **단일 tx_id** — `directory_watcher.py:409`)가 큐 선두를 차지하면, 그 뒤에 커밋된 사용자 편집의 체인 파생 통지는 백로그 소진까지 대기 → **SLO 100ms가 인제션 동안 분 단위로 붕괴**.
- **가중 요인 (코드 근거):**
  - tx 보완 쿼리가 같은 tx_id를 **LIMIT 20000**까지 끌어옴(`chain_ingestion_worker.py:796-804`) → 한 반복이 20,200 이벤트 파싱(이벤트당 전체 행 페이로드) — 메모리·CPU 스파이크. 파일이 2만 행을 넘으면 같은 tx가 여러 배치로 쪼개져 **배치 매퍼가 부분 페이로드로 반복 실행**됨.
  - 체인 결과 기록이 **무청킹 단일 `apply_batch_updates`**(`chain_ingestion_worker.py:325-334`) — 매퍼가 수만 updates를 반환하면 1000행 청킹 규칙 위반, 단일 거대 트랜잭션.
  - 인라인 통지(`:599-600` await)는 웹서버가 느릴 때 그룹당 최대 3s×메시지 수만큼 **다음 배치 폴링을 지연**(C-1 동결과 결합 시 배치당 수 초 손실 — 라이브 로그의 `notify=3000ms`가 그 사례).
- **안전 확인된 부분:** 스윕은 부분 인덱스+LIMIT 500+5s grace로 백로그와 무관하게 O(미전달)(`:604-680`); 실패 격리·HOL 가드는 동일 target만 보류(`:487-602`) — 설계 의도대로.
- **권장 조치:** ① 인제션 소스 이벤트에 대해 체인 규칙 매칭이 없는 테이블이면 **적재 시점에 processed_chain=true(또는 별도 플래그)로 스킵**하거나, 트리거 테이블 화이트리스트로 폴링 쿼리 필터. ② 파일 tx를 청크 단위 tx_id로 분할(배치 매퍼 의미론 재확인 필요 — 경계 계약 아님, 총괄 협의). ③ 체인 기록에 1000행 청킹 적용. ④ 통지 실패 시 해당 배치의 잔여 POST를 조기 포기(circuit-break)하고 스윕에 위임.

### [C-5] 🟠 중~높음 — 워처 최종 통지의 `created_logs` 무제한 페이로드 (메모리·루프 동결 결합)

- **시나리오:** 워처는 파일 전체의 감사 로그(변경 **셀당 1건**)를 메모리에 누적(`directory_watcher.py:461-462`)한 뒤, 완료 시 **전량을 HTTP POST**로 웹서버에 전송(`directory_watcher.py:479-480` → `run_watcher.py:53-63`). 수십만 행×수십 컬럼이면 수백만 dict → 워처 OOM 위험 + 수십~수백 MB JSON body. 웹서버는 파싱 **후에야** 500건으로 절단(`main.py:2775-2781`) — 파싱 자체가 async 루프 위(C-1과 동일 축)라 **단독으로 수 초 동결** 가능. `timeout=5`(`run_watcher.py:41`)라 워처 쪽은 타임아웃으로 실패 로그만 남고 진행엔 지장 없으나 서버는 이미 body를 수신·파싱한다.
- **예상 증상:** 대형 파일 인제션 완료 순간 웹서버 순간 동결 + 워처 메모리 급증.
- **권장 조치:** 워처가 POST 전에 상한(예: 500건) 절단 + `all_created_logs` 누적 자체에 상한. change_count만 보내고 로그는 클라이언트가 필요 시 조회하는 방식도 검토(계약 영향 없음 — created_logs는 선택 필드).

### [C-6] 🟠 중간 — 동시 `apply_batch_updates` 간 행 락 순서 미보장 → 락 대기·데드락 가능, 실패 시 파일 전체 err 이동

- **시나리오:** 워처 청크(1000행)와 사용자 PUT(또는 체인 워커 기록)이 같은 테이블의 겹치는 행을 동시에 upsert. CellSource/CellOverwrite 벌크는 키 정렬로 방어되어 있으나(`crud.py:251-253, 283-285` — 주석으로 데드락 의도 명시), **동적 테이블 행 UPDATE는 세션 투입 순서대로 flush**(`crud.py:1059-1077→1086`)라 두 트랜잭션이 역순으로 겹치면 고전적 데드락 조건. 또한 `replace_map` 경로는 **행 삭제를 먼저**(`crud.py:973-988`) 수행해 일반 경로(소스→행 순)와 락 획득 순서가 역전된다.
- **결과 처리의 비대칭:** 데드락/직렬화 실패 시 PG가 한쪽을 abort — 사용자 PUT은 500(`main.py:1654`는 ValueError만 400 처리), **워처는 청크 예외 → 파일 전체를 err/로 이동**(`directory_watcher.py:464-467, 124-134`). 앞 청크는 이미 커밋됨 → **부분 인제션 + 나머지 유실(수동 재시도 전까지)**. 재시도는 멱등 업서트라 데이터는 복구 가능하나 운영 개입 필요.
- **실측:** `pg_stat_database.deadlocks = 0` — 현재까지 미발생(이론 리스크). 단 rollback 21.5만 회 누적의 원인 분해는 못함.
- **권장 조치:** ① `apply_batch_updates` 진입 시 batch.updates를 business_key/row_id로 **정렬**해 행 락 획득 순서를 전 경로에서 일치시킴(저비용). ② 워처 청크에 deadlock/serialization 한정 재시도 1~2회. ③ PUT의 OperationalError를 409/503으로 구분 응답.

### [C-7] 🟠 중간 — Graph Sync 대량 동기화: 무제한 로드 + 무제한 브로드캐스트 + 수십만 행 단일 커밋

- **시나리오:** 인제션 직후 수동 그래프 동기화(전체)를 누르면 `is_graph_synced == False` 행 **전량을 `.all()` 무제한 로드**(`graph_sync_worker.py:506-508`; rollback_and_replay면 전 테이블 `updated_at >= dirty` 재로드 `:531-535`) → 수십만 ORM 객체 메모리. 완료 후 **행별 메타 스탬프를 단일 커밋**(`:719-723, 753`) — 수십만 행 UPDATE 플러시 동안 인제션 upsert와 행 락 경합. 통지는 **행 전량을 `batch_row_upsert` items로 무가드 전송**(`:726-751`, main.py의 100건 가드 없음) — `/internal/events/broadcast` 파싱(C-1)과 WS 팬아웃 폭주. 게다가 **통지 POST(timeout=20)가 commit보다 먼저**(`:746` vs `:753`).
- **완화 요소:** `sync_lock`으로 프로세스 내 동시 1건(`:777-789`), outbox 미발행(graph 메타 컬럼 변경은 리스너가 스킵 — `database/database.py:63-67`), 브로드캐스트 자체는 별도 프로세스라 워커 루프만 점유.
- **권장 조치:** ① 대상 로드·스탬프·통지 모두 1000행 청킹, ② items 100건 초과 시 `batch_refresh_required`로 강등(main.py 계약과 동일 규칙), ③ commit 후 통지 순서로 정렬, ④ 인제션 활성 중 전체 동기화 지양(운영 가이드).

### [C-8] 🟡 중간 — 런타임 ALTER TABLE 핫스왑: ACCESS EXCLUSIVE 락 컨보이 + 프로세스 간 스키마 창(窓)

- **시나리오:** 웹서버의 config watcher만 엔진을 받아 **런타임 DDL** 수행(`main.py:108` → `config_watcher.py:42-43` → `models.py:281-287` `ALTER TABLE ADD COLUMN`). 대량 인제션 청크 트랜잭션(초 단위)이 해당 테이블 락을 쥔 동안 ALTER는 ACCESS EXCLUSIVE 대기열에 서고, **그 뒤에 오는 모든 SELECT/UPDATE가 ALTER 뒤로 줄을 선다**(락 컨보이) → 해당 테이블 전면 정지가 청크 길이만큼 반복될 수 있음. DDL 자체는 개별 트랜잭션 격리(`models.py:284-287`)라 실패 오염은 없음.
- **스키마 창:** 워처/체인/그래프의 config watcher는 `engine=None`(`run_watcher.py:202`, `run_chain_worker.py` 동일)이라 **모델만 갱신하고 DDL은 웹서버에 의존** — 파일 변경 감지 타이밍 차이(디바운스 1s)로 워처가 새 컬럼 포함 INSERT를 DDL 완료 전에 날리면 UndefinedColumn 에러(청크 실패 → C-6의 err 이동 경로). 재현 창은 좁으나 대량 인제션 중 설정 변경 시 실재.
- **권장 조치:** ① DDL에 `lock_timeout`(예: 2s) + 재시도를 걸어 컨보이 상한 설정, ② 운영 수칙으로 "인제션 활성 중 스키마 변경 금지" 명시, ③ 워커들의 모델 갱신을 SYSTEM_RELOAD(웹서버 DDL 완료 후 발행) 순서에 종속시키는 방안 검토.

### [C-9] 🟡 중간 — 웹서버 커넥션 풀(30) vs threadpool(40) 불일치 + 프로세스 합계 이론치 150 > max_connections 100

- **코드 근거:** 프로세스별 독립 엔진 `pool_size=20, max_overflow=10`(`database/database.py:21-27`) × 5프로세스 = 이론 최대 150 > **실측 max_connections=100**. 웹서버 단독으로도 FastAPI sync 핸들러 threadpool 기본 40 스레드가 동시 세션 40개를 요구 가능 → 풀 30 초과분은 `pool_timeout`(기본 30s) 대기 후 TimeoutError 500. **대량 인제션으로 쿼리가 느려져 동시성이 쌓일 때** 발현 조건이 갖춰진다.
- **가중:** C-2의 이중 엔진(웹서버·워처에 각 1개 추가, 평시 유휴)과 체인 워커의 LISTEN raw 커넥션 상시 1개 점유(`chain_ingestion_worker.py:47-56`)는 소폭.
- **실측:** 유휴 시 총 접속 9 — 평시는 여유. 발현은 부하 피크 한정.
- **권장 조치:** ① 웹서버만 pool을 threadpool 크기에 정합(예: pool 30/overflow 10 또는 threadpool 축소), 워커 4종은 pool 5/overflow 2 수준으로 하향(실사용 ≤3) → 합계를 max_connections 안쪽으로 설계. ② `pool_timeout` 축소(5s) + 503 매핑으로 급성 고갈을 빠르게 노출.

### [C-10] 🟡 중~낮음 — 워처 확장자 필터 부재 → 스케줄러 `.tmp` 파일 조기 픽업 레이스

- **시나리오:** 스케줄러는 `copy2(tmp)` → `os.replace(tmp→final)`의 원자 드롭을 쓰지만(`run_auto_update.py:62-63, 174-176, 204-207`), 워처 `_handle_event`는 **확장자 필터 없이 모든 생성 파일에 반응**(`directory_watcher.py:58-64`; `supported_extensions`는 정의만 되고 미사용 — `:32`, 본문 `:70`은 `if True:`). 대형 CSV의 copy2가 디바운스 1s(`:95`)를 넘기면 워처가 **쓰기 중인 `.tmp`를 파싱**(부분 읽기) → 부분 인제션 + `.tmp` 아카이브 이동 → 스케줄러 `os.replace` FileNotFoundError로 수집 FAIL. 소형 파일은 tmp가 1s 안에 사라져 무해(`:98-100` 소멸 가드).
- **권장 조치:** `_handle_event`에서 `.tmp` 제외(또는 supported_extensions 필터 복원) — 1줄 수준.

### [C-11] 🟡 낮~중간 — WS 브로드캐스트 직렬 전송·무타임아웃: 저속 클라이언트 1명이 전체 통지 지연

- **코드 근거:** `ConnectionManager.broadcast`(`main.py:288-299`)는 클라이언트 순회 `await send_text` — 송신 버퍼가 찬(절전/원격/느린) 클라이언트 1명이 전체 브로드캐스트와 그걸 await하는 내부 이벤트 엔드포인트 응답을 지연시킴(체인 3s 타임아웃 유발 요인 중 하나일 수 있음). 다수 사용자 시나리오에서 발현 확률 상승.
- **안전 확인된 부분:** 인제션 경로 자체는 행 단위로 쏘지 않는다 — 워처는 청크당 progress 1건 + 완료 시 `batch_refresh_required` 1건(`directory_watcher.py:472-480`), 체인은 100건 초과 시 refresh로 강등(`chain_ingestion_worker.py:380-396`), PUT도 동일 가드(`main.py:1692-1716`). **의뢰서 축 #6의 "행 단위 폭주"는 없음** — 예외는 C-7 그래프 경로.
- **권장 조치:** send_text에 per-client 타임아웃 + 초과 시 연결 정리, 또는 `asyncio.gather(..., return_exceptions=True)` 병렬 전송.

### [C-12] ⚪ 낮음 — 기타 확인 사항

- **SYSTEM_RELOAD NOTIFY commit 누락**(기존 이슈 #6 잔존): `main.py:2349-2354`는 commit 후 NOTIFY라 안전하나, `main.py:2954-2959`(스크립트 저장 경로)는 미확인 상태로 남아 있던 항목 — 이번 점검 범위에서 재검증 못함(확인 못함).
- **워처 재시도 폴러**(`run_watcher.py:121-133`): 3s마다 SYSTEM_RELOAD `.first()` + PENDING_RETRY 전량 `.all()` — 건수 특성상(파일 로그) 소량, 부분 인덱스 `idx_outbox_reload` 수혜. 안전.
- **스케줄러 DB 사용**(`run_auto_update.py:459-502`): 5s 틱당 `.first()` 2회 — 미미. 안전.
- **`temp_bytes` 63GB 누적(실측)**: 대형 정렬/집계가 work_mem을 초과해 디스크 스필 중 — 어느 쿼리인지 특정 못함(실측 필요). export/audit 집계 후보.

---

## 2. 안전 확인 항목 (점검했으나 문제 없음 — 근거 포함)

| 축 | 판정 | 근거 |
|---|---|---|
| LISTEN/NOTIFY 상호 간섭 | 안전 | `OutboxListener`는 상시 커넥션 + 대기 진입 시 buffered drain(`chain_ingestion_worker.py:71-96`) — LISTEN-after-check 레이스 제거 확인. 트랜잭션 내 동일 채널 NOTIFY는 PG가 dedup하므로 청크당 1통지(스톰 없음). 단 `stage_event`의 행당 `session.execute(NOTIFY)`(`database/database.py:126-131`)는 청크당 1000회 왕복(~수십 ms) — 무해 수준이나 커밋 훅 1회로 줄일 여지. |
| 스윕 vs 정상 통지 경합 | 안전 | 통지·스탬프가 배치 처리와 같은 코루틴에서 인라인 완료(`:595-600`) → 스윕이 in-flight 그룹을 볼 수 없음(설계 주석 `:610-612`과 코드 일치). 스윕은 부분 인덱스(실측 16kB)+LIMIT 500+grace 5s로 백로그 무관 O(미전달). |
| 벌크 업서트 내부 데드락 | 안전 | CellSource/CellOverwrite 벌크는 dedup+키 정렬 후 단일 문(statement)(`crud.py:244-270, 276-303`) — 문 내부 순서 결정적. (문 간·행 UPDATE 순서는 C-6로 이관) |
| 워처 인제션의 WS 폭주 | 안전 | 청크 silent(`directory_watcher.py:454`) + progress 청크당 1건 + 완료 refresh 1건 — 행 단위 발사 없음. (created_logs 크기만 C-5) |
| 스케줄러 파일 드롭 원자성 | 안전(절반) | `.tmp`+`os.replace` 패턴 자체는 올바름(`run_auto_update.py:62-63`) — 워처 쪽 필터 부재만 C-10. 아카이브 충돌은 타임스탬프 서픽스로 처리(`directory_watcher.py:257-259`). |
| 카운트 캐시 정합 | 안전 | 워처/체인의 쓰기는 내부 이벤트 엔드포인트 경유 시 `invalidate_table_cache` 호출(`main.py:2769, 2794`) — 프로세스 간 캐시 무효화 경로 존재. |
| Graph 메타 스탬프의 outbox 오염 | 안전 | graph 메타 3컬럼만 변경 시 outbox 발행 스킵(`database/database.py:63-67`) — 그래프 동기화가 체인 루프를 재점화하지 않음. |
| 체인 순환 루프 | 안전 | `source_name == "chain_ingestion"` 필터(`chain_ingestion_worker.py:269`) + 컨텍스트 설정(`:320-322`) 확인. |

---

## 3. 실측 필요 항목 (코드만으로 단정 불가)

1. **C-1 동결 원인의 최종 귀속**: PUT `fetch_and_merge_metadata` vs `/internal/events/broadcast` 파싱 중 어느 쪽이 7초의 주범인지 — 이벤트 루프 lag 계측(또는 py-spy dump)으로 실측 필요. 두 축 모두 코드상 블로커임은 확정.
2. **인제션 부하 중 PUT 경합 지연 분포**: `fetch_and_merge_metadata`의 cell_overwrites 쿼리 실측 시간(EXPLAIN ANALYZE, 인제션 동시 실행 조건).
3. **C-6 데드락 실재율**: deadlocks=0(현재)이나, 동일 행 동시 편집+인제션 겹침의 인위 재현 테스트 필요. rollback 21.5만 회의 원인 분해(`pg_stat_statements` 필요).
4. **C-4 백로그 소진 속도**: 20만 이벤트 백로그 시 배치당 처리 시간·사용자 편집 체인 지연 실측 (중복 제거 전/후 비교 포함).
5. **레거시 outbox 인덱스 사용률**: `pg_stat_user_indexes.idx_scan`으로 `ix_database_outbox_id`/`event_uuid`/`status`/`processed_chain` 실사용 확인 후 DROP 판단.
6. **temp_bytes 63GB의 발생 쿼리** 특정.
7. **`main.py:2954-2959` NOTIFY commit 누락 여부** — 이번 범위에서 확인 못함.
8. **uvicorn threadpool 실효 크기**(anyio 기본 40 가정) 및 pool_timeout 발현 임계 부하.

---

## 4. 총평 및 권장 착수 순서

수십만 건 인제션 + 다수 사용자 시나리오에서 시스템을 무너뜨리는 것은 DB 락이 아니라 **웹서버 단일 이벤트 루프(C-1)** 와 **outbox 이중 발행·무한 성장(C-2·C-3)** 이다. 특히 C-2는 실측으로 확정된 회귀급 결함(전 이벤트 ×2)으로, 수정 비용 대비 효과(부하 절반)가 가장 크다.

1. **C-2** 리스너 중복 제거 (국소, 효과 최대) → 중복 데이터 정리
2. **C-1** async 핸들러의 동기 DB 격리 (PUT 1665, batch_delete N+1 우선)
3. **C-5** created_logs 상한 (워처 측 1곳)
4. **C-3** outbox purge 정책 + 레거시 인덱스 정리 (총괄과 보존기간 협의)
5. **C-4** 체인 큐 인제션 필터/청킹 (배치 매퍼 의미론 협의 필요)
6. **C-6~C-11** 순차

*경계 계약(REST/WS 이벤트/셀 형태) 변경이 필요한 항목은 없음 — 전부 서버 내부 조치로 가능. 단 C-4의 파일 tx 분할은 배치 매퍼 동작 의미론에 닿으므로 총괄 협의 대상.*
