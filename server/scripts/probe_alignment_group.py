# -*- coding: utf-8 -*-
"""S-94: split ONE chain group's mapper call, in this process, read-only.

🔴 WHY IT READS AND WRITES NOTHING. The alignment mapper is called by the chain worker
once per transaction group and returns updates for the caller to write; this hands it
rows READ from the box's own source table, times the phases the mapper opens, and throws
the updates away. So the group's cost can be split without a restart, without a live
config load, and without the group's writes landing twice.

🔴 WHY THE PHASES COME FROM THE PRODUCT AND NOT FROM WRAPPERS HERE. `map_alignment`
already opens named phases inside the group scope (`alignment_batch_counts.phase`), which
is what makes the split the SAME split the chain worker's own group line reports. A second
set of timings taken here would be a second spelling of the same measurement, free to
disagree with the one an operator actually sees.

⚠️ THE MAPPER COMES OUT OF THE RULE. A chain rule declares `mapper_module` and
`mapper_function` (all nine on the shipped catalogue do), so the probe reads them rather
than being told twice - `--mapper` exists only to point the same run at a DIFFERENT file,
which is how the shipped `.sample` gets measured instead of this box's copy.

⚠️ THE PAYLOAD COLUMN IS ASKED FOR, NOT GUESSED. The column a batch mapper keys on is
declared under a name that VARIES by mapper (`reference_job_column`, `trigger_job_column`,
`source_job_column`, `job_column` ... - measured, five spellings over nine rules), so this
file does not pick one: `--key-column` is required and the refusal names the rule's own
fields when the column is not in the trigger table. Nothing here knows a table or a column.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.abspath(os.path.join(_HERE, ".."))
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_ROWS = 1000


class ProbeRefusal(Exception):
    """A refusal that names what is missing, rather than measuring something else."""


def load_module(path: str, name: str):
    """Load a mapper by path, so the SHIPPED sample can be measured as easily as the
    box's own copy - a measurement of the repository rather than of this installation."""
    if not os.path.exists(path):
        raise ProbeRefusal(f"no mapper at {path}")
    spec = importlib.util.spec_from_loader(
        name, importlib.machinery.SourceFileLoader(name, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_rule(rules_path: str, rule_name: str) -> dict:
    raw = json.load(open(rules_path, encoding="utf-8"))
    entries = raw if isinstance(raw, list) else (raw.get("rules") or raw)
    entries = entries if isinstance(entries, list) else list(entries.values())
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == rule_name:
            return entry
    raise ProbeRefusal(
        f"rule {rule_name!r} is not in {rules_path} - the names there are: "
        + ", ".join(sorted(str(e.get("name")) for e in entries if isinstance(e, dict))))


def run(rule_name: str, key_column: str, rows: int, rules_path: str,
        mapper_path: str | None, no_diagnostics: bool):
    import alignment_batch_counts
    from database import models
    from database.database import SessionLocal
    from sqlalchemy import text

    # The dynamic ORM models are built at boot; a bare process has none, and the view
    # builder refuses BY NAME when it cannot find the source table.  Passing no engine
    # keeps this from touching the schema.
    models.refresh_dynamic_models()

    rule = find_rule(rules_path, rule_name)
    trigger_table = rule.get("trigger_table")
    if not trigger_table:
        raise ProbeRefusal(
            f"rule {rule_name!r} declares no `trigger_table`, so there are no rows to "
            f"make a group out of - its fields are: {', '.join(sorted(rule))}")

    db = SessionLocal()
    try:
        started = time.perf_counter()
        try:
            found = db.execute(text(
                f'SELECT "{key_column}" FROM "{trigger_table}" '
                f'WHERE "{key_column}" IS NOT NULL ORDER BY row_id DESC LIMIT :n'),
                {"n": rows}).fetchall()
        except Exception as err:                                        # noqa: BLE001
            db.rollback()
            raise ProbeRefusal(
                f'"{trigger_table}" would not answer for column {key_column!r} ({err}). '
                f"The rule's own fields are: {', '.join(sorted(rule))}")
        read_seconds = time.perf_counter() - started
        # The durable outbox contract a mapper reads: `data.<column>.value`.
        payloads = [{"data": {key_column: {"value": record[0]}}} for record in found]
        distinct = len({record[0] for record in found})
        print(f"payloads {len(payloads)} (read in {read_seconds:.3f} s) | "
              f"distinct decision keys {distinct}")
        if not payloads:
            raise ProbeRefusal(
                f'"{trigger_table}" has no row with {key_column!r} set, so the group '
                f"would be empty and the split would be of nothing")

        if no_diagnostics:
            # ⚠️ THE PRODUCT IS NOT CHANGED. The scoring block's file half is written
            # unconditionally outside a group scope, so the only way to price it is to
            # detach the handlers in THIS process and run the same call again.
            import logging

            import map_alignment
            map_alignment._diag_logger()
            diag = logging.getLogger("map_alignment.diag")
            for handler in list(diag.handlers):
                diag.removeHandler(handler)
            print("diagnostics handlers detached for this run")

        mapper_entry = rule.get("mapper_function")
        if not mapper_entry:
            raise ProbeRefusal(f"rule {rule_name!r} declares no `mapper_function`")
        if mapper_path:
            mapper = load_module(mapper_path, "probe_mapper")
        else:
            module_name = rule.get("mapper_module")
            if not module_name:
                raise ProbeRefusal(f"rule {rule_name!r} declares no `mapper_module`")
            import importlib
            mapper = importlib.import_module(module_name)
        build = getattr(mapper, mapper_entry, None)
        if build is None:
            raise ProbeRefusal(
                f"{mapper} has no {mapper_entry!r} - the callables it does have are: "
                + ", ".join(sorted(n for n in dir(mapper) if callable(getattr(mapper, n))
                                   and not n.startswith("_"))))

        with alignment_batch_counts.counting_group() as summary:
            started = time.perf_counter()
            updates = build(db, payloads, rule)
            total = time.perf_counter() - started
        report = summary()
    finally:
        db.rollback()
        db.close()

    phases = report.get("phases") or {}
    named = sum(phases.values())
    print(f"\nmapper call        {total:8.3f} s   updates {len(updates or [])}")
    print(f"  view builds      {report['view_builds']:8d}"
          f"   references {report['reference_resolutions']}"
          f"   distinct maps {report['distinct_maps']}")
    for name, seconds in sorted(phases.items(), key=lambda kv: -kv[1]):
        print(f"  {name:16s} {seconds:8.3f} s   {seconds / total * 100:5.1f} %")
    print(f"  {'OUTSIDE THE VIEW':16s} {total - named:8.3f} s   "
          f"{(total - named) / total * 100:5.1f} %")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Split one chain group's mapper call into phases, in this process.")
    parser.add_argument("--rule", required=True, help="the chain rule to measure")
    parser.add_argument("--key-column", required=True,
                        help="the trigger-table column the batch mapper keys on, as the "
                             "rule declares it")
    parser.add_argument("--mapper", default=None,
                        help="measure a DIFFERENT file than the rule names - e.g. the "
                             "shipped .py.sample rather than this box's copy")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS,
                        help="how many source rows make up the group")
    parser.add_argument("--rules", default=os.path.join(_SERVER, "config",
                                                        "chain_rules.json"))
    parser.add_argument("--no-diagnostics", action="store_true",
                        help="detach the scoring-block handlers in this process, to price "
                             "what they cost")
    args = parser.parse_args(argv)

    os.chdir(_SERVER)
    try:
        run(args.rule, args.key_column, args.rows, args.rules, args.mapper,
            args.no_diagnostics)
    except ProbeRefusal as refusal:
        print(f"REFUSED: {refusal}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
