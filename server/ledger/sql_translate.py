"""The ledger's translation over a page read by SQL (lead 10-31 ② stage 1): one SELECT of the columns a declarative
source names, the page held as CELLS (column -> tuple), and today's judges called on them - no DataFrame per
molecule. It writes nothing; `python -m ledger sql-shadow` holds it against the Python path atom by atom. A source
whose mapper is code is not this path's (`NotCovered`) - it stays on the Python path and is counted apart."""
from __future__ import annotations

from . import roleframe
from .event_frame import SourcePreparationContext, SourcePreparationError, named_columns, prepared_molecules
from .setup_bundle import executes_the_bindings


class NotCovered(Exception):
    """The source's mapper is code, not its declaration - the Python path translates it."""


def covers(plan) -> bool:
    return executes_the_bindings(plan.driver.mapper.implementation.implementation_id)


#: the switch (lead 11-01 stage 3): `ingestion_settings.json` "ledger_translate" - "python" sends every source back
#: to the Python path; anything else, or absent, is "sql". One for the deployment, no switch a source. Read a page,
#: held until the file changes (`read_ingestion_settings`), so a process takes a change at its next page
TRANSLATE_SETTING = "ledger_translate"
#: the words the log line and the run's result both say (the run stores it as `translated_by_label`)
TRANSLATED_BY = "translated by"
_said_path = {}


def translate_path(plan) -> str:
    """"sql" or "python" for this source's next page - python when the switch says so or the mapper is code (a code
    mapper stays on the Python path until stage 4). Said at a process's first page and at each change of the switch."""
    import logging

    from ingestion.settings import read_ingestion_settings

    value = read_ingestion_settings().get(TRANSLATE_SETTING, "sql")
    if "value" not in _said_path or _said_path["value"] != value:
        logging.getLogger(__name__).warning("[Ledger] %s %s (ingestion_settings.json %s: %r)", TRANSLATED_BY,
                                            "python" if value == "python" else "sql", TRANSLATE_SETTING, value)
    _said_path["value"] = value
    return "python" if value == "python" or not covers(plan) else "sql"


def translated_by(plan, start) -> str:
    """A run's path: the one it started on, or «sql → python» when the switch changed under it."""
    end = translate_path(plan)
    return start if start == end else "%s → %s" % (start, end)


def read_page(connection, plan, **page) -> list:
    """The page's rows - the columns the declaration names (`named_columns`; no other column reaches an atom, 판정
    201), by the read `backfill` pages with (`after` · `upper` · `limit` · `scope`)."""
    from .backfill import _fetch_v2_lineage_rows

    return _fetch_v2_lineage_rows(connection, plan, named_columns(plan), **page)


def event_results(snapshot, source_id, rows) -> tuple:
    """A page's rows -> (one `roleframe.LedgerV2DryRunResult` a molecule, the preparation context with its refusals
    and excluded rows) - the same results `runtime_v2.preview_cursor_batch` hands the gate."""
    cells = {column: tuple(row[column] for row in rows) for column in rows[0]} if rows else {}
    results, context, _row_ids = cells_results(snapshot, source_id, cells, len(rows))
    return results, context


