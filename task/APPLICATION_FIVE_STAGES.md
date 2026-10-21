# 체인 다섯 단계 대응 — 경로마다 단계 열 · 어기는 자리 · 정본 좌석 (응용 C, 2026-10-21)

소유자 정본 문장: 「체인은 뭐든 간에 결국 **돌릴 거 리스트 → 그룹 나누기 → 데이터 받기 → 돌리기 → 쓰기**, 이 순서고 각 문에 대응시켜」.
기호: **L** 리스트 · **G** 그룹 · **D** 받기 · **R** 돌리기 · **W** 쓰기. 줄 번호는 5ce9df90f 기준이다(위치가 아니라 함수 이름이 정본).
경로마다 줄을 내가 열어 확인했다. 리플레이 · fold_units · R2 · 파일 교체는 탐색이 낸 줄을 커밋 줄 위주로 대조했다.
전수 표(`task/APPLICATION_DOOR_CENSUS.md`)를 다시 세지 않고, 그 위에 대응시켰다. 크기 · 시간은 **안 쟀다**.

파일 약자: iw `chain/ingestion_worker.py` · rr `chain/rule_run.py` · sdk `mapper_sdk.py` · ji `chain/join_into.py` · cl `chain/cell_layer.py` · rp `chain/replay.py` · ret `admin/retroactive.py` · dw `parsers/directory_watcher.py` · ck `ingestion/checkpoint.py` · ec `event_constants.py`

---

## 1. 경로마다 단계 열 (코드 순서)

⚠ = 순서를 어기는 자리(2절 번호). 커밋은 `C:` 로 적는다.

### 1-1. 실시간 넣기 · 편집 · 지움 (체인 워커 · 슬롯)

| # | 단계 | 함수 (줄) | 커밋 |
|---|---|---|---|
| 1 | L | 줄 고르기 `lines_to_give` · `line_of` (slots:109 · 98) — 줄 열쇠 `queue_line_key` (ec:285) | |
| 2 | L | `pending_chain_events` 200 행 (iw:4224) | |
| 3 | L→W | 깊이 넘은 사건 FAILED 표시 → 커밋 → **지운 행 거두기** (iw:4142–4151) ⚠⑤ | C: iw:4150 |
| 4 | L | **같은 거래 사건을 2만 개까지 더 끌어옴** (iw:4164) ⚠① | |
| 5 | G | `trim_events_to_row_budget` 2만 행 (iw:4197) ⚠② | |
| 6 | G | `group_events` · `group_id` (iw:504 · 473) ⚠② | |
| 7 | G | `merge_consecutive_groups` (iw:2218) ⚠② | |
| 8 | L | 그룹마다 `_still_waiting` (iw:2959) · `wakes` 거르기 (iw:2135) | |
| 9 | D | `outbox_expand.expand_events` (iw:2147) | |
| 10 | R | 규칙마다 `run_rule` (iw:2307) → 첫 줄 `held_back` = require · exclude (rr:623) ④ | |
| 11 | D | 맵퍼 안 읽기: 떠난 맵 다시 읽기 `_with_the_maps_rows_left` (sdk:786 · 623) · 조인 `_read_once` (ji:438–458) · 맵퍼 자신의 `sql()` (sdk:123) ⚠③ | |
| 12 | R | 맵퍼 호출 (rr:677) · 출신 표시 `ORIGIN_MARK` 는 맵퍼가 그 열을 지닐 때만 (sdk:788 · 597) ⚠⑦ | |
| 13 | R | **편집 거두기 범위를 지금 지음** — origins · columns (iw:2312–2328) ⚠⑥ | |
| 14 | W | `apply_chain_writes` (iw:2394) — 묶음마다: | |
| 14a | W | `crud.apply_batch_updates` (iw:1744) | C: crud:5790 (묶음마다) |
| 14b | W | 잡 회수 `plan_retraction` · `apply_retraction` (iw:1801 · 1818) | C: 그 함수 안 |
| 14c | W | 빈 재계산 `_withdraw_blanks` → `_withdraw_and_tell` (iw:1843) | C: cl:637 (쪽마다) · iw:3544 (EDIT) |
| 14d | W | 사라진 키 `_delete_gone` (iw:1858) · 껍데기 `delete_shells` (iw:1894) | C: crud:6046 (1,000 행마다) |
| 14e | R+D | **다음 쪽 맵퍼 `more()` 가 쓰기 루프 안에서 돎** (iw:1550) ⚠③ | |
| 15 | W | 편집 거두기 `_withdraw_and_tell(… "edited")` (iw:2040) | C: cl:637 · crud:6046 · iw:3544 |
| 16 | W | 처리됨 `mark_processed` (iw:3051) | C: iw:3057 |
| 17 | W | **지운 원천 행 거두기 `_retract_deleted_rows`** (iw:3059) ⚠⑤ | C: cl:637 · iw:3544 |
| 18 | W | 통지 `_dispatch_broadcasts` (iw:3195) | |

