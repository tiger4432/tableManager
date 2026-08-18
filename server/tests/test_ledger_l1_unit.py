# -*- coding: utf-8 -*-
"""Ledger slice 1 - everything provable without a database.

🔴 EVERY GUARD IN THIS FILE HAS BEEN MADE TO GO RED.
`test_every_guard_has_been_seen_to_fail` at the bottom re-injects the defect each guard
exists for and asserts the guard raises. It also asserts the NUMBER of injections it
ran, because `all(...)` over an empty sequence is vacuously true and a harness that
iterates nothing reports every test green under every injection - which happened on
another lane in this same session. A count is the only thing that cannot be faked by an
empty loop.
"""
import contextlib
import os
import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import config as ledger_config          # noqa: E402
from ledger import store as ledger_store            # noqa: E402
from ledger import envelope, gate, schema, uuid7, vocabulary   # noqa: E402

WHEN = datetime(2026, 5, 3, 2, 17, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _clean_counters():
    gate.reset_counters()
    yield
    gate.reset_counters()


def source_cfg(**overrides):
    cfg = {
        "occurred_at_column": "event_time",
        "occurred_at_format": "%Y-%m-%d %H:%M:%S",
        "occurred_at_timezone": "UTC",
        "subject_types": ["Lot", "Wafer"],
        "register_entity_types": ["Lot", "Wafer"],
        "list_separator": ":",
        "columns": {"row_identity": "business_key_val", "lot": "lot",
                    "event_type": "event_type", "parent_lot": "parent_lot",
                    "child_lot": "child_lot", "slots": "slot_numbers",
                    "wafers": "wafer_ids", "equipment": "equipment"},
        "vocabulary": {
            "split": {"lineage": "parent_child", "slot_pairing": "slot_preserving"},
            "merge": {"lineage": "parent_child", "slot_pairing": "shared_wafer"},
            "track_in": {"lineage": "none", "slot_pairing": "none"},
        },
    }
    cfg.update(overrides)
    return cfg


def full_cfg(**overrides):
    return {"version": 1, "sources": {"lot_event": source_cfg(**overrides)}}


def row(lot, event_type="split", parent_lot=None, child_lot=None, slots="", wafers="",
        event_time="2026-05-03 02:17:00", identity=None):
    return {"row_identity": identity or f"{lot}|{event_type}|{event_time}",
            "lot": lot, "event_type": event_type, "parent_lot": parent_lot,
            "child_lot": child_lot, "slots": slots, "wafers": wafers,
            "event_time": event_time}



# ------------------------------------------------------------------------- vocabulary
def test_v0_vocabulary_is_exactly_seven_words():
    """The brief fixed v0 at seven. It is NINE now, and this is where that is written.

    🔴 THE NAME OF THIS TEST IS DELIBERATELY UNCHANGED. `vocabulary.py` says adding a
    word "is a ruling, and the test is where the ruling has to be written down" - so the
    test that guarded seven is the test that has to record why there are nine, rather
    than a new test appearing beside a quietly relaxed old one.

    THE RULING (product owner, 2026-08-14, `SCENARIO_CONSOLE_BRIEF` §0-bis + board §
    "가상 소스 범위 확장"): `processed_with` and `has_param` are opened because the need
    was demonstrated, not anticipated - the system could record that a package had a void
    and could not record ANYTHING about the conditions that produced it, so every causal
    question died at the first hop. `processed_with` was already RESERVED by design §4.2;
    `has_param` is its recipe-side counterpart and arrives with it because a process run
    that names a recipe revision nobody can read the setpoints of explains nothing.

    THE SECOND RULING, THE SAME DAY (`PHYSICS_ONTOLOGY_SETUP` §2-bis, commit `4dff09f`):
    `transferred` - every movement of a chip, in one word. It arrived by REPLACING two
    earlier drafts of the same fact, and the reason is worth keeping because the count is
    what caught it. Draft 1 modelled DT as a step a wafer passes through
    (`processed_with` with `step: DT`); draft 2 split it into per-stage load/consume
    claims. Both would have needed re-uttering. The generalisation subsumes them: a
    movement is one event kind, selection is that event's EXISTENCE, and residual is a
    fold of inflow minus outflow. 🔴 It also ABSORBS the reserved `consumed`, which is
    therefore still unregistered - consumption is a transfer OUT, and a separate word is
    justified only when destruction WITHOUT movement is demonstrated.

    All three are `since: 2`, so the slice a word entered in stays queryable, and the
    count stays a control: an ELEVENTH word still turns this red. It did - see below.

    THE ELEVENTH WORD (ruling R-2026-08-14-D, 2026-08-14): `observed`.
    `MI_LEDGER_SCHEMA_PROPOSAL` §6-bis had reserved the need in prose since the night
    before; what closed it was a MEASUREMENT rather than an argument. The structure census
    (`3202ac7`) showed 91,756 voids and 10,421 delaminations living in source tables only,
    every finding kind answering `in_ledger: false`, and no defect edge anywhere on the
    type graph - the ledger had no way to say「관측했다」at all. So the word is registered
    with `since: 3`, which keeps the slice it entered in queryable exactly as slice 2's
    three do.

    THE TWELFTH WORD (`measured`, 2026-08-15): the sibling is now opened because the
    selection investigation has real metrology atoms to consume. It is deliberately
    distinct from `processed_with`: that word now says only STEP + RECIPE occurrence,
    while `measured` describes a separate physical-quantity measurement with its own
    method/run evidence. `measured_as` remains a UI category only. It entered in
    slice 4 so the vocabulary still records when the need became demonstrated.
    """
    assert set(vocabulary.PREDICATES) == {
        "register", "pin", "same_as",
        "derived_from", "slot_map", "has_wafer", "frame_confirmed",
        "processed_with", "has_param", "transferred",
        "observed", "measured", "assigned_to_experiment",
    }
    # The seven that were v0 are still `since: 1`; nothing was renumbered to make the
    # arithmetic tidy. A word's slice is evidence about when the system learned to say it.
    assert {name for name, sig in vocabulary.PREDICATES.items() if sig["since"] == 1} == {
        "register", "pin", "same_as",
        "derived_from", "slot_map", "has_wafer", "frame_confirmed",
    }
    assert {name for name, sig in vocabulary.PREDICATES.items() if sig["since"] == 3} == {
        "observed",
    }
    assert {name for name, sig in vocabulary.PREDICATES.items() if sig["since"] == 4} == {
        "measured",
    }
    assert {name for name, sig in vocabulary.PREDICATES.items() if sig["since"] == 5} == {
        "assigned_to_experiment",
    }


def test_every_declared_word_carries_a_label():
    """`label_ko` is the ENFORCEMENT POINT for the label declaration.

    This project's standing rule is that a declaration field has an enforcement point or
    it does not exist (`ledger/config.py`, ruling R-2026-08-13-D). `GET /api/ledger/
    structure` renders the vocabulary as a picture whose labels are Korean, and it reads
    them from here rather than from a map beside the renderer — a second list of the
    vocabulary is how a word added here shows up on screen as a bare identifier while
    every other test stays green.

    The reader falls back to the raw name rather than raising, so this test is the ONLY
    thing that turns red for an unlabelled word. That is deliberate: a missing label must
    degrade the screen to English, never blank it.
    """
    unlabelled = [name for name, sig in vocabulary.PREDICATES.items()
                  if not str(sig.get("label_ko") or "").strip()]
    assert unlabelled == [], (
        f"predicate(s) {unlabelled} carry no `label_ko`; the structure view would render "
        f"them as bare identifiers")
    unlabelled = [name for name, entry in vocabulary.ENTITY_TYPES.items()
                  if not str(entry.get("label_ko") or "").strip()]
    assert unlabelled == [], (
        f"entity type(s) {unlabelled} carry no `label_ko`")


def test_a_value_object_is_checked_against_its_declared_required_fields():
    """A `value` payload used to be structurally unchecked. `required` is the bite.

    Both directions, because a check that only ever accepts is the decoy declaration
    ruling R-2026-08-13-D killed: a well-formed run lands, and one that forgot which step
    it was about is refused BY NAME.
    """
    good = {"step": "BONDING", "recipe": "SYN-RCP-BOND-R4"}
    assert not vocabulary.check_signature("processed_with", "Wafer", "value", good)

    missing_step = dict(good)
    missing_step.pop("step")
    violations = vocabulary.check_signature("processed_with", "Wafer", "value",
                                            missing_step)
    assert violations and "step" in violations[0]

    # 🔴 PRESENCE, NOT TRUTHINESS. A setpoint of 0 is a setpoint, and a truthiness test
    # would refuse it - which is the shape of bug that only ever bites on the values
    # somebody actually cared about.
    assert not vocabulary.check_signature(
        "has_param", "Recipe", "value",
        {"param": "purge_delay_s", "value": 0, "unit": "s"})
    assert not vocabulary.check_signature(
        "has_param", "Recipe", "value",
        {"param": "vacuum_assist", "value": False, "unit": "bool"})


def test_measured_contract_requires_evidence_and_never_encodes_missing_as_a_value():
    recorded = {"metric": "film_thickness", "unit": "um", "method": "MI",
                "state": "recorded", "value": 71.2, "run_uid": "MI:SYN:001"}
    assert vocabulary.check_signature("measured", "Wafer", "value", recorded) == []
    assert vocabulary.check_signature(
        "measured", "Wafer", "value",
        {"metric": "warpage", "unit": "um", "method": "MI",
         "state": "not_performed", "bonding_leg": "DOE-A"}) == []

    no_value = dict(recorded)
    no_value.pop("value")
    assert any("requires field 'value'" in item for item in
               vocabulary.check_signature("measured", "Wafer", "value", no_value))

    no_run = dict(recorded)
    no_run.pop("run_uid")
    assert any("requires field(s) run_uid" in item for item in
               vocabulary.check_signature("measured", "Wafer", "value", no_run))

    for state in ("missing", "not_performed", "unknown"):
        payload = {"metric": "film_thickness", "unit": "um", "method": "MI",
                   "state": state}
        assert vocabulary.check_signature("measured", "Wafer", "value", payload) == []
        payload["value"] = None
        assert any("forbids field 'value'" in item for item in
                   vocabulary.check_signature("measured", "Wafer", "value", payload))

    assert any("requires state to be one of" in item for item in
               vocabulary.check_signature(
                   "measured", "Wafer", "value",
                   {"metric": "film_thickness", "unit": "um", "method": "MI",
                    "state": "absent"}))


def test_recipe_identity_carries_the_revision():
    """A revision is a new subject, so `rev` is key material and a bare id is refused."""
    assert vocabulary.check_subject_keys("Recipe", {"recipe": "SYN-RCP-BOND"})
    assert not vocabulary.check_subject_keys(
        "Recipe", {"recipe": "SYN-RCP-BOND", "rev": "4"})
    # ... and the two revisions are two DIFFERENT subjects, which is the whole point:
    # rev4's evidence cannot be destroyed by rev5 arriving.
    assert ({"recipe": "SYN-RCP-BOND", "rev": "4"}
            != {"recipe": "SYN-RCP-BOND", "rev": "5"})
    assert vocabulary.requires_register("Recipe"), (
        "Recipe is an ISSUED entity - a revision is registered, not constructed")


def test_bonding_leg_is_an_experiment_claim_value_not_an_entity():
    keys = {"wafer": "SYN-CX-BW-006", "bonding_leg": "HBM-B_LOW-P"}
    assert vocabulary.check_subject_keys("Wafer", keys)
    assert "WaferLeg" not in vocabulary.ENTITY_TYPES
    assert not vocabulary.requires_register("WaferLeg")
    assert vocabulary.check_signature(
        "assigned_to_experiment", "Wafer", "value",
        {"experiment_type": "bonding_leg", "unit_id": keys["bonding_leg"],
         "map_ref": {"table": "bonding_map", "base": keys["wafer"]}}) == []
    assert vocabulary.check_signature(
        "assigned_to_experiment", "Wafer", "value",
        {"experiment_type": "bonding_leg", "unit_id": keys["bonding_leg"]})
    assert vocabulary.check_signature(
        "observed", "Wafer", "value",
        {"finding_kind": "void", "method": "sat", "run_uid": "SYN-RUN",
         "bonding_leg": keys["bonding_leg"]}) == []


def test_projection_state_words_can_never_be_written():
    for word in ("resolved", "contested", "candidate", "unresolvable", "pinned"):
        violations = vocabulary.check_signature(word, "Lot", "value", {"x": 1})
        assert violations and "PROJECTION" in violations[0]


def test_signature_refuses_a_concatenated_subject_key():
    """Design section 3's own incident: a joined key collapses when a piece is blank."""
    assert vocabulary.check_subject_keys("Lot", "CL-2601-006")
    assert vocabulary.check_subject_keys("Lot", {"lot": ""})
    assert vocabulary.check_subject_keys("Lot", {})
    assert not vocabulary.check_subject_keys("Lot", {"lot": "CL-2601-006"})


def test_signature_refuses_a_predicate_pointed_at_the_wrong_type():
    assert vocabulary.check_signature(
        "has_wafer", "Lot", "entity_ref",
        envelope.entity_ref("Lot", {"lot": "A"}, slot="01"))


def test_signature_requires_every_declared_qualifier():
    ok = vocabulary.check_signature(
        "slot_map", "Lot", "entity_ref",
        envelope.entity_ref("Lot", {"lot": "B"}, **{"from": "01", "to": "02",
                                                    "wafer": "W1"}))
    assert ok == []
    missing = vocabulary.check_signature(
        "slot_map", "Lot", "entity_ref",
        envelope.entity_ref("Lot", {"lot": "B"}, **{"from": "01", "to": "02"}))
    assert missing and "wafer" in missing[0]


def test_register_is_the_only_predicate_with_no_object():
    assert vocabulary.check_signature("register", "Lot", None, None) == []
    assert vocabulary.check_signature("register", "Lot", "value", {"a": 1})
    assert vocabulary.check_signature("has_wafer", "Lot", None, None)


# ------------------------------------------------------------------------------ uuid7
def test_uuid7_is_strictly_monotonic_and_the_check_is_not_vacuous():
    values = [uuid7.uuid7() for _ in range(20000)]
    assert uuid7.assert_monotonic(values) == 20000
    assert len(set(values)) == 20000


def test_uuid7_stays_monotonic_when_the_clock_goes_backwards(monkeypatch):
    """A machine's clock stepping back must not make the WATERMARK step back.

    A cursor that reads `WHERE id > :last` stops advancing forever the moment an id
    smaller than one already seen is written, and the rows behind it are never
    translated. Time going backwards is a machine problem; that is a data problem.
    """
    ticks = iter([5_000_000_000_000_000] * 3 + [1_000_000_000_000_000] * 50)
    monkeypatch.setattr(uuid7.time, "time_ns", lambda: next(ticks))
    values = [uuid7.uuid7() for _ in range(40)]
    assert uuid7.assert_monotonic(values) == 40


def test_uuid7_embeds_the_record_time():
    before = int(datetime.now(timezone.utc).timestamp() * 1000)
    value = uuid7.uuid7()
    assert value.version == 7
    assert abs(uuid7.timestamp_ms(value) - before) < 5000


# ------------------------------------------------------------- payload type preservation
def test_integer_zero_and_string_zero_stay_distinct():
    """Design section 3's `object` row: the render audit that could not tell them apart."""
    before = {"a": 0, "b": "0", "c": False, "d": None, "e": 0.0}
    assert envelope.assert_type_preserving(before, dict(before)) == 5
    with pytest.raises(AssertionError):
        envelope.assert_type_preserving(before, {**before, "a": "0"})
    with pytest.raises(AssertionError):
        envelope.assert_type_preserving(before, {**before, "c": 0})
    with pytest.raises(AssertionError):
        envelope.assert_type_preserving(before, {**before, "d": ""})


def test_a_payload_that_cannot_survive_the_round_trip_is_refused_not_coerced():
    with pytest.raises(envelope.PayloadNotPreservable):
        envelope.freeze_payload({"x": float("nan")})
    with pytest.raises(envelope.PayloadNotPreservable):
        envelope.freeze_payload({"x": {1: "int key"}})
    with pytest.raises(envelope.PayloadNotPreservable):
        envelope.freeze_payload({"x": datetime.now()})


def test_identity_mirrors_the_columns_the_unique_index_compares():
    """If `schema.DEDUPE_COLUMNS` grows, this tuple has to grow with it or the
    translator's in-memory duplicate suppression stops matching the database's."""
    atom = envelope.Atom(subject_type="Lot", subject_keys={"lot": "A"},
                         predicate="register", occurred_at=WHEN, source_who="x",
                         source_translator_ver="v", source_raw_ref="r")
    assert len(atom.identity()) == len(schema.DEDUPE_COLUMNS)


# ------------------------------------------------------------------------------- config
def test_a_source_with_no_declared_time_column_is_refused_at_load():
    """Risk 2 of the brief: arrival time may never stand in for world time."""
    with pytest.raises(ledger_config.LedgerConfigError) as exc:
        ledger_config.validate(full_cfg(occurred_at_column=""))
    assert "occurred_at_column" in str(exc.value)

    with pytest.raises(ledger_config.LedgerConfigError):
        ledger_config.validate(full_cfg(occurred_at_timezone=""))


def test_a_misspelled_slot_pairing_strategy_is_refused_at_load():
    """Silently falling back to 'none' would ship a ledger with no slot chain."""
    cfg = full_cfg()
    cfg["sources"]["lot_event"]["vocabulary"]["split"]["slot_pairing"] = "slot_preserveing"
    with pytest.raises(ledger_config.LedgerConfigError):
        ledger_config.validate(cfg)


def test_the_retired_singular_subject_type_is_refused_and_the_message_names_its_heir():
    """Ruling R-2026-08-13-D. A config written before it must not load QUIETLY.

    `subject_type` (singular) reached no atom, so accepting it and ignoring it would be
    the very failure the ruling names - a declaration with no consequence. The error is
    therefore required to carry the fix, because an operator meeting it has a file in
    front of them and needs to know what to type instead.
    """
    cfg = full_cfg()
    source = cfg["sources"]["lot_event"]
    source.pop("subject_types")
    source["subject_type"] = "Lot"                      # exactly the retired spelling
    with pytest.raises(ledger_config.LedgerConfigError) as exc:
        ledger_config.validate(cfg)
    message = str(exc.value)
    assert "subject_types" in message, "the message does not name the replacement key"
    assert "undeclared_subject_type" in message, (
        "the message does not say the new list is ENFORCED, which is the whole point of "
        "the rename")


def test_a_subject_type_outside_the_vocabulary_is_refused_at_load():
    """Adding an entity type is a vocabulary decision (`vocabulary.ENTITY_TYPES`), not
    something a source config may do on its own."""
    cfg = full_cfg()
    cfg["sources"]["lot_event"]["subject_types"] = ["Lot", "Reticle"]
    with pytest.raises(ledger_config.LedgerConfigError) as exc:
        ledger_config.validate(cfg)
    assert "Reticle" in str(exc.value)

    cfg["sources"]["lot_event"]["subject_types"] = []
    with pytest.raises(ledger_config.LedgerConfigError):
        ledger_config.validate(cfg)


def test_the_shipped_sample_config_validates():
    path = os.path.join(os.path.dirname(__file__), "..", "config", "sample",
                        "ledger_config.json.sample")
    cfg = ledger_config.load(os.path.abspath(path))
    assert "lot_event" in cfg["sources"]
    assert ledger_config.translator_version(cfg, "lot_event").startswith("lot_event/")


def test_missing_live_config_falls_back_to_nested_sample(tmp_path):
    sample_dir = tmp_path / "sample"
    sample_dir.mkdir()
    shipped = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "config", "sample",
        "ledger_config.json.sample"))
    nested = sample_dir / "ledger_config.json.sample"
    shutil.copyfile(shipped, nested)

    cfg = ledger_config.load(str(tmp_path / "ledger_config.json"))

    assert os.path.normcase(cfg["__origin__"]) == os.path.normcase(str(nested))


