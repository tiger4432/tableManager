# 🖥️ Enrichment Queue 서버측 구현 보고 (Server PM)

> **Status:** ✅ 구현 완료 (커밋·스테이징 미수행 — 지시 준수) | **작성:** 2026-07-25
> **기준:** [ENRICHMENT_QUEUE_SPEC.md](../../docs/spec/ENRICHMENT_QUEUE_SPEC.md) §3~§6·§9 + 총괄 확정 경계 계약(API 2종)
> **이력:** [20260725_113000_enrichment_queue_server_impl.md](../../docs/history/20260725_113000_enrichment_queue_server_impl.md)

---

## 1. 배선 설계 — enrichment_rules ↔ chain_rules = **자동 파생(synthesize)**

전용 저장 계층·전용 실행 경로를 만들지 않았다. `chain_ingestion_worker.load_chain_rules()`가
`enrichment_config.load_enrichment_chain_rules()`를 호출해 **enrichment 규칙 1건당 표준 체인 룰 1건**을 파생·병합한다:

```
enrichment_rules.json 규칙
  → { name: "enrichment_dedup:<규칙명>", trigger_table: source_table, target_table: derived_table,
      mapper_module: "enrichment_mapper", mapper_function: "map_enrichment_dedup",
      is_batch: true, enrichment: <전체 규칙 내장> }
```

- 파생 룰은 일반 체인 룰과 **완전 동형** → HOL 가드·`[Latency]` SLO 계측·3회 재시도·warmup(맵퍼 선import)을 전부 그대로 탄다.
- generic mapper에 룰을 전달하기 위해 `execute_custom_mapper`에 `rule=None` 인자를 추가하고, `inspect.signature`로 **`rule` 인자를 선언한 맵퍼에만** 전달한다 → 기존 맵퍼 `(db, payload)` 시그니처 완전 하위호환(호출부 워커 2곳 갱신, 테스트 영향 0).
- 반영: 웹서버는 요청 시마다 config 재로드(소형 파일 — map-presets 패턴, 무중단), 워커는 SYSTEM_RELOAD 시 `load_chain_rules()` 재호출로 재파생. 별도 config_watcher 미도입(과공학 회피, v1 요건 충족).
- 저장소/사용자 영역 분리: 인프라 코드(`enrichment_config.py`·`enrichment_mapper.py`)는 server 루트(추적됨), 실제 규칙(`server/config/enrichment_rules.json`)·참조뷰 SQL 파일(`server/config/enrichment_queries/*.sql`)은 gitignored 사용자 영역. 템플릿은 `enrichment_rules.json.sample`(추적됨).

## 2. 파일:라인

| 파일 | 성격 | 내용 |
|---|---|---|
| `server/enrichment_config.py` | 신규(추적) | 로더+검증 전체. 스키마 검증 `_validate_rule`(:150~), 참조뷰 SQL 안전성 `_validate_view_sql`(:86~), 체인 룰 파생 `load_enrichment_chain_rules`(:263~), 공개 형태 `to_public_rule`(:288~) |
| `server/enrichment_mapper.py` | 신규(추적) | `map_enrichment_dedup(db, payloads, rule)`(:69~) — 증분 dedup upsert. 영향 키 한정 count 재계산 `_recount_affected_keys`(:37~, 500키 청킹) |
| `server/chain_ingestion_worker.py` | 수정 | `load_chain_rules` 파생 병합(:268~), `_mapper_accepts_rule`(:297~), `execute_custom_mapper(..., rule=None)`(:308~), 호출부 2곳(:384, :391) `rule=rule` 전달, `import inspect`(:6) |
| `server/main.py` | 수정 | `GET /enrichment/rules`(:2696), `GET /enrichment/rules/{rule_name}/references/{index}`(:2707), `/enrichment`·`/enrichment.html` 페이지 라우트(:3237~, admin/map_editor 패턴), SPA fallback 제외 `enrichment/`(:3263) |
| `server/config/enrichment_rules.json.sample` | 신규(추적) | 규칙 작성 템플릿(스펙 §5 인스턴스) |
| `server/tests/test_enrichment.py` | 신규 | 16 테스트(아래 §4) |
| 문서 | 수정 | spec §5 "서버 구현됨" 표기 · [chain_ingestion_guide §4](../../docs/guide/chain_ingestion_guide.md)(규칙 작성 가이드) · [backend.md](../../docs/architecture/backend.md) API 지도/워커 표 · PROJECT_STATUS · history+gen_index |

## 3. API 구현 형태 — 총괄 확정 계약 **그대로** (변경 없음)

```
GET /enrichment/rules
→ {"rules": [{"name","source_table","derived_table","decision_key":[..],
              "target_fields":[..],"list_columns":[..],"reference_views":[{"label"}]}]}
```
- 참조뷰는 label만 노출(쿼리 본문·limit 비노출 — 테스트로 `SELECT` 문자열 미출현까지 확인).

```
GET /enrichment/rules/{rule_name}/references/{index}?params=<urlencoded JSON {col: value}>
→ {"label": str, "columns": [str], "rows": [[...]]}
```
- `params` 키는 해당 규칙 decision_key만 허용(그 외 **400**), 잘못된 JSON **400**, 규칙/인덱스 미존재 **404**.
- 쿼리 정의는 서버 config에만(인라인 `query` 또는 `query_ref` → `config/enrichment_queries/<ref>.sql`). 값은 SQLAlchemy 파라미터 바인딩 전용 + 로드 시 단일 SELECT·`;` 금지·바인드는 decision_key만 검증 → SQL 주입 구조적 불가.
- LIMIT 서버 강제: 서브쿼리 래핑 `LIMIT :bind`, 뷰별 설정(기본 200, 최대 1000 클램프).
- 인증·프리픽스: 기존 `/admin`·`/map-presets` 패턴 준용(별도 인증 없음 — 기존과 동일).

