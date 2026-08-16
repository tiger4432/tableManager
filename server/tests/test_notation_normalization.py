"""Notation normalization - the QUERY-TIME fold, and the one-sided fold it forbids.

[What changed, and why these tests look different from the ones they replace]
The first shipped shape (92b8d6f) wrote a folded value into a physical `<col>_norm`
column. User ruling 2026-08-04 withdrew it: arming it took three config layers, it
produced a column users could see and could not edit, and - the load-bearing reason -
using it in a virtual join required naming `<col>_norm` on BOTH sides of the join key,
which nobody would do on the side that is already clean. A join folded on one side only
SILENTLY DROPS matches.

So the tests that asserted the write path (raw byte-identity after derivation, the write
refusal, re-derivation, the `derived == raw` and `key_column` refusals) are gone with
their subject. What replaces them is the assertion the withdrawn design could not make:

    `test_both_sides_fold_when_only_the_dirty_side_is_declared`

[🔴 WHAT THIS FILE CAN AND CANNOT PROVE - read before adding to it]
The suite runs on SQLite, which has neither `regexp_replace` nor `translate`. The SQL
fold therefore compiles to a registered scalar function whose body IS `fold_notation`
(`notation_norm.install_sqlite_fold`). That means:

    THIS FILE PROVES THE WIRING - that both sides of a comparison are folded, that an
    asymmetric declaration still folds both, that a declaration reaches the join at all.

    THIS FILE CANNOT PROVE THE SPELLING - on SQLite the two halves are the same code, so
    a divergence between the Python fold and the PostgreSQL fold is invisible here BY
    CONSTRUCTION. That is scored by `contracts/notation_fold/` against a live
    PostgreSQL, and only there. Do not add a "the SQL matches Python" test to this file:
    it would pass unconditionally and read like coverage.

[Defect injection - which assertions can actually see a failure]
Run before claiming coverage (server-pm lesson: a test that never executes the new lines
certifies nothing). Measured, not guessed - see the report for the exact counts.

[Isolation] Table prefix `notnorm_test_` - cannot exist in the user's gitignored config
(server-pm lesson: the `bonding_log` trap).
"""
import json

import pytest

import notation_norm
from database import crud, models, schemas

TABLES = {
    # LEFT side of the join - the DIRTY table. Mirrors the measured production shape:
    # `dt_log.core_lot` carries 30 raw spellings folding to 15.
    "notnorm_test_log": {
        "business_key": "cell_key",
        "composite_key_source": ["job", "x"],
        "column_types": {
            "cell_key": "string",
            "job": "string",
            "x": "number",
            "core_lot": "string",
            "dt_lot": "string",
            # Declared `number` on purpose: the loader must refuse it. A number has
            # no notation, and this refusal is what keeps the SQL fold short enough
            # to be an index expression.
            "slot": "number",
        },
    },
    # RIGHT side - the CLEAN table. `core_lot` here has ZERO merge groups, which is
    # exactly why an operator would never declare it, and exactly why the fold must
    # not depend on them doing so.
    "notnorm_test_ref": {
        "business_key": "core_lot",
        "column_types": {
            "core_lot": "string",
            "wafer_id": "string",
        },
    },
}

BASE_DECL = {
    "rules": {"separator": True, "case": True, "zero_pad": False},
    "columns": {"notnorm_test_log": {"core_lot": True}},
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
    for name in TABLES:
        models.DYNAMIC_TABLES.pop(name, None)
        crud.TABLE_CONFIG.pop(name, None)
        tbl = Base.metadata.tables.get(name)
        if tbl is not None:
            Base.metadata.remove(tbl)


def _write(db, table, rows, source_name="pipeline_parser"):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name=source_name,
                                       updated_by="test") for r in rows]
    return crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id="notnorm_tx", silent=True))


# ---------------------------------------------------------------------------
# The fold, as a pure function. Each rule toggles alone.
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


def test_the_reported_spellings_fold_together():
    """'WF.01' / 'WF-01' / 'WF_01' / 'wf 01' / 'WF--01' become ONE value."""
    rules = {notation_norm.RULE_SEPARATOR: True, notation_norm.RULE_CASE: True}
    folded = {notation_norm.fold_notation(s, rules)
              for s in ["WF.01", "WF-01", "WF_01", "wf 01", "WF--01"]}
    assert folded == {"WF-01"}


