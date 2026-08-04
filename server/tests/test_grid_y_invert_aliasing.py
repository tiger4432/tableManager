"""MEASUREMENT: is `grid_y_invert` really redundant?

`docs/spec/MAP_ALIGNMENT_SPEC.md` section 2 claims the 16 tuples
(4 rotations x 2 sides x 2 y-inverts) collapse to 8 distinct lattice transforms,
so `grid_y_invert` never needs to appear in a candidate list.

This module does NOT trust that claim and does not trust its negation either.
It measures the EXACT composed visual -> physical mapping for all 16 tuples on a
fixture whose wafer bounding box is deliberately NOT vertically centred in the
declared grid, and reports:

  * the per-pair translation delta (exact, constant over the whole domain),
  * the number of distinct mappings compared EXACTLY,
  * the number of distinct mappings compared MODULO an arbitrary translation.

The last two numbers are the crux. Comparing modulo translation collapses to 8
by construction (translation is exactly what `grid_y_invert` contributes on top
of the linear part), so a measurement that quotiented by translation would have
printed "8" no matter what the answer was.

Two composition paths are measured, because the repository contains both:

  P1 "raw"        - the engine is built straight from the declared phys values.
                    `server/trace_fixture/frames.py:67` builds a transformer this
                    way (with no engine at all).
  P2 "production" - `server/map_overlay.py:443 _frame_transformer`, which first
                    runs the declared phys values through `_frame_phys_params`
                    (`server/map_overlay.py:392`). That function swaps the pitches
                    for 90/270 AND flips the offset signs per rotation/side.

The distinction is load-bearing and is the whole finding: the offset sign flip in
P2 mirrors the bounding box in exactly the way that cancels the delta.
"""

import itertools

import pytest

import map_overlay
from utils.coordinate_transformer import WaferMapCoordinateTransformer
from utils.physical_wafer_engine import PhysicalWaferEngine


# --- fixture -----------------------------------------------------------------
#
# Grid 25 x 19. Chip 12 x 16 mm (anisotropic, the spec's fixture). Wafer 300 mm,
# edge margin 3 mm.
#
# `phys_offset_y = 8.5` is the lever that decentres the bounding box. It is NOT a
# fraction of a pitch: the engine centres the circle on (rows-1)/2, so nothing
# about the DECLARED GRID can decentre the box - only the offset can. See
# `test_fixture_actually_decentres_the_bbox` for the attempts that do NOT work.
GRID_COLS, GRID_ROWS = 25, 19
START_X, START_Y = 3, 5
PHYS = {
    "phys_wafer_dia": 300.0,
    "phys_chip_x": 12.0,
    "phys_chip_y": 16.0,
    "phys_offset_x": 8.5,
    "phys_offset_y": 8.5,
    "phys_edge_margin": 3.0,
}

ROTATIONS = (0, 90, 180, 270)
SIDES = ("front", "back")
INVERTS = (False, True)
TUPLES = tuple(itertools.product(ROTATIONS, SIDES, INVERTS))

# The composed map is affine over Z^2 and total, so any rectangle determines it.
SAMPLE = tuple((xv, yv) for xv in range(-2, 30) for yv in range(-2, 30))


def _meta(rot, side, invert, start_x=START_X, start_y=START_Y):
    m = {
        "grid_cols": GRID_COLS, "grid_rows": GRID_ROWS,
        "grid_start_x": start_x, "grid_start_y": start_y,
        "rotation": rot, "side": side, "grid_y_invert": invert,
    }
    m.update(PHYS)
    return m


def _tf_raw(rot, side, invert, start_x=START_X, start_y=START_Y):
    """P1: declared phys values fed to the engine verbatim, no frame correction."""
    eng = PhysicalWaferEngine(
        wafer_diameter_mm=PHYS["phys_wafer_dia"],
        chip_size_x_mm=PHYS["phys_chip_x"], chip_size_y_mm=PHYS["phys_chip_y"],
        edge_exclusion_mm=PHYS["phys_edge_margin"],
        offset_x_mm=PHYS["phys_offset_x"], offset_y_mm=PHYS["phys_offset_y"])
    return WaferMapCoordinateTransformer(
        cols=GRID_COLS, rows=GRID_ROWS, start_x=start_x, start_y=start_y,
        rotation=rot, side=side, invert_y=invert, physical_engine=eng)


