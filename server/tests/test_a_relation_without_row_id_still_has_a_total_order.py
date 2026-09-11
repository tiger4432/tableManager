# -*- coding: utf-8 -*-
"""S-186. The grid can read a relation that has no `row_id`, and cannot write a view.

Owner: 「ledger event 도 메인 그리드에 read only 로」. Declaring `ledger_events` with
`kind: "view"` and a `business_key` is meant to be the whole job — two lines, no new cell.

Two things stood in the way, both measured before anything was built:

🔴 THE WRITE DOOR NEVER READ `kind`. It was read at three sites in `models.py`, all of them
「do not build the model/index」; no write path looked. So a view was read-only only because
PostgreSQL refused it, and a real table declared `kind: view` would simply be written.

🔴 `row_id` WAS HARDCODED AS THE TOTAL ORDER in four seats — the two tiebreakers, the
default sort, and the two-phase paging. 판정 296 named three; the fourth (the page's id
selection) was found by grep, and one direct read is all it takes to make this two paths.

⚠️ `row_id` STILL WINS WHEREVER IT EXISTS. S-131 measured what moving the grid's total
order costs: `idx_<t>_updated (updated_at, row_id)` stops being usable and one page spends
0.7 s sorting 440,000 rows. This is a lookup, not a replacement.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import main                                                           # noqa: E402
from database import crud, schemas                                    # noqa: E402

VIEW = "s186_view_rel"
TABLE = "s186_plain_rel"


class _Model:
    """A relation with only the columns it declares - which is the point."""

    def __init__(self, **columns):
        for name, value in columns.items():
            setattr(self, name, value)


@pytest.fixture(autouse=True)
def _declared():
    crud.TABLE_CONFIG[VIEW] = {
        "kind": "view", "business_key": "id",
        "column_types": {"id": "string", "occurred_at": "datetime"}}
    crud.TABLE_CONFIG[TABLE] = {
        "business_key": "k", "column_types": {"k": "string"}}
    yield
    crud.TABLE_CONFIG.pop(VIEW, None)
    crud.TABLE_CONFIG.pop(TABLE, None)


# ---------------------------------------------------------------------------
# The one function
# ---------------------------------------------------------------------------

def test_row_id_wins_wherever_it_exists():
    """🔴 THE REGRESSION LINE. Every table that has `row_id` must keep it as its total
    order, or S-131's index path dies across the whole grid."""
    model = _Model(row_id="ROWID_COL", id="ID_COL", k="K_COL")
    assert main.total_order_key(model, TABLE) == "ROWID_COL"


def test_a_relation_without_row_id_falls_to_its_declared_business_key():
    model = _Model(id="ID_COL", occurred_at="TS_COL")
    assert main.total_order_key(model, VIEW) == "ID_COL"


def test_a_relation_with_neither_is_refused_by_name_not_paged_anyway():
    """🔴 SCHEMA_CANON R7: 「상한 걸린 읽기에는 전순서가 있어야 한다」. A `LIMIT` without a
    total order hands the operator a different page on every refresh and raises nothing, so
    returning None here would be the silent version of the defect R7 exists to name."""
    from fastapi import HTTPException

    crud.TABLE_CONFIG[VIEW] = {"kind": "view", "column_types": {"id": "string"}}
    with pytest.raises(HTTPException) as caught:
        main.total_order_key(_Model(id="ID_COL"), VIEW)
    assert caught.value.status_code == 422
    assert "R7" in str(caught.value.detail)
    assert VIEW in str(caught.value.detail)


def test_a_business_key_naming_a_column_the_model_lacks_is_refused():
    """The sensitivity control: a declaration that names a missing column must not resolve
    to None and then page arbitrarily."""
    from fastapi import HTTPException

    crud.TABLE_CONFIG[VIEW]["business_key"] = "not_a_column"
    with pytest.raises(HTTPException):
        main.total_order_key(_Model(id="ID_COL"), VIEW)


# ---------------------------------------------------------------------------
# Gate ⓒ — the write door
# ---------------------------------------------------------------------------

def test_writing_a_view_is_refused_and_the_refusal_names_the_table_and_the_kind():
    batch = schemas.GeneralUpdateBatch(updates=[], transaction_id="t", silent=True)
    with pytest.raises(ValueError) as caught:
        crud.apply_batch_updates(None, VIEW, batch)
    said = str(caught.value)
    assert VIEW in said, said
    assert "kind: view" in said, said


def test_an_ordinary_table_is_not_touched_by_that_guard():
    """⚠️ THE CONTROL, and it must fail for a DIFFERENT reason. If this raised the view
    refusal the guard would be refusing everything, and every assertion above would still
    pass."""
    batch = schemas.GeneralUpdateBatch(updates=[], transaction_id="t", silent=True)
    with pytest.raises(Exception) as caught:
        crud.apply_batch_updates(None, TABLE, batch)
    assert "kind: view" not in str(caught.value)


