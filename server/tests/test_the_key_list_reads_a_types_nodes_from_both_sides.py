# -*- coding: utf-8 -*-
"""`/api/ledger/key-values` (총괄 29cee1d47): a type's nodes come from `gaps._nodes_of_type_sql`,
subject AND object side, and each value's count is the atoms naming its nodes on either side.
Run against the product's own `ensure_schema` in a scratch schema.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import schema, trace_router  # noqa: E402
from ledger.envelope import ROW_COLUMNS  # noqa: E402

pytestmark = pytest.mark.pg

WHEN = datetime(2026, 5, 3, 2, 17, tzinfo=timezone.utc)

ENTITIES = {"recipe@1": {"keys": ["recipe"]}, "tool@1": {"keys": ["tool"]},
            "wafer@1": {"keys": ["wafer"]}, "lot@1": {"keys": ["lot"]},
            "lot_slot@1": {"keys": ["lot", "slot"]}, "die@1": {"keys": ["x", "y"]},
            "carrier@1": {"keys": ["carrier"]}}

#: Past a Python float: read back through `float` it is 2.0 and names no atom.
LONG = "2.00000000000000000001"


def _atom(subject_type, keys, predicate="seen", obj=None):
    return {"id": str(uuid.uuid4()), "subject_type": subject_type, "subject_keys": keys,
            "predicate": predicate, "object_kind": "entity_ref" if obj else None,
            "object_payload": json.dumps({"type": obj[0], "keys": obj[1]}) if obj else None,
            "occurred_at": WHEN, "source_who": "src", "source_translator_ver": "v1",
            "source_raw_ref": str(uuid.uuid4()), "supersedes": None, "source_event_id": str(uuid.uuid4()),
            "source_event_state": "source_molecule", "occurred_at_basis": None}


ATOMS = (
    # recipe: object side only - R2 named three times, R1 once
    [_atom("tool", '{"tool": "T%d"}' % i, "uses", ("recipe", {"recipe": "R2"})) for i in range(3)]
    + [_atom("tool", '{"tool": "T9"}', "uses", ("recipe", {"recipe": "R1"}))]
    # wafer: W1 on both sides (two subject atoms, one object atom), W2 subject only
    + [_atom("wafer", '{"wafer": "W1"}'), _atom("wafer", '{"wafer": "W1"}'),
       _atom("lot", '{"lot": "L1"}', "holds", ("wafer", {"wafer": "W1"})),
       _atom("wafer", '{"wafer": "W2"}')]
    # lot vs lot_slot: the slot's `lot` key is not a lot node
    + [_atom("lot_slot", '{"lot": "L1", "slot": 1}'), _atom("lot_slot", '{"lot": "L9", "slot": 1}')]
    # die: subject side only; one JSON-null key; one number past a float
    + [_atom("die", '{"x": 1.0, "y": 2.0}'), _atom("die", '{"x": 1.0, "y": 2.0}'),
       _atom("die", '{"x": 1.0, "y": 3.0}'), _atom("die", '{"x": 0.0, "y": 5.0}'),
       _atom("die", '{"x": null, "y": 3.0}'), _atom("die", '{"x": %s, "y": 1.0}' % LONG)]
)


@pytest.fixture(scope="module")
def engine():
    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args, scratch_schema
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool
    from ledger import store as ledger_store

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    scratch = scratch_schema("assy_pytest_key_values")
    with _declared_as_test_database(url):
        built = create_engine(url, poolclass=NullPool, connect_args=scratch_connect_args(scratch))
        admin = create_engine(url, poolclass=NullPool)
        try:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
                conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        except OperationalError as exc:
            pytest.skip("PostgreSQL is not reachable: %s" % str(exc).strip().splitlines()[0])
        try:
            store = ledger_store.LedgerStore(built)
            store.ensure_schema()
            raw = built.raw_connection()
            try:
                store.ensure_partitions(raw, [WHEN])
                with raw.cursor() as cursor:
                    for atom in ATOMS:
                        cursor.execute(
                            f"INSERT INTO {schema.LEDGER_TABLE} ({', '.join(ROW_COLUMNS)}) "
                            f"VALUES ({', '.join(['%s'] * len(ROW_COLUMNS))})",
                            [atom[c] for c in ROW_COLUMNS])
                raw.commit()
            finally:
                raw.close()
            yield built
        finally:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            built.dispose()
            admin.dispose()


@pytest.fixture
def ask(engine, monkeypatch):
    from sqlalchemy.orm import Session
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda *_a, **_k: {"entities": ENTITIES, "vocabulary": {}})

    def call(type, key=None, limit=50):
        db = Session(bind=engine)
        try:
            return trace_router.ledger_key_values(type=type, key=key, limit=limit, world=None, db=db)
        finally:
            db.close()
    return call


def _listed(answer):
    return [(node["keys"], node["count"]) for node in answer["nodes"]]


def test_a_type_named_only_as_an_object_lists_its_nodes(ask):
    """🔴 The bug: subject side only, so recipe (no atom of its own) listed nothing."""
    assert _listed(ask("recipe")) == [({"recipe": "R1"}, 1), ({"recipe": "R2"}, 3)]


def test_the_order_is_by_value_not_by_count(ask):
    """R2 is named three times and R1 once; R1 still comes first. The node scan is the front
    of the key order, so a count order would rank only the nodes that sort early."""
    answer = ask("recipe")
    assert answer["order"] == "value_asc"
    assert [node["keys"]["recipe"] for node in answer["nodes"]] == ["R1", "R2"]


def test_a_node_on_both_sides_is_one_row_counted_on_both(ask):
    assert _listed(ask("wafer")) == [({"wafer": "W1"}, 3), ({"wafer": "W2"}, 1)]


def test_a_subject_only_type_lists_its_subjects_numbers_kept(ask):
    """The die set is today's subject set less the JSON-null key; numbers stay numbers (`->`)."""
    answer = ask("die")
    assert answer["keys"] == ["x", "y"] and answer["covers_declared_keys"] is True
    assert _listed(answer) == [({"x": 0.0, "y": 5.0}, 1), ({"x": 1.0, "y": 2.0}, 2),
                               ({"x": 1.0, "y": 3.0}, 1), ({"x": 2.0, "y": 1.0}, 1)]


