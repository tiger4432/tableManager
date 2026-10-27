"""`imports` (lead 10-27 B-4, owner «키를 한 곳에서»): a world uses another world's entity types as that world writes
them, so a type's nodes are one across worlds. `setup_bundle.resolve_imports` is the one resolver; `imported` is
passed like `catalog` from the seats that build it (`ledger.setup.live_imported`). Every seat a declaration is
judged or read through is a row here, walked with a declaration that imports (the table in RUN.md 10-27).

Run: pytest server/tests/test_a_world_imports_entity_types_from_another.py -q
"""
import copy
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from support.isolated_pg import RUN_TOKEN                          # noqa: E402
import paths                                                        # noqa: E402
from database import config_watcher                                 # noqa: E402
from ledger import config as ledger_config                          # noqa: E402
from ledger import schema, setup, setup_bundle, trace_router        # noqa: E402

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
TOKEN = "".join(ch for ch in RUN_TOKEN.lower() if ch.isalnum())[:16]
A, B, C = "a" + TOKEN, "b" + TOKEN, "c" + TOKEN
CHANGED = "wafer_process_recipe"


def _sample():
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        return json.load(fh)


def _with(imports=None, **entities):
    """The sample, with these entity types added and these imports."""
    document = _sample()
    document["entities"].update(entities)
    if imports is not None:
        document["imports"] = imports
    return document


def _declare(world, document):
    root = Path(paths.config_path("ontology_worlds", world))
    root.mkdir(parents=True, exist_ok=True)
    (root / "ledger_config.json").write_text(json.dumps(document), encoding="utf-8")
    config_watcher.changed(str(root / "ledger_config.json"))


def _root(world):
    return schema.world_names(world).declaration_root


@pytest.fixture(name="config")
def fixture_config(tmp_path, monkeypatch):
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    shutil.copy(os.path.join(SAMPLE, "table_config.json.sample"), config / "table_config.json")
    shutil.copy(os.path.join(SAMPLE, "ledger_config.json.sample"), config / "ontology" / "ledger_config.json")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))
    config_watcher.forget_held()
    # A imports tool from B; B declares it with two keys
    _declare(B, _with(**{"tool@1": {"keys": ["tool", "site"]}}))
    _declare(A, _with({B: ["tool"]}))
    yield config
    config_watcher.forget_held()


def _tool_keys(entities):
    (name,) = [name for name in entities if name.split("@")[0] == "tool"]
    return list(entities[name]["keys"])


def _codes(issues):
    return sorted({issue.code for issue in issues})


# ------------------------------------------------------------------ the resolver

def test_an_imported_type_is_the_other_worlds_and_a_local_spelling_gives_way_with_a_notice(config):
    imported = setup.live_imported()
    resolved, notices, refused = setup_bundle.resolve_imports(_with({B: ["tool"]}), imported)
    assert (_tool_keys(resolved["entities"]), notices, refused) == (["tool", "site"], (), ())
    assert resolved["imports"] == {B: ["tool"]}, "the section stays as written"

    local = _with({B: ["tool"]}, **{"tool@1": {"keys": ["tool"]}})
    resolved, notices, refused = setup_bundle.resolve_imports(local, imported)
    assert _tool_keys(resolved["entities"]) == ["tool", "site"] and not refused
    assert notices == ("tool is %s's - this world writes it differently, and that is not used" % B,)


def test_an_import_of_an_import_is_followed_to_the_world_that_declares_it(config):
    _declare(C, _with(**{"tool@1": {"keys": ["tool", "line"]}}))
    _declare(B, _with({C: ["tool"]}, **{"tool@1": {"keys": ["tool", "site"]}}))
    resolved, notices, refused = setup_bundle.resolve_imports(_with({B: ["tool"]}), setup.live_imported())
    assert (_tool_keys(resolved["entities"]), refused) == (["tool", "line"], ())


def test_a_cycle_an_unknown_world_an_undeclared_type_and_no_imported_are_refused_by_name(config):
    _declare(B, _with({A: ["tool"]}))
    (cycle,) = setup_bundle.resolve_imports(_with({B: ["tool"]}), setup.live_imported())[2]
    assert cycle.code == "imports_cycle" and "%s -> %s -> %s" % (B, A, B) in cycle.message

    (unknown,) = setup_bundle.resolve_imports(_with({"nowhere": ["tool"]}), setup.live_imported())[2]
    assert unknown.code == "imports_world_unknown" and "'nowhere'" in unknown.message

    (undeclared,) = setup_bundle.resolve_imports(_with({C: ["tool"]}), {C: {"entities": {"lot@1": {}}}})[2]
    assert undeclared.code == "imports_type_unknown" and "it declares: lot" in undeclared.message

    (unread,) = setup_bundle.resolve_imports(_with({B: ["tool"]}), None)[2]
    assert unread.code == "imports_unresolved" and "imported=ledger.setup.live_imported()" in unread.message
    (shape,) = setup_bundle.resolve_imports(_with({B: "tool"}), {})[2]
    assert (shape.code, shape.path) == ("invalid_type", "bundle.imports")


