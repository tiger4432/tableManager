# 구현자 B 보고

> **[구현자 B -> 총괄] 10-13 큐 1 — 소급 쪽 고리 전수 (5ad030347 + 2e8c6ac9c). 짓기 전 표, 물음 둘**

```
센 것     server/ 의 함수 중 «쪽을 넘기는» 것 — AST 술어: keyset_scan.PageSize 를 짓거나 · keyset_scan.iter_pages /
          keyset_scan.pages 를 부르거나 · while 안에서 .limit( 을 부르는 함수 (tests/ 제외)
          -> 23 함수 (카나리아 remove_shell_rows · fold_units · fold_written_notation 셋 다 잡힘)
          소급 작업 = admin/retroactive.OPERATIONS 의 열쇠 18 (AST 로 run 좌석까지 짝지음)
뺀 것     scripts/migrate_jsonb_to_rdb.main(일회 이주) · value_suggest._numeric_values(소급 아님) ·
          join_into._page · fold_unit._page(살아 있는 제안의 고정 쪽 — 표를 안 읽음) · keyset_scan.iter_pages(좌석 자신)
수의 출처  «응용 실측» 칸은 응용 세션의 판(test_zz_qa_census_pg.py, main 1e23bc216, 스크래치 스키마, 100만, 작업마다 45 초 상한)
          JSON 에서 내가 읽은 것이다. 내가 잰 수가 아니다. 박스 수다
```

| 작업 → 쪽 고리 | 쪽 고르기 | 받는 인덱스 | 쪽마다 통째 | 첫 줄 전 통째 | 응용 실측 100만 |
|---|---|---|---|---|---|
| chain_replay · rerun_set_aside → replay_rule | iter_pages, row_id 이어 받기 | pkey | 아니오 | 아니오 | 0.01 s/1,000 · Seq 0 |
| withdraw → withdraw_source.read | cell_sources DISTINCT row_id 이어 받기 (표 · 소스로 거름) | 안 쟀다 | 안 쟀다 | **첫 쪽 9.9 s** | 원인 안 쟀다 — 같은 성질 후보 |
| set_aside → _scope_pages | outbox id 이어 받기, 규칙은 쪽 안에서 판정 | pkey | 아니오 | 아니오 | Index Scan pkey |
| resolve → recompute_display_values | iter_pages | pkey · 층은 유일 인덱스 | 아니오 | 아니오 | Seq 0 |
| **① fold_written_notation** | iter_pages + 쪽의 cell_sources `row_id = ANY(쪽 id)` | **큰 쪽에서 Parallel Seq Scan** | **예** — cell_sources 30 번 · 1억 3천만 행 | count(*) 1.84 s (qa_nf 1.98 s) | 38.8 s / 45.9 s |
| fold_file_layers | iter_pages + _load_cell_state | pkey · 유일 인덱스 | 아니오 | 아니오 | Seq 0 |
| **fold_duplicate_rows** | 진 행 목록을 메모리에서 쪽으로 | 없음(창 함수가 표 전부) | 아니오 | **예** — 창 함수 통과 다섯(셈 넷 + 진 행) | 첫 줄 10.58 s (hold) · 8.89 s (fold) |
| **③ fold_units** | 그룹 몇 개씩 `group IN (…)` | **없음** | **예** — fu_inventory 176 번 · 1,200 만 | 예 — 순위 셈 · unit_ids · distinct 그룹 | 첫 줄 2.86 s |
| **② remove_shell_rows** | 손으로 짠 while: 빈 칸 판정 + row_id 이어 받기 | **Parallel Seq Scan + Sort** | **예** — 120 번 · 4,154 만 | 아니오 | 17.3 s |
| fold_withdrawal_events | 손으로 짠 while: payload 판정 + id 이어 받기 | pkey 를 걸러 읽음 | 첫 쪽이 안 맞는 대기 이벤트를 다 읽음 | **예**(첫 쪽) | 첫 줄 3.36 s — ② 와 같은 모양 |
| ledger_backfill → _run_via_events | 행 색인에 없는 행, anti join 이어 받기 | pkey · row_ref | 아니오 | count(*) 0.47 s (총계 한 번) | Merge Anti Join |
| ledger_catch_up · ledger_rescope | 쪽 키 이어 받기 · 묵은 원자 스트림 | 안 쟀다 | 안 쟀다 | 안 쟀다 | 응용 판에 없음 |
| enrichment_backfill → run_backfill | iter_pages(원천) + 쪽마다 파생 표 키 확인 | 파생 표 Seq Scan | 쪽마다 파생 표 통째(130 번 · 197 만, 쓴 행 3.15 만) | 아니오 | 원인 안 쟀다(자라는 표의 계획 vs 인덱스) |
| enrichment_confirm → derived_pages | iter_pages, 큐 판정이 WHERE 안 | 안 쟀다 | 안 쟀다 | 안 쟀다 | 응용 판에서 오류로 0 행 — ② 와 같은 모양 |
| rule_rows · collector_backfill | 한 쪽 · 하루 창 | — | — | — | 표 쪽 고리 아님 |

