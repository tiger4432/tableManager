# M2.5 UI fixes — Client PM report

**Scope:** 4 user-reported UI items in the map editor. Client-only; `server/**` untouched.
**Build:** `client2/dist/assets/map_editor-JvFBs1Uv.js` (`npm run build` run; dist committed to the working tree, **not** git-committed as instructed).
**Live data:** zero writes — proven by SQL `updated_at`/rowcount invariance across 8 tables (see §6).

---

## 1. Summary of the four items

| # | User's complaint | Verdict |
|---|---|---|
| 1 | 공맵에서 오버레이 불가 ("기준맵이 없다") | **Fixed.** Empty canvas now overlays against the on-screen grid metadata; the chip discloses that basis. |
| 2 | 토스트가 사용 자재 리스트를 가림 | **Fixed.** Overlap area 42,205 px² → **0 px²** at the same viewport. |
| 3 | 자재 리스트를 자재 ID 키로 재구성 | **Fixed.** One row per material ID with 총 가용 / 총 사용 / 어디에 몇 개씩. Totals verified equal to raw `map_doe_source`. |
| 4 | legend 마이그레이션 confirm 삭제 | **Fixed.** Prompt and its localStorage flag removed; DOE opens clean; server-first legend order preserved. |

Two pre-existing defects were found and fixed as a direct consequence (§4).

---

## 2. Item 1 — an empty map can now receive overlays

### What was actually wrong

Three separate refusals, not one:

1. `addOverlayLayer` refused when `targetKey` was empty (`현재 캔버스의 맵 식별자를 알 수 없습니다 — 먼저 기준 맵을 로드하세요`).
2. `handleAddOverlayClick` refused **before even calling it** when `gridData` was empty (`겹칠 기준 맵이 없습니다 — 먼저 [📂 Load]로…`). This is the one the user actually hit; fixing only #1 would have changed nothing.
3. `addOverlayForSource` forged a target key: `getCurrentMapKey() || key` — falling back to the **source** key as the target key.

### The `:4059` question you asked me to settle first

`targetKey = getCurrentMapKey()` reads the **metadata input fields**, not the loaded map. These are genuinely different things and the codebase conflated them. Per call site:

- **Spec lookup** (`fetchGridMetaFor(targetTable, targetKey)`) needs *the map on the canvas* → `loadedIdentity`, which is pinned at load time. This closes open item **F2** in `MAP_EDITOR_SPEC.md` §5.5: typing a key without loading it no longer makes the gate judge against another map's spec.
- **Nothing else** needed the typed value.

So `targetKey` now derives from `loadedIdentity` (scoped to the current table), and its absence is no longer an error — it simply means "no registered target spec exists", which is exactly the blank-plan state.

The pipeline already handled the rest correctly: `fetchGridMetaFor` returns `null` for an empty key without issuing a request, and `tgtFrame = frameFromMeta(targetMeta) || currentFrame()` already falls back to the live controls. **No new transform code was written** — §5.1's "오버레이 전용 변환 코드는 존재하지 않는다" still holds.

### Honesty of the chip

`align.targetBasis` is now `'spec'` (target frame came from a registered `wafer_map_metadata` row) or `'screen'` (came from the live controls). `'screen'` renders an extra `화면기준` chip with a tooltip. Note this is **not only** the empty-map case: it also fires for the ~390k live `bonding_map` keys that have no registered spec — the silent state §5.0 calls a contract violation. It is now visible.

### Verification (§ the path that did not exist before)

`eds_fail_map / LOT-A_05` — 1288 cells, registered spec 40×40 **rot 180** front (so the projection is a real non-identity transform, not a no-op).

**Pre-change build** (served from `git archive HEAD client2/dist` on :5173 — the working tree was never reverted):
```
toast: "겹칠 기준 맵이 없습니다 — 먼저 [📂 Load]로 편집 대상 맵을 여십시오."
overlay count: 0
```

**Post-change build, empty canvas** (grid set to 40×40 / chip 7×7 / dia 300 / margin 3, nothing loaded):
```
overlay row : eds_fail_map LOT-A_05 1288칩 정렬됨 180° 화면기준
align       : {origin:"derived", targetBasis:"screen", rotation:180, flip:"none",
               note:"프레임 정규화: 회전(180°→0°) · 기준 맵 미로드 — 현재 화면 격자 설정 기준"}
projected   : 1288 physical keys, 0 outside grid, phys x∈[0,39] y∈[0,39]
```

**Resulting cell coordinates** (not a screenshot description). Full 1288-key set, FNV-1a over sorted `physKey=val`:

| source | digest |
|---|---|
| client, **empty canvas** | `3512305347` |
| client, **loaded map** (`core_defect_map/LOT-A_05`) | `3512305347` |
| **independent Python** reimplementation from raw DB rows | `3512305347` |

The Python oracle is derived from the documented formula, not from my code:
```
c  = xv - startX + box.minC          r  = yv - startY + box.minR
xp = cols-1-c                        yp = rows-1-r          (rot 180, front, offset 0)
```
Worked example: DB row `(x=15, y=1, val='F')` → `c=14, r=0` → **`25_39`**, which is exactly the key the browser produced with value `F`. Ranges and F-count (124) match on both sides.

### Loaded-map regression check — genuine before/after

Same sequence on both builds, through **user-facing paths only** (Load → ＋겹치기 → ↓가져오기 → 📋 Copy to Excel, with `navigator.clipboard` shimmed to capture rather than write). The TSV is the painted grid laid out by visual coordinate:

| build | overlay row | TSV |
|---|---|---|
| **pre-change** | `1288칩 정렬됨 180°` | 2887 chars, 40 lines, FNV-1a `202936273` |
| **post-change** | `1288칩 정렬됨 180°` | 2887 chars, 40 lines, FNV-1a `202936273` |

Byte-identical. The `화면기준` chip correctly does **not** appear (target spec is registered → `targetBasis:"spec"`).

And on the **final shipped bundle** with no debug hook, the *empty-canvas* path produced TSV digest `202936273` — the same value the old build produced for the *loaded-map* path. The new path lands exactly the cells the old path landed.

> **Method note:** a temporary `window.__ovDump` hook was added to read projected coordinates, then **removed before the final build**. `grep __ovDump dist/assets/map_editor-JvFBs1Uv.js` = 0 matches. Every claim above was re-run on the shipped bundle; the clipboard/TSV route needs no hook and works on both builds.

---

## 3. Item 2 — toast no longer covers the material pane

Toast was `position: fixed; bottom: 24px; right: 24px`; the material pane is the bottom 250 px of the 430 px right sidebar. Direct hit.

- `tokens.css`: `right: min(var(--toast-inset-right, 24px), calc(100vw - 300px))`. Unset elsewhere → other pages keep 24 px. The `min()` keeps toasts on-screen on narrow viewports.
- `transfer_plan.css` (loaded only by the map editor): `--plan-sidebar-w: 430px` and `--toast-inset-right: calc(var(--plan-sidebar-w) + 24px)`.
- `map_editor.html`: removed the inline `style="width:430px; min-width:430px"` so the width has one source. Verified `getComputedStyle(#plan-sidebar).width === "430px"`.

Toast timing/cap/dedupe untouched.

**Measured, same viewport 1280×860, two toasts up:**

| build | toast rect | overlap area | rows covered | `elementFromPoint` at pane bottom-centre |
|---|---|---|---|---|
| pre-change | x 889 → 1256 | **42,205 px²** | **3** (`TAPE-C\|03`, `TAPE-D\|04`, `TAPE-B\|02`) | `toast-body` |
| post-change | x 459 → 826 | **0 px²** | **0** | `tp-mat-hint` |

Narrow-viewport clamp: at a 700 px CSS viewport the computed `right` becomes `400px` (= `100vw - 300px`), toast fully on screen.
No leak: `index.html` has no `--toast-inset-right` → computed `right: 24px`.

---

## 4. Item 3 — material list re-keyed by material ID

### What it looks like now

Row = one material ID. Line 1 `자재ID · 가용 N · 사용 M · 맵칩`; line 2 = the breakdown chips `값·구간 수량`, always expanded (reading stays frictionless). Group headers are gone.

**Live `bonding_map / AAA`, before vs after:**

```
BEFORE  📦 사용 자재 8        (6 group headers: "F STACK 1 소요 100", "1 STACK 16 소요 12", …)
        ├ TAPE-A|01  209 / 33   맵 ✓
        ├ TAPE-C|03    0 / 33   맵 ✓
        └ TAPE-D|04    0 / 33   맵 ✓
        └ TAPE-B|02    0 / 90   맵 없음
        └ TOP          0 / 10   맵 ✓        <-- TOP appears twice,
        └ 1H           0 / 0    맵 없음
        └ MID          0 / 0    맵 없음
        └ TOP          0 / 12   맵 ✓        <-- total 22 shown nowhere

AFTER   📦 사용 자재 7        (0 group headers)
        1H          가용 0   · 사용 0    [1·1 0]
        MID         가용 0   · 사용 0    [1·2-15 0]
        TAPE-A|01   가용 209 · 사용 34   [F·1 34]
        TAPE-B|02   가용 0   · 사용 90   [F·2-15 90]
        TAPE-C|03   가용 0   · 사용 34   [F·1 34]
        TAPE-D|04   가용 0   · 사용 34   [F·1 34]
        TOP         가용 0   · 사용 22   [F·16 10] [1·16 12]
```

