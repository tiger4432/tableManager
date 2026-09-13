# QA 보고: P1 heavy 레인 라이브 실측 드릴 (재기동 후)

- 지시서: `agent_workspace/tasks/QA_p1_live_drill_task.md`
- 수행: qa-reviewer, 2026-07-26 09:06–09:20 (재기동 09:02:19 이후 로그만 사용)
- 드릴 테이블: 총괄 지정대로 **신규 온보딩** `hvy_drill_big` / `hvy_drill_small` (id(bk), c1~c5 string)
- 코드 수정 없음. DB는 SELECT만. 생성물 삭제 없음(§7 목록 보고).

## 판정: **PASS** (전 항목 수치 충족, 무결성 결함 0. 표시 계층 낮음 결함 1건 + 정보성 관찰 2건)

P1의 핵심 주장 — "heavy 파일이 타 테이블을 막지 않고, 같은 테이블 순서는 보존되며, 대형 tx가
이벤트 루프를 얼리지 않는다" — 를 15.6MB/10만 행 실파일로 전부 실증했다.
무결성: **100,008행 = 100,000(대형) + 8(후속), bk 중복 0, 유실 0, 전 파일 SUCCESS.**

---

## 0. 사전 단계: 핫 온보딩 (재기동 불필요 체인 검증)

| 단계 | 시각 | 증거 |
|---|---|---|
| table_config.json in-place 재기록(원자적 쓰기 함정 회피 — open 'w' 직접 기록) | 09:06:50 | ConfigWatcher on_modified 발화: "Dynamic models reloaded and hot-swapped" (watcher.log 09:06:50,680) |
| `POST /admin/reload-configs` | 09:07:00 | 200 success (응답 왕복 <1s) |
| SYSTEM_RELOAD 전파 → 워크스페이스 자동 생성 | 09:07:02,964 | "🏗️ Auto-provisioned ... ['hvy_drill_big', 'hvy_drill_small']" + raws/ 감시 등록 2건 (Std-parser workspace) |
| 물리 테이블 생성 | — | information_schema 실측: 두 테이블 모두 시스템 7컬럼(row_id, business_key_val, created_at, updated_at, is_graph_synced, needs_graph_rollback, graph_synced_at) + id, c1~c5 |

reload-configs → 감시 개시까지 **약 3초**, 서버 재기동 0회.

## 1. heavy 라우팅 실측 — PASS

- 파일: `drill_big_100k.csv` **15,600,018B (15.6MB)**, 100,000행. `ingestion_settings.json` 라이브 파일 부재 → 기본 임계 10MB 적용 확인.
- watcher.log 09:10:34,595: `[hvy_drill_big] 🐘 Routed to heavy lane queue (size, 15,600,018B)` — **size 사유 라우팅**.
- 상태 통지 3종 발신 확인: `QUEUED lane=heavy` → `PROCESSING lane=heavy` → `FINISHED` (09:17:29,035).
- active API 라이프사이클(0.25s 폴링 실측): QUEUED(09:10:34.7) → PROCESSING p=1%(09:10:39.5) → … p=99% → 목록 제거(09:17:30.5).
- 총 처리 시간: **투입→아카이브 415.5s (6분 56초)**, 1000행/배치 × 100배치, 진행률 1%≈3.5~4s.

## 2. 비차단 실측 (핵심) — PASS

heavy PROCESSING 중 **다른 테이블**(hvy_drill_small)에 소형 CSV 3개 순차 투입:

| 파일 | 투입 | 아카이브 완료 | 소요 |
|---|---|---|---|
| drill_small_1.csv | 09:10:39.54 | 09:10:41.81 | **2.27s** |
| drill_small_2.csv | 09:10:41.82 | 09:10:44.07 | **2.26s** |
| drill_small_3.csv | 09:10:44.09 | 09:10:46.35 | **2.26s** |

