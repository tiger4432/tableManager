# 🧩 Enrichment Queue (결손 보정 워크리스트) — 리빙 스펙

> **Status:** 🟢 Living - **v1 구현 완료(2026-07-25), UI는 2026-08-11부터 재배치** | **Last-verified:** 2026-08-11 (🔴 **§v1 구성의 「`enrichment.html` 컨베이어」는 삭제됐습니다** — `1e29078`이 배지·nav를 걷고 `ab36fab`이 페이지와 vite 진입점을 지웠습니다. 결손 target을 순차 입력하던 워크플로는 **대체 없이 소멸**(대체가 아니라 삭제 — 커밋 스스로 "no replacement was built for it"이라고 적습니다). 참조뷰 절반만 메인 그리드 사이드바(`enrichment_reference_view.js`, Cell/Row History 옆 탭)로 이식됐고, 같은 백엔드 API를 재사용합니다. 이 스펙의 §5.x 서술(당첨 로직·규칙 config)은 여전히 유효합니다 — 낡은 것은 **UI 접근 경로**뿐입니다. **이전:** 2026-08-05 (**[사용자 재정] §5.1 재작성 - 판단키가 일부만 있으면 「남은 키로 판단한다」, 사람이든 스윕이든 똑같이.** `auto_confirm`이 **이미 동의**이므로(규칙별·기본 OFF·선언자가 무인 쓰기를 수락) 그 아래 두 번째 관문은 config가 정한 것을 코드가 다시 판정하는 일이다 - 2026-08-04에 세웠던 `keyed_queue_filters` 쓰기 가드를 **좁히는 게 아니라 걷어냈다**. 남는 거절은 산술뿐(`missing_bind` 뷰별 · **`no_decision_key`** 신설: 아무것도 안 남았을 때). 부분 판단키로 쓴 셀은 **기존 provenance로** 구별된다 - `cell_sources.source_name = enrichment_auto_confirm_partial_key`(미등재 = 99, 평범한 자동확정과 **같은 서열**), 신규 필드 없음) | **이전:** 2026-08-04 (**[N36 · 사용자 재정] §5.1 재작성 - 큐 술어에서 판단키 `notBlank`를 뺐다**: 진행률 분모(무필터 전체 행)와 잔여가 서로 다른 모집단을 세어 **판단키가 빈 행이 「답한 것」으로 계산**됐다(실측 33% → 100%, 데이터 변경 0). 그 행들은 이제 워크리스트에 **뜨고**, 뒤로 정렬되고, **「판단키 없음 N건」**으로 이름 붙는다. 판단키 술어는 사라지지 않고 **`keyed_queue_filters`**라는 이름을 얻어 **쓰기 경로(① 자동 확정 스윕)의 술어로 남았다** - 부분집합 바인드 뷰에서 빈 키가 후보 1개를 만들어 오답이 쓰이는 것이 실증됐다. ④ 분류에 `blank_decision_key` 계급 신설) | **이전:** 2026-07-30 (**[F9 후속 QA 수리] §5.2 갱신 - ⓐ 참조 질의를 SAVEPOINT로 격리**(Postgres에서 실패한 프로브가 트랜잭션을 abort시켜 `candidate_column_missing`이 도달 불가였고, 오염된 세션이 체인 워커를 통과해 outbox 부기 커밋을 무산시켜 그룹이 영원히 재처리됐다 - 읽기 전용 실측) **ⓑ `distinct_truncated` 거절 신설**(집계 절단이 `clean_str_value` 접기로 1개 값으로 접히면 `single`로 자동 확정될 수 있었다) **ⓒ `scanned`를 그룹 절단 전 값으로 정정**. 직전 [F9] **§5.2-bis 신설** - 선언의 효과를 어드민에 노출(`/admin/config/resolve`·드라이런), 후보 프로브가 뷰 `limit`에 잘리던 결함 수리(`probe_truncated` 신설), **경계 계약 1건 변경**: `GET /enrichment/rules`에 가산 필드 `candidate_for`(총괄 승인). 직전: §5.2 ① 후보 1개 자동 확정 · §5.3 ② 룰 승격 제안 · §5.4 ④ 결손 원인 분류) | **이전:** 2026-07-28 (`1fefd12`: §5.1 `queue_filters`) | **Owner:** Server PM(mapper·config·API) + Client PM(페이지·배지), 계약은 총괄
> **연관 핵심가치:** #1 최소 공수 교정(주) · #2 온톨로지/지식 그래프 기반(직결) — [SYSTEM_OVERVIEW §1](../overview/SYSTEM_OVERVIEW.md)
> **v1 구성 (2026-07-25, 출하 당시):** 서버(`enrichment_config.py`·`enrichment_mapper.py`·API 2종) + 클라(~~`enrichment.html` 컨베이어~~ + ~~참조뷰 탭~~ + ~~메인 그리드 결손 배지~~ — **셋 다 2026-08-11에 재배치/삭제**, 아래 참조). E2E 실동 검증 완료(스모크 규칙 `line_model_owner_attribution`). 규칙 작성법: [chain_ingestion_guide §4](../guide/chain_ingestion_guide.md).
> **UI 현황 (2026-08-11):** 컨베이어(입력)는 **소멸**(그리드 직접 편집으로 흡수, 대체 화면 없음). 참조뷰(조회)는 **메인 그리드 History 패널의 사이드바 탭**으로 이식(`client2/src/enrichment_reference_view.js` — 셀 선택 기반, 같은 백엔드 API). 결손 배지는 **삭제**(그리드 필터 `?enrichment_queue=<규칙명>`은 URL로는 여전히 유효, 전용 UI 컨트롤 없음).
> **2026-08-15 가산:** 선택적 `claim_contract`와 `server/enrichment_actions.py`가 착지했다. 기존 column queue는 그대로이고, 계약이 있는 rule의 결손은 Evidence Graph에서 `Claim --needs_enrichment--> Enrich Action`으로도 보인다. Action은 원장 저장물이 아닌 재계산 투영이며 통합 `/enrichment/worklist` API는 아직 미구현이다.

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
5. **완료 축소**: 채워진 판단키는 결손 필터에서 빠짐 → 남은 개수가 곧 잔여 공수. **진행률 = (파생 테이블 전체 행 − 잔여 행) / 파생 테이블 전체 행** — 분자·분모 모두 **행**이다. 🔴 **「키」로 읽지 말 것**(2026-08-04 정정): 분모는 무필터 `total`(행 카운트)이고, 「유니크 키 수」와 같아지는 것은 `composite_key_source == decision_key`일 때뿐인데 로더는 **진부분집합도 허용**한다(그 경우 판단키 여럿이 1행으로 접힌다). 같은 문장을 두 술어로 세면 §5.1이 고친 결함이 그대로 돌아온다.

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
- 🆕 `GET /enrichment/rules` — 규칙 메타(derived_table 포함). 배지·페이지가 소비. **[2026-07-28 `1fefd12`] `queue_filters` · [2026-08-04] `keyed_queue_filters` · [2026-08-05] `queue_predicate`** — §5.1 / **§5.1-bis**(큐를 이름으로 요청한다) 참조.
- ♻️ 워크리스트/결손 카운트/진행률 — 기존 `GET /tables/{derived}/data` 재사용(신규 엔드포인트 없음). **[2026-08-05] 큐 조건은 필터 dict가 아니라 라우트 파라미터 `?enrichment_queue=<규칙명>`이다**(§5.1-bis). 「판단키 없음 N건」도 차분이 아니라 `&enrichment_queue_scope=blank_key`의 `total`로 직접 읽는다.
- 🆕 `GET /enrichment/rules/{rule}/references/{i}?params=...` — 참조뷰 조회(서버측 쿼리 정의·LIMIT).
- ♻️ 입력 저장 — 기존 `PUT /tables/{derived}/data/updates`(셀 계약 불변).

### 5.0-bis `claim_contract` — column 결손을 Claim 행동으로 읽는 선택 계약 (2026-08-15)

기존 rule에 선택적으로 `claim_contract`를 붙일 수 있다. 최소 계약은 `version`, `label_ko`,
원장 Claim과 decision key를 정확히 연결하는 `anchor`, 모든 target을 덮는 `slots`, 각 target의
공급 경로를 선언하는 `sources`다. 상세 스키마는
[Claim Requirement & Worklist §3](./CLAIM_REQUIREMENT_WORKLIST_SPEC.md)가 소유한다.

- 계약이 없으면 legacy column Enrichment로 그대로 작동한다.
- 계약이 잘못되면 그 계약만 rejection에 남기고 rule 자체는 유지한다.
- 공급 source가 선언된 빈 target은 decision key별 `resolve_claim` Action이 된다.
- 공급 source가 없는 target은 row마다 반복하지 않고 rule-level `declare_claim_source` Meta Action이 된다.
- table 계약이 배포 검증에 실패하면 derived row를 읽지 않고 `repair_enrichment_contract` Action이 된다.
- 그래프 읽기는 candidate reference SQL을 실행하지 않는다. 후보 조회·확정은 명시적 다음 행동이다.

### 5.1 `queue_filters` — "큐 항목"의 단일 술어는 서버가 조성한다 (2026-07-28 · `1fefd12`, **2026-08-04 재정**)

`GET /enrichment/rules`의 각 규칙에 **추가 응답 필드 두 개**가 실립니다 — 범용 `/tables/{t}/data` 필터 DSL 객체입니다:

```
queue_filters       = { <모든 target 필드>: {type: "blank"} }
keyed_queue_filters = queue_filters ∪ { <모든 decision_key 컬럼>: {type: "notBlank"} }
```

- ⚠️ **[2026-08-05] 이 절이 말하는 "유일한 정의"는 §5.1-bis로 옮겨갔습니다.** 아래 서술은 **단일 target 규칙에서만** 참이고, 다중 target 규칙에서 `queue_filters`는 큐가 아니라 「전 target blank」라는 **일반 필터**입니다. 큐 자체는 이제 이름으로 요청합니다 — **§5.1-bis를 먼저 읽으십시오.** 이 절은 그 필터가 여전히 무엇인지, 그리고 판단키 술어가 왜 여기서 빠졌는지(N36)를 남겨 둡니다.
- **`queue_filters`**의 표시 소비처 네 곳(워크리스트 `enrichment.buildBlankFilters` · 어드민 카운트 `admin.fetchEnrichmentStatus` · 메인 배지 `ui.updateEnrichmentBadge` · 진행률 잔여)이 전부 이 객체를 그대로 씁니다 — **클라가 §5.1-bis로 옮겨가기 전까지는.**
- 🔴 **왜 판단키 `notBlank`가 여기서 빠졌나 (2026-08-04 사용자 재정 · N36)**: 진행률 **분모**(`enrichment.fetchTotalAll`)는 **필터를 하나도 걸지 않는** 파생 테이블 전체 행 수인데, 잔여만 판단키를 요구하니 **두 수가 다른 모집단**을 셌습니다. 그래서 판단키가 빈 행은 분모에 있고 잔여에서 빠져 **「답한 것」으로 계산**됐습니다. 실측: **데이터 변경 0 · 설정 한 줄로 33% → 100%**, 워크리스트는 0행인데 실제 미답 2건이 테이블에 앉아 있었습니다. 이제 양쪽 다 **행**을 셉니다.
- 🔴 **빈 판단키 행은 이제 워크리스트에 뜹니다 — 의도된 결과입니다.** 판단키 누락은 **인제션 단계 결함**이고, 보이지 않는 결함은 영영 고쳐지지 않습니다. 다만 그 행은 **판단할 수 없습니다**(참조뷰는 판단키 **값으로** 조회되므로 빈 값은 근거를 못 찾습니다). 그래서:
  - **순서**: 컨베이어는 처리 가능한 행을 먼저 소비하고 판단 불가 행은 **뒤로 내려갑니다**(각 구획 안에서 서버의 `row_id` 순서는 그대로). 컨트롤도 모드도 없습니다 — 순서 **규칙**이 바뀐 것입니다.
  - **이름**: 헤더에 **「판단키 없음 N건」** 배지, 그리고 그 행을 선택하면 상세·참조뷰가 **이름 있는 거절**로 답합니다(빈 결과와 구별되어야 합니다 — 「근거가 없다」와 「물어볼 수가 없다」는 다른 사실입니다).
  - **수치**: `N = queue_filters.total − keyed_queue_filters.total`. 둘 다 논리곱 필터라 기존 DSL이 그대로 번역합니다(**신규 엔드포인트 없음**). 판단키 컬럼 간 OR은 필터 DSL이 표현하지 못하므로(한 컬럼 안의 조합만 가능) **차분**으로 얻습니다. 서버가 `keyed_queue_filters`를 주지 않으면 클라는 **아무 말도 하지 않습니다**(「0건」은 주장입니다).
- 🔴 **[2026-08-05 사용자 재정] `keyed_queue_filters`는 더 이상 쓰기 경로의 술어가 아닙니다.** 판단키가 **일부만** 있으면 **남은 키로 판단합니다 - 사람이든 스윕이든 똑같이.** 근거는 `auto_confirm`이 **이미 동의**라는 것입니다: 규칙별이고, 선언하지 않으면 꺼져 있고, 선언한 사람은 그 규칙에 대해 무인 쓰기를 받아들인 것입니다. 그 아래에 관문을 하나 더 두는 것은 **config가 정한 운영 동작을 코드가 다시 판정**하는 일입니다. 그래서 ①의 소급 스윕은 `SCOPE_QUEUE`(= `queue_filters`)를 걷습니다.
  - 남는 거절은 **정책이 아니라 산술**이고, 근거가 있는 자리(`resolve_target_candidate`)에서 이름으로 답합니다 - 빈 컬럼을 **바인드하는** 뷰는 물어볼 수가 없으므로 `missing_bind`(종전 그대로), 판단키가 **전부** 비었으면 물어볼 것 자체가 없으므로 **`no_decision_key`**(신설). 후자는 프로브 **이전에** 판정합니다: 아무것도 바인드하지 않는 뷰는 자기 가드가 없어 규칙 전체에 대한 상수를 돌려주기 때문입니다.
  - 판단키의 **부분집합**에만 바인드하는 뷰(②가 생성하는 형태이자 실 config의 뷰 #1)에서 살아남은 키로 후보 1개가 나오는 것은 이제 **결함이 아니라 의도**입니다. 회귀 그물은 `test_auto_confirm_sweep_works_a_partial_key_and_stamps_what_it_did`(썼는가 + 무슨 이름으로 썼는가)와 `test_a_wholly_blank_key_is_refused_by_name_and_writes_nothing`(아무것도 안 남았을 때).
  - **부분 판단키로 결정된 셀은 뒤에 구별됩니다** - 새 필드가 아니라 **기존 provenance**로. `cell_sources.source_name`이 `enrichment_auto_confirm_partial_key`(역시 `SOURCE_PRIORITY` **미등재 = 99**, 평범한 자동확정과 **같은 서열**)가 되어, 빠졌던 키 컬럼이 나중에 채워졌을 때 "어느 행이 온전한 키 없이 결정됐나"가 **추정이 아니라 질의**가 됩니다.
  - ②(승격)는 여전히 `keyed_queue_filters`를 걷습니다. 이것은 잔재가 아닙니다 - ②는 **해소된** 행에서 "이 키가 이 값을 정했다"를 배우는데, 키의 일부가 없던 행은 **없던 컬럼에 판단을 귀속**시키게 됩니다.
### 5.1-bis `queue_predicate` — 큐는 필터 dict이길 그만두고 **이름 붙은 서버측 술어**가 됐다 (2026-08-05 사용자 재정)

**결함(실측)**: target이 2개 이상인 규칙에서 `queue_filters`는 「target이 *하나라도* 비었다」가 아니라 「*전부* 비었다」였습니다. 조성은 컬럼당 `{type:"blank"}` 하나이고 소비처는 전부 그것을 **논리곱**으로 겁니다(`_queue_condition`의 `and_`, `main.apply_column_filters`의 컬럼당 `query.filter`). 그래서 **한 컬럼만 채워지면 나머지가 빈 채로 그 행이 큐에서 빠졌습니다** — N36과 같은 모양(일감이 남았는데 「답한 것」으로 계산됨). 실 config의 **두 규칙 다 target이 2개**이고 `confirm_keys`는 이미 컬럼 단위로 쓰므로(§5.2-ter) **오늘 도달 가능한 상태**였습니다.

**재정**: 큐는 임의의 필터가 아니라 **하나의 질문**(「어느 행에 아직 일감이 있나」)이고, 규칙이 이미 그 답에 필요한 모든 것을 선언합니다. 그것을 클라이언트가 보는 필터 dict로 표현한 것이 **정의를 캘러에 둔** 것이고, 그래서 의미가 「그 규칙이 target을 몇 개 선언했나」에 좌우됐습니다. 그러므로 — **클라가 이름으로 요청하고 서버가 규칙의 `target_fields`에서 계산한다.**

```
GET /tables/{derived}/data?enrichment_queue=<규칙명>[&enrichment_queue_scope=<스코프>]

queue     = target 중 **하나라도** blank            ← 기본값. 이것이 큐다
keyed     = queue AND 모든 decision_key notBlank
blank_key = queue AND decision_key 중 하나라도 blank
resolved  = 모든 target notBlank AND 모든 key notBlank
```

- **단일 구현**: `enrichment_config.queue_predicate_condition`. 워크리스트·진행률 잔여·메인 배지·어드민 카운트는 위 라우트로, `classify_queue`·②의 걷기·①의 스윕은 `enrichment_analysis._queue_condition`(이 함수의 **조회 래퍼**)로 도달합니다. **정의가 두 벌이 될 수 없습니다.**
- **DSL을 넓히지 않은 이유**: 수리에는 **컬럼 간 OR**이 필요한데 공개 필터 DSL은 그것을 표현하지 못합니다(`operator`/`conditions`는 **한 컬럼 안**의 조합). DSL을 넓히면 그 표면을 **기존 캘러 전부가 상속**합니다 — 한 규칙만 묻는 질문 하나를 위해서. 질문 하나, 구현 하나.
- **`queue_filters`·`keyed_queue_filters`는 그대로 실립니다(가산적)** — 일반 필터로서 종전 의미(전 target blank)를 유지하고, 그 형태로 이미 묻고 있던 곳은 계속 같은 답을 받습니다. 클라는 **`queue_predicate` 필드의 부재**로 구버전 서버를 판정합니다.
- **`keyed` + `blank_key`가 `queue`를 정확히 분할**하므로 「판단키 없음 N건」은 두 total의 **차분이 아니라 직접 조회**가 될 수 있습니다(같은 술어에서 나오므로 어긋날 수 없습니다). `resolved`는 이제 `queue`의 **정확한 여집합**입니다 — 종전 「전부 blank」 철자에서는 부분 채움 행이 **양쪽 어디에도 없었고**, 결함이 산 자리가 정확히 그 틈입니다.
- 🚧 **경계 계약 (가산적 · 서버 착지 2026-08-05 · 클라 미착지)**: 라우트 파라미터 2개와 응답 필드 `queue_predicate`가 신설됐습니다. **클라가 바꿔야 하는 것** — ⓐ `enrichment.buildBlankFilters`/`fetchWorklist` · ⓑ `ui.updateEnrichmentBadge` · ⓒ `admin.fetchEnrichmentStatus`: `?filters=<queue_filters>` 대신 `?enrichment_queue=<rule.name>`을 보냅니다(`rule.queue_predicate`가 있을 때만, 없으면 종전 폴백). ⓓ `enrichment.fetchTotalKeyed`의 **차분 계산은 걷어냅니다** — `&enrichment_queue_scope=blank_key`의 `total`이 「판단키 없음 N건」입니다. ⓔ 진행률 **분모(`fetchTotalAll`)는 그대로 무필터**입니다. **클라가 바꾸기 전까지 다중 target 규칙의 워크리스트는 여전히 「전부 blank」를 봅니다.**
- 회귀 그물: `test_a_partly_filled_row_stays_in_the_queue_predicate_ANY_TARGET_BLANK`(결함을 기록했던 테스트를 **지우지 않고 다시 썼습니다** — 빨갰을 때의 문장을 그대로 인용한 채로) · `test_every_consumer_of_the_queue_reaches_the_one_predicate`(라우트·걷기·④가 **같은 row_id 집합**) · `test_the_queue_scopes_partition_it_and_resolved_is_its_exact_complement` · `test_the_route_refuses_a_queue_it_cannot_compose_instead_of_answering_everything`(400 + **count 캐시 키**).
- **④ 분류는 유일하게 큐 전체를 걷습니다** — 빈 판단키 행을 **`blank_decision_key`**(신설, `BUG_CLASSES` 소속)로 세어 `queue_size`가 워크리스트 잔여·배지와 계속 일치하게 합니다.
- **조성 지점은 서버 `enrichment_config.to_public_rule` 하나**입니다 — 소비처가 서로 다른 수를 말할 수 없습니다. (구버전 서버 폴백: 필드 부재 시 클라는 target-blank-only로 동작 — 지금은 서버 조성과 **같은 형태**입니다.)
- **데이터는 지우지 않습니다.**
- 참고: 같은 커밋의 소급 backfill 스크립트(`server/scripts/backfill_enrichment.py` — 파생 **행 부재**만 생성, 값 결손은 큐 소관, dry-run 기본·`--apply`·provenance `enrichment_backfill` priority 99)는 운영 도구이며 이 계약의 일부가 아닙니다.

## 5.2 ① 후보가 1개면 판단이 아니라 확인 (2026-07-30 · 서버 착지)

`reference_views` 결과가 **유일값 하나**면 사람은 판단이 아니라 확인 중이다. 두 개의 **선언**이 그 확인을 없앤다.

- `reference_views[].candidate_for = {target_field: 뷰_결과_컬럼}` — 어느 뷰의 어느 컬럼이 어느 target의 후보인지. **선언 없는 뷰는 표시 전용**이며 절대 후보가 되지 않는다.
- 규칙별 `auto_confirm` (**기본 `false`**) — 후보 1개일 때 사람 개입 없이 채운다.

**유도 금지의 근거는 실 config가 증명한다**: `core_wafer_attribution`의 뷰 #0(lot+slot 조회 → 후보 1개)과 뷰 #1(lot만 조회 → 후보 N개)이 **둘 다 `wafer_id` 컬럼을 가진다.** 컬럼명 유도 구현은 #1까지 후보로 삼아 그레인 사고로 고른 값을 자동 확정한다(맵 오버레이 `derive_table_binding` DECOY의 행 버전).

**M3 `auto_register_map_meta`와 같은 형태** — 부재 시에만, 소스 `enrichment_auto_confirm`은 `SOURCE_PRIORITY` 미등재 = 최하위(99)이므로 `user`(0)가 항상 이긴다. 노브는 작업 단위 경계에서 1회 읽고, 비-boolean은 경고 1회 후 기본값. **다른 점은 기본값뿐이며 근거는 두 가지다**: ⓐ 이 필드의 blank가 **큐 소속을 정의**하므로(§5.1) 오확정은 항목을 워크리스트에서 빼 재검토를 막는다 ⓑ 철회가 부분적이다(R2로 레이어는 되돌리지만 그 셀은 provenance가 남아 재확정되지 않는다).

**거절은 전부 이름이 있다** — `not_declared` · `no_candidate` · `ambiguous`(= 바로 그 사람의 판단) · `view_error` · `missing_bind` · `candidate_column_missing` · `cell_has_provenance` · `over_cap` · **`probe_truncated`** · **`distinct_truncated`**(둘 다 2026-07-30 신설, 아래). 그리고 **평가 못 한 뷰는 "값 없음"이 아니라 "모름"** 이므로, 선언된 뷰 중 하나라도 실패하면 살아남은 뷰가 값 1개를 냈어도 거절한다.

**🔴 후보 프로브는 뷰의 `limit`에 잘리지 않는다 (2026-07-30 [F9] 수리).** 종전에는 서버가 행을 자른 **뒤** 파이썬에서 distinct를 셌다. 실측: 라이브 참조뷰 `공정 이력(wafer_process)`는 `limit: 50`인데 (lot,slot) 하나당 행이 최소 69 · 평균 135.4 · 최대 217로 **80개 키 전부가 상한을 넘는다** — 51번째 행이 다른 `wafer_id`를 나르고 있어도 `ambiguous`는 영영 발화하지 않았고, `single` 판정은 "매핑이 우연히 정상"이라는 아무도 검사하지 않는 가정 위에 있었다. 수리는 뷰가 아니라 **실행 형태**를 갈랐다(그 뷰에는 사람의 표시라는 두 번째 소비자가 있고 그쪽은 시간순 **행**이 필요하다):

- 표시: `REFERENCE_LIMIT_WRAP_SQL` (행 LIMIT, 종전 그대로)
- 후보: `CANDIDATE_GROUP_WRAP_SQL` — 결과 **전체**에 `GROUP BY`, distinct 상한은 `limit + 1`(절단의 증거). `support`는 이제 전 결과에 대한 참 건수다.
- 스캔 상한 `enrichment_read_caps.probe_scan_rows`(미선언 시 5000, **2026-08-05부터 운영 노브** — `ingestion_settings.json`)에 닿으면 **잘린 읽기**이므로 `single`을 주장하지 않고 `probe_truncated`로 거절한다. GROUP BY는 상위 LIMIT으로 조기 종료할 수 없어, 바인드 없는 선언 뷰가 키마다 전 테이블을 훑는 것을 막는 유일한 방어선이다. 스캔 행수는 `SUM(COUNT(*)) OVER ()`로 **그룹이 잘리기 전** 값을 센다 — 반환된 그룹의 합으로 대신하면 그룹 절단 시 과소 보고되어 진짜 잘린 읽기를 놓친다(2026-07-30 QA).
- **절단은 두 축이고 둘 다 거절이다.** distinct 값이 `limit + 1`개를 넘어 집계가 잘리면 `distinct_truncated`다. 「>limit이면 어차피 2개 이상이니 `ambiguous`가 잡는다」는 **틀렸다** — 판정은 `clean_str_value`로 값을 **접으므로**, 잘려 돌아온 그룹들이 전부 같은 정규값으로 접히면 distinct는 1개가 되고 보이지 않는 그룹에 모순이 있는 채로 `single`이 된다(실증: `limit: 1`, `pairs=[('WF01',1),('WF01 ',1)]` → `single`, 잘려나간 곳에 `WF02`). 절단은 **접기 이전 사실**이라 그 자체로 거절이어야 한다.
- 🔴 **상한 셋이 전부 `limit`으로 불렸고 조작자가 엉뚱한 것을 올렸다 (2026-08-05 인시던트).** ① CLI의 **키 예산**(구 `--probe-limit`, 현 `--max-keys` — 읽기를 전혀 넓히지 않는다) ② 뷰의 표시용 **행** `limit` ③ 그 `limit`이 겸하고 있던 프로브의 **distinct** 상한. `distinct_truncated` 거절을 받고 「limit을 올리라」는 말을 들은 조작자는 손에 닿는 유일한 것(①)을 올렸고 아무 일도 일어나지 않았다. 그래서 **각 상한은 자기가 무엇을 자르는지로 이름 지어졌고**(`probe_scan_rows` / `probe_distinct_values` / `reference_rows_default` / `reference_rows_max`, 전부 `ingestion_settings.json`의 `enrichment_read_caps`), **절단 거절은 자기 수리를 스스로 말한다**: `cap`(설정 이름) · `cap_value` · `cap_declared`(미선언이면 「이건 출하 기본값」이라고 밝힌다) · `cap_home`(고칠 파일과 키) · `expected_if_raised`. 마지막 것이 두 결과를 가른다 — 이미 서로 다른 값을 2개 이상 읽었다면 상한을 올려도 `ambiguous`가 될 뿐이고(**사람의 판단**), 1개 이하면 `unknown`(읽기가 짧아 알 수 없다). **미선언은 0도 무한대도 아니라 출하 기본값이다** — 이 상한들은 판정 문턱이 아니라 안전 천장이라, `map_alignment`의 문턱처럼 미선언에 거절로 답하면 config를 손대지 않은 모두가 업그레이드에서 멈춘다.
- 🔴 **참조 질의는 전부 SAVEPOINT 안에서 실행된다**(`enrichment_config._isolated_execute`). Postgres는 실패한 문장이 **트랜잭션 전체를 abort**시키고, 그 뒤 `COMMIT`은 **정상 반환하면서 서버가 ROLLBACK으로 바꾼다**(2026-07-30 읽기 전용 실측). 드라이버 예외를 잡는 것은 격리가 아니다 — 세션은 이미 죽었고 호출자도 로그도 그것을 모른다. 격리가 없으면 ⓐ `_diagnose_probe_failure`의 재질의가 죽은 세션에서 돌아 **`candidate_column_missing`이 Postgres에서 도달 불가**가 되고 ⓑ 오염된 세션이 체인 워커의 `except`를 통과해 `process_pending_groups`의 `processed_chain=True` 커밋을 무산시켜 **그룹이 영원히 재처리**된다(실패로 보고되지 않으므로 재시도 격리 카운터도 오르지 않는다).
- 컬럼명은 바인딩할 수 없는 **식별자**라 보간된다 → 형태 검증(`_CANDIDATE_COLUMN_RE`)이 **실행보다 먼저** 오고, 참조는 반드시 별칭으로 한정한다(`__enrichment_ref."col"`). ⚠️ SQLite는 해석되지 않는 큰따옴표 이름을 **문자열 리터럴로 강등**하므로, 한정하지 않으면 존재하지 않는 컬럼이 「후보 1개 = 컬럼명 그 자체」로 읽혀 자동 확정된다(2026-07-30 실측).

**확장성**: 키 1개당 선언된 뷰 수만큼 SQL이 나가므로 작업 단위당 상한(`enrichment_auto_confirm_max_keys`, 기본 200)이 있다. 초과 키는 쓰지 않고 **큐에 남으며** 건수를 로그에 남긴다.

**구현**: `server/enrichment_candidates.py`(술어·노브·`AutoConfirmCollector`) + 체인 워커 훅(M3 훅 직후) + `server/enrichment_analysis.run_auto_confirm_sweep`(소급·dry-run). 설정 절차 정본은 [config/enrichment_rules §7](../guide/config/enrichment_rules.md).

### 5.2-ter 모호함은 **컬럼**의 성질이지 행의 성질이 아니다 (2026-08-05 사용자 재정 · 서버 착지)

후보 2개가 `target_a`에는 **합의**하고 `target_b`에서 **갈리면**, `target_a`는 결정된 것이다. 행 전체를 거절하면 **결정 가능한 컬럼이 다른 컬럼 때문에** 비게 된다 — 근거가 그렇지 않은데 전부 아니면 전무로 굴린 것이다.

- **판정 그레인은 처음부터 컬럼이었다** — `resolve_target_candidate`는 (키, 필드) 단위이고 프로브는 **선언된 그 컬럼 하나**를 GROUP BY 한다. `confirm_keys`도 필드를 독립으로 돌며 결정된 것만 `updates`에 모은다. 그래서 **판정 로직은 바꾸지 않았다**. 없던 것은 **회계**였다: 거절이 납작한 자루 하나에 쌓여 「어느 컬럼이 모호했나」와 「어느 컬럼은 아예 안 물어봤나」가 구별되지 않았다.
- **한 행이 컬럼 일부만 채워진 채로 끝날 수 있다** — 그리고 남은 컬럼이 비어 있는 한 그 행은 큐에 남아야 한다(✅ **2026-08-05 수리됨** — 큐는 「target 중 하나라도 blank」이고 이제 이름으로 요청한다: §5.1-bis).
- **빈칸이 나르는 사실 세 가지를 섞지 않는다**: `ambiguous`(물어봤고 답이 갈렸다 — 사람의 판단) · `no_candidate`(물어봤고 아무것도 없었다 — 근거를 찾아라) · **`not_declared`**(**안 물어봤다** — config 공백). 셋째는 종전에 **선언이 하나도 없을 때만** 세어졌으므로, 같은 규칙에 선언된 형제 target이 있으면 미선언 target은 **조용히 건너뛰어져** 판단된 빈칸과 똑같아 보였다. 이제 컬럼별로 이름이 남는다.
- **부분 진척은 진척으로 보고한다** — 셀 그레인(`confirmed`/`written_cells`)은 원래 부분 채움을 일로 셌지만 **행 그레인이 없었다**. `rows_fully_confirmed` / `rows_partly_confirmed` / `rows_unconfirmed`가 `rows_examined`를 **분할**한다(합이 맞는지 테스트가 단언한다 — 부분합이 조용히 안 맞기 시작하는 것이 진행률이 거짓말을 시작하는 방식이다). 컬럼별 회계는 `per_target = {target: {confirmed, refused:{사유:건수}}}`이고 **사유 어휘는 §5.2의 것을 그대로 쓴다**(새 어휘 0).
- 🔴 **부분 target 채움에는 새 provenance 이름을 만들지 않았다 — 확인하고 안 만든 것이다.** `cell_sources`는 (row_id, column_name)당 한 행이므로 결정된 컬럼은 `enrichment_auto_confirm`을 달고 거절된 컬럼은 **provenance 행 자체가 없다**. 「이 스윕이 어느 컬럼을 결정했나」는 이미 질의다. (대조: `enrichment_auto_confirm_partial_key`는 **행의 키**에 관한 사실이라 셀 기록이 나를 수 없어서 이름이 필요했다 — §5.1.) 회귀 그물 `test_cell_sources_already_says_which_columns_the_sweep_decided`.

### 5.2-bis 선언의 효과를 눈으로 본다 (2026-07-30 [F9] · 서버 착지)

「config가 먹었는가」를 제품이 답하지 못했다. 이 절의 결함 계급이 그 공백에 그대로 살아 있었다 — `auto_confirm: true`를 `candidate_for` 없이 켜면 컬렉터는 경고 한 줄 남기고 조용히 비활성이고, **라이브가 정확히 그 상태였다**(선언 0건). 두 표면이 그것을 말한다:

| 라우트 | 답하는 질문 | 비용 |
|---|---|---|
| `GET /admin/config/resolve` | 어떤 선언이 효과가 있고 · 없고(사유 포함) · 거부됐나. 전역 스위치와 캡의 **실효값과 그 값이 온 파일**. 어느 뷰가 어느 target의 후보를 나르나 | **DB 질의 0건**(config만) |
| `GET /admin/enrichment/auto-confirm/dry-run?rule=…` | 「사람 없이 몇 건이 확정 가능한가」 | 큐 표본 walk (`limit` 기본 200 · 최대 2000) |

- 서버가 세 모집단을 **이름으로** 반환한다: `effective` · `ineffective`(+ 명명된 사유) · `rejected`(+ 사유). 🔴 **클라는 사유를 유도하지 않고 서버가 만든 `detail` 문자열을 그대로 렌더한다.**
- 어휘는 런타임 열화 어휘를 **그대로 재사용**한다(새 단어 0): `not_declared` · `mapping_unavailable` · `scope_unresolved` · `not_reached`. 계약 벡터 `contracts/config_resolve_report/`가 pytest와 node 하네스를 같은 기댓값에 채점하고, 서버 어휘가 `main.CHIP_TRACE_*`의 부분집합인지까지 검사한다.
- **켜기 전에 함정이 보인다**: 선언 뷰의 `required_binds`가 `decision_key`의 진부분집합이면 `scope_unresolved` 경고가 붙는다. 실 config의 `같은 lot 전체 슬롯`이 그 모양이고, 여기에 선언하면 결과는 `ambiguous`가 **아니라** `single`이다(그 lot의 `wafer_slot_history` 행이 하나라서) — 하나의 `wafer_id`가 23개 슬롯에 쓰인다. 런타임은 이것을 경고할 수 없다(거짓말을 하고 있지 않다). **선언에서만 보이므로 선언을 보여주는 자리에서 말해야 한다.**
- 드라이런은 HTTP에 `apply`를 노출하지 않는다(쓰기는 CLI 전용). 대신 `ignore_knob=True`로 **꺼진 규칙도 측정**한다 — 「켜면 무슨 일이 일어나는가」는 켜기 전에 답해야 하고, `run_auto_confirm_sweep`이 그 플래그와 `apply`의 결합을 스스로 거부한다.

> ✅ **1클릭 확정(클라 절반)의 서버 전제 중 ⓐ가 착지했다** — `GET /enrichment/rules`의 `reference_views[]`에 **가산 필드 `candidate_for`**(총괄 승인 2026-07-30). 노출되는 것은 컬럼명이고 그 컬럼명은 참조뷰 결과 헤더에 이미 나타난다 → 신규 노출 0. 쿼리 본문·limit은 그대로 비노출. 남은 것은 ⓑ "이 키에 후보가 1개인가" 엔드포인트다.

## 5.3 ② 반복된 판단을 룰로 승격 — 제안만 (2026-07-30)

같은 패턴을 N번 풀었으면 그것은 규칙이다. `enrichment_analysis.analyze_promotions`가 **사람이 채운 셀만**(`CellSource.source_name == "user"`) 훑어 함수적 종속을 찾고 **제안**한다.

- **선행부는 `decision_key`의 진부분집합**이다 — 임의 선택이 아니라 기존 계약의 결과다: 승격물은 참조뷰로 표현되고 `_validate_view_sql`이 바인드를 decision_key 컬럼으로 제한하므로, 실행 가능한 형태는 "판단키의 일부가 target을 결정한다"뿐이다. 단일 컬럼 판단키는 진부분집합이 없어 `no_proper_subset`으로 거절한다.
- **승격물은 이 시스템이 이미 실행하는 것**이다 — `reference_views` 항목 + `candidate_for` 선언. 새 맵퍼도, 새 실행기도 없다. ①이 그것을 실행하므로 다음 동일 선행부 키는 **사람 개입 0**으로 해소된다.
- **① 의 모호 거절이 사실상의 철회다** — 선행부가 나중에 두 값에 대응하면 뷰가 후보 2개를 내고 ①이 **거절**한다. 항목이 화석화되는 대신 사람의 판단으로 되돌아간다.
- ⚠️ **자동 적용하지 않는다.** 충돌(같은 선행부 → 서로 다른 target 값)이 하나라도 있으면 그 선행부는 함수가 아니므로 제안 자체를 하지 않고 **거절 이유를 함께 보고**한다. config는 절대 쓰지 않는다.

## 5.4 ④ 결손 원인 분류 (2026-07-30)

큐는 근본적으로 다른 두 가지를 섞어 사람에게 청구하고 있었다. `enrichment_analysis.classify_queue`가 한 번 분류한다(**읽기 전용**).

| 분류 | 뜻 | 성격 |
|---|---|---|
| `mapping_gap_same_name` | **소스에 그 값이 있는데** 아무것도 옮기지 않았다 | 🐞 **파이프라인 버그** — 사람이 파서 결함을 대신 갚는 것 |
| `resolvable_from_reference` | **빈 target 전부**가 후보 1개를 낸다 | ⚙️ 기계로 해소 가능(= ①) |
| `partially_resolvable` | **일부** target만 후보 1개를 낸다 (2026-08-05 신설) | ⚙️+👤 ①이 일부를 채우고 **나머지는 사람 몫** — `REAL_WORK_CLASSES` 소속 |
| `ambiguous_reference` | 후보가 2개 이상 | 👤 **진짜 사람의 판단** |
| `no_evidence` | 소스에 그 컬럼이 없고 후보도 없다 | 👤 진짜 일감("소스에 원래 없다") |
| `no_source_rows` | 그 판단키의 원본 행이 없다 | 데이터 출처 이상 |
| `unprobed` | 참조뷰 탐색 예산 초과 | 미판정(다른 분류로 접어 넣지 않는다) |

🔴 **`partially_resolvable`을 나눈 이유 (2026-08-05)**: 종전 판정은 `any(single)`이라 **빈 target 하나만 풀려도** 그 행을 `resolvable_from_reference`로 올렸다 — 「사람이 전혀 필요 없다」로 보고해 놓고 남은 컬럼의 일감을 지웠다. 행은 분류 **하나**만 가질 수 있으므로 다중 target 규칙에서는 그것만으로 부족하다. 그래서 컬럼 그레인 회계 **`target_verdicts = {target: {"single"|사유: 건수}}`**를 행 분류 옆에 함께 반환한다 — 어느 컬럼이 모호했고 · 어느 컬럼이 근거가 없었고 · 어느 컬럼은 **아예 선언이 없어 안 물어봤는지**는 읽는 사람에게 서로 다른 지시다.

**정직한 한계 2개를 명시한다**: ⓐ 버그 분류는 **소스 테이블의 같은 컬럼명**으로 판정한다 — 다른 이름으로 값을 나르는 소스 컬럼은 선언 없이는 찾을 수 없고, **추측하지 않는다**(오버레이 DECOY 교훈). ⓑ 참조뷰 탐색은 키당 SQL이므로 `probe_limit`으로 유계이며, 예산 초과분은 `unprobed`로 **따로 보고**한다.

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
- **잔여 공수** = 미채운 파생 **행** 수(워크리스트 길이 = `?enrichment_queue=<규칙명>`의 `total` — §5.1-bis). 「판단키 없음 N건」 중 **남은 키로 판단 가능한 몫**은 2026-08-05 재정 이후 여기서 해소된다(§5.1) - 사람의 공수로 세도 된다. 판단키가 **전부** 빈 행만 여전히 해소 불가다.
- (v2) **자동 제안 채택률** — 아래 범위 밖.

## 8. 범위

- **v1 (본 스펙)**: 골격(dedup 워크리스트 + 자유입력 + 참조뷰 + 파급 + 레이어링 병합). 설정 주도.
- **v2 (별도, 나중)**: lot event·lot-slot 상관으로 `target` **후보 추정 제안**(어시스트 층). 암묵지를 대체하지 않고 보조만.

## 9. 설계 결정 (2026-07-25 확정 — 잔여는 구현 설계로 위임)

1. ✅ **파생 = 별도 영속 테이블.** 일회용 큐가 아니라 실존 도메인 테이블(log→inventory 동형). 체인 dedup mapper로 투영. — §6 반영.
2. 🗄️ **[2026-08-11 product-owner ruling로 뒤집힘]** ~~UI = 별도 페이지~~ (`enrichment.html`, 4번째 진입점 — map_editor 선례). ~~3구역 레이아웃: 워크리스트(결손 필터) | 판단·입력(컨베이어: 입력→Enter→다음) | 참조뷰. + 메인 그리드에 "결손 N건" 배지 → 클릭 시 진입.~~ **지금은 정반대다 — "발견은 그리드, 처리도 그리드"**: 전용 페이지·컨베이어·배지 전부 삭제되고, 참조뷰만 메인 그리드 사이드바 탭으로 이식됐다(`enrichment_reference_view.js`). 결손 교정 자체는 그리드 직접 편집(F3 값 제안)으로 흡수 — "발견은 그리드, 처리는 전용 화면"이라는 이 항목의 원래 판단이 뒤집혔다.
3. ✅ **원본 write-back 없음.** target은 파생 테이블에만 저장, Source와는 판단키 조인으로 연결(논리적 파급). 온톨로지도 관계로 추적. 필요 시 나중에 체인 규칙 1개로 fan-out 추가 가능.
4. ✅ **소유 분할**: Server PM = dedup mapper + 파생 테이블 config + (필요시) 결손 카운트 API. Client PM = enrichment 페이지 + 그리드 배지. **신규/변경 REST는 경계 계약 → 총괄이 설계·조율.** 확정 시 DOC_OWNERSHIP 배선.
5. ⚙️ *구현 설계로 위임:* 연속 판단키 dedup granularity(config `granularity` 옵션), `reference_views` 쿼리 정의·파라미터 바인딩 방식, 재인제션 시 사람값 보존 검증(레이어링이 커버 — 테스트로 확인).

---
*확정 시: SSOT §6 서브시스템 지도에 추가 · DOC_OWNERSHIP 배선 · README 인덱스 등록 · Living 승격.*
