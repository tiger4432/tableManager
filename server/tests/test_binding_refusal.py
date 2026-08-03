"""A refusal must name its own cause (`bonding_plan.explain_binding_refusal`).

WHY THIS FILE EXISTS. Three times in two weeks a declaration was valid on disk
and silently did not take, and every one of them surfaced as the same sentence:
"...가 선언돼 있지 않습니다".

  * board O4 - the chain worker read a rule before its own TABLE_CONFIG and
    refused it without retrying.
  * board O7 - a rule pointed at a mapper module that was not on disk; it passed
    config rebuild, the full suite, and lead-PM review.
  * 2026-08-04 live - `stages.bonding.bin_map.columns.x` named `"x"` on a table
    (`dt_log`) whose coordinate columns are `dt_x`/`dt_y`. The declaration was
    present, well-formed, pointed at a declared table, and named every required
    role. The message said it was not declared. It was.

The durable fix is not any one config: it is that the refusal states WHICH check
failed, what it looked for, and what it found. This file pins that per cause, so
a future refactor cannot quietly collapse the distinct sentences back into one
generic string - which is exactly the state the three incidents above were in.

[Isolation] Table names carry a `binref_test_` prefix that cannot exist in a
user's live config (conftest initialises dynamic models from the real config at
import, so a colliding name silently swaps the schema under the fixture).
"""
import pytest

import bonding_plan
import transfer_plan
from database import crud, models

REFUSAL_TABLES = {
    "binref_test_map": {
        "business_key": "cell_key",
        "column_types": {
            "cell_key": "string", "dt_lot": "string", "dt_slot": "string",
            "dt_x": "number", "dt_y": "number", "c_bn": "string",
        },
        "map_key_columns": ["dt_lot", "dt_slot"],
    },
}

ROLES = ("lot", "slot", "x", "y", "bin")

GOOD_COLUMNS = {"lot": "dt_lot", "slot": "dt_slot",
                "x": "dt_x", "y": "dt_y", "bin": "c_bn"}


