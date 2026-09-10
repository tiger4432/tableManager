# -*- coding: utf-8 -*-
"""원장 배치 하나가 «영수증»을 남긴다 (S-117, 판정 248).

🔴 WHY IT HAS TO RIDE THE ATOMS' OWN COMMIT. The receipt says a batch happened and what it
did. Written after the atoms' transaction closes, it can be lost while the atoms stand -
and then the history says a batch never happened that did, which is a worse defect than
having no record at all. So the store takes the row inside the transaction it already has.

⚠️ AND A FAILED BATCH IS THE OPPOSITE CASE, ON PURPOSE. Its transaction rolled back and
took any receipt inside it, so that one is written afterwards in a commit of its own. The
shape rejected for the success path is the only shape available for the failure path, and
the failure is the row an operator most needs to see.

⛔ THE ROW'S CONTENT IS `crud.create_audit_log`'S DECISION, NOT THE LEDGER'S. The ledger
supplies the numbers and the store supplies the connection; if either began assembling the
dict, a column added to `AuditLog` would leave one of them writing yesterday's shape.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                            # noqa: E402
from ledger import followup, runtime_v2, store                         # noqa: E402


# ── the id the receipt is grouped by ─────────────────────────────────────────

def test_the_queue_carries_the_transaction_of_the_event_it_followed():
    followup._queue.clear()
    try:
        assert followup.enqueue("t", ["r1"], "EDIT", "tx-9")
        item = followup._take()
        table, row_ids, event_type, _queued_at, transaction_id = item

        assert (table, row_ids, event_type) == ("t", ("r1",), "EDIT")
        assert transaction_id == "tx-9"
    finally:
        followup._queue.clear()


def test_a_backfill_fills_the_same_queue_with_no_transaction_and_that_is_kept():
    """🔴 THE EMPTY FIELD IS THE VALUE. A backfill or retroactive run has no chain
    transaction behind it, and that emptiness is what separates "this moved because
    somebody edited a cell" from "this moved because a backfill was running" on the
    timeline. Inventing an id here would erase the distinction S-117 exists to show."""
    followup._queue.clear()
    try:
        assert followup.enqueue("t", ["r1"], "CREATE")
        assert followup._take()[4] is None
    finally:
        followup._queue.clear()


def test_the_scope_is_open_only_inside_the_batch_it_was_opened_for():
    assert followup.event_transaction_id() is None
    with followup.following("tx-9"):
        assert followup.event_transaction_id() == "tx-9"
    assert followup.event_transaction_id() is None

    with followup.following(None):
        assert followup.event_transaction_id() is None


# ── the row ──────────────────────────────────────────────────────────────────

class _Preview:
    molecule_count = 7
    refusals = ()
    translator_version = "v-3"


class _Plan:
    relation = "some_relation"


class _Writer:
    """Only the field the receipt reads: who the store says is writing."""

    who = "ledger"


def test_the_receipt_carries_this_batchs_own_counts():
    build = runtime_v2._batch_receipt(_Writer(), _Plan(), _Preview(), rows=11,
                                      batch_id="batch-1")

    row = build({"inserted": 5, "deduped": 2, "withdrawn": 1})

    assert row["table_name"] == "some_relation"
    assert row["row_id"] == "batch-1"
    assert row["column_name"] == runtime_v2.RECEIPT_COLUMN
    assert row["source_name"] == runtime_v2.RECEIPT_SOURCE
    assert row["new_value"]["rows"] == 11
    assert row["new_value"]["molecules"] == 7
    assert row["new_value"]["atoms_written"] == 5
    assert row["new_value"]["atoms_deduped"] == 2
    assert row["new_value"]["status"] == "ok"
    assert row["new_value"]["translator_ver"] == "v-3"


def test_the_receipt_takes_the_transaction_of_whatever_batch_is_running():
    build = runtime_v2._batch_receipt(_Writer(), _Plan(), _Preview(), rows=1,
                                      batch_id="batch-1")

    with followup.following("tx-9"):
        assert build({"inserted": 0, "deduped": 0})["transaction_id"] == "tx-9"


def test_an_unfollowed_batch_keeps_the_empty_field_that_says_so():
    """🔴 `create_audit_log` INVENTS ONE, AND THAT IS WRONG HERE - measured on the
    first live run, where a backfill receipt came back carrying a fresh uuid.

    Inventing an id is right for a cell edit: every human write belongs to some group. For
    a receipt it makes a backfill look like a group of ONE, which on the timeline is
    indistinguishable from a chain event that happened to touch a single table - and that
    difference is the whole thing this record was asked to show.
    """
    build = runtime_v2._batch_receipt(_Writer(), _Plan(), _Preview(), rows=1,
                                      batch_id="batch-1")

    assert build({"inserted": 0, "deduped": 0})["transaction_id"] is None



# ── the insert ───────────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        self.calls.append((statement, params))


class _Connection:
    def __init__(self):
        self.calls = []
        self.committed = 0

    def cursor(self):
        return _Cursor(self.calls)

    def commit(self):
        self.committed += 1

    def rollback(self):
        pass

    def close(self):
        pass


def test_the_column_list_comes_from_the_model_and_skips_its_key():
    connection = _Connection()

    store._insert_audit_row(connection, {"table_name": "t", "row_id": "r",
                                         "column_name": "c", "id": 999})

    (statement, params), = connection.calls
    assert 'INSERT INTO "audit_logs"' in statement, statement
    assert '"id"' not in statement, "the primary key is the database's to choose"
    assert set(params) == {"t", "r", "c"}


def test_an_empty_receipt_writes_nothing():
    connection = _Connection()

    assert store._insert_audit_row(connection, None) == 0
    assert connection.calls == []


# ── the boundary ─────────────────────────────────────────────────────────────

class _Store(store.LedgerStore):
    """The real `write_batch`, with everything around it answered."""

    def __init__(self, connection):
        self._connection = connection
        self.who = "ledger"
        self._known_partitions = set()
        self.seen_at_receipt_time = None

    def connection(self):
        return self._connection

    def ensure_partitions(self, connection, occurred_ats):
        pass

    def insert_atoms(self, connection, atoms):
        return 4, 3

    def _write_row_refs(self, connection, source, refs):
        return 0

    def _advance_cursor(self, *args, **kwargs):
        pass


def test_the_receipt_is_written_before_the_commit_that_makes_the_atoms_durable():
    """🔴 THE WHOLE POINT, ASSERTED ON ORDER. If the row is inserted after the commit it
    is a separate transaction, and a crash between them leaves atoms with no record."""
    connection = _Connection()
    written_at = {}

    def receipt(written):
        written_at["commits_so_far"] = connection.committed
        written_at["counts"] = dict(written)
        return {"table_name": "t", "row_id": "r", "column_name": "c"}

    result = _Store(connection).write_batch(
        "src", "v1", [], {"k": 1}, 2, reasons={}, receipt=receipt)

    assert written_at["commits_so_far"] == 0, "the receipt went in after the commit"
    assert connection.committed == 1
    assert written_at["counts"]["inserted"] == 3
    assert written_at["counts"]["deduped"] == 1
    assert result["inserted"] == 3
    assert len(connection.calls) == 1, connection.calls


def test_a_batch_that_asks_for_no_receipt_writes_none():
    """⚠️ EVERY OTHER CALLER OF THIS DOOR IS UNCHANGED. The seeds and the forward scan
    pass no receipt, and must go on writing exactly the statements they wrote before."""
    connection = _Connection()

    _Store(connection).write_batch("src", "v1", [], {"k": 1}, 2, reasons={})

    assert connection.calls == []
    assert connection.committed == 1


def test_a_failure_receipt_says_failed_and_never_raises():
    """The drain has already named and counted the failure by the time this runs; a
    second exception escaping here would turn "one source could not be followed" into
    "the follow-up loop stopped"."""
    class _Engine:
        def raw_connection(self):
            raise RuntimeError("no database here")

    followup._write_failure_receipt(_Engine(), "t", "src", "tx-9",
                                    ValueError("the reason"))

    connection = _Connection()

    class _Working:
        def raw_connection(self):
            return connection

    followup._write_failure_receipt(_Working(), "t", "src", "tx-9",
                                    ValueError("the reason"))

    (statement, params), = connection.calls
    assert 'INSERT INTO "audit_logs"' in statement
    assert any("failed" in str(p) for p in params), params
    assert "tx-9" in params
    assert connection.committed == 1


def test_the_receipt_column_is_a_mechanism_word_no_declaration_chooses():
    """🔴 코드에 도메인 낱말이 «없다». The timeline filters on this string, so it has to be
    the same on every installation - a declared name would make the screen's filter
    installation-specific and the standing rule forbids exactly that."""
    assert runtime_v2.RECEIPT_COLUMN == "ledger_batch"
    assert followup.RECEIPT_COLUMN is runtime_v2.RECEIPT_COLUMN
    assert followup.RECEIPT_SOURCE is runtime_v2.RECEIPT_SOURCE
    assert models.AuditLog.__table__.name == "audit_logs"
