# -*- coding: utf-8 -*-
"""S-211, 판정 360. One file decides where `server/` is, and its DEPTH is the contract.

🔴 THE FAILURE THIS EXISTS FOR IS SILENT AND ONLY HAPPENS IN PRODUCTION. `paths.SERVER_DIR`
is `dirname(__file__)`, and `DATA_ROOT` falls back to it when `ASSY_DATA_ROOT` is unset -
which IS the production layout. Move `paths.py` one directory down and config, the ingestion
workspace and the logs all resolve somewhere else. Nothing raises, every existing test stays
green, and only a real install reads the wrong directory.

🔴 SO THE ASSERTION IS ABOUT THE SPELLING, NOT ONLY THE VALUE. Checking that `SERVER_DIR`
ends in `server` would pass a second module that computed the same answer its own way - and
the whole point of `paths`'s own docstring (「~17 modules build these paths independently…
there is exactly one place that decides where data lives」) is that there be one author.

⚠️ THE HARMLESS ONES ARE EXCLUDED BY NAME, never by a pattern that might quietly widen: a
module asking its OWN mtime is still right wherever it lives, and the two `except ImportError`
fallbacks are bootstrapping `paths` itself - they cannot route through the module they are in
the act of finding.
"""
import ast
import io
import os
import subprocess
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import paths                                                      # noqa: E402

#: The modules whose DEPTH is about to change (S-211 packaging boundary). The gate's
#: population is exactly this set, and for a reason: `scripts/` and `migrations/` derive
#: `dirname(__file__)` all over, and they are RIGHT to - they are not moving, and each is its
#: own `__main__` bootstrap. Scoring them here would be ~150 findings about files this round
#: never touches, which is a gate that gets muted rather than obeyed.
MOVING = frozenset("""
chain_activity chain_bindings chain_builtins chain_graph chain_ingestion_worker
chain_key_gate chain_replay cell_layer legacy_join_declaration
legacy_materialized_join join_refusal join_key_index ledger_admin ledger_explorer ledger_trace ledger_trace_router
map_alignment map_meta_registrar map_overlay map_preset_routing alignment_batch_counts
alignment_view_service dt_frame_transform frame_confirmation enrichment_analysis
enrichment_backfill enrichment_candidates enrichment_config
ingestion_activity ingestion_checkpoint file_ingestion_status event_constants
system_reload process_supervisor runtime_loops health launcher_args admin_auth
dev_bench retroactive schema_drift audit_cache audit_history
""".split())

#: Seats inside MOVING that read `__file__` and are RIGHT anyway, each with its reason.
#: ⛔ Named one by one. A pattern would widen silently, which is how an allow-list becomes
#: a permission.
ALLOWED = {
    "chain/enrichment/candidates.py":
        "`except ImportError` fallback that is FINDING `paths` - it cannot route through "
        "the module it is in the act of importing",
    "ledger/trace.py":
        "the same bootstrap, the same reason",
}

#: 🔴 NOT IN `MOVING`, AND THAT IS THE POINT: `paths` defines where the server is and
#: `pacing` sits beside its own json, so their depth is part of the contract (판정 360).
ANCHORS = ("paths", "pacing")


def test_the_server_dir_is_the_server_directory():
    assert paths.SERVER_DIR == SERVER_DIR
    assert os.path.basename(paths.SERVER_DIR) == "server"
    assert os.path.isfile(os.path.join(paths.SERVER_DIR, "main.py")), (
        "SERVER_DIR does not point at the directory that holds the server")


def test_the_repo_root_is_one_above_it():
    assert paths.REPO_ROOT == os.path.dirname(paths.SERVER_DIR)
    assert os.path.isdir(os.path.join(paths.REPO_ROOT, ".git")), paths.REPO_ROOT


def test_the_data_root_falls_back_to_the_server_directory():
    """🔴 THE PRODUCTION PATH. With no `ASSY_DATA_ROOT`, data lives under `server/` - which is
    exactly the value a move would change without any error."""
    if os.environ.get("ASSY_DATA_ROOT"):
        pytest.skip("this box sets ASSY_DATA_ROOT; the fallback is what is being scored")
    assert paths.DATA_ROOT == paths.SERVER_DIR
    assert paths.CONFIG_DIR == os.path.join(paths.SERVER_DIR, "config")


