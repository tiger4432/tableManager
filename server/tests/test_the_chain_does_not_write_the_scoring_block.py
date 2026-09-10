# -*- coding: utf-8 -*-
"""진단 블록은 «사람이 부른 요청»의 것이다 (S-94, 판정 242).

🔴 WHAT IT COST. `map_alignment` writes a forty-line scoring block per view build - to the
console and always to `align.log` - and its own docstring says why: so a person can follow
one scoring run with a pencil. The automatic chain builds ONE VIEW PER JOB, a thousand per
group, so it wrote a thousand of those blocks that nobody reads. Measured in process on
2026-09-10, three paired runs: 5.499 s with, 3.643 s without - 1.86 ms a build and a third
of the whole mapper call.

⛔ AND THE FIX IS NOT A SECOND SWITCH. The logger, its console half and the manual route
are untouched. The question "is this a person's request or the chain's" already had an
answer - the group scope the chain's own loop opens - so the emit site asks that, and
nothing new has to be declared or remembered.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import alignment_batch_counts                                        # noqa: E402
import map_alignment                                                 # noqa: E402


class _Catch(logging.Handler):
    def __init__(self):
        super().__init__()
        self.blocks = []

    def emit(self, record):
        self.blocks.append(record.getMessage())


def _capture(monkeypatch):
    map_alignment._diag_logger()
    logger = logging.getLogger("map_alignment.diag")
    caught = _Catch()
    monkeypatch.setattr(logger, "handlers", [caught])
    return caught


def test_a_persons_request_still_writes_the_block(monkeypatch):
    """⚠️ THE HALF THAT MUST NOT CHANGE. The block is the operator's way to reconstruct
    one scoring decision; silencing it everywhere would have traded a performance defect
    for a diagnosis one."""
    caught = _capture(monkeypatch)

    map_alignment._emit_diag(["a person opened one unit"])

    assert [b for b in caught.blocks if "a person" in b], caught.blocks


def test_the_chain_writes_none_of_them(monkeypatch):
    """🔴 A THOUSAND PER GROUP, READ BY NOBODY. Inside the group scope the chain's own
    loop opens, the emit does not happen at all - not a shorter block, none."""
    caught = _capture(monkeypatch)

    with alignment_batch_counts.counting_group():
        for _ in range(5):
            map_alignment._emit_diag(["the chain scored a job"])

    assert caught.blocks == [], caught.blocks


def test_the_scope_closes_and_the_next_request_writes_again(monkeypatch):
    """⛔ THE BOUNDARY IS THE GROUP, NOT THE PROCESS. A worker that stopped writing them
    for good would be the same defect wearing the fix's clothes: the next person to open a
    unit on that box would get nothing."""
    caught = _capture(monkeypatch)

    with alignment_batch_counts.counting_group():
        map_alignment._emit_diag(["the chain scored a job"])
    map_alignment._emit_diag(["and then a person asked"])

    assert len(caught.blocks) == 1, caught.blocks
    assert "a person" in caught.blocks[0]
