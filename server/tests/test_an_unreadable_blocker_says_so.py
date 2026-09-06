# -*- coding: utf-8 -*-
"""「못 읽었다」가 「막는 것이 없다」와 «같은 null» 로 나가던 자리.

🔴 THE SITE SAID THE RIGHT THING AND THEN DID THE OTHER ONE. The comment above the block
already spells the distinction — 「소급 실행이 «없으면» 이 칸은 null 이고, 그건 「이유를
모른다」이지 「막힌 것이 없다」가 아니다」 — and then the `except` writes that same null when
the READ fails, so three facts arrive as two values:

    read ok, nothing in flight   -> blocked_by = null
    read ok, something in flight -> blocked_by = {...}
    read FAILED                  -> blocked_by = null      ← indistinguishable from the first

⚠️ AND THE FAILURE WAS SWALLOWED AT `debug`, which is not emitted in production. So the one
place that could have said 「이 답을 못 만들었다」 said nothing anywhere.

🔵 NO NEW WORD WAS INVENTED FOR IT. `ready` is `ledger_trace.COVERAGE_STATES`'s and `unknown`
is already the state word in `config_backup` (ok/stale/missing/unknown) and
`enrichment_candidates.EXPECT_UNKNOWN`. A fourth spelling for one meaning is how a screen
ends up knowing only one of them.

⚠️ THIS FILE SCORES THE SOURCE OF ONE BLOCK. Reaching that `except` needs a database whose
retroactive read fails, and 「이 실패가 운영 로그에 보이나」 is not observable from a return
value at all — the text IS the subject here, not a proxy for it (CLAUDE.md 2026-09-03, per
assertion). The half that IS behavioural — the screen telling the two nulls apart — is scored
by `client2/tests/chain_queue_panel_harness.mjs`, which imports the panel.
"""
import ast
import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                            # noqa: E402

MAIN = os.path.join(os.path.dirname(__file__), "..", "main.py")


def queue_block():
    """The `try/except` that reads the retroactive in-flight state, as source."""
    src = io.open(MAIN, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            seg = ast.get_source_segment(src, node) or ""
            if "retroactive.queue_view" in seg:
                return seg
    raise AssertionError("the retroactive queue read is gone — this file lost its subject")


# --------------------------------------------------------------------- the two words

def test_the_two_words_are_distinct_and_not_new():
    """A state that equals the other state cannot separate anything."""
    assert (event_constants.RETROACTIVE_READ_READY
            != event_constants.RETROACTIVE_READ_UNKNOWN)
    assert event_constants.RETROACTIVE_READ_UNKNOWN == "unknown"
    assert event_constants.RETROACTIVE_READ_READY == "ready"


def test_the_words_were_borrowed_rather_than_coined():
    """🔵 THE SAME SPELLINGS THIS CODEBASE ALREADY USES. Asserted so a later rename to
    something prettier has to notice that three other modules disagree with it."""
    import ledger_trace

    assert event_constants.RETROACTIVE_READ_READY in ledger_trace.COVERAGE_STATES
    import enrichment_candidates

    assert enrichment_candidates.EXPECT_UNKNOWN == event_constants.RETROACTIVE_READ_UNKNOWN


# ------------------------------------------------------------------- both branches speak

def test_both_branches_say_which_one_happened():
    """🔴 THE GATE. One branch saying it and the other staying silent leaves the absent key
    meaning 「old server」 on a screen that is talking to a current one."""
    block = queue_block()
    assert "RETROACTIVE_READ_READY" in block, "the success path does not say it read"
    assert "RETROACTIVE_READ_UNKNOWN" in block, "the failure path does not say it could not"


def test_the_null_is_left_alone():
    """⚠️ NO-REGRESSION, AND IT IS THE POINT. `blocked_by: null` already means 「도는 것이
    없다」 and the panel deliberately draws nothing for it. Replacing that null with a state
    string would break the reader this round exists to serve."""
    block = queue_block()
    assert 'scheduler_bucket["blocked_by"] = None' in block


def test_the_failure_is_visible_where_an_operator_looks():
    """🔴 `debug` IS NOT EMITTED IN PRODUCTION. While this line was `debug`, a failed read was
    indistinguishable from a quiet one in the logs as well as on the screen — the screen fix
    alone would have left the operator with a box and no way to find out why."""
    block = queue_block()
    assert "logger.warning(" in block, "the swallowed failure is still invisible"
    assert "logger.debug(" not in block


def test_the_exception_is_still_swallowed_on_purpose():
    """⚠️ AVAILABILITY IS THE REASON THE `except` EXISTS — the queue view must answer even when
    the retroactive read cannot. This asserts the round did NOT turn a degraded answer into a
    500 while making the degradation visible."""
    block = queue_block()
    assert "raise" not in block
