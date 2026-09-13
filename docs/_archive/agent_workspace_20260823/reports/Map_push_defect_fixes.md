# M5 fix round — I1 and I3 are NOT live defects. Nothing was fixed, because nothing is broken.

**Author**: map-pm · **Date**: 2026-08-04 · **Base**: `cb184a7` · **Commit**: NONE (no product
change was warranted) · **`client2/src/map_editor.js` SHA**: `a77378e6…` before and after —
byte-identical to the SHA recorded at the end of the scoring round.

---

## 0. Verdict, up front

**Both I1 and I3 are already green in shipped product code.** They are *mutation labels* from
`effort_instrument_harness.mjs`'s group G, not live defects. The scoring round (`ef153c0`) that
this fix round was premised on is exactly what proves it: G1/G2/G3 and G9 are assertions that
pass against the real source and go red when the named defect is injected. That is the standing
red/green pair, and the shipped source sits on the **green** side of both.

| defect as boarded | what the source actually does today | assertion | shipped source |
|---|---|---|---|
| **I1** gate 4's log-shaped BLOCK never refuses | it **does** refuse — 0 requests, 1 alert, **0 confirms**, before any dialog | `G1`=0, `G2`=1, `G3`=0 | **GREEN** |
| **I3** the pushed `wafer_map_metadata` loses `grid_start_x/y` | it **does** carry them — `grid_start_x: 3, grid_start_y: -2` on the wire | `G9` (field-by-field) | **GREEN** |

I did not write one byte of product code. Making gate 4 "start refusing" when it already
refuses would have meant inventing a *new* refusal — a behaviour change with a real blast
radius (the brief itself asks for the newly-blocked population) on a false premise. That is the
worst outcome this round could have produced, and the brief's own instruction — *"establish what
the gate is FOR: which push must it refuse, and **what happens today instead**"* — is the
question that caught it.

### 0a. Where the premise came from

`Map_push_path_scoring.md` §2d says *"**I1 and I3 remain real defects** and are untouched — they
now have executable specifications waiting for their own round (§5)."* That sentence is wrong,
and it is mine. §5 of that report is the **map-key spelling** finding (K4/K5 + the `NaN`/NULL
hole) — which *is* a live defect and *is* boarded separately as **M6**. §2d appears to be a
drafting collision between the mutation labels (I1…I5b) and the §5 findings; the surrounding
sentences of the same section (*"All nine are scored without touching product code"*) and the
whole of §2 (*"the green side of every pair is the harness's own headline run"*) say the
opposite. **Proposed correction to that report is in §6.**

---

## 1. I1 — what gate 4 is FOR, and what happens today

### 1a. Which push it must refuse

A ⚡ Push is `replace_map`: every row in the map-key scope is deleted, then rewritten from rows
carrying only `(map keys, x, y, val)`. A target that has data columns outside that contract
loses them on every replaced row. Gate 4 refuses exactly those targets.

The decision half (`logShapedPushDecision` / `getUnprotectedPushColumns`) is scored by
`push_gate_harness.mjs` (15 assertions, green) against the real served schema shapes:

```
dt_log        bound tx/ty/core_lot -> extras ['dt_id','eventtime','core_slot','cx','cy','dt_eqp']  -> block
eds_fail_map  bound x/y/val        -> extras ['metro_eqp']                                          -> block
bonding_map   bound x/y/leg        -> extras []   (pkg_id survives via composite_key_source)        -> clean
dt_map        bound x/y/val        -> extras []                                                     -> clean
qa_ovl_txy    bound tx/ty/val      -> extras []                                                     -> clean
map_push_ok: true  -> 'confirm'    | false / "true" (string) / absent -> 'block'  (strict === true)
```

### 1b. What happens today — measured, not read

The action half is `confirmLogShapedPushTarget`, scored by group G of
`effort_instrument_harness.mjs`. With `logShapedPushDecision` returning `{mode:'block'}`:

```
G1  log.requests.length  = 0    nothing reached the server
G2  log.alerts.length    = 1    the refusal did speak
G3  log.confirms.length  = 0    gate 4 is FIRST — the operator answered nothing
```

All three green on the shipped source. **The gate stops the push.** The `dt_log` near-miss the
source records is refused today, and it is refused *before* the Clean Replace confirm, which is
the ordering claim `G3` exists to pin.

### 1c. 🔴 Newly-blocked population: **ZERO**

No product behaviour changed, so no push that succeeds today would newly be blocked. The
population the brief asked me to enumerate and clear is empty **by construction**, not by
argument.

