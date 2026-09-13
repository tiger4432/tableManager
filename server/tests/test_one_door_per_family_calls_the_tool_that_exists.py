# -*- coding: utf-8 -*-
"""S-109. 운영에서는 `python -m ledger <도구>` · `python -m chain <도구>` 하나만 외웁니다.

🔴 THE DOOR MUST IMPLEMENT NOTHING. The owner asked for an entry point that does not
require knowing a script's filename - not for a new CLI. So every subcommand resolves to a
module that already exists and calls its `main(argv)` with the rest of the command line
untouched. A door that re-parsed the arguments would be a second spelling of every tool's
contract, and the day one of them grew a flag the door would silently drop it.

⚠️ WHICH IS WHY THESE CASES ASSERT DELEGATION rather than behaviour: what is at risk
here is not what the tools do - they already had tests - but whether the door still hands them
their own arguments and their own `--help`.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import importlib                                                     # noqa: E402

LEDGER = importlib.import_module("ledger.__main__")
CHAIN = importlib.import_module("chain.__main__")


@pytest.mark.parametrize("door", [LEDGER, CHAIN])
def test_every_subcommand_names_a_module_that_really_has_a_main(door):
    """🔴 THE ONE THAT CATCHES A ROTTEN DOOR. A name here that no longer resolves - or
    a module that lost its `main` - would fail at the moment an operator typed it, which is
    the worst time. `--help` alone would not catch it: the listing prints from this table."""
    for name, (module_path, blurb) in door.TOOLS.items():
        module = importlib.import_module(module_path)
        assert callable(getattr(module, "main", None)), (
            f"{name} -> {module_path} has no callable main")
        assert blurb.strip(), f"{name} has no line an operator can choose from"


@pytest.mark.parametrize("door", [LEDGER, CHAIN])
def test_the_rest_of_the_command_line_reaches_the_tool_untouched(door, monkeypatch):
    """⛔ NOT RE-PARSED, NOT REORDERED, NOT FILTERED. The tool owns its arguments."""
    name = sorted(door.TOOLS)[0]
    seen = {}

    class _Tool:
        @staticmethod
        def main(argv):
            seen["argv"] = list(argv)
            return 0

    monkeypatch.setattr(door.importlib, "import_module", lambda path: _Tool)
    assert door.main([name, "--source", "dt_job", "--apply", "--", "-x"]) == 0
    assert seen["argv"] == ["--source", "dt_job", "--apply", "--", "-x"]


@pytest.mark.parametrize("door", [LEDGER, CHAIN])
def test_help_after_a_subcommand_belongs_to_the_tool(door, monkeypatch):
    """⚠️ THE OPERATOR MANUAL IS THE TOOL. A summary written in the door would go stale
    the first time one of them changed, so `--help` is forwarded rather than answered."""
    name = sorted(door.TOOLS)[0]
    seen = {}

    class _Tool:
        @staticmethod
        def main(argv):
            seen["argv"] = list(argv)
            return 0

    monkeypatch.setattr(door.importlib, "import_module", lambda path: _Tool)
    door.main([name, "--help"])
    assert seen["argv"] == ["--help"], "the door must not answer the tool's --help itself"


@pytest.mark.parametrize("door", [LEDGER, CHAIN])
def test_a_name_that_is_not_a_tool_is_refused_rather_than_guessed(door, capsys):
    """⛔ NO CLOSEST MATCH. Two of these tools WRITE, so running a different one than the
    operator typed is not a convenience."""
    assert door.main(["nope"]) == 2
    assert "nope" in capsys.readouterr().err


@pytest.mark.parametrize("door", [LEDGER, CHAIN])
def test_no_arguments_lists_the_tools_and_succeeds(door, capsys):
    assert door.main([]) == 0
    printed = capsys.readouterr().out
    for name in door.TOOLS:
        assert name in printed


def test_the_door_does_not_move_the_tools_it_opens():
    """⛔ A DOOR, NOT A RENAME. Opening `python -m chain` moved nothing; the tools stay
    where they are and the door only points at them.

    🪦 [S-211, 판정 364] The worker's own home DID move later - `chain/ingestion_worker.py` -
    when the flat modules became packages. That is a different round doing a different
    thing, and this case still says what it said: the DOOR did not move it.
    """
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    assert os.path.exists(os.path.join(here, "chain", "ingestion_worker.py"))
    assert os.path.exists(os.path.join(here, "scripts", "chain_replay_cli.py"))
    assert os.path.exists(os.path.join(here, "scripts", "ledger_restamp_cursor.py"))
