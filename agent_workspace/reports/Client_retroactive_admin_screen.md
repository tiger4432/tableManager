# Client — the retroactive (backfill) admin surface

**Round:** build the client half of `fbc1053`. **Status:** landed, exercised against a running
backend, not committed. **Verdict: GO** — with three findings that are the *server's*, not the
screen's (§6), and one leftover I will not clean up without your word (§7.1).

---

## 1. What I built, and where it went

**No new screen, no new tab, no new mode, no new modal.** The admin Overview already reads as a
column of one-line instruments — 재교정률 / 교정 공수 / 설정 반영 — and F9's config-resolve line is
the third. This is the **fourth row**, same `<details class="cfg-block">` grammar, same
`.recorrection-line` summary, same cfg-* vocabulary, collapsed by default.

Per operation the whole surface is **the count and a button**, exactly as briefed:

```
체인 규칙 소급 적용 (R1)                        ← label            (server)
규칙보다 오래된 데이터를 그 규칙이 한 번도 보지 못했다   ← what_is_missing  (server)
커밋 단위  crud.apply_batch_updates commits …    ← commit_granularity (server, verbatim)
파라미터   rule [필수] [__________]
          chain rule name (GET /admin/chain/rules)  ← help          (server)
[건수 확인] [실행]
버튼이 덮지 않는 것 3 ▾                          ← cli_only         (server)
```

Files:

| path | what |
|---|---|
| `C:\Users\kk980\Developments\assyManager\client2\src\retroactive_view.js` | **new, 298 lines.** DOM-free view model. Every string it emits is tagged with its provenance. |
| `C:\Users\kk980\Developments\assyManager\client2\src\admin.js` | +386. Fetch/render/confirm wiring, inserted directly after the config-resolve section. |
| `C:\Users\kk980\Developments\assyManager\client2\admin.html` | +79. The fourth row's markup, and the `retro-*` CSS the cfg-* vocabulary did not already have. |
| `C:\Users\kk980\Developments\assyManager\client2\src\config_resolve_view.js` | +15/−5. **Exports** the four provenance taggers (`srv`/`val`/`chrome`/`count`) instead of me copying them. Nothing else changed. |
| `C:\Users\kk980\Developments\assyManager\client2\tests\retroactive_view_harness.mjs` | **new, 433 lines.** Scores the discipline; auto-discovered by `check:harnesses`. |

## 2. The contract, made mechanical

The brief said the server makes the sentences and the client renders them verbatim. I turned
that into a rule a machine can check, because "we render `detail`" is not falsifiable and
"a number never appears without the server's label for it" is:

- **`buildCountView` returns `affected: null` whenever `affected_label` is absent.** The
  qualifier for four of five counts lives *inside* the label (`"회수할 셀 (최대)"`,
  `"고아 후보 노드 (최대)"`). A bare integer is read as the answer, and for four of five it is
  not one. If the server declines to label a number, the screen shows no number — `detail` still
  carries it inside a sentence.
- **`count_kind` renders as the server's own word** (`sample`, `upper_bound`) in a chip, the way
  F9 renders population names. It is never translated and never re-judged.
- **`count_kind`, `restartable`, `truncated` feed a colour and nothing else.** `KIND_TONE` is
  shaped and commented exactly like F9's `POPULATION_TONE`; an exactness declaration this client
  has never heard of draws neutral rather than being guessed at (harness-checked).
- **Which second number reaches the screen is the server's decision, made in the payload.**
  `buildExtras` renders a number from `extra` **iff** the server also sent `<key>_label`. That is
  how `withdrawal_candidates` + `withdrawal_candidates_label` appears without being added into
  `affected` — R1 never writes a blank, and summing the two would charge the writing operation
  with the count of the one thing it deliberately refuses to do. No key names are hardcoded; the
  server can label another number tomorrow and the screen shows it with no client change.
- **The confirmation is one client sentence.** `buildConfirmLines` returns tagged lines, not a
  string: `role:'question'` appears exactly once and is last; every other client line is
  `role:'label'` and must be *followed by the value it names*. Everything else is a server string
  or the operator's own input read back.

## 3. Reuse — what I did not build

