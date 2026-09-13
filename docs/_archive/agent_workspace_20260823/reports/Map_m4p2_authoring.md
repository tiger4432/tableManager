# M4 phase 2 — valid-die map authoring & registration

**Agent:** map-pm · **Baseline:** `7694b42` · **Date:** 2026-07-29
**Files changed:** `client2/src/map_editor.js`, `client2/map_editor.html`,
`client2/tests/effort_instrument_harness.mjs` (sandbox stubs only, §6)
**New:** `client2/tests/valid_die_authoring_harness.mjs`, `client2/tests/valid_die_head_parity_oracle.mjs`
`client2/dist/**` rebuilt. **Not committed. No server file touched. Not one write reached a database** (§5).

---

## 1. What landed (3 lines)

- **Generation** — the existing geometry-preset dropdown grew a third optgroup, `🧩 유효 다이 맵 만들기 (템플릿)`, with three actions: fill from the circle, fill the whole grid, or open the whole grid without filling (to re-edit a template that already exists). The authoring canvas is **always the full grid**, so a shape the circle cannot express is expressible and a saved template can be re-opened.
- **Designation** — one two-line block in the existing 물리 규격 section: a table `<select>` (defaults to "이 맵의 테이블") and a map-key `<input>` backed by a `<datalist>` of that table's registered maps. Empty key = circle geometry. Saving is the existing ⚡ Push, unchanged.
- **The one-hop limit** — `validDieChainError` refuses a reference whose target itself declares a `valid_die_ref`, and refuses self-reference. Cycle detection needs no visited set: B declared, therefore A refuses.

---

## 2. The design decision worth arguing with

**Why the authoring canvas is the whole grid, not the chosen shape.**
`pushMapData` drops cells whose `inside` is false, and the contrast guard then *refuses the whole push* because the payload covers less than the screen. So "paintable" and "savable" are the same predicate, and that predicate is `isValidDieAt`. If the circle preset opened only the circle, then:

- a rectangle on tape could never be authored (the corners are ~21% of the grid and permanently unpaintable), and
- **a saved template could never be re-opened** — its own out-of-circle cells would load as `inside: false` and the contrast guard would refuse every subsequent save of it.

So the shape choice decides **what is pre-painted**, never what is reachable. One sentence covers the whole feature: *격자 전체가 후보이고, 칠한 셀이 곧 유효 다이다.* Measured live: a rect template on an 11×13 frame put **143/143 cells** into the push payload with the contrast guard silent (§5).

**Why a fourth basis token, and why the seam does not move.**
`validDieBasis` gained `template`. The contract calls the token contract surface, so this is stated rather than assumed: `circle|ref|refused` are the tokens **derived from stored metadata**, and `resolveValidDie` cannot produce `template` — asserted against the function's own source text, not by inspection. `valid_die_basis_cases` scores the same three tokens it always did. `template` is a screen state that ends at any load, table switch, or frame restore.

**What Push writes is decided in one place, split across two functions on purpose.**
`validDieRefForPush()` answers *did the user change anything* (if not: keep the stored bytes untouched — an unreadable `5` or a `{target_table, map_key}` alias is not silently rewritten by a save the user did not aim at it). `applyValidDieRef(meta, ref)` answers *what gets written*, and it is the pure, contract-scored writer.

---

## 3. Invariants — how each was proved

| Instrument | Result |
|---|---|
| `client2/tests/valid_die_authoring_harness.mjs` | **84 passed, 0 failed** |
| ...its mutation suite (defect put back, 13 variants) | **13/13 caught** |
| `client2/tests/valid_die_head_parity_oracle.mjs` (loads the `HEAD` blob out of git) | **17,496 cells, 0 differing** |
| `contracts/map_seam/client_harness.mjs` | **393 assertions, MATCHES** (12 pinned D1 failures unchanged) |
| `client2/tests/effort_instrument_harness.mjs` (payload byte-identity) | **28 passed, 0 failed** |
| Live read-only E2E against the running server, writes shimmed | §5 |

