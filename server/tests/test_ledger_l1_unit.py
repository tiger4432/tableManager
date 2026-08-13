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
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import config as ledger_config          # noqa: E402
from ledger import envelope, gate, schema, uuid7, vocabulary   # noqa: E402
from ledger.lot_event_translator import (           # noqa: E402
    LotEventTranslator, group_molecules, molecule_key)

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
        "subject_type": "Lot",
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


def translator(cfg=None):
    cfg = cfg or full_cfg()
    return LotEventTranslator(
        ledger_config.source_config(cfg, "lot_event"),
        ledger_config.translator_version(cfg, "lot_event"),
        ledger_config.declared_derivations(cfg, "lot_event"))


def translate_one(rows, cfg=None):
    """Group `rows` into ONE molecule, translate it, and screen it. `(atoms, report)`."""
    cfg = cfg or full_cfg()
    tr = translator(cfg)
    molecules = group_molecules(rows)
    assert len(molecules) == 1, f"expected one molecule, got {len(molecules)}"
    atoms, report = tr.translate(molecules[0])
    if atoms is None:
        return None, report
    kept, screen = gate.screen_molecule(
        "lot_event", atoms, ledger_config.declared_derivations(cfg, "lot_event"),
        molecule_ref=molecules[0].ref, source_rows=len(rows))
    return (None if screen["refused"] else kept), screen


# ------------------------------------------------------------------------- vocabulary
def test_v0_vocabulary_is_exactly_seven_words():
    """The brief fixes v0 at seven. A vocabulary that grows quietly is not closed."""
    assert set(vocabulary.PREDICATES) == {
        "register", "pin", "same_as",
        "derived_from", "slot_map", "has_wafer", "frame_confirmed",
    }


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


def test_the_shipped_sample_config_validates():
    path = os.path.join(os.path.dirname(__file__), "..", "config",
                        "ledger_config.json.sample")
    cfg = ledger_config.load(os.path.abspath(path))
    assert "lot_event" in cfg["sources"]
    assert ledger_config.translator_version(cfg, "lot_event").startswith("lot_event/")


def test_the_translator_version_changes_when_a_RULE_changes():
    """The `slot_preserving` judgement is auditable only if the atoms say which
    convention made them."""
    base = ledger_config.translator_version(full_cfg(), "lot_event")
    other = full_cfg()
    other["sources"]["lot_event"]["vocabulary"]["split"]["slot_pairing"] = "shared_wafer"
    assert ledger_config.translator_version(other, "lot_event") != base


# ------------------------------------------------------------------ molecule assembly
def test_the_two_rows_of_one_split_form_one_molecule():
    rows = [row("P", child_lot="C", slots="01:02", wafers="W1:W2"),
            row("C", parent_lot="P", slots="03", wafers="W3")]
    molecules = group_molecules(rows)
    assert len(molecules) == 1
    assert (molecules[0].parent, molecules[0].child) == ("P", "C")
    assert len(molecules[0].rows) == 2


def test_a_row_naming_both_sides_is_isolated_and_refused():
    """Real data: a grid edit put a value in `child_lot` on a row that already had
    `parent_lot`. Reading one field first and ignoring the other attaches that row's
    wafers to a lineage the source never asserted."""
    bad = row("C", parent_lot="P", child_lot="OTHER", slots="01", wafers="W1")
    key = molecule_key(bad)
    assert key[-1] == bad["row_identity"]

    atoms, report = translate_one([bad])
    assert atoms is None
    assert report["reason"] == gate.REFUSE_AMBIGUOUS_PAIR
    assert gate.refusals()[("lot_event", gate.REFUSE_AMBIGUOUS_PAIR)] == 1
    assert gate.rows_refused()["lot_event"] == 1


