# 보고서: 대형 파일 인제션 P2 — 오프셋 체크포인트 재개 + 해시 dedup + 감사 결함 2건

- 작업자: server-pm
- 일시: 2026-07-26
- 브랜치(worktree): `worktree-agent-a4c63f415791a7d0e` — 커밋 `f78ab0a` (단일 커밋)
- 지시서: `agent_workspace/tasks/Server_large_file_p2_task.md`
- **`server/main.py` 수정 없음** (M2와의 충돌 지점 회피 — 설계로 우회, §5 참조)

## 0. 결론

A(체크포인트 재개) / B(해시 dedup) / C(감사 결함 2건) 전부 구현·테스트 완료.
스위트 **278 → 307 passed (+29), 허용 실패 1건(`test_map_presets_api`) 유지**.
라이브 검증은 워처 재기동이 필요하므로 계획만 제시(§8).

---

## 1. 착수 전 상태 정정 (중요)

worktree 브랜치가 **P1 미포함 시점(`9a6abeb`)에서 분기**되어 있었다. `git merge main --ff-only`로
`1c6b8f5`까지 전진시킨 뒤 착수했다(heavy 레인·`ingestion_activity.py`·`test_heavy_lane.py` 포함).
P1 위에 얹지 않았다면 heavy 레인 경로에 체크포인트가 배선되지 않았을 것이다.

또한 worktree에는 gitignored 사용자 자산(`server/config/*.json`, `server/mappers/`)이 없어
기준선이 **274 passed / 5 failed**로 나왔다. 메인 트리에서 복사해 넣은 뒤 **278 passed / 1 failed**로
main과 정확히 일치함을 확인하고 그 값을 기준선으로 삼았다(복사물은 gitignored라 커밋에 미포함,
tracked였던 `server/mappers/production_mapper.py.sample`은 즉시 원복).

---

## 2. A. 오프셋 체크포인트 재개

### 2.1 저장소 결정 — FileIngestionLog 컬럼 추가를 채택하지 않은 근거

지시서 권장안은 `FileIngestionLog`에 컬럼 추가였으나 **신규 시스템 테이블
`file_ingestion_checkpoints`**를 채택했다. 근거 3가지:

1. **마이그레이션 순서 의존 위험**: `models.Base.metadata.create_all`(main.py:44)은 **기존 테이블에
   컬럼을 추가하지 않는다**. 운영 DB에 이미 존재하는 `file_ingestion_logs`에 컬럼을 늘리면 별도 ALTER가
   *모든 조회 프로세스보다 먼저* 돌아야 하고, 그 전에 웹서버가 SELECT하면 admin File 탭이
   UndefinedColumn 500으로 죽는다. 신규 테이블 CREATE는 그 순서 의존이 없다(존재 게이트 + checkfirst).
2. **수명·의미론 불일치**: `file_ingestion_logs`는 시도(attempt)마다 append되는 **이력**이고,
   체크포인트는 (테이블, 파일내용)당 **단일 최신 상태**다. 후자에 필요한
   `UNIQUE(table_name, file_signature)`는 전자의 append 의미론과 양립할 수 없다.
3. **핫패스 쓰기**: 체크포인트는 1,000행마다 UPDATE된다. 이력 테이블을 매 청크 UPDATE하면
   append-only 계약이 깨지고 이력 테이블의 인덱스·WAL 부담이 커진다.

**단, 지시서의 실질 요구("재개/스킵 사실을 FileIngestionLog에 명시")는 충족한다** — 사유 문장을
`FileIngestionLog.error_message`(= main.py:3517이 이미 문서화한 SUCCESS detail 슬롯)에 기록한다.

### 2.2 스키마 (`server/database/models.py` — `FileIngestionCheckpoint`)

| 컬럼 | 용도 |
|---|---|
| `table_name`, `file_signature` | UNIQUE 복합 인덱스 `idx_fic_identity` — 재개·dedup 단일 조회 키 |
| `source_kind` | 파서 정체성(`"std"` / `"pipeline:<파일>::<클래스>"`) — 재개 가부 판정 |
| `total_rows`, `processed_rows`, `chunk_index` | 재개 오프셋(=커밋 완료 행 수) |
| `status` | `IN_PROGRESS`(재개 대상) / `DONE`(dedup 대상) |
| `note`, `started_at`, `updated_at` | 사유·시각 |

