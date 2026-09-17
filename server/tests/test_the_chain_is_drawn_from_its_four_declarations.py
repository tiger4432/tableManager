# -*- coding: utf-8 -*-
"""S-178. One flow lives in four files; `/chain/graph` puts them on one picture.

Owner: 「chain 이 너무 거미줄 같아」. The web is not in the code — it is in the fact that
`chain_rules.json`, `enrichment_rules.json`, `virtual_join_rules.json` and
`ledger_config.json` each hold a quarter of one flow, and nothing has ever joined them.

🔴 WHAT THIS FILE GUARDS IS THAT THE PICTURE IS READ, NEVER INFERRED.
Every edge comes from a declaration through the product's own loader, and 「who wakes
whom」 is asked of the WORKER'S function rather than re-implemented — a second
implementation of that predicate would eventually draw a wake that does not happen, which
is worse than drawing none. The test for it calls the same function the route does and
compares, so the two cannot drift apart silently.

⚠️ WHAT A REFERENCE VIEW READS IS DECLARED OR IT IS UNKNOWN (판정 283). It was neither
until this round: the view is arbitrary SQL and nothing named its tables, so the first cut
could only count the absence. `reads:` is now the cell an operator writes, and what is
pinned here is that a declared one draws a real edge, an undeclared one is COUNTED rather
than guessed, and a typo drops the view by name — a graph is read as fact, so an arrow from
a table that does not exist is worse than no arrow.

⚠️ AND TWO WRITERS ON ONE CELL IS A VALUE, NOT A FAULT (소유자 「이 둘이 충돌 안 나?」).
`contested` is cells with two NAMED writers; `contested_tables` is the weaker claim, tables
two writers share where neither declared a column. They stay apart because folding them
would let a reader take a question for a fact.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import chain.graph                                                   # noqa: E402
from chain import ingestion_worker as worker                              # noqa: E402


TRIGGER = "cg_test_trigger"
TARGET = "cg_test_target"
DERIVED = "cg_test_derived"
RIGHT = "cg_test_reference"


class _FakeDb:
    def get_bind(self):
        return type("B", (), {"dialect": type("D", (), {"name": "sqlite"})()})()


def chain_rule(**kw):
    base = {"name": "cg_rule", "trigger_table": TRIGGER, "target_table": TARGET,
            "enabled": True}
    base.update(kw)
    return base


def by_kind(graph, kind):
    return [e for e in graph["edges"] if e["kind"] == kind]


def node(graph, name):
    return next(n for n in graph["nodes"] if n["id"] == name)


@pytest.fixture(name="graph")
def fixture_graph(monkeypatch):
    """The four loaders, each answering with one declaration, through the real assembler."""
    from chain import enrichment
    from chain import legacy_join_declaration as vjc
    from database import crud

    rules = [chain_rule()]
    # ⚰️ ONE READER NOW (S-179 ①, 판정 293-b). This used to patch BOTH `_chain_rule_file`
    # and `load_chain_rules` — the two readers the graph kept so it could tell written
    # rules from synthesized ones. That split is gone, and the fixture getting SHORTER is
    # the evidence: there is one way in.
    monkeypatch.setattr(worker, "load_chain_rules", lambda: rules)
    monkeypatch.setattr(enrichment.config, "load_enrichment_rules",
                        lambda **kw: [{"name": "cg_enrich", "derived_table": DERIVED,
                                       "enabled": True,
                                       "decision_key": ["job", "slot"]}])
    monkeypatch.setattr(vjc, "load_virtual_join_rules",
                        lambda **kw: [{"name": "cg_vjoin", "left_table": TARGET,
                                       "right_table": RIGHT, "enabled": True,
                                       "right_columns": ["ref_id"], "right_folds": [None],
                                       "expose": ["grade"]}])
    monkeypatch.setattr(vjc, "unique_index_covering",
                        lambda *a, **kw: "uq_vjoin_cg_test_reference_ref_id")
    monkeypatch.setattr(crud, "TABLE_CONFIG",
                        {TRIGGER: {}, TARGET: {}, DERIVED: {}, RIGHT: {}})

    class _Plan:
        relation, status, planned, refusal = TARGET, "active", True, None

    snapshot = type("S", (), {"source_plans": {"cg_source": _Plan()}})()
    monkeypatch.setattr("ledger.setup.load_setup",
                        lambda *a, **kw: type("Setup", (), {"snapshot": snapshot})())
    monkeypatch.setattr("ledger.followup.base_tables_of", lambda e, r: (r,))
    return chain.graph.chain_graph(_FakeDb())


# ---------------------------------------------------------------------------
# 1. Four files, four edge kinds, and the counts that let a reader check it
# ---------------------------------------------------------------------------

def test_each_declaration_contributes_its_own_kind(graph):
    """⚰️ `enrich` USED TO BE HERE UNCONDITIONALLY (S-179 ①, 판정 292·293-b). Enrichment's
    own arrow — the derived table feeding itself — is a CHAIN RULE now and draws as
    `mapper`, so `enrich` is left meaning only 「this reference view reads that table」,
    which appears when a view declares `reads:`. This fixture declares none.

    🔴 The kind did not become unreachable: `test_an_undeclared_reads_is_counted_on_the_
    rule_that_replaced_the_self_loop` and its sibling below still score it."""
    assert {e["kind"] for e in graph["edges"]} == {"mapper", "vjoin", "ledger"}


def test_the_counts_say_what_each_file_declared(graph):
    """🔴 THE GATE'S NUMBER. The picture is checkable against the files rather than
    believed: an edge that appears without a rule behind it moves one of these."""
    assert graph["counts"]["chain_rules"] == 1
    assert graph["counts"]["enrichment_rules"] == 1
    assert graph["counts"]["virtual_joins"] == 1
    assert graph["counts"]["ledger_sources"] == 1
    assert graph["counts"]["edges"] == len(graph["edges"])
    assert graph["counts"]["nodes"] == len(graph["nodes"])


def test_the_mapper_edge_carries_what_decides_whether_it_fires(graph):
    edge = by_kind(graph, "mapper")[0]
    assert (edge["from"], edge["to"]) == (TRIGGER, TARGET)
    assert edge["rule"] == "cg_rule" and edge["enabled"] is True
    assert edge["allow_chain_trigger"] is False


def test_the_vjoin_edge_points_from_the_right_table_and_names_its_index(graph):
    """The join feeds the LEFT table at read time, so the arrow runs right -> left. The
    index is asked of the database because a declared rule with no index is not in
    effect, and a picture showing it live would be showing a join that is not happening."""
    edge = by_kind(graph, "vjoin")[0]
    assert (edge["from"], edge["to"]) == (RIGHT, TARGET)
    assert edge["unique_index"] == "uq_vjoin_cg_test_reference_ref_id"


def test_the_ledger_is_one_node(graph):
    edge = by_kind(graph, "ledger")[0]
    assert edge["to"] == chain.graph.LEDGER_NODE_ID
    assert edge["from"] == TARGET and edge["source"] == "cg_source"
    ledger_nodes = [n for n in graph["nodes"] if n["kind"] == chain.graph.NODE_LEDGER]
    assert len(ledger_nodes) == 1, (
        "fifteen ledger nodes would invent a distinction the declaration does not make")


# ---------------------------------------------------------------------------
# 2. 🔴 The half-graph that already cost a round
# ---------------------------------------------------------------------------

def test_a_rule_that_also_writes_map_metadata_draws_both_edges(monkeypatch, graph):
    """MEASURED 2026-09-04, on the validator this picture sits beside: a rule under
    `allow_map_metadata_upsert` writes map metadata TOO, that write raises its own chain
    event, and a graph that saw one of the two writes passed a live cycle. A picture with
    the same blind spot would hide the same cycle."""
    import map_meta_registrar

    edges = chain.graph._mapper_edges(
        [chain_rule(allow_map_metadata_upsert=True)])
    assert len(edges) == 2
    assert {e["to"] for e in edges} == {TARGET, map_meta_registrar.META_TABLE}
    metadata_edge = next(e for e in edges
                         if e["to"] == map_meta_registrar.META_TABLE)
    assert metadata_edge["via"] == "allow_map_metadata_upsert"


def test_the_metadata_edge_is_not_taken_from_the_rule(monkeypatch):
    """⛔ `metadata_target_table` NAMES THE MAPPER'S SOURCE in one shipped rule, so
    borrowing it for this arrow would draw it backwards. The table comes from the
    registrar."""
    import map_meta_registrar

    edges = chain.graph._mapper_edges([chain_rule(
        allow_map_metadata_upsert=True, metadata_target_table="cg_not_this_one")])
    assert all(e["to"] != "cg_not_this_one" for e in edges)
    assert any(e["to"] == map_meta_registrar.META_TABLE for e in edges)


# ---------------------------------------------------------------------------
# 3. 🔴 `wakes` is the worker's own answer
# ---------------------------------------------------------------------------

def test_wakes_is_the_workers_own_predicate(graph):
    """Not a second implementation. The route calls `_group_triggered_rules`; so does
    this assertion, and a drift between them shows up here rather than on a screen."""
    event = type("E", (), {"table_name": TRIGGER, "event_type": "CREATE",
                           "payload": {"source_name": "user"}})()
    expected = sorted(r["name"] for r in worker._group_triggered_rules(
        [event], [chain_rule()]))
    assert node(graph, TRIGGER)["wakes"]["user"] == expected


def test_a_chain_write_wakes_only_what_opted_in(graph, monkeypatch):
    """🔴 THE OPT-IN IS MOST OF WHAT MAKES THE WEB A WEB, so it is a value rather than
    something a reader infers from the edges."""
    rules = [chain_rule()]
    assert chain.graph._wakes(worker, rules, TRIGGER)["chain"] == []

    rules = [chain_rule(allow_chain_trigger=True)]
    assert chain.graph._wakes(worker, rules, TRIGGER)["chain"] == ["cg_rule"]


def test_a_table_nothing_watches_wakes_nothing(graph):
    assert node(graph, RIGHT)["wakes"] == {"user": [], "chain": []}


# ---------------------------------------------------------------------------
# 4. ⚠️ The edge that cannot be drawn says so
# ---------------------------------------------------------------------------

def test_a_declared_reads_becomes_a_real_edge():
    """판정 283. `reads:` is the cell an operator writes, and a written one draws the arrow
    the SQL could only have been guessed at."""
    edges = chain.graph._enrich_edges([{
        "name": "cg_enrich", "derived_table": DERIVED, "enabled": True,
        "decision_key": ["job"],
        "reference_views": [{"label": "recent runs", "required_binds": ["job"],
                             "reads": ["cg_test_upstream"]}]}])
    drawn = [e for e in edges if e.get("via_reference_view")]
    assert len(drawn) == 1
    assert (drawn[0]["from"], drawn[0]["to"]) == ("cg_test_upstream", DERIVED)
    assert "reads_unknown" not in edges[0]


def test_an_undeclared_reads_is_counted_on_the_rule_that_replaced_the_self_loop():
    """⛔ COUNTED, NOT SILENT AND NOT INVENTED. 「nobody declared it」 must not render like
    「it reads nothing」, and must never render like a guess.

    ⚰️ IT MOVED RATHER THAN DIED (S-179 ①). This detail used to ride on the `enrich`
    self-loop; that arrow is now the auto-confirm CHAIN RULE, so the count rides on the
    mapper edge — carried from the rule's own `params`. Had it been left behind, the fold
    would have been a loss of information dressed as a change of label."""
    views = [{"label": "recent runs", "required_binds": ["job"]}]
    edge = chain.graph._mapper_edges([{
        "name": "enrichment_auto_confirm:cg_enrich",
        "trigger_table": DERIVED, "target_table": DERIVED, "enabled": True,
        "params": {"decision_key": ["job"], "reference_views": views}}])[0]
    assert edge["reads_unknown"] == 1
    assert edge["reference_views"][0]["reads"] is None
    # And the reads half draws NO arrow when nobody declared one.
    assert not [e for e in chain.graph._enrich_edges([{
        "name": "cg_enrich", "derived_table": DERIVED, "enabled": True,
        "decision_key": ["job"], "reference_views": views}])
        if e.get("via_reference_view")]


def test_an_unknown_table_in_reads_drops_the_view_by_name():
    """A typo would otherwise draw an edge from a table that does not exist, and a graph is
    read as fact. Refused at the DECLARATION, per view, with the name in the message."""
    from chain import enrichment

    rejections = []
    views = enrichment.config._normalize_reference_views(
        "cg_enrich",
        [{"label": "typo", "query": "SELECT 1", "reads": ["cg_no_such_table"]}],
        ["job"], rejections=rejections, known_tables={TRIGGER: {}})
    assert views == []
    assert any("cg_no_such_table" in str(r) for r in rejections), rejections


def test_a_declared_reads_survives_the_loader():
    from chain import enrichment

    views = enrichment.config._normalize_reference_views(
        "cg_enrich",
        [{"label": "ok", "query": "SELECT 1", "reads": [TRIGGER, TRIGGER]}],
        ["job"], known_tables={TRIGGER: {}})
    assert views[0]["reads"] == [TRIGGER], "de-duplicated and sorted"


# ---------------------------------------------------------------------------
# 4-bis. 🔴 Two writers on one cell — the owner's question, as a value
# ---------------------------------------------------------------------------

def test_two_declarations_writing_one_cell_are_listed():
    """소유자 「이 둘이 충돌 안 나?」. Not an error — layering decides, and decides
    correctly. What is not normal is the fact being spread across three files with nowhere
    to read it."""
    contested = chain.graph._contested(
        [chain_rule(name="mapper_rule", target_table=DERIVED,
                    target_field="grade")],
        [{"name": "enrich_rule", "derived_table": DERIVED,
          "target_fields": ["grade", "other"]}],
        [])
    assert contested == [{"table": DERIVED, "column": "grade",
                          "writers": ["enrich_rule", "mapper_rule"]}]


def test_one_writer_is_not_contested():
    assert chain.graph._contested(
        [chain_rule(target_table=DERIVED, target_field="grade")], [], []) == []


def test_a_virtual_join_counts_as_a_writer_of_the_cell_it_presents():
    """It writes nothing to disk and a reader of that cell still sees its value where a
    mapper's may also be — which is exactly the question being asked."""
    contested = chain.graph._contested(
        [chain_rule(name="mapper_rule", target_table=TARGET, target_field="grade")],
        [],
        [{"name": "cg_vjoin", "left_table": TARGET, "expose": ["grade"]}])
    assert contested[0]["writers"] == ["cg_vjoin", "mapper_rule"]


