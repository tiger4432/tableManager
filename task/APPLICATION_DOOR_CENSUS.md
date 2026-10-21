# 문 정리 한 판 — 같은 물음에 답하는 자리 전수 (응용 C, 2026-10-21)

지시: 총괄 `9f8f0ff35` 의 1 · 덧붙임(트랜잭션 단위, 소유자 «거두기랑 채우기 중간에 꺼져서 어긋나지 않는지»).
읽기만 했다. 코드는 한 줄도 안 고쳤다.

```
기준     origin/main 9f8f0ff35 의 server/ (시험 제외) — git archive 로 떼어 온 그 트리
         껍데기 칸만 c4fd1a22c(B, 18:45) 뒤 값을 나란히 적음
계기     task/door_census.py — AST: 이름마다 def 수 · 부르는 곳 수 · 참조
센 명령  git archive 9f8f0ff35 server | tar -x -C T
         python task/door_census.py T <이름…>          (--callers <이름> 은 부르는 곳 목록)
카나리아  파싱 322 / 322 파일 · 이 문서가 든 이름 117 개 전부 def ≥ 1 (def 0 = 0 개)
         없는 이름(no_such_name_canary)은 def 0 으로 나옴을 먼저 봄
자리 찾기 읽기 전용 탐색 다섯이 갈래별로 훑고, 든 이름은 내가 같은 도구로 다시 셈
```

갈라짐 예의 «확인» 칸 — **돌림** = 함수를 직접 불러 답을 봄 · **줄** = 그 줄을 열어 읽음 · **보고** = 탐색 보고만, 내가 안 봄.

---

## 1. 한눈 표 — 물음 × 자리

| 물음 | 자리 | 갈라짐 예 | 확인 | 오늘 운영 증상 |
|---|---|---|---|---|
| 층 거두기 · 행 지우기 | 17 | 사람이 쓴 행을 지워도 되나 — 답 넷 | 보고 | 체인 껍데기 · 자동 회수 안 됨 |
| 빈 행(껍데기) 묻기 | 2 → 4 | 수정 거두기가 비운 행을 안 물음(9f8f) | 줄 | 체인 껍데기 |
| 키 철자 — 맵 id | 3 def | {lot L, slot 없음} → None · «L_» · «L_» | 돌림 | — |
| 키 철자 — 업무 · 조인 · 맵 키 칸 | 9 · 2 · 5 | 숫자 조인 칸 «01» → «01» 대 «1» | 보고 | — |
| 칸에 쓸 값(cast) | 5 | 표 이름 빠진 부름 4 곳은 시각에 시각대 안 붙임 | 줄 | double 칸에 character |
| 칸 타입 | 4 원천 | 모델 · 선언 · DB · 손 기본값 | 보고 | double 칸에 character |
| 빈 값 판단 | 12+ | NaN → 값 · 빈 값 · 빈 값 · 값 | 돌림 | — |
| 행 관문 | 4 | 공백 칸: 파이썬 빈 값 · SQL 값 (저장 불변식이 막음) | 줄 | — |
| 시간 읽기 | 10+ | 시각대 없는 시각 → 서울 · 시각대 없음 · UTC · 거절 | 돌림 | — |
| 표기 접기 | 5 | «Abc» → «ABC» 대 «abc» | 보고 | — |
| 쪽 | 13+ | 같은 맵퍼 답을 1,000 행 쪽 · 20,000 행 쪽 | 보고 | — |
| 커밋 경계 | 표 4 | 지운 행 거두기가 «처리됨» 커밋 뒤 | 줄 | 자동 회수 안 됨 |
| 소급 넣기 | 4 | 파일 다시 읽기는 관문을 안 물음 | 줄 | 외장 다시 읽기 · Retry PENDING |
| 그룹 이름 | 2 철자 | replay 사건: 이름이 replay_<run> 대 run_id | 보고 | — |
| 이미 읽었나 | 3 열쇠 | 같은 바이트 · 새 mtime: 다시 읽음 · Retry 는 0 부터 | 보고 | 외장 다시 읽기 |
| 이 규칙이 쓰는 칸 | 4 | 한 쪽짜리 join · take 칸 전부 빈 값 → 그 칸 거두기 빠짐 | 보고 | take fn · target_columns |

«자리»는 그 물음에 «스스로» 답하는 함수 · 인라인 수다. 정본을 부르기만 하는 곳은 안 셈.

