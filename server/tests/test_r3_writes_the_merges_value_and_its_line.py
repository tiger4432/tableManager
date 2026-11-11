"""R3 (`replay.recompute_display_values`) shows what `lines.merge` shows, and writes the value and the line it is
together - t's column and its won_by (lead 11-11: R3 judged «what shows» again by compute_priority_value, a tie went
by source name, and won_by kept naming the old line)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from chain import replay
from database import crud, lines, models
from support import line_tables

TABLE = "r3_merge_t"
TABLES = {TABLE: {"business_key": "k", "column_types": {"k": "string", "v": "string"}}}
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


def _world(db, said, shows):
    """Lines `said` [(source, value, hours after T0)] on row r1 (the first also says the key); t shows the line
    numbered `shows` (1-based). -> the line ids"""
    bits = line_tables.bits_of(TABLE)
    with db.get_bind().begin() as conn:
        ids = [line_tables.line(conn, TABLE, bits, "r1", source=source,
                                values={**({"k": "K1"} if n == 0 else {}), "v": value},
                                at=T0 + timedelta(hours=hours), business_key="K1")
               for n, (source, value, hours) in enumerate(said)]
        line_tables.now(conn, TABLE, "r1", "K1", values={"k": "K1", "v": said[shows - 1][1]},
                        won_by={"k": ids[0], "v": ids[shows - 1]})
    db.expire_all()
    return ids


def _t(db):
    v, won_by = db.execute(text('SELECT v, won_by FROM "%s" WHERE row_id = :r' % TABLE), {"r": "r1"}).one()
    return v, (won_by if isinstance(won_by, dict) else json.loads(won_by))["v"]


def test_a_persons_line_over_the_shown_file_line_takes_the_value_and_won_by(db):
    _file, person = _world(db, [("f.csv", "A", 0), ("user", "B", 1)], shows=1)

    stats = replay.recompute_display_values(db, TABLE, apply=True, log=lambda *_: None)

    assert (stats["cells_changed"], stats["changes"][0]["top_source"]) == (1, "user")
    assert _t(db) == ("B", person)


def test_two_file_lines_of_one_instant_show_the_later_as_the_merge_does(db):
    _first, later = _world(db, [("f03.csv", "A", 0), ("f07.csv", "B", 0)], shows=1)

    stats = replay.recompute_display_values(db, TABLE, apply=True, log=lambda *_: None)

    merged = lines.merge(db, TABLE, crud.TABLE_CONFIG[TABLE], ["r1"])["r1"]["v"]
    assert (stats["cells_changed"], merged) == (1, ("B", later))
    assert _t(db) == merged

