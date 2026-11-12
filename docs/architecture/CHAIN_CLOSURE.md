# 체인 닫힘 표 — 새 요청을 재는 동결 기준

> **Status:** 🟢 Living · 주인 C(QA) · 처음 짓기 B 2026-11-06 (총괄 지시, 소유자 「체인 다 덮는지 아직 찝찝」)
> 바탕 코드: origin/main `153fcedb4`. 규칙은 CLAUDE.md «스키마는 수학적으로 완전한 집합으로».

```
새 요청이 오면   이 표에서 «어느 축의 어느 값»인지 먼저 적는다
   칸이 있다    -> 그 칸의 선언 · 결함으로 답한다. 새 기제를 짓지 않는다
   칸이 없다    -> «축 값이 빠진 것»이다. 이 표에 줄을 더하는 것이 그 라운드의 일이다
```

상태: **있음**(선언 칸) · **기본값**(안 적으면 그 값) · **일부** · **없음**(결함).
근거: ✅ 돌려서 초록인 시험(sqlite, 2026-11-06 B) · ⏳ PG 전용 시험(있음, 아직 이 표를 위해 안 돌림) · 읽기(코드만 읽음).
시험 이름은 `server/tests/test_<이름>.py` 의 `<이름>` 이다.

## 1 사건 — 무엇이 규칙을 깨우나

| 값 | 상태 | 자리 | 근거 |
|---|---|---|---|
| insert | 있음 | 모든 규칙 | ✅ a_join_runs_on_the_trigger_path_like_any_mapper |
| update | 있음 `trigger_columns` | `ingestion_worker` | ✅ a_rule_runs_only_when_its_wake_columns_change |
| delete | 선언 없음 · AI 규칙(ask · report) 빼고 전부 깨어 그 묶음을 다시 답함, 아무도 답 안 한 지움은 origin 층을 거둠 (11-08 2단계) | `chain_bindings.takes_deletions` · `_settle` · `_withdraw_unanswered_deletions` | ✅ a_deleted_row_takes_back_the_cells_it_fed · ⏳ a_key_a_source_row_left_is_recounted |
| key move | 기본값 — 옛 값을 실은 update, 옛 키도 다시 셈 | `rule_run.held_back` | ✅ a_map_a_row_left_is_handed_whole |
| 위쪽 체인의 쓰기 | 있음 `allow_chain_trigger` · 자기 선언의 쓰기는 늘 안 깨움 | `_rule_accepts_event` | ✅ chain_cascade |
| 사람 코멘트 | 있음 `memory.comment` (AI 다시 돌림) | `chain/ask_rule` · report | 읽기 |
| replay | 있음 | `chain/replay` | ✅ chain_replay · a_cut_replay_resumes_after_its_last_committed_page |
| 시각 · 일정 | **없음** | 규칙 칸 목록(`RULE_ROUTING_OPTIONAL`)에 없음 | 읽기 |
| 참조 표(take `ref`)의 변경 | **없음** — 빠짐, 트리거 찾기 안 ㄱ 에서 닫음. 값은 다음에 가까운 행 · 키가 바뀌거나 소급할 때까지 조용히 낡음 | 깨움은 `trigger_table` 한 칸(`watches_table`) · ref 는 읽기 집합(`rule_tables` READ)에도 없음 | 읽기 (A 11-10) |
| 원장 걷기(take `fn: walk`)가 닿는 소스 표의 변경 | **없음** — 빠짐, 트리거 찾기 안 ㄱ 에서 닫음. 같은 낡음 | 같음 · walk 소스 표도 읽기 집합에 없음 | 읽기 (A 11-10) |

