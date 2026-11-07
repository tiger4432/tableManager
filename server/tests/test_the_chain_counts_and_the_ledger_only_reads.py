# -*- coding: utf-8 -*-
"""S-100 ⓐ (판정 197 · 211). The chain computes the count; the ledger only reads it.

🔴 THE DESIGN RULE THIS PAYS BACK. A ledger declaration is LOCAL and CALCULATION-FREE: one
atom comes from one molecule and its value is a column value or a constant. A dt_job's netdie
count is neither - it exists only once rows are grouped - so the ledger reached for a PYTHON
role mapper (`dt-job-role`) that counted the group itself. That was the ledger computing, and
it made the declaration beside it a DECOY: `bind.counted.value` named `dt_index` while the
mapper ignored it and emitted `len(unit)`.

So the arithmetic moved to the chain, which is allowed to compute, and the ledger reads the
table it writes with the generic declarative mapper.

⛔ THE CLAIM IS THAT NOTHING ELSE CHANGED, so that is what these cases score: the same
predicates, the same subject, the same number, the same qualifiers - measured against the old
python path before it was deleted, and written out here by hand rather than captured.
"""
from datetime import datetime, timezone
import io
import json
import os
import shutil
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.implementations import mapper_declarations               # noqa: E402
from ledger.setup import load_setup, preview_selected_cursor_batch   # noqa: E402
from ledger.setup_bundle import load_physical_catalog                # noqa: E402

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "sample")
TABLE_CONFIG = os.path.join(SAMPLE, "table_config.json.sample")
LEDGER_CONFIG = os.path.join(SAMPLE, "ledger_config.json.sample")
CHAIN_RULES = os.path.join(SAMPLE, "chain_rules.json.sample")

NOW = datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)
JOB = "SYN-DTJ-002-04"
ROLLUP = "dt_job_rollup"

#: 🔴 WHAT THE OLD PYTHON MAPPER EMITTED, measured on 2026-09-09 from five `dt_log` rows of
#: one job before `mappers/ledger_v2_dt_job_mapper.py` was deleted - and written out here
#: rather than captured, so a rewrite is scored against the CONTRACT and not against itself.
EXPECTED = [
    {"predicate": "has_netdie", "subject_type": "dtjob",
     "subject_keys": {"dt_job": JOB}, "object_kind": "value",
     "object_payload": {"value": 5}},
    {"predicate": "register", "subject_type": "dtjob",
     "subject_keys": {"dt_job": JOB}, "object_kind": None,
     "object_payload": {"qualifiers": {"dt_eqp": "EQP-7"}}},
]


def load(path):
    return json.loads(io.open(path, encoding="utf-8").read())


@pytest.fixture(scope="module")
def setup():
    """The SHIPPED declaration, through the product's own loader.

    ⚠️ `load_setup` wants a root holding `ledger_config.json`, so the sample is copied under
    that name. Everything else - catalogue, validation, compile - is the path production
    takes, which is the point: this scores the file that ships.
    """
    root = tempfile.mkdtemp()
    shutil.copy(LEDGER_CONFIG, os.path.join(root, "ledger_config.json"))
    return load_setup(root, catalog=load_physical_catalog(TABLE_CONFIG))


def semantics(setup, rows):
    preview = preview_selected_cursor_batch(
        setup, "dt_job", pd.DataFrame(rows), {"dt_job": JOB}, known_registrations=())
    out = [{key: item.get(key) for key in
            ("predicate", "subject_type", "subject_keys", "object_kind", "object_payload")}
           for item in preview.candidate_semantics]
    return sorted(out, key=lambda atom: str(atom["predicate"]))


# ------------------------------------------------------------------ the atoms


def test_the_same_atoms_come_out_of_the_declaration_alone(setup):
    """🔴 THE HEADLINE. One rollup row carrying the count produces exactly what the python
    mapper produced from the five rows it counted itself."""
    assert semantics(setup, [{"dt_job": JOB, "netdie_count": 5, "dt_eqp": "EQP-7",
                              "event_time": NOW, "created_at": NOW,
                              "row_id": "r0"}]) == EXPECTED


