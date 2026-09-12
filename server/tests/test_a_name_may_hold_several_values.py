# -*- coding: utf-8 -*-
"""S-144 / A1-2. 「이 이름은 값을 «여럿» 든다」 — a declared cell, and a walk that reads it.

🔴 PLURALITY DOES NOT ARRIVE AS A LIST IN ONE ATOM, which is what the measurement changed
about this round. A column holds one value per ROW, so a wafer with two products is two
rows and two registrations. The walk read that as one name with two values: it counted a
disagreement in `attribute_conflicts` and then kept only the latest, so the second value
was gone from the response entirely. Both were true, and nothing could say so.

⚠️ THE REFUSING HALF IS NOT THE ONE THAT MATTERED. `roleframe._scalar` does refuse a JSON
list, and that path is untouched — it is only reached by a mapper building a list by hand.
The path operations actually walk is the one above.

🔴 THE SHAPE IS FIXED PER NAME. A `many` name is a list even when it holds one value.
「a list only when there are two」 puts two shapes in one cell and the reader has to guess
which it got, which is the class 「한 경계에 모양이 둘이면 조용히 실패한다」 names.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import setup_bundle                                   # noqa: E402
from ledger_api import ledger_subgraph                            # noqa: E402
import validation                                                 # noqa: E402


# ---------------------------------------------------------------------------
# the cell, and what it refuses
# ---------------------------------------------------------------------------

def _entity_problems(entity):
    """Score ONE entity declaration through the real validator."""
    problems = validation.Problems()
    setup_bundle._validate_entities({"wafer@1": entity}, problems)
    return [issue.to_mapping() for issue in problems.finish()]


def test_an_attribute_may_be_declared_to_hold_several_values():
    assert _entity_problems({
        "keys": ["wid"],
        "attributes": ["product", "lot_state"],
        "attribute_cardinality": {"product": "many"},
    }) == []


def test_absence_is_one_which_is_what_every_declaration_on_disk_means():
    """⚠️ THE CELL IS ONLY WRITTEN WHERE IT CHANGES SOMETHING. Unlike `class`, 「declared
    single」 and 「never classified」 are the SAME answer here, so a default is safe."""
    assert _entity_problems({"keys": ["wid"], "attributes": ["product"]}) == []
    assert setup_bundle.DEFAULT_ATTRIBUTE_CARDINALITY == "one"


def test_a_word_outside_the_closed_set_is_refused():
    problems = _entity_problems({
        "keys": ["wid"], "attributes": ["product"],
        "attribute_cardinality": {"product": "several"}})
    assert [p["path"] for p in problems] == ["bundle.entities.wafer@1.attribute_cardinality.product"]


def test_a_name_that_is_not_an_attribute_is_REFUSED_rather_than_ignored():
    """🔴 THE TRAP THIS ROUND MEASURED. `_column_values` drops anything that is not a
    string SILENTLY, so a cell in the wrong shape disappears without a word — an operator
    who typed `prodcut` would get no plurality and no error either, which is the worst of
    both. This cell refuses."""
    problems = _entity_problems({
        "keys": ["wid"], "attributes": ["product"],
        "attribute_cardinality": {"prodcut": "many"}})

    assert [p["code"] for p in problems] == ["unknown_id"]
    assert "prodcut" in problems[0]["message"]


def test_an_identity_key_is_not_an_attribute_and_cannot_be_made_plural():
    """⚠️ KEYS DECIDE SAMENESS. A plural identity key would mean one entity is two, and the
    existing rule already forbids a name being both — so this refuses through that rule
    rather than through a second one written here."""
    problems = _entity_problems({
        "keys": ["wid"], "attributes": ["product"],
        "attribute_cardinality": {"wid": "many"}})
    assert problems and problems[0]["code"] == "unknown_id"


def test_the_cell_must_be_an_object():
    problems = _entity_problems({
        "keys": ["wid"], "attributes": ["product"],
        "attribute_cardinality": ["product"]})
    assert [p["code"] for p in problems] == ["invalid_type"]


# ---------------------------------------------------------------------------
# 🔴 the reading rule
# ---------------------------------------------------------------------------

@pytest.fixture
def declared(tmp_path, monkeypatch, request):
    """A declaration of this test's own, read through the walk's own cached reader.

    ⛔ NOT THE BOX'S. `server/config/ontology/` is the owner's and gitignored; a case that
    read it would measure this machine.
    """
    def declare(entities):
        root = tmp_path / "ontology"
        root.mkdir(exist_ok=True)
        (root / "ledger_config.json").write_text(
            json.dumps({"entities": entities}), encoding="utf-8")

        import paths

        monkeypatch.setattr(paths, "config_path",
                            lambda *parts: str(tmp_path.joinpath(*parts)))
        # ⚠️ THE PRODUCT'S OWN FORGETTING, not a poke at the global (S-206). A fixture that
        # cleared the sentinel by hand would keep passing on the day the real reset stopped
        # clearing the other half.
        ledger_subgraph.reset_declaration_cache()
    # ⚠️ AND IT IS FORGOTTEN AGAIN ON THE WAY OUT. This cache is module state: a test that
    # left it holding a tmp_path declaration would hand the next one an answer from a file
    # that no longer exists. [[the-model-registries-come-back]] is the same posture.
    request.addfinalizer(ledger_subgraph.reset_declaration_cache)
    return declare


def _read(by_name, node_type="wafer"):
    """The walk's reading rule for ONE node, exercised through the real code path."""
    nodes = {"n1": {"id": "n1", "type": node_type, "depth": 0,
                    "node_kind": "entity", "label": "w"}}
    ledger_subgraph._apply_registrations(nodes, {"n1": by_name})
    return nodes["n1"]


