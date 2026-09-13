# Server — Header Predicate Fix + Drop Visibility

**Date:** 2026-08-04 · **Commit:** `53b30f9` (main, NOT pushed)
**Files:** `server/parsers/html_topology_parser.py`, `server/parsers/directory_watcher.py`,
`server/tests/test_html_matrix_header_predicate.py` (new),
`server/tests/test_ingestion_drop_visibility.py` (new)
**Suite:** `1958 passed, 2 skipped` (baseline 1941/2, delta +17 = the new tests). No regressions.
`server/main.py` not touched. `client2/` not touched. `docs/` not touched.
`ingestion_workspace/` read only — nothing created, modified, moved or deleted.

---

## ① The structural signal, and why it holds across all four variants

### What the old predicate actually was

`HTMLTableGraphParser._default_is_header` rule 4 answered **"is this a header cell?"** with
**"does `float()` reject it?"**. In a matrix table that is wrong in *both* directions, and both
were measured on the real archive:

| Direction | Effect |
|---|---|
| Numeric **header** value | falls OUT of the header set → LEFT-ancestor chain shifts one cell right → the next GROUP label is consumed as the previous group's value |
| Alphabetic **grid** value | falls INTO the header set → grid data leaks back out as a phantom meta key |

### The signal I chose

> **A cell is a header iff it lies strictly above the X-axis ruler row and is non-empty.**
> The ruler row is found by SHAPE: an **unmerged** corner cell at column 0 that is **not** a
> coordinate, followed by **two or more unmerged cells to its right that all are**. The topmost
> qualifying row wins; the Y ruler is then whatever integer labels sit in column 0 *below* it.

Purely positional. No lexical test survives anywhere in the header decision — which is the point,
because a lot id, a slot number and a wafer id are all legitimately numeric, and the 2026-08-04
`slot`-is-always-int ruling makes numeric header cells the norm.

**Why it holds across the four variants.** The variants differ in *how many groups* (2 or 3) and
*which group labels* appear (`BDIE`/`CDIE`/`AQ`, sometimes `CDIE` twice). None of them differs in
the thing the signal reads: every one of the 19 files has the same three-region layout — title
band, header band, ruler row, grid — and `x_row_idx == 6` in all 19. The signal is orthogonal to
the axis along which the variants actually vary.

**Merged-ness is the load-bearing half, and it is measured, not assumed.** Across all 19 archived
files: **every corner cell and every axis tick is 1x1, and every header-band cell is merged**
(`4x2`, `2x2`, `2x18`). That is what keeps an all-numeric header ROW out — the hardest case, where
a band row has the same arity and the same text as a short ruler row and nothing lexical separates
them. The guard is deliberately strict in this direction: a shape it refuses yields **zero
records**, which is loud, whereas the failure it replaces was a **silently wrong map key** feeding
`map_split_registry`.

**Scope.** Only `HTMLMatrixTableParser.parse_matrix_to_records` re-classifies. `_default_is_header`
is untouched, so `extract_semantic_tuples`, the 9 tests in `test_html_topology.py`, and any
caller-supplied `is_header_fn` keep their behaviour exactly.

### Per-variant red-before / green-after

Fixtures rebuild the archived geometry cell-for-cell (the files themselves are gitignored user
territory). File counts are as of 2026-08-04.

| Variant | Files | Before | After |
|---|---|---|---|
| **V1** two groups, alphabetic lot | 15 | `TITLE, BDIE_LOT=A, BDIE_WF=B, CDIE_LOT=C, CDIE_WF=D` | identical ✅ |
| **V2** three groups (`AQ` present) | 2 | above + `AQ_LOT, AQ_WF` **+ phantom `F_AAA=A`** | phantom gone ✅ |
| **V3** three groups, `CDIE` typed twice | 1 | 5 keys **+ phantom `F_AAA=A`** | phantom gone; the key collision is the file's own doing and stays ✅ |
| **V4** numeric lot `12312` | 1 | 🔴 `{TITLE, BDIE_WF:B, BDIE_LOT:"CDIE"}` — **wrong map key, CDIE_LOT/CDIE_WF gone** | `BDIE_LOT="12312"`, CDIE_LOT/CDIE_WF restored ✅ |

