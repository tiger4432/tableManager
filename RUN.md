# 지금 돌리면 되는 것

> ## 🔴 [09-26 밤 1] **체인 멈춤 증거 — 연결 이름 · 멈춤 줄 · 이전 체인 워커가 남긴 쿼리 끊기 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러 — 연결 이름은 프로세스를 새로 띄워야 붙음)**
>
> ```
> 연결 이름    pg_stat_activity 의 application_name — assy_server · assy_watcher · assy_chain · assy_scheduler · assy_retroactive · 스크립트는 assy_<스크립트>
>             체인이 멈춤을 물을 때 여는 짧은 연결은 assy_chain_probe
> 찾기        Select-String -Path server\chain_worker.log -Pattern ": stalled \d+ s in "        <- 멈춘 묶음마다 한 번
>             Select-String -Path server\chain_worker.log -Pattern "left by a chain worker"       <- 기동 때 끊은 남은 쿼리
>             conda run --no-capture-output -n assy_manager python server/scripts/diagnose_db_health.py   <- §3 이 같은 문장
> 멈춤 줄     [Chain] tx <id> · <행> row(s) of <표>: stalled <초> s in <단계> (rule <규칙> · db pid <pid>) - <그 pid 가 하고 있는 것>
>             어드민 health 의 chain: 단계가 300 s 넘게 안 움직이면 stalled + 같은 문장. 움직이는 긴 묶음은 ok (예전엔 60 s 넘으면 wedged)
> 문장의 뜻과 할 일
>   waiting Lock:… on pid N (assy_watcher, active …)                   워처 청크가 같은 행을 쓰는 중 — 기다림(청크가 커밋하면 풀림)
>   waiting Lock:… on pid N (assy_<무엇>, idle in transaction <긴 시간>)  그 프로세스가 트랜잭션을 연 채 멈춤 — 그 프로세스 재기동
>   waiting Lock:… on pid N (assy_chain, …)                            체인 자기 프로세스의 리플레이 · 소급이 같은 행을 씀 — 청크 커밋마다 풀림. 안 풀리면 그 소급을 멈춤
>   waiting Lock:… on pid N (assy_ 로 시작하지 않는 이름)                 사람 · 외부 도구의 연결
>   its own query active <초> (no lock…): SELECT …                      그 쿼리 자체가 느림 — 오늘 운영의 조인 답 SELECT 가 이 모양. 급하면 그 규칙 enabled:false + 리로드, 나중에 리플레이
>   idle in transaction <초> - the time is not in the database          DB 가 아니라 파이썬(맵퍼 계산)이 오래 걸림
>   not probed (…)                                                      묻기가 실패 — diagnose_db_health 로 직접
> 남은 쿼리    체인 워커가 기동할 때 «이미 없는» 이전 체인 워커의 연결(이름 assy_chain · 이 프로세스보다 먼저 열림)을 끊고 하나마다 한 줄
>             assy_retroactive · 스크립트 · 다른 프로세스 이름은 안 건드림. 다른 체인 루프가 살아 있으면 아무것도 안 끊음
>             ⚠️ 이 착지 «뒤 첫 재기동»에는 못 끊음 — 이전 코드의 연결은 이름이 없음(diagnose 의 app=-). 두 번째 재기동부터 스스로 풂
> foreign_beat 박동 파일의 pid 가 감독자가 띄운 pid 가 아님 — 새 워커가 첫 박동 전에 막혀 있고(기동 인덱스 작업이 남은 쿼리 뒤에서 기다림) 파일엔 옛 pid 가 남은 것
> 워처 청크 줄  " | blocked by pid N: …" 가 " | waiting Lock:… on pid N (<이름>, <state> <시간>): …" 로 바뀜 — 같은 함수의 문장
> 스위치      없음(로그 · health 문장만). 멈춤 문턱은 워처와 같은 300 s
> 되돌리기    git revert 뒤 네 프로세스 재기동
> ```

---

> ## 🔴 [09-26 저녁 2] **표기 값 규칙 1 단계 — join · pad_last_number · replace · time 의 선언 점검과 미리 보기 — 마이그레이션 «없음» · 재기동 API (notation_rules.json 에 선언이 있을 때)**
>
> ```
> 총괄 한 번   python server/scripts/install_product_tables.py --apply     <- 라이브 table_config 에 notation_alias 표(비어 있음)
>            인자 없이 돌린 dry run 이 "1 to add" 면 아직 안 한 것 · "0 to add" 면 된 것
> 확인        GET /admin/config/resolve?domain=notation  -> 선언마다 effective / rejected
>            rejected 에 "Refused: the join character is the one this column's key is joined with" 이면 그 칸의 join 을 다른 글자로
>            GET /admin/config/notation/preview?table=<표>&column=<칸>  -> write 칸은 "write": true · time 칸은 time_left_as_is
> 뜻         이 단계는 «저장하지 않음» — "write": true 는 미리 보기까지. 저장은 2 단계 착지부터
>            write 칸은 «적은» 규칙만 돎(기본값 separator · case 안 옴) — {"join": "-", "pad_last_number": 2} 면 wafer.1 -> wafer-01
>            미리 보기 folds_again 이 0 이 아니면 한 번 더 접을 때 또 바뀌는 값 — 소급 전에 규칙이나 별칭 행을 고침
> 되돌리기    git log --oneline --grep "written spelling" --grep "written column runs only" 의 커밋을 새것부터 git revert 뒤 API 재기동
>            쓰는 것 없음(notation_alias 표는 남음 — 비어 있음)
> ```

---

> ## 🔴 [09-26 저녁 1] **헤비 레인 쓰기 로그 — 청크 줄의 곁표 넷 · 파일마다 한 줄 — 마이그레이션 «없음» · 재기동 감시자(워처) · 체인 워커**
>
> ```
> 찾기       Select-String -Path server\watcher.log -Pattern "\[Ingest\] .* FILE "            <- 파일이 끝날 때 한 줄 (두 레인 같은 줄)
>            Select-String -Path server\watcher.log -Pattern "\[Ingest\] .* chunk \d+:"       <- 청크마다 한 줄
>            체인 쪽 같은 쓰기 단계는 chain_worker.log 의 "[Chain] group" 줄 INSIDE THE WRITE 에 같은 모양으로 — 그 줄은 뷰를 지은 묶음에만 찍힘(보통 묶음엔 안 나옴)
> 파일 줄     <표> FILE <파일>: 행 수 · 걸린 초 · 분당 행 · <레인> · waited <초> (<무엇을 기다렸나>)
>            · sent: new · changed · unchanged · cells changed · side-table rows · STAGES(parse · apply · commit) · INSIDE THE WRITE · DB wait samples (Lock)
> 비교하는 법  같은 표의 느린 파일 줄과 안 느린 파일 줄을 위아래로 놓고 칸마다 견줌
>            waited 가 크면 쓰기가 아니라 «차례»가 느린 것 — heavy 는 (queue + table lock) · normal 은 (table lock) · 레인 없이 들어온 파일은 not measured
>            changed · cells changed 가 크면 고칠 게 많은 파일 — audit logs · cell sources 행 수가 같이 큼
>            같은 행 수인데 한 쓰기의 초만 크면 그 곁표 쪽(색인 · 부풀음). Lock 표본이 있으면 다른 쓰기에 막힌 것
> 청크 줄     side tables 한 덩어리가 넷 — audit logs · cell sources · cell overwrites · overwrite deletes, 각각 «초 / 행 수». row build 에 «바뀐 셀 수»
> 스위치      이 두 줄을 끄는 칸은 없음. ingestion_settings 의 chunk_wait_sampling=false 는 DB 대기 표본(청크 줄 waits · 파일 줄 DB wait samples)만 끔
> 되돌리기    git revert 뒤 워처 · 체인 워커 재기동. 쓰는 것 없음(로그만 — 새 질의 0)
> ```

