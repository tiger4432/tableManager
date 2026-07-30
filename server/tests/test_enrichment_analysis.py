"""[Enrichment ②④] Promote a repeated judgement; classify the cause of a gap.

④ proves each CLASS can be produced, and that the bug class is not vacuous:
   remove the value from the source and the row stops being classified as a
   pipeline gap.
② proves the promotion is a functional dependency (a conflict rejects it), that
   it is mined from HUMAN cells only, and - the strongest check - that the
   proposed reference view actually resolves through ①'s predicate. A proposal
   that ① could not execute would be a document, not a mechanism.

[Isolation] `enan_test_` prefix (see the bonding_log trap in server-pm memory).
"""
import json

import pytest

import enrichment_analysis
import enrichment_candidates
import enrichment_config
from database import crud, models, schemas

AN_TABLES = {
    "enan_test_src": {
        "business_key": "log_key",
        "composite_key_source": ["lot", "slot", "chip_id"],
        "composite_key_separator": "_",
        "column_types": {
            "log_key": "string", "lot": "string", "slot": "string",
            "chip_id": "string",
            # Same name as the rule's target field: this is what makes a
            # "the source HAS it and nothing carried it across" gap detectable.
            "wafer_id": "string",
        },
    },
    "enan_test_derived": {
        "business_key": "wafer_key",
        "composite_key_source": ["lot", "slot"],
        "composite_key_separator": "_",
        "column_types": {
            "wafer_key": "string", "lot": "string", "slot": "string",
            "wafer_id": "string", "chip_count": "number",
        },
    },
    "enan_test_hist": {
        "business_key": "hist_id",
        "column_types": {"hist_id": "string", "lot": "string", "slot": "string",
                         "wafer_id": "string"},
    },
    # Single-column decision key, to prove ②'s `no_proper_subset` refusal.
    "enan_test_single_src": {
        "business_key": "s_key",
        "column_types": {"s_key": "string", "lot": "string"},
    },
    "enan_test_single_derived": {
        "business_key": "lot",
        "column_types": {"lot": "string", "owner": "string"},
    },
}

NARROW = {
    "label": "narrow",
    "query": "SELECT wafer_id FROM enan_test_hist WHERE lot = :lot AND slot = :slot",
    "candidate_for": {"wafer_id": "wafer_id"},
}


def _rule(**overrides):
    r = {
        "source_table": "enan_test_src",
        "derived_table": "enan_test_derived",
        "decision_key": ["lot", "slot"],
        "target_fields": ["wafer_id"],
        "list_columns": ["chip_count"],
        "auto_confirm": False,
        "reference_views": [dict(NARROW)],
    }
    r.update(overrides)
    return r


SINGLE_RULE = {
    "source_table": "enan_test_single_src",
    "derived_table": "enan_test_single_derived",
    "decision_key": ["lot"],
    "target_fields": ["owner"],
    "reference_views": [],
}


@pytest.fixture()
def an_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(AN_TABLES)
    crud.TABLE_CONFIG.update(AN_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text(json.dumps({"enan_rule": _rule(), "enan_single": SINGLE_RULE}),
                          encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))
    settings = tmp_path / "ingestion_settings.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(enrichment_candidates, "INGESTION_SETTINGS_PATH", str(settings))
    enrichment_candidates.reset_warnings()
    import main
    main.TABLE_COUNT_CACHE.clear()
    return db_session


def _seed(db, table, rows, source_name="pipeline_parser", tx_id="seed"):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name=source_name,
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=tx_id, silent=True))


def _loaded(name="enan_rule"):
    rules = enrichment_config.load_enrichment_rules(known_tables=crud.TABLE_CONFIG)
    return next(r for r in rules if r["name"] == name)


# ---------------------------------------------------------------------------
# ④ Classify the cause of a gap
# ---------------------------------------------------------------------------

def test_mapping_gap_is_detected_and_is_not_vacuous(an_env):
    """The BUG class: the source carries the value and nothing brought it across.

    Then the injection that proves the check is real - blank the source value and
    the same row must leave the bug class.
    """
    _seed(an_env, "enan_test_src",
          [{"log_key": "a1", "lot": "L1", "slot": "S1", "chip_id": "C1", "wafer_id": "WF1"}])
    _seed(an_env, "enan_test_derived", [{"wafer_key": "L1_S1", "lot": "L1", "slot": "S1"}])

    rule = _loaded()
    res = enrichment_analysis.classify_queue(an_env, rule, log=lambda *_: None)
    assert res["queue_size"] == 1
    assert res["counts"].get(enrichment_analysis.CLS_MAPPING_GAP) == 1

    # INJECTED: the source no longer has the value -> no longer a pipeline bug.
    _seed(an_env, "enan_test_src",
          [{"log_key": "a1", "lot": "L1", "slot": "S1", "chip_id": "C1", "wafer_id": ""}],
          tx_id="blank")
    res2 = enrichment_analysis.classify_queue(an_env, rule, log=lambda *_: None)
    assert res2["counts"].get(enrichment_analysis.CLS_MAPPING_GAP) is None


