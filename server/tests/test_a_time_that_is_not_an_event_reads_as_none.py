# -*- coding: utf-8 -*-
"""총괄 29047aedc · 3bf28f893: an atom whose `occurred_at` is not an event time (`occurred_at_basis`
set - an entity reference, an `ingested` source) is never read AS an event time - every window keeps
it, the outside count leaves it out, the walk shows no time on its edge, and a node's first sighting
does not count it. One function decides (`schema.reads_as_event_time` / `event_time_sql`).

PostgreSQL through the product's own lookup and gaps query, and the in-memory double beside it.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer, gaps, schema  # noqa: E402
from ledger.envelope import ROW_COLUMNS  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

T0 = datetime(2026, 5, 3, 2, 0, tzinfo=timezone.utc)
LATER = T0 + timedelta(days=10)
DIE = {"mat_id": "W1", "mat_type": "Wafer", "x": "1", "y": "0"}


def _row(predicate, obj_type, obj_keys, when, basis):
    return {"id": str(uuid.uuid4()), "subject_type": "die", "subject_keys": json.dumps(DIE),
            "predicate": predicate, "object_kind": "entity_ref",
            "object_payload": json.dumps({"type": obj_type, "keys": obj_keys}),
            "occurred_at": when, "source_who": "src", "source_translator_ver": "v1",
            "source_raw_ref": str(uuid.uuid4()), "supersedes": None, "source_event_id": str(uuid.uuid4()),
            "source_event_state": "source_molecule", "occurred_at_basis": basis}


#: an event (die transferred at T0) and a reference (die in its wafer) stored with an EARLIER time - so
#: a reader that took the stored time as an event time would move the die's first sighting
STORED_EARLIER = T0 - timedelta(days=5)
ATOMS = [_row("transfer", "die", {"mat_id": "J1", "mat_type": "DT", "x": "3", "y": "4"}, T0, None),
         _row("in_container", "wafer", {"wafer": "W1"}, STORED_EARLIER, schema.REFERENCE_BASIS)]


@pytest.fixture(scope="module", name="engine")
def fixture_engine():
    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args, scratch_schema
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from ledger import store as ledger_store

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    scratch = scratch_schema("assy_pytest_not_event_time")
    with _declared_as_test_database(url):
        built = create_engine(url, poolclass=NullPool, connect_args=scratch_connect_args(scratch))
        admin = create_engine(url, poolclass=NullPool)
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        try:
            store = ledger_store.LedgerStore(built)
            store.ensure_schema()
            raw = built.raw_connection()
            try:
                store.ensure_partitions(raw, [T0, STORED_EARLIER])
                with raw.cursor() as cursor:
                    for atom in ATOMS:
                        cursor.execute(
                            f"INSERT INTO {schema.LEDGER_TABLE} ({', '.join(ROW_COLUMNS)}) "
                            f"VALUES ({', '.join(['%s'] * len(ROW_COLUMNS))})", [atom[c] for c in ROW_COLUMNS])
                raw.commit()
            finally:
                raw.close()
            yield built
        finally:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            built.dispose()
            admin.dispose()


def _fetched(engine, since):
    raw = engine.raw_connection()
    try:
        lookup = ledger_subgraph.SqlEvidenceLookup(raw, since=since)
        atoms, _ = lookup.claims_for_entities([("die", DIE)], "outgoing", 50)
        return sorted(a.predicate for a in atoms), lookup.interval_excluded, atoms
    finally:
        raw.close()


@pytest.mark.pg
def test_a_window_after_the_event_keeps_the_reference_and_counts_only_the_event_out(engine):
    predicates, excluded, atoms = _fetched(engine, LATER)
    assert predicates == ["in_container"]
    assert excluded == 1
    assert atoms[0].occurred_at_basis == schema.REFERENCE_BASIS, "the walk reads the basis with the atom"


@pytest.mark.pg
def test_a_window_around_the_event_keeps_both(engine):
    predicates, excluded, _ = _fetched(engine, T0 - timedelta(days=1))
    assert predicates == ["in_container", "transfer"] and excluded == 0


@pytest.mark.pg
def test_a_first_sighting_counts_event_times_only(engine):
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute(gaps._nodes_of_type_sql().format(table=schema.LEDGER_TABLE),
                           {"bare": "wafer", "scan": 10})
            wafer = cursor.fetchall()
            cursor.execute(gaps._nodes_of_type_sql().format(table=schema.LEDGER_TABLE),
                           {"bare": "die", "scan": 10})
            dies = {json.dumps(row[0], sort_keys=True): row[1] for row in cursor.fetchall()}
    finally:
        raw.close()
    assert len(wafer) == 1 and wafer[0][1] is None, "the wafer is named only by a reference"
    assert dies[json.dumps(DIE, sort_keys=True)] == T0, "the die is first seen at its transfer, not the stored time"


def test_the_in_memory_double_and_the_answer_follow_the_same_rule():
    def atom(row):
        return ledger_subgraph.EvidenceAtom(
            id=row["id"], subject_type="die", subject_keys=DIE, predicate=row["predicate"],
            object_kind="entity_ref", object_payload=json.loads(row["object_payload"]),
            occurred_at=row["occurred_at"], source_who="src", source_translator_ver="v1",
            source_raw_ref=row["source_raw_ref"], supersedes=None, source_event_id=row["source_event_id"],
            source_event_state="source_molecule", occurred_at_basis=row["occurred_at_basis"])
    lookup = ledger_subgraph.InMemoryEvidenceLookup([atom(row) for row in ATOMS], since=LATER)
    atoms, _ = lookup.claims_for_entities([("die", DIE)], "outgoing", 50)
    assert [a.predicate for a in atoms] == ["in_container"] and lookup.interval_excluded == 1
    body = ledger_subgraph.subgraph(explorer.entity_id("die", DIE),
                                    ledger_subgraph.InMemoryEvidenceLookup([atom(row) for row in ATOMS]),
                                    hops=1, direction="both")
    shown = {edge["predicate"]: edge["occurred_at"] for edge in body["edges"]}
    assert shown["in_container"] is None and shown["transfer"] is not None