**INV-1 — additive coexistence, measured against the blob.**
`valid_die_head_parity_oracle.mjs` extracts the verdict path (`isValidDieAt ∘ isCellInsideWaferFast`) from `git show HEAD:client2/src/map_editor.js` **and** from the working copy, then compares the per-cell verdict across 3 geometries × 4 rotations × 2 sides = 24 frames, 17,496 cells, with no declaration: **0 differ**. Two independent red-proofs, because "0 differ" is also what a comparator that measures nothing reports:
- *state*: declaring a mask on the working copy alone moves **25** cells;
- *source*: shrinking the circle radius in the working source moves **139** cells.
  (A `> 1.0` → `>= 1.0` boundary flip was tried first and moved **0** — exact tangency is measure-zero at these geometries. Recorded because it is the mutation that would have looked like a red-proof and proved nothing.)

At the payload level, the effort harness pushes with the controls empty and asserts the body byte-for-byte; live, the same push produced `grid_metadata` with **no `valid_die_ref` key at all** — absence, not `null`, not `""`.

**INV-2 — a preset template is a savable map.** `buildValidDieTemplate('rect')` addresses all 99 cells of the fixture grid; `('circle')` pre-paints exactly the circle verdict, key by key. The differential — cells the rect reaches and the circle refuses — is **72**, pinned as a number rather than `> 0`, and confirmed by an independent oracle written from the spec formula (11×9, R=9, pitch swapped to 3×2 by rot90, all-four-corners rule → 27 inside). If a future fixture stops exercising the axis it fails instead of going green. Both directions are checked: a corner the circle refuses is valid under the mask, **and** a cell carved out of the mask is invalid even though the circle allows it — a one-directional check passes an implementation that ORs the two.

**INV-3 — the saved template reads back as the same set.** Authored at rot90/back, stored meta written, then resolved while the screen sits at rot0/front. Compared **key → value per cell** (each row carries the physical key it came from, so `k === v` for all 99 entries), never as a set: a set comparison is satisfied by a permutation, which is precisely the "screen fine, values wrong" failure this domain produces. The wrong-frame differential is **98 of 99 cells misplaced** — where the *set-level* difference is only **18**, because a full rectangle largely maps onto itself. That gap is the argument for the per-cell form.

**INV-4 — unset returns to circle.** 21 cases through the end-to-end path (controls → decision → writer). Load-bearing rows: a cleared key writes **absence** (not `""`, which the parser calls a declaration and which would pin the map to `refused` forever with no editor left); a whitespace-only key clears; clearing an **unreadable** declaration works (the repair path — a writer that parses before writing can never fix a botched hand edit); an unchanged declaration is written back verbatim, alias spelling and all. Proved live end to end: with the designation the payload carries `"valid_die_ref": "4B12"`, after clearing the key is **absent** and the chip is hidden.

**INV-5 — refusal, never a silent circle.** Phase 1's parse rules re-asserted unchanged. New refusals (chain, self-reference) land in the same `refused` basis and surface in the same three places.

**INV-6 — one hop.** `validDieChainError(ref, refMeta, home)` — the shape and name the seam contract specifies. Refuses: two-level chain, two-cycle, self-reference, and a **broken** second-level declaration (`""`, `0`, `false` are declarations, not absence — a `if (refMeta.valid_die_ref)` guard is wrong for exactly those three, and all three are vectors). Does not refuse: an unknown ref meta (that failure belongs to `align_unavailable` upstream — one state, one vocabulary), the same key in another table, another key in the same table. The two refusal kinds are asserted **not to share a reason string**. Verified live by shimming the *read* of the referenced map's metadata to inject a second-level declaration: the chip went to `⚠️ 유효 다이 맵 미해석` with the chain reason; removing the injection let the same reference resolve to `🎯 유효 다이: bonding_map · 4B12 (177)`. **This closes the gap the seam harness listed as `guard_is_consulted_and_refuses` — not scoreable by any harness, verified at runtime instead.**

Also enforced at the authoring end: generating a template on a map that already declares a reference is refused with a stated reason, so a two-level chain cannot be *created*, only avoided.

