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

from ledger import backfill                                                  # noqa: E402
from ledger.backfill import _v2_frame, prepare_v2_cursor_batch               # noqa: E402
from ledger.event_frame import named_columns                                 # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.roleframe import dry_run_event_frame, mapper_context              # noqa: E402
from ledger.runtime_v2 import last_cursor, preview_cursor_batch               # noqa: E402
from ledger.setup_bundle import (SETUP_VERSION, require_ready_bundle,         # noqa: E402
                                 validate_bundle, validate_bundle_errors)
from ledger.setup_registry import compile_setup_snapshot                     # noqa: E402
from test_a_condition_can_say_is_not import _Engine                          # noqa: E402
from test_an_entity_type_can_be_read_from_a_column import (                  # noqa: E402,F401
    CANDIDATES, COLUMNS, SOURCE as TYPED_SOURCE, column, document as typed_document,
    fixture_catalog, fixture_shipped, row as typed_row, typed)

SOURCE = "process_links"
RELEASE_LOG = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "process", "RELEASE_LOG.md")
HEADING = "## 2026-10-12 · 원장 선언 — 한 소스의 문장 여럿 중 대상 칸이 빈 문장만 빠진다"
#: The physical half, written here - the deployment's table_config would carry it.
CATALOG = {SOURCE: {"columns": {"row_id": "string", "process_id": "string", "object_id": "string",
                                "quantity_id": "string", "related_process_id": "string",
                                "kind": "string", "event_at": "datetime", "created_at": "datetime"},
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


# ------------------------------------------------------------------ a group (총괄 10-12 QA ①)

def test_a_group_skips_a_sentence_only_when_its_cell_is_blank_in_every_row():
    """A cell blank in some rows of a group and filled in others refuses the group, whichever row
    is first - the filled value is not dropped in silence. Blank in every row: that sentence only."""
    source = release_log_source()
    source["read"] = {"unit": "group", "identity": ["process_id"], "group_by": ["process_id"],
                      "order_by": ["row_id"]}
    rows = [
        {"row_id": "R1", "process_id": "P1", "object_id": None, "quantity_id": "Q1", "related_process_id": "PR1"},
        {"row_id": "R2", "process_id": "P1", "object_id": "O1", "quantity_id": "Q1", "related_process_id": "PR1"},
        {"row_id": "R3", "process_id": "P2", "object_id": "O2", "quantity_id": "Q2", "related_process_id": "PR2"},
        {"row_id": "R4", "process_id": "P2", "object_id": "", "quantity_id": "Q2", "related_process_id": "PR2"},
        {"row_id": "R5", "process_id": "P3", "object_id": None, "quantity_id": "Q3", "related_process_id": "PR3"},
        {"row_id": "R6", "process_id": "P3", "object_id": " ", "quantity_id": "Q3", "related_process_id": "PR3"},
    ]
    preview = _preview(_document(source), rows)

    assert _edges(preview) == {"P3": [("physical_process", "PR3"), ("physical_quantity", "Q3")]}
    assert [(r.reason, "'object_id'" in r.detail, r.addresses[0]["path"]) for r in preview.refusals] == [
        ("no_identity", True, "event_frame.rows[0].object_id"),
        ("no_identity", True, "event_frame.rows[3].object_id")]


# ------------------------------------------------------------------ sentences a `when` gates (QA ②)

def _gated():
    """`process-object` is said when kind = obj, `process-quantity` when kind = qty."""
    source = release_log_source()
    mappings = source["bind"]["mappings"]
    del mappings["process-process"]
    mappings["process-object"]["when"] = {"kind": "obj"}
    mappings["process-quantity"]["when"] = {"kind": "qty"}
    return source


#: W2 the one applying sentence's target blank · W4 the other sentence's target blank ·
#: W5 no sentence applies, both blank.
GATED_ROWS = [
    {"row_id": "W2", "process_id": "P2", "kind": "obj", "object_id": None, "quantity_id": "Q2"},
    {"row_id": "W4", "process_id": "P4", "kind": "obj", "object_id": "O4", "quantity_id": None},
    {"row_id": "W5", "process_id": "P5", "kind": "other", "object_id": None, "quantity_id": ""},
]


def test_only_the_sentences_whose_when_holds_decide_what_every_one_needs():
    """W2: one sentence applies, so it is a one-sentence source - its blank target refuses, as
    before. W4: the blank cell is another sentence's, which does not apply. W5: no sentence applies,
    so nothing is refused and the row is counted under the `when` it passed by."""
    preview = _preview(_document(_gated()), GATED_ROWS)

    assert _edges(preview) == {"P4": [("physical_object", "O4")]}
    assert _refused(preview) == [(
        "no_identity", "molecule rows[0] declares 'object_id' and the row at "
                       "event_frame.rows[0].object_id leaves it empty")]
    assert dict(preview.unsaid) == {(("kind", "other"),): 1}


# ------------------------------------------------------------------ the census (QA ④)

def _census(document, rows, monkeypatch):
    snapshot = _snapshot(document)
    columns = named_columns(snapshot.source_plans[SOURCE])
    assert "process_id" in columns                                    # canary: declared columns read
    ids = [row["row_id"] for row in rows]
    monkeypatch.setattr(backfill, "rows_missing_from_the_index", lambda *a, **k: ids)
    fetched = [tuple(dict(row, created_at=STORED_AT).get(c) for c in columns) for row in rows]
    return backfill.rows_not_yet_translated(_Engine([len(rows), 0], fetched),
                                            type("S", (), {"snapshot": snapshot})(), SOURCE)


def test_the_census_takes_out_a_row_that_says_no_sentence_and_keeps_a_refused_one(monkeypatch):
    """P4 (every target blank) and W5 (no `when` holds) say nothing and are never indexed; the
    refused rows (a blank shared subject, W2) stay «not yet» - a refusal is something to fix."""
    owner = _census(_document(), OWNER_ROWS + [SHARED_BLANK], monkeypatch)
    gated = _census(_document(_gated()), GATED_ROWS, monkeypatch)

    assert (owner.get("excluded_rows"), owner.get("said_nothing_rows"), owner["not_yet"]) == (None, 1, 4)
    assert (gated.get("said_nothing_rows"), gated["not_yet"]) == (1, 2)


# ------------------------------------------------------------------ the read's time (QA ⑤)

def test_a_blank_time_cell_refuses_even_where_one_sentence_alone_keys_by_it():
    """The read's time is never «some sentences'» cell: blank, it refuses as before. (The read's
    identity never gets here - a blank one stops the page in `_validate_base_frame`.)"""
    source = release_log_source()
    source["read"] = {"occurred_at": {"column": "event_at", "timezone": "UTC"}}
    source["bind"]["mappings"]["process-object"]["bind"]["target"]["keys"]["object_id"]["column"] = "event_at"
    preview = _preview(_document(source), [dict(OWNER_ROWS[0], event_at=None)])

    assert _refused(preview) == [(
        "no_identity", "molecule rows[0] declares 'event_at' and the row at "
                       "event_frame.rows[0].event_at leaves it empty")]
