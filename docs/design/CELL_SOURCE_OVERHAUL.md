# 셀소스 갈아엎기

## 소유자 결정 (11-10)

- 표마다 보통 표 둘: `t__now`(개체마다 지금 줄 하나 — 쓸 때 줄들을 순위로 합친 값) · `t__lines`(쓰기마다 줄 하나 — 이력). 이름 t 는 `t__now` 를 읽는 보기다. (ㄱ2 «줄 + 쓸 때 합친 지금 줄»을, 뒤의 «두 보통 표» ㄴ 이 물리 모양으로 정했다 — 분할 ㄱ 은 뒤집혔다.)
- ㄴ1 — 개체 하나는 `t__now` 의 유일 인덱스 (row_id) · (business_key_val) 로 지킨다.
- ② — 체인의 거두기 · 도장 · 주인 읽기까지 줄로 옮겨서 착지한다. 착지(11-14 정오) 때 cell_sources 쓰기는 0 이다.
- 감사 로그 = 트랜잭션 · 표 · 누가 · 바뀐 행 수 · 작업 종류. 값은 넣지 않는다. 행 · 칸 이력의 «전 값» 셈도 짓지 않는다.

수는 박스 카탈로그 추정 · AST/grep 셈 · A/D 검토 · 박스 판에서 왔다. 운영 크기로 잰 수는 아직 없다. 센 명령을 못 붙인 수는 적지 않는다.

## 결론

- 쓰기마다 `t__lines` 에 줄이 쌓인다. 이 표가 곧 이력이다.
- 개체마다 `t__now` 에 순위로 합친 지금 줄이 하나 있다. 그리드 · 걷기 · 체인 읽기는 이름 t(보기)를 그대로 읽는다.
- 쓰기는 한 트랜잭션 안의 문장 여섯이다(«쓰기» 절). 칸마다 층을 견주는 파이썬은 없다.
- cell_sources 는 줄로 옮긴 뒤 쓰지 않는다.

## 표 모양 — 지금 → 바뀐 뒤

| 자리 | 담는 것 | 박스 크기(카탈로그 추정) |
|---|---|---|
| 표 t | 개체마다 한 행, 보이는 값 | 가장 큰 표 약 100 만 행 |
| cell_sources | 칸 × 출처 층 | 3,954 만 행 · 6.4 GB |
| cell_overwrites | 고정 | 14 만 행 |
| audit_logs | 보이는 값 바뀜 + 데이터 아닌 기록 | 753 만 행 · 2.8 GB |

(셈: C 의 scratchpad wl/box_sizes.py — pg_class.reltuples · relpages, 박스 읽기 전용. 저장소에 없는 도구)

바뀐 뒤, 표마다:

- `t__lines`: t 의 칸 + line_id(PK, 늘어나기만 함) · 줄 종류 · 출처 · 언제 · 누가 · 묶음(= transaction_id) · 입력 행 · 규칙 주인 · 확정 · written_bits · head_bits · withdrawn_bits.
  - 줄 종류: «write»(값을 말함 · 합치기 후보) · «withdraw»(말 없음) · «deleted»(행 지움) · «mark»(고정 걸기/풀기 · 순위 다시 합치기 — 네비용 표시, head_bits 0 · 합치기 후보 아님). old_exist 백업 줄은 그 출처 이름의 «write» 줄이다.
  - 비트: «write» 는 말한 칸을 written_bits 에 적고 head_bits 도 그것으로 시작한다. «withdraw» 는 거둔 칸을 written_bits 와 withdrawn_bits 에 같이 적고 head_bits 도 그것으로 시작한다(그 원천의 그 칸 머리가 «말 없음» 줄이 된다 — 앞선 머리는 «쓰기» 4 가 내린다). «mark» · «deleted» 는 세 비트가 모두 0 이고 «쓰기» 4 를 건너뛴다 — 고정을 거는 mark 줄이 사람의 머리 비트를 내리지 않는다.
  - 쓰기 하나 = 줄 하나. 칸마다가 아니라 «행 × 쓰기»마다 한 줄이고, written_bits 가 어느 칸을 말했는지 적는다.
  - 층은 줄 그 자체다. 그 칸의 head_bits 가 선 줄 = 오늘의 cell_sources 한 칸 층.
- 물리 이름 고정 (C 11-10 — D 가 lines.py 전에 가짜 데이터로 읽기를 시작할 수 있게): `t__lines` = line_id · line_kind · source_name · at · written_by · batch · input_row · owner_rule · owner_key · confirmed · written_N · head_N · withdrawn_N + t 의 칸(row_id · business_key_val · created_at · updated_at · 선언 칸). 인덱스 (row_id, at) · (batch) · 머리 줄 (row_id, source_name) WHERE head ≠ 0. `t__now` = t 의 칸 + won_by(JSON 칸 → line_id), row_id PK · business_key_val UNIQUE. 함수: `now_relation(t)` · `lines_relation(t)` · `shape(db, t, table_cfg)` · `ensure_line_table` · `drop_line_table` · `alter_columns(db, t, table_cfg, add, drop, retype)`. 파이썬 합치기 함수의 시그니처는 정렬 키 생성기와 같이 11-11 에 고정한다(아직 아님). 더 (D 물음 11-10): `line_columns` = table_name · bit · column_name · retired_at, bit 는 0 부터, 칸 c 는 `<family>_<bit // 64>` 의 (bit % 64) 자리. won_by = {칸: line_id} JSON. 감사 로그 = 새 표 `audit_batches`(오늘 audit_logs 는 칸 · 값마다 한 행이라 낟알이 다르다) — id · transaction_id · table_name · written_by(줄의 written_by 와 같은 낱말) · work_kind · at, 인덱스 (table_name, at) · (transaction_id). 신선도 칸(안 2)은 컨펌 뒤 이름을 정한다.
- `t__now`: t 의 칸 + won_by(jsonb 한 칸: 칸 → 이긴 line_id). 개체마다 한 줄.
- 이름 t = `t__now` 의 칸을 읽는 보기 — 오늘 t 의 칸 전부(row_id · business_key_val · updated_at 같은 시스템 칸 포함)이고 won_by 만 뺀다. 쓰기는 거절한다(«보기» 절).
- 오늘 t 의 인덱스는 `t__now` 에 그대로 짓는다. 그리드 정렬 · 필터 · 개수 · 쪽 넘김이 오늘 인덱스 모양을 그대로 탄다.
- `t__lines` 인덱스: (row_id, 언제) · (묶음) · 부분 인덱스 (row_id, 출처) WHERE head_bits ≠ 0.
- 이름: `lines.now_relation(t)` = «t__now», `lines.lines_relation(t)` = «t__lines», 어느 스키마에서나 같다. PG 이름 한도(63 바이트)를 넘는 t 는 그 함수가 거절한다(오늘 선언된 이름 중 닿는 것이 있는지 — 짓는 날 센다).
- 데이터를 읽는 자리(걷기 · 원장 소스 · 체인 · 내보내기 · 리포트)는 보기 t 그대로다. pg_class · pg_index · EXPLAIN 의 relname 을 표 이름과 견주는 자리(index_wants · catalogue_indexes · column_index_kinds · sort/search_column_states · ensure_auto_indexes · main.grid_model)는 `lines.now_relation(t)` 를 지난다(D 가 AST 로 센다).
- 원장 소스의 «뷰 거절»(ledger/setup_bundle.reads_a_row_table — 소유자 «운영에서는 뷰 안 써»): 판정은 선언 카탈로그(table_config.json 을 load_physical_catalog · _adapt_physical_catalog 가 읽음)의 kind 칸을 보고 PG 를 보지 않는다 (B 11-10). 이주는 table_config 를 건드리지 않는다(운영자 선언에 기계가 쓰지 않음) — 그래서 보기 t 가 된 선언된 표는 그대로 «table»이고 운영자 뷰(kind: view)는 그대로 거절된다. 판정 쪽 일은 0 이고, 시험 하나가 «선언된 표의 보기 t 소스는 참 · kind: view 소스는 거짓»을 고정한다. 착지 때 reads_a_row_table 을 묻는 자리를 AST 로 센다.
- PG 의 relkind 를 직접 묻는 자리는 보기 t 에서 답이 바뀐다: ledger/backfill._table_rows(r · p 가 아니면 None — 소급 줄의 전체 행 수 · 남은 시간이 사라짐)는 `lines.now_relation(t)` 를 센다 (B 몫, 이주 착지와 같이).

