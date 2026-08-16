from datetime import datetime, timezone
import uuid

import enrichment_actions
import enrichment_config
import ledger_explorer
import ledger_subgraph


NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def contract_rule(*, sources=True):
    reference_views = [{
        "label": "recorded destination",
        "query": "SELECT dt_lot FROM dt_log WHERE dt_job = :dt_job",
        "limit": 20,
        "candidate_for": {"dt_lot_confirmed": "dt_lot"},
        "required_binds": ["dt_job"],
    }]
    return {
        "name": "dt_identity",
        "source_table": "dt_log", "derived_table": "dt_inventory",
        "decision_key": ["dt_job"],
        "target_fields": ["dt_lot_confirmed"],
        "list_columns": [], "aggregations": {}, "auto_confirm": False,
        "reference_views": reference_views,
        "claim_contract": {
            "version": 1, "label_ko": "DT 결과물 신원",
            "anchor": {
                "predicate": "transferred", "payload_path": "to",
                "object_type": "dt_job", "decision_key_map": {"dt_job": "dt_job"},
            },
            "slots": [{
                "target_field": "dt_lot_confirmed", "predicate": "transferred",
                "payload_path": "to.keys.dt_lot",
            }],
            "sources": ([{
                "kind": "reference_view", "view_index": 0,
                "authority": "candidate", "targets": ["dt_lot_confirmed"],
            }] if sources else []),
        },
    }


def transfer_atom(number, job, wafer="WF-A"):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="Wafer",
        subject_keys={"wafer": wafer}, predicate="transferred",
        object_kind="value",
        object_payload={
            "from": {"type": "wafer_grid", "keys": {"wafer": wafer},
                     "position": None},
            "to": {"type": "dt_job", "keys": {"dt_job": job}, "position": None},
        },
        occurred_at=NOW, source_who="dt_log", source_translator_ver="v1",
        source_raw_ref=f"dt_log:{job}", supersedes=None,
        source_event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"event:{job}")),
        source_event_state="source_molecule",
    )


def test_enrich_action_is_reached_by_the_same_graph_walk_and_can_be_reseeded():
    atom = transfer_atom(501, "JOB-1")
    action_lookup = enrichment_actions.InMemoryEnrichmentActionLookup(
        [contract_rule()], rows={"dt_inventory": {}})
    graph = ledger_subgraph.subgraph(
        ledger_explorer.entity_id("Wafer", {"wafer": "WF-A"}),
        ledger_subgraph.InMemoryEvidenceLookup([atom]), hops=4,
        action_lookup=action_lookup)

    action = next(node for node in graph["nodes"] if node["node_kind"] == "action")
    assert action["action_kind"] == "resolve_claim"
    assert action["missing_targets"] == ["dt_lot_confirmed"]
    assert action["terminal_in_automatic_walk"] is True
    assert any(edge["source"] == atom.claim_node_id
               and edge["target"] == action["id"]
               and edge["predicate"] == "needs_enrichment"
               for edge in graph["edges"])
    assert ledger_subgraph.decode_node_id(action["id"])["kind"] == "action"

    tables = ledger_subgraph.tabular_projection(graph)
    assert tables["provenance"] == {
        "source": "ledger_events",
        "projection": "evidence_graph",
        "additive_sources": ["enrichment_action_projection"],
    }
    assert any(row["node_kind"] == "action"
               for row in tables["tables"]["nodes"]["rows"])

    reseeded = ledger_subgraph.subgraph(
        action["id"], ledger_subgraph.InMemoryEvidenceLookup([atom]), hops=12,
        action_lookup=action_lookup)
    assert reseeded["state"] == "ready"
    assert reseeded["seed"]["state"] == "missing_claim"
    assert reseeded["seed"]["keys"]["decision_key"] == {"dt_job": "JOB-1"}


