# Admin screen — narrow UX audit against the four gaps the repo's rules never name

**Date** 2026-09-16 · **Scope** `client2/admin.html`, `client2/src/admin.js`, `client2/src/admin_rows.js`
and the view modules/CSS they pull in. **Source only** — no running page.

## What this pass covers, and what it deliberately does not

`docs/guide/UX_AUDIT_REFERENCE.md` §C names four principles that are industry consensus and have
**no corresponding sentence** in `CLAUDE.md` or `.claude/skills/ui-design-system/SKILL.md`. Those
four are the entire scope here:

| # | Gap | Principle · source |
|---|-----|--------------------|
| 1 | Progress shows the **step** and **what remains** | NN/g heuristic 1, complex-applications reading; Shneiderman 3·4 |
| 2 | **Undo / restore** | NN/g 3; Shneiderman 6 |
| 3 | **Accelerators** for expert users | NN/g 7; Shneiderman 2 |
| 4 | **Help in the screen itself** | NN/g 10 |

Not covered, on purpose (a parallel pass owns them): margins/spacing, copy length, assembly-kit
structure, the `ui-design-system` canon, refusal wording, consistency of vocabulary.

**The operator this is written for:** a domain operator who cannot read the server's logs (security
policy) and has no shell on the server host. This screen is their only window. Several operations
here are genuinely long — chain replay, backfill, retroactive runs, collector runs, ingestion — so
gaps 1 and 2 compound: a long operation that cannot be watched and cannot be taken back is the
worst cell in the matrix.

---

## Verdict per gap

| Gap | Verdict |
|-----|---------|
| 1 — progress / what remains | **Partly refuted.** The Overview *Running* block is a genuinely good implementation for two of the four pipelines. Two other long operations have no progress surface at all, and nothing anywhere states a **step** or a **remaining** quantity. |
| 2 — undo / restore | **Open, and sharply so.** The undo material is manufactured on every write and handed to the client in the response. No screen reads it. There is no HTTP route that can apply it. |
| 3 — accelerators | **Partly refuted.** Deep links and a cross-screen scope handoff are real accelerators. Nothing else exists for the hundredth use, and no operator preference survives a page reload. |
| 4 — in-screen help | **Partly refuted.** The retroactive block explains itself in place, well. Elsewhere the only substantive guidance sends the operator to a file they cannot reach and a screen that does not exist. |

---

## Findings, most severe first

### H1 — A saved script destroys the previous version from the operator's reach, and the undo was in the response

**Gap 2** · **Severity: high** (one-way, and it is live hot-reloaded Python)

- `client2/src/admin.js:4655` `saveScriptCode()` — on `res.ok` it calls `markEditorClean()` and a
  toast. **It never reads the response body.**
- `server/main.py:6858-6860` returns `"backup": backup_path`, with the comment: *"A value, so a
  screen can offer the restore instead of the operator having to know a path on the server."*
- `server/ledger/admin.py:793` `backup_file()` — *"THE COPY IS THE UNDO … and this is the ONLY
  maker of one."*

The server was built to hand this screen an undo. The screen drops it on the floor. The
`confirm()` at `admin.js:842` warns that the save will hot-reload, which is honest about the
*consequence* and silent about the *reversal*.

**What the operator experiences:** they edit a mapper or a parser in Monaco, save, the module
reloads, and the pipeline starts behaving differently. To get back to yesterday's version they need
a path on the server host they were never shown, in a directory (`mappers/backup/`) they have no
reason to know exists. Files written through this screen have no git history by design — the
server's own comment says so. So the previous version is, from where they sit, gone.

**Cheap-fix note (reasoned from source, not executed):** `backup_file()` puts a mapper's copy under
`mappers/backup/…` (`server/config_backup.py:150` `backup_dir_for`), and the read route's prefix
guard at `server/main.py:6750-6754` admits any path starting with `mappers/`. So *"restore"* for
scripts appears to be reachable with the two routes that already exist — the screen simply never
keeps the path and never offers the button. I could not run this to confirm.

---

### H2 — Config saves have the same undo, and for them it is unreachable over HTTP at all