def test_without_imported_a_resolved_bundle_passes_and_a_raw_one_is_refused(config):
    resolved = setup_bundle.resolve_imports(_with({B: ["tool"]}), setup.live_imported())[0]
    catalog = dict(setup.live_physical_catalog())
    assert setup_bundle.validate_bundle_errors(resolved, catalog=catalog) == ()
    assert _codes(setup_bundle.validate_bundle_errors(_with({B: ["tool"]}), catalog=catalog)) == [
        "imports_unresolved"]


# ------------------------------------------------------------------ every seat, with a declaration that imports

def test_config_load_reads_the_imported_type_and_says_a_local_spelling(config):
    loaded = ledger_config.load(schema.world_names(A).declaration_path)
    assert _tool_keys(loaded["entities"]) == ["tool", "site"] and "__notices__" not in loaded
    _declare(A, _with({B: ["tool"]}, **{"tool@1": {"keys": ["tool"]}}))
    loaded = ledger_config.load(schema.world_names(A).declaration_path)
    assert loaded["__notices__"] == ["tool is %s's - this world writes it differently, and that is not used" % B]


def test_config_load_with_one_broken_source_still_reads_the_imported_type(config):
    document = _with({B: ["tool"]})
    document["sources"][CHANGED]["relation"] = "no_such_relation"
    _declare(A, document)
    loaded = ledger_config.load(schema.world_names(A).declaration_path)
    assert CHANGED not in loaded["sources"] and _tool_keys(loaded["entities"]) == ["tool", "site"]


def test_the_world_list_says_what_an_import_overrides(config):
    from ledger_api import ontology_config_explorer_router as explorer_router

    _declare(A, _with({B: ["tool"]}, **{"tool@1": {"keys": ["tool"]}}))
    notices = explorer_router.list_worlds()["notices"]
    assert notices == ["%s: tool is %s's - this world writes it differently, and that is not used" % (A, B)]


def test_the_walk_declaration_answers_the_other_worlds_keys_and_follows_a_change_to_it_alone(config):
    def keys():
        (tool,) = [item for item in trace_router.ledger_declaration_catalog(world=[A])["entities"]
                   if item["type"] == "tool"]
        return tool["keys"]

    assert keys() == ["tool", "site"]
    _declare(B, _with(**{"tool@1": {"keys": ["tool", "site", "bay"]}}))          # B's file only
    assert keys() == ["tool", "site", "bay"]


def test_the_compiled_setup_holds_the_imported_type_and_follows_a_change_to_it_alone(config):
    from ledger import worker

    def keys():
        return _tool_keys(worker._compiled_setup(A).bundle.section("entities"))

    assert keys() == ["tool", "site"]
    _declare(B, _with(**{"tool@1": {"keys": ["tool", "site", "bay"]}}))
    assert keys() == ["tool", "site", "bay"]


def test_load_setup_with_one_broken_source_isolates_it_and_keeps_the_imported_type(config):
    document = _with({B: ["tool"]})
    document["sources"][CHANGED]["relation"] = "no_such_relation"
    _declare(A, document)
    loaded = setup.load_setup(_root(A))
    assert CHANGED in loaded.left_out or CHANGED not in loaded.bundle.section("sources")
    assert _tool_keys(loaded.bundle.section("entities")) == ["tool", "site"]


def test_a_setup_from_a_document_in_hand_reads_the_imported_type(config):
    built = setup.setup_from_document(_with({B: ["tool"]}), config_root=_root(A))
    assert _tool_keys(built.bundle.section("entities")) == ["tool", "site"]


def test_the_authoring_issues_of_a_root_that_imports_are_not_an_unread_import(config):
    fallback = setup_bundle.LedgerSetupValidationError("fallback", "here", "the loader's own")
    assert setup._authoring_issues(Path(_root(A)), fallback) == (fallback,)


def _service(world, tmp_path):
    from ledger.config_explorer_service import OntologyExplorerService

    return OntologyExplorerService(config_root=_root(world), draft_root=tmp_path / ("drafts-" + world),
                                   world=world)


def test_the_screen_shows_the_imported_type_and_refuses_only_the_broken_source(config, tmp_path):
    document = _with({B: ["tool"]})
    document["sources"][CHANGED]["relation"] = "no_such_relation"
    _declare(A, document)
    service = _service(A, tmp_path)
    _setup, index, _ = service.active()
    assert _tool_keys(_setup.bundle.section("entities")) == ["tool", "site"]
    assert not service._config_level, service._config_level


def test_a_screen_whose_every_source_is_refused_still_reads_the_imported_type(config, tmp_path, monkeypatch):
    from ledger import config_explorer_service

    document = _with({B: ["tool"]})
    document["sources"] = {CHANGED: dict(document["sources"][CHANGED], relation="no_such_relation")}
    _declare(A, document)
    service, asked = _service(A, tmp_path), []
    real = config_explorer_service.load_resolved_setup
    monkeypatch.setattr(config_explorer_service, "load_resolved_setup",
                        lambda *a, **k: asked.append(1) or real(*a, **k))
    resolution = service._resolution()
    assert asked, "the loader refused, so the screen resolved what it could"
    assert not resolution["config_level"], resolution["config_level"]
    assert _tool_keys(service.active()[0].bundle.section("entities")) == ["tool", "site"]


