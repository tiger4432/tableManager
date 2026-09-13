# -*- coding: utf-8 -*-
"""S-209. The authoring directory is OUTSIDE this repo, so the names it teaches drift.

🔴 THE SEAM IS A NAME, NOT A FILE. `assyManager-authoring/` is a sibling directory with its
own git; nothing in this repo imports it and nothing in it is deployed with us. What the two
share is a short list of ENTRY-POINT NAMES - `@mapper`, `discover`, `MAPPER_REGISTRY`, and
the parser hooks on `BasePipelineParser`. A rename here is silent over there: the guide goes
on teaching a word the product no longer answers to, and an operator following it gets a
refusal with no clue which side moved.

⚠️ THE NAMES ARE RESOLVED BY IMPORT, never by reading source text. A text oracle would go
red when a file is reformatted and green when the name is only mentioned in a comment -
it measures spelling, not the thing the guide promises.

⚠️ AND THE OUTSIDE HALF SKIPS BY NAME. That directory is not everyone's checkout; a skip
that says WHICH path was missing is a measurement, while a silently-passing case is not.
"""
import importlib.util
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

REPO_DIR = os.path.dirname(SERVER_DIR)

#: 🔴 THE ONE CONSTANT. `docs/guide/AUTHORING.md` promises a SIBLING of this repo, so it is
#: derived from the repo's own location rather than typed as an absolute path - a typed one
#: would be true on exactly one box.
AUTHORING_DIR = os.path.join(os.path.dirname(REPO_DIR), "assyManager-authoring")
EXAMPLES_DIR = os.path.join(AUTHORING_DIR, "examples")

#: The five that MOVED (판정 348·349). Two copies of one file is the defect this half of
#: S-209 exists to prevent, so their repo paths have to stay empty.
MOVED = (
    "mappers/dt_standard_map_mapper.py.sample",
    "mappers/lot_slot_wafer_mapper.py.sample",
    "mappers/production_mapper.py.sample",
    "parsers/custom_parser_template.py",
    "parsers/custom_parser.py.sample",
)

#: The seven tracked samples that STAY: tests read them byte-identically against the
#: owner's live mappers, so moving them out would leave the drift gate nothing to compare.
STAYS = (
    "mappers/core_alignment_mapper.py.sample",
    "mappers/core_usage_mapper.py.sample",
    "mappers/cross_table_lookup_mapper.py.sample",
    "mappers/dt_alignment_metadata_mapper.py.sample",
    "mappers/dt_inventory_metadata_mapper.py.sample",
    "mappers/dt_job_rollup_mapper.py.sample",
    "mappers/dt_map_mapper.py.sample",
    # 🔴 AND THE TWO PARSER SHIMS (판정 349): their own headers say 「HAND-COPY THIS FILE」,
    # and `OPERATOR_RUNBOOK.md` :71 makes that copy step 4 of a procedure. Their reason to
    # exist is 「fixing a parsing defect is one `git pull`」, which a second repository would
    # make false.
    "parsers/void_obs_parser.py.sample",
    "parsers/inspection_run_parser.py.sample",
)

outside = pytest.mark.skipif(
    not os.path.isdir(EXAMPLES_DIR),
    reason="the authoring directory is not checked out here: %s" % EXAMPLES_DIR)


# ---------------------------------------------------------------------------
# 🔴 the names this repo promises - always scored, no skip
# ---------------------------------------------------------------------------

def test_the_mapper_entry_points_the_guide_teaches_resolve():
    """🔴 `MAPPING_GUIDE.md` teaches 「`@mapper(name=…)` 로 등록하면 `MAPPER_REGISTRY` 에
    이름이 선다」, and `discover` is what fills that registry in a process."""
    import mapper_sdk

    assert callable(mapper_sdk.mapper)
    assert callable(mapper_sdk.discover)
    assert isinstance(mapper_sdk.MAPPER_REGISTRY, dict)


def test_the_parser_hooks_the_guide_teaches_resolve():
    """🔴 `PARSER_GUIDE.md`'s class-based path is `match` + `process_dataframe`, with `parse`
    as the contract the base fulfils on top of them."""
    from parsers.pipeline_base import BasePipelineParser

    for hook in ("match", "process_dataframe", "parse"):
        assert callable(getattr(BasePipelineParser, hook)), hook


def test_the_registration_name_is_what_the_registry_is_keyed_by():
    """⚠️ 「THE NAME EXISTS」 IS NOT 「THE NAME IS THE KEY」. The guide's two lines are worth
    nothing if `@mapper(name=…)` registers under something else, so this drives the
    decorator rather than asserting on its signature."""
    import mapper_sdk

    before = dict(mapper_sdk.MAPPER_REGISTRY)
    try:
        @mapper_sdk.mapper(name="s209_drift_probe", target_table="t")
        def _probe(df, db):                                      # pragma: no cover - unused
            return df

        assert "s209_drift_probe" in mapper_sdk.MAPPER_REGISTRY
    finally:
        mapper_sdk.MAPPER_REGISTRY.clear()
        mapper_sdk.MAPPER_REGISTRY.update(before)


# ---------------------------------------------------------------------------
# ⚠️ one file, one home - the move, scored from this side
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relative", MOVED)
def test_a_moved_example_has_no_second_copy_here(relative):
    """⛔ A MOVE, NOT A COPY. Two homes for one example is two answers the day one is edited,
    and the outside one is the one an operator reads."""
    assert not os.path.exists(os.path.join(SERVER_DIR, relative)), (
        "%s came back - the authoring copy is the only one" % relative)


@pytest.mark.parametrize("relative", STAYS)
def test_a_sample_a_gate_reads_is_still_here(relative):
    """🔴 THE OTHER DIRECTION, AND IT IS THE ONE THAT BREAKS QUIETLY. Moving one of these out
    does not fail anything at the moment it happens - the byte-identity test simply stops
    having a file to compare, which is how a drift gate dies without a red."""
    assert os.path.exists(os.path.join(SERVER_DIR, relative)), relative


# ---------------------------------------------------------------------------
# ⚠️ the outside half - skipped BY NAME when that directory is not here
# ---------------------------------------------------------------------------

@outside
@pytest.mark.parametrize("relative", MOVED)
def test_the_moved_example_is_in_the_authoring_directory(relative):
    assert os.path.exists(os.path.join(EXAMPLES_DIR, os.path.basename(relative)))


@outside
def test_the_functional_parser_example_still_defines_the_name_the_guide_teaches():
    """🔴 `PARSER_GUIDE.md` teaches `parse_file(file_path) -> list[dict]` as the whole of the
    functional contract, and after the move this example is the only place that name is
    written down.

    ⚠️ MEASURED WHILE MOVING IT (S-209): no tracked code in this repo calls `parse_file` -
    the seat that picks up a workspace script (`parsers/directory_watcher.py` :1157) collects
    SUBCLASSES of `BasePipelineParser` only. So this case scores that the example still
    teaches what it teaches; whether the product should answer to that name at all is a
    ruling, not something a test may decide quietly.
    """
    path = os.path.join(EXAMPLES_DIR, "custom_parser_template.py")
    spec = importlib.util.spec_from_file_location("s209_authoring_example", path)
    module = importlib.util.module_from_spec(spec)
    # ⛔ NO `__pycache__` IN SOMEONE ELSE'S WORKING TREE. Executing a module writes a `.pyc`
    # beside it, and that directory is another repository - the application lane had to
    # untrack one this test produced. A compiled copy of a source file is a second copy of
    # it, which is the very defect that repo's guide warns about two sections along.
    written = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written

    assert callable(module.parse_file)
