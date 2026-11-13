# -*- coding: utf-8 -*-
"""Lead 11-13 ㄴ: a page's cells say their writer by `crud.writer_kind`, asked once per layer name of one `_named`
call - not once per cell (30 k cells, ~900 names: 0.054 -> 0.016 s on the STALL board's page). The answers are the
per-cell ones; nothing is held past the call."""
import grid_look
from database import crud

NAMES = ["user", "llm_draft", "chain_ingestion (r1 k1)", "lots.csv", "collision_merge", "a.csv", "b.csv"]
KINDS = {"person", "ai", "chain", "merge"}


def _page():
    rows = [{"row_id": "r%03d" % n, "data": {
        "value": {"priority_source": NAMES[n % len(NAMES)]},
        "note": {"priority_source": NAMES[(n + 3) % len(NAMES)]},
        "bare": {"priority_source": None} if n % 5 == 0 else {"value": 1},
    }} for n in range(70)]
    assert len({c["priority_source"] for r in rows for c in r["data"].values() if c.get("priority_source")}) == len(NAMES)
    return rows


def _counted(monkeypatch):
    asked = []
    plain = crud.writer_kind

    def writer_kind(name):
        asked.append(name)
        return plain(name)
    monkeypatch.setattr(crud, "writer_kind", writer_kind)
    return asked


def test_each_name_is_asked_once_and_every_cell_says_the_per_cell_answer(monkeypatch):
    rows = _page()
    expected = {(r["row_id"], col): crud.writer_kind(c["priority_source"]) for r in rows
                for col, c in r["data"].items() if c.get("priority_source")}
    expected = {cell: kind for cell, kind in expected.items() if kind in KINDS}
    assert expected and len(set(expected.values())) == 4, "CANARY: the page says all four asked writers"
    asked = _counted(monkeypatch)
    unnamed = grid_look._named(rows, None, KINDS)
    said = {(r["row_id"], col): c["written_by"] for r in rows for col, c in r["data"].items() if "written_by" in c}
    assert said == expected
    assert sorted(asked) == sorted(NAMES), "once per name - %d asks for %d cells" % (len(asked), 140)
    assert unnamed == {"r%03d" % n for n in range(0, 70, 5)}, "a cell with no layer leaves its row to be read"


def test_a_column_off_the_rule_is_neither_asked_nor_said(monkeypatch):
    rows = _page()
    asked = _counted(monkeypatch)
    grid_look._named(rows, {"value"}, KINDS)
    assert not any("written_by" in r["data"]["note"] for r in rows)
    assert sorted(asked) == sorted(NAMES), "value's cells name every name once"


def test_the_next_call_asks_again(monkeypatch):
    asked = _counted(monkeypatch)
    grid_look._named(_page(), None, KINDS)
    grid_look._named(_page(), None, KINDS)
    assert len(asked) == 2 * len(NAMES), "held for one call only - a layer's kind follows the config"