- **`adminFetch` / `isGateRejection` / `fetchFailureLine` / `CHROME.FETCH_*`: reused, not
  re-derived.** These routes landed after `1dc761b`, so an older process 404s here for the same
  reason and the same proxy answers the same port. There is still exactly **one** classifier of
  "who refused" in `admin.js`, and my module imports `CHROME` rather than re-authoring the five
  sentences. Verified live in §5.
- **One new rule, and it needed no new branch.** A 400 refusal carries a server sentence
  (`"refusing to withdraw source 'user': …"`) that a generic 「조회 실패」 would throw away. I get
  it by passing the server's `detail` as `fetchFailureLine`'s **fallback** — the existing splitter
  keeps ownership of no-response/404/401, and the server's words win everywhere else.
  (`retroFailureLine`, `admin.js`.)
- **The four provenance taggers moved from private to exported** rather than being copied into
  the second module. `TEXT_SOURCES` and `collectTexts` already lived in `config_resolve_view.js`
  and both harnesses read them from there; a second copy of `srv()` is how `DUPLICATION_LEDGER`
  entries begin.
- **Refresh policy is not a copy of F9's throttle.** `/admin/retroactive/operations` does zero DB
  queries and cannot change until the server restarts, so it loads **once per page, plus when the
  cause changes** (a token arrived, or Reload Configs was pressed) — four lines, and it can answer
  "why did you re-read just now".

## 4. The harness, and what it caught

`node client2/tests/retroactive_view_harness.mjs` — **177 passed, 0 failed; 7/7 defect mutants
caught; 2/2 control mutants escaped.** The payload fixtures were captured from the running server
on 2026-07-31, not imagined; server sentences are replaced with `<<markers>>` so any rewording
fails loudly. Mutants that must be caught include *bare number reaches the screen*, *the server
sentence is reworded on the way out*, *the client decides what the count kind means*, *an
unlabelled extra number is rendered anyway*, *the confirmation paraphrases the danger*.

**It caught a real defect in my own code on its first run.** My first `buildConfirmLines` emitted
three client-authored lines (the question plus two slot labels) where the contract allows one. The
check was right that something was wrong and wrong about what; the fix was to give labels a role
and require each to be followed by its value, which is a sharper property than the one I started
with. That is the only reason the label/value pairing exists.

Also green after my edits: `contracts/config_resolve_report/client_harness.mjs` (159 strings
scored, no divergence), `npm run check:contracts` (6 contracts). No forbidden client literal
appears in any file I touched.

## 5. Exercised against running backends — what I observed

I did **not** run `npm run build` and did **not** touch `client2/dist`. Verification ran the real
`client2/src` through a throwaway vite dev config in my scratchpad on a **non-5173 port**, which
makes `admin.js` resolve `API_BASE = window.location.origin`, with `/admin/*` proxied to a backend
I chose per instance. Nothing in the repo was modified for testing.

| port | backend | why |
|---|---|---|
| **5199** | **:8080**, the running server (routes present, `ASSY_ADMIN_TOKEN` unset) | real counts, real refusals, the fail-closed write |
| **5198** | **:8081**, the isolated process — **older than `fbc1053`** | the genuine 404 |
| **5197** | fake gate on :8098 | 401 with and without our challenge header |
| **5196** | **:8099**, an isolated API **I started**: `ASSY_DATA_ROOT=dev_env`, `DATABASE_URL=…/assy_qa`, `ASSY_ADMIN_TOKEN` set | the queued write path |

### 5.1 Reads (:8080, measured 2026-07-31 ~20:35 KST)

- `chain_replay rule=inv` → head `덮어쓸 셀 594` + chip `sample`, box bordered amber
  (`truncated`, 200 scanned of a 200 budget), server `detail` verbatim, and the labelled second
  number `값이 사라진 셀 (쓰지 않음 · R2 후보) 0` rendered **beside** 594, never summed into it.
- `graph_orphans` → card bordered **red** (`restartable: false`), red `삭제 대상` chip carrying
  `graph_nodes rows (derived data; …)`, head `고아 후보 노드 (최대) 12786` + chip `upper_bound`,
  and **both** server sentences (`detail` and `extra.why_upper_bound`).
- `chain_replay` with an empty `rule` → the server's own refusal on screen:
  `'chain_replay' requires parameter 'rule' (chain rule name (GET /admin/chain/rules))`.
