# 마라톤 평가 FMEA — 셀소스 갈아엎기가 찾고 고친 것 (11-12 ~ 11-13)

판 STALL board (C:/wt-d-bt/stall_board), 보드 PG 5444, 표 sb_wide 2.17 M 행 · 30 칸 · 줄 10.5 M.
모든 수는 «박스» 수다 — 이 박스의 SSD 와 판의 부하 위의 값이고, 운영에 대한 주장이 아니다.

S 심각도 · O 발생 · D 검출 (1~5, D 는 «높을수록 늦게 잡힌다») · RPN = S×O×D.

## 1. FMEA 표

| # | 고장 모드 | S | O | D | RPN | 고침 | 상태 |
|---|---|---|---|---|---|---|---|
| F1 | 깊은 OFFSET 이 무너진다 (t 의 dead tuple) | 5 | 4 | 3 | 60 | 2269e4557 · 755e72659 | 고침 |
| F2 | 새 행을 빈 INSERT 뒤 UPDATE | 4 | 5 | 3 | 60 | 2269e4557 | 고침 |
| F3 | autovacuum 이 못 따라간다 | 4 | 4 | 3 | 48 | e8f0c8f7a · 755e72659 · 31b1d62ec | 고침 |
| F4 | t 의 행 폭 (won_by JSONB) | 3 | 5 | 4 | 60 | d41fd7c3e | 고침, 폭은 남음 |
| F5 | 새 행 INSERT 가 쪽마다 다시 컴파일 | 3 | 5 | 3 | 45 | f67cb02f6 · 4e6be5b13 | 고침 |
| F6 | 큐 화면이 outbox 전체를 훑는다 | 4 | 4 | 2 | 32 | c21494810 | 고침, R6 STALL 0 |
| F7 | 시각 칸 표의 알림이 조용히 안 간다 | 4 | 5 | 4 | 80 | cee8927ef | 고침, R6 WS 180/180 |
| F8 | '' 칸을 None 으로 다시 쓴다 | 2 | 3 | 3 | 18 | cee8927ef | 고침 |
| F9 | 재기동 · 이주 직후 몇 분이 느리다 | 2 | 5 | 3 | 30 | 없음 | 11-14 계획의 열린 줄 |
| F10 | writer_kind 를 칸마다 묻는다 | 1 | 5 | 4 | 20 | 571a5f241 | 고침 |
| F11 | outbox 이벤트를 ORM flush 로 한 줄씩 | 2 | 5 | 3 | 30 | 4121f2cb3 | 고침; 쓰기 막대 1.3 s 는 열린 줄 |
| F12 | DB 가 취소한 문장이 Python 시간으로 읽힌다 | 2 | 3 | 4 | 24 | c633912ed | 고침 (계기) |
| F13 | 경계 행이 지워지면 Next/Prev 가 OFFSET 으로 | 3 | 2 | 4 | 24 | a55f27230 | 고침 |
| F14 | 이주에서 어긋난 칸이 다음 쓰기에 조용히 바뀐다 | 3 | 3 | 4 | 36 | 453d58d4e (CSV) | 운영자 몫 |
| F15 | --workers 4 를 죽인 뒤 이어 하기 | 4 | 2 | 4 | 32 | 없음 | 리허설에서 잰다 |
| F16 | 옛 릴리스로 되돌리면 옛 리플레이가 t 를 되돌릴 수 있다 | 4 | 2 | 5 | 40 | 없음 | 리허설에서 잰다 |
| F17 | 이주 시간 추정이 박스 속도로 센다 | 2 | 4 | 3 | 24 | 4573918ec | --sample 로 운영 속도 |