---

> ## 🔴 [09-26 오후 7] **수집기 하루 단위 소급 — 소급 연산 «Backfill a collector day by day» — 마이그레이션 «없음» · 재기동 API · 스케줄러**
>
> ```
> 쓰는 법    Admin -> 소급 -> "Backfill a collector day by day" · collector = <표>/<스크립트.py> (# window: 를 적은 수집기) · start = YYYY-MM-DD (KST)
>            CLI: python -c "from admin import retroactive; retroactive.run_here('collector_backfill', {'collector': '<표>/<스크립트.py>', 'start': 'YYYY-MM-DD'})"
> 도는 모습   start(날짜면 그날 00:00 KST)부터 24h 씩, 마지막은 지금에서 자름 — 하루 = 스크립트 한 번(그 날 구간이 마커에 채워짐)
>            그 날 파일이 적재 대기열을 지날 때까지(파일 체크포인트가 DONE) 기다린 뒤 다음 날. 진행 N/M 일 · 날 사이에서 취소
> 멈춤       그 날 파일이 FAILED 면 run 이 실패로 끝나고 사유에 그 날짜 — "…failed to ingest (…) - fix it, then start again from <날짜>"
>            고친 뒤 start 를 그 날짜로 다시 걸면 거기서부터 끝까지
> ⚠️ 기다림   시간 상한 없음 — 워처가 멈췄거나 체크포인트 기록이 실패한 파일이면 그 날에서 계속 기다림(진행이 안 움직임). 취소로 끝냄
> 확인       소급 목록에서 N/M 일 · 끝나면 done · days_done
> 되돌리기    git revert 뒤 API · 스케줄러 재기동. 이미 적재된 날의 행은 남음(일반 적재와 같음)
> ```

---

> ## 🔴 [09-26 오후 6] **수집기 선언 점검 — Declarations 에 collector 영역 · 짝이 안 맞는 스크립트는 로드 거절 — 마이그레이션 «없음» · 재기동 스케줄러 · API**
>
> ```
> 거절       # window: 는 있는데 {{WINDOW_START}} · {{WINDOW_END}} 가 없음 / 마커는 있는데 # window: 가 없음 / window 가 <n>d · <n>h 가 아님
>            {{LIST:표.칸}} 의 칸이 table_config 에 없음 · 날짜 칸임
>            -> 그 수집기는 스케줄러에 안 올라감(Auto Update 탭 목록에서 빠짐)
> 볼 곳      스케줄러 로그  "[Collector] '<표>/<스크립트>' is not loaded - <문장>"
>            Declarations -> "Auto update collectors (script markers)" 영역의 rejected — 같은 문장
> 이 박스    착지 전 잼: 수집기 10 개 전부 fine · rejected 0 (마커를 쓰는 스크립트가 없음)
> 줄이 나오면  스크립트 머리 · 마커를 짝으로 맞추거나, 목록 칸을 table_config 에 선언(글자 · 숫자 칸)
> 되돌리기    git revert 뒤 스케줄러 · API 재기동. 쓰는 것 없음(판정만)
> ```

---

> ## 🔴 [09-26 오후 5] **수집기 스크립트의 목록 마커 {{LIST:표.칸}} — 마이그레이션 «없음» · 재기동 스케줄러(run_auto_update)**
>
> ```
> 쓰는 법    스크립트 본문에  AND b.part IN ({{LIST:part_filter.part_id}})
>            실행마다 그 표 그 칸의 그리드 값(빈칸 뺌 · 한 번씩 · 값 순서)이 'a','b' 로 들어감. 값 속 ' 는 '' 로
> 거절       목록이 비었거나 · 1,000 값을 넘거나 · 못 읽었거나 · 표·칸이 선언 안 됐으면 그 실행은 «시작 안 함» (FAIL)
>            Auto Update 탭 서랍에 그 한 문장(트레이스백 아님) — 예 "{{LIST:…}} has no value in '…'. The run did not start."
> 재기동 까닭  스케줄러가 시작할 때 동적 모델을 만들어야 목록을 읽을 수 있음(이번에 넣음). 재기동 전에는 목록 마커 스크립트가 거절됨
> 확인       목록 마커를 적은 스크립트를 즉시 실행 -> raws 의 새 CSV(또는 스크립트가 보낸 쿼리)에 값 목록이 들어 있음
> 되돌리기    git revert 뒤 스케줄러 재기동. 쓰는 것 없음(그리드를 읽기만)
> ```

---

> ## 🔴 [09-26 오후 4] **수집기 스크립트의 시간 구간 마커 — 마이그레이션 «없음» · 재기동 스케줄러(run_auto_update)**
>
> ```
> 쓰는 법    스크립트 머리(위 20 줄)에  # window: 1d   (또는 <n>h)   · 선택  # window_format: %Y-%m-%d %H:%M:%S (없으면 이 모양)
>            본문 어디든  {{WINDOW_START}} · {{WINDOW_END}}
> 도는 모습   크론 · 즉시 실행 모두 — 실행 시각(KST)에서 window 만큼 앞 ~ 실행 시각을 채워 돌림. 원본 파일은 안 바뀜
>            out 을 안 쓰는 스크립트는 채운 사본(<스크립트>.<pid>.filled, 같은 폴더)을 자식 프로세스로 돌리고 끝나면 지움 — 수집기로 안 잡힘
> 그대로     # window: 가 없는 스크립트는 전과 같음(마커를 안 채움) — 이 박스 수집기 10 개가 전부 그렇다
> 거절       # window: 가 <n>d · <n>h 가 아니면 그 실행이 FAIL, 사유 "'# window: …' is not a length - write it as <n>d or <n>h"
> 확인       머리를 적은 스크립트를 즉시 실행 -> raws 의 새 CSV 에 마커 대신 날짜 · 시각이 들어 있음
> 되돌리기    git revert 뒤 스케줄러 재기동. 쓰는 것 없음(사본은 실행마다 지움)
> ```

---

> ## 🔴 [09-26 오후 3] **파생 표를 대상으로 한 조인은 그 표의 키를 조인 키 안에서 — 마이그레이션 «없음» · 재기동 API · 체인 워커**
>
> ```
> 규칙       조인 대상이 «켜진 파생행 규칙»의 파생 표이면, 그 표의 composite_key_source(없으면 business_key) ⊆ 조인의 on[].left
>            아니면 로드 거절 · 저장 400(code join_key_contract) · 선언 점검(Declarations) 거절 줄 — 세 곳이 한 문장
>            문장은 파생행 키 계약 그대로, 키 이름만 조인 것: "derived table composite_key_source must be a subset of the join's on[].left columns (violation: [...])"
> 그대로     파생 표가 아닌 표로 가는 조인(찾아보기 조인)은 키가 넓어도 섬 · 꺼진 파생행 규칙의 표는 파생 표로 안 셈
> 확인       재기동 뒤 체인 워커 로그에 "[ChainRules] <이름> refused (1): join_key_contract" 줄이 없으면 이 박스는 영향 0
>            (착지 전 잼: 켜진 조인 inventory_confirmed · test 둘 다 dt_log 대상, 파생 표는 dt_inventory 하나 -> 새로 거절 0)
> 줄이 나오면  그 조인은 안 돎 — 파생 표의 키 칸을 조인의 on 에 더하거나, 파생 표의 composite_key_source 를 조인 키 안으로 줄임
> 되돌리기    git revert 뒤 API · 체인 워커 재기동. 쓰는 것 없음(판정만)
> ```

