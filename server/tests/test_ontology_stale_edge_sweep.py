"""[Ontology O2] Re-derivation has to be a CORRECTION, not an ACCUMULATION.

Board O2: ``graph_materializer.materialize_events`` counts DELETE events into
``skipped_deletes`` and does nothing else, so stale edges survive re-derivation.
The purpose-scoped ontology strategy (``docs/process/DESIGN_TRACKS.md``,
"목적별 작은 온톨로지") depends on the opposite being true, and retiring an ``exp:``
ontology has no mechanism at all while it is not.

Two populations survive re-derivation TODAY, and the first half of each test here
ASSERTS that survival before the sweep runs. Those assertions are the red, and
they are meant to stay green forever: re-derivation walking rows that exist can
never reach a row that does not, and it returns an empty stat block for a table
the declaration no longer maps. The sweep is the mechanism that reaches both.

The tests that matter more are the survival ones (section 3). A sweep test that
passes an over-broad implementation is worthless, so each of those names the
defect injection that turns it red.

[격리] 테이블/라벨/타입 이름은 사용자 실 config에 실존 불가능한 staleedge_test_/Stale
접두를 쓴다 (conftest가 import 시점에 실 config를 선점하는 공유 sqlite 함정 - 교훈 파일).
"""
import json
import logging
import uuid

import pytest
from sqlalchemy.orm import sessionmaker

import enrichment_config
import graph_materializer
import graph_stale_edges
import ontology_config
from database import crud, models
from database.models import DatabaseOutbox, GraphEdge, GraphNode

BONDING = "staleedge_test_bonding"
RESOLVE = "staleedge_test_resolve"

STALE_TABLES = {
    BONDING: {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string",
            "core_lot": "string",
            "core_slot": "string",
        },
    },
    RESOLVE: {
        "business_key": "raw_name",
        "column_types": {
            "raw_name": "string",
            "eqp_id": "string",
        },
    },
}

MAPPING = {
    BONDING: {
        "description": "본딩 로그 - stale 엣지 스윕 검증용 픽스처",
        "node": {"label": "StaleCell", "identity": "log_id", "node_class": "dynamic"},
        "edges": [
            {
                "type": "STALE_FROM_CORE",
                "target_label": "StaleCore",
                "target_identity_from": ["core_lot", "core_slot"],
                "description": "이 셀이 속한 코어",
            },
        ],
    },
    RESOLVE: {
        "description": "표기 해석 결과 - 사람 교정 provenance 픽스처",
        "node": {"label": "StaleResolution", "identity": "raw_name"},
        "edges": [
            {
                "type": "STALE_RESOLVED_AS",
                "target_label": "StaleEqp",
                "target_identity_from": ["eqp_id"],
                "description": "사람이 확정한 해석 대상",
                # The enrichment promotion stamps exactly this
                # (`ontology_config.synthesize_enrichment_mappings`) because the
                # edge IS a person's judgement.
                "source_override": "user",
            },
        ],
    },
}


@pytest.fixture()
def onto_files(tmp_path, monkeypatch):
    """매핑/enrichment 선언 파일을 격리 경로로 갈아끼운다.

    enrichment 경로까지 반드시 갈아끼운다 - 안 하면 로더가 **사용자의 실 규칙 파일**을
    읽어 테스트가 그 파일 상태에 따라 흔들린다.
    """
    mapping_path = tmp_path / "ontology_mapping.json"
    mapping_path.write_text(json.dumps(MAPPING), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(mapping_path))

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))

    def rewrite(mapping_obj):
        mapping_path.write_text(json.dumps(mapping_obj), encoding="utf-8")

    return rewrite


@pytest.fixture()
def stale_env(db_session, onto_files, monkeypatch):
    models.init_dynamic_models(STALE_TABLES)
    crud.TABLE_CONFIG.update(STALE_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    # run_sweep opens its own session - point it at the test DB.
    import database.database as dbmod
    bind = db_session.get_bind()
    monkeypatch.setattr(dbmod, "SessionLocal", sessionmaker(bind=bind))
    monkeypatch.setattr(dbmod, "engine", bind)
    return db_session


# ----------------- helpers -----------------

def _mappings():
    return ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)


def _bonding_row(db, log_id, core_lot="LOT-A", core_slot="05"):
    model = models.DYNAMIC_TABLES[BONDING]
    r = model(row_id=f"row_{log_id}", business_key_val=log_id, log_id=log_id,
              core_lot=core_lot, core_slot=core_slot)
    db.add(r)
    db.flush()
    return r