def test_fulfilled_target_removes_the_action_projection():
    atom = transfer_atom(502, "JOB-DONE")
    rows = {"dt_inventory": {
        enrichment_actions._canonical({"dt_job": "JOB-DONE"}): {
            "dt_lot_confirmed": "DT-L001"}}}
    action_lookup = enrichment_actions.InMemoryEnrichmentActionLookup(
        [contract_rule()], rows=rows)
    graph = ledger_subgraph.subgraph(
        ledger_explorer.entity_id("Wafer", {"wafer": "WF-A"}),
        ledger_subgraph.InMemoryEvidenceLookup([atom]), hops=4,
        action_lookup=action_lookup)
    assert not any(node["node_kind"] == "action" for node in graph["nodes"])


def test_missing_supply_contract_is_one_rule_level_meta_action_not_one_per_job():
    atoms = [transfer_atom(503, "JOB-A"), transfer_atom(504, "JOB-B")]
    action_lookup = enrichment_actions.InMemoryEnrichmentActionLookup(
        [contract_rule(sources=False)], rows={"dt_inventory": {}})
    graph = ledger_subgraph.subgraph(
        ledger_explorer.entity_id("Wafer", {"wafer": "WF-A"}),
        ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=4,
        action_lookup=action_lookup)
    actions = [node for node in graph["nodes"] if node["node_kind"] == "action"]
    assert len(actions) == 1
    assert actions[0]["state"] == "undeclared_claim_source"
    assert actions[0]["action_kind"] == "declare_claim_source"
    assert actions[0]["keys"]["decision_key"] is None
    links = [edge for edge in graph["edges"]
             if edge["target"] == actions[0]["id"]
             and edge["predicate"] == "needs_enrichment"]
    assert len(links) == 2


def test_rule_level_source_action_payload_does_not_depend_on_first_row_missing_subset():
    rule = contract_rule(sources=False)
    rule["target_fields"] = ["dt_lot_confirmed", "dt_slot_confirmed"]
    rule["claim_contract"]["slots"].append({
        "target_field": "dt_slot_confirmed", "predicate": "transferred",
        "payload_path": "to.keys.dt_slot",
    })
    rows = {
        "dt_inventory": {
            enrichment_actions._canonical({"dt_job": "JOB-A"}): {
                "dt_lot_confirmed": "L1", "dt_slot_confirmed": None,
            },
            enrichment_actions._canonical({"dt_job": "JOB-B"}): {
                "dt_lot_confirmed": None, "dt_slot_confirmed": "2",
            },
        },
    }
    graph = ledger_subgraph.subgraph(
        ledger_explorer.entity_id("Wafer", {"wafer": "WF-A"}),
        ledger_subgraph.InMemoryEvidenceLookup([
            transfer_atom(507, "JOB-A"), transfer_atom(508, "JOB-B")]), hops=4,
        action_lookup=enrichment_actions.InMemoryEnrichmentActionLookup([rule], rows))
    actions = [node for node in graph["nodes"] if node["node_kind"] == "action"]
    assert len(actions) == 1
    assert actions[0]["missing_targets"] == [
        "dt_lot_confirmed", "dt_slot_confirmed"]


def test_undeployed_rule_becomes_one_configuration_meta_action_without_row_reads():
    class BlockedLookup(enrichment_actions.EnrichmentActionLookup):
        def __init__(self):
            super().__init__([contract_rule()], blocked_rules={"dt_identity"})

        def _rows_for(self, rule, decision_keys):
            raise AssertionError("a blocked rule must not read its derived table")

    atoms = [transfer_atom(505, "JOB-A"), transfer_atom(506, "JOB-B")]
    graph = ledger_subgraph.subgraph(
        ledger_explorer.entity_id("Wafer", {"wafer": "WF-A"}),
        ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=4,
        action_lookup=BlockedLookup())
    actions = [node for node in graph["nodes"] if node["node_kind"] == "action"]
    assert len(actions) == 1
    assert actions[0]["state"] == "enrichment_contract_not_deployed"
    assert actions[0]["action_kind"] == "repair_enrichment_contract"


