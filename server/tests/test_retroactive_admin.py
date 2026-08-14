"""[Queue 25] The admin surface over the five retroactive (backfill) operations.

Two properties carry this round, and both are proved by INJECTION rather than by
assertion (see the bottom of this file for what each injection turned red):

  * **A count route never writes.** It is a GET next to a POST that rewrites whole
    tables; the failure mode is silent and permanent.
  * **Routing R2 through admin cannot remove a human's value.** `withdraw_source`
    refuses `user` outright and skips any cell a human pinned. The route re-states
    the first refusal for a fast 400, so the interesting test is the one that
    DELETES the route's guard and drives the worker path anyway - if the safety
    lived in the route, that test would go green while the property was gone.

And one property that is about honesty rather than safety: R1 produces two counts -
cells it would WRITE and cells whose value vanished (withdrawal candidates, which
it deliberately does NOT write). A surface that added them would overstate the
writing operation by the size of the thing it refuses to do.

[Isolation] `retro_test_*` table names cannot exist in the user's gitignored
table_config (server-pm memory: the `bonding_log` trap).
"""
import json
import sys
import types

import pytest

import admin_auth
import chain_replay
import event_constants
import retroactive
from database import crud, models, schemas

TOKEN = "correct-horse-battery-staple"
HEADER = admin_auth.ADMIN_TOKEN_HEADER


@pytest.fixture()
def admin_token(monkeypatch):
    """The trigger route is behind `require_admin_token_strict`.

    conftest pops ASSY_ADMIN_TOKEN so the suite does not depend on the developer's
    shell, which means an un-tokened POST here answers 503 (fail closed) - correct,
    and asserted in test_admin_auth.py. Every test that wants to reach the handler
    must therefore configure a token, exactly as an operator does.
    """
    monkeypatch.setenv(admin_auth.ADMIN_TOKEN_ENV, TOKEN)
    return {HEADER: TOKEN}

RETRO_TABLES = {
    "retro_test_trigger": {
        "business_key": "src_key",
        "column_types": {"src_key": "string", "part_no": "string", "qty": "number"},
    },
    "retro_test_target": {
        "business_key": "part_no",
        "column_types": {"part_no": "string", "reserved": "number", "note": "string"},
    },
}

MAPPER_MODULE = "retro_test_mapper"


def _install_mapper_module():
    """A real module in `sys.modules`, so the REAL `execute_custom_mapper`
    (importlib) resolves it exactly as it resolves `mappers.production_mapper`."""
    mod = types.ModuleType(MAPPER_MODULE)

    def map_mixed(db, payloads, rule=None):
        """One column gets a value, one comes back blank.

        This is the fixture that activates the axis under test: R1 must count the
        first as "would write" and the second as "would NOT write, R2 candidate".
        A mapper that produced only values could not tell a correct implementation
        from one that adds the two numbers together.
        """
        updates = []
        for p in payloads:
            data = p.get("data") or {}
            part = (data.get("part_no") or {}).get("value")
            qty = (data.get("qty") or {}).get("value") or 0
            updates.append({"business_key_val": part,
                            "updates": {"part_no": part,
                                        "reserved": float(qty) * 2,
                                        "note": ""}})   # <- vanished under this rule
        return {"updates": updates}

    mod.map_mixed = map_mixed
    sys.modules[MAPPER_MODULE] = mod


RULE_MIXED = {
    "name": "retro_mixed", "trigger_table": "retro_test_trigger",
    "target_table": "retro_test_target", "mapper_module": MAPPER_MODULE,
    "mapper_function": "map_mixed", "is_batch": True, "enabled": True,
}


class _NoCloseSession:
    """The test session, with `close()` disarmed.

    `retroactive.execute` opens its OWN session through
    `database.database.SessionLocal` - it runs in the scheduler process, where
    nobody hands it one - and closes it in a `finally`. conftest's `db_session` is
    bound to a *different* engine, so without this the worker-path tests would
    write into an unrelated in-memory database and every assertion about the
    result would silently pass against nothing.
    """

    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest.fixture()
def retro_env(db_session, monkeypatch):
    models.init_dynamic_models(RETRO_TABLES)
    saved = dict(crud.TABLE_CONFIG)
    crud.TABLE_CONFIG.update(RETRO_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    _install_mapper_module()
    # The REAL rule loader reads the user's chain config; pin it to the test rule
    # so `find_rule` resolves without touching a gitignored file.
    monkeypatch.setattr(chain_replay, "load_rules", lambda: [RULE_MIXED])
    monkeypatch.setattr("database.database.SessionLocal",
                        lambda: _NoCloseSession(db_session))
    yield db_session
    sys.modules.pop(MAPPER_MODULE, None)
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(saved)


def _pin(db, row_id, column, source):
    """A human pinning a source on a cell. `updated_by` is NOT NULL."""
    db.add(models.CellOverwrite(
        table_name="retro_test_target", row_id=row_id, column_name=column,
        manual_priority_source=source, updated_by="a_human"))
    db.commit()


def _bk(table, row):
    cfg = crud.TABLE_CONFIG[table]
    comp = cfg.get("composite_key_source")
    if comp:
        sep = cfg.get("composite_key_separator", "_")
        return sep.join(crud.clean_str_value(row.get(c)) for c in comp)
    return crud.clean_str_value(row.get(cfg["business_key"]))


def _seed(db, table, rows, source_name="pipeline_parser", tx_id="retro_seed"):
    items = [schemas.GeneralUpdateItem(business_key_val=_bk(table, r), updates=dict(r),
                                       source_name=source_name, updated_by="test")
             for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=tx_id, silent=True))