def _tf_prod(rot, side, invert, start_x=START_X, start_y=START_Y):
    """P2: the production spelling - `map_overlay._frame_transformer`."""
    meta = _meta(rot, side, invert, start_x, start_y)
    grid = map_overlay._grid_of(meta)
    return map_overlay._frame_transformer(meta, grid)


PATHS = {"raw": _tf_raw, "prod": _tf_prod}


def _mapping(build, rot, side, invert, start_x=START_X, start_y=START_Y):
    tf = build(rot, side, invert, start_x, start_y)
    return tuple(tf.visual_to_physical(xv, yv) for (xv, yv) in SAMPLE)


def _linear_key(mapping):
    """The mapping modulo an arbitrary translation: its linear part alone.

    SAMPLE is a lexicographic rectangle, so index 0 is (-2,-2); the images of
    (-2,-2)+(1,0) and (-2,-2)+(0,1) pin the 2x2 integer matrix.
    """
    base = mapping[0]
    i_dx = SAMPLE.index((SAMPLE[0][0] + 1, SAMPLE[0][1]))
    i_dy = SAMPLE.index((SAMPLE[0][0], SAMPLE[0][1] + 1))
    col_x = (mapping[i_dx][0] - base[0], mapping[i_dx][1] - base[1])
    col_y = (mapping[i_dy][0] - base[0], mapping[i_dy][1] - base[1])
    return (col_x, col_y)


def _constant_delta(m1, m2):
    """(dx, dy) such that m2 == m1 + (dx, dy) everywhere, or None if not constant."""
    d0 = (m2[0][0] - m1[0][0], m2[0][1] - m1[0][1])
    for a, b in zip(m1, m2):
        if (b[0] - a[0], b[1] - a[1]) != d0:
            return None
    return d0


def _clear_caches():
    map_overlay._FRAME_TF_CACHE.clear()


@pytest.fixture(autouse=True)
def _fresh_caches():
    _clear_caches()
    yield
    _clear_caches()


# --- (a) the fixture must actually activate the defect axis -------------------

def test_fixture_actually_decentres_the_bbox(capsys):
    """A harness on a centred bbox proves nothing: delta is 0 by construction.

    This test asserts the fixture is NOT centred, and records the attempts that
    fail to decentre it so nobody repeats them.
    """
    tf = _tf_raw(0, "front", False)
    min_c, max_c, min_r, max_r = tf.get_wafer_bounding_box()
    delta_y = (tf.visual_rows - 1) - (min_r + max_r)
    delta_x = (tf.visual_cols - 1) - (min_c + max_c)

    lines = ["", "== fixture bbox (raw path, rot0/front) ==",
             "bbox = (min_c=%d, max_c=%d, min_r=%d, max_r=%d)" % (min_c, max_c, min_r, max_r),
             "visual_cols-1 = %d, min_c+max_c = %d -> x-decentring = %d"
             % (tf.visual_cols - 1, min_c + max_c, delta_x),
             "visual_rows-1 = %d, min_r+max_r = %d -> y-decentring = %d"
             % (tf.visual_rows - 1, min_r + max_r, delta_y),
             "", "== attempts that do NOT decentre the bbox =="]

    # NOT a lever: extra rows in the declared grid. The engine centres the circle
    # on (rows-1)/2, so spare rows are always symmetric.
    for rows in (19, 20, 21, 25, 31):
        eng = PhysicalWaferEngine(
            wafer_diameter_mm=PHYS["phys_wafer_dia"],
            chip_size_x_mm=PHYS["phys_chip_x"], chip_size_y_mm=PHYS["phys_chip_y"],
            edge_exclusion_mm=PHYS["phys_edge_margin"], offset_x_mm=0.0, offset_y_mm=0.0)
        t = WaferMapCoordinateTransformer(cols=GRID_COLS, rows=rows, physical_engine=eng)
        _mn_c, _mx_c, mn_r, mx_r = t.get_wafer_bounding_box()
        d = (t.visual_rows - 1) - (mn_r + mx_r)
        lines.append("  declared rows=%2d, offset 0 -> y-decentring = %d" % (rows, d))
        assert d == 0, "spare rows unexpectedly decentred the bbox"

    # NOT a lever: a small offset. 0.1 mm cannot move a boundary on a 16 mm pitch.
    for oy in (0.0, 0.1, 1.0, 3.0):
        eng = PhysicalWaferEngine(
            wafer_diameter_mm=PHYS["phys_wafer_dia"],
            chip_size_x_mm=PHYS["phys_chip_x"], chip_size_y_mm=PHYS["phys_chip_y"],
            edge_exclusion_mm=PHYS["phys_edge_margin"], offset_x_mm=0.0, offset_y_mm=oy)
        t = WaferMapCoordinateTransformer(cols=GRID_COLS, rows=GRID_ROWS, physical_engine=eng)
        _mn_c, _mx_c, mn_r, mx_r = t.get_wafer_bounding_box()
        d = (t.visual_rows - 1) - (mn_r + mx_r)
        lines.append("  offset_y=%.2f mm -> y-decentring = %d" % (oy, d))
        assert d == 0, "offset_y=%.2f unexpectedly decentred the bbox" % oy

    # NOT a lever: no engine at all (the analytic ellipse fallback is symmetric).
    t = WaferMapCoordinateTransformer(cols=GRID_COLS, rows=GRID_ROWS)
    _mn_c, _mx_c, mn_r, mx_r = t.get_wafer_bounding_box()
    lines.append("  no physical_engine (analytic fallback) -> y-decentring = %d"
                 % ((t.visual_rows - 1) - (mn_r + mx_r)))
    assert (t.visual_rows - 1) - (mn_r + mx_r) == 0

    # IS a lever: an offset past the boundary-crossing threshold.
    lines.append("")
    lines.append("== attempts that DO decentre the bbox (chip_y = 16 mm) ==")
    for oy in (6.0, 6.5, 7.9, 8.0, 8.5, 12.0, 24.0):
        eng = PhysicalWaferEngine(
            wafer_diameter_mm=PHYS["phys_wafer_dia"],
            chip_size_x_mm=PHYS["phys_chip_x"], chip_size_y_mm=PHYS["phys_chip_y"],
            edge_exclusion_mm=PHYS["phys_edge_margin"], offset_x_mm=0.0, offset_y_mm=oy)
        t = WaferMapCoordinateTransformer(cols=GRID_COLS, rows=GRID_ROWS, physical_engine=eng)
        _mn_c, _mx_c, mn_r, mx_r = t.get_wafer_bounding_box()
        lines.append("  offset_y=%5.2f mm -> y-decentring = %d"
                     % (oy, (t.visual_rows - 1) - (mn_r + mx_r)))

    with capsys.disabled():
        print("\n".join(lines))

    assert delta_y != 0, "fixture is vertically centred - the harness would be vacuous"
    assert delta_x != 0, "fixture is horizontally centred"


