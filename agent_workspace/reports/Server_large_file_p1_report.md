# 완료 보고: 대형 파일 인제션 P1 — heavy 레인 분리 + 진행 가시화 + 재기동 경고

- 지시서: `agent_workspace/tasks/Server_large_file_p1_heavy_lane_task.md`
- 작업자: server-pm (메인 트리, 커밋 안 함, 라이브 재기동 안 함)
- 테스트: 기준선 `233 passed / 1 allowed fail(test_map_presets_api)` → 최종 **253 passed / 1 allowed fail** (신규 20개 전부 통과, 회귀 0)

---

## 1. 설계 결정과 근거

### 1-1. HOL의 실제 발원지 (조사 결과)
watchdog `Observer`는 **모든 워크스페이스 핸들러의 이벤트를 단일 디스패치 스레드에서 실행**하고,
기동/주기 스윕도 단일 스윕 스레드에서 `_handle_event`를 인라인 호출한다. 즉 대형 파일 1개가
처리되는 동안 그 스레드가 점유되어 **모든 테이블**의 후속 파일이 대기했다(HOL). 따라서 격리의
핵심은 "라우팅 스레드가 대형 파일 처리에 블로킹되지 않게 큐로 이관"이다.

### 1-2. 임계 설정 위치: 전용 파일 `server/config/ingestion_settings.json` (⚠ escalation §6-1)
지시서 예시는 `table_config.json`의 `_system.heavy_file_mb`였으나 조사 결과 **채택하지 않았다**:
- `table_config.json`의 모든 소비처가 최상위 키를 무필터로 테이블로 순회한다 —
  `models.init_dynamic_models`(동적 ORM/물리 테이블 생성), `_provision_workspaces`(워크스페이스
  자동 생성), `setup/init_db.py`, `seed_data.py`, `migrations/*`, `/tables` 노출 등.
  `_system` 키를 넣으면 `_system`이라는 물리 테이블·워크스페이스가 생기며, 전 소비처에
  `_` 접두 필터를 심는 전수 수정이 필요(블라스트 반경 큼, 이번 태스크 범위 초과).
- `server/config/`의 현행 관례는 **서브시스템별 전용 파일**이다(`chain_rules.json`,
  `enrichment_rules.json`, `maps.json`, `ontology_mapping.json`, `auto_update_control.json`).
  인제션 시스템 설정도 이 관례를 따라 `ingestion_settings.json`을 신설했다.
- 핫리로드: 임계값은 **파일 이벤트(라우팅 결정)당 1회** 디스크에서 읽는다 — config 폐지 배치의
  "파일 경계 스냅샷" 규율과 동일한 의미론(변경은 다음 파일부터 반영, 한 파일의 결정 안에서
  값이 갈리지 않음). watcher 재기동 불필요.
- 검증: `heavy_file_mb`는 양수(int/float)만 유효. bool/문자열/0 이하/결측/파일 부재 → 기본 10MB
  + 1회 경고(dedup). 라이브 config는 건드리지 않았고 `.sample`만 추가(§7 적용 전문 참조).

### 1-3. 레인 구조: 공유 단일 heavy 워커 + 워크스페이스 backlog 라우팅 + 직렬화 락
- `HeavyIngestionLane`(directory_watcher.py): FIFO `queue.Queue` + 데몬 워커 스레드
  `watcher-heavy-lane` 1개(첫 제출 시 지연 기동). `WorkspaceWatcher`가 1개를 만들어 전 핸들러에
  주입. `heavy_lane=None`(재시도 임시 핸들러·레거시 직접 생성·기존 테스트)은 종전 인라인 경로
  그대로 — 하위호환.
- **순서 보존 (경계 계약 불변식)** — 3중 장치:
  1. `_heavy_backlog` 카운터: heavy에 제출됐고 아직 완료 안 된 이 워크스페이스 파일 수.
     `> 0`이면 후속 파일은 **크기 무관** 큐 후미로 제출 → 워크스페이스 내 FIFO 유지.
  2. 워크스페이스 직렬화 락(`get_workspace_serial_lock` — **모듈 레벨 경로 키 레지스트리**,
     핸들러 인스턴스가 복수여도 공유): heavy 워커와 인라인 경로 모두 처리 전 획득 —
     두 레인이 같은 테이블을 동시에 업서트하는 일 자체가 불가능.
  3. 인라인 경로는 락을 **논블로킹 try-acquire**: 실패(=같은 워크스페이스 처리 중)하면 블로킹
     대기 대신 큐 후미로 재라우팅 — 순서 보존과 observer 스레드 HOL 방지를 동시 만족.
     (submit마저 실패하는 최후 폴백만 블로킹 acquire — 정합 우선.)
