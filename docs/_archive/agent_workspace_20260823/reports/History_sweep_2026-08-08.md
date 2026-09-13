# History sweep — 2026-08-08

Lane: doc-historian. Scope touched: `docs/history/` only (10 new entries + regenerated
`README.md`). Nothing staged, nothing committed.

## Range actually uncovered

The brief said "57 commits with no entries". That is not what the tree shows. Coverage was
already deeper than assumed: `deb6307` shipped 26 entries for the aligner day (`690e869`..`f818360`),
and `4738d84` itself shipped five more entries covering `a14a098`, `4738d84`, `069b4e9`, `e943e46`
and the day's process record. So the genuinely uncovered window is `4738d84`..`34d2518` — 24
commits, of which 21 are new to the record.

Verification method: grep every 7-char hash in the range against `docs/history/*.md`.

## Entries written (10)

| File (all under `C:\Users\kk980\Developments\assyManager\docs\history\`) | Commits |
|---|---|
| `20260807_042352_the_per_row_select_was_the_last_accidental_guard_and_the_race_it_hid.md` | `4738d84` (second entry — see below) |
| `20260807_064625_the_outbox_carried_the_row_and_one_row_per_key_was_only_an_assumption.md` | `528dfcb`, `cc602ed` |
| `20260807_085943_a_blank_key_column_writes_nothing_because_two_bugs_were_hiding_each_other.md` | `818c9c0` |
| `20260807_094604_the_state_that_most_needed_a_person_was_the_one_a_person_could_not_answer.md` | `21209d7` |
| `20260807_100446_back_meant_mirror_and_two_attempts_to_stop_storing_it_were_refused.md` | `7a169b7`, `66b32a0`, `80f5913`, `51e4068`, `6ca9fa1`, `a7d239b`, `1073595`, `6444d51` |
| `20260807_120619_the_mirror_half_is_the_top_right_half_and_the_walk_axis_replaces_it.md` | `c4eaffa`, `c959368`, `db76be0` |
| `20260807_130054_ag_grid_suppresses_cell_text_selection_until_it_is_told_otherwise.md` | `15a2b39` |
| `20260807_133500_a_write_needs_three_answers_first_so_the_preflight_only_answers_them.md` | `b2ceb55` |
| `20260808_074639_the_absent_log_line_was_the_load_bearing_fact.md` | `714e77b` |
| `20260808_213310_the_refusal_named_the_margin_when_no_row_carried_an_index.md` | `b0d8881`, `0f19c23`, `34d2518` |

### Why `4738d84` got a second entry

`20260807_003000_the_prefetch_already_proved_the_row_was_absent...` already covers that commit's
performance work in depth, but it predates the commit (no hash) and it does **not** record the
`DO NOT DEPLOY WITHOUT D3` constraint, the ~0 → 2.4 s race window, the two-process reproduction
(two rows, one business key, no error) or the counterfactual `COUNT 1`. History is append-only, so
the missing fact went into a new entry that cross-references the old one rather than a rewrite.

### The 🔴 "record once" fact

`rotθ_back` + left-to-right ≡ `rotθ_front` + right-to-left on the index axis, therefore the mirror
half **is** the top-right half — stated once, in `20260807_120619`. The `20260807_100446` entry
covers the failed storage-side attempts and points at it without restating it.

## Deliberately skipped

| Commit | Why |
|---|---|
| `deb6307`, `d53a99d`, `1573031` | History-writing commits. Recording the act of writing history is churn. |
| `120f3bf` | `agent_workspace/memory/doc-historian.md` lesson append. Already lives in the lesson file. |
| `0a12272` | Handoff-doc refresh, superseded by the board. |
| `a14a098`, `069b4e9`, `e943e46` | Already have entries with the hash cited. |

Board-only commits (`66b32a0`, `6ca9fa1`, `a7d239b`, `1073595`, `6444d51`, `db76be0`, `0f19c23`,
`714e77b`) were **not** skipped — their findings are folded into the thematic entries above,
because each carries a measurement or a reversal that the code commits do not.

## For the lead PM — where message and diff disagree

1. **`b0d8881` message vs. its own diff.** The subject and body are entirely about the aligner
   refusal text, but the diff is 4 files and 1,263 insertions, of which 1,258 are three server-lane
   reports (`Server_D3_unique_business_key.md`, `Server_layer_reduction_design.md`,
   `Server_outbox_collapse_impl.md`). Those reports were swept in by a pathless commit — exactly the
   failure mode the `pathless-commit-defeats-add-discipline` lesson records. The message never
   mentions them.

2. **`21209d7` message vs. its own diff.** The body describes a one-line gate change in
   `view_model.confirmModel` plus three harness assertions. The diff also rewrites
   `client2/index.html` and `client2/dist/index.html` by ~730 and ~754 lines respectively — shell
   changes unrelated to the confirm gate, unmentioned. Recorded as "그때 남아 있던 것" in the entry.

3. **`b0d8881` names the live table as `dt_frame_confrimation`** (transposed letters). Either the
   live table name carries that typo or the commit does. I did not resolve it and did not repeat the
   spelling in the entry. Worth a one-query check by the server lane.

4. **`818c9c0` is honest about it, but flagging anyway:** it shipped with the full suite NOT re-run.
   The last real gate in this window is `528dfcb` — 3 failed, 3187 passed, 12 skipped, 1 xfailed.
   Three commits (`818c9c0`, `21209d7`, and the aligner thread) landed after it on module-level or
   harness-level evidence only.

5. **`c4eaffa`'s "258 passed" and `51e4068`'s "233 passed"** are module runs, not suite runs. Both
   entries say so; neither number should be quoted as a suite result.

No case found in this window where a commit asserted a count that its own diff contradicts. The
counts that were checkable (20,000 → 20 events; 2,113.5 → 36.0 B/row; 29 indexes / 382.3 MB from 5
declarations of which one produces 26; 25 tables / 52,725 rows / zero surplus) are internally
consistent, and `cc602ed` itself documents that the "29 from five declarations" figure was wrong
three times before anyone measured it.

## Index

`PYTHONIOENCODING=utf-8 conda run -n assy_manager python docs/history/gen_index.py`
→ `Wrote ... (434 dated entries, 434 total)`.
`--check` → `history/README.md is up to date.` (exit 0)

## Judgement calls worth naming

- **Entry granularity for the mirror thread.** Eight commits over four hours, five of them board
  edits reversing each other. One entry per commit would have produced five entries whose only
  content is "the previous instruction was wrong". Grouped into one entry that keeps every reversal
  visible in sequence, since the reversals *are* the record.
- **`20260808_153000` already existed** for `34d2518`, written by the server lane, untracked, and
  citing no commit hash. I did not edit it (append-only) and wrote the diagnosis-side entry with the
  hashes, cross-referencing it in both directions.
- **Line anchors avoided.** `6ca9fa1`/`a7d239b` argue from `map_editor.js:1706` and
  `seating.js:39`/`:196`. The entries name the operation (wafer centre vs. grid width) rather than
  the line, per the lesson that anchors age.

## Proposed lesson (for lead-PM review before it enters `doc-historian.md`)

> **함정**: 「이 커밋엔 항목이 없다」를 커밋 수로 센다. — 이번 스윕은 57건으로 지시됐고 실제
> 미커버는 21건이었다. 앞선 스윕이 **한 커밋에 여러 항목을 실어** 보냈기 때문에(`deb6307`이 26건,
> `4738d84`이 5건) 커밋과 항목이 1:1이 아니다.
> **올바른 방법**: 범위의 **모든 해시를 `docs/history/*.md`에 grep**해 외연을 세고 시작한다.
> 그리고 커버돼 있어도 **커밋 본문의 가장 중요한 문장이 그 항목에 없을 수 있다** — `4738d84`의
> 항목은 성능만 적고 `DO NOT DEPLOY WITHOUT D3`를 빠뜨렸다. 항목이 있다는 것과 그 커밋이
> 기록됐다는 것은 다른 사실이다.
