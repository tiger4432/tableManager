# -*- coding: utf-8 -*-
"""The counted list existed and the form could not reach it.

`implementation_choices` was landed with its own tests and then had no consumer: both
`implementation_id` squares in the skeleton were still `hint: free`, so the only way to
reach `declarative-role` on that surface was to already know it. A published value nothing
reads is the same screen as no value at all.

Two halves, and this file pins both:

  * the LISTS are published and the skeleton's two leaves NAME them, so the generic
    `choice` path draws a picker instead of a text box;
  * the DEFAULT is counted off the declaration the route reads. Every other list here is a
    property of the code and identical in every deployment; this one is a property of THIS
    deployment's sources, which is the whole reason `closed_lists` had to grow an argument.

⛔ NOTHING IS APPLIED. The default is published, never written into a document -- a screen
that fills a square the file does not hold edits somebody's config by drawing it.
"""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.config_authoring import closed_lists                 # noqa: E402
from ledger import implementations as impl                       # noqa: E402
from ledger.config_explorer_service import OntologyExplorerService  # noqa: E402
from ledger.setup_bundle import CONFIG_FILENAME                  # noqa: E402

PREPARE_LIST = "prepare_implementation"
MAP_LIST = "map_implementation"


def sources(*pairs):
    return {"s%d" % i: {"prepare": {"implementation_id": p},
                        "map": {"implementation_id": m}}
            for i, (p, m) in enumerate(pairs)}


def leaf(document, clause):
    """The `implementation_id` leaf inside a source's `prepare` / `map` record."""
    def walk(node):
        if isinstance(node, dict):
            if node.get("key") == clause and isinstance(node.get("node"), dict):
                for field in node["node"].get("fields") or ():
                    if field.get("key") == "implementation_id":
                        return field["node"]
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item)
                if found is not None:
                    return found
        return None
    return walk(document["root"])


# ---------------------------------------------------------------- the list is reachable

def test_both_squares_are_pickers_naming_a_published_list():
    """🔴 THE WIRING ITSELF. `hint: free` here is the defect this closes, and reverting a
    leaf to it leaves every other test in the repository green."""
    published = closed_lists()
    document = published["skeleton"]
    for clause, name in (("prepare", PREPARE_LIST), ("map", MAP_LIST)):
        node = leaf(document, clause)
        assert node is not None, "the %s clause lost its implementation_id" % clause
        assert node["hint"] == "choice", (
            "%s.implementation_id is free text again -- the name is unguessable, which is "
            "why it was wired" % clause)
        assert node["list"] == name
        assert published[name], "the leaf names a list with no members"


def test_the_members_are_the_registry_and_never_a_literal():
    published = closed_lists()
    assert published[PREPARE_LIST] == sorted(
        {name for name, _ in impl.source_preparer_declarations()})
    assert published[MAP_LIST] == sorted(
        {name for name, _ in impl.mapper_declarations()})


def test_the_two_squares_are_offered_different_sets():
    """A preparer's name in the mapper square is a value that can only ever refuse."""
    published = closed_lists()
    assert not set(published[PREPARE_LIST]) & set(published[MAP_LIST])


def test_the_version_rides_along_because_a_list_of_names_cannot_hold_it():
    published = closed_lists()
    block = published["implementations"]
    assert {o["id"] for o in block["map"]["options"]} == set(published[MAP_LIST])
    assert all(isinstance(o["version"], int) for o in block["map"]["options"])


# ---------------------------------------------------------------- the default is counted

def test_the_default_follows_the_declaration_it_is_handed():
    """🔴 GATE: hand it different sources and it answers differently. That property is what
    keeps the name out of the code -- a constant could not do this."""
    a = closed_lists(sources(("p1", "m1"), ("p1", "m1"), ("p2", "m2")))["implementations"]
    b = closed_lists(sources(("p2", "m2"), ("p2", "m2"), ("p1", "m1")))["implementations"]
    assert a["prepare"]["default"] == "p1" and a["map"]["default"] == "m1"
    assert b["prepare"]["default"] == "p2" and b["map"]["default"] == "m2"


def test_no_declaration_publishes_the_options_with_no_default():
    """⚠️ `None`, not the first option. An empty count decides nothing, and inventing a
    winner would decide by an axis that is not evidence."""
    for empty in (None, {}, ()):
        block = closed_lists(empty)["implementations"]
        assert block["prepare"]["default"] is None
        assert block["map"]["default"] is None
        assert block["map"]["options"], "the options are not conditional on the sources"


def test_only_the_counted_entry_moves_when_the_declaration_changes():
    """🔴 GATE: every OTHER closed list is a property of the code. If one of them started
    varying with the config, the screen would be offering a set the validator does not
    enforce -- which is the failure the whole module exists to prevent."""
    fixed = closed_lists()
    varied = closed_lists(sources(("p1", "m1"), ("p1", "m1")))
    assert set(fixed) == set(varied)
    moved = sorted(key for key in fixed if fixed[key] != varied[key])
    assert moved == ["implementations"], moved


# ---------------------------------------------------------------- the route reads it

def write_config(root, payload):
    root.mkdir(parents=True, exist_ok=True)
    io.open(str(root / CONFIG_FILENAME), "w", encoding="utf-8").write(payload)


def service_for(root):
    return OntologyExplorerService(
        config_root=root, setup_loader=lambda _root: None, catalog_loader=lambda: {})


def test_the_route_counts_off_the_file_rather_than_off_nothing(tmp_path):
    """🔴 THE HALF THAT WAS IN DOUBT: can the function that serves the form READ the
    declaration at all. `closed_lists()` took no argument, so the answer used to be no."""
    write_config(tmp_path, json.dumps(
        {"setup_version": 2,
         "sources": sources(("p9", "m9"), ("p9", "m9"), ("p8", "m8"))}))
    block = service_for(tmp_path).authoring_schema()["implementations"]
    assert block["prepare"]["default"] == "p9"
    assert block["prepare"]["counts"] == {"p9": 2, "p8": 1}


def test_an_unreadable_config_still_publishes_the_lists(tmp_path):
    """⛔ THIS PAYLOAD IS WHAT REPAIRS A BROKEN CONFIG. Raising here would blank the form
    exactly when it is needed; `authoring()` is where the parse error is reported."""
    write_config(tmp_path, "{ this is not json")
    published = service_for(tmp_path).authoring_schema()
    assert published[MAP_LIST]
    assert published["implementations"]["map"]["default"] is None


def test_an_absent_config_is_the_same_answer_as_an_empty_one(tmp_path):
    published = service_for(tmp_path / "nothing-here").authoring_schema()
    assert published[MAP_LIST] == closed_lists()[MAP_LIST]
    assert published["implementations"]["map"]["default"] is None