---

## 2. 층 거두기 · 행 지우기 — 소유자 첫 접기의 대상

### 2-1. 층을 거두는 자리 (9)

| # | 자리 | 부름 | 껍데기 묻나 9f8f → c4fd | 문 |
|---|---|---|---|---|
| 1 | 수정 거두기 `_withdraw_and_tell(…, "edited")` | 4 | 아니오 → 예 | 직접 SQL |
| 2 | 지운 원천 행 `_retract_deleted_rows` → `_withdraw_and_tell` | 4 | 아니오 → 예 | 직접 SQL |
| 3 | 빈 재계산 `_withdraw_blanks` | 1 | 예(쓰기 자리) → 예 | 직접 SQL |
| 4 | fold_units 끝 (replay `_withdraw_and_tell`) | — | 아니오 → 예 | 직접 SQL |
| 5 | R2 `withdraw_source` | 2 | 아니오 → 예 | 직접 SQL |
| 6 | 공용 속 `withdraw_layers` · `withdraw_by_origin` · `_withdraw_cells` | 2 · 1 · 2 | — | 직접 SQL, 쪽마다 커밋 |
| 7 | `fold_file_layers` | 2 | 아니오 | `bulk_delete_cell_sources` |
| 8 | 쓰기 문 안 파일 층 접기 | — | 아니오 | 쓰기 문 안 |
| 9 | 그리드 층 지우기 `delete_cell_source_batch` · `delete_cell_source` | 2 · 1 | 아니오 | 직접 SQL, 보이는 값을 스스로 다시 계산 |

### 2-2. 행을 지우는 자리 (8)

| # | 자리 | 부름 | «지워도 되나» |
|---|---|---|---|
| 10 | 맵 교체 purge `purge_map_rows`(Map Replace Executed) | 3 | 묻지 않음 — 사람이 쓴 행도 |
| 11 | 맵 교체 diff (Map Diff) | — | 이 쓰기가 안 든 행 |
| 12 | 잡 회수 `plan_retraction` · `apply_retraction` | 1 · 1 | 사람 덮어쓰기 있는 행은 지킴 · 50% 넘고 20 행 이상이면 통째 거절 |
| 13 | decide 의 사라진 키 `_delete_gone` | 1 | 다른 쓴 이는 지킴 · **사람 행은 지우고 줄만** |
| 14 | 체인 쓰기 뒤 껍데기 | — | `shells`: 사람 층 있으면 거절 |
| 15 | 껍데기 쓸기 `remove_shell_rows` | 2 | `shells` |
| 16 | `fold_duplicate_rows` | 2 | 순위만 |
| 17 | 충돌 병합 진 쪽 `_merge_into_key_holder` | 3 | 병합 규칙 |

리플레이 끝 `sweep_finished_replays`(부름 0 · 참조 1 — 워커가 `to_thread` 로 넘김)는 `_removal_batches` 로 빈 묶음을 지어
`apply_chain_writes` 로 보내므로 10 · 11(교체 규칙) 또는 12(회수 규칙)가 된다.

껍데기 묻는 자리(`cell_layer.shells` 부름): 9f8f0ff35 **2** (`apply_chain_writes` · `remove_shell_rows`) →
c4fd1a22c 뒤 **4** (+ `_withdraw_and_tell` · `withdraw_source`). 명령: `--callers shells` 를 두 트리에.

### 2-3. 갈라짐

```
① 사람이 쓴 행을 지워도 되나 — 답 넷 (보고)
   purge(10) 지움 · _delete_gone(13) 지우고 줄만 · shells(14·15) 거절 · plan_retraction(12) 지킴
② 껍데기를 묻나 (줄, 9f8f0ff35) — c4fd1a22c 가 닫음
   한 apply_chain_writes 안에서 빈 재계산이 비운 행은 1887 에서 묻고 지우지만,
   수정 거두기(2037–2045)는 그 블록 «뒤»라 안 물었다
③ 리플레이 끝 + 회수 규칙 (보고 · 추론, 안 돌림)
   빈 묶음 → plan_retraction 이 소유 행 전부를 낡음으로 봄(비율 1.0 > 0.5) → 20 행 이상이면 거절, 아무것도 안 지움
   같은 사라진 맵이 교체 규칙이면 purge 됨
```

---

