"""[F9] The two admin surfaces that answer 「내 config가 먹었는가」.

The report SHAPE is pinned by `contracts/config_resolve_report/` (and reachable from this
suite via `test_config_resolve_report_contract.py`). This file covers the ROUTES: that they
exist, that they are gated, that the dry-run never writes, and - the case that matters most
- that a rule with no `candidate_for` declaration comes back as a NAMED refusal rather than
a 500 or a silent zero. That is the state live production is in right now.

[Isolation] `f9rt_test_*` table names cannot exist in the user's gitignored table_config
(server-pm memory: the `bonding_log` trap).
"""
import json

import pytest

import config_resolve_report as crr
import enrichment_candidates
import enrichment_config
from database import crud, models, schemas

RT_TABLES = {
    "f9rt_test_src": {
        "business_key": "log_key",
        "composite_key_source": ["lot", "slot", "chip_id"],
        "composite_key_separator": "_",
        "column_types": {"log_key": "string", "lot": "string", "slot": "string",
                         "chip_id": "string"},
    },
    "f9rt_test_derived": {
        "business_key": "wafer_key",
        "composite_key_source": ["lot", "slot"],
        "composite_key_separator": "_",
        "column_types": {"wafer_key": "string", "lot": "string", "slot": "string",
                         "wafer_id": "string"},
    },
    "f9rt_test_hist": {
        "business_key": "hist_id",
        "column_types": {"hist_id": "string", "lot": "string", "slot": "string",
                         "wafer_id": "string"},
    },
}

NARROW = {
    "label": "narrow (lot+slot)",
    "query": "SELECT wafer_id, slot FROM f9rt_test_hist WHERE lot = :lot AND slot = :slot",
    "candidate_for": {"wafer_id": "wafer_id"},
}
UNDECLARED = {
    "label": "display only",
    "query": "SELECT wafer_id, slot FROM f9rt_test_hist WHERE lot = :lot AND slot = :slot",
}


def _rule(views, auto_confirm=True):
    return {
        "source_table": "f9rt_test_src",
        "derived_table": "f9rt_test_derived",
        "decision_key": ["lot", "slot"],
        "target_fields": ["wafer_id"],
        "auto_confirm": auto_confirm,
        "reference_views": views,
    }


def _seed(db, table, rows):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name="pipeline_parser",
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id="f9rt_seed", silent=True))


@pytest.fixture()
def rt_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(RT_TABLES)
    saved = dict(crud.TABLE_CONFIG)
    crud.TABLE_CONFIG.update(RT_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    rules_path = tmp_path / "enrichment_rules.json"
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))
    settings_path = tmp_path / "ingestion_settings.json"
    settings_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(enrichment_candidates, "INGESTION_SETTINGS_PATH", str(settings_path))
    enrichment_candidates.reset_warnings()

    def write(rules):
        rules_path.write_text(json.dumps(rules), encoding="utf-8")

    yield db_session, write
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(saved)


# ---------------------------------------------------------------------------
# GET /admin/config/resolve
# ---------------------------------------------------------------------------

def test_resolve_report_route_returns_the_three_populations(client, rt_env):
    _db, write = rt_env
    write({"f9rt_rule": _rule([NARROW])})
    r = client.get("/admin/config/resolve")
    assert r.status_code == 200
    body = r.json()
    assert body["vocabulary"]["reasons"] == list(crr.REASONS)
    domain = next(d for d in body["domains"] if d["domain"] == crr.DOMAIN_ENRICHMENT)
    assert [e["subject"] for e in domain["effective"]] == ["f9rt_rule"]
    assert domain["counts"]["effective"] == 1


def test_resolve_report_names_the_live_defect_class(client, rt_env):
    """`auto_confirm: true` with no `candidate_for` - ON in the file, inert in fact.

    Before this round the only witness was one warn-once line in a daemon log.
    """
    _db, write = rt_env
    write({"f9rt_rule": _rule([UNDECLARED])})
    domain = next(d for d in client.get("/admin/config/resolve").json()["domains"]
                  if d["domain"] == crr.DOMAIN_ENRICHMENT)
    assert domain["effective"] == []
    entry = domain["ineffective"][0]
    assert entry["reason"] == crr.REASON_NOT_DECLARED
    assert entry["fields"]["auto_confirm"] is True
    assert entry["fields"]["candidate_fields"] == {"wafer_id": []}
    assert "candidate_for" in entry["detail"]


def test_resolve_report_reports_the_settings_file_it_did_not_find(client, rt_env,
                                                                  monkeypatch, tmp_path):
    """MEASURED 2026-07-30: `ingestion_settings.json` does not exist - only `.sample`.
    The global switch therefore defaults to true and nothing said so anywhere."""
    _db, write = rt_env
    write({"f9rt_rule": _rule([NARROW])})
    monkeypatch.setattr(enrichment_candidates, "INGESTION_SETTINGS_PATH",
                        str(tmp_path / "absent.json"))
    domain = next(d for d in client.get("/admin/config/resolve").json()["domains"]
                  if d["domain"] == crr.DOMAIN_ENRICHMENT)
    src = {s["key"]: s for s in domain["sources"]}["settings"]
    assert src["exists"] is False and src["status"] == "ok"
    switch = {s["key"]: s for s in domain["settings"]}[
        enrichment_candidates.GLOBAL_KILL_SWITCH_KEY]
    assert switch["value"] is True and switch["origin"] == "default"
    assert switch["path"].endswith("absent.json"), "the report must name the file it read"


