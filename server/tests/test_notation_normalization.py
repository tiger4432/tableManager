"""WF/lot/slot notation normalization - the DERIVED column, and what it must never do.

[Red first - the defect this exists to fix]
`map_overlay.map_key_parts` splits a composite map key on '_'. A `core_lot` whose
own value contains '_' therefore shreds: 'CL_2601_001_09' + slot '5' composes to
'CL_2601_001_09_5', which parses back as lot='CL', slot='2601_001_09_5', and the
cell query finds NOTHING. 766 rows of the simulation carried that shape.
`test_a_lot_containing_underscore_shreds_the_map_key_today` states that as a live
assertion, and its sibling shows the normalized value composing correctly.

[The safety property, stated as tests rather than as a comment]
Every claim the design rests on is asserted here:
  - the raw column is BYTE-IDENTICAL after derivation
  - a declaration that would write back over the raw column is REFUSED
  - a derived column that is part of the business key is REFUSED
  - a WRITE aimed at a derived column is REFUSED
  - changing the rules and re-deriving produces the new answer with NO cleanup
That last one is the whole reason this could ship before the false-merge census
had been run.

[Defect injection - which assertions can actually see a failure]
Run before claiming coverage (server-pm lesson: a test that never executes the
new lines certifies nothing). Measured, not guessed:

  Injection A - `fold_notation` returns `text` unchanged.  9 RED:
      test_the_derived_value_composes_the_map_key_correctly
      test_the_reported_spellings_fold_together
      test_separator_rule_alone / test_case_rule_alone / test_both_rules_and_neither
      test_a_column_can_override_the_file_level_rules
      test_rederivation_changes_the_answer_with_no_manual_cleanup
      test_rederivation_fills_rows_written_before_the_declaration
      test_blank_and_absent_values_derive_to_null

  Injection B - `apply_derivations` returns `[]` without setting anything. 5 RED:
      test_the_reported_spellings_fold_together
      test_zero_padding_is_NOT_folded_in_a_string_column
      test_a_column_can_override_the_file_level_rules
      test_rederivation_changes_the_answer_with_no_manual_cleanup
      test_a_number_declared_column_is_folded_by_canonical_key_value_alone
    The pure-function tests stay GREEN, and so does
    `test_rederivation_fills_rows_written_before_the_declaration` (it calls
    `rederive` directly) - which is exactly why both halves are tested.

  Injection C - `_validate_column` drops the `derived == raw` refusal. 1 RED
      (test_a_declaration_that_would_rewrite_the_raw_column_is_refused) - and
      that single assertion is the guard for the entire safety property.

[격리] Table prefix `notnorm_test_` - cannot exist in the user's gitignored
config (server-pm lesson: the `bonding_log` trap).
"""
import json

import pytest

import notation_norm
from database import crud, models, schemas

TABLES = {
    "notnorm_test_log": {
        "business_key": "cell_key",
        "composite_key_source": ["job", "x"],
        "column_types": {
            "cell_key": "string",
            "job": "string",
            "x": "number",
            "core_lot": "string",
            "core_lot_norm": "string",
            "dt_lot": "string",
            "dt_lot_norm": "string",
            # Declared `number` on purpose: this is where `canonical_key_value`
            # (7b) already does the integer fold, and the point of the reuse is
            # that this module adds nothing here.
            "slot": "number",
            "slot_norm": "string",
            # Wrong on purpose - the loader must refuse a non-string target.
            "bad_norm": "number",
        },
    },
}

BASE_DECL = {
    "rules": {"separator": True, "case": True, "zero_pad": False},
    "columns": {"notnorm_test_log": {"core_lot": "core_lot_norm"}},
}


def _write_decl(tmp_path, monkeypatch, decl):
    """Point the loader at a temp declaration file and drop the TTL cache."""
    path = tmp_path / "notation_rules.json"
    path.write_text(json.dumps(decl), encoding="utf-8")
    monkeypatch.setattr(notation_norm, "NOTATION_RULES_PATH", str(path))
    notation_norm.reset_cache()
    return str(path)


@pytest.fixture()
def norm_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    _write_decl(tmp_path, monkeypatch, BASE_DECL)
    yield db_session
    notation_norm.reset_cache()


