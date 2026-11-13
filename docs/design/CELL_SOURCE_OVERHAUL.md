# 셀소스 갈아엎기 — 실린 설계 (release-2026-11-14b)

문장마다 근거는 main 의 코드다(`파일:함수`). 수는 박스에서 잰 것이고 운영 크기로 잰 수는 없다.

## 소유자 · 총괄 결정

- 11-10: 쓰기마다 줄이 쌓이고 그 줄 표가 곧 이력이다. 개체마다 보이는 값은 줄을 순위로 합친 값이다.
- 11-11: 표 t 는 그대로 «지금 값 표»다. 더해지는 것은 칸 `won_by` 하나이고, 이력은 옆 표 `t__lines` 에 있다. 11-10 의 «`t__now` + 이름 t 보기 + 트리거» 는 뒤집혔다 — 셋 다 없다.
- 11-11: cell_sources 는 착지 뒤 차가운 보관이다. 쓰기 0, 지우지 않는다. 옛 층은 이주 명령이 줄로 옮긴다(«이주»).
- 11-11: 업무 키 유일 인덱스는 «업서트 용»이다. 줄은 row_id 에 묶이므로 키 인덱스가 없어도 줄 표를 가진다.
- 11-10: 감사 = 트랜잭션 · 표 · 누가 · 바뀐 행 수 · 작업 종류. 값은 넣지 않는다. «전 값» 셈도 짓지 않는다.
- 11-12 ㄴ · 11-13 ㄴ: 이력을 안 남기는 칸(`no_history_columns`)과 줄을 안 갖는 표의 칸은 층이 없다 — 마지막 쓰기가 이긴다, 빈 값도.
- 11-13: 칸을 지우거나 이름을 바꾸는 길은 없다. 선언에서 뺀 칸은 살아 있고, 이름 바꾸기는 새 칸이다.
- 되돌리기 = 옛 릴리스를 같은 DB 위에 띄운다(소유자 ㄴ, 백업 없음).

## 표 모양

- 어느 표가 줄을 갖나 — 한 좌석 `lines.py:keeps_lines`: 운영자가 선언한 표. 갖지 않는 것은 셋이다.
  - 보기(kind view).
  - 제품이 싣는 `sys_*` 표(`shipped.names()` — `server/declarations/table_config.json`, 17 개).
  - 선언에 없는 관계(원장 자체 표 등) — TABLE_CONFIG 에 항목이 없다.
  이런 표의 칸은 이력도 없다(`crud.py:keeps_history`).
- 줄이 지어졌나 — 한 좌석 `lines.py:_catalogue`(`has_lines` 가 묻는다): `t__lines` 가 있고 t 에 won_by 가 있다. 표가 몇 개든 카탈로그를 한 번 읽는다.
- 짓기 — 한 좌석 `lines.py:ensure_declared`. 스키마 동기화 · 키 인덱스 짓기 끝 · 시험 고정물이 부른다.
  - 선언된 표마다 빈 `t__lines` 와 won_by 를 짓고, 칸이 늘면 따라잡는다(`alter_columns`). DDL 은 `db_safety.short_ddl` 로 잠금 기다림에 상한을 둔다.
  - PG: 줄 표의 인덱스는 `line_indexes` 가 CONCURRENTLY 로 짓는다(`models._ensure_one_index_once`). 줄 표에 키 유일 인덱스가 있으면 지운다(`drop_key_index`).
  - 거절(`build_refusal`): 이름이 길다 · 보기다 · t 를 다시 지었는데 옛 `t__lines` 가 남았다(`ORPHAN_REFUSAL`). 그 밖에 잠금을 못 잡음 · 인덱스를 못 지음. 거절된 표 전부가 `LineTablesRefused` 하나로 올라간다 — 부팅은 멈추고 선언 저장은 거절된다.
