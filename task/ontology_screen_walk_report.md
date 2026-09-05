# Ontology screen — the walk, in a real browser

Written by the implementer lane, 2026-08-19. Observed, not inferred, unless a line says so.

**Setup.** Real Chromium against a real uvicorn (`127.0.0.1:8099`), admin token `admin`,
serving the built `client2/dist`. Config root is an **empty temp directory**
(`%TEMP%\walk_root_c0wzvftm`), so the walk starts from the state the owner starts from.
This box's live `server/config/ontology/ledger_config.json` was **not read, moved or
written**.

One environment caveat, stated because it changes how the clicks were delivered: the
preview pane does not composite, so synthetic mouse events and keystrokes do not land
(screenshots time out, `computer type` fills nothing, and `prompt()` is unsupported, which
is why the token went into `localStorage` directly). Clicks were therefore dispatched as
`element.click()` and text via the input's own setter plus a bubbling `input` event. **The
code under test is the shipped client**; only the hand delivering the events is different.

---

## 1. Where the second entity dies

Every line below is a request the browser actually made, in order, with the code it got
back. Nothing here is reconstructed.

**First entity — lands, end to end.**

| pressed | request | back | on screen |
|---|---|---|---|
| (page open) | `GET /view` | **500** `missing_config_file` | 시작 파일 만들기 offered |
| 시작 파일 만들기 | `POST /bootstrap` | **200** | snapshot `86e3976d`, 7 empty sections |
| + New (Entities), id `lot@1`, Create | `POST /drafts/new` | **200** | draft editor opens: 초안 상태 `editing`, rev 0, Identity keys, **one button — Save** |
| + Add key → `lot_id` | (none) | — | draft JSON becomes `{"keys":["lot_id"]}` |
| **저장** | `PUT /drafts/{id}` → `POST /drafts/{id}/activate` | **200** → **200** | — |
| (same press) | `GET /view?…view_mode=active` | **200** | snapshot `3360a8af`, `lot@1` shown **active**, 구성 요소 · 1개 |

**Second entity — created, then invisible.**

| pressed | request | back | on screen |
|---|---|---|---|
| + New (Entities), id `wafer@1`, Create | `POST /drafts/new` | **200** | — |
| (same press, the re-read) | `GET /view?…view_mode=active&draft_id=fc62839a…&revision=0` | **200** | **lot@1, read-only**, with the notice 「초안 대상은 wafer@1로 고정되어 있습니다」 |

**No key rows. No Save button.** The draft exists and the operator has no way to reach it,
so the walk cannot continue: nothing to type into, nothing to press.

The one response body carries every fact needed (request `…191`):

```json
"selection": { "key": "entity|lot@1", … },
"draft": { "target_key": "entity|wafer@1", "creates_declaration": true,
           "lifecycle_status": "editing", "raw": {} },
"view_context": { "mode": "active", "fallback_reason": null }
```

Two things worth noting from that body:

* The request sent **no** `selection` parameter — the server **chose** `entity|lot@1`
  because it is the only item. With an empty config there was nothing to choose, which is
  why the first create did not hit this.
* `view_context.mode` is `active` with `fallback_reason: null`. The 「초안 대신 활성
  snapshot 표시 · invalid_type」 path is **not** what is happening here. That one is fixed.

---

## 2. The one line

**File.** `client2/src/ontology_explorer_view.js`
**Function.** `renderRaw(state)`, the first guard (line 291).

```js
// now
if (state.draft && (!state.selection || state.selection.key === state.draft.target_key))

// proposed
if (state.draft
    && (state.draft.creates_declaration
        || !state.selection
        || state.selection.key === state.draft.target_key))
```

**Why this line.** A create draft's target is by definition absent from the snapshot, so
`state.selection.key === state.draft.target_key` can never be true for one — the guard
rests entirely on `!state.selection`, which is a *proxy* for "this is a create" that only
holds while there is nothing else to select. The 🔴 comment three lines above states the
real predicate in words — 「A CREATE DRAFT HAS NO SELECTION TO MATCH」 — and the code below
it wrote down a different claim.

Nothing is added: `creates_declaration` is already on the record, already in
`ConfigDraftStore.public()`, and already arriving at the client (observed `true` in the
body above). The change swaps a proxy for the answer the server already sends.

---

## 3. What it fixes, and what it does not — including how well I know it

**Observed, not inferred:**

* The guard **is** the live branch. The string 「초안 대상은 …로 고정되어 있습니다」 is
  produced only by the `else` that follows this guard, and it is on screen.
