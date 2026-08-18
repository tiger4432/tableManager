"""Stage 7 manifest-only cutover and production lot_event preparation tests."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

import pandas as pd
import pytest

from ledger.backfill import v2_base_select_columns
from ledger.setup import (
    DEFAULT_ONTOLOGY_ROOT,
    LedgerSetupError,
    dry_run_report,
    execute_selected_cursor_batch,
    live_physical_catalog,
    load_setup,
    main as setup_main,
    physical_catalog_path,
    preview_selected_cursor_batch,
)
from ledger.setup_bundle import LedgerSetupValidationError, load_setup_bundle
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


def test_one_file_is_the_only_entry_and_compiles_deterministically():
    """MOVED from test_manifest_is_the_only_entry_...

    Determinism survives untouched. What changed is the second half: there is no selector
    to consult, so "which sources are active" is answered by the declaration itself."""
    first = load_setup()
    second = load_setup()

    assert first.snapshot.snapshot_sha256 == second.snapshot.snapshot_sha256
    assert first.snapshot.serialize() == second.snapshot.serialize()
    assert first.source_ids == ("lot_event",)
    assert first.require_source("lot_event") == "lot_event"


# RETIRED: test_manifest_covers_every_current_legacy_ledger_source.
# It compared the v2 declaration against the LEGACY `server/config/ledger_config.json` to
# prove nothing had been left behind in the cutover. That comparison target does not
# exist -- the file was never present on this box and the legacy grammar is being retired
# -- so the test measured one side against an absence. Retired because the thing it
# compared to is gone, not because it stopped passing.


# SUPERSEDED: test_lot_event_catalog_matches_current_physical_table_contract.
# Its subject was the ledger's OWN `tables` section, pinned column-for-column against
# `table_config.json` so the two copies could not drift apart. That duplicate no longer
# exists -- `ledger_config.json` has no `tables` section and the ledger reads the physical
# schema straight from `table_config.json` -- so there is nothing left to compare and the
# assertion could only ever raise KeyError. It is REPLACED rather than deleted, because
# the invariant it protected did not disappear with it, it moved: the question is no
# longer "do the two copies agree" but "is the one copy the thing the ledger actually
# read". The two tests below answer that -- one that the catalog the setup carries IS the
# adaptation of `table_config.json`, one that re-introducing a second copy is refused by
# name instead of being quietly ignored (a silently-ignored section is how a stale
# duplicate would come back).
def test_loaded_setup_carries_the_adaptation_of_the_live_table_config():
    declared = json.loads(
        physical_catalog_path().read_text(encoding="utf-8"))["lot_event"]
    setup = load_setup()

    # The expected adaptation is spelled out here rather than obtained by calling
    # `load_physical_catalog` on the same file: a test that ran the translator against
    # itself would pass no matter what the translator did.
    expected = {"columns": dict(declared["column_types"])}
    if declared.get("composite_key_source"):
        expected["composite_key"] = list(declared["composite_key_source"])
    if declared.get("indexes"):
        expected["indexes"] = [dict(item) for item in declared["indexes"]]
    # `business_key` is carried only when it names a column OF the relation; a key
    # pointing at something that is not a column certifies no ordering.
    if declared.get("business_key") in expected["columns"]:
        expected["business_key"] = declared["business_key"]

    assert dict(setup.catalog["lot_event"]) == expected
    # And it is the catalog the validation used, not one re-read afterwards.
    assert setup.snapshot.source_plans["lot_event"].relation == "lot_event"


def test_a_tables_section_in_the_ledger_file_is_refused_by_name(tmp_path):
    root = copied_root(tmp_path)
    config_path = root / "ledger_config.json"
    document = json.loads(config_path.read_text(encoding="utf-8"))
    document["tables"] = {"lot_event": {"columns": {"lot_id": "string"}}}
    config_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(LedgerSetupValidationError) as exc:
        load_setup_bundle(root, catalog=live_physical_catalog())

    assert exc.value.code == "unknown_field"
    assert exc.value.path == "ledger_config.tables"


def test_operator_report_is_ready_and_explicitly_non_destructive():
    report = dry_run_report(load_setup())

    assert report["readiness"] == "ready"
    # MOVED: the per-source row lost `mode`/`parity_status`/`approval_ref` with the
    # selector and gained the relation it reads. The report's REASON for existing is
    # unchanged -- an operator asking "what will run, and will it destroy anything".
    assert report["sources"] == ({
        "source_id": "lot_event",
        "relation": "lot_event",
    },)
    assert dict(report["destructive_actions"]) == {
        "database_reset": False,
        "cursor_reset": False,
        "legacy_removal": False,
    }


def test_existing_cursor_selects_only_physical_lot_event_columns():
    setup = load_setup()

    assert v2_base_select_columns(setup.snapshot, "lot_event") == tuple(sorted({
        "lot_id", "event_type", "slotnumbers", "waferids", "parent_lot",
        "child_lot", "txn_seq", "event_time",
    }))
    assert "event_group_key" not in v2_base_select_columns(
        setup.snapshot, "lot_event")
    assert "row_identity" not in v2_base_select_columns(
        setup.snapshot, "lot_event")


def test_live_physical_batch_normalizes_then_uses_stage6_compiler_path():
    setup = load_setup()
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
    setup = load_setup()
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


# RETIRED: test_v2_mode_requires_approved_parity.
# `parity_status` was a string the compiler compared against the literal "approved" and
# against nothing else -- it never referenced a measurement, so it certified only that
# somebody had typed the word. THE MACHINERY IS GONE. What actually holds a half-written
# source back is unchanged and earlier: `require_ready_bundle` refuses at load if any
# profile binding is not approved, which the readiness tests still cover.


# RETIRED: test_every_bundle_source_requires_one_selector.
# It required every declared source to ALSO appear in the selector. Declaration is now
# activation, so the second place to say so is gone and there is nothing left to omit.
# Retired because the requirement was removed deliberately, not because it failed.


def test_unknown_source_is_rejected_by_name():
    """MOVED from test_unknown_selector_source_is_rejected.

    Naming a source that does not exist used to be caught when the selector was
    cross-checked against `sources`; it is now caught when the source is asked for. The
    refusal is what matters and it survived the move -- asking for something undeclared
    must name it rather than return an empty run."""
    setup = load_setup()

    with pytest.raises(LedgerSetupError) as exc:
        setup.require_source("unknown")

    assert exc.value.to_mapping()["code"] == "unknown_source"
    assert exc.value.to_mapping()["path"] == "sources.unknown"
    assert "unknown" in exc.value.to_mapping()["message"]


# RETIRED: test_legacy_selector_cannot_enter_v2_execute.
# It proved a source parked on `mode: "legacy"` could not reach the v2 write path. There
# is no legacy mode and no legacy path to be parked on. THE MACHINERY IS GONE. The
# surviving half -- that an undeclared source cannot reach the store -- is covered by
# test_unknown_source_is_rejected_by_name above.


def test_cutover_module_exposes_no_reset_or_legacy_removal_capability():
    import ledger.setup as module

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

    with pytest.raises(LedgerSetupError) as exc:
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

    with pytest.raises(LedgerSetupError) as exc:
        backfill.run(
            object(), source="lot_event", ontology_root=DEFAULT_ONTOLOGY_ROOT)

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

    with pytest.raises(LedgerSetupError) as exc:
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

    with pytest.raises(LedgerSetupError) as exc:
        backfill.run(
            object(), source="lot_event", ontology_root=DEFAULT_ONTOLOGY_ROOT)

    assert exc.value.to_mapping() == {
        "code": "cursor_snapshot_reset_required",
        "path": "ledger_cursor.lot_event.translator_ver",
        "message": (
            "existing cursor belongs to a different setup snapshot; inspect, back up, "
            "and obtain separate reset or replay approval"),
    }


# ------------------------------------------------- `--root`: verify a draft, not the live file
#
# 🔴 THE GUIDE TELLS AN OPERATOR TO VERIFY BEFORE EDITING. Until `--root` existed,
# `python -m ledger.setup` was hard-wired to `DEFAULT_ONTOLOGY_ROOT` and took no argument,
# so the only way to verify a draft was to overwrite the live file first — the one thing
# the guide forbids. These pin the argument AND the two ways of getting it wrong, because
# an operator pointing at a draft in production meets both.

def test_verify_without_root_still_reads_the_live_config(capsys):
    assert setup_main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["config_root"] == DEFAULT_ONTOLOGY_ROOT.resolve().as_posix()


def test_verify_with_root_reads_the_draft_and_says_which_file_it_read(tmp_path, capsys):
    draft = copied_root(tmp_path)
    assert setup_main(["--root", str(draft)]) == 0
    report = json.loads(capsys.readouterr().out)
    # Naming the root is what makes a draft run distinguishable from a live one. A report
    # that did not carry it would let an operator read a PASS for the wrong file.
    assert report["config_root"] == draft.resolve().as_posix()
    assert report["config_root"] != DEFAULT_ONTOLOGY_ROOT.resolve().as_posix()
    assert report["destructive_actions"] == {
        "database_reset": False, "cursor_reset": False, "legacy_removal": False}


def test_verifying_a_draft_does_not_touch_the_live_config(tmp_path, capsys):
    """READ ONLY, asserted as a fact about the live file rather than as a promise."""
    live = DEFAULT_ONTOLOGY_ROOT / "ledger_config.json"
    before = live.read_bytes()
    draft = copied_root(tmp_path)
    (draft / "ledger_config.json").write_text(
        json.dumps({**json.loads((draft / "ledger_config.json").read_text("utf-8")),
                    "setup_version": 3}, ensure_ascii=False), encoding="utf-8")
    assert setup_main(["--root", str(draft)]) == 0
    capsys.readouterr()
    assert live.read_bytes() == before


@pytest.mark.parametrize("bad, fragment", [
    ("nowhere", "no such path"),
    ("ontology/ledger_config.json", "point --root at the directory"),
    ("bare", "holds no ledger_config.json"),
])
def test_a_wrong_root_is_a_named_refusal_not_a_traceback(tmp_path, capsys, bad, fragment):
    copied_root(tmp_path)
    (tmp_path / "bare").mkdir()
    assert setup_main(["--root", str(tmp_path / bad)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "", "a refused verification must not print a report"
    assert fragment in captured.err


def test_verify_reports_every_problem_not_only_the_first(tmp_path, capsys, monkeypatch):
    """🔴 AUTHORING GETS THE WHOLE LIST; THE RUNTIME STILL STOPS AT THE FIRST.

    Measured 2026-08-19: hand-authoring one source took ~20 save-and-refuse cycles, and a
    large share of them were discovering problems that were all present in the first save.
    `validate_bundle_errors` already returned the whole list -- the command simply let the
    loader raise and printed one.

    Scored on the transfer sample rather than a copy of the live root, which is hand-edited
    and gitignored; the catalog is patched to the sample's plant for the same reason the
    sample carries its own `table_config.json`.
    """
    from ledger import setup as setup_module
    from ledger.setup_bundle import load_physical_catalog
    from tests.support.ontology_explorer_sample import SAMPLE_CATALOG, SAMPLE_ROOT

    catalog = load_physical_catalog(SAMPLE_CATALOG)
    monkeypatch.setattr(setup_module, "live_physical_catalog", lambda: catalog)

    root = tmp_path / "draft"
    root.mkdir()
    raw = json.loads((SAMPLE_ROOT / "ledger_config.json").read_text(encoding="utf-8"))
    mapper = sorted(raw["mappers"])[0]
    pack = sorted(raw["packs"])[0]
    claim = sorted(raw["packs"][pack]["claims"])[0]
    predicate = sorted(raw["vocabulary"])[0]
    entity_type = sorted(raw["entities"])[0]
    source = sorted(raw["sources"])[0]
    raw["mappers"][mapper]["emits"] = "one/claim"
    raw["packs"][pack]["claims"][claim]["emit"]["object"]["payload"] = {"n": 1}
    raw["vocabulary"][predicate]["colour"] = "blue"
    raw["entities"][entity_type]["allow_null"] = "yes"
    raw["sources"][source]["driver"]["unit"] = "wafer"
    (root / "ledger_config.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    assert setup_main(["--root", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "", "a refused verification must not print a report"
    lines = [line for line in captured.err.splitlines() if line.strip()]
    # All five, from ONE run. Named individually so a regression that drops one kind of
    # check cannot hide behind a count.
    for expected in (
        f"bundle.mappers.{mapper}.emits",
        f"bundle.packs.{pack}.claims.{claim}.emit.object.payload",
        f"bundle.vocabulary.{predicate}.colour",
        f"bundle.entities.{entity_type}.allow_null",
        f"bundle.sources.{source}.driver.unit",
    ):
        assert any(expected in line for line in lines), expected
    assert lines[-1].endswith(f"{len(lines) - 1} problem(s) in {root}")

    # The runtime loader, on the same root, still stops at the first -- and the one it
    # stops at is among the lines above. The two paths differ in HOW MANY, never in WHAT.
    with pytest.raises(LedgerSetupValidationError) as refused:
        setup_module.load_setup(root)
    assert any(refused.value.path in line for line in lines)
