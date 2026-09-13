# S3A - Orientation declaration (build) + refusal blast radius (measure)

**Stage A only.** Nothing on the coordinate path changed. `git diff` is `server/map_overlay.py`
(+177, additive) plus one new untracked test module. Not committed.

* Measured: **2026-08-05**, database `assy_manager` (resolved from
  `database.database.SQLALCHEMY_DATABASE_URL`), table **`wafer_map_metadata`**, 668 rows,
  every connection opened with `SET TRANSACTION READ ONLY`.
* Files: `server/map_overlay.py:367-541` (new), `server/tests/test_orientation_declaration.py`
  (new, 43 tests).

---

## 0. Three premises in the brief were wrong

**0.1 `DB_URL_SOURCE` is `"default"` on this machine.** The brief said "the production
database name differs from the developer default and reading the default silently probes the
wrong database." Here `resolve_database_url` finds neither `DATABASE_URL` nor
`<config>/database.json`, so `SQLALCHEMY_DATABASE_URL` **is** `DEFAULT_PG_URL` -
`postgresql://.../assy_manager` - and it holds the 668 rows. I followed the rule as written
(never read `DEFAULT_PG_URL`), but the rule is currently a no-op here, and a future agent who
believes the warning will conclude it read the wrong database when it did not.

**0.2 `eqp_frame_attribution.dt_frame` is NULL in 4 rows out of 4.** The brief's frame mix
(rot0/back 40, rot90/front 40, rot0/front 20, rot180/front 20) is real - but it lives in
`wafer_map_metadata`'s **dt_map rows**, not in the frame-attribution table. Measured:

```
DT-EQP-01|PRD-A  core_frame=None dt_frame=None cell_count=2889
DT-EQP-02|PRD-A  core_frame=None dt_frame=None cell_count=2892
DT-EQP-01|PRD-B  core_frame=None dt_frame=None cell_count=1446
DT-EQP-02|PRD-B  core_frame=None dt_frame=None cell_count=1473
```

So `dt_log_to_dt_map` today derives 0 rows for a reason **earlier** than the one on record:
every row holds at `frame_missing` before any transform is attempted. The board says "identity
refuses first"; identity is not reached.

**0.3 The 516 figure survives - the mechanism named in the spec does not.** This confirms the
mid-task correction and sharpens it. Re-derived independently:

| | rows |
|---|---|
| `rotation` key absent | **0** |
| `rotation` present but unparsable | **0** |
| `rotation` present, numeric, **no evidence anyone chose it** | **516** |
| ... of which carry the `auto_registered` mark | **320** |
| ... of which do not | **196** |

`MAP_ALIGNMENT_SPEC.md` section 9c says `_rotation_of` swallows key-absence, parse failure and
an explicit 0 alike, and that rotation 0 is 516 of 668 rows. The count is right; the sentence
attributes it to a collapse that **has zero live instances**. That sentence should be corrected
in the spec - it is currently a true number resting on a false cause, which is the kind of thing
that survives review.

---

## 1. What I built

`server/map_overlay.py:482 orientation_declaration(meta) -> dict`, the twin of
`geometry_declaration:333`. Returns all five axes, always:

```python
{"rotation":      {"value": 0,       "source": "indeterminate"},
 "side":          {"value": "front", "source": "indeterminate"},
 "grid_y_invert": {"value": False,   "source": "indeterminate"},
 "grid_start_x":  {"value": 1,       "source": "absent"},
 "grid_start_y":  {"value": 1,       "source": "absent"}}
```

`value` is always **what the coordinate path will actually use** (the reader's own value, even
on a refusing token), so no caller has to re-derive it - that re-derivation is how a question
gets a second spelling.

`server/map_overlay.py:528 orientation_refusal(meta) -> str | None` - human Korean, names the
axis, judges nothing. **Called from nowhere.** A test asserts that
(`test_nothing_on_the_coordinate_path_calls_the_refusal_yet`).

### The predicate is one rule, and it is the same rule on all five axes