def test_resolvable_and_ambiguous_are_separated_from_real_work(an_env):
    _seed(an_env, "enan_test_src", [
        {"log_key": "b1", "lot": "R1", "slot": "S1", "chip_id": "C1"},
        {"log_key": "b2", "lot": "A1", "slot": "S1", "chip_id": "C1"},
        {"log_key": "b3", "lot": "N1", "slot": "S1", "chip_id": "C1"},
    ])
    _seed(an_env, "enan_test_hist", [
        {"hist_id": "h1", "lot": "R1", "slot": "S1", "wafer_id": "WF_R"},   # one candidate
        {"hist_id": "h2", "lot": "A1", "slot": "S1", "wafer_id": "WF_A1"},  # two candidates
        {"hist_id": "h3", "lot": "A1", "slot": "S1", "wafer_id": "WF_A2"},
    ])                                                                       # N1: none
    _seed(an_env, "enan_test_derived", [
        {"wafer_key": "R1_S1", "lot": "R1", "slot": "S1"},
        {"wafer_key": "A1_S1", "lot": "A1", "slot": "S1"},
        {"wafer_key": "N1_S1", "lot": "N1", "slot": "S1"},
    ])
    res = enrichment_analysis.classify_queue(an_env, _loaded(), log=lambda *_: None)
    c = res["counts"]
    assert c.get(enrichment_analysis.CLS_RESOLVABLE) == 1
    assert c.get(enrichment_analysis.CLS_AMBIGUOUS) == 1
    assert c.get(enrichment_analysis.CLS_NO_EVIDENCE) == 1
    assert res["no_evidence_reasons"].get(enrichment_candidates.REASON_NO_CANDIDATE) == 1


def test_no_source_rows_is_its_own_class(an_env):
    """A derived row with no source rows behind it is neither work nor a bug."""
    _seed(an_env, "enan_test_derived", [{"wafer_key": "Z9_S1", "lot": "Z9", "slot": "S1"}])
    res = enrichment_analysis.classify_queue(an_env, _loaded(), log=lambda *_: None)
    assert res["counts"].get(enrichment_analysis.CLS_NO_SOURCE_ROWS) == 1


def test_probe_budget_reports_unprobed_rather_than_guessing(an_env):
    _seed(an_env, "enan_test_src", [
        {"log_key": "c1", "lot": "P1", "slot": "S1", "chip_id": "C1"},
        {"log_key": "c2", "lot": "P2", "slot": "S1", "chip_id": "C1"},
    ])
    _seed(an_env, "enan_test_derived", [
        {"wafer_key": "P1_S1", "lot": "P1", "slot": "S1"},
        {"wafer_key": "P2_S1", "lot": "P2", "slot": "S1"},
    ])
    res = enrichment_analysis.classify_queue(an_env, _loaded(), probe_limit=1,
                                             log=lambda *_: None)
    assert res["counts"].get(enrichment_analysis.CLS_UNPROBED) == 1
    assert res["probed"] == 1


def test_classify_is_read_only(an_env):
    _seed(an_env, "enan_test_src",
          [{"log_key": "d1", "lot": "L9", "slot": "S1", "chip_id": "C1", "wafer_id": "WF9"}])
    _seed(an_env, "enan_test_derived", [{"wafer_key": "L9_S1", "lot": "L9", "slot": "S1"}])
    m = models.DYNAMIC_TABLES["enan_test_derived"]
    before = an_env.query(m).filter(m.business_key_val == "L9_S1").first().wafer_id
    enrichment_analysis.classify_queue(an_env, _loaded(), log=lambda *_: None)
    after = an_env.query(m).filter(m.business_key_val == "L9_S1").first().wafer_id
    assert before == after


# ---------------------------------------------------------------------------
# ② Promote a repeated judgement
# ---------------------------------------------------------------------------

def _resolve_by_hand(db, rows):
    """A human filling target values (source_name='user' — priority 0)."""
    _seed(db, "enan_test_derived", rows, source_name="user", tx_id="human")


