"""A whole replay's sweep (`replay._gone_maps`) finds the maps its rule's layers sit on in the rule's own chain lines
(t__lines, `cell_layer._claimed_filter`) - the chain's name or its per-source-row name, written by the rule's
declaration. A line whose columns are all withdrawn owns nothing: the rule took that map back already.
A table that keeps no lines (`lines.has_lines` - sys_* tables, lead 11-11 ㄱ) has nothing to sweep, says so in one
line, and the sweep goes on to its other tables; a withdrawal's count, preview and run refuse it with one reason
(`cell_layer.refuse_without_lines`, lead 11-11 ㄴ). sqlite."""
import json
import logging

import pytest
from sqlalchemy import text

from chain import cell_layer, replay
from database import crud, lines, models
from database.database import Base
from database.write_lines import write_lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE, BARE = "gm_lines", "gm_bare"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "job": "string", "a": "string"}}
RULE = {"name": "r", "allow_retraction": True, "target_table": TABLE, "trigger_table": "gm_src",
        "trigger_job_column": "job", "target_job_column": "job", "is_batch": True}
BARE_RULE = dict(RULE, name="r0", target_table=BARE)


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    models.init_dynamic_models({TABLE: CFG, BARE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    monkeypatch.setitem(crud.TABLE_CONFIG, BARE, CFG)
    monkeypatch.setattr(replay, "_WHOLE", {})
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, TABLE, CFG)
    db_session.execute(text('INSERT INTO "%s" (row_id, business_key_val, k, job) VALUES (\'b1\', \'B1\', \'B1\', '
                            '\'JB\')' % BARE))
    db_session.commit()
    assert lines.has_lines(db_session, TABLE) and not lines.has_lines(db_session, BARE), "canary: one of each"
    ticking_clock(monkeypatch)
    return db_session


def _write(db, key, source, by, **values):
    return write_lines(db, TABLE, [{"key": {"k": key}, "values": {"k": key, **values}, "source_name": source,
                                    "written_by": by, "input_row": "o-" + key}],
                       kind="chain", transaction_id="tx-" + key)["items"][0]["row_id"]


def test_the_rules_chain_lines_name_its_maps_and_a_withdrawn_line_names_none(db):
    _write(db, "K1", crud.CHAIN_SOURCE, "r", job="J1", a="x")
    _write(db, "K2", crud.merged_layer_name(crud.CHAIN_SOURCE, "o2"), "r", job="J2", a="x")   # per source row
    _write(db, "K3", crud.CHAIN_SOURCE, "other", job="J3", a="x")                             # another rule
    _write(db, "K4", "f.csv", "r", job="J4", a="x")                                           # not the chain
    _write(db, "K5", "f.csv", "loader", job="J5")                      # keeps the row once the chain withdraws
    row5 = _write(db, "K5", crud.CHAIN_SOURCE, "r", a="x")
    db.commit()
    assert replay._gone_maps(db, RULE, "run-1") == (["job"], [("J1",), ("J2",), ("J5",)])

    write_lines(db, TABLE, [{"row_id": row5, "line_kind": "withdraw", "columns": ["k", "a"],
                             "source_name": crud.CHAIN_SOURCE, "written_by": "r"}],
                kind="withdraw", transaction_id="tx-w5")
    db.commit()
    assert db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(row_id=row5).one().job == "J5", \
        "canary: the row and its map stay - only the rule's claim on it is withdrawn"
    assert replay._gone_maps(db, RULE, "run-1") == (["job"], [("J1",), ("J2",)])


def test_a_table_without_lines_has_nothing_to_sweep_and_says_so(db, caplog, monkeypatch):
    """Declared and its line table not built: the sweep cannot tell (lead 11-11). Shipped (keeps no lines): nothing."""
    import shipped

    assert replay._gone_maps(db, BARE_RULE, "run-1") == (None, "gm_bare: line table not built - the sweep cannot tell")
    monkeypatch.setattr(shipped, "tables", lambda: {BARE: CFG})
    with caplog.at_level(logging.INFO, logger=replay.logger.name):
        assert replay._gone_maps(db, BARE_RULE, "run-1") == (["job"], [])
    assert [r.getMessage() for r in caplog.records if "no lines table" in r.getMessage()] == ["[ReplaySweep] gm_bare: no lines table - nothing to sweep"]


REASON = "gm_bare: has no line table - nothing written to it can be withdrawn here"


def test_a_table_without_lines_gets_one_reason_from_the_count_the_preview_and_the_run(db, client):
    """The preview is the screen's route - its 400 detail is what the operator reads."""
    said = {}
    with pytest.raises(cell_layer.ReplayRefused) as count:
        replay.count_withdrawable(db, BARE, "f.csv")
    said["count"] = str(count.value)
    preview = client.get("/admin/retroactive/withdraw/count", params={"table": BARE, "source": "f.csv"})
    assert preview.status_code == 400, preview.text
    said["preview"] = preview.json()["detail"]
    for apply in (False, True):
        with pytest.raises(cell_layer.ReplayRefused) as run:
            cell_layer.withdraw_source(db, BARE, "f.csv", apply=apply, log=lambda m: None)
        said["run" if apply else "dry run"] = str(run.value)
    assert said == dict.fromkeys(("count", "preview", "dry run", "run"), REASON)
    assert db.query(models.DYNAMIC_TABLES[BARE]).count() == 1, "the run left the table's row alone"


class _Kept:
    """The test's session, not closed by the judge that borrows it."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


def test_a_table_without_lines_does_not_stop_the_sweep_judging_the_next(db, monkeypatch):
    _write(db, "K1", crud.CHAIN_SOURCE, "r", job="J1", a="x")
    db.commit()
    monkeypatch.setattr(replay, "find_rule", lambda name, *a, **k: {"r0": BARE_RULE, "r": RULE}[name])
    for run_id, rule in (("w-bare", BARE_RULE), ("w-lines", RULE)):     # the bare table's tally first
        db.add(models.RetroactiveRun(run_id=run_id, op="chain_replay", params=json.dumps({"rule": rule["name"]}),
                                     state="running"))
        db.commit()
        replay.open_tally(db, run_id, rule)
        run = db.query(models.RetroactiveRun).filter_by(run_id=run_id).one()
        run.state, run.result = "done", json.dumps({"rows_staged": 0, "pages_failed": 0})
        db.commit()
    said = []
    assert replay.sweep_finished_replays(said.append, session_factory=lambda: _Kept(db)) == 2
    assert said == ["[ReplaySweep] run w-bare r0: not swept - gm_bare: line table not built - the sweep cannot tell",
                    "[ReplaySweep] run w-lines r: 1 map(s) its batches never named emptied in gm_lines"]
    assert replay._gone_maps(db, RULE, "w-lines") == (["job"], []), "the second table's map was taken back"
