# -*- coding: utf-8 -*-
"""A mapper that ran must say so, in the file where it actually lands.

Owner, 2026-09-04: 「진짜 맵퍼 함수가 돌 때 로그 띄워줘 확인하게」. What was behind the
request is the day he had just lost: he put a `print` inside a mapper, watched the server
log, saw nothing, and read that as "the mapper did not run". It had run. Mappers execute
in the CHAIN WORKER process, whose lines go to `chain_worker.log`, and the server log he
was reading belongs to a different process entirely.

So "did it run" has to be answerable without owning a mapper file, and the answer has to
carry WHERE it is being answered. Both are asserted here.

⛔ AND THE LINE MUST NOT CARRY THE PAYLOAD. Group sizes and names are safe to log;
operator row content is not, and a log that quietly becomes a data export is a different
incident. Asserted with a value that would be unmistakable if it leaked.
"""
import logging
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker as worker                          # noqa: E402

RULE = {"name": "some_rule", "target_table": "some_target"}
SECRET = "PAYLOAD-BODY-MUST-NOT-BE-LOGGED"


def install(monkeypatch, fn, name="fake_mapper_module"):
    """A real importable module, so `execute_custom_mapper` takes its own import path.

    The function under test resolves its mapper with `importlib.import_module` and
    `getattr`; handing it a module through `sys.modules` exercises that resolution
    instead of replacing it.
    """
    module = types.ModuleType(name)
    module.run = fn
    monkeypatch.setitem(sys.modules, name, module)
    return name, "run"


def payloads(n=3):
    return [{"row_id": "r%d" % i, "data": {"col": {"value": SECRET}}} for i in range(n)]


def lines(caplog, marker):
    return [r.getMessage() for r in caplog.records
            if worker.MAPPER_LOG_TAG in r.getMessage() and marker in r.getMessage()]


# ------------------------------------------------------------------ it ran, and it said so

def test_a_mapper_that_runs_logs_a_start_and_an_end(monkeypatch, caplog):
    mod, fn = install(monkeypatch, lambda db, p: {"updates": [{"updates": {"a": 1}}]})
    with caplog.at_level(logging.INFO):
        worker.execute_custom_mapper(mod, fn, None, payloads(3), rule=RULE)

    start, end = lines(caplog, "START"), lines(caplog, "END")
    assert len(start) == 1, "one line per group, not per row"
    assert len(end) == 1
    for text in start + end:
        assert "some_rule" in text and "some_target" in text and mod in text
    assert "rows_in=3" in start[0] and "rows_in=3" in end[0]
    assert "rows_out=1" in end[0]
    assert "elapsed=" in end[0]


def test_the_line_says_which_file_it_is_actually_in():
    """The whole reason the owner lost a day: the answer was in another file.

    🔴 Asserted against the file the process ACTUALLY writes to, not against this
    module's `LOG_FILENAME`. The chain loop runs inside the web server in the integrated
    deployment, where `server.log` was opened first and wins, and a tag naming
    `chain_worker.log` on lines landing in `server.log` would break the very rule it
    exists to serve.
    """
    from utils import logger as process_logging

    expected = process_logging.active_log_filename() or worker.LOG_FILENAME
    assert worker.MAPPER_LOG_TAG == "mapper@%s" % expected
    assert worker.LOG_FILENAME == "chain_worker.log"      # what it asks for when it is first


def test_the_payload_body_never_reaches_the_log(monkeypatch, caplog):
    """Names and counts, never content."""
    mod, fn = install(monkeypatch, lambda db, p: {"updates": [{"updates": {"a": SECRET}}]})
    with caplog.at_level(logging.INFO):
        worker.execute_custom_mapper(mod, fn, None, payloads(2), rule=RULE)
    assert SECRET not in "\n".join(r.getMessage() for r in caplog.records)


# ------------------------------------------------------------------ it did not run

def test_a_mapper_that_raises_gets_its_own_line_and_still_raises(monkeypatch, caplog):
    """`rows_out=0` and "it threw" must not read the same.

    A mapper with nothing to do legitimately returns nothing, so folding the throw into
    the end line would make the two indistinguishable - which is exactly the confusion
    this round exists to remove.
    """
    def boom(db, p):
        raise ValueError("refused by name")

    mod, fn = install(monkeypatch, boom)
    with caplog.at_level(logging.INFO):
        with pytest.raises(ValueError):
            worker.execute_custom_mapper(mod, fn, None, payloads(2), rule=RULE)

    raised = lines(caplog, "RAISED")
    assert len(raised) == 1
    assert "ValueError" in raised[0] and "refused by name" in raised[0]
    assert "some_rule" in raised[0] and "rows_in=2" in raised[0]
    assert not lines(caplog, "END"), "a throw is not an end"


def test_a_mapper_with_nothing_to_do_says_zero_rather_than_going_quiet(monkeypatch, caplog):
    mod, fn = install(monkeypatch, lambda db, p: {"updates": []})
    with caplog.at_level(logging.INFO):
        worker.execute_custom_mapper(mod, fn, None, payloads(4), rule=RULE)
    assert "rows_out=0" in lines(caplog, "END")[0]


# ------------------------------------------------------------------ the count is honest

def test_the_batch_shape_is_counted_and_not_reported_as_zero(monkeypatch, caplog):
    """🔴 THE SHAPE THAT WOULD HAVE LIED. `dt_standard_map_mapper` returns `batches`,
    not `updates`, and a counter that read only `updates` would report a whole map's
    worth of cells as `rows_out=0` - the very number the operator is trying to tell
    apart from "did not run"."""
    result = {"map_metadata_updates": [{"updates": {"map_id": "m"}}],
              "batches": [{"updates": [{"updates": {}}] * 7},
                          {"updates": [{"updates": {}}] * 5}]}
    mod, fn = install(monkeypatch, lambda db, p: result)
    with caplog.at_level(logging.INFO):
        worker.execute_custom_mapper(mod, fn, None, payloads(1), rule=RULE)
    assert "rows_out=13" in lines(caplog, "END")[0]      # 7 + 5 + 1 metadata


def test_a_single_payload_mapper_counts_one_row(monkeypatch, caplog):
    """Non-batch rules hand over one payload dict, not a list."""
    mod, fn = install(monkeypatch, lambda db, p: {"updates": []})
    with caplog.at_level(logging.INFO):
        worker.execute_custom_mapper(mod, fn, None, payloads(1)[0], rule=RULE)
    assert "rows_in=1" in lines(caplog, "START")[0]


def test_a_rule_that_names_nothing_still_logs(monkeypatch, caplog):
    """The identity fields are read off the rule, and a mapper may be called without
    one. An instrument that only works when its context is complete is not one."""
    mod, fn = install(monkeypatch, lambda db, p: {"updates": []})
    with caplog.at_level(logging.INFO):
        worker.execute_custom_mapper(mod, fn, None, payloads(1))
    assert len(lines(caplog, "START")) == 1 and len(lines(caplog, "END")) == 1
