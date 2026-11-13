# -*- coding: utf-8 -*-
"""총괄 a61d32f4f 답 ㄱ: a table that declares only `composite_key_source` rebuilds its key by the
same mechanism, with the same answer, as one that also carries a `business_key` column.

One fixture, run on both shapes (each with its `uq_bk_` index, as every keyed table in an install
has); each branch must leave the same rows, keys, values and layers - the `business_key` column
itself is the only thing one shape has and the other has not.

  by key               create, write again by key                    one row
  named id             create under a uuid7, write again by key      one row
  grid                 an empty row, key parts typed by its id       one row
  part edited          a key part written by id                      key rebuilt, by key finds it
  part blanked         a key part blanked by id                      keyed by the rest (총괄 242f4a43a)
  edited onto a key    another row holds the new key                 merged, one row
  pinned               a pin moves a key part's shown value          key rebuilt
  pinned onto a key    the pin's key is another row's                merged into it, one row - through
                                                                     the write seat's merge (총괄 6e041f4cb ①)
  ... onto a person's  the holder carries a person's value           it stays: a pin is a choice of
                                                                     layer, not a person's value
  written onto one     a person writes only R's key part (and a note)  the holder's human value stays,
                                                                     what the person wrote moves over
  written over one     ... and the very column the holder's person    person vs person: the write shows,
                       wrote                                         the holder's value kept as a layer
"""
import os
import re
import sys

import pytest
import uuid6
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
from database import crud, lines, models, schemas                    # noqa: E402
from tests.support import line_tables                                 # noqa: E402

pytestmark = pytest.mark.pg
PARTS = ["job", "x", "y"]
COLUMNS = {"job": "string", "x": "number", "y": "number", "netdie": "number", "note": "string"}
SHAPES = {
    "rk_key": {"business_key": "k", "composite_key_source": PARTS,
               "column_types": {"k": "string", **COLUMNS}},
    "rk_parts": {"composite_key_source": PARTS, "column_types": dict(COLUMNS)},
}
ONE = "rk_one"                                   # keyed by one column - not a shape the branches compare
TABLES = {**SHAPES, ONE: {"business_key": "k", "column_types": {"k": "string", **COLUMNS}}}


@pytest.fixture(name="world")
def fixture_world(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    config = {t: {**c, "display_columns": list(c["column_types"])} for t, c in TABLES.items()}
    saved = dict(crud.TABLE_CONFIG)
    for table in TABLES:
        retire_dynamic_model(table)
    models.init_dynamic_models(config)
    crud.TABLE_CONFIG.update(config)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for table in TABLES:
        models.DYNAMIC_TABLES[table].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    with pg_engine.begin() as conn:
        for table in TABLES:
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "uq_bk_%s" ON "%s"."%s" (business_key_val)'
                              % (table, PG_TEST_SCHEMA, table)))
    for table in TABLES:
        line_tables.build(pg_engine, table)            # every declared table keeps lines (11-11)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        yield {"db": session, "engine": pg_engine}
    finally:
        session.close()
        for table in TABLES:
            line_tables.drop(pg_engine, table)
        with pg_engine.begin() as conn:
            for table in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, table)))
                for side in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
                    conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t'
                                      % (PG_TEST_SCHEMA, side)), {"t": table})
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for table in TABLES:
            retire_dynamic_model(table)


def _write(db, table, items):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source,
                                  updated_by="t") for row_id, updates, source in items]))
    db.commit()


def _part(job, netdie=None):
    return {"job": job, "x": 1, "y": 2, **({} if netdie is None else {"netdie": netdie})}


def _ids(db, table):
    return [r for (r,) in db.execute(text('SELECT row_id FROM "%s"."%s" ORDER BY row_id'
                                          % (PG_TEST_SCHEMA, table)))]


def _by_key(db, table):
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    _write(db, table, [(None, _part("J1", 2), "chain:b")])


def _named(db, table):
    _write(db, table, [(str(uuid6.uuid7()), _part("J1", 1), "chain:a")])
    _write(db, table, [(None, _part("J1", 2), "chain:b")])


def _grid(db, table):
    crud.create_empty_rows_batch(db, table, 1, "t")
    db.commit()
    _write(db, table, [(_ids(db, table)[0], _part("J1", 1), "user")])
    _write(db, table, [(None, _part("J1", 2), "chain:b")])


def _part_edited(db, table):
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    _write(db, table, [(_ids(db, table)[0], {"job": "J2"}, "user")])
    _write(db, table, [(None, _part("J2", 2), "chain:b")])


def _part_blanked(db, table):
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    _write(db, table, [(_ids(db, table)[0], {"job": ""}, "user")])


def _edited_onto_a_key(db, table):
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    first = _ids(db, table)[0]
    _write(db, table, [(None, _part("J2", 2), "chain:a")])
    second = [r for r in _ids(db, table) if r != first][0]
    _write(db, table, [(second, {"job": "J1"}, "user")])


