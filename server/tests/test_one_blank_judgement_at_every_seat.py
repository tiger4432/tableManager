# -*- coding: utf-8 -*-
"""Owner 11-08 1ㄱ 2ㄱ 3ㄱ: «is this blank» is ONE judgement, `crud.is_blank_value`, and every seat asks it - a seat
that differs says how by an argument there (containers · identity · spaces=False), not by a judgement of its own. An
infinite number is not blank: it is refused by name at the write, in every column.

  values  None · '  ' · float NaN · Decimal NaN · pd.NA · NaT · inf · 'nan' · [] · {}
  seats   is_blank_value · none_if_blank · row_is_blank · is_blank_key_part · expression.is_blank ·
          mapper_call._is_missing_scalar · roleframe._is_missing · roleframe.is_blank_source_value ·
          pipeline_base.clean_for_postgres - every cell asserted
  write   a float NaN into a text column is blank, not a stored «nan» · inf refused by name in a number, a text and a
          time column, the not-written sentence says «an infinite value» · the entrances pass inf on, NaN as None
"""
import decimal
import math

import pandas as pd
import pytest
import uuid6

from conftest import retire_dynamic_model
from database import crud, models, schemas

NAN, INF = float("nan"), float("inf")
VALUES = {"None": None, "spaces": "  ", "nan": NAN, "Decimal NaN": decimal.Decimal("NaN"), "pd.NA": pd.NA,
          "NaT": pd.NaT, "inf": INF, "'nan'": "nan", "[]": [], "{}": {}}
#: the one judgement, and each argument's difference - the columns of VALUES in order
ANSWERS = {
    "blank": [True, True, True, True, True, True, False, False, False, False],
    "containers": [True, True, True, True, True, True, False, False, True, True],
    "identity": [True, True, True, True, True, True, True, False, False, False],
    "absent": [True, False, True, True, True, True, False, False, False, False],
}


def _pipeline(value):
    from parsers.pipeline_base import BasePipelineParser

    return BasePipelineParser().clean_for_postgres(pd.DataFrame({"c": pd.Series([value], dtype=object)}))[0]["c"] is None


def _seats():
    import expression
    from chain import mapper_call
    from ledger import roleframe

    return {
        "is_blank_value": (crud.is_blank_value, "blank"),
        "none_if_blank": (lambda v: crud.none_if_blank(v) is None, "blank"),
        "row_is_blank": (lambda v: crud.row_is_blank([v]), "blank"),
        "is_blank_source_value": (roleframe.is_blank_source_value, "blank"),
        "is_blank_key_part": (crud.is_blank_key_part, "identity"),
        "expression.is_blank": (expression.is_blank, "containers"),
        "mapper_call._is_missing_scalar": (mapper_call._is_missing_scalar, "absent"),
        "roleframe._is_missing": (roleframe._is_missing, "absent"),
        "pipeline_base.clean_for_postgres": (_pipeline, "absent"),
    }


def test_every_seat_gives_the_one_judgement_s_answer_with_its_own_argument():
    got = {seat: [bool(ask(v)) for v in VALUES.values()] for seat, (ask, _kind) in _seats().items()}
    want = {seat: ANSWERS[kind] for seat, (_ask, kind) in _seats().items()}
    assert got == want, {seat: dict(zip(VALUES, got[seat])) for seat in got if got[seat] != want[seat]}
    # each argument the one judgement's own, asked directly
    asked = {"blank": {}, "containers": {"containers": True}, "identity": {"identity": True}, "absent": {"spaces": False}}
    assert {kind: [crud.is_blank_value(v, **kw) for v in VALUES.values()] for kind, kw in asked.items()} == ANSWERS


@pytest.mark.parametrize("col_type", ["number", "string", "datetime"])
def test_an_infinite_number_is_refused_by_name_in_every_column(col_type):
    with pytest.raises(crud.CellRefused) as refused:
        crud.cast_value_by_type(INF, col_type, "v", "t")
    assert refused.value.column == "v" and "infinite value" in str(refused.value), str(refused.value)
    assert crud.cast_value_by_type(NAN, col_type, "v", "t") is None, "a NaN is blank in every column"