```
같은 성질(«쪽이 고르는 행 ≠ 쪽이 읽는 행»)로 묶는 것
   ② remove_shell_rows · fold_withdrawal_events · (derived_pages)  판정이 WHERE 안 -> «다음 n 개 맞는 행»을 찾느라 멀리 읽음
      -> 쪽은 키 순서 n 행(iter_pages 한 자리), 판정은 그 쪽 안에서. 짓는다
   ① 표기 cell_sources  쪽 id 를 ANY 로 넘김 -> 큰 쪽에서 계획이 통째로 뒤집힘(가설 — 지금 잰다)
   withdraw_source 첫 쪽 9.9 s · enrichment_backfill 파생 표  원인 안 쟀다. 재고 나서 같은 성질이면 같이
요청 길의 셈  _count_remove_shell_rows · _count_fold_units 는 미리보기에서 dry run 을 끝까지 돈다(until 없음).
   «5 초에 끊고 at least» 와 다른 성질이라 이번에 안 짓는다 — 말만 한다
```

**물음 1 — fold_duplicate_rows 의 첫 줄 10.58 s.** 키가 «작업 인자»(운영자가 폼에 적는 칸)라 선언이 아니다. 큐 2 기제는 선언에서 인덱스를 뽑으니 이 키에는 안 닿는다. 키마다 한 행 남기기는 «키로 묶기»라 인덱스 없이는 표 통째 정렬 한 번이 첫 행보다 먼저 온다. row_id 로 쪽을 넘기고 키 형제를 찾으면 쪽마다 Seq Scan 이라 더 나쁘다.
```
안 ㄱ  돌 때 키 인덱스를 짓는다(CONCURRENTLY, 끝나면 둔다/지운다) — 운영 1,300 만 행에서 짓는 초 · 잠금 안 쟀다
안 ㄴ  접기 키를 «선언»으로 올린다(표의 선언된 키 · 또는 접기 선언) -> 큐 2 기제가 미리 짓는다. 폼의 자유 키는 선언된 것만
안 ㄷ  통째 읽기는 «한 번»으로 줄인다(지금 다섯 -> 하나, 셈은 쪽을 돌며) — 그래도 큰 표에서 첫 줄 5 초는 못 지킨다고 적는다
내 추천  ㄷ 을 이번에(코드만, 되돌리기 쉬움) + ㄱ/ㄴ 중 하나를 결정 받아 큐 2 와 같이. 결정 전엔 ㄷ 만 짓고 «5 초 못 지킴»을 단언 칸으로 남긴다
```

**물음 2 — fold_units 의 첫 줄.** 그룹 칸 인덱스가 없으면 «distinct 그룹을 키 순서로 이어 받기»도 쪽마다 Seq Scan + Sort 다(EXPLAIN 으로 확인 중). 그래서 첫 줄 고침은 큐 2 의 같은 인덱스가 있어야 제대로 선다.
```
안   fold_units 의 첫 줄(순위 셈 · unit_ids · distinct 그룹)도 큐 2 로 옮겨 IN 읽기와 한 커밋에 닫는다
     큐 1 보고의 읽은 행 표에는 fold_units «IN 읽기 · 첫 줄 둘 다 남음 — 큐 2» 로 단언한다(조건 ① 대로)
```

```
다음    100,000 hold 판에서 ① 의 계획을 쪽 크기(1,000 · 5,000 · 10,000 · 20,000)별로 EXPLAIN · withdraw_source 첫 쪽 EXPLAIN ANALYZE
        -> ② · fold_withdrawal_events 짓기 -> ① 은 잰 원인대로(은퇴 인덱스를 되살리는 답이면 짓기 전에 올림)
        -> 1만 · 10만 · 100만 «읽은 행» 게이트 + 고치기 전후 «답이 같다»(바뀐 칸 · 지운 행 · 원장 원자)
트리    C:/wt-impl-b · 가지 impl-b-pageread
```


> **[구현자 B -> 총괄] 10-13 큐 1 — 소급 쪽은 제 행만 읽는다 · QA 요청 (워크트리 C:/wt-impl-b, 가지 impl-b-pageread `3ff350a46`, main 아님)**

