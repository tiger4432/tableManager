"""Every capped read on the map screens must cut by a TOTAL order (`SCHEMA_CANON` R7).

WHY THIS FILE EXISTS
A `LIMIT` without an `ORDER BY` does not return "some rows" - it returns whichever rows
the plan happened to produce first, and that is a property of the heap, the plan and the
moment, not of the data. On the map screens the consequence is the worst shape a defect
can take: **the operator sees different cells on every refresh and nothing errors.**
Measured on the isolated development database before this repair - `GET
/api/maps/overlay?limit=50` over a 10,000-cell map returned TWO distinct cell sets over
16 identical requests, and the same 20,000 rows written to the heap in two different
orders answered the same capped query with two different sets of 50 cells.

HOW THIS FILE RINGS
Every fixture below is inserted in REVERSE raster order. On the suite's SQLite backend an
unordered scan returns rows in insertion order, so a read that lost its `ORDER BY` hands
back the BOTTOM of the map while the assertion asks for the top. That is deliberate: an
alarm that only rings when a query planner changes its mind is an alarm nobody can test.
Verified by injection - neutering `Query.order_by` turns each ordered case below red.

WHAT THE ORDER IS, AND WHY
`(y, x, row_id)`. `(y, x)` is raster order, the order a map is read in, so a truncated
map is the TOP OF THE MAP rather than a scatter the operator cannot place; it is also
this module's existing spelling of canonical position (`map_alignment._seat_cost`).
`row_id` is last and is not decoration: duplicate coordinates inside one map are real -
measured on the development database, `core_defect_map` has 2,576 duplicate-coordinate
groups in 5,152 rows - so `(y, x)` alone leaves ties, and a tie is the planner's choice
again. `row_id` is the primary key of every dynamic table, which makes the order total.

WHAT IS DELIBERATELY NOT HERE
- `_resolve_valid_die_uncached`. Its `LIMIT` never cuts: one row past the cap and the
  whole reference is refused, and the result is a `frozenset`. It has no order to get
  wrong, and giving it one costs 22x on exactly the maps that refuse (measured). If that
  refusal is ever softened into a truncation this file must grow a case for it.
- `resolve_reference_catalog`. Its floor tables are hard-wired product names
  (`floor_tables()`), so `test_map_alignment_references.py` owns that fixture; only the
  tie-break added to it is noted here.
"""
import json

import pytest

import map_alignment as ma
import map_overlay
from database import crud, models

# Prefixed so a table of the same name in the operator's gitignored
# `config/table_config.json` cannot win the shared in-memory schema (the trap
# `test_map_alignment_worklist.py` documents: `create_all(checkfirst)` then skips, and it
# surfaces months later as `no such column`).
SRC = "r7ord_test_log"
DERIVED = "r7ord_test_unit"
MAPT = "r7ord_test_map"
OVL = "r7ord_test_overlay"

PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}

KEY_COLS = ["lot", "slot"]

RULE = {"name": "r7ord_test_rule", "source_table": SRC, "derived_table": DERIVED,
        "decision_key": ["eqp", "product"], "target_fields": ["core_frame"],
        "list_columns": []}

TABLES = {
    SRC: {"business_key": "cell_key",
          "column_types": {"cell_key": "string", "eqp": "string", "product": "string",
                           "lot": "string", "slot": "string",
                           "sx": "number", "sy": "number", "bn": "string"},
          "map_key_columns": KEY_COLS},
    DERIVED: {"business_key": "unit_key", "composite_key_separator": "|",
              "composite_key_source": ["eqp", "product"],
              "column_types": {"unit_key": "string", "eqp": "string",
                               "product": "string"}},
    MAPT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                            "sx": "number", "sy": "number", "bn": "string"},
           "map_key_columns": KEY_COLS},
    # `_cells_of` and `get_overlay` derive their binding through
    # `map_overlay.resolve_binding`, which with an empty cfg wants `x`/`y` plus a value
    # candidate as well as `map_key_columns`. This table is that shape; SRC is not, on
    # purpose - the view path takes its coordinate columns as ARGUMENTS.
    OVL: {"business_key": "cell_key",
          "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                           "x": "number", "y": "number", "val": "string"},
          "map_key_columns": KEY_COLS},
    # Product-owned, copied verbatim from `table_config.json` for the reason every other
    # alignment fixture copies it: `Base.metadata` outlives one test.
    map_overlay.META_TABLE: {"business_key": "map_pk",
                             "composite_key_source": ["target_table", "map_id"],
                             "column_types": {"map_pk": "string",
                                              "target_table": "string",
                                              "map_id": "string",
                                              "grid_metadata": "string"}},
}