## 줄 칸 결정 (C · A 11-10)

- head_bits (A 안 3): 그 원천의 그 칸에서 아직 최신인 칸들. 새 줄은 written_bits 로 시작하고, 같은 (개체, 원천)의 앞선 줄들은 «쓰기» 4 단계(따로 한 문장)에서 그 비트를 내린다. 줄의 값 · 시각 · 출처는 안 바뀌고 이 칸만 바뀐다.
- withdrawn_bits: 그 원천이 그 칸에서 «말 없음». 사람이 비운 칸(값 NULL)과 구별한다.
- 비트 칸의 표현은 표 크기와 무관하게 하나다: bigint 묶음 — 비트 칸 셋마다 칸 64 개에 bigint 하나(`written_0` · `head_0` · `withdrawn_0`, 64 칸을 넘으면 `_1` …). 두 방언 모두 & | ~ 가 된다. 64 칸 넘는 표가 몇인지는 짓는 날 선언(table_config)에서 카나리아와 같이 센다.
- 칸 → 비트 자리는 `line_columns`(표 · 칸 · 비트) 카탈로그 표에 붙이기만 한다. 저자는 `lines.shape` 하나다. 칸이 지워져도 그 비트 자리는 다시 쓰지 않는다 — 옛 줄의 비트가 다른 칸을 가리키게 되므로. 시험이 이것을 단언한다(칸 지움 → 새 칸 → 새 비트).
- `line_columns` 를 새로 짓는 까닭 (총괄 조건 «칸마다 오래 사는 기록이 이미 있나»): 찾은 자리 — origin/main 1bbddc5e5 models.py 의 `__tablename__` 18 개 중 칸마다 한 행을 쥔 표는 없다(audit_logs · cell_sources · cell_overwrites 는 칸 이름을 «값»으로 들 뿐 칸의 수명을 쥐지 않는다). 칸 선언은 table_config(운영자가 적는 선언)에 있는데, 기계가 정하는 비트 자리를 운영자 선언에 쓰지 않는다. 칸 이름 바꾸기 이력을 쥔 자리도 없다(이름 바꾸기 = 지움 + 새 칸). 그래서 새 표.
- 표기 소급(fold_written_notation): 새 줄을 쓰되 «언제»는 고친 줄의 것을 그대로 둔다. 머리는 옮고, 순위는 안 바뀌고, 옛 줄도 남는다. 고친 때는 묶음이 가진다.
- 파일 층 접기: 같은 파일이 같은 내용을 다시 보냄(repeat)은 «쓰기» 2 단계에서 빠져 줄이 없다. 다른 파일이 같은 내용을 보냄(folded)은 줄을 남기고, «쓰기» 4 단계가 앞선 파일 원천 줄의 그 칸 머리 비트도 내린다 — 오늘 file_layer_fold 가 앞선 파일 층을 지우는 것과 같은 답이다.
- 줄을 직접 읽거나 합치는 자리는 셋: C 의 cell_layer 칸 상태 읽기 · C 의 파이썬 합치기 · A 의 쓰기 5 단계. 둘째와 셋째는 같은 정렬 키 생성기에서 나온다. 체인의 나머지는 이 셋을 부르기만 한다. 거두기 줄을 쓰는 것은 C 의 withdraw seat 하나다.
- 수식: 쓰기 5 단계가 두 겹이다 — 수식 아닌 칸을 먼저 합치고, 그 위에서 expression.to_sql 로 수식 칸. 수식의 수식은 오늘처럼 체인 연쇄가 다음 쓰기로 옮긴다(겹을 늘리지 않음). «방금 합친 값»과 오늘의 «저장된 값»이 갈리는 경우는 생성기 시험의 칸 하나로 잰다 (A).
- won_by (D): 쓰기 5 단계의 같은 UPDATE 가 적는다. 그리드의 칸 주인 · 색 규칙 «누가 썼나»는 이것을 읽고 층을 다시 읽지 않는다.

## 쓰기 — A 분야

`write_lines(db, table, items, *, kind, transaction_id)` 하나가 모든 쓰기(깔때기 · 체인 · 수식 · 거두기 · 지움 · 표기 소급 · 병합 · 고정 바꾸기)를 맡는다. 한 트랜잭션 안의 문장들이고, 묶음마다 몇 번이지 행마다가 아니다. 데이터 바꾸는 CTE 는 쓰지 않는다(sqlite 가 못 함) — 두 방언이 같은 문장을 돈다.

