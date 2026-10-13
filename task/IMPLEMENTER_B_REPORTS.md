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

> **[구현자 B -> 총괄] 10-13 번역기 안 셋 (109c09396 · fd550df13 · 7763dd6d0) — 짓기 전, 오늘 착지할 것과 그다음**

**아는 것** (이 박스 수 · 운영 주장 아님)
```
행당     프로파일 없이 3.3~6.3 ms(운영 모양 선언 판 소스 셋) · hold 판 프로파일 켜고 6.8~7.3 ms
몫       DB 문장 5~24 % · 나머지 파이썬. 파이썬의 큰 덩어리 = 분자마다 pandas 표를 다시 짓고 복사
         (event_frames 39 % · _partition_units 17 % · 칸 넣기 둘 20 %, hold 판 프로파일 기준)
DB 큰 것  쪽 열쇠 칸에 인덱스가 없는 소스(die_inspection run_uid)는 쪽마다 표 정렬 — 프로세스를 늘리면 그 정렬도 N 배
게이트 때 claim id  원자 id(uuid7)라 다시 번역마다 새로 찍힌다(같은 코드 두 번도 다름) — «id 를 뺀 원자 칸 전부 같음»으로 잰다
```

| 안 | 무엇 | 운영자 할 일 | 좋은 점 | 위험 |
|---|---|---|---|---|
| ㄱ 다시 번역을 프로세스 N 개로 (오늘) | 소급 자식 프로세스 문을 넓힌다: 실행 하나의 자식이 쪽 열쇠 범위를 N 조각으로 나눠(열쇠 값 경계 = 묶음이 안 쪼개짐) 같은 모듈의 «조각 자식» N-1 개를 띄우고 자기도 한 조각. 조각은 rescope 를 그 범위에만. 진행은 조각들의 수를 합쳐 한 줄 · 멈춤은 조각마다 실행 행을 읽어 다 멈춤 · 끝(DONE)은 부모 하나 · 표가 잃은 행 · 낡은 원자 거두기는 조각이 다 끝난 뒤 부모가 한 번 | ingestion_settings 한 칸(조각 수, 기본 = 코어 수의 절반, 4 를 넘지 않게) | 번역기 출력 계약을 안 건드림 — 파이썬이 99 % 라 거의 N 배 · 워터마크는 다시 번역이 안 움직임(그대로) | DB 쓰기 N 배(쪽 열쇠 인덱스 없는 소스는 정렬도 N 배 — 그 표 indexes 먼저) · 파티션 짓기 DDL 겹침(조각 띄우기 전 부모가 미리) · 걷기 풀(runtime/process_pool)은 A 의 파일이고 요청-시한 모양이라 안 맞음 |
| ㄴ 행당 비용 줄이기 (그다음) | 매퍼에 넘기는 모양(분자마다 pandas 표)은 그대로 두고, 쪽마다 한 번이면 되는 일을 올린다: 원천 행 ref · 사건 시각 칸을 쪽 표에 한 번에 넣고 분자는 그 조각만 · 행 단위 분자는 다시 자르지 않음 · 칸 읽기 한 번을 두 단계가 같이 씀 · 깊은 복사 없앰 | 없음 | 모든 소스 · 실시간 따라가기까지 같이 빨라짐 | 줄일 몫 어림 최대 2 배(프로파일 비율에서 셈, 안 잼) · 답 바이트 같음이 게이트 |
| ㄷ 원장 프로세스 (7763dd6d0, 그다음) | 감독 목록에 «ledger» 데몬 하나 — 원장 따라가기 · 센서스 · 원장 기동 단계 셋 · 원장 인덱스 짓기를 체인 워커에서 옮김. ㄱ 의 조각들이 나중엔 이 프로세스 밑으로 | 재기동 순서 한 줄 | 원장이 서거나 느려도 체인은 그대로 · 원장만 재기동 | 크기 큼 · 체인 쪽에 남는 원장 의존(아래) 정리가 796 ① 과 겹침 |

```
체인 워커의 원장 자리(코드로 셈, ingestion_worker.py)
  기동 단계 셋   _ensure_ledger_schema_sync · _restamp_moved_fingerprints_sync · 판정 189 단계
  고리 둘        run_ledger_followup(따라가기) · run_ledger_row_census(센서스) — 둘 다 체인 루프 옆 task
  인덱스 일      _start_index_work -> ensure_model_indexes(오늘부터 원장 ref 인덱스 줄 포함)
  따라가기 안    _retract_what_those_rows_fed(체인 지움 거두기 — 796 ① 이 체인 고리로 옮김)
  상태 말        _worker_note 의 ledger_followup.note() · 따라가기 멈춤 문장(FollowUpStopped)
크기      ㄱ 손댈 자리: backfill.rescope(열쇠 범위 칸) · 쪽 읽기 문장(범위) · 소급 실행 몸통(조각 띄우기 · 합치기) · retroactive_run(조각 모드) · 설정 칸 — 시간은 안 잼
내 추천   ㄱ 오늘 -> ㄴ -> ㄷ(796 ① 과 한 판). ㄱ 는 ledger_rescope 만(Re-translate 버튼 · whole-source). 앞으로 쓰는 ledger_backfill(커서 전진)은 안 나눔
여쭐 것   ① 조각 수 기본값 — «코어 수의 절반, 4 이하»로 해도 되는지(운영 코어 수 모름)
          ② ㄱ 의 조각 자식이 같은 소급 실행 행 하나를 나눠 쓰는 것(실행 줄 하나 · 진행 하나) — 화면에 조각마다 줄을 따로 보일 필요가 있는지
```

> **[구현자 B -> 총괄] 10-13 ㄱ 착지 9351a3580 — 원장 다시 번역 조각 N 개 + 검수 bdc08ec39 고칠 것 1~8 + 작은 ①**

**무엇이 바뀌었나**
```
조각      소스 전체 다시 번역 = 쪽 열쇠 «값» 경계로 N 조각 · 조각마다 자식 프로세스(admin.retroactive_run --slice)
          실행 행 하나(부모만 씀 — 5 초에 한 번과 조각이 끝날 때) · × = 실행 행으로 조각 전부
          조각이 죽으면 나머지 stdin 닫힘 -> 쪽 경계에서 멈춤 -> failed + 조각마다 행 수 · 상태 · 부모가 죽어도 같은 길
          한 조각으로 도는 때: 설정 1 · 쪽 열쇠 인덱스 없음(«… and the run goes in one slice» 줄) · 열쇠 NULL 행 · 뷰 · 실행 행 없는 실행
          컷: 한 값이 컷 둘을 걸치면 하나, 마지막 값에는 컷 없음(빈 조각 안 생김)
          설정 ingestion_settings "ledger_translate_slices"(없으면 코어 절반 · 4 이하) · 줄 «N slices (cores C)» · 조각 줄 앞 «[slice k/N pid P]»
검수 1~8   1 남이 짓는 파티션은 «left to it» · 파티션 하나 실패가 나머지를 안 세움 · «짓는 중» 판정 = db_waits.index_builds 하나(models._building 도 이것)
          2 원장 짓기는 다른 줄(_LEDGER_INDEX_LINE) · statement_timeout 0 · lock_timeout DDL_LOCK_TIMEOUT · 기다리는 동안 «waiting for … pid N (이름)» 줄 · /admin/indexes 원장 줄 building
          3 단계 줄은 실행 기록을 안 고침(쪽 경계 한 번)   4 끄기 시험이 EXPLAIN 을 셈   5 쪽 열쇠 인덱스 실행에 한 번
          6 뷰는 «declare» 줄 없음   7 박동은 그 실행 스레드가 쥔 연결만   8 시험 정리는 자기 스키마에 CONCURRENTLY 없이 · 시험 DDL 은 search_path 를 스크래치 하나로
작은 ①    접기 키 색인 판정이 search 종류를 안 침
문서      RUN.md 새 절 + 옛 두 절 낡은 줄 · RELEASE_LOG 새 항목 + 옛 두 항목 «고침» 칸 · CODE_MAP 넷
```

**잰 것** (박스 · 운영 주장 아님)
```
시험      착지 머리에서 비PG 111 passed · PG 34 passed(만진 파일과 그 seat 를 지나는 파일) — rebase 전 넓은 판 비PG 398 · PG 43
변이      17 개 모두 빨강: 고침마다 되돌림(q1 둘 · q2 둘 · q3~q7) · 조각 규칙 깨기(s1~s7) · 작은 ①(r1)
          처음 판에서 살아남은 셋은 시험을 고쳐 다시 빨강 — 원장 줄 둘이 겹쳐 지어지는 칸 · 원래 결함 줄 되돌리기 · 한 값이 컷 둘을 걸치는 판
실제 판    런처 넷 · hold 판 3000 행 · 스크래치 assy_b_slices_1013 · 착지 머리 9351a3580:
          N=1 · N=4 원자(id 뺀 칸 전부)+행 색인 같음 · 실행 몸통 9.1 s -> 6.1 s(조각 기동 약 3 s 포함)
          원장 잠금 중 × -> 네 조각 «stopped» 뒤 cancelled · 잠금 중 조각 2 taskkill -> failed + 문장 · 다시 돌리면 처음과 같은 답
          assy_retroactive 연결 남은 것 0 · public 행 변화 0
public    시험 정리 코드(이번 판 처음 것)가 assy_test public.idx_audit_recent_groups 를 지웠고, 지시대로 다시 지음 — public 선언 인덱스 47 -> 48/49
          남은 하나 idx_outbox_ledger_pending 은 public.database_outbox 에 ledger_state 칸이 없어 지을 수 없음(제 정리와 무관)
```

