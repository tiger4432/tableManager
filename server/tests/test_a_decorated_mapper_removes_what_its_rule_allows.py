# -*- coding: utf-8 -*-
"""A rule whose mapper `@mapper` made removes what its flag allows (총괄 ed70c3970 ② · 717f60124 ·
7489221e2). 소유자:

    @mapper 맵퍼를 쓰는 규칙에 allow_retraction: true 를 적으면, 그 출처(target_job_column)가
    이번에 안 낸 셀이 지워진다
    allow_replace_map: true 를 적으면 맵 단위로 통째로 바뀐다(맵 키는 table_config 의 map_key_columns)

- the mapper returns a DataFrame; the product builds one retract batch per job or one replace_map
  batch per map, naming the jobs and maps the INCOMING rows carry too (a zero-row source)
- refused at load: both flags · a flag without is_batch · a map key the trigger table lacks
- refused at run: the result has no job column / map key column
- the half guard still judges a zero-row job, and its refusal names the way to delete on purpose
"""
import logging
import os
import sys

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                                        # noqa: E402
import mapper_sdk                                                            # noqa: E402
from chain import ingestion_worker as worker                                 # noqa: E402
from chain import replay                                                     # noqa: E402
from database import crud, models, schemas                                   # noqa: E402
from database.database import Base                                          # noqa: E402

TRIG, TGT, BARE = "sdkm_trig", "sdkm_tgt", "sdkm_bare_trig"
TABLES = {
    TRIG: {"business_key": "tk", "composite_key_source": ["tk"],
           "column_types": {"tk": "string", "job": "string", "qty": "string"},
           "display_columns": ["tk", "job", "qty"]},
    BARE: {"business_key": "tk", "composite_key_source": ["tk"],
           "column_types": {"tk": "string", "lot": "string"}, "display_columns": ["tk", "lot"]},
    # `cell_key` declared: an undeclared key column is counted as a drop in the worker's
    # process-wide note, which another file's clean-beat cell then reads
    TGT: {"business_key": "cell_key", "composite_key_source": ["job", "cell"],
          "map_key_columns": ["job"],
          "column_types": {"cell_key": "string", "job": "string", "cell": "string",
                           "v": "string"},
          "display_columns": ["job", "cell", "v"]},
}


def _build(df, db):
    rows = [{"job": r["job"], "cell": "c%d" % i, "v": "new"}
            for _, r in df.iterrows() for i in range(int(r["qty"] or 0))]
    return pd.DataFrame(rows, columns=["job", "cell", "v"])


def _build_without_job(df, db):
    return _build(df, db).drop(columns=["job"])


@pytest.fixture(autouse=True)
def _mappers_and_tables():
    mapper_sdk.mapper(name="sdkm_build")(_build)
    mapper_sdk.mapper(name="sdkm_build_nojob")(_build_without_job)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    yield
    for name in ("sdkm_build", "sdkm_build_nojob"):
        mapper_sdk.MAPPER_REGISTRY.pop(name, None)
        mapper_sdk.MAPPER_PARAMS.pop(name, None)
    for name in TABLES:
        crud.TABLE_CONFIG.pop(name, None)


def _rule(mapper="sdkm_build", **cells):
    rule = {"name": "sdkm_rule", "enabled": True, "trigger_table": TRIG, "target_table": TGT,
            "mapper": mapper, "is_batch": True, "idempotent": True,
            "trigger_job_column": "job", "target_job_column": "job"}
    rule.update(cells)
    return rule


def _payload(tk, job, qty):
    return {"row_id": tk, "data": {"tk": {"value": tk}, "job": {"value": job},
                                   "qty": {"value": str(qty)}}}


# ---------------------------------------------------------------------------
# the envelope - every flag x every shape of result
# ---------------------------------------------------------------------------

FLAGS = {"none": {}, "retract": {"allow_retraction": True},
         "replace": {"allow_replace_map": True},
         "both": {"allow_retraction": True, "allow_replace_map": True}}
SHAPES = {"rows": ("sdkm_build", [("T1", "J-A", 2)]),
          "zero_row_source": ("sdkm_build", [("T1", "J-A", 2), ("T2", "J-B", 0)]),
          "key_column_missing": ("sdkm_build_nojob", [("T1", "J-A", 2)])}