def test_a_plural_name_comes_back_as_a_list_and_is_not_a_conflict(declared):
    """🔴 THE WHOLE ROUND. Two rows, two registrations, both true."""
    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product"],
                          "attribute_cardinality": {"product": "many"}}})

    node = _read({"product": [(1, "A"), (2, "B")]})

    assert node["attributes"]["product"] == ["A", "B"]
    assert node["attribute_conflicts"] == 0


def test_a_plural_name_is_a_list_even_when_it_holds_one_value(declared):
    """🔴 ONE SHAPE PER NAME. 「a list only when there are two」 would make a reader guess."""
    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product"],
                          "attribute_cardinality": {"product": "many"}}})

    assert _read({"product": [(1, "A")]})["attributes"]["product"] == ["A"]


def test_the_same_value_twice_is_one_value_not_two(declared):
    """⚠️ THE RULE THE CONFLICT COUNT ALREADY USED, kept: one fact stated twice is one
    fact. A registration rewritten unchanged must not grow the list."""
    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product"],
                          "attribute_cardinality": {"product": "many"}}})

    assert _read({"product": [(1, "A"), (2, "A"), (3, "B")]})["attributes"][
        "product"] == ["A", "B"]


def test_a_singular_name_behaves_exactly_as_it_does_today(declared):
    """⚠️ NO REGRESSION FOR EVERY NAME NOBODY DECLARED. Latest wins, and a disagreement is
    still counted rather than hidden (S-52 ③, ruling 124)."""
    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product", "lot_state"],
                          "attribute_cardinality": {"product": "many"}}})

    node = _read({"product": [(1, "A"), (2, "B")], "lot_state": [(1, "X"), (2, "Y")]})

    assert node["attributes"]["lot_state"] == "Y"
    assert node["attribute_conflicts"] == 1, "only the singular name disagrees"


def test_a_type_the_declaration_never_named_keeps_todays_reading(declared):
    """⚠️ AN UNREADABLE OR ABSENT DECLARATION MUST NOT CHANGE A WALK. The reader never
    raises, and 「no plural names」 is the answer that leaves everything as it was."""
    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product"],
                          "attribute_cardinality": {"product": "many"}}})

    node = _read({"product": [(1, "A"), (2, "B")]}, node_type="defect")

    assert node["attributes"]["product"] == "B"
    assert node["attribute_conflicts"] == 1


def test_the_version_does_not_have_to_be_spelled_by_the_node(declared):
    """⚠️ A NODE'S `type` IS BARE and the declaration is keyed with its version — the same
    fold `_declared_columns` makes, in the same direction."""
    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product"],
                          "attribute_cardinality": {"product": "many"}}})

    assert ledger_subgraph._declared_plural_attributes("wafer") == {"product"}
    assert ledger_subgraph._declared_plural_attributes("wafer@1") == {"product"}


def test_one_read_answers_both_questions(declared):
    """🔴 KEY ORDER AND CARDINALITY COME FROM ONE READ. Two cached reads could answer from
    two revisions of one file — a node labelled by one and valued by another."""
    declared({"wafer@1": {"keys": ["wid", "slot"], "attributes": ["product"],
                          "attribute_cardinality": {"product": "many"}}})

    assert ledger_subgraph._entity_key_order is None, "nothing has read it yet"

    assert ledger_subgraph._declared_plural_attributes("wafer") == {"product"}

    # The key order arrived in the SAME read, without a second open().
    assert ledger_subgraph._entity_key_order["wafer"] == ["wid", "slot"]


# ---------------------------------------------------------------------------
# 🔴 the envelope says which names are lists (판정 327 (2))
# ---------------------------------------------------------------------------
#: The walk harness the neighbouring suites use, so this scores the REAL response rather
#: than a hand-built one.
import uuid                                                        # noqa: E402
from datetime import datetime, timezone                            # noqa: E402

import ledger_explorer                                             # noqa: E402

NOW = datetime(2026, 9, 13, 1, 0, tzinfo=timezone.utc)
SUBJECT = ledger_explorer.entity_id("wafer", {"wid": "W1"})


