# 구현자 B — 체인 · 데이터 레인 지시서

> **[총괄 -> 구현자 B] 10-12 밤 개설 (소유자 「구현자 일 너무 많은데 세션 하나 더 만들까?」)**

```
누구      구현자 B. 구현자 A(걷기 레인, task/IMPLEMENTER_ORDERS.md)와 «파일이 안 겹치게» 나눈 둘째 구현 레인
읽을 것    CLAUDE.md 전부(착수 전 관문 · 문 가르기 금지 · 측정 상설 · 시험 상설) · docs/architecture/CODE_MAP.md 의 해당 절 ·
          아래 큐의 지시 원문(task/IMPLEMENTER_ORDERS.md 에서 커밋 해시로 찾는다)
보고      task/IMPLEMENTER_B_REPORTS.md 에 커밋 + 푸시, 그리고 총괄 세션에 메시지(ListAgents 에서 총괄을 찾는다)
          소유자께 계획을 올리지 않는다(plan mode 금지). 물음은 총괄에게 — 물음 하나가 걸리면 그 일만 세우고 다음 일로
트리       자기 워크트리 C:/wt-impl-b, 가지 이름 impl-b-<일>. main 트리(C:\Users\kk980\Developments\assyManager)에서 스테이지 · 빌드 금지
착지       총괄 QA 뒤에만 — 자기 워크트리에서 origin/main 위로 rebase 후 push HEAD:main. 넘기기 전 «진짜 프로세스»(박스 베낀 판 런처) 한 판
시험       파이썬은 conda env assy_manager 만 · pytest 에 API_BASE_URL=http://127.0.0.1:9 · DB 에 쓰는 재기는 이름 붙인 스크래치 스키마만(public 금지)
박스 DB    assy_test 의 체인 워커 · 런처는 레인 사이 한 번에 하나 — 띄우기 전 응용 세션에 «N 분» 요청, 끝나면 «내림»
커밋       git add · commit 에 경로를 붙인다(-a/-A 금지). 한글 · 백틱 · 역슬래시 든 본문은 파일로 쓰고 경로로 넘긴다
겹침       걷기 파일은 A 의 것 — server/ledger_api/ledger_subgraph.py · server/ledger/trace_router.py · server/runtime/process_pool.py ·
          server/ledger/setup_bundle.py(A 의 «행 붙이기»가 씀). B 는 손대지 않는다. 꼭 필요하면 총괄에게 먼저
운영       운영 설정 · 소유자 라이브 파일(ledger_config.json 등) · 운영 재기동은 손대지 않는다
```

## 큐 — 순서대로

```
1  소급 «쪽마다 통째 읽기» 셋 — IMPLEMENTER_ORDERS 5ad030347 + 덧붙임 2e8c6ac9c
   (표기 cell_sources 38.8 s · remove_shell_rows · fold_units, 게이트는 «읽은 행» · 100만에서 첫 줄 5 초 안)
2  키 인덱스 기제 하나로 — 74db23f4b (조인 · 판단키 · 접기 남길 행 · 파생 집계. 1 의 fold_units 단위 칸 읽기가 이 범위)
3  그리드 깊은 쪽 — 0b7d84462 의 C (값 칸 정렬이 요청마다 표를 통째로 정렬, 100만 1.64 s)
4  수식 계산기(서버) — 0b7d84462 의 B. 5d8b0d326(체인 집계 스팟파이어 철자)을 품는다.
   함수 목록은 클라가 task/SPOTFIRE_FUNCTIONS.md 로 준다 · 시험 문제 contracts/expression/vectors.json 첫 판은 B 가
   걷기 measure 를 같은 함수 표로 잇는 자리만 걷기 파일에 닿는다 — 그 한 걸음은 «맨 끝», A 의 허브 착지 뒤 rebase 해서, 총괄에게 먼저 알리고
```

> **[총괄 -> 구현자 B] 10-13 — 큐 1 에 더함: 보강 확인 sweep 의 «드라이 길»이 쪽도 멈춤도 없다 (응용 표 7)**

```
응용 실측  chain/enrichment/analysis.py run_auto_confirm_sweep — 100만(판단키 25 만)에서 45 초 상한을 걸었는데 450.6 초 동안 안 멈춤
          적용 길  쪽마다 확인 · 쪽 사이 checkpoint(멈춤)
          드라이 길 대기열을 처음에 전부 읽어 목록 하나(keyed = [row for page in pages …]) -> session_contract.discarding 의 SAVEPOINT 하나 안에서 키 전부
          -> 운영 크기에서 «미리보기»가 멈출 수 없고, 트랜잭션 하나를 몇 분 쥔다(100만 7.5 분)
          그리고 두 길 다: 후보 질의가 «키마다 한 번»(10만에서 25,000 번 · 13.8 s, 키당 SQL 3)
정함      드라이와 적용은 «같은 쪽 고리 하나» — 갈리는 것은 쪽 끝에서 «쓴다 / 버린다» 한 곳뿐(문 가르기 금지). 드라이도 쪽마다 SAVEPOINT 를 열고 버린다 · 쪽 사이 checkpoint
          후보 질의는 쪽마다 한 번(쪽의 판단키를 한 질의로) — 같은 쪽 고리 안에서
게이트    응용 판 그대로: 드라이 100만이 상한 안에서 멈춘다 · 가장 긴 트랜잭션이 쪽 하나 길이 · 키당 SQL 이 쪽당 상수로 · 드라이와 적용의 확인 결과가 같다
          응용이 적용 길도 같은 판에서 잰다(기준선)
```