**Gap 2** · **Severity: high** (blocked — the operator must ask someone with host access)

- `client2/src/admin.js:1180` `saveChainRule()` and `:1260` `saveTableConfig()` pass the whole
  response through as `{ saved: answer }`.
- `client2/src/chain_rule_panel.js:28-29` reads exactly one field from it: `saved.enabled`.
  `client2/src/table_config_panel.js` mentions `saved` only in a jsdoc type. Neither reads
  `saved.backup`.
- The server supplies it at `server/ledger/admin.py:547` (table config), `:734` (chain rules),
  `:887` (ledger config).
- `git grep -nE '@(app|router)\.(get|post|delete)\(.*backup' -- server` → **zero hits.** There is no
  HTTP route over the backup directory. Config backups land in `server/config/backup/`, which is
  outside the `mappers/` and `ingestion_workspace/` prefixes the script routes allow.
- The only restore that exists is `cmd_restore` in `server/scripts/backup_config.py` — a CLI on the
  server host.

**What the operator experiences:** they register a table or a chain rule, get it wrong, and the only
way back is to ask whoever has the shell. This is exactly the fear the standing rule
「변경 비용이 핵심 제약」 is aimed at: an operator who cannot undo a declaration edit will not make
declaration edits.

---

### H3 — A running collector is invisible on its own tab **and** absent from the list that claims to show everything running

**Gap 1** · **Severity: high** (wrong answer)

- `client2/src/admin.js:3964` `runAutoUpdateNow()` — POST, one toast
  (「강제 수집 지시가 정상적으로 발행되었습니다」), then a single
  `setTimeout(() => fetchData(), 1500)`. That is the last thing that ever happens.
- `client2/src/admin.js:408-414` — the 30-second auto-refresh loop runs only for
  `currentTab === 'overview' || 'file' || 'chain'`. **`autoupdate` is not in the list.** After that
  one 1.5-second refresh, the tab is frozen until the operator presses Refresh by hand.
- `client2/src/retroactive_view.js:413` `buildRunsView({ runs, ingestions })` — the Overview
  *Running* block is fed by `/admin/retroactive/runs` and `/admin/file-ingestion/active` only.
  Collector runs live in the auto-update status (`last_status`) and reach neither source.
- The Auto Update health card that might have carried the fact is painted into a strip that
  `client2/src/admin.js:577` hides unconditionally on every `updatePanelLayout()` call.

**What the operator experiences:** they fire a collector that takes minutes, the row keeps showing
whatever badge it had, elapsed time is never shown, and the Overview block headed 「Running / 도는
것들」 reports `idle`. The screen's one answer to *"what is running right now"* says nothing is —
while something is. NN/g 1: the system must keep the user informed **through appropriate feedback
within reasonable time**; this is worse than silence, because the silence is labelled `idle`.

---

### H4 — The most global button on the screen has no in-flight state whatsoever

**Gap 1** · **Severity: high** (blocked — the operator cannot tell running from hung)

- `client2/admin.html:1951` `#reload-configs-btn` ⚙️ Reload Configs & Code.
- `client2/src/admin.js:4466` `reloadSystemConfigs()` — `await adminFetch(...)`, then a toast. The
  button is **never disabled**; there is no spinner, no label change, no progress. Compare
  `admin.js:2627` and `:3268/:3274`, where the enrichment dry-run and the retroactive buttons *do*
  disable and relabel in flight. This one was left out.
- The operation is not trivial: it re-imports every parser script, chain rule and mapper module, and
  for new watcher entries it runs an initial directory sweep
  (`server/config/sample/ingestion_settings.json.sample:16`). `server/database/models.py:1252`
  records that concurrent `/admin/reload-configs` threads are real and are serialised behind an
  in-process lock.

**What the operator experiences:** they press it, nothing changes, and after some seconds they press
it again — which now queues behind the first behind the server's lock, still with no signal. The
irony is that this is the button the Enrichment tab's own help tells them to press (see M3).

