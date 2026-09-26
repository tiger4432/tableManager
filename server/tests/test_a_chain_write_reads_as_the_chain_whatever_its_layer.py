"""A chain write reads as the chain whatever layer it wrote under (총괄 5676b8bc6 ⓪ · f42b48591 ·
c2995cdd8 · 146b208cb).

Production 09-26: a replay of a decide rule auto-confirmed in bulk, the join on that table woke
without its opt-in, and the chain went round for an hour. The auto-confirm write left under its
LAYER name (`enrichment_auto_confirm`) - crud's batch door copies the item's layer onto the
envelope - and the one reader asked `source_name == "chain_ingestion"`. The envelope now says
the CHANNEL beside the layer, and the reader asks that:

  chain        wakes only the opted-in rules, and the depth ceiling bounds them
  api · file   wake every rule, as before
  retroactive  wakes nothing, opted in or not - unless the replay asked to cascade
  (none)       an event queued before the channel: read by its source name, and counted
"""
import os
import sys
import textwrap
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
from admin import retroactive                                         # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import replay, rule_shape                                  # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel                                  # noqa: E402
from database.database import Base                                    # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

SRC, DST = "pp_log", "pp_attr"          # the decide reads SRC into DST, the join DST into SRC
PA, PB = "pp_a", "pp_b"                 # two file mappers that write each other's table
TABLES = {
    SRC: {"business_key": "log_key", "composite_key_source": ["log_key"],
          "column_types": {"log_key": "string", "job": "string", "grade_seen": "string"},
          "display_columns": ["log_key", "job", "grade_seen"]},
    DST: {"business_key": "job", "composite_key_source": ["job"],
          "column_types": {"job": "string", "lot": "string", "grade": "string"},
          "display_columns": ["job", "lot", "grade"]},
    PA: {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "n": "string"}, "display_columns": ["k", "n"]},
    PB: {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "n": "string"}, "display_columns": ["k", "n"]},
}

#: Writes the other table's row with n + 1, under a layer that is NOT `chain_ingestion` - the
#: shape of the auto-confirm write, for any mapper that names its own layer.
BUMP = """
def bump(db, payload, rule=None):
    handed = payload if isinstance(payload, list) else [payload]
    out = []
    for p in handed:
        data = p.get("data") or {}
        k = (data.get("k") or {}).get("value")
        n = int((data.get("n") or {}).get("value") or 0)
        out.append({"business_key_val": k, "source_name": "pp_layer",
                    "updates": {"k": k, "n": str(n + 1)}})
    return {"updates": out}
"""


class _NoClose:
    """The test session handed to `retroactive.execute`, which closes what it opens."""

    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    mapper_sdk.discover()
    (tmp_path / "pp_bump.py").write_text(textwrap.dedent(BUMP), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("pp_bump", None)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoClose(session))
    monkeypatch.setattr(worker, "_READ_BY_SOURCE_NAME", set())
    # A run announces its progress to the API over HTTP; a test must not reach a live one.
    monkeypatch.setattr(retroactive, "announce_progress", lambda *a, **k: None)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
        sys.modules.pop("pp_bump", None)


def _write(db, table, rows, on=event_constants.CHANNEL_API, layer="seed"):
    with channel(on):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name=layer, updated_by="pp")
            for row in rows]))
        db.commit()


def _pending(db):
    return (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.processed_chain.is_(False))
            .order_by(models.DatabaseOutbox.id).all())


def _finish(db, events):
    for event in events:
        event_constants.mark_processed(event, "SUCCESS")
    db.commit()


def _drain(db, rules, max_depth=event_constants.DEFAULT_MAX_CHAIN_DEPTH, rounds=80):
    """The worker's loop in miniature: what is pending, refused past the ceiling, grouped by
    transaction and run through the product's own group body - until nothing is pending."""
    refused = []
    for _ in range(rounds):
        pending = _pending(db)
        if not pending:
            return refused
        groups = {}
        for event in pending:
            payload = get_payload_dict(event)
            depth = event_constants.chain_depth_of(payload)
            if depth is not None and depth > max_depth:
                event_constants.mark_processed(event, "FAILED")
                refused.append(depth)
                continue
            groups.setdefault(payload.get("transaction_id"), []).append(event)
        db.commit()
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, rules)
            assert ok, error
            _finish(db, events)
    raise AssertionError("the chain did not settle in %d rounds" % rounds)


def _values(db, table, column):
    model = models.DYNAMIC_TABLES[table]
    return sorted(getattr(r, column) or "" for r in db.query(model).all())


def _events(db, table):
    return [get_payload_dict(e) for e in db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == table).order_by(models.DatabaseOutbox.id)]