**INV-7 — one canonicaliser.** The designation control trims and nothing else; `'TPL_01'` stays `'TPL_01'`. Canonicalisation happens exactly once, in `resolveValidDie`, through `canonicalMapKey`. The home key now goes through the **same** call before the self-reference comparison, so the mirrored pair holds: the same declared text `LOT_01` against home `LOT_1` is a self-reference under `slot: number` and a perfectly ordinary reference under `slot: string`. Mutation M13 (a guard that strips its own zeros) is caught by the second polarity.

---

## 4. Complexity budget

| | |
|---|---|
| New interactive controls | **+2** (a table `<select>`, a key `<input>`) |
| New buttons | **0** — generation is three options inside the **existing** geometry-preset dropdown |
| New panels / modes / modals | **0** |
| New passive indicators | **0** — authoring is a fourth line on the phase-1 status chip |
| Confirmations added to a read path | **0** |
| Confirmations added to a write path | **0 new dialogs**; one existing confirm gains a line, and only when the mask is not the circle |
| Friction on an empty grid | **0** — generation asks nothing until it would overwrite painting |

`<datalist>` is an attribute of the input that already exists, not a control: that is how "목록·재사용" is delivered without a list panel (measured live: 11 map keys offered for the current table). The push confirm's new line is `· 웨이퍼 원 밖 셀: N건` — string-identical to `HEAD` for every map whose basis is the circle, which is every map in production today.

---

## 5. Runtime verification — evidence, and the write ledger

Vite dev server on 5173 against the **running** backend on 8080. Before any interaction, `window.fetch` was replaced with a shim that records and **blocks every non-GET**.

| Step | Evidence |
|---|---|
| Authoring entry point exists without the preset API | optgroup rendered; also moved `renderPresetDropdown()` out of the success branch (§7-B) |
| Rect template, 11×13 frame | chip `🧩 유효 다이 저작 중 — 격자 전체 143칸`, no confirm (grid was empty) |
| The template is savable | push payload `updates.length = **143**` — the contrast guard did not fire |
| Honesty in the confirm | `· 웨이퍼 원 밖 셀: 104건 (유효 다이 근거가 원이 아닙니다)` |
| The template carries no reference | pushed `grid_metadata` keys: no `valid_die_ref` → INV-6 unreachable by construction |
| Circle template, 27×21 frame | 315 cells painted along the wafer edge; 2 carved by right-click |
| Re-edit is non-destructive | `채우지 않고 격자 전체 열기` → `현재 칠해진 셀 313개는 그대로 둡니다` — carved cells stayed carved |
| Live designation | `🎯 유효 다이: bonding_map · 4B12 (177)` |
| Chain refusal (read-shimmed) | `⚠️ 유효 다이 맵 미해석` + the chain reason naming both maps |
| Set → payload | `"valid_die_ref": "4B12"` |
| Clear → payload | key **ABSENT**, chip hidden |

**Write ledger — 6 requests attempted, 6 blocked, 0 reached the server.** Methods seen: `PUT` only.
Database evidence at the end of the session (`now = 2026-07-29T09:24Z`):

- `wafer_map_metadata` · `bonding_map` · `4B12` → `updated_at = 2026-07-25 20:00:54` (four days old, untouched)
- `wafer_map_metadata` where `map_id = 'SHIM_NEVER_WRITTEN'` → **0 rows**
- `bonding_map` where `base = 'SHIM_NEVER_WRITTEN'` → **0 rows**

---

## 6. Note on `effort_instrument_harness.mjs`

`pushMapData` now reads the two designation controls, so the vm sandbox raised `ReferenceError`. Added: two `el` stubs (both **empty** — "nothing declared, nothing typed" is the state every assertion in that file assumes) and three real extracted functions (`validDieRefDisplay`, `validDieRefForPush`, `validDieBasis`) — **extracted, not stubbed**, so the file actually executes the branch that decides whether `valid_die_ref` appears at all. No instrumentation logic touched; `commitIfRecorded` stays gated on `effort_recorded`; its own mutation suite still passes 28/28 and the pushed payload is byte-identical to the baseline.

---

## 7. Escalated — your decision, not mine

