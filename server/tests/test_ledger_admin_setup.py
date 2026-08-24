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


def test_the_merged_view_notices_when_the_CODE_SET_is_swapped(extension):
    """🔴 REGRESSION. The merged view is derived from TWO mutable things — the extension
    file and this module's `PREDICATES` — and the first version keyed its cache on only the
    file.

    MEASURED failure: a suite that swaps the whole vocabulary also repoints
    `paths.CONFIG_DIR`, which dropped the merged view WHILE THE FAKE WAS INSTALLED. The
    rebuild cached the fake, the restore changed nothing the key could see, and the next
    test file got a vocabulary with zero traversable predicates and an error about a
    recursive CTE — three files away from the cause.

    It reads as a test-isolation problem and it is not: any process that swaps or reloads
    the code set at runtime would serve claims judged against a vocabulary it no longer has.
    """
    real = vocabulary.PREDICATES
    fake = {"only_word": {"label_ko": "x", "layer": "ontology", "status": "active",
                          "since": 1, "subject": ["Lot"], "object": None,
                          "qualifiers": [], "traversable": None, "direction": None}}
    try:
        vocabulary.PREDICATES = fake
        assert set(vocabulary.all_predicates()) == {"only_word"}, (
            "the merged view ignored a swapped code set")
        assert vocabulary.traversable_predicates() == ()
    finally:
        vocabulary.PREDICATES = real
    assert set(vocabulary.all_predicates()) == set(real), (
        "the merged view kept serving the fake after the code set was restored")
    assert vocabulary.traversable_predicates() == ("derived_from",)


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


# --------------------------- the source surface: declared tables, and raw editing
def test_a_source_on_an_undeclared_table_is_refused_at_SAVE_not_only_hidden(monkeypatch):
    """🔴 The picker rule needs an enforcement point or it is advice.

    Owner, 2026-08-15: the table list is `table_config`'s declared set only. Hiding
    undeclared tables from the picker would leave the rule advisory, because the RAW JSON
    editor is a second door into the same save. The reason is addressing rather than
    permission: a table the rest of the system does not declare has no key columns, no
    ingestion and no chain, so atoms about its rows name something nothing else can point
    at.
    """
    monkeypatch.setattr(ledger_admin, "declared_tables", lambda: ["void_obs"])
    violations = ledger_admin.check_source_declaration(None, "some_other_table", {})
    assert codes(violations) == ["undeclared_table"]
    assert "table_config.json" in violations[0]["detail_ko"]


def test_an_undeclared_table_is_NAMED_rather_than_silently_absent():
    """An operator who types a table they can SEE in the database and gets an empty list
    learns the screen is broken; one who gets a sentence learns what to do next. Same
    refusal ladder as everywhere else — the refusal names the next action."""
    import inspect

    body = inspect.getsource(ledger_admin.relations_view)
    assert "undeclared" in body
    assert "테이블 미등록" in body, (
        "the undeclared-table sentence changed - it is the operator's next action")


def test_raw_json_that_does_not_parse_is_refused_WITH_A_POSITION():
    """The three-step save is not relaxed for the raw path: no parse, no dry run, no save.
    A raw editor's most common failure is a stray comma, and 「JSON이 잘못됐다」 with no
    position sends the operator hunting through a 200-line blob."""
    parsed, refusal = ledger_admin.parse_raw_declaration(
        '{\n  "kind": "observation",\n  "oops": ,\n}')
    assert parsed is None
    assert refusal["code"] == "declaration_rejected"
    assert "3행" in refusal["detail_ko"], refusal["detail_ko"]

    parsed, refusal = ledger_admin.parse_raw_declaration('["not", "an", "object"]')
    assert parsed is None and refusal["code"] == "declaration_rejected"

    parsed, refusal = ledger_admin.parse_raw_declaration('{"kind": "observation"}')
    assert parsed == {"kind": "observation"} and refusal is None