[확장성] 파일 1건당 1행 — 1,000만 행 데이터에서도 이 테이블은 "처리한 파일 수" 규모로만 자란다.
조회는 UNIQUE 인덱스 단일 히트(풀스캔·큰 OFFSET 없음).

### 2.3 기록 시점 — 지시서보다 강한 보장(원자성)

지시서는 "청크 커밋 **직후**"를 요구했다. 실제로는 **같은 트랜잭션**에 실었다:

```python
# server/parsers/directory_watcher.py  _send_to_upsert
if checkpoint is not None:
    ingestion_checkpoint.record_chunk_progress(db, checkpoint, processed_rows + len(chunk), chunk_index)
results, changed_cells, created_logs, deleted_row_ids = crud.apply_batch_updates(db, t_name, batch_obj)
db.commit()
```

`crud.apply_batch_updates`가 **내부에서 `db.commit()`을 수행**하므로,
호출 *이전*에 같은 세션으로 UPDATE를 발행해야 한 번의 커밋으로 함께 확정된다.
호출 이후에 쓰면 별도 트랜잭션이 되어 두 커밋 사이 크래시 시 "데이터는 들어갔는데 오프셋은 안 오른"
창이 생긴다(업서트 멱등성 덕에 유실이 아니라 재적재로만 열화되지만 원자성이 더 낫다).
`before_flush` outbox 리스너는 `DYNAMIC_TABLES` 인스턴스만 처리하므로 Core UPDATE는 outbox를 오염시키지 않는다.

**테스트로 실증**: `test_crash_mid_file_keeps_committed_offset_then_resumes` — 1,500행(2청크) 파일의
2번째 청크에서 크래시를 주입 → 커밋 1,000행 / 기록 오프셋 정확히 1,000 / 재투입 시 **남은 500행만** 적재.

### 2.4 재개 가부 판정 (조용한 폴백 금지)

`ingestion_checkpoint.plan_ingestion`이 다음 전부를 만족할 때만 재개한다:
시그니처 일치(테이블 스코프) · `total_rows` 일치 · `source_kind` 일치 · `0 ≤ processed_rows ≤ total_rows`.

하나라도 어긋나면 **오프셋 0부터 재처리하되 사유를 3곳에 남긴다**:
`logger.warning` + `FileIngestionLog.error_message` + 완료 통지 detail.

```
[resume]        이전 실행의 체크포인트 12,000행에서 재개 (총 99,999행, chunk_index=12)
[resume-abort]  체크포인트를 사용할 수 없어 처음부터 재처리 — 사유: 총 행 수 불일치(99999 → 50000) (기록된 오프셋 12000행은 폐기)
[checkpoint-off] 체크포인트 기록 실패로 처음부터 적재 (사유: ...)   ← DB 장애 등 인프라 실패
```

### 2.5 멱등성 실증 (지시서 A-3)

`test_resume_is_idempotent_no_duplicate_rows`: 7행 파일을 전량 적재 후 오프셋을 **3 / 0**으로 인위 조작해
두 번 재개. 매번 `행 수 == 7`, `len(set(bk)) == len(bk)`(중복 0).
추가로 `test_crash_mid_file_...`에서 1,500행 규모로도 bk 중복 0을 확인했다.

### 2.6 전 경로 동일 동작 (지시서 A-4)

체크포인트/dedup은 `process_with_retry` 한 지점에 배선되어 있고, 아래 경로가 전부 그 함수로 수렴한다.

| 경로 | 진입 | 테스트 |
|---|---|---|
| normal 레인(인라인) | `_handle_event → _route_and_process → process_with_retry` | 대부분의 신규 테스트 |
| heavy 레인 | `_submit_to_heavy_lane → _run_lane_job → process_with_retry` | `test_checkpoint_applies_on_heavy_lane_path` |
| 스윕(기동/주기/런타임등록) | `sweep_existing_files → _handle_event` | `test_checkpoint_applies_on_sweep_path` |
| 관리자 재시도 | `process_archived_file_sync` (별도 배선) | `test_admin_retry_path_bypasses_dedup_and_reingests` |

