# -*- coding: utf-8 -*-
"""총괄 e91b96a28 — a join's `on` names the table whose value changes.

> 소유자: 「on 이 dt_inventory 여야지 생각해봐」 · 「붙일 값을 고쳐야 트리거 시켜서 그걸 붙이지」

mapper and decide already read 「`on` changes -> derive -> write into `into`」; the join said
`on` = the table it writes and hid the source in `derive.join.right_table`. Now `on` is the
source, `right_table` is refused by name, and one declaration stands two rules: its own, on
the source, and a `:target` half on the table it writes (a row that lands later still gets
the value). Scored by ROWS through the real loader, the real worker group step and the real
convert door - not by the shape of a rule.
"""
import json
import logging
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import ingestion_worker as worker                          # noqa: E402
from chain import replay, rule_shape, synthesis                       # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from ledger import admin                                              # noqa: E402

# Names no live table_config carries - an import-time collision pins a real schema.
INV = "e91_inventory"
LOG = "e91_log"
TABLES = {
    INV: {"business_key": "dt_job", "composite_key_source": ["dt_job"],
          "column_types": {"dt_job": "string", "dt_lot": "string", "dt_slot": "string",
                           "note": "string"},
          "display_columns": ["dt_job", "dt_lot", "dt_slot", "note"]},
    LOG: {"business_key": "log_key", "composite_key_source": ["log_key"],
          "column_types": {"log_key": "string", "dt_job": "string", "dt_lot": "string",
                           "dt_slot": "string"},
          "display_columns": ["log_key", "dt_job", "dt_lot", "dt_slot"]},
}
NAME = "e91_confirmed"
JOIN = {"on": [{"left": "dt_job", "right": "dt_job"}], "take": ["dt_lot", "dt_slot"]}

#: What an operator writes today.
DECLARATION = {"name": NAME, "on": {"table": INV},
               "derive": {"kind": "join", "join": JOIN},
               "into": {"table": LOG}, "key": {"unique": True}}

#: What the box's `inventory_confirmed` said before this round - the table it writes in `on`.
OLD = {"name": NAME, "on": {"table": LOG},
       "derive": {"kind": "join", "join": dict(JOIN, right_table=INV)},
       "into": {"table": LOG}, "key": {"unique": True}}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch):
    """The ONE rules file - the loader, the convert door and replay all read it."""
    path = tmp_path / "chain_rules.json"
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for",
                        lambda p: str(tmp_path / "backup"))

    def write(*declarations):
        path.write_text(json.dumps({"rules": list(declarations)}), encoding="utf-8")
        return path
    return write


def _mine(rules):
    return [r for r in rules if str(r.get("name") or "").startswith(NAME)]


def _push(db, table, rows):
    """A write the way the grid's `PUT /tables/{t}/data/updates` makes it - collapsed, so the
    event names the columns it changed (that is what `trigger_columns` is matched against)."""
    import event_constants
    from database.context import outbox_mode

    with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(row), source_name="seed", updated_by="e91")
            for row in rows]))
    db.commit()


def _log(db):
    return {r.log_key: r.dt_lot for r in db.query(models.DYNAMIC_TABLES[LOG]).all()}


def _events_after(db, after):
    return (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > after)
            .order_by(models.DatabaseOutbox.id.asc()).all())


def _high(db):
    last = db.query(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id.desc()).first()
    return last.id if last else 0


def _drain(db, rules, after):
    """The worker's group step over every event staged after `after`, per transaction."""
    groups = {}
    for event in _events_after(db, after):
        groups.setdefault((event.payload or {}).get("transaction_id"), []).append(event)
    for tx, events in groups.items():
        worker._process_chain_transaction_group_sync(tx, events, db, rules)
    db.commit()


def _confirmed(db, rules):
    """INV J1 = A · LOG L1, L2 on J1 and L3 on J2, all drained - the state before the edit."""
    mark = _high(db)
    _push(db, INV, [{"dt_job": "J1", "dt_lot": "A", "dt_slot": "S1"}])
    _push(db, LOG, [{"log_key": "L1", "dt_job": "J1"}, {"log_key": "L2", "dt_job": "J1"},
                    {"log_key": "L3", "dt_job": "J2"}])
    _drain(db, rules, mark)


# ---------------------------------------------------------------------------
# ① the old shape is refused by name, and the sentence names both cells to fix
# ---------------------------------------------------------------------------

def test_an_old_shape_join_is_refused_by_name_with_both_cells_to_fix(rules_file, caplog):
    rules_file(OLD)
    with caplog.at_level(logging.ERROR):
        stood = _mine(worker.load_chain_rules())

    assert stood == [], "an old-shape join still stands"
    said = " ".join(record.getMessage() for record in caplog.records)
    assert NAME in said and 'on.table to "%s"' % INV in said and "delete right_table" in said, said


# ---------------------------------------------------------------------------
# ② the convert door, once
# ---------------------------------------------------------------------------

