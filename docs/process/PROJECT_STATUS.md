# 📌 PROJECT STATUS — 진행 상황 & 문제 현황 (Living Board)

> **Status:** 🟢 Living | **Last-updated:** 2026-07-26 (M2-v2·오버레이 일원화 병합 완료 / 개발 환경 격리 착수)
> **목차:** [현재 초점](#-현재-초점-current-focus) · [최근 완료](#-최근-완료-recently-done--2026-07-2526-롤업) · [백로그](#️-다음-단계--백로그-next--backlog) · [열린 문제](#-열린-문제-open-problems) · [코드 체계](#-코드-체계-code-index--약칭이-무슨-뜻이고-어디에-정의돼-있나) · [환경 메모](#-환경-메모-env-notes)
> **작성 규율:** 각 항목은 **목표 / 할 일 / 문제** 세 줄이면 충분하다. 경과·이력·증거는 히스토리와 보고서에 있다 — 여기 쌓지 않는다.
> **역할:** 프로젝트의 **현재 진행 상황·열린 문제·다음 단계**를 담는 단일 상태 보드. **컨텍스트 압축/세션 교체에도 살아남는 영속 상태**다.
> **규칙:** 총괄(및 각 PM)은 작업 **착수 전 이 파일을 읽고**, **완료 후 갱신**한다. 상세 이력은 [history/](../history/README.md), 현재 아키텍처는 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md). 이 보드는 이력 로그가 아니다 — "지금 어디까지 왔고 무엇이 문제인가"만 담는다.

---

## 📋 개발 대기열 (Queue) — 사용자 지시 2026-07-27

> **규율:** 새 요청은 **즉시 착수하지 않고 이 대기열에 넣는다.** 위에서부터 순차 처리하며, 파일이 겹치지 않을 때만 병렬로 돌린다.
> **이유:** 대기열 항목은 **고쳐도 공짜**지만 이미 던진 항목을 고치면 에이전트-시간이 날아간다. M2.6은 착수 전 5회 수정돼 비용이 0이었고, 좌표 건은 착수 후라 2라운드를 잃었다.
> **예외:** 사용자 작업을 지금 막고 있거나 프로덕션이 깨진 건은 앞으로 당긴다 — 단 **당긴다고 말하고** 당긴다.
> **순서 변경은 사용자 권한.** 총괄은 제안만 한다.

| # | 항목 | 상태 |
|---|---|---|
> **순서 확정 (사용자 2026-07-27)**: 문서 정비 먼저 — **컴팩트 대비**다. 압축되면 문서가 남는 것의 전부다. 이후 `1 → 5 → 2 → 3 → 4`.

| # | 항목 | 상태 |
|---|---|---|
| — | 운영 강화 2차 (DB 장애 전원 실패 · 워처 하트비트 위치 · 부하 중 여유 · psutil · B3 로그) | 🔵 진행 중 |
| — | M2.6 DOE 통합 (3테이블→1, 구간 정수, 소요 파생, 동시편집 검사) | 🔵 진행 중 |
| — | **문서 정비 — 새 4분할 첫 실행** (historian·mapper·keeper 동시 → auditor) | 🔵 **진행 중 · 여기서 끊고 컴팩트** |
| 1 | 서버 `transfer_plan.py`를 M2.6 `bands` JSON 계약에 맞춤 | M2.6 착지 후 |
| 2 | **C1 접근 통제** — 최소 `admin/scripts/code`·`auto-update/run-now` 두 라우트 | 대기 |
| 3 | **B4 롤백 절차** (프로덕션 차단) | 대기 |
| 4 | **C3 백업 절차** — config·workspace·PG. **사용자 입력 필요**(보관 위치·주기). 복원을 실제로 해볼 것 | 대기 |
| 5 | 문서 등급 감사(A/B/C) + C등급 아카이브 — 살아있는 문서 49개 축소 | 대기 |
| 6 | `replace_map` 빈 집합 — 서버 scope 필드 | 대기 |
| 7 | M3 맵 메타 자동 등록 (ingestion 체인) | 대기 |
| 8 | P3 대형 파일 (backpressure·COPY·상한) | 대기 |
| 9 | 온톨로지 — **장기 트랙** | 별도 |

**사용자 승인 대기**: `map_doe`·`map_doe_source` 물리 DROP · `map_split_registry`의 UUID 맵 키 잔재.

## 🎯 현재 초점 (Current Focus)

> 완료된 트랙은 여기서 내리고 §최근 완료로 옮긴다. **지금 손이 가 있는 것과 바로 다음 관문만** 남긴다.

0. **🔴 개발 환경 격리 — 최우선, 진행 중**
   - **목표**: 에이전트가 프로덕션에 **구조적으로 닿을 수 없는** 검증 환경. 성공 기준은 "검증할 때 fetch 셰임도, 전후 해시도, 안 썼다는 증명도 필요 없다".
   - **할 일**: ① `assy_qa` 스냅샷 DB(멱등 재생성) ② config·워크스페이스 경로 격리 ③ 워처·스케줄러 끈 별도 포트 서버 ④ 진입점 1개 ⑤ pytest를 격리 DB로.
   - **문제**: 수집기가 2분마다 돌아 측정이 재현되지 않고, 에이전트 노력의 상당 부분이 "내가 안 썼다"는 증명에 쓰인다. 이 세션에서 **사용자 자산 2건이 실제로 덮어써졌다**(`maps.json`, `inventory_master/config/config.json` — 후자는 원본 미상·복구 불가). 규율로 막을 것을 구조로 막지 않은 총괄 실책.