- **교차 워크스페이스 격리**: heavy 파일은 큐 제출 후 라우팅 스레드가 즉시 반환 → A 테이블
  7분짜리 파일이 B 테이블 3행 파일을 막지 않는다(테스트 ③로 결정적 검증).
- **크기 분류**: 이벤트 시점 `os.stat` 1회. 복사 진행 중 파일이 작게 읽혀 normal로 오분류될 수
  있으나 그 경우 **레인 도입 전과 동일한 인라인 동작으로 열화**될 뿐 정합성 문제는 없다
  (auto_update는 원자적 copy&rename → on_moved 시점에 최종 크기 — 주 대형 발원지는 정확 분류).
- **기존 동시성 가드 전수 점검**:
  - `_processing_lock`/`processing_files`: heavy 제출된 파일은 큐 대기 중에도 유지(스윕/이벤트
    이중 진입 차단), 정리는 heavy 워커의 `finally`로 이관. 인라인은 종전대로 호출자 정리.
  - `_sweep_lock`/`_sweep_attempted`: 스윕이 `_handle_event`를 부르므로 **스윕 경로도 자동으로
    heavy 라우팅을 탄다**(테스트 ⑤). 대형 파일은 즉시 반환되어 스윕(재기동 캐치업)이 더는
    대형 파일에 직렬 블로킹되지 않음. raws/ 잔류 중 재스윕은 `_sweep_attempted` 시그니처 +
    `processing_files`가 이중으로 차단.
  - `_sync_lock`(F2): 무접점. 데드락 분석: heavy 워커는 직렬화 락만 대기, 락 보유자는 큐를
    기다리지 않음 — 순환 없음.
- **아카이브/에러/로그/알림 경로 불변**: 레인은 `process_with_retry`를 그대로 호출 —
  archives/err 이동, FileIngestionLog, file-processed·batch-refresh(+C-5 절단·total_log_count),
  진행 콜백 전부 기존 코드 경로 그대로. 발신 경로 교차 점검: 체인 워커는 이번 신설 이벤트를
  보내지 않으며 기존 `/internal/events/*` 계약(페이로드 포함)은 무변경.

### 1-4. 진행 가시화: push-캐시-서빙 (프로세스 간 폴링 신설 없음)
- 전달 경로: watcher → `POST /internal/events/ingestion-state` (신설, **push**) → 웹서버 인메모리
  `IngestionActivityRegistry`(신규 `server/ingestion_activity.py`) → `GET /admin/file-ingestion/active`.
- 레지스트리 유입 3종: ① ingestion-state(QUEUED/PROCESSING/FINISHED — heavy 파일만 명시 통지,
  HTTP 왕복 최소화) ② 기존 `file_ingestion_progress` 브로드캐스트를 수신부에서 인터셉트해
  진행률 갱신(normal 파일 엔트리는 이 경로로만 생성, lane 기본 "normal", **기존 lane 비오염**)
  ③ 기존 file-processed 수신 시 제거. 파일명 키는 세 경로 모두 `get_basename` 정규화로 일치.
- 고아 정리: watcher가 처리 중 죽으면 FINISHED가 안 오므로 snapshot 시 TTL(30분, 진행 갱신
  기준) 퇴거. FINISHED/remove는 멱등.
- **WS 이벤트 계약 완전 불변**: 이벤트명·페이로드 모두 무변경(신규 WS 이벤트도 없음).
  ingestion-state는 브로드캐스트하지 않는 레지스트리 전용 내부 이벤트. 페이로드는 소형 스칼라
  필드만(무절단 컬렉션 동봉 금지 교훈 준수 — 컬렉션 자체가 없음).
- 임베디드 모드(main.py 비-DECOUPLED): 같은 프로세스이므로 HTTP 없이 레지스트리 직접 반영
  콜백 배선. (임베디드는 종전에도 on_progress 미배선 — 진행률 미표시는 기존과 동일, 현행 유지.)

