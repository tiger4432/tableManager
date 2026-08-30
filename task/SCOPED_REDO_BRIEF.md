# Doing part of it again — scoped re-translate and scoped replay

Owner ruling 2026-08-30:

> 「그냥 표준 좌표계로 하고 저 회수를 좀 편리하게 만들어줘」
> 「체인 리플레이 저번에 내가 행 몇개 선택해서 그거만 선택적으로 리플레이하는거 지시했는데」

## Destination — one sentence, checked every round

**An operator who corrects one input must be able to redo exactly the part that input
touched — no more, no less — and see what will change before anything is written.**

The frame equations are corrected on roughly 1 wafer in 100 (owner). That number is why
standardising coordinates at the SOURCE is the right design and why this tool has to exist
first: without it, a corrected equation can never reach the ledger, so the 1% stays wrong
forever.

## What already exists — do not rebuild any of it

```
/admin/retroactive/operations       an inventory of retroactive operations
/admin/retroactive/{op}/count       each answers "how many rows" with its OWN dry-run
server/retroactive.py               the registry.  Each op declares `deletes`,
                                    `restartable`, its params, and its CLI equivalent
count_kind (exact|sample|upper_bound) + truncated + scanned
                                    so a count says whether it is about the TABLE or a SAMPLE
run_id                              queued execution already returns one
server/scripts/chain_replay_cli.py  replay / replay-all / withdraw / resolve / list
server/ledger/backfill.py           --source, --fetch-rows, --max-batches
```
The registry is the shape to extend. This lane adds operations to it; it does not build a
second mechanism beside it.

## What is missing — measured, not assumed

```
chain_replay        params = [rule]                   whole rule only
withdraw            params = [table, source, columns] columns can be narrowed, ROWS cannot
enrichment_*        params = [rule]                   whole rule only
replay_rule(db, rule, apply, limit, ...)   `limit` bounds how much is SCANNED.
                                           It does not select WHICH rows.
ledger backfill     --source X is whole-source, and --reset-cursor refuses:
                    LedgerSetupError("destructive_approval_required")
                    so a corrected input cannot be re-read at all today
```

## Build — one shape, two layers

Both layers want the same sentence: *redo this scope.* Give them one.

```
scope       a set of keys the operator names -- business keys, or a carrier/lot list.
            NOT a row count, NOT a limit.  Those already exist and mean something else
dry-run     ALWAYS first.  Returns: what would be withdrawn (N), what would be re-made (M),
            and which sources those atoms belong to
apply       withdraw then re-make, in that order, committed per page so it is restartable
```

### Ledger side — re-translate a scope
```
find the atoms this source wrote about the scope   `source_who` already carries the source id
withdraw them                                       scoped by source AND by the named keys
re-read just those rows                             without moving the whole-source cursor
```
🔴 `source_who` is the lock: an atom another source wrote about the same subject must not be
touched. Two sources speak about the same die today; withdrawing by subject alone would take
both.

### Chain side — replay named rows
`replay_rule` already walks items and already carries `business_key_val` through its stats and
its samples. The selection goes in beside `limit`, not instead of it.

## Stop conditions — stop and report

```
S1  🔴 DO NOT open `--reset-cursor` to solve this.  That guard blocks a WHOLE-SOURCE replay,
    which is a different and larger act.  Opening it would make the scoped case work by
    granting the unscoped one -- and then the safe path and the dangerous path are the same
    button.  If scoping genuinely cannot be done without it, STOP and report why
S2  the scope cannot be expressed against a source without adding a filter axis to `read`
    -> STOP.  `read` has no filter axis on purpose; a view is how filtering is declared here
S3  withdrawing by scope would also remove atoms whose `source_who` is a different source
    -> STOP and report the overlap count.  Do not "just also delete those"
S4  an operation cannot honestly say `deletes` and `restartable` -> STOP.  Every entry in the
    registry declares both, and a new one that cannot is not ready to be in it
```

## Verification

```
G1  dry-run writes NOTHING.  Assert atom count unchanged after a dry-run of every new op
G2  the counts are honest: dry-run says N/M, apply produces exactly N withdrawn and M written
G3  idempotent: applying the same scope twice leaves the same ledger as applying it once
G4  🔴 the isolation test.  Seed a subject two sources speak about.  Redo ONE source's scope.
    Assert the other source's atoms about that same subject are untouched.
    Without this, a passing G2 still permits taking the neighbour's atoms
G5  the real case end to end: change one carrier's equation, redo that scope, assert the
    standard coordinates moved for that carrier and did NOT move for any other
G6  human-touched rows survive.  `dt_map_derivation.plan_retraction` already separates
    `protected = _human_touched_row_ids(...)` from `retractable = stale - protected`;
    the same separation applies here and the log must name both counts, as that one does
```

Run only the tests you touch, with
`C:/Users/kk980/anaconda3/envs/assy_manager/python.exe -m pytest <file>` (conda run hangs).

## Do not build

```
⛔ a second registry beside `server/retroactive.py`
⛔ a new meaning for `--limit`.  It already means three different things across five CLIs and
   the route docstring says so; adding a fourth is how the next person gets it wrong
⛔ silent partial success.  If a scope is partly applied, say which part
⛔ a page.  The screen is a separate item (see task/OPS_PROGRESS_PAGE_CONCEPT.md);
   this lane ends at routes that answer honestly
```
