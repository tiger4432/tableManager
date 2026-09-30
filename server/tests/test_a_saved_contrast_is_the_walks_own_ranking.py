# -*- coding: utf-8 -*-
"""총괄 3a262cc76 — 대조 한 줄(contrast_run) -> 체인 -> 걷기가 매긴 후보 행(contrast_factor).

순위는 걷기 라우트의 것이다: 같은 인자로 부른 GET /api/ledger/subgraph 의 propagation.ranked 와
행 수 · 두 수와 분모 · 순위층이 같다. until 이 걷기를 묶어 리플레이해도 같은 행이다.
걷기는 메모리 원장(InMemoryEvidenceLookup)으로 돈다 — 라우트와 맵퍼가 같은 원장을 본다.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import rule_run, rule_shape                             # noqa: E402
from database.database import Base                                 # noqa: E402
from database import crud, models, schemas                         # noqa: E402
from ledger import explorer, trace_router                          # noqa: E402
from ledger_api import ledger_subgraph                             # noqa: E402

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
_TABLES = json.load(open(os.path.join(SAMPLE, "table_config.json.sample"), encoding="utf-8"))
TABLES = {name: _TABLES[name] for name in ("contrast_run", "contrast_factor")}
_RULES = json.load(open(os.path.join(SAMPLE, "chain_rules.json.sample"), encoding="utf-8"))
DECLARATION = next(r for r in _RULES["rules"] if r.get("name") == "contrast_factor_from_run")
RULE = rule_shape.expand_declaration(DECLARATION)[0][0]

UNTIL = datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc)
BEFORE, AFTER = UNTIL - timedelta(days=1), UNTIL + timedelta(days=1)


def _lot(name):
    return explorer.entity_id("Lot", {"lot": name})


def _atom(number, subject, target, when):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="Lot", subject_keys={"lot": subject},
        predicate="derived_from", object_kind="entity_ref",
        object_payload={"type": "Lot", "keys": {"lot": target}, "qualifiers": {}},
        occurred_at=when, source_who="fixture", source_translator_ver="v1",
        source_raw_ref="row:%d" % number, supersedes=None,
        source_event_id=str(uuid.UUID(int=900 + number)), source_event_state="source_record")


#: X is reached from both marked lots only, Y from one marked lot and the control, LATE only
#: after `until`, and FAN0..FAN14 give a small node budget something to cut.
ATOMS = ([_atom(1, "P1", "X", BEFORE), _atom(2, "P2", "X", BEFORE),
          _atom(3, "N1", "Y", BEFORE), _atom(4, "P1", "Y", BEFORE),
          _atom(5, "P2", "LATE", AFTER)]
         + [_atom(10 + i, "P1", "FAN%d" % i, BEFORE) for i in range(15)])


def _walk_on_the_fixture_ledger(monkeypatch):
    """The route's catalogue questions answered empty, and its ledger is ATOMS in memory."""
    monkeypatch.setattr(trace_router.trace, "relation_exists", lambda *a, **k: True)
    monkeypatch.setattr(trace_router, "_subgraph_contract_state", lambda *a, **k: [])
    for name in ("_static_types", "_static_step_predicates", "_self_describing_predicates"):
        monkeypatch.setattr(trace_router, name, lambda *a, **k: frozenset())
    monkeypatch.setattr(trace_router, "_predicate_cardinalities", lambda *a, **k: {})
    monkeypatch.setattr(ledger_subgraph, "SqlEvidenceLookup",
                        lambda connection, relation=None, since=None, until=None:
                        ledger_subgraph.InMemoryEvidenceLookup(ATOMS, since=since, until=until))


@pytest.fixture(name="db")
def fixture_db(monkeypatch):
    _walk_on_the_fixture_ledger(monkeypatch)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _save_run(db, run_id, positive, negative, **walk):
    """The run row, put in through the model: SQLite's DateTime column takes neither form the
    write door hands it (PostgreSQL parses the ISO text the screen sends)."""
    cells = {"run_id": run_id, "positive": json.dumps(positive), "negative": json.dumps(negative),
             "until": UNTIL, "hops": 4}
    cells.update(walk)
    model = models.DYNAMIC_TABLES["contrast_run"]
    db.add(model(row_id="run_" + run_id, business_key_val=run_id, **cells))
    db.commit()
    return "run_" + run_id


def _chain(db, *row_ids):
    """What the worker does with the rule: the seat resolves the declared mapper by name and
    calls it, then the proposal is written."""
    out = rule_run.run_rule(db, RULE, row_ids=list(row_ids))
    if out["updates"]:
        crud.apply_batch_updates(db, "contrast_factor",
                                 schemas.GeneralUpdateBatch(updates=out["updates"], silent=True))
    return out


