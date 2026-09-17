# -*- coding: utf-8 -*-
"""S-254. 그리드는 «자기가 든 신원»(`row_id`)으로 소급을 건다 — 화면에 없는 키가 아니라.

🔴 THE THIRD FINDING OF THE SAME INCIDENT. The owner pressed 「다시 돌리기」 on a dt_log row
and the run reported `rows_scanned 0` - no error, nothing replayed, nothing said. dt_log is
a `composite_key_source` table, so its stored `business_key_val` is an ASSEMBLED string
(`GEN-dt_cell_key-…`) that appears in NO column; the banner sent what it could see
(`DT_JOB_ID PROBE-…`) as a business key. The two worlds never met.

⛔ AND A ZERO WITH NO ERROR IS THE WORST ANSWER OF THE FIVE. 「없어서 0」과 「못 찾아서 0」
look identical from a screen, and the operator's next move after either is to press it
again.

⚠️ `row_id` IS THE ONE IDENTITY A GRID HOLDS FOR EVERY TABLE - plain-keyed or composite. It
arrives BESIDE `business_keys`, which stays for the plain-keyed operator and the CLI.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import replay                                            # noqa: E402


class _Column:
    """Records what a selection was built from, so the test can ask WHICH identity."""

    def __init__(self, name):
        self.name = name
        self.asked = None

    def in_(self, values):
        self.asked = list(values)
        return ("IN", self.name, list(values))


class _Model:
    def __init__(self):
        self.row_id = _Column("row_id")
        self.business_key_val = _Column("business_key_val")


@pytest.fixture(name="selection")
def fixture_selection(monkeypatch):
    """Runs `replay_rule` far enough to build its selection, then stops it there.

    ⚠️ THE SUBJECT IS THE SELECTION, not the scan: what this round changed is WHICH
    identity the condition is built on, and paging real rows would put a database between
    the claim and the assertion."""
    model = _Model()
    seen = {}

    class _Stop(BaseException):
        pass

    def fake_iter_pages(db, m, **kwargs):
        seen["condition"] = kwargs.get("condition")
        raise _Stop()

    from chain import keyset_scan

    monkeypatch.setattr(keyset_scan, "iter_pages", fake_iter_pages)
    monkeypatch.setattr(keyset_scan, "current_max_row_id", lambda *a, **k: 1)
    def _run(**kwargs):
        seen.clear()
        rule = {"name": "r", "trigger_table": "dt_log", "target_table": "dt_inventory",
                "mapper_module": "m", "mapper_function": "f"}
        try:
            replay.replay_rule(_Db(model), rule, apply=False, log=lambda *_: None,
                               **kwargs)
        except _Stop:
            pass
        return seen.get("condition")

    return _run


class _Db:
    def __init__(self, model):
        self.model = model

    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def count(self):
        return 0

    def first(self):
        return None

    def all(self):
        return []


# ---------------------------------------------------------------------------
# 🔴 ⓐ — which identity the selection is built on
# ---------------------------------------------------------------------------

def _asked_column(condition) -> str:
    """Which column the scan will filter on - read off the real SQLAlchemy expression.

    ⚠️ THE REAL EXPRESSION, NOT A STAND-IN. My first cut faked the model so the condition
    came back as a tuple - which measures the fake. What this round changed is which COLUMN
    the scan filters on, and that is visible in the compiled clause."""
    return str(condition.compile(compile_kwargs={"literal_binds": False}))


def test_row_ids_select_on_row_id(selection):
    """🔴 THE ROUND. A grid holds row ids for every table, composite-keyed included."""
    said = _asked_column(selection(row_ids=["r1", "r2"]))

    assert ".row_id IN " in said, said
    assert "business_key_val" not in said, said


def test_business_keys_still_select_on_the_business_key(selection):
    """⚠️ THE OLD CALL IS UNCHANGED - the CLI and a plain-keyed table's operator both think
    in business keys, and this round adds a way to say 「these rows」 rather than replacing
    the way that already worked."""
    said = _asked_column(selection(business_keys=["A", "B"]))

    assert ".business_key_val IN " in said, said


def test_neither_replays_everything(selection):
    """⚠️ THE CONTROL: no selection at all still means 「the whole rule」, deliberately."""
    assert selection() is None


# ---------------------------------------------------------------------------
# ⛔ ⓑ — the refusals, because a silent zero is what started this
# ---------------------------------------------------------------------------

def test_sending_both_is_refused_rather_than_intersected(selection):
    """⛔ TWO ANSWERS TO 「WHICH ROWS」. AND-ing them would replay the intersection, which is
    neither of the things the caller asked for; preferring one would make the other cell a
    lie. Both are silent failures of exactly the kind this round exists to end."""
    with pytest.raises(replay.ReplayRefused) as caught:
        selection(row_ids=["r1"], business_keys=["A"])

    said = str(caught.value)
    assert "row_ids" in said and "business_keys" in said


def test_an_empty_row_id_list_is_refused_not_read_as_no_filter(selection):
    """⛔ THE SAME TRAP `business_keys` ALREADY GUARDS. An empty selection that fell through
    as 「no filter」 would replay the WHOLE rule - the opposite of what a caller asking for
    specific rows wants, and expensive in exactly the way a backfill is."""
    with pytest.raises(replay.ReplayRefused) as caught:
        selection(row_ids=[])

    assert "whole rule" in str(caught.value)


def test_blank_entries_do_not_smuggle_an_empty_selection_through(selection):
    """⚠️ `["", "  "]` IS AN EMPTY SELECTION WEARING A LENGTH. The strip-then-check is what
    makes the refusal above about the CONTENT rather than about `len()`."""
    with pytest.raises(replay.ReplayRefused):
        selection(row_ids=["", "   "])


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — the operator's door carries it through
# ---------------------------------------------------------------------------

def test_the_admin_operation_declares_and_forwards_the_new_selection():
    """⚠️ A CELL NOBODY FORWARDS IS A CELL THAT DOES NOTHING - the defect three of today's
    rounds were about. The count and the run both have to hand it on, or the screen would
    ask for rows and the backfill would replay the table."""
    import inspect

    from admin import retroactive

    declared = [p for p in retroactive.OPERATIONS["chain_replay"]["params"]
                if p.get("name") == "row_ids"]
    assert declared, retroactive.OPERATIONS["chain_replay"]["params"]

    for seat in (retroactive._count_chain_replay, retroactive._run_chain_replay):
        assert 'row_ids=params.get("row_ids")' in inspect.getsource(seat), seat.__name__