```
요지      쪽마다 표를 통째로 읽던 자리를 «쪽 = 키 순서로 다음 N 행, 판정은 그 행 위에서» 한 모양으로 닫았다
          중복 행 접기는 표를 한 번 읽는다(전에는 다섯 번). 보강 확인 sweep 은 드라이 · 적용이 쪽 고리 하나, 쪽의 키를 뷰마다 한 질의로
남음      fold_units 의 IN 읽기 · 첫 줄 전 통째 읽기, 중복 행 접기의 «첫 쪽 전 한 번 읽기» -> 큐 2(접기 남길 행) — 아래 «남음»에 수
수의 출처  main = 응용 판 JSON(qa_census_<n>[_merged] · _notation · _confirm)을 내가 읽은 것 ·
          가지 = 같은 판 조리법(응용 test_zz_qa_census_pg.py 사본, idx_tup_fetch 칸만 더함)을 이 가지에서 내가 돌린 것. 둘 다 이 박스 수, 운영 주장 아님
          DB: PG 시험 DB(assy_test) · 스키마 assy_pytest_pg_<pid>_gw0(판마다 스스로 지움) · public 에 쓴 것 0
```

| 자리 | 잰 원인 | 고침 |
|---|---|---|
| 표기 `_fold_by_values` | 쪽 id 목록(ANY)만 주면 1만 id 부터 계획이 Parallel Seq Scan 으로 뒤집힘(1M 34.8 s 찬 · 1.6 s 데운) | 쪽의 (table_name, row_id) 범위를 같이 줌. 목록은 지운 행의 층을 빼려고 그대로 |
| remove_shell_rows | 빈 칸 판정이 WHERE 안 -> 다음 맞는 행을 찾느라 Seq Scan + Sort(1M 2.3 s/쪽) | 쪽 = 키 순서 N 행(iter_pages), 판정은 쪽 안에서. 쪽 1,000 -> 20,000(1M 이 커밋 1,000 번이었음) |
| fold_withdrawal_events | 표시가 WHERE 안 -> 첫 쪽이 안 맞는 대기 이벤트를 다 읽음 | 쪽 = 대기 이벤트 id 순서 N 개(부분 인덱스), 표시는 쪽 안에서 |
| withdraw_source | source 가 인덱스 넷째 칸 -> 첫 일치까지 층을 다 읽음(1M 첫 쪽 4.5 s). 층에서 row_id 순서로 뽑으면 다른 표의 층을 지나감(죽은 층 6M 판: 한 문장 12.7 s) | 쪽 = «그 표의» 다음 N 행(표 자기 키), 그 행의 층은 id 로 물음. 쓰는 것은 같음 — 표에 없는 행의 층은 전에도 건너뜀, 셈(cells_matched)만 그런 층을 안 셈. 맞바꿈이 있다 — 물음 2 |
| 보강 대기열 derived_pages | 큐 판정이 WHERE 안 -> 쪽마다 파생 표 Seq Scan | 쪽 = 파생 표 다음 N 행, 판정은 쪽 안에서 |
| fold_duplicate_rows | 첫 줄 전 창 함수 통과 다섯(1M 10.58 s) | 순위(`_ranked_duplicates` 한 자리)를 한 번 계산해 셈 · 지울 행 · 미리보기 12 행을 한 문장으로. 키 칸 «그대로» 묶어 인덱스가 순서를 줄 수 있게. 시작 줄 · 답 · 미리보기에 «index on the keys: <이름> / none - declare one on (…) in the table's indexes» |
| 보강 확인 sweep | 드라이가 대기열 전부를 목록 하나 · SAVEPOINT 하나 · 후보 질의 키마다 | 드라이 · 적용 쪽 고리 하나, 쪽마다 자기 세션 트랜잭션(쪽 끝 commit / rollback 한 곳). 후보 질의는 뷰마다 쪽당 한 문장(VALUES × LATERAL) · 실패하면 키마다 + `probe_batch_fallbacks` |

