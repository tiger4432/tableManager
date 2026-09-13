# Client half of the bonding-availability relaxation — the gross number now says so

Lane: map-pm (DOE panel) · Date: 2026-08-04 · Scope: `client2/src/transfer_plan.js` (+ its CSS,
+ one new harness, + that harness's floor entry).

Closes QA `2c2a777` finding **B2** ("the field designed to prevent B1 has zero readers, and the
UI renders gross in the typography reserved for exact-net"). B1 (the `validate` route) was fixed
server-side by another lane and is not touched here.

**Lane check before editing:** `client2/src/map_editor.js`, `client2/src/map_key.js`,
`client2/tests/map_key_*`, `contracts/map_seam/**` — **not touched.** `git diff --stat` confirms
my four paths are disjoint from the concurrent legend-registry extraction (which owns the
`map_editor.js -354` and `contracts/*` hunks in the shared tree).

---

## 1. The defect, restated as what the operator saw

`client2/src/transfer_plan.js` `availCellHtml` rendered `av.reliable ? '<b>'+av.value+'</b>'`.
After `2c2a777`, a site that never declared `transfer_log` gets `remaining_reliable: true` and a
real number computed **without** the transfer subtraction. That number reached the 가용 cell as
`<b>8</b>` — the exact same eleven bytes a fully-subtracted 8 produces. `inactive_subtractions`
had 0 occurrences in all of `client2/`.

The relaxation is what the user asked for. The silence is not.

---

## 2. What was built

### 2.1 One reader, one shape

`availabilityOfPool` — the file's single interpretation point for the server's availability
response — now also returns `inactive`, **always an array** (empty when the field is absent).
That mirrors the `bound` discipline already stated in that function's comment: a field that is
present on only some branches makes consumers distinguish `undefined` from "none", and the
judgement splits in two.

```js
function inactiveSubtractionsOf(data) {
  const raw = data && data.inactive_subtractions;
  if (!Array.isArray(raw)) return [];   // 필드 부재 = 전 역할 선언 사이트. 오늘과 같다.
  return raw.map(r => String(r == null ? '' : r).trim()).filter(r => r !== '');
}
```

Three things it deliberately does not do: it does not translate the role names, it does not
demote `reliable`, and it does not accept a non-array (a broken field yields no roles rather
than a fabricated one).

### 2.2 The rendering: a footnote mark on the number, and a full-size footnote

| surface | fully declared (field absent) | relaxed (field present) |
|---|---|---|
| 가용 cell | `<b>8</b>` | `<b class="tp-gross" title="…transfer_log, origin_log, fail_sources…">8</b><span class="tp-gross mk" title="…">*</span>` |
| 잔여 cell | `<span class="ap">≈</span>5` | `<span class="ap">≈</span><span class="tp-gross" title="…">5</span><span class="tp-gross mk" title="…">*</span>` |
| ② footnote | *(nothing added)* | `* 표시가 붙은 가용·잔여는 감산을 빼지 않은 수입니다 — 이 사이트가 선언하지 않아 집계에서 빠진 감산: transfer_log · origin_log · fail_sources. 실제 잔여는 이 값보다 적을 수 있습니다.` |
| `↻ 가용` toast | `가용 조회 완료 — 3개 풀` (info) | `가용 조회 완료 — 3개 풀 · 2개는 감산 미적용(transfer_log, origin_log, fail_sources)` (warning) |

### 2.3 Why this is readable rather than decorative

The 가용 column is **58px of monospace**. A sentence does not fit there, so the design refuses to
let the glyph carry the meaning. It splits the disclosure in two, and both halves are measured:

- **The mark is not shrunk.** Measured live against the real `transfer_plan.css` in the running
  dev server: the gross number renders **13px / weight 700**, byte-for-byte the same size and
  weight as a plain confident number, and the `*` is **13px / 700** too — not a superscript, not
  a 9px dot. `scrollWidth === clientWidth === 58` — `8*` fits without overflow.
- **It is distinguishable at a glance.** `#8A5A00` on the pane background = **5.19:1** contrast
  (WCAG AA for normal text is 4.5:1). This follows the grammar `.tp-bound` already established
  in this exact column — same size, same slot, colour is the only axis that splits — so the
  screen does not grow a new visual language.
- **The names live at body size.** The role names are printed in the ② footnote in
  `<code class="tp-gross-role">`, styled `color: var(--text)` — **darker than the surrounding
  footnote text**, which is `--text-dim`. The tokens the operator has to go find in
  `transfer_plan_config.json` are the highest-contrast thing on that line. A 9px badge holding
  three table names would be the appearance of disclosure without the fact of it; a `*` that
  points at a legible sentence is the fact.
- **It is the universal footnote convention.** `*` already means "there is a qualifier below" to
  every reader, so the pointer costs one character and no learning.

### 2.4 The four constraints, discharged

- **`≤` not reused.** `GROSS_MARK = '*'`. The two states can co-occur (a site can declare
  `transfer_log: "none"` — a real upper bound — while never declaring `origin_log`), and when
  they do the cell renders `≤12*`: the marker is **added, not substituted**. Two different
  claims, both true, visibly different. A harness mutant that sets `GROSS_MARK = '≤'` is caught.
- **Absent field is byte-identical.** Scored against string literals recorded from the
  pre-change render (`<b>8</b>`, `<span class="ap">≈</span>5`), not against a re-derived
  expectation. `grossNoteHtml([])` returns `''`, so the footnote is unchanged too. A mutant that
  marks the declared path is caught by that literal.
- **Server's vocabulary.** `transfer_log` / `origin_log` / `fail_sources` are printed verbatim,
  in the server's order, escaped but not translated and not sorted. Two mutants cover this
  (`drop the role names`, `sort the union`).
- **Not tied to `remaining_reliable`.** `isGross(av)` reads `av.inactive.length` only. The
  harness asserts `avB.reliable === true && isGross(avB) === true` on the same fixture — the
  marker appears **while** the server calls the number reliable. A mutant that ANDs the marker
  with `av.reliable !== true` is caught.

### 2.5 Complexity budget

| | count |
|---|---|
| new panels / modes / modals | **0** |
| net new controls (buttons, toggles, inputs) | **0** |
| controls removed | 0 |
| added clicks on the read path | **0** |
| added confirmations on the read path | **0** |
| new conditional text on existing surfaces | 3 (1 char in 2 cells, 1 footnote line, 1 toast clause) |

Everything lands on surfaces that already exist: the 가용/잔여 cells, the ② footnote that already
carries the 미상 ≠ 0 warning, and the `↻ 가용` toast that already reports dominant unknowns.
Nothing on the write path changed.

### 2.6 One-implementation discipline

`grossRolesOf(avs)` computes the union once; the footnote and the toast both call it. The first
draft had the union inline in two places — that is the shape of the `ceil`/`round` incident
(DB 34, screen 33), and it was folded before it could split.

### 2.7 The shortage highlight, deliberately unchanged

QA noted a gross-derived 잔여 suppresses the red that a net computation would have shown. It
stays suppressed, with a comment saying why: the client does not know the magnitude of the
missing subtraction, so painting every gross remainder red is an alarm with no evidence behind
it. The gap is closed by the marker and the footnote, not by colour. A mutant that turns on red
for a positive gross remainder is caught (`F/a positive gross remainder is not painted red`).

---

## 3. Both-paths fixture evidence

Produced by the **real sliced functions** (`availabilityOfPool`, `availCellHtml`,
`remainingCellHtml`, `grossRolesOf`, `grossNoteHtml` from `transfer_plan.js`; `remainingState`
from `doe_bands.js`) evaluated in a vm sandbox. Payloads identical except for the one field.

```
==============================================================================
PATH A — inactive_subtractions ABSENT
==============================================================================
interpreter : reliable=true  value=8  bound=null  inactive=[]
가용 cell   : <b>8</b>
잔여 cell   : <span class="ap">≈</span>5
footnote    : ""

==============================================================================
PATH B — inactive_subtractions PRESENT
==============================================================================
interpreter : reliable=true  value=8  bound=null  inactive=["transfer_log","origin_log","fail_sources"]
가용 cell   : <b class="tp-gross" title="감산을 빼지 않은 수입니다 — 이 사이트가 선언하지 않아 집계에서
              빠진 감산: transfer_log, origin_log, fail_sources. 실제 잔여는 이 값보다 적을 수
              있습니다.">8</b><span class="tp-gross mk" title="…같은 문구…">*</span>
잔여 cell   : <span class="ap">≈</span><span class="tp-gross" title="…">5</span><span class="tp-gross mk" title="…">*</span>
footnote    : "<br>\n  <b class=\"tp-gross\">*</b> 표시가 붙은 <b>가용·잔여는 감산을 빼지 않은 수</b>입니다 —\n
              이 사이트가 선언하지 않아 집계에서 빠진 감산: <code class=\"tp-gross-role\">transfer_log</code> ·
              <code class=\"tp-gross-role\">origin_log</code> · <code class=\"tp-gross-role\">fail_sources</code>.\n
              <b>실제 잔여는 이 값보다 적을 수 있습니다.</b>"
```

Path A's two cell strings are **character-identical** to the pre-change render. Path B's number
is still `8` and still `≈5` — the relaxation's whole point is that the number is usable; only its
qualification changed.

### 3.1 The fixture activates the defect axes

- `remaining` differs per BIN (**8** vs **3**), so picking the wrong `bins.entries` item shows.
- `used = 3` is non-zero, so **잔여 (5) ≠ 가용 (8)** — a marker applied to the wrong cell shows.
- The inactive list has **three** entries in **non-alphabetical** order
  (`transfer_log, origin_log, fail_sources`), so both a dropped name and a sort are visible.
  With a one-element or alphabetical list, neither defect could appear in principle.
- One fixture carries `transfer_untracked: true` **and** `inactive_subtractions` together, so the
  `≤`-vs-`*` collapse is reachable.
- One fixture carries `remaining: null` **on the relaxed path**, so a null-to-zero coercion is
  reachable.

### 3.2 The verification was checked against reverted defects

17 defect mutants were injected into the real source and re-scored. **17/17 caught, 0 escaped.**
The two that matter most:

| mutant | caught by |
|---|---|
| `stop reading the field at all` (`raw = null`) | `B/avail carries the marker — <b>8</b>` — i.e. it reproduces the exact pre-fix defect string |
| `drop inactive from the ok branch of the interpreter` | same |
| `tie the marker to the reliability axis` | `B/avail carries the marker — <b>8</b>` |
| `borrow the ≤ convention` | `B/the marker is NOT the ≤ convention` |
| `mark the fully-declared path too` | `A/avail cell is the pre-change string` |
| `coerce a null remaining to 0` | `D/null remaining stays null — got 0 want null` |
| `let the ≤ branch swallow the marker` | `C/and the marker is added, not substituted` |
| `paint a positive gross remainder red` | `F/a positive gross remainder is not painted red` |

2 control mutants (consistent local rename across both sliced modules; every full-line comment
stripped) both **escaped**, so no check is scoring source text instead of behaviour.

### 3.3 Live legibility measurement

Measured in the running dev server (`localhost:5173`) in an **isolated tab** (the seed tab
belongs to the concurrent lane), by injecting the produced HTML into the page so it picked up
the real `transfer_plan.css`. Read-only; the probe node was removed and the tab closed. No
network call, no state mutation, no config or DB touched.

```
theme_bg          rgb(238,240,244)
plain_number      13px / 700 / rgb(31,39,51)     contrast 13.18:1
gross_number      13px / 700 / rgb(138,90,0)     contrast  5.19:1
gross_mark  (*)   13px / 700 / rgb(138,90,0)
bound_number(≤)   13px / 700 / rgb(26,102,208)
footnote_role     12px / 400 / rgb(31,39,51)   ← full text colour, not --text-dim
same_size_as_plain  true
avail cell width 58px, scrollWidth 58px          ← no overflow
```

---

## 4. Null-safety re-verification (measured, not assumed)

QA's CLEAN verdict **re-confirmed independently**, and extended:

| claim | measurement | result |
|---|---|---|
| `transferred` has no client reader | `grep -rn "transferred" client2/src client2/tests client2/*.html` | **0 occurrences** |
| `/api/bonding-plan/core-summary` has no consumer | `grep -rn "core-summary\|core_summary" client2/src client2/*.html` | **0 occurrences** |
| per-core `used` is never read | `grep -rn "by_core" client2/src` | 3 hits, **all** either a comment or inside the `__held_*` block that no renderer calls (`transfer_plan.js:1790`, `:1818`, `:1839`) |
| no `\|\| 0` coercion on a server number | every `\|\| 0` in `transfer_plan.js` audited | `paintedOf` (client paint counts), `tally.get(r) \|\| 0` (Map default), `c.depth \|\| 0` (client ctx). **None reads a server payload field.** |
| `remaining` is explicitly guarded | `transfer_plan.js:472`, `:483` | `=== null \|\| === undefined` before `Number()`, both sites |
| `remainingState`'s `Number(used \|\| 0)` is not a server value | `doe_bands.js:449` `e.used += d.share`, accumulator initialised to `0` in `materialRollupRows` | **client-computed**, never a server field |
| `remainingState` cannot manufacture a number from a null availability | new assertions D5/D6 | `value === null`, `reliable === false` |
| nothing prints `null` / `NaN` / `undefined` | new assertion D3 over both cells on the relaxed-null fixture | **clean** |

**No consumer coerces a null to 0.** Contract change #1 is safe as written, and the harness now
pins it: the `coerce a null remaining to 0` mutant fails the suite.

**One thing QA did not measure, found here:** `doe_bands.js:678 rollupToGrid` renders 가용 as a
bare `num(r.availability)` for an Excel copy-out of ②. It is **not a live surface** —
`grep -rn "rollupToGrid" client2/src client2/tests` returns the definition and the export line
and **no caller**. Not a defect today, and not marked, because marking a function nobody calls
would be untestable decoration. Board item in §7.

---

## 5. Harness numbers, before and after

```
BEFORE   22 harnesses ― 17 gated, 5 on the known-red debt list (5 still red, 0 recovered).
         ✓ every gated harness is green.                                      exit 0

AFTER    23 harnesses ― 18 gated, 5 on the known-red debt list (5 still red, 0 recovered).
         ✓ every gated harness is green.                                      exit 0
         ✓ availability_gross_marker_harness.mjs  (ran 48, failed 0)
```

**No floor was edited.** The five known-red entries are byte-identical (`ran`/`failed` unchanged:
0/0, 0/0, 0/0, 99/1, 228/42) and every pre-existing green harness reports its previous count
exactly (84, 151, 131, 46, 15, 116, 53, 69, 15, 263, 19, 29, 6, 17498, 153, 94, 59). The only
`FLOORS` change is an **added row** for the new harness — the runner itself blocks without it
("1 harness(es) have no recorded floor and are NOT protected against silently scoring less").

New harness self-report:

```
48 passed, 0 failed; 17/17 defects caught, 0 escaped; 2/2 controls escaped.
ASSERTIONS 48 0
```

`npm run build` was **not** run; `client2/dist/` untouched by this lane.

---

## 6. Files

| path | change |
|---|---|
| `C:\Users\kk980\Developments\assyManager\client2\src\transfer_plan.js` | +131/−14. `inactiveSubtractionsOf` · `grossReason` · `isGross` · `grossRolesOf` · `grossNoteHtml` · `GROSS_MARK`; `availabilityOfPool` returns `inactive`; `availCellHtml` / `remainingCellHtml` mark; `renderMaterialPane` footnote; `refreshMaterials` toast clause |
| `C:\Users\kk980\Developments\assyManager\client2\src\transfer_plan.css` | +22. `.tp-num .tp-gross` / `.mk`, `.tp-foot-note .tp-gross` / `.tp-gross-role` |
| `C:\Users\kk980\Developments\assyManager\client2\tests\availability_gross_marker_harness.mjs` | new, 48 assertions / 17 defect mutants / 2 controls |
| `C:\Users\kk980\Developments\assyManager\client2\scripts\check_harnesses.mjs` | +3, one `FLOORS` row (required by the runner; no existing floor touched) |

**Not staged, not committed** — this lane's standing constraint is 커밋 금지, and the working tree
is shared with at least three other in-flight lanes (`map_editor.js`, `contracts/*`, `server/*`,
`docs/*` all carry other lanes' edits right now), so staging would risk another lane's
`git commit` sweeping these files in. Lead PM: stage exactly the four paths above.

Suggested commit message:

```
fix(map): the screen must say which subtractions it did not make

`2c2a777` let a site that never declares transfer_log/origin_log/fail_sources/
process_history receive a real availability computed without those subtractions,
and emit `inactive_subtractions` so the number could not pose as net. The field had
zero readers in client2: `availCellHtml` rendered it `<b>8</b>`, byte-identical to a
fully-subtracted 8.

`availabilityOfPool` now returns `inactive` (always an array), and a `*` footnote mark
joins the 가용 AND 잔여 cells at the same size and weight as a confident number, in
warning colour — the same grammar `.tp-bound` uses for `≤`, which is deliberately NOT
borrowed here: the relaxed path does not set `remaining_upper_bound`, and the two states
can co-occur (`≤12*`). The server's own role names are printed verbatim, at body size, in
②'s existing footnote and in both tooltips; the `↻ 가용` toast names them too. No new
panel, mode, modal or control. An absent field renders character-identically to before.

The marker is not tied to `remaining_reliable`, which is `true` on this path and remains
the reliability authority.

New harness scores both paths against literals recorded from the pre-change render:
48 assertions, 17/17 defect mutants caught, 2/2 controls escaped.
```

---

## 7. Handoffs (not done here — out of lane)

1. **Living doc — `docs/spec/MAP_EDITOR_SPEC.md §6.2-ter`** (row `DOC_OWNERSHIP.md:77`, 본딩·전사
   계획 엔진 → `client2/src/transfer_plan.js`). The section ends with "그 `ok`를 어떻게 그릴지는
   **소비자가 정합니다**" and stops. The consumer has now decided, and the decision is a contract:
   `*` (not `≤`) on 가용 **and** 잔여, server role names verbatim at body size in ②'s footnote,
   marker independent of `remaining_reliable`, absent field byte-identical. **doc-keeper.**
2. **`docs/architecture/frontend.md §3`** — no new module was added, so no row is needed; noted
   only so the sweep is not re-run.
3. **Board item: `doe_bands.js:678 rollupToGrid`** — ②'s Excel copy-out renders 가용 as a bare
   number and has **zero callers**. When ② copy-out is wired, that column needs the same
   qualifier, or the relaxed number escapes to a spreadsheet with nothing attached (and a
   spreadsheet number is the one that gets forwarded). File is out of this lane's four paths.
4. **QA B4 (`__held_classifySourceStatus`)** — `not_declared` still falls through to
   `알 수 없는 상태` in the held source-badge block and is then filtered out. Left alone: it is
   dead code, and re-animating half of a held block is how a screen grows a mode. Whoever
   re-enables that block owns adding `not_declared`.

---

## 8. Proposed memory entries (map-pm — proposal only, not self-added)

1. **함정**: 좁은 수 열(58px)에 자격 표시를 넣을 때, 의미를 **기호에 실으려다** 9px 배지를 만든다.
   읽히지 않는 공시는 공시가 아니라 공시의 외양이고, 그건 표시가 없는 것보다 나쁘다.
   **올바른 방법**: 표시를 **둘로 쪼갠다** — 셀에는 본문과 **같은 크기·같은 굵기**의 한 글자
   각주 기호만 두고, **이름은 같은 화면의 기존 각주에 본문 크기로** 적는다. 크기·대비를
   실측해서 보고한다(색만 바꾸고 크기는 건드리지 않는 것이 `.tp-bound`가 이미 세운 문법이다).
2. **함정**: 새 상태에 **기존 기호를 빌려 쓰면** 서로 다른 두 상태가 화면에서 같아진다.
   `≤`는 `remaining_upper_bound` 전용인데 서버는 완화 갈래에서 그 필드를 **일부러 세우지
   않는다** — 빌려 썼으면 "상한을 안다"와 "감산을 안 했다"가 한 그림이 됐을 것이다.
   **올바른 방법**: 두 상태가 **동시에 참일 수 있는지** 먼저 묻는다. 그렇다면 새 표시는
   기존 표시를 **대체가 아니라 병기**해야 하고(`≤12*`), 픽스처에 그 공존 케이스를 넣는다.
3. **함정**: "필드 부재 시 오늘과 같다"를 **오늘의 코드로 기댓값을 만들어** 채점하면 아무것도
   증명하지 못한다 — 결함이 있는 렌더러와 그 렌더러로 만든 기댓값은 항상 일치한다.
   **올바른 방법**: 변경 **전** 출력을 **문자열 리터럴로 박제**해 대조한다. 그 리터럴이
   「오늘」의 유일한 독립 오라클이다.
4. **함정**: 서버가 새 신뢰 축을 만들지 **않았는데** 클라가 만들어 버린다. 완화 갈래의
   `remaining_reliable`는 `true`이고, 표시를 `reliable`에 묶으면 사이트가 쓰기로 결정한 숫자가
   `미상`으로 붕괴한다 — 완화의 목적 그 자체가 사라진다.
   **올바른 방법**: 신뢰 축과 **공시 축**을 분리한다. 새 표시는 새 필드의 유무만 읽고,
   `reliable === true`인 픽스처에서 표시가 뜨는지를 명시적으로 채점한다.
