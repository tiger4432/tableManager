# -*- coding: utf-8 -*-
"""총괄 e1648e884 · 6091a7ae3 ②: a census record names its next step - the catch-up while a
person's count found rows new, edited or gone, a person's census while nobody counted them,
nothing once all three are 0 or the source is refused. The command is spelled where the tools
take it: the program name and every flag are what that tool's own parser prints. It names the
world it was measured in, always (총괄 6c266e56b ⑤)."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill, census_cli                                 # noqa: E402

SOURCE = "some_source"
WORLD = "w1"


def _counted(new=0, drifted=0, gone=0):
    return {"rows_new": {"estimate": new}, "rows_drifted": {"estimate": drifted},
            "rows_gone": {"estimate": gone}}


def test_each_state_names_its_own_step():
    catch_up = "python -m ledger.backfill --world %s --catch-up" % WORLD
    for behind in ({"new": 2}, {"drifted": 3}, {"gone": 1}):   # each of the three, alone
        assert backfill.next_step(SOURCE, _counted(**behind), WORLD) == catch_up, behind
    count = backfill.next_step(SOURCE, {"relation_rows": {"estimate": 10}}, "default")
    assert count == "python -m ledger census --source %s --world default" % SOURCE
    # a record a person counted before the three were apart: counted again
    assert backfill.next_step(SOURCE, {"rows_drifted": {"estimate": 0}}, WORLD).startswith(
        "python -m ledger census")
    assert backfill.next_step(SOURCE, _counted(), WORLD) is None
    assert backfill.next_step(SOURCE, {"refused": "source_refused"}, WORLD) is None


@pytest.mark.parametrize(("tool", "census"), [
    (backfill.main, _counted(gone=1)),
    (census_cli.main, {}),
])
def test_the_step_is_what_the_tools_parser_takes(tool, census, capsys):
    command = backfill.next_step(SOURCE, census, WORLD)
    prog = command.split(" --", 1)[0]
    flags = [word for word in command.split() if word.startswith("--")]
    assert flags, "canary: the command names flags"
    with pytest.raises(SystemExit):
        tool(["--help"])
    usage = capsys.readouterr().out
    assert usage.startswith("usage: %s " % prog), usage[:80]
    for flag in flags:                     # the whole flag - `--drift` is not `--drifted`
        assert re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(flag), usage), flag
