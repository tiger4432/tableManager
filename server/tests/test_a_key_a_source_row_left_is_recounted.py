# -*- coding: utf-8 -*-
"""A decide recounts the key a source row LEFT - an edit moved it off, a deletion took it - and a key no source row
holds any more takes its derived row with it (lead 옛 키 ㄱ: 판정 435 ④ widened by one rule cell, not reversed).

The event carries the old values (an edit the columns it changed, a deletion every column); a rule that declares
`allow_delete_trigger` is woken by a deletion (the product's decide does, a person's mapper does not unless it says
so); the decide mapper adds the old key to its recount, and one with no source row left is handed back as `gone`;
the worker deletes that row through the grid's door after the write, naming a row a person wrote on.

  path              edit (per row) · edit (collapsed) · delete (grid door) · delete (ORM, per row)
  key left          one of two rows -> recounted · the only row -> its derived row goes
  person on it      the row goes and one line names it
  rule without cell a deletion is not handed to it
  same key          the event carries no old key; nothing goes
  copy (PG)         a deleted source row's layer is withdrawn and the hold recounted - without the cell

After the NO-GO (총괄 355ee9840): a decision key wider than the derived row's identity · another writer's layer ·
a decide with `require` · a notation fold and a layer withdrawal moving a key · a failed delete. Every cell runs on
SQLite and on PostgreSQL (`-m pg`).
"""
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json                                                           # noqa: E402

import anyio                                                          # noqa: E402
import pytest                                                         # noqa: E402

import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
from chain import cell_layer, enrichment                              # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import outbox_mode                              # noqa: E402
from tests.support.enrich_decl import as_declaration, enrich_chain_rules, write_rules  # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

SRC, INV = "okey_log", "okey_inv"
#: a decision key wider than the derived row's identity: (lot, slot) decides, lot names the row
WSRC, WINV = "okey_wlog", "okey_winv"
#: a decision key with a time part - its old value is ISO text, the recount's is the database's datetime
TSRC, TINV = "okey_tlog", "okey_tinv"
TABLES = {
    TSRC: {"business_key": "log_id", "column_types": {"log_id": "string", "lot": "string", "run_time": "datetime"}},
    TINV: {"business_key": "tkey", "composite_key_source": ["lot", "run_time"],
           "column_types": {"tkey": "string", "lot": "string", "run_time": "datetime", "n": "number",
                            "note": "string"}},
    WSRC: {"business_key": "log_id", "column_types": {"log_id": "string", "lot": "string", "slot": "string"}},
    WINV: {"business_key": "lot", "composite_key_source": ["lot"],
           "column_types": {"lot": "string", "slot": "string", "n": "number", "note": "string"}},
    SRC: {"business_key": "log_id",
          "column_types": {"log_id": "string", "job": "string", "lot": "string", "t": "string"}},
    INV: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "lot": "string", "n": "number", "note": "string"}},
}
RULE = {"okey_rule": {
    "source_table": SRC, "derived_table": INV, "decision_key": ["job"], "target_fields": ["lot", "n"],
    "aggregations": {"lot": {"fn": "unique_concat", "column": "lot"}, "n": "count"}},
    "okey_timed": {"source_table": TSRC, "derived_table": TINV, "decision_key": ["lot", "run_time"],
                   "target_fields": ["n"], "aggregations": {"n": "count"}},
    "okey_wide": {"source_table": WSRC, "derived_table": WINV, "decision_key": ["lot", "slot"], "target_fields": ["n"],
                  "aggregations": {"n": "count"}}}
#: a person's mapper on the same table, which does not declare the cell
PLAIN = {"name": "okey_plain", "enabled": True, "is_batch": True, "trigger_table": SRC, "target_table": INV,
         "mapper": "okey_recorder"}
HANDED = []


def _recorder(db, payloads, rule=None):
    HANDED.extend(payloads if isinstance(payloads, list) else [payloads])
    return {"updates": []}