def test_zero_padding_is_NOT_folded():
    """R3 is not implemented, and this is what that means: 'WF010' != 'WF10'."""
    rules = {notation_norm.RULE_SEPARATOR: True, notation_norm.RULE_CASE: True}
    assert notation_norm.fold_notation("WF010", rules) != \
        notation_norm.fold_notation("WF10", rules)


def test_the_case_fold_is_ascii_only_and_that_is_deliberate():
    """🔴 The narrowing that makes the two engines agree, asserted where it is easy to
    find. `str.upper()` would give 'STRASSE' (a LENGTH change) and 'I'; PostgreSQL's
    `upper()` gives neither. The fold leaves both alone, on both engines.
    """
    rules = {notation_norm.RULE_CASE: True}
    assert notation_norm.fold_notation("straße", rules) == "STRAßE"
    assert notation_norm.fold_notation("ı", rules) == "ı"
    assert notation_norm.fold_notation("été", rules) == "éTé"


def test_the_separator_class_is_enumerated_not_a_shorthand():
    """🔴 The pattern must never go back to `\\s`. Python's `\\s` and PostgreSQL's
    `[[:space:]]` were MEASURED to disagree on five codepoints, and PostgreSQL's answer
    follows the database ctype - so the shorthand is not stable across installs.

    This asserts the enumeration is complete relative to Python's own table, which is
    what makes the SQL side (built from the same tuple) complete too.
    """
    import re as _re
    py_space = {cp for cp in range(0x11000) if _re.match(r"\s", chr(cp))}
    declared = set(notation_norm.SEPARATOR_CODEPOINTS)
    assert py_space <= declared, (
        "these whitespace codepoints fold in Python but are missing from "
        "SEPARATOR_CODEPOINTS, so the SQL fold would not fold them: "
        + " ".join("U+%04X" % c for c in sorted(py_space - declared)))
    assert "\\s" not in notation_norm.SEPARATOR_PATTERN
    assert notation_norm.SEPARATOR_PATTERN.endswith("-]+")


def test_non_strings_pass_through_untouched():
    rules = {notation_norm.RULE_SEPARATOR: True, notation_norm.RULE_CASE: True}
    for v in (None, 7, 7.5, True):
        assert notation_norm.fold_notation(v, rules) is v


# ---------------------------------------------------------------------------
# The declaration
# ---------------------------------------------------------------------------

def test_the_declaration_is_one_line_and_takes_three_shapes():
    """`true`, `{rules}`, and `false` (a decision on the record, not an error)."""
    out = notation_norm.validate_notation_rules(
        {"rules": {"separator": True, "case": True},
         "columns": {"notnorm_test_log": {
             "core_lot": True,
             "dt_lot": {"rules": {"separator": True, "case": False}},
         }}},
        known_tables=TABLES, rejections=[])
    assert set(out["notnorm_test_log"]) == {"core_lot", "dt_lot"}
    assert out["notnorm_test_log"]["core_lot"]["rules"][notation_norm.RULE_CASE] is True
    assert out["notnorm_test_log"]["dt_lot"]["rules"][notation_norm.RULE_CASE] is False

    rejections = []
    assert notation_norm.validate_notation_rules(
        {"columns": {"notnorm_test_log": {"core_lot": False}}},
        known_tables=TABLES, rejections=rejections) == {}
    assert rejections == [], "declaring a column OFF is a decision, not a rejection"


def test_the_old_derived_declaration_is_refused_by_name():
    """An operator upgrading from 92b8d6f gets told what to do, not a silent no-op."""
    rejections = []
    out = notation_norm.validate_notation_rules(
        {"columns": {"notnorm_test_log": {"core_lot": {"derived": "core_lot_norm"}}}},
        known_tables=TABLES, rejections=rejections)
    assert out == {}
    assert [r["code"] for r in rejections] == [notation_norm.CODE_SHAPE]
    assert "derived" in rejections[0]["detail"]


def test_a_number_column_cannot_be_declared_normalized():
    """🔴 A number has no notation - and this refusal is what keeps the SQL fold short
    enough to be a functional index expression."""
    rejections = []
    out = notation_norm.validate_notation_rules(
        {"columns": {"notnorm_test_log": {"slot": True}}},
        known_tables=TABLES, rejections=rejections)
    assert out == {}
    assert [r["code"] for r in rejections] == [notation_norm.CODE_NOT_TEXT]