# ------------------------------------------------------------------------ translation
def test_a_blank_wafer_id_makes_no_has_wafer_atom():
    """The brief: a blank makes no atom. 'There is a wafer here, I do not know which'
    is not a claim, so there is nothing to record."""
    rows = [row("P", event_type="track_in", slots="01:02:03", wafers="W1::W3")]
    atoms, _ = translate_one(rows)
    has_wafer = [a for a in atoms if a.predicate == "has_wafer"]
    assert len(has_wafer) == 2
    assert {a.object_payload["keys"]["wafer"] for a in has_wafer} == {"W1", "W3"}
    assert "02" not in {a.object_payload["qualifiers"]["slot"] for a in has_wafer}


def test_unequal_slot_and_wafer_lists_refuse_the_whole_molecule():
    """An unequal pairing does not raise downstream - it reattributes wafers to the
    wrong slots and still looks well formed (`trace_fixture/world.py` says so in the
    generator). That is an atomicity violation, not a warning."""
    rows = [row("P", event_type="track_in", slots="01:02:03", wafers="W1:W2")]
    atoms, report = translate_one(rows)
    assert atoms is None
    assert report["reason"] == gate.REFUSE_ATOMICITY
    assert gate.refusals()[("lot_event", gate.REFUSE_ATOMICITY)] == 1


def test_an_undeclared_event_type_is_refused_and_counted_never_skipped():
    rows = [row("P", event_type="scrap", slots="01", wafers="W1")]
    atoms, report = translate_one(rows)
    assert atoms is None
    assert report["reason"] == gate.REFUSE_UNDECLARED_VOCABULARY
    assert gate.refusals()[("lot_event", gate.REFUSE_UNDECLARED_VOCABULARY)] == 1
    assert gate.note() is not None and "undeclared_vocabulary" in gate.note()


def test_an_unparseable_event_time_is_refused_and_arrival_time_is_not_substituted():
    rows = [row("P", event_type="track_in", slots="01", wafers="W1",
                event_time="not a timestamp")]
    atoms, report = translate_one(rows)
    assert atoms is None
    assert report["reason"] == gate.REFUSE_MISSING_OCCURRED_AT


def test_split_slot_map_uses_the_declared_convention_and_says_so_in_the_atom():
    rows = [row("P", child_lot="C", slots="07:08", wafers="W7:W8"),
            row("C", parent_lot="P", slots="01:02", wafers="W1:W2")]
    atoms, _ = translate_one(rows)
    slot_maps = [a for a in atoms if a.predicate == "slot_map"]
    assert len(slot_maps) == 2
    for atom in slot_maps:
        q = atom.object_payload["qualifiers"]
        assert q["from"] == q["to"]
        assert atom.subject_keys == {"lot": "P"}
        assert atom.object_payload["keys"] == {"lot": "C"}
        assert atom.source_translator_ver.endswith("#slot_preserving")


def test_merge_slot_map_needs_no_convention_because_the_source_utters_both_slots():
    rows = [row("P", event_type="merge", child_lot="C", slots="10:13", wafers="W7:W9"),
            row("C", event_type="merge", parent_lot="P", slots="02:03:04",
                wafers="W7:W9:WX")]
    atoms, _ = translate_one(rows)
    pairs = {(a.object_payload["qualifiers"]["from"],
              a.object_payload["qualifiers"]["to"],
              a.object_payload["qualifiers"]["wafer"])
             for a in atoms if a.predicate == "slot_map"}
    assert pairs == {("10", "02", "W7"), ("13", "03", "W9")}
    for atom in atoms:
        if atom.predicate == "slot_map":
            assert atom.source_translator_ver.endswith("#shared_wafer")


def test_shared_wafer_emits_nothing_where_the_source_is_silent():
    """A split's two rows share no wafer, so the zero-inference strategy correctly
    produces no slot_map at all. Stated as a test because it is the cost of the
    zero-inference position and must not surprise anyone later."""
    cfg = full_cfg()
    cfg["sources"]["lot_event"]["vocabulary"]["split"]["slot_pairing"] = "shared_wafer"
    rows = [row("P", child_lot="C", slots="07:08", wafers="W7:W8"),
            row("C", parent_lot="P", slots="01:02", wafers="W1:W2")]
    atoms, _ = translate_one(rows, cfg)
    assert [a for a in atoms if a.predicate == "slot_map"] == []
    assert [a for a in atoms if a.predicate == "derived_from"]