def _resolve_row(db, raw_name, eqp_id="EQP-1"):
    model = models.DYNAMIC_TABLES[RESOLVE]
    r = model(row_id=f"row_{raw_name}", business_key_val=raw_name,
              raw_name=raw_name, eqp_id=eqp_id)
    db.add(r)
    db.flush()
    return r


def _drop_row(db, table, row_id):
    model = models.DYNAMIC_TABLES[table]
    db.query(model).filter(model.row_id == row_id).delete(synchronize_session=False)
    db.commit()


def _derive(db, table, mappings=None):
    return graph_materializer.resync_table(db, table, mappings or _mappings())


def _edges(db, edge_type=None):
    q = db.query(GraphEdge)
    if edge_type:
        q = q.filter(GraphEdge.type == edge_type)
    return q.order_by(GraphEdge.id.asc()).all()


def _edge_identities(db):
    """Edges as ``(type, from identity, to identity)`` triples.

    Compared by IDENTITY, never by count: this repository has already shipped a
    graph defect where the count was right and the nodes were wrong (교훈 파일).
    """
    nodes = {n.id: (n.label, n.identity_key) for n in db.query(GraphNode).all()}
    return sorted(
        (e.type, nodes.get(e.from_node), nodes.get(e.to_node))
        for e in db.query(GraphEdge).all()
    )


def _delete_event(db, table, row_id):
    ev = DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), event_type="DELETE", table_name=table,
        payload={"row_id": row_id, "timestamp": "2026-08-04T00:00:00"},
        status="PENDING",
    )
    db.add(ev)
    db.flush()
    return ev


# ---------------------------------------------------------------------------
# 1) RED: the two populations re-derivation cannot reach
# ---------------------------------------------------------------------------

def test_a_deleted_row_leaves_its_edge_and_the_sweep_removes_it(stale_env):
    """Population (A) - the DELETE hole named on the board.

    The materializer counts the DELETE and moves on; ``resync_table`` walks rows
    that EXIST, so the deleted row's edge is never in a ``processed_refs`` scope
    again and ``_retarget_stale_edges`` never sees it.
    """
    db = stale_env
    _bonding_row(db, "LOG1")
    db.commit()
    _derive(db, BONDING)
    assert _edge_identities(db) == [
        ("STALE_FROM_CORE", ("StaleCell", "LOG1"), ("StaleCore", "LOT-A|05"))
    ]

    ev = _delete_event(db, BONDING, "row_LOG1")
    _drop_row(db, BONDING, "row_LOG1")

    stats = graph_materializer.materialize_events(db, [ev], _mappings())
    assert stats["skipped_deletes"] == 1, "the defect this item is about"

    # RED: re-derive everything the declaration still knows about.
    assert _derive(db, BONDING)["rows"] == 0
    assert _edge_identities(db) == [
        ("STALE_FROM_CORE", ("StaleCell", "LOG1"), ("StaleCore", "LOT-A|05"))
    ], "re-derivation cannot reach a row that no longer exists"

    # GREEN: the sweep can, because it asks the RDB instead of an event.
    plan = graph_stale_edges.plan_sweep(db, _mappings())
    assert [(v, r) for _, v, r in plan["sweepable"]["STALE_FROM_CORE"]] == [
        (graph_stale_edges.VERDICT_ROW_GONE, f"{BONDING}:row_LOG1")
    ]
    assert graph_stale_edges.apply_sweep(db, plan) == 1
    assert _edge_identities(db) == []


