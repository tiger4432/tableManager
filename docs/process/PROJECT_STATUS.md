# 📌 PROJECT STATUS — 지금 무엇이 열려 있나 (Living Board)

> 🎯 **새 세션이면 [`LEAD_PM_HANDOFF.md`](LEAD_PM_HANDOFF.md)를 먼저 읽어라** — 역할·절대 규율·핵심 가치·되풀이되는 함정.
>
> **Status:** 🟢 Living | **Last-updated:** 2026-08-01 (HEAD `64288f4` · 미푸시 0)
> 🔴 **이 보드는 「지금 열린 것」만 담는다.** 2026-08-01에 679줄에서 쪼갰다 — 낡은 한 줄이 총괄의 위험 판정을 반대로 뒤집은 사고가 실제로 났기 때문이다(P1).

| 무엇이 궁금할 때 | 어디 |
|---|---|
| **다음에 뭘 하나** | 이 파일 §다음 이어서 할 일 ← **정본** |
| 지금 살아 있는 결함 | 이 파일 §열린 문제 |
| 진행 중인 설계와 그 근거 | [`DESIGN_TRACKS.md`](DESIGN_TRACKS.md) |
| 무슨 일이 있었나(인시던트·정정) | [`INCIDENTS_2026-07.md`](INCIDENTS_2026-07.md) · [`history/`](../history/README.md) |
| 옛 대기열·완료 롤업·장기 백로그 | [`BACKLOG_ARCHIVE.md`](BACKLOG_ARCHIVE.md) |

**작성 규율:** 한 항목 = **한 줄**. 경과·근거·수치는 위 문서들에 있다 — **여기 쌓지 않는다.** 서사가 세 줄을 넘으면 그건 인시던트 파일 소관이다.

---

## 🔁 현재 상태 (2026-08-02) ― 트레이스 픽스처가 서고 1회차 채점이 끝났다

> **미푸시 0 · 트리 깨끗.** 시뮬 config를 픽스처 기준으로 재구성하고(`table_config` 13선언), 생성기·정답 파일·채점기까지 세웠다.

**🎯 1회차 채점 ― 픽스처가 목표한 실패를 첫 판에 노출했다**

| | |
|---|---|
| 계보 재현율 | 정답 **13.4%** · 오답 **38.8%** · 정직한 미상 **47.8%** |
| 🟩 **오답의 구성이 결론이다** | **오답 2,053건이 전부 「웨이퍼는 맞고 좌표가 틀림」** ― 계보 추적이 **엉뚱한 웨이퍼를 지목한 적이 0회**다. split·merge를 시점 기준으로 거스르는 **제일 어려운 부분이 이미 맞고**, 남은 실패가 **좌표 프레임 하나로 격리**됐다 |
| 🔴 거짓 확신 | 대칭 부분집합에서 **데이터가 결정할 수 없는 케이스에 확신 있게 답했다.** 픽스처를 만든 이유가 이것이고 1회차에 나왔다 ― 그 자리 `auto_confirm`이 `false`인 근거 |
| 정직성 | 모호 62건 중 **20건을 「미상」으로 답해 정답 처리.** 41건은 채점 불가(**입도 불일치**: 정답은 job별, 시스템은 설비·제품별) |
| enrichment | 드라이런 **발화 확인**(`refused_reason: null`) ― 보드가 적어 둔 「침묵」이 닫혔다 |

**➡️ 다음 한 수 = ④번 화살표를 재는 실험**: 사람이 **설비·제품 조합마다 한 번** 프레임을 판정하고 재현율을 다시 잰다. 오답이 전부 프레임 탓이므로 **13.4% → 52%대**가 나와야 한다. **「판정 몇 번에 재현율 얼마」가 이 시스템 명제의 첫 직접 증거**다.

**오늘 새로 드러난 것**

| # | 항목 | 한 줄 |
|---|---|---|
| **O4** | 🔴 **규칙이 디스크에서 유효한데 워커 안에서 죽어 있을 수 있다** | 체인 워커가 자기 `TABLE_CONFIG`보다 **먼저** 새 규칙을 읽고 `source_table not registered`로 거절한 뒤 **재시도하지 않았다** ― 인제션 내내 옛 규칙으로 돌았다. 회복 경로는 재기동 또는 **2차 리로드**이고, 확인은 `chain_worker.log`의 `Synthesized N` |
| **O5** | **앵커 밴드가 추론 ①을 안 가른다 (총괄 설계 오류)** | 후보 뷰가 `track_in` + 단조 순위로 풀고 `core_wafer`를 **안 본다**. 밴드는 추론 ①이 아니라 **계보**를 가른다 ― 픽스처 설계에서 변수를 잘못 걸었다 |
| **O6** | **정직성 채점의 입도 불일치** | 정답은 **job별** 대칭성, 시스템은 **설비·제품별** 판정 → 41건이 채점 밖. 둘 중 하나를 상대에 맞춰야 한다 |
| **O7** | 🔴 **선언이 「구조적으로 불가능」한데 아무도 안 막는다** | 실증(사용자 발견 2026-08-02): `chain_rules`의 `dt_log_to_dt_map`이 `mapper_module: mappers.dt_map_mapper`를 가리키는데 **그 모듈이 디스크에 없었다** ― `.sample`만 있고 라이브 `.py`가 없다(`production_mapper`는 둘 다 있는 게 정상 모양). **config 재구성 · 전체 스위트 · 총괄 검수를 전부 통과했다.** <br>⚠️ 켜면 시끄럽게 죽는 게 아니라 **조용히 안 돈다** ― 워커가 로드 실패한 규칙을 거절하고 **재시도하지 않기 때문**(O4와 같은 뿌리). <br>**할 일**: 로더가 로드 시점에 `mapper_module` 임포트 가능성을 검증하게. ⚠️ 「import 되는가」는 **공유 인터프리터에서 테스트 가능한 속성이 아니다**(다른 테스트의 `sys.path` 삽입이 보인다) ― 판정은 **자식 프로세스**로 |
| **X7** | **`config_reference/`는 사본이라 조용히 낡는다** | 소유자·갱신 주기 미기록. `docs/guide/config_reference/` |
| **X8** | **`TRACE_FIXTURE_SPEC.md`가 고아 문서** | 634줄인데 `DOC_OWNERSHIP`에 행이 없다 |

