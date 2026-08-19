# Implementer handover — 2026-08-19, end of the ontology-screen day

Written by the outgoing implementer session (`00d8df53`) for its successor. The lead PM is
the fork session "Ontology Manager"; it rules, you build. The owner writes in Korean.

---

## 1. Where the tree stands RIGHT NOW

`main` = `65e9823`, pushed. **Plus uncommitted work in flight — read §2 before touching it.**

```
 M server/ledger/config_explorer_service.py     <- in flight (delete confirm)
 M client2/src/ontology_explorer.js             <- in flight (delete confirm)
 M server/dt_map_derivation.py                  <- NOT MINE, 0-line diff (CRLF noise)
 M server/map_alignment.py                      <- same
 M server/map_overlay.py                        <- same
 M server/scripts/seed_dt_index_walk.py         <- same
?? task/ontology_screen_walk_report.md          <- the day's evidence, fork-owned, DO NOT COMMIT
?? task/ontology_picker_spec.md                 <- the fork's, not mine
```

Today's commits, oldest first: `9485095` (the walk works twice) · `4487ce0` (the screen
names what you are editing) · `ade81ef` `2386296` `9e4b471` `6346152` `427b19b` `9ceb8ca`
`34340a2` (partial loading, six steps) · `7086056` (typing is not discarded; saving keeps
the editor) · `afe8249` (delete button) · `65e9823` (a clean draft stops following the
selection).

**doc-keeper counter is at 49 commits.** Not run today.

## 2. The work you are holding, mid-air

**Task: the delete confirm lied.** It printed 「영향 없음」 while deleting a predicate was
about to make a pack unread. The cause is not a bug in `deletion_plan` — it is misuse:
`removed`/`released`/`blocked` are the OLD model's vocabulary, from when deleting a
referenced declaration was *refused*. `released` means "authored in another file and merely
stops being referenced". It never answered 「무엇이 안 읽히게 되나」.

**Fork's ruling:** do not touch `deletion_plan`. Make the confirm ask the **resolver** —
drop the target from an in-memory copy, run the same fixpoint the loader runs, report what
falls. Preview and outcome then come out of one machine and cannot disagree.

**What I already wrote (uncommitted):** `deletion_preview` in `config_explorer_service.py`
adds `unread_after`, and the client confirm reads it instead of `released`.

**🔴 IT IS RED. One test, and the failure is real, not cosmetic:**

```
tests/test_ontology_config_explorer.py::test_deletion_preview_endpoint_names_the_casualties_and_shows_the_blockage
FileNotFoundError: ...\test_deletion_preview_endpoint0\absent\ledger_config.json
```

My code reads the config file unconditionally to build the copy. That fixture points at a
config root with **no file** — a state the preview is expected to survive. Fix it by asking
the already-loaded document instead of re-reading the path, or by answering with an empty
`unread_after` when there is nothing to read. 53 of 54 pass.

**Counted before changing anything, as the fork required:** production consumers of
`deletion_plan` = **1** (`config_explorer_service.deletion_preview`), reached by **1** route
(`/deletion-preview`), read by **1** client site (the confirm). Every other hit is a
comment. So changing what the confirm reads breaks nothing else.

**Delete checks still not run: 3** (refresh + **server restart**) and **4** (re-declare the
deleted thing → its referrers revive). Checks 1 and 2 passed, and 2 was the decision line:
deleting something another declaration references is **not refused**; the referrer becomes
`invalid`.

## 3. What the screen does now, so you do not re-derive it

The owner's model, in their words: 「선언을 저장할때 json 형식만 맞으면 다 저장하고, 읽는쪽에서
시스템에서 resolve되는거만 읽으면 안됨? 일단 와꾸 짜놓고 나중에 살 채우는 형식으로 일함 사람들은.
안읽히는 엔티티, 팩 등등은 invalid 태그 붙이고」

* **Buttons are CRUD only** — 생성 · 편집 · 저장 · 삭제. No Activate, no Discard, no review
  step. **저장 IS the write to the config file** (save chains PUT + activate; no new
  endpoint was added for it).
