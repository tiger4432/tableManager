# -*- coding: utf-8 -*-
"""총괄 a6db2f469 (소유자 10-07 「등록문장이란 개념 자체를 없애면 안됨?」 -> 안 ㄱ) and the 10-07 rulings:
the attributes a source binds for an entity become that entity's registration - the translator
writes it under `REGISTER_PREDICATE`, with no object, at the time of the molecule that named it.
Nobody writes a registration sentence; one written still reads as before (the control is
yesterday's bytes). On the shipped sample's `lot_slot_wafer` (lot_slot --has_wafer--> wafer),
rows from memory; PostgreSQL only where the ledger itself is the subject."""
import copy
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import pytest

from test_a_test_run_shows_the_atoms_its_rows_became import (
    SOURCE, _document, _preview, _row, _run, _service)
from ledger import explorer, runtime_v2, setup as ledger_setup, setup_bundle, store
from ledger.setup_registry import REGISTRATION_DERIVATION_PREFIX, cursor_translator_version
from ledger_api import ledger_subgraph

SENTENCE = "seat-holds-wafer"
CONTROL = os.path.join(os.path.dirname(__file__), "support", "registration_control_atoms.json")


def _bound(document, *, own_role=False, register_lot_slot=False):
    """`event_type` bound for the wafer - on the source (`bind.entities`) or on the role itself."""
    document["entities"]["wafer@1"]["attributes"] = ["event_type"]
    source = document["sources"][SOURCE]
    binding = {"kind": "column", "column": "event_type"}
    if own_role:
        source["bind"]["mappings"][SENTENCE]["bind"]["target"]["attributes"] = {"event_type": binding}
    else:
        source["bind"]["entities"] = {"wafer@1": {"attributes": {"event_type": binding}}}
    return document


def _atoms(tmp_path, document, rows):
    tmp_path.mkdir(parents=True, exist_ok=True)
    setup, _index, _ = _service(tmp_path, document).active()
    preview = _preview(setup, rows, len(rows)).preview
    return setup, runtime_v2._screened_atoms(setup.snapshot, SOURCE, preview)


def _registrations(atoms):
    return [atom for atom in atoms if setup_bundle.is_registration(atom.object_kind)]


@pytest.mark.parametrize("own_role", [False, True], ids=["source-entities", "role-own"])
def test_a_bound_attribute_with_no_sentence_becomes_the_entitys_registration(tmp_path, own_role):
    """The TARGET role's wafer - the end today's registration never read (roleframe compiled its
    type and keys only), so a role attribute reached no atom at all."""
    _setup, atoms = _atoms(tmp_path, _bound(_document(), own_role=own_role), [_row(i) for i in range(2)])
    relations = [atom for atom in atoms if atom.derivation == SENTENCE]
    registrations = _registrations(atoms)
    assert len(relations) == 2                                         # canary
    assert [(r.subject_type, r.subject_keys, r.predicate, r.object_payload, r.derivation)
            for r in registrations] == [
        ("wafer", rel.object_payload["keys"], setup_bundle.REGISTER_PREDICATE,
         {"qualifiers": {"event_type": "track_in"}}, REGISTRATION_DERIVATION_PREFIX + SENTENCE)
        for rel in relations]
    # 총괄 10-07 ②: the molecule's time, by the rule the naming sentence's atom follows
    assert [(r.occurred_at, r.occurred_at_basis, r.source_raw_ref) for r in registrations] == [
        (rel.occurred_at, rel.occurred_at_basis, rel.source_raw_ref) for rel in relations]


def test_a_registration_keeps_the_time_rule_of_the_sentence_that_named_it(tmp_path):
    """A world-time source whose sentence binds no event time stores the molecule's time as not an
    event's (총괄 0c9b6e3c0) - the registration it names says the same, not the source's world time."""
    document = _bound(_document())
    del document["sources"][SOURCE]["bind"]["mappings"][SENTENCE]["bind"]["occurred_at"]
    _setup, atoms = _atoms(tmp_path, document, [_row(0)])
    assert sorted((a.derivation, a.occurred_at_basis) for a in atoms) == [
        (REGISTRATION_DERIVATION_PREFIX + SENTENCE, "ingested"), (SENTENCE, "ingested")]


