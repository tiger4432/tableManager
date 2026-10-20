# -*- coding: utf-8 -*-
"""소유자 10-20 «조인키가 계산 칼럼일때 빌수 있는데 유니크키 땜에 아무것도 못함» — 키가 «전부» 빈 행은 조인 유일성에서 빠진다.

조인은 그 행을 짝짓지 않았는데(534f375f8) 유일 인덱스 · 쓰기 가드는 빈 키를 «'' 한 키»로 봐서, 오른쪽 표에 빈 키 행이 둘이면
인덱스가 못 서거나 묶음이 거절됐다. 판정은 `crud.every_key_part_blank` 하나, SQL 쪽은 인덱스의 셋째 칸
`join_key_index.blank_key_slot_expression`. 부분 인덱스가 아닌 이유는 그 함수에 있다(쪽이 IN 100 개를 넘으면 순차 스캔, 총괄 10-20).
"""
import os
import sys

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import join_into, join_key_index, synthesis               # noqa: E402
from database import crud, models, schemas                           # noqa: E402
from database.database import Base                                   # noqa: E402

LEFT, RIGHT = "eb_left", "eb_right"
TABLES = {LEFT: {"business_key": "lid", "column_types": {"lid": "string", "k1": "string", "k2": "string", "got": "string"}},
          RIGHT: {"business_key": "rid", "column_types": {"rid": "string", "k1": "string", "k2": "string", "x": "string"}}}


def _rule(columns):
    return {"name": "eb_join_%d" % len(columns), "mapper": join_into.JOIN_INTO_MAPPER, "trigger_table": LEFT,
            "target_table": LEFT, "key": {"unique": True},
            "params": {"right_table": RIGHT, "on": [{"left": c, "right": c} for c in columns], "take": ["x"]}}


@pytest.fixture(autouse=True)
def _fresh():
    synthesis.reset_right_key_cache()
    yield
    synthesis.reset_right_key_cache()


def test_the_write_gate_lets_every_blank_key_through_and_still_refuses_a_shared_key(monkeypatch):
    """Two right rows whose join key is blank in every part are both written; two that share a key with one part
    blank, and two that share a filled key, are refused as before."""
    from chain import ingestion_worker

    monkeypatch.setattr(crud, "TABLE_CONFIG", dict(crud.TABLE_CONFIG, **TABLES))
    monkeypatch.setattr(ingestion_worker, "loaded_chain_rules", lambda: [_rule(["k1", "k2"])])
    monkeypatch.setattr(join_key_index, "unique_index_covering", lambda db, table, columns, folds=None: "uq_eb")
    rows = [("r1", "", ""), ("r2", None, None), ("r3", "", "V"), ("r4", "", "V"), ("r5", "K", "Z"), ("r6", "K", "Z")]
    batch = schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val=rid, updates={"rid": rid, "k1": k1, "k2": k2}) for rid, k1, k2 in rows])

    refused = crud.refuse_virtual_join_duplicates(None, RIGHT, batch)

    assert sorted(r["row"] for r in refused) == ["r3", "r4", "r5", "r6"], refused
    assert [item.business_key_val for item in batch.updates] == ["r1", "r2"]


def test_only_the_unique_index_carries_the_slot_and_its_name_says_so():
    unique = join_key_index.required_index_ddl(RIGHT, ["k1", "k2"])
    lookup = join_key_index.required_index_ddl(LEFT, ["k1", "k2"], unique=False)

    assert join_key_index.blank_key_slot_expression(RIGHT, ["k1", "k2"]) in unique
    assert "CASE" not in lookup
    assert join_key_index.required_index_name(RIGHT, ["k1"]).endswith("_ns_eb")
    assert join_key_index.required_index_name(LEFT, ["k1"], prefix=join_key_index.LOOKUP_PREFIX).endswith("_ns")


