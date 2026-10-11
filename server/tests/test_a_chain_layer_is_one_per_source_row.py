# -*- coding: utf-8 -*-
"""총괄 8ec008914 · 4dd303f01 — a chain layer per source row, and a layer ranks as its writer (소유자 10-11
「체인인제션으로 소스 이름 잡으면서 행 거두기 안 되는 거 같은데」).

  「체인이 쓴 칸의 층은 원천 행마다 하나 — chain_ingestion (<원천 행>). 거두면 그 행 층만 걷히고 남은 행 층이 보인다」
  「층의 순위는 쓴이의 순위 — 같은 순위 안에서는 늦게 쓴 것」 (판정 10-11: 쓴이 순위는 체인 층에만)

  ① two source rows write one cell: two layers; either taken back, the other shows
  ② a row layer ranks as the chain's: it beats a newer file layer
  ③ a row layer's blank means emptied · `withdraw_source(chain_ingestion)` takes the row layers · an old
    envelope that names a row layer is the chain's
  ④ the layer fold: the preview counts what the run does, a re-run does nothing, and a row taken back
    after the fold shows what is left beneath - not the old plain layer
"""
import os
import sys
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
from admin import retroactive                                       # noqa: E402
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
    return crud.merged_layer_name(crud.CHAIN_SOURCE, _id(db, SRC, source_key))


def _take_back(db, *source_keys):
    """A source row deleted, the way the delete path takes back what it fed."""
    ids = [_id(db, SRC, key) for key in source_keys]
    crud.delete_rows_batch(db, SRC, ids, "cl")
    db.commit()
    worker._retract_what_those_rows_fed(db, SRC, ids)


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
    """총괄 판정 10-11 ① ㄱ - left as it is, and seen here: a join's source row is the right row it matched. L
    re-matched from R1 to R2 holds both layers; R2's, written later, shows. Taking R2 back would show R1's again."""
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
    first, later = (crud.merged_layer_name(crud.CHAIN_SOURCE, _id(db, RIGHT, job)) for job in ("J1", "J2"))
    assert (row.lot, layers) == ("B", {first: "A", later: "B"})


def test_an_old_envelope_naming_a_row_layer_is_the_chains(db):
    """An event queued before the channel says the chain only by its source name (총괄 f42b48591 3)."""
    event = models.DatabaseOutbox(table_name=SRC, event_type="EDIT",
                                  payload={"table_name": SRC, "source_name": "chain_ingestion (r1)"})
    assert worker._rule_accepts_event(dict(RULE), event) is False, "a rule that did not opt in woke"


# --- ④ the fold -------------------------------------------------------------------------------

T0 = datetime(2026, 10, 1, 1, 0, 0)


def _stack(db, key, layers, shown):
    """`[(name, value, origin)]` oldest first, an hour apart, and the value the column shows today."""
    row = db.query(models.DYNAMIC_TABLES[TGT]).filter_by(business_key_val=key).one()
    for hour, (name, value, origin) in enumerate(layers):
        db.add(models.CellSource(table_name=TGT, row_id=row.row_id, column_name="x", source_name=name,
                                 value=value, updated_by="cl", origin_row_id=origin,
                                 ingested_at=T0 + timedelta(hours=hour)))
    row.x = shown
    db.commit()


