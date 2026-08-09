# Living-docs maintenance cycle — 2026-08-08

Scope: SSOT, `docs/architecture/` (except `CODE_MAP.md`), `docs/guide/`, `docs/spec/`, `PRIMITIVES.md`.
Range: 57 commits since the last living-docs sync. Nothing committed — the lead PM commits after review.
`.claude/doc_sync_pending` left at 57, untouched.

---

## 0. What was already done by other lanes (measured, not assumed)

Before writing anything I checked which of the "substantive" commits in the brief were already
carried into living documents. Three of the four write-path items were:

| Commit | Already documented where | Badge |
|---|---|---|
| `4738d84` set-based write path, `ProbedIdentity` | `architecture/backend.md` §3 2-ter | 2026-08-07 |
| `528dfcb` outbox collapse, `uq_bk_*`, index census | `architecture/data_model.md` §3.1/§3.2 · `PRIMITIVES` §2 (two entries) · §6 OUTBOX-④ | 2026-08-07 |
| `818c9c0` blank key column writes nothing | `architecture/data_model.md` §3.1 area | 2026-08-07 |

So this cycle's real gap was the **aligner arc** (`069b4e9`..`34d2518`), the **client round**
(`e943e46`, `21209d7`, `c959368`, `15a2b39`), and the **deployment/ops surface** of D3 —
which was documented in `backend.md` (the *why*) but not in the docs an operator actually
opens before a deploy.

`34d2518`'s spec paragraph (`MAP_ALIGNMENT_SPEC` §6, "`no_winner`의 문장은 실제로 꺼진 축을
말한다") was **already in the working tree, uncommitted, written by the server lane.** I did not
touch it and edited only around it. ⚠️ **That file therefore has two authors' uncommitted work in
it right now** — if the server lane holds it in memory and rewrites it whole, my §2.4/§2.5 are lost.
Worth checking before commit.

---

## 1. Changes, file by file

### `docs/spec/MAP_ALIGNMENT_SPEC.md` — §2.4 and §2.5 new, header badge → 2026-08-08

**§2.4 「순번 축에서 거울 반쪽은 곧 우상단 시작 반쪽이다」** (`c4eaffa` + `c959368`, and the
board commit `db76be0` which states it most completely). This is the canonical fact the brief said
must be stated once and not re-derived, so it now has one home and everything else links to it.
Four things pinned in it:

1. `rotθ_back` + left-to-right ≡ `rotθ_front` + right-to-left on the index axis, no rotation shift.
2. **`back` here is a mirror, not a physical wafer side** — and the map editor one click away
   genuinely has a physical side (`currentSide`). Same spelling, different domain.
3. The start-corner axis landed as a primitive (`serpentine_index`/`serpentine_rank`,
   `left_to_right: bool = True`, rule ④) **and nothing searches it.** Candidate space is still
   4 rotations × 2 sides. Measured: `grep -n "def serpentine_index" server/map_alignment.py` → :1309,
   signature carries `left_to_right`; no scorer varies it.
4. It **replaces** the mirror half, it does not join it — adding it on top made every candidate tie
   with its twin, 10 tests red, and that red was correct.

Also recorded: the screen already says `우상단 시작` while **storage still holds `side: back`**,
because two attempts to write `front` were refused by the editor-redraw oracle (`80f5913` →
`51e4068`), and a single hand-edited row looking fine is not counter-evidence (that map's
`phys_offset_*` is zero and its rotation sits where the mismatch cancels).

**§2.5 「dt→core 축 — 부품 둘이 착지했고 아무도 부르지 않는다」** (`069b4e9`). Measured, not
transcribed: `grep -rn "index_group_count\|bin_fingerprint_shift" server/ --include=*.py` returns
the definitions, their own docstrings, and one comment in `seed_dt_index_walk.py` — **zero wiring.**
Also pinned: group minimisation ties structurally on the front/back mirror (a flip is `x → -x`, a
group boundary is a `y` event); the "88/88 vs 4/88" measurement is **not a refutation** and the
threshold-20 derivation resting on it must not be "corrected" away; and the support floor does not
fire at real bin cardinality, which must be settled before this axis is wired.

