"""[Enrichment ①] "A single candidate is a confirmation, not a judgement."

Every mechanism here is proved to be able to go RED, not merely to pass:
- the DECLARATION is load-bearing (declare the wrong view -> ambiguous refusal),
- the knob actually gates (off -> value stays blank through the real chain path),
- absent-only actually refuses (pre-existing provenance -> named refusal),
- the layering actually protects a human (user edit wins after auto-confirm),
- an unevaluated view refuses instead of reading as "no candidate".

[Isolation] Table names use the `encand_test_` prefix, which cannot exist in the
user's gitignored table_config. A collision would let import-time
`init_dynamic_models` pin the real schema into the shared in-memory sqlite and
`create_all(checkfirst)` would skip ours (server-pm memory: the `bonding_log` trap).
"""
import json

import anyio
import pytest

import enrichment_candidates
import enrichment_config
from database import crud, models, schemas


def _caps(**overrides):
    """A read-cap snapshot with the shipped values and any override applied.

    Built through `load_read_caps` rather than hand-assembled, so a test that
    overrides a cap still exercises the real reader - including the `declared`
    flag the refusals report on.
    """
    caps = enrichment_config.load_read_caps({})
    for name, value in overrides.items():
        caps[name] = {"value": value, "declared": True}
    return caps

CAND_TABLES = {
    "encand_test_src": {
        "business_key": "log_key",
        "composite_key_source": ["lot", "slot", "chip_id"],
        "composite_key_separator": "_",
        "column_types": {
            "log_key": "string", "lot": "string", "slot": "string",
            "chip_id": "string",
        },
    },
    "encand_test_derived": {
        "business_key": "wafer_key",
        "composite_key_source": ["lot", "slot"],
        "composite_key_separator": "_",
        "column_types": {
            "wafer_key": "string", "lot": "string", "slot": "string",
            # TWO target columns, so "ambiguity is per column" has somewhere to
            # be false. With one target the claim is unfalsifiable.
            "wafer_id": "string", "owner": "string", "chip_count": "number",
        },
    },
    # The reference table the candidate views read. Not part of the rule.
    "encand_test_hist": {
        "business_key": "hist_id",
        "column_types": {
            "hist_id": "string", "lot": "string", "slot": "string",
            "wafer_id": "string", "owner": "string",
        },
    },
}

NARROW_VIEW = {
    "label": "narrow (lot+slot)",
    "query": "SELECT wafer_id, slot FROM encand_test_hist WHERE lot = :lot AND slot = :slot",
    "candidate_for": {"wafer_id": "wafer_id"},
}
# Same column name, WRONG grain: keyed by lot only, so it sees every slot's
# wafer. This is the DECOY - a name-matching implementation would use it.
BROAD_VIEW = {
    "label": "broad (lot only)",
    "query": "SELECT wafer_id, slot FROM encand_test_hist WHERE lot = :lot",
}
# The SECOND target's declared source, read at the same grain as NARROW_VIEW so
# both columns are asked the same question of the same key. What differs is the
# ANSWER: for L2/S1 the two history rows disagree on wafer_id and agree on owner.
OWNER_VIEW = {
    "label": "owner (lot+slot)",
    "query": "SELECT owner FROM encand_test_hist WHERE lot = :lot AND slot = :slot",
    "candidate_for": {"owner": "owner"},
}


def _rule(**overrides):
    rule = {
        "source_table": "encand_test_src",
        "derived_table": "encand_test_derived",
        "decision_key": ["lot", "slot"],
        "target_fields": ["wafer_id"],
        "list_columns": ["chip_count"],
        "aggregations": {"chip_count": "count"},
        "auto_confirm": True,
        "reference_views": [dict(NARROW_VIEW), dict(BROAD_VIEW)],
    }
    rule.update(overrides)
    return rule


@pytest.fixture()
def cand_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(CAND_TABLES)
    crud.TABLE_CONFIG.update(CAND_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text(json.dumps({"encand_rule": _rule()}), encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))

    settings_path = tmp_path / "ingestion_settings.json"
    settings_path.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(enrichment_candidates, "INGESTION_SETTINGS_PATH", str(settings_path))
    enrichment_candidates.reset_warnings()
    # Module-level throttle state. Leaking it between tests would make a test's
    # result depend on what ran before it - which is the exact class of
    # cross-test pollution this file's fixtures already work to avoid.
    enrichment_config.reset_driver_error_incidents()

    # Reference history: L1/S1 -> WF1, L1/S2 -> WF2. Keyed by lot alone this is
    # two candidates; keyed by lot+slot it is one.
    # `owner` AGREES on L2/S1 where `wafer_id` disagrees - that pair is the whole
    # per-column claim: same key, same two rows, one column determined and one not.
    _seed(db_session, "encand_test_hist", [
        {"hist_id": "H1", "lot": "L1", "slot": "S1", "wafer_id": "WF1", "owner": "ALICE"},
        {"hist_id": "H2", "lot": "L1", "slot": "S2", "wafer_id": "WF2", "owner": "BOB"},
        {"hist_id": "H3", "lot": "L2", "slot": "S1", "wafer_id": "WF3", "owner": "OPS"},
        # ambiguous even narrow - on wafer_id ONLY; owner still says OPS.
        {"hist_id": "H4", "lot": "L2", "slot": "S1", "wafer_id": "WF9", "owner": "OPS"},
    ])
    import main
    main.TABLE_COUNT_CACHE.clear()
    return db_session


def _seed(db, table, rows, source_name="pipeline_parser", tx_id="seed", silent=True):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name=source_name,
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=tx_id, silent=silent))


def _seed_raw(db, table, rows):
    """Insert into the model DIRECTLY, bypassing `crud.apply_batch_updates`.

    [Why a probe fixture is allowed to bypass the write boundary]
    `crud.cast_value_by_type` normalizes on write (`normalize_stored_text`), so a value
    like `'WF01 '` cannot land in one of THIS system's tables any more. But this module
    does not probe this system's storage - it probes a USER-DECLARED reference VIEW,
    which is arbitrary SQL and can synthesize a value that never passed through that
    boundary (a concatenation, a CAST, a join against a table nobody here manages).

    So `enrichment_candidates` must not lean on an upstream normalization invariant it
    does not own, and a fixture that can only produce canonical bytes cannot test that.
    Same reasoning, same shape as `test_virtual_join_executor._seed_raw`.
    """
    import uuid6
    model = models.DYNAMIC_TABLES[table]
    bk = crud.TABLE_CONFIG[table].get("business_key")
    for r in rows:
        db.add(model(row_id=str(uuid6.uuid7()),
                     business_key_val=str(r.get(bk, "")).strip() or None, **r))
    db.flush()


def _loaded_rule(name="encand_rule"):
    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    return next(r for r in rules if r["name"] == name)


def _derived(db, bk):
    m = models.DYNAMIC_TABLES["encand_test_derived"]
    return db.query(m).filter(m.business_key_val == bk).first()


def _run_chain_for_tx(db, tx_id, trigger_table="encand_test_src"):
    from chain_ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    rules = enrichment_config.load_enrichment_chain_rules(known_tables=crud.TABLE_CONFIG)
    assert rules, "enrichment chain rules must be synthesized"
    events = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == trigger_table,
        DatabaseOutbox.processed_chain == False,  # noqa: E712
    ).order_by(DatabaseOutbox.id.asc()).all()
    evs = [e for e in events if (e.payload or {}).get("transaction_id") == tx_id]
    assert evs, f"no pending outbox events for tx {tx_id}"

    async def run():
        ok, err, msgs = await process_chain_transaction_group(tx_id, evs, db, rules)
        assert ok, f"chain group failed: {err}"
        for e in evs:
            e.processed_chain = True
        db.commit()
    anyio.run(run)


# ---------------------------------------------------------------------------
# 1. The declaration: `candidate_for`
# ---------------------------------------------------------------------------

def test_candidate_for_normalized_and_view_without_it_is_display_only(cand_env):
    rule = _loaded_rule()
    narrow, broad = rule["reference_views"]
    assert narrow["candidate_for"] == {"wafer_id": "wafer_id"}
    assert broad["candidate_for"] == {}, "a view with no declaration must never be a candidate source"
    assert enrichment_candidates.declaring_views(rule, "wafer_id") == [narrow]
    assert enrichment_candidates.candidate_target_fields(rule) == ["wafer_id"]
    # required_binds is derived from the SQL, per view, not from the decision key.
    assert narrow["required_binds"] == ["lot", "slot"]
    assert broad["required_binds"] == ["lot"]


def test_candidate_for_rejects_non_target_and_non_string(cand_env):
    bad = dict(NARROW_VIEW, candidate_for={"lot": "wafer_id", "wafer_id": ""})
    normalized, err = enrichment_config._validate_rule(
        "r", _rule(reference_views=[bad]), CAND_TABLES)
    assert err is None
    # 'lot' is a decision key, not a target field -> rejected. '' -> rejected.
    assert normalized["reference_views"][0]["candidate_for"] == {}


def test_declaration_is_load_bearing_decoy_view_would_have_been_ambiguous(cand_env):
    """The DECOY test. Both views expose a `wafer_id` column; only one is right.

    This is the defect injection for the no-derivation rule: declaring the
    broad view too makes the SAME key ambiguous, so a derivation-based
    implementation (e.g. "use any column named like the target") would have
    auto-confirmed a value chosen by grain accident.
    """
    rule = _loaded_rule()
    keys = {"lot": "L1", "slot": "S1"}
    good = enrichment_candidates.resolve_target_candidate(cand_env, rule, keys, "wafer_id")
    assert good["status"] == enrichment_candidates.STATUS_SINGLE
    assert good["value"] == "WF1"

    # INJECTED DEFECT: the broad view is declared as a candidate source too.
    injected = dict(rule)
    injected["reference_views"] = [rule["reference_views"][0],
                                   dict(rule["reference_views"][1],
                                        candidate_for={"wafer_id": "wafer_id"})]
    bad = enrichment_candidates.resolve_target_candidate(cand_env, injected, keys, "wafer_id")
    assert bad["status"] == enrichment_candidates.STATUS_REFUSED
    assert bad["reason"] == enrichment_candidates.REASON_AMBIGUOUS
    assert set(bad["candidates"]) == {"WF1", "WF2"}


# ---------------------------------------------------------------------------
# 2. The predicate and its named refusals
# ---------------------------------------------------------------------------

def test_ambiguous_two_rows_same_key_is_a_human_judgement(cand_env):
    rule = _loaded_rule()
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, rule, {"lot": "L2", "slot": "S1"}, "wafer_id")
    assert res["status"] == enrichment_candidates.STATUS_REFUSED
    assert res["reason"] == enrichment_candidates.REASON_AMBIGUOUS
    assert res["distinct_count"] == 2