### F1 깊은 OFFSET 이 무너진다
- 원인: 쓰기마다 t 행이 두 판(빈 INSERT + UPDATE, won_by UPDATE)으로 남고, 자동 vacuum 이 t 에 늦게 닿아 all-visible 이 35 % 로 떨어졌다. 그러자 깊은 쪽의 키 읽기가 index-only 에서 seq scan + 디스크 정렬로 바뀌었다.
- 운영자가 보는 것: 25~28 분부터 grid 의 깊은 쪽이 10~26 s, STALL 이 쏟아진다.
- 검출: 판의 10 분 grid p95 · explain_end.py (all-visible %, 1.86 M 깊이의 계획).
- 고침: 2269e4557 (새 행은 값과 함께 한 번) + 755e72659 (자동 vacuum 한 규칙).
- 남은 위험: 깊은 OFFSET 자체는 남는다 (R5 끝 326 ms, index-only). 쪽 번호 점프의 키 읽기 3b11ec645 는 착지 뒤.
- 증거: R1 · R2 무너짐 (p95 20.8 / 26.1 s, STALL 120 / 101), R3 이후 없음.

### F2 새 행을 빈 INSERT 뒤 UPDATE
- 원인: write_lines 가 새 행을 빈 채로 넣고 값을 UPDATE 로 채웠다. 새 행마다 dead tuple 이 하나씩 생겼다.
- 운영자가 보는 것: F1 과 같다. t 가 두 배로 커진다 (R1 끝 sb_wide 5.5 GB, R0 1.9 GB).
- 검출: m_report 의 t ins / upd 셈. R3 에서 t upd 가 −33 %.
- 고침: 2269e4557.
- 남은 위험: 알려진 것 없음.
- 증거: t dead 가 R1/R2 의 1.6~2.5 M 에서 R3 의 ≤ 100 k 로.

### F3 autovacuum 이 못 따라간다
- 원인: 기본 scale 0.2 면 1,000 만 줄 표는 dead 200 만에야 돈다. R1 에서 sb_wide__lines 의 autovacuum 은 60 분 동안 0 번이었다.
- 운영자가 보는 것: 부풀기 → 계획이 뒤집힌다 (F1).
- 검출: minutes.csv 의 vacuum_seconds · vacuum_tables, pg_stat_user_tables.autovacuum_count, pg.log (log_autovacuum_min_duration 0).
- 고침:
  - e8f0c8f7a · 755e72659: 줄 표와 선언 표 t 에 같은 규칙 — 50 + 행의 2 %, 상한 50 k / 100 k, cost_limit 2000, truncate off (lines.py 의 AUTOVACUUM_* 상수, C 확인). 스케줄러의 storage 줄이 건다.
  - 31b1d62ec: 이주가 표마다 끝에 VACUUM (ANALYZE) 를 t 와 t__lines 에.
  - 셋 다 trial 에만 있고 main 에는 없다.
- 남은 위험: 판 부하에서 세 표(outbox · t · 줄)의 vacuum 이 매분 약 60 % 동안 돈다 (R5). 운영 부하에서는 재지 않았다.
- 증거: R1 (줄 autovacuum 0), R2 (줄만 손으로 50 k, t 는 그대로라 여전히 무너짐), R3 (줄 20 · t 24 번), R5.

### F4 t 의 행 폭
- 원인: won_by 가 칸 이름을 든 JSONB 였다 — 행당 684 B, 1,241 B 중.
- 운영자가 보는 것: t 가 main 의 2.4 배 폭이라 쪽이 많아지고, 깊은 읽기와 vacuum 이 길어진다.
- 검출: width_split.py · row_width.json.
- 고침: d41fd7c3e — 비트 슬롯 순서의 bigint[], 접근자 하나. 264 B 는 A 의 시험 test_a_rows_won_by_is_a_slot_array_pg 의 MEASURED 다.
- 남은 위험: t 는 여전히 781 B 다 (main 494~544 B). 남은 몫은 won_by 264 B.
- 증거: R3 1,241 B → R4 832 B → R5 781 B.