MAP_ID = "L1_01"


@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    map_overlay._FRAME_TF_CACHE.clear()
    return db_session


def _meta(**kw):
    m = {"grid_cols": 9, "grid_rows": 9, "rotation": 0, "side": "front",
         "grid_y_invert": False, "grid_start_x": 0, "grid_start_y": 0}
    m.update(PHYS)
    m.update(kw)
    return m


def _register(db, table, map_id, meta=None, row_id=None):
    mm = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    db.add(mm(row_id=row_id or "m_%s_%s" % (table, map_id),
              business_key_val="%s|%s" % (table, map_id),
              target_table=table, map_id=map_id,
              grid_metadata=json.dumps(meta or _meta())))
    db.commit()


#: The map every cell test reads: a 3-wide, 4-tall block. Written to the table in
#: REVERSE raster order, so "the first rows the table gives back" and "the top of the
#: map" are different answers and the assertion can tell them apart.
GRID = [(x, y) for y in range(4) for x in range(3)]          # raster order
RASTER = [(float(x), float(y)) for (x, y) in GRID]


def _seed_cells(db, table, xcol="x", ycol="y", valcol="val", lot="L1", slot="01",
                cells=None):
    t = models.DYNAMIC_TABLES[table]
    rows = list(reversed(cells if cells is not None else GRID))
    for i, (x, y) in enumerate(rows):
        db.add(t(row_id="c_%s_%03d" % (table, i),
                 business_key_val="c_%s_%03d" % (table, i),
                 cell_key="c_%s_%03d" % (table, i),
                 lot=lot, slot=slot,
                 **{xcol: float(x), ycol: float(y), valcol: "%d-%d" % (x, y)}))
    db.commit()


# ---------------------------------------------------------------------------
# 1. the cell reads: a cut keeps the TOP of the map, not the head of the heap
# ---------------------------------------------------------------------------

def test_cells_of_cuts_by_raster_order_and_not_by_insertion_order(env):
    """`_cells_of` is the reference loader `/view` scores against. Truncated by heap
    order it hands the scorer a geometric corner nobody chose."""
    _seed_cells(env, OVL)
    full, _v, trunc_full, _k = ma._cells_of(env, {}, OVL, MAP_ID, 10 ** 6)
    cut, _v2, trunc, _k2 = ma._cells_of(env, {}, OVL, MAP_ID, 4)

    assert not trunc_full and sorted(full) == sorted(
        [(int(x), int(y)) for (x, y) in RASTER]), "fixture lost rows"
    # The positive control: without it a fixture that stopped truncating would leave
    # every assertion below vacuously true.
    assert trunc, "the fixture must exceed the cap or this test proves nothing"
    assert cut == [(0, 0), (1, 0), (2, 0), (0, 1)], (
        "a capped read must keep the top of the map; got %s" % cut)
    assert set(cut) <= set(full), "the cap invented a cell the uncapped read does not have"


def test_the_overlay_cut_is_the_same_cut(env):
    """`GET /api/maps/overlay?limit=N` is the operator-reachable one - this is the read
    that returned two different cell sets over 16 identical requests."""
    _seed_cells(env, OVL)
    _register(env, OVL, MAP_ID)
    o = map_overlay.get_overlay(env, {}, OVL, MAP_ID, [(OVL, MAP_ID)], cell_cap=4)
    entry = o["overlays"][0]
    assert entry["status"] == map_overlay.STATUS_OK, entry.get("detail")
    assert entry["truncated"], "the fixture must exceed the cap"
    assert [(c["x"], c["y"]) for c in entry["cells"]] == [(0, 0), (1, 0), (2, 0), (0, 1)]


