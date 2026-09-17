# 런타임 한 장 — 「지금 뒤에서 무엇이 도나」 (2026-09-10)

> 소유자: 「지금 아키텍처 너무 복잡해져서 뭐가 뭔지 모르겠음」 · 「뭐가 백에서 도는지 모르겠는데」
> 이 장의 용도는 하나다 — **운영 로그 한 줄이나 느려짐 하나를 30초 안에 «어느 고리»로 돌리는 것.**
> 부품의 «속»은 각 문서(`backend.md` · `event_driven_backend.md` · `CODE_MAP.md`)에 있다. 여기는 «겉»만 적는다.

## 0. 프로세스 — 둘 중 하나의 모양으로 돈다
```
통합 모드 (uvicorn 단독)  uvicorn 한 프로세스 안에 ①웹 + ②워처 + ③체인(+④⑤) 이 «같이» 산다 — 개발·박스용
                      기동 로그: 「Directory Watcher started …」 · 「Chained Ingestion Worker background task spawned.」
                      · 🆕 경고 「[Chain Worker] running INSIDE the API process - a slow tick blocks every HTTP request …」(판정 406 ②)
분리 모드 (런처 = 운영)  런처(run_decoupled_app.py)가 API 자식에 DECOUPLED=True «와» ASSY_CHAIN_WORKER=0 을 넘긴다
                      웹은 「Decoupled mode active. Skipping inline …」 을 찍고 «웹만» 한다(체인 루프는 이 프로세스에 «없다»)
                      워처(run_watcher.py) · 체인(run_chain_worker.py) · 수집기(run_auto_update.py) 가 «각자 프로세스»
                      감독(runtime/process_supervisor.py)이 살리고 죽인다(백오프 2·4·8·16·32 s)
ASSY_CHAIN_WORKER=0   uvicorn 을 손으로 띄웠는데 체인만 «안» 돌리고 싶을 때의 스위치. 로그는 info 「[Chain Worker] NOT started in this process」(경고가 아니다 — 런처 아래서는 정상)
```
🔴 통합 모드에서는 아래 표의 «모든 고리가 한 파이썬 프로세스(GIL)와 한 DB 풀»을 나눠 쓴다.
   조회가 «출렁이면»(같은 질의가 0 → 1.5 s) 먼저 이 줄을 본다 — 질의 모양이 아니라 «옆 고리»다.
🔴 [2026-09-15 22:3x 박스 장애 · 판정 406 · S-252 — 착지 `07143bbe`·`86016d10`] 통합 모드의 ③은 ①과 «같은 이벤트 루프»다. 그날 소비할 수 없는 제어 행(`RETROACTIVE_RUN` 은 수집기의 것)이 대기열에 남아 ③이 틱마다 그것을 집고 «비지 않았다»며 대기를 건너뛰어 ①이 굶었다(await 없는 고리 — py-spy 로 잰 것 · DB 막힘 0).
   오늘: ③은 «자기 행만» 집고(`pending_chain_events` — 제어 타입을 SQL 에서 뺀다) «처리 0 인 틱»은 `idle_wait()` 로 기다린다(S-252). 그리고 운영(런처)에서 ③은 API 프로세스에 «없다» — 위 상자대로 `run_chain_worker.py` 하나다(판정 406). ⚠️ **«오늘 없어진» 것이 아니다**(2026-09-16 정정 `585adbc5`): `DECOUPLED=True` 에 기동부가 체인 시작 «전»에 반환하므로 런처 배포에는 «있던 적이 없고», `ASSY_CHAIN_WORKER=0` 은 그 사실을 환경에 적는 «둘째» 명시적 가드다. 위 상자의 경고가 겨누는 것은 «손으로 띄운» uvicorn 이다. 통합 모드는 남아 있되 «경고하며» 돈다. 속은 [event_driven_backend §3 머리](./event_driven_backend.md).