def test_the_translator_version_changes_when_a_RULE_changes():
    """The `slot_preserving` judgement is auditable only if the atoms say which
    convention made them."""
    base = ledger_config.translator_version(full_cfg(), "lot_event")
    other = full_cfg()
    other["sources"]["lot_event"]["vocabulary"]["split"]["slot_pairing"] = "shared_wafer"
    assert ledger_config.translator_version(other, "lot_event") != base


# ------------------------------------------------------------- declared world time
#
# 🔴 PRODUCT OWNER RULING 2026-08-13: fab timestamps are LOCAL (Asia/Seoul), written
# ISO 8601 with the `T` separator. The declaration was `UTC` before that date.
#
# Every rule here is written as a NAMED CHECK rather than inline in a test, because the
# fault-injection round at the bottom runs the SAME check against a deliberately wrong
# `store.parse_occurred_at` and requires it to go red. A timezone rule that has never
# been seen to fail is the most expensive kind of sentence in this file: a wrong instant
# is still a well-formed one, so every atom looks fine and nothing downstream complains.
#
# 🔴 WHO STILL READS THIS RULE, MEASURED 2026-08-18 — AND IT IS NOT THE v2 RUNTIME.
# `LotEventTranslator` used to be the caller and was deleted; the v2 runtime never calls
# `parse_occurred_at` at all. The one remaining non-test caller in the tree is the lag
# probe, `ledger/observability.py:131-132`. So this block is filed under OBSERVABILITY,
# not under v2: labelling it a v2 contract is what would get it swept away by the next
# v2 refactor, and the lag probe would silently lose its only cover.
# (`observability.py` also reads `DEFAULT_OCCURRED_AT_FORMAT` from `ledger/config.py`, so
# whoever retires that module has to re-home this call site rather than follow it down.)

