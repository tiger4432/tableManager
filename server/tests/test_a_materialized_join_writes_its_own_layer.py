# -*- coding: utf-8 -*-
"""S-189 ⓑ. The join's answer stops being computed on every read and becomes a cell.

🔴 THE WRITE REUSES `execute_rule`, WHICH REUSES `join_onclause`. Not a new SELECT — that
function's own note records what a second spelling of the ON clause cost: the grid showed one
row set and the filter counted another. A materialising query composing its own join would be
a third reader of the same declaration.

🔴 `source_name` IS THE RULE NAME, AND THAT IS THE WHOLE LAYERING STORY. A `user` overwrite
already outranks a named source, so a manual edit wins without anything here defending it —
and nothing here MAY defend it, because a second precedence rule is a second answer to
「who wins」.

⚠️ WHAT IS SCORED HERE, STATED PLAINLY: the ITEMS this module hands to
`crud.apply_batch_updates` — their cells, their `source_name`, and whether the call happens at
all. Landing those items in a database is `apply_batch_updates`'s own contract with its own
tests; re-proving it here would be a second gate able to disagree with the first.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import virtual_join.config as vjc                                     # noqa: E402
from virtual_join import executor as vje                                   # noqa: E402

KNOWN = {
    "left_t": {"column_types": {"k": "string", "frame": "string"}},
    "right_t": {"column_types": {"k": "string", "frame": "string"}},
}


def _rule(**cells):
    raw = {"left_table": "left_t", "right_table": "right_t",
           "join_key": [{"left": "k", "right": "k"}], "expose": ["frame"]}
    raw.update(cells)
    rule, message, code, _ = vjc._validate_join("join_frame", raw, KNOWN)
    assert rule is not None, (message, code)
    return rule


@pytest.fixture()
def captured(monkeypatch):
    """Catches the batch instead of writing it, and records that a write was attempted."""
    calls = []

    def fake_apply(db, table_name, batch, *a, **k):
        calls.append((table_name, list(batch.updates)))
        return None

    from database import crud

    monkeypatch.setattr(crud, "apply_batch_updates", fake_apply)
    return calls


def _joined(answers):
    """Stand in for the join: `{row_id: {"matched": bool, "values": {...}}}`."""
    def fake(db, rule, row_ids, *a, **k):
        return {rid: answers[rid] for rid in row_ids if rid in answers}
    return fake


# ---------------------------------------------------------------------------
# the layer
# ---------------------------------------------------------------------------

def test_every_written_cell_carries_the_rule_as_its_source(captured, monkeypatch):
    """🔴 THE GATE THE WHOLE PIECE EXISTS FOR. The value must arrive as the RULE's layer, or
    layering cannot tell it from a user's typing and a manual edit stops winning."""
    monkeypatch.setattr(vje, "execute_rule", _joined({
        "r1": {"matched": True, "values": {"frame": "F-1"}},
        "r2": {"matched": True, "values": {"frame": "F-2"}}}))
    out = vje.materialize_rows(None, _rule(materialize=True, max_rewrite_rows=10),
                               ["r1", "r2"])
    assert out == {"rule": "join_frame", "written": 2, "refusal": None}
    table, items = captured[0]
    assert table == "left_t"
    assert {i.row_id for i in items} == {"r1", "r2"}
    for item in items:
        assert item.source_name == "join_frame" and item.updated_by == "join_frame"
    assert [i.updates for i in items] == [{"frame": "F-1"}, {"frame": "F-2"}]


def test_an_unmatched_row_is_skipped_but_a_matched_null_is_written_as_null(captured,
                                                                          monkeypatch):
    """⚠️ 「없는 것」 AND 「0인 것」 MUST NOT LAND THE SAME - and that is exactly why these two
    cases now part company.

    ⚰️ THIS TEST ASSERTED THAT BOTH WERE SKIPPED UNTIL 2026-09-15, when the owner ruled
    「null 로 쓰면 null 이 되어야 한다」. A matched right-hand row holding NULL is a FACT - the
    record exists and its value is empty - and skipping it left that fact recorded nowhere.
    An UNMATCHED row is a different thing: there is no record, and writing null there would
    assert 「the value is null」, which is a claim nobody made. So `miss` is still skipped and
    `null` is now written, which is the distinction `matched` exists to carry."""
    monkeypatch.setattr(vje, "execute_rule", _joined({
        "hit": {"matched": True, "values": {"frame": "F"}},
        "miss": {"matched": False, "values": {}},
        "null": {"matched": True, "values": {"frame": None}}}))
    out = vje.materialize_rows(None, _rule(materialize=True, max_rewrite_rows=10),
                               ["hit", "miss", "null"])
    assert out["written"] == 2
    written = {i.row_id: i.updates for i in captured[0][1]}
    assert set(written) == {"hit", "null"}, "miss 가 써졌거나 null 이 빠졌다"
    assert written["hit"] == {"frame": "F"}
    assert written["null"] == {"frame": None}, "null 이 null 로 안 써졌다"


def test_nothing_is_written_when_nothing_matched(captured, monkeypatch):
    """⛔ AND THE WRITE IS NOT ATTEMPTED AT ALL — an empty batch is a round trip that says
    nothing, and on a paced job it is one per tick forever."""
    monkeypatch.setattr(vje, "execute_rule", _joined({}))
    out = vje.materialize_rows(None, _rule(materialize=True, max_rewrite_rows=10), ["a"])
    assert out["written"] == 0 and captured == []