def _layer_rows(db, source_name="chain_ingestion"):
    """`cell_sources` rows a given source holds on the target table.

    THE WITNESS FOR "did R1 write?", and the materialised column is NOT.
    `chain_ingestion` is priority 4 and `pipeline_parser` (what the fixtures seed
    with) is priority 2, so an R1 write lands in the layer while
    `compute_priority_value` correctly keeps showing the parser's value. A test
    that watched the column would therefore pass against a count route that wrote
    on every request - which is exactly what injection caught it doing.
    """
    return db.query(models.CellSource).filter(
        models.CellSource.table_name == "retro_test_target",
        models.CellSource.source_name == source_name).all()


def _target_row(db, bk):
    m = models.DYNAMIC_TABLES["retro_test_target"]
    return db.query(m).filter(m.business_key_val == bk).first()


def _outbox_rows(db, event_type=retroactive.RUN_EVENT_TYPE):
    return db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.event_type == event_type).all()


# ===========================================================================
# The inventory route
# ===========================================================================

class TestInventory:

    def test_it_lists_every_registered_operation(self, client):
        body = client.get("/admin/retroactive/operations").json()
        assert {o["op"] for o in body["operations"]} == set(retroactive.OPERATIONS)
        # Non-vacuous: an empty registry would satisfy the equality above.
        # Was 5 until R-2026-08-14-H deregistered `graph_orphans` - see
        # test_the_retired_graph_sweep_is_not_offered_as_a_button below.
        assert len(body["operations"]) == 4

    def test_the_retired_graph_sweep_is_not_offered_as_a_button(self, client):
        """R-2026-08-14-H: the old graph branch was retired and its three tables
        dropped, so the sweep that cleaned them must not remain clickable.

        This is not cosmetic. `_run_graph_orphans` calls
        `graph_orphans.run_scheduled`, whose first act is `ensure_graph_tables` -
        so the button would RECREATE the dropped tables and then report "0
        orphans", i.e. the screen would say "clean" when the truth is "I just
        remade three empty tables". The ruling fixed the execution order
        specifically to keep states like that from existing.
        """
        assert "graph_orphans" not in retroactive.OPERATIONS
        body = client.get("/admin/retroactive/operations").json()
        assert "graph_orphans" not in {o["op"] for o in body["operations"]}
        # And the route refuses it rather than answering with a stale shape.
        # 400, not 404: this surface treats an unregistered op as a bad request
        # (measured, not assumed - the first draft of this test asserted 404 and
        # was corrected by the run).
        r = client.get("/admin/retroactive/graph_orphans/count")
        assert r.status_code == 400
        assert "graph_orphans" in str(r.json()["detail"])

    def test_each_operation_declares_the_parameters_it_needs(self, client):
        ops = {o["op"]: o for o in client.get("/admin/retroactive/operations").json()
               ["operations"]}
        assert [p["name"] for p in ops["withdraw"]["params"]] == \
            ["table", "source", "columns"]
        # withdraw takes no --limit and no --chunk-size on the CLI either; a
        # parameter here that the operation does not have would be a lie the
        # client would render as a control.
        assert "limit" not in {p["name"] for p in ops["withdraw"]["params"]}

    def test_every_remaining_operation_commits_per_chunk_and_resumes(self, client):
        """The registry's odd-one-out is gone, and that changes what this pins.

        Until R-2026-08-14-H this test was
        `test_the_sweep_is_marked_as_the_one_that_is_not_like_the_others`: four
        operations wrote and resumed, and `graph_orphans` alone deleted rows and
        rolled the whole run back, so a client wording ONE confirmation for five
        buttons would have been wrong on exactly that one. With the sweep
        deregistered the registry is homogeneous again - which is worth asserting
        rather than deleting, because a future non-restartable operation added
        without saying so is the failure this guarded against all along.
        """
        ops = {o["op"]: o for o in client.get("/admin/retroactive/operations").json()
               ["operations"]}
        for op in ("chain_replay", "enrichment_backfill", "enrichment_confirm",
                   "withdraw"):
            assert ops[op]["restartable"] is True, (
                f"{op} is marked non-restartable; it commits per chunk")
        assert all(o["restartable"] is True for o in ops.values()), (
            "a non-restartable operation is registered without this test knowing; "
            "one confirmation wording no longer fits every button")

    def test_it_says_what_the_buttons_do_not_cover(self, client):
        """The CLI is not retired by this surface and the surface has to say so."""
        ops = {o["op"]: o for o in client.get("/admin/retroactive/operations").json()
               ["operations"]}
        assert any("replay-all" in x for x in ops["chain_replay"]["cli_only"])
        for o in ops.values():
            assert o["cli"], "every operation must name its CLI equivalent"


# ===========================================================================
# The counts
# ===========================================================================

