"""MAP SEAM contract — the shim that puts it in the DEFAULT SUITE.

The contract itself is `contracts/map_seam/test_seam_contract.py`, scored against
`contracts/map_seam/vectors.json`. This file contains no assertions of its own about the
seam: it re-exports that module's tests so they run under

    conda run -n assy_manager python -m pytest server/tests/ -q -rs

`-rs` IS PART OF THE COMMAND, NOT AN OPTION
    Some contract axes are `pending` — vectors authored before the implementation, which are
    deliberately quiet rather than red (see `symbol_status` in vectors.json). The Lead PM's
    rule is that pending does not block the SUITE but does block ROUND COMPLETION, and that
    rule only functions while pending is visible by name and number. Bare `-q` reports
    "N skipped" — enough to know something is unscored, not enough to know what, whose, or
    what it blocks. `-rs` prints the reason lines, which carry the symbol, the owner and the
    blocked invariants.

WHY A SHIM AND NOT `testpaths`
    `testpaths` is only consulted when NO paths are given on the command line
    (`_pytest/config/__init__.py`: `if args: result = args`). Every documented command in this
    repo passes `server/tests/` explicitly, so a `testpaths` entry would have read like wiring
    and covered nothing — a green suite that still did not mean the contract passed.

WHY THE CONTRACT DOES NOT SIMPLY MOVE HERE
    Three agents hold this tree open during a round, and the contract file is the one artefact
    all three touch. Keeping it under `contracts/` — beside the vectors and the client harness,
    owned by neither side of the seam — is deliberate: a contract that costs someone a merge
    conflict to land stops getting landed. This shim buys default-suite coverage without
    moving it.

WHAT THIS FILE MUST NEVER BECOME
    A second place where seam assertions live. If the two files ever disagree, the contract is
    whatever `contracts/map_seam/` says. `test_shim_reexports_every_contract_test` below fails
    if this shim silently stops carrying part of the contract, which is the only way it can rot.

    NOTE the client half is NOT covered by pytest and cannot be — it is a node harness that
    reads client2 source text. Run it as its own one-line command:

        node contracts/map_seam/client_harness.mjs [--json]

    A green pytest run therefore means the SERVER meets the contract. The seam is only scored
    when both commands have been run.
"""
import pathlib
import sys

import pytest

_CONTRACT_DIR = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "map_seam"
_CONTRACT_FILE = _CONTRACT_DIR / "test_seam_contract.py"

# Loud, not skipped. A shim that quietly covers nothing when the contract moves is strictly
# worse than no shim: the suite stays green and the coverage is gone. `client2/tests/
# split_registry_harness.mjs` sat dead from U6 for exactly this reason — it failed in a way
# nobody was looking at.
if not _CONTRACT_FILE.exists():
    raise RuntimeError(
        f"the map seam contract is not where this shim expects it: {_CONTRACT_FILE}\n"
        "It moved or was deleted. Re-point this shim (and docs/architecture/CODE_MAP.md "
        "§6-2) rather than deleting it — without it the default suite stops covering the "
        "seam and nothing says so.")

if str(_CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTRACT_DIR))

# Before the import, so the contract's asserts keep pytest's rewritten diffs. Without this the
# seam failures would print as bare AssertionError and the contract's explanatory messages
# would be the only diagnosis left.
pytest.register_assert_rewrite("test_seam_contract")

import test_seam_contract as _contract  # noqa: E402

# Re-export tests, fixtures and their helpers. Everything public is copied rather than a
# hand-picked list: a hand-picked list is what stops being updated.
_EXPORTED = {k: v for k, v in vars(_contract).items() if not k.startswith("__")}
globals().update(_EXPORTED)

_CONTRACT_TESTS = {k for k in vars(_contract) if k.startswith("test_")}


def test_shim_reexports_every_contract_test():
    """The shim's own health check — the only assertion this file owns.

    A re-export that silently drops tests is indistinguishable from a passing suite. This is
    a SET comparison, not a count: `test_a` disappearing while `test_b` is added keeps the
    count identical and loses coverage.
    """
    assert _CONTRACT_TESTS, (
        f"{_CONTRACT_FILE} defines no test_* functions. Either the contract was gutted or "
        "this shim is loading the wrong file — both mean the default suite is not covering "
        "the map seam.")
    here = {k for k, v in globals().items()
            if k.startswith("test_") and k != "test_shim_reexports_every_contract_test"}
    assert here == _CONTRACT_TESTS, (
        "this shim is no longer carrying the whole contract into the default suite.\n"
        f"  dropped by the shim: {sorted(_CONTRACT_TESTS - here)}\n"
        f"  present only here  : {sorted(here - _CONTRACT_TESTS)}\n"
        "Seam assertions belong in contracts/map_seam/test_seam_contract.py, never here.")