**모르는 것**
```
운영 크기에서 조각 N 개가 DB 를 얼마나 더 쓰나 · 어디서 DB 가 병목이 되나 — 안 잼
원장 짓기의 기다림 상한은 짓기가 «끝난 뒤» 오는 기다림이라, 오래 쥔 트랜잭션이 있으면 기동마다 그 파티션 짓기 시간을 버림(RUN.md 에 적음)
그리드 읽기의 검색 상태가 부르는 models._building 이 이제 질의 둘(현재 스키마 · index_builds) — 한 읽기에 왕복 하나 더, 안 잼
```
다음: ㄴ(분자마다 pandas 일 올리기 — 계약 그대로).

> **[구현자 B -> 총괄] 10-13 검수 9752e91f7 고침 착지 9b1624ecd (ㄴ 보다 앞, 한 커밋)**

```
1 쪽 열쇠 인덱스 판정 = models.orders_rows_by(btree · WHERE 없음 · 앞 칸이 열쇠) 한 함수
   두 자리가 부름: replay._key_index(선언 줄) · backfill._page_key_index(카탈로그 줄, models.catalogue_indexes)
   hash · gin · 부분 인덱스면 한 조각 + «has no index» 줄
2 원장 짓기 lock_timeout 0(statement_timeout 처럼) — 기다림은 끝날 때까지, 누구를 기다리는지는 파티션 · 상대마다 한 번
3 원자 같음 시험이 두 판 사이 원장(그 소스의 원자 · 행 색인)을 비움
4 RUN.md 되돌리기 = git revert 9b1624ecd 9351a3580 (이 보고 커밋에서 해시를 적음)
5 쪽 열쇠 NULL 행을 실행 끝(whole_source_tail — 두 길 공통)에서 셈: 결과 칸 rows_without_page_key · 실행 줄 · retroactive.log 한 줄
6 원장 짓기 시험은 시험마다 자기 스키마(<pytest 스키마>_lx) · 자기 파티션 · 원장 줄만 지음
낮  ledger_translate_slices 1~코어 수, 그 밖은 한 줄 + 기본값 · 설정 견본에 칸 · 컷은 값으로 견줌(1.0 · 1.00) ·
    자르기 전후 줄(«cutting … - counting its rows» · «… - cut in N s») · RUN.md 멈춤 문장(qab3_orphan_driver 인용) · 판 수를 착지 머리 것으로
안 한 것  _ledger_setup N+1 — 조각마다 제 프로세스라 하나씩은 피할 수 없음. 부모 안 두 번(한 조각으로 갈 때)만 남음, 안 고침
```

**잰 것** (박스)
```
시험      만진 파일 PG 21 passed(조각 · 인덱스) + 앞 판 PG 34 · 비PG 432 passed
변이      10 개 모두 빨강 — 처음 판에 살아남은 둘(상한 다시 걸기 · 매 번 말하기)은 시험이 3 월 파티션 기다림을 3 초 쥐게 고쳐 빨강
실제 판    9b1624ecd 앞의 로컬 커밋(내용 같음)으로 런처 넷 · hold 3000 행: N=1 · N=4 같은 답 · × cancelled · 조각 죽이기 failed + 문장 · 다시 같은 답 · public 행 변화 0
```

**5 번 판정에 대해 한 줄** — 한 프로세스도 NULL 쪽 열쇠 행을 «거절로 드러내지» 않습니다: 첫 쪽은 쪽 크기 1 행부터 가장 작은 열쇠를 읽고 다음 쪽은 `> after` 라 NULL 은 어느 쪽에도 안 들어옴(표 전체가 첫 쪽에 들 만큼 작을 때만 NULL 행이 읽혀 거절). 그래서 세는 자리를 두 길이 같이 지나는 꼬리에 두었습니다.

다음: ㄴ(행당 비용) — 첫 층은 짓고 쟀음(이벤트 프레임 26,917 개 · 소스 다섯 원자 같음, 한 행 소스 행당 약 25~28 % 줄임), 이 착지 위로 다시 올려 시험 · 착지.

> **[구현자 B -> 총괄] 10-13 ㄴ 착지 a08c95676 — 번역기의 분자마다 pandas 일을 쪽마다 한 번으로 (쓰는 원자 그대로)**

```
무엇   event_frame._event_frames: 분자 판정(거절 · 정체성 · 시각 · 행 ref · 사건 id)은 전과 같은 순서로 한 바퀴,
         그다음 엔진 칸 둘(원천 행 ref · 사건 시각)을 쪽 표에 한 번 넣고 분자는 그 행들만 자름(전: 분자마다 깊은 복사 + 칸 넣기 둘)
       roleframe._partition_units: 행 단위 소스의 한 행 분자는 사건 종류와 같은 길(얕은 복사)로 단위 하나
되돌리기 git revert a08c95676 -> 체인 워커 재기동 (RUN.md 의 그 줄에 이 커밋에서 적음)
```

**잰 것** (박스)
```
같은 답    운영 소스 다섯의 실제 쪽 18 개 · 이벤트 프레임 26,917 개(가운데 거절 분자 든 쪽 포함) 전후 피클 — 값 · 형 · 칸 순서 · 색인 형 · attrs 같음
          소스 다섯의 앞 3000 행을 전후로 다시 번역 — 원자(id 뺀 칸 전부) · 행 색인 같음
시험      사건 틀 계약 시험 하나 더(칸 · 형 · 빈 ref 없음 · attrs 제 것) · 변이 셋 빨강
          비PG 같은 실패 전후(94 + 오류 10, 이 나무에 라이브 설정 없음)
          PG 232 passed 8 failed — ㄴ 앞 코드(62a0b0307)에서 같은 파일 묶음을 같은 순서로 돌려도 같은 8 개 실패(집합 같음)
          그 8 중 3 개는 단독으로 돌리면 통과(2026_09 파티션 잔여 행 · 쪽 수 1 차이 — 앞 시험이 남긴 상태)
실제 판    런처 넷 · assy_test 스크래치 스키마 assy_b_slices_1013 · hold 3000 행: 조각 1 · 4 · × 취소 · 조각 죽이기 · 다시 — 원자 · 행 ref 첫 판과 같음, public 행 변화 0, 남은 연결 0
행당      박스 운영 모양 판(assy_b_translate), 프로파일 없는 두 판:
          wafer_process_recipe 3.52~3.53 -> 2.24~2.66 ms · lot_slot_wafer 3.20~3.38 -> 2.24~2.46 ms · die_inspection 5.94~6.09 -> 3.12~3.96 ms
```

**따라가기 시험 (메시지로 먼저 드림)** — test_the_ledger_follow_up_loses_nothing 은 main 에서 끝까지 돌리면 통과(948.78 s). 멈춤이 아니라 느림 — PG 시험 엔진이 NullPool 이라 drain 한 번 304 ms(풀 엔진 3 ms), 40 번 drain 에 outbox id 40 개 모두 다름(같은 사건을 다시 집지 않음).

**작은 일 993d17c31 → 459b2ae83 은 물음으로 세움** — 메시지로 드림: 오늘 그 칸이 비는 까닭은 결정 맵퍼가 target 과 이름이 같은 집계를 계산하고 버리기 때문(chain/enrichment/mapper.py 집계 루프의 `col not in target_fields`). 집계가 체인 층(서열 4)으로 쓰면 자동 확정(등록 안 된 이름 → 99)이 그 «아래»라 지시의 게이트 둘(빈 집계 뒤 자동 확정 · 자동 확정 뒤 집계)이 반대로 나옴. 안 셋과 추천(자동 확정 두 이름을 서열 3 으로)은 메시지에. allow_chain_trigger 가이드 문단은 써 두었고, 선언 맨 위 칸이 있으면 결정의 첫 규칙이 다른 규칙의 체인 쓰기를 받고(True) 없으면 안 받음(False) — 제품 함수(expand_declaration · _rule_accepts_event)로 확인.

다음: ㄷ(원장 프로세스 + 796 ①②④ + 번역 N 프로세스) 안 셋 — 지금 모양 전수부터.

> **[구현자 B -> 총괄] 10-13 3e5c9a69e 착지 4bb3b4d85 — decide 집계가 같은 이름의 확정 칸을 체인 층으로 채운다 · 빈 집계는 층을 안 쓰고 앞선 층을 거둔다**

