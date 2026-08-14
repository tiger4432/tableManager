"""The two batched reads must answer exactly what the per-map loop answered.

WHY THIS FILE EXISTS
`build_alignment_view` stopped reading source cells one map at a time (b510df2). One
grouped read now covers most maps and the old per-map query still runs for the rest, so
the batch is only allowed to serve a map where it is PROVABLY the loop's own row set.
Three conditions decide that, and the load-bearing one is the round trip:
`compose_map_id` joins key values with `_` and the loop takes them apart with
`split('_')`, so a `_` inside an earlier key value makes the two disagree. Measured on the
isolated development database (NOT production): 170 of 1,443 `(core_lot, core_slot)`
tuples are that shape (`CL_2601_005_A5`), and those maps read ZERO cells today - that is
what `_no_cell_refusal`'s `key_ambiguous` names.

🔴 SERVING ONE OF THOSE MAPS FROM THE BATCH IS A RULING, NOT AN OPTIMISATION. It would
   put cells on the operator's screen that this endpoint does not show today. The first
   version of the change gated the whole REQUEST on this and was caught only by an
   unchanged row in an A/B table; the committed gate is per MAP, and a mutation that
   drops it rang NOTHING in this suite before this file existed (measured: 72 failed
   before, 72 failed with the gate removed).

WHAT IS DELIBERATELY NOT HERE
- `_count_cells_bulk`'s VALUES in bulk. `test_map_alignment_references.py` and
  `test_map_alignment_worklist.py` already ring on a count that is off by one, so a
  "bulk equals per-candidate" test here would be a second spelling of coverage that
  exists. Only the EXCLUSION - the case where the two read different questions - is
  pinned below, because that one rang nothing. (It was a whole-table DECLINE until
  R-2026-08-14-A F2; one bad id cost every other candidate on that table its grouped
  read, and the tests here now pin the per-map shape instead. The caller half - that
  an excluded id still reaches the operator with its honest per-candidate count -
  lives in `test_map_alignment_references.py`, next to the prefetch test it shares a
  fixture with.)
- Cell ORDER. 🔴 THIS PARAGRAPH DESCRIBED A DEFECT, NOT A DESIGN, AND R7 CLOSED IT
  (2026-08-13). It used to read "Neither the loop nor the batch declares an `ORDER BY`,
  and the truncated read is already known to be nondeterministic about which rows
  survive the cap" -- and treated that as a promise worth honouring rather than a bug
  worth naming. It was measured: one capped read returned genuinely DIFFERENT cells
  between runs, and `_unit_maps` survived 16 identical repeats before failing the
  moment the planner was allowed to pick another plan. Both reads now carry a total
  order, pinned by `test_capped_reads_have_a_total_order.py`.
  Row sets are still compared here as MULTISETS -- deliberately, and for a different
  reason than before: this file asks whether the loop and the batch read the same
  QUESTION, and ordering is now someone else's pinned invariant. Do not turn this into
  a second spelling of that test.
"""
import json

import pytest

import map_alignment as ma
import map_overlay
from database import crud, models

# Prefixed so a table of the same name in the operator's gitignored
# `config/table_config.json` cannot win the shared in-memory schema (the trap
# `test_map_alignment_worklist.py` documents: `create_all(checkfirst)` then skips, and
# it surfaces months later as `no such column`).
SRC = "abr_test_log"
DERIVED = "abr_test_unit"
MAPT = "abr_test_map"
FLOOR = "abr_test_floor"
FLOOR1 = "abr_test_floor1"      # the same shape keyed on ONE column

