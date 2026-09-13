# Map 1-a — the valid-die map is pinned to `valid_die_ref`, and APPLY is split from SAVE

**Commits** `6420ad0` (the feature) and `510a748` (the module-state ceiling, unrelated, separate on purpose).
**Gates** 24 harnesses / 20 gated green / 4 known-red / exit 0; contracts 6/6. Both re-run after the final edit.
**Not pushed. `client2/dist` untouched. No `npm run build`. No `docs/` edit.**

---

## 1. The orphan count: **8**, and none of them is orphaned

The instruction was to find out what happens to valid-die maps already stored elsewhere *before*
removing the chooser. Measured against the live database (read-only, `GET /tables/wafer_map_metadata/data`,
668 rows):

| home table  | map            | stored `valid_die_ref` | resolves to             |
|-------------|----------------|------------------------|-------------------------|
| bonding_map | `DTWWER`       | `{"table":"bonding_map","map_id":"BASE_4E"}` | bonding_map · BASE_4E |
| dt_map      | `MID_01`       | `"4MAIN_DT"`           | dt_map · 4MAIN_DT       |
| bonding_map | `DT_F`         | `"DT"`                 | bonding_map · DT        |
| bonding_map | `DT_F2`        | `"DT_TEST"`            | bonding_map · DT_TEST   |
| bonding_map | `4E_E1`        | `"4E"`                 | bonding_map · 4E        |
| bonding_map | `A2`           | `"DT_TEST"`            | bonding_map · DT_TEST   |
| bonding_map | `BASE_SHIFT2`  | `"BASE_SHIFT"`         | bonding_map · BASE_SHIFT|
| bonding_map | `M1`           | `"V1"`                 | bonding_map · V1        |

**Zero of the 8 point at `valid_die_ref`.** Seven are bare strings, whose meaning under
`parseValidDieRef` is "a map in MY table".

Meanwhile `valid_die_ref` itself is already real and populated: **2631 rows across 4 map keys**
(`CORE_1X` 854, `TEST_TEST` 425, `5N_BASE` 425, `CORE_YINV` 296), and **all four are registered in
`wafer_map_metadata`** — so they are referenceable today.

### What removing the chooser would have done, and what was done instead

The obvious implementation of "the table is fixed" is *always write `valid_die_ref`*, and reading a
bare string as a `valid_die_ref` key. Either half silently repoints all 8. `bonding_map` and
`valid_die_ref` both carry maps, so a repointed declaration can land on a real map nobody declared,
and the chip would still read healthy. That is the class of defect this domain exists to prevent.

So the split is:

* **`parseValidDieRef` is unchanged.** It is the *storage format's* meaning, both sides of the seam
  run it (`contracts/map_seam` role `parse_valid_die_ref`), and changing it would repoint the same
  8 rows **on the server too**.
* **Only authoring is pinned.** `validDieRefFromControls` now decides the table with one question —
  *did the user change the key?*

  ```js
  const table = (key === shown.key) ? shown.table : VALID_DIE_TABLE;
  ```

  Untouched key → whatever the stored declaration names (so `keep` fires and the raw is written back
  verbatim). Changed key → an explicit `{table: 'valid_die_ref', map_id: key}`. The bare-string
  (inherit-my-table) form is never emitted by this UI again.

**Nothing is orphaned and nothing is stranded.** The 8 keep working exactly as they do today; the
moment a user picks a different key for one of them it becomes a `valid_die_ref` reference. No
migration is required. If the Lead PM *wants* the 8 migrated, that is a separate, deliberate data
change — it must not be a side effect of a UI edit, which is precisely what this design refuses.

---

## 2. What APPLY did before and after

**Before:** the key input's `change` event (blur/Enter) called `onValidDieRefChanged`. Choosing a
value *was* applying it.

**After:** the 🎯 APPLY button calls `onValidDieRefChanged`. **The function body is unchanged.**

The contract is preserved because it lives one level down, in `resolveValidDie`, which this change
does not touch:

* **Board rule 1** — "loading a valid-die area swaps the existing map geometry metadata for the valid
  die's" — is `set(..., physPreset)` → `applyPresetObject` (six physical values from the reference)
  → `applyPhysicalGeometry` **derives** cols/rows from that spec → `fitGridToMask` widens only if the
  mask does not fit. The reference's *declared* dimensions are still never copied.
* **Board rule 4** — "changing the valid area must NOT change stored cell coordinates" — is
  `reseatCellsToStoredCoords` in the same call, plus the untouched `grid_start_x/y`.

Measured live in the browser (canvas table `dt_log`, key `CORE_1X`):

| | before APPLY | after APPLY |
|---|---|---|
| grid | 10 × 10 | **45 × 39** (derived) |
| chip mm | 2.5 × 2.5 | **7 × 8** |
| offset mm | 0.0, 0.0 | **5, 5** |
| **START X/Y** | **1, 1** | **1, 1 — unchanged** |
| chip | (none) | `🎯 유효 다이: valid_die_ref · CORE_1X (854)` |
| non-GET requests | — | **0** |

Requests APPLY made: `/tables/valid_die_ref/schema`, `/api/maps/paint-rules?table=valid_die_ref`,
`/tables/wafer_map_metadata/data?…target_table=valid_die_ref`, `/tables/dt_log/schema`,
`/tables/valid_die_ref/data?…product=CORE&type=1X`. It resolved against `valid_die_ref`, not the
canvas table, and decomposed `CORE_1X` into the declared key pair.

And the half that was gained: **choosing a key now costs 0 requests and moves nothing.** Measured —
typing `CORE_1X` and firing `change` produced 0 requests and a byte-identical geometry object.

### SAVE — what it is

💾 SAVE is a read-modify-write of **one field of one `wafer_map_metadata` row**. It never writes a
cell and it never applies anything.

* Refuses with no `loadedIdentity` (verified: toast, 0 confirms, 0 writes).
* Reads the stored spec with `fetchGridMetaFor`, which already distinguishes *no declaration* (null)
  from *could not confirm* (throws). **Both refuse.** Writing a designation onto an unread `{}`
  would erase the whole grid spec in one click.
* **What** to write is `validDieRefForPush()`; **how** is `applyValidDieRef()` — the same two
  contract-scored functions ⚡ Push uses. No second writer.
* Exactly one confirmation, and it names the row and promises what it will not touch.
* On success `validDie.raw` is synced, so a second SAVE is a no-op and a following ⚡ Push does not
  re-write the same change as a fresh user edit.

Verified with a `fetch` shim (writes intercepted, never forwarded). The captured PUT:

```
PUT /tables/wafer_map_metadata/data/updates
business_key_val: bonding_map_4E_E1
grid_metadata: {"grid_cols":29,"grid_rows":25,"grid_start_x":0,"grid_start_y":0,
                "grid_y_invert":false,"rotation":0,"side":"front","phys_wafer_dia":300,
                "phys_chip_x":11,"phys_chip_y":13,"phys_offset_x":0,"phys_offset_y":0,
                "phys_edge_margin":3,
                "valid_die_ref":{"table":"valid_die_ref","map_id":"CORE_1X"}}
```

Every other field byte-identical to what was stored; only `valid_die_ref` moved (from `"4E"`).
One request. Zero cell writes.

Sequence observed on the real legacy map `bonding_map · 4E_E1`:

1. loaded → key box shows `4E`, resolution goes to **bonding_map**, not `valid_die_ref`
2. SAVE untouched → `저장할 변경이 없습니다`, **0 confirms, 0 writes**
3. re-key → **1** confirm; declining writes nothing
4. accepting → 1 PUT; the chip does **not** change (stored ≠ applied — the requested separation)
5. SAVE again → no-op

**No live DB write happened.** All 668 `wafer_map_metadata` rows re-read afterwards: **0 rows changed**;
`4E_E1` still holds `"4E"`.

---

## 3. The dropdown (item 4)

