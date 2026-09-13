# 런타임 한 장 — 「지금 뒤에서 무엇이 도나」 (2026-09-10)

> 소유자: 「지금 아키텍처 너무 복잡해져서 뭐가 뭔지 모르겠음」 · 「뭐가 백에서 도는지 모르겠는데」
> 이 장의 용도는 하나다 — **운영 로그 한 줄이나 느려짐 하나를 30초 안에 «어느 고리»로 돌리는 것.**
> 부품의 «속»은 각 문서(`backend.md` · `event_driven_backend.md` · `CODE_MAP.md`)에 있다. 여기는 «겉»만 적는다.

## 0. 프로세스 — 둘 중 하나의 모양으로 돈다
```
통합 모드 (기본)        uvicorn 한 프로세스 안에 ①웹 + ②워처 + ③체인(+④⑤) 이 «같이» 산다
                      기동 로그: 「Directory Watcher started …」 · 「Chained Ingestion Worker background task spawned.」
분리 모드 (DECOUPLED=True)  웹은 「Decoupled mode active. Skipping inline …」 을 찍고 «웹만» 한다
                      워처(run_watcher.py) · 체인(run_chain_worker.py) · 수집기(run_auto_update.py) 가 «각자 프로세스»
                      감독(runtime/process_supervisor.py)이 살리고 죽인다(백오프 2·4·8·16·32 s)
```
🔴 통합 모드에서는 아래 표의 «모든 고리가 한 파이썬 프로세스(GIL)와 한 DB 풀»을 나눠 쓴다.
   조회가 «출렁이면»(같은 질의가 0 → 1.5 s) 먼저 이 줄을 본다 — 질의 모양이 아니라 «옆 고리»다.

## 1. 고리 — 여섯 칸: 어디서 · 무엇이 깨우나 · 주기 · 만지는 표 · 자기 로그 줄 · 손잡이
| # | 고리 | 어디서 | 깨우는 것 · 주기 | 만지는 표 | 자기 로그 줄 (grep 낱말) | 늦추기 / 끄기 |
|---|---|---|---|---|---|---|
| ① | **웹 라우트** | 웹 | 요청 | 동적 표 · `cell_sources` · `cell_overwrites` · 원장(walk) | `[get_table_data] Total … ID Scan … Layer Merge … Other` (S-123) | 없음 — 요청은 곧 사용자 |
| ② | **워처 (파일 인제션)** | 웹(통합) / run_watcher | `raws/` 파일 이벤트 · 기동 스윕 · **300 s 주기 재스캔**(`watcher-periodic-sweep`) | 그 표 + `file_ingestion_logs` + 큰 적재 뒤 `ANALYZE <표>` (S-124) | `[<표>] … rows` · `statistics re-analysed after N row(s)` | 파일을 `raws/` 밖으로 · `ingestion_settings.json` `analyze_after_rows`(0=끔) · 10 MB 초과는 `watcher-heavy-lane` 스레드로 격리 |
| ③ | **체인 워커** | 웹(통합) / run_chain_worker | `database_outbox` 의 LISTEN/NOTIFY(≤2 s) · **5 s 스윕** | 규칙의 `target_table` 들 · `database_outbox` · 정렬(alignment) 표 | `[Chain]` · **그룹 줄 세 층**(아래 §1-bis) · **`[Chain] batch: broadcast dispatch … · groups N`** · `[HOL Guard] Deferring tx …` · `[Chain] tx … deferred: rows_not_visible …` · `Failed to execute mapper in tx …` · 🆕 **표마다·스윕마다 HOL 한 줄**(머리의 사유를 들고, S-157) | `chain_rules.json` 의 규칙 `enabled:false` · **`max_group_attempts`**(기본 1) · **`max_rows_not_visible_defers`**(기본 30 ≈ 1분) — 셋 다 «문서 최상단 칸»이고 «SYSTEM_RELOAD 로 반영»된다 |
| ③-b | **LISTEN 커넥션** | ③ 안 | `database_outbox` 채널 알림 | (읽지 않음 — 알림만) | `[Outbox Listener]` | 🔴 **풀 «밖» 전용이다**(S-167): `psycopg2.connect` 로 «풀이 본 적 없는» 커넥션을 쓰고 `_reset_connection` 의 close 는 «진짜 닫기»다. ⛔ `engine.raw_connection()` 으로 되돌리지 말 것 — LISTEN 이 요구하는 autocommit 이 «풀로 반납»되면 다음 대여자가 트랜잭션을 못 열어 `begin_nested()` 가 25P01 로 터진다(그 형태로 112 회 실측) |
| ③-a | **outbox 정리** | 체인 안 | 1 h | `database_outbox` (7 일 지난 행 삭제) | `[Outbox Purge]` | 없음(소량) |
| ③-c | **격리 재전개** | ③ 안(실패 뒤) | 그룹 실패 | `database_outbox` (자식 사건) | 자식의 `reexpanded_from.depth` | 🆕 **«이분»이다**(S-173) — 실패한 청크를 «반»으로 가른다. 독 든 행 하나가 사건 «21 개»를 쓴다(종전 1,000). 각 반쪽이 자기 트랜잭션 그룹이고 자식이 «자기 경로»를 접두로 남겨(`a`·`ab`·`abb`) 접두 검색 하나로 계보가 나온다. 상한 `MAX_REEXPANSION_DEPTH = 12` |
| ④ | **원장 후속 큐** | 체인 안(별 태스크) | 큐 + pace `chain_followup`=`trickle`(1 단위 · 3 s) | 원장(`ledger_*`) · 커서/등록부 | 🆕 `[LedgerFollowUp] lap: N item(s) in T s, M left in the queue (rest R s between)` · 🆕㉕ **인리치 «자동 확정»도 이 랩에서 돈다**(S-179 ①) — 그것은 별도 기제가 아니라 «체인 규칙의 종류»이고(`enrichment_auto_confirm:` 합성 규칙, `follow_up`), 따라서 이 고리의 «그룹 하나»로 세어진다. 커밋 경로에는 «없다» — **«움직인 바퀴»에만 찍는다**(빈 바퀴 줄은 움직인 바퀴를 묻는다). `[LedgerFollowUp]` · 영수증은 `/audit_logs/recent` `ledger_batch` (S-117) | `pacing.json` `jobs.chain_followup` (재기동 없음) |
| ⑤ | **원장 센서스** | 체인 안(별 태스크) | pace `ledger_row_census`=`background`(1 소스 · 60 s) — «한 바퀴 = 소스 수 분» | 읽기만: `pg_class`(추정) · 등록부 `rows_indexed`(S-122-b) · **뷰 소스만 count(*)** | `[LedgerCensus]` 바퀴 벽시계 한 줄 | `pacing.json` `jobs.ledger_row_census` (재기동 없음) · 정확 수는 사람이 `python -m ledger census` |
| ⑥ | **수집기 (auto_update)** | run_auto_update | 5 s 틱 · 각 수집기의 `next_run` | 수집기가 쓰는 표(→ ② 와 같은 경로로 적재) | `Scheduler daemon started` · 수집기 이름 | `auto_update` 설정의 그 수집기 |
| ⑦ | **PG 자기 일** | DB | 큰 적재·삭제 뒤 «스스로» | autovacuum / autoanalyze / `CREATE INDEX CONCURRENTLY` | `pg_stat_activity` · `pg_stat_progress_vacuum` · `pg_stat_progress_create_index` | PG 설정(우리 것 아님) |