* Both existing terms are **false**, from the rendered payload: `state.selection` is
  non-null (`entity|lot@1`, and its raw `{"keys":["lot_id"]}` is what the panel is
  showing), and `entity|lot@1 !== entity|wafer@1`.
* The proposed term is **true** in that same payload: `creates_declaration: true`.

**~~Inferred~~ -- now OBSERVED. Approved, applied, walked.** What stood here said I had
not watched the repaired predicate render the editor. I have now, on a **fresh empty**
config root:

| pressed | result |
|---|---|
| bootstrap | 200, snapshot `86e3976d` |
| create `lot@1` -> key `lot_id` -> **저장** | editor opens; `PUT` 200 -> `activate` 200; `lot@1` **active** |
| create `wafer@1` | **editor opens** -- `hasEditor: true`, `hasAddKey: true`, `notice: null` |
| key `wafer_id` -> **저장** | 200 -> 200; tree shows **2 items, both `active`** |
| **page reload** | both still there, `error: null` |

And the file on disk, the only witness that outlives the tab:

```json
"entities": { "lot@1": {"keys": ["lot_id"]}, "wafer@1": {"keys": ["wafer_id"]} }
```

The guard was necessary AND sufficient; nothing downstream of it needed touching.

**What it does NOT fix — deliberately:**

* It does not stop `/view` from choosing a selection when none was asked for. That
  behaviour is left alone; the screen simply stops depending on it.
* It does not touch the second and third branches of `renderRaw`, so an **edit** draft on a
  different selection still shows the read-only notice, which is correct for that case.
* It says nothing about `GET /view` returning **500** on a missing config file. That is a
  separate finding: the screen survives it (the authoring plan renders and offers
  bootstrap), but the very first request a from-scratch operator makes is a 500, and a
  refusal would be more honest than an exception. **Not fixed, not in scope, flagged.**
* It says nothing about the copy 「setup_version + 6 empty sections」 on the bootstrap
  offer, where the file gets **seven**. Cosmetic, flagged, untouched.

---

## 4. One click or two

**Two clicks — one per declaration.** `lot@1` at request `…183`, `wafer@1` at `…190`.

Those numbers are the browser tool's **request sequence indices, not milliseconds**. Six
requests sit between them: the post-create `/view`, an `/authoring/plan`, the `PUT`, the
`activate`, the post-activation `/view`, and another `/authoring/plan`. No double-fire.

---

## State of the tree as this is written

Nothing committed. `main` is at `7159bce`. Working changes are the four instructed fixes
(A: `server/ledger/config_drafts.py`; B, C, D: `client2/src/ontology_explorer.js` and
`ontology_explorer_view.js`) plus the rebuilt `client2/dist`. `tests/test_ontology_config_explorer.py`
is **54 passed** after A.

The four files from other lanes (`dt_map_derivation`, `map_alignment`, `map_overlay`,
`seed_dt_index_walk`) are stat-dirty with **zero content diff** and will not be staged.

---

# ROUND 2 — the owner used it and it is still wrong

> 「lot 생성 후 wafer 생성시 여전히 lot으로 떠있는상태로 key 입력만 초기화됨」

**Reproduced.** Fresh empty root, bootstrap -> create `lot@1` -> key `lot_id` -> 저장 ->
create `wafer@1`. Everything below is read off the screen, not inferred.

## 1. What each of the four says, right after the second create

| where | what it says |
|---|---|
| **header / title** | `lot@1` |
| **breadcrumb (Reference Flow)** | 현재 경로 → entity **`lot@1`** · active · valid — and 경로 후보 1 is `lot@1` too |
| **definition panel** | `lot@1` · `entity · ledger_config.json#/entities/lot@1` · `● ACTIVE · valid` · `◇ DRAFT · editing` |
| **key input** | `Identity keys` / **`None defined`** / `+ Add key` — present, and **empty** |

Also on that panel, all of it `lot@1`'s: Integrity, 사용처 · 0, 참조 검사 ✓✓, and the
Active 보기 / Draft preview toggle.

**The decisive count.** In the explorer panel's DOM at that moment:

```
lot@1   appears 16 times
wafer@1 appears  0 times
```

The operator is editing `wafer@1` and **the screen never says the word once.** The only
thing on screen that belongs to the new draft is the editor box itself — 초안 상태
`editing`, Revision `0`, an empty key list — and an empty key list under a heading that
says `lot@1` reads as 「lot의 키가 지워졌다」. That is exactly what the owner reported.

