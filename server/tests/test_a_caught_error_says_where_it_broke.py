# -*- coding: utf-8 -*-
"""A caught error says where it broke (총괄 10-20, 소유자 「이게 다 에러를 접어서 띄워서 모르잖아」): a screen, a queue or a
record keeps «its sentence (file:line in function)» (`error_said.told`), a log outside a loop the whole traceback.
Three seats broken on purpose - the chain rules file, the outbox purge, the join's stored-key probe - and the
file ingestion record, which takes `where` from the same module."""
import logging
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import error_said                                                   # noqa: E402
from chain import ingestion_worker                                  # noqa: E402
from database import crud                                           # noqa: E402


def _boom():
    raise TypeError("unhashable type: 'dict'")


def test_told_and_where_name_the_frame_under_a_wrapping_error():
    try:
        try:
            _boom()
        except TypeError as inner:
            raise ValueError("Plugin p.py::P could not read 'f.csv'") from inner
    except ValueError as e:
        assert error_said.where(e).endswith(" in _boom") and "test_a_caught_error_says_where_it_broke.py:" in error_said.where(e)
        assert error_said.told(e).startswith("Plugin p.py::P could not read 'f.csv' (test_a_caught_error_says_where_it_broke.py:")
    assert error_said.told(KeyError()) == "KeyError" and error_said.where(KeyError()) is None      # never raised


def test_the_chain_rules_file_says_where_it_broke(tmp_path):
    path = tmp_path / "chain_rules.json"
    path.write_text("[]", encoding="utf-8")                          # a list where a document belongs
    error = ingestion_worker.read_rules_document(str(path))["error"]
    assert error.startswith("'list' object has no attribute 'get' (ingestion_worker.py:") and \
        error.endswith(" in read_rules_document)"), error


def test_the_outbox_purge_logs_its_traceback(caplog):
    class Broken:
        def execute(self, *a, **kw):
            _boom()

        def rollback(self):
            pass

        def close(self):
            pass

    with caplog.at_level(logging.ERROR, logger=ingestion_worker.logger.name):
        ingestion_worker.purge_expired_outbox_sync(Broken)
    [record] = [r for r in caplog.records if "[Outbox Purge] Failed" in r.getMessage()]
    assert record.exc_info is not None and record.exc_info[1].args == ("unhashable type: 'dict'",)
    assert " in _boom)" in record.getMessage(), record.getMessage()


def test_the_join_probe_in_its_loop_says_where_in_one_line(monkeypatch, caplog):
    """The probe runs once per declared key - inside a loop the line carries told(e) and no traceback."""
    from database import schemas

    monkeypatch.setattr(crud, "_virtual_join_right_keys", lambda db, table: [("w_join", ["job"], [None])])
    monkeypatch.setattr(crud, "_stored_join_key_owners", lambda *a: _boom())
    batch = schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val="k1", updates={"job": "J-1", "lot": "L"})])
    with caplog.at_level(logging.WARNING, logger=crud.logger.name):
        crud.refuse_virtual_join_duplicates(None, "w_right", batch)
    [record] = [r for r in caplog.records if "stored-key probe skipped" in r.getMessage()]
    assert "unhashable type: 'dict' (test_a_caught_error_says_where_it_broke.py:" in record.getMessage() and \
        record.getMessage().endswith(" in _boom))"), record.getMessage()
    assert record.exc_info is None
