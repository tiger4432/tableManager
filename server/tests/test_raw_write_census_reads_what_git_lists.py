"""raw_write_census is S-78's gate: it answers «0 raw write sites» only for files it read. git's listing is utf-8 - a
name git writes unescaped (core.quotepath=false) is read, not lost with the whole listing on a cp949 locale - and a
listing of nothing is refused, not counted as 0.

The first test reddens a locale read (text=True) only where the locale is cp949, as on this box and at ops; on a utf-8
locale that mutant is green and the test still holds - a green there is not a dead gate."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import raw_write_census  # noqa: E402


def test_a_korean_named_script_is_listed_with_the_rest(tmp_path, monkeypatch):
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(tmp_path)]
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(git + ["config", "core.quotepath", "false"], check=True)      # names come out as utf-8
    (tmp_path / "server" / "scripts").mkdir(parents=True)
    for name in ("변경—a.py", "b.py"):
        (tmp_path / "server" / "scripts" / name).write_text("x = 1\n", encoding="utf-8")
    subprocess.run(git + ["add", "."], check=True)
    monkeypatch.chdir(tmp_path)
    assert sorted(raw_write_census.tracked_scripts()) == ["server/scripts/b.py", "server/scripts/변경—a.py"]


def test_a_listing_of_nothing_is_refused_not_counted(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as refused:
        raw_write_census.tracked_scripts()
    assert "listed nothing" in str(refused.value) and "nothing was checked" in str(refused.value)
