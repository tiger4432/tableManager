# -*- coding: utf-8 -*-
"""시험 실행이 «수»가 아니라 «행»을 준다 (S-92, 판정 09-10 13:54).

🔴 THE OWNER ASKED FOR THE ROWS AND GOT A COUNT (09-09: 「체크한 로우들 줄 수 있나」). The
run reads a page, compiles it, reports `rows_read: 200` and throws the page away - so a
screen can say how many rows were checked and never which. The refusal samples had the same
shape: twenty of them, drawn as a number, while each one already carried the path it
happened at.

⛔ AND NEITHER COSTS A READ. The page is in memory when the compile finishes and the
refusal's row is in its own address, so both fields are things this route already had and
was dropping on the way out.

⚠️ THE SAMPLE IS NOT THE WHOLE ROW. A source relation can be forty columns wide; what
answers 「which rows did you check」 is the columns that identify a row plus the ones the
declaration reads. Everything else would be payload nobody asked to see.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                            # noqa: E402
from ledger.config_explorer_service import _refused_row                # noqa: E402


class _Refusal:
    def __init__(self, *paths):
        self.addresses = [{"code": "x", "path": p} for p in paths]


def test_a_refusal_that_names_a_row_says_which_one():
    """The path is `<frame>.rows[<n>].<column>`, so the row is already in the answer."""
    assert _refused_row(_Refusal("event_frame.rows[7].event_time")) == {
        "frame": "event_frame", "position": 7}


def test_a_refusal_about_the_source_names_no_row_and_invents_none():
    """⛔ ABSENT, NOT ZERO. `verified_join_reader_required` addresses
    `source_preparation.join_reader` - there is no row to point at, and a zero would send
    an operator to the first row of their table for no reason."""
    assert _refused_row(_Refusal("source_preparation.join_reader")) == {}
    assert _refused_row(_Refusal("sources.x.read.cursor")) == {}
    assert _refused_row(_Refusal()) == {}


def test_the_position_is_within_the_frame_it_names_and_says_so():
    """⚠️ NOT AN INDEX INTO THE SAMPLE. The sample is the first n rows of a page and a
    refusal can come from further in; a bare number would look like an offset into what the
    screen is showing and point at the wrong row."""
    located = _refused_row(_Refusal("role_frame.rows[3].roles.subject"))

    assert located == {"frame": "role_frame", "position": 3}


def test_the_sample_is_the_identifying_and_declared_columns():
    """Key columns first, then what the declaration reads - and nothing else."""
    class _Occurred:
        column = "event_time"

    class _Driver:
        cursor_columns = ("dt_cell_key",)
        occurred_at = _Occurred()

    class _Plan:
        driver = _Driver()

    columns = backfill._sample_columns(_Plan())

    assert columns[0] == "dt_cell_key", "the page key leads"
    assert "event_time" in columns
    assert len(columns) == len(set(columns)), "a column named twice is listed once"


def test_the_sample_shows_only_rows_it_was_given_and_only_those_columns():
    class _Occurred:
        column = "when"

    class _Driver:
        cursor_columns = ("k",)
        occurred_at = _Occurred()

    class _Plan:
        driver = _Driver()

    rows = [{"k": i, "when": "t", "payload": "not asked for"} for i in range(5)]

    sample = backfill._rows_sample(_Plan(), rows, 2)

    assert len(sample) == 2
    assert all("payload" not in row for row in sample), \
        "a wide relation must not put every column on a screen nobody asked"
    assert sample[0] == {"k": 0, "when": "t"}


def test_asking_for_no_sample_reads_and_shows_nothing():
    """⚠️ THE DEFAULT IN `preview_first_batch` IS ZERO, so every caller that is not the
    test-run route - the backfill, the harnesses - is byte-identical to before."""
    class _Plan:
        pass

    assert backfill._rows_sample(_Plan(), [{"k": 1}], 0) == ()
    assert backfill._rows_sample(_Plan(), [], 10) == ()

    import inspect
    assert "sample_rows: int = 0" in inspect.getsource(backfill.preview_first_batch)


def test_the_reading_carries_the_sample_as_its_own_field():
    """⛔ NO FIELD DEFAULTS on this dataclass, by its own docstring - one place builds it
    and passes them all, so a default would be a value nothing takes."""
    fields = backfill.TestRunReading.__dataclass_fields__

    assert "rows_sample" in fields
    import dataclasses
    assert fields["rows_sample"].default is dataclasses.MISSING


def test_the_size_is_a_request_argument_and_is_clamped():
    """🔴 NOT A DECLARATION CELL (판정 09-10 13:54). How many rows somebody wants to look
    at is a property of the looking; putting it in the declaration would make one
    operator's screen preference part of what every other reader compiles."""
    import inspect

    from ledger import config_explorer_service as service

    assert service.OntologyExplorerService.DEFAULT_SAMPLE_ROWS == 10
    assert service.OntologyExplorerService.MAX_SAMPLE_ROWS == 100

    body = inspect.getsource(service.OntologyExplorerService.test_run)
    assert "min(int(sample_rows), self.MAX_SAMPLE_ROWS)" in body, body[:600]
    assert "max(0," in body, "a negative ask must not become a negative slice"


def test_the_route_passes_it_and_survives_a_caller_that_sends_nonsense():
    import inspect

    from ledger_api import ontology_config_explorer_router as router

    body = inspect.getsource(router.test_run)
    assert "sample_rows=sample_rows" in body, body[:700]
    assert "except (TypeError, ValueError)" in body, \
        "a bad value must fall back rather than 500 an expensive read"
