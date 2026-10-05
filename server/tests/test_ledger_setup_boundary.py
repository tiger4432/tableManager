"""Stage 7 manifest-only cutover tests."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from ledger.setup import (
    DEFAULT_ONTOLOGY_ROOT,
    LedgerSetupError,
    dry_run_report,
    live_physical_catalog,
    load_setup,
    main as setup_main,
    physical_catalog_path,
)
from ledger.setup_bundle import (
    CONFIG_FILENAME,
    LedgerSetupValidationError,
    load_setup_bundle,
    upgrade_setup,
)


def _a_planned_source() -> str:
    """A source THIS box's declaration plans and reads from a table - the subject the
    cases below used to spell as `lot_event`, which retired (setup_version 6)."""
    setup = load_setup()
    planned = sorted(source for source, plan in setup.snapshot.source_plans.items()
                     if setup.catalog[plan.relation].get("kind") == "table")
    assert planned, "the live config plans no table source at all"
    return planned[0]


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
    # 🔴 THE INVARIANT, NOT THE MEMBERSHIP. This used to read
    # `first.source_ids == ("lot_event",)` and went red the day a second source was
    # legitimately DECLARED -- a failure that says "someone added a source", which is the
    # config working. An assertion that a correct change breaks gets deleted as noise and
    # takes the guard with it. What must hold is that compiling neither drops nor invents
    # a source: the KEY SETS of the declaration and the compiled registry are equal, and
    # every one of them resolves. Read straight from the file so the declaration is not
    # being compared against itself.
    declared = set(json.loads(
        (DEFAULT_ONTOLOGY_ROOT / CONFIG_FILENAME).read_text(encoding="utf-8")
    )["sources"])
    assert declared, "the live config declares no source at all"
    assert set(first.source_ids) == declared
    for source_id in declared:
        assert first.require_source(source_id) == source_id
    with pytest.raises(LedgerSetupError) as undeclared:
        first.require_source("no_such_source")
    assert undeclared.value.code == "unknown_source"


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
    # 🔴 RE-AIMED (setup_version 6): this read `lot_event`, which retired. Any source the
    # declaration PLANS answers the same question, so the first one does.
    setup = load_setup()
    relation = setup.snapshot.source_plans[_a_planned_source()].relation
    declared = json.loads(
        physical_catalog_path().read_text(encoding="utf-8"))[relation]

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
    # 🔴 `row_id` IS THE LOADER'S OWN INVARIANT, NOT A TRANSLATION, and this test would be
    # wrong to omit it. `column_types` names the BUSINESS columns; every ingested table
    # carries `PRIMARY KEY (row_id)` and none of them declares it, so `_adapt_physical_
    # catalog` ADDS both the column and its unique index rather than reading them.
    # Written out here for the same reason the rest is: an expectation obtained by calling
    # the translator would pass whatever the translator did.
    expected["columns"].setdefault("row_id", "string")
    expected.setdefault("indexes", []).append({"columns": ["row_id"], "unique": True})
    # 🔴 [총괄 f3bc02f6e] AND ITS KIND - a view may pass `row_id` through, so a source's
    #   「table that has row_id」 test has to be able to ask which one this is.
    expected["kind"] = "table"

    assert dict(setup.catalog[relation]) == expected


# ⚰️ RETIRED with lot_event (setup_version 6, 총괄 819726624): `test_existing_cursor_selects_
# only_physical_lot_event_columns`, `test_live_physical_batch_normalizes_then_uses_stage6_
# compiler_path` and `test_selected_execute_reuses_preview_candidates_and_existing_store_
# transaction`. Each drove THIS box's production lot_event through its preparer; the source
# retired and its preparer with it. Preview and execute sharing one candidate set is still
# measured on the fixture plant (`test_ledger_v2_runtime`).


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
    setup = load_setup()
    report = dry_run_report(setup)

    assert report["readiness"] == "ready"
    # MOVED: the per-source row lost `mode`/`parity_status`/`approval_ref` with the
    # selector and gained the relation it reads. The report's REASON for existing is
    # unchanged -- an operator asking "what will run, and will it destroy anything".
    #
    # 🔴 The rows are asserted as an INVARIANT against the compiled plans, not pinned to
    # one source's name: an operator report that silently omits a declared source is the
    # defect worth catching, and a hard-coded tuple stops being able to catch it the
    # first time a source is legitimately added.
    assert {row["source_id"] for row in report["sources"]} == set(setup.source_ids)
    assert all(
        row["relation"] == setup.snapshot.source_plans[row["source_id"]].relation
        for row in report["sources"])
    assert dict(report["destructive_actions"]) == {
        "database_reset": False,
        "cursor_reset": False,
        "legacy_removal": False,
    }


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
        backfill, "_run_via_events",
        lambda engine, setup, **kwargs: calls.append((engine, setup, kwargs)) or {
            "source": kwargs["source"], "selected": "v2"})

    source = _a_planned_source()
    explicit = backfill.run(
        object(), source=source, ontology_root=DEFAULT_ONTOLOGY_ROOT,
        max_batches=1)
    implied = backfill.run(object(), source=source, max_batches=1)

    assert explicit == implied == {"source": source, "selected": "v2"}
    assert len(calls) == 2
    # ⚠️ The retired cursor arguments are no longer forwarded -- `run()` refuses them
    # before it reaches the body -- so what this case pins is the SETUP both calls got.
    assert calls[0][1].config_root == calls[1][1].config_root


def test_v2_backfill_refuses_reset_controls_before_store_access():
    import ledger.backfill as backfill

    with pytest.raises(LedgerSetupError) as exc:
        backfill.run(
            object(), source=_a_planned_source(), ontology_root=DEFAULT_ONTOLOGY_ROOT,
            reset_cursor=True)

    # 🔴 THE PROPERTY IS "BEFORE STORE ACCESS", AND THAT IS WHY IT SURVIVED 판정 171.
    # `reset_cursor` used to demand a destructive approval; there is no cursor to reset now,
    # so the refusal names the argument as retired instead. What must not change is WHEN it
    # fires -- the engine here is a bare `object()`, so any refusal that reached the database
    # first would raise AttributeError rather than refuse.
    refusal = exc.value.to_mapping()
    assert refusal["code"] == "retired_cursor_argument"
    assert refusal["path"] == "run().reset_cursor"
    assert "rescope" in refusal["message"], refusal


class _SatisfiedEngine:
    """An engine whose catalogue says every object already exists.

    🔴 IT EXISTS BECAUSE `object()` STOPPED BEING AN ENGINE (S-88). The CLI now ensures the
    ledger schema before dispatching, and a stub that raises `AttributeError` on
    `raw_connection` would fail this test for a reason that has nothing to do with what it
    asserts — which is that the parser refuses retired flags.
    """

    class _Cursor:
        def execute(self, statement, params=None):
            self.statement = statement

        def fetchone(self):
            return (1,)          # `_relation_exists` / `constraint_exists`: 「already there」

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _Connection:
        def cursor(self):
            return _SatisfiedEngine._Cursor()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    def raw_connection(self):
        return self._Connection()


def test_operator_cli_has_no_legacy_escape_hatch(monkeypatch):
    """The retired flags are UNKNOWN to the parser, not merely discouraged.

    Asserting the refusal rather than the absence: a flag that is quietly ignored still
    lets an operator believe the run they asked for is the run they got.
    """
    import database.database as database_module
    import ledger.backfill as backfill

    calls = []
    # ⚠️ THE STUB HAS TO BE AN ENGINE NOW, not `object()`. Since S-88 the CLI ensures the
    # ledger schema before it dispatches, so a fake that answers nothing was only ever
    # sufficient because nothing touched it. This one answers the catalogue with 「already
    # there」, which is the state a running install is in.
    monkeypatch.setattr(database_module, "engine", _SatisfiedEngine())
    monkeypatch.setattr(backfill, "beat", lambda result: None)
    # The write goes through the admin runs' door now (80d61ae05); this test scores what
    # the CLI forwards and prints, so the door runs the adapter without a record.
    from admin import retroactive
    from tests.support.retro_door import run_without_a_record
    monkeypatch.setattr(retroactive, "run_here", run_without_a_record(database_module.engine))
    monkeypatch.setattr(
        backfill, "run", lambda engine, **kwargs: calls.append(kwargs) or {})

    assert backfill.main(["--max-batches", "0"]) == 0
    # the world is named, never a root (총괄 3b6dacd2f retired the root) - and named always,
    # the one that speaks for the source (총괄 8b81e79a0 · 6c266e56b ⑤)
    assert calls[-1]["world"] == "default" and "ontology_root" not in calls[-1]
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
    # Brought to this generation the way the loader reads an older one (`upgrade_setup`),
    # not by stamping the number: a v5 file stamped 6 still carries `prepare` everywhere.
    (draft / "ledger_config.json").write_text(
        json.dumps(upgrade_setup(json.loads(
            (draft / "ledger_config.json").read_text("utf-8"))), ensure_ascii=False),
        encoding="utf-8")
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
    from declaration_names import fold_versions

    # the names the refusals print are bare (4eb1fe98f)
    raw = fold_versions(json.loads((SAMPLE_ROOT / "ledger_config.json").read_text(encoding="utf-8")))
    predicate = sorted(raw["vocabulary"])[0]
    entity_type = sorted(raw["entities"])[0]
    source = sorted(raw["sources"])[0]
    sentence = sorted(raw["sources"][source]["bind"]["mappings"])[0]
    raw["sources"][source]["map"]["emits"] = "one/claim"
    # was `packs.<p>.claims.<c>.emit.object.payload = {"n": 1}` until the section went on
    # 2026-08-21. What this leg is for is a FIFTH independent check firing in the same
    # read, so it moved to the deepest record a config still nests.
    raw["sources"][source]["bind"]["mappings"][sentence]["colour"] = "blue"
    raw["vocabulary"][predicate]["colour"] = "blue"
    raw["entities"][entity_type]["allow_null"] = "yes"
    raw["sources"][source]["read"]["unit"] = "wafer"
    (root / "ledger_config.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    assert setup_main(["--root", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "", "a refused verification must not print a report"
    lines = [line for line in captured.err.splitlines() if line.strip()]
    # All five, from ONE run. Named individually so a regression that drops one kind of
    # check cannot hide behind a count.
    for expected in (
        f"bundle.sources.{source}.map.emits",
        f"bundle.sources.{source}.bind.mappings.{sentence}.colour",
        f"bundle.vocabulary.{predicate}.colour",
        f"bundle.entities.{entity_type}.allow_null",
        f"bundle.sources.{source}.read.unit",
    ):
        assert any(expected in line for line in lines), expected
    assert lines[-1].endswith(f"{len(lines) - 1} problem(s) in {root}")

    # ⚰️ THE RUNTIME LOADER NO LONGER STOPS THE BUNDLE ON ONE DECLARATION (S-177 ②,
    # 판정 280). It used to raise the FIRST of the list above, and that is precisely the
    # all-or-nothing this round removed: in production one typo stood fourteen ledgers up.
    # It now drops what is blamed and loads the rest.
    #
    # This sample declares ONE source, so dropping it leaves nothing to read -- and a
    # bundle that would compile to zero plans is refused BY NAME rather than loaded as a
    # silently empty ledger, carrying each refused source's own reason. The two paths
    # still differ in HOW MANY and never in WHAT: the reason names a path from the list.
    with pytest.raises(LedgerSetupError) as refused:
        setup_module.load_setup(root)
    assert refused.value.code == "every_source_refused"
    assert source in refused.value.message
    assert any(fragment in refused.value.message
               for fragment in (f"bundle.sources.{source}", f"bundle.entities.",
                                f"bundle.vocabulary.")), refused.value.message