def _write(db, rows, source_name="pipeline_parser"):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name=source_name,
                                       updated_by="test") for r in rows]
    return crud.apply_batch_updates(db, "notnorm_test_log", schemas.GeneralUpdateBatch(
        updates=items, transaction_id="notnorm_tx", silent=True))


def _row(db, key):
    model = models.DYNAMIC_TABLES["notnorm_test_log"]
    return db.query(model).filter(model.business_key_val == key).one()


# ---------------------------------------------------------------------------
# RED FIRST - the map key shredding, shown before it is fixed
# ---------------------------------------------------------------------------

def test_a_lot_containing_underscore_shreds_the_map_key_today():
    """A lot value carrying '_' parses back as a DIFFERENT (lot, slot) pair.

    This is the reported defect, asserted rather than described. It is stated as
    the CURRENT behaviour of `map_key_parts`, so it stays true after this round -
    phase 1 changes nothing about how map keys are parsed.
    """
    from map_overlay import map_key_parts

    binding = {"key_columns": ["lot", "slot"]}
    parts = dict(map_key_parts(binding, "CL_2601_001_09_5"))
    assert parts != {"lot": "CL_2601_001_09", "slot": "5"}
    assert parts == {"lot": "CL", "slot": "2601_001_09_5"}, (
        "if this ever passes as the intended pair, the split rule changed and "
        "phase 2 arrived without this test being updated")


def test_the_derived_value_composes_the_map_key_correctly():
    """The same lot, normalized, survives the round trip through the '_' join.

    The separator rule folds '_' to '-', so the value stops containing the one
    character the composite key is joined with. The convention is unchanged; it
    is the VALUE that stopped fighting it.
    """
    from map_overlay import map_key_parts

    rules = {notation_norm.RULE_SEPARATOR: True, notation_norm.RULE_CASE: True}
    lot = notation_norm.fold_notation("CL_2601_001_09", rules)
    assert lot == "CL-2601-001-09"

    composed = f"{lot}_5"
    parts = dict(map_key_parts({"key_columns": ["lot", "slot"]}, composed))
    assert parts == {"lot": "CL-2601-001-09", "slot": "5"}


# ---------------------------------------------------------------------------
# The safety property
# ---------------------------------------------------------------------------

def test_the_raw_column_is_byte_identical_after_derivation(norm_env):
    """🔴 The load-bearing assertion. Derivation adds a value; it never edits one.

    Every mixed spelling the operator reported goes in, and comes back out of the
    raw column byte-for-byte (modulo the pre-existing edge strip that
    `normalize_stored_text` has always done, which is why no input here has edge
    whitespace).
    """
    db = norm_env
    raws = ["WF.01", "WF-01", "WF_01", "wf 01", "CL_2601_001_09", "WF010", "WF10"]
    for i, raw in enumerate(raws):
        _write(db, [{"job": f"J{i}", "x": 1, "core_lot": raw}])
    for i, raw in enumerate(raws):
        row = _row(db, f"J{i}_1")
        assert row.core_lot == raw, (
            f"the raw column was rewritten: {raw!r} -> {row.core_lot!r}. The "
            f"entire 'a wrong rule is repairable' argument depends on this "
            f"never happening.")


def test_the_reported_spellings_fold_together(norm_env):
    """'WF.01' and 'WF-01' and 'WF_01' and 'wf 01' become ONE derived value."""
    db = norm_env
    for i, raw in enumerate(["WF.01", "WF-01", "WF_01", "wf 01", "WF--01"]):
        _write(db, [{"job": f"S{i}", "x": 1, "core_lot": raw}])
    derived = {_row(db, f"S{i}_1").core_lot_norm for i in range(5)}
    assert derived == {"WF-01"}


def test_zero_padding_is_NOT_folded_in_a_string_column(norm_env):
    """🔴 R3 is not implemented, and this is what that means in practice.

    'WF010' and 'WF10' stay two different derived values. That is the whole
    reason it is safe to ship without the census: the one rule that could merge
    two genuinely different entities was left out.
    """
    db = norm_env
    _write(db, [{"job": "P0", "x": 1, "core_lot": "WF010"},
                {"job": "P1", "x": 1, "core_lot": "WF10"}])
    assert _row(db, "P0_1").core_lot_norm == "WF010"
    assert _row(db, "P1_1").core_lot_norm == "WF10"


