# -*- coding: utf-8 -*-
"""A predicate's qualifier declared `indexed` (총괄 10-27 ㄱ) is one ledger index a bound step back takes:

    "vocabulary": {"<p>": {"object": {"qualifiers": {"required": [...], "optional": [...], "indexed": ["<q>"]}}}}

    seat                                         gate
    validator                                    test_indexed_names_a_declared_qualifier_only
    the source's fingerprint (no re-translate)   test_an_indexed_cell_moves_no_sources_fingerprint
    the world's list (`partitioned_indexes`)     test_the_worlds_list_is_the_ref_index_and_each_indexed_qualifier
    the name                                     test_a_qualifier_index_name_is_an_identifier_under_63
    the read's form (`_bound_on`)                test_the_read_is_bound_on_one_qualifier_or_as_it_was
    no bound - the statement as before           test_an_unbound_read_is_the_statement_it_was
    built a partition at a time, a new one too   test_the_index_is_built_on_every_partition_and_a_new_one_has_it (pg)
    the bound step takes it, the same answer     test_a_bound_step_back_takes_the_index_and_answers_the_same (pg)
    the cell taken out, kept and said (pg)       test_a_qualifier_index_no_declaration_names_is_kept_and_its_drop_said
"""
import copy
import json
import os
import re
from datetime import datetime, timezone

import pytest

import paths
from ledger import schema
from ledger.setup import load_setup
from ledger.setup_bundle import load_physical_catalog, validate_bundle_errors
from ledger.setup_registry import source_cursor_fingerprint
from ledger_api import ledger_subgraph

TABLES = {"proc_pass": {"business_key": "pass_key", "column_types": {
    "pass_key": "string", "wafer": "string", "product": "string", "step_seq": "number", "tx_id": "string",
    "event_time": "string"}}}


def _column(name):
    return {"kind": "column", "column": name, "approval_status": "approved"}


DECLARATION = {
    "setup_version": 6,
    "vocabulary": {"processed_at@1": {"status": "active", "subjects": ["wafer@1"], "object": {
        "kind": "entity_ref", "types": ["process_step@1"], "qualifiers": {"required": [], "optional": ["tx_id"]}}}},
    "entities": {"wafer@1": {"keys": ["wafer"]},
                 "process_step@1": {"keys": ["product", "step_seq"], "class": "static"}},
    "sources": {"pass_events": {
        "relation": "proc_pass",
        "read": {"unit": "row", "identity": ["pass_key"], "order_by": ["pass_key"],
                 "cursor": {"columns": ["pass_key"]}, "occurred_at": {"basis": "ingested", "timezone": "Asia/Seoul"}},
        "map": {"implementation_id": "declarative-role", "implementation_version": 1, "unit": {"kind": "row"}},
        "bind": {"mappings": {"passed": {"predicate": "processed_at@1", "bind": {
            "occurred_at": _column("event_time"),
            "subject": {"kind": "entity", "entity_type": "wafer@1", "keys": {"wafer": _column("wafer")},
                        "approval_status": "approved"},
            "target": {"kind": "entity", "entity_type": "process_step@1",
                       "keys": {"product": _column("product"), "step_seq": _column("step_seq")},
                       "approval_status": "approved"},
            "tx_id": _column("tx_id")}}}}}},
}


def _indexed(names, declaration=DECLARATION):
    out = copy.deepcopy(declaration)
    out["vocabulary"]["processed_at@1"]["object"]["qualifiers"]["indexed"] = list(names)
    return out


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A config root of this test's own: the table and the declaration (`write`)."""
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    (config / "table_config.json").write_text(json.dumps(TABLES), encoding="utf-8")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))

    def write(declaration):
        (config / "ontology" / "ledger_config.json").write_text(json.dumps(declaration), encoding="utf-8")
        return str(config / "ontology")
    write.catalog = load_physical_catalog(str(config / "table_config.json"))
    return write


# ---------------------------------------------------------------------------
# the declaration
# ---------------------------------------------------------------------------