@pytest.fixture(name="db", params=["sqlite", pytest.param("pg", marks=pytest.mark.pg)])
def fixture_db(request, tmp_path, monkeypatch):
    from sqlalchemy import MetaData, text

    # the session first - its fixture sets the table config, and ours goes on top
    session = request.getfixturevalue("pg_session" if request.param == "pg" else "db_session")
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    if request.param == "pg":
        from conftest import PG_TEST_SCHEMA
        scratch = MetaData(schema=PG_TEST_SCHEMA)
        for name in TABLES:
            models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
        scratch.drop_all(session.get_bind())
        scratch.create_all(session.get_bind())
    else:
        from database.database import Base
        Base.metadata.create_all(bind=session.get_bind())
    write_rules(tmp_path, monkeypatch, RULE)
    mapper_sdk.register("okey_recorder", _recorder)
    HANDED.clear()
    try:
        yield session
    finally:
        mapper_sdk.MAPPER_REGISTRY.pop("okey_recorder", None)
        mapper_sdk.MAPPER_PARAMS.pop("okey_recorder", None)
        if request.param == "pg":
            session.rollback()
            with session.get_bind().begin() as conn:
                for name in TABLES:
                    conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))


def _rules():
    return enrich_chain_rules(known_tables=crud.TABLE_CONFIG) + [PLAIN]


def _write(db, items, collapsed=False, table=SRC, source=crud.USER_SOURCE):
    batch = schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(source_name=source, updated_by="okey", **item) for item in items])
    if collapsed:
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            crud.apply_batch_updates(db, table, batch)
    else:
        crud.apply_batch_updates(db, table, batch)


def _chain(db, table=SRC):
    """Every waiting event on the source table, one group per transaction in id order - as the worker groups."""
    from database.models import DatabaseOutbox

    events = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == table, DatabaseOutbox.processed_chain == False  # noqa: E712
    ).order_by(DatabaseOutbox.id.asc()).all()
    groups = {}
    for event in events:
        groups.setdefault(get_payload_dict(event).get("transaction_id"), []).append(event)

    async def run():
        for tx, group in groups.items():
            ok, err, _messages = await worker.process_chain_transaction_group(tx, group, db, _rules())
            assert ok, err
            for event in group:
                event.processed_chain = True
            db.commit()

    anyio.run(run)
    return events


def _inv(db):
    db.expire_all()
    return {row.job: (row.lot, row.n) for row in db.query(models.DYNAMIC_TABLES[INV])}


def _src(db, log_id):
    return db.query(models.DYNAMIC_TABLES[SRC]).filter_by(business_key_val=log_id).one()


def _seed(db):
    _write(db, [{"updates": {"log_id": "L1", "job": "J1", "lot": "A", "t": "1"}},
                {"updates": {"log_id": "L2", "job": "J1", "lot": "B", "t": "2"}},
                {"updates": {"log_id": "L3", "job": "J3", "lot": "C", "t": "3"}}])
    _chain(db)
    assert _inv(db) == {"J1": ("A, B", 2), "J3": ("C", 1)}
    HANDED.clear()


def _gone_lines(caplog):
    return [r.getMessage() for r in caplog.records if "[ChainRetract]" in r.getMessage()
            and ("no source rows" in r.getMessage() or "no source row holds" in r.getMessage())]


def _deletions(db, table=INV):
    return [h.updated_by for h in db.query(models.AuditLog).filter_by(table_name=table, column_name="DELETE")]


@pytest.mark.parametrize("collapsed", [False, True], ids=["per row", "collapsed"])
def test_an_edit_that_moves_a_row_off_its_key_recounts_the_key_it_left(db, collapsed):
    _seed(db)
    _write(db, [{"row_id": _src(db, "L2").row_id, "updates": {"job": "J2"}}], collapsed=collapsed)
    events = _chain(db)

    assert [event_constants.old_values_of(get_payload_dict(e)) if not collapsed
            else get_payload_dict(e)[event_constants.OLD_VALUES_KEY] for e in events] == (
        [{"job": "J1"}] if not collapsed else [[{"job": "J1"}]]), "the edit carries the key it left, not more"
    assert _inv(db) == {"J1": ("A", 1), "J2": ("B", 1), "J3": ("C", 1)}


@pytest.mark.parametrize("collapsed", [False, True], ids=["per row", "collapsed"])
def test_an_edit_that_moves_the_only_row_off_its_key_takes_the_keys_row(db, collapsed, caplog):
    _seed(db)
    with caplog.at_level(logging.INFO):
        _write(db, [{"row_id": _src(db, "L3").row_id, "updates": {"job": "J4"}}], collapsed=collapsed)
        _chain(db)

    assert _inv(db) == {"J1": ("A, B", 2), "J4": ("C", 1)}
    assert _deletions(db) == [cell_layer.GONE_DELETER]
    assert _gone_lines(caplog) == ["[ChainRetract] table=%s rows_deleted=1 - no source row holds their key" % INV]