- `withdraw table=inventory_master source=user` → the server's refusal, verbatim:
  `refusing to withdraw source 'user': it is the layer that means 'a human typed this'. …`
- `enrichment_confirm rule=core_wafer_attribution` → `이 연산의 건수를 계산할 수 없습니다: rule
  '…' declares no 'candidate_for' on any reference view, …` — the live F9 state, rendered as the
  server said it rather than as a shrug.

### 5.2 The count route returns a gate rejection

Both halves of the 401 split, both real HTTP:

- **401 + `WWW-Authenticate: X-Admin-Token`** → **exactly one** token prompt, from the existing
  `adminFetch` mechanism (I counted the calls: 1). On cancel the row reads
  **「관리자 토큰이 거부되었습니다 ― 새로고침 후 다시 입력하세요」**. No second prompt, no modal of
  my own, no toast.
- **401 + `Basic realm="corp-proxy"`, `Server: squid/5.7`** → **zero** prompts, and the row reads
  **「관리자 게이트가 아닌 응답입니다 ― 프록시 등 앞단에 무엇이 있는지 확인하세요 (squid/5.7)」**.
  The responder is named. This is the 2026-07-30 incident class, and it costs nobody an afternoon.

Only `window.prompt` was stubbed (returning `null`, which is what a cancel returns) — the native
modal blocks the automation thread. Every other line ran for real.

### 5.3 The count route returns 404

Against :8081, a process older than the routes: the row goes muted, value `―`, and reads
**「실행 중인 서버가 구버전입니다 ― 서버를 재시작하세요」** — byte-identical to what the
config-resolve line one row above says at the same moment, because it is the same constant from
the same classifier. The block stays **closed** and its body stays empty; no auto-open, no toast.
A failed read never reads as "there is nothing to do here".

### 5.4 The write

- **Fail-closed (:8080, no token configured).** Confirm → POST → **503**, and the server's own
  sentence appears: 「이 기능은 관리자 토큰이 설정되어야 사용할 수 있습니다. 서버 환경변수
  ASSY_ADMIN_TOKEN를 설정한 뒤 서버를 재시작하세요.」 Nothing was executed against production.
- **Queued (:8099, token configured, isolated DB, no scheduler running).** Two runs, and I checked
  the far side rather than the screen:

  ```
  224310  RETROACTIVE_RUN  __retroactive__  {'op': 'graph_orphans', 'params': {},              'run_id': '90a60c688acb', …}
  224311  RETROACTIVE_RUN  __retroactive__  {'op': 'chain_replay',  'params': {'rule': 'inv'}, 'run_id': 'fcdc6fe16231', …}
  ```

  One click → one `confirm()` → one outbox row → the same `run_id` on screen and in the row.
  Parameters travel. Declining the dialog posts nothing (I checked: zero `/run` requests).
- **The single confirmation, captured verbatim** (graph_orphans, after a count):
  label → labelled count → the server's sentence → `삭제 대상` + what it deletes → `커밋 단위` +
  how it commits → **「이 소급 적용을 실행 큐에 넣습니다. 계속할까요?」**. One question. One dialog.
  Pressing run *without* measuring first loses the number and keeps every warning, because
  `retroactive.count` copies those facts off the same spec the inventory does.
- **`blocked_reason` disables the button.** Live config cannot produce it (nothing declares
  `candidate_for` anywhere), so I faked **one response** while every line of client code ran: the
  run button went `disabled`, `title` = 「실행이 거부되는 상태: auto_confirm_off」, and the reason
  word appeared as data. This is the branch the server asked for in its own comment.

### 5.5 One defect the exercise found in my code

The 503 path toasted **twice** — `adminFetch` already surfaces 503 bodies and I toasted again.
Fixed by deferring to the existing mechanism (`if (res.status !== 503)`), re-measured: one toast,
and the durable line stays in the row where the button is. I would not have found this by reading.

## 6. What I want you to re-measure — three of them are the server's

**6.1 `truncated: true` has no server sentence on this route, and the screen can only colour it.**
`GET /admin/enrichment/auto-confirm/dry-run` appends 「⚠️ 표본 N건까지만 본 결과입니다 — 큐는 더 클
수 있습니다」 when its sample is cut off. `_count_chain_replay` and `_count_enrichment_backfill`
compute `truncated` and **say nothing about it in `detail`**. Measured: `rule=inv` scanned 200 of a
200 budget, so 594 is a floor, and the only thing on screen that says so is an amber border. I
refuse to compose the missing sentence — that is the defect class the round exists to avoid.
**Ask the server lane to put it in `detail`, where the other qualifiers already live.**