**게이트 1 — 읽은 행 · 첫 줄 · 기울기** (`main -> 가지`, 크기 1만 / 10만 / 100만 · 상한 45 초 안에 간 행)
```
R1 fold_written_notation   rev 1만 715b3ea2d / 10만 3ff350a46 / 100만 3ff350a46
  크기    첫 줄 s         첫 쪽 s  읽은 행 seq        idx    s/1,000        45 초에 간 행
  1만    0.12 -> 0.61  0.64   21k -> 21k      88k    0.036 -> 0.042 10,497 -> 10,477
  10만   0.27 -> 0.3   0.3    210k -> 210k    885k   0.053 -> 0.05  104,997 -> 104,978
  100만  1.84 -> 2.09  2.11   131.1M -> 1.1M  7.4M   0.199 -> 0.051 221,342 -> 852,767

R4 fold_duplicate_rows (hold log)   rev 1만 715b3ea2d / 10만 3ff350a46 / 100만 3ff350a46
  크기    첫 줄 s         첫 쪽 s  읽은 행 seq        idx    s/1,000        45 초에 간 행
  1만    0.36 -> 0.28  0.52   52k -> 11k      1002   0.883 -> 1.591 496 -> 501
  10만   2.81 -> 0.2   1.27   535k -> 115k    10k    0.777 -> 0.991 5,069 -> 5,091
  100만  10.58 -> 0.19 9.84   5.4M -> 1.2M    82k    0.777 -> 1.113 45,023 -> 41,023

R4 remove_shell_rows (hold official)   rev 1만 715b3ea2d / 10만 3ff350a46 / 100만 3ff350a46
  크기    첫 줄 s         첫 쪽 s  읽은 행 seq        idx    s/1,000        45 초에 간 행
  1만    0.17 -> 0.12  0.17   84k -> 10k      9627   0.598 -> 0.818 497 -> 477
  10만   0.22 -> 0.11  0.16   1.3M -> 0       120k   0.691 -> 0.509 4,997 -> 4,978
  100만  0.73 -> 0.14  0.23   41.5M -> 0      1.2M   0.642 -> 0.485 50,159 -> 50,251

R4 fold_units   rev 1만 715b3ea2d / 10만 3ff350a46 / 100만 3ff350a46
  크기    첫 줄 s         첫 쪽 s  읽은 행 seq        idx    s/1,000        45 초에 간 행
  1만    0.16 -> 0.19  0.22   52k -> 52k      23k    0.434 -> 0.422 5,000 -> 5,000
  10만   0.34 -> 0.48  0.55   800k -> 800k    280k   0.38 -> 0.354  50,000 -> 50,000
  100만  2.86 -> 3.0   3.06   12.0M -> 12.4M  617k   0.454 -> 0.467 93,011 -> 93,015

R4 fold_duplicate_rows (fold log)   rev 1만 715b3ea2d / 10만 3ff350a46 / 100만 3ff350a46
  크기    첫 줄 s         첫 쪽 s  읽은 행 seq        idx    s/1,000        45 초에 간 행
  1만    0.56 -> 0.23  0.45   35k -> 10k      16k    0.768 -> 0.801 8,000 -> 8,000
  10만   1.38 -> 0.59  1.86   0 -> 0          218k   0.71 -> 0.759  62,023 -> 59,023
  100만  8.89 -> 0.19  11.51  92k -> 0        1.1M   0.716 -> 1.078 51,023 -> 42,023

R5 enrichment confirm (dry, candidate_for declared)   rev 1만 213694edd / 10만 213694edd / 100만 213694edd
  크기    첫 줄 s         첫 쪽 s  읽은 행 seq        idx    s/1,000        45 초에 간 행
  1만    0.16 -> 0.0   0.23   30k -> 12k      15k    None -> 0.356  0 -> 2,500
  10만   0.59 -> 0.0   0.45   12k -> 0        50k    None -> 0.197  0 -> 25,000
  100만  4.28 -> 0.0   0.16   40k -> 0        250k   None -> 0.151  0 -> 250,000

R5 withdraw_source   rev 1만 d7b8826e0 / 10만 d7b8826e0 / 100만 d7b8826e0
  크기    첫 줄 s         첫 쪽 s  읽은 행 seq        idx    s/1,000        45 초에 간 행
  1만    0.0 -> 0.0    0.22   105k -> 1111    53k    0.417 -> 0.433 9,999 -> 9,999
  10만   0.0 -> 0.02   0.31   0 -> 0          361k   0.343 -> 0.366 99,999 -> 99,999
  100만  0.0 -> 0.0    0.22   0 -> 0          654k   0.352 -> 0.361 133,839 -> 125,163

fold_withdrawal_events   rev 1만 d7b8826e0 / 10만 d7b8826e0 / 100만 d7b8826e0
  크기    첫 줄 s         첫 쪽 s  읽은 행 seq        idx    s/1,000        45 초에 간 행
  1만    0.12 -> 0.12  0.2    20k -> 0        40k    0.045 -> 0.111 10,000 -> 10,000
  10만   0.22 -> 0.11  0.12   0 -> 0          318k   0.046 -> 0.036 100,000 -> 100,000
  100만  3.11 -> 2.2   7.12   0 -> 0          4.0M   0.052 -> 0.041 806,385 -> 1,000,000

R1 fold_written_notation (foldable)   rev 1만 213694edd / 10만 213694edd / 100만 213694edd
  크기    첫 줄 s         첫 쪽 s  읽은 행 seq        idx    s/1,000        45 초에 간 행
  1만    0.11 -> 0.12  0.19   40k -> 40k      258k   0.422 -> 0.48  10,000 -> 10,000
  10만   0.19 -> 0.14  0.22   200k -> 1.2M    3.9M   0.451 -> 0.533 100,000 -> 89,548
  100만  1.98 -> 2.45  2.58   1.0M -> 1.0M    2.2M   0.473 -> 0.557 94,790 -> 80,348
```
⚠️ 중복 행 접기의 s/1,000 은 견주지 못한다 — 이 칸은 «첫 줄 뒤»부터 재는데, 가지의 첫 줄은 읽기 «전» 시작 줄이고 main 의 첫 줄은 읽기 «뒤»다.
끝까지 간 판의 전체 초로 보면: hold 1만 0.8 -> 1.08 · 10만 6.75 -> 5.25 / 접기 1만 6.7 -> 6.64. 쪽당 정상 속도(steady)는 0.7 로 같다. 100만은 둘 다 상한에 걸려 «45 초에 간 행»이 견줄 칸