def test_a_deleted_row_of_two_recounts_its_key(db):
    _seed(db)
    crud.delete_rows_batch(db, SRC, [_src(db, "L1").row_id], "okey")
    _chain(db)

    assert _inv(db) == {"J1": ("B", 1), "J3": ("C", 1)}
    assert _deletions(db) == []


@pytest.mark.parametrize("door", ["grid", "orm"])
def test_a_deleted_only_row_takes_its_keys_row(db, door, caplog):
    _seed(db)
    with caplog.at_level(logging.INFO):
        if door == "grid":
            crud.delete_rows_batch(db, SRC, [_src(db, "L3").row_id], "okey")
        else:                       # the ORM's own delete - a per-row event whose data is the row as it was
            db.delete(_src(db, "L3"))
            db.commit()
        _chain(db)

    assert _inv(db) == {"J1": ("A, B", 2)}
    assert _deletions(db) == [cell_layer.GONE_DELETER]
    assert not [line for line in _gone_lines(caplog) if "a person's value" in line]


def test_the_map_purge_door_carries_the_rows_it_deletes_too(db):
    """The second deletion door (`crud.purge_map_rows`) - read first, staged with each row's values."""
    _seed(db)
    crud.purge_map_rows(db, models.DYNAMIC_TABLES[SRC], SRC, [_src(db, "L3").row_id, "no-such-row"])
    db.commit()
    events = _chain(db)

    assert [get_payload_dict(e)[event_constants.OLD_VALUES_KEY] for e in events] == [
        [{"log_id": "L3", "job": "J3", "lot": "C", "t": "3"}, {}]]
    assert _inv(db) == {"J1": ("A, B", 2)}


def test_a_keys_row_a_person_wrote_on_goes_and_is_named(db, caplog):
    _seed(db)
    crud.apply_batch_updates(db, INV, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val="J3", updates={"note": "checked"}, source_name=crud.USER_SOURCE, updated_by="okey")]))
    with caplog.at_level(logging.INFO):
        crud.delete_rows_batch(db, SRC, [_src(db, "L3").row_id], "okey")
        _chain(db)

    assert _inv(db) == {"J1": ("A, B", 2)}
    assert "[ChainRetract] deleted %s J3: no source rows (a person's value was on it)" % INV in _gone_lines(caplog)


def test_the_chains_deletion_is_a_chain_event_and_a_persons_is_not(db):
    """총괄: the deletion the chain makes is asked like its upserts, at the one seat (`_rule_accepts_event` by
    channel) - a rule on the derived table that takes deletions but not chain events is not woken by it, and is
    by a person's deletion there."""
    from database.context import channel

    watcher = {"name": "okey_inv_watch", "enabled": True, "is_batch": True, "trigger_table": INV,
               "target_table": INV, "mapper": "okey_recorder", "allow_delete_trigger": True}
    _seed(db)
    crud.delete_rows_batch(db, SRC, [_src(db, "L3").row_id], "okey")
    _chain(db)
    by_chain = db.query(models.DatabaseOutbox).filter_by(table_name=INV, event_type="DELETE").one()
    assert event_constants.channel_of(get_payload_dict(by_chain)) == event_constants.CHANNEL_CHAIN
    assert not worker.wakes(watcher, by_chain)
    assert worker.wakes(dict(watcher, allow_chain_trigger=True), by_chain), "control: the opt-in takes it"

    j1 = db.query(models.DYNAMIC_TABLES[INV]).filter_by(business_key_val="J1").one().row_id
    with channel(event_constants.CHANNEL_API):
        crud.delete_rows_batch(db, INV, [j1], "okey")
    by_person = [e for e in db.query(models.DatabaseOutbox).filter_by(table_name=INV, event_type="DELETE")
                 if e.id != by_chain.id]
    assert len(by_person) == 1 and worker.wakes(watcher, by_person[0])


