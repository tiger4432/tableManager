# -*- coding: utf-8 -*-
"""총괄 4311a51ed · 12cc7dd1f ② — 표 선언 null_policy: {<키 칸>: "nokey"} 이면, 파일에서 온 행의 빈 키 칸을 제품이
채운다. 🔴 소유자 10-31: 키는 «파일로 입력된 유효 내용 전체의 지문» — nokey_<지문 12 hex>_<행 번호>
(`crud.NokeyPrint`). 지문 = 그 파일 행 전체의 선언된 칸 값(쓰기 문의 정리 꼴, 받지 못한 값은 빈 칸)을 내용 순으로 줄
세운 것의 해시, 번호 = 그 줄의 자리. 표준 파서(F1)는 nokey 칸을 «채워질 칸»으로 세어 그 행을 버리지 않는다.
선언 안 한 표는 한 글자도 안 바뀐다.

  the second file, against the first                          its keys
  the same content, another name                              the same (no new row)
  columns in another order · header spelled in capitals       the same
  rows in another order                                       the same, each row its own
  a column nothing declares, added                            the same
  a plugin's value as the write door stores it («  a » -> a)  the same
  one value different                                         all different (the print moved)
  two equal rows                                              two keys, numbers in a run
  the same content by a plugin's list, not the standard parser   the same
  the same content from another source                        the same - the rows written over
  a file over one chunk, resumed after its first chunk        the keys of the read that was not cut
"""
import os
import re
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import retire_dynamic_model                  # noqa: E402
from database.database import Base                         # noqa: E402
from database import crud, models                          # noqa: E402

T = "nokey_probe"
DECLARED = {"business_key": "k", "composite_key_source": ["lot", "slot"],
            "column_types": {"k": "string", "lot": "string", "slot": "string", "v": "string"},
            "null_policy": {"slot": "nokey"}}
UNDECLARED = {key: value for key, value in DECLARED.items() if key != "null_policy"}
CSV = "lot,slot,v\nL1,,a\nL1,,b\nL1,,c\n"
KEY = re.compile(r"nokey_[0-9a-f]{12}_\d+")


@pytest.fixture(name="load")
def fixture_load(pg_engine, monkeypatch, tmp_path):
    from parsers import directory_watcher as dw
    from parsers.std_parser import parse_std_file
    from ingestion import checkpoint

    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(T)
    models.init_dynamic_models({T: DECLARED})
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
        conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})
        conn.execute(text("DELETE FROM file_ingestion_checkpoints WHERE table_name = :t"), {"t": T})
    Base.metadata.create_all(bind=pg_engine, tables=[models.DYNAMIC_TABLES[T].__table__])
    Session = sessionmaker(bind=pg_engine)
    monkeypatch.setattr(dw, "SessionLocal", Session)
    monkeypatch.setattr(dw.heartbeat, "beat", lambda *a, **k: None)
    handler = dw.IngestionHandler.__new__(dw.IngestionHandler)
    handler.scripts_path = ""
    handler.on_progress_callback = None
    handler.on_refresh_callback = None

    def load(config, signature="sha256:1:aa", with_signature=True, csv=CSV, name="nokey.csv", plugin=False,
             source=None, force_restart=True, listed=None):
        path = tmp_path / name
        path.write_text(csv, encoding="utf-8")
        crud.TABLE_CONFIG[T] = config
        rows, total, _skipped = parse_std_file(str(path), config, T)
        if plugin:                                  # what a plugin's parse() hands over: a list of dicts
            rows, total = [dict(row) for row in rows] if listed is None else listed, None
        plan = None
        if with_signature:
            db = Session()
            try:
                plan = checkpoint.plan_ingestion(db, T, signature, path.name, str(path),
                                                 total if total is not None else len(rows), "std",
                                                 force_restart=force_restart)
            finally:
                db.close()
        line = handler._send_to_upsert(rows, uploader="t", filename=path.name, t_name=T,
                                       total_rows=total, source_name=source,
                                       table_info=config, checkpoint=plan)
        with pg_engine.connect() as conn:
            table = conn.execute(text('SELECT lot, slot, v FROM "%s" ORDER BY v, slot' % T)).all()
        return table, line or ""

    try:
        yield load
    finally:
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(T)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
            conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})
            conn.execute(text("DELETE FROM file_ingestion_checkpoints WHERE table_name = :t"),
                         {"t": T})


def _slots(table):
    return {v: slot for _lot, slot, v in table}


@pytest.mark.pg
def test_three_keyless_rows_get_three_keys_and_a_retry_finds_them(load):
    first, line = load(DECLARED)
    again, _ = load(DECLARED)                       # Retry: the same file

    slots = [slot for _lot, slot, _v in first]
    assert len(first) == 3 and len(set(slots)) == 3
    assert all(KEY.fullmatch(slot) for slot in slots), slots
    assert sorted(int(slot.rsplit("_", 1)[1]) for slot in slots) == [1, 2, 3]
    assert "3 row(s) keyed nokey_... (slot)" in line, line
    assert again == first                           # no new row, the same keys


