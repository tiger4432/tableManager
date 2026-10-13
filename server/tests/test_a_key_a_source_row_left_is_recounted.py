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
"""
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import anyio                                                          # noqa: E402
import pytest                                                         # noqa: E402

import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
from chain import cell_layer, enrichment                              # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import outbox_mode                              # noqa: E402
from tests.support.enrich_decl import enrich_chain_rules, write_rules  # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

SRC, INV = "okey_log", "okey_inv"
TABLES = {
    SRC: {"business_key": "log_id",
          "column_types": {"log_id": "string", "job": "string", "lot": "string", "t": "string"}},
    INV: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "lot": "string", "n": "number", "note": "string"}},
}
RULE = {"okey_rule": {
    "source_table": SRC, "derived_table": INV, "decision_key": ["job"], "target_fields": ["lot", "n"],
    "aggregations": {"lot": {"fn": "unique_concat", "column": "lot"}, "n": "count"}}}
#: a person's mapper on the same table, which does not declare the cell
PLAIN = {"name": "okey_plain", "enabled": True, "is_batch": True, "trigger_table": SRC, "target_table": INV,
         "mapper": "okey_recorder"}
HANDED = []


def _recorder(db, payloads, rule=None):
    HANDED.extend(payloads if isinstance(payloads, list) else [payloads])
    return {"updates": []}


@pytest.fixture(name="db")
def fixture_db(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    write_rules(tmp_path, monkeypatch, RULE)
    mapper_sdk.register("okey_recorder", _recorder)
    HANDED.clear()
    try:
        yield db_session
    finally:
        mapper_sdk.MAPPER_REGISTRY.pop("okey_recorder", None)
        mapper_sdk.MAPPER_PARAMS.pop("okey_recorder", None)


def _rules():
    return enrich_chain_rules(known_tables=crud.TABLE_CONFIG) + [PLAIN]


def _write(db, items, collapsed=False):
    batch = schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(source_name=crud.USER_SOURCE, updated_by="okey", **item) for item in items])
    if collapsed:
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            crud.apply_batch_updates(db, SRC, batch)
    else:
        crud.apply_batch_updates(db, SRC, batch)


def _chain(db):
    """Every waiting event on the source table, one group per transaction in id order - as the worker groups."""
    from database.models import DatabaseOutbox

    events = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == SRC, DatabaseOutbox.processed_chain == False  # noqa: E712
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
