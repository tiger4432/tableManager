# -*- coding: utf-8 -*-
"""S-283 · 판정 440·442. 좌석은 옮겼고, «인덱스는 한 글자도 안 옮겼다».

🔴 WHY A MOVE NEEDS A GATE AT ALL. `chain.builtins.ensure_declared_unique_keys` builds the
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

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import join_key_index as jki                             # noqa: E402
import virtual_join.config as vjc                                   # noqa: E402

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


def test_the_ddl_and_the_join_render_the_key_through_one_function():
    """🔴 [판정 442 ②] THE GUARANTEE THAT DOES NOT ANNOUNCE ITSELF WHEN IT BREAKS.
    PostgreSQL uses an expression index only when the query's expression MATCHES it, so a
    second spelling is not an error - it is a sequential scan with every test green.

    ⚠️ THIS SCORES THE SPELLING, WHICH IS 「간다」. The execution gate below is 「돈다」 and
    needs a PostgreSQL; S-245's file makes the same distinction about itself in its own
    docstring, and this one is here because the seat MOVED, not because the rule is new.
    """
    from virtual_join import executor as vje

    rendered = jki.index_key_expression("core_lot", None, "s283_right")
    assert rendered in jki.required_index_ddl("s283_right", ["core_lot"], None)
    assert vje.join_onclause.__module__.startswith("virtual_join"), (
        "the on-clause moved; re-point this gate at its new home rather than deleting it")


# ---------------------------------------------------------------------------
# 🔴 [판정 442 ②] 「돈다」 — the one nobody had. It asks PostgreSQL, not the source.
# ---------------------------------------------------------------------------

@pytest.mark.pg
def test_postgresql_actually_uses_the_index_the_product_asked_for():
    """🔴 THE GATE 442 ASKED FOR, AND IT DID NOT EXIST. Every assertion above - and every
    one in S-245's file - compares STRINGS. The failure this protects against is that the
    two strings differ and PostgreSQL silently plans a sequential scan, which no string
    comparison can see and no green suite reports. So this builds the index with the
    product's own DDL, asks the product for the query expression, and reads the PLAN.

    ⚠️ It skips without a declared test database. That is why the spelling gates above stay
    - a skipped test reports nothing.
    """
    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:                                     # pragma: no cover
        pytest.skip("psycopg2 is not importable: %s" % exc)

    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    scratch = "assy_pytest_s283"
    table, column = "s283_right", "core_lot"
    with _declared_as_test_database(url):
        engine = create_engine(url, poolclass=NullPool,
                               connect_args=scratch_connect_args(scratch))
        admin = create_engine(url, poolclass=NullPool)
        try:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
                conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        except OperationalError as exc:
            pytest.skip("PostgreSQL is not reachable: %s"
                        % str(exc).strip().splitlines()[0])
        try:
            with engine.begin() as conn:
                conn.execute(text('CREATE TABLE "%s" (row_id text, "%s" text)'
                                  % (table, column)))
                # Enough rows that a sequential scan is not simply the cheaper plan - the
                # question is whether the planner CAN use the index, and on a tiny table it
                # rightly would not bother.
                conn.execute(text(
                    'INSERT INTO "%s" (row_id, "%s") SELECT g::text, '
                    "'CL-' || g::text FROM generate_series(1, 20000) g" % (table, column)))

            # 🔴 THE PRODUCT'S OWN DDL, not a hand-written CREATE INDEX. If the two ever
            # part company, this gate is measuring something the product does not build.
            ddl = jki.required_index_ddl(table, [column], None)
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text(ddl))
                conn.execute(text('ANALYZE "%s"' % table))

            expression = jki.index_key_expression(column, None, table)
            with engine.begin() as conn:
                plan = "\n".join(row[0] for row in conn.execute(text(
                    'EXPLAIN SELECT row_id FROM "%s" WHERE %s = %s'
                    % (table, expression, "'cl-1'"))).fetchall())

            assert jki.required_index_name(table, [column], None) in plan, (
                "PostgreSQL planned this without the index the product built, which is what "
                "two spellings of the key expression look like - no error, no red test, and "
                "a sequential scan on every read:\n%s\nexpression: %s\nddl: %s"
                % (plan, expression, ddl))
        finally:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            engine.dispose()
            admin.dispose()