def test_a_shared_table_with_no_declared_column_is_the_weaker_list():
    """⚠️ SEPARATE, AND DELIBERATELY WEAKER. Two rules on one table may touch disjoint
    columns and only the mapper's Python knows; folding this into `contested` would let a
    reader take a question for a fact."""
    weak = chain.graph._contested_tables(
        [chain_rule(name="a", target_table=TARGET),
         chain_rule(name="b", target_table=TARGET)], [])
    assert weak == [{"table": TARGET, "writers": ["a", "b"]}]
    # And a rule that DID name its column is not in the weak list - it is in the strong one.
    assert chain.graph._contested_tables(
        [chain_rule(name="a", target_table=TARGET, target_field="grade"),
         chain_rule(name="b", target_table=TARGET)], []) == []


def test_the_derived_table_still_feeds_itself_under_the_new_label():
    """The fold's whole claim: the ENDPOINTS do not move, only the label. This is the
    assertion that would catch the arrow being lost rather than relabelled."""
    edge = chain.graph._mapper_edges([{
        "name": "enrichment_auto_confirm:cg_enrich",
        "trigger_table": DERIVED, "target_table": DERIVED, "enabled": True,
        "follow_up": True, "origin": "synthesized:cg_enrich",
        "params": {"decision_key": ["job", "slot"]}}])[0]
    assert edge["kind"] == "mapper"
    assert edge["from"] == edge["to"] == DERIVED
    assert edge["decision_key"] == ["job", "slot"]
    assert edge["origin"] == "synthesized:cg_enrich"


