# -*- coding: utf-8 -*-
"""A refusal about an attribute had nowhere to land, so the save failed and nothing went red.

S-52 gave an attribute three addresses -- the type declares the names, a source binds them
once, and a role may override that binding -- and `authoring_plan` produced no row for any
of the three.  A refusal reaches a square by its PATH (`authoring_plan` keys `by_path` on
`Field.path`, and the screen prefix-matches the same string), so every refusal written
under `attributes` fell into `unattached_refusals`: the declaration would not compile and
the form showed the operator nothing owed.  `_profile_fields` records the same class one
declaration over, for `bind.mappings`.

The subject is the SHIPPED sample and the SHIPPED catalog, both tracked.  The live root is
this box's own file; the sample is the one that says what the grammar looks like anywhere.
"""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.config_authoring import authoring_plan            # noqa: E402
from ledger.setup_bundle import load_physical_catalog          # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
BIND = "bundle.sources.dt_job.bind.entities.dtjob@1.attributes"
ROLE = "bundle.sources.dt_job.bind.mappings.counted.bind.subject.attributes"


@pytest.fixture(scope="module")
def catalog():
    return load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))


@pytest.fixture(scope="module")
def shipped():
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        return json.load(fh)


def rows(bundle, catalog):
    return {row["path"]: row for row in authoring_plan(bundle, catalog)["fields"]}


def bind_entities(bundle):
    return bundle["sources"]["dt_job"]["bind"]["entities"]["dtjob@1"]["attributes"]


# ------------------------------------------------------------------ the three addresses

def test_each_of_the_three_seats_has_a_row(shipped, catalog):
    """🔴 THE ADDRESSES ARE THE VALIDATOR'S, NOT THIS TEST'S.  Each one below is a path
    `setup_bundle` writes a refusal at; that is the whole reason a row has to exist there."""
    plan = rows(shipped, catalog)
    assert plan["bundle.entities.dtjob@1.attributes"]["value"] == ["dt_eqp"]
    assert plan[f"{BIND}.dt_eqp"]["state"] == "answered"
    assert plan[f"{BIND}.dt_eqp"]["value"] == {"kind": "column", "column": "dt_eqp"}
    role = copy.deepcopy(shipped)
    role["sources"]["dt_job"]["bind"]["mappings"]["counted"]["bind"]["subject"][
        "attributes"] = {"dt_eqp": {"kind": "column", "column": "dt_eqp"}}
    assert rows(role, catalog)[f"{ROLE}.dt_eqp"]["state"] == "answered"


@pytest.mark.parametrize("label,mutate,path,code", [
    ("the binding is not an object",
     lambda c: bind_entities(c).__setitem__("dt_eqp", "dt_eqp"),
     f"{BIND}.dt_eqp", "invalid_binding"),
    ("the source binds a name the type never declared",
     lambda c: bind_entities(c).__setitem__("nope", {"kind": "column",
                                                     "column": "dt_eqp"}),
     f"{BIND}.nope", "unknown_entity_attribute"),
    ("the type declares an empty list",
     lambda c: c["entities"]["dtjob@1"].__setitem__("attributes", []),
     "bundle.entities.dtjob@1.attributes", "invalid_type"),
    ("a role overrides with a name the type never declared",
     lambda c: c["sources"]["dt_job"]["bind"]["mappings"]["counted"]["bind"][
         "subject"].__setitem__("attributes", {"nope": {"kind": "column",
                                                        "column": "dt_eqp"}}),
     f"{ROLE}.nope", "unknown_entity_attribute"),
])
def test_the_refusal_lands_on_the_row_rather_than_in_the_loose_list(
        shipped, catalog, label, mutate, path, code):
    """⚠️ NOT A COUNT OF REFUSALS.  What is scored is WHERE each one ends up: on the
    square the operator typed in, and out of `unattached_refusals` -- which is the list the
    screen cannot draw."""
    bundle = copy.deepcopy(shipped)
    mutate(bundle)
    plan = authoring_plan(bundle, catalog)
    assert not plan["unattached_refusals"], plan["unattached_refusals"]
    row = {item["path"]: item for item in plan["fields"]}[path]
    assert [item["code"] for item in row["refusals"]] == [code], label


# --------------------------------------------------------- and nothing else moved at all

def strip_attributes(value):
    """The same document with every `attributes` key taken out, at every depth."""
    if isinstance(value, dict):
        return {key: strip_attributes(item) for key, item in value.items()
                if key != "attributes"}
    if isinstance(value, list):
        return [strip_attributes(item) for item in value]
    return value


def test_a_declaration_that_uses_no_attribute_gets_no_new_row(shipped, catalog):
    """🔴 THE ROWS ARE ADDED, NOT WOVEN IN.  With nothing declaring an attribute all three
    blocks contribute exactly zero rows and change nothing else, so a site that has never
    used the feature sees the surface it always saw -- and that is checked over EVERY row
    rather than by a count.

    ⚠️ NOT "the stripped plan equals the full plan minus these rows".  S-52 already made
    an object-less predicate open one optional ROLE per attribute its subject declares
    (`setup_bundle.predicate_claim`), so taking the names out legitimately removes three
    `register` role rows as well.  Those belong to that landing, not to this one, and
    scoring them here would make this gate red for somebody else's correct change.
    """
    bare = strip_attributes(copy.deepcopy(shipped))
    bare["sources"]["dt_job"]["bind"].pop("entities", None)
    plan = authoring_plan(bare, catalog)
    assert not [row["path"] for row in plan["fields"] if "attributes" in row["path"]]
    assert not [row["path"] for row in plan["fields"]
                if (row["ground"] or {}).get("rule")
                == "entity_binding_attributes_from_entity"]


# ------------------------------------------------------------- the box for an unbound one

def test_the_form_can_draw_an_attribute_nobody_has_bound_yet(shipped, catalog):
    """A name-keyed map draws what the DOCUMENT holds plus what the PLAN names, and the
    plan names them through one row: `derived` + `disposition == "shape"`, whose value is
    the member list (`renderSkeletonMap` -> `plannedMembers`).  Anything else and an
    attribute the type declares but nobody has bound has no box to bind it in."""
    bundle = copy.deepcopy(shipped)
    bind_entities(bundle).clear()
    bind_entities(bundle)["other"] = {"kind": "column", "column": "dt_eqp"}
    plan = rows(bundle, catalog)
    shape = plan[BIND]
    assert shape["state"] == "derived" and shape["disposition"] == "shape"
    assert shape["value"] == ["dt_eqp"]
    assert plan[f"{BIND}.dt_eqp"]["state"] == "unanswered", (
        "a declared attribute this source has not bound must still get a box")


def test_the_binding_row_offers_no_column_chips(shipped, catalog):
    """⛔ A PICKER HERE WOULD WRITE THE WRONG SHAPE.  `editableFor` turns `candidates`
    into a control that writes at `row.path`, and this path holds a binding RECORD -- a
    column name written there is the very "the form draws what the validator refuses"
    defect these rows exist to surface."""
    plan = rows(shipped, catalog)
    assert plan[f"{BIND}.dt_eqp"]["candidates"] is None
