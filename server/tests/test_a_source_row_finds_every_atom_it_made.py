# -*- coding: utf-8 -*-
"""The flattened ledger read (총괄 0fb9e9390): `ledger_atom_rows`, one row per (atom, source
row), keys and payload in their stored spelling - built by the product's own `ensure_schema`
in a scratch schema and read back.
"""
import io
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import schema  # noqa: E402
from ledger.envelope import ROW_COLUMNS  # noqa: E402

pytestmark = pytest.mark.pg

WHEN = datetime(2026, 5, 3, 2, 17, tzinfo=timezone.utc)
SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "sample",
                      "table_config.json.sample")


def _atom(subject_keys, predicate, raw_ref, source="src", kind=None, payload=None, basis=None):
    return {"id": str(uuid.uuid4()), "subject_type": "die", "subject_keys": json.dumps(subject_keys),
            "predicate": predicate, "object_kind": kind,
            "object_payload": None if payload is None else json.dumps(payload),
            "occurred_at": WHEN, "source_who": source, "source_translator_ver": "v1",
            "source_raw_ref": raw_ref, "supersedes": None, "source_event_id": str(uuid.uuid4()),
            "source_event_state": "source_molecule", "occurred_at_basis": basis}


ATOMS = [
    # row R1 made two refs: ref A said two things, ref B one
    _atom({"mat_id": "M", "x": 1.0}, "in_container", "ref-A", kind="entity_ref",
          payload={"type": "wafer", "keys": {"w": "W"}, "qualifiers": {"step": "1"}}),
    _atom({"mat_id": "M", "x": 1.0}, "has_netdie", "ref-A", kind="value", payload={"value": 72}),
    _atom({"mat_id": "M", "x": 2.0}, "in_container", "ref-B", kind="entity_ref",
          payload={"type": "wafer", "keys": {"w": "W"}}),
    # the same ref TEXT from another source - must not join R1's lines
    _atom({"mat_id": "N", "x": 1}, "in_container", "ref-A", source="other", kind="entity_ref",
          payload={"type": "wafer", "keys": {"w": "V"}}),
    # no row refers to this one (a source that read a view)
    _atom({"mat_id": "Z", "x": 3.0}, "in_container", "ref-none", kind="entity_ref",
          payload={"type": "wafer", "keys": {"w": "W"}}, basis="ingested"),
]
REFS = [("t", "R1", "src", "ref-A"), ("t", "R1", "src", "ref-B"), ("t", "R2", "other", "ref-A")]


@pytest.fixture(scope="module")
def view():
    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args, scratch_schema
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool
    from ledger import store as ledger_store

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    scratch = scratch_schema("assy_pytest_atom_rows")
    with _declared_as_test_database(url):
        engine = create_engine(url, poolclass=NullPool, connect_args=scratch_connect_args(scratch))
        admin = create_engine(url, poolclass=NullPool)
        try:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
                conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        except OperationalError as exc:
            pytest.skip("PostgreSQL is not reachable: %s" % str(exc).strip().splitlines()[0])
        try:
            store = ledger_store.LedgerStore(engine)
            store.ensure_schema()
            raw = engine.raw_connection()
            try:
                store.ensure_partitions(raw, [WHEN])
                with raw.cursor() as cursor:
                    for atom in ATOMS:
                        cursor.execute(
                            f"INSERT INTO {schema.LEDGER_TABLE} ({', '.join(ROW_COLUMNS)}) "
                            f"VALUES ({', '.join(['%s'] * len(ROW_COLUMNS))})",
                            [atom[c] for c in ROW_COLUMNS])
                    for ref in REFS:
                        cursor.execute(f"INSERT INTO {schema.ROW_REF_TABLE} VALUES (%s, %s, %s, %s)", ref)
                raw.commit()
            finally:
                raw.close()
            yield engine, scratch
        finally:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            engine.dispose()
            admin.dispose()


def _rows(engine, where="TRUE", **params):
    from sqlalchemy import text
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(
            f"SELECT * FROM {schema.ATOM_ROWS_VIEW} WHERE {where} "
            "ORDER BY predicate, subject, source_row_id"), params)]


def test_a_source_row_finds_every_atom_it_made(view):
    engine, _ = view
    rows = _rows(engine, "source_row_id = :rid", rid="R1")
    assert [(r["predicate"], r["subject"]) for r in rows] == [
        ("has_netdie", "mat_id=M / x=1.0"), ("in_container", "mat_id=M / x=1.0"),
        ("in_container", "mat_id=M / x=2.0")]
    assert {r["source_who"] for r in rows} == {"src"}, "another source's same ref text joined"


def test_the_plain_text_is_the_stored_spelling(view):
    engine, _ = view
    rows = _rows(engine, "source_row_id = :rid", rid="R1")
    assert [(r["object"], r["qualifiers"]) for r in rows] == [
        ("72", None), ("wafer w=W", "step=1"), ("wafer w=W", None)]
    assert _rows(engine, "source_row_id = :rid", rid="R2")[0]["subject"] == "mat_id=N / x=1"


def test_an_atom_no_row_refers_to_is_one_row_with_empty_source(view):
    engine, _ = view
    [row] = _rows(engine, "subject LIKE :s", s="%Z%")
    assert row["source_relation"] is None and row["source_row_id"] is None
    assert len(_rows(engine)) == 3 + 1 + 1


def test_the_view_is_read_only_and_its_columns_are_the_products(view):
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import DBAPIError

    engine, scratch = view
    built = [c["name"] for c in inspect(engine).get_columns(schema.ATOM_ROWS_VIEW, schema=scratch)]
    with io.open(SAMPLE, encoding="utf-8") as fh:
        declared = list(json.load(fh)[schema.ATOM_ROWS_VIEW]["column_types"])
    assert built == list(schema.ATOM_ROWS_COLUMNS) == declared
    with pytest.raises(DBAPIError):
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE {schema.ATOM_ROWS_VIEW} SET predicate = 'x'"))


def test_the_basis_says_whether_occurred_at_is_the_events_time(view):
    """총괄 271f4512a ④: empty = the event's time, `ingested` = not."""
    engine, _ = view
    assert {r["occurred_at_basis"] for r in _rows(engine, "source_row_id = :rid", rid="R1")} == {None}
    [row] = _rows(engine, "subject LIKE :s", s="%Z%")
    assert row["occurred_at_basis"] == "ingested"


def test_a_view_built_before_the_basis_column_is_replaced_in_place(view, monkeypatch):
    """`add_ledger_atom_rows.py` re-runs `CREATE OR REPLACE VIEW` over an install that built the
    view without the column - Postgres only lets that APPEND, so the column goes last."""
    from sqlalchemy import inspect, text

    engine, scratch = view
    names = schema.world_names()
    with engine.begin() as conn:
        conn.execute(text(f"DROP VIEW {schema.ATOM_ROWS_VIEW}"))
        with monkeypatch.context() as patch:
            patch.setattr(schema, "ATOM_ROWS_SELECT", schema.ATOM_ROWS_SELECT[:-1])
            conn.exec_driver_sql(schema.atom_rows_view_sql(names))
    assert "occurred_at_basis" not in [
        c["name"] for c in inspect(engine).get_columns(schema.ATOM_ROWS_VIEW, schema=scratch)]
    with engine.begin() as conn:
        conn.exec_driver_sql(schema.atom_rows_view_sql(names))
    built = [c["name"] for c in inspect(engine).get_columns(schema.ATOM_ROWS_VIEW, schema=scratch)]
    assert built == list(schema.ATOM_ROWS_COLUMNS) and built[-1] == "occurred_at_basis"