def _decide_and_join(join_opts_in):
    decide = rule_shape.expand_declaration(
        {"name": "pp_decide", "on": {"table": SRC}, "into": {"table": DST},
         "derive": {"kind": "decide", "decide": {
             "key": ["job"], "fields": ["grade"], "auto_confirm": True,
             "reference_views": [{"label": "c",
                                  "query": "SELECT lot AS grade FROM %s WHERE job = :job" % DST,
                                  "candidate_for": {"grade": "grade"}}]}}},
        crud.TABLE_CONFIG)[0]
    join = [r for r in rule_shape.expand_declaration(
        {"name": "pp_join", "on": {"table": DST}, "into": {"table": SRC},
         "derive": {"kind": "join", "join": {"on": [{"left": "job", "right": "job"}],
                                             "take": [{"from": "grade",
                                                       "into": "grade_seen"}]}}},
        crud.TABLE_CONFIG)[0] if r.get("trigger_table") == DST]
    for rule in join:
        rule["allow_chain_trigger"] = join_opts_in
    return decide + join


def _bumpers(opt_in):
    def rule(name, trigger, target):
        return {"name": name, "enabled": True, "is_batch": True, "trigger_table": trigger,
                "target_table": target, "mapper_module": "pp_bump",
                "mapper_function": "bump", "allow_chain_trigger": opt_in}
    return [rule("pp_a_to_b", PA, PB), rule("pp_b_to_a", PB, PA)]


# ------------------------------------------------------------------ the auto-confirm door

@pytest.mark.parametrize("opts_in", [False, True])
def test_an_auto_confirm_write_asks_the_join_for_its_opt_in(db, opts_in):
    _write(db, DST, [{"job": "J", "lot": "LOT"}])
    _write(db, SRC, [{"log_key": "L%d" % n, "job": "J"} for n in range(3)])
    _finish(db, [e for e in _pending(db) if e.table_name == SRC])

    _drain(db, _decide_and_join(opts_in))

    confirmed = [p for p in _events(db, DST) if p.get("source_name") == "enrichment_auto_confirm"]
    assert confirmed, "the fixture no longer auto-confirms, so the join's answer means nothing"
    assert {p.get(event_constants.CHANNEL_KEY) for p in confirmed} == {"chain"}
    assert _values(db, DST, "grade") == ["LOT"]
    assert _values(db, SRC, "grade_seen") == (["LOT"] * 3 if opts_in else [""] * 3)


def test_opted_in_the_ping_pong_climbs_to_the_ceiling_and_stops(db):
    _write(db, PA, [{"k": "K", "n": "0"}])

    refused = _drain(db, _bumpers(opt_in=True), max_depth=4)

    written = [p for p in _events(db, PA) + _events(db, PB)
               if p.get("source_name") == "pp_layer"]
    assert sorted(p[event_constants.CHAIN_DEPTH_KEY] for p in written) == [1, 2, 3, 4, 5]
    assert {p.get(event_constants.CHANNEL_KEY) for p in written} == {"chain"}
    assert refused == [5], "one event past the ceiling, refused once"


def test_without_the_opt_in_the_ping_pong_takes_one_step(db):
    _write(db, PA, [{"k": "K", "n": "0"}])

    _drain(db, _bumpers(opt_in=False))

    assert _values(db, PB, "n") == ["1"] and _values(db, PA, "n") == ["0"]


# --------------------------------------------------------------- the other channels

@pytest.mark.parametrize("on", [event_constants.CHANNEL_API, event_constants.CHANNEL_FILE])
def test_a_person_and_a_file_wake_every_rule_as_before(db, on):
    _write(db, PA, [{"k": "K", "n": "0"}], on=on)

    _drain(db, _bumpers(opt_in=False))

    assert _values(db, PB, "n") == ["1"]


def test_an_event_queued_before_the_channel_is_read_by_its_source_name_and_counted(db):
    _write(db, PA, [{"k": "K", "n": "0"}], on=None, layer="chain_ingestion")
    [event] = _pending(db)
    assert event_constants.CHANNEL_KEY not in get_payload_dict(event)
    closed, opted = _bumpers(opt_in=False)[0], _bumpers(opt_in=True)[0]

    assert not worker.fires(closed, event) and worker.fires(opted, event)
    assert worker._READ_BY_SOURCE_NAME == {event.id}
    assert "1 event(s) read by source name (no channel)" in worker._worker_note()


@pytest.mark.parametrize("cascade", [False, True])
def test_a_retroactive_write_wakes_no_rule_unless_its_replay_cascades(db, cascade):
    _write(db, PA, [{"k": "K", "n": "0"}], on=event_constants.CHANNEL_RETROACTIVE)
    [event] = _pending(db)
    event.payload = dict(get_payload_dict(event),
                         **({event_constants.CASCADE_KEY: True} if cascade else {}))
    event._parsed_payload = event.payload
    closed, opted = _bumpers(opt_in=False)[0], _bumpers(opt_in=True)[0]

    assert not worker.fires(closed, event)
    assert worker.fires(opted, event) is cascade


# -------------------------------------------------- the one seat every retroactive run passes