def test_a_rule_without_the_cell_is_not_handed_a_deletion(db):
    _seed(db)
    _write(db, [{"row_id": _src(db, "L1").row_id, "updates": {"t": "9"}}])
    _chain(db)
    assert len(HANDED) == 1, "control: the plain rule is handed an edit"
    crud.delete_rows_batch(db, SRC, [_src(db, "L2").row_id], "okey")
    _chain(db)

    assert len(HANDED) == 1
    assert _inv(db) == {"J1": ("A", 1), "J3": ("C", 1)}, "the decide on the same table took the deletion"


def test_a_group_with_an_edit_and_a_deletion_hands_the_plain_rule_only_the_edit(db):
    """The plain rule wakes on the group's edit; the group's deletion is the decide's alone."""
    _seed(db)
    with crud.transaction_context("okey", "tx-mixed", crud.USER_SOURCE):
        _src(db, "L1").t = "9"
        db.delete(_src(db, "L2"))
        db.commit()
    _chain(db)

    assert [p["row_id"] for p in HANDED] == [_src(db, "L1").row_id]
    assert _inv(db) == {"J1": ("A", 1), "J3": ("C", 1)}


def test_a_same_key_edit_carries_no_old_key_and_takes_nothing(db):
    _seed(db)
    _write(db, [{"row_id": _src(db, "L3").row_id, "updates": {"t": "4"}}], collapsed=True)
    events = _chain(db)

    assert [get_payload_dict(e).get(event_constants.OLD_VALUES_KEY) for e in events] == [[{"t": "3"}]]
    assert _inv(db) == {"J1": ("A, B", 2), "J3": ("C", 1)}
    assert _deletions(db) == []


# ------------------------------------------------------------------ after the NO-GO (총괄 355ee9840)

def _wide(db):
    db.expire_all()
    return {row.lot: row.note for row in db.query(models.DYNAMIC_TABLES[WINV])}


def _wrow(db, log_id):
    return db.query(models.DYNAMIC_TABLES[WSRC]).filter_by(business_key_val=log_id).one().row_id


def _wseed(db, rows):
    _write(db, [{"updates": dict(zip(("log_id", "lot", "slot"), row))} for row in rows], table=WSRC)
    _chain(db, WSRC)
    _write(db, [{"business_key_val": "L1", "updates": {"note": "checked"}}], table=WINV)
    assert _wide(db) == {"L1": "checked"}


def test_a_wider_decision_key_keeps_the_row_its_identity_still_has(db):
    """1: (L1, 3)'s last row goes while (L1, 4) still has one - the row L1, a person's value on it, stays."""
    _wseed(db, [("W1", "L1", "3"), ("W2", "L1", "4")])
    crud.delete_rows_batch(db, WSRC, [_wrow(db, "W1")], "okey")
    _chain(db, WSRC)

    assert _wide(db) == {"L1": "checked"}


def test_a_wider_decision_key_keeps_the_row_when_the_same_batch_moves_its_row_within_it(db):
    """1, the same batch: the only row moves from (L1, 3) to (L1, 4) - the key it left has no row, its identity has."""
    _wseed(db, [("W1", "L1", "3")])
    _write(db, [{"row_id": _wrow(db, "W1"), "updates": {"slot": "4"}}], table=WSRC, collapsed=True)
    _chain(db, WSRC)

    assert _wide(db) == {"L1": "checked"}


def test_a_wider_decision_key_takes_the_row_when_no_source_row_has_its_identity(db):
    _wseed(db, [("W1", "L1", "3"), ("W2", "L1", "4")])
    crud.delete_rows_batch(db, WSRC, [_wrow(db, "W1"), _wrow(db, "W2")], "okey")
    _chain(db, WSRC)

    assert _wide(db) == {}


def test_a_keys_row_another_writer_is_on_stays_and_is_named(db, caplog):
    """2: a file's layer on the row - the row stays, named; the decide's own and a person's layers do not keep it."""
    _seed(db)
    _write(db, [{"business_key_val": "J3", "updates": {"note": "from the file"}}], table=INV, source="inventory.csv")
    with caplog.at_level(logging.INFO):
        crud.delete_rows_batch(db, SRC, [_src(db, "L3").row_id], "okey")
        _chain(db)

    assert set(_inv(db)) == {"J1", "J3"}
    assert ["[ChainRetract] kept %s J3: no source rows, but inventory.csv wrote on it" % INV] == [
        r.getMessage() for r in caplog.records if "[ChainRetract] kept" in r.getMessage()]


