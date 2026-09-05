"""TEMPORAL TEXT -- the Python render and the SQL render, scored against ONE recorded answer.

The file being scored is `contracts/temporal_text/vectors.json`. Nothing here hardcodes an
expected value: every verdict comes out of that file, so deleting a case removes coverage
LOUDLY (`test_every_contract_case_is_consumed`).

    conda run -n assy_manager python -m pytest contracts/temporal_text/ -q -rs

`-rs` IS PART OF THE COMMAND. The axis that matters most -- the postgres arm, on the
dialect production actually runs -- is an opt-in skip, and a bare `-q` reports "N skipped",
which says something is unscored but not what, whose, or what it blocks.

    ASSY_CONTRACT_PG_URL=postgresql://... conda run -n assy_manager python -m pytest \
        contracts/temporal_text/ -q -rs

WHY THIS FILE EXISTS, AND WHY IT IS THE TWIN OF `notation_fold`
    `crud._TemporalText` is a `@compiles` construct with two arms, exactly like
    `notation_norm._NotationFold`. The fold got a contract on 2026-08-04; this one had
    none. Measured 2026-09-05: `contracts/` mentioned `temporal_text` nowhere, and the only
    test naming it (`test_virtual_join_types.py`) runs on `db_session` -- SQLite -- where
    the `_default` arm is a plain CAST. So the postgres arm was evaluated by nothing.

    That arm is not decoration. PostgreSQL's own `CAST(timestamptz AS varchar)` renders in
    the SESSION's timezone and omits the fraction when it is zero, so two servers holding
    the same row would compare different text and `lessThan` on a resolved temporal column
    would stop being chronological. The arm exists to remove that, and until this file
    nothing scored it.

WHAT RUNS WITHOUT POSTGRES, AND WHY THAT IS NOT NOTHING
    Two of the three axes:
      * the Python render, against the recorded expectation;
      * the SQL each arm COMPILES TO, against the recorded text -- with literal binds, so
        the format string is visible rather than a placeholder.
    Those two catch every change to the spelling. What they cannot catch is whether
    PostgreSQL EVALUATES that spelling to the same bytes; that is the third axis and it
    skips loudly.

WHAT THIS FILE DOES NOT DO
    It does not decide. Where the arms disagree the disagreement is reported, not resolved.
"""
import datetime
import json
import os
import pathlib
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT / "server") not in sys.path:
    sys.path.insert(0, str(_ROOT / "server"))

from database import crud                                        # noqa: E402

VECTORS = json.loads((pathlib.Path(__file__).parent / "vectors.json")
                     .read_text(encoding="utf-8"))
CASES = VECTORS["cases"]
PASSTHROUGH = VECTORS["passthrough"]

_CONSUMED: set = set()


def value_of(case):
    """The recorded case as the Python object it stands for."""
    raw = case["value"]
    if case.get("kind") == "date":
        return datetime.date.fromisoformat(raw)
    return datetime.datetime.fromisoformat(raw)


def compiled(dialect_name, *, literal_binds=True):
    """The SQL `temporal_text_sql` compiles to on one dialect, as text."""
    from sqlalchemy import Column, DateTime, MetaData, Table, select
    from sqlalchemy.dialects import postgresql, sqlite

    dialect = {"postgresql": postgresql.dialect(), "sqlite": sqlite.dialect()}[dialect_name]
    table = Table("probe", MetaData(), Column("ts", DateTime(timezone=True)))
    statement = select(crud.temporal_text_sql(table.c.ts))
    return " ".join(str(statement.compile(
        dialect=dialect,
        compile_kwargs={"literal_binds": literal_binds} if literal_binds else {})).split())


# ------------------------------------------------------------------ axis 1: the Python render

@pytest.mark.parametrize("case", CASES, ids=[c["label"] for c in CASES])
def test_python_render_matches_the_recorded_expectation(case):
    _CONSUMED.add(case["label"])
    assert crud.temporal_text_value(value_of(case)) == case["expected"], case["note"]


@pytest.mark.parametrize("case", PASSTHROUGH, ids=[c["label"] for c in PASSTHROUGH])
def test_a_value_that_is_not_temporal_passes_through(case):
    _CONSUMED.add(case["label"])
    assert crud.temporal_text_value(case["value"]) == case["expected"], case["note"]


def test_the_render_is_idempotent_on_its_own_output():
    """Its output is text, and text passes through -- so a second pass cannot change it.
    A render that reparsed its own output would drift on every re-resolution."""
    for case in CASES:
        once = crud.temporal_text_value(value_of(case))
        assert crud.temporal_text_value(once) == once


