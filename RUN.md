# 지금 돌리면 되는 것

> 이 파일은 **푸시할 때마다 갱신**됩니다. 지금 main 에 있는 것 기준입니다.
> 전부 `server/` 에서 돌립니다. 운영은 그 환경의 `python`, 박스는 `C:\Users\kk980\anaconda3\envs\assy_manager\python.exe`.

---

## 0. 지금 순서 «셋» (2026-09-16 10:5x 기준 — 이 순서대로 하시면 됩니다)

---

### 🔴🔴 ⓞ 재기동 «전»에 «먼저» — 마이그레이션 하나 (2026-09-16 22:2x 추가)

**pull 하신 코드는 `cell_sources` 에 컬럼 하나를 «씁니다». 그 컬럼이 없는 데이터베이스에서는
모든 쓰기가 죽습니다** — `create_all` 은 «이미 있는 표»에 컬럼을 절대 안 더합니다.

```bash
psql "$DATABASE_URL" -f server/migrations/add_cell_source_origin_row.sql
```

```
안 돌리고 재기동하면   (psycopg2.errors.UndefinedColumn) column cell_sources.origin_row_id does not exist
                    -> 인제션·체인·그리드 편집이 «전부» 멈춥니다
비용                ADD COLUMN ... NULL 은 PostgreSQL 11+ 에서 «메타데이터만» 바꿉니다 — 표를 다시 안 씁니다.
                    행이 3천만이든 0이든 같습니다. 백필 «없습니다»
인덱스              CONCURRENTLY 라 «잠그지 않습니다». 중간에 끊기면 무효 인덱스가 남으니 그때만 확인:
                    SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
                    WHERE NOT i.indisvalid AND c.relname='idx_sources_by_origin';
새 DB               아무것도 안 하셔도 됩니다
```
**무엇이 좋아지나:** 체인이 «다른 표의 행을 읽어» 채운 칸이, 그 «읽힌 행이 지워지면» 같이 사라집니다.
지금까지는 남아 있었고, 남은 값은 «측정한 값»과 화면에서 구별되지 않았습니다.

### 🔵 재기동 뒤 로그에서 볼 줄 (이번 라운드)

```
[ChainRetract] table=<표> deleted_rows=N groups=G cells_withdrawn=C protected_skipped=P
```
지워진 행이 «먹이던» 칸 C 개를 거뒀다는 뜻입니다. `cells_withdrawn=0` 은 정상입니다 —
그 행이 아무 칸도 안 먹였거나, 도장이 생기기 «전»에 쓰인 칸이라는 뜻입니다(소급 없음).


---

### ① pull + 재기동 — 🔴 **사흘 끌던 인제션 멈춤이 여기서 풀립니다**

그 산출물이 안 들어간 이유는 **선인출 진단기**였습니다. 청크가 느릴 때(기본 1.0 초 초과) 실행 계획을 한 번 찍어 주는 자리인데, 그것이 **이미 닫힌 세션의 객체를 다시 읽으려다** 던졌고 그 예외가 **파일을 통째로** 데려갔습니다. 그래서 ⓐ 그 산출물 하나만, ⓑ 매번 같은 자리에서, ⓒ `__force__` 로도 안 됐습니다 — 방아쇠가 파일이 아니라 «걸린 시간»이었기 때문입니다.

pull 하시면 그 자리가 ① 세션을 안 쓰고 아이디를 읽고 ② 그래도 무엇이 터지면 **계획만 건너뛰고 청크는 그대로** 갑니다.

```
[Ingest] <표> chunk N: ... · INSIDE THE WRITE · prefetch 10.xxx s ...   <- 계속 나옵니다(느린 건 그대로)
[Ingest] <표> prefetch 10.xxx s over 1.0 s - PLAN (once per file) | target: ... | cell_sources: ...
```
🔵 **두 번째 줄이 이제 파일당 한 번 뜹니다.** 그 줄의 `target:` / `cell_sources:` 에 `Seq Scan` 이 보이면 인덱스를 안 타는 것이고, `Index Scan` 이 보이면 인덱스는 타는데 양이 많은 것입니다 — 그 한 줄만 주시면 다음 수리가 갈립니다.

> ⛔ **급할 때 끄는 스위치:** 설정 폴더의 `ingestion_settings.json`(그 설치의 config 경로) 에 `"slow_prefetch_explain_seconds": 9999` 를 넣으시면 됩니다. 계획 줄만 사라지고 인제션은 그대로입니다.

### ② 「가림 N」 세기 — 제가 기다리는 수입니다 (읽기만, `--apply` 없음)

