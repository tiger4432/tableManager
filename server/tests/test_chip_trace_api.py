"""GET /graph/chip-trace - wafer-scoped chip trace, and the edge-spatial refusal.

The endpoint is NOT a BFS. It is a fixed shape: two bounded typed queries around a
hard wafer scope. What has to be proved is therefore not "did it walk far enough"
but the opposite - that the shape refuses to leak:

- the wafer is a scope, so sibling cells of the same core are absent;
- Knob/Recipe/Eqp are LEAVES, so a foreign wafer's events sharing our Eqp are absent
  (this is decision (2) / the forbidden S->D direction, enforced by query shape
  because the mapping config has no channel to declare a class on a stub label);
- a BaseCell the seed bonded to is reached, but the OTHER chip bonded to that same
  BaseCell is not - there is no back-expansion;
- no hop is ever silently empty: every leg says recorded / none_recorded /
  not_declared, and an unresolvable wafer says scope_unresolved instead of picking.

Table names carry a `ct_test_` prefix so they cannot collide with a real table in
the user's gitignored config (ontology-pm memory: the bonding_log trap).
"""
import datetime
import json

import pytest

import main
import ontology_config
import enrichment_config
from database import crud
from database.models import GraphNode, GraphEdge

T20 = datetime.datetime(2026, 7, 20, 9, 0, 0)
T21 = datetime.datetime(2026, 7, 21, 9, 0, 0)
T22 = datetime.datetime(2026, 7, 22, 9, 0, 0)
T25 = datetime.datetime(2026, 7, 25, 16, 10, 0)
T26 = datetime.datetime(2026, 7, 26, 10, 35, 13)
T29 = datetime.datetime(2026, 7, 29, 10, 26, 0)


# --------------------------------------------------------------------------
# ontology mapping used by the declared-pairs cross-check
# --------------------------------------------------------------------------
CT_TABLES = {
    "ct_test_bonding": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string", "eventtime": "string",
            "core_lot": "string", "core_slot": "string", "cx": "number", "cy": "number",
            "base_id": "string", "bx": "number", "by": "number",
        },
    },
    "ct_test_dt": {
        "business_key": "dt_id",
        "column_types": {
            "dt_id": "string", "eventtime": "string", "dt_eqp": "string",
            "core_lot": "string", "core_slot": "string", "cx": "number", "cy": "number",
            "tape_lot": "string", "tape_slot": "string", "tx": "number", "ty": "number",
        },
    },
    "ct_test_process": {
        "business_key": "proc_id",
        "column_types": {
            "proc_id": "string", "start_time": "string", "lot": "string", "slot": "string",
            "eqp_id": "string", "recipe_id": "string", "knobs": "string",
        },
    },
}

CT_MAPPING = {
    "ct_test_bonding": {
        "description": "bonding event (chip trace test)",
        "event_time_column": "eventtime",
        "node": {"label": "CoreCell", "identity": ["core_lot", "core_slot", "cx", "cy"],
                 "node_class": "dynamic"},
        "edges": [
            {"type": "BONDED_TO", "target_label": "BaseCell",
             "target_identity_from": ["base_id", "bx", "by"],
             "props": ["eventtime", "log_id"], "description": "base cell this die landed on"},
            {"type": "FROM_CORE", "target_label": "Core",
             "target_identity_from": ["core_lot", "core_slot"],
             "description": "the core wafer this cell belongs to"},
        ],
    },
    "ct_test_dt": {
        "description": "die transfer event (chip trace test)",
        "event_time_column": "eventtime",
        "node": {"label": "CoreCell", "identity": ["core_lot", "core_slot", "cx", "cy"],
                 "node_class": "dynamic"},
        "edges": [
            {"type": "TRANSFERRED_TO", "target_label": "DtCell",
             "target_identity_from": ["tape_lot", "tape_slot", "tx", "ty"],
             "props": ["eventtime", "dt_eqp", "dt_id"], "description": "tape cell"},
        ],
    },
    "ct_test_process": {
        "description": "process event (chip trace test)",
        "event_time_column": "start_time",
        "node": {"label": "ProcessEvent", "identity": "proc_id", "node_class": "dynamic"},
        "edges": [
            {"type": "PERFORMED_ON", "target_label": "Core",
             "target_identity_from": ["lot", "slot"], "description": "core this ran on"},
            {"type": "USED_KNOB", "target_label": "Knob",
             "target_identity_from": ["knobs"], "description": "knob bundle (leaf)"},
            {"type": "USED_RECIPE", "target_label": "Recipe",
             "target_identity_from": ["recipe_id"], "description": "recipe (leaf)"},
            {"type": "EXECUTED_BY", "target_label": "Eqp",
             "target_identity_from": ["eqp_id"], "description": "equipment (leaf)"},
        ],
    },
}