def test_a_declaration_that_would_rewrite_the_raw_column_is_refused():
    """`{"core_lot": "core_lot"}` is refused BY NAME, not quietly accepted."""
    rejections = []
    out = notation_norm.validate_notation_rules(
        {"columns": {"notnorm_test_log": {"core_lot": "core_lot"}}},
        known_tables=TABLES, rejections=rejections)
    assert out == {}
    assert [r["code"] for r in rejections] == [notation_norm.CODE_WOULD_REWRITE_RAW]


def test_a_derived_column_inside_the_business_key_is_refused():
    """A derived value must never be able to move a row's identity."""
    rejections = []
    out = notation_norm.validate_notation_rules(
        {"columns": {"notnorm_test_log": {"core_lot": "job"}}},
        known_tables=TABLES, rejections=rejections)
    assert out == {}
    assert [r["code"] for r in rejections] == [notation_norm.CODE_KEY_COLUMN]


def test_an_undeclared_or_mistyped_derived_column_is_refused():
    for decl, code in (
        ({"core_lot": "not_a_column"}, notation_norm.CODE_UNDECLARED),
        ({"not_a_column": "core_lot_norm"}, notation_norm.CODE_UNDECLARED),
        ({"core_lot": "bad_norm"}, notation_norm.CODE_SHAPE),   # declared number
    ):
        rejections = []
        out = notation_norm.validate_notation_rules(
            {"columns": {"notnorm_test_log": decl}},
            known_tables=TABLES, rejections=rejections)
        assert out == {}, decl
        assert [r["code"] for r in rejections] == [code], decl


def test_a_write_aimed_at_the_derived_column_is_refused(norm_env):
    """The derived column is not editable - the refusal names it, in Korean."""
    db = norm_env
    with pytest.raises(ValueError) as exc:
        _write(db, [{"job": "W0", "x": 1, "core_lot": "WF.01",
                     "core_lot_norm": "HAND-WRITTEN"}], source_name="user")
    assert "core_lot_norm" in str(exc.value)
    # cp949-encodable, like every user-facing string in this system.
    str(exc.value).encode("cp949")


# ---------------------------------------------------------------------------
# Each rule toggles alone
# ---------------------------------------------------------------------------

MIXED = "wf.a_b 01"


def test_separator_rule_alone():
    rules = {notation_norm.RULE_SEPARATOR: True, notation_norm.RULE_CASE: False}
    assert notation_norm.fold_notation(MIXED, rules) == "wf-a-b-01"


def test_case_rule_alone():
    rules = {notation_norm.RULE_SEPARATOR: False, notation_norm.RULE_CASE: True}
    assert notation_norm.fold_notation(MIXED, rules) == "WF.A_B 01"


def test_both_rules_and_neither():
    both = {notation_norm.RULE_SEPARATOR: True, notation_norm.RULE_CASE: True}
    assert notation_norm.fold_notation(MIXED, both) == "WF-A-B-01"
    assert notation_norm.fold_notation(MIXED, {}) == MIXED


def test_a_column_can_override_the_file_level_rules(norm_env, tmp_path, monkeypatch):
    """Per-column rules, proven through the WRITE PATH and not just the fold.

    Two columns of ONE row, same input, different rule sets - so a bug that
    applied one global rule set to everything cannot pass this.
    """
    db = norm_env
    _write_decl(tmp_path, monkeypatch, {
        "rules": {"separator": True, "case": True},
        "columns": {"notnorm_test_log": {
            "core_lot": "core_lot_norm",
            "dt_lot": {"derived": "dt_lot_norm",
                       "rules": {"separator": True, "case": False}},
        }},
    })
    _write(db, [{"job": "O0", "x": 1, "core_lot": MIXED, "dt_lot": MIXED}])
    row = _row(db, "O0_1")
    assert row.core_lot_norm == "WF-A-B-01"
    assert row.dt_lot_norm == "wf-a-b-01"


