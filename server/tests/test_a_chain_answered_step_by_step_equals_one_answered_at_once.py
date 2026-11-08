# -*- coding: utf-8 -*-
"""Owner 11-06 step 2, its gate: what the chain leaves after rows came, changed and left one at a time equals what it
leaves when it answers the rows left at the end in one go (g′ = g(group − row) - the incremental answer is the
recomputed one). Two copies of the same tables and the same rules - a decide and a gathering join on one source -
the first fed a seeded random run of creates · key moves · value edits · deletions with the chain drained after each,
the second the first's final source rows in one batch, drained once.

  compared   every target row's shown values · the chain's layers on them by (row, column, owner key)
  not here   the shown value when two rules write one cell (ranked, `test_an_owned_layer_name_reads_back_its_rule_and_key`)
"""
import asyncio
import json
import os
import random
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
import paths                                                          # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel, outbox_mode                     # noqa: E402
from database.database import Base                                    # noqa: E402
from tests.support.enrich_decl import as_declaration                  # noqa: E402
from utils import heartbeat                                           # noqa: E402

WORLDS = ("pi", "pr")                     # step by step · at once
KEYS, VALUES = ("k1", "k2", "k3"), ("x", "y", "z")


def _tables(w):
    return {f"{w}_src": {"business_key": "rid", "composite_key_source": ["rid"],
                         "column_types": {"rid": "string", "k": "string", "v": "string"}},
            f"{w}_inv": {"business_key": "k", "composite_key_source": ["k"],
                         "column_types": {"k": "string", "vs": "string", "n": "number"}},
            f"{w}_tgt": {"business_key": "k", "composite_key_source": ["k"],
                         "column_types": {"k": "string", "gv": "string", "cnt": "number"}}}


TABLES = {name: spec for w in WORLDS for name, spec in _tables(w).items()}


def _declarations(w):
    decide = as_declaration(f"{w}_decide", {
        "source_table": f"{w}_src", "derived_table": f"{w}_inv", "decision_key": ["k"], "target_fields": ["vs", "n"],
        "aggregations": {"vs": {"fn": "unique_concat", "column": "v"}, "n": "count"}})
    join = {"name": f"{w}_join", "on": {"table": f"{w}_src"}, "into": {"table": f"{w}_tgt"},
            "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}], "take": [
                {"from": "v", "into": "gv", "fn": "unique_concat"}, {"from": "rid", "into": "cnt", "fn": "count"}]}}}
    return [decide, join]


class _NoClose:
    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


async def _no_post(_endpoint, _payload):
    return True


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path / "beats"))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(tmp_path / "beats" / (name + ".json")))
    monkeypatch.setattr(worker, "post_event_async", _no_post)
    mapper_sdk.discover()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoClose(session))
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [d for w in WORLDS for d in _declarations(w)]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    rules = [r for r in worker.load_chain_rules() if str(r.get("trigger_table") or "") in TABLES]
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: list(rules))
    try:
        yield session, rules
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _drain(db, rules):
    for _ in range(40):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        asyncio.run(worker.drain_events(db, pending, rules, None))
    raise AssertionError("the chain did not settle")


def _put(db, table, rows):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="pa") for row in rows]))
        db.commit()


def _delete(db, table, rid):
    row_id = db.query(models.DYNAMIC_TABLES[table]).filter_by(rid=rid).one().row_id
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.delete_rows_batch(db, table, [row_id], "pa")
        db.commit()


def _state(db, w):
    """Every target row's shown values and the chain's layers on it, by key - the rule's name taken out."""
    db.expire_all()
    shown = {}
    for table, columns in ((f"{w}_inv", ("vs", "n")), (f"{w}_tgt", ("gv", "cnt"))):
        model = models.DYNAMIC_TABLES[table]
        by_row = {row.row_id: row.k for row in db.query(model)}
        shown[table[3:]] = {row.k: tuple(getattr(row, c) for c in columns) for row in db.query(model)}
        layers = set()
        for layer in db.query(models.CellSource).filter(models.CellSource.table_name == table):
            owner = crud.layer_owner(layer.source_name)
            if crud.layer_ranks_as(layer.source_name) == crud.CHAIN_SOURCE or owner:
                layers.add((by_row.get(layer.row_id), layer.column_name, owner[1] if owner else layer.source_name,
                            str(layer.value)))
        shown[table[3:] + " layers"] = sorted(layers, key=str)
    return shown


def _run(rng, n):
    """A random run over the source: (op, rid, {cells})."""
    alive, made, ops = {}, 0, []
    for _ in range(n):
        choice = rng.random()
        if not alive or choice < 0.4:
            made += 1
            rid = "r%d" % made
            alive[rid] = {"rid": rid, "k": rng.choice(KEYS), "v": rng.choice(VALUES)}
            ops.append(("put", rid, dict(alive[rid])))
        elif choice < 0.8:
            rid = rng.choice(sorted(alive))
            cell = rng.choice(("k", "v"))
            alive[rid][cell] = rng.choice(KEYS if cell == "k" else VALUES)
            ops.append(("put", rid, {"rid": rid, cell: alive[rid][cell]}))
        else:
            rid = rng.choice(sorted(alive))
            del alive[rid]
            ops.append(("delete", rid, None))
    return ops, alive


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_the_chain_answered_step_by_step_leaves_what_it_leaves_answered_at_once(db, seed):
    db, rules = db
    ops, alive = _run(random.Random(seed), 24)
    for w in WORLDS:
        _put(db, f"{w}_tgt", [{"k": k} for k in KEYS])
    _drain(db, rules)

    for op, rid, cells in ops:                       # step by step: the chain drained after each
        if op == "put":
            _put(db, "pi_src", [cells])
        else:
            _delete(db, "pi_src", rid)
        _drain(db, rules)
    _put(db, "pr_src", [dict(row) for row in alive.values()])       # at once
    _drain(db, rules)

    stepped, at_once = _state(db, "pi"), _state(db, "pr")
    assert at_once["inv"], "the run left no key - nothing compared"
    assert stepped == at_once, ops
