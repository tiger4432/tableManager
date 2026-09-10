# -*- coding: utf-8 -*-
"""체인 그룹의 시도 상한은 «선언 칸»이고 기본은 1 (S-139, 소유자 09-10 21:35 「3회 없애, 1회면 끝」).

🔴 THE CAP WAS SPELLED TWICE. `retry_count >= 3` decided, and a separate log line said
「(N/3)」 - so moving the cap moved one and not the other, and a log that is wrong about
「how many tries are left」 lies quietly. Verdict, reason and log now read one function.

⚠️ THE MECHANISM IS NOT REMOVED, THE DEFAULT MOVED. Declaring `max_group_attempts: 3`
restores the old behaviour exactly, which is what makes this a declaration rather than a
deletion.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker as worker                              # noqa: E402


def _document(monkeypatch, value):
    monkeypatch.setattr(worker, "_RULES_DOCUMENT", value)


def test_an_undeclared_cap_is_one_attempt(monkeypatch):
    _document(monkeypatch, {})

    assert worker.DEFAULT_MAX_GROUP_ATTEMPTS == 1
    assert worker.max_group_attempts() == 1


def test_the_old_behaviour_is_one_line_of_declaration_away(monkeypatch):
    _document(monkeypatch, {"max_group_attempts": 3})

    assert worker.max_group_attempts() == 3


def test_a_cap_below_one_would_isolate_a_group_that_never_ran(monkeypatch):
    """⛔ 0 이하는 「한 번도 안 시도한다」가 되어 그룹이 영원히 격리된다."""
    for bad in (0, -5):
        _document(monkeypatch, {"max_group_attempts": bad})
        assert worker.max_group_attempts() == 1


def test_a_cap_that_is_not_a_number_warns_and_falls_back(monkeypatch):
    """A settings typo must not stop the chain - the same rule the ingestion pace follows."""
    _document(monkeypatch, {"max_group_attempts": "three"})

    assert worker.max_group_attempts() == 1


def test_the_verdict_the_reason_and_the_log_read_one_number():
    """🔴 THE POINT OF S-139. Three spellings of one cap is how a log comes to disagree with
    the behaviour it describes."""
    import inspect

    body = inspect.getsource(worker.process_pending_groups)

    assert "attempts_cap = max_group_attempts()" in body
    assert "event.retry_count >= attempts_cap" in body
    assert "{max_retry_num}/{attempts_cap}" in body
    assert ">= 3" not in body, "the literal cap must be gone from the verdict"
    assert "/3)" not in body, "and from the log"


def test_the_row_expansion_at_the_quarantine_boundary_is_untouched():
    """⚠️ OUTBOX-4 STAYS. A collapsed event covers up to 1,000 rows, so the boundary
    re-expands into per-row events to narrow the poison - that now happens on the FIRST
    failure, which makes it more useful rather than less."""
    import inspect

    body = inspect.getsource(worker.process_pending_groups)

    assert "is_collapsed_payload" in body
    assert "OUTBOX-4" in body
