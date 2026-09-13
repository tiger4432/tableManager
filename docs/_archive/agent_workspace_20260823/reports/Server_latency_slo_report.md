# [Server PM 완료 보고서] 체인 반응 100ms SLO 구조수정 + 기동 마이그레이션 회귀 수정

> **발신:** Server PM | **수신:** 총괄 PM(lead) | **작성:** 2026-07-25
> **상태:** 구현 완료, **커밋/스테이징 안 함**(총괄 검수 후 lead가 커밋). working tree에 그대로 둠.
> **이력:** `docs/history/20260725_063000_chain_latency_slo_inline_dispatch.md` (+gen_index 실행됨)

## 1. 변경 요약 (파일:라인)

| 파일 | 변경 |
|---|---|
| `server/chain_ingestion_worker.py` | `_background_broadcast_tasks` 레지스트리·`dispatch_broadcasts_bg` 제거(불용, 잔존 참조 0건). **:152~196** `_dispatch_broadcasts` — 3-튜플 `(event_ids, messages, timing)` 수용 + 발사 완료 시 `[Latency]` 1줄 로깅. **:419~529** `process_pending_groups` — `batch_wake_ts` 키워드 인자, 그룹별 t_mapper_start/t_mapper_done/t_commit_done 계측·timing dict 누적. **:531~532** 배치 끝 `await _dispatch_broadcasts(...)` **인라인 발사**(기존 create_task 예약 대체). **:541~543** 스윕 docstring에 정상 경로 오발동 구조적 차단 근거(grace 5s 유지). **:634, :647, :688~697, :756** 메인 루프 — `loop_wake_ts` 캡처(`listener.wait` True 반환 시각)·`batch_wake_ts` 소비·전달 |
| `server/main.py` | **:127~185** startup 마이그레이션 — `data_rows` 블록 except에 `conn.rollback()` 추가, `processed_chain`·`broadcast_at` 블록을 **`information_schema.columns` 존재확인 게이팅**으로 전환("이미 존재"는 조용히 skip), 백필은 "컬럼을 방금 생성했을 때만" 유지, 모든 예외 `conn.rollback()` + `logger.error`(삼킴 제거) |
| `server/tests/test_chain_hol_scheduling.py` | `dispatch_broadcasts_bg` monkeypatch → `_dispatch_broadcasts` async 패치(`_patch_dispatch_capture`), 3-튜플 언패킹 반영, timing 필드 검증, **신규: `test_broadcasts_fired_inline_before_return`**(기아 회귀 방지 — 반환 전 POST·스탬프 완료 검증) |
| `task/chain_outbox_latency.md` | §SLO 신설: "값 변경 commit → 클라이언트 통지 도착 100ms 이내(체인 파생 포함)" + 실측(~10s→~1.4s)·원인·수정 후 기대치. 상태 헤더 갱신 |
| `docs/architecture/event_driven_backend.md` | §3.5 인라인 발사·SLO/계측 서술로 갱신, §3.6 F1/F2 "배경 태스크"→인라인 정정, Last-verified 2026-07-25 |
| `docs/process/PROJECT_STATUS.md` | 현재 초점·최근 완료·이슈 #0 갱신 |

## 2. 기아 해소 방식 — 1번(인라인 발사)만으로 충분 판정, 2번(오프로딩) 미적용 + 근거

**적용:** `process_pending_groups` 끝의 배경 태스크 예약을 `await _dispatch_broadcasts(...)` 인라인으로 전환. commit은 이미 그룹별로 완료된 뒤라 #2(commit-before-broadcast) 이득 유지, F2 순서(group_order 단일 순차)·F1 스탬프(all-ok 시) 로직 불변.

