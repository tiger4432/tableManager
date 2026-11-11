# 셀소스 갈아엎기

## 소유자 · 총괄 결정

- 11-10: 쓰기마다 줄이 쌓이고, 그 줄 표가 곧 이력이다(«메인 표가 곧 이력»). 개체마다 지금 값은 줄을 순위로 합친 값이다.
- 11-11: 표 t 는 그대로 «지금 값 표»다. 바뀌는 것은 칸 `won_by` 하나가 더해지는 것뿐이다. 이력은 옆 표 `t__lines` 에 있다. 이름 t 보기 · `t__now` · 트리거는 없다(11-10 의 «두 표 + 보기» 를 뒤집음).
- 11-11: 표는 둘 중 하나다.
  - «복사»: 운영자가 이름을 적은 표. `line_migration.copy_page` 가 옛 층(cell_sources)을 줄로 옮긴다. 소유자: «작은 인벤토리 표만 옮기면 됨».
  - «끊음»: 나머지 전부. 이력은 착지 뒤 쓰기부터 시작한다.
- 11-11: cell_sources 는 착지 뒤 차가운 보관이다. 쓰기 0 이고, 지우지 않는다.
- 11-11: 업무 키 유일 인덱스는 «업서트 용»이다(소유자 «비즈니스키는 업서트 용»). 줄은 row_id 에 묶이므로, 선언된 표는 키 인덱스가 없어도 줄 표를 가진다.
- 감사 로그 = 트랜잭션 · 표 · 누가 · 바뀐 행 수 · 작업 종류(+ 정렬용 시각). 값은 넣지 않는다. «전 값» 셈도 짓지 않는다.

수는 박스에서 잰 것이다(박스 NVMe 64 GB, 운영은 HDD 16 GB). 운영 크기로 잰 수는 없다. 센 명령을 못 붙인 수는 적지 않는다.

## 표 모양

- 어느 표가 줄을 갖나 — 한 좌석 `lines.keeps_lines(t, table_cfg)`: 운영자가 선언한 표(kind table)만. 보기 · 제품이 싣는 시스템 표 · 원장 자체 표는 그대로다.
- «줄이 지어졌나» — 한 좌석 `lines._catalogue(db, 표들)`: t__lines 가 있고 t 에 won_by 가 있다. 표가 몇 개든 카탈로그를 한 번 읽는다. `has_lines` 도 이것을 묻는다.
- 짓기 — 한 좌석 `lines.ensure_declared(engine, tables=None)`: 선언된 표마다 빈 t__lines + won_by 를 짓고, 칸이 늘면 따라잡는다. 부르는 곳은 스키마 동기화 · 키 인덱스 짓기 끝 · 시험 고정물이다. DDL 은 `db_safety.short_ddl`(잠금 기다림 상한)로 돈다.
  - 거절은 둘이다: t 를 다시 지었는데 옛 t__lines 가 남은 경우(ORPHAN_REFUSAL — 붙이지 않음), 잠금을 못 잡은 경우(다음 동기화가 다시 함).
- `t`: 오늘 칸 + `won_by`(JSON: 칸 → 이긴 line_id). 인덱스는 오늘 그대로다.
- `t__lines`:
  - 줄 칸: line_id(PK, 늘기만 함) · line_kind · source_name · at · written_by · batch(= transaction_id) · input_row · owner_rule · owner_key · confirmed · written_N · head_N · withdrawn_N.
  - t 의 칸: row_id · business_key_val · created_at · updated_at, 그리고 선언 칸은 `v_<칸>` 이다(`lines.value_column`). 줄 칸 이름(at · source_name …)과 부딪히지 않게 하려는 것이다(A 11-11, rq_memory.at). v_ 를 붙여 63 바이트를 넘는 이름은 거절한다.
  - 값 칸은 선언 타입과 무관하게 글자다. 쓸 때 `crud.line_text`, 읽을 때 `crud.line_value` 하나씩이다.
  - 인덱스: `_ra`(row_id, at) · `_b`(batch) · `_p`(사람 줄, at) · `_h`(row_id, source_name) WHERE 머리 비트 ≠ 0 · `_i`(input_row) WHERE input_row IS NOT NULL.
  - `_h` 의 이름은 머리 묶음 수를 든다(`head_index_name`: 묶음 하나면 `_h`, 둘이면 `_h2`). 65 째 칸으로 묶음이 늘면 PG 는 `lines.head_index` 가 키 인덱스와 같은 짓기 함수(`models._ensure_one_index_once`, CONCURRENTLY)로 새 것을 짓고 옛 것을 지운다. 그동안 쓰기는 막히지 않는다(e8b702177).