class TestCountsDoNotLieAboutWhatTheyCounted:

    def test_r1_counts_writes_and_withdrawal_candidates_SEPARATELY(self, client,
                                                                   retro_env):
        """The dangerous conflation, refused.

        `map_mixed` emits three columns per row: `part_no` and `reserved` carry
        values, `note` comes back blank. R1 writes the first two and REFUSES the
        third (absence is not zero - only R2 can say "this rule no longer produces
        a value here").

        So across 2 trigger rows the honest answer is 4 cells written (2 columns x
        2 rows) and 2 withdrawal candidates (1 column x 2 rows). `affected` must be
        4. An implementation that folded the candidates in would report 6, and one
        that reported only the candidates would report 2 - both are excluded here.
        """
        db = retro_env
        _seed(db, "retro_test_trigger", [
            {"src_key": "S1", "part_no": "P1", "qty": 3},
            {"src_key": "S2", "part_no": "P2", "qty": 4}])

        body = client.get("/admin/retroactive/chain_replay/count"
                          "?rule=retro_mixed").json()

        written, candidates = 4, 2
        assert body["affected"] == written, "only the cells R1 would actually write"
        assert body["extra"]["withdrawal_candidates"] == candidates
        assert body["affected"] != written + candidates, (
            "the write count and the withdrawal candidates were summed; that "
            "overstates the writing operation by the size of the one thing R1 "
            "deliberately refuses to do")
        assert "R2" in body["extra"]["withdrawal_candidates_label"]

    def test_a_count_writes_nothing(self, client, retro_env):
        """A GET beside a POST that rewrites tables. The failure is silent."""
        db = retro_env
        _seed(db, "retro_test_trigger", [{"src_key": "S1", "part_no": "P1", "qty": 3}])
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 0}])

        assert _layer_rows(db) == [], "fixture is inert: the layer already exists"

        body = client.get("/admin/retroactive/chain_replay/count"
                          "?rule=retro_mixed").json()
        assert body["affected"] >= 1, "non-vacuous: the count must have found work"

        db.expire_all()
        assert _layer_rows(db) == [], (
            "the count route wrote a chain_ingestion layer to the target table")

    def test_a_sample_says_it_is_a_sample(self, client, retro_env):
        db = retro_env
        _seed(db, "retro_test_trigger",
              [{"src_key": f"S{i}", "part_no": f"P{i}", "qty": i} for i in range(4)])

        body = client.get("/admin/retroactive/chain_replay/count"
                          "?rule=retro_mixed&scan_limit=2").json()
        assert body["count_kind"] == retroactive.COUNT_SAMPLE
        assert body["scanned"] == 2 and body["scan_limit"] == 2
        assert body["truncated"] is True
        assert "표본" in body["detail"]

    def test_the_scan_budget_is_capped(self, client, retro_env):
        body = client.get(
            f"/admin/retroactive/chain_replay/count?rule=retro_mixed"
            f"&scan_limit={retroactive.MAX_SCAN_LIMIT * 10}").json()
        assert body["scan_limit"] == retroactive.MAX_SCAN_LIMIT

    def test_an_operation_that_walks_no_rows_reports_no_scan_budget(self, client,
                                                                    retro_env):
        """Echoing the requested budget would say a sample was taken when none was.

        `withdraw`'s count is two aggregates. It reads no row, so it has no
        denominator, and `null` is the only honest value. (`graph_orphans` was the
        other example here until R-2026-08-14-H deregistered it.)
        """
        body = client.get("/admin/retroactive/withdraw/count"
                          "?table=retro_test_target&source=chain_ingestion"
                          "&scan_limit=50").json()
        assert body["scan_limit"] is None
        assert body["scanned"] is None
        assert body["count_kind"] == retroactive.COUNT_UPPER_BOUND

    def test_an_upper_bound_is_never_presented_as_the_answer(self, client, retro_env):
        # Subject moved from `graph_orphans` to `withdraw` when R-2026-08-14-H
        # deregistered the graph sweep. Both are upper-bound counts, so the
        # property under test is unchanged - only the operation that carries it.
        body = client.get("/admin/retroactive/withdraw/count"
                          "?table=retro_test_target&source=chain_ingestion").json()
        assert body["count_kind"] == retroactive.COUNT_UPPER_BOUND
        assert body["extra"]["why_upper_bound"]
        assert "최대" in body["affected_label"]

    def test_a_typo_in_a_parameter_is_refused_not_ignored(self, client, retro_env):
        """A silently dropped parameter makes "0건" look like an answer."""
        r = client.get("/admin/retroactive/withdraw/count"
                       "?table=retro_test_target&sauce=chain_ingestion")
        assert r.status_code == 400
        assert "sauce" in r.json()["detail"]

    def test_a_missing_required_parameter_names_itself(self, client, retro_env):
        r = client.get("/admin/retroactive/withdraw/count?table=retro_test_target")
        assert r.status_code == 400
        assert "source" in r.json()["detail"]

    def test_an_unknown_operation_is_refused(self, client, retro_env):
        r = client.get("/admin/retroactive/nope/count")
        assert r.status_code == 400
        assert "nope" in r.json()["detail"]


# ===========================================================================
# `enrichment_backfill` - the operation whose route NOTHING above reaches
# ===========================================================================
#
# Every test in this file used `chain_replay`, `withdraw` or `graph_orphans`, and
# that gap is not a coverage statistic - it is why a broken route shipped. Both of
# `enrichment_backfill`'s halves did `import backfill_enrichment`, naming a module
# in `server/scripts`, which is on no runtime process's `sys.path`. The count route
# answered 400 "이 연산의 건수를 계산할 수 없습니다: No module named
# 'backfill_enrichment'" and the trigger answered 200 "queued" and then died in the
# scheduler's log. The suite was green because `test_backfill_enrichment.py` had
# put `server/scripts` on `sys.path` for its own import.
#
# So these tests drive the op through the ROUTE and through `retroactive.execute`,
# and the environment those imports resolve in is proved separately, in a child
# interpreter, by `test_prod_import_env.py` - an in-process test cannot prove it.