**원인 가르기 (고치기 전, 시험 세상 실측)**
```
(c) 맞음   결정 맵퍼가 target 과 같은 이름의 집계를 계산하고 버림(enrichment/mapper.py 집계 루프의 `col not in target_fields`)
          같은 집계를 다른 이름으로 달면 'LOT-A, LOT-B' 가 차고 target 이름 쪽은 None, 그 칸의 체인 층 0 개
(b) 아님   파일이 그 칸에 None · '' 를 써도 층이 안 생김 — 그 뒤 자동 확정 값이 그대로 보임
(a) 아님   오늘은 체인이 그 칸에 층을 아예 안 만듦
```

**무엇**
```
맵퍼     집계는 target 이든 아니든 제 칸을 씀(체인 층 4). 빈 집계(crud.is_blank_value)는 안 쓰고,
         앞서 쓴 체인 층은 cell_layer.withdraw_source 로 거둠 — 지운 행 거두기가 닿는 같은 문, 아래 층이 드러남
         target 이 아닌 집계 칸도 같음 — 전에는 빈 집계가 «빈 체인 층»을 남겼음
순위표    그대로. 사람 0 이 보이고, 파일 이름 층 · 자동 확정(둘 다 99)은 비지 않은 집계 아래. 자동 확정은 여전히 층 없는 칸에만 씀
가이드    CONFIG_ROLLOUT_GUIDE ④: allow_chain_trigger 문단(선언 맨 위 칸 · Replay chain) + «한 칸에 셋이 쓸 때 무엇이 보이나»
되돌리기  git revert 4bb3b4d85 -> 체인 워커 재기동 (RUN.md 의 그 줄에 이 커밋에서 적음)
```

**잰 것**
```
시험      test_an_aggregation_fills_its_own_target_field_below_a_person 5 개 — sqlite 5 passed, 같은 시험을 PG 스크래치 스키마로 5 passed
          unique_concat · min · count 가 target 을 채움 / 사람 값이 다시 세도 남음 / 빈 집계 = 층 없음 · 큐에 있음(config.queue_predicate_condition) ·
          자동 확정의 «층 없는 칸만» 판정이 허락 / 값 -> 빈 = 층 거둠 · 큐로 돌아옴 / 파일 층이 있으면 순위표의 맨 위 층 값(파일 이름 층 · pipeline_parser 둘 다)
변이      셋 다 빨강 (target 다시 버림 · 빈 값을 층으로 씀 · 거두기 없음)
묶음      decide 관련 시험 파일 30 개 비PG 619 passed(1 실패는 기준 나무도 같음 — 저장소 위치 시험) · PG 32 passed
실제 판    런처 넷 · assy_test 스크래치 스키마 assy_b_agg_1013 · 원천 행은 감시 폴더 CSV:
          집계가 target 을 5.9 s 에 채움 · 빈 집계는 층 없음 · 사람 값이 다시 세도 남음 ·
          사람이 원천 값을 지우자 집계 층이 거둬짐(이력 X -> None, withdraw:chain_ingestion) ·
          체인이 본 적 없는 행을 Replay chain 하자 1.7 s 에 채움 · public 행 변화 0
```

**운영에서 달라 보일 것** — 소유자 운영에서 파일도 dt_inventory.dt_lot 을 쓰면, dt_log 에 랏이 있는 작업은 이제 집계 값이 파일 값을 가립니다(파일 층 이름이 파일명이라 99, 체인 4). 파일을 위로 두려면 그 표 table_config 의 source_priority — 순위표는 소유자 말대로 안 건드렸습니다.

**PG 8 실패 이름 (ㄴ 판 · ㄴ 앞 코드 판 같은 집합)**
```
test_a_recipe_walk_brings_the_measurements_other_wafers_made.py::test_a_recipe_walk_brings_the_measurements_other_wafers_made
test_a_recipe_walk_brings_the_measurements_other_wafers_made.py::test_the_recipe_step_is_cut_by_its_window_and_capped_by_its_limit
test_a_registration_may_carry_its_attributes_into_the_table.py::test_an_install_that_predates_attributes_is_widened_once      (단독 통과)
test_a_withdrawal_goes_out_as_collapsed_events.py::test_a_fold_carries_each_group_s_envelope_and_not_its_own_run               (단독 통과)
test_a_withdrawal_goes_out_as_collapsed_events.py::test_queued_withdrawal_events_fold_per_table_and_nothing_else_moves         (단독 통과)
test_ledger_l1_pg.py::test_the_live_door_writes_the_refusal_breakdown_to_the_registry_row
test_ledger_l1_pg.py::test_two_independent_refusals_are_counted_and_named_in_one_run
test_ledger_worlds_are_independent_and_meet_in_a_walk.py::test_every_live_world_follows_an_edit_and_one_switched_on_again_catches_up
```
단독 통과 셋의 묶음 판 사유: 2026_09 파티션에 앞 시험이 남긴 행(CheckViolation ck_ledger_objectless_has_no_payload) · 쪽 수 1 차이 둘. l1 둘은 «source … is not declared in shipped_ledger_…» (LedgerSetupError).

다음: ㄷ(원장 프로세스 + 796 ①②④ + 번역 N 프로세스) 안 셋.

> **[구현자 B -> 총괄] 10-13 ㄷ 짓기 전 안 셋 — 원장 프로세스(7763dd6d0) + 796 ① 체인 지움은 체인 고리 안 · ② 따라가기 묶어 번역 · ④ decide 옛 키 · 지운 행 키 + 번역 N 프로세스**

### 지금 모양 (코드로 읽음, chain/ingestion_worker.py)

체인 워커가 하는 원장 일은 다섯입니다.

| # | 하는 일 | 자리 |
|---|---|---|
| 1 | 시작 때 원장 스키마 보장 · 커서 지문 다시 찍기 | `_ensure_ledger_schema_sync` · `_restamp_moved_fingerprints_sync` |
| 2 | 원장 인덱스 짓기 줄 (시작 · 다시 읽기마다) | `_LEDGER_INDEX_LINE` |
| 3 | 원장 따라가기 · 원장 행 센서스 | `run_ledger_followup` · `run_ledger_row_census` |
| 4 | 체인 박동 줄의 따라가기 한 토막 | `ledger_followup.note()` |
| 5 | 지운 행이 먹인 칸 거두기 — 체인 결과인데 따라가기 배치 안 | `_drain_ledger_followup_sync` -> `_retract_what_those_rows_fed` |

- 1~4 는 원장 일이라 그대로 옮기면 됩니다. 체인 쪽에 남는 원장 의존은 5 하나입니다(grep 으로 셈).
- 따라가기는 사건을 하나씩 id 순으로 집습니다 — 한 바퀴에 사건 1 개.
- 고침 사건에는 옛 값이 없고, 묶음 지움 사건에는 행 id 만 있습니다. 지움 감사도 «행 삭제됨» 한 줄뿐이라 칸 값이 없습니다.
- 옛 값을 «출처 도장»으로 거두는 문은 이미 있습니다(`cell_layer.withdraw_by_origin`). 도장을 찍는 것은 조인 · 접기(fold_unit) · 복사(hold_copy 의 복사)이고, 안 찍는 것은 decide 두 반쪽 · 복사의 다시 세기입니다. 추적 맵퍼 넷(contrast_walk · ledger_v2_dt_job · lot_lineage · lot_slot_wafer)은 사실을 안 적어 «모름», 운영의 파일 맵퍼는 이 박스에서 셀 수 없습니다.

### 셋이 같은 것

- 런처 감독 목록에 «원장 프로세스» 하나(`run_ledger_worker.py`, 로그 ledger.log, 연결 이름 assy_ledger). 1~4 가 거기서 돕니다 — 같은 함수, 새 기제 없음.
- 5 는 체인 그룹 단계로 옮깁니다. 그룹에 지움 사건이 있으면 같은 `_retract_what_those_rows_fed` 를 체인이 부르고 `processed_chain` 을 찍습니다. 원장이 서도 체인 지움은 거둬집니다.
- 따라가기는 대기 사건을 id 순으로 여럿 집어, 표 · 소스마다 범위 값을 합쳐 한 번 번역합니다. 지움과 추가 · 고침이 섞이면 같은 종류가 이어진 덩어리끼리만 합쳐 순서를 지킵니다. 몇 개를 집을지는 쪽 시간 규칙(`pacing.page_seconds` 와 `keyset_scan` 의 쪽 크기 늘리기 · 줄이기)과 같은 자리입니다.
- 합친 범위 값이 크면 원장 프로세스가 자식 N 개로 나눠 번역합니다(소급 조각과 같은 자식 진입 문에 «값 목록» 칸을 넓힘). N 은 `ledger_translate_slices` 그대로.
- 통합 모드(uvicorn 단독)는 지금처럼 한 프로세스 안에서 두 루프가 돕니다. 멈춤(stop_line)과 설정 다시 읽기는 원장 프로세스에도 같은 함수로 닿습니다.

세 안은 ④(옛 키를 어디서 아나)에서만 갈립니다.

### 안 ㄱ — 고침 · 지움 사건이 옛 값을 싣는다 (추천)