넣기 · 편집 · 지움의 차이: 편집만 13 · 15 를 지나고, 지움만 17 을 지난다(실패해 격리된 그룹은 iw:3160–3163 에서 같은 일).
한 그룹의 커밋 수 = 묶음 수 × (1 + 거두기 쪽 수 + EDIT 1 + 지움 1,000 행당 1) + 처리됨 1 + 지운 행 거두기. 실제 수는 안 셌다.

### 1-2. 리플레이 (`chain_replay_cli replay <rule> --apply`)

| # | 단계 | 함수 (줄) | 커밋 |
|---|---|---|---|
| 1 | W | 런 행 `claim` (ret:3742) | C: ret:3618 |
| 2 | L | `replay_refusal` · `current_max_row_id` (rp:360 · 377) | |
| 3 | W | 전체 리플레이면 `open_tally` (rp:503) | C: rp:717 |
| 4 | L+D+G | group_by 면 `keyed_rows` → `key_pages` (rp:521 · 525) · 아니면 `iter_pages` (rp:527) ⚠② | |
| 5 | G+W | 쪽마다 EDIT 사건, 1,000 id 씩 (rp:563 · database.py:507) ⚠② | C: rp:566 (쪽마다) |
| 6 | — | 워커가 1-1 의 2–18 로 돈다. 줄 열쇠는 run_id 하나 | |
| 7 | L+D+R+W | 끝 스윕 `sweep_finished_replays` (rp:810): 런의 사건이 다 처리된 «뒤» `_gone_maps` → `_removal_batches` → `apply_chain_writes` (rp:734–835) ⚠⑤ — 런 단위라 «그룹당 커밋 하나»(3 절 ⑤)로는 안 접힌다 | C: crud:5790 … |
| 8 | W | 집계 행 지움 (rp:842) | C: rp:843 |

### 1-3. 소급 rule_rows

코드 주석이 이 운영을 **은퇴**로 적는다 — 「큐에 넣는 그룹이 없고, 옛 런 목록 때문에 등록만 남았다」 (ret:1101). 넣는 자리를 내가 세지는 않았다.
돌면: 사건 uuid 로 outbox 읽기(L+D, ret:1157) → `_process_chain_transaction_group_sync` 그대로(1-1 의 8–15) → 끝 커밋 (ret:1179). 처리됨 표시는 없다.
«one commit for the run» 은 거짓이다(묶음마다 crud:5790 커밋 · ret:1167 롤백은 그것을 못 되돌림) — 전수 표 3 에 이미 적었다.

### 1-4. fold_units (rp:1510)

| # | 단계 | 함수 (줄) | 커밋 |
|---|---|---|---|
| 1 | L+D | 대상 · 셈 · `unit_ids` · `keyed_rows` (rp:1524–1535) | |
| 2 | G | `asked()` 1 · 2 · 4 … 1,000 그룹씩 (rp:1553) ⚠② | |
| 3 | D | `load_rows_by_ids` (rp:1562) | |
| 4 | R(+D) | `run_rule` · 다음 쪽 `call()` (rp:1563 · 1571) ⚠③ | |
| 5 | G | `pages()` 2만 행으로 다시 묶음 (rp:1575) ⚠② | |
| 6 | R+D | 가상 조인 중복 거절 · 행 · 층 · 덮어쓰기 읽기 (rp:1689–1703) ⚠③ | |
| 7 | R | `_fold_units_forced` · `apply_row_update_internal` (rp:1716 · 1748) | |
| 8 | W | 배열로 넣기 · 고치기 (rp:1774–1780) | C: rp:1781 (쪽마다) |
| 9 | D+R | 지킬 행 `_rows_written_from` · `columns_a_rule_writes` (rp:1595 · 1608) | |
| 10 | W | `_withdraw_and_tell` (rp:1614) | C: cl:637 · crud:6046 · iw:3544 |