- 줄 종류: write(값을 말함) · withdraw(말 없음) · deleted(행 지움) · created(행 만듦, A) · mark(고정 · 다시 합치기 표시 — 세 비트 0).
- 비트: write 는 말한 칸을 written · head 에, withdraw 는 written · head · withdrawn 에 적는다. 같은 (행, 출처)의 앞선 줄 머리는 쓰기 4 가 내린다. deleted · mark 는 세 비트 0 이다.
- `line_columns`(표 · 비트 · 칸 · retired_at): 칸 → 비트 자리. 저자는 `lines.shape` 하나다. 지운 칸의 비트는 다시 쓰지 않는다.
- `line_sources`(source_name · ranks_as): 순위가 읽는 출처의 순위 이름.
- `audit_batches`(id · transaction_id · table_name · written_by · work_kind · at): 감사 한 행.
- `lines.shape(db, t, cfg)` → lines · bits · chunks · table · columns · kinds(저장 타입). 한 쓰기는 이것을 한 번 읽고 merge · layers · spoken 에 넘긴다(`s=`, A 11-11).

## 쓰기 — A 분야

`write_lines(db, table, items, *, kind, transaction_id)` 하나가 모든 쓰기를 맡는다. 한 트랜잭션 안의 문장들이고, 묶음마다 몇 번이지 행마다가 아니다.

1. 잡기: 있는 행은 row_id 순으로 FOR UPDATE. 새 키는 키 인덱스가 서 있으면 ON CONFLICT, 없으면 옛 길(읽고 INSERT)이다. 키 인덱스가 없으면 같은 새 키가 같은 순간에 오면 행이 둘이 될 수 있다(오늘과 같음, `lines.KEY_RACE`).
   - «K 의 주인 행» 은 `write_lines.key_owners` 하나가 답한다: K 를 가진 행 중 가장 작은 row_id(DB 정렬). 잡기 · 5½ · 표기 소급이 같이 부른다.
2. 빼기: 아무것도 바꾸지 않는 항목을 뺀다.
3. 줄: 남은 항목마다 줄 하나.
4. 머리 비트: 같은 (행, 출처)의 앞선 줄 머리를 내린다.
5. 지금 값: 손댄 행을 `lines.merge` 로 다시 합쳐 t 에 UPDATE(won_by 같이).
5½. 키 다시 짓기: 키 칸 값이 바뀐 행은 키를 다시 짓는다. 그 키를 다른 행이 쥐고 있으면 그 행으로 합친다(`_merge_into`) — 아래 «업무 키» 절.
6. 감사: (트랜잭션, 표, 누가, 작업 종류)마다 한 행.

## 순위로 합치는 법

- 한 순서: `crud.rank_terms` — 파이썬 쪽과 SQL 쪽이 같은 항 목록을 걷는다. 선언 순위 → 규칙 말함 → 규칙 우선순위 → 나중 선언(그 칸에 주인 없는 체인 층이 있으면 이 항은 0) → 날짜 있음 → 시각 desc → 이름.
- `lines.merge(db, t, cfg, row_ids, exclude_source=None, s=None)` 은 한 문장이다(`winners_sql`, 2fdbb8d3d). 고정은 그 출처의 머리 줄만 후보로 남긴다.
- 답의 세 경우:
  - 어떤 줄도 말한 적 없는 칸: 빠진다 — t 의 값을 그대로 둔다(«끊음»).
  - 고정한 출처에 머리 줄이 없는 칸: 빠진다 — t 의 값을 그대로 둔다(총괄 11-11).
  - 말했지만 후보가 없는 칸(모두 거둠): (None, None).