ENRICH_TABLES = {
    "retro_enrich_src": {
        "business_key": "log_key",
        "composite_key_source": ["equipment", "event_time", "chip_id"],
        "composite_key_separator": "_",
        "column_types": {"log_key": "string", "equipment": "string",
                         "event_time": "string", "chip_id": "string",
                         "lot_hint": "string"},
    },
    "retro_enrich_derived": {
        "business_key": "job_id",
        "composite_key_source": ["equipment", "event_time"],
        "composite_key_separator": "_",
        "column_types": {"job_id": "string", "equipment": "string",
                         "event_time": "string", "wafer_id": "string",
                         "chip_count": "number", "lot_hint": "string"},
    },
}

ENRICH_RULES = {
    "retro_enrich_rule": {
        "source_table": "retro_enrich_src",
        "derived_table": "retro_enrich_derived",
        "decision_key": ["equipment", "event_time"],
        "target_fields": ["wafer_id"],
        "list_columns": ["chip_count", "lot_hint"],
        "aggregations": {"chip_count": "count"},
    },
}


@pytest.fixture()
def retro_enrich_env(db_session, tmp_path, monkeypatch):
    """Source rows that predate the rule - the condition the backfill exists for.

    `retro_enrich_*` cannot collide with the user's gitignored table_config
    (server-pm memory: the `bonding_log` trap), and is distinct from
    `test_backfill_enrichment.py`'s `bkfl_test_*` so the two files cannot share
    state through the module-level `DYNAMIC_TABLES` registry.
    """
    import enrichment_config

    models.init_dynamic_models(ENRICH_TABLES)
    saved = dict(crud.TABLE_CONFIG)
    crud.TABLE_CONFIG.update(ENRICH_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text(json.dumps(ENRICH_RULES), encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))
    monkeypatch.setattr("database.database.SessionLocal",
                        lambda: _NoCloseSession(db_session))
    yield db_session
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(saved)


def _seed_enrich_source(db, rows):
    _seed(db, "retro_enrich_src", rows, tx_id="retro_enrich_seed")


def _seed_already_derived(db, equipment, event_time):
    """A derived identity that exists BEFORE the backfill runs.

    The backfill must count it as `already_derived` and never touch it - value
    gaps on an existing derived row are the worklist's job. Seeding it is what
    makes `distinct_combinations` and `new_combinations` different numbers, which
    is the only condition under which a test can tell them apart.
    """
    _seed(db, "retro_enrich_derived",
          [{"equipment": equipment, "event_time": event_time, "chip_count": 1}],
          tx_id="retro_enrich_pre")


def _derived_rows(db):
    m = models.DYNAMIC_TABLES["retro_enrich_derived"]
    return db.query(m).order_by(m.business_key_val.asc()).all()


def _backfill_layer_rows(db):
    """`cell_sources` rows the backfill holds. The witness for "did it write?".

    Not the materialised column, and not even the derived row count on its own -
    the file's closing note generalises it: the displayed value is not a witness
    for a write, only the layer is.
    """
    import enrichment_backfill

    return db.query(models.CellSource).filter(
        models.CellSource.table_name == "retro_enrich_derived",
        models.CellSource.source_name == enrichment_backfill.SOURCE_NAME).all()


