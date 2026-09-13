# M2.6 — DOE consolidation: three tables into one

**Agent:** map-pm · **Date:** 2026-07-27 · **Environment:** isolated (`devenv up`, `:8081`, `assy_qa`). No live write.

---

## 1. What shipped

`map_doe` and `map_doe_source` have no writer any more. **One value = one `map_split_registry` row = one DOE.**

| Before | After |
|---|---|
| 3 tables, 2 writer modules, 2 debounces, 2 guard sets | 1 table, 1 writer module, 1 debounce, 1 guard set |
| `stack_band` free-text label, parsed by nobody | `bands[].to` integer cut point, `from`/layers derived |
| `qty_total` typed by the user (painted x layers, in their head) | derived: painted cells x layer count |
| `map_doe_source.qty` stored | derived: `ceil(band total / material count)` |
| `source_lot` + `source_slot` two fields | one raw ID string, as typed |
| knobs per band | knobs per value |
| later save silently erased another session's values | later save re-reads and refuses |

### Files changed (mine only)

- `C:\Users\kk980\Developments\assyManager\client2\src\map_editor.js` — DOE model, registry read/write, all three guards, local caches
- `C:\Users\kk980\Developments\assyManager\client2\src\transfer_plan.js` — DOE panel; now **pure UI**, zero persistence code
- `C:\Users\kk980\Developments\assyManager\client2\src\transfer_plan.css` — band card layout (`.tp-band-l1`, `.tp-band-range`, `.tp-band-calc`)
- `C:\Users\kk980\Developments\assyManager\server\product_tables.py` — `map_split_registry` gains `knobs` + `bands`; `map_doe`/`map_doe_source` marked DEPRECATED (declaration kept, nothing dropped)
- `C:\Users\kk980\Developments\assyManager\server\config\table_config.json.sample` — regenerated artifact (`install_product_tables.py --sample --apply --overwrite-drift`)
- `C:\Users\kk980\Developments\assyManager\server\tests\test_install_product_tables.py` — `WRITERS` retargeted (see §7)
- `client2/dist/**` — `npm run build`

`client2/map_editor.html` unchanged.

---

## 2. The `bands` JSON contract (for the server availability calculation)

**Column:** `map_split_registry.bands`, declared `string`, holds JSON **text**. Never NULL from the client; an empty plan is `"[]"`.

```json
[
  {"seq": 2, "to": 15, "materials": ["TAPE-B_02"]},
  {"seq": 1, "to": 20, "materials": ["TAPE-A_01", "TAPE-D_04"]}
]
```

### Field by field

| Field | Type | Rule |
|---|---|---|
| `seq` | int >= 1 | **Identity.** Materials belong to it. Unique within the array. **Never renumbered** — not on reorder, not on delete. Not an index, not an order. |
| `to` | int >= 1, or `null` | The last layer of this band. `null` = the user has not set it yet: that band contributes 0 layers and no requirement, and it always sorts **last**. |
| `materials` | array of string | The raw ID string exactly as typed. Deduplicated by the client. May be empty. |

### Derivation — the whole model is these three lines

Let `B` be the array **in stored order**, `to(-1) = 0`:

```
from(i)   = to(i-1) + 1                  # first band starts at layer 1
layers(i) = to(i) - to(i-1)              # subtraction, no parsing
total(i)  = painted_cells(value) * layers(i)
share(i)  = ceil(total(i) / len(materials(i)))     # 0 when materials is empty
```

`painted_cells(value)` = rows in the map table (`ref_table`) with `map_key` and cell value == `value`.

### Rules a consumer must not break

1. **Order is array position, not `seq`.** In the example above the stack is seq2 (1-15) then seq1 (16-20). Sorting by `seq` gives 20 then 15 and `layers` goes negative. In the fixture below, deriving by `seq` instead of position changes **3 of 3** layer counts.
2. **`to` is a cut point, not a layer count.** `layers(i) = to(i)` (forgetting the subtraction) changes **2 of 3** totals in the fixture.
3. **`ceil`, not round or floor.** 43 cells / 3 materials -> 15, not 14. Rounding down hides a shortage.
4. **Nothing derived is stored.** Do not write `total` or `share` back. A stored total drifts the moment someone paints one more cell — that is the original complaint this change removes.
5. **Do not parse `materials`.** The string is the key. `lot`/`slot` parsing is a later, separate concern and must not be able to move the key.
6. `null` `to` and empty `materials` are normal states, not errors.

