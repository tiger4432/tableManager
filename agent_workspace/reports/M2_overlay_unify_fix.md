# M2 Overlay Unification — Blocking Fixes (B1, B2) + Cheap Cleanups (F4, F5)

> **Agent:** client-pm / 2026-07-26 · **Target:** `client2/src/map_editor.js` (uncommitted working tree)
> **Scope:** the 2 blockers from review B only, plus the 2 cheap cleanups from review A. Nothing else.
> **Not committed.** Build artifacts regenerated (`npm run build`).

---

## 1. Summary

| ID | Defect | Fix | Live-verified |
|---|---|---|---|
| **B1** | Source-meta fetch returning 5xx silently fell back to identity and drew at wrong coordinates, labelled "무보정 / 소스 맵 규격 미등록" (a false reason) | `fetchGridMetaFor` now separates *no row* (null) from *could not confirm* (throw); `addOverlayLayer` surfaces it as a `meta_unavailable` failure row and does not draw | ✅ |
| **B2** | `align_override_declared` gate was fail-open — one dropped probe request and a declared override was ignored while the chip read "정렬됨" | `probeAlignDeclaration` throws on non-404/405 failure; caller refuses with `align_unconfirmed`. 404/405 (old server) still passes through | ✅ |
| **F4** | `count: cells.length` over-reported (raw row count, ignored key collisions and off-grid projection) | `count: projected.size`; off-grid cells counted and exposed in the reason line when non-zero | ✅ |
| **F5** | Render-loop comment still described the old server-aligned contract; 4 unused locals in a per-cell hot path | Comment rewritten to the new design; dead locals deleted | ✅ |

The common root was already solved in this same file. `fetchPaintRules` (`:82-123`) carries an explicit `[M2 수정]` comment establishing the rule: **distinguish "there is no declaration" (404/405) from "we could not confirm" (anything else).** Both new overlay paths had skipped that discipline. Both now follow it — no new pattern was invented.

---

## 2. Diff summary

All changes are in `client2/src/map_editor.js`.

**B1 — `fetchGridMetaFor` (`:2463`)**
```js
if (res.status === 404 || res.status === 405) return null;      // no spec table on this server
if (!res.ok) throw new Error(`맵 규격 조회 실패 (HTTP ${res.status})`);
```
The only other caller, `loadExistingMap:2575`, already wraps this in a `try/catch` that degrades to `loadedGridMeta = null`, so its behavior is unchanged (a network error already threw there before this change).

**B1 — `addOverlayLayer` step ③/④**
Cell fetch and the two meta fetches were sharing one `try/catch`, which would have reported "could not confirm the spec" as "cell fetch failed". Split with `Promise.allSettled` — still three parallel requests, **no extra round trip**:
```js
const [cellR, sMetaR, tMetaR] = await Promise.allSettled([...]);
// cell failure  -> 'error'  (셀 조회 실패)
// sMeta rejected -> 'meta_unavailable' (소스 맵 규격을 확인하지 못했습니다)
// tMeta rejected -> 'meta_unavailable' (타깃 맵 규격을 확인하지 못했습니다)
```

**B2 — `probeAlignDeclaration` (`:4033`)**
The blanket `catch { return null; }` and `if (!res.ok) return null;` are gone:
```js
if (res.status === 404 || res.status === 405) return null;   // old server: no declaration path
if (!res.ok) throw new Error(`HTTP ${res.status}`);
```
Caller wraps the probe and refuses with `align_unconfirmed` on throw. The old comment's premise — *"old servers and network errors are not grounds to block"* — conflated two different things; only the old-server half survives.

**F4** — `count: projected.size`, plus an off-grid count appended to the reason when non-zero.

**F5** — render-loop comment at `:1752` rewritten (physical-key contract, not server-aligned coordinates); the 4 unused locals and their dead `side === 'back'` negation removed from `getPhysicalCoords`.

### F4 accuracy correction (found during verification)

My first F4 attempt claimed the off-grid cells "화면에 표시되지 않습니다". **That claim was false.** The render loop sweeps a 3×3 tile window (`:1658-1671`), so an off-grid cell can still be painted in the margin. Measured: 139 projected / 11 off-grid, but 132 markers actually drawn — 7 off-grid cells were painted anyway.

I then tried reconstructing the renderer's exact visited-key set, which was also wrong (viewport- and zoom-dependent, so not a stable property to report). Final form reports the **frame-defined, stable** quantity — cells outside the canonical `[0,cols) × [0,rows)` grid — with wording that is verifiably true:

> `격자 밖 N칩 — 웨이퍼 격자를 벗어나 가져오기에서 제외됩니다`

Verified against `importOverlayToGrid:4379`, which excludes any key not in `insideKeys` (cells inside the wafer circle). Off-grid ⊆ excluded-from-import, so the statement holds.

---

## 3. Live evidence

Built bundle `map_editor-DRIw8D4k.js`, served from the running server on :8080. Base map `bonding_map/AAA` (29×25). Overlay source `bonding_map/aa223`.

Method: a `fetch` shim that (a) logs every outgoing request, (b) injects a failure into **exactly one** matching request (`used` flag enforces the count), and (c) hard-blocks every non-GET as a safety guard. Marker counts are **not** read from the list label — they are counted from actual `CanvasRenderingContext2D.arc` calls during a forced re-render, calibrated against a toggle-off baseline (1 non-marker arc, subtracted).

| # | Injection | Failure row | Markers drawn | Injected count |
|---|---|---|---|---|
| T1 | none (regression) | — success, `139칩 정렬됨` | **139** | 0 |
| T2 | **source** meta → 500 | ✅ `meta_unavailable` | **0** | 1 |
| T3 | **target** meta → 500 | ✅ `meta_unavailable` | **0** | 1 |
| T4 | probe → network drop | ✅ `align_unconfirmed` | **0** | 1 |
| T5 | probe → 503 | ✅ `align_unconfirmed` | **0** | 1 |
| T6 | probe → **404** | — success (passes through) | **139** | 1 |
| T7 | probe → **405** | — success (passes through) | **139** | 1 |
| T8 | probe → `origin:"declared"` | ✅ `align_override_declared` | **0** | 1 |
| T9 | source meta → 200, empty rows | — success, `무보정` (genuine "no row") | 139 | 1 |
| T10 | source spec START (6,5) | — success, `격자 밖 27칩` in reason | 119 | 1 |
| T11 | source spec rot 90 | — success, `격자 밖 13칩` in reason | 128 | 1 |

Request lists (T2, source meta 500) — cell fetch and target meta both succeed; only the source meta is injected:
```
    /api/maps/overlay?target_table=bonding_map&target_key=AAA&sources=bonding_map%3Aaa223&limit=1
    /tables/bonding_map/data?limit=2001&filters=...
[INJECT 500] /tables/wafer_map_metadata/data?limit=2&filters=...   <- source (aa223)
    /tables/wafer_map_metadata/data?limit=2&filters=...            <- target (AAA)
```
T4/T5 (probe failure) emit **one** request total and stop — the gate refuses before any cell fetch.

Tooltip text on the new failure rows (Korean, user-facing):
- `meta_unavailable` → `bonding_map: 소스 맵 규격(wafer_map_metadata)을 확인하지 못했습니다 — 맵 규격 조회 실패 (HTTP 500). 규격을 모르는 채로 겹치면 좌표가 조용히 어긋나므로 겹치지 않습니다.`
- `align_unconfirmed` → `bonding_map: 계측 보정(align override) 선언 여부를 확인하지 못했습니다 — HTTP 503. 선언이 있는데 무시하고 겹치면 조용히 틀린 그림이 되므로 겹치지 않습니다.`

Both rows keep the retry (`↻`) button, so the state is recoverable.

### Defect-version self-check (the check that actually proves the test works)

Reverting `client2/dist` to `HEAD` was **not** a valid control — HEAD holds the *pre-unification* build (server-driven overlay), which fails these tests for the wrong reason. So I built a true defect variant: current source with **only** the two guards reverted (`fetchGridMetaFor` → `return null`, `probeAlignDeclaration` → `try/catch return null`), bundle `map_editor-CCKtCkd_.js`.

| Case | Defect variant | Fixed |
|---|---|---|
| source meta 500 | **success row**, `139칩 무보정`, tooltip `소스 맵 규격 미등록`, **132 markers drawn** | fail row, 0 markers |
| probe network drop | **success row**, `139칩 정렬됨 90°`, no sign the override was ignored | fail row, 0 markers |

Both blockers reproduce exactly as review B described, and both disappear with the fix. The verification is therefore sensitive to the defect — it is not a vacuous pass.

---

## 4. No writes, no config changes