### 1-5. R2 `withdraw_source` (cl:382)

L 대상 · 거절(cl:402–416) → G 표 행을 `iter_pages` 로(cl:424) → D 쪽마다 주장 읽기(cl:435) → L `touched` 에 더함(cl:443) → D+R+W `_withdraw_cells`(cl:552–636) **C: cl:637 쪽마다** → D `shells` → W `delete_shells` **C: crud:6046** → C: cl:453.
⚠⑤ 쪽 커밋과 껍데기 지우기 사이가 전수 표의 알려진 틈이다.

### 1-6. 빈 재계산

1-1 의 14c 다. 처리됨(16)보다 «앞»이다 — 이 경로는 순서를 안 어긴다. 다만 쓰기 문 «밖»의 직접 SQL 이라 커밋이 셋으로 나뉜다(crud:5790 · cl:637 · iw:3544) ⚠⑤.

### 1-7. 조인 (`derive.join`)

L 규칙 고르기(iw:2248) → R `run_rule` → `propose` (ji:545) → **L+D 왼쪽 행 + `keys_left` 더함 (ji:679–693)** ⚠① → G 키 쪽(ji:711) → **D 왼쪽 · 값 표 읽기 `_read_once`, require · exclude 는 여기서 SQL 조건 (ji:438–458)** ⚠③④ → G `keyset_scan.pages` (ji:600) → R `_update_items` (ji:605) → W 1-1 의 14. 둘째 쪽부터는 읽어 둔 답을 자르기만 한다(값 표를 다시 안 읽음).

### 1-8. 파일 교체 (감시기)

L 파일 고르기 `process_with_retry` (dw:2578) → L(+W) `already_checked` (ck:342) → D 행 풀기 (dw:2653) → W 체크포인트 IN_PROGRESS (ck:370) → R 빈 행 버림 → G **맵마다 `_map_batches`** (dw:3601) → 맵마다 R 정리 → W `apply_batch_updates` (맵 purge 포함, 사건도 같은 커밋) **C: crud:5790 → dw:3788** → W 보관 이동 → W DONE **C: ck:510** → W 로그 행 **C: dw:2942**.
체인은 사건이 맵마다 커밋되므로 파일 중간부터 집어 간다 — 1-1 의 2–18. 커밋 사이 틈은 전수 표 3 에 적었다(이동 → DONE · 로그).

---

## 2. 순서를 어기는 자리 — 총괄 의심 확인

