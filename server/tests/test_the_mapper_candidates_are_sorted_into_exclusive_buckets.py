# -*- coding: utf-8 -*-
"""S-223 / 판정 379. 「없다」·「고장났다」·「다른 계열이다」는 세 답이고, 한 칸에 접으면 거짓이 된다.

🔴 THE SCREEN SAID 「no options」 ABOUT A DIRECTORY FULL OF WORKING MAPPERS. `/admin/mappers/list`
answered the dropdown from `MAPPER_REGISTRY` alone — the names `@mapper` registered — while
the mappers actually running are MODULE-LEVEL FUNCTIONS a rule names through
`mapper_function`. `mapper_candidates()` is the one place that population is built.

🔴 THE BUCKETS ARE MUTUALLY EXCLUSIVE, AND THAT IS THE PROPERTY THIS FILE SCORES. A module
that could not be imported is `refused` and NOTHING ELSE — judging its family from its text
is the mistake this round's own first measurement made (parsing says nothing about
importing). The day it loads it MOVES to the bucket its contents put it in, and the move is
asserted here in order, because a transition is the only way to see that the two buckets are
not quietly both true.

⚠️ A FUNCTION IS FILTERED BY ITS SIGNATURE, NEVER BY ITS NAME. The executor hands over
`(db, payload)`, so 「takes at least two positional arguments」 is the property.
"""
import os
import sys
import textwrap

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                    # noqa: E402