SEOUL = "Asia/Seoul"
ISO_T = "%Y-%m-%dT%H:%M:%S"


def _instant_and_offset(value):
    """`(UTC wall clock, utcoffset)`.

    BOTH are asserted everywhere below, because the two ways of getting the offset rule
    wrong fail differently and only one of them moves the instant:
      * re-localising an already-offset value (`replace(tzinfo=...)`) SHIFTS it;
      * converting it (`astimezone(...)`) is a no-op on the instant and only shows up in
        the offset the value carries.
    Checking the instant alone would leave the second one invisible.
    """
    return value.astimezone(timezone.utc).replace(tzinfo=None), value.utcoffset()


def _check_naive_text_takes_the_declared_zone():
    got = ledger_store.parse_occurred_at("2026-08-13T13:45:00", ISO_T, SEOUL)
    assert got is not None, "the declared shape did not parse at all"
    when, offset = _instant_and_offset(got)
    assert when == datetime(2026, 8, 13, 4, 45), (
        f"13:45 naive under a declared Asia/Seoul is 04:45 UTC; got {when}. "
        f"Nine hours is the whole defect this ruling exists to fix.")
    assert offset == timedelta(hours=9)


def _check_an_explicit_offset_is_not_localised_a_second_time():
    """The SAME-ZONE case. Deliberately kept, deliberately not trusted alone.

    A source string already at `+09:00` under a declared `Asia/Seoul` is where a double
    shift is INVISIBLE - re-localising it lands on the same instant. That is exactly why
    the cross-zone check below exists; this one only proves the common case is not
    mangled.
    """
    got = ledger_store.parse_occurred_at("2026-08-13T13:45:00+09:00", ISO_T, SEOUL)
    assert got is not None
    when, offset = _instant_and_offset(got)
    assert when == datetime(2026, 8, 13, 4, 45)
    assert offset == timedelta(hours=9)