def cells_results(snapshot, source_id, cells, rows: int) -> tuple:
    """The page as cells (column -> tuple of `rows` values) -> (the results, the preparation context, {row ref: row
    id} of the rows a molecule took - what `runtime_v2._row_ref_index` reads off the Python path's frames)."""
    from .event_frame import FRAME_ROW_ID_COLUMN

    plan = snapshot.source_plans[source_id]
    if not covers(plan):
        raise NotCovered(f"{source_id}: mapper {plan.driver.mapper.implementation.implementation_id!r} is code")
    context = SourcePreparationContext(snapshot, plan)
    if not rows:
        return (), context, {}
    missing = [column for column in named_columns(plan) if column not in cells]
    if missing:
        raise SourcePreparationError(
            "source_preparation_incomplete", "source_batch.columns",
            f"base cursor batch is missing physical columns: {missing}")
    mapper = roleframe.MapperContext(snapshot, plan)
    descriptor, profile = plan.driver.mapper, plan.profile
    results = []
    ids, row_ids = cells.get(FRAME_ROW_ID_COLUMN), {}
    for positions, row_refs, instant, attrs in prepared_molecules(context, cells, rows):
        if ids is not None:
            row_ids.update((str(ref), str(ids[position])) for position, ref in zip(positions, row_refs)
                           if ids[position] is not None and ref is not None)
        molecule = {column: tuple(values[position] for position in positions) for column, values in cells.items()}
        molecule[roleframe.SOURCE_ROW_REF_COLUMN] = tuple(row_refs)
        molecule[roleframe.SOURCE_OCCURRED_AT_COLUMN] = (instant,) * len(positions)
        emissions, unsaid = [], []
        units = roleframe.unit_partition(mapper, descriptor, molecule, len(positions),
                                         roleframe.checked_row_refs(row_refs))
        for index, (unit, refs, _whole) in enumerate(units):
            columns = {column: tuple(values[position] for position in unit) for column, values in molecule.items()}
            produced = roleframe.declared_emissions(mapper, profile, columns, refs, len(unit))
            roleframe.unit_emissions(mapper, profile, index, produced, None, columns, emissions, unsaid)
        results.append(roleframe.dry_run_result(
            mapper, attrs, roleframe.role_rows_of(mapper, attrs, emissions, unsaid, descriptor, profile)))
    return tuple(results), context, row_ids


def atom_records(plan, results) -> list:
    """The atoms `results` hand the gate (`runtime_v2`: registrations filtered, time basis stamped, event ids minted),
    each as one sorted-key JSON line of its semantic fields and its basis - what the shadow compares."""
    import json

    from . import runtime_v2

    groups = runtime_v2._filtered_event_atoms(results, ())
    runtime_v2._stamp_occurred_at_basis(plan, groups)
    records = []
    for atoms in groups:
        for atom in atoms:
            atom.ensure_source_event_identity()
            records.append(json.dumps(dict(runtime_v2._semantic_atom(atom), basis=atom.occurred_at_basis),
                                      sort_keys=True, default=str, ensure_ascii=False))
    return records