1. **🟡 doc-keeper 4차 정비 — 진행 중**
   - **목표**: 오버레이 일원화 이후 문서를 코드와 맞춘다.
   - **할 일**: `MAP_EDITOR_SPEC §5`(서버 정렬 계약 서술 → 클라 일원화로 재작성) · CODE_MAP 재앵커 · 히스토리 8커밋 · **메타 단일 기준 규칙을 스펙에 편입**.
   - **문제**: 스펙 §5가 지금 **틀린 계약**을 설명하고 있다.

2. **🔑 도메인 규칙 — `wafer_map_metadata`가 정렬의 유일한 기준** (사용자 확정 2026-07-26)
   - 맵을 담는 모든 테이블은 **메타 등록이 전제**다. 미등록은 정상이 아니라 **누락**. 정렬은 소스·타깃 메타 델타에서 유도하고, 계측 결과(DEFECT WF)도 메타에 기록한다. 셀 레벨 `grid_metadata`는 **폐기 스킴**.
   - **문제**: `bonding_map` 맵 키 **약 39만 vs 메타 9건** — 오버레이 정렬이 사실상 9개 맵에서만 일한다. 나머지는 조용히 identity 폴백. → M3에서 해소.
   - 귀결: 검수 F3 제안(셀 `grid_metadata` 노출) **폐기**(방향이 반대). `align_overrides.by_eqp` 분기는 **제거 예정** — 폐기 범위는 착수 시 사용자 확인.
2-1. **🟡 M2.5 — 맵 에디터 UI 4건 · 진행 중**
   - **목표**: 계획을 **처음 시작할 때**(공맵) 막히지 않고, 자재 현황을 자재 기준으로 읽을 수 있게.
   - **할 일**: ① **공맵에서 오버레이 허용** — 기준 맵을 요구하는 구 가드(`map_editor.js:3867`)를 걷고 화면 그리드 메타를 타깃 프레임으로 쓴다 ② 토스트가 자재 리스트를 가리는 것 수정 ③ **자재 리스트를 자재 ID 키로 재구성** — 자재별 총 가용 / 총 사용 / 어디에 몇 개씩(현행은 VALUE-STACK 구간 기준이라 반대 질문에 답한다) ④ **legend 마이그레이션 확인창 삭제**(`:2119-2137`) → 새 맵 열면 DOE 초기화.
   - **문제**: ①은 본딩 계획 착수 자체를 막고 있었다(공맵인데 EDS FAIL 오버레이가 필요). ④는 읽기 동선에 `confirm`이 끼어 있고 내부 개념("split registry")을 사용자에게 물었다 — 둘 다 "읽기 무마찰" 위반.

2-2. **🟡 정렬 구현 통합 — 셋에서 둘로 · 진행 중**
   - **목표**: A1 수정이 안 들어간 사본을 없애고, 아무도 안 쓰던 정확한 구현에 실사용을 붙인다.
   - **할 일**: `bonding_plan.py`의 자체 변환(`normalize_align`·`make_align_transform`) 삭제 → `map_overlay` 경유. `align_overrides`·`by_eqp`·`align_override_declared` 전면 제거(클라 probe 포함 — 검수 B3를 수정이 아니라 삭제로 닫음).
   - **문제**: 정확한 구현(`map_overlay`, A1 적용)은 **운영 소비자가 0**이고, 실제로 도는 것(`bonding_plan` 사본)은 **A1이 안 들어간 쪽**이다. 완전 단일화는 불가 — 가용량은 서버가 계산하므로 서버에도 변환이 하나 필요하다. **목표는 둘**(클라 렌더링 / 서버 가용량). ⚠️ 가용량은 라이브 산출물이라 전후 수치 동일성 실측이 관문.