> **A stored value that equals what the reader invents when the key is missing is not evidence
> that anyone chose it.**

The no-evidence value per axis is not a hand-written constant; it is taken from the readers
themselves - `_rotation_of:235` (0), `_side_of:257` ("front"), `_y_invert_of:261` (False),
`_grid_of:250-251` (1). `test_no_evidence_values_are_the_readers_own_absent_defaults` asserts
the table against the readers rather than against literals, so a reader whose default changes
takes the table with it instead of leaving the predicate quietly pointing at a stale value.

### The vocabulary: four tokens verbatim, plus one

`declared` / `auto_registered` / `absent` / `unparsable` are **the same string constants**
(`GEOMETRY_*`, `map_overlay.py:314-317`). I did not alias them, did not rename them, and did
not touch those four lines - `client2/src/map/declaration.js` copies them and the seam is
intact. Confirmed by diff: my insertion starts at line 367 and the diff is 177
insertions / 0 deletions.

The fifth token is `ORIENTATION_INDETERMINATE = "indeterminate"`:

> the value is present and well-formed, but **there is no evidence anyone chose it**.

**Why the client lane's four-token shape does not transfer.** The client's fork was a declared
zero eaten by a `|| default`, and it resolved by keeping `declared` while recording the raw
value alongside the value the legacy path would have produced. That works because on the client
the two differ: raw `'0'` vs raw `''`. On the server they are the same bytes. Measured, not
argued (winning writer per row from `cell_sources`, table_name=`wafer_map_metadata`,
column_name=`grid_metadata`, latest by `ingested_at`):

| last writer | rotation token | rows | what the writer is |
|---|---|---|---|
| `custom_script` | `indeterminate` | **83** | `generate_core_defect.py:134` writes the literal `"rotation": 0` |
| `custom_script` | `declared` | 80 | `generate_eds_fail.py:36,142` writes `ROTATION_DEG = 180` |
| `user` | `indeterminate` | 53 | editor push; `map_editor.js:66` `let currentRotation = 0` |
| `user` | `declared` | 12 | rotation 270 (10), 90 (2) |
| `auto_map_meta` | `auto_registered` | 120 | `synthesize_grid_meta` |
| trace-fixture CSV | `auto_registered` / `declared` / `indeterminate` | 200 / 60 / 60 | |

**83 production rows** carry a rotation that is present, numeric, correctly typed, carries **no
`auto_registered` mark**, and was written by a machine that hardcodes the constant. Recording
"raw vs legacy" for those yields `(0, 0)`. There is no fifth spelling of "declared" here - there
is a fifth **answer**, and folding it into `declared` is I4 exactly (a plausible default
impersonating a declaration), while folding it into `absent` is false, since the key exists and
`make_frame_transform` uses its value.

The 53 `user` rows are the honest edge: an operator may genuinely have meant 0. `indeterminate`
does not say they did not. It says **nothing in the schema can tell**, which is the truth.

### Where the phys vocabulary does not fit, and why

`auto_registered` covers `PHYS_KEYS` only (spec section 9c). Extending it to orientation is
sound exactly as far as `synthesize_grid_meta` (`map_meta_registrar.py:184-194`) could have
produced the stored value:

* `rotation` / `side` / `grid_y_invert` - the registrar writes **only** `0` / `"front"` /
  `False`. A marked row saying `rotation: 90` was written by something else (the editor carries
  the mark forward while letting the operator change rotation, `map_editor.js:6292`), so
  `auto_registered` there would be a **false** provenance claim. The value wins.
* `grid_start_x/y` - the registrar writes the **observed minimum coordinate**, any integer. The
  mark explains any value, and reading "not 1, therefore a person chose it" would promote a
  machine's bbox scan into a declaration. The mark wins.

Live effect of that distinction today: **0 rows**. I kept it anyway and tested both branches;
it is a place that diverges silently rather than loudly.

### Caveat I am not hiding

