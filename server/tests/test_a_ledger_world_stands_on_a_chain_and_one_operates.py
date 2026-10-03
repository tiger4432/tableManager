# -*- coding: utf-8 -*-
"""총괄 e1f54cd72 · e67ef53f3 · 86d5061a0 · 2bb20ff56 — ledger worlds.

One layout file says which world OPERATES - every seat that names no world reads and writes it -
and what each world stands on, top first. A source shows from the topmost world of a chain that
speaks for it (its declaration differs from what speaks beneath, or it wrote that source); the
live follow-up writes each source into that world, so the operating world's view stays live in
every source. The grid reads a world's own atom view by name.
"""
import copy
import json
import os
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from support.isolated_pg import RUN_TOKEN                          # noqa: E402
import event_constants                                              # noqa: E402
import paths                                                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel                                # noqa: E402
from ledger import backfill, followup, schema                       # noqa: E402
from ledger.setup import load_setup                                 # noqa: E402
from ledger.store import LedgerStore                                # noqa: E402

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
CHANGED, KEPT = "wafer_process_recipe", "lot_slot_wafer"
TABLES = ("wafer_process", "lot_slot_wafer")
VIEW = schema.ATOM_ROWS_VIEW
TOKEN = "".join(ch for ch in RUN_TOKEN.lower() if ch.isalnum())[:16]
B1, W, N = "b" + TOKEN, "w" + TOKEN, "n" + TOKEN
EVENT_TIME = "2026-09-30 10:00:00"


def _sample(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as fh:
        return json.load(fh)


def _changed_document():
    """The sample, with wafer_process_recipe saying its core sentence without the `when`."""
    document = _sample("ledger_config.json.sample")
    mappings = document["sources"][CHANGED]["bind"]["mappings"]
    mappings.pop("dtwafer-processed-with-recipe")
    mappings["wafer-processed-with-recipe"].pop("when", None)
    return document


def _refused(document, source):
    """`source` read by an order that is not a column: the loader leaves it out alone."""
    document = copy.deepcopy(document)
    document["sources"][source]["read"]["order_by"] = ["no_such_column"]
    return document


def _said_otherwise():
    """The changed document, its recipe sentence carrying no `step` - a third way to say it."""
    document = _changed_document()
    document["sources"][CHANGED]["bind"]["mappings"]["wafer-processed-with-recipe"]["bind"].pop("step")
    return document


def _declare(world, document):
    root = Path(paths.config_path("ontology_worlds", world))
    root.mkdir(parents=True, exist_ok=True)
    (root / "ledger_config.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture(name="config")
def fixture_config(tmp_path, monkeypatch):
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    shutil.copy(os.path.join(SAMPLE, "table_config.json.sample"), config / "table_config.json")
    shutil.copy(os.path.join(SAMPLE, "ledger_config.json.sample"),
                config / "ontology" / "ledger_config.json")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))
    return config


# ------------------------------------------------------------------ the seat, no database

def test_no_layout_is_today(config):
    assert schema.operating_world() == schema.DEFAULT_WORLD
    assert schema.world_names() == schema.world_names(schema.DEFAULT_WORLD)
    assert schema.world_names().world is None
    assert schema.followed_by(None) == [(schema.DEFAULT_WORLD, None)]  # it speaks for all
    _declare(B1, _sample("ledger_config.json.sample"))
    names = schema.world_names(B1)
    assert names.beneath == (schema.DEFAULT_WORLD,)
    assert names.base_root == schema.world_names().declaration_root


