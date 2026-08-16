import os
import sys


SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import seed_root_lot_valid_die_refs as seed


def test_every_declared_root_has_a_non_square_grid_inside_requested_range():
    assert set(seed.DIMENSIONS_BY_ROOT) == {
        "NAB115", "NAB122", "NAB123", "NAB163", "NAB539"
    }
    for cols, rows in seed.DIMENSIONS_BY_ROOT.values():
        assert 15 <= cols <= 25
        assert 15 <= rows <= 25
        assert cols != rows


def test_circle_has_exactly_one_bottom_centre_notch_with_d_boundary():
    for cols, rows in seed.DIMENSIONS_BY_ROOT.values():
        cells, notch = seed.footprint(cols, rows)
        present = set(cells)
        x, y = notch
        assert x == cols // 2
        assert notch not in present
        assert (x, y + 1) not in present
        assert {(x - 1, y), (x + 1, y),
                (x - 1, y - 1), (x, y - 1), (x + 1, y - 1)} <= present
        assert seed.die_value((x - 1, y), present) == seed.VAL_EDGE
        assert seed.die_value((x + 1, y), present) == seed.VAL_EDGE
