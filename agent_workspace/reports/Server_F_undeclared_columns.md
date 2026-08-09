# LANE F — undeclared `frame_confirmation` columns

**Tier:** T2. **Result:** targeted suite green, 1 failed / 8 passed → 9 passed.

## What changed

| Path | Change |
|---|---|
| `server/migrations/add_frame_confirmation.py` | Two `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements appended to `DDL_TABLES`, in the same form the sibling columns already use. Verify block in `main()` now prints presence per column by name. |
| `server/tests/test_system_schema_drift.py` | `SYSTEM_TABLE_COLUMNS["frame_confirmation"]` gains `reference_cell_count` and `thresholds_defaulted`, with a comment naming the migration, matching the surrounding style. |
| `docs/architecture/data_model.md` | Line 200 said "여섯 컬럼" — a census my change made wrong. Replaced with a pointer to the enumerable source plus the measured incident. |

Staged with `git add <path>` only. Not committed.

The migration statements:

```
"ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS reference_cell_count INTEGER",
"ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS thresholds_defaulted TEXT",
```

`INTEGER`/`TEXT` match `Column(Integer)`/`Column(String)` and the file's existing rendering
(`margin INTEGER`, `core_frame TEXT`). Nullable with no default, deliberately: the model
comments make NULL a distinct fact ("the ruling did not carry this"), so a default would
answer for rows that were never asked.

Extension was the right move, not improvisation — the `CREATE TABLE IF NOT EXISTS` block
deliberately does not carry the later columns; every column added after the first round
(`geometry_assumed`, `frames`, `confirmed_frame`, `map_table`, `x_col`, `y_col`, `value_col`)
lives only in an `ADD COLUMN IF NOT EXISTS` line below it, which covers the fresh-database
case as well. I followed that exactly.

## The migration is load-bearing, not paperwork — measured

This box was already in the broken state the gate describes. Before the migration, a
full-entity ORM read of `FrameConfirmation` against the live database:

```
[orm] full-entity SELECT FAILED: ProgrammingError: (psycopg2.errors.UndefinedColumn)
      오류: frame_confirmation.reference_cell_count 칼럼 없음
```

`information_schema` before: 31 columns, both target columns absent, 18 rows present.
So `frame_confirmation` was down **whole** on this box — including the paths that never
mention either column — exactly the failure mode the suite's docstring records.

After the migration: 33 columns, `reference_cell_count integer null=YES`,
`thresholds_defaulted text null=YES`, and the same ORM read returns rows.

## Idempotency evidence

Run 1 was the real production scenario (table exists, columns absent). Run 2 exercised the
`IF NOT EXISTS` no-op branch. Both `EXIT=0`, byte-identical output, row counts unchanged:

| | run 1 | run 2 |
|---|---|---|
| exit code | 0 | 0 |
| `frame_confirmation` rows | 18 | 18 |
| `frame_confirmation_source` rows | 68 | 68 |
| both columns present | True | True |

Existing rows read `reference_cell_count=None, thresholds_defaulted=None` — additive only,
no data touched.

## Test result

Before — `1 failed, 8 passed`:

```
AssertionError: column(s) added to an EXISTING system table:
{'frame_confirmation': ['reference_cell_count', 'thresholds_defaulted']}
```

After — `9 passed`.

Ordering was migration-first: the migration was written and run, and its effect confirmed
against the live catalog, **before** the manifest line was touched.

The manifest entry is pinned on both sides, not just the failing one:
`test_no_undeclared_system_table_column` gives live ⊆ manifest and
`test_manifest_has_no_stale_entries` gives manifest ⊆ live, so both passing means the tuple
is exactly the live column set — a typo could not have slipped through as green. Verified
separately: 33 entries, sorted, no duplicates, matching the live count of 33.

## Findings that go beyond the brief

**1. Nothing writes either column.** `server/frame_confirmation.py:587-617` is the single
writer (`record_confirmation` builds `models.FrameConfirmation(...)`), and it sets neither
`reference_cell_count` nor `thresholds_defaulted`. A repo-wide grep confirms it: the names
appear in `models.py`, `map_alignment.py`, `view_model.js`, tests and docs — **not** in
`frame_confirmation.py`. So every confirmation written from now on stores NULL for both.

By the model's own comment (`models.py:479-483`) that NULL means *"the ruling did not carry
the count — an old record or a transport loss"*, which is precisely the state those columns
exist to distinguish. The physical schema is now correct and the table is alive again, but
the fact still never reaches the record. That is the same shape as the `ruling_state`/
`shift_dx` defects already documented in `data_model.md` — a value the scorer has that the
write path does not carry.

I did not fix this: it is out of my lane's scope, the plumbing runs through
`server/map_alignment.py` which belongs to another lane this round, and the standing rule is
propose before fixing. **Recommend a follow-up round** wiring `ruling.reference_cell_count`
and `ruling.thresholds_defaulted` into `record_confirmation`, owned by whoever holds
`map_alignment.py`.

**2. Nothing contradicted the lead PM's stated facts.** Both `models.py` line numbers, the
manifest omission, and the sibling-column pattern were exactly as described. Both columns
came in together in `9cf17ee` (`fix(align): never borrow the origin`), which added them to
`models.py` without touching the migration — that is the whole cause.

## Not done

- No history entry and no `gen_index.py` run: the lead PM commits, and the history entry is
  generated from the commit diff afterward. Other lanes are mid-flight in this tree.
- `docs/process/PROJECT_STATUS.md` shows as modified — that is another lane's, untouched and
  unstaged by me.
- Full suite not run, per the constraint (two other lanes active).

## Proposed lesson (for `agent_workspace/memory/server-pm.md`, lead PM to approve)

- **함정**: 기존 시스템 테이블에 컬럼을 더하면서 마이그레이션을 같은 라운드에 늘리지 않는다.
  `create_all`은 이미 있는 테이블을 ALTER하지 않으므로 **개발 박스를 포함한 모든 배포 박스에서
  그 테이블이 통째로 죽는다** — SQLAlchemy가 매핑된 컬럼 전부를 모든 SELECT·INSERT에 이름 대기
  때문에, 그 컬럼을 읽지 않는 코드까지 같이 죽는다. 스위트가 초록이어도 무관하다(실측 2026-08-06:
  `frame_confirmation`이 `reference_cell_count` 없이 `UndefinedColumn`으로 전체 조회 사망, 18행
  보유 상태).
  **올바른 방법**: 컬럼을 모델에 더하는 커밋은 **같은 커밋에서** ① 마이그레이션에
  `ADD COLUMN IF NOT EXISTS`를 늘리고 ② 실제로 두 번 돌려 멱등을 확인하고 ③
  `SYSTEM_TABLE_COLUMNS`에 마이그레이션 이름과 함께 등재한다. 순서는 반드시 마이그레이션이
  먼저다 — 매니페스트만 고치면 스위트는 초록이 되고 배포 박스만 죽는다. 신규 상태는 기존 테이블
  확장보다 **신규 테이블**을 우선 검토하라는 기존 교훈이 여기서 다시 회수된다.