def test_a_stale_base_is_refused_so_one_save_cannot_clobber_another(tmp_path):
    """🔴 CONCURRENCY IS ITS OWN PROBLEM AND HAS ITS OWN ANSWER.

    The strict admin token is AUTHENTICATION - it answers「are you allowed to write」and
    says nothing about「is the thing you edited still the thing on disk」. The dry-run
    token is a freshness check on the operator's OWN preview: two operators can each
    dry-run their own edit and both tokens are valid. Config files are gitignored by
    design, so a clobbered edit has no history to recover from.
    """
    path = str(tmp_path / "ledger_config.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "sources": {}}, handle)
    base = ledger_admin.file_fingerprint(path)

    assert ledger_admin.check_base(path, base) is None
    assert ledger_admin.check_base(path, None) is None      # the form sends none

    with open(path, "w", encoding="utf-8") as handle:       # somebody else saved
        json.dump({"version": 1, "sources": {"theirs": {}}}, handle)
    stale = ledger_admin.check_base(path, base)
    assert stale is not None and stale["code"] == "stale_base"

    # An absent file has a fingerprint of its own, so "created since you looked" is caught
    # rather than reading as unchanged.
    os.remove(path)
    assert ledger_admin.file_fingerprint(path) == "sha256:absent"
    assert ledger_admin.check_base(path, base)["code"] == "stale_base"


# ------------------------- the declaration map as an edit surface (owner, 08-15)
def test_every_declaration_row_says_whether_it_can_be_edited_and_by_what():
    """🔴 The structure view became an admin screen, so a row a human can see and the code
    cannot address is the last thing between the map and being its own edit surface.

    The identity was already there — `config` names the file, `name` names the key. What
    this asserts is the JUDGEMENT: most of these files have no save route yet, and a client
    cannot tell「no route exists」from「I have not built the form」by looking at a row.
    """
    import ledger_structure

    rows = [
        {"group": "translator", "config": "ledger_config.json", "name": "void_obs",
         "readable": True},
        {"group": "translator", "config": "ledger_config.json", "name": "syn_world",
         "readable": True, "declared": False},
        {"group": "axis", "config": "siblings_axes.json", "name": "bond_eqp",
         "readable": True},
        {"group": "translator", "config": "ledger_config.json", "name": None,
         "readable": False},
    ]
    handles = [ledger_structure._edit_handle(row) for row in rows]

    assert handles[0] == {"editable": True, "target": "source", "name": "void_obs",
                          "config": "ledger_config.json",
                          "route": "/admin/ledger/save",
                          "raw_route": "/admin/ledger/config/raw"}
    # 🔴 A DERIVED row must NOT get a key that goes nowhere. `syn_world` is a source the
    # ledger has atoms from and the config never declared - there is no config key to edit.
    assert handles[1]["editable"] is False and handles[1]["reason"] == "derived"
    assert "name" not in handles[1], "a derived row was handed an edit key"
    assert handles[2]["editable"] is False and handles[2]["reason"] == "no_route"
    assert handles[3]["editable"] is False and handles[3]["reason"] == "unreadable"
    for handle in handles[1:]:
        assert handle["detail_ko"], "a non-editable row must say WHY, not just refuse"


def test_a_predicate_row_is_editable_only_when_an_operator_declared_it():
    """The canonical layer has no door by ruling; a code-loaded ontology word is code."""
    import ledger_structure

    body = open(ledger_structure.__file__, encoding="utf-8").read()
    assert '"retire_route": "/admin/ledger/vocabulary/retire"' in body, (
        "the predicate row lost its retire route - retirement is the ONLY way a word "
        "leaves circulation, so the screen needs it addressable")
    assert '"reason": ("canonical" if' in body


def test_the_class_1_key_is_rendered_on_the_declaration_map():
    """A class-deciding key missing from the map is a declaration nothing SHOWS — the
    sibling of a declaration nothing reads, and this repo has shipped several today."""
    import ledger_structure

    body = open(ledger_structure.__file__, encoding="utf-8").read()
    assert "confirmed_derivations" in body, (
        "`confirmed_derivations` decides class 1 but does not appear on the declaration "
        "map, so an operator cannot see which declaration outranked which atom")


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
    assert os.path.basename(os.path.dirname(second["backup"])) == "backup"
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


# ------------------------------------------------------- root-key rollup (R-…-08-15-O)
def test_the_rollup_declaration_is_self_consistent():
    """A rollup that could only ever be right by accident is the decoy declaration again:
    a `root_key` that is not a key part of BOTH types produces a join on a jsonb field one
    side never carries, and THAT RETURNS ZERO EXTRA ROWS rather than an error — which is
    indistinguishable from the bug the declaration exists to fix."""
    assert vocabulary.check_entity_type_declaration() == []


def test_a_root_type_with_no_derived_types_rolls_up_to_itself_alone():
    """The helper must be safe to call for every subject, not only the one that has a
    derived type today — a reader that special-cased `Wafer` would break the day a second
    aggregation unit arrived."""
    assert vocabulary.rollup_subject_types("Lot") == ("Lot",)
    assert vocabulary.rollup_subject_types("Recipe") == ("Recipe",)


def test_composed_types_do_NOT_roll_up_even_though_their_keys_contain_the_root():
    """🔴 The reason the rollup is DECLARED and not inferred from key containment.
    `Die`'s keys are (wafer, x, y) — a superset of `Wafer`'s — so "rolls up if its keys
    contain yours" would fold every die atom into every wafer-scope read. There are 160M
    dies by construction."""
    assert "Die" not in vocabulary.rollup_subject_types("Wafer")
    assert vocabulary.ENTITY_TYPES["Die"].get("rolls_up_to") is None


@pytest.mark.parametrize("broken,expected", [
    ({"rolls_up_to": "Wafer"}, "only one of"),                      # no root_key
    ({"root_key": "wafer"}, "only one of"),                         # no rolls_up_to
    ({"rolls_up_to": "Nope", "root_key": "wafer"}, "not a declared entity type"),
    ({"rolls_up_to": "Wafer", "root_key": "nonesuch"}, "not one of its own key parts"),
    ({"rolls_up_to": "Recipe", "root_key": "wafer"}, "not a key part of its root"),
])
def test_a_broken_rollup_declaration_is_caught_by_name(monkeypatch, broken, expected):
    types = dict(vocabulary.ENTITY_TYPES)
    types["Trial"] = {"class": "issued", "keys": ["wafer", "trial"], "semi_ref": None,
                      "label_ko": "시험", **broken}
    monkeypatch.setattr(vocabulary, "ENTITY_TYPES", types)
    violations = vocabulary.check_entity_type_declaration()
    assert any(expected in v for v in violations), violations


def test_chained_rollups_are_refused_rather_than_silently_truncated(monkeypatch):
    """A reader follows ONE hop and stops, so a second hop's atoms would go missing with
    no error - the exact shape of the defect the rollup declaration exists to prevent,
    one level down.

    🔴 THE CHAIN IS BUILT OUT OF SYNTHETIC TYPES ON PURPOSE. An earlier version of this
    test hung the second hop off a real declared member, and the day that member was
    retired the test started failing for a reason that had nothing to do with chaining.
    A rule about SHAPE must be stated in shapes, not in today's membership list.
    """
    types = dict(vocabulary.ENTITY_TYPES)
    # Hop 1 - a legal rollup: rolls into a root that does not itself roll up.
    types["SynthMiddle"] = {"class": "issued", "keys": ["wafer", "middle"],
                            "semi_ref": None, "label_ko": "중간",
                            "rolls_up_to": "Wafer", "root_key": "wafer"}
    # Hop 2 - the same legal shape, but its root is hop 1. That is the chain.
    types["SynthLeaf"] = {"class": "issued", "keys": ["wafer", "leaf"], "semi_ref": None,
                          "label_ko": "말단", "rolls_up_to": "SynthMiddle",
                          "root_key": "wafer"}
    monkeypatch.setattr(vocabulary, "ENTITY_TYPES", types)

    violations = vocabulary.check_entity_type_declaration()
    chained = [v for v in violations if "chained rollups" in v]
    assert chained, violations
    assert "SynthLeaf" in chained[0], chained
    # Hop 1 alone is legal - the refusal is aimed at the chain, not at rolling up at all.
    assert not [v for v in violations if "SynthMiddle" in v and "chained" not in v], (
        "a single legal rollup was refused; the chain check is over-firing")


def test_the_read_paths_ask_for_the_rolled_up_set_not_a_single_type():
    """🔴 THE POINT OF THE RULING, asserted where it can actually regress: a
    wafer-scope reader must bind a LIST. Pinning one `subject_type` is what made 42
    `WaferLeg` atoms invisible and the screen say「본딩 조건 차이 없음」falsely.

    `ledger_journey` was the second source checked here and was deleted with the /journey
    route on 2026-08-25; its half of this guard goes with it rather than lingering as a
    test of nothing. `ledger_walk_contrast` still carries the same query shape, so the
    invariant is still asserted where it still exists.

    Asserted on the SQL text because these are hand-built query strings — there is no
    object to interrogate, and a future edit back to `= %(stype)s` is exactly the
    regression this guards."""
    from ledger_api import ledger_walk_contrast

    sources = [
        ("ledger_walk_contrast",
         open(ledger_walk_contrast.__file__, encoding="utf-8").read()),
    ]
    for name, text in sources:
        assert "subject_type = %(stype)s" not in text, (
            f"{name} still pins a single subject_type — WaferLeg atoms are invisible again")
        assert "subject_type = ANY(%(stypes)s)" in text, (
            f"{name} no longer asks for the rolled-up set")


def test_the_two_grain_arms_are_held_apart_by_the_leg_qualifier():
    """🔴 NOT a rollup site — the opposite, and the distinction is the whole defect.

    `_process_sql` and `_analysis_process_sql` fill ONE dict at TWO grains (component,
    keyed by wafer; analysis_unit, keyed by (wafer, bonding_leg)). If both arms accepted
    the same atom it would land in both buckets and be counted twice - no error, every
    downstream number confidently wrong.

    ⚠️ THE SEPARATOR MOVED, THE REQUIREMENT DID NOT. The two grains used to be two
    subject TYPES; the bonding leg is now a value carried in the claim payload, so all
    four arms legitimately pin the same `subject_type = 'Wafer'` and the split is made by
    the payload qualifier instead: the component arm must EXCLUDE legged evidence, the
    analysis arm must REQUIRE it. Asserting the retired type name here is what made this
    test die on a rename; asserting the exclusion/requirement pair is what actually
    guards against the double count.

    Guarded on the SQL text because these are hand-built strings: a future edit that
    "helpfully" widens either arm is exactly the regression to catch.
    """
    from ledger_api import ledger_selection

    pairs = [("process", ledger_selection._process_sql(),
              ledger_selection._analysis_process_sql()),
             ("measurement", ledger_selection._measurement_sql(),
              ledger_selection._analysis_measurement_sql())]

    for grain, component_arm, unit_arm in pairs:
        assert "NOT (object_payload ? 'bonding_leg')" in component_arm, (
            f"the {grain} component arm no longer excludes legged evidence - the same "
            f"atom now lands in both buckets and is counted twice")
        assert "object_payload->>'bonding_leg' = u.bonding_leg" in unit_arm, (
            f"the {grain} analysis arm no longer requires a bonding leg - it has stopped "
            f"being the other half of the split and reads component evidence too")
        for arm in (component_arm, unit_arm):
            assert "subject_type = 'Wafer'" in arm
            assert "ANY(%(stypes)s)" not in arm, (
                f"a {grain} two-grain arm was widened to the rollup set, merging what "
                f"these two queries exist to hold apart")


def test_the_rollup_helper_has_one_spelling_for_every_reader(monkeypatch):
    """Three copies of one fact is how a derived subject type comes to be visible to one
    query and invisible to the next.

    🔴 ASSERTED AS AN AGREEMENT BETWEEN THE TWO HELPERS, NOT AGAINST A MEMBER LIST.
    `ledger_trace.rollup_subject_types` is the query layer's adapter over
    `vocabulary.rollup_subject_types`, and what must hold is that they answer the SAME for
    every declared subject - whatever is declared today. A pinned literal list asserted
    the membership instead of the agreement, and died the day the membership changed
    while the two helpers were still in perfect agreement.

    The second half asserts the other half of "one spelling": the adapter CACHES, so a
    vocabulary that gains a derived type must reach it after `reset_walk_cache()` (which
    `/admin/reload-configs` calls) or the two spellings silently diverge until a restart.
    """
    import ledger_trace

    try:
        for subject in vocabulary.ENTITY_TYPES:
            assert (ledger_trace.rollup_subject_types(subject)
                    == vocabulary.rollup_subject_types(subject)), (
                f"the two rollup spellings disagree for '{subject}'")

        types = dict(vocabulary.ENTITY_TYPES)
        types["SynthDerived"] = {"class": "issued", "keys": ["wafer", "synth"],
                                 "semi_ref": None, "label_ko": "합성",
                                 "rolls_up_to": "Wafer", "root_key": "wafer"}
        monkeypatch.setattr(vocabulary, "ENTITY_TYPES", types)
        assert vocabulary.check_entity_type_declaration() == [], (
            "the fixture itself must be a legal declaration, or this asserts nothing")

        ledger_trace.reset_walk_cache()
        assert "SynthDerived" in ledger_trace.rollup_subject_types("Wafer"), (
            "the adapter kept a stale rollup set across reset_walk_cache() - a reload "
            "would leave the query layer reading a different vocabulary than this one")
        assert (ledger_trace.rollup_subject_types("Wafer")
                == vocabulary.rollup_subject_types("Wafer"))
    finally:
        ledger_trace.reset_walk_cache()


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