### F5 새 행 INSERT 가 쪽마다 다시 컴파일
- 원인: INSERT 에 .values(list) 로 행을 실으니 쪽마다 새 문장이 컴파일됐다.
- 운영자가 보는 것: 파일 쓰기가 느려진다 (R3 2.2 → 3.1 s; _merge_now 0.48 → 1.72 s).
- 검출: 쓰기 단계 파일(BOARD_WRITE_PHASES, file.tsv.phases) · 컴파일 수 시험.
- 고침: f67cb02f6 (한 번 컴파일) → 4e6be5b13 (배열 INSERT 한 번).
- 남은 위험: 1,000 행 파일 쓰기 중앙값 R6 1.84 s. 절대 막대 1.3 s 에는 못 미쳐 FAIL 이다 — 열린 줄이고, 착지를 막지 않는다 (총괄 11-13). main 은 같은 부하에서 4.1 s.
- 증거: R3 3.1 s · R4 2.5 s · R5 2.03~2.16 s.

### F6 큐 화면이 outbox 전체를 훑는다
- 원인: chain/queue_lines.py 의 waiting_lines 가 대기 행 전부를 묶은 뒤 window 를 돈다 (200 줄 상한은 그 뒤). main 에도 같은 결함이다.
- 운영자가 보는 것: 큐 화면의 «Read N s ago» 가 계속 커지다 «Read timed out · retrying».
- 검출: STALL 줄의 경로 /admin/chain/queue · EXPLAIN (D 가 대기 40 만 행에서 잼: 861.7 ms, seq scan 뒤 정렬 — explain_queue_400k.json).
- 고침: c21494810 (C, main 에서 6210a4f90 을 거쳐 trial 에도) — idx_outbox_line 으로 줄을 찾고, 그린 줄만 센다.
- 남은 위험: R6 의 시간 잰 구간에 STALL 0 이다. 1 s 를 넘는 느린 줄은 실행 전체에 12 개다 (1.06~1.69 s, db 143~793 ms, 13 문장). 20:13~20:25 에 대기 행이 1,165 → 245 로 빠지는 동안만 나왔고, 그 뒤 22 분은 0 이다. 시간 잰 시작 (20:17:18) 앞이 5 개, 뒤가 7 개.
- 증거: R4 STALL 42 중 41, 큐 느린 줄 R4 186 · R5 36 · R6 12, explain_queue_400k.json. (이 문서 앞 판의 R5 «72» 는 한 줄에서 두 토큰을 센 두 배였다.)
- R6 사본 EXPLAIN (11-13 22:35, 읽기 전용, explain_queue_r6.py → explain_queue_r6.json): 대기가 0 으로 다 빠진 뒤라, 라우트 함수가 보내는 문장은 10 개다. 각 문장의 실행은 0.03~7.7 ms 이고 공유 버퍼 적중뿐이다 (read 0). 같은 프로세스에서 다시 부르면 라우트 0.017 s (SQL 0.011 s), 첫 부름은 1.085 s 중 SQL 0.069 s 다 (queue_route_warm.py). 대기 행이 쌓인 모양은 이 사본에서 다시 만들 수 없었다. 그래서 느린 줄의 db 몫이 대기 행 수에 비례하는지는 재지 않았다.

### F7 시각 칸 표의 알림이 조용히 안 간다
- 원인: crud._said_logs 가 사람 쓰기의 created_logs.new_value 에 쓴 값을 그대로 싣는다. datetime 이면 async_broadcast 의 json.dumps 가 TypeError 로 죽는다. main 의 옛 길은 isoformat 문자열이었다.
- 운영자가 보는 것: 시각 칸이 있는 표에 쓸 때마다 빠짐없이, 그 배치가 다른 화면에 안 간다 (A: 확률이 아니라 결정적). 쓰기는 커밋되고 터지는 것은 뒤의 broadcast 라, 화면에는 아무 표시가 없고 서버 로그에만 traceback 이 남는다.
- 검출: test_a_cell_written_on_a_table_with_a_time_column_reaches_the_screen 6 항목 (PG) · R6 의 WS 게이트 (notices = writes).
- 고침: cee8927ef — said line 이 시각을 ISO 글로 싣는다 (said_value).
- 남은 위험: 없음으로 본다. R6 에서 lot_event 사람 쓰기 180 번 → batch_row_upsert 알림 180 (p_ws.py, 소켓 오류 0).
- 증거: 0ece35c0b 묶음 판정, 탐침 «msg['created_logs'][2]['new_value'] datetime».

