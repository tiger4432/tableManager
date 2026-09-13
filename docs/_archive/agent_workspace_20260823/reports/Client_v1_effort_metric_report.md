# Client CORE — V1 interaction-score instrument

> client-pm · 2026-07-29 · queue item 0 (client core half). Map/plan half: map-pm. Receiving half: server-pm.
> **Round 2 (Lead PM decisions applied)** — see "Round 2" section at the end for items 1/2/3/6.

## What changed

- **New `client2/src/effort_meter.js`** — the single client-side collector for core value #1's canonical instrument. Implements the Lead-PM contract verbatim (`startSession`/`countKey`/`countMouse`/`countNav`/`snapshot`/`commit`); stores raw counts + a session UUID in `sessionStorage['assy.effort']`; classifies transitions from the server-served `GET /api/effort/config`.
- **Main grid wired** — all 5 human write paths attach `effort` to the existing `PUT /tables/{t}/data/updates` and call `commit()` only on `res.ok` (`api.js`, `main.js`, `ui.js`, `clipboard.js` ×2); 9 screen-transition points counted (`main.js`, `timeline.js`, `trace_launch.js`).
- **New `client2/tests/effort_meter_harness.mjs`** — 64 assertions incl. self-mutation checks. No UI added anywhere.

## StableDevelopmentProtocol §1 side-effect checklist

| Vector | Finding |
|---|---|
| **Event flow / starvation** | All three global listeners are `capture` + `passive:true`. `passive` makes `preventDefault` **impossible at the browser level**, and I never `stopPropagation`. This structurally cannot repeat the 2026-07-27 incident where a keydown branch starved the `copy` handler. `clipboard.js` drag-select and `map_editor.js` painting `mousedown` paths verified unaffected. |
| **Shared mutable state** | `state.js` untouched. Counters live only in the module + `sessionStorage`. `commit()` sits adjacent to `state.pendingTxEdits = {}` but does not read or write it. |
| **Timing / re-entrancy** | `commit()` is gated on `res.ok`, i.e. after the server committed. **Known issue:** two concurrent non-Tx saves both snapshot pre-reset, so the same effort is attributed to two tx rows. Direction is *inflating*, never flattering — disclosed, not hidden. |
| **Reload / unload** | `sessionStorage` write-through is synchronous, so `countNav` durably lands before `location.href` assignment and before anchor navigation (capture-phase listener runs first). |
| **Boundary contracts** | **None broken.** No endpoint path, WS event, cell shape `{value,is_overwrite,priority_source}` or `/schema` change. `effort` is an additive optional field on an existing PUT; no separate telemetry request. |
| **Scale (§2)** | Payload is 4 scalars **independent of batch size** — a 10,000-row paste carries the same. No new queries, loops, or full loads. |
| **Insecure context** | `crypto.randomUUID` is secure-context gated and is `undefined` in production (plain-HTTP intranet) — the same trap that killed `navigator.clipboard`. Primary path is `crypto.getRandomValues` (not gated), with a `Math.random` last resort. |
| **Duplication** | Verified in the built bundle: `assy.effort` and `api/effort/config` each appear in exactly **one** chunk. Route→path table, session-id generator and global listeners all live inside the one module, so no page has a reason to copy them. |

## Verification

- Harness **64/64 pass**. Includes a **mutation check**: deliberately broken builds (a `snapshot()` that resets; a config path that fails *open*) are both **detected** — without this the assertions would prove nothing.
- Failure paths actually executed, not assumed: config reject / 404 / garbage entries / pre-config race / `sessionStorage` read+write throwing / corrupt JSON / `randomUUID` absent, present-but-throwing, and no `crypto` at all.
- `npm run build` **succeeded**; the two warnings are pre-existing. Bundle greps confirm `effort:` attached exactly 5× in `main` (matching the 5 write paths).
- **Server contract cross-checked against server-pm's actual code**: `get_public_config()` returns `{weights, context_preserving_transitions}` with transitions as `{from,to}` **objects** — my parser accepts both object and string forms, so it is compatible. Server 400s on empty `session_id` / non-integer / negative counts; my `toCount` guarantees non-negative integers and `ensure()` always yields a non-empty id.
- **Cross-agent check**: map-pm consumed the module in the same tree using only `countNav` manually plus one `installGlobalListeners()` — **no double counting**, no second collector.

## One bug found and fixed by the harness

A `"*>*"` wildcard entry was being retained as an inert literal key. Harmless in effect, but a config author would see it in `getConfig()` and **believe a whole class of moves had been exempted**. `transitionKey` now rejects any id containing `*`, so it fails visibly instead of silently.

