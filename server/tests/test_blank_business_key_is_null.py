"""A blank business key column stores NULL, never the empty string.

WHAT THIS GUARDS, AND WHY IT SURVIVED A NARROWING
-------------------------------------------------
`business_key_val` is how every write path recognises a row it has seen before. A
payload whose key column arrived blank used to be stored with `business_key_val = ''`,
and `''` is a VALUE - so every keyless row in a table carried the SAME identity.

That is not a duplicate-row problem. It is a **collision** problem, and the UNIQUE index
from `migrations/add_business_key_unique_index.py` turns it into an outage:

  * Five such rows in ONE batch collide with EACH OTHER.
  * `apply_batch_updates`' `IntegrityError` recovery cannot resolve it. Its recovery is
    "roll back, re-read the database in a new snapshot, resolve onto the row the winner
    committed" - and none of the colliding rows was ever committed, so the replay
    reproduces the identical collision.
  * After `BK_CONFLICT_MAX_RETRIES` the batch is REFUSED.

Measured on this workstation against real PostgreSQL with the index installed (a
simulation, not production), three pushes of a 5-row payload whose key column arrived
blank: **0 rows written each time**. Without the index the same payload wrote 5, 10 and
15 rows, all sharing the key `''`. One source file with a blank key column would stop
that table's ingestion outright.

NULL is the correct target. PostgreSQL treats NULLs as distinct under a plain UNIQUE
index (which is why the migration deliberately does NOT use `NULLS NOT DISTINCT`), so
any number of keyless rows may coexist. It is also the shape a keyless row already has
everywhere else: `create_empty_rows_batch` writes it, the grid addresses such rows by
`row_id`, and the live database carries them today - measured 2026-08-07: 11 rows in
`wafer_map_metadata` and 10 in `production_plan`, all produced by manual merges.

🔴 THERE IS NO PLACEHOLDER AND THERE MUST NOT BE ONE. An earlier draft of this lane
minted `UNKEYED::<row_id>` for such rows. The product owner ruled it out: keyless rows
arise only from manual grid work, never from ingestion, so the placeholder's value -
making a row recognisable to a LATER ingestion - is value nobody collects. A keyless row
keeps NULL, which is what the grid already handles. If a future reader is tempted to add
a synthetic identity here, the question to answer first is who reads it.

WHY THE TESTS LOOK LIKE THIS
Each test names the mutation it kills, and the ones that pass against the pre-change code
say so themselves rather than being counted as evidence.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from database.database import Base
from database import crud, models, schemas


#: Table names carry a prefix that cannot exist in the user's own (gitignored)
#: `table_config.json`. A collision there makes `init_dynamic_models` win the race for
#: the shared in-memory sqlite schema and the suite fails with `no such column` - see
#: the `bonding_log` incident in the server-pm lessons file.
PLAIN = "blankkey_test_plain"
COMPOSITE = "blankkey_test_composite"

TEST_TABLE_CONFIG = {
    PLAIN: {
        "business_key": "unit_id",
        "column_types": {"unit_id": "string", "payload": "string", "note": "string"},
        "display_columns": ["unit_id", "payload", "note"],
    },
    COMPOSITE: {
        "business_key": "map_pk",
        "composite_key_source": ["map_id", "die_no"],
        "composite_key_separator": "_",
        "column_types": {"map_pk": "string", "map_id": "string",
                         "die_no": "string", "payload": "string"},
        "display_columns": ["map_pk", "map_id", "die_no", "payload"],
    },
}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    models.init_dynamic_models(TEST_TABLE_CONFIG)
    crud.TABLE_CONFIG.update(TEST_TABLE_CONFIG)

    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)

    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _push(db, table, items, **kw):
    batch = schemas.GeneralUpdateBatch(updates=items, **kw)
    return crud.apply_batch_updates(db, table, batch)


def _plain_item(unit_id="", payload="P"):
    """A watcher-shaped payload item. `directory_watcher.py:1876` puts the payload's
    own key cell straight onto `business_key_val`, so a blank cell arrives as `''`."""
    return schemas.GeneralUpdateItem(
        business_key_val=unit_id,
        updates={"unit_id": unit_id, "payload": payload},
        source_name="pipeline_parser", updated_by="watcher")


def _rows(db, table):
    return db.query(models.DYNAMIC_TABLES[table]).all()


def _row(db, table, row_id):
    model = models.DYNAMIC_TABLES[table]
    return db.query(model).filter(model.row_id == row_id).first()


# ---------------------------------------------------------------------------
# 1. The empty string is gone
# ---------------------------------------------------------------------------

def test_a_blank_key_column_stores_null_not_the_empty_string(db):
    """KILLS: restoring `row.business_key_val = str_val` for a blank value in
    `_update_row_business_key`.

    Asserted with `is None` rather than a falsiness check on purpose - `''` and `None`
    are both falsy in Python, so `assert not row.business_key_val` would pass against
    exactly the code this test exists to forbid."""
    _push(db, PLAIN, [_plain_item(payload="P1"), _plain_item(payload="P2")])

    rows = _rows(db, PLAIN)
    assert len(rows) == 2, "the push wrote nothing - the fixture exercises nothing"
    for r in rows:
        assert r.business_key_val is None
        assert r.business_key_val != ""


def test_no_two_keyless_rows_share_an_identity(db):
    """KILLS: any spelling of 'no key' that is a VALUE rather than NULL.

    This is the axis that decides whether the UNIQUE index is survivable. `''` gives
    five keyless rows ONE identity, and under `uq_bk_<table>` they collide with each
    other inside a single transaction - which the `IntegrityError` replay cannot undo,
    because it re-reads a database in which none of them was ever committed. Measured
    outcome on real PostgreSQL: the whole batch refused, 0 rows written."""
    _push(db, PLAIN, [_plain_item(payload=f"P{i}") for i in range(5)])

    rows = _rows(db, PLAIN)
    assert len(rows) == 5
    stored = [r.business_key_val for r in rows]
    assert stored.count("") == 0, f"an empty-string identity is back: {stored}"
    assert all(v is None for v in stored)


def test_the_key_column_itself_is_untouched(db):
    """KILLS: writing anything synthetic into the business key COLUMN.

    The key column is the operator's data and it is blank because the source had
    nothing to put there. It must keep reading blank so that typing a value is an edit
    rather than a correction, and because `derive_replace_map_scope`'s legacy branch
    builds a `replace_map` purge filter out of the payload's declared columns."""
    _push(db, PLAIN, [_plain_item(payload="P1")])

    row = _rows(db, PLAIN)[0]
    assert row.business_key_val is None
    assert not row.unit_id


