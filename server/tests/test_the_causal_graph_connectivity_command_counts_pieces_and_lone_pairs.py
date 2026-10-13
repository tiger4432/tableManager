# -*- coding: utf-8 -*-
"""총괄 d7a27a758 「잼」: `scripts/causal_graph_connectivity.py --predicate <name> [--world]`, read only - nodes ·
links · pieces · the largest piece's share · lone pairs (a link neither end of which touches another node).

  the fixture        a -> b -> c -> d (a -> b said twice) · e -> f · g -> h · x -> y under another predicate
  the answer         8 nodes · 5 links · 3 pieces · largest 4 (50.0 %) · 2 lone pairs (40.0 %)
  PostgreSQL         the same numbers read from a scratch ledger, and the command's lines over a read-only connection
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from scripts import causal_graph_connectivity as connectivity            # noqa: E402
from tests.test_ledger_trace_pg import ledger_engine                       # noqa: E402,F401 - the shipped ledger schema

LINKS = [("a", "b", "leads_to"), ("a", "b", "leads_to"), ("b", "c", "leads_to"), ("c", "d", "leads_to"),
         ("e", "f", "leads_to"), ("g", "h", "leads_to"), ("x", "y", "part_of")]
ANSWER = {"nodes": 8, "links": 5, "pieces": 3, "largest": 4, "lone": 2}
LINES = ["nodes          8", "links          5", "pieces         3",
         "largest piece  4 nodes - 50.0 % of the nodes", "lone pairs     2 - 40.0 % of the links"]


def test_three_pieces_and_two_lone_pairs():
    asked = sorted({(cause, effect) for cause, effect, predicate in LINKS if predicate == "leads_to"})
    assert connectivity.connectivity(asked) == ANSWER
    assert connectivity.said(ANSWER) == LINES


def test_a_link_both_ways_and_a_loop_are_not_lone():
    assert connectivity.connectivity([("a", "b"), ("b", "a"), ("c", "c")]) == {
        "nodes": 3, "links": 3, "pieces": 2, "largest": 2, "lone": 2}, "a <-> b: two links, each a lone pair"
    assert connectivity.connectivity([]) == {"nodes": 0, "links": 0, "pieces": 0, "largest": 0, "lone": 0}
    assert connectivity.said(connectivity.connectivity([]))[-1] == "lone pairs     0 - - of the links"


def _rows():
    return [{"id": str(uuid.UUID(int=n)), "st": "thing", "sk": json.dumps({"key": cause}), "p": predicate,
             "ok": "entity_ref", "op": json.dumps({"type": "thing", "keys": {"key": effect}}),
             "oa": datetime(2026, 5, 1, tzinfo=timezone.utc), "who": "t", "ver": "v1", "raw": "row:%d" % n, "sup": None}
            for n, (cause, effect, predicate) in enumerate(LINKS, 1)]


@pytest.mark.pg
def test_the_command_reads_the_same_numbers_from_the_ledger(ledger_engine, monkeypatch, capsys):
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    import db_safety
    from tests.test_ledger_trace_pg import insert

    with ledger_engine.begin() as conn:
        schema = conn.execute(text("SELECT current_schema()")).scalar()
        assert schema != "public"
        conn.execute(text("TRUNCATE ledger_events"))
        insert(conn, _rows())
    try:
        with ledger_engine.connect() as conn:
            assert connectivity.connectivity(connectivity.read_links(conn, "ledger_events", ["leads_to"])) == ANSWER
        monkeypatch.setattr(db_safety, "open_readonly_engine", lambda **_kw: create_engine(
            ledger_engine.url, poolclass=NullPool,
            connect_args={"options": "%s -csearch_path=%s,public" % (db_safety.READONLY_OPTIONS, schema)}))
        connectivity.main(["--predicate", "leads_to"])
    finally:
        with ledger_engine.begin() as conn:
            conn.execute(text("TRUNCATE ledger_events"))
    assert capsys.readouterr().out.splitlines() == ["predicates     leads_to", "worlds         (operating)"] + LINES