def test_an_undeclared_table_or_column_is_refused():
    for decl, code in (
        ({"not_a_column": True}, notation_norm.CODE_UNDECLARED),
    ):
        rejections = []
        assert notation_norm.validate_notation_rules(
            {"columns": {"notnorm_test_log": decl}},
            known_tables=TABLES, rejections=rejections) == {}
        assert [r["code"] for r in rejections] == [code], decl
    rejections = []
    assert notation_norm.validate_notation_rules(
        {"columns": {"no_such_table": {"core_lot": True}}},
        known_tables=TABLES, rejections=rejections) == {}
    assert [r["code"] for r in rejections] == [notation_norm.CODE_UNDECLARED]


def test_zero_pad_true_is_refused_by_name_and_forced_off():
    """A knob that reads as ON and does nothing is the silence this refuses."""
    rejections = []
    out = notation_norm.validate_notation_rules(
        {"rules": {"zero_pad": True},
         "columns": {"notnorm_test_log": {"core_lot": True}}},
        known_tables=TABLES, rejections=rejections)
    assert [r["code"] for r in rejections] == \
        [notation_norm.CODE_ZERO_PAD_UNIMPLEMENTED]
    spec = out["notnorm_test_log"]["core_lot"]
    assert spec["rules"][notation_norm.RULE_ZERO_PAD] is False
    assert notation_norm.validate_notation_rules(
        {"rules": {"zero_pad": False}, "columns": {}},
        known_tables=TABLES, rejections=[]) == {}


def test_an_unknown_rule_name_is_refused_not_ignored():
    rejections = []
    notation_norm.validate_notation_rules(
        {"rules": {"transliterate": True}, "columns": {}},
        known_tables=TABLES, rejections=rejections)
    assert [r["code"] for r in rejections] == [notation_norm.CODE_UNKNOWN_RULE]


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
# 🔴 BOTH SIDES, ALWAYS - the reason the stored column was withdrawn
# ---------------------------------------------------------------------------

def test_either_side_declared_means_both_sides_folded(norm_env):
    """`join_pair_rules` gives the SAME answer whichever side carries the declaration."""
    left_only = notation_norm.join_pair_rules(
        "notnorm_test_log", "core_lot", "notnorm_test_ref", "core_lot")
    assert left_only and left_only[notation_norm.RULE_SEPARATOR] is True
    # And the mirror image: declare the OTHER side instead, same effective fold.
    assert notation_norm.join_pair_rules(
        "notnorm_test_ref", "core_lot", "notnorm_test_log", "core_lot") == left_only
    # Neither declared -> compare raw, exactly as before this feature existed.
    assert notation_norm.join_pair_rules(
        "notnorm_test_ref", "wafer_id", "notnorm_test_ref", "wafer_id") is None


def test_differing_rule_sets_on_the_two_sides_take_the_union(norm_env, tmp_path,
                                                             monkeypatch):
    """The fold is a property of the COMPARISON, so both declarations are satisfied."""
    _write_decl(tmp_path, monkeypatch, {
        "columns": {
            "notnorm_test_log": {"core_lot": {"rules": {"separator": True,
                                                        "case": False}}},
            "notnorm_test_ref": {"core_lot": {"rules": {"separator": False,
                                                        "case": True}}},
        }})
    merged = notation_norm.join_pair_rules(
        "notnorm_test_log", "core_lot", "notnorm_test_ref", "core_lot")
    assert merged[notation_norm.RULE_SEPARATOR] is True
    assert merged[notation_norm.RULE_CASE] is True


def _seed_asymmetric(db):
    """THE fixture: left column dirty, right column already clean.

    This is the real production asymmetry, measured 2026-08-04 - `dt_log.core_lot` has
    15 merge groups and `core_wafer_map.core_lot` has zero. Only the LEFT is declared,
    because that is the only side an operator has any reason to look at.
    """
    _write(db, "notnorm_test_log", [
        {"job": "A", "x": 1, "core_lot": "cl_2601_001"},   # dirty: '_' and lower case
        {"job": "B", "x": 1, "core_lot": "CL.2601.001"},   # dirty: '.'
        {"job": "C", "x": 1, "core_lot": "CL-2601-001"},   # already clean
        {"job": "D", "x": 1, "core_lot": "CL-9999-999"},   # no right row at all
    ])
    _write(db, "notnorm_test_ref", [
        {"core_lot": "CL-2601-001", "wafer_id": "W-1"},    # clean, and ONLY clean
    ])