- t: 오늘 칸 + `won_by`. PG 는 bigint 배열로, 칸의 비트 자리마다 이긴 line_id 하나다. 수식이 보이는 칸은 `FORMULA_WON`(0), 이긴 줄이 없으면 NULL. sqlite 는 같은 목록을 JSON 으로 든다(`lines.py:won_by_type`). 읽고 쓰는 길은 `won_by_cells` · `won_by_stored` · `won_by_of` 뿐이다. 인덱스는 오늘 그대로다.
- `t__lines` (`lines.py:shape`):
  - 줄 칸: line_id(PK, 늘기만 함) · line_kind · source_name · at · written_by · batch(= transaction_id) · input_row · owner_rule · owner_key · confirmed · `written_N` · `head_N` · `withdrawn_N`(칸 64 개에 bigint 하나).
  - t 의 칸: row_id · business_key_val · created_at · updated_at, 그리고 선언 칸은 `v_<칸>` 이다(`value_column`). 값 칸은 선언 타입과 무관하게 글자다 — 쓸 때 `crud.line_text`, 읽을 때 `crud.line_value`.
  - 인덱스: `_ra`(row_id, at) · `_b`(batch) · `_p`(사람 줄의 at) · `_h`(row_id, source_name, 머리 비트 ≠ 0. 묶음이 늘면 `_h2` …) · `_i`(input_row, NULL 아님).
- 줄 종류(`write_lines.py:LINE_KINDS`): write(값을 말함) · withdraw(말 없음) · deleted(행 지움) · created(값 없이 행 만듦) · mark(고정 · 다시 합치기 · 병합 표시).
- 비트: write 는 말한 칸을 written · head 에, withdraw 는 written · head · withdrawn 에 적는다. 같은 (행, 출처)의 앞선 줄 머리는 쓰기 4 가 내린다.
- `line_columns`(표 · 비트 · 칸 · retired_at): 칸 → 비트 자리. 저자는 `assign_bits` 하나이고 자리는 다시 쓰지 않는다.
- `line_sources`(source_name · ranks_as · copy_of): 순위가 읽는 출처 이름. 키 병합이 옮긴 층은 copy_of 에 원래 이름을 든다(`note_sources`).
- `audit_batches`(transaction_id · table_name · written_by · work_kind · at): 감사 한 행.

## 저장 규칙

- 한 규칙 `lines.py:_autovacuum`: scale 0.02 · threshold 50 · 상한 `autovacuum_vacuum_max_threshold`(PG 18) · cost_limit 2000 · vacuum_truncate false.
- 상한은 ingestion_settings.json 에서 온다. 줄 표는 `lines_autovacuum_threshold`(기본 50,000, `line_storage`), 선언된 t 는 `table_autovacuum_threshold`(기본 100,000, `table_storage`). null 이면 손대지 않는다. t 는 table_config 의 «storage» 칸이 이긴다.
- 거는 자리는 `runtime/maintenance_line.py` 다.

## 쓰기

`write_lines.py:write_lines(db, table, items, *, kind, transaction_id)` 하나가 모든 쓰기를 맡는다. 부르는 쪽의 트랜잭션 안에서, 묶음마다 몇 문장이지 행마다가 아니다.

1. 잡기(`_claim`): 있는 행은 row_id 순으로 FOR UPDATE. 키로 이름 댄 항목은 잠금 안에서 키를 묻는다(`key_owners` — 그 키를 가진 가장 작은 row_id). 아무 행도 안 가진 키는 여기서 row_id 를 받고 5 가 값과 같이 한 번 INSERT 한다. sqlite 는 트랜잭션을 BEGIN IMMEDIATE 로 연다(`_open`).
   - 버전 판정(`_version_gate`), 그리고 이력 없는 칸(`_plain` — `crud.keeps_history` 가 아니라고 답한 칸)은 줄 없이 t 로 간다.
2. 빼기(`_leave_out`): 아무것도 바꾸지 않는 항목을 뺀다.
3. 줄(`_lines`): 남은 항목마다 줄 하나, 한 문장(`lines.insert_lines`).
4. 머리 비트(`_heads`): 같은 (행, 출처)의 앞선 줄 머리를 내린다. 고정 표시는 `_marks`.
   - 지운 행은 t 에서 DELETE 한다.
5. 지금 값(`_merge_now`): 이 쓰기가 손댄 칸만 `lines.merge` 로 다시 합쳐 t 에 쓴다(won_by 같이). updated_at 은 새 행이거나 보이는 값이 움직인 행만 바뀐다(`_moved`).
   - 새 행은 키 인덱스가 서 있으면 ON CONFLICT DO NOTHING 으로 넣는다. 그 사이 다른 쓰기가 같은 키를 넣었으면 이 쓰기의 줄이 그 행으로 간다(`_take_over`).
5½. 키 다시 짓기(`_rekey`): 키 칸 값이 움직인 행은 키를 다시 짓고, 그 키를 다른 행이 쥐면 그 행으로 합친다 — «업무 키가 바뀔 때».
6. 감사(`_audit`): (작업 종류, 누가)마다 `audit_batches` 한 행.
7. outbox(`_stage`): 같은 트랜잭션에 CREATE · EDIT · DELETE 사건. 방송과 같은 답을 읽는다.