### 🆕 §1-quinquies. `follow_up` 종류는 «길이 하나»다 (2026-09-12 S-195)
```
종전   인리치 스윕이 `_auto_confirm_followed_rows` 에서 «디스패처 옆»에서 «직접» 불렸다
       -> `follow_up` 한 종류가 «도는 길이 둘» — 그 금지가 이름 붙은 임시방편을 이고 있었다
오늘   `chain_builtins.BUILTIN_KINDS` «표 하나»를 지난다. 표 하나, 길 하나
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
「HOL Guard 가 엄청 뜬다」                ③ 앞 그룹의 «실패»가 원인. 첫 HOL 줄 «위»의 `Failed to execute mapper` 를 본다
                                        3회 뒤 격리 경계에서 청크(≤1,000행)가 «행 단위로 펼쳐져» 줄 수가 ×1,000 될 수 있다
「인제션이 느리다」                       ② 의 `cell_sources` 인덱스 볼륨(S-118 뒤 절반) · 큰 파일이면 heavy 레인 한 줄로 직렬
「셀 소스 쓰는 게 계속 살아 있다」          ② 가 청크(1,000행)마다 커밋 — 파일 끝까지는 «살아 있는 게 정상»
```

## 3. 어디에 무엇을 적나 (손잡이는 «셀»이고 재기동이 필요한 것만 표시)
```
server/pacing.json                     ④⑤ 의 pace. 바퀴마다 다시 읽음 → 재기동 없음
server/config/ingestion_settings.json  ② analyze_after_rows · heavy 임계 · 파일 경계 핫리로드 → 재기동 없음
server/config/chain_rules.json         ③ 규칙 enabled · max_group_attempts · max_rows_not_visible_defers
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
· ✅ 「분리 모드 런처가 무엇을 띄우나」도 답이 나왔다 — `run_decoupled_app.py` 의 `specs` 가 정본.
  «무조건 넷»: Backend FastAPI Server(310) · File Ingestion Watcher(315) ·
  Chained Ingestion Worker(326) · Auto Update Scheduler(329).
  «조건부 하나»: Desktop Client UI(335) — `--server-only` 가 아닐 때만 `specs.append`.
  🔴 그래서 「다섯 프로세스」는 «데스크톱 셸을 세었을 때»의 수다 — 서버만 띄우면 «넷»이다.
  ⚠️ 수를 이 문서에 «박지 않는다»: 정본은 그 `specs` 이고, 여기 적으면 저자가 둘이 된다.
· ⚰️ 「Graph DB Sync」 는 «답이 나왔다» (D-1 실측 09-10, HEAD 1972d392). 그 낱말이 사는 곳은
  «한 줄»이다 — `server/main.py:457` 의 분리 모드 로그:
     「Skipping inline Directory Watcher, Graph DB Sync, and Chained Ingestion workers.」
  그 워커는 `R-2026-08-14-H` 로 은퇴했고 묘비가 `run_decoupled_app.py:318` 에 있다.
  🔴 그러므로 그 줄은 «없는 것을 건너뛴다»고 말한다 — 운영자가 「그게 아직 있나」로 읽는다.
  ⛔ 고치는 것은 «코드 한 줄»이라 이 문서 라운드(D-1, 코드 0줄)의 몫이 «아니다» — 큐로 올린다.
· 이 장은 09-10 코드 기준. 고리를 «하나 더 만들 때» 이 표에 «행을 먼저» 넣는다 — 안 넣으면 다음 밤에 또 「뭐가 도나」가 된다
```