**6.2 `detail` for `graph_orphans` ships literal markdown, which INV-F9-8 forbids.** It contains
`노드를 **삭제**하고` and `**전부 롤백**됩니다`. INV-F9-8 (`contracts/config_resolve_report/vectors.json`)
exists because a first implementation shipped raw asterisks in text the client renders verbatim,
and there is no second chance downstream. The asterisks are on screen right now. The invariant is
declared for one route family but the reason is general.

**6.3 `deletes` and `commit_granularity` are English inside a Korean dialog.** They are
server-owned strings and the contract says render verbatim, so I did — the graph sweep's
confirmation reads `ONE commit after the whole delete loop - an interrupted run rolls back
entirely, …` between two Korean lines. The count `detail` for the same operation says it in
Korean; the inventory does not. If those two fields are meant for operators they should be
Korean like every other operator-facing string in `retroactive.py`; if they are developer notes,
the surface needs a Korean equivalent to carry into the confirmation. **This is a server decision
and I did not want to make it by paraphrasing.**

**6.4 The server caps `samples` at 5 for a consumer that does not exist.** `_count_chain_replay`
ships `samples[:5]` and `withdrawal_candidate_samples[:5]`; `_count_enrichment_backfill` ships
`sample_new_keys[:5]`. I render none of them — "the count and a button" is the whole surface, and a
sample table is a second screen inside a row. Worth deciding deliberately rather than leaving the
truncation as dead weight.

## 7. Two things I did not do

**7.1 I left two rows in the isolated outbox and want your word before removing them.**
`assy_qa.database_outbox` ids **224310** and **224311** (see §5.4) are unconsumed
`RETROACTIVE_RUN` control events I created. Nothing consumes them today — `devenv up` deliberately
starts no scheduler — but if someone starts the isolated scheduler, **224310 executes a real graph
orphan sweep against `assy_qa`**. Harmless to a QA snapshot, but it is a live trigger sitting in a
queue and it is mine. Say the word and I delete exactly those two ids.

**7.2 I edited no documentation.** `DOC_OWNERSHIP.md` row 51 already names the list for the day
this lands, and it is now due — I am reproducing it rather than acting on it since doc-keeper owns
that tree:

- Row 51's own `⚠️ 화면(버튼)은 77d27d3 기준 아직 없다 … 화면 작업은 진행 중` — **now false.**
- `BACKFILL_GUIDE §7 서두 · §7.4 · §0` (point of entry is no longer `curl`)
- `FEATURE_CHECKLIST §1.8 행 · §2.8-quinquies 서두`
- `docs/README`의 BACKFILL 행
- Row 66 → `architecture/frontend.md §5` (the admin section; the row count moves and the fourth
  Overview instrument is undescribed)
- Row 63 → the config-resolve row should note that `config_resolve_view.js` now exports its
  taggers and has a **second** consumer, so "the view model is DOM-free so it can be scored" is
  now a shared property rather than a one-off.

## 8. Suggested lesson for `agent_workspace/memory/client-pm.md`

> - **함정**: 서버가 「이 수는 근사다」를 **여러 필드에 나눠** 말할 때(`count_kind` · 라벨 안의
>   「(최대)」 · `detail` 문장), 클라가 숫자만 크게 그리면 한정어가 화면에서 떨어져 나간다. 그 순간
>   화면은 서버가 하지 않은 주장을 한다.
>   **올바른 방법**: **숫자는 서버가 붙인 라벨과 한 쌍으로만 그린다** — 라벨이 없으면 숫자도 그리지
>   않는다(문장 안에 여전히 있다). 불리언(`truncated`·`restartable`)은 **색까지만**이고 문장으로
>   번역하지 않는다. 서버가 말하지 않은 것은 화면이 색으로만 말하고, 그 공백은 **보고서에 적어
>   서버 쪽으로 올린다.**

## 9. Gate summary