def _registration(number, value, *, at=None):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="wafer", subject_keys={"wid": "W1"},
        predicate="register", object_kind=None,
        object_payload={"qualifiers": {"product": value}}, occurred_at=at or NOW,
        source_who="wafer", source_translator_ver="v1", source_raw_ref=f"row:{number}",
        supersedes=None, source_event_id=str(uuid.UUID(int=900 + number)),
        source_event_state="source_molecule")


def _walk(atoms):
    return ledger_subgraph.subgraph(
        SUBJECT, ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=1)


def test_the_response_says_which_names_are_lists(declared):
    """🔴 THE SERVER CARRIES IT, because the declaration's reader is the server (판정 327).
    `attributes[name]` is a list for some names and a scalar for the rest, and a screen that
    had to fetch and parse the ontology to know which would be a second reader of the same
    file — free to disagree with this one."""
    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product"],
                          "attribute_cardinality": {"product": "many"}}})

    body = _walk([_registration(1, "A"),
                  _registration(2, "B", at=NOW.replace(hour=2))])

    assert body["attribute_cardinality"] == {"wafer": {"product": "many"}}
    node = next(n for n in body["nodes"] if n["id"] == SUBJECT)
    assert node["attributes"]["product"] == ["A", "B"]
    assert node["attribute_conflicts"] == 0


def test_the_envelope_uses_the_declarations_own_word_and_its_own_default(declared):
    """⚠️ ONE VOCABULARY. Only `many` names appear and absent means `one` — exactly what an
    absent cell means in the declaration. A second spelling for the same idea is how the
    two start disagreeing."""
    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product"]}})

    body = _walk([_registration(1, "A")])

    assert body["attribute_cardinality"] == {}
    assert setup_bundle.ATTRIBUTE_CARDINALITY_MANY == "many"
    node = next(n for n in body["nodes"] if n["id"] == SUBJECT)
    assert node["attributes"]["product"] == "A", "a name nobody declared many is a scalar"


# ---------------------------------------------------------------------------
# 🔴 S-206 — a declaration the operator just activated is the one the walk reads
# ---------------------------------------------------------------------------

def test_the_walk_keeps_answering_from_the_declaration_it_already_read(declared):
    """⚠️ THE CACHE IS DELIBERATE. Re-reading the file per walk would open it on every
    request; what must be true is that something FORGETS it, not that nothing caches it."""
    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product"]}})
    assert ledger_subgraph._declared_plural_attributes("wafer") == frozenset()

    _redeclare_product_as_many()

    assert ledger_subgraph._declared_plural_attributes("wafer") == frozenset(), (
        "nothing asked it to forget, so the old answer is the right answer")


def test_activating_a_declaration_makes_the_walk_read_it_again(declared):
    """🔴 THE ROUND. An operator declares `many`, presses activate -- which is a
    SYSTEM_RELOAD -- and the walk answered `one` until somebody restarted the server.
    「빌드했다고 로드된 건 아니다」: the declaration changed and the thing that answers
    questions about it did not."""
    import system_reload

    declared({"wafer@1": {"keys": ["wid"], "attributes": ["product"]}})
    assert ledger_subgraph._declared_plural_attributes("wafer") == frozenset()

    _redeclare_product_as_many()
    system_reload.reload_local_process_cache()

    assert ledger_subgraph._declared_plural_attributes("wafer") == {"product"}


def test_forgetting_drops_both_halves_of_the_one_read(declared):
    """🔴 ONE READ FILLS BOTH, SO ONE FORGETTING EMPTIES BOTH. Clearing only the sentinel
    would leave the plural map from the previous revision standing beside a key order from
    the new one -- exactly the split 「one read」 exists to prevent."""
    declared({"wafer@1": {"keys": ["wid", "slot"], "attributes": ["product"],
                          "attribute_cardinality": {"product": "many"}}})
    assert ledger_subgraph._declared_plural_attributes("wafer") == {"product"}
    assert ledger_subgraph._entity_key_order["wafer"] == ["wid", "slot"]

    ledger_subgraph.reset_declaration_cache()

    assert ledger_subgraph._entity_key_order is None
    assert ledger_subgraph._entity_plural_attributes == {}


def test_the_reload_seat_names_this_cache_beside_the_others():
    """⛔ SCORED ON THE SOURCE. The defect is an OMISSION -- a cache that is simply not in
    the list -- and an omission leaves no failing call to catch. Every neighbour in that
    list is there because the same thing went wrong once."""
    import inspect

    import system_reload

    body = inspect.getsource(system_reload.reload_local_process_cache)
    assert "reset_declaration_cache()" in body


def _redeclare_product_as_many():
    """Rewrite the SAME file the fixture pointed the reader at."""
    import json as _json

    import paths

    path = paths.config_path("ontology", "ledger_config.json")
    with io_open(path, "w") as handle:
        handle.write(_json.dumps({"entities": {"wafer@1": {
            "keys": ["wid"], "attributes": ["product"],
            "attribute_cardinality": {"product": "many"}}}}))


def io_open(path, mode):
    import io as _io

    return _io.open(path, mode, encoding="utf-8")
