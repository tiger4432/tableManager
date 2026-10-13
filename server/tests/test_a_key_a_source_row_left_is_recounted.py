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
TABLES = {
    WSRC: {"business_key": "log_id", "column_types": {"log_id": "string", "lot": "string", "slot": "string"}},
    WINV: {"business_key": "lot", "composite_key_source": ["lot"],
           "column_types": {"lot": "string", "slot": "string", "n": "number", "note": "string"}},
    SRC: {"business_key": "log_id",
          "column_types": {"log_id": "string", "job": "string", "lot": "string", "at": "string"}},
    INV: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "lot": "string", "n": "number", "note": "string"}},
}
RULE = {"okey_rule": {
    "source_table": SRC, "derived_table": INV, "decision_key": ["job"], "target_fields": ["lot", "n"],
    "aggregations": {"lot": {"fn": "unique_concat", "column": "lot"}, "n": "count"}},
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
    _write(db, [{"updates": {"log_id": "L1", "job": "J1", "lot": "A", "at": "1"}},
                {"updates": {"log_id": "L2", "job": "J1", "lot": "B", "at": "2"}},
                {"updates": {"log_id": "L3", "job": "J3", "lot": "C", "at": "3"}}])
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
        [{"log_id": "L3", "job": "J3", "lot": "C", "at": "3"}, {}]]
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
    _write(db, [{"row_id": _src(db, "L1").row_id, "updates": {"at": "9"}}])
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
        _src(db, "L1").at = "9"
        db.delete(_src(db, "L2"))
        db.commit()
    _chain(db)

    assert [p["row_id"] for p in HANDED] == [_src(db, "L1").row_id]
    assert _inv(db) == {"J1": ("A", 1), "J3": ("C", 1)}


def test_a_same_key_edit_carries_no_old_key_and_takes_nothing(db):
    _seed(db)
    _write(db, [{"row_id": _src(db, "L3").row_id, "updates": {"at": "4"}}], collapsed=True)
    events = _chain(db)

    assert [get_payload_dict(e).get(event_constants.OLD_VALUES_KEY) for e in events] == [[{"at": "3"}]]
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
    nn.reset_cache()
    _write(db, [{"updates": {"log_id": "L9", "job": "J . 9", "lot": "Z", "at": "9"}}])
    _chain(db)
    assert _inv(db) == {"J . 9": ("Z", 1)}
    rules.write_text(json.dumps({"columns": {SRC: {"job": {"write": True, "rules": {"replace": [[" *[.] *", "."]]}}}}}),
                     encoding="utf-8")
    nn.reset_cache()
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
    _write(db, [{"updates": {"log_id": "L1", "job": "J1", "lot": "A", "at": "1"}}], source="f01.csv")
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
    assert set(_inv(db)) == {"J1", "J3"}
    assert [r for r in caplog.records if "goes back to be retried" in r.getMessage()]
    monkeypatch.setattr(crud, "delete_rows_batch", real)
    _chain(db)

    assert set(_inv(db)) == {"J1"}


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
