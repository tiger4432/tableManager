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
            "wafer_id": "string", "chip_count": "number",
        },
    },
    # The reference table the candidate views read. Not part of the rule.
    "encand_test_hist": {
        "business_key": "hist_id",
        "column_types": {
            "hist_id": "string", "lot": "string", "slot": "string",
            "wafer_id": "string",
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

    # Reference history: L1/S1 -> WF1, L1/S2 -> WF2. Keyed by lot alone this is
    # two candidates; keyed by lot+slot it is one.
    _seed(db_session, "encand_test_hist", [
        {"hist_id": "H1", "lot": "L1", "slot": "S1", "wafer_id": "WF1"},
        {"hist_id": "H2", "lot": "L1", "slot": "S2", "wafer_id": "WF2"},
        {"hist_id": "H3", "lot": "L2", "slot": "S1", "wafer_id": "WF3"},
        {"hist_id": "H4", "lot": "L2", "slot": "S1", "wafer_id": "WF9"},  # ambiguous even narrow
    ])
    import main
    main.TABLE_COUNT_CACHE.clear()
    return db_session


def _seed(db, table, rows, source_name="pipeline_parser", tx_id="seed", silent=True):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name=source_name,
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=tx_id, silent=silent))


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


def test_a_truncated_probe_refuses_instead_of_claiming_single(cand_env, monkeypatch):
    """A truncated READ cannot prove 'exactly one' - the unread remainder may hold
    the contradiction. Same posture as `view_error`: incomplete is UNKNOWN, not empty.

    `CANDIDATE_PROBE_MAX_ROWS` is the only thing bounding a candidate-declaring view
    with no binds, which would otherwise scan its whole table once per probed key.
    """
    monkeypatch.setattr(enrichment_config, "CANDIDATE_PROBE_MAX_ROWS", 2)
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"P{i}", "lot": "LP", "slot": "S1", "wafer_id": "WF1"}
        for i in range(4)
    ])
    res = enrichment_candidates.resolve_target_candidate(
        cand_env, _loaded_rule(), {"lot": "LP", "slot": "S1"}, "wafer_id")
    assert res["status"] == enrichment_candidates.STATUS_REFUSED
    assert res["reason"] == enrichment_candidates.REASON_PROBE_TRUNCATED
    # The partial finding is still reported so a UI can show it; it just cannot gate.
    assert res["value"] == "WF1"


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
    """
    _seed(cand_env, "encand_test_hist", [
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


def test_row_truncation_is_still_detected_when_the_groups_are_also_clipped(cand_env, monkeypatch):
    """The consequence of the LOW: a genuinely truncated READ used to report
    `row_truncated: False` whenever the groups were clipped too, because the
    under-reported `scanned` never reached the bound it is compared against."""
    monkeypatch.setattr(enrichment_config, "CANDIDATE_PROBE_MAX_ROWS", 3)
    _seed(cand_env, "encand_test_hist", [
        {"hist_id": f"R{i}", "lot": "LR", "slot": "S1", "wafer_id": f"W{i}"}
        for i in range(6)
    ])
    view = dict(_loaded_rule()["reference_views"][0], limit=1)
    probe = enrichment_config.execute_candidate_probe(
        cand_env, view, "wafer_id", {"lot": "LR", "slot": "S1"})
    assert len(probe["pairs"]) == 2 and probe["distinct_truncated"] is True
    assert probe["scanned"] == 3, "the inner scan bound was reached"
    assert probe["row_truncated"] is True, (
        "the scan hit CANDIDATE_PROBE_MAX_ROWS - clipping the GROUP BY output "
        "must not hide that")


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
