# feat(ingestion): 대형 파일 P1 — heavy 레인 분리 + 진행 가시화 + 재기동 경고 (+라이브 드릴 PASS)

- **일시**: 2026-07-26
- **커밋**: `4fd8ac9` (P1 본체 + QA 픽스 F1/F3/F4) · `8b0fd03` (드릴 후속 — QUEUED 통지 선발신 + total_log_count 대칭화)
- **작업자**: server-pm (구현) · qa-reviewer (GO-WITH-FIXES 검수 + 라이브 드릴)
- **보고서**: `agent_workspace/reports/Server_large_file_p1_report.md` · `QA_large_file_p1_review.md` · `QA_p1_live_drill_report.md`

## 배경

실측 기준 99,999행 CSV ≈ 7분(250행/s). watchdog `Observer`는 **모든 워크스페이스 핸들러의 이벤트를 단일 디스패치 스레드에서 실행**하므로(기동/주기 스윕도 단일 스레드 인라인), 대형 파일 1개가 처리되는 동안 **전체 테이블**의 후속 파일이 대기했다(HOL). 2026-07-25 21:29 인시던트(created_logs 무절단 전송)로 시급성이 실증되어 사용자 승인된 대형 파일 전략의 1단계(P1)를 구현했다.

## 변경 내용

### 1. Heavy 레인 (server/parsers/directory_watcher.py)

- 크기 임계(기본 10MB) 초과 파일은 전용 FIFO 큐 + 데몬 워커 `watcher-heavy-lane` 1개로 이관 — 라우팅 스레드는 즉시 반환(교차 워크스페이스 격리). 임계는 신규 `server/config/ingestion_settings.json`의 `heavy_file_mb`(**파일 이벤트당 1회 디스크 읽기 — 파일 경계 핫리로드**, 무효값·부재 시 기본 10MB + 1회 경고).
  - ⚠️ 지시서 예시(`table_config._system`)는 채택하지 않음 — table_config 전 소비처가 최상위 키를 테이블로 순회하므로 `_system` 물리 테이블/워크스페이스가 생긴다. server/config의 서브시스템별 전용 파일 관례를 따름(escalation 승인).
- **워크스페이스 내 FIFO 보존 3중 장치**:

```python
def _route_and_process(self, abs_path, uploader):
    lane, size_bytes = self._classify_lane(abs_path)          # os.stat 1회
    if lane == "heavy":
        return self._submit_to_heavy_lane(abs_path, uploader, "heavy", size_bytes)
    if self._heavy_backlog_nonzero():                          # ① backlog 잔여 → 크기 무관 큐 후미
        return self._submit_to_heavy_lane(abs_path, uploader, "normal", size_bytes)
    lock = get_workspace_serial_lock(self.workspace_path)      # ② 모듈 레벨 경로 키 락 레지스트리
    if not lock.acquire(blocking=False):                       # ③ 논블로킹 — 실패 시 큐 재라우팅
        return self._submit_to_heavy_lane(abs_path, uploader, "normal", size_bytes)
    ...
```

  락 대기로 디스패치 스레드가 다시 막히는 것을 논블로킹 try-acquire + 큐 후미 재라우팅으로 회피(순서 보존과 비블로킹 동시 만족). `run_watcher.poll_pending_retries`의 재처리 경로도 같은 락으로 감쌈(QA F3).
- 스윕 경로는 `_handle_event`를 재사용하므로 **자동으로 heavy 라우팅을 탄다** — 재기동 캐치업이 대형 파일에 직렬 블로킹되지 않음.
- 아카이브/에러/FileIngestionLog/알림 경로 불변(`process_with_retry` 그대로 호출). **WS 이벤트 계약 완전 불변**.

### 2. 진행 가시화 — push-캐시-서빙 (신규 server/ingestion_activity.py)

```
watcher → POST /internal/events/ingestion-state (신설, push·비브로드캐스트)
        → IngestionActivityRegistry (웹서버 인메모리, TTL 퇴거: PROCESSING 30분/QUEUED 24h — QA F1)
        → GET /admin/file-ingestion/active (신설)
```