def _add_node(db, label, identity_key, props=None):
    n = GraphNode(label=label, identity_key=identity_key, props=props or {})
    db.add(n)
    db.flush()
    return n


def _add_edge(db, from_n, to_n, edge_type, source_name="pipeline_parser",
              event_time=None, props=None):
    e = GraphEdge(
        type=edge_type, from_node=from_n.id, to_node=to_n.id,
        source_name=source_name, event_time=event_time, props=props or {},
    )
    db.add(e)
    db.flush()
    return e


def _write_mapping(tmp_path, monkeypatch, mapping):
    mapping_path = tmp_path / "ontology_mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(mapping_path))
    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))
    return mapping_path


@pytest.fixture()
def chip_env(db_session, tmp_path, monkeypatch):
    """Mirror of the live shape, small enough to assert entity by entity.

    CORE-A ......... the scope. Two ProcessEvents.
    CORE-B ......... a FOREIGN wafer that shares Eqp E1 and BaseCell BASE-28|2|1.
    CORE-C ......... a wafer with NO ProcessEvent at all.

    SEED       CoreCell CORE-A|05|13|5  bonding x2 (rework, 07-25 and 07-29) + dt
    SIBLING    CoreCell CORE-A|05|1|1   bonding only, same core as the seed
    NOPROC     CoreCell CORE-C|18|2|2   its core has no process rows
    AMBIG      CoreCell CORE-A|05|9|9   claims TWO cores
    FOREIGN    CoreCell CORE-B|01|1|1   bonded to the SAME BaseCell as the seed
    """
    crud.TABLE_CONFIG.update(CT_TABLES)
    _write_mapping(tmp_path, monkeypatch, CT_MAPPING)

    db = db_session
    n = {
        "core_a": _add_node(db, "Core", "CORE-A|05", {"wafer_id": "W-A"}),
        "core_b": _add_node(db, "Core", "CORE-B|01"),
        "core_c": _add_node(db, "Core", "CORE-C|18"),
        "seed": _add_node(db, "CoreCell", "CORE-A|05|13|5", {"cx": 13, "cy": 5}),
        "sibling": _add_node(db, "CoreCell", "CORE-A|05|1|1"),
        "noproc": _add_node(db, "CoreCell", "CORE-C|18|2|2"),
        "ambig": _add_node(db, "CoreCell", "CORE-A|05|9|9"),
        "foreign": _add_node(db, "CoreCell", "CORE-B|01|1|1"),
        "base28": _add_node(db, "BaseCell", "BASE-28|2|1"),
        "base92": _add_node(db, "BaseCell", "BASE-92|1|2"),
        "base77": _add_node(db, "BaseCell", "BASE-77|1|1"),
        "base11": _add_node(db, "BaseCell", "BASE-11|1|1"),
        "dtcell": _add_node(db, "DtCell", "TAPE-A|01|5|8"),
        "pe1": _add_node(db, "ProcessEvent", "PE-1", {"step": "CLEAN"}),
        "pe2": _add_node(db, "ProcessEvent", "PE-2", {"step": "CMP"}),
        "pe9": _add_node(db, "ProcessEvent", "PE-9", {"step": "ETCH"}),
        "knob1": _add_node(db, "Knob", '{"chem": "SC1"}'),
        "recipe1": _add_node(db, "Recipe", "R-CLEAN-01"),
        "eqp1": _add_node(db, "Eqp", "EQP-01"),
    }

    # the seed's own destinations - rework over time, two dates, must not collapse
    _add_edge(db, n["seed"], n["base28"], "BONDED_TO", source_name="bond_0725.csv",
              event_time=T25, props={"eventtime": "2026-07-25 16:10", "log_id": "BL-1"})
    _add_edge(db, n["seed"], n["base92"], "BONDED_TO", source_name="bond_0729.csv",
              event_time=T29, props={"eventtime": "2026-07-29 10:26", "log_id": "BL-5"})
    _add_edge(db, n["seed"], n["dtcell"], "TRANSFERRED_TO", source_name="dt_0726.csv",
              event_time=T26, props={"eventtime": "2026-07-26 10:35:13", "dt_eqp": "DT-02"})
    # two FROM_CORE edges, one core - live has 2,687 cells like this
    _add_edge(db, n["seed"], n["core_a"], "FROM_CORE", source_name="bond_0725.csv",
              event_time=T25)
    _add_edge(db, n["seed"], n["core_a"], "FROM_CORE", source_name="dt_0726.csv",
              event_time=T26)

    _add_edge(db, n["sibling"], n["base77"], "BONDED_TO", event_time=T25)
    _add_edge(db, n["sibling"], n["core_a"], "FROM_CORE")
    _add_edge(db, n["noproc"], n["base11"], "BONDED_TO", event_time=T25)
    _add_edge(db, n["noproc"], n["core_c"], "FROM_CORE")
    _add_edge(db, n["ambig"], n["core_a"], "FROM_CORE", source_name="bond_a.csv")
    _add_edge(db, n["ambig"], n["core_b"], "FROM_CORE", source_name="bond_b.csv")
    # the foreign chip bonded to the SAME BaseCell the seed did
    _add_edge(db, n["foreign"], n["base28"], "BONDED_TO", event_time=T25)
    _add_edge(db, n["foreign"], n["core_b"], "FROM_CORE")

    _add_edge(db, n["pe1"], n["core_a"], "PERFORMED_ON", event_time=T20)
    _add_edge(db, n["pe1"], n["knob1"], "USED_KNOB", event_time=T20)
    _add_edge(db, n["pe1"], n["recipe1"], "USED_RECIPE", event_time=T20)
    _add_edge(db, n["pe1"], n["eqp1"], "EXECUTED_BY", event_time=T20)
    # PE-2 has NO knob edge - 866 live ProcessEvents are like this (knobs NULL)
    _add_edge(db, n["pe2"], n["core_a"], "PERFORMED_ON", event_time=T21)
    _add_edge(db, n["pe2"], n["eqp1"], "EXECUTED_BY", event_time=T21)
    # the foreign wafer's event, sharing Eqp E1 - the S->D leak this shape forbids
    _add_edge(db, n["pe9"], n["core_b"], "PERFORMED_ON", event_time=T22)
    _add_edge(db, n["pe9"], n["eqp1"], "EXECUTED_BY", event_time=T22)
    db.commit()
    return n


