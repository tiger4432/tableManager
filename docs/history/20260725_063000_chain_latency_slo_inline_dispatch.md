# 체인 반응 100ms SLO: 통지 인라인 발사(기아 제거) + 구간 계측 + 기동 마이그레이션 회귀 수정

> **일시:** 2026-07-25 | **도메인:** Server PM | **관련:** [task/chain_outbox_latency.md](../../task/chain_outbox_latency.md) §SLO, 직전 이력 [20260725_001824](20260725_001824_chain_outbox_reliability_f1_f2_f3.md)

## 현상 (사용자 라이브 로그 실측)

1. **인덱스 생성 전**: 체인 커밋 → 브로드캐스트 도착 **~10s**. broadcast_at NULL이 5s grace를 넘겨 스윕이 정상 경로를 "유실"로 오인 → 불필요한 전체 리프레시(`batch_refresh_required`) 오발사 → 클라이언트 1000행 재조회.
2. **인덱스 생성 후**: 편집 PUT → 체인 실행 +0.63s → 브로드캐스트 도착 +0.78s = **총 ~1.4s**. SLO(100ms) 대비 14배.
3. **기동 회귀**: 재기동 시 워커가 `UndefinedColumn: broadcast_at` 크래시(수동 SQL로 임시 해소됨).

## 근본 원인

### A. 통지 태스크 기아(starvation) — F2 구현의 구조적 결함
`chain_ingestion_worker.py`의 asyncio 이벤트 루프가 **동기 DB 쿼리·매퍼 실행에 블로킹**되는 동안, `dispatch_broadcasts_bg`(`asyncio.create_task`)로 예약한 통지 태스크는 루프가 다음 `await`에 닿을 때까지 실행되지 못했다. 체인 워커 프로세스(`run_chain_worker.py`)는 이 코루틴 **하나만** 이벤트 루프에 올리므로, "백그라운드 예약"은 지연 이득이 전혀 없이 기아 창만 만들었다. 그 사이 broadcast_at NULL을 스윕이 유실로 오인해 전체 리프레시를 오발사(1번 현상)했다.

### B. 기동 마이그레이션 트랜잭션 오염
`main.py` startup의 마이그레이션 블록들이 한 커넥션을 공유하면서 실패 시 rollback이 없었다. `ADD COLUMN processed_chain`이 기존 DB에서 "이미 존재" 예외로 트랜잭션을 abort → 후속 `broadcast_at` ADD COLUMN이 `InFailedSqlTransaction`으로 조용히 실패(`except: pass`) → 컬럼 미생성 → 워커 크래시(3번 현상).

## 해결

### 1. 통지 인라인 발사 (`chain_ingestion_worker.py`)
- `process_pending_groups` 끝의 `dispatch_broadcasts_bg(...)`(create_task 예약)를 **`await _dispatch_broadcasts(...)` 인라인 호출**로 전환. commit은 이미 끝난 뒤라 #2(commit-before-broadcast) 이득 유지, F2(group_order 단일 순차)·F1(all-ok 시 broadcast_at 스탬프) 로직 불변.
- 불용이 된 `dispatch_broadcasts_bg`·`_background_broadcast_tasks` 레지스트리 제거.

### 2. 메인 루프 동기 호출 오프로딩 — **불필요 판정 (최소 변경)**
- 근거: (a) 체인 워커 프로세스의 이벤트 루프에는 이 코루틴 외 다른 태스크가 없어(1번 수정 후) 동기 블로킹의 피해자가 없다. (b) 매퍼·commit은 통지의 **선행 조건**이라 오프로딩해도 체인 경로 지연이 줄지 않는다. (c) 루프 내 동기 쿼리(SYSTEM_RELOAD 1s 스로틀·스윕 5s 스로틀·pending 조회)는 부분 인덱스로 ms 수준이며, 블로킹 중에도 LISTEN 커넥션이 NOTIFY를 버퍼링해 유실이 없다. 잔여 영향은 다음 배치의 wake 구간에 한정되고, 이는 계측(3)으로 상시 관측된다 — 실측 후 필요 시 재검토.

### 3. 구간별 계측 로그 (SLO 검증용)
- tx당 1줄 INFO: `[Latency] tx=... wake=Xms mapper=Yms commit=Zms notify=Wms total=Tms ok=bool`
  - wake: outbox 이벤트 감지(LISTEN wake 또는 반복 시작)→매퍼 시작 | mapper: 매퍼+`apply_batch_updates` | commit | notify: commit→POST 응답(그룹 전 메시지+스탬프) | total: 감지→통지 완료.