PHYS = {"phys_wafer_dia": 300.0, "phys_chip_x": 7.0, "phys_chip_y": 7.0,
        "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0}

RULE = {"name": "abr_test_rule", "source_table": SRC, "derived_table": DERIVED,
        "decision_key": ["eqp", "product"], "target_fields": ["core_frame"],
        "list_columns": ["cell_count"]}

KEY_COLS = ["lot", "slot"]

TABLES = {
    # The `dt_log` shape: the DECISION key (eqp, product) and the MAP key (lot, slot) are
    # different columns, so one map can hold rows belonging to more than one unit. That
    # is what makes "the batch must honour the request's own predicates" a real question
    # rather than a hypothetical one.
    SRC: {"business_key": "cell_key",
          "column_types": {"cell_key": "string", "eqp": "string", "product": "string",
                           "lot": "string", "slot": "string",
                           "sx": "number", "sy": "number", "bn": "string"},
          "map_key_columns": KEY_COLS},
    DERIVED: {"business_key": "unit_key", "composite_key_separator": "|",
              "composite_key_source": ["eqp", "product"],
              "column_types": {"unit_key": "string", "eqp": "string",
                               "product": "string", "cell_count": "number"}},
    MAPT: {"business_key": "cell_key",
           "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                            "sx": "number", "sy": "number", "bn": "string"},
           "map_key_columns": KEY_COLS},
    # `_count_cells_bulk` resolves its key columns through `map_overlay.resolve_binding`,
    # which with an empty cfg needs coordinates named `x`/`y` and a value candidate as
    # well as `map_key_columns`. This table is that shape; SRC/MAPT deliberately are not,
    # because the view path takes its coordinate columns as ARGUMENTS.
    FLOOR: {"business_key": "cell_key",
            "column_types": {"cell_key": "string", "lot": "string", "slot": "string",
                             "x": "number", "y": "number", "val": "string"},
            "map_key_columns": KEY_COLS},
    # 🔴 The same floor shape with ARITY ONE. An id carrying no separator is CORRECT
    #    here, so this table is what stops a repair from counting separators without
    #    asking how many the table declares. Whoever writes the rule as "must contain a
    #    `_`" turns this table's healthy ids into excluded ones.
    FLOOR1: {"business_key": "cell_key",
             "column_types": {"cell_key": "string", "job": "string",
                              "x": "number", "y": "number", "val": "string"},
             "map_key_columns": ["job"]},
    # Product-owned, copied verbatim from `table_config.json` for the reason every other
    # alignment fixture copies it: `Base.metadata` outlives one test, so a fixture that
    # invents a different shape breaks the first run and passes every run after it.
    map_overlay.META_TABLE: {"business_key": "map_pk",
                             "composite_key_source": ["target_table", "map_id"],
                             "column_types": {"map_pk": "string",
                                              "target_table": "string",
                                              "map_id": "string",
                                              "grid_metadata": "string"}},
}

#: A lot name carrying the separator. Copied from real data rather than invented: on the
#: isolated development database 170 of 1,443 `(core_lot, core_slot)` tuples look like this.
AMBIGUOUS_LOT = "CL_2601_005"
AMBIGUOUS_ID = "CL_2601_005_21"       # compose_map_id(("CL_2601_005", "21"))
PLAIN_ID = "PLAIN_07"                 # compose_map_id(("PLAIN", "07"))

CAP = ma.MAX_PAYLOAD_CELLS


@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    map_overlay._FRAME_TF_CACHE.clear()
    return db_session


def _meta(**kw):
    m = {"grid_cols": 13, "grid_rows": 13, "rotation": 0, "side": "front",
         "grid_y_invert": False, "grid_start_x": 1, "grid_start_y": 1}
    m.update(PHYS)
    m.update(kw)
    return m


def _src(db, rows, eqp="E1", product="P1"):
    """`rows` = [(lot, slot, sx, sy), ...]. `lot=None` seeds a NULL map key."""
    s = models.DYNAMIC_TABLES[SRC]
    for i, (lot, slot, sx, sy) in enumerate(rows):
        db.add(s(row_id="s_%s_%s_%d" % (eqp, product, i),
                 business_key_val="s_%s_%s_%d" % (eqp, product, i),
                 cell_key="s_%s_%s_%d" % (eqp, product, i),
                 eqp=eqp, product=product, lot=lot, slot=slot,
                 sx=sx, sy=sy, bn="1"))
    db.commit()


def _register_maps(db, map_ids):
    """A `wafer_map_metadata` row per map, so the view path runs its real meta read."""
    meta_model = models.DYNAMIC_TABLES[map_overlay.META_TABLE]
    for mid in map_ids:
        db.add(meta_model(row_id="m_%s_%s" % (MAPT, mid),
                          business_key_val="%s|%s" % (MAPT, mid),
                          target_table=MAPT, map_id=mid,
                          grid_metadata=json.dumps(_meta())))
    db.commit()


def _batch(db, filters=(), cell_cap=CAP, key_cols=KEY_COLS):
    """`_source_rows_by_map` called exactly the way `build_alignment_view` calls it."""
    m = models.DYNAMIC_TABLES[SRC]
    key_attrs = [getattr(m, c) for c in key_cols]
    q_cols = [m.sx, m.sy]
    id_rows = db.query(*key_attrs).filter(*filters).distinct().all()
    got, servable = ma._source_rows_by_map(
        db, key_attrs, key_cols, list(filters), q_cols, id_rows, cell_cap)
    return got, servable, id_rows, q_cols


def _loop_rows(db, mid, q_cols, filters=(), key_cols=KEY_COLS):
    """The per-map read `build_alignment_view` still runs for maps the batch declines.

    Spelled the way the caller spells it - `mid.split('_')[i]`, NOT
    `map_overlay.map_key_parts` - because the two disagree on exactly the ids this file
    is about, and copying the wrong one would compare the batch against a predicate the
    endpoint never runs.
    """
    m = models.DYNAMIC_TABLES[SRC]
    f = list(filters)
    for i, c in enumerate(key_cols):
        part = mid if len(key_cols) == 1 else mid.split("_")[i]
        f.append(getattr(m, c) == part)
    return db.query(*q_cols).filter(*f).limit(CAP + 1).all()


def _view(db, **kw):
    kw.setdefault("x_col", "sx")
    kw.setdefault("y_col", "sy")
    return ma.build_alignment_view(db, {}, RULE, {"eqp": "E1", "product": "P1"},
                                   MAPT, **kw)


# ---------------------------------------------------------------------------
# 1. the batch is the loop, map for map - including the request's own predicates
# ---------------------------------------------------------------------------

def test_the_batch_is_the_per_map_loop_row_for_row(env):
    """Every map the batch claims to cover must hold the loop's row set for that map.

    The fixture puts the SAME map id under two decision units, which is the `dt_log`
    shape (the map key is `lot`/`slot`, the decision key is `eqp`/`product`) and is also
    what the chain's `source_filters` call does. A batch that grouped the whole table
    instead of the filtered rows would hand unit E1 unit E2's cells and no per-map
    comparison against an unfiltered loop would notice - so the loop is asked with the
    same filters the batch was given.
    """
    _src(env, [("L1", "01", 1, 1), ("L1", "01", 2, 2), ("L1", "01", 3, 3),
               ("L2", "02", 4, 4), ("L2", "02", 5, 5)], eqp="E1", product="P1")
    _src(env, [("L1", "01", 101, 101), ("L1", "01", 102, 102)],
         eqp="E2", product="P2")

    m = models.DYNAMIC_TABLES[SRC]
    filters = [m.eqp == "E1", m.product == "P1"]
    got, servable, id_rows, q_cols = _batch(env, filters)

    # A positive control FIRST. `servable == set()` is the decline answer, and every
    # assertion below is vacuously true on it - a fixture that quietly stopped reaching
    # the fast path would leave this test green while testing nothing.
    assert servable == {"L1_01", "L2_02"}
    assert len(id_rows) == 2

    for mid in sorted(servable):
        loop = [tuple(r) for r in _loop_rows(env, mid, q_cols, filters)]
        assert sorted(loop) == sorted(got.get(mid, [])), mid
    assert sorted(got) == ["L1_01", "L2_02"]
    # The other unit's rows are in the table and must not be in this answer.
    assert sum(len(v) for v in got.values()) == 5
    assert all(r[0] < 100 for rows in got.values() for r in rows)


# ---------------------------------------------------------------------------
# 2. 🔴 the ruling: a map id the loop cannot take apart is not served
# ---------------------------------------------------------------------------

def test_a_map_id_the_loop_cannot_take_apart_is_not_served_from_the_batch(env):
    """The mechanism. `CL_2601_005` + `21` composes to `CL_2601_005_21`, which the
    caller's `split('_')` reads back as `lot='CL'`, `slot='2601'` - a different map, and
    one with no rows. The batch groups by the real key tuple, so it WOULD find those
    cells; the gate is what stops it.

    Asserted in both directions on purpose. `not in servable` alone also passes when the
    batch declined the whole request, which is the version of this change that shipped
    first and cost a round - `PLAIN_07 in servable` is what separates the gate from the
    surrender.
    """
    # The two ids are written out below as literals because that is what makes the shape
    # readable, but the literal must be the composer's own output - otherwise a change to
    # the separator would leave this test green and testing nothing.
    assert (ma.compose_map_id((AMBIGUOUS_LOT, "21")),
            ma.compose_map_id(("PLAIN", "07"))) == (AMBIGUOUS_ID, PLAIN_ID)

    _src(env, [(AMBIGUOUS_LOT, "21", 1, 1), (AMBIGUOUS_LOT, "21", 2, 2),
               ("PLAIN", "07", 3, 3), ("PLAIN", "07", 4, 4)])
    got, servable, _ids, _q = _batch(env)

    assert PLAIN_ID in servable, (
        "the whole request must not be surrendered because one id does not decompose")
    assert AMBIGUOUS_ID not in servable, (
        "a map id the loop cannot decompose must fall back to the loop, which reads "
        "zero cells for it - the batch must not answer differently")
    assert AMBIGUOUS_ID not in got
    assert len(got[PLAIN_ID]) == 2


def test_the_view_still_reads_zero_cells_for_a_map_id_it_cannot_take_apart(env):
    """The same guard where the operator meets it: `sources.maps[].cell_count`.

    This is the assertion that outlives the helper. `key_ambiguous` maps render empty
    today, and making them render full is a change to what the screen MEANS - it is the
    product owner's call, not a side effect of a speed-up. The loop's own predicate is
    asserted alongside, so a future reader can see that zero is the endpoint's answer
    rather than this test's opinion.
    """
    _src(env, [(AMBIGUOUS_LOT, "21", 1, 1), (AMBIGUOUS_LOT, "21", 2, 2),
               ("PLAIN", "07", 3, 3), ("PLAIN", "07", 4, 4)])
    _register_maps(env, [AMBIGUOUS_ID, PLAIN_ID])

    m = models.DYNAMIC_TABLES[SRC]
    assert _loop_rows(env, AMBIGUOUS_ID, [m.sx, m.sy]) == [], (
        "the per-map predicate this endpoint runs finds nothing for this id; if that "
        "ever changes, this test's premise is gone and the ruling must be re-taken")

    view = _view(env, include_cells=True)
    counts = {mp["map_id"]: mp["cell_count"] for mp in view["sources"]["maps"]}
    assert counts == {AMBIGUOUS_ID: 0, PLAIN_ID: 2}
    assert view["sources"]["cell_count"] == 2
    assert sorted(view["sources"]["cells"]) == [[3, 3], [4, 4]]


# ---------------------------------------------------------------------------
# 3. the bound is the loop's own bound
# ---------------------------------------------------------------------------

def test_the_batch_declines_rather_than_read_past_the_per_map_caps(env):
    """One global `LIMIT` cannot honour N per-map ceilings: it can hand every row it is
    allowed to read to the first map and leave the next one empty. So past
    `servable x (cell_cap + 1)` the batch declines and the caller pays exactly what it
    used to pay, which is the old cost and the old answer.
    """
    _src(env, [("L1", "01", i, i) for i in range(10)])

    # Positive control: this fixture DOES reach the fast path when the cap allows it,
    # so the decline below is the cap's doing and not the fixture's.
    got_ok, servable_ok, _i, _q = _batch(env, cell_cap=CAP)
    assert servable_ok == {"L1_01"} and len(got_ok["L1_01"]) == 10

    got, servable, _ids, _q = _batch(env, cell_cap=2)     # budget = 1 x 3 < 10 rows
    assert (got, servable) == ({}, set())


# ---------------------------------------------------------------------------
# 4. a NULL map key keeps the empty cell list it has today
# ---------------------------------------------------------------------------

def test_a_null_map_key_keeps_the_empty_cell_list_it_has_today(env):
    """`compose_map_id` turns a NULL key part into `''`, and the loop then matched
    `lot == ''`, which a NULL row never satisfies. The grouping would satisfy it, so the
    NULL rows are dropped from the batch - the map composed out of NULL keeps reading
    empty exactly as before.
    """
    _src(env, [(None, "07", 9, 9), ("PLAIN", "07", 3, 3), ("PLAIN", "07", 4, 4)])
    got, servable, _ids, q_cols = _batch(env)

    assert "_07" in servable, "the NULL-keyed map is covered - with no rows, not skipped"
    assert _loop_rows(env, "_07", q_cols) == [], (
        "the per-map predicate never matched the NULL row either")
    assert got.get("_07", []) == []
    # Positive control: the ordinary map in the same call still gets its rows.
    assert len(got[PLAIN_ID]) == 2


# ---------------------------------------------------------------------------
# 5. the bulk cell count excludes an id it cannot answer - that id ALONE
# ---------------------------------------------------------------------------

def _seed_floor(db, rows):
    """`rows` = [(lot, slot, x, y), ...] into the floor-shaped table."""
    f = models.DYNAMIC_TABLES[FLOOR]
    for i, (lot, slot, x, y) in enumerate(rows):
        db.add(f(row_id="f%d" % i, business_key_val="f%d" % i, cell_key="f%d" % i,
                 lot=lot, slot=slot, x=x, y=y, val="1"))
    db.commit()


def _seed_floor1(db, rows):
    """`rows` = [(job, x, y), ...] into the SINGLE-key floor table."""
    f = models.DYNAMIC_TABLES[FLOOR1]
    for i, (job, x, y) in enumerate(rows):
        db.add(f(row_id="g%d" % i, business_key_val="g%d" % i, cell_key="g%d" % i,
                 job=job, x=x, y=y, val="1"))
    db.commit()


def test_an_id_that_does_not_decompose_is_excluded_alone(env):
    """🔴 THE RULING (R-2026-08-14-A F2). One id that cannot be taken apart used to
    decline the count for the WHOLE table, so every healthy candidate on it paid the
    per-candidate scan the batch exists to remove. The exclusion is now per map, the same
    shape `_source_rows_by_map` already had (`b510df2`).

    THE FIXTURE HAS BOTH KINDS ON ONE TABLE ON PURPOSE. With only the bad id present the
    old rule and the new rule return the same thing - `{}` and nothing covered - so such a
    fixture decides nothing. The two healthy ids in the SAME call are what separates them:
    the old rule returns `({}, False)` here, and `L1_01` below is the assertion that fails
    on it.

    `map_key_parts` falls back to matching the WHOLE id against the FIRST key column when
    an id carries too few separators, so for `nounderscore` the per-candidate `COUNT(*)`
    asks "how many rows have `lot = 'nounderscore'`" - a different question from the
    grouped `(lot, slot)` key, with a different answer. The numbers are the point: the
    honest per-candidate answer is 2 and a bulk read that answered anyway would report 0.
    `cell_count` is what lets an operator tell "no cells at all" apart from "has cells but
    they do not read", so a fabricated 0 is not a smaller number, it is the wrong one of
    those two states.
    """
    _seed_floor(env, [("nounderscore", "01", 1, 1), ("nounderscore", "02", 2, 2),
                      ("L1", "01", 3, 3), ("L2", "02", 4, 4), ("L2", "02", 5, 5)])

    counts, servable = ma._count_cells_bulk(
        env, {}, FLOOR, ["L1_01", "nounderscore", "L2_02"])

    assert servable == {"L1_01", "L2_02"}, (
        "one undecomposable id must not cost its neighbours the grouped read")
    assert counts == {"L1_01": 1, "L2_02": 2}
    assert "nounderscore" not in counts, (
        "an id outside `servable` must carry NO number here - a 0 sitting in the dict is "
        "one `counts.get(id, 0)` away from being served as an empty floor")
    # What the caller falls back to, and what a served answer would have contradicted.
    assert ma._count_cells(env, {}, FLOOR, "nounderscore") == 2


def test_a_single_key_floor_never_calls_a_separatorless_id_undecomposable(env):
    """🔴 THE TRAP THE RULING NAMES. "map_id without a separator" is a defect only where
    the DECLARED arity demands one. This table declares one key column, so `AAA` is an
    ordinary id and `MID_01` is an ordinary id too - `map_key_parts` gives the whole
    string to the single column either way. A rule that counted separators instead of
    reading the declaration would exclude every id on this table and send the operator to
    rename maps that were fine.

    Arity is read from the RESOLVED binding, per table. Asserted here rather than assumed,
    because that is the input the exclusion is computed from.
    """
    b = map_overlay.resolve_binding({}, FLOOR1)
    assert b["key_columns"] == ["job"], "premise: this floor is keyed on ONE column"

    _seed_floor1(env, [("AAA", 1, 1), ("AAA", 2, 2), ("MID_01", 3, 3)])
    counts, servable = ma._count_cells_bulk(env, {}, FLOOR1, ["AAA", "MID_01", "GONE"])

    assert servable == {"AAA", "MID_01", "GONE"}, (
        "no id on a single-key floor can be undecomposable")
    assert counts == {"AAA": 2, "MID_01": 1, "GONE": 0}, (
        "`GONE` is covered and genuinely empty - which is exactly the state an excluded "
        "id must NOT be confused with")


def test_an_id_with_extra_separators_is_covered_and_agrees_with_the_loop(env):
    """The other side of the arity question, and the reason the exclusion is "too FEW
    parts" rather than "not exactly `n` parts". `map_key_parts` lets the last column
    absorb the remainder, so `A_B_C` on a two-column key decomposes into exactly two parts
    - the wrong two, but the SAME wrong two the per-candidate `COUNT(*)` binds. Both
    answer 0, so there is nothing to exclude and excluding it would only cost a scan.
    """
    _seed_floor(env, [("A_B", "C", 1, 1), ("L1", "01", 3, 3)])

    counts, servable = ma._count_cells_bulk(env, {}, FLOOR, ["A_B_C", "L1_01"])
    assert "A_B_C" in servable and counts["A_B_C"] == 0
    assert ma._count_cells(env, {}, FLOOR, "A_B_C") == 0, (
        "the per-candidate predicate binds lot='A', slot='B_C' and finds nothing either "
        "- if this ever stops being true the batch is no longer the loop for this id")


def test_a_table_level_obstacle_still_declines_the_whole_table(env):
    """Not every decline became per-map, and it must not. "This table has no model" is a
    property of the TABLE - it is not true of one candidate and false of its neighbour, so
    no per-map answer exists on it and the caller counts every candidate the old way. An
    empty `servable` is how that is said, and it is the same sentence as before.
    """
    assert "abr_test_no_such_table" not in models.DYNAMIC_TABLES
    counts, servable = ma._count_cells_bulk(env, {}, "abr_test_no_such_table", ["L1_01"])
    assert (counts, servable) == ({}, set())