표기 소급은 새 줄을 쓰되 «언제»(at)는 고친 줄의 것을 그대로 둔다 — 순위가 안 바뀐다. 그 줄은 새 손이 아니라서 고정 · 사람 표시를 옮기지 않는다(항목의 `at` · `respelled`).

줄을 안 갖는 표는 t 만 쓴다 — 지움 · 만듦 · 다시 합치기는 그대로 하고, 줄과 감사 행은 없다.

## 순위로 합치는 법

- 한 순서 `crud.py:rank_terms`. `lines.merge` 와 `crud.compute_priority_value` 가 같은 항 목록을 `lines.rank` 로 걷는다.
  1 선언 순위 → 1a 키 병합이 옮긴 층(copy_of)은 그 행 자신의 층 뒤 → 1b 우선순위를 말한 규칙 → 1c 작은 우선순위 → 1d 나중 선언된 규칙(그 칸에 주인 없는 체인 층이 있으면 0) → 2a 날짜 있음 → 2b 최신 → 2c 같은 순간이면 나중 줄(line_id) → 3 출처 이름.
- 고정(cell_overwrites)은 순서 앞에서 이긴다 — 고정한 출처의 머리 줄만 후보로 남는다.
- `lines.py:merge` 는 머리 줄을 1,000 행마다 한 번 읽고 파이썬에서 순위를 매긴다. 답은 셋이다.
  - 어떤 줄도 말한 적 없는 칸: 빠진다 — t 의 값이 남는다.
  - 고정한 출처에 머리 줄이 없는 칸: 빠진다 — t 의 값이 남는다.
  - 말했지만 후보가 없는 칸(모두 거둠): (None, None).

## 업무 키가 바뀔 때

- 키 칸 쓰기 · 키 다시 짓기는 옛 규칙 그대로다(`crud.rebuilt_business_key` · `crud.compose_business_key`, 빈 값은 키를 안 바꾼다).
- 바뀐 키를 다른 행이 쥐면 그 행으로 합친다(`write_lines.py:_merge_into`). 쓰기 · `merge_rows`(표기 소급 · `rebuild_blank_business_keys --apply`)가 같이 부른다.
  - 이기는 값은 옛 병합 판단 그대로다. 사람 대 사람 칸은 키 주인의 값을 «user (old_exist_…)» 로 남긴다.
  - 합쳐지는 행의 줄은 키 주인 row_id 로 옮기고 출처 이름은 `crud.merged_layer_name` 으로 바꾼다. 키 주인에는 mark 줄 하나를 남긴다.
  - 합쳐지는 행의 t 행과 고정은 지운다.

## 지움 · 거두기

- 행 지우기 = deleted 줄 + t 행 DELETE. 같은 키가 다시 오면 새 row_id 다.
- 거두기 = 그 출처의 withdraw 줄 + 다시 합치기. 원천 행이 먹인 칸은 `lines.py:stamped_by`(`_i` 인덱스)가 답한다.
- 체인이 자기가 낸 행을 거둘 때, 행을 붙드는 것이 없으면 행을 지운다(`chain/cell_layer.py:person_rows`).

## 칸 DDL

- `lines.py:alter_columns(db, t, cfg, add)`: t 와 `t__lines` 에 같은 칸을 같은 순서로 한 트랜잭션에서 더한다. 그것뿐이다.
  - 타입 바꾸기는 admin/retype 이 t 에만 건다(줄 값은 글자).
  - 지우는 길은 없다. 선언에서 뺀 칸은 살아 있고, 이름 바꾸기는 새 칸(새 비트)이다.
- 머리 묶음이 늘 때 PG 의 `_h` 는 이 트랜잭션 밖에서 `head_index` 가 CONCURRENTLY 로 짓는다.

## 읽기 — D 분야

- 그리드 · 걷기 · 원장 · 체인은 t 를 그대로 읽는다.
- 머리 줄 읽기는 `lines.py:layers` 하나다. 답은 cell_sources 모양 그대로이고 거둔 칸은 빠진다. 체인의 칸 상태는 cell_layer 가 `lines.layers` · `lines.built_lines` 로 읽는다.
- 행 · 칸 이력은 `t__lines` 의 write · withdraw · deleted · created 줄이다(`admin/audit_history.py:HISTORY_KINDS`). mark 줄은 이력 쪽에 안 나오고 감사 점프가 닿는다.