def test_retiring_a_table_mapping_leaves_its_edges_and_the_sweep_removes_them(
        stale_env, onto_files):
    """Population (B) - ``exp:`` retirement, which today has no mechanism at all.

    Deleting a purpose's declaration removes the producer and leaves every edge it
    ever produced: ``resync_table`` returns an empty stat block for a table the
    mapping no longer covers.
    """
    db = stale_env
    _bonding_row(db, "LOG1")
    db.commit()
    _derive(db, BONDING)
    assert len(_edges(db, "STALE_FROM_CORE")) == 1

    retired = {k: v for k, v in MAPPING.items() if k != BONDING}
    onto_files(retired)
    mappings = _mappings()
    assert BONDING not in mappings

    # RED: resync of a retired table is a no-op, in both directions.
    assert _derive(db, BONDING, mappings) == {"rows": 0, "nodes": 0, "edges": 0,
                                              "chunks": 0}
    assert _edge_identities(db) == [
        ("STALE_FROM_CORE", ("StaleCell", "LOG1"), ("StaleCore", "LOT-A|05"))
    ], "a retired purpose ontology keeps its corpses"

    # GREEN
    plan = graph_stale_edges.plan_sweep(db, mappings)
    assert [(v, r) for _, v, r in plan["sweepable"]["STALE_FROM_CORE"]] == [
        (graph_stale_edges.VERDICT_NOT_DECLARED, f"{BONDING}:row_LOG1")
    ]
    assert graph_stale_edges.apply_sweep(db, plan) == 1
    assert _edge_identities(db) == []


# ---------------------------------------------------------------------------
# 2) scope - the sweep owns only what a derivation minted
# ---------------------------------------------------------------------------

def test_only_the_deleted_rows_edge_goes(stale_env):
    """Defect injection: sweeping by table instead of by row existence
    (``classify_refs`` returning ``row_gone`` for every ref of a table with any
    missing row) deletes LOG2's edge as well and this test goes red."""
    db = stale_env
    _bonding_row(db, "LOG1", core_lot="LOT-A", core_slot="05")
    _bonding_row(db, "LOG2", core_lot="LOT-B", core_slot="07")
    db.commit()
    _derive(db, BONDING)
    assert len(_edge_identities(db)) == 2

    _drop_row(db, BONDING, "row_LOG1")

    plan = graph_stale_edges.plan_sweep(db, _mappings())
    graph_stale_edges.apply_sweep(db, plan)
    assert _edge_identities(db) == [
        ("STALE_FROM_CORE", ("StaleCell", "LOG2"), ("StaleCore", "LOT-B|07"))
    ], "the surviving row's edge was collateral damage"


def test_a_live_rows_edge_is_never_touched(stale_env):
    db = stale_env
    _bonding_row(db, "LOG1")
    db.commit()
    _derive(db, BONDING)

    plan = graph_stale_edges.plan_sweep(db, _mappings())
    assert plan["delete_ids"] == []
    assert plan["per_type"] == {}


def test_apply_deletes_exactly_what_the_dry_run_listed(stale_env):
    """The dry run is the contract. ``apply_sweep`` re-derives nothing of its own.

    Defect injection: making ``apply_sweep`` delete by ``type`` (rather than by the
    ids the plan listed) takes LOG2's live edge with it and this goes red.
    """
    db = stale_env
    _bonding_row(db, "LOG1")
    _bonding_row(db, "LOG2")
    db.commit()
    _derive(db, BONDING)
    _drop_row(db, BONDING, "row_LOG1")

    plan = graph_stale_edges.plan_sweep(db, _mappings())
    planned = set(plan["delete_ids"])
    before = {e.id for e in _edges(db)}

    assert graph_stale_edges.apply_sweep(db, plan) == len(planned)
    assert {e.id for e in _edges(db)} == before - planned


# ---------------------------------------------------------------------------
# 3) SURVIVAL - the tests that matter more than the deletion ones
# ---------------------------------------------------------------------------

def test_a_human_confirmed_edge_survives_even_when_its_row_is_gone(stale_env):
    """The system's whole value proposition is that one human judgement propagates.

    Defect injection: delete the ``is_human_confirmed`` branch from
    ``plan_sweep`` (or make it return False) and this test goes red - the edge
    lands in ``delete_ids`` and ``apply_sweep`` removes it.
    """
    db = stale_env
    _resolve_row(db, "eqpA", eqp_id="EQP-1")
    db.commit()
    _derive(db, RESOLVE)
    minted = _edges(db, "STALE_RESOLVED_AS")
    assert [e.source_name for e in minted] == ["user"]

    _drop_row(db, RESOLVE, "row_eqpA")

    plan = graph_stale_edges.plan_sweep(db, _mappings(), max_fraction=1.0,
                                        min_population=1)
    assert plan["delete_ids"] == [], "a person's judgement was queued for deletion"
    assert plan["protected"]["edges"] == 1
    assert plan["protected"]["by_type"] == {"STALE_RESOLVED_AS": 1}
    assert plan["protected"]["samples"][0]["verdict"] == \
        graph_stale_edges.VERDICT_ROW_GONE

    graph_stale_edges.apply_sweep(db, plan)
    assert _edge_identities(db) == [
        ("STALE_RESOLVED_AS", ("StaleResolution", "eqpA"), ("StaleEqp", "EQP-1"))
    ], "the human-confirmed edge did not survive the sweep"


