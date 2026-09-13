"""S-78's gate: how many tracked scripts still write SQL straight at the database.

🔴 WHY A PARSER AND NOT A GREP. `git grep "INSERT INTO\\|DELETE FROM" -- server/scripts`
returns 94 lines, and 62 of them write nothing: 56 are docstrings telling an operator how
to roll a seed back, and 6 are `print` calls putting those same instructions on stdout.
Driving that grep to zero would mean deleting the recovery instructions - taking undo away
from the operator, which is the opposite of what S-78 is for.

⚠️ AND THE GREP FAILS THE OTHER WAY TOO, which is how this file came to exist. The first
census of these scripts was piped through `head -25` against a 102-line result, so three
raw INSERTs were never seen and a count taken off the truncated list was published. A grep
cannot tell prose from code and a pipe can hide either; `ast` can tell, and prints
everything.

THE THREE BUCKETS, and only the first is the gate:

    write       SQL on a line that is neither a docstring, a comment, nor a print. Gate 0.
    printed     SQL inside a `print(...)` - rollback instructions on stdout. Keep.
    docstring   SQL inside a bare string expression - how to recover. Keep.

Run it with no arguments; it exits non-zero while any write site remains.
"""
from __future__ import annotations

import ast
import io
import tokenize
import os
import re
import subprocess
import sys

SQL = re.compile(r"\b(INSERT\s+INTO|DELETE\s+FROM|UPDATE\s+\w+\s+SET)\b", re.I)

#: Excluded by path, each for a stated reason rather than to make the number look better.
#:   🪦 `_archive` was listed here and is gone (S-210, 판정 353). MEASURED while removing it:
#:      this walks `server/scripts`, where no `_archive` has ever existed - so the entry was
#:      excluding nothing on the day it was written, not only after the deletion.
#:   migrat    schema migrations - DDL and one-time data moves are not the product's writes
#:   dev_env   isolated-environment cloning; a restore puts a whole state down at once and
#:             is outside the algebra rather than a write that skipped the door
#: 🔴 EXCLUDED BY NAME PATTERN, NEVER BY A HAND-KEPT LIST (ruling 186). A list of file
#: names would need editing every time one is added, and the day it is not edited the gate
#: reads green for a file nobody classified. A prefix is a claim the file makes about
#: itself, and it comes with an obligation: a `migrate_`/`ops_` script writes ledger or
#: outbox tables that the product door does not serve, and carries S-77's shape - dry run by
#: default, `--apply --i-accept-writing-to-owner-database` to write.
SKIP_DIRS = ("dev_env",)
SKIP_PREFIXES = ("migrate_", "ops_")


def tracked_scripts(root="server/scripts"):
    listing = subprocess.run(["git", "ls-files", root],
                             capture_output=True, text=True).stdout.split()
    kept = []
    for path in listing:
        if not path.endswith(".py"):
            continue
        if any(part in path for part in SKIP_DIRS):
            continue
        if os.path.basename(path).startswith(SKIP_PREFIXES):
            continue
        kept.append(path)
    return kept


def _spans(tree, matches):
    return [(node.lineno, getattr(node, "end_lineno", node.lineno))
            for node in ast.walk(tree) if matches(node)]


def classify(path):
    """-> (writes, printed, docstring), each a list of (line number, text)."""
    source = io.open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # A file this tool cannot parse is REPORTED, never skipped silently - a parse
        # failure is the one case where "no hits" and "not looked at" would be the same.
        raise
    # 🔴 A `#` COMMENT IS NOT CODE, AND THE AST CANNOT SEE ONE. Comments are discarded
    # before parsing, so a comment explaining why a DELETE moved to the door counted as a
    # DELETE - measured on this very file's own explanation. `tokenize` keeps them.
    comment_lines = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and SQL.search(token.string):
                comment_lines.add(token.start[0])
    except (tokenize.TokenError, IndentationError):
        pass

    docs = _spans(tree, lambda n: isinstance(n, ast.Expr)
                  and isinstance(n.value, ast.Constant)
                  and isinstance(n.value.value, str))
    prints = _spans(tree, lambda n: isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == "print")
    # 🔴 A CONSTANT THAT IS ONLY EVER PRINTED IS NOT A WRITE. `respell_syn_frame_map_ids`
    # keeps its undo as a module-level string and prints it three times; the first version
    # of this gate counted that definition as a write site, which would have pushed someone
    # to delete the operator's rollback instructions to reach zero. The name is followed to
    # its uses: if every load of it sits inside a `print`, its definition is prose.
    printed_only = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str) and SQL.search(node.value.value)):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        for name in names:
            loads = [n for n in ast.walk(tree)
                     if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)]
            if loads and all(any(lo <= n.lineno <= hi for lo, hi in prints) for n in loads):
                printed_only.add((node.value.lineno, getattr(node.value, "end_lineno",
                                                             node.value.lineno)))

    writes, printed, docstring = [], [], []
    for number, line in enumerate(source.split("\n"), 1):
        if not SQL.search(line):
            continue
        entry = (number, line.strip()[:72])
        if number in comment_lines:
            docstring.append(entry)
        elif any(lo <= number <= hi for lo, hi in docs):
            docstring.append(entry)
        elif any(lo <= number <= hi for lo, hi in printed_only):
            printed.append(entry)
        elif any(lo <= number <= hi for lo, hi in prints):
            printed.append(entry)
        else:
            writes.append(entry)
    return writes, printed, docstring


def main(argv=None):
    os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    totals = [0, 0, 0]
    offenders = {}
    unparsed = []
    for path in tracked_scripts():
        try:
            writes, printed, docstring = classify(path)
        except SyntaxError as exc:
            unparsed.append((path, exc))
            continue
        totals[0] += len(writes)
        totals[1] += len(printed)
        totals[2] += len(docstring)
        if writes:
            offenders[path] = writes

    for path, sites in sorted(offenders.items(), key=lambda kv: -len(kv[1])):
        print("%-52s %d" % (path.replace("server/scripts/", ""), len(sites)))
        for number, line in sites:
            print("    :%-6d %s" % (number, line))
    for path, exc in unparsed:
        print("UNPARSED %s: %s" % (path, exc))

    print("")
    print("raw write sites   %d   <- the gate; 0 is the target" % totals[0])
    print("printed as text   %d   (rollback instructions on stdout - kept)" % totals[1])
    print("docstring text    %d   (how to recover - kept)" % totals[2])
    if unparsed:
        print("unparsed files    %d   <- these were NOT checked" % len(unparsed))
    return 1 if (totals[0] or unparsed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
