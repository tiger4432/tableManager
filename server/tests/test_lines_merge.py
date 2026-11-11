"""database.lines.merge / spoken on sqlite: the SQL order is crud.rank_terms, the same order
compute_priority_value walks (parity per cell); a column no line spoke in keeps t; a pin whose source has no head
line keeps t; a column every source withdrew is empty (docs/design/CELL_SOURCE_OVERHAUL.md «순위로 합치는 법»)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import crud, lines
from database.models import CellOverwrite, sql_type_of

CFG = {"column_types": {"lot": "string", "qty": "number"}}
T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    from sqlalchemy import MetaData, Table

    engine = create_engine("sqlite://")
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource, CellOverwrite):
        model.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    Table("t", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(session.connection())
    lines.ensure_line_table(session, "t", CFG)
    yield session
    session.close()


def put(db, row, source, at, value=None, withdraw=False, column="lot", owner_rule=None):
    s = lines.shape(db, "t", CFG)
    bit = s["bits"][column]
    mask, chunk = lines._mask(bit), bit // lines.BITS_PER_CHUNK
    lines.note_sources(db, [source])
    db.execute(s["lines"].insert().values(
        line_kind="withdraw" if withdraw else "write", source_name=source, at=at, row_id=row, owner_rule=owner_rule,
        **{lines.value_column(column): None if withdraw else value, f"written_{chunk}": mask, f"head_{chunk}": mask,
           f"withdrawn_{chunk}": mask if withdraw else 0}))


def pin(db, row, source, column="lot"):
    db.execute(CellOverwrite.__table__.insert().values(table_name="t", row_id=row, column_name=column,
                                                        updated_by="tester", manual_priority_source=source))


CELLS = {   # row: [(source, minutes after T0 or None, value, withdrawn)], pin
    "r1": ([("user", 1, "u", False), ("fileA", 2, "a", False), ("fileB", 3, "b", False)], None),
    "r2": ([("fileA", 1, "a", False), ("fileB", 2, "b", False)], None),
    "r3": ([("fileA", None, "a", False), ("fileB", 1, "b", False)], None),
    "r4": ([("fileB", 1, "b", False), ("fileA", 1, "a", False)], None),
    "r5": ([(crud.CHAIN_SOURCE, 1, "c", False), ("fileA", 2, "a", False)], None),
    "r6": ([("user", 1, "u", False), ("fileA", 2, "a", False)], "fileA"),
    "r7": ([("fileA", 1, "a", False), ("fileB", 2, None, True)], None),
}


def test_the_sql_winner_is_compute_priority_values_winner(db):
    for row, (layers, pinned) in CELLS.items():
        for source, minutes, value, withdrawn in layers:
            put(db, row, source, None if minutes is None else T0 + timedelta(minutes=minutes), value, withdrawn)
        if pinned:
            pin(db, row, pinned)
    got = lines.merge(db, "t", CFG, list(CELLS))
    for row, (layers, pinned) in CELLS.items():
        sources = {source: {"value": value, "ingested_at": None if minutes is None else T0 + timedelta(minutes=minutes)}
                   for source, minutes, value, withdrawn in layers if not withdrawn}
        expected, _ = crud.compute_priority_value(sources, pinned, "t")
        assert got[row]["lot"][0] == expected, row
    assert {got[r]["lot"][0] for r in ("r1", "r4", "r6", "r7")} == {"u", "a"}       # canary: answers differ by row


def test_a_column_no_line_spoke_in_keeps_t(db):
    put(db, "r1", "fileA", T0, "a")
    assert lines.spoken(db, "t", ["r1", "r2"]) == {"r1": {"lot"}}
    assert lines.merge(db, "t", CFG, ["r1", "r2"]) == {"r1": {"lot": ("a", 1)}}


def test_a_column_only_withdrawn_is_spoken_and_empty(db):
    put(db, "r1", "fileA", T0, withdraw=True)
    assert lines.spoken(db, "t", ["r1"]) == {"r1": {"lot"}}
    assert lines.merge(db, "t", CFG, ["r1"]) == {"r1": {"lot": (None, None)}}


def test_cut_table_pinned_column_machine_write_keeps_the_shown_value(db):
    """Lead 11-11: a pin whose source has no head line (its layer is in the cut-off past) keeps t's value."""
    pin(db, "r1", "user")
    put(db, "r1", "fileA", T0, "machine")
    assert lines.merge(db, "t", CFG, ["r1"]) == {}