- 무엇: crud 가 감사에 옛 값을 쓰는 바로 그 자리에서, 바뀐 칸의 옛 값을 고침 사건에 싣습니다. 지울 때는 crud 가 쥐고 있는 행의 칸 값을 지움 사건에 싣습니다. decide 는 «지금 키 ∪ 옛 키»를 다시 세고, 다시 셌더니 소스 행이 0 인 키는 파생 행을 지웁니다(그 지움 사건으로 원장이 엣지를 거둠). 지움 사건은 decide 의 다시 세기에만 닿습니다(5 와 같은 체인 자리).
- 운영자가 하는 일: 런처 재기동 한 번. 이미 낡은 요약은 «한 번 다시 세기» 명령 한 줄(RUN.md).
- 좋은 점: 사건이 자기 사실을 싣고 다녀 새 표가 없습니다. 출처 도장을 안 찍는 다른 종류(복사의 다시 세기 등)도 같은 칸을 읽을 수 있습니다.
- 위험: (1) 사건이 커집니다 — 바뀐 칸의 옛 값만이라 작다고 보지만 안 쟀습니다. (2) 지움 사건을 짓는 자리가 넷입니다(crud 둘 · ORM 하나 · 대기 사건을 다시 접는 `cell_layer` 하나, grep 으로 셈) — 넷 다 값을 들고 가야 하고, 접기에서 빠지면 옛 키를 조용히 잃습니다.
- 크기: 안 쟀습니다. 파일로는 런처 스펙 · 새 진입 파일 · 체인 워커 · followup · crud · database(사건 짓기) · cell_layer(접기) · decide 맵퍼 · 시험.

### 안 ㄴ — «소스 행 -> 키» 기억 표

- 무엇: decide 마다 «이 소스 행이 어느 키를 먹였나»를 표에 적고, 고침 · 지움 때 그 표에서 옛 키를 읽습니다.
- 운영자가 하는 일: ㄱ 과 같음 + 첫 기동 때 기억 표 채우기(소급).
- 좋은 점: 사건 모양을 안 바꿉니다. 옛 값을 못 싣는 길(다시 돌리기 · 접힌 사건)에서도 옛 키를 압니다.
- 위험: 새 표와 그 소급 — «바꾸기 비용»이 늘어납니다. 기억이 실제와 어긋나면 조용히 틀립니다. decide 가 아닌 종류는 따로 적어야 합니다.
- 크기: 안 쟀습니다. ㄱ 보다 큽니다.

### 안 ㄷ — 감사 기록에서 옛 값을 읽는다

- 무엇: 사건 모양은 그대로 두고, decide 가 고침 사건의 거래 id 로 감사 기록(이미 old · new 가 있음)을 물어 옛 키를 찾습니다. 지움 감사 한 줄에 행의 칸 값을 넓혀 적습니다.
- 운영자가 하는 일: ㄱ 과 같음.
- 좋은 점: 사건이 안 커지고, 감사가 이미 쓰는 자리를 넓히는 것뿐입니다.
- 위험: (1) 대기 사건을 다시 접는 `cell_layer` 가 새 거래 id 를 붙여 감사와 끊깁니다. (2) 체인 배치마다 감사 표 질의가 하나 늘어납니다(안 쟀음). (3) 감사가 지워지거나 밀리면 옛 키를 잃습니다.
- 크기: 안 쟀습니다. ㄱ 과 비슷하다고 봅니다.

### 추천과 여쭐 것

- 추천: 안 ㄱ. 사건이 자기 옛 값을 들고 다니면 체인 · 원장 어느 쪽이 늦게 읽어도 답이 같습니다.
- 여쭐 것 1: 여러 거래를 한 번에 번역할 때 영수증의 거래 id — (가) 거래마다 영수증 한 장(수는 묶음 전체) · (나) 한 장에 거래 id 목록. 타임라인이 무엇을 읽는지에 달렸습니다.
- 여쭐 것 2: 다시 셌더니 소스 행이 0 인 키의 파생 행 — 사람이 확정한 값이 있는 행도 지우나, 남기고 이름을 대나.
- 여쭐 것 3: ④ 를 decide 와 복사의 다시 세기에만 넓히나, 사실을 안 적은 맵퍼(«모름»)에도 같은 칸을 읽게 하나.

> **[구현자 B -> 총괄] 10-13 검수 a08c95676 나 착지 76ad487be — 한 행 분자도 이름 붙은 칸의 정규형 검사를 함**

```
무엇     roleframe._partition_units 가 한 행 지름길 «앞»에서 행마다 정렬 토큰(이름 붙은 칸의 정규형 JSON)을 지음
         -> Decimal · date · 시간대 없는 datetime 이 한 행 분자에서도 쪽을 멈춤(a08c95676 이전과 같음). 여러 행은 같은 토큰으로 정렬
게이트    test_a_named_cell_with_no_canonical_form_stops_the_page_whatever_its_row_count
           decimal · date · naive_datetime × 1 · 2 행 — 옛 지름길에서 6 빨강
           칸은 mat_type(recipe_id 는 다른 자리에서 멈춰 옛 코드에서도 초록 — 공허해서 바꿈)
         test_each_row_of_a_molecule_carries_its_own_row_ref — 두 행 분자, 변이 «분자 안 행 참조 뒤집기» 빨강
값       박스 · 미리보기 번역만(DB 없음) · 표본 행 소스 2,000 행 · 다섯 번씩 두 판
           옛 지름길 1.25-1.60 ms/행 · 검사 넣고 1.47-1.78 ms/행 — 행당 약 +0.2 ms (ㄴ 이 번 몫의 일부를 돌려줌)
시험     그 두 파일은 ㄷ 착지 직전 손댄 시험 판(163 passed)에 들어 있음
문서     RUN.md 제목과 RELEASE_LOG 에 잰 범위(실제 쪽 18 · 소스 다섯 앞 3,000 행) · RELEASE_LOG «고침» 줄 · S-64-c 갱신
         RUN.md 되돌리기 줄의 해시는 이 보고 커밋에서 채움
안 한 것  런처 실제 판 — 번역기 안의 한 함수라 안 돌렸음. 상설(착지 전 실제 프로세스) 위반이면 풀어 주실 때 돌립니다
```

> **[구현자 B -> 총괄] 10-13 ㄷ 착지 19d6da585 — 원장 일이 원장 프로세스로 · 지운 행 거두기는 체인 그룹 끝에서 · 따라가기는 사건 여럿을 한 번에 (7763dd6d0 · 796f04605 ①②)**

```
무엇     런처 자식 하나 더: Ledger Worker(run_ledger_worker.py · 로그 ledger.log · 연결 assy_ledger · 박동 ledger)
         원장 따라가기 · 원장 행 센서스 · 시작 때 원장 스키마 · 지문 · 원장 인덱스 줄 — 체인 워커의 함수를 그대로 ledger/worker.py 로 옮김
         체인 워커는 체인만. 지운 행이 먹인 칸 거두기는 체인 그룹 끝(성공 커밋 · 격리 커밋)에서 — 원장이 서도 거둬짐
         따라가기: 대기 사건을 id 순으로 행 수가 쪽 크기 규칙(PageSize)에 닿을 때까지 집어, 표마다 같은 종류 덩어리를 한 번 번역
           지움과 추가 · 고침은 섞지 않음(순서 지킴) · 덩어리에 추가가 있으면 «읽는 칸 안 바뀜» 건너뛰기 없음 · 덮은 거래마다 영수증
         체인 Pause 동안 따라가기 · 센서스가 새 묶음 · 소스를 안 집음(돌던 묶음은 끝까지, 상한 1000 행)
         다른 원장 프로세스가 살아 있으면 안 섬 — 체인의 같은 판정을 이름으로 넓힘(heartbeat.another_process_beats)
         서버 단독(uvicorn)이면 체인과 원장이 같은 프로세스 — 같은 스위치(ASSY_CHAIN_WORKER)
         걷기(ledger_subgraph) · main 의 컴파일 캐시 import 한 줄 — A 동의
뺀 것     큰 묶음 자식 N — 총괄 판정대로 이번 착지에 없음
stop_line 원장 일은 큐 화면에 «줄»로 안 그려짐(개요의 /runtime 루프 행뿐) — stop_line 그대로, Pause 만
되돌리기  git revert 19d6da585 -> 런처 재기동 (RUN.md 의 그 줄에 이 커밋에서 적음)
```