def test_indexed_names_a_declared_qualifier_only(root):
    path = "bundle.vocabulary.processed_at.object.qualifiers.indexed"
    said = [(issue.path, issue.message) for issue in validate_bundle_errors(_indexed(["lot"]), catalog=root.catalog)]
    assert said == [(path, "indexed qualifiers must be declared in required or optional: ['lot']")], said
    assert validate_bundle_errors(_indexed(["tx_id"]), catalog=root.catalog) == ()
    assert [issue.path for issue in validate_bundle_errors(_indexed("tx_id"), catalog=root.catalog)] == [path]
    assert load_setup(root(_indexed(["tx_id"])), catalog=root.catalog) is not None


def test_an_indexed_cell_moves_no_sources_fingerprint(root):
    """An index changes no atom: the source's cursor is not asked to start again (re-translate) for it."""
    def fingerprint(declaration):
        return source_cursor_fingerprint(load_setup(root(declaration), catalog=root.catalog).snapshot, "pass_events")
    assert fingerprint(DECLARATION) == fingerprint(_indexed(["tx_id"]))


def test_the_worlds_list_is_the_ref_index_and_each_indexed_qualifier(root):
    names = schema.world_names(schema.DEFAULT_WORLD)
    root(DECLARATION)
    assert schema.declared_indexed_qualifiers(names) == []
    assert schema.partitioned_indexes(names) == schema.PARTITIONED_INDEXES
    root(_indexed(["tx_id"]))
    assert schema.declared_indexed_qualifiers(names) == ["tx_id"]
    assert schema.partitioned_indexes(names) == schema.PARTITIONED_INDEXES + (schema.qualifier_index("tx_id"),)
    index, columns, predicate, child, _serves = schema.qualifier_index("tx_id")
    assert (index, child) == ("idx_ledger_q_tx_id", "{partition}_q_tx_id")
    assert columns.endswith("(object_payload->'qualifiers'->'tx_id'))")
    assert predicate == "WHERE object_kind = 'entity_ref'"
    root("{not json")
    assert schema.declared_indexed_qualifiers(names) is None, "an unreadable declaration is not «none declared»"


@pytest.mark.parametrize("name", ["tx_id", "Tx-ID", "트랜잭션", "a_very_long_qualifier_name_beyond", "it's"])
def test_a_qualifier_index_name_is_an_identifier_under_63(name):
    index, columns, _predicate, child, _serves = schema.qualifier_index(name)
    assert re.fullmatch(r"[a-z0-9_]+", index) and len(index) <= 63
    assert len(child.format(partition="ledger_events_2026_10")) <= 63
    assert ("'%s'" % name.replace("'", "''")) in columns
    folded = re.sub(r"[^a-z0-9_]", "_", name.lower())
    if folded != name:                     # two names one spelling would fold together are two indexes
        assert index != schema.qualifier_index(folded)[0]


# ---------------------------------------------------------------------------
# the read
# ---------------------------------------------------------------------------

def _node(**bound):
    return {"type": "process_step", "keys": {"s": 1},
            "skip": {"bound": {p: {"names": names, "values": [["T1"]]} for p, names in bound.items()}}}


@pytest.mark.parametrize("frontier, follow, said", [
    ([_node(processed=["tx_id"]), _node(processed=["tx_id"])], ["processed@1"], "tx_id"),
    ([_node(processed=["tx_id"]), {"type": "process_step", "keys": {"s": 2}}], ["processed"], None),
    ([_node(processed=["tx_id", "lot"])], ["processed"], None),
    ([_node(processed=["tx_id"])], ["processed", "measures"], None),
    ([_node(processed=["tx_id"], measures=["lot"])], ["processed", "measures"], None),
    ([_node(processed=["tx_id"])], None, None),
])
def test_the_read_is_bound_on_one_qualifier_or_as_it_was(frontier, follow, said):
    assert ledger_subgraph._bound_on(frontier, follow) == said


