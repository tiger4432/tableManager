"""LEDGER SQL COMPILE -- the translator (Python) and the walk's compile (SQL), scored against ONE recorded answer.

The file being scored is `contracts/ledger_sql_compile/vectors.json`; every expectation comes out of it.

    conda run -n assy_manager python server/scripts/run_pg_tests.py -k ledger_sql_compile

PostgreSQL only (the compile is PostgreSQL text: `assy_key_number`, `assy_key_instant`, jsonb). It reaches the PG run
through `server/tests/test_ledger_sql_compile_contract.py`, the shim, as the other contracts do.

Each case: the hold world's official table with the case's rows (written through the write door), the case's source
declared on it. The translator's atoms (`sql_translate.event_results` - what the stored ledger holds) and the compile's
(`sql_translate.compile_world`, every leg's rows read whole and made atoms by `Leg.atom`) must each be the case's atoms, and the two must name the same
rows (`source_raw_ref`) for the same facts.
"""
import copy
import json
import pathlib
import sys
from datetime import datetime, timezone

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SERVER = HERE.parents[1] / "server"
for path in (SERVER, SERVER / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ledger import backfill, roleframe, runtime_v2, sql_translate, trace  # noqa: E402
from ledger.setup import preview_selected_cursor_batch  # noqa: E402
from support import hold_world as hw  # noqa: E402

pytestmark = pytest.mark.pg
VECTORS = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))
CASES = {case["name"]: case for case in VECTORS["cases"]}


def _instant(text):
    return datetime.fromisoformat(text).astimezone(timezone.utc).isoformat()


def _fact(subject_type, keys, predicate, payload, occurred_at, basis):
    return json.dumps([subject_type, keys, predicate, payload, _instant(occurred_at), basis], sort_keys=True)


@pytest.fixture(name="world", params=list(CASES))
def fixture_world(request, pg_engine, monkeypatch, tmp_path):
    import event_constants
    from database import crud, schemas
    from database.context import channel

    import notation_norm

    case = CASES[request.param]
    with pg_engine.begin() as conn:                     # the key spellers, as the schema sync makes them
        conn.connection.cursor().execute(notation_norm.key_instant_sql() + notation_norm.key_number_sql())
    tables = copy.deepcopy(hw.TABLES)
    tables[hw.OFFICIAL]["column_types"].update(VECTORS["table"])
    tables[hw.OFFICIAL]["composite_key_source"] = ["dt_x"]          # one row each: the cases vary dt_x
    monkeypatch.setattr(hw, "TABLES", tables)
    source = copy.deepcopy(hw.LEDGER_SOURCE)
    source["read"], source["bind"] = case["read"], {"mappings": case["mappings"]}
    monkeypatch.setattr(hw, "LEDGER_SOURCE", source)
    sample = hw.sample

    def referencing(name):
        doc = sample(name)
        if name.startswith("ledger_config"):
            for entity, references in (case.get("references") or {}).items():
                doc["entities"][entity]["references"] = references
        return doc
    monkeypatch.setattr(hw, "sample", referencing)
    for world in hw.build(pg_engine, monkeypatch, tmp_path):
        with channel(event_constants.CHANNEL_API):
            crud.apply_batch_updates(world["db"], hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates=dict({"dt_x": 100 + at}, **row), source_name="user", updated_by="t")
                for at, row in enumerate(case["rows"])]))
            world["db"].commit()
        yield dict(world, case=case)


def _python(world):
    engine, setup = world["engine"], world["setup"]
    plan = setup.snapshot.source_plans[hw.SOURCE]
    raw = engine.raw_connection()
    try:
        frame = backfill._v2_frame(backfill._fetch_v2_lineage_rows(raw, plan, backfill._readable_columns(engine, plan)))
    finally:
        raw.close()
    with roleframe.times_read(backfill.times_read_of(engine, plan, frame)):
        preview = preview_selected_cursor_batch(setup, hw.SOURCE, frame, runtime_v2.last_cursor(plan, frame),
                                                known_registrations=(), translate="python")
    out = []
    for record in map(json.loads, sql_translate.atom_records(plan, preview.event_results)):
        out.append((_fact(record["subject_type"], record["subject_keys"], record["predicate"],
                          record["object_payload"], record["occurred_at"], record["basis"]), record["source_raw_ref"]))
    return sorted(out)


def _compiled(world):
    from ledger_api import ledger_subgraph

    with world["engine"].connect() as connection:
        legs, left_out = sql_translate.compile_world(
            world["setup"].snapshot, lambda sql, params=None: trace._fetch(connection, sql, params), "default")
        reader = ledger_subgraph.VirtualEvidenceLookup(connection, legs)
        atoms = [atom for leg in legs for atom in reader._atoms(leg, reader._execute(leg.read(), None))]
        connection.rollback()
    said = sorted((_fact(a.subject_type, a.subject_keys, a.predicate, a.object_payload, a.occurred_at.isoformat(),
                         a.occurred_at_basis), a.source_raw_ref) for a in atoms)
    return said, left_out


def test_each_engine_says_the_atoms_the_case_says(world):
    case = world["case"]
    sql, left_out = _compiled(world)
    if "left_out" in case:
        assert [item["why"] for item in left_out if item["source"] == hw.SOURCE] == [case["left_out"]]
        return
    assert not [item for item in left_out if item["source"] == hw.SOURCE], left_out
    python = _python(world)
    expected = sorted(_fact(*atom) for atom in case["expected"])
    assert [fact for fact, _ref in python] == expected, "the translator, against the hand-written atoms"
    assert [fact for fact, _ref in sql] == expected, "the compile, against the same"
    assert sql == python, "and the same row named for each fact (source_raw_ref, byte for byte)"
    if "rows_named" in case:
        assert [list(roleframe.claim_source_row_refs(ref)) for _fact_, ref in sql] == case["rows_named"]


def test_every_case_is_consumed():
    assert {case["name"] for case in VECTORS["cases"]} == set(CASES) and len(CASES) == len(VECTORS["cases"])