### A. 🔴 The server half of the M4② seam is NOT landed — `server-pm` work, and I did not touch it

`contracts/map_seam/vectors.json` (being edited live by contract-keeper — uncommitted) names two **required** server symbols that do not exist in `server/map_overlay.py`:

- `apply_valid_die_ref(meta, ref) -> dict`
- `valid_die_chain_error(ref, ref_meta, home) -> str|None`, plus wiring it into `_resolve_valid_die_uncached`

`conda run -n assy_manager python -m pytest contracts/map_seam/test_seam_contract.py -q` → **10 failed, 40 passed**; all ten are the new `test_authoring_*` / `test_chain_*` cases including `test_a_chain_refusal_reaches_the_branch_point_as_refused`. The client half is green on the identical vectors.

I confirmed the substance too: `_resolve_valid_die_uncached` (`server/map_overlay.py:1184-1282`) loads the referenced map's meta at `:1228` and **never asks what that map declares**, so today a server-side `A → B → C` chain resolves silently to B's stored cells and `A → A` resolves to a tautology wearing a healthy chip. This is not a hang (neither side recurses) — it is a wrong answer that looks right. Per your instruction I stopped at the confirmation rather than implementing.

### B. Two behaviours I changed that are arguably out of the stated scope — say the word if either should be reverted

1. **`fetchAndRenderPresets` now renders the dropdown even when `/api/map-presets` fails.** It used to render only inside the success branch. Harmless before; with the authoring entry point living in that list it means *a 500 on the preset endpoint deletes the authoring path*. One line moved.
2. **Template generation no longer wipes `gridData` wholesale.** Paint-locked cells are carried over by value, because the fill loop skips them — clearing everything first would leave them with no value **and** no way to repaint. Same rule `fillGrid` already respects.

### C. 🟠 Pre-existing, unfixed, and now more visible: `🎨 Fill All` produces an unpushable map

`fillGrid` (`map_editor.js:4329`) fills the **entire visual rect** regardless of `inside`, so on any circle-basis map it paints ~21% of cells that `pushMapData` then drops — and the contrast guard refuses the whole push. Worse, `updateLegendCounts` counts `gridData`, so **the DOE quantities on screen include cells that can never be saved**. Present at `HEAD`; I did not fix it because the fix changes cell counts, and cell counts are DOE arithmetic. Under an authoring mask this path now works correctly, which makes the circle-basis case look inconsistent by comparison.

### D. D1 is still open and is now pinned by the contract

The seam harness reports 12 assertions failing **as recorded** against D1 — `physNum`'s `|| dflt` turning a declared `edge_margin: 0` into `3.0` (escalated in the phase 1 report §6-A, owner map-pm, queued by you). It is not mine this round and I deliberately kept it out of every fixture here (`edge_margin: 1`, never `0`), or this round's harness would have been measuring that bug instead of its own subject.

### E. Not done, by scope

M4③ (retire the circle from `inside`, migrate the 188 stored metas) and E1/E2 erosion-based generation are untouched, as instructed. Note for ③: the authoring path writes **negative visual coordinates** for cells outside the circle, because `getVisualCoords` still subtracts the circle-derived `box.minC`. That is correct and round-trips exactly (INV-3 proves it key by key), but it is the concrete shape of "the bbox is still circle-derived" and ③ will have to decide whether it stays.

---

## 8. Living-doc update points (doc-keeper's — I edited no docs)

Rows found in `docs/process/DOC_OWNERSHIP.md` by the code paths I touched.

