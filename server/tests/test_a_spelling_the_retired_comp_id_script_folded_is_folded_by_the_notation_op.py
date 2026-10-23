# -*- coding: utf-8 -*-
"""소유자 10-12 「딸깍하면 되게」 → 10-23 은퇴: scripts/fold_comp_id.py folded one column's spellings with a hand-written
SQL of {"join": "-"}. The retroactive «Fold stored values into the declared spelling» does the same job - measured on
twin tables, one seed: the same shown values, layers and history lines. This keeps the spellings that script was for:
a run of whitespace . _ - (an ideographic space too) becomes one '-', case kept, a blank left blank, every layer
folded with the shown value and one history line per moved cell."""
import json
import os
import sys

import pytest
from sqlalchemy import MetaData, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                              # noqa: E402
import notation_norm as nn                                          # noqa: E402
from chain import replay                                            # noqa: E402
from conftest import PG_TEST_SCHEMA                                 # noqa: E402
from database import crud, models, schemas                          # noqa: E402

pytestmark = pytest.mark.pg

TABLE = "pgqa_comp_spelling"
DECL = {"business_key": "k", "column_types": {"k": "string", "comp_id": "string"}}
SEED = {"K1": "AB 12", "K2": "AB_12", "K3": "AB.12", "K4": "AB-12", "K5": "AB  _ .12", "K6": " AB 12 ",
        "K7": "ab 12", "K8": "AB--12", "K9": "AB　12", "K10": ""}
FOLDED = {"K1": "AB-12", "K2": "AB-12", "K3": "AB-12", "K4": "AB-12", "K5": "AB-12", "K6": "AB-12",
          "K7": "ab-12", "K8": "AB-12", "K9": "AB-12", "K10": None}


def _write(db, rows, source):
    from database.context import channel

    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"k": k, "comp_id": v}, source_name=source, updated_by="seed",
                                      business_key_val=k) for k, v in rows.items()], silent=True))
    db.commit()


def test_the_notation_op_folds_what_the_retired_script_folded(pg_engine, tmp_path, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from database import config_watcher
    from database.context import channel, retroactive_run

    rules = tmp_path / "notation_rules.json"
    rules.write_text(json.dumps({"columns": {}}), encoding="utf-8")
    monkeypatch.setattr(nn, "NOTATION_RULES_PATH", str(rules))
    config_watcher.forget_held()
    models.init_dynamic_models({TABLE: DECL})
    crud.TABLE_CONFIG[TABLE] = DECL
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    db = sessionmaker(bind=pg_engine)()
    try:
        _write(db, SEED, "f01.csv")
        _write(db, {"K1": "AB 12"}, "f02.csv")                                     # a second layer on one cell
        count = "SELECT count(*) FROM cell_sources WHERE table_name = :t AND column_name = 'comp_id'"
        seeded = db.execute(text(count), {"t": TABLE}).scalar()
        rules.write_text(json.dumps({"columns": {TABLE: {"comp_id": {"write": True, "rules": {"join": "-"}}}}}),
                         encoding="utf-8")
        config_watcher.forget_held()
        with channel(event_constants.CHANNEL_RETROACTIVE), retroactive_run("comp"):
            said = replay.fold_written_notation(db, TABLE, apply=True, log=lambda m: None)
        db.commit()
        shown = dict(db.execute(text('SELECT business_key_val, comp_id FROM "%s"' % TABLE)).fetchall())
        layers = db.execute(text("SELECT value #>> '{}' FROM cell_sources WHERE table_name = :t "
                                 "AND column_name = 'comp_id'"), {"t": TABLE}).scalars().all()
        moved = db.execute(text("SELECT count(*) FROM audit_logs WHERE table_name = :t AND column_name = 'comp_id' "
                                "AND updated_by <> 'seed'"), {"t": TABLE}).scalar()
        assert shown == FOLDED
        assert seeded and len(layers) == seeded and set(layers) == {"AB-12", "ab-12"}   # every layer, none lost
        assert said["cells_folded"] == moved == 8
    finally:
        db.close()
        with pg_engine.begin() as conn:
            for table in ("cell_sources", "audit_logs", "database_outbox"):
                conn.execute(text("DELETE FROM %s WHERE table_name = :t" % table), {"t": TABLE})
        scratch.drop_all(pg_engine)
        crud.TABLE_CONFIG.pop(TABLE, None)
        config_watcher.forget_held()
