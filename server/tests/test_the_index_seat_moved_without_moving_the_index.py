# -*- coding: utf-8 -*-
"""S-283 · 판정 440·442. 좌석은 옮겼고, «인덱스는 한 글자도 안 옮겼다».

🔴 WHY A MOVE NEEDS A GATE AT ALL. `chain.synthesis.ensure_declared_unique_keys` builds the
UNIFIED join's `key.unique` index through these names, and the virtual join that used to
own them is being removed. If the name a moved function computes were to drift by one
character, the product would build a SECOND index beside the one already standing and stop
recognising the first — and `retract_unrequired_once` would then take the old one, which is
S-248 arriving by a new road (a leftover `uq_vjoin_*` refuses every insert on that table
with 23505 and the group fails permanently on retry).

⛔ THE POPULATION IS DEFINED BY THE PREFIX, so the prefix is a VALUE and not a name to
tidy. It will read wrong once `virtual_join` is gone - the indexes in production are
called `uq_vjoin_*` and renaming the constant would put every one of them outside the
product's reach, while widening it would pull an operator's hand-built index inside.

🔴 AND THE MOVE ALREADY BROKE SOMETHING ONCE, SILENTLY, WHICH IS THE ARGUMENT FOR THIS
FILE. `load_verified_rules` imports the builder inside a `try` whose comment says it can
never break loading. Moving the module made that import fail - and the retraction simply
stopped running, with no error anywhere. An existing gate caught it
(`test_the_required_set_the_retraction_is_handed_names_the_unified_joins_index`); nothing
else would have.
"""
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import join_key_index as jki                             # noqa: E402
from chain import legacy_join_declaration as vjc                                   # noqa: E402

#: 🔴 PINNED LITERALS, NOT `jki.required_index_name(...)` ON BOTH SIDES. A test that
#: compares the function with itself moves whenever the function does, which is the one
#: thing this file exists to notice. These are the spellings standing in databases today.
PINNED = [
    (("s283_right", ["job"], None), "uq_vjoin_s283_right_job_ns"),
    (("s283_right", ["lot", "slot"], None), "uq_vjoin_s283_right_lot_slot_ns"),
]


def test_the_index_name_is_byte_identical_to_what_is_already_built():
    for (table, columns, folds), expected in PINNED:
        assert jki.required_index_name(table, columns, folds) == expected, (
            "the moved seat computes a different name than the index standing in the "
            "database: %r" % jki.required_index_name(table, columns, folds))


def test_the_prefix_is_the_value_it_was():
    """⛔ 판정 440 ③㉠'s first trap. The retraction's population IS this string."""
    assert jki.INDEX_PREFIX == "uq_vjoin_"
    for (table, columns, folds), _ in PINNED:
        assert jki.required_index_name(table, columns, folds).startswith(jki.INDEX_PREFIX)


def test_the_old_spellings_are_the_same_objects_not_copies():
    """🔴 ONE DEFINITION. `virtual_join.config` imports these back while the package is
    dismantled; a re-implementation there would be the second spelling that makes
    PostgreSQL quietly stop using the index."""
    for name in ("required_index_name", "required_index_ddl", "index_key_expression",
                 "unique_index_covering", "column_is_text", "normalize_index_expression"):
        assert getattr(vjc, name) is getattr(jki, name), name
    assert vjc.INDEX_PREFIX == jki.INDEX_PREFIX


def test_the_seat_does_not_reach_back_into_the_package_being_removed():
    """⛔ THE POINT OF MOVING IT. A seat that still imports `virtual_join` stands today and
    breaks at step 4 - which is exactly the half-move this round refused to land."""
    import ast
    import io

    for module in ("chain/join_key_index.py", "chain/unique_key.py"):
        tree = ast.parse(io.open(os.path.join(SERVER_DIR, module), encoding="utf-8").read())
        reached = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "virtual_join"):
                reached.append("%s:%d from %s" % (module, node.lineno, node.module))
            if isinstance(node, ast.Import):
                reached.extend("%s:%d import %s" % (module, node.lineno, a.name)
                               for a in node.names if a.name.startswith("virtual_join"))
        assert reached == [], reached


# ---------------------------------------------------------------------------
# ⛔ WHAT THIS FILE DELIBERATELY DOES NOT MEASURE — both halves are already seated
# ---------------------------------------------------------------------------
#
# 🔴 THE KEY EXPRESSION HAS TWO GATES ALREADY, AND I WROTE A THIRD BEFORE CHECKING.
# 판정 442 ② asked for an execution gate and said to look for one first. I grepped, had
# `test_ledger_v2_pg.py` IN THE HIT LIST, opened a different file, and concluded none
# existed. QA opened it. Both halves stand at HEAD:
#
#   간다 (spelling)    `test_one_key_expression_at_every_seat_that_compares_a_key.py`
#                      (S-245) — eleven cases scoring four renderings against one fixture,
#                      and its docstring says plainly that it scores spelling, not running
#   돈다 (running)     `test_ledger_v2_pg.py::test_postgres_right_unique_index_is_used_by_
#                      the_join_probe` — `SET LOCAL enable_seqscan = off`, probe built from
#                      `index_key_expression`, EXPLAIN, asserts the index NAME and
#                      「Index Scan」. Stronger than what I wrote: forcing seqscan off proves
#                      the index is USABLE, where a large fixture only shows it was cheapest
#
# So this file stays about THE MOVE — that the names, the prefix and the identity of the
# definitions did not shift - and adds no second door to a property two gates already hold.
