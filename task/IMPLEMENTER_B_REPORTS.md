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

> **[구현자 B -> 총괄] 10-13 큐 1 QA(59c0bfb8c) 고침 다 지음 — 가지 HEAD `39c7115ed`, 3ff350a46 위 커밋만 보시면 됩니다**

| QA | 고침 | 커밋 | 지키는 칸 (변이) |
|---|---|---|---|
| 1 바인드 판정 둘 | 로더가 text() 의 바인드 정규식 «그 자체»를 씀(같은 객체) · 적재 때 `:x::type` 거절 «write CAST(:x AS type) instead of :x::type» | 0c941b2ee | 여섯 철자에서 두 파서가 같은 바인드 + 거절 문구 — 옛 파서에서 빨강 |
| 2 묶음 실패가 조용함 · VALUES 형 | 제 문장 «candidate probe batch failed - each key asked alone»(제 throttle) · 경고 줄 «batch -> key by key for n key(s)» · 실행 결과 `probe_batch_fallbacks` · 미리보기 문장. VALUES 칸은 파생 표 그 칸 형으로 CAST | 0c941b2ee | PG: 숫자 칸 뷰가 되물림 0 으로 같은 답(CAST 빼면 빨강) · ERROR 줄 · 경고 줄 · 미리보기 문장(각 변이 빨강) |
| 3 dry 가 지울 행을 받음 | 지울 행은 apply 때만 읽음, 셈은 같은 한 읽기 | ab175aef2 | dry · 미리보기 · apply 의 수가 같고 apply 만 받음(늘 받기 변이 빨강) |
| 4 빈 행 지우기 한 트랜잭션 9.7 s | 읽기는 2만 행까지, 지우기는 쪽 시간 규칙의 조각마다 커밋 · 멈춤은 조각 사이 | 10240159e | PG: 일곱 껍데기가 3 + 3 + 1, 첫 조각 뒤 멈춤 남는 4(통째 지우기 · 조각 사이 멈춤 없음 변이 빨강) |
| 5 M7 · M10 | 칸 둘: 범위 칸이 빈 행도 범위 밖으로 셈 · 범위 밖 행이 가장 일러도 남길 행으로 안 불림 | ab175aef2 | M7 · M10 각 빨강 |
| 6 derived_pages 드문 대기열 | 같은 판 A/B -> 기점 읽기로 되돌림(아래 표) | 93f30957c | — |
| 물음 2 다시 | withdraw 는 ㄱ(표 키 쪽)으로 — 총괄 결정. 기점 읽기는 hold 판을 지운 직후 첫 문장 10.44 s(아래) | 39c7115ed | M3 칸: claim 없는 표 행은 읽어도 수에 안 듦(M3 변이 빨강) |
| 7 | 회수 사건 접기는 표시 맞는 사건의 목록(row_ids · written_by)만 받음 · `discarding` 은퇴(약속 든 자리: 모듈 독스트링 · CODE_MAP 표 · 호출자 수 · 시험 줄 · 문장 셋, 칸은 같은 커밋에서 걷고 증상 칸은 남김) · LATERAL_DIALECTS | f26ed1ab8 · 2b54a4001 · 0c941b2ee | M3 은 위 «물음 2 다시» 줄 |
| 문서 | CODE_MAP remove_shell_rows 행 · BACKFILL_GUIDE «1,000 행씩» · count_withdrawable 독스트링 · RELEASE_LOG 문안에 빠진 주장 둘(체인 훅도 묶음 질의 · 키 하나 길도 값 순서) | 0e58b35e2 (+ 착지 커밋) | — |

**6 — derived_pages 같은 판 A/B** (기점 30ed3b798 · 가지, 번갈아, 대기열 끝까지 / 미리보기 200 행)
```
판                                   기점 전체 s     가지 전체 s     기점 미리보기 · 가지
100만 · 1,000 행에 1 행 대기          1.77 / 0.59     5.49 / 5.24     0.12 / 0.05 · 1.02 / 1.05
100만 · 10 행에 1 행                  2.24 / 1.37     6.01 / 5.78     0.01 · 0.02
100만 · 전부 대기                     10.50 / 10.64   10.90 / 11.31   0.01 · 0.01
응용 판 모양(파생 25만, backfill) 전부   2.69 / 2.58     2.66 / 2.68     0.02 · 0.01
응용 판 모양 · 296 행 대기              0.32 / 0.18     1.46 / 1.58     0.12 / 0.13 · 1.04 / 1.06
기점의 가장 긴 한 문장 0.83 s — 응용 표 8 의 «쪽마다 Parallel Seq Scan» 은 이 판 다섯에서 재현 안 됨
```

