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

> **[총괄 -> 구현자 B] 10-13 — 모델링 뽑기의 LLM 요청을 체인 묶음 단위로 (소유자 「llm 요청 배치로 가능? 컨텍스트 풍부화 및 llm 요청 회수 제한 목적」 · 「모델링 뽑는 거」 · 「체인 배치로 받아서 문장 잘 합쳐서 지시문 구성해서 요청 날려」)**

```
지금      매퍼가 SDK ask_links(text, names, instruction) 를 «글 하나마다» 부른다 -> 요청 N 번 · 사전(노드 · 낱말 목록)을 N 번 보냄 · 바뀌지 않은 글도 소급 · 다시 돌리기마다 다시 물음
          답의 근거는 «그 글 안에 정말 있나»를 확인해 없으면 버린다(_evidence) — 여러 글을 한 번에 물어도 남의 글 근거는 걸러진다
정함      ask_links 가 «글 여럿»을 받는다 — 같은 이름 · 한 자리를 넓힌다(글 하나는 «하나짜리 묶음»으로, 둘째 함수 · 둘째 길 금지). mapper_sdk 의 이름도 그대로
          매퍼는 체인이 넘긴 묶음(그 그룹의 행들)을 한 번에 넘긴다: 글마다 id(행 키) · 글 · 선택 «문맥 칸»(그 행의 칸 몇 개, 예: 랏 · 공정 · 설비 — 매퍼가 고름)
지시문    사전 한 번 + 지시문(instruction) 한 번 + 글마다 «[id] 문맥 한 줄 / 글» 번호 붙여 이어 씀 — 같은 묶음의 글을 한자리에서 보게 해 문맥을 넓힌다
          답 모양 {"texts": [{"id": …, "links": [...]}]} — 뒤처리(근거 확인 · 방향 · one_of)는 글마다 지금 것 그대로
크기      묶음을 요청 하나에 다 못 담으면 «글자 수 상한»으로 쪼갠다 — 상한은 설정 한 칸(운영 게이트웨이 한도는 모름: 기본값은 보수적으로, 답에 «요청 k 번 · 글 n 개»)
실패      답에 빠진 id · 모양이 틀린 글은 그 글만 혼자 다시 한 번 묻고, 그래도 안 되면 그 글만 사유와 함께 거절 — 묶음 전체를 버리지 않는다. «묶음 실패 -> 글마다» 는 한 줄로 말한다
안 하는 것 답 기억(캐시)은 이번에 안 짓는다(소유자 지시 밖 — 제안으로만 올라가 있음)
게이트    가짜 LLM(정해진 답)으로: 글 n 개 -> 요청 ceil(n / 상한) 번 · 글마다 결과 == 글 하나씩 물은 결과 · 남의 글 근거를 댄 링크는 버려짐 · 빠진 id 는 혼자 다시 · 프롬프트 스냅숏 칸 ·
          매퍼 가이드(docs/guide) 에 «묶음으로 넘기는 법» 예시 — 예시는 제품 로더로 읽혀 돈다. 진짜 모델의 답 질은 이 박스에서 못 잼 — 보고에 «안 잼»
순서      큐 1 착지 -> 원장 행 색인 키(f7394bfdf) -> 이것 -> 큐 2
```

> **[총괄 -> 구현자 B] 10-13 — 고침(f7a79b242 LLM 묶음): 소유자 «ㄱ만해» · «분당 20 회 제한 있음»**

```
빼는 것   글마다 «문맥 칸» 은 거둔다 — 묶음(사전 한 번 + 지시문 한 번 + 글 번호 붙여 이어 쓰기)만. 답 기억(캐시) · 문맥 단위 선언도 안 함
분당 상한 운영 LLM 게이트웨이는 «분당 20 회». 요청을 내는 한 자리(utils/llm.ask_json)에서 기다린다 — 설정 한 칸(분당 요청 수, 기본 20). 게이트웨이가 «너무 많음»(429 등)을 주면 기다렸다 다시
          먼저 전수: ask_json 을 동시에 부를 수 있는 프로세스가 몇인지(체인 워커 · 서버의 dev_bench · 사전 제안 …). 둘 이상이면 프로세스마다 20 이 되어 상한을 넘는다 —
          그때는 프로세스 사이에 나눠 쓰는 상한(이미 있는 문: 원장/체인의 advisory lock 이나 표 하나)으로. 어느 쪽인지 짓기 전에 수와 함께 올려 주세요
          기다리는 동안은 «LLM 분당 상한 — n 초 기다림» 한 줄(체인 쪽 줄에 보이게)
게이트    가짜 LLM 으로 분당 21 번째가 기다리는지 · 429 뒤 다시 · 묶음 덕에 요청 수가 ceil(n / 상한) 인지
```

> **[총괄 -> 구현자 B] 10-13 — LLM 묶음 일에 더함: «이어진» 모델링 — 이미 아는 인과를 싣고 사슬로 잇게 (소유자 「모델링이 서로 연결이 되어야 온톨로지 쓰는데 다 단발성 모델링만 나옴 · 그래프가 아니라 그냥 쌍의 집합」 · 「ㅇㅇ 넣어」)**

```
원인     지금 프롬프트는 사전(노드 · 타입 · 낱말)만 보이고 기존 링크는 0 · 지시는 «쌍마다 하나씩» — 모델은 그래프를 모르고 글 하나의 쌍만 낸다
ㄱ        이미 아는 인과를 싣는다: 묶음 글에서 사전 낱말이 걸리는 노드(phrase_bag 한 자리)를 씨앗으로 걷기(직접 호출 · 접지 않음) — follow 술어 · 걸음 수는 «매퍼가 넘김»(코드에 술어 이름 0)
         닿은 링크를 «Known links, one per line: <원인 id> -> <결과 id> (<술어>)» 로 사전 아래에. 줄 수 상한은 설정 한 칸(넘으면 씨앗에 가까운 것부터, 답에 «n 줄 중 k 줄»)
         지시문 둘을 더함: 새 링크의 양 끝은 가능하면 이미 있는 노드(사전 · 아는 링크 위)로 · 글이 아는 사슬의 중간 단계를 말하면 그 단계를 잇는 링크로
ㄴ        사슬은 «같은 노드를 공유하는 쌍들»로 받는다 — 답 모양은 그대로(쌍 목록). 지시: A 가 B 를, B 가 C 를 일으키면 A->B · B->C 를 따로, 같은 것은 «같은 키 또는 같은 낱말»로
         (묶음 안 글 사이에서도). 단계마다 근거 확인은 지금 그대로 — 근거 없는 단계는 버림
잼        인과 그래프 연결성 명령 하나(server/scripts, 읽기만): --predicate <이름 여럿> [--world] -> 노드 수 · 링크 수 · 연결 덩어리 수 · 가장 큰 덩어리 비율 · 외톨이 쌍(양 끝 차수 1) 비율
         RUN.md 에 «운영에서 전후로 돌릴 명령 · 답의 뜻» — 운영 데이터는 우리가 못 보니 소유자가 잰다
게이트    가짜 LLM: 프롬프트 스냅숏에 아는 링크가 든다 · 상한 · 씨앗 없는 묶음은 그 절이 빈다 · 사슬 A->B->C 가 B 를 공유하는 두 쌍으로 · 연결성 명령이 픽스처(덩어리 셋 · 외톨이 둘)에서 맞는 수
         진짜 모델에서 연결이 좋아지는지는 박스에서 못 잼 — «안 잼», 소유자가 명령으로 잼
```

> **[총괄 -> 구현자 B] 10-13 — LLM 묶음 일 고침(d7a27a758 ㄱ): «이미 아는 인과»를 고르는 규칙 + 사전 줄이기 (소유자 「좀 더 스마트하게 샘플링해서 넣을 수 있을까? 프롬프트 너무 커지니까」 · 「ㅇㅇ」)**

```
고르는 차례  씨앗 = 묶음 글에 사전 낱말이 걸리는 노드(phrase_bag 한 자리)
            1 다리: 씨앗끼리 잇는 최단 경로 위의 링크(걷기의 만남 판정 · aux 와 같은 문을 쓸 수 있으면 그것으로)
            2 1 걸음: 씨앗에 바로 붙은 링크 — 확인된 것 · 근거 원자가 많은 것부터
            3 2 걸음: 남는 자리에만
            골고루: 씨앗마다 최대 k 줄(설정), 씨앗을 돌아가며 채운다 — 이웃 많은 노드 하나가 자리를 다 먹지 않게
            무작위 없음 — 같은 글은 늘 같은 프롬프트(정렬 열쇠: 차례 · 근거 수 · id)
사전 줄이기  사전 전체가 아니라 «씨앗 + 고른 링크 위 노드»만 싣는다. 대가: 글에 낱말이 그대로 안 나오는 동의어 노드는 빠짐 -> 모델은 null, phrase_bag 이 받음
묶어 적기    «A -> B, C, D (술어)» 원인 하나에 결과를 모음
상한        «사전 + 아는 링크» 글자 수 상한 한 칸(설정) — 위 차례로 채우고, 못 실은 것은 답에 «n 줄 중 k 줄 · 사전 m 중 j»
게이트      가짜 LLM: 다리 링크가 1 걸음보다 먼저 · 씨앗마다 k 줄 · 같은 묶음 두 번 -> 같은 프롬프트(바이트) · 상한에서 잘린 수가 답에 · 사전에 씨앗 밖 노드 0
```

