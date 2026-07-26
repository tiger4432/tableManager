# 📌 PROJECT STATUS — 진행 상황 & 문제 현황 (Living Board)

> **Status:** 🟢 Living | **Last-updated:** 2026-07-26 (M2 진행중·P2 착수·범용 오버레이 격상 반영)
> **역할:** 프로젝트의 **현재 진행 상황·열린 문제·다음 단계**를 담는 단일 상태 보드. **컨텍스트 압축/세션 교체에도 살아남는 영속 상태**다.
> **규칙:** 총괄(및 각 PM)은 작업 **착수 전 이 파일을 읽고**, **완료 후 갱신**한다. 상세 이력은 [history/](../history/README.md), 현재 아키텍처는 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md). 이 보드는 이력 로그가 아니다 — "지금 어디까지 왔고 무엇이 문제인가"만 담는다.

---

## 🎯 현재 초점 (Current Focus)

> 완료된 트랙은 여기서 내리고 §최근 완료로 옮긴다. **지금 손이 가 있는 것과 바로 다음 관문만** 남긴다.

0. **🔄 재기동 대기 — M2+P2 병합 완료(2026-07-26, 381 passed / 1 allowed fail)**. `8e34804`(M2) + P2 브랜치 병합. **재기동 후 확인**: ① 신규 라우트 3종(`/api/maps/overlay`, `/api/maps/paint-rules`, `/api/transfer-plan/stages`) 실응답 ② 서버 보고서 §16-2 체크리스트 9항(오버레이 F셀 124개·`align_applied.origin: derived`·`plan_store`에 `source_region` 키 부재가 정상) ③ P2 드릴 3종(체크포인트 재개·dedup·#10 — P2 보고서 §8) ④ 페인트 잠금이 F 차단으로 동작하는지. 준비 스크립트: `setup_ingestion_checkpoint.py`(멱등).

1. **🔴 M2-v2 「계획 = 그 맵 자체」 재설계 — 최우선, 구현 진행 중(2026-07-26 저녁)**

   **원칙**: `bonding_map` 열면 본딩 계획, `dt_map` 열면 DT 계획. stage는 열린 테이블에서 유도. 별도 stage 선택·타깃 입력·`plan_id` 없음. **"절대 복잡하면 안 된다"**(사용자) — 순 추가 3(자재 목록·브레드크럼·뒤로가기) vs 삭감 12종.

   | 구분 | 항목 | 상태 |
   |---|---|---|
   | **서버 완료** | frame↔physical 근본 수정(회전·거울상 통과, QA-B3 가드 은퇴) · 바인딩 자동 유도(선언 6→2) · 모델 v2(identity=`(ref_table,map_key)`, stage 역인덱스, DOE 재키잉) · **E1 밴드 차원**(`band_seq` 정수 identity + 라벨 비키 — 라벨 수정해도 자재 묶음 유지) | 391 passed |
   | **서버 진행** | 남은 좌표축 — **Y축 뒤집힘 + START X/Y**를 변환 파이프라인에 편입(QA O3: 시작좌표 무시로 전 셀 균일 오프셋인데 status ok) | 지시됨 |
   | **클라 완료** | stage 유도 · legend=DOE 아코디언 · 자재 목록 DOE별 그룹 · 프레임 스택(브레드크럼+뒤로가기) · **오버레이 경로 완전 분리**(4시점 불변 실증) · 메타 `(table,map_id)` 쌍 수정 · side indicator 누락 수정 | 빌드 통과 |
   | **클라 대기열** | ① 성공 알럿 토스트화(로드 완료 알럿 등 4종) ② **오버레이→실맵 가져오기**(이월 대체) ③ **STACK 다중 구간**(`1, 2-15, 16` + 밴드 행 추가) ④ **편집 대상 고정 제거**(핀·키 잠금 — 과거 맵 조회 편의, **Push 불일치 가드는 유지**) ⑤ **토스트 누적 수정**(상한·만료시각 기반·visibilitychange 정리·동종 집계) | 지시됨 |
   | **총괄 적용(라이브 config)** | `map_doe`/`map_doe_source` 생성(각 18컬럼) · paint_lock 기본 **F 잠금** · 오버레이 바인딩 복구(구코드 호환) | 완료 |
   | **보류** | 온톨로지 매핑(§4-2 미검증 + 이슈 #15 label 충돌 패턴) · 구 계획 테이블 물리 DROP(사용자 승인 필요) · **검증/경고 기능 일습**(사용자: "검증 쪽은 일단 구현하지 마") · Push 델타 모달(서버 셀카운트 엔드포인트 없음) · 자재맵 legend 교차 주입 · knobs 스톱갭 | — |

   **규율**: 읽기(조회)는 무마찰, 쓰기(Push)는 1회 확인. **다음 절차: 두 에이전트 완료 → QA 재검수 → 병합 → 재기동.**

   **🧭 재개 브리프 (컨텍스트 압축 대비 — 2026-07-26 작성)**
   - **미커밋 작업물의 위치**: 서버 v2는 `server/map_overlay.py`·`transfer_plan.py`·`main.py`(워킹트리), 클라 v2는 `client2/src/map_editor.js`·`transfer_plan.js`(워킹트리, `npm run build` 반영됨). **커밋 전이므로 `git status`로 범위를 먼저 확인할 것.**
   - **읽어야 할 보고서 3종**: `agent_workspace/reports/Server_transfer_plan_v2_impl_report.md`(§0 = 클라 계약, §4-1 = 적용 완료된 config, §5-2-bis = 좌표축), `Client_transfer_plan_v2_impl_report.md`(구현/보류/제거 3분류), `Design_transfer_plan_ui_v2.md`+`.html`(확정 시안).
   - **에이전트 재개 불가 시**: 위 보고서 3종 + 이 표만으로 잔여 작업을 새 지시서로 재구성 가능. 진행 중이던 클라 대기열 5건(위 표)이 유일한 미완 범위다.
   - **최근 스위트**: 405 passed / 1 allowed fail(`test_map_presets_api` — 상시 허용).
   - **재기동 필요 여부**: 서버 코드 변경분은 병합 후 재기동 필요. config 적용분(`map_doe` 등)은 이미 라이브 반영됨.
   - **doc-keeper 정비 미실행**: 트리거 17건 누적 — M2-v2 병합 후 CODE_MAP·히스토리·체크리스트 일괄 정비 필요(보드는 총괄 전담이라 제외).

1-1. ~~M2 Universal Transfer Plan(1차)~~ — 병합 완료(`8e34804`), 아래 재설계로 대체 진행 중. 전사 프리미티브(stage config 선언) + 관리 단위 value(DOE) + DT/Tape 계층. 서버부는 QA F1(degraded 시 `remaining` 과대) 3층 방어로 해소(307 passed) 후 F4/F6 수정 중, 클라부는 **사용자 지시로 UI 전면 단순화 재설계**(별도 패널 폐기 → 「2. Value Legend & Brush」 통합, 모드 A=base·DOE 팔레트 / 모드 B=코어·오버레이·수량). **관문: 재검수 GO → 병합 → 재기동**. 상세 골자는 §백로그 M2 항목.
2. **🟡 범용 맵 오버레이 — M2에서 파생돼 맵 인프라로 격상(사용자 지시)**. "모든 MAP을 universal하게 오버레이" — 임의의 맵을 임의의 맵 위에, **map meta가 달라도 서버가 정렬**해서 겹친다. 진입점은 「1. Map Search & Load」의 "정렬 후 오버레이?" 프롬프트. 계획 UI는 이 능력의 소비자일 뿐. align 기본값 규율: **선언 있으면 그대로 적용 / 없으면 identity(0°) / 계산 근거 없을 때만 `align_unavailable` 명시 실패**. 부수: 페인트 잠금(값 `F`) config화, align 선언의 맵 속성 승격 검토.
   - **📐 재설계 도메인 확정 사항(사용자 2026-07-26)**: ⓐ **층 차원 불요** — "1층과 꼭대기만 다르고 나머지는 거의 유사", 층에 따라 달라지는 건 *어느 소스를 쓰는가*이지 *어느 좌표를 쓰는가*가 아니다 → `bonding_map`은 `(base,x,y)` 2D 유지, 캔버스 층 스텝퍼 불요. 층 차이는 **DOE의 STACK 구간 행**이 표현하고, 층대별 좌표 차이가 있어도 **다른 value로 칠하면** 자연 표현됨. ⓑ **DOE 소스는 묶음(pool)** — "몇 층에 뭐가 들어갈지 정확히 예측 불가, 여러 DT 군 지정 가능(한 매 500칩이면 4매 묶어 투입)" → 계획 단위는 "이 층 구간에 이 묶음에서 총 N칩", 검증은 **묶음 합산 가용 vs 소요**. ⚠️ 스키마 함의: 현행 `transfer_plan_doe_layer` bk가 `doe_key|layer`라 층당 소스 1개만 담긴다 — 묶음 지원에 **키에 소스 차원 추가** 필요. ⓒ **defect = 영역×불량종류→BIN** (단순 양불 아님) → 오버레이는 종류/BIN 판독 가능해야 하고, 어떤 BIN을 사용 불가로 볼지가 설정 대상.
   - **🔜 M2 이후 재설계 논의 예정(사용자 지시 2026-07-26 "일단 마무리하고 다시 논의")** — 사용자 지적: "bonding_map을 열어 편집하면 그게 bonding plan, dt_map을 열면 dt plan이어야 하는데 Map Search & Load와 전사 계획이 따로 논다". **계획 = 그 맵 자체**, stage는 열린 테이블에서 유도. 폐기 후보: stage 선택 UI·타깃 입력창(맵 메타와 중복)·`buildPlanId`·`transfer_plan_map`(계획 맵이 곧 bonding_map/dt_map이라 사본 불필요)·페인팅 진입/이탈 모달. 살아남는 것: **DOE 정의(value ↦ 소스·층별 배정·knob·설명)** — 단 키가 `plan_id` → **`ref_table\|map_key`**(map_split_registry 관례)로 이동, 즉 **legend/split registry와 DOE를 하나로 합치는 방향**이 재설계 핵심. ⚠️ **C5 위험 확대 주의**: 새 모델은 격리된 계획 테이블이 아니라 **실운영 bonding_map/dt_map에 직접 칠하므로**, 맵 키 오변경 후 Push가 실맵 전량을 삭제할 수 있다 → "맵 키가 로드한 맵과 달라졌으면 Push 차단" 가드로 대체 필요(#14ⓐ와 뿌리 동일).

3. **🟢 대형 파일 P2 — worktree 구현 완료(브랜치 `worktree-agent-a4c63f415791a7d0e`, 커밋 `f78ab0a`+`190093a`), M2 병합 후 main 병합 대기**. 오프셋 체크포인트 재개 + sha256 파일 dedup(500MB 0.535s 실측) + 이슈 #10 + audit 값 4096자 상한. 307 passed(기준선 278 대비 +29), **`main.py` 무수정**(설계로 우회), 경계 계약 불변. 저장소는 `FileIngestionLog` 컬럼 추가 대신 **신규 테이블 `file_ingestion_checkpoints`** — `create_all`이 ALTER를 안 하므로 운영 DB에서 마이그레이션 순서 사고(admin File 탭 UndefinedColumn 500) 위험을 회피한 판단(총괄 승인). 라이브 검증은 재기동 후 드릴 3종(보고서 §8).
4. **⚪ 대기 트랙** — ⓐ **G2.5**: §7.5c 탐색 정책 엔진(node_class + 4대 룰) 선행 → LLM 도구 API ⓑ **enrichment 실전 규칙**: 사용자 실 스키마 확보가 조건 ⓒ **map_split_registry**: M2의 DOE(=SplitCondition 확장)와 통합 여지가 커져 **M2 확정 후 재평가** ⓓ **Chain Replay R1**.

## ✅ 최근 완료 (Recently Done) — 2026-07-25~26 롤업

| 영역 | 요약 | 근거 |
|---|---|---|
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

## 🐞 열린 문제 (Open Problems)

| # | 심각도 | 문제 | 도메인 | 상태 |
|---|---|---|---|---|
| 4 | 낮음 | `test_map_presets_api` 기존 실패(맵 프리셋 도메인, #0 이전부터) — **잔여는 이것 1건뿐**(enrichment 테스트 격리 버그는 2026-07-25 해소, 현재 스위트 177 passed / 1 failed) | Client·Server | 대기 |
| 5 | 중간 | **경합 점검 잔여 리스크(수정 배치 2 후보)** — C-4(체인 큐 독점·HOL, 매퍼 의미론 협의 필요)·C-6(동시 upsert 행 락 순서)·C-8(런타임 ALTER 락 컨보이)·C-9(커넥션 풀 합계>max_connections)·C-10(워처 .tmp 필터 부재)·C-11(WS 직렬 전송) + created_logs 무상한 전송 잔여. 상세: [점검 보고서](../../agent_workspace/reports/Server_contention_audit.md) (C-7은 그래프 키셋 청킹으로 해소됨) | Server | 대기 |
| 2 | 낮음 | 맵 이월 시 A/B의 x·y·val 컬럼명이 크게 다르면 자동 정합 안 됨(저장 전 Advanced Column Mapping 수동 확인 필요) | Client | 대기(관찰) |
| 3 | 정보 | 미리보기 브라우저 pane이 비-compositing → rAF/ResizeObserver 자동발화·CSS transition 프리즈로 라이브 UI 자동검증 제약(실제 브라우저 무관) | 검증환경 | 알려짐 |
| 9 | 중간 | **config_watcher가 원자적 쓰기(temp+rename)를 감지 못함** — on_modified만 처리해 에이전트 Edit류 저장 시 기존 테이블 ALTER가 조용히 누락(on_moved 미처리). 스키마 API는 config 싱글턴이라 200이어도 물리 반영 증거 아님 | Server | 대기(수정 소형 — on_moved 보강) |
| 10 | 낮음 | audit_cache total_count 과소 표기(QA D-1) — 멀티 target-table tx에서 테이블별 total_log_count가 SET 덮어쓰기. 기존 결함(회귀 아님), production_plan 체인+enrichment 동시 트리거로 도달 가능 | Server | 대기(P2 동승) |
| 11 | 중간(격하) | **좌표 변환 서버-클라 드리프트** ([감사](../../agent_workspace/reports/QA_map_transform_logic_audit.md)) — F1: rot=90/270 비등방 칩에서 transformer가 회전 치수·비회전 chip 혼용 · F2: 엔진 미장착 fallback 타원 ±1 어긋남 · F3[중]: 클라 getPhysicalCoords의 mm 오프셋 반올림 혼입(서버 정의가 정론 — 경계 계약 명문화 필요). **M1 align이 결함 지점을 구조적으로 우회 완료**(`bonding_plan.make_align_transform` — cell_to_physical 순수 인덱스 변환만, 엔진 fallback 무참여 + 90/270 치수 스왑 규약 + 규격 불명 시 `align_unavailable` 명시 실패). transformer 자체의 F1/F2 수정과 F3 계약 명문화는 잔여(현 소비자는 안전 경로만 사용) | Server·Client | M1 우회 완료 — 근본 수정 대기 |
| 16 | 중간 | **pytest가 운영 PostgreSQL에 DDL을 발행** — `main.py` import 시 모듈 레벨 `Base.metadata.create_all`(main.py:44)이 실 DB에 대해 실행되어, 테스트만 돌려도 신규 테이블이 라이브에 생성된다(P2에서 실제 발생 — 빈 테이블이라 무해했으나 경로 자체가 위험). 기존 동작이며 P2 회귀 아님. 테스트 환경 DB 격리 필요 | Server | 대기 |
| 15 | 중간 | **`Wafer` label에 이질적 정체 혼입**(2026-07-26 온톨로지 리뷰 발견) — `wafer_slot_history.wafer_id`(예 `A123`)와 `core_wafer_map.core_lot\|core_slot`(예 `LOT-A\|05`)이 같은 label에 공존해 서로 조인 불가. 더 근본적으로 **후자는 DT 계층 판명으로 실은 테이프 위치**(스펙 §7.5b)라 "테이프 91개를 Wafer라 부르는" 상태. 방치 시 불량 역추적이 엉뚱한 개체를 지목. **M2에서 dt_map/dt_log 올릴 때 정리 필수**. 파생 결정: 층 배정 온톨로지 매핑(§14-4)도 같은 패턴이라 보류, 별도 label(`PlanLayer`)로 §7.5c node_class 작업 시 처리 | Server·온톨로지 | M2에서 처리 |
| 14 | 중간 | **맵 push 경로 기존 결함 3종**([QA M2 리뷰](../../agent_workspace/reports/QA_transfer_plan_m2_review.md) 부수 발견, **M2 회귀 아님 — 전 맵 공통**) — ⓐ `limit=2000` + `replace_map` 조합에서 2000셀 초과 맵의 데이터 소실 가능(현행 프리셋 최대 1600셀이라 미발화) ⓑ `GET /tables/{t}/schema`가 미존재 테이블에도 200 반환(존재 확인 불가) ⓒ 클라 `CURRENT_USER`가 빌드 시점 값으로 박힘(번들 확인) | Server·Client | 대기 |
| 13 | 중간 | **`crud.load_table_config()`가 JSON 파싱 실패 시 로그 없이 `{}` 반환** — 가동 중에는 `refresh_dynamic_models`의 빈-config 가드가 막지만, **손상된 config로 재기동하면 전 테이블이 조용히 사라진다**. 최소 `logger.error` + 기동 시 명시 실패(fail-fast) 검토. CONFIG_GUIDE 함정 A로 문서화됨 | Server | 대기(소형) |
| 12 | 낮음 | **임베디드 모드 `trigger_ws_refresh` 레거시 경로 C-5 미적용** — main.py 임베디드(비-DECOUPLED) 콜백은 created_logs 절단 계약(C-5) 밖(레거시 5000 게이트). 분리 모드 운영에서는 무영향 — 드릴 관찰로 등재 | Server | 대기(저순위) |

**종결(2026-07-25):** #0 체인 outbox 지연·신뢰성(31ms) · #1 IntegrityAndQAExpert 스킬 웹 전환 · #6 감사 로그 DB 미저장 · #7 런타임 테이블 물리 CREATE · **#8 graph 워커 신규 테이블 미인지(G1 materializer의 SYSTEM_RELOAD 구독으로 해소)**.

## ⏭️ 다음 단계 / 백로그 (Next / Backlog)

> 가동 중 트랙은 §현재 초점에 있다. 여기는 **대기열**이다.

**우선 순위 높음 (현재 초점 연동)**
- **[사용자 승인 2026-07-25] 대형 파일 인제션 대응 전략 — ✅ P1 완료(2026-07-26, 드릴 PASS), P2/P3 잔여** — 장애 4종 중 HOL은 heavy 레인으로 해소(비차단 180배 실증). 잔여 단계: **P2** FileIngestionLog 오프셋 체크포인트 재개(재기동 시 전체 재처리 잔존 — admin 경고로 지혈만 됨) + 파일 해시 dedup + **#10 total_count 과소(D-1)** + audit old/new_value 길이 무제한(대형 텍스트 셀이면 500건 절단으로도 수십 MB 재발 여지, `crud.py:224-236`) → **P3** 경합 배치 2(C-4)와 통합한 후단 backpressure(outbox 파일 단위 집계) + PG COPY 벌크 경로(프로파일링 선행) + batch_row_upsert items 행 데이터 무제한 상한 + heavy 워커 수 설정화(escalation §6-3 — heavy 간 직렬 해소, outbox 파도 증폭 주의). 운영 수칙: AUTO_UPDATE_GUIDE에 증분(delta) 산출 가이드. 드릴 잔여: heavy 도중 재기동 멱등 수렴 실측(드릴 보고서 §5 계획 — 사용자 협의 후) + QA 후속(F2 라우팅 원자화·F4 공유 큐 대기·F5~F7).
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
