# 🧩 Enrichment Queue (결손 보정 워크리스트) — 기능 스펙 (Proposal)

> **Status:** 🟢 확정(구현 준비) — §9 핵심 결정 완료 | **작성:** 2026-07-25 | **확정:** 2026-07-25 | **Owner:** 기획(Lead) → 구현 시 Server+Client PM
> **연관 핵심가치:** #1 최소 공수 교정(주) · #2 온톨로지/지식 그래프 기반(직결) — [SYSTEM_OVERVIEW §1](../overview/SYSTEM_OVERVIEW.md)
> 본 문서는 아직 **미구현 제안**이다. 확정·구현 시 Living으로 승격하고 SSOT·DOC_OWNERSHIP에 배선한다.

---

## 1. 목적 — 왜 이 기능이 심장인가

전산 인프라가 약한 R&D 현장의 대량 로그는 **핵심 식별자가 비어 들어온다**(대표: 설비 이력에 `wafer_id` 없음). 이걸 사람이 채워야 하는데, 정답은 규칙으로 못 맞히고 **담당자의 암묵지**로만 나온다.

이 교정은 단순 데이터 수선이 아니다. `wafer_id`가 채워지는 순간 = **설비 이력이 특정 웨이퍼에 묶이는 순간**이고, 그게 바로 엔드게임("불량 WF 선택 → 연관 공정·설비 이력 전부 추적")을 가능하게 하는 **온톨로지의 핵심 링크**다. 즉 이 워크리스트는 **핵심가치 #1의 교정이 그대로 #2의 추적 자산을 생산**하는 최고 레버리지 지점이다.

## 2. 핵심 통찰 — "최소 공수"의 정의

추적이 암묵지라 **자동 정답 맞히기는 레버리지가 아니다.** 유일한 레버리지는:

> **사람이 내려야 하는 "판단의 개수"를 최소로 줄이고, 판단에 필요한 참조를 손 닿는 곳에 놓는 것.**
> = 대량 원본을 **판단키로 dedup** → 유니크 단위만 제시 → 한 번 입력하면 **전체로 fan-out** → 옆에 **참조뷰**를 띄워 암묵지가 빠르게 발동.

## 3. 핵심 모델 (일반화 추상)

"짝 테이블 페어링"이 아니라 **판단키 + 채울 필드 + 참조뷰 N개 + 파급**으로 모델링한다(이래야 케이스에 안 갇힌다).

| 구성요소 | 뜻 | bonding 인스턴스 |
|---|---|---|
| **Source** | 대량 원본 테이블 | `bonding_log` (수천 chip 행) |
| **판단키 (dedup key)** | 사람이 1회 판단하는 단위(1..N 컬럼) | `job_id = (설비, 시간)` |
| **채울 필드 (target)** | 사람이 입력하는 값(자유입력/선택) | `wafer_id` (자유입력) |
| **참조뷰 (decision aids)** | 판단 보조로 항목 옆에 띄우는 뷰/쿼리(0..N, 설정) | lot event 리스트, lot-slot 이력 |
| **파급 (fan-out)** | **논리적 파급** — 판단 1회가 **키 조인**으로 같은 판단키의 모든 Source 행에 적용됨. **원본 행 물리 갱신(write-back) 없음** [결정 2026-07-25] | job의 wafer_id는 파생 테이블에만 저장, chip 행들은 job_id 조인으로 연결 |
| **표시 컬럼 (context)** | 유니크 리스트에 함께 보여줄 단서 | chip 개수, 인접 job, lot 힌트, 원본 로그 라인 |

**일반화 경계(정직한 선):**
- ✅ **골격은 일반화**: `대량 소스 → 판단키 dedup → 필드 입력 → 파급`. 모든 케이스 동일.
- ⚙️ **참조뷰는 설정화**: 어떤 뷰를 옆에 붙일지 config로 선언(케이스마다 다름).
- 🚫 **암묵지 자체는 자동화 안 함**: dedup + 참조 근접으로 "빠르게"만 만든다.

## 4. 워크플로우 (end-to-end)

