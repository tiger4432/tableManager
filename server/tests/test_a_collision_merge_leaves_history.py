# -*- coding: utf-8 -*-
"""One of ten audit calls dropped its return, and that merge's history went nowhere (2026-09-06).

`create_audit_log`'s own docstring records the rule: with `add_to_cache=False` it skips the
in-memory cache AND `db.add`, so every caller has to keep the returned dict itself. The write door
whose merge dropped it (`crud.apply_row_update_internal`) retired with the lines (lead 11-11 ㄱ); a
merge is `write_lines._merge_into` now - its history is the lines it moves onto the holder
(`test_a_moved_key_part_rekeys_and_merges_into_the_holder`). Two of the old assertions are kept here
on that merge: a merge that moves no shown value tells no edit, and it reads the marks of both rows
in one statement.
"""
import ast
import inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud                                         # noqa: E402
from test_a_moved_key_part_rekeys_and_merges_into_the_holder import (  # noqa: E402,F401 - the fixture by its name
    _events, _rows, _write, fixture_db)


def test_no_audit_call_anywhere_in_crud_drops_its_return():
    """⛔ THE CLASS, NOT THE INSTANCE. Ten sites made this call and one had drifted; the
    next one to drift should turn this red rather than wait to be noticed."""
    tree = ast.parse(inspect.getsource(crud).lstrip())
    dropped = [node.lineno for node in ast.walk(tree)
               if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
               and (getattr(node.value.func, "id", None)
                    or getattr(node.value.func, "attr", None)) == "create_audit_log"]
    assert not dropped, "create_audit_log's return is discarded at line(s) %s" % dropped


def test_the_contract_that_makes_the_dropped_return_fatal_is_still_stated():
    """If `create_audit_log` ever started persisting regardless, the rule above would be
    harmless but the reasoning behind it would be stale - and a future reader would not
    know which."""
    assert "db.add" in (crud.create_audit_log.__doc__ or ""), \
        "create_audit_log no longer documents that add_to_cache=False skips db.add"


def _same_value_pair(db):
    _write(db, "f1.csv", {"k": "K1", "a": "same"})
    _write(db, "f2.csv", {"k": "K2", "a": "same"})
    rows = _rows(db)
    return rows["K1"][0], rows["K2"][0]


def test_a_merge_that_moves_no_shown_value_tells_no_edit(db):
    """⚠️ NO EVENT FOR NO WORK. An edit for a cell that did not move would make every merge look
    like a change. The control - a merge whose shown value moves tells one EDIT - is
    `test_a_key_part_edited_onto_a_held_key_merges_the_row_into_the_holder`."""
    holder, shell = _same_value_pair(db)
    _events(db)
    _write(db, "f3.csv", {"k": "K1"}, row_id=shell)
    assert _rows(db) == {"K1": (holder, "same")}, "canary: the shell merged into the holder"
    events = _events(db)
    assert [e for e in events if e[0] == "EDIT" and holder in e[1]] == [], events
    assert [e[0] for e in events if shell in e[1]] == ["DELETE"], events


def test_the_merge_reads_the_marks_of_both_rows_in_one_statement(db):
    """🔴 THE COUNT, NOT THE CLOCK. The old merge asked `cell_overwrites` once per column per row, so
    its cost grew with the table's WIDTH for a fact that fits in one read of two row ids."""
    from sql_budget import record_statements

    holder, shell = _same_value_pair(db)
    with record_statements(db) as recorded:
        _write(db, "f3.csv", {"k": "K1"}, row_id=shell)
    assert _rows(db) == {"K1": (holder, "same")}, "canary: the merge ran"
    reads = [c.sql for c in recorded if c.sql.lstrip().upper().startswith("SELECT")
             and "cell_overwrites" in c.sql.lower()]
    assert [sql for sql in reads if "cell_overwrites.column_name = " in sql] == [], "a read per column: %s" % reads
    assert len([sql for sql in reads if "cell_overwrites.row_id IN (?, ?)" in sql]) == 1, reads


def test_both_collision_sites_go_through_the_one_helper():
    """⛔ ONE MERGE BODY (총괄 6e041f4cb ①): every write's key rebuild (write_lines step 5½ - the funnel,
    the pin, a withdraw) and merge_into_key_holders reach `write_lines._merge_into`; the pin spells none."""
    from database import write_lines

    assert "_merge_into(" in inspect.getsource(write_lines._rekey)
    assert "_merge_into(" in inspect.getsource(write_lines.merge_rows)
    assert "merge_rows(" in inspect.getsource(crud.merge_into_key_holders)
    pin = inspect.getsource(crud.set_cell_manual_priority_batch)
    assert "_merge_into(" not in pin
