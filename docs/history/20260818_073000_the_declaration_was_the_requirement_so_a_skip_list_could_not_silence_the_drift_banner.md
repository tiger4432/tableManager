# 은퇴한 표 셋이 매 재기동마다 «결손»으로 신고됐다 — 제외 목록으로는 못 고친다

**날짜:** 2026-08-18 07:02 · **커밋:** `311ab36` · **레인:** 서버(그래프 은퇴 마무리)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

2026-08-14 `2ec78b9`이 구 그래프 저장소를 은퇴시키며 표를 **다시 만들** 경로 셋을 봉인했다.
그때의 선택은 **ORM 클래스는 트리에 남기고** 부팅 `create_all`에서 세 표만 «제외»하는
것이었고, 이유가 그 커밋 주석에 적혀 있었다 — `Base.metadata`는 테스트 픽스처가 표를 만드는
통로이기도 해서, 공유 메타데이터에서 지우면 은퇴와 무관한 그래프 단위 테스트가
「no such table」로 죽는다는 것이었다.

그 중간 상태의 대가는 그때 예측되지 않았다. 부팅 스키마 점검(`server/schema_drift.py`)은
`Base.metadata`를 **「이 빌드가 요구하는 것」**으로 읽는다. 그래서 표가 사라진 뒤로 매
재기동이 빨간 블록을 찍었다.

```
SCHEMA DRIFT: the database is missing 3 thing(s) this build requires.
  [MISSING-TABLE] graph_edges / graph_nodes / graph_sync_state
```

그리고 결손 표에 붙는 처방 문구는 `schema_drift.py`에 이렇게 박혀 있었다(이 커밋 시점
`~327`):

```python
"remedy": ("boot the web server once - Base.metadata.create_all builds a "
           "missing table whole. If it stays missing after a boot, the "
           "mapping is registered somewhere create_all does not reach."),
```

즉 **없어야 할 표를 만들라고 운영자에게 안내**하고 있었다. 은퇴가 «고장»의 옷을 입은
것이고, `2ec78b9`이 실행 순서를 못 박아 가며 막으려던 거짓말과 같은 부류가 방향만 뒤집혀
재현된 셈이다.

## 이 커밋이 한 일

**선언을 지웠다.** 부팅은 이제 제외 목록 없이 전부를 만든다 — 요구가 없으므로 결손도 없다.

```python
# before
    models.Base.metadata.create_all(
        bind=target,
        tables=[t for t in models.Base.metadata.sorted_tables
                if t.name not in RETIRED_GRAPH_TABLES],
    )
# after
    models.Base.metadata.create_all(bind=target)
```

`GraphNode` / `GraphEdge` / `GraphSyncState` 세 클래스와 `ensure_graph_tables(engine)`가
`server/database/models.py`에서 사라지고 자리에 묘비 주석이 남았다. 함수가 마지막까지 남아
있던 유일한 이유는 **그래프 단위 테스트가 픽스처 생성에 썼다**는 것이었고, 그 테스트들이
같은 커밋에서 걷히면서 이유도 함께 사라졌다.

값 제안 인덱스의 시스템 대상 목록은 비었다 — 유일한 항목이 은퇴한 `graph_nodes.identity_key`
였기 때문이다. 튜플과 그것을 읽는 루프는 **남겼다**(선언된 확장점).

```python
# ⚰️ EMPTY since 2026-08-18. Its one entry was `("graph_nodes", "identity_key")`,
SYSTEM_PREFIX_INDEX_TARGETS = ()
```

여기서 테스트가 **공허해질 자리**를 함께 막았다. 빈 튜플을 그대로 단언하면 그 단언은 아무
것도 세지 않는다 — 그래서 「오늘의 구성원」 대신 **기구**를 지키도록 probe 항목을 심는
방식으로 바꿨다.

```python
    monkeypatch.setattr(value_suggest, "SYSTEM_PREFIX_INDEX_TARGETS",
                        (("probe_system_table", "probe_key"),))
```

새 단언은 이 라운드의 하중 사실을 **원천에서** 못 박고, 스스로 공허하지 않음까지 검사한다.

```python
    declared = set(models.Base.metadata.tables)
    still_there = sorted(set(main.RETIRED_GRAPH_TABLES) & declared)
    assert still_there == [], (...)
    # Non-vacuous: the metadata is populated, so the absence above is an absence
    assert len(declared) > 5, "Base.metadata is empty; the check above proves nothing"
```

그 밖에 스키마 정준 감사의 `ENGINE_TABLES`, 드리프트 테스트의 시스템 컬럼 표, 미선언 잔여
보고 테스트에서 세 이름이 빠졌고, 격리환경 스냅샷 도구의 그래프 커서 리셋(`graph_sync_state`
1행 초기화)이 제거됐다.

## 남긴 것과 그 이유

- 은퇴 라우트는 **410 + `Cache-Control: no-store`**로 계속 답한다. 지우면 정적 SPA
  catch-all이 HTML 200을 돌려주기 때문이다. 이 커밋 시점 그 라우트는 일곱이고, 그중
  여섯이 `/graph/*`, 하나가 `/api/graph/sync`다. 커밋 본문은 「seven `/graph/*` routes」라
  적었는데, 접두사로 세면 여섯이고 **글로브가 놓치는 하나가 하필 쓰기 진입점**
  (`POST /api/graph/sync`, 수동 동기화)이다 — 은퇴 표면을 접두사로 훑으면 읽기 여섯은
  잡히고 쓰기 하나가 빠진다.
