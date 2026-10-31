# -*- coding: utf-8 -*-
"""총괄 f36abbb1a ② — 인덱스 보고(`unique_key`)의 「빈 키」와 조인의 「빈 키」는 판정 하나(`crud.every_key_part_blank`).
쓰기 가드도 그것을 지난다(소유자 10-20).

접기 전에 둘이 갈린 값은 실수 nan · inf · -inf 셋이었다. 🔴 10-31 총괄 ② 부터 PostgreSQL 의 키 «식»도
float 칸을 원장 철자(`assy_key_number`)로 읽어 그 셋이 NULL — 보고에서도 빈 키다(전엔 'NaN' 글자로 와서 중복이었다).
"""
import os
import sys

import pytest
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import unique_key                                       # noqa: E402
from database.database import Base                                 # noqa: E402
from database import crud, models                                  # noqa: E402

VALUES = [None, "", " ", "\t", "　", float("nan"), float("inf"), float("-inf"), 2.0 ** 53, -1e23, 0, 0.0,
          False, "0", "nan", "NaN", "Infinity", "x"]


@pytest.mark.parametrize("value", VALUES, ids=[repr(v) for v in VALUES])
def test_a_one_part_key_is_blank_as_its_part_is(value):
    assert crud.every_key_part_blank((value,)) == crud.is_blank_key_part(value)


def test_a_non_finite_number_is_blank_to_both():
    assert all(crud.every_key_part_blank((v,)) for v in (float("nan"), float("inf"), float("-inf")))


TABLE = "s36f_number_key"
TABLES = {TABLE: {"business_key": "k", "composite_key_source": ["k"],
                  "column_types": {"k": "number"}, "display_columns": ["k"]}}


@pytest.mark.pg
def test_the_index_report_reads_a_nan_key_as_a_blank_like_null(pg_engine):
    """🔴 TURNED (lead 10-31 ②, was «a NaN key is a duplicate, not a blank»): the key EXPRESSION spells a float
    column by `assy_key_number`, the ledger's speller, so a NaN arrives NULL -> '' and sits with the NULL rows."""
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
            {"row_id": "E2", "business_key_val": "E2", "k": None},
            {"row_id": "B1", "business_key_val": "B1", "k": 2.0 ** 53},            # past 2^53: blank too (lead 10-31)
            {"row_id": "B2", "business_key_val": "B2", "k": -1e23}])
        db.commit()

        duplicates, blanks = unique_key.duplicate_keys(db, TABLE, ["k"])

        assert duplicates == []
        assert blanks == [{"key": [""], "rows": 6}], "NaN and past-2^53 keys are COUNTED with the blank ones"
    finally:
        db.rollback()
        db.close()
        crud.TABLE_CONFIG.pop(TABLE, None)