**답이 같다** — 26/26 같음(기점 30ed3b798 대 가지 93f30957c, 1만). 새로 든 칸: hold 판 끝에 체인 · 원장 따라가기를 다 비운 뒤 원장 원자(무엇을 말하나로 묶음 500) · 공식 표. withdraw 의 지금 읽기(39c7115ed = d7b8826e0 읽기)는 그 읽기였던 3ff350a46 판에서 24/24 같음

**100만 다시 잼** (가지 93f30957c, census 판 hold · outbox · confirm, `main -> 가지` · 응용 걷기 판 10:04~10:17 겹침)
```
빈 행 지우기      첫 쪽 0.25 s · seq 41.5M -> 57k · 45 초 안 26.7 s 에 끝(main 32.9 s) · 지운 행 50,142
중복 접기(hold)   첫 쪽 9.91 s(main 첫 줄 10.58) · 45 초에 40,023 행(main 45,023, 다른 때 판) · seq 5.4M -> 1.1M
                  같은 판 A/B 는 접기 판에서만(가지 ≥ 기점, 앞 보고)
표기(hold)        seq 131M -> 1.05M · 45 초에 852,767 행(main 221,342)
보강 확인 드라이  250,000 키를 41.4 s 에 끝(main 450.6 s 안 멈춤) · 첫 쪽 0.17 s
회수 사건 접기    첫 줄 3.16 s(main 3.11) · 45 초에 921,408(main 806,385)
withdraw          이 판에서 기점 읽기의 첫 문장 10.44 s -> 물음 2 다시 열어 ㄱ 으로(같은 판 번갈아: 기점 20,025 / 31,013 행 · ㄱ 43,023 / 38,023 행 · ㄱ 가장 긴 문장 0.60 s)
                  대가: source 가 드문 표에서 전체 2~8 배(100만 · 층 900만 · 1,000 행에 1 행 19~27 s, 기점 4~9 s) — RELEASE_LOG · RUN.md 에 적음
```

**진짜 프로세스** (런처 넷, 빈 스키마 assy_b_pageread_1013, 소급 탭이 보내는 문 그대로 — HEAD 39c7115ed)
```
빈 행 지우기 7 행 · 쪽 3 · 중복 접기 10 키 표시(선언 인덱스 idx_b_log_job_x_y) · 회수 사건 25 -> 2 · withdraw 250 칸(쪽마다 read 줄)
보강 확인: 체인 훅이 12 키 확정 · 묶음 실패 줄 0 · 값과 층을 지운 5 칸 -> 미리보기 5 · 적용 «confirmed 5» -> 12 / 12
public 행 변화 0 · 스키마 지움
```

**시험 수** (passed 수) — 바뀐 시험 파일 11 개 `-m pg` 55 passed · 14 개 `-m "not pg"` 182 passed(1 skipped) · withdraw 경로 16 개 SQLite + PG 278 passed.
이 워크트리에서 기점에서도 지는 셋은 이 일과 무관: test_ledger_trace · test_ledger_transfer_unit(확정 규칙 둘) · test_the_index_can_be_recovered…dry_run(워크트리에 table_config.json 없음)

**물음** — 없음. 이 커밋들을 보시고 GO 면 RELEASE_LOG · RUN.md 와 함께 착지합니다.

> **[구현자 B -> 총괄] 10-13 796f04605 원장 따라가기 · 체인 지움 · decide 옛 키 — 짓기 전 안 셋 (코드로 읽음, 잰 것 없음)**