**잰 것**
```
게이트      test_the_ledger_follows_a_batch_of_events_behind_the_chain (PG) 4:
            묶음이 하나씩 따라간 것과 같은 원자 · 행 색인(읽는 표의 지움이 추가 사이에 있는 판) · 호출 수는 적음
            거래 셋을 접은 번역 → 거래마다 영수증, 수는 그 번역의 것 · Pause 동안 안 집음 · Resume 뒤 따라감
변이        넷 다 빨강 (한 묶음 한 사건 · 표마다 한 덩어리 · 첫 거래만 영수증 · Pause 안 물음)
시험        손댄 시험 비PG 162 passed · PG 79 passed · 1 failed(아래 세상 시험 — ㄴ 이전부터)
실제 판      런처 다섯 · assy_test 스크래치 assy_b_ledgerproc_1013 · hold 세상 · 원천 행은 감시 폴더 CSV:
            pg_stat_activity 에 assy_ledger 3 · 3000 행 따라감 · 따라가기 한 바퀴 «사건 3 개(3000 행) 4.8 s»
            원장 선언을 깨뜨려 세운 채: 체인 추가 2.2 s · 고침 1.7 s · 지움 거두기 0.5 s 에 공식 표까지
            Pause 12 s(선언 복구 상태) 동안 원장 대기 6 → 7 그대로, Resume 뒤 1.3 s 에 따라감
            따라가기가 쓴 원자 · 행 색인 = 소스 통째 다시 번역(3005, True)
            원장 프로세스를 죽이자 감독이 5.0 s 에 다시 띄움, 다음 행 따라감 · public 행 변화 0
운영 규격     원장 따라가기 1000 행 ≈ 1.6 s(위 한 바퀴 4.8 s / 3000 행, 박스 · 번역 + IO 합) — «체인 그룹 1000 행 ≤ 5 s» 안
            IO 몫만 따로는 안 잼(«≤ 1.3 s/1k» 는 이 수로 판정 못 함)
```

**다른 PG 실패** — 세상 시험 test_every_live_world_follows_an_edit_and_one_switched_on_again_catches_up 은 ㄴ 이전부터 같은 사유로 실패(보고 6e8815ee9 의 여덟 중 하나). 이주 시험 둘(test_an_index_build_cut_off… · test_the_migration_names_the_session…)은 한 판에서 «다른 세션(assy_server, idle in transaction)이 outbox 를 쥠»으로 실패, 다시 돌리자 가지 · main 둘 다 통과 — 환경.

다음: 가(decide 빈 집계 거두기를 워커 한 문으로) — 멈춤 동안 코드까지만, 시험 · 판은 풀어 주실 때. 그다음 다 · ④ 옛 키 ㄱ.

> **[구현자 B -> 총괄] 10-13 가 착지 33f5cdac3 — decide 집계가 제 확정 칸을 채움 · 빈 집계는 «이 규칙이 쓴 층»만 쓰기 뒤 워커의 한 문으로 거둠 · 백필도 체인 층 (bc9710454 가 · 가-1 ㄱ · 옛 백필 ㄱ) · 76ad487be 실제 판**

```
무엇     규칙 이름 찍기   rule_run.signed — 규칙이 낸 행(updates · 지도 메타 · 묶음 행 · 뒤 쪽)의 updated_by = 선언 이름. run_rule 한 자리
         맵퍼는 읽기만    빈 집계는 안 쓰고 아이템의 withdraw 에 칸 이름만
         거두기           쓰기 문 안, 그 묶음을 쓴 직후 _withdraw_blanks -> _withdraw_and_tell(cells=) -> cell_layer.withdraw_layers
                          고르기 cells_written_by: 그 칸의 맨 체인 층 중 updated_by 가 이 규칙인 것 + 옛 enrichment_backfill 층
                          거둔 행은 그 묶음의 그리드 메시지에 실음(쓰기가 바꾼 것 없으면 results 에 없어서) · 키만 남은 행 검사에도 넣음
         백필             chain_ingestion + decide 파생행 규칙 이름으로 씀 · 새 행만 · 거두는 것 없음
문서     mapper.py · backfill.py 머리말 · enrichment_rules.md · chain_ingestion_guide 두 곳 · CONFIG_ROLLOUT_GUIDE ④ · BACKFILL_GUIDE 표 ·
         CODE_MAP 넷 · RELEASE_LOG(되돌림 표시 걷고 새 본문, «화면에서»에 쓴이 = 규칙 이름 · 타임라인 색) · RUN.md 절
```

**잰 것**
```
게이트     test_a_blank_recount_takes_back_only_its_own_rules_layer 10 — sqlite 와 PG 스크래치 스키마 둘 다 통과
           채움 + 규칙 이름 · 사람 위 · 빈 집계 층 없음 · 빈 집계는 그 칸의 이 규칙 층만(같은 행 다른 칸 · 다른 행 같은 칸 남음) + 그리드 메시지
           조인 층 남음 · 마지막에 쓴 rule_b 값 남음 · 백필 값 -> 원천 지움 -> 다시 셈 -> 빈 칸 · 옛 enrichment_backfill 층 같이 거둠 ·
           키만 남은 행 지워짐 · 파일 층은 순위대로
변이       여덟 다 빨강 — 총괄 셋(행의 칸 전부 · 표 전체 행 · 다른 규칙 층) + 이름 안 찍음 · 거둔 행 껍데기 검사 빠짐 · 방송 빠짐 ·
           백필 옛 이름 · 옛 백필 층 안 거둠
손댄 자리   비PG 278 파일: 실패 61 = 기준 커밋(0b74ee529)에서도 따로 돌려 실패하는 57 + 옛 쓴이를 단언하던 넷(백필 2 · 소급 화면 2, 새 계약으로 고침)
           PG 30 파일 223 통과 · 5 실패 = fold-units 둘(고침: 씨앗의 옛 표시에 규칙 이름 — 지금 체인이 그렇게 씀) · 세상 시험(전부터) ·
           둘은 따로 돌리면 기준 · 가지 둘 다 통과(순서 잔여). 옮긴 뒤 핵심 284 통과
실제 판     런처 · assy_test 스크래치 assy_b_ga_1013 · 원천 행은 감시 폴더 CSV:
           채움 6.0 s(쓴이 enrichment_dedup:agt_rule) · 빈 집계 층 없음 · 사람 값 남음 · 빈 집계가 자기 층 거둠 0.2 s ·
           rule_b 가 마지막에 쓴 값 남음 · 소급 화면 백필이 체인 층 + 규칙 이름으로 씀, 원천 지우고 남은 행 고치자 0.5 s 에 거둠 ·
           Replay chain 1.9 s · chain_worker.log 에 [ChainRetract] … blank_rows= 줄 · public 0
76ad487be  같은 HEAD 로 원장 판(행 단위 소스 hc_official — 한 행 분자 길): 3000 행 따라감 · 원자 · 행 색인 == 통째 다시 번역(3005) ·
           원장 선 동안 체인 추가 · 고침 · 지움 거두기 · Pause · 다시 뜸 · public 0
```

**알릴 것**
```
게이트 문구  «원천 지움 -> 다시 셈»: 지움만으로는 decide 가 다시 안 셈 — 지움 사건 페이로드에 row_ids 만 있고 옛 키가 없음(탐침으로 확인, ④ 옛 키 ㄱ 의 일).
            그래서 시험 · 실제 판 둘 다 «원천 지움 + 남은 원천 행 고침»으로 다시 셈
한 번 다시 씀 착지 뒤 규칙이 처음 다시 쓰는 칸은 값이 같아도 층 줄을 한 번 다시 씀(쓴이가 바뀌어서). 보이는 값은 대개 그대로 — 단 같은 칸에 같은
            순위(4)의 괄호 층(조인 등)이 있으면 다시 쓴 쪽이 최신이 되어 한 번 바뀔 수 있음. 접기 첫 판 «표시한 행»이 그만큼 늚(박스 시험 11 -> 12). RUN.md 에 적음
로그 줄      새로 만든 행도 빈 집계면 묶음마다 «blank_rows=N groups=0 cells_withdrawn=0» 한 줄과 거두기 문 한 번(고를 것 0) — 결함은 아님.
            소유자 dt_lot 처럼 랏 없는 작업이 많으면 묶음마다 이 줄. 새 행을 빼는 것 · withdraw 를 스키마 칸으로 올리는 것은 안 함(지시 밖)
옛 층        이 착지 전 체인이 쓴 층(쓴이 chain_worker)은 그 집계가 비어도 안 거둬지고, 그 규칙이 값을 한 번 다시 쓴 뒤부터 — RUN.md
            한 칸을 decide 둘이 쓰면 빈 집계가 다른 decide 의 옛 백필 층도 거둠 — RUN.md
덤(소유자께) 파일 층 이름은 «들어온 파일의 이름»(directory_watcher 3521-3531, basename) — 파일 하나에 이름 하나라 열린 집합. 순위표(source_priority)는
            이름 -> 순위(crud.resolve_priority_map · get_source_priority)라 «파일 전부»를 한 칸으로 적을 자리가 없음.
            운영의 파일 층 이름 수는 모름 — 박스 사본 스키마 둘은 씨앗이라 1 · 2 개(규모를 말해 주지 못함), assy_test public 의 cell_sources 0 행
```

다음: 원장 프로세스 고침(fa5417c28) 여섯 -> 뷰 읽는 원장 소스 재기(짓지 않음).

> **[구현자 B -> 총괄] 10-13 원장 프로세스 고침 착지 76d1cd698 (fa5417c28 여섯) · 가 후속 0396c73cb · ⚠️ 사고: 33f5cdac3 이 d430d5a1d 문서 줄을 되돌렸음 → 0a6f5fff7 로 되살림**

