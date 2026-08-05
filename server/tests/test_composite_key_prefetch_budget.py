"""[P6] Assemble the composite business key BEFORE the batch prefetch is built from it.

Eleven of the fourteen real tables declare a `composite_key_source`: their business
key is a join of their own column values (`base_x_y`), not something the payload
carries. A parser, the chain worker and the map editor all send `updates` dicts with
those source columns and NO `row_id`/`business_key_val`.

The assembly used to run inside `apply_row_update_internal` - per row, and after
`apply_batch_updates` had already collected `target_bks`. So `target_bks` was empty,
the prefetch matched nothing, `row_cache` stayed empty, and `_get_or_create_row`
fell through to one full-model SELECT per row.

The intent was already proven in exactly one caller: `enrichment_mapper` pre-assembles
the key itself with the comment that the bulk prefetch is keyed on
`business_key_val`. Every other caller paid.

WHAT MOVED IS *WHEN*, NOT *WHAT*. Same function, same guard, same two side effects
(it sets `business_key_val` AND writes the key into `updates[key_col]`). The tests
below pin the value, both side effects, and every arm of the guard - not just the
budget - because a faster wrong key is the worst possible outcome here.

TWO THINGS THIS DELIBERATELY DOES NOT FIX, pinned so the numbers are executable:
  * `test_inserting_new_rows_still_probes_once_per_row` - a batch whose rows do not
    exist yet still asks for each one. The prefetch now proves their absence, but
    `_get_or_create_row` does not read that proof. That includes a `replace_map`
    push, which purges first and therefore inserts.
  * The collision-merge conflict row is still resolved mid-batch and still outside
    the prefetched set, which is what keeps `prefetched_row_ids` load-bearing.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import crud, models, schemas
from database.database import Base
from sql_budget import record_statements, selects_from


ROWS = 200

DECLARED = "p6key_test_map"    # declares map_key_columns -> declared replace_map scope
LEGACY = "p6legacy_test_meta"  # no map_key_columns -> legacy derived replace_map scope

CONFIG = {
    DECLARED: {
        "business_key": "pkg_id",
        "composite_key_source": ["base", "x", "y"],
        "composite_key_separator": "_",
        "map_key_columns": ["base"],
        "column_types": {"pkg_id": "string", "base": "string", "x": "string",
                         "y": "string", "leg": "string"},
    },
    LEGACY: {
        "business_key": "meta_pk",
        "composite_key_source": ["target_table", "map_id"],
        "composite_key_separator": "_",
        "column_types": {"meta_pk": "string", "target_table": "string",
                         "map_id": "string", "note": "string"},
    },
}


@pytest.fixture
def key_db():
    """Own engine, own session. Table names prefixed `p6*_test_` so they cannot
    collide with a real table in the user's gitignored config."""
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        for name in CONFIG:
            crud.TABLE_CONFIG.pop(name, None)


def _batch(items, **kw):
    return schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(**i) for i in items], **kw)


def _cells(leg, n=ROWS, base="A"):
    """`n` payload items carrying the composite SOURCE columns and nothing else -
    no row_id, no business_key_val. This is the shape every parser and the map
    editor send."""
    return [{"updates": {"base": base, "x": str(i), "y": "0", "leg": leg},
             "source_name": "user", "updated_by": "tester"} for i in range(n)]


def _model(table):
    return models.DYNAMIC_TABLES[table]


# ---------------------------------------------------------------------------
# The budget
# ---------------------------------------------------------------------------

def test_an_update_batch_resolves_every_row_in_one_select(key_db):
    crud.apply_batch_updates(key_db, DECLARED, _batch(_cells("L0")))

    with record_statements(key_db) as recorded:
        results, _c, _l, _d = crud.apply_batch_updates(
            key_db, DECLARED, _batch(_cells("L1")))

    assert len(results) == ROWS
    assert all(not is_new for _row, is_new in results), \
        "precondition: this batch must UPDATE the seeded rows, not create new ones"

    assert len(selects_from(recorded, DECLARED)) == 1, (
        "one prefetch resolves the whole batch; it used to be that prefetch matching "
        "nothing plus one get_row_by_business_key per row")


def test_the_metadata_prefetch_now_covers_those_rows_too(key_db):
    """The larger half of the saving, and it is a consequence rather than a second
    change: `prefetched_row_ids` is built from the rows the prefetch resolved, so
    while these rows were invisible to it, EVERY cell of every row also paid two
    metadata SELECTs to be told it had none. Five columns x 200 rows x 2."""
    crud.apply_batch_updates(key_db, DECLARED, _batch(_cells("L0")))

    with record_statements(key_db) as recorded:
        crud.apply_batch_updates(key_db, DECLARED, _batch(_cells("L1")))

    assert len(selects_from(recorded, "cell_sources")) == 1
    assert len(selects_from(recorded, "cell_overwrites")) == 1
    assert len(recorded) < 500, (
        f"a 200-row update of a composite-keyed table cost 2,604 statements and "
        f"now costs {len(recorded)}")