#: (flags, shape) -> what comes out: ("updates", n) | ("batches", [(job, n)]) | ("refused", words)
EXPECTED = {
    ("none", "rows"): ("updates", 2), ("none", "zero_row_source"): ("updates", 2),
    # today's refusal, unchanged: the target composes its key from `job`
    ("none", "key_column_missing"): ("refused", "the frame has no ['job']"),
    ("retract", "rows"): ("batches", [("J-A", 2)]),
    ("retract", "zero_row_source"): ("batches", [("J-A", 2), ("J-B", 0)]),
    ("retract", "key_column_missing"): ("refused", "removes by ['job']"),
    ("replace", "rows"): ("batches", [("J-A", 2)]),
    ("replace", "zero_row_source"): ("batches", [("J-A", 2), ("J-B", 0)]),
    ("replace", "key_column_missing"): ("refused", "removes by ['job']"),
    ("both", "rows"): ("refused", "removes one way"),
    ("both", "zero_row_source"): ("refused", "removes one way"),
    ("both", "key_column_missing"): ("refused", "removes one way"),
}


@pytest.mark.parametrize("flags, shape", sorted(EXPECTED))
def test_the_envelope_for_every_flag_and_shape(flags, shape):
    mapper, incoming = SHAPES[shape]
    rule = _rule(mapper, **FLAGS[flags])
    run = mapper_sdk.MAPPER_REGISTRY[mapper]
    kind, want = EXPECTED[(flags, shape)]

    if kind == "refused":
        with pytest.raises(mapper_sdk.MapperContractError) as refused:
            run(None, [_payload(*p) for p in incoming], rule=rule)
        assert want in str(refused.value), str(refused.value)
        return
    envelope = run(None, [_payload(*p) for p in incoming], rule=rule)
    if kind == "updates":
        assert "batches" not in envelope and len(envelope["updates"]) == want
        return
    got = []
    for batch in envelope["batches"]:
        if flags == "retract":
            assert batch["retract"] == {"source_column": "job",
                                        "source_value": batch["retract"]["source_value"]}
            got.append((batch["retract"]["source_value"], len(batch["updates"])))
        else:
            assert batch["replace_map"] is True and set(batch["scope"]) == {"job"}
            got.append((batch["scope"]["job"], len(batch["updates"])))
    assert got == want


# ---------------------------------------------------------------------------
# refused at load - the one judge, asked through the mark
# ---------------------------------------------------------------------------

LOAD = {
    "both flags": (_rule(allow_retraction=True, allow_replace_map=True), "sdk_two_removals"),
    "not a batch rule": (_rule(allow_retraction=True, is_batch=False), "sdk_removal_needs_batch"),
    "map key not on the trigger": (_rule(trigger_table=BARE, allow_replace_map=True),
                                   "sdk_map_key_not_on_trigger"),
    "a clean retraction": (_rule(allow_retraction=True), None),
    "a clean replacement": (_rule(allow_replace_map=True), None),
}


@pytest.mark.parametrize("case", sorted(LOAD))
def test_the_loader_refuses_by_name(case):
    rule, code = LOAD[case]
    issues = chain_bindings.rule_refusals(
        rule, "rules[0]", mapper_resolvable=worker._resolvable_mapper, derived_tables=set(),
        mapper_made_by_sdk=worker._made_by_sdk)
    codes = [i.code for i in issues if i.code.startswith("sdk_")]
    assert codes == ([code] if code else []), [(i.code, i.message) for i in issues]


def test_a_hand_written_mapper_is_not_judged_by_the_decorators_rules(monkeypatch):
    """The mark is what makes a rule the decorator's - a hand-written mapper returns its own
    envelope and keeps today's freedom."""
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "sdkm_hand", lambda db, payloads, rule=None: {})
    rule = _rule("sdkm_hand", allow_retraction=True, is_batch=False)
    issues = chain_bindings.rule_refusals(
        rule, "rules[0]", mapper_resolvable=worker._resolvable_mapper, derived_tables=set(),
        mapper_made_by_sdk=worker._made_by_sdk)
    assert not [i for i in issues if i.code.startswith("sdk_")]


