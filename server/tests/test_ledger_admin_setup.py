# -*- coding: utf-8 -*-
"""The admin setup lane's write gate — ruling R-2026-08-15-M.

WHY THIS FILE EXISTS AND WHY IT IS THIS SIZE
---------------------------------------------
R-2026-08-14-J put a proportionality rule in force: mutation-grade rigour is for risky
places only, and「원장 쓰기 게이트」is named as one of them. Everything checked here is
either a WRITE GATE (what a declaration must satisfy before it is allowed to change what
the ledger will accept) or the DRY RUN'S ZERO-WRITE GUARANTEE. Nothing here checks how a
screen renders a list.

THE TWO-SIDED ASSERTION THAT MATTERS MOST
-------------------------------------------
`test_a_config_word_joins_the_gate_without_moving_the_pinned_code_set` is the whole of
R-M ④ in one test: the merged set grows, `PREDICATES` does NOT, and the gate's signature
check judges the new word by the same machinery. One side alone would be worthless -
"the config word works" is compatible with the fixed v0 test having been quietly widened.
"""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import gate, vocabulary                                  # noqa: E402
import ledger_admin                                                  # noqa: E402


# --------------------------------------------------------------------------- fixtures
def signature(**overrides):
    """A COMPLETE ontology signature. Tests remove exactly the field under test.

    Written positively rather than as a pile of partial dicts so that "what a complete
    signature is" is stated once here and can be compared against
    `vocabulary.SIGNATURE_FIELDS` - which the first test below actually does.
    """
    entry = {
        "label_ko": "폐기",
        "layer": "ontology",
        "status": "active",
        "since": 5,
        "subject": ["Wafer"],
        "object": {"kind": "value", "required": ["reason", "run_uid"]},
        "qualifiers": [],
        "traversable": None,
        "direction": None,
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def extension(tmp_path, monkeypatch):
    """Point the vocabulary's config layer at a scratch file.

    `extension_path` is monkeypatched rather than `paths.CONFIG_DIR`, because the
    operator's real config directory holds files five processes read and a test that
    could write there would be one typo from editing the box's live vocabulary.
    """
    path = str(tmp_path / "ledger_vocabulary.json")
    monkeypatch.setattr(vocabulary, "extension_path", lambda: path)
    monkeypatch.setattr(ledger_admin, "vocabulary_path", lambda: path)
    vocabulary.reset_cache()
    yield path
    vocabulary.reset_cache()


def write_extension(path, predicates):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "predicates": predicates}, handle, ensure_ascii=False)
    vocabulary.reset_cache()


def codes(violations):
    return [v["code"] for v in violations]


# ------------------------------------------------- ② signature completeness (the gate)
def test_the_declared_signature_fields_are_the_ones_the_checker_enforces():
    """The list and the enforcement are the same list, not two lists that agree today."""
    complete = signature()
    for field in vocabulary.SIGNATURE_FIELDS:
        partial = dict(complete)
        partial.pop(field, None)
        assert "signature_incomplete" in codes(
            vocabulary.check_predicate_declaration("scrapped", partial)), (
            f"removing '{field}' - which SIGNATURE_FIELDS declares required - did not "
            f"refuse the declaration")


def test_traversable_must_be_CHOSEN_and_null_is_a_choice():
    """🔴 R-M ②'s sharpest edge: a defaulted tri-state is a declaration nobody made.

    The two halves are the point. An ABSENT key is refused - otherwise "I did not think
    about the walk" and "the walk must never fetch this" would be the same declaration.
    An EXPLICIT null is accepted, because `None` is a real state (`observed` carries it
    deliberately) and refusing it would leave the third state unreachable from the screen.
    """
    absent = signature()
    absent.pop("traversable")
    violations = vocabulary.check_predicate_declaration("scrapped", absent)
    assert codes(violations) == ["signature_incomplete"]
    assert violations[0]["field"] == "traversable"

    explicit_null = signature(traversable=None)
    assert vocabulary.check_predicate_declaration("scrapped", explicit_null) == []

    explicit_false = signature(traversable=False)
    assert vocabulary.check_predicate_declaration("scrapped", explicit_false) == []


def test_a_value_object_with_nothing_required_is_refused():
    """A `value` object's ONLY enforcement point is `required` (R-2026-08-13-D)."""
    violations = vocabulary.check_predicate_declaration(
        "scrapped", signature(object={"kind": "value"}))
    assert "signature_incomplete" in codes(violations)
    assert any(v["field"] == "object.required" for v in violations)