class TestTheEnrichmentBackfillRouteIsReachable:

    def test_the_count_route_answers_instead_of_failing_to_import(self, client,
                                                                  retro_enrich_env):
        """THE REGRESSION TEST. This is the request that raised in production.

        The route catches every exception and answers 400 with the message inside,
        so the broken version was not a 500 - it was a 400 whose `detail` read
        "No module named 'backfill_enrichment'". A test that only asserted
        `status_code == 200` would be enough to catch it, but asserting the shape of
        the old failure as well makes the next reader understand what broke.
        """
        db = retro_enrich_env
        # THE FIXTURE ACTIVATES THE AXIS ON PURPOSE. One decision-key combination
        # is ALREADY derived and two are not, so `distinct_combinations` (3) and
        # `new_combinations` (2) differ. Without the pre-existing row the two are
        # equal and this test cannot tell "would create" from "exists at all" - a
        # count that reported every combination in the table would pass. Injection
        # found exactly that: the first version of this test seeded no derived row
        # and stayed green against `affected = distinct_combinations`.
        _seed_already_derived(db, "EQP0", "T0")
        _seed_enrich_source(db, [
            {"equipment": "EQP0", "event_time": "T0", "chip_id": "C0"},
            {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1",
             "lot_hint": "LOT_A"},
            {"equipment": "EQP1", "event_time": "T1", "chip_id": "C2",
             "lot_hint": "LOT_A"},
            {"equipment": "EQP2", "event_time": "T2", "chip_id": "C3",
             "lot_hint": "LOT_B"},
        ])

        r = client.get("/admin/retroactive/enrichment_backfill/count"
                       "?rule=retro_enrich_rule")

        assert r.status_code == 200, (
            f"the count route failed: {r.status_code} {r.text}")
        body = r.json()
        assert body["extra"]["already_derived"] == 1, (
            "fixture is inert: nothing is pre-existing, so 'new' and 'distinct' "
            "cannot be told apart")
        assert body["extra"]["distinct_combinations"] == 3
        assert body["affected"] == 2, (
            "`affected` must be the rows the backfill WOULD CREATE, not every "
            "combination it saw")
        assert body["affected"] != body["extra"]["distinct_combinations"]
        assert body["extra"]["source_table"] == "retro_enrich_src"
        assert body["extra"]["derived_table"] == "retro_enrich_derived"
        assert body["count_kind"] == retroactive.COUNT_SAMPLE
        assert body["scanned"] == 4

    def test_the_old_failure_shape_is_gone(self, client, retro_enrich_env):
        """Named separately because it is the only assertion that would have been
        red before the fix, and it must not be diluted by the fixture assertions
        above (any of which could break for an unrelated reason)."""
        db = retro_enrich_env
        _seed_enrich_source(db, [{"equipment": "E", "event_time": "T",
                                  "chip_id": "C"}])
        r = client.get("/admin/retroactive/enrichment_backfill/count"
                       "?rule=retro_enrich_rule")
        assert "No module named" not in r.text, (
            "the route still imports a module that is not on the runtime path")

    def test_the_count_is_a_bounded_sample_and_says_so(self, client,
                                                       retro_enrich_env):
        """`scan_limit` for THIS op, which no existing scan_limit test covered.

        It matters more here than anywhere else: `enrichment_backfill`'s CLI
        `--limit` means something completely different (new derived identities,
        while the source scan runs to the end of the table), and `scan_limit` is the
        only knob that actually bounds a request.
        """
        db = retro_enrich_env
        _seed_enrich_source(db, [
            {"equipment": f"EQP{i}", "event_time": f"T{i}", "chip_id": f"C{i}"}
            for i in range(6)])

        body = client.get("/admin/retroactive/enrichment_backfill/count"
                          "?rule=retro_enrich_rule&scan_limit=2").json()

        assert body["scanned"] == 2, "scan_limit did not bound the source read"
        assert body["scan_limit"] == 2
        assert body["truncated"] is True
        assert body["affected"] == 2, (
            "the sample must report what the sample found, not the table")
        # Non-vacuous: an unbounded read would have found all six.
        unbounded = client.get("/admin/retroactive/enrichment_backfill/count"
                               "?rule=retro_enrich_rule&scan_limit=100").json()
        assert unbounded["scanned"] == 6 and unbounded["affected"] == 6
        assert unbounded["truncated"] is False

    def test_the_bounded_count_does_not_walk_the_derived_table(self, client,
                                                               retro_enrich_env,
                                                               monkeypatch):
        """`1948338`'s bounded read, asserted through the ROUTE.

        A preview that resolved existing identities by preloading the whole derived
        table would let `scan_limit` bound the source read while the derived read
        stayed unbounded - which is the same request-path cost the sample was
        introduced to avoid.
        """
        import enrichment_backfill

        def _refuse(*a, **k):
            raise AssertionError(
                "the count preloaded every derived identity; at 10M rows that is "
                "the unbounded read scan_limit exists to prevent")

        monkeypatch.setattr(enrichment_backfill, "_load_existing_business_keys",
                            _refuse)
        _seed_enrich_source(retro_enrich_env,
                            [{"equipment": "E", "event_time": "T", "chip_id": "C"}])

        body = client.get("/admin/retroactive/enrichment_backfill/count"
                          "?rule=retro_enrich_rule").json()
        assert body["extra"].get("source_table") == "retro_enrich_src"

    def test_the_count_writes_nothing(self, client, retro_enrich_env):
        """A GET beside a POST that creates rows. The failure is silent."""
        db = retro_enrich_env
        _seed_enrich_source(db, [{"equipment": "EQP1", "event_time": "T1",
                                  "chip_id": "C1"}])
        assert _derived_rows(db) == [], "fixture is inert: derived rows already exist"

        body = client.get("/admin/retroactive/enrichment_backfill/count"
                          "?rule=retro_enrich_rule").json()
        assert body["affected"] >= 1, "non-vacuous: the count must have found work"

        db.expire_all()
        assert _derived_rows(db) == [], "the count route created derived rows"
        assert _backfill_layer_rows(db) == [], (
            "the count route wrote an enrichment_backfill layer")

    def test_an_unknown_rule_is_refused_by_name(self, client, retro_enrich_env):
        r = client.get("/admin/retroactive/enrichment_backfill/count?rule=nope")
        assert r.status_code == 400
        # The loader's own reason, surfaced - not a generic failure.
        assert "nope" in r.json()["detail"]

    def test_the_trigger_queues_this_op_and_executes_nothing(self, client,
                                                             retro_enrich_env,
                                                             admin_token):
        db = retro_enrich_env
        _seed_enrich_source(db, [{"equipment": "EQP1", "event_time": "T1",
                                  "chip_id": "C1"}])

        r = client.post("/admin/retroactive/enrichment_backfill/run",
                        json={"params": {"rule": "retro_enrich_rule"}},
                        headers=admin_token)
        assert r.status_code == 200 and r.json()["status"] == "queued"

        rows = _outbox_rows(db)
        assert len(rows) == 1
        payload = json.loads(rows[0].payload) if isinstance(rows[0].payload, str) \
            else rows[0].payload
        assert payload["op"] == "enrichment_backfill"
        assert payload["params"] == {"rule": "retro_enrich_rule"}

        db.expire_all()
        assert _derived_rows(db) == [], (
            "the trigger route ran the backfill inline instead of queueing it")

    def test_the_worker_half_runs_and_creates_the_rows(self, retro_enrich_env):
        """The SECOND broken import site.

        `_run_enrichment_backfill` had the same `import backfill_enrichment`, and it
        failed further from the operator than the count did: the trigger answered
        200 "queued", and the run then failed inside the scheduler thread, where
        `execute` catches everything and returns `status="error"` to a log nobody was
        watching. A green button and no rows.
        """
        db = retro_enrich_env
        _seed_enrich_source(db, [
            {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1"},
            {"equipment": "EQP1", "event_time": "T1", "chip_id": "C2"},
            {"equipment": "EQP2", "event_time": "T2", "chip_id": "C3"},
        ])

        out = retroactive.execute(
            {"run_id": "bkfl", "op": "enrichment_backfill",
             "params": {"rule": "retro_enrich_rule"}}, log=lambda m: None)

        assert out["status"] == "ok", f"the worker path failed: {out['error']}"
        assert out["result"]["created_rows"] == 2
        assert out["result"]["rows_scanned"] == 3

        db.expire_all()
        assert len(_derived_rows(db)) == 2
        assert _backfill_layer_rows(db), (
            "rows exist but carry no enrichment_backfill layer")

    def test_the_backfill_layer_can_never_outrank_a_human(self, retro_enrich_env):
        """Provenance, asserted on the ADMIN path rather than only the CLI's.

        `enrichment_backfill` is deliberately absent from `SOURCE_PRIORITY`, so it
        resolves to 99 and loses to `user` (0). Routing the operation through an
        admin button must not change that - the button is a new caller, not a new
        privilege.
        """
        import enrichment_backfill

        db = retro_enrich_env
        _seed_enrich_source(db, [{"equipment": "EQP1", "event_time": "T1",
                                  "chip_id": "C1"}])
        retroactive.execute({"run_id": "prov", "op": "enrichment_backfill",
                             "params": {"rule": "retro_enrich_rule"}},
                            log=lambda m: None)

        layer = _backfill_layer_rows(db)
        assert layer, "non-vacuous: the run wrote no layer at all"
        assert {s.source_name for s in layer} == {enrichment_backfill.SOURCE_NAME}
        assert crud.get_source_priority(enrichment_backfill.SOURCE_NAME) == 99
        assert crud.get_source_priority("user") == 0

    def test_a_failed_backfill_does_not_kill_the_scheduler(self, retro_enrich_env):
        out = retroactive.execute({"run_id": "x", "op": "enrichment_backfill",
                                   "params": {"rule": "does_not_exist"}},
                                  log=lambda m: None)
        assert out["status"] in ("error", "refused") and out["error"]


class TestTheWithdrawalPreviewMatchesTheOperationItPreviews:
    """A preview computed from a different predicate than the run is a preview
    that lies, and it would lie silently."""

    def _two_sources_on_one_cell(self, db):
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 10}],
              source_name="pipeline_parser")
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 20}],
              source_name="chain_ingestion")
        return _target_row(db, "P1")

    def test_the_cheap_count_agrees_with_the_runs_own_dry_run(self, retro_env):
        db = retro_env
        self._two_sources_on_one_cell(db)

        cheap = chain_replay.count_withdrawable(db, "retro_test_target",
                                                "chain_ingestion")
        full = chain_replay.withdraw_source(db, "retro_test_target", "chain_ingestion",
                                            apply=False, log=lambda m: None)
        assert cheap["cells_claimed"] == full["cells_matched"]
        # Non-vacuous: 0 == 0 would satisfy the line above.
        assert cheap["cells_claimed"] > 0

    def test_a_human_pinned_cell_is_subtracted_from_the_preview(self, retro_env):
        db = retro_env
        row = self._two_sources_on_one_cell(db)
        _pin(db, row.row_id, "reserved", "chain_ingestion")

        # Scoped to the pinned column: seeding a row claims every column in it
        # (`part_no` too), and this test is about the pin, not about arity. The
        # scope also exercises the `columns` allowlist the CLI exposes.
        c = chain_replay.count_withdrawable(db, "retro_test_target",
                                            "chain_ingestion", columns=["reserved"])
        assert c["cells_claimed"] == 1 and c["pinned"] == 1
        assert max(0, c["cells_claimed"] - c["pinned"]) == 0, (
            "a cell a human pinned to this source is never withdrawn, so it must "
            "not be counted as one that would be")

    def test_a_pin_naming_a_DIFFERENT_source_does_not_subtract(self, retro_env):
        """Guards the join: counting pins on the table rather than pins ON THIS
        SOURCE would understate the result by every unrelated pin."""
        db = retro_env
        row = self._two_sources_on_one_cell(db)
        _pin(db, row.row_id, "reserved", "pipeline_parser")

        c = chain_replay.count_withdrawable(db, "retro_test_target",
                                            "chain_ingestion", columns=["reserved"])
        assert c["pinned"] == 0 and c["cells_claimed"] == 1