## 읽기

- 그리드 · 걷기 · 원장 · 체인은 t 를 그대로 읽는다.
- 머리 줄 읽기는 `lines.layers` 하나다. 답은 cell_sources 모양 그대로이고(value · ingested_at · updated_by · origin_row_id …), 거둔 칸은 빠진다(42efc9ab8).
- 체인의 칸 상태 · 사람 칸 · 규칙이 쓴 칸 · 철회 대상은 cell_layer 가 `lines.layers` · `lines.built_lines` 로 읽는다. 원천 행이 먹인 칸은 `lines.stamped_by(db, 표들, 원천 행)`(`_i` 인덱스)이다.
- 지운 행의 줄은 설계대로 남는다(이력). 산 행을 읽는 자리는 넘겨받은 행으로 거르고, 이력 읽기만 일부러 거르지 않는다. 철회가 «거둔 칸» 이라고 말하는 수는 write_lines 가 실제로 거둔 칸이다(a271f5726).

## 업무 키가 바뀔 때

- 키 칸 쓰기 · 키 다시 짓기는 오늘 규칙 그대로다(`rebuilt_business_key` · `compose_business_key`, 빈 키는 키를 바꾸지 않음).
- 바뀐 키를 다른 행이 쥐면 그 행으로 합친다(`write_lines._merge_into`, 쓰기 · 핀 · `merge_into_key_holders` 가 같이 부름).
  - 이기는 값은 옛 `_merge_into_key_holder` 의 판단 그대로다. 사람 대 사람 칸은 키 주인의 값을 «user (old_exist_…)» 로 남긴다.
  - 합쳐지는 행의 줄은 키 주인 row_id 로 옮긴다. write · withdraw 줄은 출처 이름을 `merged_layer_name(출처, 키_rowid)` 로 바꾼다.
  - 합쳐지는 행의 t 행은 DELETE 다(deleted 줄 없음). 키 주인에는 mark 줄 하나를 남긴다 — 옮긴 줄은 line_id 가 옛것이라, 되돌리기가 줄 번호로 키 주인을 찾게 하려는 것이다(총괄 11-11).

## 지움 · 거두기

- 행 지우기 = deleted 줄 + t 행 DELETE. 같은 키가 다시 오면 새 row_id 다.
- 거두기 = 그 출처의 withdraw 줄 + 다시 합치기. 체인 줄의 거두기 단위는 규칙 + 입력 행이다.
- 체인이 자기가 낸 행을 거둘 때 행을 붙드는 것 넷(사람 줄 · 핀 · 체인 아닌 작성자 · 그 행을 만든 체인의 값)이 없으면 행을 지운다(cell_layer.person_rows).

## 칸 DDL

- `lines.alter_columns(db, t, cfg, add, drop, retype)`: t 와 t__lines 에 같은 칸(이름 · 순서)을 한 트랜잭션에서 더하고 지운다. 타입 바꾸기는 t 만이다(줄 값은 글자).
- 머리 묶음이 늘 때의 `_h` 는 PG 에서 이 트랜잭션 밖에서 짓는다(위 «표 모양»).

## 복사 — 옛 층을 줄로 («복사» 표만)