def _module_path(name):
    """`server/<name>.py`, or wherever the packaging round put it."""
    flat = os.path.join(SERVER_DIR, name + ".py")
    if os.path.exists(flat):
        return flat
    # ⚠️ THE DIRECTORY AND THE NAME'S PREFIX ARE TWO FACTS, and they stopped being the same
    #    one when `enrichment/` became `chain/enrichment/` (소유자: 「모든 체인은 server/chain
    #    안에서만 코드 존재」). This read the prefix OFF the directory, so a nested package
    #    could not be found at all and three names in MOVING stopped resolving - which this
    #    gate refuses loudly, exactly as 판정 459 ㆜ asked it to.
    for package, prefix in (("chain", "chain"),
                            (os.path.join("chain", "enrichment"), "enrichment"),
                            ("virtual_join", "virtual_join"), ("ledger", "ledger"),
                            ("maps", "maps"), ("ingestion", "ingestion"),
                            ("runtime", "runtime"), ("admin", "admin")):
        for stem in (name, name[len(prefix) + 1:] if name.startswith(prefix + "_") else name,
                     name[4:] if prefix == "maps" and name.startswith("map_") else name):
            candidate = os.path.join(SERVER_DIR, package, stem + ".py")
            if os.path.exists(candidate):
                return candidate
    return flat


def _computing_sites():
    """Modules in `MOVING` that derive a directory from `__file__`, module level or inside a
    `def` - a computation tucked in a function body is exactly as wrong and harder to see."""
    found = []
    for name in sorted(MOVING):
        # 🪦 [S-211 packaging] these live in packages now. The gate follows them rather than
        # dropping them: a module that stopped being findable would silently stop being
        # scored, which is the shape of a gate that quietly goes quiet.
        #
        # ⚰️ AND THE NEXT LINE USED TO DO THAT VERY THING (판정 459 ㆜). `continue` on a
        # missing file is 「silently stop being scored」 written out - the comment above
        # forbade it and the code did it. Measured: 43 names, 42 resolved, ONE skipped in
        # silence. Nothing was missed today, but the population this gate declares was
        # false, and the next name that drifts is the one it does miss.
        path = _module_path(name)
        assert os.path.exists(path), (
            "%r is in MOVING but no file answers to it (%s). A name that stops resolving "
            "must fail this gate rather than leave it scoring a smaller population than it "
            "claims - fix the name or take it out of MOVING." % (name, path))
        tree = ast.parse(io.open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "dirname"):
                continue
            if any(isinstance(sub, ast.Name) and sub.id == "__file__"
                   for sub in ast.walk(node)):
                found.append((os.path.relpath(path, SERVER_DIR).replace(os.sep, "/"),
                              node.lineno))
    return found


def test_only_the_named_seats_compute_the_server_directory():
    """⛔ THE GATE THE RULING NAMED. Walks module level AND function bodies, because a
    computation tucked inside a `def` is exactly as wrong and harder to see."""
    stray = sorted({(f, line) for f, line in _computing_sites() if f not in ALLOWED})

    assert not stray, (
        "these derive a directory from __file__ instead of reading `paths`: %s" % stray)


def test_the_allow_list_is_not_stale():
    """⚠️ AN ALLOW-LIST THAT OUTLIVES ITS ENTRIES ROTS INTO PERMISSION. Every name on it must
    still be a real seat, or it is quietly widening what the gate above tolerates."""
    present = {f for f, _ in _computing_sites()}

    for name in sorted(ALLOWED):
        assert name in present, "%s is on the allow-list and no longer computes anything" % name


@pytest.mark.parametrize("anchor", ANCHORS)
def test_an_anchor_is_not_scheduled_to_move(anchor):
    """🔴 판정 360. `paths` and `pacing` stay at the top of `server/` because their depth is
    read, not incidental - `paths` IS the definition of where data lives, and `pacing` opens
    the json beside it. This is the assertion the packaging commit has to keep green."""
    assert anchor not in MOVING
    assert os.path.isfile(os.path.join(SERVER_DIR, anchor + ".py"))