# --- (b) per-pair deltas ------------------------------------------------------

def _pair_table(path_name):
    """Group the 16 tuples by linear part and measure the delta inside each group."""
    build = PATHS[path_name]
    maps = {t: _mapping(build, *t) for t in TUPLES}
    groups = {}
    for t in TUPLES:
        groups.setdefault(_linear_key(maps[t]), []).append(t)
    rows = []
    for key, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        assert len(members) == 2, "expected exactly 2 tuples per linear class, got %r" % (members,)
        a, b = members
        d = _constant_delta(maps[a], maps[b])
        assert d is not None, "delta between %r and %r is not a constant translation" % (a, b)
        rows.append((key, a, b, d))
    return rows, maps


@pytest.mark.parametrize("path_name", ["raw", "prod"])
def test_all_eight_pairs_delta(path_name, capsys):
    rows, _maps = _pair_table(path_name)
    assert len(rows) == 8, "expected 8 linear classes, got %d" % len(rows)

    out = ["", "== path %s: the 8 aliased pairs and their exact deltas ==" % path_name,
           "%-26s %-26s %-22s %s" % ("tuple A", "tuple B", "linear part", "delta (B - A)")]
    for key, a, b, d in rows:
        out.append("%-26s %-26s %-22s %s"
                   % ("rot%d/%s/inv=%s" % (a[0], a[1], a[2]),
                      "rot%d/%s/inv=%s" % (b[0], b[1], b[2]),
                      "x<-%s y<-%s" % (key[0], key[1]), d))
    nonzero = [r for r in rows if r[3] != (0, 0)]
    out.append("pairs with a NONZERO delta: %d of 8" % len(nonzero))
    with capsys.disabled():
        print("\n".join(out))


# --- (c) reconciling by shifting start ---------------------------------------

def _start_jacobian(build, t):
    """How the composed physical output moves when start_x / start_y move by +1."""
    base = _mapping(build, *t)
    sx = _mapping(build, *t, start_x=START_X + 1, start_y=START_Y)
    sy = _mapping(build, *t, start_x=START_X, start_y=START_Y + 1)
    j_sx = (sx[0][0] - base[0][0], sx[0][1] - base[0][1])
    j_sy = (sy[0][0] - base[0][0], sy[0][1] - base[0][1])
    for u, v in ((sx, j_sx), (sy, j_sy)):
        for p, q in zip(base, u):
            assert (q[0] - p[0], q[1] - p[1]) == v, "start shift is not a pure translation"
    return j_sx, j_sy


