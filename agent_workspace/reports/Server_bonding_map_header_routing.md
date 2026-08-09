# Server — Bonding Map Header Routing: Feasibility Measurement

**Date:** 2026-08-04 · **Mode:** READ-ONLY measurement (no code changes, no commits)
**Method:** the real `HTMLMatrixTableParser` and the real `AdvancedIngester` were *executed* against real
archived files; the live DB was queried read-only (SELECT / information_schema only).

---

## Q2 — THE DECIDING ANSWER (lead first)

**`header_rules` CANNOT extract the map key. But that does not make this an ingestion redesign — it makes
it a smaller feature than the question assumes, because `HTMLMatrixTableParser` ALREADY extracts the whole
header block, and the map key ALREADY comes from the top header in production today.**

Three separate findings, each measured:

### 2a. `header_rules` is not on this file's code path at all

`header_rules` lives in exactly one class, `AdvancedIngester`
(`C:\Users\kk980\Developments\assyManager\server\parsers\advanced_ingester.py:180`, consumed at `:254`
`extract_header_metadata`). A full grep of `server/` for that class finds **one** construction site in the
entire product, and it is a *user pipeline script for a different table*:

```
server/ingestion_workspace/sensor_metrics/scripts/run_sensor_ingestion.py:20:  ingester = AdvancedIngester(config_path)
```

`directory_watcher.py` never constructs it. The bonding-map path is a pipeline parser
(`server/ingestion_workspace/bonding_map/scripts/bonding_map_parser.py`) that calls
`HTMLMatrixTableParser` directly. So `header_rules` is an opt-in helper a user script may import, not a
stage of the standard ingestion pipeline. Nothing "consumes the document before `header_rules` runs" —
`header_rules` simply is not in the chain.

### 2b. Forced to run anyway, `header_rules` returns the WRONG value, silently

I ran the real `AdvancedIngester` against
`server\ingestion_workspace\bonding_map\archives\user(kk980)_web_smart_paste_1781918516895_2c5a5407.html`
with the most generous header declaration I could write. Result:

```
extract_header_metadata -> {'title': 'AAA', 'base': 'LOT', 'base_v2': 'D'}
```

- `title` = `'AAA'` — correct. So it *can* see the region above the grid; region visibility is not the blocker.
- `base` = `'LOT'` — it captured the **label**, not the value.
- `base_v2` = `'D'` — it captured the **last** matching value in the file. No error, no warning.

The reason is structural, and it is the whole design constraint. The header's key/value relationship is
**2D and spatial**, not linear. In the raw file the label and its value are on different physical lines:

```
line 11: <td colspan="2" rowspan="4" ... >BDIE</td>
line 12: <td colspan="2" rowspan="2" class="xl65">LOT</td>
line 13: <td colspan="2" rowspan="2" class="xl65">A</td>
line 14: <td colspan="2" rowspan="4" class="xl65">CDIE</td>
line 15: <td colspan="2" rowspan="2" class="xl65">LOT</td>      <-- byte-identical to line 12
line 16: <td colspan="2" rowspan="2" class="xl65">C</td>
```

`extract_header_metadata` is **line-scoped**: one regex, one line, `group(1)`, and later lines overwrite
earlier ones (`metadata[rule["column"]] = ...` inside the per-line loop). The identity `BDIE_LOT` exists
only as a *left-ancestor chain across merged cells* — `BDIE` (rowspan 4) is to the left of `LOT`
(rowspan 2) which is to the left of `A`. Lines 12 and 15 are byte-for-byte identical; a line-oriented
regex literally cannot tell BDIE's `LOT` from CDIE's `LOT`. The rule shape is wrong for the data shape,
and no declaration fixes it.

The row half fails too: the same run produced **26 rows from a 121-cell grid**, with no X and no Y at all.
`AdvancedIngester` cannot emit the cells either.

### 2c. What actually happens is better — the header key is ALREADY on every cell row