### `docs/architecture/PRIMITIVES.md` — 3 new entries, badge → 2026-08-08

- **§4 「순번 훑기의 시작 모서리는 *축*이다 — 거울 프레임으로 대신 말하지 마라」** — the reusable
  shape is "a fact about equipment deserves its own axis; a different axis that happens to produce
  the right coordinates produces the wrong meaning." Traps: replace-don't-add; a default that is
  byte-identical is how you land an axis without touching callers, and that is also why "the
  parameter exists" must not be read as "it is searched"; one word meaning two domains.
- **§4 「그룹 최소화만으로는 프레임을 못 짚는다」** — minimisation scores silently pass the axis
  they cannot split; support floors come before confident wrong answers; **two contradictory
  measurements in one file can read as a refutation when they are answers to different predicates**;
  two metrics describing one map must take their walk order from one helper.
- **§6 「쓰기 전 읽기 전용 사전점검」** (`b2ceb55`) — the shape is: session-enforced read-only
  (`SET SESSION default_transaction_read_only = on`, because "we say it is read-only" and "the
  session refuses" are different objects), answer three questions (scale / material / would filling
  it collide), and **never re-implement the canonical composer** — the script counts "does the same
  material already carry a key" instead, which is true independent of the composition rule.

### `docs/architecture/frontend.md` — §4.2 rewritten in part, module table re-measured, badge → 2026-08-08

- ✅ **Resolved a stale ⚠️**: the section said the `map_editor2.html` markup still carried two-step
  confirm wording and that the fix lived only in the working tree. Measured at HEAD: the markup says
  「쓰기는 한 동작(클릭 또는 Enter)」 and `Enter 확정`, and there is no `data-armed`. It landed.
- Added the **confirm gate change** (`21209d7`): the only gate is now `selectedId`. `not_scorable`
  and "rests on a guess" moved from *blocking* to *disclosing* — with the point that the state that
  most needed a human was the one state a human could not answer, and that the server
  (`frame_confirmation.accepted_ruling_states`) had always accepted all three.
- Added the **candidate labels** (`c959368`) with a pointer to §2.4 rather than a second copy of the
  derivation, plus the rule that the stored spelling stays visible in mono.
- Added the **per-table worklist** (`e943e46`): `map_table` is required by the route, the measured
  failure of not re-asking is *two tables on one screen* (populations 191/160/97/96/1 vs 40/40/20/20/6),
  supersession is one `AbortController` in the shape `value_suggest.js` already uses, and **an abort
  is not a failure**. Also that the `기준` select was deliberately left alone — symmetry is not a reason.
- Added **cell copy** to the `enrichment.js` row (`15a2b39`): AG-Grid blocks cell text selection by
  default (that was the cause, not the clipboard); it is the browser's copy, not range copy
  (Enterprise); and not calling `clipboard.js` is the design, because that module imports
  `grid.js`/`state.js`/`dom.js`/`ui.js`.
- **Module table line counts re-measured** (the table was last re-measured 2026-08-04 and its own
  header says the column is for relative scale, so drift matters when it is large):
  `enrichment.js` 788 → **1266**, `map_editor.js` 9683 → **11060**, `config.js` 5 → **113**,
  `websocket.js` 350 → **488**, `map2` 17 files/7,260 → **18 files/9,877**, plus `main.js` 2042→2047,
  `state.js` 130→162, `ui.js` 426→431, `admin.js` 3704→3708. The rest matched.

### `docs/guide/POSTGRES_OPERATIONS_GUIDE.md` — new pre-flight section, badge → 2026-08-08

- 🔴 **The badge was stale and the body was not.** `cc602ed` added both D3 sections
  (`uq_bk_<table>` and `--drop-redundant`) while `Last-verified` stayed at 2026-07-31. Recorded the
  correction *and* why it matters (a body ahead of its badge is a body nobody reads).