(2.26s 중 ~1s는 watcher의 .tmp→.csv 안정화 대기 — 순수 처리 ~1.2s.)
**Before**: P1 이전 구조(단일 디스패치 스레드 HOL)에서는 heavy 완료까지 대기 → 최악 **~415s(분 단위)**.
**After: 2.3초 — 약 180배 개선.** heavy 완료(09:17:29) 훨씬 전에 3개 모두 SUCCESS + batch_refresh_required(WS) 발신 실측.

## 3. admin 가시화 — PASS (환경 함정 1건 우회 실증)

- **API**: `GET /admin/file-ingestion/active` JSON 정상(정적 catch-all HTML 아님 — 신코드 가동 증거).
  엔트리 필드 실측: `{filename, table_name, lane:"heavy", status:"PROCESSING", progress:18, processed_rows:18000, total_rows:100000}`. 타 테이블 normal 파일(inventory/metro 수집물)도 lane="normal"로 병기됨.
- **DOM(JS 평가)**: `#sec-active-ingestions` 표시(display:block), 요약 "2 · heavy 1건 포함",
  **HEAVY 배지 = badge-warning / normal 배지 = badge-success**(F4 실값 표기 라이브 확인 — 재라우팅 소형 파일이 "normal · 0% 대기"로 표기),
  행 카운터 "5,000 / 100,000", 경과 표시.
- **재기동 경고 배너**: 섹션 내 "⚠️ 인제션 진행 중 2건 — 지금 서버를 재기동하면 진행 중 파일은 처음부터 재처리됩니다" + 헬스 스트립 File 카드 sub "⚠️ 인제션 진행 중 2건 (heavy 1) — 재기동 시 처음부터 재처리" + Overview 카드에 진행 중 메트릭·이벤트 라인("drill_big_100k.csv → hvy_drill_big (32% · heavy)") 노출.
- **5s 경량 타이머**: 미리보기 pane에서는 `document.hidden=true`라 admin.js가 **의도적으로 갱신 스킵**(admin.js:165, :908 — 백그라운드 탭 절제 설계). visibility 오버라이드 후 실측: **26,000 → 29,000행 / 11s 자동 갱신** — 타이머 로직 자체는 정상.
- **완료 후 자동 소거**: 종료 후 섹션 display:none, API total=0, 헬스 카드 경고 sub 소멸 확인.

## 4. 같은 테이블 순서 보존 — PASS

- heavy 진행 6초 시점(09:10:39.55)에 같은 워크스페이스에 소형 `drill_big_follow.csv`(306B) 투입.
- watcher.log 09:10:41,745: `🐘 Routed to heavy lane queue (workspace-order, 306B)` — **크기 무관, backlog 후미 재라우팅** + `QUEUED lane=normal`(F4 실값).
- **407초 대기** 후 heavy FINISHED(09:17:29,035)와 **5ms 간격**으로 PROCESSING(09:17:29,040) → 09:17:30,142 아카이브.
- FileIngestionLog id 순서 증명: 7359~7361(smalls, 09:10:41~46) → **7378(drill_big_100k, 09:17:29.02) → 7379(drill_big_follow, 09:17:30.14)** — 같은 워크스페이스 FIFO 완전 보존.
- DB: FOLLOW% 8행 전부 존재, hvy_drill_big 총 100,008행, bk 중복 0.

## 5. heavy 도중 재기동 멱등 수렴 — **미실행 (총괄 지시), 계획만**