**Full-corpus record-level diff, old parser vs new, over all 19 files:**

```
files=19   byte-identical output=15   changed=4
  ...f7750cf0.html  121 -> 121 records | grid cell payload identical: True
      BDIE_LOT: 'CDIE' -> '12312';  CDIE_LOT: None -> 'C';  CDIE_WF: None -> 'D'
  ...027e6f4d.html  187 -> 187 records | grid cell payload identical: True | F_AAA removed
  ...324f0c43.html  187 -> 187 records | grid cell payload identical: True | F_AAA removed
  ...9f48b116.html  187 -> 187 records | grid cell payload identical: True | F_AAA removed
```

**Grid cell payload identical on all 19.** The data half does not move; only the header block
changes, and only where it was wrong.

### Defect injection — three, each pinning a different half

| Injection | Result |
|---|---|
| **A** HEAD's parser (both halves absent) | **5 of 10 fail** |
| **B** new ruler detection, OLD lexical predicate restored | **5 of 10 fail** |
| **D** new predicate, but merged ruler cells allowed | **exactly 1 fails** — `test_a_numeric_header_row_is_not_mistaken_for_the_ruler` |

D is worth noting: my first attempt at that test **passed under injection**, because the fixture
builder hard-coded the `LOT`/`WF` key labels and so the band row was never all-numeric. I rewrote
the fixture by hand until the guard was genuinely load-bearing. `test_v4_fixture_actually_activates_the_defect_axis`
asserts the same property for V4 — it fails if anyone "fixes" the numeric lot id to a friendlier value.

### Already-ingested data now known-wrong: **0 rows**

Live DB, read-only. The corrupted key `CDIE` appears in **0 `bonding_map` rows, 0
`map_split_registry` rows, 0 `wafer_map_metadata` rows**. `bonding_map` today holds one map
(`REF_BASE`, 413 rows) — the table has been cleared and repopulated since those files were
archived. The defect was live and reproducible on a real archived file, but its output does not
survive in the database. **No repair needed.**

---

## ② Drop visibility — reframed per the mid-round correction

Adjusted. Nothing in the shipped code or comments calls this data loss; `TITLE` / `BDIE_WF` /
`CDIE_LOT` / `CDIE_WF` are treated as **fields of a superseded scheme whose absence from
`information_schema` is the intended state.** No column is routed anywhere, no schema is proposed.

**What remains true and is what shipped:** the `display_columns` filter at
`directory_watcher.py:1837` runs before `crud`, so `crud._warn_undeclared_column_once` cannot fire
and a drop leaves **no record of any kind**. The problem is not those columns; it is that an
operator cannot tell an intended drop from **a genuinely new or misspelled column vanishing
exactly as quietly**.

### The shape

`개별 침묵 + 명명된 총계`, sized so the expected case stays quiet:

- **nothing** per row or per cell — at 10M rows that buries every real event;
- **WARNING once per (table, column) per process**, on FIRST sighting — the moment a new column
  appears. Steady-state old-scheme columns spend their one warning at process start and then stop
  shouting, so a *later* warning means something actually changed;
- **INFO per file** with names and counts, so 0 dropped and 200 dropped never look the same.

A per-file WARNING would have been trained away within a day — that is the reason for the split,
and injection **C** (naive warn-every-file) fails 5 of 7 tests, so the sizing is pinned rather than
incidental.

### Replayed on the real archive (parser → the user script's rename → the real filter, DB stubbed)

