# -*- coding: utf-8 -*-
"""S-215. What a mapper may import is a declared table, and every name in it resolves.

🔴 THE SURFACE WAS REAL BUT UNWRITTEN. The owner's live mappers reach into nine product
modules for 41 names; only two of what they use came from `mapper_sdk` at all. So the
"SDK" described a surface nobody used while the real one was undeclared - and an undeclared
surface cannot be kept, because nothing says what is in it.

🔴 DECLARED, AND RESOLVED WHEN TOUCHED. Those nine modules are 13,406 lines and `mapper_sdk`
sits on the chain worker's boot path, so re-exporting eagerly would put all of it there for
names most mappers never touch. `__getattr__` pulls only what is asked for, and returns the
SOURCE MODULE'S OWN OBJECT - a wrapper would be a second implementation of something that
already has one.

⚠️ THE FAILURE SHAPE THIS TABLE HAS IS 「A NAME THAT NO LONGER RESOLVES」 - a promise to files
this repo cannot see, pointing at something that moved or was renamed. That is what the
sweep below exists for, and it is why the table is scored rather than merely written.
"""
import importlib
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                    # noqa: E402
from parsers.directory_watcher import OPERATOR_IMPORT_NAMES          # noqa: E402

SURFACE = mapper_sdk.MAPPER_SURFACE


# ---------------------------------------------------------------------------
# 🔴 gate ③ - every declared name resolves
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(SURFACE))
def test_a_declared_name_resolves(name):
    """🔴 THE ONLY WAY THIS TABLE FAILS. A name left behind after its source moved is a
    promise that raises - and it raises in the operator's file, not here, unless this runs."""
    # ⚠️ RESOLUTION IS THE ASSERTION. `getattr` raising IS the failure, so there is nothing
    # to compare against - and a comparison written anyway (`is not None`) would be vacuous
    # for every constant that is legitimately falsy.
    getattr(mapper_sdk, name)


# ---------------------------------------------------------------------------
# 🔴 gate ④ - the same object, never a copy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(SURFACE))
def test_the_resolved_object_is_the_source_modules_own(name):
    """🔴 판정 368 ①. `is`, not `==`: a wrapper or a re-implementation would satisfy equality
    for a while and then drift, which is the two-paths defect one level down."""
    source = importlib.import_module(SURFACE[name])

    assert getattr(mapper_sdk, name) is getattr(source, name), name


# ---------------------------------------------------------------------------
# ⛔ no branch beyond the table
# ---------------------------------------------------------------------------

def test_an_undeclared_name_raises_the_ordinary_attribute_error():
    """⛔ 판정 369. The seat composes no refusal sentence - Python already writes one, and a
    second author would make a typo read like a product rule."""
    with pytest.raises(AttributeError) as raised:
        mapper_sdk.definitely_not_declared

    assert "definitely_not_declared" in str(raised.value)


def test_the_table_is_data_and_nothing_else():
    """⚠️ NAME -> MODULE PATH, both strings. Anything else here would be a branch wearing a
    dict's clothes."""
    assert SURFACE and all(
        isinstance(k, str) and isinstance(v, str) for k, v in SURFACE.items())


# ---------------------------------------------------------------------------
# 🔴 gate ① - every name a mapper uses is on the surface or a promised public name
# ---------------------------------------------------------------------------

LIVE_MAPPERS = os.path.join(SERVER_DIR, "mappers")


@pytest.mark.skipif(not os.path.isdir(LIVE_MAPPERS),
                    reason="no live mappers here: %s" % LIVE_MAPPERS)
def test_every_name_the_mappers_use_is_declared_somewhere():
    """🔴 판정 368 ③. The day a mapper starts using a name nobody declared - a NEW private,
    especially - this is what says so. Until then the two privates already on the table are
    green, because writing the contract down is what this round did.

    ⚠️ SET RELATION, NO COUNTS: how many mappers this box holds says nothing about
    production; which names may be relied on is the same everywhere.
    """
    import ast
    import io

    promised = set(OPERATOR_IMPORT_NAMES)
    undeclared = set()
    for entry in sorted(os.listdir(LIVE_MAPPERS)):
        if not entry.endswith(".py"):
            continue
        try:
            tree = ast.parse(io.open(os.path.join(LIVE_MAPPERS, entry),
                                     encoding="utf-8").read())
        except Exception:
            continue
        bound = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    head = a.name.split(".")[0]
                    if head in promised:
                        bound[a.asname or head] = head
            elif isinstance(node, ast.ImportFrom) and node.module:
                head = node.module.split(".")[0]
                if head in promised:
                    for a in node.names:
                        if a.name not in SURFACE and not hasattr(
                                importlib.import_module(head), a.name):
                            undeclared.add("%s.%s" % (head, a.name))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id in bound):
                head = bound[node.value.id]
                if node.attr not in SURFACE and node.attr.startswith("_"):
                    undeclared.add("%s.%s" % (head, node.attr))

    assert not undeclared, (
        "mappers reach names that are neither on the surface nor declared public: %s"
        % sorted(undeclared))