**게이트 2 — 답이 같다** (1만 판 · 기점 30ed3b798 과 이 가지 3ff350a46 을 같은 판 조리법으로 끝까지 apply, 끝 상태를 uuid 와 무관한 키로 떠서 견줌)
```
판        견준 것                                                        결과
notation  행(k · w · v · note · 키) · 층(행 k · 칸 · 소스 · 값) · 답           같음 (층 48,740)
hold      빈 행 지운 뒤 공식 행 · 접기 표시(진 행 -> 남은 행) · 쌓인 사건 · 미리보기   같음
fold      fold_units 드라이 · 적용 답과 표시 · 중복 접기 답과 표시 · 미리보기        같음
outbox    withdraw 뒤 값 · 층 · 회수 사건 접기 뒤 대기 사건이 이름 댄 (표 · 종류 · 행)  같음 (21,111)
confirm   sweep 드라이 · 적용 답 · 파생 행 wafer_id                           같음
합        24 칸 전부 같음 (미리보기 예시는 총괄 지시대로 옛 «글자 순서»)
```

**게이트 3 — 진짜 프로세스** (런처 넷: 서버 · 와쳐 · 체인 워커 · 스케줄러, 3ff350a46 사본 · 빈 스키마 assy_b_pageread_1013 · 소급 탭이 보내는 문 그대로)
```
remove_shell_rows      껍데기 7 행 삭제 · «rows_deleted 7 · rows read 7 · pages 1»
fold_duplicate_rows    선언한 키 인덱스를 체인 워커가 기동 때 지음 -> «index on the keys idx_b_log_job_x_y» · 10 키 표시(L040 -> L000 …)
                       인덱스 없는 키 순서(x, job)의 미리보기 «none - declare one …»
fold_withdrawal_events 다른 대기 30 개 사이의 회수 사건 25 개 -> 접힌 2 개 · 쪽 7
withdraw               b_f0.csv 250 칸 · 쪽마다 «read» 줄과 진행 줄
보강 확인(새로 넣음)    decide 선언(참조 뷰 candidate_for · auto_confirm) 하나: 체인 훅이 파생 12 행 wafer_id 12 개 확정 · «candidate probe
                       execution failed» 줄 0. 값과 층을 지운 5 칸 -> 소급 탭 enrichment_confirm 미리보기 5 · 적용 «confirmed 5» -> 12 / 12
                       ⚠️ 이 판에서 묶음 문장이 몇 번 돌았는지는 안 셈(pg_stat_statements 없음) — 문장 수는 PG 칸이 잼(뷰마다 쪽당 1: 2 대 24)
공통                   public 행 변화 0 · 스키마 지움 · /health 에 paused 가 안 보임(대기 이벤트는 남아 접기에 쓰임 — 앞 판들과 같음)
```

**게이트 4 — 보강 확인 sweep 의 가장 긴 트랜잭션 = 쪽 하나** (pg_stat_activity xact_start 를 50 ms 마다, 4만 판 · 쪽 19)
```
드라이  가장 긴 트랜잭션 0.235 s ≤ 가장 긴 쪽 0.282 s     적용  1.691 s ≤ 1.734 s
드라이 100만  250,000 키를 37.8 s 에 끝까지(main 450.6 s, 상한 넘어 안 멈춤)
```

**변이** — 후보 질의 묶기 칸 넷(답을 다른 키에 · 키가 하나로 뭉침 · 쪽 답을 안 읽음 · 실패를 말 안 함) · 미리보기 순서 칸(번호를 거꾸로 · 키 글자 -> 칸 그대로) · 표 선언 인덱스 칸(순서 무시) 모두 빨강

