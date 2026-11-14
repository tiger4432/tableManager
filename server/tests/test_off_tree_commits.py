"""The off-tree census (owner 11-14 «ㄱ»): a lane commit the landing tree lacks is listed; a copy the tree holds by
patch, a commit main holds, a branch that has not moved since the tree left main and a dismissed patch are not."""
import os
import subprocess
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(script_dir, "..", "scripts"))

import off_tree_commits  # noqa: E402

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t"}


def _git(repo, *args, when=None):
    env = dict(ENV, **({"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else {}))
    return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, check=True,
                          encoding="utf-8").stdout.strip()


def _commit(repo, path, text, when):
    os.makedirs(os.path.dirname(os.path.join(repo, path)), exist_ok=True)
    with open(os.path.join(repo, path), "w", encoding="utf-8") as f:
        f.write(text)
    _git(repo, "add", path)
    _git(repo, "commit", "-q", "-m", "write %s" % path, when=when)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path):
    repo = str(tmp_path / "r")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "server/base.py", "0", "2026-11-01T00:00:00")
    old = _commit(repo, "server/old.py", "old", "2026-11-02T00:00:00")          # a branch that stopped here
    _git(repo, "branch", "a-stale")
    _git(repo, "checkout", "-q", "-b", "trial")                                # the tree leaves main here
    _commit(repo, "server/t.py", "t", "2026-11-03T00:00:00")
    _git(repo, "checkout", "-q", "-b", "c-lane", "main")
    lost = _commit(repo, "client2/src/lost.js", "lost", "2026-11-04T00:00:00")  # the miss
    _git(repo, "checkout", "-q", "-b", "d-copied", "main")
    copied = _commit(repo, "server/copied.py", "copied", "2026-11-05T00:00:00")
    _git(repo, "checkout", "-q", "trial")
    _git(repo, "cherry-pick", copied, when="2026-11-06T00:00:00")         # the tree holds its patch
    _git(repo, "checkout", "-q", "main")
    on_main = _commit(repo, "server/main_only.py", "m", "2026-11-07T00:00:00")
    _git(repo, "branch", "b-on-main")                                          # main holds its commit
    _commit(repo, "server/later.py", "l", "2026-11-08T00:00:00")
    return repo, {"old": old, "lost": lost, "copied": copied, "on_main": on_main}


def test_help_on_a_cp949_console_prints_and_exits_0(tmp_path):
    done = subprocess.run([sys.executable, os.path.join(script_dir, "..", "scripts", "off_tree_commits.py"), "--help"],
                          cwd=str(tmp_path), capture_output=True, env=dict(os.environ, PYTHONIOENCODING="cp949"))
    said = (done.stdout + done.stderr).decode("cp949", "replace")
    assert done.returncode == 0 and "Traceback" not in said, said
    assert "usage:" in said and "(owner 11-14 ?ㄱ?)" in said, said   # the docstring's «ㄱ»; cp949 lacks «»


def test_only_the_lane_commit_the_tree_lacks_is_listed(tmp_path):
    repo, c = _repo(tmp_path)
    rows, read = off_tree_commits.off_tree("trial", "main", dismissed_path=str(tmp_path / "none"), cwd=repo)
    assert read >= 2, "canary: the moved branches were read"
    assert [(r["lane"], r["sha"], r["side"], r["branches"]) for r in rows] == [("c", c["lost"][:9], "client", "c-lane")]


def test_a_dismissed_patch_is_left_out_and_nothing_left_is_zero_lines(tmp_path):
    repo, c = _repo(tmp_path)
    dismissed = tmp_path / "dismissed.txt"
    dismissed.write_text("# patch-id or sha · reason · lane\n%s not needed · c\n"
                         % off_tree_commits.patch_id(c["lost"], cwd=repo), encoding="utf-8")
    rows, _read = off_tree_commits.off_tree("trial", "main", dismissed_path=str(dismissed), cwd=repo)
    assert rows == []


def test_since_overrides_where_the_tree_left_main(tmp_path):
    repo, c = _repo(tmp_path)
    assert off_tree_commits.fork_point("trial", "main", cwd=repo) == c["old"]
    rows, _read = off_tree_commits.off_tree("trial", "main", since=c["lost"], dismissed_path=str(tmp_path / "x"),
                                            cwd=repo)
    assert rows == [], "a branch whose tip is not after --since is not read"


def test_a_commit_whose_twin_main_holds_is_not_listed_when_the_tree_is_main(tmp_path):
    """Client2 11-14: with main as the tree, `tree...tip ^main` emptied the side the twin was on - 82db74e7f listed."""
    repo, c = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "e-twin", c["old"])
    twin = _commit(repo, "client2/src/twin.js", "twin", "2026-11-09T00:00:00")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "cherry-pick", twin, when="2026-11-10T00:00:00")
    rows, _read = off_tree_commits.off_tree("main", "main", since=c["old"], dismissed_path=str(tmp_path / "x"),
                                            cwd=repo)
    assert twin[:9] not in [r["sha"] for r in rows], rows
    assert c["lost"][:9] in [r["sha"] for r in rows], "canary: the real miss is still listed"
