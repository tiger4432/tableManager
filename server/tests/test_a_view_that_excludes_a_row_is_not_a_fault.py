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
                        lambda read, plan, **k: [])
    monkeypatch.setattr(backfill, "_scope_predicate", lambda plan, scope: scope)
    monkeypatch.setattr(setup_module, "_require_declared_source", lambda setup, source: source)
    monkeypatch.setattr(store_module, "LedgerStore", lambda engine, **_: object())
    called = []
    monkeypatch.setattr(setup_module, "execute_selected_scoped_batch",
                        lambda *a, **k: called.append(a))

    result = backfill.rescope(_Engine(), _setup(), "dt_transfer", "row_id", ["r1"],
                              apply=True, withdraw=False)

    assert result["scope_empty"] is True
    assert result["rows_in_scope"] == 0 and result["inserted"] == 0
    assert called == [], "the write boundary must not be handed an empty frame"
# ⚰️ `test_the_guard_is_about_emptiness_and_not_about_the_column` read `rescope`'s source text
#    between `if frame.empty:` and `subjects =`; the paged rescope (총괄 8d8abfb5d) has no such
#    text. What it guarded - `scope_empty`, and no empty frame at the write - is the case above.