def test_no_candidate_and_not_declared_are_distinct_reasons(cand_env):
    rule = _loaded_rule()
    empty = enrichment_candidates.resolve_target_candidate(
        cand_env, rule, {"lot": "NOPE", "slot": "S1"}, "wafer_id")
    assert empty["reason"] == enrichment_candidates.REASON_NO_CANDIDATE

    undeclared = dict(rule, target_fields=["wafer_id", "other"])
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, undeclared, {"lot": "L1", "slot": "S1"}, "other")
    assert res["reason"] == enrichment_candidates.REASON_NOT_DECLARED


def test_blank_candidate_values_are_not_candidates(cand_env):
    """A blank cell in the candidate column is absence, not a candidate value."""
    _seed(cand_env, "encand_test_hist",
          [{"hist_id": "H5", "lot": "L3", "slot": "S1", "wafer_id": "  "}])
    rule = _loaded_rule()
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, rule, {"lot": "L3", "slot": "S1"}, "wafer_id")
    assert res["reason"] == enrichment_candidates.REASON_NO_CANDIDATE


def test_whitespace_and_numeric_forms_are_one_candidate_not_two(cand_env):
    """Shared normalization: 'WF7' and 'WF7 ' must not manufacture ambiguity."""
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": "H6", "lot": "L4", "slot": "S1", "wafer_id": "WF7"},
        {"hist_id": "H7", "lot": "L4", "slot": "S1", "wafer_id": "WF7 "},
    ])
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, _loaded_rule(), {"lot": "L4", "slot": "S1"}, "wafer_id")
    assert res["status"] == enrichment_candidates.STATUS_SINGLE
    assert res["value"] == "WF7"
    assert res["support"] == 2


def test_a_failed_view_refuses_even_when_a_surviving_view_agrees(cand_env):
    """ABSENCE IS NOT ZERO. An unevaluated view is UNKNOWN, so one candidate from
    the views that DID run is not enough - the failed one may have held the
    contradiction. Injection: a second declaring view whose SQL cannot execute."""
    rule = _loaded_rule()
    broken = {"label": "broken", "query": "SELECT wafer_id FROM no_such_table WHERE lot = :lot",
              "candidate_for": {"wafer_id": "wafer_id"}, "limit": 200,
              "required_binds": ["lot"]}
    injected = dict(rule, reference_views=[rule["reference_views"][0], broken])
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, injected, {"lot": "L1", "slot": "S1"}, "wafer_id")
    assert res["status"] == enrichment_candidates.STATUS_REFUSED
    assert res["reason"] == enrichment_candidates.REASON_VIEW_ERROR
    # The partial finding is still reported (a UI may show it) but must not gate.
    assert res["value"] == "WF1"
    assert res["errors"][0]["label"] == "broken"


def test_declared_column_absent_from_result_is_a_named_refusal(cand_env):
    """Also the guard on SQLite's double-quoted-string fallback (measured 2026-07-30).

    The grouped probe interpolates the column name, and SQLite DEMOTES a quoted name
    it cannot resolve into a string literal. With an unqualified reference this
    returned `single` with the value 'not_a_column' - the probe auto-confirming the
    column name itself, which is the exact lie this module must never tell. The wrap
    qualifies the reference (`__enrichment_ref."col"`), which cannot be a literal.
    """
    rule = _loaded_rule()
    wrong = dict(rule["reference_views"][0], candidate_for={"wafer_id": "not_a_column"})
    injected = dict(rule, reference_views=[wrong])
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, injected, {"lot": "L1", "slot": "S1"}, "wafer_id")
    assert res["reason"] == enrichment_candidates.REASON_CANDIDATE_COLUMN_MISSING
    assert res["value"] != "not_a_column", (
        "the probe fabricated a candidate out of the column name - the quoted "
        "identifier was demoted to a string literal")


def test_missing_bind_refuses_instead_of_executing_blindly(cand_env):
    rule = _loaded_rule()
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, rule, {"lot": "L1"}, "wafer_id")   # no slot
    assert res["reason"] == enrichment_candidates.REASON_MISSING_BIND


# ---------------------------------------------------------------------------
# 3. The knob (M3 shape) — and it really gates
# ---------------------------------------------------------------------------

def test_knob_defaults_off_and_opt_in_turns_it_on(cand_env):
    assert enrichment_candidates.rule_auto_confirm_enabled({"name": "r"}) is False
    assert enrichment_candidates.rule_auto_confirm_enabled({"name": "r", "auto_confirm": True}) is True


def test_non_boolean_knob_warns_and_falls_back_to_off(cand_env, caplog):
    with caplog.at_level("WARNING"):
        assert enrichment_candidates.rule_auto_confirm_enabled(
            {"name": "r", "auto_confirm": "true"}) is False
    assert any("expected JSON boolean" in rec.getMessage() for rec in caplog.records), \
        "a non-boolean knob must SAY it is being ignored, not fail silently"


def test_global_kill_switch_disables_every_rule(cand_env, tmp_path, monkeypatch):
    p = tmp_path / "kill.json"
    p.write_text(json.dumps({"enrichment_auto_confirm_enabled": False}), encoding="utf-8")
    monkeypatch.setattr(enrichment_candidates, "INGESTION_SETTINGS_PATH", str(p))
    assert enrichment_candidates.rule_auto_confirm_enabled({"name": "r", "auto_confirm": True}) is False
    assert enrichment_candidates.AutoConfirmCollector("encand_test_derived").active is False


def test_collector_inert_without_declaration(cand_env, tmp_path, monkeypatch):
    rules_path = tmp_path / "nodecl.json"
    rules_path.write_text(json.dumps({"encand_rule": _rule(
        reference_views=[dict(BROAD_VIEW)])}), encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))
    assert enrichment_candidates.AutoConfirmCollector("encand_test_derived").active is False


# ---------------------------------------------------------------------------
# 4. End to end through the REAL chain path — both knob positions
# ---------------------------------------------------------------------------

def test_chain_path_auto_confirms_single_candidate(cand_env):
    _seed(cand_env, "encand_test_src",
          [{"log_key": "k1", "lot": "L1", "slot": "S1", "chip_id": "C1"},
           {"log_key": "k2", "lot": "L1", "slot": "S1", "chip_id": "C2"}],
          tx_id="tx_on")
    _run_chain_for_tx(cand_env, "tx_on")
    row = _derived(cand_env, "L1_S1")
    assert row is not None
    assert row.wafer_id == "WF1", "single candidate should have been confirmed automatically"
    # Provenance: lowest priority, so nothing it writes can outrank a human.
    assert crud.get_source_priority(enrichment_candidates.SOURCE_NAME) == 99
    src = cand_env.query(models.CellSource).filter(
        models.CellSource.table_name == "encand_test_derived",
        models.CellSource.row_id == row.row_id,
        models.CellSource.column_name == "wafer_id").all()
    assert [s.source_name for s in src] == [enrichment_candidates.SOURCE_NAME]


def test_chain_path_leaves_ambiguous_key_in_the_queue(cand_env):
    """The negative control that proves the mechanism is not vacuous: same run,
    a key with two candidates stays blank and therefore stays in the worklist."""
    _seed(cand_env, "encand_test_src",
          [{"log_key": "k3", "lot": "L2", "slot": "S1", "chip_id": "C1"}], tx_id="tx_amb")
    _run_chain_for_tx(cand_env, "tx_amb")
    row = _derived(cand_env, "L2_S1")
    assert row is not None
    assert crud.clean_str_value(row.wafer_id) == "", \
        "an ambiguous key must stay visibly unresolved"


def test_knob_off_writes_nothing(cand_env, tmp_path, monkeypatch):
    rules_path = tmp_path / "off.json"
    rules_path.write_text(json.dumps({"encand_rule": _rule(auto_confirm=False)}),
                          encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))
    _seed(cand_env, "encand_test_src",
          [{"log_key": "k4", "lot": "L1", "slot": "S1", "chip_id": "C1"}], tx_id="tx_off")
    _run_chain_for_tx(cand_env, "tx_off")
    row = _derived(cand_env, "L1_S1")
    assert crud.clean_str_value(row.wafer_id) == "", "knob off must leave the target blank"


# ---------------------------------------------------------------------------
# 5. Absent-only, and the human always wins
# ---------------------------------------------------------------------------

def test_absent_only_refuses_a_cell_that_already_has_provenance(cand_env):
    _seed(cand_env, "encand_test_src",
          [{"log_key": "k5", "lot": "L1", "slot": "S1", "chip_id": "C1"}], tx_id="tx_p1")
    _run_chain_for_tx(cand_env, "tx_p1")
    row = _derived(cand_env, "L1_S1")

    # A human deliberately CLEARS the value: the display is blank again (so the
    # row is back in the queue) but the cell now carries a human's judgement.
    _seed(cand_env, "encand_test_derived",
          [{"wafer_key": "L1_S1", "lot": "L1", "slot": "S1", "wafer_id": ""}],
          source_name="user", tx_id="tx_clear", silent=False)
    row = _derived(cand_env, "L1_S1")
    assert crud.clean_str_value(row.wafer_id) == ""

    stats = enrichment_candidates.confirm_keys(
        cand_env, _loaded_rule(),
        [{"row_id": row.row_id, "business_key_val": "L1_S1",
          "keys": {"lot": "L1", "slot": "S1"}, "blank_targets": ["wafer_id"]}],
        apply=True)
    assert stats["confirmed"] == 0
    assert stats["refused"][enrichment_candidates.REASON_CELL_HAS_PROVENANCE] == 1
    row = _derived(cand_env, "L1_S1")
    assert crud.clean_str_value(row.wafer_id) == "", \
        "auto-confirm must not overwrite a human's deliberate blank"


def test_user_edit_beats_an_auto_confirmed_value(cand_env):
    _seed(cand_env, "encand_test_src",
          [{"log_key": "k6", "lot": "L1", "slot": "S1", "chip_id": "C1"}], tx_id="tx_u1")
    _run_chain_for_tx(cand_env, "tx_u1")
    assert _derived(cand_env, "L1_S1").wafer_id == "WF1"

    _seed(cand_env, "encand_test_derived",
          [{"wafer_key": "L1_S1", "lot": "L1", "slot": "S1", "wafer_id": "HUMAN_WINS"}],
          source_name="user", tx_id="tx_u2", silent=False)
    row = _derived(cand_env, "L1_S1")
    assert row.wafer_id == "HUMAN_WINS"

    # And a later re-ingestion of the same source rows must not undo that.
    _seed(cand_env, "encand_test_src",
          [{"log_key": "k7", "lot": "L1", "slot": "S1", "chip_id": "C3"}], tx_id="tx_u3")
    _run_chain_for_tx(cand_env, "tx_u3")
    assert _derived(cand_env, "L1_S1").wafer_id == "HUMAN_WINS"


