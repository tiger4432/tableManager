# -*- coding: utf-8 -*-
"""S-181. Null is ONE axis, and every seat that folds a key now gives it one answer.

Owner: 「null 땜에 다 꼬임 — 가상 조인 등 모든 영역」. Measured before the change, on this
box, the same input got five different answers:

    compose_business_key   None / '' / '  '  ->  ''          (all the same)
    canonical_key_value    None -> None,  '' -> ''           (two different keys)
    join_onclause          `left == right`  ->  NULL matches NOTHING, not even NULL
    ledger identity key    '' is a VALUE, None is missing
    plain UNIQUE index     two NULLs are DISTINCT, '' is a value

🔴 THE FOLD INVENTS NO PREDICATE (판정 284·287). Blankness already had one name at the write
door — `is_blank_value`, pinned by `contracts/blank_predicate`, with a SQL twin in
`blank_sql_condition`. Ruling 284 IS that predicate's rule, so `fold_key_value` calls it
(through `is_blank_key_part`, which adds only the identity-path rule that a non-finite float
is not an identity). A second spelling of 「blank」 is what produced the five answers.

🔴 AND WHERE KEYS ARE COMPARED, NULL EQUALS NULL (판정 285) — the opposite of SQL's rule.
Both halves are `coalesce(col, '')`: the join compares that way and the index is built that
way, because an expression index PostgreSQL cannot match is not an index, it is a sequential
scan nobody ordered.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import map_overlay                                                   # noqa: E402
import virtual_join.config as vjc                                    # noqa: E402
from database import crud                                            # noqa: E402

TABLE = "s181_test_table"
PLAIN = "s181_test_plain"

BLANKS = (None, "", "  ", "\t")


@pytest.fixture(autouse=True)
def declared():
    crud.TABLE_CONFIG[TABLE] = {
        "business_key": "k",
        "composite_key_source": ["lot", "slot"],
        "composite_key_separator": "|",
        "column_types": {"k": "string", "lot": "string", "slot": "string"},
        "null_policy": {"slot": "skip"},
    }
    crud.TABLE_CONFIG[PLAIN] = {
        "business_key": "k",
        "composite_key_source": ["lot", "slot"],
        "composite_key_separator": "|",
        "column_types": {"k": "string", "lot": "string", "slot": "string"},
    }
    yield
    crud.TABLE_CONFIG.pop(TABLE, None)
    crud.TABLE_CONFIG.pop(PLAIN, None)


# ---------------------------------------------------------------------------
# 1. 🔴 Fixtures A and B: every blank folds to the same thing, everywhere
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("blank", BLANKS)
def test_every_blank_folds_to_none(blank):
    """Fixture A (None) and B ('') must give the SAME answer, and 판정 284's supplement
    puts whitespace-only inside the rule — which the write door's predicate already did."""
    assert crud.fold_key_value(PLAIN, "slot", blank) is None


@pytest.mark.parametrize("blank", BLANKS)
def test_the_map_overlay_seat_agrees(blank):
    """This seat used to keep `None` and return `''` for `''` — one key read as two."""
    assert map_overlay.canonical_key_value(blank, "string") is None
    assert map_overlay.canonical_key_value(blank, "number") is None


@pytest.mark.parametrize("blank", BLANKS)
def test_the_key_gate_seat_agrees(blank):
    assert crud.is_blank_key_part(blank) is True


@pytest.mark.parametrize("blank", BLANKS)
def test_the_ledger_identity_seat_agrees(blank):
    from ledger.roleframe import _fold_identity_key

    assert _fold_identity_key(blank) is None


def test_a_real_value_is_never_folded():
    """The sensitivity control: a fold that swallowed everything would pass every test
    above and lose every key."""
    for seat in (lambda v: crud.fold_key_value(PLAIN, "slot", v),
                 lambda v: map_overlay.canonical_key_value(v, "string")):
        assert seat("S1") == "S1"
    assert crud.is_blank_key_part("S1") is False


def test_a_non_finite_float_is_still_not_an_identity():
    """⛔ THE NARROWER PREDICATE WOULD HAVE LET THIS BACK IN. `is_blank_value(nan)` is
    False and `compose_business_key("t", ["A", nan, "C"])` is `"A_nan_C"` — a string that
    behaves as an identity. The identity path keeps its own superset, and the fold uses it."""
    assert crud.fold_key_value(PLAIN, "slot", float("nan")) is None
    assert crud.is_blank_value(float("nan")) is False


# ---------------------------------------------------------------------------
# 2. The policy cell: absent means today, `skip` means everywhere
# ---------------------------------------------------------------------------