def test_an_undeclared_entity_type_cannot_be_minted_from_a_declaration():
    violations = vocabulary.check_predicate_declaration(
        "scrapped", signature(subject=["Cassette"]))
    assert "undeclared_entity_type" in codes(violations)


# ------------------------------------------------------- ① canonical stays out of reach
def test_the_canonical_layer_has_no_door_from_a_declaration():
    violations = vocabulary.check_predicate_declaration(
        "asserted", signature(layer="canonical"))
    assert "canonical_layer_forbidden" in codes(violations)


@pytest.mark.parametrize("name", ["register", "pin", "same_as", "observed"])
def test_a_code_loaded_word_cannot_be_redefined_from_a_declaration(name):
    violations = vocabulary.check_predicate_declaration(name, signature())
    assert "duplicate_predicate" in codes(violations)


def test_a_second_traversable_word_is_refused_because_the_walk_cannot_run_it():
    """Not squeamishness: `ledger_trace.traversal_predicate` raises on two of them.

    Accepting this declaration would take the trace screen down at the NEXT request,
    while the operator held a green save message.
    """
    violations = vocabulary.check_predicate_declaration(
        "scrapped", signature(traversable=True, direction="subject_to_object"))
    assert codes(violations) == ["traversable_true_unavailable"]
    assert "derived_from" in violations[0]["detail_ko"]


# ------------------------------------------ ④ the merged set, and the pin that holds
def test_a_config_word_joins_the_gate_without_moving_the_pinned_code_set(extension):
    """🔴 THE TWO-SIDED ASSERTION. Both halves, or neither means anything."""
    before_code = set(vocabulary.PREDICATES)
    before_all = set(vocabulary.all_predicates())

    write_extension(extension, {"scrapped": signature()})

    # (a) the pinned code set did NOT move - the v0 fixed test still pins what it pinned
    assert set(vocabulary.PREDICATES) == before_code
    # (b) the merged set DID
    assert set(vocabulary.all_predicates()) == before_all | {"scrapped"}
    assert vocabulary.predicate_origin("scrapped") == "config"
    assert vocabulary.predicate_origin("observed") == "code"
    # (c) and the GATE reads the merged one
    assert vocabulary.is_declared("scrapped")
    assert "scrapped" in vocabulary.emittable()


def test_the_gate_judges_a_config_word_by_the_SAME_signature_machinery(extension):
    write_extension(extension, {"scrapped": signature()})

    good = vocabulary.check_signature("scrapped", "Wafer", "value",
                                      {"reason": "chipping", "run_uid": "r1"})
    assert good == []

    missing = vocabulary.check_signature("scrapped", "Wafer", "value",
                                         {"reason": "chipping"})
    assert missing and "run_uid" in missing[0]

    wrong_subject = vocabulary.check_signature("scrapped", "Lot", "value",
                                               {"reason": "x", "run_uid": "r1"})
    assert wrong_subject and "does not accept subject type" in wrong_subject[0]


def test_a_config_word_reaches_the_walk_declaration_the_same_way(extension):
    """`traversable: false` means「도달은 하되 통과 금지」for a config word too."""
    write_extension(extension, {"scrapped": signature(traversable=False)})
    assert "scrapped" in vocabulary.walk_predicates()
    assert "scrapped" not in vocabulary.traversable_predicates()
    assert vocabulary.check_walk_declaration() == []


def test_a_malformed_extension_degrades_to_code_only_and_SAYS_SO(extension):
    """Never raises. Five processes import this module; a stray comma must not stop them.

    But the degradation is REPORTED - a vocabulary that quietly shrank would refuse every
    atom of a config word with `undeclared_vocabulary` and nothing would say why.
    """
    with open(extension, "w", encoding="utf-8") as handle:
        handle.write('{"predicates": {"scrapped": {"layer": "canonical"}}}')
    vocabulary.reset_cache()

    assert set(vocabulary.all_predicates()) == set(vocabulary.PREDICATES)
    status = vocabulary.extension_status()
    assert status["ok"] is False
    assert status["error"] and "scrapped" in status["error"]


# --------------------------------------------------------- ③ retirement, never deletion
def test_there_is_no_delete_route_anywhere_under_admin_ledger():
    """R-M ③ as a route-table fact, not a promise in a docstring."""
    from main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/admin/ledger"):
            assert "DELETE" not in (getattr(route, "methods", None) or set()), (
                f"{path} offers DELETE; a registered predicate can never be deleted - "
                f"atoms are already lying in the ledger under that word")