## PROPOSED transition list — needs your approval

Shipped with the allowlist **empty**: every transition below currently scores as context-losing. Nothing here is active until you approve it and server-pm's config declares it.

### Recommend PRESERVING (score 0)

| Transition | Reasoning |
|---|---|
| `map_editor > map_editor:material` | **Your user's example** (DOE → dt map). Frame push: breadcrumb + back button present, prior state snapshotted. The system routes you to exactly what you asked to edit. |
| `map_editor:material > map_editor` | **Strongest case in the set.** `restoreEditorState` restores the prior screen *verbatim* — table, grid, legend, scroll. Nothing is lost by definition. |
| `grid > trace` | Opens in a **new tab**; the grid is literally still sitting there untouched, and the selected rows are carried as seeds. Context preserved in the most literal sense available. |
| `grid > grid:log_jump` | Clicking a history entry means "take me to this change" and the system lands you exactly there. Structurally the same shape as the DOE→map example. ⚠️ Caveat: it can cross tables, so it is not *free* — flagging rather than assuming. |

### Recommend COUNTED (leave undeclared)

`grid > grid:table` (schema/data/pending edits all discarded) · `grid > map_editor` · `grid > admin` · `grid > graph` · `map_editor > map_editor` (grid wiped, DOE reseeded, overlays cleared) · `map_editor > grid` (full page load) · `map_editor:material > map_editor:material`.

### Needs your call

1. **`grid > enrichment` is ambiguous — two triggers share one key.** The generic menu link carries nothing; the 결손 badge carries `?rule=` and *is* a targeted continuation of the same correction. If you want the badge exempted but not the menu link, say so and I will split the destination id (e.g. `enrichment:rule`). I did **not** split it unilaterally, because a finer id only matters if you intend to exempt it.
2. **`grid > grid:viewmode`** (pagination ↔ infinite) — weak. Same data, but refetches from skip 0 and loses scroll.
3. **Are modals "screen moves" at all?** Sources modal, clipboard-type chooser, map choice modal are currently **not counted**. That is the *flattering* direction, so I am flagging it explicitly rather than letting it pass silently.

### Finding that changes one of your candidates

Your candidate **"grid → map editor for the row being edited" does not exist.** The only grid→map_editor path is the generic nav-dropdown link, which carries no row. There is nothing to declare preserving here — carrying the edited row into the map editor would be a **feature to build** (a natural fit for queue item 0b), not a config entry.

## Escalations

1. **`enrichment.js` writes corrections but is uninstrumented** (`enrichment.js:470` PUTs to `/data/updates` with no `effort`). Per contract that reads as "unmeasured", not zero, so it will not dilute the average — but the Enrichment conveyor is plausibly the *lowest-effort* correction surface in the product, and right now we cannot prove it. It was outside my stated scope; recommend a follow-up before the R1 comparison.
2. **I added three exports beyond your six**: `installGlobalListeners()`, `installNavLinkCounting()`/`routeFromHref()`/`currentRoute()`/`ROUTES`, and `getConfig()`. None rename or reshape the contract. Rationale: without them each page would hand-roll its own listeners and path→route table — the exact duplication you told me to prevent. map-pm independently consumed them, which is the outcome I was aiming for. Flagging for the record.
3. **`dist/` must be rebuilt by you after integration.** The bundle I produced includes map-pm's in-progress `map_editor.js` from this shared tree; it will be stale the moment they touch it again.
4. **I did not commit.** Three agents are editing this same working tree (server-pm's `effort_metric.py` and map-pm's map edits are both present here), so staging is yours.

## Proposed memory lesson (not added directly)

> **Trap**: `crypto.randomUUID` is secure-context gated and is `undefined` in production (plain-HTTP intranet) — the same gate that makes `navigator.clipboard` undefined. Code that "worked on localhost" throws in the field.
> **Correct approach**: use `crypto.getRandomValues` (not gated) as the primary path; treat `randomUUID` as an optimisation inside `try`. `enrichment.js:64` already had a fallback — check for an existing guard before writing a new generator.

## Files changed