| Code path (DOC_OWNERSHIP row) | Living doc | What now needs saying |
|---|---|---|
| 웨이퍼 맵 에디터 | `spec/MAP_EDITOR_SPEC.md` **§5.7** | §5.7 currently reads "phase 1은 **소비만** 합니다 — 프리셋=템플릿 생성기(phase 2)…는 별개 라운드입니다." **Phase 2 has landed.** Add the generator half: `buildValidDieTemplate` (원/사각/열기 — 세 동작, 진입점은 기존 규격 프리셋 드롭다운), the rule that **저작 캔버스는 언제나 격자 전체**이고 왜 그런지(Push의 대비 관문이 `inside`와 같은 술어라, 모양만 열면 저장된 템플릿을 다시 편집할 수 없다), and that the bbox **still** stays circle-derived — that boundary did not move. |
| 웨이퍼 맵 에디터 | `spec/MAP_EDITOR_SPEC.md` §2 (상태 변수) · `map_editor/README.md` | `validDie.basis` is now four-valued: `circle`/`ref`/`refused` come from stored metadata, **`template` is a screen state that metadata cannot produce** and that ends at any load / table switch / frame restore. Worth stating explicitly, because the seam contract treats the first three as contract surface. |
| 맵 정렬 메타 (`wafer_map_metadata`) | `map_editor/architecture_and_management.md` **§2.3-bis** | The `valid_die_ref` row gains: (a) it is now **editable from the UI** — 물리 규격 블록의 「🎯 유효 다이 맵」 두 줄, 비우면 키가 **아예 빠진다**(빈 문자열이 아니다); (b) **참조 체인은 1홉**이다 — 유효 다이 맵 자신은 `valid_die_ref`를 가질 수 없고, 자기 참조도 거절이며, 순환 탐지기는 없다(1홉 규칙이 포섭한다); (c) 사용자가 손대지 않은 선언은 **원문 바이트 그대로** 되쓴다(별칭 형태·읽을 수 없는 값 포함). |
| 범용 맵 오버레이 | `spec/MAP_EDITOR_SPEC.md` §5.7 구현 지점 표 | Two rows to add — 선언 쓰기: server `apply_valid_die_ref` / client `applyValidDieRef`; 체인 판정: server `valid_die_chain_error` / client `validDieChainError`. ⚠️ **서버 쪽 두 칸은 아직 비어 있다**(§7-A) — 문서가 있는 것처럼 적으면 안 된다. |
| 본딩·전사 계획 엔진 | `guide/DOE_GUIDE.md` | User-facing: 원으로 표현되지 않는 유효 다이(테이프 위 dt 맵 등)를 **어떻게 만드는가** — 규격을 맞추고 → 프리셋 목록의 「🧩 유효 다이 맵 만들기」 → 깎아내고 → ⚡ Push → 대상 맵의 「유효 다이 맵」 칸에 그 키를 넣는다. 되돌리려면 칸을 비우고 다시 Push. |
| — (new test assets) | — | `client2/tests/valid_die_authoring_harness.mjs` and `client2/tests/valid_die_head_parity_oracle.mjs` are new and unlisted. The oracle is the only instrument in the repo that compares the working copy against a **git blob** cell by cell; it is the shape any future "identical to X" claim should reuse. |

---

## 9. Proposed memory entries (for your review — not self-applied)

- **Trap:** a mutation that does not apply reports "caught" or "missed" about **nothing**. A mutation suite whose targets have drifted out of the source is decorative and its score gets cited anyway.
  **Right way:** compare the mutated text to the original and **die** when they are equal. (Caught here: 4 of 11 mutations were silently no-ops after a rename, and the suite still printed a score.)
- **Trap:** a red-proof mutation can be too small to bite. `> 1.0` → `>= 1.0` on a circle test moved **0** cells, because exact tangency is measure-zero — and a 0-cell red-proof looks exactly like a comparator that measures nothing.
  **Right way:** pick a mutation whose effect is dimensional, not boundary (a shrunken radius, not a flipped `=`), and assert the count is non-zero.
- **Trap:** comparing two coordinate sets instead of two coordinate **mappings**. A full-rectangle map largely maps onto itself, so a deliberately misread frame showed a set difference of **18/99** while actually misplacing **98/99** cells. Set equality is satisfied by a permutation, which is this domain's exact failure: every cell on some other cell's coordinate, screen fine.
  **Right way:** carry the originating key as the value and assert `k === v` per entry.
- **Trap:** putting a feature's entry point inside a `if (res.ok)` branch of an unrelated fetch. The preset dropdown was only rendered on a successful preset fetch; hanging authoring off that list silently made a 500 on `/api/map-presets` delete the authoring path.
  **Right way:** render the shell unconditionally, fill it from the fetch.