`TOP` is the case that proves the point: it is consumed by two different DOE values and the old grouping could not state its total.

### Availability — one implementation, not two

`availableOf` was the only reader of the server's `chips.remaining`; it is now a thin wrapper over a single `availabilityOf(lot, slot)`. **No availability arithmetic was added** — the server still computes `가용 = 총 − (fail ∪ transferred)`.

`availabilityOf` reads all three layers of the §6.2 defence, which the old code did not:

| server signal | old behaviour | new behaviour |
|---|---|---|
| `remaining: null` | `미상` | `미상` + reason in tooltip |
| `remaining_reliable: false` | **number shown as solid** | `미상`, raw value only in tooltip |
| `warnings[source_degraded / availability_unreliable]` | ignored | `미상` + which role degraded |
| fetch failed / `unsupported` | `미상` (indistinguishable from above) | `미상` + distinct reason |

A degraded number can no longer be presented as solid.

### Consumption — DB cross-check

Consumption comes from the same expression that writes `map_doe_source.qty`. Both call the new `bandShare(b)`.

Per-material totals and breakdowns diffed against raw `map_doe_source` rows queried directly from PostgreSQL:

```
material      DB used  UI used  match   DB breakdown -> UI breakdown
1H                  0        0  OK   {('1','1'):0}              -> {('1','1'):0}
MID                 0        0  OK   {('1','2-15'):0}           -> {('1','2-15'):0}
TAPE-A|01          34       34  OK   {('F','1'):34}             -> {('F','1'):34}
TAPE-B|02          90       90  OK   {('F','2-15'):90}          -> {('F','2-15'):90}
TAPE-C|03          34       34  OK   {('F','1'):34}             -> {('F','1'):34}
TAPE-D|04          34       34  OK   {('F','1'):34}             -> {('F','1'):34}
TOP                22       22  OK   {('F','16'):10,('1','16'):12} -> {('F','16'):10,('1','16'):12}

RESULT: PASS - UI totals equal raw map_doe_source
```

### 🔴 Pre-existing defect found and fixed: display disagreed with the database

`saveDoeToServer` stored `Math.ceil(need / n)`; `materialGroups` displayed `Math.round(need / n)`. Two implementations of one number — the exact defect class you flagged.

```
value=F band=1 qty_total=100 members=3 -> stored=34  ceil=34  (old Math.round displayed 33)
```
The live screenshot above confirms it: the old build shows `209 / 33` where the DB says 34. Both sites now call `bandShare`.

### DOE ↔ material linkage (no filtering)

Selecting a DOE row highlights the materials that use it and the matching chips only:

```
select "1" -> rows [1H, MID, TOP]                          chips [1·1 0, 1·2-15 0, 1·16 12]
select "F" -> rows [TAPE-A|01, TAPE-B|02, TAPE-C|03, TAPE-D|04, TOP]
                                                           chips [F·1 34, F·2-15 90, F·1 34, F·1 34, F·16 10]
```

---

## 5. Item 4 — legend migration prompt deleted

`maybeOfferLegendMigration`, its call site, and the `map_split_migrated_*` flag writes are gone. No stub. The replacement in the "registry empty for this map" branch resets `legendMeta = {}` and re-renders — without it the previous map's `updated_by`/`updated_at` (per-**table** carry-over) stays attached to this map's values. No dialog, no replacement toast.

Load order untouched: server split registry → localStorage cache → DEFAULT.

**Verification** — `dt_map / TAPE-A_02`, which has `map_legend_dt_map` in localStorage, no migrated flag, and no `map_split_registry` rows:

| build | `window.confirm` calls | flag written | DOE state |
|---|---|---|---|
| pre-change | `["이 맵(TAPE-A_02)의 legend 2건이 브라우저(localStorage)에만 저장되어 있습니다.\n서버 split registry로 업로드하여 팀과 공유하시겠습니까?"]` | `"1"` | — |
| post-change | `[]` | none | clean: `구간 없음`, material pane hidden |

Server-backed legend still loads — `dt_map / TAPE-C_03` (6 registry rows) renders `1 GOOD / 0 FAIL / 2 EMPTY / 3 REWORK` with no dialog.

---

## 6. Live-data safety

