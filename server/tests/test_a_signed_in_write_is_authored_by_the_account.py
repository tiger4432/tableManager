# -*- coding: utf-8 -*-
"""Lead 11-06 (owner, SSO in production): every write door takes its author from `sso.who` - the signed-in name, else
what the caller stated. The client states «web_client» on every edit, so every person layer and history line said so.

  doors      PUT data/updates · POST rows · DELETE rows/{id} · POST rows/batch_delete · PUT {row}/{col}/priority ·
             PUT cells/priority/batch
  sign-in    on: the account's name in the layer and the audit line · off: what the body said, as before
  canary     each door left its line (audit, or the pin's overwrite row) - an empty read would pass by being empty
"""
import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

from database import crud, models

pytestmark = pytest.mark.pg
TABLE = "sso_author_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"], "column_types": {"k": "string", "v": "string"}}
ACCOUNT = "kim@corp.test"
STATED = "web_client"


@pytest.fixture
def grid(pg_engine, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    from admin import sso
    from conftest import PG_TEST_SCHEMA
    from database.database import get_db

    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()

    async def broadcast(message):
        return None
    monkeypatch.setattr(main.manager, "broadcast", broadcast)
    signed = {"on": False}

    def admit(request):
        request.state.sso_user = ACCOUNT
    monkeypatch.setattr(sso, "enabled", lambda: signed["on"])
    monkeypatch.setattr(sso, "admit", admit)
    main.app.dependency_overrides[get_db] = lambda: session
    try:
        with TestClient(main.app) as client:
            yield client, signed, pg_engine, PG_TEST_SCHEMA
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        session.close()
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
            for table in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
                conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, table)), {"t": TABLE})


def _ids(engine, schema):
    with engine.connect() as conn:
        return dict(conn.execute(text('SELECT k, row_id FROM "%s"."%s"' % (schema, TABLE))).fetchall())


def _authors(engine, schema, sql):
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(text(sql % schema), {"t": TABLE})]


@pytest.mark.parametrize("on", [True, False])
def test_every_write_door_names_the_signed_in_account(grid, on):
    client, signed, engine, schema = grid
    signed["on"] = on
    want = ACCOUNT if on else STATED
    doors, ids = {}, {}

    def door(name, response, where="audit_logs WHERE table_name = :t ORDER BY id DESC LIMIT 1"):
        assert response.status_code == 200, (name, response.status_code, response.text[:200])
        with engine.connect() as conn:
            doors[name] = [r[0] for r in conn.execute(text(
                'SELECT updated_by FROM "%s".' % schema + where), {"t": TABLE, "r": ids.get(name)})]
            conn.execute(text('DELETE FROM "%s".audit_logs WHERE table_name = :t' % schema), {"t": TABLE})
            conn.commit()

    door("updates", client.put("/tables/%s/data/updates" % TABLE, json={"updates": [
        {"updates": {"k": k, "v": "x"}, "source_name": "user", "updated_by": STATED} for k in ("a", "b", "c")]}))
    assert set(_authors(engine, schema, 'SELECT updated_by FROM "%s".cell_sources WHERE table_name = :t')) == {want}
    ids.update(_ids(engine, schema))
    pinned = "cell_overwrites WHERE table_name = :t AND row_id = :r"           # a pin writes no audit line
    ids["pin"], ids["pin batch"] = ids["a"], ids["b"]
    door("pin", client.put("/tables/%s/%s/v/priority" % (TABLE, ids["a"]),
                           json={"source_name": "user", "updated_by": STATED}), pinned)
    door("pin batch", client.put("/tables/%s/cells/priority/batch" % TABLE, json={
        "updates": [{"row_id": ids["b"], "column_name": "v"}], "source_name": "user", "updated_by": STATED}), pinned)
    door("create", client.post("/tables/%s/rows" % TABLE, params={"count": 1, "user_name": STATED}))
    door("delete", client.delete("/tables/%s/rows/%s" % (TABLE, ids["a"]), params={"user_name": STATED}))
    door("batch delete", client.post("/tables/%s/rows/batch_delete" % TABLE,
                                     json={"row_ids": [ids["b"]], "user_name": STATED}))
    assert {name: said for name, said in doors.items() if not said or set(said) != {want}} == {}, doors