- Added **「업무 키가 안 조립된 행 — 읽기 전용 사전점검」** for `check_missing_business_key.py`,
  and drew the boundary explicitly: the unique index blocks keys that *collide*, this tool finds rows
  with *no key at all*. Includes the "who lives is a human decision, and `audit_logs`/`cell_sources`
  attribution follows that choice" caveat.

### `docs/guide/DEPLOY_SETUP.md` — new step 8-bis, badge → 2026-08-08

The brief said: if any deployment doc describes the write path, the "DO NOT DEPLOY WITHOUT D3"
constraint must appear there. It did not. §6 순서 요약 now has **8-bis**: apply the business-key
UNIQUE index, with the reason stated as the commit stated it (the race window widened from
microseconds to a measured 2.4s; P3 removed the last *accidental* guard from a path never protected
by design; the index closes it for pre-P3 code too).

🔴 **Measured caveat added, because it would have been the natural wrong assumption**: step 8's
`--preflight-only` does **not** catch this. `server/schema_drift.py` contains zero index checks
(`grep -n "index\|Index" server/schema_drift.py` → no output); it compares columns. "The pre-flight
was green" says nothing about this index.

### `docs/guide/config/map_overlay_config.md` — 3 config keys registered, badge → 2026-08-08

Three keys under `alignment` had loaders, warning paths, and real behavioural consequences, and
**were in no document's key reference**:

- `alignment.index.*` — the index axis thresholds. Deliberately not sharing keys with the occupancy
  thresholds; undeclared or half-declared means the axis reports numbers but takes no ranking.
  ⚠️ Added the caveat the config's own `__derivation` carries: the shipped 20/20 was derived from
  **this box's synthetic seed** (`seed_dt_index_walk.py`, `SYN-IDX-*`), not from production.
- `alignment.value_weights` — `0` is a declaration and a missing key is not.
- `alignment.sides[]` — undeclared means **both**, and narrowing to `["front"]` deletes the correct
  answers for top-right-numbering equipment outright (which is what happened). Measured at HEAD:
  the live `server/config/map_overlay_config.json` declares `index` and the two top-level thresholds
  and **no `sides`, no `value_weights`**.

### `docs/README.md` — one row extended

The Map Alignment row now points at §2.4 and §2.5 with the one-line canonical fact, so the
"mirror = top-right" statement is findable from the index without opening the 1,000-line spec.

---

## 2. Disagreements found and deliberately NOT resolved

These are rulings, not edits.

1. **`dt_log` carries its own `core_x`/`core_y`, so the aligner scores the wrong columns.**
   Diagnosed and explicitly not fixed by `e943e46`: `resolveQuestion` keeps the carried pick instead
   of adopting the declared binding, so `/view` goes out with `x_col=core_x` **against `dt_log`**.
   The commit says it "changes what gets scored and wants its own ruling." The code looks wrong here,
   not the document — I did not write it into the spec as behaviour because writing it down as
   behaviour would legitimise it.

2. **Storage still says `side: back` while every human-facing surface says `우상단 시작`.**
   Two attempts to make storage agree were refused by the oracle, and the real repair (a separate
   slot for the mirror, touching `_side_of`, `_frame_phys_params`, the editor and the overlay) is a
   round nobody has scheduled. Until then **the database and the screen use the same column to mean
   two different things**, and a reader who trusts the stored spelling will conclude a physical back
   side was measured. I documented the state; deciding when to pay for the fix is the lead PM's.

3. **The index-axis threshold shipped in production config was derived from synthetic data.**
   `alignment.index.min_*` = 20/20, and the config's own `__derivation` says it came from
   `seed_dt_index_walk.py`'s `SYN-IDX-*` units on this box and must be re-derived before being taken
   to production. It has not been. This is a live config value standing on a measurement that its own
   comment disclaims. Not mine to change.

4. **`index_group_count` / `bin_fingerprint_shift` are shipped code with zero callers, and one of
   their preconditions is known-unmet** (the support floor does not fire at real bin cardinality).
   Whether that is "landed early on purpose" or "a half-finished axis sitting in the tree" is a call
   I cannot make from the source. I documented it as unwired with the blocker named.

