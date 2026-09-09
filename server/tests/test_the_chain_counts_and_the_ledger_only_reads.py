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
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.backfill import _no_join_reader                          # noqa: E402
from ledger.implementations import mapper_declarations               # noqa: E402
from ledger.setup import load_setup, preview_selected_cursor_batch   # noqa: E402
from ledger.setup_bundle import load_physical_catalog                # noqa: E402

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "sample")
TABLE_CONFIG = os.path.join(SAMPLE, "table_config.json.sample")
LEDGER_CONFIG = os.path.join(SAMPLE, "ledger_config.json.sample")
CHAIN_RULES = os.path.join(SAMPLE, "chain_rules.json.sample")
MAPPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mappers",
                      "dt_job_rollup_mapper.py.sample")

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
        setup, "dt_job", pd.DataFrame(rows), {"dt_job": JOB}, _no_join_reader(),
        known_registrations=())
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
    assert rule["trigger_table"] == "dt_log" and rule["target_table"] == ROLLUP
    assert rule["mapper_module"] == "mappers.dt_job_rollup_mapper"
    assert rule["is_batch"] is True

    source = load(LEDGER_CONFIG)["sources"]["dt_job"]
    assert source["relation"] == ROLLUP
    assert source["read"]["unit"] == "row"
    assert source["bind"]["mappings"]["counted"]["bind"]["value"]["column"] == "netdie_count"


def test_the_mapper_the_rule_names_is_a_tracked_sample():
    """⚠️ `server/mappers/` IS GITIGNORED. A rule pointing at a module that exists only on one
    machine ships a declaration nobody else can run, which is why every other chain mapper
    here has a tracked `.py.sample` beside it."""
    assert os.path.exists(MAPPER)


def test_this_is_not_an_enrichment_rule_and_leaves_no_human_worklist():
    """⛔ MEASURED, AND IT IS WHY THE RULING'S FIRST MECHANISM WAS PUT ASIDE. Enrichment's
    `aggregations` would have done the counting declaratively, but a rule there requires a
    non-empty `target_fields` and its worklist is exactly 「rows where those are blank」 - so
    one permanent, unanswerable queue item per dt_job. An ordinary chain rule has no such
    field, and this asserts the rule stayed one."""
    rule = next(r for r in load(CHAIN_RULES)["rules"]
                if r["name"] == "dt_log_to_dt_job_rollup")
    assert "target_fields" not in rule and "decision_key" not in rule


# ------------------------------------------------------------------ the mapper


@pytest.fixture(scope="module")
def mapper():
    """The tracked `.py.sample`, imported from its own path - it is the file that ships."""
    # ⚠️ AN EXPLICIT LOADER, because `.py.sample` is not a name python recognises as source
    # - `spec_from_file_location` returns None for it and the failure is an unhelpful
    # `NoneType has no attribute loader`. The extension is the whole point of the deployment
    # shape, so the test adapts rather than the file being renamed.
    spec = importlib.util.spec_from_loader(
        "dt_job_rollup_mapper_sample",
        importlib.machinery.SourceFileLoader("dt_job_rollup_mapper_sample", MAPPER))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload(job, **extra):
    return {"data": dict({"dt_job": job}, **extra)}


def test_the_mapper_counts_the_whole_job_and_not_the_batch(mapper, monkeypatch):
    """🔴 THE ARITHMETIC'S ONE REAL HAZARD. A trigger carries the rows that just arrived;
    writing `len(payloads)` would make the number mean 「how many came together」, which is not
    what `has_netdie` says and falls the moment a job arrives in two files. The affected jobs
    are named from the batch and then RE-COUNTED against the source table."""
    seen = {}

    class _Query:
        def __init__(self, jobs):
            seen["asked"] = jobs

        def filter(self, *a, **k):
            return self

        def group_by(self, *a, **k):
            return self

        def all(self):
            return [(JOB, 5)]

    class _DB:
        def query(self, *columns):
            return _Query(columns)

    monkeypatch.setattr(mapper.chain_bindings, "resolve_table", lambda rule, key: "dt_log")

    class _Column:
        """Enough of a SQLAlchemy column to be filtered on - the mapper asks the MODEL for
        its column and then `IN`s it, and a bare string would let the double pass a mapper
        that had stopped querying at all."""

        def in_(self, values):
            seen["in"] = list(values)
            return self

    class _Model:
        dt_job = _Column()

    from database import models
    monkeypatch.setitem(models.DYNAMIC_TABLES, "dt_log", _Model)

    result = mapper.build_dt_job_rollup_rows(
        _DB(), [payload(JOB, dt_eqp="EQP-7"), payload(JOB, dt_eqp="EQP-7")], rule={})

    assert len(result["updates"]) == 1, "one row per job, however many rows arrived"
    item = result["updates"][0]
    assert item["business_key_val"] == JOB
    assert item["updates"]["netdie_count"] == 5, (
        "the count is the job's, not the batch's - two payloads arrived and the job has five")
    assert seen["in"] == [JOB], "the recount asks the source table about the jobs it saw"


def test_a_row_with_no_job_makes_no_row(mapper):
    """A row that names no job cannot be counted into one and cannot make an identity."""
    assert mapper.build_dt_job_rollup_rows(None, [payload("  "), payload(None)],
                                           rule={})["updates"] == []
    assert mapper.build_dt_job_rollup_rows(None, [], rule={})["updates"] == []


def test_the_carried_columns_ride_along_because_the_atoms_need_them(mapper):
    """⚠️ `dt_eqp` IS AN ATTRIBUTE OF THE ENTITY, so it rides on the register atom's
    qualifiers - leaving it out of the table would change the atoms, which is the one thing
    this round promises not to do. `event_time` is carried because both sentences REQUIRE an
    `occurred_at` role whose binding is checked against the relation's columns."""
    assert mapper.CARRIED_COLUMNS == ("dt_eqp", "event_time")
