# doc-keeper 정비 사이클 — M2-v2 배치(`da65a87`)

> 2026-07-26 · 대상 범위: `ac50d5d`(직전 정비) 이후 ~ `da65a87` **21커밋**(지시서 "20건"과 1건 차이 — 아래 §5-①)
> 규율 준수: 코드·config 무수정 · `PROJECT_STATUS.md` 무접촉 · 커밋 없음

---

## 1. 신규 히스토리 3건 + 인덱스 재생성

| 파일 | 대상 커밋 |
|---|---|
| `docs/history/20260726_164640_large_file_p2_checkpoint_resume_and_hash_dedup.md` | `f78ab0a` |
| `docs/history/20260726_170434_universal_map_overlay_and_transfer_plan_m2.md` | `8e34804` |
| `docs/history/20260726_204344_m2_v2_plan_as_map_redesign.md` | `da65a87` |

인시던트(`cc57b64`)·P1 heavy 레인·workspace config.json 폐지는 **이미 히스토리가 있어** 재작성하지 않고 상호 링크만 했다.
`gen_index.py` 재생성 완료 — **201 → 204건**(`--check` 통과).

## 2. CODE_MAP 갱신 (`8b0fd03` → `da65a87`)

- 헤더 HEAD 해시·TOC 라인수 갱신 + **오버레이 구간 변경 예정 경고** 배너 추가.
- **§1.2 라우트 5종 신설**: `/api/maps/overlay`·`/api/maps/paint-rules`·`/api/transfer-plan/{stages,source-summary,validate}`.
- **§2 crud.py 앵커 전면 실측 갱신**(파일 1,863→1,890줄) + `create_audit_log`의 4096자 절단.
- **§3 directory_watcher 앵커 전면 실측 갱신**(1,467→1,712줄) + P2 심볼 7종(`_try_dedup_skip`/`_plan_checkpoint`/`_finalize_checkpoint`/`_retry_should_restart`/`_compose_detail`/`dedup_by_signature_enabled`/`resume_from_checkpoint_enabled`).
- **§5 신규 모듈 3개 절 추가**: `ingestion_checkpoint.py`(~258) · `map_overlay.py`(~698) · `transfer_plan.py`(~1,429). `bonding_plan.py` 절에 **A2 경고 박스** 추가.
- **§6**: `models.FileIngestionCheckpoint` · `audit_cache.add_logs_batch` 누적 의미론 · `event_constants.MAX_AUDIT_VALUE_CHARS` · 셋업 스크립트 2종.
- **§7**: `bonding_plan.js` 절 **삭제**(파일 자체가 `8e34804`에서 삭제됨) → `transfer_plan.js` 절 신설. `map_editor.js` 앵커 전면 실측(3,065→4,209) + 페인트 잠금·오버레이 블록 신설. `utils.js` 토스트 규율.
- **§8 흐름**: 인제션 흐름에 P2 단계 삽입, 맵 에디터 흐름에 오버레이·전사 계획 2항 추가.

> **앵커 실측 방식**: `map_editor.js`는 사이클 도중 병행 에이전트가 워킹트리를 수정 중이었으므로(4,209 → 4,463), 최종 앵커를 **`git show HEAD:`** 기준으로 재검증했다. 전 20개 심볼 일치 확인.

## 3. 리빙 문서 동기화