`populateValidDieRefList` now queries `VALID_DIE_TABLE` unconditionally instead of reading a control.
**No second mechanism** — it still calls `populateMapKeyDatalist`, so `complete` / `truncated` /
`unavailable` stay distinguished and `unavailable_reason` is still never flattened into an empty list.
The datalist remains a *suggestion*: a key not in the list still types and still resolves (asserted by
`[1-a] ...but re-keying a legacy declaration moves it to the fixed table`, whose key is not required
to be listed).

Live: focus produced exactly one request filtered on `target_table = valid_die_ref` and the four real
keys `TEST_TEST, 5N_BASE, CORE_1X, CORE_YINV`.

---

## 4. Complexity budget

| | |
|---|---|
| removed | `<select id="valid-die-ref-table">` (a control **and** its 7-entry option list) | −1 |
| added | `🎯 APPLY` | +1 |
| added | `💾 SAVE` | +1 |
| **net** | | **+1** |

New panels: 0. New modes: 0. New modals: 0. Confirmation dialogs on the read path: 0 (APPLY asks
nothing). Confirmations on the write path: exactly 1. Both buttons sit in the label row of the block
that already exists, in the same shape as the `⚙️ Geometry Presets` buttons directly above — same
mechanism, not a new one.

A real reduction beyond the count: the block dropped from two stacked controls to one, and the
comment explaining why the select had to be on its own line (it truncated at 105px) went with it.

---

## 5. Item 2 — the system-table promotion, and the `server/` touch

**The mechanism is `server/product_tables.py`.** Its own header calls itself "the single definition",
and `server/config/table_config.json.sample`'s product section is *generated* from it by
`install_product_tables.py`, with `server/tests/test_install_product_tables.py` asserting the two agree.
There is no second notion of "system table" — I looked: no admin delete-table UI exists, and no
`SYSTEM_TABLES` list exists anywhere in `server/` or `client2/`.

⚠️ **One premise in the brief does not hold.** `PRODUCT_TABLES` contains
`wafer_map_metadata`, `map_split_registry`, `map_doe`, `map_doe_source` — **`bonding_map` is not
product-owned.** It is a site table that happens to hold maps. So "the same mechanism as
bonding_map/wafer_map_metadata/map_split_registry" is really "the same mechanism as the latter two".
Worth a board correction.

**I did touch `server/`, and here is the accounting**, because the brief permitted it only if the
promotion genuinely required a config `.sample`:

* `server/product_tables.py` — one dict entry (+ a `__comment` in the product-owned house style).
* `server/config/table_config.json.sample` — **generated**, not hand-edited
  (`install_product_tables.py --sample --apply`). Editing only the sample would have failed the
  agreement test; editing only the module would have left the shipped template short. They move together.
* `server/config/table_config.json` (the live site config) — **not touched**. It already declared
  `valid_die_ref` and the dry run reports `matches the product definition (comment differs —
  annotation only, ignored)`: **0 drift, 0 blocking, nothing to write.**
* Tests: `test_install_product_tables.py` 39 passed, `test_config_backup.py` 28 passed.
* Collision check: the two live server lanes are in `chain_ingestion_worker.py`,
  `process_supervisor.py`, `internal_event_client.py`, `event_constants.py`, `run_watcher.py`.
  **No overlap.**

---

## 6. Per-cell mask evidence (the M4 blind spot)

Board M4 says "stored coordinates: 0 cells moved" does not catch a mask on the wrong dies. So nothing
below is a count of moved cells.

### 6a. Designation — key → key, OLD (HEAD) vs NEW, on all 8 live declarations

Both source versions sliced into a vm, driven through the real path
(`syncValidDieRefControls` → `validDieRefForPush` → `validDieRefPayload` → `parseValidDieRef`):

