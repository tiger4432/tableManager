# -*- coding: utf-8 -*-
"""S-224. 「이 관계가 쓰기를 받나」는 판단 하나이고, 자리마다 답하면 자리 하나가 500 을 낸다.

🔴 THE OWNER'S ADD-ROW BUTTON ANSWERED 500. `POST /tables/<a view>/rows?count=1` reached
`crud.create_empty_rows_batch`, which builds `table_model(row_id=…)` — and a view's model
carries only the columns the view declares, so Python raised
`TypeError: 'row_id' is an invalid keyword argument`. Not a refusal; a crash that happened
to stop the write.

🔴 THE REFUSAL EXISTED AND SAT IN ONE FUNCTION. S-186 put 「kind: view 는 읽기 전용」 inside
`apply_batch_updates` on the reasoning that every write converges there. It does not: row
creation, row deletion and the two source controls reach the relation without passing
through it, and on a view that DOES declare `row_id` the delete path would have removed
that row's cell layers before PostgreSQL refused the last statement. That is the standing
rule 「한 축은 한 칸·한 함수」 with the function present and the sites not going through it.

⚠️ AND THE STATUS IS PART OF THE ANSWER. 500 says the server broke; this relation is doing
what it was declared to do, and the client has to be able to show the reason — so one
exception handler turns the one refusal into 422 with the sentence in `detail`.
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

VIEW = "s224_view_rel"
TABLE = "s224_plain_rel"


@pytest.fixture(autouse=True)
def _declared():
    """A view that does NOT declare `row_id` — the owner's shape, and the one that crashed."""
    crud.TABLE_CONFIG[VIEW] = {
        "kind": "view", "business_key": "id",
        "column_types": {"id": "string", "occurred_at": "datetime"}}
    crud.TABLE_CONFIG[TABLE] = {
        "business_key": "k", "column_types": {"k": "string"}}
    yield
    crud.TABLE_CONFIG.pop(VIEW, None)
    crud.TABLE_CONFIG.pop(TABLE, None)


def _said(caught):
    return str(caught.value)


# ---------------------------------------------------------------------------
# 🔴 gate ⓐ — every write path goes through the one function
# ---------------------------------------------------------------------------

WRITE_PATHS = {
    "cells": lambda t: crud.apply_batch_updates(
        None, t, schemas.GeneralUpdateBatch(updates=[], transaction_id="t", silent=True)),
    "create_rows": lambda t: crud.create_empty_rows_batch(None, t, 1),
    # 🔴 [판정 431] THE AUTHOR IS NAMED because it no longer has a default to fall back on -
    #    the default spelled `"system"`, a false author rather than an absence. These
    #    fixtures care about the VIEW refusal, not about who asked.
    "delete_rows": lambda t: crud.delete_rows_batch(None, t, ["r1"], "s431_probe"),
    "delete_row": lambda t: crud.delete_row(None, t, "r1", "s431_probe"),
    "delete_cell_source": lambda t: crud.delete_cell_source(None, t, "r1", "id", "src"),
    "delete_cell_source_batch": lambda t: crud.delete_cell_source_batch(
        None, t, [{"row_id": "r1", "column_name": "id"}], "src"),
    "pin_source": lambda t: crud.set_cell_manual_priority(None, t, "r1", "id", "src"),
    "pin_source_batch": lambda t: crud.set_cell_manual_priority_batch(
        None, t, [{"row_id": "r1", "column_name": "id"}], "src"),
}


@pytest.mark.parametrize("site", sorted(WRITE_PATHS))
def test_a_write_path_refuses_a_view_by_name(site):
    """🔴 THE SAME SENTENCE FROM EVERY DOOR. Five of these had no gate at all before S-224,
    and two of them (the empty-payload shortcuts) would have returned success."""
    with pytest.raises(crud.ReadOnlyRelation) as caught:
        WRITE_PATHS[site](VIEW)

    assert VIEW in _said(caught), _said(caught)
    assert "kind: view" in _said(caught), _said(caught)


@pytest.mark.parametrize("site", sorted(WRITE_PATHS))
def test_an_ordinary_table_is_not_refused_by_that_gate(site):
    """⚠️ THE CONTROL. Without it the gate could be refusing EVERY relation and every
    assertion above would still pass.

    ⚠️ WHAT HAPPENS INSTEAD IS NOT PINNED. With `db=None` and no dynamic model these doors
    fail for their own reasons — two of them return `([], [])` rather than raising — and
    asserting a particular one would be asserting the fixture, not the gate.
    """
    try:
        WRITE_PATHS[site](TABLE)
    except crud.ReadOnlyRelation as exc:                     # pragma: no cover - the defect
        pytest.fail(f"{site} refused an ordinary table: {exc}")
    except Exception as exc:
        assert "kind: view" not in str(exc), str(exc)


def test_the_gate_answers_before_the_payload_is_looked_at():
    """🔴 「빈 요청이라 통과됐다」 AND 「쓸 수 있는 관계라 통과됐다」 MUST NOT BE ONE ANSWER.
    Three of these doors return early on an empty payload, so a gate placed after that
    shortcut would refuse a paste of 500 cells and accept a paste of none."""
    with pytest.raises(crud.ReadOnlyRelation):
        crud.delete_rows_batch(None, VIEW, [], "s431_probe")
    with pytest.raises(crud.ReadOnlyRelation):
        crud.delete_cell_source_batch(None, VIEW, [], "src")
    with pytest.raises(crud.ReadOnlyRelation):
        crud.set_cell_manual_priority_batch(None, VIEW, [], "src")


def test_a_relation_declaring_no_kind_is_writable():
    """A catalogue entry without the cell is not one character different from a view."""
    assert crud.refuse_write_to_view(TABLE) is None
    assert crud.refuse_write_to_view("s224_not_in_the_catalogue_at_all") is None


# ---------------------------------------------------------------------------
# 🔴 gate ⓑ — the route says 422 and carries the reason
# ---------------------------------------------------------------------------

ROUTES = {
    "create_rows": ("POST", f"/tables/{VIEW}/rows?count=1", None),
    "batch_delete": ("POST", f"/tables/{VIEW}/rows/batch_delete", {"row_ids": ["r1"]}),
    "delete_row": ("DELETE", f"/tables/{VIEW}/rows/r1", None),
    "paste": ("PUT", f"/tables/{VIEW}/data/updates",
              {"updates": [], "transaction_id": "t", "silent": True}),
    "delete_source": ("POST", f"/tables/{VIEW}/cells/sources/delete/batch",
                      {"cells": [], "source_name": "src"}),
    "pin_source": ("PUT", f"/tables/{VIEW}/cells/priority/batch",
                   {"updates": [], "source_name": "src"}),
}


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_the_route_refuses_with_422_and_the_reason(route):
    """🔴 422 AND `detail`, FROM ONE HANDLER. The client draws `detail`; a 500 gives it a
    traceback and nothing to show the operator."""
    from fastapi.testclient import TestClient

    method, url, body = ROUTES[route]
    answer = TestClient(main.app).request(method, url, json=body)

    assert answer.status_code == 422, (route, answer.status_code, answer.text)
    detail = answer.json().get("detail")
    assert VIEW in str(detail), detail
    assert "kind: view" in str(detail), detail
