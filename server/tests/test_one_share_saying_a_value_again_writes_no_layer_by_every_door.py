# -*- coding: utf-8 -*-
"""The old write's answers for a cell another source already says, asked by write_lines' step 2 (lead 11-11 ㄴ):

  door × case                     its share again   behind another share   chain says the shown value   re-spelling
  watcher (funnel)                no layer (C)      -                      -                            -
  re-read (Retry door -> funnel)  no layer          -                      -                            -
  write_lines (any kind)          -                 its old layer, front   no line                      its own line
A batch none of whose items is left a line writes no audit row (the audit is a batch's work kinds - owner 11-10).
"""
import os
import sqlite3

from sqlalchemy import select

from database import crud, lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import TABLE, _now, _write, fixture_db  # noqa: F401


def _ext(share, name):
    root = "c:\\share_%s" % share
    return crud.external_layer_name("workspace", "%s@%s" % (TABLE, root), "%s\\%s" % (root, name))


def _layers(db, row_id):
    return lines.layers(db, TABLE, [row_id], ["a"]).get((row_id, "a"), {})


def test_a_share_saying_its_value_again_behind_another_share_moves_its_old_layer_to_the_front(db):
    """Owner 11-08 «층을 새로하지 말고 순서를 바꿔»: share a said v, share b said w after it, a second file of share a
    says v - the line is written under share a's first layer (its source), no layer of the second file."""
    a1, a2, b1 = _ext("a", "d1.csv"), _ext("a", "d2.csv"), _ext("b", "d1.csv")
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "v"}, "source_name": a1, "written_by": "loader",
                      "input_row": "1"})["changed"]
    _write(db, {"row_id": r, "values": {"a": "w"}, "source_name": b1, "written_by": "loader", "input_row": "1"},
           tx="tx2")
    assert _now(db)[r]["a"] == "w"
    out = _write(db, {"row_id": r, "values": {"a": "v"}, "source_name": a2, "written_by": "loader", "input_row": "2"},
                 tx="tx3")
    layers = _layers(db, r)
    assert sorted(layers) == sorted([a1, b1]) and layers[a1]["value"] == "v" and layers[a1]["origin_row_id"] == "2"
    assert _now(db)[r]["a"] == "v", "share a's layer is in front"
    [said] = out["items"]
    assert (said["work"], said["columns"], said["line_id"]) == ("edit", ["a"], layers[a1]["line_id"]), said


def test_a_new_chain_layer_saying_what_the_cell_shows_writes_no_line(db):
    """Owner 11-08: a chain layer the cell has none of, saying what the cell shows, writes nothing; another value is
    written."""
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})["changed"]
    out = _write(db, {"row_id": r, "values": {"a": "x"}, "source_name": crud.CHAIN_SOURCE, "written_by": "chain"},
                 kind="chain", tx="tx2")
    assert (out["lines"], out["left_out"], sorted(_layers(db, r))) == (0, 1, ["f1"]), out
    out = _write(db, {"row_id": r, "values": {"a": "y"}, "source_name": crud.CHAIN_SOURCE, "written_by": "chain"},
                 kind="chain", tx="tx3")
    assert out["lines"] == 1 and sorted(_layers(db, r)) == sorted(["f1", crud.CHAIN_SOURCE])


def test_a_batch_whose_every_item_says_what_is_there_writes_no_audit_row(db):
    """Share a's second file repeating share b's newest, and a new chain layer saying what the cell shows: no line,
    no audit row."""
    a1, a2, b1 = _ext("a", "d1.csv"), _ext("a", "d2.csv"), _ext("b", "d1.csv")
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "v"}, "source_name": a1})["changed"]
    _write(db, {"row_id": r, "values": {"a": "v"}, "source_name": b1}, tx="tx2")
    out = _write(db, {"row_id": r, "values": {"a": "v"}, "source_name": a2},
                 {"row_id": r, "values": {"a": "v"}, "source_name": crud.CHAIN_SOURCE, "written_by": "chain"}, tx="tx3")
    rows = db.execute(select(lines.AuditBatch.__table__).where(lines.AuditBatch.transaction_id == "tx3")).all()
    assert (out["lines"], out["left_out"], out["audit"], rows) == (0, 2, [], []), out