### 1-5. Admin UI (client2 — 소폭, 기존 구조/tokens 준수)
- File 탭 최상단 "진행 중(Active Ingestions)" 섹션(stage-section 관례): 파일명·테이블·**HEAVY
  배지**(badge-warning)·진행률 바(tokens 변수만 사용)·행 수·경과. 항목 0이면 섹션 자체 숨김.
- **재기동 경고**(P1 안전장치, 표시만): ① File 탭 섹션 내 경고 배너 "인제션 진행 중 N건 — 지금
  서버를 재기동하면 진행 중 파일은 처음부터 재처리됩니다 (단건 시 N% 진행)" ② 헬스 스트립
  File 카드: 실패 0건+진행 중이면 warn 상태·경고 sub, 실패 있으면 danger 유지+sub에 경고
  ③ Overview File 카드: 진행 중 메트릭 + 이벤트 라인 상단 노출 + warn 상태.
- 갱신: File 탭 기존 30s 자동 갱신 + 진행 항목이 있는 동안만 도는 5s 경량 타이머(탭 표시 중
  한정, 목록 비면 자동 소멸). 인메모리 스냅샷 조회라 서버 부하 무시 가능. — "폴링 신설 금지"는
  괄호 문구대로 **프로세스 간(watcher→웹서버) 경로**로 해석했고 그 경로는 push다. 클라이언트
  admin 폴링은 기존 헬스 스트립 30s 패턴 준용(§6-4 확인 요망).

## 2. 변경 파일

| 파일 | 변경 |
|---|---|
| `server/parsers/directory_watcher.py` | 설정 로더(`load_ingestion_settings`/`get_heavy_threshold_bytes`/1회 경고), 워크스페이스 직렬화 락 레지스트리, `HeavyIngestionLane`, 핸들러 라우팅(`_route_and_process`/`_classify_lane`/`_submit_to_heavy_lane`/`_run_lane_job`/`_notify_ingestion_state`), `_handle_event` 재구성, 생성자 kwargs(`on_ingestion_state_callback`/`heavy_lane` — 말단 추가, 하위호환), `WorkspaceWatcher` 배선+`stop()` 레인 정지 |
| `server/ingestion_activity.py` | **신규** — 진행 스냅샷 레지스트리(스레드 안전, TTL 퇴거, 멱등 제거) |
| `server/main.py` | 레지스트리 import, 임베디드 상태 콜백 배선+완료 정리, `POST /internal/events/ingestion-state`(신설), `/internal/events/broadcast` 진행 인터셉트, `/internal/events/file-processed` 제거 인터셉트, `GET /admin/file-ingestion/active`(신설) |
| `server/run_watcher.py` | `trigger_ws_ingestion_state`(파일명 정규화+push) + WorkspaceWatcher 배선 |
| `server/config/ingestion_settings.json.sample` | **신규** — 설정 샘플(문서 주석 포함) |
| `server/tests/test_heavy_lane.py` | **신규** — 20개 테스트 (아래) |
| `client2/admin.html` | File 탭 진행 중 섹션 마크업(+경고 배너) |
| `client2/src/admin.js` | active fetch/렌더(`renderActiveIngestions`/`formatElapsed`), 5s 경량 타이머, 헬스 카드·Overview 카드 통합 |
| `client2/dist/*` | vite 빌드 산출물 갱신 (`npm run build` 성공) |

## 3. 테스트 전문 (신규 `server/tests/test_heavy_lane.py`, 접두 `hvy_test_*`)

지시서 ①–⑤ 전부 커버, 동시성은 Event/락 기반 결정적 구성(sleep 경합 없음 — 짧은 정리 창만
조건 폴링 `_wait_until` 사용).