def test_sql_row_reader_preserves_every_decision_context_sharing_one_business_key():
    from database import models

    class Column:
        def in_(self, values):
            assert values == ["G1"]
            return ("in", values)

    class Query:
        def filter(self, condition):
            assert condition == ("in", ["G1"])
            return self

        def all(self):
            return [("G1", "LOT-DONE")]

    class Db:
        def query(self, *columns):
            assert len(columns) == 2
            return Query()

    rule = contract_rule()
    lookup = enrichment_actions.SqlEnrichmentActionLookup(Db(), rules=[rule])
    lookup.table_config = {"dt_inventory": {
        "business_key": "group",
        "composite_key_source": ["group"],
        "composite_key_separator": "_",
    }}
    fake_model = type("FakeModel", (), {
        "business_key_val": Column(), "dt_lot_confirmed": Column()})
    previous = models.DYNAMIC_TABLES.get("dt_inventory")
    models.DYNAMIC_TABLES["dt_inventory"] = fake_model
    try:
        rows = lookup._rows_for(rule, [
            {"group": "G1", "member": "A"},
            {"group": "G1", "member": "B"},
        ])
    finally:
        if previous is None:
            models.DYNAMIC_TABLES.pop("dt_inventory", None)
        else:
            models.DYNAMIC_TABLES["dt_inventory"] = previous
    assert rows == {
        enrichment_actions._canonical({"group": "G1", "member": "A"}): {
            "dt_lot_confirmed": "LOT-DONE"},
        enrichment_actions._canonical({"group": "G1", "member": "B"}): {
            "dt_lot_confirmed": "LOT-DONE"},
    }


def test_claim_contract_is_additive_and_invalid_contract_does_not_kill_legacy_rule():
    raw = {
        "source_table": "dt_log", "derived_table": "dt_inventory",
        "decision_key": ["dt_job"], "target_fields": ["dt_lot_confirmed"],
        "list_columns": [], "aggregations": {},
        "reference_views": [{
            "label": "recorded destination",
            "query": "SELECT dt_lot FROM dt_log WHERE dt_job = :dt_job",
            "candidate_for": {"dt_lot_confirmed": "dt_lot"},
        }],
        "claim_contract": contract_rule()["claim_contract"],
    }
    loaded = enrichment_config.validate_enrichment_rules({"r": raw})
    assert len(loaded) == 1
    assert loaded[0]["claim_contract"]["anchor"]["predicate"] == "transferred"

    rejected = []
    broken = dict(raw, claim_contract={"version": 1})
    legacy = enrichment_config.validate_enrichment_rules(
        {"r": broken}, rejections=rejected)
    assert len(legacy) == 1
    assert legacy[0]["claim_contract"] is None
    assert any(item["scope"] == "claim_contract" for item in rejected)

    typo_contract = dict(contract_rule()["claim_contract"])
    typo_contract["anchor"] = dict(
        typo_contract["anchor"], predicate="transferrred")
    rejected = []
    typo_rule = enrichment_config.validate_enrichment_rules(
        {"r": dict(raw, claim_contract=typo_contract)}, rejections=rejected)
    assert len(typo_rule) == 1
    assert typo_rule[0]["claim_contract"] is None
    assert any("canonical ledger vocabulary" in item["detail"]
               for item in rejected)


def test_enrich_action_id_rejects_noncanonical_spelling():
    node_id = enrichment_actions.enrich_action_node_id(
        "r", 1, enrichment_actions.ACTION_SCOPE_RESOLVE, {"dt_job": "J1"})
    assert enrichment_actions.decode_enrich_action_id(node_id)["decision_key"] == {
        "dt_job": "J1"}
    try:
        enrichment_actions.decode_enrich_action_id(node_id + "=")
    except ValueError as exc:
        assert "canonical" in str(exc) or "JSON" in str(exc)
    else:
        raise AssertionError("noncanonical Enrich Action id was accepted")