> **[총괄 -> 구현자 B] 10-13 — 큐 1 QA(3ff350a46): GO-WITH-FIXES — 틀린 답 재현 0 · 접기 차분 기점과 7/7 · PG 83 초록. 착지 전 고칠 것 (53537acd7 · 94db41466 은 다음 확인에서)**

```
1 [중] 한 선언에 판정이 둘 — 참조뷰가 «:bind::type» 철자를 쓰면 한 키 길(SQLAlchemy text)은 42601 로 거절, 묶음 길(로더 _BIND_PARAM_RE)은 후보를 냄(config.py:1679)
       쪽 크기가 1 에서 시작하니 첫 쪽은 거절 · 둘째 쪽부터 확정(apply 면 씀). 체인 훅도 flush 키 1 개면 거절 · 여럿이면 확정
       -> 바인드를 읽는 자리는 하나. 로더가 적재 때 «:x::type» 을 거절하고 «CAST(:x AS type) 로 쓰라» 한 줄 — 두 길이 같은 파서를 지난다(이 박스 선언에는 그 철자 0 — 박스 수)
2 [중] 묶음 실패가 운영자에게 조용하고, 로그 문장은 진짜 뷰 고장과 같은 SITE_CANDIDATE_PROBE(config.py:1694) — probe_batch_fallbacks 를 읽는 곳 0
       실측: 숫자 칸과 글 키를 견주는 뷰는 VALUES 칸이 text 로 굳어 쪽마다 묶음 실패(UndefinedFunction) -> 키마다 다시(답은 맞음) · ERROR 트레이스 · 진짜 실패가 throttle 에 묻힘
       -> 묶음 실패에 제 문장 · 실행 결과와 로그에 «묶음 -> 키마다 n 번». 그리고 VALUES 칸의 형을 판단키 칸의 형으로(한 키 길과 같은 비교가 되게)
3 [중] 중복 접기 dry · 미리보기(GET /admin/retroactive/fold_duplicate_rows/count)가 지울 행을 전부 받아 버림(replay.py:1045 _fold_read · 995-1000) — 1M 판 80 만 행 -> apply 때만
4 [중] SHELL_PAGE = 20000 이 한 쪽 = 한 트랜잭션 — uuid7 이라 껍데기가 몰린 구간에서 한 쪽 약 9.7 s(보고서 0.485 s/1000) · 2 만 행 한 커밋 -> 5 초 규칙 넘음
       -> 읽는 쪽은 크게 두고 지우기는 쪽 크기 규칙에 맞춘 작은 묶음으로 나눠 커밋
5 [중] 살아남은 변이 둘, 둘 다 답을 바꿈: M7(in_scope 의 coalesce 빼기 — rows_out_of_scope 269 -> 83) · M10(정렬 맨 앞 case 빼기 — 표시 47 줄이 엉뚱한 kept) -> 칸 둘
6 [중/낮] derived_pages 의 드문 대기열 맞바꿈 — SCAN_CHUNK 1000 이라 대기열이 드물면 요청 경로(count 미리보기 · dry-run)가 파생 표 전체를 1,000 행씩 걸음. withdraw 물음 2 와 같은 성질 — 같은 판 A/B 로 재고 같은 기준(전체 초 · 한 문장 5 초)으로 정한다
7 [낮] fold_withdrawal_events 가 모든 대기 사건의 payload row_ids 를 받아 옴(cell_layer.py:584) — 필요한 종류만 ·
       판정 415 좌석 discarding 을 지나는 운영 코드가 1 -> 0 — 이 일이 비웠으니 이 일에서 은퇴(약속 든 자리 전수: CODE_MAP:2125 등) ·
       FOLD_BY_VALUE_DIALECTS 를 «LATERAL 이 되나»의 대리로 씀(config.py:1672) — 그 물음의 이름을 가진 상수로 · M3(withdraw 셈) 칸
문서      «답이 같다» 표에 원장 원자를 더함(지시 5ad030347 의 셋째) · CODE_MAP:3104 · BACKFILL_GUIDE:62 «1,000 행씩» · count_withdrawable 독스트링(replay.py:667) ·
          주장 목록에 빠진 둘: 묶음 질의는 체인 훅 live 경로도 탄다(confirm_keys) · CANDIDATE_GROUP_WRAP_SQL 에 ORDER BY __c 가 더해져 한 키 길도 바뀜 — RELEASE_LOG 에
덧        pytest -m pg 는 ASSY_PG_TEST_DATABASE_URL 없이 조용히 skip — 보고의 PG 수는 «passed 수»로 적는다
```

> **[총괄 -> 구현자 B] 10-13 — 체인 decide 집계가 «옛 키»를 안 깨운다: 판단키 칸이 바뀌거나 행이 지워지면 옛 그룹의 수 · 집계 · 원장 엣지가 낡은 채 남는다 (응용 4b81fe0a6)**

```
실측(PG, 제품 자리만)  디펙 표 -> decide(키 die · kind · 단계, count · max size) -> 요약 표 -> 원장 die -has_defect_kind-> defect_kind -> 걷기
  kind 를 K1 -> K2 로 고침: (die,K2) +1 맞음 · (die,K1) 은 그대로(기대 1/3, 실제 2/5) · K1 이 다 빠져도 2/5 그대로 · 원장 die->K1 안 거둬짐 · 걷기가 «디펙 없는 kind» 에 닿음
  행 지움: 같은 모양 — 요약 · 원장 엣지 그대로
원인(코드)  chain/enrichment/mapper.py — decide 가 다시 셀 키를 배치 payload 의 «지금» data 로 짓는다. EDIT payload 에 옛 값이 없다(칸: business_key · channel · data · row_id · source_name · timestamp · transaction_id · updated_by)
           chain/ingestion_worker.py::_retract_what_those_rows_fed «DELETE never enters the rule loop» — 지운 행은 origin 셀 물러남만
           깨워진 키에 행이 없으면 count 0 을 쓰고 행을 안 지움(코드로 읽음)
도착지     ① 판단키 칸이 바뀌면 옛 키도 깨어나 다시 센다 ② 지운 행의 키도 깨어난다 ③ 다시 셌더니 그 키에 소스 행이 0 이면 파생 행을 지운다 -> 원장 엣지가 거둬진다
           decide 하나만의 일이 아니다 — 같은 성질(«이 행이 먹이던 키»를 지금 값으로만 아는 자리)을 체인 전수로 센다(조인 · 파생 · 접기 · 복사)
짓기 전     안 셋을 올린다(무엇 · 운영자 하는 일 · 좋은 점 · 위험 · 크기). 생각할 축: 고침 사건이 «옛 값»을 싣기(crud 가 이미 감사에 old/new 를 씀 — 그 자리를 넓힘) ·
           소스 행 -> 키 기억 · 지움 사건을 규칙 고리로. 소급(이미 낡은 요약을 바로잡기)은 어떻게 — 한 번 다시 세기 명령과 RUN.md 줄
게이트     응용 판 그대로(4b81fe0a6 의 칸 넷 + 지움) · 같은 성질 자리마다 칸 · 진짜 프로세스 한 판(체인 워커로)
순서       큐 1 착지 -> 원장 행 색인 키 -> 이것 -> LLM 묶음 -> 큐 2
```

> **[총괄 -> 구현자 B] 10-13 — 원장 선언 간소화: read 은퇴 · 행 단위 맵핑만 · «역할: 컬럼» 짧은 꼴 · 옛 선언 변환기 (소유자 「지금 원장 선언 너무 어려워 더 간소화 할수 없을까?」 · 「read 관련 다 빼고 소스 맵핑만」 · 「엣지 : 주어 키:컬럼(or 상수) ... 이거만 퀵하게 선언하고 싶어」 · 「그냥 컬럼 맵핑 느낌으로 하자」 · 「간소화하면서 옛선언 변환 코드도 만들어줘」 · 「read 부분은 뭐 잡다한 변환 다 없고 그냥 행단위 맵핑으로 해」 · 「그러면 read 선언할거 없잖아」)**