@pytest.mark.parametrize("path_name", ["raw", "prod"])
def test_start_shift_reconciles_every_pair(path_name, capsys):
    """A pair with delta d becomes IDENTICAL after shifting one member's start.

    The sign convention is measured, not assumed. `MAP_ALIGNMENT_SPEC.md` section 2
    writes `phys(start=(sx,sy)) == phys(start=(0,0)) + (-sx,-sy)`; this test
    records the actual Jacobian per tuple, which is NOT that constant for every
    tuple - it flips with the mirror parity of the tuple.
    """
    build = PATHS[path_name]
    rows, maps = _pair_table(path_name)
    out = ["", "== path %s: start Jacobian and the reconciling shift ==" % path_name,
           "%-26s %-16s %-16s" % ("tuple", "d(phys)/d(start_x)", "d(phys)/d(start_y)")]
    for t in TUPLES:
        j_sx, j_sy = _start_jacobian(build, t)
        out.append("%-26s %-16s %-16s"
                   % ("rot%d/%s/inv=%s" % (t[0], t[1], t[2]), j_sx, j_sy))

    out.append("")
    out.append("%-26s %-14s %-22s %s" % ("tuple B", "delta (B-A)", "start shift applied to B",
                                         "identical to A after shift?"))
    reconciled = 0
    for _key, a, b, d in rows:
        j_sx, j_sy = _start_jacobian(build, b)
        # j_sx is (+/-1, 0) or (0, +/-1); same for j_sy. Solve j_sx*u + j_sy*v == -d.
        u = v = 0
        for axis in (0, 1):
            if j_sx[axis]:
                u = -d[axis] // j_sx[axis]
            if j_sy[axis]:
                v = -d[axis] // j_sy[axis]
        shifted = _mapping(build, *b, start_x=START_X + u, start_y=START_Y + v)
        same = shifted == maps[a]
        reconciled += bool(same)
        out.append("%-26s %-14s %-22s %s"
                   % ("rot%d/%s/inv=%s" % (b[0], b[1], b[2]), d,
                      "(start_x%+d, start_y%+d)" % (u, v), same))
        assert same, "pair %r/%r did not reconcile with shift (%d,%d)" % (a, b, u, v)
    out.append("reconciled %d of %d pairs" % (reconciled, len(rows)))
    with capsys.disabled():
        print("\n".join(out))


# --- T2: the collapse count, exact vs modulo translation ---------------------

@pytest.mark.parametrize("path_name", ["raw", "prod"])
def test_collapse_count_exact_vs_modulo_translation(path_name, capsys):
    build = PATHS[path_name]
    maps = {t: _mapping(build, *t) for t in TUPLES}
    exact = len({m for m in maps.values()})
    modulo = len({_linear_key(m) for m in maps.values()})

    # The `cell_to_physical` stage alone never reads invert_y, so it can only
    # ever produce 8 - measuring it says nothing about grid_y_invert.
    stage_only = set()
    for rot, side, invert in TUPLES:
        tf = build(rot, side, invert)
        stage_only.add(tuple(tf.cell_to_physical(c, r)
                             for c in range(GRID_COLS) for r in range(GRID_ROWS)))

    with capsys.disabled():
        print("\n== path %s: distinct mappings over 16 tuples ==" % path_name)
        print("  (i)   EXACT composed visual->physical : %d" % exact)
        print("  (ii)  modulo arbitrary translation    : %d" % modulo)
        print("  (iii) cell_to_physical stage only     : %d" % len(stage_only))

    assert modulo == 8, "the linear part must always collapse to 8 (D4)"
    assert len(stage_only) == 8, "cell_to_physical ignores invert_y, so it must give 8"


# --- (d) mutation: prove the harness can go red ------------------------------