- **부팅 스텝을 실제로 돌리는 기존 테스트도 남겼다.** 새 선언 테스트와 «따로 깨질 수»
  있기 때문이다 — 픽스처나 미래 모듈이 공유 메타데이터에 같은 이름을 다시 등록하면, 어떤
  모델 파일도 그 이름을 언급하지 않는데도 부팅이 표를 만든다.
- prefix 술어(`value_suggest.prefix_conditions`)의 **정확 범위 보장은 약화하지 않았다.**
  소비자가 둘에서 하나(드롭다운)로 줄었지만, 남은 호출자의 Python 재필터는 그 호출자의
  성질이지 함수의 계약이 아니라는 이유가 주석에 그대로 적혔다. 상한이 빠졌을 때 실제로
  범위를 통째로 흘렸던 증거(`q='L\U0010FFFF'`가 `MEAS`부터 전부 반환)는 **그때 라이브였던
  `/graph/nodes/search`에서 측정된 것**으로 시제만 과거로 바뀌었다.

## 아키텍처 영향

「부팅이 요구하는 스키마」의 정의가 **선언 = 요구**로 명시됐다. 은퇴한 표를 «예외 목록»으로
다루는 방식은 드리프트 점검과 구조적으로 양립하지 않는다 — 점검이 읽는 것이 목록이 아니라
메타데이터이기 때문이다. 시스템 표 목록(`ENGINE_TABLES`·드리프트 컬럼 표·미선언 잔여 보고)
셋이 같은 이유로 한 커밋에서 함께 줄었다.

## 검증

- 커밋 본문 주장: `server/scripts/check_schema_drift.py`를 라이브 DB에 돌려 "none".
  ⚠️ 이 워크스테이션은 운영이 아니므로 기록자는 이 항목을 **커밋의 주장**으로만 남긴다.
- 커밋 본문은 「93 + 109 tests pass **across the touched files**」라 적었다. 두 수는 실측이고,
  **둘째 수의 주어가 틀렸다.**
  - 93은 이 커밋이 실제로 건드린 테스트 파일 넷이다 — `test_graph_branch_retired` 12 ·
    `test_value_suggest` 61 · `test_system_schema_drift` 9 · `test_undeclared_schema_report` 11.
  - 109는 이 커밋이 **건드리지 않은** 넷이다 — `test_schema_drift_startup` ·
    `test_declared_key_indexes` · `test_process_supervisor` · `test_duplicate_launcher`.
    변경이 손대는 **부팅 경로를 덮기 때문에** 회귀 확인으로 돌린 묶음이지 「touched files」가
    아니다.
  - 기록자가 같은 날 두 묶음을 각각 다시 돌려 **93 / 109**를 그대로 재현했다(conda
    `assy_manager`, 전부 통과). 즉 숫자는 참이고 그 숫자가 무엇을 셌는지에 대한 문장이
    거짓이었다.

## 그때 남아 있던 것

- 워커의 행 단위 부기 컬럼 세 개(`is_graph_synced` / `needs_graph_rollback` /
  `graph_synced_at`)는 그대로였다. 커밋 본문의 실측으로 16표·48컬럼·32인덱스이고,
  25,565행 중 true였던 적이 **0**이다. 지우면 응답 모양이 바뀌어 클라 재빌드가 필요하다는
  이유로 이 커밋 범위 밖에 두고 판정을 기다리는 상태였다.
- **DROP 날짜가 두 갈래로 커밋됐고, 틀린 쪽은 새로 쓴 텍스트였다.** 이 커밋의 본문과 이
  커밋이 `models.py`에 새로 쓴 묘비 주석은 물리 표 DROP을 **2026-08-16**이라 적었다.
  같은 커밋이 손댄 `docs/architecture/data_model.md`·`docs/overview/SYSTEM_OVERVIEW.md`가
  적고 있던 **2026-08-14 `2ec78b9`**(엣지 1,034,472행·노드 590,885행·약 841 MB)가 **맞는
  쪽이다.** 2026-08-16은 `9851374`(22:47, 「remove retired graph sync branch」)가 워커와
  실행 파일을 걷어낸 날이고 표를 지운 날이 아니다 — 즉 새 텍스트가 **은퇴의 두 라운드를
  한 날짜로 뭉쳤다.** 기록자가 두 해시의 날짜와 제목을 각각 확인했다. 이 항목을 쓰는
  시점에 `models.py` 묘비 주석의 정정(`2026-08-14 2ec78b9` + `9851374`의 역할 명시)은
  워킹 트리에 있었고 아직 커밋되지 않았다.
- `server/migrations/drop_graph_storage_reverse.sql`은 이 커밋이 손대지 않았다. 그 파일
  머리말은 컬럼 집합의 출처를 「`server/database/models.py`의 `GraphNode ~467`,
  `GraphEdge ~484`, `GraphSyncState ~512`」로 지목하는데, **이 커밋이 지운 것이 바로 그
  세 클래스**다 — 되돌리기 스크립트가 없는 코드를 가리키는 채로 커밋이 닫혔다. 이 항목을
  쓰는 시점에 그 머리말의 정정도 워킹 트리에 있었고(미커밋), 출처를
  `git show 2ec78b9:server/database/models.py`로 옮기면서 **이제 그 스크립트의 DDL이
  트리에 남은 유일한 그 모양의 선언**임을 함께 적고 있었다. 모델에서 재생성할 수 없다는
  뜻이라 앵커가 낡은 것보다 무거운 사실이다.
- `docs/architecture/CODE_MAP.md`의 `server/ontology_config.py` 항목은 그 파일이 2026-08-16
  은퇴에서 삭제된 뒤에도 남아 있었다. 이 커밋은 그 사실을 지도에 «재대조 필요» 경고로
  표시만 하고 지나갔다.