```
도착지 두 줄  「운영에서는 원장 선언 sources 에 표 이름을 적고, 엣지마다 «역할: 컬럼» 을 적으면 됩니다.
              옛 선언은 변환 명령 한 번으로 이 꼴이 됩니다」
짧은 꼴(예 — 견본 dt_job 93 줄이 이렇게)
  "dt_job": {
    "table": "dt_job_rollup",
    "edges": {
      "has_netdie": {"subject": "dtjob(dt_job)", "value": "netdie_count", "occurred_at": "event_time"},
      "register":   {"subject": "dtjob(dt_job)", "occurred_at": "event_time"}
    },
    "attributes": {"dtjob": {"dt_eqp": "dt_eqp"}}
  }
  엣지 이름 = 어휘 술어(맨이름) · 역할 이름은 오늘 그대로(subject · target · value · occurred_at · 수식어)
  값 글  "칸" = 컬럼 · "'K1'" = 상수 · "타입(키)" = 같은 이름 컬럼 · "타입(키:칸)" · "타입(키:'상수')" · 키 여럿은 쉼표
  같은 엣지가 한 소스에 둘 이상이면 값이 목록 · 엣지의 행 조건(when)은 행 단위라 칸 하나로 남는다(옛 것을 버리면 원자가 바뀐다)
read     은퇴 — 소스는 «행 하나 -> 원자들» 만(소유자). unit · identity · order_by · cursor · group_by · exclude_when · registration_probe 를 사람이 적지 않는다
         identity · order_by · cursor = 표의 가장 짧은 유일 키(지금 기본값 자리 with_read_defaults 그대로) · 사건 시각 = 엣지의 occurred_at
map      declarative-role 하나 — implementation_id 를 적지 않는다
읽는 자리 🔴 하나 — upgrade_setup 을 v6 -> v7 로 넓힌다(v5 -> v6 선례: 로더는 메모리에서, scripts/migrate_ledger_config_to_v7.py 는 파일로, 같은 함수)
         짧은 꼴 -> 긴 꼴 펼치기도 한 함수. 펼친 뒤는 오늘의 검증 · 컴파일 · 번역기 그대로
못 옮김   행 단위로 못 옮기는 옛 소스(group_by · 사용자 맵퍼 · exclude_when · 기본과 다른 순서 등 — 전수는 네가 센다)는 지어내 옮기지 않는다
         prepare_retired 선례대로 이름 대어 거절 + 다음 행동(«체인이 행 단위 표를 쓰게 옮긴다»)
         변환 명령은 dry-run 이 기본 · 못 옮기는 소스가 하나라도 있으면 파일을 안 쓴다(데이터 가드)
옛 값     변환이 원자를 바꾸면 그건 소급이다 — 옮겨지는 소스는 «펼친 번들 == 오늘 번들»(정규화 뒤 해시까지), 다시 돌 것 0
         어긋나는 칸(매핑 이름이 원자 신원에 드나 · 시간대 · 형식처럼 짧은 글이 못 싣는 칸)은 짓기 «전»에 수와 함께 올린다 — 시간대는 «표 선언의 칸 성질»이 후보
자리 전수 선언 문서를 읽거나 쓰는 자리 전부 — 로더 · 검증 · 작성 엔진(config_authoring) · 탐색기 · 스켈레톤(ledger_skeleton.json) · public_bundle_schema ·
         견본 · 이주 스크립트 · 시험 픽스처 · 가이드(ONTOLOGY_LEDGER_SETUP). 선언 창은 스켈레톤이 그린다 — 짧은 꼴로 바꾼 뒤 창이 따라오는지 «열어서»(크롬 한 줄)
         창 쪽이 크게 바뀌면 그 부분만 안으로 올린다
행 붙이기 구현자 A 의 행 붙이기 소스 칸(«이 표의 행을 <타입> 노드에 붙인다»)도 이 «타입(키:칸)» 글을 쓴다 — 바인딩 문법 둘 금지. 이것이 먼저 앉는다
게이트    견본 · 추적 픽스처 전부: v6 -> v7 -> 펼침 == 오늘 번들(해시) · 같은 판 PG 에서 원장 원자 차이 0 · 못 옮김 거절 문장 · dry-run 출력 ·
         v6 파일 그대로 둔 로더가 같은 번들 + 로그 한 줄 · 진짜 프로세스 한 판(런처 + 체인 워커, 짧은 꼴 견본으로) · 선언 창 열기
문서      RUN.md(변환 명령 · 답의 뜻 · 못 옮김이 나오면 할 일) · RELEASE_LOG · 가이드. CLAUDE.md «원장 선언은 국소적»의 «group_by 로 묶인 행들» 줄은 착지 때 총괄이 고친다
크기      안 쟀다
순서      큐 1 착지 -> 원장 행 색인 키 -> 이것 -> decide 옛 키 -> LLM 묶음 -> 큐 2
```

