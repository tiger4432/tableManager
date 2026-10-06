# -*- coding: utf-8 -*-
"""총괄 c1ddec935 (소유자 「가로 접어」) — `collapse_repeats`: a segment equal to the one before it
goes, when a value is written. For item ids written as an «a.b.c» hierarchy that repeat a name
where there is no lower level.

  written   stored        written   stored
  a.a.a     a             a.b.a     a.b.a
  a.b.b     a.b           ab.b      ab.b     (segments, not characters)
  a.a.b     a.b           a..a      a..a     (an empty segment stays)

Last in the order (alias -> join -> pad_last_number -> replace -> case -> this), so segments
compare as finally spelled. Write only, like `time`: `replace` cannot say it without `\\1`, which
the two engines read differently, and a written value is stored folded - nothing compares raw.
The write funnel, the preview, `folds_again` and the backfill all go through `_write_fold`.
"""
import pytest

import notation_norm as nn
from chain import replay
from test_a_written_column_is_stored_folded import (  # noqa: F401 - `env` is a fixture
    PLAIN, _declare, _rows, _stored_then_declared, _write, env)
from test_a_written_column_takes_the_declared_spelling import _refusals

COLLAPSE = {"collapse_repeats": "."}
DECLARED = {PLAIN: {"k": {"write": True, "rules": COLLAPSE},
                    "v": {"write": True, "rules": COLLAPSE}}}


@pytest.mark.parametrize("written, stored", [
    ("a.a.a", "a"), ("a.b.b", "a.b"), ("a.a.b", "a.b"),
    ("a.b.a", "a.b.a"), ("ab.b", "ab.b"), ("a..a", "a..a"), ("a...a", "a...a"),
])
def test_a_repeated_segment_is_stored_once(env, tmp_path, monkeypatch, written, stored):
    _declare(tmp_path, monkeypatch, DECLARED)
    _write(env, PLAIN, [{"k": "K", "v": written}])
    (row,) = _rows(env, PLAIN)
    assert row.v == stored


def test_segments_compare_as_finally_spelled(env, tmp_path, monkeypatch):
    _declare(tmp_path, monkeypatch, {PLAIN: {
        "k": {"write": True, "rules": COLLAPSE},
        "v": {"write": True, "rules": {"case": True, **COLLAPSE}}}})
    _write(env, PLAIN, [{"k": "K", "v": "A.a.a"}])
    (row,) = _rows(env, PLAIN)
    assert row.v == "A"


def test_a_key_written_with_repeats_finds_the_row_it_names(env, tmp_path, monkeypatch):
    """No second row: the row stored under the old spelling is found by it and re-keyed."""
    _stored_then_declared(env, tmp_path, monkeypatch, PLAIN,
                          [("f01.csv", [{"k": "a.a", "v": "x"}])], declared=DECLARED)
    _write(env, PLAIN, [{"k": "a.a", "v": "y"}], source="f02.csv")
    (row,) = _rows(env, PLAIN)
    assert (row.business_key_val, row.v) == ("a", "y")


def test_the_preview_and_the_backfill_fold_with_it(env, tmp_path, monkeypatch):
    _stored_then_declared(env, tmp_path, monkeypatch, PLAIN, [("f01.csv", [
        {"k": "K1", "v": "a.b.b"}, {"k": "K2", "v": "a.a.b"}, {"k": "K3", "v": "a.b"}])],
        declared=DECLARED)
    preview = nn.fold_preview(env, PLAIN, "v")
    (group,) = [g for g in preview["merge_groups"] if g["folded"] == "a.b"]
    assert sorted(v["raw"] for v in group["variants"]) == ["a.a.b", "a.b", "a.b.b"]
    assert preview["folds_again"]["values"] == 0, "a second fold moves nothing"
    replay.fold_written_notation(env, PLAIN, apply=True)
    assert sorted(r.v for r in _rows(env, PLAIN)) == ["a.b", "a.b", "a.b"]


@pytest.mark.parametrize("column, spec, says", [
    ("wafer", {"rules": COLLAPSE}, "'collapse_repeats' folds a value when it is written"),
    ("wafer", {"write": True, "rules": {"collapse_repeats": ".."}},
     "must be the one character that splits segments"),
    ("seen_at", {"write": True, "rules": {"time": {"from": ["%Y/%m/%d"]}, **COLLAPSE}},
     "'time' is the only rule"),
], ids=["without write", "not one character", "beside time"])
def test_a_collapse_is_refused_unless_written_and_one_character(column, spec, says):
    _specs, rejections = _refusals({column: spec})
    assert any(says in r["detail"] for r in rejections), rejections