def test_the_text_nan_and_inf_stay_text_and_are_refused_by_a_number_column_as_they_are():
    assert crud.cast_value_by_type("nan", "string", "v", "t") == "nan"
    assert crud.cast_value_by_type("inf", "string", "v", "t") == "inf"
    with pytest.raises(crud.CellRefused) as not_a_number:
        crud.cast_value_by_type("nan", "number", "v", "t")
    assert "a number" in str(not_a_number.value)
    with pytest.raises(crud.CellRefused) as infinite:
        crud.cast_value_by_type("inf", "number", "v", "t")
    assert "infinite value" in str(infinite.value)


def test_the_entrances_turn_nan_into_none_and_pass_inf_on_to_the_write():
    from chain import mapper_call

    out = mapper_call.without_missing({"updates": [{"updates": {"a": NAN, "b": INF, "c": "  "}}]})
    cells = out["updates"][0]["updates"]
    assert cells["a"] is None and cells["b"] == INF and cells["c"] == "  ", cells
    assert _pipeline(NAN) is True and _pipeline(INF) is False


TABLE = "blank_probe"
ENTRY = {"business_key": "k", "column_types": {"k": "string", "note": "string", "n": "number"}}


@pytest.fixture(name="probe")
def fixture_probe(db_session, monkeypatch):
    for name in ("_undeclared_column_drops", "_undeclared_column_warned", "_undeclared_column_drops_over_budget"):
        monkeypatch.setattr(crud, name, {})
    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    bind = db_session.get_bind()
    models.DYNAMIC_TABLES[TABLE].__table__.create(bind=bind)
    try:
        yield models.DYNAMIC_TABLES[TABLE]
    finally:
        db_session.rollback()
        for gone in (models.CellSource, models.CellOverwrite, models.AuditLog, models.DatabaseOutbox):
            db_session.query(gone).filter(gone.table_name == TABLE).delete()
        db_session.commit()
        models.DYNAMIC_TABLES[TABLE].__table__.drop(bind=bind)
        retire_dynamic_model(TABLE)


def _write(db_session, updates):
    report = {}
    crud.apply_batch_updates(db_session, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates=updates, source_name="user", updated_by="kim")]), drop_report=report)
    return report


def test_a_float_nan_into_a_text_column_is_written_blank(probe, db_session):
    _write(db_session, {"k": "a", "note": "x"})
    _write(db_session, {"k": "a", "note": NAN})
    row = db_session.query(probe).filter(probe.k == "a").one()
    layers = db_session.query(models.CellSource.value).filter(
        models.CellSource.table_name == TABLE, models.CellSource.column_name == "note").all()
    assert row.note is None, repr(row.note)
    assert not [v for (v,) in layers if isinstance(v, float) and math.isnan(v) or str(v).lower() == "nan"], layers


@pytest.mark.parametrize("column", ["note", "n"])
def test_an_infinite_number_is_not_written_and_the_sentence_says_so(probe, db_session, column):
    report = _write(db_session, {"k": "b", column: INF})
    row = db_session.query(probe).filter(probe.k == "b").one()
    assert getattr(row, column) is None, repr(getattr(row, column))
    sentence = crud.not_written_sentence(report["by_reason_column"],
                                         "Not written", {c: s["first"] for c, s in report["refused_values"].items()})
    assert sentence and column in sentence and "an infinite value" in sentence, (sentence, report)


@pytest.mark.pg
def test_a_number_column_s_nan_is_blank_in_sql_and_a_text_column_s_is_a_value(pg_session):
    from sqlalchemy import Column, Float, MetaData, String, Table, cast, func, select

    table = Table("blank_sql_probe", MetaData(), Column("f", Float), Column("t", String))
    table.create(pg_session.get_bind())
    try:
        pg_session.execute(table.insert(), [{"f": NAN, "t": "NaN"}, {"f": 1.5, "t": "x"}, {"f": None, "t": None},
                                            {"f": 7.0, "t": ""}])

        def count(where):
            return pg_session.execute(select(func.count()).select_from(table).where(where)).scalar()
        assert count(crud.blank_sql_condition(cast(table.c.f, String))) == 2, "NaN and NULL"
        assert count(crud.blank_sql_condition(crud.column_text_sql(table.c.f))) == 2, "NaN and NULL"
        assert count(crud.not_blank_sql_condition(cast(table.c.f, String))) == 2
        assert count(crud.blank_sql_condition(table.c.t)) == 2, "NULL and '' - the text «NaN» is a value"
    finally:
        pg_session.rollback()
        table.drop(pg_session.get_bind())
