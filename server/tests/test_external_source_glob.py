"""`external_sources[].options.glob` - which files under the root are the source's (총괄 10-11).

The seat is `IngestionHandler.external_source_context`; watch events and the sweep ask it.
"""
import json
import os

import pytest
from watchdog.events import FileCreatedEvent

from database import models
from directory_watcher import (
    ExternalSourceEventHandler,
    IngestionHandler,
    WorkspaceWatcher,
    _folder_may_hold,
    validate_external_source_specs,
)
from tests.test_a_failed_external_file_retries_on_its_own_handler import env  # noqa: F401
from tests.test_external_source_watcher import TABLES, _make_workspace_with_plugin

#: The filesystem's case rule, asked as the seat asks it.
CASE_FOLDS = os.path.normcase("A") == "a"


def _handler(tmp_path, options, parser="voids_json"):
    external = tmp_path / "external"
    external.mkdir(exist_ok=True)
    workspace = tmp_path / "ingestion_workspace" / "void_obs"
    (workspace / "archives").mkdir(parents=True, exist_ok=True)
    specs, errors = validate_external_source_specs({"external_sources": [{
        "path": str(external), "table_name": "void_obs", "parser": parser,
        "options": options}]}, TABLES, str(tmp_path / "ingestion_workspace"))
    assert errors == []
    handler = IngestionHandler(
        str(workspace), None, str(workspace / "archives"), default_table_name="void_obs")
    handler.register_external_source(specs[0])
    return handler, specs[0], external


TAKES = [
    ("*.png", "d1/d2/a.png", True), ("*.png", "d1/d2/a.txt", False), ("*.png", "a.png", True),
    ("sub/*.png", "sub/a.png", True), ("sub/*.png", "other/a.png", False),
    ("sub/*.png", "sub/c/a.png", False), ("sub/*.png", "x/sub/a.png", False),
    (["*.png", "*.txt"], "a/b.txt", True), (["*.png", "*.txt"], "a/b.png", True),
    (["*.png", "*.txt"], "a/b.csv", False),
    ("*/raw/**/*.jpg", "A/raw/x.jpg", True), ("*/raw/**/*.jpg", "A/raw/x/y/z.jpg", True),
    ("*/raw/**/*.jpg", "A/b/raw/x.jpg", False), ("*/raw/**/*.jpg", "A/raw/x.png", False),
    ("raw/**/*.jpg", "raw/x.jpg", True), ("raw/**/*.jpg", "raw/a/b/x.jpg", True),
    ("raw/**/*.jpg", "A/raw/x.jpg", False),
    ("**/*.jpg", "x.jpg", True), ("**/*.jpg", "a/b/x.jpg", True), ("**/*.jpg", "a/b/x.png", False),
    ("**/raw/**/*.jpg", "raw/x.jpg", True), ("**/raw/**/*.jpg", "A/raw/x.jpg", True),
    ("**/raw/**/*.jpg", "A/B/raw/y/z.jpg", True), ("**/raw/**/*.jpg", "A/rawdata/x.jpg", False),
    ("**/raw/**/*.jpg", "A/raw/x.png", False),
    ("*.PNG", "d/a.png", CASE_FOLDS),
]


@pytest.mark.parametrize("glob,rel,taken", TAKES)
def test_the_seat_takes_a_file_only_when_its_path_from_the_root_matches(
        tmp_path, glob, rel, taken):
    handler, _spec, external = _handler(tmp_path, {"glob": glob})
    context = handler.external_source_context(str(external / rel))
    assert (context is not None) is taken
    if taken:
        assert context["rel_path"] == rel


def _listed(glob):
    return [glob] if isinstance(glob, str) else glob      # as the registration keeps it


@pytest.mark.parametrize("glob,rel,taken", TAKES)
def test_the_sweep_enters_every_folder_a_taken_file_is_in(glob, rel, taken):
    """The sweep's folder prune reads the pattern as the seat does: a file the seat takes is never below a folder the
    walk leaves out."""
    folders = rel.split("/")[:-1]
    if taken:
        assert all(_folder_may_hold({"glob": _listed(glob)}, "/".join(folders[:n])) for n in range(1, len(folders) + 1))


@pytest.mark.parametrize("glob,folder,enters", [
    ("*.png", "x/y", True), ("sub/*.png", "sub", True), ("sub/*.png", "other", False), ("sub/*.png", "sub/c", False),
    ("*/raw/**/*.jpg", "A", True), ("*/raw/**/*.jpg", "A/b", False), ("*/raw/**/*.jpg", "A/raw/x/y", True),
    ("raw/**/*.jpg", "A", False), ("**/raw/**/*.jpg", "A/B/C", True), ("LOT*/W*/STEP_02/v.csv", "LOT1/W2/STEP_01", False),
    ("LOT*/W*/STEP_02/v.csv", "LOT1/W2/STEP_02", True), ("LOT*/W*/STEP_02/v.csv", "X1", False),
    (["sub/*.png", "other/*.png"], "other", True),
])
def test_the_sweep_leaves_out_the_folders_no_taken_file_can_be_in(glob, folder, enters):
    assert _folder_may_hold({"glob": _listed(glob)}, folder) is enters
    assert _folder_may_hold({"filename": "voids.json"}, folder) is True


def test_no_glob_is_today_the_one_filename(tmp_path):
    handler, _spec, external = _handler(tmp_path, {})
    assert handler.external_source_context(str(external / "WF" / "W" / "voids.json")) is not None
    assert handler.external_source_context(str(external / "WF" / "W" / "a.png")) is None


def test_a_watch_event_asks_the_same_seat(tmp_path, monkeypatch):
    handler, spec, external = _handler(tmp_path, {"glob": "sub/*.png"})
    taken, other = external / "sub" / "a.png", external / "other" / "a.png"
    for path in (taken, other):
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x")
    calls = []
    monkeypatch.setattr(handler, "_handle_event", calls.append)
    adapter = ExternalSourceEventHandler(handler, spec)
    adapter.dispatch(FileCreatedEvent(str(other)))
    adapter.dispatch(FileCreatedEvent(str(taken)))
    assert calls == [str(taken)]


@pytest.mark.parametrize("bad", [5, {"a": 1}, "", "  ", [], ["*.png", ""], ["*.png", 3]])
def test_a_glob_of_the_wrong_shape_is_refused_by_name(tmp_path, bad):
    specs, errors = validate_external_source_specs({"external_sources": [{
        "path": str(tmp_path / "external"), "table_name": "void_obs", "parser": "voids_json",
        "options": {"glob": bad}}]}, TABLES, str(tmp_path / "ingestion_workspace"))
    assert specs == []
    assert errors == ["external_sources[0].options.glob must be one glob string or a list of "
                      f"them, none empty, got {bad!r}."]


def test_a_file_the_glob_does_not_take_gets_no_ingestion_log_row(env, tmp_path):  # noqa: F811
    _make_workspace_with_plugin(env["workspace"], suffix=".png")
    for rel in ("sub/a.png", "other/b.png"):          # the plugin takes both by name
        path = env["external"] / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    (tmp_path / "ingestion_settings.json").write_text(json.dumps({"external_sources": [{
        "path": str(env["external"]), "table_name": "void_obs",
        "options": {"glob": "sub/*.png"}}]}), encoding="utf-8")
    watcher = WorkspaceWatcher(str(env["workspace"]))
    watcher.discover_and_watch()

    assert watcher.sweep_external_sources() == 1

    db = env["Session"]()
    try:
        logged = {log.filename for log in db.query(models.FileIngestionLog).all()}
    finally:
        db.close()
    assert logged == {"a.png"}