1. **트리거**: 대량 소스가 인제션됨(파일 워처/체인).
2. **결손 추출**: 규칙이 정의한 판단키 기준으로, `target`이 비어 있는 유니크 판단키를 집계 → **작은 워크리스트 테이블**로 투영(dedup). 표시 컬럼·참조뷰 함께.
3. **집중 편집**: 사람이 워크리스트만 본다(원본 대량 테이블 안 헤맴). 항목 선택 시 참조뷰가 옆에 뜸 → 암묵지로 `target` 입력.
4. **저장 + 논리적 파급**: 입력값은 **파생 테이블에 저장**(원본 log 물리 갱신 없음). 출처는 **레이어링상 `source=user`(priority 0)** 로 기록되어 자동값을 이긴다([data_model](../architecture/data_model.md)). Source의 chip 행들은 판단키 조인으로 연결 — 온톨로지도 관계(`log —(판단키)→ 파생 —(target)→ 객체`)로 추적.
5. **완료 축소**: 채워진 판단키는 결손 필터에서 빠짐 → 남은 개수가 곧 잔여 공수. (진행률 = 채운 키 / 전체 유니크 키.)

## 5. Config 스키마

> ✅ **서버 구현됨 (2026-07-25, Server PM)** — 로더/검증 `server/enrichment_config.py`, dedup mapper `server/enrichment_mapper.py`(체인 룰 자동 파생), API 2종(`GET /enrichment/rules`, `GET /enrichment/rules/{rule}/references/{i}`) `server/main.py`. 규칙 작성법: [chain_ingestion_guide §4](../guide/chain_ingestion_guide.md). 서버 전용 추가 필드: `aggregations`(v1 count만)·`enabled`·참조뷰 `query`(인라인)/`query_ref`(`config/enrichment_queries/*.sql`)/`limit`(기본 200, 최대 1000). Living 승격은 클라 통합 후 총괄이 수행.

기존 설정 주도 패턴(`table_config.json`, `chain_rules.json`)과 정합시킨다.

```jsonc
// enrichment_rules.json — 계약 확정분(2026-07-25): derived_table 필수, pending 의미 고정
{
  "bonding_wafer_attribution": {
    "source_table": "bonding_log",
    "derived_table": "bonding_job_inventory",       // [확정] 파생 영속 테이블(§9-1) — table_config.json에도 등록
    "decision_key": ["equipment", "event_time"],    // 판단키(job_id 구성)
    "target_fields": ["wafer_id"],                  // 사람이 채울 값
    // [확정] 결손 판정 의미: target이 blank(NULL 또는 '') — 서버 blank 필터와 동일 의미
    "list_columns": ["chip_count", "lot_hint"],     // 유니크 리스트 표시 단서
    "reference_views": [                             // 참조뷰 — 쿼리는 서버 config에만, 클라는 판단키 값만 전송, 서버 LIMIT 강제
      { "label": "lot event", "query_ref": "lot_events_by_time" },
      { "label": "lot-slot 이력", "query_ref": "lot_slot_history" }
    ]
  }
}
```

**클라이언트 소비 계약(확정 방향, 상세는 Server PM 위임 시 명세):**
- 🆕 `GET /enrichment/rules` — 규칙 메타(derived_table 포함). 배지·페이지가 소비.
- ♻️ 워크리스트/결손 카운트 — 기존 `GET /tables/{derived}/data` + blank 필터 재사용(신규 없음).
- 🆕 `GET /enrichment/rules/{rule}/references/{i}?params=...` — 참조뷰 조회(서버측 쿼리 정의·LIMIT).
- ♻️ 입력 저장 — 기존 `PUT /tables/{derived}/data/updates`(셀 계약 불변).

## 6. 기존 시스템 통합

