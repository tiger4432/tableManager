# 인리치먼트 큐 빈 판단키 행 노출 차단 — 서버 조성 queue_filters 단일화

**일시**: 2026-07-28
**작업자**: Server PM
**분류**: fix (사용자 지시: "enrich에 빈 디시전 키는 그냥 넣지마 지금 빈칸도 다 올라오네")

## 현상

결손 큐(인리치먼트 워크리스트)에 판단키(decision_key)가 빈 항목이 노출된다는 사용자 보고. 판단키 없는 행은 참조뷰 바인딩도, business_key 조립도 불가능해 사람이 해소할 수 없다.

## 근본 원인

- 큐 진입 조건이 클라이언트 3곳(enrichment.js 워크리스트 · admin.js 결손 카운트 · ui.js 그리드 배지)에 **각각 수제 조립**돼 있었고, 셋 다 `target_fields blank`만 걸었다 — 판단키 blank 여부는 어디서도 보지 않았다.
- 체인 mapper(`map_enrichment_dedup`)는 빈 판단키 행을 스킵하므로 정상 체인 경로로는 생기지 않지만, **그리드 빈 행 추가(`create_empty_rows_batch`)와 판단키 없는 직접 편집(batch upsert)** 은 판단키 없는 파생 행을 만들 수 있고, 그 행은 target도 비어 있어 곧장 큐에 떴다(격리 환경에서 두 경로 모두 재현).
- 운영 DB 진단(읽기 전용, 16:2x KST): `core_wafer_map` 80행·`line_model_registry` 3행 중 빈 판단키 행 **0건**, 공백-only 0건, 빈 행 생성 이력 0건 — 보고 시점의 행은 이미 사라졌거나 위 경로로 일시 존재했던 것으로 추정(삭제 이력 없음 → 단정 불가). 재발 경로는 실존하므로 구조적으로 차단.

## 해결

- **서버 단일 조성**: `enrichment_config.to_public_rule`이 `queue_filters`(모든 decision_key `notBlank` AND 모든 target_fields `blank`)를 공개 규칙에 포함 — 큐 정의가 서버 한 곳으로 수렴(기존 blank/notBlank 필터 DSL 재사용, 제2의 공백 정의 없음).
- **클라이언트 3곳 배선**: enrichment.js `buildBlankFilters` · admin.js `fetchEnrichmentStatus` · ui.js `updateEnrichmentBadge`가 `rule.queue_filters`를 그대로 사용(부재 시 구식 target-blank 폴백) — 워크리스트/카운트/배지 수치 상시 일치. 필터는 요청에 실려 DB에서 걸러지므로 클라이언트는 숨길 행을 받지 않는다.
- 데이터는 삭제하지 않음(사용자 데이터 규율) — 빈 판단키 행은 테이블 원본 그리드에서 그대로 보이고 큐에서만 제외.

## 검증

- `test_enrichment.py` 신규 `test_worklist_excludes_blank_decision_key_rows`: 빈 행 2종(그리드 빈 행 + 부분 편집) 시딩 → `queue_filters` 조회 total=1(정상 키 행만), 구식 필터라면 total=3 — 결함 축 활성 증명 내장. 계약 테스트에 `queue_filters` 형태 고정.
- 격리(:8081) 라이브: 빈 판단키 행 2건 시딩 → legacy 필터 total=2(빈 키 노출) vs `queue_filters` total=0 → 백필 `--apply` 후 큐 total=3(전부 유효 키), 빈 행은 백필이 건드리지도 늘리지도 않음(blank 원본 1행 스킵 카운트).
- 전체 스위트 860 passed. 클라이언트 3파일 `node --check` 통과(빌드는 병행 에이전트의 dist 영역이라 미실행).

## 계약 메모 (총괄 확인 필요)

`GET /enrichment/rules` 응답 규칙에 `queue_filters` 필드 **추가**(additive). ENRICHMENT_QUEUE_SPEC 반영은 총괄 소관으로 이관.