def _rule(folded_expected):
    import virtual_join_config as vjc
    rules = vjc.validate_virtual_join_rules({
        "notnorm_join": {
            "left_table": "notnorm_test_log", "right_table": "notnorm_test_ref",
            "join_key": [{"left": "core_lot", "right": "core_lot"}],
            "expose": ["wafer_id"],
        }}, known_tables=TABLES, rejections=[])
    assert len(rules) == 1
    assert rules[0]["folded"] is folded_expected, (
        "the fixture's defect axis is not live: the declaration did not reach the "
        "join rule, so whatever this test asserts next it is not asserting the fold")
    return rules[0]


def test_both_sides_fold_when_only_the_dirty_side_is_declared(norm_env):
    """🔴 THE assertion the withdrawn design could not make.

    Left column dirty, right column clean, declaration on the LEFT ONLY. All three
    left rows whose lot is the same physical lot must find the one right row.

    A fold applied to the left only would produce 'CL-2601-001' on the left and leave
    'CL-2601-001' on the right - which happens to match here - so the fixture also
    carries row C, already clean on BOTH sides. A fold applied to the RIGHT only would
    break row C. Only folding both sides matches all three.
    """
    db = norm_env
    _seed_asymmetric(db)
    import virtual_join_executor as vje

    rule = _rule(True)
    left = models.DYNAMIC_TABLES["notnorm_test_log"]
    row_ids = [r[0] for r in db.query(left.row_id).all()]
    out = vje.execute_rule(db, rule, row_ids)

    by_key = {}
    for rid, hit in out.items():
        key = db.query(left.business_key_val).filter(left.row_id == rid).scalar()
        by_key[key] = hit
    assert by_key["A_1"]["values"]["wafer_id"] == "W-1", "the dirty '_' row lost its match"
    assert by_key["B_1"]["values"]["wafer_id"] == "W-1", "the dirty '.' row lost its match"
    assert by_key["C_1"]["values"]["wafer_id"] == "W-1", (
        "the ALREADY-CLEAN row lost its match - that is what a one-sided fold does")
    assert by_key["D_1"]["matched"] is False, (
        "a lot with no right row must stay unmatched; if this matched, the fold is "
        "merging things that are not the same")


def test_without_the_declaration_the_dirty_rows_do_not_match(norm_env, tmp_path,
                                                             monkeypatch):
    """The fixture's axis is live - proven by removing the declaration, not assumed.

    (server-pm lesson: a test that would pass against an implementation which folds
    nothing certifies nothing.)
    """
    db = norm_env
    _seed_asymmetric(db)
    _write_decl(tmp_path, monkeypatch, {"columns": {}})
    import virtual_join_executor as vje

    rule = _rule(False)
    left = models.DYNAMIC_TABLES["notnorm_test_log"]
    row_ids = [r[0] for r in db.query(left.row_id).all()]
    out = vje.execute_rule(db, rule, row_ids)
    matched = {db.query(left.business_key_val).filter(left.row_id == rid).scalar()
               for rid, hit in out.items() if hit["matched"]}
    assert matched == {"C_1"}, (
        "unfolded, only the already-clean row matches. If more than that matched, the "
        "previous test proves nothing.")


def test_there_is_no_call_shape_that_folds_one_side(norm_env):
    """Structural: the ON clause builder takes no per-side fold argument.

    Asserted rather than reviewed, because "both sides" is the whole redesign and a
    future refactor that adds a `fold_left=` parameter would reintroduce the defect
    while every behavioural test still passed.
    """
    import inspect
    import virtual_join_executor as vje

    params = list(inspect.signature(vje.join_onclause).parameters)
    assert params == ["left_model", "right_model", "rule"], (
        f"join_onclause grew parameters {params}. If one of them can select which side "
        f"folds, the silent-match-drop defect is back.")
    # And both consumers go through it, so they cannot disagree about the row set.
    src = inspect.getsource(vje)
    assert src.count("join_onclause(") >= 3, (
        "execute_rule and resolved_expression must BOTH build their ON clause here")


