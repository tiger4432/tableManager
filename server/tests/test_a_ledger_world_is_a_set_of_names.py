# -*- coding: utf-8 -*-
"""총괄 60d7e8e42 · fb7ece9a3 · 8d10633ae — a ledger world is a set of NAMES, answered by one
seat (`schema.world_names`). An install with no branch writes exactly what it wrote before: every
statement `ensure_schema` and `ensure_partition` issue for the default world is compared to
the recorded text of the tree that had no worlds (`support/ledger_default_ddl.json`, a drift
oracle - the text IS the subject). A branch's statements name only its own schema, so no
branch statement can fall through `search_path` onto the default ledger.
"""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import schema                                               # noqa: E402

ORACLE = os.path.join(os.path.dirname(__file__), "support", "ledger_default_ddl.json")
WHEN = datetime(2026, 9, 15, 3, 0, tzinfo=timezone.utc)
#: The two catalogue states an install can be in: nothing yet, and up to date.
STATES = {
    "fresh": {"relation": False, "column": False, "constraints": {}},
    "current": {"relation": True, "column": True, "constraints": {
        schema.OBJECTLESS_PAYLOAD_CONSTRAINT: True,
        schema.RETIRED_REGISTER_OBJECT_CONSTRAINT: False,
        schema.RETIRED_OBJECTLESS_CONSTRAINT: False}},
}


class _Cursor:
    """Records every statement and answers the three catalogue questions from `state`."""

    def __init__(self, log, state):
        self.log, self.state, self.answer = log, state, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.log.append([sql, list(params) if params else None])
        if "pg_constraint" in sql:
            self.answer = (1,) if self.state["constraints"].get(params[1]) else None
        elif "pg_attribute" in sql:
            self.answer = (self.state["column"],)
        elif "to_regclass" in sql:
            self.answer = (self.state["relation"],)
        else:
            self.answer = None

    def fetchone(self):
        return self.answer

    def fetchall(self):
        return []


class _Connection:
    def __init__(self, state):
        self.log, self.state = [], state

    def cursor(self):
        return _Cursor(self.log, self.state)

    def commit(self):
        self.log.append(["COMMIT", None])

    def rollback(self):
        self.log.append(["ROLLBACK", None])


def record(names=None):
    """Every statement one world's `ensure_schema` + one month's `ensure_partition` issue,
    in both catalogue states."""
    out = {}
    for label, state in STATES.items():
        connection = _Connection(state)
        if names is None:
            schema.ensure_schema(connection)
            schema.ensure_partition(connection, WHEN)
        else:
            schema.ensure_schema(connection, names=names)
            schema.ensure_partition(connection, WHEN, names=names)
        out[label] = connection.log
    return out


def test_an_install_with_no_branch_issues_the_statements_it_always_did():
    with open(ORACLE, encoding="utf-8") as fh:
        oracle = json.load(fh)
    assert record() == oracle
    assert record(schema.world_names()) == oracle


#: The seat's answers that say WHICH KIND of world it is. Testing one of them is asking the
#: world; `ledger/schema.py` is the one place that may.
_KIND = {"world", "base_root", "space_statements", "beneath"}


def _asks_the_world(path):
    """(line, what) for every test in `path` that decides by the kind of world: a kind answer
    read inside a condition, or a `world` compared with a constant. Membership in a cache
    (`in` / `not in`) is not a decision about the world and is not counted."""
    import ast

    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    found = []

    def walk(expression, line):
        for node in ast.walk(expression):
            if isinstance(node, ast.Compare) and any(
                    isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
                return
        for node in ast.walk(expression):
            if isinstance(node, ast.Attribute) and node.attr in _KIND:
                found.append((line, node.attr))
            if isinstance(node, ast.Compare):
                sides = [node.left, *node.comparators]
                named = any((isinstance(s, ast.Name) and s.id == "world")
                            or (isinstance(s, ast.Attribute) and s.attr == "world")
                            for s in sides)
                if named and any(isinstance(s, ast.Constant) for s in sides):
                    found.append((line, "world == constant"))

    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.IfExp, ast.While, ast.Assert)):
            walk(node.test, node.lineno)
        elif isinstance(node, ast.comprehension):
            for condition in node.ifs:
                walk(condition, condition.lineno)
    return sorted(set(found))


def test_no_seat_outside_the_world_seat_asks_which_world_it_is_in():
    """총괄 fb7ece9a3 8: 「세상을 묻는 자리는 한 좌석」 - a branch-only turn outside
    `schema.world_names`'s module is a second door. Counted by AST over every tracked
    production file; the seat itself is the canary (it must be found asking)."""
    import subprocess

    server = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    files = [name for name in subprocess.run(
        ["git", "-C", server, "ls-files", "*.py"], capture_output=True, text=True,
        check=True).stdout.split()
        if not name.startswith(("tests/", "scripts/", "migrations/"))]
    assert len(files) > 100 and "ledger/schema.py" in files, len(files)
    assert _asks_the_world(os.path.join(server, "ledger", "schema.py")), \
        "the seat itself must be found asking - else this counts nothing"
    outside = {name: _asks_the_world(os.path.join(server, name))
               for name in files if name != "ledger/schema.py"}
    assert {name: found for name, found in outside.items() if found} == {}


_FOUR_ROOTS = r"""
import os, sys
sys.path.insert(0, os.getcwd())
from ledger import config, setup
from ledger.schema import world_names
from ledger_api import declared_entities
print(os.path.normcase(os.path.normpath(str(setup.DEFAULT_ONTOLOGY_ROOT))))
print(os.path.normcase(os.path.dirname(os.path.normpath(config.config_path()))))
print(os.path.normcase(os.path.dirname(os.path.normpath(declared_entities._config_path()))))
print(os.path.normcase(os.path.dirname(os.path.normpath(world_names().declaration_path))))
"""


@pytest.mark.parametrize("data_root", [None, "isolated"])
def test_the_four_declaration_roots_are_one_path(tmp_path, data_root):
    """총괄 e61194b1a ㉥: setup, the loader, the declared-entities reader and the walk read the
    default declaration from ONE root. Unset `ASSY_DATA_ROOT` (production): the one it always
    was. Set: the isolated stack's own `<DATA_ROOT>/config/ontology`, all four alike."""
    import subprocess

    server = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env = {key: value for key, value in os.environ.items() if key != "ASSY_DATA_ROOT"}
    if data_root:
        env["ASSY_DATA_ROOT"] = str(tmp_path)
    done = subprocess.run([sys.executable, "-c", _FOUR_ROOTS], cwd=server, env=env,
                          capture_output=True, text=True)
    roots = done.stdout.split()
    assert len(roots) == 4, done.stderr[-800:]
    want = os.path.join(str(tmp_path) if data_root else server, "config", "ontology")
    assert set(roots) == {os.path.normcase(os.path.normpath(want))}, roots


def test_the_default_names_are_the_names_the_ledger_always_had():
    names = schema.world_names()
    assert (names.ledger, names.cursor, names.row_ref, names.read_relation) == (
        "ledger_events", "ledger_translator_cursor", "ledger_source_row_ref", "ledger_events")
    assert (schema.LEDGER_TABLE, schema.CURSOR_TABLE, schema.ROW_REF_TABLE) == (
        names.ledger, names.cursor, names.row_ref)
