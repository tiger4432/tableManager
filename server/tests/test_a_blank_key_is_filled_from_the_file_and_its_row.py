# -*- coding: utf-8 -*-
"""총괄 4311a51ed · 12cc7dd1f ② — 표 선언 null_policy: {<키 칸>: "nokey"} 이면, 파일에서 온 행의 빈 키 칸을
nokey_<그 파일의 첫 적재 시각>_<6 hex> 로 채운다. 6 hex = (파일 시그니처의 해시 + 행 번호) mod 16^6 —
무작위가 없어 같은 파일을 Retry 하면 같은 값으로 옛 행을 찾는다. 표준 파서(F1)는 nokey 칸을 «채워질 칸»으로
세어 그 행을 버리지 않는다. 선언 안 한 표는 한 글자도 안 바뀐다.
"""
import os
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
    path = tmp_path / "nokey.csv"
    path.write_text(CSV, encoding="utf-8")

    def load(config, signature="sha256:1:aa", with_signature=True):
        crud.TABLE_CONFIG[T] = config
        rows, total, _skipped = parse_std_file(str(path), config, T)
        plan = None
        if with_signature:
            db = Session()
            try:
                plan = checkpoint.plan_ingestion(db, T, signature, path.name, str(path),
                                                 total, "std", force_restart=True)
            finally:
                db.close()
        line = handler._send_to_upsert(rows, uploader="t", filename=path.name, t_name=T,
                                       total_rows=total,
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


@pytest.mark.pg
def test_three_keyless_rows_get_three_keys_and_a_retry_finds_them(load):
    first, line = load(DECLARED)
    again, _ = load(DECLARED)                       # Retry: the same file

    slots = [slot for _lot, slot, _v in first]
    assert len(first) == 3 and len(set(slots)) == 3
    assert all(slot.startswith("nokey_") and len(slot.rsplit("_", 1)[1]) == 6 for slot in slots)
    assert "3 row(s) keyed nokey_... (slot)" in line, line
    assert again == first                           # no new row, the same keys


@pytest.mark.pg
def test_the_same_row_of_another_file_gets_another_key(load):
    first, _ = load(DECLARED, signature="sha256:1:aa")
    both, _ = load(DECLARED, signature="sha256:1:bb")

    assert len(both) == 6
    assert not {s for _l, s, _v in first} & ({s for _l, s, _v in both} - {s for _l, s, _v in first})
    assert len({s for _l, s, _v in both}) == 6


@pytest.mark.pg
def test_a_table_that_declares_nothing_is_not_filled(load):
    """As before: the standard parser (F1) skips a row without its key - nothing reaches the door."""
    table, line = load(UNDECLARED)

    assert table == []
    assert "nokey" not in line


@pytest.mark.pg
def test_a_file_without_a_signature_is_not_filled_and_says_why(load):
    table, line = load(DECLARED, with_signature=False)

    assert all(slot is None for _lot, slot, _v in table)
    assert "3 row(s) not keyed nokey (slot)" in line, line


def test_the_value_is_the_file_the_row_and_the_first_load_nothing_random():
    from datetime import datetime, timezone
    at = datetime(2026, 9, 30, 5, 15, 3, tzinfo=timezone.utc)
    one = crud.nokey_value("sha256:1:aa", at, 1)

    assert one == crud.nokey_value("sha256:1:aa", at, 1)
    assert one.startswith("nokey_20260930T051503Z_")
    assert len({crud.nokey_value("sha256:1:aa", at, row) for row in range(1, 20001)}) == 20000
    assert crud.nokey_value("sha256:1:bb", at, 1) != one
