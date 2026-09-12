# -*- coding: utf-8 -*-
"""S-143. A draft preview states what activating it would make re-run — 「소급이 비싸다」.

🔴 THE OWNER'S CORE CONSTRAINT IS THE COST OF CHANGE. 「운영에서는 소급이 매우 비싸기 때문에
원장 선언도 매우 신중해야 하고 … 이것을 싸게 만드는 게 기술이고 운영의 핵심」. The counting
machinery all existed — six retroactive ops, each with its own dry-run — and nothing asked it
from a DECLARATION change, which is the moment an operator is deciding.

🔴 `count` IS THE COUNTER'S ANSWER VERBATIM (판정 323). Not picked, not renamed, extra keys
carried. `/admin/retroactive/{op}/count` already taught the screen these names, and a second
spelling here would make one number answer to two.

⚠️ AND A WORD IS NOT COUNTED ON PURPOSE. Editing a predicate re-runs every source that utters
it; counting that is one dry-run PER SOURCE on a request path. The sources are named and
`absence` says so, because 「cannot be counted」 sends an operator nowhere while 「not counted
here」 tells them the count is still on the retroactive route.
"""
import os
import sys
from types import SimpleNamespace

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import retroactive                                                    # noqa: E402
from ledger import config_drafts                                      # noqa: E402

#: What the counter would answer. 🔴 A SENTINEL OBJECT, so "verbatim" can be asserted by
#: IDENTITY - a test comparing field by field would pass on a copy that renamed nothing today
#: and something tomorrow.
COUNTER_ANSWER = {"op": "ledger_backfill", "affected": 1234,
                  "affected_label": "아직 번역되지 않은 행", "absence": None,
                  "scan_limit": None, "blocked_reason": None,
                  "a_key_this_test_never_heard_of": "rides along"}


def _node(kind, canonical_id):
    return SimpleNamespace(kind=kind, canonical_id=canonical_id)


def _setup(cfg):
    return SimpleNamespace(bundle=SimpleNamespace(to_mapping=lambda: cfg))


CFG = {"sources": {
    "s_utters": {"bind": {"mappings": {"m": {"predicate": "measures@1", "bind": {}}}}},
    "s_quiet": {"bind": {"mappings": {}}},
}}


# ---------------------------------------------------------------------------
# nobody asked
# ---------------------------------------------------------------------------

def test_without_a_session_there_is_no_cost_and_that_is_not_a_zero():
    """⛔ `None` MEANS THE QUESTION WAS NOT ASKED. A CLI or a test builds a preview with no
    request behind it; answering 「nothing re-runs」 there would be a statement nobody made."""
    assert config_drafts._redo_for(_setup(CFG), _node("source_plan", "s_utters"), None) is None


def test_the_existing_callers_still_get_a_preview_without_one(monkeypatch):
    """⚠️ THE SIZE OF THE CONTRACT CHANGE. Six DraftContext construction sites pass no db and
    must keep working; `redo` is simply absent for them."""
    context = config_drafts.DraftContext("setup", "index")
    assert context.db is None


# ---------------------------------------------------------------------------
# 🔴 one source: the counter's answer, verbatim
# ---------------------------------------------------------------------------

def test_a_source_node_carries_the_counters_answer_unchanged(monkeypatch):
    """🔴 ASSERTED BY IDENTITY. `redo["count"]` must BE what the counter returned - a test
    that compared chosen fields would stay green on the day somebody renamed one."""
    seen = {}

    def fake_count(db, op, params, **kw):
        seen.update(db=db, op=op, params=params)
        return COUNTER_ANSWER

    monkeypatch.setattr(retroactive, "count", fake_count)
    redo = config_drafts._redo_for(_setup(CFG), _node("source_plan", "dt_transfer"), "SESSION")

    assert redo["count"] is COUNTER_ANSWER
    assert redo["op"] == "ledger_backfill"
    assert redo["params"] == {"source": "dt_transfer"}
    assert redo["sources"] == ["dt_transfer"]
    assert seen == {"db": "SESSION", "op": "ledger_backfill",
                    "params": {"source": "dt_transfer"}}


def test_the_op_is_the_whole_source_one_and_not_the_scoped_one(monkeypatch):
    """🔴 `ledger_rescope` NEEDS A SCOPE COLUMN AND VALUES, and a declaration edit has none -
    it changes what the source means for every row it reads. Measured before wiring (판정 320);
    the first ruling named the scoped counter and it could not have been called."""
    monkeypatch.setattr(retroactive, "count", lambda db, op, params, **kw: {"op": op})
    redo = config_drafts._redo_for(_setup(CFG), _node("source_plan", "x"), "SESSION")
    assert redo["op"] == "ledger_backfill"
    assert "scope_column" not in redo["params"]


