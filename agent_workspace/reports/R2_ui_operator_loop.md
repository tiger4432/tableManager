# R2 - UI lens: what the operator must see to trust the die map

> Round 2, UI lens. Design report only. No code changed, no build, no commit.
> Korean strings below are the proposed UI copy. Prose is English.
> Mockup: `agent_workspace/reports/R2_ui_operator_loop.html` (static file, open in a browser).

---

## 0. The one thing this report argues

**The screen the operator needs is not in the map editor, and building it there is the reason
the reload loop exists.**

The operator described the complaint in the map editor's vocabulary ("맵을 열고 프레임을 맞추는
행위"), so the instinct is to make the map editor faster. But look at the shape of the work under
the corrected four-step chain:

    coordinate system confirmed -> align multiple defect sources -> die map confirmed -> bonding plan

The unit of the decision is **(dt_eqp, product)** - one equipment, one product, spanning many maps
and several sources. The map editor's unit is **one map**. Every extra map under the same
(eqp, product) is a load the operator should never have paid for. The reload loop is not slow
loading; it is **N loads for a decision whose N is 1**.

`server/config/enrichment_rules.json` already declares that decision at the right unit
(`eqp_product_frame_attribution`, `decision_key: [dt_eqp, product]`, `target_fields:
[core_frame, dt_frame]`), and `client2/enrichment.html` already has the three-panel workbench
that shape wants. So the resolution of the "no new panes" constraint is not a compromise:
**the pane already exists and it is the right pane.**

Everything below is specified as changes to the existing enrichment workbench
(`client2/enrichment.html` lines 795-871, `client2/src/enrichment.js`).
Zero new panes, zero modes, zero modals.

---

## 1. Q1 - what is on screen at the moment of the decision

The decision under the corrected chain is not "is this map oriented right". It is:

> **do these N sources, each placed on the common floor by its own frame, tell the same story
> per die - enough that a bonding plan may be built on the result?**

That is two layers of evidence and the screen must keep them separate:

| layer | question | who can check it |
|---|---|---|
| **L1** source vs floor | is this source's frame the one that matches the floor? | the scorer, and the operator by eye |
| **L2** source vs source | do two independent witnesses put the same defect in the same cell? | only available when N >= 2 |

L2 is the one the bonding plan actually rests on, and **no single source can produce it.**

### 1.1 Layout - three panels, unchanged geometry

| panel | today | R2 |
|---|---|---|
| **[A] 워크리스트** (flex 3) | queue rows | unchanged, plus the availability partition (section 5) |
| **[B] 판단 - 입력** (flex 2) | free-text target inputs | **source rows + inline candidate grid + confirm** |
| **[C] 참조뷰** (flex 2) | text tables, 4 tabs | **one more tab whose body is a picture, not a table** |

A picture is a new tab in an existing tab strip. That is not a new pane.

### 1.2 Panel [C] - THE PICTURE (largest element, ~60% of the panel body)

This is the single most important element on the screen, and the argument for it is not
aesthetic. **It is the only element the operator can check without trusting us.** The score is
produced by code the operator cannot audit; the shape is produced by their own eyes. If the
budget forces a cut, the number goes and the picture stays.

Three draw layers, and the visual weight is deliberately inverted from instinct:

| layer | draw | why |
|---|---|---|
| **바닥 (floor)** - reference footprint | flat, quiet, `--canvas-inside-empty` weight | it is the stage, not the news |
| **일치** | same quiet fill | agreement is the ground |
| **불일치** | full-strength `--accent` fill, drawn LAST | **the error shape is the figure** |
| **한쪽만 있음** | `--orange` ring, no fill | coverage gap is not disagreement, and must not read as one |

Round 1 measured that the primary channel is shape, not number: whether the misses **cluster on
an asymmetric feature** or lie as a **crescent along one edge**, and that the crescent is a
direction vector telling you which way to shift. Drawing agreement loudly buries exactly that.

