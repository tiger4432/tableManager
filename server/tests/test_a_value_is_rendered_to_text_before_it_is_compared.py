# -*- coding: utf-8 -*-
"""비교하기 «전»에 텍스트로 만든다 — 그리고 그 철자는 «고정»이다.

🪦 [S-283] THESE ASSERTIONS CAME OUT OF `test_virtual_join_types.py`, which died with the
read-time join. Most of that file measured the JOIN SEAM: which SQLAlchemy types an `expose`
column could be, and whether the joined value reached the payload. That seam is gone.

🔴 WHAT SURVIVED IS THE FUNNEL, AND IT HAS OTHER CONSUMERS. `crud.column_text_sql` is called
by `enrichment/mapper.py` (blank conditions) and referenced by `column_filter` and
`notation_norm`; `comparison_text_value` is what `column_filter` renders an AG-Grid JSON
value through before comparing it to a text expression. One of the carried tests says so in
its own words - 「No fixture and no database: the subject is the funnel, not the seam」 - which
is why it is here rather than in the grave with its neighbours.

⚠️ THE DEFECT SHAPE THESE CLOSE (N7/N8). Comparing a text expression against a TYPED bind is
a dialect lottery: PostgreSQL raises, SQLite silently matches nothing. Rendering both sides
through one funnel is what makes those two answer the same.
"""
import datetime

from database import crud

T_MICRO = datetime.datetime(2026, 8, 4, 6, 23, 39, 123456)
T_ZERO = datetime.datetime(1999, 1, 2, 3, 4, 5, 0)
T_MICRO_TEXT = "2026-08-04 06:23:39.123456"
T_ZERO_TEXT = "1999-01-02 03:04:05.000000"


def test_a_type_the_funnel_has_never_heard_of_is_cast_not_passed_through():
    """The no-crash floor. `column_text_sql` decides by asking "is this ALREADY text",
    so a type added tomorrow gets a CAST rather than reopening N7/N8 a third time."""
    from sqlalchemy import Column, LargeBinary, JSON, Enum
    from sqlalchemy.sql import sqltypes
    for col in (Column("blob_col", LargeBinary), Column("json_col", JSON),
                Column("enum_col", Enum("a", "b", name="probe_enum"))):
        expr = crud.column_text_sql(col)
        assert isinstance(expr.type, sqltypes.String), f"{col.name} was not rendered to text"
        assert "CAST" in str(expr.compile(compile_kwargs={"literal_binds": True})).upper(), (
            f"{col.name} reached the COALESCE without a cast - this is the N7/N8 shape")


def test_the_type_bridge_still_spells_a_bool_and_a_timestamp_the_way_sql_does():
    """A Boolean VALUE still reaches the filter funnel: AG-Grid sends a JSON `true` for any
    column it treats as boolean and `column_filter` renders it through
    `comparison_text_value` before comparing it against a text expression.

    No fixture and no database: the subject is the funnel, not the seam.
    """
    assert crud.boolean_text_value(True) == "true", "'True' is the spelling no operator sees"
    assert crud.clean_str_value(True) == "True", (
        "if this ever became 'true', the two spellings merged and the bridge is moot")
    assert crud.comparison_text_value(True) == "true"
    assert crud.comparison_text_value(T_MICRO) == T_MICRO_TEXT


def test_the_temporal_text_is_pinned_not_the_dialects_default():
    """The canonical spelling: UTC, space separator, SIX microsecond digits, always.

    PostgreSQL's own `CAST(timestamptz AS varchar)` renders in the SESSION's timezone and
    omits the fractional part when it is zero - so two servers holding the same row would
    compare different text. `T_ZERO` is here for exactly that second half.

    ⚠️ 이 시험의 «SQL 쪽 절반»은 조인 좌석과 함께 사라졌습니다 — 그쪽은 조인해 온 컬럼을
    읽어야 했습니다. 남은 것은 파이썬 쪽 철자이고, 그것이 두 쪽을 같게 만드는 정본입니다.
    """
    assert crud.temporal_text_value(T_MICRO) == T_MICRO_TEXT
    assert crud.temporal_text_value(T_ZERO) == T_ZERO_TEXT, (
        "a whole-second timestamp lost its .000000 - the dialect default leaked in")
    # An aware value is normalised to UTC, so the text does not follow a session GUC.
    aware = T_MICRO.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
    assert crud.temporal_text_value(aware) == "2026-08-03 21:23:39.123456"
