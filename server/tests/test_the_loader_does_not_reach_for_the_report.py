# -*- coding: utf-8 -*-
"""S-211 ①. The loader and the report stop importing each other, and no `def` hides it.

🔴 A DEFERRED IMPORT DOES NOT BREAK A CYCLE, IT HIDES ONE. Measured before this round: the
eight-module SCC had only THREE import-time edges and no cycle among them - the whole ring
was held apart by 22 in-function import statements. Nothing failed, which is the problem: the
structure was circular and the code simply never said so.

🔴 SO THE ASSERTION IS ABOUT BOTH PLACES. Checking only module-level imports would pass the
exact defect being removed here - `verification_report` imported the report from INSIDE
itself, and a module-level check cannot see that.

⚠️ WHAT MOVED, AND WHY THAT DIRECTION: the loader needed a SENTENCE, not a report. The
sentence went down to `virtual_join_refusal`, which imports nothing but stdlib, and both read
it. A report reading a loader is the right way round and is untouched.

⚠️ THE TEXT IS THE SUBJECT HERE, not a proxy for behaviour: the question is literally 「does
this file name that module」, which is what the source says and what a reader sees.
"""
import ast
import io
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

# 🪦 [S-211 packaging] these live in packages now; the assertions are unchanged.
# ⚰️ [S-283] AND THEY MOVED AGAIN with the read-time join's retirement: the
#    declaration loader and the sentence are `chain` modules now. The ring, and every
#    assertion about it, is the same - only the spelling of two nodes changed.
LOADER = "chain/legacy_join_declaration"
REPORT = "config_resolve_report"
SENTENCE = "chain/join_refusal"


def _imports(module_name):
    """Every module this file imports, module-level and inside a `def` alike."""
    path = os.path.join(SERVER_DIR, *(module_name.split("/"))) + ".py"
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name.split(".")[0])
                found.add(a.name)                       # `import enrichment.config`
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split(".")[0])
            found.add(node.module)
            # 🔴 AND THE NAMES TAKEN OUT OF THE PACKAGE. After S-211 a module is reached as
            # `from chain import cell_layer`, so recording only the package head would make
            # every one of these assertions answer about `chain` rather than about the
            # module being asked after.
            for a in node.names:
                found.add(a.name)
                found.add("%s.%s" % (node.module, a.name))
    return found


# ---------------------------------------------------------------------------
# 🔴 the cut
# ---------------------------------------------------------------------------

def test_the_loader_never_names_the_report():
    """🔴 THE EDGE THAT WAS BACKWARDS. `verification_report` imported the report from inside
    itself to build one Korean sentence."""
    assert REPORT not in _imports(LOADER)


def test_both_read_the_sentence_from_the_light_module():
    assert "chain.join_refusal" in _imports(LOADER)
    assert "chain.join_refusal" in _imports(REPORT)


def test_the_light_module_imports_nothing_of_ours():
    """⛔ 「LIGHT」 IS THE WHOLE PROPERTY. The moment this module imports one of ours it can
    be on a cycle again, and the thing that was moved down is back up."""
    ours = {name for name in _imports(SENTENCE)
            if os.path.exists(os.path.join(SERVER_DIR, name + ".py"))
            or os.path.isdir(os.path.join(SERVER_DIR, name))}

    assert not ours, "the light module grew a dependency: %s" % sorted(ours)


def test_the_report_still_reads_the_loader_because_that_way_is_correct():
    """⚠️ NOT EVERY EDGE IS A DEFECT. A report reading a loader is the right direction; only
    the reverse was wrong. Asserting this keeps a later 「cycle cleanup」 from cutting the good
    edge and calling the graph tidy."""
    assert "chain.legacy_join_declaration" in _imports(REPORT)


# ---------------------------------------------------------------------------
# ⚠️ and no `def` hides what is left
# ---------------------------------------------------------------------------

def _deferred_pairs(module_name):
    path = os.path.join(SERVER_DIR, *(module_name.split("/"))) + ".py"
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out = set()

    def walk(node, depth):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)) and depth:
                heads = ([a.name.split(".")[0] for a in child.names]
                         if isinstance(child, ast.Import)
                         else ([child.module.split(".")[0]]
                               if child.module and not child.level else []))
                out.update(heads)
            walk(child, depth + (1 if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else 0))

    walk(tree, 0)
    return out


#: The ring as the IMPORT GRAPH names it today - package-qualified where they moved.
RING = ("chain_bindings", "synthesis", "ingestion_worker", "replay",
        "config_resolve_report", "dt_map_derivation",
        "legacy_join_declaration", "legacy_materialized_join")


@pytest.mark.parametrize("module", (REPORT, LOADER))
def test_neither_side_defers_an_import_of_the_other_ring_members(module):
    """🔴 THE GATE THE RULING NAMED: 「그 5 쌍의 함수 안 import 이 0」. These two modules left
    the ring, so they have no reason left to import a ring member from inside a function - and
    a deferred import is precisely how the ring stayed invisible."""
    deferred = _deferred_pairs(module) & set(RING)

    assert not deferred, (
        "%s defers an import of %s - that is the mechanism this round removed"
        % (module, sorted(deferred)))
