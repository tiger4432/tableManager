# -*- coding: utf-8 -*-
"""A second share writing the value another share already wrote keeps its own layer (owner 10-31 «ㄴ», 11-04 «ㄷ»):
an external file's layer name carries its share (`crud.external_layer_name`), and the write's fold
(`file_layer_fold`) folds only within one share (`crud.same_share`). A name with no share in it (from before, a raws file's) folds as every file layer did.

  seat × case                   same share     other share    old name vs new    raws vs external
  file_layer_fold               repeat         written (2)    repeat             repeat
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud  # noqa: E402

T0 = datetime(2026, 11, 4, 9, 0, 0)


def _ext(share_root, name, table="tb"):
    return crud.external_layer_name("workspace", "%s@%s" % (table, share_root), "%s\\%s" % (share_root, name))


A1, A2 = _ext("c:\\share_a", "d1.csv"), _ext("c:\\share_a", "d2.csv")
B1 = _ext("c:\\share_b", "d1.csv")
OLD = "external:workspace:C:\\share_a\\d0.csv"            # a layer named before 11-04
RAWS = "d0.csv"                                            # a raws file's layer
CASES = {"same share": (A1, A2), "other share": (A1, B1), "old name vs new": (OLD, A1), "raws vs external": (RAWS, A1)}


def _layer(name, minutes, value="v"):
    return SimpleNamespace(source_name=name, value=value, ingested_at=T0 + timedelta(minutes=minutes))


@pytest.mark.parametrize("case,expected", [("same share", (True, [], None)), ("other share", (False, [], None)),
                                           ("old name vs new", (True, [], None)), ("raws vs external", (True, [], None))])
def test_the_write_fold(case, expected):
    there, coming = CASES[case]
    assert crud.file_layer_fold([_layer(there, 0)], coming, "v", "string", "tb") == expected


def test_the_share_is_read_back_and_the_name_reads_as_any_file_layer():
    assert (crud.layer_share(A1), crud.layer_share(B1)) == ("tb@c:\\share_a", "tb@c:\\share_b")
    assert crud.layer_share(OLD) is None and crud.layer_share(RAWS) is None
    for name in (A1, OLD):        # the readers of a layer's name answer as they do for the old shape
        assert crud.layer_writer(name) == name and crud.layer_ranks_as(name) == name
        assert crud.is_file_layer(name) and crud.get_source_priority(name, "tb") == 99


def test_two_shares_with_one_value_leave_two_layers_through_the_real_watcher(tmp_path):
    """The real watcher (`run_watcher.main`) on a scratch root and a sqlite file: share_a then share_b, each a file
    with the same row - two layers of the cell, one per share. Then a second file in share_a says it again - no
    third layer."""
    from test_an_external_source_reads_as_raws_does import CSV_PLUGIN, TABLE, _plugin, _run, _settings

    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    share_a, share_b = str(tmp_path / "share_a"), str(tmp_path / "share_b")
    for folder in (share_a, share_b):
        os.makedirs(folder)
        with open(os.path.join(folder, "d1.csv"), "w", encoding="utf-8") as f:
            f.write("lot\nL1\n")
    db = tmp_path / "box.db"
    _plugin(str(data), "tb", CSV_PLUGIN % '"same"')
    _settings(str(data), {"tb": TABLE}, [("tb", share_a, "*.csv"), ("tb", share_b, "*.csv")])

    def layers(c):
        # a source's standing word on tb.val: its head line says val and did not withdraw it (the layers live in
        # tb__lines since the overhaul - cell_sources is cold); tb's few columns sit in chunk 0
        return sorted(crud.layer_share(name) for (name,) in c.execute(
            "SELECT l.source_name FROM tb__lines l JOIN line_columns k ON k.table_name = 'tb' AND "
            "k.column_name = 'val' AND k.bit < 64 WHERE (l.head_0 >> k.bit) & 1 = 1 "
            "AND (l.withdrawn_0 >> k.bit) & 1 = 0"))
    _run(tmp_path, db, lambda c: c.execute("SELECT count(*) FROM file_ingestion_logs WHERE table_name = 'tb' "
                                           "AND status = 'SUCCESS'").fetchone()[0] >= 2)
    with sqlite3.connect(str(db)) as c:
        assert c.execute("SELECT val FROM tb").fetchall() == [("same",)]                    # canary: it was read
        two = layers(c)
    assert len(two) == 2 and len(set(two)) == 2 and None not in two, two

    with open(os.path.join(share_a, "d2.csv"), "w", encoding="utf-8") as f:
        f.write("lot\nL1\n")
    _run(tmp_path, db, lambda c: c.execute("SELECT count(*) FROM file_ingestion_logs WHERE table_name = 'tb' "
                                           "AND status = 'SUCCESS'").fetchone()[0] >= 3)
    with sqlite3.connect(str(db)) as c:
        assert layers(c) == two, "the same share saying it again leaves no third layer"