**Caption, always present, directly under the picture** (0.85rem, not smaller):

    지금 보는 것: DT 출처 · 0° · 앞면 · 기준 대비
    지금 보는 것: 출처 2개 상호 일치

The caption exists because the picture answers a different question depending on which row in
panel [B] has focus, and a picture that silently changes its meaning is worse than no picture.

**Scale check.** The spec's own figure is 567 dies (§2.1, §3), which is a grid of roughly
27 x 27 including the circle. At a 1600px viewport with the current flex 3:2:2, panel [C]'s
canvas is about 404px wide, giving **~15 px per die**. The shape channel needs about **8 px per
die** to keep a crescent contiguous and readable. **So the current panel widths are sufficient
and I am not asking for a layout change.** They stop being sufficient above roughly 50 dies per
side (~2,000 dies), at which point either the flex moves to 2:2:3 (545px, ~11 px/die) or the
picture drops to the discriminating subset only. Grid size per production map is **unmeasured in
this round** - flagged for the map lens.

### 1.3 Panel [B] - the source rows (N rows, one per target field)

`target_fields` and "sources" are the same list. `core_frame` is the CORE map's frame,
`dt_frame` is the DT log's frame. So the source strip needs no new data model - it is the
existing target field list rendered as rows instead of text inputs.

Each row, at 0.95rem or larger:

    ┌──────────────────────────────────────────────────────┐
    │ CORE 맵          270° · 뒷면        일치 512 / 판별 528│  <- 확정 표시
    │ DT 로그          고르지 않음        구별 안 됨 · 후보 3개│
    ├──────────────────────────────────────────────────────┤
    │ 출처 2개 상호 일치   일치 -  · 불일치 -  · 한쪽만 -     │  <- L2 row
    └──────────────────────────────────────────────────────┘

Clicking a row expands its candidate grid **inline, inside the same block** (accordion; one open
at a time). Not a modal, not a pane, not a mode - the block already exists
(`#target-input-block`, enrichment.html:836).

The **L2 row is the (N+1)th focusable row**. Focusing it swaps the picture to per-die
cross-source agreement. That is how L2 gets a first-class place on screen without a new pane.

### 1.4 What replaces the percentage

Round 1 measured that a coverage percentage **inverts rankings**: a correctly-oriented but
offset candidate at 94% ranked below three wrongly-oriented candidates at 98/97/95. So the
percentage must not appear anywhere on this screen.

**The replacement is two absolute counts, and the denominator is the point:**

    일치 512 / 판별 528        <- agreement over the DISCRIMINATING subset
    2위와 47다이 차이           <- margin, also a count

Why counts and not the measured 6.1-7.5pp margin:

1. **A percentage destroys the denominator, and the denominator is the evidence.**
   `일치 38 / 판별 40` and `일치 512 / 판별 528` are both "95%". The first says *there are only
   40 dies of evidence here* - which is the single most decision-relevant fact on the screen -
   and the percentage erases it.
2. Spec §3 rule 3 requires normalizing to the discriminating subset (symmetric core cells carry
   zero information). Once you have done that, the natural unit is already a die count.
3. "47 dies apart" is a physical quantity to a die engineer. "6.1pp" is not.

**Thresholds go to config, not to code** (`enrichment_rules.json`, per rule):

    "align_scoring": { "min_margin_dies": 20, "min_discriminating_dies": 40 }

Both knobs are needed and neither substitutes for the other: a 47-die margin over a
528-die discriminating subset is a result; a 47-die margin over a 60-die subset is a coincidence
waiting to happen.

**What the operator should conclude when the margin is small:** nothing about the map. The
screen must say so in the machine's own voice rather than let the operator infer:

    이 기준으로는 구별되지 않습니다 - 후보 3개
    (원인) 기준 발자국이 대칭입니다 - 후보 3개가 같은 다이를 차지합니다

and the cause line must distinguish the two facts spec §4 says are different:

    (원인) 기준이 원 기하뿐입니다 - 비대칭 기준이 없습니다        <- fix: plug a better reference
    (원인) 기준 발자국이 대칭입니다 - 세 후보가 같은 다이를 차지합니다  <- fix: nothing; it is genuinely ambiguous