def _trace(client, identity, **params):
    return client.get("/graph/chip-trace", params={"identity": identity, **params})


def _keys(body):
    return {(x["label"], x["identity_key"]) for x in body["nodes"]}


# ---------------------------------------------------------------------------
# 1) walk A - a chip in the 419: bonding AND dt
# ---------------------------------------------------------------------------

def test_walk_with_dt_answers_every_leg(client, chip_env):
    res = _trace(client, "CORE-A|05|13|5")
    assert res.status_code == 200
    body = res.json()

    assert body["seed"] == {"label": "CoreCell", "identity": "CORE-A|05|13|5",
                            "id": chip_env["seed"].id}
    assert body["scope"]["identity"] == "CORE-A|05"

    bonded = body["walk"]["chip"]["BONDED_TO"]
    assert bonded["status"] == "recorded"
    assert bonded["count"] == 2                    # two events, not one collapsed base
    assert bonded["node_ids"] == [chip_env["base28"].id, chip_env["base92"].id]

    dt = body["walk"]["chip"]["TRANSFERRED_TO"]
    assert dt["status"] == "recorded"
    assert dt["node_ids"] == [chip_env["dtcell"].id]

    wafer = body["walk"]["wafer"]
    assert wafer["status"] == "recorded"
    assert wafer["events"]["count"] == 2
    assert wafer["terminals"]["USED_KNOB"]["node_ids"] == [chip_env["knob1"].id]
    assert wafer["terminals"]["USED_RECIPE"]["node_ids"] == [chip_env["recipe1"].id]
    assert wafer["terminals"]["EXECUTED_BY"]["node_ids"] == [chip_env["eqp1"].id]
    assert body["truncated"] is False


def test_rework_sequence_is_readable(client, chip_env):
    """The three-date fan-out is rework, not a defect. Each hop needs its time."""
    body = _trace(client, "CORE-A|05|13|5").json()
    bonded = [e for e in body["edges"] if e["type"] == "BONDED_TO"]
    assert [e["props"]["eventtime"] for e in bonded] == [
        "2026-07-25 16:10", "2026-07-29 10:26",
    ]
    assert [e["event_time"][:10] for e in bonded] == ["2026-07-25", "2026-07-29"]
    # provenance survives per claim
    assert {e["source_name"] for e in bonded} == {"bond_0725.csv", "bond_0729.csv"}
    dt = next(e for e in body["edges"] if e["type"] == "TRANSFERRED_TO")
    assert dt["props"]["dt_eqp"] == "DT-02"


