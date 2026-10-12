# -*- coding: utf-8 -*-
"""소유자 10-12 「맵핑에 process - relatedto - (object, quantity, process) 세 개 중 빈 거는 무시」 ·
「선언 아이덴티티가 없다고 하나만 적은 거 안 나오는데」.

A cell only SOME sentences of a source need to name their entities, left blank, leaves only those
sentences unsaid - as a `when` that does not match. A cell every sentence needs (the shared subject),
an `allow_null` entity's key, or any cell of a code mapper's source still refuses the molecule. One
seat: `event_frame.blank_entity_cells`.

The source is the RELEASE_LOG example, read out of the log and run as written.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.backfill import _v2_frame, prepare_v2_cursor_batch               # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.roleframe import dry_run_event_frame, mapper_context              # noqa: E402
from ledger.runtime_v2 import last_cursor, preview_cursor_batch               # noqa: E402
from ledger.setup_bundle import (SETUP_VERSION, require_ready_bundle,         # noqa: E402
                                 validate_bundle, validate_bundle_errors)
from ledger.setup_registry import compile_setup_snapshot                     # noqa: E402
from test_an_entity_type_can_be_read_from_a_column import (                  # noqa: E402,F401
    CANDIDATES, COLUMNS, SOURCE as TYPED_SOURCE, column, document as typed_document,
    fixture_catalog, fixture_shipped, row as typed_row, typed)

SOURCE = "process_links"
RELEASE_LOG = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "process", "RELEASE_LOG.md")
HEADING = "## 2026-10-12 · 원장 선언 — 한 소스의 문장 여럿 중 대상 칸이 빈 문장만 빠진다"
#: The physical half, written here - the deployment's table_config would carry it.
CATALOG = {SOURCE: {"columns": {"row_id": "string", "process_id": "string", "object_id": "string",
                                "quantity_id": "string", "related_process_id": "string",
                                "created_at": "datetime"},
                    "business_key": "row_id"}}
STORED_AT = pd.Timestamp("2026-10-12T01:00:00+00:00")

#: The owner's rows: P1 all filled · P2 NULL / filled / '' · P3 spaces / NULL / filled · P4 all blank.
OWNER_ROWS = [
    {"row_id": "R1", "process_id": "P1", "object_id": "O1", "quantity_id": "Q1", "related_process_id": "PR1"},
    {"row_id": "R2", "process_id": "P2", "object_id": None, "quantity_id": "QB", "related_process_id": ""},
    {"row_id": "R3", "process_id": "P3", "object_id": "  ", "quantity_id": None, "related_process_id": "PC"},
    {"row_id": "R4", "process_id": "P4", "object_id": None, "quantity_id": "", "related_process_id": "  "},
]
SHARED_BLANK = {"row_id": "R5", "process_id": None, "object_id": "O5", "quantity_id": "Q5",
                "related_process_id": "PR5"}


def release_log_source():
    text = open(RELEASE_LOG, encoding="utf-8").read()
    assert HEADING in text, "the RELEASE_LOG entry is gone or renamed"
    return json.loads(re.search(r"```json\n(.*?)\n```", text.split(HEADING, 1)[1], re.S).group(1))


def _document(source=None, allow_null=False):
    out = {
        "setup_version": SETUP_VERSION,
        "vocabulary": {"related_to": {
            "status": "active", "subjects": ["physical_process"],
            "object": {"kind": "entity_ref",
                       "types": ["physical_object", "physical_quantity", "physical_process"],
                       "qualifiers": {"required": [], "optional": []}}}},
        "entities": {"physical_process": {"keys": ["process_id"]},
                     "physical_object": {"keys": ["object_id"]},
                     "physical_quantity": {"keys": ["quantity_id"]}},
        "sources": {SOURCE: source if source is not None else release_log_source()},
    }
    if allow_null:
        out["entities"]["physical_object"]["allow_null"] = True
    return out


def _snapshot(document):
    return compile_setup_snapshot(require_ready_bundle(validate_bundle(document, catalog=CATALOG)),
                                  trusted_implementations(), catalog=CATALOG)


def _preview(document, rows):
    snapshot = _snapshot(document)
    frame = _v2_frame([dict(row, created_at=STORED_AT) for row in rows])
    return preview_cursor_batch(snapshot, SOURCE, frame,
                                last_cursor(snapshot.source_plans[SOURCE], frame),
                                role_mapper_registry(), known_registrations=())


def _edges(preview):
    """process -> sorted (target type, target key) its row said."""
    out = {}
    for atom in preview.candidate_semantics:
        target = atom["object_payload"]
        out.setdefault(atom["subject_keys"]["process_id"], []).append(
            (target["type"], next(iter(target["keys"].values()))))
    return {process: sorted(edges) for process, edges in out.items()}


def _refused(preview):
    return [(refusal.reason, refusal.detail) for refusal in preview.refusals]


def _one_sentence():
    source = release_log_source()
    for sentence in ("process-quantity", "process-process"):
        del source["bind"]["mappings"][sentence]
    return source


# ------------------------------------------------------------------ the owner's source

def test_the_example_loads_through_the_product_validator():
    assert list(validate_bundle_errors(_document(), catalog=CATALOG)) == []


def test_each_row_says_the_edges_its_filled_targets_name():
    preview = _preview(_document(), OWNER_ROWS)

    assert len(_edges(preview).get("P1", ())) == 3, _edges(preview)     # canary: all three say
    assert _edges(preview) == {
        "P1": [("physical_object", "O1"), ("physical_process", "PR1"), ("physical_quantity", "Q1")],
        "P2": [("physical_quantity", "QB")],
        "P3": [("physical_process", "PC")],
    }
    assert _refused(preview) == []


def test_a_row_whose_targets_are_all_blank_writes_nothing_and_is_not_indexed():
    """P4: no atom, no refusal, no `unsaid` line - and no row reference, so the row index never
    names it and `rows_not_yet_translated` keeps counting it."""
    preview = _preview(_document(), OWNER_ROWS)

    assert "P4" not in _edges(preview)
    assert (preview.refusals, dict(preview.unsaid)) == ((), {})
    assert sorted({ref[1] for ref in preview.row_refs}) == ["R1", "R2", "R3"]


def test_a_blank_shared_subject_still_refuses_the_row():
    preview = _preview(_document(), [OWNER_ROWS[0], SHARED_BLANK])

    assert _refused(preview) == [(
        "no_identity", "molecule rows[1] declares 'process_id' and the row at "
                       "event_frame.rows[1].process_id leaves it empty")]
    assert set(_edges(preview)) == {"P1"}


def test_one_sentence_with_a_blank_target_is_refused_as_before():
    preview = _preview(_document(_one_sentence()), OWNER_ROWS[:2])

    assert _refused(preview) == [(
        "no_identity", "molecule rows[1] declares 'object_id' and the row at "
                       "event_frame.rows[1].object_id leaves it empty")]


def test_an_allow_null_target_is_refused_as_before():
    """A column-bound key of an `allow_null` entity was never a null-key atom - the read refused
    the row (measured on the code before this round) - and it still is."""
    preview = _preview(_document(allow_null=True), OWNER_ROWS[:2])

    assert _refused(preview) == [(
        "no_identity", "molecule rows[1] declares 'object_id' and the row at "
                       "event_frame.rows[1].object_id leaves it empty")]
    assert set(_edges(preview)) == {"P1"}


def test_a_code_mappers_source_refuses_as_before():
    """A code mapper says no declared sentence, so there is no sentence to leave unsaid."""
    source = release_log_source()
    source["map"]["implementation_id"] = "dt-job-role"
    snapshot = _snapshot(_document(source))
    refusals = []
    prepare_v2_cursor_batch(snapshot, SOURCE, _v2_frame([dict(row, created_at=STORED_AT)
                                                         for row in OWNER_ROWS]),
                            refusals=refusals)

    assert [refusal.reason for refusal in refusals] == ["no_identity"] * 3


# ------------------------------------------------------------------ a type read from a column

def test_a_typed_target_with_a_blank_key_or_type_unsays_only_its_sentence(shipped, catalog):
    """Two sentences share the typed subject; `leads` reads its target's type and key from
    phenomenon_*, `leads-eqp` from cause_type / dt_eqp. A blank phenomenon key or type leaves
    `leads` unsaid; a blank shared subject key still refuses (`_row_type_refusal`)."""
    source = copy.deepcopy(TYPED_SOURCE)
    source["bind"]["mappings"]["leads-eqp"] = {"predicate": "leads_to@1", "bind": {
        "subject": typed("cause_type", {"quantity": column("cause_key")}),
        "target": typed("cause_type", {"quantity": column("dt_eqp"),
                                       "defect_kind": column("dt_eqp")})}}
    snapshot = compile_setup_snapshot(
        require_ready_bundle(validate_bundle(typed_document(shipped, source), catalog=catalog)),
        trusted_implementations(), catalog=catalog)
    rows = [dict(typed_row(1, "quantity", "q-1", "defect_kind", ""), dt_eqp="q-9"),
            dict(typed_row(2, "quantity", "q-2", "", "d-1"), dt_eqp="q-8"),
            dict(typed_row(3, "quantity", "", "defect_kind", "d-2"), dt_eqp="q-7")]
    frame = _v2_frame([{**{name: r.get(name) for name in COLUMNS}, "created_at": STORED_AT}
                       for r in rows])
    refusals = []
    events = prepare_v2_cursor_batch(snapshot, CANDIDATES, frame, refusals=refusals)
    said = sorted((atom["subject_keys"]["quantity"], atom["object_payload"]["type"],
                   atom["object_payload"]["keys"])
                  for event in events
                  for atom in dry_run_event_frame(mapper_context(snapshot, CANDIDATES), event,
                                                  role_mapper_registry()).ledger_frame.to_dict("records")
                  if atom["predicate"] == "leads_to")

    assert said == [("q-1", "quantity", {"quantity": "q-9"}),
                    ("q-2", "quantity", {"quantity": "q-8"})]
    assert [(r.reason, r.detail) for r in refusals] == [(
        "no_identity", "molecule rows[2]: a row of type 'quantity' needs 'cause_key' and the row at "
                       "event_frame.rows[2].cause_key leaves it empty")]