## 1. 고리 — 여섯 칸: 어디서 · 무엇이 깨우나 · 주기 · 만지는 표 · 자기 로그 줄 · 손잡이
| # | 고리 | 어디서 | 깨우는 것 · 주기 | 만지는 표 | 자기 로그 줄 (grep 낱말) | 늦추기 / 끄기 |
|---|---|---|---|---|---|---|
| ① | **웹 라우트** | 웹 | 요청 | 동적 표 · `cell_sources` · `cell_overwrites` · 원장(walk) | `[get_table_data] Total … ID Scan … Layer Merge … Other` (S-123) | 없음 — 요청은 곧 사용자 |
| ② | **워처 (파일 인제션)** | 웹(통합) / run_watcher | `raws/` 파일 이벤트 · 기동 스윕 · **300 s 주기 재스캔**(`watcher-periodic-sweep`) | 그 표 + `file_ingestion_logs` + 큰 적재 뒤 `ANALYZE <표>` (S-124) | `[<표>] … rows` · `statistics re-analysed after N row(s)` | 파일을 `raws/` 밖으로 · `ingestion_settings.json` `analyze_after_rows`(0=끔) · 10 MB 초과는 `watcher-heavy-lane` 스레드로 격리 |
| ③ | **체인 워커** | 웹(통합) / run_chain_worker | `database_outbox` 의 LISTEN/NOTIFY(≤2 s) · **5 s 스윕** | 규칙의 `target_table` 들 · `database_outbox` · 정렬(alignment) 표 | `[Chain]` · **그룹 줄 세 층**(아래 §1-bis) · **`[Chain] batch: broadcast dispatch … · groups N`** · `[ChainWaiting] <표>: N group(s) deferred behind …` · `[Chain] tx … deferred: rows_not_visible …` · `Failed to execute mapper in tx …` · 🆕 **`Transaction … permanently failed: N event(s) -> FAILED. 원인: <마지막 줄>`**(S-248 `90d971ba` — 종전엔 트레이스백의 «첫 줄»「Traceback (most recent call last):」을 실어 하루 종일 원인이 안 보였다) · 🆕 **표마다·스윕마다 `[ChainWaiting]` 한 줄**(머리의 사유를 들고, S-157) · 🆕 **거절·경고 줄 넷은 «다음 행동»을 싣는다**(S-247 `3aab7173`) — `[join_into:<규칙>]` · `[VirtualJoinUnique:<규칙>]` · `[BKConflict:<표>]` · `[VirtualJoinIndex:<표>]` … `→ 다음: <행동>`. grep 낱말은 `다음:` 하나, 저자는 `server/operator_line.py`, 표는 `RUN.md` §2-bis · 🆕 `[Warmup] 유일 키 설치 건너뜀 …` / `[Warmup] 선언된 유일 키를 세우지 못했습니다(체인은 계속)`(S-240 — 통합 join 의 `key.unique` 를 웜업이 세운다) | `chain_rules.json` 의 규칙 `enabled:false` · **`max_group_attempts`**(🆕 [S-221 `fc0914a7`] «규칙 칸이 먼저» · 문서 칸은 «기본값» · 없으면 1 — 합친 단위는 «최소») · **`max_rows_not_visible_defers`**(기본 30 ≈ 1분, 문서 «최상단» 칸) — ⚰️ 종전 「셋 다 문서 최상단」은 오늘 거짓이다. 셋 다 «SYSTEM_RELOAD 로 반영»되는 것은 그대로 |
| ③-b | **LISTEN 커넥션** | ③ 안 | `database_outbox` 채널 알림 | (읽지 않음 — 알림만) | `[Outbox Listener]` | 🔴 **풀 «밖» 전용이다**(S-167): `psycopg2.connect` 로 «풀이 본 적 없는» 커넥션을 쓰고 `_reset_connection` 의 close 는 «진짜 닫기»다. ⛔ `engine.raw_connection()` 으로 되돌리지 말 것 — LISTEN 이 요구하는 autocommit 이 «풀로 반납»되면 다음 대여자가 트랜잭션을 못 열어 `begin_nested()` 가 25P01 로 터진다(그 형태로 112 회 실측) |
| ③-a | **outbox 정리** | 체인 안 | 1 h | `database_outbox` (7 일 지난 행 삭제) | `[Outbox Purge]` | 없음(소량) |
| ③-c | **격리 재전개** | ③ 안(실패 뒤) | 그룹 실패 | `database_outbox` (자식 사건) | 자식의 `reexpanded_from.depth` | 🆕 **«이분»이다**(S-173) — 실패한 청크를 «반»으로 가른다. 독 든 행 하나가 사건 «21 개»를 쓴다(종전 1,000). 각 반쪽이 자기 트랜잭션 그룹이고 자식이 «자기 경로»를 접두로 남겨(`a`·`ab`·`abb`) 접두 검색 하나로 계보가 나온다. 상한 `MAX_REEXPANSION_DEPTH = 12` |
| ④ | **원장 후속 큐** | 체인 안(별 태스크) | 큐 + pace `chain_followup`=`trickle`(1 단위 · 3 s) | 원장(`ledger_*`) · 커서/등록부 | 🆕 `[LedgerFollowUp] lap: N item(s) in T s, M left in the queue (rest R s between)` · 🆕㉕ **인리치 «자동 확정»도 이 랩에서 돈다**(S-179 ①) — 그것은 별도 기제가 아니라 «체인 규칙의 종류»이고(`enrichment_auto_confirm:` 합성 규칙, `follow_up`), 따라서 이 고리의 «그룹 하나»로 세어진다. 커밋 경로에는 «없다» — **«움직인 바퀴»에만 찍는다**(빈 바퀴 줄은 움직인 바퀴를 묻는다). `[LedgerFollowUp]` · 영수증은 `/audit_logs/recent` `ledger_batch` (S-117) · 🆕 **[09-15 S-249 `b1e89e36`·`6edf4db4`] 이 랩은 «홉»이다** — 원인 tx 의 `chain_depth+1` 로 쓰고 ③의 `max_chain_depth` 를 «만난다»(종전엔 홉이 안 찍혀 이 길의 고리는 «무한») · (원인 tx, 표, 규칙)당 «한 번»만 준다(`이 원인(tx …)의 행은 이미 한 번 받았습니다. 건너뜁니다`) · 이벤트를 그룹 경로처럼 «접는다» · 줄은 **`[ChainBuiltin] rule=… table=… rows_in=… written=… ← woke_by=<표>#<tx> hop=h/max`** — 안 쓴 랩은 DEBUG, 같은 (규칙, 표)는 첫 줄 뒤 500 마다 `(xN)` | `pacing.json` `jobs.chain_followup` (재기동 없음) |
| ⑤ | **원장 센서스** | 체인 안(별 태스크) | pace `ledger_row_census`=`background`(1 소스 · 60 s) — «한 바퀴 = 소스 수 분» | 읽기만: `pg_class`(추정) · 등록부 `rows_indexed`(S-122-b) · **뷰 소스만 count(*)** | `[LedgerCensus]` 바퀴 벽시계 한 줄 | `pacing.json` `jobs.ledger_row_census` (재기동 없음) · 정확 수는 사람이 `python -m ledger census` |
| ⑥ | **수집기 (auto_update)** | run_auto_update | 5 s 틱 · 각 수집기의 `next_run` | 수집기가 쓰는 표(→ ② 와 같은 경로로 적재) | `Scheduler daemon started` · 수집기 이름 | `auto_update` 설정의 그 수집기 |
| ⑦ | **PG 자기 일** | DB | 큰 적재·삭제 뒤 «스스로» | autovacuum / autoanalyze / `CREATE INDEX CONCURRENTLY` | `pg_stat_activity` · `pg_stat_progress_vacuum` · `pg_stat_progress_create_index` | PG 설정(우리 것 아님) |