def test_a_code_mapper_role_gets_its_bound_attributes_read_where_both_mappers_pass(tmp_path):
    """`_with_attribute_values` is the one seat both mapper kinds pass: an entity a code mapper
    hands over with its keys only gets the registered role's attributes read there."""
    import pandas as pd
    from ledger import roleframe

    (tmp_path / "c").mkdir()
    setup, _index, _ = _service(tmp_path / "c", _bound(_document())).active()
    context = roleframe.mapper_context(setup.snapshot, SOURCE)
    profile = context.source_plan.profile
    emission = roleframe.RoleEmission(sentence=SENTENCE, source_row_refs=("ROW-000",), roles={
        "subject": {"type": "lot_slot", "keys": {"lot": "L000", "slot": "1"}},
        "target": {"type": "wafer", "keys": {"wafer": "W000"}},
        "occurred_at": datetime(2026, 10, 7, tzinfo=timezone.utc)})
    filled = roleframe._with_attribute_values(context, profile, emission, pd.DataFrame([_row(0)]), "t")
    assert filled.roles["target"]["attributes"] == {"event_type": "track_in"}
    assert "attributes" not in filled.roles["subject"]


def test_registrations_are_folded_in_a_batch_by_their_shape_not_their_name(tmp_path):
    """An object-less sentence named anything is a registration (총괄 10-07 ⑤): two rows naming one
    wafer in one state keep the earliest, as `register` always did."""
    document = _document()
    document["vocabulary"]["enrolled@1"] = {"status": "active", "subjects": ["wafer@1"],
                                            "object": {"kind": "none", "qualifiers": {"required": [], "optional": []}}}
    target = document["sources"][SOURCE]["bind"]["mappings"][SENTENCE]["bind"]["target"]
    document["sources"][SOURCE]["bind"]["mappings"]["wafer-enrolled"] = {"predicate": "enrolled@1", "bind": {
        "occurred_at": {"kind": "column", "column": "event_time"}, "subject": copy.deepcopy(target)}}
    rows = [_row(0), dict(_row(1), wafer="W000")]
    _setup, atoms = _atoms(tmp_path, document, rows)
    enrolled = [a for a in atoms if a.predicate == "enrolled"]
    said = sorted(a.occurred_at for a in atoms if a.derivation == SENTENCE)
    assert len(said) == 2                                                     # canary: both rows said
    assert [(a.subject_keys, a.occurred_at) for a in enrolled] == [({"wafer": "W000"}, said[0])]


def test_a_source_that_admits_its_time_basis_stamps_its_registration_alike(tmp_path):
    document = _bound(_document())
    document["sources"][SOURCE]["read"]["occurred_at"] = {"basis": "ingested", "timezone": "Asia/Seoul"}
    rows = [dict(_row(i), created_at=datetime(2026, 10, 7, 1, i, tzinfo=timezone.utc)) for i in range(2)]
    _setup, atoms = _atoms(tmp_path, document, rows)
    assert {(a.derivation.split(":")[0], a.occurred_at_basis) for a in atoms} == {
        (SENTENCE, "ingested"), (REGISTRATION_DERIVATION_PREFIX.rstrip(":"), "ingested")}


