"""Commits on lane branches that a landing tree does not hold - read-only, run before every landing (owner 11-14 «ㄱ»).

A commit is «in» the tree when the tree holds it or a commit with the same patch (`git rev-list --cherry-pick`), so a
cherry-picked copy is not reported. Read: every local and origin branch whose tip moved after `since` (default: where
the tree first left main); a commit main holds is not reported. A commit whose patch-id or SHA is in the dismissed file is left out - a lane writes «not
needed» there once, with its reason. One line per commit: lane · sha · side · branches · subject. 0 lines = nothing
off the tree; the landing step passes only then. 0 branches read is refused (exit 2): nothing was checked.

    conda run -n assy_manager python scripts/off_tree_commits.py <tree> [--main origin/main] [--since <sha>]
"""
import argparse
import os
import re
import subprocess
import sys

DISMISSED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs", "process",
                         "off_tree_dismissed.txt")


def git(*args, cwd=None, stdin=None):
    return subprocess.run(["git", *args], cwd=cwd, input=stdin, capture_output=True, check=True,
                          encoding="utf-8", errors="replace").stdout


def fork_point(tree, main, cwd=None):
    """Where `tree` first left `main`: the merge-base of its oldest first-parent commit `main` lacks."""
    own = git("rev-list", "--first-parent", tree, "^" + main, cwd=cwd).split()
    return git("merge-base", own[-1], main, cwd=cwd).strip() if own else git("rev-parse", tree, cwd=cwd).strip()


def dismissed(path):
    """{patch-id or sha} - the first word of each line; # starts a comment."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.split()[0] for line in f if line.strip() and not line.lstrip().startswith("#")}


def patch_id(sha, cwd=None):
    out = git("patch-id", "--stable", cwd=cwd, stdin=git("show", sha, cwd=cwd))
    return out.split()[0] if out else ""


def side(sha, cwd=None):
    tops = {path.split("/", 1)[0] for path in git("show", "--name-only", "--format=", sha, cwd=cwd).split()}
    return "+".join(sorted({"server" if t == "server" else "client" if t.startswith("client") else "other"
                            for t in tops})) or "none"


def lacking(ref, tip, cwd=None):
    """Commits of `tip` that `ref` holds neither as themselves nor as a patch (each side of ref...tip compared whole)."""
    return git("rev-list", "--cherry-pick", "--right-only", "--no-merges", "%s...%s" % (ref, tip), cwd=cwd).split()


def off_tree(tree, main, since=None, dismissed_path=DISMISSED, cwd=None):
    """-> ([{lane, sha, side, branches, subject}], branches read)."""
    since = since or fork_point(tree, main, cwd)
    after = int(git("log", "-1", "--format=%ct", since, cwd=cwd))
    skip = {git("rev-parse", ref, cwd=cwd).strip() for ref in (tree, main)}
    gone = dismissed(dismissed_path)
    found, read = {}, 0
    for line in git("for-each-ref", "--format=%(committerdate:unix) %(objectname) %(refname:short)",
                    "refs/heads", "refs/remotes/origin", cwd=cwd).splitlines():
        when, tip, name = line.split(" ", 2)
        if int(when) <= after or tip in skip or name.endswith("/HEAD"):
            continue
        read += 1
        in_main = set(lacking(main, tip, cwd))
        for sha in (s for s in lacking(tree, tip, cwd) if s in in_main):
            if sha not in found:
                found[sha] = {"sha": sha[:9], "branches": [], "full": sha}
            found[sha]["branches"].append(name)
    rows = []
    for sha, row in found.items():
        if sha in gone or sha[:9] in gone or patch_id(sha, cwd) in gone:
            continue
        branches = sorted(set(row["branches"]))
        rows.append({"lane": re.match(r"[a-z]*", branches[0].split("/")[-1].split("-", 1)[0]).group() or "?", "sha": row["sha"], "side": side(sha, cwd),
                     "branches": ",".join(branches),
                     "subject": git("log", "-1", "--format=%s", sha, cwd=cwd).strip()})
    return sorted(rows, key=lambda r: (r["lane"], r["branches"], r["sha"])), read


def main():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # server/, run as a file
    from utils.logger import make_stdout_safe
    make_stdout_safe()                                  # argparse's --help prints the docstring's «» before the line below
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tree", help="the landing tree, e.g. origin/ovh-trial-1111")
    parser.add_argument("--main", default="origin/main")
    parser.add_argument("--since", help="read branches whose tip moved after this commit (default: the tree's fork)")
    parser.add_argument("--dismissed", default=DISMISSED)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")             # a subject's « on a cp949 console cut the list short (D 11-14)
    rows, read = off_tree(args.tree, args.main, args.since, args.dismissed)
    if not read:                                        # right after a rebase the default window holds nothing
        print("[off-tree] read 0 branches - nothing was checked; widen with --since <an older commit>", file=sys.stderr)
        return 2
    print("[off-tree] %d branch(es) read, %d commit(s) off %s" % (read, len(rows), args.tree), file=sys.stderr)
    for r in rows:
        print("\t".join((r["lane"], r["sha"], r["side"], r["branches"], r["subject"])))
    return 1 if rows else 0


if __name__ == "__main__":
    sys.exit(main())