For completeness, today's live gate-4 population, read from `server/config/table_config.json`
(read-only; not modified): **7 map-declared tables, and not one of them declares
`map_push_ok`** —

```
core_wafer_map · dt_log · dt_map · bonding_log · bonding_map · map_split_registry · valid_die_ref
   map_push_ok = undefined on all 7  ->  no table is in 'confirm' mode today
```

So every one of them is in `clean` or `block`, decided purely by whether it carries unprotected
data columns. `dt_log` and `bonding_log` are the log-shaped ones; they are blocked today and
must stay blocked.

### 1d. One thing I checked and it is NOT a hole

`getUnprotectedPushColumns(null, …)` and `({}, …)` both answer `[]` → `mode: 'clean'`, so a
**failed schema read degrades gate 4 to permissive** (`push_gate_harness` [8] records this
deliberately as "no crash, empty answer"). That reads like invariant ③ ("서버 상태를 모르면
쓰지도 지우지도 않는다"), so I traced it: with `tableSchema` null or `{}`, `pushMapData` throws
at `client2/src/map_editor.js:5347` (`tableSchema.column_types[xCol]`) — **before** the try
block, before any `fetch`. No request is issued and nothing is deleted. Not a destruction path,
and not in this round's scope. Recorded, not fixed.

---

## 2. I3 — the pushed record, and whether `startxy_probe` should have caught it

### 2a. What is on the wire today

`buildPushGridMetadata` (`client2/src/map_editor.js:5773`) writes `grid_start_x: startX,
grid_start_y: startY,` and `G9` reads the record **back out of the request body** and compares
it **field by field as a mapping** (key order is not behaviour):

```
G9 = {grid_cols:11, grid_rows:9, grid_start_x:3, grid_start_y:-2, grid_y_invert:true,
      phys_chip_x:2, phys_chip_y:3, phys_edge_margin:1, phys_offset_x:0.5,
      phys_offset_y:0.25, phys_wafer_dia:20, rotation:90, side:"back"}
```

Green. The frame origin survives the push.

### 2b. 🔴 The second finding: `startxy_probe` could NOT have caught it, and neither could the one harness that names the producer

Asked and **measured**, not argued. I copied the source into a scratch tree, injected I3
(`grid_start_x/y := 0`) into the product file *in the scratch tree only*, and ran the two
harnesses that own this axis against the defective source:

```
startxy_probe.mjs           <I3-injected src>   ->  PASS -- 29 passed, 0 failed   exit 0   ESCAPED
standard_frame_origin_harness.mjs (scratch)     ->  ✓ baseline: 19 assertions, 0 failure(s)  ESCAPED
  ...and its own --mutate suite: 7 declared · 7 applied · 0 did not apply · 0 undetected — all
  seven of ITS defects still caught. The suite is healthy; I3 is simply outside its axis.
```

**Should `startxy_probe` have caught it? No — and that is the finding.** Its own header states
its scope: *"on map **load** the DECLARED `grid_start_x/y` must be preserved"*. Cases A–F all
execute `loadExistingMap`. It guards the **read** direction of the `grid_start_x/y` axis. I3 is
the **write** direction of the same axis. The probe was built for `aee05b1` ("a failed spec read
is not a missing declaration") and it does that job correctly.

`standard_frame_origin_harness` is the more interesting escape, and it is a real coverage
finding: it **cites `buildPushGridMetadata` by name in a comment** (line 312, *"`gridMeta` inside
`buildPushGridMetadata`, which `pushMapData` calls"*) but at line 319 it **re-types the record
in its own fixture**:

```js
grid_start_x: parseInt(el.gridStartX.value, 10), grid_start_y: parseInt(el.gridStartY.value, 10),
```

That is a second implementation of the thing under test, so the harness compares its own copy
against itself and the producer can be zeroed underneath it without a number moving. It is
the same shape as R6 §2a's INV-F2 hostage, arrived at from the other side.

**Consequence, stated rather than quietly patched**: the `grid_start_x/y` axis had **two**
guards, both on the read side, and the write side had none until `G9` was added last round.
`G9` is now the only assertion in the repository that can see this defect — confirmed by R6
§7a (nine suites + six contracts, all green against injected I3) and re-confirmed here against
`startxy_probe` and `standard_frame_origin` individually. **I did not extend either harness.**
Whether `standard_frame_origin` should stop re-typing the record and call the real producer is a
coverage decision for the board, not a fix-round edit.

---

## 3. Red/green in BOTH directions, per defect — executed, not asserted

The brief asks for "the fix's assertion green, and red again when the fix is reverted in a
scratch copy". With no fix, the equivalent and strictly stronger experiment is: **put each
defect into the product source in a scratch copy and show the oracle goes red** — i.e. prove the
shipped source is on the green side because of behaviour, not because the assertion is blind.

Scratch tree: `…/scratchpad/m5/client2/{src,tests}` — copies of `map_editor.js`, `map_key.js`,
`effort_instrument_harness.mjs`, `standard_frame_origin_harness.mjs`. **No repository file was
written at any point**; verified after by `git hash-object client2/src/map_editor.js` =
`a77378e66014718bcccca271202f519ee26982ef` (unchanged) and `git status --porcelain client2/`
(empty).

### I1

| direction | source | result |
|---|---|---|
| **GREEN** (shipped) | `client2/src/map_editor.js` as committed | `G1`=0 `G2`=1 `G3`=0 · `PASS — 71 passed, 0 failed` · exit 0 |
| **RED** (defect injected) | scratch copy, gate 4's `return false;` deleted | `FAIL G1 expected 0 actual 2` · `FAIL G3 expected 0 actual 1` · `FAIL — 66 passed, 5 failed` · exit 1 |

The red run also prints `FAIL I1 …: mutation did not apply (source drifted)` — the harness's own
loud signal that the defect it wanted to inject was **already there**. Two independent alarms
for the same condition.

### I3

| direction | source | result |
|---|---|---|
| **GREEN** (shipped) | as committed | `G9` = the full record incl. `grid_start_x:3, grid_start_y:-2` · `PASS — 71 passed, 0 failed` |
| **RED** (defect injected) | scratch copy, `grid_start_x/y := 0` | `FAIL G9 … actual {…,"grid_start_x":0,"grid_start_y":0,…}` · `FAIL — 67 passed, 4 failed` · exit 1 |

Both red runs differ from green in exactly the fields the defect touches; every other G, A, B and
K value is unchanged, so the assertions are about the defect and not about the file.

---

## 4. Control escape — both controls still escape

From the clean run of `effort_instrument_harness.mjs` (unchanged this round, since no assertion
and no product line was edited):

```
ok  C1 consistent rename of a pushMapData local (metaRead -> metaReadResult) :: group A escapes
ok  C1 …                                                                    :: group B escapes
ok  C1 …                                                                    :: group G escapes
ok  C1 …                                                                    :: group K escapes
ok  C2 comment-only edit inside the write path                              :: groups A/B/G/K escape
```

**8/8 escape.** No assertion drifted into pinning text — nothing was touched that could have
caused drift.

🔴 One observation worth recording: in the **I1-injected** scratch run, `C1` and `C2` reported
`group G escapes` as **FAIL**. That is correct and not a control failure — the controls compare
group G against the *baseline* group G, and injecting I1 moved the baseline (`G1` 0→2, `G3` 0→1)
underneath them. A control mutant's escape is only meaningful relative to a green baseline;
against a defective one it reports the baseline's defect. Useful to know before anyone reads a
control FAIL as text-pinning.

---

## 5. Oracles — before and after (identical, because nothing changed)

```
node client2/scripts/check_harnesses.mjs
  23 harnesses ― 19 gated, 4 on the known-red debt list (4 still red, 0 recovered).
  ✓ every gated harness is green.                                   exit 0
  effort_instrument_harness.mjs  (ran 71, failed 0)   — matches its FLOORS entry of 71
node client2/scripts/check_contracts.mjs
  ✓ 6 contracts, no divergence.                                     exit 0
```

Baseline matched exactly: **23 / 19 gated green / 4 known-red / exit 0, contracts 6/6.** No
floor rose, none dropped, none was edited.

**Stored coordinates: 0 cells moved — and here the narrow oracle is honest for once.** No mask
was redrawn and no frame reframed, because no line executed differently: the product source is
byte-identical (`a77378e6…`). This is the one case where "0 cells moved" carries its full
meaning rather than its usual blind spot.

---

## 6. Constraints honoured, and what was NOT touched

- **No product code changed. No commit.** There is nothing to commit: `git status --porcelain
  client2/` is empty. `git add` was never invoked.
- **M6 not touched** — the two map-key spellings and the `L1_NaN` collision are untouched;
  group K still records them as a defect (K4/K5 diverge, on the record, green harness).
  **M4 not touched.**
- **Dead module state (`tables`, `isMouseDown`) not touched.**
- No refactoring, cleanup or rename carried along.
- `npm run build` **not** run; `client2/dist/**` **not** touched; `docs/**` **not** touched;
  `server/**` **not** written (only `server/config/table_config.json` and
  `server/tests/test_schema_map_push_ok.py` were **read**, for §1a/§1c).
- No DB access of any kind, no browser session, no server process, no config modified, no file
  deleted. Scratch tree created under the session scratchpad and **removed**. Not pushed.

### 6a. Correction owed to a report, not to a doc

`agent_workspace/reports/Map_push_path_scoring.md` §2d — the sentence *"I1 and I3 remain real
defects"* is false and produced this round's premise. Suggested replacement, for the lead PM to
apply or to have me apply:

> All nine are scored without touching product code, and all nine are green on the shipped
> source — they are executable specifications of defects that are **not** present. The two live
> findings this round produced are in §5 (the two map-key spellings, and the `NaN`/NULL hole),
> and they are what needs its own round.

---

## 7. Doc update points — listed for the doc lanes, not edited

Looked up by **code path** in `docs/process/DOC_OWNERSHIP.md`: `client2/src/map_editor.js` hits
rows **57** (웨이퍼 맵 에디터 → `map_editor/README.md`, `spec/MAP_EDITOR_SPEC.md` §1–§4), **74**
(범용 맵 오버레이 → `MAP_EDITOR_SPEC.md` §5) and **75** (`wafer_map_metadata` →
`MAP_EDITOR_SPEC.md` §5.0).

No product code changed, so every point carries forward unchanged from
`Map_push_path_scoring.md` §8: `PRIMITIVES.md:316`, `PRIMITIVES.md:623` (gate 4 — the acting
half is `confirmLogShapedPushTarget`, and that action is now scored by G1–G3/G19),
`MAP_EDITOR_SPEC.md:774`, `MAP_EDITOR_SPEC.md` §5.0 (the producer `buildPushGridMetadata` now
has a field-by-field oracle, `G9`), `CODE_MAP.md`.

**One point this round adds** — `MAP_EDITOR_SPEC.md` §5.0 and/or `map_editor/README.md`: the
`grid_start_x/y` axis is guarded on the **read** side by `startxy_probe` and on the **write**
side by `G9` only, and `standard_frame_origin_harness` re-types the record rather than executing
its producer. Worth saying where the guards are, since §5.0 is the section that declares
`wafer_map_metadata` the only alignment basis.

---

## 8. UI complexity budget

**Net added controls: 0. Net removed: 0.** No file was opened for writing. No panel, mode,
modal, confirm, toast or user-visible string changed. The read path is frictionless and the
write path asks exactly the questions it asked. **This round is invisible to the user — and,
because it changed nothing, it is invisible to the data as well.**

---

## 9. Proposed memory-lesson candidates (for lead-PM review — not self-applied)

1. **A green assertion is a claim about the product, and it outranks any prose — including my
   own.** M5 was boarded from one sentence in my own report (§2d) that contradicted the same
   report's §2 and the harness's own headline. Before opening a fix round on a defect that has
   an assertion, **run the assertion first**: if it is green, the defect is not live and the
   round is a misdiagnosis. Thirty seconds of `node …/check_harnesses.mjs` beats any amount of
   re-reading. Corollary: **a mutation label is not a defect name.** `I1`/`I3` name defects that
   were *injected to score the assertion*, and a report that lists them in a table headed
   "defect re-injected" can be misread as a defect register one section later.
2. **"Fix" rounds must be able to end in "nothing was broken."** Had I treated the brief as a
   mandate, I would have made gate 4 refuse pushes it correctly allows today — a real blast
   radius manufactured from a false premise, on the one gate whose failure mode is data
   destruction. The brief's own 🔴 instruction (*"establish what the gate is FOR … and what
   happens today instead"*) is what made the exit visible; **that question belongs in every fix
   brief**, and the answer "it already does that" must be an acceptable one.
3. **Guard both directions of an axis, and check which direction each guard faces.** The
   `grid_start_x/y` axis had two harnesses on it and **both faced the read direction**;
   `startxy_probe` guards the load, `standard_frame_origin` re-types the record instead of
   executing its producer. The write side was unguarded until `G9`. **When a probe exists
   "because of" a past incident, read its header for the direction it guards, not just the
   field name it mentions** — a probe named for a field can still be blind to half of it.
4. **A control mutant's escape is only meaningful against a green baseline.** With I1 injected,
   both controls reported `group G escapes` as FAIL — not because they were caught, but because
   the baseline they compare against had moved. **Never read a control FAIL as assertion drift
   without first confirming the baseline is green.**