def test_per_unit_cap_leaves_the_remainder_in_the_queue(cand_env, tmp_path, monkeypatch):
    p = tmp_path / "cap.json"
    p.write_text(json.dumps({"enrichment_auto_confirm_max_keys": 1}), encoding="utf-8")
    monkeypatch.setattr(enrichment_candidates, "INGESTION_SETTINGS_PATH", str(p))
    _seed(cand_env, "encand_test_hist",
          [{"hist_id": "H8", "lot": "L5", "slot": "S1", "wafer_id": "WF5"}])
    _seed(cand_env, "encand_test_src",
          [{"log_key": "k8", "lot": "L1", "slot": "S1", "chip_id": "C1"},
           {"log_key": "k9", "lot": "L5", "slot": "S1", "chip_id": "C1"}], tx_id="tx_cap")
    _run_chain_for_tx(cand_env, "tx_cap")
    confirmed = [bk for bk in ("L1_S1", "L5_S1")
                 if crud.clean_str_value(getattr(_derived(cand_env, bk), "wafer_id", "")) != ""]
    assert len(confirmed) == 1, "the cap must bound the probe, not silently drop the rest"


# ---------------------------------------------------------------------------
# 5-bis. The probe reads the WHOLE result, not the first `limit` rows
#        [F9, 2026-07-30] The live `wafer_process` view declares `limit: 50` while
#        every one of 80 (lot,slot) keys returns 69..217 rows. Counting distinct
#        values in Python AFTER the server truncated made `ambiguous` unreachable
#        past row 50 - `single` rested on the mapping happening to be functional,
#        which nothing checked.
# ---------------------------------------------------------------------------

def test_a_contradiction_past_the_view_limit_still_makes_it_ambiguous(cand_env):
    """THE MEASURED DEFECT, as a test. Row 3 of 3 disagrees; the view shows 2.

    With the old row-limited read this returned `single` (WF1, support 2) and would
    have auto-confirmed a value chosen by where the LIMIT happened to fall.
    """
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": "T1", "lot": "LT", "slot": "S1", "wafer_id": "WF1"},
        {"hist_id": "T2", "lot": "LT", "slot": "S1", "wafer_id": "WF1"},
        {"hist_id": "T3", "lot": "LT", "slot": "S1", "wafer_id": "WFX"},
    ])
    rule = _loaded_rule()
    narrow = dict(rule["reference_views"][0], limit=2)   # truncates before WFX
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, dict(rule, reference_views=[narrow]), {"lot": "LT", "slot": "S1"},
        "wafer_id")
    assert res["status"] == enrichment_candidates.STATUS_REFUSED
    assert res["reason"] == enrichment_candidates.REASON_AMBIGUOUS
    assert set(res["candidates"]) == {"WF1", "WFX"}


def test_support_counts_every_row_not_just_the_first_limit(cand_env):
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"S{i}", "lot": "LS", "slot": "S1", "wafer_id": "WF1"}
        for i in range(5)
    ])
    rule = _loaded_rule()
    narrow = dict(rule["reference_views"][0], limit=2)
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, dict(rule, reference_views=[narrow]), {"lot": "LS", "slot": "S1"},
        "wafer_id")
    assert res["status"] == enrichment_candidates.STATUS_SINGLE
    assert res["support"] == 5, "support must be a count over the whole result"
    assert res["evidence"][0]["rows"] == 5


def test_a_truncated_probe_refuses_instead_of_claiming_single(cand_env):
    """A truncated READ cannot prove 'exactly one' - the unread remainder may hold
    the contradiction. Same posture as `view_error`: incomplete is UNKNOWN, not empty.

    `probe_scan_rows` is the only thing bounding a candidate-declaring view with no
    binds, which would otherwise scan its whole table once per probed key.

    The cap arrives as a DECLARED value in the caps snapshot, not as a patched
    module constant, so this exercises the config path an operator actually has.
    """
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"P{i}", "lot": "LP", "slot": "S1", "wafer_id": "WF1"}
        for i in range(4)
    ])
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, _loaded_rule(), {"lot": "LP", "slot": "S1"}, "wafer_id",
        caps=_caps(probe_scan_rows=2))
    assert res["status"] == enrichment_candidates.STATUS_REFUSED
    assert res["reason"] == enrichment_candidates.REASON_PROBE_TRUNCATED
    # The partial finding is still reported so a UI can show it; it just cannot gate.
    assert res["value"] == "WF1"


def test_a_truncation_refusal_names_the_cap_that_cut_it_and_where_to_set_it(cand_env):
    """[2026-08-05 incident] The refusal must name its own repair.

    Told only that a read was clipped, an operator raised the CLI's key budget -
    the one number spelled `limit` they could reach - and nothing changed. So the
    error carries the CAP's config name, its value, whether anyone declared it,
    and the file+key to edit. Asserting the exact cap name is the point: a refusal
    that said `limit` would be the defect restored.
    """
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"C{i}", "lot": "LC", "slot": "S1", "wafer_id": "WF1"}
        for i in range(4)
    ])
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, _loaded_rule(), {"lot": "LC", "slot": "S1"}, "wafer_id",
        caps=_caps(probe_scan_rows=2))
    err = res["errors"][0]
    assert err["cap"] == enrichment_config.CAP_PROBE_SCAN_ROWS
    assert err["cap"] != "limit"
    assert err["cap_value"] == 2
    assert err["cap_declared"] is True
    assert enrichment_config.READ_CAPS_SETTINGS_KEY in err["cap_home"]
    assert "ingestion_settings.json" in err["cap_home"]


def test_an_undeclared_cap_says_so_in_the_refusal(cand_env):
    """Absence must not be invisible. An operator refused by a cap NOBODY set has
    no way to learn the knob exists unless the refusal tells them - and that
    ignorance is exactly what made the incident expensive.

    Uses the shipped `probe_distinct_values`, which is undeclared by design: it
    inherits the view's own display `limit`.
    """
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"U{i}", "lot": "LU", "slot": "S1", "wafer_id": f"W{i}"}
        for i in range(4)
    ])
    rule = _loaded_rule()
    narrow = dict(rule["reference_views"][0], limit=1)
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, dict(rule, reference_views=[narrow]), {"lot": "LU", "slot": "S1"},
        "wafer_id", caps=_caps())
    err = next(e for e in res["errors"]
               if e["reason"] == enrichment_candidates.REASON_DISTINCT_TRUNCATED)
    assert err["cap"] == enrichment_config.CAP_PROBE_DISTINCT_VALUES
    assert err["cap_declared"] is False, (
        "undeclared must read as undeclared - reporting the inherited number as a "
        "declaration hides the fact that nobody ever chose it")
    assert err["cap_value"] == 1, "undeclared inherits the view's own row limit"


def test_the_refusal_says_whether_a_bigger_cap_could_even_help(cand_env):
    """Two outcomes, two repairs, and the refusal must not merge them.

    A clipped read that ALREADY holds two different values cannot become `single`
    at any cap - raising it renames the refusal `ambiguous`, which is a person's
    judgement. A clipped read holding one value so far is genuinely unknown.
    Offering "a bigger number" for the first case sends someone to turn a knob
    that cannot work.
    """
    rule = _loaded_rule()
    narrow = dict(rule["reference_views"][0], limit=1)

    # Two DIFFERENT values already read -> a bigger cap yields `ambiguous`.
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"A{i}", "lot": "LA", "slot": "S1", "wafer_id": f"W{i}"}
        for i in range(4)
    ])
    amb = enrichment_candidates.resolve_target_candidate(
        cand_env, dict(rule, reference_views=[narrow]), {"lot": "LA", "slot": "S1"},
        "wafer_id", caps=_caps())
    err = next(e for e in amb["errors"]
               if e["reason"] == enrichment_candidates.REASON_DISTINCT_TRUNCATED)
    assert err["distinct_values_read"] >= 2
    assert err["expected_if_raised"] == enrichment_candidates.EXPECT_AMBIGUOUS

    # One value read so far -> the remainder may agree or may not. Say unknown.
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"K{i}", "lot": "LK", "slot": "S1", "wafer_id": "WSAME"}
        for i in range(4)
    ])
    unk = enrichment_candidates.resolve_target_candidate(
        cand_env, dict(rule, reference_views=[narrow]), {"lot": "LK", "slot": "S1"},
        "wafer_id", caps=_caps(probe_scan_rows=2))
    err = next(e for e in unk["errors"]
               if e["reason"] == enrichment_candidates.REASON_PROBE_TRUNCATED)
    assert err["distinct_values_read"] <= 1
    assert err["expected_if_raised"] == enrichment_candidates.EXPECT_UNKNOWN


def test_the_two_outcomes_are_counted_apart_in_the_sweep_stats(cand_env):
    """`distinct_truncated=76` is not an instruction. Split by what a bigger cap
    would do, it becomes two: N that a knob resolves, M that a person must judge.
    The census is keyed by CAP NAME so the operator is told what to turn."""
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"S{i}", "lot": "LS2", "slot": "S1", "wafer_id": f"W{i}"}
        for i in range(4)
    ])
    _seed(cand_env, "encand_test_derived",
          [{"wafer_key": "LS2_S1", "lot": "LS2", "slot": "S1"}])
    rule = _loaded_rule()
    narrow = dict(rule["reference_views"][0], limit=1)
    st = enrichment_candidates.confirm_keys(
        cand_env, dict(rule, reference_views=[narrow]),
        [{"row_id": None, "business_key_val": "LS2_S1",
          "keys": {"lot": "LS2", "slot": "S1"}, "blank_targets": ["wafer_id"]}],
        apply=False, caps=_caps())
    slot = st["cap_hits"][enrichment_config.CAP_PROBE_DISTINCT_VALUES]
    assert slot["hits"] == 1
    assert slot[enrichment_candidates.EXPECT_AMBIGUOUS] == 1
    assert slot[enrichment_candidates.EXPECT_UNKNOWN] == 0
    assert slot["cap_declared"] is False
    assert "ingestion_settings.json" in slot["cap_home"]


def test_the_display_path_keeps_its_row_limit(cand_env):
    """One declaration, two execution shapes. The human display still needs ROWS,
    ordered - grouping it would break the other consumer of the same view."""
    view = dict(_loaded_rule()["reference_views"][1], limit=1)
    columns, rows = enrichment_config.execute_reference_view(cand_env, view, {"lot": "L1"})
    assert len(rows) == 1 and "wafer_id" in columns
    probe = enrichment_config.execute_candidate_probe(
        cand_env, view, "wafer_id", {"lot": "L1"})
    assert probe["scanned"] == 2, "the probe must see both rows the display path hid"
    assert probe["distinct_truncated"] is True   # 2 distinct > limit 1