3 단 검사기(A 11-10, 트리거 찾기 안 ㄱ): 시스템 세계의 규칙 —reads_from(역할: 트리거 · 오른쪽 · ref · walk)/writes/writes_column→ 표 · 칸 «그래프 하나» 위의 걷기다 — 깨울 규칙 · 순환 · (표, 칸) 소유 충돌이 같은 엣지를 읽는다. 오늘 `reads_from` 은 `trigger_table` 뿐이고(`chain/graph.rule_facts`), 순환 그래프 셋(`column_loops` · `rule_order` · `_validate_chain_cascade_graph`)은 각자 엣지를 짓는다.

## 2 언제 — 어느 행을 넘기나

| 값 | 상태 | 자리 | 근거 |
|---|---|---|---|
| 바뀐 칸 | 있음 `trigger_columns` (+게이트 칸 자동) | `ingestion_worker` | ✅ a_rule_may_watch_only_the_columns_it_names |
| 행 조건 — 찼나 · 값 · glob | 있음 `require` · `exclude` | `rule_run.gate_misses` (+SQL 쌍 `gate_conditions`) | ✅ a_rule_is_handed_only_rows_its_require_fills · a_rule_gate_takes_values |
| 행 조건 — 비교 · 범위 · 날짜 · And/Or | **없음** (소유자 11-06 요청) | — | 읽기 |
| 빈 키 행 | 기본값 — 빼고 셈 | 체인 키 게이트 | 읽기 (71dfa331d) |
| 누가 썼나 — 체인이냐 아니냐 | 있음 | `allow_chain_trigger` | ✅ chain_cascade |
| 누가 썼나 — 사람 · 파일 · AI 따로 | **없음**. 자동 확정 쓰기가 체인 아닌 것처럼 깨우는 결함(가이드 09-26) | — | 읽기 |

## 3 모으기 — 무엇을 읽나

| 값 | 상태 | 자리 | 근거 |
|---|---|---|---|
| 자기 행 | 있음 `=수식` 자기 조인 | `join_into` · `chain.formula` | ✅ a_formula_on_a_column_is_a_join_onto_its_own_row |
| 같은 표, 키로 | 있음 `group_by` | rule_run | ✅ a_rule_can_say_what_a_group_is |
| 다른 표, 같은 키 | 있음 join `on` | `join_into` | ✅ a_declared_join_writes_what_it_says_into_the_table |
| 다른 표, 키 묶음 전부 | 있음 take `fn` | `join_into._fn_takes` | ✅ a_join_take_can_gather_every_row_of_a_key |
| 다른 이름 칸끼리 | 있음 `on` 짝(left · right) | `join_into._pairs` | ✅ a_declared_join_writes_what_it_says_into_the_table |
| 다른 표, 범위 · 가장 가까운 · 시간 창 | **없음** — `on` 은 같음 짝뿐. 코드 맵퍼로만 | — | 읽기 |
| 참조 표 통째 | 있음 take `ref` | `join_into._functions_and_ref` | ✅ a_join_take_fn_names_a_function (ref 단언 여부는 안 열었다) |
| 원장 걷기 | 있음 take `fn: walk` (`worlds`) | `join_into.walked` | ✅ a_join_take_walks_the_rows_wafers_to_the_keys_quantity |
| 바깥 — LLM | 있음 `derive.ask` · report | `chain/ask_rule` | ✅ an_ask_rule_fills_a_table_from_a_groups_rows |
| 바깥 — 파일 · API | 기본값 — 인제션으로 표에 들어온 뒤 조인 | 설계 «원천은 표에» | 읽기 |

### 3-a 같은 키의 뜻 (소유자 10-14 · 10-23 · 10-24)

| 값 | 상태 | 자리 | 근거 |
|---|---|---|---|
| 철자 — 1 · 1.0 · 001 은 한 값 | 있음 칸 선언 타입대로 | `crud.key_part` · `map_overlay.canonical_bind_value` | 읽기 |
| 표기 접기 | 있음 | notation fold | 읽기 |
| 시각 — 한 순간은 한 키 | 있음 | 키 철자 | 읽기 (a_datetime_key_has_one_spelling 있음, 안 돌림) |
| 빈 칸 = 빈 칸 | 있음 | `crud.is_blank_key_part` | 읽기 (a_blank_key_part_is_one_key_and_old_rows_are_rekeyed 있음, 안 돌림) |