def test_the_convert_door_turns_it_into_the_new_shape_once(rules_file):
    path = rules_file(OLD)

    answer = admin.convert_chain_rule_grammar(
        NAME, "unified", dry_run=False, base=admin.file_fingerprint(str(path)))

    stored = json.loads(path.read_text(encoding="utf-8"))["rules"][0]
    assert answer["changed"] is True and answer["saved"] is True
    assert stored["on"] == {"table": INV}
    assert "right_table" not in stored["derive"]["join"]
    assert stored["into"] == {"table": LOG}
    assert [r["name"] for r in _mine(worker.load_chain_rules())] == [
        NAME, NAME + rule_shape.COMPANION_SUFFIX]

    again = admin.convert_chain_rule_grammar(
        NAME, "unified", dry_run=False, base=admin.file_fingerprint(str(path)))
    assert again["changed"] is False, "a second press changed an already-new declaration"


# ---------------------------------------------------------------------------
# ③ the owner's flow: fix the value on the source, the rows that point at it follow
# ---------------------------------------------------------------------------

def test_fixing_the_value_on_the_source_moves_every_row_that_points_at_it(db, rules_file):
    rules_file(DECLARATION)
    rules = worker.load_chain_rules()
    _confirmed(db, rules)
    assert _log(db) == {"L1": "A", "L2": "A", "L3": None}

    mark = _high(db)
    _push(db, INV, [{"dt_job": "J1", "dt_lot": "B"}])
    edits = [e for e in _events_after(db, mark) if e.table_name == INV]
    # CANARY: the edit names only the value it changed - so the rule wakes on `dt_lot`
    # itself, not on a key that happened to ride along.
    columns = set((edits[0].payload or {}).get("columns") or ()) if edits else set()
    assert "dt_lot" in columns and "dt_job" not in columns, columns
    _drain(db, rules, mark)

    assert _log(db) == {"L1": "B", "L2": "B", "L3": None}


# ---------------------------------------------------------------------------
# ④ the `:target` half: a row that lands after the source was confirmed still gets it
# ---------------------------------------------------------------------------

def test_a_row_that_lands_later_gets_the_value_through_the_target_half(db, rules_file):
    rules_file(DECLARATION)
    rules = worker.load_chain_rules()
    _confirmed(db, rules)
    target = [r for r in _mine(rules) if r["name"] == NAME + ":target"]
    assert target and target[0]["trigger_table"] == LOG, [r["name"] for r in _mine(rules)]

    mark = _high(db)
    _push(db, LOG, [{"log_key": "L4", "dt_job": "J1"}])
    _drain(db, rules, mark)

    assert _log(db)["L4"] == "A"


# ---------------------------------------------------------------------------
# ⑤ the engine and the approval did not move: the unique key is still the source's
# ---------------------------------------------------------------------------

def test_the_unique_key_is_still_asked_of_the_source_table(rules_file):
    rules_file(DECLARATION)
    wanted = {(table, tuple(columns))
              for name, table, columns, _folds, skip, _kind in
              synthesis.declared_unique_targets(worker.load_chain_rules())
              if str(name).startswith(NAME) and not skip}

    assert wanted == {(INV, ("dt_job",))}


# ---------------------------------------------------------------------------
# ⑦ what was edited while the old shape stood refused arrives after convert + replay
# ---------------------------------------------------------------------------

def test_an_edit_made_while_refused_arrives_after_convert_and_replay(db, rules_file):
    path = rules_file(DECLARATION)
    _confirmed(db, worker.load_chain_rules())
    path = rules_file(OLD)
    refused = worker.load_chain_rules()
    assert _mine(refused) == []

    mark = _high(db)
    _push(db, INV, [{"dt_job": "J1", "dt_lot": "C"}])
    _drain(db, refused, mark)
    assert _log(db) == {"L1": "A", "L2": "A", "L3": None}, "a refused join wrote"

    admin.convert_chain_rule_grammar(
        NAME, "unified", dry_run=False, base=admin.file_fingerprint(str(path)))
    rules = worker.load_chain_rules()
    mark = _high(db)
    replay.replay_rule(db, replay.find_rule(NAME, rules), apply=True, log=lambda m: None)
    _drain(db, rules, mark)

    assert _log(db) == {"L1": "C", "L2": "C", "L3": None}


# ---------------------------------------------------------------------------
# 총괄 6ef4ab1f2 — the rule view says which rule needs the new-shape conversion
# ---------------------------------------------------------------------------

def test_the_rule_view_says_an_old_join_needs_the_new_shape_and_nothing_else_does(rules_file):
    """The screen's convert offered only `to=flat` for a unified rule, which stands no
    `:target` half. The server says which rule needs `to=unified`, by the judgement the
    conversion itself runs - the screen does not guess from the cells."""
    mapper = {"name": "e91_mapper", "on": {"table": INV}, "into": {"table": LOG},
              "derive": {"kind": "mapper", "mapper": {"mapper": "x"}}}
    rules_file(OLD, dict(DECLARATION, name="e91_new"), mapper)

    said = {name: admin.chain_rule_raw_view(name)["join_needs_new_shape"]
            for name in (NAME, "e91_new", "e91_mapper")}

    assert said == {NAME: True, "e91_new": False, "e91_mapper": False}