def _pinned(db, table):
    """Three layers on a key part; the pin shows the middle one - a key neither write left."""
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    row = _ids(db, table)[0]
    _write(db, table, [(row, {"job": "J2"}, "chain:b")])
    _write(db, table, [(row, {"job": "J3"}, "chain:c")])
    crud.set_cell_manual_priority_batch(db, table, [{"row_id": row, "column_name": "job"}],
                                        "chain:b")
    db.commit()


def _pinned_onto_a_key(db, table):
    """R's hidden layer says J1; the pin shows it while P holds J1_1_2. R's own human value
    travels to P. Until the pin seat called the write seat's merge this raised (an unbound name,
    a65640ca8 .. 10-03) and the pin rolled back."""
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    row = _ids(db, table)[0]
    _write(db, table, [(row, {"job": "J2"}, "chain:b")])
    _write(db, table, [(row, {"netdie": 3}, "user")])
    _write(db, table, [(None, _part("J1", 5), "chain:c")])
    crud.set_cell_manual_priority_batch(db, table, [{"row_id": row, "column_name": "job"}],
                                        "chain:a")
    db.commit()


def _pinned_onto_a_persons_value(db, table):
    """P, the key's holder, carries a person's netdie; R's is a machine's. Only the pinned cell
    counts as the person's in the merge (총괄 6e041f4cb ① 답), so P's value stays."""
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    row = _ids(db, table)[0]
    _write(db, table, [(row, {"job": "J2"}, "chain:b")])
    _write(db, table, [(None, _part("J1", 5), "chain:c")])
    holder = [r for r in _ids(db, table) if r != row][0]
    _write(db, table, [(holder, {"netdie": 9}, "user")])
    crud.set_cell_manual_priority_batch(db, table, [{"row_id": row, "column_name": "job"}],
                                        "chain:a")
    db.commit()


def _written_onto_a_persons_value(db, table):
    """A person writes R's key part and a note - nothing else - onto P's key; P carries a person's
    netdie, R a machine's. Only what the person wrote counts as the person's (총괄 6e041f4cb ① 답),
    so P's netdie stays and the note moves over. It used to count every column."""
    _write(db, table, [(None, _part("J2", 1), "chain:a")])
    row = _ids(db, table)[0]
    _write(db, table, [(None, _part("J1", 5), "chain:c")])
    holder = [r for r in _ids(db, table) if r != row][0]
    _write(db, table, [(holder, {"netdie": 9}, "user")])
    _write(db, table, [(row, {"job": "J1", "note": "typed"}, "user")])


def _written_over_a_persons_value(db, table):
    """The person writes R's key part AND netdie, the column P's person wrote: person against
    person - the write shows, and P's value is kept as a `user (old_exist_…)` layer."""
    _write(db, table, [(None, _part("J2", 1), "chain:a")])
    row = _ids(db, table)[0]
    _write(db, table, [(None, _part("J1", 5), "chain:c")])
    holder = [r for r in _ids(db, table) if r != row][0]
    _write(db, table, [(holder, {"netdie": 9}, "user")])
    _write(db, table, [(row, {"job": "J1", "netdie": 3}, "user")])


def _made_onto_a_key(db, table):
    """총괄 829e3fe20: a row this batch makes under a new id lands on P's key - the merge took
    its layers and left the pending row to be INSERTED, a shell with none."""
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    _write(db, table, [(str(uuid6.uuid7()), _part("J1", 2), "chain:b")])


def _made_then_moved_onto_a_key(db, table):
    """... and a row an earlier item of the same batch made, moved onto P's key by a later one."""
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    made = str(uuid6.uuid7())
    _write(db, table, [(made, _part("J2", 2), "chain:b"), (made, {"job": "J1"}, "user")])


def _named_with_every_part_onto_a_key(db, table):
    """Ruling 190: a row_id naming a row keeps its row - a person writes every key part of R, P's key: the write lands
    on R and R merges into P (its layer kept under R's key), never claimed by P's key the way a made row is (lead
    11-13)."""
    _write(db, table, [(None, _part("J1", 1), "chain:a")])
    _write(db, table, [(None, _part("J2", 2), "chain:a")])
    row = [r for r, k in _keyed(db, table) if k == "J2_1_2"][0]
    _write(db, table, [(row, _part("J1"), "user")])


def _keyed(db, table):
    return list(db.execute(text('SELECT row_id, business_key_val FROM "%s"."%s"' % (PG_TEST_SCHEMA, table))))


BRANCHES = {"by_key": (_by_key, ["J1_1_2"]), "named": (_named, ["J1_1_2"]),
            "made_onto_a_key": (_made_onto_a_key, ["J1_1_2"]),
            "made_then_moved_onto_a_key": (_made_then_moved_onto_a_key, ["J1_1_2"]),
            "grid": (_grid, ["J1_1_2"]), "part_edited": (_part_edited, ["J2_1_2"]),
            "part_blanked": (_part_blanked, ["_1_2"]),
            "edited_onto_a_key": (_edited_onto_a_key, ["J1_1_2"]),
            "pinned": (_pinned, ["J2_1_2"]),
            "pinned_onto_a_key": (_pinned_onto_a_key, ["J1_1_2"]),
            "pinned_onto_a_persons_value": (_pinned_onto_a_persons_value, ["J1_1_2"]),
            "written_onto_a_persons_value": (_written_onto_a_persons_value, ["J1_1_2"]),
            "written_over_a_persons_value": (_written_over_a_persons_value, ["J1_1_2"]),
            "named_with_every_part_onto_a_key": (_named_with_every_part_onto_a_key, ["J1_1_2"])}


