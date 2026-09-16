# -*- coding: utf-8 -*-
"""Run the suite as if the `virtual_join` package were DELETED, and count (S-283, 판정 458).

    conda run -n assy_manager python server/scripts/measure_without_virtual_join.py
    conda run -n assy_manager python server/scripts/measure_without_virtual_join.py -k join

Every extra argument is handed to pytest unchanged. With no file arguments it measures the
files that name the package, which is the population step 4 is about.

🔴 WHY A META_PATH FINDER AND NOT A HOLLOW MODULE. The first version of this instrument
replaced `virtual_join.config` with a module whose `__getattr__` raised, and that measured
the WRONG PROPERTY: a file doing `from virtual_join import executor` never goes through the
parent's `__getattr__` at all, because the import machinery sets the submodule as an
attribute. So it reported tests as surviving that a real deletion would kill, and the count
it produced was an upper bound wearing a value's clothes (판정 458 ㉠). A finder that refuses
the package AND every submodule is what 「deleted」 actually means.

⚠️ WHAT THIS STILL CANNOT TELL YOU. A test that dies here dies for one of two reasons - it
exercises the engine, or it merely imports the module - and the counts do not separate them.
Read a red here as 「this file must be touched by step 4」, never as 「this file must be
deleted」; the difference between repointing an import and retiring a gate is a judgement,
not a number.

🔴 AND IT IS AN INSTRUMENT, SO IT OWNS NOTHING. It installs the finder, runs pytest, and
prints. If it ever starts deciding anything, it has become the thing it measures.
"""
import os
import sys

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

#: The package this instrument pretends is gone, and the prefix that catches its submodules.
GONE = "virtual_join"


class _Deleted(object):
    """A `sys.meta_path` finder that refuses one package and everything under it.

    Returning None from `find_module`/`find_spec` means 「I do not handle this」 and the next
    finder gets a turn, so refusing has to be an explicit raise rather than a silent None.
    """

    def find_spec(self, fullname, path=None, target=None):
        if fullname == GONE or fullname.startswith(GONE + "."):
            raise ImportError(
                "%s: removed by %s (판정 458). This is the instrument, not a real failure."
                % (fullname, os.path.basename(__file__)))
        return None

    # Python 2-era hook some tools still consult; harmless and keeps the refusal total.
    def find_module(self, fullname, path=None):
        self.find_spec(fullname, path)
        return None


def _erase():
    for name in [n for n in sys.modules
                 if n == GONE or n.startswith(GONE + ".")]:
        del sys.modules[name]
    sys.meta_path.insert(0, _Deleted())


class _Plugin(object):
    def pytest_configure(self, config):
        _erase()


def _default_population():
    """The files that NAME the package - step 4's population, listed by git, not by hand."""
    import subprocess

    out = subprocess.check_output(
        ["git", "grep", "-ln", GONE, "--", "tests"], cwd=SERVER_DIR)
    return [line for line in out.decode("utf-8", "replace").split() if line]


def main(argv):
    import pytest

    args = list(argv)
    if not any(not a.startswith("-") for a in args):
        args = _default_population() + args
    print("[measure] running %d path(s) with `%s` unimportable"
          % (len([a for a in args if not a.startswith("-")]), GONE))
    code = pytest.main(["-q", "-p", "no:cacheprovider",
                        "--continue-on-collection-errors"] + args,
                       plugins=[_Plugin()])
    print("[measure] pytest exit=%s. A red here means 「step 4 must touch this file」, "
          "not 「delete it」." % code)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
