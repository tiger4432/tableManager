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

from ledger_api import finding_kinds                                  # noqa: E402
import ledger_lots                                                    # noqa: E402
from ledger_api import ledger_siblings                                # noqa: E402

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

#: 🔴 THE BONDED-BASE-WAFER GROUPS. The 16 packages above each carry their OWN `base_id`,
#: which is the shape a frame with MANY wafers on it has — useful as the negative case and
#: useless as the positive one. These two lots have the shape the live box measured
#: (`base_id` ↔ the bonding frame key, 1:1), and its absence:
#:
#:   WAFER_LOT  one frame, ONE base wafer   -> `frame.wafer` names it
#:   BLANK_LOT  one frame, NO base identity -> the field is ABSENT and the frame still opens
#:
#: `bx` VARIES within WAFER_LOT while `by` is constant, on purpose: it makes the declared
#: identity column and the other unit columns give DIFFERENT answers, which is what lets
#: `test_the_identity_follows_the_declaration` decide anything at all.
WAFER_LOT, BLANK_LOT = "BOND-W", "BOND-Z"
WAFER_SLOT = 5
WAFER_ID = "BW-777"
WAFER_CONSTANT_Y = 7
N_WAFER = N_BLANK = 3

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
    f"{WAFER_LOT}_{WAFER_SLOT}": (9, 9),
    f"{BLANK_LOT}_{WAFER_SLOT}": (9, 9),
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
        # 🔴 PLANTED AFTER THE SCAN LOOP ABOVE, so these packages have no inspection run
        # and no observation. `frame.wafer` is a property of the BONDED rows, not of what
        # was found on them, and a fixture that could only exercise it through a finding
        # would be asserting two rules at once.
        cur.executemany(
            f"INSERT INTO {LOT_RELATION} VALUES "
            f"(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [(f"PKG-W{j}", WAFER_ID, j, WAFER_CONSTANT_Y, "EQP-3",
              WAFER_LOT, WAFER_SLOT, j + 1, 4, "DT-W", 13, j + 1, 8, None, None, None, None)
             for j in range(N_WAFER)]
            + [(f"PKG-Z{j}", None, None, None, "EQP-3",
                BLANK_LOT, WAFER_SLOT, j + 1, 4, "DT-Z", 13, j + 1, 8, None, None, None,
                None)
               for j in range(N_BLANK)])
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
        #: WHICH unit column names the wafer. `frame.wafer` is read through THIS plus the
        #: attribution join below, so a deployment moves the identity by editing these two
        #: and nothing else — see `test_the_identity_follows_the_declaration`.
        "ledger_subject": {"type": "Wafer", "key": "wafer", "column": "base_wafer_id"},
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


# ------------------------------------------------- who the frame IS: the base wafer id
def test_the_frame_names_the_bonded_base_wafer_and_never_samples_one(pg):
    """🔴 P0 item 5 (「본딩 base wf 축으로 리스트」). The strip is listed by bonded base
    wafer and labelled with its id, so the frame has to CARRY the id — `map_id` is
    `{lot}_{slot}`, a frame key, and a screen that printed it under a wafer heading would
    be naming the wafer after something that is not its name.

    Asserted together with its negative, because the two candidate implementations differ
    ONLY there: `BOND_LOT`'s frame carries six base wafers, so an implementation that took
    the first value it saw would label six wafers' dies with one wafer's id — the same
    flattening `MAP_REASON_FRAME_AMBIGUOUS` is named after, one field over. The field is
    absent there, and present exactly where the frame IS one wafer.
    """
    one = _axis(ledger_lots.lot_map(pg, row=WAFER_LOT, slot=str(WAFER_SLOT)), "bond")
    assert one["state"] == ledger_lots.MAP_STATE_READY, one
    assert one["frame"]["map_id"] == f"{WAFER_LOT}_{WAFER_SLOT}"
    assert one["frame"][ledger_lots.IDENTITY_FIELD] == WAFER_ID, \
        "the frame of a single bonded base wafer must name it"

    many = _axis(ledger_lots.lot_map(pg, row=BOND_LOT, slot="3"), "bond")
    assert many["state"] == ledger_lots.MAP_STATE_READY, many
    assert ledger_lots.IDENTITY_FIELD not in many["frame"], (
        f"a frame carrying {N_A} base wafers named one of them: "
        f"{many['frame'].get(ledger_lots.IDENTITY_FIELD)!r}")


