# -*- coding: utf-8 -*-
"""One of ten audit calls dropped its return, and that merge's history went nowhere.

`create_audit_log`'s own docstring records the rule: with `add_to_cache=False` it skips the
in-memory cache AND `db.add`. Every caller therefore has to keep the returned dict and put
it on `logs_to_cache` itself -- nine of the ten do. The `collision_merge` site in
`apply_row_update_internal` called it as a statement and threw the return away, so the row
reached neither the database nor the cache.

🔴 AND IT WAS NOT INTERMITTENT. Measured 2026-09-06: `apply_row_update_internal` has exactly
one live caller, and that caller sets `logs_to_cache = []` and passes it unconditionally. So
`add_to_cache` was ALWAYS False on this path and the history was ALWAYS lost -- "sometimes"
would have been the wrong word for the report.

🔵 THE CORRECT SHAPE WAS ALREADY IN THE FILE. The other `collision_merge` site does exactly
`log_dict = create_audit_log(...)` then `logs_to_cache.append(log_dict)`, and so do the two
sites a few hundred lines above. Nothing was designed here; a line was missing.
"""
import ast
import inspect
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud, models, schemas                       # noqa: E402


def audit_calls(function):
    """Every `create_audit_log(...)` in `function`, and whether its value is kept."""
    tree = ast.parse(inspect.getsource(function).lstrip())
    kept, dropped = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != "create_audit_log":
            continue
        # A call whose value is used is not an `Expr` statement on its own.
        (dropped if _is_bare_statement(tree, node) else kept).append(node.lineno)
    return kept, dropped


def _is_bare_statement(tree, call):
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and node.value is call:
            return True
    return False


# ------------------------------------------------------------------ the return is kept

def test_the_collision_merge_call_keeps_its_return():
    """🔴 THE FIX. A discarded return here means the row reaches neither the database nor
    the cache, because `add_to_cache=False` skips both."""
    kept, dropped = audit_calls(crud.apply_row_update_internal)
    assert kept, "no audit call found - the walker stopped short"
    assert not dropped, "an audit call still drops its return at line(s) %s" % dropped


def test_it_is_appended_rather_than_merely_captured():
    """Capturing without appending would be the same loss with a variable name on it."""
    # Split on the CALL, not on the string "collision_merge": that word appears earlier in
    # this function as an overwrite comparison, so splitting on it scores the wrong region
    # - the assertion would answer a different question than it asks.
    # EVERY captured call, not the first one within some window: a fixed slice length is a
    # number this assertion would have to keep in step with the code, and it already cut
    # the append off by a few characters once.
    body = inspect.getsource(crud.apply_row_update_internal)
    captures = body.count("log_dict = create_audit_log(")
    appends = body.count("logs_to_cache.append(log_dict)")
    assert captures and appends >= captures, (
        "%d call(s) capture the return but only %d append it - capturing without appending "
        "is the same loss with a variable name on it" % (captures, appends))


def test_no_audit_call_anywhere_in_crud_drops_its_return():
    """⛔ THE CLASS, NOT THE INSTANCE. Ten sites make this call and one had drifted; the
    next one to drift should turn this red rather than wait to be noticed."""
    tree = ast.parse(inspect.getsource(crud).lstrip())
    dropped = [node.lineno for node in ast.walk(tree)
               if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
               and (getattr(node.value.func, "id", None)
                    or getattr(node.value.func, "attr", None)) == "create_audit_log"]
    assert not dropped, "create_audit_log's return is discarded at line(s) %s" % dropped


# ------------------------------------------------- why it was always lost, not sometimes

def test_the_only_live_caller_always_supplies_the_list():
    """🔴 THIS IS WHY THE WORD IS "ALWAYS". If some caller passed `None`, `add_to_cache`
    would be True there and the row would persist itself - the loss would be partial. It is
    not: one caller, one list, every time."""
    body = inspect.getsource(crud)
    calls = [line for line in body.splitlines()
             if "apply_row_update_internal(" in line and "def " not in line]
    assert len(calls) == 1, "the caller count changed: %s" % calls
    assert "logs_to_cache=logs_to_cache," in body