**2번(메인 루프 동기 호출 `to_thread` 오프로딩) 미적용 근거:**
1. **기아의 피해자가 사라짐**: 체인 워커 프로세스(`run_chain_worker.py` 확인)는 이벤트 루프에 `start_chain_ingestion_worker` 코루틴 **하나만** 올린다(config watcher는 스레드). 인라인 전환 후 이 루프에서 굶을 수 있는 다른 태스크가 존재하지 않는다.
2. **오프로딩해도 체인 경로가 안 빨라짐**: 매퍼·commit은 통지의 선행 조건(순차 의존)이라 스레드로 옮겨도 total은 동일하다.
3. **잔여 동기 블로킹의 영향은 다음 배치 wake 구간에 한정**되며, SYSTEM_RELOAD 조회(1s 스로틀)·스윕(5s 스로틀)·pending 조회는 부분 인덱스(#1/#3/F1) 하에서 ms 수준. 블로킹 중에도 `OutboxListener` 상시 LISTEN 커넥션이 NOTIFY를 소켓에 버퍼링하므로 유실 없음.
4. 이 판단은 이번에 넣은 `[Latency]` 계측의 **wake 구간**으로 상시 검증된다 — wake가 크게 나오면 그때 오프로딩을 후속 적용(과공학 방지, 실측 기반).

## 3. 계측 로그 (사용자 체크리스트 포함)

형식(tx당 INFO 1줄, 통지 있는 그룹만 — no-op은 미로깅):
```
[Latency] tx=chain_abc123 wake=3ms mapper=25ms commit=8ms notify=12ms total=48ms ok=True
```
- **wake**: outbox 이벤트 감지(LISTEN wake/폴링 발견)→매퍼 시작 (pending 조회·그룹핑 포함. 크면 → 루프 동기 구간/인덱스 점검)
- **mapper**: 매퍼 + `apply_batch_updates` (크면 → 커스텀 매퍼 비용)
- **commit** | **notify**: commit→POST 응답+broadcast_at 스탬프 (크면 → 웹서버/`/internal/events/broadcast` 경로)
- **total**: 감지→통지 완료. 스모크 실측(가짜 매퍼 5ms/POST 10ms): `[Latency] tx=tx_demo_001 wake=0ms mapper=16ms commit=0ms notify=31ms total=47ms ok=True` (Windows 타이머 해상도 ~16ms 반영).

**재기동 후 사용자 확인 체크리스트:**
1. 기동 로그에 마이그레이션 에러 없음. 기존 DB면 `Added ... column` 로그가 **안 떠야** 정상(게이팅 skip). 워커 `UndefinedColumn` 크래시 재발 없음.
2. 셀 편집 → `chain_worker.log`에 `[Latency]` 1줄 확인, **total ≤ 100ms** 기대(로컬 웹서버 기준. 초과 시 최대 구간이 병목).
3. 편집 후 클라이언트에 `batch_row_upsert` **델타**만 도착하고, ~5초 뒤 불필요한 `batch_refresh_required`(전체 리프레시)가 **오지 않아야** 함(스윕 오발동 제로). `[Reliability F1] Recovery sweep ...` 로그는 웹서버를 죽였을 때만 떠야 정상.
4. 버스트 인제션 시에도 tx당 1줄만(로그 스팸 없음).

## 4. 마이그레이션 수정 검증 근거
- **원인 재현 경로 제거**: 기존엔 `ADD COLUMN processed_chain`이 기존 DB에서 예외(이미 존재) → rollback 부재로 공유 커넥션 트랜잭션 abort → `broadcast_at` ADD COLUMN이 `InFailedSqlTransaction`으로 `except: pass`에 삼켜짐. 수정 후엔 `information_schema.columns` SELECT로 **예외 경로 자체가 발생하지 않고**, 만약의 예외도 `conn.rollback()`으로 후속 블록을 오염시키지 않으며 `logger.error`로 드러난다.
- **백필 게이팅 보존**: 백필은 "컬럼 미존재→방금 생성" 분기 안에서만 실행. 재기동 시 skip → 진짜 미전달 행(NULL)을 전달됨으로 오인하지 않음(스윕 회수 경로 보존). `setup_db_performance.py`의 기존 게이팅과 동일 패턴·동일 백필 SQL(1000행 청킹).
- 한계: psycopg2/Postgres 부재로 실 DB 기동 검증은 못함 — 체크리스트 1번으로 확인 요망.

## 5. 테스트 결과
- `python -m pytest tests/test_chain_hol_scheduling.py -q --noconftest -p anyio -k "not trio"` → **7/7 통과** (기존 HOL 3 + F1/F2 2 + 헬퍼 1 + **신규 기아 회귀 방지 1**).
  - `--noconftest`: conftest가 `from main import app`→psycopg2 부재로 컬렉션 실패(기존 알려진 제약). 본 테스트는 DB 비의존 순수 단위.
  - `-k "not trio"`: trio 백엔드 미설치(conftest 부재로 anyio가 양 백엔드 파라미터화). asyncio 변형은 전부 통과.
- `py_compile`: `chain_ingestion_worker.py`·`main.py`·`tests/test_chain_hol_scheduling.py`·`scripts/setup_db_performance.py` 정상.
- Grep 전수: `dispatch_broadcasts_bg`/`_background_broadcast_tasks` 잔존 참조 **0건**(server/). `process_pending_groups` 호출부는 워커 내부 1곳(+`batch_wake_ts` 키워드, 기본값 있어 하위호환)·테스트뿐.

## 6. 경계 계약 / 회귀 확인
- 이벤트명·페이로드·REST·셀 형태 **전부 무변경**, 신규 이벤트 없음. `[Latency]`는 서버 로그일 뿐.
- F1(eventual delivery): 스탬프/스윕/백필 로직 불변. F2(순서): 단일 순차 발사 유지(인라인화는 실행 시점만 변경). F3(인덱스): 무접촉. 확장성: 신규 쿼리 없음(계측은 time.monotonic만).
- 스윕: grace 5s 유지 — 인라인화로 통지·스탬프가 배치와 같은 코루틴 반복 안에서 완료되어 정상 경로 오발동이 구조적으로 불가(docstring 명시).

## 7. 미해결 / 총괄 검수 포인트
1. **런타임 SLO 실측 미완**(환경 제약) — §3 체크리스트로 사용자 확인 필요. wake가 크면 2번(오프로딩) 후속 검토.
2. **인라인화의 트레이드오프**: 웹서버 다운 시 POST 3s 타임아웃×메시지 수만큼 **다음 배치 착수**가 늦어질 수 있음(통지 자체가 불가능한 상황 한정, commit은 이미 완료라 무결성 무관, 유실분은 스윕 회수). 허용 판단 요망.
3. per-tx `[Latency]`의 wake는 같은 배치 내 후행 그룹일수록 선행 그룹 처리 시간을 포함(=해당 tx의 실제 대기)이라 배치가 크면 후행 tx의 wake가 커 보이는 게 정상.
4. 커밋은 총괄이 검수 후 수행(스테이징 안 함).
