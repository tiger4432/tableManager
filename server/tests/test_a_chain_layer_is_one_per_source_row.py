# -*- coding: utf-8 -*-
"""총괄 8ec008914 · 4dd303f01 — a chain layer per source row, and a layer ranks as its writer (소유자 10-11
「체인인제션으로 소스 이름 잡으면서 행 거두기 안 되는 거 같은데」).

  「체인이 쓴 칸의 층은 원천 행마다 하나 — chain_ingestion (<원천 행>). 거두면 그 행 층만 걷히고 남은 행 층이 보인다」
  「층의 순위는 쓴이의 순위 — 같은 순위 안에서는 늦게 쓴 것」 (판정 10-11: 쓴이 순위는 체인 층에만)

  ① two source rows write one cell: two layers; either taken back, the other shows
  ② a row layer ranks as the chain's: it beats a newer file layer
  ③ a row layer's blank means emptied · `withdraw_source(chain_ingestion)` takes the row layers · an old
    envelope that names a row layer is the chain's
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
from chain import cell_layer, replay                                # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.database import Base                                  # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

SRC, TGT, LEFT, RIGHT = "cl_src", "cl_tgt", "cl_left", "cl_right"
TABLES = {SRC: {"business_key": "s", "composite_key_source": ["s"],
                "column_types": {c: "string" for c in ("s", "key", "v")}, "display_columns": ["s", "key", "v"]},
          TGT: {"business_key": "key", "composite_key_source": ["key"],
                "column_types": {c: "string" for c in ("key", "x", "y")}, "display_columns": ["key", "x", "y"]},
          LEFT: {"business_key": "lk", "composite_key_source": ["lk"],
                 "column_types": {c: "string" for c in ("lk", "job", "lot")}, "display_columns": ["lk", "job", "lot"]},
          RIGHT: {"business_key": "job", "composite_key_source": ["job"],
                  "column_types": {c: "string" for c in ("job", "lot")}, "display_columns": ["job", "lot"]}}
JOIN = {"name": "cl_join", "on": {"table": RIGHT},
        "derive": {"kind": "join", "join": {"on": [{"left": "job", "right": "job"}],
                                            "take": [{"from": "lot", "into": "lot"}]}},
        "into": {"table": LEFT}}
RULE = {"name": "cl_rule", "mapper": "cl_mapper", "enabled": True, "is_batch": True, "trigger_table": SRC,
        "target_table": TGT, "trigger_columns": ["key", "v"]}


def _copy(db, payload, rule=None):
    out = []
    for one in (payload if isinstance(payload, list) else [payload]):
        data = {k: (v or {}).get("value") for k, v in (one.get("data") or {}).items()}
        out.append({"updates": {"key": data["key"], "x": data.get("v")}, "origin_row_id": one["row_id"]})
    return {"updates": out}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    mapper_sdk.register("cl_mapper", _copy)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
        mapper_sdk.MAPPER_REGISTRY.pop("cl_mapper", None)
        mapper_sdk.MAPPER_PARAMS.pop("cl_mapper", None)


def _write(db, table, source_name, **cells):
    from database.context import channel, outbox_mode

    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            updates=dict(cells), source_name=source_name, updated_by="cl")]))
    db.commit()


def _drain(db, rules=(RULE,)):
    for _ in range(4):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        groups = {}
        for e in pending:
            groups.setdefault(get_payload_dict(e).get("transaction_id"), []).append(e)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, [dict(r) for r in rules])
            assert ok, error
            for e in events:
                event_constants.mark_processed(e, "SUCCESS")
            db.commit()
    raise AssertionError("the chain did not settle")


def _id(db, table, key):
    return db.query(models.DYNAMIC_TABLES[table]).filter_by(business_key_val=key).one().row_id


def _cell(db, key="K", column="x"):
    """(shown value, {layer: value}) of the target's cell."""
    db.expire_all()
    row = db.query(models.DYNAMIC_TABLES[TGT]).filter_by(business_key_val=key).one()
    return getattr(row, column), {s.source_name: s.value for s in db.query(models.CellSource).filter_by(
        table_name=TGT, row_id=row.row_id, column_name=column)}


def _row_layer(db, source_key):
    """The layer one source row's reading owns - (its rule, the row) since owner 11-06 step 2."""
    return crud.owned_layer_name("cl_rule", _id(db, SRC, source_key))


