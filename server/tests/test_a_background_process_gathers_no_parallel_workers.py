"""A background process's connections gather no parallel workers; the API's and its pool children's keep the server's
own (owner 11-06 «stall이 너무 많은데» - the freezes were PostgreSQL's CPU while background statements ran parallel).

Each row opens a new connection on `database.build_engine` as one process would name itself and reads
`SHOW max_parallel_workers_per_gather`. The setting `background_parallel_workers` (ingestion_settings.json): left out
is 0, null leaves every connection the server's own, a number is that number.
"""
import pytest
from sqlalchemy import text

from database import database
from parsers import directory_watcher
from utils import logger

pytestmark = pytest.mark.pg

SERVER_OWN = object()


@pytest.mark.parametrize("process, settings, want", [
    ("Server", {}, SERVER_OWN),
    ("GridPool", {}, SERVER_OWN),
    ("WalkPool", {}, SERVER_OWN),
    ("Chain", {}, "0"),
    ("ChainSlot3", {}, "0"),
    ("Ledger", {}, "0"),
    ("Watcher", {}, "0"),
    ("Scheduler", {}, "0"),
    ("Retroactive", {}, "0"),
    (None, {}, "0"),                                    # a script that named no logger
    ("Chain", {"background_parallel_workers": None}, SERVER_OWN),
    ("Server", {"background_parallel_workers": None}, SERVER_OWN),
    ("Chain", {"background_parallel_workers": 1}, "1"),
    ("Server", {"background_parallel_workers": 1}, SERVER_OWN),
    ("Chain", {"background_parallel_workers": "two"}, "0"),
])
def test_a_new_connection_gathers_as_its_process_role_says(pg_engine, monkeypatch, process, settings, want):
    with pg_engine.connect() as conn:
        server_own = conn.execute(text("SHOW max_parallel_workers_per_gather")).scalar()
    assert server_own not in ("0", "1"), "the test database's own value must differ from what the rows expect"
    monkeypatch.setitem(logger._ACTIVE, "process_name", process)
    monkeypatch.setattr(directory_watcher, "load_ingestion_settings", lambda: dict(settings))
    built = database.build_engine(pg_engine.url.render_as_string(hide_password=False))
    try:
        with built.connect() as conn:
            got = conn.execute(text("SHOW max_parallel_workers_per_gather")).scalar()
            name = conn.execute(text("SHOW application_name")).scalar()
    finally:
        built.dispose()
    assert got == (server_own if want is SERVER_OWN else want), name