1. `test_heavy_threshold_default_when_settings_absent` — 파일 부재 → 10MB 기본
2. `test_heavy_threshold_reads_and_hot_reloads_settings_file` — 값 읽기 + 파일 재기록 즉시 반영(파일 경계 핫리로드)
3. `test_heavy_threshold_invalid_values_fall_back_to_default` ×6(parametrize: "ten"/True/-5/0/None/[10]) — 기본 폴백
4. `test_size_boundary_routes_heavy_vs_inline` — **① 크기 경계**(임계=100B: 99→인라인, 100→heavy 큐), processing_files 유지/정리, backlog 증감
5. `test_threshold_config_change_reflected_on_next_file` — **① config 변경 반영**(1MB→~1KB 하향 후 동일 크기 파일이 heavy로)
6. `test_handler_without_lane_processes_inline_regardless_of_size` — 레인 미배선 하위호환
7. `test_same_workspace_order_preserved_behind_heavy` — **② 순서 보존**: heavy 진행 중(게이트 블로킹) 같은 워크스페이스 소형 파일이 큐 후미 대기, 완료 순서 [heavy→small] 검증
8. `test_inline_falls_back_to_queue_when_workspace_busy` — 직렬화 락 점유 시 인라인 대신 큐 후미(HOL 방지+순서 보존)
9. `test_cross_workspace_small_file_not_blocked_by_heavy` — **③ 교차 워크스페이스 비차단**: A heavy 블로킹 중 B 소형 파일 즉시 완료
10. `test_sweep_routes_big_files_to_heavy_lane` — **⑤ 스윕 경로 라우팅**: 스윕 대상 대형 파일이 `watcher-heavy-lane` 스레드에서, 소형은 스윕 스레드에서 처리
11. `test_heavy_lane_emits_state_lifecycle` — QUEUED→PROCESSING→FINISHED 순서·필드(lane/size/타임스탬프)
12. `test_activity_registry_state_progress_and_remove` — 상태·진행 병합(lane 비오염)·normal 엔트리 생성·멱등 제거
13. `test_activity_registry_evicts_stale_entries` — 고아 TTL 퇴거
14. `test_activity_registry_ignores_malformed_payloads` — 불량 페이로드 무해
15. `test_active_api_snapshot_shape` — **④ active API 계약**: 내부 push→스냅샷 필드 전수·FINISHED 제거 (TestClient)

실행: `conda run -n assy_manager python -m pytest server/tests/ -q`
→ `1 failed(test_map_presets_api — 기준선 허용 실패), 253 passed`. 신규 파일 단독 20 passed.
`py_compile` 4개 파일 OK, `npm run build` OK.

## 4. 라이브 검증 계획 (미수행 — 라이브 재기동 금지 제약)

**재기동 필요 항목** (총괄 승인 후 5-프로세스 재기동, :8080 웹서버 + watcher):
1. `GET http://127.0.0.1:8080/admin/file-ingestion/active` 응답이 **JSON**인지 확인(정적 catch-all
   HTML 200 함정 — 구코드 상태에서 호출하면 HTML이 오므로 재기동 후 검증해야 유효).
2. 대형 CSV(>10MB, 실측용 99,999행) + **다른 테이블** 소형 CSV 동시 투입 → 소형이 수 초 내 완료
   (교차 격리), watcher.log에 `🐘 Routed to heavy lane` 확인.
3. heavy 진행 중 **같은 테이블** 소형 파일 투입 → heavy 완료 후 처리(순서 보존), 완료 후
   업서트/아카이브/FileIngestionLog/알림 정상.
4. admin File 탭: 진행 섹션·HEAVY 배지·진행률 바 5s 갱신·재기동 경고 배너, 헬스 스트립 warn,
   Overview 카드. 완료 시 목록 자동 소거.
5. 스윕 캐치업: watcher 정지 → raws/에 대형+소형 배치 → 기동 → 스윕이 대형만 heavy로 보내고
   소형·타 테이블이 선완료되는지.
6. 임계 핫리로드: `ingestion_settings.json` 값 변경 후 다음 파일부터 반영(재기동 불필요) 확인.

**재기동 불필요 항목**: 없음(신설 엔드포인트 2종이 웹서버 코드에 있으므로 전부 재기동 후).

## 5. 적용 필요 config 전문 (선택 — 파일 없으면 기본 10MB로 동작)

`server/config/ingestion_settings.json` (신규 생성 시):
```json
{
  "heavy_file_mb": 10
}
```

## 6. Escalation (총괄 판단 요망)

1. **임계 설정 위치**: 지시서 예시(`table_config._system`) 대신 전용 파일
   `server/config/ingestion_settings.json` 채택(근거 §1-2). `_system` 방식을 원하면 table_config
   전 소비처에 `_` 접두 필터를 심는 별도 태스크가 선행되어야 함.