5. **`DEPLOY_SETUP.md`'s ~5,000-character folded changelog in the header** still violates
   CONTRIBUTING §3 ("`Last-verified` is a date"). A previous doc-keeper round flagged it as awaiting
   lead-PM judgement (whether `docs/history/` carries it all). It is still awaiting. I added this
   round above it rather than resolving it.

6. **`api.js`'s `worklist` comment still says "STILL UNSERVED ... null until the server lane ships
   the route"** while the same file fills the value and the server serves it. `frontend.md` §4.2
   already flags this and routes it to the lead PM. Still true at HEAD. Code, so out of my scope.

---

## 3. Deliberately left alone

- **`docs/architecture/CODE_MAP.md`** — code-mapper owns it this round. I have an anchor observation
  for them regardless: `serpentine_index` is at `server/map_alignment.py:1309`, `serpentine_rank` at
  :1355, `index_group_count` at :1645, `bin_fingerprint_shift` at :1718, `compose_refusal` at :4340,
  `load_alignment_sides` at :80.
- **`docs/history/**`** — doc-historian. **`docs/process/PROJECT_STATUS.md`** — lead PM only; read for
  context, not edited. **`server/map_alignment.py` / `test_map_alignment.py`** — server lane, read-only,
  and I only grepped them.
- **`docs/process/DOC_OWNERSHIP.md`** — no new documents or contracts were created this round, so no
  new ownership rows are required. I did not add a round note because I added no rows. ⚠️ If the lead
  PM wants `server/scripts/check_missing_business_key.py` to have a named owner row, the natural home
  is the data-model / business-key row alongside `add_business_key_unique_index.py`.
- **Compliance audit** — doc-auditor's job since the 2026-07-27 split. The disagreements in §2 are
  ones I hit while working, not ones I went looking for. I did not grade documents or recommend
  archives.
- **SSOT (`SYSTEM_OVERVIEW.md`)** — nothing in these 57 commits changed process topology, the model
  inventory, or a boundary contract. The write-path change is a mechanism inside one process and
  belongs in `backend.md`, where it already is. Left untouched deliberately rather than by omission.

---

## 4. Proposed lessons for `agent_workspace/memory/doc-keeper.md` (not added — proposal only)

1. **함정**: 「직전 정비 이후 N커밋」을 받으면 그 N개가 전부 미문서화라고 가정하게 된다 — 이번엔
   57개 중 write-path 3건이 이미 `backend.md`·`data_model.md`·`PRIMITIVES`에 **완전히** 들어와 있었고,
   그대로 썼다면 같은 사실의 두 번째 사본을 만들 뻔했다.
   **올바른 방법**: 착수 시 **소유 문서의 `Last-verified`를 먼저 정렬**해 보고, 지시서의 커밋 목록과
   대조해 「이미 처리된 것」을 먼저 뺀다. 배지가 커밋보다 나중이면 그 커밋은 이미 반영된 것이다.

2. **함정**: 그 역도 성립한다 — **본문은 갱신됐는데 배지만 안 갱신된 문서**가 있고, 그것은
   「미반영」과 구별되지 않는다(`POSTGRES_OPERATIONS_GUIDE`가 이번에 정확히 그랬다: D3 두 절이
   본문에 있는데 날짜가 2026-07-31).
   **올바른 방법**: 배지 날짜로 후보를 좁히되 **본문을 grep해 확인한 뒤에** 「미반영」이라고 판정한다.

3. **함정**: 「사실이 이미 어딘가 적혀 있다」와 「그 사실을 찾을 사람이 있는 자리에 적혀 있다」는 다른
   진술이다. D3의 배포 제약은 `backend.md`에 **완전히** 서술돼 있었는데, 배포하는 사람이 여는 문서
   (`DEPLOY_SETUP` 순서 요약)에는 한 줄도 없었다.
   **올바른 방법**: 제약을 만나면 「어느 문서에 적혀 있나」가 아니라 **「그것을 어길 사람이 그 순간
   무엇을 읽고 있나」**를 묻는다.