```
WARNING [bonding_map] ... NO per-cell record is created for them: bdie_wf, cdie_lot, cdie_wf, title.
        First sighting in this process, carried by '...f7750cf0.html'. If the drop is intended (a
        field of a superseded scheme) this is the expected state; if the column is new or
        misspelled, declare it in config/table_config.json. Repeats are reported at INFO...
INFO    [bonding_map] Dropped 4 undeclared column(s) over 121 row(s) of '...f7750cf0.html':
        bdie_wf=121, cdie_lot=121, cdie_wf=121, title=121 (name=non-blank values discarded)...

WARNING [bonding_map] ... : aq_lot, aq_wf.  <-- ONLY the new ones. The four known are not repeated.
INFO    [bonding_map] Dropped 6 undeclared column(s) over 187 row(s) of '...324f0c43.html': ...

INFO    [bonding_map] Dropped 4 undeclared column(s) over 121 row(s) of '...2c5a5407.html': ...
        <-- third file: no WARNING at all
```

That second line is the whole feature working on real data: a column the operator has not seen
before surfaces **by itself**, not buried in a repeat of the known ones.

Scale: `dropped_value_counts` is a per-file dict of column names, capped at
`MAX_DROPPED_COLUMNS_REPORTED = 64` (mirrors `crud._MAX_UNDECLARED_WARNED_PER_TABLE`); saturation
is announced in the line, never silent. Per dropped cell the cost is one dict increment and a
`val is not None and val != ""` test — no allocation, no `str()`. ASCII only; no emoji, no U+2014.

### 🔵 Proposal, NOT built this round — a way to declare expected drops

The remaining gap: the first-sighting WARNING still fires once per process for columns everyone
already knows about, and a restart replays it. If that proves noisy, the honest fix is a
**declaration**, not a louder or quieter log: an optional `expected_dropped_columns: [...]` list per
table in `table_config.json`. Columns in it report at INFO only and never warn; everything else
warns on first sighting. That turns "we know about these" from tribal knowledge into a config fact
the log can check against, and it costs one lookup. **Lead PM call — I did not build it.**

---

## 🔴 For the second-emission round (out of scope here, but it changes the inputs)

1. **Do not design it around these header fields.** Per the user's ruling they are a superseded
   scheme. `TITLE`, `BDIE_WF`, `CDIE_LOT`, `CDIE_WF`, `AQ_*` are what these *archives* happen to
   carry; what the header should contribute has to be decided against the **current** scheme.
2. **What ① changed about the extraction output** — the second emission reads the header off the
   row dict, so these matter:
   - `F_AAA` **no longer exists**. It was a phantom built from grid BIN letters, present in 3 of 19
     files. Anyone who inventoried the header keys from the archive before today would have
     recorded it as a real field. It is not one.
   - The genuine observed key space is now exactly: `TITLE`, `{GROUP}_LOT`, `{GROUP}_WF` where
     `GROUP ∈ {BDIE, CDIE, AQ}`. Three shapes, not four — V3's "fourth shape" was V2 with the
     third group label typed as `CDIE` again, so `CDIE_LOT`/`CDIE_WF` genuinely collide and the
     last wins. **A composite header key can collide inside one file**, which any header-row table
     must decide about explicitly (last-wins, or refuse the file).
   - `BDIE_LOT` (→ `base`, the map key) is now **correct for numeric lot ids**, which is the
     precondition my previous report set for the second emission shipping at all.
3. The key-agreement constraint from the previous report is unchanged: compose the identity through
   `map_meta_registrar.compose_map_id` **by import**, off the same normalized row dict, at the same
   work-unit boundary.

---

## Boundary contracts

**None touched.** No REST signature, no WS event name or payload, no cell shape, no
`table_config.json` change, no schema contract. `HTMLMatrixTableParser.parse_matrix_to_records`
keeps its exact signature and return shape; only the *values* in the header block change, and only
where they were wrong. The one user pipeline script that consumes it
(`server/ingestion_workspace/bonding_map/scripts/bonding_map_parser.py`, gitignored) reads only
`BDIE_LOT` and `VALUE` — both verified unaffected by grep and by end-to-end replay.

## Doc impacts (NOT applied — `docs/` was out of scope)

