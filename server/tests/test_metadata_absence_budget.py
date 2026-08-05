"""[P2] "Not in the prefetch cache" must mean "has no metadata", not "unknown".

`apply_batch_updates` prefetches every `cell_sources`/`cell_overwrites` row for the
rows the batch resolves up front, with NO column filter. `_load_metadata_row_cell`
then treated a missing cache key as "I do not know" and issued two SELECTs per
cell - so writing a column that has never been written before cost two round
trips per row to be told, every time, that there is nothing there.

🔴 THE GUARD IS PER-ROW MEMBERSHIP IN THE PREFETCHED SET, NOT "the row exists".
The equivalence is only bought by the prefetch's lack of a column filter, and it
is only bought for the rows that prefetch actually covered. A row can be resolved
mid-batch and never have been prefetched, and answering "empty" for it would
silently discard its stored `user` layer.

⚠️ AMENDED BY P6 (composite key assembled before the prefetch). When this module
was written, the example of such a row was "the payload carries the key's SOURCE
COLUMNS but not the key, so the prefetch filter never saw it" - which was every row
of every composite-keyed write. P6 moved that assembly ahead of the prefetch
filter, so those rows are now covered and answering "empty" for them is CORRECT
rather than dangerous. `test_row_resolved_after_the_prefetch_still_reads_its_
metadata` below has been amended to say so, and its correctness assertions are
unchanged - they now hold for a better reason.

The guard is still load-bearing, on a narrower case: the COLLISION-MERGE conflict
row. Editing a key source column re-derives a row's identity mid-batch, and if the
new key already belongs to another row, `apply_row_update_internal` finds that row
with its own query (crud.py, `conflict_row`) and merges onto it. That row's key was
never in the payload, so it is genuinely outside the prefetched set.
`test_composite_key_prefetch_budget.py::test_collision_merge_still_reads_the_
conflict_rows_metadata` is that case, and it is the one that must not be deleted.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import crud, models, schemas
from database.database import Base
from sql_budget import record_statements, selects_from


ROWS = 20


def _batch(items):
    return schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(**i)
                                               for i in items])


def test_writing_a_never_written_column_costs_the_prefetch_and_nothing_more(db_session):
    """Two statements, not two per row.

    The floor for this batch is exactly the prefetch: one `cell_sources` SELECT and
    one `cell_overwrites` SELECT, both covering every row at once.
    """
    table = "rmscope_test_map"
    keys = [f"P2_{i}" for i in range(ROWS)]

    # Existing rows, with metadata for die_key/ref_table/map_key/val - but NOT for
    # x or y, which is the shape being measured: a column arriving for the first time.
    crud.apply_batch_updates(db_session, table, _batch([
        {"updates": {"die_key": k, "ref_table": "bonding_map", "map_key": "P2",
                     "val": "1"}} for k in keys
    ]))

    with record_statements(db_session) as recorded:
        results, _changed, _logs, _deleted = crud.apply_batch_updates(
            db_session, table,
            _batch([{"business_key_val": k, "updates": {"x": 1, "y": 2}}
                    for k in keys]))

    assert len(results) == ROWS
    assert all(not is_new for _row, is_new in results), \
        "the second batch must UPDATE the seeded rows, not create new ones"

    # 20 rows x 2 new columns used to be 40 CellSource SELECTs + 40 CellOverwrite
    # SELECTs on top of the two prefetch queries.
    assert len(selects_from(recorded, "cell_sources")) == 1
    assert len(selects_from(recorded, "cell_overwrites")) == 1


# ---------------------------------------------------------------------------
# The correctness argument, as an executable case.
# ---------------------------------------------------------------------------

@pytest.fixture
def composite_db():
    """A table whose business key is ASSEMBLED FROM COLUMN VALUES.

    That is what makes a row reachable without ever having been prefetched: the
    key does not exist when `target_ids`/`target_bks` are collected, only after
    `apply_row_update_internal` joins the source columns.

    Table name prefixed `p2meta_test_` so it cannot collide with a real table in
    the user's gitignored config.
    """
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    config = {
        "p2meta_test_map": {
            "business_key": "pkg_id",
            "composite_key_source": ["base", "x", "y"],
            "composite_key_separator": "_",
            "column_types": {
                "pkg_id": "string", "base": "string",
                "x": "string", "y": "string", "leg": "string",
            },
        }
    }
    models.init_dynamic_models(config)
    crud.TABLE_CONFIG.update(config)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)

    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.pop("p2meta_test_map", None)


def test_row_resolved_after_the_prefetch_still_reads_its_metadata(composite_db):
    """A human correction must survive a parser write to an unkeyed payload row.

    If absence were memoised on "the row exists" rather than on "the row was
    prefetched", the parser value below would find an empty source list, become
    the only source, win the priority computation, and take the `is_overwrite`
    marker down with it. Nothing would raise; the correction would just be gone.

    ⚠️ AMENDED BY P6. The name is now half wrong and is kept only so the history is
    followable: the second item below is no longer resolved AFTER the prefetch.
    `apply_batch_updates` assembles its composite key before building the prefetch
    filter, so the row IS covered, its metadata IS loaded in the bulk query, and the
    cache hit is a real hit rather than a memoised absence.

    The claim the test makes is therefore unchanged and the assertions below are
    untouched - a human correction survives a parser write to an unkeyed payload -
    but the BUDGET assertion that used to close it ("a row outside the prefetched
    set must still be queried", `cell_sources >= 2`) has moved out, because this row
    is no longer outside that set. It now lives on the case that still is:
    `test_composite_key_prefetch_budget.py::test_collision_merge_still_reads_the_
    conflict_rows_metadata`.
    """
    table = "p2meta_test_map"

    # A human value on a row we will reach ONLY through the composite key.
    crud.apply_batch_updates(composite_db, table, _batch([
        {"updates": {"base": "A", "x": "1", "y": "2", "leg": "HUMAN"},
         "source_name": "user", "updated_by": "operator"}
    ]))
    # A second, unrelated row that WILL be prefetched, so the batch below has a
    # non-empty prefetched set and the guard is actually live.
    crud.apply_batch_updates(composite_db, table, _batch([
        {"updates": {"base": "B", "x": "9", "y": "9", "leg": "OTHER"},
         "source_name": "user", "updated_by": "operator"}
    ]))

    with record_statements(composite_db) as recorded:
        crud.apply_batch_updates(composite_db, table, _batch([
            # keyed -> lands in target_bks -> prefetched
            {"business_key_val": "B_9_9", "updates": {"leg": "OTHER2"},
             "source_name": "pipeline_parser", "updated_by": "parser"},
            # unkeyed -> key assembled mid-batch -> resolved but NOT prefetched
            {"updates": {"base": "A", "x": "1", "y": "2", "leg": "PARSER"},
             "source_name": "pipeline_parser", "updated_by": "parser"},
        ]))

    model = models.DYNAMIC_TABLES[table]
    row_a = composite_db.query(model).filter(model.business_key_val == "A_1_2").one()
    assert row_a.leg == "HUMAN", (
        "the user layer outranks pipeline_parser; reading it back is the only way "
        "this row's stored sources can take part in the priority computation")

    ow = composite_db.query(models.CellOverwrite).filter(
        models.CellOverwrite.table_name == table,
        models.CellOverwrite.row_id == row_a.row_id,
        models.CellOverwrite.column_name == "leg").one_or_none()
    assert ow is not None and ow.is_overwrite is True, \
        "the overwrite marker is deleted when the user source is not seen"

    # [P6] And the read that made it possible really happened - now in the BULK
    # query rather than in per-row follow-ups, because the unkeyed item's composite
    # key is assembled before the prefetch filter is built. One `cell_sources`
    # SELECT covering both rows, where there used to be that one plus two more for
    # the row it had missed.
    assert len(selects_from(recorded, "cell_sources")) == 1, \
        "the prefetch now covers the unkeyed row, so it costs no follow-up reads"

    # The membership set really did include it - that, and not "the row exists", is
    # what made answering from cache correct.
    assert composite_db.query(models.CellSource).filter(
        models.CellSource.table_name == table,
        models.CellSource.row_id == row_a.row_id,
        models.CellSource.column_name == "leg",
        models.CellSource.source_name == "user").count() == 1, \
        "the user layer this test is about is really stored on the prefetched row"