def test_a_frame_with_no_recorded_base_identity_omits_the_field_and_still_opens(pg):
    """MEASURED on `assy_manager` 2026-08-14: 5 of 108 bond lots (`BS-2601-001..005`,
    5,296 rows) carry no `base_id` at all, their frames are registered, and the operator
    still opens them. So the absent identity must cost the map nothing — the projection is
    `ready`, the grid is served, and the FIELD is simply not there. Not `null` dressed as a
    name, not the frame key wearing a wafer's heading."""
    bond = _axis(ledger_lots.lot_map(pg, row=BLANK_LOT, slot=str(WAFER_SLOT)), "bond")
    assert bond["state"] == ledger_lots.MAP_STATE_READY, bond
    assert bond["frame"]["map_id"] == f"{BLANK_LOT}_{WAFER_SLOT}", \
        "a lot with no base identity must still get its registered frame"
    assert _grid(bond)["grid_cols"] == 9
    assert ledger_lots.IDENTITY_FIELD not in bond["frame"], (
        f"an identity was invented for a lot that records none: "
        f"{bond['frame'].get(ledger_lots.IDENTITY_FIELD)!r}")


def test_the_identity_follows_the_declaration_and_is_no_column_name_in_code(pg):
    """🔴 THE STANDING COMPLETION CRITERION, DRIVEN: a feature is complete only if it fires
    in a different-schema deployment by swapping DECLARATIONS, with zero code change.

    The same planted rows are read three times under three declarations, and they answer
    three different ways — which is only possible because no column name is typed in
    `ledger_lots.py`:

        column: base_wafer_id   ->  `BW-777`  (the wafer id, through join base_wafer_id->base_id)
        column: base_y          ->  `7`       (another unit column, through join base_y->by)
        no ledger_subject       ->  absent    (nothing declared, so nothing claimed)

    `bx` varies and `by` is constant across these rows on purpose: the two candidate
    columns give DIFFERENT answers here, so a fixture where they agreed could not tell a
    declaration-following implementation from one that reached for `base_id` directly.
    """
    import copy

    swapped = copy.deepcopy(AXES)
    swapped["geometry"]["ledger_subject"]["column"] = "base_y"
    ledger_siblings.set_axes_config(swapped)
    moved = _axis(ledger_lots.lot_map(pg, row=WAFER_LOT, slot=str(WAFER_SLOT)), "bond")
    assert moved["frame"][ledger_lots.IDENTITY_FIELD] == str(WAFER_CONSTANT_Y), \
        "the identity did not follow the declaration — a column name is baked into the code"

    undeclared = copy.deepcopy(AXES)
    undeclared["geometry"].pop("ledger_subject")
    ledger_siblings.set_axes_config(undeclared)
    silent = _axis(ledger_lots.lot_map(pg, row=WAFER_LOT, slot=str(WAFER_SLOT)), "bond")
    assert silent["state"] == ledger_lots.MAP_STATE_READY, silent
    assert ledger_lots.IDENTITY_FIELD not in silent["frame"], (
        "a geometry that declares no ledger subject must claim no identity")


