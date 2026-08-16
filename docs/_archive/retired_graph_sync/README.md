# Retired graph sync branch

> 🗄️ **SUPERSEDED — 2026-08-16**

이 폴더는 R-2026-08-14-H로 은퇴한 ontology_mapping.json 기반
extract → materialize → graph storage 갈래의 설정 예시와 옛 가이드만 보관한다.

- 실행 코드(graph_sync_worker.py, run_graph_sync.py, ontology_config.py,
  materializer와 sweep 코드)는 제거했다. 복구가 필요하면 Git 이력을 사용한다.
- 현재 개체·관계의 정본은 ledger_events와 원장 어휘다.
- 현재 조회는 /api/ledger/*, 화면은 ledger-graph.html을 사용한다.
- 이 폴더의 JSON을 server/config/로 복사해도 소비자는 없다.
