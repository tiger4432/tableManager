# DocAudit — M2.6 documentation round (doc-historian / code-mapper / doc-keeper)

**Agent:** doc-auditor · **Date:** 2026-07-27
**Ground truth:** `git show 0f8d35f` **and the current working tree.** The tree is ahead by two
rounds (contract 161 → 185 → **110** assertions; `server/transfer_plan.py` gained `_band_seq`,
`_band_materials`, and refusal behaviour in `_parse_bands`). **Judged against the tree**, because
the tree is what gets committed next. Where a claim was true at `0f8d35f` and is false in the
tree, that is stated explicitly — the distinction changes who owns the fix.

**Nothing was modified.** No docs, no code, no config, no commits.

---

## VERDICT: 조건부 (conditional)

The three agents' *own* claims are almost all true and I verified the load-bearing ones by
running them. What is wrong is what landed **after** they finished: six statements across
`PRIMITIVES.md` and `CODE_MAP.md` are now false, and two of them teach the design the user
rejected. One finding (F1) was wrong when it was written, not merely overtaken.

`CODE_MAP §0`, the self-verifying tombstone section, **verifies** — I ran all four commands.
`MAP_EDITOR_SPEC §6.3` **is fixed**. Client anchors **are** re-measured correctly.

---

## Findings, ranked by consequence

### F1 — `PRIMITIVES.md:27` points at the wrong file. Wrong when written.

```
- **어디**: `client2/src/transfer_plan.js`의 `normalizeBands` — ...
```

`normalizeBands` is declared at **`client2/src/map_editor.js:214`**. It is not in
`transfer_plan.js` at all; that file's only occurrence is a *comment* at `transfer_plan.js:215`
which itself correctly says "map_editor의 `normalizeBands`".

Verified by running: `grep -rn "function normalizeBands" client2/src/` → one hit, `map_editor.js:214`.

Why this one is worst:
- `PRIMITIVES.md` is loaded on **every dispatch**. This is the highest-traffic wrong anchor in the tree.
- The entry's own instruction is *"그 필드의 두 번째 파싱이 어디 있는지 **grep**하라."* An agent
  who follows that instruction using the anchor the entry supplies finds nothing but a comment.
- `CODE_MAP.md:621` and `:671` both get the file **right**. The two most-read documents contradict
  each other on the location of the same function.

This is not a moving-target failure — `normalizeBands` has been in `map_editor.js` the whole time.

### F2 — `CODE_MAP.md:572` has the wrong signature *and* teaches the rejected mirror.

```
| **`_parse_bands(raw) -> (밴드[], 읽었는가)`** | ... 객체 아닌 원소는 **버리고 나머지로 계속**
  유도(클라 `normalizeBands`와 동일) ... | ~1119 |
```

Tree, `server/transfer_plan.py:1153`:

```python
    return _assign_band_seqs(kept), True, len(parsed) - len(kept)
```

A **3-tuple**. The third element is a refusal count, and `validate_plan` (tree `:1474–1483`)
turns a non-zero count into a `layer_range_invalid` warning with `reason: "not_a_band"` and a
`dropped` field, which downgrades the plan. The caller destructures three names:
`bands, readable, dropped = _parse_bands(...)` (`:1471`).

Two independent defects in one cell:

1. **Signature.** `CODE_MAP.md:12` declares *"라인은 보조 식별자이고 **함수명·시그니처가 1차
   식별자**다."* This is the primary identifier being wrong.
2. **"클라 `normalizeBands`와 동일"** is the rejected design, stated as fact. The function's own
   docstring (`:1126–1132`) says the opposite in as many words: *"[객체가 아닌 원소는 **거부**한다
   — 총괄 결정 2026-07-27] ... (클라는 `typeof [] === 'object'`라 중첩 배열을 빈 구간으로 살려
   둔다. 그리드로만 들어올 수 있는 입력이라 일치시킬 대상이 없고, **서버는 거부하는 쪽이 옳다**.)"*