def test_a_blank_value_does_not_destroy_an_existing_key(db):
    """KILLS: the obvious-looking fix `blank -> set NULL`, which I wrote first and
    which is wrong.

    The pre-change code wrote `''` here, which dropped the old key. Clearing to NULL
    drops it just the same, and for a DERIVED key column that is destruction rather
    than an edit - see `test_a_map_payload_survives_an_unchanged_re_push`, which is the
    case that actually caught it. The old code got away with it only because `''`
    collided on the way out and the batch was refused before the damage committed.

    A stale-but-unique handle is recoverable by typing a new key. A destroyed one
    orphans everything keyed to it."""
    _push(db, PLAIN, [_plain_item(unit_id="REAL-1", payload="P")])
    row_id = _rows(db, PLAIN)[0].row_id
    assert _row(db, PLAIN, row_id).business_key_val == "REAL-1"

    _push(db, PLAIN, [schemas.GeneralUpdateItem(
        row_id=row_id, updates={"unit_id": ""},
        source_name="user", updated_by="operator")])

    after = _row(db, PLAIN, row_id)
    assert after.business_key_val == "REAL-1"
    assert after.business_key_val != ""
    assert after.payload == "P"


# ---------------------------------------------------------------------------
# 2. Composite tables
# ---------------------------------------------------------------------------

def test_an_incomplete_composite_source_leaves_the_key_null(db):
    """The composite path already wrote NULL rather than `''`, so this passes against
    the pre-change code too - said plainly so it is not counted as evidence for this
    change. It is here because the two paths must agree on what 'no key' looks like,
    and a future edit that unifies them could unify them onto the wrong value."""
    _push(db, COMPOSITE, [
        schemas.GeneralUpdateItem(
            updates={"map_id": "M1", "die_no": "", "payload": f"P{i}"},
            source_name="pipeline_parser", updated_by="watcher")
        for i in range(3)])

    rows = _rows(db, COMPOSITE)
    assert len(rows) == 3
    assert all(r.business_key_val is None for r in rows)
    assert all(r.map_pk is None for r in rows)


def test_a_complete_composite_key_is_unaffected(db):
    """CONTROL. Passes both ways by design. If it ever fails, the blank-key branch is
    eating real identities - the worst outcome available on this lane."""
    for _ in range(3):
        _push(db, COMPOSITE, [
            schemas.GeneralUpdateItem(
                updates={"map_id": "M9", "die_no": str(i), "payload": f"P{i}"},
                source_name="pipeline_parser", updated_by="watcher")
            for i in range(4)])

    rows = _rows(db, COMPOSITE)
    assert len(rows) == 4, "a keyed re-push duplicated rows"
    assert sorted(r.business_key_val for r in rows) == ["M9_0", "M9_1", "M9_2", "M9_3"]