def _check_an_offset_that_disagrees_with_the_declaration_wins():
    """🔴 THE DISCRIMINATING CASE. `+00:00` text under a declared `Asia/Seoul`.

    The source has already said which instant it is. Re-applying the declared zone here
    moves it nine hours; converting it silently rewrites the offset the source chose.
    Both are caught.
    """
    got = ledger_store.parse_occurred_at("2026-08-13T04:45:00+00:00", ISO_T, SEOUL)
    assert got is not None
    when, offset = _instant_and_offset(got)
    assert when == datetime(2026, 8, 13, 4, 45), (
        f"an explicit +00:00 must be honoured, not re-read as Asia/Seoul; got {when}")
    assert offset == timedelta(0), (
        f"the source's own offset must be carried through unchanged; got {offset}")


def _check_an_unreadable_time_is_refused_by_name():
    for text in ("not a timestamp", "2026-13-45T99:99:99", "", None,
                 "2026-08-13X13:45:00"):
        got = ledger_store.parse_occurred_at(text, ISO_T, SEOUL)
        assert got is None, (
            f"{text!r} was given the instant {got!r} instead of being refused. `None` is "
            f"the refusal signal; anything else here is a guess wearing a datetime.")


def _check_the_space_spelling_reads_as_the_same_instant():
    """The fixture's transport, not a second format.

    Production emits `T`; `table_config.json` stores this column as TEXT with a space so
    it sorts lexicographically. RFC 3339 section 5.6 makes them one shape, and the reader
    admits both - so a declaration naming either spelling reads a box holding the other.
    """
    with_t = ledger_store.parse_occurred_at("2026-08-13T13:45:00", ISO_T, SEOUL)
    with_space = ledger_store.parse_occurred_at("2026-08-13 13:45:00", ISO_T, SEOUL)
    assert with_space is not None, (
        "the space spelling was refused, so a development box holding the trace fixture "
        "translates nothing at all")
    assert _instant_and_offset(with_space) == _instant_and_offset(with_t)


def test_naive_source_text_is_read_in_the_declared_zone():
    _check_naive_text_takes_the_declared_zone()


def test_an_explicit_offset_is_honoured_and_the_declared_zone_is_not_reapplied():
    _check_an_explicit_offset_is_not_localised_a_second_time()
    _check_an_offset_that_disagrees_with_the_declaration_wins()


def test_a_time_that_cannot_be_read_is_refused_never_guessed():
    _check_an_unreadable_time_is_refused_by_name()