def test_the_walk_shows_it_on_the_node_where_no_declared_predicate_has_no_object(tmp_path):
    """총괄 10-07 ③'s gate: the name list is one function, and the translator's own name is in it
    even for a vocabulary with no object-less predicate at all."""
    document = _bound(_document())
    _setup, atoms = _atoms(tmp_path, document, [_row(0)])
    vocabulary = {key: rule for key, rule in document["vocabulary"].items()
                  if rule["object"]["kind"] != "none"}
    assert all(rule["object"]["kind"] != "none" for rule in vocabulary.values()) and vocabulary
    follow = setup_bundle.registration_predicates(vocabulary)
    evidence = [ledger_subgraph.EvidenceAtom(
        id=str(uuid.uuid4()), subject_type=a.subject_type, subject_keys=a.subject_keys,
        predicate=a.predicate, object_kind=a.object_kind, object_payload=a.object_payload or {},
        occurred_at=a.occurred_at, source_who=a.source_who, source_translator_ver="v",
        source_raw_ref=a.source_raw_ref, supersedes=None, source_event_id=str(a.source_event_id),
        source_event_state=a.source_event_state, occurred_at_basis=a.occurred_at_basis) for a in atoms]
    seed = explorer.entity_id("wafer", {"wafer": "W000"})
    body = ledger_subgraph.subgraph(seed, ledger_subgraph.InMemoryEvidenceLookup(evidence), hops=1,
                                    registration_follow=follow)
    node = next(n for n in body["nodes"] if n["id"] == seed)
    assert node.get("attributes") == {"event_type": "track_in"}


def test_a_source_that_declares_its_registration_writes_yesterdays_bytes(tmp_path):
    """The control (총괄 10-07 ① ㄱ): a declared registration sentence still decides its subject's
    attributes, and the translator adds nothing beside it - the records equal what the code before
    this round wrote for the same rows (id and translator stamp left out; dumped then)."""
    with open(CONTROL, encoding="utf-8") as handle:
        yesterday = json.load(handle)
    rows = [_row(i) for i in range(4)]
    documents = {"declared_registration_with_attribute": _document(registered_wafer=True, attribute=True),
                 "declared_registration": _document(registered_wafer=True),
                 "no_attribute": _document()}
    for name, document in documents.items():
        _setup, atoms = _atoms(tmp_path / name, document, rows)
        records = []
        for atom in atoms:
            record = store.atom_record(atom)
            record.pop("id"), record.pop("source_translator_ver")
            records.append(json.loads(json.dumps(record, default=str, sort_keys=True)))
        assert sorted(records, key=lambda r: json.dumps(r, sort_keys=True)) == yesterday[name], name
        assert not any(a.derivation.startswith(REGISTRATION_DERIVATION_PREFIX) for a in atoms), name


def test_one_wafer_two_sentences_name_through_one_column_carries_its_attributes(tmp_path):
    """총괄 10-07 ③ (one keying, two roles): lot_slot -> wafer and wafer -> recipe name the wafer
    through the same `wafer` binding - one wafer per row, so its bound attributes are registered."""
    document = _bound(_document())
    target = document["sources"][SOURCE]["bind"]["mappings"][SENTENCE]["bind"]["target"]
    document["sources"][SOURCE]["bind"]["mappings"]["wafer-processed-with-recipe"] = {
        "predicate": "processed_with@1", "bind": {
            "occurred_at": {"kind": "column", "column": "event_time"},
            "subject": copy.deepcopy(target),
            "target": {"kind": "entity", "entity_type": "recipe@1",       # the relation has no recipe column
                       "keys": {"recipe": {"kind": "column", "column": "event_type"}}}}}
    assert setup_bundle.attribute_registrations(document["sources"][SOURCE], document["vocabulary"]) == (
        {SENTENCE: ("target",), "wafer-processed-with-recipe": ("subject",)}, ())
    _setup, atoms = _atoms(tmp_path, document, [_row(i) for i in range(2)])
    assert len([a for a in atoms if a.predicate == "processed_with"]) == 2    # canary: both sentences said
    assert sorted(((r.subject_keys, r.object_payload) for r in _registrations(atoms)), key=str) == [
        ({"wafer": wafer}, {"qualifiers": {"event_type": "track_in"}}) for wafer in ("W000", "W001")]


