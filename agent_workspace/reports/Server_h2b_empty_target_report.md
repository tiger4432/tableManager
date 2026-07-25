# Server 보고서 — [H2-b] 교정 비움(blank 복귀) 시 낡은 엣지 잔존 수정

- **일시:** 2026-07-25 18:30 / **주체:** Server PM / **트리:** 본체 main (미커밋 — 총괄 커밋)
- **결론:** 수정 완료. 신규 회귀 2건 포함 모듈 27 passed, 전체 스위트 **146 passed / 1 failed**(기허용 `test_map_presets_api`만). 경계 계약·DELETE(§8) 정책 불변.

## 1) 원인 확정

`_retarget_stale_edges`(server/graph_materializer.py)는 **이번 산출 엣지들로부터** ref 스코프와 허용 집합을 만들었다. 로우의 현재 산출 엣지가 **0개**(타깃 blank 복귀)면 그 로우의 ref가 스코프에 들어오지 않아 정리 경로 자체에 도달 불가 — 총괄 라이브 실증(graph_sync.log 16:51:24 `rows=1 nodes=1 edges=0` 소비 후 엣지 잔존)과 정확히 일치.

## 2) 변경 함수 목록 (전부 server/graph_materializer.py)

| 함수 | 변경 |
|---|---|
| `_retarget_stale_edges(db, rows, chunk_size, processed_refs=None)` | 파라미터 추가. 스코프 = processed_refs ∪ 산출 엣지 ref. 허용 집합을 로우별 `{(from_node, type, to_node)}`로 재구성 — 그 로우 ref의 기존 엣지 중 이번 산출 집합에 없는 것은 **산출 0개여도** 삭제. idx_graph_edges_row_ref 룩업 + 1000행 청크 삭제 유지 |
| `bulk_upsert_edges(db, edges, node_ids, chunk_size, processed_refs=None)` | 파라미터 추가·관통. `if not edges: return 0` 조기 탈출을 retarget **뒤**로 이동(엣지 0개 배치도 정리 수행) |
| `materialize_rows` | 처리 로우 전체의 `f"{table}:{row_id}"` 집합(산출 무관)을 수집해 전달 → **resync 경로**(resync_table → materialize_rows) 동일 의미론 |
| `materialize_events` | 매핑된 테이블의 CREATE/EDIT 로우 전체 ref 수집·전달 → **증분 경로** 동일 의미론 |

의미론 메모: 매칭이 (from,type) 고정→to 비교에서 로우 단위 집합 부재 판정으로 일반화되어, **from 노드 identity가 바뀐 구 엣지**도 함께 정리된다(로우가 주장의 단위 — 기존 docstring 원칙의 완성). 안전 근거: outbox EDIT payload는 항상 전 컬럼 스냅샷(`stage_event`가 `__table__.columns` 전량 직렬화, `scripts/reapply_chain.py`도 동일) — 전 producer 전수 확인했으므로 "산출 없음 = 현재 로우가 주장 없음"이 보장된다. 다른 로우의 엣지는 여전히 source_row_ref 스코프 밖. DELETE 이벤트는 여전히 skip(§8 범위 밖, 미변경).

## 3) 검증

- **신규 회귀 2건** (server/tests/test_ontology_g1.py, 공용 헬퍼 `_seed_two_resolved_as`/`_assert_only_r2_resolved`):
  - `test_h2b_source_delete_blank_clears_edge_incremental` — 파생행 2개 각각 user 교정(RESOLVED_AS 2개) → **`crud.delete_cell_source`로 user 소스 삭제(라이브 DELETE .../sources/user와 동일 경로)** → wafer_id blank 복귀 확인 → EDIT outbox를 materialize_events로 소비 → 해당 로우 엣지만 소멸·타 로우(같은 타깃 W777) 엣지 보존·노드 3종 보존 + 같은 이벤트 재소비 멱등.
  - `test_h2b_source_delete_blank_clears_edge_resync` — 증분 소비를 생략해 잔존 상태를 만든 뒤 **부분 resync(row_ids=[r1])** 만으로 정리 확인 + 전체 resync 멱등.
- 기존 H1(위조 날인·경로 동등성)·H2(retarget·타 로우 보존)·E2E(재교정 W123→W124)·resync 청킹 전부 유지 — 모듈 27 passed.
- 전체: `conda run -n assy_manager python -m pytest server/tests/ -q` → **146 passed, 1 failed**(기허용 `test_map_presets_api`).

## 4) 라이브 잔존 엣지(WF-LIVE-G1-TEST) 정리 방법 — 실행은 총괄

핵심: 현재 기동 중인 graph_sync 워커(:8090)는 **구 graph_materializer를 import한 채**이므로, 그 워커에 `POST /sync`를 보내도 구 코드가 돌아 정리되지 않는다. **워커 재기동 없이** 정리하려면 수정 코드를 새 프로세스로 실행하는 부분 resync가 정답:

```python
# server/ 에서 실행: conda run -n assy_manager python <이 스크립트>
# (PYTHONIOENCODING=utf-8 권장)
import sys; sys.path.insert(0, ".")  # server/ 기준
from database.database import SessionLocal
from database import crud, models
import ontology_config, graph_materializer

cfg = crud.load_table_config()
models.init_dynamic_models(cfg); crud.TABLE_CONFIG.update(cfg)
mappings = ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)

ROW_ID = "019f970a-aa6c-..."  # 총괄 보유 전체 row_id로 치환
db = SessionLocal()
try:
    stats = graph_materializer.resync_table(
        db, "core_wafer_map", mappings, row_ids=[ROW_ID])
    print("resync stats:", stats)
finally:
    db.close()
```

- 안전성: 같은 PostgreSQL에 대해 멱등 UPSERT + row_ref 스코프 삭제 + is_graph_synced 스탬프뿐이라 가동 중 워커와 병행 무해(해당 로우는 정지 상태). 회귀 테스트 ②가 정확히 이 경로(`resync_table(row_ids=...)`)를 검증한다.
- 대안(수정 배포로 워커를 재기동한 뒤라면): `POST http://127.0.0.1:8090/sync` body `{"table_name": "core_wafer_map", "row_ids": ["<row_id>"]}` — 동일하게 정리된다. 워커 재기동 자체가 정리를 해주지는 않음(증분 커서는 이미 지나감) — 재기동 후에도 부분 resync 1회는 필요.

## 5) 인계 요약

- **변경:** server/graph_materializer.py 4함수(위 표) + server/tests/test_ontology_g1.py 신규 2건·헬퍼 2개. 문서: docs/history/20260725_183000_ontology_h2b_empty_target_retarget.md + 인덱스 재생성. PROJECT_STATUS #60 항목(H2-b 수정 중 → 완료) 갱신은 총괄 병합 시점에 일임.
- **미해결(범위 밖, 기존 동작):** 한 배치에 같은 로우의 CREATE+EDIT가 함께 소비되면 구·신 타깃 엣지가 일시 병존 가능(edges dict가 이벤트별 상태를 모두 산출) — 다음 이벤트/resync에서 수렴. 필요시 "배치 내 로우 최종 상태만 채택"으로 후속 가능.
- **다음 단계:** 총괄 diff 검수 → 커밋 → 라이브 부분 resync(§4) → 서브그래프 미니 뷰어 착수.
- **교훈 제안(총괄 검수용):** "그래프 정리(retarget)류 로직은 '산출물 스코프'가 아니라 '처리한 입력(로우) 스코프'로 잡아야 한다 — 산출 0개인 입력이 스코프에서 빠지면 '비움' 계열 흐름이 영구 잔존을 만든다."