- 레지스트리 유입 3종: ① ingestion-state(QUEUED/PROCESSING/FINISHED — heavy만 명시 통지) ② 기존 `file_ingestion_progress` 브로드캐스트 인터셉트(normal 엔트리는 이 경로로만 생성) ③ file-processed 시 제거(멱등). 임베디드 모드는 HTTP 없이 콜백 직접 배선.
- 재라우팅된 소형 파일은 `lane:"normal"`로 통지(QA F4 — HEAVY 배지 오염 제거).

### 3. Admin UI (client2/src/admin.js, admin.html)

- File 탭 최상단 "진행 중(Active Ingestions)" 섹션 — 파일명·테이블·HEAVY 배지·진행률 바·행 수·경과. 진행 항목이 있는 동안만 도는 5s 경량 타이머(File 탭 표시 중 한정).
- **재기동 경고**(표시만): 섹션 배너 "인제션 진행 중 N건 — 지금 서버를 재기동하면 진행 중 파일은 처음부터 재처리됩니다" + 헬스 스트립 File 카드 warn + Overview 카드 진행 메트릭.

### 4. 드릴 후속 (8b0fd03)

- **QUEUED 통지 선발신**: 빈 큐에서 워커가 즉시 픽업해 PROCESSING이 먼저 발신 → 뒤늦은 QUEUED가 레지스트리를 역행 덮어쓰던 경합(~5초 '대기' 오표시)을 QUEUED를 submit 이전으로 이동해 제거. submit 실패 시 FINISHED 정리 통지 후 인라인 폴백.
- **total_log_count 대칭화**: watcher-직행 `internal_event_batch_refresh`가 msg 재구성 시 필드를 누락하던 비대칭을 순수 추가 필드로 해소 —

```python
# main.py internal_event_batch_refresh (~3447)
msg["total_log_count"] = actual_count   # 체인 경로(passthrough)와 대칭 — 클라가 절단 여부 판별 가능
```

## 라이브 드릴 실증 (24713a4 — 재기동 후, 신규 온보딩 hvy_drill_big/small)

| 항목 | 실측 |
|---|---|
| heavy 라우팅 | 15.6MB/100,000행 → `🐘 Routed to heavy lane queue (size)`, 총 처리 415.5s |
| **교차 비차단 (핵심)** | heavy 진행 중 타 테이블 소형 3건 각 **2.27s** 완료 — 종전 최악 ~415s 대비 **약 180배** |
| 같은 테이블 순서 보존 | 후속 소형 파일 `workspace-order` 재라우팅 → heavy 완료 5ms 후 처리, FileIngestionLog id 순서 증명 |
| 무결성 | **100,008행 = 100,000 + 8, bk 중복 0, 유실 0** |
| created_logs 절단 | WS 실수신 — **정확히 500건 절단**, 페이로드 278KB(절단 전이라면 수백 MB급). 2026-07-25 인시던트 회귀 없음 |
| 이벤트 루프 | 0.25s 폴링 1,614회 — p50 3.5ms/p95 26ms, 연속 스파이크·동결 없음. 체인 notify 15~32ms |

판정 **PASS**. 잔여 라이브 항목: heavy 도중 재기동 멱등 수렴 드릴(§5 계획만 — 총괄·사용자 협의 후).

## 아키텍처 영향

- 인제션 토폴로지: 워처 내부가 2-레인(inline/heavy)으로 분화 — 경계 계약 추가분은 REST 2종(`GET /admin/file-ingestion/active`, `POST /internal/events/ingestion-state` — 내부·비브로드캐스트)뿐, WS 이벤트명·페이로드·셀 형태 무변경.
- heavy 워커는 단일 스레드 — heavy끼리는 직렬(P1 목표인 교차 격리는 충족, 워커 수 설정화는 P3와 함께 검토).
- 테스트 +27(`test_heavy_lane.py`), 전체 278 passed / 1 allowed fail.

## 다음 단계

- P2: FileIngestionLog 오프셋 체크포인트 재개 + 파일 해시 dedup + #10(D-1) + audit old/new_value 길이 상한.
- P3: outbox 후단 backpressure + PG COPY 벌크 경로 + heavy 워커 수 설정화.
- 관찰(저순위): 임베디드 모드 `trigger_ws_refresh` 레거시 경로는 C-5 절단 미적용(보드 등재). :8080 지터 0.68%(100~846ms 단발)의 발생원 미규명 — 장기 프로파일링 별도 태스크 권장.
