# -*- coding: utf-8 -*-
"""`GET /api/ledger/lot_map` — WHICH FRAME each axis lands on, asserted on a corpus where
the three slot spaces DISAGREE.

WHY THIS FILE EXISTS SEPARATELY FROM `test_ledger_lots.py`
----------------------------------------------------------
That file runs without a database on purpose and says so. These assertions are about the
`WHERE` clause and the `wafer_map_metadata` lookup — the two things a fake connection
cannot exercise — so they need real PostgreSQL, in an ISOLATED database, in a scratch
schema that is dropped at teardown. Same shape as `test_ledger_siblings_pg.py`.

🔴 THE FIXTURE IS BUILT SO THE TWO CANDIDATE RULES DISAGREE, WHICH IS THE ONLY WAY IT
DECIDES ANYTHING
--------------------------------------------------------------------------------------
Every planted package carries THREE slot values that are pairwise different:

    bond_slot 3   dt_slot 7    core_slot 21      (group A)
    bond_slot 7   dt_slot 11   core_slot 22      (group B)

A corpus where `core_slot == bond_slot` would score the broken rule and the correct rule
identically — it would be green before and after the repair and would prove nothing. So
the slots are forced apart, and `test_the_fixture_actually_separates_the_slot_spaces`
asserts that they are, because a fixture that silently stopped separating them would turn
every other test in this file into a green line over a dead defect axis.

🔴 AND THE WRONG ANSWER IS REGISTERED TOO, ON PURPOSE.
`wafer_map_metadata` carries a DECOY frame at `CORE-A_3` and `DT-A_5` — the keys the
defective code built by pairing an axis's LOT with the BONDING slot. Without the decoys
the broken code would answer `no_frame` and any implementation that refuses everything
would pass. With them, both rules answer `ready` and the tests are forced onto WHICH
frame came back: `CORE-A_21` (13 cols) or the decoy `CORE-A_3` (4 cols). That is the
difference between a test that detects the defect and a test that merely dislikes it.

MEASURED BEFORE AND AFTER (2026-08-14, this file against `ledger_lots.py`):
    before the repair   core projection `ready`, map_id `CORE-A_3`,  grid 4x4   (fiction)
    after  the repair   core projection `ready`, map_id `CORE-A_21`, grid 13x13
"""
import contextlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import finding_kinds                                                  # noqa: E402
import ledger_lots                                                    # noqa: E402
import ledger_siblings                                                # noqa: E402

PG_TEST_URL_ENV = "ASSY_PG_TEST_DATABASE_URL"
SCRATCH_SCHEMA = "assy_lotmap_pytest" + (
    "_" + os.environ["PYTEST_XDIST_WORKER"]
    if os.environ.get("PYTEST_XDIST_WORKER") else "")

#: 🔴 NAMES THAT EXIST IN NO OTHER SCHEMA, and that is load-bearing rather than tidy.
#: `ledger_lots._column_present` asks `information_schema.columns` WITHOUT a
#: `table_schema` predicate, so a relation named `bonding_log` here would be answered
#: about `public.bonding_log` as well as about ours. Unique names make the bleed
#: unreachable for this file. (Reported to the lead PM as a latent defect in its own
#: right — inert on a one-schema box, not inert under a scratch schema.)
LOT_RELATION = "lotmap_probe_bond"
OBS_RELATION = "lotmap_probe_void"


def _resolve_url():
    import db_safety
    from database.database import DEFAULT_PG_URL

    url = os.environ.get(PG_TEST_URL_ENV) or None
    if not url:
        candidate = os.environ.get(db_safety.TEST_DATABASE_URL_ENV) or ""
        url = candidate if candidate.startswith("postgres") else None
    if not url:
        return None, (f"no PostgreSQL test database declared. Set {PG_TEST_URL_ENV} to "
                      f"an ISOLATED database, e.g. postgresql://…@localhost:5432/assy_qa")
    violations = db_safety.check_test_database(url, production_url=DEFAULT_PG_URL,
                                               opt_in=url)
    if violations:
        return None, f"{PG_TEST_URL_ENV} is not usable: {violations[0]}"
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        return None, f"{PG_TEST_URL_ENV} is not a PostgreSQL URL"
    if (parsed.database or "") == "assy_manager":
        return None, "refusing to run schema DDL against 'assy_manager'"
    return url, None