def test_the_T_and_space_spellings_are_one_shape_in_two_transports():
    _check_the_space_spelling_reads_as_the_same_instant()


def test_the_shipped_declaration_carries_the_product_owner_ruling():
    """The ruling lives in `ledger_config.json.sample`, so the sample is where it can
    rot. Pinning it here means a silent revert to `UTC` fails a test instead of shifting
    every atom by nine hours."""
    path = os.path.join(os.path.dirname(__file__), "..", "config", "sample",
                        "ledger_config.json.sample")
    cfg = ledger_config.load(os.path.abspath(path))
    declared = cfg["sources"]["lot_event"]
    assert declared["occurred_at_timezone"] == "Asia/Seoul"
    assert declared["occurred_at_format"] == "%Y-%m-%dT%H:%M:%S"



# ------------------------------------------------------------------------------- gate
def test_the_gate_refuses_the_WHOLE_molecule_not_the_bad_atom():
    """A half-translated event is worse than an untranslated one: it looks complete."""
    good = envelope.Atom(
        subject_type="Lot", subject_keys={"lot": "A"}, predicate="register",
        occurred_at=WHEN, source_who="s", source_translator_ver="v",
        source_raw_ref="r", molecule_ref="m", derivation="first_sight")
    bad = envelope.Atom(
        subject_type="Lot", subject_keys={"lot": ""}, predicate="register",
        occurred_at=WHEN, source_who="s", source_translator_ver="v",
        source_raw_ref="r", molecule_ref="m", derivation="first_sight")
    kept, report = gate.screen_molecule("lot_event", [good, bad], {"first_sight"},
                                        {"Lot"}, molecule_ref="m")
    assert kept == []
    assert report["refused"] and report["reason"] == gate.REFUSE_NO_IDENTITY
    assert gate.atoms_lost()["lot_event"] == 2


def test_an_atom_whose_derivation_was_never_declared_is_refused():
    """Atomicity check 3 in mechanical form: only a rule somebody declared may speak."""
    atom = envelope.Atom(
        subject_type="Lot", subject_keys={"lot": "A"}, predicate="register",
        occurred_at=WHEN, source_who="s", source_translator_ver="v",
        source_raw_ref="r", molecule_ref="m", derivation="i_made_this_up")
    kept, report = gate.screen_molecule("lot_event", [atom], {"first_sight"},
                                        {"Lot"}, molecule_ref="m")
    assert kept == [] and report["reason"] == gate.REFUSE_UNDECLARED_DERIVATION


def test_an_atom_with_no_raw_ref_is_refused():
    """Atomicity check 4: nothing points back at the source, so it cannot be re-uttered."""
    atom = envelope.Atom(
        subject_type="Lot", subject_keys={"lot": "A"}, predicate="register",
        occurred_at=WHEN, source_who="s", source_translator_ver="v",
        source_raw_ref="", molecule_ref="m", derivation="first_sight")
    kept, report = gate.screen_molecule("lot_event", [atom], {"first_sight"},
                                        {"Lot"}, molecule_ref="m")
    assert kept == [] and report["reason"] == gate.REFUSE_NO_RAW_REF


def test_a_naive_occurred_at_is_refused():
    atom = envelope.Atom(
        subject_type="Lot", subject_keys={"lot": "A"}, predicate="register",
        occurred_at=datetime(2026, 5, 3, 2, 17), source_who="s",
        source_translator_ver="v", source_raw_ref="r", molecule_ref="m",
        derivation="first_sight")
    kept, report = gate.screen_molecule("lot_event", [atom], {"first_sight"},
                                        {"Lot"}, molecule_ref="m")
    assert kept == [] and report["reason"] == gate.REFUSE_MISSING_OCCURRED_AT


def _equipment_atom():
    """A WELL FORMED atom about `Equipment`. Every other check in the gate passes it -
    `register` accepts Equipment, the identity is complete, the envelope is whole - so
    the only thing that can refuse it is the source's declared extension. That is what
    makes the pair of tests below a test of THIS check and not of some other one."""
    return envelope.Atom(
        subject_type="Equipment", subject_keys={"equipment": "EQP-07"},
        predicate="register", occurred_at=WHEN, source_who="s",
        source_translator_ver="v", source_raw_ref="r", molecule_ref="m",
        derivation="first_sight")


def test_an_atom_about_an_undeclared_subject_type_is_refused_BY_NAME():
    """Ruling R-2026-08-13-D, the refusing arm. The atom is true; the objection is that
    nobody reviewed this source speaking about equipment."""
    kept, report = gate.screen_molecule("lot_event", [_equipment_atom()],
                                        {"first_sight"}, {"Lot", "Wafer"},
                                        molecule_ref="m")
    assert kept == []
    assert report["reason"] == gate.REFUSE_UNDECLARED_SUBJECT_TYPE
    assert gate.refusals()[("lot_event", gate.REFUSE_UNDECLARED_SUBJECT_TYPE)] == 1
    assert "Equipment" in " ".join(report["violations"])


def test_the_same_atom_LANDS_when_the_source_declares_that_type():
    """⚠️ THE OTHER ARM, and it is not decoration.

    A refusal guard tested only on the refusing side cannot be told apart from one that
    refuses everything - or from one that never parsed at all. This lane's own sibling
    shipped exactly that on 2026-08-13. So the identical atom is run through the identical
    gate with `Equipment` added to the declaration, and it must LAND: the check reads the
    list, rather than merely having one.
    """
    atom = _equipment_atom()
    kept, report = gate.screen_molecule("lot_event", [atom], {"first_sight"},
                                        {"Lot", "Wafer", "Equipment"}, molecule_ref="m")
    assert kept == [atom]
    assert not report["refused"] and report["reason"] is None
    assert gate.refusals() == {}, "a passing atom was counted as a refusal"


# ------------------------------------------- ruling R-2026-08-13-H-bis 1: one grammar
#
# 🔴 THESE ARE NOT INJECTION-HARNESS ENTRIES ON PURPOSE. Both shared harnesses at the
# bottom of this file catch `AssertionError` and read it as "the guard fired", so a guard
# whose whole claim is "an exception is raised" cannot state that claim there - a round
# that raised the WRONG exception would report success. `pytest.raises(<the exact type>)`
# is the spelling that can tell those two apart, and every assertion about the exception
# is made on `caught.value` AFTER the block, because a statement written after the raising
# call inside it would never execute.