| Doc | Why |
|---|---|
| `guide/HTML_TOPOLOGY_PARSER_GUIDE.md` | §3.6 documents `HTMLMatrixTableParser`. The header/axis detection rule is now positional + shape-based; the guide describes the old behaviour. **Stale as of this commit.** |
| `architecture/CODE_MAP.md` | `parse_matrix_to_records` gained `_ruler_row`; `directory_watcher` gained `_announce_dropped_columns`, `MAX_DROPPED_COLUMNS_REPORTED`, `_dropped_column_announced`. |
| `docs/history/` | entry + `gen_index.py` — draft below. |
| `qa/FEATURE_CHECKLIST.md` | worth a line for "numeric lot id in a bonding-map header". |

A doc-keeper trigger fired during this round (46 commits since last sync). Flagging, not acting.

### History draft

> **본딩맵 헤더 판정을 위치 기반으로 교체 + 드롭 컬럼 가시화** (`53b30f9`)
> `_default_is_header` 규칙 4가 "숫자로 파싱되면 헤더가 아니다"로 판정해, 숫자 lot id
> (`BDIE/LOT/12312`)가 헤더 집합에서 빠지고 LEFT 조상 체인이 한 칸 밀려 **맵 키가 `"CDIE"`로
> 조용히 오염**됐다(`map_key_columns:["base"]` = `BDIE_LOT`). 반대 방향으로는 격자 BIN 문자가
> 헤더로 승격돼 유령 키 `F_AAA`가 3개 파일에 생겼다. 판정을 **눈금 행 위/아래라는 위치**로
> 교체하고, 눈금 행은 **모양**(병합 안 된 코너 + 병합 안 된 정수 눈금 2개 이상)으로 찾는다 —
> 아카이브 19파일 전수 실측에서 눈금은 전부 1x1, 헤더 밴드는 전부 병합. 구/신 파서 레코드 전수
> 대조: 19건 중 15건 완전 동일, 1건 키 교정, 3건 유령 제거, 격자 값은 19건 전부 동일. 라이브
> DB에 오염 잔존 0행. 결함 주입 3종으로 각 절반을 각각 적색화. 별건으로,
> `display_columns` 필터가 `crud` 이전에 돌아 드롭이 **아무 기록도 남기지 않던** 문제를
> 「개별 침묵 + 명명된 총계」로 가시화(첫 목격 1회 WARNING + 파일당 INFO 집계).

## Proposed lessons (for 총괄 review — not added directly)

1. **함정**: 「이건 헤더인가」를 **텍스트 모양**(숫자냐 아니냐)으로 답하면, 값이 숫자여도 되는
   도메인(lot·slot·wafer id)에서 **양방향으로** 틀린다 — 헤더가 빠지고 데이터가 들어온다. 그리고
   둘 다 예외 없이 SUCCESS로 통과한다.
   **올바른 방법**: 문서가 스스로 선언하는 **기하학적 기준선**(눈금 행·격자 원점)을 찾아 **위치로**
   판정한다. 기준선 자체도 텍스트가 아니라 **모양**(병합 여부·1x1)으로 찾고, 그 모양이 실물
   코퍼스 전수에서 성립하는지 **세어서** 확인한다("19파일 전부 1x1"). 거부하면 0행이 나오는
   방향으로 엄격하게 잡아라 — 조용한 오답보다 시끄러운 빈 결과가 낫다.
2. **함정**: 결함 주입 테스트의 **픽스처가 결함 축을 활성화하지 못하면 주입해도 초록**이 나온다.
   이번에 실제로 발생 — 「전부 숫자인 헤더 행」 테스트를 빌더로 만들었더니 빌더가 `LOT`/`WF`
   라벨을 하드코딩해 실은 전부 숫자가 아니었고, 가드를 제거해도 10/10 통과했다.
   **올바른 방법**: 주입이 **초록으로 나오면 그것은 가드가 불필요하다는 증거가 아니라 픽스처가
   틀렸다는 증거**로 먼저 의심하라. 헬퍼/빌더로 만든 픽스처는 결함 축의 값을 **하드코딩하고
   있지 않은지** 확인하고, 필요하면 손으로 쓴다.