def test_zero_pad_true_is_refused_by_name_and_forced_off():
    """A knob that reads as ON and does nothing is the silence this refuses."""
    rejections = []
    out = notation_norm.validate_notation_rules(
        {"rules": {"zero_pad": True},
         "columns": {"notnorm_test_log": {"core_lot": "core_lot_norm"}}},
        known_tables=TABLES, rejections=rejections)
    assert [r["code"] for r in rejections] == \
        [notation_norm.CODE_ZERO_PAD_UNIMPLEMENTED]
    spec = out["notnorm_test_log"]["core_lot"]
    assert spec["rules"][notation_norm.RULE_ZERO_PAD] is False
    # And declaring it OFF is not a rejection - "declared false" is a decision.
    assert notation_norm.validate_notation_rules(
        {"rules": {"zero_pad": False}, "columns": {}},
        known_tables=TABLES, rejections=[]) == {}


def test_an_unknown_rule_name_is_refused_not_ignored():
    rejections = []
    notation_norm.validate_notation_rules(
        {"rules": {"transliterate": True}, "columns": {}},
        known_tables=TABLES, rejections=rejections)
    assert [r["code"] for r in rejections] == [notation_norm.CODE_UNKNOWN_RULE]


# ---------------------------------------------------------------------------
# Re-derivation - the repair that makes a wrong rule cheap
# ---------------------------------------------------------------------------

def test_rederivation_changes_the_answer_with_no_manual_cleanup(norm_env, tmp_path,
                                                                monkeypatch):
    """🔴 THE argument for shipping before the census.

    Write rows under one rule set, change the rules, re-derive, and the derived
    column carries the NEW answer while every raw value is untouched. Nothing is
    deleted, nothing is reset by hand, and the dry-run says what it would do
    before it does it.
    """
    db = norm_env
    raws = ["WF.01", "wf_02", "CL_2601_001_09"]
    for i, raw in enumerate(raws):
        _write(db, [{"job": f"R{i}", "x": 1, "core_lot": raw}])
    assert [_row(db, f"R{i}_1").core_lot_norm for i in range(3)] == \
        ["WF-01", "WF-02", "CL-2601-001-09"]

    # Rule change: case fold off.
    _write_decl(tmp_path, monkeypatch, {
        "rules": {"separator": True, "case": False},
        "columns": {"notnorm_test_log": {"core_lot": "core_lot_norm"}},
    })
    spec = notation_norm.derivations_for("notnorm_test_log")["core_lot"]

    dry = notation_norm.rederive(db, "notnorm_test_log", spec, chunk_size=2)
    assert dry["mode"] == "dry-run" and dry["scanned"] == 3 and dry["changed"] == 1
    assert _row(db, "R1_1").core_lot_norm == "WF-02", "dry-run wrote something"

    applied = notation_norm.rederive(db, "notnorm_test_log", spec, chunk_size=2,
                                     apply=True)
    assert applied["changed"] == 1
    assert [_row(db, f"R{i}_1").core_lot_norm for i in range(3)] == \
        ["WF-01", "wf-02", "CL-2601-001-09"]
    # The raw values never moved, which is why this repair was possible at all.
    assert [_row(db, f"R{i}_1").core_lot for i in range(3)] == raws

    # Idempotent: running it again finds nothing left to do.
    assert notation_norm.rederive(db, "notnorm_test_log", spec,
                                  apply=True)["changed"] == 0


def test_rederivation_fills_rows_written_before_the_declaration(norm_env, tmp_path,
                                                               monkeypatch):
    """Existing rows are not stranded - this is how an operator switches it on."""
    db = norm_env
    _write_decl(tmp_path, monkeypatch, {"rules": {}, "columns": {}})
    _write(db, [{"job": "B0", "x": 1, "core_lot": "WF.01"}])
    assert _row(db, "B0_1").core_lot_norm is None

    _write_decl(tmp_path, monkeypatch, BASE_DECL)
    spec = notation_norm.derivations_for("notnorm_test_log")["core_lot"]
    assert notation_norm.rederive(db, "notnorm_test_log", spec,
                                  apply=True)["changed"] == 1
    assert _row(db, "B0_1").core_lot_norm == "WF-01"


# ---------------------------------------------------------------------------
# Reuse of canonical_key_value (7b), not a second vocabulary
# ---------------------------------------------------------------------------

