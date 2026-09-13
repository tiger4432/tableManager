# -*- coding: utf-8 -*-
"""S-180 ⓓ. The sixth step has no file of its own, so it asks the walk what it already knows.

🔴 THE SAME SET THE WALK REFUSES BY. `ledger_trace_router._collectable_types()` builds the
list `/subgraph` hands back as `declared` when it raises `node_type_not_declared`. Counting
entities again here would let one declaration be collectable on one surface and refused on
the other — which is the defect that function's own docstring exists to prevent.

⚠️ THIS STEP HAS NO `rejected` OF ITS OWN. A walk refusal answers ONE REQUEST — nobody asked,
nothing is refused — so the only file-scope refusal here is 「the declaration would not read」.

⚠️ AND THE SEATING IS NOT COUNTED. `client2/src/map2/seating.js` is screen state; a server
that claimed to count it would be reporting something it cannot see.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import config_resolve_report as crr                                   # noqa: E402


def _walk():
    return crr.resolve_report([crr.DOMAIN_WALK])["domains"][0]


@pytest.fixture()
def collectable(monkeypatch):
    """Stands in for the walk's own set, so the cases are about THIS step."""
    from ledger import trace_router

    def build(names, boom=None):
        def fake():
            if boom is not None:
                raise boom
            return set(names)

        monkeypatch.setattr(trace_router, "_collectable_types", fake)
        return _walk()

    return build


# ---------------------------------------------------------------------------
# what it reports
# ---------------------------------------------------------------------------

def test_every_collectable_name_is_an_effective_node_type(collectable):
    walk = collectable({"die", "defect", "wafer"})

    assert [e["subject"] for e in walk["effective"]] == ["defect", "die", "wafer"]
    assert {e["scope"] for e in walk["effective"]} == {crr.SCOPE_NODE_TYPE}
    assert walk["counts"]["rejected"] == 0


def test_a_node_type_is_not_called_a_rule(collectable):
    """⛔ THE SCOPE WORD IS THE POINT (판정 316's precedent, applied). Reporting a node type
    as `rule` would make the line itself false — the same reason `table` was added for the
    chain step's ineffective rows."""
    walk = collectable({"die"})
    assert walk["effective"][0]["scope"] == "node_type"
    assert crr.SCOPE_NODE_TYPE in crr.SCOPES


def test_no_declared_entity_is_INEFFECTIVE_and_says_what_to_do(collectable):
    """⚠️ 「안 적음」, NOT 「틀림」. Nothing declared means the seats have no name to choose, and
    the answer is step ⑤ — so the entry points there rather than reading as a fault."""
    walk = collectable(set())

    assert walk["counts"] == {"effective": 0, "ineffective": 1, "rejected": 0}
    only = walk["ineffective"][0]
    assert only["reason"] == crr.REASON_NOT_DECLARED
    assert "⑤" in only["detail"], only["detail"]


def test_a_declaration_that_will_not_read_is_a_file_refusal_carrying_its_reason(collectable):
    """🔴 AND IT MUST NOT ESCAPE AS AN HTTP ERROR. `_collectable_types` raises
    `HTTPException(503)`; letting that through would take the WHOLE report down over one
    step, which is the failure `resolve_report` was built to prevent
    (「한 도메인의 실패가 나머지를 삼키지 않는다」)."""
    from fastapi import HTTPException

    walk = collectable(set(), boom=HTTPException(
        status_code=503, detail={"reason": "declaration_unreadable",
                                 "message": "선언을 읽지 못했습니다: boom"}))

    assert walk["counts"]["rejected"] == 1
    refusal = walk["rejected"][0]
    assert refusal["scope"] == crr.SCOPE_FILE
    assert refusal["reason"] == crr.REASON_MAPPING_UNAVAILABLE
    assert "boom" in refusal["detail"]


def test_one_step_failing_does_not_take_the_report_down(collectable):
    """⚠️ THE WHOLE REPORT IS THE UNIT AN OPERATOR READS. A step that threw would leave them
    with nothing, including the five steps that are fine."""
    from fastapi import HTTPException
    from ledger import trace_router

    def boom():
        raise HTTPException(status_code=503, detail={"message": "nope"})

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(trace_router, "_collectable_types", boom)
    try:
        report = crr.resolve_report()
        assert len(report["domains"]) >= 6
        assert any(d["domain"] == crr.DOMAIN_CATALOG for d in report["domains"])
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# 🔴 it counts nothing of its own
# ---------------------------------------------------------------------------

def _code_of(fn):
    """The function's CODE, docstring removed line by line.

    ⚠️ `source.replace(inspect.getdoc(fn), "")` DOES NOT WORK: `getdoc` dedents, so the
    dedented text never matches the indented source and the docstring stays in. Measured -
    the seating assertion below went red on the very sentence that forbids seating.
    """
    import inspect

    source = inspect.getsource(fn)
    doc = inspect.getdoc(fn)
    if doc:
        for line in doc.splitlines():
            source = source.replace(line, "")
    return source


def test_the_registrar_asks_the_walk_rather_than_reading_entities_itself():
    """🔴 SCORED ON THE SOURCE. Reading `entities` here would be a second author for 「what
    may I collect」, and the two would disagree the day one declaration changed."""
    body = _code_of(crr._resolve_walk)
    assert "_collectable_types" in body
    for rebuilt in ('"entities")', "config.load", "split(\"@\"", "ledger import config"):
        assert rebuilt not in body, (
            "the walk step counts entities for itself again: %s" % rebuilt)


def test_the_seating_file_is_not_counted():
    """⚠️ THE SERVER CANNOT SEE IT. `seating.js` is screen state, and a report that claimed a
    number for it would be asserting something it has no way to know."""
    assert "seating" not in _code_of(crr._resolve_walk)