def test_the_contract_that_makes_the_dropped_return_fatal_is_still_stated():
    """If `create_audit_log` ever started persisting regardless, this fix would be
    harmless but the reasoning behind it would be stale - and a future reader would not
    know which."""
    assert "db.add" in (crud.create_audit_log.__doc__ or ""), \
        "create_audit_log no longer documents that add_to_cache=False skips db.add"


# ------------------------------------------- the row that is ACTUALLY written, not the text

TABLE = "xscope_safe_map"          # business key = lot_slot_cx_cy, so one edit can collide


def merge_pair(db, *, shell_bn="NEW", conflict_bn="OLD"):
    """Two rows one composite-key edit apart, so the shell can land on the other's key."""
    model = models.DYNAMIC_TABLES[TABLE]

    def add(lot, slot, cx, cy, bn):
        key = crud.compose_business_key(TABLE, [lot, slot, cx, cy])
        row = model(row_id=str(uuid.uuid4()), business_key_val=key, cell_key=key,
                    lot=lot, slot=slot, cx=cx, cy=cy, bn=bn)
        db.add(row)
        return row

    conflict = add("L1", 1, 1, 1, conflict_bn)
    shell = add("L1", 1, 2, 1, shell_bn)          # differs only in cx
    db.flush()
    return shell, conflict


def run_the_merge(db, **kw):
    """The real write path, driven into the collision branch. Returns what it cached."""
    shell, conflict = merge_pair(db, **kw)
    logs = []
    crud.apply_row_update_internal(
        db, TABLE,
        schemas.GeneralUpdateItem(row_id=shell.row_id, updates={"cx": 1},
                                  source_name="user", updated_by="tester"),
        logs_to_cache=logs)
    return logs, conflict


def test_a_real_collision_merge_produces_an_audit_row(db_session):
    """🔴 GATE ④. The assertions above read the source; this one RUNS it. A test that
    builds its own log dict and then finds it would stay green with the append deleted,
    which is the one thing this fix must not allow."""
    logs, conflict = run_the_merge(db_session)
    merges = [d for d in logs if d.get("source_name") == "collision_merge"]
    assert merges, "the merge happened and left no history: %s" % logs
    assert {d["column_name"] for d in merges} == {"bn"}
    assert merges[0]["row_id"] == conflict.row_id


def test_the_audit_row_carries_both_sides_of_the_merge(db_session):
    """A history row that cannot say what was replaced is a row, not a history."""
    logs, _ = run_the_merge(db_session, conflict_bn="OLD", shell_bn="NEW")
    merge = [d for d in logs if d.get("source_name") == "collision_merge"][0]
    assert merge["old_value"] == "OLD" and merge["new_value"] == "NEW"
    assert merge["updated_by"] == "tester"


def test_the_cached_row_survives_the_caller_s_bulk_insert(db_session):
    """⛔ THE END OF THE ROUTE, NOT THE MIDDLE OF IT. `logs_to_cache` is a list the caller
    hands to `bulk_insert_audit_logs`; asserting only that the dict was appended would
    stop one step before the row exists."""
    logs, conflict = run_the_merge(db_session)
    crud.bulk_insert_audit_logs(db_session, logs)
    db_session.flush()
    written = (db_session.query(models.AuditLog)
               .filter(models.AuditLog.table_name == TABLE,
                       models.AuditLog.source_name == "collision_merge").all())
    assert [r.row_id for r in written] == [conflict.row_id]
    assert written[0].column_name == "bn"


def test_a_merge_that_changes_nothing_writes_no_history(db_session):
    """⚠️ NO EVENT FOR NO WORK, the same rule the purge helper keeps. An audit row for a
    column that did not move would make every merge look like a change."""
    logs, _ = run_the_merge(db_session, shell_bn="SAME", conflict_bn="SAME")
    assert [d for d in logs if d.get("source_name") == "collision_merge"] == []


# ------------------------------------------- [P-4] the merge reads the overwrites ONCE

def overwrite_selects(recorded):
    """Statements that read `cell_overwrites`, which is what the merge loop used to
    issue once per column per row."""
    return [c for c in recorded
            if "FROM cell_overwrites" in c.sql or "from cell_overwrites" in c.sql]


def pin(db, row, column, by="user"):
    """A user overwrite on one cell - what the merge's protection guard reads."""
    from datetime import datetime

    db.add(models.CellOverwrite(table_name=TABLE, row_id=row.row_id, column_name=column,
                                is_overwrite=True, updated_by=by,
                                manual_priority_source=by, updated_at=datetime.now()))
    db.flush()