def test_a_decide_that_requires_a_column_still_takes_a_deletion(db):
    """3: `on.require` judges a deletion on the row as it was - it has no data."""
    import pathlib

    declarations = [as_declaration(name, cells) for name, cells in RULE.items()]
    declarations[0]["on"]["require"] = ["lot"]
    pathlib.Path(worker.RULES_PATH).write_text(json.dumps({"rules": declarations}), encoding="utf-8")
    assert [r.get("require") for r in _rules() if r["name"] == enrichment.config.synthesized_rule_names(
        "okey_rule")[0]] == [["lot"]], "control: the dedup rule carries the gate"
    _seed(db)
    crud.delete_rows_batch(db, SRC, [_src(db, "L3").row_id], "okey")
    _chain(db)

    assert _inv(db) == {"J1": ("A, B", 2)}


def test_a_notation_fold_that_moves_a_key_recounts_the_key_it_left(db, tmp_path, monkeypatch):
    """4: the notation fold writes outside the flush hook on PostgreSQL (`replay._write_by_values`) - its event
    carries what the cell was."""
    import notation_norm as nn
    from chain import replay

    rules = tmp_path / "notation_rules.json"
    monkeypatch.setattr(nn, "NOTATION_RULES_PATH", str(rules))
    rules.write_text(json.dumps({"columns": {}}), encoding="utf-8")
    from database import config_watcher
    config_watcher.forget_held()
    _write(db, [{"updates": {"log_id": "L9", "job": "J . 9", "lot": "Z", "t": "9"}}])
    _chain(db)
    assert _inv(db) == {"J . 9": ("Z", 1)}
    rules.write_text(json.dumps({"columns": {SRC: {"job": {"write": True, "rules": {"replace": [[" *[.] *", "."]]}}}}}),
                     encoding="utf-8")
    from database import config_watcher
    config_watcher.forget_held()
    replay.fold_written_notation(db, SRC, apply=True, log=lambda message: None)
    _chain(db)

    assert _inv(db) == {"J.9": ("Z", 1)}


def test_a_layer_withdrawal_that_moves_a_key_recounts_the_key_it_left(db):
    """4: a withdrawal that changes a shown key stages its edit through the flush hook, old value and all; the told
    EDIT beside it is for a row whose shown value did not move. A withdrawal is the chain's - a decide hears it with
    `allow_chain_trigger`."""
    import pathlib

    declarations = [as_declaration(name, cells) for name, cells in RULE.items()]
    declarations[0]["allow_chain_trigger"] = True
    pathlib.Path(worker.RULES_PATH).write_text(json.dumps({"rules": declarations}), encoding="utf-8")
    _write(db, [{"updates": {"log_id": "L1", "job": "J1", "lot": "A", "t": "1"}}], source="f01.csv")
    row_id = _src(db, "L1").row_id
    _write(db, [{"row_id": row_id, "updates": {"job": "J9"}}], source=crud.CHAIN_SOURCE)
    _chain(db)
    assert set(_inv(db)) == {"J9"}, "control: the chain's layer is shown over the file's"
    layers = cell_layer.cells_written_by(db, SRC, [(row_id, "job")], ("okey",))
    assert layers, "control: the layer to take back"
    worker._withdraw_and_tell(db, SRC, [row_id], "blank", declarations=("okey",), layers=layers)
    _chain(db)

    assert set(_inv(db)) == {"J1"}


def test_a_failed_delete_fails_the_group_and_its_retry_deletes(db, monkeypatch, caplog):
    """5: the delete is part of the group - it fails, the group is not stamped done, and the retry deletes."""
    from database.models import DatabaseOutbox

    _seed(db)
    crud.delete_rows_batch(db, SRC, [_src(db, "L3").row_id], "okey")
    real = crud.delete_rows_batch

    def refused(session, table, row_ids, who):
        if table == INV:
            raise RuntimeError("the derived table refused the delete")
        return real(session, table, row_ids, who)

    monkeypatch.setattr(crud, "delete_rows_batch", refused)
    events = db.query(DatabaseOutbox).filter(DatabaseOutbox.table_name == SRC,
                                             DatabaseOutbox.processed_chain == False).all()  # noqa: E712
    said = []

    async def run():
        said.append(await worker.process_chain_transaction_group(
            get_payload_dict(events[0]).get("transaction_id"), events, db, _rules()))

    with caplog.at_level(logging.ERROR):
        anyio.run(run)
    assert said[0][0] is False
    db.rollback()                       # as its caller does (`process_pending_groups`) - the group is one commit
    assert set(_inv(db)) == {"J1", "J3"}
    assert [r for r in caplog.records if "then FAILED" in r.getMessage()]
    monkeypatch.setattr(crud, "delete_rows_batch", real)
    _chain(db)

    assert set(_inv(db)) == {"J1"}