def test_repeated_human_judgement_becomes_a_proposal(an_env):
    """lot alone determines wafer_id across three slots -> promotable."""
    _seed(an_env, "enan_test_derived", [
        {"wafer_key": f"L1_S{i}", "lot": "L1", "slot": f"S{i}"} for i in range(1, 4)])
    _resolve_by_hand(an_env, [
        {"wafer_key": f"L1_S{i}", "lot": "L1", "slot": f"S{i}", "wafer_id": "WF_SAME"}
        for i in range(1, 4)])

    res = enrichment_analysis.analyze_promotions(an_env, _loaded(), min_support=3,
                                                 log=lambda *_: None)
    assert res["refused"] is None
    props = [p for p in res["proposals"] if p["antecedent_columns"] == ["lot"]]
    assert len(props) == 1
    p = props[0]
    assert p["target_field"] == "wafer_id"
    assert p["total_support"] == 3
    assert p["reference_view"]["candidate_for"] == {"wafer_id": "wafer_id"}
    assert ":lot" in p["reference_view"]["query"]


def test_a_conflict_rejects_the_rule_and_says_why(an_env):
    """INJECTED DEFECT: the same lot resolved to two different wafers. That is not
    a function, so no rule may be proposed from it."""
    _seed(an_env, "enan_test_derived", [
        {"wafer_key": f"L2_S{i}", "lot": "L2", "slot": f"S{i}"} for i in range(1, 5)])
    _resolve_by_hand(an_env, [
        {"wafer_key": "L2_S1", "lot": "L2", "slot": "S1", "wafer_id": "WF_A"},
        {"wafer_key": "L2_S2", "lot": "L2", "slot": "S2", "wafer_id": "WF_A"},
        {"wafer_key": "L2_S3", "lot": "L2", "slot": "S3", "wafer_id": "WF_A"},
        {"wafer_key": "L2_S4", "lot": "L2", "slot": "S4", "wafer_id": "WF_B"},
    ])
    res = enrichment_analysis.analyze_promotions(an_env, _loaded(), min_support=3,
                                                 log=lambda *_: None)
    assert not [p for p in res["proposals"] if p["antecedent_columns"] == ["lot"]]
    conflict = next(c for c in res["conflicts"] if c["antecedent_columns"] == ["lot"])
    assert "does not determine" in conflict["why_rejected"]


def test_machine_written_values_are_not_evidence_of_a_judgement(an_env):
    """A value an auto-confirm or backfill wrote is not a human decision, so it
    must never be laundered into a rule."""
    _seed(an_env, "enan_test_derived", [
        {"wafer_key": f"L3_S{i}", "lot": "L3", "slot": f"S{i}"} for i in range(1, 4)])
    _seed(an_env, "enan_test_derived",
          [{"wafer_key": f"L3_S{i}", "lot": "L3", "slot": f"S{i}", "wafer_id": "WF_MACHINE"}
           for i in range(1, 4)],
          source_name=enrichment_candidates.SOURCE_NAME, tx_id="machine")
    res = enrichment_analysis.analyze_promotions(an_env, _loaded(), min_support=3,
                                                 log=lambda *_: None)
    assert res["human_cells"] == 0
    assert res["proposals"] == []


def test_below_threshold_is_not_promoted(an_env):
    _seed(an_env, "enan_test_derived", [
        {"wafer_key": f"L4_S{i}", "lot": "L4", "slot": f"S{i}"} for i in range(1, 3)])
    _resolve_by_hand(an_env, [
        {"wafer_key": f"L4_S{i}", "lot": "L4", "slot": f"S{i}", "wafer_id": "WF_TWICE"}
        for i in range(1, 3)])
    res = enrichment_analysis.analyze_promotions(an_env, _loaded(), min_support=3,
                                                 log=lambda *_: None)
    assert not [p for p in res["proposals"] if p["antecedent_columns"] == ["lot"]]


def test_single_column_decision_key_is_refused_with_a_reason(an_env):
    res = enrichment_analysis.analyze_promotions(an_env, _loaded("enan_single"),
                                                 log=lambda *_: None)
    assert res["refused"] == "no_proper_subset"
    assert res["proposals"] == []


def test_proposal_never_writes_config(an_env, tmp_path):
    before = (tmp_path / "enrichment_rules.json").read_text(encoding="utf-8")
    _seed(an_env, "enan_test_derived", [
        {"wafer_key": f"L5_S{i}", "lot": "L5", "slot": f"S{i}"} for i in range(1, 4)])
    _resolve_by_hand(an_env, [
        {"wafer_key": f"L5_S{i}", "lot": "L5", "slot": f"S{i}", "wafer_id": "WF5"}
        for i in range(1, 4)])
    enrichment_analysis.analyze_promotions(an_env, _loaded(), min_support=3,
                                           log=lambda *_: None)
    assert (tmp_path / "enrichment_rules.json").read_text(encoding="utf-8") == before


