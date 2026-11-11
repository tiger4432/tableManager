"""A whole replay's sweep (`replay._gone_maps`) finds the maps its rule's layers sit on in the rule's own chain lines
(t__lines, `cell_layer._claimed_filter`) - the chain's name or its per-source-row name, written by the rule's
declaration. A line whose columns are all withdrawn owns nothing: the rule took that map back already. sqlite."""
import pytest

from chain import replay
from database import crud, lines, models
from database.database import Base
from database.write_lines import write_lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE = "gm_lines"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "job": "string", "a": "string"}}
RULE = {"name": "r", "allow_retraction": True, "target_table": TABLE, "trigger_table": "gm_src",
        "trigger_job_column": "job", "target_job_column": "job"}


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    models.init_dynamic_models({TABLE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, TABLE, CFG)
    db_session.commit()
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