`grid_start_x = 0` appears in 403 rows and scores `declared` on the unmarked ones. The editor's
`parseInt(el.gridStartX.value, 10) || 0` turns a **cleared field** into 0, so a 0 start is
weaker evidence than a 90-degree rotation. I did not invent a token for it. If the lead wants
start treated as unattested-by-default, that is a one-line change to the no-evidence table plus
a re-run of the census - say so and I will re-measure rather than guess the delta.

---

## 2. A2 - the census

**2026-08-05, `wafer_map_metadata`, all 668 rows, read-only.**

| axis | declared | indeterminate | auto_registered | absent | unparsable |
|---|---|---|---|---|---|
| `rotation` | 152 | 196 | 320 | 0 | 0 |
| `side` | 55 | 293 | 320 | 0 | 0 |
| `grid_y_invert` | 2 | 346 | 320 | 0 | 0 |
| `grid_start_x` | 131 | 217 | 320 | 0 | 0 |
| `grid_start_y` | 131 | 217 | 320 | 0 | 0 |

Values actually in force:

```
rotation       0:516   180:100   90:42   270:10
side           front:613  back:55
grid_y_invert  False:666  True:2
grid_start_x   0:403  1:257  2:2  -4:2  -3:2  -8:1
grid_start_y   0:407  1:253  2:2  -3:2  -2:2  -39:1
```

Rows by number of declared orientation axes: **0 axes: 437 | 1: 99 | 2: 26 | 3: 105 | 4: 0 |
5: 1**. `orientation_refusal(...) is None` for exactly **1 of 668 rows**.

Cross-tab against the phys axis - the two predicates agree on the marked rows and split cleanly
on the rest:

```
geometry=auto_registered   rotation=auto_registered   320
geometry=declared          rotation=declared          152
geometry=declared          rotation=indeterminate     196
```

By table:

```
bonding_log      120  auto_registered 120
core_wafer_map   200  auto_registered 200
core_defect_map   80  indeterminate 80
eds_fail_map      80  declared 80
dt_map           146  indeterminate 85, declared 61
bonding_map       32  indeterminate 25, declared 7
sample_map         4  declared 1, indeterminate 3
valid_die_ref      4  indeterminate 3, declared 1
test               2  declared 2
```

### The population the brief asked me to size instead of 516

`load_map_meta` returns `None` when a map has no `wafer_map_metadata` row. Sized read-only by
composing each map table's declared `map_key_columns` over its own data and differencing
against the 668 registered keys:

| table | distinct map keys in data | registered | **unregistered** |
|---|---|---|---|
| `bonding_log` | 120 | 120 | 0 |
| `core_wafer_map` | 200 | 200 | 0 |
| `bonding_map` | 1 | 1 | 0 |
| `dt_map` | 1 | 1 | 0 |
| `valid_die_ref` | 4 | 4 | 0 |
| **`dt_log`** | **73** | **0** | **73** |

**73**, all of them `dt_log`, covering all **8,700** `dt_log` rows across 120 jobs. `dt_log` was
declared a map table (`map_key_columns: [dt_lot, dt_slot]`) and has no metadata rows at all, so
every alignment that reaches it takes the meta-absent identity branch at
`map_overlay.py:755-757` - the one that writes raw coordinates and labels them
`origin: "identity"`. That is the honest replacement for 516 on the "the collapse bites when
meta is None" axis.

Not measurable read-only, and I am naming it rather than estimating: **how often each of those
73 is actually requested.** There is no request log for `/api/maps/overlay`, so exposure is
sized, traffic is not.

Incidental, outside my scope, flagged because it is a live refusal: **8 rows declare
`valid_die_ref` and 0 of them resolve.** They name `BASE_4E, 4MAIN_DT, DT, DT_TEST, 4E,
DT_TEST, BASE_SHIFT, V1`; the registered `valid_die_ref` map_ids are `5N_BASE, CORE_1X,
CORE_YINV, TEST_TEST`. Every one of those 8 maps gets `SOURCE_REFUSED` for its valid-die basis
today, independent of anything in this task.

---

## 3. A3 - blast radius. **The refusal should not be relocated.**

### 3.1 Who takes the shortcut