def _run_facts(out):
    """The write-back the mapper proposes for the run rows: {run_id: cells}."""
    return {item.updates["run_id"]: item.updates for batch in out.get("batches") or ()
            if batch.get("target_table") == "contrast_run" for item in batch["updates"]}


def _factors(db, run_id):
    model = models.DYNAMIC_TABLES["contrast_factor"]
    return {r.node_id: r for r in db.query(model).filter(model.run_id == run_id).all()}


def _route(db, positive, negative, until=UNTIL.isoformat(), node_limit=400):
    return trace_router.evidence_subgraph(
        node_id=positive[0], positive=positive[1:] or None, negative=negative or None,
        hops=4, direction="both", since=None, until=until, node_limit=node_limit,
        edge_limit=1200, follow=None, backbone_hops=0, collect=None, seed_type=None,
        seed_limit=ledger_subgraph.DEFAULT_SEED_LIMIT, group_by=None, measure=None,
        response_format="json", db=db, include_superseded=False)["propagation"]


def test_the_rows_are_the_route_ranked_candidates_bound_by_until(db):
    positive, negative = [_lot("P1"), _lot("P2")], [_lot("N1")]
    out = _chain(db, _save_run(db, "R1", positive, negative, backbone_hops=0))
    rows = _factors(db, "R1")
    route = _route(db, positive, negative)

    assert len(rows) == len(route["ranked"]) > 0
    for item in route["ranked"]:
        row = rows[item["id"]]
        assert [row.reach_positive, row.reach_negative] == item["reach"]
        assert [row.reachable_positive, row.reachable_negative] == item["reachable"]
        assert (row.rank, row.type, row.label) == (item["rank"], item["type"], item["label"])
        assert (row.top, row.tied, row.incomparable) == tuple(
            json.dumps(item[k]) for k in ("top", "tied", "incomparable"))
    facts = _run_facts(out)["R1"]
    assert (facts["contrast"], facts["candidates"]) == ("contrasted", len(rows))
    labels = {r.label for r in rows.values()}
    assert "LATE" not in labels
    assert "LATE" in {i["label"] for i in _route(db, positive, negative, until=None)["ranked"]}, (
        "the fixture must hold an atom after until, or binding it proves nothing")


def test_no_controls_is_unexamined_and_a_cut_walk_is_not_complete(db):
    facts = _run_facts(_chain(db, _save_run(db, "R_OPEN", [_lot("P1"), _lot("P2")], []),
                              _save_run(db, "R_CUT", [_lot("P1")], [_lot("N1")], node_limit=10)))

    assert (facts["R_OPEN"]["contrast"], facts["R_OPEN"]["complete"]) == ("unexamined", "true")
    assert facts["R_CUT"]["complete"] == "false"


def test_a_replay_writes_the_same_rows_and_two_saves_are_two_runs(db):
    first = _save_run(db, "R1", [_lot("P1"), _lot("P2")], [_lot("N1")])
    second = _save_run(db, "R2", [_lot("P1"), _lot("P2")], [_lot("N1")])
    _chain(db, first)
    before = {k: (r.rank, r.reach_positive, r.evidence) for k, r in _factors(db, "R1").items()}
    _chain(db, first)
    after = {k: (r.rank, r.reach_positive, r.evidence) for k, r in _factors(db, "R1").items()}
    _chain(db, second)

    assert after == before and before
    assert set(_factors(db, "R2")) == set(before)


def test_the_stored_trail_names_the_predicates_it_crossed(db):
    _chain(db, _save_run(db, "R1", [_lot("P1"), _lot("P2")], [_lot("N1")]))
    trails = json.loads(_factors(db, "R1")[_lot("X")].evidence)

    assert trails and all(hop["predicates"] == ["derived_from"]
                          for trail in trails for hop in trail["hops"][1:])


def test_include_superseded_is_read_as_true_or_false_and_anything_else_is_refused():
    """총괄 d4a949a8c ⑤: `crud.boolean_text_read`, not a reader of its own that took "1" and
    called "yes" false."""
    from types import SimpleNamespace

    import validation
    from mappers import contrast_walk

    for text, want in (("true", True), ("FALSE", False)):
        args, why = contrast_walk._walk_arguments(
            SimpleNamespace(include_superseded=text, until=UNTIL))
        assert why is None and args["include_superseded"] is want, (text, why)
    for text in ("yes", "1"):
        args, why = contrast_walk._walk_arguments(
            SimpleNamespace(include_superseded=text, until=UNTIL))
        assert args is None and why == validation.flag_refusal("include_superseded", text), why


def test_a_run_without_until_is_refused_by_name(db):
    row_id = _save_run(db, "R_OPEN_ENDED", [_lot("P1")], [_lot("N1")], until=None)
    out = _chain(db, row_id)

    assert out["updates"] == [] and "until is empty" in out["refusal"]
    assert _factors(db, "R_OPEN_ENDED") == {}