3. **함정**: 로그를 「누락 방지」 목적으로 넣을 때 **정상 상태가 곧 경고**인 경로에 WARNING을 걸면
   하루 만에 학습돼 무시되고, 진짜 사건이 다시 보이지 않게 된다.
   **올바른 방법**: 「개별 침묵 + 명명된 총계」에 **첫 목격 1회**를 더한다 — WARNING은 (테이블,
   컬럼) 최초 1회, 반복은 INFO 집계. 그러면 **나중에 뜨는 WARNING은 정의상 새로운 것**이다. 그리고
   이 사이징 자체를 테스트로 고정하라(순진한 "매 파일 경고" 주입이 적색이 되는지).

---
---

# Round 2 — Adversarial review response (`419cd8f`)

**Date:** 2026-08-04 · **Commit:** `419cd8f` on top of `53b30f9` (main, NOT pushed)
**Verdict on the finding: upheld in full.** All four shapes reproduced on the first attempt
before any code changed.

## The finding, restated in my own words

`53b30f9` replaced a **bottom-anchored** grid origin with a **top-anchored** one and the commit
message did not say so. The old derivation collected column-0 integer labels and took
`min_y_row - 1`; `float()` rejection there decided *header-ness*, not the *origin*. My `_ruler_row`
took the first qualifying row scanning **down** — and the top of a spreadsheet is where operator
junk lives. That is a regression class, and the omission from the message is why an adversarial
pass, not the message, is what surfaced it.

Reproduced with an alphabetic lot so the V4 defect is out of play:

| shape | OLD (`53b30f9^`) | `53b30f9` | now (`419cd8f`) |
|---|---|---|---|
| control | 121 / X `1..11` | same | same |
| **M1** `SLOT` row above the ruler | 121 / correct | 121 / X `[2,3,6,7,10,…]` 🔴 | **REFUSED**, named |
| **M2** ragged `DATE\|2026\|6\|20` | 121 / correct | **33 records** 🔴 | **REFUSED**, named |
| **M2-A** blank-corner legend `　\|1\|2` | 121 / correct | **22 records** 🔴 | **REFUSED**, named |
| **M3** padded `DATE` row | 121 / correct | correct **+ phantom `DATE_2026:"6"`** 🔴 | **correct parse, no phantom** |

## Which anchor survives: **both**, and they must agree

Neither survives alone. Their blind spots are at opposite ends of the document and do **not**
overlap:

| derivation | reads | blind spot | shapes that fool it |
|---|---|---|---|
| **TOP** — `_ruler_row`, scanning down | the *shape* of a row | anything ruler-shaped **above** the real ruler | M1, M2, M2-A |
| **BOTTOM** — the Y ruler's topmost label, minus one (pre-`53b30f9`) | where the grid *begins* | any integer in column 0 above the grid | **M4** |

**M4 is new in this round and I added it because injection F exposed a hole in my own suite.**
Restricting the bottom anchor to **unmerged** cells closes the numeric-TITLE and numeric-GROUP
cases (those are merged), which made the hardened bottom anchor survive every test I had written —
so a reviewer could reasonably have asked why the top anchor was still there. M4 (`5 | F | 16` — a
stray 1x1 numeric legend cell in column 0) is the shape it cannot see: bottom anchor says row 5,
top says row 7. `test_the_junk_fixtures_actually_reach_the_cross_check` now asserts the shape set
is **balanced** — at least one fixture must fool each anchor — so this hole cannot silently reopen.

**On disagreement the parse is REFUSED**, not resolved by picking a winner. Picking a winner is the
guess; agreement between two independent derivations is evidence. This is not conservatism for its
own sake: **X and Y are part of the business key** (`composite_key_source: [base, x, y]`), so a
plausible-looking wrong origin files every cell of the map under coordinates that do not exist.
Zero rows with a stated reason is strictly better.

The refusal names both candidates:

```
[matrix] REFUSED to parse: the two derivations disagree - row shape says the ruler is row 6
(ticks ['2','3','6','7','10','11','14','15','18','19','22']), the Y-axis labels say row 7.
Something ruler-shaped sits above the real grid. Returning 0 records rather than a
plausible-looking wrong grid origin, because X and Y are part of the business key.
```