## 4 몇 개 → 몇 개

| 값 | 상태 | 자리 | 근거 |
|---|---|---|---|
| 1→1 | 있음 join | `join_into` | ✅ a_declared_join_writes_what_it_says_into_the_table |
| N→1 | 있음 fn take · decide 집계 | `join_into` · `enrichment/mapper` | ✅ a_join_take_can_gather_every_row_of_a_key · ⏳ a_derived_row_carries_the_groups_aggregate |
| 1→N 펼침 | 있음 decide 키 목록 | decide | ✅ a_decide_key_expands_into_listed_rows |
| 평행 목록 둘을 짝지어 펼침 | **없음?** — lot_slot_wafer 맵퍼가 코드로. decide 펼침이 덮는지 안 쟀다 | — | 읽기 |
| N→M 다시 묶음 | 있음 ask · 맵퍼 `group_by` | ask_rule | ✅ an_ask_rule_fills_a_table_from_a_groups_rows |
| 0→1 없으면 만듦 | 일부 — decide · ask · mapper 는 만든다. **join 은 없음**(있는 행만 씀) | `join_into._update_items` | 읽기 |
| 1→0 지움 | 있음 gone · 빈 껍데기 · replace_map | `_settle`(11-08, 전 `_delete_gone`) · `cell_layer.shells` | ✅ a_withdrawal_that_empties_a_row_deletes_it · replace_map · ⏳ a_row_left_with_only_the_chains_keys_is_deleted |

## 5 계산

| 값 | 상태 | 자리 | 근거 |
|---|---|---|---|
| 복사 | 있음 join | `join_into` | ✅ a_declared_join_writes_what_it_says_into_the_table |
| 행 수식 | 있음 `=수식` | `server/expression.py` | ✅ a_formula_follows_the_cells_it_reads |
| 묶음 집계 | 있음 fn · decide | `enrichment.config.aggregation_record` | ✅ a_join_take_can_gather_every_row_of_a_key · ⏳ a_decide_aggregation_is_an_expression (pg 부분) |
| 창 · 순위 (OVER) | **없음** — expression 에 OVER 없음, lag/lead 는 NOT_YET | — | 읽기 |
| 하나 고르기 (decide · 자동 확정) | 있음 `auto_confirm` | `enrichment/candidates` | ✅ enrichment_candidates (153fcedb4 부터 어느 데이터 루트에서나) |
| 합의 · 보류 | 있음 제품 맵퍼 `copy_rows_with_hold` | `mappers/hold_copy.py` | ⏳ a_copied_row_holds_until_its_claims_agree |
| 글 쪼개기 | AI 로만 | ask | ✅ an_ask_rule_reads_split_item_texts_into_quantities |
| 찾아보기 표 | 있음 fn + ref | `join_fn` | ✅ a_join_take_fn_names_a_function · mapper_sample_cross_table_lookup |
| 코드 | 있음 `@mapper` | `mapper_sdk` | ✅ mapper_sdk |
| AI | 있음 ask · report (`prompts`) | ask_rule · report | ✅ an_ask_rule_fills_a_table_from_a_groups_rows |

## 6 쓰는 곳

| 값 | 상태 | 자리 | 근거 |
|---|---|---|---|
| 같은 행 | 있음 | 수식 | ✅ a_formula_write_holds_no_layer_and_leaves_a_receipt |
| 같은 표 다른 행 | 일부 — 트리거 표엔 업서트만 | 쓰기 자리 | 읽기 |
| 다른 표의 있는 행 | 있음 join | `join_into` | ✅ a_declared_join_writes_what_it_says_into_the_table |
| 새 행 | 있음 decide · ask · mapper | | ✅ an_ask_rule_fills_a_table_from_a_groups_rows |
| 원장 | 기본값 — 체인은 원장에 안 쓴다. 원장이 그 표를 읽는다 | 설계 | 읽기 |
| 맵 | 있음 `replace_map` · `retract` | `dt_map_derivation` | ✅ replace_map |
| 바깥 동작 | **없음** | — | 읽기 |

