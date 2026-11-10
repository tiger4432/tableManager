# -*- coding: utf-8 -*-
"""Owner 11-10 «release 폴더에 받은 번들 넣어주면 알아서 반영하게 해줘 · 버전들 찾아서» (lead ㄱ+ㄷ): bundles put in
<install>/release/ are applied in the order their commits need, by the launcher when it starts and by
apply_release.bat - one function, the same answer from both. Real git repositories and real incremental bundles
(head ref «release»), built here."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from runtime import release_apply  # noqa: E402


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def made(tmp_path):
    """A source repository with four releases c1..c4, bundles b2..b4 (each c(n-1)..cn), and an install at c1."""
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-q")
    git(src, "config", "user.email", "t@t")
    git(src, "config", "user.name", "t")
    commits = []
    for n in range(1, 5):
        (src / "app.py").write_text("VERSION = %d\n" % n)
        git(src, "add", "app.py")
        git(src, "commit", "-q", "-m", "c%d" % n)
        commits.append(git(src, "rev-parse", "HEAD"))
    bundles = {}
    for n in range(2, 5):
        git(src, "branch", "-f", "release", commits[n - 1])
        path = tmp_path / ("b%d.bundle" % n)
        git(src, "bundle", "create", str(path), "release", "^" + commits[n - 2])
        bundles[n] = path.read_bytes()

    def install(at=1, name="install"):
        """A copy that holds only what the releases up to c<at> brought - cloned from a bundle of c<at>."""
        root = tmp_path / name
        git(src, "branch", "-f", "upto", commits[at - 1])
        whole = tmp_path / (name + ".full")
        git(src, "bundle", "create", str(whole), "upto")
        git(tmp_path, "clone", "-q", "-b", "upto", str(whole), name)
        assert subprocess.run(["git", "cat-file", "-e", commits[-1]], cwd=root).returncode != 0, "no later commit"
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        return root

    def drop(root, files):
        folder = root / "release"
        folder.mkdir(exist_ok=True)
        for name, n in files.items():
            (folder / name).write_bytes(bundles[n] if isinstance(n, int) else n)

    return {"commits": commits, "install": install, "drop": drop, "bundles": bundles}


def head(root):
    return git(root, "rev-parse", "HEAD")


def left(root):
    folder = root / "release"
    return sorted(n for n in os.listdir(folder) if (folder / n).is_file()) if folder.is_dir() else None


def applied(root):
    folder = root / "release" / "applied"
    return sorted(os.listdir(folder)) if folder.is_dir() else []


def bat(root):
    said = []
    code = release_apply.main(str(root), said.append)
    return code, said


def launcher(root, monkeypatch):
    """The launcher's entry with the run-again replaced: (its return, the lines, the command it ran again)."""
    ran = []

    class Child:
        def __init__(self, cmd, env):
            ran.append((cmd, env.get(release_apply.AGAIN)))

        def wait(self):
            return 7
    monkeypatch.setattr(release_apply, "_launch", Child)
    monkeypatch.delenv(release_apply.AGAIN, raising=False)
    said = []
    got = release_apply.start(str(root), ["run_decoupled_app.py", "--server-only"], said.append)
    return got, said, ran


