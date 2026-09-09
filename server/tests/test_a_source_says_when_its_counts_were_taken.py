# -*- coding: utf-8 -*-
"""S-58 (판정 180). 「표 행 N · 색인 M · 남은 N−M」 per source, measured off the request path.

🔴 D5: A REQUEST MAY NOT COUNT. Both numbers are scans — `count(*)` on a relation that may
hold ten million rows, and `count(DISTINCT row_id)` on the index — so a declaration response
that computed them would be a screen that waits for a table. A paced job (`ledger_row_census`
in `pacing.json`) measures and STAMPS; the route reads the stamp.

🔴 A PUBLISHED NUMBER SAYS HOW IT WAS OBTAINED AND WHEN. `ledger_trace.measured` is the one
shape for that, and `ATOMS_UNKNOWN` is built from it rather than beside it — two spellings of
「this is an estimate」 is how one of them comes to render as a fact.

⛔ AND THE ABSENCES STAY DISTINGUISHABLE. A source that has never been swept omits the key
(not 0 — that would say the table is empty). A source that cannot be counted at all is
stamped `refused` (not 0 — 「셀 수 없다」 and 「한 것이 없다」 are different answers).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_trace                                                  # noqa: E402
import pacing                                                        # noqa: E402
from ledger import backfill, schema                                  # noqa: E402


class _Plan:
    """⚠️ THE FAKE CARRIES A `driver`, because the real plan does. A fake thinner than the
    thing it stands in for is more permissive than production, and this one hid that the
    census has to know whether a source reads by ROW or by GROUP."""

    def __init__(self, relation, frame_row_id, unit="row", group_by=()):
        self.relation = relation
        self.frame_row_id = frame_row_id
        self.driver = type("D", (), {"unit": unit, "group_by": tuple(group_by)})()


def _setup(plans):
    return type("S", (), {"snapshot": type(
        "Snap", (), {"source_plans": plans, "__hash__": None})()})()


class _Cursor:
    def __init__(self, answers):
        self._answers = list(answers)

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return (self._answers.pop(0),)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Engine:
    def __init__(self, answers):
        self._answers = answers

    def raw_connection(self):
        engine = self

        class _Connection:
            def cursor(self):
                return _Cursor(engine._answers)

            def rollback(self):
                pass

            def close(self):
                pass

        return _Connection()


# ------------------------------------------------------------------ the shape

def test_every_published_number_says_how_and_when():
    value = ledger_trace.measured(12, exact=True, method="count(*)", measured_at="T")
    assert value == {"estimate": 12, "exact": True, "method": "count(*)",
                     "measured_at": "T"}


def test_the_atoms_estimate_is_built_from_the_same_helper_not_beside_it():
    """⛔ NOT A SECOND SPELLING. Two shapes for 「this is an estimate」 is how one of them
    starts rendering as a fact."""
    assert ledger_trace.ATOMS_UNKNOWN["exact"] is False
    assert ledger_trace.ATOMS_UNKNOWN["method"] == "pg_class.reltuples"
    assert ledger_trace.ATOMS_UNKNOWN["measured_at"] is None
    assert set(ledger_trace.measured(0, exact=False, method="m")) <= set(
        ledger_trace.ATOMS_UNKNOWN)


def test_the_key_is_estimate_because_that_one_already_ships():
    """⚠️ `value` would be the nicer word. The trace client reads `atoms.estimate` today,
    and renaming a shipped key to improve a word breaks a reader for nothing."""
    assert "estimate" in ledger_trace.ATOMS_UNKNOWN
    assert "value" not in ledger_trace.ATOMS_UNKNOWN


# ------------------------------------------------------------ the measurement

def test_the_three_numbers_come_from_one_measurement():
    """🔴 ONE INSTANT. Two queries a second apart can disagree — rows arrive between them —
    and a remainder computed from a mismatched pair was never true at any moment."""
    setup = _setup({"wafer_process": _Plan("wafer_process_recipe", "row_id")})
    census = backfill.measure_row_census(_Engine([478035, 470000]), setup,
                                         "wafer_process")

    assert census["relation_rows"]["estimate"] == 478035
    assert census["indexed_rows"]["estimate"] == 470000
    assert census["not_yet"]["estimate"] == 8035
    stamps = {census[key]["measured_at"] for key in
              ("relation_rows", "indexed_rows", "not_yet")}
    assert stamps == {census["measured_at"]}, "the three must share one instant"


def test_each_number_names_how_it_was_obtained():
    setup = _setup({"wafer_process": _Plan("wafer_process_recipe", "row_id")})
    census = backfill.measure_row_census(_Engine([10, 4]), setup, "wafer_process")

    assert census["relation_rows"]["method"] == "count(*)"
    assert census["indexed_rows"]["method"] == "count(distinct row_id)"
    assert census["not_yet"]["method"] == "relation_rows - indexed_rows"
    assert all(census[key]["exact"] for key in
               ("relation_rows", "indexed_rows", "not_yet"))


def test_a_source_that_cannot_be_counted_is_stamped_refused_and_not_zero():
    """⛔ THE WHOLE POINT OF THE REFUSAL IS THAT IT SURVIVES. Storing a 0 here would throw
    away 「cannot be counted」 one layer after `rows_not_yet_translated` earned it."""
    setup = _setup({"void_observation": _Plan("void_obs_observed", None)})
    census = backfill.measure_row_census(object(), setup, "void_observation")

    assert census["refused"] == "no_row_id"
    assert "not_yet" not in census
    assert census["measured_at"], "even a refusal says when it was found"


# ----------------------------------------------------------------- the sweep

def test_one_source_failing_does_not_silence_the_rest():
    """A relation that was dropped must cost its own number and not the fourteen after it —
    the shape the follow-up loop already carries."""
    class _Store:
        def __init__(self):
            self.written = []

        def write_row_census(self, source, census):
            self.written.append(source)

    class _Broken(_Engine):
        def raw_connection(self):
            raise RuntimeError("relation is gone")

    setup = _setup({"a": _Plan("rel_a", None), "b": _Plan("rel_b", "row_id"),
                    "c": _Plan("rel_c", None)})
    store = _Store()
    done = backfill.measure_every_source(_Broken([]), setup, store=store)

    # `a` and `c` carry no row_id, so they are refused WITHOUT touching the database and
    # still get stamped; `b` would need the connection and fails. Two of three survive.
    assert done == ["a", "c"] and store.written == ["a", "c"]


# ------------------------------------------------------- where the answer lives

def test_the_column_is_added_rather_than_required():
    """An install that predates S-58 gets the column by `CURSOR_ADDITIONS`, which
    `ensure_schema` runs — no migration script, because adding a nullable column is not a
    change anything can fail on."""
    assert schema.ROW_CENSUS_COLUMN in schema.CREATE_CURSOR
    assert schema.ROW_CENSUS_COLUMN in dict(schema.CURSOR_ADDITIONS)


def test_the_job_has_a_declared_pace_rather_than_a_constant():
    """🔴 `pacing.json` exists so an operator who needs this to stop crowding the database
    at 2am edits a cell instead of a constant."""
    units, rest = pacing.job_pace(backfill.ROW_CENSUS_JOB)
    assert rest > 0
    assert units is None or units >= 1


def test_a_group_source_is_stamped_without_a_remainder_rather_than_crashing():
    """🔴 THE JOB RUNS EVERY CYCLE. A census that assumed `not_yet` was always there would
    raise on `lot_event` (unit=group) on every sweep — and the sweep names the failure and
    moves on, so it would have been a source silently never measured.

    ⛔ AND THE TWO COUNTS STILL SAY WHAT THEY COUNTED. `[rows]` and `[groups]` ride in the
    `method`, which is the field that exists so a number cannot be read as the wrong thing."""
    setup = _setup({"lot_event": _Plan("lot_event", "row_id", unit="group",
                                       group_by=("event_group_key",))})
    census = backfill.measure_row_census(_Engine([3633, 490]), setup, "lot_event")

    assert census["relation_rows"]["method"].endswith("[rows]")
    assert census["indexed_rows"]["method"].endswith("[groups]")
    assert "not_yet" not in census
    assert "event_group_key" in census["not_comparable"]