- **Config untouched.** sha256 before == after for all of `server/config/*.json`, including `map_overlay_config.json` (`96fc785f…`), `table_config.json` (`226d7956…`), `maps.json` (`5fcc8c8a…`). **B2 did not require touching `align_overrides`** — the fix concerns probe *failure*, so a declared override was simulated by injecting the response body instead. No user asset was modified or copied over.
- **DB writes: 0.** The shim blocked every non-GET; `blockedWrites` stayed **empty** for the whole session, meaning no write was even attempted.
- `bonding_map` rows **UPDATED** (`updated_at <> created_at`) since baseline: **0**.

**Observation — live data shifted mid-session (not caused by this work).** `bonding_map` went 1,756,716 → 1,756,739 → +113 rows for `base='AAA'`, all with `created_at == updated_at == 22:45:21.645616` (pure INSERT), and `(bonding_map, AAA)`'s metadata row was rewritten at `22:45:21.618836` — 27 ms earlier, the ingestion's own metadata upsert. `server/auto_update.log` confirms the scheduler running (22:46, 22:47). This matches the ~6-minute cadence already documented in review A §6.

Consequence for the record: **AAA's stored rotation changed 270° → 0° partway through testing.** That is why T1's label reads `139칩 정렬됨 90°` in the earlier runs and `139칩 정렬됨` in the later ones — the rotation difference vanished, leaving only `면(front→back)`. **The marker count stayed 139 in both**, so the regression baseline holds either way. Anyone re-running these numbers against live data should expect the label to track whatever AAA's current metadata says.

---

## 5. Documentation correction

Implementation report `M2_overlay_unify_client.md` §5-1 states *"선언이 있으면 명시 실패"* (an explicit failure whenever a declaration exists). That is **still not universally true** and the wording should be narrowed:

- **True now:** when the probe *succeeds* and returns `origin` of `declared`/`default`, and — after this fix — when the probe fails for any reason other than 404/405.
- **Still false for B3** (deferred to backlog by instruction): a declaration scoped to `by_eqp` only is invisible to this gate, because the probe reads `align_applied.origin` from a single overlay row. The correct fix is a server contract change (an `align_declared` flag), so the client cannot close it alone. Currently unreachable on live data (no such override declared).
- **Still false for 404/405:** an old server that lacks `/api/maps/overlay` passes through unchecked by design.

Suggested replacement: *"A declaration blocks drawing whenever the gate can see it — i.e. the probe succeeded and reported `origin: declared|default`, or the probe failed in a way that could indicate a hidden declaration. `by_eqp`-scoped declarations and pre-`/api/maps/overlay` servers are outside the gate's visibility (B3, backlog)."*

---

## 6. Untouched (backlog, per instruction)

B3, B4 (1→5 requests, 12ms→53ms), B5 (overlay persists across table switch — pre-existing), B6, B7, B8, and review A's F1, F2, F3. No code was touched for any of these.

---

## 7. Proposed lessons (for lead-PM review — not added directly)

**client-pm section:**

- **Trap:** A "graceful degradation" path that returns the same value for *"the declaration does not exist"* and *"I could not read it"* becomes a silent-wrong-output generator the moment either branch feeds a rendering decision. In this batch the identical bug was written **twice** (`fetchGridMetaFor`, `probeAlignDeclaration`) in a file that **already contained the corrected pattern with a comment explaining it** (`fetchPaintRules:82-123`).
  **Right approach:** Before adding a fallback, ask which of the two questions the `null` answers. If it can answer both, split it: 404/405 = "absent", everything else = throw, and let the caller decide whether absence is drawable. Grep the file for an existing precedent before writing a new failure path.

- **Trap:** Reverting `dist` to `HEAD` looks like a defect-version control but is not one when the working tree contains a whole uncommitted redesign — HEAD is the *previous architecture*, so the test fails for an unrelated reason and proves nothing.
  **Right approach:** Build the defect variant from the *current* source with only the specific fix reverted. Confirm the bundle hash/name actually changed and that the failure reproduces with the *expected symptom*, not merely "failed".

**Common section:**

- **Trap:** Shipping a new user-facing number or label without checking that the sentence attached to it is true. The F4 count was going to ship saying cells "are not displayed" when 7 of 11 were in fact painted in the margin tile window.
  **Right approach:** Measure the claim, not just the number. If the true quantity turns out to be viewport- or state-dependent, report the stable one and reword — do not report an unstable quantity with confident wording.

- **Trap:** Treating live-DB drift as test noise. `bonding_map` gained 113 rows and `AAA`'s rotation flipped 270°→0° mid-session, silently changing an expected label.
  **Right approach:** Snapshot `count(*)`/`max(updated_at)` before and after, and separate *inserted* (`created_at == updated_at`) from *updated* rows. A changed expected value is only acceptable once you have shown which process caused it.