```
지금 모양(origin/main 코드)
  따라가기   run_ledger_followup 한 바퀴 = drain_outbox_once 를 units 번(fast: 큐가 빌 때까지) — 한 번에 «사건 하나»(가장 오래된 id),
             그 사건의 행들로 소스마다 rescope 한 번, 표시 한 문장. 사건이 작으면 행당 고정비가 처리량을 정한다
  체인 지움  DELETE 는 규칙 고리에 안 들어감(_is_trigger_event: CREATE · EDIT). 지운 행이 먹인 칸 거두기는
             _drain_ledger_followup_sync 안(ingestion_worker 의 따라가기 배치) — 원장 선언이 컴파일 안 되면
             FollowUpStopped 로 그 배치가 안 돌아 체인 지움도 안 거둠
  decide     키를 payload 의 «지금» data 로만 지음(mapper.py) — 옛 키는 다시 안 셈(옛 그룹은 옛 수 N 그대로),
             DELETE 는 안 닿음, 0 이 된 파생 행은 안 지움(빈 행 판정이 0 을 값으로 봄) -> 원장 엣지도 남음
  옛 값      EDIT payload 에 없음(칸 «이름»만) · 같은 트랜잭션의 audit_logs 에 있음(사람 고침은 칸마다,
             기계 쓰기는 «col: val, …» 한 줄 글) · DELETE 의 감사 줄은 old_value 없음
묶음 번역의 계약  원자의 시각은 행 값(소스의 occurred_at)과 소스 선언의 basis 에서 온다 — 사건 시각(queued_at)은 «기다린 초»에만 쓰임
             -> 같은 표 · 같은 종류 사건을 묶어 한 번 rescope 해도 원자 · 시각은 같다. 다만 영수증이 «한 트랜잭션 id» 를 싣는다
             (following(tx) — 이력 화면이 «누구의 고침을 따라갔나»를 그 id 로 보임) -> 묶음은 트랜잭션별로
```

| 안 | 무엇을 | 운영자가 할 일 | 좋은 점 | 위험 |
|---|---|---|---|---|
| ㄱ 사건이 옛 값을 싣는다 | ① DELETE 사건을 체인 그룹 고리가 받아 거두기(_retract_what_those_rows_fed)를 «그 그룹 안»에서 — 따라가기에서 뺌. ④ EDIT 사건에 «바뀐 칸의 옛 값», DELETE 사건에 «지운 행의 값»을 싣는다(쓰기 문이 이미 아는 값: EDIT 는 스테이징 때 attr.history, DELETE 는 지우기 전 읽은 행). decide 는 지금 키 + 옛 키를 다시 세고, 0 이 된 파생 행은 그리드 지우기 문으로 지운다(-> DELETE -> 원장 엣지 거둠). ② 따라가기는 page_seconds 안에서 사건을 여럿 꺼내 (표 · 트랜잭션 · 종류)로 묶어 한 번 rescope, 표시 한 문장 | 없음. 이미 낡은 요약은 소급 탭의 «decide 다시 세기» 한 번 | 옛 값이 «사건 하나»에 있어 decide 말고 같은 성질 자리(조인 왼쪽 동반 · fold_by_unit)도 같은 값을 쓸 수 있다 · 감사 글을 파싱하지 않는다 | 사건 payload 가 커진다(EDIT 는 바뀐 칸만, DELETE 는 지운 행 전부 — 1,000 행 지우기면 그 행 값 1,000 개) · DELETE 가 규칙 고리에 «decide 만» 들어가는 문이 하나 생긴다(지금 «DELETE 는 안 깨운다» 판정을 좁혀 뒤집는 것 — 판정 435 ④ 인용해 올림) |
| ㄴ decide 가 소속을 기억한다 | ④ decide 가 «원천 행 -> 그룹 키» 소속 표를 원장 행 색인처럼 같은 쓰기에 적는다. EDIT · DELETE 때 옛 키는 그 표에서 읽는다(사건에 옛 값 불필요). ① · ② 는 ㄱ 과 같다 | 이주(소속 표 · 기존 파생 행의 소속 채우기 한 번) | payload 가 안 커진다 · DELETE 도 지운 뒤에 옛 키를 안다 · 원장 행 색인과 같은 모양 | 표 하나 + decide 쓰기마다 원천 행 수만큼 줄 쓰기(1,000 행 그룹이면 1,000 줄) · decide 에만 맞는 답이라 같은 성질 자리(조인 · 접기)는 따로 남는다 |
| ㄷ 옮기지 않고 앞세운다 | ① 거두기는 따라가기 배치에 두되 «원장 선언 컴파일 전»으로 올려 원장이 서도 돈다 · DELETE 사건을 먼저 집는다. ④ 옛 값은 같은 트랜잭션의 audit_logs 에서 읽고(기계 쓰기 줄을 구조로 바꿈), DELETE 감사 줄에 지운 행 값을 적는다. ② 는 ㄱ 과 같다 | 없음 | 체인 고리를 안 건드린다 — 판정 435 ④(DELETE 는 규칙 고리 밖) 그대로 | 체인 지움이 여전히 따라가기 «속도»에 묶인다(① 도착지 «원장과 무관하게» 를 반만 채움) · 감사 줄 모양을 바꾸는 것이 이력 화면 · 시험의 기대를 건드림 |

