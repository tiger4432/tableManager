# -*- coding: utf-8 -*-
"""Owner 10-23 «a 표에서 b 표 값을 가져오는데 spec 표의 spec 으로 참조해서 s/o 여부를 판정» (lead f14181fbd · 650a23f9c): a
join take's `fn` names «<file>.<function>» of server/mappers/join_fn/, called a key with f(values, row, ref) - the key's
source values (blanks out), the target row's join key and `row` columns, and the `ref` tables whole, read once a batch.
The functions are the shipped sample's (spec_out.py.sample), copied into this test's folder. The chain here is its
batch body (`drain_events`) over the rules the loader stands from the declaration.

  source rows come and go   S/O and the spec's fingerprint written a key
  a target row arrives      or its `row` column changes - judged again
  one batch                 the spec table read once, whichever takes name it
  the spec table changes    nothing is judged again by itself - a replay is
  refused                   a file, a function, a ref table, a row column; ref and row on one of the four
"""
import asyncio
import json
import os
import shutil
import sys

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
import paths                                                          # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import join_into, replay, rule_shape                       # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel, outbox_mode                     # noqa: E402
from database.database import Base                                    # noqa: E402
from utils import heartbeat                                           # noqa: E402

SAMPLE = os.path.join(SERVER_DIR, "mappers", "join_fn", "spec_out.py.sample")
TABLES = {"jf_meas": {"business_key": "rid", "composite_key_source": ["rid"],
                      "column_types": {"rid": "string", "lot": "string", "item": "string", "v": "number"},
                      "display_columns": ["rid", "lot", "item", "v"]},
          "spec": {"business_key": "sid", "composite_key_source": ["sid"],
                   "column_types": {"sid": "string", "item": "string", "grade": "string", "lower": "number",
                                    "upper": "number"},
                   "display_columns": ["sid", "item", "grade", "lower", "upper"]},
          "jf_tgt": {"business_key": "tid", "composite_key_source": ["tid"],
                     "column_types": {"tid": "string", "lot": "string", "item": "string", "grade": "string",
                                      "so": "string", "spec_ver": "string"},
                     "display_columns": ["tid", "lot", "item", "grade", "so", "spec_ver"]}}
TAKE = [{"from": "v", "into": "so", "fn": "spec_out.s_o", "ref": ["spec"], "row": ["grade"]},
        {"from": "v", "into": "spec_ver", "fn": "spec_out.spec_hash", "ref": ["spec"]}]
SPEC_ROWS = [{"sid": "s1", "item": "A", "grade": "g1", "lower": 0, "upper": 10},
             {"sid": "s2", "item": "B", "grade": "g1", "lower": 0, "upper": 5},
             {"sid": "s3", "item": "A", "grade": "g2", "lower": 0, "upper": 3}]


def _declaration(take):
    return {"name": "jf", "on": {"table": "jf_meas"}, "into": {"table": "jf_tgt"},
            "derive": {"kind": "join", "join": {"on": [{"left": "lot", "right": "lot"},
                                                       {"left": "item", "right": "item"}], "take": take}}}


class _NoClose:
    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


async def _no_post(_endpoint, _payload):
    return True


@pytest.fixture(name="functions")
def fixture_functions(tmp_path, monkeypatch):
    folder = tmp_path / "join_fn"
    folder.mkdir()
    shutil.copy(SAMPLE, folder / "spec_out.py")
    monkeypatch.setattr(join_into, "JOIN_FN_DIR", str(folder))
    return folder


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch, functions):
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path / "beats"))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(tmp_path / "beats" / (name + ".json")))
    monkeypatch.setattr(worker, "post_event_async", _no_post)
    mapper_sdk.discover()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoClose(session))
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _rules(tmp_path, monkeypatch, take=TAKE):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [_declaration(take)]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    rules = [r for r in worker.load_chain_rules() if str(r.get("name") or "").startswith("jf")]
    assert len(rules) == 2, "the declaration stood both halves - else this measures nothing"
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: list(rules))
    return rules


def _drain(db, rules):
    for _ in range(40):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        asyncio.run(worker.drain_events(db, pending, rules, None))
    raise AssertionError("the chain did not settle")


def _put(db, table, rows, collapsed=False):
    """`collapsed`: the events say which columns changed (a file's or a bulk write's) - a rule watching columns
    reads them; a row-by-row event says none and wakes every rule on its table."""
    with channel(event_constants.CHANNEL_API), outbox_mode(
            event_constants.OUTBOX_MODE_COLLAPSED if collapsed else event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="jf") for row in rows]))
        db.commit()


def _judged(db):
    db.expire_all()
    return {(r.lot, r.item): (r.so, r.spec_ver) for r in db.query(models.DYNAMIC_TABLES["jf_tgt"]).all()}


def _spec_hash(rows):
    function, why = join_into.take_function("spec_out.spec_hash")
    assert why is None, why
    return function([], {}, {"spec": rows})


def _seed(db):
    _put(db, "spec", SPEC_ROWS)
    _put(db, "jf_tgt", [{"tid": "t1", "lot": "L1", "item": "A", "grade": "g1"},
                        {"tid": "t2", "lot": "L1", "item": "B", "grade": "g1"},
                        {"tid": "t3", "lot": "L2", "item": "A", "grade": "g2"}])