def test_bit_63_and_a_number_column_read_back_typed(db):
    cfg = {"column_types": {**{f"c{i}": "string" for i in range(63)}, "qty": "number"}}
    lines.alter_columns(db, "t", {"column_types": {**CFG["column_types"], **cfg["column_types"]}},
                        add=[f"c{i}" for i in range(63)])
    put(db, "r1", "fileA", T0, "7", column="qty")
    bits = lines.bit_map(db, "t")
    assert max(bits.values()) >= 63 and lines._mask(63) < 0                        # canary: the sign bit is in use
    sign = next(c for c, b in bits.items() if b == 63)
    put(db, "r1", "fileA", T0, "x", column=sign)
    got = lines.merge(db, "t", {"column_types": {**CFG["column_types"], **cfg["column_types"]}}, ["r1"])
    assert got["r1"]["qty"][0] == 7 and got["r1"][sign][0] == "x"


def test_layers_are_each_sources_standing_word_in_the_old_shape(db):
    put(db, "r1", "fileA", T0, "a")
    put(db, "r1", "fileB", T0, withdraw=True)
    put(db, "r1", "fileA", T0, "7", column="qty")
    got = lines.layers(db, "t", ["r1", "r2"])
    assert set(got) == {("r1", "lot"), ("r1", "qty")}
    assert set(got[("r1", "lot")]) == {"fileA"}                    # a withdrawn head is no layer
    assert got[("r1", "qty")]["fileA"]["value"] == 7               # read back as t's stored kind
    assert set(got[("r1", "lot")]["fileA"]) >= {"value", "ingested_at", "updated_by", "origin_row_id", "line_id"}
    assert lines.layers(db, "t", ["r1"], columns={"qty"}).keys() == {("r1", "qty")}


def test_merge_without_one_source_is_what_shows_once_it_is_gone(db):
    put(db, "r1", "user", T0, "u")
    put(db, "r1", "fileA", T0, "a")
    put(db, "r2", "user", T0, "only")
    got = lines.merge(db, "t", CFG, ["r1", "r2"], exclude_source="user")
    assert got["r1"]["lot"][0] == "a" and got["r2"]["lot"] == (None, None)
    assert lines.merge(db, "t", CFG, ["r1"])["r1"]["lot"][0] == "u"            # canary: user wins with it


@pytest.mark.parametrize("unowned, shown", [(False, "b"), (True, "a")])
def test_the_rule_declared_later_wins_unless_an_unowned_chain_layer_sits_on_the_cell(db, monkeypatch, unowned, shown):
    """rank_terms 1d: two rules' chain layers - the one declared later wins over the newer one; an unowned chain layer
    on the cell turns the term off and the newer wins (the one statement counts every head line saying the cell)."""
    monkeypatch.setattr(crud, "_rule_order", lambda: {"ra": 0, "rb": 1})
    put(db, "r1", crud.merged_layer_name(crud.CHAIN_SOURCE, "ka"), T0 + timedelta(minutes=3), "a", owner_rule="ra")
    put(db, "r1", crud.merged_layer_name(crud.CHAIN_SOURCE, "kb"), T0 + timedelta(minutes=1), "b", owner_rule="rb")
    if unowned:
        put(db, "r1", crud.CHAIN_SOURCE, T0, "c")
    assert lines.merge(db, "t", CFG, ["r1"])["r1"]["lot"][0] == shown


def test_a_callers_shape_gives_the_same_layers_and_spoken_and_shape_reads_kinds_once(db, monkeypatch):
    """A write holds one shape (A 11-11): layers / spoken given it answer as they do reading for themselves, and the
    shape reads t's stored kinds once."""
    for row, (layers, pinned) in CELLS.items():
        for source, minutes, value, withdrawn in layers:
            put(db, row, source, None if minutes is None else T0 + timedelta(minutes=minutes), value, withdrawn)
    rows = list(CELLS)
    read = []
    keep = lines.physical_kinds
    monkeypatch.setattr(lines, "physical_kinds", lambda *a: read.append(a) or keep(*a))
    s = lines.shape(db, "t", CFG)
    assert len(read) == 1
    assert lines.layers(db, "t", rows) and lines.layers(db, "t", rows, s=s) == lines.layers(db, "t", rows)
    assert lines.spoken(db, "t", rows, s=s) == lines.spoken(db, "t", rows) != {}


def test_one_batchs_two_sources_on_one_cell_the_later_item_wins(db):
    """A batch's lines share one instant, so time cannot order them: the later line wins (rank term 2c), as the old
    write's later layer_instant for a later item did (A QA 11-11). By name alone src1 would win."""
    put(db, "r1", "src1", T0, "y")
    put(db, "r1", "src2", T0, "z")
    assert lines.merge(db, "t", CFG, ["r1"])["r1"]["lot"][0] == "z"
