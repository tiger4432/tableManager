# Client — band arithmetic contract conformance (M2.6 `map_split_registry.bands`)

**Agent:** map-pm · **Date:** 2026-07-27 · **Scope:** client side of the shared band-arithmetic
contract. Server side untouched.

## Result

| | before | after |
|---|---|---|
| harness verdict | 27 divergences (exit 1) | **0 divergences, MATCHES (exit 0)** |
| assertions compared | 111 | **155** |
| `to_cases` | 10 divergences | 0 |
| `sequence` | 11 divergences | 0 |
| `material_split` | 6 divergences | 0 |
| `normalization` | 0 | 0 |
| `normalize_roundtrip` (new, derived) | did not exist | 0 (46 assertions) |

`vectors.json` was **not modified**. One vector pair is unsatisfiable on the client for a
reason that is not a client defect — see [Vectors I believe are wrong](#vectors-i-believe-are-wrong).

Run: `node contracts/band_arithmetic/client_harness.mjs`

## Files changed

- `C:\Users\kk980\Developments\assyManager\client2\src\transfer_plan.js`
- `C:\Users\kk980\Developments\assyManager\client2\src\map_editor.js`
- `C:\Users\kk980\Developments\assyManager\client2\src\transfer_plan.css`
- `C:\Users\kk980\Developments\assyManager\contracts\band_arithmetic\client_harness.mjs`
- `client2/dist/**` (rebuilt via `npm run build`; new hashed assets contain the change)

## What changed

### 1. One `to` classifier, three states — `bandToState`

`bandTo` was `Number()` + `Number.isFinite` + `Math.trunc`. Replaced by `bandToState(b) ->
{value, state}` with `state ∈ {blank, ok, invalid}`, and `bandTo` is now a one-line wrapper
over it. There is exactly one place in the client that decides what a `to` means.

The structural point is not the coercion table, it is that **blank and invalid are both
`value: null`**, so `prevTo`'s existing "skip nulls" walk becomes the contract for free. The
old bug was never in `prevTo`: `Number("  ") === 0` made a blank band return a *number*,
which **stopped** the walk. `prevTo` and `bandLayers` were still rewritten to branch on
`state === 'ok'` so they mirror the server's `_prev_to` line for line and do not silently
depend on "null means not-ok".

The 2^53 bound is enforced exactly on the string path with `BigInt`, not `Number`:
`Number("9007199254740993")` folds to 2^53 *before* any comparison runs, so a `Number`-based
guard would pass an out-of-range value. Numbers use `Math.abs(raw) > MAX_LAYER`.

Constants and the integer regex live **inside** the function on purpose: the harness slices
out the function body and evaluates it alone, so a rule hoisted to module scope would mean
the harness checks something different from what the app runs.

### 2. Material ID — refuse rather than guess

`splitMaterialId` returns `{lot: null, slot: null}` when there is no separator or either side
is empty after trimming, and trims both fields. Null rather than `''` so a caller that forgets
to check produces `lot=null` in a URL rather than the silently-plausible `lot=ABC&slot=`.

Both call sites now check:
- `getSourceSummary` records `status: 'unresolved'` and **issues no HTTP request**.
- `materialMetaValues` returns an empty filter set, which makes `probeMapExists` return
  `null` (= 미상) instead of `false` (= 맵 없음). That keeps PRIMITIVES §7's "없다 vs 확인
  못 했다" distinction intact.
- `availabilityOf` gains a reason string for `unresolved`, so the pane renders the existing
  `미상` treatment with a tooltip instead of a confident `0`.

### 3. `normalizeBands` stopped being a second interpreter

This is the find that the contract did not ask about and that I think matters most.

`normalizeBands` is the read/modify/write normaliser: everything loaded from the column
passes through it and everything saved is re-serialised from its output. It ran its own
`Number(b.to)`, so **`"0x10"` in the column was rewritten to `16` and saved back** before
`bandTo` ever saw it, and `"  "` was rewritten to `0`. The screen then showed no mistake,
because the mistake had become the data. The server has no equivalent step — it leaves `to`
alone and classifies on read — so this was a pure client-side corruption path.

It now calls `bandToState` and:

| state | stored form |
|---|---|
| ok | the truncated number (canonical) |
| blank | `''` in memory → `null` on the wire |
| invalid | **the original value, verbatim** |

Preserving the invalid value verbatim is what makes the inline indication possible at all —
rewriting it to `''` would erase the evidence and leave a band silently counting 0 layers.

Round-trip evidence (`serializeBands(normalizeBands(parseJsonCol(stored)))`):

```
stored  [{"seq":1,"to":10,...},{"seq":2,"to":"0x10",...},{"seq":3,"to":"  ",...},{"seq":4,"to":7.9,...},{"seq":"2","to":true,...}]
written [{"seq":1,"to":10,...},{"seq":2,"to":"0x10",...},{"seq":3,"to":null,...},{"seq":4,"to":7,...},  {"seq":5,"to":true,...}]

  [0] to 10      -> 10      preserved   ok
  [1] to "0x10"  -> "0x10"  preserved   invalid     (was becoming 16)
  [2] to "  "    -> null    preserved   blank       (was becoming 0)
  [3] to 7.9     -> 7       CHANGED     ok          (only intentional rewrite; both sides read 7.9 as 7 anyway)
  [4] seq "2"    -> 5,  to true -> true preserved   invalid
```

### 4. `normalizeBands` seq rule vs the server — they did **not** agree

The brief asked me to confirm the two rules agree. They agreed on everything the vectors
cover and disagreed outside it:

| `seq` value | server `_assign_band_seqs` | client (before) | client (now) |
|---|---|---|---|
| `1` | 1 | 1 | 1 |
| `"abc"`, `0`, `-4` | position | position | position |
| **`"2"`** (string) | position | **2** | position |
| **`true`** | position | **1** | position |
| `2.0` | position | 2 | 2 (**still diverges** — see below) |

`bands` is a plain `character varying` and the generic grid can write it, so a string `seq`
is reachable in practice — exactly the `map_doe` hand-migration path the server comment
calls out. Client now uses `typeof raw === 'number' && Number.isInteger(raw) && raw > 0`,
matching the server's `isinstance(int) and not bool and > 0`.

`2.0` remains divergent and is **not fixable on the client**: `JSON.parse('{"seq":2.0}').seq`
is indistinguishable from `2`, while Python sees a `float` and falls back to position. Same
class as the 2^53 problem below. Low practical risk (nothing writes `2.0`), but it should be
written down rather than discovered again.

### 5. Invalid made visible — inside the row that already exists

`renderBand` now renders three states in the one line it already had, and `bandCalcText`
explains the zero on the line it already had:

```
[0] 1–10층 10층                          칠함 4 × 10층 = 소요 40 · 자재 1매 → 매당 40
[1] 11층 ~ 읽을 수 없는 값 "0x10"         끝 층을 숫자로 읽을 수 없어 이 구간은 0층으로 셉니다 — 끝 층을 다시 입력하세요.
[2] 11–20층 10층                         칠함 4 × 10층 = 소요 40 · 자재 1매 → 매당 40
[3] 21층 ~ 미정                          끝 층을 입력하면 소요가 계산됩니다.
```

The raw value is shown (clipped at 24 chars, full value in the tooltip) because *what to fix*
is the value itself. The existing `<input type="number">` cannot display `0x10` at all — it
renders empty — so without this the operator would see an empty box and a plausible 0.

**Complexity budget: net new controls 0 / removed 0.** Element census per band row:

| row | div | span | input | button |
|---|---|---|---|---|
| ok | 5 | 5 | 2 | 3 |
| **invalid (new)** | 5 | **6** | 2 | 3 |
| blank (pre-existing) | 5 | **6** | 2 | 3 |

The invalid row is structurally identical to the blank row that already shipped — it reuses
`.tp-unknown-val` with a `.bad` modifier (grey → red). No new panel, mode, modal or region;
`/(modal|dialog|overlay|tp-sec)/` does not match the emitted markup. CSS added: 2 rules,
7 lines. Reading stays frictionless; the write path keeps its single confirmation.

One write-path behaviour changed: typing `7.5` into 끝 층 used to be silently stored as `7`,
and now raises the existing toast `끝 층은 정수로 입력하세요.` The input runs through the same
classifier as display, so the panel can no longer create a value the contract calls invalid.

## Verification

### Mutation testing — the only self-check I trust

A green harness proves nothing until it has been watched going red. Each fixed defect was put
back, one at a time, into a **copy** of the tree (the repo was never mutated) and the harness
re-run. Script: `<scratchpad>/mutate.mjs`.

```
BASELINE (no mutation): exit=0 MATCHES

  ok M1  bandTo back to Number() coercion (the original defect)     -> CAUGHT (25 divergences)
  ok M2  prevTo stops on blank/invalid instead of skipping          -> CAUGHT (8)
  ok M3  splitMaterialId back to the ("ABC","") fallback            -> CAUGHT (3)
  ok M4  splitMaterialId stops trimming the two fields              -> CAUGHT (2)
  ok M5  bandTo drops the 2^53 guard on numbers                     -> CAUGHT (1)
  !! M6  bandTo string path uses Number() (2^53 folds silently)     -> HOLE
  !! M7  normalizeBands seq back to Number() (accepts "2" / true)   -> HOLE
  ok M8  normalizeBands drops duplicate-seq repair                  -> CAUGHT (2)
  ok M9  normalizeBands coerces invalid `to` (silent RMW corruption)-> CAUGHT (23)
  ok M10 bandToState renamed (extraction must die)                  -> CAUGHT (exit 2)

holes: 2/10
```

M9 was a hole on the first run — the harness had **no check at all** on `normalizeBands`'s
`to` output, which is where the silent corruption lived. I closed it (see next section).
M6 and M7 remain holes because closing them needs new vectors, which I must not add.

### Counterfactual — how many numbers actually move

Every `sequence_case` evaluated under both readings (`<scratchpad>/delta.mjs`):

```
key->value pairs compared      : 56
pairs that MOVE because of fix : 11        (= exactly the 11 sequence divergences)
sequence cases affected        : 2/7
summed stack demand            : fixed 106 · pre-fix 116 · delta -10

  blank_between_does_not_reset_the_walk            20 vs  30
  invalid_between_is_skipped_exactly_like_blank    20 vs  20   (same total!)
  non_increasing_inflates_the_next_band            25 vs  25   (same total!)
  ...
```

Worth noting for whoever reviews future work here: `invalid_between` has an **identical stack
total** under both readings while every per-band layer count and every per-material share is
wrong (band 1: 6 layers vs 0; band 2: 4 layers vs 10). A check that compared only the total
would have passed it. The divergence only shows per band and per material.

### Request list — the part the contract cannot score

The harness scores `splitMaterialId`'s return value; it cannot see what the panel then does
with it. Ran the real `getSourceSummary` / `materialMetaValues` / `availabilityOf` out of the
source with a `fetch` shim (`<scratchpad>/requests.mjs`), stage pinned so only the split shows:

**After the fix — 5 requests for 10 ids:**

```
"TAPE-A_01"   stage=DT&lot=TAPE-A&slot=01   {"lot":"TAPE-A","slot":"01"}   0
"LOT_A_01"    stage=DT&lot=LOT_A&slot=01    {"lot":"LOT_A","slot":"01"}    0
"  A_01  "    stage=DT&lot=A&slot=01        {"lot":"A","slot":"01"}        0
" A _ 01 "    stage=DT&lot=A&slot=01        {"lot":"A","slot":"01"}        0
"웨이퍼-갑_03"  stage=DT&lot=%EC%9B%A8...&slot=03                           0
"ABC"         (none)                        {}    미상 — 자재 ID를 lot·slot으로 나눌 수 없어 조회하지 않았습니다
"ABC_"        (none)                        {}    미상 — …
"_01"         (none)                        {}    미상 — …
"_"           (none)                        {}    미상 — …
"   "         (none)                        {}    미상 — …
```

**Same probe with the pre-fix `splitMaterialId` restored — 10 requests for 10 ids:**

```
" A _ 01 "    stage=DT&lot=A+&slot=+01      {"lot":"A ","slot":" 01"}      0
"ABC"         stage=DT&lot=ABC&slot=        {"lot":"ABC","slot":""}        0
"ABC_"        stage=DT&lot=ABC&slot=        {"lot":"ABC","slot":""}        0
"_01"         stage=DT&lot=_01&slot=        {"lot":"_01","slot":""}        0
"_"           stage=DT&lot=_&slot=          {"lot":"_","slot":""}          0
"   "         stage=DT&lot=&slot=           {"lot":"","slot":""}           0
```

Five unresolvable ids each produced a query and a confident `0` — PRIMITIVES §2's failure
mode, reproduced and then removed.

### Other checks

- Both edited modules parse (`node --check`), line endings preserved per file
  (map_editor.js CRLF, transfer_plan.js LF — no mixed endings introduced).
- `npm run build` clean; `읽을 수 없는 값` and the unresolved reason string are present in
  `client2/dist/assets/map_editor-BZztVZm2.js`.
- No DB access of any kind. All evidence is from source extraction in a `vm` sandbox with a
  `fetch` shim; no server was contacted and nothing was written.

## Harness changes (deliberate, please review these specifically)

1. **`bandToState` added to the extraction list** and to the `typeof` guard. Required because
   it is the classifier and `normalizeBands` calls it across the module boundary. M10 confirms
   the loud-failure property survives: renaming it exits 2 with "could not extract".
   `bandToState` is exported via a separate `export { bandToState };` statement rather than
   `export function` — the extractor's regex is `function NAME(`, so merging them would break
   it. There is a comment in the source saying so.

2. **New `normalize_roundtrip` group (+44 assertions).** Derived from the existing `to_cases`
   — no new vectors: for each case, assert `bandToState(normalizeBands([band])[0])` equals
   `bandToState(band)`. This is what catches M9. The invariant it states is real and
   server-relevant: the client must not change how a stored value reads just by loading and
   re-saving it.

3. **Ambiguous-input reporting.** See below. This one changes the scoring, so it is the change
   I would most want overruled if you disagree.

## Vectors I believe are wrong

### `to_cases.over_max_layer` is unsatisfiable on the client (not a client defect)

`vectors.json` asks for two different answers from one argument:

```
max_layer      {"to": 9007199254740992}  -> ok,      9007199254740992
over_max_layer {"to": 9007199254740993}  -> invalid, null
```

`JSON.parse('9007199254740993') === 9007199254740992` — both vectors arrive at the client as
the identical double. Verified: `Object.is` true, `JSON.stringify` equal. The client reads
`bands` from a varchar via the same `JSON.parse`, so this is not a harness artifact; the value
is unreachable in the product. Python's arbitrary-precision int makes it meaningful for the
server, which is why pytest can pin it.

**What I did:** I did not edit `vectors.json`. I taught the harness to detect this class
*derivationally* — group `to_cases` by parsed input, and if one input carries conflicting
expectations, report it in a `NOT COMPARED` block printed **above** the verdict and exclude
it from scoring (compared drops 111 → 109 for that group). It is not a name-based exemption:
a vector that becomes representable is scored again automatically.

**I am flagging this as a scoring change I made on my own judgement.** The alternative is a
permanently red harness, which I think is worse (an ignored check is worse than none —
PRIMITIVES §6-bis). If you would rather see it stay red, revert that block; the client code
needs no change either way.

**Recommended fix (server-side call, since pytest shares the file):** restate the vector as a
**decimal string** — `{"to": "9007199254740993"} -> invalid`. Strings are exact on both sides
(Python `int(s)`, client `BigInt(s)`), the vector becomes testable here, and it closes
mutation hole **M6**, which is currently the only unguarded part of the boundary rule. The
client is already implemented to pass it.

### Coverage gaps (no vector is wrong, but the axis is dead)

- **M6** — no vector exercises the 2^53 boundary through a string, so the exact `BigInt`
  comparison is unverified by the contract. Fixed by the suggestion above.
- **M7** — `normalization_cases.invalid_seq_types` covers `"abc"` / `0` / `-4` but not the
  types that actually diverged: `{"seq": "2"}` and `{"seq": true}`. Both should fall back to
  position on both sides. Suggested addition:
  `{"bands": [{"seq": "2", ...}, {"seq": true, ...}], "expect_seqs": [1, 2]}`.
- `normalization_cases` declares only `expect_seqs` / `expect_count`, so nothing in the file
  pins what `normalizeBands` does to `to`. My derived `normalize_roundtrip` group covers it
  for the client; if you want it symmetric, the natural vector field is `expect_to`.

## Contract behaviour I think is bad for the operator — none, with one caveat

The refusal decision is right and I am not re-litigating it. One consequence is worth stating
plainly so it is a choice and not a surprise: a site whose material IDs genuinely have no
separator (single-field lots) now gets `미상` on **every** material rather than a number. That
is correct — the number was never trustworthy — but it will read as a regression to whoever
sees it first. It is driven by `plan_store.material_identity` declaring
`compose: [lot, slot]`; a single-field site should declare a single-field rule, and the
server's `_material_identity_rule` already returns `None` when `{lot, slot}` is not a subset
of `compose`. Worth confirming that the client's hard-coded `lastIndexOf('_')` should
eventually read the declaration too rather than assuming the two-field shape — right now the
client assumes what the server derives. **Not in scope here; flagging it as the next divergence
of this exact family.**

## Suggested lesson-file additions (proposal only — `agent_workspace/memory/map-pm.md`)

1. **A contract vector can be unreachable on one side of the wire.** JSON numbers past 2^53
   and `2.0` vs `2` do not survive into JS. When two vectors demand different answers from one
   argument, that is a transport limit, not a defect — say so and quantify it, do not contort
   the code and do not silently skip it.
2. **A normaliser is an interpreter.** Any read/modify/write path that parses a field is a
   second implementation of that field's meaning, and it corrupts data *before* the display
   code can be blamed. `normalizeBands` rewrote `"0x10"` to `16` in storage while every
   display function was already correct. Grep for a second parse of any field the contract
   governs.
3. **Aggregates hide per-item divergence.** `invalid_between` has the same stack total under
   both readings while every band and every material share differs. Compare key→value, never
   the sum.
