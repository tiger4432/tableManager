# -*- coding: utf-8 -*-
"""S-42: 「N행 중 M행 · <컬럼>」 counts the column the refusal named.

🔴 IT COUNTED `driver.occurred_at.column` UNCONDITIONALLY. An identity refusal was
therefore reported beside "0 of 200 rows, event_time" - a count of a column with nothing
to do with the refusal, under a sentence about another one. The owner read it exactly as
written: 「event time 좋은 행도」. The refusal's own path carries the column, so the
number and the sentence can be about the same cell.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.config_explorer_service import _refused_column      # noqa: E402


def test_an_identity_refusal_names_the_identity_column():
    assert _refused_column("event_frame.rows[3].target_id") == "target_id"


def test_a_time_refusal_still_names_the_time_column():
    """The case that used to be right by accident stays right on purpose."""
    assert _refused_column("event_frame.rows[0].event_time") == "event_time"


def test_a_page_refusal_names_its_own_column_not_the_time_one():
    """A base-frame refusal addresses `source_batch.rows[N].<col>` - a different frame,
    the same shape, and it must not be read as the time column either."""
    assert _refused_column("source_batch.rows[1].record_id") == "record_id"


def test_a_refusal_that_names_no_row_column_gets_no_count():
    """No count beats a wrong one. These paths address a reader, a declaration or a
    cursor - there is no row's cell behind them to count."""
    for path in ("source_preparation.join_reader",
                 "event_frame.columns.lot",
                 "event_frame.identity.lot",
                 "cursor_value.event_time",
                 "", None):
        assert _refused_column(path) == "", path


def test_a_role_inside_a_row_is_not_a_column_of_the_source():
    """🔴 THE INPUT THAT SEPARATES THE TWO READINGS, and the gate had no such input until
    a mutant survived. `role_frame.rows[0].roles.subject` has the same row shape as a
    column path, so "take what follows the bracket" returns `roles.subject` - a name the
    relation does not have. Asking it for that count is not a smaller answer, it is a
    different question."""
    assert _refused_column("role_frame.rows[0].roles.subject") == ""
