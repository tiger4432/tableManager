# UI/UX Audit — DOE Working Surface (표①/표②, chips, gates, journey)

- **Auditor:** ui-designer | **Date:** 2026-07-29 (overnight) | **Mode:** REPORT ONLY — zero code/doc edits
- **Target:** isolated `:8081` (full isolated dataset; `:8082` = minimal e2e set, untouched; **zero `:8080` contact**), real Chromium via browser pane, `map_editor.html`
- **Fixture:** `bonding_map|AAA` with a pre-existing local draft (5 value rows incl. STACK-0 marker with live V6, 2 material pools) + journey to `dt_map|LOT-A_05` and back. Served bundle `map_editor-DxCPgSEP.js` (2026-07-28 21:26) — **postdates the 5b fix commit `0052d76`**, so everything below was measured against current code.
- **Writes:** none to server (Push attempt verified **0 network calls** — cancelled at first confirm). Draft-local only.

## 0. Method & harness caveats (read before trusting any keyboard finding)

1. **Coordinate calibration.** The browser pane runs viewport emulation (inner 1600×900, native ~2902 wide). Mouse coordinates from screenshots/refs are mis-scaled by ×3.6275; I calibrated by dividing target client coords and verified every click against the page's own instrumented event log (`mousedown/mouseup/click/focusin` capture listeners). All click findings below are backed by that log, not by screenshots.
2. **Named-key artifact — two findings RETRACTED.** `Delete`/`BackSpace`/`Ctrl+A` sent by the harness arrive with **empty `e.key`** (proven: document-level keydown logged `key:""`, `defaultPrevented:false`, and the input did not change; a plain letter sent through the same path *did* insert). Early in the session I believed the page swallowed select-all/delete inside plan inputs — **that was the harness, not the page.** In-field Ctrl+A/Delete/Backspace need a 30-second manual check; no page-side handler exists that could swallow them (grep: no `keydown` listener in `transfer_plan.js`; `map_editor.js` has none targeting inputs).
3. **Native dialogs auto-dismiss as cancel** in this pane. Good: destructive paths are probe-safe. Bad: accept-paths (실제 Push, row delete) are untestable. The `저장됨` chip state was therefore not observed live.
4. **Leftover state disclosure:** one empty draft row `D3` (auto color `#ef4444`, no STACK, no materials, no painted cells) remains in the `bonding_map|AAA` browser draft — created by the `+ 값` probe; deleting it requires accepting a native confirm, which the pane refuses. One human click (🗑 → 확인) removes it. Everything else was restored to the exact pre-audit values (verified field-by-field: `F/0/BIN F`, `2/4/BIN 2`, `D1/2/—`, `D2/1/—`, MIDs `LOT-A_05:1`, `LOT-A_05:1`, `LOT-A_05:2`; chip `저장 안 됨`; light theme; native `fetch/confirm/alert` restored).

---

## 1. Ranked findings (pain × frequency)

| # | Finding | Sev | Lane |
|---|---|---|---|
| 1 | Dirty-field exit rebuilds 표① and **eats the next click / kills Tab** — every fill flow, with silent keystroke loss | P0 | (b) map-pm T2 |
| 2 | Size/density islands: action buttons & V-messages are the smallest text on a surface used for hours; 2~2.5 rows visible per screen | P1 | (a) ui-designer T3 |
| 3 | Hit targets & affordance: 🗑 20×13px, panel buttons ≤21px tall, pool rows have zero hover feedback, ⇄ 엑셀 is a 19px help-span | P1 | (a) T3 |
| 4 | `+ 값` appends the new row **off-screen, without focus** — "button did nothing" → double-add | P1 | (b) map-pm T2 (small) |
| 5 | Auto-color assigns near-duplicates (`#ef4444` new vs `#f40b0b` existing; two identical grays) — DOE conditions indistinguishable on canvas | P2 | (b) map-pm T2 (small) |
| 6 | V6 remedy copy points at a **disabled** control; offending material is invisible in the row | P2 | (c) copy + (b) small |
| 7 | 미상 reasons are hover-tooltip-only (21.8×15px token) — no keyboard/scan access | P2 | (a)/(b) — partially covered by queue 7c |
| 8 | "No Grid Metadata Detected" modal: EN/KO mixed, trade-offs unexplained, interrupts the pool-row journey | P2 | (c) copy-only |
| 9 | Return journey: pane ① scroll not restored (promise says it is); reward-after-return fully silent | P3 | (b) small / (c) |
| 10 | Push cancel = zero feedback; desc-gate cancel doesn't point at the offending rows | P3 | (c) copy |