### 🆕 §1-quinquies. `follow_up` 종류는 «길이 하나»다 (2026-09-12 S-195)
```
종전   인리치 스윕이 `_auto_confirm_followed_rows` 에서 «디스패처 옆»에서 «직접» 불렸다
       -> `follow_up` 한 종류가 «도는 길이 둘» — 그 금지가 이름 붙은 임시방편을 이고 있었다
오늘   좌석 «하나»를 지난다 — `rule_run.resolve(rule)` 가 이름을 풀고 `run_rule` 이 돌린다.
       ⚰️ 이 줄은 `chain_builtins.BUILTIN_KINDS` «표 하나»라고 적고 있었다. 그 표는 판정 562 에서
       지워졌고(종류가 아니라 «맵퍼»다), 그 파일은 `3c9da31f` 에서 `chain/synthesis.py` 가 됐다
```
🔴 **일은 «안 바뀌었다» — 바뀐 것은 「어떻게 찾히나」다.** 그리고 규칙이 «선언»에서 온다:
`AutoConfirmCollector` 는 이미 `rules` 를 받는데, 안 주면 `load_enrichment_rules` 로 «다시 찾았다»
— 합성된 규칙이 이미 들고 있는 것을.
📐 그 목록은 «리로드당 한 번» 실린다(`_followup_builtin_rules` :1682) — **드레인 배치마다 규칙 파일을
다시 읽던 것**을 그만뒀고, 무효화는 이 프로세스의 «다른 캐시와 같은 자리»에 있다
(`reload_worker_process_cache`). ⚠️ **리셋 없는 캐시는 「리로드가 아무 뜻도 없게 되는」 이유**다.