def _take_back(db, *source_keys):
    """A source row deleted, the way the delete path takes back what it fed."""
    ids = [_id(db, SRC, key) for key in source_keys]
    crud.delete_rows_batch(db, SRC, ids, "cl")
    db.commit()
    worker._withdraw_what_those_rows_fed(db, SRC, ids, "unanswered")


def _two_rows(db):
    _write(db, SRC, "user", s="s1", key="K", v="A")
    _drain(db)
    _write(db, SRC, "user", s="s2", key="K", v="B")
    _drain(db)


# --- ① · ② · ③ --------------------------------------------------------------------------------

def test_two_source_rows_writing_one_cell_leave_two_layers_and_the_later_shows(db):
    _two_rows(db)
    assert _cell(db) == ("B", {_row_layer(db, "s1"): "A", _row_layer(db, "s2"): "B"})


@pytest.mark.parametrize("taken, shown", [("s1", "B"), ("s2", "A")])
def test_taking_back_one_source_row_leaves_the_others_layer_shown(db, taken, shown):
    _two_rows(db)
    kept = {"s1": "s2", "s2": "s1"}[taken]
    left = _row_layer(db, kept)
    _take_back(db, taken)
    assert _cell(db) == (shown, {left: shown})


def test_a_row_layer_ranks_as_the_chain_and_beats_a_newer_file_layer(db):
    _write(db, SRC, "user", s="s1", key="K", v="A")
    _drain(db)
    _write(db, TGT, "lot_0915.csv", key="K", x="F")
    assert _cell(db) == ("A", {_row_layer(db, "s1"): "A", "lot_0915.csv": "F"})


def test_a_row_layers_blank_means_the_chain_emptied_the_cell(db):
    _write(db, SRC, "user", s="s1", key="K", v="A")
    _drain(db)
    _write(db, TGT, "lot_0915.csv", key="K", y="kept")          # not a shell once x is blank
    _write(db, SRC, "user", s="s1", v="")
    _drain(db)
    shown, layers = _cell(db)
    assert crud.is_blank_value(shown) and list(layers) == [_row_layer(db, "s1")], (shown, layers)
    assert crud.is_blank_value(layers[_row_layer(db, "s1")])


def test_withdrawing_chain_ingestion_takes_its_row_layers(db):
    _two_rows(db)
    _write(db, TGT, "lot_0915.csv", key="K", x="F")
    counted = replay.count_withdrawable(db, TGT, crud.CHAIN_SOURCE, columns=["x"])
    done = cell_layer.withdraw_source(db, TGT, crud.CHAIN_SOURCE, columns=["x"], apply=True)
    assert (counted["cells_claimed"], done["cells_withdrawn"]) == (2, 2)
    assert _cell(db) == ("F", {"lot_0915.csv": "F"})


def test_a_left_row_that_matches_another_right_row_keeps_the_first_rows_layer_and_shows_the_later(db):
    """뒤집음 · owner 11-06 step 2 (B): L re-matched from J1 to J2 holds the layer its join and its new key own - J1's
    goes, so taking J2's back can never show J1's again. 총괄 판정 10-11 ① ㄱ («left as it is»: both layers) is what
    this reverses."""
    from chain import rule_shape

    rules = rule_shape.expand_declaration(JOIN, crud.TABLE_CONFIG)[0]
    _write(db, RIGHT, "seed", job="J1", lot="A")
    _write(db, RIGHT, "seed", job="J2", lot="B")
    _write(db, LEFT, "seed", lk="L1", job="J1")
    _drain(db, rules)
    _write(db, LEFT, "user", lk="L1", job="J2")
    _drain(db, rules)
    db.expire_all()
    row = db.query(models.DYNAMIC_TABLES[LEFT]).filter_by(business_key_val="L1").one()
    layers = {s.source_name: s.value for s in db.query(models.CellSource).filter_by(
        table_name=LEFT, row_id=row.row_id, column_name="lot")}
    assert (row.lot, layers) == ("B", {crud.owned_layer_name(JOIN["name"], "J2"): "B"})


def test_an_old_envelope_naming_a_row_layer_is_the_chains(db):
    """An event queued before the channel says the chain only by its source name (총괄 f42b48591 3)."""
    event = models.DatabaseOutbox(table_name=SRC, event_type="EDIT",
                                  payload={"table_name": SRC, "source_name": "chain_ingestion (r1)"})
    assert worker._rule_accepts_event(dict(RULE), event) is False, "a rule that did not opt in woke"