def _build(root, package, modules):
    """Write a fixture mapper package to disk and hand back its name."""
    directory = root / package
    directory.mkdir()
    (directory / "__init__.py").write_text("", encoding="utf-8")
    for name, body in modules.items():
        (directory / f"{name}.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return package


def _evict(package):
    for name in [n for n in list(sys.modules)
                 if n == package or n.startswith(package + ".")]:
        del sys.modules[name]


@pytest.fixture
def isolated_registry(monkeypatch):
    """A registry of its own, so 「exactly one registered candidate」 means the fixture's.

    `register` and `discover` read these as module globals at call time, so replacing the
    attribute replaces what the decorator writes into — and monkeypatch puts the real ones
    back, which matters because the chain worker's registry lives in this same module.
    """
    monkeypatch.setattr(mapper_sdk, "MAPPER_REGISTRY", {})
    monkeypatch.setattr(mapper_sdk, "MAPPER_PARAMS", {})


FOUR_BOXES = {
    "registered_one": """
        import mapper_sdk

        @mapper_sdk.mapper(name="fixture_registered", params=("alpha",))
        def build_registered_rows(df, db):
            return df
        """,
    "plain_function": """
        FIXTURE_CONSTANT = 7

        def build_fixture_rows(db, payload):
            return {"updates": []}

        def not_a_mapper(db):
            return None
        """,
    "roleframe_only": """
        from ledger.roleframe import BaseLedgerMapper

        class FixtureLedgerMapper(BaseLedgerMapper):
            pass
        """,
    "broken": """
        raise TypeError("fixture: this module refuses to import")
        """,
}


@pytest.fixture
def four_boxes(tmp_path, monkeypatch, isolated_registry):
    package = _build(tmp_path, "s223_four_boxes", FOUR_BOXES)
    monkeypatch.syspath_prepend(str(tmp_path))
    _evict(package)
    yield package
    _evict(package)


# ---------------------------------------------------------------------------
# 🔴 gate — one in each box, and no module in two
# ---------------------------------------------------------------------------

def test_each_bucket_holds_the_one_module_that_belongs_in_it(four_boxes):
    out = mapper_sdk.mapper_candidates(four_boxes)

    registered = [c for c in out["candidates"] if c["kind"] == "registered"]
    functions = [c for c in out["candidates"] if c["kind"] == "function"]

    # ⚰️ [판정 562 · 600] THE PRODUCT'S OWN MAPPERS SHARE THIS REGISTRY NOW. They used to sit
    #   in a kind table of their own, so 「registered」 meant 「an author's `@mapper`」 and the
    #   bucket held exactly the fixture. One registry means this bucket legitimately holds
    #   both, so the assertion splits them rather than counting.
    # 🔴 AND BOTH HALVES ARE PINNED: a stray registration still turns this red, and a product
    #   template that failed to install turns it red too.
    from chain import dynamic_mappers

    product = set(dynamic_mappers.TEMPLATES)
    names = {c["name"] for c in registered}
    assert product <= names, (
        "a mapper the product builds from declarations is not registered: %s"
        % sorted(product - names))
    assert [(c["name"], c["params"]) for c in registered if c["name"] not in product] == [
        ("fixture_registered", ["alpha"])]
    assert [(c["module"], c["name"]) for c in functions] == [
        (f"{four_boxes}.plain_function", "build_fixture_rows")]
    assert [o["module"] for o in out["other"]] == [f"{four_boxes}.roleframe_only"]
    assert [r["module"] for r in out["refused"]] == [f"{four_boxes}.broken"]


def test_the_refusal_names_the_reason_rather_than_the_count(four_boxes):
    """🔴 「하나가 안 읽혔다」 IS NOT AN ANSWER. The operator's next action is in the reason."""
    why = mapper_sdk.mapper_candidates(four_boxes)["refused"][0]["why"]

    assert why.startswith("TypeError: ")
    assert "this module refuses to import" in why


def test_a_one_argument_function_is_not_a_candidate(four_boxes):
    """The executor calls `(db, payload)`; a one-argument function would raise at run time."""
    named = {c["name"] for c in mapper_sdk.mapper_candidates(four_boxes)["candidates"]}

    assert "not_a_mapper" not in named


def test_no_module_lands_in_two_buckets(four_boxes):
    out = mapper_sdk.mapper_candidates(four_boxes)
    candidates = {c["module"] for c in out["candidates"]}
    other = {o["module"] for o in out["other"]}
    refused = {r["module"] for r in out["refused"]}

    assert candidates & other == set()
    assert candidates & refused == set()
    assert other & refused == set()


def test_a_registered_mapper_is_not_listed_a_second_time_as_a_function(four_boxes):
    """🔴 `@mapper` LEAVES ITS WRAPPER ON THE MODULE-LEVEL NAME TOO. Listed twice, one mapper
    reads as two choices and nothing on the screen says picking either runs the same code."""
    rows = [c for c in mapper_sdk.mapper_candidates(four_boxes)["candidates"]
            if c["module"] == f"{four_boxes}.registered_one"]

    assert [c["kind"] for c in rows] == ["registered"]


# ---------------------------------------------------------------------------
# 🔴 gate — the transition: refused -> other, never both
# ---------------------------------------------------------------------------

MENDING = {
    "mending": """
        import os

        if os.environ.get("S223_FIXTURE_MENDED") != "1":
            raise TypeError("fixture: not mended yet")

        from ledger.roleframe import BaseLedgerMapper

        class MendedLedgerMapper(BaseLedgerMapper):
            pass
        """,
}


def test_a_module_moves_out_of_refused_the_day_it_imports(tmp_path, monkeypatch,
                                                          isolated_registry):
    """🔴 ORDERED, BECAUSE THE MOVE IS THE ASSERTION. Measured broken first and mended second,
    so 「it is in `other`」 cannot be satisfied by a module that was never refused."""
    package = _build(tmp_path, "s223_mending", MENDING)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delenv("S223_FIXTURE_MENDED", raising=False)
    _evict(package)
    module = f"{package}.mending"

    try:
        broken = mapper_sdk.mapper_candidates(package)
        assert [r["module"] for r in broken["refused"]] == [module]
        assert broken["other"] == []
        assert module not in {c["module"] for c in broken["candidates"]}

        monkeypatch.setenv("S223_FIXTURE_MENDED", "1")
        mended = mapper_sdk.mapper_candidates(package)
        assert [o["module"] for o in mended["other"]] == [module]
        assert mended["refused"] == []
        assert module not in {c["module"] for c in mended["candidates"]}
    finally:
        _evict(package)