* **Saving no longer requires the setup to compile.** Four gates were removed; each had
  refused a state that is normal while building.
* **Loading resolves declaration by declaration.** `resolve_declarations` in
  `config_explorer.py`: validate, drop what is blamed, validate again, until **nothing
  falls** — NOT until nothing is wrong. A config-level problem blames no declaration and a
  `problems == 0` condition would never return. Propagation *is* that fixpoint; there is no
  edge walk, and none should be added.
* **Unread declarations stay on the list**, tagged `invalid`, with reasons under the row and
  inside the editor. Their row opens the **editor** (`edit-unread`), not a selection.
* **The list has rows that cannot be selected, and that is correct.** The list answers "what
  is in the file"; selection answers "what was interpreted". Do NOT "tidy" this by putting
  unread nodes into the index — the panels around a selection show interpreted facts, and an
  unread declaration has none, so filling them means inventing facts.
* **The compare-and-swap basis is the FILE's hash** (`document_hash`, canonical JSON), not
  the compiled snapshot's. The compiled hash moves when an unrelated declaration stops
  resolving, and is absent entirely while a setup is half-written.
  `snapshot.snapshot_sha256` is untouched and still answers "did what runs change?".

## 4. Traps that cost real time today

* **Built is not loaded.** After a rebuild the browser kept serving the previous bundle and
  the measurement came back *identical to the unfixed screen* — I nearly reverted a correct
  fix. Check `script[src]` on the live page against the build output **before** measuring.
  Same for the server: a stale process held port 8099 and I measured old code.
* **Fix one site, then sweep for its siblings.** Three times today: six copies of "no
  selection means wrong", four copies of the snapshot-hash basis, two of the discarded
  editor. The suite caught the second; nothing caught the first.
* **A proxy one layer below the claim passes.** I asserted "the editor appeared" and never
  asked "what does the screen say it is editing" — it said `lot@1` sixteen times while the
  operator was editing `wafer@1`.
* **Measure before building.** Two designs shrank to almost nothing this way: propagation is
  a fixpoint over the existing validator, and "which declaration is invalid" falls out of
  the error list that already exists.

## 5. How to walk the screen (you will need this)

`%TEMP%\claude\...\scratchpad\walk_server.py` — a uvicorn on **8099** serving `client2/dist`
with the explorer router against an **empty temp config root**, so the owner's live config
is never touched. `WALK_ROOT=<path>` reuses a root, which is how the **server restart** check
is done. The admin token is **`admin`** (the owner's own; they gave it and said to use it);
set it with `localStorage.setItem('assy.adminToken','admin')` — the preview pane does not
support `prompt()`.

The pane does not composite, so synthetic mouse events and keystrokes do not land: drive it
with `element.click()` and the native value setter plus a bubbling `input` event. The code
under test is the shipped bundle; only the hand is different.

## 6. Next, in the fork's order

1. Finish the delete confirm (§2), then delete checks 3 and 4.
2. **datalist round.** The spec is in `task/ontology_picker_spec.md`, sections 0-a/0-b/0-c —
   read it first. Owner's ruling: **`datalist` on the input, not a `select`** —
   「미묘한 오타로 같은 말이 갈라지는거 방지」. It must SUGGEST, never constrain: coining a new
   name has to stay possible. The primitive already exists in `ledger_setup.js` and
   `map_editor.js`, with a harness. Do not build a new one.
3. Still deferred by ruling: distinguishing 「was reading, now is not」 from 「never
   finished」. The risk is real — one typo now takes one source dark while everything else
   keeps running.

## 7. Standing rules you will be judged against

CLAUDE.md's gate: ① minimal edit ② simplest logic ③ **never build what was not asked for**.
Report in plain language, no codenames. `git add` AND `git commit` both take explicit paths —
four foreign files are sitting dirty in this tree. Do not write
`server/config/ontology/ledger_config.json`; the owner hand-edits it.
`docs/process/PROJECT_STATUS.md` is the fork's. Report to the fork by **writing a file and
sending one line** — messages arrive truncated.