def test_scope_edge_duplicates_do_not_duplicate_the_wafer(client, chip_env):
    """Two FROM_CORE edges, one Core: 2 claims reported, 1 entity resolved."""
    body = _trace(client, "CORE-A|05|13|5").json()
    scope_leg = body["walk"]["wafer"]["scope_edge"]
    assert scope_leg["count"] == 2
    assert scope_leg["node_ids"] == [chip_env["core_a"].id]
    assert body["scope"]["id"] == chip_env["core_a"].id


# ---------------------------------------------------------------------------
# 2) the shape must refuse to leak - this is the whole point
# ---------------------------------------------------------------------------

def test_sibling_cells_of_the_same_core_are_absent(client, chip_env):
    body = _trace(client, "CORE-A|05|13|5").json()
    assert ("CoreCell", "CORE-A|05|1|1") not in _keys(body)
    assert ("BaseCell", "BASE-77|1|1") not in _keys(body)
    # the seed is the ONLY CoreCell in the answer
    assert [k for k in _keys(body) if k[0] == "CoreCell"] == [
        ("CoreCell", "CORE-A|05|13|5")
    ]


def test_terminals_are_leaves_no_foreign_wafer_through_shared_eqp(client, chip_env):
    """Eqp EQP-01 is shared with CORE-B's PE-9. Reaching it must not open that door.

    This is the forbidden S->D direction. There is no policy engine yet (G2.5), so
    the query shape is what forbids it - and this case is what proves the shape does.
    """
    body = _trace(client, "CORE-A|05|13|5").json()
    keys = _keys(body)
    assert ("Eqp", "EQP-01") in keys              # reached, one hop, as a leaf
    assert ("ProcessEvent", "PE-9") not in keys   # never expanded back out
    assert ("Core", "CORE-B|01") not in keys
    assert ("CoreCell", "CORE-B|01|1|1") not in keys
    assert {e["type"] for e in body["edges"]} == {
        "BONDED_TO", "TRANSFERRED_TO", "FROM_CORE",
        "PERFORMED_ON", "USED_KNOB", "USED_RECIPE", "EXECUTED_BY",
    }
    for e in body["edges"]:                       # no edge leaves the answer
        ids = {n["id"] for n in body["nodes"]}
        assert e["from"] in ids and e["to"] in ids


def test_no_back_expansion_from_a_shared_base_cell(client, chip_env):
    """BASE-28|2|1 is the seed's destination AND the foreign chip's. Only ours shows."""
    body = _trace(client, "CORE-A|05|13|5").json()
    assert ("BaseCell", "BASE-28|2|1") in _keys(body)
    assert ("CoreCell", "CORE-B|01|1|1") not in _keys(body)


# ---------------------------------------------------------------------------
# 3) walk B - bonding only. `none_recorded` is the vocabulary, not an empty hop.
# ---------------------------------------------------------------------------

def test_walk_bonding_only_says_none_recorded_for_dt(client, chip_env):
    body = _trace(client, "CORE-A|05|1|1").json()
    dt = body["walk"]["chip"]["TRANSFERRED_TO"]
    assert dt["status"] == "none_recorded"
    assert dt["node_ids"] == [] and dt["count"] == 0
    assert body["walk"]["chip"]["BONDED_TO"]["status"] == "recorded"
    # the wafer half still answers - the two halves are independent
    assert body["walk"]["wafer"]["status"] == "recorded"
    assert body["walk"]["wafer"]["events"]["count"] == 2


# ---------------------------------------------------------------------------
# 4) walk C - a core with no process rows
# ---------------------------------------------------------------------------

def test_walk_core_without_process_rows(client, chip_env):
    body = _trace(client, "CORE-C|18|2|2").json()
    assert body["scope"]["identity"] == "CORE-C|18"
    assert body["walk"]["chip"]["BONDED_TO"]["status"] == "recorded"
    wafer = body["walk"]["wafer"]
    assert wafer["status"] == "none_recorded"
    assert wafer["events"]["count"] == 0
    # terminals are reached THROUGH the events, so they report the same silence
    for leg in wafer["terminals"].values():
        assert leg["status"] == "none_recorded"
        assert leg["node_ids"] == []
    assert ("Eqp", "EQP-01") not in _keys(body)