### §1-bis. 체인 «그룹 줄»의 모양 — 세 층, 층마다 «남은 시간»까지 (S-151, 판정 241·261)
```
group <tx>: view builds N · reference resolutions N · distinct maps N · T s
            · MACHINERY   · <stage …>       · unnamed U s      <- 그룹 전체를 쪼갠 층
            · INSIDE THE VIEW · <phase …>   · unnamed U s      <- `mapper` 안
            · INSIDE THE WRITE · <step …>   · unnamed U s      <- `write:*` 안 (셋째 dict)
batch: broadcast dispatch T s · groups N                       <- 배치당 «한 번», 그래서 자기 줄
```
🔵 **`unnamed` 이 층마다 찍히는 이유**: 이름 붙은 조각의 합이 그 층의 벽시계와 «맞는지»를 읽는 사람이
검산할 수 있어야 하기 때문입니다. 그리고 배치 발사는 그룹당이 아니라 «배치당»이라 어느 그룹에 달면
그 그룹의 합이 «검산 안 되는 수»가 됩니다 — 그래서 줄을 따로 뺐습니다.
⚠️ **정렬을 한 번도 안 만진 그룹은 이 줄을 «안 찍습니다»** — 0 으로 채운 줄이 진짜를 묻어 버립니다.

### §1-ter. 워처 «청크 줄» — 체인과 «같은 계수기»를 쓴다 (S-164, `parsers/directory_watcher.py`)
```
[Ingest] <표> chunk N: R row(s) in T s · STAGES · <스테이지…> · unnamed U s · INSIDE THE WRITE · <스텝…>
```
🔵 **새 계기를 만들지 않고 체인의 `alignment_batch_counts` 를 «그대로» 연다** — 두 계수기를 두면
같은 낱말이 두 곳에서 다른 것을 뜻하게 된다. 층 모양도 그룹 줄과 같다(`unnamed` 잔여 포함).
🔵 **이것이 운영에서 «읽혀서» S-168 이 됐다** — 운영 apply 19 s/1k = 선인출 10 · 행 만들기 1 · 부수 표 7
(이 박스 0.03 · 0.37 · 0.42). 운영을 여기서 잴 수 없으므로 «계기를 보내고 값을 받는다»가 방법이다.

### §1-quater. 🔵 **이 표를 «화면»이 대신 읽는다 — `GET /runtime`** (S-176, 09-11)