@contextlib.contextmanager
def _declared_as_test_database(url):
    import db_safety
    key = db_safety.TEST_DATABASE_URL_ENV
    previous = os.environ.get(key)
    os.environ[key] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


DDL = f"""
CREATE TABLE {LOT_RELATION} (
    bond_cell_key TEXT PRIMARY KEY,
    base_id TEXT, bx INT, by INT,
    bond_eqp  TEXT,
    bond_lot  TEXT, bond_slot INT, bond_x INT, bond_y INT,
    dt_lot    TEXT, dt_slot   INT, dt_x   INT, dt_y   INT,
    core_lot  TEXT, core_slot INT, cx     INT, cy     INT
);
CREATE TABLE inspection_run (
    run_uid TEXT PRIMARY KEY, method TEXT,
    base_wafer_id TEXT, base_x INT, base_y INT,
    recipe_id TEXT, eqp_id TEXT, observed_at TIMESTAMPTZ
);
CREATE TABLE {OBS_RELATION} (
    void_uid TEXT PRIMARY KEY, run_uid TEXT,
    base_wafer_id TEXT, base_x INT, base_y INT,
    radius_x DOUBLE PRECISION, radius_y DOUBLE PRECISION, unit TEXT
);
CREATE TABLE wafer_map_metadata (
    map_pk TEXT PRIMARY KEY, target_table TEXT, map_id TEXT, grid_metadata TEXT
);
"""

BOND_LOT, DT_LOT, CORE_LOT = "BOND-A", "DT-A", "CORE-A"
UNKEYED_LOT = "BOND-N"          # coordinates on every axis, NO core lot/slot recorded

#: (bond_slot, dt_slot, core_slot, bond_y, dt_y, cy). The y coordinate is the GROUP'S
#: FINGERPRINT: it says which rows survived the `WHERE`, which is how a test about the
#: filter column can tell one narrowing from another.
GROUP_A = (3, 7, 21, 1, 2, 3)
GROUP_B = (7, 11, 22, 5, 6, 7)

#: The registered frames. The two DECOYS are the keys the defect built — an axis's own
#: lot paired with the BONDING slot — and they carry grids nothing else does, so a
#: response that lands on one is identifiable by its column count alone.
FRAMES = {
    f"{BOND_LOT}_3": (11, 11),
    f"{BOND_LOT}_7": (11, 12),
    f"{DT_LOT}_7": (12, 12),          # correct for group A's dt slot
    f"{DT_LOT}_3": (5, 5),            # DECOY: dt lot x BONDING slot
    f"{CORE_LOT}_21": (13, 13),       # correct for group A's core slot
    f"{CORE_LOT}_3": (4, 4),          # DECOY: core lot x BONDING slot
    f"{UNKEYED_LOT}_9": (10, 10),
}
DECOY_CORE_KEY, TRUE_CORE_KEY = f"{CORE_LOT}_3", f"{CORE_LOT}_21"
DECOY_DT_KEY, TRUE_DT_KEY = f"{DT_LOT}_3", f"{DT_LOT}_7"

N_A = N_B = 6
N_UNKEYED = 4
SCAN_AT = "2026-08-10T00:00:00+00:00"


