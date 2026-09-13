# QA — retroactive (backfill) admin screen, client half

**Tier:** T2 · **Scope:** uncommitted working tree · `client2/src/retroactive_view.js` (new, 298),
`client2/src/admin.js` (+386), `client2/src/config_resolve_view.js` (+15/-5), `client2/admin.html`
(+79), `client2/tests/retroactive_view_harness.mjs` (new, 433). Server side `fbc1053`.

**Not re-confirmed** (parent already ran it): the harness result. Everything below is what a green
harness cannot see — the DOM wiring in `admin.js`, the state machine across two buttons, the CSS,
and the payload shapes `server/retroactive.py` actually emits.

---

## 1. Verdict

**GO-WITH-FIXES.**

The central contract holds. I attacked the claim "the client never authors a sentence" and could not
break it: every operator-facing string that leaves `retroactive_view.js` is either a payload string,
the operator's own input, a structural slot name, or the single `role:'question'` line — and
`buildConfirmLines` genuinely emits exactly one client sentence, last. `cfgEl` writes with
`textContent` only, so verbatim really is verbatim.

What does not hold is **the binding between a number and the input it was measured for**, and
**exactly-once on the write path when the two buttons interleave**. Neither corrupts data — the
server re-validates and runs whatever it was actually sent — but F1 lets the confirmation assert a
measurement for parameters that are not the ones being submitted, which is core value #3's failure
mode exactly: quiet, plausible, wrong. F1 and F2 should land before commit; the rest can be queued.

---

## 2. Confirmed defects

### [HIGH] F1 — the cached count is not invalidated when the operator edits the parameter

`client2/src/admin.js:2029` (input listener) · `:2174` (`retroCountByOp.set` keyed by `op.op` only) ·
`:2203` (`buildConfirmLines(op, countView, params)`)

The count is cached per **operation**. The typed parameters live in a **separate** map. The input
listener writes only to `retroParamsByOp`; it never touches `retroCountByOp`. Nothing anywhere
records which parameters produced a cached count.

**Failure scenario — measured, not theorised.** I fed the real `_count_chain_replay` payload shape
through the real module:

1. Operator types `rule = inv`, presses 건수 확인 → `덮어쓸 셀 594` box appears.
2. Operator changes the input to `rule = lot_alias`. **The 594 box does not change and is not
   marked stale.**
3. Operator presses 실행. The one confirmation reads:

```
체인 규칙 소급 적용 (R1)
rule = lot_alias                          <- input, the NEW rule
덮어쓸 셀
594                                        <- measured for rule=inv
트리거 테이블 200행을 표본으로 검사해 594개 셀을 다시 씁니다. …
커밋 단위 / per chunk
이 소급 적용을 실행 큐에 넣습니다. 계속할까요?
```

`_count_chain_replay`'s `detail` (`server/retroactive.py:171-176`) **does not name the rule** — I
checked the string it composes. So there is **nothing in the dialog** that reveals the number belongs
to a different parameter. The operator authorises a write against `lot_alias` while reading a
measurement of `inv`, and both the number and the whole server sentence are wrong for what runs.

Same defect on the row itself: the stale box sits under the edited input indefinitely.

Also stale by the same root cause: `admin.js:2058` disables/enables the run button from
`cached.view.blocked`, i.e. from the *old* parameter's block state.

**Recommended:** clear `retroCountByOp.delete(op.op)` in the input listener (`:2029`), or store the
param snapshot alongside the count and refuse to carry it into `buildConfirmLines` when it differs.
Deleting is simpler and matches F9's `dryRunByRule.clear()` precedent.

---

### [HIGH] F2 — pressing 건수 확인 during a queuing run re-arms the write button

`client2/src/admin.js:2190` — `actions.parentElement.replaceChild(retroActionsEl(op, host), actions)`

There is **no per-operation run-in-flight state anywhere** (grep: no `retroRunInFlight`;
`retroactiveInFlight` at `:1892` guards only the operations-list fetch). The only thing that says
"a run is queuing" is the `disabled` flag and the `요청 중…` label on that one button object.

`runRetroactiveCount`'s `finally` rebuilds the entire actions row unconditionally, and
`retroActionsEl` (`:2049`) always constructs a **fresh, enabled** run button reading `실행`.

