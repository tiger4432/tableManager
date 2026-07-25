# Enrichment Queue 서버측 구현 — config 로더 + dedup mapper(체인 자동 파생) + API 2종

> **날짜:** 2026-07-25 | **작업자:** Server PM | **연관:** [spec/ENRICHMENT_QUEUE_SPEC.md](../spec/ENRICHMENT_QUEUE_SPEC.md)(🟢 확정), [Client_enrichment_plan.md](../../agent_workspace/reports/Client_enrichment_plan.md)

## 현상 / 목표

스펙 확정된 Enrichment Queue(결손 보정 워크리스트)의 서버측 전량 구현. 핵심가치 #1(최소 공수 교정)·#2(온톨로지 링크 생산)의 최고 레버리지 기능. 요구: ① `enrichment_rules.json` config 지원, ② 체인 인프라 재사용 dedup mapper(신규 저장 계층 금지), ③ 경계 계약 확정분 API 2종, ④ `enrichment.html` 서빙, ⑤ 기존 워크리스트/저장 경로 무변경 확인.

## 설계 결정 (배선)

**enrichment_rules ↔ chain_rules 배선 = "자동 파생(synthesize)" 방식.**
`chain_ingestion_worker.load_chain_rules()`가 `enrichment_config.load_enrichment_chain_rules()`를 호출해 enrichment 규칙마다 표준 체인 룰 1개를 파생·병합한다:

```python
{
  "name": "enrichment_dedup:<rule_name>",
  "trigger_table": rule["source_table"], "target_table": rule["derived_table"],
  "mapper_module": "enrichment_mapper", "mapper_function": "map_enrichment_dedup",
  "is_batch": True, "enabled": True,
  "enrichment": rule,   # 전체 규칙을 내장 — generic mapper가 참조
}
```

- 파생 룰은 일반 룰과 완전 동형이므로 **체인 파이프라인(HOL 가드·[Latency] SLO 계측·재시도·warmup)을 그대로 탄다** — 신규 실행 경로 없음.
- generic mapper에 룰을 전달하기 위해 `execute_custom_mapper(..., rule=None)` 확장: `inspect.signature`로 맵퍼가 `rule` 인자를 선언한 경우에만 전달 → **기존 맵퍼 (db, payload) 시그니처 완전 하위호환**.
- `enrichment_mapper.py`/`enrichment_config.py`는 저장소 추적 인프라 코드로 server 루트에 배치(사용자 영역 `server/mappers/*`·`server/config/*`는 gitignored — 실제 규칙 파일만 사용자 영역).
- 반영 경로: 웹서버는 요청 시마다 config 재로드(파일 소형 — map-presets 패턴), 워커는 SYSTEM_RELOAD 시 `load_chain_rules()` 재호출로 재파생 → 무중단 반영, 별도 워처 불필요(과공학 회피).

## 해결 (구현 상세)

1. **`server/enrichment_config.py`(신규)** — 로더+스키마 검증. 필수 필드(`source_table`/`derived_table`/`decision_key`/`target_fields`), table_config 대조(테이블·컬럼 존재), **파생 테이블 키 계약**(`composite_key_source ⊆ decision_key` 또는 `business_key ∈ decision_key`) 강제 — 위반 규칙은 로그와 함께 스킵. 참조뷰 SQL 검증(단일 SELECT만·`;` 금지·바인드는 decision_key만·`query_ref` 파일명 traversal 가드) — 무효 뷰는 로드 시 제거되어 `/rules` 목록과 `/references/{i}` 인덱스가 항상 정합.
2. **`server/enrichment_mapper.py`(신규)** — `map_enrichment_dedup(db, payloads, rule)`. 배치 payload에서 decision_key 유니크 조합 추출(**증분** — 이벤트 행만, 원본 풀스캔 없음) → 키당 1행 upsert 아이템 생성. `business_key_val`을 선(先)조립하여 `apply_batch_updates`의 벌크 프리페치(N+1 방지)를 태움. **target_fields는 updates에 절대 미포함**(1차 방어) + source `chain_ingestion`은 user(priority 0)에 항상 패배(2차 방어 — 레이어링). count 집계는 "영향 키 한정" `GROUP BY` 재계산(500키 청킹, `tuple_().in_`) → 재인제션에도 멱등(이중 가산 불가).
3. **API 2종(`server/main.py` :2688~, 경계 계약 그대로)** — `GET /enrichment/rules`(참조뷰는 `{label}`만 노출, 쿼리 본문·limit 비노출), `GET /enrichment/rules/{rule}/references/{i}?params=<urlencoded JSON>`(decision_key 외 파라미터 400, 파라미터 바인딩 전용 — 주입 구조적 불가, 서브쿼리 래핑 `LIMIT :bind` 강제(기본 200/최대 1000), 규칙·인덱스 미존재 404).
4. **`enrichment.html` 서빙** — `/enrichment`·`/enrichment.html` 전용 라우트(admin/map_editor 패턴: dist → dev 폴백 → 404) + SPA fallback 제외 목록에 `enrichment/` 추가(미정의 API 하위경로가 index.html로 오인 서빙되는 것 방지).
5. **`server/config/enrichment_rules.json.sample`(신규)** — 규칙 작성 템플릿.

## 검증

- `conda run -n assy_manager python -m pytest server/tests/ -q` → **75 passed, 1 failed** — 실패는 기존 실패로 알려진 `test_map_presets_api`(이슈 #4, 본 작업 무관) 단 1건.
- 신규 `server/tests/test_enrichment.py` 16건: 로더 검증 8(필수 필드·overlap·미등록 테이블/컬럼·키 계약·참조뷰 안전성·비활성/파일부재·파생 룰 형태), dedup mapper 4(**체인 워커 실경로** `process_chain_transaction_group` E2E — 신규 키 insert/기존 키 user target 보존+chain_ingestion 소스 미기록/재인제션 멱등 count/blank 판단키 스킵), API 3(계약 형태·LIMIT 강제·params/404/400), 기존 경로 재사용 1(blank 필터 워크리스트 → user 저장 → 결손 이탈 — **기존 엔드포인트 무수정**).
- 사이드 이펙트 분석: `execute_custom_mapper` 시그니처 확장은 기본값 인자 + 조건부 전달로 기존 호출부(워커 2곳·`test_chain_payload_resilience`) 영향 0. `load_chain_rules` 반환 형태 불변(리스트 append). 경계 계약(셀 형태·WS 이벤트·기존 REST) 불변. 경합 배치 1(C-1/2/3/5)·#0(F1~F3·인라인·웜업) 코드 미접촉 — 전체 스위트 회귀 없음으로 확인.

## 잔여 / 주의

- 클라 통합 대기: `client2/enrichment.html`(Client PM). dist에 파일이 생기면 서빙 즉시 동작.
- 운영 규칙 작성 시: 대규모 원본에서 `aggregations: count` 사용하려면 decision_key 복합 인덱스 생성 권장(가이드 §4.2-4).
- Living 승격(SSOT §6·DOC_OWNERSHIP 배선)은 클라 통합 후 총괄 수행.