```
고침     1 체인 워커가 첫 박동 뒤 박동 한 주기(60 s)에 «ledger» 박동이 없으면 한 줄(어느 프로세스 박동이든 — 서버 단독은 한 프로세스)
         2 그룹의 지운 행을 성공 · 격리 커밋 «전»에 읽음(_deleted_rows_of) — 커밋 뒤 사건을 다시 안 읽음
         3 큐 화면 × 로 치운 지움(set_aside 쪽마다 커밋 뒤) · 깊이 상한 거절 지움(FAILED 표시 커밋 뒤)도 같은 거두기
         4 거두기 실패에 db.rollback()
         5 따라가기는 id · 행 수(payload 의 row_count · row_id)만 먼저, payload 는 예산 안 사건만
         6 devenv up 이 런처 자식 목록(launcher_specs)에서 체인 · 원장을 받아 띄움 — 감시기 · 스케줄러는 그대로 뺌
         RUN.md 세 줄(런처 전체 재기동 · 원장만 세우는 법 없음 · 상한 1000 행) · RELEASE_LOG 원장 항목 밑 «고침» 줄
시험     test_the_chain_withdraws_every_deletion_it_ends 6 + 원장 묶음 시험의 payload 칸 · 변이 일곱 다 빨강(자리마다 하나)
         손댄 자리 비PG 645 통과 + 격리 스택 시험(up = {api, chain, ledger} 로 고침) 35 통과 · PG 179 통과 · 4 실패:
         셋은 같은 시간대에 기준(0396c73cb)에서도 실패 · 뒤에 두 번씩 다시 돌리자 양쪽 다 통과(흔들림, 원인은 안 잼) · 하나는 따로 돌리면 통과
         런처 판은 안 돌림(말씀대로 시험 칸 · 변이만)
가 후속   0396c73cb — 말씀하신 셋 반영(빈 집계가 고를 층 없으면 문 · 줄 없음 · RELEASE_LOG 에 첫 fold-units 판의 processed 늘어남)
```

**⚠️ 사고와 되살림**
```
무엇     가 착지 33f5cdac3 이 총괄 d430d5a1d(오늘 밤 병합들의 문서 동기화)의 RUN.md 다섯 줄 · CODE_MAP 두 행(walk/main.js · start_baskets.js)을 옛것으로 되돌렸음
까닭     wip 를 한 커밋으로 접을 때 «git reset --soft origin/main» 을 썼는데, 같은 저장소의 다른 나무가 fetch 해서 공유 참조 origin/main 이
         그새 d430d5a1d 로 앞당겨져 있었음 — 제 나무(밑 4b1f2f29f)의 옛 문서가 d430d5a1d 위에 그대로 커밋됨. 코드 파일은 그 사이 바뀐 것이 없어 영향 없음
되살림   0a6f5fff7 — d430d5a1d 의 줄을 다시 얹음. 자동 인덱스 «볼 것» 로그 줄만은 그 뒤 그리드 풀 착지가 이미 새로 고쳐 두어 지금 것을 둠.
         원장 프로세스 되돌리기 줄은 d430d5a1d 의 «f620962c7 먼저»와 76d1cd698 해시를 같이 적음
확인     나 76ad487be · ㄷ 19d6da585 · 0396c73cb · 76d1cd698 은 부모가 제 직전 커밋이거나 merge-base 로 접어 같은 일 없음(지운 줄 전부 제 것)
막음     접기는 merge-base 로만(기억에 남김) · 푸시 전 «git diff origin/main --stat» 에 제 파일만 · RUN.md 는 줄 끝을 건드리지 않고 글자 그대로 바꿈
```

다음: 뷰 읽는 원장 소스 재기(짓지 않음) — 18766 박스 선언의 원장 소스 15 개 중 뷰를 읽는 일곱(process_param_num_measure · process_param_txt_measure ·
void_observation · dt_transfer · bonded_from · lot_slot_move · bw_dt_seat), 거절은 setup_bundle 의 relation_not_a_row_table(총괄 f3bc02f6e · da3fa7493,
소유자 09-25 «운영은 뷰를 안 씀 · 그냥 빼라», 착지 c193986a8).

> **[구현자 B -> 총괄] 10-13 재기만 — 뷰를 읽는 원장 소스 일곱이 원자를 안 내는 까닭 · 읽게 하려면 · 간소화와 · 안 셋 (짓지 않음)**

**① 거절 자리와 사유**
```
코드     server/ledger/setup_bundle.py — 소스의 relation 이 «row_id 가 있는 표»(reads_a_row_table: 카탈로그 kind 가 table 이고 row_id 칸)가 아니면
         그 소스만 떨어뜨림(나머지는 섬). 문구 «source 'X' reads 'Y', which is not a table that has row_id (view); a ledger source must read
         a table that has row_id» · 코드 relation_not_a_row_table
판정     총괄 f3bc02f6e · da3fa7493, 소유자 09-25 «운영은 뷰를 안 씀 · 백필 없이 그냥 빼라 · 있는 그대로» — 착지 c193986a8
         (뷰 따라가기 기제 · 샘플의 뷰 소스 아홉 · create_*_view 스크립트 여섯을 지움)
박스     18766 선언(dm_root2) 소스 15 → 제품 로더(ledger.config.load)가 8 만 세움, 뷰를 읽는 일곱이 떨어짐:
         process_param_num_measure · process_param_txt_measure · void_observation · dt_transfer · bonded_from · lot_slot_move · bw_dt_seat
         지금 샘플엔 이 일곱이 없음(c193986a8 이 지움) — 이 박스 선언은 09-25 전 것
```

**뷰 일곱이 하는 일**(박스 table_config 의 주석)
```
거르기만    process_param_num / _txt   process_param 에서 value / value_text 가 빈 행 빼기(빈 숫자 칸이 NaN 이 되어서)
           dt_log_transferable        dt_log 에서 core_wafer(와 event_time)가 빈 행 빼기
           bonding_die_from_core      bonding_core_die 에서 core wafer 를 못 찾은 행 빼기
계산       void_obs_observed          void_obs 와 inspection_run 을 run_uid 로 조인(검사 시각)
           bonding_core_die           dt_log 행을 붙인 다이 하나에 한 행으로 접기(DISTINCT)
           lot_slot_move              lot_event 두 행을 웨이퍼로 짝짓고 양방향을 합치기(배열 펼치기)
```

**② 뷰를 읽게 하려면 — c193986a8 이 지운 것을 되살리는 일**
```
행 id      원자 · 행 색인이 (relation, row_id)로 행을 가리킴. 일곱 중 넷(void_obs_observed · bonding_* 둘 · lot_slot_move)은 row_id 칸이 없고,
           조인 · 접기 · 짝짓기 뷰는 «밑 행 하나»가 없음
커서       쪽마다 뷰 질의 전체가 돎 — 세기도 같음(backfill 의 «a view's count runs its whole query»)
따라가기    뷰에는 outbox 사건이 없음 → 밑 표 사건을 뷰 소스로 잇는 길(pg_depend 걷기 · view_followers_of, 지워짐)이 필요하고,
           밑 행 하나가 뷰 행 여럿에 닿는 조인 · 합치기는 다시 번역할 범위를 키로 넓혀야 함
지움 거두기 밑 행이 지워지면 어느 뷰 행이었는지 — row_id 가 없으면 못 찾음
```

**③ 간소화(read 은퇴)와**
```
간소화 소스 = {table, attributes, sentences(when)} · 신원 · 순서 · 커서는 «표의 유일 키» 기본값 — 뷰엔 유일 키 · 색인이 없어 기본값이 안 섬
오늘의 거르기 read.exclude_when({"column": c, "blank": true})은 간소화에서 문장 when 으로 감 — 거르기 뷰는 그대로 옮겨짐
뷰 따라가기 정보를 적던 자리(read)가 은퇴 — 뷰 소스를 되살리는 안은 간소화와 정면으로 부딪힘
```

