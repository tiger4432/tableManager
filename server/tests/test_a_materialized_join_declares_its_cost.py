# -*- coding: utf-8 -*-
"""S-189 ⓐ. A join that writes must say what a change to it costs.

🔴 THE NUMBER IS WHY THIS EXISTS. Measured on this box: `dt_log` carries 606,215 rows and one
`dt_job` value covers 70,800 of them. Materialising means a change to ONE referenced row
rewrites every target row carrying that key — so at the owner's IO spec (≤1.3 s/1k) a single
edit is ≈92 seconds of writing.

⛔ SO THE CEILING HAS NO DEFAULT (판정 302). A number the product picks is a number nobody
reads, and picking one would make the product the author of a 92-second write it never
mentioned. `materialize: true` without `max_rewrite_rows` is refused BY NAME, and the refusal
tells the operator the query that counts it. Same posture as `occurred_at_basis`: what can be
declared is declared, and what is not declared is refused rather than guessed.

⛔ AND OVER THE CEILING IS A REFUSAL, NOT A TRUNCATION. Writing up to the ceiling leaves the
table part new and part old with nothing saying which row is which — a screen then shows a
quietly wrong answer, which is worse than a loud stop.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, text

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from chain import legacy_join_declaration as vjc                                     # noqa: E402

KNOWN = {
    "left_t": {"column_types": {"k": "string", "frame": "string"}},
    "right_t": {"column_types": {"k": "string", "frame": "string"}},
}
BASE = {"left_table": "left_t", "right_table": "right_t",
        "join_key": [{"left": "k", "right": "k"}], "expose": ["frame"]}


def _rule(**cells):
    return vjc._validate_join("r", dict(BASE, **cells), KNOWN)


# ---------------------------------------------------------------------------
# the grammar
# ---------------------------------------------------------------------------

def test_materialize_without_a_ceiling_is_refused_by_name():
    rule, message, code, _ = _rule(materialize=True)
    assert rule is None and code == vjc.CODE_NO_REWRITE_CAP
    # 🔴 THE REFUSAL HANDS OVER THE WORK, which is this module's whole posture: a rejected
    # declaration tells the operator what to write, never just that it is wrong.
    assert "max_rewrite_rows" in message
    assert "count(*)" in message, "it must say how to count the number it is asking for"


def test_a_ceiling_must_be_a_positive_count():
    for bad in (0, -1, "1000", 12.5, True, None):
        rule, _m, code, _ = _rule(materialize=True, max_rewrite_rows=bad)
        assert rule is None and code == vjc.CODE_NO_REWRITE_CAP, bad


def test_a_declared_ceiling_is_carried_with_the_left_index_it_needs():
    rule, message, code, _ = _rule(materialize=True, max_rewrite_rows=1000)
    assert code is None, (message, code)
    assert rule["materialize"] is True and rule["max_rewrite_rows"] == 1000
    assert rule["required_left_index"] == vjc.required_left_index_name("left_t", ["k"])


def test_a_rule_that_does_not_materialize_is_refused_by_name_now(monkeypatch):
    """🪦 [S-283, 판정 446] THIS TEST ASSERTED THE OPPOSITE, and the old line is kept here
    because its premise was a BOX reading that has since been withdrawn: 「⚠️ THE REGRESSION
    LINE. Both production rules on this box are read-time today, and this piece must not
    change a single thing about them.」

    Read-time rules are gone (ruling 461), so `materialize: false` no longer describes a
    rule this loader can stand - it describes the retired half - and it is refused by name
    rather than standing and doing nothing.
    """
    rule, message, code, _ = _rule()

    assert rule is None
    assert code == "read_time_retired", code
    assert "chain_rules.json" in message, message


def test_materialize_must_be_a_boolean():
    rule, message, code, _ = _rule(materialize="yes")
    assert rule is None and code == vjc.CODE_SHAPE and "true or false" in message


# ---------------------------------------------------------------------------
# 🔴 the two indexes answer opposite questions
# ---------------------------------------------------------------------------

def test_the_left_index_is_not_unique_and_the_right_one_is():
    """🔴 THIS IS THE WHOLE REASON THE LEFT HELPER EXISTS. The right key must be UNIQUE — that
    is the approval condition. The left key must NOT be: 70,800 rows share one on this box,
    and that sharing IS the fan-out. Reusing the right DDL would order an index that cannot
    be built."""
    left = vjc.required_left_index_ddl("left_t", ["k"])
    right = vjc.required_index_ddl("right_t", ["k"], None)
    assert "UNIQUE" not in left and "UNIQUE" in right
    assert vjc.required_left_index_name("left_t", ["k"]) != vjc.required_index_name(
        "right_t", ["k"], None)
    assert "CONCURRENTLY" in left, "it must not lock writes on a production table either"


# ---------------------------------------------------------------------------
# 🔴 counting before writing — and folding both sides
# ---------------------------------------------------------------------------

@pytest.fixture()
def counted(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "s189.db"))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE left_t (k TEXT, frame TEXT)"))
        for value in (None, None, None, "", "A"):
            conn.execute(text("INSERT INTO left_t (k, frame) VALUES (:k, 'f')"),
                         {"k": value})
    return engine


def test_a_blank_key_counts_the_same_rows_as_a_null_one(counted):
    """🔴 THE DISCRIMINATOR, AND IT CAUGHT A REAL BUG. 판정 285 says NULL = NULL where keys are
    compared, and `''` is NULL (판정 284). The fixture holds three NULLs and one `''`, so a
    count that folded only ONE side would answer 3 or 1 here — never 4.

    ⛔ MEASURED BEFORE IT WAS WRITTEN: the first version bound `fold_key_value`'s answer
    directly, which is `None` for a blank, against an expression that folds the column to
    `''`. `'' = NULL` is NULL, and the live count came back ZERO for a key this box has
    70,800 rows of. The two folds are halves of a pair written for an INDEX, where both sides
    pass through the same SQL; crossing that boundary is what needed saying.
    """
    rule, _m, code, _ = _rule(materialize=True, max_rewrite_rows=10)
    assert code is None
    with counted.connect() as conn:
        assert vjc.rewrite_row_count(conn, rule, [None]) == 4
        assert vjc.rewrite_row_count(conn, rule, [""]) == 4
        assert vjc.rewrite_row_count(conn, rule, ["A"]) == 1
        assert vjc.rewrite_row_count(conn, rule, ["absent"]) == 0


def test_over_the_ceiling_is_refused_whole_and_names_the_numbers(counted):
    rule, _m, _c, _f = _rule(materialize=True, max_rewrite_rows=3)
    with counted.connect() as conn:
        counted_rows = vjc.rewrite_row_count(conn, rule, [None])
    refusal = vjc.rewrite_refusal(rule, counted_rows)
    assert refusal and "4" in refusal and "3" in refusal and "left_t" in refusal
    # ⛔ The word that matters: it does not offer to write the first three.
    assert "Refused whole" in refusal


def test_under_the_ceiling_is_not_refused(counted):
    rule, _m, _c, _f = _rule(materialize=True, max_rewrite_rows=10)
    assert vjc.rewrite_refusal(rule, 4) is None


def test_the_cost_gate_only_ever_sees_a_materializing_rule():
    """⚠️ THIS USED TO READ 「a read-time rule is never refused for cost」, and that sentence
    had a subject the loader can no longer produce: a validated rule with
    `materialize: False`. Rather than assert a ceiling against a rule shape that cannot
    exist, the property is stated where it is still true - every rule reaching
    `rewrite_refusal` materialises, and the ceiling is the one its declaration wrote.
    """
    rule, _m, code, _f = _rule(materialize=True, max_rewrite_rows=1000)
    assert code is None and rule["materialize"] is True

    assert vjc.rewrite_refusal(rule, 999) is None
    assert vjc.rewrite_refusal(rule, 1001) is not None