# Every case, both entries: (files dropped, the install's commit) -> (HEAD after, files left, files applied, exit)
CASES = {
    "in order": ({"b2.bundle": 2, "b3.bundle": 3, "b4.bundle": 4}, 1, 4, [], ["b2.bundle", "b3.bundle", "b4.bundle"], 0),
    "names shuffled": ({"z.bundle": 2, "a.bundle": 4, "m.bundle": 3}, 1, 4, [], ["a.bundle", "m.bundle", "z.bundle"], 0),
    "already applied": ({"b2.bundle": 2, "b3.bundle": 3, "b4.bundle": 4}, 3, 4, [],
                        ["b2.bundle", "b3.bundle", "b4.bundle"], 0),
    "middle missing": ({"b2.bundle": 2, "b4.bundle": 4}, 1, 2, ["b4.bundle"], ["b2.bundle"], 1),
    "broken": ({"b2.bundle": 2, "bad.bundle": b"not a bundle\n", "cut.bundle": "cut"}, 1, 2,
               ["bad.bundle", "cut.bundle"], ["b2.bundle"], 1),
    "empty folder": ({}, 1, 1, [], [], 0),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_each_case_gives_the_same_answer_from_both_entries(made, monkeypatch, case):
    files, at, want_head, want_left, want_applied, want_code = CASES[case]
    answers = []
    for entry in ("bat", "launcher"):
        root = made["install"](at, name="%s-%s" % (case.replace(" ", "-"), entry))
        whole = made["bundles"][3]                     # its header kept, its pack garbage
        files_here = {n: (whole[: whole.index(b"\n\n") + 2] + b"PACK" + bytes(40) if v == "cut" else v)
                      for n, v in files.items()}
        made["drop"](root, files_here)
        if entry == "bat":
            code, said = bat(root)
        else:
            got, said, ran = launcher(root, monkeypatch)
            moved = want_head != at
            assert (got, ran) == ((7, [([sys.executable, "run_decoupled_app.py", "--server-only"], "1")]) if moved
                                  else (None, [])), "HEAD moved: the launcher runs again from the new code"
            code = 1 if left(root) else 0
        answers.append((head(root), left(root), applied(root), code,
                        [line for line in said if "restart the launcher" not in line and "starting again" not in line]))
        assert head(root) == made["commits"][want_head - 1], (entry, said)
        assert left(root) == want_left and applied(root) == want_applied and code == want_code, (entry, said)
    assert answers[0][1:] == answers[1][1:], "both entries: the same files, the same lines"


def test_each_applied_bundle_says_its_file_and_the_commit_before_and_after(made):
    root = made["install"](1)
    made["drop"](root, {"z.bundle": 2, "a.bundle": 4, "m.bundle": 3})
    _, said = bat(root)
    c = [sha[:9] for sha in made["commits"]]
    assert said == ["[Release] z.bundle: %s -> %s (back: git reset --hard %s)" % (c[0], c[1], c[0]),
                    "[Release] m.bundle: %s -> %s (back: git reset --hard %s)" % (c[1], c[2], c[1]),
                    "[Release] a.bundle: %s -> %s (back: git reset --hard %s)" % (c[2], c[3], c[2]),
                    "[Release] restart the launcher to run %s" % c[3]]


def test_a_bundle_already_in_is_said_and_put_away_without_a_merge(made):
    root = made["install"](3)
    made["drop"](root, {"b2.bundle": 2, "b3.bundle": 3})
    code, said = bat(root)
    c = [sha[:9] for sha in made["commits"]]
    assert said == ["[Release] b2.bundle: already in (%s)" % c[1], "[Release] b3.bundle: already in (%s)" % c[2]]
    assert (code, applied(root), git(root, "reflog", "-1", "--format=%gs").startswith("clone")) == (
        0, ["b2.bundle", "b3.bundle"], True), "no merge ran"


def test_a_bundle_git_cannot_read_is_said_and_left_and_the_rest_goes_on(made):
    root = made["install"](1)
    whole = made["bundles"][3]
    made["drop"](root, {"b2.bundle": 2, "bad.bundle": b"not a bundle\n",
                        "cut.bundle": whole[: whole.index(b"\n\n") + 2] + b"PACK" + bytes(40)})
    code, said = bat(root)
    assert said[0].startswith("[Release] b2.bundle: ")
    assert said[1] == ("[Release] bad.bundle left in the release folder: git cannot read it (not a git bundle) - get "
                       "the file again")
    assert said[2].startswith("[Release] cut.bundle left in the release folder: git cannot read it (") and said[
        2].endswith(") - get the file again")
    assert (code, left(root), head(root)) == (1, ["bad.bundle", "cut.bundle"], made["commits"][1])


def test_a_copy_with_its_own_commit_is_not_moved_and_says_where_it_stays(made):
    root = made["install"](1)
    (root / "local.txt").write_text("x")
    git(root, "add", "local.txt")
    git(root, "commit", "-q", "-m", "made here")
    here = head(root)
    made["drop"](root, {"b2.bundle": 2, "b3.bundle": 3})
    code, said = bat(root)
    assert (code, head(root), left(root)) == (1, here, ["b2.bundle", "b3.bundle"])
    assert said[0].startswith("[Release] b2.bundle not applied: ") and said[0].endswith(
        " - this copy stays at %s; send this line to the lead" % here[:9])


def test_untracked_files_never_hold_a_release_but_one_in_the_releases_way_stops_it(made):
    """Lead 11-10: «손댄 파일» is a changed TRACKED file only - an operator's config or a .bat beside the launcher is
    untracked and the release goes on; an untracked file at a path the release brings stops it, said, nothing moved."""
    root = made["install"](1, name="untracked")
    (root / "ops_config.json").write_text("{}")
    (root / "my_start.bat").write_text("@echo off\n")
    made["drop"](root, {"b2.bundle": 2})
    code, said = bat(root)
    assert (code, head(root), (root / "ops_config.json").read_text()) == (0, made["commits"][1], "{}")
    assert said[0].startswith("[Release] b2.bundle: ")

    src = made["install"](1, name="untracked-src")       # a release that brings a new file, new.txt
    (src / "new.txt").write_text("from the release")
    git(src, "add", "new.txt")
    git(src, "commit", "-q", "-m", "c2b")
    git(src, "branch", "-f", "release", "HEAD")
    bundle = src / "new.bundle"
    git(src, "bundle", "create", str(bundle), "release", "^" + made["commits"][0])
    root = made["install"](1, name="untracked-way")
    (root / "new.txt").write_text("the operator's own")
    made["drop"](root, {"new.bundle": bundle.read_bytes()})
    code, said = bat(root)
    assert (code, head(root), (root / "new.txt").read_text(), left(root)) == (
        1, made["commits"][0], "the operator's own", ["new.bundle"])
    # the operator reads this line only (lead 11-10): which file, what to do
    assert said == ["[Release] new.bundle not applied: 1 file(s) here outside git are files it brings (new.txt) - "
                    "move or delete them and start again; this copy stays at %s" % made["commits"][0][:9]]
    os.rename(root / "new.txt", root / "new.txt.mine")              # what the line says to do, then again
    code, said = bat(root)
    assert (code, (root / "new.txt").read_text(), applied(root)) == (0, "from the release", ["new.bundle"])


@pytest.mark.skipif(os.name != "nt", reason="the job is Windows'")
def test_the_launcher_run_again_goes_down_with_the_first_process_and_takes_its_children(tmp_path):
    """Lead 11-10 «처음 프로세스를 닫으면 두 번째와 그 자식들이 같이 내려가는가 — 남으면 8000 이 두 벌»: a first
    process starts the run again through `_launch`; the run again starts a child the way the supervisor does (its own
    console); the first process is killed alone - both go down."""
    import psutil
    pids = tmp_path / "pids.txt"
    again = tmp_path / "again.py"
    again.write_text(
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],\n"
        "                         creationflags=subprocess.CREATE_NEW_CONSOLE | 0x08000000)\n"
        "open(sys.argv[1], 'w').write('%d %d' % (__import__('os').getpid(), child.pid))\n"
        "time.sleep(120)\n")
    first = tmp_path / "first.py"
    first.write_text(
        "import os, sys, time\n"
        "sys.path.insert(0, %r)\n"
        "from runtime import release_apply\n"
        "release_apply._launch([sys.executable, %r, %r], dict(os.environ))\n"
        "time.sleep(120)\n" % (os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), str(again), str(pids)))
    parent = subprocess.Popen([sys.executable, str(first)])
    try:
        for _ in range(200):
            if pids.exists() and pids.read_text().count(" ") == 1:
                break
            __import__("time").sleep(0.1)
        run_again, its_child = (int(v) for v in pids.read_text().split())
        both = [psutil.Process(run_again), psutil.Process(its_child)]
        subprocess.run(["taskkill", "/PID", str(parent.pid), "/F"], capture_output=True)
        gone, alive = psutil.wait_procs(both, timeout=10)
        assert alive == [], "the run again or its child outlived the first process"
    finally:
        for pid in (parent.pid,):
            if psutil.pid_exists(pid):
                psutil.Process(pid).kill()