## 7 효과

| 값 | 상태 | 자리 | 근거 |
|---|---|---|---|
| 칸 씀 (표시 포함) | 있음 | | ✅ the_fold_mapper_keeps_one_unit_per_group |
| 칸 비움 | 있음 | | ✅ a_join_may_declare_a_blank_answer_is_not_written · a_blank_recount_takes_back_only_its_own_rules_layer |
| 행 만듦 | 있음 | | ✅ an_ask_rule_fills_a_table_from_a_groups_rows |
| 행 지움 (동작) | 있음 mapper 봉투 · decide/ask 의 gone | | ✅ a_decorated_mapper_removes_what_its_rule_allows |
| 집합 통째 교체 | 있음 | | ✅ replace_map · a_whole_replay_takes_back_the_maps_it_never_named |

## 8 입력이 바뀔 때 — 원천 고침 / 원천 지움 / 조건 밖으로

| 값 | 고침 | 지움 | 조건 밖 | 자리 |
|---|---|---|---|---|
| 다시 계산 (모으는 규칙) | ✅ | ⏳ | ⏳ 떠난 행으로 넘김 | `rule_run.held_back` |
| 칸 거둠 | ⏳ an_edited_source_row_takes_back_what_it_no_longer_feeds | ✅ a_deleted_row_takes_back_the_cells_it_fed | exclude ⏳ · require ⏳ | `_withdraw_and_tell` |
| 만든 행 지움 | — | ⏳ gone | — | `_settle`(11-08, 전 `_delete_gone`) · 빈 껍데기 ✅ |
| 남김 | 기본값 — origin 안 찍는 규칙(자동 확정 · 안 찍는 파일 맵퍼)은 남고 로그에 이름 댐 | | | `rule_run.retraction_refusal` |
| 규칙마다 남김/거둠 고르기 | **없음** | | | — |

require 가 빠진 행: 시험 `a_folded_row_is_marked_and_what_it_fed_taken_back::test_a_row_that_lost_require_is_taken_back_in_a_fresh_process` 가 «거둔다»를 단언한다(⏳). 가이드 chain_rules.md 의 require 행(«지우지 않는다»)과 어긋난다.

## 9 서열

| 값 | 상태 | 자리 | 근거 |
|---|---|---|---|
| 층 서열 — 사람 · 파일 · 체인 | 있음 `SOURCE_PRIORITY` (사람이 이김) | crud | ✅ a_rules_layer_is_chain_ingestion_whatever_its_mapper_writes · a_chain_layer_is_one_per_source_row |
| 수식 칸 저자 하나 | 있음 | `chain.formula.second_writers` | ✅ a_formula_column_has_one_writer |
| 규칙 둘이 한 칸 | 기본값 — 둘 다 chain_ingestion, 나중 쓰기가 이김 | | ✅ the_later_item_of_one_batch_wins_as_in_two |
| 규칙 사이 우선 | **없음** | — | 읽기 |

## 10 순서

| 값 | 상태 | 근거 |
|---|---|---|
| 깊이 `max_chain_depth` | 있음 | ✅ the_chain_counts_its_hops |
| 고리 | 있음 — 칸 고리는 로드 거절 | ✅ rules_that_wake_each_other_by_column_are_refused |
| 규칙 순서 | 있음 — 선언이 정함 | ✅ the_worker_runs_rules_in_the_order_the_declaration_implies |
| 두 번 먹이면 안 됨 `idempotent` | 있음 | ✅ a_rule_can_say_it_must_not_be_fed_twice |
| 같은 값 다시 씀 | 기본값 — 안 깨움 | ⏳ the_same_value_written_again_wakes_no_rule |