2-3. **🟡 M2.6 — DOE 입력 단순화** · 삭제 버그 수정 착지 후 착수(같은 파일)
   - **목표**: 사용자가 머릿속으로 계산하거나 형식을 맞춰 넣는 일을 없앤다.
   - **할 일 ① 자재 = 단일 ID 문자열**. `lot|slot` 분리 입력 폐기, 한 칸에 원문 그대로 입력하고 **그 원문이 정체(키)**다. `source_lot`/`source_slot`은 **파생 컬럼으로 강등** — 나중에 파서가 채운다(`{LOT} S{n}`, `{lot}_{slot}` 등 현장 표기가 다양).
   - **할 일 ② 구간 = 정수 2칸 `[from] - [to]`, 단 연속(contiguous)**. 자유 텍스트 `stack_band` 폐기. 첫 구간은 **무조건 1**로 시작하고, 이후 각 구간의 `from`은 **앞 구간의 `to` + 1로 자동 결정**되며 **편집 불가**다. 즉 사용자가 만지는 값은 구간당 **`to` 하나**뿐이고, 스택 전체가 *끊는 지점 목록*이 된다. 층 수 = `to_i − to_(i−1)`(첫 구간은 `to_1`) — 뺄셈 한 번, 파싱 없음. 비수치 라벨 처리 문제도 함께 소멸. `1, 2-15, 16`은 **구간 3개**다.
   - **⚠️ 순서와 정체를 분리할 것**: `from`이 앞 구간에서 유도되므로 **순서가 의미를 갖는다**. 그런데 `band_seq`는 자재가 매달린 **정체**다. 둘을 같은 것으로 쓰면 구간 재정렬 시 seq가 재배정되어 **자재가 엉뚱한 구간으로 따라간다**. → **순서 = JSON 배열 위치 · 정체 = `band_seq`(재정렬해도 불변)**.
   - **중간 구간 삭제**는 아래 구간들의 `from`을 당겨 빈틈을 메운다(연속 스택이므로 의도된 동작). 자재는 자기 `seq`를 따라가고 범위만 넓어지며, 소요는 자동 재계산된다.
   - **검증**: 각 `to`는 앞 구간의 `to`보다 **커야** 한다(같거나 작으면 빈 구간·역전). 입력 단계에서 막는다.
   - **할 일 ③ 총 소요·자재 배분은 파생**. `칠한 셀 × 층 수`, 자재 배분은 `올림(총 소요 / 자재 수)`. **저장하지 않는다** — 저장하면 맵을 더 칠했을 때 어긋난 채 남고 아무도 모른다.
   - **할 일 ④ knobs → 값 층위**(knob은 값별이지 구간별이 아니다).
   - **할 일 ⑤ `map_doe` 폐기 — 3테이블 → 2.** 구간에서 수량·knob이 빠지면 남는 건 `{seq, from, to}`뿐이라 **값 행의 JSON 배열**로 충분하다. `map_split_registry`가 **값 = DOE 조건 그 자체**를 담고(색·설명·knobs·bands), `map_doe_source`가 값×구간×자재를 담는다. 원래 M2-v2 노트의 "legend/split registry와 DOE를 합친다"가 여기서 완성된다.
   - **불변식 유지**: `band_seq`는 정수 정체로 남는다. `(from, to)`를 정체로 삼으면 범위를 고치는 순간 **자재가 고아**가 된다 — 라벨을 키로 쓰면 안 되는 것과 같은 이유.
   - **서버 파급**: `transfer_plan.py`의 `plan_store.doe` 바인딩이 사라지고 `map_split_registry`가 그 역할을 받는다. 기존 6행은 **사용자가 직접 수정**(2026-07-27 확인) — 이관 코드 불필요. **물리 DROP은 사용자 승인 후.**
   - **문제**: 사용자 지적 "**STACK 구간별 총 소요는 뭘 적으란 건지 모르겠음**". 원인은 설계였다 — 라벨을 파싱하지 않기로 해서 시스템이 층 수를 모르고, **칠한 셀 수는 이미 아는데** 사용자가 `100 × 14`를 머릿속으로 곱해 넣고 있었다. "칠한 그림이 곧 계획"과 어긋난다.

3. **⚪ M3 — 맵 메타 자동 등록 (ingestion에 체인 부착)** · 착수 대기
   - **목표**: 맵 원천 데이터가 들어올 때 메타가 자동으로 붙어 위 §2의 누락이 구조적으로 사라진다.
   - **할 일**: `디펙맵 → 계측 WF → 그 WF의 PLAN 조회 → 그 PLAN의 MAP PRESET META 주입`. 프리셋은 **PLAN(제품 규격)별**로 선언하고, 주입은 **메타 JSON 세트 통째**(범위는 방향·물리 규격에서 파생되므로 계산할 것이 없다).
   - **문제/전제**: 소스 우선순위가 실제로 **USER > 체인**인지 착수 전 쿼리로 증명해야 한다 — 사용자 편집이 2분마다 덮이면 안 되고, 단순화 전체가 이 전제 위에 있다. 기존 39만 맵 **소급 등록은 별개 결정(미정)**.

4. **⚪ 대기 트랙** — ⓐ **G2.5** §7.5c 탐색 정책 엔진(node_class + 4대 룰) → LLM 도구 API ⓑ **enrichment 실전 규칙**(사용자 실 스키마 확보가 조건) ⓒ **Chain Replay R1** ⓓ `align_overrides` 폐기 범위 확정.

## ✅ 최근 완료 (Recently Done) — 2026-07-25~26 롤업

