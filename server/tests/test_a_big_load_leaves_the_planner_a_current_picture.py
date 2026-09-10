# -*- coding: utf-8 -*-
"""큰 적재 뒤 통계와, 선언만 되고 없던 인덱스 (S-124, 판정 09-10 13:05).

🔴 WHAT WAS MEASURED. After a 440,000-row load the grid's page query spent 0.7 s choosing
a page of ids. Nothing was broken: the table HAD the index, and the planner was costing the
query against statistics that describe the table as it was BEFORE the load, so it chose a
sequential scan and a sort over an index it already had.

⛔ SO THE FIX IS NOT A SECOND INDEX. It is two things the system should not need a person
to remember: re-analyse a table after a load big enough to have moved it, and build - on a
table that already exists - the indexes the model declares, because `create_all` adds them
only while it is creating the table and an older relation never got them.

⚠️ 「사람이 기억해야 하는 절차는 구멍이다」. Both halves work until the day somebody is
busy, which is the day a large load happens.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                            # noqa: E402
from parsers import directory_watcher as dw                            # noqa: E402


# ── the indexes a model declares and a table may lack ────────────────────────

def test_both_declared_indexes_are_asked_for():
    """⚠️ BOTH, THOUGH ONE IS A PREFIX OF THE OTHER. They are declared together because the
    page query orders by both columns; the migration that retires prefix-redundant indexes
    states why such a pair is kept, so an ensure building one of them would be a third
    opinion about the same declaration."""
    built = dict(models.dynamic_table_index_ddls("some_table", {}))

    assert set(built) == {"ix_some_table_updated_at", "idx_some_table_updated"}
    assert '("updated_at")' in built["ix_some_table_updated_at"]
    assert '("updated_at", "row_id")' in built["idx_some_table_updated"]
    for statement in built.values():
        assert "CONCURRENTLY" in statement and "IF NOT EXISTS" in statement


def test_a_view_is_asked_for_nothing():
    assert models.dynamic_table_index_ddls("v", {"kind": "view"}) == []
    assert models.dynamic_table_index_ddls("", {}) == []


def test_the_count_is_what_was_built_and_not_what_was_attempted():
    """🔴 THE LINE THIS FIXES SAID `built 68` ON EVERY BOOT (caught by this round's own
    gate). `IF NOT EXISTS` succeeds loudly on an index that is already there, so a builder
    reporting "the statement ran" made a second boot announce sixty-eight fresh indexes and
    issue sixty-eight pointless CONCURRENTLY builds. A line that reads the same whether or
    not anything happened is the log equivalent of no line at all."""
    attempted = []

    def _fake(engine, name, statement, what):
        attempted.append(name)
        # 🔴 THREE STATES, NOT A TRUTH VALUE, and the log proved twice in one day why:
        # `True` meaning "the statement ran" announced sixty-eight indexes nobody built,
        # and `False` meaning "already there" made a caller print COULD NOT BE ENSURED
        # about an index that exists. Both false, in opposite directions, from one bit.
        return (models.INDEX_BUILT if name.endswith("_updated")
                else models.INDEX_PRESENT)

    original = models._ensure_one_index
    models._ensure_one_index = _fake
    try:
        created = models.ensure_dynamic_table_indexes(
            object(), config={"t": {}, "v": {"kind": "view"}})
    finally:
        models._ensure_one_index = original

    assert created == ["idx_t_updated"]
    assert attempted == ["ix_t_updated_at", "idx_t_updated"], attempted


def test_every_caller_of_the_builder_speaks_the_same_three_words():
    """⛔ FOUR CALLERS, ONE VOCABULARY. The states exist because a boolean had two things
    to say and one bit to say them with; a caller left reading it as a truth value is the
    regression that shipped a `COULD NOT BE ENSURED` line about an index that exists."""
    import inspect

    import chain_ingestion_worker as worker

    assert {models.INDEX_BUILT, models.INDEX_PRESENT,
            models.INDEX_FAILED} == {"built", "present", "failed"}

    body = inspect.getsource(worker._ensure_human_claims_index_sync)
    assert "models.INDEX_BUILT" in body and "models.INDEX_PRESENT" in body, body[:400]

    for name in ("ensure_dynamic_table_indexes", "ensure_alignment_decision_key_indexes",
                 "ensure_map_key_indexes"):
        source = inspect.getsource(getattr(models, name))
        assert "== INDEX_BUILT" in source, (name, source[:400])


def test_the_ensure_survives_a_database_that_refuses():
    """A boot that dies on an index build is a worse outage than a missing index."""
    class _Refuses:
        def connect(self):
            raise RuntimeError("no database here")

    assert models.ensure_dynamic_table_indexes(_Refuses(), config={"t": {}}) == []


def test_the_boot_sequence_calls_it():
    """🔴 착지는 배선이 아니다 — the check every ensure in this file needed, for the reason
    the decision-key one proved: wired only into a config reload, a restarted deployment
    comes up without the index and nothing says so."""
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker.start_chain_ingestion_worker)
    assert "_ensure_dynamic_table_indexes_sync" in body, body[:400]
    assert hasattr(worker, "_ensure_dynamic_table_indexes_sync")


# ── the statistics a load leaves behind ──────────────────────────────────────

def test_the_threshold_is_declared_and_has_a_default_that_changes_nothing_small():
    """Under the threshold nothing extra runs, so the ordinary drip of small files costs
    what it costs today."""
    assert dw.DEFAULT_ANALYZE_AFTER_ROWS == 10000
    assert dw.analyze_after_rows() >= 0


def test_a_small_load_is_left_alone(monkeypatch):
    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 10000)
    called = []
    monkeypatch.setattr(dw, "SessionLocal", lambda: called.append(1))

    assert dw._analyze_after_load("t", 9999) is False
    assert called == []


def test_it_can_be_turned_off_by_declaration(monkeypatch):
    """⚠️ ZERO IS OFF, not "every load". An operator who has autovacuum tuned should be
    able to say so without editing code."""
    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 0)
    called = []
    monkeypatch.setattr(dw, "SessionLocal", lambda: called.append(1))

    assert dw._analyze_after_load("t", 10_000_000) is False
    assert called == []


def test_a_failure_to_re_analyse_never_takes_the_load_down(monkeypatch):
    """🔴 THE ROWS ARE ALREADY DURABLE WHEN THIS RUNS. Letting a statistics failure escape
    would turn a slower next query into a file reported FAILED - a small cost traded for a
    large lie."""
    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 10)

    class _Boom:
        def connection(self):
            raise RuntimeError("no database here")

        def close(self):
            pass

    monkeypatch.setattr(dw, "SessionLocal", lambda: _Boom())

    assert dw._analyze_after_load("t", 20000) is False


def test_the_load_path_asks_for_it_after_the_last_chunk():
    """착지는 배선이 아니다, again: the seat is the end of the file's own loop, after the
    rows are committed, and not a runbook."""
    import inspect

    body = inspect.getsource(dw.IngestionHandler._send_to_upsert)
    assert "_analyze_after_load(t_name, processed_rows)" in body, body[-1500:]


# ── the always-on timing line must not carry what a person typed ─────────────

def test_the_timing_line_says_whether_a_search_was_set_and_never_what_it_was():
    """🔴 THE LINE IS ALWAYS ON NOW, so `q` would put user-typed values in a permanent
    file. 「payload 본문 로그 금지」 is about content a person supplied, and a search box is
    that even though it is not a payload body. What a diagnosis needs is whether a filter
    was in play."""
    import inspect

    import main

    body = inspect.getsource(main.get_table_data)
    assert "q={'set' if q else '-'}" in body, body[-1200:]
    assert "q={q}" not in body