@pytest.fixture()
def refusal_env(db_session):
    models.init_dynamic_models(REFUSAL_TABLES)
    crud.TABLE_CONFIG.update(REFUSAL_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    return db_session


def _explain(src):
    return bonding_plan.explain_binding_refusal(
        src, ROLES, label="bin_map", where="stages.<stage>.bin_map")


# ---------------------------------------------------------------------------
# The vocabulary is borrowed, not invented
# ---------------------------------------------------------------------------

def test_vocabulary_matches_its_canonical_definitions():
    """A second spelling of an existing word is a silent fork.

    `bonding_plan` spells these three literally so it takes no dependency on the
    admin-report or enrichment stacks. That is only safe while the literals stay
    equal to the definitions they borrow from - this test is what makes that
    true, rather than true-for-now.
    """
    import config_resolve_report
    import enrichment_candidates

    assert bonding_plan.BINDING_NOT_DECLARED == config_resolve_report.REASON_NOT_DECLARED
    assert (bonding_plan.BINDING_MAPPING_UNAVAILABLE
            == config_resolve_report.REASON_MAPPING_UNAVAILABLE)
    assert (bonding_plan.BINDING_COLUMN_MISSING
            == enrichment_candidates.REASON_CANDIDATE_COLUMN_MISSING)


# ---------------------------------------------------------------------------
# Distinct causes must produce distinct, self-explaining sentences
# ---------------------------------------------------------------------------

def test_declared_but_column_name_wrong_says_so(refusal_env):
    """THE LIVE 2026-08-04 CAUSE. Declaration present, table declared, every
    required role named - and two of the column names do not exist.

    The old sentence ("선언돼 있지 않습니다") was FALSE here, and being false is
    what made this a manual bisect instead of a read.
    """
    src = {"table": "binref_test_map",
           "columns": dict(GOOD_COLUMNS, x="x", y="y")}
    reason, detail = _explain(src)

    assert reason == bonding_plan.BINDING_COLUMN_MISSING
    # names the offending roles AND the names it looked for
    assert "x" in detail and "y" in detail
    assert "`x`" in detail and "`y`" in detail
    # names the table it looked on
    assert "binref_test_map" in detail
    # offers what the table actually has, so the operator can fix it from here
    assert "dt_x" in detail and "dt_y" in detail
    # the roles that DID resolve are not accused
    assert "`dt_lot`" not in detail
    # and it does not claim the declaration is absent
    assert "선언이 없습니다" not in detail


def test_absent_declaration_says_absent(refusal_env):
    """The other side of the same coin: nothing declared is NOT a defect, and
    its sentence must not read like the typo case above."""
    reason, detail = _explain(None)

    assert reason == bonding_plan.BINDING_NOT_DECLARED
    assert "선언이 없습니다" in detail
    # tells the operator what a valid declaration needs
    assert "table" in detail and "columns" in detail
    for role in ROLES:
        assert role in detail
    # must NOT borrow the column-missing vocabulary
    assert bonding_plan.BINDING_COLUMN_MISSING not in (reason or "")


def test_table_not_in_table_config_says_which_table(refusal_env):
    """The "declare tables first, rules second" trap (board O4's shape).

    The rule is fine; the table it points at was never declared. The sentence
    must name the table AND list what IS declared, because the usual cause is a
    typo one character away from a real name.
    """
    reason, detail = _explain({"table": "binref_test_nope",
                               "columns": dict(GOOD_COLUMNS)})

    assert reason == bonding_plan.BINDING_MAPPING_UNAVAILABLE
    assert "binref_test_nope" in detail
    assert "table_config.json" in detail
    assert "binref_test_map" in detail        # the declared neighbour


def test_missing_role_key_is_not_the_same_sentence_as_a_wrong_column(refusal_env):
    """A role never named and a role named at a column that does not exist are
    two different mistakes with two different fixes."""
    src = {"table": "binref_test_map",
           "columns": {k: v for k, v in GOOD_COLUMNS.items() if k != "bin"}}
    reason, detail = _explain(src)

    assert reason == bonding_plan.BINDING_NOT_DECLARED
    assert "bin" in detail
    assert "lot" in detail and "slot" in detail   # what IS declared

    other_reason, other_detail = _explain(
        {"table": "binref_test_map", "columns": dict(GOOD_COLUMNS, bin="nope_col")})
    assert other_reason == bonding_plan.BINDING_COLUMN_MISSING
    assert detail != other_detail


def test_malformed_shape_says_what_it_read(refusal_env):
    for src in ({"table": "binref_test_map", "columns": "dt_x"},
                {"table": "", "columns": dict(GOOD_COLUMNS)},
                ["binref_test_map"]):
        reason, detail = _explain(src)
        assert reason == bonding_plan.BINDING_MAPPING_UNAVAILABLE, src
        assert detail


def test_every_cause_produces_a_distinct_sentence(refusal_env):
    """The anti-collapse pin. A refactor that funnels these back into one
    generic string fails HERE, not six months later in production.

    The reason vector is pinned alongside the sentences: a collapse that keeps
    the strings incidentally distinct (a shorter generic sentence, say) but
    re-labels a wrong column name as `not_declared` is the SAME defect wearing a
    different coat, and the sentence-uniqueness check alone walks past it.
    """
    causes = {
        "absent": (None, bonding_plan.BINDING_NOT_DECLARED),
        "table_undeclared": ({"table": "binref_test_nope",
                              "columns": dict(GOOD_COLUMNS)},
                             bonding_plan.BINDING_MAPPING_UNAVAILABLE),
        "column_name_wrong": ({"table": "binref_test_map",
                               "columns": dict(GOOD_COLUMNS, x="x")},
                              bonding_plan.BINDING_COLUMN_MISSING),
        "role_absent": ({"table": "binref_test_map",
                         "columns": {k: v for k, v in GOOD_COLUMNS.items()
                                     if k != "bin"}},
                        bonding_plan.BINDING_NOT_DECLARED),
        "malformed": ({"table": "binref_test_map", "columns": "dt_x"},
                      bonding_plan.BINDING_MAPPING_UNAVAILABLE),
    }
    sentences = {}
    for name, (src, expected_reason) in causes.items():
        reason, detail = _explain(src)
        assert reason == expected_reason, (name, reason)
        sentences[name] = detail
    assert len(set(sentences.values())) == len(sentences), sentences


def test_resolvable_binding_is_not_refused(refusal_env):
    """The diagnostic must not invent a refusal for a binding that resolves -
    otherwise the sentence and the behaviour disagree and the sentence wins the
    operator's attention."""
    assert _explain({"table": "binref_test_map",
                     "columns": dict(GOOD_COLUMNS)}) == (None, None)


def test_diagnostic_agrees_with_the_resolver(refusal_env):
    """Scored against the real predicate, not against itself.

    `_resolve_model_columns` is what actually accepts or rejects. If the two ever
    disagree the operator is told a story about a binding that behaves
    differently - the exact failure mode this whole change exists to end.
    """
    cases = [
        None,
        {},
        ["x"],
        {"table": "binref_test_map"},
        {"table": "binref_test_map", "columns": {}},
        {"table": "binref_test_map", "columns": "dt_x"},
        {"table": "binref_test_nope", "columns": dict(GOOD_COLUMNS)},
        {"table": "binref_test_map", "columns": dict(GOOD_COLUMNS)},
        {"table": "binref_test_map", "columns": dict(GOOD_COLUMNS, x="x")},
        {"table": "binref_test_map", "columns": dict(GOOD_COLUMNS, bin="nope")},
        {"table": "binref_test_map",
         "columns": {k: v for k, v in GOOD_COLUMNS.items() if k != "y"}},
        # optional (non-required) role at a bad column: still resolves, and the
        # existing `column_unresolved` demotion carries that fact separately.
        {"table": "binref_test_map", "columns": dict(GOOD_COLUMNS, extra="nope")},
    ]
    for src in cases:
        model, _cols = transfer_plan._resolve(src, required=ROLES)
        reason, detail = _explain(src)
        assert (model is None) == (reason is not None), (src, model, reason)
        assert (model is None) == (detail is not None), (src, model, detail)


# ---------------------------------------------------------------------------
# cp949: these sentences reach a Korean Windows console
# ---------------------------------------------------------------------------

def test_sentences_survive_a_cp949_console(refusal_env):
    """A refusal that crashes the console it is printed to has refused twice.

    U+2014 (em dash) and emoji are not encodable in cp949; U+2015 is.
    """
    for src in (None, {}, ["x"],
                {"table": "binref_test_map", "columns": "dt_x"},
                {"table": "binref_test_nope", "columns": dict(GOOD_COLUMNS)},
                {"table": "binref_test_map", "columns": dict(GOOD_COLUMNS, x="x")},
                {"table": "binref_test_map",
                 "columns": {k: v for k, v in GOOD_COLUMNS.items() if k != "bin"}}):
        _reason, detail = _explain(src)
        detail.encode("cp949")     # raises UnicodeEncodeError on a bad character
        assert "—" not in detail


# ---------------------------------------------------------------------------
# The reader actually delivers the named cause (not just the helper)
# ---------------------------------------------------------------------------

def _stage(bin_map):
    return {"source_kind": "tape", "bin_map": bin_map,
            "source": {"identity": {"compose": ["lot", "slot"]}}}


def test_bins_block_carries_the_named_cause(refusal_env):
    """`_bins_block` is the site the live user hit. Pin it end to end so an
    improvement to the helper cannot sit behind an unchanged call site."""
    stage = _stage({"table": "binref_test_map",
                    "columns": dict(GOOD_COLUMNS, x="x", y="y")})
    block = transfer_plan._bins_block(
        refusal_env, stage, "L1", "01", None, set(), set(), None, [], True, None)

    assert block["axis"] == "unavailable"
    assert block["reason"] == bonding_plan.BINDING_COLUMN_MISSING
    assert "binref_test_map" in block["detail"]
    assert "dt_x" in block["detail"]
    # `entries` stays None: "no axis" is not "no BINs"
    assert block["entries"] is None

    absent = transfer_plan._bins_block(
        refusal_env, _stage(None), "L1", "01", None, set(), set(), None, [], True, None)
    assert absent["reason"] == bonding_plan.BINDING_NOT_DECLARED
    assert absent["detail"] != block["detail"]


def test_lot_membership_refusal_uses_the_same_diagnostic(refusal_env):
    """Two sources, one vocabulary. If `lot_membership` grew its own sentence
    rules, improving one would leave the other on the old generic string."""
    stage = {"source": {"lot_membership": {"table": "binref_test_map",
                                           "columns": {"lot": "dt_lot",
                                                       "slot": "nope_col"}}}}
    reason, detail = transfer_plan._lot_membership_refusal(stage)
    assert reason == bonding_plan.BINDING_COLUMN_MISSING
    assert "lot_membership" in detail
    assert "nope_col" in detail

    reason2, detail2 = transfer_plan._lot_membership_refusal({"source": {}})
    assert reason2 == bonding_plan.BINDING_NOT_DECLARED
    assert detail2 != detail