def test_the_rows_carry_the_run_rows_stamp_so_deleting_the_run_empties_them(db):
    """The body stamps `origin_row_id` as the join's body does; a deleted run row is taken
    back by that stamp (`withdraw_by_origin`, the delete path). The rows stay, their cells go."""
    from chain import cell_layer

    run = _save_run(db, "R1", [_lot("P1"), _lot("P2")], [_lot("N1")])
    _chain(db, run)
    count = len(_factors(db, "R1"))
    stamps = {r[0] for r in db.query(models.CellSource.origin_row_id)
              .filter_by(table_name="contrast_factor")}
    stats = cell_layer.withdraw_by_origin(db, [run], apply=True)
    db.commit()
    model = models.DYNAMIC_TABLES["contrast_factor"]
    rows = db.query(model).all()

    assert stamps == {run} and count > 0
    assert stats["cells_withdrawn"] == count * len(TABLES["contrast_factor"]["column_types"])
    assert len(rows) == count and {(r.run_id, r.node_id, r.rank) for r in rows} == {
        (None, None, None)}


@pytest.mark.pg
@pytest.mark.parametrize("until", ["2026-09-30T09:00:00", "2026-09-30T09:00:00+09:00"])
def test_a_run_the_board_writes_through_the_door_is_walked_into_rows(pg_engine, monkeypatch,
                                                                      until):
    """Save contrast is PUT /tables/contrast_run/data/updates - the lists as JSON text, until as
    ISO text with or without a zone. That door writes the run on PostgreSQL and the chain fills
    its rows. The walk still reads the in-memory ledger."""
    _walk_on_the_fixture_ledger(monkeypatch)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=pg_engine)
    models.sync_dynamic_tables_schema(pg_engine)
    db = sessionmaker(bind=pg_engine)()
    run_id = "R_PG_ZONED" if "+" in until else "R_PG_NAIVE"
    positive, negative = [_lot("P1"), _lot("P2")], [_lot("N1")]
    try:
        crud.apply_batch_updates(db, "contrast_run", schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={
                "run_id": run_id, "positive": json.dumps(positive),
                "negative": json.dumps(negative), "until": until, "hops": 4,
                "backbone_hops": 0})]))
        model = models.DYNAMIC_TABLES["contrast_run"]
        run = db.query(model).filter(model.run_id == run_id).one()
        _chain(db, run.row_id)
        rows = _factors(db, run_id)
        route = _route(db, positive, negative, until=run.until.isoformat())

        assert len(rows) == len(route["ranked"]) > 0
        assert "LATE" not in {r.label for r in rows.values()}
    finally:
        db.rollback()
        db.close()
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


# ------------------------------------------------ the run row says it was computed (2dd93d4a9 1)

def _drain(db, rule=RULE):
    """The worker over this file's events -> chain-written events that woke the rule."""
    import event_constants
    from chain import ingestion_worker as worker
    from utils.payload_helper import get_payload_dict

    woke = 0
    for _ in range(4):
        pending = [e for e in db.query(models.DatabaseOutbox)
                   .filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all() if e.table_name in TABLES]
        if not pending:
            return woke
        woke += sum(1 for e in pending
                    if event_constants.channel_of(get_payload_dict(e)) == event_constants.CHANNEL_CHAIN
                    and worker.fires(rule, e) and worker.rule_watches_changed_columns(rule, e))
        groups = {}
        for e in pending:
            groups.setdefault(get_payload_dict(e).get("transaction_id"), []).append(e)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, [rule])
            assert ok, error
            for e in events:
                event_constants.mark_processed(e, "SUCCESS")
            db.commit()
    raise AssertionError("the chain did not settle")