def test_a_key_past_a_float_is_still_counted(ask):
    """The node's keys go back to SQL as stored text; a float round trip would count 0."""
    assert ({"x": 2.0, "y": 1.0}, 1) in _listed(ask("die"))


def test_the_type_is_matched_exactly(ask):
    """`lot` used to be `LIKE 'lot%'`: lot_slot's `lot` key joined the lot list (L9)."""
    assert _listed(ask("lot")) == [({"lot": "L1"}, 1)]


def test_one_axis_groups_the_nodes_and_says_it_does_not_cover(ask):
    answer = ask("die", key="x")
    assert answer["keys"] == ["x"] and answer["covers_declared_keys"] is False
    assert "seedable" not in answer
    assert _listed(answer) == [({"x": 0.0}, 1), ({"x": 1.0}, 3), ({"x": 2.0}, 1)]
    assert answer["limits"]["scan_nodes"] == trace_router.KEY_VALUE_SCAN_NODES


def test_the_value_cut_without_the_scan_cut(ask):
    answer = ask("wafer", limit=1)
    assert _listed(answer) == [({"wafer": "W1"}, 3)]
    assert answer["values_truncated"] is True and answer["scan_truncated"] is False
    assert answer["scanned"] == 2 and answer["limits"] == {"scan_nodes": 2, "values": 1}


def test_the_scan_cut_without_the_value_cut(ask, monkeypatch):
    """Two nodes read of five, in key order: the null-x node and (0.0, 5.0) - one value left."""
    monkeypatch.setattr(trace_router, "KEY_VALUE_SCAN_NODES", 2)
    answer = ask("die", key="x")
    assert _listed(answer) == [({"x": 0.0}, 1)]
    assert answer["scan_truncated"] is True and answer["values_truncated"] is False
    assert answer["scanned"] == 2


def test_a_type_with_no_node_on_either_side_lists_none_and_cuts_nothing(ask):
    answer = ask("carrier")
    assert (answer["nodes"], answer["scanned"], answer["scan_truncated"],
            answer["values_truncated"]) == ([], 0, False, False)


def test_the_wire_cell_is_nodes(ask):
    answer = ask("wafer")
    assert "subjects" not in answer and "scan_rows" not in answer["limits"]
