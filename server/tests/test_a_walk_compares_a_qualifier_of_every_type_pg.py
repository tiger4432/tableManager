# -*- coding: utf-8 -*-
"""Lead 11-11: a bound value (`follow=<predicate>:<qualifier>`) and a value filter compare a qualifier by ONE seat
(`VirtualEvidenceLookup._qualifier_cell`) - a time by its instant, a bool as a bool - on the shape gate's table
(`support.walk_shape_gate`), with S4 holding S1's values and S5 others.

  bound     from S1 over O, bound on q: S4 is reached (the same value), S5 is not - every qualifier type; a time read by
            a format is refused by name, not drawn another way
  filter    a bool filter keeps exactly the steps the calculator holds true of; a time filter is refused «not yet»
            (lead 11-11: the calculator compares a time as its text - an instant is A's grammar landing)
"""
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer, trace_router, walk_filter                # noqa: E402
from support import walk_shape_gate as gate                         # noqa: E402
from test_ledger_worlds_are_independent_and_meet_in_a_walk import fixture_config, fixture_world  # noqa: E402,F401

pytestmark = pytest.mark.pg

#: S5's cell of each type - a value, not S1's
OTHER = {"text": "A2", "integer": 8, "bigint": 9000000001, "double": 8.5, "numeric": Decimal("2.5"), "boolean": False,
         "timestamptz": datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc), "timestamp_zone": datetime(2026, 10, 1, 10, 0),
         "date": date(2026, 10, 1), "text_format": "20261001_100000"}
KINDS = sorted(OTHER)


def _rows():
    s1, s2 = gate.rows()[:2]
    s4 = dict(s1, row_id="r4", sid="S4")
    s5 = dict(s1, row_id="r5", sid="S5", **{gate.column(kind): value for kind, value in OTHER.items()})
    return [s1, s2, s4, s5]


@pytest.fixture(name="board")
def fixture_board(world, config, monkeypatch):
    from conftest import PG_TEST_SCHEMA
    from database import crud
    import notation_norm

    tables = json.loads((config / "table_config.json").read_text(encoding="utf-8"))
    tables[gate.TABLE] = gate.catalogue()
    (config / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    monkeypatch.setitem(crud.TABLE_CONFIG, gate.TABLE, gate.catalogue())
    (config / "ontology" / "ledger_config.json").write_text(json.dumps(gate.document(), default=str),
                                                           encoding="utf-8")
    raw = world["engine"].raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())
            cursor.execute(f'DROP TABLE IF EXISTS "{PG_TEST_SCHEMA}"."{gate.TABLE}"')
            cursor.execute(gate.ddl(PG_TEST_SCHEMA))
            for row in _rows():
                names = sorted(row)
                cursor.execute(f'INSERT INTO "{PG_TEST_SCHEMA}"."{gate.TABLE}" '
                               f'({", ".join(chr(34) + n + chr(34) for n in names)}) '
                               f"VALUES ({', '.join(['%s'] * len(names))})", [row[n] for n in names])
        raw.commit()
    finally:
        raw.close()
    trace_router._COMPILED.clear()
    yield world
    with world["engine"].begin() as conn:
        conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{PG_TEST_SCHEMA}"."{gate.TABLE}"')


def _predicate(kind):
    return "p_" + gate.name("qualifier_optional", kind)


def _walk(board, seeds, hops, **asked):
    with board["engine"].connect() as conn:
        return trace_router._evidence_graph(
            conn, node_id={"positive": [explorer.entity_id("subj", {"sid": row}) for row in seeds], "negative": []},
            hops=hops, direction="both", node_limit=200, edge_limit=200, engine="virtual", **asked)


def _subjects(payload):
    return sorted(node["keys"]["sid"] for node in payload["nodes"] if node["type"].split("@")[0] == "subj")


@pytest.mark.parametrize("kind", [kind for kind in KINDS if kind != "text_format"])
def test_a_bound_qualifier_reaches_the_same_value_and_not_another(board, kind):
    unbound = _walk(board, ["S1"], 2, follow=[_predicate(kind)])
    assert _subjects(unbound) == ["S1"], "unbound, the walk does not come back the way it went (`_skip`)"
    bound = _walk(board, ["S1"], 2, follow=[_predicate(kind)], follow_keys={_predicate(kind): ["q"]})
    assert _subjects(bound) == ["S1", "S4"], (kind, _subjects(bound))


def test_a_bound_time_read_by_a_format_is_refused_by_name(board):
    kind = "text_format"
    with pytest.raises(ValueError) as refused:
        _walk(board, ["S1"], 2, follow=[_predicate(kind)], follow_keys={_predicate(kind): ["q"]})
    assert isinstance(refused.value, walk_filter.NotRead) and "a time read by a format" in str(refused.value)


@pytest.mark.parametrize("text", ["[q] = true", "[q] = false", "not ([q] = true)", "[q] is null", '[q] = "true"',
                                  "[q] > false"])
def test_a_bool_filter_keeps_the_steps_the_calculator_holds_true_of(board, text):
    predicate = _predicate("boolean")
    with board["engine"].connect() as conn:
        filters = trace_router._walk_filters([f"{predicate}:{text}"], [], None, conn)
    whole = _walk(board, ["S1", "S2", "S4", "S5"], 1, follow=[predicate])
    kept = _walk(board, ["S1", "S2", "S4", "S5"], 1, follow=[predicate], filters=filters)
    compiled = walk_filter.compiled("edge_filter", predicate, text, ["q"])
    steps = {edge["source"]: edge.get("qualifiers") or {} for edge in whole["edges"] if edge["predicate"] == predicate}
    assert len(steps) == 4, steps
    want = sorted(source for source, qualifiers in steps.items() if walk_filter.holds([compiled], qualifiers))
    assert sorted(edge["source"] for edge in kept["edges"] if edge["predicate"] == predicate) == want, text


def test_the_bool_filters_keep_some_and_leave_some():
    held = [{"q": True}, {}, {"q": True}, {"q": False}]
    for text, want in (("[q] = true", [True, False, True, False]), ("[q] = false", [False, False, False, True]),
                       ("not ([q] = true)", [False, False, False, True]), ('[q] = "true"', [False] * 4)):
        compiled = walk_filter.compiled("edge_filter", "p", text, ["q"])
        assert [walk_filter.holds([compiled], q) for q in held] == want, text


@pytest.mark.parametrize("kind", ["timestamptz", "timestamp_zone", "date", "text_format"])
def test_a_time_filter_is_refused_not_yet(board, kind):
    with board["engine"].connect() as conn, pytest.raises(HTTPException) as refused:
        trace_router._walk_filters([f'{_predicate(kind)}:[q] >= "2026-09-30"'], [], None, conn)
    assert refused.value.status_code == 422 and refused.value.detail["reason"] == "filter_not_read"
    assert "is a time" in refused.value.detail["message"], refused.value.detail