## 2. What the server sent (the `/view` the screen drew this from)

```
selection.key      -> entity|lot@1
selection.raw      -> {"keys": ["lot_id"]}     <- what the definition panel is showing
draft.target_key   -> entity|wafer@1
draft.raw          -> {}                        <- what the empty key box is showing
draft.creates_declaration -> true
view_context.mode  -> active
```

**One response, two subjects.** The panel renders `selection`, the editor renders `draft`,
and after a create those are different declarations. Nothing is malfunctioning at the
request layer: the screen asked for no selection, and the server chose one — the behaviour
already noted in this file — so `selection` fell to `lot@1` while the draft moved on.

## 3. Why my own verification passed this

I asserted **that the editor appeared** (`hasEditor: true`, `hasAddKey: true`,
`notice: null`) and never asked **what the screen said it was editing**. The proxy was one
layer below the claim: "the editor renders" is not "the operator can tell what they are
editing". Same failure as the harness that rendered the same shape twice — I measured the
thing I had just changed instead of the thing the owner would see.

The guard fix in `9485095` is not wrong and is not in question here: before it there was no
key box at all, and now there is one. It got the editor onto the screen; it never claimed
to move the selection, and it does not.

## 4. Not touched, awaiting your ruling

Two candidate seams, and I am deliberately **not** choosing between them:

* the create could name its new target in the re-read instead of passing `selection: null`,
  so the panel follows the draft; or
* the panel could take its subject from the draft whenever one is open.

They differ in what happens to an **edit** draft opened on a different selection, and to the
back/forward history — which is why this is a ruling, not a patch. **Nothing changed in the
tree since `9485095`.**

---

# ROUND 2 — FIXED, counted, pushed as `4487ce0`

Ruling (B) applied: when `creates_declaration` is true the workspace's subject is the
draft's target, and the panels that have nothing to say are **not drawn** rather than
filled with the previous declaration's values.

**Counted again, same walk, same method, fresh empty root:**

| region | before | after |
|---|---|---|
| working area (`.oe-workspace`) | `wafer@1` 0 · `lot@1` 12 | **`wafer@1` 1 · `lot@1` 0** |
| whole panel | `wafer@1` 0 · `lot@1` 16 | `wafer@1` 1 · `lot@1` 4 |

The four remaining `lot@1` are the **left tree's entry** for it — declared, and it belongs
there. Verified by counting inside `.oe-tree` alone: `lot@1` 4, `wafer@1` 0.

Heading now reads `wafer@1` / `entity`. Integrity and the detail grid are absent
(`integrity: false`). Key box present. Walk finishes: key `wafer_id` → 저장 → tree shows
both `active`, and on disk:

```json
"entities": { "lot@1": {"keys": ["lot_id"]}, "wafer@1": {"keys": ["wafer_id"]} }
```

## One trap this round set, recorded so nobody pays for it twice

The first measurement after the rebuild came back **16 / 0 — identical to the unfixed
screen.** The build was correct and `admin.html` referenced the new asset; the **browser
was still running the previous bundle** (`admin-Bb5GeKL2.js` while the build had produced
`admin-D5s8kLQs.js`). A cache-busted reload showed the change immediately.

**Built is not loaded.** Check `script[src]` on the live page, not the build log — the
build log is the one thing that cannot tell you this.

---

# ② PRE-FLIGHT — are the pieces already there?

You asked me to measure two things before starting and to stop if either was false.
**Both are true**, and I went one step further and ran the extraction, because "the parts
exist" and "the parts answer the question" are different claims.

Nothing was built. Nothing was written. The live config was read, never modified — every
break below was made on an in-memory copy.

## 1. Errors carry a location, and they are COLLECTED, not raised one at a time

`LedgerSetupValidationError(code, path, message)` — `setup_bundle.py:107`, and it has
`to_mapping()`, so it is already shaped for the wire.

`class _Problems` holds `self.items: list[LedgerSetupValidationError]` and `add()` appends;
the sorted tuple comes back at the end. Validation does **not** stop at the first failure.
**Confirmed.**

## 2. Path → declaration key exists

`ground_node_key(path)` in `config_authoring.py:105`:
`bundle.entities.DTJob@1.keys` → `entity|DTJob@1`, `None` when the path is not inside a
declaration. It splits the path and reads `_KIND_BY_SECTION`. **Confirmed.**

Note what it was built for — sending an author to the declaration that *forces* a derived
field. That is the same question in different clothes: *which declaration owns this path*.

