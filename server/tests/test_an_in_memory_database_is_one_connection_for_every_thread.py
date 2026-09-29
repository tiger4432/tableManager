# -*- coding: utf-8 -*-
"""총괄 76aa4b6ed ① — sqlite :memory: 일 때만 한 연결을 모든 스레드가 나눈다(StaticPool).

기본 풀은 스레드마다 연결 하나(그 하나하나가 따로인 빈 DB)이고 다섯을 넘으면 아무거나 닫는다 —
스키마를 든 연결이 닫히면 다음 시험이 표를 잃었다(파일 순서 그대로 재현, 이분). PostgreSQL 과
파일 sqlite 는 전과 같은 풀이다.
"""
import os
import sys
import threading

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import database                                         # noqa: E402

PG_URL = "postgresql://user:secret@127.0.0.1:5999/not_a_database"


def _from_another_thread(engine, sql):
    out = {}

    def run():
        try:
            with engine.connect() as conn:
                out["rows"] = conn.execute(text(sql)).fetchall()
        except Exception as exc:                                    # noqa: BLE001
            out["error"] = "%s: %s" % (type(exc).__name__, exc)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    return out


def test_postgres_builds_the_pool_it_built_before():
    before = create_engine(PG_URL, pool_size=20, max_overflow=10, pool_recycle=3600,
                           connect_args={"options": "-c client_encoding=utf8"})
    now = database.build_engine(PG_URL)
    assert type(now.pool) is type(before.pool)
    assert (now.pool.size(), now.pool._max_overflow) == (before.pool.size(), 10)


def test_a_file_sqlite_builds_the_pool_it_built_before_and_crosses_threads(tmp_path):
    url = "sqlite:///%s" % (tmp_path / "file.db").as_posix()
    before = create_engine(url, connect_args={"check_same_thread": False})
    now = database.build_engine(url)
    assert type(now.pool) is type(before.pool)

    with now.connect() as conn:                     # made on this thread, back to the pool
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
        conn.commit()
    # ⚠️ Crosses threads as before. It cannot see `check_same_thread`: SQLAlchemy turns it
    #    off for a file database by itself (measured - the flag removed stayed green here, red
    #    in the in-memory cell below).
    assert _from_another_thread(now, "SELECT count(*) FROM t") == {"rows": [(0,)]}


def test_in_memory_every_thread_sees_the_one_database():
    engine = database.build_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
        conn.execute(text("INSERT INTO t VALUES (1)"))
        conn.commit()

    for _ in range(8):                              # past the old pool's five threads
        assert _from_another_thread(engine, "SELECT x FROM t") == {"rows": [(1,)]}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT x FROM t")).fetchall() == [(1,)]
