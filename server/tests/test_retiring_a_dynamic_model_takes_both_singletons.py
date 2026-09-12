# -*- coding: utf-8 -*-
r"""S-191. `retire_dynamic_model` — one function, and it takes BOTH process-wide singletons.

🔴 THE DEFECT IS THE HALF NOBODY SEES. Eight seats in this suite retired a dynamic table;
four of them popped `models.DYNAMIC_TABLES` and left the `Table` in `Base.metadata`. That
costs nothing in the file that does it — `init_dynamic_models` builds with
`extend_existing=True`, so the rebuilt table simply gains a SECOND `Index` of the same
name — and it is paid, much later, by the first OTHER file to call `create_all`, which dies
with 「index … already exists」. Measured this session at 1,008 errors from one such fixture.

⛔ AND THE POPULATION WAS NOT 52. That number came from `del .*DYNAMIC_TABLES\[`, a pattern
that finds "del" inside 「mo(del)」 — 48 of its 49 hits were ordinary reads. With a word
boundary the real answer is 9 files, and three of THOSE are not retirements at all but
save-and-restore pairs, which is why this module also scores who still pops for themselves.
"""
import os
import re
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from conftest import retire_dynamic_model                              # noqa: E402
from database import models                                           # noqa: E402
from database.database import Base                                    # noqa: E402

PREFIX = "s191_"
T = "s191_retire_probe"
CFG = {T: {"business_key": "k", "column_types": {"k": "string"}}}


@pytest.fixture(autouse=True)
def _leave_nothing_behind():
    """This file eats its own cooking — the thing it scores is what cleans up after it."""
    yield
    for name in [n for n in list(models.DYNAMIC_TABLES) + list(Base.metadata.tables)
                 if str(n).startswith(PREFIX)]:
        retire_dynamic_model(name)


# ---------------------------------------------------------------------------
# both halves
# ---------------------------------------------------------------------------

def test_it_takes_the_class_and_the_table():
    """🔴 THE SECOND ASSERTION IS THE WHOLE POINT. The first one passed at every seat
    already; it is the `Base.metadata` line that four of them never had."""
    models.init_dynamic_models(dict(CFG))
    assert T in models.DYNAMIC_TABLES and T in Base.metadata.tables

    retired = retire_dynamic_model(T)

    assert retired is not None, "the class comes back, so a caller can still use it"
    assert T not in models.DYNAMIC_TABLES
    assert T not in Base.metadata.tables


def test_a_name_that_was_never_registered_says_so_instead_of_raising():
    """⚠️ `None` vs the class is how a caller tells 「it was there」 from 「it never was」 —
    a teardown that runs after a failed setup must not raise on top of the real error."""
    assert retire_dynamic_model("s191_never_registered") is None


def test_the_index_stops_doubling_and_that_is_the_defect_itself():
    """🔴 THE 1,008 ERRORS, REPRODUCED IN ONE FUNCTION.

    ⚠️ AND THE NEGATIVE CONTROL IS FIRST, DELIBERATELY. Asserting only that the helper
    leaves one index would pass on a build that never doubled — so the old seat's behaviour
    is run first and the duplicate is asserted. If that arm ever stops being 2, this test is
    measuring a defect that no longer exists and must be re-read, not re-passed.
    """
    models.init_dynamic_models(dict(CFG))

    models.DYNAMIC_TABLES.pop(T, None)          # the OLD seat: the class only
    models.init_dynamic_models(dict(CFG))
    leaked = [i.name for i in Base.metadata.tables[T].indexes]
    assert leaked.count("idx_%s_updated" % T) == 2, leaked

    retire_dynamic_model(T)                      # the helper: both halves
    models.init_dynamic_models(dict(CFG))
    healed = [i.name for i in Base.metadata.tables[T].indexes]
    assert healed.count("idx_%s_updated" % T) == 1, healed


# ---------------------------------------------------------------------------
# 🔴 who still pops for themselves — and why that is allowed to be exactly three
# ---------------------------------------------------------------------------

#: ⚠️ Assembled, never written out, so this file cannot match ITSELF. A gate that walks
#: tracked files and spells its own subject becomes a third site the day it is committed.
_POP = re.compile(r"DYNAMIC_TABLES" + r"\.pop\(|(?:^|[^A-Za-z_])del +[A-Za-z_.]*"
                  + "DYNAMIC_TABLES" + r"\[")

#: The three save-and-restore pairs. There the pop is the INVERSE OF A RESTORE — the
#: `finally` puts the same class back and never the `Table` — so routing them through the
#: helper would break the pair. Named here and in the helper's docstring so the next reader
#: does not 「finish the job」.
RESTORE_PAIRS = {"test_ledger_v2_pg.py",
                 "test_map_alignment_references.py",
                 "test_map_alignment_worklist.py"}

#: ⚠️ AND THIS FILE POPS TOO, ON PURPOSE — `test_the_index_stops_doubling…` runs the OLD
#: seat as its negative control, so the defect is reproduced before it is shown healed. It
#: is listed rather than spelled around, because a gate whose exceptions are invisible is a
#: gate that stops meaning what it says.
NEGATIVE_CONTROL = os.path.basename(__file__)


def _files_that_pop():
    found = set()
    for name in sorted(os.listdir(script_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(script_dir, name), encoding="utf-8") as fh:
            if _POP.search(fh.read()):
                found.add(name)
    return found


def test_the_only_seats_left_are_the_three_restore_pairs_and_the_helper():
    found = _files_that_pop()
    assert found, "the pattern matched nothing at all — it is the instrument that broke"
    assert found == RESTORE_PAIRS | {"conftest.py", NEGATIVE_CONTROL}, sorted(found)


def test_the_helper_names_those_three_where_the_next_reader_will_look():
    """⛔ THE DOCSTRING IS LOAD-BEARING (판정 307). Without it the three read as seats
    somebody forgot, and the next sweep converts them and breaks the restore."""
    doc = retire_dynamic_model.__doc__ or ""
    for name in RESTORE_PAIRS:
        assert name in doc, name