| 번호 | 의심 · 발견 | 판정 | 근거 |
|---|---|---|---|
| ① | 리스트가 중간에 넓어짐 — drain 의 같은 거래 끌어오기 | **맞다** | iw:4164. 넓힌 «뒤» 행 예산으로 다시 자른다(iw:4197) |
| ①b | 그 밖의 넓힘 | 셋 더 | 조인 `keys_left` (ji:687) · 맵퍼 SDK 떠난 맵 다시 읽기 (sdk:623) · R2 `touched` (cl:443) |
| ② | 그룹 나누기가 여러 곳 | **맞다 — 일곱** | 줄 열쇠 (ec:285) · trim (iw:4197) · `group_id` (iw:473) · merge (iw:2877) · 쪽 `_in_rule_order` (iw:1526) · 리플레이 `key_pages` + 1,000 id (rp:525 · database.py:507) · 파일 `_map_batches` (dw:3601). fold_units 는 셋 더 (rp:1553 · 1575 · 거두기 1,000) |
| ②b | 줄 열쇠와 그룹 열쇠가 다른 답 | 새 발견 | 줄 = run_id → 거래 → 행 (ec:285). 그룹 = group_by 키 → 거래 → 행 (iw:473). 슬롯은 줄 하나만 받으므로, 실시간에서 group_by 그룹은 거래를 넘어 못 모인다고 읽힌다. 안 쟀다 |
| ③ | 데이터 받기가 돌리기 안 — SDK 맵 다시 읽기 · 조인 `_read_once` · 맵퍼 자신의 SQL | **맞다 — 셋 다** | sdk:786 · ji:438 · sdk:123. 더해: 다음 쪽 `more()` 가 쓰기 루프 안 (iw:1550), fold_units 의 읽기 (rp:1689–1703) |
| ③b | f2 판 결함(맵 교체에서 편집 행 하나가 맵을 통째 바꿈)의 원인 | ③ 의 결과 | SDK 가 맵 전체를 다시 읽는 조건이 «행이 «떠난» 맵»뿐이다 (sdk:623 `key_left`). 맵 안에 머문 편집 행은 그 한 행만 받고, replace_map 이 맵을 그 한 행으로 바꾼다 |
| ④ | 행 거르기(require · exclude)의 자리 | **받기와 돌리기 사이 — 맞는 자리**, 단 좌석 둘 | 정본 `held_back` (rr:623, 받기 뒤 · 맵퍼 앞). 조인은 값 표 쪽을 SQL 조건으로 따로 거른다 (ji:450). 편집으로 문을 나간 행은 «떠난 행»으로 바뀌어 건네진다 (rr:574) |
| ⑤ | 쓰기가 여러 커밋 · 일부 거두기가 «처리됨» 뒤 | **맞다** | 처리됨 뒤 거두기 셋: iw:3059 · iw:3163 · iw:4151. 리플레이 끝 스윕도 처리됨 뒤 (rp:816). 한 그룹 안 커밋 넷 갈래: crud:5790 · cl:637 · iw:3544 · crud:6046 |
| ⑥ | edit retraction 범위를 돌리기 단계에서 지음 | **맞다** | iw:2312–2328 이 규칙 루프 안에서 origins · columns 를 짓고, 실행은 모든 묶음 뒤 (iw:2035–2045). 판단 «이 규칙이 출신을 찍나»는 프로세스 메모리 `_ORIGIN_SEEN` (rr:263 · 719) |
| ⑦ | 출신을 어떻게 지니나 (총괄 ①) | **새 빨강** | 출신은 SDK 가 입력 틀에 넣은 `__origin_row_id` 열을 맵퍼가 «지닐 때만» 산다 (sdk:788 → 597). `df[[k, m, v]]` 꼴이면 조용히 사라지고, 지운 행 · 키 편집이 아무것도 못 거둔다(판 f4 열 고르기: 옛 키 K2 · 지운 K5 가 리플레이 뒤에도 남음). 경고 `retraction_refusal` 은 `_ORIGIN_SEEN` 을 묻는데, 그것이 슬롯 프로세스마다 따로라 지움을 받은 슬롯이 그 규칙을 안 돌렸으면 «모름»으로 침묵한다고 읽힌다. 안 쟀다(고정 판 f4n 으로 잴 것) |
| ⑧ | 연결이 끊긴 그룹이 set aside 로 끝나고 다시 안 돎 (총괄 ③가) | **결함으로 읽힌다** | 슬롯의 계약은 «던진 묶음은 그대로 다시 돈다» (slots:545–557 try). 그런데 `_reloaded` 의 DB 읽기(slots:542 → 591)가 그 try «밖»이라, 끊긴 연결 하나가 슬롯을 죽이고 디스패처 `_reap` 가 줄을 통째 set aside 한다 (slots:314–333). 판 f1: 리플레이 줄 사건 2 개가 그렇게 끝났다. 기동 중 죽음(DLL)도 같은 길이다 |
| ⑨ | 시작 때 남의 백엔드를 끊는 기준 (총괄 ③나) | 사실 | `end_connections` (slots:439) 와 `_end_queries_a_gone_chain_worker_left_sync` (iw:4264) 둘 다 **연결 이름 + DB** 로 거른다. **스키마가 아니다.** 후자는 «다른 체인 루프가 살아 있나»를 심장박동으로 묻고 건너뛴다(iw:3424). 운영은 DB 하나에 체인 하나라 무해할 수 있다 |

---

## 3. 이 순서로 되돌리면 어디로 가나 (한 줄씩)