```
자리      `GET /runtime` (관리자 토큰) · 조립은 `server/runtime/loops.py` 의 `LOOPS` 아홉
아홉      web · watcher · chain · outbox_purge · listen · ledger_followup · ledger_census · scheduler · postgres
          = 이 표의 ①~⑦ 에 ③ 을 «셋»으로 가른 것(③ · ③-a · ③-b)
🔴 ③-c 는 «없다**  재전개는 «자기 lap 을 보고하지 않는다» — 그룹이 실패했을 때만 도는 «행동»이지
          주기를 가진 고리가 아니다. 그래서 이 지도에는 «행»이 있고 화면에는 «칸»이 없다.
          ⚠️ 둘을 억지로 맞추지 말 것 — 지도는 「무엇이 도나」를, 화면은 「무엇이 lap 을 내나」를 답한다
값        lap 은 그 고리가 이미 쓰는 `heartbeat.record_lap` 을 타고 온다 — 이 화면은 «아무것도 재지 않는다»
```
🔴 **`/health` 와 «다른 일»이다(판정 282).** `/health` 는 «판정»하고(ok/degraded/unhealthy + HTTP 상태)
`/runtime` 은 «값»을 답한다. 한쪽이 다른 쪽을 대신 정하면 «한 시간 안 움직인 큐 옆에 초록 불»이 선다.
⚠️ **없는 칸은 «생략»이지 0 이 아니다** — 「lap 을 보고한 적 없다」와 「마지막 lap 이 0 초」는 다른 사실이다.
📎 **그러므로 이 문서의 자리가 바뀌었다**: 「무엇이 도나」는 이제 «화면»이 답한다.
   이 장이 답하는 것은 「무엇이 그것을 깨우나 · 무엇을 만지나 · 어디서 늦추나」 — 화면이 못 말하는 쪽이다.

## 2. 증상 → 어느 고리 (오늘 밤에 실제로 온 것들)
```
「모든 표 조회가 느리다, 큐는 비었다」      ⑤ (09-10 전: 소스마다 count(*) 쉼 없이) → 지금은 추정+분 단위. 남으면 ⑦
「ID Scan 이 0.7 s 로 «고정»」            ① 의 정렬이 인덱스를 못 탐 = 통계 낡음(적재 직후) → ANALYZE (② 가 이제 자동)
「Entity Fetch / Layer Merge 가 «출렁»」   대기다. 통합 모드면 ②③④⑤ 중 그때 도는 것, 아니면 ⑦
「SAVEPOINT 가 400 · 25P01」            ③-b 의 LISTEN 커넥션이 «풀로» 반납되던 때의 증상(S-166·S-167).
                                        autocommit 커넥션을 받은 세션은 BEGIN 을 안 내므로 SAVEPOINT 가 앉을 데가 없다.
                                        ⚠️ `in_transaction()` 가드로는 «안 닫힌다» — 그 가드가 있는 빌드에서 112 회 났다
「rows_in=0 인데 SUCCESS」               ⚰️ 09-11 «전»의 증상. 접힌 사건이 자기 행을 하나도 못 읽으면 빈 페이로드로
                                        돌고 SUCCESS 로 찍혔다(조용한 손실, S-158). 지금은 «미룬다» —
                                        `rows_not_visible` 로 이름 대고, `max_rows_not_visible_defers`(기본 30 ≈ 1분)
                                        까지 기다린 뒤에도 못 읽으면 «이름 대어 거절»한다(판정 267).
                                        🔴 원인은 삭제가 아니라 «가시성 시차»였다 — 같은 세션이 100 ms 뒤에 전부 봤다
「`[ChainWaiting]` 가 엄청 뜬다」                ③ 앞 그룹의 «실패»가 원인. 첫 `[ChainWaiting]` 줄 «위»의 `Failed to execute mapper` 를 본다
                                        3회 뒤 격리 경계에서 청크(≤1,000행)가 «행 단위로 펼쳐져» 줄 수가 ×1,000 될 수 있다
「인제션이 느리다」                       ② 의 `cell_sources` 인덱스 볼륨(S-118 뒤 절반) · 큰 파일이면 heavy 레인 한 줄로 직렬
「셀 소스 쓰는 게 계속 살아 있다」          ② 가 청크(1,000행)마다 커밋 — 파일 끝까지는 «살아 있는 게 정상»
```