2. **경계 계약 추가분 승인**: REST 신설 `GET /admin/file-ingestion/active`,
   `POST /internal/events/ingestion-state`(내부·비브로드캐스트). **WS 이벤트명·페이로드·셀 형태는
   무변경**. 승인 시 스펙/CODE_MAP 반영은 doc-keeper 몫.
3. **heavy 워커 단일 스레드**: 서로 다른 테이블의 heavy 파일 2개가 동시에 오면 heavy끼리는
   직렬화된다(소형은 계속 비차단). P1 목표(교차 격리)는 충족 — 필요 시
   `ingestion_settings.json`에 워커 수 설정 추가는 후속(P3와 함께 검토 권장: heavy 병렬화는
   outbox 대형 tx 파도를 증폭시킬 수 있음).
4. **클라이언트 5s 경량 폴링**(진행 항목 존재+File 탭 표시 중 한정): "폴링 신설 금지"를 프로세스
   간 경로로 해석했음. 부적절하다고 판단되면 해당 타이머(`scheduleActiveRefresh`)만 제거해도
   30s 자동 갱신으로 동작.
5. **admin 재처리(retry-failed)·PENDING_RETRY 폴러 경로**는 레인/직렬화 락 밖(종전과 동일한
   동시성 의미론 유지 — 이번 불변식 범위는 두 레인 간). 재처리까지 직렬화가 필요하면 후속.

## 7. 히스토리 초안 (doc-keeper용 — docs/ 미수정)

> feat(ingestion): 대형 파일 P1 — heavy 레인 분리(크기 임계 라우팅·워크스페이스 순서 보존·교차
> 워크스페이스 격리·스윕 경로 포함), 진행 스냅샷 push 파이프라인(ingestion-state →
> IngestionActivityRegistry → /admin/file-ingestion/active), admin 진행 가시화(File 탭 진행
> 섹션·HEAVY 배지·진행률 바)와 재기동 경고(헬스 스트립·Overview). 임계는 신규
> server/config/ingestion_settings.json `heavy_file_mb`(기본 10MB, 파일 경계 핫리로드).
> WS 계약 무변경. 테스트 +20(hvy_test_*), 253 passed.

## 8. 교훈 제안 (server-pm.md 반영 후보)

- **함정**: watchdog `Observer`는 모든 핸들러의 이벤트를 단일 디스패치 스레드에서 실행한다 —
  핸들러 안에서 인라인 장기 처리를 하면 그 워크스페이스만이 아니라 **전체 워크스페이스**가
  HOL로 막힌다(스윕 스레드도 동일 구조).
  **올바른 방법**: 장기 작업은 이벤트 스레드에서 분류만 하고 전용 큐/워커로 이관, 이벤트
  스레드는 즉시 반환.
- **함정**: 순서 보존을 위해 처리 경로에 락을 넣으면, 락 대기 자체가 디스패치 스레드를 다시
  블로킹해 격리가 무효화된다.
  **올바른 방법**: 논블로킹 try-acquire + 실패 시 큐 후미 재라우팅 — 순서 보존과 비블로킹을
  동시에 만족시킨다.
- **함정**: `table_config.json` 최상위에 메타/시스템 키를 추가하면 모든 소비처(동적 모델 생성·
  워크스페이스 프로비저닝·시드/마이그레이션)가 그 키를 테이블로 취급한다.
  **올바른 방법**: 시스템 설정은 server/config의 서브시스템별 전용 파일 관례를 따른다.

## 9. QA 픽스 반영 (GO-WITH-FIXES 후속 — `QA_large_file_p1_review.md` F1/F3/F4)

총괄 지시 3건 전부 반영. **main.py는 무접촉**(M1 병렬 작업 존중 — 이번 라운드 수정 파일:
`ingestion_activity.py` / `parsers/directory_watcher.py` / `run_watcher.py` / `tests/test_heavy_lane.py`).

### F1 [중] QUEUED 장기 대기 엔트리 TTL 퇴거 → 상태별 TTL 차등
- `server/ingestion_activity.py`: `STALE_QUEUED_TTL_SECONDS = 24h` 신설, `snapshot()` 퇴거가
  `_ttl_for(entry)`(QUEUED→24h, 그 외→기존 30분)를 사용. 생성자에 `queued_ttl_seconds` 추가(테스트 주입용).