`resolve_align:762` shortcuts when all eight `frame_axes` components match. Grouping the 668
registered maps by that signature gives **59 distinct frames**; pairs inside a group shortcut,
pairs across groups reach `make_frame_transform`.

| | ordered pairs |
|---|---|
| all pairs (668 x 667) | 445,556 |
| **take the identity shortcut** | **71,126 (15.96%)** |
| reach `make_frame_transform` | 374,430 |

Largest shortcut groups - note that the brief's four-frame mix is right, it is just in `dt_map`:

```
n=232  53,592 pairs  rot=0   front  core_wafer_map 200 + bonding_log 32   all auto_registered
n=80    6,320 pairs  rot=0   front  core_defect_map 80                    all indeterminate
n=80    6,320 pairs  rot=180 front  eds_fail_map 80                       all declared
n=40    1,560 pairs  rot=90  front  dt_map 40                             all declared
n=40    1,560 pairs  rot=0   back   dt_map 40                             all indeterminate
n=20      380 pairs  rot=180 front  dt_map 20                             all declared
n=20      380 pairs  rot=0   front  dt_map 20                             all indeterminate
```

### 3.2 How many would be refused

| policy | refused of 71,126 |
|---|---|
| **A - strict** (any of 5 axes not `declared`, either side) | **71,126 (100.00%)** |
| **B - narrow** (only `auto_registered` / `absent` / `unparsable`) | **54,196 (76.20%)** |
| **C - rotation + side only, strict** | **71,126 (100.00%)** |

Realized traffic is much smaller than the exposure surface. The overlay endpoint's dominant
shape is "same map key, different table" (`parse_sources` inherits the target key): 84 map_ids
appear in more than one table, giving **172 ordered pairs**, of which **2** shortcut, 170 reach
the transform, and **4 already refuse** on geometry. Relocating the refusal adds **2** new
refusals there under policy A and **0** under policy B.

Both numbers are true and they answer different questions. 71,126 is what is *exposed*;
172 is what today's screens actually build. I have no way to weight them - there is no request
log.

### 3.3 What breaks for a user

1. **Overlay screen (map editor layers).** `map_overlay.py:1131` calls `resolve_map_transform`
   inside `try`, and the `except ValueError` handler at **`:1134` calls `resolve_align` again**
   to build the degraded payload. A refusal placed *inside* `resolve_align` therefore raises
   **from inside the exception handler**, escapes `get_overlay`, and hits
   `main.py:4154-4156`'s `except Exception` -> **HTTP 500, detail "Failed to build map
   overlay."**. The operator loses **every** source in the request, not the refused one, and
   the refusal text - the only thing that says which map to fix - is discarded. Today the same
   situation degrades one source to `align_unavailable` with the reason attached. This is the
   single most important thing stage B must not do accidentally.
2. **Bonding plan availability** (`bonding_plan.py:752`) - per-role status flips
   `connected` -> `connected(align_unavailable)`. Counts stay valid (transform-invariant), but
   region queries and coordinate placement stop. Under policy A that is every role on every
   plan.
3. **Transfer plan fail overlay** (`transfer_plan.py:1591`) - returns
   `(None, "align_unavailable", False)`; the fail-map layer disappears from the plan screen.
4. **Valid-die basis** (`map_overlay.py:1603` region) - `SOURCE_REFUSED`, and it deliberately
   does **not** fall back to the wafer circle, so the editor loses the mask and shows the
   reason.
5. **`dt_map` derivation** (`dt_map_derivation.py:642`) - `HOLD_TRANSFORM_UNAVAILABLE`. Zero
   effect today: the rule is `enabled:false` and holds at `frame_missing` first (section 0.2).

### 3.4 Ruling on `origin="identity"` - **it conflates, and splitting it is the fix**

It carries **three** situations under one string:

