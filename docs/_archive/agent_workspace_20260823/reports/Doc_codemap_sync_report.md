# 보고서: 코드맵 동기화 (이슈 #7 배치 + CSS 2건 + 스펙 등재)

- 발신: doc-keeper / 수신: 총괄 PM
- 기준 HEAD: `7932926` / 상태: **갱신 완료 / 미커밋(총괄 검수 대기)**
- 히스토리 기록 없음(경상 유지보수 — 지시대로 생략).

## 1. 갱신 파일

| 파일 | 변경 요지 |
|---|---|
| `docs/architecture/CODE_MAP.md` | 본체 — 아래 §2 |
| `docs/README.md` | §3 표에 `ENRICHMENT_QUEUE_SPEC.md`(🟢)·`ONTOLOGY_GRAPH_SPEC.md`(🟠 제안) 등재, `graph_db_integration_plan.md`에 "구식화 예정 — ONTOLOGY_GRAPH_SPEC이 대체" 표기, 이력 인덱스 카운트 187→188 |
| `docs/architecture/backend.md` | 서버 보고서에서 이관된 리빙 문서 항목 — §2 라우트 표 `/admin/reload-configs`(:2277→:2425, 물리 CREATE 포함·발행 선행 명시) + §4 공통 문장(워커 SYSTEM_RELOAD가 `refresh_dynamic_models`로 신규 테이블 CREATE 보충, Graph Sync만 리로드 경로 없음 명시). ※ 보고서가 지목한 `event_driven_backend.md`에는 SYSTEM_RELOAD "흐름" 서술 자체가 없어(인덱스·리스너 언급뿐) 흐름이 실제 서술된 backend.md에 반영 |

## 2. CODE_MAP.md 변경 상세

**6c447ee (이슈 #7)** — grep으로 전 앵커 실측 확인:
- 상단 Last-verified `cd3f90c` → `7932926` (사용 규칙의 앵커 기준 해시 포함 2곳).
- §5에 **`server/database/models.py` 서브섹션 신설**(~376줄): `DYNAMIC_TABLES`(~181) `init_dynamic_models`(~186) `sync_dynamic_tables_schema`(~273, ⚠️ 존재 테이블 ALTER 전용 명시) `_runtime_ddl_lock`(~310) `create_missing_dynamic_tables`(~313) `refresh_dynamic_models`(~354, 호출처 4곳 명기). §6 models.py 행은 §5 포인터로 축약.
- §1.1 `reload_local_process_cache`(~2396) 역할 재서술 — refresh_dynamic_models 위임(이전 no-op이었음 명시). §1.4 `/admin/reload-configs` 앵커 :2418→:2425 + 1차 DDL 소유자·발행 선행 명시.
- §4 `start_chain_ingestion_worker`(~768 유지) 서술에 SYSTEM_RELOAD 블록(~834) refresh 호출 추가. §6 config_watcher(engine 분기 ~44 선호출)·run_watcher(폴러 ~141) 행 갱신.
- §8 흐름 6(설정 핫리로드) 재작성 — CREATE 선행/보충 안전망/graph_sync 미인지(열린 이슈) 반영.
- 라인수: main.py ~3,301 / chain worker ~955 / §5 합계 ~1,075 (TOC 갱신).

**d48f25b / 4229d9f (CSS)** — 함수 변화 없음, §7 보조 모듈 표만: style.css ~1,844(app-header z:200 스태킹 1줄) / tokens.css ~287(다크 심화 1줄). 그 외 스킵.

## 3. 발견한 불일치 (미수정 — 검토 요망)

1. **backend.md 라인 앵커 전반 노후**: 이번에 :2277 하나만 고쳤으나, 같은 표의 다른 앵커도 다수 낡음(예: upload :1753 vs 실제 ~1863, WS :1741 vs ~1851 — main.py가 그간 ~200줄 성장). CODE_MAP이 앵커 SSOT이므로 backend.md는 라인 앵커를 걷어내고 CODE_MAP 링크로 대체하는 편이 유지비가 낮음 — 정합 감사 사이클에 일괄 처리 제안.
2. **DOC_OWNERSHIP.md에 신설 스펙 2종 매핑 부재**: `ENRICHMENT_QUEUE_SPEC.md`(Owner: Server+Client PM, 계약은 총괄)·`ONTOLOGY_GRAPH_SPEC.md`(Owner: 총괄) 행 추가 필요 — 소유 매핑은 거버넌스 결정이라 직접 추가하지 않고 제안만.
3. PROJECT_STATUS.md working-tree diff는 총괄 세션의 동시 편집으로 확인 — 본인 미접촉(지시 준수).

## 4. SSOT 관련

변경 없음 — 이번 배치는 경계 계약 불변(서버 보고서 확인)이라 SYSTEM_OVERVIEW 제안 사항 없음.

## 5. 교훈 제안 (총괄 검수 후 memory/doc-keeper.md 반영)

- **함정**: 커밋 diff의 "+N줄"만 보고 함수 라인 앵커를 산술 이동시키면 틀린다 — 삽입 위치가 해당 함수 **뒤**일 수 있다(이번에 `start_chain_ingestion_worker`를 ~778로 잘못 옮겼다 grep으로 ~768 확인 후 정정). **올바른 방법**: 앵커 갱신은 반드시 `grep -n "def <이름>"` 실측으로 확정.
- **함정**: 보고서가 지목한 리빙 문서에 해당 서술 섹션이 실제로 없을 수 있다(event_driven_backend.md에 SYSTEM_RELOAD 흐름 서술 부재). **올바른 방법**: 반영 전 대상 문서를 grep으로 확인하고, 서술이 실존하는 문서에 반영한 뒤 보고서에 위치 변경 사유를 남긴다.
