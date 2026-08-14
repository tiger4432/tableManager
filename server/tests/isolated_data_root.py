"""Point ONE test file's data root at a temp directory, so it cannot read the operator's.

WHY THIS EXISTS (R-2026-08-14-A F4)
`paths.py` is the single override point for the user-owned trees on disk - `config/` and
`ingestion_workspace/` - and `ASSY_DATA_ROOT` moves them. Unset, they resolve to the
operator's LIVE `server/config/`, which is gitignored and therefore says whatever this box
says. `ingestion_settings.json` on this box carries `archive_processed_files: false`, and
six tests that assert a processed file is archived went red because of it. Two lanes in a
row then spent a round proving the red was not theirs; the ruling is that the cost of that
has passed the cost of isolating.

WHAT THIS IS NOT
It is not a global conftest change. A test file OPTS IN with an autouse fixture of its own,
so no other lane's file changes behaviour, and a file that opts in is isolated even when
someone runs it on its own - which is the difference between this and exporting
`ASSY_DATA_ROOT` in a shell before running pytest.

The nearest existing shape is `conftest._heartbeats_never_touch_the_live_tree`, which was
added after these SAME two test files wrote a live `server/config/worker_heartbeats/`
entry. Same class of leak, in the other direction: that one wrote to the operator's tree,
this one reads from it.

WHY THE ENV VAR ALONE IS NOT ENOUGH
`paths.DATA_ROOT` and everything derived from it are computed at IMPORT time, and several
modules freeze their own copy (`INGESTION_SETTINGS_PATH = paths.config_path(...)`). By the
time a fixture runs, those constants already point at the operator's tree. So the env var
is set for anything imported later, `paths`' own module attributes are re-pointed, and
every module that already froze a settings path is re-pointed too. That last sweep reads
`sys.modules` rather than a hand-written list of module names: the list would go stale the
day someone adds the seventh copy, and a stale list here fails SILENTLY - the test simply
starts reading the operator's file again.
"""
import os
import sys

#: The frozen per-module constants this sweep re-points. Add a name here only if it is a
#: path INTO the data root that modules capture at import time.
_FROZEN_PATH_ATTRS = ("INGESTION_SETTINGS_PATH",)


def isolate_data_root(monkeypatch, tmp_path):
    """Redirect the data root to `tmp_path`. Returns the isolated config directory.

    The config directory is created EMPTY. An absent config file is how every reader in
    `server/` spells "use the defaults" (`load_ingestion_settings` returns `{}`), so a test
    that says nothing gets documented defaults rather than this box's opinions. A test that
    wants a specific setting writes the file into the returned directory, which is what
    `test_ingestion_ledger_tier1.py` already does with its own temp path.
    """
    root = tmp_path / "isolated_data_root"
    config_dir = root / "config"
    workspace_dir = root / "ingestion_workspace"
    for d in (config_dir, workspace_dir):
        d.mkdir(parents=True, exist_ok=True)

    # For anything imported AFTER this point, and for any subprocess.
    monkeypatch.setenv("ASSY_DATA_ROOT", str(root))

    import paths
    monkeypatch.setattr(paths, "DATA_ROOT", str(root))
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(paths, "WORKSPACE_DIR", str(workspace_dir))
    monkeypatch.setattr(paths, "IS_ISOLATED", True)

    # For everything already imported, which is where the operator's file was actually
    # reaching these tests from.
    settings = str(config_dir / "ingestion_settings.json")
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        for attr in _FROZEN_PATH_ATTRS:
            try:
                if hasattr(mod, attr):
                    monkeypatch.setattr(mod, attr, settings)
            except Exception:       # noqa: BLE001 - a module that cannot be patched is
                continue            # not one this suite reads config through
    return config_dir


def assert_isolated(config_dir):
    """The guard the pinning test calls. Raises rather than returns a bool on purpose.

    What it checks is the thing that actually broke: the path `directory_watcher` will
    open is inside `config_dir` and NOT inside the operator's `server/config/`. Comparing
    against `paths.SERVER_DIR` rather than against a hard-coded path keeps this true on a
    checkout that lives somewhere else.
    """
    import paths
    import directory_watcher

    frozen = os.path.abspath(directory_watcher.INGESTION_SETTINGS_PATH)
    operator = os.path.abspath(os.path.join(paths.SERVER_DIR, "config"))
    assert frozen.startswith(os.path.abspath(str(config_dir))), (
        "the settings path is not inside the isolated root: %s" % frozen)
    assert not os.path.normcase(frozen).startswith(os.path.normcase(operator) + os.sep), (
        "the settings path still points into the operator's live config tree: %s" % frozen)
    assert directory_watcher.load_ingestion_settings() == {}, (
        "the isolated root must hold no settings file, so every knob reads its default")