| # | site | meaning | today's size |
|---|---|---|---|
| i | `map_overlay.py:755-757` | either meta is absent - "no basis to think otherwise" | 73 unregistered map keys / 8,700 `dt_log` rows |
| ii | `:762` with both sides attested | "genuinely the same frame" | **0 pairs** |
| iii | `:762` with either side unattested | "both readers produced the same values, and at least one of them is a default nobody chose" | **71,126 pairs** |

The decisive number: **of the 71,126 shortcut pairs, 0 have both sides declared on all five
orientation axes.** Today `origin="identity"` *never* means (ii). Case (i) is distinguished only
by a free-text `note`, which no consumer parses.

**So I rule against relocating the refusal, and for splitting the origin.** The reasons are
measurements, not preference:

* Policy A refuses **100%** of shortcut pairs. `frame_axes` equality genuinely *is* sufficient
  for the transform to be the identity - when every axis matches, no coordinate moves and the
  pitch cannot matter (this is the `frame_axes` docstring's own [D1] argument, and it is still
  correct). Refusing to do nothing is not safer; it is just refusing. It would take out case
  (ii) as well, which is the case we want to keep.
* Policy B still refuses **76.20%**, and the 54,196 it takes out are dominated by one group of
  232 auto-registered maps (`core_wafer_map` + `bonding_log`) overlaying **each other** - pairs
  where both sides are the same unmeasured frame and the transform is genuinely identity.
* The actual defect is not that the shortcut skips a refusal. It is that the shortcut's premise
  ("the axes are equal, therefore the frames are the same") is **unfounded when the equality is
  an equality of defaults**. That is a labelling defect, and refusing is the wrong instrument
  for it: it destroys the 15.96% of pairs that work while telling the operator nothing about
  which map to fix.

Proposed shape for stage B (**not implemented, and it needs approval - `align_applied.origin`
is a boundary contract**): keep the shortcut, split its outcome.

```
origin = "identity"            # (ii) both sides attested on every axis - unchanged meaning
origin = "identity_unattested" # (iii) axes equal, but at least one side has no provenance
origin = "identity_no_meta"    # (i)  one side has no meta row at all
```

Nothing refuses; the coordinates are unchanged in all three. What changes is that a consumer
can finally tell "we checked" from "we had nothing to check", which is what section 0.2 layer 9
(consume the record, or downgrade) needs and does not have. Sizes above give the exact partition
on day one: 0 / 71,126 / (73 unregistered keys).

**If the lead wants a refusal anyway**, the only defensible placement is *not* above the
shortcut but above the **write** - `dt_map_derivation.py:663-664`, where a `transform is None`
becomes a stored coordinate. That refuses the thing that persists rather than the thing that
renders, and its blast radius today is 0 rows (rule disabled). I did not implement it.

---

## 4. Mutation discipline

Mutations injected by an in-memory pytest plugin (`-p mutplug`, monkeypatch style - no source
edit, so no stale-`.pyc` and no CRLF hazard). The plugin's `pytest_sessionfinish` re-probes the
mutated state **after the last test finishes** and prints it, so a mutation that something
repaired mid-run cannot masquerade as an honest red.

| | mutation | result | state at `sessionfinish` |
|---|---|---|---|
| baseline | none | **43 passed** | `no mutation` |
| MUT=1 | fold `indeterminate` into `declared` | **5 failed**, 38 passed | `declared` - still mutated |
| MUT=2 | drift rotation's no-evidence value 0 -> 999 | **6 failed**, 37 passed | `999` - still mutated |
| MUT=3 | let the mark explain any value on every axis | **1 failed**, 42 passed | `True` - still mutated |

MUT=1 kills `test_the_canonical_row_is_indeterminate_on_three_axes_not_declared`,
`test_indeterminate_is_not_declared_and_not_absent`,
`test_rotation_360_normalises_to_zero_and_is_therefore_indeterminate`,
`test_a_mark_that_is_not_literally_true_is_not_a_mark`,
`test_refusal_names_the_axis_so_the_operator_knows_what_to_fix`. MUT=2 kills those five plus the
load-bearing `test_no_evidence_values_are_the_readers_own_absent_defaults`. MUT=3 kills only
`test_the_mark_cannot_explain_a_rotation_the_registrar_never_writes`, which is the whole point
of that test existing - it is the single assertion guarding a distinction with 0 live instances.