**Failure scenario → two outbox rows:**

1. Click 실행 → confirm → OK → POST in flight; button disabled, reads `요청 중…`.
2. Click 건수 확인 (a separate, enabled button — nothing blocks it).
3. The GET returns first. `finally` replaces the actions row. **The screen now shows an enabled
   `실행` button and no sign a run is pending.**
4. Operator presses 실행 again → second confirm → second POST → **second `RETROACTIVE_RUN` outbox
   row with a different `run_id`**.
5. Both POSTs resolve; `host` is wiped twice, so only the *second* `run_id` is ever displayed. The
   first row exists and is invisible.

The window is the POST latency. Behind the corporate proxy (2026-07-30 incident class) that is not
negligible, and 건수 확인 immediately after 실행 is a natural operator move on a screen whose whole
vocabulary is "count, then act".

**Recommended:** a `retroRunInFlight` Set keyed by `op.op`, consulted in `retroActionsEl` so any
rebuild reconstructs the disabled state, and checked at the top of `runRetroactiveRun` before
`confirm()`.

---

### [MEDIUM] F3 — an unknown `count_kind` draws exactly like `exact`

`client2/src/retroactive_view.js:84` — `const KIND_TONE = { exact: '', sample: 'warn', upper_bound: 'warn' };`

The module comment claims "a kind this client has never heard of draws neutral rather than being
guessed at". Measured through the real function:

| `count_kind` | rendered word | `kindTone` |
|---|---|---|
| `exact` | exact | `""` |
| `sample` | sample | `"warn"` |
| `upper_bound` | upper_bound | `"warn"` |
| `estimate` | estimate | **`""`** |
| `floor` | floor | **`""`** |

Neutral is not a safe default here, because **neutral is already the colour of `exact`**. A future
approximate kind renders in the one colour that means "this number is the answer". F9's
`POPULATION_TONE` (`config_resolve_view.js:135`) does **not** have this collision — its safe value
`effective` maps to `'ok'`, so unknown → `''` is genuinely distinct there. This round copied the
shape and broke the property.

**Recommended:** map `exact` to an explicit tone (e.g. `'ok'`) so `''` means "unrecognised" and only
that, matching the table it was modelled on.

---

### [MEDIUM] F4 — the confirmation drops two of the server's three exactness carriers

`client2/src/retroactive_view.js:272-298` (`buildConfirmLines`)

The design states the qualifier travels in three places: `count_kind`, the label text, and `detail`.
The count **box** renders all three plus `truncated` (border) and `why_upper_bound`. The
**confirmation** — the last surface before a write, and plain text, so no colour can reach it —
carries only label + number + `detail`. Measured:

| carrier | in count box | in confirm dialog |
|---|---|---|
| `affected_label` + `affected` | yes | yes |
| `detail` | yes | yes |
| `count_kind` (`sample` / `upper_bound`) | chip | **no** |
| `truncated` (the number is a floor) | amber border | **no** |
| `extra.why_upper_bound` | sentence | **no** |
| labelled `extra` numbers | chip line | **no** |

Today this survives by luck, not by rule: I checked all five `detail` strings in
`server/retroactive.py` and each happens to contain 표본 or 최대. Two of the five labels
(`덮어쓸 셀`, `새로 만들 파생 행`, `사람 없이 확정 가능한 건`) carry **no** qualifier, so for those
three operations the dialog's honesty rests entirely on one field. `truncated` reaches no dialog for
any operation.

**Recommended:** carry `kind` into the confirm lines as a server-owned word (it already is one — no
new sentence needed), and once the server puts truncation in `detail` (see §5.1) it will flow
automatically.

---

### [MEDIUM] F5 — the run acknowledgement is the only state a re-render destroys, and it is the one that must not be lost

`client2/src/admin.js:2231` (`host.appendChild(retroQueuedEl(view))` — never cached) ·
`:1959` (`renderRetroactive` wipes `body`) · `retroactive_view.js:242-251` (`buildRunView`)