| 영역 | 요약 | 근거 |
|---|---|---|
| 서버+클라/맵 | **오버레이 변환 일원화** — 정렬을 서버에서 받지 않고 클라가 `소스 메타 프레임 → 물리 → 타깃 현재 컨트롤`로 배치. 오버레이 전용 변환 코드 0줄(메인 로드와 같은 함수). 화면에서 변환을 바꾸면 오버레이가 따라온다. 검수 A(기하) 15개 공격 전패, 검수 B가 잡은 fail-open 2종 수정. UI 순증 0. 이슈 #18 종결 | `7d931dc`+`251dbfd` · [검수 A](../../agent_workspace/reports/QA_overlay_unify_geometry.md) · [검수 B](../../agent_workspace/reports/QA_overlay_unify_behavior.md) |
| 서버+클라/계획 | **M2-v2 「계획 = 그 맵 자체」** — `bonding_map` 열면 본딩 계획, stage는 열린 테이블에서 유도. `plan_id`·별도 계획 테이블 폐기, 정체성은 `(ref_table, map_key)`. 병렬 QA 첫 적용(A·B 동시) → 양쪽 NO-GO → A1(프레임 규격 좌표)·C1(DOE 전량 삭제) 수정 후 병합 | `da65a87` · [히스토리](../history/20260726_204344_m2_v2_plan_as_map_redesign.md) |
| 인프라/테스트 | **스위트에서 허용 실패 제거 — 414 passed / 0 failed** — 라이브 사용자 자산에 쓰던 테스트 2종 격리(`maps.json`, 워크스페이스 `config.json`). `.sample` config가 v1 잔재라 신규 환경이 안 뜨던 문제 수정 | `9a8ede8` |
| 서버/인제션 | **대형 파일 P1 — heavy 레인 분리 + 진행 가시화 + 재기동 경고, 라이브 드릴 PASS** — 크기 임계(기본 10MB, `ingestion_settings.json` 핫리로드) 라우팅·워크스페이스 FIFO 3중 보존·스윕 경로 포함, push 진행 스냅샷(`/admin/file-ingestion/active`)+admin File 탭 HEAVY 배지/경고 배너. 드릴 실측: **비차단 180배(2.3s vs 415s)·10만 행 유실 0·bk 중복 0·created_logs 정확 500건 절단·이벤트 루프 p50 3.5ms**. QUEUED 통지 역전·total_log_count 비대칭 후속 수정 완료. 테스트 278 passed(+27) | `4fd8ac9`+`8b0fd03` · [히스토리](../history/20260726_093100_large_file_p1_heavy_lane_and_live_drill.md) · [드릴 보고서](../../agent_workspace/reports/QA_p1_live_drill_report.md) |
| 서버+클라/맵 | **본딩 실험계획 M1(조회 전용)** — 역할 바인딩 config + `GET /api/bonding-plan/core-summary`(`server/bonding_plan.py` — align은 cell_to_physical 순수 인덱스 변환만, QA F1/F2 결함 지점 무참여) + map editor Info 패널(`bonding_plan.js` — 층 배정·수량/FAIL/조건 이탈 경고 3종·knob 비교·localStorage 초안) + fake 원천 2종(eds 180° align 실증). **rect 영역 선택 모드는 개발 중 폐기**(M2 값 페인팅 정본). 테스트 275 passed(+18) | `e6eabe4`+`24753d3` · [히스토리](../history/20260726_093200_bonding_plan_m1_info_panel_and_core_summary.md) |
| 설계/온톨로지 | **DT/Tape 계층 편입(스펙 §7.5b) + Universal Transfer Plan/DOE 관리 단위 확정** — bonding의 core lot/slot=실제 DT lot/slot, 전사 프리미티브 일반화, value=DOE 조건군 | `63ac0c3`·`437d6d5` · [히스토리](../history/20260726_093300_dt_tape_layer_universal_transfer_plan_design.md) |
| 클라/그래프 | **뷰어 stats 라벨 카드 클릭 → 노드 리스트**(빈 q+label 서버 리스팅 캡 200, 행 클릭 explore 연동) | `df63f3a` · [히스토리](../history/20260726_093400_graph_viewer_label_node_list.md) |
| 클라/그래프 | **뷰어 Connections 테이블 + 검색 시드 연동** — 노드 클릭=선택+관계 테이블(비중심은 depth-1 보강, 80행 페이지), 행 클릭 → 중심 재조회+URL push/popstate+검색바 반영, 패널 접기. ⚠️ 중심 이동이 클릭→**더블클릭**으로 변경(사용자 공지 권장) | `18218da` · [히스토리](../history/20260725_222215_graph_viewer_connections_table.md) |
| 스펙/그래프 | **§7.5c 정적/동적 노드 분류 + 4대 탐색 정책** 수렴(S→D 기본 금지·2단계 백본→ROI·EqpState 허브앤스포크) — 정책 엔진이 **G2.5 전제 조건**으로 승격 | `99c4cb6` · [히스토리](../history/20260725_222347_ontology_spec_static_dynamic_traversal_policy.md) |
| 서버/인제션 | **워크스페이스 config.json 폐지** — `table_name`/`std_parse`를 글로벌 table_config의 `workspace_name`/`std_parse`로 흡수(옵트아웃 핫리로드화 → F4 자연 해소), 신규 생성 중단+하위호환 읽기, QA 6건 반영(파일당 config 스냅샷·별칭 섀도잉/경로탈출 방어)·테스트 21건(스위트 229 passed) | `5fac5f0`+`20d6898` · [히스토리](../history/20260725_220619_workspace_config_deprecation.md) |
| 서버/그래프 | **온톨로지 G1** — graph_nodes/edges/graph_sync_state + 매핑 v2(description 필수, enrichment `RESOLVED_AS` 자동 승격) + materializer(증분 소비·QA H1/H2 provenance·retarget) | `6da2276`→`7c40a33`→`d130c65` |
| 서버/그래프 | **조회 API 5종** — stats/neighbors/search(뷰어) + trace/mapping-summary(G2, 공용 BFS 추출) | `c63b881`, `d8d109d` |
| 클라/그래프 | **그래프 뷰어 + 추적 리포트** — graph.html(BFS 동심원 캔버스)·trace.html(그룹+타임라인) + index 「🕸️ 추적」 진입점, 양방향 크로스링크 | `eea929d`/`f41ca3e`, `6c0a722`/`83507aa` |
| 클라/admin | **파이프라인 생애주기 5탭 IA 재편**(Overview/File/Chain/AutoUpdate/Enrichment, Code Editor 딥링크 공용 뷰, 구 해시 별칭 호환) — 라이브 검증 통과 | `7d02989`(소안), `3e599d2`/`387d987`(중안) |
| 서버/인제션 | **온보딩 완결** — std parser 폴백 + 워크스페이스 자동생성(`f90717f`) + 런타임 테이블 CREATE(#7, `6c447ee`) → "config 추가→리로드→즉시 사용" | [20260725_113212](../history/20260725_113212_std_parser_fallback_and_workspace_autoprovision.md), [20260725_170000](../history/20260725_170000_issue7_runtime_table_create.md) |
| 클라/테마 | **듀얼 테마(기본 라이트)** tokens.css SSOT + 다크 심화, 헤더 드롭다운 z-order 수정 | `765c7e5`~`cd3f90c`, `4229d9f`, `d48f25b` |
| 서버/체인 | 이슈 #0 종결 — outbox 지연·신뢰성(F1~F5·인라인 발사·웜업), 정상 31ms(SLO 100ms) | [task/chain_outbox_latency.md](../../task/chain_outbox_latency.md) |
| 서버 | 경합 수정 배치 1(C-1/C-2/C-3/C-5) + 감사 로그 미저장 수정(#6) | `4329c29`, `5fd8d24` |
| 전체 | **Enrichment Queue v1**(서버 dedup mapper + 컨베이어 + 참조뷰 + 결손 배지) — 스펙 Living 승격 | [20260725_130000](../history/20260725_130000_enrichment_queue_v1_complete.md) |
| 프로세스 | 코드맵+교훈 파일 체계(유지보수 doc-keeper 전담) · 기능 체크리스트 초판 · 에이전트 로스터 확장(qa-reviewer/doc-keeper/ui-designer) | `de79c50`, `d0c14a5`, `cbdc1e2` |
| 서버/체인 | **인시던트(21:29) 수정** — 체인 워커 created_logs 무절단(~50MB/6.5만 건) 전송 → :8080 이벤트 루프 GIL 동결 → 알림 타임아웃 연쇄. 발신측 500건 절단+`total_log_count`(C-5 계약 확장, `event_constants.py` 공용 상수). QA GO-WITH-FIXES(D-2 편승 적용) | [히스토리](../history/20260725_215500_chain_created_logs_truncation_incident.md) · [QA 리뷰](../../agent_workspace/reports/QA_chain_created_logs_truncation_review.md) |
| 서버/온톨로지 | **wafer_process lot/slot 확장**(사용자 config·핫리로드) — 수집기 lot_id/slot_no 기록, ProcessEvent props, enrichment 공정 이력 뷰 노출. 라이브 검증 통과(LOT-E\|25 분기 발화) | [보고서](../../agent_workspace/reports/Server_wafer_process_lot_slot_report.md) |

2026-07-24 이전 완료분은 [history/README.md](../history/README.md)와 [RELEASE_LOG](./RELEASE_LOG.md) 참조.

## ⏭️ 다음 단계 / 백로그 (Next / Backlog)

> 가동 중 트랙은 §현재 초점에 있다. 여기는 **대기열**이다.

**우선 순위 높음 (현재 초점 연동)**
- **대형 파일 인제션 — P1·P2 완료, P2 드릴 미실행, P3 미착수**
  - **P1** heavy 레인 ✅ 병합·드릴 PASS(비차단 180배, 유실 0). **P2** 체크포인트 재개 + sha256 dedup + #10 ✅ 병합·라이브 가동(`file_ingestion_checkpoints` 643행 실적재 확인).
  - **✅ P2 드릴 3종 PASS** (격리 환경 첫 사용, 2026-07-27). **D1 재개**: 30,000/100,000 지점에서 `taskkill /F` — 커밋 오프셋과 실제 행수가 정확히 일치(주입 예외가 아닌 실제 강제 종료에서 원자성 관측), 재개 후 10만 행·10만 고유키·**기대 키 누락 0**(`generate_series` 안티조인으로 "10만 행인데 다른 10만"까지 차단), 건너뛰기 **275ms** vs 재적재 ~219초. **D2 dedup**: 동일 재투입 1.22초 `SKIPPED` vs `__force__` 1,687초 `SUCCESS` — **1,383배** 분리. **D3 #10**: 비대칭 5+2로 총계 7(구 SET 의미론이면 2), 단일 타깃 대조군 1. **회귀 없음**: 이벤트 루프 11,371 샘플 p50 5.1ms·250ms 초과 0건, 체크포인트 UPDATE는 청크의 **0.0097%**. 보고서 `agent_workspace/reports/QA_p2_drills_isolated.md`.
  - **P3(미착수)**: 후단 backpressure(outbox 파일 단위 집계, 경합 배치 2·C-4와 통합) · PG COPY 벌크 경로(프로파일링 선행) · `batch_row_upsert` items 행 데이터 상한 · audit `old/new_value` 길이 상한(`crud.py:224-236` — 대형 텍스트 셀이면 500건 절단으로도 수십 MB 재발) · heavy 워커 수 설정화(heavy 간 직렬 해소, outbox 파도 증폭 주의).
  - 잔여 QA 후속: F2 라우팅 원자화 · F4 공유 큐 대기 · F5~F7. 운영 수칙: AUTO_UPDATE_GUIDE에 증분(delta) 산출 가이드.
- G2.5 서브그래프 직렬화 → G3(그래프 시각화 고도화, Neo4j 병행 타깃). 시간 범위 스캔용 엣지 인덱스(event_time)는 G2.5 쿼리 설계와 함께.
- **[신규 2026-07-26] Chain Replay(룰 재적용)** — 룰 변경 시 기존 데이터 재적용. 설계: 원천 keyset 재계산(그래프 resync 패턴) + 레이어링의 user 보호 + stale 소스 철회(H2-b 패턴 셀 버전) + dry-run 우선. 단계 R1(dry-run+적용)→R2(stale 철회)→R3(admin 위저드). 착수 전 확정: 매퍼 파일 컨텍스트 의존성·다중 룰 의존·enrichment dedup 별도 취급. P1 병합 후 R1 권장.
- map_split_registry(현재 초점 #2) — client-pm 착수.
- **[본딩 실험계획 — ✅ M1 완료(2026-07-26), 다음은 M2 = Universal Transfer Plan]** M1 산출물(Info 패널·역할 바인딩 config·core-summary·align 서버 단독 변환·rect 모드 폐기)은 [히스토리](../history/20260726_093200_bonding_plan_m1_info_panel_and_core_summary.md), 설계 확정(DT/Tape·전사 프리미티브·DOE)은 [히스토리](../history/20260726_093300_dt_tape_layer_universal_transfer_plan_design.md) 참조. **M2 골자 — Universal Transfer Plan 프레임워크**(사용자 확정): 모든 단계=전사 프리미티브 `(stage, target 맵 페인팅, assignments[소스, 소스 영역, 타깃 값(층/코어), 수량])`, 가용=총−fail류(역할 바인딩)−기전사(단계 전사 로그), 테이프 가용은 코어 fail의 DT-조인 투영으로 제외, 신규 단계=config stage 선언만(코드 불변). **영역 지정 정본 = 값 페인팅**(base 맵 값=층 번호, 코어 맵=사용 영역 — rect 모드는 폐기됨, 서버 region 계약은 M2 cells 모드용 존치). **관리 단위 = value(DOE)**: value ↦ {소스, knob/조건, 수량, 자연어 설명} — map_split_registry 직계 확장, SplitCondition=DOE로 온톨로지 정합(G3 "어느 DOE에서 불량 군집" 질의). M2 작업 항목: 역할 바인딩에 dt_log/dt_map 추가 + 잔여 계산 2단계(코어 잔여 vs 테이프 위 가용) + 계획 페인팅은 DT 테이프 맵 위 + 관리 테이블 2종(`bonding_experiment_plan`/`bonding_plan_layer` — localStorage 초안 승격) + 온톨로지 ExperimentPlan·PlanLayer·TransferEvent 일반화 + **by_eqp 장비별 align 적용·align 보정 모드**(시험 align 서버 변환 오버레이 + 확정 시 config 원자 저장 — `make_align_transform` 주입형이라 재사용 가능) → M3(실적 대조·중복 배정 감지·EDS 연동). M1 이월 잔재: total_chips는 실 운영에서 칩 레벨 total 테이블로 재바인딩 필요(현 config는 core_defect_map 풀맵 겸용 — escalation 승인분), 기존 bonding fake의 마스크 밖 (cx,cy) 미세 왜곡(미접촉). 착수 전 사용자 확인(잔여 2건): ①defect/EDS 원천 위치 ②실로그의 knob 형태.
- enrichment 실전 규칙(현재 초점 #3).

**그래프 트랙 미결 정책**
- 행 DELETE 시 그래프 정리 정책(스펙 §8 — materializer는 DELETE 스킵, stale 엣지 잔존). `idx_graph_edges_row_ref`가 구현 기반.
- 운영 수칙: outbox 7일 purge보다 materializer 장기 정지 시 증분 유실 → `/api/graph/sync {"table_name":"all"}` 복구(문서화됨 — [event_driven_backend §4.3](../architecture/event_driven_backend.md)).
- search ILIKE 프리픽스 인덱스 한계(pg_trgm/text_pattern_ops 검토) · stats GROUP BY 캐시 — 그래프 대형화 시.

**admin 이관 목록** ([중안 보고서 §E](../../agent_workspace/reports/Client_admin_ux_mid_report.md))
- Enrichment 규칙 CRUD API · Chain rule CRUD API · 워크스페이스 생성/검증 API · 파이프라인별 "신규 추가" 위저드 UI · 헬스 시간창 집계 API(+파일 로그 서버 검색/정렬).

**관찰/저순위**
- [드릴 2026-07-26] :8080 이벤트 루프 지터 0.68%(100~846ms 단발, 동결 아님) 발생원 미규명 — 장기 프로파일링은 별도 태스크(qa-reviewer 위임 후보).
- [드릴 2026-07-26] 드릴 생성물 정리 대기(총괄 수행) — config 항목·물리 테이블 `hvy_drill_big`(100,008행)/`hvy_drill_small`·워크스페이스 2식·FileIngestionLog 5행: [드릴 보고서 §7](../../agent_workspace/reports/QA_p1_live_drill_report.md) 목록 참조.
- 워크스페이스 레거시 config.json **읽기 경로의 최종 제거 시점** — 총괄 결정 대기(현재는 하위호환 읽기 + deprecation 경고 가동, 실 워크스페이스 14곳 전수 무영향 확인).
- 레이어링 표시 정합 의심 1건: `priority_source: chain_ingestion`인데 표시 값은 system 소스 값(38320 vs 3832) — chain_ingestion 서열 등재(#5 배치에 동승 가능) 후 재확인.
- 재생성 소스 삭제 시 경고 표시 UX(파이프라인이 소스를 재생성하는 것은 레이어링 설계상 정상 — 비이슈 종결됨).
- main.py 셀 히스토리 라우트 이중 정의(~2020 사장) · `client2/src/counter.js` 템플릿 잔재 — 소규모 정리 후보.
- 재기동 첫 체인 579ms(수용) — 잔여 mapper 첫 쿼리 웜업.
- [라이브 검증 PASS 관찰 3건, 다음 서버 배치 동승 후보] ① pytest가 라이브 로그 파일 오염 → 테스트 로거 분리 ② created_logs 절단 발동 시 무음 → `truncated N→500` 1줄 로그 ③ wafer_process lot_id UndefinedColumn 1회(21:48, 컬럼 핫추가 과도기 — #9와 같은 뿌리 추정).
- wafer_process에 `lot`/`slot`(기존)과 `lot_id`/`slot_no`(신규)가 중복 공존 — 데모 테이블이라 수용, 실전화 시 하나로 통일 필요. Lot 노드 label 신설 여부도 미결(현재 props까지만).
- 루트 `task/` 대기: `cursor_based_pagination_pending.md`, `total_count_sync_pending.md`, `desktop_hybrid_wrapper_plan.md`.

## 🐞 열린 문제 (Open Problems)

| # | 심각도 | 문제 | 도메인 | 상태 |
|---|---|---|---|---|
| 4 | 낮음 | `test_map_presets_api` 기존 실패(맵 프리셋 도메인, #0 이전부터) — **잔여는 이것 1건뿐**(enrichment 테스트 격리 버그는 2026-07-25 해소, 현재 스위트 177 passed / 1 failed) | Client·Server | 대기 |
| 5 | 중간 | **경합 점검 잔여 리스크(수정 배치 2 후보)** — C-4(체인 큐 독점·HOL, 매퍼 의미론 협의 필요)·C-6(동시 upsert 행 락 순서)·C-8(런타임 ALTER 락 컨보이)·C-9(커넥션 풀 합계>max_connections)·C-10(워처 .tmp 필터 부재)·C-11(WS 직렬 전송) + created_logs 무상한 전송 잔여. 상세: [점검 보고서](../../agent_workspace/reports/Server_contention_audit.md) (C-7은 그래프 키셋 청킹으로 해소됨) | Server | 대기 |
| 2 | 낮음 | 맵 이월 시 A/B의 x·y·val 컬럼명이 크게 다르면 자동 정합 안 됨(저장 전 Advanced Column Mapping 수동 확인 필요) | Client | 대기(관찰) |
| 3 | 정보 | 미리보기 브라우저 pane이 비-compositing → rAF/ResizeObserver 자동발화·CSS transition 프리즈로 라이브 UI 자동검증 제약(실제 브라우저 무관) | 검증환경 | 알려짐 |
| 9 | 중간 | **config_watcher가 원자적 쓰기(temp+rename)를 감지 못함** — on_modified만 처리해 에이전트 Edit류 저장 시 기존 테이블 ALTER가 조용히 누락(on_moved 미처리). 스키마 API는 config 싱글턴이라 200이어도 물리 반영 증거 아님 | Server | 대기(수정 소형 — on_moved 보강) |
| 10 | 낮음 | audit_cache total_count 과소 표기(QA D-1) — 멀티 target-table tx에서 테이블별 total_log_count가 SET 덮어쓰기. 기존 결함(회귀 아님), production_plan 체인+enrichment 동시 트리거로 도달 가능 | Server | 대기(P2 동승) |
| 20 | 중간 | **변환 구현이 아직 둘이다 — `bonding_plan.py`가 자기 사본을 갖고 있다**(구 A2의 정체). doc-keeper 4차가 총괄의 오인을 잡았다: `bonding_plan.py`는 `map_overlay`를 **참조 0건**이고 자체 `normalize_align`/`make_align_transform`(`:74`,`:140`)을 쓴다. `transfer_plan.py`도 `resolve_binding`/`build_key_filters`/`load_overlay_config`만 쓰고 **정렬 함수는 안 쓴다**. 즉 A1 수정이 `bonding_plan`에 전파되지 않은 이유가 이것이고, 오버레이에서 방금 없앤 "두 구현" 문제가 **가용량 산출에는 그대로 살아 있다**(`bonding_plan.py:199-204` bbox 항 없는 구 산술 — 라이브 오버라이드 없어 휴면). 부수 발견: 클라가 서버 정렬 좌표 소비를 멈춘 뒤로 `map_overlay`의 정렬 함수군(`resolve_align`/`make_frame_transform`/`_frame_transformer`/`_frame_phys_params`) **운영 소비자가 0**이다 — 호출처는 엔드포인트 자신과 자기 테스트뿐. 폐기 여부 판단 필요 | Server | 대기 |
| 11 | 중간(격하) | **좌표 변환 서버-클라 드리프트** ([감사](../../agent_workspace/reports/QA_map_transform_logic_audit.md)) — F1: rot=90/270 비등방 칩에서 transformer가 회전 치수·비회전 chip 혼용 · F2: 엔진 미장착 fallback 타원 ±1 어긋남 · F3[중]: 클라 getPhysicalCoords의 mm 오프셋 반올림 혼입(서버 정의가 정론 — 경계 계약 명문화 필요). **M1 align이 결함 지점을 구조적으로 우회 완료**(`bonding_plan.make_align_transform` — cell_to_physical 순수 인덱스 변환만, 엔진 fallback 무참여 + 90/270 치수 스왑 규약 + 규격 불명 시 `align_unavailable` 명시 실패). transformer 자체의 F1/F2 수정과 F3 계약 명문화는 잔여(현 소비자는 안전 경로만 사용) | Server·Client | M1 우회 완료 — 근본 수정 대기 |
| 16 | **높음(격상)** | **테스트 스위트가 라이브 환경으로 샌다 — 2계통 실증** ⓐ **운영 PostgreSQL에 DDL 발행**: `main.py` import 시 모듈 레벨 `Base.metadata.create_all`(main.py:44)이 실 DB에 대해 실행되어, 테스트만 돌려도 신규 테이블이 라이브에 생성된다(P2에서 실제 발생 — 빈 테이블이라 무해했으나 경로가 위험). ⓑ **사용자 config에 써넣는다**: `test_map_presets_api`가 `POST /api/map-presets`로 라이브 `server/config/maps.json`을 수정한다. 실증 — 현재 프리셋 키가 `['custom_1784890104442', 'core_std', 'base_std', 'tape_std']`이고 첫 항목이 테스트 산물(총괄 직접 확인). 같은 테스트가 `maps.json.sample`에만 있는 키를 라이브에서 찾아 단언하므로 **세션 내내 "상시 허용 실패"로 취급돼 왔다 — 항상 실패하는 테스트는 스위트 전체의 신호를 죽인다.** **✅ ⓑ 해소(`9a8ede8`)** — 두 오염 테스트 격리. `test_map_presets_api`는 `tmp_path` + `MAPS_CONFIG_PATH` 패치, 단언을 `set(presets) == {심은 키}`로 써서 **격리가 풀리면 즉시 깨지게** 했다. `test_file_ingestion_callback_direct`는 핸들러가 이미 경로를 생성자 인자로 받으므로 패치 없이 `tmp_path` 주입으로 끝났고, `config.json` 쓰기는 **제거**(폐기 개념 + `columns` 키 무소비 + 테이블명이 `default_table_name`으로 동일 해석) 후 재생성 시 깨지는 네거티브 단언을 넣었다. **증명은 바이트 동일성** — `maps.json`의 sha256·크기·**mtime**까지 불변, `ingestion_workspace` 9,230파일 `changed=0`. 생긴 3파일이 수집기 산물임은 **pytest를 안 돌린 동일 길이 창 대조군**으로 실증. **스위트 414 passed / 0 failed — 허용 실패 소멸.** ⓐ(운영 DB DDL)는 잔존하나 테스트 엔진은 전부 sqlite 메모리/tmp로 확인됨. 라이브 잔재 2건(`maps.json`의 `custom_…`, `inventory_master/config/config.json`)은 **사용자 자산이라 미삭제 — 원본 미상·복구 불가로 고지함** | Server | ⓑ 해소 / ⓐ 대기 |
| 15 | 중간 | **`Wafer` label에 이질적 정체 혼입**(2026-07-26 온톨로지 리뷰 발견) — `wafer_slot_history.wafer_id`(예 `A123`)와 `core_wafer_map.core_lot\|core_slot`(예 `LOT-A\|05`)이 같은 label에 공존해 서로 조인 불가. 더 근본적으로 **후자는 DT 계층 판명으로 실은 테이프 위치**(스펙 §7.5b)라 "테이프 91개를 Wafer라 부르는" 상태. 방치 시 불량 역추적이 엉뚱한 개체를 지목. **M2에서 dt_map/dt_log 올릴 때 정리 필수**. 파생 결정: 층 배정 온톨로지 매핑(§14-4)도 같은 패턴이라 보류, 별도 label(`PlanLayer`)로 §7.5c node_class 작업 시 처리 | Server·온톨로지 | M2에서 처리 |
| 14 | 중간 | **맵 push 경로 기존 결함 3종**([QA M2 리뷰](../../agent_workspace/reports/QA_transfer_plan_m2_review.md) 부수 발견, **M2 회귀 아님 — 전 맵 공통**) — ⓐ `limit=2000` + `replace_map` 조합에서 2000셀 초과 맵의 데이터 소실 가능(현행 프리셋 최대 1600셀이라 미발화) ⓑ `GET /tables/{t}/schema`가 미존재 테이블에도 200 반환(존재 확인 불가) ⓒ 클라 `CURRENT_USER`가 빌드 시점 값으로 박힘(번들 확인) | Server·Client | 대기 |
| 13 | 중간 | **`crud.load_table_config()`가 JSON 파싱 실패 시 로그 없이 `{}` 반환** — 가동 중에는 `refresh_dynamic_models`의 빈-config 가드가 막지만, **손상된 config로 재기동하면 전 테이블이 조용히 사라진다**. 최소 `logger.error` + 기동 시 명시 실패(fail-fast) 검토. CONFIG_GUIDE 함정 A로 문서화됨 | Server | 대기(소형) |
| 17 | 중간 | **계획 자재 500행 초과 시 영구 저장 불가** (QA-B의 C3) — 클라가 `limit=500`으로 조회하고(`client2/src/transfer_plan.js:1068/1104`) `total > rows`면 로드 실패로 강등하는데, 그 강등이 쓰기 보류로 이어지므로 **자재 500행을 넘긴 계획은 저장 경로가 영구히 닫힌다**. 강등 자체는 옳다(절단된 상태로 prune하면 전량 삭제) — 페이징이나 상한 상향이 필요 | Client·Server | 대기 |
| 18 | 중간 | **오버레이 기하 시그니처에 물리 파라미터 누락** (QA-B의 C7) — `currentGeomSignature()`(`client2/src/map_editor.js`)가 cols/rows/start/invertY/rot/side만 보고 `phys_*`(칩 피치·오프셋·직경·edge margin)를 빼먹어, 물리 규격을 바꾸면 오버레이가 **조용히 안 따라온다**. 기존 결함이나 신규 `importOverlayToGrid`가 어긋난 좌표를 `gridData`에 써 넣어 **표시 오류에서 데이터 오염으로 승격**됐다. **오버레이 변환 일원화 작업의 수용 기준에 포함시켰다** | Client | 일원화 작업에 동승 |
| 19 | 낮음 | **페인트 잠금 콜드 스타트 fail-open** (QA-B의 C4) — `degrade()`가 유지하는 "직전 값"이 로드 직후에는 기본값 `{enabled:false}`(`client2/src/map_editor.js:37`)라, **첫 조회가 실패하면 8개 강제 지점이 열린 채 시작**한다. 칩으로 표시는 되므로 *조용한* fail-open은 해소된 상태 — "fail-open 제거"라는 서술만 과장이었다 | Client | 대기 |
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