| gate | result |
|---|---|
| `node client2/tests/retroactive_view_harness.mjs` | 177 pass / 0 fail · 7/7 defects caught · 2/2 controls escaped |
| `contracts/config_resolve_report/client_harness.mjs` | OK, 159 strings scored, 0 divergence |
| `npm run check:contracts` | 6 contracts, no divergence |
| `node --check` × 3 | clean |
| forbidden client literals in touched files | none |
| browser E2E | :8080 reads + fail-closed write · :8081 404 · fake gate 401 ×2 · :8099 queued write ×2 |

⚠️ `client2/scripts/check_harnesses.mjs` reports **`geometry_origin_reseat_harness.mjs` went from
green to red**. **Not mine.** That harness reads exactly one file, `client2/src/map_editor.js`,
which another agent has open in this shared tree right now (`git diff --stat`: 265 insertions, 47
deletions) and which I never touched. Flagging it because the runner treats a green→red transition
as a build failure and whoever builds next will meet it.

`client2/dist` **not rebuilt**, nothing committed, nothing staged.

---

# Round 2 — QA fixes (GO-WITH-FIXES → addressed)

QA's root diagnosis was right and I fixed the root rather than the two symptoms. F1 and F2 were
one defect wearing two faces: **derived state kept somewhere other than a single per-operation
record** — the count keyed by operation while the parameters it was measured for lived in a
different map, and the write button's in-flight state living only in the DOM node a re-render
replaced. Both are cured by the same change.

## R2.1 The root fix

`client2/src/admin.js` now holds **one record per operation**, and every rendered row is a pure
function of it:

```
{ params, count: {ok, view, failure, paramsKey}, run, runFailure, busy, cliOpen }
```

`retroCountByOp` and `retroParamsByOp` are gone (grep: 0 hits). Three judgements moved into
`retroactive_view.js` where node can score them — `paramsKey`, `resolveCount`, `buildActionsView`
— and `admin.js` only moves their results into the DOM.

- **F1.** A measurement now carries the `paramsKey` it was measured with. `buildConfirmLines`
  takes the **record**, not a bare view, and resolves the count itself: there is no argument shape
  that smuggles a mismatched measurement into the dialog. A stale count is not deleted from the
  row — it is marked (dashed, muted, 「입력이 바뀌었습니다 — 이 측정은 지금 보낼 요청의 것이
  아닙니다」), because "I measured `inv` and now I am asking about `lot_alias`" is context worth
  keeping. A stale refusal also stops barring the button, which was the same root.
- **F2.** `buildActionsView(operation, record)` derives both buttons from `busy`. Any rebuild
  reconstructs the disabled state because there is nothing else to reconstruct it from. The two
  async handlers no longer hold `btn`/`host` across an `await` at all — they mutate the record and
  call `renderRetroOperation(op)`, which also removes the detached-node half of F5.
- **Beyond QA's ask:** `state.busy` is now set **before** `confirm()`, not after. QA §4.1 was right
  that "the tab-modal dialog is the guard" is browser behaviour the source does not prove. Setting
  it first removes the dependency; declining restores it.

## R2.2 The MEDIUMs and LOWs

