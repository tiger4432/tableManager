"""Stage 6 tests for the existing gate/store transaction execution adapter."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from types import MappingProxyType

import pytest

from ledger import gate
from ledger.runtime_v2 import (
    LedgerV2RuntimeError,
    execute_scoped_batch,
    preview_cursor_batch,
)
from ledger.setup_registry import cursor_translator_version
from ledger.source_preparation import SourcePreparationError
from ledger.store import CursorVersionConflict, LedgerStore
from test_ledger_setup_registry import snapshot
from test_ledger_source_preparation import (
    FakeJoinReader,
    base_rows,
    mappers,
    preparers,
    reader_for,
)


def cursor_for(frame):
    row = frame.iloc[-1]
    return {"event_at": row["event_at"], "record_id": row["record_id"]}


def scope_for(frame):
    """Every row of this batch, named. The live door writes nothing unscoped (S-113 ⓐ).

    These tests used to drive `execute_cursor_batch`, which took a cursor here. It retired
    with ruling 221 because after S-76 it had no product caller, so the properties below are
    now asked of the door the live path actually uses -- which needs the batch PROVED to be
    the named part rather than a position to write.
    """
    return ("join_id", sorted(frame["join_id"].tolist()))


class RecordingStore:
    def __init__(self, *, failure=None):
        self.calls = []
        self.failure = failure

    def write_batch(self, source, translator_ver, atoms, cursor_value, molecules,
                    refused=0, incomplete=0, *, reasons,
                    enforce_translator_version=False, advance_cursor=True,
                    withdraw_refs=None, row_refs=None, receipt=None):
        self.calls.append({
            "advance_cursor": advance_cursor,
            # S-54-b: which physical row each `source_raw_ref` was built from, written in
            # the same transaction as the atoms so the pair cannot come apart.
            "row_refs": tuple(row_refs or ()),
            # S-60: the scoped door hands the store the generation it REPLACES, so the
            # delete and the insert share one commit. A double that could not take it
            # would make the contract untestable from this side.
            "withdraw_refs": None if withdraw_refs is None else tuple(withdraw_refs),
            "source": source,
            "translator_ver": translator_ver,
            "atoms": tuple(atoms),
            "cursor_value": dict(cursor_value),
            "molecules": molecules,
            "refused": refused,
            "incomplete": incomplete,
            "reasons": dict(reasons),
            "enforce_translator_version": enforce_translator_version,
        })
        if self.failure:
            raise self.failure
        return {"attempted": len(atoms), "inserted": len(atoms),
                "deduped": 0, "molecules": molecules}


def semantic_atom(atom):
    return {
        "source_event_id": str(atom.source_event_id),
        "source_event_state": atom.source_event_state,
        "subject_type": atom.subject_type,
        "subject_keys": atom.subject_keys,
        "predicate": atom.predicate,
        "object_kind": atom.object_kind,
        "object_payload": atom.object_payload,
        "occurred_at": atom.occurred_at.isoformat(),
        "source_who": atom.source_who,
        "source_raw_ref": atom.source_raw_ref,
        "source_translator_ver": atom.source_translator_ver,
        "supersedes": str(atom.supersedes) if atom.supersedes else None,
        "derivation": atom.derivation,
        "molecule_ref": atom.molecule_ref,
    }


def test_dry_run_and_execute_use_the_exact_same_compiler_candidates():
    compiled = snapshot()
    base = base_rows(2)
    dry = preview_cursor_batch(
        compiled, "input_rows", base, cursor_for(base), reader_for(base),
        preparers(), mappers())
    store = RecordingStore()

    executed = execute_scoped_batch(
        compiled, "input_rows", base, scope_for(base), reader_for(base),
        preparers(), mappers(), store)

    assert executed.preview.candidate_semantics == dry.candidate_semantics
    assert executed.preview.snapshot_hash == compiled.snapshot_sha256
    # 🔴 THE CURSOR'S STRING IS THE SOURCE'S FINGERPRINT, NOT THE GLOBAL SNAPSHOT HASH
    # (2026-08-21). This assertion used to read `f"ledger-v2:{compiled.snapshot_sha256}"`
    # and it was right for the rule it measured: one global value that every cursor
    # compared against, which is why editing one source's bindings refused another
    # source's backfill. The INEQUALITY is pinned beside the equality on purpose -- an
    # equality against `cursor_translator_version` alone would still hold if that function
    # went back to returning the global hash, and "these two strings are no longer the
    # same" is the property the per-source cursor actually depends on.
    assert executed.preview.translator_version == cursor_translator_version(
        compiled, "input_rows")
    assert executed.preview.translator_version != (
        f"ledger-v2:{compiled.snapshot_sha256}")
    assert len(store.calls) == 1
    assert store.calls[0]["advance_cursor"] is False
    canonical = lambda value: json.dumps(  # noqa: E731 - compact test comparator
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    stored = sorted((semantic_atom(atom) for atom in store.calls[0]["atoms"]),
                    key=canonical)
    assert [canonical(value) for value in stored] == [
        canonical(dict(value)) for value in dry.candidate_semantics]
    assert store.calls[0]["cursor_value"] == dict(dry.cursor_value)


# ⚰️ `test_cursor_accepts_exact_physical_columns_and_only_values_in_the_batch` - died with
# `execute_cursor_batch`'s `cursor_value` ARGUMENT (S-113 ⓐ, ruling 221). No live door takes
# one: the scoped door derives an unwritten cursor from the batch itself, so there is no
# operator-supplied value left to validate.
#
# ⚰️ `test_missing_physical_cursor_column_has_structured_failure_before_preparation` - same
# door. 🔴 THE PROPERTY IT MEASURED LOST ITS ONLY READER AND IS NAMED HERE: the scoped door
# also needs `plan.driver.cursor_columns` present (it sorts the batch by them) and answers a
# batch without one with a bare pandas `KeyError` rather than `invalid_cursor_batch`. Not
# reachable from the live path, which builds the batch from the relation - so this is a
# contract gap to rule on, not a fault to fix inside a retirement.


def test_source_preparation_failure_writes_no_atom():
    compiled = snapshot()
    base = base_rows()
    store = RecordingStore()

    with pytest.raises(SourcePreparationError) as exc:
        execute_scoped_batch(
            compiled, "input_rows", base, scope_for(base), FakeJoinReader(),
            preparers(), mappers(), store)

    assert exc.value.code == "source_preparation_missing"
    assert store.calls == []


def test_gate_refusal_writes_no_atom(monkeypatch):
    compiled = snapshot()
    base = base_rows()
    store = RecordingStore()

    def refuse(*args, **kwargs):
        raise gate.MoleculeRefused("input_rows", "test_refusal", "compiled gate refusal")

    monkeypatch.setattr(gate, "screen_compiled_molecule", refuse)
    with pytest.raises(gate.MoleculeRefused):
        execute_scoped_batch(
            compiled, "input_rows", base, scope_for(base), reader_for(base),
            preparers(), mappers(), store)

    assert store.calls == []


def test_later_event_refusal_does_not_partially_store_earlier_event(monkeypatch):
    compiled = snapshot()
    base = base_rows(2)
    store = RecordingStore()
    original = gate.screen_compiled_molecule
    calls = 0

    def refuse_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise gate.MoleculeRefused(
                "input_rows", "test_refusal", "second event refused")
        return original(*args, **kwargs)

    monkeypatch.setattr(gate, "screen_compiled_molecule", refuse_second)
    with pytest.raises(gate.MoleculeRefused):
        execute_scoped_batch(
            compiled, "input_rows", base, scope_for(base), reader_for(base),
            preparers(), mappers(), store)

    assert calls == 2
    assert store.calls == []


def test_store_failure_is_not_converted_to_success():
    compiled = snapshot()
    base = base_rows()
    failure = RuntimeError("database write failed")
    store = RecordingStore(failure=failure)

    with pytest.raises(RuntimeError, match="database write failed"):
        execute_scoped_batch(
            compiled, "input_rows", base, scope_for(base), reader_for(base),
            preparers(), mappers(), store)

    assert len(store.calls) == 1
    # The write was attempted and it was the scoped one: a door that swallowed the failure
    # would show zero calls, and one that had quietly become the forward scan would ask for
    # the cursor statement it is not allowed to issue.
    assert store.calls[0]["advance_cursor"] is False


# ⚰️ `test_store_without_version_guard_is_explicitly_unsupported` - died with
# `enforce_translator_version`, which only the retired forward-scan door ever passed
# (S-113 ⓐ). The property survives on the live door and is already measured: the scoped
# door's own `unsupported_store_contract` refusal is pinned further down this file.


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        self.sql = sql

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.cursor_value = FakeCursor(row)
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


class CursorOnlyStore(LedgerStore):
    def __init__(self, connection):
        self.engine = object()
        self.who = "test"
        self._known_partitions = set()
        self._connection = connection

    def connection(self):
        return self._connection

    def ensure_partitions(self, connection, occurred_ats):
        return None

    def insert_atoms(self, connection, atoms):
        return 0, 0


def test_cursor_version_conflict_rolls_back_the_existing_store_transaction():
    connection = FakeConnection(None)
    store = CursorOnlyStore(connection)

    with pytest.raises(CursorVersionConflict):
        store.write_batch(
            "input_rows", "ledger-v2:new", [], {"record_id": "R-1"}, 1,
            reasons={}, enforce_translator_version=True)

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closes == 1
    assert "translator_ver = EXCLUDED.translator_ver" in connection.cursor_value.sql
    assert "RETURNING source" in connection.cursor_value.sql


def test_same_cursor_version_commits_and_legacy_call_shape_remains_available():
    guarded = FakeConnection(("input_rows",))
    result = CursorOnlyStore(guarded).write_batch(
        "input_rows", "ledger-v2:same", [], {"record_id": "R-1"}, 1,
        reasons={}, enforce_translator_version=True)
    assert result["molecules"] == 1
    assert guarded.commits == 1
    assert guarded.rollbacks == 0

    legacy = FakeConnection(None)
    CursorOnlyStore(legacy).write_batch(
        "legacy-source", "legacy-v1", [], {"offset": 1}, 1, reasons={})
    assert legacy.commits == 1
    assert "translator_ver = EXCLUDED.translator_ver" not in legacy.cursor_value.sql



# ------------------------------------------------------ the scoped door (one named part)
def test_the_live_door_lands_the_previews_atoms_and_asks_for_no_cursor_advance():
    """Same gate, same translation, same atoms - and the position is not written.

    ⚰️ IT USED TO COMPARE THE TWO DOORS. The forward scan translated the identical batch
    and the two outputs were asserted equal, because the danger of a second write path is
    that it drifts into screening differently and only the other door's own output can
    detect that. `execute_cursor_batch` retired with S-113 ⓐ (product callers 0), so there
    is no second output left to compare against and the comparison is now against the
    preview this door itself produced - which catches a door that drops or adds atoms after
    screening, and cannot catch a drift in screening, because nothing can any more.
    """
    compiled = snapshot()
    base = base_rows()

    scoped = RecordingStore()
    executed = execute_scoped_batch(
        compiled, "input_rows", base, ("join_id", ["J-0000"]), reader_for(base),
        preparers(), mappers(), scoped)

    assert len(scoped.calls[0]["atoms"]) == executed.preview.atom_count
    assert [semantic_atom(atom)["predicate"] for atom in scoped.calls[0]["atoms"]] == \
           [value["predicate"] for value in executed.preview.candidate_semantics]
    assert scoped.calls[0]["advance_cursor"] is False


def test_every_way_the_scoped_door_could_become_a_whole_source_write_is_refused_by_name():
    """🔴 WITHOUT THE CURSOR STATEMENT, AN UNSCOPED CALL HERE IS THE SECOND WRITE DOOR.

    Each of these otherwise lands atoms and leaves nothing in the cursor row to show it
    happened, which is the shape the standing rule forbids. The third is the one a decorative
    guard would miss: a scope IS named, and the batch reaches outside it anyway.
    """
    compiled = snapshot()
    base = base_rows(2)
    store = RecordingStore()

    def refusal(scope, rows=base):
        with pytest.raises(LedgerV2RuntimeError) as caught:
            execute_scoped_batch(
                compiled, "input_rows", rows, scope, reader_for(rows),
                preparers(), mappers(), store)
        return caught.value.to_mapping()

    assert refusal(None)["code"] == "scope_required"
    assert refusal(("join_id", []))["code"] == "scope_required"
    assert refusal(("no_such_column", ["J-0000"]))["code"] == "scope_column_absent"
    outside = refusal(("join_id", ["J-0000"]))
    assert outside["code"] == "scope_not_honoured"
    # The value that reached outside is NAMED. A refusal that only said "out of scope"
    # would leave the operator unable to tell a wrong scope from a wrong fetch.
    assert "J-0001" in outside["message"]
    assert store.calls == []


def test_a_store_that_cannot_separate_the_two_statements_is_explicitly_unsupported():
    """It would advance the cursor instead, which is the one outcome that must not be quiet."""
    compiled = snapshot()
    base = base_rows()

    class CursorAlwaysStore:
        def write_batch(self, source, translator_ver, atoms, cursor_value,
                        molecules, refused=0, incomplete=0, *, reasons,
                        enforce_translator_version=False, withdraw_refs=None,
                        row_refs=None, receipt=None):
            raise AssertionError("body must not run")

    with pytest.raises(LedgerV2RuntimeError) as caught:
        execute_scoped_batch(
            compiled, "input_rows", base, ("join_id", ["J-0000"]), reader_for(base),
            preparers(), mappers(), CursorAlwaysStore())
    assert caught.value.to_mapping() == {
        "code": "unsupported_store_contract",
        "path": "store.write_batch",
        "message": "LedgerStore must be able to append atoms without moving the cursor, "
                   "to withdraw the generation they replace in the same transaction, and "
                   "to write this batch's receipt inside that same commit",
    }


def test_a_store_that_cannot_take_the_receipt_is_refused_by_the_same_name():
    """🔴 A THIRD ARM OF ONE CONTRACT, NOT A THIRD REFUSAL (S-117, 판정 248). A store that
    silently dropped the receipt would leave the atoms standing with no record that the
    batch happened - the history lying, which is the whole reason the receipt rides the
    atoms' own commit. So it is refused where the other two arms are refused, and by the
    same code, rather than being allowed through with a warning nobody reads."""
    compiled = snapshot()
    base = base_rows()

    class NoReceiptStore:
        def write_batch(self, source, translator_ver, atoms, cursor_value,
                        molecules, refused=0, incomplete=0, *, reasons,
                        enforce_translator_version=False, advance_cursor=True,
                        withdraw_refs=None, row_refs=None):
            raise AssertionError("body must not run")

    with pytest.raises(LedgerV2RuntimeError) as caught:
        execute_scoped_batch(
            compiled, "input_rows", base, ("join_id", ["J-0000"]), reader_for(base),
            preparers(), mappers(), NoReceiptStore())
    assert caught.value.to_mapping()["code"] == "unsupported_store_contract"
    assert "receipt" in caught.value.to_mapping()["message"]


def test_skipping_the_cursor_step_still_commits_the_atoms_and_issues_no_cursor_statement():
    """The atoms commit; the statement that would write a position is never sent at all.

    Asserted on the SQL rather than on the stored value because "not sent" and "sent with
    the value it already had" are indistinguishable from the row afterwards, and only the
    first of the two is free of a read-then-write race.
    """
    connection = FakeConnection(None)
    result = CursorOnlyStore(connection).write_batch(
        "input_rows", "ledger-v2:same", [], {"record_id": "R-1"}, 1,
        reasons={}, advance_cursor=False)

    assert result["molecules"] == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.cursor_value.sql == ""


def test_a_version_guard_that_could_not_be_honoured_is_refused_instead_of_dropped():
    """🔴 The guard IS a condition on the skipped statement, so honouring the pair is a lie.

    Refused before the connection opens, so the caller learns nothing was written from the
    fact that nothing was opened.
    """
    connection = FakeConnection(None)
    with pytest.raises(TypeError, match="advance_cursor"):
        CursorOnlyStore(connection).write_batch(
            "input_rows", "ledger-v2:same", [], {"record_id": "R-1"}, 1,
            reasons={}, enforce_translator_version=True, advance_cursor=False)
    assert connection.commits == 0
    assert connection.closes == 0