When no winner is marked, **no candidate carries a badge**. The absence of a mark is the answer.

### 1.5 The second metric: computed always, shown only when it disagrees

Spec §3 requires both footprint-overlap and value-agreement to be computed. Showing both always
doubles the numerals for zero decision value - a second metric that agrees changes nothing.
So: compute both, surface the second **only** on disagreement, as one line:

    두 지표가 다른 후보를 가리킵니다 - 값 일치는 270°·뒷면, 점유는 90°·앞면

That line is worth more than eight rows of a second number column, because it is the only
condition under which the second metric alters the decision.

### 1.6 Deliberately NOT on this screen - and why each is noise

| cut | measured reason |
|---|---|
| any fitness percentage | inverts rankings (spec §3) |
| a rotate button, and the notch | the same transform on both compared sets cannot change their relation (§1, I9); the notch is drawn from `currentRotation` so it renders the hypothesis (I8) |
| all 16 spellings | every answer appears twice (§2.1 ⑤) |
| 총 개수 (total die count) as a score | spec §3: 절대 쓰지 말 것 - 8 mappings yield 1-2 distinct values |
| a confidence bar or gauge | a continuous visual for a discrete 8-way decision manufactures precision that was not measured |
| 8 candidate thumbnails | eight pictures at 100px each are eight unreadable pictures; small marks are a defect for the same reason small type is. One large picture that swaps on click carries strictly more information |
| a second numeric column for the occupancy metric | see 1.5 |

---

## 2. Q2 - killing the reload loop

### 2.1 The request and the constraint do not actually conflict

The operator asked for "db값을 고정하고 좌표계만 돌릴 수 있는 모드". Round 1 proved that turning
the whole coordinate system teaches nothing, because the transform lands on both compared sets.
So the literal request is for a control that cannot inform.

But the request is not wrong - it is **under-specified about what stays still.** Reframe it:

| | held fixed | turned | informative? |
|---|---|---|---|
| what the map editor does today | nothing | map + coordinate system together | **no** - I9 |
| what the operator meant | DB values | coordinate system | ambiguous |
| **what actually informs** | **the floor (reference)** | **this source's cells under it** | **yes - it can be wrong** |

Hold the **floor** still and turn **the source on top of it**. Same two hands, different anchor.
And this version can produce a wrong-looking picture, which is precisely what makes it evidence.
That is also literally the workflow they described: lay down the valid-die coordinate system as
the common floor, then bring sources onto it and check the match.

### 2.2 It is not a mode. It is a change to how the existing view reads its data.

Today: one selection -> one fetch -> rows for whatever the stored declaration is.
R2: one selection -> **one fetch that returns the cells once plus all 8 candidate scorings** ->
candidate selection is a **pure client-side repaint of data already in hand**.

The operator never triggers a load. There is no "check" round trip, because all eight answers
arrived together with the first and only one.

**This is the load-bearing requirement of the whole design.** If the client fetched per
candidate, eight round trips per row would blow the 30-second bar on its own. The reference view
must return the scoring of all 8 in a single payload. That is a server/client contract item, not
a presentation item - see section 6.

### 2.3 Cost, in actions and seconds

The switchover bar is **8 maps, <= 4 actions each, <= 30 seconds each, 0 DB writes while
exploring.** The bar governs *exploring*, so the confirm keystrokes are counted separately.

Exploring one (dt_eqp, product) row:

| # | action | cost |
|---|---|---|
| 1 | select the row (Down arrow, or click) | 1 action, 1 fetch (debounced, `REF_DEBOUNCE_MS`) |
| - | read the picture and the marked winner | 0 actions, ~5-12 s |
| 2 | *optional* click a rival candidate to compare | 1 action, **0 fetches**, one canvas repaint |
| 3 | *optional* focus the L2 row to see cross-source agreement | 1 action, 0 fetches |