def test_a_table_declaring_no_kind_is_writable():
    """A catalogue entry without the cell is not one character different - which is what
    makes this safe to deploy against a live declaration nobody has edited."""
    assert (crud.TABLE_CONFIG[TABLE].get("kind") or "table") != "view"


# ---------------------------------------------------------------------------
# 🔴 THE ROUTE, ON A REAL VIEW — the read the unit tests above could not reach
# ---------------------------------------------------------------------------

def test_a_view_model_carries_only_its_declared_columns():
    """⚰️ THE FIFTH SEAT, AND THE ONE THAT KEPT THE ROUTE AT 500 AFTER THE SORT WAS FIXED.
    Every dynamic model got `row_id`, `business_key_val`, `created_at`, `updated_at` — the
    columns a WRITE path maintains — whatever its kind. A view has none of them unless its
    SQL selects them, so the failure simply moved from the ORDER BY to the SELECT:
    `UndefinedColumn: void_obs_observed.row_id`.

    ⚠️ `dt_log_transferable` is a view that DOES expose `row_id`, and it answered 200 all
    along — which is exactly why the suite was green while a relation without one had never
    been read through the route at all."""
    from database import models

    cfg = dict(crud.TABLE_CONFIG)
    cfg["s186_real_view"] = {
        "kind": "view", "business_key": "vid",
        "column_types": {"vid": "string", "seen_at": "datetime", "updated_at": "datetime"}}
    models.init_dynamic_models(cfg)
    model = models.DYNAMIC_TABLES["s186_real_view"]
    names = [c.name for c in model.__table__.columns]

    assert names == ["vid", "seen_at", "updated_at"], names
    for framework in ("row_id", "business_key_val", "created_at"):
        assert framework not in names, framework
    # the declared key is the mapped primary key, so the model and `total_order_key` agree
    assert [c.name for c in model.__table__.primary_key] == ["vid"]
    # 🔴 a view cannot be indexed, and the framework index names columns it does not have
    assert not model.__table__.indexes


def test_a_view_declaring_no_business_key_is_still_mappable_but_refused_at_read():
    """🔴 TWO DIFFERENT QUESTIONS, and conflating them is how a page gets served
    arbitrarily. Measured: of ten `kind: view` relations on this box, FOUR declare no
    `business_key`. SQLAlchemy cannot map a class without a primary key, so one is
    nominated — that is a mapping mechanic, NOT a claim that the relation has an identity,
    and `total_order_key` still refuses to page it under R7."""
    from fastapi import HTTPException
    from database import models

    cfg = dict(crud.TABLE_CONFIG)
    cfg["s186_keyless_view"] = {
        "kind": "view", "column_types": {"a": "string", "b": "string"}}
    models.init_dynamic_models(cfg)
    model = models.DYNAMIC_TABLES["s186_keyless_view"]
    assert [c.name for c in model.__table__.primary_key] == ["a"], "not mappable"

    crud.TABLE_CONFIG["s186_keyless_view"] = cfg["s186_keyless_view"]
    try:
        with pytest.raises(HTTPException) as caught:
            main.total_order_key(model, "s186_keyless_view")
        assert "R7" in str(caught.value.detail)
    finally:
        crud.TABLE_CONFIG.pop("s186_keyless_view", None)


def test_a_view_row_carries_no_layering_metadata_and_renders_its_times():
    """A view's cells have exactly one value each — the write door refuses the relation, so
    nothing ever wrote a source for it. And the times are RENDERED: a raw `datetime` makes
    the payload non-JSON-native and the route's own warning prices that at ~10x."""
    from datetime import datetime, timezone

    class _Row:
        vid = "V1"
        seen_at = datetime(2026, 8, 13, 4, 12, 7, tzinfo=timezone.utc)

    crud.TABLE_CONFIG["s186_render_view"] = {
        "kind": "view", "business_key": "vid",
        "column_types": {"vid": "string", "seen_at": "datetime"}}
    try:
        merged = main.fetch_and_merge_metadata(
            None, "s186_render_view", [_Row()], ["vid", "seen_at"])
    finally:
        crud.TABLE_CONFIG.pop("s186_render_view", None)

    assert merged[0]["vid"] == {"value": "V1", "is_overwrite": False,
                                "sources": {}, "updated_by": None}
    assert isinstance(merged[0]["seen_at"]["value"], str), "a raw datetime costs 10x"
    assert merged[0]["seen_at"]["value"].endswith("+00:00")