# ---------------------------------------------------------------------------
# 🔴 a word: named, not counted
# ---------------------------------------------------------------------------

def test_a_predicate_names_its_sources_and_says_it_did_not_count(monkeypatch):
    called = []
    monkeypatch.setattr(retroactive, "count",
                        lambda *a, **k: called.append(a) or {"never": "reached"})

    redo = config_drafts._redo_for(_setup(CFG), _node("predicate", "measures@1"), "SESSION")

    assert redo["sources"] == ["s_utters"]
    assert redo["op"] is None and redo["params"] is None
    assert redo["count"] == {"absence": retroactive.ABSENCE_NOT_COUNTED_HERE}
    assert not called, (
        "counting a word means one dry-run PER SOURCE on a request path - the drift gate")


def test_an_unuttered_word_is_truly_none_and_not_not_counted_here(monkeypatch):
    """🔴 TWO DIFFERENT EMPTIES. Nothing re-runs, versus something does and this seat declined
    to count it. Rendering them the same would tell an operator a predicate is unused when it
    is merely uncounted."""
    monkeypatch.setattr(retroactive, "count", lambda *a, **k: pytest.fail("must not count"))

    redo = config_drafts._redo_for(_setup(CFG), _node("vocabulary", "nobody_says_this"),
                                   "SESSION")
    assert redo["sources"] == []
    assert redo["count"] == {"absence": retroactive.ABSENCE_TRULY_NONE}


def test_the_absence_word_lives_in_the_counters_vocabulary():
    """⚠️ ONE PLACE FOR THE CLIENT TO LEARN IT. A word invented beside the report would be a
    second vocabulary for the same idea."""
    assert retroactive.ABSENCE_NOT_COUNTED_HERE in retroactive.ABSENCE_WORDS
    assert retroactive.ABSENCE_TRULY_NONE in retroactive.ABSENCE_WORDS


def test_there_is_no_second_absence_outside_the_count():
    """⛔ `absence` SITS IN ONE PLACE (판정 323). An outer copy would let the two disagree, and
    a reader would have no way to know which one to believe."""
    redo = config_drafts._redo_for(_setup(CFG), _node("entity", "nobody"), "SESSION")
    assert "absence" not in redo
    assert set(redo) == {"op", "params", "sources", "count"}


# ---------------------------------------------------------------------------
# the shape is one shape
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,name", [("source_plan", "s"), ("predicate", "measures@1"),
                                       ("vocabulary", "unused")])
def test_the_outer_keys_are_the_same_four_whatever_the_node_is(kind, name, monkeypatch):
    """🔴 A FIXED KEY SET IS WHY THIS IS NOT 「두 상태 한 응답」. That defect comes from mixing
    key-absent, value-null and value-zero; fixing the keys removes the mix, and the difference
    lives in `count` where a reader already knows to look."""
    monkeypatch.setattr(retroactive, "count", lambda *a, **k: COUNTER_ANSWER)
    redo = config_drafts._redo_for(_setup(CFG), _node(kind, name), "SESSION")
    assert set(redo) == {"op", "params", "sources", "count"}


# ---------------------------------------------------------------------------
# 🔴 the route, actually called
# ---------------------------------------------------------------------------

def test_the_view_route_takes_the_request_session_and_opens_no_second_one():
    """🔴 THE SEAT, SCORED WHERE IT LIVES. `redo` is only ever filled when a REQUEST asks, so
    the route has to hand its own Session down - and it must be the one FastAPI already holds
    (`Depends(get_db)`), never a connection opened here. A second connection on a preview
    path is the quiet cost 「성능 마진 넉넉하게」 forbids."""
    import inspect

    from ledger_api import ontology_config_explorer_router as router

    source = inspect.getsource(router.explorer_view)
    assert "Depends(get_db)" in source
    assert "db=db" in source, "the session must reach the service"
    for opened in ("create_engine", "open_readonly", "sessionmaker"):
        assert opened not in source, opened


def test_the_route_still_answers_after_gaining_the_dependency(client):
    """⚠️ CALLED FOR REAL, not asserted about. Adding `Depends(get_db)` to a handler is
    exactly the change that 422s every request when it goes wrong - a decorator binding to
    the wrong callable, a parameter read as a required query field - and none of that shows
    up in a source assertion.

    ⚠️ THE TOKEN HALF IS NOT ASSERTED HERE. `test_admin_auth.py` parametrises over EVERY
    gated `/admin/*` route, so a second copy would be a second answer to 「is this route
    gated」 - and the one that drifts is the copy. Measured while writing this: the route
    answers 200 unauthenticated in a test env with no token configured, which is that
    suite's contract and not this one's to restate.
    """
    answer = client.get("/admin/ontology-explorer/view")

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert "snapshot_hash" in body, "the handler ran rather than being refused by FastAPI"