관리자 재시도만 의미론이 다르다: **dedup skip 미적용**(명시적 재처리 의사)이되
`IN_PROGRESS`(중단됨)면 이어받고 `DONE`(이미 완료)이면 0부터 전량 재적재한다.

---

## 3. B. 파일 해시 dedup

### 3.1 시그니처 방식 결정 — 비용 실측 근거

형식: `sha256:<size_bytes>:<hexdigest>`. **전체 내용 해시**를 채택했다.
실측(본 워크스테이션, 1MB 청크 스트리밍, 2회 중 최소값):

| 파일 크기 | sha256 전체 | blake2b 전체 | 선두/말미 1MB 샘플링 |
|---|---|---|---|
| 16MB | **0.016s** | 0.032s | 0.004s |
| 100MB | **0.101s** | 0.212s | 0.005s |
| 500MB | **0.535s** | 1.147s | 0.005s |

- sha256이 blake2b보다 **2배 빠르다**(CPU SHA 확장 명령, ~935MB/s) — "blake2b가 더 빠르다"는 통념은 이 환경에서 반증됨.
- P1 라이브 드릴 실측 기준 15.6MB 파일의 총 처리 시간은 **415초**인데 전체 해시는 **16ms = 0.004%**.
  500MB 파일이라도 0.5초. **비용이 무시 가능하므로 정확성을 택했다.**
- 샘플링은 더 빠르지만 **중간만 바뀐 파일을 같은 파일로 오판**한다. 그 오판의 결과는
  (a) 재개 오프셋 오적용 → 실제 유실, (b) dedup 오스킵 → 데이터 미적재. 둘 다 무음 데이터 사고다.
  0.5초를 아끼려고 감수할 리스크가 아니다.

### 3.2 skip 동작 (무음 skip 금지)

동일 `(table_name, file_signature)`가 `DONE`이면:
1. `logger.warning`에 사유 기록
2. 파일을 `archives/`로 이동 (스윕이 같은 파일을 무한 재픽업하지 않도록)
3. `FileIngestionLog(status="SKIPPED", error_message=<사유 전문>)` 기록
4. 완료 콜백 통지 — **status는 `"SUCCESS"`**, detail에 사유

> **status 비대칭의 이유**: 수신부(`main.py:3515`, 임베디드 `main.py:207`)는 `status == "SUCCESS"` 외
> 전부를 "파일 처리에 **실패**했습니다"로 렌더링한다. 스킵을 `"SKIPPED"`로 보내면 실패로 오표기된다.
> main.py를 못 건드리는 제약(M2 병행) 하에서 "실패 아님"을 정확히 전달하려면 SUCCESS + detail이 유일한 선택.
> DB 이력에는 정직하게 `SKIPPED`로 남는다.

dedup은 **테이블 스코프**다(같은 내용이라도 대상 테이블이 다르면 스킵하지 않음 —
`test_dedup_is_scoped_per_table`).

### 3.3 강제 재처리 경로 (지시서 B-6)

| 경로 | 방법 | 테스트 |
|---|---|---|
| 파일 단위 | 파일명에 `__force__` 포함 (예: `report__force__.csv`, 대소문자 무시) | `test_force_token_in_filename_bypasses_dedup` |
| 전역 | `ingestion_settings.json`의 `"dedup_by_signature": false` | `test_dedup_can_be_disabled_globally` |
| 개별 이력 | admin File 탭 Retry(FAILED 로그) → `process_archived_file_sync` | `test_admin_retry_path_bypasses_dedup_and_reingests` |

`__force__` 파일은 dedup만 우회하는 것이 아니라 잔여 오프셋도 이어받지 않는다(0부터 전량 재적재).
`resume_from_checkpoint: false`(전역)로 재개 자체를 끌 수도 있다.
두 설정 모두 `ingestion_settings.json.sample`에 문서화했다.

---

## 4. C. 감사 결함 2건

### 4.1 이슈 #10 — `audit_cache` total_count 과소 표기 (QA D-1)

**같은 tx id로 메시지가 2회 이상 도착하는 경로 전수 확인 결과** (지시서 요구):

