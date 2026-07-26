# 📌 PROJECT STATUS — 진행 상황 & 문제 현황 (Living Board)

> **Status:** 🟢 Living | **Last-updated:** 2026-07-25 (대청소 — 현재 상태 중심 재구성)
> **역할:** 프로젝트의 **현재 진행 상황·열린 문제·다음 단계**를 담는 단일 상태 보드. **컨텍스트 압축/세션 교체에도 살아남는 영속 상태**다.
> **규칙:** 총괄(및 각 PM)은 작업 **착수 전 이 파일을 읽고**, **완료 후 갱신**한다. 상세 이력은 [history/](../history/README.md), 현재 아키텍처는 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md). 이 보드는 이력 로그가 아니다 — "지금 어디까지 왔고 무엇이 문제인가"만 담는다.

---

## 🎯 현재 초점 (Current Focus)

1. **온톨로지 그래프 트랙 — G1+뷰어+G2 라이브 가동 완료(2026-07-25)**. PG 엣지 스토어 + outbox 증분 materializer(자동 승격) + 조회 API 5종 + 서브그래프 뷰어(graph.html) + 추적 리포트(trace.html)까지 실동·라이브 검증 통과([GraphLatency] lag 162ms, 교정→RESOLVED_AS(user) 실시간). 종합: [20260725_233000](../history/20260725_233000_ontology_graph_track_live_and_architecture_sync.md) · 스펙 [ONTOLOGY_GRAPH_SPEC](../spec/ONTOLOGY_GRAPH_SPEC.md). **다음: G2.5 — §7.5c 탐색 정책 엔진(node_class 선언 + 4대 룰) 선행 → 서브그래프 직렬화·도구 API → G3(시각화 고도화·Neo4j 병행)**.
2. **map_split_registry 착수 대기(사용자 승인)** — 맵 value description(실험 split 자연어)을 localStorage에서 동적 테이블로 승격 + SplitCondition 온톨로지 매핑 + 맵 에디터 로드/저장 전환. 지시서 `agent_workspace/tasks/Client_map_split_registry_task.md` 준비됨 — client-pm 위임 예정.
3. **Enrichment 실전 규칙 작성 대기** — 사용자의 실제 설비이력/bonding log 스키마 확보 → `table_config.json` 파생 테이블 + `enrichment_rules.json` 실규칙. (스모크 규칙 `line_model_owner_attribution`은 데모로 유지.)
4. **아키텍처 문서 대청소 완료(2026-07-25)** — SSOT·architecture 4종·CODE_MAP이 그래프 트랙/admin 5탭/6엔트리/온보딩 완결을 반영. SYSTEM_OVERVIEW 하나로 현행 파악 가능.

## ✅ 최근 완료 (Recently Done) — 2026-07-25 롤업

| 영역 | 요약 | 근거 |
|---|---|---|
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
| 11 | 높음 | **좌표 변환 서버-클라 드리프트** ([감사](../../agent_workspace/reports/QA_map_transform_logic_audit.md)) — F1: rot=90/270 비등방 칩에서 transformer가 회전 치수·비회전 chip 혼용 → 전 셀 불일치(chip 스왑으로 일치 실증됨) · F2: 엔진 미장착 fallback 타원이 클라 물리 원과 rot=0에서도 ±1 어긋남 · F3[중]: 클라 getPhysicalCoords가 mm 오프셋을 die 인덱스에 반올림 혼입(서버 정의가 정론 — 경계 계약 명문화 필요). 서버 transformer는 현재 프로덕션 소비자 0(tests만)이라 무증상이나 **본딩 align이 첫 실소비자 — M1/M2 착수 조건으로 F1·F2 해소 필수**(M1 에이전트에 반영 지시됨). F4·F5[낮] 표시 전용/이론적 | Server·Client | M1 경로 내 처리 중 |

