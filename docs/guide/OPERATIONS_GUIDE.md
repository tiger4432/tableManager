# 운영 안내서 — 줄이 뜻하는 것 · 조절 칸 · 그 수가 나오면 할 일

> 늘 참인 문서다. 그때그때 할 일은 RUN.md 에 있다.
> 줄을 짓는 코드를 바꾸는 착지는 이 문서의 그 절도 «같은 착지»에서 고친다.
> 도우미(어드민 Help)가 «왜 느려» 같은 물음에 이 문서의 절과 서버의 마지막 상태 줄을 인용해 답한다.

## 어느 로그에 무엇이 있나

| 로그 파일 | 쓰는 프로세스 | 운영에서 볼 줄 |
|---|---|---|
| server.log | API | STALL · [Slow] |
| watcher.log | 와처(파일 적재) | [Ingest] FILE · [Ingest] chunk |
| chain_worker.log | 체인 워커 | [LayerHealth] · [Chain] |
| launcher.log | 런처 | [Release] · Priority of |
| ledger.log · auto_update.log · retroactive.log | 원장 · 스케줄러 · 소급 | 각 일의 줄 |

어드민 머리의 노란 띠는 마지막 STALL 줄과 그 요청의 [Slow] 줄을 보여 준다. 로그 파일을 열지 않아도 된다.

## STALL 줄 — API 가 굳었을 때 한 줄

꼴

```
STALL 12s P /tables/dt_log/data SELECT cell_sources 9s Lock:relation L0 T6/40 G0 D3/9s SELECT cell_sources
B0 X0 C83 ours:23 api:17 chain.slot.1:6 pg:61 AUTOANALYZE public.database_outbox other:12 IO r180w420MB/s 950iops pgIO7
```

요청이 5 초 넘게 안 끝나거나 API 의 이벤트 루프가 5 초 넘게 답을 안 하면 굳음이다.
굳음이 끝날 때 한 줄, 30 초 넘게 이어지면 30 초마다 한 줄(초 뒤에 «+»)을 쓴다.
칸마다 그 굳음 동안의 «가장 큰 값»이다. 못 읽은 칸은 «?» 이다.

### P — 가장 오래 열린 요청

`P <경로> <문장 머리> <초>s <기다림>` — 그 요청이 DB 에서 돌리던 문장이다(그리드 쪽 읽기처럼 풀 프로세스에 넘긴 것도).
P 뒤에 문장이 없으면 그 굳음 동안 그 요청은 DB 문장을 안 돌렸다(파이썬 계산이나 풀 기다림 — G · T 칸을 본다).

| 기다림 | 뜻 | 할 일 |
|---|---|---|
| cpu | 문장이 돌고 있다(기다림 없음) — 디스크 읽기도 여기 섞일 수 있다 | [Slow] 줄의 단계 중 SQL 이 큰 단계와 IO 칸을 본다 |
| Lock:… | 다른 세션의 자물쇠를 기다린다 | B 칸(누가 쥐었나)을 본다 |
| IO:… | 디스크를 기다린다 | IO 칸을 본다 |
| LWLock:… · BufferPin:… | DB 안쪽 경합 | pg 몫과 autovacuum 을 본다 |

### L · T · G — 이벤트 루프 · 스레드 · 그리드 풀

- L<초>: 이벤트 루프가 답 안 한 초. 크면 API 프로세스 자체가 바쁘다.
- T<쓰는 중>/<전체>: 요청 스레드. 전체에 닿으면 새 요청이 줄 선다.
- G<수>: 그리드 풀 프로세스를 기다리는 요청 수. 크면 grid_processes 를 본다.

### D · B · X — DB 문장 · 자물쇠 · 오래 열린 트랜잭션

- D<도는 문장 수>/<가장 긴 초> <머리>: DB 에서 지금 도는 문장. 머리는 가장 오래 돈 것.
- B<막힌 세션 수> <머리>: 다른 세션에 막힌 세션 수와 가장 많이 막은 쪽의 머리. AUTOVACUUM … 이면 자동 청소가 막고 있다.
- X<초>/<나이> <머리>: 가장 오래 열린 트랜잭션. 오래 열려 있으면 청소가 그 뒤를 못 치운다. X0 은 없음.

### C · IO — CPU 와 디스크