| 발신 경로 | 같은 tx로 N회 도착? | 조치 |
|---|---|---|
| 체인 워커 target_table 루프 (`chain_ingestion_worker.py`) | **예** — 한 소스 tx가 여러 target 룰 트리거 → `chain_{tx}` 하나로 target 수만큼 broadcast | 누적으로 해소 |
| 워처 파일 인제션 (`run_watcher.trigger_ws_refresh`) | 아니오 — 파일당 `file_tx_id` 유일, 통지 1회 | 신·구 의미론 동일 |
| `crud.*` 내부 5개 호출부 | override 미전달 → 종전과 동일하게 `len(logs)` 누적 | 무변경 |
| 체인 워커 복구 스윕 (`sweep_undelivered_broadcasts`) | 재전송은 있으나 **`created_logs` 미동봉**(table-level refresh만) → `add_logs_batch` 미호출 | 중복 가산 없음 |
| 체인 워커 mapper 재시도(RETRYING) | 실패 그룹은 rollback되어 **broadcast 자체를 안 함** | 중복 가산 없음 |
| 임베디드 모드 `trigger_ws_refresh`(main.py:178) | `add_logs_batch` 호출 없음(브로드캐스트만) | 이중 가산 없음 |

→ **의미론 확정: 누적(+=)**. 파라미터를 `override_total_count` → **`message_total_count`**로 개명
(이름이 SET을 암시해 오해를 유발했음). 전 호출부가 위치 인자이므로 파급 없음
(gitignored `server/config/`·`ingestion_workspace/`·`mappers/`·`client2/` 전수 grep 0건 확인).

방어 추가: 한 메시지에 **여러 tx가 섞이면** 기여분 귀속 근거가 없으므로 `message_total_count`를
적용하지 않고 그룹별 `len(logs)`로 폴백 + 1회 경고(현행 발신 경로는 메시지당 단일 tx).

재발 방지: "발신 경로를 추가할 때는 '같은 tx로 같은 로그가 두 번 오는가'를 먼저 확인할 것"을
docstring에 못박았다.

### 4.2 audit `old_value`/`new_value` 길이 무제한

- 상한 `MAX_AUDIT_VALUE_CHARS = 4096`을 **`server/event_constants.py` 단일 정의**로 신설
  (`MAX_NOTIFY_CREATED_LOGS`와 같은 위치 — 상수 분산 금지 교훈).
- `crud.create_audit_log`에서 `sanitize_to_utf8` 직후 적용. **DB 저장본과 통지 dict에 동일 적용**.
- **조용한 절단 금지**: 문자열은 `…[truncated: 총 N자]`로 원래 길이를 값 안에 남기고,
  dict/list는 부분 절단이 구조를 깨므로 `[truncated: dict 값 51234자 — 감사 로그 값 상한 4096자 초과로 본문 생략]`
  플레이스홀더로 대체한다. 숫자/불리언/None은 무변경.
- 경고 로그는 `(table, column)`별 **1회**만 (셀 단위 핫패스라 무조건 로깅하면 대형 파일 1건이
  수십만 줄 WARNING을 쏟는다).

**현행 데이터 영향 실측(읽기 전용 쿼리, `ORDER BY id DESC LIMIT 200000` 서브쿼리로 인덱스 스캔에 한정)**:

```
audit_logs 최근 20만건: max(old_value)=85자, max(new_value)=432자, 4096자 초과 = 0건
wafer_map_metadata.grid_metadata max length = 260자
```

→ **현행 데이터엔 영향이 전혀 없고**, 대형 텍스트 셀이 체인/워처 대상이 되는 미래 리스크만 봉쇄한다
(500건 × 2값 × 4KB = 최악 4MB로 페이로드 상한 고정).
`old_value`/`new_value` 소비처는 **표시 전용**(`client2/src/timeline.js:79,182`, `main.py:1211/1674`)이며
값을 되돌리는(revert) 기능은 없음을 grep으로 확인했다 — 절단이 기능을 깨지 않는다.

---

## 5. `server/main.py` 무수정 달성 방법