---

> ## 🔴 [09-26 오후 2] **파생행 집계에 unique_concat — 마이그레이션 «없음» · 재기동 체인 워커 · API**
>
> ```
> 선언       파생행 규칙의 aggregations 에 한 줄  "wafer_ids": {"fn": "unique_concat", "column": "wafer_id", "separator": ", "}
>            파생 표(table_config)에 그 이름의 text 칸이 있어야 함(없으면 로드 거절 — 전과 같음)
> 값         그 판단키의 커밋된 소스 행 전체에서 — 빈 값 빼고 · 중복 없이 · 값 순서 · separator 로 이음. 값이 하나도 없으면 비움
> 거절       count · min · max 에 separator 를 적으면 규칙이 이름과 함께 거절됨 · separator 가 글자가 아니면 거절
> ⚠️ 채워지는 때  그 키에 새 소스 행이 올 때(체인). enrichment backfill 은 «없는 파생행만» 만들고 기존 행은 안 건드림 —
>            기존 파생행에 새 집계를 채우는 문은 아직 안 정함(총괄께 여쭘)
> 되돌리기    git revert 뒤 체인 워커 · API 재기동. 선언에 unique_concat 을 적었으면 그 줄을 먼저 지움(되돌린 코드는 모르는 fn 으로 거절)
> ```

---

> ## 🔴 [09-26 오후 1] **같은 내용의 실패 파일이 워처 기동마다 다시 읽히지 않음 — 마이그레이션 «없음» · 재기동 감시자(워처)**
>
> ```
> 무엇       raws 에 남은 실패 파일(아카이브 끔)이 같은 내용의 사본을 가지면 기동마다 하나씩 다시 파싱 · FAILED 기록 +1 이었음
>            이제 «그 내용이 FAILED» + «이 경로에서 실패한 뒤로 파일이 안 바뀜»이면 조용히 건너뜀(기록 없음 — tier-1 과 같이)
> 그대로     같은 내용이 새 이름으로 오면 읽음 · 실패 뒤 고쳐 저장하면(mtime 이 뒤) 읽음 · Retry 는 늘 읽음
> 확인       재기동 뒤 워처 로그 기동 스윕 줄의 dispatched 수 — 같은 내용 실패 파일만 남아 있으면 0
> 되돌리기   git revert 뒤 워처 재기동. 쓰는 것 없음(읽기만: 체크포인트 한 줄 · 파일 기록 FAILED 줄)
> ```

---

> ## 🔴 [09-26 아침 3] **PG 시험은 자기 DB assy_test 에서 — 분리 환경(assy_qa)을 켜든 말든 같은 답 · 운영 무관 · 재기동 «없음»**
>
> ```
> 무엇       시험의 PostgreSQL 되돌이가 assy_qa 가 아니라 같은 서버의 assy_test (빈 DB + pg_trgm). 이름은 tests/support/isolated_pg.PG_TEST_DATABASE 한 자리
> 처음 한 번  시험이 postgres 관리 DB 에서 CREATE DATABASE assy_test · pg_trgm 설치. 사람이 할 일 없음
> 그대로     분리 환경(devenv)은 assy_qa. ASSY_PG_TEST_DATABASE_URL 로 다른 DB 를 주면 그것이 먼저
> 되돌리기   git revert. assy_test 는 남음 — 지울 때 DROP DATABASE assy_test (시험 말고 쓰는 것 없음)
> ```

---

> ## 🔴 [09-26 아침 2] **쓴 값이 하나도 없는 파일은 FAILED + 한 문장 · 일부만 버린 파일은 기록에 버린 칸 문장 — 파서 길 둘이 같은 답 · 마이그레이션 «없음» · 재기동 감시자(워처)**
>
> ```
> 전부 버림   선언된 칸이 하나도 없는 파일 -> FAILED · 파일 기록(error_message) 한 줄:
>            No column of this file is declared on '<표>', so nothing was written - dropped <칸들>. Declare the columns on the table, or send the file to the table that declares them.
>            표준 파서(헤더에서) · 커스텀 파서(쓰기 고리에서) 같은 문장. 전: 커스텀은 SUCCESS · 기록 없음, 표준은 FAILED · 트레이스백
> 일부 버림   SUCCESS 그대로 + 기록에 Dropped N undeclared column(s) over M row(s): <칸>=<값 수> ...
>            전: 표준 파서 길은 기록 없음(표준 파서가 스스로 빼고 WARNING 만)
> 로그       버린 칸은 워처의 한 자리가 적음 — 칸마다 처음 한 번 WARNING · 파일마다 INFO(기록과 같은 문장). 표준 파서의 "ignoring unknown column(s)" WARNING 은 없어짐
> 아카이브 끔  FAILED 파일은 raws 에 남음. 내용이 같은 실패 파일이 둘 이상이면 워처 기동마다 하나 빼고 다시 읽혀 FAILED 기록이 늘어남(보고만 · 958d57347)
> 되돌리기    git revert 뒤 워처 재기동. 쓰는 것 없음(파일 기록 · 체크포인트의 상태 낱말만 달라짐)
> ```

---

> ## 🔴 [09-26 아침 1] **스케줄러 재기동을 넘어 수집기의 마지막 실행이 남음 · 끊긴 실행은 FAIL + 사유 — 마이그레이션 «없음» · 재기동 스케줄러**
>
> ```
> 재기동 뒤   Auto Update 탭의 last_run · last_status · last_error 가 재기동 전 그대로 (전: PENDING · last_run 없음)
> 끊긴 실행   수집 도중 스케줄러가 죽고 되살아나면 그 수집기는 FAIL
>            last_error = The scheduler running this collector stopped before it finished - run it again.
>            last_run = 끊긴 실행의 시작 시각 · 대기열(지금 도는 것)에는 안 나옴
> 로그       auto_update.log — [Collector] '<표>/<스크립트>' was RUNNING under scheduler/<host>/<pid>, which is gone - recorded as FAIL
> 되살림 없이 스케줄러가 죽은 채면 지금처럼 탭 · 대기열 state 가 orphaned (그걸 적는 프로세스가 없음)
> 도장 없는 옛 RUNNING   이 코드 전의 줄 — unknown 그대로, 다음 실행이 덮음
> 되돌리기    git revert. 쓰는 것은 상태 파일 server/config/scheduler_status.json 뿐 (지금도 스케줄러가 쓰는 파일)
> ```

---

> ## 🔴 [09-26 새벽 2] **수집기·소급의 «누가 돌리나» — 대기열 항목에 state · Auto Update 탭 낱말 · 재적재 도중 끝난 수집이 RUNNING 으로 안 남음 — 마이그레이션 «없음» · 재기동 API · 스케줄러 · 체인 워커**
>
> ```
> 대기열    /admin/chain/queue 의 now_running 항목마다 "state": running · orphaned · unknown
>           orphaned = 그 일을 시작한 프로세스의 심박이 없거나 다른 pid 가 뜀 — 시작한 프로세스가 죽음
>           unknown  = 도장이 없는 옛 줄 (이 코드 전에 시작된 수집 · 소급)
> 탭        Auto Update 의 상태 낱말 — RUNNING 인데 그 스케줄러가 없으면 orphaned (unknown 은 옛 줄)
> 수집 도중  설정 재적재(SYSTEM_RELOAD)가 와도 끝나면 SUCCESS · FAIL — 전: 끝나도 RUNNING 으로 남음
> 확인      상태 파일 server/config/scheduler_status.json 의 줄마다 "runner": scheduler/<host>/<pid>
>           없으면 스케줄러가 옛 코드
> 재기동     스케줄러 재기동 뒤의 수집기 상태는 [09-26 아침 1]
> 되돌리기  git revert. 쓰는 것은 상태 파일의 runner 칸뿐
> ```

