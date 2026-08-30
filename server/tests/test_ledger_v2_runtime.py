"""Stage 6 tests for the existing gate/store transaction execution adapter."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from types import MappingProxyType

import pytest

from ledger import gate
from ledger.runtime_v2 import (
    LedgerV2RuntimeError,
    execute_cursor_batch,
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


class RecordingStore:
    def __init__(self, *, failure=None):
        self.calls = []
        self.failure = failure

    def write_batch(self, source, translator_ver, atoms, cursor_value, molecules,
                    refused=0, incomplete=0, *, reasons,
                    enforce_translator_version=False, advance_cursor=True):
        self.calls.append({
            "advance_cursor": advance_cursor,
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

    executed = execute_cursor_batch(
        compiled, "input_rows", base, cursor_for(base), reader_for(base),
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
    assert store.calls[0]["enforce_translator_version"] is True
    canonical = lambda value: json.dumps(  # noqa: E731 - compact test comparator
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    stored = sorted((semantic_atom(atom) for atom in store.calls[0]["atoms"]),
                    key=canonical)
    assert [canonical(value) for value in stored] == [
        canonical(dict(value)) for value in dry.candidate_semantics]
    assert store.calls[0]["cursor_value"] == dict(dry.cursor_value)


@pytest.mark.parametrize("cursor", [
    {"event_at": "2026-08-17T12:00:00+00:00"},
    {"event_at": "2026-08-17T12:00:00+00:00", "record_id": "NOT-IN-BATCH"},
    {"event_at": "2026-08-17T12:00:00+00:00", "record_id": "R-0000",
     "target_id": "virtual-output"},
    {"event_at": "2026-08-17T12:00:00+00:00", "record_id": "R-0001"},
])
def test_cursor_accepts_exact_physical_columns_and_only_values_in_the_batch(cursor):
    compiled = snapshot()
    base = base_rows()
    store = RecordingStore()

    with pytest.raises(LedgerV2RuntimeError) as exc:
        execute_cursor_batch(
            compiled, "input_rows", base, cursor, reader_for(base), preparers(),
            mappers(), store)

    assert exc.value.code == "invalid_cursor"
    assert exc.value.path.startswith("cursor_value")
    assert store.calls == []


def test_missing_physical_cursor_column_has_structured_failure_before_preparation():
    compiled = snapshot()
    base = base_rows().drop(columns=["record_id"])
    store = RecordingStore()

    with pytest.raises(LedgerV2RuntimeError) as exc:
        execute_cursor_batch(
            compiled, "input_rows", base,
            {"event_at": base.iloc[0]["event_at"], "record_id": "R-0000"},
            FakeJoinReader(), preparers(), mappers(), store)

    assert exc.value.to_mapping() == {
        "code": "invalid_cursor_batch",
        "path": "source_batch.columns",
        "message": "base batch is missing cursor columns ['record_id']",
    }
    assert store.calls == []


def test_source_preparation_failure_writes_no_atom_and_moves_no_cursor():
    compiled = snapshot()
    base = base_rows()
    store = RecordingStore()

    with pytest.raises(SourcePreparationError) as exc:
        execute_cursor_batch(
            compiled, "input_rows", base, cursor_for(base), FakeJoinReader(),
            preparers(), mappers(), store)

    assert exc.value.code == "source_preparation_missing"
    assert store.calls == []


def test_gate_refusal_writes_no_atom_and_moves_no_cursor(monkeypatch):
    compiled = snapshot()
    base = base_rows()
    store = RecordingStore()

    def refuse(*args, **kwargs):
        raise gate.MoleculeRefused("input_rows", "test_refusal", "compiled gate refusal")

    monkeypatch.setattr(gate, "screen_compiled_molecule", refuse)
    with pytest.raises(gate.MoleculeRefused):
        execute_cursor_batch(
            compiled, "input_rows", base, cursor_for(base), reader_for(base),
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
        execute_cursor_batch(
            compiled, "input_rows", base, cursor_for(base), reader_for(base),
            preparers(), mappers(), store)

    assert calls == 2
    assert store.calls == []


def test_store_failure_is_not_converted_to_success_or_cursor_advance():
    compiled = snapshot()
    base = base_rows()
    failure = RuntimeError("database write failed")
    store = RecordingStore(failure=failure)

    with pytest.raises(RuntimeError, match="database write failed"):
        execute_cursor_batch(
            compiled, "input_rows", base, cursor_for(base), reader_for(base),
            preparers(), mappers(), store)

    assert len(store.calls) == 1
    assert store.calls[0]["enforce_translator_version"] is True


def test_store_without_version_guard_is_explicitly_unsupported():
    compiled = snapshot()
    base = base_rows()

    class LegacyShapeStore:
        def write_batch(self, source, translator_ver, atoms, cursor_value,
                        molecules, refused=0, incomplete=0, *, reasons):
            raise AssertionError("body must not run")

    with pytest.raises(LedgerV2RuntimeError) as exc:
        execute_cursor_batch(
            compiled, "input_rows", base, cursor_for(base), reader_for(base),
            preparers(), mappers(), LegacyShapeStore())
    assert exc.value.to_mapping() == {
        "code": "unsupported_store_contract",
        "path": "store.write_batch",
        "message": "LedgerStore must enforce the setup snapshot cursor version",
    }


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
def test_the_scoped_door_lands_the_same_atoms_and_asks_for_no_cursor_advance():
    """Same gate, same translation, same atoms - and the position is not written.

    Compared against the forward scan over the identical batch rather than against a
    hand-written expectation: the danger of a second write path is that it drifts into
    screening differently, and only the forward scan's own output can detect that.
    """
    compiled = snapshot()
    base = base_rows()

    forward = RecordingStore()
    execute_cursor_batch(
        compiled, "input_rows", base, cursor_for(base), reader_for(base),
        preparers(), mappers(), forward)

    scoped = RecordingStore()
    execute_scoped_batch(
        compiled, "input_rows", base, ("join_id", ["J-0000"]), reader_for(base),
        preparers(), mappers(), scoped)

    assert [semantic_atom(atom) for atom in scoped.calls[0]["atoms"]] == \
           [semantic_atom(atom) for atom in forward.calls[0]["atoms"]]
    assert forward.calls[0]["advance_cursor"] is True
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
                        enforce_translator_version=False):
            raise AssertionError("body must not run")

    with pytest.raises(LedgerV2RuntimeError) as caught:
        execute_scoped_batch(
            compiled, "input_rows", base, ("join_id", ["J-0000"]), reader_for(base),
            preparers(), mappers(), CursorAlwaysStore())
    assert caught.value.to_mapping() == {
        "code": "unsupported_store_contract",
        "path": "store.write_batch",
        "message": "LedgerStore must be able to append atoms without moving the cursor",
    }


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