**남음 — 큐 2** (fold_units 는 총괄 결정 · 중복 행 접기는 지시서 큐 2 «접기 남길 행»을 내가 읽은 것 — 물음 1)
```
fold_units           «단위 칸 IN (…)» 읽기 — 쪽마다 fu_inventory Seq Scan · 첫 줄 전 통째(위 표 그대로)
fold_duplicate_rows  첫 «쪽» 전 한 번 읽기 — 100만 첫 쪽 9.84 s(hold 판) · 11.51 s(접기 판), main 의 첫 줄 10.58 · 8.89 s.
                     45 초에 간 행 41,023 · 42,023(main 45,023 · 51,023) — 접기 판은 main 보다 늦다
                     잰 내역(100만 접기 판, 지울 행 80만): DB 순위 계산 4.4 s + 80만 행이 SQLAlchemy 행이 되는 데 약 6~8 s
                     (같은 문장을 DBAPI 커서로 받으면 7.4 s). 미리보기 번호를 LIMIT 위로 올린 것(통정렬 제거, 1.5 s)만 이번에 넣음
                     키 순서로 흘려 읽으면(키 인덱스 있으면 정렬도 없음) 첫 쪽이 순위 계산을 안 기다림 — 큐 2 의 일
```

**잰 원인 · 안 고침**
```
fold_withdrawal_events 100만 첫 읽기 2.2 s   계획이 pkey 로 간다(EXPLAIN). 앞 단계(set_aside)가 처리한 100만 행을 지나 첫 대기 이벤트까지 걷는 것으로 «추정», 안 잼.
                                             첫 줄 5 s 안 · 이후 쪽 0.3 s/1만 · 100만 전부 43 s(main 45 s 에 806,385)
withdraw_source                             모든 행이 그 source 를 가진 판: 응용 판 100만 main 133,839 -> 가지 125,163 행(-7%) · 같은 판 A/B -8%(DB 초 같음)
                                             source 가 드문 판(1,000 행에 1 행, 같은 A/B 탐침, 기점 = 30ed3b798 의 withdraw_source):
                                               표 111k 행 · 층 1M    전체  기점 0.22~0.31 s · 가지 1.7~1.8 s
                                               표 1M 행 · 층 9M      전체  기점 4.1~10.5 s · 가지 17.6~24.7 s (문장 51~61 · 4,719)
                                                                     가장 느린 한 문장  기점 0.84~3.47 s · 가지 0.01~0.17 s
                                             -> 가지는 «한 문장이 층을 훑는 일»을 없앤 대신, 표의 행을 다 쪽으로 지나서 전체가 2~8 배 길다 — 물음 2
표기 foldable 판                             1,000 행당 main 0.451 / 0.473 -> 가지 0.533 / 0.557 s (10만 / 100만). 100만에서 문장별로 갈라 봄:
                                             고친 범위 읽기(SELECT cell_sources)의 행당 초는 main 과 같음(0.040 ms), 손 안 댄 audit_logs INSERT 가
                                             같은 비율로 느림(8.6 s 에 94,790 행 -> 8.7 s 에 80,348 행) — 판 사이 흔들림으로 봄, 같은 판 A/B 는 안 함
                                             10만에서 qa_nf Seq Scan 2 -> 12 번: 쓰기 문(UPDATE … FROM unnest, 21 번 합 1.24 s) — 쪽이 5,600 행까지 커지자
                                             10만 표에서 계획이 표 훑기를 고름(추정, 계획은 안 떴음). 100만에서는 main 과 같은 3 번
enrichment_backfill                          1,000 행당 main 0.356 -> 가지 0.421 s(100만). 이 길은 이 가지가 안 지남(derived_pages 를 안 부름 ·
                                             main 기준선 1e23bc216 과 가지 기점 30ed3b798 사이 server/ 차이 0 줄) — 판 사이 흔들림으로 봄
                                             파생 표 Seq Scan 은 쓰기 문(crud.apply_batch_updates)의 기존 행 찾기(방금 만든 작은 표, ANALYZE 앞뒤 같음)
auto_confirm 켠 판의 처음 채우기              재현 안 됨(1만, 한 프로세스에서 끔/켬: 가지 3.59 / 3.95 s · 기점 4.20 / 3.58 s, 문장 213 같음)
요청 길의 셈                                  _count_remove_shell_rows · _count_fold_units 는 미리보기에서 dry run 을 끝까지 돈다(until 없음) — 다른 성질이라 말만
```