1. 잡기: 손댄 개체의 지금 줄을 잠근다.
   - 있는 개체: `SELECT … FROM t__now WHERE row_id IN (…) ORDER BY row_id FOR UPDATE`.
   - 새 개체: 키로 정렬해 `INSERT INTO t__now … ON CONFLICT (business_key_val) DO NOTHING`(정렬 — 두 쓰기가 새 키 둘을 반대 순서로 넣어 유일 인덱스 대기에서 교착하지 않게) 뒤 그 키들을 같은 잠금으로 다시 읽는다. row_id 는 여기서 정해진다 — 줄은 그 뒤에만 쓴다. 같은 새 키를 두 쓰기가 동시에 내면 둘째는 첫째의 지금 줄을 기다렸다 같은 row_id 로 이어 쓴다(고아 줄 없음). 오늘 `_is_business_key_unique_violation` 재시도의 일을 이 단계가 맡는다.
   - 지금 줄이 없는 row_id(이미 지워짐)로 온 거두기 · 지움 항목은 말없이 빠진다(할 일이 없다). 값 쓰기 항목은 거절한다 — 오늘 동작과 같은지는 A 가 시험으로 확인하고, 다르면 오늘 쪽을 따른다.
   - sqlite 에는 행 잠금이 없다(DB 쓰기 잠금 하나). SQLAlchemy 가 FOR UPDATE 를 sqlite 에서는 내지 않고, write_lines 의 트랜잭션은 sqlite 에서 BEGIN IMMEDIATE 로 연다(기다림이 SQLITE_BUSY 오류가 되지 않게 — 짓는 날 시험으로 확인). 방언 갈림은 이 잠금 둘이다.
2. 빼기(잠금 안): 아무것도 바꾸지 않는 항목을 SQL 로 뺀다(머리 줄 값 vs 들어온 값).
   - 쓰기 항목에만 건다. 거두기는 «그 출처가 그 칸의 머리가 아님»일 때만 빠진다 — 값 견주기로 빠지지 않는다(NULL 머리 줄을 거둘 때 NULL = NULL 로 빠지면 거둔 줄이 계속 말한다). 지움은 1 에서만 빠진다.
   - 정답지: s4(착지 안 함, 소유자 11-10 ㄱ)의 crud.file_cell_verdict 판정과 시험 test_a_files_unchanged_rows_are_left_out_before_the_lock (C 작업 트리, 커밋 안 함). 까닭 — s4 판(박스 10 만 행 · 층 300 만 · 1,000 행 × 30 칸, wl/run_s4_board.sh): 같은 내용 묶음 2.962 → 2.732 s, 그중 파이썬 칸마다 판정 2.66 s(DB 읽기 0.07 s).
   - «같나»는 따로 생성기를 두지 않는다 (A 11-10): 쓰기가 어차피 하는 cast_value_by_type 뒤의 «저장 꼴»을 그 칸의 물리 타입(number → Float · datetime → timestamptz · 나머지 → text)으로 `IS NOT DISTINCT FROM`(빈 값 = NULL) 견주는 한 문장이다. 오늘의 crud.values_differ(캐스트한 값끼리)와 같은 답인지는 A 의 철자 표(number 23 · datetime 11 · string 14 가지, 짝 447 — 어긋남 0, 파이썬만 · DB 없이 잼)를 시험으로 고정해 지킨다. 남은 하나: 시간대 없는 datetime 글자를 PG 는 세션 시간대로, value_key 는 선언 시간대(expression.time_zone())로 읽는다 — write_lines 게이트의 PG 시험 «시간대 없는 글자 둘 → 같나»로 재고, 갈리면 캐스트가 선언 시간대를 단 값을 넘기는 쪽으로 맞춘다.
3. 줄: 남은 항목마다 `t__lines` 에 줄 하나 INSERT(written_bits · withdrawn_bits · 값 · 출처 · 언제 · 누가 · 묶음 · 입력 행 · 주인).
4. 머리 비트(«write» · «withdraw» 줄만): 같은 (개체, 원천)의 앞선 줄들 — 그리고 folded 판정이 가리킨 앞선 파일 원천의 줄들 — 의 head_bits 에서 새 줄의 written_bits 를 내린다(UPDATE 한 문장).
5. 지금 줄: 손댄 개체의 지금 줄을 머리 줄들 + 고정으로 다시 합쳐 `UPDATE t__now … RETURNING`. won_by 도 같이. 전/후 값은 1 에서 읽은 옛 지금 줄과 이 RETURNING 이다 — 방송 · outbox 가 같은 저자다.
6. 감사: 감사 로그 한 행 INSERT.

규칙 (A 11-10):

- 줄을 쓰는 함수는 하나다. 잠금(1)을 건너뛰는 자리가 생기면 오류 없이 머리가 둘 남는다. 게이트: 버리는 PG 에서 두 연결이 같은 개체(있는 개체 · 새 키 둘 다)에 겹쳐 쓰는 시험 하나 — 둘째가 오류 없이 기다렸다 이어 쓰고, 머리 줄 수 = 원천 수, 고아 줄 0.
- 잠금 순서는 오늘과 같은 row_id 순이다. 한 트랜잭션이 표 여럿을 쓸 때의 표 순서는 오늘도 정해져 있지 않고 이번에도 바꾸지 않는다 — 오늘의 교착 위험이 그대로 남는다(안 쟀다).

위험: 줄은 값이 실제로 바뀔 때만 쌓인다(2 가 아무것도 안 바꾸는 쓰기를 뺌 — 소유자 짚음). 5 의 합치기는 머리 줄(원천 수)만 읽는다. 행 이력 한 쪽은 그 행의 줄 수에 비례하므로, 값이 자주 실제로 바뀌는 행의 이력 읽기를 깊이 판으로 잰다.

## 감사 로그 (소유자 11-10 «감사로그 그냥 트랜잭션, 테이블별, 누가 바꿨는지, 바뀐 행수, 바뀐 작업 타입 이것만 있으면 됨»)