def test_a_map_payload_survives_an_unchanged_re_push(db):
    """🔴 THE DANGEROUS ONE, and the reason the blank branch writes NOTHING rather
    than clearing to NULL.

    A map CSV carries its key column PRESENT AND BLANK (see
    `test_set_based_write_path._item`), and that column is DERIVED - `map_pk` is
    assembled from `map_id`+`die_no`. Blank means "the file did not supply it", not
    "this row has no key".

    The trap is on the SECOND push. The rows resolve by their assembled key, so the
    composite recomputation at the end of `apply_row_update_internal` is skipped
    (`is_src_changed` is False, the row is not new) and nothing puts the key back. Any
    version of this branch that touches `business_key_val` on a blank value therefore
    strips every row of an unchanged map. Measured on real PostgreSQL: push 2 left all
    four rows NULL and push 3 created four MORE rows.

    ⚠️ ONE PUSH IS NOT ENOUGH TO CATCH THIS - a single-push version of this test passes
    against the clearing bug, because push 1 assembles the key after the blank is
    processed. The loop is the test.

    ⚠️ THE ASSERTION IS ON `business_key_val`, NOT ON THE COLUMN `map_pk`, and that is
    not laziness. The blank `map_pk` cell in the payload is written through the ordinary
    cell loop, which nulls the column on re-push. That is pre-existing behaviour of the
    cell loop and independent of this branch - it was simply invisible before, because
    the old `''` code made push 2 collide and the batch never committed. Confirmed on
    real PostgreSQL: after three pushes, `business_key_val` is intact on all rows while
    `map_pk` reads NULL. Reported separately; asserting it here would pin a behaviour
    this lane does not own."""
    for _ in range(3):
        _push(db, COMPOSITE, [
            schemas.GeneralUpdateItem(
                updates={"map_pk": "", "map_id": "M3", "die_no": str(i),
                         "payload": "P"},
                source_name="pipeline_parser", updated_by="watcher")
            for i in range(3)])

        rows = _rows(db, COMPOSITE)
        assert sorted(r.business_key_val for r in rows) == ["M3_0", "M3_1", "M3_2"]
    assert len(_rows(db, COMPOSITE)) == 3, "an unchanged re-push duplicated map rows"


# ---------------------------------------------------------------------------
# 3. A keyless row is still reachable, by row_id - which is why no placeholder
# ---------------------------------------------------------------------------

def test_a_keyless_row_is_still_editable_and_can_acquire_a_real_key(db):
    """The load-bearing reason the product owner ruled the placeholder out: a keyless
    row is manual work, manual work addresses rows by `row_id`, and that link needs no
    identity in `business_key_val` at all. Typing a key into the grid promotes the row
    with no extra machinery."""
    _push(db, PLAIN, [_plain_item(payload="KEEP-ME")])
    row_id = _rows(db, PLAIN)[0].row_id
    assert _row(db, PLAIN, row_id).business_key_val is None

    _push(db, PLAIN, [schemas.GeneralUpdateItem(
        row_id=row_id, updates={"unit_id": "REAL-7"},
        source_name="user", updated_by="operator")])

    after = _row(db, PLAIN, row_id)
    assert after.business_key_val == "REAL-7"
    assert after.unit_id == "REAL-7"
    assert after.payload == "KEEP-ME"
    assert len(_rows(db, PLAIN)) == 1, "promoting the row created a second one"


def test_existing_null_keyed_rows_are_not_disturbed(db):
    """STANDING GUARD - passes against the pre-change code too, said so it is not
    counted as evidence for this lane.

    The live database already holds NULL-keyed rows from manual merges (measured
    2026-08-07: 11 in `wafer_map_metadata`, 10 in `production_plan`). Writing an
    unrelated row must not touch them, and - the part this pins - they must not acquire
    a synthetic identity behind the operator's back. That is the ruling this lane was
    narrowed by, and a guard is the only thing that keeps a withdrawn mechanism
    withdrawn."""
    model = models.DYNAMIC_TABLES[PLAIN]
    survivors = []
    for i in range(3):
        r = model(row_id=f"manual-{i}", payload=f"M{i}")
        db.add(r)
        survivors.append(r.row_id)
    db.commit()

    _push(db, PLAIN, [_plain_item(unit_id="UNRELATED", payload="X")])

    for rid in survivors:
        r = _row(db, PLAIN, rid)
        assert r is not None, "a manual row disappeared"
        assert r.business_key_val is None


def test_create_empty_rows_batch_still_leaves_the_key_null(db):
    """CONTROL, passes both ways. `add_business_key_unique_index.py` chooses a plain
    UNIQUE index over `NULLS NOT DISTINCT` precisely so this path works - the "add empty
    row" button would fail on its second click otherwise."""
    rows = crud.create_empty_rows_batch(db, PLAIN, 3, "operator")
    assert len(rows) == 3
    assert all(r.business_key_val is None for r in rows)
