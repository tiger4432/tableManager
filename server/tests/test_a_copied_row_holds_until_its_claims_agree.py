# -*- coding: utf-8 -*-
"""총괄 3211e9000 — 보류 포함 행 복사, end to end on PostgreSQL.

Source rows copy into the same-key official row (`copy_rows_with_hold`, the owner's
`copy_one_row` plus params and a count); the hold says whether the key's source rows agree, and a
ledger source reading the official table with `read.exclude_when` on the hold says nothing about a
held row. Every seat is the product's: crud writes, the chain's transaction-group body,
`followup.drain_once`.

  one source row                     agreed, the ledger says its value
  two rows, different values         blank, the ledger's atom is withdrawn
  two rows, the same values          agreed
  every commit                       a row whose values changed carries the hold of that moment
  a row deleted · moved · gated out  the copy rule counts its key's hold again - one hold layer a key
                                     (lead 11-08 ㄱ: the recount rule, 총괄 e11bb4de0, retired)
  a person's edit of the official    the hold stays - no rule counts on the official table
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from database import crud, lines                                    # noqa: E402
from support import hold_world as hw                                # noqa: E402
from support import line_tables                                     # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402
from sqlalchemy import select                                       # noqa: E402

pytestmark = pytest.mark.pg


@pytest.fixture(name="world", params=[True, False], ids=["batch", "one_row"])
def fixture_world(request, pg_engine, monkeypatch, tmp_path):
    for world in hw.build(pg_engine, monkeypatch, tmp_path, batch=request.param):
        line_tables.build(pg_engine, hw.OFFICIAL)          # its shape for a planted line (line_tables.line)
        try:
            yield world
        finally:
            world["db"].rollback()                        # its open read would hold the drop's lock
            line_tables.drop(pg_engine, hw.OFFICIAL)


def test_one_source_row_is_agreed_and_said(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert hw.hold(world) == "agreed"
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 7.0)]


def test_two_different_rows_hold_it_and_its_atom_is_withdrawn(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert len(hw.said(world)) == 1
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert hw.hold(world) in (None, "")
    assert hw.said(world) == []


def test_two_rows_with_the_same_values_stay_agreed(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert hw.hold(world) == "agreed"
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 7.0)]


@pytest.mark.parametrize("batches", [1, 2], ids=["one_batch", "two_batches"])
def test_no_commit_shows_new_values_without_their_hold(world, batches):
    """「원장이 보류 칸 없이 값만 본 횟수 0」, measured on every commit: values and hold travel in
    one item list, so they land together whether the clashing rows come in one batch or two."""
    rows = [{"log_id": "A", **hw.KEY, "netdie": 7}, {"log_id": "B", **hw.KEY, "netdie": 9}]
    for chunk in ([rows] if batches == 1 else [rows[:1], rows[1:]]):
        hw.push(world, chunk)
        hw.settle(world)
    assert hw.hold(world) in (None, "")
    assert world["stale"] == []
    assert hw.said(world) == []
    # a blank hold on a row made in this batch is absence - no layer; on the row the first batch made, the copy's own
    assert _hold_layers(world) == ([] if batches == 1 else
                                   [crud.owned_layer_name("hc_copy", hw.official(world).business_key_val)])


def test_a_new_row_is_one_write_of_the_copy_with_its_hold(world):
    """Lead 11-08 ㄱ gate 3: B's values and its hold land in the copy's one write, and the ledger never reads 9
    with the old «agreed» (the recount, declared after the copy, showed its older count over the copy's)."""
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    before = len(hw.writes_by(world, hw.RULE["name"]))
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert len(hw.writes_by(world, hw.RULE["name"])) - before == 1
    assert (hw.official(world).netdie, hw.hold(world) or "") == (9, "")
    assert world["stale"] == []


def test_a_persons_edit_of_the_official_row_leaves_its_hold(world):
    """Lead 11-08 ㄱ gate 2: the hold counts the source rows' claims, so a person's edit of the official row moves
    no hold - measured the same on the code before (where the recount woke on it and wrote nothing)."""
    from database import schemas
    from database.context import channel

    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert hw.hold(world) == "agreed", "CANARY: one claim"
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(world["db"], hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            row_id=hw.official(world).row_id, updates={"netdie": 8}, source_name="user", updated_by="hold_test")]))
        world["db"].commit()
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world)) == (8, "agreed")


def _official_layers(world, column):
    """[(source, source row)] of the standing layers on the official rows' `column` (lines.layers)."""
    from sqlalchemy import text
    db = world["db"]
    ids = [r for (r,) in db.execute(text('SELECT row_id FROM "%s"' % hw.OFFICIAL))]
    return [(src, d["origin_row_id"]) for named in lines.layers(db, hw.OFFICIAL, ids, [column]).values()
            for src, d in named.items()]


def _hold_layers(world):
    """The layer names on the official row's hold cell."""
    return sorted(src for src, _origin in _official_layers(world, "hold"))


# ------------------------------------------- a deleted row: the copy counts its key again (lead 11-08 ㄱ)