def test_absent_policy_is_not_a_policy():
    """🔴 THE REGRESSION GATE. A table with no cell must be 「not one character different」,
    which is what makes this safe to add to a live deployment."""
    assert crud.key_null_policy(PLAIN, "slot") is None
    assert crud.key_fold_drops_row(PLAIN, "slot", None) is False
    assert crud.key_fold_drops_row(PLAIN, "slot", "") is False


def test_skip_drops_the_row_at_every_seat():
    assert crud.key_null_policy(TABLE, "slot") == crud.KEY_NULL_SKIP
    for blank in BLANKS:
        assert crud.key_fold_drops_row(TABLE, "slot", blank) is True
    assert crud.key_fold_drops_row(TABLE, "slot", "S1") is False


def test_a_column_without_a_policy_in_a_table_that_has_one_is_untouched():
    """The cell is per column, so declaring it for `slot` must not judge `lot`."""
    assert crud.key_null_policy(TABLE, "lot") is None
    assert crud.key_fold_drops_row(TABLE, "lot", None) is False


def test_an_unknown_policy_value_is_not_obeyed():
    """⛔ 판정 286 REMOVED `placeholder`. A config still carrying one must not be read as
    some third behaviour — the only value with meaning is `skip`."""
    crud.TABLE_CONFIG[PLAIN]["null_policy"] = {"slot": "placeholder:-"}
    assert crud.key_null_policy(PLAIN, "slot") is None


# ---------------------------------------------------------------------------
# 3. 🔴 The index and the join are ONE spelling
# ---------------------------------------------------------------------------

def test_the_index_expression_is_null_safe():
    assert vjc.index_key_expression("dt_job") == "coalesce(\"dt_job\", '')"
    assert "coalesce" in vjc.required_index_ddl("t", ["a", "b"])


def test_nulls_not_distinct_is_not_the_shape():
    """⛔ IT SATISFIES 285 AND BREAKS 284. Measured on this box: under
    `NULLS NOT DISTINCT` a second `('L1', NULL)` is refused — good — but a second
    `('L1','')` is ALSO refused as a separate key, so a blank stays a value. `coalesce`
    satisfies both rulings, on every version."""
    ddl = vjc.required_index_ddl("t", ["a"])
    assert "NULLS NOT DISTINCT" not in ddl.upper()


def test_the_index_name_carries_the_shape():
    """So the old index and the new one can COEXIST while a deployment migrates — without
    it, `CREATE` collides with the name a plain UNIQUE already holds and an operator has
    to drop an index blind on a live table."""
    assert vjc.required_index_name("t", ["a"]).endswith("_ns")


def test_the_join_compares_the_same_expression_the_index_is_built_on():
    """🔴 A QUERY WHOSE EXPRESSION DIFFERS FROM THE INDEX'S DOES NOT FAIL — it silently
    stops using the index. So the two spellings are scored against each other here."""
    from sqlalchemy import Column, MetaData, String, Table
    from sqlalchemy.dialects import postgresql

    from virtual_join import executor as vje

    metadata = MetaData()
    left = Table("s181_left", metadata, Column("a", String))
    right = Table("s181_right", metadata, Column("b", String))
    clause = vje.join_onclause(
        left.c, right.c, {"join_key": [{"left": "a", "right": "b", "fold": None}]})
    rendered = str(clause.compile(dialect=postgresql.dialect(),
                                  compile_kwargs={"literal_binds": True})).lower()
    assert rendered.count("coalesce") == 2, rendered
    # ⚠️ THE COLUMN IS TABLE-QUALIFIED IN A QUERY AND BARE IN AN INDEX — that difference is
    # PostgreSQL's own and does not stop the match. What has to agree is the WRAPPER and
    # its sentinel, which is what the two assertions below pin.
    squashed = rendered.replace(" ", "")
    assert "coalesce(s181_left.a,'')" in squashed, squashed
    assert "coalesce(s181_right.b,'')" in squashed, squashed
    assert vjc.index_key_expression("a").replace('"', "") == "coalesce(a, '')"


def test_the_normaliser_folds_case_but_not_literals():
    """MEASURED: we build `coalesce`, PostgreSQL renders `COALESCE`, and the two normalised
    to different strings — a correctly built index went unrecognised and every join went
    unapproved. Folding the WHOLE string would turn `'A'` into `'a'` and accept an index
    built on a different value."""
    assert (vjc.normalize_index_expression("COALESCE(dt_job, ''::character varying)")
            == vjc.normalize_index_expression(vjc.index_key_expression("dt_job")))
    assert "'A'" in vjc._casefold_outside_literals("COALESCE(x, 'A')")


def test_an_escaped_quote_inside_a_literal_does_not_end_it():
    """`''` is SQL's escaped quote. A naive split would treat it as a delimiter and start
    lowercasing the literal's own text."""
    assert vjc._casefold_outside_literals("F(X, 'A''B')") == "f(x, 'A''B')"