## 감사 로그

- 한 행 = (트랜잭션, 표, 누가, 작업 종류)(`write_lines.py:_audit`). 바뀐 행 수는 저장하지 않는다 — 그 트랜잭션의 줄(`_b`)에서 센다.
- 작업 종류: edit · new · delete · withdraw · merge · mark, 이주의 copy, 그리고 부르는 쪽이 정한 낱말(formula 등).
- 패널 클릭 → 그 트랜잭션의 줄 → row_id → 행.
- 칸의 쓰기는 `audit_batches` 로 간다. `audit_logs` 에 남는 것은 관문 시험(`AUDIT_EVENTS_ALLOWED` · `EVENT_COLUMNS`)이 허용한 자리뿐이다.
  - 칸이 아닌 기록(«*» 기록 · 영수증): `crud.create_audit_log` · `crud.bulk_insert_audit_logs` · `ledger/store._insert_audit_row`.
  - 칸 줄 하나: 순위 다시 합치기(R3)가 보이는 값을 바꾼 칸의 «전 → 후»(`chain/replay.py:_write_resolved`, 총괄 11-11 허용).

## 이주

- 명령 하나 `server/scripts/copy_layers_to_lines.py` — 서버를 끈 채 돈다(제품 프로세스가 붙어 있으면 거절).
  - 미리보기: 기본 동작이다.
  - `--estimate`: 시간 추정.
  - `--check`: 쪽마다 복사해 보고 되돌린다.
  - `--apply [--workers N] [--table t …]`: 옮긴다. `--rows <csv>`: 그 행들만 다시 옮긴다.
- 쪽마다 `line_migration.py:copy_page` 를 부르고 커밋한다. (행, 출처, ingested_at, updated_by, 주인)마다 write 줄 하나다.
  - 값은 오늘의 쓰기가 썼을 값이다(`crud.cast_value_by_type` → `crud.line_text`). 칸마다 시각이 지켜져 순위가 안 바뀐다.
  - t 의 값은 건드리지 않는다. won_by 는 줄 값이 t 값과 같을 때만 그 줄을 가리킨다.
  - 거절(`copy_refusal`): 객체 값 · 쓰기가 거절하는 값. 그 쪽은 한 줄도 안 옮긴다.
- 게이트: 옮긴 줄을 다시 합친 값이 t 와 다른 칸은 `copy_mismatch_<t>.csv` 에 적고 쪽은 착지한다(소유자 ㄴ). 그 칸은 t 의 값을 보이다가, 그 칸이 쓰일 때 줄들의 승자로 바뀐다.
- 이어 하기: 끊기면 다시 돌린다 — 표마다 마지막으로 커밋한 쪽 다음부터다(`copied_through`). 마지막 쪽이 감사 «copy» 행을 남기고, 그 표는 다시 부르면 `AlreadyCopied` 로 건너뛴다.
- 나중에 옮기기: 표 하나를 빼고 옮긴 뒤 나중에 `--table` 로 옮겨도 된다. 그 사이 쓴 칸의 머리는 그대로이고, 옮긴 줄은 그 밑 이력으로 들어간다(`copy_page`).
- 박스 리허설은 RUN.md 착지 블록에 있다.

## 되돌리기

- 옛 릴리스를 같은 DB 위에 띄운다(소유자 ㄴ). cell_sources 는 지우지 않았으므로 옛 코드가 그대로 읽는다.
- 박스에서 잰 모양은 RUN.md 착지 블록 ⑨ 에 있다. 착지 뒤 쓴 칸은 grid 에 그대로 보이지만, 셀 소스 · 이력은 옛 층만 보인다.
- 줄로 쓴 것을 cell_sources 로 되쓰는 함수는 없다.

## 11-14 관문 — 옛 두 표를 묻는 자리

관문은 AST 셈 시험이다. cell_sources 와 audit_logs 를 묻는 함수, 그리고 그 함수를 부르는 함수까지 센다. 허용 목록 밖은 0 이어야 한다.

```bash
python -m pytest -q server/tests/test_the_old_layer_and_audit_tables_are_asked_only_where_allowed.py
```

## 이 착지 밖

- 고정(cell_overwrites) 접기.
- 오래된 줄 정리.
- `t__lines` 의 물리 순서(CLUSTER · 읽는 순서).
- 사람 값의 신선도 표시.
- 선언의 원본을 시스템 표 행으로.