def test_every_render_is_the_same_width():
    """The pin is a FIXED width, which is what makes `lessThan` on the text chronological.
    A variable-width render sorts `...:09` after `...:10`."""
    widths = {len(crud.temporal_text_value(value_of(c))) for c in CASES}
    assert widths == {26}, widths


def test_the_text_sorts_in_the_same_order_as_the_instants():
    """🔴 THE PROPERTY THE WHOLE PIN EXISTS FOR. If these two orders can differ, a filter
    on a resolved temporal column answers a different question than the column does."""
    naive = [c for c in CASES if value_of(c).__class__ is datetime.datetime
             and value_of(c).tzinfo is None]
    by_instant = [c["label"] for c in sorted(naive, key=value_of)]
    by_text = [c["label"] for c in sorted(naive, key=lambda c: c["expected"])]
    assert by_instant == by_text


# ------------------------------------------------- axis 2: the SQL each arm compiles to

def test_the_postgres_arm_compiles_to_the_recorded_spelling():
    """🔴 THE ARM NOTHING EVALUATED. `to_char(timezone('UTC', ...), '...')` is the whole
    repair: `timezone('UTC', ...)` stops the session GUC from choosing, and `.US` keeps six
    digits when the fraction is zero."""
    assert VECTORS["compiled_sql"]["postgresql"] in compiled("postgresql")


def test_the_sqlite_arm_compiles_to_the_recorded_spelling():
    assert VECTORS["compiled_sql"]["sqlite"] in compiled("sqlite")


def test_the_two_arms_are_not_the_same_sql():
    """If they ever compiled identically, one of them would be dead -- and the suite would
    be scoring the surviving one twice while reporting two."""
    assert compiled("postgresql") != compiled("sqlite")


def test_the_format_string_is_visible_and_not_a_placeholder():
    """⚠️ WHY `literal_binds`. The format rides as a BOUND PARAMETER, so a compile without
    it renders `%(to_char_1)s` -- and a changed format would score identical."""
    assert VECTORS["format"]["postgres"] in compiled("postgresql")
    assert VECTORS["format"]["postgres"] not in compiled("postgresql", literal_binds=False)


def test_the_two_format_constants_agree_on_what_they_describe():
    """One is `strftime`, the other is `to_char`; they are different languages for one
    layout, and this is the only place that says so."""
    import re

    python, postgres = VECTORS["format"]["python"], VECTORS["format"]["postgres"]
    assert python == crud.TEMPORAL_TEXT_FORMAT
    assert postgres == crud._PG_TEMPORAL_TEXT_FORMAT
    # The MEMBERS, not a count: a directive swapped for another keeps the count identical.
    assert re.findall(r"%.", python) == ["%Y", "%m", "%d", "%H", "%M", "%S", "%f"]
    assert postgres == "YYYY-MM-DD HH24:MI:SS.US"
    # 🔴 `%f` and `.US` are the pair the whole pin turns on -- six digits, always.
    assert python.endswith("%f") and postgres.endswith(".US")


# ------------------------------------- 🔴 the contract has to be shown to go red

def test_the_corpus_catches_a_deliberately_wrong_python_render():
    """A CONTRACT THAT HAS NEVER GONE RED PROVES NOTHING. Two regressions somebody would
    actually write: dropping the microseconds, and rendering in local time. Each must be
    caught by at least one recorded case."""
    def trimmed(value):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def local(value):
        return value.replace(tzinfo=None).strftime(crud.TEMPORAL_TEXT_FORMAT)

    caught_trim = [c for c in CASES if trimmed(value_of(c)
                   if isinstance(value_of(c), datetime.datetime)
                   else datetime.datetime.combine(value_of(c), datetime.time()))
                   != c["expected"]]
    assert caught_trim, "no case notices a render that drops the fraction"

    aware = [c for c in CASES if isinstance(value_of(c), datetime.datetime)
             and value_of(c).tzinfo is not None]
    assert aware, "the corpus has no aware value, so 'renders in local time' is unscored"
    assert [c for c in aware if local(value_of(c)) != c["expected"]], (
        "no aware case notices a render that skips the UTC normalisation")


def test_the_corpus_catches_a_deliberately_wrong_sql_spelling():
    """The two SQL regressions with the same shape: a bare CAST on postgres (the dialect
    default this arm exists to override), and `.MS` for `.US` (three digits, not six)."""
    recorded = VECTORS["compiled_sql"]["postgresql"]
    assert "CAST(probe.ts AS VARCHAR)" != recorded
    assert recorded.replace(".US", ".MS") != recorded


