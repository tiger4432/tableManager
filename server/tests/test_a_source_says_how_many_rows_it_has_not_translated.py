# -*- coding: utf-8 -*-
"""판정 173. S-69's sentence, and it is arithmetic now rather than a page.

S-69 was 「the backfill answers 'there is nothing to do' and 'there are rows the scan cannot
see' with the SAME silence」. The old count could not fix that: `rows_past_cursor` read ONE
PAGE from the watermark, so a full page could only ever say "at least N" -- counting past a
position means reading past it, and the route had to carry `count_kind` to say which sort of
number it was handing over.

🔴 THE ROW INDEX MAKES IT A SUBTRACTION. The index names the rows the ledger holds facts
from, so what is left is the relation's count minus the index's count: exact, every time,
with no page that can come back full.

⛔ AND A SOURCE THAT CANNOT BE COUNTED SAYS SO RATHER THAN SAYING ZERO. A relation with no
`row_id` writes no index rows at all, so the subtraction would return the WHOLE TABLE and
report a source translated entirely by the live path as one that has never been touched.
That is the same "absent zero read as an inert zero" this project keeps naming, and it is
refused by name instead.

⚠️ WHAT THIS FILE SCORES: the shape of the answer, on a fake plan and a fake connection --
the counts themselves are two `count(*)`s and are the lead PM's live half. What cannot be
faked away is which of the three sentences comes back.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                          # noqa: E402


class _Plan:
    def __init__(self, relation, frame_row_id):
        self.relation = relation
        self.frame_row_id = frame_row_id


def _setup(plans):
    return type("S", (), {"snapshot": type(
        "Snap", (), {"source_plans": plans, "__hash__": None})()})()


class _Cursor:
    """Answers the two counts in the order the function asks them."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchone(self):
        return (self._answers.pop(0),)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Connection:
    def __init__(self, answers):
        self.cursor_object = _Cursor(answers)
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_object

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class _Engine:
    def __init__(self, answers):
        self.connection = _Connection(answers)

    def raw_connection(self):
        return self.connection


def test_a_source_without_row_id_is_refused_rather_than_counted():
    """⛔ NOT ZERO. Such a source writes no index rows, so `relation - indexed` is the whole
    table -- the loudest possible wrong answer, in the confident direction."""
    setup = _setup({"void_observation": _Plan("void_obs_observed", None)})
    report = backfill.rows_not_yet_translated(object(), setup, "void_observation")

    assert report["refused"] == "no_row_id"
    assert "not_yet" not in report, "a refusal must not also hand back a number"
    assert "row_id" in report["remedy"], "the refusal must say what to declare"


def test_the_answer_is_three_values_and_the_third_is_the_difference():
    """🔴 THREE, NOT ONE. 「nothing was staged」 alone reads the same whether the table is
    empty or already translated; the two counts are what tell those apart."""
    setup = _setup({"wafer_process": _Plan("wafer_process_recipe", "row_id")})
    report = backfill.rows_not_yet_translated(_Engine([478035, 470000]),
                                              setup, "wafer_process")

    assert report["relation_rows"] == 478035
    assert report["indexed_rows"] == 470000
    assert report["not_yet"] == 8035
    assert "refused" not in report


def test_a_fully_translated_source_reports_zero_left_and_says_why_it_is_zero():
    """The zero that IS an answer -- and it is distinguishable from the refusal above
    because both counts came back and they are equal."""
    setup = _setup({"wafer_process": _Plan("wafer_process_recipe", "row_id")})
    report = backfill.rows_not_yet_translated(_Engine([478035, 478035]),
                                              setup, "wafer_process")

    assert report["not_yet"] == 0
    assert report["relation_rows"] == report["indexed_rows"] == 478035


def test_an_index_naming_rows_the_table_no_longer_holds_is_named_not_clamped_silently():
    """⛔ A SILENT ZERO. More indexed than present means a deletion the follow-up could not
    withdraw. Clamping to 0 without saying so reports 「nothing left」 for a table that is
    actually missing its withdrawals."""
    setup = _setup({"dt_transfer": _Plan("dt_log_transferable", "row_id")})
    report = backfill.rows_not_yet_translated(_Engine([100, 107]), setup, "dt_transfer")

    assert report["not_yet"] == 0
    assert report["index_names_absent_rows"] == 7


def test_the_read_is_closed_even_though_it_only_counted():
    """A counting connection left open holds ACCESS SHARE, and the write path's first
    partition create is ACCESS EXCLUSIVE -- the deadlock this module already carries a
    comment about, one call site over."""
    setup = _setup({"wafer_process": _Plan("wafer_process_recipe", "row_id")})
    engine = _Engine([10, 10])
    backfill.rows_not_yet_translated(engine, setup, "wafer_process")

    assert engine.connection.rolled_back and engine.connection.closed


def test_the_index_is_asked_by_relation_AND_by_source():
    """Two sources may read one relation. Counting by relation alone would credit one
    source with the other's work, and the difference would silently shrink."""
    setup = _setup({"dt_transfer": _Plan("dt_log_transferable", "row_id")})
    engine = _Engine([10, 4])
    backfill.rows_not_yet_translated(engine, setup, "dt_transfer")

    params = [p for _, p in engine.connection.cursor_object.queries if p]
    assert params == [("dt_log_transferable", "dt_transfer")]


def test_the_cli_prints_the_three_values_rather_than_the_word_None(monkeypatch, caplog):
    """🔴 THE GATE ITEM. The CLI used to end with two lines that printed `None` -- keys the
    deleted cursor driver had produced -- and no count at all, so 「nothing was staged」 was
    the whole answer. It is a PRINTER now: the values ride the result, so stubbing the run
    is enough to score what an operator sees."""
    import logging

    import database.database as database_module

    monkeypatch.setattr(database_module, "engine", object())
    monkeypatch.setattr(backfill, "beat", lambda result: None)
    monkeypatch.setattr(backfill, "run", lambda engine, **kwargs: {
        "source": "wafer_process", "rows_read": 0, "batches": 0,
        "relation_rows": 478035, "indexed_rows": 478035, "not_yet": 0})

    with caplog.at_level(logging.INFO):
        assert backfill.main(["--source", "wafer_process"]) == 0

    printed = "\n".join(record.getMessage() for record in caplog.records)
    assert "relation rows 478035 | indexed 478035 | not yet translated 0" in printed
    assert "census by predicate" not in printed
    assert not any(record.getMessage().strip() == "None" for record in caplog.records)


def test_the_cli_says_a_refused_source_was_not_counted():
    """⛔ NOT A ZERO ON THE SCREEN EITHER. The refusal has to survive all the way to the
    line an operator reads, or the screen re-invents the silence the count removed."""
    import inspect

    body = inspect.getsource(backfill.main)
    assert 'result.get("refused")' in body and "not counted" in body