---

> ## 🔴 [09-26 새벽 1] **표·원장 소급도 없는 이름은 기록 «전»에 거절 · 거절된 소스의 rescope 는 이름 있는 거절 — 마이그레이션 «없음» · 재기동 API · 스케줄러 · 체인 워커**
>
> ```
> 확인      어드민 소급에서 resolve · withdraw · ledger_backfill · ledger_rescope 에 없는 표·칸·소스 이름
> 답의 뜻   400 한 문장(영어), 실행 목록에 줄 없음                                 새 코드
>           실행 목록에 줄이 생기고 queued -> failed                                API 가 옛 코드
>           건수 400 이 「이 연산의 건수를 계산할 수 없습니다: …」 로 시작              API 가 옛 코드
> 거절된 소스  rescope -> 「source 'X' was refused by the loader, so it has no plan to run: …」 (전: 자식이 AttributeError)
>           ledger_backfill 의 건수는 그대로 not_applicable (있는 이름이라 문에서 안 막음)
> 빈 표 설정  CLI · 데몬이 「table_config.json is empty or missing」 을 이름 판정보다 먼저 말함
> 되돌리기   git revert. 쓰는 것 없음
> ```

---

> ## 🔴 [09-25 밤 10] **대형 레인 워커 N — 한 표는 한 워커가 차례대로, 다른 표끼리 동시 · 칸 heavy_lane_workers(기본 1) · 마이그레이션 «없음» · 재기동 감시자**
>
> ```
> 칸        server/config/ingestion_settings.json 의 "heavy_lane_workers" — 1 이상 정수, 없으면 1 (= 전과 같음)
>           감시자 재기동 때 읽음. 값은 운영자가 적음 (박스 설정에 아무도 안 채움)
> 확인      다른 표의 큰 파일 둘을 거의 같이 올림 -> 감시자 로그의 「📥 New file detected: <파일>」 (처리 시작) 두 줄의 시각
> 답의 뜻   워커 1: 둘째 표는 첫째가 끝난 뒤 시작                          그대로 (칸이 없거나 1)
>           워커 N>1: 둘째 표가 첫째가 도는 동안 시작 · 같은 표 둘째 파일은 첫째 뒤   새 코드 + 칸 읽음
>           N>1 인데 둘째 표가 기다림                                    감시자가 옛 코드이거나 재기동 전
> 잘못 적음  「Ignoring invalid 'heavy_lane_workers' …」 경고 한 줄 뒤 1 로 돔
> 주의      쓰기가 적재 시간의 거의 전부 — 워커를 늘리면 DB 부하가 같이 늘어남
> 되돌리기  칸을 1 로(재기동) — 또는 git revert
> ```

---

> ## 🔴 [09-25 밤 9] **업로드한 큰 파일이 대형 레인을 탑니다 — 업로드가 raws/ 옆에 다 쓴 뒤 옮김 · 마이그레이션 «없음» · 재기동 API**
>
> ```
> 확인      문턱(ingestion_settings 의 heavy_file_mb, 기본 10 MB) 이상인 파일을 화면에서 업로드 -> 감시자 로그
> 답의 뜻   「🐘 Routed to heavy lane queue (… B): user(…)_…」            새 코드
>           그 줄 없이 「New file detected」 뒤 바로 처리                    API 가 옛 코드 (재기동 안 먹음)
> 남는 것   표 작업공간 폴더(raws/ 의 부모)에 「.upload.<hex>」 파일이 남아 있으면 — 쓰다가 프로세스가 죽은 것. 지워도 됨(감시자는 안 봄)
> 그대로    탐색기·네트워크 복사로 raws/ 에 직접 넣는 큰 파일은 지금처럼 크기를 생긴 순간에 재서 인라인으로 갈 수 있음 (내용은 맞게 들어감)
> 되돌리기  git revert. 쓰는 것 없음 — 파일이 raws/ 에 «나타나는 방식»만 바뀜
> ```

---

> ## 🔴 [09-25 밤 8] **로더가 거절한 원장 소스도 셈 바퀴가 잽니다 — 셈이 거절 문장으로 · 마이그레이션 «없음» · 재기동 체인 워커**
>
> ```
> 확인      /api/ledger/declaration 의 소스별 셈 — 로더가 거절한 소스
> 답의 뜻   「Refused by the loader」 + 로더의 지금 문장              새 코드, 그 소스 차례가 지남
>           옛 남은 행 수 · 「뷰에 row_id 를 선언하라」 처방           체인 워커가 옛 코드, 또는 아직 차례 전 (바퀴 = 소스 수 × 쉼)
> 바퀴 줄    [LedgerCensus] lap: N source(s) — N 에 거절 소스가 들어감. 「retired」 뒤에는 운영자가 은퇴시킨 것만
>           거절 소스마다 매 바퀴 「[LedgerCensus] X failed」 — 지문을 부르는 옛 갈래 (이 수리가 안 들어감)
> 행 없음    거절 소스인데 등록 행이 없으면 계속 없음 — 돈 적이 없다는 뜻
> 되돌리기   git revert. 쓰는 것은 셈 칸뿐 — 다음 바퀴가 다시 씀
> ```

---

> ## 🔴 [09-25 밤 7] **없는 규칙 이름은 기록 «전»에 거절 — 어드민 · 건수 · CLI 같은 문장 · 마이그레이션 «없음» · 재기동 API · 스케줄러 · 체인 워커**
>
> ```
> 확인      어드민 소급에서 없는 규칙 이름으로 실행
> 답의 뜻   400 「chain rule 'X' not found or disabled; available: …」, 실행 목록에 줄 없음   새 코드
>           실행 목록에 줄이 생기고 queued -> failed                                        API 가 옛 코드
>           건수 400 이 「이 연산의 건수를 계산할 수 없습니다: …」 로 시작                    API 가 옛 코드
> 관문 문장  「op=X is progressing, last progress Ns ago」 · 진행 보고가 없으면 「no progress reported yet」
>           「progressing for Ns」 가 보이면 그 프로세스가 옛 코드
> CLI 실행  실행 목록의 요청자 칸 = OS 계정 이름 (전: 빈칸)
> 매퍼 로그  「… decision key(s) built for 'T'」 (전: upserted into — 건수만 셀 때도 그렇게 적었음)
> 되돌리기  git revert. 쓰는 것 없음
> ```

---

