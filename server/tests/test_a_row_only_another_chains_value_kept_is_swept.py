# -*- coding: utf-8 -*-
"""«Remove rows with no source left» takes the rows the owner's master already holds from before 96e0fa44d: chain 1
took its value back but left its key layer (and a blank hold), chain 2's attached value kept the row - («K1», no
value, «b1»). The sweep's SQL «shows nothing outside its keys» never handed such a row to `shells`; it now judges
every row, with the same `person_rows` the chain's write seat asks (lead 11-10). The preview counts it first."""
import pytest

from admin import retroactive
from chain import replay
from database import crud, lines, models
from tests.support import line_tables
from tests.test_a_row_a_chain_only_attached_to_goes_with_its_maker import (  # noqa: F401
    MASTER, _master, _official, _put, fixture_db)


def _left_as_before(db):
    """What a take-back left before 96e0fa44d: the maker's value gone, its key layer and a blank hold kept."""
    row = db.query(models.DYNAMIC_TABLES[MASTER]).one()
    layers = lines.layers(db, MASTER, [row.row_id], columns=["val", "hold"])
    ((val_by, val),) = layers[(row.row_id, "val")].items()
    ((hold_by, hold),) = layers[(row.row_id, "hold")].items()
    bits = lines.bit_map(db, MASTER)
    ln = lines.shape(db, MASTER, crud.TABLE_CONFIG[MASTER], assign=False)["lines"]
    conn = db.connection()
    for source, column in ((val_by, "val"), (hold_by, "hold")):    # the cell's older head comes off
        chunk, place = divmod(bits[column], lines.BITS_PER_CHUNK)
        head = ln.c["head_%d" % chunk]
        conn.execute(ln.update().where(ln.c.row_id == row.row_id, ln.c.source_name == source)
                     .values({head.name: head.op("&")(~(1 << place))}))
    line_tables.line(conn, MASTER, bits, row.row_id, kind="withdraw", source=val_by, withdrawn=("val",),
                     written_by=val["updated_by"])
    line_tables.line(conn, MASTER, bits, row.row_id, source=hold_by, values={"hold": None},
                     written_by=hold["updated_by"])
    row.val, row.hold = None, None
    db.commit()
    assert _master(db) == [("K1", None, "b1")]


def test_the_sweep_counts_then_takes_a_row_only_another_chains_value_kept(db):
    _official(db)
    _left_as_before(db)
    said = retroactive.count(db, "remove_shell_rows", {"table": MASTER})
    assert (said["affected"], said["scanned"]) == (1, 1)
    assert replay.remove_shell_rows(db, MASTER, apply=True)["rows_deleted"] == 1
    assert _master(db) == []


@pytest.mark.parametrize("keeper", [{"source": crud.USER_SOURCE, "hold": "mine"}, {"source": "master.csv"}])
def test_a_person_or_a_file_still_keeps_it(db, keeper):
    _official(db)
    _left_as_before(db)
    source = keeper.pop("source")
    _put(db, MASTER, [dict(keeper, k="K1")], source=source)
    assert retroactive.count(db, "remove_shell_rows", {"table": MASTER})["affected"] == 0
    assert replay.remove_shell_rows(db, MASTER, apply=True)["rows_deleted"] == 0
    assert len(_master(db)) == 1


def test_the_chain_that_made_it_keeps_it_while_its_value_stands(db):
    _official(db)
    assert retroactive.count(db, "remove_shell_rows", {"table": MASTER})["affected"] == 0
    assert _master(db) == [("K1", "a1", "b1")]
