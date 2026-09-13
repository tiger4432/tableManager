# Map/DOE — V1 effort instrument wiring

> **Scope:** MAP + PLAN pages only. Consumer of `client2/src/effort_meter.js` (Lead PM contract, built by client-pm).
> **Date:** 2026-07-29 · **Agent:** map-pm · **Tier:** T2

## What changed

`client2/src/map_editor.js` only (+94 / −3). It starts the shared session and installs the module's
page-wide listeners, declares the four screen transitions only this file can see (`countNav`), and rides
`effort: snapshot()` on the **existing** cell batch update in `pushMapData`, resetting via `commit()`
exclusively on that request's success branch.
`transfer_plan.js`, `transfer_plan.css`, `map_editor.html`: **zero changes** — the panel lives in the same
document, so the module's document-level listeners already cover it, and its only screen moves route
through `openMapFrame`/`popMapFrame`.

**Complexity budget: net added controls 0, removed 0.** No panel, badge, toast, modal, or DOM node was
added. The one HTML anchor id I first added was reverted after switching to the shared
`installNavLinkCounting` helper.

## StableDevelopmentProtocol §1 — side-effect analysis

| Axis | Finding |
|---|---|
| **Coordinate system / geometry** | **Untouched.** No change to `getPhysicalCoords`, `getCellFromVisualCoords`, `getWaferBoundingBox`, `withPhysFrame`, `frameFromMeta`, the overlay layer, or any `canvas.width`/DPR path. Instrumentation reads no coordinate and writes none. Invariant ① (one transform implementation) and ② (`wafer_map_metadata` is the only alignment basis) are not in the blast radius. |
| **Mouse → cell mapping** | The module's listeners are `mousedown`, **capture phase, `passive: true`**. They never `preventDefault`/`stopPropagation`, so `initMouseDragEvents`' paint/erase/origin handling, drag box selection, and hover coordinates are byte-identical in behaviour. Verified live: paint/drag still functions after install. |
| **Shared mutable state** | Adds no module state except two `const` route ids and `effortRoute()`, which **reads** `editorFrames.length` and mutates nothing. Counters live in the module's `sessionStorage`, not in `state`/`gridData`/`legend`. |
| **Timing / re-entrancy** | The Load handler became `async` and now `await`s a promise that was previously fire-and-forget. It does not gate the load itself — `loadExistingMap` still runs identically; only the `countNav` decision happens afterwards. No new debounce, rAF, or WS interaction. |
| **Data-protection gates (4) in `pushMapData`** | **Order preserved and unmodified**: gate 4 (log-shaped target) → identity-mismatch confirm → contrast guard → empty-payload → missing-desc confirm → C5 replace confirm. Every instrumentation touch is strictly *after* all six, so no gate can be reordered or short-circuited. A push refused by any gate performs zero requests and leaves the counters untouched (harness A7). |
| **Draft-survival paths** | `scheduleCellDraft`, `saveDoeDraft`, `readDoeDraft`, `applyDoeDraftRecord` and the load-path precedence are **not referenced or modified**. Confirmed by the removed-lines audit: the entire diff deletes exactly 3 lines (2 rewritten handlers + the `replace_map: true` payload line). |
| **Server/client contract** | `effort` is an **optional** field already declared on `GeneralUpdateBatch` (`server/database/schemas.py:115`). Omission means "unmeasured", not zero. Absent the field the endpoint behaves exactly as before. |
| **Scale (§2)** | Payload grows by one flat object of 4–5 integers per push, independent of cell count. No new query, loop, or round trip. |

## Verification

**1. Harness — `client2/tests/effort_instrument_harness.mjs` (new): 23 passed / 0 failed.**
It lifts the **real** `pushMapData`, `openMapFrame`, `popMapFrame` bodies from source into a `vm` sandbox
(same technique as `push_gate_harness.mjs`), so every assertion executes the branch it claims to test.
Evidence is a **request list**, not "it worked":

