"""The walk's shape gate without a database - the SQLite twin of `test_every_declared_shape_walks_pg.py`, from the same
generator (`support.walk_shape_gate`): every enabled cell compiles with nothing left out (or holds its save-time
refusal), and a cell the walk reads as a value is spelled as the walk spells it - the value, a blank and a NaN."""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import paths                                                        # noqa: E402
from ledger import roleframe, sql_translate                         # noqa: E402
from ledger.setup import load_setup                                 # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402
from support import walk_shape_gate as gate                         # noqa: E402
from test_ledger_worlds_are_independent_and_meet_in_a_walk import fixture_config  # noqa: E402,F401

VALUED = ("attribute", "qualifier_optional", "qualifier_required", "value")


def _board(config, monkeypatch):
    from database import crud

    tables = json.loads((config / "table_config.json").read_text(encoding="utf-8"))
    tables[gate.TABLE] = gate.catalogue()
    (config / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    monkeypatch.setitem(crud.TABLE_CONFIG, gate.TABLE, gate.catalogue())
    (config / "ontology" / "ledger_config.json").write_text(json.dumps(gate.document(), default=str),
                                                           encoding="utf-8")
    snapshot = load_setup(paths.config_path("ontology")).snapshot
    kinds = sql_translate.column_kinds(lambda sql, params: list(gate.kinds().items()), gate.TABLE)
    return snapshot, kinds


def census(config, monkeypatch):
    """({cell: [the reasons it is red]} - every cell, the number of cells read as a value or a time and compared)."""
    snapshot, kinds = _board(config, monkeypatch)
    out, compared = {}, set()
    for seat, kind in gate.CELLS:
        cell, red = gate.name(seat, kind), []
        plan = snapshot.source_plans[cell]
        sentence = gate.REFUSED.get((seat, kind))
        if sentence is not None or not plan.runs:
            refused = None if plan.runs else (plan.refusal or {}).get("message")
            out[cell] = [] if refused == sentence else [f"refused {refused!r}, not {sentence!r}"]
            continue
        try:
            legs, unread = sql_translate.compile_source(snapshot, plan, kinds, "w")
        except sql_translate.NotCompiled as why:
            out[cell] = [f"not compiled: {why}"]
            continue
        red += unread
        mine = [leg for leg in legs if leg.source == cell]
        if not mine:
            red.append("no leg")
        want = gate.expected(seat, kind, ledger_subgraph._instant)
        for leg in mine:
            spec = leg.value if seat == "value" else leg.qualifiers.get("v" if seat == "attribute" else "q")
            if seat in VALUED and spec is not None:
                compared.add(cell)
                for row in gate.ROWS:
                    got = ledger_subgraph.VirtualEvidenceLookup._cell(gate.cell_of_row(kind, row), spec)
                    blank = roleframe._is_missing(gate.cell_of_row(kind, row))
                    if blank and not roleframe._is_missing(got):
                        red.append(f"{row}: a blank read as {got!r}")
                    if not blank and got != want:
                        red.append(f"{row}: {got!r}, not {want!r}")
            if seat == "event_time":
                compared.add(cell)
                got = leg.instant(gate.cell_of_row(kind, "S1"))
                if got is None or ledger_subgraph._instant(got) != want:
                    red.append(f"S1: time {got!r}, not {want!r}")
        if seat in VALUED and not any((leg.value if seat == "value" else leg.qualifiers) for leg in mine):
            red.append("no value spec")
        out[cell] = red
    return out, len(compared)


def test_every_enabled_cell_compiles(config, monkeypatch):
    assert len(gate.CELLS) == len(gate.SEATS) * len(gate.TYPES) - len(gate.CANNOT_EXIST) == 74
    assert len(gate.ENABLED) == 64 and gate.ENABLED <= set(gate.CELLS)      # 74 - the value-object row (pending owner)
    assert all(gate.not_yet(*cell) == gate.PENDING_OWNER for cell in gate.CELLS if cell not in gate.ENABLED)
    reds, compared = census(config, monkeypatch)
    assert len(reds) == len(gate.CELLS), "canary: every cell compiled"
    # attribute and both qualifiers x 10 types, the value row's compiled cells, the 3 event times read
    assert compared >= 30 + 3, f"canary: {compared} cells compared as a value or a time"
    held = {gate.name(*cell): reds[gate.name(*cell)] for cell in sorted(gate.ENABLED)}
    assert held == {cell: [] for cell in held}, " | ".join(f"{cell}: {'; '.join(why)}" for cell, why in held.items() if why)
