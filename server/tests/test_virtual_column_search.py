"""VIRTUAL COLUMN SEARCH ― the filter must run on the value the user SEES.

[The defect this closes]
Virtual join stage 1 attached joined values AFTER the page was selected
(`virtual_join_executor.attach` on the already-fetched row list), so the database never
saw the joined value and `get_column_filter_condition` had nothing to filter on. Fixing
the client alone would have produced the worst version of this: rows that LOOK filtered
while `Matches:` stays unfiltered. Every test here therefore asserts the returned rows
AND `total` together ― a filter that narrows one but not the other is the actual bug.

[Sorting is out of scope] ― user ruling 2026-07-31 ("정렬은 안해도되고 검색만되게해").
The resolved expression is only ever placed in WHERE, never in SELECT or ORDER BY.

[Why this is allowed to be one LEFT JOIN and not a per-row subquery]
`virtual_join_config` refuses to verify a declaration whose right side lacks a UNIQUE
index covering the join key. That is what makes output rows == input rows, which is what
keeps `query.count()` honest and pagination undisturbed. `test_the_join_cannot_change_
the_row_count` is that guarantee, asserted rather than assumed.

[격리] 테이블명 접두 `vjs_test_` ― 사용자 gitignored config에 실존할 수 없다.
[승인 대역] 이 스위트는 sqlite로 돈다. `unique_index_covering`은 postgresql이 아니면
항상 None이므로(모르면 거부) 대역 없이는 조인이 0건이고 모든 테스트가 헛통과한다 ―
`test_virtual_join_executor.py`가 기록한 것과 같은 이유, 같은 대역이다.
"""
import json

import pytest

import virtual_join_config as vjc
import virtual_join_executor as vjx
from database import crud, models, schemas

SEARCH_TABLES = {
    "vjs_test_log": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string", "core_lot": "string", "core_slot": "string",
            # collide ― exists on the left AND is exposed by the join
            "wafer_id": "string",
        },
    },
    "vjs_test_wafer": {
        "business_key": "wafer_key",
        "column_types": {
            "wafer_key": "string", "core_lot": "string", "core_slot": "string",
            "wafer_id": "string",
            # virtual_only ― exists ONLY on the right
            "fab_site": "string",
        },
    },
}

DECL = {
    "vjs_rule": {
        "left_table": "vjs_test_log", "right_table": "vjs_test_wafer",
        "join_key": [{"left": "core_lot", "right": "core_lot"},
                     {"left": "core_slot", "right": "core_slot"}],
        "expose": ["wafer_id", "fab_site"],
    }
}


@pytest.fixture()
def search_env(db_session, client, tmp_path, monkeypatch):
    models.init_dynamic_models(SEARCH_TABLES)
    crud.TABLE_CONFIG.update(SEARCH_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    p = tmp_path / "virtual_join_rules.json"
    p.write_text(json.dumps(DECL), encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    # `pg_index` approval stand-in ― see the module docstring.
    monkeypatch.setattr(vjc, "unique_index_covering",
                        lambda db, table, columns: "uq_fake"
                        if table == "vjs_test_wafer" else None)
    vjx.reset_cache()

    # The route's count cache is module-level with a 5s TTL and is keyed by
    # (table, q, cols, filters) - NOT by content. Tests run in well under 5s with
    # identical query strings over different data, so a stale total would leak between
    # them and an assertion about `total` would be reading the previous test's answer.
    import main
    main.TABLE_COUNT_CACHE.clear()

    _seed(db_session, "vjs_test_wafer", [
        {"wafer_key": "K1", "core_lot": "LOT-A", "core_slot": "01",
         "wafer_id": "WF-1", "fab_site": "M1"},
        {"wafer_key": "K2", "core_lot": "LOT-A", "core_slot": "02",
         "wafer_id": "WF-2", "fab_site": "M2"},
        # right row EXISTS but carries nothing - case (2) of 미상
        {"wafer_key": "K3", "core_lot": "LOT-A", "core_slot": "03"},
    ])
    _seed(db_session, "vjs_test_log", [
        {"log_id": "L1", "core_lot": "LOT-A", "core_slot": "01"},   # -> WF-1 / M1
        {"log_id": "L2", "core_lot": "LOT-A", "core_slot": "02"},   # -> WF-2 / M2
        {"log_id": "L3", "core_lot": "LOT-A", "core_slot": "03"},   # -> 미상 / 미상 (2)
        {"log_id": "L4", "core_lot": "LOT-Z", "core_slot": "99"},   # -> 미상 / 미상 (1)
        # left carries its own wafer_id - absent-only means the join must not win here,
        # and its fab_site is still 미상 because there is no right row at all.
        {"log_id": "L5", "core_lot": "LOT-Z", "core_slot": "98", "wafer_id": "WF-LEFT"},
    ])
    db_session.commit()
    yield client
    vjx.reset_cache()
    main.TABLE_COUNT_CACHE.clear()


def _seed(db, table, rows):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name="pipeline_parser",
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=f"seed_{table}", silent=True))


