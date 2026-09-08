# -*- coding: utf-8 -*-
"""S-66 (판정 150). A row id is the engine's; a caller may not invent one for a NEW row.

uuid7 is time-ordered, so "later row, later id" holds and anything that pages on `row_id`
walks arrivals in order. A supplied id that is not uuid7 breaks that silently.

🔴 IT ALREADY DID. Measured 2026-09-08: ten hand-written `zzdoe-wp-brk-*` ids sit in
`wafer_process`, whose `row_id` column is varchar, and they sort AFTER every uuid7. The
ledger's cursor for that source came to rest on the largest of them, and the 470,000 rows
loaded afterwards were then invisible to the forward scan -- with no error and a cursor
reporting it had finished. Those ten came from an investigation fixture on 2026-08-29, not
from any committed generator, which is exactly why a guard and not a convention is the fix.

⚠️ THE UPDATE PATH IS UNTOUCHED, and that is the whole reason this sits where it does.
Naming an existing row by its id is how callers address rows; what is refused is MINTING one.

🔴 THE MUTATION: delete the guard (return `supplied or uuid7()`) and
`test_a_hand_written_row_id_is_refused` goes green-to-red -- a string id would be accepted
again, which is the state that produced the defect above.
"""
import os
import sys
import uuid

import pytest
import uuid6

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud                                            # noqa: E402


def test_an_absent_id_is_minted_by_the_engine():
    for absent in (None, "", 0):
        minted = crud._engine_minted_row_id(absent, "wafer_process")
        assert uuid.UUID(minted).version == 7


def test_an_engine_shaped_id_is_accepted_unchanged():
    """A caller re-using an id the engine minted -- a re-push keeping a row's identity --
    is not inventing anything."""
    supplied = str(uuid6.uuid7())
    assert crud._engine_minted_row_id(supplied, "dt_map") == supplied


def test_a_hand_written_row_id_is_refused():
    """⛔ THE ONE THAT BROKE THINGS. `zzdoe-wp-brk-1` is the literal that actually did it."""
    with pytest.raises(ValueError) as caught:
        crud._engine_minted_row_id("zzdoe-wp-brk-1", "wafer_process")
    assert "wafer_process" in str(caught.value)
    assert "zzdoe-wp-brk-1" in str(caught.value)


def test_another_uuid_version_is_refused_too():
    """⚠️ THE SHAPE IS NOT THE POINT, THE ORDERING IS. A uuid4 parses and looks like an id,
    and sorts randomly -- which is the same defect wearing a better costume."""
    with pytest.raises(ValueError):
        crud._engine_minted_row_id(str(uuid.uuid4()), "dt_map")


def test_it_refuses_rather_than_quietly_minting_a_replacement():
    """Substituting one would leave the caller believing the id it chose is the id that
    exists -- two truths about one row."""
    try:
        crud._engine_minted_row_id("123", "dt_map")
    except ValueError as exc:
        assert "Omit row_id" in str(exc)
    else:
        raise AssertionError("a bad id was accepted")


def test_the_create_branch_uses_the_guard():
    """The seat, so the guard cannot be left beside an unguarded literal."""
    import inspect

    body = inspect.getsource(crud._get_or_create_row)
    assert "_engine_minted_row_id(" in body
    assert "update_item.row_id or str(uuid6.uuid7())" not in body