> ## 🔴 [09-25 밤 6] **숫자 칸에 글자가 오면 «한 문장» — 그리드 · 파일 · 체인 같은 말 · 마이그레이션 «없음» · 재기동 API · 감시자 · 체인 워커**
>
> ```
> 문장     Row N: column 'C' does not take 'V' - a number is expected.
>          그리드  N = 보낸 묶음에서 몇 번째          파일  N = 파일의 몇 번째 데이터 행 (머리줄 빼고)
>          체인    [rules=그 규칙 target=그 표] 뒤에 같은 문장 — N 은 그 규칙이 쓴 묶음에서 몇 번째
> 확인     파일 탭의 실패 사유 · 그리드 붙여넣기 거절 토스트 · 체인 실패 목록의 사유
> 답의 뜻   그 문장                         새 코드
>          한국어 「올바른 숫자 형식이 아닙니다」   그 프로세스가 옛 코드 (재기동 안 먹음)
>          파일 사유가 여러 줄 Traceback        이름 붙은 거절이 아닌 다른 실패 — 지금처럼 전체를 남김
>          체인 사유 머리가 (unknown)           규칙 이름을 모르는 실패 (쓰기 전 단계) — 쓰기에서 난 거절은 이제 규칙을 적음
> 되돌리기  git revert. 쓰는 것 없음 — 거절 문장과 사유 머리만 바뀜
> ```

---

> ## 🔴 [09-25 밤 5] **소급 연산 «전부» 페이지 사이에서 취소 — ledger_rescope · enrichment_confirm 도 · 마이그레이션 «없음» · 재기동 API**
>
> ```
> 무엇     원장 재번역(rescope)은 범위를 1,000 행 페이지로 — 한 페이지의 걷어냄 + 다시 번역이 한 커밋, 묶음은 안 가름
>          강화 확정(confirm)은 큐를 1,000 개 페이지로 — 한 쓸기는 여전히 거래 id 하나
>          소급 카드 일곱이 모두 취소를 받음. 실행은 자식 프로세스가 매번 새로 떠서 새 코드를 읽음 — 카드(× 버튼)만 API 재기동
> 확인     Retroactive 탭에서 두 연산 중 하나를 긴 범위로 -> 도는 중 × -> 다음 페이지 경계에서 cancelled
> 답의 뜻   cancelled · 결과의 행 수 = 끝난 페이지의 행      정상 — 끝난 페이지는 온전, 나머지는 손 안 댐
>          × 가 안 보임                               API 가 옛 코드 (재기동 안 먹음)
>          누르고 한 페이지 더 돈 뒤 멈춤               정상 — 취소는 «다음» 경계에서 읽힘
>          다시 돌리면                               rescope 는 처음부터(이미 한 페이지는 deduped), confirm 은 남은 큐
> 되돌리기  git revert. 쓰는 모양 · 쓰는 값은 같고 «나눠서» 쓸 뿐
> ```

---

> ## 🔴 [09-25 밤 4] **「지금 도는 것」 한 문 — 대기열 응답에 now_running · 마이그레이션 «없음» · 재기동 API**
>
> ```
> 무엇     /admin/chain/queue 가 now_running 을 싣는다 — 체인 규칙 · 소급 실행 · 수집기 · 파일 적재, 한 모양
>          옛 running(체인 규칙만)은 은퇴 — 화면이 now_running 을 읽음 (총괄 c1dc16fdd)
> 확인     server 에서 (API 를 거치지 않고 같은 함수를 부름 — 파일 적재는 API 메모리에만 있어 여기선 안 보임)
> ```
> ```bash
> python -c "import main; from database.database import SessionLocal as S; print(main.get_chain_queue_depth(db=S())['now_running'])"
> ```
> ```
> 답의 뜻   []                                   지금 도는 것 없음
>          where=own_process · cancel={run_id}   소급 실행이 자기 프로세스에서 돎 — 화면 취소가 닿음
>          where=chain_worker · cancel={run_id}  체인 리플레이 (체인 워커 안)
>          where=scheduler                       수집기가 돎 (취소 문 없음)
>          where=chain_worker · cancel=null      체인 규칙 — 워커가 따로 돌면 lap 이 찍힌 순간에만 보임(짧은 규칙은 거의 안 잡힘)
>          KeyError 'now_running'                옛 코드 — git pull 안 됨
> 되돌리기  두 커밋에 걸쳐 있음 — 새 파일 둘은 다른 커밋에 먼저 실렸다. 한 줄로:
>          git revert d6f4b8bcc && git rm server/runtime/running.py server/tests/test_what_is_running_is_one_seat.py
>          쓰는 것 없음 — 응답에 칸 하나가 는 것뿐
> ```

---

> ## 🔴 [09-25 밤 3] **실패 재시도: 행이 지워진 줄은 «끝냄», 한 것이 없으면 refused · 「언제부터 실패」 는 마지막 실패 시각 — 마이그레이션 «없음» · 재기동 API 만**
>
> ```
> 확인     어드민 Chain 탭 실패 목록에서 Retry All
> 토스트    「Reset N failed event(s) to PENDING. …」 로 시작   -> 새 코드 (N 은 PENDING 으로 되돌린 줄 수)
>          「Ended N row event(s) whose row no longer exists」 -> 행이 지워진 줄 N 개를 끝냄 — 실패 목록에서 빠지고 payload 에 cancelled_by=retry · 사유
>          「Successfully reset …」 · 「Skipped … whose row …」 -> API 가 옛 코드 (재기동 안 먹음)
> 곁       끝낸 줄은 SUCCESS 라 통지 스윕이 그 표를 한 번 새로고침함 (triage 취소와 같음) — 결함 아님
> 되돌리기  git revert 하고 API 재기동. 끝낸 줄은 FAILED 로 안 돌아옴 — 행이 없어 다시 돌릴 것도 없음 · 7 일 청소가 지움
> ```

---

