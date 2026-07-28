# 인리치먼트 소급 적용(백필) 스크립트 — 규칙 이전 원본 행의 파생 행 생성

**일시**: 2026-07-28
**작업자**: Server PM (backfill_enrichment)
**분류**: feat (운영 도구)

## 현상

인리치먼트 큐는 outbox 증분 구동이다 — `map_enrichment_dedup`은 변경 행 payload만 소비하므로, **규칙을 선언하기 전에 인제션된 원본 행은 파생 행을 영원히 만들지 않는다**. 결손 워크리스트가 그 판단키 조합을 볼 방법이 없다. Chain Replay(R1)는 미구축 상태에서 소급 적용이 즉시 필요했다.

## 해결

신규 운영 CLI `server/scripts/backfill_enrichment.py` (dry-run 기본, `list_undeclared_tables.py` 규율):

```
conda run -n assy_manager python server/scripts/backfill_enrichment.py <rule> [--apply] [--limit N] [--force-disabled] [--chunk-size N]
```

- **스캔**: 원본 테이블을 `row_id` keyset 페이지네이션(기본 1000행 청크)으로 1회 순회 — 전량 로드 없음(1,000만 행 규율). blank 판단키 행은 mapper와 동일 프리미티브(`_cell_value` + `crud.clean_str_value`)로 스킵·집계.
- **디프**: 파생 테이블의 `business_key_val`(업서트 정체성) 집합과 대조 — 기존 파생 행은 배치에 아예 넣지 않는다(값 결손은 큐, 행 부재는 백필).
- **적용(`--apply`)**: 신규 조합의 행만 **실제 mapper**(`map_enrichment_dedup`) + **실제 쓰기 경로**(`crud.apply_batch_updates`)로 청크 단위 커밋 — 그룹핑/집계/키 조립의 2차 구현 없음. mapper 출력에 provenance만 스탬프: `source_name/updated_by = "enrichment_backfill"`(미등재 우선순위 99 → user(0) 불가침, 이후 `chain_ingestion`(4)이 자연 갱신).
- **outbox**: 정상 `stage_event` 경로로 발화 → 그래프 워커가 새 행을 승격. 파생 테이블 이벤트는 규칙 트리거(소스 테이블)와 불일치라 동일 규칙 재점화 불가; 체인 워커 쓰기는 전부 `chain_ingestion` 태그로 루프 가드에 걸리므로 무한 사이클 구조적 불가.
- **거부 규율**: 규칙 미존재/파일 미존재/비활성(`--force-disabled` 없이는 거부)/로더 거부(사유 명시, `enrichment_config._validate_rule` 직접 사용 — 공개 API는 사유를 로그로 삼킴) 전부 사유와 함께 즉시 실패.

## 검증

- `server/tests/test_backfill_enrichment.py` 11건 전부 통과 — dry-run 수치·무쓰기, apply 정확 생성, 기존 파생 행 바이트 불변(결함 축 활성 픽스처: 기존 조합에 미체인 원본 행 추가 → 버그면 chip_count 2→3), provenance/우선순위, outbox 재점화 무해성(실제 `process_chain_transaction_group` 재실행 no-op), 멱등 재실행 0건, `--limit` 상한, 거부 4종.
- **결함 주입 2회**: 기존행 필터 제거 → 4건 실패, blank 스킵 제거 → 2건 실패 — 테스트가 신규 코드 경로를 실제로 실행함을 증명 후 원복.
- 전체 스위트 859 passed.
- **격리(:8081/assy_qa) E2E**: 스크래치 테이블·규칙으로 7행 시딩(규칙 선언 전) → dry-run(new 3, blank skip 1) → `--apply`(3행 생성, count 3/2/1, wafer_id NULL, 소스명 `enrichment_backfill`) → 재실행 dry-run(new 0, already 3) → 라이브 체인 워커가 파생 이벤트를 no-op 소비(`processed_chain=true`, 행 수 불변). 종료 후 스크래치 전부 원복. :8080 무접촉.

## 문서

- `docs/guide/config/enrichment_rules.md` §4-bis 소급 적용 절차(값 결손=큐 / 행 부재=백필 분담) 추가.