## One measured fact, stated once

Everything positional in this file now leans on `_is_unmerged`: **ruler cells are unmerged, header
cells are merged — 19 files, 0 exceptions either way.** Round 1 used only its first half. Its
second half is new here and is what fixes **M3**: a row that failed the ruler test but still sits
inside the band contributes no header key, because its cells are 1x1. That is what turns the
phantom `DATE_2026: "6"` into nothing at all, without asking what the text looks like.

## Corpus unchanged — the reviewer's stop condition did not trigger

Re-ran the full record-level diff over all 19 archived files **after** the cross-check:
**15 byte-identical, 1 key corrected, 3 phantoms removed, grid cell payload identical on all 19,
and ZERO refusals on real files.** The two derivations agree on every real file. Item 4's stop
condition ("if the cross-check rejects shapes the corpus actually contains, STOP") was checked and
is clear.

## Item 2 — a refused shape no longer looks like a success

Confirmed: zero records raised nothing, so `status` was `SUCCESS` with an empty `error_message`,
and "not one cell was stored" was indistinguishable from "processed normally". The reason now lands
in the **detail slot that already carries the F1 key-skip and the P2 resume note**
(`_compose_detail`), which flows to `file_ingestion_logs.error_message`, the completion log line,
and `on_file_processed_callback`. Same sizing as the drop report, same channel, no second style:

```
파싱 결과 0행 ― 저장된 셀 없음(파서가 형식을 거부했을 수 있음, 워처 로그 확인)
```

U+2015, not U+2014 — the first draft used an em dash and `test_zero_rows_is_named_in_the_detail_slot`
caught it as a cp949 encode failure. The detail slot for a file **with** rows is byte-identical to
before (pinned by `test_rows_present_leaves_the_detail_exactly_as_before`, and
`test_std_parser.py:467` still asserts its exact legacy string).

## Injection matrix — six on the parser, one on the watcher

Each red on a **distinct** subset of the 18 parser tests, so no guard is decorative:

| injection | what it removes | fails |
|---|---|---|
| **A** | HEAD's parser (everything) | **10** |
| **B** | new origin kept, old lexical header predicate restored | 5 |
| **D** | the unmerged-ruler requirement | **1** (`test_a_numeric_header_row_…`) |
| **E** | the cross-check — TOP anchor alone (= what `53b30f9` shipped) | 5 (M1, M2, M2-A, M4, refusal msg) |
| **F** | the cross-check — BOTTOM anchor alone | 5 (same set) |
| **G** | the merged requirement on the header band | **1** (M3) |
| **H** | pre-fix `_compose_detail` | 2 of 10 drop-visibility tests |

**A methodological note that mattered.** Under F, M4 produced zero records *by accident* — the
bottom anchor landed inside the header band, where no cell parses as a tick — so an assertion of
`records == []` passed for the wrong reason. I strengthened every refusal assertion to require a
**named refusal in the log**, not merely zero records. An accidentally-empty parse must not be able
to pass for a deliberate one; that is the same principle as item 2, applied to the tests
themselves.

## Suite

`1992 passed, 2 skipped` (`server/tests/`). The stated baseline of 1958 moved under me — other
lanes landed `ef153c0` (map write-path tests) and `843af4f` during this round. My own two files
account for **28 tests** (18 + 10), up from 17. `server/database/crud.py` is modified in the working
tree by the live crud lane and was **not** staged. Staged paths were the four explicit ones only.

## Still open / not done

- **Not pushed.** `53b30f9` and `419cd8f` both sit on local `main`.
- `docs/` untouched, per the brief. The doc-keeper trigger fired **again** (now 50 commits).
  `guide/HTML_TOPOLOGY_PARSER_GUIDE.md` §3.6 is now stale on two counts — the header predicate
  *and* the grid-origin derivation. `CODE_MAP.md` needs `_is_unmerged`, `_ruler_row`, the
  cross-check, and `_announce_dropped_columns`.
