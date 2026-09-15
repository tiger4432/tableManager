# -*- coding: utf-8 -*-
"""S-186-b. A catalogue entry may only name columns the relation actually has.

🔴 MEASURED: the shipped sample's `ledger_events` entry declared NINE columns, and FOUR of
them do not exist -- `recorded_at`, `subject_key`, `source`, `tx_id`. The physical table has
fourteen. An operator who copies the shipped shape into the live catalogue gets
`UndefinedColumn` and a 500 from the data route, on a relation whose whole point is to be
read.

⛔ THE CAUSE WAS WRITING A CATALOGUE FROM MEMORY. I wrote that entry during S-186 beside the
DDL and spelled the columns as I remembered them: `subject_key` for `subject_keys`, `source`
for `source_who`, and two names (`recorded_at`, `tx_id`) belonging to no table here. Its own
comment then described `payload` and `qualifiers` as columns, which are keys INSIDE
`object_payload`. Nothing failed, because no test read the declaration against the relation.

🔴 SO THE LIST HAS ONE AUTHOR AND THIS FILE SCORES AGAINST IT. `envelope.ROW_COLUMNS` is the
tuple `store.insert_atoms` interpolates into its `INSERT`, so a name in it that the table
lacks fails every ledger write -- it cannot be a second memory of the schema the way a
hand-typed list in a test can. `test_the_catalogue_matches_what_ensure_schema_builds` closes
the remaining gap by asking PostgreSQL, which is the only witness that owes nothing to any
Python list.
"""
import io
import json
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from ledger import schema                                            # noqa: E402
from ledger.envelope import ROW_COLUMNS                              # noqa: E402
from ledger.setup_bundle import catalog_kind                         # noqa: E402

SAMPLE = os.path.join(server_dir, "config", "sample", "table_config.json.sample")

#: The four names the sample declared that belong to no column of this table. Pinned so the
#: regression has a name rather than only a count.
NAMES_THAT_NEVER_EXISTED = ("recorded_at", "subject_key", "source", "tx_id")

#: Relation -> the columns the PRODUCT says it has. One entry today; the loop below is over
#: the catalogue, so the day a second ledger relation is declared it is covered by adding a
#: line here rather than by writing another test.
PHYSICAL_COLUMNS = {schema.LEDGER_TABLE: frozenset(ROW_COLUMNS)}


@pytest.fixture(scope="module")
def catalog():
    with io.open(SAMPLE, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# 🔴 The gate — the declaration is scored against the relation
# ---------------------------------------------------------------------------

def test_no_entry_declares_a_column_its_relation_does_not_have(catalog):
    """The property, over every entry -- not over `ledger_events` by name."""
    for name, entry in catalog.items():
        physical = PHYSICAL_COLUMNS.get(name)
        if physical is None:
            continue
        declared = set((entry or {}).get("column_types") or {})
        assert declared <= physical, (
            name, sorted(declared - physical),
            "declared columns this relation does not have")


def test_the_ledger_entry_declares_the_physical_columns_in_full(catalog):
    """⚠️ SUBSET IS NOT ENOUGH HERE. A grid that is the only reader of the ledger must be
    able to show every recorded field; a column left out is invisible rather than wrong,
    which is the quieter failure of the two."""
    declared = set(catalog[schema.LEDGER_TABLE]["column_types"])
    assert declared == frozenset(ROW_COLUMNS), (
        sorted(declared - set(ROW_COLUMNS)), sorted(set(ROW_COLUMNS) - declared))


def test_the_four_invented_names_are_gone(catalog):
    declared = set(catalog[schema.LEDGER_TABLE]["column_types"])
    assert declared.isdisjoint(NAMES_THAT_NEVER_EXISTED), sorted(
        declared.intersection(NAMES_THAT_NEVER_EXISTED))


def test_the_entry_is_still_a_read_only_view_with_a_total_order(catalog):
    """🔴 THE TWO LINES S-186 PUT THERE MUST SURVIVE THIS EDIT. `kind: view` is what the
    write door reads to refuse a cell, and `business_key` is what `total_order_key` reads --
    SCHEMA_CANON R7 refuses a capped read without one, so losing it turns the route into a
    refusal rather than into a wrong answer."""
    entry = catalog[schema.LEDGER_TABLE]
    assert catalog_kind(entry) == "view"
    assert entry["business_key"] in entry["column_types"]


# ---------------------------------------------------------------------------
# The witness that owes nothing to a Python list
# ---------------------------------------------------------------------------

@pytest.mark.pg
def test_the_catalogue_matches_what_ensure_schema_builds(catalog):
    """🔴 ASKS POSTGRESQL, because both assertions above lean on `ROW_COLUMNS` and a list
    can be wrong in the same direction as the declaration that copied it. This runs the
    product's own `ensure_schema` into a scratch schema and inspects the result.

    ⚠️ IT SKIPS WITHOUT A DECLARED TEST DATABASE, and that is why it is not the only gate in
    this file: a skipped test reports nothing, so the assertions above are the ones that
    hold on a box with no PostgreSQL.
    """
    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:                                     # pragma: no cover
        pytest.skip("psycopg2 is not importable: %s" % exc)

    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    from ledger import store as ledger_store

    scratch = "assy_pytest_s186b"
    with _declared_as_test_database(url):
        engine = create_engine(url, poolclass=NullPool,
                               connect_args=scratch_connect_args(scratch))
        admin = create_engine(url, poolclass=NullPool)
        try:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
                conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        except OperationalError as exc:
            pytest.skip("PostgreSQL is not reachable: %s"
                        % str(exc).strip().splitlines()[0])
        try:
            ledger_store.LedgerStore(engine).ensure_schema()
            built = {c["name"] for c in
                     inspect(engine).get_columns(schema.LEDGER_TABLE, schema=scratch)}
            assert built == frozenset(ROW_COLUMNS), (
                sorted(built - set(ROW_COLUMNS)), sorted(set(ROW_COLUMNS) - built))
            declared = set(catalog[schema.LEDGER_TABLE]["column_types"])
            assert declared == built, (sorted(declared - built), sorted(built - declared))
        finally:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            engine.dispose()
            admin.dispose()