def test_the_view_per_map_read_cuts_by_the_same_key(env):
    """The map a batch cannot cover is read one map at a time. That statement cuts too,
    and it must lose the same cells `_cells_of` loses - otherwise the same map answers
    differently depending on which route reached it."""
    _seed_cells(env, SRC, xcol="sx", ycol="sy", valcol="bn")
    _register(env, MAPT, MAP_ID)
    v = ma.build_alignment_view(env, {}, RULE, {}, MAPT, cell_cap=4,
                                x_col="sx", y_col="sy")
    assert v["sources"]["truncated"], "the fixture must exceed the cap"
    assert v["sources"]["cells"][:4] == [[0, 0], [1, 0], [2, 0], [0, 1]], \
        v["sources"]["cells"]


# ---------------------------------------------------------------------------
# 2. duplicate coordinates: `(y, x)` is not a total order on real data
# ---------------------------------------------------------------------------

def test_a_duplicate_coordinate_is_broken_by_row_id_and_not_by_the_planner(env):
    """Two rows at the same seat are not hypothetical - `core_defect_map` has 2,576 such
    groups in 5,152 rows. With `(y, x)` alone the cut would be a coin toss between two
    DIFFERENT values at the same coordinate, which reads as a value defect and not as an
    ordering one."""
    t = models.DYNAMIC_TABLES[OVL]
    for i, (rid, val) in enumerate((("c_dup_z", "second"), ("c_dup_a", "first"))):
        env.add(t(row_id=rid, business_key_val=rid, cell_key=rid, lot="L1", slot="01",
                  x=0.0, y=0.0, val=val))
    env.commit()
    cells, values, trunc, _k = ma._cells_of(env, {}, OVL, MAP_ID, 1)
    assert trunc and cells == [(0, 0)]
    assert values == ["first"], (
        "the tie must be broken by row_id (c_dup_a < c_dup_z), got %s" % values)


# ---------------------------------------------------------------------------
# 3. the batched read: it may not hand the caller a list the caller has to cut
# ---------------------------------------------------------------------------

def _batch(db, cell_cap):
    m = models.DYNAMIC_TABLES[SRC]
    key_attrs = [getattr(m, c) for c in KEY_COLS]
    q_cols = [m.sx, m.sy]
    id_rows = db.query(*key_attrs).distinct().all()
    return q_cols, ma._source_rows_by_map(db, key_attrs, KEY_COLS, [], q_cols,
                                          id_rows, cell_cap)


def test_a_map_over_the_cap_is_not_served_from_the_unordered_batch(env):
    """The batch read has a `LIMIT` and deliberately no `ORDER BY` - ordering it would
    make its DECLINE decision pay for a full sort (measured: 10.4 ms -> 366.9 ms on
    2,000,000 rows). What keeps it honest instead is that nothing it returns is ever
    cut: a map over the per-map cap leaves `servable`, and the caller re-reads that one
    through the ordered per-map statement."""
    _seed_cells(env, SRC, xcol="sx", ycol="sy", valcol="bn")
    # Three one-cell maps beside the 12-cell one. Without them the budget
    # (`servable x (cap + 1)` = 1 x 5) is under the 12 rows and the batch declines for a
    # DIFFERENT reason - which would make the assertion below vacuously true and this
    # test a no-op. With them: 4 maps x 5 = 20 >= 15 rows, so the batch really does
    # serve, and the over-cap map is the only thing that may not come back.
    t = models.DYNAMIC_TABLES[SRC]
    for i in range(3):
        env.add(t(row_id="x_%d" % i, business_key_val="x_%d" % i, cell_key="x_%d" % i,
                  lot="T%d" % i, slot="01", sx=0.0, sy=0.0, bn="1"))
    env.commit()

    _q, (by_map, servable) = _batch(env, 4)
    assert servable, "the batch declined outright - this fixture must reach the fast path"
    assert {"T0_01", "T1_01", "T2_01"} <= servable, sorted(servable)
    assert MAP_ID not in servable, (
        "an over-cap map must not be served from an unordered read: %s" % sorted(servable))
    assert all(len(v) <= 4 for v in by_map.values())