## 3. 커밋 경계 — 경로마다 «쓰기 · 거두기 · 껍데기 · 처리됨 · 이력»

커밋 기호(탐색 보고, W · M · 순서는 내가 줄로 확인):
`W` 쓰기 문 `_apply_batch_updates_once` 의 커밋 하나(값 · 층 · 이력 · 사건 · 교체 purge 까지) ·
`R` `apply_retraction` · `P` `_withdraw_cells` 쪽마다 · `T` «층 잃은 행» EDIT 알림 · `D` `delete_rows_batch` · `M` 아웃박스 처리됨.
쓰기 문은 **묶음마다** 커밋한다(crud `_apply_batch_updates_once` 안 `db.commit()` 하나 — 줄).

| 경로 | 커밋 순서 | 죽으면 남는 것 → 재시도가 바로잡나 |
|---|---|---|
| 실시간 편집 | W… → R → P…→T → D → M | W 뒤: 재시도 예 · 잡힌 오류면 SUCCESS 로 끝나 아니오 · P→T: 층은 없고 알림 없음, 재시도는 거둘 층이 없어 아니오(값 바뀐 행은 P 의 사건으로 부분) |
| **지운 원천 행** | W(·R) → **M** → P…→T | **M→P: 처리됨인데 그 행이 먹이던 층이 남음 → 아니오** (줄: 9f8f0ff35 · 지금 main 둘 다 `mark_processed`·커밋 뒤 `_retract_deleted_rows`) |
| 파일 · 맵 교체 | 묶음(맵)마다 W → 보관 이동 → 체크포인트 DONE(따로) → 로그 행(따로) | 맵 사이: 맵 파일은 이어 읽지 않고 다시 다 교체, 예 · 이동→DONE·로그: 데이터는 다 들어갔는데 로그 행 없음 → Retry 단추도 없음, 모름 |
| 리플레이 쪽 | 쪽마다 사건 커밋 → 워커가 경로 1 | 쪽 사이: 남은 쪽 안 돎, 런은 running 으로 서 있음, 손으로 다시, 부분 · 집계 수가 다시 시도로 두 번 셈 → 끝 스윕 거절(안전 방향) |
| 리플레이 끝 스윕 | 맵마다 W(·R) → 집계 행 지움 | 사이: 집계가 남아 다음 깸이 다시 판정, 예 |
| R2 | P 쪽마다 → (c4fd 뒤) D | 쪽 사이: 다시 돌리면 남은 것을 찾음, 손으로 예 · P→D: 껍데기 남음, 재시도는 거둘 층이 없어 안 물음, 아니오(B 커밋 본문도 같은 말) |
| fold_units | 쪽마다 W(사건 없음) → P…→T | 마지막 쪽→P: 다시 돌리면 거둠, 예 · P→T 부분 |
| 빈 재계산 | W → P→T → D(gone) → D(껍데기) → M | P→T 부분 · 나머지 예 |
| rule_rows(소급 운영) | 묶음마다 W → 끝 커밋 | **선언 문구 «one commit for the run» 이 거짓** — 묶음마다 커밋되어 실패 때 `rollback` 이 앞 묶음을 못 되돌림 (줄: retroactive.py `OPERATIONS["rule_rows"]` · crud 커밋) |

### 3-1. 그 틈을 이미 말하는 줄 (보고, 위치는 9f8f0ff35)

| 자리 | 문구 | 경로 |
|---|---|---|
| ingestion_worker 1812 | «DECLINED … Stale rows were LEFT IN PLACE» | 편집 · 지움 |
| ingestion_worker 1832 | «retraction failed AFTER a committed write; stale rows may remain» | 편집 · 지움 · 끝 스윕 |
| ingestion_worker 1850 | «a blank recount's withdrawal failed AFTER a committed write» | 빈 재계산 |
| ingestion_worker 2027 | «rows are COMMITTED but clients will NOT be notified» | 체인 쓰기 전부 |
| ingestion_worker 2052 | «the edit's withdrawal failed AFTER a committed write; old layers may remain» | 편집 |
| ingestion_worker 2330 | 편집된 원천 행이 먹이던 옛 층 못 거둠(한국어) | 편집 |
| ingestion_worker 3485 | «retraction failed for table … (the group itself is committed)» | 지움 |
| ingestion_worker 3595 | «kept … no source rows, but … wrote on it» | 빈 재계산 |
| cell_layer 332 | «… is a protected layer and was NOT withdrawn» | 지움 · R2 · fold_units |
| directory_watcher 2919 · 2949 | «Failed to finalize ingestion checkpoint» · «Failed to write the … ingestion log row» | 파일 |
| replay 593 · 841 | «page … failed and was skipped» · «[ReplaySweep] … not swept» | 리플레이 |
| dt_map_derivation 1117 | «the upsert itself already committed»(예외 문구) | 편집 · 지움 |

