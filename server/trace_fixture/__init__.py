"""Synthetic core-material trace fixture (docs/spec/TRACE_FIXTURE_SPEC.md).

The simulation environment has no real data, so this package manufactures a world
in which the ontology loop's fourth arrow -- discovery feeding back into
enrichment -- can actually be run end to end and then SCORED.

Why the logic lives here and not in `server/scripts/`: that directory is a one-way
door. Scripts bootstrap `server/`, never the reverse. The auto-update collector and
the CLI are both thin callers of this package.

Layout:
    frames.py   the 8 coordinate frames, built on the repo's own transformer
    world.py    the generator -- holds the invariants that make the fixture worth having
    emit.py     CSV output for ingestion + the five oracle files
    scoring.py  the scorer, which counts an honest "unresolved" as CORRECT
"""

from .world import GeneratorConfig, generate_batch  # noqa: F401
from .emit import emit_batch  # noqa: F401

__all__ = ["GeneratorConfig", "generate_batch", "emit_batch"]