def test_an_unbound_read_is_the_statement_it_was(monkeypatch):
    """No node bound, or bound on a qualifier no world declares `indexed`: no `bound_frontier`, no equality - the arms
    read `frontier` as before (MEASURED, box 400,000 atoms: the equality with no index turned the planner to a full
    scan, 3.2 s -> 6.1 s)."""
    said = []
    bound_node = ("process_step", {"s": 1}, {"bound": {"processed": {"names": ["tx_id"], "values": [["T1"]]}}})
    for indexed, entity in (({"tx_id"}, ("process_step", {"s": 1}, {"steps": [{"p": "x", "d": "incoming", "t": "w"}]})),
                            ({"lot"}, bound_node), ((), bound_node), ({"tx_id"}, bound_node)):
        lookup = ledger_subgraph.SqlEvidenceLookup(connection=None, indexed=indexed)
        monkeypatch.setattr(lookup, "_execute", lambda sql, params: said.append((sql, params)) or [])
        lookup.claims_for_entities([entity], "both", 10, follow=["processed"])
    (unbound, unbound_params), (other, _), (none, _), (bound, bound_params) = said
    assert other == none == unbound, "bound on a qualifier no world indexes: the statement as it was"
    assert "bound_frontier" not in unbound and "bound_on" not in unbound_params
    assert unbound.count("FROM frontier f") == 2
    assert bound.count("FROM bound_frontier f") == 1
    assert "e.object_payload->'qualifiers'->%(bound_on)s = f.bv" in bound and bound_params["bound_on"] == "tx_id"
    # the same statement but the bound arm's frontier and its one equality
    assert bound.replace(ledger_subgraph.BOUND_FRONTIER_CTE.rstrip(), "").replace(ledger_subgraph.BOUND_JOIN, "") \
        .replace("FROM bound_frontier f", "FROM frontier f") == unbound


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

WORLD = "qix10"
NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def _world(pg_engine, monkeypatch, declared):
    monkeypatch.setattr(schema, "worlds", lambda: [WORLD])
    # this world's declaration only - the default world's ledger may be there from another test, and declares none
    monkeypatch.setattr(schema, "declared_indexed_qualifiers",
                        lambda names: declared[0] if names.world == WORLD else [])
    return schema.world_names(WORLD)


def _children(connection, names, index):
    with connection.cursor() as cursor:
        cursor.execute("SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
                       "WHERE i.inhparent = to_regclass(%s) ORDER BY 1", (schema.in_space(names, index),))
        return [name for (name,) in cursor.fetchall()]


def _build(pg_engine, connection):
    """The index work, the test's own connection out of any transaction first - CONCURRENTLY waits for every older
    one, so one left open here would wait on itself."""
    from database import models

    connection.commit()
    said = []
    models.ensure_model_indexes(pg_engine, say=said.append, sources=("ledger",))
    return said


def _drop_world(connection, names):
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA IF EXISTS %s CASCADE" % names.ledger.split(".")[0])
    connection.commit()


@pytest.mark.pg
def test_the_index_is_built_on_every_partition_and_a_new_one_has_it(pg_engine, monkeypatch):
    names = _world(pg_engine, monkeypatch, [["tx_id"]])
    index = schema.qualifier_index("tx_id")[0]
    connection = pg_engine.raw_connection()
    try:
        schema.ensure_schema(connection, names=names)
        for month in (9, 10):
            schema.ensure_partition(connection, datetime(2026, month, 15, tzinfo=timezone.utc), names=names)
        connection.commit()
        first, second = [name for name, _bound in schema.partitions(connection, names)]
        _build(pg_engine, connection)
        assert _children(connection, names, index) == [first + "_q_tx_id", second + "_q_tx_id"]
        assert schema.index_valid(connection, schema.in_space(names, index))
        with connection.cursor() as cursor:
            cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = %s", (first + "_q_tx_id",))
            made = cursor.fetchone()[0]
        assert "(((object_payload -> 'qualifiers'::text) -> 'tx_id'::text))" in made, made
        assert made.endswith("WHERE (object_kind = 'entity_ref'::text)"), made
        schema.ensure_partition(connection, datetime(2026, 11, 15, tzinfo=timezone.utc), names=names)
        connection.commit()
        third = [name for name, _bound in schema.partitions(connection, names)][-1]
        assert len(_children(connection, names, index)) == 3, "a partition made after it has its own"
        assert third not in (first, second)
        row = next(row for row in schema.partitioned_index_states(pg_engine)
                   if row["world"] == WORLD and row["name"].endswith(index))
        assert (row["partitions"], row["partitions_missing"], row["valid"]) == (3, 0, True)
    finally:
        _drop_world(connection, names)
        connection.close()