```
UNTOUCHED SAVE — declarations whose resolved map CHANGED: 0 of 8
  bonding_map::DTWWER      OLD/NEW  bonding_map :: BASE_4E    stored object identical
  dt_map::MID_01           OLD/NEW  dt_map :: 4MAIN_DT        stored "4MAIN_DT" identical
  bonding_map::DT_F        OLD/NEW  bonding_map :: DT
  bonding_map::DT_F2       OLD/NEW  bonding_map :: DT_TEST
  bonding_map::4E_E1       OLD/NEW  bonding_map :: 4E
  bonding_map::A2          OLD/NEW  bonding_map :: DT_TEST
  bonding_map::BASE_SHIFT2 OLD/NEW  bonding_map :: BASE_SHIFT
  bonding_map::M1          OLD/NEW  bonding_map :: V1

RE-KEY to CORE_1X — the change the ruling is FOR:
  bonding_map::DTWWER   OLD -> bonding_map :: CORE_1X    NEW -> valid_die_ref :: CORE_1X
  dt_map::MID_01        OLD -> dt_map      :: CORE_1X    NEW -> valid_die_ref :: CORE_1X
  bonding_map::DT_F     OLD -> bonding_map :: CORE_1X    NEW -> valid_die_ref :: CORE_1X
```

Note the OLD column of the re-key: today, picking `CORE_1X` looks for it in `bonding_map`, where it
does not exist. That is the defect the ruling closes.

### 6b. Mask — die key by die key, on 854 real cells

`valid_die_ref :: CORE_1X`, its declared frame from `wafer_map_metadata`. **Every defect axis is
active:** `chipX 7 ≠ chipY 8`, rot **270**, offsets **5,5** (non-zero), grid **45×39** (non-square).

```
OLD mask cells: 854   NEW mask cells: 854
keys in OLD but not NEW: 0
keys in NEW but not OLD: 0
--> PER-CELL VERDICT: every die key identical
first 12 die keys (px_py): 20_-4 20_-3 20_-2 20_-1 19_-7 19_-6 19_-5 19_-4 19_-3 19_-2 19_-1 18_-9
```

**Differential — how many of the 854 land on a different die if the frame is misread:**

| misreading | cells on a different die | mask size |
|---|---|---|
| rotation read as 0 | **341** | 854 |
| chip pitch swapped 7×8 → 8×7 | **108** | 854 |
| offset dropped | **41** | 854 |
| y-invert flipped | **284** | 854 |

No axis is 0, so the fixture proves something on each. And note every misread mask still has **854
cells** — an identical count with 341 cells on the wrong dies is exactly the M5-I5b/M4 blind spot,
which is why the comparison above is key→key and not a count.

---

## 7. Harness and contract movement

| | before | after | |
|---|---|---|---|
| `map_key_datalist_harness` | 53 | **54** | floor raised; population re-pinned to `valid_die_ref` and a *never asks for the canvas table* assertion added |
| `valid_die_authoring_harness` | 99 ran / 1 failed | **100 ran / 1 failed** | still known-red (same single pre-existing failure); mutations **19/19 caught** |
| `undeclared_identifier_harness` | 6 | **10** | commit `510a748` |
| `geometry_origin_reseat`, `offset_pitch_guard` | — | — | stub for the newly wired SAVE handler |
| contracts | 6/6 | **6/6** | |

Mutations: `M14`/`M15` described the `<select>` and retire with it; `M20`/`M21` are the same two
failures expressed against the control that survived —
`const table = VALID_DIE_TABLE` (repoints untouched legacy declarations) and
`const table = shown.table` (the fixed table stops being fixed). **Both were put back into the real
source and both go red**, on the harness *and* on the seam contract:

```
M20 injected -> map_seam RED at:
  legacy_cross_table_declaration_untouched_save   keep, saved_table
  absent_declaration_untouched_push               keep, payload_is_the_untouched_grid_meta_object
  unreadable_declaration_untouched_push_is_preserved
  retyping_the_same_key_is_not_an_edit            keep, saved_table
M21 injected -> map_seam RED at:
  user_declares_on_a_previously_absent_map                saved_table
  user_rekeys_a_legacy_declaration_onto_the_fixed_table   saved_table
restored -> 6 contracts, no divergence
```