@pytest.mark.pg
def test_a_file_with_no_nokey_column_at_all_is_loaded_and_filled(load):
    """총괄 d4a949a8c ①: the owner's first case is a file that does not HAVE the column. The
    header check used to require every composite column while the row check already let the
    nokey one go - two answers to 「which key columns must the file bring」."""
    table, line = load(DECLARED, csv="lot,v\nL1,a\nL1,b\n")

    assert [(lot, v) for lot, _slot, v in table] == [("L1", "a"), ("L1", "b")]
    assert all(KEY.fullmatch(slot) for _lot, slot, _v in table), table
    assert "2 row(s) keyed nokey_... (slot)" in line, line


@pytest.mark.pg
def test_an_undeclared_table_still_refuses_a_header_without_its_key(load):
    with pytest.raises(ValueError, match="required key column"):
        load(UNDECLARED, csv="lot,v\nL1,a\n")


@pytest.mark.pg
def test_a_table_that_declares_nothing_is_not_filled(load):
    """Nothing is filled. Since 10-24 a blank key part among filled ones is a part (총괄 242f4a43a): the standard
    parser keeps the row and it lands keyed by the rest, its blank part blank."""
    table, line = load(UNDECLARED)

    assert table == [("L1", None, "c")]
    assert "nokey" not in line


@pytest.mark.pg
def test_a_file_without_a_checkpoint_signature_is_filled_the_same(load):
    """The key is made from the rows, not from the file's signature: «not keyed - no content signature» is gone."""
    signed, _ = load(DECLARED)
    unsigned, line = load(DECLARED, with_signature=False, name="other.csv")

    assert unsigned == signed and "3 row(s) keyed nokey_... (slot)" in line, line


@pytest.mark.parametrize("csv, name", [
    (CSV, "renamed.csv"),
    ("v,slot,lot\na,,L1\nb,,L1\nc,,L1\n", "nokey.csv"),
    ("LOT,Slot,V\nL1,,a\nL1,,b\nL1,,c\n", "nokey.csv"),
    ("lot,slot,v\nL1,,c\nL1,,a\nL1,,b\n", "nokey.csv"),
    ("lot,slot,v,zz\nL1,,a,9\nL1,,b,8\nL1,,c,7\n", "nokey.csv"),
], ids=["another name", "columns reordered", "header in capitals", "rows reordered", "an undeclared column"])
@pytest.mark.pg
def test_what_is_not_the_content_does_not_move_the_keys(load, csv, name):
    first, _ = load(DECLARED)
    second, _ = load(DECLARED, csv=csv, name=name, signature="sha256:1:bb")

    assert second == first, "no new row: each row's content found its key"


@pytest.mark.pg
def test_one_value_different_moves_every_key(load):
    first, _ = load(DECLARED)
    both, _ = load(DECLARED, csv="lot,slot,v\nL1,,a\nL1,,b\nL1,,d\n", signature="sha256:1:bb")

    prints = {slot.split("_")[1] for _l, slot, _v in both}
    assert len(both) == 6 and len(prints) == 2, "a second print: a and b of the second file are new rows too"


@pytest.mark.pg
def test_two_equal_rows_get_two_keys_in_a_run(load):
    table, _ = load(DECLARED, csv="lot,slot,v\nL1,,b\nL1,,a\nL1,,a\n")

    numbers = sorted(int(slot.rsplit("_", 1)[1]) for _l, slot, v in table if v == "a")
    assert len(table) == 3 and numbers[1] == numbers[0] + 1, table


@pytest.mark.pg
def test_a_plugin_s_list_and_the_standard_parser_give_one_content_one_set_of_keys(load):
    by_parser, _ = load(DECLARED)
    by_plugin, line = load(DECLARED, plugin=True, signature="sha256:1:bb")

    assert by_plugin == by_parser and "3 row(s) keyed nokey_... (slot)" in line, line


@pytest.mark.pg
def test_a_value_spelled_as_the_write_door_stores_it_is_the_same_content(load):
    """The print reads each value as the write door casts it: a plugin's «  a », a key as «L1 », are the a and L1
    the table holds."""
    first, _ = load(DECLARED)
    listed = [{"lot": "L1 ", "slot": "", "v": "  a "}, {"LOT": "L1", "v": "b"}, {"lot": "L1", "slot": None, "v": "c"}]
    second, _ = load(DECLARED, plugin=True, listed=listed, signature="sha256:1:bb")

    assert second == first


SPELLED = {"business_key": "k", "composite_key_source": ["lot", "slot"],
           "column_types": {"k": "string", "lot": "string", "slot": "string", "n": "number", "t": "datetime"},
           "null_policy": {"slot": "nokey"}}
TIMES = ["2026-10-29", "2026-10-29 00:00", "2026-10-29 00:00:00", "2026-10-29T00:00:00", "2026-10-28T15:00:00Z"]