`HTMLMatrixTableParser.parse_matrix_to_records`
(`C:\Users\kk980\Developments\assyManager\server\parsers\html_topology_parser.py:524`) already does
structurally what `header_rules` cannot do textually. Its step 3 lifts the title (widest top `colspan`),
its step 5 walks the LEFT-ancestor chain to build composite meta keys, and step 6 stamps **title + all
meta** onto every single cell record. Same file, real run:

```
records: 121
record[0]: {"TITLE": "AAA", "BDIE_LOT": "A", "BDIE_WF": "B", "CDIE_LOT": "C", "CDIE_WF": "D",
            "X": 1, "Y": 1, "VALUE": ""}
```

And the pipeline script then does `df.rename(columns={'BDIE_LOT': 'base', 'VALUE': 'leg'})`, while
`table_config.json` declares for `bonding_map`:

```json
"composite_key_source": ["base", "x", "y"],
"map_key_columns": ["base"]
```

**So `base` — the map key, the business key component, the `map_key_columns` value — is a header value
today, in production, in the live database.** Confirmed in the live DB: `map_split_registry` holds
`bonding_map|A|F`, `bonding_map|A|16`, `bonding_map|A|12`, `bonding_map|A|C` — map key `A` is the
`BDIE_LOT` header cell, and `F/16/12/C` are the bin values from the 2D grid underneath it.
`wafer_map_metadata` holds `bonding_map_A`.

**Verdict: the cell-keying half already works. The only missing piece is the second emission. Small feature.**

---

## Q1 — What is actually in the header block

Structure, from the real files (the archive contains genuine Excel HTML clipboard payloads, `<table>` with
`colspan`/`rowspan` merged cells, `class="xl65"`, `mso-*` styles — Excel's clipboard flavour, which is why
`HTMLMatrixTableParser` exists):

| Region | Shape | Content |
|---|---|---|
| Row 1–2 | one `<td colspan="12" rowspan="2">` spanning the full width | **the bonding title** — `"AAA"`, `"asdf"` |
| Rows 3–6 | merged 3-deep chains: `GROUP` (rowspan 4) → `KEY` (rowspan 2) → `VALUE` (rowspan 2) | **the material info** — `BDIE/LOT/A`, `BDIE/WF/B`, `CDIE/LOT/C`, `CDIE/WF/D` |
| Row 7 | `<td>` blank corner + `1..11` (or `1..17`) | X axis ticks |
| Rows 8+ | `1..11` in column 0, then per-coordinate bin cells | the 2D grid |

**Which cell holds the map key:** the `BDIE`→`LOT`→value chain. Its third cell (`"A"`, `"HFZ123.12"`,
`"basdf"`, `"sdfsd"`, `"dgdfg"` across the sampled files) is what becomes `base`. The title
(`TITLE`/`"AAA"`) is **not** the key — it is dropped (see Q3).

**Header shape is not fixed.** I ran the parser over **every** smart-paste HTML in the workspace (19
bonding-map files: 16 in `archives/`, 3 in `err/`), and the emitted meta key set varies file to file:

```
15 x ('BDIE_LOT','BDIE_WF','CDIE_LOT','CDIE_WF','TITLE')
 2 x ('AQ_LOT','AQ_WF','BDIE_LOT','BDIE_WF','CDIE_LOT','CDIE_WF','F_AAA','TITLE')
 1 x ('BDIE_LOT','BDIE_WF','CDIE_LOT','CDIE_WF','F_AAA','TITLE')
 1 x ('BDIE_LOT','BDIE_WF','TITLE')            <-- degenerate, see Q4
```

⚠️ **Scale correction to the brief.** The 3,225 figure is the total file count under
`server/ingestion_workspace/bonding_map/` (all subdirectories). `archives/` holds **3,195** files, of
which **3,179 are `web_bonding_data_*.csv`** (auto-update output, flat `base,x,y,leg`, no header block at
all) and only **16 are smart-paste HTML**. The multi-table header case therefore has a real corpus of
~19 files, not 3,225. This matters for sizing: it is a young format with few live variants, but also few
samples to generalise from — the four shapes above are the entire observed population.