| 필요했을 변경 | 우회 방법 |
|---|---|
| 신규 테이블 부팅 생성 | `FileIngestionCheckpoint`를 `Base`에 선언 → 기존 `main.py:44 create_all`이 자동 생성 |
| 워처 프로세스 테이블 보장 | `models.ensure_ingestion_checkpoint_table(engine)` 신설 + `run_watcher.py` 부팅 + `refresh_dynamic_models` 배선 |
| skip 통지 렌더링 | 신규 status 대신 기존 SUCCESS + detail 슬롯 재사용 (§3.2) |
| #10 수정 | `audit_cache.py` 내부 의미론만 변경 (main.py는 위치 인자 호출이라 무변경) |

재기동 없이 테이블만 미리 만들고 싶을 때를 위해 멱등 스크립트
`server/scripts/setup_ingestion_checkpoint.py`를 추가했다.

---

## 6. 변경 파일

| 파일 | 내용 |
|---|---|
| `server/ingestion_checkpoint.py` **(신규)** | 시그니처 산출 · 체크포인트 계획/기록/확정 · 설계 근거 docstring |
| `server/database/models.py` | `FileIngestionCheckpoint` 모델 + `ensure_ingestion_checkpoint_table` + `refresh_dynamic_models` 배선 |
| `server/parsers/directory_watcher.py` | dedup skip · 체크포인트 계획/재개 · 청크 오프셋 기록 · `_log_ingestion_record` 통합 · 설정 2종 |
| `server/audit_cache.py` | #10 — SET → 누적, 파라미터 개명, 다중 tx 폴백 |
| `server/database/crud.py` | 감사 값 상한 적용 + (table,column)별 1회 경고 |
| `server/event_constants.py` | `MAX_AUDIT_VALUE_CHARS` + `truncate_audit_value` |
| `server/run_watcher.py` | 부팅 시 체크포인트 테이블 보장 |
| `server/config/ingestion_settings.json.sample` | `dedup_by_signature` · `resume_from_checkpoint` 문서화 |
| `server/scripts/setup_ingestion_checkpoint.py` **(신규)** | 멱등 테이블 생성 스크립트 |
| `server/tests/test_ingestion_checkpoint.py` **(신규)** | 신규 검증 29건 |
| `server/tests/test_std_parser.py` | `_FakeDB`에 체크포인트 조회 스텁 추가(기존 계약 검증 의미 불변) |

---

## 7. 테스트

### 7.1 결과 (전문)

```
기준선(worktree, 사용자 config 주입 후): 1 failed, 278 passed, 13 warnings in 16.29s
P2 적용 후:                              1 failed, 307 passed          in 28.26s
FAILED server/tests/test_api.py::test_map_presets_api   ← 기존 허용 실패(변동 없음)

신규 파일 단독: server/tests/test_ingestion_checkpoint.py — 29 passed in 9.35s
```

### 7.2 신규 29건 (테이블 접두 `p2_test_*` — 사용자 config와 충돌 불가)

- **시그니처(2)**: 내용 기준·이름 무관·결정적 / 읽기 불가 시 None
- **체크포인트·재개(9)**: 성공 후 DONE 기록 / **크래시 후 오프셋 원자성 + 이어받기(1,500행 2청크)** /
  중간 오프셋 재개 시 선두 행 제외 / 재개 사유 3곳 기록 /
  재개 불가 4종(총행수·파서·오프셋 초과·음수) 각각 `[resume-abort]` + 사유 명시 /
  **멱등성(오프셋 3·0 강제 재개, 행 수·bk 중복 0)** / 스윕 경로 / heavy 레인 경로 / 재개 비활성 설정
- **dedup(6)**: 중복 skip + 3곳 명시 기록 + archives 이동 / 테이블 스코프 격리 /
  다른 내용은 미스킵 / `__force__` 우회 / 전역 스위치 우회 / 관리자 재시도 우회
- **#10 total_count(5)**: 멀티 메시지 누적(600+50=650) / 단일 메시지 실건수 /
  override 미전달 폴백 / 다중 tx 폴백 / 500건 캡 유지
- **감사 값 상한(4)**: 문자열 마커·원 길이 보존 / 컨테이너 플레이스홀더 /
  `create_audit_log` 양 값 상한 / 대형 셀 인제션 시 통지 페이로드 유계
