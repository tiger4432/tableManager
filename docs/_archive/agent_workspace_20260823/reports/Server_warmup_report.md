# Server PM 보고서 — 체인 워커 콜드 스타트 웜업 (이슈 #0 마지막 조각)

> **일시:** 2026-07-25 | **상태:** ✅ 구현 완료 (커밋·스테이징 안 함 — 총괄 검수 대기)
> **이력:** [docs/history/20260725_073000_chain_worker_cold_start_warmup.md](../../docs/history/20260725_073000_chain_worker_cold_start_warmup.md)

## 1. 변경 요약 (파일:라인)

**`server/chain_ingestion_worker.py`** (유일한 소스 변경):

| 위치 | 변경 |
|---|---|
| :8 | `import threading` 추가 |
| :110-125 | `_http_local`(threading.local) + `_get_http_session()` 신설 — 스레드당 `requests.Session` 1개 지연 생성(requests import도 이 안으로 이동) |
| :128-147 | `post_event_async`: `requests.post(...)` → `_get_http_session().post(url, json=payload, timeout=3)`(:140) — URL·페이로드·timeout·반환값 전부 불변 |
| :439-486 | `warmup_worker(rules, db_session_factory=None)` 신설 — ①활성 규칙 `mapper_module` 선(先)import ②factory 주어지면 세션 1개 `SELECT 1` 후 close(풀 프라임) ③`_get_http_session()` 1회(requests import 웜) ④`[Warmup] mappers=Xms db=Yms total=Zms` 1줄 로그. 항목별 실패는 warning 로깅 후 계속(치명 아님) |
| :709-711 | 기동 경로: `start_chain_ingestion_worker`의 sys.path 설정 **직후**(=`mappers.*` 해석 가능 시점), while 루프 진입 전 `warmup_worker(rules, db_session_factory)` |
| :740-742 | **리로드 재웜업(핵심)**: SYSTEM_RELOAD 분기에서 `reload_worker_process_cache()` → `load_chain_rules()` 직후 `warmup_worker(rules)` — DB 프라임은 풀 유지되므로 생략(`None`) |

**`server/tests/test_chain_warmup.py`** (신규): 단위 테스트 5건.

## 2. HTTP 세션 스레드 안전 방식 + 근거

**선택: `threading.local` 스레드-로컬 세션** (공유 단일 Session 아님).

- `requests.Session`은 스레드 안전이 문서상 보장되지 않는다(쿠키 저장소 등 세션 내부 상태 변이에 레이스 가능 — 알려진 requests 이슈). 스레드당 세션 1개면 공유 상태 자체가 없어 **무조건 안전**.
- keep-alive 이득이 유지되는 근거: `post_event_async`는 `asyncio.to_thread`(기본 ThreadPoolExecutor)로 실행되지만, 워커의 모든 통지(`_dispatch_broadcasts`·스윕)는 **단일 코루틴에서 순차 `await`** — 동시 POST가 없어 executor는 유휴 스레드 1개를 반복 재사용하고, 그 스레드의 세션이 커넥션 풀(keep-alive)을 계속 물고 있는다.
- 대안이던 "공유 Session + HTTPAdapter"(urllib3 풀은 thread-safe)도 실용상 동작하나, 세션 레벨 상태 공유 리스크가 0이 아니므로 더 단순·확실한 스레드-로컬을 채택.
- HTTP 커넥션 **선수립은 하지 않음**: 워커 기동 시 웹서버가 아직 안 떠 있을 수 있어(5-프로세스 병렬 기동) 웜업은 requests import + Session 생성까지만. 첫 통지의 TCP 수립(로컬 수 ms)만 남고 이후 재사용.

## 3. 리로드 경로 재웜업 확인

- `reload_worker_process_cache()`가 `sys.modules`에서 `mappers.*` 제거 → 직후 `warmup_worker(rules)`가 **새로 로드된 규칙 기준**으로 즉시 재import. 리로드로 규칙이 바뀌어도 새 활성 매퍼가 웜업 대상.
- 리로드 시 DB 프라임 생략(풀 유지됨), HTTP 세션도 유지되므로 사실상 매퍼 재웜업만 수행 — 과공학 없음.

## 4. 테스트 결과

```
python -m pytest tests/test_chain_warmup.py tests/test_chain_hol_scheduling.py --noconftest -p anyio -k "not trio"
→ 12 passed (신규 웜업 5 + 기존 HOL/인라인발사 7 — 회귀 없음)
```
- conftest 우회 사유: 로컬 환경 psycopg2 부재로 `from main import app` 실패(기존과 동일). 테스트는 DB 비의존 순수 단위.
- `py_compile`: `chain_ingestion_worker.py`, `tests/test_chain_warmup.py` 정상.
- 신규 5건: 활성 매퍼 선import / 비활성 규칙 skip / 모듈 부재·불량 규칙 무해 / DB 프라임(execute 1회+close) / DB 프라임 실패 무해.

## 5. 제약 준수

- 경계 계약·이벤트 형식·엔드포인트 불변(POST 인자 동일). F1/F2/F3·인라인 발사·`[Latency]` 계측 로직 무변경(기존 테스트 7건 통과로 확인).
- 커밋·스테이징 안 함.

## 6. 사용자 확인 포인트 (재기동 후)

1. 워커 기동 로그에 `[Warmup] mappers=Xms db=Yms total=Zms` 1줄 — mappers가 기존 첫 체인의 ~1.1s를 흡수했는지.
2. **재기동 후 1번째 체인**의 `[Latency] ... total=..ms` — 기대: mapper 콜드 비용(~1125ms)과 requests import 비용이 사라져 **total ≤100ms**(첫 통지의 TCP 수립 수 ms만 잔존; 웜업 전 1297ms 대비).
3. 어드민에서 매퍼 저장 등으로 `SYSTEM_RELOAD` 발생 → `[Reload]` 직후 `[Warmup]` 로그 + **리로드 직후 첫 체인**도 total ≤100ms.
4. 2번째 이후 체인이 기존 31~47ms 수준 유지(회귀 없음).

## 7. 미해결 / 다음 단계

- 런타임 실측(위 4개 포인트)은 사용자 환경 필요 — 코드만으로 종결 불가.
- 잔여: 이슈 #0의 기존 런타임 검증 항목(F1~F3·마이그레이션 게이팅·스윕 무-오발사)과 함께 재기동 1회에서 일괄 확인 권장.