```bash
python scripts/count_absent_null_layers.py
```

마지막 줄의 «가림» 숫자 하나만 주시면 됩니다. 0 이 아니면 그만큼 조인 값이 파일의 빈 층에 가려져 «안 보이는» 중입니다 — 지우기는 되돌릴 수 있게 별도로 올리겠습니다. 뜻은 §1-bis 표에.

### ③ 조인이 «안 선다»고 느껴질 때만 — §1 로

지금은 조인이 서 있어야 정상입니다. 안 서면 §1 의 한 줄이 이유를 셋 중 하나로 가릅니다. 평소엔 안 돌리셔도 됩니다.

### ④ 「savepoint 명령은 트랜잭션 블럭에서만」이 보이면 — 끄는 스위치가 있습니다

로그(체인·인제션 워커)에 아래 낱말 중 하나가 보이면 같은 것입니다:

```
savepoint 명령은 트랜잭션 블럭에서만 사용할 수 있음   ·   SAVEPOINT   ·   25P01
no_active_sql_transaction
```

**무엇인가:** 큰 적재 뒤에 도는 «통계 다시 재기(ANALYZE)» 좌석이 연결 하나를 빌려 쓰고 **되돌려 놓지 않은 채** 반납합니다. 그 연결을 다음에 받은 작업이 이 문장을 뱉습니다. **적재된 행은 무사합니다** — 그 뒤에 그 연결을 쓴 «다른» 작업이 실패합니다.

> ⛔ **끄는 법:** 설정 폴더 `ingestion_settings.json` 에 `"analyze_after_rows": 0`.
> 그 좌석이 아예 안 돕니다. 대가는 큰 적재 직후 «페이지 질의가 한동안 느린 것»이고, 수리가 착지하면 되돌리시면 됩니다(기본값으로 돌리려면 그 줄을 지우십시오).

🔴 **순서가 증거입니다.** 같은 표에 대해 이 줄이 «먼저» 나오고 뒤에 위 문장이 나오면 이 사슬이 맞습니다:

```
[<표>] statistics re-analysed after N row(s) ...      (성공해도 오염은 남습니다)
[<표>] could not re-analyse after N row(s): ...       (실패해도 마찬가지)
```

⚠️ 이것은 **사흘 장애가 풀리면서 드러난 것**입니다 — 그 적재가 끝까지 가게 되자 이 좌석이 처음으로 돌았습니다. 수리는 진행 중(S-272)이고, 착지하면 이 절을 지우겠습니다.

### ⑤ 「체인이 도는가」를 한 줄로 — 🔴 «할 일이 없다»와 «멈췄다»를 가릅니다

```bash
curl -s http://127.0.0.1:8080/health
```
(포트는 그 설치의 API 포트. 브라우저로 열어도 됩니다.)

그 답에서 **수 둘만** 보십시오 — `checks.workers.chain.age_seconds` 와 `checks.outbox.pending`:

| 대기(pending) | 체인 박동(age) | 뜻 | 조치 |
|---|---|---|---|
| 0 | 몇 초 이내 | ✅ 정상 — 할 일이 없는 것 | 없음 |
| 0 | 낡음/없음 | 🔴 **루프가 죽었다** — 큐가 비어 있어 «정상처럼» 보입니다 | 재기동 |
| > 0 | 몇 초 이내 | 🔴 루프는 도는데 **소비를 못 한다** | 아래 ⑤-bis |
| > 0 | 낡음/없음 | 🔴 멈췄고 쌓이는 중 | 재기동 |

🔴 **두 번째 줄이 제일 위험합니다** — 대기가 0 이라 화면상 아무 문제도 없어 보이는데 체인은 죽어 있습니다. 「인제션은 잘 되는데 체인이 아예 안 돈다」가 이 모양입니다.

⚠️ **맨 위의 `status` 단어는 «보지 마십시오».** 일꾼이 전부 멀쩡해도 감독자 파일이 낡으면 `unhealthy` 로 나옵니다(알려진 결함, 큐 S-273). **수 둘**이 답입니다.

### ⑤-bis 쌓인 것이 «무엇인지» 볼 때만

```bash
python scripts/outbox_triage.py --count
```

읽기만 합니다(`--apply` 없이는 아무것도 안 바꿉니다). 표가 «표 이름 · 모양 · 사유»로 나옵니다 — 그 세 낱말을 주시면 제가 다음을 가릅니다.

⚠️ **§6(PG 시험)은 코드를 고친 뒤에만** 돌리시면 됩니다 — 운영에서 정기로 돌릴 것이 아닙니다.
---