# ---------------------------------------------------------------------------
# 5. What the loader refused is part of the picture
# ---------------------------------------------------------------------------

def test_a_refused_cycle_is_shown_rather_than_hidden(monkeypatch):
    """It is the one thing an operator cannot see anywhere else: the rules are in the
    file, look live, and the worker refused the whole document over them."""
    loop = [chain_rule(name="a", trigger_table="t1", target_table="t2",
                       allow_chain_trigger=True),
            chain_rule(name="b", trigger_table="t2", target_table="t1",
                       allow_chain_trigger=True)]
    monkeypatch.setattr(worker, "load_chain_rules", lambda: loop)
    from chain import enrichment
    from chain import legacy_join_declaration as vjc
    monkeypatch.setattr(enrichment.config, "load_enrichment_rules", lambda **kw: [])
    monkeypatch.setattr(vjc, "load_virtual_join_rules", lambda **kw: [])
    monkeypatch.setattr("ledger.setup.load_setup",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no ledger")))

    graph = chain.graph.chain_graph(_FakeDb())
    assert graph["cycles"] and "cycle" in graph["cycles"][0]
    # And a quarter of the picture missing is NAMED, not silently empty.
    assert "no ledger" in graph["ledger_error"]


def test_a_healthy_load_carries_no_error_key(graph):
    """An absent key means 「nothing to say」; a present one means 「this quarter is
    missing, and here is why」. They must not render alike."""
    assert "ledger_error" not in graph
    assert graph["cycles"] == []


# ---------------------------------------------------------------------------
# 6. The route
# ---------------------------------------------------------------------------

def test_the_route_answers_and_is_gated(client, monkeypatch):
    from admin import auth
    from main import app

    token = "s178-graph-token"
    monkeypatch.setenv(auth.ADMIN_TOKEN_ENV, token)
    res = client.get("/chain/graph", headers={auth.ADMIN_TOKEN_HEADER: token})
    assert res.status_code == 200, res.text
    payload = res.json()
    assert "nodes" in payload and "edges" in payload and "counts" in payload
    assert res.headers.get("Cache-Control") == "no-store"

    # ⚠️ `/chain/graph` IS NOT UNDER `/admin`, so `test_admin_auth`'s durable audit does
    # not walk it. It reads the operator's live declarations, so the gate is asserted here
    # by name rather than assumed.
    for route in app.routes:
        if getattr(route, "path", None) == "/chain/graph":
            calls = {getattr(d, "dependency", None)
                     for d in getattr(route, "dependencies", ())}
            assert calls & set(auth.ADMIN_GATES)
            return
    raise AssertionError("/chain/graph is not registered")