def shadow_source(engine, setup, source, page_rows=2000, max_pages=None, show=3) -> dict:
    """Every page of `source` translated by both paths, read only - the backfill's pages (page key order, cut at the
    same `after`). -> rows, pages, atoms each path, the atoms only one path made (count and the first `show`),
    refusals, excluded rows by cause (and the pages whose causes differ) and seconds each path."""
    import time
    from collections import Counter

    from . import backfill, runtime_v2
    from .setup import preview_selected_cursor_batch

    plan = setup.snapshot.source_plans[source]
    page_key, readable = backfill._page_key(plan), backfill._readable_columns(engine, plan)
    said = {"source": source, "rows": 0, "pages": 0, "atoms": {"python": 0, "sql": 0},
            "only": {"python": 0, "sql": 0}, "first": {"python": [], "sql": []},
            "refused": {"python": 0, "sql": 0}, "excluded": {"python": {}, "sql": {}}, "excluded_pages_differ": 0,
            "seconds": {"python": 0.0, "sql": 0.0}}
    after = None
    while max_pages is None or said["pages"] < max_pages:
        raw = engine.raw_connection()
        try:
            full = backfill._fetch_v2_lineage_rows(raw, plan, readable, after=after, limit=page_rows)
            narrow = read_page(raw, plan, after=after, limit=page_rows)
        finally:
            raw.close()
        if not full:
            break
        said["pages"] += 1
        said["rows"] += len(full)
        frame = backfill._v2_frame(full)
        started = time.perf_counter()
        with roleframe.times_read(backfill.times_read_of(engine, plan, frame)):
            preview = preview_selected_cursor_batch(setup, source, frame, runtime_v2.last_cursor(plan, frame),
                                                    known_registrations=(), translate="python")
            python = atom_records(plan, preview.event_results)
        said["seconds"]["python"] += time.perf_counter() - started
        started = time.perf_counter()
        cells = {column: tuple(row[column] for row in narrow) for column in narrow[0]}
        with roleframe.times_read(backfill.times_read_of(engine, plan, cells)):
            results, context = event_results(setup.snapshot, source, narrow)
            sql = atom_records(plan, results)
        said["seconds"]["sql"] += time.perf_counter() - started
        said["refused"]["python"] += len(preview.refusals)
        said["refused"]["sql"] += len(context.refusals)
        kept_out = {"python": dict(preview.excluded_rows or {}), "sql": dict(context.excluded_rows or {})}
        said["excluded_pages_differ"] += kept_out["python"] != kept_out["sql"]
        for name, causes in kept_out.items():
            for cause, n in causes.items():
                said["excluded"][name][cause] = said["excluded"][name].get(cause, 0) + n
        for name, mine, theirs in (("python", python, sql), ("sql", sql, python)):
            said["atoms"][name] += len(mine)
            extra = list((Counter(mine) - Counter(theirs)).elements())
            said["only"][name] += len(extra)
            said["first"][name].extend(extra[:max(0, show - len(said["first"][name]))])
        after = full[-1][page_key]
    said["seconds"] = {name: round(value, 1) for name, value in said["seconds"].items()}
    said["rows_per_s"] = {name: (round(said["rows"] / value) if value else None)
                          for name, value in said["seconds"].items()}
    return said


def differs(said) -> bool:
    """The two paths are the same only when the atoms, the refusals and every page's excluded rows by cause are."""
    return bool(any(said["only"].values()) or said["refused"]["python"] != said["refused"]["sql"]
                or said["excluded_pages_differ"])


def main(argv=None) -> int:
    """`python -m ledger sql-shadow` - every page of every declarative source through both paths, read only; exit 1
    when the atoms, the refusals or a page's excluded rows by cause differ."""
    import argparse
    import json
    import sys

    from sqlalchemy import create_engine

    parser = argparse.ArgumentParser(
        prog="python -m ledger sql-shadow",
        description="Translate every page by the Python path and the SQL path and compare the atoms (writes nothing)")
    parser.add_argument("--world", default=None, help="this world; the operating one when absent")
    parser.add_argument("--source", action="append", default=None, help="this source (repeatable); every one when absent")
    parser.add_argument("--page-rows", type=int, default=2000)
    parser.add_argument("--max-pages", type=int, default=None, help="stop each source after this many pages")
    parser.add_argument("--show", type=int, default=3, help="atoms shown per side when they differ")
    args = parser.parse_args(argv)

    from database.database import engine as live
    from . import schema
    from .setup import load_setup

    setup = load_setup(schema.require_world(args.world).declaration_root)
    engine = create_engine(live.url, connect_args={"options": "-c default_transaction_read_only=on"})
    plans = {name: plan for name, plan in setup.snapshot.source_plans.items() if plan.runs}
    wanted = args.source or sorted(plans)
    different = False
    for source in wanted:
        if source not in plans:
            print(json.dumps({"source": source, "skipped": "not a planned source"}, ensure_ascii=False))
            continue
        if not covers(plans[source]):
            print(json.dumps({"source": source, "skipped": "mapper is code - the Python path translates it"},
                             ensure_ascii=False))
            continue
        said = shadow_source(engine, setup, source, args.page_rows, args.max_pages, args.show)
        different = different or differs(said)
        print(json.dumps(said, ensure_ascii=False), flush=True)
    print("DIFFERENT" if different else "SAME", file=sys.stderr)
    return 1 if different else 0
