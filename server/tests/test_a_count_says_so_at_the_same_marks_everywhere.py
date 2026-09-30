# -*- coding: utf-8 -*-
"""총괄 5c39aa10c · 5deda97cf — 「언제 한 줄 찍나」는 한 물음이다. 알림 다섯 자리(key_gate · void_sat_format ·
gate.refuse · gate.record_unsaid · crud 의 드롭)가 각자 문턱을 적었고(넷은 10^6 에서 멈춤) 판정 모양도 셋이었다.
이제 utils.logger.announce_crossed 하나 — 1 · 10 · … · 10^18 을 넘을 때. 같은 입력을 다섯 문에 넣어 같은 답.
"""
import ast
import logging
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import key_gate                                               # noqa: E402
from database import crud                                                # noqa: E402
from ledger import gate                                                  # noqa: E402
from parsers import void_sat_format                                      # noqa: E402
from utils.logger import announce_crossed                                # noqa: E402

#: (before, total) -> a line. 10^7 and past are the marks four seats did not reach before.
EXPECTED = {(0, 1): True, (1, 2): False, (9, 10): True, (10, 11): False, (5, 50): True,
            (0, 5000): True, (999_999, 10 ** 6): True, (10 ** 6, 10 ** 6 + 1): False,
            (10 ** 6, 5 * 10 ** 6): False, (10 ** 7 - 1, 10 ** 7): True, (10 ** 7, 10 ** 8): True,
            (10 ** 18 - 1, 10 ** 18): True, (10 ** 18, 10 ** 18 + 1): False}
KEY = (("mat_type", "WF"),)


@pytest.fixture(name="fresh")
def fixture_fresh(monkeypatch):
    for module, names in ((key_gate, ("_refusals", "_refused_rows")),
                          (void_sat_format, ("_refusals", "_refused_rows")),
                          (gate, ("_refusals", "_atoms_lost", "_rows_refused", "_incomplete",
                                  "_unsaid")),
                          (crud, ("_undeclared_column_drops", "_undeclared_column_warned",
                                  "_undeclared_column_drops_over_budget"))):
        for name in names:
            monkeypatch.setattr(module, name, {})
    monkeypatch.setattr(gate, "_samples", [])


def _key_gate(b, t, caplog):
    key_gate._refusals[("t", "c")] = b
    return bool(key_gate._record("t", ["r"], {"c": t - b}, 1))


def _void_sat(b, t, caplog):
    void_sat_format._refusals[("t", "reason")] = b
    return bool(void_sat_format._record("t", {"reason": t - b}, 1))


def _gate_refuse(b, t, caplog):
    gate._refusals[("s", gate.REFUSE_UNDECLARED_VOCABULARY)] = b
    gate.refuse("s", gate.REFUSE_UNDECLARED_VOCABULARY, "x")
    return any("REFUSED a source event" in r.getMessage() for r in caplog.records)


def _gate_unsaid(b, t, caplog):
    gate._unsaid[("s", KEY)] = b
    gate.record_unsaid("s", {KEY: t - b})
    return any("said no sentence" in r.getMessage() for r in caplog.records)


def _crud_drop(b, t, caplog):
    crud._undeclared_column_drops[("t", "c")] = b
    if b:
        crud._undeclared_column_warned["t"] = {"c"}
    crud._warn_undeclared_column_once("t", "c")
    return any("was DROPPED" in r.getMessage() for r in caplog.records)


DOORS = {"key_gate": _key_gate, "void_sat_format": _void_sat, "gate.refuse": _gate_refuse,
         "gate.record_unsaid": _gate_unsaid, "crud_drop": _crud_drop}
ONE_AT_A_TIME = {"gate.refuse", "crud_drop"}
CASES = [(door, pair) for door in DOORS for pair in EXPECTED
         if door not in ONE_AT_A_TIME or pair[1] == pair[0] + 1]


@pytest.mark.parametrize("door, pair", CASES, ids=["%s-%d-%d" % (d, *p) for d, p in CASES])
def test_every_seat_says_so_at_the_same_marks(fresh, caplog, door, pair):
    before, total = pair
    with caplog.at_level(logging.WARNING):
        said = DOORS[door](before, total, caplog)
    assert said == EXPECTED[pair] == announce_crossed(before, total)


def test_no_seat_writes_its_own_marks():
    """A seat that grows its own constant back answers the same today and drifts tomorrow."""
    server = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=server, capture_output=True,
                           text=True, check=True).stdout.split()
    files = [f for f in files if not f.startswith("tests/")]
    assert "utils/logger.py" in files and len(files) > 100          # the listing itself works
    owners = []
    for rel in files:
        tree = ast.parse(open(os.path.join(server, rel), encoding="utf-8").read())
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, ast.AnnAssign) else [])
            owners += ["%s:%s" % (rel, t.id) for t in targets
                       if isinstance(t, ast.Name) and t.id.endswith("ANNOUNCE_AT")]
    assert owners == ["utils/logger.py:ANNOUNCE_AT"], owners