```
크기      안 잼. 손댈 자리 수(코드로 셈): ㄱ = 체인 그룹 고리 1 · 스테이징 2(auto_stage · stage_collapsed_event) · delete_rows_batch 1 · decide 맵퍼 1 · 따라가기 1 + 다시 세기 소급 1
          ㄴ = ㄱ 에서 스테이징 2 · delete 1 대신 소속 표 1 + 그 쓰기 1 + 이주 1 · ㄷ = 따라가기 1 · 감사 쓰기 2 · decide 1 + 다시 세기 1
내 추천   ㄱ — ① 도착지(«원장과 무관하게 체인 고리 안에서»)를 다 채우고, 옛 값을 «사건에서» 읽는 한 자리라 decide 뒤에 같은 성질 자리를 같은 값으로 넓힐 수 있다.
          DELETE 를 규칙 고리에 들이는 것은 «decide 처럼 지운 행을 다시 세는 규칙»만(선언 칸이 아니라 규칙 종류가 이미 아는 성질)으로 좁힌다
여쭐 것   ① 판정 435 ④(DELETE 는 규칙 고리에 안 들어감)를 «거두기 · 다시 세기만 그룹 고리 안»으로 좁혀 뒤집어도 되는지
          ② DELETE 사건에 지운 행 값을 싣는 크기(1,000 행 지우기 = 값 1,000 행)를 받아도 되는지 — 아니면 ㄴ
덧(작게)  표 잠금 기다림 · 빈 값 판정 둘(NaN) · 죽은 runner cancel 문장은 이 판 안에서 작게 — 지은 뒤 같은 보고에
③         행 하나 번역 비용은 짓기 전에 운영 규격 판에서 잰다(질의 · 파이썬 · 쓰기 몫) — 같은 판 A/B(사건 크기 1 · 10 · 1000)의 기준선
```

> **[구현자 B -> 총괄] 10-13 d9be013cb 재번역 디버그 로그 착지 `85d7e1de1` — 단계 줄 · 5 초 박동 · 느린 문장, 그리고 재번역 비용 재기의 지금까지**

```
착지    85d7e1de1 (main) — RUN.md 맨 위 절 · RELEASE_LOG 항목 같은 커밋. pull 만, 재기동 없음(소급 실행은 실행마다 새 프로세스)
볼 곳   retroactive.log 의 [ledger_rescope] 줄
단계    쪽마다 read · event frames · dry run · row refs · translate · withdrawal count · index lines of the rows ·
        screen atoms · partitions · withdraw atoms · insert atoms · index lines · commit · write · forget index lines
        read 줄 = 쪽 열쇠 칸 + 그 칸의 인덱스(없으면 «no index on it - each page sorts the table») + 계획
        withdrawal count 줄 = 원장 ref 인덱스 이름과 valid 여부(아니면 «missing or not valid … build it: <명령>») + 계획
박동    5 초마다: 지금 단계 · 몇 초째 · 그 실행 프로세스의 DB 연결마다 «자기 문장 중 / 누구(pid · 이름)를 기다림 / DB 밖에서 일함»
느림    2 초 넘게 도는 문장 한 줄(앞 400 자) · 끝날 때 한 줄
칸      ingestion_settings retroactive_debug(기본 true — 끄면 단계 줄만 꺼짐) · retroactive_slow_statement_seconds(기본 2, null 꺼짐)
```