def test_a_time_in_the_decision_key_keeps_the_row_another_source_row_still_holds(db):
    """총괄 10-14 GO-WITH-FIXES 1: the key a deleted row left (its time as ISO text) and the key the recount gives
    back (the database's datetime) are one spelling (`crud.key_part`) - the row its sibling still holds stays."""
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("a datetime column on SQLite takes no ISO text - the product's time keys are PostgreSQL's")
    _write(db, [{"updates": {"log_id": "A", "lot": "L1", "run_time": "2026-10-01T09:00:00+00:00"}},
                {"updates": {"log_id": "B", "lot": "L1", "run_time": "2026-10-01T09:00:00+00:00"}}], table=TSRC)
    _chain(db, TSRC)
    _write(db, [{"business_key_val": db.query(models.DYNAMIC_TABLES[TINV]).one().business_key_val,
                 "updates": {"note": "checked"}}], table=TINV)
    a = db.query(models.DYNAMIC_TABLES[TSRC]).filter_by(business_key_val="A").one().row_id
    crud.delete_rows_batch(db, TSRC, [a], "okey")
    _chain(db, TSRC)

    db.expire_all()
    assert [(row.n, row.note) for row in db.query(models.DYNAMIC_TABLES[TINV])] == [(1, "checked")]


def test_a_keys_row_under_a_merged_layer_name_of_its_own_rule_still_goes(db):
    """총괄 10-14 GO-WITH-FIXES 4: a merge renames the rule's layer «chain_ingestion (<key>)» - still the rule's."""
    from sqlalchemy import update

    _seed(db)
    j3 = db.query(models.DYNAMIC_TABLES[INV]).filter_by(business_key_val="J3").one().row_id
    db.execute(update(models.CellSource).where(models.CellSource.table_name == INV, models.CellSource.row_id == j3,
                                               models.CellSource.source_name == crud.CHAIN_SOURCE)
               .values(source_name=crud.merged_layer_name(crud.CHAIN_SOURCE, "J3_1")))
    db.commit()
    crud.delete_rows_batch(db, SRC, [_src(db, "L3").row_id], "okey")
    _chain(db)

    assert set(_inv(db)) == {"J1"}


@pytest.mark.pg
def test_the_withdrawal_fold_carries_each_rows_old_values(db):
    """총괄 10-14 GO-WITH-FIXES 3: per-row withdrawal events folded into collapsed ones keep what each row was."""
    from database import database
    from database.models import DatabaseOutbox

    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("the fold reads the payload with PostgreSQL's JSON operators")
    _seed(db)
    db.query(DatabaseOutbox).delete()
    db.commit()
    with crud.transaction_context(cell_layer.R2_AUDIT_SOURCE, "okey-fold", cell_layer.R1_SOURCE_NAME):
        for log_id, was in (("L1", {"job": "J0"}), ("L3", {})):
            db.add(DatabaseOutbox(**database.row_event("EDIT", SRC, _src(db, log_id), old=was)))
        db.commit()
    cell_layer.fold_withdrawal_events(db, apply=True, log=lambda message: None)
    folded = db.query(DatabaseOutbox).filter(DatabaseOutbox.table_name == SRC).all()

    was = {}
    for event in folded:       # a page folds its own events (총괄 2ea5ee2a7 ③) - one or several
        payload = get_payload_dict(event)
        was.update(zip(payload["row_ids"], payload.get(event_constants.OLD_VALUES_KEY) or [{}] * payload["row_count"]))
    assert was == {_src(db, "L1").row_id: {"job": "J0"}, _src(db, "L3").row_id: {}}