def test_mutation_bbox_mirror_makes_harness_red(monkeypatch, capsys):
    """Inject the exact bug `map_overlay.py:492` warns about and prove RED.

    The invert branch is specified as `max_r - r` (bounding-box relative). The
    easy wrong spelling is `(visual_rows - 1) - r` (full-grid relative). On a
    decentred fixture the two differ, so a harness that measures anything must
    notice. If this test's inner assertions had passed, the harness above would
    be vacuous.
    """
    orig_c2v = WaferMapCoordinateTransformer.cell_to_visual
    orig_v2c = WaferMapCoordinateTransformer.visual_to_cell

    def bad_cell_to_visual(self, c, r):
        min_c, _max_c, min_r, _max_r = self.get_wafer_bounding_box()
        xv = c - min_c + self.start_x
        yv = (r - min_r + self.start_y) if not self.invert_y \
            else ((self.visual_rows - 1) - r + self.start_y)
        return xv, yv

    def bad_visual_to_cell(self, xv, yv):
        min_c, _max_c, min_r, _max_r = self.get_wafer_bounding_box()
        c = xv - self.start_x + min_c
        r = (yv - self.start_y + min_r) if not self.invert_y \
            else ((self.visual_rows - 1) - (yv - self.start_y))
        return c, r

    baseline_prod, _ = _pair_table("prod")
    baseline_raw, _ = _pair_table("raw")

    monkeypatch.setattr(WaferMapCoordinateTransformer, "cell_to_visual", bad_cell_to_visual)
    monkeypatch.setattr(WaferMapCoordinateTransformer, "visual_to_cell", bad_visual_to_cell)
    _clear_caches()

    mutated_prod, _ = _pair_table("prod")
    mutated_raw, _ = _pair_table("raw")

    changed_prod = [(a, b, d0, d1) for (_k, a, b, d0), (_k2, _a2, _b2, d1)
                    in zip(baseline_prod, mutated_prod) if d0 != d1]
    changed_raw = [(a, b, d0, d1) for (_k, a, b, d0), (_k2, _a2, _b2, d1)
                   in zip(baseline_raw, mutated_raw) if d0 != d1]

    with capsys.disabled():
        print("\n== mutation: invert branch mirrors about the FULL GRID, not the bbox ==")
        print("  prod path: %d of 8 pair deltas changed" % len(changed_prod))
        for a, b, d0, d1 in changed_prod:
            print("    rot%d/%s/inv=%s vs rot%d/%s/inv=%s : %s -> %s"
                  % (a[0], a[1], a[2], b[0], b[1], b[2], d0, d1))
        print("  raw path : %d of 8 pair deltas changed" % len(changed_raw))
        for a, b, d0, d1 in changed_raw:
            print("    rot%d/%s/inv=%s vs rot%d/%s/inv=%s : %s -> %s"
                  % (a[0], a[1], a[2], b[0], b[1], b[2], d0, d1))

    monkeypatch.undo()
    _clear_caches()
    # Confirm the mutation was not silently repaired by a later code path:
    restored, _ = _pair_table("prod")
    assert restored == baseline_prod
    assert WaferMapCoordinateTransformer.cell_to_visual is orig_c2v
    assert WaferMapCoordinateTransformer.visual_to_cell is orig_v2c

    assert changed_prod or changed_raw, (
        "MUTATION SURVIVED: the harness cannot see a bbox-vs-full-grid mirror error, "
        "so its green result proves nothing")


def test_mutation_frame_pitch_swap_makes_harness_red(monkeypatch, capsys):
    """Remove the 90/270 pitch swap + offset sign flip from `_frame_phys_params`.

    This is the correction that only the production path applies. If the harness
    is measuring the production path at all, dropping it must move something.
    """
    orig = map_overlay._frame_phys_params

    def naive(meta):
        return map_overlay._phys_signature(meta)

    baseline, _ = _pair_table("prod")
    monkeypatch.setattr(map_overlay, "_frame_phys_params", naive)
    _clear_caches()
    mutated, _ = _pair_table("prod")

    changed = [(a, b, d0, d1) for (_k, a, b, d0), (_k2, _a2, _b2, d1)
               in zip(baseline, mutated) if d0 != d1]

    with capsys.disabled():
        print("\n== mutation: _frame_phys_params returns the declared phys verbatim ==")
        print("  prod path: %d of 8 pair deltas changed" % len(changed))
        for a, b, d0, d1 in changed:
            print("    rot%d/%s/inv=%s vs rot%d/%s/inv=%s : %s -> %s"
                  % (a[0], a[1], a[2], b[0], b[1], b[2], d0, d1))

    monkeypatch.undo()
    _clear_caches()
    restored, _ = _pair_table("prod")
    assert restored == baseline
    assert map_overlay._frame_phys_params is orig

    assert changed, ("MUTATION SURVIVED: the production path measurement is not "
                     "sensitive to `_frame_phys_params` at all")