def test_the_value_now_comes_from_the_column_the_declaration_names(setup):
    """⛔ THE DECOY IS GONE. `bind.counted.value` used to name `dt_index` and the mapper
    emitted `len(unit)` instead, so the declaration said something that was not true. Change
    the column and the atom must follow - if it does not, something is still computing."""
    atoms = semantics(setup, [{"dt_job": JOB, "netdie_count": 41, "dt_eqp": "EQP-7",
                               "event_time": NOW, "created_at": NOW, "row_id": "r0"}])
    assert atoms[0]["object_payload"] == {"value": 41}


def test_the_shipped_declaration_no_longer_reaches_the_python_implementation():
    """⛔ NO SECOND PATH IN THE DECLARATION (판정 211) - and that is the half that can land
    today.

    ⚠️ THE CLASS ITSELF IS STILL THERE, ON PURPOSE. A trusted implementation is derived from
    the classes that EXIST, so deleting it makes every deployment whose own
    `ledger_config.json` still says `dt-job-role` fail to compile - the WHOLE setup, not one
    source. Measured: deleting it turned six `test_ledger_setup_boundary` cases red on this
    box, because the box's own gitignored declaration still names it, and production has such
    a file too. The order is: this declaration ships, each deployment's own moves, then the
    class goes. So what is pinned here is that the SAMPLE reaches the generic mapper, plus
    the deprecation notice that keeps the leftover from reading as a live second path.
    """
    assert load(LEDGER_CONFIG)["sources"]["dt_job"]["map"]["implementation_id"] == \
        "declarative-role"
    assert ("declarative-role", 1) in mapper_declarations()

    leftover = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mappers",
                            "ledger_v2_dt_job_mapper.py")
    if os.path.exists(leftover):
        assert "RETIRED IN THE DECLARATION" in io.open(
            leftover, encoding="utf-8").read(2000), (
            "the class outlived the declaration that used it, so it has to say so - "
            "otherwise the next reader takes it for a live second path")


# ------------------------------------------------------------------ the declarations


def test_the_three_declarations_name_each_other():
    """The table, the rule and the ledger source are one chain of names; a break anywhere
    leaves the count written nowhere or read from nothing."""
    table = load(TABLE_CONFIG)[ROLLUP]
    assert table["business_key"] == "dt_job"
    assert set(table["column_types"]) == {"dt_job", "netdie_count", "dt_eqp", "event_time"}

    rules = load(CHAIN_RULES)["rules"]
    rule = next(r for r in rules if r["name"] == "dt_log_to_dt_job_rollup")
    assert rule["on"]["table"] == "dt_log" and rule["into"]["table"] == ROLLUP
    assert rule["derive"]["kind"] == "decide" and rule["derive"]["decide"]["key"] == ["dt_job"]
    assert set(rule["derive"]["decide"]["aggregations"]) == set(table["column_types"]) - {"dt_job"}

    source = load(LEDGER_CONFIG)["sources"]["dt_job"]
    assert source["relation"] == ROLLUP
    assert source["read"]["unit"] == "row"
    assert source["bind"]["mappings"]["counted"]["bind"]["value"]["column"] == "netdie_count"


def _rule():
    return next(r for r in load(CHAIN_RULES)["rules"] if r["name"] == "dt_log_to_dt_job_rollup")


