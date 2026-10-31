"""Lead 10-31 ② (owner ㄱ): a float or numeric key had two spellers - the ledger's `map_overlay.canonical_key_value`
(1e15 -> '1000000000000000', NaN -> None) and the join's `::text` (1e15 -> '1e+15', NaN -> 'NaN'). Now one:
`assy_key_number` in PostgreSQL, the same Python function under that name in SQLite, and both renderings of a key
expression call it. Each engine is scored against the answers recorded here, not only against the other.

  the cells   float8 · numeric values, edges 1e15 · 1e16 · 1e19 · NaN · ±inf · -0.0 · NULL
  the seats   the PostgreSQL function · the Python speller · the SQLite function · a join's WHERE on an index built
              from the index expression (and the index comparator recognises that index)
"""
import math
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

import map_overlay
import notation_norm
from chain import join_key_index as vjc

pytestmark = pytest.mark.pg

#: a whole number is its integer; a fraction is float8::text (the exponent from 1e15 up); NaN · ±inf · |x| >= 2^53
#: (`crud.KEY_EXACT_LIMIT`) are blank - such a float cannot tell neighbouring integers apart, and the engines parted
#: on 1e23 (lead 10-31 ㄱ). The near-edge fractions are where an unproven disagreement below 2^53 would show.
FLOATS = [(9.0, "9"), (-0.0, "0"), (1.5, "1.5"), (1e15, "1000000000000000"), (2.0 ** 53 - 1, "9007199254740991"),
          (2.0 ** 53, None), (2.0 ** 53 + 2, None), (-(2.0 ** 53), None), (1e16, None), (1e23, None),
          (1000000000000000.5, "1.0000000000000005e+15"), (2.0 ** 52 + 0.5, "4503599627370496"),
          (2.0 ** 51 + 0.5, "2.2517998136852485e+15"),
          (0.1 + 0.2, "0.30000000000000004"), (1 / 3, "0.3333333333333333"), (1e-07, "1e-07"), (5e-324, "5e-324"),
          (0.0001, "0.0001"), (1.5e-07, "1.5e-07"), (123456.789, "123456.789"),
          (math.nan, None), (math.inf, None), (-math.inf, None), (None, None)]
#: a numeric reads as Python reads it: an integer text exactly, anything else through float - NaN blank too
NUMERICS = [("9.0", "9"), ("1.50", "1.5"), ("0.1000", "0.1"), ("12", "12"), ("123.4500", "123.45"), ("NaN", None),
            ("12345678901234567", "12345678901234567"), ("12345678901234567.0", None)]


@pytest.fixture(name="pg")
def fixture_pg(pg_engine):
    with pg_engine.begin() as conn:
        conn.connection.cursor().execute(notation_norm.key_number_sql())
    return pg_engine


def test_the_python_speller_gives_the_recorded_answers():
    assert [map_overlay.canonical_key_value(v, "number") for v, _ in FLOATS] == [e for _, e in FLOATS]
    assert [map_overlay.canonical_key_value(Decimal(v), "number") for v, _ in NUMERICS] == [e for _, e in NUMERICS]


def test_postgresql_gives_the_recorded_answers(pg):
    with pg.connect() as conn:
        floats = [conn.execute(text("SELECT assy_key_number(CAST(:v AS double precision))"), {"v": v}).scalar()
                  for v, _ in FLOATS]
        numerics = [conn.execute(text("SELECT assy_key_number(CAST(:v AS numeric))"), {"v": v}).scalar()
                    for v, _ in NUMERICS]
    assert floats == [e for _, e in FLOATS]
    assert numerics == [e for _, e in NUMERICS]


def test_sqlite_gives_the_recorded_answers():
    notation_norm.install_sqlite_fold()
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        got = [conn.execute(text("SELECT assy_key_number(:v)"), {"v": v}).scalar() for v, _ in FLOATS]
    assert got == [e for _, e in FLOATS]


def test_a_join_finds_a_1e15_key_through_the_index_it_is_built_on(pg):
    expression = notation_norm.key_expression_text('"k"', None, text_column=False, number_column=True)
    with pg.begin() as conn:
        conn.execute(text("CREATE TEMP TABLE float_key (row_id text, k double precision)"))
        conn.execute(text("INSERT INTO float_key VALUES ('a', 1e15), ('b', 9.0), ('c', 'NaN'), ('d', NULL)"))
        conn.execute(text("CREATE INDEX float_key_ix ON float_key (%s)" % expression))
        found = conn.execute(text("SELECT row_id FROM float_key WHERE %s IN ('1000000000000000', '9') ORDER BY 1"
                                  % expression)).scalars().all()
        blank = conn.execute(text("SELECT row_id FROM float_key WHERE %s = '' ORDER BY 1"
                                  % expression)).scalars().all()
        built = conn.execute(text("SELECT pg_get_indexdef(to_regclass('float_key_ix'), 1, true)")).scalar()
    assert found == ["a", "b"], "the ledger's spelling of 1e15 and 9.0 finds the rows"
    assert blank == ["c", "d"], "NaN is blank like NULL, as the ledger folds it"
    assert vjc.normalize_index_expression(built) == vjc.normalize_index_expression(expression), built