def test_a_clipped_distinct_read_is_refused_even_when_it_folds_to_one_value(cand_env):
    """[QA 2026-07-30] `distinct_truncated` used to carry NO error, on the
    reasoning that ">limit distinct values is >=2, so the ambiguous branch names
    it correctly". That reasoning ignores the caller's own `clean_str_value`
    folding: the clipped groups can fold back down to ONE canonical value, and
    the verdict then reads `single` while the real contradiction sits in an
    invisible clipped group.

    Fixture: three rows for one key -> 'WF01', 'WF01 ' (trailing space) and
    'WF02'. With `limit: 1` the probe asks for limit+1 = 2 groups, so one group
    is clipped; the two that come back fold to a single value.

    GROUP BY output order is unspecified in both engines, so the test ASSERTS
    that the fixture still activates the defect axis (the returned groups fold
    to one) instead of assuming it - a fixture that quietly stopped clipping
    'WF02' would otherwise turn this into a test of `ambiguous`.

    🔴 **That self-guard earned its keep on 2026-07-31.** The write boundary became
    canonical (`crud.normalize_stored_text`), `'WF01 '` started landing as `'WF01'`, the
    two clipped groups became {'WF01','WF02'} - and this test failed with its own
    "fixture no longer activates the defect axis" message instead of quietly becoming a
    test of `ambiguous`. `_seed_raw` restores the axis; see its docstring for why a probe
    fixture is entitled to bypass that boundary (the view is arbitrary user SQL).
    """
    _seed_raw(cand_env, "encand_test_hist", [
        {"hist_id": "D1", "lot": "LD", "slot": "S1", "wafer_id": "WF01"},
        {"hist_id": "D2", "lot": "LD", "slot": "S1", "wafer_id": "WF01 "},
        {"hist_id": "D3", "lot": "LD", "slot": "S1", "wafer_id": "WF02"},
    ])
    rule = _loaded_rule()
    narrow = dict(rule["reference_views"][0], limit=1)
    keys = {"lot": "LD", "slot": "S1"}

    probe = enrichment_config.execute_candidate_probe(cand_env, narrow, "wafer_id", keys)
    assert probe["distinct_truncated"] is True
    folded = {crud.clean_str_value(v) for v, _ in probe["pairs"]} - {""}
    assert len(folded) == 1, (
        "fixture no longer activates the defect axis: the CLIPPED groups must fold "
        f"to a single value (that is what used to read as `single`), got {folded}")

    res = enrichment_candidates.resolve_target_candidate(
        cand_env, dict(rule, reference_views=[narrow]), keys, "wafer_id")
    assert res["status"] == enrichment_candidates.STATUS_REFUSED
    assert res["reason"] == enrichment_candidates.REASON_DISTINCT_TRUNCATED
    # The partial finding is still reported so a UI can show it; it just cannot gate.
    assert res["value"] == "WF01"


def test_scanned_counts_every_row_the_probe_read_not_just_the_returned_groups(cand_env):
    """[QA 2026-07-30, the LOW] `scanned` was `sum(n for _, n in rows)` over the
    RETURNED groups, but it is compared against the INNER scan bound, which
    applied to every group. Clipped groups therefore vanished from the count.

    `SUM(COUNT(*)) OVER ()` is evaluated after GROUP BY and before the outer
    LIMIT, so it counts the whole scan regardless of clipping.
    """
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"N{i}", "lot": "LN", "slot": "S1", "wafer_id": f"W{i}"}
        for i in range(6)
    ])
    view = dict(_loaded_rule()["reference_views"][0], limit=1)
    probe = enrichment_config.execute_candidate_probe(
        cand_env, view, "wafer_id", {"lot": "LN", "slot": "S1"})
    assert probe["distinct_truncated"] is True
    assert len(probe["pairs"]) == 2, "the outer LIMIT is limit+1, the rest is clipped"
    assert probe["scanned"] == 6, (
        "scanned must count every row the probe READ, not only the groups it "
        "returned - it is the number `row_truncated` is decided from")


def test_row_truncation_is_still_detected_when_the_groups_are_also_clipped(cand_env):
    """The consequence of the LOW: a genuinely truncated READ used to report
    `row_truncated: False` whenever the groups were clipped too, because the
    under-reported `scanned` never reached the bound it is compared against."""
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"R{i}", "lot": "LR", "slot": "S1", "wafer_id": f"W{i}"}
        for i in range(6)
    ])
    view = dict(_loaded_rule()["reference_views"][0], limit=1)
    probe = enrichment_config.execute_candidate_probe(
        cand_env, view, "wafer_id", {"lot": "LR", "slot": "S1"},
        caps=_caps(probe_scan_rows=3))
    assert len(probe["pairs"]) == 2 and probe["distinct_truncated"] is True
    assert probe["scanned"] == 3, "the inner scan bound was reached"
    assert probe["row_truncated"] is True, (
        "the scan hit probe_scan_rows - clipping the GROUP BY output must not hide that")


def test_the_probe_distinct_cap_can_be_declared_apart_from_the_display_limit(cand_env):
    """THE conflation, undone. The view's `limit` answers "how many rows should a
    human read"; it was silently also answering "how many distinct values may the
    probe see". Declaring `probe_distinct_values` separates them - the display
    stays narrow, the probe sees enough to reach a verdict.

    Proven RED-able: at the same `limit` with no declared cap the probe truncates.
    """
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"D{i}", "lot": "LD", "slot": "S1", "wafer_id": f"W{i}"}
        for i in range(4)
    ])
    view = dict(_loaded_rule()["reference_views"][0], limit=1)
    inherited = enrichment_config.execute_candidate_probe(
        cand_env, view, "wafer_id", {"lot": "LD", "slot": "S1"}, caps=_caps())
    assert inherited["distinct_truncated"] is True
    assert inherited["distinct_values_cap"] == 1
    assert inherited["distinct_values_cap_declared"] is False

    declared = enrichment_config.execute_candidate_probe(
        cand_env, view, "wafer_id", {"lot": "LD", "slot": "S1"},
        caps=_caps(probe_distinct_values=50))
    assert declared["distinct_truncated"] is False
    assert declared["distinct_values_cap"] == 50
    assert declared["distinct_values_cap_declared"] is True
    # The DISPLAY path is untouched by the probe's cap - that is the separation.
    _, rows = enrichment_config.execute_reference_view(
        cand_env, view, {"lot": "LD", "slot": "S1"}, caps=_caps(probe_distinct_values=50))
    assert len(rows) == 1


def test_a_candidate_column_that_is_not_an_identifier_is_rejected_at_load(cand_env):
    """The column name is INTERPOLATED into the probe SQL, so its shape is checked
    before anything executes - validation must not sit downstream of the query."""
    bad = dict(NARROW_VIEW, candidate_for={"wafer_id": 'wafer_id" OR "1"="1'})
    normalized, err = enrichment_config._validate_rule(
        "r", _rule(reference_views=[bad]), CAND_TABLES)
    assert err is None
    assert normalized["reference_views"][0]["candidate_for"] == {}
    with pytest.raises(enrichment_config.ReferenceViewError):
        enrichment_config.execute_candidate_probe(
            cand_env, dict(NARROW_VIEW, required_binds=["lot", "slot"], limit=200),
            'wafer_id" OR "1"="1', {"lot": "L1", "slot": "S1"})


# ---------------------------------------------------------------------------
# 5-ter. A failed reference query must not poison the caller's transaction
#        [2026-07-30] The suite runs on SQLite, where a failed statement costs
#        nothing: pysqlite does not even open a transaction for a SELECT. On
#        PostgreSQL a failed statement ABORTS the transaction, and every later
#        statement raises until someone rolls back. So the green
#        `candidate_column_missing` test above was certifying a refusal
#        production could not reach - the diagnostic re-query ran on a dead
#        session and could only ever come back `view_error`.
# ---------------------------------------------------------------------------

class _AbortedTransaction(Exception):
    """Stand-in for psycopg2's InFailedSqlTransaction."""


@pytest.fixture()
def pg_abort_semantics(cand_env):
    """Impose PostgreSQL's transaction-abort rule on the SQLite test engine.

    WHY A FAULT INJECTION RATHER THAN A POSTGRES-BACKED TEST
        conftest pins the suite to `sqlite:///:memory:` deliberately - a hard
        assignment, so an ambient DATABASE_URL cannot point the suite at
        production. A Postgres-backed test would therefore SKIP in the default
        suite, and a skipped test certifies nothing. What has to be restored is
        not Postgres, it is one documented RULE that pysqlite does not have:

            after ANY statement fails, every subsequent statement on that
            connection raises until the transaction is rolled back - to the top,
            or to a SAVEPOINT.

        Everything else here stays real: the real probe SQL, the real view, the
        real SAVEPOINT SQLAlchemy emits, the real diagnostic re-query. Only the
        abort POLICY is injected.

    THE POLICY IS THE MEASURED ONE (live database, read-only, 2026-07-30)
            bad SELECT                       -> ProgrammingError
            next SELECT on the same session  -> InternalError  (poisoned)
            db.commit()                      -> RETURNED NORMALLY
                                                (the server made it a ROLLBACK)
            the same bad SELECT in a SAVEPOINT, then rollback to it
                                             -> next SELECT succeeds

        The third line is what made the failure silent, and it is why catching
        the driver error is not containment.

    Top-level BEGIN/COMMIT/ROLLBACK are issued through DBAPI methods rather than
    as SQL, so the flag is cleared from the `rollback` event; SAVEPOINT traffic
    IS emitted as SQL and is matched on the statement text.
    """
    from sqlalchemy import event

    bind = cand_env.get_bind()
    state = {"aborted": False}

    def _on_error(ctx):
        state["aborted"] = True

    def _on_rollback(conn):
        state["aborted"] = False

    def _before(conn, cursor, statement, parameters, context, executemany):
        head = statement.lstrip().upper()
        if head.startswith("ROLLBACK"):          # incl. ROLLBACK TO SAVEPOINT
            state["aborted"] = False
            return
        if head.startswith(("SAVEPOINT", "RELEASE", "COMMIT", "BEGIN")):
            return
        if state["aborted"]:
            raise _AbortedTransaction(
                "current transaction is aborted, commands ignored until end of "
                "transaction block")

    hooks = (("handle_error", _on_error), ("rollback", _on_rollback),
             ("before_cursor_execute", _before))
    for name, fn in hooks:
        event.listen(bind, name, fn)
    try:
        yield state
    finally:
        for name, fn in hooks:
            event.remove(bind, name, fn)
        cand_env.rollback()


def test_the_abort_injection_actually_bites(cand_env, pg_abort_semantics):
    """Guard on the guard. If the injector silently did nothing, the two tests
    below would pass on a defect - which is exactly how the suite came to
    certify `candidate_column_missing` in the first place."""
    from sqlalchemy import text

    with pytest.raises(Exception):
        cand_env.execute(text("SELECT nope FROM encand_test_hist")).fetchall()
    assert pg_abort_semantics["aborted"] is True
    with pytest.raises(_AbortedTransaction):
        cand_env.execute(text("SELECT 1")).fetchall()
    cand_env.rollback()
    assert cand_env.execute(text("SELECT 1")).scalar() == 1