### F8 '' 칸을 None 으로 다시 쓴다
- 원인: 새 쓰기 길이 저장된 '' 와 승자 None 을 다른 값으로 본다. 판정 284 («'' 는 부재») 와 어긋난다.
- 운영자가 보는 것: 보이는 값은 그대로다. 변화 수가 하나 늘고, t 행이 '' → NULL 로 한 번 더 쓰이고, 이력에 «job: empty» 같은 거짓 줄이 남는다. 이력 없는 칸(_plain)에도 같은 다시 쓰기가 있었다 (A).
- 검출: test_a_stored_blank_under_an_empty_winner_is_not_rewritten (PG).
- 고침: cee8927ef — 판정 284 의 같은 값 판정을 한 자리로 모았다 (승자 None 아래의 '' 는 변화가 아니다).
- 남은 위험: 쓰기 문이 빈 칸을 접기 전에 들어온 '' 행.
- 증거: 줄 표를 지은 탐침에서도 changed 1 · t.job '' → NULL.

### F9 재기동 · 이주 직후 몇 분이 느리다
- 원인: 차가운 shared_buffers 와, 첫 분부터 세 표에 도는 autovacuum.
- 운영자가 보는 것: R5 의 1~6 분 쪽 p95 1.33~1.66 s, 7 분부터 1.0 s 안팎. R6 (착지 트리) 는 1~6 분 p95 1.25 s, 7~30 분 0.92 s.
- 검출: minutes.csv 의 분별 쪽 p95 와 vacuum 초.
- 고침: 없음. 이주 끝을 VACUUM (FREEZE) 로 바꾸는 안은 버렸다 — 빠지는 것은 첫 두 번의 얼림 웃돈(약 8 만 쪽, WAL 0.6 GB)뿐이고, 창 안에서 약 1 GB 를 쓴다.
- 남은 위험: 7~10 분도 vacuum 이 같은 만큼 돌았는데 p95 가 낮았다. 그러니 vacuum 만으로는 설명이 안 되고, 캐시 몫은 다시 돌려야 가른다 (11-14 계획의 열린 줄).
- 증거: R5 minutes.csv · pg.log autovacuum 44 건, stall_after_clean 의 all-visible 100 %.

### F10 writer_kind 를 칸마다 묻는다
- 원인: grid_look._named 가 1,000 행 쪽에서 crud.writer_kind 를 29,955 번 불렀다. 이름은 866 개뿐이다.
- 운영자가 보는 것: 쪽 읽기 +0.03 s.
- 검출: profile_stages.py (단계 시계).
- 고침: 571a5f241 — 한 번 부를 동안 이름별로 담는다.
- 남은 위험: winners 가 줄을 다시 읽는 0.039 s 는 두기로 했다 (총괄 판정, 안 A · B 보류).
- 증거: 무부하 같은 쪽 main 0.135 s · 갈아엎기 0.199 → 0.171 s.

