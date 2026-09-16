# Admin screen — adversarial UX/UI audit (2026-09-16)

**Scope.** `client2/admin.html` (lines 15–1939 = one inline `<style>`; 1941–2578 = markup),
`client2/src/admin.js` (4,996 lines), `client2/src/admin_rows.js`, and the panels the page mounts
(`runtime_panel.js`, `chain_queue_panel.js`, `chain_graph.js`, `chain_rule_panel.js`,
`config_resolve_view.js`, `raw_registry_panel.js`, `retroactive_view.js`, `pickup_state.js`).
Shipped bytes checked in `client2/dist/admin.html` and `client2/dist/assets/admin-Dc96VsZw.js`
(built 2026-09-16 11:03, newer than source — what I audited is what ships).

**Method.** Design system loaded first (`.claude/skills/ui-design-system/SKILL.md`); values measured
from the canon `client2/src/ontology_explorer.css` and `client2/src/tokens.css`, not quoted from the
skill page. Owner rules read in `CLAUDE.md`. Every count below was measured. Where two independent
sweeps produced different totals I re-measured once and published the re-measurement.

**No code changed. No file touched except this report.**

---

## Ranked findings

### H-1 — the always-on status summary is not on screen, and the code that fills it is dead
**HIGH — the operator has nowhere to look; this is the headline answer to "why isn't it running"**

- `client2/src/admin.js:577` — `healthStripEl.style.display = 'none';` is the last line of
  `updatePanelLayout()`, **outside the if/else**. It runs unconditionally, and `updatePanelLayout()`
  runs inside `switchTab()`, which `applyRoute(true)` calls on every load. It is the **only**
  assignment to that element's display in the file.
- `client2/src/admin.js:4842` — `refreshHealthStrip()` is defined and **called from nowhere**.
  Exhaustive grep over `client2/src/*.js`, `client2/*.html`, `client2/tests/*.mjs`: the only other
  occurrence of the identifier is the comment at `admin.js:576`.
- Shipped-bundle confirmation: `dist/assets/admin-Dc96VsZw.js` still carries `health-strip` (1×) and
  `health-card-` (6×, i.e. the four click listeners), but Rollup dropped the strings
  `체인 파이프라인 정상` and `실패 0건` — 0 occurrences. The bundler eliminated the refresh path as
  unreachable. The markup and four click handlers ship; content never arrives.

**Rule broken.** `CLAUDE.md` 구성 기준 ③: 「분기 «중첩»이 없다 판별식: 「이 갈래를 «누가» 타나」
-> 아무도 안 타면 «잔해»다」. And ①: 「이 줄이 «참»인가 — 참이 아니면 불친절이 아니라 «거짓»이다」.

**What the operator experiences.** 43 lines of markup for a four-card pipeline summary sit at the top
of `admin.html:1959-1982` and never paint. The only organ that renders process liveness —
`RuntimePanel`'s 「살았나」 column, `runtime_panel.js:38-47` — is mounted at `#runtime-mount`, inside
`#overview-wrapper` (`admin.html:2010`). **Overview tab only.** An operator who clicks "Chain"
because chain is not running walks away from the one place that says whether the loop is alive.
There is no persistent, tab-independent surface that answers "is it running".

That is the brief's question: the screen the owner opened six times has no always-visible status
organ, so every question becomes a tab hunt or a source read.

---

### H-2 — the Chain health card asserts 「정상」 from a number that is 0 when nothing runs
**HIGH — wrong answer (latent: see H-1)**

`client2/src/admin.js:4965-4979`, the whole of `refreshChainHealth()`:

```js
const res = await adminFetch(`${API_BASE}/admin/outbox/failed?page=1&limit=1`);
const total = r.total || 0;
if (total > 0) { setHealthCard('chain', 'danger', `실패 트랜잭션 ${total}건`, …); }
else          { setHealthCard('chain', 'ok',     '실패 0건', '체인 파이프라인 정상'); }
```

One input: the count of failed outbox transactions. Chain worker dead → 0 failures → `ok` +
「체인 파이프라인 정상」. Every rule `enabled: false` → 0 → 「정상」. Queue 4,000 deep and nothing
picking up → 0 → 「정상」. "Stopped" and "idle" are byte-identical, and "stopped" is labelled healthy.

**The same file already rules against this, 1,160 lines earlier.** `client2/src/admin.js:3806-3807`,
on the Overview Chain card:

> 🔴 「0 이니 정상」이라고 «주장하지» 않습니다. 규칙이 거절되거나 꺼져 있어 체인이 «아예 안 돌아도»
> 실패는 0 입니다 — 그 0 으로 건강을 말하면 거짓입니다.

The page therefore holds two renderings of one question, one written specifically not to make the
claim the other makes. `CLAUDE.md` ④: 「같은 기능인데 두 경로가 있어서도 안 됨 · 판별식: 「둘이
«갈라질 수» 있나」」 — they have already diverged.

**Severity, stated honestly.** Because of H-1 this card does not reach a human today. I record it as
HIGH on the *code*, not on today's pixels: re-enabling the strip is one line, and the moment anyone
does, a green 「정상」 appears over a dead worker. Calling it low because it is hidden would be
「실패하는 것이 무해한 것은 아니다」.

---

### H-3 — the refresh clock lies in both directions, and the auto-refresh path is silent
**HIGH — stale numbers read as current**

`client2/src/admin.js:1055-1061`:

```js
if (!allRead && !silent) {
  const why = bodyFailures.length ? ` — ${bodyFailures.join(' · ')}` : '';
  showToast(`${TAB_ERROR_MSG[tab] || '❌ 목록 로드 실패'}${why}`, 'error');
}
markRefreshed();          // ← runs whether or not allRead is true
return allRead;
```

`markRefreshed()` (`admin.js:451-456`) writes `갱신 HH:MM:SS` into `#last-refreshed`. Two failures:

1. **Partial failure still stamps a fresh time.** Sections that came back `—` (via
   `markSectionUnread`, `admin.js:471`) sit under a timestamp saying the screen is current.
2. **Total failure freezes the clock with no visual change.** `markRefreshed()` is *not* called from
   the `catch` at `admin.js:1062-1066`, nor from `refreshRunning`, `refreshChainRule`,
   `refreshTableConfig`, `refreshConfigResolve`, `refreshRetroactiveOperations`, or the 5 s poll.
   The last successful time simply stays.

