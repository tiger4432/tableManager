"""Lead 11-09 (speed, owner «100 배»): the virtual walk read the index catalogue once per table every request - 4 of
a 2-hop walk's 10 statements, 7 of its 34 ms. A key column an index serves is held for the process (`_SERVED`) and
not asked again; a column no index serves is asked every request (an index may have been built since); an end keyed
by no text column is never asked (nothing to serve it); a declaration compiled again empties what was held.
Each end says so (lead 11-11): a served one its index, one keyed by no text column that none is asked - on the log once."""
from types import SimpleNamespace

from database import models
from ledger import sql_translate, trace_router
from runtime import index_wants

INDEX = {"name": "ix_t1_a", "columns": ["a", "row_id"], "using": "btree", "where": None, "search": []}


def _leg(relation, columns, keys=None):
    keys = columns if keys is None else keys
    return SimpleNamespace(relation=relation, columns={"outgoing": columns}, source="s", world_name="w",
                           columns_of=lambda arm: [(key, {"column": key}) for key in keys])


def test_a_served_column_is_read_once_an_unserved_one_every_time_and_no_text_column_never(monkeypatch):
    legs = [_leg("t1", ["a"]), _leg("t2", ["b"]), _leg("t3", [], keys=["x"])]
    monkeypatch.setattr(trace_router, "_compiled", lambda connection, names: (legs, []))
    monkeypatch.setattr(trace_router, "_SERVED", {})
    monkeypatch.setattr(index_wants, "_WORDS", {})
    read, told = [], []
    monkeypatch.setattr(models, "catalogue_indexes", lambda raw, table: read.append(table) or ([INDEX] if table == "t1" else []))
    monkeypatch.setattr(index_wants, "want", lambda *a, **k: None)
    monkeypatch.setattr(index_wants.logger, "log", lambda level, form, said: told.append(said))
    connection = SimpleNamespace(connection=SimpleNamespace(dbapi_connection=None), engine=None)

    for _ in range(3):
        _legs, said = trace_router._engine_reading(connection, "virtual", [])
        assert said["scans"] == [{"table": "t2", "column": "b", "said": None},
                                 {"table": "t3", "column": "x", "said": "t3 (x) - not a text key, no index asked"}]
        assert said["served"] == [{"table": "t1", "column": "a", "said": "t1 (a) - served by ix_t1_a"}]
    assert sorted(read) == ["t1", "t2", "t2", "t2"]                 # t1 once, t2 every request, t3 never
    assert sorted(told) == ["t1 (a) - served by ix_t1_a", "t3 (x) - not a text key, no index asked"]   # once a word


def test_a_declaration_compiled_again_empties_what_was_held(monkeypatch, tmp_path):
    declaration = tmp_path / "ledger_config.json"
    declaration.write_text("{}", encoding="utf-8")
    names = [SimpleNamespace(name="w", declaration_path=str(declaration), declaration_root=str(tmp_path))]
    from ledger import setup
    monkeypatch.setattr(setup, "load_setup", lambda root: SimpleNamespace(snapshot=None))
    monkeypatch.setattr(sql_translate, "compile_world", lambda snapshot, fetch, world: ([], []))
    monkeypatch.setattr(trace_router, "_COMPILED", {})
    monkeypatch.setattr(trace_router, "_SERVED", {("t1", "a"): "ix_t1_a"})
    trace_router._compiled(None, names)
    assert trace_router._SERVED == {}
    trace_router._SERVED[("t1", "a")] = "ix_t1_a"
    trace_router._compiled(None, names)                              # the same stamp: nothing compiled, kept
    assert trace_router._SERVED == {("t1", "a"): "ix_t1_a"}


def test_an_ask_that_broke_is_its_column_s_last_word(monkeypatch):
    """Lead 11-11 ㄴ: last_word None means «queued, no answer yet» only - an ask that raised says so there too."""
    def broke(*_a):
        raise RuntimeError("no connection")

    monkeypatch.setattr(index_wants, "_WORDS", {})
    monkeypatch.setattr(index_wants, "ask", broke)
    index_wants._asked(("t2", ("b",), models.AUTO_WALK_KEY), "t2", ["b"], models.AUTO_WALK_KEY, None, None)
    assert index_wants.last_word("t2", "b").startswith(
        "an automatic index on t2 (b) was not asked: RuntimeError: no connection")    # + where (`told`)