# ===========================================================================
# The trigger
# ===========================================================================

class TestTheTriggerQueuesAndReturns:

    def test_it_publishes_one_outbox_event_and_executes_nothing(self, client,
                                                                retro_env,
                                                                admin_token):
        """A retroactive run walks a whole table; a synchronous handler would hold
        the request until the browser gave up."""
        db = retro_env
        _seed(db, "retro_test_trigger", [{"src_key": "S1", "part_no": "P1", "qty": 3}])
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 0}])

        r = client.post("/admin/retroactive/chain_replay/run",
                        json={"params": {"rule": "retro_mixed"}},
                        headers=admin_token)
        assert r.status_code == 200
        assert r.json()["status"] == "queued" and r.json()["run_id"]

        rows = _outbox_rows(db)
        assert len(rows) == 1
        payload = json.loads(rows[0].payload) if isinstance(rows[0].payload, str) \
            else rows[0].payload
        assert payload["op"] == "chain_replay"
        assert payload["params"] == {"rule": "retro_mixed"}
        assert rows[0].processed_chain is False

        db.expire_all()
        assert _layer_rows(db) == [], (
            "the trigger route executed the run inline instead of queueing it")

    def test_a_refused_request_queues_nothing(self, client, retro_env, admin_token):
        r = client.post("/admin/retroactive/withdraw/run",
                        json={"params": {"table": "retro_test_target"}},
                        headers=admin_token)
        assert r.status_code == 400
        assert _outbox_rows(retro_env) == [], (
            "a rejected request left a job in the outbox for a worker to run")

    def test_the_event_type_is_a_declared_control_event(self):
        """An unlisted control type falls through into the chain worker's grouping
        logic, where a trigger payload is read as a set of changed rows."""
        assert retroactive.RUN_EVENT_TYPE in event_constants.CONTROL_EVENT_TYPES
        assert event_constants.EVENT_SCHEDULER_RUN_NOW in \
            event_constants.CONTROL_EVENT_TYPES

    def test_the_chain_worker_filters_on_the_set_not_a_literal(self):
        """Textual, in this file's established style: a THIRD control type added
        later must not need someone to remember this call site."""
        import inspect

        import chain_ingestion_worker

        src = inspect.getsource(chain_ingestion_worker.start_chain_ingestion_worker)
        assert "CONTROL_EVENT_TYPES" in src, (
            "the chain worker skips control events by name; a new control type "
            "would be processed as a data transaction")