def test_the_rule_names_no_mapper_file_and_queues_nobody():
    """11-02 (lead ㄱ): the count is a decide declaration - the product builds its mapper from the declaration in this
    process (`declared:enrich`), so no file ships or has to be put anywhere; the mapper file this rule named
    (mappers/dt_job_rollup_mapper.py.sample) retired. ⚰️ This file used to assert the rule was NOT a decide, because a
    decide then required a field for a person and queued one unanswerable item a dt_job; da6c523e1 («a decide with no
    field for a person stands on its aggregations - one derived row per key ... queued for nobody») ended that."""
    from chain import rule_shape

    rules, refusal = rule_shape.decide_rules(rule_shape.from_declaration(_rule()), load(TABLE_CONFIG))
    assert refusal is None
    assert sorted(r["mapper"] for r in rules) == ["declared:decide", "declared:enrich"]
    assert all(r["params"]["target_fields"] == [] for r in rules), "no field for a person - nothing queued"
    assert not any("mapper_module" in r for r in rules)


# ------------------------------------------------------------------ the count, run by the chain seat


@pytest.fixture(name="seat")
def fixture_seat():
    """The sample's dt_log and dt_job_rollup on sqlite, and the shipped declaration's dedup half - the rule the seat
    runs when dt_log moves."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import mapper_sdk
    from chain import rule_shape
    from database import crud, models
    from database.database import Base

    mapper_sdk.discover()
    tables = {name: load(TABLE_CONFIG)[name] for name in ("dt_log", ROLLUP)}
    # sqlite takes no text into a datetime column and the write door spells a time as text - the count is this
    # test's, not the tables' time (a datetime in the sample, owner 11-07)
    for name in tables:
        tables[name]["column_types"]["event_time"] = "string"
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    rules = rule_shape.expand_declaration(_rule(), crud.TABLE_CONFIG)[0]
    try:
        yield session, [r for r in rules if r["name"].startswith("enrichment_dedup:")]
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in tables:
            crud.TABLE_CONFIG.pop(name, None)


def _counts(db):
    from database import models

    return {r.dt_job: int(float(r.netdie_count)) for r in db.query(models.DYNAMIC_TABLES[ROLLUP]).all()}


def _run(db, tag, rules):
    from chain import ingestion_worker as worker
    from database import models

    events = db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.table_name == "dt_log",
                                                    models.DatabaseOutbox.processed_at.is_(None)).all()
    worker._process_chain_transaction_group_sync("tx-rollup-%s" % tag, events, db, rules)
    for event in events:
        event.processed_at = event.processed_at or datetime.now(timezone.utc)
    db.commit()


def test_one_row_a_job_its_count_and_a_deleted_row_recounts(seat):
    """🔴 THE RETIRED MAPPER'S CONTROL (lead 11-02): what `build_dt_job_rollup_rows` did - one row a job, the job's
    count and not the batch's, a deleted row recounts its job - measured here on the declaration that replaced it.
    The throwaway-DB board of 11-02 (API + chain worker + ledger worker) gave the same 1 · 2 · 4, then 3."""
    from database import crud, models, schemas

    db, rules = seat
    jobs = {"JOB-A": 1, "JOB-B": 2, "JOB-C": 4}
    crud.apply_batch_updates(db, "dt_log", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"dt_job": job, "dt_job_id": job, "b_wx": i, "b_wy": j,
                                           "dt_eqp": "EQP-%d" % j, "event_time": "2026-11-02 0%d:00:00" % j},
                                  source_name="user", updated_by="t")
        for j, (job, n) in enumerate(jobs.items()) for i in range(n)]))
    db.commit()
    _run(db, "seed", rules)
    assert _counts(db) == jobs, "one row a job, each the job's own count"
    row = db.query(models.DYNAMIC_TABLES[ROLLUP]).filter_by(dt_job="JOB-B").one()
    assert (row.dt_eqp, row.event_time) == ("EQP-1", "2026-11-02 01:00:00"), "the columns the ledger reads ride along"

    gone = db.query(models.DYNAMIC_TABLES["dt_log"]).filter_by(dt_job="JOB-C").first()
    crud.delete_rows_batch(db, "dt_log", [gone.row_id], "t")
    db.commit()
    _run(db, "delete", rules)
    assert _counts(db) == dict(jobs, **{"JOB-C": 3}), "a deleted row recounts its job, and only its job"
