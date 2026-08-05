"""[P3] The `bulk_*` cell-metadata helpers must chunk, like every other bulk
operation in this codebase (`graph_materializer.CHUNK_SIZE`).

`bulk_upsert_cell_sources`, `bulk_upsert_cell_overwrites` and
`bulk_delete_cell_overwrites` each built ONE statement over the whole batch. A
5,000-die map save produced a single ~690 KB INSERT binding 210,000 parameters,
and the delete was an N-term OR chain.

🔴 WHY THIS SUITE COULD NEVER HAVE CAUGHT IT. The failure is a per-statement
PARAMETER limit, and SQLite's is 250,000 on the build this suite runs while
PostgreSQL's is 32,767 - the count travels in an int16 on the wire. So the
statement production refuses outright executes happily here, and asserting only
"the push succeeds" would assert nothing about production. The tests below
assert the bind count per statement, which is the property that transfers.
"""

import math
from datetime import datetime

import pytest

from database import crud, models, schemas
from sql_budget import (PG_MAX_BIND_PARAMS, deletes_from, inserts_into,
                        record_statements)


TABLE = "rmscope_test_map"
#: A real map save, not a token one. `rmscope_test_map` declares 6 columns, so
#: this is 30,000 cell-metadata rows - the size at which the old single statement
#: bound 210,000 parameters.
DIE_COUNT = 5000
COLUMNS_PER_DIE = 6
CELLS = DIE_COUNT * COLUMNS_PER_DIE
#: The charter's chunk size, spelled as a literal so this file states the expected
#: behaviour independently of the constant it is checking.
CHUNK = 1000


def _push(count):
    return schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(
            updates={"die_key": f"P3_{i}", "ref_table": "bonding_map",
                     "map_key": "P3", "x": i, "y": 0, "val": "1"},
            source_name="user", updated_by="operator")
        for i in range(count)
    ])


def test_real_size_map_push_binds_no_more_than_one_chunk_per_statement(db_session):
    """A 5,000-die push, which this suite has never run before."""
    with record_statements(db_session) as recorded:
        results, _changed, _logs, _deleted = crud.apply_batch_updates(
            db_session, TABLE, _push(DIE_COUNT))

    assert len(results) == DIE_COUNT
    model = models.DYNAMIC_TABLES[TABLE]
    assert db_session.query(model).count() == DIE_COUNT
    # Every cell's metadata landed. Chunking a write is only free if no chunk
    # boundary swallows a row, and a lost CellSource is invisible until the next
    # priority computation reads the layer that is no longer there.
    assert db_session.query(models.CellSource).filter(
        models.CellSource.table_name == TABLE).count() == CELLS
    assert db_session.query(models.CellOverwrite).filter(
        models.CellOverwrite.table_name == TABLE).count() == CELLS

    # The property that transfers to PostgreSQL, asserted ahead of the chunk count
    # because it is the one that names the production failure. Checked over EVERY
    # statement the save issued, not just the two helpers, so a future single-shot
    # statement anywhere on this path trips it too.
    worst = max(recorded, key=lambda c: c.bind_count)
    assert worst.bind_count < PG_MAX_BIND_PARAMS, (
        f"one statement bound {worst.bind_count} parameters; PostgreSQL refuses "
        f"above {PG_MAX_BIND_PARAMS}. Statement head: {worst.sql[:120]}")

    expected_chunks = math.ceil(CELLS / CHUNK)
    assert len(inserts_into(recorded, "cell_sources")) == expected_chunks
    assert len(inserts_into(recorded, "cell_overwrites")) == expected_chunks


def test_bulk_delete_cell_overwrites_chunks_its_or_chain(db_session):
    """The delete is the same defect in a worse shape: one OR term per key.

    Chunking a DELETE changes what is sent, so this also pins that it still
    removes exactly the keys it was given and nothing else - a chunk boundary is
    the natural place for an off-by-one to eat a row.
    """
    n = CHUNK * 2 + 500
    now = datetime.now()
    rows = [{"table_name": TABLE, "row_id": f"D_{i}", "column_name": "val",
             "is_overwrite": True, "updated_by": "operator",
             "updated_at": now, "manual_priority_source": None}
            for i in range(n + 3)]
    crud.bulk_upsert_cell_overwrites(db_session, rows)
    db_session.flush()

    keys = [(TABLE, f"D_{i}", "val") for i in range(n)]
    with record_statements(db_session) as recorded:
        crud.bulk_delete_cell_overwrites(db_session, keys)

    assert len(deletes_from(recorded, "cell_overwrites")) == math.ceil(n / CHUNK)
    worst = max(recorded, key=lambda c: c.bind_count)
    assert worst.bind_count < PG_MAX_BIND_PARAMS

    surviving = {r.row_id for r in db_session.query(models.CellOverwrite).filter(
        models.CellOverwrite.table_name == TABLE).all()}
    assert surviving == {f"D_{i}" for i in range(n, n + 3)}, \
        "chunking must delete exactly the given keys - no more, no fewer"


@pytest.mark.parametrize("n", [0, 1, CHUNK - 1, CHUNK, CHUNK + 1])
def test_chunk_boundaries_upsert_every_mapping(db_session, n):
    """Off-by-one guard on the chunk loop itself, at and around the boundary."""
    now = datetime.now()
    mappings = [{"table_name": TABLE, "row_id": f"B_{i}", "column_name": "val",
                 "source_name": "user", "value": str(i), "updated_by": "operator",
                 "ingested_at": now}
                for i in range(n)]
    crud.bulk_upsert_cell_sources(db_session, mappings)
    db_session.flush()

    stored = db_session.query(models.CellSource).filter(
        models.CellSource.table_name == TABLE).count()
    assert stored == n