# ---------------------------------------------------------------------------
# 5) the scope is resolved, never guessed
# ---------------------------------------------------------------------------

def test_two_cores_claimed_is_refused_not_picked(client, chip_env):
    """A chip has one core. Two claims means we answer the chip half and say so."""
    body = _trace(client, "CORE-A|05|9|9").json()
    assert body["scope"] is None
    wafer = body["walk"]["wafer"]
    assert wafer["status"] == "scope_unresolved"
    assert {c["identity"] for c in wafer["scope_candidates"]} == {"CORE-A|05", "CORE-B|01"}
    assert "events" not in wafer and "terminals" not in wafer
    # and no wafer-side node leaked in on the way
    assert ("ProcessEvent", "PE-1") not in _keys(body)
    # the chip half is still answered
    assert body["walk"]["chip"]["BONDED_TO"]["status"] == "none_recorded"


def test_no_from_core_edge_is_also_scope_unresolved(client, chip_env, db_session):
    _add_node(db_session, "CoreCell", "CORE-Z|99|1|1")
    db_session.commit()
    body = _trace(client, "CORE-Z|99|1|1").json()
    assert body["scope"] is None
    assert body["walk"]["wafer"]["status"] == "scope_unresolved"
    assert body["walk"]["wafer"]["scope_candidates"] == []
    assert body["walk"]["wafer"]["scope_edge"]["status"] == "none_recorded"
    assert body["counts"]["nodes"] == 1 and body["counts"]["edges"] == 0


# ---------------------------------------------------------------------------
# 6) `not_declared` - a config rename must not masquerade as `none_recorded`
# ---------------------------------------------------------------------------

def test_config_rename_reports_not_declared_not_none_recorded(
    client, chip_env, tmp_path, monkeypatch
):
    """Drop TRANSFERRED_TO from the mapping while the dt edge still EXISTS in the
    store. A `none_recorded` here would be a lie: the chip has a dt event."""
    trimmed = json.loads(json.dumps(CT_MAPPING))
    trimmed["ct_test_dt"]["edges"] = [
        e for e in trimmed["ct_test_dt"]["edges"] if e["type"] != "TRANSFERRED_TO"
    ]
    renamed_dir = tmp_path / "renamed"
    renamed_dir.mkdir()
    _write_mapping(renamed_dir, monkeypatch, trimmed)

    body = _trace(client, "CORE-A|05|13|5").json()
    dt = body["walk"]["chip"]["TRANSFERRED_TO"]
    assert dt["status"] == "not_declared"
    assert dt["node_ids"] == []
    assert ("DtCell", "TAPE-A|01|5|8") not in _keys(body)
    # the still-declared legs are unaffected
    assert body["walk"]["chip"]["BONDED_TO"]["status"] == "recorded"


# ---------------------------------------------------------------------------
# 7) contract edges
# ---------------------------------------------------------------------------

def test_missing_chip_is_404(client, chip_env):
    assert _trace(client, "NO-SUCH|00|0|0").status_code == 404


def test_identity_is_required(client, chip_env):
    assert client.get("/graph/chip-trace").status_code == 422
    # the known trap: node_id is not the parameter (ontology-pm memory)
    assert client.get("/graph/chip-trace",
                      params={"node_id": chip_env["seed"].id}).status_code == 422


def test_there_is_no_depth_parameter(client, chip_env):
    """Exposing depth invites the flood back. A depth query param must do nothing."""
    plain = _trace(client, "CORE-A|05|13|5").json()
    with_depth = _trace(client, "CORE-A|05|13|5", depth=3).json()
    assert plain["counts"] == with_depth["counts"]
    assert _keys(plain) == _keys(with_depth)


def test_event_cap_truncates_loudly(client, chip_env, monkeypatch):
    monkeypatch.setattr(main, "GRAPH_CHIP_TRACE_EVENT_CAP", 1)
    body = _trace(client, "CORE-A|05|13|5").json()
    assert body["walk"]["wafer"]["events"]["truncated"] is True
    assert body["walk"]["wafer"]["events"]["count"] == 1
    assert body["walk"]["wafer"]["events"]["capped_at"] == 1
    assert body["truncated"] is True