- C<기계 %>: 기계 전체 CPU. 그 뒤 몫은 같은 눈금(기계 전체 %)이다.
- ours: 이 제품 프로세스 합(API · 워커 · 슬롯 · 풀). api: API 자신. 그다음은 가장 바쁜 이름 있는 프로세스.
- pg: PostgreSQL 프로세스 합과, 그중 가장 바빴던 프로세스가 하던 일(문장 머리, 없으면 checkpointer 같은 종류).
- other: 나머지 전부(백신 · 백업 · 다른 프로그램). ours + pg + other = C.
- IO r<읽기>w<쓰기>MB/s <n>iops: 기계 디스크. pgIO<n>: 디스크를 기다리는 DB 세션 수.

| 보이는 것 | 뜻 | 할 일 |
|---|---|---|
| C 높고 pg 큼 | DB 가 CPU 를 쓴다 | pg 뒤 머리와 D · B 칸 — AUTO… 면 자동 청소 · 통계 |
| C 높고 ours 큼 | 이 제품이 CPU 를 쓴다 | 가장 바쁜 이름. 뒤에서 도는 일은 낮은 우선순위로 뜬다 |
| C 높고 other 큼 | 제품 밖 프로그램 | 작업 관리자에서 그 시각의 프로세스 |
| C 낮고 pgIO 여럿 | DB 가 디스크를 기다린다 | MB/s 가 크면 같이 쓰는 일, 작으면 디스크가 느리다 |
| C 낮고 B 큼 | 자물쇠 | B 칸의 머리 |
| C 낮고 G 큼 | 그리드 풀 대기 | grid_processes |

## [Slow] 줄 — 느린 요청 하나가 어디서 시간을 썼나

꼴

```
[Slow] GET /tables/dt_log/data 200 - 응답이 12100ms 걸렸습니다 (예산 1000ms) · db 9800 ms · 41 queries · 5,000 rows · 1,234,567 bytes · layers 8.10 s (SQL 8.02 s · 120,000 rows · Python 0.08 s)
```

slow_request_ms(기본 1000 ms)를 넘은 요청이 끝날 때 server.log 에 쓴다. 노란 띠의 둘째 줄이 같은 문장이다.
단계마다 `<이름> <초> (SQL <초> · <행> · Python <초>)` — SQL 이 크면 그 단계의 문장이, Python 이 크면 서버 계산이 느리다.

| 보이는 것 | 뜻 | 할 일 |
|---|---|---|
| layers 의 SQL 이 크고, 같은 때 cell_sources 의 자동 청소 · 통계(STALL 의 B · pg 머리)가 돈다 | 그리드가 칸 색을 정하려고 cell_sources 를 읽다 청소와 겹친다 | 그 표의 Colours 를 끈다(아래 «Colours 끄기») |

### Colours 끄기

- 표마다: 메인 그리드 Colours 탭에서 그 표의 «Written by person» 행 ×(Off on this table). 다시 켜기는 그 줄의 On here.
- 모든 표: sys_looks 그리드에서 look_table 이 * 인 행(관리자만).
- 효과: 그 표에 «누가 썼나»를 묻는 색 규칙이 없으면 그리드가 cell_sources 를 안 읽는다.

## [Ingest] FILE 줄 — 파일 하나를 다 적재했을 때

꼴

```
[Ingest] dt_log FILE a.csv: 50000 row(s) in 42.000 s (71428 rows/min) · heavy lane · waited 3.100 s (queue + table lock) · sent: new 100 · changed 2000 · unchanged 47900 · cells changed 4100 · ... · STAGES · ... · INSIDE THE WRITE · ... · DB wait samples 120 (Lock 80)
```

watcher.log 에 파일마다 한 줄이다. waited 가 크면 앞 파일이나 표 자물쇠를 기다렸다. DB wait samples 의 Lock 이 크면 쓰기가 자물쇠를 기다렸다.
STAGES · INSIDE THE WRITE 의 가장 큰 단계가 느린 자리다.

## 상태 줄로 답이 안 되는 물음

도우미는 서버가 메모리에 쥔 것(마지막 STALL · [Slow] 줄 · /health)만 읽는다.
파일 적재가 느린 물음(«파일 올리는 게 느려»)은 상태 줄에 없다 — watcher.log 의 [Ingest] FILE 줄을 본다.
체인 표 청소 상태(«dead 행이 많아?»)는 chain_worker.log 의 [LayerHealth] 줄을 본다.

## [LayerHealth] 줄 — 표 건강

꼴 `[LayerHealth] <표>: live <행> · dead <행> · last autovacuum <시각> · autovacuums <수> · xid age <나이> · vacuum <진행>`