- 동시성 검증은 sleep 경합이 아닌 `threading.Event` 기반(heavy 레인).

### 7.3 전수 grep (gitignored 사용자 영역 포함)

`add_logs_batch` / `override_total_count` / `_send_to_upsert` / `_resolve_rows` /
`_discover_and_execute_pipeline` / `_log_ingestion_success` / `process_archived_file_sync`를
`server/`(config·mappers·ingestion_workspace 포함)·`client2/` 전수 검색 —
사용자 영역 참조 0건, `add_logs_batch`는 전부 위치 인자 호출로 개명 파급 없음.

---

## 8. 라이브 검증 계획 (재기동 필요 — 미실행)

라이브 서버 재기동 금지 지시에 따라 아래는 **계획만** 제시한다.

1. **선행(재기동 불필요)**: `conda run -n assy_manager python server/scripts/setup_ingestion_checkpoint.py`
   — 멱등. (※ 이미 존재함 — §9-1 참조)
2. **재기동**: 웹서버 + 워처. (워처만 먼저 띄워도 안전 — 테이블은 이미 있고 웹서버는 이 테이블을 읽지 않음)
3. **드릴 D1 (재개)**: 10만 행 CSV 투입 → 진행률 30~50% 구간에서 **워처만** 강제 종료 → 재기동 →
   워처 로그에서 `⏩ Resumed ingestion: skipped N already-committed row(s)` 확인 →
   완료 후 `count(*)`, `count(DISTINCT business_key_val)`가 100,000으로 일치(유실·중복 0),
   `file_ingestion_checkpoints`가 `DONE`/`processed_rows=100000`인지 확인.
   admin File 탭 SUCCESS 로그의 detail에 `[resume]` 문구가 보이는지 확인.
4. **드릴 D2 (dedup)**: 같은 파일을 다시 투입 → 즉시 skip, `SKIPPED` 로그 + 통지 문구 확인,
   처리 시간이 초 단위인지(재적재 미발생) 확인. 이어서 `xxx__force__.csv`로 재투입해 전량 재적재 확인.
