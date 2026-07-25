# 코드맵(CODE_MAP) + 에이전트 교훈 파일 체계 구축

- **일시:** 2026-07-25
- **작업자:** doc-keeper (총괄 PM 위임, 지시서 `agent_workspace/tasks/Doc_code_map_system_task.md`)
- **기준 커밋:** cd3f90c (라인 앵커 기준)
- **성격:** 문서·에이전트 정의만 변경 — **코드 무변경**

## 배경

에이전트들이 작업마다 대형 소스(`main.py` 3,295줄, `map_editor.js` 2,771줄 등)를 전량 Read하여 토큰 소모가 과다했다(사용자 직접 요청, 2026-07-25). 또한 반복 함정(환경·인코딩·outbox 인덱스 등)이 세션마다 재발견되고 있었다. 해법으로 두 축을 신설했다:

1. **코드맵** — "코드맵 먼저 읽고, 소스는 필요한 부분만" 이 가능한 압축 구조 지도.
2. **에이전트별 교훈 파일** — 확정 교훈의 영속 저장소(제안 → 총괄 검수 → 반영).

## 변경 내용

### 1. `docs/architecture/CODE_MAP.md` 신설 (~300줄, 규율 상한 1,500줄 이내 → 분할 불필요)

파일별 핵심 함수/클래스 **시그니처 + 역할 1줄 + 대략 라인 앵커(±20줄)** + 주요 호출 흐름 7개. 수록 범위:

- `server/main.py` — API 라우트 표 4개(조회/편집, 이력/레이어링, 어드민/운영, 내부 이벤트) + 헬퍼
- `server/database/crud.py` — 레이어링 코어 함수군. 예:

```python
def apply_row_update_internal(
    db, table_name, update_item, row_cache=None, sources_cache=None,
    overwrites_cache=None, transaction_id=None, logs_to_cache=None,
    cell_sources_to_upsert=None, cell_overwrites_to_upsert=None,
    cell_overwrites_to_delete=None, deleted_row_ids=None
) -> tuple[Any, bool, list[str]]:   # crud.py ~446 — 모든 쓰기 경로가 수렴하는 통합 코어
```

- `server/parsers/directory_watcher.py` — 2026-07-25 std parser 통합 반영(`_resolve_rows` 파이프라인 우선 → `_try_std_parse` 폴백, `_send_to_upsert`는 HTTP 아닌 `crud.apply_batch_updates` 직접 호출)
- `server/chain_ingestion_worker.py` — F1~F5·warmup 반영된 최신 구조
- 소형 모듈(`std_parser.py`/`enrichment_config.py`/`enrichment_mapper.py`) + 기타 서버 모듈 한줄 요약
- `client2/src/*` — 모듈 책임 + export 함수 목록 + 소비 이벤트/API 수준으로 압축(WS 소비 이벤트 6종 라인 앵커 포함)

문서 상단에 유지보수 규율 명시: **"코드 변경 시 해당 모듈 맵 갱신은 구현 에이전트 책임, 정기 정합 감사는 doc-keeper"**.

부수 발견: `main.py` ~1613과 ~2020에 `GET /tables/{t}/rows/{r}/cells/{c}/history` 라우트가 **중복 정의**되어 있음(선등록 ~1614가 유효, 후자는 사실상 사장) — 코드맵에 주석으로 표기, 코드 수정은 하지 않음.

### 2. `agent_workspace/memory/<agent>.md` 5개 신설

대상: `server-pm` / `client-pm` / `qa-reviewer` / `doc-keeper` / `ui-designer`. 형식은 항목당 2~3줄(**함정 → 올바른 방법**). 초기 시드는 총괄이 검수한 확정 교훈(공통 4건: conda `assy_manager` 필수 / `PYTHONIOENCODING=utf-8` / conda run 멀티라인 `-c` 불가 / `/tmp` 불가시성 + 에이전트별 전용 교훈). 각 파일 상단에 운영 규칙 명시:

```markdown
> **운영 규칙:** 신규 교훈은 에이전트가 보고서에 **제안** → 총괄 검수 후 이 파일에 반영. (직접 추가 금지)
```

doc-keeper 전용 섹션은 확정 교훈이 아직 없어 빈 상태로 개설.

### 3. `.claude/agents/*.md` 5개 Pre-Flight 배선 (기존 내용 무변경, 항목 추가만)

각 정의의 착수 전 필독(Pre-Flight) 목록 끝에 2개 항목 추가:

```markdown
6. **코드맵 먼저**: docs/architecture/CODE_MAP.md에서 함수·라인을 찾은 뒤 소스는 **필요한 부분만 Read** (파일 전량 읽기 금지).
7. **자기 교훈 파일 로드**: agent_workspace/memory/<agent>.md — 반복 함정 목록. 신규 교훈은 보고서에 제안(직접 추가 금지).
```

(번호는 파일별 기존 목록 길이에 맞춤: server-pm/client-pm 6·7, qa-reviewer 4·5, doc-keeper 5·6, ui-designer 4·5.)

### 4. 문서 지도 등재

- `docs/README.md` §2 아키텍처 표에 🟢 CODE_MAP.md 등재(최상단).
- `docs/process/DOC_OWNERSHIP.md`에 소유 매핑 행 추가(코드 구조 지도 — 갱신은 구현 에이전트, 감사는 doc-keeper).

## 아키텍처 영향

런타임 영향 없음(코드 무변경). 에이전트 운영 체계 영향:
- 모든 서브에이전트의 표준 착수 절차에 "코드맵 → 부분 Read" 단계가 삽입되어 토큰 소모 구조가 바뀐다.
- 코드맵은 리빙 문서이므로 **docs-as-code 규율의 갱신 대상이 하나 늘었다** — 구현 커밋 시 해당 모듈 맵 갱신 필요.

## 다음 단계

- PROJECT_STATUS 백로그의 해당 항목 완료 처리(총괄 — 초안은 `agent_workspace/reports/Doc_code_map_report.md`).
- 라인 앵커는 소스 진화에 따라 드리프트하므로 주기 정합 감사 시 코드맵 앵커 스팟체크 포함.
- `main.py` 중복 라우트(~2020)는 server-pm에 정리 여부 판단 위임 검토.