def test_terminal_cap_is_sized_off_the_event_count_not_the_chip_leg_cap(
    client, chip_env, monkeypatch
):
    """A terminal leg's claim count scales with the EVENT count, not with the number
    of terminal entities. Live: 206 EXECUTED_BY claims resolving to 8 Eqp. Sharing
    the chip-leg cap of 200 truncated that 8-entity answer on the first live run.

    [2026-07-30] The lever changed. This used to shrink TARGET_CAP to 1, which is no
    longer usable: the seed carries 2 FROM_CORE claims, so a cap of 1 now truncates
    the SCOPE leg and the wafer half is (correctly) not computed at all - see
    test_a_truncated_scope_leg_refuses_to_resolve. The claim under test is that the
    two caps are separate values and that the terminal leg is bounded by its own, so
    it is asserted on the terminal cap directly.
    """
    assert main.GRAPH_CHIP_TRACE_TERMINAL_CAP >= main.GRAPH_CHIP_TRACE_EVENT_CAP
    body = _trace(client, "CORE-A|05|13|5").json()
    # both PE-1 and PE-2 claim EQP-01: 2 claims, 1 entity
    eqp = body["walk"]["wafer"]["terminals"]["EXECUTED_BY"]
    assert eqp["count"] == 2 and eqp["node_ids"] == [chip_env["eqp1"].id]
    assert eqp["truncated"] is False
    assert eqp["capped_at"] == main.GRAPH_CHIP_TRACE_TERMINAL_CAP
    assert body["walk"]["chip"]["BONDED_TO"]["capped_at"] == main.GRAPH_CHIP_TRACE_TARGET_CAP

    # ... and the terminal leg really is bounded by the terminal cap
    monkeypatch.setattr(main, "GRAPH_CHIP_TRACE_TERMINAL_CAP", 1)
    eqp = _trace(client, "CORE-A|05|13|5").json()["walk"]["wafer"]["terminals"]["EXECUTED_BY"]
    assert eqp["count"] == 1 and eqp["truncated"] is True and eqp["capped_at"] == 1


def test_target_cap_truncates_loudly(client, chip_env, monkeypatch):
    monkeypatch.setattr(main, "GRAPH_CHIP_TRACE_TARGET_CAP", 1)
    body = _trace(client, "CORE-A|05|13|5").json()
    bonded = body["walk"]["chip"]["BONDED_TO"]
    assert bonded["truncated"] is True and bonded["count"] == 1
    assert body["truncated"] is True


def test_exactly_at_the_cap_is_not_reported_as_truncated(client, chip_env, monkeypatch):
    monkeypatch.setattr(main, "GRAPH_CHIP_TRACE_TARGET_CAP", 2)
    bonded = _trace(client, "CORE-A|05|13|5").json()["walk"]["chip"]["BONDED_TO"]
    assert bonded["count"] == 2 and bonded["truncated"] is False


def test_node_and_edge_shape_matches_the_other_graph_endpoints(client, chip_env):
    body = _trace(client, "CORE-A|05|13|5").json()
    for n in body["nodes"]:
        assert set(n) == {"id", "label", "identity_key", "props"}
    for e in body["edges"]:
        # same keys as /graph/neighbors and /graph/trace, plus props
        assert set(e) == {"from", "to", "type", "source_name", "updated_by",
                          "event_time", "props"}
    assert body["counts"]["nodes"] == len(body["nodes"])
    assert body["counts"]["edges"] == len(body["edges"])


# ---------------------------------------------------------------------------
# 8) ruling 6-b - `spatial` on an EDGE prop is refused at load, with a reason
# ---------------------------------------------------------------------------

_SPATIAL_ON_EDGE = {
    "ct_test_bonding": {
        "description": "edge spatial refusal case",
        "node": {"label": "CoreCell", "identity": ["core_lot", "core_slot"]},
        "edges": [
            {"type": "BONDED_TO", "target_label": "BaseCell",
             "target_identity_from": ["base_id"],
             "props": [{"col": "bx", "spatial": {"coord_system": "base_grid", "axis": "x"}}],
             "description": "base cell"},
        ],
    },
}


def test_spatial_on_an_edge_prop_is_rejected_with_a_named_reason(caplog):
    with caplog.at_level("WARNING"):
        mappings = ontology_config.validate_ontology_mapping(
            _SPATIAL_ON_EDGE, known_tables=None
        )
    assert "ct_test_bonding" not in mappings          # the table is skipped, not half-loaded
    text = caplog.text
    assert "edges[0]: props[0].spatial" in text
    assert "not supported on an EDGE property" in text
    assert "unsupported combination" in text