- 한 행 = 쓰기 문장 묶음 하나. 저장하는 칸은 넷: 트랜잭션 · 표 · 누가 · 작업 종류. 다섯째 «바뀐 행 수»는 저장하지 않고 패널이 줄에서 센다(아래). 값은 넣지 않는다.
- «언제»(기록 시각)는 네비 정렬용 배관이다 — 다섯 칸에 값을 더하는 것이 아니다 (총괄 11-10).
- 작업 종류 = 그 쓰기가 «무엇을 했나». write_lines 가 «쓰기» 1(잡기)에서 이미 아는 것이다 (총괄 11-10): «edit»(있던 행 고침) · «new»(새 행) · «delete»(지움) · «withdraw»(거두기) · «merge»(키 병합) · «mark»(고정 걸기/풀기 · 순위 다시 합치기). 한 묶음에 여럿이 섞이면 종류마다 감사 행 하나다. «누가»는 출처(적재 · 손 편집 · 체인 · 소급 …)를 오늘 낱말 그대로 든다.
- 바뀐 행 수 = 그 트랜잭션 · 그 표에서 줄을 쓴 서로 다른 row_id 수 (총괄 11-10, 소유자 낱말 그대로의 뜻). 줄은 무언가 바뀐 행에만 쓰인다(«쓰기» 2 가 아무것도 안 바꾸는 항목을 뺌) — 순위에서 져 보이는 값은 그대로인 쓰기(층이 바뀜)와 mark 줄의 행(고정이 걸리거나 풀림 · 순위로 보이는 값이 바뀜)도 «바뀐 행»에 든다. 패널이 `t__lines` 의 (묶음) 인덱스로 그 트랜잭션의 줄에서 센다 — 트랜잭션 크기에 묶인다. 저자가 하나라 쓰기마다 적은 수와 갈라질 일이 없다.
  - 키 병합이 옛 줄의 row_id 를 키 주인으로 바꾸므로, 지난 트랜잭션의 수가 병합 뒤에 줄 수 있다(두 행이 한 행이 됨). 지금의 개체 기준으로 센 수다 — 그 트랜잭션 당시의 수가 아니다.
- 목적은 네비게이션이다: 패널 클릭 → 그 트랜잭션의 줄(`t__lines` (묶음) 인덱스) → row_id → 행. 오늘의 행 점프(timeline.js navigator)가 끊기지 않는 것이 게이트다.
- 순위 선언 바뀜의 다시 합치기와 고정 걸기/풀기도 쓰기다 — 감사 행이 남고(종류 = 소급 · 핀), «mark» 줄 하나씩을 써서 점프가 닿는다 — 고정은 고정이 걸리거나 풀린 행마다(보이는 값이 안 바뀌어도), 순위 다시 합치기는 지금 줄이 바뀐 행마다. 고정 자체는 이 착지 밖이라 cell_overwrites 에 있다 — «mark» 줄은 합치기 후보가 아니다.
- 인덱스: 감사 로그 (표, 언제) · (트랜잭션).
- 감사 표는 착지 날 하나다 (총괄 11-10 조건): 새 표 `audit_batches` 가 감사 로그이고, audit_logs 는 그날 은퇴한다 — 쓰기 0, 읽기는 전부 audit_batches + 줄. 걸리는 것 하나(물음): «이 착지 밖» 첫 줄의 소유자 ㄴ(데이터 아닌 기록은 그동안 audit_logs 에 씀)과 «쓰기 0»이 같이 설 수 없다 — ㄱ 데이터 아닌 기록도 착지 날 audit_batches 로(작업 종류 낱말을 그만큼 더함) / ㄴ audit_logs 를 그 기록만의 표로 남김(감사 표 둘).
- 옛 audit_logs 행: 이주가 (transaction_id, table_name, 누가, 작업) 묶음마다 audit_batches 한 행으로 접는다 — 네비는 줄 표의 (묶음) 인덱스로 닿는다(이주 3 단계의 옛 줄이 같은 transaction_id 를 든다). 옛 표는 이름을 `audit_logs__old` 로 바꿔 되돌리기 창 동안 두고, 아무도 읽지 않는다.
- audit_logs 를 묻는 자리 (origin/main 2b09c2bdf 의 server/, 시험 밖 함수, AST — AuditLog 이름 또는 «audit_logs» 문자열. 카나리아 `def create_audit_log` 1. 셈 명령: C 의 scratchpad wl/census_audit_logs.py — 저장소에 없음): 44 함수. 읽기/쓰기 갈래는 본문 낱말로 가른 짐작이다.
  - 쓰기 (10): crud.create_audit_log · crud.bulk_insert_audit_logs · crud._merge_into_key_holder · ledger/store._insert_audit_row · chain/replay._write_by_values · admin/audit_cache._merge · scripts/migrate_to_postgres.migrate · scripts/probe_ingestion_stages.run · .report · setup/seed_data.clear_db
  - 감사 패널 · 이력 탭 · 행 이력: main.get_transaction_logs · get_recent_audit_logs · get_row_history · get_cell_history · _history_page · grid_read.transaction_rows · admin/audit_cache 의 여덟(load_initial · refresh_if_stale · _ordered_rows · _resolve · _tally · _count_by_transaction · _chunk_edge · _groups_seen_at_or_above)
  - 지운 행 · 업무 키: crud.deleted_rows · main.get_deleted_row_business_key · get_deleted_rows_business_keys_bulk · resolve_missing_business_keys · create_row · delete_rows_batch_endpoint · _create_and_collect · _delete_and_collect — «deleted» 줄(업무 키를 든다)로 옮긴다
  - Overview 재교정 · 공수: crud.get_recorrection_stats · get_effort_stats — 감사 행이 아니라 줄(written_by · 작업 종류)에서 센다
  - 소급 · 체인: chain/replay._fold_units_page · chain/ingestion_worker._report_layer_table_health
  - 이름만 드는 자리(인덱스 · 통계 · 진단 · 정적): admin/schema_drift._declared_kind · migrations/drop_redundant_layering_indexes.stats_are_trustworthy · scripts/ops_setup_db_performance.setup_performance · scripts/check_missing_business_key._report · scripts/diagnose_slow_after_ingest 의 둘 · setup/init_db.setup_database · main.serve_static_or_index
- 깊이 판에서 잴 것: 뜨거운 행의 행 이력 한 쪽 초 · «트랜잭션 → 줄» 읽기 초(큰 적재 한 트랜잭션) · 하루에 몇 줄 · 몇 MB.

## 업무 키가 바뀔 때 (소유자 11-10 «비즈니스키는 어케 처리됨») — 오늘 동작을 옮긴다

