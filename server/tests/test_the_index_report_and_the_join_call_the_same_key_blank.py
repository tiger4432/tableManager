# -*- coding: utf-8 -*-
"""총괄 f36abbb1a ② — 인덱스 보고(`unique_key`)의 「빈 키」와 조인의 「빈 키」는 판정 하나.

접기 전에 둘이 갈린 값은 실수 nan · inf · -inf 셋이었다. 인덱스 보고에는 키 «식»(텍스트로
캐스트)이 들어오므로 PostgreSQL 에서는 그 셋이 문자열로 와서 보고 문장은 안 바뀐다 — 아래 pg 칸.
"""
import os
import sys

import pytest
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import join_into, unique_key                            # noqa: E402
from database.database import Base                                 # noqa: E402
from database import crud, models                                  # noqa: E402

VALUES = [None, "", " ", "\t", "　", float("nan"), float("inf"), float("-inf"), 0, 0.0,
          False, "0", "nan", "NaN", "Infinity", "x"]


@pytest.mark.parametrize("value", VALUES, ids=[repr(v) for v in VALUES])
def test_the_index_report_and_the_join_answer_blank_alike(value):
    assert unique_key._is_blank(value) == join_into._every_part_blank((value,))
    assert unique_key._is_blank(value) == crud.is_blank_key_part(value)


def test_a_non_finite_number_is_blank_to_both():
    assert all(unique_key._is_blank(v) for v in (float("nan"), float("inf"), float("-inf")))


TABLE = "s36f_number_key"
TABLES = {TABLE: {"business_key": "k", "composite_key_source": ["k"],
                  "column_types": {"k": "number"}, "display_columns": ["k"]}}


@pytest.mark.pg
def test_the_index_report_reads_text_so_a_nan_key_is_a_duplicate_not_a_blank(pg_engine):
    """What reaches `_is_blank` on PostgreSQL is the key EXPRESSION, cast to text - so a NaN
    key arrives as 'NaN' and is a duplicate, a NULL arrives as '' and is a blank."""
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=pg_engine)
    models.sync_dynamic_tables_schema(pg_engine)
    db = sessionmaker(bind=pg_engine)()
    try:
        model = models.DYNAMIC_TABLES[TABLE]
        db.execute(model.__table__.insert(), [
            {"row_id": "N1", "business_key_val": "N1", "k": float("nan")},
            {"row_id": "N2", "business_key_val": "N2", "k": float("nan")},
            {"row_id": "E1", "business_key_val": "E1", "k": None},
            {"row_id": "E2", "business_key_val": "E2", "k": None}])
        db.commit()

        duplicates, blanks = unique_key.duplicate_keys(db, TABLE, ["k"])

        assert duplicates == [{"key": ["NaN"], "rows": 2}]
        assert blanks == [{"key": [""], "rows": 2}]
    finally:
        db.rollback()
        db.close()
        crud.TABLE_CONFIG.pop(TABLE, None)