def test_a_failed_probe_does_not_poison_the_callers_transaction(cand_env, pg_abort_semantics):
    """THE data-integrity assertion, in both halves.

    (a) The diagnostic re-query must run on a LIVE session, or the one refusal
        that tells an operator "your `candidate_for` names a column this view
        does not return" degrades into the generic `view_error`.
    (b) The caller's transaction must SURVIVE. Without this, everything the
        chain worker does afterwards on the same session is either a hard
        failure or - worse - a `commit()` the server converts to a rollback.
    """
    rule = _loaded_rule()
    wrong = dict(rule["reference_views"][0], candidate_for={"wafer_id": "not_a_column"})

    res = enrichment_candidates.resolve_target_candidate(
        cand_env, dict(rule, reference_views=[wrong]), {"lot": "L1", "slot": "S1"},
        "wafer_id")
    assert res["reason"] == enrichment_candidates.REASON_CANDIDATE_COLUMN_MISSING, (
        "the diagnostic ran on an aborted session, so it could only report "
        "view_error - candidate_column_missing is unreachable on PostgreSQL")

    assert pg_abort_semantics["aborted"] is False, "the savepoint was not rolled back"
    survivor = enrichment_candidates.resolve_target_candidate(
        cand_env, rule, {"lot": "L1", "slot": "S1"}, "wafer_id")
    assert survivor["status"] == enrichment_candidates.STATUS_SINGLE
    assert survivor["value"] == "WF1", "the session did not survive the failed probe"


def test_a_bad_candidate_column_does_not_wedge_the_chain_work_unit(cand_env, pg_abort_semantics,
                                                                   tmp_path, monkeypatch):
    """End to end: one typo in `candidate_for` must not take the worker down.

    Production consequence of the poisoning, in order: the chain rows ARE
    committed (`crud.apply_batch_updates` commits before these hooks run), the
    auto-confirm hook then fails and is swallowed, and the poisoned session
    escapes into `process_pending_groups`, whose commit of
    `processed_chain=True` cannot land. The group is never marked processed, so
    the batch loop replays it forever while the retry quarantine - which only
    counts REPORTED failures - never advances.

    `_run_chain_for_tx` performs exactly that bookkeeping commit, so a wedged
    session fails this test at the commit.
    """
    rules_path = tmp_path / "badcol.json"
    bad_view = dict(NARROW_VIEW, candidate_for={"wafer_id": "not_a_column"})
    rules_path.write_text(json.dumps({"encand_rule": _rule(reference_views=[bad_view])}),
                          encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))

    _seed(cand_env, "encand_test_src",
          [{"log_key": "kb1", "lot": "L1", "slot": "S1", "chip_id": "C1"}], tx_id="tx_badcol")
    _run_chain_for_tx(cand_env, "tx_badcol")

    row = _derived(cand_env, "L1_S1")
    assert row is not None, "the chain write must still be there"
    assert crud.clean_str_value(row.wafer_id) == "", \
        "a view that cannot answer must leave the key visibly unresolved"

    # The bookkeeping really landed - the group will not be replayed.
    from database.models import DatabaseOutbox
    cand_env.expire_all()
    pending = cand_env.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == "encand_test_src",
        DatabaseOutbox.processed_chain == False,  # noqa: E712
    ).count()
    assert pending == 0, "the outbox bookkeeping commit was rolled back - the group replays"


# ---------------------------------------------------------------------------
# 6. Seam guard: one definition of the LIMIT wrap
# ---------------------------------------------------------------------------

def test_reference_view_execution_has_one_definition(cand_env):
    """The route used to hold an inline copy of the LIMIT wrap because main.py
    belonged to a concurrent round. [F9, 2026-07-30] it now calls
    `execute_reference_view`, so this guard flipped from "the two copies agree" to
    "there is only one copy" - a second inline wrap in main.py fails here.

    Reads main.py FROM DISK rather than via `inspect.getsource`: the imported
    module's line numbers go stale the moment anyone edits main.py during a run,
    and getsource then happily returns a DIFFERENT function's body (observed
    2026-07-30 — it returned `get_mappers`). File text has no such hazard.
    """
    import os
    import main

    main_src = open(os.path.abspath(main.__file__.replace(".pyc", ".py")),
                    encoding="utf-8").read()
    assert "execute_reference_view" in main_src, (
        "the enrichment reference route no longer calls the shared executor - either "
        "it grew its own definition again or the call was renamed")
    for token in ("__enrichment_ref", "__enrichment_cand", ":__enrichment_limit"):
        assert token in (enrichment_config.REFERENCE_LIMIT_WRAP_SQL
                         + enrichment_config.CANDIDATE_GROUP_WRAP_SQL)
        assert token not in main_src, (
            f"main.py contains {token!r} again - reference-view execution has grown a "
            f"second definition. The display path and the candidate probe share it.")


def test_execute_reference_view_enforces_the_limit(cand_env):
    view = dict(_loaded_rule()["reference_views"][1], limit=1)
    columns, rows = enrichment_config.execute_reference_view(cand_env, view, {"lot": "L1"})
    assert "wafer_id" in columns
    assert len(rows) == 1, "server-side LIMIT must be enforced regardless of the view body"


def test_execute_reference_view_refuses_missing_bind(cand_env):
    view = _loaded_rule()["reference_views"][0]
    with pytest.raises(enrichment_config.ReferenceViewError):
        enrichment_config.execute_reference_view(cand_env, view, {"lot": "L1"})


def test_a_blank_bind_value_is_missing_and_not_a_query_that_matches_nothing(cand_env):
    """Absent and blank read the same from the view's side; only one was named.

    Passing `slot=''` used to build a legal query that returned no rows, and a
    zero-row read is indistinguishable from "no such evidence exists" at the call
    site. Now that a partial decision key is workable this distinction carries
    weight: the views that still bind get asked, and the view that cannot be
    asked says so. `resolve_target_candidate` has always folded blank into
    missing - this puts the same funnel where the SQL is built, so the DISPLAY
    path and the CANDIDATE path refuse the same view for the same reason.
    """
    view = _loaded_rule()["reference_views"][0]      # binds lot AND slot
    with pytest.raises(enrichment_config.ReferenceViewError) as e:
        enrichment_config.execute_reference_view(cand_env, view, {"lot": "L1", "slot": "  "})
    assert "slot" in str(e.value)
    with pytest.raises(enrichment_config.ReferenceViewError):
        enrichment_config.execute_candidate_probe(
            cand_env, view, "wafer_id", {"lot": "L1", "slot": ""})

    # The control: the SURVIVING bind still executes, on the same call, so this is
    # a refusal about one view and not a blanket one about blank-containing keys.
    subset = _loaded_rule()["reference_views"][1]    # binds lot only
    columns, rows = enrichment_config.execute_reference_view(
        cand_env, subset, {"lot": "L1", "slot": ""})
    assert "wafer_id" in columns and rows


def test_collector_keeps_a_partial_key_and_drops_only_a_wholly_blank_one(cand_env):
    """The chain-worker gate follows the same ruling as the sweep.

    It used to skip a row if ANY key column was blank. Now it skips only when
    NOTHING survives - and that skip is an optimization, not a second opinion:
    `resolve_target_candidate` would refuse the same row `no_decision_key`.
    """
    c = enrichment_candidates.AutoConfirmCollector("encand_test_derived")
    assert c.active, "fixture is inert: the collector must be live for this to mean anything"
    c.collect([
        {"business_key_val": "FULL", "updates": {"lot": "L1", "slot": "S1"}},
        {"business_key_val": "PARTIAL", "updates": {"lot": "L1", "slot": ""}},
        {"business_key_val": "KEYLESS", "updates": {"lot": "", "slot": ""}},
    ])
    assert set(c.entries) == {"FULL", "PARTIAL"}


# ---------------------------------------------------------------------------
# Ambiguity is per COLUMN, not per row  [2026-08-05 user ruling]
# ---------------------------------------------------------------------------

def _two_target_rule(cand_env, tmp_path, views):
    """Reload the isolated rules file with a TWO-target rule.

    `server/config/` is never touched - a write there reloads three live processes.
    """
    path = tmp_path / "enrichment_rules.json"
    path.write_text(json.dumps({"encand_rule": _rule(
        target_fields=["wafer_id", "owner"], reference_views=views)}), encoding="utf-8")
    return _loaded_rule()


def _confirm(db, rule, bks, apply=True):
    """Run the shared writer over derived rows addressed by business key."""
    m = models.DYNAMIC_TABLES["encand_test_derived"]
    keyed = []
    for bk in bks:
        row = db.query(m).filter(m.business_key_val == bk).first()
        assert row is not None, f"fixture did not create {bk}"
        blanks = [t for t in rule["target_fields"]
                  if crud.clean_str_value(getattr(row, t)) == ""]
        keyed.append({"row_id": row.row_id, "business_key_val": bk,
                      "keys": {"lot": row.lot, "slot": row.slot}, "blank_targets": blanks})
    return enrichment_candidates.confirm_keys(db, rule, keyed, apply=apply,
                                              tx_prefix="encand_test")


def test_a_determined_column_is_written_while_its_ambiguous_sibling_stays_blank(cand_env,
                                                                               tmp_path):
    """THE ruling. Same key, same evidence, two columns, two different verdicts.

    L2/S1 has two history rows. They disagree on `wafer_id` (WF3 vs WF9) and agree
    on `owner` (OPS). Refusing the row would leave OPS unwritten because a
    DIFFERENT column could not be decided - all-or-nothing where the evidence is
    not. L1/S1 is carried alongside as the control: with one history row both
    columns resolve, so `partly` is a verdict about the evidence and not about
    the harness failing to write anything.
    """
    rule = _two_target_rule(cand_env, tmp_path, [dict(NARROW_VIEW), dict(OWNER_VIEW)])
    _seed(cand_env, "encand_test_derived", [
        {"wafer_key": "L2_S1", "lot": "L2", "slot": "S1"},
        {"wafer_key": "L1_S1", "lot": "L1", "slot": "S1"},
    ])
    st = _confirm(cand_env, rule, ["L2_S1", "L1_S1"])

    amb = _derived(cand_env, "L2_S1")
    assert crud.clean_str_value(amb.owner) == "OPS", \
        "the column the candidates AGREE on must be filled"
    assert crud.clean_str_value(amb.wafer_id) == "", \
        "the column they disagree on must stay blank - that is the human judgement"

    ctl = _derived(cand_env, "L1_S1")
    assert (crud.clean_str_value(ctl.wafer_id), crud.clean_str_value(ctl.owner)) \
        == ("WF1", "ALICE"), "control row: both columns are decidable here"

    assert st["rows_fully_confirmed"] == 1 and st["rows_partly_confirmed"] == 1
    assert st["per_target"]["owner"]["confirmed"] == 2
    assert st["per_target"]["wafer_id"]["confirmed"] == 1
    assert st["per_target"]["wafer_id"]["refused"] == {
        enrichment_candidates.REASON_AMBIGUOUS: 1}