# ===========================================================================
# The safety property: admin cannot remove a human's value
# ===========================================================================

class TestAdminCannotRemoveAHumansValue:
    """R2's two refusals live in `withdraw_source`. Routing through admin must not
    move them, weaken them, or depend on the route re-stating them."""

    def _user_value_over_a_chain_value(self, db):
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 10}],
              source_name="chain_ingestion")
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 99}],
              source_name="user")
        row = _target_row(db, "P1")
        assert crud.clean_str_value(row.reserved) == crud.clean_str_value(99), (
            "fixture is inert: the user layer is not the visible value")
        return row

    def test_the_route_refuses_to_withdraw_user(self, client, retro_env,
                                               admin_token):
        db = retro_env
        self._user_value_over_a_chain_value(db)
        r = client.post("/admin/retroactive/withdraw/run",
                        json={"params": {"table": "retro_test_target",
                                         "source": "user"}},
                        headers=admin_token)
        assert r.status_code == 400
        assert "human" in r.json()["detail"]
        assert _outbox_rows(db) == []

    def test_the_count_route_refuses_it_too(self, client, retro_env):
        """Otherwise the admin page renders "3 cells would be withdrawn" next to a
        button that refuses - which reads as a bug in the button."""
        r = client.get("/admin/retroactive/withdraw/count"
                       "?table=retro_test_target&source=user")
        assert r.status_code == 400

    def test_it_is_still_refused_with_the_ROUTE_GUARD_REMOVED(self, retro_env,
                                                              monkeypatch):
        """The load-bearing test of this round.

        `retroactive.validate` re-states the `user` refusal so the operator gets a
        400 instead of a queued job that dies in a worker log. That check is
        CONVENIENCE. The safety property is inside `withdraw_source`, and the only
        way to prove which one is holding is to delete the convenience and drive
        the worker path anyway.

        If the refusal lived only in the route, this test goes green on the
        `status` assertion and RED on the value assertion - the human's 99 would be
        gone. That is precisely the failure the previous rounds' hollow tests could
        not have detected.
        """
        db = retro_env
        self._user_value_over_a_chain_value(db)

        # Delete the route-level guard: validate now passes `user` straight through.
        monkeypatch.setattr(retroactive, "validate",
                            lambda op, params: dict(params or {}))

        out = retroactive.execute(
            {"run_id": "inj", "op": "withdraw",
             "params": {"table": "retro_test_target", "source": "user"}},
            log=lambda m: None)

        assert out["status"] == "error", (
            "with the route guard removed, the worker path ACCEPTED a request to "
            "withdraw the user layer")
        assert "human" in (out["error"] or "")

        db.expire_all()
        assert crud.clean_str_value(_target_row(db, "P1").reserved) == \
            crud.clean_str_value(99), "a human's value was removed"
        assert "user" in {
            s.source_name for s in db.query(models.CellSource).filter(
                models.CellSource.table_name == "retro_test_target",
                models.CellSource.column_name == "reserved").all()}, \
            "the user's cell_sources row was deleted"

    def test_a_human_pinned_source_survives_a_run_through_admin(self, retro_env):
        """The second refusal, end to end on the worker path.

        The pin is a human saying "show me this one". Honouring the withdrawal
        would override that choice silently.
        """
        db = retro_env
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 10}],
              source_name="pipeline_parser")
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 20}],
              source_name="chain_ingestion")
        _pin(db, _target_row(db, "P1").row_id, "reserved", "chain_ingestion")

        out = retroactive.execute(
            {"run_id": "pin", "op": "withdraw",
             "params": {"table": "retro_test_target", "source": "chain_ingestion",
                        "columns": "reserved"}},
            log=lambda m: None)

        assert out["status"] == "ok"
        assert out["result"]["pinned_skipped"] == 1
        assert out["result"]["cells_withdrawn"] == 0
        assert "chain_ingestion" in {
            s.source_name for s in db.query(models.CellSource).filter(
                models.CellSource.table_name == "retro_test_target",
                models.CellSource.column_name == "reserved").all()}, \
            "a source a human pinned was withdrawn anyway"

    def test_an_unpinned_source_IS_withdrawn(self, retro_env):
        """Non-vacuity for the two tests above: a `withdraw_source` that refused
        everything would satisfy both of them.
        """
        db = retro_env
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 10}],
              source_name="pipeline_parser")
        _seed(db, "retro_test_target", [{"part_no": "P1", "reserved": 20}],
              source_name="chain_ingestion")

        out = retroactive.execute(
            {"run_id": "ok", "op": "withdraw",
             "params": {"table": "retro_test_target", "source": "chain_ingestion",
                        "columns": "reserved"}},
            log=lambda m: None)

        assert out["status"] == "ok"
        assert out["result"]["cells_withdrawn"] == 1
        assert out["result"]["revealed"] == 1
        db.expire_all()
        assert crud.clean_str_value(_target_row(db, "P1").reserved) == \
            crud.clean_str_value(10), "the layer underneath was not revealed"


