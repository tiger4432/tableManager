# Map request 1-c -- overlay markers coloured by the overlay map's own value (board N2)

Worktree: `.claude/worktrees/agent-a5b1bf56eed7611e3` (branch `main`, base `5d35337`).
Files touched: `client2/src/map_editor.js`, `client2/tests/overlay_value_colour_harness.mjs` (new),
`client2/scripts/check_harnesses.mjs` (one floor entry). No `dist/`, no `server/`, no `docs/`, no build.

---

## 1. What changed

Before: the overlay layer painted **one flat colour per layer**. A user could see how many
overlapping chips there were and where, but not what any of them said.

After: each dot's **fill** is the colour the legend declares for **that dot's own value**. The
dot's **ring** stays the layer colour, so which overlay a dot belongs to is still readable.

Five new functions, all in the overlay/legend rendering region of `map_editor.js`:

| symbol | job |
|---|---|
| `legendColorForValue(val)` | value -> colour, or `null` |
| `overlayMarkerFill(list)` | the fill for one dot; `null` unless there is exactly one value |
| `paintOverlayDot(ctx, cx, cy, rad, fill, ringColor)` | halo + fill + layer ring |
| `overlayUnlistedValues(o)` | the layer's values the legend does not declare |
| `overlayLegendChip(o)` | the row chip that names them |

Plus three call-site edits: the two branches of `drawOverlayMarkers`, one chip slot in
`renderOverlayList`, and one guarded `renderOverlayList()` call at the top of
`renderLegendTable` (so the chip recounts when the user edits the legend).

## 2. Where the colour comes from

`legendColorForValue` consults, in order:

1. **the open map's own `legend` row** -- literally the colour the legend table on screen is
   showing right now; those rows are this map's `map_split_registry` rows;
2. **the served `map_overlay_config.default_legend`**, via the existing `declaredLegendRow()`;
3. otherwise **`null`**.

There is no third source. `pickUnusedColor()` and `LEGEND_PALETTE` are deliberately **not**
reachable from this path -- those invent a colour, which would dress an undeclared value in a
confident colour (screen fine, meaning wrong). A source-text assertion (A10g) holds that.

**Precedence is observable and asserted.** The fixture declares value `1` in *both* layers with
*different* colours (`#10b981` in the map legend, `#000000` in the served default). If the
served row won, the canvas would contradict the legend table the user is looking at. A3 fails
if that happens; equal colours would have made the question unanswerable.

Existing primitives reused rather than rebuilt: `declaredLegendRow` (U6, the one declared-row
lookup), the `legend` array itself, the `.ov-chip.warn` class, and `escapeHtmlAttr`. No new
palette, no new config key, no new endpoint, no new CSS.

## 3. What an unlisted value renders as

**No fill at all.** Not the layer colour, not a grey, not a palette entry -- `fillStyle` is
never even assigned (A7g: assigning it is one edit away from filling it). The dot is drawn as
a white halo plus a layer-colour ring, so it is still visible and still identifiable as
belonging to its layer, and its emptiness is the honest statement "nobody declared a colour
for this value".

In words, the layer's row gains one chip: **`범례 밖 N종`**, whose tooltip names up to 8 of the
values and points at the legend panel. It is **recounted from the live legend on every render**
-- add the value to the legend and the chip shrinks on the spot (A8e/A8f/A8g). A count captured
at add time would go quietly stale, and a stale count is indistinguishable from a defect.

## 4. How the N:1 case is presented (the ruling that must not regress)

A solid dot has **exactly one meaning**: one source chip, whose value the legend declares. That
gives one clean rule for the fill:

- **roomy N:1** (target cell large enough): unchanged from this round's predecessor -- every
  source chip gets **its own dot at its own in-chip position**, and now **its own value's
  colour**. Nothing is merged, nothing is picked.
- **N:1 that cannot be spread** (cell too small): the single fallback dot is **hollow**.
  Filling it with `list[0]`'s colour would be exactly the representative the user rejected --
  it discards the rest while looking confident. This is asserted even when the several items
  *agree* (A6e): the fallback dot exists because the cell is too small to show them apart, so a
  solid dot there would read as "one source chip", which is false.

The two reasons a dot can be hollow are told apart **in words**, not in the dot: the
`최대 N:1` / `중복 좌표` chip (pre-existing) speaks for the several-values case, the new
`범례 밖 N종` chip for the undeclared-value case.

**The mm remainder was not consumed.** `it.rx` / `it.ry` still drive the in-chip placement in
the roomy branch; assertion A10d and a dedicated mutation fail if that path stops using them.
`waferMmToDieCell` and `seatWaferMmInFrame` were not touched at all.

## 5. Evidence -- the renderer executed, per dot

`drawOverlayMarkers` driven over a recording canvas with two layers. Legend: `1`->`#10b981`,
`F`->`#ef4444`; served default: `R`->`#8b5cf6`; `ZZ9` declared by nobody. Layer 1 ring
`#ef4444`, layer 2 ring `#3b82f6`.