- The `expected_dropped_columns` declaration proposed in round 1 is still unbuilt (lead PM call).

### History draft (round 2)

> **격자 원점을 이중 유도 + 불일치 시 거부로 교체** (`419cd8f`, `53b30f9` 보정)
> `53b30f9`는 격자 원점 유도를 **아래 기준(Y눈금 최상단−1)에서 위 기준(위에서 첫 눈금 모양 행)으로
> 바꿔놓고 커밋 메시지에 적지 않았다.** 스프레드시트 위쪽은 운영자 잡동사니가 사는 자리라 이는
> 회귀 부류였다 — `SLOT` 행 하나로 **레코드 수·값은 맞고 X만 조용히 틀리는** 최악의 형태가 나온다
> (실측 M1). 두 유도는 **서로 반대편에 맹점**이 있어(위 기준=눈금 모양 잡동사니, 아래 기준=0열의
> 1x1 정수) 어느 하나도 단독으로 성립하지 않는다. 그래서 **둘 다 유지하고 일치할 때만 채택**,
> 불일치 시 **후보 행 2개를 이름으로 밝히며 거부**한다(X·Y가 비즈니스 키라 그럴듯한 오답이 0행보다
> 나쁘다). 병합 여부라는 **하나의 실측 사실**(19파일 예외 0)로 눈금·헤더를 모두 가르며, 그 후반부가
> M3 유령 키를 없앤다. 실파일 19건 재대조: 거부 0건, 격자 값 전부 동일. 주입 7종이 각각 다른
> 부분집합을 적색화. 별건으로, 0행 결과가 무자격 SUCCESS로 보이던 것을 기존 detail 슬롯에 사유로
> 실었다.

### Proposed lessons — round 2 additions

4. **함정**: 판정 로직을 고치면서 **그 판정이 딛고 선 기준점의 유도 방식까지 같이 바꿔놓고**
   커밋 메시지에는 판정만 적으면, 검수자가 회귀 부류를 스스로 재발견해야 한다. 이번에 실제로
   발생 — 헤더 판정을 위치 기반으로 바꾸면서 그 「위치」의 원점을 아래 기준→위 기준으로 바꿨고,
   메시지에는 한 줄도 없었다.
   **올바른 방법**: diff에서 **좌표계·기준점·정렬 순서·탐색 방향**이 바뀌었는지 따로 확인하고,
   바뀌었으면 **바뀌었다는 사실 자체를 커밋 메시지의 독립 문단으로** 쓴다. 「무엇을 고쳤나」와
   「무엇을 기준으로 고쳤나」는 다른 질문이다.
5. **함정**: 휴리스틱 두 개 중 하나를 고르면 **고른 쪽의 맹점이 그대로 제품의 맹점**이 된다.
   맹점이 겹치지 않는데도 하나만 남기면, 코퍼스가 한 생산자·한 형상일 때는 아무 문제가 없다가
   형상이 늘어나는 순간 조용히 틀린다.
   **올바른 방법**: 유도가 둘이면 **둘 다 계산해 일치를 요구**하고 불일치는 **거부**한다. 특히
   결과가 **비즈니스 키**에 들어가는 값이면 「그럴듯한 오답」이 「사유가 적힌 0행」보다 훨씬 나쁘다.
   그리고 각 유도의 맹점을 **각각 활성화하는 픽스처를 최소 1개씩** 두고, 그 균형을 테스트가
   스스로 단언하게 하라 — 안 그러면 한쪽을 지워도 스위트가 초록이다(이번에 F 주입이 그걸 드러냈다).
6. **함정**: 거부를 「0건 반환」으로만 검사하면, **우연히 비어버린 파싱**이 의도된 거부로 위장해
   테스트를 통과한다. F 주입에서 M4가 정확히 이 방식으로 통과했다.
   **올바른 방법**: 거부 테스트는 **0건 + 사유가 로그에 명명됨**을 함께 단언한다. 침묵과 거부를
   테스트 자신이 구별하지 못하면, 제품도 구별하지 못하는 것을 잡을 수 없다.
