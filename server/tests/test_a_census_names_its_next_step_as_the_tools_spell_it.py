# -*- coding: utf-8 -*-
"""총괄 e1648e884: a census record names its next step - the redo of the rows edited behind the
chain while there are some, a person's census while the drift was never counted, nothing once it
is 0 or the source is refused. The command is spelled where the tools take it: the program name
and every flag are what that tool's own parser prints. It names the world it was measured in,
always (총괄 6c266e56b ⑤)."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill, census_cli                                 # noqa: E402

SOURCE = "some_source"
WORLD = "w1"


def test_each_state_names_its_own_step():
    redo = backfill.next_step(SOURCE, {"rows_drifted": {"estimate": 3}}, WORLD)
    count = backfill.next_step(SOURCE, {"relation_rows": {"estimate": 10}}, "default")
    assert redo == "python -m ledger.backfill --source %s --world %s --drifted" % (SOURCE, WORLD)
    assert count == "python -m ledger census --source %s --world default" % SOURCE
    assert backfill.next_step(SOURCE, {"rows_drifted": {"estimate": 0}}, WORLD) is None
    assert backfill.next_step(SOURCE, {"refused": "source_refused"}, WORLD) is None


@pytest.mark.parametrize(("tool", "census"), [
    (backfill.main, {"rows_drifted": {"estimate": 1}}),
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
