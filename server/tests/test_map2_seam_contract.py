"""MAP2 SEAM contract - the shim that puts it in the DEFAULT SUITE.

Twin of `test_map_seam_contract.py`, pointed at `contracts/map2_seam/`, which scores the
seams of Map Editor 2: the declaration vocabulary on both sides, the frame basis, scoring,
the Excel form, and `align_applied.origin`.

Read `test_map_seam_contract.py` first - every design note there applies here unchanged
(why a shim and not `testpaths`, why the contract does not move into `server/tests/`, and
why this file must never grow assertions of its own).

WHY THIS FILE EXISTS AT ALL, WRITTEN THE HOUR THE CONTRACT LANDED
    The contract lane authored `contracts/map2_seam/` and reported, in its own words, that
    without this shim `pytest server/tests/` stays green while the contract goes unrun - and
    that by its own rule the contract then dies within a week. It could not write the shim
    because the shim lives outside `contracts/`, which is the one directory that lane owns.
    So the lead PM wrote it in the same round rather than boarding it. A contract nobody
    runs is worse than no contract: it reads like coverage.

    The precedent is concrete and in this repo. `client2/tests/split_registry_harness.mjs`
    sat dead from U6 because it failed in a way nobody was looking at.

RUN IT WITH `-rs`, AND THAT IS PART OF THE COMMAND
    conda run -n assy_manager python -m pytest server/tests/ -q -rs

    This contract carries `pending` axes on purpose - vectors authored before the
    implementations they score, and at the time of writing there are several: the Excel round
    trip has no real operator artefact to score against (`ingestion_workspace/bonding_map/
    archives/` is empty on this box), and the `align_applied.origin` client consumers cannot
    be reached without source-text assertion, which is the technique that killed three
    harnesses. Pending does not block the suite; it blocks round completion. That rule only
    works while pending is visible by name, and bare `-q` prints "N skipped".

THE CLIENT HALF IS NOT COVERED HERE AND CANNOT BE
    A green pytest run means the SERVER meets the contract. Score the other side with

        node contracts/map2_seam/client_harness.mjs [--json]

    The seam is only scored when both commands have been run. That harness carries declared
    divergences - client answers pinned beside server answers with no verdict taken - so a
    non-zero divergence count is data, not failure.
"""
import pathlib
import sys

import pytest

_CONTRACT_DIR = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "map2_seam"
_CONTRACT_FILE = _CONTRACT_DIR / "test_map2_seam_contract.py"

# Loud, not skipped - same reasoning as the map_seam shim. A shim that quietly covers
# nothing when the contract moves is strictly worse than no shim.
if not _CONTRACT_FILE.exists():
    raise RuntimeError(
        f"the map2 seam contract is not where this shim expects it: {_CONTRACT_FILE}\n"
        "It moved or was deleted. Re-point this shim (and docs/architecture/CODE_MAP.md) "
        "rather than deleting it - without it the default suite stops covering the Map "
        "Editor 2 seams and nothing says so.")

if str(_CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTRACT_DIR))

# 🔴 LOADED BY PATH UNDER A DIFFERENT NAME, AND THE FIRST RUN PROVED WHY.
#    The contract file and this shim have the SAME basename. A plain
#    `import test_map2_seam_contract` therefore resolves to whatever is already in
#    sys.modules under that name - which, during collection, is THIS FILE. The shim
#    imported itself, found zero test functions, and its own health check failed loudly
#    on the first run. That is the shim working: a silent version of this bug is a green
#    suite covering nothing, which is the exact failure this file exists to prevent.
#    (`test_map_seam_contract.py` never hit it only because its contract is named
#    `test_seam_contract.py` - luck, not design.)
_MODULE_NAME = "_map2_seam_contract_impl"

# Before the load, so the contract's asserts keep pytest's rewritten diffs. Without it the
# seam failures print as bare AssertionError and the contract's explanatory messages - the
# only diagnosis a reader gets - are lost.
pytest.register_assert_rewrite(_MODULE_NAME)

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _CONTRACT_FILE)
_contract = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _contract
_spec.loader.exec_module(_contract)

# Everything public is copied rather than a hand-picked list: a hand-picked list is what
# stops being updated.
_EXPORTED = {k: v for k, v in vars(_contract).items() if not k.startswith("__")}
globals().update(_EXPORTED)

_CONTRACT_TESTS = {k for k in vars(_contract) if k.startswith("test_")}


def test_map2_shim_reexports_every_contract_test():
    """The shim's own health check - the only assertion this file owns.

    A SET comparison, not a count: one test disappearing while another is added keeps the
    count identical and loses coverage.
    """
    assert _CONTRACT_TESTS, (
        f"{_CONTRACT_FILE} defines no test_* functions. Either the contract was gutted or "
        "this shim is loading the wrong file - both mean the default suite is not covering "
        "the Map Editor 2 seams.")
    here = {k for k, v in globals().items()
            if k.startswith("test_") and k != "test_map2_shim_reexports_every_contract_test"}
    assert here == _CONTRACT_TESTS, (
        "this shim is no longer carrying the whole contract into the default suite.\n"
        f"  dropped by the shim: {sorted(_CONTRACT_TESTS - here)}\n"
        f"  present only here  : {sorted(here - _CONTRACT_TESTS)}\n"
        "Seam assertions belong in contracts/map2_seam/, never here.")