And the 30 s auto-refresh calls `fetchData({ silent: true })` (`admin.js:408-414`), so on that path
the toast above **never fires**. The screen refreshes itself, part of it fails, nothing is said, and
the clock advances.

The file's own comment at `admin.js:1043-1046` diagnoses this exact class for a different cause (the
missing `else`) and closes that one: 「markRefreshed() 가 «새 시각»을 찍고 … 즉 «무음»이 아니라
«거짓»이었고, 운영자는 낡은 수를 «새 수»로 읽었습니다」. The partial- and total-failure legs are open.

---

### H-4 — "show me the failures" silently shows everything
**HIGH — the operator concludes there is no problem**

`client2/src/admin.js:604-607`:

```js
statusFilterSelect.value = opts.statusFilter;
if (statusFilterSelect.value !== opts.statusFilter) {
  console.warn('[admin] status filter has no option for', opts.statusFilter,
    '- the vocabulary has not arrived yet; showing all statuses instead.');
}
```

A `<select>` refuses a value it has no `<option>` for, silently, leaving `ALL` standing. The options
come from the server's `status_vocabulary`; before it arrives, or if it changes, the deep-link
「→ File 탭 실패 필터」 lands on the unfiltered list. The operator sees a full log page and reads it as
"these are the failures" — or, seeing nothing red near the top, as "no problem".