def test_a_gate_refusal_inside_a_molecule_scope_UNWINDS_rather_than_returning():
    """Ruling R-H-bis 1. The refusal used to leave as `([], report)`.

    `[]` is the shape ruling R-H executed one module over: `or []`, a bare `extend` and an
    ignored return all absorb it. Now the gate refuses through `gate.refuse` like every
    other refusal site, so inside a molecule scope it unwinds - and the counting that used
    to happen beside the `return` still happens, because `refuse` counts BEFORE it raises.
    """
    gate.reset_counters()
    reached_the_line_after_the_call = []
    with pytest.raises(gate.MoleculeRefused) as caught:
        with gate.building_molecule("lot_event"):
            kept, _report = gate.screen_molecule(
                "lot_event", [_equipment_atom()], {"first_sight"}, {"Lot", "Wafer"},
                molecule_ref="m")
            reached_the_line_after_the_call.extend(kept or [])   # the swallow, unwritable

    assert caught.value.reason == gate.REFUSE_UNDECLARED_SUBJECT_TYPE
    assert caught.value.source == "lot_event"
    assert reached_the_line_after_the_call == [], (
        "execution continued past the refusal, so a merge expression could still swallow "
        "it - which is the 2026-08-13 defect in a new place")
    assert gate.refusals()[("lot_event", gate.REFUSE_UNDECLARED_SUBJECT_TYPE)] == 1, (
        "the refusal unwound without being counted - `molecules_refused` and the "
        "breakdown beside it would then disagree in the OTHER direction")
    assert gate.atoms_lost()["lot_event"] == 1


def test_a_refusal_and_a_silence_are_no_longer_SPELLED_alike():
    """⚠️ THE OTHER ARM, and it is what stops the ruling from being over-applied.

    A molecule that legitimately produced no atoms - a `track_in` whose wafer column is
    blank throughout - still leaves by RETURNING `([], report)`, un-refused and uncounted.
    That was always the intent and it is now the only `[]` the gate emits on its own
    account: with the refusal raising, the two outcomes that used to be typed identically
    can finally be told apart by a caller that looks at neither the report nor the docs.
    """
    gate.reset_counters()
    with gate.building_molecule("lot_event"):
        kept, report = gate.screen_molecule("lot_event", [], {"first_sight"}, {"Lot"},
                                            molecule_ref="m")
    assert kept == [] and not report["refused"] and report["reason"] is None
    assert gate.refusals() == {}, (
        "a molecule with nothing to say was counted as a refusal, which makes the refusal "
        "counter mean two different things")


def test_outside_a_molecule_scope_the_gate_still_refuses_by_RETURNING():
    """The double net, and the reason this change is not a contract break.

    `refuse` only counts when no molecule is open, so a caller that never opened a scope
    keeps the old pair rather than silently receiving atoms. It is the same degradation
    `gate.refuse` itself has had since R-H - one rule, not a second one for this call.
    """
    gate.reset_counters()
    assert not gate.molecule_is_open()
    kept, report = gate.screen_molecule("lot_event", [_equipment_atom()],
                                        {"first_sight"}, {"Lot", "Wafer"},
                                        molecule_ref="m")
    assert kept == [] and report["refused"]
    assert report["reason"] == gate.REFUSE_UNDECLARED_SUBJECT_TYPE
    assert gate.refusals()[("lot_event", gate.REFUSE_UNDECLARED_SUBJECT_TYPE)] == 1


# ------------------------------------- ruling R-2026-08-13-H-bis 3: the driver's scope


# --------------------------------- ruling R-2026-08-13-H-bis 2: no default for `reasons`
#
# 🔴 THE SUITE BEING GREEN PROVES NOTHING HERE. Every caller of `write_batch` in the tree
# already passes `reasons`, so the default could come back tomorrow and nothing else in
# this repository would notice. These two call it the way a caller who FORGOT would.


def test_write_batch_has_no_default_for_reasons():
    """Ruling R-H-bis 2, read off the signature.

    Keyword-only as well as undefaulted: `reasons` sits behind two integer parameters with
    defaults, so positionally it is one miscount away from being handed `incomplete`.
    """
    import inspect
    parameter = inspect.signature(ledger_store.LedgerStore.write_batch).parameters["reasons"]
    assert parameter.default is inspect.Parameter.empty, (
        "the default is back. A caller who says nothing about refusals would again "
        "advance `molecules_refused` with no names beside it")
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_a_write_that_FORGETS_reasons_fails_loudly_and_writes_nothing():
    """The same rule exercised as a call, because a signature can be satisfied and then
    undone by a `reasons or {}` in the body - which is exactly what used to be there.

    `engine=None` is deliberate: both refusals below have to happen BEFORE any connection
    is taken, so an engine that cannot produce one is the proof that nothing was written.
    An `AttributeError` here would mean the check runs too late.
    """
    store = ledger_store.LedgerStore(None)
    argv = ("lot_event", "v1", [], {"event_time": "2026-05-03 02:17:00"}, 1)

    with pytest.raises(TypeError) as omitted:
        store.write_batch(*argv)
    assert "reasons" in str(omitted.value)

    # 🔴 AND AN EXPLICIT `None` IS REFUSED TOO. Removing the default while the body still
    # read `reasons or {}` would leave the decoy one keystroke away - the ruling says the
    # only legitimate empty breakdown is an explicit `{}` from a run that refused nothing.
    with pytest.raises(TypeError) as explicit_none:
        store.write_batch(*argv, reasons=None)
    assert "H-bis" in str(explicit_none.value), (
        "the message does not name the ruling it enforces, so the next author reads it "
        "as a type nit and passes `{}` for a batch that DID refuse")


def test_refusal_reasons_are_a_closed_set():
    with pytest.raises(ValueError):
        gate.refuse("lot_event", "a_reason_i_invented", "detail")


def test_a_clean_translator_keeps_the_heartbeat_note_silent():
    """`None` is load-bearing: a line appearing in the note is itself the alarm."""
    assert gate.note() is None
    gate.refuse("lot_event", gate.REFUSE_UNDECLARED_VOCABULARY, "x")
    assert gate.note() is not None


# ------------------------------------------------------------------------ partitioning
def test_partition_bounds_are_utc_and_carry_an_explicit_offset():
    """A bound without an offset is read in the SESSION's timezone, so two processes
    with different TZ produce partitions that do not line up - and the row in the gap
    cannot be inserted at all."""
    sql = schema.create_partition_sql(datetime(2026, 12, 20, 23, 30, tzinfo=timezone.utc))
    assert "ledger_events_2026_12" in sql
    assert "'2026-12-01T00:00:00+00:00'" in sql
    assert "'2027-01-01T00:00:00+00:00'" in sql


def test_a_december_timestamp_rolls_the_year_not_month_thirteen():
    start, end, suffix = schema.month_bounds(
        datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc))
    assert (start.year, start.month) == (2026, 12)
    assert (end.year, end.month) == (2027, 1)
    assert suffix == "2026_12"