### F11 outbox 이벤트를 ORM flush 로 한 줄씩
- 원인: write_lines._stage 가 한 쓰기의 outbox 이벤트 1,000 개를 DatabaseOutbox ORM 객체로 세션에 넣었고, 커밋 때 ORM flush 가 객체마다 다뤘다.
- 운영자가 보는 것: 파일 쓰기가 그만큼 느리다.
- 검출: 쓰기 단계 파일의 end_step (커밋의 마지막 flush).
- 고침: 4121f2cb3 — 이벤트 전부를 crud.insert_by_arrays 배열 INSERT 한 문장으로 쓰고, NOTIFY 래치를 직접 한 번 부른다.
- 남은 위험: INSERT 자체(약 0.15 s)는 남아 _stage 로 옮겨 갔다. 줄어든 것은 객체마다 하던 파이썬 몫뿐이다.
- 증거 (A, 시험 DB · R5 의 파일 모양 새 행 1,000 x 30 칸, 7fd729788 과 23add2f92 를 번갈아): 문 전체 1.842 / 1.874 s → 1.801 / 1.740 / 1.772 / 1.662 s, 약 −0.1 s. 판으로는 재지 않았다 (R5 는 이 고침 전 트리).

### F12 DB 가 취소한 문장이 Python 시간으로 읽힌다
- 원인: request_timing 이 SQL 시간을 after_cursor_execute 에서만 더했다. DB 가 취소한 문장은 거기 안 닿는다.
- 운영자가 보는 것: 느린 줄이 «Python 10.03 s» 라고 말한다 — 진단이 틀린 쪽으로 간다.
- 고침: c633912ed — handle_error 도 같은 자리로 더한다.
- 증거: 마라톤의 grid 작성자 읽기가 10 s 에 잘린 느린 줄.

### F13 경계 행이 지워지면 Next/Prev 가 OFFSET 으로
- 원인: key_page 가 경계 행을 찾아 값을 읽었다. 그 행이 지워지면 OFFSET 으로 떨어졌다.
- 고침: a55f27230 — row_id 순서에서는 row_id > :after 하나로 쪽을 정한다.
- 증거: test_in_row_id_order_a_gone_boundary_row_still_pages_by_key, 박스 1.86 M 깊이에서 키 5 ms · OFFSET 3.2 s.

### F14 이주에서 어긋난 칸이 다음 쓰기에 조용히 바뀐다 (C)
- 원인: 이주가 옮긴 줄의 승자가 t 의 값과 다른 칸이 있다. 쪽은 그대로 들어가고, 그 칸은 다음에 쓰일 때 줄 승자의 값으로 바뀐다 (소유자 ㄴ).
- 운영자가 보는 것: copy_mismatch_<t>.csv 를 안 보면 값이 조용히 바뀐다.
- 검출: 이주 끝의 «N cell(s) do not match, listed in …» 줄과 그 CSV.
- 고침: 453d58d4e — 어긋난 칸을 CSV 에 남기고 --rows 로 그 행만 다시 옮긴다.
- 남은 위험: CSV 를 읽는 것은 운영자 몫이다.
- 증거: 박스 stall_after_clean 에서 98,804 칸 (C).

### F15 --workers 4 를 죽인 뒤 이어 하기 (C)
- 원인 · 위험: 한 프로세스 시험만 있다. 여러 일꾼을 강제로 죽인 뒤 이어 하는 판은 재지 않았다.
- 검출: 11-13 밤 리허설.

### F16 옛 릴리스로 되돌리면 옛 리플레이가 t 를 되돌릴 수 있다 (C)
- 원인 · 위험: 같은 DB 에서 옛 릴리스의 리플레이 · 재계산은 옛 층 표만 본다. 그래서 착지 뒤의 t 값을 되돌릴 «수» 있다. 재지 않았다.
- 검출: 11-13 밤 리허설.

### F17 이주 시간 추정이 박스 속도로 센다 (C)
- 원인: --estimate 는 박스의 층 16,348 개/s 로 센다 (4573918ec). 운영 디스크의 속도는 --sample 로만 안다.
- 남은 위험: 가장 큰 표 하나가 창의 바닥을 정한다.

## 2. 판마다의 증거

공통: 읽는 사람 12 (grid 쪽 · 수 · 필터 · 작성자 읽기, 팝업 포함), 시작 VACUUM ANALYZE, 판 PG 차가운 재기동, 사본은 FILE_COPY.