## 11 시간

| 값 | 상태 | 근거 |
|---|---|---|
| 그때 기준 (as-of) | **없음** — 규칙은 지금 상태만 계산 | 읽기 |
| 늦게 온 데이터 | 기본값 — insert 로 들어와 키를 다시 셈, `Latest()` 는 시각으로 고름 | 읽기 |
| replay 키째 쪽 | 있음 | ✅ a_replay_keeps_a_group_by_key_on_one_page |

## 12 실패

| 값 | 상태 | 근거 |
|---|---|---|
| 다시 시도 · 격리 `max_group_attempts` | 있음 | ✅ a_group_is_isolated_after_the_declared_attempts |
| 묶음 일부 실패 | 있음 | ✅ one_bad_row_does_not_stop_a_tables_chain |
| 연속 실패면 규칙 끔 (소유자 10-24) | 있음 — 10 번 연속이면 저장 전까지 끔 | 읽기 (06b1fd297) |

## 13 규모 · 비용

운영 규격(CLAUDE.md): 체인 그룹 1,000 행 ≤ 5 s. 아래 수는 **B 가 버리는 PG(`assy_b_pgtest`)에서 잰 박스 수**이고, 운영에 대한 주장이 아니다. 「미측정」은 아직 안 잰 것이다.

| 값 | 선언 | 잰 수 (박스) |
|---|---|---|
| 행 지움 자체 (모든 행 지우기) | 쪽 크기 `pacing.page_seconds` 3 s, 페이스 Fast 쉼 0 | 1,000 행 규칙 있음 539 rows/s · 10,000 행 규칙 없음 1,169 rows/s · 100 칸 × 층 16 493 rows/s. 운영 화면 보고는 32 rows/s — 차이를 조사 중 |
| 지운 뒤 체인 + 원장 후속 | 페이스 `jobs.chain_followup` fast | 1,000 행 33.8 s |
| 체인 그룹 쓰기 | 규격 1,000 행 ≤ 5 s | 미측정 |
| 묶음 자르기 | `rows_per_run` | 미측정 |
| 조인 키 조회 인덱스 | `key.unique` 없으면 `ix_vjoin_*` | 미측정 |
| 이력 패널 읽기 | `recent_statement_seconds` 5 · `recent_walk_seconds` 10 | 상한을 시험이 단언(⏳ the_recent_history_never_holds_the_server) |
| 인덱스 화면 원장 판정 | 세계마다 카탈로그 한 번(착지 대기) | 박스 DB 에서 화면 읽기 한 번 0.5~1.0 s |

## 닫힘 시험 — 모집단과 결과

모집단: 맵퍼 9(hold_copy · fold_unit · lot_lineage · lot_slot_wafer · dt_map · core_usage · agent_walk · contrast_walk · cross_table_lookup) + 2026-10-06~11-06 커밋 제목에 인용된 소유자의 체인 기능 요청 22 + 09-26 자동 확정 결함.
한 달 요청 22 중 20 은 이미 있는 칸이었다. 고친 것은 그 칸의 결함이었다.

| 순위 | 없는 칸 | 걸린 것 |
|---|---|---|
| 1 | 창 · 순위 (OVER) | fold_unit · contrast_walk (둘 다 코드로 우회) |
| 2 | 행 조건 수식 | 소유자 11-06 |
| 2 | 누가 썼나 따로 고르기 | 09-26 자동 확정 깨움 |
| 2 | 평행 목록 짝짓기 | lot_slot_wafer |
| 2 | join 의 0→1 | 소유자 11-06 «체인 액션 crud» |
| — | 범위 · 가장 가까운 · 시간 창 모으기 · 시각 · 일정 사건 · as-of · 바깥 동작 · 규칙 사이 우선 · 규칙마다 남김/거둠 | 0 |