# ------------------------------------------------------- the denominator layer, on the wire
# 🔴 These need no database: `relation_exists` is stubbed so the frame lookups take their
# absent branch, which leaves exactly the CELL rule under test. What they defend is that
# `cells[]` stopped being the found set — the middle layer of every stack.
def _map_rows(monkeypatch, rows, projected="b.bond_x AS bond_x, b.bond_y AS bond_y"):
    monkeypatch.setattr(ledger_lots, "relation_exists", lambda *a, **k: False)
    monkeypatch.setattr(ledger_lots, "_frame_key_columns",
                        lambda *a, **k: ["bond_lot", "bond_slot"])
    from datetime import datetime, timezone
    axis = type("A", (), {"name": "bond_lot", "label": "본딩 랏", "column": "bond_lot"})()
    source = type("S", (), {"relation": "bonding_log", "key_column": "bond_cell_key"})()
    window = ledger_siblings.parse_window(None)
    body = ledger_lots._map_envelope(
        None, "L-1", axis, source, None, None, "void", rows, projected,
        window, datetime(2026, 8, 14, tzinfo=timezone.utc))
    return next(p for p in body["projections"] if p["axis"] == "bond")


def test_a_position_that_was_never_inspected_is_not_a_scanned_one(monkeypatch):
    """🔴 THE REASON THERE ARE THREE VALUES AND NOT TWO. Measured on `SYN-BW-101-07`: 141
    bonded positions, 29 inspected, 26 with a finding. Tagging the other 112 as `scanned`
    would be a false claim about 112 of 141 — the same 「미검사 ≠ 0」 rule this module
    already enforces for its grid cells."""
    # (x, y, lot, slot, is_found, is_scanned)
    rows = [(1, 1, "L", "01", True, True),      # found
            (2, 2, "L", "01", False, True),     # inspected, nothing found
            (3, 3, "L", "01", False, False)]    # bonded, never inspected
    proj = _map_rows(monkeypatch, rows)
    states = {(c["x"], c["y"]): c["state"] for c in proj["cells"]}
    assert states == {(1, 1): ledger_lots.MAP_CELL_FOUND,
                      (2, 2): ledger_lots.MAP_CELL_SCANNED,
                      (3, 3): ledger_lots.MAP_CELL_UNSCANNED}
    # 🔴 The two that must never merge, said as an assertion rather than as a comment.
    assert states[(2, 2)] != states[(3, 3)]


def test_cells_stopped_being_the_found_set_but_n_did_not_change_meaning(monkeypatch):
    """`cells[]` now carries the denominator; `n` still counts findings, so a consumer
    that reads `n` is unaffected and one that counted ROWS must filter on `state`."""
    rows = [(1, 1, "L", "01", True, True), (1, 1, "L", "01", True, True),
            (2, 2, "L", "01", False, True), (3, 3, "L", "01", False, False)]
    proj = _map_rows(monkeypatch, rows)
    assert len(proj["cells"]) == 3                     # every present position
    by_pos = {(c["x"], c["y"]): c for c in proj["cells"]}
    assert by_pos[(1, 1)]["n"] == 2                    # findings at that position
    assert by_pos[(2, 2)]["n"] == 0 and by_pos[(3, 3)]["n"] == 0
    # The projection counters keep counting ROWS, and `sum(n)` still equals `found`.
    assert proj["found"] == 2 and proj["scanned"] == 3
    assert sum(c["n"] for c in proj["cells"]) == proj["found"]


def test_a_refusing_projection_reports_how_many_frames_it_is_superposing(monkeypatch):
    """A row spanning several frames is a SUPERPOSITION, and the count is the fact that
    makes it readable as one. Without a frame relation there is no grid to agree on, so
    the basis is absent rather than assumed."""
    rows = [(1, 1, "L", "01", True, True), (2, 2, "L", "02", True, True)]
    proj = _map_rows(monkeypatch, rows)
    frame = proj["frame"]
    assert proj["state"] == ledger_lots.MAP_STATE_NO_FRAME
    assert frame["frames_considered"] == 2 and frame["superposed"] is True
    # 🔴 No frame relation deployed -> nothing matched -> NO grid invented.
    assert frame["frames_matched"] == 0
    assert "grid" not in frame and "valid_die_ref" not in frame
