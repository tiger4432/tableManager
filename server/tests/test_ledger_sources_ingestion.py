# -*- coding: utf-8 -*-
"""「내 소스가 잘 들어갔나」 — the four states, and the sentence that travels with them.

WHY THIS FILE EXISTS
--------------------
The answer is assembled from `ledger_translator_cursor`, one row per source, because
counting the ledger itself by `source_who` is a scan of every partition (measured
2026-09-04: planner cost 110,832 against 1.13 for this). That choice is only safe if two
things hold, and neither is observable on the box that wrote them:

  * THE FOUR STATES ARE VALUES. Three of the four cannot be produced here - every source
    on this box has run and written - and a state nobody can see is a state nobody can
    check. They are fed in directly rather than seeded into the database, because
    manufacturing a state to observe it is how a fixture starts deciding the answer.

  * NOT KNOWING IS NOT THE SAME AS KNOWING NOTHING RAN. An unreadable cursor table must
    not render as fifteen sources that "never ran" - that is this repository's oldest
    recurring defect (an absence and a correct zero looking identical), and here BOTH
    live in the same list.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_admin                                                  # noqa: E402


class _Cursor:
    """A `ledger_translator_cursor` with the rows a test names, in column order."""

    def __init__(self, rows=None, raises=None):
        self.rows, self.raises, self.queries = rows or {}, raises, []

    def execute(self, statement):
        self.queries.append(str(statement))
        if self.raises is not None:
            raise self.raises
        return [(source,) + tuple(row.get(f) for f in ledger_admin._CURSOR_FIELDS)
                for source, row in self.rows.items()]


def wrote(atoms=10, molecules=5, refused=0, reasons=None):
    return {"translator_ver": "ledger-v2:abc", "molecules_done": molecules,
            "atoms_written": atoms, "atoms_deduped": 0, "molecules_refused": refused,
            "refusal_reasons": reasons, "updated_at": None}


def states(view):
    return {row["source"]: row["state"] for row in view["sources"]}


def test_the_four_states_are_values_not_something_a_reader_infers():
    """🔴 EACH OF THESE IS A DIFFERENT INSTRUCTION TO AN OPERATOR, and three of the four
    are invisible on the box this shipped from, so they are fed in.

        ran_and_wrote      nothing to do
        ran_wrote_nothing  the source is wired and produced nothing - look at the source
        never_ran          the translator has not been pointed at it yet
        orphan             a cursor row whose source is no longer declared

    The middle two are the pair that matters: both are "zero" to anyone reading a count,
    and they need opposite actions.
    """
    view = ledger_admin.ingestion_view(
        _Cursor({"alive": wrote(), "empty": wrote(atoms=0), "gone": wrote()}),
        declared=["alive", "empty", "quiet"])
    assert states(view) == {"alive": "ran_and_wrote",
                            "empty": "ran_wrote_nothing",
                            "quiet": "never_ran",
                            "gone": "orphan"}


def test_a_source_that_ran_and_wrote_nothing_still_carries_its_numbers():
    """Its zero is the ANSWER, so it arrives as a number rather than as a missing key -
    otherwise the row is indistinguishable from the one that never ran."""
    view = ledger_admin.ingestion_view(_Cursor({"empty": wrote(atoms=0, molecules=90)}),
                                       declared=["empty"])
    row = view["sources"][0]
    assert row["atoms_written"] == 0 and row["molecules_done"] == 90
    assert row["state"] == "ran_wrote_nothing"


def test_the_source_that_never_ran_carries_no_invented_zeros():
    """The opposite rule, and the reason the states are values: there is no row, so there
    is no count. Emitting `atoms_written: 0` here would state something nobody measured.
    """
    view = ledger_admin.ingestion_view(_Cursor({}), declared=["quiet"])
    row = view["sources"][0]
    assert row["state"] == "never_ran"
    assert "atoms_written" not in row, row


def test_an_unreadable_cursor_is_named_and_never_rendered_as_never_ran():
    """🔴 THE GUARD THIS FILE IS FOR. If the table cannot be read, every source would fall
    into the `never_ran` branch by construction - fifteen sources reported as never having
    run, from a database error. The answer is that there is no answer, said out loud."""
    view = ledger_admin.ingestion_view(
        _Cursor(raises=RuntimeError("relation does not exist")),
        declared=["alive", "empty", "quiet"])
    assert view["sources"] == []
    assert "RuntimeError" in view["unavailable"]
    assert "relation does not exist" in view["unavailable"]


def test_the_numbers_never_travel_without_the_sentence_that_says_what_they_are():
    """`atoms_written` is what the translator RECORDED WRITING. Nothing decrements it, so
    beside a ledger that has been rebuilt it is not a count of anything present. Read as
    "how many are in the ledger", it is wrong and looks authoritative."""
    view = ledger_admin.ingestion_view(_Cursor({"alive": wrote()}), declared=["alive"])
    assert view["note"], "the numbers shipped bare"
    assert "번역기" in view["note"] and "재건" in view["note"], view["note"]


def test_it_reads_the_cursor_table_and_not_the_ledger():
    """The whole reason this view exists. A query naming `ledger_events` would be the
    scan this replaces, and it would still return plausible numbers."""
    cursor = _Cursor({"alive": wrote()})
    ledger_admin.ingestion_view(cursor, declared=["alive"])
    assert len(cursor.queries) == 1, cursor.queries
    assert "ledger_translator_cursor" in cursor.queries[0]
    assert "ledger_events" not in cursor.queries[0]


def test_the_added_key_leaves_the_declaration_view_as_it_was():
    """Additive, so a reader that does not know `ingestion` is unaffected - and the form's
    own keys are asserted by name rather than by count."""
    view = ledger_admin.sources_view(_Cursor({}))
    for key in ("kinds", "unsupported_kinds", "sources", "config_path", "error"):
        assert key in view, key
    assert "ingestion" in view


# ------------------------------------------------------- WHY, not only HOW MANY

def test_a_breakdown_travels_with_the_count():
    """🔴 THE OTHER HALF OF THE PHASE'S DoD. "How many were refused" reached a screen and
    "why" did not, so an operator got as far as a number and stopped at "what do I fix".

    The reasons were never lost - they are written per source in ONE statement with the
    aggregate, so the two cannot drift - but the only code that read them hung off a route
    that retired on 2026-08-28 and took the read with it.
    """
    view = ledger_admin.ingestion_view(
        _Cursor({"alive": wrote(refused=3, reasons={"missing_occurred_at":
                                                    {"count": 3, "last_at": None}})}),
        declared=["alive"])
    row = view["sources"][0]
    assert row["refusals"] == "named"
    assert row["refusal_reasons"]["missing_occurred_at"]["count"] == 3
    assert row["refusals_unaccounted"] == 0


def test_nothing_refused_and_cannot_be_broken_down_are_DIFFERENT_states():
    """🔴 THREE STATES. `{}` is "the writer owned this row and nothing was refused"; NULL
    is "this row predates the column, so it CANNOT be broken down". Folding them puts
    `모른다` and `없다` on the same pixel - the defect this view already avoids for the
    source states beside them.

    ⛔ And the empty state is not dropped because this box happens to have no NULLs:
    fifteen rows here are all `{}`, and production is not this box.
    """
    view = ledger_admin.ingestion_view(
        _Cursor({"quiet": wrote(reasons={}), "ancient": wrote(refused=1, reasons=None)}),
        declared=["quiet", "ancient"])
    states = {r["source"]: r["refusals"] for r in view["sources"]}
    assert states == {"quiet": "none", "ancient": "unknowable"}


def test_refusals_counted_before_the_column_existed_are_reported_as_such():
    """⚠️ The SIGN carries the meaning, which is why the number travels rather than a
    boolean: >0 is deployment history, not a fault. A screen rendering "1 refused" beside
    an empty list would be reporting a bookkeeping problem that is not there."""
    view = ledger_admin.ingestion_view(
        _Cursor({"ancient": wrote(refused=4, reasons=None)}), declared=["ancient"])
    assert view["sources"][0]["refusals_unaccounted"] == 4


def test_the_unaccounted_figure_is_the_shared_one_not_a_local_sum():
    """Two spellings would disagree about a fault. `ledger_trace._unaccounted` states the
    sign convention; this view imports it."""
    from ledger_trace import _unaccounted
    assert _unaccounted({"molecules_refused": 5},
                        {"a": {"count": 2}, "b": {"count": 3}}) == 0