def test_proposed_view_is_accepted_by_the_real_loader_and_resolves(an_env):
    """The strongest check on ②: the proposal is not prose, it EXECUTES.

    Feed the generated reference view back through the real rule loader and ①'s
    predicate. A fourth slot of the same lot must now resolve to a single
    candidate - i.e. the human judgement has become a machine rule, which is the
    whole point of ②.
    """
    _seed(an_env, "enan_test_derived", [
        {"wafer_key": f"L6_S{i}", "lot": "L6", "slot": f"S{i}"} for i in range(1, 4)])
    _resolve_by_hand(an_env, [
        {"wafer_key": f"L6_S{i}", "lot": "L6", "slot": f"S{i}", "wafer_id": "WF6"}
        for i in range(1, 4)])
    res = enrichment_analysis.analyze_promotions(an_env, _loaded(), min_support=3,
                                                 log=lambda *_: None)
    view = next(p["reference_view"] for p in res["proposals"]
                if p["antecedent_columns"] == ["lot"])

    promoted = _rule(reference_views=[view])
    normalized, err = enrichment_config._validate_rule("promoted", promoted, AN_TABLES)
    assert err is None, f"the real loader rejected the proposal: {err}"
    assert normalized["reference_views"], "the proposed view was dropped by the loader"

    # A NEW key of the same lot, never resolved by hand.
    _seed(an_env, "enan_test_derived", [{"wafer_key": "L6_S9", "lot": "L6", "slot": "S9"}])
    verdict = enrichment_candidates.resolve_target_candidate(
        an_env, normalized, {"lot": "L6", "slot": "S9"}, "wafer_id")
    assert verdict["status"] == enrichment_candidates.STATUS_SINGLE
    assert verdict["value"] == "WF6"

    # ...and the safety property that makes the promotion retractable-in-effect:
    # add a contradicting judgement and the SAME view now refuses.
    _seed(an_env, "enan_test_derived", [{"wafer_key": "L6_S8", "lot": "L6", "slot": "S8"}])
    _resolve_by_hand(an_env, [{"wafer_key": "L6_S8", "lot": "L6", "slot": "S8",
                               "wafer_id": "WF6_OTHER"}])
    verdict2 = enrichment_candidates.resolve_target_candidate(
        an_env, normalized, {"lot": "L6", "slot": "S9"}, "wafer_id")
    assert verdict2["status"] == enrichment_candidates.STATUS_REFUSED
    assert verdict2["reason"] == enrichment_candidates.REASON_AMBIGUOUS


# ---------------------------------------------------------------------------
# ① retroactive sweep — the dry-run is the instrument
# ---------------------------------------------------------------------------

def test_sweep_dry_run_measures_without_writing(an_env):
    _seed(an_env, "enan_test_src",
          [{"log_key": "e1", "lot": "W1", "slot": "S1", "chip_id": "C1"}])
    _seed(an_env, "enan_test_hist",
          [{"hist_id": "hh1", "lot": "W1", "slot": "S1", "wafer_id": "WF_W1"}])
    _seed(an_env, "enan_test_derived", [{"wafer_key": "W1_S1", "lot": "W1", "slot": "S1"}])

    rule = _loaded()
    stats = enrichment_analysis.run_auto_confirm_sweep(an_env, rule, apply=False,
                                                       log=lambda *_: None)
    assert stats["confirmed"] == 1
    assert stats["mode"] == "dry-run"
    m = models.DYNAMIC_TABLES["enan_test_derived"]
    assert crud.clean_str_value(
        an_env.query(m).filter(m.business_key_val == "W1_S1").first().wafer_id) == "", \
        "a dry-run must not write"


def test_sweep_apply_refused_while_the_knob_is_off(an_env):
    with pytest.raises(enrichment_analysis.AnalysisRefused) as e:
        enrichment_analysis.run_auto_confirm_sweep(an_env, _loaded(), apply=True,
                                                   log=lambda *_: None)
    assert "auto_confirm" in str(e.value)


def test_sweep_refuses_a_rule_with_no_declaration(an_env):
    rule = dict(_loaded(), reference_views=[])
    with pytest.raises(enrichment_analysis.AnalysisRefused) as e:
        enrichment_analysis.run_auto_confirm_sweep(an_env, rule, log=lambda *_: None)
    assert "candidate_for" in str(e.value)


def test_queue_predicate_excludes_blank_key_rows(an_env):
    """The queue predicate is the server's single composition, so a row without
    its decision keys must not appear here either (spec §5.1)."""
    _seed(an_env, "enan_test_derived", [{"wafer_key": "ONLYKEY", "lot": "", "slot": ""}])
    rows = list(enrichment_analysis.iter_derived_rows(an_env, _loaded()))
    assert all(crud.clean_str_value(r["keys"]["lot"]) != "" for r in rows)