```
ROOMY N:1 (cell D, 4 source chips, cellW=cellH=40)
   at (105.3,232) r=4  fill=#10b981      rings=[#ffffff@1.6, #ef4444@0.8]
   at (129.3,212) r=4  fill=#ef4444      rings=[#ffffff@1.6, #ef4444@0.8]
   at (105.3,212) r=4  fill=#8b5cf6      rings=[#ffffff@1.6, #ef4444@0.8]
   at (129.3,232) r=4  fill=NONE (hollow) rings=[#ffffff@1.6, #ef4444@0.8]
      -> 4 chips, 4 distinct in-chip positions, 4 distinct answers, one honest blank.

1:1, TWO layers on the same cell A
   at (133.3,206.7) fill=#10b981  rings=[#ffffff@1.6, #ef4444@0.8]   layer 1, value '1'
   at (121.4,206.7) fill=#ef4444  rings=[#ffffff@1.6, #3b82f6@0.8]   layer 2, value 'F'
      -> different values AND different layers, both readable.

1:1, same cell C, one undeclared and one declared
   at (133.3,206.7) fill=NONE (hollow)  rings=[..., #ef4444@0.8]     layer 1, value 'ZZ9'
   at (121.4,206.7) fill=#10b981        rings=[..., #3b82f6@0.8]     layer 2, value '1'

1:1, value declared ONLY by the served default_legend (cell B)
   at (133.3,206.7) fill=#8b5cf6  rings=[#ffffff@1.6, #ef4444@0.8]

N:1 too small to spread (cell E, 2 chips, cellW=cellH=9)
   at (106,203) r=1.5  fill=NONE (hollow)  rings=[#ffffff@1.6, #ef4444@0.8]
      -> no representative was chosen.
```

The overlay row's `.ov-dot` swatch remains the flat layer colour, which is now exactly right:
it is the layer's identity, and it matches the ring on the canvas.

## 6. Complexity budget

| | count |
|---|---|
| new screens / modes / modals | **0** |
| new controls added (buttons, inputs, selects, toggles) | **0** |
| controls removed | 0 |
| **net control count** | **0** |
| new status chips (non-interactive, existing `.ov-chip.warn` class) | 1, and only when there is something to say |
| new CSS rules | 0 |
| confirmations added to a read path | 0 |

No toggle was added and none is argued for. The colouring is not a mode: the dot answers the
question the user already asked by pressing `[+ 겹치기]`, and the previous flat colour is still
present as the ring, so nothing was taken away that a toggle would need to give back.
A11/A11b assert the overlay row still has exactly 3 buttons and no input.

## 7. Gates -- before / after

| | before (this worktree, untouched) | after |
|---|---|---|
| harnesses discovered | 23 | **24** |
| gated | 19 | **20** |
| known-red | 4 | 4 |
| gated green | 18 | **19** |
| BLOCKING | 1 (`undeclared_identifier_harness.mjs`) | 1 (same one) |
| exit code | 1 | 1 |
| contracts | 6/6, no divergence | **6/6, no divergence** |

After the change the runner prints `24 harnesses -- 20 gated, 4 on the known-red debt list`,
which is the briefed baseline shape.

**About the one BLOCKING harness.** `undeclared_identifier_harness.mjs` was **already
blocking on the untouched worktree before I edited anything** -- it fails with
`Cannot find package 'rolldown'` because a git worktree has no `node_modules` (the brief
forbids building here). It is an environment artifact, not a regression, and its floor was not
touched. Because it is the one harness that would have caught an undeclared identifier, I
substituted an explicit parse check: `node --check` on the edited module -> `PARSE OK`, and
every identifier the new code references (`legend`, `declaredLegendRow`, `escapeHtmlAttr`,
`overlayLayers`, `renderOverlayList`) is a pre-existing module-level declaration.
**The lead PM should re-run this gate in the main checkout, where `rolldown` resolves.**

**No floor dropped and none was edited downward.** One floor was *added*:
`overlay_value_colour_harness.mjs` at 54, the count it reports on the commit that introduces
it (the runner explicitly asks for this on a newly discovered harness).

`overlay_wafer_mm_harness.mjs` -- the harness that scores this exact area -- is unchanged at
**ran 69, failed 0, 21/21 mutations applied and caught**. I read all 21 of its injected
mutations before editing; two of them (`representative value chosen for a multi-value cell`,
`remainder thrown away`) anchor on lines inside `reseatOverlayLayer` and `waferMmToDieCell`
that I therefore did **not** touch, and all 21 still apply.

## 8. The new harness

`client2/tests/overlay_value_colour_harness.mjs` -- **54 assertions, 13/13 mutations caught.**

Both required paths are fixtures, with the discrimination axes live:

- value in the **map legend** (A1, A1b) and declared **only in the served default** (A2);
- the same value declared by **both with different colours**, so precedence is observable (A3);
- values declared by **neither** (A4), cross-checked against both palettes parsed out of the
  source so a future palette colour cannot slip past (A4b/A4c);
