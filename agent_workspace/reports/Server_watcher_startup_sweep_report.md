# Server 보고서 — 워처 기동 스윕 (raws/ 기존 파일 미처리 결함 수정)

- 담당: server-pm (worktree 격리: `worktree-agent-a93e815a4d00b5c6a`)
- 대상 결함: `parsers/directory_watcher.py`가 watchdog 이벤트 전용이라 워처 다운타임 중
  raws/에 도착한 파일이 영영 미처리(FileIngestionLog 기록조차 없음)로 방치됨.
  라이브 잔류: 7개 워크스페이스 36개 파일(최고 7/17자).

## 1. 변경 요약

### `server/parsers/directory_watcher.py` (유일한 코드 변경 파일)

| 항목 | 내용 |
|---|---|
| 기동 스윕 | `WorkspaceWatcher.start()`가 observer 기동 **후** `sweep_existing_files_async()` 킥 (~L955). observer 선기동이라 스윕 중 새 이벤트도 유실 없음. 임베디드(`main.py` `start(blocking=False)`)·decoupled(`run_watcher.py` `start(blocking=True)`) 양쪽 모두 `start()`를 경유하므로 **entry 파일 수정 불필요** |
| 런타임 등록 스윕 | `sync_new_workspaces()`가 신규 등록 raws/ 절대경로만 모아 `_ensure_observer_running()` 직후 비동기 스윕 (~L815). `/admin/reload-configs` 응답을 파일 처리가 블로킹하지 않도록 데몬 스레드 |
| 스윕 본체 | `sweep_existing_files(raw_paths=None)` (~L845): `handlers_by_raw_path` 레지스트리(등록 시 저장)로 핸들러 획득 → raws/ **직속 파일만** 열거(`os.path.isfile`, 하위 dir 제외 = observer `recursive=False`와 동일 범위; err/·archives/는 형제 폴더라 원천 제외) → **전역 mtime 오름차순** 정렬 → `IngestionHandler._handle_event()` 재사용. 디바운스·재시도·아카이브/에러 이동·FileIngestionLog 기록·WS 콜백 전부 기존 이벤트 경로와 동일 의미론 |
| 주기 안전망 (채택) | `_periodic_sweep_loop` — `PERIODIC_SWEEP_INTERVAL_SECONDS = 300` 간격 데몬 재스캔 (~L921). 채택 근거: 비용은 워크스페이스당 listdir 1회로 무시 가능, 업서트 멱등이라 중복 무해. **무한 재시도 루프 차단**: 스윕은 path→`(mtime, size)` 시그니처를 기록하고 동일 시그니처는 재시도하지 않음(처리 실패로 raws/에 잔류한 파일은 1회만 시도, 파일 갱신 시 재시도). 처리되어 사라진 파일 시그니처는 다음 스윕에서 정리(무한 성장 방지). err/는 애초에 열거 대상 아님 |
| 이중 처리 가드 | 기존 `processing_files` set은 있었으나 멤버십 검사→add가 **비원자**(사이에 로깅·업로더 추출 존재) — `IngestionHandler._processing_lock`으로 check-then-add 원자화 (~L204). 스윕 스레드 vs watchdog 스레드 동시 진입 시 정확히 1회 처리. 성공 처리 후 파일이 아카이브로 이동하므로 지연 이벤트는 `os.path.exists` 게이트에서 자연 소멸 |
| 수명 관리 | `stop()`이 `_stop_event` set → 진행 중 스윕은 파일 단위로 조기 종료, 주기 스레드 종료. 스윕 스레드는 전부 daemon이라 프로세스 종료에 안전 |

### `server/tests/test_watcher_startup_sweep.py` (신규, 6 테스트)

1. 기동 전 존재 파일 처리 — 전역 mtime 오름차순, err/·archives/·raws 하위 dir 제외, 동일 시그니처 재스윕 0건
2. `start()`가 observer 기동 **후** 전체 raws 대상 비동기 스윕 킥
3. `sync_new_workspaces()`가 **신규 등록 raws만** 스윕(기존 워크스페이스 재스윕 안 함)
4. 이중 처리 가드 — 동일 파일 2-스레드 동시 `_handle_event` → 정확히 1회 처리 + set 정리
5. 시그니처 가드 — 잔류 파일 재시도 차단, mtime 변경 시에만 재시도 허용
6. 주기 스윕 반복 실행 + `_ensure_periodic_sweep_running` 멱등 + stop 신호 종료

테이블명은 교훈 파일 규칙대로 사용자 config와 충돌 불가능한 `sweeptest_*` 접두 사용.