Partial credit where it is due: *after* the call returns, the 설정 반영 block force-refreshes and
re-opens itself (`admin.js:4479-4484`), so the reload does have a result surface. The gap is
entirely the span *during*.

---

### M1 — Nothing on the screen says what remains

**Gap 1** · **Severity: medium** (must ask someone — "will this finish before I go home?")

- `client2/src/retroactive_view.js:385` `buildProgressCell(processed, total, minutes)` returns
  `{percent, processed, total, elapsedMinutes}`. There is no ETA, no remaining count, no rate.
  `grep -in "eta|remaining|남은|예상|estimat"` across `admin.js`, `retroactive_view.js`,
  `progress_card.js` returns nothing that is a projection.
- For the operations whose total is unknowable up front — and the file's own comment at
  `retroactive_view.js:395-396` says these walk *"until the rows run out"* — the operator gets an
  indeterminate bar and a bare processed count with **no denominator at all**.

**What the operator experiences:** elapsed time is shown; time-to-finish never is. On a percent row
they can do the arithmetic themselves; on an indeterminate row there is nothing to do arithmetic
with. NN/g's complex-applications guidance is explicit that for operations past ~10 seconds,
"how far along" without "how much left" leaves the user unable to decide whether to wait, switch
tasks, or cancel — and cancelling is precisely the decision this block exists to support.

I want to be fair to the code here: refusing to draw a fake percent is the right call and the file
argues it well. The gap is that having refused the fake number, nothing was put in its place.

---

### M2 — "Retry All Failed" states no scope before, no outcome after, and leaves no record

**Gap 2 (primary) / Gap 1** · **Severity: medium**

- `client2/admin.html:2181` and `:2274` — the two 🔄 Retry All Failed buttons.
- `client2/src/admin.js:752` / `:759` — the confirm asks 「실패 상태인 모든 … 재실행하시겠습니까?」.
  **「모든」 is never resolved to a number.** Contrast the retroactive block, which makes counting
  before running a first-class step.
- `client2/src/admin.js:4437` `retryAllFailed()` — one POST, one toast built from `result.message`,
  then `fetchData()`. Neither button is disabled in flight.
- `client2/src/utils.js:158-161` — toast TTL defaults to 5000 ms. After five seconds the only
  evidence that the operator reset N items is gone.