@pytest.mark.pg
def test_the_copy_takes_a_deletion_back_without_the_cell(pg_engine, monkeypatch, tmp_path):
    """총괄: the copy is left without the cell - its deleted source row's layer is withdrawn where the chain ends the
    deletion, and that withdrawal's EDIT wakes the hold's recount."""
    from tests.support import hold_world as hw

    for world in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        assert not [r["name"] for r in world["rules"] if r.get(worker.chain_bindings.ALLOW_DELETE_TRIGGER_KEY)]
        hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
        hw.settle(world)
        hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
        hw.settle(world)
        assert (hw.official(world).netdie, hw.hold(world) or "") == (9, "")
        hw.delete(world, "B")
        deletion = world["db"].query(models.DatabaseOutbox).filter_by(table_name=hw.LOG, event_type="DELETE").one()
        assert not [r["name"] for r in world["rules"] if worker.wakes(r, deletion)]
        hw.settle(world)
        assert (hw.official(world).netdie, hw.hold(world)) == (7, "agreed")


# 총괄 63c747046 - the rows a decide counts are the rows its rule takes (`rule_run.gate_misses` / `gate_conditions`):
#   gate      require (the column filled) · exclude (the column blank)
#   rows      a row outside the gate is not counted · an edit that takes a row out leaves its key's count, and the
#             key's only row takes the key's row · a row that was never in is not handed
GATED = {"require": ({"L1": "1", "L2": "", "L3": "3"}, "1", ""),    # (t per seeded row, a t inside, a t outside)
         "exclude": ({"L1": "", "L2": "2", "L3": ""}, "", "x")}


def _gate(db, gate, t):
    """okey_rule with `on.<gate>: [t]`, and three rows whose t is `t` {log_id: t}."""
    import pathlib

    declarations = [as_declaration(name, cells) for name, cells in RULE.items()]
    declarations[0]["on"][gate] = ["t"]
    pathlib.Path(worker.RULES_PATH).write_text(json.dumps({"rules": declarations}), encoding="utf-8")
    assert [r.get(gate) for r in _rules() if r["name"] == enrichment.config.synthesized_rule_names(
        "okey_rule")[0]] == [["t"]], "control: the dedup rule carries the gate"
    _write(db, [{"updates": {"log_id": "L1", "job": "J1", "lot": "A", "t": t["L1"]}},
                {"updates": {"log_id": "L2", "job": "J1", "lot": "B", "t": t["L2"]}},
                {"updates": {"log_id": "L3", "job": "J3", "lot": "C", "t": t["L3"]}}])
    _chain(db)


@pytest.mark.parametrize("gate", sorted(GATED))
def test_a_row_outside_the_decides_gate_is_not_counted(db, gate):
    _gate(db, gate, GATED[gate][0])

    assert _inv(db) == {"J1": ("A", 1), "J3": ("C", 1)}, "L2 is outside the gate - not in J1's lot or count"


@pytest.mark.parametrize("gate", sorted(GATED))
def test_an_edit_that_takes_a_row_out_of_the_gate_leaves_its_keys_count(db, gate, caplog):
    inside, outside = GATED[gate][1:]
    _gate(db, gate, {"L1": inside, "L2": inside, "L3": inside})
    assert _inv(db) == {"J1": ("A, B", 2), "J3": ("C", 1)}, "control: every row inside"
    with caplog.at_level(logging.INFO):
        _write(db, [{"row_id": _src(db, "L2").row_id, "updates": {"t": outside}},
                    {"row_id": _src(db, "L3").row_id, "updates": {"t": outside}}])
        _chain(db)

    assert _inv(db) == {"J1": ("A", 1)}, "J1 counts without L2 - J3's only row left, so J3's row goes"
    assert any("2 of them handed as rows that left" in r.getMessage() for r in caplog.records)


def test_a_row_that_was_never_inside_is_not_handed_and_one_that_left_is_handed_as_it_was():
    from chain import rule_run

    rule = {"name": "r", "require": ["t"], "allow_delete_trigger": True}
    never = {"row_id": 1, "data": {"t": {"value": ""}, "job": {"value": "J1"}}, "old": {"job": "J0"}}
    left = {"row_id": 2, "data": {"t": {"value": ""}, "job": {"value": "J1"}}, "old": {"t": "1"}}
    inside = {"row_id": 3, "data": {"t": {"value": "2"}, "job": {"value": "J1"}}}

    handed, missed = rule_run.held_back(rule, [never, left, inside])
    assert handed == [{"row_id": 2, "data": {}, "old": {"t": "1", "job": "J1"}}, inside]
    assert missed == {"t": 2}
    assert rule_run.held_back({**rule, "allow_delete_trigger": False}, [never, left, inside])[0] == [inside], \
        "a rule that does not read rows that left is not handed them"


