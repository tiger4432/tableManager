# Server — product-owned table installer

**Date:** 2026-07-27 · **Owner:** server-pm · **Status:** implemented, verified, uncommitted (follow-up on `4ba13ae`)

Installing assyManager's own storage tables (`wafer_map_metadata`, `map_split_registry`,
`map_doe`, `map_doe_source`) is now the product's job, not the operator's. The operator
keeps only what is genuinely theirs: the site-owned factory tables.

---

## 1. Deliverables

| File | Status | Role |
|---|---|---|
| `server/product_tables.py` | committed in `4ba13ae`, **modified since** | The single definition |
| `server/scripts/install_product_tables.py` | committed in `4ba13ae` | Merge engine + CLI |
| `server/tests/test_install_product_tables.py` | committed in `4ba13ae`, **modified since** | 39 tests |
| `server/config/table_config.json.sample` | **modified since** `4ba13ae` | Regenerated from the corrected definition |

The follow-up change: **four missing column declarations added** to `PRODUCT_TABLES`, the
sample regenerated from it, and a new guard that compares the declaration against the
*code* rather than against another declaration.

---

## 2. The correction, and how I got it wrong

### 2.1 What was wrong

`map_doe` and `map_doe_source` were declared without `updated_by` and `eventtime`. The
committed sample was taken as canonical; the live site config, which has all four, was
reported as "additive drift" and left alone.

That was backwards. Both columns are written by the product, and `map_doe.eventtime` is
read back:

| Column | Write | Read |
|---|---|---|
| `map_doe.eventtime` | `client2/src/transfer_plan.js:1016` | `:1222` → `S.serverSavedAt` → `:437` renders the `서버 <시각>` chip |
| `map_doe.updated_by` | `client2/src/transfer_plan.js:1016` | no targeted read; in `display_columns`, so it shows in the grid |
| `map_doe_source.eventtime` | `client2/src/transfer_plan.js:1034` | as above |
| `map_doe_source.updated_by` | `client2/src/transfer_plan.js:1034` | as above |

**Why an undeclared column is not cosmetic** — `server/database/crud.py:562`:

```python
col_types = config.get("column_types", {})
if col_name not in col_types:
    continue
```

The column is **silently dropped**. The request still returns 200. A site deployed from the
pre-fix sample would save its DOE plan successfully, lose both columns on every write, and
simply never show the `서버 <시각>` chip — a working feature failing with nothing on the wire
to explain it. That is the exact defect class this `.sample` work exists to remove.

### 2.2 Two method errors, because they generalise

**"No code reads them" was a search result, not a fact.** My grep looked for the column
names on lines that also mentioned the table's key columns. The columns actually live as
keys inside an `updates` object literal, sharing a line with another key
(`updated_by: CURRENT_USER, eventtime: nowStr,`). No search of that shape could have
matched. When the claim is "nothing uses X", the burden is to exhibit the write path and
the read path for that table — read the row-construction block whole; an empty grep is not
evidence.

**Canonical ≠ authoritative.** I preferred the committed sample over the live config
because the sample is version-controlled. But the sample is the artifact this task exists
to *repair* — it was v1-stale, which is the premise of the work. The live config is what a
working system actually runs on. When the two disagree, the running system is the evidence
and the tracked artifact is the suspect.

### 2.3 The full audit, done the right way

Rather than diffing two configs, I enumerated every column the product **writes** for each
product table by reading each row-construction block in full, then compared against the
declaration in both directions:

| Table | Write site | Columns written | Undeclared | Declared but never written |
|---|---|---|---|---|
| `wafer_map_metadata` | `map_editor.js:3039` | map_pk, target_table, map_id, grid_metadata | none | none |
| `map_split_registry` | `map_editor.js:185` | split_key, ref_table, map_key, value, split_desc, color, eventtime | none | none |
| `map_doe` | `transfer_plan.js:1009` | …note, **updated_by**, **eventtime** | **2 (now fixed)** | none |
| `map_doe_source` | `transfer_plan.js:1029` | …note, **updated_by**, **eventtime** | **2 (now fixed)** | none |

After the fix the correspondence is exact in both directions for all four tables. The audit
surface was bounded: those four columns were the *only* behaviour-bearing difference between
the live config and the sample — `wafer_map_metadata` and `map_split_registry` had none at
all, and there were no sample-only columns anywhere.

### 2.4 The guard that makes this not recur

