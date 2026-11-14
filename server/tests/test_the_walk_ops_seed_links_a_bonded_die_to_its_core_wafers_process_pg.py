"""`scripts/seed_walk_ops.py` at a small shape on PostgreSQL (lead 11-14: the generator lands with a test on a small size):
COPY writes the three tables, each row keyed as the product keys it; every chip of a package reaches - through its core
die's lot and slot - a core wafer that has a process list, and a package's chips come from as many wafers in as many lots
as it has layers (owner 11-14). A schema of its own, dropped after: the shared scratch schema holds the sample's own
wafer_process and bonding_log."""
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import pytest                                                          # noqa: E402
from sqlalchemy import Column, DateTime, Float, MetaData, String, Table, create_engine, text   # noqa: E402

import seed_walk_ops                                                   # noqa: E402
from database import crud                                              # noqa: E402

pytestmark = pytest.mark.pg

TABLES = {
    "wafer_process": {"business_key": "proc_id",
                      "column_types": {"proc_id": "string", "wafer_id": "string", "lot": "string", "slot": "string",
                                       "step": "string", "eqp_id": "string", "result": "string",
                                       "eventtime": "datetime", "recipe_id": "string"}},
    "core_wafer_map": {"business_key": "core_cell_key", "composite_key_source": ["core_lot", "core_slot", "core_x", "core_y"],
                       "composite_key_separator": "_",
                       "column_types": {"core_cell_key": "string", "core_lot": "string", "core_slot": "string",
                                        "core_x": "number", "core_y": "number", "c_bn": "string", "wafer_id": "string",
                                        "event_time": "string"}},
    "bonding_log": {"composite_key_source": ["base_id", "bx", "by", "layer"], "composite_key_separator": "|",
                    "column_types": {"base_id": "string", "bx": "number", "by": "number", "layer": "string",
                                     "core_lot": "string",
                                     "core_slot": "number", "cx": "number", "cy": "number", "dt_lot": "string",
                                     "dt_slot": "number", "dt_x": "number", "dt_y": "number",
                                     "event_time": "datetime"}},
}
SQL_TYPE = {"string": String, "number": Float, "datetime": DateTime(timezone=True)}
SHAPE = {"lots": 4, "slots": 2, "steps": 3, "side": 2, "bases": 2, "layers": 3}


@pytest.fixture
def board(pg_engine, monkeypatch):
    url = pg_engine.url.render_as_string(hide_password=False)
    schema = "seed_walk_%s" % uuid.uuid4().hex[:8]
    admin = create_engine(url)
    with admin.begin() as c:
        c.execute(text('CREATE SCHEMA "%s"' % schema))
    engine = create_engine(url, connect_args={"options": "-csearch_path=%s" % schema})
    meta = MetaData()
    for name, config in TABLES.items():
        Table(name, meta, Column("row_id", String, primary_key=True), Column("business_key_val", String, unique=True),
              Column("created_at", DateTime(timezone=True)), Column("updated_at", DateTime(timezone=True)),
              *[Column(c, SQL_TYPE[t]) for c, t in config["column_types"].items()])
    meta.create_all(engine)
    for name, config in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, config)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.execute(text('DROP SCHEMA "%s" CASCADE' % schema))
        admin.dispose()


def test_the_three_tables_hold_the_shape_keyed_as_the_product_keys_them(board):
    held = seed_walk_ops.seed(board, log=lambda *_: None, **SHAPE)
    wafers = SHAPE["lots"] * SHAPE["slots"]
    packages = SHAPE["bases"] * SHAPE["side"] ** 2
    dies = packages * SHAPE["layers"]
    assert held == {"wafer_process": wafers * SHAPE["steps"], "core_wafer_map": dies, "bonding_log": dies}
    with board.connect() as c:
        for table, config in TABLES.items():
            parts = config.get("composite_key_source")
            for row in c.execute(text('SELECT * FROM "%s"' % table)).mappings():
                want = crud.compose_business_key(table, [row[p] for p in parts], parts) if parts \
                    else row[config["business_key"]]
                assert row["business_key_val"] == want, (table, dict(row))
        assert c.execute(text("SELECT count(DISTINCT row_id) FROM bonding_log")).scalar() == dies


def test_every_chip_reaches_a_core_wafer_with_a_process_list_from_its_own_wafer_and_lot(board):
    seed_walk_ops.seed(board, log=lambda *_: None, **SHAPE)
    with board.connect() as c:
        # the chain's join matches bonding_log.core_slot (a number) to core_wafer_map.core_slot («01») as a number
        unreached = c.execute(text(
            "SELECT count(*) FROM bonding_log b WHERE NOT EXISTS ("
            " SELECT 1 FROM core_wafer_map m JOIN wafer_process p ON p.wafer_id = m.wafer_id"
            " WHERE m.core_lot = b.core_lot AND m.core_slot::numeric = b.core_slot::numeric"
            " AND m.core_x = b.cx AND m.core_y = b.cy)")).scalar()
        bases = {r[0] for r in c.execute(text("SELECT DISTINCT base_id FROM bonding_log"))}
        cores = {r[0] for r in c.execute(text("SELECT DISTINCT wafer_id FROM core_wafer_map"))}
        slots = {r[0] for r in c.execute(text("SELECT DISTINCT core_slot FROM core_wafer_map"))}
        packages = c.execute(text(
            "SELECT base_id, bx, by, count(*), count(DISTINCT layer), count(DISTINCT core_lot),"
            " count(DISTINCT (core_lot, core_slot)) FROM bonding_log GROUP BY 1, 2, 3")).fetchall()
    assert unreached == 0
    assert len(bases) == SHAPE["bases"] and len(cores) == SHAPE["bases"] * SHAPE["layers"] and not bases & cores
    layers = SHAPE["layers"]
    assert len(packages) == SHAPE["bases"] * SHAPE["side"] ** 2
    assert all(row[3:] == (layers, layers, layers, layers) for row in packages), packages
    assert all(len(s) == 2 for s in slots), slots          # «01»: the spelling the join's formula folds


def test_a_shape_with_too_few_wafers_is_refused_before_a_row_is_written(board):
    with pytest.raises(ValueError, match="need 12 wafers"):
        seed_walk_ops.seed(board, log=lambda *_: None, **dict(SHAPE, bases=3))
    with board.connect() as c:
        assert c.execute(text("SELECT count(*) FROM wafer_process")).scalar() == 0


def test_tables_writes_only_the_tables_named(board):
    held = seed_walk_ops.seed(board, log=lambda *_: None, tables=("bonding_log",), **SHAPE)
    with board.connect() as c:
        counts = {t: c.execute(text('SELECT count(*) FROM "%s"' % t)).scalar() for t in TABLES}
    assert list(held) == ["bonding_log"]
    assert counts == {"wafer_process": 0, "core_wafer_map": 0, "bonding_log": held["bonding_log"]}