## 1. 조인이 왜 안 서는지 «한 줄로» 가른다 — 조인이 왜 안 서는지 «한 줄로» 가른다

```bash
python scripts/check_one_row_one_fact.py --db
```

읽기만 합니다. 답이 셋 중 하나이고 **수리가 전부 다릅니다**:

| 답 | 뜻 | 고칠 곳 |
|---|---|---|
| 키가 «신원보다 좁은» 조인 | 유일 인덱스가 «영원히» 못 섭니다 | 🔴 **선언** — 조인 키를 신원까지 넓히기 |
| 같은 키 행이 있음 (진짜 중복) | 사본이거나 다른 사실이거나 | 아래 2번으로 가름 |
| 키가 «비어 있는» 행 | 중복이 아니라 **부재** | 키를 채우거나 null 정책 선언 |

## 1-bis. 어제까지 쌓인 «파일의 NULL 층» 세기 (S-243-b — 읽기만)

```bash
python scripts/count_absent_null_layers.py
```

판정 405 는 «앞으로의 쓰기»를 고쳤습니다 — 파일의 빈 칸은 이제 층을 안 세웁니다. 그런데 그전에 세워진 층은 그대로 남아 조인 값을 «오늘도» 가립니다. 이 명령은 그 수를 내며, 아무것도 쓰지 않습니다(`--apply` 가 «없습니다»).

| 답 | 뜻 | 조치 |
|---|---|---|
| 「NULL 층: 없음」 | 이 설치엔 쌓인 것이 없습니다 | 없음 |
| 가림이 **0** | NULL 층은 있지만 그 밑에 값이 없습니다 | 없음 — 지워도 화면이 안 바뀝니다 |
| 가림이 **0 아님** | 그 수만큼 조인 값이 «안 보이고» 있습니다 | 그 수를 총괄에게. 지우기는 별 지시(S-243-c)이고 «먼저 내보낸 뒤» 되돌릴 수 있게 |

🔴 이 명령이 「없음」이라 해도 «조인이 잘 보인다»는 뜻이 아닙니다 — 이 수는 «파일이 세운 빈 층» 하나만 셉니다.

## 2. 접어도 되는지 가른다 (1번이 「진짜 중복」일 때만)

```bash
python -c "import sys;sys.path.insert(0,'.');sys.stdout.reconfigure(encoding='utf-8');from database.database import SessionLocal;from virtual_join import unique_key;db=SessionLocal();print(unique_key.describe_fold_plan(unique_key.fold_plan(db,'<표>',['<조인 키>'])));db.close()"
```

* 「접어도 되는 키 N」 → 진짜 사본. 접으면 됩니다
* 「접으면 데이터가 사라지는 키 N」 → **접지 마십시오.** 신원이 그 컬럼이 아니라는 뜻입니다

## 2-bis. 거절·경고 줄은 이제 «조치»를 실어 옵니다 (S-247)

이 자리에 «해독표»가 있었습니다 — 운영 로그를 밖으로 못 내오므로 줄의 뜻을 여기서 풀어야 했기 때문입니다. 지금은 줄 자체가 답합니다:

```
[<자리>:<규칙 또는 표>] 무엇이 일어났나 (표본: ≤3) → 다음: <무엇을 하나>
```

🔴 «다음:» 절을 그대로 따르십시오. 같은 「중복 키」라도 수리가 «정반대»인 자리가 있습니다 — 「행들을 하나로 합치십시오」(데이터)와 「선언에 컬럼을 더 적으십시오」(선언)는 서로의 질문에 대한 «틀린 답»입니다.

| 줄 앞머리 | 무엇을 말하나 |
|---|---|
| `[join_into:<규칙>]` | 오른쪽 표에 같은 키의 행이 둘 — 그 왼쪽 행만 건너뜀 |
| `[VirtualJoinUnique:<규칙>]` | 쓰기가 가상 조인의 오른쪽 유일성을 어기려 함 — 해당 행만 건너뜀 |
| `[BKConflict:<표>]` | 표의 «신원»이 두 행을 못 가름 — 그 배치 거절 |
| `[VirtualJoinIndex:<표>]` | 조인의 유일 인덱스 상태 — 없음·INVALID·빈 키·진짜 중복 |

🪦 `invalid input syntax for type double precision: ""` 는 `ddd5b3ba` 부터 안 납니다(S-245). 재기동 뒤에도 나면 «다른 자리»입니다 — 줄의 SQL 을 보고 올려 주십시오.

## 3. 급할 때 끄는 스위치 (환경변수, 재기동 필요)