- 찾기: `t__now` 의 business_key_val. 새 키는 «쓰기» 1(ON CONFLICT). 지운 뒤 같은 키는 새 row_id(«지움» 절).
- 키 칸 손 편집 · 키 칸 쓰기: 오늘 `_update_row_business_key` 와 같다 — 그 줄이 키 칸을 쓰고 «쓰기» 5 가 business_key_val 을 바꾼다. 빈 값은 키를 바꾸지 않는다. row_id 는 그대로다.
- 키 다시 짓기: 오늘 `rebuilt_business_key` + `put_business_key` 그대로. 빈 키 채우기는 `fill_nokey_keys` 그대로.
- 바뀐 키가 다른 지금 줄과 부딪힘: row_id 를 키 주인 한쪽으로 몬다 (소유자 11-10 «합쳐지면 rowid를 한쪽으로 몰아야»).
  - 오늘 `_merge_into_key_holder` 가 병합 뒤 남기는 층을 1:1 로 옮긴다 — 오늘 남는 층 하나 = 같은 출처 이름의 머리 줄 하나. 키 주인의 사람 층을 살려 두는 `merged_layer_name(USER_SOURCE, "old_exist_…")` 층도 그 이름의 머리 줄로 남는다(사람 층 보존). 어느 값이 이기나(`explicit` · `human_columns`)는 그 함수의 판단 그대로다.
  - 합쳐지는 쪽 행의 줄 전부를 키 주인 row_id 로 옮긴다(`t__lines` 안의 UPDATE — 출처 · 언제 · 누가 · 값은 그대로). 합쳐지는 쪽 row_id 의 지금 줄은 DELETE 다.
  - 병합 트랜잭션은 오늘의 폴백 층을 줄로 쓴다(묶음 = 그 트랜잭션). 그래서 병합의 감사 행에서도 점프가 닿는다.
  - 잠금: 키 주인은 키를 계산한 뒤에야 안다. 껍데기와 키 주인을 row_id 순으로 같이 잡는다 — 그래도 «키 계산 뒤 잡기»는 다른 쓰기와 교착 경로다. 오늘과 같은 위험이고 이번에 바꾸지 않는다.
  - 고정(이 착지 밖)은 오늘처럼 cell_overwrites 에서 옮긴다.
  - 같은 몸통 하나를 오늘처럼 쓰기 자리 · 핀 자리 · `merge_into_key_holders`(rebuild_blank_business_keys --apply, 표기 소급)가 부른다.
  - 이주 전 audit_logs 의 옛 row_id 줄은 손대지 않는다(오늘도 병합된 껍데기의 audit 줄은 없는 행을 가리킨다).
  - 크기: 안 쟀다.
- 오늘과 다른 곳: 합쳐지는 쪽의 이력이 키 주인 밑으로 따라온다(오늘은 껍데기 행과 함께 지워졌다). 이긴 값 · 남는 층은 오늘과 같다.

## 줄 표의 물리 순서

- 판정: 소유자 11-10 ㄴ «ㄴ 이 낫지 직관적이고» — 두 보통 표 `t__now` · `t__lines`. PG 부모 · 분할 · ATTACH · is_now 칸은 없다(앞의 분할 ㄱ 을 뒤집음). 두 방언의 DDL 이 같다.
- 까닭(총괄 11-10 물음 — A 의 노테이션 판, A 가 잰 수): 한 heap 에 지금 줄과 이력 줄이 섞이면 이력이 쌓일수록 지금 줄이 묽어져 그리드 읽기가 나빠진다. `t__now` 는 오늘 t 처럼 개체당 한 줄로 촘촘하다.
- 줄이 표를 넘어 옮겨지는 일은 없다(A 11-10): 줄은 `t__lines` 에 INSERT, 지금 줄은 `t__now` 에서 제자리 UPDATE, 지움은 «deleted» 줄 INSERT + 지금 줄 DELETE, 키 병합의 줄 옮기기는 `t__lines` 안의 UPDATE.
- `t__lines` 의 머리 줄 합치기 · 행 이력 읽기는 오늘 cell_sources 와 같은 흩어짐이다. 그 순서(CLUSTER (row_id, 언제) · row_id 정렬로 읽기)는 다음 라운드이고, 깊이 판에서 차가운 캐시로 잰다.

## 칸 DDL — 한 함수

- `lines.alter_columns(db, table_name, changes)`(C 몫 · 총괄 11-10): 한 트랜잭션에서 «보기 t · 트리거 지움 → 두 표에 같은 칸 DDL(더하기 · 타입 바꾸기 · 지우기 · 이름 바꾸기) → 보기 t · 트리거 다시 지음». PG 는 보기가 기대는 칸의 타입 바꾸기 · 지우기를 거부하고, 더한 칸은 보기에 안 나타나기 때문이다(PG 일반 동작 — 짓는 날 버리는 DB 시험으로 확인).
- 표 만들기는 `lines.ensure_line_table`(두 표 · 보기 · 트리거 · 인덱스). 표 지우기는 `lines.drop_line_table`(보기 · 두 표 · 있으면 `t__old`).
- 운영자에게 «손으로 돌릴 줄»로 보여 주는 DDL 문장(schema_drift · list_undeclared_tables)도 이 함수가 낸 문장을 그대로 보인다.
- 지나야 할 자리 — A 셈, origin/main 8151d231e(문자열 grep + AST, 카나리아 models.py create_all = 1):
  - 칸 DDL: models.sync_dynamic_tables_schema 의 ADD COLUMN · models.create_missing_dynamic_tables 의 create_all(표 만들기 → ensure_line_table) · admin/retype.py 의 ALTER COLUMN TYPE + 그 칸 인덱스 DROP · admin/schema_drift._add_column_ddl · scripts/list_undeclared_tables.py.
  - 표 모양: models.init_dynamic_models(Table · append_column · 인덱스 둘) — 두 Table 이 여기서 같은 칸 목록으로 나온다. models.model_index_ddl(CreateIndex).
  - 메타데이터 전체 만들기/지우기: main.bootstrap_database_schema · setup/init_db 의 create_all · setup/reset_db 의 drop_all — 보기 · 트리거는 create_all 이 짓지 않으니 ensure_line_table 이 이 셋을 따라간다.
  - 칸 아닌 DDL 은 `t__now` 에 건다: 자동 인덱스 · gin 검색 인덱스 · 남은 인덱스 지우기 · decide 키 인덱스 안내 · chain/unique_key 의 조인 키 유일 인덱스 · notation_norm 의 접은 값 식 인덱스.
  - 저장 매개변수: 선언된 «storage» 는 `t__now` 에 건다(제자리 UPDATE 의 표). `t__lines` 는 덧붙이기만 하는 표라 PG 기본값(C 판단).
- 칸 어긋남 가드: 부팅 때 두 표의 칸 목록을 견주어, 갈라졌으면 그 표의 쓰기를 거절하고 한 줄로 말한다(데이터를 지키는 가드).

## 이름 t 보기는 쓰기를 거절한다 (총괄 11-10 ㄱ)