**안 셋**
```
ㄱ (추천) 뷰를 «선언»으로 옮김 — 원장은 표만 읽음
   하는 일    거르기 넷: 밑 표를 읽고 exclude_when(간소화 뒤엔 문장 when) — process_param + {value 빈 칸} / {value_text 빈 칸},
                        dt_log + {core_wafer 빈 칸}·{event_time 빈 칸}, (아래 bonding 표) + {core_wafer 빈 칸}
             계산 셋: 체인이 표로 씀 — void_obs 에 선언 조인(inspection_run 의 시각, run_uid) · bonding_core_die 는 decide(키 base_id · bx · by)로
                        파생 표 · lot_slot_move 는 짝짓기 · 합치기라 조인 · decide 로 안 됨 → 맵퍼가 표를 씀
   운영자     chain_rules.json 에 조인 하나 · decide 하나 · 맵퍼 규칙 하나, ledger_config 소스 일곱의 relation 을 밑 표 · 새 표로 + 거르기
   좋은 점    «원장 선언은 국소적 · 무계산 — 그 밖은 체인이 표에 쓴다»와 같음 · 실시간 전파 · 지움 거두기 · 행 색인 그대로 · 간소화와 안 부딪힘 ·
             제품 코드 0(맵퍼 하나 빼고)
   위험       lot_slot_move 맵퍼는 새 코드(소유자 맵퍼 자리) · 파생 표를 한 번 채우는 소급(박스 주석 수: bonding_core_die 371,593 행 ·
             void_obs 103,729 행 — 박스) · decide 가 DISTINCT 접기와 같은 답을 내는지 안 쟀다
   크기       선언 셋 + 소스 일곱 고침 + 맵퍼 하나 — 코드 줄 수 안 쟀다
ㄴ 뷰 소스를 되살림(c193986a8 이전)
   소유자 09-25 판정을 뒤집는 안 — 제가 고를 수 없음. 지운 기제(pg_depend 따라가기 · 행 id 없는 소스 갈래) 복원, 행 id 없는 넷은 그래도 안 됨,
   간소화와 부딪힘. 크기 큼(c193986a8 이 followup.py 에서만 251 줄 지움)
ㄷ 박스만 지금 샘플로
   18766 선언을 지금 샘플(뷰 소스 없음)로 — 거절은 사라지지만 계측 소스 자체가 없어져 «계측 항목에서 걸어도 안 나옴»은 그대로. 박스 상태 답이지 구조 답 아님
```

**여쭐 것**
```
1  운영에 뷰가 정말 없나(소유자 09-25 말씀) — 있으면 운영의 «계측 항목에서 안 나옴»도 같은 원인, 없으면 운영 원인은 따로(운영 선언을 안 봐 모름)
2  ㄱ 이면 lot_slot_move 같은 «짝짓기» 뷰를 맵퍼로 옮겨도 되나
3  박스 선언을 ㄱ 로 옮기는 일은 누가(응용 세션 박스)
```

> **[구현자 B -> 총괄] 10-14 행 색인 키 ㄷ 착지 e30c85c9c — 큰 묶음이 넘치는 행 색인 키는 그 소스의 이름 댄 거절 (사건 실패 아님)**

```
무엇     store 의 행 색인 쓰기가 DB 의 program_limit_exceeded 를 RowRefKeyTooLong(DB 문장)으로 올림 → 따라가기는 그 소스를 {"refused": 문장} 으로
         두고 그 행들은 안 씀 · 사건은 done(실패 아님) · 같은 사건의 다른 소스는 그대로. ledger.log 에 소스 이름 댄 한 줄(1 · 10 · 100 번째)
         키는 그대로(이주 없음) — 간소화가 group_by 소스를 거절하므로
시험     진짜 번역 → 진짜 행 색인 쓰기(PG)를 지나게 claim ref 를 «행 수천 개 묶음» 모양으로 지어 — 소스 거절 · 실패 사건 0 · 한 줄. 변이 둘 빨강.
         원장 쓰기 · 따라가기 파일 82 통과(PG · 비PG)
알릴 것  이 박스 PG 의 오류 문장은 한국어이고 54000 에는 «8191 바이트» 쪽 문장도 있어 문장으로는 못 가림 — 그래서 «행 색인 쓰기에서 난 것»으로 가림
         착지 전에 이 까닭으로 failed 가 된 사건은 그대로 failed — RUN.md 에 --requeue-failed 로 다시 넣으면 거절 한 줄로 끝난다고 적음
         런처 판은 안 돌림
```

다음: 원장 선언 간소화 — 짓기 전 전수 표(오늘 문법 칸 → 짧은 꼴 칸 | 뺌)와 «어긋나는 칸»을 수와 함께 먼저 올립니다.

> **[구현자 B -> 총괄] 10-14 원장 선언 간소화 — 짓기 전 표: 오늘 문법 칸 → 짧은 꼴 칸 | 뺌, 소스별 옮김 판정, 어긋나는 칸과 수 (짓지 않음)**

**칸 전수**(setup_bundle 의 `_validate_*` · `exact(required/optional)` 23 자리 + 바인딩 세 종류, AST 로 셈)
```
번들      setup_version                       -> 7
          vocabulary · entities               -> 그대로
          virtual_joins                       -> 뺌 — 비면 버림 · 규칙 있으면 이름 대어 거절
소스      relation                            -> table
          status                              -> status
          read.unit · identity · order_by     -> 뺌 — 기본값(표의 가장 짧은 유일 키 · row). 기본과 다르면 거절
          read.group_by · cursor              -> 뺌 — group_by 는 거절 · cursor 는 오늘도 무시
          read.occurred_at {column · timezone · format} -> 문장 occurred_at 객체 {column · timezone · format}
          read.occurred_at.basis              -> 뺌 — 엣지 시각이 없으면 저장 시각 자동
          read.registration_probe             -> 뺌
          read.exclude_when [{column · blank}] -> 문장마다 when 의 «빈 칸 아님»
          read.exclude_when [{when: {c: v}}]   -> 문장마다 when {c: {"not": v}} — 한 칸일 때만, 여러 칸(= 또는)은 거절
          map.implementation_id · version · unit -> 뺌 — declarative-role 기본 · 다르면 거절
bind      mappings.<이름>                      -> sentences[{sentence: <이름>}] (원자 신원 그대로)
          mapping.predicate · when            -> predicate · when
          mapping.bind.<역할>                   -> 그 역할 칸(subject · target · value · occurred_at · 수식어)
          entities.<타입>.attributes            -> 소스 attributes.<타입>
바인딩    column {column}                      -> "칸" 글
          column {column · timezone · format}  -> {"column", "timezone", "format"}
          constant {value}                     -> {"const": 값}
          entity {entity_type · keys}          -> {"node": 타입, "keys": {키: 값}}
          entity {entity_type: {kind: column}} -> {"node": {"column": 칸}, "keys": …}
          entity attributes                    -> 소스 attributes.<타입> — 한 문장에 같은 타입 노드가 둘이면 거절
          approval_status · binding_origin · suggestion_reason -> 뺌(오늘도 무시)
빈 칸     0
```

**소스별 판정**(저장소의 선언 셋 — 견본 · transfer_explorer 견본 · 시험 v5_setup)
```
견본 dt_job              read.occurred_at = 저장 시각(basis ingested) 인데 엣지는 event_time 을 묶음 — 짧은 꼴의 «사건 시각 = 엣지 시각»과 다름
     lot_event (retired) group_by · 사용자 맵퍼 lot-event-role · identity · order_by 기본과 다름
     transfer_event      옮김(시간대만 옮김)
     die_inspection      옮김(시간대만 옮김)
     wafer_process_recipe identity · order_by = row_id (기본 = 유일 키 proc_id)
     lot_slot_wafer      옮김(시간대만 옮김)
     lot_lineage         order_by = event_time + lot_lineage_key (기본 = lot_lineage_key)
transfer_explorer dt_log group_by · identity · order_by 기본과 다름 · virtual_joins 규칙 1
v5_setup (시험)          견본과 같은 꼴 + registration_probe(dt_job · lot_event)
```

**어긋나는 칸**(짓기 «전»에 수와 함께)
```
1 시간대   견본 활성 6 소스 전부 시간대를 read.occurred_at 에만 적고 사건 엣지 바인딩엔 없음.
           짧은 꼴은 시간대를 문장 occurred_at 객체에 싣는다 -> 그대로 펼치면 바인딩에 timezone 이 생겨 «펼친 번들 ≠ 오늘 번들(해시)»
           원자 값은 같을 것으로 보이나 안 쟀다. 번들 해시(setup_snapshot_hash)가 원자 행에 실림 — 해시가 바뀌면 다시 번역이 도는지 안 쟀다
2 순서     ref 는 order_by 값으로, 사건 id 는 identity 로 지어짐(event_frame) -> 기본 키로 바꾸면 원자 신원이 바뀜 = 그 소스 전부 다시 번역(소급)
           견본 활성 6 중 2(wafer_process_recipe · lot_lineage)
3 시각 기준 dt_job 의 분자 시각 = 저장 시각, 엣지 = event_time -> 엣지 시각으로 바꾸면 사건 id 가 바뀜 = 소급. 견본 활성 6 중 1
4 은퇴 소스 lot_event(retired)는 group_by · 사용자 맵퍼라 «못 옮김» -> «하나라도 못 옮기면 파일을 안 쓴다»에 걸려 견본 파일이 통째로 안 옮겨짐
운영 수     운영 선언은 못 봐 소스 · 행 수 모름
```

