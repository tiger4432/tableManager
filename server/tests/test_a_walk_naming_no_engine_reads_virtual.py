# -*- coding: utf-8 -*-
"""A walk that names no engine reads virtual (owner 11-08 «다 가상걷기로 해» · 11-09 «전면 가상전환», lead 11-10).

`trace_router.engine_for` is the one seat: the engine asked, else `DEFAULT_ENGINE`. Every caller passes through it -
the subgraph route (HTTP and a direct call's Query sentinel), the key list, the gap catalogue, a reach, the walk
function a screen helper calls. A walk that names none and asks to be continued is walked whole (no 422); one that
names virtual and asks it is refused as before.
"""
import pytest

from ledger import trace_router
from tests.test_a_paused_walk_is_kept_in_its_process import _route


class _Stop(Exception):
    pass


@pytest.fixture
def lookup(monkeypatch):
    """The engine each caller hands the walk's reader (`_walk_lookup`) - the walk stops there."""
    seen = []

    def stop(connection, engine, names, world, leave_out=None, **reading):
        seen.append(trace_router.engine_for(engine))
        raise _Stop()
    monkeypatch.setattr(trace_router, "_walk_lookup", stop)
    monkeypatch.setattr(trace_router, "_worlds", lambda world: ["w"])
    return seen


@pytest.mark.parametrize("asked, reads", [(None, "virtual"), ("virtual", "virtual"), ("stored", "stored"),
                                         ("nonsense", "virtual")])
def test_the_one_seat(asked, reads):
    assert trace_router.engine_for(asked) == reads


@pytest.mark.parametrize("params, engine, resumable, status", [
    ({}, "virtual", False, 200),                                         # none named
    ({"engine": "stored"}, "stored", False, 200),
    ({"engine": "virtual"}, "virtual", False, 200),
    ({"resumable": "true"}, "virtual", False, 200),                      # none named + continue: walked whole
    ({"resumable": "true", "engine": "stored"}, "stored", True, 200),
    ({"resumable": "true", "engine": "virtual"}, None, None, 422),       # named virtual + continue: refused
])
def test_the_subgraph_route(monkeypatch, params, engine, resumable, status):
    answer, asked = _route(monkeypatch, params=params)
    assert answer.status_code == status, answer.text
    if status == 200:
        assert (asked["engine"], asked["resumable"]) == (engine, resumable)
    else:
        assert answer.json()["detail"]["reason"] == "virtual_walk_not_continued"


def test_a_next_page_named_by_no_engine_is_refused_not_read_from_a_ledger_it_did_not_walk(monkeypatch):
    answer, _asked = _route(monkeypatch, method="POST", json={"resume": {"walk": "x.0123456789abcdef.2"}})
    assert answer.status_code == 422 and answer.json()["detail"]["reason"] == "virtual_walk_not_continued"


def test_a_report_s_direct_call_of_the_route_reads_virtual(monkeypatch):
    """A report's walk calls the route with its defaults filled in (`report_reads._walk`) - the default, not the
    ledger."""
    from chain import report_reads
    from ledger import explorer

    seen = {}
    monkeypatch.setattr(trace_router, "_evidence_graph", lambda *a, **k: seen.update(k) or {"nodes": []})
    report_reads._walk(_Db(), "cell", node_id=explorer.entity_id("wafer", {"w": "W"}))
    assert seen["engine"] == "virtual", seen


class _Db:
    def connection(self):
        return None


def test_the_walk_function_reads_virtual_when_none_is_named(lookup):
    with pytest.raises(_Stop):
        trace_router._evidence_graph(None, node_id="n", hops=1, direction="both", node_limit=10, edge_limit=10)
    assert lookup == ["virtual"]


@pytest.mark.parametrize("function", [trace_router._evidence_graph, trace_router.reach])
def test_a_function_taking_an_engine_names_none_by_default(function):
    import inspect

    assert inspect.signature(function).parameters["engine"].default is None


@pytest.mark.parametrize("engine, reads", [(None, "virtual"), ("stored", "stored")])
def test_the_engine_seat_reads_the_declaration_unless_stored_is_named(monkeypatch, engine, reads):
    compiled = []
    monkeypatch.setattr(trace_router, "_compiled", lambda connection, names: compiled.append(names) or ([], []))
    legs, said = trace_router._engine_reading(_Conn(), engine, ["w"])
    assert ("virtual" if compiled else "stored") == reads
    assert (said or {}).get("name") == ("virtual" if reads == "virtual" else None)


class _Conn:
    class connection:
        dbapi_connection = None
    engine = None