Counts survive a re-render (`retroCountByOp`, re-appended at `:2065`). Typed params survive
(`retroParamsByOp`, re-read at `:2026`). The **queued box carrying the `run_id` is not stored
anywhere** — `renderRetroactive()` deletes it permanently. The toast is already gone by then.

Re-render is reachable two ways: `reloadSystemConfigs()` → `refreshRetroactiveOperations(true)`
(`:3115`), and any `adminTokenGeneration` bump (any token prompt anywhere on the page) making the
next 30-second overview poll refetch (`:1919-1921`, `:2256`).

Compounding: `retroactive.publish` returns `params` (`server/retroactive.py`, the `publish` return),
and `buildRunView` **drops it**. So the acknowledgement never states *what* was queued — which is
precisely the fact that would have caught F1.

Worse in the mid-flight case: if the re-render happens while the POST is in flight, the closure's
`btn`/`host` are detached nodes. `host.appendChild(retroQueuedEl(view))` appends to nothing, the
toast is the only signal, and the on-screen button was rebuilt enabled — the same duplicate-write
path as F2 by a different route.

**Recommended:** cache the run view per op the way counts are cached, and render `params` in it.

---

### [MEDIUM] F6 — no content-unchanged guard on re-render; the operator's open sub-details collapse

`client2/src/admin.js:1928-1933`

F9's adjacent function has this exact guard with this exact reason:

> `admin.js:1648` — `if (raw === configResolveRaw && configResolveView) return;`
> "매번 다시 그리면 운영자가 펼쳐 둔 참조뷰가 읽는 도중에 접힌다"

`refreshRetroactiveOperations` has no equivalent. It re-renders on **every** successful fetch even
though the payload is static by design (the function's own comment says the list "cannot change
until the server restarts"). Every `버튼이 덮지 않는 것` details the operator opened
(`retroCliEl`, `:2100`) closes underneath them. This is the same lesson the file above already
learned, not a new one.

---

### [MEDIUM] F7 — the number that governs the write decision is the smallest text in its box

`client2/admin.html:657` `.cfg-jsonval { font-size: 0.82rem }` (the `affected` number) ·
`:587` `.cfg-chip { font-size: 0.74rem }` (the `count_kind` qualifier) ·
`:665` `.cfg-detail { font-size: 0.88rem }` (the prose)

Rendering order by size on this surface: prose 0.88 > label 0.86 > **the number 0.82** > **the
exactness declaration 0.74**. On a screen whose entire purpose is "how many rows will this write
touch, and how sure is that number", the number and its qualifier are set smaller than everything
around them, and `.cfg-jsonval` is a class designed for echoing JSON config values.

"가독성은 기능이다" is a core value here. This is not a nit — the two facts a write decision rests
on are the two least legible things in the box.

---

### [LOW] F8 — CSS comment claims a size the CSS does not set

`client2/admin.html:752-754`

```
/* 「가독성은 기능이다」 — 입력칸은 본문 크기로 둔다. 좁혀서 끼워 넣지 않는다. */
.retro-input { font-size: 0.86rem; … }
```

0.86rem is below the block's own body text (`.cfg-detail` 0.88rem) and well below 1rem. The comment
asserts a property the rule does not have — exactly the overstatement class this round exists to
police.

---

### [LOW] F9 — `buildExtras` orders by internal key name and renders into one separator-less line

`client2/src/retroactive_view.js:189` (`Object.keys(source).sort()`) ·
`client2/src/admin.js:2115-2120`

With two labelled extras, measured output is:

```
사람이 고정한 셀 12 값이 사라진 셀 (쓰지 않음 · R2 후보) 7
```

`.cfg-dryrun-refused` (`admin.html:708`) is a bare flex row with `gap: 6px` and **no separator
between pairs**, so `12 사람이 고정한 셀` runs together — a value can read as belonging to the next
label. And the display order is the ASCII order of the server's internal key names (`pinned` before
`withdrawal_candidates`), not a server decision, which contradicts the module's stated principle
that "which numbers reach the operator is the server's decision".

**Latent, not live:** I checked all five `extra` dicts in `server/retroactive.py`. Exactly one
labelled pair exists across all five operations (`withdrawal_candidates` on `chain_replay`), so
today only one chip ever renders. The moment a second label lands, this fires.

---

