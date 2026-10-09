# -*- coding: utf-8 -*-
"""총괄 72f419bd1 (소유자 「ㅇㅇ 은퇴해」): `run_in: operation` is retired - a rule runs in the chain group
alone. A slow rule (an LLM) writes `rows_per_run: 1`, and the chain's one row-budget cut takes one
text a group, so a wrong answer fails that text only. An old declaration still carrying `run_in` loads,
runs in the chain, and is told once; no `rule_rows` run is queued.

⚰️ `test_a_rule_can_run_as_an_operation.py` (총괄 be0abe305) stood before this - its fixtures are here.
"""
import asyncio
import json
import logging
import os
import sys
import textwrap

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                                 # noqa: E402
import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
import paths                                                          # noqa: E402
from admin import retroactive                                         # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import rule_order                                          # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel, outbox_mode                     # noqa: E402
from database.database import Base                                    # noqa: E402
from utils import heartbeat                                           # noqa: E402

TABLES = {name: {"business_key": "k", "composite_key_source": ["k"],
                 "column_types": {"k": "string", "n": "string"}, "display_columns": ["k", "n"]}
          for name in ("q_txt", "q_cand")}
MAPPERS = """
def _rows(payload):
    handed = payload if isinstance(payload, list) else [payload]
    for p in handed:
        data = p.get("data") or {}
        yield (data.get("k") or {}).get("value"), (data.get("n") or {}).get("value")

def fast(db, payload, rule=None):
    return {"updates": [{"business_key_val": k, "updates": {"k": k, "n": "from " + str(n)}}
                        for k, n in _rows(payload)]}

def picky(db, payload, rule=None):
    rows = list(_rows(payload))
    if any(n == "two" for _k, n in rows):
        raise ValueError("this mapper cannot read text two")
    return fast(db, payload, rule)
"""
TEXTS = [{"k": "t1", "n": "one"}, {"k": "t2", "n": "two"}, {"k": "t3", "n": "three"}]


class _NoClose:
    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


async def _no_post(_endpoint, _payload):
    return True


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path / "beats"))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(tmp_path / "beats" / (name + ".json")))
    monkeypatch.setattr(worker, "post_event_async", _no_post)
    mapper_sdk.discover()
    (tmp_path / "q_maps.py").write_text(textwrap.dedent(MAPPERS), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("q_maps", None)
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
        sys.modules.pop("q_maps", None)


def _rule(name, trigger, target, function, **cells):
    return {"name": name, "enabled": True, "is_batch": True, "trigger_table": trigger,
            "target_table": target, "mapper_module": "q_maps", "mapper_function": function,
            "allow_chain_trigger": False, **cells}


def _write(db, table, rows):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="q") for row in rows]))
        db.commit()


def _values(db, table):
    return sorted((r.k, r.n) for r in db.query(models.DYNAMIC_TABLES[table]).all())


def _pending(db):
    return (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.processed_chain.is_(False),
                    models.DatabaseOutbox.table_name.in_(list(TABLES)))
            .order_by(models.DatabaseOutbox.id).all())


def _drain_all(db, rules, monkeypatch, rounds=30):
    """The chain's batch body (`drain_events` - the row budget, the groups, their retries) until
    nothing of these tables waits; -> the batches it took."""
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: list(rules))
    batches = 0
    for _ in range(rounds):
        pending = _pending(db)
        if not pending:
            return batches
        asyncio.run(worker.drain_events(db, pending, rules, None))
        batches += 1
    return batches


def _rule_rows_runs(db):
    return db.query(models.RetroactiveRun).filter(models.RetroactiveRun.op == retroactive.RULE_ROWS_OP).count()


def test_one_text_a_group_and_a_wrong_answer_fails_that_text_only(db, monkeypatch):
    rules = [_rule("q_llm", "q_txt", "q_cand", "picky", rows_per_run=1)]
    _write(db, "q_txt", TEXTS)                              # one transaction, one event a text
    _drain_all(db, rules, monkeypatch)
    assert _values(db, "q_cand") == [("t1", "from one"), ("t3", "from three")]
    assert _rule_rows_runs(db) == 0


def test_without_rows_per_run_the_three_texts_share_a_group(db, monkeypatch):
    """The control: the transaction is one group, so the wrong text fails all three - the cut above is
    what isolates."""
    rules = [_rule("q_llm", "q_txt", "q_cand", "picky")]
    _write(db, "q_txt", TEXTS)
    _drain_all(db, rules, monkeypatch)
    assert _values(db, "q_cand") == []


def test_an_old_run_in_declaration_loads_runs_in_the_chain_and_is_told_once(db, monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [_rule("q_old", "q_txt", "q_cand", "fast", run_in="operation",
                                                 rows_per_run=1)]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    monkeypatch.setattr(rule_order, "_SAID_FOR", None)
    rules = worker.load_chain_rules()
    worker.say_the_declaration()
    worker.load_chain_rules()
    worker.say_the_declaration()                             # the same declaration: nothing more
    said = [r.getMessage() for r in caplog.records if "run_in is retired" in r.getMessage()]
    assert said == ["[ChainRules] q_old: run_in is retired - this rule runs in the chain; rows_per_run "
                    "splits its groups"]
    _write(db, "q_txt", TEXTS[:1])
    _drain_all(db, [r for r in rules if r.get("name") == "q_old"], monkeypatch)
    assert _values(db, "q_cand") == [("t1", "from one")]
    assert _rule_rows_runs(db) == 0


@pytest.mark.parametrize("caps,kept", [
    ([None, 1, None], 1),          # an uncapped event first: the capped one waits for a batch of its own
    ([1, None, None], 1),          # a capped event first: the batch holds to its cap
    ([None, None, None], 3),       # nobody declared: today's budget
])
def test_the_batch_keeps_to_the_smallest_cap_of_what_it_holds(caps, kept):
    events = list(range(len(caps)))
    out = event_constants.trim_events_to_row_budget(
        events, 1000, payload_of=lambda e: {"row_id": "r%d" % e}, cap_of=lambda e: caps[e])
    assert len(out) == kept


@pytest.mark.parametrize("cells,code", [
    ({"run_in": "later"}, "bad_run_in"),
    ({"rows_per_run": 0}, "bad_rows_per_run"),
    ({"rows_per_run": "6"}, "bad_rows_per_run"),
])
def test_a_bad_cell_is_refused_at_load(cells, code):
    issues = chain_bindings.rule_refusals(
        _rule("q", "q_txt", "q_cand", "fast", **cells), "rules[0]",
        mapper_resolvable=lambda _name: True, derived_tables=())
    assert code in {issue.code for issue in issues}


def test_rows_per_run_not_written_is_no_cut_and_the_form_offers_no_run_in():
    assert worker.rows_per_run({}) is None and worker.rows_per_run({"rows_per_run": 1}) == 1
    assert chain_bindings.RUN_IN_KEY in chain_bindings.routing_keys()          # still read
    assert chain_bindings.RUN_IN_KEY not in json.dumps(chain_bindings.skeleton())   # offered by no form