**3 actions worst case, 0 writes.** Budget: fetch p95 <= 1.5 s, repaint <= 16 ms
(~567 rects is far under one frame). Total ~10-20 s. **Meets the bar with one action spare.**

Two caveats stated honestly:
- Pooling means one worklist row may cover many maps, so "8 maps" may be 1-2 rows.
  **The maps-per-row ratio is unmeasured**; I am not claiming the bar is beaten 8x.
- The bar is met *only* if 2.2 holds. Per-candidate fetching fails it.

Confirming adds **2 keystrokes** (arm + confirm), outside the bar.

### 2.4 Confirming the die map - the one genuine write

Reading is frictionless; this write gets exactly one confirmation, and it is not a modal.
The existing `#save-btn` becomes a two-state inline control:

1. Enter (or click) **arms** it. The button relabels to the sentence below and a hint appears.
2. Enter again (or click again) **commits**. Esc disarms.

The sentence the operator reads, and what they are affirming:

    CORE 맵 270°·뒷면, DT 로그 0°·앞면으로 이 설비·제품의 좌표계를 확정합니다.
    이후 이 설비·제품의 다이 맵과 본딩 계획이 이 좌표계 위에 세워집니다.

Two clauses on purpose: the first names the values (so a mis-click is visible before it lands),
the second names the consequence (so the operator knows what they are underwriting). Note the
config comment already states why this one deserves friction: a wrong frame bakes an unverified
rotation into stored coordinates and **nothing downstream looks wrong afterwards.**

`confirm_before_write: true` is a **per-rule config flag**, not a global change. Other rules keep
their single-Enter save; only this rule pays the extra keystroke, because only this rule is
silently unfalsifiable after the fact.

**Confirming an unchanged value is still a real act.** Per spec §5, the enrichment confirm is what
records `source=user` - the human establishment of the frame. When the marked winner equals the
stored declaration, the button must not read as a no-op:

    현재 선언과 같습니다 - 사람의 확정으로 기록합니다

---

## 3. Q3 - what the 8 candidates are called

### 3.1 The layout carries the two motions, so the label does not have to

The operator's hands do two things: **turn** and **flip**. `side` is the flip -
`coordinate_transformer.cell_to_physical:55-59` mirrors about `visual_cols-1`, which is a
left/right mirror. `rotation` mirrors about `visual_rows-1`. So the algebra already has one term
per motion; the merge risk is not in (rotation, side).

Rather than argue about the wording, **make the geometry of the control the geometry of the
motion**: two columns (the flip) by four rows (the turn).

```
        앞면 (좌우 그대로)        뒷면 (좌우 뒤집음)
          0°                       0°
         90°                      90°
        180°                     180°
        270°                     270°
```

There is no mental translation to pay because the operator's two motions are the two axes of the
grid they are pointing at. Reading down a column is turning; stepping across is flipping.

### 3.2 The actual Korean strings

Column headers (0.85rem, `--text-muted`):

    앞면 (좌우 그대로)
    뒷면 (좌우 뒤집음)

Candidate cells (1.05rem, weight 600, mono for the degree), with the stored value in mono at
0.8rem dimmed on the right of the same row:

    0°     rot0_front        90°    rot90_front
    90°    rot90_front       ...
    180°   rot180_front
    270°   rot270_front
    0°     rot0_back
    ...    rot270_back

The stored spelling is shown, always. It is what is written to the database and what every other
screen displays; hiding it would make this screen speak a private language that no one can
cross-check against a grid cell or an API response.

Badges on candidate rows:

    추천        (the marked winner - only when the margin clears config)
    현재 선언   (equals the stored declaration)

### 3.3 The operator's second unknown - inversion - handled in one line, not a third axis

The operator names rotation **and** inversion. Adding an inversion axis gives 16 candidates,
which round 1 forbids. The honest resolution is to say once, permanently, where the second
motion lives, instead of forcing the translation at every row.