- a numeric value finding its string row (A1c) -- stored values arrive typed by the column;
- multi-item cells with **different** values (A6d) and with **identical** values (A6e);
- the painter executed against a recording canvas: filled dot, hollow dot, halo, layer ring
  (A7-A7i);
- freshness of the unlisted set across a legend edit and its undo (A8e-A8g);
- wiring: both marker branches go through the painter and each painted dot asks the legend
  (A10/A10b), the renderer sets no fill of its own (A10c), the remainder is still used (A10d),
  the lookup never reaches for a palette (A10g), and the legend-edit refresh is guarded on
  `overlayLayers`, not on a constant (A10i);
- the complexity budget itself (A11/A11b).

**The self-check that matters** is the mutation sweep -- every defect put back and confirmed
to turn the harness red, including the two that would look like *improvements* on screen:
`an undeclared value is given an invented colour` and `a representative value is chosen for a
multi-source dot`. One mutation initially **SURVIVED** (`if (false) renderOverlayList();` left
the call text in place and satisfied a naive presence check); the assertion was tightened to
require the `overlayLayers` guard, which is what actually holds the property.

One implementation detail exists solely to keep the sweep honest: the local in
`legendColorForValue` is named `declared`, not `dr`, because `autoAddLegendValue` holds a
byte-identical `const dr = declaredLegendRow(v);` line **earlier in the file** -- a
first-match string replacement would have landed there instead and the mutation would have
passed while measuring nothing. That is a silent hole, and it is commented at the site.

## 9. Reported, not fixed

1. **Board item 18 is stale.** The brief warns that `currentGeomSignature()` omits `phys_*`.
   On this base it **does** include all six (`phys_wafer_dia`, `chip_x`, `chip_y`, `offset_x`,
   `offset_y`, `edge_margin`) -- `client2/src/map_editor.js:9134` onward -- and the comment
   above it records the fix as `[C7]`. Nothing I did widens or narrows it. The board item
   should be closed or re-scoped.
2. **`undeclared_identifier_harness.mjs` cannot run in any worktree.** It imports `rolldown`
   from `node_modules`, which a worktree does not have, so every worktree-based lane will see
   the gate exit 1 for a reason unrelated to its change. Worth a guard that reports
   "unavailable in this tree" rather than the dead-harness verdict, so a real regression is
   not camouflaged by a permanent red. (Not touched -- it is a gate, not my domain.)
3. **The `KNOWN_RED`/`FLOORS` numbers in `check_harnesses.mjs` are the main checkout's.** The
   worktree matched them exactly after this change, so no drift is implied; noting only that
   the 24/20/4 figures were confirmed here, not assumed.

## 10. Living documents to update (doc-keeper's call, not touched)

Rows found by code path in `docs/process/DOC_OWNERSHIP.md`:

- row **"범용 맵 오버레이(맵 인프라)"** (`client2/src/map_editor.js` overlay layer) ->
  **`docs/spec/MAP_EDITOR_SPEC.md` §5** (alignment contract / client pipeline §5.1). §5 now
  needs the marker's colour rule stated next to the placement rule: *the fill is the legend
  colour of the value; unfilled means "this dot does not name a single declared colour"; the
  ring is the layer.* Without it the next reader will assume the flat-colour behaviour.
- row **"웨이퍼 맵 에디터"** -> **`docs/map_editor/README.md`**, for the operator-visible half:
  the new `범례 밖 N종` chip and what a hollow dot means.
- row **"DOE 저장 분해도"** -> **`docs/spec/MAP_EDITOR_SPEC.md` §6** mentions the legend as the
  DOE row; it is now also the overlay's colour authority. One cross-reference, no contract
  change -- nothing about what is *stored* moved.
- `docs/architecture/PRIMITIVES.md` §"config 선언 + 기존 엔드포인트 서빙" (U6) already names
  `get_default_legend` / `declaredLegendRow`; it gains one consumer (overlay marker colour).
  Worth adding so the next person looking for "value -> colour" finds the one implementation
  instead of writing a second.

`docs/spec/DOE_STORAGE_MAP.md` is **not** affected -- nothing about storage changed, and that
document is marked as the retired 3-table model anyway.

## 11. Proposed lessons for `agent_workspace/memory/map-pm.md` (proposal only)

1. **A mutation that replaces a string lands on the FIRST match in the file, which may be a
   different function.** Before relying on a mutation to score a line, confirm the pattern is
   unique in the whole source -- `const dr = declaredLegendRow(v);` existed twice, and the
   mutation would have silently scored `autoAddLegendValue` instead. Symptom: a mutation that
   is CAUGHT for the wrong reason, which no counter distinguishes from a real catch.
2. **A presence check is not a wiring check.** `if (false) f();` still contains `f(`. Assert
   the *guard*, not the call -- this round produced exactly one SURVIVED mutation and that was
   the cause.
3. **In a worktree, record which gate failures are environment, not code, BEFORE editing.**
   The baseline here already had one BLOCKING harness (`rolldown` absent without
   `node_modules`). Measuring it first is what turns "the gate is red" into "the gate is red
   for the same reason it was red an hour ago".
