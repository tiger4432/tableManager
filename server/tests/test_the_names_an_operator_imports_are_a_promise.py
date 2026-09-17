# -*- coding: utf-8 -*-
"""S-211 ②. Some module names are a promise to people whose files this repo cannot see.

🔴 THE QUESTION CANNOT BE MEASURED, SO IT IS PROMISED. Workspace parser scripts live under
`server/ingestion_workspace/*/scripts/` and are gitignored - the operator's own files. This
repo never edits them and cannot count what they import, so 「which modules break if we move
them」 has no measurable answer. `OPERATOR_IMPORT_NAMES` is the answer it has instead, and
these cases keep the promise honest from both sides.

🔴 THE PROMISE IS ALREADY IN THE PRODUCT, which is why the list sits beside it:
`_register_legacy_import_shim` aliases old `server.*` spellings onto the same module objects
precisely so operator scripts need no edits - its docstring says 「사용자 스크립트는 무수정
원칙」.

⚠️ THE HARD DIRECTION IS THE SECOND ONE. Pinning that today's names import is easy and would
stay green while a shim quietly grew a THIRD import that nobody promised. So the shims are
parsed and their imports must be a SUBSET of the promise - a new one fails here until it is
either promised or removed.
"""
import ast
import importlib
import io
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from parsers.directory_watcher import OPERATOR_IMPORT_NAMES        # noqa: E402

#: The files whose own headers say 「HAND-COPY THIS FILE to …ingestion_workspace/…」. They are
#: the only operator-side imports this repo can actually read, which makes them the lower
#: bound on the promise - never the whole of it.
#:
#: 🔴 [2026-09-17] THE MAPPER SAMPLES WERE MISSING AND THAT COST A RED MAIN. This tuple held
#: the two PARSER samples only, so seven mapper samples importing `chain_bindings` and one
#: importing `session_contract` were shipped to operators and scored by nothing. A census
#: that read `*.py` then moved `session_contract` into `chain/` and every hand-copied mapper
#: broke - measured, `ModuleNotFoundError: No module named 'session_contract'`.
#: ⚠️ AND THE ONE THAT BIT IS INSIDE A FUNCTION (`cross_table_lookup_mapper.py.sample:318`),
#: which a line-anchored grep does not see. `_imported_names` walks the AST, so it does.
HAND_COPIED = (
    os.path.join("parsers", "void_obs_parser.py.sample"),
    os.path.join("parsers", "inspection_run_parser.py.sample"),
    os.path.join("mappers", "core_alignment_mapper.py.sample"),
    os.path.join("mappers", "core_usage_mapper.py.sample"),
    os.path.join("mappers", "cross_table_lookup_mapper.py.sample"),
    os.path.join("mappers", "dt_alignment_metadata_mapper.py.sample"),
    os.path.join("mappers", "dt_inventory_metadata_mapper.py.sample"),
    os.path.join("mappers", "dt_job_rollup_mapper.py.sample"),
    os.path.join("mappers", "dt_map_mapper.py.sample"),
)


def _homes_of(module):
    """Directories a module lives in - `__file__` for a plain module, `__path__` for a
    namespace package, which has no `__file__` at all."""
    path = getattr(module, "__file__", None)
    if path:
        return {os.path.dirname(os.path.abspath(path))}
    return {os.path.abspath(p) for p in getattr(module, "__path__", [])}


def _imported_names(relative):
    """Top-level module names a `.sample` imports. It is DATA here, not a module: the
    extension makes it unimportable, and what is being asked is 「which names does this file
    name」 - the text IS the subject."""
    path = os.path.join(SERVER_DIR, relative)
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            found.add(node.module.split(".")[0])
    return found


# ---------------------------------------------------------------------------
# 🔴 every promised name resolves, at the top level
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", OPERATOR_IMPORT_NAMES)
def test_a_promised_name_imports_at_the_top_level(name):
    """🔴 THE PROMISE IS THE BARE NAME. `import void_sat_format` is what an operator's file
    says; a module that became `ingestion.void_sat_format` would still import here under its
    new name and break every one of those files."""
    module = importlib.import_module(name)

    assert module.__name__ == name, (
        "%s resolved as %s - the promised spelling is the bare one" % (name, module.__name__))


