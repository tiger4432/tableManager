---
name: StableDevelopmentProtocol
description: 모든 에이전트가 준수하는 assyManager 핵심 개발 헌장 — 의존성 안전, 대규모(수천만 행) 최적화, 문서·이력 무결 동기화, 작업 인계 요약
---

# 🧭 Stable Development Protocol (핵심 개발 헌장)

본 스킬은 `assyManager`의 **모든 에이전트가 예외 없이 준수해야 하는 최상위 개발 규율**입니다. 다른 도메인 스킬(DataIngester, ExcelInteractionExpert 등)보다 상위에 있으며, 어떤 작업이든 시작 전과 종료 전에 이 프로토콜을 통과해야 합니다.

> 기준 문서: SSOT [`docs/overview/SYSTEM_OVERVIEW.md`](file:///c:/Users/kk980/Developments/assyManager/docs/overview/SYSTEM_OVERVIEW.md) · 규율 [`docs/process/CONTRIBUTING.md`](file:///c:/Users/kk980/Developments/assyManager/docs/process/CONTRIBUTING.md) · 소유 매핑 [`docs/process/DOC_OWNERSHIP.md`](file:///c:/Users/kk980/Developments/assyManager/docs/process/DOC_OWNERSHIP.md)

---

## 🚦 0. 작업 전 필수 절차 (Pre-Flight)

1. **진입점부터 읽기**: `docs/README.md`(문서 지도) → `docs/overview/SYSTEM_OVERVIEW.md`(SSOT)로 현재 아키텍처를 파악한다. **낡은 정보 주의**: 메인 클라이언트는 웹 `client2`(AG-Grid)이며 구 PySide6 클라이언트는 없다. DB는 PostgreSQL/JSONB. 백엔드는 5-프로세스 + Outbox.
2. **소유 문서 확인**: 손댈 서브시스템의 리빙 문서를 `DOC_OWNERSHIP.md`에서 찾아 설계 의도와 데이터 흐름을 먼저 이해한다. (Docs-First)
3. **영향 범위 매핑**: 수정 대상이 참조되는 곳(라우터·워커·클라이언트 모듈·테스트)을 Grep으로 사전 조사한다.

---

## 1. 🔗 핵심가치 ① 의존성 문제 없는 코드 수정 (Dependency-Safe)

**단 한 곳의 누락도 런타임 전체를 마비시킨다.** 아래를 강제한다.

- **시그니처 영향 전수 분석**: CRUD 코어(`server/database/crud.py`)나 공용 함수의 매개변수/반환 구조를 바꾸기 전, 프로젝트 전체를 Grep하여 호출부를 찾고 **연쇄 갱신**한다. 필수 대상: `server/main.py`(라우터), `server/chain_ingestion_worker.py`(워커), `server/tests/`(테스트). 완료 후 `pytest` 통과 증명. 상세: [`docs/guide/data_preservation_and_signature_change.md`](file:///c:/Users/kk980/Developments/assyManager/docs/guide/data_preservation_and_signature_change.md) **(필독)**.
- **계약(Contract) 보존**: `crud.apply_batch_updates`의 반환 `(results, changed_cells, created_logs, deleted_row_ids)` 등 확립된 반환 구조를 임의로 깨지 않는다.
- **레이어 간 계약 인지**: 서버 스키마 JSON 형태 ↔ 클라이언트 셀 형태 `data[col] = {value, is_overwrite, priority_source}`(`client2/src/grid.js` `ensureCellObject`), WS 이벤트명(`batch_row_create|upsert|delete`, `batch_refresh_required`), API 엔드포인트(`api.js`/`websocket.js` 소비)는 한쪽만 바꾸면 즉시 파손된다. 항상 양쪽을 함께 본다.
- **설정 주도 존중**: 스키마/테이블 변경은 하드코딩이 아니라 `server/config/table_config.json` + `SYSTEM_RELOAD` 경로로 한다.
- **병합 데이터 보존**: 비즈니스 키 충돌 병합 시 사용자 오버라이트를 보존하고 원천 소스명을 계승, `updated_by="collision_merge"`로 이중 추적한다.
- **GC 안티패턴 금지**: PyQt/PySide 비동기 시그널 연결에 로컬 `lambda`/클로저 금지 → 반드시 **Bound Method**에 연결(GC 유실로 인한 영구 행 버그 방지).
- **최소 침습(Minimum Surgery)**: 근본 원인만 정밀 수정. 동작 중인 로직을 요청 범위 밖까지 리팩토링하지 않는다.

---

## 2. ⚡ 핵심가치 ② 수천만 행을 염두한 최적화 (Scale-First)

**모든 쿼리·루프·페이로드는 "이 테이블에 1,000만 행이 있어도 괜찮은가?"를 통과해야 한다.**

- **풀 스캔 금지**: `cast(data, String).ilike('%q%')` 류의 JSON 전체 문자열 캐스팅 검색은 1,000만 행에서 20~60초 지연을 유발한다. 인덱스 컬럼(`business_key_val`) 또는 특정 JSONB 필드 타겟팅 + GIN/trigram(`pg_trgm`)만 사용한다.
- **복합 색인 전제**: 테이블 필터 + 정렬은 `(table_name, business_key_val)` / `(table_name, updated_at)` 복합 색인을 전제로 작성한다. 새 정렬/필터 축을 추가하면 색인도 함께 설계한다.
- **큰 OFFSET 금지**: 깊은 페이지네이션은 keyset/cursor 방식과 `row_id` 2차 정렬(tie-breaker)로 처리한다. 클라이언트는 뷰포트 기반 청크 페칭(가상 로딩)을 유지한다.
- **대량 쓰기는 배치**: 행 단위 ORM 반복 금지. **1000행 청크** + `bulk_insert_mappings`/`bulk_upsert`(dialect별 `ON CONFLICT`)로 처리. 감사 로그도 `bulk_insert_audit_logs` 사용.
- **응답 즉시 반환**: 무거운 브로드캐스트는 FastAPI `BackgroundTasks`로 이관해 HTTP 200을 즉시 반환한다. 카운트는 캐시(5s)하고, 실시간 동기화는 실제 변경 셀만(delta/`change_count`) 전송한다.
- **N+1 제거**: 맵퍼/체인에서 매 행 `db.query()` 금지. 초기화 시 룩업 대상을 메모리 딕셔너리에 캐싱한다.
- **절대 전량 로드 금지**: 서버·pgAdmin·클라이언트 어디서든 `SELECT *` 무제한 금지, 항상 `LIMIT`/페이징. 신규 코드는 대규모 데이터에서의 메모리/네트워크 부하를 리뷰 포인트로 명시한다.

---

## 3. 📚 핵심가치 ③ 이력·프로젝트 지도 무결 동기화 (Docs-as-Code)

**히스토리 기록만으로는 부족하다. 현재 상태를 말하는 것은 리빙 문서다.**

- **히스토리 필수**: 모든 주요 변경은 `docs/history/YYYYMMDD_HHMMSS_summary.md`에 기록한다. 현상·근본원인·해결(핵심 코드 스니펫 포함)·검증을 담는다.
- **인덱스 자동 재생성**: 히스토리 파일 추가 후 반드시 실행 —
  ```bash
  python docs/history/gen_index.py
  ```
  `docs/history/README.md`는 자동 생성물이므로 수동 편집 금지.
- **리빙 문서 동시 갱신**: 변경이 아키텍처/프로세스면 SSOT(`overview/SYSTEM_OVERVIEW.md`) + `architecture/*`, 서브시스템 동작이면 소유 문서(`DOC_OWNERSHIP.md` 매핑)를 **같은 작업에서** 고친다. 판단 기준: *"다음 사람이 이 변경을 알아야 하는가?"* → 예이면 문서를 고친다.
- **배지 갱신**: 손댄 리빙 문서 상단 `Last-verified`(코드 대조일)를 갱신한다.
- **낡은 문서**: 삭제하지 말고 `docs/_archive/`로 `git mv` + SUPERSEDED 배지.
- **커밋 규약**: `feat|fix|docs|refactor|test|chore`. 히스토리 기록은 커밋 전 필수 단계.

---

## 4. 📝 핵심가치 ④ 다음 작업을 위한 요약 (Handoff Summary)

**작업 종료 시 다음 세션/에이전트가 문맥 없이도 이어갈 수 있는 요약을 남긴다.**

작업 종료 전 아래를 포함한 요약을 제출한다.
- **변경 요약**: 무엇을·왜 바꿨는가 (한 문단).
- **수정 파일 목록**: 경로 + 한 줄 설명.
- **검증 결과**: 실행/테스트 결과를 사실 그대로. 실패·미검증은 숨기지 않는다.
- **미해결 이슈 / 다음 단계**: 남은 작업, 리스크, 후속 TODO.

인계 위치:
- 하위 에이전트 → `agent_workspace/reports/[이름]_report.md`.
- 마일스톤 → `docs/process/RELEASE_LOG.md` 상단에 한 줄.
- 백로그 → 루트 `task/`.
- 코드가 없는 비-자명한 사실(설계 결정 등)은 프로젝트 메모리에 저장 제안.

---

## ✅ 종료 전 체크리스트 (Post-Flight)

- [ ] ① 시그니처/계약 변경 시 호출부 전수 갱신 + `pytest` 통과했는가?
- [ ] ① 서버-클라이언트 데이터 계약(셀 형태·WS 이벤트·API)을 깨지 않았는가?
- [ ] ② 새 쿼리/루프/페이로드가 1,000만 행에서도 안전한가? (인덱스/청킹/LIMIT)
- [ ] ③ `docs/history/`에 이력 작성 + `gen_index.py` 실행했는가?
- [ ] ③ 아키텍처/동작 변경이면 SSOT·소유 리빙 문서를 갱신했는가?
- [ ] ④ 변경·검증·미해결·다음단계 요약을 남겼는가?

---

## 🐍 정식 실행 환경 (Canonical Commands)

| 구분 | 명령어 |
|---|---|
| 환경 활성화 | `conda activate assy_manager` (⚠️ `venv` 절대 사용 금지 — DLL 충돌로 폐기됨) |
| **전체 스택 기동** | `python run_decoupled_app.py` (웹서버 :8080 + 워커 4종 + 데스크톱 셸) |
| 서버만 | `python run_decoupled_app.py --server-only` |
| 프론트엔드 개발 | `cd client2 && npm run dev` (:5173 → API/WS는 :8080 자동 타겟) |
| 테스트 | `cd server && pytest` |

---

*이 프로토콜을 우회한 수정은 시스템의 부채가 된다. 의존성 안전 · 확장성 · 문서 동기화 · 인계 요약, 이 넷은 타협 대상이 아니다.*