def test_every_seat_that_names_no_world_reads_the_operating_one(config):
    from ledger import config as ledger_config
    from ledger import setup as ledger_setup
    from ledger_api import declared_entities

    _declare(W, _sample("ledger_config.json.sample"))
    entry = schema.operate(W, "tester")
    root = os.path.normcase(os.path.normpath(schema.world_names(W).declaration_root))

    def norm(path):
        return os.path.normcase(os.path.normpath(str(path)))

    assert schema.world_names().world == W and LedgerStore(None).names.world == W
    from ledger import trace_router
    assert trace_router._world(None).world == W                          # the walk route
    assert norm(os.path.dirname(ledger_config.config_path())) == root
    assert norm(os.path.dirname(declared_entities._config_path())) == root
    assert norm(load_setup().config_root) == norm(Path(root).resolve())
    # the default BY NAME stays the default
    assert schema.LEDGER_TABLE == "ledger_events"
    assert norm(ledger_setup.DEFAULT_ONTOLOGY_ROOT) != root
    assert (entry["world"], entry["by"]) == (W, "tester")

    schema.operate(schema.DEFAULT_WORLD)
    assert schema.world_names().world is None
    assert [h["world"] for h in schema.layout()["history"]] == [W, schema.DEFAULT_WORLD]
    with pytest.raises(LookupError):
        schema.operate("nope")


def test_a_chain_refuses_itself_a_world_twice_and_a_world_not_made(config):
    _declare(B1, _sample("ledger_config.json.sample"))
    with pytest.raises(LookupError):
        schema.stand(W, [W])                                         # itself: not made yet
    with pytest.raises(LookupError):
        schema.stand(W, ["nope"])
    with pytest.raises(ValueError):
        schema.stand(W, [schema.DEFAULT_WORLD, schema.DEFAULT_WORLD])
    with pytest.raises(ValueError):
        schema.stand(B1, [schema.DEFAULT_WORLD])                     # already made
    schema._write_layout({"beneath": {N: [N]}})                      # written by hand
    with pytest.raises(ValueError):
        schema.world_names(N)
    _declare(schema.DEFAULT_WORLD, _sample("ledger_config.json.sample"))
    assert schema.DEFAULT_WORLD not in schema.worlds()


def test_each_source_is_spoken_for_by_the_topmost_world_whose_declaration_differs(config):
    schema.stand(B1, [schema.DEFAULT_WORLD])
    _declare(B1, _changed_document())
    schema.stand(W, [B1, schema.DEFAULT_WORLD])
    _declare(W, _refused(_changed_document(), KEPT))
    names = schema.world_names(W)
    assert names.beneath == (B1, schema.DEFAULT_WORLD)
    assert names.base_root == schema.world_names(B1).declaration_root
    assert schema._declared_speakers(names) == [{KEPT}, {CHANGED}, None]
    assert schema.changed_sources(names) == {KEPT}

    schema.stand(N, [])
    _declare(N, _sample("ledger_config.json.sample"))
    assert schema.world_names(N).base_root is None
    with pytest.raises(LookupError):
        schema.require_world("undeclared")


def test_the_operating_world_and_a_world_stood_on_are_not_deleted(config):
    schema.stand(B1, [schema.DEFAULT_WORLD])
    _declare(B1, _sample("ledger_config.json.sample"))
    schema.stand(W, [B1, schema.DEFAULT_WORLD])
    _declare(W, _sample("ledger_config.json.sample"))
    schema.operate(W)
    with pytest.raises(ValueError, match="operating"):
        schema.world_deletion(None, W)
    with pytest.raises(ValueError, match=W):
        schema.world_deletion(None, B1)
    schema.operate(schema.DEFAULT_WORLD)
    with pytest.raises(ValueError, match=W):
        schema.world_deletion(None, B1)                              # W still stands on it
    with pytest.raises(ValueError):
        schema.world_deletion(None, schema.DEFAULT_WORLD)


def test_every_answer_that_lists_the_worlds_carries_one_shape(config):
    """총괄 e51e3e417: the declaration answer, /tables and the explorer's list."""
    import main
    from fastapi import HTTPException
    from ledger import trace_router
    from ledger_api import ontology_config_explorer_router as explorer_router

    schema.stand(B1, [schema.DEFAULT_WORLD])
    _declare(B1, _sample("ledger_config.json.sample"))
    schema.operate(B1)
    expected = {"worlds": [schema.DEFAULT_WORLD, B1], "operating": B1}
    for answer in (trace_router.ledger_declaration_catalog(world=None), main.list_tables(),
                   explorer_router.list_worlds()):
        assert {key: answer[key] for key in expected} == expected
    with pytest.raises(HTTPException) as refused:                    # 총괄 f1ad96964 ①
        trace_router._world("nowhere")
    assert refused.value.detail["worlds"] == expected["worlds"]


