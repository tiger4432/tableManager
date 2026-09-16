# -*- coding: utf-8 -*-
"""S-283 · 판정 458 ㉠. 삭제 계기가 «정말로» 거절하는지 — 계기도 코드다.

🔴 WHY THIS FILE EXISTS AT ALL. The first version of this instrument replaced
`virtual_join.config` with a module whose `__getattr__` raised, and it was WRONG in the
quiet direction: `from virtual_join import executor` never consults the parent's
`__getattr__`, because the import machinery binds the submodule as an attribute first. So
the instrument reported tests as surviving a deletion that would have killed them, and the
number it produced went into a report as a value. Nobody could catch that, because the
instrument lived in a scratchpad where nobody could read it.

⚠️ AN INSTRUMENT THAT OVER-REPORTS SURVIVAL FAILS SILENTLY. A measurement that says 「fewer
things break than really do」 produces no red anywhere; it just makes the next decision on a
smaller number. That is the whole class 「초록 대리지표는 초록 주장이 아니다」, arriving in the
measuring tool rather than in the code being measured.
"""
import importlib
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
SCRIPTS = os.path.join(SERVER_DIR, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import measure_without_virtual_join as instrument                   # noqa: E402

#: Every spelling of 「reach that package」 this repository actually uses, taken from the
#: import census rather than imagined: plain import, submodule import, `from ... import
#: <submodule>` and `from ... import <name>`. The third is the one the first instrument
#: leaked on, so it is not a formality.
EVERY_SPELLING = (
    "import virtual_join",
    "import virtual_join.config",
    "from virtual_join import executor",
    "from virtual_join.config import INDEX_PREFIX",
    "import virtual_join.refusal",
    "from virtual_join import config as vjc",
)


@pytest.fixture(name="deleted")
def fixture_deleted():
    """The instrument's own effect, undone afterwards - it edits `sys.meta_path`."""
    saved_path = list(sys.meta_path)
    saved_modules = {k: v for k, v in sys.modules.items()
                     if k == "virtual_join" or k.startswith("virtual_join.")}
    instrument._erase()
    try:
        yield
    finally:
        sys.meta_path[:] = saved_path
        sys.modules.update(saved_modules)


@pytest.mark.parametrize("spelling", EVERY_SPELLING)
def test_every_spelling_of_reaching_the_package_is_refused(deleted, spelling):
    with pytest.raises(ImportError):
        exec(compile(spelling, "<probe>", "exec"), {})


def test_it_refuses_a_submodule_that_never_existed_too(deleted):
    """⚠️ THE REFUSAL IS BY PREFIX, NOT BY A LIST OF NAMES. A list would go stale the moment
    somebody adds a module to the package - and the instrument would then over-report
    survival again, in exactly the direction that raises no red."""
    with pytest.raises(ImportError):
        importlib.import_module("virtual_join.something_nobody_wrote_yet")


def test_the_refusal_holds_even_when_a_PARENT_IS_ALREADY_PRESENT(deleted):
    """🔴 THIS IS THE ONLY TEST HERE THAT CATCHES THE ORIGINAL BUG, AND I FOUND THAT OUT BY
    MUTATING. Narrowing the finder to `fullname == GONE` - the proxy's behaviour - left the
    rest of this file GREEN, because importing a submodule imports its PARENT first and the
    parent was refused. So the parent refusal alone covers every ordinary spelling, and the
    prefix check looked like belt-and-braces that nothing measured.

    ⚠️ IT IS NOT BELT-AND-BRACES. The proxy failed precisely because a parent WAS present
    (it registered a fake one in `sys.modules`), so the submodule import never needed the
    finder and the attribute never went through `__getattr__`. That is the state this test
    builds on purpose: parent in place, submodule still refused.
    """
    import types

    # 🔴 `__path__` POINTS AT THE REAL DIRECTORY, AND THAT IS THE WHOLE TEST. With an
    # empty one the submodule import fails because nothing can FIND it - a green for the
    # wrong reason, which is what the first version of this test did (measured: the narrowed
    # mutant still passed). Pointing it at the package means that without the prefix check
    # the submodule WOULD load, so a pass here can only come from the refusal.
    parent = types.ModuleType("virtual_join")
    parent.__path__ = [os.path.join(SERVER_DIR, "virtual_join")]
    assert os.path.isdir(parent.__path__[0]), parent.__path__
    sys.modules["virtual_join"] = parent
    # ⛔ THE SUBMODULES ARE LISTED FROM DISK, NEVER TYPED. A hand-written list is the very
    # mutation this test has to catch - a finder that refuses a fixed set instead of the
    # prefix goes stale the day somebody adds a module, and over-reports survival in the
    # direction that raises no red. Enumerating means this test cannot go stale either.
    real = sorted(f[:-3] for f in os.listdir(parent.__path__[0])
                  if f.endswith(".py") and f != "__init__.py")
    assert len(real) >= 3, real
    try:
        for name in real:
            with pytest.raises(ImportError):
                importlib.import_module("virtual_join.%s" % name)
        with pytest.raises(ImportError):
            exec(compile("from virtual_join import executor", "<probe>", "exec"), {})
    finally:
        sys.modules.pop("virtual_join", None)


def test_it_refuses_nothing_else(deleted):
    """🔴 THE OTHER HALF OF THE CELL. A finder that refused too much would turn unrelated
    failures into evidence about this package, which is the same lie pointing the other way.
    """
    import json                                                     # noqa: F401
    importlib.import_module("chain.join_key_index")
    importlib.import_module("notation_norm")


def test_the_package_is_importable_again_once_the_instrument_is_removed():
    """⚠️ THE INSTRUMENT MUST NOT LEAK INTO THE SUITE THAT RUNS IT. It edits process-global
    state, so a run that forgot to undo it would make every later file measure a deleted
    package without saying so."""
    importlib.import_module("virtual_join.config")