> ## 🔴 [09-25 밤 2] **어드민 소급이 자기 프로세스로 돕니다 — 마이그레이션 «없음» · 재기동 «필요» (런처까지)**
>
> 소유자 「어드민에서 백필도 별도 프로세스로 · 대기열만 잘 떠서 제어할 수 있으면 됨」 (bfbe8a525).
> 스케줄러가 집은 소급은 `python -m admin.retroactive_run <run_id>` 자식에서 돕니다. 체인 리플레이는 체인 워커 그대로.
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드립니다
> ③ 재기동        스케줄러 · 체인 워커 · API (프로세스를 내리면 감독자가 새 코드로 띄움)
> ④ 확인          어드민 Retroactive 에서 아무 소급 하나 (쓰는 것 없는 값으로: 예 withdraw · 표 아무것 · 없는 source 이름)
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> 실행 목록의 그 줄 runner 가 retroactive/<호스트>/<pid> 이고 그 pid 가 스케줄러 pid 와 다름   -> 자식에서 돎
>    runner 가 scheduler/…     스케줄러가 옛 코드입니다 (재기동 안 먹음)
> auto_update.log 「[Retroactive] run_id=… runs in its own process pid=…」 한 줄
> retroactive.log                 자식의 START / DONE 줄 · 자식이 죽었으면 retroactive_stdout.log 에 traceback
> 둘을 연달아 누르면              둘째는 queued 로 기다렸다가 첫째가 끝난 뒤 뜸 (동시에 running 둘 = 결함)
> 도는 중 Cancel                  다음 페이지에서 멈추고 cancelled
> 자식이 강제로 죽었으면          기록이 cancel_requested / running 으로 남고 약 60 초 뒤 「주인 없음」 -> Cancel 한 번에 failed 로 풀림
> ```
>
> ### 되돌릴 수 있나
>
> ```
> 끄는 스위치는 없습니다. 코드: git revert bfbe8a525 하고 재기동 — 스케줄러가 다시 자기 스레드에서 돌림
> 지우는 것 없음 · 소급이 쓰는 일은 전과 같고 도는 «프로세스»만 다릅니다
> ```

---

> ## 🔴 [09-25 밤] **CLI 의 쓰기가 어드민 소급과 같은 기록 · 관문 · 취소로 + 실패 요약은 화면 zone 의 날 — 마이그레이션 «없음» · 재기동 «필요»**
>
> 소유자 「내가 백필을 따로 둔 이유가 대형 작업을 별도 프로세스로」. 일은 CLI 자기 프로세스에서 돌고, 기록 · 관문 · 취소 · 끝맺기는
> 어드민 소급과 같은 것을 지납니다 (9ca3633f1). 실패 목록은 표 · 종류 · 날 한 줄 요약을 싣고, 날은 화면이 보낸 zone 의 날입니다 (29711cace).
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드립니다
> ③ 재기동        스케줄러 · 체인 워커 · API 셋 다 (프로세스를 내리면 감독자가 새 코드로 띄움)
> ④ 확인 한 번     원자를 안 쓰는 0 페이지 실행 — 소스 이름은 그 설치의 원장 소스
> ```
> ```bash
> python -m ledger.backfill --source lot_event --max-batches 0
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> 어드민 Retroactive 실행 목록에 ledger_backfill 한 줄 (done) · runner 가 cli/<호스트>/<pid>
>    안 뜨면   CLI 가 옛 코드이거나 문을 안 지났습니다
> 「REFUSED: run_id=… held by …」   다른 소급이 도는 중 — 관문이 CLI 도 막는 것이 정상입니다. 끝나거나 화면에서 취소한 뒤 다시
> 마지막 줄이 KeyError 'not_yet'    이 변경 «전부터» 있던 출력 줄 결함입니다 (보고함). 실행은 이미 done 으로 적혀 있습니다
> /health 의 cli 줄 off_roster      CLI 가 한 번 돌았다는 표시입니다. 경보 아님 — 끝난 뒤에도 남습니다
> CLI 를 강제로 죽였으면            60 초 뒤 실행 목록의 그 줄에서 Cancel -> 잠금이 풀립니다 (failed 로 적힘)
> ```
>
> ### 되돌릴 수 있나
>
> ```
> 끄는 스위치는 없습니다. 코드: git revert 9ca3633f1 29711cace e8d2f7519 (새것부터) 하고 재기동
> 지우는 것 없음 · 쓰는 모양이 바뀐 것 없음 — CLI 가 쓰는 일은 전과 같고, 실행 기록 한 줄씩이 더 남습니다
> ```

---