## 4. 테스트 결과

`conda run -n assy_manager python -m pytest server/tests/ -q` → **75 passed, 1 failed** (실패는 기존 알려진 `test_map_presets_api` 1건뿐 — 이슈 #4, 본 작업 무관. 기존 대비 회귀 0).

신규 `server/tests/test_enrichment.py` 16건 전부 통과:
- **로더 8**: 정규화·limit 기본/클램프, 필수 필드 누락 스킵, decision/target overlap 스킵, 미등록 테이블·컬럼 스킵, 파생 키 계약 위반 스킵, 참조뷰 안전성(INSERT/다중문/외부 바인드/traversal 드롭 + 인덱스 정합), 비활성·파일부재, 파생 체인 룰 형태.
- **dedup mapper 4** (fake 아닌 **체인 워커 실경로** `process_chain_transaction_group` E2E): 신규 키 insert(키당 1행·count·대표값·target NULL), **기존 키 user target 보존**(재인제션 후 `wafer_id` 유지 + `chain_ingestion` CellSource가 target 셀에 아예 미기록 = 1차 방어 증명), 재인제션 **멱등 count**(이중 가산 없음), blank 판단키 스킵.
- **API 3**: `/rules` 계약 형태(키 집합 완전 일치·쿼리 비노출), 참조뷰 실행+LIMIT 강제(매치 3행 → limit 2 반환), params 검증 400/400·404/404.
- **기존 경로 재사용 1**: 파생 테이블에 blank 필터 워크리스트 조회(`GET /tables/{t}/data`) → `PUT /tables/{t}/data/updates`(user) 저장 → 결손 필터에서 이탈 + 셀 계약 `{value,...}` 유지 — **기존 엔드포인트 무수정 확인**.

## 5. Client PM에 전달할 주의점

1. **계약은 확정분 그대로 구현됨** — 계획서 §4-A의 `rule_id`는 응답에서 **`name`** 필드다. 참조뷰 항목에 `params[]` 힌트는 없다(계약대로 label만) — 파라미터는 항상 **규칙의 `decision_key` 전체 컬럼 값을 보내면 안전**하다(쿼리가 안 쓰는 키는 무시됨, decision_key 밖 키는 400).
2. 참조뷰 호출 형태: `GET /enrichment/rules/{name}/references/{i}?params=` + `encodeURIComponent(JSON.stringify({equipment: "...", event_time: "..."}))`. 실행 오류(필수 바인드 누락 포함)는 400 + 일반화 메시지.
3. 결손 판정은 "target 컬럼 blank"(`NULL OR ''`)로 서버 필터와 정합 — 계획서 §4-2 제안대로 확정. 파생 행의 target은 NULL로 생성된다(계획서 리스크 4 해소).
4. `enrichment.html`은 dist에 빌드되면 즉시 서빙된다(`/enrichment`, `/enrichment.html` 모두, no-cache 헤더). dev 모드 폴백(`client2/enrichment.html`)도 지원.
5. 배지 카운트: `GET /tables/{derived}/data?limit=1&filters={"<target>":{"type":"blank"}}`의 `total`(5초 캐시) — 확인 완료. `/enrichment/rules`가 404가 아니라 **빈 `rules: []`** 를 반환할 수 있음(규칙 미설정 시) — 배지 가드에 반영 요.
6. 워크리스트 갱신 WS: 체인 dedup upsert는 기존 `batch_row_upsert`(≤100행)/`batch_refresh_required`(>100행) 이벤트로 파생 테이블에 브로드캐스트된다(신규 이벤트 없음).

## 6. 총괄 검수 포인트

1. **경계 계약 준수**: API 형태 계약 그대로(§3). 기존 계약(셀 형태·WS 이벤트·REST) 무변경 — `execute_custom_mapper` 확장은 내부 시그니처이며 하위호환(기본값 인자+조건부 전달).
2. **레이어링 불변식**: target 보존 이중 방어(mapper가 target 미기록 + `chain_ingestion` priority 99 < user 0) — 테스트 `test_dedup_preserves_user_target_on_reingestion`이 두 층 모두 증명.
3. **확장성(1000만 행)**: 증분 처리(이벤트 행만), count는 영향 키 한정 GROUP BY(500키 청킹), business_key 선조립으로 벌크 프리페치 경로 유지, 참조뷰 서버 LIMIT. **운영 주의: count 집계 사용 규칙은 원본 decision_key 복합 인덱스 권장**(가이드 §4.2-4에 명시 — setup 스크립트 반영 여부는 총괄 판단).
4. **회귀 없음**: 경합 배치 1·#0 관련 코드 미접촉, 전체 스위트 기존 실패 1건 외 전부 통과.
5. 커밋·스테이징·라이브 DB 변경 없음(지시 준수). 커밋 시 `.sample`·인프라 모듈·테스트·문서만 스테이징 대상(실규칙 파일은 gitignored).

## 7. 미해결 / 다음 단계

- Client PM: 계획서 ①단계(페이지+워크리스트+컨베이어) 즉시 착수 가능(§5 주의점 반영).
- 통합 후: 스펙 Living 승격 + SSOT §6·DOC_OWNERSHIP 배선(총괄).
- 백로그(선택): count 집계용 decision_key 인덱스를 `setup_db_performance.py`에 규칙 기반으로 추가하는 자동화 — v1 범위 밖으로 판단(운영 규칙 확정 후).
