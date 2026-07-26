# 대형 파일 P2 — 오프셋 체크포인트 재개 + 해시 dedup + 감사 결함 2건

> 커밋 `f78ab0a` (+ 보고서 `190093a`) · 2026-07-26 16:46 · 도메인 Server/인제션
> 상위: [INGESTION_GUIDE](../guide/INGESTION_GUIDE.md) · [CODE_MAP §3·§5](../architecture/CODE_MAP.md)

## 배경

P1(heavy 레인, `4fd8ac9`+`8b0fd03`)이 대형 파일의 **HOL 차단**을 없앴지만, 두 구멍이 남아 있었다.

1. **재기동 = 전량 재처리.** 10만 행 파일을 7분째 처리하다 서버가 내려가면 다음 기동에서 0행부터 다시 시작했다. P1은 admin에 경고 배너를 띄우는 **지혈**까지만 했다.
2. **같은 파일 재투입 방어 없음.** 수집기가 같은 파일을 다시 떨구면 그대로 다시 전량 파싱·업서트했다.

부수로, QA가 지목한 감사 계층 결함 2건(이슈 #10 + audit 값 길이 무제한)을 같은 배치에 태웠다.

## 변경 내용

### A. 오프셋 체크포인트 재개 — 신규 모듈 `server/ingestion_checkpoint.py`

저장소는 **`FileIngestionLog`에 컬럼을 늘리지 않고 신규 테이블 `file_ingestion_checkpoints`**(`UNIQUE(table_name, file_signature)`)를 썼다. 이유는 `create_all`이 ALTER를 하지 않기 때문 — 기존 테이블에 컬럼을 붙이면 **조회 프로세스보다 먼저 도는 마이그레이션**이 필요해지고, 운영 DB에서 admin File 탭이 `UndefinedColumn` 500을 뱉는 순서 사고가 열린다(총괄 승인 판단).

모듈 표면:

```python
SIGNATURE_ALGO = "sha256"          # :51
STATUS_IN_PROGRESS = "IN_PROGRESS" # :53
STATUS_DONE = "DONE"               # :54
FORCE_REINGEST_TOKEN = "__force__" # :58

def compute_file_signature(file_path: str) -> str | None:   # :61
def is_force_reingest(filename: str) -> bool:               # :88
class CheckpointPlan:                                        # :93
def find_checkpoint(db, table_name, file_signature):         # :132
def find_completed_ingestion(db, table_name, file_signature):# :142
def plan_ingestion(db, table_name, file_signature, filename, filepath, ...):  # :150
def record_chunk_progress(db, plan, processed_rows, chunk_index):             # :218
def mark_done(db, plan, processed_rows=None, note=None):                      # :243
```

**원자성이 이 설계의 핵심이다.** 오프셋 갱신은 청크 upsert와 **같은 트랜잭션**에서 일어난다(`apply_batch_updates` 내부 commit에 동승) → "커밋된 행 수 == 기록된 오프셋"이 항상 성립한다. 별도 커밋이면 두 값이 어긋나는 창이 생긴다.

**재개 판정은 보수적이다.** 시그니처 + `total_rows` + `source_kind`(파서 정체성) + 오프셋 범위가 **전부** 일치할 때만 이어붙인다. 하나라도 다르거나 손상이면 0부터 재처리하되, 그 사유를 로그·`FileIngestionLog.detail`·완료 통지에 명시한다(조용한 재처리 금지).

heavy/normal 레인, 기동·주기 스윕, 관리자 재시도 — **4개 경로 전부 동일 동작**이다.

### B. 파일 해시 dedup

시그니처 형식은 `sha256:<size>:<digest>`(**샘플링 아님 — 전체 해시**). 채택 근거는 실측이다: 500MB 0.535초(~935MB/s), 15.6MB 0.016초 — 라이브 드릴 총 처리 415초의 **0.004%**. 비용이 무시 가능하므로 정확성을 택했다.

동일 시그니처가 이미 `DONE`이면 skip + archives 이동 + `FileIngestionLog(status=SKIPPED, 사유)`. 단, **WS 통지의 `status`는 `SUCCESS`로 보낸다** — 수신부(클라)가 비-SUCCESS를 일괄 "실패"로 렌더링하므로 오표기를 막기 위함이고, 사유는 `detail`에 담는다.

강제 재처리 탈출구 3경로: 파일명에 `__force__` 토큰 / `dedupe_by_signature=false` 설정 / 관리자 재시도.

### C. 감사 결함 2건

- **이슈 #10 (`audit_cache.add_logs_batch`)** — `override_total_count`(SET) → `message_total_count`(누적)으로 전환. 멀티 target-table 트랜잭션에서 마지막 메시지가 앞선 테이블의 총계를 **덮어 지우던** 과소 표기를 제거했다. 다중 tx가 한 배치에 섞이면 귀속이 불가능하므로 `len(logs)` 폴백 + 1회 경고.
- **`crud.create_audit_log`** — `old_value`/`new_value`에 4096자 상한 + 절단 시 원 길이 마커를 값 안에 명시. 최근 20만 건 실측 최대 432자라 **현행 데이터엔 무영향**이며, 대형 텍스트 셀이 들어올 때의 재발 경로만 봉쇄한 것이다.

## 아키텍처 영향

- **`main.py` 무수정.** P2는 워처·crud·audit_cache 안에서 끝났다 — 경계 계약(`/internal/events/*`, WS 메시지 형태) 불변.
- 신규 시스템 테이블 1개(`file_ingestion_checkpoints`). 준비 스크립트 `server/scripts/setup_ingestion_checkpoint.py`(멱등).
- 테스트 278 → 307 passed(+29), 허용 실패 1건(`test_map_presets_api`) 유지.

## 다음 단계 / 열린 항목

- **라이브 드릴 3종 미실행(재기동 대기)** — 체크포인트 재개 / dedup / 이슈 #10. 절차는 [P2 보고서 §8](../../agent_workspace/reports/Server_large_file_p2_report.md). 재기동 전까지 P2의 **라이브 동작은 미검증**이다(테스트 스위트만 통과).
- **이슈 #16 (신규 등재)** — `main.py` import 시 모듈 레벨 `Base.metadata.create_all`이 운영 PostgreSQL에 DDL을 발행한다. P2 작업 중 실제로 라이브에 빈 테이블이 생겼다(무해했으나 경로 자체가 위험). 기존 동작이며 P2 회귀 아님 — 테스트 DB 격리 필요.
- P3 잔여: 후단 backpressure(outbox 파일 단위 집계) + PG COPY 벌크 경로 + heavy 워커 수 설정화.