# ------------------------------------------------------------------ on PostgreSQL

@pytest.fixture(name="world")
def fixture_world(pg_engine, config, monkeypatch):
    import database.database as database_module
    from ledger_api import ontology_config_explorer_router as explorer_router

    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    monkeypatch.setattr(database_module, "engine", pg_engine)
    monkeypatch.setattr(explorer_router, "_services", {})
    sample = _sample("table_config.json.sample")
    declared = {name: sample[name] for name in (*TABLES, VIEW)}
    saved = dict(crud.TABLE_CONFIG)
    for name in declared:
        retire_dynamic_model(name)
    models.init_dynamic_models(declared)
    crud.TABLE_CONFIG.update(declared)

    def clean():
        with pg_engine.begin() as conn:
            for world in (B1, W, N):
                conn.execute(text("DROP SCHEMA IF EXISTS w_%s CASCADE" % world))
            for name in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
                for side in ("cell_sources", "database_outbox", "audit_logs"):
                    conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t'
                                      % (PG_TEST_SCHEMA, side)), {"t": name})
        raw = pg_engine.raw_connection()
        try:
            schema.ensure_schema(raw)
            from datetime import datetime, timezone
            schema.ensure_partition(raw, datetime(2026, 9, 30, 1, 0, tzinfo=timezone.utc))
            with raw.cursor() as cursor:
                for source in (CHANGED, KEPT):
                    cursor.execute(f"DELETE FROM {schema.LEDGER_TABLE} WHERE source_who = %s", (source,))
                    cursor.execute(f"DELETE FROM {schema.ROW_REF_TABLE} WHERE source_who = %s", (source,))
            raw.commit()
        finally:
            raw.close()
        schema._ensured.clear()

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    maker = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    session = maker()
    try:
        yield {"db": session, "maker": maker, "engine": pg_engine, "router": explorer_router}
    finally:
        session.close()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in declared:
            retire_dynamic_model(name)


def _write(world, table, rows, key=None):
    """`key`: the row's business key, for a write that changes a row rather than makes one."""
    db = world["db"]
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, business_key_val=key, source_name="user",
                                      updated_by="probe")
            for row in rows]))
        db.commit()


def _seed(world):
    _write(world, "wafer_process", [{"proc_id": "P1", "wafer_id": "W1", "step": "S1",
                                     "recipe_id": "RCP-1", "eventtime": EVENT_TIME}])
    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K1", "lot": "L1", "slot": "1",
                                      "wafer": "W1", "event_type": "load",
                                      "event_time": EVENT_TIME}])
    for source in (CHANGED, KEPT):
        backfill.run(world["engine"], source=source)


def _rows(world, relation, *columns, where=""):
    with world["engine"].connect() as conn:
        return sorted(tuple(r) for r in conn.execute(text(
            "SELECT %s FROM %s WHERE source_who IN (:a, :b) %s"
            % (", ".join(columns), relation, where)), {"a": CHANGED, "b": KEPT}))


def _saying(world, relation, needle):
    """Sources whose atoms in `relation` carry `needle` in their keys or payload."""
    return {who for (who,) in _rows(world, relation, "source_who",
                                    where="AND (subject_keys::text || coalesce(object_payload::text, '')) "
                                          "LIKE '%%%s%%'" % needle)}


def _b1(world):
    schema.stand(B1, [schema.DEFAULT_WORLD])
    _declare(B1, _changed_document())
    LedgerStore(world["engine"], world=B1).ensure_schema()
    backfill.run(world["engine"], source=CHANGED, world=B1)
    return schema.require_world(B1)


def _operate(world, name):
    return world["router"].operate_world(SimpleNamespace(headers={"X-User": "tester"}),
                                         {"world": name})