def test_a_rule_that_does_not_materialize_writes_nothing(captured, monkeypatch):
    """⛔ THE SAFETY LINE for the two read-time rules this box runs today."""
    monkeypatch.setattr(vje, "execute_rule", _joined({
        "r1": {"matched": True, "values": {"frame": "F"}}}))
    out = vje.materialize_rows(None, _rule(), ["r1"])
    assert out["written"] == 0 and captured == []
    assert "does not declare materialize" in out["refusal"]


# ---------------------------------------------------------------------------
# 🔴 the two triggers, and the ceiling
# ---------------------------------------------------------------------------

def test_a_reference_change_counts_before_it_writes(captured, monkeypatch):
    monkeypatch.setattr(vjc, "rewrite_row_count", lambda conn, rule, keys: 4)
    monkeypatch.setattr(vje, "_left_row_ids_for_key", lambda db, rule, keys: ["r1"])
    monkeypatch.setattr(vje, "execute_rule", _joined({
        "r1": {"matched": True, "values": {"frame": "F"}}}))

    class _Db:
        def connection(self):
            return None

    out = vje.on_reference_rows_changed(_Db(), _rule(materialize=True, max_rewrite_rows=10),
                                        ["key"])
    assert out["counted"] == 4 and out["written"] == 1 and out["refusal"] is None


def test_over_the_ceiling_writes_zero_rows(captured, monkeypatch):
    """⛔ NOT THE FIRST N. A table left part new and part old says nothing about which row is
    which, and the screen then shows a quietly wrong answer."""
    monkeypatch.setattr(vjc, "rewrite_row_count", lambda conn, rule, keys: 70800)

    class _Db:
        def connection(self):
            return None

    out = vje.on_reference_rows_changed(_Db(), _rule(materialize=True, max_rewrite_rows=1000),
                                        ["key"])
    assert out["written"] == 0 and captured == [], "the ceiling must stop the WRITE"
    assert "70800" in out["refusal"] and "1000" in out["refusal"]


def test_a_target_change_has_no_ceiling(captured, monkeypatch):
    """⚠️ The ceiling is about FAN-OUT: one reference row reaching many target rows. A target
    row costs itself, and applying a ceiling there would refuse an ordinary edit."""
    monkeypatch.setattr(vje, "execute_rule", _joined({
        "r1": {"matched": True, "values": {"frame": "F"}}}))
    out = vje.on_target_rows_changed(None, _rule(materialize=True, max_rewrite_rows=1),
                                     ["r1"])
    assert out["written"] == 1 and out["refusal"] is None


# ---------------------------------------------------------------------------
# retraction
# ---------------------------------------------------------------------------

def test_retraction_withdraws_the_layer_by_the_rule_name(monkeypatch):
    """🔴 THE MECHANISM ALREADY EXISTED. `withdraw_source` retracts a named source's layer
    and the join layer is named for the rule — so a reference row disappearing costs the layer
    and NOTHING is written in its place. Inventing a `0` or a blank where a value used to be is
    how a screen stops telling absence from measurement.

    🚩 IT LIVES IN `cell_layer` SINCE S-211 ① (판정 358). It was in `chain_replay`, imported
    here inside `retract_rows`, and that one line was the last seam of a four-module ring.
    Patching the OLD home would leave this green while the executor called the real thing.

    ⛔ [S-280 · 판정 433 ③] AND THIS TEST WAS GREEN WHILE THE FUNCTION WROTE NOTHING. It
    asserted the three arguments it named and let a `**k` swallow the two that decide
    whether anything happens: without `row_ids` the withdrawal takes the WHOLE table, and
    without `apply=True` it rolls back. Both are `withdraw_source` defaults, so both were
    invisible at the call site AND at this assertion - a gate scoring the proxy (「누구의
    층인가」) while the property (「그 행들에 «썼나»」) went unmeasured. It now scores every
    argument that decides the outcome.
    """
    from chain import cell_layer

    seen = {}

    def fake_withdraw(db, table_name, source_name, columns=None, row_ids=None, apply=False,
                      **k):
        seen.update(table=table_name, source=source_name, columns=columns,
                    row_ids=row_ids, apply=apply)
        return {"withdrawn": 3}

    monkeypatch.setattr(cell_layer, "withdraw_source", fake_withdraw)
    out = vje.retract_rows(None, _rule(materialize=True, max_rewrite_rows=10),
                           ["r1", "r2"], True)
    assert seen == {"table": "left_t", "source": "join_frame", "columns": ["frame"],
                    "row_ids": ["r1", "r2"], "apply": True}
    assert out == {"withdrawn": 3}


def test_retraction_cannot_be_called_without_saying_which_rows_or_whether_to_write():
    """🔴 [판정 433 ③] THE SHAPE, NOT ONLY THE VALUE — the same argument 판정 431 made about
    the deletion author. A default that means 「the whole table」 and one that means 「do not
    actually write」 cannot be seen at a call site, which is how a function called
    `retract_rows` sat for a round as a whole-table dry run with nobody able to read that
    off the code. Removing them makes the omission a TypeError at the boundary."""
    import inspect

    parameters = inspect.signature(vje.retract_rows).parameters
    for required in ("row_ids", "apply"):
        assert parameters[required].default is inspect.Parameter.empty, (
            "retract_rows still has a default for %r, so a caller can silently get "
            "「whole table」 or 「write nothing」: %r"
            % (required, parameters[required].default))


def test_the_join_is_not_respelled_for_the_write():
    """🔴 SCORED ON THE SOURCE, because the defect it guards against is a SECOND query that
    happens to agree today. `materialize_rows` must go through `execute_rule` — which is
    where `join_onclause` is already the single spelling of the ON clause."""
    import inspect

    body = inspect.getsource(vje.materialize_rows)
    assert "execute_rule(" in body
    assert "join_onclause" not in body, "composing the join here would be a second reader"
    assert "outerjoin" not in body and "SELECT" not in body