def test_a_human_confirmed_edge_survives_a_retired_mapping_too(stale_env, onto_files):
    """Same protection on the other stale population. Retiring a purpose must not
    quietly discard the judgements a person made inside it."""
    db = stale_env
    _resolve_row(db, "eqpA", eqp_id="EQP-1")
    db.commit()
    _derive(db, RESOLVE)

    onto_files({k: v for k, v in MAPPING.items() if k != RESOLVE})
    mappings = _mappings()

    plan = graph_stale_edges.plan_sweep(db, mappings, max_fraction=1.0,
                                        min_population=1)
    assert plan["delete_ids"] == []
    assert plan["protected"]["samples"][0]["verdict"] == \
        graph_stale_edges.VERDICT_NOT_DECLARED
    graph_stale_edges.apply_sweep(db, plan)
    assert len(_edges(db, "STALE_RESOLVED_AS")) == 1


def test_an_edge_without_an_owner_is_not_reached_and_survives(stale_env):
    """"I do not know who minted this" is not "nobody minted this".

    Defect injection: treating an unparseable ref as sweepable (adding
    ``VERDICT_NOT_REACHED`` to ``SWEEPABLE_VERDICTS``) turns this red.
    """
    db = stale_env
    a = GraphNode(label="StaleCell", identity_key="HAND1", props={})
    b = GraphNode(label="StaleCore", identity_key="HAND2", props={})
    db.add_all([a, b])
    db.flush()
    unownable = (None, "", "no_colon_at_all", f"{BONDING}:None", f"{BONDING}:  ")
    for i, ref in enumerate(unownable):
        # source_name varies only to satisfy the (from,type,to,source_name) unique
        # index; none of these is `user`, so the protection below is not the thing
        # keeping them alive.
        db.add(GraphEdge(type="STALE_HAND", from_node=a.id, to_node=b.id,
                         source_name=f"pipeline_parser_{i}", source_row_ref=ref))
    db.commit()

    plan = graph_stale_edges.plan_sweep(db, _mappings(), max_fraction=1.0,
                                        min_population=1)
    assert plan["delete_ids"] == []
    assert plan["not_reached"]["edges"] == 5
    assert plan["not_reached"]["refs"] == 5
    graph_stale_edges.apply_sweep(db, plan)
    assert len(_edges(db, "STALE_HAND")) == 5, \
        "edges whose owner could not be established were swept anyway"


def test_an_edge_owned_by_an_unknown_table_is_not_reached_and_survives(stale_env):
    """"not registered in this process" is indistinguishable from "retired", and
    reading the first as the second is exactly the ``mapping_unavailable`` ->
    ``not_declared`` confusion the vocabulary exists to prevent."""
    db = stale_env
    a = GraphNode(label="StaleCell", identity_key="X1", props={})
    b = GraphNode(label="StaleCore", identity_key="X2", props={})
    db.add_all([a, b])
    db.flush()
    db.add(GraphEdge(type="STALE_FOREIGN", from_node=a.id, to_node=b.id,
                     source_name="pipeline_parser",
                     source_row_ref="some_other_purpose_table:row_9"))
    db.commit()

    plan = graph_stale_edges.plan_sweep(db, _mappings(), max_fraction=1.0,
                                        min_population=1)
    assert plan["delete_ids"] == []
    assert plan["not_reached"]["edges"] == 1
    assert plan["not_reached"]["samples"][0]["ref"] == "some_other_purpose_table:row_9"