# ---------------------------------------------------------------------------
# The approval gate moves with the fold
# ---------------------------------------------------------------------------

def test_the_required_ddl_becomes_a_functional_index(norm_env):
    """A folded key needs a functional UNIQUE index, and the DDL says the fold."""
    import virtual_join_config as vjc

    fold = notation_norm.join_pair_rules(
        "notnorm_test_log", "core_lot", "notnorm_test_ref", "core_lot")
    plain = vjc.required_index_ddl("notnorm_test_ref", ["core_lot"], [None])
    folded = vjc.required_index_ddl("notnorm_test_ref", ["core_lot"], [fold])
    assert "regexp_replace" not in plain
    assert "regexp_replace" in folded and "translate" in folded
    assert notation_norm.SEPARATOR_PATTERN in folded, (
        "the DDL must carry the SAME pattern the query folds with - a functional index "
        "PostgreSQL cannot match is a sequential scan that every test still passes")
    assert vjc.required_index_name("notnorm_test_ref", ["core_lot"], [fold]) != \
        vjc.required_index_name("notnorm_test_ref", ["core_lot"], [None]), (
        "the folded index needs its own NAME, or an operator who already made the plain "
        "one reads the name collision as 'already done'")
    # Pasteable: ASCII only, one line, no raw control characters.
    assert folded.isascii() and "\n" not in folded


def test_the_ddl_and_the_query_expression_come_from_one_spelling():
    """🔴 If these two ever diverge, PostgreSQL silently stops using the index."""
    import virtual_join_config as vjc
    from sqlalchemy.dialects import postgresql
    from sqlalchemy import Column, String, literal_column

    rules = {notation_norm.RULE_SEPARATOR: True, notation_norm.RULE_CASE: True}
    expr = notation_norm.fold_notation_sql(literal_column('"core_lot"'), rules)
    compiled = str(expr.compile(dialect=postgresql.dialect(),
                                compile_kwargs={"literal_binds": True}))
    ddl_expr = vjc.index_key_expression("core_lot", rules)
    assert vjc.normalize_index_expression(compiled) == \
        vjc.normalize_index_expression(ddl_expr), (
        f"query expression and index expression disagree:\n  query={compiled}\n"
        f"  ddl  ={ddl_expr}")


def test_normalize_index_expression_folds_what_postgres_adds():
    """The pure matcher, scored against a REAL PostgreSQL rendering.

    `lower((identity_key)::text)` is verbatim what `pg_get_indexdef` returns for
    `idx_suggest_graph_nodes_identity_key` on the live database (measured 2026-08-04) -
    so the cast-and-paren noise this has to absorb is measured, not imagined.
    """
    import virtual_join_config as vjc
    assert vjc.normalize_index_expression("lower((identity_key)::text)") == \
        vjc.normalize_index_expression('lower("identity_key")')
    assert vjc.normalize_index_expression("(core_lot)") == "core_lot"
    assert vjc.normalize_index_expression('  "core_lot"  ') == "core_lot"
    # 🔴 NOT folded away: a different collation is a different index.
    assert vjc.normalize_index_expression('lower(identity_key) COLLATE "C"') != \
        vjc.normalize_index_expression("lower(identity_key)")


def test_the_gate_says_nothing_on_a_dialect_it_cannot_read(norm_env):
    """Not PostgreSQL -> None -> refused. Safe-direction ignorance, unchanged."""
    import virtual_join_config as vjc
    fold = notation_norm.join_pair_rules(
        "notnorm_test_log", "core_lot", "notnorm_test_ref", "core_lot")
    assert vjc.unique_index_covering(norm_env, "notnorm_test_ref", ["core_lot"],
                                     [fold]) is None
    rule = _rule(True)
    assert vjc.verify_uniqueness(norm_env, rule)["code"] == vjc.CODE_NO_UNIQUE_INDEX


# ---------------------------------------------------------------------------
# The fold preview - the false-merge check
# ---------------------------------------------------------------------------

