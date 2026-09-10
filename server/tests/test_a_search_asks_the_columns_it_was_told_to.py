# -*- coding: utf-8 -*-
"""`?q=` 는 «선언된 컬럼»을 훑는다 — 기본은 그 표의 신원 (S-125, 판정 255).

🔴 WHAT WAS MEASURED, ON THIS BOX'S `dt_log` (200,215 rows). An unscoped search built 31
`ILIKE` arms over casts AND SIX aliased `LEFT JOIN`s to `dt_inventory` - all six on the
same key, one per virtual-join column - for 2,174 ms, a sequential scan, and a filter
applied only after every join was built.

⛔ THE COST WAS THE DEFAULT, NOT SEARCHING. A plain page built ZERO joins and a
`?cols=`-scoped search built ZERO too, so scoping was already free; nothing had ever
chosen a scope for the unscoped case. With the identity as the default the same search is
3 arms, 0 joins, 117 ms.

⚠️ A SCOPE MUST NEVER BE EMPTY. A search whose scope contributes no condition skips
filtering and returns the WHOLE TABLE with a 200 while the response implies a search
happened - the refusal in `apply_search_filter` was written for exactly that incident.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud                                            # noqa: E402


def _info(**kw):
    return dict(kw)


# ── the default: the row's identity ──────────────────────────────────────────

def test_the_default_is_the_composite_key():
    assert crud.search_scope_default(
        _info(composite_key_source=["dt_job_id", "b_wx", "b_wy"],
              column_types={"a": "string", "b": "number", "c": "string"})) == \
        ("dt_job_id", "b_wx", "b_wy")


def test_a_single_business_key_answers_when_there_is_no_composite_one():
    assert crud.search_scope_default(
        _info(business_key="part_no", column_types={"part_no": "string"})) == ("part_no",)


def test_a_table_declaring_no_identity_still_gets_a_non_empty_scope():
    """⛔ THE ONE THING THIS MUST NOT DO. An empty scope builds no condition, the filter is
    skipped, and the whole table comes back 200 as if it had been searched. `row_id` and
    `business_key_val` are physical on every dynamic table, so this fallback cannot fail."""
    assert crud.search_scope_default({}) == ("row_id", "business_key_val")
    assert crud.search_scope_default(None) == ("row_id", "business_key_val")


def test_an_empty_declaration_is_not_a_declaration():
    """An empty list means the operator declared nothing, not that they declared 「search
    nothing」 - which would be the whole-table answer above."""
    assert crud.search_scope_default(
        _info(composite_key_source=[], business_key="k")) == ("k",)


# ── the declaration, and the names in it that nothing can search ─────────────

def test_a_declared_scope_is_used_verbatim(monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, "t", _info(
        composite_key_source=["k"], column_types={"k": "string", "a": "string"},
        search_columns=["a", "k"]))

    assert crud.resolve_search_columns("t", {"k", "a"}) == (("a", "k"), ())


def test_a_name_nothing_can_search_is_returned_rather_than_dropped(monkeypatch):
    """⛔ NOT SILENTLY IGNORED (판정 255). A `search_columns` entry nothing matches is a
    scope the operator believes is in force; the caller has to be able to name it."""
    monkeypatch.setitem(crud.TABLE_CONFIG, "t", _info(
        composite_key_source=["k"], column_types={"k": "string"},
        search_columns=["k", "typo_here"]))

    used, unknown = crud.resolve_search_columns("t", {"k"})

    assert used == ("k",)
    assert unknown == ("typo_here",)


def test_a_scope_of_nothing_but_unknown_names_falls_back_rather_than_searching_nothing(
        monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, "t", _info(
        composite_key_source=["k"], column_types={"k": "string"},
        search_columns=["typo_a", "typo_b"]))

    used, unknown = crud.resolve_search_columns("t", {"k"})

    assert used == ("k",), "an all-typo scope must not become the whole table"
    assert sorted(unknown) == ["typo_a", "typo_b"]


def test_a_virtual_join_column_counts_as_searchable(monkeypatch):
    """It is not in `column_types` - it is not stored - but the search path resolves it."""
    monkeypatch.setitem(crud.TABLE_CONFIG, "t", _info(
        composite_key_source=["k"], column_types={"k": "string"},
        search_columns=["k", "joined_name"]))

    assert crud.resolve_search_columns("t", {"k", "joined_name"}) == \
        (("k", "joined_name"), ())


def test_without_a_known_set_nothing_is_judged(monkeypatch):
    """⚠️ 「모르는 것」과 「없는 것」은 다르다. A caller that could not enumerate what is
    searchable must not report absences it cannot see."""
    monkeypatch.setitem(crud.TABLE_CONFIG, "t", _info(
        composite_key_source=["k"], column_types={"k": "string"},
        search_columns=["k", "maybe_virtual"]))

    assert crud.resolve_search_columns("t", None) == (("k", "maybe_virtual"), ())


def test_an_undeclared_table_is_the_default_and_never_an_unknown(monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, "t", _info(
        composite_key_source=["k"], column_types={"k": "string"}))

    assert crud.resolve_search_columns("t", {"k"}) == (("k",), ())


# ── the seats that must keep the rule in ONE place ───────────────────────────

def test_the_search_path_reads_the_resolver_and_not_column_types(monkeypatch):
    """🔴 ONE SPELLING. The reload judges the same declaration from a different set of
    known columns; two copies of 「is this searchable」 is how a reload blesses a name the
    search then ignores."""
    import inspect

    import main

    body = inspect.getsource(main.apply_search_filter)
    assert "crud.resolve_search_columns(" in body, body[:1200]
    assert "col_types.keys()" not in body, \
        "the unscoped default must not rebuild itself from column_types"


def test_the_config_reload_names_them_and_uses_the_same_resolver():
    import inspect

    from database import config_watcher

    body = inspect.getsource(config_watcher._report_unsearchable_declarations)
    assert "crud.resolve_search_columns(" in body
    assert "exposed_columns(" in body, "the virtual half comes from the search's own source"
    # ⚠️ A reload that dies over a typo would trade a semantic complaint for an outage,
    # which `load_table_config_or_raise` states is not this file's contract.
    assert "except Exception as exc:" in body

    caller = inspect.getsource(config_watcher)
    assert "_report_unsearchable_declarations(new_config, self.engine)" in caller


def test_the_timing_line_carries_the_arm_count_and_never_the_term():
    """🔴 THE COUNT, NOT THE NAMES OR THE TEXT. The line is always on, so a user-typed
    search term must not land in a permanent file; how many arms it built is the shape of
    the query, which is what a plan question needs."""
    import inspect

    import main

    body = inspect.getsource(main.get_table_data)
    assert "q={'set/' + str(search_scope.get('arms', 0)) if q else '-'}" in body, body[-1400:]
    assert "scope_report=search_scope" in body
    assert "q={q}" not in body


def test_a_real_search_request_answers_and_the_line_says_how_many_arms(client, caplog):
    """🔴 OVER HTTP, BECAUSE THE LAST ROUTE CHANGE SHIPPED A NameError-SHAPED DEFECT THAT
    ONLY THE ROUTE COULD SHOW (the 422 of 09-10 14:33). The scope report is filled inside
    `narrowed_table_query` and read inside `get_table_data`; a version of this that put
    the dict in the wrong function parsed, imported and unit-tested fine and would have
    raised on every search.
    """
    import logging

    with caplog.at_level(logging.INFO):
        response = client.get("/tables/inventory_master/data",
                              params={"q": "PN", "skip": 0, "limit": 5})

    assert response.status_code == 200, response.text

    lines = [r.getMessage() for r in caplog.records if "q=set/" in r.getMessage()]
    assert lines, [r.getMessage() for r in caplog.records][-4:]
    # inventory_master's identity is a single business key -> exactly one arm.
    assert "q=set/1" in lines[-1], lines[-1]


def test_a_request_with_no_search_still_says_so(client, caplog):
    import logging

    with caplog.at_level(logging.INFO):
        response = client.get("/tables/inventory_master/data",
                              params={"skip": 0, "limit": 5})

    assert response.status_code == 200, response.text
    assert any("q=-" in r.getMessage() for r in caplog.records)