- PG 단순 보기는 쓰기가 되고 sqlite 보기는 안 된다 — 그대로 두면 직접 쓰기가 PG 에서는 줄 구조를 조용히 건너뛰고 sqlite 에서는 터진다.
- 두 방언 모두 보기 t 에 INSTEAD OF 트리거를 두어 쓰기를 거절한다. 오류 문장: «write_lines 를 지나라». 트리거가 줄 쓰기를 대신하지 않는다.
- t 에 직접 쓰는 자리 — A 셈(origin/main 9fb1d6907, AST, 카나리아 apply_row_update_internal 의 setattr · _get_or_create_row 의 db.add): 제품 25 자리(4 파일) · 시험 290 자리(114 파일) · 스크립트 8 자리. 제품은 write_lines 를 직접 부른다.
- 시험: flush 훅(database.write_changed_rows_by_shape)이 «씨앗 문맥» 안에서만 동적 모델의 add · 속성 대입 · session.delete 를 write_lines 로 넘긴다(종류 «seed», 출처는 행의 source 칸). 문맥 밖이면 «write_lines 를 지나라»로 거절한다 — 제품의 놓친 직접 쓰기가 조용히 줄이 되지 않게 (총괄 11-10). query().update/.delete · 원문 SQL 은 손으로 옮긴다. 시험 본문(test_* 함수 자체가 직접 쓰는 것 118 개 · 73 파일 — A 셈, 같은 AST 셈의 갈래)의 심는 줄 감싸기는 A 의 레인 에이전트(시험 파일만).
- PG 시험 44 파일(A 셈: 직접 쓰는 114 파일 중 mark.pg 가 붙은 파일, pg_engine 고정물 scope="session")은 한 DB 를 같이 쓰고 손으로 치운다 — 정리 자리는 «DROP TABLE t» 대신 `lines.drop_line_table` 을 부른다. 놓친 «DROP TABLE t» 는 보기라서 터진다.

## 들어온 철자 (소유자 11-10 «ㄱ»)

- 표기 접기 칸의 «들어온 철자»는 버린다. 줄에 칸이 없고 audit_logs 에도 안 쓴다. 착지 때 crud 의 `_written_spelling` → create_audit_log 자리가 은퇴한다.
- 은퇴 때 그 약속을 든 자리를 같이 지운다. origin/main 에서 낱말로 센 자리: crud.py 2 · schemas.py 1 · chain/replay.py 1 · RUN.md 한 블록 · docs/guide/config/notation_rules_config.md «이력» 줄 · CODE_MAP «쓰기 접기» 줄 · 시험 test_a_key_handed_back_in_another_shape_names_its_row.py. 그 감사 줄을 «성질»로 단언하는 시험은 착지 때 시험이 빨개지는 것으로 다시 센다.

## 지움 · 거두기 (소유자 11-10 «지우기는 ㄱ»)

- 사람이 그리드에서 지우는 행 지우기 = «deleted» 줄 INSERT + `t__now` 의 지금 줄 DELETE. 이름 t 에서 바로 사라지고, 이력 · 감사 점프는 남는다.
- 같은 business_key 가 다시 오면 새 row_id 로 지금 줄이 선다. 오늘 «DELETE 뒤 INSERT»와 같은 결과다.
- 표 행 DELETE 와 delete_row_layers 의 cell_sources 지우기는 없어진다. 고정(이 착지 밖)은 오늘처럼 cell_overwrites 에서 지운다.
- deleted_rows(«지워졌나»)는 줄 종류 «deleted» 를 읽는다 (D). 감사 행 = 종류 «지움» · 바뀐 행 N. 체인 대기열의 DELETE 사건은 오늘 그대로 (A).
- 거두기 = 그 출처의 «withdraw» 줄(withdrawn_bits) + 지금 줄 다시 합침.
- 체인 줄의 거두기 단위 = 규칙 + 입력 행 (소유자 11-10 «체인 규칙 + 낸 행으로»). 원천 행 S1 이 사라지면 «규칙 R · 입력 행 S1» 인 머리 줄만 거둔다. 같은 규칙이 S2 로 그 칸을 이미 다시 썼으면 거둘 것이 없다. 오늘의 cell_layer.cells_stamped_by(그 입력 행이 먹인 칸 중 그 출처의 최신이 아직 그 입력 행인 것)와 같은 답이다.
- 집계 줄(decide 집계 · take fn — 오늘 근거 행을 안 남기고 층 이름 «규칙 + 키»만 남김, 총괄 11-10 A 의 5d1f98b3a 읽기): 입력 행 칸 하나로는 근거 목록을 못 담는다. 집계 줄은 규칙 + 키를 들고, «어느 행 때문에 이 판정이 났나»는 원천 표의 줄(이력)에서 그 줄의 시각으로 다시 짓는다 — 따로 목록을 저장하지 않는다.
- 체인이 자기가 낸 행을 거둘 때(소유자 11-10 «체인이 낸 행 부분만 없애면 됨»): 그 체인 출처의 줄만 거두고, 행을 «붙드는 것»이 남지 않았을 때만 «deleted» 줄 + 지금 줄 DELETE. 판정은 오늘의 cell_layer.person_rows 한 함수 «무엇이 이 행을 붙드나»를 줄로 옮긴 것이다(release-2026-11-10d 96e0fa44d 부터 shells · delete_shells · ingestion_worker._settle 이, 10i 5ea5e3ec0 부터 소급 «Remove rows with no source left» 도 이것을 부른다). 붙드는 것 넷: ① 사람 줄(빈 것 포함 — 출처를 crud.layer_writer 로 접어 «user» 인 줄, 그래서 키 병합의 «user (old_exist_…)» 백업 줄도 사람 몫이다) ② 핀 ③ 체인 아닌 작성자(파일의 키 줄 또는 값) ④ 그 행을 «만든» 체인의 값 — 줄에서는 «그 출처의 줄이 그 행의 키 칸을 written_bits 에 든 적이 있나»로 읽는다. 다른 체인이 «붙이기만» 한 값은 행을 붙들지 않는다(소유자 공식 마스터 모양: 체인 1 이 거두면 체인 2 의 값과 같이 지워지고 체인 2 는 DELETE 를 받는다). 시험: 키 병합 뒤 백업 줄만 남은 행이 체인 거두기에 지워지지 않는다(A 쓰기 몫).
- 오래된 줄 정리: 이번 착지 밖 — 다 남긴다. 운영 크기를 잰 뒤 다시 본다.