def test_retirement_stops_emission_and_leaves_reading_alone(extension):
    write_extension(extension, {"scrapped": signature()})
    assert "scrapped" in vocabulary.emittable()

    ledger_admin.retire_predicate("scrapped", superseded_by="observed")
    vocabulary.reset_cache()

    entry = vocabulary.all_predicates()["scrapped"]
    assert entry["status"] == "retired"
    assert entry["superseded_by"] == "observed"
    # Emission stops...
    assert "scrapped" not in vocabulary.emittable()
    refused = vocabulary.check_signature("scrapped", "Wafer", "value",
                                         {"reason": "x", "run_uid": "r"})
    assert refused and "RETIRED" in refused[0]
    # ...and reading does not: the word is still declared, so atoms written under it
    # still resolve to a signature rather than becoming unreadable.
    assert vocabulary.is_declared("scrapped")
    assert vocabulary.signature("scrapped") is not None


def test_a_code_loaded_word_cannot_be_retired_from_the_screen(extension):
    write_extension(extension, {"scrapped": signature()})
    with pytest.raises(ValueError):
        ledger_admin.retire_predicate("observed")


# ------------------------------------------------- SQL identifiers (a NEW risk, today)
@pytest.mark.parametrize("bad", [
    "wafer; DROP TABLE ledger_events",
    'wafer" , (SELECT 1) AS "x',
    "Wafer",                    # unquoted identifiers fold to lower case in PostgreSQL
    "wafer id",
    "1_wafer",
    "",
])
def test_an_identifier_that_would_land_in_an_interpolation_is_refused(bad):
    """The fetches build SQL with f-strings, so this is the ONLY place to say no.

    An identifier is not a bind parameter, so the check cannot be moved downstream. Until
    today a human typed these into a file; from today an HTTP request does.
    """
    assert codes(ledger_admin.check_identifier(bad, "columns.wafer")) \
        == ["invalid_identifier"]


def test_a_legal_identifier_passes():
    assert ledger_admin.check_identifier("base_wafer_id", "columns.wafer") == []


# ------------------------------------------------- ⑥ the save cannot skip the dry run
def test_the_token_binds_a_save_to_the_EXACT_declaration_that_was_previewed():
    """🔴 What makes「드라이런 없는 저장 버튼은 만들지 않는다」a server rule.

    Not "the client is expected to call dry-run first" - a client that skips it, or that
    edits one character afterwards, produces a token the server does not accept.

    ⚠️ Scope, stated so nobody reads more into this test than it proves: the fingerprint
    is a pure function of the declaration, so a caller who reimplements the hash can
    produce a valid token without ever previewing. That is deliberate circumvention by a
    caller who already holds the strict admin token, not the accidental skip this gate
    exists to prevent - and a server-issued nonce, the only thing that would close it,
    would intermittently refuse legitimate saves the moment there is more than one worker
    process.
    """
    declaration = signature()
    token = ledger_admin.declaration_token("predicate", "scrapped", declaration)

    assert ledger_admin.declaration_token("predicate", "scrapped", declaration) == token
    edited = signature(label_ko="폐기됨")
    assert ledger_admin.declaration_token("predicate", "scrapped", edited) != token
    assert ledger_admin.declaration_token("predicate", "other", declaration) != token
    assert ledger_admin.declaration_token("source", "scrapped", declaration) != token


def test_key_order_does_not_change_the_token():
    """A screen that serialises its form in a different order must not be refused."""
    a = {"label_ko": "x", "layer": "ontology", "since": 5}
    b = {"since": 5, "layer": "ontology", "label_ko": "x"}
    assert (ledger_admin.declaration_token("predicate", "n", a)
            == ledger_admin.declaration_token("predicate", "n", b))


def test_the_refusal_codes_are_closed():
    """A code invented at a call site is a refusal the screen cannot render."""
    with pytest.raises(ValueError):
        ledger_admin.violation("something_went_wrong", None, "…")
    for code in vocabulary.DECL_REFUSALS:
        assert code in ledger_admin.REFUSAL_CODES, (
            f"vocabulary can emit '{code}' but the route's closed set does not carry it, "
            f"so the client would meet a code its vocabulary does not contain")