**안 셋**
```
ㄱ (추천) 같은 번들로 펼치는 규칙을 둠 + 바뀌는 것만 거절
   1 시간대: 펼칠 때 문장들의 occurred_at 이 한 {column · timezone} 이면 그 시간대를 read.occurred_at 으로 올리고 바인딩에선 뺌 — 오늘 견본 꼴이 그대로 나옴
     (오늘 바인딩에 시간대가 따로 적힌 선언은 이 규칙으로 안 돌아옴 — 저장소 선언에선 0, 변환기가 그런 소스를 이름 대어 거절)
   2 · 3 순서 · 시각 기준이 기본과 다른 소스는 거절 + 다음 행동(«그 소스를 다시 번역할 각오로 순서를 지우거나, 그대로 둠»)
   4 은퇴 소스는 옮기지 않고 «은퇴 소스 N 개는 짧은 꼴에서 지움»으로 말함(번역하는 것이 없음) — 지우기가 싫으면 거절로
   운영자: 변환 명령 dry-run -> 거절 목록 보고 그 소스만 손봄 -> --apply
   좋은 점: 옮겨지는 소스는 원자 · 해시 그대로(다시 돌 것 0)  위험: 견본에서도 2~3 소스는 손으로 정해야 함  크기: 안 쟀다
ㄴ 바뀌는 것도 옮기고 «다시 번역할 소스»로 말함
   순서 · 시각 기준이 다른 소스도 짧은 꼴로 옮기고, dry-run 에 «이 소스는 전부 다시 번역 — N 행»을 적음, --apply 가 그 소스의 다시 번역을 큐에 넣음
   좋은 점: 견본이 한 번에 옮겨짐  위험: 운영 크기에서 그 소급이 얼마인지 모름(운영 선언 · 행 수를 못 봄)  크기: 안 쟀다
ㄷ 짧은 꼴에 «순서» 칸 하나를 남김
   identity · order_by 를 소스 칸 하나(예 "order": [...])로 남겨 기본과 다른 소스도 신원 그대로 옮김 — 시각 기준도 같은 식
   좋은 점: 소급 0 · 거절 0  위험: 소유자 «read 관련 다 빼고»와 어긋남(소유자께 여쭐 일)  크기: 안 쟀다
```

**여쭐 것**
```
1 ㄱ · ㄴ · ㄷ 중 어느 것(소유자 몫이면 그대로 올려 주세요)
2 «하나라도 못 옮기면 파일을 안 쓴다» — 은퇴 소스는 예외로 지워도 되나
3 번들 해시가 바뀌면 다시 번역이 도는지 — 짓기 전에 박스에서 재 볼까요(안 쟀다)
```

> **[구현자 B -> 총괄] 10-14 옛 키 착지 d3c143d45 — decide 가 원천 행이 떠난 키를 다시 세고, 원천 행이 안 남은 키의 행은 사람 값까지 지운다 (총괄 옛 키 ㄱ)**

```
무엇     사건이 옛 값을 싣는다 — 편집은 바뀐 칸(ORM 속성 이력, 안 읽힌 값은 뺌 · 모름 ≠ 빈칸), 지움은 모든 칸(지움 문 셋: 그리드 · 맵 purge · ORM)
         규칙 칸 allow_delete_trigger(기본 꺼짐) — 규칙을 고르는 자리 전부가 좌석 wakes 하나를 물음. 묶기(group_id)는 fires 그대로
         decide dedup 규칙은 켬 · 복사는 끔(지운 원천 행 층 거두기 + 대상 EDIT 로 이미 맞음 — PG 게이트 칸으로 잼)
         decide 는 떠난 키를 같이 셈, 원천 행 0 인 떠난 키는 gone -> 워커가 쓰기 뒤 그리드 지움 문으로 지움(이력 chain_no_source_rows),
         사람 층이 있던 행은 키를 대어 한 줄
         판정 자리 둘(지운 행 거두기 · purge 문 독스트링)과 CODE_MAP 에 «뒤집음이 아니라 이 칸으로 넓힘»
총괄 판정  체인이 지운 행의 DELETE = 체인 사건 — 이미 그렇게 돎: 쓰기 블록의 체인 채널을 달고, 업서트와 같은 한 자리(_rule_accepts_event)가 채널로 읽음
         (출처 낱말 batch_delete 는 그 자리에서 안 읽힘). 껍데기 지움도 같음. 제품 줄 0 · 게이트 칸 하나 + 껍데기 시험에 채널 단언 · 변이 하나 빨강
시험     게이트 14 칸 + 대기열 칸 + 껍데기 시험 채널 단언. 변이 11 빨강
         비PG 전체: 실패 144 · 오류 10 은 main 나무에서도 같음(워크트리에 없는 파일). 제 것 둘은 고침(축 수 24->25 · 훅 철자)
         체인 · 원장 PG 41 파일: 245 통과 · 6 실패 — 다른 레인 PG 판과 겹친 판, 따로 다시 돌려 6 다 통과(main 나무는 같은 파일에서 다른 3 실패)
박스 판  (원천 1,000 행 · decide 하나 · 실제 런처 · 박스 판 운영 주장 아님) 전 3 판 / 후 4 판 + 착지 머리 1 판
         같은 키 편집 그룹 평균 250 -> 266 ms(+6%, 관문 10% 안) · 착지 머리 234 ms
         키 바꿈 958 -> 981 ms(착지 머리 891) · 지움은 이제 돎 ~350 ms
         파생 행: 키 바꿈 뒤 1,050 -> 1,000 · 다 지운 뒤 1,050 -> 0
         사건 크기(1,000 행): 같은 키 40 -> 61 KB · 지움 40 -> 112 KB
알릴 것  1 main 이 76d1cd698(제 착지)부터 빨강이던 시험 하나를 같이 고침 — test_a_map_purge_is_visible_to_the_outbox 의 글자 칸이
           _deleted_rows_of 의 DELETE 철자를 셌음. 이제 «묻는 자리 둘»을 이름으로 셈
         2 A 의 impl-expr 이 먼저 착지 — rebase 때 숨은 count 를 A 정규형 {"expression": "Count()"} 로(A 와 합의한 한 곳)
         3 감사 «지움 이력 줄»은 값 없이 «행 삭제됨». 사람 값은 그 사람 편집의 이력 줄에 남음
         4 착지 전에 떠난 옛 키 행은 소급으로도 안 지워짐 — RUN.md 에 «파생 표 그리드에서 지움»
         5 맵 purge(dt_map 대치)의 사건 크기는 안 잼 — 지움마다 행 값 전부가 실림
런처     응용께 25 분 + 5 분 받아 씀, 둘 다 내림. 스크래치 스키마 지움, public 행 변화 없음(판마다 전후 대조)
```

다음: 큐에 남은 것 — 원장 선언 간소화(소유자 결정 대기). 결정 오기 전엔 정리(남은 스크래치 스키마 · 워크트리)를 하겠습니다.

> **[구현자 B -> 총괄] 10-14 옛 키 다시 착지 4abf68886 — NO-GO 다섯 · GO-WITH-FIXES 넷 · e 고침 얹어 한 커밋 (첫 착지 d3c143d45 · 되돌림 4d6c7c184)**

```
고친 것   1 지울지는 파생 행의 정체성 칸으로 원천을 다시 물음(넓은 판단키) · 2 남의 층 있으면 남기고 한 줄 · 3 require 는 지운 행을 옛 값으로
          4 표기 접기(PG) · 거두기 접기도 옛 값 · 5 지우기 실패 = 그룹 실패 -> 다시 돎
          GWF 1 키 철자 한 자리(_clean_key: crud.key_part -> clean_str_value) — 배치 키 · 떠난 키 · 다시 센 답
          GWF 3 거두기 접기 옛 값 · GWF 4 제 층을 쓴 이 이름으로 접어 견줌 · 덤 _rules_for_group 을 wakes 로
          e 표기 접기 PG 낱행 사건이 행을 이름 표로 읽음(칸 이름 t)
시험      게이트 47 + 건너뜀 2(SQLite 시각 키 · 접기) — SQLite · PG 두 판. 변이 19 빨강(전 11 · NO-GO 5 · GWF 3, 각 제 칸)
          비PG 전체: main 에 없는 실패 0 (127 실패 · 16 오류 — 워크트리에 없는 파일)
          체인 · 원장 PG 41 + 게이트 + 표기 접기: 286 통과 · 6 실패(한 세션) -> 따로 다시 돌려 3 남음:
            거두기 접기 둘 = main 나무도 같은 순서(슬롯 파일 뒤)에서 같은 빨강, 그 파일만 돌리면 통과(순서 의존, 이 변경 아님)
            원장 묶음 칸 하나 = main 에서도 그 파일이 따로 빨강(흔들림)
박스 판   이 머리로 전후 번갈아 3 판씩(박스, 운영 주장 아님): 같은 키 250·234·235 -> 250·250·250 ms ·
          키 바꿈 829·812·828 -> 906·875·922 ms(+9 %, RELEASE_LOG «바뀐 동작»에) · 지움 이제 돎 406~422 ms ·
          파생 행 키 바꿈 뒤 1,050 -> 1,000 · 다 지운 뒤 1,050 -> 0 · public 행 변화 없음
RUN.md    ⚰️ 되돌림 절 자리에 새 절 — main 5,944 -> 5,971 줄(+38 -11), 한 벌. «안 하는 것» 넷
알릴 것   A 의 63c747046(다시 세기에 require · exclude) 이 이 착지 뒤 같은 자리에 — 착지 알림 보냄
런처      A 와 번갈아 씀, 내림 다 함. 스크래치 스키마 지움
```

다음: 체인 1,000 행 그룹 5 s 규격(8af4d378c).