def _print(monkeypatch, **cells):
    monkeypatch.setitem(crud.TABLE_CONFIG, T, SPELLED)
    printer = crud.NokeyPrint(T, SPELLED)
    printer.add(dict({"lot": "L1", "slot": "", "n": 1, "t": TIMES[0]}, **cells))
    return printer.keys()[0].split("_")[1]


@pytest.mark.parametrize("cells", [{"n": "1.0"}, {"n": "1.00"}, {"n": 1.0}, {"n": "001"},
                                   {"t": TIMES[1]}, {"t": TIMES[2]}, {"t": TIMES[3]}, {"t": TIMES[4]}],
                         ids=["1.0", "1.00", "float 1.0", "001", *TIMES[1:]])
def test_a_value_the_table_stores_as_one_is_one_print(monkeypatch, cells):
    """lead 10-31 ㄷ: «1.0 and 1, 2026-10-29T00:00:00 and 2026-10-29 are one value» - the print spells each cast value
    by the one key speller (`key_part`)."""
    assert _print(monkeypatch, **cells) == _print(monkeypatch)
    assert _print(monkeypatch, n="007") == _print(monkeypatch, n="7")


def test_another_value_and_a_time_only_postgresql_reads_are_another_print(monkeypatch):
    """The canary (the print does move), and what stays apart: «2026/10/29» is read by PostgreSQL, not by our reader,
    so the first pass has nothing to fold it with (lead 10-31: reported, not built)."""
    assert _print(monkeypatch, n=2) != _print(monkeypatch)
    assert _print(monkeypatch, t="2026-10-30") != _print(monkeypatch)
    assert _print(monkeypatch, t="2026/10/29") != _print(monkeypatch)


def _keys(rows):
    printer = crud.NokeyPrint(T, SPELLED)
    for row in rows:
        printer.add(row)
    return printer.keys(), printer


def test_a_remembered_spelling_is_the_spelling(monkeypatch):
    """lead 10-31: the print remembers (column, value) -> spelling within one file, at most NOKEY_SPELLED_MAX. The
    same file with nothing remembered gives the same keys - one raw value in two columns of two types, 1 and True in
    one column, a value that cannot be a dict key (a plugin's list)."""
    monkeypatch.setitem(crud.TABLE_CONFIG, T, SPELLED)
    rows = [{"lot": "1.0", "n": "1.0", "t": TIMES[1], "k": 1}, {"lot": "1.0", "n": "1.0", "t": TIMES[1], "k": True},
            {"lot": "1", "n": 1, "t": TIMES[3], "k": ["a"]}, {"lot": "1.0", "n": "2", "t": TIMES[1], "k": True}]
    remembered, printer = _keys(rows)
    assert printer.spelled, "CANARY: something was remembered"
    monkeypatch.setattr(crud, "NOKEY_SPELLED_MAX", 0)
    spelled_each_time, printer = _keys(rows)

    assert not printer.spelled and remembered == spelled_each_time


def test_the_print_remembers_no_more_than_its_bound(monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, T, SPELLED)
    rows = [{"lot": "L%d" % at, "n": at, "t": TIMES[0]} for at in range(50)]
    whole, _ = _keys(rows)
    monkeypatch.setattr(crud, "NOKEY_SPELLED_MAX", 7)
    bounded, printer = _keys(rows)

    assert len(printer.spelled) == 7 and bounded == whole


@pytest.mark.pg
def test_another_source_with_the_same_content_writes_the_same_rows(load):
    first, _ = load(DECLARED, source="share-a")
    second, _ = load(DECLARED, source="share-b", signature="sha256:1:bb")

    assert second == first


@pytest.mark.pg
def test_a_file_resumed_after_its_first_chunk_gets_the_keys_of_one_uncut_read(load, pg_engine, monkeypatch):
    rows = ["L1,,v%04d" % (n % 1700) for n in range(2500)]           # 800 equal pairs, across the chunk edge
    csv = "lot,slot,v\n" + "\n".join(rows) + "\n"
    whole, _ = load(DECLARED, csv=csv)
    keys = sorted(slot for _l, slot, _v in whole)
    assert len(keys) == len(set(keys)) == 2500, "CANARY: every row its own key"
    with pg_engine.begin() as conn:
        conn.execute(text('DELETE FROM "%s"' % T))
        conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})
        conn.execute(text("DELETE FROM file_ingestion_checkpoints WHERE table_name = :t"), {"t": T})

    real, calls = crud.apply_batch_updates, []

    def cut(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("the read is cut after its first chunk")
        return real(*args, **kwargs)

    monkeypatch.setattr(crud, "apply_batch_updates", cut)
    with pytest.raises(RuntimeError, match="cut after its first chunk"):
        load(DECLARED, csv=csv)
    with pg_engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM "%s"' % T)).scalar() == 1000, "CANARY: one chunk written"
    monkeypatch.setattr(crud, "apply_batch_updates", real)
    resumed, line = load(DECLARED, csv=csv, force_restart=False)

    assert sorted(slot for _l, slot, _v in resumed) == keys, "the same keys as the read that was not cut"
    assert "1500 row(s) keyed nokey_... (slot)" in line, line
