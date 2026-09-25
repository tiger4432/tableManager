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

from ledger import trace                                                  # noqa: E402
import pacing                                                        # noqa: E402
from ledger import backfill, schema                                  # noqa: E402


class _Plan:
    """⚠️ THE FAKE CARRIES A `driver`, because the real plan does. A fake thinner than the
    thing it stands in for is more permissive than production, and this one hid that the
    census has to know whether a source reads by ROW or by GROUP.

    `preparation.exclude_when` for the same reason, since the census also asks how many rows
    the declaration now EXCLUDES but the index still names (ruling 199). Empty here: these
    cases are about the STAMP, and a source with no clause is asked nothing."""

    def __init__(self, relation, frame_row_id, unit="row", group_by=(), exclude_when=(),
                 status="active", planned=True, refusal=None):
        self.relation = relation
        self.frame_row_id = frame_row_id
        # S-103: the sweep asks this before it counts, so the fake carries it.
        self.status = status
        # S-177 ②: and retirement is no longer the only way a source stops - the loader can
        # refuse one. `runs` is the ONE predicate the sweep asks, and the double computes it
        # the way the real `SourcePlan` does rather than answering a constant.
        self.planned = planned
        self.refusal = refusal
        self.driver = type("D", (), {
            "unit": unit, "group_by": tuple(group_by),
            "preparation": type("P", (), {"exclude_when": tuple(exclude_when)})()})()

    @property
    def runs(self):
        return self.status == "active" and self.planned


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
    value = trace.measured(12, exact=True, method="count(*)", measured_at="T")
    assert value == {"estimate": 12, "exact": True, "method": "count(*)",
                     "measured_at": "T"}


def test_the_atoms_estimate_is_built_from_the_same_helper_not_beside_it():
    """⛔ NOT A SECOND SPELLING. Two shapes for 「this is an estimate」 is how one of them
    starts rendering as a fact."""
    assert trace.ATOMS_UNKNOWN["exact"] is False
    assert trace.ATOMS_UNKNOWN["method"] == "pg_class.reltuples"
    assert trace.ATOMS_UNKNOWN["measured_at"] is None
    assert set(trace.measured(0, exact=False, method="m")) <= set(
        trace.ATOMS_UNKNOWN)


def test_the_key_is_estimate_because_that_one_already_ships():
    """⚠️ `value` would be the nicer word. The trace client reads `atoms.estimate` today,
    and renaming a shipped key to improve a word breaks a reader for nothing."""
    assert "estimate" in trace.ATOMS_UNKNOWN
    assert "value" not in trace.ATOMS_UNKNOWN


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
    setup = _setup({"void_observation": _Plan("void_obs_observed", None, planned=False,
                                              refusal={"path": "bundle.sources.void_observation.relation", "message": "not a table that has row_id"})})
    census = backfill.measure_row_census(object(), setup, "void_observation")

    assert census["refused"] == "source_refused"
    assert "not_yet" not in census
    assert census["measured_at"], "even a refusal says when it was found"


# ----------------------------------------------------------------- the sweep

def test_one_source_failing_does_not_silence_the_rest(monkeypatch):
    """A relation that was dropped must cost its own number and not the fourteen after it —
    the shape the follow-up loop already carries.

    ⚠️ THE FINGERPRINT IS STUBBED AND NOTHING ELSE IS. Since S-113 ⓑ-1 the census write is
    what CREATES a source's registry row, so it carries `cursor_translator_version` - which
    reads a whole compiled snapshot (plan, profile mappings, reachable entities). Faking
    that to reach this file's subject would be a second declaration; stubbing the one
    function keeps the subject where it is, which is the sweep's per-source isolation.
    """
    from ledger import setup_registry

    monkeypatch.setattr(setup_registry, "cursor_translator_version",
                        lambda snapshot, source_id: f"ledger-v2:{source_id}")

    class _Store:
        def __init__(self):
            self.written = []

        def write_row_census(self, source, census, *, translator_ver):
            # S-113 ⓑ-1: the write carries the fingerprint because it is now what CREATES
            # the source's registry row, so a double that dropped it would let the sweep
            # keep calling a signature the store no longer has.
            assert translator_ver
            self.written.append(source)

    class _Broken(_Engine):
        def raw_connection(self):
            raise RuntimeError("relation is gone")

    setup = _setup({"a": _Plan("rel_a", "row_id"), "b": _Plan("rel_b", "row_id"),
                    "c": _Plan("rel_c", "row_id")})
    # ⚠️ [총괄 f3bc02f6e] `a` and `c` used to be sources without row_id, refused WITHOUT the
    #   database; every planned source reads row_id now, so the census is stubbed and `b`'s
    #   raises - the subject is still that one failure costs one source.
    def census(engine, setup, source, now=None, *, exact_rows=True):
        if source == "b":
            raise RuntimeError("relation rel_b was dropped")
        return {"source": source, "relation": "rel_" + source, "measured_at": "now"}

    monkeypatch.setattr(backfill, "measure_row_census", census)
    store = _Store()
    done = backfill.measure_every_source(_Broken([]), setup, store=store)

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