**Contract change, flagged for the Lead PM / contract-keeper.** `valid_die_push_decision_cases` lost
`user_repoints_to_another_table` and `user_inherits_the_home_table` (they describe a control that no
longer exists) and gained `user_rekeys_a_legacy_declaration_onto_the_fixed_table` and
`retyping_the_same_key_is_not_an_edit`. The group's fixture-inactivity guard was re-anchored from
"is the declared table in the option list" to "does the declared table agree with the fixed one",
plus a new guard requiring a re-key case that lands on the fixed table — without it, "never rewrite
an untouched declaration" is satisfied by never writing anything. The `$comment` records all of this
in the file. `contracts/map_seam/client_harness.mjs` also gained one general improvement: declared
`client_consts` are now published on the sandbox global, because a top-level `const` in
`vm.runInContext` is invisible to the scorer and the alternative was re-typing the table name.

---

## 8. The module-state ceiling (commit `510a748`, separate)

**Measured: 48**, not 92. My definition: **top-level `let`/`var`, per bound name** — exactly
"bindings whose value can still change after the module finishes evaluating". For context, the same
file has 40 top-level `const` and 227 top-level `function`; 17 of those consts hold a mutable
container (`el`, `mapKeyListCache`, …). Those 17 *are* shared mutable state and the exclusion is the
honest weakness of the definition — it is excluded because detecting "const holding a mutable
container" is a heuristic (`new Map()` is visible, `makeThing()` is not) and a gate satisfiable by
changing the shape of an initialiser measures the initialiser, not the state. **If you prefer 65
(48 + 17) as the ceiling, say so and I will re-baseline** — but a crisp under-count that cannot be
gamed seemed the better trade.

**Yes, 48 includes the dead pair.** `tables` is #1 and `isMouseDown` is #7 in the list. They stay
boarded and undeleted, and this is recorded in the `CEILINGS` comment so the first re-baseline is
expected rather than surprising.

Implementation: `undeclared_identifier_harness.mjs` (same oxc parser via `rolldown/parseAst`, zero
new dependencies) emits `MODULE_STATE <n>`; `check_harnesses.mjs` holds `CEILINGS` beside `FLOORS`
so a baseline is edited in one file either way. Self-vacuity: a new top-level `let` must raise the
count by exactly 1, and a top-level `const` plus function-local `let`/`var` must not raise it at all.

Proven in four directions:

| probe | result |
|---|---|
| baseline | green, exit **0** |
| `+ let __ceilingProbe = 1;` at module scope | `[BLOCKING] MODULE_STATE 49, but the ceiling is <= 48`, exit **1** |
| restored | exit **0** |
| removed `let tables = [];` (48 → 47) | exit **0**, reported as `came in UNDER their ceiling … Not a failure. Lower the ceiling when convenient` |
| `MODULE_STATE` line silenced | `[BLOCKING] no \`MODULE_STATE <n>\` line … A silent ceiling is not a ceiling`, exit **1** |

**Scope: `map_editor.js` only.** My view on extending it: worth doing, but only after measuring —
`transfer_plan.js` is the obvious next candidate and it is 1875 lines, but the R3–R6 evidence is
about `map_editor.js` specifically and a ceiling set on an unmeasured file is a number nobody can
defend when it first bites.

---

## 9. Bugs found while working — reported, not fixed

1. 🔴 **`bonding_map · 4E` has zero cells, so `bonding_map · 4E_E1` is permanently `refused` in
   production today.** Observed live on load: `유효 다이 맵을 해석하지 못했습니다 — bonding_map · 4E:
   참조 맵에 좌표로 읽히는 셀이 없습니다`. Confirmed independently: `GET /tables/bonding_map/data`
   filtered `base = 4E` returns `total: 0`. Worth a sweep of all 8 legacy references — some of the
   others may be dead too, and a `refused` map is showing the operator the pre-M4 circle.