def test_never_asked_is_not_the_same_blank_as_asked_and_disagreed(cand_env, tmp_path):
    """`not_declared` vs `ambiguous`, on two rows of the same rule.

    A target no view declares a candidate column for was NEVER COMPARED. That used
    to be counted only when NO target was declared, so on a rule with a declared
    sibling the undeclared one was skipped in silence and its blank was
    indistinguishable from a judged one. Different facts: one sends a person to
    fix the config, the other to make a call.
    """
    rule = _two_target_rule(cand_env, tmp_path, [dict(NARROW_VIEW)])   # owner undeclared
    _seed(cand_env, "encand_test_derived", [{"wafer_key": "L2_S1", "lot": "L2", "slot": "S1"}])
    st = _confirm(cand_env, rule, ["L2_S1"])

    assert st["per_target"]["owner"]["refused"] == {
        enrichment_candidates.REASON_NOT_DECLARED: 1}
    assert enrichment_candidates.REASON_AMBIGUOUS not in st["per_target"]["owner"]["refused"]
    assert st["per_target"]["wafer_id"]["refused"] == {
        enrichment_candidates.REASON_AMBIGUOUS: 1}, \
        "the sibling was asked, and its blank means something else entirely"
    assert crud.clean_str_value(_derived(cand_env, "L2_S1").owner) == ""


def test_the_row_outcomes_partition_the_rows_examined(cand_env, tmp_path):
    """full + partly + none == examined, over a set containing all three.

    A progress number whose parts stop adding up is exactly how the bar read 100%
    with work left, so the identity is asserted rather than assumed - and the
    fixture is checked to contain all three outcomes, or the identity would hold
    vacuously.
    """
    rule = _two_target_rule(cand_env, tmp_path, [dict(NARROW_VIEW), dict(OWNER_VIEW)])
    _seed(cand_env, "encand_test_derived", [
        {"wafer_key": "L1_S1", "lot": "L1", "slot": "S1"},   # both decidable
        {"wafer_key": "L2_S1", "lot": "L2", "slot": "S1"},   # owner only
        {"wafer_key": "L9_S9", "lot": "L9", "slot": "S9"},   # no history at all
    ])
    st = _confirm(cand_env, rule, ["L1_S1", "L2_S1", "L9_S9"])
    assert (st["rows_fully_confirmed"], st["rows_partly_confirmed"],
            st["rows_unconfirmed"]) == (1, 1, 1), "fixture must produce all three outcomes"
    assert st["rows_examined"] == (st["rows_fully_confirmed"] + st["rows_partly_confirmed"]
                                   + st["rows_unconfirmed"])
    assert st["written_cells"] == 3, "cell grain still counts the partial fill as work"


def test_cell_sources_already_says_which_columns_the_sweep_decided(cand_env, tmp_path):
    """Why a partial-TARGET fill needs no new source name.

    `cell_sources` is one row per (row_id, column_name), so the decided column
    carries the sweep's name and the refused one has NO provenance row at all.
    "Which columns did this sweep decide" is therefore already a predicate over
    the existing table. A third source name would restate the table's own grain.
    (Contrast `SOURCE_NAME_PARTIAL_KEY`, which names a fact about the ROW's key
    that no per-cell record could carry.)
    """
    rule = _two_target_rule(cand_env, tmp_path, [dict(NARROW_VIEW), dict(OWNER_VIEW)])
    _seed(cand_env, "encand_test_derived", [{"wafer_key": "L2_S1", "lot": "L2", "slot": "S1"}])
    _confirm(cand_env, rule, ["L2_S1"])

    row = _derived(cand_env, "L2_S1")
    got = dict(cand_env.query(models.CellSource.column_name, models.CellSource.source_name)
               .filter(models.CellSource.table_name == "encand_test_derived",
                       models.CellSource.row_id == row.row_id,
                       models.CellSource.column_name.in_(["wafer_id", "owner"])).all())
    assert got == {"owner": enrichment_candidates.SOURCE_NAME}, \
        "the decided column is named and the refused one has no provenance row"


# ---------------------------------------------------------------------------
# 5-quater. A BROKEN reference view must say WHAT is broken
#
#   [2026-08-05, reported live] Running an enrichment reference view's SQL
#   showed only `ProgrammingError`. `ReferenceViewError` was built from
#   `e.__class__.__name__` alone, and `main.py` logged that same already-
#   stripped message, so the cause existed NOWHERE - not in the response, not
#   in the log. An authoring mistake was undebuggable.
#
#   The no-body contract on `ReferenceViewError` is not the bug and is not
#   relaxed here. It is load-bearing, and MEASURED to be: SQLAlchemy's `str(e)`
#   appends `[SQL: <the whole wrapped statement>]` and `[parameters: ...]`, and
#   psycopg2's own text carries a `LINE n: <statement excerpt>` echo. The bug is
#   that hiding the body was implemented as discarding the DIAGNOSIS, which
#   PostgreSQL reports separately in `psycopg2.Error.diag`.
#
#   WHY THESE TESTS INJECT DIAGNOSTICS (the honest answer to "can SQLite see
#   this at all")
#       No. Under SQLite `orig` is a `sqlite3.OperationalError`, which has no
#       `.diag`, so every un-injected test in this file can only ever exercise
#       the DEGRADATION branch. A suite that stopped there would certify
#       "the message says diagnostics are unavailable" and would go green on a
#       `describe_driver_error` that had never once read a diagnostic field -
#       the same shape of hole that let `candidate_column_missing` be certified
#       while being unreachable on PostgreSQL (see `pg_abort_semantics` above).
#       So `pg_diagnostics` restores ONE missing rule to the SQLite engine, the
#       way `pg_abort_semantics` restores the transaction-abort rule: driver
#       errors carry structured diagnostics. Everything else stays real - the
#       real view, the real wrap SQL, the real SAVEPOINT, the real raise site.
#
#   THE INJECTED VALUES ARE MEASURED, NOT INVENTED. Every field below was read
#   off a live PostgreSQL 18.0 / psycopg2 2.9.11 (read-only, local instance,
#   `lc_messages = Korean_Korea.949`) and is reproduced verbatim.
# ---------------------------------------------------------------------------

BROKEN_VIEW = {
    "label": "broken (authoring mistake)",
    # No binds, so the refusal under test is the DRIVER's and not `missing_binds`.
    "query": "SELECT nosuchcol_xyz AS wafer_id FROM encand_test_hist",
    "limit": 5,
    "candidate_for": {"wafer_id": "wafer_id"},
}


class _FakeDiag:
    """Stand-in for psycopg2's `Diagnostics`.

    `__getattr__` returning None matters: the real object exposes EVERY
    diagnostic field and yields None for the unset ones, so a fake that raised
    `AttributeError` would let `describe_driver_error` pass for the wrong
    reason.
    """

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __getattr__(self, name):
        return None


# Measured verbatim. `column_name` is deliberately ABSENT on the 42703 cases -
# that is not an oversight in the fixture, it is what PostgreSQL does: for
# undefined_column it populates NO structured identifier field, so the column
# name exists only inside `message_primary`.
DIAG_UNDEFINED_COLUMN = dict(
    sqlstate="42703", message_primary='"nosuchcol_xyz" 이름의 칼럼은 없습니다')
DIAG_UNDEFINED_COLUMN_HINTED = dict(
    sqlstate="42703", message_primary='"table_nam" 이름의 칼럼은 없습니다',
    message_hint='아마 "tables.table_name" 칼럼을 참조하는 것 같습니다.')
DIAG_SYNTAX_ERROR = dict(
    sqlstate="42601", message_primary='구문 오류, "SELCT" 부근')
DIAG_UNDEFINED_TABLE = dict(
    sqlstate="42P01",
    message_primary='"no_such_table_xyz" 이름의 릴레이션(relation)이 없습니다')


@pytest.fixture()
def pg_diagnostics(cand_env):
    """Give this SQLite engine's driver errors PostgreSQL-shaped `.diag`.

    Set `state["diag"]` to a `_FakeDiag` before provoking the error. `attached`
    counts how many driver errors actually received it, so a test can prove the
    injection bit rather than assume it.
    """
    from sqlalchemy import event

    bind = cand_env.get_bind()
    state = {"diag": None, "attached": 0}

    def _on_error(ctx):
        orig = ctx.original_exception
        if state["diag"] is None or orig is None:
            return
        orig.diag = state["diag"]      # the same object SQLAlchemy exposes as `.orig`
        state["attached"] += 1

    event.listen(bind, "handle_error", _on_error)
    try:
        yield state
    finally:
        event.remove(bind, "handle_error", _on_error)
        cand_env.rollback()


def test_the_diagnostics_injection_actually_bites(cand_env, pg_diagnostics):
    """Guard on the guard, same posture as `test_the_abort_injection_actually_bites`.

    If the listener silently did nothing, the tests below would fail rather than
    pass on a defect - but they would fail for a reason that reads like a
    product bug, and the tempting repair is to weaken the assertion. So the
    injection proves itself once, out loud.
    """
    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    with pytest.raises(enrichment_config.ReferenceViewError) as err:
        enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})
    assert pg_diagnostics["attached"] >= 1, "the driver error never received a .diag"
    assert "42703" in str(err.value)


def test_a_broken_reference_view_names_the_column_postgres_named(cand_env, pg_diagnostics):
    """THE repair. The message must carry the identifier that makes the view fixable.

    Before this round the whole message was
    `reference query execution failed (OperationalError)` - a class name and
    nothing else. `nosuchcol_xyz` is the one string an author needs.
    """
    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    with pytest.raises(enrichment_config.ReferenceViewError) as err:
        enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})

    message = str(err.value)
    assert "nosuchcol_xyz" in message, "the message does not name the offending column"
    # SQLSTATE, because `message_primary` is LOCALIZED (this server answers in
    # Korean) and an operator or a log grep needs something stable to key on.
    assert "42703" in message, "SQLSTATE missing - the only language-independent handle"
    # The driver's own class is always named. Under this injection that reads
    # `OperationalError` (SQLite's class, which no fixture can rename - a static
    # C type does not accept `__class__` assignment). The psycopg2 half, where
    # that same slot reads `UndefinedColumn`, is pinned by
    # `test_describe_driver_error_renders_a_real_psycopg2_shape` below.
    assert "OperationalError" in message, "the driver's own class is not named"