| Path | Change |
|---|---|
| `C:\Users\kk980\Developments\assyManager\client2\src\effort_meter.js` | **New** — the one collector |
| `C:\Users\kk980\Developments\assyManager\client2\tests\effort_meter_harness.mjs` | **New** — 64 assertions + mutation self-check |
| `C:\Users\kk980\Developments\assyManager\client2\src\main.js` | session start, global listeners, nav-link counting, Tx batch `effort`+`commit`, badge/table/viewmode nav |
| `C:\Users\kk980\Developments\assyManager\client2\src\api.js` | single-edit `effort` + `commit` |
| `C:\Users\kk980\Developments\assyManager\client2\src\ui.js` | range-fill `effort` + `commit` |
| `C:\Users\kk980\Developments\assyManager\client2\src\clipboard.js` | paste + clear-cells `effort` + `commit` |
| `C:\Users\kk980\Developments\assyManager\client2\src\timeline.js` | `navigateToLog` nav count |
| `C:\Users\kk980\Developments\assyManager\client2\src\trace_launch.js` | trace new-tab nav count |
| `C:\Users\kk980\Developments\assyManager\docs\architecture\frontend.md` | new §3.2 + module table row + badge |
| `C:\Users\kk980\Developments\assyManager\docs\history\20260729_074223_effort_meter_client_core.md` | history entry (index regenerated) |

---

# Round 2 — Lead PM decisions applied (2026-07-29)

## 1. Contract addendum: `nav_preserved` — DONE

`countNav` no longer discards exempted transitions. Both buckets are raw counts:

```js
const s = ensure();
if (preservingSet.has(key)) s.nav_preserved += 1;   // preserving (currently scored 0)
else s.nav += 1;                                     // context-losing (scored)
```

Wire shape is now `effort: {session_id, key, mouse, nav, nav_preserved}`, optional as before. Client-side classification is unchanged — only the discard was removed. Plumbed through `ensure()`, `snapshot()`, `commit()` and storage; entries written before the addendum lack the key and sanitise to 0 (covered by a test).

You were right that this matters more than the weights case. Weights are reinterpretable because the raw counts survive; a discarded transition leaves nothing to reinterpret, and this metric cannot be recomputed after the fact.

## 2. Allowlist — no client code change needed; config not yet installed

Nothing to ship client-side: the allowlist is served, and I never shipped a populated one. `grid > grid:log_jump` remains unexempted as instructed — and with the `nav_preserved` split that is now a reversible call.

**`server/config/effort_metric.json` does not exist yet** (only `.sample`). Until it does, every transition counts as `nav`, which is the safe default. The approved content, for whoever installs it — I did not create it myself, since it lives in server-pm's directory and creating it also *activates* a config:

```json
"context_preserving_transitions": [
  { "from": "map_editor",          "to": "map_editor:material" },
  { "from": "map_editor:material", "to": "map_editor" },
  { "from": "grid",                "to": "trace" },
  { "from": "grid",                "to": "enrichment:rule" }
]
```

## 3. `grid > enrichment` split — DONE

Badge with a rule emits `enrichment:rule`; badge without one emits `enrichment`, same as the generic menu link. Verified the badge is a bare `<span>`, not nested in an anchor, so the delegated nav-link listener does not also fire on it.

## 6. `enrichment.js` instrumented — DONE

`effort` attached to the conveyor's existing PUT, `commit()` only on success, plus `startSession`/`installGlobalListeners`/`installNavLinkCounting` at init (without the listeners the page would report typed corrections as zero keystrokes, which understates and therefore flatters).

`commit()` is placed **before** the existing stale-session guard: if the rule switches mid-save the UI update is skipped, but the server committed and the effort was already reported. Rule switching is counted on the `change` handler, not inside `selectRule()`, which boot deep-links also call. The refresh button re-reads the same rule and is deliberately not counted.

## 5. Extra exports promoted to contract — DONE

Documented as contract in the module header and in `frontend.md` §3.2, with the reason attached so a future reader does not "tidy them away".

## Verification (round 2)

- Harness **71/71**, now with a third mutation: *exempted transition discarded*.
- **The mutation check caught its own staleness.** Adding `nav_preserved` moved the source that mutations A and B targeted, so their `replace` calls silently became no-ops — the "broken" builds were actually correct builds, and both reported as detected-failures. `loadMutated` now **throws if a mutation does not alter the source**. Worth noting because this class of rot is invisible once it happens: a stale mutation check reports success forever.
- Build clean. Attach sites per chunk: `main` 5, `enrichment` 1, `map_editor` 1 (map-pm's). `nav_preserved` appears in **exactly one chunk** — the collector is now its own shared chunk across three entry points, which is stronger single-collector evidence than before.
- `frontend.md` §3.2 and the history entry updated to the final design (the history entry was uncommitted and described the superseded discard behaviour).

## Still open

- Serving config install (item 2 above) — server-pm/you.
- `dist/` rebuild at integration; still not committing, shared tree unchanged.
- Concurrent non-Tx save double-attribution: documented, inflates rather than flatters.
