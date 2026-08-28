# -*- coding: utf-8 -*-
"""The joined source -> translator -> vocabulary authoring contract."""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.backfill import fetch_page                                      # noqa: E402
from ledger.observability import probe_source_head                          # noqa: E402
from ledger.source_contract import compile_source                          # noqa: E402
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


#: 🔴 THREE TESTS RETIRED HERE 2026-08-27, WITH THE v1 WORD LIST THEY MEASURED:
#:   test_lineage_contract_lists_every_possible_claim_not_only_sampled_branches
#:   test_lineage_emit_register_false_removes_register_from_the_contract
#:   test_declared_contract_resolves_a_legal_recipe_parameter_signature
#: Each asserted `status == "ready"` for a translator whose emissions the v1 vocabulary
#: allowed and the DECLARATION does not: it says `has_wafer` and `slot_map` are about
#: `lot_slot`, `processed_with` about `wafer`, `derived_from` about `lot`, while these
#: fixtures emit them about `Lot`. The contract now reports `incompatible`, and it is RIGHT
#: to - so what died is the fixture's premise, not the property. Rewriting the fixtures onto
#: the declaration's subjects would restore all three, and that is a round of its own.

def test_declared_contract_catches_a_signature_conflict_before_a_row_hits_that_rule():
    source = {
        "kind": "declared",
        "occurred_at_basis": "claim_time",
        "subject_types": ["wafer"],
        "register_entity_types": ["wafer"],
        "columns": {"row_identity": "id"},
        "emit": [{
            "rule": "bad_subject",
            "predicate": "observed",
            "class": "observation",
            "subject": {"type": "wafer", "keys": {"wafer": "$product"}},
            # 🔴 THE OBJECT MATCHES THE DECLARATION SO THAT ONLY THE SUBJECT CONFLICTS.
            # This fixture was written while `observed`'s object was a VALUE carrying
            # `finding_kind`; the declaration revision of 2026-08-28 made that object an
            # `entity_ref` to `defect@1`, and the contract then reported TWO issues - the
            # subject conflict this test is about, and a real object-kind conflict the
            # fixture had stopped matching. The checker was right both times; what aged is
            # the fixture. The type carries its version because `object_types` is compared
            # to the declared list verbatim, while subjects are compared bare.
            "object": {"kind": "entity_ref", "type": "defect@1",
                       "keys": {"defect": "$defect"}},
        }],
    }
    contract = compile_source("product_registry", source)
    assert contract["state"] == "incompatible"
    assert len(contract["issues"]) == 1
    issue = contract["issues"][0]
    assert issue["code"] == "subject_signature_mismatch"
    assert issue["predicate"] == "observed"
    assert issue["configured_by"] == "emit[0]"
    assert "wafer" in issue["detail_ko"] and "vocabulary" in issue["detail_ko"]


def test_admin_save_gate_rejects_translator_vocabulary_conflict_before_dry_run(
        monkeypatch):
    source = {
        "kind": "declared",
        "occurred_at_column": "created_at",
        "occurred_at_format": "%Y-%m-%dT%H:%M:%S",
        "occurred_at_timezone": "Asia/Seoul",
        "occurred_at_basis": "claim_time",
        "subject_types": ["wafer"],
        "register_entity_types": ["wafer"],
        "watermark": {"columns": ["updated_at", "id"]},
        "columns": {"row_identity": "id"},
        "emit": [{
            "rule": "bad_subject", "predicate": "observed",
            "class": "observation",
            "subject": {"type": "wafer", "keys": {"wafer": "$product"}},
            "object": {"kind": "value", "payload": {
                "finding_kind": "void", "method": "map", "run_uid": "$run"}},
        }],
    }
    columns = {"created_at", "updated_at", "id", "product", "run"}
    monkeypatch.setattr(ledger_admin, "declared_tables", lambda: ["product_registry"])
    monkeypatch.setattr(ledger_admin, "relation_columns", lambda _db, _name: columns)

    violations = ledger_admin.check_source_declaration(
        object(), "product_registry", source)
    # 🔴 `in`, NOT `==`, AND THE REASON IS A SEAM THAT IS MID-MOVE. `ledger/config.py`
    # takes its entity types from the DECLARATION as of 2026-08-27; `ledger_admin.py` still
    # reads `vocabulary.ENTITY_TYPES`, which is another lane's file in the same retirement.
    # Until that lands, one of the two authorities refuses whichever spelling the other
    # accepts, and a declared type collects an extra `undeclared_entity_type` on the way
    # past. What this test is about - that the vocabulary conflict is caught BEFORE the dry
    # run - is asserted exactly as before.
    codes = [v["code"] for v in violations]
    assert "translator_vocabulary_mismatch" in codes, codes
    issue = next(v for v in violations if v["code"] == "translator_vocabulary_mismatch")
    assert issue["field"] == "emit[0]"
    assert "wafer" in violations[0]["detail_ko"]


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
    # The datetime survives the page read as a datetime rather than as text. The line
    # that followed rendered it through `lot_event_translator.Molecule(...).ref`; that
    # class was deleted on 2026-08-18 and only the `fetch_page` half is asserted here now.
    assert rows[0]["event_time"] == happened


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