## 읽기 — D 분야

- 그리드 · 걷기 · 원장 번역 · 체인 읽기: 보기 t 를 그대로 읽는다. row_id 를 부르는 함수는 지금 줄이 개체당 하나라서 뜻이 그대로다(셈: C 의 scratchpad wl/row_id_census.py, origin/main 018babf90 — 저장소에 없는 도구).
- 층 표시 · 행 이력 · 칸 이력: `t__lines` 를 (row_id, 언제) 인덱스로 읽는다. 보이는 행 수에 묶인다.
- 이력은 줄이 적은 값만 보인다. «전 값» 셈은 짓지 않는다(소유자). 이력 봉투(schemas.AuditLogResponse)에서 old_value 칸을 지운다(총괄 11-10 — 소유자 «감사로그에 값을 넣지마 · 줄이려는데 왜 키워»). 그 칸을 읽는 클라 자리는 클라2 몫이다: client2/src/timeline.js 에서 old_value 를 읽는 자리 넷(값 그리기 둘 · 감사 종류 판정 auditKind 둘)과 주석 하나, client2/src/look_panel.js 하나 (origin/main e31816d34, git grep «old_value» client2/src, 카나리아 new_value = 3 파일).
  - auditKind(감사 알약)는 old_value 가 아니라 감사 행의 작업 종류 칸(+ «누가»)을 읽는다 (총괄 11-10 — 알약은 사라지지 않고 저자가 하나다). 클라2 몫: timeline.js 의 auditKind 두 자리 · 값 그리기 두 자리 · look_panel.js 한 자리를 «작업 칸을 읽어 알약»으로. OVERWRITE 알약은 «edit»(+ 사람 출처)에서 나온다.
- 방송 · outbox 의 옛 값(쓰기 1 의 옛 지금 줄)은 체인이 «바뀌었나»를 판단하는 기계 계약이라 그대로 둔다 (총괄 11-10). 이력 화면의 값이 아니다.

## 순위로 합치는 법

칸마다 다음 순서로 고른다.

1. 출처마다 머리 줄. withdrawn_bits 가 서면 «말 없음».
2. 고정이 있으면 고정.
3. 정렬 키 최소: 선언 순위 → 규칙 말함 → 규칙 우선순위 → 나중 선언 → 날짜 있음 → 시각 desc → 이름. 수식은 정렬 안의 후보 하나다 (A).

정렬 키는 선언된 항 목록 하나에서 SQL(쓰기 5)과 파이썬(검증 · 화면)이 같이 지어진다. 둘이 같은 답인지는 생성기와 같은 커밋의 시험으로 잰다(아직 안 쟀다). 순위 선언이 바뀌면 그 표의 지금 줄을 다시 합친다(오늘 `recompute_display_values` 와 같은 크기의 소급).

## 셀소스 · 감사 이력 · 고정이 어디로

- cell_sources: 이주 때 줄로 옮긴다(«이주» 3). 착지 뒤 쓰기 0.
- audit_logs: 칸 변화는 이 착지부터 안 쓴다. 이주 전 줄은 읽기 전용으로 보관한다. 데이터 아닌 기록(원장 · 수식 영수증 · 체인 큐 · 전체 리셋 · 만들기/지우기 · ROW_UPDATE 요약 · 통계 등)은 이 착지 밖이라 그동안 audit_logs 에 쓴다.
- cell_overwrites(고정)는 이 착지 밖이다. 그동안 남고, 쓰기 5 의 합치기가 읽는다.

## cell_sources 를 묻는 함수 — 옮길 자리

origin/main 93bb81aa7 의 server/ 에서 시험 밖 함수를 AST 로 셌다. 셈 명령: C 의 scratchpad wl/census_cell_sources_askers.py origin/main (카나리아 `def compute_priority_value` = 1). 저장소에는 없는 도구다.

| 무리 | 함수 | 레인 |
|---|---|---|
| 체인 — 거두기 · 도장 · 주인 읽기 · 접기 | 34 | A (거두기 seat 은 C) |
| 쓰기 (crud) | 16 | A |
| 읽기 (grid_read · grid_look) | 3 | D |
| 스키마 · 저장 · 감시 | 11 | C (감시 2 는 B) |
| 스크립트 · 이주 · 씨앗 | 19 | C |
| 맵퍼 | 1 | A |
| 합계 | 84 (32 파일) | |

체인 34: chain/replay 12 · chain/cell_layer 9 · admin/retroactive 4 · chain/ingestion_worker 3 · chain/enrichment 3 · chain/rule_run 1 · dt_map_derivation 1 · maps/frame_confirmation 1.

## 이주

표마다 소급 일 하나(`migrate_to_lines`, 인자 table — B 안 ㄱ). 단계 여덟(0~7):

