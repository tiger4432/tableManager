"""[Version gate] A table whose single key must always hold the LATEST row only accepts a
machine write when the incoming row's version column is GREATER than the one already
stored. Version is the authority; arrival order is not.

Without the gate this path is last-write-wins, so re-dropping a superseded file makes
current state regress - an ordinary operational accident with no diagnostic of any kind.

The constraint that matters most here is NOT the overwrite one. A newer version must
still never overwrite a human's correction: the gate is a VETO placed in front of the
per-cell layering, never a promotion past it. `test_human_correction_survives_a_newer_version`
is the test that pins that, and it is the one to mutate first when this file is edited -
an over-broad gate (one that force-applies the payload once the version passes) must turn
it red.
"""

import logging
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


# Names carry a prefix that cannot exist in the user's gitignored config: a collision
# there makes `init_dynamic_models` win the race for the shared in-memory schema and the
# suite fails with `no such column` (recorded trap: bonding_log).
TEST_TABLE_CONFIG = {
    # Numeric version column, declared `number`.
    "vergate_test_lot": {
        "business_key": "lot_id",
        "version_column": "rev",
        "column_types": {
            "lot_id": "string",
            "rev": "number",
            "qty": "number",
            "grade": "string",
        },
    },
    # Version column declared TEXT. Holds numeric revisions in one test and ISO-8601
    # timestamps in another and non-orderable text in a third - the point is that the
    # declared type is `string` for all three, so the comparison cannot be chosen from
    # the declaration alone.
    "vergate_test_text": {
        "business_key": "lot_id",
        "version_column": "ver",
        "column_types": {
            "lot_id": "string",
            "ver": "string",
            "grade": "string",
        },
    },
    # Version column declared `datetime` - a real DateTime column, so the stored side is
    # a datetime object and the incoming side is a string.
    "vergate_test_stamp": {
        "business_key": "lot_id",
        "version_column": "update_time",
        "column_types": {
            "lot_id": "string",
            "update_time": "datetime",
            "grade": "string",
        },
    },
    # CONTROL: identical shape, no `version_column`. Proves the default is untouched -
    # every table that does not declare the gate keeps last-write-wins byte for byte.
    "vergate_test_plain": {
        "business_key": "lot_id",
        "column_types": {
            "lot_id": "string",
            "rev": "number",
            "grade": "string",
        },
    },
    # An explicit null - the shape a config carries while the key is documented but not
    # in use. Must be exactly as inert as the absent key.
    "vergate_test_null": {
        "business_key": "lot_id",
        "version_column": None,
        "column_types": {
            "lot_id": "string",
            "rev": "number",
            "grade": "string",
        },
    },
    # MISCONFIGURED on purpose: the declared version column is not a column of the table.
    "vergate_test_ghost": {
        "business_key": "lot_id",
        "version_column": "no_such_column",
        "column_types": {
            "lot_id": "string",
            "grade": "string",
        },
    },
}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    models.init_dynamic_models(TEST_TABLE_CONFIG)
    crud.TABLE_CONFIG.update(TEST_TABLE_CONFIG)

    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)

    # Process-global registry: without the reset a prior test could pre-warm a pair and
    # make "warns once" pass vacuously.
    crud._version_gate_announced.clear()

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud._version_gate_announced.clear()