# ------------------------------------------------------ the save writes, and backs up
def test_saving_twice_leaves_a_backup_because_config_has_no_history(extension):
    """Config files are gitignored by design (R-2026-08-13-G): the copy IS the undo."""
    first = ledger_admin.save_predicate("scrapped", signature())
    assert first["backup"] == ""            # nothing to back up on the first write
    assert first["replaced"] is False

    second = ledger_admin.save_predicate("scrapped", signature(label_ko="폐기 v2"))
    assert second["replaced"] is True
    assert os.path.exists(second["backup"])
    with open(second["backup"], "r", encoding="utf-8") as handle:
        assert json.load(handle)["predicates"]["scrapped"]["label_ko"] == "폐기"


def test_the_FIRST_save_on_a_fresh_box_does_not_poison_the_empty_default(extension):
    """Regression. The default document was shallow-copied, so the first save on a box
    with no file wrote the new predicate INTO the module constant - and every later
    "there is no file" default in that process already contained it. Invisible on any box
    that already has the file, which is every box that has ever been tested by hand."""
    ledger_admin.save_predicate("scrapped", signature())
    assert ledger_admin._EMPTY_VOCABULARY["predicates"] == {}, (
        "the first save mutated the module-level empty document")

    os.remove(extension)
    ledger_admin.save_predicate("other_word", signature(label_ko="다른 낱말"))
    with open(extension, "r", encoding="utf-8") as handle:
        assert list(json.load(handle)["predicates"]) == ["other_word"], (
            "a save after the file was removed resurrected the previous predicate")


def test_the_save_never_leaves_a_half_written_file(extension, monkeypatch):
    """A partially written vocabulary is the worst outcome: the loader would then refuse
    the whole file and the gate would refuse every atom of every config word."""
    ledger_admin.save_predicate("scrapped", signature())
    original = open(extension, "r", encoding="utf-8").read()

    real_replace = os.replace

    def explode(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", explode)
    with pytest.raises(OSError):
        ledger_admin.save_predicate("scrapped", signature(label_ko="새 이름"))
    monkeypatch.setattr(os, "replace", real_replace)

    assert open(extension, "r", encoding="utf-8").read() == original


# ---------------------------------------------------------------- the dry run's config
def test_the_candidate_config_carries_only_the_source_under_preview():
    """A broken NEIGHBOUR must not be able to refuse this preview - and vice versa."""
    declaration = {"occurred_at_column": "t", "occurred_at_timezone": "Asia/Seoul",
                   "subject_types": ["Wafer"]}
    cfg = ledger_admin.candidate_config("my_table", declaration)
    assert list(cfg["sources"]) == ["my_table"]


def test_the_previews_translator_version_is_the_one_a_real_run_would_stamp():
    """The atoms a preview shows carry the SAME provenance string a real run writes.

    If they did not, the preview would be showing atoms that are not the atoms - the
    definition of the fake preview the brief forbids.
    """
    from ledger import config as ledger_config

    declaration = copy.deepcopy(
        ledger_config.load()["sources"].get("lot_event")
        or {"occurred_at_column": "t", "occurred_at_timezone": "Asia/Seoul",
            "subject_types": ["Wafer"]})
    cfg = ledger_admin.candidate_config("lot_event", declaration)
    live = ledger_config.load()
    assert (ledger_config.translator_version(cfg, "lot_event")
            == ledger_config.translator_version(live, "lot_event"))


# ------------------------------------------------ the gate's counters survive a preview
def test_a_preview_does_not_move_the_processs_refusal_counters():
    """🔴 Otherwise「거절이 쌓이나」answers yes because somebody LOOKED at a declaration.

    The counters are what `/health` and the heartbeat report, and they are process
    aggregates on purpose.
    """
    gate.reset_counters()
    gate.refuse("live_source", gate.REFUSE_NO_IDENTITY, "a real refusal")
    before = gate.refusals()

    with gate.captured() as captured:
        gate.refuse("preview_source", gate.REFUSE_NOT_TRUE_ALONE, "a previewed refusal")

    assert gate.refusals() == before, "the preview's refusal leaked into the process"
    assert captured["refusals"] == {("preview_source", "not_true_alone"): 1}
    assert ("preview_source", "not_true_alone") not in gate.refusals()
    gate.reset_counters()


def test_a_capture_that_raises_still_reports_what_it_counted():
    """A refusal is a fact whether or not the caller caught the exception."""
    gate.reset_counters()
    handle = {}
    with pytest.raises(gate.MoleculeRefused):
        with gate.captured() as handle:
            with gate.building_molecule("preview_source"):
                gate.refuse("preview_source", gate.REFUSE_ATOMICITY, "boom")
    assert handle["refusals"] == {("preview_source", "atomicity_violation"): 1}
    assert gate.refusals() == {}