# ================================================================= FAULT INJECTION ROUND
#
# 🔴 Each entry re-introduces the defect one guard exists for and asserts the guard goes
# RED. A guard that has never been seen to fail is not a guard - it is a sentence.
#
# The list is DECLARED and its length is asserted. A harness that silently iterates
# nothing passes every injection vacuously; that is not a hypothetical, it happened on
# another lane in this session.

def _inject_uuid7_that_wraps():
    """The 2026-08-11 incident, exactly: a key generator that wraps."""
    values = [uuid.UUID(int=i % 3) for i in range(10)]
    uuid7.assert_monotonic(values)


def _inject_uuid7_that_repeats():
    same = uuid.UUID(int=42)
    uuid7.assert_monotonic([same, same])


def _inject_payload_stringifier():
    before = {"a": 0, "b": "0"}
    after = {k: str(v) for k, v in before.items()}
    envelope.assert_type_preserving(before, after)


def _inject_bool_for_int():
    envelope.assert_type_preserving({"a": 1}, {"a": True})


def _inject_null_as_empty_string():
    envelope.assert_type_preserving({"a": None}, {"a": ""})


def _inject_concatenated_subject_key():
    violations = vocabulary.check_subject_keys("Lot", "P_C")
    if not violations:
        raise AssertionError("a concatenated subject key was accepted")
    raise ValueError(violations[0])


def _inject_undeclared_predicate():
    violations = vocabulary.check_signature("scrapped", "Lot", "value", 1)
    if not violations:
        raise AssertionError("an undeclared predicate was accepted")
    raise ValueError(violations[0])


def _inject_slot_map_without_its_wafer():
    violations = vocabulary.check_signature(
        "slot_map", "Lot", "entity_ref",
        envelope.entity_ref("Lot", {"lot": "B"}, **{"from": "1", "to": "2"}))
    if not violations:
        raise AssertionError("a slot_map with no wafer was accepted - it is not true "
                             "standing alone, because nothing says which substrate moved")
    raise ValueError(violations[0])


def _inject_config_without_a_time_column():
    ledger_config.validate(full_cfg(occurred_at_column=""))


def _inject_config_with_a_misspelled_strategy():
    cfg = full_cfg()
    cfg["sources"]["lot_event"]["vocabulary"]["merge"]["slot_pairing"] = "shared_wafr"
    ledger_config.validate(cfg)


def _inject_config_with_the_retired_singular_subject_type():
    cfg = full_cfg()
    cfg["sources"]["lot_event"].pop("subject_types")
    cfg["sources"]["lot_event"]["subject_type"] = "Lot"
    ledger_config.validate(cfg)


def _inject_config_declaring_a_subject_type_nobody_minted():
    cfg = full_cfg()
    cfg["sources"]["lot_event"]["subject_types"] = ["Lot", "Reticle"]
    ledger_config.validate(cfg)


def _inject_atom_about_an_undeclared_subject_type():
    """Through the REAL gate, not through a re-implementation of its predicate.

    🔴 RETURNS NORMALLY when the gate accepts the atom, and that is not sloppiness - it
    is the only spelling both harnesses below can see. They catch `AssertionError` and
    call it a pass, so an injection that raises one when the guard FAILED reports success
    either way; falling off the end is what puts this guard's name in `silent`. Measured,
    not reasoned: with the membership test disabled this entry stayed green until it was
    written this way.
    """
    gate.reset_counters()
    kept, report = gate.screen_molecule("lot_event", [_equipment_atom()],
                                        {"first_sight"}, {"Lot", "Wafer"},
                                        molecule_ref="m")
    if kept or not report["refused"]:
        return                    # the guard accepted the defect - see above
    raise ValueError(report["reason"])


def _inject_undeclared_refusal_reason():
    gate.refuse("lot_event", "invented_on_the_spot", "detail")


def _inject_nan_payload():
    envelope.freeze_payload({"x": float("inf")})



# ------------------------------------------------------- wrong ways to read a timestamp
#
# 🔴 These are the injections the 2026-08-13 world-time ruling exists for. Each one is a
# COMPLETE, plausible implementation of `parse_occurred_at` that differs from the real
# one in exactly its timezone rule - not a stub that raises. That matters: a spot check
# passes under every one of them, which is why the rule needed a test at all.

def _read_without_applying_any_zone(raw, fmt):
    """Everything the real reader does EXCEPT the zone decision, so the wrong versions
    below differ from it in that decision and nothing else."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    for candidate in ledger_store._candidate_formats(fmt):
        try:
            return datetime.strptime(text, candidate)
        except (ValueError, TypeError):
            continue
    return None


def _wrong_relocalise_everything(raw, fmt, tzname):
    """THE DOUBLE SHIFT. `replace(tzinfo=...)` keeps the wall clock and throws away the
    offset the source stated, so `04:45+00:00` becomes `04:45+09:00` - nine hours early,
    and still a perfectly well-formed timestamp."""
    parsed = _read_without_applying_any_zone(raw, fmt)
    return None if parsed is None else parsed.replace(tzinfo=ledger_store._zone(tzname))


def _wrong_convert_instead_of_honouring(raw, fmt, tzname):
    """THE SILENT NO-OP. `astimezone` preserves the instant, so this one is invisible to
    any test that checks only the instant - it merely rewrites the offset the source
    chose and pretends the declaration was consulted."""
    parsed = _read_without_applying_any_zone(raw, fmt)
    if parsed is None:
        return None
    zone = ledger_store._zone(tzname)
    return parsed.astimezone(zone) if parsed.tzinfo else parsed.replace(tzinfo=zone)


def _wrong_naive_means_utc(raw, fmt, tzname):
    """The RETIRED declaration, in code: naive text read as UTC no matter what the
    source declared. This is the state every one of the atoms already in the ledger was
    written under."""
    parsed = _read_without_applying_any_zone(raw, fmt)
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _wrong_substitute_arrival_time(raw, fmt, tzname):
    """Design section 10 risk 1: an unreadable world time filled in with `now()`. Every
    atom is well formed and the ORDER of history is wrong."""
    parsed = _read_without_applying_any_zone(raw, fmt)
    if parsed is None:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ledger_store._zone(tzname))


def _wrong_only_the_declared_separator(raw, fmt, tzname):
    """The reader as it stood before this ruling: ONE `strptime` against the declared
    format. Under a `T` declaration it refuses every space-separated row - which on a
    development box is the entire source."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=ledger_store._zone(tzname))
    text = str(raw).strip()
    if not text:
        return None
    try:
        naive = datetime.strptime(text, fmt)
    except (ValueError, TypeError):
        return None
    return naive.replace(tzinfo=ledger_store._zone(tzname))