def test_inserting_new_rows_still_probes_once_per_row(key_db):
    """Pinned because it is what P6 does NOT fix, and the number belongs in the open.

    The prefetch below proves these rows are absent - it selects on exactly their
    keys with no other filter - but `_get_or_create_row` does not read that proof,
    so it asks for each one individually before creating it. A `replace_map` map
    push purges first and therefore takes this path for every die.

    Closing this needs a business-key equivalent of `prefetched_row_ids`, which is a
    separate correctness argument and is not made here.
    """
    with record_statements(key_db) as recorded:
        crud.apply_batch_updates(key_db, DECLARED, _batch(_cells("L0")))

    assert len(selects_from(recorded, DECLARED)) == ROWS + 1, (
        "one prefetch that matches nothing, plus one futile probe per row")


# ---------------------------------------------------------------------------
# WHAT the key is - unchanged
# ---------------------------------------------------------------------------

def test_the_assembled_key_is_the_same_key_it_always_was(key_db):
    crud.apply_batch_updates(key_db, DECLARED, _batch(_cells("L0", n=3)))

    model = _model(DECLARED)
    rows = {r.business_key_val: r for r in key_db.query(model).all()}
    assert sorted(rows) == ["A_0_0", "A_1_0", "A_2_0"], \
        "same source columns, same separator, same order"


def test_the_key_is_also_written_into_the_row_as_a_value(key_db):
    """The second side effect. Dropping it would leave `pkg_id` NULL on every
    ingested row while `business_key_val` looked fine."""
    crud.apply_batch_updates(key_db, DECLARED, _batch(_cells("L0", n=1)))

    row = key_db.query(_model(DECLARED)).one()
    assert row.pkg_id == "A_0_0" == row.business_key_val


@pytest.mark.parametrize("item, why", [
    ({"row_id": "R1", "updates": {"base": "A", "x": "1", "y": "2"}},
     "an explicit row_id already names the row"),
    ({"business_key_val": "EXPLICIT", "updates": {"base": "A", "x": "1", "y": "2"}},
     "an explicit business key already names the row"),
    ({"updates": {"base": "A", "x": "1"}},
     "a source column is missing entirely"),
    ({"updates": {"base": "A", "x": "1", "y": ""}},
     "a source column is blank"),
    ({"updates": {"base": "A", "x": "1", "y": "   "}},
     "a source column is blank after cleaning"),
])
def test_the_guard_refuses_to_assemble(key_db, item, why):
    """Every arm of the guard, on the function itself.

    The last three matter most: a PARTIAL key must not be joined. `A_1_` would be a
    second spelling of a row's identity, and two spellings is how one row silently
    becomes two. Hoisting the assembly earlier makes that failure reach the prefetch
    filter as well as the write, so the guard is pinned rather than assumed.
    """
    update_item = schemas.GeneralUpdateItem(**item)
    before = dict(update_item.updates)

    assembled = crud.assemble_composite_business_key(DECLARED, update_item)

    assert assembled is False, why
    assert update_item.updates == before, "and it touched nothing on the way out"
    assert update_item.business_key_val == item.get("business_key_val")


def test_the_guard_assembles_when_and_only_when_it_should(key_db):
    """The positive arm, and both side effects, on the function itself."""
    update_item = schemas.GeneralUpdateItem(
        updates={"base": "A", "x": "1", "y": "2", "leg": "L"})

    assert crud.assemble_composite_business_key(DECLARED, update_item) is True
    assert update_item.business_key_val == "A_1_2"
    assert update_item.updates["pkg_id"] == "A_1_2", \
        "the key is also written back as a column value"

    # Idempotent: a second call is a no-op, which is what lets the batch path call it
    # up front while `apply_row_update_internal` keeps calling it for itself.
    assert crud.assemble_composite_business_key(DECLARED, update_item) is False


def test_an_incomplete_composite_source_still_writes_the_row_unkeyed(key_db):
    """End to end: refusing to assemble is not refusing to write."""
    crud.apply_batch_updates(key_db, DECLARED, _batch([
        {"updates": {"base": "A", "x": "1", "leg": "L"}, "source_name": "user"}]))

    row = key_db.query(_model(DECLARED)).one()
    assert row.leg == "L"
    assert row.business_key_val is None
    assert row.pkg_id is None


# ---------------------------------------------------------------------------
# The ordering constraint this change had to respect
# ---------------------------------------------------------------------------

def test_replace_map_still_purges_the_whole_map_and_not_one_row(key_db):
    """🔴 THE DANGEROUS ONE.

    The assembly writes the key into `updates[key_col]`, and
    `derive_replace_map_scope`'s LEGACY branch (a table with no declared
    `map_key_columns` - four real tables, `wafer_map_metadata` among them) builds
    the purge filters from every non-coordinate column present in the first payload
    row. The business key column is not on its skip list.

    So assembling the key one step too early turns "delete every row of this map"
    into "delete the single row whose key equals the first payload row's key", and
    the purge silently stops purging. Nothing raises; rows just accumulate.
    """
    seed = [{"updates": {"target_table": "T", "map_id": str(i), "note": "old"},
             "source_name": "user"} for i in range(5)]
    crud.apply_batch_updates(key_db, LEGACY, _batch(seed))
    assert key_db.query(_model(LEGACY)).count() == 5

    report = {}
    crud.apply_batch_updates(
        key_db, LEGACY,
        _batch([{"updates": {"target_table": "T", "map_id": "0"},
                 "source_name": "user"}], replace_map=True),
        report)

    # The claim is narrow and exact: the ASSEMBLED key column must not appear among
    # the purge filters. What else the legacy branch picks up is its own (unchanged)
    # business; what must never happen is this change adding a filter of its own.
    assert "meta_pk" not in report["filters"], (
        f"the purge scope was derived from a key this code assembled, not from the "
        f"payload the caller sent: {report['filters']}")
    assert report["filters"] == {"target_table": "T", "map_id": "0"}
    assert report["deleted"] == 1
    assert key_db.query(_model(LEGACY)).count() == 5