**물음 둘** — 나머지는 QA 부탁드립니다. 착지는 두 답과 QA 뒤, rebase · push HEAD:main 에 RELEASE_LOG 항목과 RUN.md 절을 같은 커밋으로.
```
물음 1  중복 행 접기 — 접기 판 100만에서 main 보다 늦다(첫 쪽 11.5 s · main 첫 줄 8.9 s, 45 초에 42,023 · main 51,023 행)
        ㄱ 지금대로 착지, 큐 2(키 순서로 흘려 읽기)에서 닫는다 — «중복 접기 = 큐 2 의 접기 남길 행»은 지시서 문구를 «내가» 읽은 것
        ㄴ 지금 «DBAPI 커서로 받기»를 넣는다 — 같은 읽기 12.1 -> 7.4 s(100만 접기 판, 잼). 답 같다 · 변이 다시
        내 추천 ㄱ — ㄴ 의 자리는 큐 2 의 흘려 읽기가 다시 짓는 자리다
물음 2  withdraw_source — 위 «잰 원인»의 맞바꿈
        ㄱ 지금대로(쪽 = 그 표의 다음 N 행): 한 문장 ≤ 0.17 s · 첫 줄 바로, 대신 source 가 드문 표에서 전체 2~8 배
        ㄴ 기점으로 되돌림: 전체 빠름, 대신 첫 쪽이 첫 claim 까지 그 표의 층을 훑는다(층 9M 에서 한 문장 3.47 s, 총괄 판 13M 에서 4.5 s)
        ㄷ ㄱ 의 키 읽기만 크게(빈 행 지우기처럼 한 번에 2만 행, 쓰는 쪽은 그대로) — 안 쟀다. 지금 재는 중이고 수가 나오면 덧붙인다
        내 추천 ㄷ(재서 기점 전체 초에 가까우면), 아니면 ㄴ — 첫 줄 5 s 는 13M 층까지 기점도 지킨다
```

> **[구현자 B -> 총괄] 10-13 큐 1 물음 둘 닫음 — 가지 HEAD 94db41466 (QA 는 3ff350a46 위 두 커밋만)**

```
물음 1 (ㄴ)  53537acd7  중복 행 접기가 지울 행을 «위치로» 읽음 — 이름으로 찾기 240 만 번이 13 s 읽기의 5 s 였다
             같은 판 A/B(접기 판 100만, apply, 45 초씩, 번갈아): 기점 42,023 / 44,023 행 · 첫 표시 11.0 / 9.3 s
             가지 46,023 / 44,023 행 · 9.0 / 8.9 s. 지울 행 · 남길 행 칸을 바꾼 변이(읽는 쪽 · SELECT 쪽) 각 14 칸 빨강
물음 2 (ㄴ)  94db41466  withdraw_source 를 기점 읽기로 되돌림(끝에서 None 만 지금 쪽 규약대로)
             ㄷ 잼(표 100만 · 층 900만 · 1,000 행에 1 행, 같은 판 번갈아): 전체 기점 9.0 / 4.3 s · 표 행 쪽 27.2 / 19.0 s ·
             키 2만 행 쪽 16.7 / 17.6 s, 한 문장 최대 기점 3.4 / 0.95 s — ㄷ 이 «전체 초가 기점보다 나쁘지 않음»을 못 지킴
             withdraw 경로 칸 277 초록(SQLite + PG)
착지 문안    RELEASE_LOG · RUN.md 에서 Withdraw 를 «키 순서 쪽» 목록에서 뺌
```

> **[구현자 B -> 총괄] 10-13 f7394bfdf 원장 행 색인 키 — 짓기 전 전수 · 안 셋 · 이주 초 (물음 하나)**

```
전수(AST/grep + 함수 열어 확인)  행 색인 표를 직접 만지는 자리 26 · 그 값을 나르는 자리 10
  키에 ref 전문이 «필요한» 곳     PRIMARY KEY 하나뿐 — 쓰기(_write_row_refs)는 «과녁 없는» ON CONFLICT DO NOTHING 이라 어느 유일 인덱스든 받음
  ref 로 견주는 곳               뷰 ledger_atom_rows 가 이미 md5(r.ref) = md5(e.ref) AND r.ref = e.ref
                               거두기(withdraw_deleted_rows · rescope)는 행 색인에서 «전문»을 꺼내 원장 사건을 source_raw_ref = ANY 로 지움
                               — 원장 사건 쪽은 hash 인덱스(전문)라 바이트 상한 없음
  선례                          원장 사건의 유일 키 uq_ledger_atom 이 이미 md5(source_raw_ref) 로 겨룸(DEDUPE_COLUMNS, 4bdbff36: 1,123MB -> 160MB)
  이주가 «안» 되는 까닭          ensure_schema 는 있는 표의 키를 안 바꾸고(CREATE IF NOT EXISTS), 인덱스 · 뷰도 «이름이 없을 때만» 짓는다
                               migrations/add_ledger_atom_rows.py 는 기본 세상만 — 가지 세상은 길이 없다
```