# ------------------------------------------------------------------------------ a deletion set aside, run again

def _dies_before_its_mark(db, monkeypatch):
    real = worker.mark_processed

    def dies(event, status):
        raise RuntimeError("killed before the mark")
    monkeypatch.setattr(worker, "mark_processed", dies)
    with pytest.raises(RuntimeError, match="killed before the mark"):
        _chain(db)
    monkeypatch.setattr(worker, "mark_processed", real)
    db.rollback()


def _set_aside_what_waits(db):
    from chain import set_aside
    from database.models import DatabaseOutbox

    waiting = db.query(DatabaseOutbox).filter(DatabaseOutbox.table_name == SRC,
                                              DatabaseOutbox.processed_chain == False).all()  # noqa: E712
    set_aside.set_aside(db, ids=[e.id for e in waiting], apply=True)
    return waiting


def test_a_deletion_set_aside_comes_back_as_the_deletion_it_was_and_recounts(db, monkeypatch):
    """총괄 g26: the group that took the deletion dies before its mark - one commit, all undone - and the deletion is
    set aside. A decide keeps no lineage, so the set-aside's withdrawal does not reach its row; rerun_set_aside puts
    the deletion back as it was, with its old values, and the decide recounts as it does a live one."""
    from admin import retroactive

    _seed(db)
    crud.delete_rows_batch(db, SRC, [_src(db, "L3").row_id], "okey")
    _dies_before_its_mark(db, monkeypatch)
    _set_aside_what_waits(db)
    assert set(_inv(db)) == {"J1", "J3"}, "no lineage: the set-aside withdrew nothing of it"

    said = []
    out = retroactive._run_rerun_set_aside(db, {"tables": [SRC]}, said.append)
    assert out["deletions_staged"] >= 1 and said == [], (out, said)
    _chain(db)
    assert set(_inv(db)) == {"J1"}, "the key the deleted row left is recounted - its row goes"


@pytest.mark.parametrize("collapsed", [False, True], ids=["per row", "collapsed"])
def test_an_edit_set_aside_comes_back_with_the_key_it_left_and_recounts_it(db, monkeypatch, collapsed):
    """총괄 g31: an edit that moved the only row off its key dies before its mark and is set aside - the key it
    left is still counted. rerun_set_aside puts the edit back with its old values, and the key it left goes."""
    from admin import retroactive

    _seed(db)
    _write(db, [{"row_id": _src(db, "L3").row_id, "updates": {"job": "J4"}}], collapsed=collapsed)
    _dies_before_its_mark(db, monkeypatch)
    _set_aside_what_waits(db)
    assert set(_inv(db)) == {"J1", "J3"}, "no lineage: the set-aside withdrew nothing of it"

    said = []
    out = retroactive._run_rerun_set_aside(db, {"tables": [SRC]}, said.append)
    assert out["edits_staged"] >= 1 and said == [], (out, said)
    _chain(db)
    assert _inv(db) == {"J1": ("A, B", 2), "J4": ("C", 1)}, "the key the edit left is recounted - its row goes"


def test_a_deletion_set_aside_without_its_old_values_is_said_not_replayed(db, monkeypatch):
    """총괄 g26: one set aside before its old values were kept cannot be put back - one line says which rows."""
    from admin import retroactive
    from database.models import DatabaseOutbox

    _seed(db)
    gone = _src(db, "L3").row_id
    crud.delete_rows_batch(db, SRC, [gone], "okey")
    for event in db.query(DatabaseOutbox).filter(DatabaseOutbox.table_name == SRC,
                                                 DatabaseOutbox.processed_chain == False):  # noqa: E712
        event.payload = {k: v for k, v in get_payload_dict(event).items() if k != event_constants.OLD_VALUES_KEY}
    db.commit()
    _set_aside_what_waits(db)

    said = []
    out = retroactive._run_rerun_set_aside(db, {"tables": [SRC]}, said.append)
    assert out["deletions_staged"] == 0
    assert said == ["[rerun_set_aside] %s: old values not kept - this deletion cannot be replayed; rows: %s"
                    % (SRC, gone)]
