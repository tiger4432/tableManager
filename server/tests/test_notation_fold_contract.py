"""NOTATION FOLD contract -- the shim that puts it in the DEFAULT SUITE.

The contract itself is `contracts/notation_fold/test_notation_fold_contract.py`, scored
against `contracts/notation_fold/vectors.json`. This file owns no seam assertions: it
re-exports that module's tests so they run under

    conda run -n assy_manager python -m pytest server/tests/ -q -rs

Same shape and same reasons as `test_blank_predicate_contract.py`: `testpaths` is only
consulted when NO paths are given on the command line, and every documented command in
this repo passes `server/tests/` explicitly, so a `testpaths` entry would have looked like
wiring and covered nothing.

🔴 `-rs` IS PART OF THE COMMAND, and here it matters more than usual. The SQL half CANNOT
run on the suite dialect -- SQLite has no `regexp_replace` and no `translate` -- so on a
bare `server/tests/` run the load-bearing half of this contract is SKIPPED, and a bare
`-q` reports that as an anonymous "N skipped". To score it:

    ASSY_CONTRACT_PG_URL=postgresql://... conda run -n assy_manager python -m pytest \
        server/tests/test_notation_fold_contract.py -q -rs

It is a READ-ONLY, scalar-only run: no table is named and no row is read.
"""
import pathlib
import sys

import pytest

_CONTRACT_DIR = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "notation_fold"
_CONTRACT_FILE = _CONTRACT_DIR / "test_notation_fold_contract.py"

# Loud, not skipped: a shim that quietly covers nothing when the contract moves is strictly
# worse than no shim, because the suite stays green and the coverage is gone.
if not _CONTRACT_FILE.exists():
    raise RuntimeError(
        f"the notation fold contract is not where this shim expects it: {_CONTRACT_FILE}\n"
        "It moved or was deleted. Re-point this shim rather than deleting it -- without it "
        "the default suite stops covering the seam and nothing says so.")

if str(_CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTRACT_DIR))

# Before the import, so the contract's asserts keep pytest's rewritten diffs.
pytest.register_assert_rewrite("test_notation_fold_contract")

import importlib.util as _ilu  # noqa: E402

# Loaded by PATH, not by name: this shim and the contract share a module basename, so a
# plain `import test_notation_fold_contract` resolves to whichever `sys.path` entry wins -
# and under `pytest server/tests/` that is this file, which would silently re-export
# itself and score nothing.
_spec = _ilu.spec_from_file_location("_notation_fold_contract_impl", _CONTRACT_FILE)
_contract = _ilu.module_from_spec(_spec)
sys.modules["_notation_fold_contract_impl"] = _contract
_spec.loader.exec_module(_contract)

_EXPORTED = {k: v for k, v in vars(_contract).items() if not k.startswith("__")}
globals().update(_EXPORTED)

_CONTRACT_TESTS = {k for k in vars(_contract) if k.startswith("test_")}


def test_shim_reexports_every_contract_test():
    """The shim's own health check -- the only assertion this file owns.

    A SET comparison, not a count: `test_a` disappearing while `test_b` is added keeps the
    count identical and loses coverage.
    """
    assert _CONTRACT_TESTS, (
        f"{_CONTRACT_FILE} defines no test_* functions. Either the contract was gutted or "
        "this shim is loading the wrong file.")
    here = {k for k, v in globals().items()
            if k.startswith("test_") and k != "test_shim_reexports_every_contract_test"}
    assert here == _CONTRACT_TESTS, (
        "this shim is no longer carrying the whole contract into the default suite.\n"
        f"  dropped by the shim: {sorted(_CONTRACT_TESTS - here)}\n"
        f"  present only here  : {sorted(here - _CONTRACT_TESTS)}\n"
        "Seam assertions belong in contracts/notation_fold/, never here.")