| 문서 | 변경 |
|---|---|
| `overview/SYSTEM_OVERVIEW.md` (SSOT) | Last-verified + HEAD · watcher 행에 P2 · `FileIngestionCheckpoint` 모델 · config 표 4행(`ingestion_settings`/`map_overlay_config`/`bonding_plan_config`/`transfer_plan_config`) · 서브시스템 지도 2행 · API 요약 2행 · 클라 JS 규모·map_editor 엔트리 · **죽은 링크 1건 제거**(`architecture/layering_and_priority.md` 부재) |
| `architecture/backend.md` | 라우트 5종 상세 + degraded 3층 방어 계약 · watcher 워커 행에 P2 · 파일 규모 |
| `architecture/frontend.md` | `transfer_plan.js` 행 신설 · `map_editor.js` 규모·오버레이·페인트 잠금 · `utils.js` 토스트 · **§4.1 전사 계획 사이드바** 신설 |
| `spec/MAP_EDITOR_SPEC.md` | **§5 범용 맵 오버레이**(정렬 규율·프레임 vs 물리 표·클라 규약·페인트 잠금) + **§6 전사 계획**(가용량 계약·신뢰 표기 3층 방어·prune 권한 불변식) 신설. §5는 변경 예정 배너 |
| `guide/INGESTION_GUIDE.md` | **§1.8 체크포인트 재개 & dedup** 신설. §1.7의 "P2 예정" 문구 정리 |
| `guide/CONFIG_GUIDE.md` | `map_overlay_config.json`·`ingestion_settings.json` 표 갱신 · **§5.8-bis 오버레이 config 키 구조** 신설 · 캐시 표 2곳 · **`.sample` 드리프트 경고**(§5) |
| `qa/FEATURE_CHECKLIST.md` | 기능 행 5건(페인트 잠금·오버레이·전사 계획·P2 체크포인트·P2 dedup) + M1 행을 "UI 대체됨"으로 정정 · 점검 항목 16건 |
| `process/DOC_OWNERSHIP.md` | 소유 3행 신설(오버레이·P2 체크포인트) + 계획 엔진 행에 스펙 링크 |
| `README.md` | 히스토리 개수 204 · 맵 에디터 스펙 설명 |

## 4. 문서-코드 정합 감사 — 발견 사항

### 4-1. 삭제된 파일을 살아 있는 것으로 서술 (수정 완료)

`client2/src/bonding_plan.js`(903줄)·`bonding_plan.css`(675줄)는 `8e34804`에서 **삭제**됐는데, `CODE_MAP §7`은 함수 앵커까지 딸린 전용 절을, `FEATURE_CHECKLIST §1.7`은 기능 행을 그대로 유지하고 있었다. 서버 API(`/api/bonding-plan/core-summary`)와 `server/bonding_plan.py`는 **존치**하므로 "전부 사라졌다"가 아니라 **"UI만 대체, 서버는 `transfer_plan`의 core-kind 위임 대상으로 존속"**으로 정정했다.

### 4-2. `.sample`이 코드보다 오래됨 — **코드 아닌 config 자산이라 미수정, 총괄 판단 필요**

`server/config/transfer_plan_config.json.sample`의 `plan_store` 섹션이 **v1 잔재**다:

| 항목 | `.sample` | 코드(`transfer_plan.py`)가 실제로 읽는 것 |
|---|---|---|
| `plan_store.doe` 필수 키 | `plan_id, source_lot, source_slot, qty_per_unit, layer_from, layer_to, knobs, description` | `ref_table, map_key, doe_value, band_seq` (+ `stack_band`, `qty_total`) |
| `plan_store.doe_source` | **없음** | `ref_table, map_key, doe_value, band_seq, source_lot, source_slot` (+ `qty`, `note`) |
| `plan_store.source_region` | **없음** | `ref_table, map_key, source_lot, source_slot, x, y`(휴면 경로) |
| `plan_store.plan` / `.map` / `.doe_layer` | 있음 | **코드가 더 이상 읽지 않음**(`_plan_store_statuses` 미참조) |

또 `map_overlay_config.json.sample`의 `table_bindings.transfer_plan_map`은 **폐기된 계획 맵 사본** 테이블을 가리킨다.

**영향**: `.sample`은 `.gitignore` 예외로 **git에 올라가는 유일한 config 원본**이고 CONFIG_GUIDE가 "새 환경은 `.sample`을 복사해 시작"이라고 안내한다 → 새 환경을 세팅하면 **v1 형태 config로 시작**해 `plan_store.doe`가 `missing`이 된다. `config/`는 내 수정 금지 영역이라 CONFIG_GUIDE에 경고를 남기고 여기 보고한다.