**Full suite, clean:** **2,261 passed, 1 failed, 6 skipped** in 432s. The one failure is
`tests/test_dual_stack_bind.py::test_the_launcher_default_is_the_dual_stack_host`,
`ModuleNotFoundError: No module named 'run_decoupled_app'` - pre-existing, unrelated to
`map_overlay`, untouched by this change.

**Full suite under MUT=1:** **6 failed, 2,256 passed, 6 skipped** in 388s - the same 5
orientation tests plus that same pre-existing failure, and
`[MUT=1] state at sessionfinish: 'declared'`. The mutation was still in force after 2,262 tests
across 6.5 minutes, so the red is a real red and not a mutation something quietly repaired
mid-run. No pytest process ran concurrently with another at any point.

---

## 5. Deviations and open items

1. **Code comments are in Korean, not English as the brief asked.** `map_overlay.py` is Korean
   throughout, including the `[D1]` block this is the direct twin of; an English `[D2]` block
   next to a Korean `[D1]` would split the file. Say the word and I will convert it. This report
   and any commit message are English as instructed.
2. **Docs not touched.** `MAP_ALIGNMENT_SPEC.md` is lead-owned, and section 2.2 warns against
   editing conclusions without their premises. Three corrections are needed there and I have not
   made them: section 9c's mechanism (see 0.3), the `dt_frame`-is-NULL fact (0.2), and the
   `origin="identity"` partition (3.4). Per `DOC_OWNERSHIP.md`, a stage B that lands the split
   also touches `architecture/backend.md` and `qa/FEATURE_CHECKLIST.md`.
3. **Not committed, nothing restarted, no process touched.** `client2/` untouched.
4. The four token strings at `map_overlay.py:314-317` are byte-identical to before; the
   `client2/src/map/declaration.js` seam is intact.

---

## 6. Lead ruling (2026-08-05) - answers, the rule, and the origin consumer census

### 6.1 The four token strings: **unchanged. Zero edits. Not one byte.**

Stated plainly because the client now copies them: **I changed none of the four.** Evidence,
not assertion:

* `git diff --stat -- server/map_overlay.py` = **177 insertions, 0 deletions**. A deletion count
  of zero means no existing line was touched, including those four.
* My insertion begins at line **367**, after `geometry_refusal` ends at 364. Everything at or
  below 366 is untouched, so the anchor did not move either.
* Read back from the loaded module: `declared` / `auto_registered` / `absent` / `unparsable`,
  and `AUTO_REGISTERED_KEY = "auto_registered"`.

The only new string in the vocabulary is `"indeterminate"`. Nothing was renamed, aliased, or
re-cased. If any of the four ever must change, it changes on both sides in one round and gets
pinned first - see 6.4, where the pin does not exist yet.

**Anchor correction for `declaration.js`:** it cites the token block as `map_overlay.py:312-316`.
The real block is **`314-317`**; `312` is `AUTO_REGISTERED_KEY`, which is the marker *key*, not a
token. Off-by-two, still off after my change (my change did not move it). Worth fixing in the
client comment, since an anchor that is wrong by two lines is how the next reader concludes the
marker key is a fifth token.

### 6.2 The tainting rule, stated as a rule

For the client to implement rather than transcribe. Two independent rules; both are needed and
neither implies the other.

> **Rule N (no evidence).** A stored value equal to *what your own reader produces when the key
> is absent* is not evidence that anyone chose it.
>
> **Rule T (marker taint).** `auto_registered` means "the values in this row that the
> auto-registering writer produces were produced by it, not measured". It taints an axis **iff
> the stored value lies in the range of what that writer emits for that axis** - and for no
> other reason.

Rule T's range test per axis, from `map_meta_registrar.synthesize_grid_meta:168-196`:

| axis family | the writer's range | so the marker taints |
|---|---|---|
| the six `PHYS_KEYS` | the synthetic constants (chip 1x1, offsets 0, margin 3, circumscribing dia) | **always** - and the existing `geometry_declaration` deliberately does not sniff the value, because a real 1 mm die is legal and the value must never *be* the marker |
| `rotation` / `side` / `grid_y_invert` | exactly `{0}` / `{"front"}` / `{False}` - nothing else, ever | **only when the value is that one.** A marked row saying `rotation: 90` was not written by the registrar (the editor carries the mark forward while letting the operator change rotation, `map_editor.js:6292`); answering `auto_registered` there is a false provenance claim |
| `grid_start_x` / `grid_start_y` | the **observed minimum coordinate** - any integer | **always.** "Not 1, therefore a person chose it" would promote a machine's bbox scan into a declaration |

The marker and the value are **not in competition.** The marker names the *writer*; the range
test asks whether that writer could have produced *this* value. When it could not, the marker is
simply silent about that one axis and still holds for the others.

Decision order per axis - this order, not another:

```
1. key missing or blank                              -> absent
2. present, but not a value the reader can read      -> unparsable
3. marked AND the writer's range contains the value  -> auto_registered
4. value != the no-evidence value                    -> declared
5. otherwise                                         -> indeterminate
```

**Portability warning, and this is the part a transcription would get wrong.** Rule N is
portable; **its constants are not.** The no-evidence value is defined as *your own reader's
absent-default*, and the two sides read from different places - the server from a meta dict, the
client from DOM controls. Server side, measured from the readers themselves:
`rotation=0, side='front', grid_y_invert=False, grid_start_x=1, grid_start_y=1`. If the client's
start default is `0` (`parseInt(...) || 0`) while the server's is `1`, the same row scores
`declared` on one side and `indeterminate` on the other - a divergence produced by two correct
implementations of the same rule. **Each side must derive its constants from its own readers and
then the two lists must be compared**, not copied. That comparison is a contract vector, not a
code review.

One acknowledged asymmetry, so it is on the record rather than discovered later:
`geometry_declaration` checks the mark *before* absent/unparsable; `orientation_declaration`
checks it after. Both refuse either way, so the only observable difference is which reason a
marked row with a missing key reports. **Live instances: 0** - measured, no marked row is missing
any phys key or any orientation key.

### 6.3 The 320, and the 516 stated honestly

The ruling's statement holds, and I can put numbers under every clause. Measured 2026-08-05,
production `wafer_map_metadata`, read-only:

* **320 rows carry `auto_registered`.** All 320 have `(rotation, side, grid_y_invert) =
  (0, "front", False)` - a single distinct triple across all 320, which is the registrar's output
  and nothing else. **All five** orientation axes on **all 320** rows taint. Their orientation was
  defaulted by `map_meta_registrar.py:184-186`, not measured.
* **Until today nothing could say so on this axis.** The mark was in the row the whole time -
  what was missing is a predicate that read it for orientation. `geometry_declaration:333` covers
  `PHYS_KEYS` only; `_rotation_of` / `_side_of` / `_y_invert_of` never look at the mark at all.
  The fact was recorded and unreadable.

The three-position history is worth keeping, because each position was true about something
different and only one was measured:

| position | claim | verdict |
|---|---|---|
| brief | "516 rows are ambiguous" | wrong mechanism - absent = 0, unparsable = 0, nothing collapses |
| client-lane correction | "0 rows are ambiguous" | true **about stored types only**; every value is present, numeric and well-typed |
| measured | **516 = 320 marked + 196 unmarked**, none of them evidence of a choice | holds |

And the 196 deserve their own split, because "the row says it was defaulted" and "nothing in the
row can say" are different repairs:

| | rows | what the row can tell you |
|---|---|---|
| marked | **320** | it says, in the row, that a machine wrote it - `auto_registered` |
| unmarked, provably machine-written | **83** | `generate_core_defect.py:134` hardcodes `"rotation": 0` and writes no mark - `indeterminate` |
| unmarked, genuinely unknowable | **113** | 53 `user` pushes + 60 fixture CSV; may have been chosen, may not - `indeterminate` |

