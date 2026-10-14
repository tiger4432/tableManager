# -*- coding: utf-8 -*-
"""총괄 10-14 (소유자 «도는지 굳었는지 모르겠다»): a re-translate's page line counts one thing - the rows it
translates, over the rows there are. The atoms of a table the declaration no longer reads, taken back after the
pages, are said on their own line («withdrew N») and never counted against the rows («98046 / 50000» was)."""
import os
import sys
from types import SimpleNamespace

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from admin import retroactive                                        # noqa: E402
from ledger import backfill                                           # noqa: E402
from ledger import store as store_module                              # noqa: E402


class _Store:
    def __init__(self, *_a, **_k):
        pass

    def withdraw(self, _source, refs):
        return len(refs)

    def forget_row_refs(self, _table, _ids, source=None):
        return 0


def _engine():
    cursor = SimpleNamespace(execute=lambda *a: None, fetchall=lambda: [],
                             __enter__=None, __exit__=None)

    class Cursor:
        def __enter__(self):
            return cursor

        def __exit__(self, *a):
            return False

    connection = SimpleNamespace(cursor=Cursor, rollback=lambda: None, close=lambda: None)
    return SimpleNamespace(raw_connection=lambda: connection)


def test_the_atoms_taken_back_after_the_pages_are_not_counted_as_rows(monkeypatch):
    lines = []
    control = retroactive.RunControl(None, op="ledger_rescope", log=lines.append)
    checkpoint = retroactive._checkpoint(control)
    monkeypatch.setattr(store_module, "LedgerStore", _Store)
    monkeypatch.setattr(backfill, "_stale_atoms",
                        lambda *a, **k: iter([("ref%d" % i, ("dt_log",), "register") for i in range(9)]))

    checkpoint(50000, 50000)                                        # the pages: every row translated
    done = backfill.withdraw_stale_atoms(_engine(), "dt_job", "dt_job_rollup", apply=True,
                                         checkpoint=checkpoint, page_refs=4)

    after = lines[1:]
    assert "50000 / 50000" in lines[0] and done["stale_withdrawn"] == 9
    assert not [line for line in after if "/ 50000" in line], after
    assert after and all("withdraw atoms of a table it no longer reads" in line and "withdrew" in line
                         for line in after), after