One footnote under the grid (0.82rem, `--text-dim`):

    상하 뒤집기는 별도 후보가 아닙니다 - 180° 더 돌린 뒤 좌우 뒤집기와 같은 격자 변환입니다.

This is the operator's `반전` question answered in the place they will ask it, one time.

### 3.4 Same transform, different spelling - labelling only

Per the lead PM's correction, the section 2.1 delta does not materialize on the production path,
so this is a labelling question and carries no coordinate caveat. Rule:

- a candidate that equals the stored declaration under **any** spelling always carries `현재 선언`.
- if it is also the winner, the header line reads:

      현재 선언과 같습니다 - 표기만 다릅니다

No warning styling, no delta explanation, no second sentence. The failure mode being prevented
is one thing only: the operator reading a re-spelling as "it moved".

---

## 4. Q4 - the maps that cannot be scored, and the three states

**Scale, stated carefully.** Production has 668 map meta rows, 320 of them `auto_registered`
with synthetic `chip 1x1` geometry, and `map_overlay.py:518-523` already refuses to build a frame
transform for them. That is a **map count, not a worklist row count** - the worklist unit is
(dt_eqp, product) and one row pools many maps. **The row-level count is unmeasured.** I am
deliberately not moving 320 across that unit boundary.

Two design consequences follow from the map-level scale:

1. **This is not an error state.** Roughly half the map population lands here. Anything styled as
   an error on half a population trains the operator to ignore the styling, and then it also
   fails on the cases that are real.
2. **Pooling makes partial availability the normal case.** A single row may pool 12 maps of which
   5 are refused. So the state is not binary per row, and the screen must say the fraction.

### 4.1 The three states

| | 계산 중 | 채점함, 승자 없음 | 채점 못 함 |
|---|---|---|---|
| picture | frame skeleton + spinner (reuse `#reference-spinner`), no marks | **drawn** - floor + source + misses | **the source's own cells drawn alone, neutral gray, no floor** |
| numerals | **none, ever** | present | **none** - every count reads `미상` |
| headline | `후보 8개 채점 중...` | `이 기준으로는 구별되지 않습니다 - 후보 3개` | `기준이 없습니다 - 채점하지 않았습니다` |
| sub | (none) | the cause line, section 1.4 | **the server's own refusal sentence, verbatim** |
| candidates | listed, all inert | listed, none badged | listed, all inert |
| action offered | (none) | (none - it is a measured result) | `기준 선택` (pluggable reference, spec §4) |

The hard invariant that separates them:

> **A numeral is a claim. States (계산 중) and (채점 못 함) must never render a numeral in the
> agreement column** - not `0`, not `-`, not a grayed-out count. They render `미상`.

This is invariant I4 ("그럴듯한 기본값은 선언을 사칭한다") applied to the score column: a `0` in
an agreement column is indistinguishable from a measured zero, and a measured zero would be a
very loud fact.

Drawing the source's own cells in state 3 is honest, not decorative: we genuinely know where the
cells are; what we do not know is how they relate to anything. Showing them alone, with no floor
underneath, is the picture of exactly that.

### 4.2 The refusal sentence is not rewritten

`map_overlay.py:521-523` already produces a Korean sentence that names which map is at fault and
what to declare. It is passed through unchanged. Precedent: `GET /admin/config/resolve` -
the server makes the sentence, the client renders `detail` and does not judge for itself. A
second copy of this sentence in `enrichment.js` would be the two-spellings defect class (I6)
in its purest form.

### 4.3 Partial availability

Not a fourth state - a modifier on states 2 and 3, rendered on the panel meta line only:

    맵 12개 중 5개 제외 (규격 미선언) · 채점 528다이 · 340ms

---

## 5. Q5 - honest states, individually silent and named in aggregate

The rule already has an implementation in this exact screen, and it should be reused rather than
re-invented: `#blankkey-badge` (enrichment.html:776) plus the `partitionQueueRows` /
`blankKeyBoundaryIndex` sort (enrichment.js:225, 233). Rows that a human cannot resolve here are
counted in one header badge and **sunk below a boundary in the worklist**, so the Down arrow runs
through the answerable rows first and stops at a visible edge.