def _follow(world):
    from chain import ingestion_worker

    with world["engine"].begin() as conn:
        conn.execute(text('UPDATE "%s".database_outbox SET processed_chain = true '
                          "WHERE table_name IN ('wafer_process', 'lot_slot_wafer')" % PG_TEST_SCHEMA))
    for _ in range(200):
        if ingestion_worker._drain_ledger_followup_sync(world["maker"]) is None:
            return
    raise AssertionError("the follow-up did not drain")


@pytest.mark.pg
def test_a_chain_view_shows_each_source_from_the_world_that_speaks_for_it(world):
    _seed(world)
    b1 = _b1(world)
    schema.stand(W, [B1, schema.DEFAULT_WORLD])
    _declare(W, _changed_document())                                 # W says what B1 says
    LedgerStore(world["engine"], world=W).ensure_schema()
    backfill.rescope(world["engine"], load_setup(schema.world_names(W).declaration_root), KEPT,
                     None, None, apply=True, page_rows=backfill.RESCOPE_PAGE_ROWS,
                     whole_source=True, world=W)                     # W writes KEPT
    w = schema.require_world(W)
    assert set(_rows(world, w.read_relation, "source_who", "world_leg")) == {(KEPT, W), (CHANGED, B1)}
    assert set(_rows(world, b1.read_relation, "source_who", "world_leg")) == {
        (CHANGED, B1), (KEPT, schema.DEFAULT_WORLD)}
    assert schema.followed_by(world["engine"], w) == [
        (W, {KEPT}), (B1, {CHANGED}), (schema.DEFAULT_WORLD, None)]

    from ledger import trace_router
    from ledger_api import ledger_subgraph

    class _Plan(ledger_subgraph.SqlEvidenceLookup):
        def _execute(self, sql, params):
            self.plan = "\n".join(row[0] for row in trace_router.trace._fetch(
                self.connection, "EXPLAIN " + sql, params))
            return []

    with world["engine"].connect() as conn:
        planned = _Plan(conn, relation=w.read_relation)
        planned.claims_for_entities([("wafer", {"wafer": "W1"})], "outgoing", 50)
    assert "Subquery Scan" not in planned.plan, planned.plan        # three legs, still flat

    schema.stand(N, [])
    _declare(N, _sample("ledger_config.json.sample"))
    LedgerStore(world["engine"], world=N).ensure_schema()
    backfill.refresh_world_view(world["engine"], N)
    assert _rows(world, schema.require_world(N).read_relation, "source_who") == []  # no default atom


@pytest.mark.pg
def test_the_live_follow_up_writes_each_source_where_the_operating_view_shows_it(world):
    _seed(world)
    b1 = _b1(world)
    # operating = default: today's - the worker follows into the default
    assert schema.followed_by(world["engine"]) == [(schema.DEFAULT_WORLD, None)]
    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K1", "wafer": "W5"}], key="K1")
    _follow(world)
    assert _saying(world, schema.LEDGER_TABLE, "W5") == {KEPT}

    _operate(world, B1)
    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K1", "wafer": "W9"}], key="K1")
    _write(world, "wafer_process", [{"proc_id": "P1", "recipe_id": "RCP-2"}], key="P1")
    _follow(world)
    assert _saying(world, schema.LEDGER_TABLE, "W9") == {KEPT}       # B1 does not speak for it
    assert _saying(world, b1.ledger, "W9") == set()
    assert _saying(world, b1.ledger, "RCP-2") == {CHANGED}           # B1 speaks for it
    assert _saying(world, schema.LEDGER_TABLE, "RCP-2") == set()
    assert _saying(world, b1.read_relation, "W9") == {KEPT}          # the view is live in both
    assert _saying(world, b1.read_relation, "RCP-2") == {CHANGED}

    # back to the default: what B1 alone followed shows as drift, and the census's step closes it
    _operate(world, schema.DEFAULT_WORLD)
    default = load_setup(schema.world_names(schema.DEFAULT_WORLD).declaration_root)
    assert backfill.rows_drifted(world["engine"], default, CHANGED)["rows_drifted"] == 1
    backfill.retranslate_drifted(world["engine"], default, CHANGED, apply=True)
    assert backfill.rows_drifted(world["engine"], default, CHANGED)["rows_drifted"] == 0
    assert _saying(world, schema.LEDGER_TABLE, "RCP-2") == {CHANGED}


