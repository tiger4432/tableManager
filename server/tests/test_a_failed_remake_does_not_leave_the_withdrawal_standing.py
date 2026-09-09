# -*- coding: utf-8 -*-
"""A rescope that failed halfway DELETED atoms and left nothing in their place.

S-60, grade 1. `rescope` withdrew the old generation in one transaction, committed it, and
then translated and wrote the new one in a second. A remake that failed for any reason --
and on 2026-09-08 one did, on the objectless-payload CHECK -- left the withdrawal standing:
the two atoms of one `dt_job` (its `register` and its `has_netdie`) were simply gone, and
only running the same scope again brought them back.

🔴 REORDERING IS NOT THE FIX. Remake-first collides with the atoms still present on
`uq_ledger_atom`, so the write dedupes to nothing and the withdrawal then takes everything --
the same loss, arrived at more quietly. One transaction is the fix, and the withdrawal
therefore travels to `store.write_batch` as `withdraw_refs` and runs inside the commit that
writes the replacement.

⚠️ 「그 사이에 두 세대가 있다」 HAS NO OBSERVER. Both statements are inside one transaction, so
nothing outside it can see between them.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill, schema                                  # noqa: E402
from ledger.envelope import Atom                                     # noqa: E402
from ledger.implementations import (role_mapper_registry,            # noqa: E402
                                    source_preparer_registry,
                                    trusted_implementations)
from ledger.setup import LedgerSetup                                 # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,              # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot             # noqa: E402
from ledger.store import LedgerStore                                 # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
OCCURRED_AT = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)
REFS = ["raw-1", "raw-2"]


@pytest.fixture(scope="module")
def setup():
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    snapshot = compile_setup_snapshot(
        bundle, trusted_implementations(), (), catalog=catalog)
    return LedgerSetup(
        config_root=Path(SAMPLE), bundle=bundle, snapshot=snapshot,
        preparers=source_preparer_registry(), mappers=role_mapper_registry(),
        catalog=catalog)


# ------------------------------- the withdrawal never travels on a transaction of its own

class SpyStore:
    """A store that records the one call `execute_scoped_batch` is allowed to make.

    ⚠️ ITS INDEX IS EMPTY ON PURPOSE (S-101). Since the withdrawal is aimed from
    `schema.ROW_REF_TABLE` as well as from the new translation, a store double that answered
    that question would change what these cases carry - and what they are about is the
    TRANSACTION the refs travel in, not which refs they are. An empty index leaves the aim
    exactly `REFS`, which is what the assertions below were written against.
    """

    def __init__(self, raises=None):
        self.calls = []
        self.raises = raises
        self.forgotten = []

    def row_refs_for(self, relation, row_ids):
        return []

    def forget_row_refs(self, relation, row_ids, source=None):
        self.forgotten.append((relation, tuple(row_ids), source))
        return 0

    def write_batch(self, *args, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        return {"attempted": 2, "inserted": 2, "deduped": 0, "molecules": 1,
                "withdrawn": len(kwargs.get("withdraw_refs") or ())}


class SpyConnection:
    """Every connection `rescope` opens for itself. It may read; it may not delete."""

    def __init__(self, log):
        self.log = log

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.log.append(" ".join(str(sql).split()))

    rowcount = 2

    def fetchone(self):
        return (0,)

    def fetchall(self):
        return []

    def rollback(self):
        pass

    def commit(self):
        self.log.append("COMMIT")

    def close(self):
        pass


def run_rescope(setup, monkeypatch, store, rows):
    statements = []

    monkeypatch.setattr(backfill, "preview_rescope", lambda *a, **k: {
        "source": "dt_job", "scope_column": "dt_job", "scope_values": 1,
        "rows_in_scope": len(rows), "withdraw": 2, "remake": 2, "refs": list(REFS)})
    monkeypatch.setattr(backfill, "_fetch_v2_lineage_rows",
                        lambda *a, **k: rows)
    monkeypatch.setattr("ledger.store.LedgerStore", lambda engine: store)
    engine = SimpleNamespace(raw_connection=lambda: SpyConnection(statements))
    return backfill.rescope(
        engine, setup, "dt_job", "dt_job", ["SYN-DTJ-002-04"], apply=True), statements


def dt_log_rows(count=2):
    return [{"created_at": OCCURRED_AT, "dt_cell_key": f"C{index}", "dt_eqp": "EQP-7",
             "dt_index": index, "dt_job": "SYN-DTJ-002-04", "event_time": OCCURRED_AT,
             "row_id": f"r{index}"}
            for index in range(count)]


def test_the_refs_reach_the_store_instead_of_a_delete_of_our_own(setup, monkeypatch):
    """🔴 THE PROPERTY. `rescope` opens connections to READ; the only statement that removes
    an atom is the store's, inside the transaction that writes the replacement. A DELETE on
    a connection of ours is the shape that lost data, whatever it is followed by."""
    store = SpyStore()
    result, statements = run_rescope(setup, monkeypatch, store, dt_log_rows())
    assert len(store.calls) == 1
    assert list(store.calls[0]["withdraw_refs"]) == REFS
    assert store.calls[0]["advance_cursor"] is False
    assert not [line for line in statements if "DELETE" in line.upper()], statements
    assert "COMMIT" not in statements, "rescope must commit nothing of its own"
    assert result["withdrawn"] == len(REFS) and result["applied"] is True


def test_a_write_that_raises_takes_the_withdrawal_down_with_it(setup, monkeypatch):
    """🔴 THE INCIDENT, AS A TEST. The remake fails; because the delete is inside that same
    call, nothing of it survives -- and `rescope` must not have removed anything before
    reaching it either."""
    store = SpyStore(raises=RuntimeError("check violation"))
    with pytest.raises(RuntimeError):
        run_rescope(setup, monkeypatch, store, dt_log_rows())


def test_nothing_is_withdrawn_when_neither_the_preview_nor_the_index_names_a_ref(
        setup, monkeypatch):
    """⚠️ THIS CASE NARROWED ON 2026-09-09 AND THE OLD SENTENCE WAS THE DEFECT (S-101).

    It used to read "a scope whose rows produce no atoms has nothing to aim a withdrawal
    with", and that was exactly what ruling 199 found: a row EXCLUDED by the declaration
    produces no atoms either, so the aim went empty in the one case where the old atoms had
    to go and this returned having done nothing. The aim now also asks the row index, so the
    case that returns early is the narrower one - nothing to withdraw AND nothing to put in
    its place, which is what this store's empty index says.
    """
    store = SpyStore()
    statements = []
    monkeypatch.setattr(backfill, "preview_rescope", lambda *a, **k: {
        "source": "dt_job", "scope_column": "dt_job", "scope_values": 1,
        "rows_in_scope": 3, "withdraw": 0, "remake": 0, "refs": []})
    monkeypatch.setattr(backfill, "_fetch_v2_lineage_rows", lambda *a, **k: dt_log_rows(3))
    monkeypatch.setattr("ledger.store.LedgerStore", lambda engine: store)
    result = backfill.rescope(
        SimpleNamespace(raw_connection=lambda: SpyConnection(statements)),
        setup, "dt_job", "dt_job", ["SYN-DTJ-002-04"], apply=True)
    assert store.calls == [] and result["applied"] is False
    assert result["withdrawn"] == 0 and result["forgotten"] == 0
    assert store.forgotten == [], "nothing was withdrawn, so no index line is stale"
    assert not [line for line in statements if "DELETE" in line.upper()], statements


# ------------------------------------------------- the statement itself, with no server

def test_the_withdrawal_is_one_statement_scoped_to_this_source():
    """⛔ `source_who` IS IN THE PREDICATE. Aiming by `source_raw_ref` alone would reach an
    atom another source wrote about the same subject, and a rescope of one source would
    quietly withdraw another's work."""
    log = []
    store = LedgerStore.__new__(LedgerStore)
    assert store._withdraw_refs(SpyConnection(log), "dt_job", []) == 0
    assert log == [], "no refs means no statement, not a DELETE matching nothing"

    store._withdraw_refs(SpyConnection(log), "dt_job", REFS)
    assert len(log) == 1
    assert "DELETE FROM" in log[0]
    assert "WHERE source_who = %s AND source_raw_ref = ANY(%s)" in log[0]