def test_derived_from_points_child_at_parent():
    rows = [row("P", child_lot="C", slots="01", wafers="W1"),
            row("C", parent_lot="P", slots="02", wafers="W2")]
    atoms, _ = translate_one(rows)
    derived = [a for a in atoms if a.predicate == "derived_from"]
    assert len(derived) == 1
    assert derived[0].subject_keys == {"lot": "C"}
    assert derived[0].object_payload["keys"] == {"lot": "P"}


def test_every_atom_carries_a_raw_ref_naming_its_source_rows():
    rows = [row("P", child_lot="C", slots="01", wafers="W1"),
            row("C", parent_lot="P", slots="02", wafers="W2")]
    atoms, _ = translate_one(rows)
    identities = {r["row_identity"] for r in rows}
    for atom in atoms:
        assert atom.source_raw_ref.startswith("lot_event:")
        named = set(__import__("json").loads(atom.source_raw_ref.split(":", 1)[1]))
        assert named and named <= identities


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
                                        molecule_ref="m")
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
                                        molecule_ref="m")
    assert kept == [] and report["reason"] == gate.REFUSE_UNDECLARED_DERIVATION


def test_an_atom_with_no_raw_ref_is_refused():
    """Atomicity check 4: nothing points back at the source, so it cannot be re-uttered."""
    atom = envelope.Atom(
        subject_type="Lot", subject_keys={"lot": "A"}, predicate="register",
        occurred_at=WHEN, source_who="s", source_translator_ver="v",
        source_raw_ref="", molecule_ref="m", derivation="first_sight")
    kept, report = gate.screen_molecule("lot_event", [atom], {"first_sight"},
                                        molecule_ref="m")
    assert kept == [] and report["reason"] == gate.REFUSE_NO_RAW_REF


def test_a_naive_occurred_at_is_refused():
    atom = envelope.Atom(
        subject_type="Lot", subject_keys={"lot": "A"}, predicate="register",
        occurred_at=datetime(2026, 5, 3, 2, 17), source_who="s",
        source_translator_ver="v", source_raw_ref="r", molecule_ref="m",
        derivation="first_sight")
    kept, report = gate.screen_molecule("lot_event", [atom], {"first_sight"},
                                        molecule_ref="m")
    assert kept == [] and report["reason"] == gate.REFUSE_MISSING_OCCURRED_AT


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


def _inject_undeclared_refusal_reason():
    gate.refuse("lot_event", "invented_on_the_spot", "detail")


def _inject_nan_payload():
    envelope.freeze_payload({"x": float("inf")})


def _inject_unequal_slot_and_wafer_lists():
    gate.reset_counters()
    rows = [row("P", event_type="track_in", slots="01:02", wafers="W1")]
    atoms, report = translate_one(rows)
    if atoms is not None:
        raise AssertionError("an unequal positional pairing was accepted")
    raise ValueError(report["reason"])


def _inject_ambiguous_pair():
    gate.reset_counters()
    atoms, report = translate_one(
        [row("C", parent_lot="P", child_lot="OTHER", slots="01", wafers="W1")])
    if atoms is not None:
        raise AssertionError("a row naming both sides of a pair was accepted")
    raise ValueError(report["reason"])


#: (name, callable). Each callable must RAISE. Declared as data so the count below is a
#: real assertion about coverage rather than a comment.
INJECTIONS = [
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
    ("refusal reason invented at a call site", _inject_undeclared_refusal_reason),
    ("non-finite number in a payload", _inject_nan_payload),
    ("unequal slot and wafer lists", _inject_unequal_slot_and_wafer_lists),
    ("row naming both sides of a pair", _inject_ambiguous_pair),
]

EXPECTED_INJECTIONS = 14


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
