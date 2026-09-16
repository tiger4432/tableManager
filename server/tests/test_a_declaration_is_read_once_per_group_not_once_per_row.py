# -*- coding: utf-8 -*-
"""S-276 · 판정 417. The join declaration is resolved ONCE per group, not once per row.

🔴 MEASURED BEFORE IT WAS BUILT. `_payload_filters` looped over the two rule names and
called `derivation.join_rule` INSIDE the per-payload loop, so a 1,000-row group asked the
join loader 2,000 times - and that loader re-reads the declaration file and runs a
uniqueness query per declaration. On this box, with its TWO live declarations, one call
is 3.4 ms median, so ≈6.9 s per 1,000-row group from this helper alone. The owner's
spec for a whole 1,000-row group is 5 s.

⛔ HOISTED, NOT CACHED, AND THAT DISTINCTION IS THE RULING. A declaration does not change
while one group runs, so its lifetime IS the loop's - which makes this a move. A cache
creates the question 「when is it stale」, and that question is part of what the
2026-09-14 outage was: `virtual_join/config`'s own note records every read that missed
the TTL re-running the loader and re-logging the same refusal, forever.

⚠️ THE SUBJECT IS THE TEMPLATE, FOR THE THIRD TIME TODAY. S-271 found it opening a
SAVEPOINT with no guard; ruling 416 found it handing the worker's session to the join
loader; this is it re-reading a declaration per row. Live mappers are gitignored, so the
only copy this repository can reach is the one future mappers are copied FROM.
"""
import importlib.util
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

TEMPLATE = os.path.join(SERVER_DIR, "mappers", "dt_map_mapper.py.sample")

SOURCE = "s276_source"
TRIGGER = "s276_attr"

#: What the loader hands back for the declaration this group is about.
DECLARED = {"name": "s276_join", "left_table": SOURCE, "right_table": TRIGGER,
            "join_key": [{"left": "lot", "right": "lot"},
                         {"left": "slot", "right": "slot"}]}


@pytest.fixture(name="template")
def fixture_template(monkeypatch):
    """The TEMPLATE itself, imported (⛔ never sliced - 소유자 상설 2026-09-02).

    ⚠️ `.py.sample` is not importable by name, so it is loaded from its path - the whole
    file, byte for byte, which is what keeps this a test of the shipped text.
    """
    import dt_map_derivation

    spec = importlib.util.spec_from_loader(
        "s276_template",
        importlib.machinery.SourceFileLoader("s276_template", TEMPLATE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    asked = []

    def join_rule(db, name):
        asked.append(name)
        return DECLARED if name == dt_map_derivation.CONFIRMED_JOIN_RULE else {
            "name": name, "left_table": "other", "right_table": "other", "join_key": []}

    monkeypatch.setattr(module.derivation, "join_rule", join_rule)
    module._s276_asked = asked
    return module


def _payloads(n):
    return [{"lot": "L%d" % i, "slot": str(i % 25)} for i in range(n)]


def test_the_declaration_is_asked_for_once_no_matter_how_many_rows(template, monkeypatch):
    """🔴 THE GATE, AS A COUNT. 2,000 -> 2 for a 1,000-row group: the two rule NAMES are
    still tried once between them, and neither is tried again per payload."""
    from database import models

    class Db:
        """Answers the two things `expand_trigger` asks of a session after the loop."""

        def query(self, _model):
            return self

        def filter(self, *_a, **_k):
            return self

        def all(self):
            return []

    model = type("Model", (), {"lot": object(), "slot": object()})
    monkeypatch.setitem(models.DYNAMIC_TABLES, SOURCE, model)
    monkeypatch.setattr(template, "_rule_source_table", lambda rule: SOURCE)
    monkeypatch.setattr(template.derivation, "frame_trigger_scope",
                        lambda db, table, filters: {"rows": 1})

    template.expand_trigger(Db(), _payloads(1000), {"trigger_table": TRIGGER})

    assert len(template._s276_asked) == 1, template._s276_asked
    assert len(template._s276_asked) <= 2, (
        "at most the two declared names, and never once per row")


def test_hoisting_did_not_change_the_answer(template):
    """⚠️ A MOVE THAT CHANGES THE ANSWER IS NOT A MOVE. The per-row half gets the resolved
    declaration and reads the payload; same declaration, same payload, same filters."""
    got = [template._payload_filters(DECLARED, p) for p in _payloads(3)]

    assert got == [{"lot": "L0", "slot": "0"},
                   {"lot": "L1", "slot": "1"},
                   {"lot": "L2", "slot": "2"}]


def test_an_incomplete_key_still_selects_nothing(template):
    """⛔ THE REGRESSION LINE THE ORIGINAL COMMENT NAMES: 「an incomplete key selects
    nothing, never everything」. A blank is missing, not a value (the standing rule)."""
    assert template._payload_filters(DECLARED, {"lot": "L1", "slot": "  "}) == {}
    assert template._payload_filters(DECLARED, {"lot": "L1"}) == {}
    assert template._payload_filters(None, {"lot": "L1", "slot": "1"}) == {}


def test_the_per_row_half_cannot_reach_the_database(template):
    """🔴 THE SHAPE, NOT ONLY THE COUNT. `_payload_filters` no longer takes a session, so
    a future edit to this TEMPLATE cannot put a query back in the per-row loop without
    first re-adding the parameter - which is a visible change rather than a quiet one."""
    import inspect

    assert list(inspect.signature(template._payload_filters).parameters) == ["vj", "payload"]
    assert "db" not in inspect.signature(template._payload_filters).parameters
