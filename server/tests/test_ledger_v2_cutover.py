"""Stage 7 manifest-only cutover and production lot_event preparation tests."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

import pandas as pd
import pytest

from ledger.backfill import v2_base_select_columns
from ledger.cutover_v2 import (
    DEFAULT_ONTOLOGY_ROOT,
    LedgerV2CutoverError,
    dry_run_report,
    execute_selected_cursor_batch,
    load_cutover_setup,
    preview_selected_cursor_batch,
)
from ledger.source_preparation import VerifiedJoinBatchReader


NOW = pd.Timestamp("2026-08-17T10:00:00+09:00")


class NoJoinReader(VerifiedJoinBatchReader):
    def read_chunk(self, descriptor, keys):
        raise AssertionError("production lot_event has no inherited virtual join")


class RecordingStore:
    def __init__(self):
        self.calls = []

    def write_batch(self, source, translator_ver, atoms, cursor_value, molecules,
                    refused=0, incomplete=0, *, reasons,
                    enforce_translator_version=False):
        self.calls.append({
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
        return {"attempted": len(atoms), "inserted": len(atoms),
                "deduped": 0, "molecules": molecules}


def physical_split_rows():
    return pd.DataFrame([
        {
            "lot_id": "P", "event_type": "split", "slotnumbers": "1:2",
            "waferids": "W1:W2", "parent_lot": "", "child_lot": "C",
            "txn_seq": "R1", "event_time": NOW,
        },
        {
            "lot_id": "C", "event_type": "split", "slotnumbers": "3",
            "waferids": "W3", "parent_lot": "P", "child_lot": "",
            "txn_seq": "R2", "event_time": NOW,
        },
    ], dtype=object)


def cursor_for(frame):
    row = frame.iloc[-1]
    return {"event_time": row["event_time"], "txn_seq": row["txn_seq"]}


def copied_root(tmp_path: Path) -> Path:
    root = tmp_path / "ontology"
    shutil.copytree(DEFAULT_ONTOLOGY_ROOT, root)
    return root


def mutate_selector(root: Path, mutate):
    path = root / "dataflows" / "chains.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    mutate(raw["chains"]["ledger_v2_execution"]["sources"])
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def test_manifest_is_the_only_entry_and_compiles_deterministically():
    first = load_cutover_setup()
    second = load_cutover_setup()

    assert first.snapshot.snapshot_sha256 == second.snapshot.snapshot_sha256
    assert first.snapshot.serialize() == second.snapshot.serialize()
    assert tuple(first.selections) == ("lot_event",)
    assert first.selection("lot_event").mode == "v2"
    assert first.selection("lot_event").parity_status == "approved"


def test_manifest_covers_every_current_legacy_ledger_source():
    legacy_path = DEFAULT_ONTOLOGY_ROOT.parent / "ledger_config.json"
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    setup = load_cutover_setup()

    assert set(legacy["sources"]) == set(setup.selections) == {"lot_event"}


def test_lot_event_catalog_matches_current_physical_table_contract():
    table_path = DEFAULT_ONTOLOGY_ROOT.parent / "table_config.json"
    table_config = json.loads(table_path.read_text(encoding="utf-8"))["lot_event"]
    setup = load_cutover_setup()
    declared = setup.bundle.section("tables")["lot_event"]

    assert dict(declared["columns"]) == table_config["column_types"]
    assert declared["business_key"] == table_config["business_key"]


def test_operator_report_is_ready_and_explicitly_non_destructive():
    report = dry_run_report(load_cutover_setup())

    assert report["readiness"] == "ready"
    assert report["sources"] == ({
        "source_id": "lot_event",
        "mode": "v2",
        "parity_status": "approved",
        "approval_ref": "stage6:b98f0c3804f5bdfc6653670da571f8fef0e9e129",
    },)
    assert dict(report["destructive_actions"]) == {
        "database_reset": False,
        "cursor_reset": False,
        "legacy_removal": False,
    }


def test_existing_cursor_selects_only_physical_lot_event_columns():
    setup = load_cutover_setup()

    assert v2_base_select_columns(setup.snapshot, "lot_event") == tuple(sorted({
        "lot_id", "event_type", "slotnumbers", "waferids", "parent_lot",
        "child_lot", "txn_seq", "event_time",
    }))
    assert "event_group_key" not in v2_base_select_columns(
        setup.snapshot, "lot_event")
    assert "row_identity" not in v2_base_select_columns(
        setup.snapshot, "lot_event")


def test_live_physical_batch_normalizes_then_uses_stage6_compiler_path():
    setup = load_cutover_setup()
    frame = physical_split_rows()

    preview = preview_selected_cursor_batch(
        setup, "lot_event", frame, cursor_for(frame), NoJoinReader(),
        known_registrations=(),
    )

    assert preview.atom_count == 10
    assert preview.molecule_count == 1
    assert preview.incomplete_count == 0
    assert {item["predicate"] for item in preview.candidate_semantics} == {
        "register", "has_wafer", "derived_from", "slot_map",
    }
    assert all(item["source_who"] == "lot_event"
               for item in preview.candidate_semantics)


def test_selected_execute_reuses_preview_candidates_and_existing_store_transaction():
    setup = load_cutover_setup()
    frame = physical_split_rows()
    store = RecordingStore()

    preview = preview_selected_cursor_batch(
        setup, "lot_event", frame, cursor_for(frame), NoJoinReader(),
        known_registrations=(),
    )
    executed = execute_selected_cursor_batch(
        setup, "lot_event", frame, cursor_for(frame), NoJoinReader(), store,
        known_registrations=(),
    )

    assert executed.preview.candidate_semantics == preview.candidate_semantics
    assert len(store.calls) == 1
    assert store.calls[0]["cursor_value"] == {
        "event_time": NOW.isoformat(), "txn_seq": "R2"}
    assert store.calls[0]["enforce_translator_version"] is True
    assert len(store.calls[0]["atoms"]) == preview.atom_count


def test_v2_mode_requires_approved_parity(tmp_path):
    root = copied_root(tmp_path)
    mutate_selector(root, lambda sources: sources["lot_event"].update(
        parity_status="pending"))

    with pytest.raises(LedgerV2CutoverError) as exc:
        load_cutover_setup(root)

    assert exc.value.to_mapping() == {
        "code": "cutover_not_approved",
        "path": (
            "bundle.chains.ledger_v2_execution.sources.lot_event.parity_status"),
        "message": "v2 execution requires approved source parity",
    }


def test_every_bundle_source_requires_one_selector(tmp_path):
    root = copied_root(tmp_path)
    mutate_selector(root, lambda sources: sources.pop("lot_event"))

    with pytest.raises(LedgerV2CutoverError) as exc:
        load_cutover_setup(root)

    assert exc.value.to_mapping() == {
        "code": "missing_execution_selector",
        "path": "bundle.chains.ledger_v2_execution.sources.lot_event",
        "message": "source 'lot_event' requires an explicit execution selector",
    }


def test_unknown_selector_source_is_rejected(tmp_path):
    root = copied_root(tmp_path)
    mutate_selector(root, lambda sources: sources.update({
        "unknown": {
            "mode": "legacy", "parity_status": "pending",
            "approval_ref": "not-cut-over",
        }}))

    with pytest.raises(LedgerV2CutoverError) as exc:
        load_cutover_setup(root)

    assert exc.value.to_mapping() == {
        "code": "unknown_execution_source",
        "path": "bundle.chains.ledger_v2_execution.sources.unknown",
        "message": "selector names unknown source 'unknown'",
    }


def test_legacy_selector_cannot_enter_v2_execute(tmp_path):
    root = copied_root(tmp_path)
    mutate_selector(root, lambda sources: sources["lot_event"].update(
        mode="legacy", parity_status="pending", approval_ref="legacy-frozen"))
    setup = load_cutover_setup(root)
    frame = physical_split_rows()
    store = RecordingStore()

    with pytest.raises(LedgerV2CutoverError) as exc:
        execute_selected_cursor_batch(
            setup, "lot_event", frame, cursor_for(frame), NoJoinReader(), store,
            known_registrations=(),
        )

    assert exc.value.to_mapping() == {
        "code": "legacy_source_selected",
        "path": "sources.lot_event.mode",
        "message": "source 'lot_event' remains on the legacy execution path",
    }
    assert store.calls == []


def test_cutover_module_exposes_no_reset_or_legacy_removal_capability():
    import ledger.cutover_v2 as module

    forbidden = {"reset", "truncate", "drop", "delete", "unlink", "rmtree"}
    public = {name.lower() for name in vars(module) if not name.startswith("_")}
    assert forbidden.isdisjoint(public)


def test_backfill_runs_the_ontology_root_without_being_asked_to(monkeypatch):
    """`ontology_root` is now a location, not a mode switch.

    It used to default to None and None meant LEGACY, so any in-process caller that simply
    did not pass it silently took the retired path. There is one path; omitting the
    argument selects the shipped root, never a second grammar.
    """
    import ledger.backfill as backfill

    calls = []
    monkeypatch.setattr(
        backfill, "_run_v2_lineage",
        lambda engine, setup, **kwargs: calls.append((engine, setup, kwargs)) or {
            "source": kwargs["source"], "selected": "v2"})

    explicit = backfill.run(
        object(), source="lot_event", ontology_root=DEFAULT_ONTOLOGY_ROOT,
        max_batches=1)
    implied = backfill.run(object(), source="lot_event", max_batches=1)

    assert explicit == implied == {"source": "lot_event", "selected": "v2"}
    assert len(calls) == 2
    assert calls[0][2]["reset_cursor"] is False
    assert calls[0][1].config_root == calls[1][1].config_root


def test_v2_backfill_refuses_reset_controls_before_store_access():
    import ledger.backfill as backfill

    with pytest.raises(LedgerV2CutoverError) as exc:
        backfill.run(
            object(), source="lot_event", ontology_root=DEFAULT_ONTOLOGY_ROOT,
            reset_cursor=True)

    assert exc.value.to_mapping() == {
        "code": "destructive_approval_required",
        "path": "reset_cursor",
        "message": (
            "v2 cursor reset or replay requires a separate destructive approval"),
    }


def test_existing_legacy_cursor_shape_blocks_v2_before_source_read(monkeypatch):
    import ledger.backfill as backfill
    import ledger.store as store_module

    class ReadConnection:
        def close(self):
            pass

    class FakeStore:
        def __init__(self, engine):
            self.engine = engine

        def ensure_schema(self):
            pass

        def connection(self):
            return ReadConnection()

        def read_cursor(self, connection, source):
            return {"cursor_value": {"event_time": NOW.isoformat()}}

    monkeypatch.setattr(store_module, "LedgerStore", FakeStore)

    with pytest.raises(LedgerV2CutoverError) as exc:
        backfill.run(
            object(), {}, source="lot_event", ontology_root=DEFAULT_ONTOLOGY_ROOT)

    assert exc.value.to_mapping() == {
        "code": "legacy_cursor_reset_required",
        "path": "ledger_cursor.lot_event.cursor_value",
        "message": (
            "existing cursor shape does not match the v2 physical cursor; inspect, "
            "back up, and obtain separate reset approval"),
    }


def test_operator_cli_has_no_legacy_escape_hatch(monkeypatch):
    """The retired flags are UNKNOWN to the parser, not merely discouraged.

    Asserting the refusal rather than the absence: a flag that is quietly ignored still
    lets an operator believe the run they asked for is the run they got.
    """
    import database.database as database_module
    import ledger.backfill as backfill

    calls = []
    monkeypatch.setattr(database_module, "engine", object())
    monkeypatch.setattr(backfill, "beat", lambda result: None)
    monkeypatch.setattr(
        backfill, "run", lambda engine, **kwargs: calls.append(kwargs) or {})

    assert backfill.main(["--max-batches", "0"]) == 0
    assert calls[-1]["ontology_root"] == str(DEFAULT_ONTOLOGY_ROOT)
    assert "cfg" not in calls[-1]

    for argv in (["--legacy"], ["--config", "legacy.json"]):
        with pytest.raises(SystemExit) as exc:
            backfill.main([*argv, "--max-batches", "0"])
        assert exc.value.code == 2
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("argv", "path"),
    [
        (["--reset-cursor"], "reset_cursor"),
        (["--from", "2026-08-17T00:00:00"], "start_from"),
    ],
)
def test_operator_cli_blocks_reset_and_replay_before_io(
        monkeypatch, argv, path):
    import ledger.backfill as backfill

    monkeypatch.setattr(
        backfill, "run", lambda *args, **kwargs: pytest.fail("source must not run"))

    with pytest.raises(LedgerV2CutoverError) as exc:
        backfill.main(argv)

    assert exc.value.to_mapping() == {
        "code": "destructive_approval_required",
        "path": path,
        "message": "cursor reset or replay requires a separate destructive approval",
    }


def test_existing_other_snapshot_cursor_blocks_before_source_read(monkeypatch):
    import ledger.backfill as backfill
    import ledger.store as store_module

    class ReadConnection:
        def close(self):
            pass

    class FakeStore:
        def __init__(self, engine):
            pass

        def ensure_schema(self):
            pass

        def connection(self):
            return ReadConnection()

        def read_cursor(self, connection, source):
            return {
                "translator_ver": "ledger-v2:older-snapshot",
                "cursor_value": {
                    "event_time": NOW.isoformat(), "txn_seq": "R2"},
            }

    monkeypatch.setattr(store_module, "LedgerStore", FakeStore)

    with pytest.raises(LedgerV2CutoverError) as exc:
        backfill.run(
            object(), {}, source="lot_event", ontology_root=DEFAULT_ONTOLOGY_ROOT)

    assert exc.value.to_mapping() == {
        "code": "cursor_snapshot_reset_required",
        "path": "ledger_cursor.lot_event.translator_ver",
        "message": (
            "existing cursor belongs to a different setup snapshot; inspect, back up, "
            "and obtain separate reset or replay approval"),
    }