def test_a_number_declared_column_is_folded_by_canonical_key_value_alone(
        norm_env, tmp_path, monkeypatch):
    """'01' and '1' land on one derived value because 7b already said so.

    This module adds no padding rule; the integer parse it inherits is why the
    'slot is always int' ruling retires the zero-pad question for slot.
    """
    db = norm_env
    _write_decl(tmp_path, monkeypatch, {
        "rules": {"separator": True, "case": True},
        "columns": {"notnorm_test_log": {"slot": "slot_norm"}},
    })
    _write(db, [{"job": "N0", "x": 1, "slot": "01"},
                {"job": "N1", "x": 1, "slot": "1"},
                {"job": "N2", "x": 1, "slot": 1.0}])
    assert {_row(db, f"N{i}_1").slot_norm for i in range(3)} == {"1"}


def test_blank_and_absent_values_derive_to_null(norm_env):
    """An absent value has no notation; inventing '' would claim one."""
    db = norm_env
    _write(db, [{"job": "Z0", "x": 1, "core_lot": None},
                {"job": "Z1", "x": 1, "core_lot": "   "}])
    assert _row(db, "Z0_1").core_lot_norm is None
    assert _row(db, "Z1_1").core_lot_norm is None
    # A value made only of separators folds to '-', which is not a value either.
    assert notation_norm.normalized_value(
        "notnorm_test_log", "core_lot", "__",
        {notation_norm.RULE_SEPARATOR: True}) == "-"


def test_nothing_is_derived_when_nothing_is_declared(norm_env, tmp_path, monkeypatch):
    """The feature is inert until an operator declares a pair (phase 1 default)."""
    db = norm_env
    _write_decl(tmp_path, monkeypatch, {"rules": {}, "columns": {}})
    _write(db, [{"job": "I0", "x": 1, "core_lot": "WF.01"}])
    row = _row(db, "I0_1")
    assert row.core_lot == "WF.01" and row.core_lot_norm is None
    # ...and with nothing declared, the write guard refuses nothing.
    _write(db, [{"job": "I1", "x": 1, "core_lot_norm": "anything"}])


def test_a_missing_declaration_file_is_not_an_error(tmp_path, monkeypatch):
    """File absence is 'no declaration', not a rejection (the repo's rule)."""
    monkeypatch.setattr(notation_norm, "NOTATION_RULES_PATH",
                        str(tmp_path / "nope.json"))
    notation_norm.reset_cache()
    rejections = []
    assert notation_norm.load_notation_rules(rejections=rejections) == {}
    assert rejections == []
    notation_norm.reset_cache()


# ---------------------------------------------------------------------------
# "Did my config take?" - the answer must be visible, not log-only
# ---------------------------------------------------------------------------

def test_the_resolve_report_names_the_declaration_and_says_nothing_reads_it(
        norm_env, tmp_path, monkeypatch):
    """A refusal nobody can see is the trap this repo keeps paying for.

    Also pins the phase-1 fact IN THE OPERATOR'S OWN SENTENCE: the declaration
    is in effect AND nothing consumes the value yet. Those are two different
    questions and the report answers both.
    """
    import config_resolve_report as crr

    _write_decl(tmp_path, monkeypatch, {
        "rules": {"separator": True, "case": True, "zero_pad": True},
        "columns": {"notnorm_test_log": {"core_lot": "core_lot_norm",
                                         "dt_lot": "dt_lot"}},
    })
    domain = crr._resolve_notation()
    assert domain["domain"] == crr.DOMAIN_NOTATION
    assert [e["subject"] for e in domain["effective"]] == \
        ["notnorm_test_log.core_lot"]
    assert "core_lot_norm" in domain["effective"][0]["detail"]
    assert "1단계" in domain["effective"][0]["detail"], \
        "the report must say nothing reads the derived value yet"
    reasons = {e["reason"] for e in domain["rejected"]}
    assert reasons == {crr.REASON_NOT_REACHED, crr.REASON_MAPPING_UNAVAILABLE}
    for e in domain["rejected"] + domain["effective"]:
        e["detail"].encode("cp949")   # operator-facing Korean must survive cp949


def test_the_shipped_sample_is_valid_json_and_declares_nothing():
    """The sample must parse, and must ship inert - phase 1 has no consumers."""
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "notation_rules.json.sample")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    rejections = []
    assert notation_norm.validate_notation_rules(raw, known_tables=TABLES,
                                                 rejections=rejections) == {}
    assert rejections == [], (
        f"the shipped sample produces rejections: {rejections}")
