"""The audit panel's index door (lead 11-11b): without --apply it only reads - a dropped index says «missing» and stays
missing; --apply builds it and the read after says «present». On SQLite it says «not PostgreSQL» and ends."""
import os
import sys

import pytest
import sqlalchemy
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA                                            # noqa: E402
from migrations import add_audit_recent_groups_index as door                  # noqa: E402

NAME = "idx_audit_recent_groups"


def test_on_sqlite_the_door_says_not_postgresql_and_ends(capsys):
    assert door.run(apply=True, url="sqlite:///never_made.db") == {}
    assert "Not PostgreSQL" in capsys.readouterr().out
    assert not os.path.exists("never_made.db")


@pytest.mark.pg
def test_a_missing_index_is_read_as_missing_and_built_by_apply(pg_engine, monkeypatch, capsys):
    real = sqlalchemy.create_engine

    def on_the_scratch_schema(url, **kw):
        """The door's own engines on the test schema - first on the path, as pg_engine's."""
        args = dict(kw.pop("connect_args", {}))
        args["options"] = (args.get("options", "") + " -csearch_path=%s,public" % PG_TEST_SCHEMA).strip()
        return real(url, connect_args=args, **kw)

    monkeypatch.setattr(sqlalchemy, "create_engine", on_the_scratch_schema)
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text('DROP INDEX IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, NAME)))
    url = pg_engine.url.render_as_string(hide_password=False)

    read = door.run(apply=False, url=url)
    assert read == {"idx_audit_row_history": "present", "idx_audit_cell_history": "present", NAME: "missing"}
    assert "--apply" in capsys.readouterr().out
    assert door.run(apply=False, url=url)[NAME] == "missing", "a read builds nothing"

    built = door.run(apply=True, url=url)
    assert set(built.values()) == {"present"}
    assert "building %s" % NAME in capsys.readouterr().out
    assert door.run(apply=False, url=url)[NAME] == "present"