def test_the_sweep_skips_a_retired_source_and_says_which(monkeypatch, caplog):
    """S-103: a retired source has nothing arriving, so 「rows not yet translated」 for it
    is a remainder that will never move - published, it reads as a backlog somebody must
    clear.

    ⛔ AND THE SKIP IS NAMED. A sweep that quietly returns fewer sources than the
    declaration has is indistinguishable from a sweep that lost them, which is the shape
    this file's other cases exist to refuse.
    """
    import logging

    from ledger import setup_registry

    class _Store:
        def __init__(self):
            self.written = []

        def write_row_census(self, source, census, *, translator_ver):
            self.written.append(source)

    monkeypatch.setattr(setup_registry, "cursor_translator_version",
                        lambda snapshot, source_id: f"ledger-v2:{source_id}")
    setup = _setup({"a": _Plan("rel_a", "row_id"),
                    "gone": _Plan("rel_gone", "row_id", status="retired"),
                    "c": _Plan("rel_c", "row_id")})
    monkeypatch.setattr(backfill, "measure_row_census",
                        lambda engine, setup, source, now=None, *, exact_rows=True:
                        {"source": source, "relation": "rel_" + source, "measured_at": "now"})
    store = _Store()
    with caplog.at_level(logging.INFO):
        done = backfill.measure_every_source(_Engine([]), setup, store=store)

    assert done == ["a", "c"] and store.written == ["a", "c"]
    assert "gone" in chr(10).join(r.getMessage() for r in caplog.records)


# ------------------------------------------------ 총괄 7426f76b0 ㉤: a refused source is measured

def _one_of_each():
    """A running source, one the loader refused, and one the operator retired."""
    return _setup({"a": _Plan("rel_a", "row_id"),
                   "r": _Plan("rel_r", "row_id", planned=False,
                              refusal={"path": "bundle.sources.r.relation",
                                       "message": "not a table that has row_id"}),
                   "gone": _Plan("rel_gone", "row_id", status="retired")})


def _real_census_for_the_refused(monkeypatch):
    """`r` goes through the real census (its refusal needs no database); the rest are
    stubbed, because this file's subject is which sources are measured and how they are
    stored. The fingerprint raises for `r`, as the real one does for a refused source."""
    from ledger import setup_registry

    def version(snapshot, source_id):
        if source_id == "r":
            raise RuntimeError("source 'r' was refused by the loader and has no material "
                               "to fingerprint")
        return f"ledger-v2:{source_id}"

    real = backfill.measure_row_census
    monkeypatch.setattr(setup_registry, "cursor_translator_version", version)
    monkeypatch.setattr(
        backfill, "measure_row_census",
        lambda engine, setup, source, now=None, *, exact_rows=True:
        real(engine, setup, source, now=now, exact_rows=exact_rows) if source == "r"
        else {"source": source, "relation": "rel_" + source, "measured_at": "now"})


def test_a_refused_source_is_measured_and_stored_without_a_fingerprint(monkeypatch, caplog):
    """The census asked `plan.runs`, so a source the LOADER refused was never measured
    again and the census it had before the refusal stood as its answer. Its census is the
    refusal now, stored with no fingerprint - the loader planned nothing to take one of.
    Only the retired source is skipped, by name."""
    import logging

    class _Store:
        def __init__(self):
            self.written = []

        def write_row_census(self, source, census, *, translator_ver):
            self.written.append((source, census.get("refused"), translator_ver))

    _real_census_for_the_refused(monkeypatch)
    store = _Store()
    with caplog.at_level(logging.INFO):
        done = backfill.measure_every_source(_Engine([]), _one_of_each(), store=store)

    assert done == ["a", "r"]
    assert store.written == [("a", None, "ledger-v2:a"), ("r", "source_refused", None)]
    said = chr(10).join(r.getMessage() for r in caplog.records)
    assert "census skips gone" in said and "census skips r" not in said, said


def test_the_worker_lap_measures_what_the_sweep_measures(monkeypatch, caplog):
    """The two census loops read one answer (`census_sources`), so the lap measures the
    refused source too (총괄 7426f76b0 ㉤). It rests only after a SCAN - a refused source's
    census touches no database, so the running sources keep their cadence - and the lap line
    names it refused, not retired (총괄 3b3b6803f)."""
    import asyncio
    import logging

    from chain import ingestion_worker as worker

    class _LapEnded(Exception):
        pass

    measured, laps, rests = [], [], []

    async def rest_then_end_after_the_lap_line(seconds):
        if laps:
            raise _LapEnded()
        rests.append(seconds)

    setup = _one_of_each()
    monkeypatch.setattr(pacing, "job_pace", lambda job: (1, 60.0))
    monkeypatch.setattr(worker, "_load_setup_sync", lambda factory: setup)
    monkeypatch.setattr(worker, "_measure_one_source_sync",
                        lambda factory, source, setup=None: measured.append(source) or (
                            {"refused": "source_refused"} if source == "r" else {}))
    monkeypatch.setattr(worker.heartbeat, "record_lap", lambda *a, **k: laps.append(k))
    monkeypatch.setattr(worker.asyncio, "sleep", rest_then_end_after_the_lap_line)
    with caplog.at_level(logging.INFO):
        try:
            asyncio.run(worker.run_ledger_row_census(lambda: None))
        except _LapEnded:
            pass

    assert measured == backfill.census_sources(setup)[0] == ["a", "r"]
    assert rests == [60.0], "one rest, after the one source that scanned"
    assert laps and laps[0]["depth"] == 2, laps
    line = [r.getMessage() for r in caplog.records if "lap:" in r.getMessage()][-1]
    assert "refused by the loader (no scan): r" in line, line
    assert "retired (content unvalidated): gone" in line, line