def _plant(connection):
    rows = []
    for i in range(N_A + N_B):
        bslot, dslot, cslot, by_, dy, cy = GROUP_A if i < N_A else GROUP_B
        rows.append((f"PKG-{i:02d}", f"W-{i:02d}", i, 0, "EQP-1",
                     BOND_LOT, bslot, i + 1, by_,
                     DT_LOT, dslot, i + 1, dy,
                     CORE_LOT, cslot, i + 1, cy))
    # 🔴 THE HONEST-EMPTY-KEY GROUP. Coordinates on all three axes, but no core lot and
    # no core slot — the shape that must answer 「기록돼 있지 않다」 rather than
    # 「슬롯을 고르십시오」, because picking a slot cannot conjure a key that was never
    # written. `bond_eqp` differs too, so `by=bond_eqp` can address the other groups.
    for j in range(N_UNKEYED):
        i = N_A + N_B + j
        rows.append((f"PKG-{i:02d}", f"W-{i:02d}", i, 0, "EQP-2",
                     UNKEYED_LOT, 9, i + 1, 9,
                     "DT-N", 9, i + 1, 10,
                     None, None, i + 1, 11))
    with connection.cursor() as cur:
        cur.executemany(
            f"INSERT INTO {LOT_RELATION} VALUES "
            f"(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
        for i in range(len(rows)):
            cur.execute(
                "INSERT INTO inspection_run VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (f"sat|W-{i:02d}", "sat", f"W-{i:02d}", i, 0, "RCP", "SCAN", SCAN_AT))
            cur.execute(
                f"INSERT INTO {OBS_RELATION} (void_uid, run_uid, base_wafer_id, base_x, "
                f"base_y) VALUES (%s,%s,%s,%s,%s)",
                (f"void|W-{i:02d}", f"sat|W-{i:02d}", f"W-{i:02d}", i, 0))
        for map_id, (cols, grid_rows) in FRAMES.items():
            cur.execute(
                "INSERT INTO wafer_map_metadata VALUES (%s,%s,%s,%s)",
                (f"{LOT_RELATION}|{map_id}", LOT_RELATION, map_id,
                 json.dumps({"grid_cols": cols, "grid_rows": grid_rows,
                             "grid_start_x": 1, "grid_start_y": 1,
                             "grid_y_invert": False, "rotation": 0})))
    connection.commit()


REGISTRY = {
    "void": {"label": "보이드", "observed_by": ["sat"],
             "observation_table": OBS_RELATION,
             "extent_columns": ["radius_x", "radius_y"], "unit_column": "unit"},
}

#: 🔴 `bond_eqp` IS DECLARED FIRST AND IS NOT THE DEFAULT ROW AXIS. `resolve_row_axis`
#: takes the first `about: process` axis whose NAME ends in `_lot`, so the default here is
#: `bond_lot` even though it is declared second — which is the behaviour under test in
#: `test_a_row_axis_with_no_frame_family_says_the_slot_bought_nothing`, where `bond_eqp`
#: has to be reachable by `?by=` without being what an unqualified request lands on.
AXES = {
    "version": 1,
    "defaults": {"limit": 50, "min_support": 2, "evidence_ref_sample": 3,
                 "contrast": {"enriched_at": 1.5, "depleted_at": 0.6667}},
    "geometry": {
        "unit": "package", "unit_label": "패키지",
        "unit_columns": ["base_wafer_id", "base_x", "base_y"],
        "run_key_column": "run_uid", "run_method_column": "method",
        "run_time_column": "observed_at", "observation_run_ref_column": "run_uid",
        "universe": {"relation": LOT_RELATION,
                     "join": {"base_wafer_id": "base_id", "base_x": "bx",
                              "base_y": "by"}},
    },
    "attribution": [{
        "relation": LOT_RELATION, "about": "process", "label": "본딩",
        "key_column": "bond_cell_key",
        "join": {"base_wafer_id": "base_id", "base_x": "bx", "base_y": "by"},
        "axes": [{"name": "bond_eqp", "label": "본딩 장비", "column": "bond_eqp"},
                 {"name": "bond_lot", "label": "본딩 랏", "column": "bond_lot"},
                 {"name": "dt_lot", "label": "DT 랏", "column": "dt_lot"}],
    }],
    "kinds": {},
}


@pytest.fixture(scope="module")
def pg():
    url, reason = _resolve_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2                                              # noqa: F401
    except Exception as exc:                                         # pragma: no cover
        pytest.skip(f"psycopg2 is not importable: {exc}")
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    with _declared_as_test_database(url):
        admin = create_engine(url, poolclass=NullPool)
        try:
            with admin.begin() as conn:
                conn.execute(text("SELECT 1"))
        except OperationalError as exc:
            admin.dispose()
            pytest.skip(f"PostgreSQL is not reachable: "
                        f"{str(exc).strip().splitlines()[0]}")
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{SCRATCH_SCHEMA}"'))
        engine = create_engine(
            url, poolclass=NullPool,
            connect_args={"options": f"-csearch_path={SCRATCH_SCHEMA}"})
        raw = engine.raw_connection()
        with raw.cursor() as cur:
            cur.execute(DDL)
        raw.commit()
        _plant(raw)
        try:
            yield raw
        finally:
            raw.close()
            engine.dispose()
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
                # ASK THE CATALOGUE. "I issued a DROP" is not the same fact as "it is
                # gone" — 92 objects were left behind on 2026-08-12 believing it was.
                left = conn.execute(text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = :s"), {"s": SCRATCH_SCHEMA}).scalar()
                assert left == 0, f"{left} object(s) left behind in {SCRATCH_SCHEMA}"
            admin.dispose()


@pytest.fixture(autouse=True)
def declarations():
    finding_kinds.set_registry(REGISTRY)
    ledger_siblings.set_axes_config(AXES)
    yield
    finding_kinds.set_registry(None)
    ledger_siblings.set_axes_config(None)


def _axis(answer, name):
    for p in answer["projections"]:
        if p["axis"] == name:
            return p
    raise AssertionError(f"projection {name!r} absent from {answer['projections']}")


def _grid(projection):
    return json.loads(projection["frame"]["grid"])


# --------------------------------------------------------------- the fixture's own guard
def test_the_fixture_actually_separates_the_slot_spaces(pg):
    """The precondition every other test in this file rests on, asserted rather than
    assumed. If the three slot spaces ever coincide again, the correct rule and the
    defective one return the SAME frame and every assertion below goes green over a dead
    defect axis — the exact shape this project has paid for before."""
    with pg.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {LOT_RELATION} "
                    f"WHERE core_slot IS NOT NULL AND "
                    f"(core_slot = bond_slot OR dt_slot = bond_slot)")
        assert cur.fetchone()[0] == 0, \
            "a planted row has two slot spaces agreeing — the corpus decides nothing"
    assert DECOY_CORE_KEY in FRAMES and TRUE_CORE_KEY in FRAMES, \
        "both the right and the wrong frame must be registered, or refusing everything passes"


# --------------------------------------------------------- defect (1): the frame lookup
def test_the_core_axis_frames_on_its_own_slot_and_not_the_bonding_one(pg):
    """🔴 THE HEADLINE. `slot=3` is a BONDING slot — the filter it drives is
    `bond_slot = 3`. The core axis's frame is `{core_lot}_{core_slot}` and nothing else.

    Both candidate rules answer `ready` here because both keys are registered, so the
    assertion is on WHICH frame came back. Before the repair this was `CORE-A_3` with a
    4x4 grid: every core coordinate would have been drawn on a grid a third the right
    size, with nothing on screen saying so.
    """
    answer = ledger_lots.lot_map(pg, row=BOND_LOT, slot="3")
    core = _axis(answer, "core")
    assert core["state"] == ledger_lots.MAP_STATE_READY, core
    assert core["frame"]["map_id"] == TRUE_CORE_KEY, \
        f"core axis framed on {core['frame']['map_id']} — the bonding slot was borrowed"
    assert _grid(core)["grid_cols"] == 13
    assert core["frame"]["map_id"] != DECOY_CORE_KEY


def test_the_dt_axis_frames_on_its_own_slot_too(pg):
    """A second, independent witness. One axis could be right by coincidence; the rule
    under test is 「every axis reads its own pair」, so two axes are asserted."""
    answer = ledger_lots.lot_map(pg, row=BOND_LOT, slot="3")
    dt = _axis(answer, "dt")
    assert dt["state"] == ledger_lots.MAP_STATE_READY, dt
    assert dt["frame"]["map_id"] == TRUE_DT_KEY, \
        f"dt axis framed on {dt['frame']['map_id']} — the bonding slot was borrowed"
    assert _grid(dt)["grid_cols"] == 12
    assert dt["frame"]["map_id"] != DECOY_DT_KEY

    bond = _axis(answer, "bond")
    assert bond["frame"]["map_id"] == f"{BOND_LOT}_3", \
        "the axis the slot DOES belong to must be unaffected by the repair"


def test_each_axis_lists_its_own_slots_when_the_row_spans_several_frames(pg):
    """With no `slot`, the row spans two frames on every axis — and the slots offered are
    each axis's OWN, never one list stamped onto all three."""
    answer = ledger_lots.lot_map(pg, row=BOND_LOT)
    assert _axis(answer, "bond")["frame"]["available_slots"] == ["3", "7"]
    assert _axis(answer, "dt")["frame"]["available_slots"] == ["11", "7"]
    assert _axis(answer, "core")["frame"]["available_slots"] == ["21", "22"]
    for name in ("bond", "dt", "core"):
        p = _axis(answer, name)
        assert p["state"] == ledger_lots.MAP_STATE_NO_FRAME
        assert p["reason"] == ledger_lots.MAP_REASON_FRAME_AMBIGUOUS


# ------------------------------------------------------ defect (2): the filter's column
def test_the_slot_narrows_the_row_axis_own_family(pg):
    """`by=dt_lot` makes the row a DT lot, so `slot` is a DT slot and `dt_slot` is what it
    narrows. `_slot_column_for` used to answer `bond_slot` for every row axis.

    The two rules select DIFFERENT ROWS here, and the rows say which one ran: group A
    carries `dt_slot = 7` and `bond_y = 1`, group B carries `bond_slot = 7` and
    `bond_y = 5`. So `slot="7"` under the correct rule returns group A's coordinates and
    under the defective rule returns group B's.
    """
    answer = ledger_lots.lot_map(pg, row=DT_LOT, by="dt_lot", slot="7")
    # 🔴 THE BEHAVIOUR IS ASSERTED BEFORE THE DISCLOSURE FIELD, and the order is
    # deliberate: `slot_column` is what the response SAYS, `cells` is what the query DID.
    # Asserting the label first would let an injected defect fail on the label and never
    # reach the fact — an alarm that has only ever been heard describing itself.
    bond = _axis(answer, "bond")
    assert {c["y"] for c in bond["cells"]} == {1}, \
        "the wrong row set survived the WHERE — group B answered a group A question"
    assert bond["found"] == N_A
    assert _axis(answer, "core")["frame"]["map_id"] == TRUE_CORE_KEY
    assert _axis(answer, "dt")["frame"]["map_id"] == TRUE_DT_KEY
    assert answer["slot_column"] == "dt_slot", \
        "the slot was applied to another family's column"


def test_a_row_axis_with_no_frame_family_says_the_slot_bought_nothing(pg):
    """`bond_eqp` is not a lot; there is no slot column a `slot` could mean on it. The
    request is not silently narrowed on someone else's family, and the response says so
    with `slot_column: null` — otherwise a screen shows an UNNARROWED row under a slot
    heading and the reader has no way to tell."""
    answer = ledger_lots.lot_map(pg, row="EQP-1", by="bond_eqp", slot="3")
    bond = _axis(answer, "bond")
    assert bond["state"] == ledger_lots.MAP_STATE_NO_FRAME
    assert bond["frame"]["available_slots"] == ["3", "7"], \
        "nothing was narrowed, so both slots must still be on offer"
    assert answer["slot"] == "3"
    assert answer["slot_column"] is None


# ------------------------------------------------- the third situation: no key recorded
def test_an_axis_with_no_recorded_frame_key_does_not_tell_the_reader_to_pick_a_slot(pg):
    """Coordinates present, `core_lot`/`core_slot` never written. The verdict is
    `no_frame` — correct, and unchanged — but the SENTENCE must not be 「slot을 지정할
    것」, which is an instruction to do something that cannot work: there is no slot to
    pick, and `available_slots` is empty, so a reader following the advice loops."""
    answer = ledger_lots.lot_map(pg, row=UNKEYED_LOT, slot="9")
    core = _axis(answer, "core")
    assert core["state"] == ledger_lots.MAP_STATE_NO_FRAME
    assert core["frame"]["available_slots"] == []
    assert core["cells"], "the measured coordinates are still served, not hidden"
    assert "slot을 지정할 것" not in core["message"], core["message"]
    assert "기록돼 있지 않다" in core["message"], core["message"]

    bond = _axis(answer, "bond")
    assert bond["state"] == ledger_lots.MAP_STATE_READY, \
        "one axis lacking a key must not cost the axes that have one"
    assert bond["frame"]["map_id"] == f"{UNKEYED_LOT}_9"