- 구현: `start_chain_ingestion_worker`가 `listener.wait()` 반환 시각(`loop_wake_ts`)을 캡처해 `process_pending_groups(batch_wake_ts=...)`로 전달, 그룹별 timing dict를 `pending_broadcasts` 3-튜플 `(event_ids, messages, timing)`에 실어 `_dispatch_broadcasts`가 발사 완료 시 로깅. 통지 없는 no-op 그룹은 미로깅(스팸 방지).

### 4. 스윕 오발동 가드 — grace 5s 유지 판정
통지·스탬프가 배치 처리와 **같은 코루틴 반복 안에서 인라인 완료**되므로(단일 루프 순차 실행) 스윕은 "커밋됐지만 미발사" 상태를 구조적으로 볼 수 없다. 스윕이 잡는 NULL은 POST 실패/스탬프 실패/커밋 직후 크래시 등 **진짜 유실**뿐 → grace 상향 불필요(빠른 진짜 복구 유지). docstring에 명시.

### 5. 기동 마이그레이션 게이팅 (`main.py`)
- `processed_chain`·`broadcast_at` 블록 모두 **`information_schema.columns` 존재 확인 게이팅**으로 전환(`setup_db_performance.py` 선례 패턴): 컬럼 존재 시 조용히 skip — 예외 경로 자체가 사라짐.
- 백필은 종전대로 "컬럼을 방금 생성했을 때만"(재기동 시 백필이 진짜 미전달 행을 전달됨으로 오인하는 것 금지).
- 모든 마이그레이션 except에 `conn.rollback()` 추가(공유 커넥션 트랜잭션 오염 차단) + `logger.error`로 기록(삼킴 제거). 첫 `data_rows` 블록도 동일 처리.

## 수정 파일
| 파일 | 변경 |
|---|---|
| `server/chain_ingestion_worker.py` | 인라인 발사 전환, `dispatch_broadcasts_bg`/`_background_broadcast_tasks` 제거, `[Latency]` 계측(wake 캡처·timing 3-튜플·발사 시 로깅), 스윕 docstring 가드 근거 |
| `server/main.py` | 기동 마이그레이션 information_schema 게이팅 + rollback + logger.error |
| `server/tests/test_chain_hol_scheduling.py` | `dispatch_broadcasts_bg` 패치 → `_dispatch_broadcasts` async 패치, 3-튜플 반영, **기아 회귀 방지 테스트** `test_broadcasts_fired_inline_before_return` 추가 |
| `task/chain_outbox_latency.md` | SLO 공식화(100ms) + 실측/기대치 기재 |

## 검증
- 단위 테스트 **7/7 통과**: `python -m pytest tests/test_chain_hol_scheduling.py --noconftest -p anyio -k "not trio"` (conftest가 psycopg2 부재로 `from main import app`에서 실패해 우회; trio 백엔드 미설치로 asyncio만. DB 비의존 순수 단위).
- `py_compile`: `chain_ingestion_worker.py`·`main.py`·테스트·`setup_db_performance.py` 정상.
- 계측 로그 스모크(가짜 매퍼/POST): `[Latency] tx=tx_demo_001 wake=0ms mapper=16ms commit=0ms notify=31ms total=47ms ok=True` 형식 확인.
- 시그니처 전파: `process_pending_groups`(+`batch_wake_ts` 키워드, 기본값으로 하위호환)·`_dispatch_broadcasts`(3-튜플) — Grep 전수 결과 호출부는 워커 내부 1곳 + 테스트뿐, 연쇄 갱신 완료. `dispatch_broadcasts_bg` 외부 참조 없음(문서/이력 제외).
- **런타임 미검증(psycopg2/Postgres 부재)**: 재기동 후 실 SLO 실측, 마이그레이션 게이팅 로그, 스윕 무-오발사 — 사용자 체크리스트는 보고서 참조.

## 한계 / 주의
- SLO 잔여 병목이 mapper_ms(커스텀 매퍼 비용)로 나타나면 매퍼 최적화가 별도 과제.
- 통지 인라인화로 POST 실패 시 최악 `3s 타임아웃 × 메시지 수`만큼 다음 배치 착수가 늦어질 수 있으나, 웹서버 다운 상황(어차피 통지 불가)에 한정되고 데이터 경로(commit)는 이미 완료 상태라 무결성 영향 없음. 유실분은 스윕이 회수.
