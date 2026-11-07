# -*- coding: utf-8 -*-
"""Lead 11-07 (the virtual read's remaining time - 72,400 rows made atoms for 10,000 kept): a virtual atom makes its
raw ref and id when first read (`ledger_subgraph._RowAtom`), and one reader spells each value once (`Leg.atom`'s
memo, `VirtualEvidenceLookup._texts`).

  replace     `replace(atom, not_current=True)` keeps the atom's type and its two late cells
  late        the raw ref and id an atom makes when read are `Leg.late`'s for its row, byte for byte - and the rules
              (`claims_for_entities`: «as of», interval, current, order, cut) make none for an atom whose first five
              cells decide
  memo        values Python holds equal (True and 1, Decimal 9.0 and 9, 1e20 and 10**20) keep their own spellings
"""
import dataclasses
import decimal
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import sql_translate                                    # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402

KEY = {"column": "wafer_id", "declared": None, "kind": "text", "zone": None}


def _leg():
    plan = SimpleNamespace(source_id="src", relation="wafer_process", profile=None,
                           driver=SimpleNamespace(occurred_at=SimpleNamespace(column="at", timezone="UTC", format=None),
                                                  order_by=("row_id",)))
    return sql_translate.Leg(plan, "made-with", "processed_with",
                             {"outgoing": ("wafer", {"wafer": KEY}),
                              "incoming": ("recipe", {"recipe": {**KEY, "column": "recipe_id"}})},
                             {}, [KEY], [], None, "v1", {}, [])


ROWS = [{"row_id": n, "wafer_id": "W%d" % (n % 3), "recipe_id": "R%d" % (n % 2),
         "at": datetime(2026, 9, 30, 1, n, tzinfo=timezone.utc)} for n in range(1, 21)]
ROWS += [dict(row, row_id=row["row_id"] + 20) for row in ROWS[:4]]     # four pairs tie on everything but the row


def _reader(leg):
    reader = ledger_subgraph.VirtualEvidenceLookup(None, [leg], worlds=(SimpleNamespace(name="default"),))
    made = []
    maker = reader._maker

    def counting(leg_, row):
        make = maker(leg_, row)
        return lambda: made.append(row["row_id"]) or make()
    reader._maker = counting
    return reader, made


def test_a_replaced_atom_keeps_its_type_and_its_late_cells():
    leg = _leg()
    reader, made = _reader(leg)
    atom = reader._atoms(leg, [tuple(row[cell] for cell in leg.cells()) for row in ROWS[:1]])[0]
    assert made == [], "canary: nothing made before a read"
    replaced = dataclasses.replace(atom, not_current=True)
    assert type(replaced) is ledger_subgraph._RowAtom and replaced.not_current
    assert (replaced.source_raw_ref, replaced.id) == leg.late(ROWS[0]) == (atom.source_raw_ref, atom.id)


def test_the_late_cells_are_the_rows_own_and_an_order_decided_early_makes_none():
    leg = _leg()
    reader, made = _reader(leg)
    atoms = reader._atoms(leg, [tuple(row[cell] for cell in leg.cells()) for row in ROWS])
    distinct = {(a.occurred_at, a.subject_keys["wafer"], a.object_payload["keys"]["recipe"]) for a in atoms}
    assert len(distinct) < len(atoms), "canary: some atoms tie on the five cells before the late two"
    reader.atoms = atoms
    kept, cut = ledger_subgraph.InMemoryEvidenceLookup.claims_for_entities(
        reader, [("wafer", {"wafer": "W%d" % n}) for n in range(3)], "both", 5)
    assert len(kept) == 5 and cut, "canary: the rules read every atom and cut"
    assert made and set(made) <= {1, 2, 3, 4, 21, 22, 23, 24}, "the rules and the order made the tied atoms' only"
    for row, atom in zip(ROWS, atoms):
        assert (atom.source_raw_ref, atom.id) == leg.late(row), row["row_id"]
    assert sorted(made) == sorted(set(made)), "each atom makes them once"


def test_one_reader_spells_each_value_once_and_equal_values_keep_their_own_spelling():
    pairs = [(True, 1), (decimal.Decimal("9.0"), 9), (1e20, 10 ** 20)]
    for a, b in pairs:
        assert a == b and hash(a) == hash(b), "canary: Python holds them one dict key"
        assert sql_translate._spelled(KEY, {"wafer_id": a}) != sql_translate._spelled(KEY, {"wafer_id": b}), (a, b)
    leg, memo = _leg(), {}
    for value in [9, 9.0, "9", *[v for pair in pairs for v in pair]]:
        row = {"row_id": 1, "wafer_id": value, "recipe_id": "R", "at": datetime(2026, 9, 30, tzinfo=timezone.utc)}
        fields, _unreadable = leg.atom(row, memo)
        expected = sql_translate._spelled(KEY, row)
        assert (fields["subject_keys"]["wafer"] if fields else None) == expected, value