### [LOW] F10 — `retroParamsByOp` is never cleared, not even on force

`client2/src/admin.js:1930` clears `retroCountByOp` on force; `retroParamsByOp` (`:1897`) is cleared
nowhere. If a restarted server's inventory renames or removes a parameter, the stale key stays in
the map and `retroParamEntries` (`:1906`) still sends it. `main.py:4720-4721` documents that unknown
parameter names are rejected with 400, so the operator gets an unexplained refusal on a field that
is no longer on screen.

---

### [LOW] F11 — `.cfg-dryrun-refused` reused for a non-refusal

`client2/src/admin.js:2115`. The class name means "refused" in the F9 dry-run vocabulary; here it
carries neutral context (`값이 사라진 셀 … 0`). Visually harmless today because the rule is layout
only, but the next person who gives `.cfg-dryrun-refused` a danger colour will silently paint R1's
withdrawal candidates red.

---

## 3. Attacked and safe

Each of these was a hypothesis I tried to make fire, with the reason it did not.

- **"The gate-rejection retry duplicates the POST."** `admin.js:147-149` and `:159` both re-`fetch`
  the same `init` (a string body, re-sendable). Safe: a gate-rejected POST never reached
  `retroactive.publish`, so no outbox row exists to duplicate. Max one row either way.
- **"A rejection produces a repeated or infinite credential prompt."** `adminTokenDeclined`
  (`admin.js:69`, checked at `:151`) latches on cancel and is never reset except by page reload;
  `tokenPromptInFlight` (`:70`, `:88`) coalesces concurrent prompts into one. Verified both guards
  are on the path these routes take (they go through `adminFetch` unchanged).
- **"404 misfires on an operation-level error, so a current server reads as an old build."**
  `main.py:4739` and `:4748` return **400** for unknown op, missing/unknown params, and
  uncomputable counts; `:4778` returns 400 on the run route. Nothing on these routes returns 404
  except FastAPI's own "no such route". So `fetchFailureText`'s 404 → 「실행 중인 서버가
  구버전입니다」 (`config_resolve_view.js:97`) is correct in every reachable case.
- **"401 with the challenge and 401 without it are distinguished by status, not header."** They are
  not — `isGateRejection` (`admin.js:80-85`) tests the `WWW-Authenticate` value and ignores the
  status split, `failureFactOf` (`:1617-1623`) reuses that one function, and `retroFailureLine`
  (`:2140`) delegates to `fetchFailureLine`. There is exactly one classifier; no second copy was
  introduced. 403 routes through the same test.
- **"The 503 body is consumed twice."** `adminFetch:137` reads `res.clone().json()`, leaving `res`
  unread for `retroFailureLine`'s `res.json()` at `:2143`. No `TypeError`, and the double-toast the
  implementer found is genuinely fixed at `:2222` (`if (res.status !== 503)`).
- **"A bare number reaches the screen."** `buildCountView:210` gates `affected` on `affectedLabel`,
  `admin.js:2103` gates the render on **both**. Fed `affected_label: null` with `affected: 594`: the
  head renders nothing, and the 594 that still appears comes from `detail` — inside a sentence, as
  designed.
- **"`affected: 0` is swallowed by a truthiness check."** No — `count(0)` returns an object
  (`config_resolve_view.js:169`), so `0` renders. Same for extras.
- **"An unlabelled extra renders anyway."** `buildExtras:192` requires both `label` and `value`. I
  checked every `extra` dict in `server/retroactive.py`: `cells_claimed`, `pinned`, `queue_size`,
  `keys_examined`, `written_cells`, `already_derived`, `distinct_combinations`, `skipped_blank`,
  `user_protected_cells`, `samples`, `sample_new_keys` all lack a `_label` and all are dropped.
- **"Extras get summed into the primary count."** They cannot: separate view fields, separate DOM
  containers (`:2103` head vs `:2116` line), and `buildConfirmLines` carries neither into the same
  line. `withdrawal_candidates` genuinely appears beside `affected` and never inside it.