@pytest.mark.parametrize("cascade", [False, True])
def test_a_replay_runs_its_rule_and_its_writes_wake_the_downstream_only_when_asked(
        db, monkeypatch, cascade):
    _write(db, PA, [{"k": "K", "n": "0"}])
    _finish(db, _pending(db))
    rules = _bumpers(opt_in=True)
    monkeypatch.setattr(replay, "load_rules", lambda: rules)

    out = retroactive.execute(
        {"run_id": "pp", "op": "chain_replay",
         "params": dict({"rule": "pp_a_to_b"}, **({"cascade": True} if cascade else {}))},
        log=lambda m: None)
    assert out["status"] == "ok", out["error"]
    staged = _pending(db)
    assert staged and all(event_constants.channel_of(get_payload_dict(e)) is None
                          and event_constants.only_rule_of(get_payload_dict(e)) == "pp_a_to_b"
                          and event_constants.replay_of(get_payload_dict(e))
                          for e in staged), "a trigger event carries no channel, and its mark"

    _drain(db, rules, max_depth=3)

    wrote = [p for p in _events(db, PB) if p.get("source_name") == "pp_layer"]
    first = wrote[0]
    assert first.get(event_constants.CHANNEL_KEY) == "retroactive", wrote
    assert first.get(event_constants.CASCADE_KEY, False) is cascade
    if not cascade:
        assert _values(db, PB, "n") == ["1"] and _values(db, PA, "n") == ["0"]
        return
    # Asked to cascade, the downstream woke and went on as the chain goes - opted-in rules
    # only, bounded by the ceiling, and without the replay's key on the chain's own hops.
    later = [p for p in _events(db, PA) + wrote[1:] if p.get("source_name") == "pp_layer"]
    assert later and _values(db, PA, "n") != ["0"]
    assert {p.get(event_constants.CHANNEL_KEY) for p in later} == {"chain"}
    assert not any(event_constants.CASCADE_KEY in p for p in later)


def test_a_replays_group_is_never_folded_into_an_ordinary_one(db):
    """A merge ceiling folds adjacent groups that wake the same rules. A replay's group folded
    into an ordinary one would make the ordinary writes retroactive - silent downstream."""
    rules = [dict(r, **{"max_group_rows": 1000}) for r in _bumpers(opt_in=False)]
    ordinary = types.SimpleNamespace(id=1, table_name=PA, event_type="EDIT",
                                     payload={"row_ids": ["r1"]})
    replayed = types.SimpleNamespace(id=2, table_name=PA, event_type="EDIT",
                                     payload={"row_ids": ["r2"], "only_rule": "pp_a_to_b",
                                              event_constants.REPLAY_KEY: True})
    other = types.SimpleNamespace(id=3, table_name=PA, event_type="EDIT",
                                  payload={"row_ids": ["r3"]})
    groups = {"t1": [ordinary], "t2": [replayed], "t3": [other]}

    order, merged = worker.merge_consecutive_groups(["t1", "t2", "t3"], groups, rules)

    assert order == ["t1", "t2", "t3"], merged
    folded, _ = worker.merge_consecutive_groups(["t1", "t3"], groups, rules)
    assert folded == ["t1"], "the fixture no longer folds two ordinary groups"


def test_the_form_says_what_a_run_does_to_the_chain():
    """The operator reads it before running: every operation says its writes wake nothing,
    and the collector backfill - whose files the watcher ingests - says the chain runs."""
    notes = {entry["op"]: entry["downstream_note"] for entry in retroactive.inventory()}
    assert notes.pop("collector_backfill").startswith("The files it collects are ingested")
    # The emergency stop's pair says its own: set aside does not run, run again runs each rule
    # once and cascades nothing - the grid's click replay is the one that cascades (소유자 09-27).
    assert notes.pop("set_aside").startswith("Events set aside do not run")
    assert "nothing downstream runs" in notes.pop("rerun_set_aside")
    assert notes and set(notes.values()) == {retroactive.DOWNSTREAM_NOTE}


def test_every_operation_writes_on_the_retroactive_channel(db, monkeypatch):
    def run(session, params, log, control):
        crud.apply_batch_updates(session, PA, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"k": "K", "n": "0"}, source_name="seed",
                                      updated_by="pp")]))
        session.commit()
        return {}
    spec = dict(retroactive.OPERATIONS["withdraw"], params=[], run=run,
                judge=lambda *a, **k: None, count=None)
    monkeypatch.setitem(retroactive.OPERATIONS, "pp_probe", spec)
    monkeypatch.setattr(retroactive, "validate", lambda op, params: dict(params or {}))

    out = retroactive.execute({"run_id": "pp2", "op": "pp_probe", "params": {}},
                              log=lambda m: None)

    assert out["status"] == "ok", out["error"]
    assert [event_constants.channel_of(p) for p in _events(db, PA)] == ["retroactive"]