## 3. So I ran it. "Which declaration is invalid" falls out of the existing errors

Live config + real `table_config.json`, three states:

| state | problems | blamed | unmapped |
|---|---|---|---|
| untouched | **0** | — | 0 |
| one claim's `emit.predicate` → a predicate nothing declares | **1** | `pack\|dt-job@1` | 0 |
| a half-written entity added (`"wafer@1": {}`) | **2** | `entity\|wafer@1` | 0 |

```
unknown_predicate   bundle.packs.dt-job@1.claims.die_count.emit.predicate
invalid_type        bundle.entities.wafer@1.keys
missing_field       bundle.entities.wafer@1.keys
```

Three things worth reading off that table:

* **A dangling reference is reported on the REFERRER's own path.** The pack that points at
  a missing predicate is blamed, by name, with the exact field. That is the whole
  `invalid` tag, already computed.
* **Every declaration-level problem mapped. Zero unmapped.** Grouping the existing error
  list by `ground_node_key` *is* the answer — there is no new validator here.
* **The healthy declarations stayed out of it.** Breaking one pack blamed one pack. The
  per-declaration split the owner described already holds in the data.

**So: do not build a validator.** What is missing is not analysis, it is that nothing
currently *saves* a bundle whose analysis is non-empty, and nothing renders the tag.

## Two things the error list does NOT answer — flagged, not solved

1. **Propagation past one hop.** A pack naming a missing predicate blames itself. A
   profile naming *that pack* does **not** get an error — the pack still exists by name,
   so the reference resolves. Marking the referrer needs the edge graph you pointed at
   (`build_explorer_index`), not the error list. Measured as one hop only; I did not test
   a chain.

2. **File-level problems have no declaration to blame.** With no `table_config.json` the
   only problem is `physical_catalog_required` on path `table_config.json`, and
   `ground_node_key` returns `None` — correctly, because no declaration is at fault. That
   bucket needs somewhere to go, or it disappears.

## And the risk you named, sharpened by the same measurement

The live config validates with **0 problems today**. Under the new model, one typo in one
source declaration produces **exactly one** problem, tagged on that source, while
everything else keeps running — which is the desired behaviour and also precisely how a
running ingestion goes quiet without anyone noticing. Your minimum response
(distinguish *was reading, now is not* from *never finished*) is the right shape; I have
not built it.

**Awaiting your ruling on scope. Nothing started.**

---

# ② DESIGN — propagation is a FIXPOINT over the validator we already have

Measured before building, because it decides the size of the round. Live config, one pack
broken (`emit.predicate` -> a predicate nothing declares). Then: validate, drop whatever is
blamed, validate again, repeat.

```
round 1  1 problem   pack|dt-job@1         unknown_predicate  ...claims.die_count.emit.predicate
         -> drop pack|dt-job@1
round 2  5 problems  mapper|dt-job-role@1  unknown_pack       ...mappers.dt-job-role@1.emits[0]
                     profile|dt-job@1      unknown_pack       ...profiles.dt-job@1.mappings[0].use
         -> drop both
round 3  2 problems  source_plan|dt_job    unknown_mapper     ...sources.dt_job.driver.mapper_id
         -> drop it
round 4  0 problems  -- fixpoint. Everything left LOADS.
```

**One typo cascaded pack -> mapper + profile -> source and converged in four rounds, with
no edge walk and no new code.** Dropping a declaration is what makes its referrers dangle,
and the existing validator already reports a dangling reference on the referrer's own path.
The reference graph is not needed for loading: the fixpoint *is* the propagation.

It also hands us the two reason texts your ruling asked for, for free:

* **blamed in round 1** — its own fault. The error names the missing thing.
* **blamed in a later round** — dropped because something it references was dropped. The
  error path names the referrer, the error message names what went missing.

Same `invalid` tag, different sentence, decided by *which round dropped it*. No second
state, no new badge.

And the accounting you asked for holds at every step: `problems == per-declaration +
config-level`, which is how the loop is written — nothing is silently dropped.

**Building on this. Nothing else changed yet.**

---

# ② BUILD — step 1 of 6 landed: the resolver

`resolve_declarations(document, catalog=...)` in `ledger/config_explorer.py`. Returns the
document that loads, the invalid declarations with the round each fell in, and the
config-level problems. **No new validator; no edge walk; nothing written.**

Measured on four states:

| state | rounds | invalid | config-level | survives |
|---|---|---|---|---|
| live, untouched | 1 | none | none | everything |
| one pack broken | 4 | `pack\|dt-job@1` (r1), `mapper\|dt-job-role@1` (r2), `profile\|dt-job@1` (r2), `source_plan\|dt_job` (r3) | none | packs 2→1, mappers 2→1, profiles 2→1, sources 2→1; **vocabulary, entities, preparers untouched** |
| half-written entity `wafer@1: {}` | 2 | `entity\|wafer@1` (r1) | none | everything else |
| **no catalog at all** | 1 | none | `physical_catalog_required` | everything |

Your two warnings, both checked:

* **Termination is "nothing fell".** The no-catalog row is the test: one config-level
  problem that no drop can clear, loop returns after one round. Under a `problems == 0`
  condition it would not have returned.
* **The round number carries the reason split.** Round 1 = its own fault. Round 2+ = it was
  knocked out. The raw `unknown_pack` text is kept only for **which field**; the sentence a
  person reads gets rewritten at the display layer, because "the pack is not declared" is a
  lie about a pack that is sitting right there on screen.

And the check you asked for: **the operator's file is byte-identical afterwards**
(`live file unchanged: True`).

## Remaining, in order

2. `active()` loads through the resolver, and its loader exception becomes a named state
3. `/view` carries the tags and the config-level bucket
4. saving stops being blocked (`draft_preview_invalid` and the two hash checks)
5. failure no longer rolls the write back
6. the screen renders the tag, the two reason texts, and the config-level banner

**One thing I need ruled before step 2.** The resolver is wired into the EXPLORER's loader
only. Production `load_setup` still refuses whole. That is deliberate — a half-built config
silently loading in ingestion is the risk you named — but "적재는 전파를 따른다" could mean
the system's load too. **Say which and I will follow it; I am not deciding it here.**

---

# ② MEASURED — the snapshot hash follows what SURVIVES, not the file

You asked before ruling. Measured, not fixed.

```
full live config                      39ebb419d15d84b0   packs 2  mappers 2  profiles 2  sources 2
one pack broken -> resolver drops
  pack|dt-job@1, mapper|dt-job-role@1,
  profile|dt-job@1, source_plan|dt_job
reduced bundle                        379748b2a15d745b   packs 1  mappers 1  profiles 1  sources 1

hash moved: TRUE
```

`compile_setup_snapshot` is handed the **bundle**, and under partial loading the bundle is
the reduced one. So the hash is a hash of *what loaded*, not of *what the operator wrote*.

**What that means, stated as implication and not as measurement** — I have not wired
`active()` yet, so nothing downstream has actually been observed failing:

* One typo in one source moves the snapshot hash. The file did not change; every consumer
  that compares hashes would read "the config changed".
* `base_snapshot_hash` compare-and-swap is exactly such a consumer. A draft opened before
  an unrelated declaration went invalid would find its base hash stale — and the operator
  would be told the active snapshot changed under them, which is true of the hash and false
  of the file.
* The convergence probe compares the reloaded hash to the reviewed preview hash. Same
  exposure.

So your suspicion holds: **this is the same root as the pending `base_snapshot_hash`
question.** Two candidate spellings exist — hash the file the operator wrote, or hash what
loaded — and they answer "did the config change?" and "did what runs change?" respectively.
Both are real questions and they are not the same question.

**Step 2 is stopped on this.** Wiring `active()` through the resolver is precisely the edit
that makes the explorer's snapshot hash the reduced one, so I would be deciding this by
accident. Steps 4 and 5 (saving stops being blocked, no rollback on failure) do not touch
the hash — **say the word and I will take those two first while this is ruled.**

---

# ② WALKED — five of six pass, and the sixth needs a ruling

Real browser, empty config root, token `admin`, server code from `427b19b`.

| # | step | result |
|---|---|---|
| 1 | save a pack whose claim emits an undeclared predicate | **saved**, and in the file on disk |
| 2 | it is on the list | **`invalid`**, with two reasons naming the field and the missing predicate |
| 3 | the declaration next to it | `lot@1` still **`active`** |
| 4 | refresh | screen opens, **no 500** |
| 5 | **restart the server** on the same file | `lot@1` still active, pack still listed and tagged, `active_snapshot.valid: false` |
| 6 | declare the missing predicate | the "unknown predicate" reason **disappears** — 2 reasons → 1 |

**Step 5 is the one that decides whether partial loading is real.** That config would
previously have made the server load nothing at all.

Step 6's remaining reason is a second, genuine defect in the pack I typed by hand
(`emit.object.value` naming no role). That it still says so is correct.

