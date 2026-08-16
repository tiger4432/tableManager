# -*- coding: utf-8 -*-
"""The joined source -> translator -> vocabulary authoring contract."""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import gate                                                     # noqa: E402
from ledger.backfill import fetch_page                                      # noqa: E402
from ledger.examples.grouped_translator_template import (                  # noqa: E402
    GroupedProcessJobTranslator, group_rows)
from ledger import config as ledger_config                                  # noqa: E402
from ledger.lot_event_translator import (LotEventTranslator,                # noqa: E402
                                         Molecule, group_molecules)
from ledger.observability import probe_source_head                          # noqa: E402
from ledger.source_contract import compile_source                          # noqa: E402
from ledger.translator_pattern import (ClaimDraft, SafeTranslatorTemplate, # noqa: E402
                                       SourceMolecule)
import ledger_admin                                                         # noqa: E402


def lineage_declaration():
    return {
        "kind": "lineage",
        "occurred_at_column": "event_time",
        "occurred_at_format": "%Y-%m-%dT%H:%M:%S",
        "occurred_at_timezone": "Asia/Seoul",
        "subject_types": ["Lot", "Wafer"],
        "register_entity_types": ["Lot", "Wafer"],
        "columns": {},
        "vocabulary": {
            "split": {"lineage": "parent_child",
                      "slot_pairing": "slot_preserving",
                      "emit_has_wafer": True},
            "track_in": {"lineage": "none", "slot_pairing": "none",
                         "emit_has_wafer": True},
        },
    }


def test_lineage_contract_lists_every_possible_claim_not_only_sampled_branches():
    contract = compile_source("lot_event", lineage_declaration())
    assert contract["state"] == "ready"
    assert [row["predicate"] for row in contract["emissions"]] == [
        "register", "has_wafer", "derived_from", "slot_map"]
    slot_map = next(row for row in contract["emissions"]
                    if row["predicate"] == "slot_map")
    assert slot_map["event_types"] == ["split"]
    assert slot_map["vocabulary"]["qualifiers"] == ["from", "to", "wafer"]


def test_lineage_emit_register_false_matches_contract_and_real_translator():
    source = lineage_declaration()
    source["vocabulary"] = {
        "track_in": {"lineage": "none", "slot_pairing": "none",
                     "emit_has_wafer": True, "emit_register": False}}
    contract = compile_source("lot_event", source)
    assert contract["state"] == "ready"
    assert [row["predicate"] for row in contract["emissions"]] == ["has_wafer"]

    row = {
        "row_identity": "r1", "lot": "LOT-1", "event_type": "track_in",
        "parent_lot": None, "child_lot": None, "slots": "1", "wafers": "WF-1",
        "event_time": "2026-08-16T10:00:00",
    }
    molecule = group_molecules([row])[0]
    cfg = {"version": 1, "sources": {"lot_event": source}}
    translator = LotEventTranslator(
        source, ledger_config.translator_version(cfg, "lot_event"),
        ledger_config.declared_derivations(cfg, "lot_event"))
    gate.reset_counters()
    with gate.building_molecule("lot_event"):
        atoms, report = translator.translate(molecule)
    gate.reset_counters()

    assert report["refused"] is False
    assert [atom.predicate for atom in atoms] == ["has_wafer"]


def test_declared_contract_catches_a_signature_conflict_before_a_row_hits_that_rule():
    source = {
        "kind": "declared",
        "occurred_at_basis": "claim_time",
        "subject_types": ["Product"],
        "register_entity_types": ["Product"],
        "columns": {"row_identity": "id"},
        "emit": [{
            "rule": "bad_subject",
            "predicate": "observed",
            "class": "observation",
            "subject": {"type": "Product", "keys": {"product": "$product"}},
            "object": {"kind": "value", "payload": {
                "finding_kind": "void", "method": "map", "run_uid": "$run"}},
        }],
    }
    contract = compile_source("product_registry", source)
    assert contract["state"] == "incompatible"
    assert len(contract["issues"]) == 1
    issue = contract["issues"][0]
    assert issue["code"] == "subject_signature_mismatch"
    assert issue["predicate"] == "observed"
    assert issue["configured_by"] == "emit[0]"
    assert "Product" in issue["detail_ko"] and "vocabulary" in issue["detail_ko"]


def test_declared_contract_resolves_a_legal_recipe_parameter_signature():
    source = {
        "kind": "declared", "occurred_at_basis": "claim_time",
        "subject_types": ["Recipe"], "register_entity_types": ["Recipe"],
        "columns": {"row_identity": "id"},
        "emit": [{
            "rule": "parameter_row", "predicate": "has_param",
            "class": "observation",
            "subject": {"type": "Recipe",
                        "keys": {"recipe": "$recipe", "rev": "$rev"}},
            "object": {"kind": "value", "payload": {
                "param": "$name", "value": "$value", "unit": "$unit"}},
        }],
    }
    contract = compile_source("recipe_params", source)
    assert contract["state"] == "ready"
    assert {row["predicate"] for row in contract["emissions"]} == {
        "register", "has_param"}


