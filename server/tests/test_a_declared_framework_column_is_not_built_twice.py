# -*- coding: utf-8 -*-
"""Declaring `row_id` broke the model builder, and the running server was hiding it.

판정 140. The builder makes `row_id` the PRIMARY KEY of every dynamic table, and until
2026-09-08 no `column_types` listed it -- the catalogue loader planted it into its own view
of a relation and nobody declared it. Then 판정 138 made a VIEW declare its columns as they
are, five of them carry `row_id`, and SQLAlchemy refused the second definition:
「Trying to redefine primary-key column 'row_id' as a non-primary-key column」.

🔴 THE RUNNING PROCESS HID IT. A server that started BEFORE the declaration keeps the models
it already built, so nothing was red anywhere -- the failure waits for the next restart or
config reload. This file is what makes it visible without one.

⚠️ SKIPPING IS NOT IGNORING THE DECLARATION. The declaration stays true (that view does have
the column) and the catalogue loader reads it to answer `frame_row_id`; what is skipped is
BUILDING it twice.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                          # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample",
                      "table_config.json.sample")


@pytest.fixture(scope="module")
def catalog():
    with open(SAMPLE, encoding="utf-8") as handle:
        return json.load(handle)


def test_the_shipped_catalogue_builds(catalog):
    """🔴 THE GATE. The shipped sample is what a new deployment starts from, and it declares
    `row_id` on the five views that have one.

    ⚰️ IT USED TO ASSERT `len(DYNAMIC_TABLES) == len(catalog)`, AND THAT NUMBER WAS THIS
    BOX'S (S-200). The registry starts the session holding whatever the LIVE, gitignored
    `config/table_config.json` declares — 45 names here — and it passed only because, on this
    machine, live is a strict SUBSET of the sample (`live - sample` is empty, `sample - live`
    is `dt_job_rollup`). An operator who declares one extra table would see this red with no
    leakage at all: the gate's subject was a file the repository cannot see.

    🔴 THE PROPERTY IT WAS SCORING SURVIVES AS A SET: everything declared gets built, and
    building adds nothing else. Same question, no number.
    """
    before = set(models.DYNAMIC_TABLES)
    models.init_dynamic_models(catalog)
    assert set(catalog) <= set(models.DYNAMIC_TABLES), (
        "declared but not built: %s" % sorted(set(catalog) - set(models.DYNAMIC_TABLES)))
    assert set(models.DYNAMIC_TABLES) - before <= set(catalog), (
        "building the catalogue registered something it does not declare: %s"
        % sorted(set(models.DYNAMIC_TABLES) - before - set(catalog)))


def test_a_view_that_declares_row_id_gets_exactly_one_and_it_is_the_key(catalog):
    """⚠️ NOT JUST "IT DID NOT RAISE". The column has to be there ONCE and be the primary
    key -- a builder that skipped it entirely would also stop raising, and the table would
    then have no key at all."""
    models.init_dynamic_models(catalog)
    declared = [name for name, entry in catalog.items()
                if entry.get("kind") == "view"
                and "row_id" in (entry.get("column_types") or {})]
    assert len(declared) == 5, declared
    for name in declared:
        table = models.DYNAMIC_TABLES[name].__table__
        assert [c.name for c in table.columns].count("row_id") == 1, name
        assert [c.name for c in table.primary_key] == ["row_id"], name


def test_a_relation_that_declares_none_is_unchanged(catalog):
    """The tables -- 34 of them -- never declared it and must build exactly as before."""
    models.init_dynamic_models(catalog)
    silent = [name for name, entry in catalog.items()
              if "row_id" not in (entry.get("column_types") or {})]
    assert len(silent) == len(catalog) - 5
    for name in silent:
        table = models.DYNAMIC_TABLES[name].__table__
        entry = catalog[name]
        if str(entry.get("kind") or "table") == "view":
            # 🔴 A VIEW HAS NO FRAMEWORK COLUMNS TO BE UNCHANGED BY (S-186). It is built
            # from its declared columns alone, so its mapped key is its declared
            # `business_key` — and where a view DOES declare `row_id` the key stays
            # `row_id` (판정 296), which the sibling assertion above already covers.
            #
            # ⚠️ Split rather than loosened: asserting 「row_id or business_key」 for
            # everything would stop this test noticing a real table that lost its PK.
            expected = [str(entry.get("business_key") or
                            list(entry.get("column_types") or {"?": 1})[0])]
            assert [c.name for c in table.primary_key] == expected, name
            continue
        assert [c.name for c in table.primary_key] == ["row_id"], name


def test_the_two_passes_read_one_list():
    """⛔ THE LIST WAS WRITTEN OUT TWICE. `init_dynamic_models` has a fresh-build pass and a
    hot-swap pass, and each carried its own copy of the framework columns -- so a name added
    to one would be built by the other on any deployment that had already loaded the table.
    """
    import inspect

    body = inspect.getsource(models.init_dynamic_models)
    assert body.count("FRAMEWORK_COLUMNS") == 2
    assert "created_at" not in body.split("FRAMEWORK_COLUMNS")[0][-400:], (
        "a hand-written copy of the list is back")
    assert "row_id" in models.FRAMEWORK_COLUMNS
