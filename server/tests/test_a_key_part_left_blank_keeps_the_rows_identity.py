"""총괄 10-14 (b): a NEW row whose composite key cannot be built - one part blank - keeps the key the write gave it,
whether as `business_key_val` or as the key column (`run_uid` in the updates). The write door's rebuild put None over
it, so the row was found by nothing (B's inspection_run rows). An EXISTING row whose key part is blanked loses its key
- a61d32f4f, kept: test_a_composite_key_is_rebuilt_alike_with_or_without_a_key_column.py «part blanked».

A part the write does not CARRY is what this measures; a part carried BLANK among filled ones composes blank and the
assembled key wins over a given one (총괄 242f4a43a ㄱ2 - `test_a_blank_key_part_is_one_key_and_old_rows_are_rekeyed.py`);
`null_policy` (skip, or filled `nokey`) - `test_a_blank_key_is_filled_from_the_file_and_its_row.py`."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest                                                         # noqa: E402

from database import crud, models, schemas                            # noqa: E402

T = "keykeep_runs"
DECL = {"business_key": "run_uid", "composite_key_source": ["method", "wafer", "gate"], "composite_key_separator": "|",
        "column_types": {"run_uid": "string", "method": "string", "wafer": "string", "gate": "number",
                         "recipe": "string"}}
FULL = {"method": "aoi", "wafer": "W1", "gate": 3, "recipe": "R1"}


@pytest.fixture(params=["sqlite", pytest.param("pg", marks=pytest.mark.pg)])
def db(request):
    from sqlalchemy import MetaData, text

    session = request.getfixturevalue("pg_session" if request.param == "pg" else "db_session")
    models.init_dynamic_models({T: DECL})
    crud.TABLE_CONFIG.update({T: DECL})
    if request.param == "pg":
        from conftest import PG_TEST_SCHEMA
        scratch = MetaData(schema=PG_TEST_SCHEMA)
        models.DYNAMIC_TABLES[T].__table__.to_metadata(scratch, schema=None)
        scratch.drop_all(session.get_bind())
        scratch.create_all(session.get_bind())
    else:
        models.DYNAMIC_TABLES[T].__table__.create(bind=session.get_bind(), checkfirst=True)
    yield session
    session.rollback()
    if request.param == "pg":
        with session.get_bind().begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, T)))


def _write(db, updates, row_id=None, business_key_val=None, source="run_file.csv"):
    crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        row_id=row_id, business_key_val=business_key_val, updates=updates, source_name=source,
        updated_by="keykeep")]))
    db.expire_all()
    return [(r.business_key_val, r.run_uid, r.gate, r.recipe) for r in db.query(models.DYNAMIC_TABLES[T])]


@pytest.mark.parametrize("given", ["key column", "business_key_val"])
def test_a_new_row_missing_a_key_part_keeps_the_key_it_was_given(db, given):
    assert _write(db, FULL) == [("aoi|W1|3", "aoi|W1|3", 3, "R1")], "control: every part - the composite key"
    db.query(models.DYNAMIC_TABLES[T]).delete()
    updates = {k: v for k, v in FULL.items() if k != "gate"}
    if given == "key column":
        rows = _write(db, dict(updates, run_uid="RUN-7"))
    else:
        rows = _write(db, updates, business_key_val="RUN-7")
    assert [(bk, gate, recipe) for bk, _uid, gate, recipe in rows] == [("RUN-7", None, "R1")]
    if given == "key column":
        assert rows[0][1] == "RUN-7", "the key column keeps the value it was given"