0. 표시 — 이주 창을 연다: 옛 t 와 그 표의 cell_sources 행에 AFTER INSERT/UPDATE/DELETE 트리거를 걸어, 바뀐 row_id 를 이주 기록 표(일련 id · 표 · row_id)에 남긴다. 옛 t 와 cell_sources 의 TRUNCATE 는 문장 트리거가 «표 전체» 기록을 남기고(cell_sources 는 여러 표가 같이 쓰므로 그 TRUNCATE 는 이주 중인 표 전부를 멈춘다), catch-up 이 그것을 보면 그 표의 이주를 멈추고 한 줄로 말한다(처음부터 다시). 그 표를 바꾸는 모든 길(지움 · 층 지우기 · file_layer_fold · replay 의 DELETE 포함)이 같은 트리거를 지나므로 «어느 길이 기록을 쓰나»에 기대지 않는다. PG 전용(운영 이주) — sqlite 시험은 새 구조로 처음부터 짓는다.
1. create — `t__now` · `t__lines` 를 만든다.
2. now rows — 옛 t 의 행을 `t__now` 로(값 그대로).
3. old lines — cell_sources 를 (표, 행, 출처, 시각)마다 «write» 줄 하나로 `t__lines` 에. 칸마다 다른 시각을 지켜 순위(«시각 desc»)가 안 바뀐다. 각 줄의 head_bits = 그 층이 선 칸들.
4. indexes — `t__now` · `t__lines` 의 인덱스를 «임시 이름»으로 짓는다(옛 t 의 인덱스와 이름이 부딪히지 않게 — swap 에서 이름을 바꾼다). merge check 앞이라 merge check 가 쪽마다 (row_id) 인덱스를 탄다.
5. merge check — 합치기 생성기로 머리 줄에서 다시 합쳐 won_by 를 채우고, 게이트 «다시 합친 지금 줄 = 옮긴 지금 줄 = 옛 t 값»을 잰다. 어긋나면 그 표에서 멈추고 한 줄로 말한다 — 이주 뒤 첫 쓰기가 쓰지 않은 칸 값을 조용히 바꾸지 않게.
6. catch-up — 이주 기록 표에서 일련 id 최댓값 M 을 읽고, M 이하 기록의 row_id 를 «통째로» 다시 옮긴다: 그 행의 `t__now` · `t__lines` 줄을 지우고 옛 t · cell_sources 에서 2 · 3 · 5 를 그 행만 다시. 옛 t 에서 사라진 행은 `t__now` 에서도 지운다(되살아나지 않게). 끝나면 M 이하 기록만 지운다(그 사이에 새로 남은 기록은 다음 바퀴가 옮김). 남은 기록이 줄어들 때까지 되풀이.
7. swap — 표 잠금(lock_timeout)을 쥐고 마지막 catch-up(5 의 게이트 포함) + 인덱스 이름 바꾸기 + t 를 `t__old` 로 + 보기 t · 트리거 + 이주 트리거 지움 + «이주 마지막 line_id» 기록. 한 트랜잭션. 못 잡으면 `SwapLockBusy` → B 가 물러났다 재시도. 게이트가 어긋나면 swap 트랜잭션을 되돌리고 그 표에서 멈춘다(옛 t 가 그대로 산다).
- 단계 함수(database/line_migration.py, C 11-11 · B 가 부름): `plan(db, table) -> {"stage", "after", "total"}` · `open_window` · `create` · `now_rows(db, table, after) -> (moved, next_after)` · `old_lines(db, table, after)` · `indexes` · `merge_check(db, table, after)` · `catch_up(db, table) -> moved` · `swap(db, table, lock_timeout)`. after 는 row_id 커서다. catch-up 은 since 대신 이주 기록 표를 읽는다.
- 진행: 단계는 run 행의 phase 칸(RunControl.say «Stage k/8: …» — 0 부터 7), 옮긴 줄은 쪽마다 progress(processed_rows / total_rows). 일 트랜잭션 밖이다 (B).
- 쓰기는 swap 순간에만 멈춘다.
- 이주 시간은 안 쟀다. 박스 리허설 시간 × 운영과 박스의 크기 비로 말한다.

## 되돌리기

- `t__old` 와 cell_sources 를 지우지 않고 남긴다.
- 되돌리기 = `line_migration.write_back(db, table)` 뒤 보기 t 지우기 + `t__old` 를 t 로 이름 되돌리기.
- write_back: swap 이 기록한 «이주 마지막 line_id» 보다 큰 line_id 의 줄을 가진 row_id 들(표기 소급처럼 «언제»를 옛것으로 둔 줄도 line_id 는 새것이라 빠지지 않는다)의 `t__now` 값으로 옛 t 행을 다시 쓰고, 그 머리 줄로 cell_sources 층을 다시 쓴다. 그리고 옛 t 에 있고 `t__now` 에 없는 row_id 를 전부 옛 t 에서 지운다(지움 · 키 병합의 껍데기 둘 다 — 껍데기는 «deleted» 줄 없이 지금 줄만 지워지므로 «deleted» 줄로는 못 찾는다). 리허설에서 시간을 잰다.

## 안 — 컨펌 전 (외부 검토, 총괄 11-10)

- 안 1 안전망(«줄로 다시 합친 지금 값 = t__now» 점검 일): 닫음 — 소유자 11-10 «지금 값과 이력 줄 추가를 트랜잭션으로 하면 되잖아»: 한 트랜잭션으로 충분, 짓지 않음. 이주 5 단계 게이트(이주한 지금 줄 = 다시 합친 값 = 옛 t)는 그대로다.
- 안 2 사람 값의 신선도 «Below changed since edit»: 사람 머리 줄 시각 < 그 칸 아래층(적재 · 체인) 최신 머리 줄 시각. C 의 추천은 «쓰기 5 단계가 won_by 옆에 적음»: 그 단계가 어차피 그 행의 머리 줄을 다 보고 다시 합치므로 쓰기 쪽 더하는 일은 견주기 하나이고, 그리드 읽기는 줄 표를 안 읽는다. 읽을 때 세면 저장은 없지만 그리드 쪽마다 `t__lines` 를 읽는다(D 판정 «그리드 읽기 영향 0»에 걸림). 범위: 11-14 착지 밖. 크기는 안 쟀다.

## 시간표

날 수는 안 잰 추정이다. 근거: 2 일 뼈대가 체인 밖 함수 50 개를 덮고, 체인 34 가 그와 같은 크기라서 2 일을 더한다.

- 11-10 밤: C `lines.py`(이름 · 표 만들기 · 지우기 · alter_columns) + 씨앗 문맥 — 검수 판정 붙여 준비 SHA. 이주 단계가 여덟(0~7)이 되어 B 의 단계 이름표를 고친다
- 11-11: C 정렬 키 생성기(SQL · 파이썬) · 이주 · 되돌리기, A write_lines, D 읽기, B 이주 진행, 각자 호출자 × 갈래 시험 표. 밤 통합(기계 차례)
- 11-12 ~ 11-13: 체인 34 를 줄로 — A(replay · ingestion_worker · enrichment · rule_run · dt_map · frame_confirmation · retroactive 셈) · C(cell_layer 거두기 seat). 거두기 · 도장 판
- 11-13 밤: 통합 다시, cell_sources 쓰기 0 확인
- 11-14 오전: 박스 크기 이주 · 되돌리기 리허설 · 남의 몫 검수(쓰기 = D, 읽기 = A) → 정오 착지

## 이 착지 밖

- 감사 이력의 데이터 아닌 기록 — 그동안 audit_logs 에 쓴다 (소유자 ㄴ 11-10). 다음 착지: 감사 로그의 작업 종류 칸으로. 쓰는 함수 셋(create_audit_log · bulk_insert_audit_logs · ledger/store._insert_audit_row) · 부르는 자리 28(origin/main 93bb81aa7, git grep «<함수>(» 시험 밖, 각 def = 1), +1 일 추정(안 쟀다). 그 뒤 audit_logs 은퇴.
- 고정(cell_overwrites) 접기.
- 오래된 줄 정리.
- `t__lines` 의 물리 순서(CLUSTER · 읽는 순서).
- 운영 크기의 이주 시간과 깊이 판 수 — 리허설 전에는 안 쟀다.