LOT = {"kind": "column", "column": "parent_lot"}
TWO_KEYINGS = {   # 총괄 10-07 ③: the whole binding, in key order - column, kind and order each split it
    "parent_lot-child_lot": ("lot", {"lot": LOT}, {"lot": {"kind": "column", "column": "child_lot"}}),
    "column-constant": ("lot", {"lot": LOT}, {"lot": {"kind": "constant", "value": "parent_lot"}}),
    "key-order": ("lot_slot", {"lot": LOT, "slot": {"kind": "column", "column": "slot"}},
                  {"slot": {"kind": "column", "column": "slot"}, "lot": LOT}),
}


@pytest.mark.parametrize("entity_type, subject_keys, target_keys", TWO_KEYINGS.values(), ids=TWO_KEYINGS)
def test_a_type_named_through_two_keyings_is_not_registered_and_is_said(caplog, entity_type, subject_keys,
                                                                        target_keys):
    """총괄 10-07 ③: `bind.entities` attributes cannot pick between two entities - not registered,
    one load line; a role's own attributes still are its entity's."""
    declared = f"{entity_type}@1"
    source = {"bind": {
        "entities": {declared: {"attributes": {"event_type": {"kind": "column", "column": "event_type"}}}},
        "mappings": {
            "a": {"predicate": "follows@1", "bind": {
                "subject": {"kind": "entity", "entity_type": declared, "keys": subject_keys},
                "target": {"kind": "entity", "entity_type": declared, "keys": target_keys,
                           "attributes": {"wafer": {"kind": "column", "column": "wafer"}}}}}}}}
    vocabulary = {"follows@1": {"subjects": [declared], "object": {"kind": "entity_ref", "types": [declared]}}}
    registered, unregistered = setup_bundle.attribute_registrations(source, vocabulary)
    assert registered == {"a": ("target",)}
    assert unregistered == ((entity_type, ("a.subject",)),)
    ledger_setup._REGISTRATION_NOTES_ANNOUNCED.clear()
    with caplog.at_level(logging.INFO, logger=ledger_setup.logger.name):
        ledger_setup._announce_registration_notes(
            ledger_setup._registration_notes({"s": source}, vocabulary))
    said = [r.getMessage() for r in caplog.records if "attributes not registered" in r.getMessage()]
    assert len(said) == 1 and f"sources.s names {entity_type} through" in said[0]


def test_a_source_that_declares_the_registration_is_left_to_it():
    source = copy.deepcopy(_document(registered_wafer=True, attribute=True)["sources"][SOURCE])
    vocabulary = _document(registered_wafer=True)["vocabulary"]
    assert setup_bundle.attribute_registrations(source, vocabulary) == ({}, ())


def test_binding_attributes_moves_only_that_sources_fingerprint(tmp_path):
    """총괄 10-07 ④: the plan rides the compiled mapping only when it is not empty, so the one
    source that gains it is the one a deploy re-stamps (and that a rescope would re-translate)."""
    before = _document()
    before["entities"]["wafer@1"]["attributes"] = ["event_type"]          # the same on both sides
    after = _bound(copy.deepcopy(before))
    (tmp_path / "b").mkdir()
    (tmp_path / "a").mkdir()
    old, _index, _ = _service(tmp_path / "b", before).active()
    new, _index, _ = _service(tmp_path / "a", after).active()
    planned = sorted(s for s, plan in new.snapshot.source_plans.items() if plan.runs)
    moved = [s for s in planned if cursor_translator_version(old.snapshot, s)
             != cursor_translator_version(new.snapshot, s)]
    assert len(planned) > 1 and moved == [SOURCE]


def test_a_registration_probe_still_written_loads_and_is_said_to_be_retired(tmp_path, caplog):
    document = _document()
    document["sources"][SOURCE]["read"]["registration_probe"] = [{"entity_type": "wafer@1", "columns": ["wafer"]}]
    setup, _atoms_ = _atoms(tmp_path, document, [_row(0)])
    assert setup.snapshot.source_plans[SOURCE].runs
    ledger_setup._REGISTRATION_NOTES_ANNOUNCED.clear()
    with caplog.at_level(logging.INFO, logger=ledger_setup.logger.name):
        ledger_setup._announce_registration_notes(
            ledger_setup._registration_notes(document["sources"], document["vocabulary"]))
    assert any(f"retired cell: sources.{SOURCE}.read.registration_probe is read by nothing"
               in r.getMessage() for r in caplog.records)