## 🔴 The gap — and why I stopped instead of fixing it

**Clicking the unread declaration errors:**

```
selection 'pack|lot-events@1' does not exist in this snapshot
```

The operator can **see** their half-written pack and cannot get **into** it. That is the
owner's whole workflow — 「일단 와꾸 짜놓고 나중에 살 채우는」 — and right now the second
half has no door. Visible-but-unreachable is closer to the old dead end than it looks.

Two ways, and they differ in more than spelling:

* **(A) `/view` accepts a selection that is not in the index** and answers with the raw
  declaration plus its reasons. You rejected (A) earlier for the *create* case, on the
  grounds that the server refuses unknown selections — this is the same refusal, but the
  subject here **is** in the file, so "unknown" is arguably wrong about it.
* **(B) the tree row opens a draft directly**, skipping selection, the way a create draft
  already renders without one. Smaller, and it reuses the path built this morning.

I lean (B) — it changes no server contract and the editor already knows how to render a
draft with no selection. But (A) is the one that also fixes 「사용처」 and the definition
panel for unread declarations, and I do not know which of those you want.

**Nothing else is left. Steps 1-6 of your list are otherwise green, and every server
change is committed and pushed.**

---

# ② DONE — all six, walked, and the gap is closed

Ruling (B) landed (`9ceb8ca`). The row for an unread declaration opens the editor instead
of selecting it, seeded from the file, with the reasons carried inside.

Walked again on a fresh empty root, bundle checked against the build **before** measuring:

| pressed | result |
|---|---|
| bootstrap → entity `lot@1` + key → 저장 | `active` |
| pack `lot-events@1` emitting an undeclared predicate → 저장 | **saved to the file** |
| its row | `invalid`, reason names the exact field |
| **click it** | **editor opens** — heading `lot-events@1`, text from the file, reason shown inside |
| declare predicate `started@1` → 저장 | pack goes **`active`**, its claim appears as a resolved node, **0 reasons, 0 banners** |

File afterwards: `entities 1, packs 1, vocabulary 1` — all three written through the
screen, in a config that **never once compiled as a whole** until the last save.

Your three conditions: pressing always opens (no silence, no error); the reasons are inside
the editor; a resolved declaration's row still says `select` and behaves exactly as before.

## Left for you

* **「전엔 읽혔는데 지금 안 읽힘」** — deferred by your ruling, still deferred. The risk is
  real: one typo now takes one source dark and everything else keeps running.
* **`task/ontology_picker_spec.md`** is untracked in the tree and is not mine.
* **doc-keeper counter is at 43 commits.**

---

# ③ KEEPING THE OPERATOR'S PLACE — verified, including the `invalid` loop

`7086056`. Two fixes, one commit (same file; the split would have meant staging partial
hunks, which this project has already paid for once — the fork accepted the reasoning).

**A response no longer deletes what is being typed.** Reproduced first: key `wafer_id`
typed, not saved, `lot` typed into the search box → editor back to `{}`, no warning.
`RESPONSE_RECEIVED` rebuilt `editorText` from the draft record on every response and
cleared `dirty` with it. Fixed in the reducer — the one place answers arrive — so a caller
added later cannot reopen it. Counted, not claimed: `load({` callers **9**, carrying
`editorCheckpoint` **4**; the other five are paths where discarding is the *decision*, and
passing a checkpoint there would resurrect text the operator chose to throw away.

**Saving keeps the editor on the declaration.** It re-opens rather than holding the spent
record. The re-read runs first, so the new draft sits on the hash the write just produced.

| walked | result |
|---|---|
| save #1 | editor stays, heading `lot@1`, text unchanged |
| save #2 → #3 | both work; file holds `["lot_id","wafer_id","die_id"]` |
| text after saving | identical to what was typed — no key-order or whitespace drift |
| **`invalid` declaration, save #1** | editor stays on `ev@1`, 2 reasons shown inside |
| **`invalid` declaration, save #2** | editor stays, reasons **update** to the new state (`still-missing@1`), file agrees |

The last two rows are the ones that mattered: an unread declaration is what the owner will
sit on longest, and losing your place there would mean the repair missed the case it exists
for.

## Next

**Delete button** — the last of CRUD. Instruction already received and unchanged: no gate,
no reference-count guard (source and profile name each other, so in-degree never reaches
zero — board `ec9f1c2`), preview shows rather than blocks, and the decision line is that
deleting something others reference **is not refused** — the referrers simply become
`invalid`, which is now a normal state.