```bash
ASSY_CHAIN_WORKER=0        # 체인 루프 자체를 안 띄움 (API·읽기는 그대로)
# 규칙 «하나»만 끄려면: 그 규칙이 적힌 파일(chain_rules · enrichment_rules · virtual_join_rules)에서 `enabled: false` — 부팅 줄 set(N) 이 이름을 전부 보여 줍니다
ASSY_VJOIN_AUTO_INDEX=0    # 제품이 유일 인덱스를 자동으로 세우지 않음 — 🔴 1497ea3e 부터 OFF 는 «DB 를 한 번도 안 만짐»(그 전엔 점검 SQL 이 여전히 돌아 안 멎었음)
```

## 4. 통합 뒤 모양 미리보기 (읽기 전용, 안 써도 됨)

```bash
python scripts/preview_unified_declarations.py --out ../unified_preview.json
```

왕복이 하나라도 깨지면 **아무것도 안 씁니다.**

---

## 부팅 로그에서 볼 것 (재기동 뒤)

```
[ChainRules] set(N): 이름[출처,방식] 표=값 ... (꺼진 건 OFF)   <- 무엇이 도는가. synt = 제품이 만든 규칙
[ChainRules] refused(N): 이름(사유)                          <- 무엇이 «안» 도는가
[ChainRules] 지난 적재와 다름 - 사라짐 1: ...                  <- 선언을 바꾼 뒤 무엇이 달라졌나
[VirtualJoin:이름] 조인 키 (...) 가 ... 의 «신원»(...)보다 좁습니다   <- 1번과 같은 진단
[VirtualJoin] 인덱스 uq_vjoin_… (표) 를 «제품이» 걷어냈습니다 … 다음: 없음   <- 규칙 없는 인덱스가 그 표의 쓰기를 막던 것이 풀림 (S-248). 이 줄 뒤 dedup 영구 실패가 멎어야 함
Transaction … permanently failed: N event(s) -> FAILED. 원인: <예외 문장>   <- 이제 traceback 첫 줄이 아니라 «원인»이 실림
[ChainRule] rule=… kind=… target=… rows_in=N updates=N written=M|None refusal=… elapsed=…
     🆕 (2026-09-16) 「이 규칙이 돌았나」는 «이 한 줄»로 봅니다 — 종류를 «몰라도» 됩니다
     kind 이 builtin:… 이면 updates=0 written=M  (스스로 씀)  ·  모듈.함수 이면 updates=M written=None (제안함)
     written=None 은 «0 이 아니라» 「안 셌다」입니다
[ChainBuiltin] rule=… table=… rows_in=N written=M ← woke_by=<표>#<tx> hop=h/max   <- 조인 오른쪽·자동 확정이 «왜» 돌았나. 쓴 것이 0 이면 DEBUG(안 보임). 같은 규칙은 첫 줄 + 500 마다
[Chain Depth] outbox#… reached hop N, over the declared limit of M; refusing it   <- 고리가 상한에서 끊김(정상). 더 길게 가야 하면 chain_rules.json 최상위 max_chain_depth
[ChainRules] 고리: A → B → A (순서는 선언 순 · 홉 상한 …)   <- 오류 아님. 한 번만 뜸
```

## 5. 통합 선언에 «join» 적기 (S-237 착지 — 가상 조인은 그대로, 이건 «체인»)

🔴 **지금은 «파일에 직접» 적으십시오.** 어드민 chain 탭의 저장은 이 모양을 옛 문법으로 재서 «거절»합니다(S-244, 구현자 맨 먼저). 적은 뒤 재기동하거나 어드민 「설정 반영」(SYSTEM_RELOAD)을 누르면 로더가 읽습니다.

`chain_rules.json` 의 `rules` 에 이 모양 하나를 적으면 체인 규칙 **둘**이 섭니다(왼쪽 트리거 + 오른쪽 트리거는 페이싱). 값은 대상 표의 «진짜 컬럼»에 «자기 층»으로 써지고, 원장이 그대로 봅니다.