- **"The client injects markup from a server string."** `cfgEl` (`admin.js:1592-1598`) assigns
  `textContent` only. Every server string goes through it. (The literal `**삭제**` markdown in
  `graph_orphans`' `detail` therefore renders as visible asterisks — §5.2 — but is inert.)
- **"The confirmation is a wizard."** One `confirm()` (`:2204`), one question line, `role:'question'`
  emitted exactly once and last. No new modal, no second step.
- **"An operator input is re-authored on the way into the dialog."** `buildConfirmLines:284` carries
  `entry.value` verbatim with `raw` alongside it.

---

## 4. Runtime verification needed

Code alone cannot settle these.

1. **Double-click / held-Enter on 실행.** `btn.disabled = true` happens *after* `confirm()`
   (`:2204` then `:2207`). I reason a tab-modal `confirm()` prevents the page from receiving the
   second click, so the modal is the guard — but that is browser behaviour, not something the source
   proves. Worth one measured double-click and one held-Enter (key repeat can dismiss the dialog and
   re-fire the click) with a network trace counting `/run` requests.
2. **F2's window under real latency.** How long the POST is actually in flight through the corporate
   proxy determines whether step 2-3 is a race or a comfortable pause.
3. **F7's rendered sizes** against the page's computed base font — I read the CSS, not the render.
4. Whether `truncated` is in fact the normal case in production. `DEFAULT_SCAN_LIMIT = 200`
   (`server/retroactive.py:136`) and the client never sends `scan_limit`, so any in-scope table over
   200 rows makes the headline number a floor. If that is always, F4/§5.1 are not edge cases.

---

## 5. Server-side findings (re-derived, not taken from the report)

The implementer's §6 raises three. All three check out; I add a fourth observation.

**5.1 `truncated: true` has no sentence — confirmed, and the precedent is one file away.**
`_count_chain_replay:171-176`, `_count_enrichment_backfill:245-249`, `_count_enrichment_confirm:275-277`
all compute `truncated` and none mention it in `detail`. The sibling route does:
`server/main.py:4666` appends 「⚠️ 표본 {limit}건까지만 본 결과입니다 — 큐는 더 클 수 있습니다.」
The client is right to refuse to compose it.

**Additional, and it is the client's to know about:** the server ships `scanned` and `scan_limit` at
the top level of every count response (`:168-169`, `:242-243`, `:285-286`). `buildCountView`
**reads neither** — measured, they are absent from its output keys. So the two numbers that would let
an operator see "200 scanned of a 200 budget" arrive at the client and are dropped, because they have
no `_label` and the module's rule forbids rendering an unlabelled number. The rule is right; the
consequence is that a floor is presented with a border colour as its only qualifier. Labelling those
two server-side is a smaller fix than rewriting `detail`, and it flows into `buildExtras` with no
client change.

**5.2 `graph_orphans` `detail` ships literal markdown — confirmed.** `server/retroactive.py:317-319`
contains `노드를 **삭제**하고` and `**전부 롤백**됩니다`. `cfgEl` uses `textContent`, so the
asterisks are on screen as characters. INV-F9-8's reasoning applies.

**5.3 `deletes` / `commit_granularity` are English in a Korean dialog — confirmed server-owned.**
They come from the `OPERATIONS` spec verbatim via `retroactive.count`'s `out.update({...})` and the
inventory. The client cannot fix this without paraphrasing, which is the prohibited move. Server
decision.

**5.4 The count is a 200-row sample; the run is unbounded.** `DEFAULT_SCAN_LIMIT = 200` /
`MAX_SCAN_LIMIT = 2000` (`:136-137`), and `execute` calls `spec["run"](db, params, log)` with no
limit. The gap between what is measured and what runs is the whole reason F4 matters.

---

## 6. UI constraints

- **New screen area / mode / modal: none.** Verified in markup — `admin.html:1134-1150` adds one
  `<details class="cfg-block">` inside the existing Overview column, same `recorrection-line` grammar
  as the three instruments above it, collapsed by default. The confirmation is the browser's
  `confirm()`, not a custom modal.
- **"Net control delta is zero" does not hold literally** and cannot for a screen that adds five
  write triggers. Honest accounting: **at rest, +1** (one collapsed summary row, matching the three
  existing instrument rows). **Expanded, roughly +24** — per operation 2 buttons + 1 `cli_only`
  details toggle, plus one text input per declared parameter, across five operations. The constraint
  that actually governs ("새 영역·모드·모달 금지") is satisfied; the zero-delta phrasing is not the
  right test for this change and should not be recorded as passed.
- **Reading frictionless:** yes for the list; **no** for F7 (the two governing facts are the smallest
  text) and **no** for F6 (opened sub-details collapse under the operator).
- **Writing confirms once:** one dialog, one question — but see F2, where the *state* around it can
  be re-armed without a second intent.
- **Korean/English mixing:** genuinely server-owned (§5.3). The client could not have avoided it
  without violating the verbatim rule. The implementer's judgement here was correct.

---

## 7. Documentation alignment

I looked the rows up by changed code path in `docs/process/DOC_OWNERSHIP.md` rather than following
the implementer's follow-up list. Their list is right as far as it goes and **misses row 42**.

**Row 51** (소급 운영 경로) states its own list for the day the screen lands, and the implementer
reproduced it correctly: `BACKFILL_GUIDE §7 서두 · §7.4 · §0`, `FEATURE_CHECKLIST §1.8 행 ·
§2.8-quinquies 서두`, `docs/README`의 BACKFILL 행, plus row 51's own
「⚠️ 화면(버튼)은 `77d27d3` 기준 아직 없다」 which is now false.

**Row 42** (프론트엔드) carries a hard rule the implementer did not cite:
「**§3 모듈 표는 `client2/src/*.js` 전수를 덮어야 한다**(행 없는 모듈은 조용히 낡는다)」.
Three edits follow from it, and only the third is arguably in their list:

| `docs/architecture/frontend.md` | says | measured |
|---|---|---|
| §3 module table | **no row for `retroactive_view.js`** | new module, 298 lines — needs a row (the precedent is line 12's own note: 「§3 모듈 표에 `config_resolve_view.js` 행 신설(줄 수 실측 235)」) |
| §3 line 124 `admin.js` | 3155 | **3588** |
| §3 line 125 `config_resolve_view.js` | 235 | **324** |

**Row 66** (어드민) → `frontend.md §5`: the Overview instrument count moves from three to four and the
fourth is undescribed. Correctly identified by the implementer.

**Row 63** (config 해석 보고서) → should note `config_resolve_view.js` now exports its four taggers
and has a second consumer. Correctly identified.

**Board:** `docs/process/PROJECT_STATUS.md` has already been updated by the lead PM with this round's
result and the three server defects. Current, no action.

**One gate result to discount:** the report's `npm run check:contracts` → "6 contracts" is
contaminated by the shared tree — `contracts/blank_predicate/` is another lane's untracked work.
`DOC_OWNERSHIP` row 38 records 5 as of 2026-07-30. That number is not evidence about this change
either way, and row 38's count should be re-measured by whoever lands `blank_predicate`, not here.

**No overstatement found in the code comments** except F8. The module header's claims about what it
is allowed to know are accurate; the `🔴` markers sit on the properties that are actually enforced.
The one exception is `KIND_TONE`'s "draws neutral rather than being guessed at" (F3), which is true
of the code and false of what the operator sees.

---

## 8. Suggested lesson for `agent_workspace/memory/qa-reviewer.md`

> - **함정**: 뷰 모델이 DOM-free 모듈로 분리돼 하네스가 초록이면 「렌더 계약은 검증됐다」고 읽고
>   배선 파일을 훑고 만다. 하네스는 **함수 하나의 입출력**을 채점할 뿐, 두 버튼이 같은 캐시와 같은
>   DOM 호스트를 공유할 때 생기는 **상태 기계**는 보지 못한다 — 캐시 무효화 누락·재렌더 중
>   detached 노드·in-flight 플래그 부재는 전부 하네스 밖이다.
>   **올바른 방법**: 뷰 모델이 초록이면 검수 시간을 **배선 파일의 상태 변수 목록**에 쓴다. 캐시
>   Map 하나마다 「무엇이 이걸 무효화하는가 · 무효화 계기가 코드에 있는가」를 묻고, 쓰기 버튼마다
>   「이 버튼을 다시 만드는 코드 경로가 몇 개이고 각각 in-flight를 복원하는가」를 센다.
