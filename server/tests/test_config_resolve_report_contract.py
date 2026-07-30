"""CONFIG RESOLVE REPORT contract — the shim that puts it in the DEFAULT SUITE.

The contract itself is `contracts/config_resolve_report/test_report_contract.py`, scored
against `contracts/config_resolve_report/vectors.json`. This file owns no seam assertions:
it re-exports that module's tests so they run under

    conda run -n assy_manager python -m pytest server/tests/ -q -rs

Same shape and same reasons as `test_map_seam_contract.py` - `testpaths` is ignored when
paths are given on the command line, and every documented command here passes
`server/tests/` explicitly, so a `testpaths` entry would have looked like wiring and
covered nothing.

The CLIENT half is not pytest-reachable. Run it as its own command:

    node contracts/config_resolve_report/client_harness.mjs

A green pytest run means the SERVER meets the contract. The seam is only scored when both
commands have been run.
"""
import pathlib
import sys

import pytest

_CONTRACT_DIR = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "config_resolve_report"
_CONTRACT_FILE = _CONTRACT_DIR / "test_report_contract.py"

# Loud, not skipped: a shim that quietly covers nothing when the contract moves is strictly
# worse than no shim, because the suite stays green and the coverage is gone.
if not _CONTRACT_FILE.exists():
    raise RuntimeError(
        f"the config resolve report contract is not where this shim expects it: "
        f"{_CONTRACT_FILE}\nIt moved or was deleted. Re-point this shim rather than "
        "deleting it - without it the default suite stops covering the seam and nothing "
        "says so.")

if str(_CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTRACT_DIR))

pytest.register_assert_rewrite("test_report_contract")

import test_report_contract as _contract  # noqa: E402

_EXPORTED = {k: v for k, v in vars(_contract).items() if not k.startswith("__")}
globals().update(_EXPORTED)

_CONTRACT_TESTS = {k for k in vars(_contract) if k.startswith("test_")}


def test_shim_reexports_every_contract_test():
    """The shim's own health check - the only assertion this file owns."""
    assert _CONTRACT_TESTS, (
        f"{_CONTRACT_FILE} defines no test_* functions. Either the contract was gutted or "
        "this shim is loading the wrong file.")
    here = {k for k, v in globals().items()
            if k.startswith("test_") and k != "test_shim_reexports_every_contract_test"}
    assert here == _CONTRACT_TESTS, (
        "this shim is no longer carrying the whole contract into the default suite.\n"
        f"  dropped by the shim: {sorted(_CONTRACT_TESTS - here)}\n"
        f"  present only here  : {sorted(here - _CONTRACT_TESTS)}")