## 3. 어디에 무엇을 적나 (손잡이는 «셀»이고 재기동이 필요한 것만 표시)
```
server/pacing.json                     ④⑤ 의 pace. 바퀴마다 다시 읽음 → 재기동 없음
server/config/ingestion_settings.json  ② analyze_after_rows · heavy 임계 · 파일 경계 핫리로드 → 재기동 없음
server/config/chain_rules.json         ③ 규칙 enabled · max_group_attempts · max_rows_not_visible_defers
                                          🆕 [S-221 `fc0914a7`] `max_group_attempts` 는 «규칙 칸이 먼저», 문서 칸은 «기본값»이다
                                       ⚰️ **「기동 때만 읽음 → 재기동」은 거짓이었다**(09-11 D-6 실측, 09-11 D-8 재확인):
                                       `load_chain_rules()` 가 SYSTEM_RELOAD 에서도 돌고(:2721) `rules` 를 다시 묶으며,
                                       두 손잡이는 `_RULES_DOCUMENT` 를 «부를 때마다» 읽는다 → **재기동 없음**
DECOUPLED=True                          0 절의 분리 모드 → 재기동
```
### 운영자 «명령» 둘 — 설정이 아니라 «도구»다 (09-11)
```
server/scripts/tune_layer_tables.py   층 표의 배큠 상태를 «읽는다». dry-run 이 기본이고 **아무것도 정하지 않는다**
                                      (dead/live · last_autovacuum · reloptions · progress) — `--apply` 는 표별 설정
server/scripts/outbox_triage.py       터진 재전개 홍수를 치운다 — per-row 사건을 «건너뛰고» 접힌 채로 다시 쏜다
                                      (`--count` 로 먼저 «센다»)
🔵 둘 다 «소유자가 SQL 을 못 낸다»는 제약에서 나온 모양이다(판정 276) — 운영을 여기서 못 재므로
   제품과 도구가 값을 «말해» 주고, 판단은 사람에게 남긴다
```

## 4. 이 장이 아직 못 말하는 것 (적어 두는 미지)
```
· ⑥ 수집기의 «수와 주기»는 운영 설정에 있다 — 여기선 셀 수 없다
· ✅ 「분리 모드 런처가 무엇을 띄우나」도 답이 나왔다 — `server/runtime/launcher_specs.py::child_specs()` 가 정본
  (S-255 `8c824a1e` — 런처 `main()` 이 그 «값»을 받고 시험도 그 값을 읽는다; 종전엔 런처 파일 안의 목록을
  시험이 «텍스트로 잘라» 읽어 주석 하나에 빨개졌다).
  «무조건 넷»: Backend FastAPI Server · File Ingestion Watcher · Chained Ingestion Worker · Auto Update Scheduler.
  «조건부 하나»: Desktop Client UI — `--server-only` 가 아닐 때만 런처 `main()` 이 `specs.append`.
  🔴 그래서 「다섯 프로세스」는 «데스크톱 셸을 세었을 때»의 수다 — 서버만 띄우면 «넷»이다.
  ⚠️ 수를 이 문서에 «박지 않는다»: 정본은 그 `child_specs()` 이고, 여기 적으면 저자가 둘이 된다.
· ⚰️ 「Graph DB Sync」 는 «답이 나왔다» (D-1 실측 09-10, HEAD 1972d392). 그 낱말이 사는 곳은
  «한 줄»이다 — `server/main.py:457` 의 분리 모드 로그:
     「Skipping inline Directory Watcher, Graph DB Sync, and Chained Ingestion workers.」
  그 워커는 `R-2026-08-14-H` 로 은퇴했고 묘비가 `server/runtime/launcher_specs.py` 의 명부 안에 있다(S-255 로 명부와 같이 옮겨졌다).
  🔴 그러므로 그 줄은 «없는 것을 건너뛴다»고 말한다 — 운영자가 「그게 아직 있나」로 읽는다.
  ⛔ 고치는 것은 «코드 한 줄»이라 이 문서 라운드(D-1, 코드 0줄)의 몫이 «아니다» — 큐로 올린다.
· 이 장은 09-10 코드 기준. 고리를 «하나 더 만들 때» 이 표에 «행을 먼저» 넣는다 — 안 넣으면 다음 밤에 또 「뭐가 도나」가 된다
```