def test_the_candidate_probe_path_says_the_same_thing(cand_env, pg_diagnostics):
    """The second copy of the defect.

    `execute_reference_view` and `execute_candidate_probe` had the SAME stripped
    `raise` line. Fixing one and not the other would have produced the next
    report from the other path, so this pins that both go through the shared
    helper.
    """
    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_TABLE)
    with pytest.raises(enrichment_config.ReferenceViewError) as err:
        enrichment_config.execute_candidate_probe(cand_env, BROKEN_VIEW, "wafer_id", {})

    message = str(err.value)
    assert message.startswith("candidate probe execution failed"), \
        "the probe path must still name ITSELF - the two sites share a helper, not an identity"
    assert "no_such_table_xyz" in message
    assert "42P01" in message


def test_the_hint_ships_because_it_names_the_column_the_author_meant(cand_env, pg_diagnostics):
    """`message_hint` is the single most actionable sentence PostgreSQL produces
    for a typo, and it is identifier-shaped (measured: it quotes
    `tables.table_name`). Dropping it would leave the author knowing the name is
    wrong and not what it should be."""
    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN_HINTED)
    with pytest.raises(enrichment_config.ReferenceViewError) as err:
        enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})
    assert "tables.table_name" in str(err.value)


def test_a_condition_whose_message_quotes_the_statement_is_withheld_by_name(
        cand_env, pg_diagnostics):
    """The bound, and the reason there is one.

    MEASURED: `42601 syntax_error` puts a RAW STATEMENT TOKEN in its primary
    message (it quotes `SELCT`, the misspelling itself), not an identifier - so
    this one class cannot ship verbatim under a contract that says the statement
    does not leave the server. The answer is not to fall back to silence, which
    is the bug being repaired: the condition NAME and the SQLSTATE still ship,
    and the message SAYS the text was withheld and where to read it.
    """
    pg_diagnostics["diag"] = _FakeDiag(**DIAG_SYNTAX_ERROR)
    with pytest.raises(enrichment_config.ReferenceViewError) as err:
        enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})

    message = str(err.value)
    assert "SELCT" not in message, "a raw statement token reached the response"
    assert "구문" not in message, "PostgreSQL's prose for this condition reached the response"
    assert "42601" in message, \
        "withheld must not mean silent - the condition is still named by SQLSTATE"
    assert "withheld" in message and "server log" in message, \
        "a withheld message must say it was withheld and where the full text is"


def test_a_shape_that_is_not_a_condition_is_withheld_even_unmeasured(cand_env, pg_diagnostics):
    """The guard that does not need the SQLSTATE list to be complete.

    A statement echo is structurally multi-line and long; every measured
    `message_primary` was one line of at most 26 characters. So a future
    PostgreSQL condition that pastes statement text into its primary message is
    caught by SHAPE, without anyone having measured that condition first.
    """
    pg_diagnostics["diag"] = _FakeDiag(
        sqlstate="42P01",
        message_primary='relation does not exist\nLINE 1: SELECT nosuchcol_xyz AS '
                        'wafer_id FROM encand_test_hist\n               ^')
    with pytest.raises(enrichment_config.ReferenceViewError) as err:
        enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})

    message = str(err.value)
    assert "encand_test_hist" not in message, "a multi-line echo slipped through by shape"
    assert "LINE 1" not in message
    assert "42P01" in message, "the condition is still named"


def test_the_query_body_never_reaches_the_message(cand_env, pg_diagnostics):
    """The contract, as an assertion rather than a comment.

    This one PASSES on the old code too - it guards the repair, it does not
    witness it. Mutation-checked instead: making `describe_driver_error` return
    `str(exc)` (the obvious "just include the error" fix) turns it red, because
    SQLAlchemy's text carries `[SQL: ...]` and `[parameters: ...]`.
    """
    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    with pytest.raises(enrichment_config.ReferenceViewError) as err:
        enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})

    message = str(err.value)
    for leak in ("SELECT", "FROM", "encand_test_hist", "[SQL:", "[parameters:",
                 "LINE 1", "__enrichment_ref"):
        assert leak not in message, "the response carries statement text: " + repr(leak)


def test_a_driver_without_diagnostics_degrades_by_name(cand_env):
    """No injection: this is what SQLite - and any driver without PostgreSQL's
    structured diagnostics - actually produces.

    The failure mode being closed here is a silent fall-back to the old
    behaviour. "I could not read the diagnostics" must be sayable, or a missing
    `.diag` is indistinguishable from the defect.
    """
    with pytest.raises(enrichment_config.ReferenceViewError) as err:
        enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})

    message = str(err.value)
    assert "no structured diagnostics" in message
    assert "server log" in message, "a degraded message must point at where the cause is"
    assert "OperationalError" in message, "the driver's own class is still named"


def test_the_full_driver_error_reaches_the_server_log(cand_env, caplog):
    """Requirement two: the log is not the browser.

    The contract governs the HTTP RESPONSE. An operator reading the log must see
    the driver's own text and its traceback - previously the raise site logged
    NOTHING and `main.py` logged the already-stripped message, so the cause was
    destroyed before either reader could reach it.
    """
    import logging

    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        with pytest.raises(enrichment_config.ReferenceViewError):
            enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})

    records = [r for r in caplog.records if r.name == "EnrichmentConfig"]
    assert records, "the raise site logged nothing at all"
    assert any(r.exc_info for r in records), "logged without exc_info - no traceback"
    # SQLite's own words for this mistake. On PostgreSQL the same channel carries
    # `column "..." does not exist` plus the `LINE n:` echo and the full [SQL: ].
    assert "nosuchcol_xyz" in caplog.text, "the driver's own text is not in the log"
    assert "Traceback" in caplog.text


def test_reading_diagnostics_does_not_disturb_the_savepoint_discipline(
        cand_env, pg_abort_semantics, pg_diagnostics):
    """Both injected rules at once: PostgreSQL's abort semantics AND its diagnostics.

    `_isolated_execute` has already rolled back to its SAVEPOINT by the time the
    raise site reads `.diag`, and reading it touches no connection (the
    diagnostics are a snapshot the exception carries - measured: every field was
    read after the rollback). This pins that the new diagnosis and the old
    containment hold TOGETHER, because the failure this file exists to prevent
    is a poisoned session escaping into the chain worker's bookkeeping commit.
    """
    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)

    with pytest.raises(enrichment_config.ReferenceViewError) as err:
        enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})
    assert "nosuchcol_xyz" in str(err.value), "the diagnosis did not survive the rollback"

    assert pg_abort_semantics["aborted"] is False, "the savepoint was not rolled back"
    survivor = enrichment_candidates.resolve_target_candidate(
        cand_env, _loaded_rule(), {"lot": "L1", "slot": "S1"}, "wafer_id")
    assert survivor["status"] == enrichment_candidates.STATUS_SINGLE
    assert survivor["value"] == "WF1", "the session did not survive the failed read"


def test_the_named_refusal_carries_the_diagnosis_to_the_worklist(cand_env, pg_diagnostics):
    """The message is not only for the HTTP path.

    `resolve_target_candidate` puts `str(e)` into `errors[].detail`, so the same
    repair reaches the auto-confirm refusals an operator reads in the worklist -
    which is where a broken `candidate_for` declaration is actually noticed.
    """
    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    rule = dict(_loaded_rule(), reference_views=[dict(BROKEN_VIEW, required_binds=[])])

    res = enrichment_candidates.resolve_target_candidate(
        cand_env, rule, {"lot": "L1", "slot": "S1"}, "wafer_id")

    assert res["status"] == enrichment_candidates.STATUS_REFUSED
    details = " ".join(e.get("detail") or "" for e in res["errors"])
    assert "nosuchcol_xyz" in details, "the refusal still hides why the view failed"


# --- the psycopg2 half, where no database can help -------------------------
#   `pg_diagnostics` above can lend SQLite's driver error a `.diag`, but it
#   cannot rename it: `sqlite3.OperationalError` is a static C type and does not
#   accept `__class__` assignment. So the slot where psycopg2 puts PostgreSQL's
#   own condition name - `UndefinedColumn`, `SyntaxError`, ... - reads
#   `OperationalError` in every test above. That name is not decoration: it is
#   the ENGLISH, statement-free diagnosis that still ships when PostgreSQL's
#   prose is withheld, so something has to pin it.
#
#   These are unit tests on `describe_driver_error` with an exception shaped
#   exactly like the measured article. No database, no engine, no view - and
#   therefore no way for a passing DB test to hide a broken renderer.


def _psycopg2_shaped(condition_name, **diag_fields):
    """An exception shaped like SQLAlchemy's wrapper around a psycopg2 error.

    `orig` is an instance of a class NAMED for PostgreSQL's condition, because
    that is exactly what psycopg2 does - `psycopg2.errors` is generated from
    PostgreSQL's own errcodes table, which is why the name is stable and
    English even when the message is not.
    """
    orig_cls = type(condition_name, (Exception,), {})
    orig = orig_cls("... whatever text the driver puts here ...")
    orig.diag = _FakeDiag(**diag_fields)
    wrapper = Exception("(psycopg2.errors.%s) ..." % condition_name)
    wrapper.orig = orig
    return wrapper


def test_describe_driver_error_renders_a_real_psycopg2_shape():
    """The flagship case, end to end through the renderer.

    Measured values, and the measured ABSENCE: PostgreSQL populates no
    structured identifier field for `42703`, so the column name lives only in
    `message_primary`. A renderer that kept only the identifier fields would
    return a contentless string here and re-create the original defect.
    """
    described = enrichment_config.describe_driver_error(
        _psycopg2_shaped("UndefinedColumn", **DIAG_UNDEFINED_COLUMN))

    assert described.startswith("UndefinedColumn/42703:"), described
    assert "nosuchcol_xyz" in described


def test_describe_driver_error_names_the_condition_even_when_it_withholds():
    """`42601` is the class that cannot ship its prose. It must still ship a
    diagnosis: "your SQL does not parse" said in a stable English word."""
    described = enrichment_config.describe_driver_error(
        _psycopg2_shaped("SyntaxError", **DIAG_SYNTAX_ERROR))

    assert described.startswith("SyntaxError/42601:"), described
    assert "SELCT" not in described, "a raw statement token survived the withholding"
    assert "withheld" in described and "server log" in described


def test_describe_driver_error_ships_structured_identifiers_when_there_are_any():
    """Where PostgreSQL DOES populate them (constraint and not-null conditions),
    the identifier fields are pure identifiers and are worth carrying."""
    described = enrichment_config.describe_driver_error(
        _psycopg2_shaped("NotNullViolation", sqlstate="23502",
                         message_primary="null value in column violates not-null constraint",
                         table_name="encand_test_hist", column_name="wafer_id"))

    assert "table_name=encand_test_hist" in described
    assert "column_name=wafer_id" in described


