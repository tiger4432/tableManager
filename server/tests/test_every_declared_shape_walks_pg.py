"""The walk's shape gate on PostgreSQL (owner 11-11 «노드, 엣지 속성, 키 모든 타입 그리고 걷기 끝»): `support.
walk_shape_gate` builds one table, its three rows and one source a cell of SEATS x TYPES; the virtual walk from every
subject must draw each cell - the node or edge there, its value spelled as the walk spells it, a blank or a NaN not
said, nothing left out. Every cell is walked; the cells `gate.ENABLED` names are held, the rest say why not yet."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                        # noqa: E402
from ledger import explorer, roleframe, schema, trace_router        # noqa: E402
from ledger.setup import load_setup                                 # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402
from support import walk_shape_gate as gate                         # noqa: E402
from test_ledger_worlds_are_independent_and_meet_in_a_walk import fixture_config, fixture_world  # noqa: E402,F401

pytestmark = pytest.mark.pg


@pytest.fixture(name="board")
def fixture_board(world, config, monkeypatch):
    from database import crud
    from conftest import PG_TEST_SCHEMA

    tables = json.loads((config / "table_config.json").read_text(encoding="utf-8"))
    tables[gate.TABLE] = gate.catalogue()
    (config / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    monkeypatch.setitem(crud.TABLE_CONFIG, gate.TABLE, gate.catalogue())
    (config / "ontology" / "ledger_config.json").write_text(json.dumps(gate.document(), default=str),
                                                           encoding="utf-8")
    import notation_norm

    raw = world["engine"].raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())   # as the schema sync makes them
            cursor.execute(f'DROP TABLE IF EXISTS "{PG_TEST_SCHEMA}"."{gate.TABLE}"')
            cursor.execute(gate.ddl(PG_TEST_SCHEMA))
            for row in gate.rows():
                names = sorted(row)
                cursor.execute(f'INSERT INTO "{PG_TEST_SCHEMA}"."{gate.TABLE}" ({", ".join(chr(34) + n + chr(34) for n in names)}) '
                               f"VALUES ({', '.join(['%s'] * len(names))})", [row[n] for n in names])
        raw.commit()
    finally:
        raw.close()
    trace_router._COMPILED.clear()
    yield world
    with world["engine"].begin() as conn:
        conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{PG_TEST_SCHEMA}"."{gate.TABLE}"')


def _walk(board, seat, kind):
    """One cell's walk - its own seeds, its own predicate, so a cell that breaks the read breaks only itself."""
    cell = gate.name(seat, kind)
    held = cell if seat in ("attribute", "qualifier_required_attribute") else "subj"
    seeds = [explorer.entity_id(held, {"sid": row}) for row in gate.ROWS]
    with board["engine"].connect() as conn:
        return trace_router._evidence_graph(conn, node_id={"positive": seeds, "negative": []}, hops=1,
                                            direction="both", node_limit=500, edge_limit=500, engine="virtual",
                                            follow=["register" if seat == "attribute" else f"p_{cell}"])


def census(board):
    """{cell: [the reasons it is red]} - every cell, an empty list when it walks."""
    snapshot = load_setup(schema.require_world(None).declaration_root).snapshot
    out, dumped = {}, {}
    for seat, kind in gate.CELLS:
        cell = gate.name(seat, kind)
        plan = snapshot.source_plans.get(cell)
        refused = None if plan is None or plan.runs else (plan.refusal or {}).get("message")
        if (seat, kind) in gate.REFUSED or refused is not None or plan is None:
            # a cell whose answer is the save-time refusal holds that sentence; any other is red not planned
            sentence = gate.REFUSED.get((seat, kind))
            out[cell] = [] if plan is not None and refused == sentence else [f"refused {refused!r}, not {sentence!r}"]
            continue
        try:
            answer = _walk(board, seat, kind)
        except Exception as exc:                                   # a cell that breaks the read is its red
            out[cell] = ["walk raised %s: %s" % (type(exc).__name__, str(exc).splitlines()[0][:200])]
            continue
        dumped[cell] = answer
        red = [item["why"] for item in answer["engine"]["left_out"] if item["source"] == cell]
        nodes = {node["id"]: node for node in answer["nodes"]}
        want = gate.expected(seat, kind, ledger_subgraph._instant)
        for row in gate.ROWS:
            said = not roleframe._is_missing(gate.cell_of_row(kind, row)) or seat == "key_constant"
            subject = explorer.entity_id(cell if seat == "qualifier_required_attribute" else "subj", {"sid": row})
            if seat == "attribute":
                node = nodes.get(explorer.entity_id(cell, {"sid": row})) or {}
                got = (node.get("attributes") or {}).get("v", "<none>")
                if said and got != want:
                    red.append(f"{row}: attribute v {got!r}, not {want!r}")
                if not said and got != "<none>":
                    red.append(f"{row}: a blank said attribute v {got!r}")
                continue
            edges = [e for e in answer["edges"] if e["source"] == subject and e["predicate"] == f"p_{cell}"]
            if seat in ("qualifier_optional", "follow_bound") and not said:
                if len(edges) != 1 or "q" in (edges[0].get("qualifiers") or {}):
                    red.append(f"{row}: a blank optional qualifier - edges {[e.get('qualifiers') for e in edges]}")
                continue
            if not said:
                if edges:
                    red.append(f"{row}: a blank drew {len(edges)} edge(s)")
                continue
            if len(edges) != 1:
                red.append(f"{row}: {len(edges)} edges, not 1")
                continue
            edge = edges[0]
            if seat in ("key_one", "key_several", "key_constant"):
                got = (nodes.get(edge["target"]) or {}).get("keys", {}).get("k", "<no node>")
            elif seat.startswith("qualifier") or seat == "follow_bound":
                got = (edge.get("qualifiers") or {}).get("q", "<none>")
            elif seat == "value":
                got = (nodes.get(edge["target"]) or {}).get("value", "<no value node>")
            else:
                got = edge.get("occurred_at")
            if got != want:
                red.append(f"{row}: {got!r}, not {want!r}")
        out[cell] = red
    dump = os.environ.get("SHAPE_GATE_DUMP")
    if dump:
        with open(dump, "w", encoding="utf-8") as handle:
            json.dump(dumped, handle, default=str, ensure_ascii=False, indent=1)
    return out


def test_every_cell_walks(board):
    """Every cell is walked and its reds collected; the ENABLED cells are held (none red), every other one carries
    the reason it is not held yet (`gate.not_yet`)."""
    assert len(gate.CELLS) == len(gate.SEATS) * len(gate.TYPES) - len(gate.CANNOT_EXIST) == 94
    assert len(gate.ENABLED) == 74 and gate.ENABLED <= set(gate.CELLS)      # 94 - the value row (owner) - D's row
    assert all(gate.not_yet(*cell) for cell in gate.CELLS if cell not in gate.ENABLED)
    reds = census(board)
    assert len(reds) == len(gate.CELLS), "canary: every cell walked"
    report = os.environ.get("SHAPE_GATE_REDS")
    if report:
        with open(report, "w", encoding="utf-8") as handle:
            json.dump({cell: why for cell, why in reds.items() if why}, handle, ensure_ascii=False, indent=1)
    held = {gate.name(*cell): reds[gate.name(*cell)] for cell in sorted(gate.ENABLED)}
    assert held == {cell: [] for cell in held}, " | ".join(f"{cell}: {'; '.join(why)}" for cell, why in held.items() if why)
