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
from database.write_lines import write_lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import (TABLE, _now, _write, fixture_db,  # noqa: F401
                                                                         keep_lines)


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


def test_a_file_whose_own_layer_is_on_the_cell_writes_it_though_its_share_holds_the_value(db):
    """The old write's `src_obj or moved` (QA 11-11): share a's second file has its own layer there (w); saying v,
    which share a's first file holds, it writes its own layer - not the first file's - so a withdraw of the first
    file leaves v, what a live file says."""
    a1, a2 = _ext("a", "d1.csv"), _ext("a", "d2.csv")
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "v"}, "source_name": a1, "input_row": "1"})["changed"]
    _write(db, {"row_id": r, "values": {"a": "w"}, "source_name": a2, "input_row": "1"}, tx="tx2")
    _write(db, {"row_id": r, "values": {"a": "v"}, "source_name": a2, "input_row": "7"}, tx="tx3")
    layers = _layers(db, r)
    assert (layers[a1]["origin_row_id"], layers[a2]["value"], layers[a2]["origin_row_id"]) == ("1", "v", "7"), layers
    _write(db, {"row_id": r, "line_kind": "withdraw", "columns": ["a"], "source_name": a1}, kind="withdraw", tx="tx4")
    assert _now(db)[r]["a"] == "v"


def test_an_item_split_whole_with_a_column_of_no_history_answers_once(db, monkeypatch):
    """QA 11-11: every history column moved to its share's layer, and a column of no history beside it - the item is
    not left out and its line is the split item's."""
    table, cfg = "wl_share_plain", {"composite_key_source": ["k"], "no_history_columns": ["p"],
                                    "column_types": {"k": "string", "a": "string", "p": "string"}}
    monkeypatch.setitem(crud.TABLE_CONFIG, table, cfg)
    keep_lines(db, table, cfg)
    root = "c:\\share_%s"
    a1, a2, b1 = (crud.external_layer_name("workspace", "%s@%s" % (table, root % s), "%s\\%s" % (root % s, n))
                  for s, n in (("a", "d1.csv"), ("a", "d2.csv"), ("b", "d1.csv")))
    out = write_lines(db, table, [{"key": {"k": "K1"}, "values": {"k": "K1", "a": "v", "p": "1"}, "source_name": a1}],
                      kind="funnel", transaction_id="tx1")
    [r] = out["changed"]
    write_lines(db, table, [{"row_id": r, "values": {"a": "w"}, "source_name": b1}], kind="funnel", transaction_id="tx2")
    out = write_lines(db, table, [{"row_id": r, "values": {"a": "v", "p": "2"}, "source_name": a2}], kind="funnel",
                      transaction_id="tx3")
    [said] = out["items"]
    assert (out["lines"], out["left_out"], said["work"]) == (1, 0, "edit") and said["line_id"] is not None, out


def test_a_share_holding_the_value_in_another_priority_class_folds_nothing(monkeypatch):
    """file_layer_fold asks the class only of a cell its share says the value on (11-11): a layer of the share in
    another class is not the class's - the write is its own layer, as before."""
    from types import SimpleNamespace

    a1, a2 = _ext("a", "d1.csv"), _ext("a", "d2.csv")
    monkeypatch.setattr(crud, "get_source_priority", lambda name, table=None: 2 if name == a1 else 99)
    there = SimpleNamespace(source_name=a1, value="v", ingested_at=None)
    assert crud.file_layer_fold([there], a2, "v", "string", TABLE) == (False, [], None)


def test_two_chain_row_layers_in_one_batch_judge_in_turn(db):
    """QA 11-11: the second chain row layer of a batch sees the first one's layer - the chain holds a layer there
    now, so its value is written (the old write, item by item)."""
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "x"}, "source_name": "f1"})["changed"]
    r1, r2 = (crud.merged_layer_name(crud.CHAIN_SOURCE, s) for s in ("src1", "src2"))
    out = _write(db, {"row_id": r, "values": {"a": "y"}, "source_name": r1, "written_by": "chain"},
                 {"row_id": r, "values": {"a": "x"}, "source_name": r2, "written_by": "chain"}, kind="chain", tx="tx2")
    assert (out["lines"], out["left_out"]) == (2, 0), out


def test_a_persons_write_takes_the_pin_off_for_the_items_after_it(db):
    """QA 11-11 P2: f1 pinned over g, a batch [person z, chain p] - the person takes the pin off, so the chain item
    reads z shown and writes p (the old write's `ow` after the person's item); on the batch's first pin it read p
    shown and was left out."""
    g = _ext("b", "g.csv")
    [r] = _write(db, {"key": {"k": "K1"}, "values": {"k": "K1", "a": "p"}, "source_name": "f1"})["changed"]
    _write(db, {"row_id": r, "values": {"a": "q"}, "source_name": g}, tx="tx2")
    crud.bulk_upsert_cell_overwrites(db, [{"table_name": TABLE, "row_id": r, "column_name": "a", "is_overwrite": True,
                                           "updated_by": "kim", "updated_at": None, "manual_priority_source": "f1"}])
    _write(db, {"row_id": r, "line_kind": "mark", "columns": ["a"], "source_name": "f1"}, kind="mark", tx="tx3")
    assert _now(db)[r]["a"] == "p"
    out = _write(db, {"row_id": r, "values": {"a": "z"}, "source_name": "user", "written_by": "kim"},
                 {"row_id": r, "values": {"a": "p"}, "source_name": crud.CHAIN_SOURCE, "written_by": "chain"}, tx="tx4")
    assert (out["lines"], out["left_out"], _now(db)[r]["a"]) == (2, 0, "z"), out
    assert crud.CHAIN_SOURCE in _layers(db, r)


def test_a_row_an_earlier_item_of_the_batch_made_is_there_for_the_items_after_it(db):
    """QA 11-11 P3: a new key written [file x, chain x] in one batch - the chain item meets the row the file item made
    and says what it shows, so it is left out (the old write's is_new False on the second item)."""
    out = _write(db, {"key": {"k": "K9"}, "values": {"k": "K9", "a": "x"}, "source_name": "f1"},
                 {"key": {"k": "K9"}, "values": {"k": "K9", "a": "x"}, "source_name": crud.CHAIN_SOURCE,
                  "written_by": "chain"})
    [r] = list(_now(db))
    assert (out["lines"], out["left_out"], sorted(_layers(db, r))) == (1, 1, ["f1"]), out


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