Positives worth keeping (do not "fix"): validation-does-not-block-save model, inline V-blocks beside their rows, live zone-extent labels while typing (`1–32` updated mid-keystroke without focus loss), 해당없음 hints that state the exact threshold ("STACK을 2 이상으로"), the 표② honesty notes, chip tooltip copy, breadcrumb frame with dual back affordances, dedupeKey toast merging, `matSeq` stale-response guard, dark theme (contrast 7.3–12.3, coherent).

---

## 2. Axis: 클릭 후 입력 연속성 (the load-bearing section)

### 2.1 P0 — blur-commit rebuild eats the next pointer/keyboard action
The 2026-07-28 mousedown-rebuild fix cured typing-in-place (verified: typing in STACK keeps node identity — marker property survived, caret correct, zone label live-updates). **Its relative survives on the exit path**: leaving any *changed* field re-renders the DOE list, and the re-render lands between `mousedown` and `mouseup` of whatever the user pressed next.

Evidence (page's own event log, D1 STACK edited then click into MID textarea):

```
mousedown TEXTAREA.tp-zc-raw (1378,546)   ← user's next click starts
(blur → commitRow → renderDoeList)        ← node replaced here
mouseup   TEXTAREA.tp-zc-raw
(no click event, no focusin) → activeElement = BODY
```

- **Mouse path:** first click after every edited field is consumed; second click required. Reproduced 4/4 attempts on dirty exits; clean exits (nothing typed) land in one click (control test: `focusout din → focusin TEXTAREA → click` — normal).
- **Keyboard path:** type in a field → `Tab` → focus dies on BODY (no focusin ever fires — Tab's target was replaced). **Filling VALUE→STACK→1H→MID→TOP with Tab alone is impossible**; every field costs a mouse re-entry.
- **Silent data loss:** keystrokes typed after an eaten click go to BODY. Observed live: clicked DESC after a STACK edit, typed `abc` — all three characters vanished with zero feedback (they never reached any input).
- **Aim-shift variant:** the commit re-layout is asynchronous; a V-block appearing/disappearing shifts rows ±53–86px a beat after the edit, so even the *second* click can land on the wrong element (measured: intended DESC at y588 was pane-② header by click time).
- What does NOT happen (verified, so don't re-fix): scroll position of `.tp-pane-b` survives the rebuild; values are never lost from the committed field itself.

**Recommendation (map-pm):** on commit, patch the changed row's dependent fragments in place (the code already does this for zone labels during typing — `refreshRowZones`); rebuild the whole list only on add/delete/reorder. This *reduces* DOM churn — control count unchanged. Acceptance test: type in STACK → single click into MID lands focus; type → Tab reaches DESC.

### 2.2 Rest of the axis
- **Caret placement:** click inside text lands caret at click point (selStart matched click offset) ✓.
- **Focus theft during typing:** none observed over 1.5s idle with instrumented marker — no debounced refresh steals focus while you stay in-field ✓.
- **Tab order (clean fields):** `VALUE → STACK → DESC → 🗑 → 1H → MID → TOP → (next row) COLOR → VALUE…` — the **destructive 🗑 sits mid-row in the flow** (guarded by confirm, but it's a stop every row), and COLOR adds a second stop. Recommended tab order surgery (T3, `tabindex="-1"` on 🗑 and COLOR): flow becomes the exact fill order with zero new elements.
- **Enter/Escape:** Escape keeps focus and doesn't rebuild ✓. Enter in zone textareas = newline (correct — multi-material contract). Enter in VALUE/STACK: no action (no accidental submit) ✓.
- **Ctrl+A / Delete / Backspace in-field:** untestable here (see §0.2) — manual check recommended, expected fine.

---

## 3. Axis: 클릭성 (hit targets, measured at default zoom, 1600×900)

| Control | Measured | Verdict |
|---|---|---|
| 🗑 row delete | **20×13.1px** button (13px font) | Far below 32px. Mitigations: confirm guard with consequence copy ✓; nearest interactive neighbor (zone textarea top edge) is 22px away — adjacency tolerable, size is not. T3: pad hitbox to ≥24×24 via padding (no layout change). |
| `+ 값` | 36.8×21 | Under-height; it's the most-used creation control. |
| `↻ 가용` | 48.6×21 | Under-height. |
| `⇄ 엑셀` | 44.3×18.9 span, `cursor:help` | Not a button at all — see §5 discoverability. |
| `← 돌아가기` (pane ② card) | 70.4×21, 10.56px font | Under-height; also starts 31px-visible in pan-mode (§4.3). |
| `← 뒤로` (breadcrumb) | 61.9×26 | Acceptable. |
| Pool row (표②) | clickable span 183×19.3 inside a 399×25.3 row | **Zero hover feedback** (no bg/underline/color change on :hover — verified computed styles), and only the MAT-cell third of the row is clickable while the whole row reads as one unit. Header teaches "행 클릭 → 그 자재의 맵" but the row itself never confirms. T3: row-level `:hover` tint + make the full row the click target (event delegation already row-scoped — verify with map-pm). |
| Row inputs VALUE/STACK/DESC | 56/52/170 × 26 | Fine. |
| Zone textareas | 100.8–162.5 × 47.4 | Good targets. |
| Color swatch | 24×26 | Fine. |
| Chips (`저장 안 됨` etc.) | 129–206×20.3, pill-styled, `cursor:auto` | **Reverse affordance problem**: styled like buttons, text literally says "[⚡ Push]로 저장", but inert. Consider `cursor:help` + underline-dotted to signal "tooltip lives here", or make the chip focus the Push button on click (1 behavior, 0 new controls). |
| Push Map Data | 104×73 toolbar tile | Good. |
| Metadata modal buttons | 430×42~43 ×3 | Good. |

**Mis-click adjacency:** 🗑 column aligns vertically with the `+ 값` button (x1535–1584 vs 🗑 x1547) — a user aiming for `+ 값` right after scrolling can land on row-1's 🗑; the confirm guard catches it, but the near-miss geometry is unnecessary. T3 option: left-align `+ 값` within the pane header, away from the delete rail.

---

## 4. Axis: UI 크기 적절성 (fonts, heights, density — measured)

### 4.1 The 0.82rem bump landed on row inputs only — mismatched islands remain
Measured font sizes on the surface (px at default zoom):

- 13.12px — VALUE/STACK/DESC inputs (0.82rem ✓ the bump)
- 12.48px — zone textareas (0.78rem) ← same editing tier as row inputs, smaller
- 11.84px — pool rows (the primary data readout)
- 11.2px — 해당없음 cell text
- 10.88px — **V-messages** (the text telling you what's wrong), chips, 미상 tokens
- 10.56px — `+ 값`, `↻ 가용`, `← 돌아가기` button labels
- 10.24px — both footnotes (표① syntax legend, 표② 사용≈ honesty note)

Inversion: the *most consequential reading* (V-blocks, refusal chips) and the *most-used actions* are the smallest type on the panel. Contrast is fine everywhere (light: 5.03–5.74:1 on the small text, AA pass; dark: 7.27–12.25:1) — size, not color, is the issue. T3 recommendation: one tier up for V-blocks/chips/buttons (0.68→0.74rem, 0.66→0.72rem), keep footnotes as-is. No layout growth beyond ~2px per row.

### 4.2 Density at real volumes
- Pane ① viewport 278px (at 900px tall screen) / 212px (at 768px). Regular row ≈ 86px, marker row with V6 block ≈ 131px → **2~2.5 rows visible of 5**; at the task's "4+ DOE rows" a third of the plan is always below the fold, and the **syntax footnote (the learning aid) is unreachable without scrolling** the moment you have >2 rows.
- Row height budget: 20.8 (input line) + 47.4 (zone textareas) + inter-row gaps. The 47.4px textarea double-line is what makes rows 86px. If density ever needs improving, collapse zone cells to single-line (26px) until focused — but that adds a state; **not recommended under 절대 복잡하면 안 됨**. Cheaper T3: trim the marker-row 해당없음 triplication (§5.2) and V-block padding — recovers ~40px per marker row.
- 표②: ~4 pool rows + notes visible — adequate for realistic pool counts.

### 4.3 Width reality (1366/1600) — 5b-ⓕ verified, residue documented
- At 1366×768 the editor's natural min width is **1570px**; `.main-layout{overflow-x:auto}` (5b-ⓕ, `0052d76`) works as designed — verified live: `scrollWidth 1570 vs clientWidth 1366`, and `scrollLeft=204` brings the panel fully in. **Not a regression; do not re-queue.**
- Residue worth one line in the queue item's memory: at 1366 the *default* view amputates TOP zone, 칠함, 🗑 (panel right edge at x1569.9), and the only cue is a scrollbar at the very bottom of the page. The same mechanism puts even **1600px screens into pan-mode inside the material-map frame** (natural width grows to ~1656 with a 56-col dt map canvas) — the panel the user just traveled to starts 56px cut, `← 돌아가기` 31px visible. If any future pass touches this: right-anchor the scroll position when a frame opens with the plan panel as the navigation target (scroll `.main-layout` to max on `openMapFrame` completion) — zero new controls.
- Material-frame column allocation bug (independent of scroll): with zone columns absent, 표① gives DESC **52px** (clips "scratch DOE", scrollWidth 86 > clientWidth 50, no ellipsis) while the painted-count cell idles at **185px**. T3 CSS: swap the fraction weights in that frame's grid template.
- Canvas paintability: 22.3px cells (29-col map @1600), 16.7px @1366 — comfortably above the ~12px painting floor; not a concern.

---

## 5. 표① 값 정의 — comprehension at volume

### 5.1 What works (keep)
Readability at 4–5 rows is fundamentally sound: color swatch → VALUE → STACK → DESC on one line, zones on the second, painted count right-aligned mono. 해당없음 hints are state-specific and truthful. Placeholders teach the zone model in place ("비우면 MID가 1층부터"/"STACK까지"). V-blocks sit inline under their row — help, not nag; and per `사용자 지시 2026-07-28` they don't block saving, which the live Push attempt confirmed (V6 present, push proceeded to the desc gate).

### 5.2 Findings
- **V6 dead-end (P2, copy + small logic).** Row `F` (STACK 0) shows V6 "…MID: MID9 — STACK을 채우거나 **자재를 지우십시오**", but all three zone cells are `disabled` behind 해당없음 overlays and the offending `MID9` is *nowhere visible in the row* — only inside the V6 sentence. The remedy as written cannot be performed: you must know to set STACK≥1 first (then the material appears and is editable), clear it, and set STACK back to 0 — a detour verified live. Worse, in the pre-commit window after typing STACK=1 the zone chip renders `MID9_✱:1` while the raw textarea is still empty — typing there then overwrites the hidden material silently (desync heals on commit; §2.1's fix likely heals this too). Minimal fix, copy-first: V6 message → `…자재를 지우려면 STACK을 1로 바꾸면 자재 칸이 열립니다 — 지운 뒤 다시 0으로 두십시오.` Better (small logic): render the marker row's zone content read-only inside the 해당없음 cell (`해당 없음 · 자재 MID9 남음`). Adjacent to completed U9 (marker/V6 both-sides) but this interaction gap is new.
- **해당없음 triplication (P3, visual-only).** A STACK-0 marker prints the identical 25-char sentence in all three zone cells (88.8+150.5+88.8px × 34–50px). One statement across the merged width would halve marker-row noise and height.
- **`+ 값` births rows invisibly (P1, map-pm small).** Click → row `D3` auto-named and appended, but pane scroll stays at 0 (new row below fold, overflow 387px), focus stays on the button, nothing visible changes. "Did it work?" → second click → duplicate. Fix: scroll new row into view + focus its VALUE input. (This also converts `+ 값` into the natural keyboard entry point, which §2.1's Tab fix then chains.)
- **Contract asterisks unexplained on-surface (P3, copy).** `COLOR*`/`칠함*` asterisks are only decoded inside the ⇄ 엑셀 hover tooltip ("계약 밖"). A first-time user reads them as "required" (the web convention). One-word title on the headers (`title="엑셀 계약 밖 — 붙여넣기/복사에서 제외"`) or footnote mention.
- **Excel paste discoverability (P2).** The entire TSV contract (header-name matching, partial columns OK, 1×1 pass-through, color column skipping, Ctrl+C export) lives behind a 44×19px `cursor:help` span. The interaction itself is excellently designed (`onPlanPaste` — accepts 3-column pastes, toasts applied-count with header-match note); it's the *doorway* that's invisible. T3: make ⇄ 엑셀 a real (small) button whose click shows the same text as a toast/popover — same information, one affordance upgrade, zero new concepts. Also note `navigator.clipboard` is correctly not used (paste event path — works on plain HTTP ✓; frontend.md §3's `copyGridToExcel` caveat doesn't apply to the plan panel).
- **V-message tone (copy verdict):** V1–V6 all name the value, the fact, and the remedy in one sentence; none moralize. The `_✱` render token in zone chips (e.g. `MID9_✱:1`) is undocumented on-surface — minor.

---

## 6. 표② 자재 롤업

- **Column comprehension:** MAT/MAP/가용/사용≈/잔여≈ with the two footnotes is learnable; `사용≈은 실제 소비가 아닙니다…` is the best copy on the page and correctly kills the #1 misreading (share-split vs consumption). Verdict: keep verbatim.
- **미상 discoverability (P2).** The reason lives only in a `title` tooltip on a 21.8×15px amber token — hover-only, no keyboard/touch path, invisible while batch-scanning. Mitigation already shipped (U8 ✓ verified live): `↻ 가용` toast names the dominant reason ("가용 조회 완료 — 2개 풀 중 2개 미상: 이 단계에 BIN 축(`bin_map`)이 선언돼 있지 않습니다…"). Residual gap: per-pool reasons when reasons differ. **Queue 7c (`transfer_log:"none"` → `≤N` 상한 + tooltip) will land in this exact cell — fold any change into that round rather than a separate pass.** Copy nit: backtick-quoted `bin_map` is config-speak in a user string; acceptable for R&D audience, flag only.
- **↻ 가용 feedback loop:** dedupeKey merges rapid duplicates (3 clicks → 1 toast ✓); `matSeq` guard discards stale responses ✓; but there's **no in-flight guard** (3 clicks → 12 requests) and no busy state on the button — invisible at the measured 9–28ms locally, will read as "dead button" on a slow prod link until the toast arrives. T3: `disabled` + `↻…` label while the force-refresh promise is pending — no new element.
- **Pool row → map jump affordance:** see §3 (no hover feedback, ⅓-row click zone). The `→` glyph is always-on so it reads as decoration, not action.

## 7. 칩·토스트·게이트 (tone vs the house rule)

All four chip states inspected (two live, two from `transfer_plan.js:503-516`): `저장 안 됨`(warn) / `저장됨 hh:mm`(ok) / `변경 없음`(dim) / two `bad` refusal chips. **The refusal chips are the house style at its best** — both explain *what* would be lost, state "그래서 저장하지 않았습니다. **계획이 틀려서가 아닙니다.**", and promise auto-retry. The `저장 안 됨` tooltip carries the entire draft mental model ("탭을 닫거나 새로고침해도 사라지지 않습니다 — [⚡ Push Map Data]가 맵과 함께 올립니다"). Verdict: no copy changes.

Gate messages (desc-gate captured live; log-shaped / frame-coverage / identity-mismatch / final Clean Replace from source `map_editor.js:4100-4275`): every one names the object, the count, the consequence, and the remedy; the log-shaped refusal even tells you what to use the table for instead. Tone-consistent with the house rule. Two small gaps:
- **Cancel is a silent no-op (P3, copy).** Cancelling the desc-gate (or any confirm) returns you to the editor with zero feedback; the desc-gate already knows the offending values (`[D1, D2]`) but the panel doesn't point at them. Cheapest honest fix: one info toast on cancel — `적재를 취소했습니다 — 서술 없는 값: D1, D2 (표①에서 채울 수 있습니다)`. No new UI.
- **Metadata modal (P2, copy-only).** "No Grid Metadata Detected" + English body + Korean option 1 + English option 2 in one dialog, and the two load strategies' trade-off is unstated. Proposed copy (Korean, information-identical): title `맵 규격(메타)이 등록되지 않은 맵입니다`; body `좌표를 어떻게 배치할지 선택하십시오. 이 선택은 화면 배치에만 영향하며 데이터는 바뀌지 않습니다.`; options `📐 표준 — 데이터 전체를 사각 격자로 (마스크 없음 · 회전 0°)` / `⚙️ 현재 좌측 패널 설정대로` / `❌ 열지 않음`.

Toast mechanics: bottom-center ✓ (640×67 at y809, 13.6px), stacking bounded by the utils.js cap-4/dedupe/TTL system — rapid-action stress produced exactly one merged warning; no pile-up observed.

## 8. 여정 단절점 (DOE 작성 → 자재 → dt 맵 → 복귀)

Verified live end-to-end. The skeleton is strong: pool-row click → (modal, see §7) → dt map loads with **lavender breadcrumb** (896×43: `← 뒤로 | bonding_map · AAA › dt_map · LOT-A_05 | 뒤로가면 편집 상태·오버레이·스크롤이 복원됩니다`), panel head swaps to `자재 맵` + `상위 bonding_map · AAA에서 이동` chip + correctly independent `변경 없음` chip, pane ② becomes the `📦 자재 맵 편집 중` card with `← 돌아가기` and one-click `＋ defect / ＋ EDS fail` overlays. Return restores draft rows, chip state, and panel position exactly (verified field-by-field).

Breaks, in journey order:
1. **The metadata modal** is the hard seam — a technical projection question in the middle of "show me this material" (§7). Copy fix suffices; the 5b-ⓒ geometry fix already made the default option safe.
2. **Arrival cut short:** material frame opens in pan-mode at 1600 (§4.3) — the panel you traveled to is the thing cut off.
3. **Return scroll promise:** breadcrumb says "스크롤이 복원됩니다" but pane ①'s scrollTop measured 262→0 across the round trip (the map frame's own state does restore). Either restore the pane scroll in the frame snapshot (it already snapshots `legendDirty`/`frameTouched` — same gateway) or drop "스크롤" from the copy.
4. **Silent reward:** `rewardAfterReturn` refreshes that material's numbers with no signal on success (toast only on failure). Under 무마찰 read rules silence is defensible, but the user who left *to check availability* returns to a screen that looks identical. One dim toast (`LOT-A_05 가용·맵 상태 갱신됨`) is the entire fix — or leave as-is; ranked P3 deliberately.

## 9. 정보 위계 / draft-discipline learnability

- **Learnable from the screen alone?** Partially. The chip row teaches save-state *if* you hover; the Excel contract, 미상 reasons, marker semantics, and contract asterisks are all tooltip-gated. First-timers get a coherent surface but must discover the rules by accident. The single cheapest improvement is §5.2's ⇄ 엑셀 button-ization plus the V6 copy fix — both convert hidden knowledge to shown-on-demand without adding surface area.
- **Attention competition:** mostly sane. The V6 block + red row border rightly dominate. One leak: `⚙️ 4. Advanced Column Mapping` selects (left sidebar) list internal columns (`is_graph_synced`, `needs_graph_rollback`, `eventtime`…) as mapping candidates — internal vocabulary in a user dropdown (map-pm lane, adjacent to the declaration-driven candidate work in U6).
- **Auto-color near-collisions (P2, map-pm small):** `+ 값` assigned `#ef4444` next to existing `#f40b0b` (ΔE ≈ indistinguishable at 22px cells); the two draft rows both carry `#6b7280`. On a wafer canvas the *only* identity of a DOE 조건군 is its color. The palette picker should skip colors within a distance threshold of existing legend entries — pure assignment logic, no UI change.

## 10. Duplicate/queue cross-references (not re-reported as new)

- **5b-ⓕ** (sub-1540 sidebar reach): verified **working as designed** at 1366 (`scrollWidth 1570`, panel fully reachable at `scrollLeft 204`). §4.3 documents residue only.
- **5b-ⓒ** (metadata-less default frame): geometry fix confirmed live (표준 option loaded 1293-cell dt map normally). My finding is the modal's *copy*, not its behavior.
- **U8** (↻ 가용 dead-button): fix verified live — force refresh always toasts. Residual: per-pool reasons, in-flight affordance (§6).
- **U9** (marker/V6 both-sides): shipped; §5.2's V6 dead-end is the surviving interaction gap on top of it.
- **7c** (`transfer_log:"none"` → `≤N`): will rewrite the 미상 cell this audit criticizes — fold, don't fork.
- **2026-07-28 mousedown-rebuild fix:** typing-in-place is cured; §2.1 is the blur-commit relative the coordinator asked me to hunt.

## 11. Proposed lessons for `agent_workspace/memory/ui-designer.md` (총괄 승인 대상)

1. Browser-pane viewport emulation mis-scales both coordinate- and ref-clicks (observed ×3.6275). Calibrate by clicking a known element and reading the page's own event log; never trust screenshot-space coordinates directly.
2. Browser-pane named keys (`Delete`/`BackSpace`/`Ctrl+A`) arrive with empty `e.key` — before reporting "the page swallows key X", instrument a document-level keydown logger and confirm the key actually arrives intact.
3. Browser-pane auto-dismisses native `confirm/alert` as cancel — destructive UX paths are probe-safe, accept-paths are untestable; plan audits accordingly.

## 12. Handoff summary

- **Changed files:** none (report only). Server writes: none. Draft residue: one empty `D3` row (§0.4).
- **Verification:** all geometry numbers are `getBoundingClientRect` measurements at default zoom; all interaction claims are backed by instrumented in-page event logs; two early keyboard findings retracted after artifact analysis (§0.2).
- **Top recommendation if only one thing gets a round:** §2.1 (dirty-commit rebuild). It is the only finding that loses user keystrokes, it fires on every single row fill, and its fix (patch-in-place instead of list rebuild) also erases §5.2's pre-commit desync and §2.1's aim-shift.
- **Untested:** `저장됨` chip state, real Push accept path, in-field Ctrl+A/Delete/Backspace (harness limits), live Excel paste (mechanics audited from source to avoid draft damage).