def test_a_missing_release_in_the_middle_says_what_it_waits_for(made):
    root = made["install"](1)
    made["drop"](root, {"b2.bundle": 2, "b4.bundle": 4})
    _, said = bat(root)
    assert "[Release] b4.bundle waits for %s, which no bundle here brings" % made["commits"][2][:9] in said[1]


def test_a_changed_tracked_file_changes_nothing_and_says_what_to_do(made, monkeypatch):
    for entry in ("bat", "launcher"):
        root = made["install"](1, name="dirty-" + entry)
        made["drop"](root, {"b2.bundle": 2})
        (root / "app.py").write_text("VERSION = 99\n")
        if entry == "bat":
            code, said = bat(root)
        else:
            got, said, ran = launcher(root, monkeypatch)
            assert (got, ran) == (None, [])
            code = 1
        assert head(root) == made["commits"][0] and left(root) == ["b2.bundle"] and code == 1
        assert said == ["[Release] not applied: 1 tracked file(s) changed in this copy (app.py) - nothing was "
                        "changed; put them back with «git checkout -- <file>» or send the list to the lead, then "
                        "start again"]
        assert (root / "app.py").read_text() == "VERSION = 99\n"


def test_no_release_folder_says_so_and_changes_nothing(made, monkeypatch):
    for entry in ("bat", "launcher"):
        root = made["install"](1, name="none-" + entry)
        if entry == "bat":
            code, said = bat(root)
        else:
            got, said, ran = launcher(root, monkeypatch)
            assert (got, ran) == (None, [])
            code = 0
        assert (head(root), left(root), code) == (made["commits"][0], None, 0)
        assert said == ["[Release] nothing to apply - no release folder"]


def test_the_launcher_run_again_does_not_look_again(made, monkeypatch):
    root = made["install"](1)
    made["drop"](root, {"b2.bundle": 2})
    monkeypatch.setenv(release_apply.AGAIN, "1")
    said = []
    assert release_apply.start(str(root), ["x"], said.append) is None and said == []
    assert head(root) == made["commits"][0]


def test_a_failing_release_step_never_keeps_the_launcher_from_starting(made, monkeypatch):
    def fails(root, say):
        raise RuntimeError("disk gone")
    monkeypatch.setattr(release_apply, "apply_releases", fails)
    monkeypatch.delenv(release_apply.AGAIN, raising=False)
    said = []
    assert release_apply.start("x", ["x"], said.append) is None
    assert said[0].startswith("[Release] the release step failed: disk gone") and said[0].endswith(
        "- starting on the code as it is")
