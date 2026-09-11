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
                      감독(process_supervisor.py)이 살리고 죽인다(백오프 2·4·8·16·32 s)
```
🔴 통합 모드에서는 아래 표의 «모든 고리가 한 파이썬 프로세스(GIL)와 한 DB 풀»을 나눠 쓴다.
   조회가 «출렁이면»(같은 질의가 0 → 1.5 s) 먼저 이 줄을 본다 — 질의 모양이 아니라 «옆 고리»다.

## 1. 고리 — 여섯 칸: 어디서 · 무엇이 깨우나 · 주기 · 만지는 표 · 자기 로그 줄 · 손잡이
| # | 고리 | 어디서 | 깨우는 것 · 주기 | 만지는 표 | 자기 로그 줄 (grep 낱말) | 늦추기 / 끄기 |
|---|---|---|---|---|---|---|
| ① | **웹 라우트** | 웹 | 요청 | 동적 표 · `cell_sources` · `cell_overwrites` · 원장(walk) | `[get_table_data] Total … ID Scan … Layer Merge … Other` (S-123) | 없음 — 요청은 곧 사용자 |
| ② | **워처 (파일 인제션)** | 웹(통합) / run_watcher | `raws/` 파일 이벤트 · 기동 스윕 · **300 s 주기 재스캔**(`watcher-periodic-sweep`) | 그 표 + `file_ingestion_logs` + 큰 적재 뒤 `ANALYZE <표>` (S-124) | `[<표>] … rows` · `statistics re-analysed after N row(s)` | 파일을 `raws/` 밖으로 · `ingestion_settings.json` `analyze_after_rows`(0=끔) · 10 MB 초과는 `watcher-heavy-lane` 스레드로 격리 |
| ③ | **체인 워커** | 웹(통합) / run_chain_worker | `database_outbox` 의 LISTEN/NOTIFY(≤2 s) · **5 s 스윕** | 규칙의 `target_table` 들 · `database_outbox` · 정렬(alignment) 표 | `[Chain]` · **그룹 줄 세 층**(아래 §1-bis) · **`[Chain] batch: broadcast dispatch … · groups N`** · `[HOL Guard] Deferring tx …` · `[Chain] tx … deferred: rows_not_visible …` · `Failed to execute mapper in tx …` | `chain_rules.json` 의 규칙 `enabled:false` · **`max_group_attempts`**(기본 1) · **`max_rows_not_visible_defers`**(기본 30 ≈ 1분) — 셋 다 «문서 최상단 칸»이고 «SYSTEM_RELOAD 로 반영»된다 |
| ③-a | **outbox 정리** | 체인 안 | 1 h | `database_outbox` (7 일 지난 행 삭제) | `[Outbox Purge]` | 없음(소량) |
| ④ | **원장 후속 큐** | 체인 안(별 태스크) | 큐 + pace `chain_followup`=`trickle`(1 단위 · 3 s) | 원장(`ledger_*`) · 커서/등록부 | `[LedgerFollowUp]` · 영수증은 `/audit_logs/recent` `ledger_batch` (S-117) | `pacing.json` `jobs.chain_followup` (재기동 없음) |
| ⑤ | **원장 센서스** | 체인 안(별 태스크) | pace `ledger_row_census`=`background`(1 소스 · 60 s) — «한 바퀴 = 소스 수 분» | 읽기만: `pg_class`(추정) · 등록부 `rows_indexed`(S-122-b) · **뷰 소스만 count(*)** | `[LedgerCensus]` 바퀴 벽시계 한 줄 | `pacing.json` `jobs.ledger_row_census` (재기동 없음) · 정확 수는 사람이 `python -m ledger census` |
| ⑥ | **수집기 (auto_update)** | run_auto_update | 5 s 틱 · 각 수집기의 `next_run` | 수집기가 쓰는 표(→ ② 와 같은 경로로 적재) | `Scheduler daemon started` · 수집기 이름 | `auto_update` 설정의 그 수집기 |
| ⑦ | **PG 자기 일** | DB | 큰 적재·삭제 뒤 «스스로» | autovacuum / autoanalyze / `CREATE INDEX CONCURRENTLY` | `pg_stat_activity` · `pg_stat_progress_vacuum` · `pg_stat_progress_create_index` | PG 설정(우리 것 아님) |

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

## 2. 증상 → 어느 고리 (오늘 밤에 실제로 온 것들)
```
「모든 표 조회가 느리다, 큐는 비었다」      ⑤ (09-10 전: 소스마다 count(*) 쉼 없이) → 지금은 추정+분 단위. 남으면 ⑦
「ID Scan 이 0.7 s 로 «고정»」            ① 의 정렬이 인덱스를 못 탐 = 통계 낡음(적재 직후) → ANALYZE (② 가 이제 자동)
「Entity Fetch / Layer Merge 가 «출렁»」   대기다. 통합 모드면 ②③④⑤ 중 그때 도는 것, 아니면 ⑦
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
server/config/chain_rules.json         ③ 규칙 enabled → 🔴 기동 때만 읽음 → 재기동
DECOUPLED=True                          0 절의 분리 모드 → 재기동
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