**게이트**
```
시험     test_a_retranslate_says_its_stages_and_its_wait_pg.py 5 passed — 단계 전부 · 끄면 쪽 줄만 · 잡힌 잠금을 박동이 이름으로 · 박동이 터져도 끝까지 · 켜고 끈 답 같음
변이     m1 단계 하나 빠짐 · m2 박동 예외 안 잡음 · m3 박동이 연결을 안 말함 · m4 끄기 무시 · m5 조회마다 롤백 안 함 · m6 인덱스 이름 안 말함 — 여섯 다 그 칸 빨강
진짜     런처 넷 · hold 판 200 행 · 실행 START 에 원장 잠금 12 초:
         beat: page 1 · withdrawal count 5.0 s · 1 rows · db: pid … waiting Lock:relation on pid … (b_e2e_lock_holder, idle in transaction 5 s): LOCK TABLE ledger_events …
         원자 200 개 실행 전 · 잠금 판 뒤 · 빈 판 뒤 같음 · public 행 변화 0
기존     바뀐 자리를 지나는 시험 54 파일: not-pg 667 passed · pg 108 passed. 진 것 11 개는 기점에서도 같이 짐(워크트리에 table_config 없음 8 ·
         박스 선언 없음 2 · 다른 스키마의 같은 이름 표 reltuples 를 읽는 worlds 시험 1 — 그 시험은 assy_test 에 wafer_process 가 여러 스키마에 있으면 진다)
```

**재번역 비용 — 지금까지 잰 것** (109c09396, 이 박스 수)
```
행당      hold 판 1만 행: 프로파일 켜고 6.8~7.3 ms(DB 문장 5%). 운영 선언 판(박스 행을 읽기만으로 베낀 스크래치): 프로파일 없이
          wafer_process_recipe 3.3~3.6 ms(DB 10%) · lot_slot_wafer 3.8 ms · die_inspection 5.6~6.3 ms(DB 24% — 아래 쪽 열쇠)
          파이썬 몫의 대부분 = 분자마다 pandas 표를 다시 짓고 복사(event_frames · _partition_units · 칸 넣기 둘)
다툼      혼자 / 따라가기 · 그리드 저장 · 체인과 함께: 막힌 표본 0. 다시 번역은 대부분 «DB 쉼 · 파이썬 일함»
거두기    박스 원장(원자 238만)에 ref 인덱스 없음 -> 쪽마다 셈 · DELETE 가 원장 통째(1~4.5 s). 운영은 인덱스 있음(총괄 확인)
          복사본에 인덱스가 있으면 둘 다 탐: ref 1,000 개 셈 0.19~0.30 s · DELETE 0.07~0.49 s (없을 때 1.4~4.5 s)
쪽 열쇠   die_inspection 의 run_uid 에 인덱스 없음(박스 원본도) -> 쪽마다 11.7만 행 표 정렬 0.3~2.0 s. 표 선언 indexes 로 적을 자리 — 값은 안 채움
안 잰 것  운영 크기에서 쪽마다 EXPLAIN 둘이 더하는 초 · 운영의 «5 초에 1 개» 원인 — 이 로그가 운영에서 말해 줄 것
```

**사고 하나** — 운영 모양 판 재기에서 원장 영수증 255 행이 assy_test public.audit_logs 로 샜습니다(스크래치에 그 표가 없어서). 그 255 행만 지웠고 67 행으로 돌아왔습니다(앞 메시지).

**다음** — ① 파티션 ref 인덱스를 기동 · 인덱스 관리가 스스로 짓고 GET /admin/indexes 에(총괄 지시) ② 쪽마다 «missing or not valid» 줄은 이 착지의 withdrawal count 줄이 같은 판정 함수(ref_index_state)로 이미 말합니다 — 단계 줄을 끄면 안 나오니, 꺼도 남겨야 하면 말씀 주세요 ③ ff4eb2cf0 큐 1 고침 ④ 번역기 행당 비용의 안 셋 ⑤ 796f04605 ①④.