def _drop_mine(engine):
    """The scratch schema lives for the session - this file's two tables go at both ends, named in that schema."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        schema = c.execute(text("SELECT current_schema()")).scalar()
        assert schema and schema != "public", schema
        for name in TABLES:
            c.execute(text('DROP TABLE IF EXISTS "%s"."%s" CASCADE' % (schema, name)))


@pytest.fixture
def pg_tables(pg_engine):
    _drop_mine(pg_engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=pg_engine)
    models.sync_dynamic_tables_schema(pg_engine)
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        assert c.execute(text("SELECT to_regclass(:t)::text"), {"t": RIGHT}).scalar() == RIGHT
        schema = c.execute(text("SELECT current_schema()")).scalar()
        assert schema != "public", schema
        c.execute(text('INSERT INTO "%s" (row_id, business_key_val, rid, k1, k2, x) '
                       "SELECT 'r'||g, 'r'||g, 'r'||g, 'A'||g, 'B'||g, 'x'||g FROM generate_series(1, 200000) g" % RIGHT))
        c.execute(text('INSERT INTO "%s" (row_id, business_key_val, rid, k1, k2) VALUES '
                       "('e1','e1','e1',NULL,NULL), ('e2','e2','e2','',''), ('e3','e3','e3',NULL,'')" % RIGHT))
        c.execute(text('INSERT INTO "%s" (row_id, business_key_val, lid, k1, k2) '
                       "SELECT 'l'||g, 'l'||g, 'l'||g, 'A'||g, 'B'||g FROM generate_series(1, 3000) g" % LEFT))
        c.execute(text('ANALYZE "%s"' % RIGHT))
    yield pg_engine
    _drop_mine(pg_engine)
    for name in TABLES:
        crud.TABLE_CONFIG.pop(name, None)


def _build(engine, columns):
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text(join_key_index.required_index_ddl(RIGHT, columns)))
        c.execute(text('ANALYZE "%s"' % RIGHT))
    return join_key_index.required_index_name(RIGHT, columns)


def _plans_of(engine, run):
    """EXPLAIN of every SELECT on the right table the product sends while `run` runs - its own statements."""
    sent = []

    def keep(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and RIGHT in statement:
            sent.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", keep)
    try:
        run()
    finally:
        event.remove(engine, "before_cursor_execute", keep)
    assert sent, "the product sent no SELECT on the right table - nothing below measures anything"
    with engine.connect() as c:
        return ["\n".join(row[0] for row in c.exec_driver_sql("EXPLAIN " + s, p)) for s, p in sent]


@pytest.mark.pg
@pytest.mark.parametrize("columns", [["k1"], ["k1", "k2"]], ids=["one_column", "two_columns"])
def test_the_index_stands_over_blank_keys_and_the_join_and_the_gate_read_through_it(pg_tables, columns):
    engine = pg_tables
    name = _build(engine, columns)
    db = sessionmaker(bind=engine)()
    try:
        keys = {tuple("%s%d" % (c[-1] == "1" and "A" or "B", i) for c in columns): [0] for i in range(1, 2001, 2)}
        gate = _plans_of(engine, lambda: crud._stored_join_key_owners(db, RIGHT, columns, [None] * len(columns), keys))
        spec = join_into.join_spec(_rule(columns))
        left_model, right_model = models.DYNAMIC_TABLES[LEFT], models.DYNAMIC_TABLES[RIGHT]
        answer = {}
        join = _plans_of(engine, lambda: answer.setdefault("read", join_into._read_once(
            db, spec, left_model, right_model, [left_model.row_id.in_(["l%d" % i for i in range(1, 2001)])], LEFT)))
    finally:
        db.close()

    for plan in gate + join:
        assert name in plan and "Seq Scan" not in plan, plan
    pairs, answers, _empty = answer["read"]
    assert len(pairs) == 2000 and len(answers) == 2000
    assert all(key and not crud.every_key_part_blank(key) for key in answers)


@pytest.mark.pg
def test_blank_keys_never_meet_and_every_other_key_is_still_unique(pg_tables):
    engine = pg_tables
    _build(engine, ["k1", "k2"])
    insert = text('INSERT INTO "%s" (row_id, business_key_val, rid, k1, k2) VALUES (:r, :r, :r, :k1, :k2)' % RIGHT)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(insert, {"r": "e4", "k1": "", "k2": None})
        c.execute(insert, {"r": "p1", "k1": "", "k2": "V"})
        for row in ({"r": "p2", "k1": None, "k2": "V"}, {"r": "d1", "k1": "A7", "k2": "B7"}):
            with pytest.raises(IntegrityError):
                c.execute(insert, row)
        assert c.execute(text('SELECT count(*) FROM "%s" WHERE coalesce(k1, \'\') = \'\' AND coalesce(k2, \'\') = \'\''
                              % RIGHT)).scalar() == 4