| 안 | 무엇을 | 운영자가 할 일 | 좋은 점 | 위험 |
|---|---|---|---|---|
| ㄱ 식 유일 인덱스 | PRIMARY KEY 를 떼고 `UNIQUE (relation, row_id, source_who, md5(source_raw_ref))`. 지문 식은 상수 하나 — 이 인덱스 · 원장 DEDUPE_COLUMNS · 행 색인 raw 인덱스 · 뷰 조인이 그 상수를 지남. 전문은 같은 칸(키 밖) | 이주 명령 한 줄(세상마다) | 표를 다시 쓰지 않음 — CONCURRENTLY 로 지은 뒤 PK 만 뗌. 쓰는 쪽 코드 변경 0 | 표에 PRIMARY KEY 가 없어짐(유일성은 인덱스가 지킴) · md5 가 겹치면 둘째 줄이 말없이 빠짐(원장 키와 같은 성질) |
| ㄴ 생성 칸 | `source_raw_ref_md5 TEXT GENERATED ALWAYS AS (md5(source_raw_ref)) STORED` + 그 칸으로 PK | 이주 명령 한 줄 | PK 가 남음 | 칸 더하기가 «표 다시 쓰기» — 그동안 읽기 · 쓰기 다 막힘(ACCESS EXCLUSIVE) |
| ㄷ 파이썬 지문 칸 | 쓰는 쪽이 지문을 지어 칸에 넣고 PK 를 그 칸으로 | 이주(칸 · 채우기 · 키) | PK 가 남음 | 채우기 UPDATE 가 표 전부(표 두 배) · 쓰는 쪽 · 시험 고침이 가장 많음 |

**이주 초 — 박스(PG 시험 DB, 스크래치 스키마, 행 색인과 같은 모양의 표)** · 잠금: CIC = 쓰기 안 막음 / 그 밖 ALTER = 읽기 · 쓰기 다 막음
```
                         100만 · ref 95 B(496MB)   100만 · ref 1,503 B(1.9GB)   500만 · ref 96 B(2.6GB)
ㄱ 식 인덱스 CONCURRENTLY      6.7 s                    10.1 s                   22.4 s
  PK 떼기(막음)               0.04 s                   0.01 s                   0.18 s
  되돌리기(원래 PK CIC + 붙이기 + 식 인덱스 지우기)  6.7 + 0.04 + 0.17 s   12.0 + 0.0 + 0.01 s   25.2 + 0.01 + 0.05 s
ㄴ 생성 칸 더하기(막음)        27.3 s                   66.6 s                   103.9 s
  PK 바꾸기(막음)             11.7 s                   39.0 s                   46.7 s
ㄷ 채우기 UPDATE              78.8 s                   157.3 s                  679.8 s
  PK 바꾸기(막음)             12.5 s                   59.7 s                   44.3 s
⚠️ CONCURRENTLY 는 «시작할 때 열려 있던 DB 의 모든 트랜잭션»을 기다린다 — 1천 행 판에서 다른 세션 트랜잭션 때문에 215 s(재기 전 가장 오래된 트랜잭션 나이를 같이 찍음)
⚠️ PK 떼기는 짧지만 그 표를 쓰는 트랜잭션이 끝날 때까지 줄을 선다 — 이주 명령은 lock_timeout 을 걸고, 못 잡으면 다시 하라고 말한다
```

```
내 추천   ㄱ — 지문을 PG 가 짓는 «한 식»으로 두면 짓는 자리가 하나이고(원장 키와 같은 상수), 쓰는 쪽 · 지우는 쪽 · 읽는 쪽 코드가 안 갈라진다. 이주가 쓰기를 막지 않는다
이주(ㄱ)   세상마다: CREATE UNIQUE INDEX CONCURRENTLY … md5(source_raw_ref) -> 유효한지 확인 -> SET lock_timeout · ALTER TABLE … DROP CONSTRAINT <pkey>
          되돌리기: (전문이 상한 안인 행만 있을 때) CREATE UNIQUE INDEX CONCURRENTLY … (원래 넷) -> ADD CONSTRAINT … PRIMARY KEY USING INDEX -> 식 인덱스 지움
          ensure_schema 는 새 세상에 같은 모양으로 짓고, 있는 세상에 옛 키가 있으면 이주 명령을 한 줄 말함(짓지 않음)
          이주 뒤 RUN.md: requeue_failed 한 줄 + 답의 뜻 · 이 실패가 지금 운영자 화면 어디에 보이는지 열어서 적음
여쭐 것   PRIMARY KEY 없이 유일 인덱스로 키를 지켜도 되는지(ㄱ) — 아니면 ㄴ / ㄷ 중 무엇
```