📌 **총괄 오류 2건 기록**: ① `dt_log` 비즈니스 키를 코어 좌표로 잡아 **충돌**(한 DT 웨이퍼가 여러 코어의 다이를 섞는다) ② **맵 키와 행 키를 혼동**해 샘플 매퍼가 한 job의 모든 셀을 한 행에 뭉갰다. 둘 다 에이전트가 잡았다.
📌 **또 낡은 보드 줄에 속았다**: 「`config_watcher`가 원자적 쓰기를 감지 못한다」는 `46a67c7`(7-29)로 **이미 거짓**인데 내가 새 문서에 옮겼다. `dist` 건과 **같은 실수, 같은 날 두 번째.**

## 🔁 (구) 현재 상태 (2026-08-01)

- **이번 주 착지·푸시 완료**: 가상 컬럼 검색·필터 + CSV 추출 + `/schema` `join_resolved_columns` · 소급 어드민 화면(사용자 실기 확인) · 오버레이 = 맵 규칙 6(클라 mm 공간) · `blank_predicate` 계약. 소스 `cd3e0f4` · dist `52a1703`.
- **게이트**: 스위트 **1818 passed / 1 skipped / 0 failed**(총괄 실행) · 계약 **6/6 무분기** · 강제 하네스 **15/15 초록**.
- ⚠️ **운영 반영 시 서버 재기동 필수** — 소급 라우트·config resolve·가상 조인·`/schema` 키는 **새 프로세스라야 존재**한다. 재기동 없이는 404가 나고 **우리 버그처럼 보인다**.
- ⚠️ **가상 컬럼 검색은 UI에서 되지만** `bonding_log.wafer_id`는 사용자의 `table_config` 변경으로 **`virtual_only` = 읽기 전용**이다(그리드에서 수정 불가).

---

# 📌 다음 이어서 할 일 (2026-07-31 마감 시점 정본)

한 줄 = 한 항목. 근거·경과는 위 본문과 `agent_workspace/reports/`에 있다. **여기 쌓지 않는다.**
이번 주 착지분은 `cd3e0f4`(소스)·`52a1703`(dist)로 **푸시 완료**, 미푸시 0.

### 🔴 데이터가 걸린 것 (먼저)

| # | 항목 | 한 줄 |
|---|---|---|
| D1 | **`proc_id` 날짜 충돌** | `WP-<HHMMSS>-<seq>`에 날짜가 없어 **날짜를 넘어 덮어쓴다** ― 07-28 행이 오늘 파일에 조용히 사라졌다. **지금도 매일 진행 중** |
| D2 | **잉여 389행 정리** | 원인(고아 워커)은 제거됨. 삭제는 **사용자 몫** ― 어느 `row_id`가 사는지가 `audit_logs`·`cell_sources`·`cell_overwrites` 귀속을 바꾼다 |
| D3 | **`business_key_val` UNIQUE 인덱스** | 「키당 1행」을 DB가 강제하지 않는다. **D2 정리 선행** + `CONCURRENTLY`(`bonding_map` 176만 행) |
| D4 | **런처 싱글턴 가드** | 저장소 락파일로는 **다른 디렉터리의 런처를 못 잡는다** ― 공유하는 것에 걸어야 한다(포트 또는 **DB advisory lock**) |
| D5 | **백업 부재** | PostgreSQL 덤프 · `ingestion_workspace/` ― 프로덕션 게이트에 남은 유일한 🟡. 위 넷 중 뭐가 터져도 되돌릴 원본이 없다 |

### 🟠 이번 주가 만든 빚

| # | 항목 | 한 줄 |
|---|---|---|
| N1 | **백필이 소켓을 안 쏜다** | 실측: `chain_replay`·`enrichment_backfill`·`scripts/backfill_enrichment` **알림 호출 0건**(증분 경로는 58건). 소급을 **버튼으로 만들었으므로** 이제 필요하다 ― 39만 행에 행마다 쏘면 클라가 죽으니 **「개별 침묵 + 명명된 총계」** 형태. ⚠️ 발행 자체가 없어 **스윕이 회수할 것도 없다** |
| N2 | **겹친 칩 점을 legend 값 색으로** | 총괄이 안 ⓐ로 판정해 놓고 **수리 지시서에 안 넣었다**(내 누락). 지금은 레이어 단색이라 「몇 개·어디」는 보여도 「무슨 값」이 안 보인다 |
| N3 | **서버 문장 결함 3건** | `truncated: true`인데 그 사실을 말하는 문장이 없다 · `graph_orphans`가 **리터럴 `**삭제**`** 를 보낸다(INV-F9-8 위반, 화면에 떠 있다) · 확인 문구 속 영어 키 |
| N4 | **`?cols=` 드롭다운이 조인 컬럼 누락** | 서버는 이제 받는데 `api.js`가 `currentColumns`로 목록을 만든다 |
| N5 | **`/schema` 계약 벡터** | contract-keeper 설계 노트(`Contract_join_resolved_columns.md`)에서 재생성. **S8(알림을 지워도 쓰기가 성공하면 안 된다)** 이 핵심 |
| N6 | **ⓓ enrichment 참조뷰에 가상 컬럼** | 승인 범위 ⓑⓒⓓ 중 **ⓓ만 안 들어갔다**(실측: `enrichment_candidates`·`enrichment_config`에 `virtual_join` 참조 0건). 아래 §설계 트랙의 전제이기도 하다 ― **사전엔 결론, 참조뷰엔 후보** |

### 🧭 핵심 가치에 난 구멍 (총괄 평가 2026-08-01에서 지목했는데 목록엔 없던 것)

| # | 항목 | 한 줄 |
|---|---|---|
| **V1** | **F4 ― 방금 만든 맵이 다음 화면에서 「없음」** | dt map을 315행 저장하고 본딩맵을 다시 로드해도 롤업이 `MAP X`를 유지, **`↻ 가용`을 눌러야** 풀린다. **가치 3 위반이고, 사용자가 방금 자기가 만든 것을 시스템이 부정하는 형태**라 신뢰 손상이 특히 크다 |
| **V2** | **F2 ― 화면 DOE 수량이 저장 불가능한 셀을 포함** | `Fill All`이 `inside`와 무관하게 칠하고 `updateLegendCounts`가 그것까지 센다 ― 화면 숫자가 실제 저장량보다 **35~51% 많다**. **화면과 저장이 갈리는** 계급 |
| **V3** | **가상 조인 값에 계보가 없다 (가치 5 구멍, 이번 주가 넓혔다)** | 조회 시점 계산이라 `cell_sources`에 못 쓴다. 왼쪽 셀의 **이력 타임라인이 비어 있는데 화면 값은 바뀐다** ― 「이 칸 왜 바뀌었지」에 그 화면이 답을 못 한다 |