> **[구현자 B -> 총괄] 10-13 ① 착지 `17d8ea0d6` — 원장 ref 인덱스를 체인 워커가 기동 때 스스로 짓는다 · GET /admin/indexes 에 원장 줄 · 결함 두 줄은 늘 처음 한 번**

```
무엇     인덱스 관리의 선언 목록에 세상마다 원장 줄(source ledger · partitions · partitions_missing · state present/missing)
         짓기 = build_missing_indexes 그 칸 아래, 손 명령과 같은 빌더(파티션 하나씩 CONCURRENTLY · 붙임) — 체인 워커 기동 · 다시 읽기 때
         다시 번역: «ref 인덱스 missing or not valid» · «page key … has no index» 를 실행 처음 한 번, retroactive_debug 를 꺼도(같은 판정 함수)
게이트   인덱스 관리 시험 8 passed(파티션 셋에서 지운 인덱스: missing 3/3 · 짓기 끔은 이름만 · 짓기 켬은 파티션마다 한 줄 · present)
         다시 번역 시험 6 passed(결함 두 줄 한 번씩, 단계 줄 끈 채) · 변이 n1~n5 각 빨강
진짜     런처 넷 · 파티션 셋의 ref 인덱스를 지우고 띄움 -> 체인 워커 기동 직후 [Indexes] «3 of 3 partition(s) lack it» · 파티션마다 built · attached
         -> 라우트 원장 줄 present -> 그 뒤 다시 번역에 결함 줄 0 · public 행 변화 0
안 잰 것 운영 크기에서 파티션 하나 짓는 초
다음     ff4eb2cf0 큐 1 고침 -> 번역기 행당 비용 안 셋 -> 796f04605 ①④
```

> **[구현자 B -> 총괄] 10-13 큐 1 착지 `97617bf8e` — ff4eb2cf0 고침 셋 · 문서 · RELEASE_LOG · RUN.md 같은 커밋(가지 23 커밋을 한 착지로)**

```
6  derived_pages 쪽 = 파생 표의 row_id 범위(다음 N 행), 대기 조건은 그 안에서 — keyset_scan.iter_pages(ranged=True) 한 자리
   4M 같은 박스 · 기점(WHERE) 대 가지(범위), 가장 긴 문장 / 전체:
     앞 50 행 대기      2.42 s / 10.4 s   ->   0.016 s / 12.5 s
     고르게 1/1000     0.46 s / 2.1 s    ->   0.008 s / 12.9 s
     꼬리 50 행        0.59 s / 0.6 s    ->   0.007 s / 12.1 s
   대가: 대기가 드물어도 표를 쪽마다 지나 전체는 표 크기에 비례(4M 약 12 s). 칸: 3,000 행 · 꼬리 5 대기에서 문장마다 스캔 행 <= 쪽(EXPLAIN ANALYZE) — 범위 끈 변이 빨강
2  VALUES CAST 거둠 — 형이 다른 뷰는 묶음 실패 -> 키마다, 답 같음, 줄이 말함. 칸: DB 형 값(3)은 묶음 그대로 · 글 «3» 은 되물림 + 같은 답
3  dry · 미리보기 칸을 PG 로: 그 문장이 돌려준 part 1 행 수 [0, 0, 5](드라이 · 미리보기 · 적용) — losers 무시 변이 빨강
문서  CODE_MAP in_savepoint · _BIND_PARAM_RE 줄을 지금 코드로 · enrichment_rules ④-2 «write CAST(:x AS type)» · BACKFILL_GUIDE 쪽 시간 «기본 3 초 · 5 초 상한» ·
      cell_layer 주석 배수 «3.0-4.4x, 많아야 6.3x»(QA 수) · analysis 독스트링 «every board» 지움 · RUN.md 배포 뒤 줄(«:x::type» 뷰 탈락 -> CAST 로 고침)
시험  가지가 바꾼 시험 10 파일 두 모드 140 passed · 디버그 로그 · 인덱스 관리와 합친 트리에서 7 파일 101 passed
```
