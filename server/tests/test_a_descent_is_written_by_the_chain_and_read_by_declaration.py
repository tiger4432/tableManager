# -*- coding: utf-8 -*-
"""A lot's descent is computed by the chain and read by the ledger as a declaration
(총괄 e14416950, owner 10-01 「준비기는 ㄱ으로」).

    운영에서는 체인 규칙 lot_event_to_lot_lineage 가 lot_lineage 에 계보 한 행씩 쓰고,
    원장 소스 lot_lineage 의 bind 에 derived_from 을 적으면 됩니다.

The pairing of a split's two rows was the ledger preparer's job; here each row names its own
descent and both rows of a pair land on the same lineage row.
"""
import copy
import json
import logging
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.implementations import (                                     # noqa: E402
    role_mapper_registry, trusted_implementations)
from ledger.runtime_v2 import preview_cursor_batch                       # noqa: E402
from ledger.setup_bundle import (                                        # noqa: E402
    load_physical_catalog, require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot                 # noqa: E402
from mappers import lot_lineage_mapper                                   # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
T1, T2 = "2026-01-01T10:00:00", "2026-01-02T10:00:00"


def _shipped(name):
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as fh:
        return json.load(fh)


#: The mapper names no column of its own (총괄 0cb2ab958), so it runs on the rule that ships.
RULE = next(rule for rule in _shipped("chain_rules.json.sample")["rules"]
            if rule.get("name") == "lot_event_to_lot_lineage")


@pytest.fixture(autouse=True)
def lineage_table_declared(monkeypatch):
    """The target's declaration as it ships: the mapper reads its key column there."""
    from database import crud
    monkeypatch.setitem(crud.TABLE_CONFIG, "lot_lineage",
                        _shipped("table_config.json.sample")["lot_lineage"])


def row(lot, event_type, time, parent=None, child=None):
    return {"data": {"lot_id": lot, "event_type": event_type, "event_time": time,
                     "parent_lot": parent, "child_lot": child}}


def lineage(payloads, rule=RULE):
    return [u["updates"] for u in
            lot_lineage_mapper.build_lot_lineage_rows(None, payloads, rule)["updates"]]


# ------------------------------------------------------------------- the chain's half

def test_the_two_rows_of_a_split_write_one_descent_row():
    rows = lineage([row("P1", "split", T1, child="C1"), row("C1", "split", T1, parent="P1")])

    assert {r["lot_lineage_key"] for r in rows} == {f"P1|C1|split|{T1}"}
    assert {(r["parent_lot"], r["child_lot"], r["event_type"]) for r in rows} == {
        ("P1", "C1", "split")}


def test_half_a_pair_already_says_its_descent():
    assert [(r["parent_lot"], r["child_lot"]) for r in lineage(
        [row("M1", "merge", T2, parent="P9")])] == [("P9", "M1")]


def test_a_row_naming_no_relative_writes_nothing():
    assert lineage([row("L1", "track_in", T1)]) == []


def test_an_old_generation_row_writes_nothing_and_is_counted_on_one_line(caplog):
    """Owner 08-21 「옛 세대는 버린다」: a row with no lot cannot be one end of a descent."""
    with caplog.at_level(logging.INFO, logger="Mappers.LotLineage"):
        rows = lineage([row("", "split", T1, parent="P1"), row(None, "split", T1, child="C1"),
                        row("C2", "split", T1, parent="P2")])

    assert [(r["parent_lot"], r["child_lot"]) for r in rows] == [("P2", "C2")]
    said = [r.getMessage() for r in caplog.records]
    assert len(said) == 1 and said[0].startswith("[Chain] lot_lineage: 2 row(s)"), said


def test_a_row_naming_both_a_parent_and_a_child_is_refused_by_name():
    with pytest.raises(lot_lineage_mapper.DescentRefused, match="name both parent_lot and child_lot"):
        lineage([row("L1", "split", T1, parent="P1", child="C1")])


def test_the_columns_are_the_rules_to_name():
    payload = {"data": {"lot": "C1", "kind": "split", "at": T1, "up": "P1", "down": None}}
    rule = copy.deepcopy(RULE)
    rule["params"].update({"lot_column": "lot", "parent_column": "up", "child_column": "down",
                           "time_column": "at", "event_type_column": "kind"})

    assert [(r["parent_lot"], r["child_lot"]) for r in lineage([payload], rule)] == [("P1", "C1")]


# ------------------------------------------------------------------- the ledger's half

@pytest.fixture(scope="module")
def sample_snapshot():
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    return compile_setup_snapshot(
        require_ready_bundle(validate_bundle(document, catalog=catalog)),
        trusted_implementations(), catalog=catalog)


def test_the_sample_reads_derived_from_from_the_lineage_table_only(sample_snapshot):
    said = {name: {m.predicate_id for m in plan.profile.mappings.values()}
            for name, plan in sample_snapshot.source_plans.items() if plan.runs}

    assert said["lot_lineage"] == {"derived_from"}
    assert [name for name, predicates in said.items() if "derived_from" in predicates] == [
        "lot_lineage"]


def test_a_lineage_row_of_a_split_or_a_merge_is_a_descent_and_no_other_kind_is(sample_snapshot):
    """Only a split and a merge said a descent before (the retired mapper's own rule); the
    sample now says so as two `when`s rather than in code."""
    def at(text):
        return pd.Timestamp(text).tz_localize("Asia/Seoul")

    lineage_rows = lineage([row("C1", "split", T1, parent="P1"),
                            row("P2", "merge", T2, child="M2"),
                            row("X1", "rework", T2, parent="X0")])
    frame = pd.DataFrame([{**r, "row_id": f"R{i}", "event_time": at(r["event_time"])}
                          for i, r in enumerate(lineage_rows)])
    preview = preview_cursor_batch(
        sample_snapshot, "lot_lineage", frame,
        {"event_time": frame.iloc[-1]["event_time"],
         "lot_lineage_key": frame.iloc[-1]["lot_lineage_key"]},
        role_mapper_registry(), known_registrations=())

    assert sorted((a["predicate"], a["subject_keys"]["lot"],
                   a["object_payload"]["keys"]["lot"]) for a in preview.candidate_semantics) == [
        ("derived_from", "C1", "P1"), ("derived_from", "M2", "P2")]


def test_the_old_and_the_new_atom_of_one_descent_walk_as_one_edge():
    """Lead 0cb2ab958 (duplicates 나): the retired source's atoms stay, so after the lineage
    source translates, one descent has two atoms. The walk merges them into ONE edge - and
    that edge carries ONE of them (`claim_id` / `source_who` / `basis`): the first fetched,
    newest instant first, the atom id breaking a tie. The other is not in the response."""
    import uuid
    from datetime import datetime, timezone
    from ledger import explorer
    from ledger_api import ledger_subgraph

    when = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)

    def atom(number, who):
        return ledger_subgraph.EvidenceAtom(
            id=str(uuid.UUID(int=number)), subject_type="lot", subject_keys={"lot": "C1"},
            predicate="derived_from", object_kind="entity_ref",
            object_payload={"type": "lot", "keys": {"lot": "P1"}}, occurred_at=when,
            source_who=who, source_translator_ver="v1", source_raw_ref="row:%d" % number,
            supersedes=None, source_event_id=str(uuid.UUID(int=900 + number)),
            source_event_state="source_molecule")

    body = ledger_subgraph.subgraph(
        explorer.entity_id("lot", {"lot": "C1"}),
        ledger_subgraph.InMemoryEvidenceLookup([atom(1, "lot_event"), atom(2, "lot_lineage")]),
        hops=1)

    assert len(body["edges"]) == 1, "two atoms of one descent are one edge"
    assert body["edges"][0]["source_who"] in {"lot_event", "lot_lineage"}