def test_describe_driver_error_never_returns_nothing():
    """Every way of failing to read diagnostics has a NAME.

    Silence is the defect. An exception with no `.orig`, an `.orig` with no
    `.diag`, and a diagnostics object that raises on access are three different
    failures and each says which one it was - a caller must never be handed a
    message that merely restates that something went wrong.
    """
    class _Hostile:
        @property
        def diag(self):
            raise RuntimeError("diagnostics unavailable")

    bare = Exception("no orig at all")
    assert "no driver error attached" in enrichment_config.describe_driver_error(bare)

    no_diag = Exception("wrapper")
    no_diag.orig = ValueError("a driver with no structured diagnostics")
    assert "no structured diagnostics" in enrichment_config.describe_driver_error(no_diag)

    hostile = Exception("wrapper")
    hostile.orig = _Hostile()
    described = enrichment_config.describe_driver_error(hostile)
    assert "unreadable" in described, described

    for exc in (bare, no_diag, hostile):
        assert "server log" in enrichment_config.describe_driver_error(exc), \
            "a degraded message that does not say where the cause is, is still silence"


# ---------------------------------------------------------------------------
# 5-quinquies. The diagnostic must not bury itself
#
#   [2026-08-05, ruled] Shipping the full traceback at every raise site put
#   ~400 identical tracebacks per work unit into the log for ONE broken view:
#   the worker probes up to `DEFAULT_MAX_KEYS_PER_UNIT` (200) keys per unit per
#   declaring view, continuously, and `_diagnose_probe_failure` re-queried and
#   failed a second time for the same cause, doubling it.
#
#   A flood is a disk problem, but the worse half is that it makes the ONE
#   traceback that matters unfindable - the same defect the round was fixing,
#   wearing a different hat.
#
#   Three properties, and the tests below exist one per property:
#     (1) repeats collapse to a count, and the FIRST still carries everything;
#     (2) suppressed is not silent - the count is stated periodically and
#         exactly at the work-unit boundary;
#     (3) a DIFFERENT condition at the same site is never swallowed by the
#         first one's entry. That is why the key has two parts, and it is the
#         failure mode that would let a second real defect hide behind an old.
# ---------------------------------------------------------------------------

def _errors(caplog):
    return [r for r in caplog.records if r.name == "EnrichmentConfig"]


def _traced(caplog):
    return [r for r in _errors(caplog) if r.exc_info]


def _probe_fails(db, times=1):
    for _ in range(times):
        with pytest.raises(enrichment_config.ReferenceViewError):
            enrichment_config.execute_candidate_probe(db, BROKEN_VIEW, "wafer_id", {})


def test_repeated_probe_failures_collapse_to_one_traceback(cand_env, pg_diagnostics, caplog):
    """(1) One broken view, many keys - one traceback.

    The first occurrence is untouched: full driver text, full traceback. What
    the throttle removes is the 199 identical copies behind it.
    """
    import logging

    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        _probe_fails(cand_env, times=5)

    assert len(_traced(caplog)) == 1, \
        "every repeat printed its own traceback - the flood is still there"
    assert len(_errors(caplog)) == 1, "a repeat logged at ERROR without being a new cause"
    assert "nosuchcol_xyz" in caplog.text, "the ONE surviving record lost the diagnosis"
    assert "Traceback" in caplog.text


def test_a_different_condition_at_the_same_site_is_never_swallowed(cand_env, pg_diagnostics,
                                                                   caplog):
    """(3) THE reason the key has two parts.

    A throttle keyed on the site alone would let a second, genuinely different
    failure hide behind the first one's entry - the log would show one cause
    while two were live. Nothing about "this site already reported something"
    may suppress a condition nobody has seen yet.
    """
    import logging

    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
        _probe_fails(cand_env, times=3)
        pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_TABLE)
        _probe_fails(cand_env, times=3)

    assert len(_traced(caplog)) == 2, \
        "the second condition was swallowed by the first condition's throttle entry"
    # Each record names WHICH condition it opened an entry for. (The log carries
    # the DRIVER's text - SQLite's - not the injected diag, which is what the
    # response gets; so the discriminator to assert on here is the SQLSTATE.)
    assert "42703" in caplog.text and "42P01" in caplog.text
    assert len([r for r in _traced(caplog) if "42703" in r.getMessage()]) == 1
    assert len([r for r in _traced(caplog) if "42P01" in r.getMessage()]) == 1


def test_the_suppressed_repeats_are_counted_not_lost(cand_env, pg_diagnostics, caplog):
    """(2a) A long unit never goes quiet.

    Silence that hides HOW OFTEN something happened is how a broken view looks
    like a one-off. The periodic line states the running TOTAL, so the operator
    reads a scale rather than an incident.
    """
    import logging

    every = enrichment_config.DRIVER_ERROR_REPEAT_EVERY
    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        _probe_fails(cand_env, times=every + 1)

    assert len(_traced(caplog)) == 1, "the traceback repeated"
    assert f"failed {every + 1} time(s)" in caplog.text, \
        "the repeats were suppressed WITHOUT ever saying how many there were"


def test_the_work_unit_boundary_states_the_true_total_and_then_forgets(cand_env,
                                                                      pg_diagnostics, caplog):
    """(2b) The exact total, and why the state must be cleared with it.

    The periodic line can only ever report a multiple; the drain reports the
    truth. Clearing matters as much as counting: without it a view that broke
    this morning logs one traceback and is silent for the rest of the day, so
    the next work unit's operator sees nothing at all.
    """
    import logging

    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    _probe_fails(cand_env, times=3)

    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        drained = enrichment_config.drain_driver_error_incidents()
    assert drained == [(enrichment_config.SITE_CANDIDATE_PROBE, "42703", 3)], drained
    assert "failed 3 time(s)" in caplog.text

    # Forgotten: nothing left to drain, and the NEXT failure is news again.
    assert enrichment_config.drain_driver_error_incidents() == []
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        _probe_fails(cand_env, times=1)
    assert len(_traced(caplog)) == 1, \
        "after the drain a broken view stayed silent - it must re-announce itself"


def test_the_display_path_is_not_throttled_because_a_person_is_repairing_it(
        cand_env, pg_diagnostics, caplog):
    """The deliberate asymmetry, asserted so nobody 'tidies' it away.

    The HTTP path is bounded by a person clicking, and that person is usually
    MID-REPAIR: the client caches a 400 per (row, view), so a second request
    means the author actually changed something. Answering their second attempt
    with silence is a worse trade than a few duplicate tracebacks.
    """
    import logging

    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        for _ in range(3):
            with pytest.raises(enrichment_config.ReferenceViewError):
                enrichment_config.execute_reference_view(cand_env, BROKEN_VIEW, {})

    assert len(_traced(caplog)) == 3, \
        "the display path was throttled - an author's second attempt now logs nothing"


def test_the_diagnostic_requery_does_not_open_a_second_incident(cand_env, pg_diagnostics,
                                                                caplog):
    """The other half of the doubling, and the one that is not a throttle.

    `_diagnose_probe_failure` re-runs the DISPLAY wrap to tell
    `candidate_column_missing` from `view_error`. That call still happens and
    still answers - what changed is that its failure no longer counts as news,
    because it is the same root cause reached by a second route. Before this,
    ONE broken view cost TWO tracebacks per key.
    """
    import logging

    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    rule = dict(_loaded_rule(), reference_views=[dict(BROKEN_VIEW, required_binds=[])])

    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        res = enrichment_candidates.resolve_target_candidate(
            cand_env, rule, {"lot": "L1", "slot": "S1"}, "wafer_id")

    assert res["status"] == enrichment_candidates.STATUS_REFUSED
    assert len(_traced(caplog)) == 1, \
        "the diagnostic re-query logged a second traceback for the same root cause"
    assert not [r for r in _errors(caplog)
                if enrichment_config.SITE_REFERENCE_VIEW in r.getMessage()], \
        "the follow-up read opened an incident at the display site"
    # And the refusal it exists to produce is unchanged - the quieting must not
    # have cost the diagnosis.
    details = " ".join(e.get("detail") or "" for e in res["errors"])
    assert "nosuchcol_xyz" in details


def test_the_collector_drains_at_the_real_work_unit_boundary(cand_env, pg_diagnostics, caplog):
    """End to end: the drain is wired to the thing that IS a work unit.

    `AutoConfirmCollector.flush` is the chain worker's per-transaction-group
    boundary. A unit-level drain that nothing calls would report nothing.
    """
    import logging

    pg_diagnostics["diag"] = _FakeDiag(**DIAG_UNDEFINED_COLUMN)
    rule = dict(_loaded_rule(), reference_views=[dict(BROKEN_VIEW, required_binds=[])])
    _seed(cand_env, "encand_test_derived", [
        {"wafer_key": "L1_S1", "lot": "L1", "slot": "S1"},
        {"wafer_key": "L1_S2", "lot": "L1", "slot": "S2"},
    ])

    collector = enrichment_candidates.AutoConfirmCollector(
        "encand_test_derived", rules=[rule])
    assert collector.active, "fixture is inert - the collector must be live to mean anything"
    collector.collect([
        {"business_key_val": "L1_S1", "updates": {"lot": "L1", "slot": "S1"}},
        {"business_key_val": "L1_S2", "updates": {"lot": "L1", "slot": "S2"}},
    ])

    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        collector.flush(cand_env)

    assert len(_traced(caplog)) == 1, "two keys, two tracebacks - the throttle is not wired"
    assert "failed 2 time(s)" in caplog.text, "the unit ended without stating the total"
    assert enrichment_config.drain_driver_error_incidents() == [], \
        "flush left throttle state behind for the next work unit to inherit"


def test_a_driver_with_no_sqlstate_still_separates_its_conditions(cand_env, caplog):
    """No injection: SQLite has no SQLSTATE, and the key must still discriminate.

    Falling back to a constant would throttle `no such column` and `no such
    table` as one thing - which is property (3) failing for exactly the drivers
    that cannot report a condition code.
    """
    import logging

    other = dict(BROKEN_VIEW, query="SELECT wafer_id FROM encand_test_no_such_table")
    with caplog.at_level(logging.ERROR, logger="EnrichmentConfig"):
        _probe_fails(cand_env, times=2)
        for _ in range(2):
            with pytest.raises(enrichment_config.ReferenceViewError):
                enrichment_config.execute_candidate_probe(cand_env, other, "wafer_id", {})

    # SQLite reports both as OperationalError, so this is the honest floor: the
    # two collapse into one entry and the test says so rather than pretending
    # otherwise. What it pins is that the FIRST is never lost and the driver
    # class - not a constant - is what the key falls back to.
    assert len(_traced(caplog)) >= 1
    assert enrichment_config._incident_condition(
        _sqlalchemy_error(cand_env, "SELECT 1 FROM encand_test_no_such_table")
    ) == "OperationalError"


def _sqlalchemy_error(db, sql):
    """Provoke a real driver error and hand back the SQLAlchemy wrapper."""
    from sqlalchemy import text

    nested = db.begin_nested()
    try:
        db.execute(text(sql)).fetchall()
    except Exception as exc:
        nested.rollback()
        return exc
    nested.commit()
    raise AssertionError("the statement was supposed to fail")