- 하트비트 방식 대신 TTL 차등을 택한 근거: watcher 사망 잔재는 ① watcher 재기동 시 스윕이 같은
  파일을 재처리하며 동일 키 엔트리를 갱신/제거(자가 치유) ② 웹서버 재기동 시 레지스트리가 비므로
  무한 잔류 없음 — 추가 통지 트래픽 없이 수 줄로 닫힘. QA 권장안 두 갈래 중 전자.
- 회귀 테스트: `test_activity_registry_keeps_long_queued_entries` — PROCESSING TTL 초과 backdate에서
  QUEUED만 생존, QUEUED 전용 TTL 초과 시엔 퇴거.

### F4 [낮] 재라우팅 소형 파일 lane 오표기 → 분류 실값 통지
- `directory_watcher.py`: `_submit_to_heavy_lane`/`_run_lane_job`이 `lane` 인자(크기 분류 실값)를
  받아 QUEUED/PROCESSING 통지에 그대로 싣는다 — 순서 보존 재라우팅된 소형 파일은
  `lane:"normal"`(+QUEUED "대기" 표기), heavy 배지/카운트 오염 제거. 로그도 라우팅 사유
  (`size` | `workspace-order`) 구분. 클라이언트는 기존 렌더러가 normal 배지를 이미 처리 —
  **client 변경·재빌드 불필요**.
- 회귀 테스트 2종: `test_rerouted_small_file_reports_normal_lane`(락 점유 재라우팅),
  `test_backlog_rerouted_small_file_reports_normal_lane`(backlog 후미 — big은 heavy, small은 normal 순서 검증).
- 참고: QA F4의 나머지 절반(재라우팅 소형 파일이 타 워크스페이스 heavy 뒤에 줄 서는 공유 큐
  비용)은 QA 판정대로 후속(P3/워커 설정화 연계) — 이번 수정은 표기 정확성만.

### F3 [낮→격상] run_watcher 재처리 폴러를 순서 계약에 편입
- `run_watcher.py` `poll_pending_retries`: `process_archived_file_sync` 호출을
  `with get_workspace_serial_lock(workspace_root):`로 감쌈(QA 확인대로 한 줄 폐쇄). 폴러는 heavy
  워커·observer와 같은 프로세스이므로 모듈 레벨 락 레지스트리가 그대로 공유된다. heavy 처리 중
  재시도는 완료까지 대기(백그라운드 폴러 스레드라 무해). 재진입 문제 없음 —
  `process_archived_file_sync`는 내부에서 락을 잡지 않는다.
- **main.py의 admin retry-failed(별도 프로세스) 경로는 지시대로 범위 외 백로그 유지.**
- 회귀 테스트: `test_retry_pattern_waits_for_heavy_via_workspace_serial_lock` — 락 레지스트리
  동일성(표기 상이 경로 포함) + heavy 처리 중 재처리 패턴이 대기했다가 완료 후 진행함을
  Event 기반으로 검증.

### 검증
- 신규 파일 단독: **24 passed** (기존 20 + 회귀 4).
- 전체 스위트: **257 passed / 1 allowed fail(test_map_presets_api)** — 기준선 253 이상 유지, 회귀 0.
- `py_compile` 3개 파일 OK. main.py·client2 무변경(재빌드 불필요).

## 10. 인계 요약

- **변경**: §2 표 + §9(QA 픽스 F1/F3/F4) 참조. 커밋 없음(총괄 diff 검수 대기), docs/·main.py
  무변경(M1 병렬 작업 존중).
- **검증**: 전체 pytest **257 passed / 1 allowed fail**(기준선 253 이상), 신규 24 통과,
  py_compile OK, vite build OK. 라이브 검증은 §4 계획으로 이관(재기동 필요).
- **미해결/후속**: §6 escalation(§6-5는 F3로 run_watcher 측 해소 — main.py 재시도 경로만 백로그),
  QA F2(라우팅 check-then-act 잔여 창 원자화)·F4 잔여(공유 큐 소형 파일 대기)·F5·F6·F7은 QA
  판정대로 후속. P2(체크포인트)·P3(outbox 파도)는 범위 밖 유지.
- **다음 단계**: 총괄 diff 검수(QA GO-WITH-FIXES 반영 확인) → 재기동 포함 라이브 검증(§4,
  QA §4 추가 3건 포함) → doc-keeper 문서 반영(§7).