- `A1` cell batch body carries `effort` verbatim; `A2` the `wafer_map_metadata` body carries none (**deep scan**, not top-level only); `A4` exactly 2 requests.
- `A3` on success: `snapshot,commit`. `A5`/`A6` on a **500 from the cell push**: `snapshot` only — counters intact for the retry.
- `A7` gate-refused push: **0 requests, 0 effort calls.**
- `B1`–`B8` one `countNav` per completed move, with the correct route pair at depth 0 and nested; **no** nav on a cancelled open, a stack-too-deep refusal, or a declined back-confirm.

**2. Mutation — 8 defect variants, every one breaks its check.** A green suite against a broken source
proves nothing, so each behaviour is re-run against a deliberately defective source:

| Mutant | Effect on the check |
|---|---|
| M1 `commit()` moved off the success branch | A3/A5 → `commit,snapshot` (resets on a *failed* save) |
| M2 `effort` dropped from payload | A1 → `null` |
| M3 / M3b effort also on the metadata push (top-level / nested) | A2 → `HAS-EFFORT` |
| M4 frame nav emitted before the load | B3 → counts a cancelled open |
| M5 `from` captured after the push | B1 → `material>material` |
| M6 pop nav before the pop | B6 → `material>material` |
| M7 pop nav before the unsaved-edit confirm | B8 → counts a move the user declined |

> Trap hit and fixed mid-run: the source is **CRLF**, so multi-line mutation patches silently failed to
> apply and the suite reported "ok" for defects it had never injected. The harness now normalizes to LF
> and **fails loudly** if a patch does not apply (`mutation did not apply (source drifted)`).

**3. Live browser (dev :5173 → API :8080), read-only.** A `fetch` shim rejected every non-GET;
**`blocked: []` — no write was ever attempted**, and ⚡ Push was never clicked. Counter trace:

| Action | key | mouse | nav |
|---|---|---|---|
| page load (boot restore + its frame-choice modal) | 0 | 0 | **0** ← boot path correctly scores nothing |
| 1 real click (cancel modal) | 0 | 1 | 0 |
| 5 bare modifiers dispatched (`Shift/Control/Alt/Meta/CapsLock`) | 6→**+0** | — | — |
| each of `a` / `a`(repeat) / `Enter` / `v` | **+1 each** | — | — |
| table switch `bonding_map → dt_map` | 6 | 1 | **1** |
| Load with **empty** key (cancelled) | 6 | **2** | **1** ← click counted, no nav |
| Load `dt_map · TAPE-A/01` (2,313-row map, succeeded) | 6 | 3 | **2** |
| 「← Back to Grid」 | 6 | **5** | **4** |

Counters survived the **full page load** into `/index.html` with the same `session_id` — invariant 2
verified in a real browser. The live process predates the new route, so `GET /api/effort/config` returned
**404** and the module **failed closed** (every transition counted) — invariant 3 exercised for free.

**4. Regression.** `npm run build` clean (dist synced). `push_gate_harness` 15/15,
`effort_meter_harness` 71/71, contract harnesses unchanged.
Pre-existing, **not caused by this round**: `client2/tests/split_registry_harness.mjs` crashes with
`const DEFAULT_LEGEND not found` — reproduced identically on a clean tree (stash/pop).

## Proposed context-preserving transitions (for your merge — I did **not** populate the allowlist)

Route ids are **table-agnostic** on purpose: the DOE→material detour is declared once, not once per stage
table, and a new stage table needs no config edit.

**Propose score 0 (context-PRESERVING):**

1. **`map_editor:material > map_editor`** — frame pop. *Strongest case.* `restoreEditorState` restores
   gridData, legend, `legendVocabularySeed`, overlay layers, canvas scroll position, meta inputs,
   rotation/side/physical spec, and the `legendDirty`/`frameTouched`/`framePushed` flags **verbatim**.
   The user returns to the screen they left, not to a rebuilt one. Charging 5 here would penalise the
   round trip the design deliberately made lossless.
2. **`map_editor > map_editor:material`** — frame push. This is the user's named *"DOE → dt map routing"*.
   The parent frame is **snapshotted, not destroyed**; a breadcrumb shows the trail and return is
   guaranteed. The user selected that exact material from the rollup row — the destination is the
   context, not a departure from it.

**Propose leaving COUNTED (do not declare):**