---

## 4. 나머지 물음 (줄인 표)

### 키 철자
| 칸 | 자리 | 갈라짐 |
|---|---|---|
| 맵 id | `compose_map_id` **def 3**(map_meta_registrar · map_overlay · map_alignment), 부름 15 | {lot L, slot 없음}: registrar **None** · overlay **«L_»** · alignment **«L_»** (돌림) |
| 업무 키 | `canonical_key_value`(10) 위에 `key_part` · `compose_business_key`(def 2) · `assemble_composite_business_key` · `rebuilt_business_key` · `meta_business_key` · `compose_unit_key` · `_clean_key` · `value_key` | 빈 조각을 자리마다 따로 판단 · `_clean_key` 는 빈 값을 '' 로 |
| 조인 키 | 파이썬 `_folded_join_key` · SQL `key_expression_sql/_text` | 숫자 칸 «01»: «01» 대 «1» (보고) |
| 맵 키 칸 읽기 | `identity_columns` · `_map_key_columns` · `replace_map_columns` · `map_key_parts` · 인라인 1 | 둘이 ["lot","slot"] 로 기본값 (보고) |
| 그룹 키 | `spelled_group_key`(2) 하나 — 그룹 «이름»은 아래 |  |

### 빈 값 판단 — NaN (돌림)
`is_blank_value` **False** · `is_blank_key_part` **True** · `roleframe._is_missing` True(보고) · `expression.is_blank` **False**.
같은 행이 키 조립에서는 빈 조각, 값 쓰기에서는 «nan» 글자. 인라인 `clean_str_value(x) == ""` 6 곳 · `str(v).strip()==""` 꼴 8 곳(보고).

### 시간 읽기 — «2026-01-01T00:00:00» (돌림)
`crud.value_key` → 00:00 **Asia/Seoul** · `crud.parse_version_key` → 00:00 **시각대 없음** — 같은 crud.py 안.
`_instant_arg` · `_as_datetime` 은 UTC 로, `ledger_subgraph._parse_instant` 는 거절(보고).

### cast · 칸 타입
- `cast_value_by_type` 부름 9 중 **4 곳이 표 이름을 안 넘김**(cell_layer 216 · replay 2241 · analysis 273 · enrichment/mapper 383 — 줄) → `column_is_text(None, …)` 이 «글자»로 답해 시각대를 안 붙임. 쓰기 문(crud 3951)은 넘겨서 붙임.
- 칸 타입 원천 넷: 모델(`column_is_text` · `sql_type_of`) · 선언(`declared_column_type` 10 · 인라인 `col_types.get(c,"string")` 여럿) · DB(`_type_family` · `physical_columns`) — e53117872 는 «리로드»만 모델을 선언에 맞춤.

### 행 관문
`gate_misses`(파이썬) 짝 `gate_conditions`(SQL, 부름 3) + join_into 안 같은 SQL 을 다시 씀 + hold_copy 는 찍힌 관문으로. 공백만 든 칸은 파이썬 빈 값 · SQL 값이지만, `blank_sql_condition` 의 독스트링이 «저장이 정규화되므로 맞다»고 그 불변식에 기댐 — 실제로 갈라진 행은 못 봄.

### 표기 접기
`fold_notation`(대문자) 과 `value_suggest.db_fold`(PostgreSQL `lower`) — «Abc» 가 «ABC» 대 «abc» (보고). 쓰기용 `fold_for_write` 는 SQL 짝 없음.

### 쪽
키 경계에서 자르는 자리는 `key_pages` **하나**(부름 1). `iter_pages`(9) · `pages`(def 2) · `FOLD_*` 상한 넷은 row_id 로.
같은 fold 맵퍼 답: 실시간 1,000 행 쪽 · 소급 20,000 행 쪽(보고). `stage_collapsed_event`(9)가 키 쪽을 다시 1,000 행 사건으로 나눠 1,000 행 넘는 키는 맵퍼에 나뉘어 닿을 수 있음(보고).

