# -*- coding: utf-8 -*-
"""총괄 6e041f4cb ②: `database_outbox.ledger_state` gained a third written value - «done · skipped:
<소스>» - on the promise that nothing outside `ledger/followup.py` reads more of the cell than
whether it is empty. This finds every seat that names the cell in code and holds them to that.

The text is the subject here (a drift oracle), not a stand-in for behaviour: the question is
「who reads this column, and how」, and a new reader that compares the value is what must go red.

⚠️ ONE READER IS NAMED, NOT HELD: the migration that adds the cell reads it through its own
`COLUMN` constant, for a report that groups events by the part before ':' - «done · skipped»
shows there as a group of its own. A display, no decision.
"""
import ast
import os
import re

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OWNER = os.path.join("ledger", "followup.py")
MIGRATION = os.path.join("migrations", "add_outbox_ledger_state.py")
SQL_EMPTINESS = re.compile(r"\s+IS\s+(NOT\s+)?NULL\b", re.I)


def _docstrings(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _readers():
    """(file, line, how) for every read of the cell in code outside the owner and the migration."""
    found = []
    for root, dirs, files in os.walk(SERVER):
        dirs[:] = [d for d in dirs if d not in ("tests", ".tmp", "__pycache__", "_archive")]
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), SERVER)
            if not name.endswith(".py") or rel in (OWNER, MIGRATION):
                continue
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as fh:
                source = fh.read()
            if "ledger_state" not in source:
                continue
            tree = ast.parse(source)
            docs = _docstrings(tree)
            parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and id(node) not in docs and "ledger_state" in node.value):
                    for match in re.finditer(r"ledger_state", node.value):
                        tail = node.value[match.end():]
                        found.append((rel, node.lineno, "sql", bool(SQL_EMPTINESS.match(tail))))
                if isinstance(node, ast.Attribute) and node.attr == "ledger_state":
                    parent = parents.get(id(node))
                    call = parents.get(id(parent)) if parent is not None else None
                    asks_emptiness = (isinstance(parent, ast.Attribute)
                                      and parent.attr in ("isnot", "is_")
                                      and isinstance(call, ast.Call)
                                      and [getattr(a, "value", 0) for a in call.args] == [None])
                    found.append((rel, node.lineno, "orm", asks_emptiness))
    return found


def test_every_reader_outside_the_owner_asks_only_whether_the_cell_is_empty():
    readers = _readers()
    assert len(readers) >= 4                       # the worker · the index · the purge script (2)
    assert [r for r in readers if not r[3]] == []