**What the operator experiences:** they approve "all", without being told whether all is 3 or 300.
The batch cannot be taken back, and five seconds later the screen holds no record that it happened —
so they cannot even tell a colleague what they did. Shneiderman 4 ("closure") and 6 ("easy reversal
of actions") both land here; the closure half is the cheaper of the two to fix.

---

### M3 — The only substantive in-screen help sends the operator somewhere they cannot go, and to a screen that does not exist

**Gap 4** · **Severity: medium** (must ask someone)

- `client2/admin.html:2441-2445` (`.section-note` on the Enrichment tab) and a second copy at
  `client2/src/admin.js:4311`. Both say: edit `server/config/enrichment_rules.json` by hand, then
  press Reload Configs & Code; and *"규칙 CRUD UI는 파이프라인 온보딩 위저드(대안 단계)로 이관"*.
- The operator has no shell on the server host, so the first instruction is not executable by its
  reader.
- The wizard it forwards to does not exist. `client2/` holds `admin.html`, `index.html`,
  `map_editor.html`, `map_editor2.html`, `rnd-board.html`, `walk.html` — no wizard page, and no
  route inside admin that opens one. The word 「온보딩」 appears in exactly two places in the whole
  client, and both are this sentence.
- The screen has **no** help affordance of any other kind: the only `<a href>` in `admin.html` is
  「🏠 Return to Main」, and there are 16 `title=` tooltips across 2,578 lines.

**What the operator experiences:** the one place the screen explains itself at length tells them to
do something they cannot do, and points at a destination that is not there. NN/g 10 asks for help
**where the work happens**; this is help that relocates the work to a room with no door.

---

### M4 — No long operation ever names the step it is on

**Gap 1** · **Severity: medium**

No phase, stage, or step indicator exists anywhere on this screen. `buildRunsView`
(`retroactive_view.js:413-505`) carries `state`, `moving`, `finished`, `stopping` — a *liveness*
axis, not a *progress-through-phases* axis. A chain replay, a backfill and an ingestion each render
as a single opaque span from start to end.

**What the operator experiences:** a run that sits at 4% for ten minutes is indistinguishable from a
run that is wedged, because there is no "now reading / now mapping / now writing" to watch advance.
This is the half of NN/g 1's complex-applications reading that the Running block does not cover, and
it is the half that matters most to someone who cannot open the log to find out.

I could not determine from the client source whether the server exposes a phase at all — see
「모르는 것」.

---

### M5 — Five ingestion states are drawn in two colours, with no legend anywhere

**Gap 4** · **Severity: medium**

- `client2/src/admin_rows.js:31-33` `fileLogRowHtml()`:
  `badge ${log.status === 'SUCCESS' ? 'badge-success' : 'badge-danger'}` — every non-SUCCESS state
  renders in the same red.
- The filter `<select>` at `client2/admin.html:2181` is populated from the server's
  `status_vocabulary` (`admin.js:applyStatusVocabulary`), so the operator can *see* five words.
  Nothing on the screen says what any of them means.
- `client2/admin.html:2168-2176` records in a source comment that one of the five, `PENDING_RETRY`,
  means *"someone else still has to act"* — a fact the operator needs and that lives only in a
  comment they will never read.

**What the operator experiences:** they filter to `PENDING_RETRY`, get a page of red badges
identical to failures, each with an enabled Retry button, and have no way to learn from the screen
that these are already being handled. NN/g 10: the help belongs next to the vocabulary, not in the
source that renders it.

---

### L1 — No keyboard accelerators of any kind

**Gap 3** · **Severity: low** (friction, every day, for the same few people)

- `grep -n "keydown|keyup|ctrlKey|metaKey|accessKey"` over `admin.js` and `admin_rows.js`: **zero
  hits.** The only keyboard handling in the client lives in `enrichment_reference_view.js`, a
  different screen.
- Monaco is created at `client2/src/admin.js:4503` with no `addCommand` and no `KeyMod`/`KeyCode`
  anywhere in the file, so **Ctrl+S in the code editor does nothing** — or rather, it hands the
  browser's Save-Page dialog to someone who meant to save a mapper. The save is mouse-only:
  `#save-code-btn` at `admin.html:2556`.
- No shortcut for tab switching, refresh, or escaping the editor.

NN/g 7 and Shneiderman 2 are both aimed squarely at this user: the same handful of people, daily,
for the hundredth time.

---

### L2 — No operator preference survives a page reload

**Gap 3** · **Severity: low**

Only one thing is persisted in the whole screen: the admin token (`admin.js:103-109`,
`localStorage`). Everything else resets on every load:

| Preference | Where it lives | Survives reload? |
|---|---|---|
| Active tab | URL hash (`admin.js:623-624`) | **yes** |
| Status filter | `#status-filter` DOM value | no |
| Page size (10/50/100) | `fileLimit` / `outboxLimit` module vars | no |
| Section collapse | `sec.classList.toggle('collapsed')` (`admin.js:688-694`) | no |
| `<details>` open state (설정 반영 / Retroactive / Running) | JS record | no |
| Split-panel width | `leftPanelEl.style.width` | no |

**What the operator experiences:** every morning they re-collapse Mapper Modules, re-expand Chain
실패, re-set 100/page, and re-drag the splitter. Six gestures before the first piece of work. The
tab is the one thing that persists, and that is by accident of the hash router rather than by
design.

---

### L3 — Nothing in the lists is built for a large list

**Gap 3** · **Severity: low**

- **Sorting is page-local.** `client2/src/admin.js:1490-1500` sorts `fileData` — the rows of the
  *current page* — and the header `title=` at `admin.html:2188` says so honestly:
  「클릭: 현재 페이지 내 정렬」. Honest, and still means that finding the oldest failure among 300
  requires paging through 30 pages at 10/page.
- **No text search anywhere.** Not on file logs, chain rules, mappers, workspaces, collectors, or
  the outbox. The file-log status `<select>` is the only filter on the entire screen.
- **No multi-select.** No checkbox column in any table, so the only batch operation available is the
  all-or-nothing Retry All of M2. There is no way to retry *these seven*.

---

## Refuted — these are handled, and handled well

I would rather hand back a short list than a padded one. Three of my starting suspicions did not
survive the source.

**Gap 1 is not open for retroactive runs and file ingestion.** The Overview *Running* block
(`admin.js:2809-2937` + `retroactive_view.js:385-505`) is a careful, honest progress surface:
a real percent bar when the total is known; an explicitly indeterminate bar when it is not, with a
recorded refusal to fabricate a percentage; elapsed time that **stops** when the run finishes;
queued rows drawn as *waiting* rather than *moving*; the requester's name; the server's failure
sentence and result sentence rendered verbatim; a cancel `×` drawn **only** where the operation
declares itself cancellable; and an adaptive poll (3 s busy / 30 s idle, paused on hidden tabs).
That is better than most production admin screens. The remaining gap-1 findings are the operations
this block does not cover (H3, H4) and the two dimensions it does not carry (M1, M4).

**Gap 4 is not open in the retroactive block.** `admin.js:3087` renders `op.whatIsMissing` — the
server's sentence explaining *why the operation exists* — directly on each operation card. The
count button is a dry-run preview placed next to the run button, which is NN/g 5 done properly.
`restartable` / `blocked` / `cli_only` are all spelled in place rather than left to a document.
This is the pattern the rest of the screen should be measured against, not a gap.

**Gap 3 is partly handled.** Three genuine accelerators exist:
deep links (`#overview`, `#file`, …, and `#editor=<path>` which opens a specific script directly —
`admin.js:530-539`); health cards that jump to a **pre-filtered** tab
(`switchTab('file', { statusFilter: 'FAILED' })`, `admin.js:665-668`); and the grid → admin scope
handoff (`adoptRescopeHandoff`, `admin.js:2946-2972`), which carries a selection from the data grid
into the retroactive parameters and deliberately consumes it once. That last one is a real
expert path across screens. The gap is that nothing else was built in that spirit.

---

## 모르는 것

Things I could not judge from source alone, stated so they are not read as absences.

1. **Whether the server exposes a step/phase at all.** M4 says the client never shows one. I did not
   audit the retroactive worker or the chain replay path to find out whether a phase exists and is
   simply not carried, or does not exist. That determines whether M4 is a client round or a
   server-first one. *This is the single most load-bearing unknown in this report.*
2. **How long these operations actually take.** "More than ~10 seconds" is the NN/g threshold, and I
   applied it on the shape of the work (module re-import + initial sweep; a walk until rows run out;
   a collector script), not on measurement. Measuring here would mean measuring this box, which is
   forbidden as a claim about production. If reload-configs is reliably sub-second in production,
   H4 drops to low.
3. **Whether the restore-for-scripts path actually works.** H1's cheap-fix note is read off the
   prefix guard at `server/main.py:6750-6754`. I did not execute a GET against a
   `mappers/backup/…` path, and `_resolve_admin_script_path` may normalise in a way I did not trace.
4. **Retry-all batch sizes in production.** M2's severity assumes "all" can be large enough that an
   unstated count matters. If the realistic number is always single digits, M2 is low.
5. **Whether operators use the keyboard at all.** L1 assumes they would if they could. I have no
   observation of how this screen is actually driven, and a mouse-only operator would rank L1 below
   L2.
6. **Rendered appearance.** No page was run. Everything above is read off markup, handlers and view
   models; anything that depends on how it actually looks — whether an indeterminate bar reads as
   "stuck", whether the red badges are distinguishable in practice — is inference.
7. **Out of scope but noticed, flagged rather than judged:** `admin.js:577` hides the health strip
   unconditionally while `refreshHealthStrip()` keeps running on the 30 s loop and painting into it
   — four `setHealthCard` call sites writing to a hidden element. That is dead work rather than a
   UX gap in my four, but it is why no surface outside the Auto Update tab could have rescued H3.
