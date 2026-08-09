# Map2 Retired Candidate Harness Debt

**Date:** 2026-08-09  
**Status:** Accepted debt — harness gate is report-only by Lead PM direction

The alignment candidate space is now the eight front-side walk starts
`rot{0,90,180,270}_{tl,tr}`. Four client harnesses still encode the retired
physical-mirror candidates `rot*_front/back`.

`client2/scripts/check_harnesses.mjs` records those harnesses in `KNOWN_RED`
with their measured failure/early-exit shape rather than changing production
code back to the old candidate space:

- `alignment_verdict_harness.mjs` — 163 assertions, 6 failures;
- `map_editor2_question_harness.mjs` — fails before assertions on `rot180_back`;
- `map_editor2_shell_harness.mjs` — imports removed `SIDE_HEADERS`;
- `map2_placement_seat_harness.mjs` — parses retired `rot*_front/back` ids.

Each remains executed and visible in the harness report. The harness runner is
temporarily report-only: it prints failures and configuration drift but does
not return a non-zero exit code, so `npm run build` can proceed during this
triage. Re-gating requires a deliberate fixture/oracle rewrite for the
start-corner contract; it must not reintroduce physical back-side candidates
into the scorer.