# ----------------------------------------------------- axis 3: postgres, opt-in and loud

_PG_SKIP = (
    "PENDING AXIS -- the postgres render is UNSCORED on this run. It cannot be scored on "
    "the suite dialect: SQLite compiles `temporal_text_sql` to a plain "
    "`CAST(ts AS VARCHAR)`, which is the arm that never had the defect, so evaluating it "
    "proves nothing about the one that repairs it. Blocks: EVERY value assertion that "
    "PostgreSQL's `to_char(timezone('UTC', ts), 'YYYY-MM-DD HH24:MI:SS.US')` evaluates to "
    "the recorded text -- and with it the claim that two servers in different session "
    "timezones compare the same string. Owner: whoever runs the suite. Run with "
    "ASSY_CONTRACT_PG_URL=postgresql://... to score it. NOT YET MEASURED against a real "
    "PostgreSQL: this contract was written 2026-09-05 without one, so unlike "
    "contracts/notation_fold there is no recorded pass to cite here.")


def _pg_cursor():
    url = os.environ.get("ASSY_CONTRACT_PG_URL")
    if not url:
        pytest.skip(_PG_SKIP)
    import psycopg2

    conn = psycopg2.connect(url, connect_timeout=5)
    # READ ONLY, scalar only: no table is named and no row is read. The render is a pure
    # expression, so this axis never needs the operator's data.
    conn.set_session(readonly=True, autocommit=True)
    return conn.cursor()


@pytest.mark.parametrize("case", CASES, ids=[c["label"] for c in CASES])
def test_postgres_render_matches_the_recorded_expectation(case):
    """🔴 THE LOAD-BEARING ASSERTION. Everything above scores the SPELLING; this is the
    only axis that scores what PostgreSQL DOES with it."""
    cursor = _pg_cursor()
    cursor.execute(
        "select to_char(timezone('UTC', %s::timestamptz), %s)",
        (value_of(case).isoformat(), crud._PG_TEMPORAL_TEXT_FORMAT))
    assert cursor.fetchone()[0] == case["expected"], case["note"]


def test_postgres_agrees_with_python_case_by_case():
    """Both are scored against the record above; this scores them against EACH OTHER, so a
    disagreement is reported as a disagreement rather than as two separate failures."""
    cursor = _pg_cursor()
    disagreed = []
    for case in CASES:
        cursor.execute(
            "select to_char(timezone('UTC', %s::timestamptz), %s)",
            (value_of(case).isoformat(), crud._PG_TEMPORAL_TEXT_FORMAT))
        got = cursor.fetchone()[0]
        mine = crud.temporal_text_value(value_of(case))
        if got != mine:
            disagreed.append((case["label"], mine, got))
    assert not disagreed, disagreed


def test_the_session_timezone_does_not_move_the_answer():
    """⚠️ THE DEFECT ITSELF, as an assertion. `timezone('UTC', ...)` is what makes this
    true; without it the same row reads differently on two servers."""
    cursor = _pg_cursor()
    answers = set()
    for zone in ("UTC", "Asia/Seoul", "America/New_York"):
        cursor.execute("set time zone %s", (zone,))
        cursor.execute(
            "select to_char(timezone('UTC', %s::timestamptz), %s)",
            ("2026-08-03T12:23:39.123456+00:00", crud._PG_TEMPORAL_TEXT_FORMAT))
        answers.add(cursor.fetchone()[0])
    assert len(answers) == 1, answers


# --------------------------------------------------------------------- the corpus is used

def test_every_contract_case_is_consumed():
    """Deleting a case must remove coverage LOUDLY. A vector nothing reads is a vector
    that can be edited to say anything."""
    labels = {c["label"] for c in CASES} | {c["label"] for c in PASSTHROUGH}
    assert labels - _CONSUMED == set(), sorted(labels - _CONSUMED)


def test_the_corpus_covers_the_classes_this_seam_can_fail_in():
    """The recorded reasons, as a checklist. A corpus that lost one of these would still
    pass every assertion above while covering less."""
    labels = {c["label"] for c in CASES}
    for required in ("whole_second",      # the fraction PostgreSQL's CAST drops
                     "one_microsecond",   # the digit a shorter format loses
                     "aware_plus_nine",   # the offset a session-timezone render follows
                     "aware_minus_five",  # the offset that moves the DAY
                     "single_digit_parts"):  # the padding an unpadded render loses
        assert required in labels, "%s left the corpus" % required