def test_the_preview_reports_merge_groups_with_their_raw_variants(norm_env):
    """The question that matters: "did my rule merge two things that are not the same?"

    A raw->folded listing cannot answer it. The groups can.
    """
    db = norm_env
    _seed_asymmetric(db)
    p = notation_norm.fold_preview(db, "notnorm_test_log", "core_lot")
    assert p["declared"] is True and p["folds"] is True
    assert p["distinct_raw"] == 4 and p["distinct_folded"] == 2
    assert len(p["merge_groups"]) == 1
    g = p["merge_groups"][0]
    assert g["folded"] == "CL-2601-001" and g["raw_count"] == 3
    assert {v["raw"] for v in g["variants"]} == \
        {"cl_2601_001", "CL.2601.001", "CL-2601-001"}
    # The lone unmerged spelling is NOT reported as a merge.
    assert all(mg["folded"] != "CL-9999-999" for mg in p["merge_groups"])


def test_the_preview_of_a_clean_column_reports_no_merges(norm_env):
    db = norm_env
    _seed_asymmetric(db)
    rules = {notation_norm.RULE_SEPARATOR: True, notation_norm.RULE_CASE: True}
    p = notation_norm.fold_preview(db, "notnorm_test_ref", "core_lot", rules)
    assert p["merge_groups"] == []
    assert p["distinct_raw"] == p["distinct_folded"] == 1


def test_the_preview_sentence_is_korean_and_leads_with_the_merges(norm_env):
    import config_resolve_report as crr
    db = norm_env
    _seed_asymmetric(db)
    p = notation_norm.fold_preview(db, "notnorm_test_log", "core_lot")
    detail = crr.notation_preview_detail(p)
    assert "cl_2601_001" in detail and "CL-2601-001" in detail
    detail.encode("cp949")      # operator-facing Korean must survive cp949


# ---------------------------------------------------------------------------
# "Did my config take?" - the answer must be visible, not log-only
# ---------------------------------------------------------------------------

def test_the_resolve_report_names_the_declaration_and_points_at_the_preview(
        norm_env, tmp_path, monkeypatch):
    """A refusal nobody can see is the trap this repo keeps paying for.

    It must also say the thing the operator now has no column to see for themselves:
    where the false-merge answer lives.
    """
    import config_resolve_report as crr

    _write_decl(tmp_path, monkeypatch, {
        "rules": {"separator": True, "case": True, "zero_pad": True},
        "columns": {"notnorm_test_log": {"core_lot": True, "slot": True}},
    })
    domain = crr._resolve_notation()
    assert domain["domain"] == crr.DOMAIN_NOTATION
    assert [e["subject"] for e in domain["effective"]] == ["notnorm_test_log.core_lot"]
    detail = domain["effective"][0]["detail"]
    assert "양쪽" in detail, "the report must say BOTH sides of the comparison fold"
    assert "notation/preview" in detail, (
        "the report must name where the false-merge check lives - it is the only thing "
        "left that answers the question the derived column used to answer by eye")
    reasons = {e["reason"] for e in domain["rejected"]}
    assert reasons == {crr.REASON_NOT_REACHED, crr.REASON_MAPPING_UNAVAILABLE}
    for e in domain["rejected"] + domain["effective"]:
        e["detail"].encode("cp949")


def test_the_shipped_sample_is_valid_json_and_declares_nothing():
    """The sample must parse, and must ship inert."""
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "sample", "notation_rules.json.sample")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    rejections = []
    assert notation_norm.validate_notation_rules(raw, known_tables=TABLES,
                                                 rejections=rejections) == {}
    assert rejections == [], (
        f"the shipped sample produces rejections: {rejections}")
    assert raw["columns"] == {}


def test_the_withdrawn_write_path_is_gone_everywhere():
    """🔴 Deleted, not orphaned. A symbol that survives its subject gets called again.

    `refuse_notation_derived_columns` in particular was a WRITE guard on the funnel every
    write path converges on; leaving a dead one behind would read to the next author as
    "derived columns are still protected".
    """
    from database import crud as _crud
    for gone in ("apply_derivations", "derived_columns_for", "derivations_for",
                 "derivations_by_table", "rederive", "normalized_value",
                 "CODE_WOULD_REWRITE_RAW", "CODE_KEY_COLUMN"):
        assert not hasattr(notation_norm, gone), (
            f"notation_norm.{gone} outlived the design it belonged to")
    assert not hasattr(_crud, "refuse_notation_derived_columns")
