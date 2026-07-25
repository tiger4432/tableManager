# 온톨로지 G1 후속 결함 [H2-b] 수정 — 교정 비움(blank 복귀) 시 낡은 엣지 잔존 해소

- **일시:** 2026-07-25 18:30
- **주체:** Server PM (총괄 라이브 실증 결함 위임)
- **영역:** server (graph_materializer + tests)
- **커밋:** (미커밋 — 총괄 검수 후 커밋 예정)

## 무엇이 바뀌었나

enrichment 교정을 **비우는** 흐름(예: wafer_id의 user 소스 삭제 → 값 blank 복귀)에서
낡은 RESOLVED_AS 엣지가 그래프에 영구 잔존했다(총괄 라이브 실증: core_wafer_map
019f970a-... / WF-LIVE-G1-TEST). 원인: `_retarget_stale_edges`가 **이번 산출 엣지의
ref**로만 스코프를 잡아, 로우의 현재 산출 엣지가 **0개**면 정리 경로에 아예 도달하지
않았다.

- `_retarget_stale_edges(db, rows, chunk_size, processed_refs=None)`: 스코프를
  "산출 엣지의 ref"에서 "**이번 배치에서 처리한 전체 로우 ref**(processed_refs ∪ 산출
  ref)"로 확장. 매칭도 (from,type,ref)→to_node 비교에서 **로우 단위 산출 집합**
  `{(from_node,type,to_node)}` 대비 부재 판정으로 일반화 — 산출 0개 로우의 잔존 엣지,
  from 노드 identity가 바뀐 구 엣지까지 정리된다(로우가 주장의 단위). outbox EDIT
  payload는 항상 전 컬럼 스냅샷(`stage_event`)이므로 "산출 없음 = 현재 로우가 주장
  없음"이 보장됨을 확인(전 producer: before_flush listener·reapply_chain 전수 확인).
- `bulk_upsert_edges(..., processed_refs=None)`: edges가 비어도 retarget은 수행하도록
  조기 return 위치 이동 + 파라미터 관통.
- `materialize_rows`(→ resync 경로) / `materialize_events`(→ 증분 경로): 처리한 로우의
  `f"{table}:{row_id}"` 집합을 산출 유무와 무관하게 수집해 전달 — 양 경로 동일 의미론.
- **DELETE 이벤트(행 삭제) 정책은 불변** — 여전히 스펙 §8 범위 밖(skip + 카운트).
  경계 계약(REST/WS/셀 형태/스키마) 무변경. 인덱스 경로(idx_graph_edges_row_ref)와
  1000행 청킹 규율 유지.

## 검증

- 신규 회귀 테스트 2건(`test_ontology_g1.py`): 교정→RESOLVED_AS 생성→**user 소스
  삭제(crud.delete_cell_source, 라이브와 동일 경로)**→blank 복귀→엣지 소멸을
  ① 증분(materialize_events, 재소비 멱등 포함) ② 재동기화(부분 row_ids + 전체) 양
  경로에서 확인. 같은 타깃(W777)을 주장하는 **다른 로우의 엣지 보존**(source_row_ref
  스코핑)과 노드 보존(§8 밖)도 단언.
- 기존 H1/H2 경로 동등성·retarget·E2E 테스트 전부 유지: 모듈 27 passed.
- 전체 스위트 `conda run -n assy_manager python -m pytest server/tests/ -q`:
  **146 passed / 1 failed** — 실패는 기허용 `test_map_presets_api` 1건뿐.

## 잔여/미해결

- **라이브 잔존 엣지 정리(실행은 총괄)**: 현재 기동 중인 graph_sync 워커는 구 코드를
  물고 있으므로, 워커 재기동 없이 정리하려면 **수정 코드로 별도 프로세스 부분 resync**
  실행(보고서 `Server_h2b_empty_target_report.md`에 스크립트 명시). 워커 재기동을
  겸한다면 `POST 127.0.0.1:8090/sync` 부분 동기화로도 동일 정리.
- 배치 내 동일 로우 다중 이벤트(create+edit 동시 소비) 시 구·신 타깃이 한 배치 안에서
  병존 가능한 기존 한계는 본 건 범위 밖(기존 동작 불변, 다음 배치/resync에서 수렴).