@pytest.mark.pg
def test_a_source_two_worlds_say_otherwise_is_the_topmost_ones_alone(world):
    """총괄 94e925b57: W on [B1, default], W and B1 each saying the recipe source their own way."""
    _seed(world)
    b1 = _b1(world)
    schema.stand(W, [B1, schema.DEFAULT_WORLD])
    _declare(W, _said_otherwise())
    LedgerStore(world["engine"], world=W).ensure_schema()
    backfill.run(world["engine"], source=CHANGED, world=W)
    w = schema.require_world(W)
    assert schema._declared_speakers(w) == [{CHANGED}, {CHANGED}, None]   # both say it
    assert _rows(world, b1.ledger, "source_who") and _rows(world, w.ledger, "source_who")
    assert {leg for who, leg in _rows(world, w.read_relation, "source_who", "world_leg")
            if who == CHANGED} == {W}
    assert schema.followed_by(world["engine"], w) == [
        (W, {CHANGED}), (B1, set()), (schema.DEFAULT_WORLD, None)]

    _operate(world, W)
    _write(world, "wafer_process", [{"proc_id": "P1", "recipe_id": "RCP-3"}], key="P1")
    _follow(world)
    assert _saying(world, w.ledger, "RCP-3") == {CHANGED}
    assert _saying(world, b1.ledger, "RCP-3") == set()
    assert _saying(world, schema.LEDGER_TABLE, "RCP-3") == set()


@pytest.mark.pg
def test_a_source_is_counted_and_written_in_the_world_that_speaks_for_it(world, monkeypatch, capsys):
    """총괄 8b81e79a0: B1 operates on the default and speaks for the recipe source. The load
    source is the default's: its census is measured and read there and says so, its next step
    names it, a backfill naming no world writes it there, and naming B1 for it is refused by
    name. Once B1 has written the load source too, B1 speaks for it and a backfill writes there."""
    import database.database as database_module
    from admin import retroactive
    from chain import ingestion_worker
    from ledger import admin, census_cli, trace_router
    from ledger.setup import LedgerSetupError
    from tests.support.retro_door import run_without_a_record

    monkeypatch.setattr(retroactive, "run_here", run_without_a_record(world["engine"]))
    monkeypatch.setattr(backfill, "beat", lambda result: None)
    _seed(world)
    _b1(world)
    _operate(world, B1)
    default = schema.DEFAULT_WORLD

    for source in (CHANGED, KEPT):                                   # the paced tick
        ingestion_worker._measure_one_source_sync(world["maker"], source)
    census = trace_router._row_census_by_source()
    assert {source: (census[source]["world"], census[source]["next_step"]) for source in census} == {
        CHANGED: (B1, "python -m ledger census --source %s --world %s" % (CHANGED, B1)),
        KEPT: (default, "python -m ledger census --source %s --world %s" % (KEPT, default))}
    monkeypatch.setattr(backfill, "census_sources", lambda setup: ([CHANGED, KEPT], []))
    assert census_cli.main([]) == 0                                  # a person's count, all
    counted = trace_router._row_census_by_source()
    assert all("rows_drifted" in counted[source] for source in (CHANGED, KEPT))  # in its world
    assert census_cli.main(["--source", KEPT, "--world", default]) == 0
    assert census_cli.main(["--source", KEPT, "--world", B1]) == 2
    assert "%s is spoken for by %s, not %s" % (KEPT, default, B1) in capsys.readouterr().err
    panel = {row["source"]: row for row in admin.ingestion_view(world["db"], [CHANGED, KEPT])["sources"]}
    assert {source: (row["world"], row["state"]) for source, row in panel.items()} == {
        CHANGED: (B1, admin.SOURCE_RAN_AND_WROTE), KEPT: (default, admin.SOURCE_RAN_AND_WROTE)}
    assert trace_router._row_census_by_source()[KEPT]["not_yet"]["estimate"] == 0

    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K2", "lot": "L1", "slot": "2",
                                      "wafer": "W2", "event_type": "load",
                                      "event_time": EVENT_TIME}])
    with pytest.raises(LedgerSetupError, match="%s is spoken for by %s" % (KEPT, default)):
        backfill.main(["--source", KEPT, "--world", B1])
    assert backfill.main(["--source", KEPT]) == 0
    b1 = schema.require_world(B1)
    assert (_saying(world, schema.LEDGER_TABLE, "W2"), _saying(world, b1.ledger, "W2")) == ({KEPT}, set())
    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K4", "lot": "L1", "slot": "4",
                                      "wafer": "W4", "event_type": "load",
                                      "event_time": EVENT_TIME}])
    retroactive.run_here("ledger_backfill", {"source": KEPT})       # the board's redo: no world
    assert (_saying(world, schema.LEDGER_TABLE, "W4"), _saying(world, b1.ledger, "W4")) == ({KEPT}, set())

    backfill.rescope(world["engine"], load_setup(b1.declaration_root), KEPT, None, None,
                     apply=True, page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True,
                     world=B1)                                        # B1 writes it: B1 speaks
    backfill.refresh_world_view(world["engine"], B1)
    assert schema.speaker(schema.followed_by(world["engine"]), KEPT) == B1
    _write(world, "lot_slot_wafer", [{"lot_slot_wafer_key": "K3", "lot": "L1", "slot": "3",
                                      "wafer": "W3", "event_type": "load",
                                      "event_time": EVENT_TIME}])
    assert backfill.main(["--source", KEPT]) == 0
    assert (_saying(world, b1.ledger, "W3"), _saying(world, schema.LEDGER_TABLE, "W3")) == ({KEPT}, set())
    assert database_module.engine is world["engine"]                 # canary: the fixture's