@contextlib.contextmanager
def _reader_replaced_by(wrong):
    """Swap the real reader for a wrong one on EVERY door that reaches it.

    🔴 THE DOOR LIST IS THE ASSERTION, not a formality. `lot_event_translator` did
    `from .store import parse_occurred_at`, so it held its own reference and patching only
    `ledger.store` would have left it running the correct code - an injection that changes
    nothing looks exactly like a guard that works (server-pm lessons file, 2026-08-11: "a
    wrapping key generator"). That module was deleted on 2026-08-18 and its door with it,
    so `ledger.store` is the only door today. Any future module that binds
    `parse_occurred_at` by value has to be added here or these injections go quietly inert.
    """
    doors = [(ledger_store, ledger_store.parse_occurred_at)]
    for module, _ in doors:
        module.parse_occurred_at = wrong
    try:
        yield
    finally:
        for module, original in doors:
            module.parse_occurred_at = original


def _time_injection(wrong, checks):
    """Run `checks` against a wrong reader. Raises `ValueError` when every one of them
    went red (the outcome being proven) and `AssertionError` naming the ones that stayed
    green (the guard is a sentence)."""
    def run():
        stayed_green = []
        with _reader_replaced_by(wrong):
            for check in checks:
                try:
                    check()
                except AssertionError:
                    continue
                stayed_green.append(check.__name__)
        if stayed_green:
            raise AssertionError(
                f"{wrong.__name__} changed nothing these checks could see: "
                f"{', '.join(stayed_green)}")
        raise ValueError(f"{wrong.__name__} was caught by all {len(checks)} check(s)")
    run.__name__ = wrong.__name__
    return run


#: (name, callable), paired with PRECISELY the checks each wrong reader must break. The
#: pairing is the assertion: `_wrong_naive_means_utc` does not touch a value that already
#: carries an offset, so listing the offset checks under it would be a claim this test
#: cannot support.
TIME_INJECTIONS = [
    ("declared zone re-applied over an explicit offset",
     _time_injection(_wrong_relocalise_everything,
                     [_check_an_offset_that_disagrees_with_the_declaration_wins])),
    ("explicit offset converted rather than honoured",
     _time_injection(_wrong_convert_instead_of_honouring,
                     [_check_an_offset_that_disagrees_with_the_declaration_wins])),
    ("naive text read as UTC instead of the declared zone",
     _time_injection(_wrong_naive_means_utc,
                     [_check_naive_text_takes_the_declared_zone])),
    ("arrival time substituted for an unreadable world time",
     _time_injection(_wrong_substitute_arrival_time,
                     [_check_an_unreadable_time_is_refused_by_name])),
    ("the space spelling of the declared shape refused",
     _time_injection(_wrong_only_the_declared_separator,
                     [_check_the_space_spelling_reads_as_the_same_instant])),
]


@pytest.mark.parametrize("name,injection", TIME_INJECTIONS,
                         ids=[n for n, _ in TIME_INJECTIONS])
def test_a_wrong_timestamp_reader_is_CAUGHT_and_not_merely_noticed(name, injection):
    """🔴 Distinguishes the two outcomes the shared harness below cannot.

    An `AssertionError` here means the wrong reader got past the checks; a `ValueError`
    means they refused it. Both are "an exception was raised", and telling them apart is
    the entire value of an injection round.
    """
    with pytest.raises((AssertionError, ValueError)) as caught:
        injection()
    assert not isinstance(caught.value, AssertionError), str(caught.value)


#: (name, callable). Each callable must RAISE. Declared as data so the count below is a
#: real assertion about coverage rather than a comment.
INJECTIONS = TIME_INJECTIONS + [
    ("uuid7 generator that wraps", _inject_uuid7_that_wraps),
    ("uuid7 generator that repeats", _inject_uuid7_that_repeats),
    ("payload rendered to strings", _inject_payload_stringifier),
    ("bool substituted for int", _inject_bool_for_int),
    ("NULL substituted for empty string", _inject_null_as_empty_string),
    ("concatenated subject key", _inject_concatenated_subject_key),
    ("undeclared predicate", _inject_undeclared_predicate),
    ("slot_map with no wafer", _inject_slot_map_without_its_wafer),
    ("config with no occurred_at column", _inject_config_without_a_time_column),
    ("config with a misspelled slot_pairing", _inject_config_with_a_misspelled_strategy),
    ("config with the retired singular subject_type",
     _inject_config_with_the_retired_singular_subject_type),
    ("config declaring a subject type outside the vocabulary",
     _inject_config_declaring_a_subject_type_nobody_minted),
    ("atom about an undeclared subject type",
     _inject_atom_about_an_undeclared_subject_type),
    ("refusal reason invented at a call site", _inject_undeclared_refusal_reason),
    ("non-finite number in a payload", _inject_nan_payload),
]

#: 14 built with this file + 5 added by the 2026-08-13 world-time ruling + 3 added by
#: ruling R-2026-08-13-D (the `subject_types` allow-list, its two config guards and the
#: gate refusal itself) + 2 by ruling R-2026-08-13-H (a refusal a caller swallows, and
#: the register memo a refused molecule used to keep) = 24, MINUS the 4 retired on
#: 2026-08-18 with `ledger/lot_event_translator.py`: unequal slot and wafer lists, a row
#: naming both sides of a pair, a fragment's refusal swallowed by its caller, and a
#: refused molecule keeping its register memo. All four drove the deleted translator; the
#: defects they injected have no reachable implementation left to inject into.
EXPECTED_INJECTIONS = 20


def test_every_guard_has_been_seen_to_fail():
    assert len(INJECTIONS) == EXPECTED_INJECTIONS, (
        "the injection list changed size. That is allowed - but the count is the only "
        "thing standing between this test and passing vacuously, so update it "
        "deliberately.")
    silent = []
    for name, injection in INJECTIONS:
        try:
            injection()
        except (AssertionError, ValueError, ledger_config.LedgerConfigError,
                envelope.PayloadNotPreservable):
            continue
        silent.append(name)
    assert not silent, (
        f"{len(silent)} guard(s) accepted the defect they exist to refuse: "
        f"{', '.join(silent)}")


@pytest.mark.parametrize("name,injection", INJECTIONS, ids=[n for n, _ in INJECTIONS])
def test_injection_goes_red_individually(name, injection):
    """The same injections, one test each - so a failure NAMES the guard that stopped
    working instead of reporting 'one of fourteen'."""
    with pytest.raises((AssertionError, ValueError,
                        ledger_config.LedgerConfigError,
                        envelope.PayloadNotPreservable)):
        injection()