```jsonc
{
  "name": "inventory_confirmed",
  "on":     { "table": "dt_inventory" },                       // columns 는 적지 마십시오 — 왼쪽 키에서 유도됩니다(판정 398)
  "derive": { "kind": "join",
              "join": { "right_table": "dt_job_attribution",
                        "on":   [ { "left": "dt_job", "right": "dt_job" } ],
                        "take": [ "dt_lot_confirmed", "dt_slot_confirmed" ] } },
  "into":   { "table": "dt_inventory" },
  "key":    { "unique": true }                                 // 재기동/반영 때 «제품이» 오른쪽 표에 유일 인덱스를 세웁니다(S-240)
}
```
* fold 는 적지 않습니다 — 두 표의 표기 선언에서 «계산»됩니다(판정 397). `max_rewrite_rows` 도 없습니다 — 페이싱(판정 396).
* `key.unique: true` 면 재기동/반영 때 «오른쪽 표»에 유일 인덱스가 섭니다. 중복이 있으면 «안 세우고» 값과 건수를 로그에 냅니다 — 그때는 2번(접기)으로 가르십시오. `ASSY_VJOIN_AUTO_INDEX=0` 이면 아무것도 안 만듭니다.
  `key.columns` 는 «맞는지 보는» 칸입니다 — 조인의 오른쪽 키와 다르면 두 목록을 이름 대고 «안 세웁니다»(다른 컬럼에 세우면 이 조인이 그 인덱스를 안 씁니다). 안 적어도 됩니다.
* 재기동 뒤 부팅 줄에서 확인: `[ChainRules] set(N): inventory_confirmed[decl,join] …` 가 «둘» 보여야 합니다.
* 오른쪽 값이 null 이면 «null 로» 써집니다. 오른쪽 행이 없으면 안 씁니다.
* 오른쪽 행이 «둘 이상» 이면 그 왼쪽 행은 안 씁니다(둘 다 답이 아님) — 나머지 행은 그대로 써집니다. 로그 한 줄:
  `[join_into:이름] N left row(s) matched MORE THAN ONE right row and are skipped by name ...`
  이 줄이 보이면 «오른쪽 표의 데이터»에 같은 키가 둘인 것입니다 — 2번(접기)으로 가십시오. 선언을 고칠 일이 아닙니다.
* 켜면 «지금부터 바뀌는 행»이 조인됩니다. **기존 행 소급(S-242 착지):** 어드민 소급 탭 → `chain_replay` → 규칙 이름은 **왼쪽 규칙**(오른쪽 `…:reference` 는 이름 대고 거절됨) → pace `slow` 또는 `trickle` → «세기»(「다시 계산할 행」 수가 뜸) → 실행. 왼쪽 표 전체 행이 대상입니다(박스 실측 488,429 행). 한 페이지가 던지면 그 페이지만 세고 계속 갑니다(`pages_failed`).

### 5-bis. 같은 파일에 «읽기 시점» 조인 적기 (S-251)

`into` 가 «택1» 입니다 — `table` 이면 «쓰는» 조인(위 §5), `read: true` 면 «읽을 때 답하는» 조인입니다. 읽기 조인은 값을 «저장하지 않고» 조회 응답에서 채워집니다.

```jsonc
{
  "name": "log_frame_from_inventory",
  "on":     { "table": "dt_log" },                     // 왼쪽 표
  "derive": { "kind": "join",
              "join": { "right_table": "dt_inventory",
                        "join_key": [ { "left": "dt_job", "right": "dt_job" } ],
                        "expose": [ "dt_frame" ] } },
  "into":   { "read": true }                           // ← 이 한 칸이 «읽기 시점»
}
```

* `virtual_join_rules.json` 에 적은 것과 «완전히 같습니다» — 같은 검증 · 같은 이름공간 · 같은 유일 인덱스 요구 · 같은 회수 대상. 두 파일 중 «어디에 적었나»가 뜻을 바꾸지 않습니다.
* ⛔ **같은 이름을 두 파일에 적으면 «거절»입니다** — 한 이름은 한 조인입니다. 거절 줄이 그 이름을 댑니다.
* 이 선언은 «체인 규칙이 아닙니다» — 부팅 줄의 `[ChainRules] set(N)` 에 «안 뜹니다»(쓰는 게 없으니 트리거도 맵퍼도 없습니다). 가상 조인 쪽 줄에서 확인하십시오.
* 기존 `virtual_join_rules.json` 은 «그대로 읽힙니다». 옮길 필요 없습니다.

## 6. 재기동 «전» PG 시험 (S-256)

```bash
python scripts/run_pg_tests.py
```

* SQLite 가 «받아 주는» 것을 PostgreSQL 이 «거절하는지»를 이 박스의 PG 서버(격리 DB, 운영 DB 는 이름으로 거절)에서 잽니다 — `passed` 면 재기동 · `skipped` 는 «통과가 아닙니다»(`-rs` 줄이 이유: 서버 도달 불가·확장 없음) · `failed` 면 재기동 «전»에 고침 · `REFUSED` 한 줄(종료 64)이면 서버 DB 가 PG 가 아니거나 격리 DB 선언이 없는 것 — `ASSY_PG_TEST_DATABASE_URL=postgresql://…/assy_qa` 로 선언합니다.