---

## Q3 — What happens today when one of these files is ingested

**It succeeds, and the material info is silently discarded. It is nowhere in the database.**

Live DB, `file_ingestion_logs`: **20 `web_smart_paste*.html` rows for `table_name='bonding_map'`, all
`status='SUCCESS'`, empty `error_message`.** The parse does not break. (For contrast, the three
`inventory_master` smart-paste files are `FAILED` with tracebacks — a different, non-matrix format.)

Where the header goes:

1. `HTMLMatrixTableParser` extracts `TITLE`, `BDIE_LOT`, `BDIE_WF`, `CDIE_LOT`, `CDIE_WF` onto all 121 rows.
2. The pipeline script renames `BDIE_LOT`→`base` and lowercases the rest.
3. `directory_watcher.py:1693` sets `defined_cols = table_info.get("display_columns", [])`, and the
   normalization loop at `:1762` keeps **only** columns matching that list. `bonding_map`'s
   `display_columns` is `["pkg_id","base","x","y","leg"]`.
4. `title`, `bdie_wf`, `cdie_lot`, `cdie_wf` match nothing and are dropped **before `crud` ever sees them**
   — so `crud._warn_undeclared_column_once` (`database/crud.py:78`, which would at least log
   `"...was DROPPED from the update..."`) **never fires**. The loss is not merely unwritten, it is
   unlogged.

Confirmed by query — no table in the database has any of these columns:

```sql
SELECT table_name, column_name FROM information_schema.columns
WHERE column_name IN ('title','bdie_wf','cdie_lot','cdie_wf','bdie_lot','aq_lot','aq_wf');
-- 0 rows
```

Only `base` survived, because it is a declared column and the map key. **`BDIE_WF`, `CDIE_LOT`, `CDIE_WF`
and the bonding title from all 20 successful ingests are gone.** The user's VOC is exactly right: the
information reaches the parser and dies at the schema boundary.

---

## Q4 — Sizing "one file, one parse, two emissions"

### What is already there

- Parse: done. `HTMLMatrixTableParser` returns the header AND the grid from one pass over one file.
- Emission 1 (cells): done. Wired, ingesting, keyed on the header value.
- Emission 2 (header row): **missing.** This is the entire delta.

### The correctness constraint, stated explicitly

> The header emission and the cell emission must produce the SAME business key, or the two land in the
> database without being able to find each other — visibly saved, silently unjoined.

**How key agreement would be guaranteed:** by reusing the mechanism that already guarantees it for
`wafer_map_metadata`, not by recomputing the key. `directory_watcher.py:1784` reads:

```python
meta_collector.collect(it.updates for it in items)
```

