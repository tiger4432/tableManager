# -*- coding: utf-8 -*-
"""S-192. Run a mapper or a parser on a sample and see what comes out. No writes.

Owner 2026-09-12: 「체인 맵퍼·인제션 파서 개발용 시험 환경 — 샘플 인풋과 핵심 로직 아웃풋만」.

🔴 BOTH SEAMS ALREADY EXISTED; WHAT WAS MISSING WAS A PLACE TO STAND. A mapper is
`(df, db) -> df` under `mapper_sdk.mapper`, and a parser is
`pipeline_base.parse(file_path) -> list[dict]`. Neither needed inventing. What did not exist
was running either one WITHOUT writing to the database, and a shape where the sample and the
expectation are just files.

⚠️ THE db IS READ-ONLY BECAUSE THE SERVER SAYS SO, NOT BECAUSE THIS MODULE IS CAREFUL
(판정 301). The first draft wrapped the call in a transaction and rolled back -- and `conftest`
already records why that is not enough: 「the code under test COMMITS」, so a rollback is void
wherever anything commits. `db_safety.open_readonly_connection` + `assert_readonly` make
PostgreSQL refuse the write, and `db_safety` even records that the obvious setting
(`default_transaction_read_only`) is not the one the server enforces.

🔴 A PARSER IS CHOSEN THE WAY PRODUCTION CHOOSES ONE -- BY CLAIM, NOT BY NAME (판정 301).
`scan_workspace_pipeline_parsers` walks the workspace, asks each class `match(path)`, and the
first one that says yes takes the file. There is no name to look a parser up by, and adding
one would have built a bench that exercises a path production never takes. `force=` exists
for the real development case: a parser whose `match()` does not claim the file YET.
"""
from __future__ import annotations

import csv
import io
import json
import os

MAPPER = "mapper"
PARSER = "parser"
KINDS = (MAPPER, PARSER)


def read_sample(path):
    """A sample file as rows. CSV/TSV by delimiter, JSON as a list of objects."""
    if path.lower().endswith(".json"):
        with io.open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, list) else [loaded]
    delimiter = "\t" if path.lower().endswith((".tsv", ".tab")) else ","
    with io.open(path, encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]


def as_payloads(rows):
    """Sample rows in the shape the worker hands a mapper.

    ⚠️ `payloads_to_df` READS `{col: {"value": x}}`, which is the OUTBOX envelope and not what
    anybody writes in a CSV. A flat row is wrapped; a row already in envelope shape is left
    alone, so a sample captured from a real payload works unchanged.
    """
    out = []
    for index, row in enumerate(rows):
        if any(isinstance(v, dict) and "value" in v for v in row.values()):
            out.append(row)
            continue
        cells = {k: {"value": v} for k, v in row.items() if k != "row_id"}
        cells["row_id"] = row.get("row_id") or "sample-%d" % index
        out.append(cells)
    return out


def rows_to_tsv(rows):
    """The ONE text form of a result, shared by the CLI and the pytest fixture.

    🔴 IT GOES THROUGH `wire_text` (S-190), so a cell here reads exactly as the grid and the
    CSV export read it. A bench that spelled a JSON cell its own way would let an author
    match an expectation the product never produces.
    """
    from utils.wire_format import wire_text

    rows = list(rows or ())
    columns = []
    for row in rows:
        for name in row:
            if name not in columns:
                columns.append(str(name))
    lines = ["\t".join(columns)]
    for row in rows:
        cells = []
        for name in columns:
            value = row.get(name)
            if value is None:
                cells.append("")
                continue
            text = str(wire_text(value))
            cells.append(text.replace("\t", " ").replace("\r", " ").replace("\n", " "))
        lines.append("\t".join(cells))
    return "\n".join(lines) + "\n"


def _frame_rows(frame):
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return frame.to_dict(orient="records")
    return list(frame)


# ---------------------------------------------------------------------------
# the read-only footing
# ---------------------------------------------------------------------------

def _readonly_session():
    """A Session the SERVER refuses writes on, plus its teardown.

    ⚠️ A MAPPER THAT NEVER TOUCHES `db` MUST STILL RUN. Most do not, and requiring a live
    PostgreSQL to try one would make the bench useless in exactly the case it is best at --
    so a database that cannot be opened yields `None` and the mapper is handed that.
    """
    try:
        import db_safety
        from sqlalchemy.orm import Session

        engine = db_safety.open_readonly_engine()
        conn = db_safety.open_readonly_connection(engine)
        db_safety.assert_readonly(conn)
        session = Session(bind=conn)

        def closer():
            try:
                session.close()
            finally:
                db_safety.close_readonly_connection(conn)
                engine.dispose()

        return session, closer
    except Exception:
        return None, lambda: None


# ---------------------------------------------------------------------------
# the mapper
# ---------------------------------------------------------------------------