UUID_TAIL = re.compile(r"_?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\)$")


def _answer(world, table):
    """Rows (key and values) and layers, by key rather than by row_id - ids differ per run."""
    with world["engine"].connect() as conn:
        rows = conn.execute(text('SELECT row_id, business_key_val, job, x, y, netdie, note FROM "%s"."%s"'
                                 % (PG_TEST_SCHEMA, table))).all()
        key_of = {r[0]: r[1] for r in rows}
    # a cell's lines (11-11); a merged layer's name carries the whole merged row_id (aa14dd278) - each shape has its
    # own ids, so it is compared without it
    layers = [(row, column, UUID_TAIL.sub(")", source), "" if said["value"] is None else str(said["value"]))
              for (row, column), by in lines.layers(world["db"], table, list(key_of)).items() if column != "k"
              for source, said in by.items()]
    return (sorted((r[1] or "", r[2] or "", str(r[3]), str(r[4]), str(r[5]), r[6] or "") for r in rows),
            sorted((key_of.get(l[0]) or "", l[1], l[2], l[3]) for l in layers))


def _outliving(world, table):
    """Layers and overwrite marks under a row_id the table no longer has - a merged-away shell's."""
    with world["engine"].connect() as conn:
        return tuple(conn.execute(text(
            'SELECT count(*) FROM "%s".%s m WHERE m.table_name = :t AND NOT EXISTS '
            '(SELECT 1 FROM "%s"."%s" r WHERE r.row_id = m.row_id)'
            % (PG_TEST_SCHEMA, side, PG_TEST_SCHEMA, table)), {"t": table}).scalar()
                     for side in ("cell_sources", "cell_overwrites"))


@pytest.mark.parametrize("branch", list(BRANCHES))
def test_both_shapes_give_one_answer(world, branch):
    build, keys = BRANCHES[branch]
    answers = {}
    for table in SHAPES:
        build(world["db"], table)
        answers[table] = _answer(world, table)
        assert _outliving(world, table) == (0, 0), (table, branch)      # 총괄 a13fcf00c
        assert [r[0] or None for r in answers[table][0]] == keys, (table, answers[table][0])
    assert answers["rk_key"] == answers["rk_parts"]
    if branch.startswith("made"):
        # the made row is claimed by its key (lead 11-13): its write lands on P itself - no shell, so no merge
        assert any(layer[:3] == ("J1_1_2", "netdie", "chain:b") for layer in answers["rk_parts"][1])
    if branch == "named_with_every_part_onto_a_key":
        assert ("J1_1_2", "job", "user (J2_1_2)", "J1") in answers["rk_parts"][1], answers["rk_parts"][1]
    if branch == "pinned_onto_a_key":
        rows, layers = answers["rk_parts"]
        assert rows[0][4] == "3.0"                                  # R's human value, on P
        assert any(layer[:2] == ("J1_1_2", "job") and layer[2].startswith("chain:b (")
                   for layer in layers)                             # R's layers, inherited
    if branch == "pinned_onto_a_persons_value":
        assert answers["rk_parts"][0][0][4] == "9.0"                # the holder's person value
    if branch == "written_onto_a_persons_value":
        assert answers["rk_parts"][0][0][4:] == ("9.0", "typed")    # stays · what was written moves
    if branch == "written_over_a_persons_value":
        rows, layers = answers["rk_parts"]
        assert rows[0][4] == "3.0"                                  # the write shows
        assert any(layer[:2] == ("J1_1_2", "netdie") and layer[2].startswith("user (old_exist_")
                   and layer[3] == "9" for layer in layers)         # the holder's, kept


def test_a_row_made_by_its_row_id_on_a_one_column_key_gets_that_key(world):
    """Lead 11-13 ㄴ: a table keyed by one column - a row made by a row_id is keyed by its key column's value (the
    assembler's `_key_from_the_key_column`, the seat a keyed write goes through): onto P's key the write lands on P,
    onto a new key the row is made under its row_id with that key. Both were put keyless beside P."""
    db = world["db"]
    _write(db, ONE, [(None, {"k": "P", "netdie": 1}, "chain:a")])
    held = [r for r, _k in _keyed(db, ONE)]
    _write(db, ONE, [(str(uuid6.uuid7()), {"k": "P", "netdie": 2}, "chain:b")])
    made = str(uuid6.uuid7())
    _write(db, ONE, [(made, {"k": "N", "netdie": 3}, "chain:b")])
    assert sorted(_keyed(db, ONE), key=lambda r: r[1]) == [(made, "N"), (held[0], "P")]