### 4-3. QA 재검수 비차단 결함이 문서에 반영되지 않은 채였음 (반영 완료)

병합은 차단 2건(A1·C1)만 고치고 진행했고, `QA_v2_rereview_client.md`의 나머지는 **미해소로 이월**됐다. 구현 보고서·커밋 메시지만 읽으면 "페인트 잠금 fail-open 해소"처럼 **실제보다 강하게** 읽힌다. 다음을 문서에 명시했다:

| 코드 | 사실 |
|---|---|
| **C4** | **콜드 스타트는 아직 fail-open** — `degrade()`가 유지하는 "직전 값"이 페이지 로드 직후엔 기본값 `{enabled:false}`(`map_editor.js:37`)라, **첫 조회 실패 시 8개 강제 지점이 열린 채 시작**한다. 칩은 뜨므로 *조용한* fail-open은 아니다. 테이블 전환 실패 시 이전 테이블 잠금 값이 새 테이블에 계속 적용됨 |
| **C7** | `currentGeomSignature`에 **`phys_*` 파라미터 누락**. 격자 치수를 안 바꾸는 offset 변경은 웨이퍼 bbox를 옮기지만 서명이 그대로 → 오버레이 좌표가 낡은 채 남는다. 기존 결함이나 **신규 `importOverlayToGrid`가 그 좌표를 `gridData`에 써 넣어 표시 오류를 데이터 오염 경로로 승격**시켰다 |
| **C3** | 클라 조회가 `limit=500`(`transfer_plan.js:1068/1104`)이고 절단을 로드 실패로 강등하므로, **자재 행 500 초과 계획은 영구히 저장 불가**(20값 × 3구간 × 10자재 = 600행이면 도달) |
| **C5 / C6 / C8** | legend 저장 오탐 · 헤더 초안/서버 신선도 역전 · `sticky` 토스트 퇴거 미보호(호출부 0건) |

이들은 `MAP_EDITOR_SPEC §5.4 열린 항목`과 `CODE_MAP` 해당 항목, M2-v2 히스토리 "열린 항목"에 **미해소로 명기**했다.

### 4-4. 죽은 링크 1건 (수정 완료)

`SYSTEM_OVERVIEW.md §4` → `architecture/layering_and_priority.md` — **존재하지 않는 파일**이었다. 레이어링 서술은 `data_model.md`가 담고 있어 링크를 제거했다.
(`DOC_AUDIT.md:173`의 `../overview/SYSTEM_OVERVIEW.md`는 `_archive/` 배지 **템플릿 예시**라 오탐 — 미수정.)

### 4-5. 인덱스에 없는 문서 (관찰 — 조치 안 함)

`docs/spec/{BATCH_INGESTION_SPEC, BATCH_PROCESSING_SPEC, TABLE_ENGINE_SPEC}.md`, `docs/map_editor/{philosophy, specification, architecture_and_management}.md`, `docs/prompts/{CLAUDE, starting_prompts}.md`가 `docs/README.md`·다른 문서 어디서도 링크되지 않는다. **아카이브 대상인지 인덱스 누락인지 판별하려면 각 문서를 코드와 대조해야 해** 이번 사이클 범위를 넘는다 — 다음 사이클 후보로 등재 제안.

### 4-6. `api_documentation.md` 범위 미달 (관찰 — 조치 안 함)

행/셀/우선순위 API만 다루고 맵·계획·그래프·어드민 라우트를 전혀 담지 않는다(🟠 표시됨). 신설 라우트 5종을 여기 넣으면 문서 성격이 바뀌므로 `backend.md`·`CODE_MAP`에만 반영했다. **역할 재정의(전수 레퍼런스로 승격 vs 「핵심 API 튜토리얼」로 범위 명문화)는 총괄 판단 사항.**