5. **드릴 D3 (#10)**: `production_plan` 편집 tx로 체인 룰 2종(→`inventory_master`, →`line_model_registry`)을
   동시 트리거 → 히스토리 패널 총계가 두 테이블 합계로 표시되는지 확인(종전엔 마지막 메시지 값).
6. **회귀 감시**: P1 드릴과 동일하게 `[Latency] notify=` p50/p95, 이벤트 루프 스파이크 0건 유지 확인.
   체크포인트 UPDATE가 청크당 1회 추가되므로 청크 처리 시간이 유의미하게 늘지 않았는지 대조
   (예상: 1,000행 청크당 UNIQUE 인덱스 단일 UPDATE 1건 → 무시 가능).

---

## 9. 총괄이 알아야 할 사항 · 미해결

1. **라이브 DB에 빈 테이블 `file_ingestion_checkpoints`가 이미 생성되어 있다.**
   테스트 스위트가 `main.py`를 import하면 모듈 레벨 `models.Base.metadata.create_all(bind=engine)`(main.py:44)이
   **실 PostgreSQL**에 대해 실행되는 기존 동작 때문이다(내가 도입한 것이 아님).
   기존 테이블·컬럼은 일절 변경되지 않았고 신규 테이블은 비어 있으므로 무해하나, 인지가 필요하다.
   → 별건 백로그 제안: *pytest가 운영 DB에 DDL을 발행하는 경로 차단(TESTING 환경변수 게이트)*.

2. **client2 후속(경미, client-pm 몫)** — 새 상태 `SKIPPED`에 대한 표현:
   - `client2/src/admin.js:843` — `status === 'SUCCESS' ? badge-success : badge-danger` →
     `SKIPPED`가 **빨간 danger 배지**로 표시된다(라벨은 정확). 중립/경고 톤 권장.
   - 같은 파일 `:844` — 비-SUCCESS면 Retry 버튼이 뜨는데 `/admin/file-ingestion/retry-failed`는
     `status == "FAILED"`만 받으므로 SKIPPED 행의 Retry는 **무동작**이다(죽은 버튼).
     버튼을 숨기거나, 서버 측 retry 대상에 SKIPPED를 포함시키는 판단이 필요
     (후자는 main.py 변경 → 총괄 승인 사항).
   - `/admin/file-ingestion/failed`는 `status == "FAILED"` 정확 일치라 **실패 카운트 오염은 없다**(확인 완료).

3. **정책 판단 필요**: 감사 값 상한을 **DB 저장본에도** 적용했다(통지 페이로드만 자르는 안 대비).
   근거는 [확장성 최우선] — `audit_logs`는 1,000만 행 목표 테이블이라 무제한 텍스트 저장이 그 자체로 리스크이고,
   소비처가 표시 전용이라 기능 손실이 없다. **"이력 원본 보존이 더 중요하다"는 판단이면 되돌릴 수 있다**
   (`crud.create_audit_log`에서 `log_dict`만 자르고 ORM `models.AuditLog`에는 원본을 넣으면 됨).

4. **보존 정책 미구현(P3 제안)**: `file_ingestion_checkpoints`의 `DONE` 행은 dedup 원장이라
   영구 누적된다. 파일 수 기준이라 증가 속도는 느리지만, outbox처럼 보관 기간(예: 180일) purge를
   넣을지 판단이 필요하다. purge하면 그만큼 오래된 파일의 dedup이 풀린다(재적재 = 업서트라 무해).

5. **heavy 레인 dedup 타이밍(저순위)**: 중복 파일이라도 크기 임계를 넘으면 일단 heavy 큐에 들어간 뒤
   워커 스레드에서 skip된다(라우팅 시점에는 해시를 계산하지 않음). 큐 점유는 수백 ms 수준이라
   현재는 문제 없으나, 중복 대형 파일이 반복 투입되는 운영이면 라우팅 전 dedup을 검토할 수 있다.

6. **경계 계약 무변경 확인**: REST 시그니처/경로, WS 이벤트명·페이로드, 셀 형태
   `{value, is_overwrite, priority_source}`, `table_config.json`→`/schema` 스키마 계약 전부 불변.
   추가된 것은 **내부 시스템 테이블 1개**와 `ingestion_settings.json`의 선택 필드 2개뿐이다.

---

## 10. 히스토리 초안 (doc-keeper/총괄용 — 본인은 문서를 수정하지 않음)

```
# feat(ingestion): 대형 파일 P2 — 오프셋 체크포인트 재개 + 해시 dedup + 감사 결함 2건

- 일시: 2026-07-26 / 커밋: f78ab0a / 작업자: server-pm
- 배경: P1(heavy 레인)까지도 진행 오프셋을 남기지 않아 재기동 시 99,999행(≈7분)이 통째로 소실.
  동일 파일 재투입 방어도 없었다.
- 변경:
  1) 신규 시스템 테이블 file_ingestion_checkpoints — UNIQUE(table_name, file_signature).
     오프셋은 청크 upsert와 같은 트랜잭션에 실려 원자 커밋(apply_batch_updates 내부 commit 동승).
  2) 시그니처 sha256:<size>:<digest> 전체 해시 — 500MB 0.535s(~935MB/s), 15.6MB 0.016s로
     라이브 드릴 총 처리 415s의 0.004%. 샘플링의 오판 리스크 대비 정확성 채택(실측 근거).
  3) 재개 가부는 시그니처+총행수+파서 정체성+오프셋 범위 전부 일치 시에만. 불일치는 0부터 재처리하되
     사유를 로그·FileIngestionLog·완료 통지 3곳에 명시(조용한 폴백 금지).
  4) 동일 시그니처 DONE이면 skip + archives 이동 + FileIngestionLog(status=SKIPPED).
     강제 재처리 3경로(__force__ 파일명 / dedup_by_signature=false / 관리자 재시도).
  5) 이슈 #10 — audit_cache.add_logs_batch의 override_total_count(SET) → message_total_count(누적).
     멀티 target-table tx 총계 과소 표기 제거. 재전송 경로 전수 확인 후 확정.
  6) 감사 값 4096자 상한 + 절단 마커(event_constants 단일 정의). 실측상 현행 최대 432자 — 미래 리스크만 봉쇄.
- 아키텍처 영향: 인제션에 durable 진행 상태가 추가(신규 시스템 테이블 1개).
  REST/WS 경계 계약·셀 형태·스키마 계약 전부 불변. main.py 무수정.
- 테스트: 278 → 307 passed(+29), 허용 실패 1건 유지.
- 다음: P3(outbox backpressure · PG COPY 벌크 · heavy 워커 수 설정화) + 라이브 재개/dedup 드릴.
```

리빙 문서 갱신 필요 지점(참고): `docs/architecture/data_model.md`(신규 테이블),
`docs/architecture/backend.md`·`docs/guide/INGESTION_GUIDE.md`(재개/dedup 동작·설정 2종·`__force__` 규약),
`docs/architecture/CODE_MAP.md`(`server/ingestion_checkpoint.py` 신규 · directory_watcher 신규 메서드),
`docs/spec/FAILURE_MANAGEMENT_SPEC.md`(FileIngestionLog의 새 status `SKIPPED`).

---

## 11. 교훈 제안 (`agent_workspace/memory/server-pm.md` 반영 검토 — 직접 추가하지 않음)

1. **함정**: worktree 브랜치가 최신 main보다 뒤에서 분기되어 있으면, 방금 병합된 선행 단계(P1) 위가
   아니라 그 이전 코드 위에 얹게 된다 — 테스트는 통과하는데 신규 경로(heavy 레인 등)에 배선이 누락된다.
   **올바른 방법**: 착수 즉시 `git log --oneline -3 main` vs `HEAD`를 대조하고 필요하면 `merge main --ff-only`.

2. **함정**: worktree에는 gitignored 사용자 자산(`server/config/*.json`, `server/mappers/`)이 없어
   기준선 테스트 수치가 main과 다르게 나온다(실측 274 vs 278) — 이를 "내가 깨뜨렸다"로 오진하기 쉽다.
   **올바른 방법**: 기준선 측정 전에 사용자 자산을 메인 트리에서 복사해 넣고, tracked 파일이 함께
   덮어써지지 않았는지 `git status`로 확인한다.

3. **함정**: "청크 커밋 직후 오프셋 기록"을 코드 순서 그대로 구현하면, `crud.apply_batch_updates`가
   **내부에서 이미 commit**하기 때문에 별도 트랜잭션이 되어 원자성이 깨진다.
   **올바른 방법**: 공용 CRUD 함수를 쓸 때는 그 함수가 커밋을 소유하는지 먼저 확인하고,
   같이 커밋해야 할 부수 기록은 **호출 이전**에 같은 세션으로 발행한다.

4. **함정**: 진행/스킵 같은 새 상태를 `file-processed` 통지의 status로 실으면, 수신부가
   `status == "SUCCESS"` 외 전부를 "처리 실패"로 렌더링해 정상 동작이 실패로 오표기된다.
   **올바른 방법**: 수신부를 못 고치는 상황이면 status는 기존 값으로 두고 detail 슬롯에 사유를 싣되,
   DB 이력에는 정확한 상태를 남겨 둘을 분리한다(그리고 클라이언트 후속을 보고서에 명시).

5. **함정**: 상한·절단 같은 "안전 장치"를 넣을 때 그 값이 현행 데이터에 실제로 걸리는지 재보지 않으면,
   기능 손상 여부를 근거 없이 주장하게 된다.
   **올바른 방법**: 도입 전 읽기 전용 쿼리로 분포를 실측한다(예: 최근 20만 건 max length).
   전량 스캔 대신 `ORDER BY id DESC LIMIT N` 서브쿼리로 인덱스 스캔에 가둔다.

6. **함정**: `Base.metadata.create_all`은 **신규 테이블만** 만들고 기존 테이블을 ALTER하지 않는다.
   시스템 테이블에 컬럼을 늘리는 설계는 "마이그레이션이 모든 조회 프로세스보다 먼저 돌아야 한다"는
   순서 의존을 만들어, 웹서버가 먼저 뜨면 admin API가 UndefinedColumn 500으로 죽는다.
   **올바른 방법**: 상태 저장이 필요하면 기존 테이블 확장보다 **신규 테이블 + `ensure_*` 함수**
   (information_schema 게이트 + checkfirst)를 우선 검토한다.
