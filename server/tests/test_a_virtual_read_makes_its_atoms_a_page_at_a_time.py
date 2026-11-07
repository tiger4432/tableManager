# -*- coding: utf-8 -*-
"""Lead 11-07 (ㄱ, no SQL time expression): a virtual read reads each row's instant by the translator's own function
(`Leg.moment`), orders the rows newest first in Python, and makes their atoms a page at a time until the rules keep
`limit` (`VirtualEvidenceLookup.claims_for_entities`). The answer is the double's over every atom made at once.

  pages     every limit, current or every fact, with and without a window: the same atoms, the same «not current»,
            the same cut and the same interval count - a subject's later fact on an earlier page than its earlier one
  times     a time PostgreSQL reads that is not ISO takes its place in the order; a time nothing reads leaves its row
            alone out, counted (PostgreSQL)
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import sql_translate                                    # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402

KEY = {"column": "wafer_id", "declared": None, "kind": "text", "zone": None}
T0 = datetime(2026, 9, 30, tzinfo=timezone.utc)


def _leg():
    plan = SimpleNamespace(source_id="src", relation="wafer_process", profile=None,
                           driver=SimpleNamespace(occurred_at=SimpleNamespace(column="at", timezone="UTC", format=None),
                                                  order_by=("row_id",)))
    return sql_translate.Leg(plan, "made-with", "processed_with",
                             {"outgoing": ("wafer", {"wafer": KEY}),
                              "incoming": ("recipe", {"recipe": {**KEY, "column": "recipe_id"}})},
                             {}, [KEY], [], None, "v1", {}, [])


def _reader(leg, rows, connection=None, **kw):
    """A reader whose `_execute` answers a leg's read from `rows` by its key columns; and the rows it made."""
    reader = ledger_subgraph.VirtualEvidenceLookup(connection, [leg], worlds=(SimpleNamespace(name="default"),), **kw)
    cells, made, maker = leg.cells(), [], reader._made

    def execute(sql, params):
        column = re.search(r'w\."(\w+)" = ANY', sql).group(1)
        held = set(params["k_0"])
        return [tuple(row[cell] for cell in cells) for row in rows if row[column] in held][:params["guard"]]

    def counting(timed):
        made.extend(each[0][2] for each in timed)
        return maker(timed)
    reader._execute, reader._made = execute, counting
    return reader, made


def _double(leg, rows, **kw):
    """The answer's measure: `InMemoryEvidenceLookup` over every row's atom, made at once."""
    reader, _made = _reader(leg, rows)
    atoms = reader._atoms(leg, [tuple(row[cell] for cell in leg.cells()) for row in rows])
    return ledger_subgraph.InMemoryEvidenceLookup(atoms, **kw)


def _said(answer):
    atoms, over = answer
    return [(str(atom.id), atom.not_current) for atom in atoms], over


# six wafers ran recipe R0 early; four ran R1 later, so their R0 fact is not current - and the later facts, newer, are
# made on the pages before; six more R0 facts, older still, so the pages stop before the oldest
ROWS = ([{"row_id": n, "wafer_id": "W%d" % n, "recipe_id": "R0", "at": T0 + timedelta(minutes=10 + n)}
         for n in range(1, 7)]
        + [{"row_id": 10 + n, "wafer_id": "W%d" % n, "recipe_id": "R1", "at": T0 + timedelta(minutes=50 + n)}
           for n in range(1, 5)]
        + [{"row_id": 20 + n, "wafer_id": "W%d" % (n % 6 + 1), "recipe_id": "R0", "at": T0 + timedelta(minutes=n)}
           for n in range(1, 7)]
        + [{"row_id": 20 + n, "wafer_id": "W%d" % n, "recipe_id": "R0", "at": T0 + timedelta(minutes=17)}
           for n in range(7, 10)])     # newest R0, one instant: their content orders them - W9 first, read last
ASKED = [("recipe", {"recipe": "R0"})]
WINDOWS = [{}, {"since": "2026-09-30T00:12:00+00:00"}, {"until": "2026-09-30T00:14:00+00:00"}]


def test_a_read_made_a_page_at_a_time_is_the_read_made_at_once(monkeypatch):
    monkeypatch.setattr(ledger_subgraph, "READ_GUARD_FACTOR", len(ROWS))     # no read is cut: the double reads all
    leg, stopped, flagged = _leg(), 0, 0
    for window in WINDOWS:
        for current_only in (True, False):
            for limit in range(1, len(ROWS) + 2):
                kw = dict(one=("processed_with",), current_only=current_only)
                reader, made = _reader(leg, ROWS, **window, **kw)
                double = _double(leg, ROWS, **{k: reader.since if k == "since" else reader.until for k in window}, **kw)
                said = _said(reader.claims_for_entities(ASKED, "incoming", limit))
                case = (window, current_only, limit)
                assert said == _said(double.claims_for_entities(ASKED, "incoming", limit)), case
                assert reader.interval_excluded == double.interval_excluded, case
                pool = len(_reader(leg, ROWS, **window, **kw)[0]._pool(ASKED, "incoming", limit)[0])
                stopped += len(reader.atoms) < pool
                flagged += any(not_current for _row, not_current in said[0])
    assert stopped and flagged, "canary: some reads stopped before their last page and kept a fact not current"


@pytest.mark.pg
def test_a_time_nothing_reads_leaves_its_row_alone_out_and_the_rest_keep_their_order(pg_engine):
    texts = {1: "2026-09-30 00:05:00", 2: "2026/09/30 00:04:00", 3: "not a time", 4: "2026-09-30T00:03:00",
             5: "30.09.2026 00:02", 6: "2026-09-31 25:00", 7: "2026-09-30 00:01:00", 8: "2026/09/30 00:06"}
    rows = [{"row_id": n, "wafer_id": "W1", "recipe_id": "R%d" % n, "at": text} for n, text in texts.items()]
    newest_first = [8, 1, 2, 4, 7]                          # 3, 5 and 6 nothing reads
    leg = _leg()
    with pg_engine.connect() as connection:
        for limit in (1, 2, 3, 10):
            said = {}
            reader, _made = _reader(leg, rows, connection=connection, said=said)
            atoms, over = reader.claims_for_entities([("wafer", {"wafer": "W1"})], "outgoing", limit)
            assert [atom.id for atom in atoms] == [leg.late(rows[n - 1])[1] for n in newest_first[:limit]], limit
            assert over == (limit < len(newest_first)), limit
            assert said["unreadable_times"] == 3, limit