That is the **same normalized dict object** that is handed to `crud.apply_batch_updates` on the next lines
— not a copy, not a re-derivation from the file. `MapMetaCollector` then composes the identity through
`map_meta_registrar.compose_map_id(key_columns, row, table_name)`
(`C:\Users\kk980\Developments\assyManager\server\map_meta_registrar.py:132`), which routes through
`map_overlay.canonical_bind_value` so the declared column type governs — the docstring records exactly the
defect this closes ("a raw pre-cast `'01'` in a number-declared key column registers `'LOT_01'` while the
stored cell casts to `1` and every consumer looks up `'LOT_1'`").

**So the design rule for the second emission is: it must read `map_key_columns` off the same row dict via
the same `compose_map_id`, at the same work-unit boundary.** Any implementation that re-parses the file or
re-derives the key from the header block independently reintroduces exactly the divergence the constraint
forbids. This is a reuse, not a new invariant.

`compose_map_id` also already handles the missing-key case correctly: a missing or empty key part returns
`None` and the row is disqualified rather than registered under a guessed partial identity
(`"ingestion must not guess a partial identity it would then register meta for"`). The header emission
should adopt the same rule — **no key, no header row**, and the cells for that file are equally
unidentifiable, so the honest outcome is to refuse the file (the `filename_rules` `required:true` refusal
at `advanced_ingester.py:341` is the existing precedent for "0 rows rather than untrustworthy rows").

### 🔴 The malformed-key case is not hypothetical — it is already in the archive

One archived file (`user(kk980)_web_smart_paste_1781956356720_f7750cf0.html`) has the header
`BDIE / LOT / 12312`. The parser emitted:

```
meta = {"BDIE_LOT": "CDIE", "BDIE_WF": "B", "TITLE": "AAA"}     <-- CDIE_LOT and CDIE_WF vanished entirely
```

The map key silently became the literal string `"CDIE"`. Cause:
`HTMLTableGraphParser._default_is_header` rule 4
(`C:\Users\kk980\Developments\assyManager\server\parsers\html_topology_parser.py:104-113`) classifies any
`float()`-parseable cell as **not** a header, so the numeric lot `12312` drops out of `meta_nodes`, the
LEFT-ancestor chain shifts one cell right, and the next header cell (`CDIE`) is consumed as BDIE_LOT's
value. `HFZ123.12` survives (not float-parseable); a purely numeric lot number does not.

This is a live data-integrity hazard **today**, independent of the new feature — a numeric lot id produces
a wrong map key with no error, and everything downstream (`map_split_registry`, `wafer_map_metadata`,
virtual joins) keys off it. Adding a second emission on the same key does not create the problem, but it
does **double the blast radius**, because the material row would then be filed under `"CDIE"` too. It
should be fixed or explicitly gated before the second emission ships.

### Sizing

Small feature, on three conditions:

1. **A new table, not a widened `bonding_map`.** Composite key `(target_table, map_id)`, mirroring
   `wafer_map_metadata` exactly. Columns carry the header verbatim. A new table is created by
   `create_all`/`create_missing_dynamic_tables` with no migration-ordering dependency; widening an
   existing table needs a migration that must beat every reading process or the web server 500s on
   `UndefinedColumn` (recorded in the server-pm lessons file).
2. **Header shape is variable** (four observed shapes, `AQ_*`/`F_AAA` appearing and disappearing). A fixed
   column list will drop the next variant just as silently as today. Either declare the union and accept
   nulls, or store the header as a declared JSON payload the way `wafer_map_metadata.grid_metadata` does.
   `F_AAA` in two files also looks like a mis-detection of the title cell, not a real material field —
   worth confirming before it becomes a column.
3. **The `_default_is_header` numeric hazard above is closed or explicitly accepted.**

The wiring point is one call at the same work-unit boundary as `MapMetaCollector` in
`directory_watcher.py:1746/1784/flush`. The pipeline script's `process_dataframe` currently flattens the
header into per-row columns that then get dropped — the second emission needs the header as a *distinct
object*, which means the collector must read it off the row dict (where the parser already put it) before
`defined_cols` filtering strips it, or the pipeline contract must carry it separately.

---

## Q5 — Should `map_meta_registrar` be the home?

**Extend the pattern; do not extend the module. Build a sibling collector, not a new mechanism.**

Measured properties of `server/map_meta_registrar.py` (367 lines):

| Property | Verdict for header emission |
|---|---|
| Per-work-unit collector, gated inert at construction (`active=False` unless knob + `map_key_columns` + coordinate binding resolve) — `:208-249` | ✅ exactly the right lifecycle |
| Key composed by `compose_map_id` off the same row dict — `:262` | ✅ **this is the key-agreement guarantee**; reuse it verbatim |
| Absent-only creation with a batched indexed existence check on `business_key_val` (`IN (...)`, `CHUNK_SIZE`) plus a process-lifetime `_known_present` cache — `:309-354` | ⚠️ right for *derived* metadata, **wrong for carried-through material info** |
| Hard-wired to one destination: `META_TABLE = wafer_map_metadata`, with an explicit recursion guard on it — `:219`, `:296`, `:352` | ❌ cannot address a second table |
| Payload is `synthesize_grid_meta(min_x,min_y,max_x,max_y)` — a bbox-derived synthetic frame, `:168-195` | ❌ **synthesises; carries nothing through** |

The last two are decisive. The module's entire payload is *derived from the cells* — which is precisely
the category the user excluded ("셀에서 파생되는 정보가 아님"). It has no channel for a value read out of
the file, and adding one would mean a second destination table, a second payload builder, and a second
write semantics inside a class whose recursion guard, knob, and cache are all scoped to one table.

**Board item M2 is the direct evidence that its write semantics are wrong for this job.** `synthesize_grid_meta`
uses the batch bbox as the grid start, and absent-only + `_known_present` means a map split across two files
gets the **first file's bbox permanently frozen** — the second file is never even looked at. Applied to
material info that would read: the first file's material values win forever, and a corrected re-upload of
the same bonding map would be silently ignored. For *derived* metadata that is a defensible conservatism
(never overwrite a user's declaration). For *carried-through* header values it is a data-loss default:
a header the user just corrected in Excel would not land.

**Recommendation:** a new sibling module (`bonding_header_registrar` or similar) that:
- reuses `map_meta_registrar.compose_map_id` **by import**, so the two emissions cannot diverge on key
  composition (this is the whole correctness constraint, and it becomes a compile-time fact rather than a
  convention);
- copies the collector lifecycle (construct at the file boundary, inert unless gated, one batched write at
  flush);
- but writes a **new** table with **upsert** semantics rather than absent-only, because the header is the
  file's own assertion and a re-upload is a correction, not a duplicate — consistent with the 2026-07-30
  「파일이 정본」 ruling already encoded in `advanced_ingester._merge_row:364`.

Bypass `map_meta_registrar` for the payload; reuse it for the key.

---

## Boundary-contract impact

None of the below is proposed here — flagged for 총괄 because the feature would touch them:

- **New table** ⇒ `table_config.json` ⇒ `GET /tables/{t}/schema` response — schema contract, needs
  Client PM coordination.
- Cell shape `{value, is_overwrite, priority_source}` and the WS batch events are **unaffected** — the
  second emission is an ordinary row write through `crud.apply_batch_updates`, same as
  `MapMetaCollector.flush` does today, and its outbox events already flow.

## Proposed lessons (for 총괄 review — not added directly)

1. **함정**: 「이 선언 기능이 X를 뽑을 수 있나」를 코드만 읽고 판정하면 *영역이 보이는지*와 *값을 맞게
   뽑는지*를 혼동한다. `header_rules`는 헤더 영역을 실제로 봤고(`title='AAA'` 성공) 그래서 코드 독해로는
   "가능"으로 보이지만, 실행하면 라벨(`'LOT'`)과 마지막 매치(`'D'`)를 **경고 없이** 돌려준다.
   **올바른 방법**: 선언 기능의 가부는 실물 파일에 먹여 **뽑힌 값을 눈으로 대조**해 판정한다. 빈 결과가
   아니라 **틀린 값**이 나오는 것이 이 계열의 전형적 실패 모드다.
2. **함정**: 아카이브 파일 수를 디렉터리 총계로 세면 포맷별 실제 코퍼스를 수십 배 과대평가한다
   (`bonding_map/` 3,225건 중 스마트페이스트 HTML은 16건, 나머지는 `web_bonding_data_*.csv`).
   **올바른 방법**: 착수 전 `ls | sed 's/.*\.//' | sort | uniq -c`로 확장자 분포부터 세고, 대상 포맷의
   실건수를 보고서에 명시한다. (기존 「규모는 재고, 존재만 커밋을 믿는다」의 파일 코퍼스 판.)
3. **함정**: `display_columns`에 없는 컬럼은 `directory_watcher.py:1762`에서 `crud` **이전에** 걸러지므로
   `crud._warn_undeclared_column_once`의 "DROPPED" 경고가 **한 줄도 안 남는다** — 로그를 근거로
   "누락 없음"을 판정하면 틀린다.
   **올바른 방법**: 컬럼 유실 여부는 로그가 아니라 `information_schema.columns` 실측으로 확인한다.