3. **`map_editor > map_editor`** — table switch / map load. Grid wiped, DOE reseeded to one empty row,
   overlays cleared (with a toast), identity pin voided. Real context loss.
4. **`map_editor > grid`** — full page load; nothing survives.

⚠️ **Known conflation to decide on:** #3 covers **both** the table dropdown and the Load button, because
`countNav(from, to)` names *places*, not *actions*. Both are context-losing today so they would be
declared identically — but if you ever want to zero map **Load** (the read-heavy "browse past maps" flow
the charter calls 무마찰), that same declaration would also zero table switches. Say the word and I will
split the vocabulary; I did not invent a third route id unilaterally.

## Escalations

**E1 — `nav_preserved` is silently dropped by the server (cross-domain, HIGH).**
client-pm's module now records declared-preserving moves in a separate `nav_preserved` counter so the
allowlist stays a *query-time* reinterpretation — exactly what board item 0 asks for. But
`schemas.EffortReport` declares only `session_id/key/mouse/nav`, and `main._validate_effort` iterates
`("key","mouse","nav")`. Pydantic v2 defaults to `extra='ignore'`, so the field is dropped **with no error
and no 422**. Measured directly:

```
client sent      : {'session_id': 's1', 'key': 11, 'mouse': 7, 'nav': 2, 'nav_preserved': 5}
server model has : {'session_id': 's1', 'key': 11, 'mouse': 7, 'nav': 2}
nav_preserved kept: False
```

Nothing breaks and `nav` is correct, so **V1 still works** — but the historical-reinterpretation goal is
defeated, and this is the exact failure class this domain exists to catch (screen fine, value quietly
gone). Needs a server-pm + client-pm decision: store it, or drop it from the client. Not mine to fix.

**E2 — `installNavLinkCounting(fromRoute)` takes a static value (LOW).**
Leaving the editor from **inside** a material frame is recorded as `map_editor > grid`, not
`map_editor:material > grid`. Score is identical either way (both counted), so this is analysis
granularity only. A getter (`() => effortRoute()`) would fix it if you want depth fidelity.

**E3 — route vocabulary must be agreed before the config ships.**
The served allowlist is keyed on exact ids. Mine are `map_editor` and `map_editor:material` (matching the
module's documented `page:subcontext` convention and its own `map_editor:material` example). Please
confirm client-pm's proposed list uses the same strings before `effort_metric.json` is written.

## Living-doc update points (doc-keeper's, not mine — I edited no docs)

Looked up by code path in `DOC_OWNERSHIP.md`:

- **`spec/MAP_EDITOR_SPEC.md §6`** (DOE 저장 분해도 / push contract) — the push payload now carries an
  optional `effort` object; the metadata push and registry write deliberately do not.
- **`map_editor/README.md`** (웨이퍼 맵 에디터) — the editor starts an effort session on load; frame
  push/pop, table switch, map load and page exit are counted transitions.
- **`architecture/PRIMITIVES.md`** — candidate new primitive: *"계측은 기존 쓰기에 얹는다"* (instrumentation
  rides the existing write; never a second request, reset only on that write's success).

## Proposed lesson for `agent_workspace/memory/map-pm.md` (your call, not added by me)

- **함정:** 여러 에이전트가 같은 워크트리에서 동시에 일할 때 `git stash`로 "변경 전 상태"를 재현하면
  **남의 진행 중 작업까지 통째로 들어갔다 나온다.** 이번에 client-pm·server-pm의 미커밋 파일 20여 개가
  함께 stash됐다(pop으로 전량 복구 확인).
  **올바른 방법:** 회귀 여부는 `git stash` 대신 **`git show HEAD:<path>`를 임시 파일로 뽑아** 대조한다.
- **함정:** 소스가 CRLF인데 하네스가 `\n` 다중행 문자열로 뮤테이션을 주입하면 **패치가 조용히 실패**하고
  주입한 적 없는 결함에 "ok"가 찍힌다.
  **올바른 방법:** 읽는 즉시 LF로 정규화하고, **패치 미적용을 실패로 처리**한다(`mutated === SRC` 검사).