### 🧬 온톨로지 트랙 (2번 가치가 사용자에게 값을 증명한 적이 **아직 0건**)

| # | 항목 | 한 줄 |
|---|---|---|
| **O1** | **슬라이스 1호 착수 ― 자재 knob tag 추적** | 기계는 이미 있다(materializer·`POST /graph/trace`·`trace.html`). 비어 있는 건 **매핑과 label 정합**뿐. **딸려 오는 것 둘만** 단단히 하면 된다: 테이프 label 분리(#15) · 그 슬라이스 테이블의 `event_time` |
| **O2** | 🔴 **materializer가 DELETE를 스킵해 stale 엣지가 남는다** | **목적 온톨로지 전략 전체의 전제다.** 지우지 못하면 재도출이 **교정이 아니라 누적**이고, `exp:` 폐기가 불가능해진다. 「온톨로지는 고치기 어렵다」를 **실제로** 참으로 만드는 유일한 결함 |
| **O3** | **`not_reached`/`mapping_unavailable`을 큐로 연결** | 그래프가 「내가 뭘 못 했는지」를 이미 이름 대어 말하는데 **아무도 안 줍는다.** 이게 순환의 **④번 화살표**(발견 → 다시 보강)이고, 없으면 ①→②→③은 순환이 아니라 **직선**이다 |

### ⚙️ 프로세스 (총괄이 지적하고 스스로 안 지킨 것)

| # | 항목 | 한 줄 |
|---|---|---|
| **P1** | 🔴 **이 보드를 쪼갠다** | 「9천 줄 파일과 500줄 보드는 같은 병」이라고 적어 놓고 **오늘 하룻밤에 또 늘렸다.** 비용이 실증됐다 ― **총괄이 낡은 한 줄(「dist 최신 `1dc761b`」)을 믿고 위험 판정을 반대로 냈다.** 인시던트 경과는 히스토리로, 보드는 「지금 열린 것」만 |
| **P2** | **경합 잔여** | C-4(체인 큐 독점·HOL) · C-6(동시 upsert 락 순서) · C-8(런타임 ALTER 락 컨보이) · C-9(풀 합계>max_connections) · C-10(워처 `.tmp` 필터 부재) · C-11(WS 직렬 전송). **오늘 중복 사고가 「동시성 가정이 얇다」를 실증했다** |

### 🟡 하네스·구조

| # | 항목 | 한 줄 |
|---|---|---|
| H1 | **러너가 「단언 0개로 빨감」을 구분** | `check_harnesses.mjs:78`이 종료코드 한 줄이라 **죽은 하네스가 부채로 위장된다**(이번 주 3건). 하네스당 `ASSERTIONS <ran> <failed>` + 러너 ~15줄 ― **리팩토링 선행조건** |
| H2 | **모듈 로드 스모크 1건** | 하네스는 함수를 **이름으로 잘라내** 채점하므로 `validDieListCache` 계급을 영원히 못 본다 ― **리팩토링 선행조건** |
| H3 | **그리드에서 admin 초기화가 던진다** | 페이지 가드 한 줄. 🔴 **null 가드로 덮지 말 것**(위 진단 참조) |

### ⚪ 문서·환경

| # | 항목 | 한 줄 |
|---|---|---|
| X1 | **`mm은 일부러 비어 있다`가 거짓이 됐다** | 클라에 mm 공간이 **생겼다** ― 7파일 11자리(`CODE_MAP:127/1452`·`frontend:284/290`·`DOC_OWNERSHIP:54`·`LEAD_PM_HANDOFF:118`·이 보드·`README:39`) + 삭제된 거절이 `MAP_EDITOR_SPEC:590`·`CODE_MAP:1700`에 남음 |
| X2 | **열린 문제 #4·#18이 낡았다** | #18은 이미 수리됨(실측), #4는 #16과 모순 ― 스위트 재실행으로 닫는다 |
| X3 | **`SERVER_STARTUP_GUIDE`가 틀린 경로를 인쇄** | `scripts/` vs `server/scripts/` + 이 시스템이 안 쓰는 `uvicorn --port 8000`. doc-auditor 후보 |
| X4 | **`frontend.md` 헤더가 약 1만 자 변경이력** | 나머지 넷은 정리됐는데 이것만 남음 |
| X5 | **`:8081`이 가상 조인을 못 올린다** | `assy_qa.core_wafer_map`에 중복 2건 → UNIQUE 인덱스 불가 → 선언 거부. 격리 E2E가 이 기능엔 안 쓰인다 |
| X6 | **`line_model_owner_attribution` 못 켬** | 타깃이 `owner`인데 뷰가 `owner`를 SELECT 안 한다 ― 뷰 쿼리 수정 선행 |

---

## 🐞 열린 문제 (Open Problems)

| # | 심각도 | 문제 | 도메인 | 상태 |
|---|---|---|---|---|
| 4 | 낮음 | `test_map_presets_api` 기존 실패(맵 프리셋 도메인, #0 이전부터) — **잔여는 이것 1건뿐**(enrichment 테스트 격리 버그는 2026-07-25 해소, 현재 스위트 177 passed / 1 failed) | Client·Server | 대기 |
| 5 | 중간 | **경합 점검 잔여 리스크(수정 배치 2 후보)** — C-4(체인 큐 독점·HOL, 매퍼 의미론 협의 필요)·C-6(동시 upsert 행 락 순서)·C-8(런타임 ALTER 락 컨보이)·C-9(커넥션 풀 합계>max_connections)·C-10(워처 .tmp 필터 부재)·C-11(WS 직렬 전송) + created_logs 무상한 전송 잔여. 상세: [점검 보고서](../../agent_workspace/reports/Server_contention_audit.md) (C-7은 그래프 키셋 청킹으로 해소됨) | Server | 대기 |
| 2 | 낮음 | 맵 이월 시 A/B의 x·y·val 컬럼명이 크게 다르면 자동 정합 안 됨(저장 전 Advanced Column Mapping 수동 확인 필요) | Client | 대기(관찰) |
| 3 | 정보 | 미리보기 브라우저 pane이 비-compositing → rAF/ResizeObserver 자동발화·CSS transition 프리즈로 라이브 UI 자동검증 제약(실제 브라우저 무관) | 검증환경 | 알려짐 |
| 9 | 중간 | **config_watcher가 원자적 쓰기(temp+rename)를 감지 못함** — on_modified만 처리해 에이전트 Edit류 저장 시 기존 테이블 ALTER가 조용히 누락(on_moved 미처리). 스키마 API는 config 싱글턴이라 200이어도 물리 반영 증거 아님 | Server | 대기(수정 소형 — on_moved 보강) |
| 10 | 낮음 | audit_cache total_count 과소 표기(QA D-1) — 멀티 target-table tx에서 테이블별 total_log_count가 SET 덮어쓰기. 기존 결함(회귀 아님), production_plan 체인+enrichment 동시 트리거로 도달 가능 | Server | 대기(P2 동승) |
| 20a | ✅ **해소됨 (낡은 항목이었다)** | ~~변환 구현이 아직 둘이다 — `bonding_plan.py`가 자기 사본을 갖고 있다~~ — **`4ba13ae`(2026-07-27)가 이미 지웠다.** 지금 `bonding_plan.py:20`은 **「변환 구현은 이 모듈에 없다」**고 명시하고 `map_overlay`를 **17번** 참조하며, `test_bonding_plan.py::test_deleted_transform_copy_is_gone`이 다섯 이름 중 하나라도 돌아오면 실패한다. **이 행은 그 커밋 이후 나흘을 살아남았고 앵커(`:74`·`:140`·`:199-204`)까지 전부 낡았다** — 내가 대기열을 재검하지 않았다는 뜻이다. 발견자 doc-keeper, 사실은 [`DUPLICATION_LEDGER`](../architecture/DUPLICATION_LEDGER.md)의 해소 목록으로 이관. 아래 원문은 **읽지 말 것** ―<br>~~(구) **변환 구현이 아직 둘이다**(구 A2의 정체). doc-keeper 4차가 총괄의 오인을 잡았다: `bonding_plan.py`는 `map_overlay`를 **참조 0건**이고 자체 `normalize_align`/`make_align_transform`(`:74`,`:140`)을 쓴다. `transfer_plan.py`도 `resolve_binding`/`build_key_filters`/`load_overlay_config`만 쓰고 **정렬 함수는 안 쓴다**. 즉 A1 수정이 `bonding_plan`에 전파되지 않은 이유가 이것이고, 오버레이에서 방금 없앤 "두 구현" 문제가 **가용량 산출에는 그대로 살아 있다**(`bonding_plan.py:199-204` bbox 항 없는 구 산술 — 라이브 오버라이드 없어 휴면). 부수 발견: 클라가 서버 정렬 좌표 소비를 멈춘 뒤로 `map_overlay`의 정렬 함수군(`resolve_align`/`make_frame_transform`/`_frame_transformer`/`_frame_phys_params`) **운영 소비자가 0**이다 — 호출처는 엔드포인트 자신과 자기 테스트뿐. 폐기 여부 판단 필요 | Server | 대기 |
| 11 | 중간(격하) | **좌표 변환 서버-클라 드리프트** ([감사](../../agent_workspace/reports/QA_map_transform_logic_audit.md)) — F1: rot=90/270 비등방 칩에서 transformer가 회전 치수·비회전 chip 혼용 · F2: 엔진 미장착 fallback 타원 ±1 어긋남 · F3[중]: 클라 getPhysicalCoords의 mm 오프셋 반올림 혼입(서버 정의가 정론 — 경계 계약 명문화 필요). **M1 align이 결함 지점을 구조적으로 우회 완료**(`bonding_plan.make_align_transform` — cell_to_physical 순수 인덱스 변환만, 엔진 fallback 무참여 + 90/270 치수 스왑 규약 + 규격 불명 시 `align_unavailable` 명시 실패). transformer 자체의 F1/F2 수정과 F3 계약 명문화는 잔여(현 소비자는 안전 경로만 사용) | Server·Client | M1 우회 완료 — 근본 수정 대기 |
| 16 | **높음(격상)** | **테스트 스위트가 라이브 환경으로 샌다 — 2계통 실증** ⓐ **운영 PostgreSQL에 DDL 발행**: `main.py` import 시 모듈 레벨 `Base.metadata.create_all`(main.py:44)이 실 DB에 대해 실행되어, 테스트만 돌려도 신규 테이블이 라이브에 생성된다(P2에서 실제 발생 — 빈 테이블이라 무해했으나 경로가 위험). ⓑ **사용자 config에 써넣는다**: `test_map_presets_api`가 `POST /api/map-presets`로 라이브 `server/config/maps.json`을 수정한다. 실증 — 현재 프리셋 키가 `['custom_1784890104442', 'core_std', 'base_std', 'tape_std']`이고 첫 항목이 테스트 산물(총괄 직접 확인). 같은 테스트가 `maps.json.sample`에만 있는 키를 라이브에서 찾아 단언하므로 **세션 내내 "상시 허용 실패"로 취급돼 왔다 — 항상 실패하는 테스트는 스위트 전체의 신호를 죽인다.** **✅ ⓑ 해소(`9a8ede8`)** — 두 오염 테스트 격리. `test_map_presets_api`는 `tmp_path` + `MAPS_CONFIG_PATH` 패치, 단언을 `set(presets) == {심은 키}`로 써서 **격리가 풀리면 즉시 깨지게** 했다. `test_file_ingestion_callback_direct`는 핸들러가 이미 경로를 생성자 인자로 받으므로 패치 없이 `tmp_path` 주입으로 끝났고, `config.json` 쓰기는 **제거**(폐기 개념 + `columns` 키 무소비 + 테이블명이 `default_table_name`으로 동일 해석) 후 재생성 시 깨지는 네거티브 단언을 넣었다. **증명은 바이트 동일성** — `maps.json`의 sha256·크기·**mtime**까지 불변, `ingestion_workspace` 9,230파일 `changed=0`. 생긴 3파일이 수집기 산물임은 **pytest를 안 돌린 동일 길이 창 대조군**으로 실증. **스위트 414 passed / 0 failed — 허용 실패 소멸.** ⓐ(운영 DB DDL)는 잔존하나 테스트 엔진은 전부 sqlite 메모리/tmp로 확인됨. 라이브 잔재 2건(`maps.json`의 `custom_…`, `inventory_master/config/config.json`)은 **사용자 자산이라 미삭제 — 원본 미상·복구 불가로 고지함** | Server | ⓑ 해소 / ⓐ 대기 |
| 15 | 중간 | **`Wafer` label에 이질적 정체 혼입**(2026-07-26 온톨로지 리뷰 발견) — `wafer_slot_history.wafer_id`(예 `A123`)와 `core_wafer_map.core_lot\|core_slot`(예 `LOT-A\|05`)이 같은 label에 공존해 서로 조인 불가. 더 근본적으로 **후자는 DT 계층 판명으로 실은 테이프 위치**(스펙 §7.5b)라 "테이프 91개를 Wafer라 부르는" 상태. 방치 시 불량 역추적이 엉뚱한 개체를 지목. **M2에서 dt_map/dt_log 올릴 때 정리 필수**. 파생 결정: 층 배정 온톨로지 매핑(§14-4)도 같은 패턴이라 보류, 별도 label(`PlanLayer`)로 §7.5c node_class 작업 시 처리 | Server·온톨로지 | M2에서 처리 |
| 14 | 중간 | **맵 push 경로 기존 결함 3종**([QA M2 리뷰](../../agent_workspace/reports/QA_transfer_plan_m2_review.md) 부수 발견, **M2 회귀 아님 — 전 맵 공통**) — ⓐ `limit=2000` + `replace_map` 조합에서 2000셀 초과 맵의 데이터 소실 가능(현행 프리셋 최대 1600셀이라 미발화) ⓑ `GET /tables/{t}/schema`가 미존재 테이블에도 200 반환(존재 확인 불가) ⓒ 클라 `CURRENT_USER`가 빌드 시점 값으로 박힘(번들 확인) | Server·Client | 대기 |
| 13 | 중간 | **`crud.load_table_config()`가 JSON 파싱 실패 시 로그 없이 `{}` 반환** — 가동 중에는 `refresh_dynamic_models`의 빈-config 가드가 막지만, **손상된 config로 재기동하면 전 테이블이 조용히 사라진다**. 최소 `logger.error` + 기동 시 명시 실패(fail-fast) 검토. CONFIG_GUIDE 함정 A로 문서화됨 | Server | 대기(소형) |
| 17 | 중간 | **계획 자재 500행 초과 시 영구 저장 불가** (QA-B의 C3) — 클라가 `limit=500`으로 조회하고(`client2/src/transfer_plan.js:1068/1104`) `total > rows`면 로드 실패로 강등하는데, 그 강등이 쓰기 보류로 이어지므로 **자재 500행을 넘긴 계획은 저장 경로가 영구히 닫힌다**. 강등 자체는 옳다(절단된 상태로 prune하면 전량 삭제) — 페이징이나 상한 상향이 필요 | Client·Server | 대기 |
| 18 | 중간 | **오버레이 기하 시그니처에 물리 파라미터 누락** (QA-B의 C7) — `currentGeomSignature()`(`client2/src/map_editor.js`)가 cols/rows/start/invertY/rot/side만 보고 `phys_*`(칩 피치·오프셋·직경·edge margin)를 빼먹어, 물리 규격을 바꾸면 오버레이가 **조용히 안 따라온다**. 기존 결함이나 신규 `importOverlayToGrid`가 어긋난 좌표를 `gridData`에 써 넣어 **표시 오류에서 데이터 오염으로 승격**됐다. **오버레이 변환 일원화 작업의 수용 기준에 포함시켰다** | Client | 일원화 작업에 동승 |
| 19 | 낮음 | **페인트 잠금 콜드 스타트 fail-open** (QA-B의 C4) — `degrade()`가 유지하는 "직전 값"이 로드 직후에는 기본값 `{enabled:false}`(`client2/src/map_editor.js:37`)라, **첫 조회가 실패하면 8개 강제 지점이 열린 채 시작**한다. 칩으로 표시는 되므로 *조용한* fail-open은 해소된 상태 — "fail-open 제거"라는 서술만 과장이었다 | Client | 대기 |
| — | ~~21 중복 키~~ | ✅ **종결 — 사용자 판정 2026-07-31: 「중복 키 다 실수니까 무시. 지금 개발환경이라 그래.」** 등재 자체가 내 오독에서 출발했다: 최악으로 보고한 `bonding_map` 437행/키는 **중복이 아니라 맵 하나의 셀 437개**였다(`business_key_val`에 `x,y`가 안 들어간다 — 맵 테이블의 정상 모양). 남은 실제 중복(`bonding_log` 117 · `wafer_process` 43은 바이트 동일, `inventory_master` 163은 `MAX` 한 필드만 다름)은 **개발 환경 산물**이다. <br>📌 **다만 구조적 사실 하나는 남는다**: `business_key_val`을 덮는 인덱스 **54개 전부 non-unique**이므로 「키당 1행」은 DB가 강제하지 않는다. 조인 경로는 아래 판정으로 닫힌다 | — | 종결 |
| 20 | 낮음 | **enrichment 조회 상한 3개가 코드 상수** — `DEFAULT_REFERENCE_LIMIT=200` / `MAX_REFERENCE_LIMIT=1000` / `CANDIDATE_PROBE_MAX_ROWS=5000` (`server/enrichment_config.py:55·56·457`). 운영 테이블이 커지면 움직여야 하는 값인데 재배포가 필요하다. **셋을 같이** config로 뺀다 — 하나만 빼면 형제 상수 사이에 규칙이 갈린다. [[config-over-hardcode]] | Server | 대기(소형) |
| 21 | **중간** | **오토컨펌이 꺼져 있을 땐 아무 신호도 안 남는다** (사용자 2026-07-31: 「wf id 유니크가 1개인데 오토컨펌 작동 안해」). 총괄 실측(config 읽기 전용, 시뮬 박스): 규칙 2개 모두 `auto_confirm` **미선언**(기본 OFF)이고 뷰 4개 모두 `candidate_for` **`{}`** → `declaring_views` 공집합 → **`not_declared`로 거절, 프로브가 아예 안 돈다.** GROUP BY는 무관하고 **이미 들어가 있다**(`enrichment_candidates.py:324`). <br>🔴 **진짜 결함은 침묵이다**: `__init__`의 「`auto_confirm: true`인데 선언이 없다」 경고(`enrichment_candidates.py:519-524`)는 **노브가 켜졌을 때만** 뜬다. 노브가 미선언이면 그 위에서 `continue`로 **조용히** 빠진다 — **지금 상태가 로그 0줄**이다. 켜지 않은 것과 켰는데 안 먹는 것이 **관측상 구분되지 않는다.** <br>✅ 이미 있는 답: `GET /admin/enrichment/auto-confirm/dry-run?rule=…`이 **`ignore_knob=True`로 꺼진 규칙도 측정**하고(`main.py:4429-4432`) `no_evidence_reasons`에 `not_declared` 건수를 이름으로 돌려준다. **단 `f3fd785` 이후 서버라야 한다** — 재기동 우선순위가 이 건으로 한 번 더 올라간다. <br>📌 별건: `line_model_owner_attribution`은 지금 선언해도 못 켠다. 타깃이 `owner`인데 뷰가 `plan_id, target_qty, due_date`만 SELECT 한다 → `candidate_column_missing`. **뷰 쿼리 수정이 선행.** <br>⚠️ 선언 자체는 **운영 컴 config**에서 해야 한다(사용자: 시뮬 박스에서 고쳐야 의미 없음). 권장 선언은 `lot-slot 웨이퍼 이력` 뷰 하나 — 결정키에 정확히 바인딩되고 `wafer_id`를 돌려준다. `같은 lot 전체 슬롯`은 lot만 걸려 슬롯 전체가 나오므로 **선언하면 안 된다**(늘 `ambiguous`) | Server | 대기 |
| 22 | **높음** | **가상 조인 첫 소비자 (사용자 요청 2026-07-31 「세팅 잘했는데 사용처 만들어줘」)** — ✅ **1단계 착지**(아래). 착수 시점 상태는 `virtual_join_config.py` 모듈 주석이 스스로 적어 둔 그대로였다: 「조인 실행은 여기 없다」, 선언 검증기와 승인 라우트뿐, **실행기 0·소비자 0**. <br>**범위(사용자 확정, 4개 전부)** ⓐ 그리드 읽기 전용 컬럼 ⓑ 정렬·필터 ⓒ 엑셀/CSV 내보내기 ⓓ enrichment 참조뷰에서 사용. **순서는 총괄 판단** — 실행기+ⓐ가 계약을 정하므로 먼저 착지, 나머지 셋은 그 위에. <br>🔴 **충돌 판정(사용자 확정)**: `expose` 이름이 왼쪽 테이블에 **이미 있을 때**(운영 `dt_log`는 lot/slot 대신 `wafer_id`가 직접 꽂히는 행이 있다) → **왼쪽이 비었을 때만 채운다.** 있으면 그대로, 비면 조인값, 둘 다 없으면 `미상`. **enrichment의 빈칸 전용 게이트와 구조적으로 같은 연산**(`enrichment_candidates.py:424·585`)이므로 두 번째 철자를 만들지 말 것. 빈칸 판정은 `crud.clean_str_value` 공용 정규화로 — 여기선 값이고 저기선 공백인 상태가 생기면 안 된다. <br>⚠️ **딸려 오는 것**: 한 컬럼에 원본과 조인값이 섞이면 **어느 칸이 어느 쪽인지 구분이 사라진다** — `미상`을 만든 논리(「없는 값을 있다고 읽지 마라」)가 그대로 적용된다. 시스템에 이미 `cell_sources`/`source_name`이 있고 그리드가 이미 렌더한다(`models.py:264`, `main.py:1357`) → **같은 어휘로 payload에 실어 표시 재사용, 화면 추가 0.** 가상 조인은 조회 시점 계산이라 `cell_sources`에 **쓸 수는 없다.** <br>🔴 **가상 컬럼은 쓰기 경로에 닿으면 안 된다** — 편집·붙여넣기·Push 셋 다. 없는 컬럼에 쓰기를 시도하게 된다. 각 호출부 반복 검사보다 **구조적 거절**을 선호. <br>📌 `미상`은 **두 경우를 덮는다**(오른쪽 행 없음 + 행은 있는데 빈 값). 실측: `bonding_log → core_wafer_map.wafer_id`는 14,436행 **전부** 오른쪽 행을 찾는데 **26.27%가 빈 값** — 평범한 LEFT JOIN은 그 26%를 진짜 값으로 보고한다. INNER 금지 <br>✅ **1단계 착지 (`d70a33d`)** — `virtual_join_executor.py` 신설 + 행 조회 부착 + `shadowed` 가드 제거. **총괄 실측 1765 통과/0 실패.** 쓰기 거절은 호출부마다가 아니라 **깔때기 하나**(`apply_batch_updates` 첫 문장, 트랜잭션·`replace_map` purge보다 **앞**). 겹치는 컬럼은 **일부러 쓰기 허용** — 실재 컬럼이고 그걸 쓰는 게 조인값을 덮는 방법이다. 비용 실측: 규칙당 호출당 SELECT 1(페이지 단위 청크), 왼쪽 10만행이 1천행보다 **+1ms**, 같은 페이지에서 N+1 대비 **56배** 빠름. <br>🔬 **에이전트가 자기 테스트 4건이 깨진 코드에서도 통과한다는 걸 스스로 찾았다** — `cast_value_by_type`이 `""`를 NULL로 정규화해 빈 문자열 픽스처가 실제로 비어 있지 않았다. INNER 테스트도 실패 불가였다(페이지 행 집합이 왼쪽 질의에서 오므로 INNER/LEFT 페이로드가 동일 — INNER는 `matched` 신호만 깬다). **주입 11건 전부 빨감.** 다중 규칙 순서 결함도 도중에 수리(뒤 규칙이 앞 규칙의 `미상`을 값으로 읽어 **선언 순서가 답을 바꿨다**). <br>⚖️ **사용자 판정 2건(2026-07-31)**: ① `/schema`가 가상 컬럼도 알리게 한다 — 안 하면 선언의 절반이 **이유도 없이 조용히 사라진다** → 대기열 24 ② **일부러 지운 칸도 채운다** — 비면 비었다, 「의도적 공백」이라는 새 상태를 만들지 않는다 <br>⚠️ **`d70a33d` 커밋 메시지의 「26.20%」는 내가 틀렸다** — 운영 실측은 **26.27%**(`3,792 / 14,436` = 26.267%, `virtual_join_config.py:62-63`). 26.20%는 에이전트가 **10만 행 합성 픽스처**로 재현한 수치인데 내가 그걸 운영값인 양 옮겼다. 커밋은 불변이라 여기 남긴다. **행 수가 뒤에 붙은 쪽을 쓴다** — 26.20%면 3,782행이어야 하고 그런 측정은 없다. 발견자 doc-keeper <br>🔴 **후속 QA 필요 — 쓰기 거절의 반경이 HTTP 밖까지 간다.** `apply_batch_updates`를 직접 부르는 곳이 6개다(`chain_ingestion_worker:444`·`chain_replay:310`·`enrichment_candidates:471`·`map_meta_registrar:352`·`parsers/directory_watcher:1805`·`scripts/backfill_enrichment:263`). `ValueError`→400 매핑은 **`main.py`에만** 있어서 나머지는 생짜 raise를 받는다. 파서가 `virtual_only` 이름과 겹치는 컬럼을 뱉으면 종전엔 조용히 버려지던 것이 **이제 배치 전체를 실패시킨다.** 방향은 옳지만 **실패 모양이 호출부마다 다르다** | server-pm | T2 | ✅ 1단계 |
| 26 | 중간 | **가상 컬럼의 남은 구멍 2 (`4b50135`이 열어 둔 것)** ① **CSV 내보내기가 가상 컬럼을 빠뜨린다** — `/tables/{t}/export`는 `attach`를 안 타는 별도 라우트라, **화면에 보이는 컬럼이 추출물엔 없다.** ② **`filter: false`라 미상 행을 찾을 방법이 없다** — 정직한 선택이었지만 손실이다. 컬럼 필터가 **서버측**이고 서버는 이 컬럼을 못 보므로, 클라만 고치면 **행은 걸러진 것처럼 보이는데 `Matches:` 수는 안 걸러진 채**로 남는다(서버가 「팬텀 컬럼을 알리느니 침묵」을 택한 것과 같은 계급). 수리는 `get_column_filter_condition`에 가상 컬럼을 가르치는 **서버측**이라야 한다 <br>📌 별건 발견(선행 결함): `?cols=<가상컬럼>`으로 검색하면 조건이 하나도 안 서고 라우트가 **조건이 있을 때만** 필터를 걸므로 **테이블 전체가 돌아온다** — 그 컬럼을 검색했다고 말하면서 | server-pm | T2 | 대기 |
| 24 | **높음** | **`/schema`가 가상 컬럼을 안 알린다** (대기열 22의 후속, 사용자 판정 ①). 페이로드는 이미 싣는데 스키마가 안 알려서 **AG-Grid가 `virtual_only` 컬럼을 못 그린다** — 겹치는 경우(ⓐ)는 오늘 이미 동작한다. <br>⚠️ **읽기 전용은 구조가 지탱해야 한다**: 스키마 표식은 클라가 편집을 **제안하지 않게** 하는 것이고, 쓰기를 막는 것은 `crud.refuse_virtual_join_columns`(깔때기)다. 표식이 유일한 방어가 되면 안 된다. <br>⚠️ 겹치는 컬럼은 **이미 스키마에 있다** — 새 항목이 되면 이중 등재다. 겹치는 선언은 스키마 응답이 **바이트 동일**해야 한다 | server-pm | T2 | 🟡 진행 중 |
| 23 | 중간 | **맵 키를 드롭다운으로 (사용자 요청 2026-07-31)** — 본맵·오버레이·유효 다이맵 셋. **셋 중 하나는 이미 있다**: 유효 다이는 `<datalist id="valid-die-ref-list">` + `populateValidDieRefList`(`map_editor.js:8263`, 포커스 시 채움)로 **이미 구현돼 있고, 이게 참조 구현이다** — 두 번째 기제를 만들지 말 것. 오버레이(`map_editor.html:72`)는 평문 input, 본맵은 `metadata-fields-container`에 **JS가 테이블마다 동적 생성**하는 필드 N개라 재생성을 견뎌야 한다. API는 그대로 쓴다(`GET /tables/{t}/columns/{c}/values`, `main.py:1881`). <br>⚠️ **`unavailable_reason`을 빈 목록으로 뭉개지 말 것** — 「못 봤다」가 「없다」로 읽히는 그 계급(F9에서 일주일 낸 값). 기존 구현이 이미 삼키고 있는지 확인이 지시서에 포함됐다. <br>⚠️ datalist는 **제약이 아니라 제안** — 목록에 없는 키를 타이핑해 로드하던 경로가 막히면 안 된다. <br>🚫 **연쇄 제외**: 그 API는 형제 컬럼 필터를 안 받아 LOT→SLOT 좁히기가 안 된다. 클라에서 흉내 금지(서버가 이미 자른 목록을 거르는 것은 정직한 모집단이 아니다) — 필요하면 서버 확장으로 별건 | map-pm | T2 | 🟡 진행 중 |
| 25 | **높음** | **소급(backfill) 가이드 + 어드민 트리거** (사용자 요청 2026-07-31). <br>**① 가이드** — 소급 경로가 **5개**고 공통 규율이 하나다(기본 dry-run · `--apply`만 쓴다 · **진짜 매퍼와 진짜 쓰기 경로** · 페이지 단위 커밋이라 중단해도 이어서). ⓐ `chain_replay_cli.py replay <rule>`(R1) ⓑ `chain_replay_cli.py withdraw <table> <source>`(R2) ⓒ `backfill_enrichment.py`(**파생 행 자체가 없을 때**) ⓓ `enrichment_insights.py confirm <rule> --apply`(**행은 있고 타깃 칸이 빈 경우**) ⓔ `graph_orphan_sweep.py`. ⓒ/ⓓ 혼동이 제일 잦다. <br>📌 **R1/R2를 가르는 문장**: 「규칙이 이제 여기서 값을 안 만든다」와 「값이 비었다」는 **다른 진술**이고 앞엣것은 R2만 표현한다 → **R1은 절대 공백을 쓰지 않고** 사라진 칸을 「철회 후보」로 보고한다. R2는 층에서 철회하지 행/컬럼을 지우지 않으며 **`user`와 사람이 고정한 소스는 거부**한다. <br>**② 어드민 트리거** — 소급 항목마다 **건수만 표시 + 실행 버튼**. 카운트는 기존 dry-run 코드를 `apply=False`로, 실행은 **아웃박스 이벤트 발행 후 즉시 반환**(`POST /admin/auto-update/run-now`가 선례 — `SCHEDULER_RUN_NOW` 발행 + `NOTIFY`). 테이블 전수를 걷는 작업이라 **요청을 붙잡으면 안 된다.** 쓰기 트리거는 `require_admin_token_strict`, 확인 **1회**. <br>⚠️ **이건 F9의 결정을 뒤집는다** — 그때 「소급 쓰기는 CLI에만」으로 정하고 dry-run 라우트에서 `apply`를 **일부러 뺐다**(`main.py:4429`). 그 근거는 「어드민에서 쓰기를 트리거할 안전한 모양이 없다」였고, 아웃박스 선례로 그 전제가 사라졌다. **뒤집었다는 사실 자체를 코드 주석에 남길 것** — 다음 사람이 그 `apply` 부재 주석과 새 버튼을 나란히 보고 어느 쪽이 최신인지 몰라선 안 된다. <br>✅ 선행 착지: `reapply_chain.py` **삭제**(`8f8be4b`) — R1과 같은 일을 하면서 `source_name`이 `SOURCE_PRIORITY`에 없어 **99(최하위)**로 떨어지던 두 번째 문. 맞는 값을 쓰고도 다른 소스에 질 수 있었다 | server-pm+client-pm | T2 | 대기(`/schema` 레인 뒤 — `main.py` 충돌) |
| 12 | 낮음 | **임베디드 모드 `trigger_ws_refresh` 레거시 경로 C-5 미적용** — main.py 임베디드(비-DECOUPLED) 콜백은 created_logs 절단 계약(C-5) 밖(레거시 5000 게이트). 분리 모드 운영에서는 무영향 — 드릴 관찰로 등재 | Server | 대기(저순위) |

**종결(2026-07-25):** #0 체인 outbox 지연·신뢰성(31ms) · #1 IntegrityAndQAExpert 스킬 웹 전환 · #6 감사 로그 DB 미저장 · #7 런타임 테이블 물리 CREATE · **#8 graph 워커 신규 테이블 미인지(G1 materializer의 SYSTEM_RELOAD 구독으로 해소)**.

## 🔤 코드 체계 (Code Index) — 약칭이 무슨 뜻이고 어디에 정의돼 있나

**트랙 단계 코드** (전역 유효 — 여기가 정의처)

| 코드 | 뜻 | 정의 위치 |
|---|---|---|
| `G1`~`G4` | 온톨로지 그래프 트랙 단계 (G1 materializer → G2 추적 → **G2.5 LLM 액세스** → G3 불량추론 → G3.5 상태물화 → G4 Neo4j) | [ONTOLOGY_GRAPH_SPEC §8 단계표](../spec/ONTOLOGY_GRAPH_SPEC.md) |
| `P1`~`P3` | 대형 파일 인제션 대응 단계 (P1 heavy 레인 **완료** → P2 체크포인트 → P3 backpressure·COPY) | 이 보드 백로그 |
| `M1`~`M3` | 본딩/전사 계획 단계 (M1 조회 **완료** → M2 Universal Transfer Plan **진행중** → M3 실적 대조) | 이 보드 백로그 |
| `R1`~`R3` | Chain Replay(룰 재적용) 단계 | 이 보드 백로그 |
| `C-1`~`C-11` | 경합 점검 항목 (하이픈 있음 — 아래 QA 코드와 구별) | [Server_contention_audit.md](../../agent_workspace/reports/Server_contention_audit.md) |
| `F1`~`F5` | 체인 outbox 신뢰성 수정 (이슈 #0) | [task/chain_outbox_latency.md](../../task/chain_outbox_latency.md) |
| `S1`~`S8` | config 온보딩 시나리오 체크리스트 | [CONFIG_GUIDE](../guide/CONFIG_GUIDE.md) |
| `#0`~`#14` | 열린 문제 번호 | 이 보드 §열린 문제 |

**⚠️ QA 리뷰 결함 코드는 문서 로컬이다** — 리뷰마다 `F1`/`D1`/`C1`이 새로 시작하므로 **반드시 문서명과 함께** 인용할 것(예: "M2 QA의 F1", "P1 QA의 F1"은 서로 다름).

| 리뷰 문서 | 쓰는 코드 | 대표 사례 |
|---|---|---|
| [QA_transfer_plan_m2_review](../../agent_workspace/reports/QA_transfer_plan_m2_review.md) | `F1`~`F7`(서버) · `C1`~`C11`(클라) | F1=degraded 시 remaining 과대, C5=plan_id 미잠금 데이터 소실 |
| [QA_large_file_p1_review](../../agent_workspace/reports/QA_large_file_p1_review.md) | `F1`~`F7` | F1=QUEUED TTL 과소 표시 |
| [QA_workspace_config_deprecation_review](../../agent_workspace/reports/QA_workspace_config_deprecation_review.md) | `D1`~`D6` | D1=파일 처리 중 config 리로드 정합 |
| [QA_chain_created_logs_truncation_review](../../agent_workspace/reports/QA_chain_created_logs_truncation_review.md) | `D-1`,`D-2` | D-1=total_count 과소(이슈 #10) |
| [QA_map_transform_logic_audit](../../agent_workspace/reports/QA_map_transform_logic_audit.md) | `F1`~`F5` | F1/F2=변환 드리프트(이슈 #11) |
| G1 그래프 QA(이력) | `H1`,`H2`,`H2-b` | H1=provenance 위조, H2-b=빈 산출 정리 |

**규율**: 리뷰 결함이 배치를 넘어 살아남으면(미조치 이월) **이 보드의 `#번호` 열린 문제로 승격**해 추적한다 — QA 코드로만 남기지 않는다.

## 🧭 환경 메모 (Env Notes)
- 로컬 테스트 테이블 `sample_map`은 `server/config/table_config.json`(gitignored)에만 존재 — 운영 무영향.
- 서버 기동: `python run_decoupled_app.py` (웹 :8080 + 워커 4종). 프론트 개발: `cd client2 && npm run dev`. dist는 추적·서빙 대상 → 소스 변경 시 `npm run build` 후 dist 커밋.
- 운영 서버는 `git pull` 후 이슈 #0 절차(재기동→인덱스→purge→VACUUM, `scripts/setup_db_performance.py`) 필요.

---
*갱신 규율: 이 보드는 상태의 단일 원천이다. 새 작업/문제/해결이 생기면 즉시 이 파일을 고친다. 이력 상세는 history, 이 파일은 "지금 어디까지 왔고 무엇이 문제인가"의 요약.*