# ---------------------------------------------------------------------------
# the database: worker and replay, the zero-row job, and the half guard
# ---------------------------------------------------------------------------

def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _push(db, table, rows):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(r), source_name="seed", updated_by="sdkm")
        for r in rows]))
    db.commit()


def _left(db):
    return sorted((r.job, r.cell) for r in db.query(models.DYNAMIC_TABLES[TGT]).all())


def _seed(db, old):
    _push(db, TGT, [{"job": job, "cell": "c%d" % i, "v": "old"}
                    for job, n in old.items() for i in range(n)])
    _push(db, TRIG, [{"tk": "T1", "job": "J-A", "qty": "2"}, {"tk": "T2", "job": "J-B", "qty": "0"},
                     {"tk": "T3", "job": "J-C", "qty": "0"}])


def _run(db, rule, path):
    events = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == TRIG,
        models.DatabaseOutbox.processed_chain.is_(False)).all()
    if path == "worker":
        ok, error, _b = worker._process_chain_transaction_group_sync("tx-sdkm", events, db, [rule])
        assert ok, error
        return
    for event in events:
        event.processed_chain = True
    db.commit()
    trig_ids = [r.row_id for r in db.query(models.DYNAMIC_TABLES[TRIG]).all()]
    replay.replay_rule(db, rule, apply=True, log=lambda m: None, row_ids=trig_ids)
    staged = [e for e in db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.processed_chain.is_(False)).all()
        if (e.payload or {}).get("only_rule")]
    assert staged, "replay staged nothing"
    ok, error, _b = worker._process_chain_transaction_group_sync(
        (staged[0].payload or {}).get("transaction_id"), staged, db, [rule])
    assert ok, error


@pytest.mark.parametrize("path", ["worker", "replay"])
@pytest.mark.parametrize("flag", ["allow_retraction", "allow_replace_map"])
def test_a_job_that_produced_nothing_loses_its_old_cells_on_either_path(flag, path):
    """J-A made two of its three cells; J-B made none - both are named by the incoming rows."""
    db = _db()
    _seed(db, {"J-A": 3, "J-B": 3})

    _run(db, _rule(**{flag: True}), path)

    assert _left(db) == [("J-A", "c0"), ("J-A", "c1")]


@pytest.mark.parametrize("path", ["worker", "replay"])
def test_the_half_guard_still_wins_and_says_how_to_delete_on_purpose(path, caplog):
    """소유자 1 = ㄱ: a job with 20 or more rows that produced nothing is refused by the half
    guard - nothing deleted, one refusal line, and the line names the door."""
    db = _db()
    _seed(db, {"J-A": 2, "J-C": 25})

    with caplog.at_level(logging.WARNING):
        _run(db, _rule(allow_retraction=True), path)

    assert sum(1 for job, _c in _left(db) if job == "J-C") == 25, "the guard deleted"
    said = [r.getMessage() for r in caplog.records
            if "DECLINED" in r.getMessage() and "'J-C'" in r.getMessage()]
    assert len(said) == 1, said
    assert "Next, to remove them on purpose" in said[0] and "rows/batch_delete" in said[0]


def test_a_replacement_takes_a_whole_map_and_its_human_corrections_with_it():
    """소유자 5 = ㄴ: replace_map removes the map whole - corrections included (retract keeps them)."""
    db = _db()
    _seed(db, {"J-B": 3})
    tgt = models.DYNAMIC_TABLES[TGT]
    corrected = db.query(tgt).filter(tgt.job == "J-B").first().row_id
    crud.apply_batch_updates(db, TGT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=corrected, updates={"v": "fixed"}, source_name="user",
                                  updated_by="person")]))
    db.commit()

    _run(db, _rule(allow_replace_map=True), "worker")

    assert not [c for c in _left(db) if c[0] == "J-B"]
    assert not db.query(models.CellOverwrite).filter(
        models.CellOverwrite.table_name == TGT, models.CellOverwrite.row_id == corrected).count()