### `knobs` (sibling column, flat on purpose)

`map_split_registry.knobs` = JSON **object** of string->string, e.g. `{"bond_temp":"260C"}`. Empty is `"{}"`. It is a **value-level** attribute (not per band) and stays a flat column, next to `split_desc`, because those two are what the ontology/LLM consumes — nesting them inside `bands` would bury the ontology's input in a blob.

---

## 3. Concurrency — one read added to the write path

`replace_map` purges the whole `(ref_table, map_key)` scope, so with 2-5 people on a plan the later save erases the other's additions silently.

`saveLegendToServer` now runs **one** GET before the PUT and compares a content fingerprint against the baseline it recorded when it last saw the server:

```
read scope
  |- read failed / truncated .............. BLOCK (no write at all)
  |- no authority + server has rows ....... ADOPT server copy, skip this write cycle
  |- no authority + server empty .......... grant authority, proceed
  |- fingerprint != baseline .............. REFUSE, set conflict, tell the user to reload
  '- fingerprint == baseline .............. PUT replace_map:true, baseline = payload
```

Authority and baseline are **one object** (`legendReplaceScope = {table, mapKey, fingerprint}`) because they are one claim: "the screen came from this map's rows, and they looked like this". Anything that voids one voids the other.

The fingerprint runs both sides through **one** normal form (`canonRegistryRow`) — the rows read back and the payload about to be sent. Two implementations of "the same row" would either miss a real conflict or invent a false one. It found a real false-positive during verification (see §6).

A conflict **blocks the write entirely** rather than degrading to an upsert. Degrading would push our stale `bands` over theirs — the row now carries the plan, so the old "upsert-only fallback" is no longer the safe option it was when the row held only desc/colour. This is a deliberate tightening: a legend desc edit made while the registry read is failing is now **not sent**, where before it was upserted.

---

## 4. Complexity budget

**Net: controls removed > controls added. Zero new panels, modes or modals.**

Measured on the live page, one value expanded, shape = 2 bands / 3 materials / 1 knob:

| | Before | After |
|---|---|---|
| Value level | value, colour, desc, delete, `+ 구간` = **5** | same + `+ knob` + 3 knob fields = **9** |
| Per band | STACK text, 총 소요 number, delete, N x mat-delete, `＋ 자재`, mat input, 추가, `+ knob`, 3 x knob fields | 끝 층 number, delete, N x mat-delete, `＋ 자재`, mat input, 추가 |
| **Total (2 bands, 3 mats, 1 knob)** | **28** | **22** (−6, −21%) |
| **Total (3 bands, 5 mats, 1 knob)** | **40** | **29** (−11, −27%) |