**That 83 is why the fifth token is not optional.** Without it those rows answer `declared` while
being demonstrably machine-defaulted.

**QA's divergence figures reproduce exactly**, re-derived from the production table (not from a
fixture) as "rows where my token is not `declared`, i.e. where a four-token implementation would
say `declared`": rotation **516/668**, side **613/668**, grid_y_invert **666/668**, grid_start_x
**537/668**, grid_start_y **537/668**. Four for four.

### 6.4 Consumer census for `align_applied.origin` - required before the split, delivered before

Every consumer of the value, and what each does with a token it has never seen.

**Server - safe by construction. Every comparison is against `derived`, never against
`identity`.**

| # | site | what it does | unknown token |
|---|---|---|---|
| 1 | `map_overlay.py:797` `resolve_map_transform` | `if origin == ALIGN_ORIGIN_DERIVED:` build the transform | falls through -> `transform = None` -> **identity semantics, correct** |
| 2 | `map_overlay.py:810` `_pure_translation` | `if origin != ALIGN_ORIGIN_DERIVED: return None` | returns None -> no offset shown -> **correct** |
| 3 | `map_overlay.py:820-832` `align_applied_payload` | emits it; `or ALIGN_ORIGIN_IDENTITY` is a null-guard only | pass-through -> **correct** |

Pass-through, value discarded: `bonding_plan.py:752` (`_origin`), `transfer_plan.py:1591`
(`_origin`), `dt_map_derivation.py:642` (takes `[0]` only). **Unaffected.**

**Client - fails open, in the wrong direction. This is the blocker.**

| # | site | what it does | unknown token |
|---|---|---|---|
| 4 | `map_editor.js:10355` | `alignApplied: align.origin !== 'identity'` | **TRUE** - reports "alignment applied" for a pair where no coordinate moved |
| 5 | `map_editor.js:10542` `overlayAlignChip` | `if (origin === 'identity')` -> chip `무보정`; **else** -> chip `정렬됨` | falls to the else -> the operator sees **"정렬됨"** on maps nothing was done to |
| 6 | `map_editor.js:10864` | forwards `alignApplied` | inherits #4 |

Both are literal tests against the string `identity`, and both are **negative** tests, so every
new token that starts with `identity` reads as "not identity" and therefore as "aligned". The
shipped bundle has it too - `client2/dist/assets/map_editor-Dcw94L1Y.js` contains both
`origin!==\`identity` and `origin:...?\`identity`, so this is in the operator's hands today, not
just in source.

**Ordering constraint that follows, and it is not negotiable:** the client change lands in the
same round as the server change, or **before** it. A server-first split makes the editor claim
`정렬됨` on 71,126 pairs where nothing moved - which is a *worse* false statement than the silence
it replaces, and it is the exact failure class (I4 / screen-perfect-values-wrong) this round
exists to close. The safe client predicate is an explicit membership test against the three
identity tokens, not `!== 'identity'` and not a `startsWith` - a prefix test would quietly absorb
any future `identity_*` token without anyone choosing to.

**Tests pinning the literal** (these are the guard that the split does not silently reclassify,
and they must be updated deliberately): `server/tests/test_map_overlay.py:186, 201, 492` assert
`align_applied["origin"] == "identity"`. Assertions against `"derived"` (`:178, 245, 272, 454,
556, 579, 594, 887, 896, 1260`) are unaffected.

**Contract coverage: zero.** `contracts/map_seam/vectors.json` has **no vector carrying an
`origin` field** - the only `origin` hits in that directory are the English words "originate" and
"original" in prose. So nothing today would catch either the token drift or the client's
fail-open. Confirmed as the lead described. A pin for this needs, at minimum: one vector per
identity token asserting the client's rendered chip, and one vector asserting that an unrecognised
token renders as *unaligned*, not as aligned.

### 6.5 What I did not do

Per the ruling, the split is **not implemented**. This section is the pre-change census the
ruling requires, and stage A stops here.