def test_spatial_on_a_node_prop_still_works():
    ok = json.loads(json.dumps(_SPATIAL_ON_EDGE))
    ok["ct_test_bonding"]["edges"][0]["props"] = ["bx"]
    ok["ct_test_bonding"]["node"]["props"] = [
        {"col": "cx", "spatial": {"coord_system": "wafer_grid", "axis": "x"}}
    ]
    mappings = ontology_config.validate_ontology_mapping(ok, known_tables=None)
    assert mappings["ct_test_bonding"]["node"]["props"] == [
        {"col": "cx", "spatial": {"coord_system": "wafer_grid", "axis": "x"}}
    ]
    assert mappings["ct_test_bonding"]["edges"][0]["props"] == [
        {"col": "bx", "spatial": None}
    ]


def test_plain_edge_props_are_untouched_by_the_refusal():
    ok = json.loads(json.dumps(_SPATIAL_ON_EDGE))
    ok["ct_test_bonding"]["edges"][0]["props"] = [{"col": "bx"}, "by"]
    mappings = ontology_config.validate_ontology_mapping(ok, known_tables=None)
    assert mappings["ct_test_bonding"]["edges"][0]["props"] == [
        {"col": "bx", "spatial": None}, {"col": "by", "spatial": None}
    ]


# ---------------------------------------------------------------------------
# 8) [QA 2026-07-30] "we could not read the declaration" is not "it moved"
# ---------------------------------------------------------------------------

def test_unreadable_mapping_says_mapping_unavailable_not_not_declared(
    client, chip_env, tmp_path, monkeypatch, caplog
):
    """The measured failure: a request landing in the config write window.

    `json.load` raises -> `raw_config = {}` -> the declared-pair set collapses to
    the enrichment-promoted pairs, and the endpoint asserted `not_declared` for a
    chip whose BONDED_TO edges are in `graph_edges` right now.

    Defect injection: revert `_chip_trace_leg`'s degraded branch and every leg here
    reads `not_declared` again.
    """
    broken = tmp_path / "mid_save.json"
    broken.write_text('{"ct_test_bonding": {"desc', encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(broken))

    with caplog.at_level("WARNING"):
        body = _trace(client, "CORE-A|05|13|5").json()

    assert body["declaration"]["status"] == "degraded"
    assert body["declaration"]["exists"] is True
    assert [r["scope"] for r in body["declaration"]["rejected"]] == ["file"]
    for leg_type in ("BONDED_TO", "TRANSFERRED_TO"):
        assert body["walk"]["chip"][leg_type]["status"] == "mapping_unavailable", leg_type
    assert body["walk"]["wafer"]["scope_edge"]["status"] == "mapping_unavailable"
    assert "did not load cleanly" in caplog.text


def test_absent_mapping_file_is_degraded_and_logged(
    client, chip_env, tmp_path, monkeypatch, caplog
):
    """The branch QA found silent: `os.path.exists() is False` logged nothing."""
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(tmp_path / "gone.json"))

    with caplog.at_level("WARNING"):
        body = _trace(client, "CORE-A|05|13|5").json()

    assert body["declaration"] == {
        "status": "degraded",
        "path": str(tmp_path / "gone.json"),
        "exists": False,
        "rejected": [],
    }
    assert body["walk"]["chip"]["BONDED_TO"]["status"] == "mapping_unavailable"
    assert "file absent at" in caplog.text


def test_a_rejected_table_degrades_only_the_negative_statuses(
    client, chip_env, tmp_path, monkeypatch
):
    """A renamed column drops that table's whole mapping - the same conflation one
    notch down. `recorded` is a conclusion from rows we read and must NOT degrade."""
    broken = json.loads(json.dumps(CT_MAPPING))
    broken["ct_test_dt"]["node"]["identity"] = ["core_lot", "core_slot", "cx", "cy_renamed"]
    d = tmp_path / "rejected_table"
    d.mkdir()
    _write_mapping(d, monkeypatch, broken)

    body = _trace(client, "CORE-A|05|13|5").json()
    assert body["declaration"]["status"] == "degraded"
    assert [r["table"] for r in body["declaration"]["rejected"]] == ["ct_test_dt"]
    # TRANSFERRED_TO came from the rejected table -> unknown, not absent
    assert body["walk"]["chip"]["TRANSFERRED_TO"]["status"] == "mapping_unavailable"
    # ... while a leg whose rows we actually read still reports the evidence
    assert body["walk"]["chip"]["BONDED_TO"]["status"] == "recorded"
    assert body["walk"]["chip"]["BONDED_TO"]["count"] == 2


