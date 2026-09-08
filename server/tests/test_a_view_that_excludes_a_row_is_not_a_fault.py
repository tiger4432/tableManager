# -*- coding: utf-8 -*-
"""S-81. A view need not contain every row of the table it reads, and that is not an error.

S-65-c made a base table's event wake the sources reading views built on it. A view, though,
is usually a FILTER: measured 2026-09-09, `dt_log_transferable` holds 28,208 of `dt_log`'s
35,939 rows. So an event naming one of the other 7,731 scopes that source to nothing.

🔴 WHAT THAT USED TO DO. The empty scope fetched an empty frame, an empty frame has no
columns, and the write boundary refused it as `scope.row_id: the batch does not carry
'row_id'` -- a missing-column complaint about a frame that has no columns because it has no
rows. The follow-up drops a failed event, so the atoms were simply lost, and it repeated
every three seconds for as long as the loader ran.

⚠️ AND THE FIXTURES COULD NOT SEE IT. S-65-c's live gate used `void_obs`, whose follower is
keyed on `void_uid`; every view keyed on `row_id` reached this path for the first time when
the application lane loaded a thousand `dt_log` rows. One kind of key was covered and the
other was not.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                          # noqa: E402


class _Plan:
    relation = "dt_log_transferable"
    frame_row_id = "row_id"
    driver = type("D", (), {"cursor_columns": ("row_id",), "identity": ("row_id",)})()


def _setup():
    return type("S", (), {"snapshot": type(
        "Snap", (), {"source_plans": {"dt_transfer": _Plan()}, "__hash__": None})()})()


class _Connection:
    def rollback(self):
        pass

    def close(self):
        pass


class _Engine:
    def raw_connection(self):
        return _Connection()


def test_a_scope_that_selects_nothing_returns_instead_of_refusing(monkeypatch):
    """⛔ NOT AN EXCEPTION. The event named a row this view does not carry: there is nothing
    to translate and nothing has gone wrong.

    ⚠️ `rescope` imports its store and its write boundary INSIDE the function, so the patches
    below name the modules those imports read from rather than attributes of `backfill` --
    patching the latter would bind nothing and the case would pass without exercising this.
    """
    import ledger.setup as setup_module
    import ledger.store as store_module

    monkeypatch.setattr(backfill, "_fetch_v2_lineage_rows",
                        lambda read, plan, scope=None: [])
    monkeypatch.setattr(backfill, "_scope_predicate", lambda plan, scope: scope)
    monkeypatch.setattr(store_module, "LedgerStore", lambda engine: object())
    called = []
    monkeypatch.setattr(setup_module, "execute_selected_scoped_batch",
                        lambda *a, **k: called.append(a))

    result = backfill.rescope(_Engine(), _setup(), "dt_transfer", "row_id", ["r1"],
                              apply=True, withdraw=False)

    assert result["scope_empty"] is True
    assert result["rows_in_scope"] == 0 and result["inserted"] == 0
    assert called == [], "the write boundary must not be handed an empty frame"


def test_the_guard_is_about_emptiness_and_not_about_the_column():
    """🔴 THE OLD MESSAGE BLAMED A COLUMN. It said the batch does not carry 'row_id', which
    reads as a declaration fault and sent the first reader looking at `base_select_columns`;
    the frame had no columns because it had no ROWS. The guard therefore says `scope_empty`,
    which is the thing that was true.

    ⚠️ Scored on the source of one decision, deliberately narrow: the live half is that an
    excluded `dt_log` row now drains to inserted 0 with no error while an included one
    inserts 1, which needs the database and is reported rather than run here.
    """
    import inspect

    body = inspect.getsource(backfill.rescope)
    guard = body.split("if frame.empty:")[1].split("subjects =")[0]
    assert "scope_empty" in guard
    assert "return result" in guard
