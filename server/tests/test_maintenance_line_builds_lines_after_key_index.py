"""The index line builds a table's lines right after it builds (or finds) that table's business key index - the
same lines.ensure_declared the schema sync calls (lead 11-11 ㄱ: no silent stretch of writes without history)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import lines, models
from runtime import index_wants, maintenance_line


def test_a_built_key_index_builds_that_tables_lines_and_only_that(monkeypatch):
    engine = create_engine("sqlite://")
    models.DatabaseOutbox.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    asks = [(1, ("lot_t", ["business_key_val"], models.KEY_UNIQUE)),
            (2, ("other_t", ["business_key_val"], models.KEY_UNIQUE)),
            (3, ("auto_t", ["lot"], "auto"))]
    words = {index_wants.index_name("lot_t", ["business_key_val"], models.KEY_UNIQUE): models.INDEX_BUILT,
             index_wants.index_name("other_t", ["business_key_val"], models.KEY_UNIQUE): models.INDEX_FAILED,
             index_wants.index_name("auto_t", ["lot"], "auto"): models.INDEX_BUILT}

    def a_round(_factory, _works, said=None, _cuts=None):
        said.update(words)
        return []

    built = []
    monkeypatch.setattr(maintenance_line, "_round", a_round)
    monkeypatch.setattr(maintenance_line, "_ask_works", lambda _f, asked: [])
    monkeypatch.setattr(lines, "ensure_declared", lambda e, tables=None: built.append(list(tables)) or {})
    maintenance_line._take_asks(factory, asks)
    assert built == [["lot_t"]]