"No reference available" is structurally the same problem as "no decision key", so it gets the
same three mechanisms and no new ones:

| where | what | rule |
|---|---|---|
| **header badge** | `기준 없음 N건`, same `.stat-badge` family, `--warning` (not `--danger`; unlike a blank key this one is fixable by declaring geometry) | one badge, one count, never per row |
| **worklist order** | unscorable rows sink below a boundary, same as blank-key rows | the operator's Down key never wastes an action on one |
| **row decoration** | **none** | half the population must not be decorated |
| **contact point** | the sentence appears only when the row is selected, in panel [C] | named where it can be acted on |
| **panel meta line** | `맵 12개 중 5개 제외 (규격 미선언) · 채점 528다이 · 340ms` | the aggregate is stated once, always, never shouted |

**Vocabulary - reuse, do not grow synonyms:**

| condition | existing word | UI string |
|---|---|---|
| no usable reference at all | `align_unavailable` | `기준 없음` |
| geometry refused by the transform path | `mapping_unavailable` | `비교 불가` |
| a count we did not compute | `미상` | `미상` |
| the rule/field was never declared | `not_declared` | `선언 없음` |

**One typography defect this creates and must fix.** `.panel-meta` is 0.72rem (~11.5px,
enrichment.html:291-298). Under this design it becomes load-bearing - it carries the exclusion
count and the scored denominator. It must move to **0.82rem minimum**. Floor for this screen:
**nothing that carries a fact goes below 0.8rem.** Readability is function.

---

## 6. Items that are not mine - hand off to Client PM / server lens

I changed no logic and none of the below is a presentation change:

1. **A reference view whose payload is a scoring, not rows.** The `reference_views` contract is
   SQL-plus-`candidate_for` today (`enrichment_config.to_public_rule`). The picture needs
   `{floor_cells, source_cells, per_candidate: [{frame, agree, discriminating, margin}], excluded_maps, refusal_detail}`.
   Whether that arrives as a new reference-view kind or a sibling endpoint is a server call.
2. **All 8 scorings in ONE payload.** Section 2.2 - the 30-second bar dies without it.
3. **`align_scoring` config block** (`min_margin_dies`, `min_discriminating_dies`) and the
   per-rule `confirm_before_write` flag.
4. **Focus contract.** Arrow Up/Down must keep moving the worklist (existing muscle memory,
   `onInputKeydown` enrichment.js:505-511). Candidate selection therefore uses Tab/Space and
   mouse only - **no arrow keys** - and Enter accepts the marked winner. When nothing is marked,
   Enter must be inert with the hint `구별되지 않아 자동 선택이 없습니다 - 후보를 직접 고르세요`.
   Silent-Enter-does-nothing is worse than the hint.
5. **Canvas performance.** Draw with `transform`/`opacity` only for the swap transition; repaint
   the whole small canvas rather than per-cell style writes.

## 7. Measurement I could not make, flagged rather than guessed

- **Grid size per production map.** My 15 px/die figure uses the spec's 567-die figure. If real
  maps exceed ~50 dies per side the shape channel needs the flex rebalance in 1.2.
- **Maps per worklist row.** Needed to state honestly how many maps one confirmation covers.
- **How many worklist rows are unscorable.** 320 is a map count. Do not print it as a row count.

## 8. Proposed lesson for `agent_workspace/memory/ui-designer.md` (not added by me)

> **함정**: 점유율·적합도 같은 비율을 순위 근거로 화면에 올리면 분모가 사라진다.
> `일치 38 / 판별 40`과 `일치 512 / 판별 528`은 둘 다 95%지만 전자는 "근거가 40다이뿐"이라는
> 가장 중요한 사실을 말하고 있었다.
> **올바른 방법**: 판정을 뒤집을 수 있는 수치는 **분모를 붙인 절대 개수**로 낸다. 비율은
> 요약이지 근거가 아니다.