Every browser session ran behind a `fetch` shim that intercepted all non-GET requests. **`blockedWrites` stayed empty throughout** — the client never even attempted a write during the whole exercise.

SQL invariance across the full session:

```
table                 rows before/after     max_updated_at before/after                           verdict
map_doe               6 / 6                 2026-07-26 23:38:35.772604 / …772604                  UNCHANGED
map_doe_source        8 / 8                 2026-07-26 23:38:36.074261 / …074261                  UNCHANGED
map_split_registry    77 / 77               2026-07-26 23:38:36.596889 / …596889                  UNCHANGED
bonding_map           1756715 / 1756715     2026-07-26 23:38:35.873443 / …873443                  UNCHANGED
wafer_map_metadata    171 / 171             2026-07-26 22:51:04.777267 / …777267                  UNCHANGED
dt_map                1598 / 1598           2026-07-26 22:44:11.904513 / …904513                  UNCHANGED
core_defect_map       95312 / 95312         2026-07-26 22:51:08.107813 / …107813                  UNCHANGED
eds_fail_map          95312 / 95312         2026-07-26 22:51:14.327507 / …327507                  UNCHANGED

RESULT: PASS - zero writes to live data
```

`server/config/**` not touched. `server/**` not touched.

---

## 7. Complexity budget

| | added | removed |
|---|---|---|
| Controls (buttons/inputs/toggles) | **0** | **0** |
| Modals / dialogs | 0 | **1** (`maybeOfferLegendMigration` confirm) |
| Panels / modes | 0 | 0 |
| Status indicators (read-only) | 2 (`화면기준` chip; per-material breakdown chips) | 0 |
| Rows on `bonding_map/AAA` | — | 8 → **7** |
| Group headers | — | 6 → **0** |
| Refusal paths that blocked reading | — | **3** (`addOverlayLayer` guard, `handleAddOverlayClick` guard, forged target key) |
| Functions | 3 (`bandShare`, `availabilityOf`, `materialRollup`) | 3 (`maybeOfferLegendMigration`, `materialGroups`, `summaryStatusOf`) |

Net: nothing new to operate; one dialog and three read-path blocks removed.

---

## 8. Side-effect analysis (SDP §1)

- **Coordinate/geometry.** No transform function touched. `projectCellsToPhys`, `getCellFromVisualCoords`, `getPhysicalCoords`, `getWaferBoundingBox`, `withPhysFrame` are byte-identical. `tgtFrame` was only hoisted into a variable so its provenance could be recorded. Proven by the identical TSV digest before/after.
- **Compatibility gate.** With an empty canvas the gate compares source dims against the on-screen dims. A 40×40 source over a default 10×10 screen is refused as `align_unavailable` with an actionable message. Intended: the user picks a 규격 프리셋 first, which is the existing blank-plan flow.
- **Align-override gate.** `probeAlignDeclaration` now runs with `target_key=`. Verified live that the endpoint answers normally (`align_overrides` is keyed by **source_table**, so the declaration answer does not depend on the target key). The gate is not weakened.
- **Re-projection.** `currentGeomSignature` unchanged; `syncOverlayGeometry` still re-projects from `rawCells` + source `frame`. Physical keys stay invariant under screen manipulation.
- **Shared state.** `S.flash` keys moved from `value#seq::matKey` to `matKey`; the only producer (`rewardAfterReturn`) and consumer (`renderMaterialPane`) were updated together.
- **Prune authority.** `loadDoeFromServer` / `adoptServerDoe` / `pruneScoped` untouched. The C1 invariant (`doeServerLoaded ⇒ S.doe came from the server`) is unaffected — I added no path that populates `S.doe`.
- **Dead code from my own changes** removed: `materialGroups`, `summaryStatusOf`, CSS `.tp-mat-grp*`, `.tp-tree`, `.tp-sw.sm`.

---

## 9. Open / not done

- **C3 (`limit=500` plan cap)** unchanged — still reachable at 500+ material rows.
- **Stale align verdict**: `identity` vs `derived` is computed once when the overlay is added. Rotating the screen afterwards re-projects the cells but does not recompute the chip. Pre-existing; now more visible because `화면기준` overlays follow the screen by definition. Suggest recomputing the verdict inside `syncOverlayGeometry` as a follow-up.
- **`화면기준` will be very common** on live data (9 registered specs vs ~390k `bonding_map` keys). That is §5.0's open gap surfacing, tracked under M3, not a regression.
- **No server change is required** for any of the four items. The `source-summary` contract already ships everything the re-keyed view needs.

---

## 10. Files changed