**R0 — main 기준선.**
- 조건: 트리 fcab7103e (main), stall_before_v2 사본, 쓰기 쉼 없이 (GAP 0), 60 분.
- 수: grid p95 0.88~1.08 s, p50 0.41. 파일 쓰기 4.09~4.16 s, 10 분에 150 콜. 깊은 OFFSET index-only 576 ms. t 1.9 GB, 행 494~544 B. STALL 1.
- 부서진 것: 없음 — 무너지지 않았다.

**R1 — 갈아엎기 첫 판.**
- 조건: d7003a52d, stall_after_clean 사본, GAP 0, 60 분.
- 수: 파일 2.17~2.50 s, 10 분에 256~296 콜 (R0 의 두 배 속도라 부하도 두 배). grid p95 1.14 → 20.84 s. STALL 120.
- 부서진 것: 25~28 분에 무너짐. t dead 1.7 M · all-visible 35 % · seq scan + 디스크 정렬 3.2 s. 줄 표 autovacuum 0 번 (F1 · F2 · F3).

**R2 — 줄 표 저장 설정만 손으로.**
- 조건: R1 과 같은 트리, 줄 표만 autovacuum 문턱 50,000 (alter_lines.py).
- 수: grid p95 1.23 → 26.14 s, STALL 101, t dead 2.5 M.
- 부서진 것: 줄은 vacuum 됐지만 t 는 그대로라 같은 무너짐 — 원인이 t 라는 증거.

**R3 — 행 한 번 + 저장 규칙.**
- 조건: 6b7ad710a, stall_after_clean.
- 수: grid p95 0.98~1.22 s, STALL 5, t dead ≤ 100 k, all-visible 99 %, 깊은 OFFSET index-only 650 ms. 행 1,241 B (won_by 684).
- 부서진 것: 파일 쓰기 3.1 s — 쪽마다 컴파일 (F5).

**R4 — won_by 배열.**
- 조건: f481bf4a0, 새 stall_after_clean (C 의 재이주).
- 수: 파일 2.33~2.50 s, grid p95 1.09~1.33 s, dead ≤ 108 k, all-visible 98 %, 행 832 B. layers 단계 (느린 줄) 0.36 s, R0 는 0.23.
- 부서진 것: STALL 42 중 41 이 큐 화면의 outbox 전체 훑기 (F6, main 에도 있는 결함). 지우기 전에 그 문장을 EXPLAIN 하지 못했다 → 덫 4.

**R5 — 같은 부하.**
- 조건: 7fd729788, stall_after_clean, R0 속도에 맞춤 (파일 턴 8.03 s · 체인 2.34 s), 30 분.
- 수: grid p95 1.25 / 0.97 / 0.97 (R0 0.97 / 1.08 / 0.88). 1.1 s 넘은 분 8/30 (R0 3/30), 그중 6 개가 1~6 분. grid p50 0.52~0.55 (R0 0.41). 파일 2.03~2.16 s (R0 4.1). 깊은 OFFSET 326 ms. 행 781 B. STALL 1 (첫 기동의 인덱스 짓기 중, 판정 밖).
- 부서진 것: 처음 6 분 (F9).

**R6 — 착지 트리.**
- 조건: 61f3ce6a4 (cee8927ef 쓰기 문 고침 · c21494810 큐 고침 포함), stall_after_clean, R0 속도, 30 분 (시간 잰 시작 20:17:18), BOARD_TIME_WS=1 로 lot_event 사람 쓰기 10 s 마다.
- 수:
  - grid p95: 1~6 분 1.25 s · 7~30 분 0.92 s (R0 0.94 · 1.00, R5 1.31 · 0.97). 10 분 블록 1.12 / 0.92 / 0.89. 1.1 s 넘은 분 4/30 [1, 2, 3, 6].
  - grid p50 0.47~0.50 (R0 0.41).
  - STALL: 시간 잰 구간 0 (큐 포함). 첫 기동 prime 중 1 (인덱스 짓기, 판정 밖).
  - 파일 쓰기 1.78 / 1.80 / 1.81 s (전체 1.84), 체인 1.53~1.58 s.
  - WS: 쓰기 180 · 200 답 180 · 알림 180.