@pytest.mark.parametrize("name", OPERATOR_IMPORT_NAMES)
def test_a_promised_name_is_a_file_at_the_top_of_server(name):
    """⛔ WHERE IT LIVES IS PART OF THE PROMISE. `sys.path` happens to contain `server/` and
    `server/parsers/`, so a bare import can succeed from more than one home; what must not
    change is that it is reachable without a package prefix.

    ⚠️ MEASURED WHILE WRITING THIS: `database` is a NAMESPACE package - `server/database/`
    has no `__init__.py`, so its `__file__` is None and only `__path__` says where it is.
    Reading `__file__` alone made this case fail on a module that was perfectly fine, and
    `or ""` turned that None into the CURRENT DIRECTORY, which is a wrong answer rather than
    an error.
    """
    module = importlib.import_module(name)
    homes = _homes_of(module)

    allowed = {SERVER_DIR, os.path.join(SERVER_DIR, "parsers"),
               os.path.join(SERVER_DIR, "database")}
    assert homes and homes <= allowed, (name, sorted(homes))


# ---------------------------------------------------------------------------
# ⚠️ the direction that catches a NEW name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("shim", HAND_COPIED)
def test_a_hand_copied_shim_imports_only_promised_names(shim):
    """⚠️ THE CASE THAT DOES WORK LATER. A shim that gains an import nobody promised would
    ship an operator a file that breaks the day that module moves - and it would do so
    silently, because the shim keeps working here where everything is top-level."""
    named = _imported_names(shim)
    unpromised = {n for n in named if n not in OPERATOR_IMPORT_NAMES
                  and n not in sys.builtin_module_names
                  and not _is_stdlib_or_third_party(n)}

    assert not unpromised, (
        "%s imports names outside the promise: %s - either add them to "
        "OPERATOR_IMPORT_NAMES or stop shipping them" % (shim, sorted(unpromised)))


def _is_stdlib_or_third_party(name):
    """A name is ours only if it resolves to a file under `server/`."""
    try:
        module = importlib.import_module(name)
    except Exception:
        return True
    path = os.path.abspath(getattr(module, "__file__", "") or "")
    return not path.startswith(SERVER_DIR + os.sep)


def test_the_shims_actually_name_something(request):
    """🔴 A SUBSET ASSERTION IS VACUOUS OVER AN EMPTY SET. If the parse ever returned nothing
    - a renamed file, a changed extension - the case above would pass while measuring
    nothing at all."""
    for shim in HAND_COPIED:
        ours = {n for n in _imported_names(shim) if not _is_stdlib_or_third_party(n)}
        assert ours, shim
        # ⚰️ THIS PINNED `void_sat_format`, which only the two PARSER samples import. The
        #    property it was after is 「this file is actually covered by the promise」, and
        #    that generalises to the mapper samples the tuple now carries; the literal did
        #    not. A shim naming none of the promised modules makes the subset case above
        #    vacuous for it, which is the thing worth refusing.
        assert ours & set(OPERATOR_IMPORT_NAMES), (shim, sorted(ours))


# ---------------------------------------------------------------------------
# 🔴 the live mappers - the half that was missed
# ---------------------------------------------------------------------------

#: `server/mappers/` is gitignored: the operator's own files, which this repo never edits.
#: It CAN read them, and 「which top-level names does this file import」 is a structural fact
#: rather than a number about this box - so no count is recorded here, only the set
#: relation. (S-211, 판정 364.)
LIVE_MAPPERS = os.path.join(SERVER_DIR, "mappers")


def _live_mapper_imports():
    """Top-level server modules the live mappers name. Empty if the folder is not here."""
    found = set()
    if not os.path.isdir(LIVE_MAPPERS):
        return found
    for entry in sorted(os.listdir(LIVE_MAPPERS)):
        if not entry.endswith(".py"):
            continue
        try:
            tree = ast.parse(io.open(os.path.join(LIVE_MAPPERS, entry),
                                     encoding="utf-8").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            heads = ([a.name.split(".")[0] for a in node.names]
                     if isinstance(node, ast.Import)
                     else ([node.module.split(".")[0]]
                           if isinstance(node, ast.ImportFrom) and node.module
                           and not node.level else []))
            for head in heads:
                if os.path.isfile(os.path.join(SERVER_DIR, head + ".py")):
                    found.add(head)
    return found


@pytest.mark.skipif(not os.path.isdir(LIVE_MAPPERS),
                    reason="no live mappers here: %s" % LIVE_MAPPERS)
def test_every_name_the_live_mappers_import_is_promised():
    """🔴 THE GATE THAT WAS MISSING. A package move renamed modules the operator's mappers
    import; it was applied, the suite broke, and it was reverted. Nothing measured that
    surface, so nothing objected until the tree was already moved.

    ⚠️ SET RELATION, NOT A COUNT. How many mappers this box happens to hold says nothing
    about production; which NAMES a mapper may rely on is the same everywhere, because it is
    what the product promises.
    """
    named = _live_mapper_imports()
    unpromised = sorted(named - set(OPERATOR_IMPORT_NAMES))

    assert not unpromised, (
        "the live mappers import top-level modules that are not promised: %s - either add "
        "them to OPERATOR_IMPORT_NAMES or stop them being importable" % unpromised)