- **영속 파생 도메인 테이블** *(§9-1·9-6 결정)*: 파생 테이블은 일회용 큐가 아니라 **실존 도메인 테이블**(log→inventory 관계와 동형). `table_config.json`에 등록되는 **보통 테이블**이므로 레이어링·AuditLog·WS·그리드 편집이 전부 공짜로 붙는다. 투영 자체는 **체인 인제션 규칙 + dedup mapper**로 구현(신규 저장 계층 없음): `Source(log) → dedup mapper → 파생 테이블(유니크 판단키당 1행)`. 사람이 채운 `target`은 파생 테이블에 저장(기존 배치 업서트 `PUT /tables/{t}/data/updates` 재사용). **원본 write-back 없음** — 필요해지면 나중에 체인 규칙 하나로 추가 가능.
- **워크리스트 = 파생 테이블의 결손 필터 뷰**: 별도 저장소가 아니라 `target IS NULL` 필터. 전용 페이지가 이 필터 + 참조뷰 + 컨베이어 입력을 제공.
- **레이어링**: 채운 값은 `CellSource`(source=user, priority 0) + 필요 시 `CellOverwrite`. 자동 재인제션이 사람 값을 덮지 않음(핵심가치 불변식).
- **실시간(#3)**: 워크리스트 소진·파급은 기존 WS 브로드캐스트(`batch_row_*`/`batch_refresh_required`)로 반영. (신규 이벤트 최소화.)
- **온톨로지(#2)**: 채워진 링크(wafer_id)는 `ontology_mapping.json` 경로로 그래프에 반영 → 객체 추적 가능.
- **확장성(1000만행)**: dedup 집계는 판단키 인덱스 + LIMIT/청킹. 원본 전량 로드 금지(뷰포트 가상 로딩).

## 7. 성공 지표 (최소 공수의 정량화)

- **판단 개수 압축비** = 유니크 판단키 수 / 원본 행 수 (낮을수록 좋음; 파급 효과).
- **키당 처리 시간** = 참조뷰 근접 배치 전/후 비교.
- **잔여 공수** = 미채운 유니크 키 수(워크리스트 길이).
- (v2) **자동 제안 채택률** — 아래 범위 밖.

## 8. 범위

- **v1 (본 스펙)**: 골격(dedup 워크리스트 + 자유입력 + 참조뷰 + 파급 + 레이어링 병합). 설정 주도.
- **v2 (별도, 나중)**: lot event·lot-slot 상관으로 `target` **후보 추정 제안**(어시스트 층). 암묵지를 대체하지 않고 보조만.

## 9. 설계 결정 (2026-07-25 확정 — 잔여는 구현 설계로 위임)

1. ✅ **파생 = 별도 영속 테이블.** 일회용 큐가 아니라 실존 도메인 테이블(log→inventory 동형). 체인 dedup mapper로 투영. — §6 반영.
2. ✅ **UI = 별도 페이지** (`enrichment.html`, 4번째 진입점 — map_editor 선례). 3구역 레이아웃: 워크리스트(결손 필터) | 판단·입력(컨베이어: 입력→Enter→다음) | 참조뷰. **+ 메인 그리드에 "결손 N건" 배지** → 클릭 시 진입. (발견은 그리드, 처리는 전용 화면.)
3. ✅ **원본 write-back 없음.** target은 파생 테이블에만 저장, Source와는 판단키 조인으로 연결(논리적 파급). 온톨로지도 관계로 추적. 필요 시 나중에 체인 규칙 1개로 fan-out 추가 가능.
4. ✅ **소유 분할**: Server PM = dedup mapper + 파생 테이블 config + (필요시) 결손 카운트 API. Client PM = enrichment 페이지 + 그리드 배지. **신규/변경 REST는 경계 계약 → 총괄이 설계·조율.** 확정 시 DOC_OWNERSHIP 배선.
5. ⚙️ *구현 설계로 위임:* 연속 판단키 dedup granularity(config `granularity` 옵션), `reference_views` 쿼리 정의·파라미터 바인딩 방식, 재인제션 시 사람값 보존 검증(레이어링이 커버 — 테스트로 확인).

---
*확정 시: SSOT §6 서브시스템 지도에 추가 · DOC_OWNERSHIP 배선 · README 인덱스 등록 · Living 승격.*
