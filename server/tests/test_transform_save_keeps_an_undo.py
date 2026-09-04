# -*- coding: utf-8 -*-
"""Saving a transform must leave something to go back to.

This is the ONE place a person can write code inside the application - the part of the
strategy that works - and it overwrote with a plain `open(w)`: no copy, and a truncate
before the first byte. A mapper written through this screen has no git history, exactly
like the config files beside it, so a bad save took the previous version with it.

🔴 The undo copy has ONE maker (`ledger_admin.backup_file`), not two. The table editor
already used it; it was simply private to that writer.

🔴 The write is atomic for a MEASURED reason rather than for symmetry: this handler
publishes SYSTEM_RELOAD, a reload re-imports the mapper modules, and `open(w)` truncates
FIRST - so a write that raises leaves a syntactically broken module for the next reload to
import, and the worker caches modules for the life of the process.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_admin                                             # noqa: E402


@pytest.fixture
def a_file(tmp_path, monkeypatch):
    target = tmp_path / "mapper.py"
    target.write_text("def old(): pass\n", encoding="utf-8")
    monkeypatch.setattr(ledger_admin.config_backup, "backup_dir_for",
                        lambda p: str(tmp_path / "backup"))
    return target


def test_the_previous_version_is_kept(a_file):
    backup = ledger_admin.backup_file(str(a_file))
    assert backup and os.path.exists(backup)
    assert open(backup, encoding="utf-8").read() == "def old(): pass\n"


def test_a_file_that_does_not_exist_yet_needs_no_copy(a_file, tmp_path):
    """⚠️ An empty string is the answer, not a failure: a NEW transform has no previous
    version, and refusing here would block creating one."""
    assert ledger_admin.backup_file(str(tmp_path / "not_there.py")) == ""


def test_the_config_writer_uses_THAT_maker_and_not_its_own(a_file, monkeypatch):
    """⛔ Two makers mean two places to be wrong about where copies live and how they are
    named. Checked by BEHAVIOUR - the config writer is driven and the shared maker is
    watched - because asserting on its source text would measure letters."""
    calls = []
    real = ledger_admin.backup_file
    monkeypatch.setattr(ledger_admin, "backup_file",
                        lambda path: calls.append(path) or real(path))

    target = a_file.parent / "cfg.json"
    target.write_text('{"a": 1}', encoding="utf-8")
    backup = ledger_admin._atomic_write(str(target), {"a": 2})

    assert calls == [str(target)], "the config writer made its own copy instead"
    assert backup and os.path.exists(backup)
    assert open(backup, encoding="utf-8").read() == '{"a": 1}'