def test_a_deletion_preview_of_a_world_that_imports_names_the_source_that_would_fall(config, tmp_path):
    service = _service(A, tmp_path)
    service.active()
    answer = service.deletion_preview(targets=["predicate|processed_with"])
    assert CHANGED in [item["canonical_id"] for item in answer["unread_after"]], answer["unread_after"]


def test_a_world_copied_from_one_that_imports_starts(config, tmp_path):
    service = _service(C, tmp_path)
    answer = service.bootstrap_config(seed_root=_root(A))
    assert json.loads(Path(answer["created"]).read_text(encoding="utf-8"))["imports"] == {B: ["tool"]}


def test_the_authoring_plan_of_a_world_that_imports_carries_no_unread_import(config, tmp_path):
    plan = _service(A, tmp_path).authoring()
    assert not [item for item in plan["refusals"] if item["code"].startswith("imports")], plan["refusals"]

    # and what may leave the file is measured as for the same file without the import (`_dispositions`)
    _declare(C, _sample())
    def leaving(world):
        return {row["path"]: row["disposition"] for row in _service(world, tmp_path).authoring()["fields"]
                if row.get("disposition") == "remove_from_file"}
    assert leaving(A) == leaving(C) and leaving(C), leaving(C)


def test_a_draft_of_a_world_that_imports_previews_valid_and_its_activation_keeps_the_imports(config, tmp_path):
    service = _service(A, tmp_path)
    _setup, index, _ = service.active()
    key = next(key for key in index.nodes if key.startswith("predicate|"))
    draft = service.create_draft(target_key=key, base_snapshot_hash=index.snapshot_hash)
    saved = service.save_draft(draft["draft_id"], expected_revision=draft["revision"],
                               raw=json.dumps(index.nodes[key].raw))
    assert saved["context_token"].startswith("draft:"), saved            # the preview compiled
    reviewed = service.review_draft(draft["draft_id"], expected_revision=saved["revision"])
    service.activate_draft(draft["draft_id"], expected_revision=reviewed["revision"], reload_callback=lambda: None)
    written = json.loads(Path(schema.world_names(A).declaration_path).read_text(encoding="utf-8"))
    assert written["imports"] == {B: ["tool"]} and "tool@1" not in written["entities"] and "tool" not in written[
        "entities"], "the file keeps what was written - the imported type is not copied in"


def test_the_declared_types_of_an_operating_world_that_imports_carry_its_keys_and_follow_a_change(config):
    from ledger_api import declared_entities

    schema.operate(A)
    assert declared_entities.identity_keys("tool") == ["tool", "site"]
    _declare(B, _with(**{"tool@1": {"keys": ["tool", "site", "bay"]}}))
    assert declared_entities.identity_keys("tool") == ["tool", "site", "bay"]


def test_the_walks_key_order_for_an_imported_type_is_the_other_worlds_and_follows_a_change(config):
    from ledger_api import ledger_subgraph

    token = ledger_subgraph._WALK_DECLARATION.set((schema.world_names(A).declaration_path,))
    try:
        assert ledger_subgraph._declared_key_order("tool") == ["tool", "site"]
        _declare(B, _with(**{"tool@1": {"keys": ["tool", "site", "bay"]}}))
        assert ledger_subgraph._declared_key_order("tool") == ["tool", "site", "bay"]
    finally:
        ledger_subgraph._WALK_DECLARATION.reset(token)


def test_a_script_that_validates_a_file_by_hand_refuses_an_import_it_did_not_read(config):
    """`scripts/migrate_ledger_slim_sources.py` passes no `imported`: a declaration that imports is refused by name
    there rather than judged without the types it names."""
    issues = setup_bundle.validate_bundle_errors(_with({B: ["tool"]}), catalog=dict(setup.live_physical_catalog()))
    assert _codes(issues) == ["imports_unresolved"]


def test_the_restamp_scripts_tolerant_read_names_no_imported_and_still_drops_only_the_broken_source(config):
    """`scripts/ledger_restamp_cursor.py` calls `load_resolved_setup` as it always did - no `imported` - and the
    seat builds it, as `load_setup` does."""
    from ledger.config_explorer import load_resolved_setup

    document = _with({B: ["tool"]})
    document["sources"] = {CHANGED: dict(document["sources"][CHANGED], relation="no_such_relation"),
                           "lot_slot_wafer": document["sources"]["lot_slot_wafer"]}
    _declare(A, document)
    root, catalog = _root(A), setup.live_physical_catalog()
    resolved = load_resolved_setup(
        root, catalog=catalog,
        setup_from_document=lambda doc, **more: setup.setup_from_document(
            doc, config_root=root, catalog=catalog, **more))
    assert ([key.partition("|")[2] for key in resolved["invalid"]], resolved["config_level"]) == ([CHANGED], [])
    assert _tool_keys(resolved["setup"].bundle.section("entities")) == ["tool", "site"]