**종결(2026-07-25):** #0 체인 outbox 지연·신뢰성(31ms) · #1 IntegrityAndQAExpert 스킬 웹 전환 · #6 감사 로그 DB 미저장 · #7 런타임 테이블 물리 CREATE · **#8 graph 워커 신규 테이블 미인지(G1 materializer의 SYSTEM_RELOAD 구독으로 해소)**.

## ⏭️ 다음 단계 / 백로그 (Next / Backlog)

**우선 순위 높음 (현재 초점 연동)**
- **[신규·사용자 승인 2026-07-25] 대형 파일 인제션 대응 전략** — 실측: 99,999행 CSV ≈ 7분(250행/s). 장애 4종(HOL 실시간 지연 / 재기동 시 전체 재처리 / outbox 후단 폭주 / 낮은 처리율). 단계: **P1** heavy 레인 분리(크기 임계 라우팅) + admin 진행 표시·재기동 경고 → **P2** FileIngestionLog 오프셋 체크포인트 재개 + 파일 해시 dedup + **#10 total_count 과소(D-1)** + audit old/new_value 길이 무제한(대형 텍스트 셀이면 500건 절단으로도 수십 MB 재발 여지, `crud.py:224-236`) → **P3** 경합 배치 2(C-4)와 통합한 후단 backpressure(outbox 파일 단위 집계) + PG COPY 벌크 경로(프로파일링 선행) + batch_row_upsert items 행 데이터 무제한 상한. 운영 수칙: AUTO_UPDATE_GUIDE에 증분(delta) 산출 가이드. (2026-07-25 21:29 인시던트로 시급성 실증 — 지혈은 created_logs 절단으로 완료)
- G2.5 서브그래프 직렬화 → G3(그래프 시각화 고도화, Neo4j 병행 타깃). 시간 범위 스캔용 엣지 인덱스(event_time)는 G2.5 쿼리 설계와 함께.
- **[신규 2026-07-26] Chain Replay(룰 재적용)** — 룰 변경 시 기존 데이터 재적용. 설계: 원천 keyset 재계산(그래프 resync 패턴) + 레이어링의 user 보호 + stale 소스 철회(H2-b 패턴 셀 버전) + dry-run 우선. 단계 R1(dry-run+적용)→R2(stale 철회)→R3(admin 위저드). 착수 전 확정: 매퍼 파일 컨텍스트 의존성·다중 룰 의존·enrichment dedup 별도 취급. P1 병합 후 R1 권장.
- map_split_registry(현재 초점 #2) — client-pm 착수.
- **[신규 2026-07-26] 본딩 실험계획 Info 창(map editor)** — base+multistack core 구성 계획·검증(잔여 칩=총−defect−EDS−기사용, 공정 이력 경고로 사고 방지). **공정 이력은 step+knob(공정 조건)까지**: wafer_process에 `recipe_id`+`knobs`(JSON) 추가, ProcessEvent props로 승격(함수의 파라미터 — §7.5b 정합), 코어 간 knob 비교 뷰(다른 값 하이라이트)로 조건 이탈 경고. 경고 3종: 수량/결과 FAIL/조건 이탈. **원천은 역할 바인딩 config**(`bonding_plan_config.json` — 역할(process_history/eds_fail/defect/used_chips)→실테이블·컬럼 매핑, 실환경 전환=config 교체, 미연결 역할은 부분 가동): 사용자 요구 "실 운영 테이블명 상이 — 커스텀 가능하게". **층 구조 모델**(2026-07-26 보강): 배정 행=`(layer_from, layer_to, core, 층당 수량, core 사용 영역, base 부착 영역)` — 소요=층당×층수 검증, 층 커버리지 검사. **공간 배정**: 맵 에디터 선택 도구로 코어 사용 영역/base 부착 영역 지정(region JSON), base 프리뷰 층별 오버레이, 잔여 검증은 영역 내 가용 칩 기준, M3에서 bonding_log 실적 (cx,cy)→(bx,by) 대조(계획 이탈 감지). 테이블 2개: `bonding_experiment_plan`(헤더)+`bonding_plan_layer`(배정). 경고 4종: 수량/FAIL/조건 이탈/영역 충돌. **좌표 얼라인 원칙(2026-07-26)**: defect/EDS는 계측 시 회전되어 좌표계가 다를 수 있음 → config `align`(rotation/flip/offset) 선언 + **변환은 서버 단독 실행**(기존 coordinate_transformer 재사용), 클라는 정렬된 결과만 소비(오버레이도 서버가 정렬해 반환 — 이중 구현 금지). 클라 변환이 불가피해지면 골든 벡터 공유 픽스처로 드리프트 차단. **align 보정 모드(M2, 사용자 확인된 실무 케이스)**: 시험 align도 서버가 변환해 오버레이 반환(클라는 렌더만 — 이중 구현 원천 회피), 확정 시 config 원자 저장(auto_update_control 패턴), **장비별 align**(`by_eqp` 키 — 계측 장비마다 회전 상이) 지원. M1은 스키마 호환만 선확보. **영역 지정 정본 = 값 그리기 재사용(M2, 사용자 제안 2026-07-26)**: 계획을 맵으로 페인팅 — base 맵에 값=층 번호, 코어 맵에 사용 영역 값. 임의 형상·층별 오버레이·저장(맵 테이블 push)·온톨로지 승격·계획vs실적 맵 diff(M3) 전부 기존 인프라 편승. ~~M1 rect 모드는 빠른 선택 숏컷으로 존치~~ → **rect 모드 삭제 지시(2026-07-26, 진행 중)** — 페인팅 단일 정본. region 계약(서버)은 M2 cells 모드용으로 존치. **DT/Tape 계층 편입(2026-07-26 도메인 공개)**: bonding_log의 core lot/slot = 실제로는 DT(테이프) lot/slot. 여러 코어 칩이 테이프에 혼재, DT 로그(칩 단위 코어↔테이프 대응)+DT 맵(영역→코어) 존재 → 스펙 §7.5b에 DTEvent/Tape 노드 편입 완료. M2 재설계 필요: 역할 바인딩에 dt_log/dt_map 추가, 잔여 계산 2단계(코어 잔여 vs 테이프 위 가용), 계획 페인팅은 DT 테이프 맵 위에서(영역→코어가 이미 보이는 캔버스). 사용자 확정(2026-07-26): **테이프에도 불량 섞임** + **DT 구성도 계획 대상** → **Universal Transfer Plan 프레임워크로 재정의**: 모든 단계=전사 프리미티브 `(stage, target 맵 페인팅, assignments[소스, 소스 영역, 타깃 값(층/코어), 수량])`, 가용=총−fail류(역할 바인딩)−기전사(단계 전사 로그), 테이프 가용은 코어 fail의 DT-조인 투영으로 제외, 신규 단계=config stage 선언만(코드 불변). 온톨로지 TransferEvent 일반화(DTEvent/BondingEvent 인스턴스). M1 산출물은 첫 인스턴스로 흡수. **관리 단위 = value(DOE) (사용자 확정 2026-07-26)**: "붙이는 행위"를 페인팅 value=DOE 조건군으로 관리 — value ↦ {소스, knob/조건, 수량, 자연어 설명}, 페인팅=DOE의 공간 분포. map_split_registry(value=실험 split)의 직계 확장이며 SplitCondition 노드=DOE로 온톨로지 정합(계획 DOE vs 실제 knobs vs 불량 분포가 그래프 한 체인 — G3 "어느 DOE에서 불량 군집" 질의 가능). 단계 M1(조회 전용+층 모델+영역 UI 골격)→M2(관리 테이블 2종+온톨로지 ExperimentPlan·PlanLayer)→M3(실적 대조·중복 배정 감지·EDS 연동). 착수 전 사용자 확인(잔여 2건): ①defect/EDS 원천 위치 ②실로그의 knob 형태.
- enrichment 실전 규칙(현재 초점 #3).

**그래프 트랙 미결 정책**
- 행 DELETE 시 그래프 정리 정책(스펙 §8 — materializer는 DELETE 스킵, stale 엣지 잔존). `idx_graph_edges_row_ref`가 구현 기반.
- 운영 수칙: outbox 7일 purge보다 materializer 장기 정지 시 증분 유실 → `/api/graph/sync {"table_name":"all"}` 복구(문서화됨 — [event_driven_backend §4.3](../architecture/event_driven_backend.md)).
- search ILIKE 프리픽스 인덱스 한계(pg_trgm/text_pattern_ops 검토) · stats GROUP BY 캐시 — 그래프 대형화 시.

**admin 이관 목록** ([중안 보고서 §E](../../agent_workspace/reports/Client_admin_ux_mid_report.md))
- Enrichment 규칙 CRUD API · Chain rule CRUD API · 워크스페이스 생성/검증 API · 파이프라인별 "신규 추가" 위저드 UI · 헬스 시간창 집계 API(+파일 로그 서버 검색/정렬).

**관찰/저순위**
- 워크스페이스 레거시 config.json **읽기 경로의 최종 제거 시점** — 총괄 결정 대기(현재는 하위호환 읽기 + deprecation 경고 가동, 실 워크스페이스 14곳 전수 무영향 확인).
- 레이어링 표시 정합 의심 1건: `priority_source: chain_ingestion`인데 표시 값은 system 소스 값(38320 vs 3832) — chain_ingestion 서열 등재(#5 배치에 동승 가능) 후 재확인.
- 재생성 소스 삭제 시 경고 표시 UX(파이프라인이 소스를 재생성하는 것은 레이어링 설계상 정상 — 비이슈 종결됨).
- main.py 셀 히스토리 라우트 이중 정의(~2020 사장) · `client2/src/counter.js` 템플릿 잔재 — 소규모 정리 후보.
- 재기동 첫 체인 579ms(수용) — 잔여 mapper 첫 쿼리 웜업.
- [라이브 검증 PASS 관찰 3건, 다음 서버 배치 동승 후보] ① pytest가 라이브 로그 파일 오염 → 테스트 로거 분리 ② created_logs 절단 발동 시 무음 → `truncated N→500` 1줄 로그 ③ wafer_process lot_id UndefinedColumn 1회(21:48, 컬럼 핫추가 과도기 — #9와 같은 뿌리 추정).
- wafer_process에 `lot`/`slot`(기존)과 `lot_id`/`slot_no`(신규)가 중복 공존 — 데모 테이블이라 수용, 실전화 시 하나로 통일 필요. Lot 노드 label 신설 여부도 미결(현재 props까지만).
- 루트 `task/` 대기: `cursor_based_pagination_pending.md`, `total_count_sync_pending.md`, `desktop_hybrid_wrapper_plan.md`.

## 🧭 환경 메모 (Env Notes)
- 로컬 테스트 테이블 `sample_map`은 `server/config/table_config.json`(gitignored)에만 존재 — 운영 무영향.
- 서버 기동: `python run_decoupled_app.py` (웹 :8080 + 워커 4종). 프론트 개발: `cd client2 && npm run dev`. dist는 추적·서빙 대상 → 소스 변경 시 `npm run build` 후 dist 커밋.
- 운영 서버는 `git pull` 후 이슈 #0 절차(재기동→인덱스→purge→VACUUM, `scripts/setup_db_performance.py`) 필요.

---
*갱신 규율: 이 보드는 상태의 단일 원천이다. 새 작업/문제/해결이 생기면 즉시 이 파일을 고친다. 이력 상세는 history, 이 파일은 "지금 어디까지 왔고 무엇이 문제인가"의 요약.*