def _stacked(db):
    """The cells as a table stood before the landing - every chain write under the plain name."""
    plain, row = crud.CHAIN_SOURCE, lambda r: crud.merged_layer_name(crud.CHAIN_SOURCE, r)
    copy = crud.merged_layer_name(crud.CHAIN_SOURCE, "K9_abc123")
    cells = {
        "A": ([(plain, "a", "r1")], "a"),                                   # renamed
        "B": ([(plain, "b", "r1"), (row("r1"), "b2", "r1")], "b"),          # its row's layer is there: goes
        "C": ([("f.csv", "F", None), (plain, "c", None), (row("r2"), "c", "r2")], "c"),   # repeated: goes
        "D": ([(row("r2"), "d", "r2"), (plain, "Z", None)], "Z"),           # differs, newer: stays and shows
        "E": ([(plain, "e", None)], "e"),                                   # alone: stays
        "F": ([(copy, "M", None), ("f.csv", "F1", None)], "F1"),            # a merge copy now ranks as the chain
        "G": ([(plain, "P", None), (row("r3"), "R", "r3")], "P"),           # differs, older: stays, R shows
        "H": ([(row("r3"), "R", "r3"), ("f.csv", "FH", None)], "FH"),       # the row layer beats the file
    }
    _write(db, TGT, "seed", key="seed")
    for key in cells:
        _write(db, TGT, "seed", key=key)
    db.query(models.CellSource).filter(models.CellSource.source_name == "seed").delete()
    db.commit()
    for key, (layers, shown) in cells.items():
        _stack(db, key, layers, shown)


ACTIONS = ("layers_deleted", "chain_renamed", "chain_deleted", "shown_changed")


def test_the_fold_previews_what_it_does_and_a_rerun_does_nothing(db):
    _stacked(db)
    dry = replay.fold_file_layers(db, TGT, apply=False)
    assert {key: dry[key] for key in ACTIONS + ("chain_differs", "chain_unstamped", "chain_copies")} == {
        "layers_deleted": 0, "chain_renamed": 1, "chain_deleted": 2, "shown_changed": 4,
        "chain_differs": 2, "chain_unstamped": 4, "chain_copies": 1}
    assert _cell(db, "A")[1] == {crud.CHAIN_SOURCE: "a"}, "a dry run changes nothing"
    counted = retroactive._count_fold_file_layers(db, {"table": TGT}, 100000)
    assert counted["affected"] == sum(dry[key] for key in ACTIONS)

    applied = replay.fold_file_layers(db, TGT, apply=True)
    assert {key: applied[key] for key in ACTIONS} == {key: dry[key] for key in ACTIONS}
    row = lambda r: crud.merged_layer_name(crud.CHAIN_SOURCE, r)              # noqa: E731
    assert {key: _cell(db, key) for key in "ABCDEFGH"} == {
        "A": ("a", {row("r1"): "a"}),
        "B": ("b2", {row("r1"): "b2"}),
        "C": ("c", {"f.csv": "F", row("r2"): "c"}),
        "D": ("Z", {row("r2"): "d", crud.CHAIN_SOURCE: "Z"}),
        "E": ("e", {crud.CHAIN_SOURCE: "e"}),
        "F": ("M", {crud.merged_layer_name(crud.CHAIN_SOURCE, "K9_abc123"): "M", "f.csv": "F1"}),
        "G": ("R", {crud.CHAIN_SOURCE: "P", row("r3"): "R"}),
        "H": ("R", {row("r3"): "R", "f.csv": "FH"}),
    }
    said = {(a.row_id, a.old_value, a.new_value) for a in db.query(models.AuditLog).filter(
        models.AuditLog.table_name == TGT, models.AuditLog.source_name == replay.R3_AUDIT_SOURCE)}
    assert {(old, new) for _row_id, old, new in said} == {("b", "b2"), ("F1", "M"), ("P", "R"), ("FH", "R")}

    again = replay.fold_file_layers(db, TGT, apply=True)
    assert {key: again[key] for key in ACTIONS} == dict.fromkeys(ACTIONS, 0)


def test_a_row_taken_back_after_the_fold_shows_what_is_left_beneath(db):
    """총괄 4dd303f01: C's plain layer said what r2's layer says - folded, taking r2 back shows the file's F."""
    _stacked(db)
    replay.fold_file_layers(db, TGT, apply=True)
    stats = cell_layer.withdraw_by_origin(db, ["r2"], apply=True, table=TGT)
    assert stats["cells_withdrawn"] == 2
    assert (_cell(db, "C"), _cell(db, "D")) == (("F", {"f.csv": "F"}), ("Z", {crud.CHAIN_SOURCE: "Z"}))
