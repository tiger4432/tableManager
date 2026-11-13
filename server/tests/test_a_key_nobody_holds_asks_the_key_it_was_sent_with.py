# -*- coding: utf-8 -*-
"""Ruling 191 on the line path (S-90, lead 3eb161a9c ②, lead 11-11 안 1): write_lines' claim asks an item's assembled
key first and, when that is nobody's, the key it was sent with (`old_key`) - under the claim's lock, before a new key
is put; the row found is re-keyed in step 5½.

    assembled key    old key     the write
    nobody's         a row's     edits that row and re-keys it - one row (a rename by the old key, a raw spelling)
    a row's          a row's     edits the assembled key's row - identity first; the old key's row as it was
    nobody's         nobody's    a new row
    taken meanwhile  a row's     the re-key meets the key another write put after the claim read: the row merges there
"""
import pytest

from database import write_lines as wl
from test_write_lines_writes_a_line_a_change_and_its_current_line import (TABLE, _now, _write, fixture_db,  # noqa: F401
                                                                         keep_lines)


def _by_key(db):
    return {r["business_key_val"]: r for r in _now(db).values()}


def _seed(db, *rows):
    for n, (key, a) in enumerate(rows):
        _write(db, {"key": {"k": key}, "values": {"k": key, "a": a}, "source_name": "f1"}, tx="seed%d" % n)


def test_a_key_nobody_holds_finds_the_row_its_old_key_names_and_re_keys_it(db):
    _seed(db, ("K1", "x"))
    [row_id] = _now(db)
    out = _write(db, {"business_key_val": "K2", "old_key": "K1", "values": {"k": "K2", "a": "y"}, "source_name": "f1"},
                 tx="tx2")
    assert list(_by_key(db)) == ["K2"], "one row - none made for the new key"
    assert (_by_key(db)["K2"]["row_id"], _by_key(db)["K2"]["a"]) == (row_id, "y")
    assert out["changed"][row_id]["work"] == "edit"


def test_an_assembled_key_a_row_holds_wins_over_the_old_key(db):
    _seed(db, ("K1", "x"), ("K2", "z"))
    _write(db, {"business_key_val": "K2", "old_key": "K1", "values": {"k": "K2", "a": "y"}, "source_name": "f1"},
           tx="tx2")
    said = _by_key(db)
    assert (said["K1"]["a"], said["K2"]["a"]) == ("x", "y")


@pytest.mark.parametrize("old_key_first", [True, False])
def test_another_item_of_the_key_an_old_key_took_goes_to_the_same_row(db, old_key_first):
    """QA 11-11: [K2 sent as K1, K2] in one batch, either order - one row, the entity's row_id kept, the batch's
    last word shown; before, the plain K2 item minted a row and the found row merged into it."""
    _seed(db, ("K1", "x"))
    [row_id] = _now(db)
    renamed = {"business_key_val": "K2", "old_key": "K1", "values": {"k": "K2", "a": "y"}, "source_name": "f1"}
    plain = {"business_key_val": "K2", "values": {"k": "K2", "a": "z"}, "source_name": "f1"}
    out = _write(db, *([renamed, plain] if old_key_first else [plain, renamed]), tx="tx2")
    assert out["merged"] == {} and list(_by_key(db)) == ["K2"], out["merged"]
    assert (_by_key(db)["K2"]["row_id"], _by_key(db)["K2"]["a"]) == (row_id, "z" if old_key_first else "y")


def test_neither_key_held_makes_a_new_row(db):
    _seed(db, ("K1", "x"))
    _write(db, {"business_key_val": "K3", "old_key": "K9", "values": {"k": "K3", "a": "y"}, "source_name": "f1"},
           tx="tx2")
    assert sorted(_by_key(db)) == ["K1", "K3"]


def test_a_key_another_write_puts_after_the_claim_read_takes_the_row_in(db, monkeypatch):
    """Forced: the box's one session cannot race the claim, so the other writer's row is put right after the read."""
    from sqlalchemy import insert


    _seed(db, ("K1", "x"))
    [row_id] = _now(db)
    real = wl._by_old_key

    def and_another_writer(db_, now, *args):
        real(db_, now, *args)
        db_.execute(insert(now).values(row_id="other", business_key_val="K2", k="K2", a="w"))

    monkeypatch.setattr(wl, "_by_old_key", and_another_writer)
    out = _write(db, {"business_key_val": "K2", "old_key": "K1", "values": {"k": "K2", "a": "y"}, "source_name": "f1"},
                 tx="tx2")
    assert out["merged"] == {row_id: "other"}, out["merged"]
    assert list(_by_key(db)) == ["K2"] and _by_key(db)["K2"]["row_id"] == "other"
    assert _by_key(db)["K2"]["a"] == "y", "the write's value, merged into the key's holder"