def test_a_clean_declaration_still_reports_not_declared(client, chip_env, tmp_path, monkeypatch):
    """The distinction is only worth anything if the clean case keeps saying
    `not_declared` — otherwise the new status just swallows the old one."""
    trimmed = json.loads(json.dumps(CT_MAPPING))
    trimmed["ct_test_dt"]["edges"] = [
        e for e in trimmed["ct_test_dt"]["edges"] if e["type"] != "TRANSFERRED_TO"
    ]
    d = tmp_path / "clean_trim"
    d.mkdir()
    _write_mapping(d, monkeypatch, trimmed)

    body = _trace(client, "CORE-A|05|13|5").json()
    assert body["declaration"]["status"] == "ok"
    assert body["walk"]["chip"]["TRANSFERRED_TO"]["status"] == "not_declared"


# ---------------------------------------------------------------------------
# 9) [QA 2026-07-30] terminals must not assert "no knobs" behind a dead anchor
# ---------------------------------------------------------------------------

def test_renaming_performed_on_makes_terminals_not_reached(
    client, chip_env, tmp_path, monkeypatch
):
    """`events` correctly says not_declared, but the terminals used to report
    `USED_KNOB: none_recorded, count 0` - "this wafer used no knobs" when no knob
    query ran. The wafer HAS knob edges; they were simply never asked for.

    Defect injection: drop the `anchor_leg` argument at the terminal call site and
    every terminal reads `none_recorded` again.
    """
    renamed = json.loads(json.dumps(CT_MAPPING))
    for e in renamed["ct_test_process"]["edges"]:
        if e["type"] == "PERFORMED_ON":
            e["type"] = "PERFORMED_UPON"
    d = tmp_path / "renamed_performed_on"
    d.mkdir()
    _write_mapping(d, monkeypatch, renamed)

    body = _trace(client, "CORE-A|05|13|5").json()
    wafer = body["walk"]["wafer"]
    assert wafer["events"]["status"] == "not_declared"
    for t in ("USED_KNOB", "USED_RECIPE", "EXECUTED_BY"):
        leg = wafer["terminals"][t]
        assert leg["status"] == "not_reached", t
        assert leg["count"] == 0
        assert leg["blocked_by"] == {"edge_type": "PERFORMED_ON", "status": "not_declared"}


def test_a_wafer_with_no_events_still_says_none_recorded_on_terminals(client, chip_env):
    """The sound inference stays: zero events genuinely implies zero knobs REACHED
    THROUGH events. Only an undeclared/unreadable anchor is `not_reached`."""
    body = _trace(client, "CORE-C|18|2|2").json()
    wafer = body["walk"]["wafer"]
    assert wafer["events"]["status"] == "none_recorded"
    for t in ("USED_KNOB", "USED_RECIPE", "EXECUTED_BY"):
        assert wafer["terminals"][t]["status"] == "none_recorded", t
        assert "blocked_by" not in wafer["terminals"][t]


# ---------------------------------------------------------------------------
# 10) [QA 2026-07-30] a truncated scope leg must not resolve a wafer
# ---------------------------------------------------------------------------

def test_a_truncated_scope_leg_refuses_to_resolve(client, chip_env, monkeypatch):
    """201 claims to one core fill the cap+1 buffer before a claim to a second core
    is read: length 1, scope 'resolved', wafer half computed for the WRONG core.

    Driven by shrinking the cap to 1 rather than by seeding 201 edges - the seed
    already carries 2 FROM_CORE claims to ONE core, so with cap=1 the leg fetches
    cap+1=2, truncates to 1, and yields exactly one node_id. Before the fix that
    resolved the scope off a truncated set.

    Defect injection: remove `and not scope_leg["truncated"]` and this fails with
    scope resolved to CORE-A|05.
    """
    monkeypatch.setattr(main, "GRAPH_CHIP_TRACE_TARGET_CAP", 1)

    body = _trace(client, "CORE-A|05|13|5").json()
    assert body["walk"]["wafer"]["scope_edge"]["truncated"] is True
    assert len(body["walk"]["wafer"]["scope_edge"]["node_ids"]) == 1
    assert body["walk"]["wafer"]["status"] == "scope_unresolved"
    assert body["scope"] is None
    assert body["truncated"] is True


def test_the_event_cap_must_fit_in_one_id_chunk():
    """Two constants that read as independent are load-bearing on each other: the
    leg applies limit() per anchor chunk, so the documented truncation order only
    holds while an anchor set fits in one chunk."""
    assert main.GRAPH_CHIP_TRACE_EVENT_CAP <= main.GRAPH_CHIP_TRACE_ID_CHUNK