실행 계획(총괄·사용자 협의 후):
1. `hvy_drill_big` raws/에 대형 파일 재투입(기존 아카이브 재사용 가능 — 동일 bk라 멱등 수렴 검증에 오히려 적합). 사전에 `SELECT COUNT(*)` 기준값 기록.
2. active API로 진행률 30~50% 확인 시점에 **사용자가 watcher 프로세스 재기동** (admin 배너가 사전 경고를 표시하는지 함께 확인).
3. 재기동 직후: 부분 업서트 행수 기록(`COUNT(*)` — 절단 시점 스냅샷), raws/ 파일 잔류 확인(archives 이동 전이어야 함).
4. 스윕 캐치업 관찰: watcher.log에서 스윕이 해당 파일을 **다시 heavy로 라우팅**하는지(`Routed to heavy lane queue (size, ...)` 재출현 — 스윕 경로 라우팅의 라이브 실증 겸함).
5. 수렴 판정: 최종 `COUNT(*) == 100,000` + `GROUP BY business_key_val HAVING COUNT(*)>1` 0건(중복/유실 0) + FileIngestionLog SUCCESS 기록 + 처리 중 고아 엔트리가 레지스트리 TTL/재처리로 소거되는지.
6. 리스크 관리: auto_update 수집 주기(매 분)와 겹치는 시간대 피할 것. 실패 시 err/ 이동 여부와 PENDING_RETRY 경로 관찰.

## 6. created_logs 절단 + 이벤트 루프 동결 부재 — PASS (관찰 2건)

