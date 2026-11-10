# -*- coding: utf-8 -*-
"""A table a rule writes whose business key has no valid unique index takes new keys today's way, with no lines
(lead 11-11 ㄴ) - the rules list says so on the rule's line with `lines.key_index_next`, the one sentence, read from the
catalogue only (C 11-11 ㄱ: no census on a list read). The same table with its index: nothing said."""
from sqlalchemy import Index, MetaData, Table, create_engine
from sqlalchemy.orm import sessionmaker

from chain import synthesis
from database import crud, lines, models

CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


def _db(monkeypatch, unique):
    engine = create_engine("sqlite://")
    monkeypatch.setitem(crud.TABLE_CONFIG, "rk_out", CFG)
    t = Table("rk_out", MetaData(), *lines._data_columns(CFG, models.sql_type_of, row_id_key=True))
    Index("ix_rk_out_bk", t.c.business_key_val, unique=unique)
    t.create(engine)
    return sessionmaker(bind=engine)()


def test_a_written_table_without_its_key_index_is_said_with_the_one_sentence(monkeypatch):
    db = _db(monkeypatch, unique=False)
    rules = [{"name": "r1", "target_table": "rk_out"}, {"name": "r2", "target_table": "elsewhere"}]
    said = synthesis.rules_without_key_index(db, rules)
    assert said == {"r1": ([], None, ["rk_out"])}, said
    line = synthesis.no_key_index_line(*said["r1"])
    assert line == lines.key_index_next([("rk_out", (lines.KEY_UNKNOWN, 0))]) and "rk_out" in line, line


def test_with_its_index_nothing_is_said(monkeypatch):
    assert synthesis.rules_without_key_index(_db(monkeypatch, unique=True),
                                             [{"name": "r1", "target_table": "rk_out"}]) == {}