def test_a_rejected_mapping_refuses_the_whole_sweep(stale_env, onto_files, caplog):
    """The compound failure. A renamed column silently drops a table's mapping
    (the loader's documented contract), that table then looks *unmapped*, and this
    sweep reads unmapped as "delete every edge that table produced".

    Defect injection: remove the ``declaration_blockers`` gate from ``run_sweep``
    and the STALE_FROM_CORE edge is deleted, failing the count below.
    """
    db = stale_env
    _bonding_row(db, "LOG1")
    db.commit()
    _derive(db, BONDING)
    assert len(_edges(db, "STALE_FROM_CORE")) == 1

    broken = json.loads(json.dumps(MAPPING))
    broken[BONDING]["node"]["identity"] = "log_id_renamed"
    onto_files(broken)

    with caplog.at_level(logging.ERROR):
        out = graph_stale_edges.run_sweep(known_tables=crud.TABLE_CONFIG,
                                          apply_deletions=True)

    assert out["status"] == "refused"
    assert out["applied"] is None
    assert any("log_id_renamed" in b for b in out["blockers"]), out["blockers"]
    assert len(_edges(db, "STALE_FROM_CORE")) == 1, \
        "a rejected mapping was read as a retired one and the edges were swept"
    assert "REFUSED" in caplog.text
    assert graph_stale_edges.REASON_MAPPING_UNAVAILABLE in caplog.text


def test_the_budget_guard_declines_a_type_it_would_empty(stale_env):
    """A mapping typo looks exactly like a retired purpose. Same guard, same
    reasoning, and the same per-type (not all-or-nothing) shape as the node sweep."""
    db = stale_env
    for i in range(20):
        _bonding_row(db, f"LOG{i}", core_slot=f"{i:02d}")
    db.commit()
    _derive(db, BONDING)
    for i in range(20):
        _drop_row(db, BONDING, f"row_LOG{i}")

    plan = graph_stale_edges.plan_sweep(db, _mappings())
    assert "STALE_FROM_CORE" in plan["declined"]
    assert plan["declined"]["STALE_FROM_CORE"]["fraction"] == 1.0
    assert plan["delete_ids"] == [], "a declined type must contribute nothing"
    assert graph_stale_edges.apply_sweep(db, plan) == 0
    assert len(_edges(db, "STALE_FROM_CORE")) == 20

    relaxed = graph_stale_edges.plan_sweep(db, _mappings(), max_fraction=1.0)
    assert len(relaxed["delete_ids"]) == 20


def test_a_small_type_is_exempt_from_the_fraction_test(stale_env):
    db = stale_env
    _bonding_row(db, "LOG1")
    db.commit()
    _derive(db, BONDING)
    _drop_row(db, BONDING, "row_LOG1")

    assert len(graph_stale_edges.plan_sweep(db, _mappings())["delete_ids"]) == 1
    strict = graph_stale_edges.plan_sweep(db, _mappings(), min_population=1)
    assert "STALE_FROM_CORE" in strict["declined"], \
        "min_population must be the only exemption"


# ---------------------------------------------------------------------------
# 4) honest vocabulary - the words are the contract
# ---------------------------------------------------------------------------

def test_the_verdict_words_come_from_the_existing_vocabulary():
    import config_resolve_report
    assert graph_stale_edges.VERDICT_NOT_DECLARED == \
        config_resolve_report.REASON_NOT_DECLARED
    assert graph_stale_edges.VERDICT_NOT_REACHED == \
        config_resolve_report.REASON_NOT_REACHED
    assert graph_stale_edges.REASON_MAPPING_UNAVAILABLE == \
        config_resolve_report.REASON_MAPPING_UNAVAILABLE
    assert graph_stale_edges.VERDICT_NOT_REACHED not in \
        graph_stale_edges.SWEEPABLE_VERDICTS


def test_an_uncapped_scan_reports_exact_and_a_capped_one_reports_sample(stale_env):
    """``count_kind`` is not decoration: a capped scan describes the rows it looked
    at and nothing about the rest, and the number must say so."""
    db = stale_env
    for i in range(5):
        _bonding_row(db, f"LOG{i}", core_slot=f"{i:02d}")
    db.commit()
    _derive(db, BONDING)
    for i in range(5):
        _drop_row(db, BONDING, f"row_LOG{i}")

    full = graph_stale_edges.plan_sweep(db, _mappings(), max_fraction=1.0)
    assert full["count_kind"] == "exact"
    assert full["truncated"] is False
    assert full["scanned"] == 5

    capped = graph_stale_edges.plan_sweep(db, _mappings(), max_fraction=1.0,
                                          scan_limit=2)
    assert capped["count_kind"] == "sample"
    assert capped["truncated"] is True
    assert capped["scanned"] == 2
    assert capped["per_type"] == {"STALE_FROM_CORE": 2}
    # A truncated scan deletes nothing: the guard's numerator would come from the
    # sample and its denominator from the whole population, so the fraction is a
    # lower bound and the guard could only ever FAIL to decline.
    assert capped["delete_ids"] == []
    assert capped["declined"]["STALE_FROM_CORE"]["truncated"] is True
    assert "scan_limit 2" in capped["declined"]["STALE_FROM_CORE"]["reason"]
    assert graph_stale_edges.apply_sweep(db, capped) == 0
    assert len(_edges(db, "STALE_FROM_CORE")) == 5