> **[총괄 -> 구현자 B] 10-13 — 원장 선언 짧은 꼴(b9d33d6f6) 모양을 소유자 안으로 바꾼다: "타입(키:칸)" 글 은퇴 · 문장 목록 + 노드 객체 (소유자 「{attr.. : {node : {attr1 : col, ...}, ...}, sentences : [sentence : predicate : edge, subject : {node : dt_job, keys : {dt_jobid : dtjobid} ] } 이게 낫지 않나?」)**

```
모양(견본 dt_job)
  "dt_job": {
    "table": "dt_job_rollup",
    "attributes": {"dtjob": {"dt_eqp": "dt_eqp"}},
    "sentences": [
      {"sentence": "counted", "predicate": "has_netdie",
       "subject": {"node": "dtjob", "keys": {"dt_job": "dt_job"}},
       "value": "netdie_count", "occurred_at": "event_time"},
      {"sentence": "register", "predicate": "register",
       "subject": {"node": "dtjob", "keys": {"dt_job": "dt_job"}},
       "occurred_at": "event_time"}
    ]
  }
값       글 = 컬럼 · {"const": "K1"} = 상수(키 안에서도 같음) · 노드 = {"node": 타입, "keys": {키: 값}} (subject · target 같은 모양)
문장     sentence = 오늘 매핑 이름 그대로(원자 신원이 안 바뀐다 — 앞 지시의 «매핑 이름» 위험은 이 모양에서 사라짐) · predicate = 어휘 술어 · 그 밖 칸 = 오늘의 역할(value · occurred_at · 수식어) · when 칸 하나
은퇴     앞 지시의 "타입(키)" · "타입(키:칸)" · "'상수'" 글과 edges 사전 — 작은 언어를 파싱하지 않는다
그대로   앞 지시(b9d33d6f6)의 나머지 전부 — read · map 은퇴, 행 단위만, upgrade_setup v6 -> v7 한 자리, 못 옮김 이름 대어 거절, dry-run, 펼친 번들 == 오늘 번들, 자리 전수, 게이트, 순서
행 붙이기 A 의 붙이기 칸도 이 노드 객체 {"node", "keys"} 를 쓴다
```

> **[총괄 -> 구현자 B] 10-13 — 짧은 꼴: 소유자가 말하지 않은 기능은 «그대로» 가져온다 (소유자 「when 이런 등등 내가 언급 안한 기능은 그대로 가져와」)**

```
규칙     은퇴는 소유자가 말한 것뿐 — read 의 묶기 · 순서 · 커서 · 단위(group_by · order_by · cursor · identity · unit) · map 의 implementation_id(사용자 맵퍼).
         그 밖에 오늘 선언이 하는 일은 «같은 이름 · 같은 뜻»으로 짧은 꼴에 남는다 — 못 옮김 거절은 위 은퇴 칸에 걸린 소스만
예       문장의 when · 수식어 · 소스 status(retired) · attributes · 엔티티 · 어휘 절 전부 · virtual_joins 같은 선택 절 · 바인딩의 timezone · format 같은 덧칸
         덧칸이 붙는 값은 객체로 적는다 — {"column": "event_time", "timezone": "Asia/Seoul"} (글 = 컬럼 · {"const"} = 상수는 그대로, 객체는 오늘 바인딩 칸 이름)
read 안의 행 제외(exclude_when)는 «행 하나»를 거르는 일이라 소스 칸 exclude_when 으로 가져온다(총괄 판단 — 소유자께 한 줄로 알림)
게이트   전수 표 하나: 오늘 문법의 칸마다(public_bundle_schema · _validate_* 가 받는 칸 전부, AST 로 셈) «짧은 꼴의 어느 칸 | 은퇴(소유자 문장)» — 빈 칸 0
```

> **[총괄 -> 구현자 B] 10-13 — 원장 선언 짧은 꼴: 넣고 뺄 칸 확정(소유자 「좀 나랑 뭐넣고 뭐뺄지 정하고 하자」 -> 「추천대로」 · 「virtual join 도 빼」). 보류 풀림 — 이 절이 b9d33d6f6 · 640631bf0 · 571685e7f 의 칸 목록을 대신한다**

```
넣음      table · attributes{타입: {속성: 값}} · sentences[{sentence(오늘 매핑 이름) · predicate · subject · target · value · occurred_at · 그 밖 수식어 · when}]
          값: 글 = 컬럼 · {"const": ...} = 상수 · 노드 = {"node": 타입, "keys": {키: 값}}
          소스 끄기 "status": "retired"
          시각 덧칸 — 시간대 · 글 모양은 그 값만 객체로: "occurred_at": {"column": "event_time", "timezone": "Asia/Seoul", "format": ...}
          행마다 노드 타입을 컬럼에서: "node": {"column": "type_col"} (오늘 entity_type {kind: column} 그대로)
          when 에 «빈 칸» 조건 하나 더함(오늘 exclude_when 의 blank 를 받는 자리)
뺌        read 전부 — 묶기 · 순서 · 커서 · 단위 · identity · 사건 시각 없는 소스의 기준 시각(저장 시각 자동) · exclude_when
          map 의 사용자 맵퍼(implementation_id) · virtual_joins 절 · 노드 칸 «안»의 attributes(소스 attributes 하나로)
그대로    vocabulary · entities (이번 범위 밖)
옛 것 옮기기(변환기 = upgrade_setup v6 -> v7 한 자리)
          exclude_when -> 그 소스 문장마다 when 에 «아님» 조건으로. when 으로 못 적는 모양(예: 여러 칸 묶은 제외 = «또는»)은 이름 대어 거절
          노드 칸 안 attributes -> 소스 attributes. 한 행에 같은 타입 노드가 둘이라 어느 것인지 못 가리면 이름 대어 거절
          virtual_joins — 비었으면 버림, 규칙이 있으면 이름 대어 거절 + 다음 행동(«체인 조인이 표에 쓰게»). 은퇴 약속 든 자리 전수(transfer_explorer 견본 · FEATURE_CHECKLIST · config_explorer · 스켈레톤 · README)
          group_by · 사용자 맵퍼 · 기본과 다른 순서 -> 이름 대어 거절(앞 지시 그대로)
          못 옮김이 하나라도 있으면 파일을 안 쓴다 · dry-run 기본 · 옮겨지는 소스는 펼친 번들 == 오늘 번들(해시) — 다시 돌 것 0
게이트    전수 표: 오늘 문법의 칸마다(_validate_* · public_bundle_schema 가 받는 칸, AST 로 셈) «짧은 꼴의 어느 칸 | 뺌(위 줄)» — 빈 칸 0
          나머지 게이트 · 자리 전수 · 문서는 b9d33d6f6 그대로
순서      큐 1 착지 -> 원장 행 색인 키 -> 이것 -> decide 옛 키 -> LLM 묶음 -> 큐 2
```

> **[총괄 -> 구현자 B] 10-13 — 원장 따라가기가 느리고, 체인 «지움»이 그 줄 뒤에 묶여 있다 (소유자 「지금 체인 결과가 안써지는데」 · 「원장 번역속도는 왤케 느려」 · 「5초에 10개인데」, 응용 재현 a43734da3 최종). 순서를 당긴다**

```
실측(응용, origin/main 08fe05c0c 런처 4 프로세스)  추가 · 고침은 5~10 s 안에 써짐 · 조인 원천 행 지움은 42~46 s 뒤에야 거둬짐 · decide 지움은 안 씀(a84e12f31)
원인 1   server/pacing.json jobs.chain_followup = "trickle" — 따라가기 루프(ingestion_worker.run_ledger_followup)가 한 바퀴에 «사건 1 개» 처리하고 3 s 쉼(분당 약 20 사건)
         사건 하나 = 체인 배치 하나. 소유자 «5초에 10개» = 사건 하나의 행 수 ÷ (처리 시간 + 3 s)
원인 2   지운 행이 먹인 칸 거두기(_retract_what_those_rows_fed)가 체인 규칙 고리가 아니라 따라가기 배치(_drain_ledger_followup_sync) 안에 있다
         -> 지움이 원장 줄의 속도에 묶이고, 원장 선언이 컴파일 안 되면([LedgerFollowUp] stopped) 체인 지움도 영영 안 거둔다(응용 2 판 실측)
원인 3   decide 는 옛 키 · 지운 행 키를 안 깨운다(a84e12f31 — 그대로 이 판에 합친다)
도착지   ① 체인 결과(추가 · 고침 · 지움)는 원장 따라가기와 «무관하게» 체인 고리 안에서 끝난다 — 원장이 서도 체인 지움은 거둬진다
         ② 따라가기는 사건을 «여럿 묶어 한 번에» 번역하고, 속도는 «사건 수»가 아니라 «몇 초 일하고 쉬기»(page_seconds 규칙과 같은 한 자리)로 — 사건 크기와 무관한 처리량
         ③ 행 하나 번역 비용을 운영 규격 판에서 잰다(«lap: 1 item(s) in X s» 의 X 가 무엇으로 이루어지나 — 질의 · 파이썬 · 쓰기 몫) — IO 목표 1.3 s/1k
         ④ decide 옛 키 · 지운 행 키(a84e12f31 도착지 ①②③)
기본 속도 소유자 「fast」 — 총괄이 착지함 e914303b7(pacing.json chain_followup = fast · 시험 · RUN.md). ② 는 그 위에서 «사건 묶어 번역 · 시간 예산»으로
짓기 전   ① · ② · ④ 를 한 판으로 안 셋(무엇 · 운영자 하는 일 · 좋은 점 · 위험 · 크기) — 거두기를 어느 고리로 옮기나 · 묶음 번역의 원자 순서/시각 계약이 그대로인가
덧(작게)  표 잠금 기다림에 끝이 없다(응용 ⑤: 잡은 쪽이 안 풀면 그 표 그룹은 영영 섬) — 큐 줄에 «잡은 pid · 얼마나» 가 이미 보이는지 확인하고, RUN.md 에 «어느 표에서 서 있나 · 잡은 pid · 끄는 법» 한 절
          빈 값 판정 두 정본이 NaN 에서 갈림 — crud.is_blank_value(NaN 아님) · crud.is_blank_key_part(NaN 빈 값) -> 하나로(호출자 전수, 답이 바뀌는 자리 표)
          죽은 runner 의 chain_replay running 행 cancel -> cancel_requested 로 약 4 분 관문 그대로(응용 ④, 다른 호스트 runner 갈래) — RUN.md 문장을 동작대로
게이트    응용 판 그대로(추가 · 고침 · 조인 지움 · decide 지움 · 원장 stopped 판에서 지움) + 따라가기 처리량 같은 판 A/B(사건 크기 1 · 10 · 1000)
순서      큐 1 착지(확인 검수 중) -> 이것 -> 원장 행 색인 키 -> 짧은 꼴 -> LLM 묶음 -> 큐 2
```

> **[총괄 -> 구현자 B] 10-13 🔴 최우선(796f04605 ①④ 보다 앞) — 원장 번역기 행당 비용: Re-translate 가 혼자 돌아도 느리다 (소유자 「원장 재번역이랑 같이 돌리는중 근데 원장 재번역은 혼자 돌려도 느렸음」 · 「psql server가 cpu 점유율 70퍼」)**

```
아는 것   네 측정(hold 판, 단순 선언): EDIT · CREATE 모두 행당 약 6 ms, 그 대부분이 프레임 짓기(event_frames · dry_run_event_frame), DB 드라이버 0.01 s/1,000 행
         IO 목표 1.3 s/1k 의 약 5 배 — 400만 행 다시 번역이면 박스 수로도 약 7 시간. 운영 선언(roleframe · group_by · 문장 여럿)은 안 잼
         네가 «이번 판 밖»으로 둔 것을 판 안으로 들인다 — 소유자가 직접 말한 아픔이 이것이다
먼저 재기  운영 선언 판(응용의 박스 베낀 판 선언 그대로, 읽기만 — 체인 워커는 레인 사이 한 번에 하나) + hold 판, Re-translate 를 제품 문(화면 버튼이 부르는 그 라우트)으로
         ① 행당 파이썬 몫을 함수 단위 표로(cProfile 누적 상위 — 프레임 짓기 안에서 무엇이 행마다 도나: 선언 해석 · 칸 정규화 · 시각 파싱 · 원자 객체 · 해시)
         ② 같은 실행 동안 PG 몫 — 그 실행이 보내는 문장 전부 × EXPLAIN (ANALYZE, BUFFERS) × 쪽마다 횟수 (소유자의 CPU 70% 가 이 실행의 문장인지 갈라야 한다)
         ③ 1만 · 10만 · 100만 기울기(쪽 크기 규칙 그대로)
그다음    안 셋(무엇 · 운영자 하는 일 · 좋은 점 · 위험 · 크기). 생각할 축: 행마다 다시 하는 일 중 «선언마다 한 번»으로 올릴 것 · 열 단위(쪽 전체 한 번)로 바꿀 것 ·
         원자 신원 · 시각 · 순서 계약은 그대로(답 바이트 같음이 게이트)
게이트    같은 판 전후: 행당 ms(두 판) · 답(원자 집합 · 시각 · claim id) 바이트 같음 · PG 문장 수 · 진짜 프로세스로 Re-translate 한 판
순서      이것 -> 796f04605 ①④(지움을 체인 고리로 · decide 옛 키) -> ②(사건 묶기) -> 원장 행 색인 키 -> 짧은 꼴 -> LLM 묶음 -> 큐 2
```

> **[총괄 -> 구현자 B] 10-13 🔴🔴 급 — 번역기 행당 비용(109c09396) 덧: 소유자가 «지금» 소급으로 자료를 만들어야 한다 (소유자 「원장 번역도 너무 느려 지금 소급해서 자료만들어야하는데」)**

```
뜻        측정 → 안 셋 → 짓기 순서는 그대로, 다만 «가장 빨리 효과가 나는 것»을 먼저 착지시키고 나머지는 이어서
안 셋에    반드시 한 칸: 프로세스 나눠 돌리기 — 네 측정이 «99 % 파이썬 · DB 0.01 s/1,000 행»이니 행 범위(키 순서 쪽)를 프로세스 N 개에 나누면 거의 N 배가 «번역기 출력 계약을 안 건드리고» 나온다
          새 기제 금지 — 이미 있는 문을 넓힌다: runtime/process_pool(걷기 풀, in_pool · 세대 · 시한) 또는 소급 자식 프로세스(assy_retroactive) 중 어느 것이 맞나를 안에 적는다
          지킬 것: 원자 · 시각 · claim id 바이트 같음 · 소스 커서(워터마크)가 범위마다 맞게 · 진행 줄(5 초 규칙) · 멈춤(stop_line)이 프로세스 전부에 닿음 · 운영 CPU 코어 수를 넘지 않는 기본값(설정 한 칸)
          그리고 행당 비용 자체를 줄이는 안(선언마다 한 번으로 올리기 · 쪽 단위 계산)과 둘을 함께 쓰는 안
게이트    같은 판 전후: 100만 행 Re-translate 전체 초 · 행당 ms · 답 바이트 같음 · 진짜 프로세스로 한 판
보고      안 셋을 «오늘 착지할 수 있는 것»과 «그다음»으로 나눠서
```

> **[총괄 -> 구현자 B] 10-13 🔴🔴 지금 바로(하던 측정보다 앞) — 원장 다시 번역의 실시간 디버그 로그: 무엇이 돌고 무엇을 기다리나, 내부 단계마다 (소유자 「재번역 디버그 로그 다띄워 실시간으로 뭐가돌고 뭘 기다리는지 내부 진행 코드마다 로그 다 찍어서 푸시」)**

```
도착지   운영자가 retroactive 로그(그 실행이 쓰는 로그 파일 · 화면 진행 줄) 하나만 보면 «지금 어느 단계에서 몇 초째 · DB 가 무엇을 기다리나 · 누가 막나»가 5 초마다 보인다
단계 줄   한 쪽(page)의 내부 단계마다 시작 · 끝 · 초 · 행 수 — 네 cProfile 의 길 그대로: 쪽 읽기 · rescope · _preview_frame/preview_cursor_batch · event_frames · dry_run_event_frame ·
         거두기(이 행이 낳은 원자 찾기 — 무엇으로 찾나: row_ref 색인 / 그 밖) · execute_scoped_batch · 원장 쓰기 · 커밋 · 워터마크. 행마다 줄은 안 찍는다(쪽마다 · 단계마다)
박동 줄   그 실행 옆 감시 스레드 하나가 5 초마다: 지금 단계 · 그 단계 몇 초째 · 쪽 안 행 진행 · 그 실행의 DB 백엔드가 기다리는 것(db_waits.backend_waits / wait_sentence — 체인 · 워처가 이미 쓰는 그 함수)
         + 지금 문장 앞 120 자 + pg_blocking_pids 의 이름(application_name). 새 기제 금지 — c6bc9bcc0 의 «느린 쪽 안의 진행 줄»과 db_waits 를 넓힌다
느린 문장  한 문장이 N 초(설정 한 칸, 기본 2 s)를 넘으면 그 문장 글과 EXPLAIN 없이 초 · 읽은 행(가능하면)을 한 줄
스위치    ingestion_settings 칸 하나(retroactive_debug, 기본 켬 — 소유자가 «다 띄워»), 끄면 단계 줄만 꺼지고 박동은 남김. 재기동 없이 다음 쪽부터
침묵      계측은 자기만 침묵 — 감시 스레드가 터지면 «무엇이 조용해졌는지» 한 줄 찍고 번역은 계속(CLAUDE.md 계측 상설)
게이트    박스 hold 판 한 판(진짜 프로세스 · 화면 Re-translate 버튼이 부르는 그 문)으로 로그 묶음을 보고에 그대로 · 잠금을 일부러 잡아 박동 줄이 «waiting for … held by <pid> (assy_…)» 를 말하는 칸 ·
         감시 스레드를 일부러 터뜨려 번역이 끝까지 가는 칸 · 번역 답 바이트 같음
문서      RUN.md 한 절: 로그 파일 자리 · 줄 모양 · 답의 뜻(단계별로 «이 단계가 길면 무엇») · 끄는 칸. 착지는 main 으로 바로(소유자 「푸시」)
```

> **[총괄 -> 구현자 B] 10-13 — 큐 1 고침 확인 검수(39c7115ed): GO-WITH-FIXES — 1 · 3 · 4 · 5 · 7 확인(변이 14 중 12 잡힘), live 체인 결과 쓰기를 멈추는 새 갈래 0, withdraw 기점 대 HEAD 14/14 같음. 착지 전 셋 (디버그 로그 d9be013cb 뒤)**

```
6 [중] derived_pages 기점 읽기 — 한 문장 길이가 대기열의 «위치»(대기 행 사이 틈 길이)에 비례. 네 판 다섯은 밀도만 바꿈
       4M 판 · 맨 앞 50 행만 대기: 기점 전체 14.66/7.17 s · 가장 긴 문장 8.68 s(5 초 규칙 어김) · 1,000 행 쪽 하나가 Parallel Seq Scan 3 × 1,333,317 행
       걸리는 자리: 적용 스윕 analysis.py:772 · dry-run GET main.py:6841 · count 미리보기 retroactive.py:386(요청 경로)
       -> 총괄 결정: 쪽은 «row_id 범위»로(같은 가지 53d9b65c8 표기 접기의 모양 — 한 문장이 읽는 범위가 정해짐). 기점의 «다음 N 대기 행» 모양은 은퇴. 게이트: 4M 앞 50 행 · 고른 1/1000 · 꼬리 몰림 세 판 모두 한 문장 < 5 s
2 [중] VALUES 칸 CAST 가 잰 경우(파생 String · 참조 정수 · 글 키)를 못 고침 · 운영 두 자리(collect_rows · derived_pages)는 DB 형 값을 넘겨 CAST 가 바꾸는 운영 값 0 ·
       새 칸은 운영에 안 나오는 값(Float 칸에 "3")이라 공허 · round(:x, 1) 뷰는 CAST 때문에 새로 묶음 실패
       -> 총괄 결정: CAST 를 거둔다. 남은 몫(형이 다른 뷰는 묶음 실패 -> 키마다, 답은 같음)은 묶음 실패 줄이 이미 말한다 — 독스트링 · 커밋의 «compares as it does alone» 을 동작대로
3 [중/낮] dry · 미리보기가 지울 행을 안 읽는다는 칸이 인자 모양만 잼 — _fold_read 가 losers 를 무시하는 변이가 31 passed 로 삶 -> dry · 미리보기에서 part 1 행이 0 이라는 칸(PG)
문서      CODE_MAP :2114 · :2119 · :2127 · :2245(in_savepoint · _BIND_PARAM_RE 줄) · enrichment_rules.md:62 뷰 탈락 사유에 «write CAST(:x AS type)» · BACKFILL_GUIDE:62 «5 초»(기본 3 s, 5 s 는 상한) ·
          cell_layer.py:331 «2-8x» -> 잰 수(3.0× · 4.4×, 최대 6.3×) · analysis.py:212 «every board» 거짓 · RELEASE_LOG 항목과 RUN.md 절이 아직 없음 — 착지 커밋에
RUN.md    배포 뒤 볼 줄: «:x::type» 철자를 쓰는 운영 뷰는 적재 때 이름 대어 떨어진다 — 그 줄이 나오면 CAST(:x AS type) 로 고침, 안 고치면 그 자동확정이 멈춤
```

> **[총괄 -> 구현자 B] 10-13 — 원장 일을 체인 워커에서 떼어 «원장 프로세스» 하나로 (소유자 「근데 원장 프로세스가 굳이 체인 워커일 필요가 있어」 -> 안 ㄱ 「원장 프로세스 ㄱ」)**

```
도착지   런처(감독)가 띄우는 데몬 목록에 원장 프로세스 하나 — 원장 따라가기(번역) · 원장 센서스 · 원장 인덱스 짓기(17d8ea0d6)가 거기서 돈다. 체인 워커는 체인만
         원장이 서거나 느려도 체인 묶음 처리는 그대로 · 원장만 재기동 가능 · 원장이 자기 코어를 씀
있는 문   새 기제 금지 — runtime/process_supervisor 의 데몬 목록(워처 · 체인 · 수집기와 같은 모양) · 원장이 사건을 읽는 자리는 지금 그대로(database_outbox 의 ledger_state)
         연결 이름 assy_ledger(database.connection_name 한 자리) · 로그 파일 하나(ledger.log, RUNTIME_MAP 의 ④ ⑤ 줄을 옮김)
지킬 것   사건 순서(원장이 체인의 쓰기 뒤를 따름 — 지금의 계약 그대로) · 설정 다시 읽기가 두 프로세스에서 같은 답(config_watcher) · 멈춤(stop_line)이 원장에도 닿음 ·
         통합 모드(uvicorn 단독 — 박스 · 개발)에서는 지금처럼 한 프로세스 안에서도 돈다 · 원장 프로세스가 죽으면 감독이 살림(백오프 그대로)
같이 볼 것 번역기 행당 비용(109c09396 · fd550df13 «행 범위를 프로세스 N 개로»)과 같은 자리 — 원장 프로세스가 그 N 개의 주인이 되게 한 판으로 설계. 796f04605 ①(체인 지움은 체인 고리 안)과 겹치는 칸 정리
짓기 전   안 셋(무엇 · 운영자 하는 일 · 좋은 점 · 위험 · 크기) — 특히 «체인 워커에서 원장 일이 빠질 때 체인 쪽에 남는 원장 의존»(지금 체인 고리가 원장을 부르는 자리) 전수
게이트    진짜 런처 판: 원장 프로세스를 죽여도 체인 결과(추가 · 고침 · 지움)가 5~10 s 안에 써짐 · 원장 프로세스가 살아나면 밀린 사건을 순서대로 · 원자 바이트 같음 ·
          pg_stat_activity 에 assy_ledger · RUN.md(새 프로세스 · 로그 자리 · 끄는 법 · 재기동 순서)
순서      지금 B 순서의 «번역기 행당 비용»(3) 자리에 합친다 — 그 앞의 ref 인덱스(착지) · 큐 1 고침(ff4eb2cf0)은 그대로
```

> **[총괄 -> 구현자 B] 10-13 — 착지 뒤 검수(85d7e1de1 디버그 로그 · 17d8ea0d6 원장 ref 인덱스 스스로 짓기): GO-WITH-FIXES — 체인 묶음 쓰기 안 막힘(300만 파티션 짓는 9.3 s 동안 INSERT 최대 16 ms) · 데이터 안 바뀜 · 끄기 둘 실제로 꺼짐. 고칠 것 (조각 N 개 ㄱ 착지 «전»에 — 둘 다 같은 원장 짓기 · 소급 자리) (probe 총괄 scratchpad qab2_*)**

```
1 [중] 짓는 쪽 둘이 겹치면 교착 — schema.py:692-699 가 남이 «지금 짓는 중»인 무효 인덱스를 «멈춘 짓기의 잔해»로 보고 DROP INDEX CONCURRENTLY
       실측 300만: 둘째를 1.5 s 뒤 시작 -> 첫째 DeadlockDetected · 둘째 처음부터 21.3 s(혼자 9.3 s). 교착에 체인 워커 쪽이 지면 남은 파티션은 다음 기동까지 그대로(파티션 하나 오류가 짓기 전체를 세움)
       경로: 손 명령 + 체인 워커 재기동 동시 · 짓는 중 체인 워커 강제 종료(DB 쪽 고아 짓기) + 다음 기동
       -> 지금 짓는 중인 인덱스는 안 지움(pg_stat_progress_create_index 또는 그 인덱스를 쥔 백엔드가 살아 있나 — 판정 한 함수) · 파티션 하나 실패가 나머지를 안 세움
       RUN.md 옛 절은 총괄이 내림(이 커밋 옆에서)
2 [중] 짓기가 DB 전체의 오래된 트랜잭션을 상한 없이 기다리고, 그동안 다시 읽기 때의 인덱스 일(조인 유일 키 · 조회 인덱스)이 그 뒤에 줄 섬(ingestion_worker.py:2797 · 4979)
       그 사이 조인 승인 줄이 «유일 인덱스 없음 -> REFUSED»(chain/synthesis.py:399-407). 기존 두 길과 다름 — 유일 키 길은 DDL_LOCK_TIMEOUT 에서 포기 · 다음 기동에 다시, 모델 인덱스 길은 문장 상한 0
       -> 원장 짓기를 다른 인덱스 일과 «다른 줄»로(원장 짓기가 서도 조인 키는 지어짐) · 기다림에 상한(같은 DDL_LOCK_TIMEOUT 자리) · 기다리는 동안 «waiting for transactions older than it: pid … (이름)» 줄 ·
          /admin/indexes 원장 줄에 building 상태(지금은 짓는 동안 missing 만)
3 [중-낮] 쪽마다 실행 기록 UPDATE + COMMIT 이 단계마다(14~15 번) — retroactive.py:2675 · 2683-2697, 단계 줄 기본 켬이라 기본으로. 시험은 run_id 없이 돌아 이 갱신을 한 번도 안 부름
       -> 실행 기록 갱신은 쪽마다 한 번(진행 줄 5 초 규칙은 그대로) · run_id 있는 칸 · RELEASE_LOG 에 비용
4 [낮] 끄기 시험이 «쪽마다 EXPLAIN 안 나감»을 단언 안 함 — 변이 «늘 켬»이 3 passed 로 삶 -> 문장 수 칸
5 [낮] 쪽 열쇠 인덱스 «한 번만 묻기»가 인덱스 없을 때 깨짐(backfill.py:926 빈 문자열로 남아 쪽마다 다시 물음)
6 [낮-중] 뷰를 읽는 원장 소스에 «each page sorts the table · indexes 를 적으라»가 끌 수 없이 거짓으로 찍힘(backfill.py:2438 · 845-866 — 같은 파일 883-886 은 뷰를 따로 다룸) -> 뷰면 그 판정을 안 함(또는 뷰라고 말함)
7 [낮] 체인 리플레이의 박동이 assy_chain 연결 전부(체인 묶음 · 따라가기 · 인덱스 짓기)를 그 실행의 것처럼 «[chain_replay] slow statement» 로 찍음(retroactive.py:2515 · 3476) -> 그 실행의 백엔드 pid 로만
8 [낮] 게이트가 공용 DB 의 긴 트랜잭션 뒤에서 섬(마무리가 모든 인덱스를 CONCURRENTLY 로 다시 지음, 이번 23 분) -> 그 게이트는 자기 스키마 인덱스만
문서      RUN.md:24 «재기동 없음(실행마다 새 프로세스)»은 체인 리플레이엔 틀림(체인 워커 안) · RELEASE_LOG 첫 항목에 3 의 비용 · 둘째 항목에 2 · CODE_MAP:961 /admin/indexes 원장 줄 · main.py:4661 독스트링(building)
런타임    운영 체인 워커 연결의 statement_timeout 이 0 이 아니면 큰 파티션 짓기가 매번 끊겨 무효 잔해 -> 기동마다 처음부터 — 짓기 연결은 모델 인덱스 길처럼 상한을 0 으로 푸는지 확인
```

> **[총괄 -> 구현자 B] 10-13 — 조각 N 개(9351a3580) 착지 뒤 검수: GO-WITH-FIXES — 경계 일부러 건 판에서 1 프로세스 대 4 조각 원자 · 행 색인 같음, × · 고아 안전. 고칠 것 (ㄴ 보다 앞, 작게 한 커밋) (probe 총괄 scratchpad qab3_*.py)**

```
1 [중] 쪽 열쇠 인덱스 판정(backfill.py:2489 _page_key_index)이 hash · gin · 부분 인덱스도 «있음» — 그 표에서 ORDER BY k 는 Seq Scan + Sort 인데 4 조각, 결함 줄도 안 남
       replay._key_index 와 같은 물음의 둘째 답(문 가르기) -> 판정 한 함수: btree · 부분 조건 없음 · 첫 칸이 쪽 열쇠일 때만 «있음», 두 자리가 부름
2 [중] 원장 ref 인덱스 짓기의 20 초 lock_timeout(models.py:2007)이 «다 짓고 마지막 스냅숏 기다림에서 포기 -> INVALID -> 다음 기동 · Reload 에 지우고 다시» 고리(실측 8.3 · 10.3 s 짓고 버림)
       버린 인덱스는 indisready=true 라 모든 원장 쓰기가 갱신(10 만 행에 10.5 -> 13.7 MB)
       -> 총괄 결정: 원장 줄에서는 lock_timeout 을 뺀다(원장 짓기가 이미 다른 줄이라 조인 키가 안 밀림 — 상한을 둔 이유가 사라짐). «waiting for transactions older than it: pid N (이름)» 줄과 building 상태만
3 [중] «원자가 같다» 시험이 원장을 안 비우고 1 프로세스 판 위에서 조각 판을 돌림 — 조각이 쓰기를 건너뛰어도 8 passed -> 판 사이 원장 비우기 + 그 변이 빨강
4 [중] RUN.md 되돌리기 줄이 --grep 이라 지금은 보고 커밋(37c9aa885)만 잡음 -> 해시를 적음(9351a3580 · 함께 되돌릴 것)
5 [중] slice_bounds 뒤에 쪽 열쇠가 NULL 인 행이 들어오면 어느 조각에도 안 들어가 조용히 빠짐(한 프로세스면 거절로 드러남) -> 그 행을 세어 실행 끝에 이름 대거나 마지막 조각이 받음
6 [중/낮] 원장 짓기 시험이 다른 시험 뒤 한 프로세스에서 빨강(공유 스크래치에 남은 2026_10 파티션) -> 시험마다 자기 스키마 · 자기 파티션
낮    조각 수 설정에 상한 없음(64 = 프로세스 64) · 0 · −2 · '8' 이 말없이 기본값 -> 1~(코어 수) 로 거르고 한 줄 · ledger_translate_slices 를 ingestion_settings.json.sample 에 ·
      빈 조각(numeric 1.0 · 1.00 컷 중복을 글자로 견줌) · 1000 만 행 slice_bounds 의 count · OFFSET 동안 줄 없음 · RUN.md 수(9.9→7.4)와 보고(9.1→6.1) 맞춤 ·
      강제 종료 뒤 조각이 지금 쪽을 커밋하고서야 멈춤(잠금 기다리는 조각은 상한 없음) — 문서에 동작대로 · _ledger_setup N+1 번
문서      RELEASE_LOG «인덱스 없으면 한 조각» 을 1 의 판정대로 · RUN.md «실행이 죽으면 조각도 멈춘다» 는 잰 판(qab3_orphan_driver)을 인용
```

> **[lead -> implementer B] 10-13 - queue 4 (server expression calculator, 0b7d84462 B) gets a migration of the existing declarations (owner «다만 수식 바꾸고 기존 수식 마이그레이션 할 수 있게»)**

```
what      when chain decide aggregations become expressions, the existing declarations move too - not only read in memory:
          one reading function (aggregation_record) turns the old shapes ("count" · {"fn", "column"} · the lowercase names) into the expression text, and a script
          scripts/migrate_decide_aggregations_to_expressions.py calls that same function to rewrite chain_rules.json (or wherever the decide rules live) - dry-run by default,
          prints «rule · name · old -> new» per aggregation, refuses by name what has no expression form (and writes nothing then), keeps a backup beside the file
gate      every rule in the sample and the tracked fixtures: old declaration and migrated declaration give the same derived rows (byte-equal) on the same board;
          a second run of the script changes nothing; the loader reads both shapes the same until the owner migrates
docs      RUN.md: the command, what each answer means, the backup and how to go back; the decide guide shows the expression form first
order     unchanged - after the translator per-row cost and the ledger process (owner «지금 순서»)
```

> **[lead -> implementer B] 10-13 small - a decide's aggregation column may be one of its target_fields and nothing refuses it (owner: an aggregation of dt_lot from dt_log into dt_inventory always comes out empty, «dt_lot is also a confirm target»)**

```
what      chain/enrichment/config.py refuses decision_key ∩ target_fields by name but not aggregations ∩ target_fields - one derived column, two writers (the confirm and the aggregation)
          -> refuse by name at save and load: «aggregation <name> is also a target field - one column has one writer; name the aggregation differently»; measure first what happens today
             (which writer wins, is the aggregation dropped) and say it in the report; the same judgement for list_columns if it can collide
also      the guide's decide section: a source column that another rule fills (auto-confirm, join) wakes this rule only with "allow_chain_trigger": true - and a Replay chain fills the rows already blank (one paragraph, with the owner's case as the example)
gate      a cell that saves aggregations {dt_lot: ...} with target_fields [dt_lot] -> refused by name; the loader refuses the same; the guide example runs
order     small, after the slices fixes landed - before ㄴ lands if it fits, otherwise right after
```

> **[lead -> implementer B] 10-13 - 993d17c31 changes: do NOT refuse - make an aggregation and a target field on the same column work together (owner «2번인데 그냥 호환되게 바꿔» - the owner's case is a decide whose target field dt_lot is also its aggregation over dt_log.dt_lot)**

```
meaning   one column, two writers, told apart by the layers the system already has (no new mechanism):
          the aggregation writes its value into that target column as the chain's layer; a person's or the auto-confirm's value is a higher layer and wins;
          a later recompute never overwrites a higher layer (the layer rule as it is); a blank aggregation leaves the cell blank so the row stays in the queue for confirm / a person;
          a non-blank aggregation fills the target, so that row leaves the queue as a filled row does today
measure   first, today: which writer wins now and why the owner's cell stays blank (is the aggregation dropped for a target column, is it written then blanked, is it never computed) - say it in the report
gate      decide with target_fields [x] and aggregations {x: unique_concat(src.x)}: source rows fill x -> derived x = the aggregate; a person sets x -> a recompute keeps the person's value;
          aggregation blank -> the row is in the queue; the auto-confirm can still confirm it; the same with min/max/count; the guide's decide section says this in one paragraph with the owner's case
also      keep the guide paragraph about allow_chain_trigger (a source column another rule fills) from 993d17c31
retired   the «refuse by name» sentence of 993d17c31 - not built
```

> **[총괄 -> 구현자 B] 10-13 — 459b2ae83(집계와 대상 칸 호환) 소유자 답 둘: ① ㄱ «집계는 빈 값을 안 쓴다 · 층 순위는 그대로» ② 운영에서 파일 인제션도 dt_inventory.dt_lot 을 «쓴다»**

```
①  ㄱ 확정    집계 결과가 빈 값(부재 — strip 뒤 길이 0 · NULL)이면 그 칸에 체인 층을 «안 씀»(빈 값으로 덮지 않음)
              비지 않은 값만 체인 층(우선순위 4)으로 씀. 층 순위 표는 손대지 않음 — 자동 컨펌(미등재 99) 순위 올리기는 «안 함»
              앞선 체인 층 값이 있는데 다시 계산이 빈 값이면: 그 층을 거둠(지금 값이 «없음»이니까) — 남겨 두면 옛 집계가 거짓으로 보임. 거두는 문은 지금 체인이 쓰는 그 문
②  파일도 같은 칸을 씀 -> 한 칸에 쓰는 이가 셋(파일 · 집계 · 컨펌/사람). 고르는 것은 지금의 표별 우선순위 선언(resolve_priority_map) 그대로
    재기 먼저   오늘 «항상 비어 나옴»의 원인을 이 셋으로 갈라 보고에 적음:
               (a) 집계의 빈 값 체인 층이 컨펌(99)을 가림  (b) 파일이 빈 dt_lot 을 층으로 써서 집계 · 컨펌을 가림  (c) 집계가 아예 계산 · 기록이 안 됨
               (b) 이면 «고치지 말고 먼저 보고» — 높은 층의 빈 값이 낮은 층을 가리는 것은 표 전부에 걸린 층 규칙이고(사람이 지운 값도 같은 모양), 소유자 «순위 그대로» 범위 밖
    게이트 추가 같은 칸에 파일 층(pipeline_parser 등 표 선언 순위)이 있는 판: 파일 값 있음 -> 보이는 값은 순위 표대로(오늘과 같음) ·
               파일 값 없음(그 행에 층 없음) -> 집계 값 · 집계 빈 값 -> 컨펌 값 · 사람 값은 어느 경우나 이김
문서        가이드 decide 절 한 문단에 «한 칸에 셋이 쓸 때 무엇이 보이나»를 표별 우선순위 선언 낱말로
순서        지금 — ㄴ(a08c95676) 착지했으니 이것 먼저, ㄷ(원장 프로세스) 안 셋은 그 뒤
```

> **[총괄 -> 구현자 B] 10-13 — ㄷ(4fa3bc629)의 남은 둘, 소유자 답 «안 무거우면 추천대로»**

```
④ 옛 키   ㄱ — 고침 · 지움 변경 알림이 «바뀐 칸의 옛 값»을 싣는다. crud 가 감사에 옛 값을 쓰는 그 자리에서(데이터베이스를 더 읽지 않음)
          지움 · 고침 알림을 짓는 넷(crud 둘 · ORM · 대기 사건 접기)을 «한 함수»로 접고 넷이 그것을 부름 — 같은 커밋
          맵퍼 전부가 같은 칸으로 읽음 · decide · 복사는 옛 키 묶음도 새 키 묶음과 같은 배치에서 한 번에 다시 셈. 키가 안 바뀐 고침은 더 하는 일 0
② 확정 파생 행  다시 세어 원천 0 -> 사람 층(user)이 있는 행은 체인 층만 거두고 행은 남김 + 로그 한 줄 «[ChainRetract] kept <표> <키>: a person's value, no source rows»
          사람 층 없으면 지금처럼. 화면 표시는 이번에 안 함
«안 무거우면»  실제 런처 판에서 전후 같은 판: 키 안 바뀐 고침 1,000 행 · 키 바뀐 고침 1,000 행 · 지움 1,000 행 — 체인 그룹 초와 알림 크기(바이트)
          키 안 바뀐 고침이 10 % 넘게 느려지거나 운영 규격(1,000 행 ≤ 5 s)을 넘으면 «짓지 말고» 수와 함께 보고
게이트    L1 -> L2 고침 뒤 L1 집계가 빠짐 · 지운 행이 L1 집계에서 빠짐 · 사람 값 있는 원천 0 행이 남음 + 로그 · 변이 셋(옛 값 안 실음 · 옛 키 안 셈 · 사람 층 무시)
```

> **[총괄 -> 구현자 B] 10-13 — f666b114a ② 고침 (소유자 「이런 논리면 파생행도 원본에 없어지면 지워야지」)**

```
② 확정 파생 행  다시 세어 원천 0 -> 파생 행을 «지움» — 사람 층(user)이 있어도. «남기고 로그»는 은퇴
          지우는 문은 오늘 행 지움이 쓰는 그 문(감사에 옛 값이 남는 길) — 사람이 적은 값은 이력에서 볼 수 있음
          로그 한 줄 «[ChainRetract] deleted <표> <키>: no source rows (a person's value was on it)» 는 사람 층이 있던 행에만
게이트    ② 칸을 «사람 값 있는 원천 0 행이 지워지고 감사에 그 값이 남음»으로 · 변이 «사람 층이면 안 지움»이 빨강
```

> **[총괄 -> 구현자 B] 10-13 — 착지 뒤 검수 둘: 4bb3b4d85 NO-GO -> 총괄이 되돌림(474254ed8) · a08c95676 GO-WITH-FIXES (탐침 총괄 scratchpad qab5_* · qab4_*)**

```
가 decide 집계가 제 확정 칸 채우기 — 다시 짓기 (ㄷ wip 를 커밋해 두고 이것 먼저, 소유자가 기다리는 dt_lot)
  1 [높음] 빈 집계의 거두기가 mapper.py 안 withdraw_source(CHAIN_SOURCE, columns) — 같은 칸의 다른 체인 층(조인 · 다른 규칙)까지 거둠
       -> 맵퍼는 «읽기만»(ingestion_worker 계약). 거두기는 쓰기 뒤 워커의 한 문 _withdraw_and_tell / withdraw_by_origin 으로,
          «이 규칙이 그 칸에 쓴 층»만(규칙의 표 · 칸 + 그 묶음의 원천 행) — 그 문이 층 잃은 행마다 EDIT 를 내니 화면도 따라옴(결함 4 같이 닫힘)
  2 [높음] 백필이 그 칸을 enrichment_backfill 층(99)으로 써서 끝내 안 거둬짐 -> 백필도 체인과 같은 층 · 같은 쓰기 길(쓰는 이 하나)
  3 [중] 백필이 «안 건드린다»는 기존 행의 체인 층을 거둠 -> 백필의 쓰기 범위 밖은 거두기도 밖
  게이트 조인 값 + 규칙 A 빈 집계 -> 조인 값 남음 · 규칙 B 값 남음 · 백필 OLD -> 원천 지움 -> 다시 셈 -> 빈 칸 · 거둔 행이 그리드 메시지에 실림
         변이 «행의 칸 전부 거둠» · «표 전체 행 거둠» · «다른 규칙 층 거둠» 빨강
  문서   mapper.py:8-10 · backfill.py:46-52 · enrichment_rules.md:166 · chain_ingestion_guide.md:297 · 816 · CODE_MAP:4569 · CONFIG_ROLLOUT_GUIDE:279 · RELEASE_LOG(되돌림 표시 걷고 새 항목) · RUN.md 되돌림 절
  덤(소유자께 올림 — 짓지 않음) 파일 층 이름이 «파일마다 다른 파일명»(directory_watcher:3527)이라 순위표에 «파일»을 적을 자리가 없음 — 수와 함께 보고에 한 줄
나 번역기 쪽마다 한 번(a08c95676) 고침 — 작게 한 커밋
  1 [중] roleframe.py:839 한 행 단위 지름길이 «결정적 JSON» 검사(_row_sort_token)를 건너뜀 -> 한 행이면 Decimal · date · 시간대 없는 datetime · NaN 이 원자로,
       두 행이면 전처럼 쪽이 멈춤 — 행 수로 갈리는 문. 총괄 결정: 전 동작(멈춤)으로 맞춤 — 한 행에도 같은 검사. 바꿀지는 소유자 몫이라 이번에 안 바꿈. 검사 비용 한 줄
  2 [낮] 분자 안 행 ref 순서 칸(변이 Md 생존 — event_frame.py:824)
  3 [낮] RUN.md «바이트까지 같다» · RELEASE_LOG 문장을 범위대로 · SERVER_DEFECT_QUEUE S-64-c 갱신 · RUN.md 되돌리기 줄에 «RUN.md 는 충돌 — 코드만 되돌아감» · roleframe.py:837 주석
다 PG 8 실패 판정(검수관): 단독 통과 셋(순서 잔여) · test_ledger_l1_pg 둘(시험 낡음 — 샘플이 09-25 부터 process_param_num_measure 안 선언) ·
     recipe walk 둘(환경) · 진짜 결함 하나 — backfill.py:1328-1335 행 수 추정이 ANALYZE 전이면 다른 스키마 같은 이름 표를 집음(478,718) -> 스키마 붙여 묻기. 낡은 시험 둘 고치기와 함께 작게
순서  가 -> 나 -> 다 -> ㄷ 이어서
```

> **[총괄 -> 구현자 B] 10-13 밤 — 원장 프로세스(19d6da585) 짧은 검수: GO-WITH-FIXES (가 다음, 작게 한 커밋)**

```
1 [높음] 체인 워커만 재기동하면(런처는 옛 코드 그대로) 원장 따라가기가 조용히 0 — 런처 자식 목록은 런처 기동 때만 읽힘
       -> 체인 워커가 기동 뒤 N 초 안에 신선한 "ledger" 박동이 없으면 경고 한 줄 · RUN.md 에 «이 착지는 런처 전체 재기동, 체인 워커만이면 원장이 멈춤 · 확인은 pg_stat_activity 의 assy_ledger»
2 [중] 성공 · 격리 그룹마다 commit 뒤 event.event_type 을 읽어 사건마다 SELECT(ingestion_worker:2990 · 3094 · 3420) -> DELETE 의 {표: row_ids} 를 commit 전에 event_ids 옆에서 잡음
3 [중] 큐 화면 × 로 치운 DELETE · 깊이 상한으로 거절된 DELETE 가 이제 안 거둬짐(전에는 따라가기가 상태 무관하게 거둠) — 총괄 결정: 전 동작으로(행이 지워진 것은 사실 — 치움은 체인 규칙을 안 돌릴 뿐)
       그 둘의 자리에서도 같은 _retract_deleted_rows 를 부름
4 [중] 거두기 실패를 삼키고 rollback 안 함(3412-3414) — 공유 세션 오염 -> except 안에서 db.rollback()
5 [중] drain_outbox_once 가 LIMIT 1000 으로 payload 까지 읽고 행 예산에서 끊음 — 밀린 큐에서 배치마다 1000 읽고 1~2 씀 -> id 와 행 수만 먼저, payload 는 예산 안의 것만
6 [낮] QA 격리 스택(devenv.py:157)에 원장 프로세스 없음 -> 같은 자식 목록에서
RUN.md  되돌리기 해시 19d6da585 · «원장만 세우는 법은 없음(Pause 는 체인도 세움)» · «상한 1000 행 — 사건 하나가 1000 행을 넘으면 그만큼»
```
