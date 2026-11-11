"""R3 (`replay.recompute_display_values`) merges the rows it asks about again through write_lines' door
(`_merges_again`), so the value and the line it is (won_by) are written together, as every write writes them (lead
11-11: R3 judged «what shows» again by compute_priority_value and won_by kept naming the old line). A declared formula
wins as the merge ranks it; a removed formula's column with no layer goes blank (owner 11-11 ㄱ); each cell it moves
keeps its history line, old -> new."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from chain import formula, replay
from database import crud, lines, models
from support import line_tables

TABLE = "r3_merge_t"
TABLES = {TABLE: {"business_key": "k", "column_types": {"k": "string", "v": "string", "n": "string"}}}
T0 = datetime(2026, 11, 1, 1, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    line_tables.build(db_session.get_bind(), TABLE)
    yield db_session
    db_session.rollback()
    line_tables.drop(db_session.get_bind(), TABLE)
    from conftest import retire_dynamic_model
    retire_dynamic_model(TABLE)
    crud.TABLE_CONFIG.pop(TABLE, None)


def _world(db, said, shows, n=None):
    """Lines `said` [(source, value, hours after T0)] on row r1's «v» (the first also says the key); t shows the line
    numbered `shows` (1-based) and «n» = `n` with no line. -> the line ids"""
    bits = line_tables.bits_of(TABLE)
    with db.get_bind().begin() as conn:
        ids = [line_tables.line(conn, TABLE, bits, "r1", source=source,
                                values={**({"k": "K1"} if i == 0 else {}), "v": value},
                                at=T0 + timedelta(hours=hours), business_key="K1")
               for i, (source, value, hours) in enumerate(said)]
        line_tables.now(conn, TABLE, "r1", "K1", values={"k": "K1", "v": said[shows - 1][1], "n": n},
                        won_by={"k": ids[0], "v": ids[shows - 1]})
    db.expire_all()
    return ids


def _t(db, column="v"):
    value, won_by = db.execute(text('SELECT %s, won_by FROM "%s" WHERE row_id = :r' % (column, TABLE)),
                               {"r": "r1"}).one()
    return value, (won_by if isinstance(won_by, dict) else json.loads(won_by)).get(column)


def _run(db, **kw):
    return replay.recompute_display_values(db, TABLE, apply=True, log=lambda *_: None, **kw)


def test_a_persons_line_over_the_shown_file_line_takes_the_value_and_won_by(db):
    _file, person = _world(db, [("f.csv", "A", 0), ("user", "B", 1)], shows=1)

    stats = _run(db)

    assert (stats["cells_changed"], stats["changes"][0]["top_source"]) == (1, "user")
    assert _t(db) == ("B", person)


def test_two_file_lines_of_one_instant_show_the_later_as_the_merge_does(db):
    _first, later = _world(db, [("f03.csv", "A", 0), ("f07.csv", "B", 0)], shows=1)

    stats = _run(db)

    merged = lines.merge(db, TABLE, crud.TABLE_CONFIG[TABLE], ["r1"])["r1"]["v"]
    assert (stats["cells_changed"], merged) == (1, ("B", later))
    assert _t(db) == merged


def test_a_declared_formula_over_two_file_lines_shows_its_answer_and_won_by_names_it(db, monkeypatch):
    _first, later = _world(db, [("f03.csv", "A", 0), ("f07.csv", "B", 1)], shows=2)
    name = "%s (%s)" % (crud.CHAIN_SOURCE, formula.RULE_NAME % (TABLE, "v"))     # the layer a formula ranks as
    monkeypatch.setattr(formula, "columns", lambda: {(TABLE, "v"): (name, lambda rows: "F", ["k"], "=F")})

    stats = _run(db)

    assert stats["cells_changed"] == 1
    assert _t(db) == ("F", lines.FORMULA_WON)


def test_a_removed_formulas_column_with_no_layer_goes_blank_with_its_history_line(db):
    _world(db, [("f03.csv", "A", 0), ("f07.csv", "B", 1)], shows=2, n="9")

    _run(db, formula_removed=["n"])

    assert _t(db, "n") == (None, None)
    said = [(a.old_value, a.new_value, a.source_name) for a in db.query(models.AuditLog).filter(
        models.AuditLog.table_name == TABLE, models.AuditLog.row_id == "r1", models.AuditLog.column_name == "n")]
    assert said == [("9", None, replay.R3_AUDIT_SOURCE)]


def test_a_dry_run_leaves_the_table_and_the_outbox_as_they_were(db):
    first, _person = _world(db, [("f.csv", "A", 0), ("user", "B", 1)], shows=1, n="9")
    outbox = db.query(models.DatabaseOutbox).count()

    stats = replay.recompute_display_values(db, TABLE, apply=False, formula_removed=["n"], log=lambda *_: None)

    assert stats["cells_changed"] == 2, "canary: the preview found the two cells the run would move"
    assert (_t(db), _t(db, "n")) == (("A", first), ("9", None))
    assert db.query(models.DatabaseOutbox).count() == outbox
    assert db.query(models.AuditLog).filter(models.AuditLog.table_name == TABLE).count() == 0