def test_deleting_the_clashing_row_recounts_the_hold_to_agreed(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world) or "") == (9, "")
    hw.delete(world, "B")
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world)) == (7, "agreed")
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 7.0)]


def test_deleting_the_row_whose_value_is_hidden_recounts_the_hold_too(world):
    """Withdrawing a layer that was not the shown one changes no cell; the copy rule, handed the deleted row,
    counts its key's hold again in its own answer (lead 11-08 ㄱ - before, the delete path's EDIT woke the recount)."""
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world) or "") == (9, "")
    hw.delete(world, "A")
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world)) == (9, "agreed")
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 9.0)]
    assert _hold_layers(world) == [crud.owned_layer_name("hc_copy", hw.official(world).business_key_val)]


def test_a_deleted_row_that_fed_nothing_stages_no_event(world):
    from database import models
    from chain import ingestion_worker as worker
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    before = world["db"].query(models.DatabaseOutbox).count()
    worker._withdraw_what_those_rows_fed(world["db"], hw.LOG, ["01890000-0000-7000-8000-000000000000"], "deleted")
    world["db"].commit()
    assert world["db"].query(models.DatabaseOutbox).count() == before


def test_the_two_left_agreeing_are_agreed_by_the_copys_one_hold(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "C", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world) or "") == (9, "")
    hw.delete(world, "B")
    hw.settle(world)
    assert hw.hold(world) == "agreed"
    assert _hold_layers(world) == [crud.owned_layer_name("hc_copy", hw.official(world).business_key_val)]


# ------------------------------------------------------------------ one batch (32bab7896 · cb3d3c1bf)

def _netdie_layers(world):
    return sorted(_official_layers(world, "netdie"))


def _row_id(world, log_id):
    from sqlalchemy import text
    return world["db"].execute(text('SELECT row_id FROM "%s" WHERE log_id = :l' % hw.LOG),
                               {"l": log_id}).scalar()


def test_two_rows_of_one_key_in_one_batch_keep_a_layer_each(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}, {"log_id": "B", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    a, b = _row_id(world, "A"), _row_id(world, "B")
    assert _netdie_layers(world) == sorted([(crud.owned_layer_name("hc_copy", a), a), (crud.owned_layer_name("hc_copy", b), b)])
    hw.delete(world, "B")
    hw.settle(world)
    assert _netdie_layers(world) == [(crud.owned_layer_name("hc_copy", a), a)]


def test_a_key_whose_source_rows_are_all_deleted_goes_and_is_unsaid(world):
    """The copy counts the hold empty and the row is left with only the chain's keys - it goes (총괄
    5eee501eb · 판정 ㄱ: it was held blank and stayed, a shell)."""
    from database import models

    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "C", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert hw.hold(world) == "agreed" and len(hw.said(world)) == 1
    hw.delete(world, "A")
    hw.settle(world)
    hw.delete(world, "C")
    hw.settle(world)
    assert world["db"].query(models.DYNAMIC_TABLES[hw.OFFICIAL]).count() == 0
    assert hw.said(world) == []


def test_the_delete_paths_edit_names_what_lost_a_layer_and_wakes_only_opted_in_rules(world):
    """총괄 e11bb4de0 (나). A human layer carrying the deleted row's stamp is skipped, so its column
    is not named; the event rides the chain channel, so a rule that does not opt in stays asleep."""
    from chain import ingestion_worker as worker
    from database import models
    db = world["db"]
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    a, official_id = _row_id(world, "A"), hw.official(world).row_id
    named = sorted({c for _t, _r, c, _s, _o in lines.stamped_by(db, list(hw.TABLES), [a])})
    db.commit()
    with world["engine"].begin() as conn:               # a person's layer carrying A as its source row
        line_tables.line(conn, hw.OFFICIAL, line_tables.bits_of(hw.OFFICIAL), official_id, source="user",
                         values={"note": "x"}, input_row=a, written_by="t")
    # the row merged once, as the door's write would leave it - a line planted alone left t's note NULL, and the
    # withdrawal's re-merge told NULL -> 'x' as an EDIT of its own (lead 11-12)
    config = crud.TABLE_CONFIG[hw.OFFICIAL]
    said, now = lines.merge(db, hw.OFFICIAL, config, [official_id])[official_id], lines.current_table(
        db, hw.OFFICIAL, config, won_by=True)
    won = lines.won_by_of(db, hw.OFFICIAL, [official_id]).get(official_id, {})
    db.execute(now.update().where(now.c.row_id == official_id).values(
        **{c: value for c, (value, _line) in said.items()}, won_by=lines.won_by_stored(
            {**won, **{c: line for c, (_v, line) in said.items()}}, lines.bit_map(db, hw.OFFICIAL))))
    db.commit()
    assert db.execute(select(now.c.note).where(now.c.row_id == official_id)).scalar() == "x", "canary: merged"
    last = db.query(models.DatabaseOutbox.id).order_by(models.DatabaseOutbox.id.desc()).first()[0]
    worker._withdraw_what_those_rows_fed(db, hw.LOG, [a], "deleted")
    new = db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > last).all()
    assert "note" not in named and named
    assert [(e.event_type, e.table_name) for e in new] == [("EDIT", hw.OFFICIAL)]
    payload = get_payload_dict(new[0])
    assert (payload["row_ids"], payload["columns"]) == ([official_id], named)
    # the channel, not only the source name: the guard reading `chain_ingestion` as the chain retires
    assert event_constants.channel_of(payload) == event_constants.CHANNEL_CHAIN
    reader = {**hw.RULE, "name": "hc_reader", "trigger_table": hw.OFFICIAL, "target_table": hw.LOG,
              "allow_chain_trigger": True}                      # a rule on the official table that opts in
    assert worker.fire_refusal(reader, new[0]) is None
    asleep = {**reader, "allow_chain_trigger": False}
    assert worker.fire_refusal(asleep, new[0]) == worker.FIRE_REFUSED_CHAIN


