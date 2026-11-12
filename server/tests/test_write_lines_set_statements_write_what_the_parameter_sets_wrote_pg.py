"""On PostgreSQL write_lines takes a step's rows in one set statement (lead 11-12 ㄴ: psycopg2 sends an UPDATE's
parameter sets one round trip each) - _heads by the earlier lines' masks gathered with bit_or, _merge_now through
crud.update_by_arrays. Gate: the same writes on one fixture leave the same lines and the same t as the parameter sets
(`lines.sets_at_once` off), write by write.

    write                                                    what it reaches
    two new rows from a file                                 _merge_now's moved rows (new)
    a second file on PN-1, qty and note                      the earlier line of its source
    two lines of that source on PN-1 in one batch, one a     _heads: one earlier line two new lines reach, a
      column each, and a person's note on the other row        column each - its masks gathered (bit_or)
    another source saying the value shown                    _merge_now: won_by may move, the values do not
    the same batch again                                     nothing written
"""
import pytest
from sqlalchemy import text

from database import crud, lines, schemas, write_lines
from tests.support import line_tables

pytestmark = pytest.mark.pg

TABLE = "pgqa_bk_table"


def _item(key, source, who="watcher", **values):
    return schemas.GeneralUpdateItem(business_key_val=key, updates={"part_no": key, **values}, source_name=source,
                                     updated_by=who)


WRITES = [
    [_item("PN-1", "f1.csv", qty=1, note="a"), _item("PN-2", "f1.csv", qty=2)],
    [_item("PN-1", "f2.csv", qty=4, note="c")],
    [_item("PN-1", "f2.csv", qty=6), _item("PN-1", "f2.csv", note="z"), _item("PN-2", "user", who="user", note="b")],
    [_item("PN-1", "f1.csv", qty=6)],
    [_item("PN-1", "f1.csv", qty=6)],
]


def _said(db):
    heads = sorted(c for c in db.execute(text('SELECT * FROM "%s" LIMIT 0' % lines.lines_relation(TABLE))).keys()
                   if c.startswith("head_"))
    ln = [tuple(r) for r in db.execute(text('SELECT line_id, business_key_val, source_name, line_kind, %s FROM "%s" ORDER BY line_id'
                                            % (", ".join(heads), lines.lines_relation(TABLE))))]
    t = [tuple(r) for r in db.execute(text('SELECT business_key_val, part_no, qty, note, won_by FROM "%s" '
                                           "ORDER BY business_key_val" % TABLE))]
    return ln, t


def _run(db):
    line_tables.build(db.get_bind(), TABLE)
    said = []
    for batch in WRITES:
        crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[i.model_copy() for i in batch]))
        db.commit()
        said.append(_said(db))
    db.rollback()                                              # its reads' lock goes before the DROP
    line_tables.drop(db.get_bind(), TABLE)
    return said


def test_the_set_statements_write_what_the_parameter_sets_wrote(pg_session, monkeypatch):
    at_once = _run(pg_session)
    monkeypatch.setattr(lines, "sets_at_once", lambda db: False)
    one_by_one = _run(pg_session)
    assert at_once == one_by_one
    # the fixture reaches what it is for: two f2.csv lines of one batch take the earlier f2 line's two columns off
    f2 = [line for line in at_once[2][0] if line[2] == "f2.csv"]
    assert len(f2) == 3 and not any(f2[0][4:]) and any(f2[1][4:]) and any(f2[2][4:]), f2
    assert at_once[4] == at_once[3]                           # the same batch again writes nothing