class _LogCollector(logging.Handler):
    """Attached to the "Server" logger directly rather than through caplog: these tests
    assert HOW MANY records are emitted, so capture must not depend on propagation."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append((record.levelno, record.getMessage()))

    def _of(self, level):
        return [m for lvl, m in self.records if lvl == level and "[VersionGate]" in m]

    @property
    def warnings(self):
        return self._of(logging.WARNING)

    @property
    def infos(self):
        return self._of(logging.INFO)


@pytest.fixture(name="logs")
def fixture_logs():
    logger = logging.getLogger("Server")
    handler = _LogCollector()
    logger.addHandler(handler)
    prev_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        logger.setLevel(prev_level)
        logger.removeHandler(handler)


def _write(db, table, key, updates, source="pipeline_parser", by="watcher"):
    batch = schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                business_key_val=key,
                updates=updates,
                source_name=source,
                updated_by=by,
            )
        ],
        silent=True,
    )
    return crud.apply_batch_updates(db, table, batch)


def _row(db, table, key):
    model = models.DYNAMIC_TABLES[table]
    return db.query(model).filter(model.business_key_val == key).first()


# ---------------------------------------------------------------------------
# The headline: version, not arrival order
# ---------------------------------------------------------------------------

def test_lower_version_arriving_later_does_not_overwrite(db):
    """RED before the gate: re-dropping a superseded file makes current state regress."""
    _write(db, "vergate_test_lot", "LOT-1", {"lot_id": "LOT-1", "rev": 5, "grade": "NEW"})
    _write(db, "vergate_test_lot", "LOT-1", {"lot_id": "LOT-1", "rev": 3, "grade": "OLD"})

    row = _row(db, "vergate_test_lot", "LOT-1")
    assert row.grade == "NEW", "a lower version must not overwrite a higher one"
    assert row.rev == 5


def test_higher_version_arriving_later_does_overwrite(db):
    """The gate is a veto on regression, not a freeze: forward motion still lands."""
    _write(db, "vergate_test_lot", "LOT-2", {"lot_id": "LOT-2", "rev": 3, "grade": "OLD"})
    _write(db, "vergate_test_lot", "LOT-2", {"lot_id": "LOT-2", "rev": 5, "grade": "NEW"})

    row = _row(db, "vergate_test_lot", "LOT-2")
    assert row.grade == "NEW"
    assert row.rev == 5


def test_table_without_a_declaration_is_still_last_write_wins(db):
    """The gate is a property of the TABLE. A table that does not declare a version
    column behaves exactly as it did before this feature existed - which is also the
    baseline the test above is RED against."""
    _write(db, "vergate_test_plain", "LOT-1", {"lot_id": "LOT-1", "rev": 5, "grade": "NEW"})
    _write(db, "vergate_test_plain", "LOT-1", {"lot_id": "LOT-1", "rev": 3, "grade": "OLD"})

    row = _row(db, "vergate_test_plain", "LOT-1")
    assert row.grade == "OLD"
    assert row.rev == 3


def test_a_null_declaration_is_as_inert_as_an_absent_one(db, logs):
    _write(db, "vergate_test_null", "LOT-1", {"lot_id": "LOT-1", "rev": 5, "grade": "NEW"})
    _write(db, "vergate_test_null", "LOT-1", {"lot_id": "LOT-1", "rev": 3, "grade": "OLD"})

    assert _row(db, "vergate_test_null", "LOT-1").grade == "OLD"
    assert logs.warnings == [] and logs.infos == []


def test_a_version_column_that_does_not_exist_refuses_loudly_rather_than_passing(db, logs):
    """A misconfigured declaration must not degrade into "no gate". The column can never
    be in a payload, so every machine overwrite is refused - which is the safe direction -
    and the warning names the column so the config error is findable."""
    _write(db, "vergate_test_ghost", "LOT-G", {"lot_id": "LOT-G", "grade": "FIRST"})
    _write(db, "vergate_test_ghost", "LOT-G", {"lot_id": "LOT-G", "grade": "SECOND"})

    assert _row(db, "vergate_test_ghost", "LOT-G").grade == "FIRST"
    named = [m for m in logs.warnings if crud.REASON_VERSION_MISSING in m]
    assert len(named) == 1, logs.warnings
    assert "no_such_column" in named[0]


# ---------------------------------------------------------------------------
# The constraint that outranks all of the above
# ---------------------------------------------------------------------------

def test_human_correction_survives_a_newer_version(db):
    """A NEWER version must not overwrite a human's correction.

    Version orders only WITHIN a priority tier; it never crosses one. The gate can only
    REFUSE a row - once a row passes, the ordinary per-cell layering decides each cell,
    and `user` (priority 0) outranks `pipeline_parser` (2).

    MUTATION CHECK: make the gate force the payload onto the row once the version passes
    (the plausible over-broad reading of "version is the authority") and this assertion
    must fail. If it does not, the test is not exercising the line it claims to.
    """
    _write(db, "vergate_test_lot", "LOT-9",
           {"lot_id": "LOT-9", "rev": 1, "qty": 10, "grade": "A"})

    # A person corrects the cell.
    _write(db, "vergate_test_lot", "LOT-9", {"grade": "A-CORRECTED"},
           source="user", by="operator")
    assert _row(db, "vergate_test_lot", "LOT-9").grade == "A-CORRECTED"

    # A strictly newer ingestion arrives and disagrees with the human on that cell.
    _write(db, "vergate_test_lot", "LOT-9",
           {"lot_id": "LOT-9", "rev": 7, "qty": 99, "grade": "MACHINE"})

    row = _row(db, "vergate_test_lot", "LOT-9")
    assert row.grade == "A-CORRECTED", "a newer version must never overwrite a human correction"
    # The row DID pass the gate - the untouched-by-anyone cells moved forward.
    assert row.rev == 7
    assert row.qty == 99


def test_a_human_edit_is_never_version_gated(db):
    """A grid edit carries one cell and no version column. Gating it by "version missing"
    would make a version-gated table read-only for people, which inverts the whole point.
    """
    _write(db, "vergate_test_lot", "LOT-U", {"lot_id": "LOT-U", "rev": 4, "grade": "A"})

    _write(db, "vergate_test_lot", "LOT-U", {"grade": "HUMAN"}, source="user", by="operator")

    assert _row(db, "vergate_test_lot", "LOT-U").grade == "HUMAN"


# ---------------------------------------------------------------------------
# Equal version: a no-op, but a findable one
# ---------------------------------------------------------------------------

def test_equal_version_is_a_noop(db):
    _write(db, "vergate_test_lot", "LOT-3", {"lot_id": "LOT-3", "rev": 5, "grade": "FIRST"})
    results, changed, _logs, _deleted = _write(
        db, "vergate_test_lot", "LOT-3", {"lot_id": "LOT-3", "rev": 5, "grade": "SECOND"})

    assert _row(db, "vergate_test_lot", "LOT-3").grade == "FIRST"
    assert changed == [], "an equal-version row must change nothing"


def test_equal_version_with_different_content_is_named_in_the_log(db, logs):
    """The no-op must be loud enough to FIND. Same version + different content means
    version management upstream is broken, and accepting it silently hides that.

    Shape follows the ingestion drop-visibility precedent: nothing per row, a WARNING on
    first sighting per (table, reason) per process, and a per-batch INFO carrying counts.
    """
    _write(db, "vergate_test_lot", "LOT-4", {"lot_id": "LOT-4", "rev": 5, "grade": "FIRST"})
    _write(db, "vergate_test_lot", "LOT-4", {"lot_id": "LOT-4", "rev": 5, "grade": "SECOND"})

    warnings = [m for m in logs.warnings if "version_same_content_differs" in m]
    assert len(warnings) == 1, logs.warnings
    assert "vergate_test_lot" in warnings[0]
    assert "grade" in warnings[0], "the differing column must be named"

    infos = [m for m in logs.infos if "version_same_content_differs" in m]
    assert infos, logs.infos


def test_equal_version_with_identical_content_is_quiet(db, logs):
    """A re-drop of the SAME file is the expected steady state and must not shout."""
    _write(db, "vergate_test_lot", "LOT-5", {"lot_id": "LOT-5", "rev": 5, "grade": "SAME"})
    logs.records.clear()
    _write(db, "vergate_test_lot", "LOT-5", {"lot_id": "LOT-5", "rev": 5, "grade": "SAME"})

    assert not [m for m in logs.warnings if "content_differs" in m], logs.warnings


def test_same_version_differing_only_where_a_human_corrected_is_not_a_defect(db, logs):
    """The content diff is measured against what THIS SOURCE previously wrote, not
    against the displayed cell. A human correction makes the displayed value differ from
    the file forever; reporting that as "version management is broken" would put a
    permanent false warning on every re-drop and get the whole diagnostic ignored."""
    _write(db, "vergate_test_lot", "LOT-6", {"lot_id": "LOT-6", "rev": 5, "grade": "A"})
    _write(db, "vergate_test_lot", "LOT-6", {"grade": "HUMAN"}, source="user", by="operator")
    logs.records.clear()

    # Identical file re-dropped: the parser's own value is unchanged.
    _write(db, "vergate_test_lot", "LOT-6", {"lot_id": "LOT-6", "rev": 5, "grade": "A"})

    assert not [m for m in logs.warnings if "content_differs" in m], logs.warnings


# ---------------------------------------------------------------------------
# Unknown is not "older" and not "newer" - it is refused, by name
# ---------------------------------------------------------------------------

def test_missing_version_is_refused_by_name(db, logs):
    _write(db, "vergate_test_lot", "LOT-7", {"lot_id": "LOT-7", "rev": 5, "grade": "KEEP"})
    _write(db, "vergate_test_lot", "LOT-7", {"lot_id": "LOT-7", "grade": "NO_VERSION"})

    assert _row(db, "vergate_test_lot", "LOT-7").grade == "KEEP"
    named = [m for m in logs.warnings if crud.REASON_VERSION_MISSING in m]
    assert len(named) == 1, logs.warnings
    assert "rev" in named[0], "the refusal must name the version column"


def test_blank_version_is_refused_by_name(db, logs):
    _write(db, "vergate_test_lot", "LOT-8", {"lot_id": "LOT-8", "rev": 5, "grade": "KEEP"})
    _write(db, "vergate_test_lot", "LOT-8", {"lot_id": "LOT-8", "rev": "", "grade": "BLANK"})

    assert _row(db, "vergate_test_lot", "LOT-8").grade == "KEEP"
    assert [m for m in logs.warnings if crud.REASON_VERSION_MISSING in m], logs.warnings


def test_unorderable_text_version_is_refused_by_name(db, logs):
    """A non-ISO text version must not be silently mis-ordered. `REV_B` > `REV_A` is a
    lexical accident, not a version order, so the write is refused and says so."""
    _write(db, "vergate_test_text", "LOT-T1", {"lot_id": "LOT-T1", "ver": "REV_A", "grade": "KEEP"})
    _write(db, "vergate_test_text", "LOT-T1", {"lot_id": "LOT-T1", "ver": "REV_B", "grade": "LEX"})

    assert _row(db, "vergate_test_text", "LOT-T1").grade == "KEEP"
    named = [m for m in logs.warnings if crud.REASON_VERSION_UNORDERABLE in m]
    assert len(named) == 1, logs.warnings


def test_a_row_with_no_stored_version_adopts_the_incoming_one(db, logs):
    """Adoption path: a row written before the column existed has nothing to regress to.
    Refusing it would wedge the table permanently behind a manual backfill. Named so the
    one-time adoption is visible."""
    model = models.DYNAMIC_TABLES["vergate_test_lot"]
    db.add(model(row_id="preexisting-1", business_key_val="LOT-OLD",
                 lot_id="LOT-OLD", grade="LEGACY"))
    db.commit()

    _write(db, "vergate_test_lot", "LOT-OLD", {"lot_id": "LOT-OLD", "rev": 2, "grade": "ADOPTED"})

    row = _row(db, "vergate_test_lot", "LOT-OLD")
    assert row.grade == "ADOPTED"
    assert row.rev == 2
    assert [m for m in logs.infos if crud.NOTE_ROW_VERSION_ABSENT in m], logs.infos


def test_a_brand_new_row_is_created_whatever_its_version(db):
    """Creating a row is not an overwrite. The gate must not block first arrival."""
    _write(db, "vergate_test_lot", "LOT-NEW", {"lot_id": "LOT-NEW", "rev": 1, "grade": "FIRST"})
    assert _row(db, "vergate_test_lot", "LOT-NEW").grade == "FIRST"


# ---------------------------------------------------------------------------
# Type awareness
# ---------------------------------------------------------------------------

def test_numeric_version_in_a_text_column_orders_10_after_9(db):
    """Compared as text, `'10' < '9'`. The comparison is chosen from the VALUE, not from
    the declaration, so a numeric revision stored in a text column still orders."""
    _write(db, "vergate_test_text", "LOT-N", {"lot_id": "LOT-N", "ver": "9", "grade": "NINE"})
    _write(db, "vergate_test_text", "LOT-N", {"lot_id": "LOT-N", "ver": "10", "grade": "TEN"})

    assert _row(db, "vergate_test_text", "LOT-N").grade == "TEN", "10 must be newer than 9"

    # ...and the reverse direction is refused, which is the half a lexical compare passes
    # by accident.
    _write(db, "vergate_test_text", "LOT-N", {"lot_id": "LOT-N", "ver": "9", "grade": "BACK"})
    assert _row(db, "vergate_test_text", "LOT-N").grade == "TEN"


def test_iso8601_text_version_orders_chronologically(db):
    _write(db, "vergate_test_text", "LOT-I",
           {"lot_id": "LOT-I", "ver": "2026-08-04T09:00:00", "grade": "MORNING"})
    _write(db, "vergate_test_text", "LOT-I",
           {"lot_id": "LOT-I", "ver": "2026-08-04T11:30:00", "grade": "LATER"})
    assert _row(db, "vergate_test_text", "LOT-I").grade == "LATER"

    _write(db, "vergate_test_text", "LOT-I",
           {"lot_id": "LOT-I", "ver": "2026-08-04T08:00:00", "grade": "EARLIER"})
    assert _row(db, "vergate_test_text", "LOT-I").grade == "LATER"


def test_iso8601_text_version_compares_across_offsets(db):
    """`10:00+09:00` and `01:00Z` are ONE instant; a text compare calls them different
    and orders them by the wrong digit."""
    _write(db, "vergate_test_text", "LOT-Z",
           {"lot_id": "LOT-Z", "ver": "2026-08-04T10:00:00+09:00", "grade": "KST"})
    _write(db, "vergate_test_text", "LOT-Z",
           {"lot_id": "LOT-Z", "ver": "2026-08-04T01:00:00+00:00", "grade": "SAME_INSTANT"})
    # Same instant -> equal -> no-op.
    assert _row(db, "vergate_test_text", "LOT-Z").grade == "KST"

    _write(db, "vergate_test_text", "LOT-Z",
           {"lot_id": "LOT-Z", "ver": "2026-08-04T02:00:00+00:00", "grade": "ONE_HOUR_ON"})
    assert _row(db, "vergate_test_text", "LOT-Z").grade == "ONE_HOUR_ON"


def test_datetime_column_version_orders_a_stored_object_against_an_incoming_string(db):
    """Declared `datetime`: the stored side is a DateTime column holding a datetime
    OBJECT, the incoming side is the string a parser emits. Both must land on the same
    comparable instant.

    Driven through `version_gate_verdict` rather than through a write, because
    `cast_value_by_type` renders every non-`number` value to text and SQLite's DateTime
    type refuses a string outright - a PRE-EXISTING property of the write boundary, not
    of this gate, and one PostgreSQL does not share (psycopg2 adapts the ISO string).
    This is the exact pair of shapes production puts in front of the comparison.
    """
    from datetime import datetime as _dt, timezone as _tz

    config = TEST_TABLE_CONFIG["vergate_test_stamp"]

    class _Row:
        update_time = _dt(2026, 8, 4, 9, 0, 0, tzinfo=_tz.utc)

    def verdict(text):
        item = schemas.GeneralUpdateItem(
            business_key_val="LOT-D",
            updates={"lot_id": "LOT-D", "update_time": text, "grade": "X"},
            source_name="pipeline_parser",
        )
        return crud.version_gate_verdict("vergate_test_stamp", config, _Row(), False, item)

    assert verdict("2026-08-04 12:00:00") == (True, None)
    assert verdict("2026-08-04T12:00:00+00:00") == (True, None)
    assert verdict("2026-08-04 07:00:00") == (False, crud.REASON_VERSION_OLDER)
    assert verdict("2026-08-04 09:00:00") == (False, crud.REASON_VERSION_SAME)
    # An aware value on the incoming side must be folded to UTC, not compared naively:
    # 18:00+09:00 IS 09:00Z.
    assert verdict("2026-08-04T18:00:00+09:00") == (False, crud.REASON_VERSION_SAME)
    assert verdict("not a timestamp") == (False, crud.REASON_VERSION_UNORDERABLE)


def test_version_that_changes_type_is_refused_not_guessed(db, logs):
    """A numeric version followed by a timestamp is not an ordering - it is a broken
    feed. Two values of different kinds are refused rather than coerced into one."""
    _write(db, "vergate_test_text", "LOT-M", {"lot_id": "LOT-M", "ver": "7", "grade": "NUM"})
    _write(db, "vergate_test_text", "LOT-M",
           {"lot_id": "LOT-M", "ver": "2026-08-04T09:00:00", "grade": "STAMP"})

    assert _row(db, "vergate_test_text", "LOT-M").grade == "NUM"
    assert [m for m in logs.warnings if crud.REASON_VERSION_UNORDERABLE in m], logs.warnings


# ---------------------------------------------------------------------------
# Log volume
# ---------------------------------------------------------------------------

def test_a_thousand_refused_rows_produce_one_warning_and_one_summary(db, logs):
    """Individual silence, named aggregate. At 10M rows a per-row line buries every real
    event, so the per-row record is nothing at all."""
    seed = schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                business_key_val=f"BULK-{i}",
                updates={"lot_id": f"BULK-{i}", "rev": 9, "grade": "NEW"},
                source_name="pipeline_parser",
                updated_by="watcher",
            )
            for i in range(200)
        ],
        silent=True,
    )
    crud.apply_batch_updates(db, "vergate_test_lot", seed)
    logs.records.clear()

    stale = schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                business_key_val=f"BULK-{i}",
                updates={"lot_id": f"BULK-{i}", "rev": 2, "grade": "OLD"},
                source_name="pipeline_parser",
                updated_by="watcher",
            )
            for i in range(200)
        ],
        silent=True,
    )
    crud.apply_batch_updates(db, "vergate_test_lot", stale)

    assert len(logs.warnings) == 1, logs.warnings
    assert crud.REASON_VERSION_OLDER in logs.warnings[0]

    summaries = logs.infos
    assert len(summaries) == 1, summaries
    assert "200" in summaries[0], summaries[0]

    assert _row(db, "vergate_test_lot", "BULK-7").grade == "NEW"


def test_first_sighting_warning_fires_once_per_process(db, logs):
    """A later warning must therefore be something genuinely new."""
    _write(db, "vergate_test_lot", "LOT-W", {"lot_id": "LOT-W", "rev": 5, "grade": "NEW"})
    _write(db, "vergate_test_lot", "LOT-W", {"lot_id": "LOT-W", "rev": 1, "grade": "OLD"})
    assert len([m for m in logs.warnings if crud.REASON_VERSION_OLDER in m]) == 1

    _write(db, "vergate_test_lot", "LOT-W", {"lot_id": "LOT-W", "rev": 2, "grade": "OLD2"})
    assert len([m for m in logs.warnings if crud.REASON_VERSION_OLDER in m]) == 1

    # A DIFFERENT reason on the same table still gets its own first sighting.
    _write(db, "vergate_test_lot", "LOT-W", {"lot_id": "LOT-W", "grade": "NOVER"})
    assert len([m for m in logs.warnings if crud.REASON_VERSION_MISSING in m]) == 1