def _get(client, **params):
    """Returns (set of log_ids, total). Both, always ― that pairing IS the contract."""
    r = client.get("/tables/vjs_test_log/data", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {d["data"]["log_id"]["value"] for d in body["data"]}
    return ids, body["total"]


def _filters(col, ftype, val=None):
    spec = {"type": ftype}
    if val is not None:
        spec["filter"] = val
    return json.dumps({col: spec})


# ---------------------------------------------------------------------------
# Capability (1) ― "find the unresolved rows"
# ---------------------------------------------------------------------------

def test_unresolved_rows_are_found_on_a_virtual_only_column(search_env):
    """🔴 The highest-value filter: which rows did the join fail to resolve?

    Covers BOTH faces of 미상 in one assertion ― L3 (right row exists, value empty) and
    L4/L5 (no right row). A predicate written as `right.fab_site IS NULL` would return
    L4/L5 only and silently lose L3, which is the 26.27% the executor's docstring
    measured.
    """
    ids, total = _get(search_env, filters=_filters("fab_site", "equals", "미상"))
    assert ids == {"L3", "L4", "L5"}
    assert total == 3, "the count must be filtered too, or `Matches:` lies"


def test_the_resolved_rows_are_the_complement(search_env):
    """notEqual on the label is the other half ― the two must tile the table."""
    ids, total = _get(search_env, filters=_filters("fab_site", "notEqual", "미상"))
    assert ids == {"L1", "L2"}
    assert total == 2


def test_unresolved_on_a_collide_column_respects_absent_only(search_env):
    """On a collide column, "unresolved" means NEITHER side had a value.

    L5 has no right row but carries its OWN `wafer_id`, so it is resolved and must NOT
    appear. A predicate built only from the right side would wrongly include it ― this is
    where the COALESCE's left-first ordering is observable from the outside.
    """
    ids, total = _get(search_env, filters=_filters("wafer_id", "equals", "미상"))
    assert ids == {"L3", "L4"}, "L5 resolves from its own left value (absent-only)"
    assert total == 2


# ---------------------------------------------------------------------------
# Capability (2) ― general search on the virtual column
# ---------------------------------------------------------------------------

def test_search_on_a_virtual_only_column_narrows_rows_and_count_together(search_env):
    ids, total = _get(search_env, q="M1", cols="fab_site")
    assert ids == {"L1"}
    assert total == 1


def test_search_on_a_collide_column_sees_the_JOINED_value(search_env):
    """🔴 Searching `wafer_id` must find rows whose value came from the RIGHT table.

    Before this round the stored left column was searched, so `?q=WF-2` on a row whose
    `wafer_id` is displayed only because the join supplied it returned nothing ― the grid
    showed the value and the search denied it existed.

    Defect-injection check (actually run): route the collide column back to
    `cast(getattr(table_model, col), String)` and this returns an empty set.
    """
    ids, total = _get(search_env, q="WF-2", cols="wafer_id")
    assert ids == {"L2"}
    assert total == 1
    # ...and the left-owned value is still found (the join did not displace it).
    ids, total = _get(search_env, q="WF-LEFT", cols="wafer_id")
    assert ids == {"L5"}
    assert total == 1


def test_contains_and_startswith_work_through_the_same_translator(search_env):
    """The override reuses `get_column_filter_condition` wholesale, not a thinner copy."""
    ids, _ = _get(search_env, filters=_filters("fab_site", "contains", "M"))
    assert ids == {"L1", "L2"}
    ids, _ = _get(search_env, filters=_filters("fab_site", "startsWith", "M2"))
    assert ids == {"L2"}
    ids, _ = _get(search_env, filters=_filters("wafer_id", "endsWith", "LEFT"))
    assert ids == {"L5"}


def test_an_unscoped_search_reaches_a_virtual_only_column(search_env):
    """`?q=` with no `?cols=` must cover virtual columns too.

    `virtual_only` columns are not in `table_config.column_types` (they are not stored),
    so the default column list skipped them ― the grid displayed a column that the
    all-columns search could not see.
    """
    ids, total = _get(search_env, q="M2")
    assert ids == {"L2"}
    assert total == 1


def test_the_unresolved_label_is_searchable_as_plain_text(search_env):
    """Typing 미상 into the search box finds exactly the unresolved rows.

    Same population as capability (1) reached by the other door ― if these two ever
    disagree, one of them is not using the resolved expression.
    """
    ids, total = _get(search_env, q="미상", cols="fab_site")
    assert ids == {"L3", "L4", "L5"}
    assert total == 3


# ---------------------------------------------------------------------------
# The pre-existing defect: `?cols=` that builds no condition
# ---------------------------------------------------------------------------

def test_cols_naming_a_column_that_cannot_be_searched_is_refused(search_env):
    """🔴 **RED before this round** ― it returned the WHOLE TABLE with 200.

    The route only applied `or_(*conditions)` when at least one condition survived. A
    scope consisting entirely of unsearchable columns produced none, the filter was
    skipped, and the response carried every row while implying that column had been
    searched. Answering "everything" to "search only here" is the same class of defect as
    the server staying silent about a phantom column.

    Defect-injection check (actually run): delete the `unsearchable and not conditions`
    branch and this returns 200 with all 5 rows.
    """
    r = search_env.get("/tables/vjs_test_log/data",
                       params={"q": "anything", "cols": "no_such_column"})
    assert r.status_code == 400, (
        f"expected a refusal, got {r.status_code} with "
        f"{len(r.json().get('data', []))} rows")
    assert "no_such_column" in r.json()["detail"]


def test_a_partly_unsearchable_scope_still_searches_the_rest(search_env):
    """Refusal is only for a scope with NOTHING searchable in it.

    If one named column is real, the search runs on it and the unknown one is logged and
    dropped ― refusing the whole request would turn a stale client column list into an
    outage, and the honest-response property is already satisfied.
    """
    ids, total = _get(search_env, q="M1", cols="fab_site,no_such_column")
    assert ids == {"L1"}
    assert total == 1


# ---------------------------------------------------------------------------
# The property the whole design rests on
# ---------------------------------------------------------------------------

def test_the_join_cannot_change_the_row_count(search_env, db_session):
    """Left multiplicity is NORMAL (many log rows per wafer) and must not fan out.

    The WHERE-side LEFT JOIN is only safe because the right side is unique on the join
    key ― that is what `virtual_join_config` verifies before a declaration may run. If
    that ever stopped holding, `total` would inflate and every page would repeat rows.
    """
    _seed(db_session, "vjs_test_log",
          [{"log_id": f"M{i}", "core_lot": "LOT-A", "core_slot": "01"} for i in range(20)])
    db_session.commit()
    import main
    main.TABLE_COUNT_CACHE.clear()

    unfiltered, base_total = _get(search_env)
    assert base_total == 25, "5 seeded + 20 sharing one join key"
    # The same query, now forced through the join by naming a virtual column.
    ids, joined_total = _get(search_env, q="M1", cols="fab_site")
    assert joined_total == 21, "L1 plus the 20 rows sharing its key"
    assert len(ids) == 21


def test_no_sorting_was_added(search_env):
    """Sorting stayed out of scope ― the resolved expression never reaches ORDER BY.

    Asking to order by a virtual column falls back to the default ordering rather than
    erroring or half-working. Pinned so a later round adding sorting has to do it
    deliberately.
    """
    ids, total = _get(search_env, order_by="fab_site")
    assert total == 5 and len(ids) == 5