def test_a_registration_whose_subject_has_two_keys_runs_without_a_probe(tmp_path):
    """`registration_context_required` retired (총괄 10-07 ④): no default probe could be derived
    for a two-key subject, so this run used to be refused whole."""
    document = _document()
    document["vocabulary"]["register@1"]["subjects"].append("lot_slot@1")
    document["sources"][SOURCE]["bind"]["mappings"]["slot-registered"] = {"predicate": "register@1", "bind": {
        "occurred_at": {"kind": "column", "column": "event_time"},
        "subject": copy.deepcopy(document["sources"][SOURCE]["bind"]["mappings"][SENTENCE]["bind"]["subject"])}}
    _setup, result = _run(tmp_path, document, [_row(i) for i in range(2)], 2)
    counts = {entry["sentence"]: entry["atoms"] for entry in result["sentences"]}
    assert result["refusal"] is None and counts["slot-registered"] == 2, result


def test_the_test_run_shows_the_registration_as_written(tmp_path):
    _setup, result = _run(tmp_path, _bound(_document()), [_row(i) for i in range(2)], 2)
    made = [e for e in result["atoms_sample"] if e["sentence"].startswith(REGISTRATION_DERIVATION_PREFIX)]
    assert [(e["subject_keys"], e["writes"], e["drop_reason"], e["row_ids"]) for e in made] == [
        ({"wafer": "W000"}, True, None, ["ROW-000"]), ({"wafer": "W001"}, True, None, ["ROW-001"])]


def test_the_boot_restamp_says_which_source_now_registers(tmp_path, monkeypatch, caplog):
    """총괄 10-07 ②: two kinds move on one deploy and an operator must tell them apart - the line
    of a source whose translator now registers attributes says so; any other is a re-stamp only."""
    from chain import ingestion_worker as worker
    from ledger import schema as ledger_schema
    from ledger import store as ledger_store

    document = _bound(_document())
    (tmp_path / "d").mkdir()
    setup, _index, _ = _service(tmp_path / "d", document).active()
    runs = sorted(s for s, plan in setup.snapshot.source_plans.items() if plan.runs)

    class _Store:
        def __init__(self, engine, world=None):
            pass

        restamp_decision = staticmethod(ledger_store.LedgerStore.restamp_decision)

        def connection(self):
            return type("C", (), {"close": lambda self: None})()

        def read_cursor(self, connection, source):
            return {"translator_ver": "ledger-v2:old", "cursor_value": {"row_id": "R1"}}

        def restamp_cursor(self, source, *, expect, translator_ver):
            return True

    monkeypatch.setattr(worker, "_compiled_setup", lambda world: setup)
    monkeypatch.setattr(ledger_store, "LedgerStore", _Store)
    monkeypatch.setattr(ledger_schema, "world_names",
                        lambda *a, **k: type("W", (), {"name": "default"})())
    session = type("S", (), {"get_bind": lambda self: None, "close": lambda self: None})
    with caplog.at_level(logging.INFO):
        worker._restamp_moved_fingerprints_sync(lambda: session())
    said = " | ".join(r.getMessage() for r in caplog.records)
    lines = {source: [part for part in said.split(" | ") if f"{source} (default): " in part]
             for source in runs}
    assert len(runs) > 1 and all(len(found) == 1 for found in lines.values()), lines
    lines = {source: found[0] for source, found in lines.items()}
    assert "registers the bound attributes of wafer" in lines[SOURCE]
    assert not any("registers the bound attributes" in lines[s] for s in runs if s != SOURCE)


# --- PostgreSQL: the ledger itself ------------------------------------------------------------