def test_resolve_report_can_be_narrowed_to_one_domain(client, rt_env):
    _db, write = rt_env
    write({"f9rt_rule": _rule([NARROW])})
    body = client.get("/admin/config/resolve?domain=enrichment").json()
    assert [d["domain"] for d in body["domains"]] == [crr.DOMAIN_ENRICHMENT]
    assert client.get("/admin/config/resolve?domain=nope").json()["domains"] == []


# ---------------------------------------------------------------------------
# GET /admin/enrichment/auto-confirm/dry-run
# ---------------------------------------------------------------------------

def test_dry_run_counts_what_needs_no_human_and_writes_nothing(client, rt_env):
    db, write = rt_env
    write({"f9rt_rule": _rule([NARROW])})
    _seed(db, "f9rt_test_hist", [{"hist_id": "h1", "lot": "L1", "slot": "S1",
                                  "wafer_id": "WF1"}])
    _seed(db, "f9rt_test_derived", [{"wafer_key": "L1_S1", "lot": "L1", "slot": "S1"}])

    body = client.get("/admin/enrichment/auto-confirm/dry-run?rule=f9rt_rule").json()
    assert body["mode"] == "dry-run"
    assert body["refused_reason"] is None
    assert body["queue_size"] == 1 and body["confirmed"] == 1
    assert body["detail"]

    m = models.DYNAMIC_TABLES["f9rt_test_derived"]
    row = db.query(m).filter(m.business_key_val == "L1_S1").first()
    assert crud.clean_str_value(row.wafer_id) == "", "a dry-run must not write"


def test_dry_run_measures_a_rule_whose_knob_is_off(client, rt_env):
    """「켜면 무슨 일이 일어나는가」 has to be answerable BEFORE turning it on.

    `run_auto_confirm_sweep(ignore_knob=True)` already refuses to combine that flag
    with `apply`, so measuring an off rule cannot become writing to one.
    """
    db, write = rt_env
    write({"f9rt_rule": _rule([NARROW], auto_confirm=False)})
    _seed(db, "f9rt_test_hist", [{"hist_id": "h2", "lot": "L2", "slot": "S1",
                                  "wafer_id": "WF2"}])
    _seed(db, "f9rt_test_derived", [{"wafer_key": "L2_S1", "lot": "L2", "slot": "S1"}])
    body = client.get("/admin/enrichment/auto-confirm/dry-run?rule=f9rt_rule").json()
    assert body["confirmed"] == 1


def test_dry_run_with_no_declaration_is_a_named_refusal_not_a_crash(client, rt_env):
    """Production's current state. A 500 here would send the operator back to the log."""
    _db, write = rt_env
    write({"f9rt_rule": _rule([UNDECLARED])})
    r = client.get("/admin/enrichment/auto-confirm/dry-run?rule=f9rt_rule")
    assert r.status_code == 200
    body = r.json()
    assert body["refused_reason"] == crr.REASON_NOT_DECLARED, (
        "the dry-run must answer in the SAME closed vocabulary as the resolve report - "
        "a client reading two surfaces must not need two dictionaries")
    assert body["confirmed"] == 0 and body["detail"]


def test_dry_run_404s_on_an_unknown_rule(client, rt_env):
    _db, write = rt_env
    write({"f9rt_rule": _rule([NARROW])})
    assert client.get(
        "/admin/enrichment/auto-confirm/dry-run?rule=nope").status_code == 404


def test_dry_run_limit_is_capped_and_truncation_is_declared(client, rt_env):
    """It sits on a request path and each key costs a round trip per declaring view,
    so it looks at a SAMPLE - and says so rather than passing a partial count off as
    the whole queue."""
    import main

    db, write = rt_env
    write({"f9rt_rule": _rule([NARROW])})
    _seed(db, "f9rt_test_hist", [{"hist_id": f"h{i}", "lot": f"L{i}", "slot": "S1",
                                  "wafer_id": f"WF{i}"} for i in range(3)])
    _seed(db, "f9rt_test_derived", [{"wafer_key": f"L{i}_S1", "lot": f"L{i}",
                                     "slot": "S1"} for i in range(3)])
    body = client.get(
        "/admin/enrichment/auto-confirm/dry-run?rule=f9rt_rule&limit=2").json()
    assert body["limit"] == 2 and body["queue_size"] == 2
    assert body["truncated"] is True and "표본" in body["detail"]

    huge = client.get(
        f"/admin/enrichment/auto-confirm/dry-run?rule=f9rt_rule"
        f"&limit={main.ENRICHMENT_DRY_RUN_MAX_LIMIT * 10}").json()
    assert huge["limit"] == main.ENRICHMENT_DRY_RUN_MAX_LIMIT


def test_the_dry_run_route_offers_no_apply(client):
    """THIS route stays read-only. A query parameter is one typo away from a write.

    [2026-07-31] The F9 reasoning for this test was "writing stays on the CLI", and
    that half has been REVERSED: `POST /admin/retroactive/{op}/run` now triggers the
    same sweep's apply. The test survives the reversal unchanged because its subject
    was never "admin cannot write" - it is "a GET whose job is measuring must not
    grow a write flag". The trigger is a separate POST behind the strict token, so
    both statements are true at once. See the route's own docstring in main.py for
    which surface answers which question.
    """
    import main
    from fastapi.routing import APIRoute

    route = next(r for r in main.app.routes
                 if isinstance(r, APIRoute)
                 and r.path == "/admin/enrichment/auto-confirm/dry-run")
    params = {p.name for p in route.dependant.query_params}
    # Non-vacuous: an empty param set would make the assertion below meaningless.
    assert {"rule", "limit"} <= params, f"route params look wrong: {sorted(params)}"
    assert "apply" not in params and "ignore_knob" not in params, (
        f"the dry-run route exposes {sorted(params)}. `apply` must not be reachable "
        "over HTTP - the sweep's write path stays in enrichment_insights.py.")
