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

> **[총괄 -> 구현자 B] 10-13 — 큐 1 다음, 큐 2 앞: 원장 행 색인 키에 «분자의 행 목록 전부»가 들어가 큰 group_by 분자의 번역이 통째로 실패 (응용 331ac83b1)**

```
코드(운영에도 참)  ledger/schema.py create_row_ref_sql — PRIMARY KEY (relation, row_id, source_who, source_raw_ref)
                  group_by 분자의 source_raw_ref = 그 분자 행 참조 «전부»의 JSON(roleframe._claim_source_raw_ref)
                  btree 한 줄 상한(압축 뒤 바이트)을 넘으면 그 사건이 통째로 failed — ProgramLimitExceeded. 상한은 행 수가 아니라 바이트
                  drain_outbox_once 는 ledger_state IS NULL 만 다시 집음 — failed 는 requeue_failed 로만, 같은 행이면 같은 키라 또 실패
박스 수            1,000 행 체인 그룹(파일마다 dt_job 2 × 500 행, group_by dt_job) 10 / 10 failed · 오류 4464 > 2704 바이트 · 넣은 1만 행의 행 색인 0
                  베낀 판 기존 묶음: 150 행은 색인 있음 / 400 · 12000 행은 색인 0 · 원자 0 (들어맞을 뿐 증명은 아님)
모름              운영 선언에 group_by 소스가 있는지 · 운영 묶음 크기 · 실패가 운영자 화면 어디에 보이는지
정함              키는 «source_raw_ref 의 지문»(해시) — 지문을 짓는 자리 하나를 쓰는 쪽 · 지우는 쪽 · 읽는 쪽이 다 지난다. 전문은 키 밖 칸으로 남긴다
                  (키에 ref 가 든 까닭 — 한 행이 여러 문장의 부분집합에 들 때 둘째가 첫째를 덮지 않게 — 은 지문으로 그대로 지켜진다)
할 것             ① row_ref 를 읽고 쓰는 자리 전수(AST · 세상마다 스키마) ② 지문 자리 하나 ③ 있는 표 이주 — 운영 크기에서 짓는 초 · 잠금을 먼저 적고, 되돌리는 길
                  ④ 실패한 사건을 다시 집는 법을 RUN.md 에(이주 뒤 requeue_failed 한 줄 + 그 답의 뜻) ⑤ 이 실패가 지금 운영자에게 어디 보이는지 열어서 적는다(안 보이면 그 사실)
게이트            group_by 분자 1,000 · 10,000 행이 번역된다 · 한 행을 지우면 그 행의 원자가 거둬진다(키에 ref 가 든 까닭) · 이주 전후 행 색인 같은 수 ·
                  지문 자리를 비틀면 빨강 · 진짜 프로세스(박스 베낀 판 런처) 한 판에서 응용의 1,000 행 그룹이 원장 다리까지 끝난다
순서              큐 1 착지 -> 이것 -> 큐 2 (원장에 안 들어가는 데이터라 앞)
```

> **[총괄 -> 구현자 B] 10-13 — 큐 5(제안 먼저): 그리드 검색 · 개수가 매번 표의 산 행 전부를 읽는다 (응용 404c9ef38)**

```
응용 실측(박스 · dt_log 55 만 행 · 서버가 실제로 보낸 문장 EXPLAIN ANALYZE BUFFERS)
  검색   ILIKE — Seq Scan · 훑은 행 55 만 · 데움 전후 모두 약 15,000 블록을 PG 밖에서 읽음 · 사용자 10 부하 아래 p95 0.75~2.5 s
  개수   Index Only Scan(ix_dt_log_updated_at) · 훑은 행 55 만 · 0.12 s(새 연결 첫 번 0.5 s, 원인 안 잼)
  둘 다 운영 dt_log 크기에 비례 — 운영 크기는 모름
할 것    짓기 전에 안 셋을 총괄에게(무엇 · 운영자가 하는 일 · 좋은 점 · 위험 · 크기). 생각할 축: 검색 칸 인덱스를 «표 선언 indexes»에 적을 자리(글자 일부 찾기용 인덱스 종류) ·
         개수를 정확히 셀지 / 어림으로 보일지(바뀌면 화면 문장이 바뀜 — 소유자 물음) · 검색이 걸리는 칸 수
순서     큐 4 뒤. 다만 안 셋은 큐 사이 손이 빌 때 먼저 올려도 된다
```
