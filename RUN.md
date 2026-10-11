# 지금 돌리면 되는 것

> ## [10-11 일요일] **셋업 명령표 — 위에서부터 그대로 친다 · 시연 선언은 맨 아래 (응용 · 리허설 af8ef5701 -> 355ba2092)**
>
> ```
> 리허설       운영 런처(서버 · 수집기 · 체인 워커 · 스케줄러). 소유자 코드(af8ef5701)로 꼬임을 만들고, ① 에서 355ba2092 로 pull 한 뒤
>              이 표의 명령을 순서대로 두 바퀴. 꼬인 dt_log 모양 220 행 —
>              한 칩 두 이벤트 10 · 좌표 빈 행 5 · 수동 잡 5 · 인벤토리 칸이 옛 chain_ingestion 층(틀린 값)에 덮임 · 옛 판 소스 원자 215
>              초 = 명령이 돌아올 때까지(리허설 · 박스). 운영 크기의 초가 아니다. replay 의 «rows handed over» 뒤 체인이 쓰는 시간은
>                   이 초 밖이다 — chain_worker.log 의 [ChainRule] rule=<규칙> … rows_in= 줄이 그 끝
>              지금 main 도 같은 명령: git diff --name-only 355ba2092 origin/main -- server/ ':!server/tests' -> ledger/config_explorer.py · ledger/gaps.py · ledger/trace_router.py · ledger_api/ledger_subgraph.py — 이 표의 명령이 부르는 파일은 그 안에 없음
> 어디서       server 폴더(cd server) · PowerShell 창에 «직접» 친다
>              ⚠️ 출력을 파이프(|)나 파일(>)로 받지 않는다 — 리허설에서 fold-rows 미리보기가 '«'(U+00AB) 를 cp949 로 못 써서 죽었다(exit 1).
>                 받아야 하면 먼저  $env:PYTHONIOENCODING = "utf-8"   (창에 직접 친 경우는 이 박스에서 못 쟀다)
> 이름         리허설 이름                     운영에서 — 소유자가 채운다
>              dt_log                          «로그 표»
>              official_dt                     «공식 표»
>              dt_inventory_core_xy            «인벤토리 식 규칙»          (맵퍼가 적던 층 이름 dt_inventory -> «옛 층 이름»)
>              official_dt_copy                «복사 규칙»
>              dt_log (원장 소스)               «옛 판 소스»               official_dt (원장 소스) -> «공식 표 소스»
>              core_wafer,core_x,core_y        «공식 표 키 칸»             event_time · dt_job_id · AUTO -> «고를 칸» · «범위 칸» · «범위 글자»
> ```
>
> ```
> ⓪ 재기동 전 선언   table_config.json   «로그 표» 에 "fold_mark": "string"
>                   chain_rules.json    «복사 규칙» 에 "exclude": ["fold_mark"]
>                   ontology/ledger_config.json   transfer 소스는 «공식 표»를 읽고, «옛 판 소스» 이름은 sources 에 없다
> ① git pull -> 서버 · 수집기 · 체인 워커 · 스케줄러 재기동                                   재기동 뒤 기다리는 사건 0
>    볼 줄   chain_worker.log  [ChainRules] dt_inventory_core_xy: source_name 'dt_inventory' is written as chain_ingestion
>            «인벤토리 식 규칙»이 맵퍼를 mapper_module · mapper_function 으로 적었으면 이 줄은 0 개(값은 ③ 에서 그래도 바로잡힘 · 237d313db)
>    기동 중 메인 화면 뱃지 «CHAIN: STARTING» · 그 title «starting: <단계>, N s» — 1 분 넘어도 그 단계 중이면 정상 (e032d526e)
>            리허설: 단계 하나(ensure_human_claims_index)를 92 s 붙잡아도 내내 starting · foreign_beat 0
>    기동 끝 chain_worker.log «[Chain] startup <합> s - <단계> <초> s · …» — 가장 긴 단계가 «왜 오래 걸렸나»의 답
>    ⓪ 의 새 칸 재기동 때 체인 워커가 «starting: sync_dynamic_tables_schema» 단계에서 ALTER 한다. 그 표를 다른 연결이 쥐고 있으면 넘어간다:
>            chain_worker.log «column '<칸>' was not added to '<표>' - another session held the table past 20s. Retried at the next start or config save»
>            이 줄이 있으면 ⑤ 전에 체인 워커를 한 번 더 재기동 — 리허설(5b-2 40d94309b): 붙잡은 ALTER 가 칸 없이 넘어갔다(그 단계 36.1 s)
> ①b 비어 버린 보류 다시 세기  python scripts/chain_replay_cli.py replay «다시 세기 규칙»   -> --apply          2.2 · 2.9 초
>    까닭    pull 전 코드는 원천 키 칸과 공식 표 키 칸의 형이 다르면 보류를 오류 없이 빈칸으로 덮었다(7a 5777da3c4 가 고침)
>    답      source rows scanned : N · rows handed over : N (리허설 205) — 다시 세기 규칙마다, 그 규칙의 공식 표 전부
>    뜻      리허설(공식 표 키 글자 · 로그 표 숫자): pull 전 agreed 0 -> 이 명령 뒤 39 = 같은 꼬임의 같은 형 세계 39 (03c31a6e6)
>            이 표의 공식 표는 ⑥ 이 다시 채운다 — 이 줄은 ⑥ 을 안 돌리는 다른 공식 표에. 멈춤은 ③ 과 같다(안 쟀다)
> ② 쌓인 회수 사건 접기       python scripts/chain_replay_cli.py fold-withdraw-events       -> --apply          1.8 · 2.7 초
>    답      «No waiting withdrawal event goes row by row - 0 row(s)» 면 접을 것 없음
>    멈춤    소급 탭 × — 쪽 사이에서 선다
> ③ 좌표 바로잡기             python scripts/chain_replay_cli.py replay «인벤토리 식 규칙»   -> --apply          2.3 · 3.0 초
>    답      미리보기 source rows scanned : 220 · 실행 rows handed over : 220
>    뜻      core x,y 가 chain_ingestion 자리에 새 값 — 맞는 행 43 -> 215 / 215
>            공식 표는 이 단계에서 안 움직인다(보류 agreed 39 -> 39) — 스크립트 replay 는 연쇄하지 않는다(소유자 09-26). ⑥ 이 그 일
>    멈춤    소급 탭 실행 목록의 Cancel(10-08 «일 하나를 끈다») — 이 리허설에서는 안 쟀다
> ④ (골라서) 옛 층 이름 거두기  python scripts/chain_replay_cli.py withdraw «로그 표» «옛 층 이름» --columns core_x,core_y   -> --apply    1.6 · 2.3 초
>    답      칸마다 «(now from 'chain_ingestion'; remaining ['chain_ingestion'])» — 보이는 값은 그대로
>    멈춤    안 쟀다
> ⑤ 접기 표시                 python scripts/chain_replay_cli.py fold-rows «로그 표» --keys «공식 표 키 칸» --order «고를 칸» --mark-column fold_mark --only-column «범위 칸» --only-text «범위 글자»   -> --apply    2.2 · 3.0 초
>    답      미리보기 «10 row(s) are marked, 210 stay» · 키 칸 빈 행 5 그대로 / 실행 «10 of 10 row(s) marked» · 범위 밖 5 그대로
>    뜻      지운 행 0 — 표시된 행은 «복사 규칙»이 안 받고, 그 행이 먹인 층을 거둔다(보류 agreed 39 -> 45)
>    되돌리기 fold_mark 칸을 비운다 · 멈춤 안 쟀다
> ⑥ 복사 replay               python scripts/chain_replay_cli.py replay «복사 규칙»          -> --apply          2.1 · 2.8 초
>    답      source rows scanned : 220 (표시된 행 포함 — 규칙이 거른다)
>    뜻      공식 표 보류 agreed 45 -> 205 · 껍데기 행 82 -> 0 · 공식 표 소스 원자 6 -> 205
>            일부 행만이면 --business-keys <«로그 표» 키,…> (표 키가 여러 칸이면 --row-ids)
>    멈춤    ③ 과 같음 — 안 쟀다
> ⑦ 남은 껍데기 쓸기           python scripts/chain_replay_cli.py remove-shells «공식 표»      -> --apply          1.5 · 2.4 초
>    답      «N row(s) of '«공식 표»' show nothing outside their keys; M of them have only the chain's key layers left» — M 이 지울 수
>    뜻      리허설: ① 직후 미리보기 M 82 · ⑥ 뒤 M 0(⑥ 이 다시 채움) · 실행 «0 of 0 row(s) deleted»
>            ⑥ 앞에서 쓸면 82 행을 지우고 ⑥ 이 다시 만든다(공식 표 123 -> 205 · 껍데기 판) — 그래서 ⑥ 뒤
>            그 뒤로는 체인이 지운다 — 그리드에서 원천 행을 지우면 그 공식 행이 «[ChainShell] table=official_dt rows_deleted=1 - only the chain's keys were left» 와 함께 사라지고
>            사람이 적은 칸이 있는 행은 남는다 · 소급 탭 «Remove rows with no source left» 의 count 가 이 미리보기와 같은 수(82)
>    멈춤    소급 탭 × — 쪽 사이(95cffa5af)
> ⑦b 원장 ref 인덱스           python scripts/build_ledger_ref_index.py                       -> --apply          1.0 · 1.1 초
>    답      미리보기 «ledger_events: 0 partition(s) built, 0 attached as they were, 0 already had it, 1 would be built, 0 attached as they are (add --apply) - the parent index is not valid yet» -> 실행 «ledger_events: 1 partition(s) built, 0 attached as they were, 0 already had it - the parent index is valid» · 다시 «ledger_events: 0 partition(s) built, 0 attached as they were, 1 already had it - the parent index is valid»
>            pull 전에 같은 이름을 SQL 로 지어 둔 원장도 «ledger_events: 0 partition(s) built, 0 attached as they were, 1 already had it - the parent index is valid» — 다시 안 짓는다 (7b e8baa5243)
>    뜻      ⑧ · ⑨ 의 로그 «idx_ledger_events_source_raw_ref_hash valid - 1000 refs a page». 없으면 50,000 장에 이 명령을 대는 줄(RUN.md 7b 절)
>    멈춤    안 쟀다 — 파티션마다 CONCURRENTLY 라 쓰기를 안 막는다(RUN.md 7b 절)
> ⑧ 옛 판 소스 거두기          python -m ledger.backfill --source «옛 판 소스» --whole-source   -> --apply          1.9 · 2.8 초
>    답      미리보기 relation_rows None(= 선언에 없는 이름) · stale_atoms 215 / 실행 stale_withdrawn 215
>    뜻      같은 코어 다이에 transfer 둘 123 -> 0
>            relation_rows 가 None 이 아니라 수면 ⓪ 에서 «옛 판 소스»를 sources 에서 안 뺀 것 — 그때 --apply 는 거두지 않고 다시 번역한다
>    멈춤    소급 탭 × — 쪽 사이에서 선다
> ⑨ 공식 표 소스 다시 번역      python -m ledger.backfill --source «공식 표 소스» --whole-source   -> --apply        2.0 · 3.1 초
>    답      미리보기 relation_rows 205 · stale_atoms 0 / 실행 «rows 205, withdrawn 205, written 205 of 205»
>    멈춤    소급 탭 × — 쪽 사이에서 선다
> 끝 상태      transfer 원자 205 = 기대 205 · 같은 코어 다이에 transfer 둘 0(처음 84) · 옛 판 원자 0 · 보류 agreed 205 · 껍데기 0
> 다시 돌리면   미리보기만 다시 — ② 0 row(s) · ④ cells withdrawn 0 · ⑤ «0 row(s) are marked» · ⑦ M 0 · ⑧ stale_atoms 0 · ⑨ stale_atoms 0 이면 끝 (리허설 둘째 바퀴 그대로)
>              replay 미리보기의 scanned 와 ⑨ 실행의 written 은 매번 같은 수다 — 0 신호가 아니다
> 착지 뒤 채움  없음 — 6 표 선언 인덱스는 시연 뒤(총괄 f9ebc82ea)
> ```
>
> ### 시연 선언 (월 10-12) — 위 셋업이 끝난 뒤
>
> ```
> 0  ledger_config.json 이 setup_version 5 이면 먼저   python scripts/migrate_ledger_config_to_v6.py --apply   (운영 판은 못 봤다)
> 1  ontology/ledger_config.json 의 sources 에서 mechanism_edge_to_quantity_causes · mechanism_edge_to_finding_causes 를 뺀다
>    python -m ledger.backfill --source <그 이름> --whole-source --apply          이름마다 · 옛 원자를 거둔다 · 3.3 · 3.1 초
> 2  선언 화면 «Empty» 로 세상 둘 — «모델 세상 1»(void_formation) · «모델 세상 2»(void_observation_bias)
> 3  config/ontology_worlds/<세상>/ledger_config.json — entities quantity · defect_kind · vocabulary leads_to · sources 에 1 의 두 소스를 그대로 두고 칸 둘만
>      "relation": "mechanism_edge"
>      "read": {"exclude_when": [{"when": {"to_role": "<다른 역할>"}}, {"when": {"model": "<다른 모델>"}}, …]}
>    python -m ledger.backfill --source <이름> --world <세상> --whole-source --apply   세상마다 · 이름마다 · 2.9~3.4 초
>    답      written — 세상 1 은 11 · 7 · 세상 2 는 1 · 0 (박스 mechanism_edge 사본 · f116890f9)
> 4  base 두 웨이퍼 id 를 여기에   불량 «______» · 양품 «______»      (박스 리허설은 SYN-BW-103-11 · SYN-BW-SPL-400-19)
> 대본 (걷기 화면 · 누른 것 -> 본 것 · 뜻) — 리허설 18766 = 박스 조각 + 가짜 행
>    빌드    main 의 dist walk-BR4Mc7Hx.js · 18766 서버 파일과 main 의 server/ 차이 database/database.py 한 줄 = 하니스가 스크래치 스키마를 거는 줄(ASSY_SCRATCH_SCHEMA)
>            누른 빌드 — walk-BR4Mc7Hx.js (= main) 에서 ①② · ① · ③ · ③ 칩 순서 · ③ 출처 · ④ · ④ 쪽 넘김 · ④ 점 출처 · ⑤ · ⑥ · ⑦ · ⑦ No more · ⑧ · ① 목록 밖 키 · ④ 쪽 점 출처 · ① 빈 걷기 표 · ③b 이어 걷기 · ③b 같은 표 · ③c 걸음 탭 · ③b · ③c 요청 · ③d 갈래 · ③e 구역 트렌드 · ③e 쪽 넘김 · ③e 다시 걸면 · ③f Control · B · ③f bonded_from 넣음 · ③ 복사
>    누름    마지막 판은 페이지 스크립트로 눌렀다 — 단추 · 칸 · 체크는 요소 클릭, 타자는 입력 칸에 값 넣기, 그래프의 노드 · 덩어리는 cytoscape tap
>            (이 박스의 브라우저 창이 그려지지 않아 좌표 클릭이 안 먹음. ① ③ ⑥ ⑦ ⑧ 은 앞선 판에서 진짜 클릭으로 눌렀을 때와 수가 같다)
>            «모델 세상 1» = 리허설의 appdemo_vf
>    ①  바구니   Type wafer · PICK A NODE 에 «불량» 앞글자 -> 목록(리허설 «SYN-BW-103-11 · 278 atoms»)에서 고름 -> Positive «+ Add» · «양품» 도 같이 -> Negative «+ Add» · Collect wafer -> Walk
>       본 것    제목 «+ 1 · − 1 → wafer» · «Nodes 32 (collect: wafer) · Edges 1650 (all) · 0.8 s» · 머리 «Positive · 1 start · 31 rows | Negative · 1 start · 1 row»
>       뜻       + 쪽 = 불량 base 에서 걸어 닿은 것 · − 쪽 = 양품 base 에서. 한쪽만 닿은 줄은 다른 쪽 칸 전부가 빨간 missing 한 칸
>       목록 밖 키  원장에 없는 키를 치면(리허설 «syn-bw-103-11» — 목록은 «SYN-BW-103-11 · 278 atoms») 바구니 밑에 «0 atoms · not in the ledger»
>                그대로 + Add -> Walk 하면 «Asked 12 hops · reached 0 hops · both» · 머리 줄 «empty · No ledger evidence is connected to the selected node»
>                표는 «Positive · 1 start · 1 row» 한 줄 «syn-bw-103-11 ¦ start» · 페이지 글에 «ledger-entity:» 0
>                뜻: 노드는 키가 정확히 같아야 같은 노드다 — 찾기는 대소문자를 안 가리지만 넣는 것은 목록의 줄을 골라서
>    ②  Route    표 양 끝 열 — + 쪽은 맨 왼쪽 · − 쪽은 맨 오른쪽
>       본 것    «start | missing» 1 (SYN-BW-103-11) · «missing | start» 1 (SYN-BW-SPL-400-19) · «in_container → bonded_from → in_container | missing» 30 (first SYN-CW-001-02)
>       뜻       Route = 서버가 그 쪽 시작에서 걸은 길(술어만 · 걷기 답 그대로) · «start» = 그 줄이 시작 · missing = 그 쪽에서 못 닿음
>                코어 웨이퍼 30 개가 «in_container → bonded_from → in_container» — 불량 base 의 다이가 본딩으로 받은 코어 다이의 웨이퍼
>    ③  세상 · 값 표   Collect 에 quantity 를 더함 · 세상 칩 «모델 세상 1» (누르면 그 세상만 켜짐 — Type 목록도 그 세상 것만) · 이어 default 칩 -> 저절로 다시 걷는다
>       본 것    «Nodes 81 (collect: wafer, quantity) · Edges 1668 (all) · 0.8 s» · quantity 머리 «Positive · 1 start · 49 rows | Negative · 1 start · 22 rows»
>                열 «Route · value_text · step · role · eqp_id · model · dir · model · dir · value · quantity · Δ · value · dir · model · dir · model · eqp_id · role · step · value_text · Route»
>                줄 49 · 두 쪽 값 16 · + 쪽만 25 · − 쪽만 2 · − 빨간 missing 27 · + «—» 8 · − «—» 4 · Δ 보이는 줄 5
>                pressure_MPa  + 0.22 | Δ −0.1105 | − 0.3305
>                Route «measures | measures» 16 · «measures | missing» 13 · «measures | measures → leads_to» 3 · «measures → leads_to | measures» 2 · «measures → leads_to | measures → leads_to» 1 · «in_container → bonded_from → in_container → measures | missing» 14
>       출처     값마다 밑에 «준 노드 · 그 쪽 길» — default 세상 · Collect quantity 만으로 누름: bond_temp + 값 «+2» -> «35.5» «SYN-BW-103-11 · start» · «21.5» «SYN-CW-103-01 · in_container → bonded_from → in_container» · «23.5» «SYN-CW-103-02 · in_container → bonded_from → in_container»
>                − 값 «13» «SYN-BW-SPL-400-19 · start» · 출처 줄 258 개 중 «ledger-entity:» 0
>       뜻       한 줄 = 한 계측군 · 빨간 missing = 그 쪽 base 가 그 계측군에 못 닿음 · «—» = 닿았는데 값이 없음 · 값이 여럿이면 첫 값과 «+N»(누르면 펼침)
>                Route «measures → leads_to» = 모델 세상의 leads_to 를 한 번 더 걸어 닿은 계측군
>                출처 = 그 값을 준 노드(선언된 키 순서)와 그 쪽 시작에서 그 노드까지 서버가 걸은 길 — 코어 웨이퍼 값이 base 값과 섞여도 누구 것인지 보인다
>                칩 순서는 답을 안 바꾼다 — 리허설 «모델 세상 1» 먼저든 default 먼저든 노드 81 · 엣지 1668, 노드와 엣지 전부 같음
>       복사     구역 머리 «Copy table» — 소유자 손 클릭으로(스크립트 클릭은 «Copy failed · Select the table and press Ctrl+C» 를 띄우고 아무것도 안 씀)
>                리허설(default · Collect quantity) «Copied 48 rows» · 클립보드 TSV 49 줄 × 15 칸(머리 줄 · 마지막 칸 id) + HTML 표
>                트렌드의 «Copy points» -> «Copied 1000 points» · TSV 1001 줄 × 5 칸 «time | value | side | node | claim_id»
>    ③b 이어 걷기   표에서 줄을 체크하고 NEXT 의 «measures → wafer» (리허설: SYN-BW-103-11 만 + · Collect quantity · bond_temp 체크)
>       본 것    요청 하나 node_limit=1000&hops=1&follow=measures&collect=wafer&direction=both · «Nodes 64 (collect: wafer) · Edges 64 (all) · 0.1 s» · 머리 «Positive · 1 start · 64 rows» · 열 «wafer · value · eqp_id · role · step · Route» · 줄 64
>                첫 줄 «FAKE-W-001 ¦ 22.791 bond_temp · start ¦ FAKE-EQP bond_temp · start ¦ fake bond_temp · start ¦ FAKE-HIST bond_temp · start ¦ measures»
>       같은 표  bond_temp 하나만 + · Collect wafer · Follow measures · both · hops 1 · Walk -> 머리 · 열 · 줄 수 · 첫 세 줄이 같음
>       뜻       이어 걷기 = 체크한 줄을 시작으로 한 바구니 걷기 — 한쪽 표 하나. 폼의 node_limit 을 같이 싣는다(③c 의 요청 7 개 전부 node_limit=1000 · fanout_limit 은 폼 칸이 비어 안 실림 — 채운 경우는 안 쟀다)
>    ③c 걸음 탭   이어 걸을 때마다 탭이 하나씩 — 제한 없음 (리허설: SYN-BW-103-11 만 + · Walk · in_container → die / → wafer 를 번갈아 다섯 번)
>       본 것    탭 6 «Step 1 · + 1 | Step 2 · in_container → die | Step 3 · in_container → wafer | Step 4 · in_container → die | Step 5 · in_container → wafer | Step 6 · in_container → die»
>                여섯째 표: 체크 전 NEXT 꺼짐 «Check rows first» -> 한 줄 체크 -> «bonded_from → die(on) · in_container → wafer(on) · inspected → wafer(on) · observed → defect(on) · transfer → die(on)»
>       앞 걸음  탭 «Step 2 · …» 를 누르면 그 걸음의 체크가 그대로 -> 그 NEXT -> 탭 3 «Step 1 · + 1 | Step 2 · in_container → die | Step 3 · in_container → wafer» — 뒤 탭은 지워진다
>       뜻       걸음마다 자기 마킹(이름은 순번)에 체크가 남는다. 앞 걸음에서 다시 이어 걸으면 그 뒤 걸음과 그 마킹이 같이 지워진다
>    ③d 갈래   한 걸음에서 다른 엣지로 이어 걸으면 탭이 나란히 선다 (리허설: SYN-BW-103-11 만 + · wafer 줄 체크)
>       본 것    NEXT «in_container → die» -> «Nodes 179 (collect: die) · Edges 179 (all) · 0.2 s» · 탭 «Step 1 · + 1 | Step 2 · in_container → die»
>                탭 Step 1 (체크 그대로) -> NEXT «measures → quantity» -> «Nodes 32 (collect: quantity) · Edges 32 (all) · 0.1 s» · 탭 «Step 1 · + 1 | Step 2 · in_container → die | Step 2 · measures → quantity»
>                Step 1 에서 «in_container → die» 를 다시 -> 탭 «Step 1 · + 1 | Step 2 · in_container → die | Step 2 · measures → quantity» 그대로
>       뜻       걸음은 나무다 — 같은 걸음의 다른 엣지는 형제 갈래로 남는다(F 의 «뒤 탭 지움»은 같은 갈래 안에서만)
>                graph per branch: pending — 그래프는 아직 두 갈래를 같게 그린다(모든 술어로 걷는다). 고치는 일은 주문됨
>    ③e 구역 트렌드   표의 구역 머리마다 Table | Trend — Trend 를 누르면 그 구역 줄 전부의 값이 한 그림 (리허설: ③b 의 bond_temp -> wafer · 64)
>       본 것    요청 하나 id=<bond_temp>&follow=measures&direction=incoming&hops=1&around=2026-12-23T18:49:00.000Z&page=1000 · «wafer · 64 · measures · value» «64 points · 2026-10-25 03:49 → 2026-12-24 03:49 local time» · 점 64 개 전부 title «<wafer> · measures»(첫 «FAKE-W-001 · measures»)
>                Load earlier «Nothing earlier» · Load later «Nothing later» — 점이 64 개뿐
>       쪽 넘김  같은 길을 점이 많은 local_gap 으로 -> «1000 points · 2026-11-11 09:35 → 2026-12-24 03:49 local time» -> Load earlier -> «1402 points · 2026-10-25 03:49 → 2026-12-24 03:49 local time» · 그 단추 꺼짐 «Nothing earlier»
>       뜻       시간 쪽은 그 구역 줄들의 값이 모이는 노드(여기서는 bond_temp · local_gap)에서 묻는다 — 줄마다 묻지 않는다
>       다시 걸면  Trend 를 연 채 앞 걸음에서 다른 줄(local_gap)로 같은 NEXT -> 그 줄의 시간 쪽을 새로 묻는다 -> «1000 points · 2026-11-11 09:35 → 2026-12-24 03:49 local time» · 걸은 점 102 · 쪽 점 898 · 옛 쪽 점 0
>                (밤사이 응용 QA 로 고침 6d6e235e0 — 시간 쪽은 그 노드 · 열의 것)
>    ③f Control · B   Follow 밑의 두 번째 술어 목록 — 고르면 Walk 가 같은 바구니로 한 번 더(follow = B) 걷고 칸을 칠한다
>                (리허설: «모델 세상 1» + default · void 혼자 + · Collect quantity · Follow = leads_to 뺀 전부 · B = leads_to)
>       본 것    요청 둘 · bonded_from 뺌: «quantity · 35» · «Positive · A only 17 A + B 15 B only 3» · 초록 줄 backside_damage Route «of_kind → observed → in_container → measures / B · leads_to» · 빨강 줄 wetting_deficit Route «— / B · leads_to»
>                bonded_from 넣음: «quantity · 49» · «Positive · A only 31 A + B 15 B only 3»
>       뜻       초록 = A 와 B 둘 다 닿음 · 빨강 = B 만 · 색 없음 = A 만. Route 는 두 줄 — A 의 길 / B 의 길
>                bonded_from 을 Follow 에 넣으면 A 만 줄이 는다(리허설 17 -> 31) · A + B · B only 는 같다 — 넣을지는 물음에 따라 고른다
>    ④  트렌드   ③ 표의 값 칸을 누름(리허설: pressure_MPa 의 + 값)
>       본 것    요청 하나 id=<id>&follow=measures&direction=incoming&hops=1&around=2026-08-11T16:40:00.000Z&page=1000&world=appdemo_vf&world=default · 73 ms · «pressure_MPa · measures (in) · value» «5 points · 2026-08-10 01:00 → 2026-08-12 01:40 local time» · 걸은 점 2 개에 고리
>                Load earlier 꺼짐 «Nothing earlier» · Load later 꺼짐 «Nothing later» — 리허설에 그 계측군 점이 그것뿐
>       쪽 넘김  점이 많은 계측군(리허설 가짜 행 local_gap)의 + 값 «53» 을 누름 -> «1000 points · 2026-11-02 18:42 → 2026-12-15 12:55 local time» · Load earlier · Load later 켜짐
>                Load earlier -> «1201 points · 2026-10-25 03:49 → 2026-12-15 12:55 local time» · 그 단추 꺼짐 «Nothing earlier» · Load later -> «1402 points · 2026-10-25 03:49 → 2026-12-24 03:49 local time» · 그 단추 꺼짐 «Nothing later»
>                요청마다 page=1000 · 219 ms · 86 ms · 90 ms
>       점 출처  bond_temp + 값을 누름 -> «bond_temp · measures (in) · value» «64 points · 2026-10-25 03:49 → 2026-12-24 03:49 local time» · 걸은 점 4 개마다 title 에 ③ 의 출처 그대로
>                쪽으로 온 점: local_gap 를 누르면 걸은 점 2 · 쪽 점 998 개 전부 «<키> · not in this walk»(리허설 «FAKE-W-002 · not in this walk») · raw id 0
>       뜻       누른 쪽의 걸은 시각 근방 1,000 점이 먼저 · Load earlier / Load later 가 1,000 점씩 넓힌다 · 꺼짐 글씨 = 그 쪽에 더 없음
>                주황 Positive · 청록 Negative · 회색 다른 줄 · 점선 = 걸은 시각
>    ⑤  그래프   Graph
>       본 것    «Nodes 69 · Edges 136» · «Folded · 2 nodes» · 작은 덩어리 SYN-BW-103-11 «← in_container +159 more die» · SYN-BW-103-11 «inspected → +18 more die» · SYN-BW-103-11 «measures → +12 more quantity» · SYN-BW-SPL-400-19 «← in_container +27 more die» · SYN-BW-SPL-400-19 «inspected → +27 more die»
>       뜻       그래프는 표와 따로 걷는다 — 요청 표 «node_limit=1000&collect=wafer&collect=quantity&world=appdemo_vf&world=default» · 그래프 «fanout_limit=20&world=appdemo_vf&world=default» — 그래서 Nodes 수가 표와 다르다
>                «+N more die» = 서버가 안 보낸 묶음, N 개가 더 있다는 말만 왔다
>    ⑥  묶음 열기  불량 base 의 «← in_container +159 more die» 를 누름 -> 창 «in_container · die» «159 not drawn · from SYN-BW-103-11» -> 다이 하나 틱 -> «Open 1»
>       본 것    그려짐 1 · 다른 노드 움직임 0 · 그 다이에 점선 큰 덩어리 «? next · not walked» · 묶음은 «← in_container 158 more die»
>       뜻       묶음에서 연 노드는 서버가 그 노드에서 걸은 적이 없다 — 점선이 그 말이다
>    ⑦  not walked   그 점선을 누름
>       본 것    요청 1 개 (hops=1&direction=both&world=appdemo_vf&world=default) · 덩어리 «? next · not walked» · 창 «From SYN-BW-103-11 / 1 / 6 / Wafer» «8 next · 0 behind» · 가지 bonded_from → die 1 · observed → defect 6 · transfer → die 1
>                All -> «Open 8» -> 그려짐 8 (die 2 · defect 6) · 움직임 0 · 새 작은 덩어리 0 · 새 노드마다 «? next · not walked»
>       더 없으면  같은 묶음에서 글자 키 다이를 열고 그 «? next · not walked» 누름 -> 요청 (hops=1&direction=both&world=appdemo_vf&world=default) · 덩어리 0 · 상태 줄 «No more · from SYN-BW-103-11 / 0 / 6 / Wafer»
>       뜻       그 노드에서 한 걸음(모든 술어 · 양방향)을 그 자리에서 더 걷는다. 새로 온 노드도 서버가 거기서 안 걸었으니 다시 점선
>                창 머리 «From <노드>» = 그 덩어리의 주인 · «behind» 는 접힌 채 남는 수 한 뜻 · 더 걸을 것이 없으면 «No more · from <노드>»
>    ⑧  덩어리 한 겹   양품 base 를 누름 -> «Fold branches» -> 그 base 의 큰 덩어리 하나 «≤ 79 next · 2 behind | 74 die · 5 quantity» -> 누름
>       본 것    창 하나 «From SYN-BW-SPL-400-19» «≤ 79 next · 2 behind» · 가지 ← in_container die 47 · inspected → die 47 · measures → quantity 5
>                All -> 요청 2 개 · «52 next · 2 behind» · «Open 52» -> 그려짐 52 (die 47 · quantity 5) · 움직임 0 · 새 작은 덩어리 0 · base 의 덩어리 없음
>       뜻       next = 한 걸음 너머 서로 다른 노드 수(Open 이 그리는 수) · behind = 그 너머에 접힌 채 남는 수
>                «≤» = 안 보낸 묶음이 있어 가지끼리 겹침을 아직 모름 — All 이 그 묶음을 걸은 뒤 정확한 수(리허설: 두 가지가 같은 다이)
>    ⑨  그래프의 갈래별 그림(graph per branch) · 덩어리를 걸음 탭으로(E2b) · 값 대응 — main 에 없음 · 클라 착지 대기 (총괄 af004cd7d)
>    시연 전 읽기 — 운영 DB 에서 읽기만. 모델 계측군마다 그것을 재는 measures 원자 수, 0 인 줄은 ③ 에서 닿은 쪽이 «—»(못 닿은 쪽은 빨간 missing)
>         SELECT q.quantity, count(e.id) AS measures_atoms FROM (SELECT from_quantity AS quantity FROM mechanism_edge WHERE model = '<모델>' UNION SELECT to_quantity FROM mechanism_edge WHERE model = '<모델>' AND to_role = 'quantity') q LEFT JOIN ledger_events e ON e.predicate = 'measures' AND e.object_payload->'keys'->>'quantity' = q.quantity GROUP BY 1 ORDER BY 2, 1;
>         박스  void_formation 계측군 18 개 중 0 인 것 18 · void_observation_bias 계측군 2 개 중 0 인 것 1 (post_bond_queue_h 2575) · 0.12 초
>    시연 전 읽기 2 — 운영 DB 에서 읽기만. 두 base 웨이퍼 각각을 이름 부르는 원자 수(주어 · 목적어 · 술어별). 걷기는 한 번에 claims 6,000 까지만 읽고, base 의 원자 하나가 claim 하나다
>         SELECT 'subject' AS side, predicate, count(*) AS atoms FROM ledger_events WHERE subject_type = 'wafer' AND subject_keys = '{"wafer": "<base>"}'::jsonb GROUP BY predicate UNION ALL SELECT 'object', predicate, count(*) FROM ledger_events WHERE object_kind = 'entity_ref' AND object_payload->>'type' = 'wafer' AND object_payload->'keys' = '{"wafer": "<base>"}'::jsonb GROUP BY predicate ORDER BY 3 DESC;
>         리허설 조각(18767 · 18766 과 같은 박스 조각 — 18766 PICK A NODE 목록의 «SYN-BW-103-11 · 278 atoms» · «SYN-BW-SPL-400-19 · 206 atoms» 와 같은 수)
>                     불량 base 278 · 양품 base 206 (0.11 초) — 걷기 claims 2862 · 4 걸음. 불량 base 를 3278 로 늘려도 claims 5862 로 안 잘림,
>                     4278 이면 «Cut · claims 6000» · 3 걸음 · measures 변 518 -> 51 (③ 값 대부분 빠짐) · 5278 이면 2 걸음 · 모델 계측군 17 of 18
>                     경계 ≈ 6,000 − (claims 2862 − base 278) — base 말고 걷기가 읽는 나머지는 운영에서 다르다(못 봤다)
>         잘리면 (18767 · 불량 base 를 4278 로 늘린 조각 · 6d9e9c76d walk-BVDcEwgF.js)
>                     ① 모델 길: Follow 에서 그 많은 술어를 뺀다 — 리허설(measures 를 뺌) claims 1737 · 6 걸음 · 모델 계측군 18 of 18 · 대신 measures 값 0
>                     ② 값: Follow 를 그 술어(measures) 하나 · hops 1 로 다시 걷고 ③ 표 · ④ 트렌드 — 리허설 claims 4073 · measures 변 51
>                        화면: Cut 줄 없음 · quantity 35 줄 · 값 칸 누르면 트렌드 5 점 — 그 술어 원자만으로 6,000 을 넘으면 ② 도 잘린다
>                     ③ STEP 의 fanout_limit 칸에 50~100 을 치고 Walk — 리허설: 비우면 «Cut · claims 6000» · 3 걸음 · Nodes 68 · quantity 36 줄
>                        100 -> Cut 없음 · 4 걸음 · Nodes 78 · quantity 50 줄 · 모델 계측군 18 · pressure_MPa 0.22 | −0.1105 | 0.3305 · 50 -> Nodes 64 · 4 걸음 · 50 줄
>                        (API 로 잰 것: claims 5974 / 5180 · 덩어리 = 불량 base 의 다이 179 중 100 / 50 만 그림 — 표에는 덩어리를 안 그림)
>                        덩어리로 그리지 않은 다이를 안 넓혀서 아낀다(base 자신의 원자는 그대로 다 읽음). =200 은 안 됨 · =20 이면 2 걸음이고 base 의 measures 도
>                        덩어리(33 중 20)라 값이 빠진다
> 걸린 것     리허설의 값은 가짜 행이다 — 모델 계측군에 값이 보이는 것은 가짜 measures 덕. 운영 DB 에 그 값이 있는지는 «시연 전 읽기»가 답한다
> ```
>
> ---
>
> ## [10-10] **bonded_from 이 Follow 에 돌아옴 — 거절된 소스가 같은 이름의 술어를 안 넘어뜨림 (총괄 fe72e5c32) — 이주 «없음» · 재기동 «서버»**
>
> ```
> 순서        pull -> 서버 재기동 (체인 워커는 읽는 소스가 같아 그대로 — 박스 선언 사본에서 남는 소스 5 개가 고치기 전과 같음)
> 확인        GET /api/ledger/declaration -> predicates 에 bonded_from (박스 선언 사본에서 13 -> 14)
>             걷기 화면 STEP 의 Follow 목록에 bonded_from
>             GET /api/ledger/subgraph?id=<베이스 다이 id>&follow=bonded_from&hops=1&direction=outgoing -> 200, 코어 다이로 bonded_from 엣지
> 로그        서버 기동의 «[Ledger] source_plan|bonded_from is NOT read» 줄 사유가 «reads 'bonding_die_from_core', which is not a table»
>             (뷰를 읽음 — 고치기 전엔 «unknown predicate 'bonded_from'»)
> 원장        0 행 — 그 소스는 여전히 읽히지 않음(뷰). 지금 원장의 bonded_from 원자 18,609 개를 Follow 로 걷는 것
> 급할 때      git revert <이 커밋> -> 서버 재기동 (Follow 에서 bonded_from 이 다시 빠짐)
> ```
>
> ---
>
> ## [10-10] **트렌드 쪽 나누기 — /subgraph 의 around · earlier · later (총괄 10-10 B) — 이주 «없음» · 재기동 «서버»**
>
> ```
> 순서        pull -> 서버 재기동 (트렌드 화면은 클라 착지와 함께)
> 확인        GET /api/ledger/subgraph?id=<행 노드 id>&follow=<술어 하나>&direction=incoming&hops=1&around=<ISO 시각>&page=1000
>             walk.mode time_page · edges = 그 노드의 그 술어 원자, 시각 순 — around 앞 · 뒤에서 가까운 1,000 개
>             page.earlier · page.later 를 받은 그대로 earlier= · later= 로 -> 그다음 1,000 개
>             page.has_earlier · has_later = 그 쪽에 더 있나 · page.not_event_time = 시각이 사건 시각이 아니라 뺀 원자 수
> 422         time_page_invalid — argument 가 틀린 자리(follow 하나 키 없이 · direction 한쪽 · hops=1 · 커서 · ISO)
>             time_page_conflicts — arguments 가 같이 못 주는 걷기 인자(positive · negative · seed_type · collect · group_by ·
>             measure · expand · since · until · fanout_limit · format=rows)
> 걷기        around · earlier · later 가 없으면 오늘 걷기 그대로 — 박스 걷기 6 + 메모리 걷기 2, 응답 10,568,244 바이트가 같음
> 박스        읽기 전용 · quantity pressure_MPa <-measures- 4,679 · defect_kind void <-of_kind- 103,863 · recipe RCP-01 <-processed_with- 52,001: 1,000 점 쪽 0.12~0.99 초
> 급할 때      git revert <이 커밋> -> 서버 재기동 (쪽 인자는 무시되고 걷기로 답함 — page 칸 없음)
> ```
>
> ---
>
> ## [10-10] **노드 고르기 — 앞글자로 찾기: key-values 의 starts_with (총괄 bccbdd601) — 이주 «없음» · 재기동 «서버»**
>
> ```
> 순서        pull -> 서버 재기동 (클라 «찾는 상자»는 클라 착지와 함께)
> 확인        GET /api/ledger/key-values?type=wafer&starts_with=SYN-CW
>             nodes = SYN-CW 로 시작하는 노드(대소문자 무시 · 주어 · 목적어) · scanned = 그 수
>             prefix_axis wafer · prefix_case insensitive(이 콜레이션이 대소문자를 같이 세움) · exact 면 대소문자 그대로
> 빈 접두     ?type=wafer  -> 오늘과 같은 목록 + prefix_axis (화면이 상자 이름으로 씀)
> 못 찾는 타입  그 키에 글자로 든 노드가 하나도 없음 — 서버 판정: 그 키가 "" 이상인 첫 노드(jsonb 순서 null < 글자 < 숫자)의 값이 글자인가
>             아니면 prefix_refusal 한 줄, starts_with 를 주면 422 prefix_axis_not_text
> 섞인 형      한 타입에 글자 · 숫자 키가 섞이면(응용 18766 die 의 x) 거절 없이 상자가 열리고 글자로 든 노드만 찾힘
>             — 보드의 «키 값 형 갈림»(시연 뒤)과 같은 뿌리
> 다른 키 접두  &key=<첫 키가 아닌 키>&starts_with=… -> 422 prefix_on_another_key
> 급할 때      git revert <이 커밋> -> 서버 재기동 (목록은 앞 50 개로 돌아감)
> ```
>
> ---
>
> ## [10-10] **원장 ref 해시 인덱스 — 거두기 한 장이 원장 전체를 안 읽게 (총괄 7b) — 이주 «없음» · 재기동 «체인 워커» · 스크립트 한 번**
>
> ```
> 순서        pull -> 체인 워커 재기동(부모 인덱스를 메타데이터로만 만듦)
>             python server/scripts/build_ledger_ref_index.py              미리보기 — 파티션마다 «already» 또는 «would build»
>             python server/scripts/build_ledger_ref_index.py --apply      파티션마다 CONCURRENTLY 로 만들고 붙임 · 쓰기를 안 막음
>             ⚠️ 거두기(--whole-source) «앞»에 — 그래야 한 장이 1,000 ref 로 인덱스를 탄다
> 끝 줄 뜻     <원장>: N partition(s) built, A attached as they were, M already had it - the parent index is valid       <- 이것이면 끝
>             ... is not valid yet   <- 안 붙은 파티션이 남음. --apply 를 다시 (이미 된 것은 건너뜀)
> 소유자 SQL   10-09 에 드린 SQL 을 일부 돌렸어도 됨 — 붙은 파티션은 already, 만들어 두고 안 붙인 <파티션>_ref_hash 는 붙이기만
> 거두기 로그  [Ledger] <원장>.idx_ledger_events_source_raw_ref_hash valid - 1000 refs a page
>             ... missing or not valid - 50000 refs a page, each reads the whole ledger; build it: python server/scripts/build_ledger_ref_index.py --apply --world <세계>
> 급할 때      DROP INDEX idx_ledger_events_source_raw_ref_hash (부모를 지우면 파티션 것도 같이) — 거두기는 50,000 장으로 돌아감
>             되돌리기 git revert <이 커밋> -> 체인 워커 재기동
> ```
>
> ---
>
> ## [10-10] **복사 규칙의 보류 세기 — 키 칸 형이 표마다 달라도 맞게 (총괄 7a) — 이주 «없음» · 재기동 «체인 워커»**
>
> ```
> 순서        pull -> 체인 워커 재기동
> 볼 것       원천 키 칸 형과 공식 표 키 칸 형이 다른 곳(예: 원천 integer · 공식 text)의 보류 칸
>             전: 다시 세기가 오류 없이 보류를 빈칸으로 덮음  ·  후: agreed
>             이미 빈칸으로 덮인 보류는 복사 규칙 replay 로 다시 셈(일요일 표의 복사 replay 단계가 그것)
> 로그        chain_worker.log [ChainRule] rule=<다시 세기 규칙> ... error=None
>             error 에 「integer = text」 가 보이면 이 착지 전 코드(또는 되돌린 VALUES)가 도는 것
> 급할 때      git revert <이 커밋> -> 체인 워커 재기동 (형이 다른 키의 보류가 다시 빈칸이 됨)
> ```
>
> ---
>
> ## [10-10] **체인 워커 기동 중엔 /health 가 «starting: <단계>, N s» — 1 분 넘는 기동이 foreign_beat 로 안 읽힌다 (총괄 bdb356d3f 5b) — 이주 «없음» · 재기동 «체인 워커 · 서버»**
>
> ```
> 순서        pull -> 체인 워커 · 서버 재기동 (서버는 /health 판정이 바뀌어서)
> 기동 중      /health  checks.workers.chain  status starting · detail "starting: <단계>, <N>s"  (CHAIN 뱃지 title 도 같은 문장)
>             단계 이름은 함수 이름(앞 _ · 끝 _sync 뗌). 전부는 기동 끝 줄이 댄다
> 기동 끝      chain_worker.log  [Chain] startup <합> s - <단계> <초> s · ...   <- 「왜 1분이나 걸려」의 답 = 초가 가장 큰 단계
> 뜻          60 s 를 넘어도 그 단계 중이면 starting. 같은 단계의 N 이 계속 늘면 그 단계가 막힌 것(DDL 이면 앞선 질의 뒤)
>             스키마 동기화(설정에 새 칸이 있을 때 ALTER TABLE)도 단계 — starting: sync_dynamic_tables_schema (5b-2)
>             foreign_beat 는 이제 감독자가 띄우지 않은 pid 의 박동 — 둘째 체인 워커를 찾는다(첫 박동 앞엔 import 만)
> 둘째 워커    살아 있는 다른 루프의 박동이 있으면 보정 «전»에 물러난다: [Chain Worker] NOT starting: another chain loop is already running (pid ...)
> 급할 때      git revert <이 커밋> -> 체인 워커 · 서버 재기동
> ```
>
> ---
>
> ## [10-09] **출처가 하나도 안 남은 행은 행째 지운다 — 체인 키만 남은 «껍데기» (총괄 5eee501eb · 판정 ㄱ) — 이주 «없음» · 재기동 «체인 워커 · 서버»**
>
> ```
> 순서        ① pull -> 체인 워커 · 서버 재기동
>            ② 이미 쌓인 껍데기 — 둘 중 하나
>               미리보기  python server/scripts/chain_replay_cli.py remove-shells <공식 표>
>               실행      같은 명령 + --apply   (소급 탭 «Remove rows with no source left» 와 같은 일)
>               또는 공식 표를 비우고 다시 채우기(일요일 순서) — 그러면 쓸기가 필요 없다
> 미리보기 뜻   N row(s) of '<표>' show nothing outside their keys; M of them have only the chain's key layers left
>              M 이 지울 수. N - M 은 사람 · 파일이 키를 썼거나 사람 층(빈 값 포함)이 있어 남는다
> 껍데기란      키 칸 밖에 값 있는 층 0(체인이 쓴 빈 칸은 없는 것으로) · 키 칸 층은 체인 것뿐 · 사람 층 0(빈 값이어도)
>              그리고 화면에 키 밖 값이 없음
> 그 뒤로       회수와 다시 세기 뒤 그런 행이 되면 체인이 그 쓰기 바로 뒤 지운다
>              chain_worker.log  [ChainShell] table=<표> rows_deleted=N - only the chain's keys were left
>              지운 행마다 이력 한 줄(updated_by chain_shell_rows) · 원장은 그 행의 원자를 거둔다 · 그 삭제는 어떤 규칙도 안 깨운다
> 급할 때      git revert <이 커밋> -> 체인 워커 · 서버 재기동 (이미 지운 행은 원본을 다시 넣으면 다시 생긴다)
> ```

---

> ## [10-09] **맵퍼가 쓰는 층 이름은 chain_ingestion 하나 — 체인 출력이 옛 체인 층에 덮이던 것 (총괄 09f3cd289 ①) — 이주 «없음» · 재기동 «체인 워커 · 서버»**
>
> ```
> 순서        ① pull -> 체인 워커 · 서버 재기동
>            ② chain_worker.log 에서 이름이 바뀐 규칙 확인 — @mapper(source_name=) 를 적은 규칙마다 한 줄, 선언을 새로 읽을 때만
>               [ChainRules] <규칙>: source_name '<그 이름>' is written as chain_ingestion
>            ③ 그 규칙 replay — 미리보기  python server/scripts/chain_replay_cli.py replay <규칙>
>                             실행      같은 명령 + --apply   (소급 탭 «Chain replay» 와 같은 일)
>               -> 같은 칸의 옛 chain_ingestion 층 자리에 새 값이 써진다(같은 이름 = 같은 자리)
>            ④ 옛 이름 층(예: dt_inventory)은 남아도 순위 99 라 안 보인다. 지우려면
>               python server/scripts/chain_replay_cli.py withdraw <표> <그 이름> --columns <칸,…>  -> 보고 --apply
>               (소급 탭 «Withdraw a stale source (R2)» 와 같은 일)
> 뜻          맵퍼가 무엇을 적든 그 칸의 층은 chain_ingestion. 괄호 행 층 X (<id>) 는 chain_ingestion (<id>).
>            source_name 을 안 적은 칸(기본값 user — 사람 층으로 써지던 것)도 체인 층
> 볼 것       replay 뒤 그 칸의 층(cell_sources)에 chain_ingestion 이 새 값 — 화면 값이 그것
>            그대로인 것: 자동확정 두 이름 · enrichment_backfill
> 안 바뀐 것   순위 — chain_ingestion (<id>) 행 층이 옛 plain chain_ingestion 층에 지는 것은 이번에 안 고침(총괄: 시연 뒤).
>            일요일에 공식 표를 비우고 다시 채우면 옛 plain 층이 없어져 안 드러난다
> 급할 때      git revert <이 커밋> -> 체인 워커 · 서버 재기동 (이미 chain_ingestion 으로 써진 칸은 그대로)
> ```

---

> ## [10-09] **접기를 «지우지 않고 표시»로 — 복사 규칙 on.exclude 가 표시된 행을 안 받고 그 층을 거두며, 보류를 다시 센다 (총괄 016a766af · 83c05cfbb) — 이주 «없음» · 재기동 «체인 워커 · 서버»**
>
> ```
> 순서           ① 로그 표(table_config)에 글자 칸 하나 — 예: "fold_mark": "string"
>               ② 복사 규칙에 on.exclude: ["fold_mark"] (평면 규칙은 "exclude") -> 저장 -> 체인 워커 · 서버 재기동
>                  다시 세기 규칙에는 로더가 source_exclude 를 찍는다(손으로 안 적음)
>               ③ 좌표가 틀린 수동 행이 섞였으면 범위 칸으로 자동 행끼리만 — 좌표 바로잡기(층 이름 고정 착지 뒤 인벤토리 replay)가 먼저
>               ④ 미리보기  python server/scripts/chain_replay_cli.py fold-rows <로그 표> --keys <키 칸,…> --order <고를 칸> --mark-column fold_mark [--only-column <칸> --only-text <글자>]
>               ⑤ 실행      같은 명령 + --apply   (소급 탭 «Fold duplicate rows» 의 mark_column · only_column · only_text 와 같은 일)
> 미리보기 뜻      N row(s) are marked, M stay · K row(s) outside (범위 밖, 그대로) · J row(s) marked before rank no more
>               the rules that exclude by fold_mark (<규칙>) run on them and take back what they fed; then the recount rules (<규칙>) run on the rows they fed
>               no recount rule paired - holds stay as they are   = 다시 세기 짝이 없다(보류는 그대로)
> 실행 뒤 볼 줄    chain_worker.log
>                 [Chain] slot N (pid …) runs line <실행 id>
>                 [Chain] <복사 규칙>: N row(s) not handed over - excluding column(s) filled: fold_mark=N
>                 [ChainRetract] table=<로그 표> edited_rows=N … cells_withdrawn=…
>                 [ChainRule] rule=<다시 세기 규칙> … rows_in=…
>               «이 규칙이 무엇을 쓰는지 아직 모릅니다» 줄 = 그 맵퍼가 쓰는 칸을 등록 안 했다(copy_rows_with_hold 는 등록함)
> 되돌리기        표시 칸을 비우면 그 행이 다시 규칙에 들어간다(값이 다르면 다시 보류)
> 다시 돌리면      표시된 행은 순위에 안 든다 — 미리보기 N 이 0 이면 끝
> 급할 때         git revert <이 커밋> -> 체인 워커 · 서버 재기동 (이미 적힌 표시는 남는다 — 지우려면 그 칸을 비운다)
> ```

---
> ## [10-09] **성공 토스트의 문장은 note 칸으로 · 판정에서 깨진 소급 실행은 failed 로 끝난다 (총괄 10-09) — 이주 «없음» · 재기동 «서버 · 스케줄러»**
>
> ```
> 토스트         SUCCESS 인 파일 인입 메시지는 그 문장(다시 읽기의 [resume-abort] … force · 키 결측 N행 스킵)을 note 칸에 싣는다
>               error_msg 칸은 실패 · 건너뜀에만 — 화면이 성공을 오류로 그리지 않는다
> 소급 실행       스케줄러가 띄운 자식이 판정에서 어떤 예외를 내도 그 행은 failed:
>               «the run could not be judged - <예외 이름>: <문장>» (거절은 전처럼 그 문장)
>               전에는 행이 running 으로 남아 소급 관문을 닫았다 — 모든 소급이 «반응 없음»
> 확인           소급 탭 실행 목록에 running 으로 멈춘 행이 없다 · 있으면 그 행의 error 를 읽는다
> 급할 때         git revert <이 커밋> -> 서버 · 스케줄러 재기동
> ```

---
> ## [10-09] **파일 다시 읽기는 실패 재시도 문의 statuses — 소급 «Re-read files» 은퇴 (총괄 a4d135a06) — 이주 «없음» · 재기동 «서버»**
>
> ```
> 화면           파일 인입 화면 Retry(폴더 · 미리보기)의 «Include files that went in» 토글 — 클라 레인이 붙인 뒤
> 그 전 명령줄    운영 서버 PowerShell · 토큰은 본인 것
>   미리보기      curl.exe --noproxy "*" -X POST -G "http://127.0.0.1:8080/admin/file-ingestion/retry-failed" -H "X-Admin-Token: <토큰>" --data-urlencode "statuses=SUCCESS,FAILED,SKIPPED" --data-urlencode "folder=<폴더>" --data-urlencode "preview=true"
>   실행          같은 명령에서 preview 줄만 뺀다 (since / until 도 같은 모양: --data-urlencode "since=2026-10-09 18:00")
> 답의 뜻         count = 넘길 파일 · by_state = 상태별 · by_folder = 바로 아래 폴더별
>                missing = 기록이 말하는 자리에 없어 안 넘긴 수 · missing_files = 그 앞 다섯 이름
>                실행 답 «N file(s) handed to the watcher» = 요청 안에서 PENDING_RETRY 로 표시함 (기다리지 않는다)
> 볼 줄          watcher.log: Detected PENDING_RETRY log ID #<id> (<파일>). Processing... -> File processed: <파일> (SUCCESS) for <표>. -> Retry succeeded for log ID #<id>.
>                화면에는 보통 인제션과 같은 토스트 (다시 읽기는 [resume-abort] … 재처리(force) 문장을 같이 싣는다)
> 관문           소급 관문을 안 잡는다 — replay 가 돌아도 바로 표시되고, 다시 읽기가 replay 를 안 막는다
> statuses 없음   오늘과 같은 실패 재시도(FAILED 만, 자리에 없는 파일도 넘김)
> 소급 탭         «Re-read files» 는 없어졌다 — 옛 실행 기록은 «reread_files (retired)»
> 급할 때         git revert <이 커밋> -> 서버 재기동
> ```

---
> ## [10-09] **회수가 드러낸 값을 «접힌 사건»으로 내고, 이미 쌓인 회수의 행마다 사건을 한 명령으로 접는다 (총괄 eddf9e38e) — 이주 «없음» · 재기동 «체인 워커 · 서버»**
>
> ```
> 순서           git pull -> 체인 워커 · 서버 재기동 -> 쌓인 것 접기 미리보기 -> --apply
> 미리보기        python server/scripts/chain_replay_cli.py fold-withdraw-events                (안 씀)
>               '<표>' N event(s) -> M - R row(s). Left as they are: T event(s) the chain already tried (RETRYING), U on a line the chain runs now.
>               N = 회수가 행마다 낸, 체인이 아직 안 돈 사건 · M = 바뀔 접힌 사건(표마다 1,000 행에 하나) · R = 그 사건들이 가리키는 행
>               T · U = 안 접고 두는 것 — 체인이 이미 시도한 것 · 지금 체인이 도는 줄. 체인이 끝내면 그대로 지나간다
>               No waiting withdrawal event goes row by row = 접을 것 없음
> 실행           python server/scripts/chain_replay_cli.py fold-withdraw-events --apply        (소급 탭 «Fold row-by-row withdrawal events» 와 같은 일)
>               fold-withdraw-events: <같은 문장> -> 다시 미리보기에서 N 이 없으면 끝
> 쪽             사건 10,000 개마다 한 커밋(cell_layer.FOLD_PAGE_EVENTS) — 새 사건 넣기와 옛 사건 지우기가 같은 커밋
> 멈추기          소급 탭의 × — 쪽 사이에서 선다. 다시 돌리면 남은 것만
> 큐에서          접힌 사건은 새 id 라 큐 뒤로 간다. 체인은 그 행을 «돌 때의 값»으로 다시 읽는다
> 재기동 뒤       회수 사건이 표마다 1,000 행에 하나 — python -m ledger followup 의 따라갈 일에 회수 때문에 «EDIT 한 행»이 쌓이지 않는다
> 바뀐 깨움       회수 사건이 바꾼 칸 이름을 싣는다 — 그 칸을 깨움 칸으로 안 가진 규칙 · 그 칸을 안 읽는 원장 소스는 회수에 안 깬다(다른 접힌 쓰기와 같은 규칙)
> 급할 때         git revert <이 커밋> -> 체인 워커 · 서버 재기동 (이미 접은 사건은 그대로 돈다)
> ```

---
> ## [10-09] **선언이 바뀌어 남은 원자를 --whole-source 가 거둔다 (총괄 e027f669d) — 이주 «없음» · 재기동 «서버»(소급 탭에서 쓸 때) · 명령줄은 그대로**
>
> ```
> 언제           소스가 읽는 표를 바꿨거나(예: dt_log -> 공식 표) 소스 이름을 바꿨는데 예전 원자가 남았을 때
> 미리보기        python -m ledger.backfill --source <소스> --whole-source              (server 폴더 · 안 씀)
>                 stale_atoms · stale_tables = 지금 선언이 안 읽는 표에서 나온 원자 수, 표 · 술어마다
>                 선언에 없는 이름(옛 이름)이면 relation_rows 가 None 이고 stale_* 가 그 이름의 원자 전부
> 실행           python -m ledger.backfill --source <소스> --whole-source --apply
>                 선언에 있는 소스면 먼저 그 소스를 다시 번역하고, 끝에 안 읽는 표의 원자를 거둔다
> 답의 뜻         stale_withdrawn = 거둔 원자 · stale_forgotten = 지운 색인 줄 · stale_pages = 50,000 ref 쪽 수
>                 같은 명령으로 다시 미리보기 -> stale_atoms 0 이면 끝
> 은퇴 소스       source_retired 로 거절 — 원자 그대로(판정 198)
> 비용           쪽 하나 = 원장 훑기 한 번(source_who 로 시작하는 원장 인덱스가 없다)
>                 박스 사본(파티션 8 · 원자 238 만) 50,000 ref 쪽 DELETE 2.01 · 1.53 s — 박스 수, 운영 주장 아님
> 멈추기          소급 탭의 × — 쪽 사이에서 선다. 다시 돌리면 남은 것만
> census         다음 커밋(총괄 10-09 미룸) — 지금은 이름을 알고 있을 때 쓴다
> ```

---
> ## [10-09] **raws 하위 폴더에 «나중에» 온 파일이 30 초 안에 들어간다 · 남은 파일은 한 줄로 까닭을 말한다 — 이주 «없음» · 재기동 «수집기»(따로 띄우면 run_watcher, 아니면 서버)**
>
> ```
> 무엇이 바뀌나    하위 폴더 다시 보기가 자기 스레드(watcher-subfolder-recheck)에서 돈다 — 스윕의 잠금 밖
>                기동 즉시 한 번, 그 뒤 subfolder_recheck_seconds(ingestion_settings.json, 적지 않으면 30)마다 raws/ 하위 폴더를 훑는다
>                일꾼을 부르는 것은 «바뀐 폴더» · «마지막으로 부른 뒤 300 초(스윕 주기)가 지난 폴더»뿐 — 보관 끔으로 남는 폴더는 훑기만
>                스윕(300 초)은 이제 하위 폴더를 안 본다 — 어느 수집기의 느린 raws 직속 파일이 모든 하위 폴더를 붙잡던 길이 없어졌다
> 볼 줄          수집기 로그:
>                  [<표>] 📂 '<폴더>': N file(s) left - <까닭> - <다음 시도> - #k for this folder and reason (said at the 1st, 10th, 100th ...)
>                까닭과 그 뜻:
>                  tree ingestion has been running for M min (now: <파일>)       = 그 폴더 일꾼이 아직 돈다. now 가 오래 같은 파일이면 그 파일이 걸린 것
>                  Tree ingestion deferred — K file(s) still being written ...   = 아직 쓰는 중인 파일. 다 쓰면 다음 다시 보기에 들어간다
>                  kept in place (archive_processed_files=false): dispatched N ... = 처리는 됐고 보관 끔이라 제자리. 남아 있어도 «인식 못 함»이 아니다
>                  Tree ingestion incomplete: ... — directory preserved            = 처리 못 했거나 못 옮긴 파일. 바뀌면 다음 다시 보기, 아니면 300 초 뒤 다시
>                  nested-directory ingestion is off (flatten_nested_dirs=false) ... = 하위 폴더 적재가 꺼져 있다. 그 파일은 안 들어간다
>                같은 폴더 · 같은 까닭은 1 · 10 · 100 번째만 말한다. 폴더가 다 비워지면 셈이 비어 다음은 다시 #1
>                전의 «Tree ingestion of '<폴더>' has been running …» · «… periodic sweep will retry» 줄은 이 줄로 바뀌었다
> 확인           이미 있는 하위 폴더에 파일 하나를 넣는다 -> 30 초 안에 행이 들어간다 (전엔 최대 300 초, 붙잡히면 그 이상 · 로그 0 줄)
> 비용           다시 보기마다 하위 폴더를 훑는다(DB 안 감) — 이 박스 2만 파일 폴더 1.13 · 1.14 · 1.15 s
> 급할 때        git revert <이 커밋> -> 수집기 재기동
> ```

---
> ## [10-09] **같은 원천 행이 한 묶음에 두 번 와도 그 칸을 한 번만 찾는다 — 이주 «없음» · 재기동 «체인 워커»**
>
> ```
> 무엇이 바뀌나    cell_layer.cells_stamped_by 가 원천 id 를 한 번씩만 보낸다(순서 유지)
>                고친 원천 목록은 EDIT 사건마다 행 id 를 하나씩 모으므로 같은 행이 한 묶음에 두 번 올 수 있다 —
>                원천마다 묻는 모양(아래 절)은 그때 두 번 답해 보호(user) 층 셈이 부풀었다. 거두는 칸은 전에도 같았다
> 볼 줄          chain_worker.log: [ChainRetract] table=<표> ... protected_skipped=N
>                  = 거두지 않고 둔 사람 값 칸 수 그대로. 전엔 겹친 만큼 컸다
> 급할 때        git revert <이 커밋> -> 체인 워커 재기동
> ```

---
> ## [10-09] **LLM 선언 파일 llm_config.json · 요청 로그 llm_requests.log (총괄 043915ab0 ①) — 이주 «없음» · 재기동 «필요 없음»(부를 때마다 파일을 읽는다)**
>
> ```
> 적는 곳        server/config/llm_config.json — 모양은 server/config/sample/llm_config.json.sample
>               base_url · model · api_key · timeout_s(초, 기본 60) · headers(덧붙일 요청 머리, 기본 없음) · proxy
> proxy          없거나 null = 시스템 프록시를 안 읽고 base_url 로 바로 간다
>               프록시를 거쳐야 하면 "proxy": "http://<호스트>:<포트>"
> 할 일          샘플을 server/config/llm_config.json 으로 복사해 값을 넣는다 — 재기동 없음(부를 때마다 읽음)
> 확인 한 줄      cd server; python -c "from utils import llm; print(llm.ask_json('Reply with a JSON object with one key ok set to 1'))"
>                 -> {'ok': 1} 이면 닿았다. LlmRefused 문장이면 그 문장이 칸 이름을 댄다
> 옮기기          ASSY_LLM_* 환경변수는 은퇴했다 — 값을 파일로 옮긴다. 파일 없이 환경변수만 있으면 부를 때 거절:
>                 ASSY_LLM_* environment variables are not read any more - write server/config/llm_config.json (sample: config/sample/llm_config.json.sample)
> 볼 로그         server/llm_requests.log — 부를 때마다 두 줄
>                 {"sent": <시각>, "id": …, "url": "<base_url>/chat/completions", "model": …, "headers": {… "Authorization": "Bearer ***" …}, "payload": {…}, "proxy": …}
>                 {"received": <시각>, "id": <같은 id>, "status": 200, "answer": {…}, "ms": …}
>                 실패면 둘째 줄이 "status": <숫자 또는 null>, "error": "<예외 이름>: <문장>"
> 뜻             sent 줄 뒤에 timeout_s 만큼 지나 status null 의 error = 그 주소에 못 닿음(프록시 · 방화벽 쪽)
>               status 숫자 = 상대가 답했다. 401 · 403 은 키 · 권한, 404 는 base_url 경로 · 모델 이름부터 본다
> 키 확인         Select-String -Path server\llm_requests.log -Pattern '<키 앞 여섯 글자>' | Measure-Object   -> Count 0
> 크기           요청 하나 ≈ 3285 바이트(이 박스 · 사전 50 구절 · 글 600 자 · 답 3 링크) -> 글 1 만 개 ≈ 33 MB. 사전 · 글이 길면 그만큼 는다
>               돌려 쓰기 없음 — 커지면 파일을 다른 곳으로 옮긴다(줄마다 열고 닫으므로 다음 부름이 새로 만든다)
> httpx          0.26 보다 낮으면 부를 때 거절: httpx <지금 판> cannot take a proxy - 0.26 or later is needed: pip install -U httpx
> 격리 스택       devenv bootstrap 이 이 파일도 복사한다 — 격리 스택도 같은 키로 같은 모델을 부른다
> 급할 때         파일 이름을 바꾼다 -> 다음 부름부터 거절(그 글의 묶음만 실패, 다른 표는 그대로)
> ```
> ## [10-09] **run_in: operation 은퇴 — 규칙은 체인 묶음에서만, 느린 규칙은 rows_per_run: 1 — 이주 «없음» · 재기동 «서버 · 체인 워커»**
>
> ```
> 무엇이 바뀌나    run_in: operation(작업 rule_rows 로 줄 세우기)이 은퇴했다. 모든 규칙은 체인 묶음에서 돈다
>                rows_per_run: N = 이 규칙의 묶음 하나가 받는 트리거 행 수. 1 이면 글 하나 = 묶음 하나 — 틀린 답은 그 글만 FAILED
>                적지 않으면 지금 그대로(자르지 않음). 다른 표의 줄은 다른 슬롯에서 돈다
>                ⚠️ 한 이벤트에 여러 행이 묶인 것(소급 · 삭제 등)은 쪼개지 않고 통째로 간다
> 할 일           LLM 규칙의 "run_in": "operation" 은 지워도 되고 그대로 둬도 된다(거절 안 함). "rows_per_run": 1 은 남긴다
> 볼 줄          chain_worker.log (켜질 때 · 선언 내용이 바뀐 뒤 한 번):
>                  [ChainRules] <규칙>: run_in is retired - this rule runs in the chain; rows_per_run splits its groups
>                  = 그 규칙에 아직 run_in 이 적혀 있다. 체인에서 돈다
> 확인           관리 화면 Retroactive 에 새 «Run a rule's queued rows» 실행이 더 안 생긴다(옛 실행은 목록에 «(retired)»로 남음)
>                체인 대기열에서 그 글 표의 줄이 글 하나씩 줄어든다
> 급할 때        git revert <이 커밋> -> 서버 · 체인 워커 재기동
> ```

---
> ## [10-09] **체인 고리 줄은 배정자만, 고리마다 한 줄, 선언이 바뀔 때만 — 이주 «없음» · 재기동 «체인 워커»**
>
> ```
> 볼 줄          chain_worker.log:  [ChainRules] loop: dt_inventory -> dt_log -> dt_inventory · capped at max_chain_depth=8
>                = 선언에 그 고리가 있고(의도된 고리면 할 일 없음), 홉 상한이 그만큼 막는다. 더 긴 고리가 필요하면 chain_rules.json 의 max_chain_depth
>                나오는 때: 체인 워커가 켜질 때 한 번 · 체인 선언 «내용»이 바뀐 뒤 다시 읽을 때 한 번. 슬롯 · 슬롯 재기동 · 서버는 안 말한다
>                고리는 표 이름으로 적는다 — 같은 고리는 어느 규칙에서 출발해 찾든 한 줄
> 전과 다름      전엔 «[ChainRules:규칙 -> … ] 고리 (이 고리의 규칙들끼리만 …)» 가 프로세스마다 · 출발 규칙마다 따로 나왔다
> 급할 때        git revert <이 커밋> -> 체인 워커 재기동
> ```

---
> ## [10-09] **겹쳐 들어간 행을 키마다 하나로 접는다 — Fold duplicate rows — 이주 «없음» · 재기동 «서버 · 체인 워커»**
>
> ```
> 미리보기   python server/scripts/chain_replay_cli.py fold-rows <로그 표> --keys dt_wafer_id --order <시간 칸>
> 실행       python server/scripts/chain_replay_cli.py fold-rows <로그 표> --keys dt_wafer_id --order <시간 칸> --pace slow --apply
>            (가장 늦은 것을 남기려면 --keep max · 소급 탭 «Fold duplicate rows» 도 같은 연산)
> 답의 뜻    미리보기: 「K key(s) of (dt_wafer_id) … M row(s) go, R stay … For example dt_wafer_id=…: keeps <시간>, deletes <시간>」 — keeps 가 진짜인지 본다. 아무것도 안 씀
>            실행: 「fold-rows '<표>': M of M row(s) deleted in P page(s), K key(s), B row(s) with a blank key part left as they are」 — 그리드 삭제 문으로 지움(층 · 이력 같이, 원자 · 먹인 층은 원장 따라가기가 거둠). STOPPED 면 다시 돌리면 남은 것만
> 빈 키      키 칸 하나라도 빈('' 또는 NULL) 행은 접지 않고 그대로 둔다(총괄 9c8b9f919) — 미리보기 「B row(s) with a blank key part are left as they are.」 의 B 가 그 수
> 먼저 남길 행  python server/scripts/chain_replay_cli.py fold-rows <로그 표> --keys dt_wafer_id,dtx,dty --order <시간 칸> --prefer-column job --prefer-text auto
>            같은 키에서 job 에 auto 가 든 행(AUTO · Auto 도)을 먼저 남기고, 그 안에서 가장 이른 시간(총괄 1d2a7e0fd). 둘 중 하나만 적으면 거절
>            미리보기 「a row whose job holds 'auto' (any case) stays first - P key(s) keep one」 + 표본에 「keeps <시간> (job=…), deletes <시간> (job=…)」
> ```

---
> ## [10-09] **원천 행이 먹인 칸 찾기가 인덱스를 탄다(복사 · 조인의 고친 행 거두기, 지운 행 거두기) — 이주 «없음» · 재기동 «체인 워커»**
>
> ```
> 무엇이 바뀌나    cell_layer.cells_stamped_by 가 PostgreSQL 에서 원천 하나씩 idx_sources_by_origin 으로 찾는다
>                전엔 IN (1,000 개) 한 덩어리 — 통계가 «원천 하나가 칸 수천»이라 믿으면 cell_sources 를 통째로 읽었다(Seq Scan)
>                지나는 길: 고친 원천 행이 먹이던 층 거두기(묶음마다) · 지운 행이 먹인 층 거두기
>                소급 첫 채우기도 replay 가 EDIT 으로 넣으므로 묶음마다 이 찾기를 지난다(거둘 층이 없어도)
> 확인           어드민 Overview «Indexes» 표에서 idx_sources_by_origin 의 Scans 가 묶음마다 그 묶음의 원천 행 수만큼 는다
>                  = 탄다. 전엔 이 수가 안 늘었다
>                pg_stat_activity 에 «cell_sources ... origin_row_id IN (...)» 대신 «unnest(...) ... CROSS JOIN LATERAL» 이 보인다
> 급할 때        git revert <이 커밋> -> 체인 워커 재기동
> ```

---
> ## [10-09] **원장 따라가기의 소스 실패 줄 #N 은 «이번 고장»에서 몇 번째 — 그 소스가 한 번 성공하면 다시 #1 — 이주 «없음» · 재기동 «체인 워커»**
>
> ```
> 무엇이 바뀌나    [LedgerFollowUp] <소스> <- <표> (N rows) failed in world <세상>: <사유> - #N of this source, table and error (...)
>                의 #N 은 그 소스 · 표 · 세상이 마지막으로 성공한 뒤부터 센다. 성공하면 셈이 비고, 다시 생긴 고장은 #1 부터 말한다
>                전엔 프로세스가 사는 동안 쌓여, 고친 뒤 다시 생긴 고장이 누적 100 번째까지 조용했다
> 그대로         삭제 실패 줄 · batch failed 줄의 셈은 비우지 않는다(재기동 때 다시 1)
> 답의 뜻        #1 이 다시 보인다 = 한 번 나았던 그 소스가 다시 넘어졌다
> 급할 때        git revert <이 커밋> -> 체인 워커 재기동
> ```

---
> ## [10-09] **선언된 인덱스가 DB 에 없으면 체인 워커가 알리고 스스로 만든다 · GET /admin/indexes — 이주 «없음» · 재기동 «체인 워커 · 서버»**
>
> ```
> 무엇이 바뀌나    «있어야 할 인덱스»의 답은 하나 — server/database/models.py 의 Index · UNIQUE 선언(각각 info 의 purpose · serves)
>                체인 워커가 켜질 때와 설정을 다시 읽을 때 선언 대 DB 를 견주고, 빠졌거나 무효인 것을 한 줄로 알린 뒤 하나씩 만든다
>                CONCURRENTLY — 표 쓰기를 막지 않는다. 체인 · 슬롯은 그동안 그대로 돈다
>                은퇴한 둘(ix_cell_sources_table_name · ix_cell_sources_column_name)은 이제 선언에 없다 — 다시 안 만든다
> 볼 줄          chain_worker.log:
>                  [Indexes] <N> declared index(es) the database lacks or holds invalid: <이름> on <표> (missing|invalid), ... - building them one at a time
>                  = 이 DB 에 그 인덱스가 없다(또는 깨졌다). 이어서 하나씩:
>                  [Indexes] building <이름> on <표>
>                  [Indexes] <이름> built in <초> s        (failed 면 바로 위에 [Schema Sync] Failed to ensure ... : <사유>)
>                  [Indexes] <이름> still building after <초> s - building - waiting for transactions older than it: pid <P> (<application_name>)
>                  = 10 분마다. 그 pid 의 트랜잭션이 끝나야 만들기가 끝난다 — pg_stat_activity 에서 그 pid 가 무엇인지 본다
>                이 줄들이 없다 = 선언된 인덱스가 전부 있다
> 볼 곳          GET /admin/indexes  (관리자 토큰)
>                  declared 의 줄마다 name · table · columns · where · include · purpose · serves · state(present|missing|invalid|building) · building · size_bytes · scans
>                  outside = 그 표들에 있는데 아무 선언도 없는 인덱스 (기본 키는 선언된 것으로 친다)
> 끄는 법        ingestion_settings.json 에 "build_missing_indexes": false   -> 알리기만 하고 안 만든다 (다음 기동 · 설정 다시 읽기부터)
>                만드는 중인 것을 멈추려면 그 만들기의 pid 를 pg_cancel_backend — 남은 무효 인덱스는 다음 기동이 지우고 다시 만든다
> 급할 때        git revert <이 커밋> -> 체인 워커 · 서버 재기동
> ```

---
> ## [10-09] **원장 따라가기의 실패 줄은 같은 실패의 1 · 10 · 100 … 번째에만 — 이주 «없음» · 재기동 «체인 워커»**
>
> ```
> 무엇이 바뀌나    아래 세 줄이 매번이 아니라 같은 실패의 1 · 10 · 100 · 1000 … 번째에만 나온다. 줄 끝에 #N
>                  [LedgerFollowUp] <소스> <- <표> (N rows) failed in world <세상>: <사유> - #N of this source, table and error (...)
>                  [LedgerFollowUp] delete on <표> (N rows) failed in world <세상>: <사유> - #N of this table and error (...)
>                  [LedgerFollowUp] batch failed: <사유> - #N of this error (...)
>                «같은 실패» = 같은 소스 · 표 · 세상 · 예외 이름(행은 안 가름). 체인 워커를 재기동하면 다시 1 부터
> 그대로         실패 «기록» — 아웃박스 ledger_state failed · 실패 영수증 · 하트비트의 failed=N
>                몇 건 · 어느 이벤트인지는  python -m ledger followup        (server 폴더)
> 답의 뜻        #1 만 있다 = 그 실패가 아직 10 번이 안 됐다 · #10 · #100 이 이어진다 = 같은 실패가 계속 — 그 소스 · 표부터
> 선언 깨짐       따로 — 처음 · 풀림 · 10 분 알림 줄 셋(전 라운드)은 그대로
> 급할 때        git revert <이 커밋> -> 체인 워커 재기동
> ```

---
> ## [10-09] **× 와 끝을 쓰는 묶음은 행을 id 순으로 잠근다 · 슬롯 박동을 못 읽으면 다시 읽고, 그래도 못 읽으면 답이 말한다 — 이주 «없음» · 재기동 «서버 · 체인 워커»**
>
> ```
> 무엇이 바뀌나    묶음은 끝(SUCCESS)을 쓰기 직전에 그 행을 잠그고 빼 둔 표시를 읽는다
>                  그 뒤에 온 × 는 그 커밋을 기다렸다가 끝난 행을 비켜 간다 — 그 행은 «돌았음»
>                × 의 빼 두기도 같은 순서(id 오름차순)로 먼저 잠근다 — 둘이 서로를 기다리며 서지 않게
>                × 가 슬롯 박동 파일을 못 읽으면(쓰는 중) 1 초 안에서 다시 읽는다
> 답의 뜻        × 응답에 "slot_not_found": "slot not found - the line's events are set aside; its running group may finish"
>                  = 그 줄의 대기 이벤트는 빼 뒀다. 어느 슬롯이 돌리는지는 모른다 — 도는 묶음은 끝까지 갈 수 있다
>                  대기열을 다시 읽어 그 줄에 slot_pid 가 보이면 × 를 한 번 더
> 늦어지는 것     끝을 쓰는 묶음과 겹친 × 는 그 묶음이 커밋할 때까지 응답이 늦다
> 급할 때        git revert <이 커밋> -> 서버 · 체인 워커 재기동
> ```

---
> ## [10-09] **× 의 답은 슬롯이 끝난 «뒤»의 행 수 · 빼 두는 사이 끝까지 돈 행은 «돌았음» — 이주 «없음» · 재기동 «서버 · 체인 워커»**
>
> ```
> 무엇이 바뀌나    × 는 슬롯을 끈 뒤 그 프로세스와 DB 연결이 «끝날 때까지» 기다리고(각각 최대 5 초) 그 줄의 행을 다시 센다
>                답 skipped_events    = × 가 읽을 때 기다리던 그 줄의 체인 이벤트 중 지금 «빼 둔» 것
>                답 already_processed = 그중 «돈» 것 — 표시와 슬롯 종료 사이에 묶음이 커밋했거나, 읽기와 표시 사이에 체인이 끝낸 것
>                묶음이 파이썬 일 중이라 끊을 질의가 없었고 끝까지 돌았으면 그 행은 «돌았음»(SUCCESS, 빼 둔 표시를 지움)
>                  — rerun_set_aside 가 그 행을 다시 돌리지 않는다
> 볼 줄          chain_worker.log:
>                  [slot <n> pid <P>] [Chain] tx '<열쇠>': <N> event(s) were set aside while it ran and it ran - they read as ran, not set aside
>                  = × 가 늦었다. 그 행은 이미 돌았다. 감사 줄 출처 chain_queue_skip_too_late (표마다 · 열쇠 · 수)
>                서버 로그:
>                  [Chain] slot <n> pid <P> had not ended 5 s after its kill - its line is counted as it stands
>                  = 슬롯이 그 안에 안 끝났다. 그 답의 두 수는 그 순간의 것 — 대기열을 다시 읽어 본다
> 확인           × 한 번 -> 응답 JSON 에 already_processed 칸(화면은 아직 이 수를 안 그린다)
> 급할 때        git revert <이 커밋> -> 서버 · 체인 워커 재기동
> ```

---
> ## [10-08] **글자로 적힌 시각 칸은 선언한 형식(format)으로 읽는다 · 못 읽는 시각은 그 분자만 거절 — 이주 «없음» · 재기동 «서버 · 체인 워커»**
>
> ```
> 적을 곳        선언 폼의 시각 칸(매핑의 occurred_at 바인딩 또는 read.occurred_at)에 «Time format» — strptime 철자
>                예  20261008_123000 -> %Y%m%d_%H%M%S   ·   20261008123000 -> %Y%m%d%H%M%S
>                timezone 은 그 옆에 그대로(Asia/Seoul). 글자에 오프셋이 적혀 있으면 오프셋이 이긴다
>                저장이 거절하면 그 문장대로: 형식이 오늘 시각을 다시 못 읽거나 날짜가 없음(invalid_time_format) · timezone 없음
> 바꾼 뒤 돌릴 것  server 폴더에서
>                python -m ledger.backfill --source <소스> --whole-source              (미리보기 — 행 · 원자 · 거절)
>                python -m ledger.backfill --source <소스> --whole-source --apply      (그 소스를 다시 번역)
> 답의 뜻        미리보기에 거절이 0 이면 형식이 맞다
>                「Time unreadable」(unreadable_occurred_at) 이 있으면 그 행의 값이 형식과 다르다 — 문장에 '<값>' does not match format <형식>
>                  = 그 분자만 빠지고 나머지는 들어간다. 전엔 못 읽는 시각 하나가 그 쪽 전체를 멈췄다
> 급할 때        format 칸을 지우면 전과 같다(글자는 ISO 읽기 하나로만) · 코드 되돌리기는 git revert <이 커밋> -> 서버 · 체인 워커 재기동
> ```

---
> ## [10-08] **끊긴 묶음은 누가 끊었든 되감는다(질의 상한만 빼고) — 이주 «없음» · 재기동 «체인 워커»**
>
> ```
> 무엇이 바뀌나    묶음의 질의가 끊기면(빼 두기 · Pause · 다른 묶음을 겨눈 끊기가 이 묶음에 닿음 · 사람의 pg_cancel_backend)
>                그 묶음은 실패로 세지 않고 대기로 되감는다 — retry_count · last_failure 그대로, 같은 슬롯에서 다시 돈다
>                질의 상한(chain_statement_timeout_seconds)이 끊은 것과 맵퍼 오류는 전처럼 실패(기본 상한 1 이면 FAILED)
> 볼 줄          chain_worker.log:
>                  [slot <n> pid <P>] [Chain] tx '<열쇠>': its query was cancelled, not by the statement limit - its <N> event(s) rewound, not failed
>                  = 누가 이 묶음의 질의를 끊었다. 그 이벤트는 다시 돈다. 같은 열쇠로 계속 나오면 누가 계속 끊는 것 — pg_stat_activity 를 본다
>                빼 두기가 끊은 것은 전처럼:
>                  [Chain] tx '<열쇠>': <M> event(s) were set aside while it ran - left set aside; the other <N> rewound, not failed
> 급할 때        git revert <이 커밋> -> 체인 워커 재기동
> ```

---
> ## [10-08] **체인 대기열 줄 하나 = 슬롯 프로세스 하나 — 줄마다 slot_pid, × 나 그 pid 를 죽이면 그 줄만 멈춘다 — 이주 «없음» · 재기동 «체인 워커 · 서버»**
>
> ```
> 급할 때 — 증상마다 다른 스위치
>   순서가 틀어진 것 같다(같은 표의 저장이 뒤집힘 · 줄이 앞뒤로 섞임)
>                -> ingestion_settings.json 에 "chain_slots": 1   한 번에 한 줄, 재기동 없이 다음 바퀴부터
>   슬롯 자체가 안 뜬다 · 계속 죽는다 · 체인이 아예 안 돈다
>                -> git revert <이 커밋> -> 체인 워커 · 서버 재기동    chain_slots 1 로는 안 고쳐진다(슬롯 하나도 슬롯이다)
>
> 무엇이 바뀌나    체인 워커가 슬롯 프로세스 N 개(python -m chain.slots <n>)를 띄우고 대기열 줄을 맡긴다. 슬롯은 줄을 한 배치씩 돈다
>                큰 소급 줄 하나는 슬롯 하나만 잡고, 다른 줄은 다른 슬롯에서 돈다. 더 오래 기다린 줄이 있으면 배치 경계에서 그 줄이 슬롯을 받는다
>                두 슬롯이 같은 표를 동시에 쓰지 않는다 — 같은 표의 줄은 지금 도는 묶음 하나만 기다린다
> 값 칸          ingestion_settings.json 의 "chain_slots" (적지 않으면 2)
> 볼 곳          GET /admin/chain/queue 의 줄마다 "slot_pid" (그 줄을 쥔 슬롯의 pid, 없으면 null) 와 "chain_state"
>                chain_state.state 에 새 낱말 waiting_for_table — why.table 이 그 줄이 기다리는 표
> 끄기           그 줄의 × — 답의 slot_pid 가 멈춘 슬롯의 pid
>                또는 cmd 에서: taskkill /F /PID <slot_pid>
>                pid 를 죽이면 chain_worker.log 에 한 줄:
>                  [Chain] slot pid <P> ended (exit <C>) before finishing line <열쇠> - <N> waiting event(s) set aside; run them again with rerun_set_aside
>                  = 그 줄의 남은 대기 이벤트를 빼 두었고 그 줄은 다시 안 돈다. 다른 줄은 계속 돈다
>                다시 돌리려면 소급 탭의 rerun_set_aside (그 표 · 규칙)
>                10 초 안에: [Chain] slot <n> started, pid <새 pid>
> 빼 두기         표 · 규칙 · 거래로 고른 것(소급 연산 set_aside · outbox_triage --cancel)은 고른 이벤트만 뺀다
>                그 이벤트를 쥔 묶음이 도는 중이면 그 묶음의 질의만 끊고 되감는다 — 슬롯은 살아 그 줄을 이어 간다
>                chain_worker.log: [slot <n> pid <P>] [Chain] tx '<열쇠>': <N> event(s) were set aside while it ran - left set aside; the other <M> rewound, not failed
>                  = 같은 줄의 나머지는 시도 수 그대로 다시 돈다
>                이 줄이 없으면 끊을 질의가 없었던 것(맵퍼가 파이썬 일 중) — 그 묶음은 끝까지 돌았고 그 행은 «돌았음»(빼 둔 표시를 지움, 10-09):
>                  [slot <n> pid <P>] [Chain] tx '<열쇠>': <N> event(s) were set aside while it ran and it ran - they read as ran, not set aside
>                «the other <M> fail as the group did» 면 질의 끊김이 아니라 맵퍼 오류 — 나머지는 전처럼 실패 길(시도 1 셈)
>                표를 기다리던 묶음이 끊기면 ERROR 한 줄:
>                  [slot <n> pid <P>] [Chain] a batch of line <열쇠> raised - its events wait as they were and run again: (…QueryCanceled) …
>                  = 빼 두기가 그 기다림을 끊었다. 나머지는 시도 수 그대로 1 초 뒤 다시 돈다. QueryCanceled 가 아니면 진짜 예외 — 같은 줄이 계속 나오면 올린다
>                슬롯을 끄는 것은 줄 전체(× · 실행 Cancel · pid kill)뿐
> Pause 의 답     cancelled_pid -> cancelled_pids (끊은 pid 목록 — 체인 워커와 슬롯 전부)
> 로그           파일은 그대로 chain_worker.log 하나. 슬롯의 줄은 머리에 [slot <n> pid <P>] 가 붙어 거기 들어간다
> 재기동 뒤 볼 줄  chain_worker.log: [Chain] slot 1 started, pid … · [Chain] slot 2 started, pid …
>                                 [slot 1 pid …] [Chain] slot 1 up, pid …
>                대기열에 줄이 있으면: [Chain] slot 1 (pid …) runs line <열쇠>
>                /health 의 workers 에 chain-slot-1 · chain-slot-2
> ```

---
> ## [10-08] **대기열 줄 · 행마다 상태 낱말 하나와 그 근거 — 「도는지 · 멈췄는지 · 왜」 — 이주 «없음» · 재기동 «서버 · 체인 워커»**
>
> ```
> 볼 곳          GET /admin/chain/queue 의 줄마다 · GET /outbox/queue/rows 의 행마다 "chain_state": {"state", "why"} — 같은 함수 하나
>                /health 의 workers.chain 에도 도는 일이 있을 때 같은 칸
> 낱말 · 근거     waiting    아직 안 집힘                         why.waiting_seconds
>                running    그 줄의 묶음이 지금 도는 중            why.stage · moved_seconds(마지막으로 움직인 뒤 초) · elapsed_seconds
>                           stage 예: mapper · <규칙> -> <표> · page 3 · 1000 rows / write:<표>
>                stalled    도는데 300 s 넘게 안 움직임(/health 와 같은 임계)   why.stalled_on(무엇을 기다리나 — 아직 안 물었으면 null)
>                retrying   실패, 다시 시도 예정                   why.attempt · cap · last_failure(그 실패의 마지막 줄)
>                paused     Pause 중                             why.by · at · reason
>                set_aside · failed · done 은 끝난 행 — 두 대기열은 기다리는 것만 실어 거기 안 나온다
> 읽는 법        running 인데 moved_seconds 가 계속 커지면 그 단계에서 안 움직이는 것 — 300 s 를 넘으면 stalled 로 바뀐다
>                묶음이 규격(1,000 행 ≤ 5 s, 행 수에 비례)을 넘기면 chain_worker.log 에 한 줄:
>                  [Chain] group <tx>: <N> row(s) · view builds … · <초> s · MACHINERY · mapper <초> s · write:<표> <초> s … · INSIDE THE WRITE …
>                  = 그 묶음이 어디에 몇 초 썼나(정렬 없는 묶음도 이제 남는다)
> 바뀐 칸        그리드 행의 "chain_state" 가 문자열 -> {"state","why"} · "state_detail" 은 은퇴(why 안으로)
>                클라 착지 전에는 그리드 우측 대기열의 상태 칸이 그 객체를 그대로 보일 수 있다
> 급할 때        git revert <이 커밋> -> 서버 · 체인 워커 재기동
> ```

---

> ## [10-08] **메인 그리드 우측 대기열 = 어드민 대기열과 같은 «기다리는 것»만 · 빼 둔(×) 행은 알릴 것이 없다 — 이주 «없음» · 재기동 «서버 · 체인 워커» · 운영 SQL 한 번**
>
> ```
> 무엇이 바뀌나  그리드 우측 대기열(GET /outbox/queue/rows)이 기다리는 행만 싣는다 — 어드민 대기열과 같은 술어
>                × · 빼 두기로 끝낸 행은 broadcast_at 도 찍는다 — 「미전달」로 안 읽혀 그리드 · 미전달 스윕 · /health 미전달 나이에서 빠진다
> 운영에 이미 남은 행  재기동 뒤 한 번 (psql 또는 DB 도구):
>                UPDATE database_outbox SET broadcast_at = now()
>                 WHERE processed_chain = true AND status = 'SUCCESS' AND broadcast_at IS NULL
>                   AND payload->>'cancelled_by' IS NOT NULL;
>                답 UPDATE N = 빼 둔 채 「미전달」로 남아 있던 행 수(그리드에 남아 보이던 것). 0 이면 남은 것이 없었다
>                미전달 부분 인덱스(idx_outbox_undelivered) 위에서 돈다 — 큰 표 전체를 훑지 않는다
> 확인          × 를 누른 줄이 어드민 · 그리드 두 대기열에서 같이 사라진다
> 급할 때       git revert <이 커밋> -> 서버 · 체인 워커 재기동 (SQL 로 찍은 broadcast_at 은 되돌릴 필요 없음 — 알릴 것이 없던 행)
> ```

---

> ## [10-08] **대기열 줄 × 와 소급 실행 Cancel 이 «일 하나를 끈다» — 이미 끝난 소급의 대기 이벤트도 뺀다 — 이주 «없음» · 재기동 «서버»(체인 워커 코드는 안 바뀜)**
>
> ```
> 돌릴 것        서버 재기동 뒤 Overview 대기열에서 그 소급 줄(열쇠 = run_id)의 × 한 번
>                (소급 탭의 그 실행 Cancel 도 같은 함수 — 어느 쪽이든 한 번)
> 답의 뜻        {"run": "done", "skipped_events": N, "slot_pid": P}
>                run             그 실행의 상태 되읽기. done = 실행은 이미 끝났다 — N 이 그 실행이 넣어 두고 체인이 아직 안 먹은 이벤트
>                                cancel_requested = 넣는 중 — 실행이 다음 페이지에서 멈추며, 그 사이 넣은 것도 그 자리에서 뺀다
>                skipped_events  이번에 빼 둔 대기 체인 이벤트 수(지우지 않음 · cancelled_by=operator 표시). 0 = 그 줄에 기다리는 것이 없었다
>                slot_pid        그 줄을 쥔 슬롯 프로세스의 pid — 그 프로세스를 끈다, 쥔 슬롯이 없으면 null (10-08 슬롯, 전엔 cancelled_pid)
>                두 번 눌러도 안전 — 둘째 답은 skipped_events 0
> 취소로 끝난 실행  누가 멈췄든(× · Cancel · 앱 정지) 끝나는 자리에서 남은 대기 이벤트를 뺀다 — 이유 칸 「run <id> cancelled」
>                전엔 앱 정지로 끊긴 소급의 남은 이벤트를 재기동 뒤 워커가 먹었다(반쪽 소급이 조용히 돌았다)
> 확인          GET /admin/chain/queue 에 그 run_id 줄이 없다 · 다른 줄은 그대로 돈다
> 되돌리기       빼 둔 이벤트를 다시 돌리려면 소급 탭 rerun_set_aside(그 표 · 규칙) — 규칙마다 한 번, 연쇄 없음
> 급할 때        Pause 는 그대로 쓸 수 있다 · 코드 되돌리기는 git revert <이 커밋> -> 서버 재기동
> ```

---

> ## [10-08] **원장 소스의 read.exclude_when 에 값 조건 — 매핑 when 과 같은 철자 — 이주 «없음» · 재기동 «필요»(서버 · 체인)**
>
> ```
> 적는 법        read.exclude_when: [{"when": {"type": "bbox"}}]   — 그 칸이 bbox 인 행은 이 소스의 행이 아니다
>                값 여럿은 줄 여럿: [{"when": {"type": "bbox"}}, {"when": {"type": "ruler"}}] (하나라도 맞으면 제외)
>                같음만 · 키 AND · 숫자 1 과 1.0 은 같다(매핑 when 과 같은 견주기) · 그 칸이 빈 행은 값 조건으로 안 빠진다
>                {"column": …, "blank": true} 와 한 줄에 같이 못 쓴다(거절) · 빈 when 은 거절
> 이미 올라간 원자  선언만 바꾸면 이미 쓴 bbox 행의 원자는 그대로다. 그 행만 다시 번역해 거둔다 (server 폴더에서)
>                python -m ledger.backfill --source <소스> --scope-column <칸> --scope-values bbox
>                  = 미리보기 — 몇 행이 다시 도는지 · 무엇이 바뀌는지만 말하고 쓰지 않는다
>                python -m ledger.backfill --source <소스> --scope-column <칸> --scope-values bbox --apply
>                  = 그 행들의 원자를 거두고 다시 만든다(이제 제외라 만들 것 없음)
>                어림: python -m ledger census --source <소스> 의 excluded_but_indexed(첫 쪽 표본 — 같은 판정) · 미리보기의 행 수
> 급할 때       선언에서 그 줄을 지우면 된다(재기동 없이 다음 바퀴부터) · 코드 되돌리기는 git revert <이 커밋> -> 재기동
> ```

---

> ## [10-08] **copy_rows_with_hold 의 리스트 칸에 글자를 적으면 규칙 검사가 거절 — 이주 «없음» · 재기동 «필요»(서버 · 체인)**
>
> ```
> 무엇이 바뀌나  key_columns · columns 에 "c_bn" 처럼 글자를 적으면 저장 · 리로드 때 거절: columns must be a list, e.g. ["c_bn"]
>                전엔 실행 중에 글자로 쪼개져 'c', 'o' … 오류가 났다
> 고칠 것        chain_rules.json 의 그 규칙 params 를 ["c_bn"] 처럼 리스트로
> 볼 줄          [ChainRules] <규칙> refused (1): param_not_a_list <경로>.params.columns: columns must be a list, e.g. ["c_bn"]
>                  = 그 규칙만 로드에서 빠진다(다른 규칙은 그대로)
> 급할 때       git revert <이 커밋> -> 재기동 (검사만 빠짐 — 글자로 적은 규칙은 다시 실행 중에 실패)
> ```

---

> ## [10-08] **체인 대기열 «모든 줄»에 × — 이주 «없음» · 재기동 «필요»(서버 · 체인 워커)**
>
> ```
> × 의 뜻      「그 변경들로는 체인 규칙을 안 돌린다」. 원천 행은 그대로 · 원장 따라가기도 그대로 · 지우지 않는다
>             그 줄의 기다리는 체인 사건에 «운영자가 뺐다»(cancelled_by=operator · 사유)를 남긴다 — 비상 정지의 치워 두기와 같은 표시
>             도는 묶음이면 그 질의도 끊는다. 체인 전체는 멈추지 않는다
> 재기동       서버(× 라우트) · 체인 워커(빠진 줄을 안 집고, 끊긴 묶음이 표시를 안 덮음) — 소유자 몫
> 되돌리기     그 행들을 다시 돌림: 어드민 Retroactive 탭 「Run set-aside events again」 (표 · 규칙 · 트랜잭션 중 하나)
>             또는  python server/scripts/outbox_triage.py --rerun-set-aside --tables <표> --apply
> 볼 줄        [Chain] tx '<열쇠>' was set aside before it ran - N event(s), not run
>               = 워커가 이미 집어 둔 줄이었는데 × 가 먼저 닿았다 — 안 돌았다
>             [Chain] tx '<열쇠>': N event(s) were set aside while it ran - left set aside, not failed
>               = 도는 묶음에 × — 질의가 끊겼고 그 행은 «뺐다»로 남았다(재시도 없음). 이미 쓴 표는 남는다(묶음은 표마다 커밋)
> 감사         audit_logs 의 source_name = chain_queue_skip 한 줄(표마다) — 누가 · 열쇠 · 사건 수
> 소급 줄 ×     아직 시작 안 한(queued) 실행은 바로 cancelled — 게이트가 열리고 뒤의 실행이 다음 틱에 돈다
>             도는 실행은 전과 같이 «멈춰 달라»(cancel_requested)
> 같이 빨라짐    Retroactive 탭 「Set queued chain events aside」의 transactions 범위 — 대기열 전체를 읽던 것을 그 트랜잭션만
> × 는 소급 게이트 뒤에 줄 서지 않는다 — 다른 소급이 돌고 있어도 그 자리에서 답한다
> 대기열 화면    GET /admin/chain/queue 가 기다리는 행의 payload 를 «한 번»만 읽는다 — 줄 수와 무관하게 질의 몇 개로. 응답 모양 그대로
>             볼 것: 응답 머리 Server-Timing 의 db 시간 · 질의 수(재기 수는 보고서)
> 행 하나짜리 줄  outbox_id 칸(값)이 같이 온다 — transaction_id 의 «(no tx · outbox#N)» 글자는 옛 화면 몫으로 그대로
> ```

---

> ## [10-08] **많은 갈래가 «하나도 안 나오던» 걷기 — 앞 20 을 그리고 나머지는 덩어리 — 이주 «없음» · 재기동 «필요»(서버)**
>
> ```
> 무엇이 바뀌나  한 노드에서 한 술어로 fanout_limit(화면 20)을 넘는 갈래는 «앞 20» 을 그리고 나머지 수를 덩어리(bundles)에
>                덩어리 칸: count(본 먼 노드 수) · drawn(그린 수 — 새 칸). 앞 20 = 원장을 읽는 순서(최신 먼저)
>                연 덩어리(expand)는 같은 깊이에서 예산을 먼저 쓴다. 그래도 넘치면 그린 만큼 + 남은 것을 덩어리로
> 볼 것          웨이퍼 하나에 디펙 수천: 디펙 20 이 보이고 덩어리 «count 3000 · drawn 20». 열면 노드 상한(400)까지 그려지고 Truncated · nodes
> 뜻            덩어리 count 는 «읽은 범위 안의» 수다 — Truncated 에 claims 가 같이 뜨면 실제는 그보다 많다
>                깊은 곳의 덩어리를 여는 것은 클라 몫(주인 노드에서 한 걸음 이어 걷기) — 클라 착지 전에는 처음부터 다시 걷는 지금 방식
> 급할 때       git revert <이 커밋> -> 재기동 (넘친 갈래는 다시 하나도 안 그림)
> ```

---

> ## [10-08] **걷기 라우트 기본 엣지 상한 1200 -> 6000(걷기 상수를 부름) — 이주 «없음» · 재기동 «필요»(서버)**
>
> ```
> 무엇이 바뀌나  GET /api/ledger/subgraph 가 edge_limit · node_limit · hops 를 안 받으면 걷기 상수(ledger_subgraph.DEFAULT_*)로 걷는다
>                엣지 1200 -> 6000 · claims(원자 훑기) 2400 -> 6000 · 노드 400 · 깊이 12 는 같은 값
> 볼 것          걷기 응답 limits — edges 6000 · claims 6000. 잘리면 truncated 에 축 이름
> 뜻            「claims 2400 에서 잘림」이 사라지면 이 변경이 닿은 것. 같은 걷기가 여전히 비면 그건 갈래 묶음(fan-out) 쪽 — 다음 커밋
> 급할 때       화면이 느려지면 git revert <이 커밋> -> 재기동(1200 으로 돌아감)
> ```

---

> ## [10-08] **원장 따라가기가 «왜 섰는지» 스스로 말한다 · 운영 아닌 세상이 깨지면 그 세상만 live 끔 — 이주 «없음» · 재기동 «필요»(체인 · 서버)**
>
> ```
> 무엇이 바뀌나  따라가기가 live 세상의 선언을 컴파일하지 못하면
>                운영 세상(지금 운영 중인 세상 — 기본 default) -> 전처럼 따라가기 전체가 선다. 줄은 셋: 처음 · 10 분마다 · 풀릴 때
>                다른 live 세상 -> 그 세상만 live 를 끈다(worlds.json 이력에 사유) · 줄 하나 · 나머지 세상은 계속 따라간다
>                같은 선언 파일 · 같은 table_config.json 이면 다시 컴파일하지 않는다(같은 실패를 기억) — 같은 줄이 바퀴마다 쌓이지 않음
>                선언 화면 · 테스트 런이 table_config.json 변경도 본다(전엔 선언 폴더만 봐서 카탈로그가 바뀌어도 옛 «OK»)
>                거절된 소스의 테스트 런은 그 거절을 답한다(전엔 AttributeError … cursor_columns)
> 재기동         체인(따라가기) · 서버(화면) — 소유자 몫
> 볼 줄          [LedgerFollowUp] stopped: world default · declaration <파일> · every_source_refused · <소스>: <경로> <사유>; … (+N more); N event(s) waiting - nothing is followed until it compiles
>                  = 운영 세상 선언이 컴파일 안 됨. 그 파일의 그 소스를(또는 table_config.json 을) 고치면 다음 바퀴에 풀린다
>                [LedgerFollowUp] still stopped, 600 s: …  = 10 분째 그대로(대기 수 같이)
>                [LedgerFollowUp] flowing again: world default compiles, after N s stopped; N event(s) waiting  = 풀렸다
>                [LedgerFollowUp] live switched OFF: world <세상> · declaration <파일> · … - the other worlds go on. Next: … python -m ledger.backfill --world <세상> --catch-up
>                  = 그 세상만 꺼졌다. 고친 뒤 화면에서 Live 켜기(따라잡기가 저절로 돈다) 또는 server 폴더에서 그 명령
> 어드민         GET /runtime 의 ledger_followup 줄 — state flowing|stopped · 멈췄으면 world · said(위 문장) · since · depth(대기)
>                · switched_off(따라가기가 끈 세상과 그 문장 — worlds.json 이력에서 읽어 재기동해도 남음)
> 급할 때       git revert <이 커밋> -> 재기동. 꺼진 세상은 화면 Live 켜기로 다시
> ```

---

> ## [10-08] **체인 묶음의 SQL 문장 하나에 2 분 상한 — 이주 «없음» · 재기동 «필요»(체인)**
>
> ```
> 무엇이 바뀌나  체인 묶음의 트랜잭션마다(묶음이 시작할 때 열려 있던 것도) SET LOCAL statement_timeout (PostgreSQL 만)
>                문장 하나가 상한을 넘으면 DB 가 그 문장을 끊고, 그 묶음은 실패(지금 규칙대로 재시도 없이 FAILED), 체인은 다음 묶음으로 간다
>                리플레이가 깨운 묶음도 같다. 편집 회수가 끊기면 전처럼 그 줄만 오류로 남고 묶음은 성공한다
> 값 칸          ingestion_settings.json 의 "chain_statement_timeout_seconds" (파일 상한 두 칸과 같은 파일)
>                없으면 120 · null 이나 0 = 상한 없음(전과 같음) · 양수가 아닌 값은 120
>                바꾸면 다음 트랜잭션부터(재기동 없이)
> 재기동         체인 — 이 코드가 들어가려면 한 번. 소유자 몫
> 볼 줄          Transaction <tx> permanently failed: … 원인: [rules=<규칙> target=<표>] statement timeout · 120 s · stage <단계> - one statement of this group ran past chain_statement_timeout_seconds (ingestion_settings.json); the database stopped it
>                  = 그 묶음의 문장 하나가 상한을 넘었다. <단계>(mapper · write:<표> · edit retraction:<표> …)가 «어디서»다
>                  Chain 탭 실패 목록의 Reason 칸에 같은 문장, 다시 돌리기는 Retry. 같은 단계에서 또 끊기면 그 단계의 질의(인덱스)부터 본다
>                🔴 [ChainRetract] … the edit's withdrawal failed AFTER a committed write; old layers may remain: statement timeout · 120 s - …
>                  = 편집 회수가 상한에 끊겼다. 묶음은 성공, 그 원천 행이 먹이던 옛 층이 남았을 수 있다
> 걸지 않은 것   체인 프로세스의 다른 일 — 워커가 돌리는 리플레이 실행 · 원장 따라가기 · 행 세기. 파일 적재 상한과 API 요청은 그대로
> 급할 때       "chain_statement_timeout_seconds": 0 — 재기동 없이 전처럼 끝없이 기다린다
> ```

---

> ## [10-08] **로그아웃이 ADFS 로그인도 끝낸다 — 이주 «없음» · 재기동 «필요»(서버)**
>
> ```
> 무엇이 바뀌나  Log out 은 우리 세션을 먼저 지우고, 브라우저를 ADFS 의 로그아웃 주소(설정 문서의 end_session_endpoint)로 보낸다
>                POST /auth/logout 은 200 {"next": …} (전엔 204). 클라 버튼은 그 next 로 간다(204 를 받으면 전처럼 새로고침)
> 재기동        서버 — 소유자 몫
> 지금(IT 등록 전)  auth_config.json 에 post_logout_redirect_uri 를 «적지 않는다» -> ADFS 자기 «로그아웃됨» 화면에 멈춘다
> IT 에 등록할 주소  https://<서버>/auth/signed-out   — 로그인 돌아올 주소를 등록한 그 앱의 RedirectUris 에 더해 달라고
>                등록되면 auth_config.json 에 "post_logout_redirect_uri": "https://<서버>/auth/signed-out" (같은 값) · 재기동
>                -> ADFS 가 우리 Signed out 화면(Signed out + Sign in)으로 돌려보낸다
> 볼 줄          [sso] Signed out here only: the issuer's discovery names no end_session_endpoint, so the issuer's sign-in did not end.
>                  = 설정 문서에 end_session_endpoint 가 없다 — ADFS 로그인은 안 끝난다. Signed out 에 멈추고 Sign in 은 같은 계정으로 들어온다
>                [sso] Signed out here only: the issuer's discovery could not be read (…), so the issuer's sign-in did not end.
>                  = 그 순간 ADFS 설정 문서를 못 읽었다(프록시 · 네트워크) — 로그인이 되는지 먼저 본다
> 확인          <issuer>/.well-known/openid-configuration 에 "end_session_endpoint" 가 있는지
> 급할 때       스위치 없음. 되돌리려면 이 커밋을 되돌리고 서버 재기동(클라 버튼은 204 를 받으면 전처럼 새로고침)
> ```

---

> ## [10-08] **표 비우기 도구가 모든 표를 «선언된 표가 아닙니다»로 거절하던 것 고침 — 이주 «없음» · 재기동 «불필요»(스크립트)**
>
> ```
> 무엇     python server/scripts/empty_table.py <표> 가 명령으로 돌 때 table_config 의 표를 스스로 등록한다 — 전엔 0 개라 모든 표를 거절
> 할 일     git pull 만. 「공식 표 다시 채우기」 6 · 7 은 명령 그대로 — 먼저 등록하고 부르는 우회가 필요 없다
> 볼 줄     6 의 첫 줄  표 official_dt — 행 N · 칸 층 … = 고쳐졌다
>          거절: 'official_dt' 는 선언된 표가 아닙니다 (table_config) = pull 이 안 됐거나 table_config.json 에 그 표가 없다
> ```

---

> ## [10-08] **회사 로그인 «들어올 사람» 목록 — auth_config.json 의 users · 이주 «없음» · 재기동 «필요»(서버)**
>
> ```
> 무엇이 바뀌나  auth_config.json 에 users 칸이 있으면 그 이름들과 admins 만 화면 · API · 표 변경 방송(/ws)에 들어온다. 칸이 없으면 전과 같다(회사 로그인 되는 누구나)
> 적는 법       "users": ["kim@corp.test", "lee@corp.test"]   — name_claim 값 그대로, 대소문자는 무시(admins 와 같은 규칙). sample 에는 없다
> 재기동        서버 — 소유자 몫. 설정은 프로세스마다 한 번 읽는다
> 볼 기동 줄    [sso] ON - … Only the <N> name(s) on users (auth_config.json) and the administrators may come in.
>                  = 목록이 읽혔다. N 이 적은 이름 수와 같은지 본다. 이 문장이 없으면 users 칸이 없는 것(누구나)
>               [sso] ON - … users (auth_config.json) is not a list, so only the administrators may come in.   (경고)
>                  = 값이 목록이 아니라 admins 만 들어온다 — ["…"] 로 고치고 재기동
> 거절 줄       [sso] <이름> is not on the users list in auth_config.json - ask an administrator to add the name.
>                  = 그 사람이 로그인했거나 화면을 열었다. 세션은 안 만들어졌다. 넣을 사람이면 users 에 넣고 재기동
> 끄는 법       users 칸을 지우고 재기동 — 전과 같이 누구나
> ```

---

> ## [10-08] **하위 폴더 안의 다 쓴 파일은 옆 파일이 아직 쓰는 중이어도 들어간다 — 이주 «없음» · 재기동 «필요»(수집기)**
>
> ```
> 재기동        수집기(run_watcher) — 소유자 몫. 분리 안 한 배포(DECOUPLED 아님)면 수집기가 서버 안에서 도니 서버
> 무엇이 바뀌나  raws 밑 하위 폴더: 파일 하나가 1 초 동안 크기 · 수정시각 그대로면 그때 넣는다(전엔 폴더 «전체»가 1 초 그대로일 때까지)
>                빈 폴더 지우기는 전과 같이 폴더 «전체»가 조용할 때만. raws 바로 밑 파일은 그대로
> 볼 줄          [<표>] Tree ingestion deferred — <N> file(s) still being written after 600s, <M> finished file(s) dispatched: <폴더> (still writing: <이름 몇 개>; periodic sweep will retry)
>                  = 그 폴더의 다 쓴 파일 M 개는 넣었고, N 개는 아직 쓰는 중이라 두었다. 다음 점검(300 초)이 다시 본다
>                    N 이 늘 같은 이름이면 그 파일이 쉬지 않고 자라는 것 — 그 파일만 기다리고 있다
>                    M 이 0 이고 N 이 폴더의 파일 전부면 전과 같은 «아무것도 못 넣음»이다
>                [<표>] 📂 Tree ingested '<폴더>': … directory tree removed.   — 전과 같다(폴더 전체가 조용해졌을 때)
> 급할 때       하위 폴더 적재를 통째로 멈추기: config/ingestion_settings.json 에 "flatten_nested_dirs": false (다음 폴더 트리거부터, 파일은 그대로 남음)
>                전 동작(폴더 전체를 기다림)으로 되돌리기: 이 커밋을 되돌리고 수집기 재기동
> ```

---

> ## [10-08] **조인 값 쪽 행을 «아무 행도 안 가진 키»로 고쳐도 옛 칸을 거둔다 — 이주 «없음» · 재기동 «필요»(체인 워커)**
>
> ```
> 무엇이 바뀌나  고칠 때 회수가 «그 묶음에서 낸 행이 0» 인 규칙에도 돈다 — 그 규칙이 쓰는 칸을 선언(조인 take)이나
>                이 프로세스에서 마지막으로 쓴 칸으로 안다면. 낸 행이 있는 경우는 그대로
> 볼 줄          [ChainRetract] table=<원천 표> edited_rows=<N> … cells_withdrawn=<C> …   — 그대로(낸 행 0 인 묶음에서도 나온다)
>              [ChainRetract] <규칙>: 이 규칙이 무엇을 쓰는지 아직 모릅니다(이 프로세스에서 낸 행이 없음) — 고친 원천 행 N 개가 먹이던 옛 층을 거두지 않았습니다
>                 = 재기동 뒤 아직 행을 한 번도 안 낸 파일 맵퍼. 그 규칙이 한 번 행을 내면 다음부터 거둔다.
>                   그 사이 남은 옛 층은 그 규칙을 리플레이하면 거둔다(10-07 «옛 키 행 정리»와 같은 명령)
> 급할 때       스위치 없음. 되돌리려면 이 커밋을 되돌리고 체인 워커 재기동
> ```

---

> ## [10-07 밤 · ②③] **원천 행을 «고칠 때»도 그 행이 먹이던 칸을 거둔다 · @mapper 출력에 출처 기본 도장 · 회수 경고는 «그 규칙의 출력»으로 — 이주 «없음» · 재기동 «필요»(체인 워커)**
>
> ```
> 무엇이 바뀌나  출처를 찍는 규칙(낸 행에 origin_row_id 가 실린 규칙)이 고친 원천 행에 다시 돌면, 쓰기 뒤에 그 행이 찍은 층 중
>                «그 규칙의 칸»이고 «이번 쓰기가 그 원천 행으로 쓴 행 밖»인 것을 거둔다
>                보류 복사에서 좌표(키)를 고치면 옛 키 행에서 그 층만 빠지고 보류를 다시 센다 -> 원장에서 옛 키 원자가 빠진다
>                조인에서 값 쪽 행의 키를 고치면 옛 키로 채웠던 행의 가져온 칸이 빈다
>                같은 행의 다른 규칙 칸 · 사람 층 · 핀은 그대로. 키가 안 바뀐 수정은 거두는 것 0
>              지울 때는 그 원천 행이 «찍은 층»만 거둔다 — 같은 이름 층(chain_ingestion)을 쓰는 다른 원천 행의 칸은 이제 안 거둔다
>              @mapper 의 출력 행이 입력 행을 이어 왔으면(거르기 · 정렬 · reset_index 포함) 그 입력 행이 출처로 찍힌다
>                집계(groupby · agg)나 칸을 골라 새로 만든 표는 안 찍힌다
>              회수 경고는 그 규칙이 «이 프로세스에서» 낸 행에 출처가 없을 때만 — 재기동 뒤 아직 안 돈 규칙은 말하지 않는다
> 볼 줄          [ChainRetract] table=<원천 표> edited_rows=<N> groups=<G> cells_withdrawn=<C> protected_skipped=<P> rows_told=<R>
>                 = 고친 원천 행 N 개가 더는 안 먹이는 층 C 개를 거뒀다. 출처를 찍는 규칙이 고친 행을 받은 묶음마다 한 줄(0 이어도)
>              [ChainRetract] table=<원천 표> deleted_rows=<N> … — 지울 때, 그대로
>                 P(사람 층 건너뜀)는 이제 «실제 사람 층 수» — 전에는 칸 수 x 행 수의 곱이었다
>              [ChainRetract] <규칙>: 「<종류>」 규칙의 출력에 «어느 행에서 왔는지»가 실리지 않습니다 — …
>                 = 그 규칙이 쓴 칸은 원천 행을 지우거나 고쳐도 남는다. 맵퍼가 출력 행에 origin_row_id 를 실어야 한다
>              🔴 [ChainRetract] Table: '<표>' | TX: … | rule: <규칙> | the edit's withdrawal failed AFTER a committed write; old layers may remain
>                 = 쓰기는 들어갔고 거두기만 실패. 옛 층이 남을 수 있다 — 아래 «옛 키 행 정리»로 다시 거둔다
> 옛 키 행 정리  이 착지 «전»에 좌표를 고쳐 남은 옛 키 행은 두 규칙을 «이 순서로» 리플레이한다 (스크립트 리플레이는 다른 규칙을 안 깨운다)
>                1  conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <보류 다시 세기 규칙> --apply
>                2  conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <복사 규칙> --apply
>                🔴 순서를 바꾸면 옛 행의 값이 먼저 비고 보류는 agreed 인 채로 남아, 원장 후속이 그 행을 missing value 로 실패시킨다
>                   그때는 1 을 돌리고 python -m ledger followup --requeue-failed (server 폴더)
> 급할 때       스위치 없음. 되돌리려면 이 커밋을 되돌리고 체인 워커 재기동
> ```

---

> ## [10-07 밤 · ①] **입력 행을 지울 때의 회수를 표마다 한 번에 — 이주 «없음» · 재기동 «필요»(체인 워커)**
>
> ```
> 무엇이 바뀌나  입력 행이 지워지면 그 행이 먹인 칸을 거두는 일(체인 워커의 원장 후속)이 층 이름마다가 아니라 표마다 한 번에 돈다
>                보류 복사 1,000 행: 9.3 s -> 1.2 s (PG 박스 시험 수 · 풀 엔진, 운영 수 아님)
>                거둔 층 · 남은 층 · 보이는 값 · 감사 · 사건은 전과 같다. 다만 회수 사건이 표마다 한 거래로 묶인다(전에는 층 이름마다 한 거래)
>              운영자 회수(소급 withdraw · CLI)도 같은 한 벌을 지난다 — 답과 줄은 그대로
> 볼 줄          [withdraw] <N> source(s) claim <M> cell(s) across <R> row(s) in '<표>'
>                [withdraw] apply: <K> cell(s) withdrawn (... revealed another source, ... left empty, ... skipped as human-pinned)
>                 = 표마다 두 줄(전에는 층 이름마다 두 줄 — 1,000 행 삭제면 2,000 줄이었다)
>              [ChainRetract] table=<표> deleted_rows=… groups=… cells_withdrawn=… — 그대로
> 급할 때       스위치 없음. 되돌리려면 이 커밋을 되돌리고 체인 워커 재기동
> ```

---

> ## [10-07 밤] **모든 요청에 Server-Timing(total · db) · 느린 요청 한 줄 — 이주 «없음» · 재기동 «필요»(API)**
>
> ```
> 무엇이 바뀌나  모든 HTTP 응답 머리에 Server-Timing: total;dur=<ms>, db;dur=<ms>;desc="<N> queries"
>                db 는 «그 요청 안»에서 돈 질의의 시간 합과 수 — 워커 · 요청이 띄운 스레드의 질의는 안 들어간다
>              slow_request_ms 를 넘은 요청은 서버 로그에 한 줄
> 보는 법        브라우저 개발자 도구 -> Network -> 그 요청 -> Timing 탭(Server Timing) 에 total · db 가 보인다
>                total 이 크고 db 가 작다 = 파이썬 쪽 · db 가 total 에 가깝다 = 질의 쪽(queries 수가 크면 질의를 너무 많이 낸다)
> 적는 곳       server/config/server_settings.json (모양: server/config/sample/server_settings.json.sample)
>                 slow_request_ms   없으면 1000 · null 이면 줄을 안 남김(머리는 그대로) · 재기동 때 읽음
> 볼 줄          [Slow] <메서드> <경로> <상태> - 응답이 <N>ms 걸렸습니다 (예산 <B>ms) · db <D> ms · <Q> queries
>                 = 그 요청이 예산을 넘었다. 쿼리 문자열 · 바디는 싣지 않는다
> 급할 때       slow_request_ms 를 null 로 + 재기동 — 줄이 멈춘다(머리는 남는다)
> ```

---

> ## [10-07 밤 · 후속] **멈춘 수집 폴더 후속 — 적재 뒤 ANALYZE 에도 같은 잠금 상한 · 외부 소스 파일도 다음 스윕에 다시 · ingestion_settings.json 의 BOM — 이주 «없음» · 재기동 «필요»(감시자)**
>
> ```
> 무엇이 바뀌나  적재 뒤 ANALYZE(analyze_after_rows 를 넘은 파일)도 lock_timeout_seconds 를 넘게 기다리지 않는다 — 넘으면 ANALYZE 만 건너뜀, 파일은 SUCCESS
>                (같은 표에 CREATE INDEX CONCURRENTLY · VACUUM · 다른 ANALYZE 가 돌 때 폴더가 다시 멈추던 자리)
>              잠금 상한으로 실패한 외부 소스 파일도 raws/ 파일처럼 다음 외부 스윕이 다시 돌린다
>              ingestion_settings.json 에 BOM 이 붙어도 읽는다 — 전에는 경고 한 줄 뒤 모든 값이 기본값이었다
> 볼 줄          [<표>] ANALYZE skipped: <표> locked by waiting Lock:relation on pid <쥔 pid> (<앱>, <상태> …): <그 질의>
>                 = 그 표의 통계 갱신만 미뤄졌다. 다음 적재나 autovacuum 이 갱신한다. 할 일 없음
>                   같은 쥔 쪽이 줄마다 나오면 그 세션(인덱스 만들기 · VACUUM)이 끝났는지 본다
> 급할 때       lock_timeout_seconds 를 null 로 — 파일 쓰기와 ANALYZE 둘 다 전처럼 끝없이 기다린다
> ```

---

> ## [10-07 밤] **멈춘 수집 폴더 — 걸림 줄 · 스윕 줄 · 파일 쓰기 잠금 상한(기본 300 s) — 이주 «없음» · 재기동 «필요»(감시자)**
>
> ```
> 무엇이 바뀌나  감시자의 파일 쓰기 트랜잭션마다 lock_timeout(기본 300 s). 남의 잠금을 그보다 오래 기다리면 그 파일은 FAILED,
>                폴더 일꾼은 다음 파일로 간다. 그 파일은 봉인하지 않고 제자리에 둔다 — 다음 스윕이 마지막 커밋된 청크부터 다시 넣는다
>              걸린 파일은 걸림마다 «걸림 줄» 한 번, 폴더 일꾼이 도는 동안은 스윕(5분)마다 «처리 중 줄»
> 적는 곳       server/config/ingestion_settings.json (모양: server/config/sample/ingestion_settings.json.sample)
>                 lock_timeout_seconds       없으면 300(걸림 판정과 같은 수) · null 이나 0 = 상한 없음(전과 같음)
>                 statement_timeout_seconds  없으면 끔 — 켜면 문장 하나가 그보다 길 때 그 파일 FAILED(이건 봉인, 다른 실패와 같음)
>              값은 감시자 재기동 없이 다음 트랜잭션부터 읽는다. 숫자가 아닌 값은 «없음»으로 읽는다
> 볼 줄          [Watcher] ingest <파일>: stalled N s in <단계> (folder <폴더> · db pid <pid>) - waiting Lock:… on pid <쥔 pid> (<앱>, <상태> …): <그 질의>
>                 = 그 파일이 300 s 째 안 움직인다. 쥔 pid 의 앱 · 상태 · 질의가 원인. 걸림 한 번에 한 줄
>              [<표>] 📂 Tree ingestion of '<폴더>' has been running for N min (now: ingest <파일>)
>                 = 그 폴더 일꾼이 아직 돈다(스윕마다). now: no file = 폴더가 안정되기를 기다리거나 파일 사이
>              [<표>] ⏳ <파일>: waited past the lock timeout (300 s) in chunk K - waiting Lock:… on pid <쥔 pid> … (retry R) - left in place for the next sweep
>                 = 상한으로 FAILED. R 은 그 자리의 그 파일이 마지막 성공 뒤 «이번 전에» 잠금으로 실패한 횟수 — 첫 실패는 0
>                   (file_ingestion_logs.retry_count 와 같은 값)
> 값을 고칠 때   ⏳ 줄의 retry 가 계속 오르고 쥔 pid 가 매번 같은 앱 · 같은 질의 = 그 세션이 원인. 값이 아니라 그 세션을 본다
>              ⏳ 줄이 정상 쓰기(체인 · 소급 · 다른 파일)를 쥔 쪽으로 대고 한두 번 뒤 풀린다 = 상한이 짧다 — 늘린다
>              걸림 줄이 나온 뒤 ⏳ 까지 폴더가 막혀 있는 시간이 너무 길다 = 줄인다
> 급할 때       lock_timeout_seconds 를 null 로 — 전처럼 끝없이 기다린다(재기동 없이)
> ```

---

> ## [10-07 저녁] **SSO — 설정 파일 하나로 서버가 안 멈춘다 · 클라이언트 비밀은 선택(public client) — 이주 «없음» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  auth_config.json 을 못 읽어도(문법 오류 · 맨 위가 객체 아님) 기동은 계속된다 — SSO 는 OFF, 요청은 오늘처럼
>              BOM 이 붙어도 읽는다(table_config.json 과 같은 읽기)
>              클라이언트 비밀은 선택 — 없으면 public client(PKCE 만)로 코드를 토큰으로 바꾼다. 위 10-07 절의 «비밀 하나»는 이제 «있으면»
> 적는 곳       메모장은 BOM 없는 UTF-8로 저장, 틀리면 기동 로그 [sso] OFF 줄이 이유를 말한다
>              회사 가이드의 토큰 서명 인증서(.cer)는 넣지 않는다. 서버가 ADFS의 키 주소에서 받는다
>              비밀 없으면 public, invalid_client면 IT에 비밀 받기 — 받으면 환경변수 ASSY_OIDC_CLIENT_SECRET 에 두고 재기동
> 재기동 뒤 볼 줄  [sso] ON - issuer …, return address …, public client. …   = 비밀 없이 켜짐
>              [sso] ON - issuer …, return address …, secret client. …   = 비밀로 켜짐
>              [sso] ON - … admins (auth_config.json) is not a list, so no one is an administrator.
>                 = admins 를 ["이름", …] 목록으로 고치고 재기동. 그때까지 관리 화면은 아무도 못 쓴다
>              [sso] OFF - auth_config.json could not be read: line <줄> column <칸> (char …): <무엇>   = 그 자리를 고치고 재기동
>              [sso] OFF - auth_config.json could not be read: the top level is …, not an object       = 파일 전체를 { … } 하나로
>              [sso] OFF - enabled must be true (not "true") in auth_config.json                      = 따옴표 없이 true
> 거절 줄        [sso] The identity provider refused the sign-in: invalid_client - …   = ADFS 가 비밀을 원한다 -> IT 에 클라이언트 비밀 받기
>              화면에도 같은 문장과 Try again
> 급할 때       enabled false + 재기동 (오늘과 같음)
> ```

---

> ## [10-07] **소스에 묶은 속성이 그 개체의 칸이 된다(등록 문장 없이) · 등록 probe 은퇴 — 마이그레이션 «없음» · 재기동 «필요» · 다시 번역은 «부류 1» 소스만, 운영자가**
>
> ```
> 무엇이 바뀌나  소스 bind 의 개체 속성 — bind.entities.<타입>.attributes, 그리고 롤 자신의 attributes(목적어 롤 포함) —
>                을 번역기가 그 행의 시각으로 원장에 남긴다. 걷기 노드 칸과 이름표가 그것을 읽는다
>              등록 문장을 적어 둔 소스는 그대로 — 그 문장이 그 타입의 속성을 정한다
>              read.registration_probe 은퇴 — 읽는 곳이 없다. 적혀 있어도 거절하지 않는다
> 돌릴 명령     재기동 — run_app.bat 전체
>              부류 1 소스만, 이미 읽은 행에도 싣고 싶으면 (whole_source 는 화면 폼에 없어 명령줄):
>                 python server/ledger/backfill.py --source <소스> --whole-source              (미리보기 — 행 · 잃은 행 · 그 원자, 안 씀)
>                 python server/ledger/backfill.py --source <소스> --whole-source --apply --pace slow
>                 가지면 --world <가지> — 아래 재기동 줄의 (<세상>) 칸
> 재기동 뒤 볼 줄  [Ledger] re-stamped N cursor(s) whose declaration did not change: <소스> (<세상>): <옛> -> <새> (position stays …) | …
>                 부류 1  그 소스 항목이 " - the translator registers the bound attributes of <타입들>: rows read before carry none of them until this source is rescoped whole" 로 끝남
>                         = 새 행부터 속성이 실린다. 과거 행은 위 명령으로. 대상 소스 = 이 꼬리가 붙은 소스
>                 부류 2  그 꼬리 없이 끝남 = 등록 문장이 있던 소스의 다시 찍기뿐. 위치 그대로 · 다시 번역 0 · 할 일 없음
>              [Ledger] retired cell: sources.<소스>.read.registration_probe is read by nothing -- it can be deleted
>                 = 그 칸을 지워도 된다. 안 지워도 돈다
>              [Ledger] attributes not registered: sources.<소스> names <타입> through different keys (<롤들>), …
>                 = 그 타입을 부르는 롤들의 키 바인딩(키 순서 · 칼럼/상수 · 값)이 갈려 bind.entities 속성을 어느 개체에 실을지 모른다
>                   — 롤마다 자기 attributes 에 적는다. 바인딩이 같으면 롤이 둘이어도 한 개체라 실리고 이 줄은 안 나온다
> 뜻           다시 번역 전의 부류 1 소스 — 같은 개체라도 재기동 뒤에 읽은 행에서 온 속성만 보인다
> 급할 때       커밋 되돌리기 + 재기동. 이미 쓰인 등록 원자는 남는다 — 되돌린 코드로 그 소스를 통째로 다시 번역하면 거둬지는지는 안 쟀다
> ```

---

> ## [10-07] **회사 SSO 로그인(OIDC · ADFS) — 켜기 = auth_config.json + 환경변수 비밀 하나 + 재기동 · 이주 «불필요»(부팅이 표 셋을 만든다) · 재기동 «필요»**
>
> ```
> IT 에 받을 것   ADFS 애플리케이션 그룹 · 그 안의 서버 애플리케이션(= 클라이언트 ID) · 리디렉션 URI · 클라이언트 비밀
>               요청 scope 는 openid 하나. ADFS ID 토큰에 upn 이 기본으로 실리는지는 «아직 확인 못 한 사실» — 첫 로그인이 알려 준다(아래 거절 줄)
> 적는 곳        server/config/auth_config.json — 모양은 server/config/sample/auth_config.json.sample
>                 enabled      true 면 켬. 없거나 false 면 꺼짐(오늘 그대로)
>                 issuer       https://<adfs 호스트>/adfs — 끝점은 그 아래 /.well-known/openid-configuration 에서 찾는다
>                 client_id    서버 애플리케이션의 클라이언트 ID
>                 redirect_uri IT 에 등록한 주소를 «글자 그대로, 끝 / 유무까지». https 여야 켜진다
>                 name_claim   사람 이름으로 쓸 클레임 이름(대개 upn). 비워 두고 켜도 된다 — 첫 로그인 거절 문장이 토큰에 있는 클레임 이름을 보여 준다
>                 admins       관리 화면을 쓸 사람 — name_claim 으로 나온 값(대소문자는 안 가림 · 기록에는 토큰 철자 그대로)
>               환경변수 ASSY_OIDC_CLIENT_SECRET = 클라이언트 비밀. 파일에는 적지 않는다
> 켜기 전에       관리 토큰(X-Admin-Token)으로 관리 기능을 부르던 프로그램은 관리자 목록에 있는 사람의 개인 키로 바꾼다
>                 로그인 -> POST /auth/keys {"name": "<이름>"} -> 응답의 key 를 Authorization: Bearer <key> 로. 키는 그 응답에서 한 번만 보인다
>               워커는 바꿀 것 없음 — /internal/* 은 그대로 ASSY_ADMIN_TOKEN
> 재기동 뒤 볼 줄  [sso] ON - issuer … return address …                 = 켜짐
>               [sso] OFF - enabled is true but not set: <칸 이름>      = 그 칸을 채우고 재기동
>               [sso] OFF - redirect_uri (auth_config.json) is not an https address = https 앞단(10-01 nginx 절) 뒤에서만 켠다
>               [sso] OFF - enabled is not true in auth_config.json   = 꺼짐, 오늘 그대로
> 뜻            켜지면 /auth/* · /internal/* · /health 말고는 로그인해야 한다. 화면은 회사 로그인으로 갔다가 돌아온다
>               관리 라우트는 admins 에 있는 사람만 — /admin/* 에서 X-Admin-Token 은 안 받는다
>               기록의 «누가»는 로그인한 이름이다 — 로그인한 요청에서는 X-User 와 쿼리 user 를 안 읽는다
>               세션은 12 시간, 로그아웃하면 끝
> 거절 줄        [sso] Sign-in refused: name_claim in auth_config.json is '…', … Claims in the token: … = 목록 중 하나를 name_claim 에 적고 재기동
>               [sso] The identity provider refused the sign-in: <error> = ADFS 쪽 거절 — 화면에 같은 문장과 Try again
>               [sso] Sign-in refused: the ID token did not verify (…) = issuer · client_id 가 ADFS 와 맞는지 먼저
> 끄기           enabled false + 재기동. 꺼진 동안은 누구나 로그인 없이 들어온다(오늘과 같음)
> ```

---

> ## [10-07] **원장 선언 테스트 런에 원자 견본 — 읽은 행이 된 원자를 원장 철자 그대로, 쓰는지 · 버리는지와 함께 (총괄 026ced7f1) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        온톨로지 탐색기에서 소스 하나 테스트 런 -> 응답에 atoms_sample(최대 50) · truncated.atoms_sample · rows_sample[].row_id
> 뜻             atoms_sample 은 rows_sample 행들에서 나온 원자다(원자의 row_ids 가 그 행을 가리킴) — 실행 순서, 원장에 쓰는 철자
>                writes:false 면 drop_reason 이 게이트 거절 코드다(그때는 배치 전체). 원장에 이미 있는 주어의 등록 원자도 실행처럼 «쓴다»(10-07 고침)
>                rows_sample 은 이제 «원자 수를 낸 페이지»의 행이다 — 빈 머리를 건너뛰었으면 pages 가 2 이상
> 급할 때          이 커밋을 되돌리면 견본만 사라지고 rows_sample 이 첫 페이지로 돌아간다 — 쓰기 · 커서는 이 기능과 무관(0)
> 볼 것           테스트 런 한 번에 게이트가 쓰는 시간은 작다(샘플 선언 · 가짜 행 199 · 원자 398 에서 게이트 중앙값 4.8 ms) — 원장은 읽지 않는다
> ```

---

> ## [10-07] **체인이 datetime 칸이 있는 표에 쓰면 그 행이 다른 화면에 바로 뜬다 — 전체 새로고침으로 미뤄지지 않는다 (총괄 9eb902922 ① 여섯째) — 이주 «불필요» · 재기동 «필요»(체인 워커)**
>
> ```
> 재기동 뒤        datetime 칸이 있는 표를 체인 규칙이 채우게 한다(조인 · 파생) — 열어 둔 격자의 그 행이 바로 바뀐다
> 뜻             전에는 체인 묶음의 행 갱신 방송이 웹서버로 보내는 직렬화에서 datetime 으로 터져
>                broadcast_at 이 안 찍히고, 스윕이 닿은 표마다 «전체 새로고침»을 다시 보냈다(늦게, 행 단위가 아니라)
>                이제 체인도 다섯 격자 라우트와 같은 event_constants.upsert_item 으로 item 을 짓고, 칸은 모두 감싼 셀이다
> 급할 때          이 커밋을 되돌리면 그 표들의 갱신이 다시 늦은 전체 새로고침으로 간다 — 쓰기 자체는 그대로다
> 볼 로그 줄       [Chain Worker] Failed to send API notification: Object of type datetime is not JSON serializable
>                — datetime 칸 표에 체인이 쓴 뒤 이 줄이 더 안 나와야 한다
> ```

---

> ## [10-07] **datetime 칸이 있는 표 — 셀 메뉴(우선 소스 고정 · 원천 지우기)가 오류 없이 끝나고 다른 화면에 닿는다 (총괄 9eb902922 ① 연장) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        datetime 칸이 있는 표에서 셀 우클릭 -> 우선 소스 고정 / 원천 지우기 (한 칸 · 여러 칸)
>                 그 동작이 성공으로 끝나고, 다른 창(같은 표)에 바로 반영된다
> 뜻             전에는 쓰기는 커밋되고 «그 뒤» 방송 직렬화가 datetime 에서 터져 요청이 오류로 끝났다
>                이제 다섯 라우트(셀 쓰기 + 셀 메뉴 넷)가 방송 item 을 event_constants.upsert_item 하나로 짓는다
> 급할 때          이 커밋을 되돌리면 셀 메뉴 넷이 다시 오류로 끝난다 — 쓰기 자체는 그대로 들어간다
> ```

---

> ## [10-07] **datetime 칸이 있는 표의 셀 쓰기가 다른 화면에 닿는다 — 「Object of type datetime is not JSON serializable」 (총괄 9eb902922 ①) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        datetime 칸이 있는 표에서 아무 셀이나 고친다 — 다른 창(같은 표)에 바로 바뀐 값이 뜬다
> 뜻             전에는 쓰기는 들어가고 «방송»이 그 직렬화에서 터져 server.log 에 그 문장이 남고, 다른 화면엔 안 갔다
>                방송의 시각 칸은 격자를 다시 읽을 때와 같은 철자다
> 급할 때          이 커밋을 되돌리면 방송만 다시 실패한다 — 쓰기 자체는 그대로 들어간다
> ```

---

> ## [10-06] **새 체크아웃 · main 트리 — client2 에서 npm ci 한 번 (총괄 10-06 · 걷기 그래프 Cytoscape 132d4c6ee 뒤) — 이주 «불필요» · 재기동 «불필요»**
>
> ```
> 돌릴 것          cd client2 ; npm ci      (package-lock.json 그대로 설치)
> 뜻             걷기 그래프가 cytoscape · cytoscape-dagre 를 import 한다. 설치 전에는 그것을 부르는 하니스가 ERR_MODULE_NOT_FOUND
>                러너(check_harnesses.mjs)가 package.json 에 적혔는데 node_modules 에 없는 패키지를 이름으로 대고 이 명령을 낸다
>                node_modules 가 있는데 빠졌으면 빨강(BLOCKING) · node_modules 가 아예 없으면 「이 트리에서 못 잼」
>                빌드는 devDependency @dagrejs/dagre 도 읽는다(라이선스 파일) — 없으면 빌드가 그 이름을 대고 멈춘다
> 급할 때          dist 는 커밋돼 있어 화면은 설치 없이 뜬다 — 설치가 필요한 것은 하니스와 빌드뿐
>                미리보기 · dev 서버가 그 트리의 node_modules 로 떠 있으면 npm ci 가 EPERM 으로 멈추고 반쯤 지운다 — 그때는 npm install
> ```

---

> ## [10-06] **엔티티 label — 노드가 키 대신 선언한 이름으로 보인다 · 선언 초안의 «다시 도는 소스»가 지문으로 (총괄 03bc94b6b) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 선언           원장 선언 entities.<타입> 에 "label": ["step", ...] — 그 타입의 키 또는 attributes 이름
>                없는 이름이면 저장 · 로드가 그 이름을 대어 거절(unknown_id, bundle.entities.<타입>.label)
> 재기동 뒤        걷기(표 · 그래프 · 사실 상자)에서 그 타입의 노드 이름이 적힌 순서대로 값을 「 · 」로 이은 것
>                값이 없는 이름은 빠지고, 하나도 없거나 label 을 안 적으면 오늘처럼 키(「 / 」)
>                소스 지문은 안 움직인다 — 커서 · 원장 소급 0
> 초안 비용        엔티티 · 술어 초안 저장 버튼 옆 「Sources N · …」 의 N = 활성과 초안 사이에 커서 지문이 바뀌는 도는 소스
>                label · inverse_of 만 고친 초안은 「Sources 0 · Truly none」 (전에는 그 이름을 쓰는 소스를 다 셌다)
> 급할 때          label 을 지우면 오늘의 키 이름표 — 다른 것은 안 바뀐다
> ```

---

> ## [10-06] **이력 목록 — 접힌 줄은 사람이 쓴 로그가 대표, 세상마다 실패 수 (총괄 a40ec0283 · 클라 9cdbda108 제안) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        히스토리 사이드바 Global 탭(/audit_logs/recent)에서 고친 행과 그 원장 영수증이 한 트랜잭션인 줄을 본다
> 뜻             접힌 줄의 로그 하나가 «영수증이 아닌» 가장 새 로그 — 사람이 고친 값(옛 값 -> 새 값)과 그 사람
>                전에는 가장 새 로그라서, 영수증이 뒤에 쓰이니 사용자 칸이 [ledger] 였다
>                영수증만 있는 트랜잭션(백필 · 소급)은 전과 같이 가장 새 영수증
>                receipt_worlds 의 세상마다 failed = 그 세상 번역이 실패한 영수증 수 (화면 표시는 클라 착지 뒤)
> 급할 때          읽기만 하는 목록 — 이 커밋을 되돌리면 대표가 가장 새 로그로 돌아간다. 데이터는 안 바뀐다
> ```

---

> ## [10-06] **원장 선언 폼 — 엔티티 바인딩의 타입 칸이 «이름 · 칸» 둘 중 하나 (총괄 068c904a6 ② · 클라 먼저) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        원장 선언 화면에서 소스 문장의 subject/target 바인딩(kind entity)을 연다
> 뜻             Entity type 칸에 고르개 name / column — name 은 오늘의 이름 고르개, column 은 Type from · column 두 칸
>                이미 이름을 적은 바인딩은 name 으로, {"kind": "column", ...} 를 적은 바인딩은 column 으로 열린다
> 급할 때          이 커밋을 되돌리면 타입 칸이 이름 고르개만 — 칸 타입은 원문 편집기로 적는다(오늘 오전과 같음)
> ```

---

> ## [10-06] **설정 해석 보고서 — 소스 줄이 로더의 판정 그대로 (총괄 11d0b6b88) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        관리 화면 설정 해석 보고서(/admin/config/resolve) 원장 도메인의 소스 줄
> 뜻             fine = 로더가 세운 소스(「`<소스>` is read: …」, 은퇴한 것은 「is retired」)
>                rejected = 로더가 거절한 소스, 로더의 문장 그대로 · 선언이 컴파일 안 되면 파일 줄 하나
>                전에는 옛 문법 검증기로 재서, 지금 문법 소스를 전부 「failed validation」 으로 적었다
> 급할 때          읽기만 하는 보고 — 되돌릴 일 없음
> ```

---

> ## [10-06] **설정 해석 보고서 — 「No translator states …」 목록이 실제로 안 쓰는 술어만 (총괄 6142e81bc) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        관리 화면의 설정 해석 보고서(/admin/config/resolve) 원장 도메인
> 뜻             「No translator states the declared predicates …」 에 이제 «어느 소스 문장도 · 엔티티 참조도 안 쓰는» 낱말만
>                전에는 옛 문법만 읽어, bind.mappings 소스의 술어를 거의 다 「안 쓴다」고 적었다(샘플: 16 중 15, 참은 7)
> 급할 때          읽기만 하는 보고 — 되돌릴 일 없음
> ```

---

> ## [10-06] **칸에서 타입을 읽는 바인딩 — 표 머리의 emits 와 온톨로지 탐색기 선에도 (총괄 564a46193 ②) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        entity_type 을 {"kind": "column", ...} 로 적은 소스가 있으면
>                그리드 표 머리 「ledger source — <소스> · emits ...」 에 그 역할이 받는 타입들의 references 엣지가 같이 나온다
>                온톨로지 탐색기에서 그 바인딩에 받는 타입마다 선이 하나씩
> 뜻             원장이 실제로 받는 것(행마다 그 칸의 타입)과 화면의 목록이 같아졌다
>                칸 타입 바인딩이 없는 박스에서는 전과 같다
> 급할 때          읽기만 하는 화면 — 되돌릴 일 없음
> ```

---

> ## [10-06] **체인 규칙 run_in 을 목록에서 고른다 (총괄 ff60fe669 ② · 클라 4256feacb 뒤) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ⚰️ run_in 은 10-09 에 은퇴했다(총괄 72f419bd1) — 규칙은 체인 묶음에서 돈다. 느린 규칙은 rows_per_run: 1 · 맨 위 10-09 절
>
> ```
> 재기동 뒤        관리 화면 체인 규칙 응답(/admin/chain/rules/raw)에 "run_in": ["chain", "operation"]
>                규칙 폼의 run_in 칸(평면 · 통합 limits 둘 다)이 chain / operation 고르개
> 오타            저장 때 bad_run_in: run_in must be one of chain, operation, got '<값>' — 파일은 안 바뀐다
> 급할 때          쓰는 값을 바꾸지 않는다 — 원문 편집기로도 적을 수 있다
> ```

---

> ## [10-06] **선언 고치기 미리보기 — 칸에서 타입을 읽는 소스도 센다 (총괄 564a46193 ②) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        온톨로지 탐색기에서 엔티티 타입을 고치는 초안 -> 미리보기 비용 줄 Sources N
> 뜻             N 에 그 타입을 칸에서 읽을 수 있는 소스(술어가 그 역할에 그 타입을 받는 것)가 들어간다
>                칸 타입 바인딩이 없는 박스에서는 전과 같은 수
> 급할 때          읽기만 하는 미리보기 — 되돌릴 일 없음
> ```

---

> ## [10-06] **🔴 합치기가 빈 층을 안 남긴다 · 이미 남은 빈 층을 센다 (총괄 c773b0fed) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬 · 수집기 · 스케줄러)**
>
> ```
> 재기동 뒤        새 합치기(쓰기 문 · 키 고치기 --apply · 표기 소급)는 넘어가는 행에 없던 칸의 층을 만들지 않는다
> 센다(읽기만)      python server/scripts/count_absent_null_layers.py
> 세 수의 뜻        ① 비울 수 없는 쓴 이(파일 등)의 빈 층 — 전부터 세던 그 수(S-243-b), 판정 405 이전에 쌓인 부재
>                ② 합치기가 남긴 빈 사본, 비울 수 없는 쓴 이 — 부재로 확정. 이번 결함이 남긴 것
>                ③ 합치기가 남긴 빈 사본, 사람 · 체인 — 부재이거나 사람이 일부러 비운 칸의 사본. 구별이 안 된다
>                수마다 「가림」 = 그 칸에 값이 있는 다른 층이 있다 — 다음에 그 칸을 다시 계산하면 그 값이 지워질 수 있다
> 그래서          지우기가 정해질 때까지 합치기가 있던 표에 표기 소급을 다시 돌리지 않는다 — 세 수는 총괄께
> 급할 때          이 커밋을 되돌리면 빈 층이 다시 생긴다 — 되돌리지 않는다. 스크립트는 아무것도 쓰지 않는다
> ```

---

> ## [10-06] **실패한 규칙 작업의 기록이 잘리지 않음 (총괄 ff60fe669 ①) — 이주 «불필요» · 재기동 «필요»(API · 스케줄러)**
>
> ```
> 실패한 규칙 작업   Retroactive 실행 목록의 그 줄 error 가 JSON 으로 읽힌다(failed_at · reason · rules · tables · rows · row)
>                reason 이 길면 가운데가 … — 머리에 [rules=<규칙> ...], 꼬리에 올라온 오류
> 급할 때          쓰는 값을 바꾸지 않는다 — 되돌릴 일 없음
> ```

---

> ## [10-06] **표기 소급 — 접은 키가 다른 행의 키면 그 행으로 «합친다» (총괄 5ffa48232 · 소유자 「예」) — 이주 «불필요» · 재기동 «필요»(API · 스케줄러)**
>
> ```
> 순서            1 관리 화면 Retroactive 의 Fold stored values into the declared spelling 를 표 하나로 count(dry run)
>                2 문장에 N row(s) fold onto another row's key - the run merges each into that row
>                  (e.g. <옛 키> -> row <그 행> (<접은 키>); ...) 가 있으면 견본 셋을 열어 같은 것인지 본다
>                3 맞으면 run. 아니면 별칭 행이나 규칙을 고치고 1 부터
> 되돌릴 수 없음     합쳐진 행은 지워진다. 값 · 층은 받는 행으로 옮겨지고 감사 줄(collision_merge)이 남는다
>                받는 행에 사람이 적은 값은 그대로 남는다. 그 키를 가진 행이 없으면 모인 행 중 row_id 가 가장 작은 행이 받는다
> 돌린 뒤          실행 목록의 그 줄 result 의 rows_merged = 합친 행 수
>                같은 표를 다시 count -> fold onto another row's key 문장이 없어야 한다
> 급할 때          run 을 누르지 않는다 — count 는 아무것도 쓰지 않는다. 이미 합친 것은 되돌리지 못한다
> ```

---

> ## [10-06] **표기 규칙 collapse_repeats — 연달아 같은 마디는 하나로 (총괄 c1ddec935) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬 · 수집기)**
>
> ```
> 선언           notation_rules.json 칸에 {"write": true, "rules": {"collapse_repeats": "."}}
> 먼저 볼 것      그 칸의 미리보기 — 병합군에 a.b.b · a.a.b · a.b 가 한 줄로, folds_again 0
> 저장된 값       관리 화면 Retroactive 의 Fold stored values into the declared spelling 으로 그 표를 접는다(먼저 dry run)
> 거절이면        해석 보고서의 그 칸 줄: 'collapse_repeats' folds a value when it is written ...
>                (write 없음) · must be the one character that splits segments (값) · 'time' is the only rule
> 급할 때         그 칸의 collapse_repeats 를 지운다 — 몇 초 안에 다시 읽힌다. 이미 접어 저장한 값은 그대로
> ```

---

> ## [10-06] **선언 화면 — 엔티티 바인딩 타입 칸을 이름 고르개로 되돌림 (f1238d6ef 의 either 되돌리기, 총괄 긴급) — 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        원장 선언 화면에서 소스 · 문장의 subject/target 바인딩을 연다
> 뜻             Entity type 칸이 오늘처럼 이름 고르개로 그려진다(f1238d6ef 로 재기동했으면 그 칸이 비어 있었다)
> 칸에서 읽는 타입   선언 원본(JSON)에 {"kind": "column", "column": "<칸>"} 으로 적는다 — 폼은 아직 이름만
> 급할 때          이 커밋을 되돌리면 f1238d6ef 의 빈 칸이 다시 난다 — 되돌리지 않는다
> ```

---

> ## [10-06] **원장 — 엔티티 타입을 행의 칸에서 (총괄 b5b335f2e ④ · 7255b4918) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 재기동 뒤        기존 소스는 다시 번역하지 않는다 — 지문이 그대로(견본 6 · 이 박스 5 전후 같음)
>                그래서 체인 데몬 로그에 [Ledger] re-stamped ... cursor(s) 줄이 이번엔 안 나온다
> 칸 타입 소스를 더하면   후보 표의 확정 칸을 채운 행만 원자. 받지 않는 타입의 행은 거절 목록에
>                type_not_admitted (그 행의 칸 · 값 · 받는 타입을 문장에), 다른 행은 들어간다
> 급할 때          그 소스의 entity_type 을 이름으로 되돌리거나 소스를 retired — 다른 소스는 영향 없음
> ```

---

> ## [10-06] **체인 규칙을 작업으로 · LLM 으로 후보 뽑기 (총괄 b5b335f2e · be0abe305 · 92d0483e5) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬 · 스케줄러)**
>
> ⚰️ run_in 은 10-09 에 은퇴했다(총괄 72f419bd1) — 규칙은 체인 묶음에서 돈다. 느린 규칙은 rows_per_run: 1 · 맨 위 10-09 절
>
> ```
> 설치            LLM 을 쓸 때만: conda env assy_manager 에서 pip install openai
> 환경변수         ⚰️ 10-09 은퇴 — server/config/llm_config.json 하나에 적는다(맨 위 10-09 «LLM 선언 파일» 절)
> 재기동 뒤        run_in: operation 규칙의 트리거 표에 쓰면 체인 데몬 로그에
>                [Retroactive] queued run_id=<id> op=rule_rows params={'rule': '<규칙>', ...}
> 뜻              묶음이 맵퍼 대신 작업을 줄 세우고 다음 묶음으로 갔다. 스케줄러가 작업을 하나씩 돈다
>                관리 화면 Retroactive 의 Run a rule's queued rows 가 그 작업 — failed 면 error 의 reason 이
>                체인 격리와 같은 문장(LLM 답이 틀리면 LlmRefused: ...)
> 키 확인          로그에 키가 없어야 한다: 키 앞 여섯 글자로 grep -c -> 0
> 후보 표          extractor · evidence 두 칸을 table_config 에 더하기 전까지는 쓰기가 그 둘만 버리고 센다:
>                [Schema] Column 'extractor' is not declared in column_types for table '<후보 표>' ... DROPPED
>                (find_links 맵퍼도 같다 — 두 칸을 더하면 그 줄이 멎는다)
> 급할 때          규칙의 run_in 줄을 지우고 재적재 -> 체인 안에서 돈다(느린 맵퍼면 그 뒤 묶음이 기다린다)
> ```

---

> ## [10-06] **걷기 요청 이름을 한 자리에서 — 옛 철자 접고, group_by 는 키 이름도, 없는 이름 거절 (총괄 17b6337e4 · a588e5d80) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤     curl "http://<서버>:<포트>/api/ledger/subgraph?id=<노드 id>&group_by=type&measure=sum:inspected@1"
> 뜻           groups[].value 의 키가 "sum:inspected@1"(보낸 그대로)이고 값이 sum:inspected 와 같다
>             follow=processed_with@1 · collect=wafer@1 · seed_type=wafer@1 도 맨이름과 같은 걷기
>             없는 이름 -> 422, detail = {reason, argument(칸), unknown, declared, world}
>             group_by · measure 의 없는 이름은 전에 «빈 값»이었다 — 이제 422 value_name_not_declared
>             group_by=wafer -> 웨이퍼마다 무리(노드 keys 에서). value_sources 맨 앞이 "keys"
> 급할 때       git revert <이 커밋> -> 재기동 (옛 철자가 다시 빈 값, 없는 이름도 다시 빈 값, group_by=wafer 도 다시 빈 무리)
> ```

---

> ## [10-06] **서버와 화면은 함께 — 화면이 이름의 @ 를 더는 벗기지 않는다 (총괄 2c4093eac) — 화면 빌드 · 서버 재기동 «같이»**
>
> ```
> 무엇이 바뀌나  선언 화면 Version 줄 · 새 이름의 @1 제안 · 걷기 전선의 @ 벗기기가 없어졌다. 이름은 서버가 보낸 그대로
> 볼 것        pull 뒤 재기동 없이 화면만 쓰면 옛 서버와 이름 철자가 어긋난다 — 옛 서버는 선언을 x@1 로 보내고 follow=x@1 을 422
>             재기동 뒤(서버 f34f16892 이후) 걷기 화면에서 follow 를 골라 걸으면 200
> 급할 때       git revert <이 커밋> -> 화면 빌드 (화면이 다시 @ 를 벗긴다 — 옛 서버와도 맞음)
> ```

---

> ## [10-06] **노드 · 엣지 이름에서 @1 은퇴 · 세상마다 목록은 고른 순서 (총괄 4eb1fe98f · 5788bd81c · 4be010312) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 재기동 뒤 체인 데몬 로그   [Ledger] re-stamped N cursor(s) whose declaration did not change: ...
> 뜻          N = 운영 세상에서 도는 소스 수. 줄마다 (position stays ...) — 위치 · 원자는 그대로, 다시 번역 없음
>             다른 켜진 세상의 도장은 낡은 채 남지만 아무것도 막지 않는다
>             (맞추려면 python scripts/ledger_restamp_cursor.py --world <세상> --apply)
> 패널         원장 인입의 소스마다 도장(translator_ver)이 바뀌고, 차이 · 새 행 · 지워진 행은 재기동 전과 같다
> 확인         python -m ledger census   -> 새 행 · 수정 누락 · 지워진 행이 재기동 전과 같다
>             curl "http://<서버>:<포트>/api/ledger/declaration"   -> entities[].type 이 wafer 모양 (@1 없음)
> 걷기         world=<가>&world=<나> 로 걸으면 엣지 worlds · by_world 와 노드 attributes_by_world 가 둘 다 <가>, <나> 순서
> 파일         ledger_config.json 은 다음 저장 때 맨이름으로 다시 쓰인다 (그 전에도 읽기는 맨이름)
> 급할 때       git revert <이 커밋> -> 재기동. ⚠️ 그 사이 저장이 있었으면 파일이 맨이름이라 옛 코드가 거절한다
>             -> ledger_config.json 옆 backup 폴더의 저장 직전 파일을 같이 돌려놓는다
> ```

---

> ## [10-04] **걷기 응답의 노드 속성이 세상마다 (총괄 4e1e49fe9) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤     curl "http://<서버>:<포트>/api/ledger/subgraph?id=<노드 id>&world=<세상1>&world=<세상2>&hops=1"
> 뜻           nodes[].attributes_by_world = 속성마다 [{world, value, occurred_at, source_who}] — 고른 순서, 세상마다 한 줄
>              값은 그 세상의 원자에서 · 이름이 many(목록)인지는 걷기가 합친 선언(처음 고른 세상 우선)
>              attributes · attribute_conflicts 는 전과 같다 (세상들 가운데 한 값 · 값이 갈린 이름 수)
>              occurred_at null = 그 원자의 시각이 사건 시각이 아니다 (관계 선과 같은 규칙)
>              칸이 없는 노드 = 이 걷기가 그 노드의 등록 원자에 안 닿았다 (전과 같은 뜻)
> 급할 때       git revert <이 커밋> -> 재기동 (그 칸만 없어지고 다른 칸은 그대로)
> ```

---

> ## [10-04] **원장 census 가 새 행 · 고친 행 · 지워진 행을 따로 센다 (총괄 6091a7ae3 ② · ca68c7c48) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 재기동 뒤 (server 폴더에서)
>   python -m ledger census
> 뜻           줄마다 「표 … · 색인 … · 차이 … · 새 행 … · 수정 누락 … · 지워진 행 … · 지문 없음 …」
>              차이 = 표 행 − 색인 행(새 행과 지워진 행이 상쇄됨) — «남은 0» 이 아니다. 판단은 새 행 · 수정 누락 · 지워진 행으로
> 셋 중 하나라도 0 이 아니면 그 세상 따라잡기 (census 기록의 next_step 이 이 줄)
>   python -m ledger.backfill --world <세상> --catch-up
> 급할 때       git revert <이 커밋> -> 재기동 (census 가 다시 not_yet 한 칸 · 다음 걸음 --drifted)
> ```

---

> ## [10-04] **원장 배치 영수증이 세상을 댄다 (총괄 6091a7ae3 ③) — 이주 «불필요» · 재기동 «필요»(체인 데몬 · API)**
>
> ```
> 무엇이 바뀌나  후속 · backfill 이 남기는 영수증(감사 행, column_name = ledger_batch)의 new_value 에 "world" — 성공 · 실패 둘 다
> 볼 것        세상이 둘 이상 켜진 채 행 하나를 고치면 같은 트랜잭션에 영수증이 세상 수만큼, 줄마다 world 가 다름
>              (타임라인 줄에 세상이 보이는 것은 클라 착지 뒤 — 그 전에는 펼친 값에서)
> 급할 때       git revert <이 커밋> -> 재기동 (영수증에 world 칸만 빠짐)
> ```

---

> ## [10-04] **원장 후속의 고치기가 같은 행을 한 번만 번역한다 (총괄 6091a7ae3 ①) — 이주 «불필요» · 재기동 «필요»(체인 데몬)**
>
> ```
> 무엇이 바뀌나  고치기(EDIT)를 따라갈 때 거둘 것을 겨누려고 번역한 결과를 그대로 쓴다 — 전: 같은 행을 두 번 번역
> 잰 것        이 박스 시험 DB, 세상 하나 · 1,000 행 한 그룹 고치기 4.55~5.17 s -> 3.48~3.99 s (켜진 세상마다 그만큼)
> 볼 것        체인 데몬 재기동 뒤 원장 후속이 고치기에서 덜 밀림 — 쓰는 원자 내용은 그대로
> 급할 때       git revert <이 커밋> -> 체인 데몬 재기동
> ```

---

> ## [10-04] **세상은 따로 · 겹침은 걸을 때 · 실시간은 켜진 세상 전부 (총괄 092a6f9e5 · 71880678a · ee0f66e7b) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 재기동 뒤 볼 것  GET /admin/ontology-explorer/worlds -> live: {세상: true|false} (가지는 모두 true 로 시작)
>              체인 데몬 로그 [LedgerFollowUp] ... failed in world <세상> — 실패가 있으면 어느 세상인지 붙음
> 후속 비용      켜진 세상 수만큼 후속이 한 벌씩 — 이 박스 1,000 행 한 그룹에 세상 하나 ≈ 만들기 2.8 s · 고치기 4.9 s
> 뜻           큐가 밀리면 쓰지 않는 세상을 끈다 (화면 Live 끄기 = PUT /admin/ontology-explorer/worlds/<세상>/live {"live": false})
> 켤 때         화면 Live 켜기 -> 응답 run_id = 따라잡기 작업(ledger_catch_up) — 관리 화면 소급 작업 줄에서 끝 확인
>              손으로 (server 폴더에서)  python -m ledger.backfill --world <세상> --catch-up
> 뜻           꺼진 동안 생긴 행 · 고친 행 · 지운 행을 맞춤 — 끝나면 python -m ledger census --world <세상> 이 남은 0 · 수정 누락 0
> 급할 때       git revert <이 커밋> -> 재기동 (live 칸은 읽히지 않고, 이 커밋 뒤 만든 가지는 기본 세상 위에 선 것으로 읽힘)
> ```

---

> ## [10-03] **새 소스 backfill 이 같은 표의 다른 소스 사실을 한 번 더 쓰지 않는다 (총괄 5fec118bb) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 무엇이 바뀌나  python -m ledger.backfill --source X (와 화면의 다시 번역)가 X 만 번역 — 전: 그 표를 읽는 소스 전부를 거두지 않고 한 번 더
> 운영에 쌓인 것  먼저 센다 (PG · 원장 전체를 훑음 — 한가할 때)
>   SELECT source_who, sum(n - 1) AS extra FROM (
>     SELECT source_who, count(*) AS n FROM ledger_events WHERE supersedes IS NULL
>      GROUP BY source_who, source_raw_ref, occurred_at, predicate, subject_type, subject_keys,
>               coalesce(object_payload, '{}'::jsonb)
>     HAVING count(*) > 1) d GROUP BY source_who ORDER BY 2 DESC;
> 뜻           소스마다 «같은 행 · 같은 사실을 이미 말한 원자가 있는데 하나 더» 의 수 — 줄이 없으면 끝
> 고치기        센 소스마다 (server 폴더에서, 먼저 미리보기)
>   python -m ledger.backfill --source <소스> --whole-source
>   python -m ledger.backfill --source <소스> --whole-source --apply
> 뜻           그 소스의 원자를 거두고 행마다 한 번씩 다시 씀 — 위 SQL 을 다시 돌려 그 소스 줄이 사라지면 끝
> 급할 때       git revert <이 커밋> -> 재기동 (backfill 이 다시 표 단위 — 선언이 바뀐 뒤면 중복이 다시 생김)
> ```

---

> ## [10-03] **대조 저장의 빈 세상은 걸은 세상 이름으로 (총괄 71ecd8223 · 0c918c2eb) — 이주 «불필요» · 재기동 «필요»(체인 데몬)**
>
> ```
> 무엇이 바뀌나  world 를 비워 저장한 contrast_run 행 — 체인 맵퍼가 운영 세상을 «이름으로» 걷고 computed_at 과 같은 되쓰기에 world 를 적는다
>              world 를 적어 저장한 행은 그대로
> 재기동 뒤 볼 것 R&D 보드에서 Save contrast 한 번 -> 계산된 뒤 그 행의 world 칸 = 운영 세상 이름(GET /admin/ontology-explorer/worlds 의 operating)
> 뜻           빈 칸이면 체인 데몬이 재기동 전 코드로 돌고 있다
>              그 전에 빈 칸으로 남은 행은 그대로 — 다시 계산(리플레이)되면 그때의 운영 세상 이름이 적힌다
> 급할 때       git revert <이 커밋> -> 체인 데몬 재기동 (빈 칸으로 남고 걷기는 그때의 운영 세상)
> ```

---

> ## [10-03] **한 배치 안에서도 나중에 온 값이 이긴다 (총괄 9280922aa) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬 · 파일 감시)**
>
> ```
> 무엇이 바뀌나  층 시각(cell_sources.ingested_at)을 한 함수(crud.layer_instant)가 찍는다 — 한 프로세스 안에서 앞 찍기보다 반드시 뒤
>              한 배치에 같은 칸을 두 소스가 쓰면 뒤 항목이 칸 · 감사 · 아웃박스에 나간다(전: 같은 눈금이면 이름 순으로 앞 항목)
>              병합 사본은 사라지는 행 안의 원래 전달 순서대로 찍힌다 — 그 행이 보이던 값이 사본 사이에서도 이김
>              (같이) 모르는 세상을 물으면 거절 world_unknown 의 worlds 가 default 를 먼저 싣는다 (총괄 f1ad96964 ①)
> 재기동 뒤 볼 것 (스캔 — 한가할 때, PG)
>   SELECT count(*) FROM (SELECT 1 FROM cell_sources WHERE ingested_at >= '<재기동 시각>'
>    GROUP BY table_name, row_id, column_name, ingested_at HAVING count(*) > 1) t;
> 뜻           재기동 뒤 한 칸에서 시각이 같은 층의 묶음 수 — 0 이 정상(한 프로세스는 같은 시각을 두 번 안 줌)
>              0 이 아니면 두 프로세스가 같은 눈금에 같은 칸을 썼거나 재기동 전 코드가 돌고 있다
>              '<재기동 시각>' 없이 돌리면 지난날 동률이 남긴 묶음까지 센다 — 그 칸들은 이름 순 값을 보이고 있을 수 있다(고치지 않음)
> 급할 때       git revert <이 커밋> -> 재기동 (층마다 datetime.now() 로 돌아감 · 이미 찍힌 시각은 그대로)
> ```

---

> ## [10-03] **세상 목록은 어느 답에서나 한 모양 (총괄 e51e3e417) — 이주 «불필요» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  걷기 선언 답(/api/ledger/declaration)의 worlds 가 default 를 먼저 품고 operating 을 같이 싣는다
>              /tables · GET /admin/ontology-explorer/worlds 와 같은 함수(schema.world_listing)에서 나옴
> 재기동 뒤 볼 것  curl -s http://localhost:8080/api/ledger/declaration | python -c "import json,sys; d=json.load(sys.stdin); print(d['worlds'], d['operating'])"
> 뜻           ['default', ...가지] 와 운영 세상 이름 — 세상 목록 라우트 · /tables 의 같은 두 칸과 같아야 한다
>              worlds 에 default 가 없으면 재기동 전 코드가 돌고 있다
> 급할 때       git revert <이 커밋> -> 재기동 (선언 답이 가지만 싣던 모양으로 돌아감)
> ```

---

> ## [10-03] **원장 세상 — 운영 세상 한 칸 (총괄 e1f54cd72 · e67ef53f3 · 86d5061a0 · 2bb20ff56) — 이주 «불필요» · 재기동 «필요»(서버 + 워커 — 위 절과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  세상 이름 없이 읽고 쓰는 자리 전부(원장 후속 · 걷기 · 그리드 원자 보기 · 선언 읽기 · census)가 «운영 세상»을 따른다
>              배치 파일 config/ontology_worlds/worlds.json 이 없으면 운영 = 기본 (오늘 그대로)
> 확인         GET /admin/ontology-explorer/worlds
> 뜻           "operating": "default" 이면 오늘과 같다 · "history" 는 누가 언제 바꿨나
> 운영 바꾸기   PUT /admin/ontology-explorer/worlds/operating   본문 {"world": "<이름>"}   (엄격 관리자 토큰 · X-User 머리가 이력의 by)
>              되돌리기 = 같은 PUT 에 "default"
> 급할 때       worlds.json 의 "operating" 을 "default" 로 고치거나 파일을 지운다 -> 다음 요청 · 다음 후속 배치부터 기본
> ```

---

> ## [10-03] **합쳐져 사라진 행의 층 · 덮어쓰기 행도 같이 지운다 (소유자 10-03 · 총괄 a13fcf00c) — 이주 «불필요» · 재기동 «필요»(위 절과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  두 행이 한 키로 합쳐질 때(쓰기 · 핀 · rebuild_blank_business_keys --apply) 지워지는 행의 cell_sources · cell_overwrites 행도 지운다
>              전: 그 행의 층과 덮어쓰기가 행 없는 row_id 아래 남았다 — 아무도 안 읽음
> 운영에 쌓인 것  표마다, 먼저 센다 (PG)
>   SELECT 'cell_sources' AS side, count(*) FROM cell_sources m
>    WHERE m.table_name = '<표>' AND NOT EXISTS (SELECT 1 FROM "<표>" r WHERE r.row_id = m.row_id)
>   UNION ALL
>   SELECT 'cell_overwrites', count(*) FROM cell_overwrites m
>    WHERE m.table_name = '<표>' AND NOT EXISTS (SELECT 1 FROM "<표>" r WHERE r.row_id = m.row_id);
> 뜻           행이 없는 row_id 의 층 · 덮어쓰기 — 병합(7월부터)과 오늘 --apply 의 병합이 남긴 것. 값은 이미 임자 행에 있다
> 지우기        같은 조건으로 (센 뒤에)
>   DELETE FROM cell_sources m WHERE m.table_name = '<표>' AND NOT EXISTS (SELECT 1 FROM "<표>" r WHERE r.row_id = m.row_id);
>   DELETE FROM cell_overwrites m WHERE m.table_name = '<표>' AND NOT EXISTS (SELECT 1 FROM "<표>" r WHERE r.row_id = m.row_id);
> 급할 때       git revert <이 커밋> -> 재기동 (되돌리면 병합이 다시 층을 남긴다 · 지운 행은 돌아오지 않는다)
> ```

---

> ## [10-03] **같은 데이터를 다시 써도 행이 하나 더 생기거나 합쳐지지 않고, 합쳐진 껍데기 행은 표에 안 남는다 (총괄 e243d6abf ③ · d5cf3a954 · 829e3fe20 ④) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체 — 아래 절의 보류도 이것으로 풀린다)**
>
> ```
> 무엇이 바뀌나  ③ 조합키를 지을 때 각 조각을 그 칸이 저장하는 철자로 바꾼 뒤 잇는다
>                숫자 "1.0" · "01" · 1.0 -> 1   시각 -> 세션 존 벽시계 'YYYY-MM-DD HH:MM:SS'(마이크로초가 있으면 .ffffff)
>                전: 페이로드 철자로 지은 키와 저장된 값으로 다시 지은 키가 달라, 같은 행을 두 번 쓰면 껍데기 행이 생기고 합쳐졌다
>              ④ 이 배치에서 새로 만든 행이 병합되면 그 행은 표에 들어가지 않는다
>                전(fb9a0b649 만 재기동한 경우): 층이 하나도 없는 껍데기 행이 남았다
> 순서 (표마다)  ① 미리보기 — 읽기 전용, 아무것도 안 씀
>   python server/scripts/rebuild_blank_business_keys.py --table <표>
>              ② 재기동
>              ③ 고치기 — 키와 업무키 칸을 새 철자로 · 부딪히는 행은 그 키를 가진 행에 합침 · 행마다 감사 줄
>                 끝에 「고친 행 N / 미리보기 N · 합친 행 M / 부딪힘 M」 — 두 쌍이 같아야 한다
>   python server/scripts/rebuild_blank_business_keys.py --table <표> --apply --by <이름>
>              ④ 미리보기 다시 — rebuildable 0 · collides 0 이어야 한다
> 뜻           rebuildable  옛 철자 키를 가진 행 — 고치기 전에 같은 데이터가 오면 그 행을 못 찾고 «새 행이 하나 더» 생긴다
>              「키가 바뀌는 행 - 어느 조각」  number · datetime = 그 조각의 철자 때문 · not_iso = ISO 로 안 읽히는 시각 글자(그대로 둔다)
>                                            split = 저장 키가 조각 수대로 안 나뉨(구분자가 값 안에 있음)
>              collides     다시 지으면 다른 행과 같은 키 — --apply 가 그 키를 가진 행에 합친다 · 🔴 되돌릴 수 없다
>                           (견본 「이 행 -> 그 키를 가진 행 · 다시 지은 키」 · 셋 이상이면 row_id 순으로 하나로)
>                           앞 판(5416d3020)으로 ③ 을 이미 돌렸다면 남은 collides 가 있다 — 이 판에서 ③ 을 한 번 더 돌려 합친다
> 유령 행       fb9a0b649 로 이미 재기동했다면만 — 키가 있는데 층이 하나도 없는 행 (PG, 표마다)
>   SELECT count(*) FROM "<표>" r
>    WHERE r.business_key_val IS NOT NULL
>      AND NOT EXISTS (SELECT 1 FROM cell_sources s WHERE s.table_name = '<표>' AND s.row_id = r.row_id);
>              0 이 아니면 그 행의 값은 임자 행으로 이미 넘어가 있다 — 지울지는 총괄에게 올린다(이 착지는 지우지 않는다)
> 세션 존       psql 에서 SHOW TimeZone;  -> 'Asia/Seoul' 같은 이름이어야 한다
>              파이썬이 못 읽는 이름이면 시각 조각은 고쳐지지 않는다(naive 는 벽시계 그대로, offset 붙은 것은 UTC 로 적혀 둘이 갈린다)
> 급할 때       git revert <이 커밋> -> 재기동 (되돌리면 같은 행 두 번 쓰기가 다시 껍데기 · 합치기로 간다)
> ```

---

> ## [10-03] **병합과 쓰기가 한 배치에 섞여도 인제션이 터지지 않고, 층의 원천 행(origin_row_id)을 잃지 않는다 (총괄 1495534c9) — 이주 «불필요» · 🔴 재기동 «보류»**
>
> ```
> 🔴 지금 재기동하지 않는다 (총괄 829e3fe20) — 이 커밋만으로 재기동하면, 숫자 칸에 "1.0" 처럼 저장 철자와 다르게
>    온 같은 데이터를 두 번 쓸 때 인제션 오류 대신 «층이 하나도 없는 껍데기 행»이 표에 남는다
>    재기동은 키 철자(총괄 e243d6abf ③) + 껍데기 행 지우기(④)가 함께 착지한 뒤 한 번 — 그 절이 이 위에 올라온다
> 무엇이 바뀌나  키 조각이 다른 행의 키가 되어 병합이 나는 쓰기와 보통 쓰기가 한 배치에 있으면
>              전: CompileError「origin_row_id is explicitly rendered as a boundparameter」로 배치 실패, 또는
>                  오류 없이 그 청크 전부의 origin_row_id 가 NULL — 09-16 부터
>              뒤: 오류 0 · 쓰기의 origin 남음 · 병합이 넘겨받은 층은 껍데기 행 층의 origin 을 그대로 가짐
> 재기동 뒤     인제션 로그에 위 CompileError 가 더 안 나와야 한다
> 세는 SQL     조용히 잃었을 수 있는 체인 층 (PG, 표마다)
>   SELECT table_name,
>          count(*) FILTER (WHERE source_name = 'chain_ingestion') AS chain_layers,
>          count(*) FILTER (WHERE source_name LIKE 'chain_ingestion (%') AS merged_chain_layers
>     FROM cell_sources
>    WHERE origin_row_id IS NULL AND source_name LIKE 'chain_ingestion%'
>      AND ingested_at >= '2026-09-16'
>    GROUP BY table_name ORDER BY 2 DESC;
> 뜻           원천 행 하나를 못 대는 체인 쓰기도 NULL 이라, 이 수는 «잃었을 수 있는» 상한이다
>              NULL 인 칸은 원천 행이 지워져도 거둬지지 않는다(그 층이 남는다)
>              층 이름으로는 못 되살린다 — 병합 층의 괄호 속은 합쳐진 행의 키와 행 id 앞 6자이지 원천 행이 아니다
>              같은 값을 다시 써도 층은 다시 쓰이지 않아(값이 같으면 손대지 않음) 리플레이로도 안 채워진다
>              그 원천 행이 바뀌어 새 값이 오면 그때 채워진다
> 급할 때       git revert <이 커밋> -> 재기동 (되돌리면 섞인 배치가 다시 실패한다)
> ```

---

> ## [10-03] **table_config 를 다시 쓰는 스크립트 둘이 운영자가 적은 칸을 지우지 않는다 (총괄 338abb9f3) — 이주 «불필요» · 재기동 «불필요»(명령줄 도구)**
>
> ```
> 무엇이 바뀌나  install_product_tables.py --overwrite-drift — 제품이 말하는 칸만 되돌리고 group · kind · indexes · 더한 열은 남김
>              table_config_from_schema.py --merge     — 시트에 있는 표는 column_types · display_columns 만 바꾸고 나머지 칸은 그대로
>                                                        그 두 칸도 더하고 고칠 뿐 안 지움 — 시트에 없는 열은 남고(보고 「시트에 없음, 남겨 둠」) · 순서 · 숨긴 열 그대로 · 새 열은 끝에
> 확인         python server/scripts/install_product_tables.py            (드라이런, 아무것도 안 씀)
> 뜻           DRIFT 줄의 extra 는 현장이 더한 칸 — --overwrite-drift 로도 지워지지 않는다 · missing / changed 만 되돌아간다
> 급할 때       없음 — 두 스크립트 다 쓰기 전에 백업을 남긴다(install) · --merge 는 -o 초안 파일에만 쓴다
> ```

---

> ## [10-03] **두 행이 한 키로 합쳐질 때 — 핀은 터지지 않고, 사람 값은 사람이 쓴 칸에서만 이긴다 (총괄 6e041f4cb ①) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체, 위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  셀 핀이 키 조각의 보이는 값을 바꿔 키가 다른 행의 것과 같아지면 → 그 행에 합침(쓰기에서 부딪힐 때와 같은 한 병합)
>              전: 합칠 칸이 하나라도 있으면 오류(NameError: changed_cols) · 핀 전체가 되돌려짐 — 2026-07-17 부터
>              합칠 때 사람이 쓴 칸은 «이번에 쓴 칸»뿐(핀 = 핀 걸린 칸, 쓰기 = 그 항목의 칸) — 임자 행에 사람이 적은 값은 남는다
>              전: 사람이 키 조각만 고친 쓰기도 그 항목의 모든 칸을 사람 것으로 세어, 임자 행의 사람 값을 기계 값으로 덮을 수 있었다
> 확인         그리드에서 키 조각 칸의 숨은 층을 핀으로 골라 다른 행의 키와 같게 → 행이 하나로, 오류 없음
> 뜻           합쳐진 행: 핀 걸린 칸 = 핀이 고른 층 · 임자 행에 사람이 적은 값 = 그대로 · 지운 쪽 행에 사람이 적은 값 = 넘어옴
>              사람이 쓴 칸이 임자 행의 사람 값과 부딪히면 쓴 값이 보이고 옛 값은 그 칸의 user (old_exist_…) 층
>              그 전에 «먹지 않은» 핀이 있었을 수 있다 — 그 칸은 핀 전 층을 보이는 채. 다시 핀하면 이제 합쳐진다
> 급할 때       git revert <이 커밋> -> 재기동 (되돌리면 핀 충돌은 다시 오류로 되돌려짐)
> ```

---

> ## [10-03] **원장이 «소스가 안 읽는 칸»만 바뀐 수정을 다시 번역하지 않는다 (총괄 «소스가 안 읽는 칸» · 6e041f4cb ②) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체, 위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  그리드 · 체인 · 파서가 고친 칸을 사건에 싣는다(오늘도) — 그 칸 중 어느 것도 원장 소스가 읽는 칸이 아니면 그 소스를 건너뜀
>              다시 번역은 오늘처럼: 읽는 칸이 섞임 · 칸을 안 말하는 사건 · 새 행 · 지움 · 파이썬 맵퍼 소스
> 확인         python -m ledger followup        (server 폴더)
>              뜻: 「따라갈 일 N · 실패 M」 아래 「건너뜀 <소스> N 사건」 — 아웃박스가 지닌 동안(보관 7일) 그 소스가 건너뛴 사건 수
>              체인 워커 로그  [LedgerFollowUp] lap: … · skipped <소스>=<사건 수> (no column it reads changed)
> 뜻           원장에 있어야 할 값이 안 바뀌었는데 그 소스가 건너뜀에 있으면: 그 값의 칸을 선언(bind · read)이 이름 부르지 않는 것 — 선언을 고친 뒤
>                 python -m ledger.backfill --source <소스> --whole-source --apply     (server 폴더, 그 소스를 다시 번역)
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음 — 칸에 남은 «done · skipped» 는 «done» 과 같이 읽힌다)
> ```

---

> ## [10-03] **조합키만 선언한 표도 키 조각이 바뀌면 키를 다시 짓는다 (총괄 a3cd662d9 · a61d32f4f ㄱ) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체, 위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  business_key 칸 없이 composite_key_source 만 선언한 표 — 키 조각을 고치면 키를 다시 짓고 · 비우면 NULL · 남의 키와 부딪히면 병합
>              그리드 «행 추가» 빈 행에 키 칸을 채우면 키가 생긴다(전: 안 생겨서 다음 키 쓰기가 행을 하나 더 만듦)
> 확인         조합키만 선언한 표에서 «행 추가» -> 키 칸을 다 채움 -> 같은 키로 파일 · 체인이 한 번 쓰면 행이 하나 그대로
>              이 병이 남긴 행 수(읽기만):
>              SELECT count(*) FROM <표> WHERE business_key_val IS NULL AND <조각 칸마다 IS NOT NULL AND btrim(칸::text) <> ''>
>              박스 오늘: 키를 선언한 표 32 · 겹친 키 그룹 0 · 이 병의 행 0
> 뜻           0 이 아니면 그 행은 키 없이 남은 것 — 고치는 것은 소유자가 돌린다(지우거나 접는 명령, 기본은 읽기만):
>                 python server/scripts/rebuild_blank_business_keys.py --table <표>            (키를 다시 조립 — 부딪히는 키는 collides 로 냄)
>                 python server/scripts/dedupe_business_key_rows.py --table <표>               (그다음 겹친 행 접기 — 값이 다른 그룹은 건너뜀)
>              각각 --apply 를 붙여야 쓴다. 순서는 rebuild 먼저
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음)
> ```

---

> ## [10-03] **원천 행을 지우면 «가려진 값»이었어도 보류를 다시 센다 (총괄 e11bb4de0 (나)) — 이주 «불필요» · 재기동 «필요»(체인 워커 — 위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  지움 경로(원장 따라가기의 DELETE)가 층을 거둔 대상 행마다 EDIT 사건 하나 — 체인 채널 · 거둔 칸 이름
>              allow_chain_trigger 를 적은 규칙만 깬다(보류 다시 세기 규칙)
> 확인         같은 키에 값이 다른 원천 행 둘 -> 공식 행 hold 빈 값 -> «안 보이는» 쪽 원천 행을 지움 -> hold = agreed
>              체인 워커 로그  [ChainRetract] table=<원천 표> … rows_told=<행 수>
> 뜻           그 줄에 rows_told 가 없으면 이 판이 아님(체인 워커 재기동 안 됨)
>              rows_told 가 있는데 hold 가 그대로면 다시 세기 규칙이 꺼져 있음 — 다시 채우기 동안은 꺼 둔 것이 맞다(「공식 표 다시 채우기」 8 · 10)
> 급할 때       다시 세기 규칙 "enabled": false -> Reload Configs & Code (사건은 남고 그 규칙만 안 깬다)
>              코드는 git revert <이 커밋> -> 체인 워커 재기동
> ```

---

> ## [10-03] **쓰기 문 — 같은 묶음에서 만든 행을 다시 쓸 때 칸마다 묻지 않는다 (총괄 bce43236b) — 이주 «불필요» · 재기동 «필요»(위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  체인 · 그리드 · 파서 쓰기 문에서, 묶음이 방금 만든 행의 다음 항목(값 다음 보류)이 칸 이력을 칸마다 DB 에 묻지 않는다
>              결과(칸 값 · 층 · 출처 · 덮어쓰기 · 아웃박스 · 감사 줄)는 전과 같다 — 시험 스키마 비교
> 확인         재기동 뒤 체인 워커 로그의 그룹 줄에 쓰기 단계 시간이 찍힌다(write:<표> · row build …) — row build 가 전보다 짧다
>              시험 스키마 1,000 행 체인 그룹: 4.23 s -> 3.04 s (운영은 안 쟀다)
> 뜻           row build 가 그대로 길면 이 판이 아닌 것(재기동 안 됨) — 체인 워커 재기동 확인
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음)
> ```

---

> ## [10-03] **원장 읽기 — «표의 물리 칸» 은 한 함수가 답하고, 읽기마다 한 번 묻는다 (총괄 c8d6a8597) — 이주 «불필요» · 재기동 «필요»(위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  표의 실제 칸을 묻는 자리 셋(원장 선언 검사 · 칼럼 통계 · 원장 읽기)이 column_stats.physical_columns 하나로
>              원장 읽기는 그 물음을 페이지마다가 아니라 «읽기 한 번»(소스 · 배치)마다 한 번 (pg 시험의 한 읽기: 7 번 -> 1 번)
> 확인         할 일 없음 — 원자 · 지문은 그대로(박스 소스 다섯 · 샘플 소스 셋 전후 같음)
> 뜻           어느 소스가 「relation '…' does not exist in the current schema」 로 서면 그 표가 DB 에 없는 것(전에는 같은 경우 SELECT 오류)
> 급할 때       git revert <이 커밋> -> 재기동
> ```

---

> ## [10-03] **원장 census — 사람이 센 두 수가 주기 census 뒤에도 남고 · 기록이 다음 할 명령을 싣는다 (총괄 5baab7b8d · e1648e884) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체, 위 절과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  주기 census 가 기록을 쓸 때 사람이 센 rows_drifted · rows_unprinted 를 그때 시각 그대로 잇는다(전엔 지워져 Not measured)
>              census 기록에 next_step — 누락 있음: python -m ledger.backfill --source <소스> --drifted
>                                        사람이 센 적 없음: python -m ledger census --source <소스>   · 누락 0: 없음
> 확인         python -m ledger census --source <소스>   (server 폴더) -> 몇 분 뒤(주기 census 한 바퀴) 대시보드 원장 소스 패널
>              Edited, not followed 의 수와 Measured 시각이 사람이 센 그대로 남아 있어야 한다
>              python -m ledger census --source <소스> --json 의 그 소스 기록에 next_step
> 뜻           주기 뒤 Not measured 로 돌아가면 이 판이 아닌 것(재기동 안 됨) — 체인 워커 재기동 확인
>              Measured 시각이 주기마다 바뀌면 주기 census 가 두 수를 «다시 센» 것 — 표를 훑는 일이라 그러면 안 된다(보고)
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음 · 기록은 다음 census 가 다시 쓴다)
> ```

---

> ## [10-03] **원장 — 맵퍼는 그 표의 칸을 전부 받는다 · `map.input_columns` 은퇴 (소유자 · 총괄 2a8d9073c · 멈춤 둘 닫음 164553a6f) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  원장 읽기가 소스 표의 칸 전부(table_config.json 의 그 표)를 가져와 맵퍼에 넘긴다
>              ledger_config.json 의 map.input_columns 는 읽고 무시(지우지 않아도 된다) · 탐색기 폼에서 그 칸이 사라짐
> 확인         재기동 뒤 체인 워커 로그에 [Ledger] re-stamped N cursor(s) 줄이 «없어야» 한다
>              (박스: 소스 다섯 · 샘플 소스 셋 모두 지문이 그대로 · 같은 2,000 행에서 원자가 같음)
>              python -m ledger census --source <소스>   (server 폴더) — 수가 재기동 전과 같다
> 뜻           re-stamped 줄이 나오면 지문이 움직인 것 — 원자는 같아도 그 소스 커서가 한 번 다시 찍힌다(자리 그대로, 다시 읽는 행 없음)
>              로그 [Ledger] <표>: table_config declares <칸>, the table has no such column - not read (프로세스마다 한 번)
>                 = table_config.json 에는 있는데 DB 표에 없는 칸. 그 칸만 안 읽고 소스는 돈다 — 맞추려면 둘 중 한쪽을 고친다
>                 「column ... does not exist」 로 서는 것은 바인딩이 그 칸을 부를 때뿐(전과 같다)
>              행 단위 소스의 행 순서는 선언이 부르는 칸과 row_id 로만 — 다른 칸의 NUMERIC · DATE 값이 소스를 세우지 않는다
>              원자의 번역 버전(선언 전체 해시)은 재기동 뒤 새 원자부터 한 번 바뀐다 — 선언을 고칠 때마다 생기는 것과 같다
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음 · 옛 코드는 안 적은 input_columns 를 [] 로 채운다)
> ```

---

> ## [10-03] **원장 — 원장이 못 본 수정을 센다 · 그 행만 다시 번역 (총괄 bb9b1c19c (나) · c21cba507) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  원장 행 색인 줄에 «번역할 때의 행 지문». 칸은 원장 쓰기가 처음 돌 때 스스로 더함(로그 [Ledger] adding ledger_source_row_ref.row_fingerprint 한 번)
> 확인         python -m ledger census --source <소스>   (server 폴더) — 「표 · 색인 · 남은 · 수정 누락 D · 지문 없음 U」
> 뜻           U = 이 착지 전에 적힌 줄. 채우는 것은 필수 아님(새 세상 번역이 처음부터 적음)
>                 기본 세상에서 채우려면 소스마다 python -m ledger.backfill --source <소스> --whole-source --apply
>                 (이 박스 색인 행 1,215,824 · 시간은 총괄 율 1,000 행당 5.85 s 로 어림, 운영은 안 쟀다)
>              D = 원장이 못 본 수정(그 소스가 읽는 칸이 바뀌었는데 원장은 옛 값). python -m ledger.backfill --source <소스> --drifted 로 보고 --apply 로 그 행만 다시
>              D 가 다시 늘면 따라가기가 무언가를 놓친 것 — python -m ledger followup 의 실패 목록부터
> 급할 때       git revert <이 커밋> -> 재기동 (칸은 남아도 옛 코드가 안 읽는다)
> ```

---

> ## 🔴 [10-03 아침 고침] **원장 따라가기 — 대기열이 아웃박스 행으로 (총괄 bb9b1c19c (가) · a3d19dc51) — 이주 «필요»(앱을 «끄고») · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 순서          1 앱 끔       run_app.bat 전체를 닫는다 — 앱이 도는 중에 이주하지 않는다(쓰다 쉬는 세션이 이주를 붙잡는다)
>              2 이주 보고   python server/migrations/add_outbox_ledger_state.py
>                 뜻: server_version (11 이상이어야 칸 추가가 빠름) · column=ledger_state exists=False 면 아직 · index … valid=None 이면 색인 없음
>              3 이주        python server/migrations/add_outbox_ledger_state.py --apply
>                 뜻: 「added ledger_state - existing events 'done', N unprocessed back to NULL」 · 「idx_outbox_ledger_pending ensured」
>                    끝에 다시 찍는 보고에 done 이 거의 전부, <null = yet to follow> 이 N · index … valid=True
>                    「STOPPED at <단계>: waited 30s … pid … 」 면 그 pid 들이 아웃박스를 쥐고 있다(대개 아직 안 꺼진 앱) —
>                    그 세션을 끝내고(앱을 끄고) 3 을 다시. 칸은 이미 더해졌으면 그대로, 끊긴 색인은 지우고 다시 세운다
>              4 앱 켬       run_app.bat 전체 — 이주 «없이» 켜면 아웃박스 쓰기가 「column ledger_state does not exist」 로 실패
> 확인          python -m ledger followup     (server 폴더) — 「따라갈 일 K · 실패 F」. K 는 체인이 돌면 줄어들고, 일이 없으면 0
>              체인 워커 로그 [LedgerFollowUp] lap: N item(s) … M left in the queue — M 이 그 순간의 따라갈 일 수
> 뜻           실패 F 가 0 이 아니면 아래 목록에 이유가 찍힘 — 원인을 고친 뒤 python -m ledger followup --requeue-failed
>              K 가 줄지 않고 늘기만 하면 따라가기 루프가 안 도는 것 — 체인 워커 로그에 [LedgerFollowUp] batch failed 가 있는지
>              색인이 valid=True 가 아니면 따라가기가 매번 아웃박스를 훑는다 — 앱을 끄고 3 을 다시
> 급할 때       git revert <이 커밋> -> 재기동 (칸은 남아도 옛 코드가 안 읽는다 — 되돌릴 이주 없음)
> ```

---

> ## [10-02 밤] **원장 소스 선언 폼 — 기본값뿐인 read 는 접힌 한 줄 · exclude_when 칸 칩 · 비운 사건 시각은 Not an event (총괄 04cecc30f) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  탐색기 저작 계획(/admin/ontology-explorer/authoring/plan)에 read.exclude_when 줄이 선다
>              후보는 그 관계의 칸마다 {"column": <칸>, "blank": true}
>              매핑의 사건 시각 역할을 비우면 그 줄의 ground 가 not_an_event 「Not an event」
>              화면: read 가 Defaults · N 으로 접혀 시작 · Exclude when 은 칩만(마지막 칩을 빼면 키 지움)
>                    레코드 칩 글자는 후보마다 값이 다른 키만(read.occurred_at 칩도)
>              초안은 파일의 그 선언 그대로 연다(v5 파일은 로더의 v6 읽기 upgrade_setup 으로)
>              저장은 로더가 채우는 칸(read 기본값 · map.unit · map.input_columns)을 비워 둔다 — 계획이 채우는 다른 칸(implementation_version 등)은 전처럼 적힌다
>              map.unit 을 안 적은 소스의 Mapper unit 은 로더의 기본값(row, 묶는 소스는 group_by) — 빨간 칸 아님
>              이미 쓴 원장 · 원자는 안 바뀐다. 이미 적힌 선언은 다음 저장 때도 적힌 그대로
> 확인         관리자 화면 Ontology Explorer -> read 를 안 적은 소스 -> 초안 -> read 줄이 Defaults · N
>              펼쳐 Exclude when 줄을 열면 column · <칸> 칩
> 뜻           read 가 펼쳐져 있고 Exclude when 에 + Condition 만 있으면 재기동 전 서버(계획에 그 줄이 없음)
>              read 를 적은 소스는 펼쳐진 채 시작하는 것이 맞다(기본값이 아닌 칸이 있음)
>              read 를 안 적은 소스의 초안 편집기에 read 가 보이면 재기동 전 서버(초안이 기본값 채운 선언에서 열림)
> 급할 때       git revert <이 커밋> -> 재기동
> ```

---

> ## 🔴 [10-03 소유자] **공식 표를 제자리에서 비우고 다시 채우기 — 순서 전부 (총괄 35b76ba92 · 32bab7896 · 1472ec1cc · a3d19dc51) — 이주 «필요»(위 절, 앱을 끄고) · 재기동 «필요»(run_app.bat 전체, 한 번)**
>
> ```
> 0 코드        git pull — 복사 맵퍼 묶음(8990d408f) · 비우기 도구(81ffa8499) · 원장 따라가기 대기열(3bce75e88) · 이주 고침(이 커밋)
> 1 앱 끔       run_app.bat 전체를 닫는다
> 2 이주        python server/migrations/add_outbox_ledger_state.py --apply   (위 절의 2 · 3 — STOPPED 면 그 절대로)
> 3 표 설정      server/config/table_config.json 의 official_dt — composite_key_source 를 코어 칸으로 · column_types 에 "hold": "string"
> 4 원장 소스    config/ontology/ledger_config.json 에서 official_dt 를 읽는 소스의 read 에 "exclude_when": [{"column": "hold", "blank": true}]
> 5 앱 켬       run_app.bat 전체 — 3 · 4 를 한 번에 읽는다
>               확인: SELECT count(*) FROM information_schema.columns WHERE table_name = 'official_dt' AND column_name = 'hold'
>               뜻: 1 = hold 칸이 섰음 · 0 = 3 이 안 들어감(표 설정 파일 · 저장 위치를 다시 봄). 그리드 official_dt 에도 HOLD 칸이 보인다
> 6 비우기 보고   python server/scripts/empty_table.py official_dt
>               뜻: 행 · 칸 층 · 사람 층(비우면 사람이 고친 값도 같이 감) · 덮어쓰기 · 원장 소스와 원자 · 트리거 규칙. 아무것도 안 씀
> 7 비우기       python server/scripts/empty_table.py official_dt --apply --confirm-rows <6 의 행 수> --by <이름>
>               뜻: 「비움 … · 원자 N 거둠 · 아웃박스 이벤트 0」. 「거절: 지금 K 행」이면 그 사이 표가 움직임 — 6 부터 다시
>                  「비움」 줄 뒤 「원자 거둠」 전에 오류로 멈췄으면 표는 이미 빔 — 소스마다 python -m ledger.backfill --source <소스> --whole-source --apply (server 폴더)
>               시간: 시험 스키마 10,000 행(칸 층 80,000 · 원자 10,000) 1.03 s -> 100만 어림 103 s (운영은 안 쟀다)
> 8 체인 규칙 둘  config/chain_rules.json 에 RELEASE_LOG 「보류 포함 행 복사」의 두 규칙(둘 다 "is_batch": true) — 다시 세기 규칙 official_dt_hold_recount 에는 "enabled": false
>               까닭: 켜 두면 복사가 공식 행에 쓸 때마다 다시 세기가 한 번 더 돈다(세기 질의가 한 번씩 더) — 다시 채우기 내내
>               -> 어드민 Reload Configs & Code (체인 탭 편집기로 저장하면 그 자리에서 다시 읽음)
> 9 다시 채우기   python server/scripts/chain_replay_cli.py replay dt_log_to_official_dt --apply
>               뜻: 이벤트를 1,000 행씩 쌓고 바로 끝남. 복사는 체인 워커가 돈다 — 그동안 다른 체인 일은 그 뒤에 줄 선다
>               시간: 시험 스키마 10,000 행에 체인 64.89 s · 원장 21.59 s((가) 위, 운영 같은 연결 풀) -> 100만 어림 약 2.4 시간 (운영은 안 쟀다)
> 10 다시 세기 켬  체인 대기열에서 9 의 줄이 사라지면 official_dt_hold_recount 의 "enabled": false 를 지우고 Reload Configs & Code
> 11 확인        체인 대기열 화면 — 9 는 «한 줄»(잡 하나), 다 돌면 없음
>               SELECT count(*) FROM official_dt WHERE hold IS NULL OR hold = ''    -- 같은 키 원천 행들의 값이 갈린(또는 원천이 없는) 공식 행 수
>               python -m ledger census --source <official_dt 를 읽는 소스>        (server 폴더) — 「표 N · 색인 N · 남은 0」이어야
>                  남은 이 0 이 아니면   python -m ledger.backfill --source <그 소스>   (색인에 없는 행만 번역)
>                  색인이 표보다 크면    그만큼 «표엔 없고 색인엔 있는 행» — python -m ledger.backfill --source <그 소스> --whole-source --apply
>               python -m ledger followup (server 폴더) — 「따라갈 일 0 · 실패 0」이어야. 실패가 있으면 이유를 고치고 --requeue-failed
> 급할 때       9 를 멈춤: python server/scripts/chain_pause_cli.py pause --reason "다시 채우기 멈춤" (다시: ... resume)
>               규칙 둘을 "enabled": false -> Reload Configs & Code
> ```

---

> ## [10-02 밤] **표 통째로 비우기 — server/scripts/empty_table.py (총괄 35b76ba92) — 이주 «불필요» · 재기동 «불필요»(새 명령)**
>
> ```
> 무엇          표 하나의 행 · 그 표의 칸 층 · 덮어쓰기를 한 트랜잭션에 지우고, 그 표를 읽는 원장 소스의 원자를 거둔다. 아웃박스 이벤트 0
>              내일 공식 표 다시 채우기의 «순서 전부»는 다음 착지(복사 맵퍼 묶음)의 RUN.md 에 들어간다
> 보고          python server/scripts/empty_table.py <표>
>              뜻: 행 · 칸 층 · 사람 층(비우면 사람이 고친 값도 감) · 덮어쓰기 · 원장 소스와 원자 · 트리거 규칙. 아무것도 안 씀
> 비우기        python server/scripts/empty_table.py <표> --apply --confirm-rows <보고의 행 수> --by <이름>
>              뜻: 「비움 … · 원자 N 거둠 · 아웃박스 이벤트 0」. 「거절: 지금 K 행」이면 그 사이 표가 움직임 — 보고부터 다시
>                 「비움」 줄 뒤 「원자 거둠」 전에 오류로 멈췄으면 표는 이미 빔 — 소스마다 python -m ledger.backfill --source <소스> --whole-source --apply (server 폴더)
>              시간: 시험 스키마 10,000 행(칸 층 80,000 · 원자 10,000) 0.99 s -> 100만 어림 99 s
> 급할 때       없음 — --apply 전에는 아무것도 안 쓴다
> ```

---

> ## [10-02 밤] **보류 포함 행 복사 맵퍼 copy_rows_with_hold (총괄 3211e9000 · 3ba1d1dd4) — 이주 «불필요» · 재기동 «필요»(체인 워커)**
>
> ```
> 무엇이 바뀌나  제품 맵퍼 하나(server/mappers/hold_copy.py, 추적됨). 제품 코드는 그대로
> 쓰는 법       RELEASE_LOG 「보류 포함 행 복사」 예시 — 대상 표에 hold 칸 · 규칙 둘(복사 · 보류 다시 세기) · 원장 소스 exclude_when 한 줄
>              내일 공식 표 다시 채우기 순서는 다음 착지(빠른 비우기)의 RUN.md 에 «전부» 명령으로 들어간다
> 확인         재기동 뒤 체인 규칙 화면에서 두 규칙에 거절이 없는지 · 원천 행 하나 저장 -> 공식 행 hold = agreed
>              같은 키에 값이 다른 원천 행 하나 더 -> hold 빈 값 · 원장에서 그 행 원자가 거둬짐
> 뜻           hold 빈 값 = 같은 키 원천 행들이 다른 값 묶음 둘 이상
>              원천 행을 지운 뒤에도 빈 값이면: 남은 원천 행들이 아직 갈린 것(가려진 값을 지운 경우는 10-03 e11bb4de0 착지로 다시 셈)
>              그 착지 «전»에 지운 행이면 다시 세기 규칙을 그 행에 리플레이
>              python server/scripts/chain_replay_cli.py replay official_dt_hold_recount --row-ids <공식 행 row_id> --apply
> 급할 때       두 규칙을 enabled: false (또는 chain_rules.json 에서 지움) -> 체인 워커 재기동
> ```

---

> ## [10-02 저녁] **메인 그리드 — row_id 가 있는 표 끝에 ROW_ID 칸 · 그 칸으로 거르기 (총괄 e67ef53f3 · d692af408) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  GET /tables/{표}/schema 의 columns 가 created_at · updated_at 뒤에 row_id 로 끝난다 — 그 관계의 모델에 row_id 가 있을 때만
>              (모든 표 · row_id 를 선언한 보기. display_columns 에 이미 적은 표는 그 자리)
>              row_id 없는 보기에 row_id/id 거르기 -> 422 「'<표>' has no row_id, so it cannot be filtered by 'row_id'」
>              화면: 메인 그리드 맨 오른쪽 ROW_ID 칸, 머리 아래 거르기 칸. 맵 편집기 X · Y · Val 고르기에는 시스템 칸이 안 나옴
> 확인         curl -s http://localhost:8080/tables/<표>/schema  -> columns 의 마지막이 "row_id"
> 뜻           표에서 마지막이 updated_at 이면 재기동 전 서버. row_id 를 선언 안 한 보기는 updated_at 으로 끝나는 것이 맞다
>              화면에 ROW_ID 칸이 없으면(표에서) 화면 새로 받기 전
> 급할 때       git revert <이 커밋> -> 재기동. 화면은 row_id 가 안 오면 그 칸을 안 그린다
> ```

---

> ## [10-02 밤] **원장 소스 — 시각은 사건 엣지에만 · read 는 안 적어도 됨 (총괄 0c9b6e3c0) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  bind.occurred_at 을 안 적은 매핑 = 사건 엣지 아님(원자 basis 'ingested', 저장 시각은 같은 행의 사건 시각 — 사건 id 하나)
>              read 칸을 안 적으면 제품이 채움(unit · identity · order_by · group_by · occurred_at · map.unit · input_columns)
>              적은 선언은 그대로 — 박스 미리보기 5 소스 · 원자 1,198 가 전후 같음(사건 id · 시각 · basis · 번역 버전), 묶음 해시 같음
> 확인         재기동 뒤  python -m scripts.migrate_ledger_slim_sources   (미리보기, 아무것도 안 씀 — server 폴더에서)
> 뜻           「movable - atoms unchanged」 옮겨도 원자가 같다 · 「movable - atoms change」 옮기면 시각 · 사건 id 가 바뀐다
>              이 박스 선언은 setup_version 5 라 미리보기만 된다 — 옮기려면 먼저 v6 이주
> 옮기기       --apply --source <소스>  (고른 소스만)
>              박스에서 `dt_job` 을 옮기면 원자 866,192 개의 시각과 사건 id 가 바뀌고, 다시 번역은 원천 행 535,559 × 1,000 행당 5.85 s(박스에서 잰 율) ≈ 52 분입니다.
>              그 소스는 --change-atoms 를 같이 주고, 뒤에 python -m ledger.backfill --source dt_job --whole-source --apply
>              --drop-retired  아무도 안 읽는 옛 바인딩 칸(approval_status) 지우기 — 묶음 해시가 한 번 바뀜(새 원자만 새 번역 버전)
> 급할 때       git revert <이 커밋> -> 재기동
> ```

---

> ## [10-02 저녁] **메인 그리드 표 드롭다운 — table_config 의 group 으로 묶기 + 검색 (총괄 685f236d7) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  GET /tables 에 groups 가 붙는다 — {표: 묶음}, group 을 안 적은 표는 없음. tables 목록은 그대로
>              화면: 표 드롭다운이 그 묶음 이름 아래로 묶이고(Other 맨 아래), 앞에 검색 칸(Search tables)
> 확인         curl -s http://localhost:8080/tables  -> 키에 groups 가 있다
> 뜻           groups 가 {} 이면 아직 아무 표도 group 을 안 적은 것 — 드롭다운은 오늘처럼 묶음 없는 목록(정상)
>              묶으려면 server/config/table_config.json 의 그 표 항목에 "group": "이름" 한 줄 -> 재기동(어드민 Reload Configs & Code 로도 되는지는 안 쟀음)
>              groups 키 자체가 없으면 재기동 전 서버
> 급할 때       git revert <이 커밋> -> 재기동. 화면은 groups 가 없으면 오늘 모양이라 서버만 되돌려도 된다
> ```

---

> ## [10-02 저녁] **원장 — 시각 값 문장이 사건 시각 대신 바인딩한 칸 값을 싣는다 (총괄 0c9b6e3c0 ③) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  value_type "timestamp" 술어를 declarative-role 로 번역하면 값 = bind.value 의 칸(전에는 사건 시각)
>              폼: basis 소스의 그 값 칸에서 「This square is not read」가 빠진다(occurred_at 칸은 그대로)
> 확인         grep -n '"value_type": "timestamp"' server/config/ontology/ledger_config.json
> 뜻           안 나오면 할 일 없음(이 박스는 0 — 걸린 소스 · 매핑 · 원자 0)
>              나오면 그 술어를 매핑하는 소스 중 map.implementation_id 가 declarative-role 인 소스의 원자가 사건 시각을 값으로 들고 있다
>              그 소스만 다시 번역(아래) — 돌리기는 소유자
>                python -m ledger.backfill --source <소스> --whole-source            (미리보기 — relation_rows 가 행 수, 안 씀)
>                python -m ledger.backfill --source <소스> --whole-source --apply
>                시간 어림  행 수 × 5.85 s / 1,000 (박스 다이 소스에서 잰 율)
> 급할 때       git revert <이 커밋> -> 재기동
> ```

---

> ## [10-02 저녁] **체인 대기열 — 소급 잡 하나는 한 줄 (run_id) · 접기는 자르기 전 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  소급 잡이 도는 동안 낸 이벤트와 그것이 깨운 체인 쓰기가 payload 에 run_id 를 싣는다
>              GET /admin/chain/queue 의 waiting_transactions = «줄»: 잡(run_id · op) · 트랜잭션 · 그 행 하나 중 하나
>                 한 줄 = run_id · op · transaction_id · events(남은 이벤트) · rows(그 이벤트가 싣는 행) · 가장 오래 기다림
>              🔴 rows 의 뜻이 바뀜: 전에는 «이벤트 수», 이제 «행 수». 이벤트 수는 events
>              listed = {lines, lines_total, cap, capped} — 상한은 «줄» 200(전에는 «이벤트» 200, rows_scanned 은 없어짐)
> 확인         재기동 뒤 소급 잡 하나(어드민 Retroactive 탭) -> 체인 대기열 화면에 그 잡이 한 줄
>              curl -s -H "X-Admin-Token: <토큰>" http://localhost:8080/admin/chain/queue  -> waiting_transactions[].run_id · op
> 뜻           같은 잡이 두 줄이면: 재기동 전에 큐에 들어간 이벤트(run_id 없음) — 다 빠지면 한 줄
>              op 가 비어 있고 run_id 만 있으면 retroactive_runs 에 그 실행 행이 없는 것
> 급할 때       git revert <이 커밋> -> 재기동. 이벤트의 run_id 키는 읽는 쪽이 없으면 무해
> 화면         클라 레인이 이 줄 모양으로 대기열 화면을 바꾼다(그 전까지 화면의 rows 칸은 «행 수»를 보이고, 잡 줄의 tx 칸은 빈다)
> ```

---

> ## [10-02 오후] **배포 뒤 운영 순서 — 다이 references · 키 철자 하나 (총괄 6736254fd) — 이주 «불필요» · 재기동 «필요»**
>
> ```
> 1 선언     config/ontology/ledger_config.json 의 die@1 에 references 목록 하나(아래 references 절의 예시) — 재기동 «전»에 적어도 된다
> 2 재기동   run_app.bat 전체. 로그 [Ledger] re-stamped N cursor(s) … — 다이를 부르는 소스들의 지문이 새로 찍힘(자리 그대로)
> 3 다이를 부르는 소스 전부 다시 번역 — 키 철자 하나(7.0 -> '7', 7350027a6) 와 references 원자가 같이 들어온다
>     소스 목록   GET /api/ledger/declaration 의 sources[].emits 에 in_container@1 이 있는 소스
>     소스마다    python -m ledger.backfill --source <소스> --whole-source            (미리보기 — relation_rows 가 행 수, 안 씀)
>                python -m ledger.backfill --source <소스> --whole-source --apply
>     시간 어림   행 수 × 5.85 s / 1,000 (박스 die_inspection 117,742 행 = 11분 28초) — 1,000 행당 5 s 규격을 넘는다
> 뜻           3 을 다 돌리기 전에는 같은 다이가 두 철자로 갈려 걷기에서 두 노드로 보인다 — 다 돌리면 하나
>              한 소스만 돌리고 멈추면 그 소스의 다이만 새 철자 — 나머지를 이어서 돌린다
> 급할 때       선언에서 references 를 지우고 재기동(이미 쓴 원자는 3 을 다시 돌리면 거둬진다)
> ```

---

> ## [10-02 오후] **그리드 행 지우기 — 답은 지운 수 · 트랜잭션만 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  POST /tables/<표>/rows/batch_delete 의 답 = {status, deleted_count, transaction_id} — created_logs 가 빠짐
>              행마다 이력은 그대로 audit_logs 에, 다른 화면은 그대로 batch_row_delete 방송으로 받음(500 행 묶음마다 그 행들의 이력)
> 확인         재기동 뒤 그리드에서 행 몇 개 고르고 🗑️ Row -> 아래 줄 Deleting … · N s 가 오르다 Deleted N rows · S s
>              다른 탭에 같은 표를 열어 두면 그 행들이 그쪽에서도 빠짐(방송)
> 뜻           Deleted 가 뜨는데 다른 탭에서 안 빠지면 방송이 안 간 것 — 서버 로그의 웹소켓 줄을 본다. 답 자체가 늦으면 지우기 본체(DB) 시간
> 급할 때       git revert <이 커밋> -> 재기동(화면은 deleted_count 만 읽으므로 되돌려도 화면 변화 없음)
> ```

---

> ## [10-02 오후] **원장 펼친 보기에 occurred_at_basis 칸 · references 예시는 목록 모양 — 이주 «필요»(보기만) · 재기동 «불필요»**
>
> ```
> 무엇이 바뀌나  ledger_atom_rows 보기 맨 끝에 occurred_at_basis(빈 값 = 사건 시각, ingested = 아님)
>              RELEASE_LOG · 아래 references 절의 선언 예시가 «목록 하나» 모양 — 재기동 전 옛 코드도 받아들인다
> 돌릴 명령     python server/migrations/add_ledger_atom_rows.py --report    (보기 있음 확인)
>              python server/migrations/add_ledger_atom_rows.py             (보기를 그 자리에서 다시 만듦 — 원장 · 원천 표 그대로)
>              config/table_config.json 의 ledger_atom_rows.column_types 맨 끝에 "occurred_at_basis": "string" (샘플 그대로)
> 뜻           메인 그리드의 ledger_atom_rows 에 그 칸이 보이면 끝. 칸만 비어 보이면 표 선언은 됐고 이주를 안 돌린 것
>              이주가 「cannot change name of view column」으로 거절하면 보기를 손으로 바꾼 설치 — 보기를 지우고(DROP VIEW ledger_atom_rows) 다시 돌린다
> 급할 때       표 선언에서 그 한 줄을 지우면 그리드에서 사라진다(보기는 그대로 둬도 됨)
> ```

---

> ## [10-02 오후] **바인딩 · 묶음 · when 칸은 맵퍼 입력 칸에 다시 안 적는다 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  검증기가 바인딩(bind.mappings 의 칸 · bind.entities 속성 칸) · map.unit.columns 를 map.input_columns 에 다시 적으라고 안 한다
>              그 칸은 읽기가 저절로 싣는다 — bind.entities 속성 칸도(전에는 안 실려 번역에서 missing_binding_column)
>              ⚰️ 10-03 2a8d9073c 로 Mapper input_columns 칸째 사라짐 — 아래 확인은 할 수 없다
> 확인         (⚰️) 재기동 뒤 탐색기에서 소스를 열어 Mapper input_columns — 바인딩한 칸이 눌린 채 잠겨 있다
>              입력 칸에서 바인딩한 칸을 빼고 저장 · 적용 -> 거절 없음(전에는 「Profile column 'X' at … is missing」)
> 뜻           체인 데몬이 뜰 때 [Ledger] re-stamped N cursor(s) … 줄 — bind.entities 속성이 있는 소스(박스: dt_job)의 지문만 새로 찍힘.
>              자리 그대로, 다시 읽는 행 없음. [Ledger] N cursor(s) were NOT re-stamped 줄이 나오면 그 소스가 멈춘 것 — 줄 뒤 사유를 본다
> 급할 때       git revert <이 커밋> -> 재기동. 단 이 커밋 뒤에 입력 칸을 비워 저장한 선언은 되돌리면 다시 거절된다
> 재기동 뒤 로그 위 re-stamped 줄
> ```

---

> ## [10-02 오후] **엔티티 references 가 원자를 쓴다(다이 → 웨이퍼) · 사건 시각 아닌 원자는 창을 늘 지난다 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  entities.<타입>.references(하나 또는 목록)를 적으면 그 엔티티를 부르는 소스마다 그 엣지 원자를 하나 더 쓴다(분자당 하나)
>              그 원자의 occurred_at_basis = ingested(사건 시각 아님). 새 칸 · 새 값 · CHECK 교체 없음
>              사건 시각 아닌 원자(이것 · 원래 ingested 인 dt_job)는 걷기 시간 창이 늘 지나보내고 · 창 밖 수에 안 세고 ·
>              응답 엣지 occurred_at 이 null · 처음 본 시각(gaps)에 안 든다. 최신값 · 가져오기 순서는 그대로
> 선언(운영자가)  config/ontology/ledger_config.json 의 entities 에서, 예:
>                "die@1": {"keys": [...그대로...], "references": [{"edge": "in_container@1",
>                  "to": {"entity": "wafer@1", "keys": {"wafer": "mat_id"}}, "from": {"when": {"mat_type": "Wafer"}}}]}
>              목록 모양으로 — 재기동 전 옛 코드도 받아들인다(한 개 객체면 옛 코드가 die@1 을 거절해 다이 소스가 멈춘다)
> 확인 명령     재기동 뒤 로그에 [Ledger] entity|die@1 is NOT read: … 줄이 없어야 한다(있으면 그 줄 뒤가 거절 사유 — 술어 · 키 대응 · when)
>              다이를 부르는 소스를 소스마다 다시 번역:  python -m ledger.backfill --source <소스> --whole-source --apply
>              확인:  SELECT count(*) FROM ledger_events WHERE predicate = 'in_container' AND occurred_at_basis = 'ingested'
> 뜻           그 수가 늘면 references 원자가 쓰인 것
>              체인 데몬이 뜰 때 [Ledger] re-stamped N cursor(s) … 줄 — 선언이 바뀐 소스의 커서 지문을 새로 찍음(자리 그대로), 그 뒤 새 행부터 references 원자
>              이미 번역된 옛 행은 위 다시 번역으로만 생긴다
> 급할 때       선언에서 references 를 지우면 새 원자는 안 생긴다(이미 쓴 것은 남음 — 그 소스를 다시 번역하면 거둬진다). 코드는 git revert -> 재기동
> 재기동 뒤 로그 위 두 줄
> ```

---

> ## [10-02 낮] **정적 «씨앗»의 첫 걸음은 동적 노드로 간다 — 걷기 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  씨앗이 정적 타입(선언 class: static)이면 그 씨앗에서 나가는 첫 걸음이 동적 노드로 간다
>              예: 레시피 씨앗 + follow=processed_with -> 그 레시피를 쓴 웨이퍼들. 전에는 노드 1 · 엣지 0
>              걷는 도중 만난 정적 노드는 오늘과 같다(웨이퍼 -> 레시피 -> 다른 웨이퍼 0)
>              씨앗이 동적인 걷기 · 대조는 답이 그대로
> 확인 명령     curl "http://<서버>:<포트>/api/ledger/subgraph?id=<레시피 노드 id>&follow=processed_with&hops=2&fanout_limit=20"
> 뜻           nodes 에 웨이퍼가 있다                       새 코드
>              bundles 에 {far_type: wafer, count: N}       웨이퍼가 fanout_limit 을 넘었다 — 그리지 않고 수로 답했다
>                 truncated.claims 가 true 면 그 N 은 «읽은 만큼»이다(전체 수가 아니다)
>              nodes 에 레시피 하나뿐 · edges 0              서버가 옛 코드 — 재기동이 안 됐다
>              ⚠️ 걷기 화면의 경로 목록은 이 첫 걸음을 아직 안 내놓는다 — 클라 착지 뒤에 화면에서 고를 수 있다
> 급할 때       이 커밋을 되돌린다(git revert) -> 재기동. 데이터는 안 바뀐다
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-02 낮] **걷기 시작점 목록이 노드를 «두 쪽»에서 읽는다 — /api/ledger/key-values — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체) + 브라우저 강력 새로고침**
>
> ```
> 무엇이 바뀌나  목록의 노드를 주어 쪽 «과» 목적어 쪽에서 읽는다(gaps._nodes_of_type_sql). 목적어로만 나오던 타입(이 박스 recipe · defect_kind)이 이제 목록에 나온다
>              타입은 같은 이름만 — 전에는 lot 목록에 lot_slot 의 lot 키가 섞였다
>              순서는 «값 오름차순»(전: 빈도 내림차순). count 는 그 값의 노드를 두 쪽에서 부르는 원자 수
>              전선 칸 subjects -> nodes · limits.scan_rows -> limits.scan_nodes · scanned 는 «읽은 노드 수»
>              client2/dist 를 같이 다시 빌드했다 — 화면이 nodes 를 읽는다
> 확인 명령     curl "http://<서버>:<포트>/api/ledger/key-values?type=recipe"
> 뜻           "nodes": [...] · "order": "value_asc"        새 코드
>              "subjects": [...]                             서버가 옛 코드 — 재기동이 안 됐다
>              걷기 화면 목록이 «모든 타입»에서 비고 「원장에 주어로 없습니다」     서버 · 번들 중 하나만 새것(둘 다 같은 증상)
>                                                           -> 서버 재기동 «그리고» 브라우저 강력 새로고침(Ctrl+F5)
>              "nodes": [] · "scan_truncated": false          그 타입은 원장 어느 쪽에도 노드가 없다
> 급할 때       이 커밋을 되돌린다(git revert) -> 재기동 + 새로고침. 데이터는 안 바뀐다
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-01 밤] **이미지 참조 — 이미지는 «전부» 서버가 받아서 보낸다 · 브라우저가 답을 3600 초 든다 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  칸 값 하나로 이미지를 가리킨다 — https://… 그대로, 또는 <출처 이름>:<경로 또는 키>. 칼럼 타입 낱말은 "image"(저장은 글자)
>              출처는 server/config/image_sources.json 한 파일 — 샘플 server/config/sample/image_sources.json.sample 에 셋:
>                 folder  {"kind": "folder", "root": "D:/shared/photos"}                         photos:2026/10/a.png
>                 db      {"kind": "db", "connection": {dialect · host · port · database · user · password_env},
>                          "query": "SELECT image FROM images WHERE image_id = :key"}             inspection_db:IMG-001
>                 url     {"kind": "url", "base": "https://vendor.example.com/images/"}         vendor:a.png
>              🔴 비밀번호는 파일에 0 — password_env 에 «환경변수 이름»만. db 출처는 «읽기 전용 사용자»를 권한다
>              🆕 url 출처도 https:// 칸도 서버가 받아서 보낸다 — 브라우저를 그 주소로 보내는 답은 없다
>                 -> 사용자 PC 가 이미지 호스트에 못 닿아도 보인다. 그만큼 서버가 바깥 주소를 대신 읽는다(부하)
>                 받은 답은 image/* · 20,971,520 바이트 이하 · 리다이렉트 아님 — 넘으면 다 받기 전에 끊는다
>              옛 선언의 "proxy" 칸은 읽지 않는다 — 있어도 거절 안 함, 지워도 된다
>              🆕 답(파일 · 바이트)에 Cache-Control: private, max-age=3600 — 거절에는 안 붙는다
> 확인 명령     curl -i "http://<서버>:<포트>/api/image?ref=photos:a.png"
>              curl -sI "http://<서버>:<포트>/api/image?ref=photos:a.png" | findstr /i cache-control
> 뜻           200 + 이미지                                   읽힘
>              400 "… outside the root …"                     folder 경로가 root 밖(.. · 절대경로)
>              400 "… leaves the host of image source …"      url 출처에서 칸 값이 호스트를 바꾸려 했다(base 가 / 로 안 끝날 때 @ · . · :포트) — base 를 / 로 끝내면 그 값은 경로
>              404 "no file … / no image for key …"           파일 · 키가 없다
>              404 "image source … is not declared"           선언에 없는 출처 이름
>              500 "… must bind :key and nothing else"        db 출처의 query 가 :key 하나만 묶지 않는다
>              500 "… reads its password from X, which is not set"   그 환경변수가 서버 프로세스에 없다
>              500 "… another reference twice"                db 값이 글자면 참조로 «한 번 더» 푸는데 두 번째도 글자였다
>              502 "image source '<이름>' could not be read: …"   db 연결 · 질의 실패 — 뒤의 첫 줄이 사유
>              502 "… could not be fetched: …"                바깥 주소에 못 닿음(이름 · 연결 · 시간 초과)
>              502 "… answered a redirect (3xx) - not followed"   바깥이 다른 곳으로 넘기려 했다 — 넘겨진 주소로 고친다
>              502 "… answered '<type>', not an image"        바깥 답이 그림이 아니다(사내 페이지 · JSON)
>              502 "… is larger than … bytes - not read further"   상한(image_sources.MAX_BYTES)을 넘었다
>              🔴 배포 뒤 이미지를 «같은 참조»로 바꿔 놓으면 이미 본 화면은 최대 3600 초 옛 그림을 보인다
> 급할 때       image_sources.json 을 지우면 출처 참조가 전부 404(https:// 칸은 여전히 받아 옴). 캐시는 image_sources.CACHE_SECONDS 를 0 으로 -> 재기동
> 재기동 뒤 로그 새 로그 줄 없음 — 거절은 응답의 detail 로 말한다
> ```

---

> ## [10-01 밤] **잡 단위 거둠으로 지운 행이 이력 · 원장 후속에 간다 + 맵퍼 표면에 find_links · unknown_words — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  allow_retraction 이 행을 지우는 길이 맵 퍼지와 «같은 문»(crud.purge_map_rows — 그리드 지우기는 따로)
>              -> 거둠으로 지운 행마다 DELETE 이벤트 · 행 지움 이력. 원장 후속이 그 행에서 나온 원자를 거두고, 체인 거둠 바퀴가 그 행이 먹인(도장 있는) 칸을 거둔다
>              맵퍼는 from mapper_sdk import find_links, unknown_words 로 부른다 (from utils import text_links 도 계속 된다)
> 뜻           `🔄 [DtMapRetraction] … retracted N stale row(s)` 뒤에 같은 표의 `[ChainRetract] table=<표> deleted_rows=N …` 가 따라 나오면 이 변경이 돈 것
>              그 표를 지켜보는 규칙 중 «되돌릴 수 없는» 종류가 있으면 거둠마다 `[ChainRetract] <규칙>: …` 경고 한 줄씩 — 이 박스는 dt_map 를 지켜보는 규칙 0 · 경고할 것 0
>              이미 거둠으로 지운 행에서 나온 원자(소급) — 이 박스 원자 0 (거둠 표 dt_map 는 원장 참조 0)
>              운영에서 세기: SELECT count(*) FROM ledger_source_row_ref r WHERE r.relation = '<거둠 표>'
>                             AND NOT EXISTS (SELECT 1 FROM <거둠 표> x WHERE x.row_id = r.row_id)
> 급할 때       이 커밋을 되돌린다(git revert) -> 거둠이 다시 손으로 지우고 이벤트 · 이력이 안 남는다. 이미 남은 이력 · 거둬진 원자는 그대로
> 재기동 뒤 로그 위 두 줄 — 거둠이 일어날 때만
> ```

---

> ## [10-01 밤] **글에서 원인 -> 현상 후보 — server/utils/text_links.py — 이주 «불필요» · 재기동 «불필요»(새 파일)**
>
> ```
> 무엇이 바뀌나  소유자 @mapper 가 import 해 쓰는 순수 함수 둘 — find_links(text, names, links) · unknown_words(texts, names, links). 다른 코드 무변
> 가이드        docs/guide/TEXT_LINKS_GUIDE.md — 표 넷 · 짝짓는 규칙 두 줄 · 맵퍼 예 · 규칙 선언(allow_retraction) · 사전 고친 뒤 다시 돌리기 · 남는 것 둘
> import 한 줄  from utils import text_links
> 뜻           글에 말이 있는데 후보 0 -> 연결 말 사전에 cause 행(side 포함)이 없거나, 그 side 쪽에 노드가 없다. unknown_words 로 사전이 못 덮은 낱말을 본다
>              연결 말 행의 meaning 이 다섯 밖이거나 cause 행에 side 가 없으면 그 행 번호를 대고 ValueError -> 그 규칙의 실패 로그로 보인다
>              속도(박스, 합성 naming phrases 1000 · link phrases 7 · texts 1000 x 20 sentences (seeded synthetic)): 글 하나 9.7 ms 중 사전 짓기 8.3 ms — 글 1,000 건 10.56 s
> 급할 때       그 규칙을 끈다(enabled false). 이 모듈은 부르는 맵퍼가 없으면 안 돈다
> 재기동 뒤 로그 새 줄 없음. 이 모듈을 고친 «뒤»에는 체인 워커 재기동 — 이미 읽힌 모듈은 다시 안 읽는다
> ```

---

> ## [10-01 밤] **원장 «펼친 보기» ledger_atom_rows — 그리드에서 원자를 평문으로 · 원천 row_id 로 — 이주 «필요» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  읽기 전용 보기 ledger_atom_rows: 한 행 = (원자, 원천 행). 주어 · 목적 · 수식어는 저장 철자 그대로의 평문(키=값 / …)
>              source_row_id 로 거르면 그 행이 낳은 원자가 전부 나온다. 원천 행이 없는 원자(뷰를 읽던 소스)는 원천 칸이 빈 한 줄
>              원천 행 참조 표에 색인 둘(이음 · row_id). 원장 표는 무변
> 돌릴 명령     python server/migrations/add_ledger_atom_rows.py --report     (있고 없음 · 크기)
>              python server/migrations/add_ledger_atom_rows.py              (색인 둘 CONCURRENTLY + 보기 — 쓰기 계속됨, IF NOT EXISTS 라 다시 돌려도 같음)
>              table_config.json 에 "ledger_atom_rows" 항목을 출고 샘플에서 그대로 복사 -> 재기동(run_app.bat 전체) -> 그리드 표 목록에 뜸
>              ⚠️ 이 박스는 이주가 «이미» 돌았다(보기 · 색인 둘 있음) — table_config 항목만 남음
> 뜻           이 박스: 색인 79 MB + 67 MB
>              첫 쪽 100 행 0.03 s · row_id 하나 1.85 s · 주어 평문 일부 10.9 s · 전체 행 수 10.5 s (2,334,076 행)
>              전체 행 수는 그리드의 미뤄 세기(defer_total -> /data/count, 캐시)로 — 첫 쪽을 막지 않는다
>              row_id · 주어 거르기는 원장 표에 색인을 안 넣어 원장 전체를 훑는다(총괄 판정 — 원장 표에는 색인을 안 넣기로)
>              참조 표 쓰기 비용: 1,000 행당 44.5 / 47.1 ms -> 62.5 / 65.5 ms (시험 DB, 참조 길이 882 · 지우고 다시 넣기)
> 급할 때       table_config 의 그 항목을 지우면 그리드에서 사라진다. 보기 · 색인은 DROP VIEW ledger_atom_rows · DROP INDEX CONCURRENTLY 두 색인
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-01 밤] **걷기 «도로 내려가지 않기» — 역 술어 칸 `inverse_of` · 같은 타입 형제만 막음 — 마이그레이션 «없음» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  걷기가 형제로 퍼지지 않는다: 같은 술어를 반대 방향으로(또는 선언된 역 술어를 같은 방향으로) 되밟아
>              «출발한 노드와 같은 타입»으로 가는 걸음을 막는다 — 다이 -> 웨이퍼 <- 다이. 다른 타입으로 가는 길은 걷는다
>              어휘 술어에 칸 하나 inverse_of — 걷기만 읽는다(소스 지문 · 원장 무변, 소급 0)
> 운영자가 적을 것  ledger_config.json 의 vocabulary 에 짝 하나 (한쪽만 적어도 양쪽으로 읽힘):
>                "inspected@1": { …, "inverse_of": "in_container@1" }
>              적지 않은 짝은 그 두 술어로 형제가 «오늘처럼» 퍼진다(같은 술어 되밟기만 막힘)
> 돌릴 명령     재기동 — run_app.bat 전체 (짝을 적은 뒤에도 재기동이 걷기에 읽힘을 보장)
> 뜻           이 박스 다이 씨앗(라우트 기본): 오늘 노드 400 · 엣지 892(잘림) -> 짝 없음 노드 400 · 엣지 795 -> 짝 적은 사본 노드 15 · 엣지 25(잘림 없음)
>              짝 없이 빠지는 것은 같은 술어 형제 걸음뿐 — hops 3 비교에서 빠진 노드 65 개 전부 «형제 걸음으로만 닿던» 노드
>              검증 거절: unknown_id(없는 술어) · invalid_predicate(두 끝이 뒤집혀 안 맞음 / 역이 둘)
> 급할 때       짝을 지우면 그 두 술어는 다시 따로 걸린다. 규칙 자체를 되돌리려면 커밋 되돌리기
> 재기동 뒤 로그 새 로그 줄 없음 · 짝이 틀리면 선언 적재가 그 이름으로 거절
> ```

---

> ## [10-01 밤] **걷기 노드 이름표 — 선언 키 전부 · 키 철자 — 마이그레이션 «없음» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  걷기 응답 노드의 label = 그 타입 «선언»의 키 순서 전부(앞 두 값이 아니라). 수는 원장 키 접기와 같은 철자(1 · 1.0 -> 1)
>              선언에 없는 타입은 오늘 모양 그대로 · 키 하나짜리(웨이퍼 · 랏)는 오늘과 같음
> 돌릴 명령     재기동 — run_app.bat 전체
> 뜻           이 박스 웨이퍼 SYN-CX-BW-001 걷기: 다이 278 개의 이름표 42 가지 -> 278 가지 · 다이 아닌 노드 122 개 이름표는 그대로
> 급할 때       커밋 되돌리기 (데이터 · 선언 변경 없음)
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-01 밤] **걷기 펼침 묶음 — `fanout_limit` · `expand` · `bundles` — 마이그레이션 «없음» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  걷기(GET /api/ledger/subgraph)에 요청 칸 둘: fanout_limit=<정수> · expand=<노드 id>|<술어>|<방향>
>              한 노드에서 한 술어 · 한 방향으로 먼 노드가 fanout_limit 을 «넘으면» 그리지 않고 응답 bundles 에 한 줄
>              칸이 없으면 오늘과 같음(bundles 키도 없음)
> 돌릴 명령     재기동 — run_app.bat 전체 (라우트 인자)
>              확인: GET /api/ledger/subgraph?id=<다이 id>&fanout_limit=20  -> 응답에 bundles
> 뜻           bundles 의 count = 그 묶음을 펼치면 그려지는 먼 노드 수(이미 그린 노드 포함). 묶음은 노드가 아니고 truncated 와 별개
>              이 박스 다이 씨앗: 칸 없으면 노드 400(잘림 nodes) · fanout_limit=20 이면 노드 15 · 묶음 13 · 잘림 None
>              원자는 오늘처럼 읽는다 — 묶음은 «그리는 수»를 줄이지 원자 예산을 아끼지 않는다
> 급할 때       요청에서 fanout_limit 를 빼면 오늘과 같음(서버 스위치 없음)
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-01 저녁] **원장 선언 v6 — prepare 절 은퇴 · lot_event 은퇴(계보는 체인) · 맵퍼 칼럼 이름은 규칙 칸 — 이주 «필요»(v6 --apply) · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  ① 원장 선언 setup_version 6 — 소스의 prepare 절 은퇴. 옛(5) 파일은 메모리에서 6 으로 읽힘:
>                 direct-join prepare 는 버리고 적재 노트 한 줄, 일하는 준비기를 든 lot_event 만 이름 거절(Next: 아래 이주)
>              ② lot_event 소스 은퇴(원자는 남음) — 계보 derived_from 은 체인 규칙 lot_event_to_lot_lineage -> 표 lot_lineage -> 원장 소스 lot_lineage
>                 웨이퍼·랏 등록(register)은 끊김 · 갭 질문 「등록되지 않은 웨이퍼 · 랏」 은퇴 · 어휘 register@1 의 주어에서 lot@1 · wafer@1 빠짐
>              ③ 체인 맵퍼 lot_slot_wafer · lot_lineage 는 칼럼 이름 전부를 규칙 params 에서 읽음 — 기본값 없음, 빠지면 이름 거절
>              ④ 걷기 타입 목록(seed_type) = 원자가 이름 댄 노드 전부(등록 여부 무관) · 예산만큼 «키 순서 앞쪽». 갭 측정도 같은 질의
> 돌릴 명령     git pull 전에 server/mappers/lot_slot_wafer_mapper.py 를 옆으로 옮김 (추적 안 된 박스 사본 — 같은 경로에 추적판이 들어옴)
>              python server/scripts/migrate_ledger_config_to_v6.py                 (미리보기 — 바꿀 것을 줄마다, 아무것도 안 씀)
>              python server/scripts/migrate_ledger_config_to_v6.py --apply         (ledger_config · table_config · chain_rules 셋, 백업 남김)
>              재기동 — run_app.bat 전체 (lot_lineage 표 생성 · 규칙 적재)
>              python server/scripts/chain_replay_cli.py replay lot_event_to_lot_lineage --apply
> 뜻           --apply 전(재기동 사이)에 멈추는 것 셋: lot_event 소스(이름 거절) · lot_slot_wafer 규칙(돌 때마다 「빠진 칸」 거절) · 갭 화면(「이름 없는 질문」 거절)
>                 셋 다 같은 Next(위 이주)이고 --apply 로 풀림. 나머지 소스는 그대로 돎
>              미리보기 정상 줄: vocabulary.register@1.subjects: - lot@1, wafer@1 · chain_rules.lot_event_to_lot_slot_wafer.params: + target_* 다섯
>              옛 계보 원자는 남는다 — lot_event 가 쓴 derived_from 과 lot_lineage 가 쓸 derived_from 은 걷기에서 엣지 «하나»(근거는 둘 중 하나만 보임)
>              이 박스(사본 · 메모리, 쓰기 0): 이주 뒤 prepare_retired 0 · lot_slot_wafer 36525행 전후 같음 · 계보 쌍 1986 원장과 같음
> 급할 때       커밋 되돌리기 + --apply 가 남긴 백업 세 파일 복원
> 재기동 뒤 로그 --apply 전: [Ledger] setup_version 5 read as 6: … - Next: run scripts/migrate_ledger_config_to_v6.py to write it
>                         [Ledger] source lot_event is NOT planned: bundle.sources.lot_event.prepare …
>              --apply 뒤: 그 두 줄이 없어야 함
> ```

---

> ## [10-01 오후] **숫자의 신원 철자는 하나 — 문자 칸 숫자 · 저장된 칸 소급 · 원장 엔티티 키 — 마이그레이션 «없음» · 재기동 «필요» · 소급/다시 번역은 운영자가 표·소스마다**
>
> ```
> 무엇이 바뀌나  ① 문자 칸(number · datetime 아닌 칸)에 숫자가 오면 clean_str_value 의 철자로 저장 — 1.0 -> '1', 3 -> '3', 1.5 -> '1.5'
>                 층과 보이는 칸이 같은 글자(전엔 층 숫자 1.0 · 칸 PG 글자 '1.0' — 파이썬 '1' · PG ->> '1.0' 로 답이 둘). bool · NaN · inf · 글자 '1.0' · number 칸은 그대로
>              ② 소급 "Fold stored values into the declared spelling" 이 write 칸만이 아니라 «글자 칸 전부»를 쓰기 접기 그대로 지남
>                 층이 접힌 칸은 보이는 값을 접힌 층에서 다시 정함. 키는 접기가 키 부품 칸을 바꾼 행만, 그 행의 안 접은 칸이 저장 키를 그대로 짓는 때만 바뀜
>              ③ 원장 엔티티 키 — 선언 바인딩의 키 칸이 그 칸의 «선언 타입»으로 정규화(map_overlay.canonical_key_value):
>                 number 칸의 1 · 1.0 · '01' 은 키 '1'(글자) 하나. 문자 칸의 '1.0' 은 '1.0' 그대로 — 접고 싶으면 그 칸을 table_config 에서 number 로 선언
>                 저장된 원장 키는 «다시 번역할 때까지» 옛 꼴(7.0) 그대로 — 새로 번역되는 원자부터 '7'
> 돌릴 명령     재기동 — run_app.bat 전체
>              ② 표마다: 어드민 Retroactive 탭 "Fold stored values into the declared spelling" -> table -> Count 먼저, 그다음 Run
>              ③ 소스마다 (whole_source 는 화면 폼에 없어 명령줄):
>                 python server/ledger/backfill.py --source <소스> --whole-source              (미리보기 — 행 · 잃은 행 · 그 원자, 안 씀)
>                 python server/ledger/backfill.py --source <소스> --whole-source --apply --pace slow
>                 대상 = number 칸을 엔티티 키에 묶는 소스: bonded_from · bw_dt_seat · die_inspection · dt_transfer · transfer_event · void_observation
> 뜻           ② Count: affected = 보이는 값이 바뀌는 칸 · layers_folded = 바뀌는 층 · keys_not_rebuilt = 키가 저장 키와 이미 어긋나 건너뛰는 행(그 행은 한 칸도 안 접음, 신원 그대로)
>              ③ 다시 번역 전에는 같은 다이가 옛 꼴(7.0)과 새 꼴('7')로 갈려 걷기에서 둘로 보일 수 있음 — 소스를 다시 번역하면 옛 꼴이 빠지고 새 꼴만 남음
>              저장된 마킹의 옛 다이 id 는 다시 번역 뒤 안 맞음 — 마킹은 브라우저에 저장돼 서버에서 셀 수 없음. 저장된 대조(contrast_run)는 이 박스엔 표가 없음(0)
>              이 박스(미리보기만, 실행 안 함): dt_map.value 층 1,000,400 · 보이는 칸 1,000,399 · wafer_map_metadata 층 1 / 다시 번역: die_inspection 숫자 키 0 · transfer_event 숫자 키 0 (뷰를 읽는 넷은 오늘 로드 거절 — 미리보기 없음)
> 급할 때       커밋 되돌리기. 소급·다시 번역은 실행 전이면 안 돌리면 됨 — ② 는 돌린 뒤 되돌릴 수 없음(옛 철자는 칸마다 이력 줄), ③ 은 되돌린 코드로 다시 번역하면 옛 꼴로 돌아감
> ```

---

> ## [10-01 오후] **sample 의 decide 넷 복원 — 마이그레이션 «없음» · 재기동 «없음» (sample 만)**
>
> ```
> 무엇이 바뀌나  server/config/sample/chain_rules.json.sample 에 derive.decide 넷이 돌아옴 — 09-24 은퇴 때 옮겨지지 않고 지워졌던 것
>              dt_job_lot_slot_attribution · dt_frame_confrimation · core_frame_review · dt_lot_slot_from_log (이름 철자 그대로)
>              sample 의 alignment_rule 둘이 다시 있는 선언을 가리킴. 넷 다 꺼진 채 출하 — DT 체인을 켤 때 같이 켬
> 돌릴 명령     없음
> 뜻           박스·운영 설정은 한 줄도 안 바뀜. 새 설치가 sample 을 복사할 때만 닿음
> 급할 때       커밋 되돌리기
> ```

---

> ## [10-01 오후] **표 선언 엑셀 붙여넣기 · 복사 — 화면만 · 마이그레이션 «없음» · 재기동 «없음» (git pull 뒤 페이지 새로고침)**
>
> ```
> 어디         Admin -> Tables -> 표 고르기 -> 「Paste columns · names / types / key」 칸과 「Copy columns」 버튼
> 붙여넣기      엑셀 가로 세 줄: 1 줄 컬럼 이름 · 2 줄 타입(string · number · datetime, 대소문자 무관) · 3 줄(있으면) 키 컬럼에 key
>              -> column_types · display_columns(붙인 순서 전부) · 키(하나면 business_key, 둘 이상이면 composite_key_source)를 채움
>              있는 표는 통째로 바뀜 — 저장 전에 Dropped · Type · Key · Shown · Existing rows change identity 줄과 확인창
> 복사          지금 컬럼을 같은 세 줄로 클립보드에 — 엑셀에서 고쳐 다시 붙여넣기. 키를 세 줄로 못 적는 표는 3 줄을 빼고 그렇다고 한 줄
> 뜻           칸 · 버튼이 안 보이면 = 옛 화면이 캐시됨 -> Ctrl+F5
> 급할 때       저장 전 확인창에서 No — 아무것도 안 보냄
> ```

---

> ## [10-01 오후] **(선택) HTTPS — nginx 앞단 · 제품 코드 무변 · 마이그레이션 «없음» · 재기동 «없음»**
>
> ```
> 무엇이 바뀌나  가이드만 — docs/guide/HTTPS_PROXY_GUIDE.md (pfx + p7b -> fullchain · nginx.conf · 방화벽 · 부팅 시 자동)
> 돌릴 명령     가이드 2~7 단계 (관리자 PowerShell 한 창)
> 뜻           curl.exe https://<호스트명>/health 가 200 = 프록시가 8080 에 닿음
>              다른 PC 브라우저에서 자물쇠 + 실시간 갱신 = 웹소켓까지 통함
> 급할 때       C:\nginx 에서 .\nginx.exe -s stop — http://<서버>:8080 은 그대로 살아 있다(8 단계를 안 했으면)
> ```

---

> ## [10-01 오후] **체인 규칙 이름 바꾸기 = 제자리 · 이름을 붙든 기록이 있으면 거절 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  체인 편집기에서 규칙 이름을 바꿔 저장하면 «그 자리의 그 규칙»이 바뀜(켜짐 그대로) — 전엔 꺼진 새 규칙이 덧붙고 옛 것이 계속 돌았음
>              서버는 POST /admin/chain/rules/raw 의 from(연 이름)을 읽음 — 클라가 from 을 보내야 화면에서 동작(클라 레인)
> 돌릴 명령     없음
> 뜻           저장이 rule_name_held 로 거절되면 = 옛 이름으로 찾는 기록이 있음(확정 · 미처리 리플레이 · 다른 규칙의 alignment_rule · 안 끝난 소급) — 이름 유지, 새 이름이 꼭 필요하면 새 규칙을 추가하고 이것을 끔
>              바꾸기가 되면 = 그 규칙이 쓴 칸은 그 행이 다음에 올 때 새 이름으로 다시 쓰임
> 급할 때       커밋 되돌리기
> ```

---

> ## [10-01 오전] **걷기 — 아무도 안 부르던 claims_by_ids 둘 은퇴 · 동작 같음 · 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  코드 정리만 — 걷기 룩업의 claims_by_ids(SQL · 메모리 둘) 지움. 호출자 0
> 돌릴 명령     없음
> 뜻           걷기 응답은 전과 같음
> 급할 때       커밋 되돌리기
> ```

---

> ## [10-01 오전] **탐색기 — 가지 뷰 다시 짓기를 세 문이 함수 하나로 부름 · 동작 같음 · 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  코드 정리만 — bootstrap · 초안 반영 · 선언 삭제 뒤의 뷰 다시 짓기가 함수 하나(_world_after_write)
> 돌릴 명령     없음
> 뜻           가지 걷기가 503 「ledger_relation_absent」 면 = 전과 같이 그 가지를 한 번 반영하거나 backfill --world 로 번역
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 오전] **원장 `cardinality: one` — 지금 값은 가장 늦은 occurred_at, 걷기가 읽을 때 정함 · 쓰기에서는 아무것도 안 함 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  one 으로 적으면 걷기가 지금 것만 그린다(옛 값은 include_superseded)
>              지금 것 = 같은 주어·술어 중 occurred_at 이 가장 늦은 사실. 늦게 «도착한» 옛 사실은 지금 것이 아님
>              옛 값을 그리면 엣지에 not_current · 가장 늦은 시각에 목적어가 둘이면 둘 다 그리고 노드의 current_conflicts 가 셈
>              원자를 쓸 때는 one 이 아무것도 안 함 — 한 배치 거절(cardinality_one_violated)·supersedes 찍기 은퇴
> 돌릴 명령     없음 (이미 쓰인 원자에도 바로 걸림 — 재번역 불필요)
> 뜻           걷기 응답에 walk.superseded_dropped 가 없어짐 — 그 칸을 읽던 화면은 없음(클라 검색 0)
>              one 술어에서 한 주어에 엣지가 둘 이상 보이면 = 같은 가장 늦은 시각의 두 사실(current_conflicts 로 확인)
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 오전] **원장 가지 — 기본에 거절 소스가 있어도 새 가지를 만듦 · 없는 가지는 이름 대어 거절 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  가지 만들기(bootstrap?world=)가 기본 선언을 그대로 복사하고 기본과 같은 잣대로 잼 — 거절 소스는 기본처럼 이름 대어 빠짐
>              전: 기본에 거절 소스가 하나라도 있으면 400 bootstrap_invalid 「the starting file did not validate and was not written」
>              폴더 없는 가지를 열면 400 world_not_created 「Next: create the branch first」 (전: 500)
> 돌릴 명령     없음
> 뜻           가지 만들기가 아직 400 bootstrap_invalid 면 = 기본 선언 파일 «전체»의 문제(선언 하나의 문제가 아님) — 그 응답의 details 를 봄
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **원장 가지 — 만들 때 · 선언을 저장(반영)·삭제할 때 걷기 뷰를 다시 지음 · static 만 바꾼 가지도 걷힘 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  탐색기의 가지 만들기(bootstrap?world=) · 초안 반영 · 선언 삭제 뒤에 그 가지의 걷기 뷰를 다시 지음
>              전: 번역(backfill --world)만 뷰를 지어서 static 처럼 소스를 안 움직이는 바꿈만 한 가지는 걷기 503 · 저장 뒤 뷰의 제외 목록이 옛것
> 돌릴 명령     없음 (이미 있는 가지는 다음 반영·삭제 때 다시 지어짐)
> 뜻           가지 걷기가 503 「ledger_relation_absent」 면 = 그 가지를 한 번 반영하거나 backfill --world 로 번역
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **원장 가지 번역 — 가지가 바꾼 소스만 씀 · 같은 표를 읽는 안 바뀐 소스는 기본 원자로 보임 · 마이그레이션 «없음» · 재기동 없음 (backfill --world 는 CLI 한 번)**
>
> ```
> 무엇이 바뀌나  backfill --world <가지> --source <소스> 가 그 가지의 «바뀐 소스»만 번역. 전엔 같은 표를 읽는 다른 소스도 가지에 들어가 걷기에서 기본 원자가 가려짐
> 돌릴 명령     없음 (가지를 쓰는 중이면: 그 가지를 지우고 다시 만들어 번역하면 곁 소스가 빠짐)
> 뜻           가지 걷기에서 안 바꾼 소스의 엣지가 기본과 같으면 = 됨
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **수를 세어 로그 한 줄 찍는 다섯 자리 — 같은 문턱(1·10·…·10^18) · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 · 워처 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  키 게이트 거절 · VOID/SAT 파일 거절 · 원장 거절 · 안 말한 단위 · 미선언 컬럼 드롭 — 넷은 100 만 뒤로 줄을 안 냈는데 이제 1000 만 · 1 억 … 에서도 냄
>              미선언 컬럼 드롭 줄은 전과 같음
> 돌릴 명령     없음
> 뜻           그 줄들 뒤로 조용하면 = 그 수가 더 안 늘었음 (다섯 자리 모두)
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **작성 화면 — 못 읽는 설정 파일은 계획과 view 가 같은 낱말 · unreadable_config 은퇴 · draft_required 문장 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  ledger_config.json 이 JSON 으로 안 읽히면 작성 계획도 view 와 같이 400 invalid_json (전: unreadable_config)
>              뿌리가 객체가 아니면 둘 다 400 invalid_type at ledger_config
>              draft_id 없는 요청의 문장: 「Next: open a draft first - this request needs a draft id」
>              받는 파일은 그대로 — 같은 키가 두 번인 파일도 전처럼 읽힘
> 돌릴 명령     없음
> 뜻           「Next: restore or fix ledger_config.json ...」 = 그 파일을 고치기. 문장 끝에 줄·칸 위치
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **어느 문장도 안 말한 행 — 배치마다 경고 대신 값마다 세어 하트비트 노트 · 1·10·100… 단위에서 한 줄 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  전: 배치마다 「[Ledger] <소스>: N unit(s) said no sentence - mat_type='WF' (N). Next: …」
>              후: 하트비트 ledger 노트에 「units no sentence said: units=N | <소스>:mat_type='WF'=N, …」(상위 5 + (+k more))
>                  값 하나가 1 · 10 · 100 … 단위에 닿을 때만 「[Ledger] Next: correct the value … <소스>: mat_type='WF' said no sentence … | units so far in this process: N」
> 돌릴 명령     없음
> 뜻           노트의 수가 늘면 = 그 값의 행이 계속 아무 문장도 안 말함 -> 그 값을 표에서 고치거나 그 값을 when 에 적은 문장을 선언
>              수는 프로세스 집계 — 재기동이면 0 부터
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **작성 화면 — 저장 전 계획이 저장과 같은 입력으로 채움 · 초안 없는 POST 는 draft_required · 설정 파일 없음/못 읽음은 500 대신 이름 붙은 거절 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  POST /admin/ontology-explorer/authoring/plan (초안 있음): 채우기가 저장과 같은 활성 셋업·카탈로그로
>              같은 라우트에 draft_id 없음: 400 draft_required (전: invalid_draft_id)
>              ledger_config.json 이 없거나 객체로 못 읽힘: view·초안·저장 등 400 + 코드(missing_config_file · invalid_json · invalid_type) (전: 500)
> 돌릴 명령     없음
> 뜻           「Next: restore or fix ledger_config.json ...」 거절 = 그 파일을 되살리거나 고치기. 파일이 없으면 작성 화면의 Create starting file
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **걷기 응답의 증거 길 — 홉마다 predicates · 대조 저장은 그 길 그대로 · 참거짓 글 칸은 "true"/"false" 만 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  /api/ledger/subgraph 의 propagation.ranked[].evidence[].hops[i](i ≥ 1)에 predicates 가 붙음 — 응답 edges 중 앞 홉과 그 홉 사이 술어 전부
>              대조 저장(contrast_factor.evidence)은 전과 같은 글(시험 픽스처에서 byte 같음)
>              contrast_run.include_superseded 칸: "true"/"false" 만 읽음. 전엔 "1" 도 참, "yes" 는 거짓 — 이제 둘 다 그 run 거절
>              소급 작업의 참거짓 인자도 같은 읽기 · 같은 거절 문장
> 돌릴 명령     없음
> 뜻           대조 run 이 「include_superseded must be true or false, got "yes" - write true or false」 로 안 돌면 = 그 칸에 true 나 false 를 적기
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **작성 폼 감사 스크립트가 제품의 스켈레톤 해석기를 부름 · 출력 같음 · 재기동 «없음»**
>
> ```
> 돌릴 명령     (필요할 때) python server/scripts/audit_authoring_form.py --help 대로 — 결과는 전과 같음(추적 표본 311 경로 전후 byte 같음)
> 뜻           폼 감사가 제품 해석기(config_authoring._skeleton_node)와 다른 답을 낼 수 없게 됨
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **파일의 «내놓았는데 안 써진 칸» — 한 문장 · 다음 행동 먼저 · 모델이 못 받는 칸만 든 파일도 FAILED · 마이그레이션 «없음» · 재기동 워처 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  파일 기록 · 워처 줄이 한 문장: 「Next: declare the undeclared columns in table_config.json; reload or restart so this process holds the
>              unmapped columns, then Retry the file. Not written: undeclared_column a=3; unmapped_column c=5 over N row(s).」(있는 사유만)
>              전엔 「Dropped N undeclared column(s) ...」 과 「Not written (unmapped_column): ...」 두 문장
>              선언됐지만 이 프로세스 모델이 못 받는 칸만 든 파일(쓴 행 0) -> 이제 FAILED 「... Nothing was written to '<표>' - dropped: unmapped_column <칸>.」
> 돌릴 명령     없음
> 뜻           undeclared_column = 표 선언(table_config.json)에 없는 칸 -> 선언하거나 그대로(옛 필드면 버리는 게 맞음)
>             unmapped_column = 선언엔 있는데 이 프로세스가 아직 모름 -> 리로드/재기동 뒤 그 파일 Retry
>             WARNING 은 (사유, 칸) 이 이 프로세스에서 처음 보일 때 한 번, 그 뒤엔 파일마다 INFO
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **체인 범위 배치 — 권한(allow_replace_map / allow_retraction)을 봉투 독자가 묻음 · 동작 같음 · 마이그레이션 «없음» · 재기동 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  «되쓰기가 아닌» 배치의 권한 검사를 dt_map_derivation.normalize_scoped_batch 가 함(워커가 두 번 묻던 것을 뺌)
>              한 가지 다름: 권한도 없고 봉투도 틀린 배치는 이제 권한 문장이 먼저 나옴(격리 사유 글)
> 돌릴 명령     없음
> 뜻           격리 사유 「returned scoped batches without allow_replace_map or allow_retraction」 = 그 규칙에 두 권한 중 하나를 줘야 함(되쓰기만 하는 규칙은 필요 없음)
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **가지 — 기본과 가지 «둘 다» 거절한 소스는 «안 바뀜» · 가지 걷기에 기본 원자가 보임 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  가지가 말하는 소스 = 선언 지문이 기본과 다른 소스. 이제 양쪽 선언이 다 그 소스를 거절하면(예: 뷰를 읽는 소스) 가지는 새로 말할 것이 없으니
>              가지 뷰가 그 소스의 기본 원자를 그대로 보임. 한쪽만 거절하면 여전히 «바뀜»(가지 뷰에서 기본 원자 빠짐)
> 돌릴 명령     없음. 이미 만든 가지는 다음 --world 번역이나 가지 선언 저장 때 뷰가 다시 지어짐
> 뜻           가지 걷기에서 어떤 소스가 통째로 안 보이면 = 그 소스가 가지 쪽에서만 거절됨(가지 선언을 고치거나 --world 번역)
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **--whole-source 가 표가 잃은 행의 원자도 거둠 (모든 세상) · --apply 없이 미리보기 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  --whole-source 는 페이지로 다시 번역한 뒤, 색인엔 있고 표엔 없는 행(따라가기가 놓친 삭제 · 가지는 따라가기가 없음)의 원자를 삭제처럼 거둠
>              기본 세상에서도 같음 — 따라가기가 이미 거뒀으면 0
> 미리보기       python -m ledger.backfill --source <소스> [--world <이름>] --whole-source   (--apply 없이 · server/ 에서)
>              -> relation_rows(표 행) · gone_rows(표가 잃은 행) · gone_atoms(거둘 원자). 번역은 안 함
>              관리 화면의 소급 작업(ledger_rescope, whole_source) 미리보기도 같은 셋
> 거두기        같은 명령에 --apply -> gone_rows · gone_withdrawn
> 뜻           gone_rows > 0 인데 기본 세상 = 따라가기가 그 삭제를 못 봄(큐가 비었거나 워커가 꺼져 있던 동안) — 거두는 게 맞음
>             가지는 늘 따라가기가 없으니 기본 표에서 지운 행은 여기서만 거둬짐
> 가지 속도(박스 수)  lot_slot_wafer 37,325 행 -> 원자 37,325 · 88.7 초 (421 행/초 · 2.38 ms/행) · 19 배치 — 임시 가지로 한 번 잼
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **원장 프레임은 NaN 을 만들지 않음 — DB 의 NULL 이 None 으로 끝까지 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  DB 행 -> 원장 소스 프레임(backfill._v2_frame) · 준비기 출력 -> 프레임 칸(_assemble_prepared_frame) 을 object 로 지음
>              pandas 3 은 NULL 이 섞인 글자 칸을 str 로 잡아 None 을 NaN 으로 바꿨음 — 이제 None 그대로
>              그래서 when 비교(_when_value) · 정본 JSON 의 NaN 갈래가 빠짐. 번역 결과는 같아야 함(NULL 이 든 글자 칸 = 빈 칸으로 견줌)
> 돌릴 명령     없음. 재기동 뒤 따라가기가 평소처럼 도는지만
> 뜻           로그 「value is not deterministic JSON ... NaN」 으로 배치가 거절되면 = 어딘가 프레임이 아직 NaN 을 만듦(원장 밖에서 지은 프레임) -> 그 소스 이름과 보고
>             「mat_type='nan' said no sentence」 처럼 nan 글자가 보이면 = 같은 원인
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **row 소스의 group_by — 폼에 안 그림 · 저장하면 파일에서 빠짐 · 없음은 빈 목록으로 읽음 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  선언 폼: unit=row 소스엔 group_by 칸이 없음(스켈레톤 when {unit: group}). 「Filled: unit=row -> no group_by」 줄들이 사라짐
>              저장: row 소스 파일에서 "group_by": [] 가 빠짐. 검증·컴파일은 없음을 빈 목록으로 읽음(setup_bundle.read_group_by)
>              라이브 파일에 [] 가 남아 있어도 그대로 유효 — 폼은 빈 목록이면 안 그림(클라 92ad06716). 한 번 저장하면 파일에서도 빠짐
> 돌릴 명령     없음. 재기동 뒤 탐색기에서 row 소스(dt_job 등) 하나 열기 -> group_by 칸 없음 · group 소스(lot_event) -> 지금과 같음
> 뜻           row 소스를 저장한 뒤 그 소스 커서가 cursor_snapshot_reset_required 로 서면 = 소스 지문이 움직인 것(추적 표본 여섯에선 [] 든 파일 · 저장한 파일이 같음을 잼) -> 보고
>             group 소스에서 group_by 를 지우면 「field is required」 거절 — 정상
> 급할 때       커밋 되돌리기(되돌린 코드는 group_by 를 모든 소스에 요구 — 저장으로 빠진 row 소스엔 "group_by": [] 한 줄 다시)
> ```

---

> ## 🔴 [09-30 밤] **원장 가지 — 선언을 바꿔 시험하는 세상 · 가지 없는 설치는 그대로 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  가지 <이름> = 선언 파일 하나(config/ontology_worlds/<이름>/ledger_config.json) + PG 스키마 하나(w_<이름>)
>              가지에는 «기본과 선언이 다른 소스»의 원자만. 걷기는 가지 뷰 = 가지 원자 + 기본 원자(그 소스 빼고)
>              따라가기(체인)는 기본만 — 가지는 사람이 명령으로 다시 번역
> 만들기        탐색기 Bootstrap 에 world=<이름> — 기본 선언을 복사해 시작. 그 세상의 선언을 탐색기에서 고침(요청마다 world=<이름>)
> 번역          python -m ledger.backfill --source <바꾼 소스> --world <이름> --whole-source --apply   (server/ 에서 · 가지 스키마·표·뷰도 이 명령이 만듦)
> 걷기 · 보드    /api/ledger/subgraph · /key-values · /gaps · /declaration 에 world=<이름> · /declaration 의 worlds 칸 = 가지 목록
>              대조 저장 행(contrast_run)의 world 칸 — 라이브 table_config 의 contrast_run 에 "world": "string" 한 줄(표본대로. 저장하면 감시가 칸을 더함)
> 병합          탐색기 기본 세상(world 없음)에서 그 소스 선언을 가지 것으로 저장·활성화
>              → python server/scripts/ledger_restamp_cursor.py --apply
>              → python -m ledger.backfill --source <소스> --whole-source --apply   (옛 선언 원자는 페이지마다 걷히고 새로 씀 · 한 페이지 한 커밋)
>              → 가지 지움
> 지우기        DELETE /admin/ontology-explorer/worlds/<이름> → 미리보기(스키마 · 원자 수 · 파일). 같은 요청에 ?confirm_atoms=<그 수> → 지움(되돌릴 수 없음)
> 은퇴          backfill · ledger_restamp_cursor 의 --ontology-root → --world. 저장된 작업의 ontology_root 칸: 기본 뿌리면 기본으로, 다른 경로면 이름 대어 거절
> ASSY_DATA_ROOT 세운 설치는 원장 선언을 <DATA_ROOT>/config/ontology 에서 읽음 — 전과 다른 파일이면 커서가 선다(위 restamp)
> 뜻           404 「world_unknown」 = 그 이름의 가지 선언 파일이 없음. 503 「ledger_relation_absent」 relation w_<이름>.ledger_view = 가지를 아직 번역 안 함(위 번역)
>             가지 선언을 손으로 고치면 «가지가 말하는 소스»는 다음 --world 번역 때 다시 정해짐(그 전까지 뷰는 전 번역 기준)
>             기본 원천 행이 지워지면 가지 원자는 다음 --whole-source --apply 가 거둠(가지엔 따라가기가 없음 · --apply 없이 돌리면 몇 행 · 몇 원자인지 먼저 보임)
> 급할 때       가지만 끄기 = 가지 지우기. 가지 없는 설치는 이름 · 원장 · 커서가 전과 byte 같음. 코드는 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 밤] **nokey 로 적은 키 칸이 «아예 없는» 파일도 적재 — 마이그레이션 «없음» · 재기동 워처 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  표준 파서 헤더 검사: null_policy 에 nokey 로 적은 키 칸은 헤더에 없어도 통과 — 그 칸은 쓰기 문이 nokey_… 로 채움
>              전: 그 칸이 헤더에 없으면 「required key column(s) missing from header」 로 파일째 거절(err/ 로)
> 누가          null_policy 에 nokey 를 적은 표만. 안 적은 표는 전처럼 거절
> 확인          그 파일의 줄 「N row(s) keyed nokey_... (<칸>).」
> 뜻           전에 err/ 로 간 그런 파일은 다시 넣으면 적재됨
> 급할 때       null_policy 에서 nokey 를 지움 — 그 칸이 없는 파일은 다시 거절
> ```

---

> ## 🔴 [09-30 밤] **원장 커서 칸이 빈 행 — 그 행이 든 분자만 이름 대어 거절, 배치는 계속 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  원장 번역: 커서 칸(read.order_by)이 빈 행이 든 분자를 no_raw_ref 로 거절 1 건 — 같은 배치의 나머지 분자는 번역됨
>              전: 그런 행 하나가 배치 전체를 멈춤 「cursor number must be finite」 — 이 박스 dt_log 에서 작업 3 개(144 행), 그 작업을 따라갈 때마다
>              묶음 소스(group_by 가 있는 소스, 예 dt_job)는 그 분자를 «통째로» 거절 — 남은 행으로 작은 사건을 짓지 않음
> 확인          서버·체인 워커 로그에 「cursor number must be finite」가 더는 안 남
>              대신 거절 표본: 사유 no_raw_ref · 주소 bundle.sources.<소스>.read.order_by.<칸>
>              문장 「molecule …: row … leaves its cursor column <칸> empty - … fill <칸>」
> 뜻           그 줄 = 원천 표의 그 행 커서 칸이 비어 있음. 할 일은 그 칸을 채우는 것 — 채우면 다음 따라가기가 그 분자를 번역
>             그 분자에 전에 적힌 원자는 거절되는 동안 원장에서 걷힘 — 편집으로 칸을 비우면 걷히고 채우면 돌아옴(PG 에서 잼)
>             거절 수는 그 작업을 따라갈 때마다 늘어남 — 채울 때까지
>             identity · group_by 칸이 빈 행은 전처럼 페이지째 멈춤 — 문장만 「driver identity/group_by value is missing」 으로
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 밤] **DT 스텝 뒤 공정 행은 dtwafer 로 — 표본 선언 셋을 라이브에 옮기면 켜짐 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커(번역 ①②) · 선언 ③ 은 리로드 + 커서 지문**
>
> ```
> 무엇이 바뀌나  ① 원장 번역: 어느 문장의 when 에도 안 맞은 행을 값마다 세어 — 「[Ledger] Next: … <소스>: mat_type='WF' said no sentence …」 (10-01 부터 1·10·100… 단위에서 한 줄, 수는 하트비트 노트)
>              ② 원장 번역: 문자열 칸의 NULL(pandas 3 에선 NaN)이 배치 전체를 멈추던 것이 멈추지 않음 — 09-10 박스 로그의 「not deterministic JSON … nan」
>              ③ 표본 선언(추적 파일)에 스텝 가르기 — 라이브 선언에는 «운영자가 옮길 때» 켜짐. 옮기기 전엔 동작 그대로
> 옮기기        표본 server/config/sample 의 세 파일에서 그대로:
>              table_config   step_phase 표(business_key · composite_key_source = step, 칸 step · mat_type) · wafer_process 에 mat_type 칸
>                             저장하면 웹 서버의 설정 감시가 표를 만들고 칸을 더함 — 서버 로그 「Physical database schema synced successfully.」
>              chain_rules    step_phase_to_wafer_process 조인(체인 탭 저장 — 리로드 불필요)
>              ledger_config  dtwafer@1 · processed_with@1 subjects 에 dtwafer@1 · wafer_process_recipe 문장 둘(when mat_type "" / "DT") · input_columns 에 mat_type
>              curl -X POST "http://<host>:8080/admin/reload-configs" -H "X-Admin-Token: <토큰>"
>              python server/scripts/ledger_restamp_cursor.py --apply     (선언이 바뀌어 커서가 선 것을 풀기 — 위치는 안 움직임)
> 운영자 두 줄   「운영에서는 step_phase 표에 DT 스텝을 한 줄씩 적으면 됩니다(스텝 · DT).」
>              「결함 계측 표에도 같은 조인 한 줄, 다이 문장을 when 으로 둘(빈 칸 -> mat_type Wafer · DT -> DT).」
> 확인          DT 스텝을 적으면 그 스텝의 공정 행 mat_type 이 DT 가 되고, 원장의 그 행 원자가 wafer -> dtwafer 로 옮겨감(옛 원자는 지워짐)
> 뜻           「mat_type='WF' said no sentence」 = 단계표에 DT 가 아닌 값(WF · 오타)을 적은 스텝 — 그 행은 원장에 안 감. 그 칸을 비우거나 DT 로
>             스텝을 빼려면 단계표 행을 지우지 말고 mat_type 칸을 비울 것 — 지운 행은 채웠던 공정 행에 닿지 않아 DT 가 남음(잰 것)
>             「cursor number must be finite」 = 이제 안 남 — 바로 위 절(커서 칸이 빈 행)
> 놓친 따라가기  원장 따라가기 줄은 메모리라 워커가 죽으면 잃음 — 그때만: python -m ledger.backfill --source wafer_process_recipe --scope-column mat_type --scope-values DT --apply (server/ 에서)
> 급할 때       스텝 가르기만 끄기: 단계표를 비움(행의 mat_type 을 비우면 원자가 wafer 로 돌아감) · 코드 되돌리기는 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 저녁] **HTML 토폴로지 파서 — 한 헤더 경로에 값 칸 둘이면 이름 대어 거절 · 옆 그룹 헤더가 안 섞임 · 마이그레이션 «없음» · 재기동 «없음»**
>
> ```
> 무엇이 바뀌나  HTMLTableGraphParser.extract_semantic_tuples — 두 값 칸의 헤더 경로가 같으면 ValueError (전: 뒤 칸만 남고 앞 칸이 말없이 사라짐)
>              같은 줄에 나란히 선 그룹 헤더(A · B)는 자기 열 아래 칸에만 붙음 (전: B 가 A 의 칸에도 붙어 값 하나가 사라짐)
> 누가 부르나     이 박스: 추적 코드 0 · ingestion_workspace 파이썬 18 개 중 0 (bonding_map 은 HTMLMatrixTableParser — 안 바뀜)
> 확인          이 함수를 부르는 커스텀 파서가 있으면, 헤더 경로가 겹치는 파일은 그 파일 줄에
>              「Next: mark the cell that tells these rows apart as a header (is_header_fn) … N value cells share one header path … The path: (…)」 — 다음 행동이 맨 앞(파일 상태 칸이 500 자만 남겨도 안 잘림, 09-30 f7738d7a4)
> 뜻           그 줄 = 전에는 값 일부를 조용히 잃던 파일. 할 일은 행을 가르는 칸(예: 웨이퍼 열)을 is_header_fn 에서 헤더로 — 그 뒤 다시 올리기
>             위아래로 쌓인 표는 거절이 아니라 가이드 §3.1-bis(먼저 나눠 읽기)
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 저녁] **원장 선언 폼 — column 바인딩의 Time zone 칸이 글자 상자로 · 마이그레이션 «없음» · 재기동 «없음» (리로드 한 번)**
>
> ```
> 무엇이 바뀌나  원장 선언 폼에서 Binding 이 column 인 칸마다 뜨던 「Time zone … No shape · broken」 줄이 글자 상자로 뜸
>              값은 시간대 이름(예 Asia/Seoul) — 목록에서 고르는 칸이 아니라 적는 칸 (read.occurred_at 의 Time zone 과 같은 모양)
> 할 일         curl -X POST "http://<host>:8080/admin/reload-configs" -H "X-Admin-Token: <토큰>"   (스켈레톤 캐시를 비움 — 서버 재기동 불필요)
> 확인          원장 선언 폼 · 어느 소스의 bind · column 바인딩 하나 → Time zone 칸이 상자, 「No shape · broken」 없음
> 뜻           리로드 뒤에도 그 줄이 남으면 화면이 옛 응답을 들고 있는 것 — 폼 새로고침
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 저녁] **nokey 값의 시각이 마이크로초까지 — 마이그레이션 «없음» · 재기동 서버 · 워처 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  nokey_<첫 적재 시각 UTC, 마이크로초까지 — 20260930T051503.123456Z>_<6 hex> (전: 초까지)
>              같은 초에 처음 적재된 두 파일의 행이 우연히 같은 6 hex 여도 안 합쳐짐
> 확인          nokey 칸 값에 소수점 여섯 자리
> 뜻           ⚠️ 바로 앞 절(nokey)을 운영에 올려 이미 채운 파일이 있으면, 그 파일을 Retry 할 때 값 모양이 달라 새 행이 생김 — 안 올렸으면 영향 0
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **행마다 부르는 체인 규칙의 batches · 맵 메타데이터도 씀 — 마이그레이션 «없음» · 재기동 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  "is_batch" 가 없는(행마다 부르는) 규칙이 돌려준 batches · map_metadata_updates 를 워커가 버리던 것을 이제 읽음 — 배치 규칙과 같은 한 길
>              허락 칸 검사도 같음: 맵 메타데이터는 allow_map_metadata_upsert, 봉투는 그 규칙의 허락 · trigger 표 되쓰기는 덮어쓰기만
> 이 박스 · 표본  불러오는 규칙이 전부 "is_batch": true 라 동작이 바뀌는 규칙 0 (박스 15 · 표본 11)
> 확인          행마다 규칙이 되쓰기 · 봉투를 돌려주면 그 표에 써짐 · 허락 없는 맵 메타데이터는 이름 대어 실패
> 뜻           @mapper 규칙의 allow_retraction · allow_replace_map 은 여전히 "is_batch": true 가 필요 — 문장이 바뀜:
>             「called row by row, each row's call removes what the other rows of its job or map made」
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **키 칸이 빈 파일 행을 nokey_… 로 채움 — 선언한 표만 · 마이그레이션 «없음» · 재기동 서버 · 워처 (run_app.bat 로 전체)**
>
> ```
> 선언          표 선언 null_policy 에 키 칸마다 "nokey" — 예 "null_policy": {"slot": "nokey"} (표 편집기 저장). 안 적은 표는 그대로
> 값            nokey_<그 파일의 첫 적재 시각 UTC, 20260930T051503Z>_<6 hex>
>              6 hex = (파일 내용 시그니처의 해시 + 행 번호) mod 16^6 — 같은 파일이면 Retry 에도 같은 값(옛 행을 찾음), 한 파일 안에서는 안 겹침
> 누가 채우나     파일에서 온 행만(워처 — 표준 파서 · 파이프라인). 그리드 입력 · 체인 쓰기는 안 채움
>              표준 파서는 nokey 칸이 빈 행을 더는 안 버림(전에는 「키 컬럼 공백/결측으로 스킵」)
> 확인          파일 줄 「N row(s) keyed nokey_... (<칸>).」 · 표의 그 칸에 nokey_… 값
> 뜻           「N row(s) not keyed nokey (<칸>) - the file has no content signature …」 = 파일 내용을 못 읽어 안 채움, 그 행은 전처럼 키 없이
>             ⚠️ 이어쓰는 로그 파일은 내용이 바뀌면 시그니처가 바뀌어 앞 행들이 «새 nokey» 를 받고 행이 겹침(잰 것: 3 행 파일에 1 행 더해 다시 올리면 7 행)
> 급할 때       표 선언에서 "nokey" 를 지우고 저장 — 그 뒤 파일부터 채우지 않음(이미 채운 행은 그대로)
> ```

---

> ## 🔴 [09-30 오후] **원장 선언 계획에 «물려받은 속성» 행 — 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  역할이 entity 이고 자기 attributes 를 안 적었으면, 계획(GET/POST /admin/ontology-explorer/authoring/plan)에
>              그 역할의 attributes 자리에 읽기 전용 행 하나 — 값 = 번역이 묶는 속성 · ground.rule "inherited_from_source" ·
>              근거 = 그 소스의 bind.entities.<타입>.attributes
>              저장은 그 행을 역할에 «안 씀»(쓰면 역할이 덮어써서 소스 쪽 고침이 안 따라감)
> 확인          속성을 소스에 적은 소스의 계획에서 그 타입을 쓰는 역할마다 그 행
> 뜻           역할이 자기 attributes 를 적었으면 그 행이 없음 — 그 역할은 소스 것을 안 씀
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **표 스키마 응답에 smart_paste — 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  GET /tables/<표>/schema 에 "smart_paste" — 표 선언(table_config.<표>.smart_paste)을 그대로. 안 적은 표는 null
> 확인          선언한 표의 스키마 응답에 그 목록 · 안 적은 표는 null
> 뜻           null = 순서를 안 적음(클라가 묻는 쪽) · [] 는 오지 않음
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **원장 선언 저장이 꺼진 갈래의 칸을 걷음 — 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  바인딩을 column -> constant 로 바꾸면 남던 "column": "" 같은 칸을 저장이 걷음(스켈레톤의 when)
>              저장(PUT drafts/<id>)과 저장 없는 계획(POST authoring/plan)이 같은 자리를 지남
>              응답에 dropped_fields: [{path, value}] — 걷은 칸과 그 값
>              kind 를 아직 안 고른 바인딩은 아무것도 안 걷음(저장이 이름 대어 거절)
> 확인          원장 선언 창에서 역할 하나를 column -> constant 로 바꿔 저장 -> 저장됨 · dropped_fields 에 그 column
> 뜻           dropped_fields 가 비었는데 unknown_field 로 거절되면 when 이 없는 칸이 남은 것 — 그 경로를 적어 올릴 것
>             엔티티 · 키 · 속성 · 술어 · 한정어 · 컬럼 이름을 바꾸거나 지운 흔적은 이 변경이 안 걷음 — 저장이 이름 대어 거절(보고의 표)
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **시각 칸은 같은 순간이면 같은 값 · 빈 글은 None — 마이그레이션 «없음» · 재기동 서버 · 워처 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  「칸 값이 바뀌었나」를 묻는 자리(AST 로 센 것 — 보고에 표)가 한 함수(crud.value_key)를 지남
>              datetime 칸 = 순간으로 견줌(「…T08:00:00+09:00」 = 「… 08:00:00+09:00」 = 「…T23:00:00Z」 전날)
>              꼬리 없는 시각 = PG 세션 시간대로 읽음(쓰기 문이 PG 에 넘길 때와 같음 — 연결마다 PG 가 알려 줌, 질의 없음)
>              빈 글('' · 공백만) = None (판정 284)
> 운영에서 보일 것 같은 순간을 다른 철자로 다시 보낸 파일 · 체인이 같은 순간을 다시 옮긴 것 -> 칸 안 씀 · ROW_UPDATE 이력 줄 0 · 체인 사건 0
>              파일 줄의 「바뀐 칸」 수가 그만큼 줄어듦 · R3 dry-run 이 철자만 다른 칸을 안 셈
>              옛 행의 '' 칸 위에 이긴 층이 None 이면 안 다시 씀(전에는 매번 None 으로 씀)
>              버전 게이트의 「같은 판 다른 내용」 경고가 철자만 다른 시각에는 안 뜸
>              셀 원천 삭제 · 우선순위 지정의 이력 줄이 같은 값이면 안 남음
> 확인          같은 파일을 다시 떨어뜨려 파일 줄의 바뀐 칸이 0 인지 · 다른 순간을 넣으면 전처럼 씀
> 뜻           다른 순간인데 안 써지면 이 변경이 원인일 수 있음 — 그 칸의 두 값과 PG 의 SHOW TimeZone 을 같이 적어 올릴 것
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **대조 run 행이 스스로 말함 — computed_at · candidates · contrast · complete — 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 준비          운영 table_config 의 contrast_run 에 칸 넷: computed_at(datetime) · candidates(number) · contrast · complete(string) — 표 편집기 저장
>              운영 chain_rules 의 contrast_factor_from_run 에 "is_batch": true 한 칸 — Chain 탭 저장 (표본 server/config/sample/chain_rules.json.sample 과 같게)
>              둘 중 하나라도 빠지면: 칸이 없으면 그 칸은 버린 칸(unmapped/undeclared)으로 셈 · is_batch 가 없으면 run 행에 아무것도 안 씀
> 무엇이 바뀌나  체인이 대조를 계산한 같은 호출에서 그 run 행에 넷을 되씀. factor 행은 contrast · complete 를 더는 안 씀(옛 행의 값은 남음)
>              규칙은 읽은 표(trigger)에만, 덮어쓰기로만 되쓸 수 있음 — 다른 표는 「cannot redirect a scoped batch … only the rule's trigger table」 로 거절
> 확인          체인 워커 로그 「Executing chained batch updates to 'contrast_run' …」 · 그 run 행의 computed_at 이 참
> 뜻           넷 다 빔 = 아직 안 돎(또는 until 이 비어 거절) · computed_at 있고 candidates 0 = 돌았고 후보 0
>             [ChainRule] 줄의 rows_out 은 이제 factor 행 수 + run 행 수(run 하나면 N+1)
> 급할 때       Chain 탭에서 contrast_factor_from_run 의 enabled 를 false 로 저장
> ```

---

> ## 🔴 [09-30 오전 4] **조인이 시각 칸 값을 옮겨도 쓰기가 안 깨짐 — 층 · 표 · 다시 읽은 값이 같은 순간 — 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  조인의 take 가 datetime 칸이면 전에는 그 규칙의 쓰기 묶음이 통째로 TypeError(층 JSON 이 파이썬 시각을 못 씀)
>              이제 쓰기 문 경계가 시각 값을 시간대 꼬리 있는 ISO 글로 바꿔 층 · 표에 씀 — 같은 순간
>              파일에서 오는 글 값은 한 글자도 안 바뀜
> 확인          그 조인이 돈 뒤 체인 로그에 TypeError 줄이 없고, 그리드 그 칸 · 소스 관리의 chain_ingestion 층에 값
> 뜻           같은 순간을 다시 옮기면 표 칸을 매번 다시 씀(값 비교가 글자라 철자만 달라도 «바뀜») — 사건이 그만큼 남음
>             행 방송의 시각 TypeError(동결 09-29)는 그대로 — 방송은 커밋 뒤 표에서 다시 읽은 시각을 실음
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-30 오전 3] **설정엔 있는데 떠 있는 프로세스의 모델이 모르는 칸은 층도 표도 안 씀 — 버린 칸으로 세고 파일 줄에 이름 — 마이그레이션 «없음» · 재기동 서버 · 워처 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  Reload 실패 · 설정과 모델이 갈리는 순간 · 모델이 건너뛰는 칸 이름(is_graph_synced · needs_graph_rollback ·
>              graph_synced_at) — 전에는 층엔 값을 쓰고 표 값은 조용히 안 써서 「층엔 값 · 표엔 빈칸」이 됐음
>              이제 그 칸은 층도 표도 안 쓰고 버린 칸(unmapped_column)으로 셈 — 층과 표가 어긋나지 않음
> 확인          파일 처리 줄(워처 로그 · 파일 기록)의 「Next: reload or restart so this process holds the unmapped columns, then Retry the file. Not written: unmapped_column <칸>=<값 수> over N row(s)」(10-01 d4a949a8c ③ 에서 이 모양으로 — 옛 글: declared, but this
>              process's model does not hold the column; reload or restart, then Retry the file.」
> 뜻           그 줄이 뜨면 그 칸 값은 «어디에도» 안 들어감 — Reload(안 되면 재기동) 뒤 그 파일을 Retry 하면 들어감
>             칸 이름이 위 셋 중 하나면 Reload · 재기동으로도 안 됨 — 표 편집기에서 칸 이름을 바꿔야 함
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-30 오전 2] **기존 표에 칸을 더하고 저장 · Reload 만 해도 그리드가 그 칸을 보여 줌 (재기동 없이) — 마이그레이션 «없음» · 재기동 서버 · 워처 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  표 편집기로 칸을 더해 저장하거나 Reload 해서 떠 있는 프로세스가 그 칸을 모델에 붙이면, 그 프로세스의
>              SQL 컴파일 캐시를 비움 -> 전에 쓰던 질의도 새 칸을 실어 읽음
>              전에는 표와 층엔 값이 있는데 그리드가 그 칸을 모든 행에서 빈칸으로 보였고, 재기동해야 떴음
>              칸이 안 바뀐 저장 · Reload 는 캐시를 안 비움
> 확인          칸을 더해 저장 -> 파일 한 번 적재 -> 새로고침 없이도(다음 페이지 요청에서) 그리드에 그 칸 값
> 뜻           이 수리는 재기동 «뒤»부터 들어감 — 지금 떠 있는 프로세스는 옛 코드라 이번 재기동 한 번은 필요
>             저장 순간 표가 바쁘면(누가 읽는 중) 칸을 만드는 ALTER 가 20초 잠금에 밀려 칸이 안 생길 수 있음 — 서버 로그
>             「[Schema Sync] column '…' was not added to '…' - another session held the table past 20s」 가 뜨면 그 칸은
>             다음 저장이나 재기동 때 생김(이 수리와 별개)
> 급할 때       스위치 없음 — 재기동이 옛 방법 그대로 풀어 줌
> ```

---

> ## 🔴 [09-30 오전] **원장 선언 창: 역할을 엔티티로 고르고 키 없이 저장해도 500 없음 · 저장 없이 키 칸을 받는 읽기 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  역할을 entity 로 고르고 키를 아직 안 적은 채 Save -> 전엔 500(KeyError 'keys'), 이제 저장되고 그 칸의 거절 이름이 뜸
>              POST /admin/ontology-explorer/authoring/plan  {selection, draft_id, raw} -> 저장 없이 그 본문의 폼(키 칸 포함)
>              GET plan 과 같은 답 모양 · 쓰는 것 0 · 화면이 이 길을 부르는 것은 클라 몫
>              plan 의 행마다 "reshapes" — true 인 잎(entity_type · kind · predicate …)이 바뀌면 화면이 다시 물음
> 확인          그 Save 가 200 이고 화면에 「Saved but not applied」 와 그 칸의 거절 줄
> 뜻           「Saved but not applied」 인 채 파일에 남은 소스는 재기동 뒤 원장이 «그 소스만» 안 읽음 —
>             서버 로그 「[Ledger] source <id> is NOT planned: …」(다른 소스는 읽음). 키를 채워 다시 저장하면 풀림
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-30 아침] **대조 저장 — contrast_run 한 줄 -> 체인 -> contrast_factor (걷기의 순위 그대로) — 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체를 다시 띄우면 둘 다 됨)**
>
> ```
> 준비          표 둘: server/config/sample/table_config.json.sample 끝의 contrast_run · contrast_factor 를 운영 table_config 에 (표 편집기 저장)
>              규칙 하나: server/config/sample/chain_rules.json.sample 끝의 contrast_factor_from_run 을 운영 chain_rules 에 (Chain 탭 저장)
>              맵퍼는 추적 파일 server/mappers/contrast_walk.py — Chain 탭 맵퍼 고르개에 소유자 맵퍼와 같이 «mappers.contrast_walk / contrast_walk» 로 뜸
> 무엇이 바뀌나  contrast_run 에 행이 들어오면 체인이 그 행의 인자로 걷기 라우트(GET /api/ledger/subgraph)를 부르고
>              propagation.ranked 를 contrast_factor 행으로 씀 — 키 run_id + node_id. until 이 걷기를 묶음
> 확인          체인 워커 로그 「[ChainRule] rule=contrast_factor_from_run kind=mappers.contrast_walk.contrast_walk target=contrast_factor rows_in=1 rows_out=<N> …」
>              같은 인자로 부른 걷기의 propagation.ranked 수 = <N> = contrast_factor 에서 그 run_id 의 행 수
> 뜻           contrast=unexamined -> 양품(negative) 씨앗이 없었음 · complete=false -> 걷기가 잘림(node_limit) — 순위는 잠정
>             「[ContrastWalk] … until is empty - …」 -> until 이 빈 run 이라 안 씀 (걷기를 묶을 수 없어서)
>             until 은 시간대를 붙여 적는다 — 안 붙이면 DB 세션 시간대로 읽힘(보드는 Z 를 붙여 보냄, 그리드에 손으로 적을 때만 해당)
>             행 0 -> 후보 0 이거나 아직 안 돎 — 둘을 가를 자리는 아직 없음(보고의 제안)
>             contrast_run 행을 지우면 -> 그 run 의 factor 행은 «남고» 칸이 전부 비워짐(맵퍼가 찍은 도장으로 걷힘, 키 R1|<노드> 만 남음)
>             그때 「[ChainRetract] … 파일 맵퍼는 … 적는지는 제품이 모릅니다」 줄이 나와도 이 규칙엔 해당 없음 — 이 맵퍼는 도장을 찍음
> 급할 때       Chain 탭에서 contrast_factor_from_run 의 enabled 를 false 로 저장
> ```

---

> ## 🔴 [09-29 밤 4] **체인 규칙을 저장하면 체인 워커가 «규칙만» 다시 읽음 — 마이그레이션 «없음» · 재기동 run_app.bat 전체(서버 · 체인 워커 · 워처 · 스케줄러)**
>
> ```
> 무엇이 바뀌나  Chain 탭 저장 · 문법 변환 -> 범위(chain_rules)를 실은 SYSTEM_RELOAD 한 행
>              체인 워커: 규칙 파일만 다시 읽음 — 매퍼 다시 불러오기 · 표 모양 맞추기 · 웜업 없음
>              워처 · 스케줄러: 그 행은 지나감. Reload 버튼(범위 없음)은 전과 같이 전부
> 확인          체인 워커 로그 「[Reload] SYSTEM_RELOAD chain_rules (Event ID: N) - re-reading the chain rules only」
>              바로 다음 「[Reload] Loaded N active chain ingestion rules.」 — 저장 뒤 보통 1 초 안, 길어도 3 초
>              GET /admin/chain/queue 의 rules_base 가 저장 답의 base 와 같으면 워커가 그 저장을 읽은 것
>              rules_loaded_age_seconds 는 그 뒤 지난 초
> 뜻           rules_base 가 저장 답의 base 와 다르면 워커가 아직 안 읽음 — 3 초 넘게 다르면 워커 로그를 봄
>             서버 로그 「saved, but the chain worker was NOT told」 -> 워커는 모름. Reload 를 누름
>             규칙이 새 맵퍼 이름을 가리키면 그 이름을 못 찾을 때만 맵퍼 폴더를 한 번 더 훑음
>                새 «파일»은 찾음 · 이미 불러온 파일에 새로 적은 함수는 못 찾음(「unresolvable」) -> Reload
> 급할 때       스위치 없음 — Reload 버튼이 전과 같이 전부 다시 읽음
> ```

---

> ## 🔴 [09-29 밤 3] **유일 인덱스 보고의 「빈 키」가 조인과 같은 판정 — 마이그레이션 «없음» · 재기동 체인 워커 · 서버 (run_app.bat 로 전체를 다시 띄우면 둘 다 됨)**
>
> ```
> 무엇이 바뀌나  인덱스 보고(키가 «비어 있습니다» — 중복이 아니라 부재)의 빈 판정이 조인의 것(crud.is_blank_key_part)과 하나
> 확인          보고 문장은 그대로 — PostgreSQL 에선 키 식이 텍스트라 NaN 키는 'NaN' 으로 와서 전처럼 «중복», NULL·빈 값은 전처럼 «부재»
> 뜻           갈리던 값은 실수 nan · inf · -inf 셋뿐이고 PostgreSQL 보고엔 그 값이 실수로 들어오지 않음
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 밤 2] **조인 선언 한 칸 `derive.join.blank: "skip"` — 짝이 된 빈 값은 안 씀(파일 값이 섬) — 마이그레이션 «없음» · 재기동 체인 워커 · 서버 (run_app.bat 로 전체를 다시 띄우면 둘 다 됨)**
>
> ```
> 무엇이 바뀌나  적은 조인: 짝이 된 원천 행의 take 값이 비면 그 칸을 안 씀 — 층 없음, 파일 값이 그대로 보임
>              값이 있는 take 는 전처럼 덮음 · 안 적은 조인은 전처럼 빈 값을 씀
>              "skip" 말고 다른 낱말은 저장·로드에서 거절: 「derive.join.blank 'yes' - one of skip」
> 확인          서버 로그 「<규칙>: N blank answer(s) not written (blank: skip) - core_wafer_id=<n>」 (한 번 돌 때 한 줄)
> 뜻           이 칸을 켜도 그 조인이 «전에» 쓴 빈 층은 남아 파일 값을 계속 가림 — 아래로 걷음
> 이미 덮인 것  ① 수만 보기   python server/scripts/chain_replay_cli.py withdraw dt_log chain_ingestion --columns core_wafer_id
>             ② 걷기       같은 줄 끝에 --apply
>             ③ 다시 쓰기   python server/scripts/chain_replay_cli.py replay <조인 이름>:target   (수만 · 끝에 --apply 로 씀)
>             ⚠️ chain_ingestion 층은 칸당 «하나» — ② 는 빈 층만이 아니라 그 칸에 체인이 쓴 값 «전부»를 걷음
>                같은 칸을 쓰는 다른 규칙이 있으면 ③ 을 그 규칙들에도. ③ 이 끝날 때까지 그 칸은 파일 값(없으면 빈 칸)
>             같은 ①~③ 이 [09-29 밤] 의 것도 걷음 — 조인 키가 모두 빈 행끼리 전에 짝지어 쓴 값은 남아 있는데,
>                ② 가 그 칸의 체인 값을 걷고 ③ 은 이제 그 행을 짝짓지 않으므로 다시 안 씀. 칸은 그 조인의 take 칸들(--columns a,b)
> 급할 때       선언에서 blank 칸을 지우면 전처럼(빈 값을 씀)
> ```

---

> ## 🔴 [09-29 밤] **조인 키 칸이 «모두» 빈 행은 짝이 아님 — «일부»만 비면 그대로 — 마이그레이션 «없음» · 재기동 체인 워커 · 서버 (run_app.bat 로 전체를 다시 띄우면 둘 다 됨)**
>
> ```
> 무엇이 바뀌나  선언한 조인(derive.join)의 짝 키 칸이 모두 빈 행
>              into 표 행이면 답을 찾지 않음 · 원천(on.table) 행이면 누구의 답도 아님
>              키가 둘 이상이고 일부만 비면 전과 같이 빈 칸끼리 같음
> 확인          서버 로그 「<규칙>: N row(s) with every join key empty - not matched (target side)」
>              또는 「(value side)」 — 그 규칙이 한 번 돌 때 쪽마다 한 줄, N 이 0 이면 안 나옴
> 뜻           전에 빈 키끼리 짝지어 쓴 값은 «남음» — 이제 조인이 그 행에 대해 말하지 않으므로 지우지 않음
>             원천에 빈 키 행이 여럿이라 「둘 이상과 맞아 건너뜁니다」 가 나던 행은 이제 그 줄 대신 위 줄이 나옴
>             유일 인덱스는 안 바뀜 — 원천에 키가 모두 빈 행이 둘 이상이면 인덱스는 여전히 안 섬
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 저녁 3] **실패한 파일을 폴더째 재시도 — 먼저 보기(수 · 바로 아래 폴더별) — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  POST /admin/file-ingestion/retry-failed?folder=<폴더>  -> 그 폴더 «아래»(하위 전부) FAILED 만 PENDING_RETRY
>              ...&preview=true  -> 쓰지 않고 count · by_folder(바로 아래 폴더별 수, 폴더에 바로 있는 파일은 ".")
>              폴더 경계로만(C:\a\A 가 C:\a\AB 를 물지 않음) · 대소문자 · 구분자는 파일 시스템대로 · 외부 루트든 관리 폴더든 같은 판정
>              화면의 폴더 고르기 · 버튼은 클라 몫(총괄이 넘김)
> 확인          같은 폴더로 preview 의 count 가 곧 누른 뒤 PENDING_RETRY 가 되는 수
> 뜻           count 0 이면 「No failed file under <폴더>」 — 쓴 것 없음. preview 는 폴더가 없어도 아무것도 안 씀
>             외부 경로 판정도 같은 함수라 이제 대소문자를 파일 시스템처럼 봄(Windows 에서 경로 대소문자가 달라도 같은 루트)
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 저녁 2] **웹소켓 연결을 두 번 빼던 ValueError — 대기열 방송이 멈추지 않음 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  끊긴 연결을 방송의 보내기 실패와 /ws 끊김이 둘 다 빼도 둘째는 조용히 넘어감 — list.remove ValueError 없음
>              방송은 연결 목록의 사본을 돎 — 도중에 한 명이 나가도 다음 사람을 건너뛰지 않음
> 확인          서버 로그의 「Client disconnected. Total clients: N」 이 「list.remove(x): x not in list」 없이 나옴
>              「Error sending to a client」 가 난 뒤에도 대기열 탭이 계속 새로고침됨
> 뜻           전에는 그 ValueError 하나로 대기열 방송 루프가 끝나 재기동까지 대기열 화면이 안 바뀌었음
> 급할 때       스위치 없음 — 서버 재기동이 그 루프를 다시 세움
> ```

---

> ## 🔴 [09-29 저녁] **외부 경로 파일의 재시도가 워처의 «그 표 처리기»로 돔 — 폴더의 웨이퍼·시각·options 그대로 — 마이그레이션 «없음» · 재기동 워처**
>
> ```
> 무엇이 바뀌나  Retry(파일 인제션) -> PENDING_RETRY -> 워처의 재처리 폴러가 «그 표를 감시하는 처리기»로 다시 읽음
>              전에는 새 처리기를 만들어 외부 경로를 몰랐음 -> 외부 파일 재시도가 「No custom pipeline parser matched」로 다시 실패
>              워처가 처리기를 다 세우기 전엔 PENDING_RETRY 를 집지 않음(다음 바퀴에 집음)
>              워처가 감시하지 않는 표의 기록은 「the watcher runs no handler for table …」 로 FAILED
> 확인          외부 파일 하나가 FAILED 면 원인(예: unit 없음)을 external_sources[].options 로 고치고 워처 재기동 -> Retry
>              -> 인입 기록 SUCCESS · 행에 폴더의 웨이퍼 · cell source 이름 external:<parser>:<경로>
> 뜻           관리 raws/ 파일 재시도는 전과 같음(파일을 옮기지 않고 그 자리에서 읽음)
>             options 를 바꾼 것은 워처 재기동 뒤에만 처리기에 실림 — 재기동 없이 Retry 하면 옛 options 로 읽음
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 오후 3] **수집기 백필이 «다음 시작일»을 말함 — 지난 실행이 멈춘 자리 — 마이그레이션 «없음» · 재기동 서버 · 스케줄러(auto update) · 체인 워커**
>
> ```
> 무엇이 바뀌나  /admin/retroactive/runs 의 collector_backfill 실행마다 next_start (KST, backfill Start 칸이 받는 모양)
>              끝까지 돔 -> 마지막 창이 잘린 그 시각 · 취소 -> 끝낸 다음 날 00:00 · 실패 -> 실패한 날 · 도는 중 -> null
>              실행 결과에 done_until 이 실리고, 결과 문장에 「collected up to (KST) <날짜>」 가 붙음
>              화면의 Start 칸 미리 채우기는 클라 몫(총괄이 넘김) — 이 착지만으로는 칸이 안 바뀜
> 확인          백필을 한 번 돌리고 끝난 뒤 GET /admin/retroactive/runs 에서 그 실행의 next_start 를 봄
>              그 값을 Start 로 다시 돌리면 창이 이어짐(겹침 · 빈틈 없음)
> 뜻           null 이면 이어 누를 자리가 없음 — 도는 중이거나, 이 착지 «전»에 끝까지 돈 기록(잘린 자리가 안 적혀 있음)
>             재기동 전 스케줄러 · 체인 워커가 돌린 실행은 done_until 이 없음 — 끝까지 돈 것은 null, 취소 · 실패는 날 수로 답함
> 급할 때       스위치 없음 — next_start 는 제안일 뿐, Start 칸에 아무 날이나 적어 돌릴 수 있음
> ```

---

> ## 🔴 [09-29 오후 2] **저장 뒤 로드에서 빠진 선언이 탐색기 목록에 남음 — 같이 빠진 것까지 · 저장 답도 댐 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  원장 선언이 저장된 뒤 로드가 그 선언을 빼고 읽으면, 탐색기 목록(스냅숏 invalid)에 그 선언과 «같이 빠진» 선언이 남음
>              전에는 로드가 통째로 실패할 때만 목록이 찼음 — 하나만 빼고 읽으면 목록이 비었음
>              같이 빠진 것의 사유 = "entity <x> left out" · "predicate <x> left out" (전에는 한국어 문장)
>              저장 답(validation_errors)도 같이 빠진 것을 댐 — 같은 판정 자리(resolve_declarations)
>              빠진 것이 하나라도 있으면 스냅숏의 active_snapshot.valid 가 false
> 확인          서버 로그의 「[Ledger] <선언> is NOT read」 줄이 있으면, 탐색기 목록에도 그 선언이 사유와 함께 있어야 함
> 뜻           목록에 남은 것 = 파일에는 있는데 로드가 안 읽은 것. 같이 빠진 것은 앞의 것을 고치면 같이 돌아옴
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 오후] **체인 규칙은 «바뀔 때만» 읽음 — 대기열 새로고침이 규칙을 다시 읽지 않음 — 마이그레이션 «없음» · 재기동 서버 · 체인 워커**
>
> ```
> 무엇이 바뀌나  서버는 규칙을 한 번 읽어 두고 씀. 다시 읽는 때: 체인 규칙 저장(체인 탭 raw 편집기 · 문법 바꾸기) 직후 · Reload Configs
>              체인 워커는 전과 같음(부팅 · SYSTEM_RELOAD 때 읽음). 워커의 DELETE 그룹 경로도 읽어 둔 것을 씀
>              [ChainRules] set(N) 줄 = 실제로 다시 읽은 횟수. 대기열 탭이 방송마다 새로고침해도 줄이 안 늘어남
> 확인          grep -c "\[ChainRules\] set(" server/chain_worker.log   를 대기열 탭을 연 채 체인이 도는 동안 두 번 — 수가 그대로여야 함
> 뜻           저장하거나 Reload 를 누를 때만 한 줄씩 늚. 그 밖에 늘면 규칙을 요청마다 읽는 자리가 아직 있다는 뜻
>             ⚠️ 서버를 안 거친 파일 수정(손 편집 · 스크립트 · 복원)은 Reload Configs 를 눌러야 서버 화면에 보임 — 워커는 원래 그랬음
> 급할 때       스위치 없음 — 화면이 옛 규칙을 보이면 Reload Configs
>             Reload 뒤 서버 로그에 「[Reload] chain rules NOT forgotten」 줄이 있으면 서버가 옛 규칙을 들고 있음 — 서버 재기동
> ```

---

> ## 🔴 [09-29 낮] **체인 묶음이 실패하면 «쪼개지 않음» — 재시도 한도에서 통째 FAILED · 새 사건 0 — 마이그레이션 «없음» · 재기동 체인 워커**
>
> ```
> 무엇이 바뀌나  재시도 한도(max_group_attempts, 기본 1)에 닿은 묶음은 반으로 나뉘지 않고 통째로 FAILED. 새 사건을 안 만듦
>              그 묶음의 사건마다 error_log = failed_at · reason(원문 그대로) · rules · tables · rows · row
>              rules · tables = 사유 머리 [rules=.. target=..] 를 쓴 «실패한 자리»의 값. 그 자리가 모르면 null — 그룹이 깨운 규칙으로 안 채움
>              row = 오류 문장이 대는 행 id(최대 10). 안 대면 null — 행을 찾으려고 다시 돌리지 않음
>              맵퍼 실패의 사유 머리가 [rule=X target=Y] 에서 [rules=X target=Y] 로 — 쓰기 실패와 같은 모양
> 돌릴 명령     python server/scripts/outbox_triage.py --count      큐를 모양·원인별로 셈 (드라이런, 아무것도 안 바꿈)
> 확인          재기동 뒤 실패 줄이 묶음마다 «한 줄»:
>              Transaction <tx> permanently failed: <n> event(s), <m> row(s) -> FAILED [rules=<규칙> tables=<표> row=<...>]. 원인: <마지막 줄>
>              그 뒤 같은 tx 에 #half# 가 붙은 사건이 새로 생기지 않아야 함
>              rules=(unknown) 이면 실패한 자리가 규칙을 모름(예: 행이 안 읽혀 규칙이 돌기 전에 거절). row=not given by the error 는 로그 줄에만
> 뜻           한 행이 틀려도 그 묶음 전부(최대 1,000 행)가 FAILED — 의도된 답. 어느 행인지는 사유 원문(어드민 실패 목록의 traceback)
>             재시도 버튼 = 그 묶음을 한 번 다시 PENDING · 새 사건 0
>             이미 큐에 있던 #half# 사건도 한도에 닿으면 통째 FAILED 로 끝남(더 안 나뉨)
> 급할 때       어드민 체인 Pause -> 체인 워커 로그 「under tx 'chain_replay_<run>'」 에서 그 리플레이의 <run> 을 봄
>             -> python server/scripts/outbox_triage.py --set-aside --transactions replay_<run>,chain_replay_<run> --reason "<왜>"
>                (드라이런, 수만 봄) -> 같은 명령에 --apply -> Resume
>             ⚠️ 한 홉 더 번진 사건은 tx 앞에 chain_ 이 하나씩 더 붙음(chain_chain_replay_<run>) — 그 이름을 같이 적거나 --tables <표>
>                --rules <규칙> 은 «그 규칙이 깨울» 대기 사건을 고름 — 리플레이 것만이 아님
> ```

---

> ## 🔴 [09-29 오전 4] **조인의 on.columns 를 «키 + take» 와 집합으로 견줌 — 마이그레이션 «없음» · 재기동 체인 워커 · 서버**
>
> ```
> 무엇이 바뀌나  조인 선언에 on.columns 를 적었으면 그 칸 = 조인을 실제로 깨우는 칸(키 + take) 이어야 함 · 순서 무관
>              다른 칸이 섞이면 그 선언만 로드에서 빠짐 — 로그 [ChainRules] join_trigger_conflict: ... wakes on ['<키>', '<take>'] ...
>              키만 적은 옛 모양은 로드되고 한 줄로 이름 불림 — [ChainRules] '<선언>' writes on.columns [...] - the join key only; ...
> 확인          재기동 뒤 체인 워커 로그에 join_trigger_conflict 줄이 없어야 함. 있으면 그 줄이 보이는 칸 목록을 on.columns 에 그대로 적거나 on.columns 를 지움
> 뜻           on.columns 를 안 적는 것이 기본 — 조인이 스스로 적음. 적었다면 설명일 뿐 깨우는 칸을 바꾸지 않음
> 급할 때       스위치 없음 — 그 선언의 on.columns 를 지우면 됨
> ```

---

> ## 🔴 [09-29 오전 3] **엔터티 class 도 운영자의 낱말 — ["static","probe"] 저장 뒤 엔터티가 선언에서 빠지던 결함 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  엔터티 class 에 static · dynamic 밖의 낱말을 적어도 받음(술어와 같음). 빈 낱말은 「없음」으로 접힘
>              코드가 읽는 낱말은 여전히 엔터티 static 하나 — probe 같은 낱말은 행동 없음
> 확인          선언창에서 엔터티 class 에 낱말 하나를 더해 저장 -> GET /api/ledger/declaration 의 entities 에 그 엔터티가 그대로 있고
>              class 가 적은 목록 그대로. 서버 로그에 「[Ledger] entity|… is NOT read」 줄이 없어야 함
> 뜻           「Saved」 뒤 엔터티가 사라지면 그 엔터티의 선언이 문법에서 떨어진 것 — 서버 로그의 NOT read 줄에 칸 이름이 있음
>              (저장은 문법이 틀려도 파일에 씀 — 소유자 판정 「지금은 안읽히면 저장도 안하네」. 읽는 쪽이 그 선언만 뺌)
> 급할 때       스위치 없음 — 그 class 칸을 지우거나 낱말 하나로 되돌리면 오늘 그대로
> ```

---

> ## 🔴 [09-29 오전 2] **class = 낱말 하나 또는 목록 (엔터티 · 술어) · follow=class:<낱말> — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 선언 예      "vocabulary": {"measures@1": {..., "class": ["model"]}, "inspected@1": {..., "class": "context"}}
>             엔터티는 "class": "static" 도 ["static"] 도 됨. 낱말은 엔터티든 술어든 운영자가 지음 — 코드가 읽는 것은 엔터티 static 하나(위 [09-29 오전 3])
> 걷기         /api/ledger/subgraph?...&follow=class:model   -> 부류 model 을 든 술어 전부를 밟음
>             모르는 낱말 -> 422 · reason predicate_class_not_declared · unknown · declared(선언에 쓰인 낱말)
> 선언 라우트   /api/ledger/declaration 의 entities[].class · predicates[].class 가 «목록»(없으면 null)
>             전에는 엔터티 class 가 낱말 하나("static")였음 — 이 칸을 읽는 서버 밖 소비자가 있으면 모양이 바뀜
> 선언창       술어마다 class 칸(낱말 목록) — 적고 저장하면 파일에 목록 그대로, 다시 열면 그대로
>             ⚠️ 엔터티 class 를 낱말 하나로 적은 선언(이 박스 3 · 샘플 3)은 창에서 그 값을 «보여만» 주고 편집 칸을 안 냄
>                파일은 그대로 맞게 읽힘 — 창에서 고치려면 지우고 목록으로 다시 적음. 창이 낱말 하나를 목록으로 그리는 것은 클라 몫
> 뜻           class 는 운영자가 붙이는 낱말. 제품 동작이 부류 이름으로 갈리지 않음 — 엔터티 static 만 걷기가 읽음(전과 같음)
> 급할 때       스위치 없음 — class 칸을 지우면 오늘 그대로
> ```

---

> ## 🔴 [09-29 오전] **걷기 라우트의 화면 문장이 영어 — reason 낱말은 그대로 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  /api/ledger/subgraph · key-values · gaps · declaration 의 거절과 빈 응답 message 가 영어. 문장 모양은 「무엇 - 다음 행동」
>              detail.reason 과 나머지 칸(unknown · declared · state …)은 그대로
> 확인          curl -s "http://127.0.0.1:8080/api/ledger/subgraph?seed_type=wafer&seed_limit=1&collect=banana"
>              -> 422 · reason node_type_not_declared · message "Not a declared node type: banana - pick one from 'declared'"
> 뜻           message 는 사람이 읽는 문장이라 바뀜. 코드로 가르는 쪽은 reason 을 읽을 것 — reason 은 안 바뀜
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 아침] **trigger_columns 가 «막는 칸» — 적힌 칸 밖의 변경에 규칙이 안 돎 — 마이그레이션 «없음» · 재기동 체인 워커 · 서버**
>
> ```
> 재기동 «전»   pull 한 뒤 이 목록을 소유자께 — 적힌 칸 밖의 변경에 이제 안 도는 규칙들
>              conda run --no-capture-output -n assy_manager python -c "import sys; sys.path.insert(0,'server'); from chain import ingestion_worker as w; [print('WAKES', r.get('name'), w.wake_columns(r)) for r in w.load_chain_rules() if w.wake_columns(r)]"
>              WAKES 로 시작하는 줄 하나 = 규칙 하나와 그 규칙을 깨우는 칸. 넓히려면 그 규칙의 trigger_columns(통합 선언은 on.columns)에 칸을 더함
>              조인과 그 :target 짝은 스스로 적으므로 손댈 것 없음
> 무엇이 바뀌나  trigger_columns(∪ require)와 겹치지 않는 사건에 규칙이 안 돎
>              칸 목록이 없는 사건(행 하나씩 쓴 변경 · 옛 사건 · 리플레이)에는 오늘처럼 돎
>              조인 값 표 쪽의 깨우는 칸에 take 칸이 더해짐(전에는 키만) — 값만 바뀌어도 조인이 돎
> 재기동 뒤      로드 때 규칙마다 한 줄   [ChainRules] <규칙> wakes only on: [..]
>              안 돈 묶음마다 한 줄     [Chain] rule <규칙> skipped: none of [..] changed   <- 이제 참: 그 규칙은 실제로 안 돎
> 뜻           값이 안 옮겨지고 skipped 줄이 찍히면 — 그 값을 바꾸는 칸이 깨우는 칸에 없음. 그 칸을 trigger_columns 에 더함
> 급할 때       스위치 없음 — 그 규칙의 trigger_columns 를 지우면 표의 어떤 변경에도 다시 돎
> ```

---

> ## 🔴 [09-28 밤 3] **require 가 조인 양쪽 · 전부 막힌 묶음 · 보강 백필까지 — 마이그레이션 «없음» · 재기동 서버 · 체인 워커**
>
> ```
> 무엇이 바뀌나  조인: 값 표 행의 require 칸이 비면 그 행은 답이 아님 — :target 짝(채워지는 표가 바뀔 때)도 그 값을 안 옮김
>              묶음의 행이 전부 막히면 맵퍼를 부르지 않음. 처음부터 행이 없던 묶음은 오늘처럼 부름
>              보강 백필(어드민 소급 · scripts/backfill_enrichment.py)도 같은 판정으로 거름
> 로그 줄       [Chain] <규칙 또는 선언 이름>: <N> row(s) not handed over - required column(s) empty: <칸>=<N>  — 백필도 같은 줄
> 뜻           아래 [밤 2] 절의 뜻 그대로. 그 절의 「조인은 값 표 쪽만」 줄은 이 착지로 지움
> 조인 오타     손으로 고친 파일에서 on.require 이름이 틀리면 값 표 쪽 규칙은 로드 거절,
>              :target 짝은 돌 때 「require column '<칸>' does not exist on '<표>'」로 거절하고 아무것도 안 씀
> 급할 때       스위치 없음 — 그 선언의 require 칸을 지우면 오늘 그대로
> ```

---

> ## 🔴 [09-28 밤 2] **규칙의 require — 이 칸이 다 찬 트리거 행만 규칙에 넘어감 — 마이그레이션 «없음» · 재기동 서버 · 체인 워커**
>
> ```
> 예시 선언   평평  {"name": "<복사 규칙>", "trigger_table": "dt_log", "target_table": "<정답맵 표>",
>                  "require": ["<키 칸>", "<키 칸>"], "allow_chain_trigger": true, ...}
>            통합  "on": {"table": "dt_log", "require": ["<키 칸>", "<키 칸>"]}
>            allow_chain_trigger 가 있어야 함 — 키를 채우는 것이 inventory 조인(체인 쓰기)이라 이 칸이 없으면 채워져도 안 깨어남
> 로그 줄     [Chain] <규칙 이름>: <N> row(s) not handed over - required column(s) empty: <칸>=<N>, <칸>=<N>
> 뜻         그 행들은 맵퍼에 안 넘어감. 묶음마다 한 줄, 막힌 행이 없으면 줄 없음
>            나중에 그 칸이 채워지는 쓰기에 다시 깨어나 넘어감
>            같은 칸 이름이 계속 찍히면 그 칸을 «채우는 쪽»이 안 채우고 있는 것 — 조인·원천을 볼 것
>            이미 넘어가 쓴 행은 칸이 다시 비어도 안 거둠
> 로드 거절   [ChainRules] <규칙> refused (1): unknown_require_column ... requires ['<칸>'] that '<표>' does not have ...
>            그 규칙 하나만 빠짐(파일 전체 아님). 저장 화면도 같은 문장으로 거절
> 급할 때     스위치 없음 — 그 규칙의 require 칸을 지우면 오늘 그대로
> ```

---

> ## 🔴 [09-28 밤 1] **선언은 자기가 쓴 것에 안 깨어남 — allow_chain_trigger 는 «다른» 선언이 쓴 것만 받음 — 마이그레이션 «없음» · 재기동 체인 워커 · 스케줄러**
>
> ```
> 무엇이 바뀌나  체인이 쓴 사건에 쓴 선언 이름이 실림(payload 의 "written_by")
>              그 선언의 규칙(조인의 원천 규칙 · :target 짝 · 자기 트리거 표에 쓰는 맵퍼)은 그 사건에 안 깨어남 — allow_chain_trigger 가 있어도
> 뜻           오늘 사건의 조인 선언에 allow_chain_trigger 를 다시 적어도 자기 순환은 안 남
>              다른 선언이 쓴 것엔 그대로 깨어남(옵트인) · 같은 쓰기에 다른 선언이 섞였으면 깨어남(그쪽 변화 때문)
>              decide 의 자동 확정 반쪽은 dedup 반쪽의 쓰기에 그대로 깨어남(둘은 다른 규칙)
> 재기동 뒤     재기동 «전»에 쌓인 사건은 "written_by" 가 없어 옛 규칙대로 읽힘 — 대기열이 비면 끝
>              확인: 조인이 쓴 뒤 database_outbox 의 그 사건 payload 에 "written_by": ["<선언 이름>"]
> 급할 때       스위치 없음. 되돌리기는 git revert 뒤 둘 재기동 — 되돌리면 allow_chain_trigger 가 적힌 조인은 다시 자기에 깨어나니 그 칸을 지운 채로
> ```

---

> ## [09-27 아침 6] **예/아니오 칸 셋 더 — 파일명 규칙 required · finding kind active · bypass_proxy — 동작 같음, 문장만 하나로 · 재기동 워처 · 스케줄러**
>
> ```
> 무엇이 바뀌나  세 칸 다 오늘도 true/false 아니면 거절(규칙 · 종류) 또는 기본 true(bypass_proxy) — 로그 문장만
>              「<칸> must be true or false, got <값> - write true or false」로 (bypass_proxy 의 한국어 경고 줄은 사라짐)
> 재기동 뒤     scheduler 로그 "auto_update_control.json: bypass_proxy must be true or false, got … - falling back to true" — 뜨면 그 칸을 true/false 로
> 되돌리기      git revert
> ```

---

> ## [09-27 아침 5] **스크립트 리플레이는 연쇄를 청하지 못함 — chain_replay_cli.py 의 --cascade 없음 — 마이그레이션 «없음» · 재기동 없음(CLI) · API(소급 탭 안내 줄)**
>
> ```
> 무엇이 바뀌나  python server/scripts/chain_replay_cli.py replay <규칙> ... --cascade  ->  "unrecognized arguments: --cascade" 로 거절(아무것도 안 돎)
>              --cascade 없이 돌리면 오늘과 같음 — 리플레이의 쓰기는 하류 규칙을 안 깨움
> 연쇄가 필요하면  그리드에서 행을 찍어 리플레이(그 클릭만 연쇄를 청함 — 옵트인 규칙만)
> 되돌리기      git revert
> ```

---

> ## [09-27 아침 4] **페인트 잠금 기본 문장 영어 — 마이그레이션 «없음» · 재기동 API**
>
> ```
> 무엇이 바뀌나  map_overlay_config.json 의 paint_lock 에 message 를 안 적은 표 -> 화면 문장이 "This cell holds a locked value - it cannot be painted"
> 운영 설정     paint_lock 의 message 칸에 문장을 적어 두었으면 그건 운영자 값 — 그대로 그려짐. 바꾸려면 그 칸을 고침(저장하면 다음 요청부터)
>              찾기: findstr /n "message" server\config\map_overlay_config.json
> 되돌리기      git revert 뒤 API 재기동
> ```

---

> ## 🔴 [09-27 아침 3] **표에 새 칸을 붙이는 스키마 동기화 — 20 s 넘게 막히면 포기하고 프로세스는 계속 — 마이그레이션 «없음» · 재기동 API · 워처 · 체인**
>
> ```
> 무엇이 바뀌나  선언에 새 칸이 생겨 기동 · 설정 저장 때 ALTER TABLE ... ADD COLUMN 을 걸 때, 그 표를 잡은 세션이 있으면 20 s 뒤 포기
>              (전: 끝없이 기다림 — 기동이 거기서 멈추고, 그 표의 읽기 · 쓰기가 ALTER 뒤에 줄 섬)
> 재기동 뒤     각 프로세스 로그 "[Schema Sync] column '<칸>' was not added to '<표>' - another session held the table past 20s. …"
> 뜻           그 표는 칸이 붙을 때까지 읽기 · 쓰기가 실패(「column "<칸>" does not exist」) · 기동과 다른 표는 돎
> 뜨면         conda run --no-capture-output -n assy_manager python server/scripts/diagnose_db_health.py — 그 표를 잡은 pid 확인
>              그 트랜잭션을 끝낸 뒤 설정 저장(리로드가 다시 붙임) 또는 재기동
> 같이 바뀜     원장 파티션 DDL 의 「락을 못 잡음」 판정이 같은 함수 — statement timeout 은 더 이상 「락」이라 말하지 않음
> 급할 때       스위치 없음. 되돌리기는 git revert 뒤 셋 재기동
> ```

---

> ## 🔴 [09-27 아침 2] **예/아니오 칸은 true/false 만 — 체인 규칙 · 수집기 · 원장 묶음 · 표기 · 맵 · 자동 확정 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 재기동 «전»   운영 설정에 true/false 아닌 예/아니오 값이 있나 — 둘 다 저장소 루트에서
>              conda run --no-capture-output -n assy_manager python -c "import sys; sys.path.insert(0,'server'); import chain_bindings; from chain import ingestion_worker as w; rules=w.read_rules_document()['rules']; bad=[(r.get('name'), f) for r in rules for f in chain_bindings.flag_refusals(r)]; [print(*b) for b in bad]; print('chain rules checked:', len(rules), '| not true/false:', len(bad))"
>              conda run --no-capture-output -n assy_manager python -c "import sys; sys.path.insert(0,'server'); import map_overlay; from maps import preset_routing as p; c=map_overlay.load_overlay_config(); t=list(c.get('preset_routing') or {}); [p.resolve_routing_config(c,x) for x in t]; l=list(c.get('paint_lock') or {}); [map_overlay.get_paint_rules(c,x) for x in l]; print('map routing tables checked:', len(t), '| paint lock entries checked:', len(l))"
>              뜻: 줄마다 「<규칙> <칸> must be true or false, got <값> - write true or false」 · 맵은 「… ignored: …」 경고 줄
>              뜨면 그 칸을 true 또는 false 로 고친 뒤 재기동. 안 고치면 — 체인 규칙은 «안 섬»(오늘 1 · "true" 로 돌던 규칙도 멈춤),
>              맵 라우팅 · 페인트 잠금 항목은 «안 씀»(오늘 0 · "false" 가 켜짐으로 읽히던 것)
>              끝 줄의 checked 수가 0 이면 파일을 못 읽은 것 — 경로부터
> 바뀌는 것     체인 규칙: 예/아니오 칸(enabled · is_batch · allow_* · idempotent · key.unique · decide 의 auto_confirm · alignment)이
>              true/false 아니면 로드 · 저장에서 그 선언이 안 섬 — 전에는 "false" 글자가 켜짐(allow_retraction 이면 지우기가 켜짐)
>              맵: 라우팅 · 페인트 잠금의 enabled 도 같음 — 그 항목을 안 쓰고 경고 한 줄
>              나머지(수집기 · 원장 묶음 · 표기 · 자동 확정 · map_push_ok · 수집 설정 여섯 · std_parse)는 전에도 거절/기본값 — «문장»만 하나로
> 재기동 뒤     chain_worker.log "[ChainRules] <규칙>: <칸> must be true or false, got …" — 그런 규칙마다 한 줄
> 급할 때       스위치 없음. 그 칸을 true/false 로 고치면 다음 리로드부터 섬. 되돌리기는 git revert 뒤 넷 재기동
> ```

---

> ## 🔴 [09-27 아침 1] **치워 둔 사건 다시 돌리기 — 규칙마다 한 번 · 연쇄 없음 — 마이그레이션 «없음» · 재기동 API · 스케줄러**
>
> ```
> 무엇이 바뀌나  소급 탭 "Run set-aside events again" · outbox_triage.py --rerun-set-aside · --replay-cancelled
>              치운 사건이 가리키던 행을 그 표의 규칙마다 «한 번» 리플레이 — 그 쓰기는 하류 규칙을 «안 깨움»(옵트인이어도)
>              (전에는 체인처럼 연쇄 — 소유자 09-27 「큰 소급 치워둔거니 한번만」)
> 그대로        그리드에서 행을 찍어 리플레이하면 오늘처럼 연쇄(옵트인 규칙만)
> 확인          소급 탭 그 연산의 안내 줄 "It replays the rows those events named, each rule once - nothing downstream runs; …"
>              옛 문장 "… cascades like the chain would have" 가 보이면 API 가 옛 코드 — 재기동
> 뜻           다시 돌린 뒤 하류 표가 옛 값이면 정상 — 하류가 필요하면 하류 규칙을 소급 탭 "Replay chain rules over old data (R1)" 로 따로, 또는 그리드에서 행 리플레이
> 급할 때       스위치 없음. 되돌리기는 git revert 뒤 API · 스케줄러 재기동
> ```

---

> ## 🔴 [09-27 새벽 1] **@mapper 규칙도 지운다 — allow_retraction(잡마다) · allow_replace_map(맵마다) — 마이그레이션 «없음» · 재기동 체인 워커 · API**
>
> ```
> 무엇이 바뀌나  @mapper 맵퍼를 쓰는 규칙에 allow_retraction / allow_replace_map 이 적혀 있으면 착지 «뒤 첫 실행부터» 지움
>              (전에는 그 칸이 아무 일도 안 했음 — 덮어쓰기만)
> 재기동 뒤     chain_worker.log "[ChainRules] <규칙>: @mapper removes by job - …" 또는 "… map by map - …" — 그런 규칙마다 한 줄
>              거절 "[ChainRules] <규칙> refused …: sdk_two_removals · sdk_removal_needs_batch · sdk_map_key_not_on_trigger · sdk_job_column"
>              뜻: 그 규칙은 안 돎 — 문장이 다음 행동을 적음("is_batch": true 등)
> 절반 가드     이번에 한 행도 안 낸 잡이 가진 행이 20 이상이면 "[DtMapRetraction] … DECLINED … Next, to remove them on purpose: …"
>              뜻: 아무것도 안 지움. 정말 지우려면 그 줄이 적은 대로 그리드에서 그 잡의 행을 지움
> replace_map   맵을 통째로 — 사람이 고친 값(CellOverwrite)도 같이 지움(소유자 판정). retract 는 살림
> 급할 때       그 규칙의 allow_* 칸을 지우고 설정 저장(리로드) — 덮어쓰기만으로 돌아감
> 되돌리기      git revert 뒤 체인 워커 · API 재기동
> ```

---

> ## 🔴 [09-26 밤 8] **넓은 조인은 쪽으로 — 1,000 행씩 답하고 · 쓰고 · 커밋 · 왼쪽 조회 인덱스 · 두 칸 키가 만 개를 넘어도 섬 — 마이그레이션 «없음» · 재기동 체인 워커**
>
> ```
> 재기동 뒤     chain_worker.log "[Join] 조회 인덱스 ix_vjoin_<표>_<칸>… 를 세웠습니다 (<초> s)" — 조인마다 처음 한 번(이미 있으면 줄 없음)
>              미뤄지면 "… 세우지 못했습니다 — … 다음 기동/리로드로 미룹니다. 그동안 이 조인은 왼쪽 행을 인덱스 없이 고릅니다(느림)"
> 조인 줄       "[Chain] <규칙> -> <표>: page <N>, <M> row(s)" — 둘째 쪽부터 쪽마다 한 줄
>              [ChainRule] 줄의 rows_out 은 «모든 쪽»의 행 수 — 조인이 첫 부름에 한 번 읽은 것으로 셈
> 읽는 때       조인은 답에 필요한 것(왼쪽 키 · 맞는 오른쪽 행)을 첫 부름에 «한 번» 읽음 — 같은 묶음의 앞 규칙이 쓴 값은
>              이 조인이 안 봄(한 번에 쓰던 때와 같음)
> 뜻           쪽마다 커밋 — 도는 동안 왼쪽 표가 반만 붙은 채 보일 수 있음
>              중간에 실패하면 앞 쪽은 남고 그 묶음은 FAILED(시도 1) — 리플레이가 같은 값은 헛쓰기로 지나며 나머지를 채움
> 급할 때       그 조인만 끄기: chain_rules.json 의 그 선언에 enabled: false + 설정 저장(리로드) · 나중에 리플레이
> 되돌리기      git revert 뒤 체인 워커 재기동. 남은 ix_vjoin_* 인덱스는 되돌린 코드가 모름 — 필요 없으면 손으로 DROP INDEX CONCURRENTLY
> ```

---

> ## 🔴 [09-26 밤 7] **기동 인덱스 작업은 첫 박동 «뒤», 체인 루프 «옆»에서, 20 s 시한 — 마이그레이션 «없음» · 재기동 체인 워커**
>
> ```
> 재기동 뒤      체인 워커가 첫 박동부터 냄 — 선언된 유일 인덱스 세우기 · 걷기는 그 «뒤» 옆 작업(루프는 안 기다림)
> 미뤄진 줄      chain_worker.log
>   "[Join:<규칙>] 유일 인덱스를 세우지 못했습니다 — 다른 세션이 표 <표> 를 20s 넘게 잡고 있습니다. 다음 기동/리로드로 미룹니다 ..."
>       뜻: 그동안 그 조인은 행 단위 그물만(오른쪽 행이 둘인 왼쪽 행은 거절). 급하지 않음 — 다음 설정 저장이나 재기동에 다시
>   "[Join] 인덱스 <이름> 를 걷지 못했습니다 — ... 그동안 이 인덱스가 그 표의 쓰기에 23505 를 낼 수 있습니다(S-248)"
>       뜻: 그 표 쓰기가 23505 로 실패하면 이것이 이유 — diagnose_db_health.py §3 로 표를 잡은 pid 를 찾아 끝낸 뒤 설정 저장(리로드)
> 리로드         설정 저장(리로드)마다 인덱스 작업이 다시 돎 — 전에는 기동 때만 돌았음(주석은 「리로드마다」라 적혀 있었음)
> foreign_beat   이 착지 뒤엔 인덱스 작업 때문에는 안 생김(첫 박동이 먼저). 그래도 보이면 첫 박동 앞에 남은 것:
>                import 때 스키마 동기화(run_chain_worker.py · 설정에 새 컬럼이 있을 때 ALTER TABLE · 시한 없음) — 소유자 물음으로 올라가 있음
>                -> 10-10 5b-2: 기동 단계가 됨(첫 박동 뒤, starting: sync_dynamic_tables_schema). 시한은 09-27 부터 있음 — ALTER 마다 DDL_LOCK_TIMEOUT(3c26854c3 · a696ee4e8)
> 시한 값        server/db_safety.py 의 DDL_LOCK_TIMEOUT = "20s" — 원장 파티션 DDL 과 같은 상수 하나
> 스위치         없음. 되돌리기는 git revert 뒤 체인 워커 재기동
> ```

---

> ## 🔴 [09-26 밤 6] **표기 3 단계 — 선언 전에 저장된 값을 선언한 철자로(제자리) — 마이그레이션 «없음» · 재기동 API**
>
> ```
> 언제          notation_rules.json 에 "write": true 칸을 선언한 «그날». 선언이 없으면 할 일 없음
> 순서          ① 소급 탭 "Fold stored values into the declared spelling" — table · 드라이런(Count) 먼저
>              ② 같은 표에 "Fold file layers that repeat a newer one" — 철자만 달랐던 파일 층이 이제 같은 값
>              ③ python server/scripts/tune_layer_tables.py --table cell_sources --vacuum
> 드라이런 뜻    "... row(s) would take another row's key and are skipped" — 두 옛 철자가 한 키가 됨. 병합 안 함 — 별칭 행이나 규칙을 고치고 다시
>              "... value(s) change again on a second fold - the run stops there" — 선언부터 고침. 실행은 그 페이지 앞에서 멈춤
> 사실 둘        맵 키 칸(map_key_columns)을 write 로 선언하면 소급을 같은 날 — 첫 replace_map 푸시가 옛 철자 행의 뺀 칸을 못 지움
>              별칭 표: python server/scripts/install_product_tables.py --apply -> POST /admin/reload-configs -> 선언
> 되돌리기       불가 — 저장돼 있던 철자는 칸마다 이력 줄(notation_backfill)의 옛 값. 코드는 git log --oneline --grep "feat(notation): notation stage three" 를 revert
> ```

---

> ## 🔴 [09-26 밤 6] **문 가르기 복기 넷 — 켜짐 판정 하나 · 재시도 집계 · 파일 마무리 단계 · 리플레이 기록 전 판정 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 돌릴 것      없음. 재기동만
> 재기동 뒤     chain_worker.log  "[ChainRules] set(N): ..." — 규칙 옆 " OFF" 는 enabled 가 false · 0 · null 인 규칙
>              뜻: 0·null 은 전에도 워커가 안 깨웠고 명단도 OFF 였다. 이제 파생 표 집계도 같은 답(도는 규칙은 하나도 안 바뀜)
>              통합 선언에 enabled 0·null 을 적었으면 이제 «규칙을 안 세움» + 노트 "enabled=false - no rule stands for it"
> 워처 로그     "[BK Conflict Recovered]" 다음 그 파일의 FILE 줄 — side-table rows · row build 칸 수가 커밋된 시도 것만
>              뜻: 되감긴 시도의 초는 그 쓰기 단계의 «이름 없는 나머지»로 감. 나머지가 굵으면 위 경고 줄이 이유
> 헬스         마지막 청크 뒤에 멈추면 워처 박동 단계가 "finish" (전엔 마지막 청크의 commit 으로 읽힘)
> 소급 탭       chain_replay 에 멱등 아닌 규칙 · 등록 안 된 트리거 표 -> 요청 자리에서 거절, 실행 행이 안 생김
> 스위치        없음. 되돌리기는 git revert 뒤 재기동
> ```

---

> ## 🔴 [09-26 밤 5] **표기 2 단계 — "write": true 칸은 쓸 때 접혀 저장 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 무엇이 바뀌나  server\config\notation_rules.json 에서 "write": true 인 칸만 — 파일 · 격자 · 체인 쓰기가 접힌 값을 저장
>              그 파일이 없거나 write 칸이 없으면 아무것도 안 바뀜
>              키 칸을 write 로 선언해도 새 행 없음 — 옛 철자로 저장된 행을 찾아 그 행의 키를 접힌 키로 바꿈
> 이력          접기가 철자를 바꾸고 그 칸이 쓰일 때 칸마다 한 줄(old = 들어온 철자, new = 저장값). 같은 철자를 다시 보낸 파일은 줄 없음
> 확인          watcher.log "[Ingest] <표> FILE <파일>: ... · time rule left as written: no matching format N, time zone written M"
>              time 칸이 그대로 둔 값의 수 — 0 이면 이 칸이 안 나옴. N 이 크면 그 칸의 "from" 모양을 더 적음
>              GET /admin/config/notation/preview?table=<표>&column=<칸> 의 folds_again 이 0 이 아니면 선언부터 고침(소급이 거기서 멈춤)
> 별칭 표        notation_alias 라이브 설치는 총괄이 소유자께(1 단계 항목의 install_product_tables.py)
> 스위치        그 칸의 "write": true 를 지우면 5 초 안에 다음 쓰기부터 안 접음. 이미 접혀 저장된 값은 그대로
> 되돌리기       git log --oneline --grep "feat(notation): notation stage two" 의 커밋을 git revert 뒤 네 프로세스 재기동
> ```

---

> ## 🔴 [09-26 밤 4] **비상 정지 — 체인 일시정지 · 대기열 치워 두기 · 다시 돌리기 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 사고 때 순서   ① Pause          어드민 POST /admin/chain/pause {reason}  ·  또는 conda run --no-capture-output -n assy_manager python server/scripts/chain_pause_cli.py pause --reason "왜"
>                                 새 묶음을 안 잡고 · 도는 묶음은 다음 단계에서 되감고 · 도는 쿼리는 그 자리에서 끊음. 대기열은 그대로(잃는 것 0 · 재시도 횟수 안 올림)
>               ② 치워 두기       소급 탭 "Set queued chain events aside" — 표 · 규칙 · 트랜잭션 중 하나 이상 + 사유. 드라이런이 사건 수 · 행 수를 먼저 보여 줌
>                                 CLI: python server/scripts/outbox_triage.py --set-aside --tables 표 --reason "왜" (--apply 로 실제로)
>               ③ Resume          POST /admin/chain/resume  ·  chain_pause_cli.py resume — 남은 대기열이 다시 흐름
>               ④ 나중에           소급 탭 "Run set-aside events again"(같은 범위) — 치운 사건이 가리키던 행을 리플레이, 규칙마다 한 번 · 연쇄 없음(09-27 아침 1 절)
>                                 CLI: outbox_triage.py --rerun-set-aside --tables 표 --apply
> 확인          GET /admin/chain/pause 가 요청 상태 · /health 의 chain 이 paused(degraded) 면 워커가 멈춤을 지킴
>               chain_worker.log "[Chain] paused - tx '...' was rewound at a stage boundary" — 되감긴 묶음마다
> 재기동        멈춤은 재기동해도 유지 — 풀려면 Resume. 상태 파일: server\config\chain_control.json
> 뜻           치운 사건은 지워지지 않음 — cancelled_by = operator · cancel_reason 이 사건에 남음
> 스위치        이것 자체가 스위치. 되돌리기는 git revert 뒤 재기동 — 남은 상태 파일은 읽는 코드가 없어 아무 일도 안 함
> ```

---

> ## 🔴 [09-26 밤 3] **쓰기의 경로(channel) — 자동 확정이 옵트인을 지나고 · 소급의 쓰기는 체인을 안 깨움 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 무엇이 바뀌나   outbox 사건에 경로 칸 — chain · api · file · retroactive. 층 이름(source_name)은 그대로
>               chain        체인이 쓴 것(자동 확정 포함) — 옵트인한 규칙만 깨움 · 깊이 상한이 셈
>               api · file   사람 · 다른 클라이언트 · 파일 적재 — 오늘처럼 모든 규칙을 깨움
>               retroactive  소급 탭 · CLI 의 모든 소급 실행이 쓴 것 — 옵트인이어도 «아무 규칙도» 안 깨움. 하류는 하류를 따로 소급
>               그리드 클릭 리플레이만 연쇄(cascade) — 옵트인 규칙만 깨움. 클라는 d3659ec09 부터 cascade: true 를 보냄(빌드 포함 — 브라우저 새로고침 뒤)
> 재기동 뒤      server\config\ingestion_settings.json 의 "enrichment_auto_confirm_enabled" 를 true 로 되돌려도 됨 — 자동 확정 쓰기가 이제 옵트인을 지남
> 확인          chain 박동 note 에 "N event(s) read by source name (no channel)" — 착지 전에 쌓인 체인 사건을 옛 방식(source_name)으로 읽은 수
>               대기열이 비면 더 안 늘어남. 늘어나면 경로를 안 세우는 체인 쓰기가 남아 있다는 뜻 — 보고
> 소급 폼        모든 연산에 "Downstream chain rules are not triggered by a retroactive run - run them too if they read what this changed"
>               수집기 날짜별 소급만 "The files it collects are ingested as usual, and the chain runs on them"
> 스위치        없음. 되돌리기는 git revert 뒤 네 프로세스 재기동(경로 칸이 없는 사건은 옛 방식으로 읽히므로 섞여도 안전)
> ```

---

> ## 🔴 [09-26 밤 3] **같은 값의 파일 층 — 쓰기에서 안 쌓고, 쌓인 것은 소급 한 번 — 마이그레이션 «없음» · 재기동 워처 · 체인 워커 · API**
>
> ```
> 보이는 것   헤비 레인 청크 줄 · 파일 줄의 INSIDE THE WRITE — cell sources <초> / N rows · folded layers <초> / N rows
>            값이 그대로인 행을 다시 가져온 파일이면 cell sources 0 rows · folded layers 0 rows = 층이 안 쌓임
>            값이 바뀐 파일이면 cell sources 는 바뀐 칸 수 · folded layers 는 그 값을 말했던 옛 파일 층 수
> 쌓인 것     드라이런: 어드민 Retroactive -> "Fold file layers that repeat a newer one" -> table -> Count
>            문장 "layers N -> M, the deepest cell A -> B" — N-M 이 지울 수
>            (이 박스 1,000 행 x 5 칸 x 9 겹 픽스처: 46,000 -> 6,000 · 9 -> 1 · 1.2 s — 운영 규모는 안 쟀음)
>            실행: 같은 화면 Run  또는  python -c "from admin import retroactive; retroactive.run_here('fold_file_layers', {'table': '<표>'})"
>            끝나면: python server/scripts/tune_layer_tables.py --table cell_sources --vacuum
> 뜻         되돌릴 수 없음 — 사라지는 것은 「같은 값을 말한 옛 파일 이름」 기록뿐. 칸 값 · 이력 · 이기는 층은 그대로
> 되돌리기    코드: git log --oneline -1 --grep "file layer that repeats" 의 커밋을 git revert 뒤 워처 · 체인 워커 · API 재기동. 지운 층은 안 돌아옴
> ```

---

> ## 🔴 [09-26 밤 2] **지금 운영 — 자동 확정이 옵트인을 건너뛰어 번지는 것을 멈추는 스위치 (코드 착지 전 · 재기동 «없음»)**
>
> ```
> 끄기        server\config\ingestion_settings.json 에 "enrichment_auto_confirm_enabled": false
>             파일을 매 작업마다 다시 읽음 — 재기동 없이 다음 묶음부터 자동 확정이 멈춤
> 뜻          판정 규칙이 값을 «자동으로» 채우는 쓰기만 멈춤. 판정 목록(대기열)은 그대로 쌓이고 사람이 확정하는 길은 그대로
> 확인        어드민 설정 해석 화면(/admin/config/resolve 가 답하는 것)에 enrichment_auto_confirm_enabled 가 false 로 나오는지
>             ⚠️ 꺼져 있을 때 체인 로그에 따로 찍히는 줄은 없음
> 다시 켜기    ⓪(자동 확정 쓰기가 체인 경로로 읽히게 하는 착지) 뒤에 true 로 — 그 착지의 RUN.md 절이 알림
> ```

---

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
> foreign_beat 박동 파일의 pid 가 감독자가 띄운 pid 가 아님 — 새 워커가 첫 박동 전에 막혀 있고(기동 인덱스 작업이 남은 쿼리 뒤에서 기다림) 파일엔 옛 pid 가 남은 것 — 10-10 뒤로 기동 보정 · 스키마 동기화는 starting 으로 읽힌다(10-10 절)
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
> 뜻         저장은 2 단계([09-26 밤 5] 항목)부터 — 이 단계의 몫은 선언 점검과 미리 보기
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
> 일부 버림   SUCCESS 그대로 + 기록에 Next: declare the undeclared columns in table_config.json. Not written: undeclared_column <칸>=<값 수> over M row(s). (10-01 d4a949a8c ③)
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