# ------------------------------------------------ and what one transaction means, in Postgres

def atom(raw_ref, object_payload=None, predicate="register"):
    return Atom(
        subject_type="dtjob@1", subject_keys={"dt_job": "J1"}, predicate=predicate,
        object_kind=None, object_payload=object_payload, occurred_at=OCCURRED_AT,
        source_who="dt_job", source_translator_ver="v1", source_raw_ref=raw_ref,
        source_event_id=uuid.uuid4(), source_event_state="source_molecule",
        derivation="d")


@pytest.fixture
def store(pg_engine):
    connection = pg_engine.raw_connection()
    try:
        schema.ensure_schema(connection)
        schema.ensure_partition(connection, OCCURRED_AT)
    finally:
        connection.close()
    return LedgerStore(pg_engine)


def rows_named(store, raw_ref):
    connection = store.connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {schema.LEDGER_TABLE} "
                           "WHERE source_raw_ref = %s", (raw_ref,))
            return int(cursor.fetchone()[0])
    finally:
        connection.close()


def write(store, atoms, withdraw_refs=None):
    return store.write_batch(
        "dt_job", "v1", atoms, {"dt_job": "J1"}, 1, reasons={},
        advance_cursor=False, withdraw_refs=withdraw_refs)


def test_a_failed_write_withdraws_nothing(store):
    """🔴 THE GATE THE RULING ASKED FOR, MEASURED RATHER THAN ARGUED: make the remake fail
    and the atom count is the same before and after.

    The failure is a real one and not a stub -- an objectless atom carrying a `value` is
    refused by `ck_ledger_objectless_carries_only_qualifiers`, which is the very constraint
    that produced the 2026-09-08 incident."""
    write(store, [atom("raw-1")])
    assert rows_named(store, "raw-1") == 1

    with pytest.raises(Exception):
        write(store, [atom("raw-1", {"value": 1})], withdraw_refs=["raw-1"])

    assert rows_named(store, "raw-1") == 1, (
        "the withdrawal committed while the replacement did not -- atoms were lost")


def test_the_success_path_replaces_the_generation(store):
    """And when it succeeds the old generation is gone and the new one is there, from one
    commit -- the numbers the caller reports come back with it."""
    write(store, [atom("raw-1")])
    written = write(store, [atom("raw-1", {"qualifiers": {"dt_eqp": "EQP-7"}})],
                    withdraw_refs=["raw-1"])
    assert written["withdrawn"] == 1 and written["inserted"] == 1
    assert rows_named(store, "raw-1") == 1

    connection = store.connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT object_payload FROM {schema.LEDGER_TABLE} "
                           "WHERE source_raw_ref = 'raw-1'")
            assert cursor.fetchone()[0] == {"qualifiers": {"dt_eqp": "EQP-7"}}
    finally:
        connection.close()


def test_a_write_with_nothing_to_withdraw_is_the_write_it_always_was(store):
    """⚠️ THE FORWARD SCAN GOES THROUGH THIS SAME DOOR and passes no refs; it must issue no
    DELETE at all and report `withdrawn: 0`."""
    written = write(store, [atom("raw-9")])
    assert written["withdrawn"] == 0 and written["inserted"] == 1