What went away:
- **`STACK 구간` free-text input** and **`총 소요` number input** per band, replaced by **one** `끝 층` number input.
- **knob editor per band** -> once per value. With B bands the old model needed the same knob typed B times; the saving grows with B.
- header state **"삭제 미반영"** — structurally unreachable now (a legend always has >= 1 row, so the empty-set-can't-be-expressed case cannot arise).
- the "쉼표로 여러 구간(`1, 2-15, 16`)" explanation paragraph — the concept is gone.

What is new and visible: two **read-only** derived lines per band — the range/`14층` chip and `칠함 43 × 14층 = 소요 602 · 자재 3매 → 매당 201`. These are text, not controls, and they are the point: the multiplication the user was doing in their head is now printed.

**Read path friction: unchanged at zero.** Opening a map = 3 GETs, no dialog. The only confirmation in the panel is deleting a value (a write) — 1 confirm, as before.

---

## 5. Verification

Fixture: `bonding_map` / `AAA` in the isolated snapshot. **F = 43 painted cells** (verified by SQL), 3 bands `to = 1 / 15 / 16` — the user's own `1, 2-15, 16` example. Deliberately chosen so the defect axes are live:

| Axis | Is it activated? |
|---|---|
| subtraction (`layers = to - prevTo`) | yes — layers `[1,14,1]`; the naive `layers = to` gives `[1,15,16]`, **2 of 3 differ** |
| position vs `seq` | yes — after the reorder test, stored order is `[seq2, seq3, seq1]`; deriving by `seq` gives layers `[20,-5,1]` vs correct `[15,1,4]`, **3 of 3 differ** |
| `ceil` vs round/floor | yes — 43/3 = 14.33 -> **15** (round/floor both give 14); 172/3 = 57.33 -> **58** (both give 57) |

A fixture with `to = [1,2,3]` or a material count dividing the total would have masked all three.

### Request lists (method, path, `replace_map`, row count)

| # | Scenario | Requests | DB result |
|---|---|---|---|
| V0 | Open map | `GET /tables/bonding_map/data`, `GET /tables/wafer_map_metadata/data`, `GET /tables/map_split_registry/data` | read-only, no dialog |
| V1 | Set 3 `to` + add 5 materials | 6 x `PUT /tables/map_split_registry/data/updates replace_map=true rows=2` (debounce-coalesced) | `seq=1 to=1 [TAPE-A_01,TAPE-C_03,TAPE-D_04]`, `seq=2 to=15 [TAPE-B_02]`, `seq=3 to=16 [TOP]` |
| V2 | Add value-level knob | 1 x `PUT ... replace_map=true rows=2` | `knobs={"bond_temp":"260C"}` |
| V3 | **Reorder**: seq1 `to` 1 -> 20 | 1 x `PUT ... rows=2` | order `[seq2, seq3, seq1]`; **materials stayed with their seq** |
| V4 | **Delete middle band** (seq3) | 1 x `PUT ... rows=2` | seq3 gone; seq1 shifted 17-20 -> 16-20; seq numbers **not** renumbered |
| V5 | Delete a material (TAPE-C_03) | 1 x `PUT ... rows=2` | `seq=1 ... ['TAPE-A_01','TAPE-D_04']` |
| V6 | Delete a value (`2`) | 1 x `PUT ... replace_map=true rows=1` | row `bonding_map\|AAA\|2` **gone from the table** |
| V7 | **Concurrency refusal** | 1 x `GET ...`, **0 PUT** | second session's value `Z` intact; chip `⚠ 다른 사람이 변경함 · 다시 불러오기`; user's edit kept on screen |
| V7b | Further edits while in conflict | **0 GET, 0 PUT** (sticky until reload) | unchanged |
| V8 | **Truncation guard** (1 injection, `total = n+7`) | 1 x `GET ... [INJECTED:truncate]`, **0 PUT** | chip `⚠ 서버 상태 미확인 · 저장 보류` |
| V8b | Next edit, no injection | 1 GET + 1 PUT | saved — the block is one-shot, not a lockout |
| V9 | **C1 guard**: 1 injected failure on the load read, then edit | load: `GET [INJECTED:error]`; edit: 1 x `GET`, **0 PUT** | server copy adopted, screen put back on server state, toast says the edit was not written |
| V11 | Reload after conflict | 3 GETs | conflict cleared, authority + baseline re-established |
| V12 | `to` validation: duplicate, and `to=0` | **0 PUT** each | model unchanged, toasts `끝 층 11은(는) 앞 구간의 끝 층 11보다 커야 합니다.` / `끝 층은 1 이상이어야 합니다.` |
| V13 | Push (map + plan companion) | `PUT wafer_map_metadata rows=1`, `PUT bonding_map replace_map=true rows=67`, `GET map_split_registry`, `PUT map_split_registry replace_map=true rows=2` | 67 = 43 + 24, matches the table |

**Injection counting.** Each guard test injected **exactly one** failure (`__INJECTED` counted, remaining budget asserted 0) and was followed by an un-injected repeat that had to succeed. Without that second step the "block" branch and the "recover" branch are indistinguishable — the recorded lesson from the last cycle.

### Negative control (the only self-check worth trusting)

With the plan holding `F` (ours) and `Z` (a second session's), I issued **the exact PUT the client would have sent with the concurrency guard removed** — `rows=1` (`F` only), `replace_map=true`:

```
DB before:  value='F' ... , value='Z' desc='added by SECOND SESSION' bands=[{seq:1,to:9,materials:['OTHER_99']}]
DB after :  value='F' ...
```

`Z` was destroyed. The refusal in V7 is load-bearing, not decorative.

### Suite

`574 passed, 0 failed` (`pytest server/tests -q`, 88.9s). `test_install_product_tables.py` 37 passed.

### Live-DB non-interference (read-only proof)

All client traffic went to `window.location.origin` = `127.0.0.1:8081` (`config.js` derives `API_BASE` from it), i.e. `assy_qa`.

```
live assy_manager, read-only session:
  map_split_registry  102 rows  max(updated_at) = 2026-07-27 05:56:51   (session started ~07:00)
  map_doe               9 rows  max(updated_at) = 2026-07-27 05:57:09
  map_doe_source        8 rows  max(updated_at) = 2026-07-26 23:38:36
  live map_split_registry columns: ... split_desc, color, eventtime      (no knobs/bands -> no DDL ran there)
```

---

## 6. Two real defects found while verifying (both fixed)

**(a) `updated_by` cannot be written — the target schema's column is impossible.**
`crud.py:566` lists `updated_by` in `system_cols` and `crud.py:598/602` skip it in the column loop. A declared `map_split_registry.updated_by` would sit NULL forever. Empirical confirmation: **every** `map_doe` (3) and `map_doe_source` (5) row in the snapshot has `updated_by = NULL` — the column has been dead since it was declared, silently.

Deviation from the stated target schema: **`updated_by` is not declared and not sent.** The "who" is already carried per cell by `cell_sources` / `cell_overwrites.updated_by`, which is exactly what the editor's legend meta line already displays (`kk980 · 2026-07-27 07:28`). Reason recorded in the `__comment`.

This surfaced as a **false conflict**: the payload fingerprint contained `updated_by='web_client'`, the read-back contained the platform's per-cell value, so every second save refused. Removing the field fixed it, and V1 then produced six consecutive successful saves.

**(b) `getLocalTimeString()` does not zero-pad the hour** (`client2/src/utils.js:7`), so before 10:00 it emits `2026-07-27 7:43:54`. Slicing the time at a fixed offset printed `7:43:` in the header chip. Fixed in my file by splitting on the separator (`hhmm()`), with the reason in a comment. **The underlying helper is client-pm's** and is written into `eventtime` audit columns on several product tables, where string ordering breaks across 9->10 — flagged as a separate task, not touched here.

An environment artifact also cost time and is worth recording: an **orphaned isolated API process** kept `:8081` after `devenv down` (devenv reported `api dead` while `netstat` showed a listener). Its ORM model predated the new columns while its config watcher had picked up the new config, so `GET .../data` returned `bands: null` for rows the database demonstrably held. Symptom looked exactly like a serialization bug. **Check `netstat -ano | grep LISTENING | grep :8081` against `devenv status` before trusting an isolated-environment reading.**

---

## 7. Boundary crossings — please review

1. **`server/tests/test_install_product_tables.py`** — `TestProductWritePathsAreDeclared.WRITERS` named `transfer_plan.js` as the writer of `map_doe`/`map_doe_source`. Those payloads no longer exist, so the test's own `assert payloads` would fail. Its docstring says *"If the write path moved, retarget this test — do not delete it"*, so I retargeted: the two retired entries are removed with a comment, `map_split_registry -> map_editor.js / split_key` now covers every DOE column the product writes. No overlap with the concurrent agent's supervision/logger/watcher work.
2. **`server/config/table_config.json.sample`** — a generated artifact of `product_tables.py`; `test_sample_product_section_equals_the_module` compares full entries including `__comment`, so *any* edit to the module requires regenerating it. Produced with the official command, not by hand.
3. Backups the installer left behind (gitignored, not deleted): `server/config/table_config.json.sample.bak.*`, `dev_env/config/table_config.json.bak.*`.

---

## 8. Operator steps still owed (not done — need approval)

1. **Live config**: `conda run -n assy_manager python server/scripts/install_product_tables.py --apply --overwrite-drift`, then restart the web server so `sync_dynamic_tables_schema` issues `ALTER TABLE map_split_registry ADD COLUMN knobs/bands`. Verify against `information_schema.columns`, **not** `GET /tables/{t}/schema` (that reads the config singleton).
2. **Hand-move the data** — 6 `map_doe` rows + 8 `map_doe_source` rows into `map_split_registry.bands`. No migration code was written, as instructed. Note the label->cut-point translation: `1, 2-15, 16` becomes three bands with `to = 1, 15, 16`.
3. **`DROP TABLE map_doe, map_doe_source`** — waits on approval. Declarations stay in `product_tables.py` (marked DEPRECATED) until then so the rows remain readable.
4. **Dispatch the server side**: `server/transfer_plan.py` still binds `plan_store.doe` / `plan_store.doe_source` (`transfer_plan.py:1163,1203`) to the retired tables, so `/api/transfer-plan/validate` reads an empty plan. The availability calculation needs the §2 contract. `server/scripts/setup_transfer_plan_indexes.py` still indexes the old tables.

---

## 9. Proposed lessons for `agent_workspace/memory/map-pm.md`

Proposals only — for the lead PM to accept or drop.

1. **함정**: 격리 환경의 응답을 그대로 믿었다. `devenv status`가 `api dead`인데 `:8081`을 **고아 프로세스**가 잡고 있었고, 그 프로세스의 ORM 모델은 새 컬럼을 모르는 채 config만 핫리로드돼 있었다 — DB에 값이 있는데 API가 `null`을 주는, 직렬화 버그와 구별되지 않는 증상이 나왔다.
   **올바른 방법**: 격리 환경에서 이상한 값을 보면 코드를 의심하기 전에 `netstat -ano | grep LISTENING | grep :8081`의 PID와 `devenv status`의 PID가 **같은지** 확인한다.

2. **함정**: 새 컬럼을 선언했는데 플랫폼이 **구조적으로 못 쓰는 이름**이었다. `crud.py`의 `system_cols`에 `updated_by`가 있어 컬럼 루프에서 건너뛴다 — `map_doe`·`map_doe_source`의 `updated_by`는 선언된 날부터 전 행 NULL이었고 아무도 몰랐다.
   **올바른 방법**: 제품 소유 테이블에 컬럼을 더하면 **한 번 저장한 뒤 그 컬럼을 SQL로 조회**해 실제로 값이 들어갔는지 확인한다. "200이 떴다"는 증거가 아니다(미선언 컬럼 조용한 드롭의 거울상).

3. **함정**: 동시성/일치 검사를 만들면서 "보낸 것"과 "읽어올 것"의 정규화를 다른 코드로 했다. 정규형이 둘이면 없는 충돌을 만들어내고(실제로 매 두 번째 저장이 거부됐다), 그 거부는 진짜 충돌과 구별되지 않는다.
   **올바른 방법**: 지문(fingerprint)은 **한 함수**를 양쪽에 통과시켜 만든다. 그리고 **연속 저장 2회가 거부되지 않는지**를 반드시 회귀 항목으로 넣는다 — 이 케이스가 없으면 거짓 양성이 조용히 산다.

4. **함정**: 같은 행을 두 모듈이 쓰면 `replace_map`이 서로의 컬럼을 지운다. 테이블을 합칠 때 가장 먼저 결정할 것은 스키마가 아니라 **기록자가 누구 하나인가**다.
   **올바른 방법**: 합친 뒤 기록자는 하나로 두고, 나머지 모듈은 관문 함수(`updateLegendRow`)로만 변조하게 한다. 그러면 가드(권한·절단·동시성)도 한 벌만 있으면 된다.