def test_the_merge_reads_the_overwrites_in_one_statement(db_session):
    """🔴 THE COUNT, NOT THE CLOCK. The loop asked per column and per row, and a column
    with no overwrite asked too - so the cost scaled with the table's WIDTH for a fact
    that fits in one read of two row ids."""
    from sql_budget import record_statements

    shell, conflict = merge_pair(db_session)
    with record_statements(db_session) as recorded:
        crud.apply_row_update_internal(
            db_session, TABLE,
            schemas.GeneralUpdateItem(row_id=shell.row_id, updates={"cx": 1},
                                      source_name="user", updated_by="tester"),
            logs_to_cache=[])
    reads = overwrite_selects(recorded)
    # 🔴 THE PROPERTY IS THE SHAPE, NOT A TOTAL. Other reads on this path are not the
    # merge's, and pinning a total would make this test go red for their reasons. What
    # the repair removed is the PER-COLUMN read, so that is what is asserted gone.
    # ⚠️ NOT ZERO, AND THE REASON IS NAMED. The ordinary metadata path reads the
    # overwrite of each cell this update CHANGED, and that read is not the merge's and
    # not this repair's. What the merge used to add was one per column OF THE TABLE, so
    # the property is that the count no longer scales with the table's width.
    merged_columns = [c.name for c in models.DYNAMIC_TABLES[TABLE].__table__.columns
                      if c.name not in ("cell_key", "row_id", "business_key_val",
                                        "created_at", "updated_at")]
    per_column = [c for c in reads if "cell_overwrites.column_name = " in c.sql]
    assert len(per_column) < len(merged_columns), (
        "%d per-column overwrite reads for %d merged columns - the merge is still "
        "asking once per column" % (len(per_column), len(merged_columns)))
    batched = [c for c in reads if "row_id IN " in c.sql]
    assert len(batched) == 1, (
        "expected exactly one batched read for the two rows, got %d: %s"
        % (len(batched), [c.sql[-60:] for c in batched]))


def test_the_protection_decision_is_unchanged(db_session):
    """🔴 THE OTHER ARM. A batch that loses the overwrites would also issue one
    statement, and would silently stop protecting the user's value."""
    shell, conflict = merge_pair(db_session, conflict_bn="MINE", shell_bn="THEIRS")
    pin(db_session, conflict, "bn")                     # the conflict row's cell is pinned
    crud.apply_row_update_internal(
        db_session, TABLE,
        schemas.GeneralUpdateItem(row_id=shell.row_id, updates={"cx": 1},
                                  source_name="parser_x", updated_by="parser_x"),
        logs_to_cache=[])
    db_session.flush()
    assert conflict.bn == "MINE", "the pinned value was overwritten by the merge"


def test_an_unpinned_cell_still_merges(db_session):
    """The control for the test above: without the pin the same call DOES merge, so the
    assertion there is about the guard rather than about the merge never running."""
    shell, conflict = merge_pair(db_session, conflict_bn="OLD", shell_bn="NEW")
    crud.apply_row_update_internal(
        db_session, TABLE,
        schemas.GeneralUpdateItem(row_id=shell.row_id, updates={"cx": 1},
                                  source_name="parser_x", updated_by="parser_x"),
        logs_to_cache=[])
    db_session.flush()
    assert conflict.bn == "NEW"


def test_both_collision_sites_go_through_the_one_helper():
    """⛔ TWO SITES, ONE READ. They each spelled this lookup by hand, which is how one of
    them gets repaired and the other keeps the old cost."""
    import inspect

    module = inspect.getsource(crud)
    assert module.count("prime_merge_overwrites(db, table_name, merge_ow,") == 2
    # Scoped to the two merge functions: `column_name ==` is still correct elsewhere
    # (the chunked delete builds an `or_()` of exactly those comparisons), so asserting
    # its absence module-wide would assert something untrue about other code.
    for fn in (crud.apply_row_update_internal, crud.set_cell_manual_priority_batch):
        body = inspect.getsource(fn)
        assert "CellOverwrite.column_name == col_name" not in body
        assert "CellOverwrite.column_name == c_name" not in body
        assert "prime_merge_overwrites(" in body