### `docs/architecture/CODE_MAP.md` — §3 신규 시그니처·라인 갱신 (watcher 섹션만 접촉)

## 2. 검증

- 신규 스위트: `test_watcher_startup_sweep.py` 6/6 PASS.
- 전체 스위트: `conda run -n assy_manager python -m pytest server/tests/ -q`
  → **5 failed, 121 passed** — 5건 전부 **베이스라인(변경 stash 후 재실행)에서도 동일하게 실패**함을 실증. 즉 본 변경으로 인한 회귀 0건, 신규 통과 +6.
- 경계 계약 불변: REST/WS 이벤트·페이로드·셀 형태·스키마 계약 일절 미접촉. 스윕은 기존 처리 경로를 그대로 호출하므로 콜백 페이로드 형태 동일.

### 미해결(기존 결함, 본 작업 무관 — 총괄 확인 요망)

전체 스위트 기준 pre-existing 실패 5건 (파일 단독 실행에서도 재현되는 것 포함):
`test_map_presets_api`(기허용), `test_composite_business_key_ingestion`,
`test_chained_ingestion`, `test_file_ingestion_callback_direct`,
`test_watcher_created_logs_capped_at_500`.
`test_composite_business_key_ingestion`은 단독 실행에서도 실패 — 교훈 파일의 `bonding_log`
사례와 동일 클래스(테스트 픽스처 테이블명 `bonding_map_test`가 사용자 config의 실 테이블과
간섭) 가능성이 높음. 별도 태스크 권고.

## 3. 라이브 잔류 36개 파일 자동 처리 검증 절차 (실행: 총괄, 병합·재기동 후)

1. **사전 스냅샷**: 재기동 전 각 워크스페이스 `ingestion_workspace/*/raws/` 직속 파일 목록·개수 기록
   (PowerShell: `Get-ChildItem server\ingestion_workspace\*\raws\* -File | Select FullName, LastWriteTime`). 기대: 36개.
2. **재기동**: 워처 프로세스(decoupled `run_watcher.py` 또는 임베디드 웹서버) 재기동.
3. **로그 확인**: `watcher.log`에서
   - `Started observer with N watches.` 이후 `New file detected:` 가 잔류 파일들에 대해 mtime 오름차순으로 발생
   - 완료 시 `🧹 Sweep: attempted 36 pre-existing file(s) in raws/.` (일부가 처리 실패면 err/ 이동 로그와 함께 수치 동일 — "시도" 카운트)
4. **파일 이동 확인**: raws/ 직속이 비고(또는 파싱 실패 파일만 err/로 이동), 성공분은 archives/에 존재.
   bonding_map의 7/17자 파일이 archives/로 이동했는지 명시 확인.
5. **DB 확인**: `FileIngestionLog`에 36건의 신규 행(SUCCESS 또는 FAILED) 존재 — 이제 실패분은 admin 재시도 UI로 잡힌다. 대상 테이블 행 수 증가 및 클라이언트 `file_ingestion_completed` 수신 확인.
6. **안전망 확인(선택)**: 워처를 잠시 내리고 raws/에 테스트 파일 1개 배치 → 재기동 없이 5분 대기 시 주기 스윕이 처리하는지(주기 안전망), 재기동 시 즉시 처리되는지(기동 스윕) 각각 확인.
7. **중복 없음 확인**: 대상 테이블에서 business_key 중복 행이 생기지 않았는지 스팟 체크(업서트 멱등이라 기대상 무해).

## 4. 히스토리 초안 (통합 시 총괄 기록용)

> fix(watcher): 기동/런타임 등록/주기(300s) raws/ 잔류 파일 스윕 추가 — watchdog 이벤트 유실·다운타임 중 도착 파일이 영영 미처리되던 결함 해소. 기존 `_handle_event` 경로 재사용(mtime 오름차순, err/ 제외), (mtime,size) 시그니처로 무한 재시도 차단, processing_files check-then-add 락 원자화(이중 처리 가드). 테스트 6건 신규(`test_watcher_startup_sweep.py`), 회귀 0.

## 5. 교훈 제안 (server-pm.md 반영은 총괄 검수 후)

- **함정**: 전체 스위트의 실패가 자기 변경 탓처럼 보여도, 사용자 config(gitignored) 실 테이블과의
  간섭으로 인한 pre-existing 실패일 수 있다.
  **올바른 방법**: `git stash -u` 후 동일 명령으로 베이스라인을 반드시 재실행해 실패 집합을 diff로 실증.