## 5. 총괄 확인 요망

1. **커밋 수 불일치** — 지시서는 "20커밋"이나 `ac50d5d..da65a87`은 **21건**이다(`git log --oneline ac50d5d..da65a87 | wc -l`). 코드 커밋은 `f78ab0a`/`8e34804`/`da65a87` 3건뿐이고 나머지 18건은 docs/board라 **문서화 누락은 없다**. 지시서의 `04de1b3`(pre-compaction snapshot)이 목록에서 빠진 것으로 보인다.
2. **`.sample` 드리프트 정정**(§4-2) — `server/config/*.sample`은 내 수정 금지 영역이다. server-pm 위임 또는 총괄 직접 수정 필요.
3. **SSOT 편집 범위** — `SYSTEM_OVERVIEW.md`는 사실 동기화(config 표·API 요약·모델 표·서브시스템 지도·죽은 링크)만 손댔고 **아키텍처·경계 계약 서술은 건드리지 않았다.** 그래도 SSOT 편집이므로 검수 요망.
4. **`PROJECT_STATUS.md` 갱신 제안(직접 수정 안 함)**:
   - §현재 초점 0번의 "재기동 대기" 체크리스트에 **P2 드릴 3종**과 **A3(A1 REST 재검증)**이 이미 있으나, 신설 라우트 목록에 `/api/maps/paint-rules`가 빠져 있다(현재 3종 중 2종만 명시).
   - §열린 문제에 **QA C3(500행 초과 계획 영구 저장 불가)**와 **C7(오버레이 서명 물리 파라미터 누락 → `importOverlayToGrid`가 데이터 오염 경로화)**을 `#번호`로 승격 권장 — 보드 규율("리뷰 결함이 배치를 넘어 살아남으면 `#번호`로 승격")에 해당한다. 특히 C7은 **오버레이 변환 일원화 작업이 손댈 바로 그 코드**라 그 작업의 수용 기준에 넣어야 한다.
   - §최근 완료에 P2·M2·M2-v2 롤업 3행과 히스토리 링크 추가.
   - "doc-keeper 정비 미실행: 트리거 17건 누적" 문구는 이번 사이클로 해소.
5. **`map_editor.js` 워킹트리가 사이클 도중 변경됨**(4,209 → 4,463, 오버레이 일원화 작업). CODE_MAP 오버레이 절은 `da65a87` 기준이며 **그 작업 병합 시 재정비가 필요**하다 — 문서에 변경 예정 배너를 달아 두었다.

## 6. 교훈 제안 (`agent_workspace/memory/doc-keeper.md` — 총괄 승인 후 반영)

- **함정**: 구현 보고서·커밋 메시지의 "해소" 표현을 그대로 문서에 옮기면, **병합이 차단 결함만 고치고 비차단은 이월한 경우** 문서가 실제보다 강한 상태를 주장하게 된다("fail-open 제거"라 썼는데 콜드 스타트는 여전히 열려 있었다).
  **올바른 방법**: 배치에 QA 보고서가 있으면 **커밋 메시지가 아니라 QA의 §5「병합 차단 vs 후속 백로그」를 정본으로 삼는다.** 백로그로 내려간 항목은 리빙 문서에 **미해소로 명기**한다.
- **함정**: 서브시스템 UI 파일이 통째로 교체되면(`bonding_plan.js` → `transfer_plan.js`) 코드맵의 **삭제된 절이 함수 앵커까지 딸린 채 살아남아** 다음 에이전트가 없는 파일을 Read하려 든다.
  **올바른 방법**: 배치 diff의 **삭제(`D`) 라인을 먼저 훑어** 코드맵·체크리스트에서 해당 절을 제거·정정하고, "서버는 존치/클라만 대체" 같은 **부분 대체**는 그 경계를 명시한다.