- `copy_page(db, t, cfg, after, page_size, *, transaction_id, written_by)` → (옮긴 칸 수, 다음 행). B 의 소급 일 `migrate_to_lines` 가 쪽마다 부르고 커밋한다. 진행 줄의 단위는 칸(cells)이다(«12,400 / 380,000 cells · 2,100 cells/s · ~3 min left», B).
- (행, 출처, ingested_at, updated_by, 주인)마다 write 줄 하나다. 칸마다 시각이 지켜져 순위가 안 바뀐다.
- 값은 «오늘의 쓰기가 썼을 값» 이다: `crud.cast_value_by_type`(선언 타입) → `crud.line_text`(총괄 11-11, 39f780e94). 글자 칸의 JSON 1.0 은 «1», 글자 «1.0» 은 그대로다.
- 이미 그 칸의 머리가 있는 줄(착지 뒤 쓰기)은 복사한 줄이 머리를 갖지 않는다 — 이력으로만 들어간다.
- won_by 는 줄 값이 t 값과 같을 때만 그 줄을 가리킨다. 다르면 그 칸의 키를 남기지 않는다(표기 소급이 이것을 읽는다, A).
- 거절(그 쪽은 한 줄도 안 옮김, 한 함수 `copy_refusal` 이 문장을 지음): 객체 값 · 쓰기가 거절하는 값. RUN.md 에 두 문장과 «그대로 총괄에게» 가 있다.
- 처음부터 다시 부르면 `AlreadyCopied`, 끊긴 복사는 `copied_through` 다음 행부터 이어 간다. 마지막 쪽이 감사 «copy» 한 행을 남긴다.

## 감사 로그

- 한 행 = (트랜잭션, 표, 누가, 작업 종류). 바뀐 행 수는 저장하지 않고 패널이 그 트랜잭션의 줄(`_b` 인덱스)에서 센다.
- 작업 종류: edit · new · delete · withdraw · merge · mark · copy · declare + 데이터 아닌 기록 낱말.
- 패널 클릭 → 그 트랜잭션의 줄 → row_id → 행. 이 점프가 끊기지 않는 것이 게이트다.

## 되돌리기

- cell_sources 는 지우지 않는다.
- 되돌리기의 write_back 은 B 몫이다. 착지 뒤 줄 번호보다 큰 줄을 가진 행을 고른다(키 주인은 mark 줄로 잡힘, 총괄 11-11). 나머지 모양은 B 가 지을 때 정한다. 시간은 리허설에서 잰다.

## 위험 — 박스에서 잰 수 (C 판 11-11 — C 의 scratchpad cb/, 저장소에 없는 도구 · 전후는 판 2)

- settle(표 없이 부르는 철회): 표당 약 24 ms, 표 1,183 개 한 바퀴 28.5 초(39f780e94). 카탈로그를 한 번에 읽게 고쳤다(8123a3895). 전후 수는 판 2.
- merge 1,000 행 × 30 칸: 1.71 초(줄 1M). 쓰기 IO 목표(1,000 행 ≤ 1.3 초)를 이것 하나가 넘었다. 한 문장으로 묶었다(2fdbb8d3d). 작은 판(줄 1 만) 1.27 → 0.90 초. 큰 판 전후는 판 2. 넘으면 다음 길을 계획으로 올린다.
- 인덱스 다섯 짓기: 줄 1M 7.9 초, 5M 28.7 초. 착지 때는 생기지 않는다 — 끊은 표는 빈 줄 표에 짓는다. 복사한 표는 INSERT 마다 인덱스를 고치는 비용을 내고, 그것은 안 쟀다.
- `_h` 다시 짓기: 5M 줄에서 3.6 초 동안 그 표의 줄 읽기 · 쓰기가 모두 막혔다(옛 길). CONCURRENTLY 로 바꿨다(e8b702177). 짓는 동안 쓰기가 기다리는지는 판 2 가 잰다.
- 복사: 작은 판에서 초당 약 7,500 칸이다. 박스 NVMe 수이고, 운영 HDD 는 안 쟀다.
- 쓰기 한 번의 카탈로그: shape 한 번 17.9 ms(표 1,183 개). 쓰기 한 번에 shape 1 번, 저장 타입 읽기 1 번으로 줄였다(68c8145ef + A a-shape-once).

## 이 착지 밖

- 선언의 원본을 시스템 표 행으로(소유자 11-10 ㄱ, 다음 라운드).
- 고정(cell_overwrites) 접기.
- 오래된 줄 정리.
- `t__lines` 의 물리 순서(CLUSTER · 읽는 순서).
- 사람 값의 신선도 표시(안 2).
