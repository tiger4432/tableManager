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


def wrote(indexed=10, refused=0, reasons=None, measured=True):
    """One registry row, in the shape a writer leaves it (S-113 ⓒ).

    ⚠️ `indexed` IS THE CENSUS, NOT A COUNTER. The row used to carry `atoms_written` and
    the view read it to decide whether the source had done anything; since S-76 nothing
    writes that column, so the discriminator is now the paced measurement of how many of
    the relation's rows the index names. `measured=False` is the third answer: a row whose
    census has not been taken says nothing, which is not the same as saying zero.
    """
    census = ({"source": "s", "relation": "r", "measured_at": "2026-09-10T00:00:00+00:00",
               "indexed_rows": {"estimate": indexed}} if measured else None)
    return {"translator_ver": "ledger-v2:abc", "molecules_refused": refused,
            "refusal_reasons": reasons, "row_census": census, "updated_at": None}


def states(view):
    return {row["source"]: row["state"] for row in view["sources"]}


def test_each_state_is_a_value_and_each_is_a_different_instruction():
    """🔴 EACH OF THESE IS A DIFFERENT INSTRUCTION TO AN OPERATOR, and most are invisible
    on the box this shipped from, so they are fed in.

        ran_and_wrote      nothing to do
        ran_wrote_nothing  the source is wired and produced nothing - look at the source
        never_ran          the index names none of its rows and nothing was refused
        orphan             a registry row whose source is no longer declared
        not_measured       the census has not reached it - 「모른다」, not 「없다」

    The middle pair is what matters: both are "zero" to anyone reading a count, and they
    need opposite actions.

    ⚰️ `never_ran` USED TO MEAN 「NO ROW」 and that stopped being true at S-76: nothing
    creates a row on the live path any more, so every source declared after it read as
    never having run however much it had translated. The discriminator is the census now,
    and 「no row」 became `not_measured` - which is what an unwritten row actually says.
    """
    view = ledger_admin.ingestion_view(
        _Cursor({"alive": wrote(), "empty": wrote(indexed=0, refused=3),
                 "quiet": wrote(indexed=0), "pending": wrote(measured=False),
                 "gone": wrote()}),
        declared=["alive", "empty", "quiet", "pending", "absent"])
    assert states(view) == {"alive": "ran_and_wrote",
                            "empty": "ran_wrote_nothing",
                            "quiet": "never_ran",
                            "pending": "not_measured",
                            "absent": "not_measured",
                            "gone": "orphan"}


def test_a_census_that_refused_to_count_is_not_a_zero():
    """⛔ 「셀 수 없다」 AND 「한 것이 없다」 ARE DIFFERENT SENTENCES. A relation that was
    dropped makes the census refuse, and reading that as `indexed_rows = 0` would report
    the source as never having run - the oldest recurring defect in this repository, an
    absence and a correct zero rendering identically."""
    row = wrote(indexed=0)
    row["row_census"] = {"source": "s", "relation": "r", "refused": "relation is gone",
                         "remedy": "declare it or drop the source"}
    view = ledger_admin.ingestion_view(_Cursor({"broken": row}), declared=["broken"])
    assert view["sources"][0]["state"] == "not_measured"


def test_a_source_that_ran_and_wrote_nothing_still_carries_its_numbers():
    """Its zero is the ANSWER, so it arrives as a number rather than as a missing key -
    otherwise the row is indistinguishable from the one nobody has measured."""
    view = ledger_admin.ingestion_view(
        _Cursor({"empty": wrote(indexed=0, refused=90, reasons={})}), declared=["empty"])
    row = view["sources"][0]
    assert row["molecules_refused"] == 90
    assert row["row_census"]["indexed_rows"]["estimate"] == 0
    assert row["state"] == "ran_wrote_nothing"


def test_the_source_with_no_row_carries_no_invented_zeros():
    """The opposite rule, and the reason the states are values: there is no row, so there
    is no count. Emitting `molecules_refused: 0` here would state something nobody
    measured."""
    view = ledger_admin.ingestion_view(_Cursor({}), declared=["quiet"])
    row = view["sources"][0]
    assert row["state"] == "not_measured"
    assert "molecules_refused" not in row and "row_census" not in row, row


def test_the_answer_carries_what_each_state_means():
    """The screen renders what it was told rather than keeping its own copy of the rule
    (ruling 223) - so a state that changes meaning cannot go on being drawn the old way."""
    view = ledger_admin.ingestion_view(_Cursor({"alive": wrote()}), declared=["alive"])
    assert set(view["states"]) == {
        ledger_admin.SOURCE_RAN_AND_WROTE, ledger_admin.SOURCE_RAN_WROTE_NOTHING,
        ledger_admin.SOURCE_NEVER_RAN, ledger_admin.SOURCE_ORPHAN,
        ledger_admin.SOURCE_NOT_MEASURED}
    assert view["states"][states(view)["alive"]], view["states"]
    assert all(view["states"].values()), view["states"]


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