def try_mapper(name, sample, *, rule=None, target_table="bench_target"):
    """Run one mapper over `sample`. Returns `{who, rows, refusal}`; never writes.

    `name` resolves through the decorator's registry (S-188 ⓒ) and falls back to
    `module:function`, because the registry is empty wherever no mapper file uses the
    decorator yet -- measured zero on this box.
    """
    import mapper_sdk

    rows = sample if isinstance(sample, list) else read_sample(sample)
    payloads = as_payloads(rows)

    fn = mapper_sdk.MAPPER_REGISTRY.get(name)
    who = name
    if fn is None and (":" in name or "." in name):
        import importlib

        separator = ":" if ":" in name else "."
        module_name, _, function_name = name.rpartition(separator)
        try:
            fn = getattr(importlib.import_module(module_name), function_name)
            who = "%s.%s" % (module_name, function_name)
        except Exception as exc:
            return {"who": name, "rows": [],
                    "refusal": "%s: %s" % (type(exc).__name__, exc)}
    if fn is None:
        registered = ", ".join(sorted(mapper_sdk.MAPPER_REGISTRY)) or "none"
        return {"who": name, "rows": [],
                "refusal": "no mapper named %r; registered: %s "
                           "(or give module:function)" % (name, registered)}

    effective_rule = dict(rule or {})
    effective_rule.setdefault("name", "bench")
    effective_rule.setdefault("target_table", target_table)

    session, closer = _readonly_session()
    try:
        try:
            out = fn(session, payloads, rule=effective_rule)
        except TypeError as exc:
            # ⚠️ A mapper that never declared `rule` is called the old way by the worker too,
            # so the bench must not be stricter than production. The message is checked so a
            # genuine TypeError INSIDE the mapper is not swallowed as a signature mismatch.
            if "rule" not in str(exc):
                raise
            out = fn(session, payloads)
    except Exception as exc:
        return {"who": who, "rows": [], "refusal": "%s: %s" % (type(exc).__name__, exc)}
    finally:
        closer()

    if isinstance(out, dict):
        return {"who": who, "rows": list(out.get("updates") or ()), "refusal": None}
    return {"who": who, "rows": _frame_rows(out), "refusal": None}


# ---------------------------------------------------------------------------
# the parser
# ---------------------------------------------------------------------------

def try_parser(file_path, *, force=None, scripts_path=None):
    """Parse one file the way production would. Returns `{who, rows, refusal}`. No database.

    🔴 SELECTION IS BY CLAIM. Each parser class is offered the path and answers `match()`;
    the first yes takes it, and 「nobody claimed it」 is an ANSWER rather than an error --
    `directory_watcher` already distinguishes those two. `force="File.py::Class"` (or just the
    class name) runs a parser whose `match()` has not been written yet.
    """
    from parsers.directory_watcher import (SCAN_UNAVAILABLE,
                                           scan_workspace_pipeline_parsers)

    scripts_path = scripts_path or _default_scripts_path()
    load_errors = {}
    offered = []

    def visit(filename, obj):
        label = "%s::%s" % (filename, obj.__name__)
        offered.append(label)
        if force:
            if force not in (label, obj.__name__):
                return None
        else:
            try:
                if not obj.match(file_path):
                    return None
            except Exception as exc:
                load_errors[label] = "match(): %s: %s" % (type(exc).__name__, exc)
                return None
        instance = obj()
        # The watcher hands the path in as an ATTRIBUTE for the same reason: `parse(path)` is
        # a contract user scripts already subclass.
        instance.rel_path = os.path.basename(file_path)
        return (label, instance.parse(file_path))

    try:
        claim = scan_workspace_pipeline_parsers(scripts_path, visit, load_errors)
    except Exception as exc:
        return {"who": None, "rows": [], "refusal": "%s: %s" % (type(exc).__name__, exc)}

    if claim is SCAN_UNAVAILABLE:
        return {"who": None, "rows": [],
                "refusal": "the parser workspace is unavailable at %s" % scripts_path}
    if claim is None:
        detail = "; ".join("%s -> %s" % (k, v) for k, v in sorted(load_errors.items()))
        return {"who": None, "rows": [],
                "refusal": "no parser claimed this file (offered: %s)%s"
                           % (", ".join(offered) or "none",
                              "; " + detail if detail else "")}
    who, rows = claim
    return {"who": who, "rows": list(rows or ()), "refusal": None}


def _default_scripts_path():
    try:
        import paths

        return os.path.join(paths.workspace_path(), "scripts")
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")


# ---------------------------------------------------------------------------
# the shells read THIS, so a folder is a test
# ---------------------------------------------------------------------------

def run_sample_folder(folder):
    """`<kind>/<name>/input.* (+ rule.json | force.txt)` -> the same result dict.

    🔴 THE CLI AND THE PYTEST FIXTURE BOTH COME HERE. Two entry points that each assembled
    the call would drift, and then 「it works from the command line」 and 「the test passes」
    would be different facts about one mapper.
    """
    folder = os.path.abspath(folder)
    kind = os.path.basename(os.path.dirname(folder))
    name = os.path.basename(folder)
    inputs = sorted(f for f in os.listdir(folder) if f.startswith("input."))
    if not inputs:
        return {"who": None, "rows": [], "refusal": "no input.* in %s" % folder}
    target = os.path.join(folder, inputs[0])

    if kind == PARSER:
        force_file = os.path.join(folder, "force.txt")
        force = None
        if os.path.exists(force_file):
            force = io.open(force_file, encoding="utf-8").read().strip() or None
        # ⚠️ The parser's own folder is the workspace: the sample ships its parser beside its
        # input, so a repository sample needs nothing from the operator's workspace.
        return try_parser(target, force=force, scripts_path=folder)

    rule_file = os.path.join(folder, "rule.json")
    rule = None
    if os.path.exists(rule_file):
        rule = json.load(io.open(rule_file, encoding="utf-8"))
    mapper_name = (rule or {}).get("mapper") or name
    return try_mapper(mapper_name, target, rule=rule)


def expected_path(folder):
    return os.path.join(folder, "expected.tsv")


def sample_folders(root, kind=None):
    """Every `<root>/<kind>/<name>/` that has an `input.*`. A folder IS a test."""
    found = []
    for one in (KINDS if kind is None else (kind,)):
        base = os.path.join(root, one)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            folder = os.path.join(base, name)
            if os.path.isdir(folder) and any(
                    f.startswith("input.") for f in os.listdir(folder)):
                found.append(folder)
    return found