def test_under_the_cap_the_batch_is_the_ordered_loop_row_for_row(env):
    """Under the cap the batch serves the map, and its list must be the ordered per-map
    statement's list EXACTLY - a map must not depend on which route answered it."""
    _seed_cells(env, SRC, xcol="sx", ycol="sy", valcol="bn")
    m = models.DYNAMIC_TABLES[SRC]
    q_cols, (by_map, servable) = _batch(env, 100)
    assert servable == {MAP_ID}
    loop = [tuple(r) for r in db_loop(env, m, q_cols)]
    assert [tuple(r) for r in by_map[MAP_ID]] == loop
    assert loop == RASTER, "the loop itself is not in raster order: %s" % loop[:5]


def db_loop(db, m, q_cols):
    return (db.query(*q_cols).filter(m.lot == "L1", m.slot == "01")
              .order_by(m.sy, m.sx, m.row_id).limit(101).all())


# ---------------------------------------------------------------------------
# 4. the list reads: which UNITS an operator can see is also a cut
# ---------------------------------------------------------------------------

def _seed_units(db, keys):
    """`keys` = [(eqp, product), ...] seeded in REVERSE, so insertion order and key
    order disagree."""
    s, d = models.DYNAMIC_TABLES[SRC], models.DYNAMIC_TABLES[DERIVED]
    for i, (eqp, product) in enumerate(reversed(keys)):
        db.add(d(row_id="u_%03d" % i, business_key_val="%s|%s" % (eqp, product),
                 unit_key="%s|%s" % (eqp, product), eqp=eqp, product=product))
        db.add(s(row_id="su_%03d" % i, business_key_val="su_%03d" % i,
                 cell_key="su_%03d" % i, eqp=eqp, product=product,
                 lot="L%s" % eqp, slot="01", sx=0.0, sy=0.0, bn="1"))
    db.commit()


UNIT_KEYS = [("E1", "P1"), ("E2", "P1"), ("E3", "P1"), ("E4", "P1")]


def test_the_worklist_cap_keeps_the_head_of_the_list_not_a_sample_of_it(env):
    _seed_units(env, UNIT_KEYS)
    w = ma.build_alignment_worklist(env, {}, RULE, MAPT, unit_cap=2)
    assert w["totals"]["units_truncated"], "the fixture must exceed the cap"
    assert [u["key"]["eqp"] for u in w["units"]] == ["E1", "E2"], w["units"]


def test_the_unit_map_pairs_cap_keeps_the_head_of_the_list(env):
    _seed_units(env, UNIT_KEYS)
    m = models.DYNAMIC_TABLES[SRC]
    pairs, trunc = ma._unit_maps(env, m, RULE["decision_key"], KEY_COLS, [], 2)
    assert trunc, "the fixture must exceed the cap"
    assert sorted(k[0] for k in pairs) == ["E1", "E2"], sorted(pairs)


# ---------------------------------------------------------------------------
# 5. `.first()` is a cap too
# ---------------------------------------------------------------------------

def test_the_metadata_read_is_deterministic_when_the_pair_is_duplicated(env):
    """`_meta_select` is `LIMIT 1` and nothing enforces one row per
    `(target_table, map_id)` - measured, `wafer_map_metadata` carries no unique index
    beyond its `row_id` primary key on either database. Undecided, one duplicated pair
    lets the SAME map read a DIFFERENT geometry from one refresh to the next: rotation,
    side, start. The oldest row wins, because every reference already written against
    this map was written against that one.

    🔴 The real repair is a unique index on the pair (`SCHEMA_CANON` R6). It lives in a
       migration; this assertion only fixes what the reader does until then.
    """
    _register(env, OVL, MAP_ID, meta=_meta(rotation=90), row_id="m_zz_second")
    _register(env, OVL, MAP_ID, meta=_meta(rotation=0), row_id="m_aa_first")
    for _ in range(4):
        assert map_overlay.load_map_meta(env, OVL, MAP_ID)["rotation"] == 0
