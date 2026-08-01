"""The eight coordinate frames (4 rotations x 2 flips), and what they can hide.

This module deliberately contains NO coordinate arithmetic of its own. It delegates
to `utils.coordinate_transformer.WaferMapCoordinateTransformer`, the same class the
map overlay uses to project one map onto another. A second, private spelling of the
rotate/flip maths would let the fixture and the application disagree -- and then the
fixture would be testing itself instead of the system.

Verified on a 13x13 grid (2026-08-01): all 8 frames give a lossless bijective
relabelling of the 169 cells, and all 8 relabellings are distinct from one another.

[The ambiguity model]

An observer sees a set of RECORDED cells and wants to know which frame they were
recorded in. Two candidate frames are indistinguishable exactly when the composition
of one with the inverse of the other maps the true occupied set onto itself. So the
number of candidates the observer cannot separate is the size of the STABILISER of
the true set under the frame group -- which is what `invariant_frames` returns.

That is why the wafer's circular mask cannot help: a circle is invariant under all
eight frames, so it contributes nothing. Only the OCCUPIED SUBSET can break the tie,
and only when that subset is itself asymmetric. This is the formal version of the
user's observation that a partial map may genuinely not be decidable.
"""

import os
import sys

_SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER not in sys.path:  # importable from a collector script exec'd elsewhere
    sys.path.insert(0, _SERVER)

from utils.coordinate_transformer import WaferMapCoordinateTransformer  # noqa: E402

ROTATIONS = (0, 90, 180, 270)
SIDES = ("front", "back")
FRAMES = tuple("rot%d_%s" % (r, s) for r in ROTATIONS for s in SIDES)
CANONICAL = "rot0_front"


def parse_frame(name):
    """'rot90_back' -> (90, 'back'). Raises on anything not one of the eight."""
    if name not in FRAMES:
        raise ValueError("unknown frame %r (expected one of %s)" % (name, list(FRAMES)))
    rot, side = name[3:].split("_", 1)
    return int(rot), side


class FrameGrid:
    """Relabels cells of one square grid between the canonical frame and the other 7."""

    def __init__(self, cols, rows):
        if cols != rows:
            # A non-square grid is not closed under 90-degree rotation, so "the 8
            # frames" would silently become 4. Refuse rather than quietly halve the
            # candidate space the fixture exists to exercise.
            raise ValueError("frame group needs a square grid, got %dx%d" % (cols, rows))
        self.cols = cols
        self.rows = rows
        self._tf = {}
        self._canon = self._transformer(CANONICAL)

    def _transformer(self, frame):
        tf = self._tf.get(frame)
        if tf is None:
            rot, side = parse_frame(frame)
            tf = WaferMapCoordinateTransformer(
                cols=self.cols, rows=self.rows, start_x=0, start_y=0,
                rotation=rot, side=side)
            self._tf[frame] = tf
        return tf

    def record(self, frame, x, y):
        """Canonical cell -> the label an instrument using `frame` would write down."""
        return self._transformer(frame).physical_to_cell(*self._canon.cell_to_physical(x, y))

    def restore(self, frame, x, y):
        """A label written in `frame` -> the canonical cell it actually is."""
        return self._canon.physical_to_cell(*self._transformer(frame).cell_to_physical(x, y))

    def invariant_frames(self, cells):
        """Frames that map this cell set onto itself -- i.e. the candidates nobody can separate.

        Always contains CANONICAL. Length 1 means the frame is determinable from the
        occupancy alone; length > 1 means the honest answer is "unresolved", and the
        fixture records it in truth_ambiguous.csv so that answering "unresolved" scores
        as CORRECT rather than as a miss.
        """
        target = set(cells)
        out = []
        for frame in FRAMES:
            if {self.record(frame, x, y) for (x, y) in target} == target:
                out.append(frame)
        return tuple(out)

    def orbit(self, x, y):
        """Every image of one cell under the 8 frames -- the building block of a
        deliberately symmetric subset."""
        return {self.record(f, x, y) for f in FRAMES}


def circular_mask(size, radius):
    """The dies inside the wafer, as a D4-symmetric set centred on the grid.

    Symmetric ON PURPOSE: the mask must carry no frame information, so that the only
    thing able to resolve a frame is the occupied subset drawn on top of it.
    """
    c = (size - 1) / 2.0
    return {(x, y) for y in range(size) for x in range(size)
            if (x - c) ** 2 + (y - c) ** 2 <= radius ** 2}
