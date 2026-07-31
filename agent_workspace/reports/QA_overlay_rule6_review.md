# QA — adversarial review: map rule 6 overlay (WF-internal physical position), client-only

**Scope:** uncommitted working tree · `client2/src/map_editor.js` (+355/-79 in diffstat terms),
`client2/tests/overlay_wafer_mm_harness.mjs` (new), `client2/tests/geometry_origin_reseat_harness.mjs`,
`client2/tests/valid_die_authoring_harness.mjs` (also modified — not in the brief's file list).
**Tier:** T2. **Reviewer stance:** find defects, not approve.
**Constraints honoured:** no file edited, no build run, DB read-only (SELECT + `information_schema` only),
nothing staged or committed. Every number below was re-derived by me; none is quoted from the
implementer's report, the board, or a commit message.

---

## 1. Verdict

**GO-WITH-FIXES.**

The single highest-risk item in the brief — the pitch axis under rotation — is **correct**, and I
proved it discriminates rather than merely passing. But the round left a harness dead in a way its
own report says it fixed, and the refusal it installed to replace the deleted gate cannot fire for
the inputs it names.

---

## 2. Confirmed defects

### [HIGH] F1 — A third harness was disabled by the same dependency the report says it fixed twice

**`client2/tests/valid_die_frame_adoption_harness.mjs:79`**

```js
  'projectCellsToPhys', 'resolveValidDie',
```

`projectCellsToPhys` is now stated in terms of `projectCellsToWaferMm`, so slicing it without also
slicing the new function throws. Running it:

```
ReferenceError: projectCellsToWaferMm is not defined
    at Object.projectCellsToPhys (evalmachine.<anonymous>:712:3)
    at scoreAll (valid_die_frame_adoption_harness.mjs:424:33)
```

**Failure scenario.** The debt list (`client2/scripts/check_harnesses.mjs:52`) records this harness as
*"28 of 228 assertions fail — most are fixtures holding the pre-`da8f390` contract; under triage"*.
It now throws at `scoreAll` **before the first assertion executes**, so the ~200 assertions that were
green — origin-box and adoption-path coverage — run **zero times**. `check_harnesses.mjs` prints it as
"still red", the build stays green, and the coverage loss is invisible. The runner's own comment at
`:116` names this exact hazard. Report §2.6 states "two harnesses died with `ReferenceError`"; there
were **three**, and the third is masked by the debt list.

**Fix.** One line, identical to the two already applied:
`'projectCellsToWaferMm', 'projectCellsToPhys', 'resolveValidDie',` at `:79`.

---

### [HIGH] F2 — The replacement gate is dead for exactly the inputs it names

**`client2/src/map_editor.js:8984-8992`** (the `badPitch` refusal), depending on
**`client2/src/map_editor.js:1774-1781`** (`physNum`):

```js
function physNum(key, domEl, dflt) {
  ...
  const v = domEl ? parseFloat(domEl.value) : NaN;
  return v || dflt;          // 0 and NaN are falsy -> the default wins
}
```

`badPitch(rf) = !(rf.chipX > 0) || !(rf.chipY > 0)` is evaluated on `resolveFrame(...)`, i.e. **after**
the fallback. A pitch that is absent, empty, zero or unparseable can therefore never reach the gate as
a non-positive number. Measured (screen/target declares 15×10 mm):

| declared `phys_chip_x` | `frameFromMeta` | `resolveFrame` | refused? |
|---|---|---|---|
| absent | `undefined` | **15** (the target's screen pitch) | no |
| `0` | `0` | **2.5** (the hardcoded default — neither map's value) | no |
| `""` | `undefined` | 15 | no |
| no phys spec at all | `undefined` | 15 | no |
| `"abc"` | `undefined` | 15 | no |
| `1e9` | `1e9` | 1e9 | no |
| `-7` | `-7` | -7 | **yes** |

Only a **negative** pitch refuses. The error string names `phys_chip_x/phys_chip_y` "cannot be
established" — a state the code cannot reach for the realistic cases.

**Failure scenario A (the case the old gate caught).** Source metadata declares `grid_cols/rows =
42×59` and no physical spec; target is 20×30 @ 15×10 mm. Old code: refused (`align_unavailable`,
dims differ). New code: draws **2478 chips over 2436 cells, 1878 of them (75.8%) counted outside the
grid**, using a pitch the source never declared. The only signal is the `missingPhys` string inside a
`title=` tooltip on the align chip.

**Failure scenario B (fully silent).** Source metadata declares `phys_chip_x = 0` (same dims, same
everything else as the target). Resolved to **2.5 mm** — a constant from neither side. `missingPhys`
checks `=== undefined`, and `0 !== undefined`, so **no note fires at all**. Measured: **570 of 600
cells seat on the wrong target cell**, canvas draws cleanly.

Live data mitigates severity — 0 of 217 registered `wafer_map_metadata` rows have a missing, zero or
negative pitch — so this is latent, not live. It is HIGH because the round *deleted* a working
refusal and installed one that cannot fire, while the report asserts the precondition is checked.

**Fix.** Gate on the **declared** frame (`frameFromMeta` output) before the fallback runs, not on
`resolveFrame`'s post-fallback value — e.g. refuse when `srcFrame.chipX === undefined || !(srcFrame.chipX > 0)`
and the source has a registered metadata row. Alternatively give `physNum` a strict mode returning
`NaN` instead of `dflt`, and use it in the gate only.

---

### [MEDIUM] F3 — Deleting the dims gate removed the only bound on the source frame's grid dimensions

**`client2/src/map_editor.js:8843` (`addOverlayLayer`) never calls `frameDimError` (`:7739`).**

`frameDimError` exists for precisely this hazard — its own comment at `:7723-7727` says the cost
argument is *"`projectCellsToPhys` opens a frame window whose `getWaferBoundingBox` sweeps
`visualCols × visualRows`"* — and it is called at exactly one site, `:8129`, the valid-die reference
path. In the overlay path the old `cols/rows` equality gate was the de-facto bound (the target's dims
come from the screen controls, clamped 1..100). That gate is gone.

**Failure scenario.** A `wafer_map_metadata` row declares `grid_cols = grid_rows = 1024`. Adding that
overlay runs `projectCellsToWaferMm` → `getCanvasCellFromDb` → `getWaferBoundingBox`, a
1,048,576-iteration synchronous loop with no cancellation, on the UI thread. Measured with a **single**
source cell: **378 ms** (0 ms at 20×30). Live: 0 of 217 rows exceed 100×100, so latent.

**Fix.** `const dimErr = frameDimError(srcFrame); if (dimErr) return fail(..., 'align_unavailable');`
before projecting — reusing the function and wording that already exist.

---

### [MEDIUM] F4 — The tombstone check the report claims "still holds" fails

`docs/architecture/CODE_MAP.md:127` (§0 ⑫) prescribes a command and a pass condition:

```
git grep -nE "\b(const|let|var|function) mm\b|\bmm\s*[:=]" -- client2/src
# 선언 히트가 1건이라도 나오면 그것이 이 검사가 막으려는 것이다.
```

Running it against the working tree returns **`client2/src/map_editor.js:7811`**:

```js
        mm: (chipX > 0 && chipY > 0) ? { mmX: p.xCells * chipX, mmY: p.yCells * chipY } : null,
```

That matches `\bmm\s*[:=]`. The report's doc section states *"the tombstone in `CODE_MAP.md` §0 ⑫
that greps for a bare `mm` identifier still holds — I introduced no bare `mm`."* **False by the
tombstone's own command.**

The *intent* is arguably intact — the field genuinely is millimetres, which is the opposite of the
`getPhysicalCoords` confusion ⑫ was written to prevent. But leaving both the code and the check as
they are gives the check a permanent false positive, which is how a tripwire stops being read.

**Also pre-existing, and worth fixing in the same pass:** `client2/src/utils.js:8` is
`const mm = pad(date.getMinutes());` — a genuine *declaration* hit that is present at HEAD. §0 ⑫'s
claim *"현재 히트는 문자열/주석 2건뿐이고 선언은 0건이다"* was already false when written. Do not
let the fix chase only the new line.

**Fix.** Either rename the field (`waferMm`) or amend §0 ⑫ to a pattern that expresses the real rule
(a non-millimetre quantity named `mm`) and restate its baseline honestly.

---

### [MEDIUM] F5 — For the dominant live cross-pitch pair, `[↓ 가져오기]` becomes a 1.3% no-op

Re-derived from `wafer_map_metadata` (217 rows, `grid_metadata` JSON parsed): **162 maps are 7×7 mm @
40×40** and **23 are 15×15 mm @ 23×23** — the two most common specs, and precisely the pair rule 6
exists to overlay (the old dims gate refused it). Measured on those specs, wafer 300 mm / margin 3 mm:

| direction | chips | target cells | max fan-in | importable | skipped (`null`) |
|---|---|---|---|---|---|
| 7 mm 40×40 → 15 mm 23×23 | 1288 | 297 | **9** | **4** | **293 (98.7%)** |
| 15 mm 23×23 → 7 mm 40×40 | 261 | 261 | 1 | 261 | 0 |
| 11×13 mm 29×25 rot270 → 7 mm 40×40 | 425 | 425 | 1 | 425 | 0 |
| identity 7 mm 40×40 | 1288 | 1288 | 1 | 1288 | 0 |

`importOverlayToGrid` (`client2/src/map_editor.js:9243-9247`) skips every `null` cell. So on the main
cross-pitch case the import button applies **4 cells of 297** and toasts
`4셀 반영 · 293셀 건너뜀(한 칸에 여러 값)`.

This is the ruled behaviour (ⓒ "list them all", no representative) and it is **counted, not silent** —
so it is not a correctness defect. It is escalated because the report's framing (*"그 칸은 가져오기에서
제외됩니다"*) reads as an edge case when it is the main case, the `[↓]` button gives no pre-click
signal, and §1.6's escalation was about values being *unreadable*, not about import being ~0%.
The magnitude belongs on the board with the (a)/(b)/(c) options.

---

### [LOW] F6 — `layer.outside` counts grid membership; the sentence it prints promises import exclusion

`client2/src/map_editor.js:9120` counts `!canvasKeys.has(key)` and `:9131` prints
`격자 밖 N칩 — 웨이퍼 격자를 벗어나 **가져오기에서 제외됩니다**`. But `importOverlayToGrid` excludes on
`insideKeys` (`:9229-9239`) = canvas cells **inside the wafer circle**, a strictly smaller set.

**Measured, 7 mm 40×40 → 15 mm 23×23:** `layer.outside = 0` while **36 of 297** seated cells sit on
the canvas grid but outside the target's wafer circle. Import will skip them and report them as
`격자 밖`; the layer row says nothing.

The counter is **correct for the definition it chose** — I could not make it under-report on grid
membership (see §3.4). This is a wording defect, pre-existing in kind (the old `0 <= px < cols`
predicate was also grid-based), but it survived a round that rewrote the sentence.

---

### [LOW] F7 — Duplicate source coordinates now block import and are misdescribed

Measured: two source rows on the **same** `(x, y)`, identical pitch on both sides →
`count=2 cellCount=1 fanout=2 multiCells=1`, `cells` value `null`, cell **not importable**.
The pre-round `projectCellsToPhys` kept `"B"` (last-wins) and imported it.

The chip and `seatNote` say `타깃 셀이 더 굵어 한 칸이 최대 2칩을 받습니다` — **false**; the target is
the same pitch. An operator would be sent to the geometry panel to fix a data problem.

Likelihood is low: source rows are key-filtered (`buildKeyFilters`, `:8829`), so this needs duplicate
rows under one map key. Consider phrasing the note from what was measured (`N cells received several
values`) rather than from an assumed cause.

---

## 3. Hypotheses I tried to falsify and could not

Harnesses: `<scratchpad>/qa_attack.mjs` (139 assertions, 0 failures), `qa_attack2.mjs`, `qa_live.mjs`.
Same source-slicing + `node:vm` technique as the existing coordinate harnesses; read-only.

**3.1 — The pitch axis under rotation (the brief's #1 attack). SAFE, and the test discriminates.**
The server swaps `chip_x`/`chip_y` for rot 90/270 (`server/map_overlay.py:332-337`) because
`PhysicalWaferEngine` computes mm from **frame** indices. The client has no counterpart because
`getDieIndex` **de-rotates into physical axes before returning `xCells`** (`:1846-1857`), so `xCells`
already counts cells along physical x, whose spacing is the declared unrotated `chipX`. Verified, not
argued:
- 8 rot/side combos × 5 die indices, `chipX=7 chipY=5`, offsets `(1.3, -0.7)`, dims 42×59 (even × odd):
  **40/40 comparisons identical to 1e-9 mm.**
- Discrimination check: a deliberately swapped lattice moves the same die by >1 mm, so a pitch swap
  *would* have been caught (a fixture that cannot see the defect proves nothing).
- End-to-end at exactly 2× pitch, source **rot 90 / back** 7×5 mm 40×40 → target **rot 0 / front /
  invert-Y** 14×10 mm 20×20: 1600 chips → 400 cells, **every** cell fan-in 4, sub-lattice spacing
  exactly 7.000 mm on x and 5.000 mm on y, all `rx ∈ [0,14)`, `ry ∈ [0,10)`.

Live relevance: 31 of 217 maps have non-square pitch and 7 maps are rot 90/270, so this combination
is in production — it is the strongest positive result of the round.

**3.2 — The remainder: correct, not merely present. SAFE on all 8 combos.**
`waferMmToDieCell` (`:1975-1985`) keeps the division intact. For every rot/side and 5 die indices:
a die centre round-trips to its own index with `rx == chipX/2` and `ry == chipY/2`; a point 2 mm
along physical +x reads `rx == chipX/2 + 2`. Units are millimetres, range `[0, pitch)`.
**Sign convention on `back` and under rotation is inherited, not re-derived:** the mm space is a
function of the die index, which is already side- and rotation-invariant; the mirror appears only
where it should, in `seatAxes` (`:9107-9113`), which is read off `getCanvasCellFromDieIndex`
differences rather than from a second sign table.

**3.3 — `cells: null` consumers. SAFE — all four enumerated, none treats null as "empty".**
- `isOverlayLocked` `:85` — `.has(key)`: a fan-out cell still locks. ✓
- `recomputeActiveOverlays` `:7621` — `.size > 0`: null entries still count. ✓
- `importOverlayToGrid` guard `:9223` — `.size`. ✓
- `importOverlayToGrid` loop `:9243` — `if (val === null) { multi++; return; }` explicit. ✓
- `drawOverlayMarkers` `:7636` no longer reads `cells` at all; it reads `layer.items`. ✓
- `listOverlayLayers` `:9418` exports `count`/`visible`/`color` only — no value passes through.
No rendering, counting or export path skips a `null` and reports the cell as empty.

**3.4 — `outside` under-report. SAFE on grid membership.**
`canvasDieKeySet` produces exactly `cols × rows` keys (measured 400/400 on a 20×20 target — an empty
or partial set would make everything "outside"); a chip at die (500,500) is counted; an interior chip
is not. A chip cannot land on a canvas key without being on that canvas cell, so no under-report is
constructible. See F6 for the separate wording problem.

**3.5 — `projectCellsToPhys` semantics. SAFE — byte-equivalent behaviour.**
Scored against a hand-written copy of the pre-round body over a 20×30 rot-90/back fixture:
identical map size, **0 differing keys**. Insertion order is preserved through the array, so the
"last value wins" collision rule is unchanged.

**3.6 — `canvasDieKeyCache` invalidation. SAFE.**
Cache key is `frameAxesKey(resolveFrame(f))`, which carries every axis the built set depends on —
`cols`, `rows`, `rotation`, `side`, and `chipX/chipY/offsetX/offsetY` (which enter through
`getScreenShift`). No dependency is missing from the key, so a spec change cannot leave a stale set.
Cost is one full-grid sweep per distinct frame, cached, so six layers pay it once.

**3.7 — Control-surface delta. SAFE, re-derived.**
`git diff client2/src/map_editor.js` matching `document.getElementById|addEventListener|<button|
<input|<select|confirm\(`: **0 added, 0 removed**. `client2/map_editor.html` is unmodified.
The report's "net control delta: 0" holds.

**3.8 — Stored coordinates.** Not re-confirmed; the brief measured 0 of 600 moved and instructed me
not to spend the round on it.

---

## 4. Runtime verification still required

1. **Fan-out markers have never been drawn on a real canvas.** `drawOverlayMarkers:7639` gates the
   multi-dot branch on `cellW >= 10 && cellH >= 10`. At the live 15 mm/23×23 target with **fan-in 9**
   (F5), nine dots of radius `min(cellW,cellH)*0.10` land inside one cell. Whether that reads as
   "nine chips, here" or as noise is a pixel question no harness can answer — and it is exactly where
   the 293-cell import exclusion becomes legible or does not.
2. **Two fan-out layers on the same cell overlap.** `:7640-7658` does not advance `idx` in the roomy
   branch, so two layers draw at identical in-chip positions in different colours. Physically correct,
   visually unresolvable. Needs eyes.
3. **`renderOverlayList()` now runs inside the canvas render loop.** `syncOverlayGeometry:9174` is
   called from `renderGridCanvas:3386`, and `importOverlayToGrid:9228` calls `renderGridCanvas()`
   from inside a click handler on a row that `renderOverlayList` then rebuilds. Signature gating
   should make this one rebuild per spec edit, but a click-through is the only proof.
4. **`e2e` on the 7 mm → 15 mm pair** — the numbers in F5 are the ones the board should see rendered.

---

## 5. Documentation coherence

The report named **2 `DOC_OWNERSHIP` rows** (69 "범용 맵 오버레이", 53 "웨이퍼 맵 에디터") plus
`CODE_MAP §7` and `PROJECT_STATUS` line 84. Searching by **changed code path** instead of by the
implementer's list, the stale set is **7 files / 11 sites**:

| file:line | claim, now false | flagged? |
|---|---|---|
| `docs/spec/MAP_EDITOR_SPEC.md:590` | "소스·타깃의 `cols×rows`가 다르면 `align_unavailable`로 명시 거절합니다" — gate deleted | yes (as §5) |
| `docs/spec/MAP_EDITOR_SPEC.md:48` | row 6) "⏳ 클라에 mm 공간이 아직 없습니다" | yes |
| `docs/architecture/CODE_MAP.md:127` | §0 ⑫ tombstone — see **F4**, it now *fails* | claimed to hold |
| `docs/architecture/CODE_MAP.md:1452` | "`mm`은 의도적으로 비어 있다 — 이 파일에 밀리미터 공간은 없다" | partly (as "stale blob") |
| `docs/architecture/CODE_MAP.md:1700` | overlay pipeline "⑤ `cols×rows` 관문 → ⑥ `projectCellsToPhys`" | **no** |
| `docs/architecture/frontend.md:284` | "**`mm`은 일부러 비어 있다**" | **no** |
| `docs/architecture/frontend.md:290` | overlay row: "`projectCellsToPhys`로 투영한다" / "`syncOverlayGeometry`가 화면 규격 변경을 추종" — now `projectCellsToWaferMm` + `reseatOverlayLayer` | **no** |
| `docs/process/DOC_OWNERSHIP.md:54` | row 54 (M4) lists `map_editor.js`/`projectCellsToPhys` and asserts "**`mm`은 일부러 비어 있습니다**" — **this is a third owning row the report did not identify** | **no** |
| `docs/process/LEAD_PM_HANDOFF.md:118` | "**클라에는 그 공간이 없다**" | **no** |
| `docs/process/PROJECT_STATUS.md:91` | "**`mm`은 비워 뒀다** … 클라에는 그 공간이 없다" (lead-PM owned; only line 84 was flagged) | **no** |
| `docs/README.md:39` | "§1-bis … **`mm`은 일부러 비어 있다**" | **no** |

**Method note for the board.** `DOC_OWNERSHIP.md` row 54 owns `projectCellsToPhys` by name. That
symbol's body changed in this round, so row 54 was an owning row — it was missed because the search
started from "which docs describe overlay" rather than from "which rows list the files I touched".
This is the 2026-07-27 pattern again: implementer named 2 rows, the true set was 3, and the
`mm`-is-empty sentence had propagated to 7 files.

**No count-vs-set trap found:** the refusal-reason vocabulary is unchanged at 4 named states
(`meta_unavailable`, `binding_unavailable`, `align_unavailable`, `no_data`) — `align_unavailable`
survives with a different *cause*, so `docs/architecture/frontend.md:294` remains true as written.

---

## 6. Scope notes

- The brief listed 3 files; **`client2/tests/valid_die_authoring_harness.mjs` is also modified**
  (+3/-1, same symbol-list fix). Benign, but it belongs in the commit's file list.
- `client2/dist/assets/{admin,main,map_editor}-*.js` are untracked and were built from a tree
  containing other lanes' uncommitted `client2/src` work. Decide explicitly whether `dist` is in
  this commit — the report itself flags this at §4.6.
- `valid_die_authoring_harness` INV-6 (98 passed / 1 failed) reproduces at HEAD; the report's
  diagnosis (the assertion compares `indexOf` over sliced text and `projectCellsToPhys` appears
  first in a comment) is consistent with the source and is pre-existing. Not this round's.

---

## 7. Proposed lessons for `agent_workspace/memory/qa-reviewer.md` (proposal only)

1. **함정**: 구현자가 "하네스 N개가 깨져서 고쳤다"고 하면 그 N을 믿는다.
   **올바른 방법**: 바뀐 심볼을 **슬라이스하는 모든 하네스를 직접 grep해서 전부 실행**한다.
   `KNOWN_RED` 부채 목록에 있는 하네스는 **이미 빨간색이라 새 고장이 보이지 않는다** — 실측:
   `valid_die_frame_adoption_harness`가 "28/228 실패"에서 "첫 단정 이전에 ReferenceError로 죽음"
   으로 바뀌었는데 러너는 똑같이 "still red"라고 찍는다. 부채 목록 항목은 **실패 방식이 바뀌었는지**
   까지 대조해야 한다.
2. **함정**: 관문의 술어만 읽고 통과 판정한다.
   **올바른 방법**: 그 술어가 읽는 **값이 어디서 오는지 끝까지 따라간다**. `physNum`의
   `return v || dflt`처럼 폴백이 있는 읽기 위에 세운 `> 0` 검사는 **0과 NaN을 절대 만나지 못한다** —
   문구는 "확정할 수 없습니다"인데 코드는 그 상태에 도달할 수 없다. 관문은 **폴백 이전 값**에 걸어야
   한다.
3. **함정**: 문서에 박아 둔 grep 계약(묘비)을 "구현자가 안 어겼다고 했으니" 넘어간다.
   **올바른 방법**: 묘비가 **명령어를 적어 뒀으면 그 명령어를 그대로 실행**한다. 실측: §0 ⑫가
   적어 둔 명령이 신규 히트 1건을 뱉었고, 게다가 그 묘비의 **기준선("선언 0건")부터 이미 틀려**
   있었다(`utils.js:8`).