| 번호 | 되돌린 자리 |
|---|---|
| ① | 같은 거래 끌어오기를 L 좌석 `pending_chain_events` 안으로 — 줄을 고를 때 거래째 고른다. 2만 상한과 행 예산 자르기가 한 곳이 된다 |
| ①b | 조인 `keys_left` · SDK 떠난 맵 · R2 `touched` 는 «무엇을 더 읽나»라서 D 좌석의 선언(아래 D)으로 |
| ② | 그룹 열쇠를 `group_id` 하나로 — 줄 열쇠가 그것을 부른다. trim · merge · 쪽 · 맵 · key_pages 는 그 좌석의 «크기» 칸이 된다 |
| ②b | 위와 같다 — 줄 = 그룹이면 group_by 가 거래를 넘어 모인다 |
| ③ | 맵 · 잡 전체, 조인 값 표, 다음 쪽을 `expand_events` 다음의 D 좌석이 읽어 맵퍼에 «건넨다». 맵퍼 안 `sql()` 은 그 좌석을 못 지나는 것만 남는다 |
| ③b | D 좌석이 «건네진 행이 든 맵 전체»를 읽으면(떠난 맵만이 아니라) 고쳐진다. B 의 wip `e62d92f0c` 제목이 이 꼴이다 |
| ④ | 그대로 둔다. 조인의 SQL 거르기는 같은 «require» 낱말을 값 표에 쓰는 것이라, 한 좌석이 «어느 표의 칸인가»를 받게 하면 하나가 된다 |
| ⑤ | 거두기 · 껍데기 · EDIT 알림 · 처리됨 표시를 한 그룹의 쓰기 문 «한 커밋» 안으로. 지운 행 거두기가 처리됨 «앞»으로 온다 |
| ⑥ | 편집 거두기 범위를 W 좌석이 짓는다 — 쓴 결과(`written`)에서 «이번에 안 쓴 칸»으로. 프로세스 메모리 판단이 빠진다 |
| ⑦ | R → W 사이에서 좌석이 출신을 단다 — 맵퍼가 표시 열을 버렸어도, 건넨 행과 낸 행의 키가 한 행으로 맞으면 그 행. 안 맞으면 «출신 모름»을 규칙 이름으로 말한다 |
| ⑧ | `_reloaded` 를 try 안으로 — 끊긴 연결은 «다시 돎», 슬롯은 안 죽는다. 기동 실패만 set aside |
| ⑨ | 기준에 스키마(현재 search_path)를 더하거나, 그대로 두고 «DB 하나에 체인 하나»를 운영 전제로 적는다 — 정할 것 |

---

## 4. 다섯 단계 정본 좌석 — 제안

| 단계 | 좌석 하나 | 거기로 오는 것 |
|---|---|---|
| L 리스트 | `pending_chain_events` (iw:4224) | 줄 고르기 · 같은 거래 끌어오기 · 깊이 거절 · `wakes` 거르기 |
| G 그룹 | `group_id` / `group_events` (iw:473 · 504) | 줄 열쇠 · trim · merge · 쪽 · 맵 묶음 · key_pages 크기 |
| D 받기 | `outbox_expand.expand_events` (iw:2147)를 넓힌 것 | 맵 · 잡 전체(규칙 선언이 말함) · 조인 값 표 · 다음 쪽 |
| R 돌리기 | `rule_run.run_rule` (rr:589) | `held_back` 이 첫 줄로 남음 · 출신 달기 · 맵퍼는 받은 틀만 |
| W 쓰기 | `apply_chain_writes` → `crud._apply_batch_updates_once` | 회수 · 빈 재계산 · 사라진 키 · 껍데기 · 편집 거두기 · 지운 행 거두기 · 처리됨 표시 — 그룹당 커밋 하나 |

리플레이 · fold_units · 파일 교체 · R2 는 «L 과 G 를 자기가 짓고 W 로 바로 간다». 다섯 좌석을 지나게 하는 것이 문 합치기의 몸통이다.
크기 · 시간 · 바뀌는 줄 수는 안 쟀다.

---

## 5. 모르는 것

- 한 그룹의 실제 커밋 수(묶음 · 쪽이 몇인지에 따름) — 안 셌다
- `dt_map_derivation.apply_retraction` 의 커밋 줄 — 탐색이 «dt_map_derivation:975» 를 냈고 내가 열지 않았다
- ②b · ⑦ 의 «읽힌다»는 판으로 안 쟀다. ⑦ 은 고정 판 f4n(열 고르는 맵퍼, 빨강이어야 함)으로 잰다
- 그룹당 커밋 하나로 접을 때 1,000 행 그룹의 잠금 · 시간 — 안 쟀다(운영 규격 1,000 행 ≤ 5 초)