`TestProductWritePathsAreDeclared` extracts the keys of each `updates: {...}` payload from
the client sources and asserts every one is declared. It locates payloads by the table's
business-key column, so it does not depend on line numbers, and a payload it cannot find is
a **failure**, not a silent skip.

This is the check a config-vs-config diff structurally cannot provide: it compares the
declaration against the code.

> **The first version of this guard was itself wrong, in the same way.** It pulled keys with
> a line-anchored regex, which reports only `updated_by` from
> `updated_by: CURRENT_USER, eventtime: nowStr,` — so it passed while missing the very
> column at issue. Injection **L** exposed it: the shipped bug was caught only incidentally
> by the sample-equality test, not by the guard written for it. The extractor now tokenises
> properly (quotes, both comment styles, brace depth, and "a key is an identifier preceded
> by `{` or `,`" so a ternary cannot fake one), and `TestUpdatesLiteralExtractor` tests it
> directly — including the two-keys-on-one-line shape and the ternary case.

---

## 3. Where the single definition lives

`server/product_tables.py` → `PRODUCT_TABLES`. Nothing else declares these tables.

Two consumers derive from it: the installer, and `table_config.json.sample`, whose product
section is *generated* by running the installer against the template:

```
python server/scripts/install_product_tables.py --sample --apply --overwrite-drift
```

Enforced mechanically, not by convention: `test_sample_product_section_equals_the_module`
fails the moment the two disagree, and `test_no_other_module_hard_codes_these_declarations`
walks `server/**` for a third copy. Both proved non-vacuous (injection **K**; and a planted
duplicate module made the second test fail on cue).

A Python module rather than canonical JSON because `server/config/**` is gitignored except
`*.sample`, so a canonical JSON there would not ship. `product_tables.py` sits alongside
`paths.py` / `event_constants.py`, this repo's pattern for single-definition modules.

---

## 4. Merge rules

**Target:** `paths.config_path("table_config.json")` by default, so `ASSY_DATA_ROOT` already
points it at an isolated data root. `--config <path>` overrides; `--sample` targets the
tracked template (compared strictly — comments included — because it is a generated
artifact, not a user asset).

| Situation | Behaviour |
|---|---|
| Product entry absent | **Added**, appended at the end |
| Present and identical | **No-op** — file not opened for writing, no backup |
| Present but different | **Drift.** Reported in full, never changed without `--overwrite-drift` |
| Site-owned entry | **Never touched.** Not reordered, reformatted, or re-serialised |
| Dry run | **The default.** Writing requires `--apply` |
| File missing | Error, exit 2 — refuses to create it |

### Byte preservation

`json.load` + `json.dump` would round-trip the whole file and reformat entries the script
must not touch. Instead the file is parsed once with the stdlib for correctness, a top-level
span scanner locates each member's byte range, and edits are applied as **splices**. Line
endings, indent unit, UTF-8 BOM, key order and per-entry spacing all survive. The scanner
cross-checks its spans against the parsed object and refuses to edit on disagreement (e.g.
duplicate top-level keys).

After writing, the file is read back and every member not deliberately changed is compared
byte-for-byte against the original; a mismatch restores the original and exits 2.

### Drift classification

- **BLOCKING** (`missing`, `changed`) — the entry no longer says what the product needs.
  Exit 1. **A site on the stale sample lands here**: its `map_doe` is missing two product
  columns.
- **additive** (`extra`) — the site added something on top. Exit 0, still reported, still
  never overwritten without the flag.

`display_columns` is the one list where an in-order superset counts as additive.
`composite_key_source` deliberately is not: appending there rewrites every business key.
Misreporting a benign append as BLOCKING would train operators to reach for
`--overwrite-drift`, which then deletes what they added (injections **F**/**G** cover both
directions).

`__comment` is an annotation — `init_dynamic_models` never reads it — so a reworded comment
never flags an operator's file.

### Backup and write style

`--apply` writes `<config>.bak.<YYYYMMDD-HHMMSS>` first and prints the path. The write is
then **in place and deliberately not atomic**:

> Measured on a watchdog `Observer` using `ConfigChangeHandler`'s exact trigger condition:
> **in-place rewrite → `on_modified` fires. temp+rename → only `on_moved` fires**, which
> `database/config_watcher.py` does not implement.

Atomic rename is the safer file operation but would silently skip the runtime ALTER path
(`CONFIG_GUIDE` §6.B). The backup covers the truncation window, and a test monkeypatches
`os.replace`/`os.rename` to raise so a future refactor to atomic writes fails the suite.

---

## 5. What the operator must do after running it

The script prints this itself. It issues **no DDL and opens no database connection** —
verified on the import graph, not by substring.

| Change | What makes it physical |
|---|---|
| **New table** | `config_watcher` on the in-place write (fires — measured) · `POST /admin/reload-configs` · restart. All reach `create_missing_dynamic_tables`. |
| **Columns added to an existing table** — including the `updated_by`/`eventtime` repair | **Only** `config_watcher` → `sync_dynamic_tables_schema`. `/admin/reload-configs` does **not** ALTER. |

Verify against `information_schema.columns`. `GET /tables/{t}/schema` reads the config
singleton, so a 200 there is not evidence of a physical column.

**Exit codes:** `0` nothing left to do · `1` action required · `2` error.

---

## 6. Verification

`conda run -n assy_manager`. No live database written, no server restarted, no commit. The
live `server/config/table_config.json` was **read only** throughout — every test works on a
copy under `tmp_path` or in an isolated `ASSY_DATA_ROOT`, and both E2E scripts assert the
live file's hash is unchanged at the end.

### 6.1 Suite

```
server/tests/test_install_product_tables.py                          39 passed
server/tests/  (excluding test_map_overlay / test_bonding_plan /
                test_transfer_plan — concurrent refactor)            339 passed
```

The three excluded modules are another agent's in-flight work; **this is not a claim of a
green full suite.** Nothing here touches them.

### 6.2 Required cases, proved by byte comparison

| Case | Test |
|---|---|
| Fresh config, no product entries → all four added | `test_empty_object_gets_every_product_table`, `test_site_only_config_gains_product_tables_and_keeps_the_site_entry` |
| Already correct → **byte-identical**, exit 0, no backup | `test_apply_on_a_correct_config_is_byte_identical` |
| Unusual site-owned entry → **byte-identical** | `test_unusual_site_entry_survives_byte_for_byte` |
| Operator-modified product entry → drift, not overwritten; changed only with the flag | `TestDrift` (7 tests) |
| Run twice → second run a no-op | `test_running_twice_changes_nothing_the_second_time` |

The "unusual" fixture is awkward on purpose: non-standard key order, an extra key, its own
`__note` comment key, 4-space indent in a 2-space file, a one-line array, slack whitespace
around colons. All unchanged, and the test asserts key order was not normalised.

### 6.3 Defect injection — 13 defects, 0 MISSED

Originals restored from exact bytes and hash-verified.

| # | Injected defect | Caught by |
|---|---|---|
| A | Re-serialise the whole file instead of splicing | 7 tests + 1 fixture error |
| B | Overwrite drift without the flag | 5 |
| C | Skip the backup | 2 |
| D | Atomic temp+rename write | 1 |
| E | Write and back up even when nothing to do | 2 |
| F | No additive list handling | 1 |
| G | Additive handling extended to the business key | 1 |
| H | Line ending forced to LF | 1 |
| I | BOM dropped on write | 1 |
| J | Annotations not stripped before comparing | 1 |
| K | Definition changed without regenerating the sample | 3 |
| **L** | **`map_doe.eventtime` dropped — the bug that shipped** | 2, incl. `test_written_columns_are_all_declared[map_doe]` |
| **M** | **`map_doe_source.updated_by` dropped** | 2, incl. `test_written_columns_are_all_declared[map_doe_source]` |

Injection found real defects twice, in two separate passes:

1. **First pass** — two tests passing *vacuously*: the post-write guard restored the file,
   so "the site entry is intact" was true even with a broken merge. Both now assert the
   exit code as well.
2. **This pass** — the new write-path guard under-reporting because of the line-anchored
   regex (§2.4). Without injection **L** it would have sat in the suite looking green while
   blind to the exact bug it was written for.

### 6.4 End-to-end, two paths

**Fresh/normal install** — copy of the **real** site config (20 site-owned tables) in an
isolated `ASSY_DATA_ROOT`, `map_doe_source` spliced out, invoked with no `--config`: dry run
exit 1 byte-unchanged → `--apply` exit 0, table added, **all 20 site entries byte-identical**,
CRLF preserved, one backup → second `--apply` byte-identical, no write, no backup.

> With the corrected definition the real site config now reports **4/4 matching, zero
> drift**. That is the cleanest confirmation that the running system was right and the
> sample was the stale artifact.

**Upgrade from the stale sample** — a site whose `map_doe`/`map_doe_source` lack the two
columns: dry run reports **BLOCKING** with `missing column_types.eventtime` /
`missing column_types.updated_by`, exit 1, untouched → `--apply` alone refuses the drift,
exit 1, still byte-identical, **no backup written** → `--apply --overwrite-drift` repairs
both, prints the ALTER caveat, leaves the site entry untouched → second run byte-identical.

### 6.5 Dogfood

The sample's product section was regenerated by the script itself. `git diff`: 14 insertions
/ 6 deletions, confined to the two `map_doe*` entries (columns + comments). The ~290 lines of
site-example entries were untouched.

---

## 7. Section for `docs/guide/DEPLOY_SETUP.md`

*(Korean, to match the file. Suggested: replace the second bullet of §1-2, and add a step to
§6. Not applied — that file is yours.)*

````markdown
### 1-2. `table_config.json` — 동적 테이블 선언 (**핵심**)

이 시스템의 스키마 SSOT다. 여기 선언된 테이블만 존재한다.

- **제품 소유 테이블은 스크립트가 넣어준다 — 손으로 복사하지 마라.**

  ```bash
  python server/scripts/install_product_tables.py            # 미리보기 (기본값, 아무것도 안 씀)
  python server/scripts/install_product_tables.py --apply    # 실제 반영
  ```

  `wafer_map_metadata` · `map_split_registry` · `map_doe` · `map_doe_source` 네 개를
  `server/product_tables.py`(정의의 단일 원천)에서 읽어 넣는다. **현장 소유 항목은 절대
  건드리지 않는다** — 키 순서·들여쓰기·줄바꿈까지 원본 바이트 그대로 남는다.
  이미 올바르면 파일을 열지도 않는다(백업도 안 만든다).

  - 기존 제품 항목이 정의와 **다르면** 덮어쓰지 않고 무엇이 다른지 출력만 한다.
    바꾸려면 `--overwrite-drift`를 명시해야 한다. 이때 항목 **전체**가 교체되므로
    당신이 추가한 컬럼 선언은 사라진다(물리 컬럼이 지워지진 않지만 선언에서 빠져
    그리드·인제션에서 보이지 않게 된다).
  - `--apply`는 쓰기 전에 `table_config.json.bak.<타임스탬프>` 백업을 남기고 경로를 출력한다.
  - 종료 코드: `0` 할 일 없음 · `1` 조치 필요 · `2` 오류.

> ⚠️ **2026-07-27 이전에 배포한 환경은 반드시 한 번 돌려라.** 그때의 `.sample`은
> `map_doe`·`map_doe_source`에 `updated_by`·`eventtime` 선언이 빠져 있었다. 선언에 없는
> 컬럼은 서버가 **조용히 버리므로**(200은 그대로 떨어진다) 전사 계획 저장이 성공한 것처럼
> 보이면서 계획 헤더의 `서버 <시각>` 칩이 영영 뜨지 않는다. 스크립트가 이를 **BLOCKING**
> drift로 잡아주며 `--apply --overwrite-drift`로 복구한다.

- **내가 추가할 것(현장 소유)**: 우리 공장 로그·맵 테이블 전부. 아래 §2의 기능별 표 참조.

각 테이블에 필요한 것: 컬럼 정의(`column_types`), **비즈니스 키**(`business_key`),
복합키면 `composite_key_source` + `composite_key_separator`.

> ⚠️ **구분자 함정**: 맵 키는 `_`가 흔하고 테이블명에도 `_`가 있다. 복합키 구분자로 `_`를
> 쓰면 파싱이 깨진다. 제품 소유 3종은 `|`를 쓴다 — 새로 만들 때도 `|` 권장.

> **스크립트를 돌린 뒤**: 선언은 물리 테이블이 아니다. **신규 테이블**은 config watcher
> (스크립트가 in-place로 쓰므로 발화한다) · `POST /admin/reload-configs` · 재기동 중
> 아무거나로 생성된다. 반면 **기존 테이블의 컬럼 추가**(위 복구가 여기 해당한다)는 ALTER라서
> **config watcher만** 처리한다 — `/admin/reload-configs`는 ALTER를 하지 않는다. 확인은
> `information_schema.columns`로 하라(`/tables/{t}/schema`는 config 싱글턴을 읽는다).
````

§6 순서 요약에 삽입할 단계:

```markdown
3. **`python server/scripts/install_product_tables.py --apply`** — 제품 소유 테이블 자동 설치
4. **`table_config.json`에 우리 현장 테이블 선언** (여기가 대부분의 작업)
```

---

## 8. Not done / open

- **Not committed.** Modified since `4ba13ae`: `product_tables.py`, the test module, and
  the regenerated `.sample`.
- **Existing deployments need a run.** Any site installed from the pre-fix sample is
  silently dropping `updated_by`/`eventtime` on every DOE save. The repair is an **ALTER**,
  so only the config watcher applies it — see §5.
- **Proposed follow-up: make the silent drop audible.** `crud.py:562` discards undeclared
  columns with no signal, which is what let this stay invisible. A warn-once per
  (table, column) would have surfaced it on the first DOE save. Not done here — shared hot
  path, outside this task's scope.
- **Shared living docs untouched** (`CODE_MAP.md`, `PROJECT_STATUS.md`, `docs/history/`,
  `DEPLOY_SETUP.md`) — other agents active in this tree. The DEPLOY_SETUP section is §7.

## 9. Proposed lessons for `agent_workspace/memory/server-pm.md`

Proposals only — not added directly.

- **함정**: "이 컬럼은 아무도 안 쓴다"를 **grep 결과로 단정**한다. 컬럼이 기대한 문맥이 아니라
  `updates: { ... }` 객체 리터럴 안에 다른 키와 같은 줄로 들어 있으면
  (`updated_by: CURRENT_USER, eventtime: nowStr,`) 그런 모양의 검색으로는 절대 안 걸린다.
  2026-07-27에 이 판단으로 `map_doe`·`map_doe_source`의 감사 컬럼 4개를 제품 정의에서 빠뜨렸다.
  **올바른 방법**: "아무도 안 쓴다"의 입증 책임은 **쓰기 경로와 읽기 경로를 각각 제시**하는
  것이다. 행 생성 블록을 통째로 읽어라 — 빈 grep은 근거가 아니다.
- **함정**: 커밋된 아티팩트(`.sample`)를 버전 관리된다는 이유로 **정본**으로 취급한다. 그
  아티팩트가 바로 지금 고치고 있는 대상이면 순환 논증이다.
  **올바른 방법**: 살아 있는 config와 커밋된 샘플이 다르면 **돌아가는 시스템이 증거이고 샘플이
  용의자**다. 두 선언을 서로 비교하지 말고 **선언을 코드와 대조**하라.
- **함정**: `crud.py`의 `column_types` 게이트는 미선언 컬럼을 **경고 없이 버리고 200을 반환**한다.
  그래서 스키마 누락은 500이 아니라 "기능이 조용히 사라짐"으로 나타난다.
  **올바른 방법**: 테이블 선언을 다룰 땐 "이 컬럼이 빠지면 어떻게 실패하는가"를 먼저 확인하고,
  조용한 실패라면 선언 누락을 BLOCKING으로 취급하라.
- **함정**: 새로 만든 **가드 자체가 조용히 약해질 수 있다** — 줄 단위 정규식으로 키를 뽑으면
  한 줄에 두 키가 있을 때 앞의 것만 보고도 초록으로 통과한다.
  **올바른 방법**: 가드를 만들었으면 **그 가드가 잡아야 할 결함을 주입**해 실제로 실패하는지
  확인하라. 이번에는 주입 L이 없었으면 가드가 무용지물인 채로 남았다.
- **함정**: 사용자 자산 파일을 `json.load` → `json.dump`로 왕복시키면 손대지 않은 항목까지
  재직렬화되어(키 순서·들여쓰기·줄바꿈·BOM) 가짜 diff와 소유권 사고가 난다.
  **올바른 방법**: 최상위 멤버의 **바이트 스팬을 splice**하고, 쓰기 후 재읽기로 "안 건드린
  멤버는 바이트 동일"을 검증해 실패 시 원복한다.
- **함정**: 안전망(쓰기 후 롤백)이 있으면 보존 테스트가 **공허하게 통과**한다.
  **올바른 방법**: 상태 검증에 **종료 코드/결과 보고까지 함께 단언**한다.
- **함정**: 무해한 추가(superset)를 BLOCKING으로 보고하면 운영자가 `--overwrite-drift`류
  플래그를 습관적으로 쓰게 되어, 그 플래그가 결국 그들이 추가한 것을 지운다.
  **올바른 방법**: drift를 "동작을 깨는 것"과 "덧붙인 것"으로 분류하되, 리스트 예외는 최소
  범위로만 둔다(`display_columns`는 예외, `composite_key_source`는 절대 아님).
- **함정**: 배포 스크립트가 비ASCII를 출력하면 Windows cp949 콘솔에서 깨지거나 죽는다.
  **올바른 방법**: 출력 리터럴은 ASCII로, 진입점에서 `sys.stdout.reconfigure(errors=...)`.