**Correct at `0f8d35f`.** I checked: the commit's version ends `return _assign_band_seqs([...]), True`
— a 2-tuple, with drop-and-continue semantics. code-mapper documented it accurately; the second
post-commit round inverted the behaviour.

### F3 — `CODE_MAP.md:556` enumerates 3 `reason` values; the tree has 4.

The cell says `layer_range_invalid` *"`reason`을 나른다: `unreadable`|`incomplete`|`not_increasing`"*.

Verified by `grep -n '"reason":' server/transfer_plan.py`:

| revision | reason values |
|---|---|
| `0f8d35f` | `unreadable` (:1423) · `incomplete` (:1521) · `not_increasing` (:1531) — **3** |
| tree | **`not_a_band` (:1479)** · `unreadable` (:1501) · `incomplete` (:1599) · `not_increasing` (:1609) — **4** |

This is the `WARN_*` "14종" trap one level down: the *outer* count is still right, the *inner*
enumeration is not. A consumer switching on `reason` — and the history entry at `:167` explicitly
flags that a future client must render this field — will not handle `not_a_band`.

*(I checked the outer claim too. `WARN_*` **14종** is correct: `grep -n "^WARN_[A-Z_]* = "` yields
14, and all 14 names match the doc's list element for element. `painted_unavailable` in,
`layer_coverage_gap` out. Membership verified, not just the count.)*

### F4 — `CODE_MAP` server anchors drifted +65…+78 in the tree; two new functions unmapped.

Measured both revisions directly:

| symbol | CODE_MAP | `0f8d35f` | tree | tree drift |
|---|---|---|---|---|
| `_parse_bands` | ~1119 | 1119 | 1119 | 0 |
| `_assign_band_seqs` | ~1151 | 1151 | 1217 | **+66** |
| `BAND_TO_OK/BLANK/INVALID` | ~1181–1183 | 1181 | 1246 | **+65** |
| `_band_to` | ~1188 | 1188 | 1253 | **+65** |
| `_prev_to` | ~1228 | 1228 | 1293 | **+65** |
| `_material_identity_rule` | ~1241 | 1241 | 1306 | **+65** |
| `_split_material` | ~1260 | 1260 | 1325 | **+65** |
| `validate_plan` | ~1343 | 1343 | 1408 | **+65** |
| `_reg_get` | ~1392 | 1392 | 1457 | **+65** |
| `painted_reliable` | ~1414 | 1414 | 1492 | **+78** |
| `_get_summary` | ~1464 | 1464 | 1542 | **+78** |

**At `0f8d35f` every one is exact.** code-mapper's "zero drift" claim is verified true for the
revision it measured. All tree values exceed the ±20 tolerance CODE_MAP declares at `:8`.

The worst instance is not the size of the drift but a coincidence: **`_band_materials` now sits at
line 1188**, which is exactly CODE_MAP `:574`'s anchor for `_band_to`. An agent following the map
to the `to` classifier lands on a real function — the wrong one. That is the "plausible but wrong
anchor" failure my memory file records, arriving by accident rather than by carelessness.

`_band_seq` (`:1156`) and `_band_materials` (`:1188`) are **absent from CODE_MAP entirely** — two
new module-level functions, one of which (`_band_seq`) is the seq classifier the contract tests.

### F5 — `PRIMITIVES.md:158` offers a resolution the harness now rejects, for a case that no longer occurs.

The bullet gives three ways to handle a vector the wire cannot carry, ③ being *"채점에서 빼되
**보고**하고, 표현 가능해지면 자동으로 다시 채점되게 둔다."*

`contracts/band_arithmetic/client_harness.mjs:253–257`:

```js
// An unscored vector FAILS the run. ... Ambiguity is a defect in the vector file (restate the
// input so both sides parse it exactly), not a licence to drop the assertion.
process.exit(failures.length || unrepresentable.length ? 1 : 0);
```

Unrepresentable ⇒ **exit 1**. The artifact classifies option ③ as a defect; the doc offers it as
one of three acceptable choices.