| id | fix |
|---|---|
| F3 | `KIND_TONE.exact` → `'ok'`, so `''` means *unrecognised* and only that. Harness asserts `tone(exact) !== tone(unknown)`. |
| F4 | The confirmation now carries `count_kind`, `truncated`, `why_upper_bound` and the labelled extras. `truncated` travels as a **slot name + the payload value in JSON** (`buildSetting`'s F9 shape) — the client still composes no sentence, but a border colour cannot reach a plain-text dialog. The row shows it in words too, so colour is no longer the only carrier. |
| F5 | The run acknowledgement lives in the record and survives re-render; `buildRunView` now carries the server's `params` echo (list values element-by-element, since a joined string is not payload text). |
| F6 | Content-unchanged guard, reusing F9's shape at `admin.js:1648` (`raw === retroactiveRaw`). `cliOpen` is in the record, so an opened `버튼이 덮지 않는 것` survives a card rebuild too. |
| F7 | The number 13.1px → **23.2px**, the exactness chip 11.8px → **14.4px**. Nothing was shrunk: prose stays 14.08px, plain chips stay 11.84px. New `.retro-count-*` classes — the number no longer borrows `.cfg-jsonval`, a class meant for echoing JSON config values. |
| F8 | `.retro-input` 0.86 → 0.9rem, so the comment claiming body size is true. |
| F9 | `buildExtras` no longer sorts: `JSON.parse` preserves document order, so the sequence is the server's decision like the selection already was. Each pair gets its own bordered box — no more `12 사람이 고정한 셀` running together. |
| F10 | Fixed at the root: `paramEntries` derives from what the **inventory declares**, so a renamed parameter cannot be sent at all. |
| F11 | `.cfg-dryrun-refused` no longer reused; extras and the params echo use `.retro-extras`/`.retro-extra`. |

**Deferred: nothing from QA's client-side list.** The three server findings (§6.1–6.3) stay
untouched per instruction.

## R2.3 Harness — red first, then green

Per the constraint, the F1/F2 assertions were written and **proven red against the defective
code** before any fix. Both defects reproduced:

```
base suite: 192 passed, 11 failed      <- before the fix
  🔴 F1: the confirmation must NOT show a number measured for a different parameter
  🔴 F1: the confirmation must NOT show a server sentence measured for a different parameter
  🔴 F2: a run in flight disables the write button — any rebuild reconstructs that
  🔴 F2: measuring holds the write button — the count returning is what used to re-arm it
  ...
base suite: 263 passed, 0 failed       <- after
```

Final: **263 passed, 0 failed; 18/18 defect mutants caught, 0 escaped; 2/2 control mutants
escaped.** Eleven new mutants pin this round's findings (F1 ×3, F2 ×2, F3, F4 ×3, F5, F10) and
each is caught by its own targeted assertion, not by collateral damage.

The harness also caught something on the way: adding `truncated` introduced the `val()` provenance
tag, which the scorer did not know — it failed with *unknown provenance tag 'value'* rather than
passing over an unscored string.

## R2.4 Exercised

- **Fake backend on :8097** (scratchpad, `RUN_DELAY_MS=2500`) proxied through a scratch vite dev
  server on **:5195**. Chosen over an isolated API precisely so the write path could be driven
  **without adding a single outbox row anywhere**, and because a dial-able POST latency is the
  entire content of F2's race.
- **:8080** through a scratch vite on **:5194** for real reads (`graph_orphans` → 12786
  `upper_bound`) and the real confirmation.
- Ids **224310 / 224311** in `assy_qa` untouched, per the user ruling.

**F1, measured:** measure `rule=inv` → 594 box; retype `lot_alias` → box goes `data-tone="stale"`
with the marker, **and the caret stays in the input**; press 실행 → the dialog reads
`rule = lot_alias` and contains neither `594` nor the `inv` sentence.

**F2, measured with real timestamps:**

| t | action | count button | run button |
|---|---|---|---|
| 1ms | 실행 pressed | 건수 확인 / off | 요청 중… / off |
| 707ms | 건수 확인 pressed mid-flight | 건수 확인 / off | 요청 중… / off |
| 1416ms | 실행 pressed again mid-flight | 건수 확인 / off | 요청 중… / off |
| 3017ms | POST landed | 건수 확인 / ON | 실행 / ON |

`confirms: 1`, POSTs leaving the browser: `1`, server log: `RUN #3` and nothing else.

**Re-entrancy, measured:** a second click fired from *inside* the confirm stub (the key-repeat
shape QA said source could not settle) → 1 dialog, 1 POST. Declining → `busy` released, row
usable, 0 POSTs.

**F5/F6 across a re-render:** queued box (`fake00000003`), run id, opened cli details, typed input
and the stale marker all survive a forced refresh.

**F7 computed (16px root):** number 23.2 · label 15.68 · exactness chip 14.4 · input 14.4 ·
prose 14.08 · plain chip 11.84.

## R2.5 Notes for the coordinator

- **`geometry_origin_reseat_harness.mjs` is green again** — confirming that red was the other
  lane's `map_editor.js`, as I reported. `check_harnesses`: 20 harnesses, 15 gated, all green.
- **Doc list gap acknowledged.** QA is right about `DOC_OWNERSHIP` row 42 — `frontend.md §3`
  needs a row for `retroactive_view.js` and two line-count corrections. My round-1 list missed it.
- ⚠️ **Untracked `client2/dist/assets/{admin,main,map_editor}-*.js` are in the tree and are not
  mine** — I did not run a build in either round. Likely residue from the build you reverted.
