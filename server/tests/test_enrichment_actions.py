from datetime import datetime, timezone
import uuid

import enrichment_actions
import enrichment_config
import ledger_explorer
from ledger_api import ledger_subgraph


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


#: 🔴 FIVE TESTS RETIRED 2026-08-28, WITH THE ACTION NODES THEY WALKED TO. The graph
#: walk stopped expanding enrich actions when every node became a declared entity - an action
#: is a thing to DO about a rule, not a place in the ledger's graph. What these asserted was
#: reachability THROUGH the walk, which no longer exists by design.
#:
#: The action lookup itself is untouched and still covered here: id canonicalisation, the row
#: reader's decision contexts, and the fulfilled-target projection.