def test_replace_map_on_a_declared_scope_is_unchanged(key_db):
    """The other branch: `map_key_columns` is declared, so the scope never looked at
    the payload's other columns and the assembly could not have reached it. Pinned
    so the pair is symmetric."""
    crud.apply_batch_updates(key_db, DECLARED, _batch(_cells("L0", n=10, base="A")))
    crud.apply_batch_updates(key_db, DECLARED, _batch(_cells("L0", n=4, base="B")))

    report = {}
    crud.apply_batch_updates(key_db, DECLARED,
                             _batch(_cells("L2", n=3, base="A"), replace_map=True),
                             report)

    assert report["filters"] == {"base": "A"}
    assert report["deleted"] == 10
    model = _model(DECLARED)
    assert key_db.query(model).filter(model.base == "A").count() == 3
    assert key_db.query(model).filter(model.base == "B").count() == 4, \
        "the other map is untouched"


# ---------------------------------------------------------------------------
# Collision merge - the named regression risk, and what keeps P2's guard alive
# ---------------------------------------------------------------------------

def test_collision_merge_still_reads_the_conflict_rows_metadata(key_db):
    """Editing a key SOURCE column re-derives the row's identity mid-batch. If the
    new key already belongs to another row, `apply_row_update_internal` finds that
    row with its own query and merges onto it.

    That conflict row is resolved AFTER the prefetch filter was built - its key was
    never in the payload - so it is outside `prefetched_row_ids` and its stored
    metadata must still be read. This is the case that keeps P2's guard load-bearing
    now that the ordinary composite payload is prefetched, and it is the collision
    path P6 could have broken.

    If the conflict row's sources were assumed empty, `crud` would find no stored
    `user` value to back up and the human's value would be gone with no record that
    it ever existed. Nothing would raise.
    """
    # The human's row, reachable only by its assembled key. This is the CONFLICT row.
    crud.apply_batch_updates(key_db, DECLARED, _batch([
        {"updates": {"base": "A", "x": "1", "y": "2", "leg": "HUMAN"},
         "source_name": "user", "updated_by": "operator"}]))
    # A second row that the batch below re-keys ONTO the first one.
    crud.apply_batch_updates(key_db, DECLARED, _batch([
        {"updates": {"base": "A", "x": "9", "y": "9", "leg": "MOVER"},
         "source_name": "user", "updated_by": "operator"}]))

    model = _model(DECLARED)
    keeper = key_db.query(model).filter(model.business_key_val == "A_1_2").one()
    keeper_id = keeper.row_id

    with record_statements(key_db) as recorded:
        crud.apply_batch_updates(key_db, DECLARED, _batch([
            # Keyed on the MOVER, so the prefetch covers A_9_9 and NOT A_1_2. Moving
            # its coordinates re-derives its key to the keeper's, and the merge fires.
            {"business_key_val": "A_9_9",
             "updates": {"x": "1", "y": "2", "leg": "MOVED"},
             "source_name": "user", "updated_by": "operator2"}]))

    key_db.expire_all()
    survivors = key_db.query(model).all()
    assert len(survivors) == 1, "the collision merged the two rows into one"
    assert survivors[0].row_id == keeper_id, "merged ONTO the pre-existing row"

    # The evidence that the conflict row's stored sources were READ, not assumed
    # empty: crud backs the displaced `user` value up under its own source name, and
    # it can only do that if it saw it.
    backups = key_db.query(models.CellSource).filter(
        models.CellSource.table_name == DECLARED,
        models.CellSource.row_id == keeper_id,
        models.CellSource.column_name == "leg",
        models.CellSource.source_name.like("user (old_exist_%")).all()
    assert len(backups) == 1, (
        "the conflict row's pre-existing user value must be preserved as a backup "
        "source; an empty source list produces no backup and the value is lost")
    assert backups[0].value == "HUMAN"

    ow = key_db.query(models.CellOverwrite).filter(
        models.CellOverwrite.table_name == DECLARED,
        models.CellOverwrite.row_id == keeper_id,
        models.CellOverwrite.column_name == "leg").one_or_none()
    assert ow is not None and ow.is_overwrite is True

    # And the read that made it possible really happened.
    assert len(selects_from(recorded, "cell_sources")) >= 2, (
        "a row resolved after the prefetch must still be queried - the prefetch "
        "covered A_9_9, not A_1_2")