@pytest.mark.pg
def test_a_bound_step_back_takes_the_index_and_answers_the_same(pg_engine, monkeypatch):
    """A step P with W1, W2 under T1 and 30 wafers under T9: from W1, `processed:tx_id` reaches W1, W2 - with the index
    as it was (no `indexed`) and with it the same, and the bound read's plan looks the qualifier up (Index Cond)."""
    from ledger import explorer
    from ledger.envelope import Atom
    from ledger.store import LedgerStore

    names = _world(pg_engine, monkeypatch, [["tx_id"]])
    store = LedgerStore(pg_engine, world=WORLD)
    step = {"type": "process_step", "keys": {"step": "P"}}

    def processed(n, wafer, tx):
        return Atom(subject_type="wafer", subject_keys={"wafer_id": wafer}, predicate="processed",
                    object_kind="entity_ref", object_payload={**step, "qualifiers": {"tx_id": tx}},
                    occurred_at=NOW, source_who="qix-fixture", source_translator_ver="v1",
                    source_raw_ref="r%d" % n, molecule_ref="event:r%d" % n)
    atoms = [processed(1, "W1", "T1"), processed(2, "W2", "T1")] + [
        processed(10 + n, "W%d" % (10 + n), "T9") for n in range(30)]
    connection = pg_engine.raw_connection()
    try:
        store.ensure_schema()
        store.ensure_partitions(connection, [NOW])
        store.insert_atoms(connection, atoms)
        connection.commit()
        seed = explorer.entity_id("wafer", {"wafer_id": "W1"})

        def walk(indexed=()):
            lookup = ledger_subgraph.SqlEvidenceLookup(connection, worlds=(names,), indexed=indexed)
            read = []
            original = lookup._execute
            lookup._execute = lambda sql, params: read.append((sql, params)) or original(sql, params)
            body = ledger_subgraph.subgraph(seed, lookup, hops=4, direction="both", follow=["processed"],
                                            follow_keys={"processed": ("tx_id",)})
            wafers = sorted(node["keys"]["wafer_id"] for node in body["nodes"] if node["type"] == "wafer")
            return (wafers, body["walk"]["claims_scanned"], sorted(edge["id"] for edge in body["edges"])), read
        before, _ = walk()
        _build(pg_engine, connection)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE %s" % names.ledger)
        connection.commit()
        after, read = walk({"tx_id"})
        assert before == after and before[:2] == (["W1", "W2"], 4), (before, after)
        sql, params = next((sql, params) for sql, params in read if "bound_frontier" in sql)
        with connection.cursor() as cursor:
            # a 32-atom table is hashed whole; with the joins a big one takes (box 2,000,000 atoms: nested loop,
            # 11.5 s -> 0.09 s) the index must serve the equality - its expression is the statement's
            for setting in ("enable_seqscan", "enable_hashjoin", "enable_mergejoin"):
                cursor.execute("SET LOCAL %s = off" % setting)
            cursor.execute("EXPLAIN " + sql, params)
            plan = "\n".join(line for (line,) in cursor.fetchall())
        assert re.search(r"Index Scan using \S+_q_tx_id .*\n\s*Index Cond: .*"
                         r"\(\(object_payload -> 'qualifiers'::text\) -> 'tx_id'::text\) = ", plan), plan
    finally:
        _drop_world(connection, names)
        connection.close()


@pytest.mark.pg
def test_a_qualifier_index_no_declaration_names_is_kept_and_its_drop_said(pg_engine, monkeypatch):
    declared = [["tx_id"]]
    names = _world(pg_engine, monkeypatch, declared)
    index = schema.in_space(names, schema.qualifier_index("tx_id")[0])
    connection = pg_engine.raw_connection()
    try:
        schema.ensure_schema(connection, names=names)
        schema.ensure_partition(connection, NOW, names=names)
        connection.commit()
        _build(pg_engine, connection)
        declared[0] = []
        said = _build(pg_engine, connection)
        assert schema.index_valid(connection, index), "an index no declaration names is not dropped by the product"
        assert [line for line in said if "DROP INDEX" in line] == [
            "[Indexes] %s - no declaration indexes it any more; a person drops it: DROP INDEX %s;" % (index, index)]
        declared[0] = None                                        # unreadable: nothing is said to be stale
        assert not [line for line in _build(pg_engine, connection) if "DROP INDEX" in line]
        with connection.cursor() as cursor:                       # the said statement drops it
            cursor.execute(said[-1].split("drops it: ", 1)[1])
        connection.commit()
        assert not schema.index_valid(connection, index)
    finally:
        _drop_world(connection, names)
        connection.close()