Further: after the shrink the case has **no live instance**. All six `to_cases` carry distinct
`band` inputs, so the derived ambiguity detector (`:109–130`) can never fire. I ran the harness:
`compared: 110 assertions / MATCHES`, with no `NOT COMPARED` block. And `2.0` — the bullet's other
worked example — is not in the contract at all; `normalization_cases` was reduced to one
`invalid_seq_types_fall_back_to_position` vector using `"abc"`, `0`, `-4`.

The resolution actually taken was option ①: `over_max_layer` restated as the decimal string
`"9007199254740993"` (`vectors.json:62`).

### F6 — `PRIMITIVES.md` §6 omits the principle the round actually settled on. (Omission, weighted by traffic.)

The reason the contract went 185 → 110 is written down in three places:

- `vectors.json:12–25` — *"WHY `to_cases` IS SHORT, AND WHY IT MUST STAY SHORT (2026-07-27)…
  the server needs ONE rule, not a mirror… Enumerating more of that class buys agreement on
  garbage and costs a table nobody can keep true."*
- `vectors.json:215` — the `materials_cases` `$comment`, same argument for element types.
- `transfer_plan.py:1195–1201` — *"…그리드 입력에 대한 옳은 답은 '클라와 같은 방식으로 잘못
  읽기'가 아니라 **'읽을 수 없다'**이다."*