@pytest.fixture(scope="module", name="ledger_engine")
def fixture_ledger_engine():
    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args, scratch_schema
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    scratch = scratch_schema("assy_pytest_registration")
    with _declared_as_test_database(url):
        built = create_engine(url, poolclass=NullPool, connect_args=scratch_connect_args(scratch))
        admin = create_engine(url, poolclass=NullPool)
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        try:
            store.LedgerStore(built).ensure_schema()
            yield built
        finally:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            built.dispose()
            admin.dispose()


@pytest.mark.pg
def test_the_ledger_keeps_the_declared_time_basis_of_what_it_is_handed(ledger_engine, tmp_path):
    """총괄 10-07: the write side carries `occurred_at_basis` - nothing measured it there. A world-time
    source writes none, an `ingested` one writes its basis, the translator's registration alike."""
    from ledger import schema as ledger_schema

    world = _bound(_document())
    admitted = _bound(_document())
    admitted["sources"][SOURCE]["read"]["occurred_at"] = {"basis": "ingested", "timezone": "Asia/Seoul"}
    rows = [dict(_row(i), created_at=datetime(2026, 10, 7, 1, i, tzinfo=timezone.utc)) for i in range(2)]
    _s, world_atoms = _atoms(tmp_path / "w", world, rows)
    _s, admitted_atoms = _atoms(tmp_path / "i", admitted, rows)
    ledger = store.LedgerStore(ledger_engine)
    raw = ledger_engine.raw_connection()
    try:
        atoms = list(world_atoms) + list(admitted_atoms)
        ledger.ensure_partitions(raw, [a.occurred_at for a in atoms])
        ledger.insert_atoms(raw, atoms)
        raw.commit()
        with raw.cursor() as cursor:
            cursor.execute(f"SELECT id::text, occurred_at_basis FROM {ledger_schema.LEDGER_TABLE}")
            stored = dict(cursor.fetchall())
    finally:
        raw.close()
    assert {stored[str(a.id)] for a in world_atoms} == {None}
    assert {stored[str(a.id)] for a in admitted_atoms} == {"ingested"}
    assert len(stored) == len(atoms) and len(_registrations(atoms)) == 4         # canary


@pytest.mark.pg
def test_a_source_re_stamped_only_keeps_its_position_and_its_atoms(ledger_engine, tmp_path, monkeypatch):
    """총괄 10-07 ②'s gate for the second kind: a source whose fingerprint moved only because the
    probe left the plan - after the boot step its cursor stands where it stood and no row of it
    was translated again."""
    from chain import ingestion_worker as worker
    from ledger import schema as ledger_schema
    from sqlalchemy.orm import Session

    import paths
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))       # no worlds layout of the box's
    document = _document(registered_wafer=True)
    (tmp_path / "r").mkdir()
    setup, _index, _ = _service(tmp_path / "r", document).active()
    names = ledger_schema.world_names()
    raw = ledger_engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute(f"DELETE FROM {names.cursor}")
            cursor.execute(f"INSERT INTO {names.cursor} (source, translator_ver, cursor_value) "
                           f"VALUES (%s, %s, %s)", (SOURCE, "ledger-v2:before-the-probe-left",
                                                    json.dumps({"lot_slot_wafer_key": "K003"})))
            cursor.execute(f"SELECT count(*) FROM {names.ledger}")
            atoms_before = cursor.fetchone()[0]
        raw.commit()
    finally:
        raw.close()
    monkeypatch.setattr(worker, "_compiled_setup", lambda world: setup)
    worker._restamp_moved_fingerprints_sync(lambda: Session(bind=ledger_engine))
    raw = ledger_engine.raw_connection()
    try:
        cursor_row = store.LedgerStore(ledger_engine).read_cursor(raw, SOURCE)
        with raw.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {names.ledger}")
            atoms_after = cursor.fetchone()[0]
    finally:
        raw.close()
    assert cursor_row["translator_ver"] == cursor_translator_version(setup.snapshot, SOURCE)
    assert cursor_row["cursor_value"] == {"lot_slot_wafer_key": "K003"}
    assert atoms_after == atoms_before