- **WS 실수신 실측**(ws://127.0.0.1:8080/ws 직접 구독): 대형 파일 완료 시 `batch_refresh_required`
  페이로드 = `created_logs` **정확히 500건 절단**, `change_count=500,000`, **페이로드 284,608B(278KB)** —
  절단 전이라면 수백 MB급이었을 것. 2026-07-25 인시던트 회귀 없음.
- **chain_worker.log [Latency]**: heavy 처리 창(09:10~09:17) 내 전 tx `ok=True`,
  notify **15~32ms**(두 자릿수), total 47~109ms. 오류·재시도 0.
- **:8080 이벤트 루프**: 드릴 전 구간 0.25s 간격 **1,614회** 폴링 — 오류 0,
  **p50 3.5ms / p95 26.0ms / p99 28.5ms / max 845.5ms**. >100ms 11건(0.68%), >500ms 2건, 모두 단발
  (연속 스파이크·초 단위 동결 없음). 278KB 브로드캐스트 직후에도 336ms 1회뿐.

## 확인된 결함

1. **[낮음] QUEUED/PROCESSING 통지 발신 역전 경합** · `server/parsers/directory_watcher.py:613,623,641`
   - 시나리오: `_submit_to_heavy_lane`이 **큐 제출(613행) 후에 QUEUED 통지(623행)**를 보낸다. 큐가 비어 있으면 heavy 워커가 즉시 잡을 집어 PROCESSING 통지(641행)를 먼저 발신 → 레지스트리에 PROCESSING이 QUEUED로 **역행 덮어쓰기**(ingestion_activity.py:87은 무조건 대입).
   - 라이브 실증: watcher.log 09:10:34,595에 PROCESSING이 QUEUED보다 **먼저** 찍힘. active API는 첫 진행 이벤트(1%, ~5초 후)까지 실제 처리 중인 파일을 QUEUED로 표시.
   - 영향: 표시 전용(무결성 무관). 진행 통지 간격이 긴 파서에서는 오표시 창이 길어질 수 있음.
   - 권장: QUEUED 통지를 `submit()` **앞**으로 이동(1줄), 또는 `apply_state`에 상태 단조 가드(QUEUED가 PROCESSING을 덮지 못하게).

## 반증 시도했으나 안전한 항목

- **교차 워크스페이스 오염**: heavy 6분 56초 동안 타 테이블 4종(hvy_drill_small + inventory/metro 자동 수집) 전부 초 단위 완료 — HOL 재현 실패(=격리 성립).
- **순서 역전**: 후속 소형 파일이 heavy를 추월하는 시나리오 — workspace-order 재라우팅으로 차단됨을 로그+FileIngestionLog id로 실증.
- **부분 실패/중복 업서트**: 100배치 커밋 후 row_count 정확 일치·bk 중복 0 — 배치 경계 오염 없음.
- **대형 페이로드 재발**: WS 실수신 284KB — 절단 동작 실증. 구독 클라이언트 2개 존재 상태에서 broadcast 지연 없음.
- **온보딩 중 트랜잭션 오염**: reload-configs 직후 기존 테이블(inventory 등) 수집이 09:07~09:17 내내 정상 지속 — 기동 마이그레이션/핫스왑 부작용 없음.

## 런타임 검증 필요 (이번 드릴로 단정 불가)

- **:8080 지터 원인**(0.68% 샘플 100~846ms): 동결은 아니나 발생원(작업 스레드풀 포화? Windows 스케줄링? DB 커넥션 경합?) 미규명. 장기 프로파일링은 별도 태스크 권장.
- **항목 5 전체**(재기동 멱등 수렴) — §5 계획으로 이관.
- **heavy 2개 동시 유입 시 heavy 간 직렬화 대기 체감**(escalation §6-3) — 이번 드릴 범위 밖.

## 문서 정합

- `docs/architecture/CODE_MAP.md`에 "heavy" 관련 심볼 **0건**(grep 실측) — 커밋 4fd8ac9의 HeavyIngestionLane/ingestion_activity.py/신규 엔드포인트 2종 미반영. doc-keeper 반영 필요(구현 보고서 §7 히스토리 초안 존재).
- 구현 보고서(Server_large_file_p1_report.md)의 주장 대조: 임계 기본 10MB·파일 경계 핫리로드·순서 보존·F1/F3/F4 반영·WS 계약 불변 — **전부 실측과 일치**. 과장 없음.
- 관찰(정보성): watcher-직행 경로의 WS `batch_refresh_required` 페이로드에는 `total_log_count`가 **포함되지 않는다**(main.py:3432-3442가 msg를 재구성하며 누락 — 체인 경로 3485는 passthrough로 포함). 서버측 audit_cache에는 actual_count 정상 반영(3446), client2/src는 이 필드를 소비하지 않아 실해 없음. 다만 "클라이언트가 절단 여부를 판별할 수 없는" 비대칭이므로 경계 계약 문서화 시 명시 권장.

## 7. 드릴 생성물 정리 목록 (삭제하지 않음 — 총괄 수행)

| # | 생성물 | 위치/식별 |
|---|---|---|
| 1 | config 항목 2건 `hvy_drill_big`, `hvy_drill_small` | `server/config/table_config.json` (드릴 전 원본 백업: 스크래치패드 `table_config.backup_before_drill.json`) |
| 2 | 물리 테이블 `hvy_drill_big`(100,008행), `hvy_drill_small`(24행) | PostgreSQL (config 항목 제거만으로는 자동 DROP되지 않음) |
| 3 | 워크스페이스 2식 | `server/ingestion_workspace/hvy_drill_big/`, `hvy_drill_small/` — archives에 drill_big_100k.csv(15.6MB), drill_big_follow.csv, drill_small_1~3.csv |
| 4 | FileIngestionLog 행 | id **7359, 7360, 7361, 7378, 7379** |
| 5 | 감사 로그(created_logs) 및 그래프 동기화 산출물 | hvy_drill_* 대상 audit 이력·(그래프 워커가 동기화했다면) 노드 — 총괄 판단 |

## 교훈 제안 (qa-reviewer.md 반영 후보)

- **함정**: 미리보기 pane은 `document.hidden=true`라 visibility-gated 자동 갱신(admin 5s/30s 타이머)이 전부 스킵되어 "타이머 미작동"으로 오판한다.
  **올바른 방법**: `Object.defineProperty(Document.prototype,'hidden',{get:()=>false})` 오버라이드 후 탭 재진입으로 타이머를 재점화해 실측한다.
- **함정**: WS 페이로드 검증을 server.log의 Broadcasting 라인으로 하면 로그 절단(~100자) 때문에 필드 존재/크기를 단정할 수 없다.
  **올바른 방법**: conda 환경의 `websockets`로 `ws://127.0.0.1:8080/ws`를 직접 구독해 실페이로드(크기·필드)를 수집한다.