def test_a_re_spelling_is_written_on_its_own_line_whatever_its_share_says(db):
    """A notation re-spelling is no new statement: share a's first layer is re-spelled where it is, though share a's
    newer layer says the new spelling already."""
    a1, a2 = _ext("a", "d1.csv"), _ext("a", "d2.csv")
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "abc"}, "source_name": a1, "written_by": "loader",
                      "input_row": "1"})["changed"]
    _write(db, {"row_id": r, "values": {"a": "ABC"}, "source_name": a2, "written_by": "loader", "input_row": "1"},
           tx="tx2")
    first = _layers(db, r)[a1]
    _write(db, {"row_id": r, "values": {"a": "ABC"}, "source_name": a1, "written_by": first["updated_by"],
                "acted_by": "notation", "input_row": first["origin_row_id"], "at": first["ingested_at"],
                "respelled": True}, kind="notation", tx="tx3")
    layers = _layers(db, r)
    assert sorted(layers) == sorted([a1, a2]) and layers[a1]["value"] == "ABC", layers


def test_a_reread_of_a_share_s_file_saying_its_value_again_leaves_no_third_layer(tmp_path):
    """C's fixture (test_two_shares_saying_one_value_keep_a_layer_each) through the real watcher, then share a's
    second file handed again by the re-read (`reread.hand_files`, what Read now and Read these call)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database import models
    from ingestion import reread
    from test_an_external_source_reads_as_raws_does import CSV_PLUGIN, TABLE as TB, _plugin, _run, _settings

    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    share_a, share_b = str(tmp_path / "share_a"), str(tmp_path / "share_b")
    for folder, names in ((share_a, ("d1.csv", "d2.csv")), (share_b, ("d1.csv",))):
        os.makedirs(folder)
        for name in names:
            with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                f.write("lot\nL1\n")
    db = tmp_path / "box.db"
    _plugin(str(data), "tb", CSV_PLUGIN % '"same"')
    _settings(str(data), {"tb": TB}, [("tb", share_a, "*.csv"), ("tb", share_b, "*.csv")])

    def read(c):
        return c.execute("SELECT count(*) FROM file_ingestion_logs WHERE table_name = 'tb' "
                         "AND status = 'SUCCESS'").fetchone()[0]

    def layers(c):
        return sorted(crud.layer_share(name) for (name,) in c.execute(
            "SELECT l.source_name FROM tb__lines l JOIN line_columns k ON k.table_name = 'tb' AND "
            "k.column_name = 'val' AND k.bit < 64 WHERE (l.head_0 >> k.bit) & 1 = 1 "
            "AND (l.withdrawn_0 >> k.bit) & 1 = 0"))
    _run(tmp_path, db, lambda c: read(c) >= 3)
    with sqlite3.connect(str(db)) as c:
        assert read(c) == 3 and c.execute("SELECT val FROM tb").fetchall() == [("same",)]     # canary: read
        two = layers(c)
    assert len(two) == 2 and len(set(two)) == 2 and None not in two, two

    engine = create_engine("sqlite:///" + db.as_posix())
    s = sessionmaker(bind=engine)()
    try:
        [row] = s.query(models.FileChecklist).filter(models.FileChecklist.table_name == "tb",
                                                     models.FileChecklist.filepath.like("%share_a%d2.csv")).all()
        log_id, handed = row.id, reread.hand_files(s, "tb", row.source, [os.path.join(share_a, "d2.csv")])
    finally:
        s.close()
        engine.dispose()
    assert handed["ids"] == [log_id], handed
    _run(tmp_path, db, lambda c: read(c) >= 4)
    with sqlite3.connect(str(db)) as c:
        assert read(c) == 4, "canary: the re-read was read"
        assert layers(c) == two, "share a's file read again leaves no third layer"

