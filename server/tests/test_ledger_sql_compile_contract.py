"""LEDGER SQL COMPILE contract -- the shim that puts it in the PG run (`scripts/run_pg_tests.py` collects
`server/tests`). The contract is `contracts/ledger_sql_compile/test_compile_contract.py`, scored against
its `vectors.json`; this file owns no seam assertion, the same shape as `test_blank_predicate_contract.py`."""
import pathlib
import sys

import pytest

_CONTRACT_DIR = pathlib.Path(__file__).resolve().parents[2] / "contracts" / "ledger_sql_compile"
_CONTRACT_FILE = _CONTRACT_DIR / "test_compile_contract.py"
if not _CONTRACT_FILE.exists():
    raise RuntimeError(f"the ledger SQL compile contract is not where this shim expects it: {_CONTRACT_FILE}")
if str(_CONTRACT_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTRACT_DIR))
pytest.register_assert_rewrite("test_compile_contract")

import test_compile_contract as _contract  # noqa: E402

globals().update({k: v for k, v in vars(_contract).items() if not k.startswith("__")})
_CONTRACT_TESTS = {k for k in vars(_contract) if k.startswith("test_")}


def test_shim_reexports_every_contract_test():
    here = {k for k in globals() if k.startswith("test_") and k != "test_shim_reexports_every_contract_test"}
    assert _CONTRACT_TESTS and here == _CONTRACT_TESTS
