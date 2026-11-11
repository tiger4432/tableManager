"""R3 (`replay.recompute_display_values`) after a formula is removed, run through its product door - the run record a
CLI and the scheduler's child both take (`retroactive.run_here` / `run_claimed` -> `_run_to_the_end`) - writes on the
retroactive channel: every moved row's event is staged and NONE wakes a rule, an opt-in one included (owner 09-26
«큰 소급으로 한 거 체인 연쇄 안 되게», chain_ingestion_guide §5.6). The same run with the channel taken off wakes the
opt-in rule - the control that the rule would wake, so the 0 is the channel's doing."""
from datetime import datetime, timezone

import pytest

import event_constants
from admin import retroactive
from chain import ingestion_worker as worker
from database import context, crud, models
from support import line_tables
from tests.test_retroactive_admin import _NoCloseSession

TABLE = "r3_retro_t"
TABLES = {TABLE: {"business_key": "k", "column_types": {"k": "string", "v": "string", "n": "string"}}}
ROWS = ("r1", "r2", "r3")
RULE = {"name": "r3_retro_optin", "trigger_table": TABLE, "target_table": "r3_retro_elsewhere",
        "mapper": "production_mapper", "allow_chain_trigger": True}
T0 = datetime(2026, 11, 1, 1, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db(db_session, monkeypatch):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    line_tables.build(db_session.get_bind(), TABLE)
    # the run opens its own sessions (`_run_to_the_end`, `_mark_run`) - on this one, or it writes elsewhere
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoCloseSession(db_session))
    monkeypatch.setattr(retroactive, "announce_progress", lambda *a, **k: None)
    yield db_session
    db_session.rollback()
    line_tables.drop(db_session.get_bind(), TABLE)
    from conftest import retire_dynamic_model
    retire_dynamic_model(TABLE)
    crud.TABLE_CONFIG.pop(TABLE, None)


def _world(db):
    """Each row: one file line says «k» and «v»; t shows it, and «n» = 9 with no line - the formula's old answer."""
    bits = line_tables.bits_of(TABLE)
    with db.get_bind().begin() as conn:
        for i, row_id in enumerate(ROWS):
            key = "K%d" % i
            said = line_tables.line(conn, TABLE, bits, row_id, source="f.csv", values={"k": key, "v": "A"},
                                    at=T0, business_key=key)
            line_tables.now(conn, TABLE, row_id, key, values={"k": key, "v": "A", "n": "9"},
                            won_by={"k": said, "v": said})
    db.expire_all()


@pytest.mark.parametrize("retroactive_channel, woken", [(True, ()), (False, (RULE["name"],))])
def test_r3_after_a_formula_removed_stages_its_rows_and_wakes_no_rule_on_the_retroactive_channel(
        db, monkeypatch, retroactive_channel, woken):
    _world(db)
    if not retroactive_channel:                  # the control: the run's channel seat says «no channel»
        real = context.channel
        monkeypatch.setattr(context, "channel", lambda value: real(None))
    before = db.query(models.DatabaseOutbox.id).count()

    out = retroactive.run_here("resolve", {"table": TABLE, "columns": "n", "formula_removed": "n"},
                               log=lambda *_: None)

    run = db.query(models.RetroactiveRun).filter(models.RetroactiveRun.op == "resolve").one()
    assert (run.state, out["stats"]["cells_changed"]) == (retroactive.RUN_DONE, len(ROWS)), \
        "canary: the run went through and moved every row's «n»"
    staged = [e for e in db.query(models.DatabaseOutbox).order_by(models.DatabaseOutbox.id).all()[before:]
              if e.table_name == TABLE]
    said = [(e.event_type, event_constants.channel_of(worker.get_payload_dict(e)),
             worker.get_payload_dict(e).get("source_name")) for e in staged]
    assert len(staged) == len(ROWS), said
    assert worker._rules_for_group(staged, [RULE]) == woken, said