def test_the_summary_names_everything_it_did_not_delete(stale_env):
    """A sweep that reports only its deletions makes "everything was refused" read
    exactly like "there was nothing to do"."""
    db = stale_env
    for i in range(20):
        _bonding_row(db, f"LOG{i}", core_slot=f"{i:02d}")
    _resolve_row(db, "eqpA")
    db.commit()
    _derive(db, BONDING)
    _derive(db, RESOLVE)
    for i in range(20):
        _drop_row(db, BONDING, f"row_LOG{i}")
    _drop_row(db, RESOLVE, "row_eqpA")

    a = db.query(GraphNode).filter(GraphNode.label == "StaleCell").first()
    db.add(GraphEdge(type="STALE_HAND", from_node=a.id, to_node=a.id,
                     source_name="pipeline_parser", source_row_ref=None))
    db.commit()

    line = graph_stale_edges.format_plan_summary(
        graph_stale_edges.plan_sweep(db, _mappings()))
    assert "DECLINED 20 edge(s)" in line
    assert "STALE_FROM_CORE=20/20(100%)" in line
    assert "PROTECTED 1 human-confirmed" in line
    assert "not_reached 1 edge(s)" in line
    assert "count_kind=exact" in line


def test_a_refusal_summary_says_refused_and_why():
    line = graph_stale_edges.format_plan_summary(
        None, blockers=["table 'x' was rejected: y"])
    assert line.startswith("[GraphStaleEdges] REFUSED")
    assert "table 'x' was rejected: y" in line


def test_run_sweep_is_a_dry_run_unless_asked(stale_env, caplog):
    """Precedent: ``GET /admin/enrichment/auto-confirm/dry-run`` measures first.

    Defect injection: flipping the ``apply_deletions`` default to True makes the
    surviving-edge assertion red.
    """
    db = stale_env
    _bonding_row(db, "LOG1")
    db.commit()
    _derive(db, BONDING)
    _drop_row(db, BONDING, "row_LOG1")

    with caplog.at_level(logging.INFO):
        out = graph_stale_edges.run_sweep(known_tables=crud.TABLE_CONFIG)

    assert out["status"] == "ok"
    assert out["applied"] is None
    assert len(out["plan"]["delete_ids"]) == 1
    assert len(_edges(db, "STALE_FROM_CORE")) == 1, "a dry run wrote to the graph"
    assert "would delete 1" in caplog.text

    applied = graph_stale_edges.run_sweep(known_tables=crud.TABLE_CONFIG,
                                          apply_deletions=True)
    assert applied["applied"] == 1
    assert _edges(db, "STALE_FROM_CORE") == []


def test_run_sweep_logs_even_when_there_is_nothing_to_do(stale_env, caplog):
    with caplog.at_level(logging.INFO):
        out = graph_stale_edges.run_sweep(known_tables=crud.TABLE_CONFIG)
    assert out["status"] == "ok"
    assert "[GraphStaleEdges]" in caplog.text, \
        "a silent cycle is indistinguishable from a dead one"


# ---------------------------------------------------------------------------
# 5) ownership parsing - the unit that every verdict rests on
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ref", [None, "", "   ", "no_colon", ":row_1", "tbl:",
                                 "tbl:None", "tbl:   "])
def test_unownable_refs_parse_to_none(ref):
    assert graph_stale_edges.parse_row_ref(ref) is None


def test_a_well_formed_ref_parses_to_its_table_and_row():
    assert graph_stale_edges.parse_row_ref("bonding_log:row_7") == \
        ("bonding_log", "row_7")


def test_human_confirmation_is_selected_positively():
    """Never by blacklisting the automatic sources - there are 10,750 distinct
    automatic source values on live, so a blacklist can only ever be incomplete."""
    assert graph_stale_edges.is_human_confirmed(crud.USER_SOURCE) is True
    for other in ("pipeline_parser", "chain_ingestion", "collision_merge",
                  "some_file_20260804.csv", "unknown", "", None):
        assert graph_stale_edges.is_human_confirmed(other) is False