# ----------------------------------------------------------------------------------- 총괄 0117a0048
# The copy rule's require is a row gate like its exclude: a row it holds back is no claim on the hold.
# 응용 measured: written after the rows were copied, replay took back what the empty rows fed but the
# recount still counted them - J1 stayed blank, J2 · J3 agreed with no value, and remove-shells found 0.

#: J1 has a row the require keeps and one it holds back; J2 · J3 only rows it holds back.
REQUIRED = [{"log_id": "A", "dt_job": "J1", "dt_x": 1, "dt_y": 2, "netdie": 7, "kind": "good"},
            {"log_id": "B", "dt_job": "J1", "dt_x": 1, "dt_y": 2, "netdie": 5},
            {"log_id": "C", "dt_job": "J2", "dt_x": 1, "dt_y": 2, "netdie": 3},
            {"log_id": "D", "dt_job": "J3", "dt_x": 1, "dt_y": 2, "netdie": 4}]


def _require_kind(world):
    """The copy rule now also requires `kind`, read the way the worker reads a saved rule."""
    import json

    from chain import ingestion_worker as worker

    with open(worker.RULES_PATH, encoding="utf-8") as fh:
        document = json.load(fh)
    for rule in document["rules"]:
        if rule["name"] == hw.RULE["name"]:
            rule["require"] = hw.KEYS + ["kind"]
    with open(worker.RULES_PATH, "w", encoding="utf-8") as fh:
        json.dump(document, fh)
    world["rules"][:] = [r for r in worker.load_chain_rules() if r.get("name") == hw.RULE["name"]]
    return {rule["name"]: rule for rule in world["rules"]}


def _by_job(world):
    from database import models

    world["db"].expire_all()
    return {row.dt_job: (None if row.netdie is None else float(row.netdie), row.hold or "")
            for row in world["db"].query(models.DYNAMIC_TABLES[hw.OFFICIAL]).all()}


def test_a_row_the_copys_require_holds_back_is_no_claim_and_the_copy_replay_takes_its_rows(world):
    """The owner's lines (총괄 ㄱ): replay the copy rule. Its answer holds J1 only, counted by its require, and
    what it no longer answers - J2 · J3, the key layers and the holds with them - is taken back, so those rows are
    gone; remove-shells finds nothing left (lead 11-08 ㄱ: no recount replay after it)."""
    from chain import replay

    hw.push(world, REQUIRED)
    hw.settle(world)
    assert {job: hold for job, (_value, hold) in _by_job(world).items()} == {
        "J1": "", "J2": "agreed", "J3": "agreed"}, "CANARY: before require, every row is a claim"
    rules = _require_kind(world)

    replay.replay_rule(world["db"], rules[hw.RULE["name"]], apply=True)
    hw.settle(world)

    assert _by_job(world) == {"J1": (7.0, "agreed")}, "J2 · J3 held only the chain's keys, and the chain took them"
    assert replay.remove_shell_rows(world["db"], hw.OFFICIAL)["rows_to_delete"] == 0


def test_a_recount_rule_still_declared_is_refused_by_name_at_load(world, caplog):
    """Lead 11-08 ㄱ: the recount rule retired - one still declared (the copy's mapper on its own target) would copy
    the official table onto itself, so the load refuses it by name and the copy stands."""
    import json

    from chain import ingestion_worker as worker

    with open(worker.RULES_PATH, encoding="utf-8") as fh:
        document = json.load(fh)
    document["rules"].append({"name": "hc_recount", "trigger_table": hw.OFFICIAL, "target_table": hw.OFFICIAL,
                              "mapper": "copy_rows_with_hold", "allow_chain_trigger": True,
                              "params": {**hw.RULE["params"], "source_table": hw.LOG}})   # as one was written
    with open(worker.RULES_PATH, "w", encoding="utf-8") as fh:
        json.dump(document, fh)
    caplog.set_level("ERROR", logger=worker.logger.name)

    names = [r.get("name") for r in worker.load_chain_rules()]

    assert "hc_recount" not in names and hw.RULE["name"] in names
    said = [r.getMessage() for r in caplog.records if "refused: recount_retired" in r.getMessage()]
    assert said == ["[ChainRules] hc_recount refused: recount_retired - the recount is retired - delete this rule; "
                    "its copy rule into %s counts the holds again (lead 11-08)" % hw.OFFICIAL], said