# ===========================================================================
# The worker side
# ===========================================================================

class TestTheSchedulerRunsItOffTheTickThread:

    def test_a_run_does_not_execute_on_the_tick(self):
        """`run()` beats once per tick and `DEFAULT_STALE_AFTER_SEC` is 60 s.

        A retroactive run executed inline - the way `run_collector_on_demand`
        executes a collector - would stop the beat for the whole run and make
        /health report this daemon WEDGED. An operator pressing an offered button
        would take the monitoring surface down as a direct consequence.
        """
        import threading

        import run_auto_update
        from utils import heartbeat

        assert heartbeat.DEFAULT_STALE_AFTER_SEC <= 60.0, (
            "the staleness budget changed; re-check that an inline run is still "
            "the wrong shape")

        sched = run_auto_update.MultiDiscoveryScheduler.__new__(
            run_auto_update.MultiDiscoveryScheduler)
        sched._retroactive_thread = None
        sched._retroactive_last = None

        started = threading.Event()
        release = threading.Event()

        def slow(payload, log=None):
            started.set()
            release.wait(5)
            return {"status": "ok"}

        import retroactive as retro_mod
        original = retro_mod.execute
        retro_mod.execute = slow
        try:
            assert sched.start_retroactive_run({"run_id": "a", "op": "graph_orphans"})
            assert started.wait(5), "the run never started"
            # The tick thread is free while the run is in flight: this call returns
            # rather than blocking behind it.
            assert sched.retroactive_busy() is True
            # ...and a second request is REFUSED, not queued into a concurrent run.
            assert sched.start_retroactive_run({"run_id": "b", "op": "graph_orphans"}) \
                is False
        finally:
            release.set()
            if sched._retroactive_thread:
                sched._retroactive_thread.join(5)
            retro_mod.execute = original

        assert sched.retroactive_busy() is False

    def test_the_scheduler_consumes_the_declared_event_type(self):
        import inspect

        import run_auto_update

        src = inspect.getsource(run_auto_update.MultiDiscoveryScheduler.run)
        assert "EVENT_RETROACTIVE_RUN" in src
        assert "start_retroactive_run" in src

    def test_a_failed_run_does_not_kill_the_daemon(self, retro_env):
        """Same rule as `config_backup.run_scheduled` and
        `graph_orphans.run_scheduled`: a maintenance failure must not take the
        scheduler down."""
        out = retroactive.execute({"run_id": "x", "op": "chain_replay",
                                   "params": {"rule": "does_not_exist"}},
                                  log=lambda m: None)
        assert out["status"] in ("error", "refused")
        assert out["error"]

    def test_an_unknown_op_on_the_worker_side_is_refused_by_name(self):
        out = retroactive.execute({"run_id": "x", "op": "nope"}, log=lambda m: None)
        assert out["status"] == "refused" and "nope" in out["error"]


# ===========================================================================
# INJECTION RECORD - 2026-07-31
#
# Every test above was run against a deliberately broken implementation to check
# it can fail. 10 defects injected, 10 turned the named test RED:
#
#   defect injected                                     caught by
#   --------------------------------------------------- -------------------------
#   affected = cells_proposed + skipped_blank_cells      ..._SEPARATELY
#   the count calls replay_rule(apply=True)              test_a_count_writes_nothing
#   withdraw_source drops the PROTECTED_SOURCES refusal  ..._with_the_ROUTE_GUARD_REMOVED
#   withdraw_source stops skipping pinned cells          ..._pinned_source_survives_...
#   count_withdrawable stops sharing _claimed_filter     ..._agrees_with_the_runs_own_dry_run
#   the pin join drops `== source_name`                  ..._a_pin_naming_a_DIFFERENT_source...
#   publish() runs the operation before queueing it      ..._publishes_one_outbox_event_...
#   validate() stops reporting unknown parameters        ..._a_typo_in_a_parameter_is_refused...
#   start_retroactive_run() runs inline, not on a thread ..._does_not_execute_on_the_tick
#   a non-scanning count echoes the scan budget          ..._reports_no_scan_budget
#
# TWO OF THESE WERE HOLLOW ON THE FIRST PASS and the injection is the only reason
# it is known. `test_a_count_writes_nothing` and the trigger's "executes nothing"
# assertion both watched the MATERIALISED COLUMN, and both stayed green while the
# injected code wrote on every request.
#
# The reason is layering, and it is worth keeping: R1 writes as `chain_ingestion`
# (SOURCE_PRIORITY 4) while these fixtures seed as `pipeline_parser` (2), so
# `compute_priority_value` correctly keeps displaying the parser's value and the
# column never moves. The write was real and invisible. Both assertions now watch
# `cell_sources` - the layer R1 actually writes - via `_layer_rows`.
#
# Generalisation for anything that tests a writer in this codebase: the displayed
# value is not a witness for "did a write happen". Only the layer is.
