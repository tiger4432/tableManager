# 체인 워커 콜드 스타트 웜업: 매퍼 선import + DB 풀 프라임 + HTTP keep-alive

> **일시:** 2026-07-25 | **도메인:** Server PM | **관련:** [task/chain_outbox_latency.md](../../task/chain_outbox_latency.md) §SLO(이슈 #0 마지막 조각), 직전 이력 [20260725_063000](20260725_063000_chain_latency_slo_inline_dispatch.md)

## 현상 (사용자 라이브 로그 실측)

- 워커 기동 후 **첫 체인만** `[Latency] wake=0ms mapper=1125ms commit=0ms notify=172ms total=1297ms`.
- 2번째부터 `total=47ms`, `31ms` — SLO(100ms) 달성.
- 원인 분해: ①매퍼 모듈 첫 동적 import(mapper 1125ms의 대부분) ②SQLAlchemy 풀 첫 커넥션 수립·다이얼렉트 초기화 ③웹서버로의 첫 HTTP 커넥션 수립 + `requests` 첫 import(notify 172ms).

## 왜 수정하나 (수용 대신)

`SYSTEM_RELOAD`가 `reload_worker_process_cache()`로 매퍼 캐시(`sys.modules`의 `mappers.*`)를 비우므로, 콜드 스타트는 **재기동 직후만이 아니라 운영 중 리로드 직후에도 재발**한다. 리로드 직후 첫 체인도 100ms 안이 목표.

## 해결 (`server/chain_ingestion_worker.py`)

### 1. `warmup_worker(rules, db_session_factory=None)` 신설
- **매퍼 선(先)import**: 활성 규칙(`enabled=True`)의 `mapper_module`을 `importlib.import_module`로 미리 로드해 캐시를 덥힌다.
- **DB 커넥션 프라임**: `db_session_factory`가 주어지면(기동 경로) 세션 1개로 `SELECT 1` 1회 실행 후 close — 풀 첫 커넥션·다이얼렉트 초기화를 앞당긴다. 리로드 경로에서는 풀이 유지되므로 `None`으로 호출해 생략.
- **HTTP 클라이언트 준비**: `_get_http_session()` 1회 호출로 `requests` 모듈 import(전역 캐시)와 Session 생성. 웹서버가 아직 기동 전일 수 있어 **실제 커넥션 수립은 시도하지 않음**(첫 통지에서 수립 후 keep-alive 재사용).
- 웜업 실패는 치명 아님 — 항목별 `logger.warning` 후 계속 기동. 완료 시 1줄 계측: `[Warmup] mappers=Xms db=Yms total=Zms`.

### 2. 호출 지점 2곳
- **기동**: `start_chain_ingestion_worker`의 sys.path 설정 직후(`mappers.*` 해석 가능 시점), while 루프 진입 전 — `warmup_worker(rules, db_session_factory)`.
- **리로드 재웜업(핵심)**: SYSTEM_RELOAD 처리에서 `reload_worker_process_cache()` + `load_chain_rules()` 직후 — `warmup_worker(rules)` (DB 프라임 생략).

### 3. HTTP 커넥션 재사용 (`post_event_async`)
- 매 호출 `requests.post`(매번 새 TCP 커넥션) → **스레드-로컬 `requests.Session`**(`threading.local`) 재사용으로 전환. timeout=3 유지, URL·페이로드·반환값 불변.
- **스레드 안전 근거**: `requests.Session`은 스레드 안전이 보장되지 않으므로(쿠키 저장소 등 내부 상태 변이 레이스) 공유 세션 대신 스레드당 1개를 유지. `post_event_async`는 `asyncio.to_thread`(기본 ThreadPoolExecutor)로 실행되고 워커의 통지는 단일 코루틴에서 **순차 await**되므로 실제로는 유휴 스레드 1개가 반복 재사용됨 → 스레드당 세션이어도 keep-alive 이득이 유지된다.

## 수정 파일
| 파일 | 변경 |
|---|---|
| `server/chain_ingestion_worker.py` | `threading` import, `_http_local`/`_get_http_session()` 신설, `post_event_async` 세션 재사용 전환, `warmup_worker()` 신설, 기동·리로드 2곳 호출 |
| `server/tests/test_chain_warmup.py` | 신규 5건: 활성 매퍼 선import / 비활성 skip / 모듈 부재 무해 / DB 프라임(execute+close) / DB 프라임 실패 무해 |

## 검증
- 단위 테스트 **12/12 통과**(신규 5 + 기존 HOL 7): `python -m pytest tests/test_chain_warmup.py tests/test_chain_hol_scheduling.py --noconftest -p anyio -k "not trio"` (psycopg2 부재로 conftest 우회, DB 비의존 순수 단위).
- `py_compile`: `chain_ingestion_worker.py`·테스트 정상.
- 경계 계약 불변: 이벤트 형식·엔드포인트·F1/F2/F3·인라인 발사·`[Latency]` 계측 무변경(기존 HOL 테스트 7건 통과로 회귀 부재 확인).
- **런타임 미검증**: 재기동 후 첫 체인 `total` 실측(기대: 100ms 이내, `[Warmup]` 로그로 웜업 소요 확인), SYSTEM_RELOAD 직후 첫 체인 실측.

## 한계 / 주의
- 웜업은 기동/리로드 시점에 동기 실행되므로 그만큼(기존 첫 체인이 내던 ~1.2s) 기동 완료가 늦어진다 — 체인 처리 가용 시점은 동일하고 첫 요청 지연만 앞당겨진 것. `main.py` 임베디드 모드(`create_task`)에서는 startup 이벤트 루프를 잠시 점유하나 기동 1회에 한정.
- HTTP는 커넥션을 선수립하지 않으므로 재기동 후 첫 통지에 TCP 수립 비용(로컬 수 ms)이 남는다 — 웹서버 기동 순서에 안전한 트레이드오프.