@pytest.mark.pg
def test_a_deletion_followed_in_a_branch_withdraws_there_and_leaves_the_default(world):
    _seed(world)
    b1 = _b1(world)
    default_before = _rows(world, schema.LEDGER_TABLE, "source_who", "source_raw_ref")
    assert _rows(world, b1.ledger, "source_who") and default_before
    with world["engine"].begin() as conn:
        (row_id,) = conn.execute(text('SELECT row_id FROM "%s".wafer_process' % PG_TEST_SCHEMA)).one()
        conn.execute(text('DELETE FROM "%s".wafer_process' % PG_TEST_SCHEMA))
    followup._follow(("wafer_process", (row_id,), "DELETE", time.time(), None, 0, None),
                     world["engine"], load_setup(b1.declaration_root), world=B1)
    assert _rows(world, b1.ledger, "source_who") == []                # withdrawn in the branch
    assert _rows(world, schema.LEDGER_TABLE, "source_who", "source_raw_ref") == default_before


@pytest.mark.pg
def test_the_grid_reads_the_atom_view_of_the_world_it_names(world):
    import main
    from fastapi import HTTPException

    _seed(world)
    _b1(world)

    def count(name):
        with world["engine"].connect() as conn:
            return conn.execute(text("SELECT count(*) FROM %s" % name)).scalar()

    in_b1 = count("w_%s.%s" % (B1, VIEW))
    in_default = count(VIEW)
    assert in_b1 and in_default and in_b1 != in_default
    db = world["db"]
    assert main.get_table_data_count(VIEW, world=B1, db=db)["total"] == in_b1
    page = json.loads(main.get_table_data(VIEW, order_by="atom_id", world=B1, db=db).body)
    assert len(page["data"]) == in_b1
    assert main.get_table_data_count(VIEW, db=db)["total"] == in_default    # no world: operating
    with pytest.raises(HTTPException) as refused:
        main.get_table_data_count(VIEW, world="nope", db=db)
    assert refused.value.status_code == 404 and refused.value.detail["reason"] == "world_unknown"
    _operate(world, B1)
    assert main.get_table_data_count(VIEW, db=db)["total"] == in_b1
    listed = main.list_tables()
    assert (listed["operating"], B1 in listed["worlds"], listed["per_world"]) == (B1, True, [VIEW])
