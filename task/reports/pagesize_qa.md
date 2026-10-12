# impl-pagesize 적대 재검수 — e902a67e6 (응용, 10-12)

**NO-GO 하나 남음 — fold_units 의 시작 → 첫 줄(아래 «쪽 칸» 표).** 지난번 NO-GO 넷(쪽 앞 전체 읽기 · 요청 안 세기 · 접기 이벤트 수 · 줄이기 변이)은 고쳐졌습니다.

판: assy_test 의 이름 붙인 스크래치 스키마(qa_pagesize* — search_path 는 그 스키마만, 끝에 DROP, 남은 것 0)와
PG 시험 스키마(hold 판 · fold 판 · enrichment 판, 씨앗은 쓰기 문으로 넣은 행을 SQL 로 늘림). 대상 표 인덱스 11개.
이 파일의 수는 전부 결과 JSON 에서 뽑은 표에 있습니다(scratchpad qa_pagesize_report_gen.py). 위 글에는 수를 다시 적지 않습니다.

## 남은 것

- **fold_units** — 첫 줄이 «page 1: read · 1 rows» 로, 규칙 자리(`rule_run.run_rule`, `next_page`)의 첫 부름이 답 전체를 먼저 셈.
  그 뒤 줄 간격은 상한 안. `replay.py` 는 e902a67e6 에서 안 바뀜 — 46324bcbb 에도 있던 것, 지난번엔 안 잰 칸
- **ledger_backfill** — 쪽 최대 초가 상한을 조금 넘음(46324bcbb 에서 잼; `_run_via_events` 는 e902a67e6 에서 안 바뀜)
- **요청 안 세기** — set_aside · 낡은 원자 둘 다 상한을 넘긴 첫 쪽 경계에서 멈춤(상한보다 조금 김). «at least» 문장 붙음
- **안 잰 것** — remove_shell_rows: 이 판에 껍데기 행이 없어 빈 훑기만 잼. 백필 전체 세기의 exclude_when 읽기: 이 판은 빠진 행이
  넘쳐 그 읽기를 안 함(아래 줄) — 그 아래에서 읽는 경우는 안 잼

## 시험 · 변이 (e902a67e6)

- 가지가 만진 시험 파일: 일반 · PG 둘 다 초록(PG 의 errors 는 새 작업트리에 없는 gitignore 매퍼·설정, 지난번과 같음)
- 변이 셋 — 첫 쪽 고정 · 안 늘림 · 넘으면 안 줄임 — 전부 failed(기준 먼저 초록). 줄이기는 test_a_page_over_the_page_time_cuts_the_next_by_its_overshoot 가 잡음
- 접기 이벤트 수: 가지 시험이 늘어난 수를 단언함(지난번 응용이 잰 수와 같음)
- 라이브 체인 «쓰기 하나 = 이벤트 하나»: 지난번 판정 그대로(체인 자신의 철회는 고정 쪽)

### 쪽 앞 전체 읽기 넷 — e902a67e6, 이름 붙인 스크래치 스키마 (대상 표 인덱스 11개)

| 자리 | 판 | 시작 → 첫 줄 | 첫 줄 뒤 최대 간격 | 끝 |
|---|---|---|---|---|
| ① set_aside dry | 이벤트 500,000 | 0 s | 0.08 s | 14.17 s |
| ① set_aside apply | 이벤트 500,000 | 0.03 s | 0.14 s | 38.53 s |
| ③ withdraw_source dry | 셀 900,000 | 0 s | 0.52 s | 44.58 s |
| ③ withdraw_source apply | 셀 900,000 | 0 s | 3.42 s | 304.8 s |
| ② confirm 의 쪽(derived_pages) | 대기열 1,000,000 | 첫 쪽 0.078 s | 쪽 최대 0.078 s | 9.64 s |
| ④ withdraw_stale_atoms apply | 원자 2,000,000 | 0.12 s | 0.45 s | 11.14 s |

### 요청 안 세기 (5 s 상한 · «at least»)

- set_aside 세기: 5.03 s · waiting events to set aside (at least - 151000 row(s)) · by table: {'qa_t': 151000} - stopped counting at 5 s; the run counts the rest as it goes
- 낡은 원자 세기(whole_source 세기의 그 읽기): 5.02 s · cut True · 읽은 원자 1,949,421 / 2,000,000
- ledger_rescope 세기 whole_source 전체(hold 판 210,013 행): 0.55 s

### 쪽 칸 — 지난번 안 잰 것 (운영 크기 판)

| 연산 | 판 | 시작 → 첫 줄 | 첫 쪽 | 쪽 최대 초 | 줄 간 최대 | 쪽 수 | 코드 |
|---|---|---|---|---|---|---|---|
| resolve | hold 20만 · 셀 266만 | 0.05 s | 1 | 0.4 s | 0.44 s | 219 | 46324bcbb (이 연산의 코드 e902a67e6 와 같음) |
| fold_written_notation | hold 20만 | 0.14 s | 1 | 1.1 s | 0.94 s | 24 | 46324bcbb (이 연산의 코드 e902a67e6 와 같음) |
| fold_file_layers | hold 20만 | 0 s | 1 | 0.7 s | 0.67 s | 219 | 46324bcbb (이 연산의 코드 e902a67e6 와 같음) |
| ledger_backfill | hold 20만 | 0.98 s | 1 | 5.2 s | 5.2 s | 249 | 46324bcbb (이 연산의 코드 e902a67e6 와 같음) |
| fold_units | fold 판 | 12.19 s | 1 | 12.4 s | 2.48 s | 22 | e902a67e6 |
| inventory_replay | fold 판 | 0.75 s | 1 | 0.8 s | 0.76 s | 49 | e902a67e6 |
| inventory_replay_trickle | fold 판 · trickle · 3,000 행 | 3.09 s | 1 | 3.4 s | 3.44 s | 12 | e902a67e6 |
| fold_duplicate_rows | fold 판 · mark | 3.05 s | 1 | 3 s | 1.62 s | 169 | e902a67e6 |
| remove_shell_rows | fold 판 | 0.23 s | — | — s | 0 s | 0 | e902a67e6 |
| enrichment_backfill | 원천 20만 | 0.34 s | 1 | 1.2 s | 1.22 s | 209 | e902a67e6 |

fold 판: 인벤토리 40,000 · 로그 200,000 행(로그 인덱스 8) · enrichment 원천 200,000 행

백필 전체 세기 rows_not_yet_translated, main 코드(382c5f444, exclude_when 셈 9c1da298f 포함), hold 209,998 행: 1.12 s · excluded_not_subtracted = over 100k rows the index does not name

public: 전 70 표 · 67 행 -> 후 70 표 · 67 행 · 바뀐 표 0