| path | what |
|---|---|
| `client2/src/map_editor.js` | Item 1: target key from `loadedIdentity`, empty target allowed, `align.targetBasis`, `화면기준` chip, both refusal guards removed, `addOverlayForSource` no longer forges a key. Item 4: migration prompt deleted, `legendMeta` reset. |
| `client2/src/transfer_plan.js` | Item 3: `bandShare`, `availabilityOf`, `materialRollup`, re-keyed `renderMaterialPane`, `refreshMaterials`/`rewardAfterReturn` updated, writer uses `bandShare`. |
| `client2/src/transfer_plan.css` | Item 2 vars; Item 3 row/chip styles; dead group styles removed. |
| `client2/src/tokens.css` | Item 2: `#toast-container` right inset variable. |
| `client2/map_editor.html` | Item 2: sidebar inline width → CSS var. |
| `client2/dist/**` | rebuilt. |

---

## 11. For the lead — docs I did **not** touch

Another agent is active in `server/**`, so I left shared docs alone. Ready to apply at integration:

**`docs/spec/MAP_EDITOR_SPEC.md` §5.5** — mark **F2 resolved**: `addOverlayLayer`'s target key now derives from `loadedIdentity`, not `getCurrentMapKey()`.

**`docs/spec/MAP_EDITOR_SPEC.md` §5.1** — add after the frame-window paragraph:
> 타깃 규격이 없으면(미로드이거나 미등록) 타깃 프레임은 **현재 화면 컨트롤**이며, 이는 실패가 아니다 — 본딩 계획은 빈 맵에서 시작한다. 그 사실은 `align.targetBasis: 'screen'` → 목록의 `화면기준` 칩으로 드러난다. 등록 규격 기준(`'spec'`)과 절대 같은 표기로 보이지 않는다.

**`docs/spec/MAP_EDITOR_SPEC.md` §6** — add to the 6.x rules:
> 자재 수량 배분식은 `transfer_plan.js`의 `bandShare` **한 곳**이다. 저장(`map_doe_source.qty`)과 표시(사용 자재 목록)가 같은 함수를 쓴다. 종전 표시부는 `Math.round`라 DB(`ceil`)와 갈라져 있었다.

**History draft** — `docs/history/20260727_HHMMSS_m2_5_ui_fixes.md`: the four items with the digests in §2 and the DB cross-check in §4 as the 검증 section.

---

## 12. Proposed lessons for `agent_workspace/memory/client-pm.md`

1. **함정**: 공유 워킹트리에서 `git stash`로 옛 빌드를 만들면 **다른 에이전트의 진행 중 작업까지 되돌린다**(실제로 server/** 20파일을 30초간 날렸다 — 즉시 pop으로 복구). 게다가 CRLF 정규화 churn이 남는다.
   **올바른 방법**: 옛 빌드는 `git archive HEAD <path>`로 **임시 디렉터리에 추출**해 별도 포트(5173 — `config.js`가 그 포트를 devServer로 보고 API를 :8080으로 잡는다)에서 서빙한다. 워킹트리는 절대 건드리지 않는다.
2. **함정**: 같은 숫자를 저장부와 표시부가 각자 계산하면 반드시 갈라진다 — `map_doe_source.qty`는 `ceil`, 자재 목록은 `round`라 화면 33 / DB 34였다.
   **올바른 방법**: 배분·집계식은 **함수 하나**로 뽑아 쓰기·읽기가 공유한다. 검증은 **DB 원본 행과 직접 대조**한다.
3. **함정**: 좌표 회귀를 "화면이 맞아 보인다"로 판정한다.
   **올바른 방법**: 전 셀 집합의 **다이제스트**를 내고, ① 변경 전 빌드 ② 변경 후 빌드 ③ **DB 원본에서 문서화된 수식으로 독립 재계산**한 값 셋을 비교한다. 세 값이 같아야 통과다.
4. **함정**: 디버그 훅을 넣은 빌드로 검증하고 훅을 빼고 재빌드한 뒤 "같은 코드니 괜찮다"고 넘어간다.
   **올바른 방법**: 훅 없이도 되는 검증 경로(가져오기 → Copy to Excel + `navigator.clipboard` 캡처 shim)를 우선 쓰고, 훅이 필요했다면 **최종 번들에서 전 항목을 재실행**한다.
5. **함정**: 사용자가 지목한 거절 문구 한 곳만 고친다.
   **올바른 방법**: 같은 동작을 막는 관문을 **전수 조사**한다(이번엔 3곳 — 실제로 사용자가 본 것은 지목되지 않은 `handleAddOverlayClick` 쪽이었다).
