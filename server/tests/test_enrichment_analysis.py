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
    """Every walk in this module defaults to the KEYED queue.

    The display stopped hiding blank-key rows on 2026-08-04 (N36), but nothing
    here may walk them: with no key there is nothing to bind a reference view to.
    """
    _seed(an_env, "enan_test_derived", [{"wafer_key": "ONLYKEY", "lot": "", "slot": ""}])
    rows = list(enrichment_analysis.iter_derived_rows(an_env, _loaded()))
    assert all(crud.clean_str_value(r["keys"]["lot"]) != "" for r in rows)


# A view bound to a PROPER SUBSET of the decision key. Not hypothetical: this is
# the exact shape `_proposed_reference_view` generates when ② promotes a repeated
# judgement ("part of the key determines the target"), and the live config in the
# `enrichment_config` docstring has one too (view #1 binds lot only, of a lot+slot
# key). It is what makes a blank key DANGEROUS rather than merely useless: the
# probe's own `missing_bind` guard never fires, because the blank column is not a
# bind of this view.
SUBSET_VIEW = {
    "label": "slot only",
    "query": "SELECT wafer_id FROM enan_test_hist WHERE slot = :slot",
    "candidate_for": {"wafer_id": "wafer_id"},
}


def _enable_auto_confirm(tmp_path, views):
    """Rewrite the ISOLATED rules file (tmp_path, monkeypatched in `an_env`) with
    the knob on. `server/config/` is never touched - a write there reloads three
    live processes."""
    path = tmp_path / "enrichment_rules.json"
    path.write_text(json.dumps({"enan_rule": _rule(auto_confirm=True, reference_views=views),
                                "enan_single": SINGLE_RULE}), encoding="utf-8")


def test_auto_confirm_sweep_never_writes_to_a_blank_key_row(an_env, tmp_path):
    """The write path must not follow the display.

    This is why the key predicate could not simply be deleted. `resolve_target_
    candidate` does refuse a blank value as `missing_bind` - but only for views
    that BIND that column. Against a subset-bound view (see SUBSET_VIEW) the
    blank column is not a bind at all, so the probe runs, finds exactly one
    candidate on the surviving key, and `confirm_keys` writes it. The value is
    wrong by construction: `slot=S1` is evidence about the OTHER row.

    The fixture asserts the hazard is live before it asserts the refusal, so a
    green result cannot come from an inert setup.
    """
    _enable_auto_confirm(tmp_path, [dict(SUBSET_VIEW)])
    _seed(an_env, "enan_test_src",
          [{"log_key": "k1", "lot": "L1", "slot": "S1", "chip_id": "C1"}])
    _seed(an_env, "enan_test_hist",
          [{"hist_id": "h1", "lot": "L1", "slot": "S1", "wafer_id": "WF_GOOD"}])
    _seed(an_env, "enan_test_derived", [{"wafer_key": "L1_S1", "lot": "L1", "slot": "S1"}])
    # The orphan: lost its `lot`, kept `slot`, so the subset view still binds. Its
    # business key is supplied EXPLICITLY - `composite_key_source` is [lot, slot],
    # so a composed key would come out NULL and `confirm_keys` (which writes by
    # business_key_val) could not land on the row even with the guard removed. That
    # accident would mask the mutation instead of the guard catching it. An explicit
    # key is also the realistic shape: a hand edit on the grid supplies one.
    crud.apply_batch_updates(an_env, "enan_test_derived", schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(
            business_key_val="ORPHAN_BK", updates={"wafer_key": "ORPHAN", "slot": "S1"},
            source_name="user", updated_by="test")], silent=True))
    rule = _loaded()

    # (a) The hazard is real: probed with the blank key, the declared view yields
    #     exactly one candidate - the shape `confirm_keys` writes on.
    trap = enrichment_candidates.resolve_target_candidate(
        an_env, rule, {"lot": "", "slot": "S1"}, "wafer_id")
    assert trap["status"] == enrichment_candidates.STATUS_SINGLE, (
        f"fixture is inert: a blank key must actually resolve to one candidate for "
        f"this test to mean anything (got {trap})")
    assert trap["value"] == "WF_GOOD", "the candidate is real, and it is the WRONG row's"

    # (b) And the sweep still refuses to go near it. The STORED VALUE is asserted
    #     first and the counters second: `queue_size` is a proxy, the cell is the
    #     consequence, and a mutation that trips only the proxy would leave the
    #     real question unanswered.
    stats = enrichment_analysis.run_auto_confirm_sweep(an_env, rule, apply=True,
                                                       log=lambda *_: None)

    # Looked up by the BLANKNESS of the key, not by business_key_val: that key is
    # composed from `composite_key_source` (lot+slot), so a blank lot leaves it
    # NULL - one more reason these rows are broken rather than merely unlabelled.
    # (`''` and NULL are both blank here; `clean_str_value` is the shared funnel.)
    m = models.DYNAMIC_TABLES["enan_test_derived"]
    rows = an_env.query(m).all()
    orphan = next((r for r in rows if crud.clean_str_value(r.lot) == ""), None)
    assert orphan is not None, (
        "fixture premise: the blank-key derived row exists; table holds "
        + repr([(r.business_key_val, r.lot, r.slot, r.wafer_id) for r in rows]))
    assert crud.clean_str_value(orphan.wafer_id) == "", (
        f"the sweep wrote {orphan.wafer_id!r} into a row that has no decision key")
    good = next(r for r in rows if crud.clean_str_value(r.lot) == "L1")
    assert crud.clean_str_value(good.wafer_id) == "WF_GOOD", (
        "the keyed row must still be confirmed - the guard is a filter, not an off switch")
    assert stats["queue_size"] == 1, (
        f"the sweep examined {stats['queue_size']} rows - a blank-key row entered a "
        f"WRITE path")
    assert stats["confirmed"] == 1


def test_classify_names_blank_key_rows_and_totals_the_whole_queue(an_env):
    """④ must reconcile with the worklist remainder, and name what it counts.

    The operator now SEES blank-key rows, so a report whose `queue_size` excluded
    them would disagree with the badge by exactly their count - and
    FEATURE_CHECKLIST ④ reads that disagreement as "the queue predicate has
    split". They are counted, and counted under their own name: an empty
    `no_evidence`-style bucket would not tell anyone the rows are unworkable.
    """
    _seed(an_env, "enan_test_src",
          [{"log_key": "k1", "lot": "L1", "slot": "S1", "chip_id": "C1"}])
    _seed(an_env, "enan_test_derived", [
        {"wafer_key": "L1_S1", "lot": "L1", "slot": "S1"},
        {"wafer_key": "ORPHAN_A", "lot": "", "slot": "S9"},   # partially blank key
        {"wafer_key": "ORPHAN_B", "lot": "", "slot": ""},
    ])

    res = enrichment_analysis.classify_queue(an_env, _loaded(), log=lambda *_: None)
    assert res["queue_size"] == 3, "queue_size must be the queue the operator sees"
    assert res["blank_decision_key"] == 2
    assert res["counts"].get(enrichment_analysis.CLS_BLANK_DECISION_KEY) == 2, (
        "blank-key rows must be counted under their OWN name, not folded into "
        "no_source_rows")
    assert enrichment_analysis.CLS_BLANK_DECISION_KEY in enrichment_analysis.BUG_CLASSES
    # Sum of all classes accounts for every queue row - nothing silently dropped.
    assert sum(res["counts"].values()) == 3
    detail = res["samples"][enrichment_analysis.CLS_BLANK_DECISION_KEY][0]["detail"]
    assert "lot" in detail, f"the sample must name WHICH key is missing (got {detail!r})"