- 부서진 것: 없음. 남은 것은 처음 6 분 (F9) 과 쓰기 막대 1.3 s (F5).

## 3. 마라톤 돌리는 법과 덫

1. **읽기를 판정하기 전에 쓰기 부하를 기준선에 맞춘다.** R1~R4 는 쓰기가 빨라진 만큼 같은 시간에 두 배를 썼다 (R0 10 분 150 콜, R4 260). 그래서 «grid 가 느리다» 를 가를 수 없었다. 쓰는 이를 기준선 속도로 묶는다 (p_write 의 BOARD_PACE_FILE / BOARD_PACE_CHAIN, 턴의 시작에서 다음 시작까지).
2. **시험 DB 의 pg_session 은 NullPool 이라, 문 한 번에 연결 값이 약 0.2 s 붙는다.** 연결 하나만 재면 0.10 s (7 회 중앙값, A 의 11-13 문 프로파일). 쓰기 문은 한 번에 둘을 연다 — write_lines._table_shape → lines._catalogue 에서 하나, end_step 뒤 답의 1,000 행을 다시 읽을 때 하나. 풀을 쓰는 운영과 판은 이 값을 내지 않는다. 시험에서 잰 «문 한 번» 시간을 판의 수와 견주지 않는다.
3. **프로파일러는 부풀린다.** cProfile 아래 0.503 s 였던 같은 쪽이 단계 시계로는 0.193~0.215 s 였다. 순위는 cProfile 로, 크기는 perf_counter 감싸기로 잰다.
4. **사본을 지우기 전에 EXPLAIN.** 판정 줄이 새로 이름 든 문장은 그 사본이 있을 때만 그 상태로 잰다. R4 의 큐 문장을 지운 뒤에야 물어 400 k 로 다시 쟀다.
5. **따뜻한 분과 차가운 분을 가른다.** 판은 PG 를 차갑게 재기동하고 시작한다. 첫 몇 분은 vacuum 과 캐시가 겹친다 (R5 1~6 분). 10 분 블록 평균에 묻히지 않게 분별 수를 같이 본다.
6. **시간 잰 판은 혼자 돈다.** 크롬 · node 하니스 · 넓은 pytest 가 같은 박스에 돌면 수가 그 몫만큼 흔들린다. 총괄이 크롬 줄을 비우고 신호를 준 뒤에 돈다.
7. **Windows 의 time.monotonic 은 15.6 ms 계단이다.** 짧은 단계는 0 이나 15.6 으로 찍힌다 (중앙값 0.0 이 나눗셈을 죽인 적이 있다). 단계는 time.perf_counter 로 잰다.
8. **Git Bash 의 tee /dev/stderr 는 리다이렉트한 로그를 지운다.** R1 · R2 의 머리 줄(SHA 등)을 잃었다. tee -a 를 쓰고, 도는 bash 스크립트를 고치지 않는다.
9. **conda run 은 이 박스에서 출력을 잃고, 자기 오류 질문에 멈춘다.** env 의 python 을 바로 부른다.
10. **탐침은 읽은 뒤 commit 한다.** 열린 transaction 은 teardown 의 DROP 을 막고, 공유 시험 DB 에서 남의 레인까지 막는다 (11-13 에 30 s).

도구: C:/wt-d-bt/stall_board — m_run.sh (사본 · 핀 SHA · 판 · 보고) · p_load.py · p_write.py · p_ws.py · m_report.py · m_rates.py · r5_gate.py · explain_end.py · width_split.py · profile_stages.py.