The only notice is `console.warn`. **This operator cannot read logs — that is the premise of the
screen.** A console warning is no warning. The comment above the branch says exactly this ("saying so
out loud is the difference between a late vocabulary and a screen that quietly answers a different
question") and then says it to the console.

---

### H-5 — Auto Update cannot say whether the scheduler is alive, or why a collector failed
**HIGH — blocked; only the source answers this**

Table at `client2/admin.html:2338-2349`: `Cron Schedule · Next Run · Last Run · Status · Active`.
Row builder `client2/src/admin_rows.js:123-150`.

- **Scheduler liveness: not present in source.** No `scheduler` / `paused` / `스케줄러` token is read
  or rendered anywhere in `admin.js` or `admin.html`. A stopped APScheduler renders the identical
  table to a running one, with a `Next Run` in the past — and `formatTimestamp` (`admin.js:437`) does
  not mark a past timestamp as past.
- **Collector last error: not present in source.** No `last_error` field is read on this tab. The
  `Status` badge is `SUCCESS` / `FAIL` / `RUNNING` / `PENDING`, nothing more. The only error surface
  is the separate 「산출물 인제션 실패」 section — `auto-update tables ∩ recent file-ingestion
  failures`, a *downstream* symptom, not the collector's own exception.

Every "why didn't it run" here requires a log or a source read.

---

### H-6 — three CSS variables are referenced and never defined; two of them break meaning
**HIGH — "not measured" renders identically to "measured"; graph nodes render black**

`--text-primary`, `--text-secondary` and `--bg` do not exist in `tokens.css`,
`ontology_explorer.css`, `ledger_console.css`, or anywhere under `client2/`. Verified:
`grep -rnE '^\s*--(text-primary|text-secondary|bg)\s*:' client2/src client2/*.html` → 0 hits.
None has a fallback, so each declaration is invalid-at-computed-value-time and resolves to `unset`,
which on these inherited properties means `inherit` — **in both themes**, which is worse than being
wrong in one.

**(a) The Overview instruments — `admin.html:1151-1171`:**

```css
.recorrection-line            { color: var(--text-secondary); }
.recorrection-line .rc-label  { color: var(--text-primary); }
.recorrection-line .rc-value  { color: var(--text-primary); }
.recorrection-line[data-tone="muted"] .rc-value { color: var(--text-secondary); }
```

`admin.js` assigns `dataset.tone = 'muted'` **12 times**; three land on this component —
`admin.js:1992` (「보고 없음」), `:1999`, and `:2023` (`cells < 100`, where the value is a *real*
percentage that is supposed to be de-emphasised and renders at full strength). `warn` and `danger`
work, because `--warning` / `--danger` exist. **So the one tone that means "do not read this as a
fact" is the one that does nothing.** And `.rc-sub` declares only `font-size` and inherits the broken
line colour, so the number and its denominator/caveat carry the same ink.

`renderEffort` (`admin.js:2043-2078`) exists precisely so that 「표본이 없다」 and 「계기가 죽었다」 do
not look alike. The CSS erases the distinction the JS is careful to make — the memory entry
「같아 보이는 다섯 개의 0」 in literal form, on the owner's #1 instrument.

**(b) The chain graph — `admin.html:263`:**

```css
.cg-node circle { fill: var(--bg); stroke: var(--text); stroke-width: 1.5; cursor: pointer; }
```

`fill` is inherited; no ancestor sets one (`chain_graph.js:353` appends the circle into a bare
`<g class="cg-node">`), so it falls to the initial value — **black**. Meanwhile
`admin.html:273` `.cg-node.is-ledger circle { fill: var(--text-dim); }` works. The graph's one
node-type distinction is "surface-filled vs dim-filled"; it is actually "black vs dim". In light
theme `--text-dim: #5b6779` against black is nearly the same disc, so **the distinction collapses**.
The label is drawn beside the circle (`chain_graph.js:354`, `x + LABEL_DX`), so text stays readable —
only the node itself is wrong.

---

### H-7 — every non-SUCCESS file status is painted as a failure
**HIGH — wrong answer on the table the operator scans first**

`client2/src/admin_rows.js:32`:

```js
const statusBadge = `<span class="badge ${log.status === 'SUCCESS' ? 'badge-success' : 'badge-danger'}">${escapeHtml(log.status || 'FAILED')}</span>`;
```

A binary. `PENDING_RETRY` (someone still has to act), `PROCESSING` (running right now) and `FAILED`
(dead) all render red. `.badge-warning` (`admin.html:888`) and `.badge-muted` (`admin.html:900`)
exist and are unused here — the sibling collector row uses all four correctly
(`admin_rows.js:124-128`). The vocabulary is present; one row ignores it.

The irony is in the markup: `admin.html:2093-2101` explains at length that the status filter was
widened *because* `PENDING_RETRY` — 「someone else still has to act」 — was the one state an operator
needed and could not filter to. They can filter to it now. It is still red. At a glance, a backlog of
in-flight retries reads as an outage.

---

### H-8 — a failed progress poll leaves the bars frozen, which reads as "this job is stuck"
**HIGH — wrong answer**

`client2/src/admin.js:1585` — the 5 s active-ingestion poll:

```js
} catch (e) { /* 보조 정보 — 무음 */ }
```

The bars keep their last painted value. `.running-bar.is-unknown .running-bar__fill` has an
indeterminate animation for "we don't know the total" (`admin.html:1891`), but there is no state for
"we don't know *anything* right now". A frozen 62% bar and a genuinely stalled ingestion are the same
picture, and the operator's next move (kill it? wait? restart?) differs completely between them.

The comment two lines above the catch (`admin.js:1586-1591`) already states that a frozen bar reads
as 「this job has not moved」. The catch stays silent anyway.

---

### M-1 — the only confirmation channel for ~35 operations has no `aria-live`, and it disappears
**MEDIUM**

`admin.html:2573` — `<div class="toast-container" id="toast-container"></div>`. **`aria-live` appears
0 times** in `admin.html`, `admin.js`, `admin_rows.js` and `utils.js` (verified). Toasts are the only
feedback for `Retry All Failed`, `Reload Configs & Code`, `Save Code`, `Run Now`, collector toggles
and every transport error listed in M-5. A screen-reader user gets no confirmation that a destructive
bulk retry succeeded or failed; every user loses the message after a few seconds, with nothing left
on screen to read back or quote to someone.

---

### M-2 — bulk retry asks for consent without the number
**MEDIUM — the operator must go count, or guesses**

`client2/src/admin.js:752` and `:759`:

```js
if (confirm('실패 상태인 모든 체인(아웃박스) 트랜잭션을 재실행하시겠습니까?'))
if (confirm('실패 상태인 모든 파일 인제션 건을 재실행하시겠습니까?'))
```

The count is the decision — re-running 3 and re-running 3,000 are different acts against a production
pipeline — and it is on screen in the section badge but not in the dialog asking for consent. Nine
`confirm()` sites total (`admin.js:752, 759, 833, 842, 1448, 1539, 1843, 3911, 4610`); the two bulk
ones are where the missing number matters. Separately: a native `confirm()` is OS chrome — no token,
no theme, no font. It is the only surface on the page outside the design system entirely.

---

### M-3 — thirteen collapsible sections cannot be operated by keyboard, and the page has two collapse mechanisms
**MEDIUM — accessibility + 「같은 기능에 두 경로」**

`client2/src/admin.js:688-694`:

```js
document.querySelectorAll('.section-header').forEach(h => {
  h.addEventListener('click', (e) => {
    if (e.target.closest('.section-actions')) return;
    const sec = h.closest('.stage-section');
    if (sec) sec.classList.toggle('collapsed');
  });
});
```

`.section-header` is a `<div>` (`admin.html:1039`). Measured across the whole surface: `role=` **0**,
`tabindex` **0**, `aria-expanded` **0**. No keyboard handler. All 13 sections are un-collapsible
without a mouse, and the `▾` chevron has no `aria-hidden`, so it is announced as literal text.

Meanwhile `admin.html:2037`, `:2075`, `:2089` (`#config-resolve`, `#retroactive`, `#running`) use
native `<details>/<summary>` — which is keyboard-operable and announces its state for free. **Two
collapse mechanisms on one screen, one accessible and one not**, and an operator learns two
interaction grammars for one idea.

---

### M-4 — controls below the 24 px target, including the most destructive one on the screen
**MEDIUM**

| control | file:line | computed | note |
|---|---|---|---|
| `.running-x` — stop a running job | `admin.html:1898-1908` `width: 18px; height: 18px; padding: 0` | **18 × 18** | the single most destructive control on Overview |
| `.au-switch` — enable/disable a scheduled collector | `admin.html:925-931` `width: 38px; height: 21px` | **21** | |
| `#copy-payload-btn` | `admin.html:2536` inline `padding: 2px 6px; font-size: 0.7rem` | ≈ **19.4** | |
| `.cfg-btn` — the Retroactive action buttons | `admin.html:1350` `padding: 3px 12px; font-size: 0.76rem` | ≈ **22.6** | |
| row `Retry` buttons | `admin_rows.js:34, 35, 112, 146` inline `padding: 4px 10px; font-size: 0.75rem` | ≈ **24.4** | the most-clicked control in the app, sitting on the line |

WCAG 2.5.8 (AA) asks for 24 × 24 CSS px. Four of these were pushed under or onto the line by
**inline** `font-size` overrides, so they cannot be corrected from a stylesheet (see M-7).

---

### M-5 — information that exists only inside a `title=` tooltip
**MEDIUM — invisible to keyboard and touch**

24 `title=` attributes (admin.html 16, admin.js 3, admin_rows.js 5). These carry facts available
nowhere else:

- `admin.js:1423` — `<span class="tx-id-chip" title="${tx.transaction_id}&#10;(클릭하여 전체 ID 복사)">${shortTxId(...)}</span>`.
  Two failures in one element: the **full transaction ID** exists only in the tooltip (the cell is
  truncated), and "click to copy" exists only there. It is a `<span>` with `cursor: copy`
  (`admin.html:778-781`) and a click handler (`admin.js:1438`) — no `<button>`, no `tabindex`, no
  `role`. **Keyboard-unreachable.**
- `admin.html:2189-2194` — six sortable `<th title="클릭: 현재 페이지 내 정렬">`. The handler is bound
  to the bare `<th>` (`admin.js:720`, `:1550`). No `<button>`, no `tabindex`, `aria-sort` **0**.
  Sorting is keyboard-inaccessible, and the correctness caveat — **sorting applies to the current
  page only** — is invisible.
- `admin.html:2347` — `title="스케줄 활성/비활성 (비활성이어도 Run Now 수동 실행은 가능)"`. The one
  fact needed before disabling a collector lives only here.
- `admin.html:2027` — the entire scoring rubric for 교정 공수 (`키 1 · 클릭 3 · 화면이동 5`). The
  visible row shows `12.4점`; the number is meaningless without the tooltip.
- `admin.js:479-484` (`markSectionAbsent`) — the config path that would fix the absence, set as
  `el.title = path`. The comment says 「경로를 `title` 로 달아 운영자가 고칠 자리를 찾게 합니다」;
  nothing on screen suggests a badge reading 「없음」 is hoverable.
- `admin_rows.js:46, 135, 136` — the **full timestamps** for `Processed At` / `Next Run` / `Last Run`;
  the cells show an abbreviated form. A keyboard user can never read the exact time of a failure.
- `admin.html:2485`, `:2549` — `<select>` elements whose only accessible name is a `title`; no
  `<label>`, no `aria-label`.

Only two elements in 7,724 lines are correctly labelled: `admin.html:1953` (theme toggle, with
`aria-hidden` on both icons) and `admin_rows.js:140`.

---

### M-6 — the good failure sentences exist and the status surfaces do not use them
**MEDIUM — 「같은 기능에 두 경로」**

`client2/src/config_resolve_view.js:36-50` declares the five sentences that actually tell an operator
which hand fixes the problem:

```js
FETCH_FAILED:       '조회 실패',
FETCH_OLD_SERVER:   '구버전 서버 · 재시작 필요',
FETCH_UNREACHABLE:  '서버 연결 불가 · 실행 중인지 확인',
FETCH_UNAUTHORIZED: '토큰 거부 · 새로고침 후 재입력',
FETCH_INTERCEPTED:  '관리자 게이트 아님 · 앞단 프록시 확인',
```

Used by config-resolve, join-verify, plan-dry-run and retroactive. **No pipeline status surface uses
them.** File / Chain / Auto Update / Enrichment collapse every transport failure to the single word
「상태 조회 실패」 (`admin.js:4885, 4956, 4977, 4994`), which names no next action. A solved and an
unsolved version of one problem sit on one page, and which you get depends on which block you look at.

Same class, three neighbours, two behaviours: `admin.js:2319` `refreshGapCatalogue` catches and
**discards** the exception text (prints 「격차 · 모름」 with an empty reason) while
`refreshJoinVerification` (`:2189`) and `refreshPlanDryRun` (`:2272`) both pass `String(e.message)`
through.

---

### M-7 — 18 failures reach the console and nothing else
**MEDIUM — the operator cannot read the console any more than the logs**

Catches writing nothing to the DOM: `admin.js:103, 110, 151, 209, 511, 1102, 1125, 1309, 1585, 2319,
3255, 3409, 3609, 4016, 4561, 4807, 4867, 4879`. The consequential ones:

| line | swallowed | what the operator sees |
|---|---|---|
| `1102` | `loadChainMappers` → `null` | mapper dropdown in the rule editor is empty, no reason |
| `1125` | `loadTableNames` → `null` | table dropdown empty, no reason |
| `4561` | editor file list | picker shows only 「스크립트 선택…」, no reason |
| `209` | non-JSON 503 body | the server's "restart with a token" sentence is lost |

Plus eight sites where the exception is dropped and a fixed toast fires instead — `admin.js:3991,
4035, 4399, 4430, 4459, 4486, 4672` — e.g. 「❌ 강제 수집 구동 요청 실패」 with no status code, no URL,
no reason. `CLAUDE.md` keeps 「거절의 «사유»와 «다음 행동»」 on the *keep* list of the 설명 문구 rule.
These drop both.

---

### M-8 — 「이 프로세스에 루프 없음」 reads as a refusal about the API, not "the worker is down"
**MEDIUM — the operator must ask someone what the sentence means**

`client2/src/chain_queue_panel.js:229-233`:

```js
const sees = payload.loop_in_this_process;
const runningCell = countWithAbsence(
  sees === false ? { unread: '이 프로세스에 루프 없음' }
    : sees === true ? { value: running, absence: 'truly_none' }
      : { unread: '모름' });
```

It sits in the `unread` (= could not read) slot and is phrased as a statement about *this process* —
plumbing the operator was never told about. The fact they need ("the thing that does chain work is
not running") is derivable from it plus 「집은 적 없음」 (`pickup_state.js:47`) plus queue depth, but
**nothing composes those three into one statement**. `pickup_state.js:10-12` deliberately refuses to
say 「멈춤」 because no threshold is declared — correct discipline; the gap it leaves is a screen gap,
not a data gap. Compare `CLAUDE.md` memory, owner 09-15: 「「HOL 가드」 같은 용어 금지 — 하는 일로
부른다」. 「루프」・「집기」・「프로세스」 are our words.

---

### M-9 — two button systems in one header row, and 156 inline styles bypassing the token class
**MEDIUM — 「묘하게 다르다」**

| | `.tab-btn` (`admin.html:1802`) | `.admin-btn` (`admin.html:119`) |
|---|---|---|
| font | `var(--font-sans)` — Outfit | `var(--oe-font-head)` — Barlow Condensed |
| radius | `8px` | `0` |
| padding | `8px 16px` | `6.8px 12.24px` |

They share one flex row — `admin.html:1987-1999`, where the seven tab buttons and `🔄 Refresh` sit
side by side. Different family, different corner, different rhythm. Canon: 「Corner radius 0.
Everywhere.」

Inline-style inventory (measured): **admin.html 93** (all in markup; 63 hand-type px) · **admin.js
22** · **admin_rows.js 41** → **156**.

`.admin-btn--sm` exists at `admin.html:101-104`, correctly written in tokens
(`var(--space-1) var(--space-3)` / `var(--fs-label)`), and is used **4 times**. Sixteen inline
overrides hand-type six different small-button paddings instead: `4px 10px` (×6), `2px 8px` (×4),
`5px 12px` (×2), `4px 12px` (×2), `6px 12px`, `2px 6px`. `admin.js:4135` and `:4331` are the *same
button* at a different size from `admin.js:3949` and `:4224`.

Two whole components are declared inline and are unreachable from any stylesheet:
`admin.html:2118` (the active-ingestion warning banner — nine properties, four off-grid px, an 8px
radius, a 13.12px font) and `admin.html:2483` (the pagination footer chrome). And `admin.html:2539` —
`<pre id="payload-viewer" style="color: var(--success);">` — paints a raw JSON payload in the
*success* semantic: colour used as decoration, not meaning.

Owner rule 마진: 「손으로 px 를 적지 않는다」. Memory: 「인라인 스타일이 스타일시트를 이긴다」 — a
token change cannot reach any of these 156.

---

### M-10 — 116 font-size declarations, 12 tokenised, 25 distinct literals against a five-step scale
**MEDIUM — 「적힌 위계가 안 보이는」**

Measured across `admin.html` + `admin.js` + `admin_rows.js`: **116** `font-size:` declarations,
**12** using a token (10%), **25** distinct literal values. `--fs-title`, `--fs-body` and `--fs-meta`
are never used. `admin.js` and `admin_rows.js` use zero tokens; `admin_rows.js` carries 17 font-size
literals in 150 lines.

Most of the vocabulary is crammed into one band. Indistinguishable neighbours, cited:

- `0.73rem` (11.68px) `admin.html:763` vs `0.74rem` (11.84px) `:1220` — **0.16 px apart**, and
  `.health-card-sub` / `.cfg-chip` sit in the same Overview column.
- `0.76rem` (12.16) `:1305` vs `0.77rem` (12.32) `:910` vs `0.78rem` (12.48) `:1172` — three steps
  inside 0.32 px.
- `0.84rem` (13.44) `:1156` vs `0.85rem` (13.60) `:423` vs `0.86rem` (13.76) `:1299` — three more.
- 12 px spelled three ways — `.75rem` `:159`, `12px` `:282`, `0.75rem` `admin.js:3949` — while
  `--fs-label: 12px` sits unused.

`tokens.css:172-177` predicted this shape while defining the scale:

> 실측 2026-09-13 `board.css`: font-size 선언 83개에 크기가 «열» 가지였고, 그중 여섯이 10~13.5px
> 사이에 있었습니다 — 위계가 없는 것이 아니라 «적힌 위계가 안 보이는» 것입니다.

Also `admin.html:1698-1710` deliberately collapses `.panel-title` from 18.4px to 13px to match
`.section-title`. The right panel's heading 「🔍 Error & Event Diagnostics」 now carries the same
weight as every collapsed section header in the left panel — the panel no longer reads as a level
above its sections. The comment flags it ("보고에 적어 올립니다"); recorded here as still open.

---

### M-11 — 80% of spacing numbers are off the 3.4 grid, and `--space-5`/`--space-6` are never used
**MEDIUM — the 마진 rule, measured**

`admin.html` `padding` / `margin` / `gap`: **230 px numbers**, **27 distinct values**.
On-grid: `3.4px` ×8, `6.8px` ×16, `10.2px` ×17, `13.6px` ×6 = **47 (20%)**.
Off-grid: **183 (80%)**, across **23 of the 27 distinct values** — most frequently `10px` (×29),
`8px` (×26), `6px` (×22), `12px` (×18), `16px` (×10). (Two independent sweeps produced these same
totals.)

`--space-5` (20.4) and `--space-6` (27.2) never appear anywhere; their off-grid stand-ins do —
`20px` ×8, `25px` ×2, `30px` ×3. And the on-grid values are written as **raw decimals**
(`padding: 6.8px 12.24px`, `gap: 6.8px`, `padding: 10.2px 13.6px`) rather than as tokens, so a change
to `--space-2` will move 27 declarations and leave 47 behind. `12.24px` (`admin.html:123`) is not a
grid value at all — 1.8 steps.

---

### M-12 — 23 of 33 border-radius declarations break "radius 0, everywhere"
**MEDIUM**

33 declarations, 10 distinct values. Only **10 are `0`**; **23 are non-zero (70%)** — `8px` ×6,
`6px` ×3, `14px` ×3, `10px` ×3, `50%` ×2, `4px` ×2, `999px`, `3px`, `12px`.

The page is visibly mid-migration: `.stage-chip` and `.section-count` are `0` (`admin.html:1073`,
`:1081`) while `.panel` keeps `14px` (`:787`), `.health-card` `12px` (`:220`), `.section-note` `10px`
(`:1131`), `.tab-btn` `8px` (`:1807`), `.logo-badge` `8px` (`:65`). Sharp chips inside rounded cards
inside a rounded panel. Three button-shaped things — `.admin-btn` 0, `.tab-btn` 8px, `.health-card`
12px — speak three corner languages on one screen.

---

### M-13 — a part reaches into another component's CSS namespace
**MEDIUM — 조립식**

`client2/src/chain_queue_panel.js:452, 637, 640` uses `.health-dot`, `.health-card-title` and
`.health-card-sub` — classes declared in `admin.html`'s `<style>` for the health strip
(`admin.html:733, 748, 762`). `chain_queue_panel.js:46` says so: 「The status tokens `admin.html`'s
`.health-dot` already understands.」

1. **A trap.** The obvious cleanup for H-1 — delete the dead strip's CSS — silently removes the queue
   panel's dot and two text styles. No error; the panel just goes plain.
2. **The panel cannot move.** It is mounted twice today (`admin.js:1380-1381`) and does that
   correctly — one div each, mount in the constructor, no module state, which satisfies
   「같은 화면에 둘을 놓아도 간섭 없음」. But it cannot go to another page, because its styling lives in
   this page's `<style>` under a dead component's name. 「부품마다 자기 div 하나」 is honoured; the
   namespace half is not.

Visually: `.health-card-title` is `text-transform: uppercase; letter-spacing: 0.6px; font-size:
0.72rem` — a style for a short English micro-label. `chain_queue_panel.js:637` puts a Korean sentence
in it: 「여기서 «재지 않는» 수 N개 — 없는 것이 아니라 안 잰 것입니다」. Uppercase does nothing to
Hangul, the 0.6 px tracking stretches it, and 11.5 px is below `--fs-label`.

---

### M-14 — Korean and English collide inside single components
**MEDIUM — 「match to the user's language」 fails per-component, not per-screen**

The document is `<html lang="ko">` (`admin.html:2`) but navigation, all table headers and 7 of 9
empty states are English. The collisions are *inside* components:

- **All 13 section headers** are a Korean chip glued to a title 8 of which are English, 6.8 px apart
  on one baseline: `진행 중 / Active Ingestions` (`:2111`), `현황 / Chain Rules` (`:2212`),
  `수정 / 규칙 등록` (`:2245`), `계측 / Chain 대기열 (읽기 전용)` (`:2256` — both languages inside one
  title), `오류·실행 / Chain 실패 (Outbox Transactions)` (`:2269` — again). In the Chain tab alone,
  one concept is spelled `Rule` in one header and `규칙` in the next.
- **The Enrichment Rules table switches language four times.** Headers `Rule Name`,
  `Source → Derived`, `Target Fields` (`:2429-2431`) and then **`<th>결손</th>`** (`:2432`) — one
  Korean column head in a row of three English ones. Empty state Korean (`:2439`), count chip Korean
  (`:2421`), note Korean quoting the English button name (`:2441`).
- **Empty states:** 7 English (`:2158, 2202, 2233, 2294, 2321, 2355, 2567`), 2 Korean (`:2384`,
  `:2439`), same CSS class. Two empty tables in a row give two languages.
- **The Overview headline stack** is half translated: `재교정률` `:2019`, `교정 공수` `:2028`,
  `설정 반영` `:2039`, then `Retroactive` `:2077`, `Running` `:2091` — five `.rc-label` spans in one
  vertical list.
- **Press English, get answered in Korean, every time.** All ~35 `showToast()` strings are Korean;
  every button that fires them is English (`🔄 Retry All Failed`, `💾 Save Code`, `📋 Copy`,
  `⚙️ Reload Configs & Code`).
- Three spellings of "nothing": `admin.js:478` `'없음'`, `admin.js:3712` `'표시할 최근 이벤트 없음'`,
  `admin.html:2494` `—`.

---

### L-1 — 설명 문구: prose where the screen should show
**LOW**

Discriminant applied — 「이 문장을 지우면 운영자가 «틀리게» 읽나」. (The ~40 long Korean passages at
`admin.html:2007-2102, 2170-2177, 2390-2401, 2450-2467` are HTML comments and do **not** render;
they are not counted.)

1. `admin.html:2442-2444` — the Enrichment `.section-note`, three rendered sentences, five inline
   tags, a file path, a button name and a routing explanation, permanently on screen. Sentence 1
   passes (it names the file and the button). Sentence 2 — 「규칙 CRUD UI는 파이프라인 온보딩
   위저드(대안 단계)로 이관되어 있습니다」 — is our design history, 「내 «설계 의도»의 해설」, on the
   delete list. 번역체: 「반영합니다」, 「이관되어 있습니다」.
   **And `admin.js:4311` renders the same paragraph a second time**, built inline — so one session
   can show it twice, in two wordings.
2. `admin.html:1947` — header subtitle
   `File Ingestion · Chain · Auto Update · Enrichment 생애 관리`. The tab bar twelve lines below lists
   exactly those four names. 「제목이 말한 것을 부제가 다시 말하기」 — delete. (It also hand-types
   `font-size: 0.75rem; margin-top: 2px` inline.)
3. `admin.html:2567` — `#diagnostics-empty`, the right panel's resting state: a 3rem (48 px) 🔍 over
   *"Select a failed transaction or file from the left list to view detailed error diagnostics."* —
   one English sentence in a Korean UI, in the global `.empty-state` (`:1779-1799`: `padding: 40px`,
   `gap: 15px`, `font-size: 1rem`). The canon's `.oe-empty` is one line, left-aligned, 13 px, no
   icon — and `admin.html:1116-1119` already overrides `.empty-state` to exactly that, **inside
   `.stage-section` only**. The page holds both answers and gives the right panel the wrong one.
   Nearby: `:2294` `No failed chain transactions. Chain pipeline is healthy!` — two sentences and an
   exclamation mark for an empty table.
4. 번역체 in the toasts and dialogs: `admin.js:4472`
   「🚀 시스템 설정 및 파이썬 코드가 성공적으로 핫-리로드되었습니다.」 · `:3985`
   「강제 수집 지시가 정상적으로 발행되었습니다」 · `:4395` 「실패 목록에서 해제되었습니다」 · `:162`
   「관리자 토큰 입력을 취소했습니다. 새로고침하면 다시 물어봅니다.」 — and 「~하시겠습니까?」 in seven
   of the nine `confirm()` strings. Owner rule: 「기호·짧은 English·명사형」.
5. Tooltips that explain a past refactor rather than the control: `admin.html:2549`
   `title="편집할 스크립트 선택 (구 Code Editor 트리 대체)"`.

---

### L-2 — tab bar has no tab semantics; `#running-hint` is a permanently empty span
**LOW**

- `admin.html:1989-1995`: seven `<button class="tab-btn">`. Measured across the surface: `role=` 0,
  `aria-selected` 0, `aria-controls` 0. The wrapper (`:1988`) is a bare `<div style="display: flex;
  gap: 10px; flex-wrap: wrap;">`; the panels have no `role="tabpanel"`. A screen reader announces
  seven unrelated buttons with no indication which panel is showing.
- Selected state is `admin.html:1819-1823` — `background` + `border-color` + `color`, three colour
  properties and nothing else. No weight change, no underline, no marker, no `aria-selected`.
- `admin.html:2095` — `<span id="running-hint">` is never written to (0 references in `admin.js`).
  Its siblings `#retroactive-hint` and `#config-resolve-hint` are both filled from their view
  modules' `CHROME`. The Running summary shows a bare `▾` where the other two show a word plus the
  caret — three rows built to read as one grammar, one missing a limb.

---

### L-3 — the panel resizer is mouse-only; emoji are announced verbatim; one node serves two meanings
**LOW**

- `admin.html:2501` — `<div id="split-resizer">` drives `leftPanelEl.style.width` (`admin.js:889`).
  No `role="separator"`, no `aria-valuenow`, no arrow-key handling. The diagnostics panel cannot be
  resized without a mouse.
- `admin.html:1944` `<div class="logo-badge">⚡</div>` and the nine `.empty-icon` emoji have no
  `aria-hidden="true"`; ~20 button labels and ~30 toast strings are emoji-prefixed. Screen readers
  read "high voltage", "party popper".
- `admin.html:2525` — `<span id="traceback-severity" …>CRITICAL</span>` is 12 px bold red text with
  no icon and no `role="status"`, and `admin.js:4287/4290/4293` reuse the **same node** for
  `결손 조회 실패` / `결손 N건` / `결손 없음`. One element is both a severity badge and a neutral
  count, separated only by hue.

---

### L-4 — 3 px horizontal jitter on row selection
**LOW**

`admin.html:861-864` — `.table-row.active { border-left: 3px solid var(--accent); }` on a `<tr>`
inside `border-collapse: collapse`. Selecting a row adds 3 px to the row box and shifts the first
cell. On a table the operator clicks through row by row, every column twitches.

---

### Out of scope, for Client PM (logic, not presentation)

- `client2/src/admin.js:1748-1753` — `renderChainTable` interpolates `rule.name`, `mapper`, `source`,
  `target`, `sourceNote` into `row.innerHTML` **unescaped**, while `outcome.outcome` and
  `outcome.reason` in the same template *are* escaped. Those five are server-config strings, so the
  risk is low, but this is the drift `admin_rows.js:15-19` was written to prevent (「One author per
  row」) reappearing in the one table that stayed inline.
- `client2/tests/health_card_absence_harness.mjs:33` — `src.indexOf('async function
  refreshFileAndAutoHealth()')` slices the function out of the file as text. That is 잘라쓰기, banned
  by `CLAUDE.md` 시험 상설, and it scores a function the bundler has proven unreachable (H-1) — a
  green gate over pixels no operator can see.

---

## 제안 — 지시받은 것 이상

Proposals only. Nothing below was built. Ranked by what it unblocks.

| # | 무엇 | 왜 (어떤 상황에서 막히나) | 크기 |
|---|---|---|---|
| P-1 | **「지금 도나」 한 줄 — 모든 탭에 상시.** 헤더 아래 한 줄. `/health` 가 «이미» 내는 것을 그대로 읽는다: 프로세스별 `alive` · 마지막 박동 나이 · 멈춘 «이유»(`failure_reason` · `last_exit_code` · `state`). 판정은 서버 것이고 화면은 값만 놓는다. | **「왜 안 도나」의 절반이 여기서 끝난다.** 오늘은 `RuntimePanel` 이 Overview «에만» 있어서, 체인이 안 돌아 Chain 탭으로 간 운영자가 「살았나」 표를 «두고» 간다. 그리고 소유자가 여섯 번 물은 그 답은 지금 «로그에만» 있다 — `server/main.py:318` `_log_chain_worker_exit` 가 「did NOT start … Reason: …」 을 logger 로만 보낸다. 운영자는 보안상 로그를 못 읽는다. ✅ 재료 확인함: `server/main.py:280-290` 이 `heartbeats` · `supervisor_status` · `stale_after` 를 이미 묶어 내고, `server/runtime/health.py:168-186` 이 `failure_reason` · `last_exit_code` · 낡음 판정까지 낸다. **client2 에서 `/health` 를 부르는 파일은 «0» 이다.** | 중 (서버 0줄) |
| P-2 | **H-1 을 되돌릴지 «지울지» 판정.** 스트립은 `display:none`, `refreshHealthStrip` 은 호출자 0, 번들러가 내용을 떨궜다. 셋 중 하나 — ① P-1 로 대체하고 마크업·핸들러·CSS·하니스를 «구간으로» 지운다 ② 되살린다(그러면 H-2 를 «먼저» 고쳐야 한다) ③ 그대로 둔다. | 지금은 「있는 것처럼 보이는 없는 것」이다. 다음 사람이 H-2 의 「정상」 갈래를 못 보고 한 줄로 되살리면 죽은 워커 위에 초록 불이 켜진다. 그리고 `.health-dot` 을 큐 패널이 «빌려 쓰고» 있어(M-13) 「죽은 CSS 를 지운다」가 조용히 다른 부품을 깬다. | 소 (판정) / 중 (실행) |
| P-3 | **거절 문장 «한 벌»로.** `config_resolve_view.js:36-50` 의 다섯(`FETCH_UNREACHABLE` · `FETCH_UNAUTHORIZED` · `FETCH_OLD_SERVER` · `FETCH_INTERCEPTED` · `FETCH_FAILED`)을 파이프라인 상태 표면 넷이 «같이» 쓴다. | 오늘 File·Chain·Auto·Enrichment 는 전송 실패를 전부 「상태 조회 실패」 한 낱말로 접는다 — 고칠 손이 «서버 재기동»인지 «토큰 재입력»인지 «프록시»인지가 안 갈린다. 해답이 «같은 페이지 안에» 이미 있고 넷이 안 쓴다. | 소 |
| P-4 | **갱신 줄이 «무엇이» 갱신됐는지 말한다.** `갱신 HH:MM:SS` 옆에 「N/M 절 읽음」. 부분 실패면 시각을 «안 찍거나» 낡음 표시, 전체 실패면 줄 자체가 「N분째 못 읽음」. | H-3. 지금은 부분 실패에 «새 시각»이 찍히고 전체 실패엔 «옛 시각»이 그대로 있다. 두 경우 다 운영자는 화면을 최신으로 읽는다. 30초 자동 갱신은 `silent:true` 라 토스트도 없다. | 소 |
| P-5 | **키보드로 화면을 한 바퀴 돌 수 있게.** 접기 헤더 13개에 `role="button"` · `tabindex` · `aria-expanded` · Enter/Space, 정렬 헤더에 `aria-sort`, 탭 바에 `role="tablist"/tab` + `aria-selected`, 토스트 컨테이너에 `aria-live="polite"`, `.tx-id-chip` 을 `<button>` 으로. | M-1·M-3·M-5·L-2. 측정값: 이 화면 전체에 `role=` **0** · `tabindex` **0** · `aria-expanded` **0** · `aria-sort` **0** · `aria-live` **0**. 절을 접는 것도 표를 정렬하는 것도 트랜잭션 ID 를 복사하는 것도 «마우스 없이는 불가능»하고, 일괄 재시도의 유일한 확인 통로인 토스트가 낭독되지 않는다. | 중 |
| P-6 | **일괄 재시도 확인창에 «수»를.** 「실패 47건을 재실행합니다」. 가능하면 네이티브 `confirm` 대신 제자리 확인(섹션 헤더 버튼이 「47건 재실행 · 취소」로 바뀜). | M-2. 3건과 3,000건은 다른 행동인데 확인창이 그 수를 안 싣는다. 그리고 네이티브 창은 이 페이지에서 «유일하게» 디자인 시스템 밖이다. | 소 |
| P-7 | **Auto Update 에 「마지막 오류」 칸과 「지난 예정 시각」 표시.** `next_run` 이 과거면 그 칸이 스스로 말한다. | H-5. 멈춘 스케줄러와 도는 스케줄러가 «같은 표»를 그린다. 수집기가 왜 실패했는지는 이 탭에 «한 글자도» 없다. | 중 (서버가 `last_error` 를 내는지 확인 필요 — 「모르는 것」 ①) |
| P-8 | **상태 배지 어휘를 «한 곳»에서.** `admin_rows.js:32` 의 2분기를 `:124-128` 이 이미 쓰는 4분기와 같은 표로 접는다. | H-7. 같은 파일 안에 옳은 판과 틀린 판이 «둘» 있고, 한쪽이 PENDING_RETRY 를 빨갛게 칠한다. | 소 |
| P-9 | **`--fs-*` · `--space-*` · radius 를 「한 축 한 칸」으로 한 라운드.** 전수 실측 표를 먼저(오늘 것: font-size 116선언/12토큰/25값 · spacing 230수/off-grid 183 · radius 33/non-zero 23 · 인라인 156). 그다음 «한 커밋»으로. | M-9·M-10·M-11·M-12. 나눠 착지시키면 그 사이가 거짓이다(`CLAUDE.md` 방법 상설 ④). 지금은 `.admin-btn--sm` 이 토큰으로 «있고» 16개 인라인이 그것을 지나쳐 간다. 그리고 세 자리(`--text-primary`·`--text-secondary`·`--bg`)는 «없는 토큰»이라 지금 이미 조용히 틀리다(H-6). | 대 |
| P-10 | **「5분 쓰면 무엇이 짜증나나」 한 바퀴.** Auto Update·Enrichment·Tables·Ontology 탭은 «자동 갱신이 아예 없다**(`admin.js:411` 이 overview/file/chain 셋만 건다). Run Now 를 누른 운영자는 스스로 Refresh 를 눌러야 결과를 본다. | 「지금」을 말하는 화면인데 네 탭이 스스로 안 따라간다. 소유자 관측 「새로고침 해야하네」가 이미 한 번 나왔고, 그때 고친 것은 Running 목록 «하나»였다. | 소~중 |
| P-11 | **낱말을 한 언어로.** 절 머리의 「칩(한글) + 제목(영문)」 13쌍과 Enrichment 표의 영문 머리 3 + 한글 머리 1, 빈 상태 영문 7 / 한글 2 를 «한 표»로 정한다. | M-14. 지금은 한 표 안에서 언어가 네 번 바뀌고, 영문 버튼을 눌러 한글 토스트를 받는다. 도메인 운영자에게 「Rule」과 「규칙」이 같은 것인지 확신할 근거가 화면에 없다. | 소 (판정) / 중 (적용) |

---

## 모르는 것

정직하게 — 소스만으로는 판정할 수 없었던 것들.

1. **`/admin/auto-update/status` 가 `last_error` 를 «내는지».** 클라가 안 읽는 것은 확인했다(H-5).
   서버가 그 값을 «갖고 있는지»는 안 봤다. P-7 의 크기가 여기서 갈린다 — 있으면 화면 한 줄, 없으면
   서버 라운드.
2. **`/runtime` 응답의 실제 모양.** `runtime_panel.js` 가 여덟 열(`loop`·`process`·`alive`·`age`·
   `seconds`·`depth`·`pace`·`knob`)을 «선언»하지만, 운영에서 그중 몇 열에 값이 오는지는 응답을 봐야
   안다. `visibleColumns()` 가 값 없는 열을 지우므로 **여덟 열짜리 표일 수도, 두 열짜리일 수도
   있다.** 이 표가 P-1 의 재료라 크기 추정이 여기 걸려 있다.
3. **글자가 선에 닿는지 — 스샷 판별식을 못 돌렸다.** 서버를 띄우지 않았으므로 「스샷에서 글자가 선에
   «닿아» 있으면 그 부품은 안 끝난 것이다」를 «측정»하지 못했다. CSS 상으로는 표(`6.8px 10.2px`)와
   절 헤더(`10.2px 13.6px`)가 격자 위에 있어 «선언상» 통과지만, 실제로 닿는 자리는 대개 «인라인
   스타일»이나 «오버플로 잘림»에서 생긴다. 인라인 156개는 세었고, 그중 어느 것이 실제로 붙는지는
   **띄워 봐야 안다.**
4. **`sticky` 표 머리가 어디에 붙는지.** `admin.html:1051-1056` 의 주석이 스스로 「안 재 본 값」이라
   적어 두었다 — `.section-body { overflow-x: auto }` 가 생기면서 `thead` 의 sticky 기준이 탭
   래퍼에서 «이 절»로 바뀐다. 행이 많은 표를 세로로 굴릴 때 머리가 남는지는 **데이터가 있는 화면을
   열어야** 보인다.
5. **다크 테마 실측.** 세 토큰이 «없다»는 것(H-6)은 정적으로 확정했고 `fill` 이 검정으로 떨어지는
   것도 상속 규칙으로 확정했다. 그러나 `#fff` 노브(`admin.html:956`)와 검정 원, 회색 트랙
   (`rgba(127,127,127,.22)`)이 두 테마에서 «얼마나» 나쁜지는 렌더링해야 안다. 대비비를 계산으로
   낼 수는 있으나 그건 「측정」이 아니라 「추정」이라 적지 않았다.
6. **좌패널이 좁을 때의 넘침.** `admin.html:1029-1040` 에 폭별 넘침 실측 표(546/496/446/396/346 →
   전부 0)가 있는데 그것은 «자산 네 절» 기준이다. 오늘 있는 절들(규칙 등록·표 등록·대기열·소스 상태)이
   같은 폭에서 0 인지는 **안 쟀다.**
7. **`status_vocabulary` 가 실제로 언제 도착하는지.** H-4 의 심각도는 「옵션이 늦게 온다」가 얼마나
   잦은지에 달려 있다. 한 번도 안 늦으면 잠재 결함이고, 첫 로드마다 늦으면 오늘의 결함이다.
   **네트워크 타이밍이라 소스로는 못 가른다.**
8. **운영 규격에서의 그림.** `CLAUDE.md` 운영 모양(체인 한 트랜잭션 «수천 행» · 맵 20×20 · 동시
   사용자 ~10) 기준으로 이 화면이 어떻게 보이는지 — 특히 대기열 목록과 실패 로그가 수천 행일 때 —
   는 **재지 않았다.** 이 박스에서 잰 수를 운영 주장으로 내지 않기 위해 아예 안 쟀다.