chain_worker.log 에 몇 분마다 표 몇 개씩(pacing.json 의 jobs.layer_health 가 고르는 pace — 기본 watch: 300 초마다 8 개).
dead 가 live 에 견줘 크고 last autovacuum 이 오래면 자동 청소가 못 따라온다 — 그 표의 저장 매개변수(autovacuum_*)를 본다.

## [DDL] 줄 — 표 구조 변경이 자물쇠를 못 얻음

꼴 `[DDL] <일> on <표> - its lock not had in <n> tries over <초> s (<ms> ms each); held by <pid> <머리>`

인덱스 만들기 같은 구조 변경은 읽기를 막지 않게 짧게 여러 번 시도한다. 다 못 얻으면 이 줄을 쓰고 다음 차례로 미룬다.
held by 의 머리가 그 표를 쥔 일이다.

## [Release] 줄 — 릴리스 묶음 반영

launcher.log 에 쓴다. 뜻과 할 일은 RUN.md 의 릴리스 블록에 있다.
`not applied … tracked file(s) changed` 이면 이 사본에서 바뀐 파일이 있어 아무것도 안 바꿨다 — 줄의 안내대로 되돌리거나 그 목록을 총괄에게.

## Priority 줄 — 자식 프로세스 우선순위

launcher.log 에 자식마다 한 줄 `Priority of <자식>: below normal | normal`.
와처 · 체인 워커 · 원장 워커 · 스케줄러는 below normal(화면 읽기가 먼저), API 는 normal.

## 조절 칸

### slow_request_ms — 느린 요청 줄의 문턱

config/server_settings.json. 기본 1000(ms). null 이면 [Slow] 줄을 안 쓴다. 다음 요청부터 바로 적용.

### grid_processes · grid_wait_seconds — 그리드 풀

config/ingestion_settings.json. grid_processes 기본 4(그리드 읽기를 도는 프로세스 수, 하나에 약 135 MB · DB 연결 2), 0 이면 풀 없이 API 안에서 돈다.
grid_wait_seconds 기본 60 — 프로세스를 기다리는 최대 초. STALL 의 G 가 자주 크면 grid_processes 를 올린다(메모리 · DB 연결이 같이 는다).

### analyze_after_rows — 적재 뒤 통계 갱신

config/ingestion_settings.json. 기본 10000. 한 번에 이만큼 넘게 들어온 표는 적재 뒤 ANALYZE 한다. 0 이하면 끈다.
STALL 의 pg 머리에 ANALYZE 가 자주 보이고 큰 적재가 잦으면 올린다. 끄면 큰 적재 뒤 읽기 계획이 나빠질 수 있다.

### pacing.json — 긴 일의 속도

config/pacing.json(바꾼 칸만 적는다, 나머지는 기본표). paces: fast(쉼 없음) · slow(5 단위마다 1 초) · trickle(1 단위마다 3 초) · watch · background.
jobs: 스스로 도는 일이 쓰는 pace(layer_health · chain_followup · ledger_row_census · chain_unowned_census · system_runtime).
소급은 거는 사람이 pace 를 고른다 — 화면 읽기가 느려지면 slow 나 trickle. page_seconds(기본 3, 최대 5)는 한 쪽이 노리는 초다.

### 자식 우선순위

운영에서 바꾸지 않는다. 어느 자식이 낮은지는 코드(릴리스)가 정한다 — 추적되는 파일을 고치면 다음 릴리스 묶음의 자동 반영이 «tracked file(s) changed» 로 멈춘다.
지금 낮은 우선순위로 뜨는지는 launcher.log 의 Priority 줄로 본다.

### 문장 · 자물쇠 시간 한도

config/ingestion_settings.json — statement_timeout_seconds · lock_timeout_seconds(파일 쓰기), chain_statement_timeout_seconds(기본 120, 체인 그룹), grid_read_timeout_seconds(기본 10, 그리드 읽기 문장).

### shared_buffers — PostgreSQL 캐시

제품 설정이 아니라 PostgreSQL 의 postgresql.conf 칸이다. 바꾸면 PostgreSQL 서비스를 다시 켜야 적용된다.
STALL 에 pgIO 가 잦고 IO 읽기 MB/s 가 큰데 같은 표를 거듭 읽는다면 올릴 후보다.

- 값: 기계 메모리의 1/4 쯤에서 시작한다(16 GB 면 4GB). PostgreSQL 이 시작을 못 하면 절반으로. 되돌리기는 128MB.
- 다시 켜기: `sc query state= all | findstr /I postgres` 로 서비스 이름을 찾고 `net stop <이름>` 뒤 `net start <이름>`.