### 소급 넣기
`publish`(2) · `run_here`(6) · `mark_for_reread`(2) · ledger `enqueue`(1). 소비자 둘(`start_replay_if_queued` · `run_auto_update`).
`mark_for_reread` 는 `RetroactiveRun` 행도 관문(`gate_refusal`)도 안 묻는다(줄 — 함수 안 관문 낱말 0) → 리플레이가 관문을 쥐고 있어도 파일 다시 읽기가 시작하고 대기열 화면에 안 보임.

### 그룹 이름
`group_id` = group_by → transaction_id → `single_<uuid>` · `queue_line_key`(7, SQL) = run_id → transaction_id → `outbox#<id>`. 순서도 대체 토큰도 다름(보고). main.py 에 인라인 하나 더.

### 이미 읽었나
`checked`(경로 · mtime · size, SUCCESS 등) · 체크포인트 `find_completed_ingestion`(내용 시그니처, «DONE») · `_wait_until_ingested`(SUCCESS · FAILED 만 기다림을 끝냄).
같은 바이트 · 새 mtime: 체크리스트는 다시 읽고, Retry 는 체크포인트 DONE 을 보고 0 부터(보고).

### 이 규칙이 쓰는 칸
`written_columns`(def 2 — notation_norm 의 같은 이름은 다른 물음) · `columns_a_rule_writes`(3) · `columns_declared_for`(2) · join `take_targets`.
target_columns 없는 한 쪽짜리 join 에서 take 칸 b 가 모든 행에 빈 값이면 `columns_a_rule_writes` 는 {a} — 수정 거두기가 b 의 옛 층을 남김(보고, 둘째 쪽부터는 메워짐).

---

## 5. 접을 순서 — 운영 위험 큰 것부터 (추천)

```
1  지운 원천 행의 거두기를 «처리됨» 커밋 앞으로      재시도가 못 바로잡는 유일한 틈. 운영 «자동 회수 안 됨» 계열
2  거두기 · 행 지우기 → 쓰기 문의 «범위» 하나       소유자 첫 접기. «사람 행 지워도 되나» 답 넷을 하나로,
                                                  P→T(층 잃은 행 알림) 틈과 리플레이 끝 + 회수 규칙 거절을 같이
3  빈 값 하나 (NaN)                               키 조립과 값 쓰기가 같은 칸을 다르게 봄 — 조용한 키 갈림
4  시간 읽기 하나 + cast 의 표 이름 필수            시각대 없는 시각 9 시간 차 · 같은 값이 자리마다 다른 순간
5  칸 타입 하나 (모델 · 선언 · DB)                 운영 «double 칸에 character» — 리로드만 고쳐짐
6  맵 id 하나 + 맵 키 칸 읽기 하나                  None 대 «L_» — 맵 하나가 두 이름
7  소급 넣기의 관문 하나                           파일 다시 읽기가 관문 밖 · 대기열 화면에 안 보임
8  그룹 이름 한 철자 · 쪽 크기 · 이미 읽었나 둘 · 쓰는 칸(한 쪽 join) · rule_rows 커밋 문구
```
1 은 «쓰기 문 범위»로 접히면 저절로 닫히므로 2 와 한 판으로 해도 된다 — 다만 2 가 길면 1 을 먼저 따로.

## 6. 모르는 것

```
지운 행 경로에서 P 뒤 T 의 EDIT 가 껍데기 묻는 재계산 규칙에 늘 닿는지 — 박스 선언에 달림, 안 돌림
리플레이 끝 + 회수 규칙의 거절(2-3 ③) — normalize_scoped_batch 를 안 따라감, 안 돌림
파일 경로의 이동 → DONE · 로그 행 사이에 죽으면 체크리스트가 그 파일을 어떻게 보나 — 안 돌림
server/mappers/ 는 git 무시 — 운영 맵퍼가 따로 답하는 자리는 이 표에 없다(박스에도 없는 것은 셀 수 없음)
행 관문 공백 갈라짐 — 공백을 든 저장 행이 실제로 있나, 안 셈
«보고»로 적은 갈라짐은 내가 안 봤다 — 접기 판에서 같은 입력으로 먼저 잴 것
```