def test_each_key_is_judged_by_the_function_against_the_spec_and_the_target_row(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch)
    _seed(db)
    _drain(db, rules)
    _put(db, "jf_meas", [{"rid": "m1", "lot": "L1", "item": "A", "v": 3}, {"rid": "m2", "lot": "L1", "item": "A", "v": 7},
                         {"rid": "m3", "lot": "L1", "item": "B", "v": 2}, {"rid": "m4", "lot": "L1", "item": "B", "v": 6},
                         {"rid": "m5", "lot": "L2", "item": "A", "v": 2}])
    _drain(db, rules)
    ver = _spec_hash([{**row, "lower": float(row["lower"]), "upper": float(row["upper"])} for row in SPEC_ROWS])
    assert _judged(db) == {("L1", "A"): ("OK", ver), ("L1", "B"): ("S/O", ver), ("L2", "A"): ("OK", ver)}
    # a source row comes: its key is judged again
    _put(db, "jf_meas", [{"rid": "m6", "lot": "L2", "item": "A", "v": 4}])
    _drain(db, rules)
    assert _judged(db)[("L2", "A")] == ("S/O", ver), "4 is past grade g2's upper 3"
    # the target row's `row` column changes - an event that names its changed column: judged against the other spec row
    _put(db, "jf_tgt", [{"tid": "t3", "grade": "g1"}], collapsed=True)
    _drain(db, rules)
    assert _judged(db)[("L2", "A")] == ("OK", ver), "grade g1's upper is 10"
    # a target row arrives after its key's source rows
    _put(db, "jf_meas", [{"rid": "m7", "lot": "L3", "item": "B", "v": 9}])
    _put(db, "jf_tgt", [{"tid": "t4", "lot": "L3", "item": "B", "grade": "g1"}])
    _drain(db, rules)
    assert _judged(db)[("L3", "B")] == ("S/O", ver)


def test_one_batch_reads_the_spec_table_once_for_both_takes(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch)
    _seed(db)
    _drain(db, rules)
    reads = []
    engine = db.get_bind()

    def count(_conn, _cursor, statement, *_rest):
        if 'FROM spec' in statement:
            reads.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        _put(db, "jf_meas", [{"rid": "m1", "lot": "L1", "item": "A", "v": 3},
                             {"rid": "m3", "lot": "L1", "item": "B", "v": 2},
                             {"rid": "m5", "lot": "L2", "item": "A", "v": 2}])
        reads.clear()
        _drain(db, rules)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    judged = _judged(db)
    assert all(so for so, _ver in judged.values()) and len(judged) == 3, "three keys in the batch - else this measures nothing"
    assert len(reads) == 1, reads


def test_a_changed_spec_is_judged_again_only_by_a_replay(db, tmp_path, monkeypatch):
    rules = _rules(tmp_path, monkeypatch)
    _seed(db)
    _put(db, "jf_meas", [{"rid": "m5", "lot": "L2", "item": "A", "v": 2}])
    _drain(db, rules)
    before = _judged(db)[("L2", "A")]
    assert before[0] == "OK"
    _put(db, "spec", [{"sid": "s3", "upper": 1}])
    _drain(db, rules)
    assert _judged(db)[("L2", "A")] == before, "the spec table is no source of this join"
    value_side = next(r for r in rules if r.get("trigger_table") == "jf_meas")
    replay.replay_rule(db, value_side, apply=True, log=lambda m: None)
    _drain(db, rules)
    after = _judged(db)[("L2", "A")]
    assert after[0] == "S/O" and after[1] != before[1], (before, after)


@pytest.mark.parametrize("take,words", [
    ([{"from": "v", "into": "so", "fn": "nofile.s_o"}], "of a file in"),
    ([{"from": "v", "into": "so", "fn": "spec_out.missing"}], "has no function 'missing'"),
    ([{"from": "v", "into": "so", "fn": "spec_out.s_o", "ref": ["nosuch"]}], "ref 'nosuch' - not a table"),
    ([{"from": "v", "into": "so", "fn": "spec_out.s_o", "row": ["nosuch"]}], "row 'nosuch' - not a column of jf_tgt"),
    ([{"from": "v", "into": "so", "fn": "max", "ref": ["spec"]}], "ref and row are a function's"),
])
def test_a_function_take_that_cannot_stand_is_refused_by_name(db, take, words):
    _rules_, refusal, _notes = rule_shape.expand_declaration(_declaration(take))
    assert refusal is not None and words in refusal, refusal


def test_the_declarations_screen_offers_the_folders_functions(functions, client):
    from ledger import admin

    offered = admin._chain_lists()[join_into.TAKE_FN_LIST]
    assert offered[:4] == ["count", "min", "max", "unique_concat"]
    assert offered[4:] == ["spec_out.s_o", "spec_out.spec_hash"]
    # the Editor's Mappers list opens the file
    listed = client.get("/admin/scripts/list").json()["data"]["mappers"]
    assert {"filename": "join_fn/spec_out.py", "path": "mappers/join_fn/spec_out.py", "type": "mapper"} in listed