def test_admin_save_gate_rejects_translator_vocabulary_conflict_before_dry_run(
        monkeypatch):
    source = {
        "kind": "declared",
        "occurred_at_column": "created_at",
        "occurred_at_format": "%Y-%m-%dT%H:%M:%S",
        "occurred_at_timezone": "Asia/Seoul",
        "occurred_at_basis": "claim_time",
        "subject_types": ["Product"],
        "register_entity_types": ["Product"],
        "watermark": {"columns": ["updated_at", "id"]},
        "columns": {"row_identity": "id"},
        "emit": [{
            "rule": "bad_subject", "predicate": "observed",
            "class": "observation",
            "subject": {"type": "Product", "keys": {"product": "$product"}},
            "object": {"kind": "value", "payload": {
                "finding_kind": "void", "method": "map", "run_uid": "$run"}},
        }],
    }
    columns = {"created_at", "updated_at", "id", "product", "run"}
    monkeypatch.setattr(ledger_admin, "declared_tables", lambda: ["product_registry"])
    monkeypatch.setattr(ledger_admin, "relation_columns", lambda _db, _name: columns)

    violations = ledger_admin.check_source_declaration(
        object(), "product_registry", source)
    assert [v["code"] for v in violations] == ["translator_vocabulary_mismatch"]
    assert violations[0]["field"] == "emit[0]"
    assert "Product" in violations[0]["detail_ko"]


def process_config():
    return {
        "occurred_at_column": "event_time",
        "occurred_at_format": "%Y-%m-%dT%H:%M:%S",
        "occurred_at_timezone": "Asia/Seoul",
        "register_entity_types": ["Wafer"],
    }


def test_copyable_grouped_template_only_needs_domain_claim_code():
    rows = [
        {"row_identity": "r1", "job_id": "J1", "event_time": "2026-08-16T10:00:00",
         "wafer": "WF-1", "step": "BOND", "recipe": "R1", "equipment": "EQ-1"},
        {"row_identity": "r2", "job_id": "J1", "event_time": "2026-08-16T10:00:00",
         "wafer": "WF-2", "step": "BOND", "recipe": "R1", "equipment": "EQ-1"},
    ]
    molecule = group_rows("process_log", rows)[0]
    translator = GroupedProcessJobTranslator(
        "process_log", process_config(), "process_log/1/rules:abc",
        {"first_sight", "job_row_observation"})
    gate.reset_counters()
    with gate.building_molecule("process_log"):
        atoms, report = translator.translate(molecule)
    gate.reset_counters()

    assert report["refused"] is False
    assert [atom.predicate for atom in atoms] == [
        "register", "processed_with", "register", "processed_with"]
    assert all(atom.source_who == "process_log" for atom in atoms)
    assert atoms[1].source_raw_ref == 'process_log:["r1"]'
    assert atoms[1].object_payload == {
        "step": "BOND", "recipe": "R1", "equipment": "EQ-1"}


class _LateRefusalTranslator(SafeTranslatorTemplate):
    def claim_drafts(self, molecule, occurred_at):
        yield ClaimDraft("processed_with", "Wafer", {"wafer": "WF-1"}, "rule",
                         "value", {"step": "BOND", "recipe": "R1"})
        self.refuse(gate.REFUSE_ATOMICITY, "second half is inconsistent")


def test_template_materialises_claims_before_registration_so_late_refusal_leaks_nothing():
    molecule = SourceMolecule(
        "custom_source", "J1", [{"row_identity": "r1"}],
        datetime(2026, 8, 16, 10, 0, 0))
    translator = _LateRefusalTranslator(
        "custom_source", process_config(), "v1", {"first_sight", "rule"})
    gate.reset_counters()
    with gate.building_molecule("custom_source"):
        atoms, report = translator.translate(molecule)
    gate.reset_counters()

    assert atoms is None and report["refused"] is True
    assert translator.registered == set()


class _Cursor:
    def __init__(self, *, rows=(), one=None):
        self.rows = list(rows)
        self.one = one
        self.calls = []
        self.description = [(name,) for name in (
            "row_identity", "lot", "event_type", "parent_lot", "child_lot",
            "slots", "wafers", "event_time")]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def test_unstarted_timestamp_cursor_does_not_compare_timestamptz_to_empty_text():
    happened = datetime(2026, 8, 16, 10, 0, 0)
    cursor = _Cursor(rows=[("r1", "LOT-1", "track_in", None, None,
                            "1", "WF-1", happened)])
    connection = _Connection(cursor)
    columns = {
        "event_time_column": "event_time", "row_identity": "id", "lot": "lot",
        "event_type": "event", "parent_lot": "parent", "child_lot": "child",
        "slots": "slots", "wafers": "wafers",
    }

    rows = fetch_page(connection, "source_table", columns, None, 20)
    sql, params = cursor.calls[0]
    assert "WHERE event_time > %s" not in sql
    assert params == (20,)
    assert rows[0]["event_time"] == happened
    assert "2026-08-16T10:00:00" in Molecule(
        "track_in", happened, None, "LOT-1").ref


def test_unstarted_lag_probe_counts_all_rows_and_serialises_datetime_head():
    happened = datetime(2026, 8, 16, 10, 0, 0)
    cursor = _Cursor(one=(happened, 31))
    connection = _Connection(cursor)

    class Store:
        def connection(self):
            return connection

    head, behind = probe_source_head(
        Store(), "source_table", {"occurred_at_column": "event_time"}, None)
    sql, params = cursor.calls[0]
    assert "FILTER" not in sql and "count(*)" in sql
    assert params is None
    assert head == "2026-08-16T10:00:00" and behind == 31
    assert connection.closed is True