> ## 🔴 [09-25 저녁] **대기열 — 끝난 줄이 제 상태로 빠집니다 · 체인 대기열이 워커를 봅니다 — 마이그레이션 «없음» · 재기동 «필요» · 한 번 도는 명령 «하나»**
>
> 소유자 「ㄴ 으로」 · 「같은 문하고 옛 줄 치워」. 스케줄러가 줄을 뺄 때 상태와 시각을 같이 찍고(c28ab7ad9),
> 체인 대기열이 따로 도는 체인 워커를 그 워커의 heartbeat 로 봅니다(191c0b54a).
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드립니다
> ③ 재기동        스케줄러 · 체인 워커 · API 셋 다 (run_app.bat 은 떠 있으면 아무것도 안 합니다 — 프로세스를 내리면 감독자가 새 코드로 띄움)
>                확인: /health 의 workers.chain.pid 와 workers.scheduler.pid 가 바뀌었나
> ④ 한 번         재기동 «뒤»에 옛 줄을 치웁니다 — 먼저 드라이런, 수를 보고 나서 --apply
> ```
> ```bash
> python scripts/outbox_triage.py --finish-stranded
> ```
> ```bash
> python scripts/outbox_triage.py --finish-stranded --apply
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> ④ 드라이런   「finished but PENDING: N」 과 종류별 줄 — 스케줄러가 예전에 상태 없이 빼 둔 줄입니다
>             N 이 0   치울 것이 없습니다. --apply 를 안 돌려도 됩니다
>             N > 0    --apply 가 그 N 줄을 SUCCESS + 지금 시각으로 찍고, 알림 청소가 곧 가져갑니다 (이 박스: 24 줄, 몇 초 안에)
> ⑤ 어드민 Chain 대기열 머리   「Loop Unknown · Mapper never reloaded · No loop in this process」 가 «안» 나와야 합니다
>             나오면   체인 워커가 옛 코드이거나(재기동 안 먹음) 워커 heartbeat 가 60 초 넘게 멎었습니다
>             Log 줄은 체인 워커의 로그 이름(chain_worker.log)입니다 — API 의 server.log 가 아닙니다
> ```
>
> ### 되돌릴 수 있나
>
> ```
> ④ --apply 는 «되돌릴 수 없습니다» — 그 줄들의 PENDING 이 SUCCESS 로 바뀌고, 처리 시각은 «이 명령을 돌린 때»입니다
>    (실제로 끝난 시각은 처음부터 안 적혀 있었습니다). 지우는 것은 없습니다. 그 줄들은 7일 청소로 원래대로 사라집니다
> 코드  git revert 00c0bad6a 191c0b54a c28ab7ad9  (새것부터) 하고 재기동
> ```

---

> ## 🔴 [09-25 오후] **원장 소스는 «뷰»를 안 읽습니다 + 그리드에 Ledger 열 — 마이그레이션 «없음» · 소급 «없음» · 재기동 «필요»**
>
> 소유자 「소급은 하지 말고 그냥 걷어내 · 운영에서는 뷰 안 써」. 원장 소스는 `row_id` 가 있는 «표»만 읽습니다.
> 뷰를 읽는 소스는 로드 때 «그 소스 하나만» 빠지고 나머지는 섭니다.
>
> ```
> ① 마이그레이션   없습니다. 소급도 없습니다 — 이미 뷰 소스로 들어간 원자는 그대로 둡니다
> ② config        제품은 안 건드립니다
> ③ 재기동        API 와 워커 둘 다. 메인 그리드는 새로고침 — 새 번들 main-DWdsueZG.js
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> ㉠ 재기동 뒤 로그에서 이 두 줄이 «0 줄»이어야 합니다
>      ERROR [Ledger] source <이름> is NOT planned: bundle.sources.<이름>.relation source '<이름>' reads '<관계>',
>        which is not a table that has row_id (view); a ledger source must read a table that has row_id
>      ERROR [Ledger] <이름> is NOT read: ...
>    있으면   그 소스가 뷰를 읽고 있습니다. 그 소스 «하나만» 빠졌고 나머지는 섭니다
>            고치려면 그 소스의 relation 을 row_id 가 있는 표로 (소유자 config)
>    🔴 소스가 «전부» 거절되면 원장 전체가 서지 않습니다 — 「every declared source was refused, so nothing would be read」
> ㉡ 메인 그리드 열 목록 «맨 끝»의 Ledger 칸
>      소스 이름   그 소스가 이 행을 원장에 올렸습니다
>      Not yet    아직 안 올렸습니다 — 원장이 따라오면 이름으로 바뀝니다
>      Refused    이 표를 읽는 소스가 «전부» 로더에서 거절됐습니다 — 사유는 ㉠ 의 줄
>      Unknown    소스인지 · 올라갔는지 알 수 없습니다 (선언이나 색인을 못 읽음)
>    원장 소스가 아닌 표에는 Ledger 열이 없습니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 토글이 없습니다 — 갈래를 «지운» 것이라 켜고 끌 축이 없습니다
> 되돌리려면  git revert 8def5f28e 2fbe12b3f 9653f3e6b c193986a8  하고 재기동 + 그리드 새로고침
>            임시 복제본에서 쟀습니다: 새것부터 · 옛것부터 둘 다 충돌 0
> ```

---

> ## 🔴 [09-25] **조인 선언의 `on` 이 «원천»으로 — 배포 직후 옛 모양 조인은 거절됩니다 · Chain 탭에서 조인마다 버튼 한 번**
>
> 소유자 「붙일 값을 고쳐야 트리거 시켜서 그걸 붙이지」. 조인도 mapper·decide 와 같은 문장입니다 —
> `on` = 값이 바뀌는 표(원천), `into` = 붙는 표. `derive.join.right_table` 은 없어졌습니다.
>
> ```
> ① 마이그레이션   없습니다
> ② config        제품은 안 건드립니다. 다만 derive.join.right_table 이 적힌 조인은 재기동 «직후» 거절됩니다
>                 (그 규칙 하나만 빠지고 나머지 규칙은 섭니다)
> ③ 재기동        API 와 체인 워커 둘 다 (API: 선언창 · 변환 문 / 워커: 로더). 어드민은 새로고침 — 새 번들
> ④ 할 일         재기동 «바로 뒤», 조인마다:
>                   Chain 탭 → 그 조인 열기 → 「To new join shape」 한 번 → 확인창에서 확인
>                 재기동과 ④ «사이»에 원천 표를 고쳤다면, 변환 뒤 원천 표 그리드에서 «선언 이름»으로 소급 한 번
>                   (거절된 동안의 수정은 into 표에 안 붙었습니다 — 소급이 붙입니다)
> ```
>
> ### 거절 문장 — 체인 워커 로그 `ERROR [ChainRules] …`
>
> ```
> <이름>: derive.join.right_table is retired - on names the table whose value changes.
>   Set on.table to "<원천>" and delete right_table (the Chain tab's convert does both)
>    뜻   옛 모양입니다 — ④ 의 버튼 한 번이 두 칸을 다 고칩니다
> <이름>: a join needs on.table - the table whose value changes
>    뜻   on 이 비었습니다 — 원천 표 이름을 on.table 에
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> ㉠ Chain 탭에서 조인을 열었을 때 변환 버튼의 글자
>    To new join shape   옛 모양입니다 — 누르십시오
>    To flat             이미 새 모양입니다. 🔴 누르지 마십시오 — 평면 규칙이 되고 :target 짝이 사라집니다
>    통합으로 · 평면으로   옛 번들입니다 — 새로고침
> ㉡ 체인 워커 부팅 줄 [ChainRules] set(N): 에 조인마다 «둘»
>      <이름>[decl,join] target_table=<붙는 표> trigger_table=<원천>
>      <이름>:target[decl,join] target_table=<붙는 표> trigger_table=<붙는 표>
>    하나뿐이면  짝이 없습니다 — on 과 into 가 같은 표면 정상, 아니면 「To flat」 으로 평면이 된 것입니다
>    없으면     거절된 것입니다 — 같은 로그의 ERROR [ChainRules] <이름>: 줄
> ㉢ 원천 행 하나의 값을 고치면 붙는 표의 같은 키 행이 그 값이 됩니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 토글이 없습니다
> 되돌리려면  git revert 2a9d8e18c 7c94fdc65 f4300aa19 244d825dc  하고 재기동 — «이 순서로» (새것부터)
>            임시 복제본에서 쟀습니다: 이 넷을 새것부터 충돌 0 · (문서 커밋 뺀) 셋을 옛것부터 충돌 1
>            🔴 이미 변환한 조인은 옛 코드가 «거절하지 않고» 세웁니다 — 다만 원천을 모르는 채로
>               (엔진이 읽는 right_table 이 비어 있음 · 돌 때 무엇이 되는지는 안 쟀습니다)
>               되돌리면 변환한 조인마다 원문을 손으로: on.table <- 붙는 표 · derive.join.right_table <- 원천
> ```

---

> ## 🔴 [09-24 밤] **`enrichment_rules.json` 은퇴 — 마이그레이션 «없음» · 재기동 «필요» · 🔴 재기동 «전» 확인 하나**
>
> 인리치(결손 보정) 선언의 집이 «하나»가 됐습니다 — `server/config/chain_rules.json` 의 `derive: {kind: "decide"}`.
> 제품은 `server/config/enrichment_rules.json` 을 «어디서도» 읽지 않습니다. 다시 놓아도 아무 일도 안 일어납니다.
>
> ```
> ① 마이그레이션   없습니다
> ② 재기동        필요합니다 — 로더·소급·설정 보고가 바뀌었습니다 (위 09-23 절의 «먹는 방법» 그대로)
> ```
>
> ### 🔴 재기동 «전»에 — 이 설치에 `server/config/enrichment_rules.json` 이 있습니까
>
> ```
> 없다       할 일 없습니다. 이 박스가 그렇습니다 (소유자 박스엔 그 이름의 파일이 없고,
>           enrichment_rules2.json 은 제품이 원래 안 읽던 이름입니다)
> 있다       🔴 재기동하면 그 안의 규칙은 «오류 없이» 멈춥니다. 재기동 «전»에 규칙마다
>           chain_rules.json 의 "rules" 에 한 항목으로 옮기십시오:
>              source_table  -> "on":   {"table": ...}
>              derived_table -> "into": {"table": ...}
>              decision_key  -> "derive": {"kind": "decide", "decide": {"key": [...],
>              target_fields ->                                    "fields": [...],
>              나머지 칸(list_columns · aggregations · reference_views · auto_confirm · alignment)
>                             -> 같은 이름으로 "decide" 안에
>              enabled       -> 항목의 최상위
>           키 표: docs/guide/config/chain_rules.md §5-B-bis
> ```
>
> ### 확인 셋 — 답이 «무엇을 뜻하나»
>
> ```
> ㉠ 체인 워커 부팅 줄 [ChainRules] set(N): ... 에 옮긴 규칙이 «둘씩» 보여야 합니다
>      enrichment_dedup:<이름>[decl,decide] · enrichment_auto_confirm:<이름>[decl,decide]
>    없으면   그 선언이 거절된 것입니다 — 같은 로그의 ERROR [ChainRules] <이름>: ... 가 사유입니다
> ㉡ 어드민 설정 해석 보고의 Enrichment 칸 출처가 chain_rules.json 이어야 합니다
>    (전에는 enrichment_rules.json 을 들고, 그 파일이 없으면 「규칙이 하나도 없습니다」라고 말했습니다)
> ㉢ 소급(backfill) 이 규칙을 못 찾으면 이제 이렇게 말합니다:
>      rule '<이름>' is not declared in chain_rules.json; available rules: ...
>    뜻   그 이름의 derive.decide 선언이 없습니다. «파일이 없다»는 말은 더 이상 안 나옵니다
>    대신 rule '<이름>' cannot be looked up: chain_rules.json could not be read (...) 가 나오면
>    뜻   선언이 없는 게 아니라 chain_rules.json 이 «깨져» 있습니다 — 파일부터 고치십시오 (09-25 추가)
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 토글이 없습니다 — 두 번째 문을 «지운» 것이라 켜고 끌 축이 없습니다
> 되돌리려면  이 착지 커밋을 git revert 하고 재기동
> ```

---

> ## 🔴 [09-23 저녁] **운영 장애 수리 — 마이그레이션 «없음» · config 변경 «없음» · 재기동 «필요»**
>
> 「선언은 섰고 체인은 돌았는데 행 추가만 안 되던」 것을 고쳤습니다.
> 판단키 한 칸이 비면 파생 행을 «안 만들고» 넘어가던 갈래를 지웠습니다.
>
> ```
> ① 마이그레이션   없습니다
> ② 소유자 config  안 건드렸습니다. 한 줄도 고치실 것 없습니다
> ③ 재기동        🔴 `run_app.bat` 은 «이미 떠 있으면 아무것도 안 합니다» (총괄 실측:
>                두 번 돌렸는데 다섯 프로세스 전부 옛 코드 그대로였습니다)
>                먹는 방법: 체인 워커 프로세스를 «내리면» 감독자가 새 코드로 띄웁니다
>                확인: `/health` 의 `workers.chain.pid` 가 «바뀌었나` · `restarts` 가 늘었나
>                🔴 체인 워커가 «옛 코드»로 돌고 있습니다 — 재기동 전에는 안 고쳐집니다
> ```
>
> ### 무엇이 달라지나 — 세 줄
>
> ```
> 전   판단키가 일부 빈 소스 행 -> 파생 행이 «안 생김». 경고는 로그에만
> 후   그 행도 파생됨. 정체성은 «표가 선언한 컴포짓키»로 지어집니다 (전과 같은 철자)
> ⚠️  빈 성분은 «키를 짓는 데»만 씁니다 — 기존 행의 «값을 덮지 않습니다»
> ```
>
> ### 🔵 소급 «없습니다» — 이미 있는 파생 행은 안 움직입니다
>
> ```
> 정체성 철자가 한 글자도 안 바뀌므로 옛 이름 행이 «두 벌»이 되는 일은 없습니다
> 새로 생기는 것은 «전에 거절당하던» 행뿐입니다
> ```
>
> ### 확인 셋 — 답이 «무엇을 뜻하나»까지
>
> ```
> ㉠ 재기동 뒤 체인 워커 로그에서 «이 줄이 더는 안 나와야» 합니다
>    server/chain_worker.log
>      「row(s) with a PARTIAL decision key were NOT derived」
>    나오면   재기동이 안 먹은 것입니다 (옛 프로세스가 살아 있습니다)
>    안 나오면 고쳐진 것입니다
>
> ㉡ 그리고 대신 이 줄의 «뒤 숫자»를 보십시오 — 같은 줄에 있습니다
>      「N source row(s) -> M unique decision key(s) upserted into '<표>'
>        (K of them on a PARTIAL decision key)」
>    K 가 «0보다 크면» 전에 버려지던 행이 지금 들어가고 있는 것입니다
>
> ㉢ 🔴 새로 생긴 줄 하나 — 이것이 나오면 «선언을 보셔야» 합니다
>      「N decision key(s) were NOT derived: every column that BUILDS the identity of
>        '<표>' is blank on them」
>    뜻   그 행들은 파생 표에서 «주소가 없습니다». 만들면 나중에 갱신도 회수도 못 합니다
>    할 일 그 표의 composite_key_source (없으면 business_key) 가 가리키는 «그 컬럼»이
>          소스에서 왜 비는지 보십시오. 코드가 대신 정해 줄 수 없는 자리입니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 이 수리에는 토글이 없습니다 — 갈래를 «지운» 것이라 켜고 끌 축이 없습니다
> 되돌리려면  git revert 2b37dcbd  하고 재기동
> ⚠️ 되돌리면 「행 추가가 안 되는」 증상이 그대로 돌아옵니다
> ```
>
> ```
> 착지  2b37dcbd  (시험 포함 7 파일 · 회귀 309 통과 · 변이 증명 있음)
> ```

---

> ## [09-24 · 서버] 체인 스켈레톤이 목록은 «목록», 참거짓은 «체크박스»라고 말합니다 — `90b9f4437` · API 재기동 필요
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드렸습니다
> ③ 재기동        API 프로세스 — 선언창의 모양(스켈레톤)은 API 가 «돌면서» 냅니다. 새로고침만으로는 안 바뀝니다
> ```
>
> ### Chain 탭에서 inventory_confirmed 의 on · take 가 어떻게 보이나 — 그 답의 뜻
>
> ```
> 빈 입력칸                 옛 번들입니다 — 아래 [09-24 · 화면] 의 ㉠ 부터
> [{"left":…}] 같은 글자     새 번들 · «옛 API» 입니다 — API 재기동 전
> 「접힘 · N」 목록           새 번들 · 새 API 입니다 — 눌러서 펴지고 「+」·「−」로 고칩니다 (aac2e1bac)
> key.unique 가 체크박스     새 API 입니다
> into 드롭다운에 table 만     새 API 입니다 (09-25) — read 가 보이면 옛 API, 재기동 전입니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> git revert 90b9f4437  -> API 재기동   목록이 다시 «글자»로 보입니다(값은 보이되 폼에서 못 고침)
> ```
>
> ## [09-24 · 화면] 체인 선언창의 목록이 «펴지고» 고쳐집니다 — 마이그레이션 없음 · 새 번들
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드렸습니다
> ③ 돌릴 것        없습니다. 어드민 페이지를 «새로고침» 하십시오 — 번들 파일 이름이 바뀌었습니다
> ```
>
> ### 무엇이 달라지나
>
> ```
> 전   on · take 가 「접힘 · 2」 · 「접힘 · 3」 으로 그려지고 눌러도 안 펴졌습니다. 「+ pair」 도 무반응
> 후   누르면 펴지고, 항목을 고치고 · 「+」 로 더하고 · 「−」 로 뺄 수 있습니다
> 덤  「+」 뒤 「−」 로 원래대로 돌리면 초안이 안 남습니다 — 다음에 열어도 「복원」이 안 뜹니다
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> ㉠ 개발자도구 Network 에서 admin-*.js 의 «이름»을 보십시오
>    admin-WsUDTkwl.js  새 번들이 떴습니다
>    다른 이름    옛 번들이 캐시에 남았거나 배포가 안 된 것입니다 — 화면은 안 바뀝니다
> ㉡ Chain 탭 → inventory_confirmed → on 의 「접힘 · 2」 «한 번»
>    left · right 칸에 dt_job 이 보이면  고쳐진 것입니다
>    눌러도 안 펴지면                  옛 번들입니다 (㉠ 부터)
> ㉢ 같은 번들에 09-23 수리도 실려 있습니다 — 끝난 enrichment backfill 줄에
>    「not created - no decision key N」 같은 칩이 보이면 그 수만큼 «안 만든» 것입니다 (0 도 그대로)
> ㉣ 인리치 목록 아래 메모가 「Edit rules in the Chain tab (derive.decide)」 이면 은퇴한 파일 안내가 빠진 번들입니다
>    「server/config/enrichment_rules.json 수기 편집」 이 보이면 옛 번들 — 그 파일은 이제 아무도 안 읽습니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 없습니다 — 화면이 «받는» 클릭만 늘었고 토글할 축이 없습니다
> 되돌리려면  git revert 4335f209c 2cdb1e74f aac2e1bac  하고 다시 배포 — 셋을 «이 순서로» (새것부터)
>            ⚠️ 옛것부터 돌리면 첫 단계에서 충돌합니다 — 임시 트리에서 둘 다 돌려 봤습니다:
>               옛것부터 충돌 파일 4 · 새것부터 0
>            되돌리면  목록이 다시 «안 펴집니다»(값은 원문 JSON 에서만) · 은퇴한 파일 안내 문장도 «다시» 나옵니다
> ```
