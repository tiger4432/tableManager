# Ledger Graph — LOT 전용 검색을 전체 개체 카탈로그로 교체

## 판정

그래프의 시작점은 LOT 검색창 하나가 아니라 원장 어휘가 등록을 요구하는 **모든 개체 인스턴스**다. 화면은 검색 가능한 타입과 해당 타입의 실제 목록을 먼저 보여 주고, 어느 항목이든 클릭하면 그 개체 중심 원장 주장을 펼친다. 합성 신원이라 `register`가 금지된 `Die`는 목록에 나타나지 않는다.

## 구현

- `GET /api/ledger/entities`: Equipment·Lot·Product·Recipe·Wafer·WaferLeg 타입을 어휘에서 생성하고, 선택 타입의 `register` 인스턴스를 40개 단위 keyset page로 답한다.
- `GET /api/ledger/explore_entity`: 카탈로그의 opaque id를 검증해 어느 타입이든 `register`·`processed_with`·`measured`·`observed` 등 원장 주장을 노드로 연다. Lot만 기존 분기 보존 보행을 재사용한다.
- `client2/src/ledger_graph/entity_catalog.js`: 타입 선택, 서버측 검색, `더 보기`, 요청 취소와 stale 응답 폐기를 소유한다. 그래프를 열어도 출발 목록과 검색어는 유지한다.
- `idx_ledger_register_search`: register JSON contains 검색용 partial trigram 인덱스. 없으면 503으로 거절한다.
- `idx_ledger_subject_entity`: structured `(subject_type, subject_keys)` exact frontier join 인덱스.

## 실측

- 개발 DB 인덱스 자식 합계: 검색 656 kB, subject exact 13 MB.
- 라이브 카탈로그: Lot·Recipe·Wafer·WaferLeg `ready`, Equipment·Product는 정직한 `empty`.
- WaferLeg `SYN-CX-BW-001 / HBM-B_LOW-P`: 6 nodes·5 edges, `register`·`processed_with`·`observed` 확인.
- 집중 서버 테스트 10 passed, 클라이언트 하네스 37 assertions, 전체 56 harness 중 gated 51 green·known-red 5 불변, Vite 100 modules build 성공.

## 파일

- `server/ledger_catalog.py`, `server/ledger_explorer.py`, `server/ledger_trace_router.py`
- `server/ledger/schema.py`, `server/migrations/add_ledger_entity_catalog_indexes.py`
- `client2/ledger-graph.html`, `client2/src/ledger_graph/main.js`, `entity_catalog.js`, `styles.css`
- `server/tests/test_ledger_catalog.py`, `client2/tests/ledger_graph_harness.mjs`