@pytest.mark.pg
@pytest.mark.parametrize("shape", ["batch", "per_row"])
def test_a_run_row_says_whether_it_was_computed_and_what_it_found(pg_engine, monkeypatch, shape):
    """computed_at · candidates · contrast · complete, written back by the same call through the
    worker: a run never walked has all four empty, one that found nothing has computed_at and
    0, and the write-back does not wake the rule again. `per_row` (총괄 12cc7dd1f ③): the same
    rule called row by row - its write-back was dropped by the worker before."""
    import event_constants
    from utils.payload_helper import get_payload_dict

    _walk_on_the_fixture_ledger(monkeypatch)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=pg_engine,
                             tables=[models.DYNAMIC_TABLES[n].__table__ for n in TABLES])
    models.sync_dynamic_tables_schema(pg_engine)
    with pg_engine.begin() as conn:                 # each shape starts from empty tables
        for name in TABLES:
            conn.exec_driver_sql('DELETE FROM "%s"' % name)
            conn.exec_driver_sql("DELETE FROM cell_sources WHERE table_name = '%s'" % name)
    db = sessionmaker(bind=pg_engine)()
    model = models.DYNAMIC_TABLES["contrast_run"]

    def save(run_id, positive, negative, until="2026-09-30T09:00:00+09:00"):
        cells = {"run_id": run_id, "positive": json.dumps(positive),
                 "negative": json.dumps(negative), "hops": 4, "backbone_hops": 0}
        if until:
            cells["until"] = until
        crud.apply_batch_updates(db, "contrast_run", schemas.GeneralUpdateBatch(
            updates=[schemas.GeneralUpdateItem(updates=cells)]))
        db.commit()

    def facts(run_id):
        row = db.query(model).filter(model.run_id == run_id).one()
        db.refresh(row)
        return row.computed_at, row.candidates, row.contrast, row.complete

    try:
        save("RW_FOUND", [_lot("P1"), _lot("P2")], [_lot("N1")])
        save("RW_NONE", [_lot("NOBODY")], [_lot("NOBODY2")])
        save("RW_OPEN_ENDED", [_lot("P1")], [_lot("N1")], until=None)
        waiting = facts("RW_FOUND")
        woke = _drain(db, RULE if shape == "batch" else dict(RULE, is_batch=False))
        found, none, open_ended = facts("RW_FOUND"), facts("RW_NONE"), facts("RW_OPEN_ENDED")
        written = [get_payload_dict(e) for e in db.query(models.DatabaseOutbox).all()
                   if e.table_name == "contrast_run" and event_constants.channel_of(
                       get_payload_dict(e)) == event_constants.CHANNEL_CHAIN]

        assert waiting == (None, None, None, None), "not computed yet: all four empty"
        assert found[0] is not None and found[1] == len(_factors(db, "RW_FOUND")) > 0
        assert found[2:] == ("contrasted", "true")
        assert none[0] is not None and none[1] == 0 and _factors(db, "RW_NONE") == {}
        assert open_ended == (None, None, None, None), "refused: nothing written back"
        assert woke == 0, "the write-back woke the rule again"
        assert written and all(p[event_constants.WRITTEN_BY_KEY] == [DECLARATION["name"]]
                               for p in written)
    finally:
        db.rollback()
        db.close()
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def test_a_rule_writes_back_to_its_trigger_table_only_and_only_plainly():
    import dt_map_derivation

    rule = {"name": "r", "trigger_table": "t_in", "target_table": "t_out"}
    table, updates, scope, retract = dt_map_derivation.normalize_scoped_batch(
        {"target_table": "t_in", "updates": ["u"]}, rule, "t_out")
    assert (table, list(updates), scope, retract) == ("t_in", ["u"], None, None)
    with pytest.raises(ValueError) as elsewhere:
        dt_map_derivation.normalize_scoped_batch(
            {"target_table": "t_other", "updates": ["u"]}, rule, "t_out")
    assert "'r'" in str(elsewhere.value) and "'t_other'" in str(elsewhere.value)
    assert "only the rule's trigger table" in str(elsewhere.value)
    with pytest.raises(ValueError) as purge:
        dt_map_derivation.normalize_scoped_batch(
            {"target_table": "t_in", "replace_map": True, "scope": {"a": 1}}, rule, "t_out")
    assert "plain updates only" in str(purge.value)


# ---------------------------------------------------------------- the owner's shape (lead)

def test_the_form_offers_it_as_the_one_mapper_of_its_module_and_the_save_gate_takes_it(
        db, tmp_path, monkeypatch):
    """Offered where the owner's mappers are, by module and function - and only that function:
    every public function of two arguments in the package would be offered too."""
    import mapper_sdk
    from ledger import admin

    offered = [c for c in mapper_sdk.mapper_candidates("mappers")["candidates"]
               if c["module"] == "mappers.contrast_walk"]
    assert offered == [{"module": "mappers.contrast_walk", "name": "contrast_walk",
                        "kind": "function", "params": None}]

    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": []}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "bk"))
    declaration = {k: v for k, v in DECLARATION.items() if k != "name"}
    saved = admin.save_chain_rule_raw(DECLARATION["name"], declaration,
                                      admin.file_fingerprint(str(path)))
    assert saved["ok"] and saved["created"]


def test_the_package_walk_at_start_does_not_import_the_route():
    """`discover` imports this module in every process at start; the route comes in only when a
    run is walked. Asked in a fresh interpreter - this test process has the route already."""
    import subprocess

    probe = ("import sys, mapper_sdk; mapper_sdk.discover(); "
             "print('mappers.contrast_walk' in sys.modules, 'ledger.trace_router' in sys.modules)")
    done = subprocess.run([sys.executable, "-c", probe], cwd=SERVER_DIR, capture_output=True,
                          text=True, env={**os.environ, "TESTING": "True",
                                          "DATABASE_URL": "sqlite:///:memory:"})
    assert done.stdout.split()[-2:] == ["True", "False"], done.stdout + done.stderr