None of it is in `PRIMITIVES.md`. §6 carries the adjacent-but-different rule (*don't port the other
side's coercion*) and, in trap ②, the narrower *"못 움직이는 쪽에 움직일 수 있는 쪽을 맞춘다"* —
which is still true of `_band_seq`, but is the only sizing guidance the every-dispatch document
gives, and it points **toward** matching the client.

An agent who reads §6 to decide how large to make the next cross-implementation contract gets no
signal to keep it small. This is the same shape as the earlier cycle where `PRIMITIVES` taught a
retry design the code had abandoned — except here the doc is not false, it is silent on the axis
that was actually decided. Silence in the every-dispatch catalogue is how the table gets rebuilt.

### F7 — `DOE_STORAGE_MAP.md:15` asserts a perishable runtime state in a Living doc.

> ⚠️ **남은 것은 웹서버 재기동 하나입니다.** … **`GET /api/transfer-plan/validate`가 현재 404**입니다(`plan_store.doe unresolved`).

The diagnosis is right — I confirmed `plan_store.doe unresolved` is verbatim the old code's message
(`git show 0f8d35f^:server/transfer_plan.py:1166`). The problem is the tense. "현재 404" expires on
the next restart with nothing to invalidate it, and **nothing is listening now** (checked
:8000/:8001/:5173/:3000 — no listener), so the sentence is already unverifiable.

The same fact is stated correctly elsewhere and those are **not** defects:
`PROJECT_STATUS.md:11` (a board to-do, lead-owned), the history entry (a record, past tense),
`DEPLOY_SETUP.md §7` and `PRODUCTION_READINESS.md B4` (both past tense, as case studies).
Only the Living spec states it in the present.

### F8 — `CODE_MAP.md:620/621` file sizes stale.

`vectors.json` "(218줄)" → **237**; `client_harness.mjs` "(~220줄)" → **257**. Both were exact at
`0f8d35f` (`git show … | wc -l` = 218 / 220). The 237 is inside the ±20 tolerance; the 257 is not.

### F9 — The history entry's "다음 단계" recommends the reversed work.

`docs/history/20260727_114542_…:180–181`:

> `seq` 타입 축(`"2"`·`true`)은 벡터 추가로 닫히고, `2.0`은 닫히지 않는다 — **벡터 파일에 "여기는 고정할 수 없다"를 남기는 편이 낫다.**

That is the `$known_divergences` block, which was added and then **removed** on user instruction.
`vectors.json:203` now says the opposite in the file itself: *"Do not expand this into a type
table."* Line `:137` of the same entry frames the seq-type axis as "아직 열려 있다", which the
contract has since deliberately closed by declining to cover it.

The **body** of a history entry is a record and must not be rewritten. But a forward-looking
"다음 단계" that survives a reversal reads as an instruction to redo undone work, and history is
indexed and linked. Recommend either (a) the historian's charter drop forward-looking
recommendations, or (b) an append-only superseding note — the record stays intact either way.

### F10 — `docs/README.md:17` grades an executed plan as Living; one genuine dead link.

`docs/README.md:17` lists `DOC_AUDIT.md` as 🟢 Living. The file's own header says
`Status: ✅ Executed (2026-07-24 — P1~P5 반영 완료)`. It has no read trigger and is already on the
board's archive list (`PROJECT_STATUS` queue #5 ⓑ).

`docs/DOC_AUDIT.md:173` contains the **only** genuine dead relative link in the tree:
`../overview/SYSTEM_OVERVIEW.md` — from `docs/`, that resolves outside the repo. Should be
`./overview/…`.

---

## Attempted but safe — what I suspected and why it survived

Ranked by how much of the verdict rests on it. Everything below marked **(ran)** was executed, not
reasoned about.

1. **CODE_MAP §0's self-verifying commands — the section is the point, so I ran all four. (ran)**
   ① and ② return **zero hits** at `0f8d35f` *and* against the working tree. ③ returns **exactly
   three** hits, at exactly the three cited lines (`transfer_plan.js:1174`,
   `test_transfer_plan.py:1094`, `transfer_plan.py:126`) — and all three still hold in the tree
   even after `transfer_plan.py` gained 131 lines, because the additions are all below line 126.
   ④ returns only tombstone-context hits. **This section does what it claims.**
   One design limit worth naming, not a defect today: the commands are pinned to `0f8d35f`, so the
   section cannot re-verify itself against a later tree. F2/F3/F4 are precisely the class it would
   have caught had it been pinned to `HEAD`.

2. **Item 4 — `MAP_EDITOR_SPEC §6.3`. Confirmed fixed, and nothing else teaches the dead API. (ran)**
   `pruneScoped` / `serverKeys` / `doeServerLoaded` / `adoptServerDoe`: **zero hits** in
   `client2/src`. Every replacement claim in §6.3 verifies against source:
   `legendReplaceScope = {table, mapKey, fingerprint}` (`map_editor.js:2355`); refuse-not-downgrade
   on fingerprint mismatch (`:2362–2364` → `legendConflict`); erasure on load / read failure /
   frame entry (`:3144`, `:3164`, `:4064`, `:4120`); truncation-is-not-a-read (`readRegistryScope`
   `:2252` wrapping a throwing `fetchLegendFromServer`).
   Remaining doc hits for the dead names are all legitimate: `CODE_MAP §0` (tombstone),
   `DOE_STORAGE_MAP:123` (describes the removal), and two history entries scoped to their commits.

3. **Contract assertion counts. (ran)** Harness on the tree: **110 assertions, MATCHES, exit 0**.
   I then rebuilt the `0f8d35f` harness + vectors in a scratch tree against the (unmodified)
   `client2/src` and got **161** — exactly the number the history entry claims at `:146`. That
   claim is honest and reproducible.

4. **`WARN_*` 14종 — the memory-file trap, so I enumerated instead of counting. (ran)** 14
   constants, and the doc's 14 names match the code's set element for element. Verified as a set.

5. **Client-side CODE_MAP anchors — the prior cycle's +145…308 drift. (ran)** Sampled 13:
   `parseJsonCol` 208 · `normalizeBands` 214 · `normalizeKnobs` 247 · `knobsToObject` 259 ·
   `serializeBands` 268 · `normalizeLegendItem` 275 · `cloneLegend` 288 · `bandToState` 186
   (+ its `export` at 220, cited separately and also correct) · `splitMaterialId` 298 ·
   `fetchLegendFromServer` 2233 · `readRegistryScope` 2252 · `applyRegistryRowsToLegend` 2264 ·
   `saveLegendToServer` 2333. **All 13 exact.** Genuinely fixed.

6. **Suite and index. (ran)** `pytest server/tests -q` → **608 passed** on the tree. History claims
   602 at `0f8d35f`; `test_transfer_plan.py` went 78 → 84 test functions (+6) and the suite total
   moved +6 — consistent. *I did not check out the commit to confirm 602 directly.*
   `gen_index.py --check` → exit 0, "up to date"; README says **220** and there are **220** entry
   files (221 `.md` minus README). Verified.

7. **`CONFIG_GUIDE §5.8` vs the real `.sample`. (ran)** The excerpt matches
   `server/config/transfer_plan_config.json.sample:72–85` on roles and columns. The load-bearing
   claims verify in code: `REGISTRY_ROLES` includes `bands` (`:115`) → `_resolve(required=…)` →
   `LookupError` (`:1423`) → 404, so *"`bands` 역할이 빠지면 404"* is true; `material_identity`
   미선언 → `missing` (`:258`) and the `source_unresolved` detail string (`:1665`).

8. **`backend.md:124`.** *"`plan_store.registry`(필수 역할키 `bands` 포함) 미구성만 404"* — the only
   `LookupError` in `validate_plan` is that one. True.

9. **`PRIMITIVES.md:55` — "양쪽 다 적용됨".** `splitMaterialId` (`transfer_plan.js:298–306`)
   returns `{lot: null, slot: null}` for no-separator and for either side empty. The `("ABC","")`
   fallback is gone. The parenthetical *"클라는 아직 `lastIndexOf('_')`를 하드코딩"* is also true
   (`:300`). This entry is accurate on both halves.

10. **`frontend.md` "쓰기 소유권". (ran)** *"`transfer_plan.js`는 서버에 쓰지 않습니다"* — zero
    `PUT`/`POST`/`data/updates` occurrences in that file. The sole registry writer is
    `map_editor.js:2371`. True.

11. **Dead links. (ran)** 600 relative links checked across all non-history docs. One genuine break
    (F10). The other 35 flagged are `file:///c:/…` absolute URIs whose targets all exist
    (spot-checked `.agents/skills/StableDevelopmentProtocol/SKILL.md`) — a portability smell,
    pre-existing, out of scope for this round.

12. **The other count claim in the touched docs — overlay "실패 status 4종".** Code gives
    `meta_unavailable` · `binding_unavailable` · `align_unavailable` · `no_data`, and
    `FEATURE_CHECKLIST` names all four **and** adds *"+ IO 실패는 일반 `error`"*. That is exactly the
    shape the "실패 상태 6종" case got wrong; here it is right. No finding.

**Adjacent observation (code, not docs — out of my remit to fix, flagging only):**
`transfer_plan.py:1172` ends `_band_seq`'s docstring with *"…계약이 **의도적으로 고정하지 않은
꼬리**이며, 묶으려면 양쪽 동시 변경이 필요하다(**벡터 파일 주석 참조**)."* After the shrink,
`vectors.json` no longer carries a comment about the seq `>2^53` / float tail — the `$known_divergences`
block that would have held it was removed. The pointer dangles.

---

## Read-trigger grading

**Re-measured (ran):** 62 `.md` under `docs/` excluding history · 13 already in `docs/_archive/`
· **49 live**, of which **18** are named in a `.claude/agents/*.md` charter. **Identical to the
prior audit's 18/49** — the ratio has not moved, and the board's queue #5 ⓑ (7 archives, 49→42)
is still pending.

Grading the 15 files touched this round:

| Doc | Grade | Trigger | Action |
|---|---|---|---|
| `architecture/PRIMITIVES.md` | **A** | charter — every dispatch | keep; **F1/F5/F6 first** |
| `architecture/CODE_MAP.md` | **A** | charter — every dispatch | keep; **F2/F3/F4** |
| `architecture/backend.md` | **A** | charter | keep — verified clean |
| `architecture/frontend.md` | **A** | charter | keep — verified clean |
| `architecture/data_model.md` | **A** | charter | keep — verified clean |
| `spec/MAP_EDITOR_SPEC.md` | **A** | charter | keep — §6.3 verified fixed |
| `process/DOC_OWNERSHIP.md` | **A** | charter | keep |
| `process/PROJECT_STATUS.md` | **A** | charter | keep (lead-owned) |
| `README.md` | **A** | charter | keep; fix F10 grade |
| `spec/DOE_STORAGE_MAP.md` | **A→B** | charter, but body is 🗄️ superseded | keep for legacy reads; **F7** |
| `guide/CONFIG_GUIDE.md` | **B** | config work | keep — verified against `.sample` |
| `guide/DEPLOY_SETUP.md` | **B** | deploy | keep |
| `process/PRODUCTION_READINESS.md` | **B** | prod gate | keep |
| `qa/FEATURE_CHECKLIST.md` | **B** | pre-release QA | keep — §2 rewrite is good |
| `history/…114542….md` + index | **B** | incident lookup | keep; **F9** on 다음 단계 only |

**Archive recommendation (decision is the lead's):** `docs/DOC_AUDIT.md` — **C**. An executed
2026-07-24 plan, no trigger, mis-graded 🟢, and carrying the tree's only dead relative link.
Already item ⓑ on the board's queue; this audit is a second, independent vote for it.

Two structural notes on grading, offered rather than asserted:

- `DOE_STORAGE_MAP.md` is graded 🗄️ in `README.md:40` but lives in `docs/spec/`, not `docs/_archive/`,
  which breaks `DOC_AUDIT` governance rule #5. The doc's stated reason (needed to read legacy
  `map_doe` rows until the physical DROP is approved) is a defensible exception — but the exception
  should be written down, or the next audit will re-raise it.
- `CONFIG_GUIDE`, `DEPLOY_SETUP`, `PRODUCTION_READINESS` and `FEATURE_CHECKLIST` are all **B by
  real trigger and A by content quality**, yet none is named in any charter. They are not at risk
  of rot from disuse by *humans*; they are at risk of not being loaded by *agents* who need them.
  That is a charter gap, not a document gap.

---

## Proposed lessons (for `agent_workspace/memory/`, lead to approve — not written by me)

**doc-auditor**
- 함정: 문서가 최신 커밋에 대해 **정확한** 것을 확인하고 통과시킨다. 검수 시점의 워킹트리는
  그 커밋보다 앞서 있을 수 있고, 실제로 **문서를 쓴 뒤 설계 결정이 뒤집힌** 사례가 이 라운드에
  둘 있었다(`_parse_bands` 2-tuple → 3-tuple, `reason` 3종 → 4종). 둘 다 커밋 시점에는 옳았다.
  올바른 방법: 앵커·시그니처·열거는 **두 리비전 모두에서** 측정하고, 표에 둘 다 적어라. "커밋
  기준 정확"과 "다음 커밋 기준 정확"은 다른 판정이며, 고칠 사람이 다르다.

**code-mapper** (제안 — 해당 에이전트 파일은 총괄이 반영)
- 함정: 자기 검증 절(§0)의 grep을 **측정한 커밋에 고정**하면, 그 절은 다음 트리에 대해 자신을
  검사하지 못한다. 이 라운드의 F2·F3·F4가 정확히 그 절이 잡았어야 할 부류다.
  올바른 방법: 묘비 검사는 커밋 고정, **현행 앵커·시그니처 검사는 워킹트리 기준**으로 한 줄씩
  같이 실을 것.

**doc-historian** (제안)
- 함정: "다음 단계"에 적은 권고가 뒤집혀도 **본문은 append-only라 고칠 수 없다**. 기록은 남아야
  하지만 권고는 지시로 읽힌다(`$known_divergences`를 남기라는 권고가 그것이 제거된 뒤에도 남았다).
  올바른 방법: 히스토리 항목은 **일어난 일만** 쓰고 전망을 쓰지 않거나, 뒤집힌 경우 **추가 노트로
  덧붙여** 기록을 보존하면서 무효화하라.

**doc-keeper** (제안)
- 함정: 프리미티브의 `**어디**` 필드는 서술이 아니라 **앵커**다. `PRIMITIVES.md:27`은 파일을
  틀렸고, 같은 항목이 "grep하라"고 지시하고 있었다.
  올바른 방법: `**어디**`에 파일 경로를 쓸 때는 **선언부를 grep해 확인**하라 — 언급(주석)과
  선언은 같은 문자열을 낸다.