2. 🟡 **The untriaged known-red assertion in `valid_die_authoring_harness` is a HARNESS defect, not a
   product one — attributed today.** The assertion is
   `resolveSrc.indexOf('validDieChainError') < resolveSrc.indexOf('projectCellsToPhys')`. In the real
   `resolveValidDie`, `projectCellsToPhys` first appears at offset **8297 inside the `[H5]` comment**
   ("`projectCellsToPhys`가 참조 치수로 프레임 창을 열고…"), while the chain guard's call is at 9564.
   The **code** order is correct — the chain check does run before any cell is projected. A text
   `indexOf` is being beaten by a comment mention. Fixing it means matching a call, not a substring.
   I did not touch it: it is on the debt list and outside this round.
3. 🟡 **`bonding_map` is not a product-owned table**, contrary to the brief's premise (see §5).

## 10. Living-document update points (for doc-keeper — I edited no `docs/`)

Found by looking up the code paths I touched in `docs/process/DOC_OWNERSHIP.md`, not by enumeration:

* **Row 62 (유효 다이 맵 M4)** → `guide/VALID_DIE_MAP_GUIDE.md` is the operator-facing canon and that
  row warns in red that changing a verdict or a message stales the user guide first. **Three things
  changed that it quotes or implies:** the table picker is gone, applying is now a button, and there
  is a save that does not apply. Also `spec/MAP_EDITOR_SPEC §5.7/§5.7-bis/§5.7-ter`,
  `qa/FEATURE_CHECKLIST §1.7 / §2.9`, `architecture/PRIMITIVES §4`.
* **Row 61 (웨이퍼 맵 에디터)** → `map_editor/README.md`, `spec/MAP_EDITOR_SPEC §1~§4`.
* **Row 41 (제품 소유 테이블 배포)** → `guide/DEPLOY_SETUP §1-2`, `guide/CONFIG_GUIDE §5.8-ter` —
  `PRODUCT_TABLES` is now **five** entries, not four.
* **Row 44 (계약 벡터)** → `architecture/frontend §2`, `qa/FEATURE_CHECKLIST §2.0`. Contract *count*
  is unchanged (6), so only the `map_seam` description moves.
* **Row 77 (설정 전반)** → `guide/config_reference/` records its own trigger ① *`.sample` 변경*, and
  `table_config.json.sample` changed. `guide/config/table_config.md` mentions
  `install_product_tables.py`.
* Also worth a board line: the harness runner now has a **ceiling** concept alongside floors —
  wherever `architecture/frontend §2` / `qa/FEATURE_CHECKLIST §2.0` describe `check_harnesses.mjs`.
* The doc-keeper trigger fired twice during this round (**63 commits accumulated**).

## 11. Proposed lessons for `agent_workspace/memory/map-pm.md` (proposal only)

* **함정**: 저장 포맷의 의미를 바꾸는 것으로 "테이블 고정"을 구현하면, 이미 저장된 선언 전부가
  다른 맵을 가리키게 되고 화면은 정상으로 보인다.
  **올바른 방법**: 고정은 **저작(쓰기) 쪽에만** 건다. 읽기 규칙(`parse*`)은 이음매 계약이 채점하는
  저장 포맷의 뜻이라 건드리지 않는다. "사용자가 그 값을 바꿨는가"가 유일한 분기이고, 안 바꿨으면
  원문을 그대로 되쓴다.
* **함정**: 컨트롤을 지우면 그 컨트롤에 묶인 하네스·계약이 조용히 아무것도 채점하지 않게 된다.
  **올바른 방법**: 사라진 컨트롤이 지키던 **불변식이 어디로 옮겨갔는지** 먼저 적고, 그 새 자리에
  대해 결함 두 방향(과잉 보존 · 과잉 수정)을 다 주입해 양쪽이 빨개지는지 확인한다.
* **함정**: `vm.runInContext` 안의 최상위 `const`는 슬라이스된 함수에는 보이지만 **채점기에는
  안 보인다**. 그래서 채점기가 그 값을 다시 타이핑하게 되고, 그 사본이 낡는다.
  **올바른 방법**: 소스에서 추출해 sandbox 전역에 실어 준다(`contracts/map_seam/client_harness.mjs`
  의 `client_consts` 루프가 지금 그렇게 한다).
