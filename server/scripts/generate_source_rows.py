"""Generate SOURCE ROWS for a production-shaped box, at whatever scale is asked for.

🔴 WHY A ROW GENERATOR AND NOT AN ATOM GENERATOR.  「표에 원천 데이터를 넣고, 그걸로 원장」
is a standing rule, and `store.write_batch` has exactly one legitimate caller
(`ledger/runtime_v2.py`).  Atoms this script wrote directly would be atoms the
declaration does not know, and the walk cannot make a subject out of those - they would
be in the ledger and unreachable.  So this writes ROWS, the declared source reads them,
and the translator makes the atoms.  The multiplier from rows to atoms is therefore not a
knob here: it is `len(bind.mappings)` of the source, read from the declaration.

🔴 WHY IT IS DECLARATION-DRIVEN RATHER THAN CARRYING A COLUMN LIST.  A hardcoded column
list is a second declaration, and the day it disagrees with the catalog this script writes
rows the source cannot read - silently, because a missing column reads as a missing value.
`plan_for` therefore asks the catalog what the relation's columns are and refuses BY NAME
when the source needs a column the catalog does not declare.  Measured 2026-09-09 on the
shipped sample, `bonded_from` is exactly that case (see `MissingColumns`), and that refusal
is the point: the operator gets the eight names rather than eight silently blank columns.

THE FIVE KNOBS (owner's production shape, `CLAUDE.md` D6):
    rows      how many rows per source
    months    how many distinct months `occurred_at` spreads over -- more than one is what
              puts atoms in more than one partition
    monotonic whether the page key rises with insertion order.  `bonded_from` orders by a
              NAME axis and is therefore NOT monotonic, which is why its new rows are seen
              by the live path rather than by catch-up
    target    always a TABLE.  Not a knob so much as a refusal: a view is rejected, because
              rows cannot be inserted into one
    maps      how many 20x20 maps, each of a DIFFERENT material

Nothing here runs at import: the module is importable and the CLI is under `main`.
"""
from __future__ import annotations

import argparse
import calendar
import dataclasses
import datetime
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.abspath(os.path.join(_HERE, ".."))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

#: A map is 20x20 by the owner's production shape, and each map is a different material.
MAP_SIDE = 20
DEFAULT_ROWS = 1000
DEFAULT_MONTHS = 3
DEFAULT_MAPS = 0
SEOUL = datetime.timezone(datetime.timedelta(hours=9))


class GeneratorRefusal(Exception):
    """A refusal that names what is missing, rather than writing something wrong."""


@dataclasses.dataclass(frozen=True)
class MissingColumns(GeneratorRefusal):
    relation: str
    names: tuple[str, ...]

    def __str__(self) -> str:
        return (f"relation {self.relation!r} does not declare these columns, and the "
                f"source reads them: {', '.join(self.names)}. Declare them in the table "
                f"catalog, or point this source at the relation that has them.")


@dataclasses.dataclass(frozen=True)
class Plan:
    """What a run WOULD do, said before anything is written."""

    source_id: str
    relation: str
    target_table: str
    columns: tuple[str, ...]
    rows: int
    months: tuple[str, ...]
    monotonic: bool
    maps: int
    atoms_per_row: int

    @property
    def atoms(self) -> int:
        return self.rows * self.atoms_per_row

    def describe(self) -> str:
        lines = [
            f"source        {self.source_id}",
            f"relation      {self.relation}",
            f"target table  {self.target_table}",
            f"rows          {self.rows}",
            f"months        {len(self.months)}  ({', '.join(self.months)})",
            f"page key      {'monotonic' if self.monotonic else 'NOT monotonic'}",
            f"maps          {self.maps} x {MAP_SIDE}x{MAP_SIDE}"
            + (", each a different material" if self.maps else ""),
            f"atoms/row     {self.atoms_per_row}   (= len(bind.mappings))",
            f"atoms         {self.atoms}",
            f"columns       {', '.join(self.columns)}",
        ]
        return "\n".join(lines)


def months_from(count: int, *, end: datetime.date = None) -> tuple[str, ...]:
    """`count` distinct YYYY-MM labels ending at `end`'s month, oldest first.

    Distinct months are the point: the ledger partitions by RANGE (occurred_at), so a run
    whose rows all land in one month proves nothing about more than one partition.
    """
    if count < 1:
        raise GeneratorRefusal("months must be at least 1")
    end = end or datetime.date.today()
    labels = []
    year, month = end.year, end.month
    for _ in range(count):
        labels.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return tuple(reversed(labels))


def occurred_at_for(index: int, months: tuple[str, ...]) -> datetime.datetime:
    """Spread rows evenly over `months`, in Asia/Seoul, deterministically.

    Deterministic on purpose: a re-run with the same knobs writes the same instants, so a
    second run is a no-op at the ledger's dedupe key rather than a duplicate.
    """
    label = months[index % len(months)]
    year, month = (int(part) for part in label.split("-"))
    span = calendar.monthrange(year, month)[1]
    day = (index // len(months)) % span + 1
    return datetime.datetime(year, month, day, 12, 0, 0, tzinfo=SEOUL)


def load_declaration(setup_root=None, catalog_path: str = None):
    """The declaration and the catalog, through the ONE loader the server uses.

    🔴 `ledger.setup.load_setup` IS THAT LOADER, and calling it rather than re-doing its
    two loads is the whole reason this function is three lines. It resolves the catalog
    once and carries it on the result, so a reader that re-read the file could get a
    different answer -- which is exactly the second-opinion shape this repository keeps
    deleting. `catalog_path` exists for tests and for a sample root; production passes
    neither and gets the live one.

    Imported inside the function so the module stays importable in a checkout with no
    config on disk -- `--help` and the unit tests need that.
    """
    from ledger.setup import DEFAULT_ONTOLOGY_ROOT, load_setup, physical_catalog_path
    from ledger.setup_bundle import load_physical_catalog

    if catalog_path is None:
        catalog_path = str(physical_catalog_path())
        catalog = None
    else:
        catalog = load_physical_catalog(catalog_path)
    setup = load_setup(setup_root or DEFAULT_ONTOLOGY_ROOT, catalog=catalog)

    # 🔴 `kind` DOES NOT SURVIVE THE ADAPTER, and a WRITER needs it. `_adapt_physical_
    # catalog` keeps columns, indexes and the business key -- what a VALIDATOR needs -- and
    # `kind` has already done its job there (it decides whether `row_id` is planted). The
    # raw document is read once here for the one question the adapted shape cannot answer.
    with open(catalog_path, encoding="utf-8") as handle:
        raw = json.load(handle)
    views = frozenset(
        name for name, item in raw.items()
        if isinstance(item, dict) and str(item.get("kind") or "table") == "view")
    return setup.bundle, dict(setup.catalog), views


def source_columns(source: dict) -> tuple[str, ...]:
    """Every column this source's declaration names, in a stable order.

    Read from the source itself rather than listed here, for the reason in the module
    docstring: a list here is a second declaration.
    """
    wanted: list[str] = []

    def _add(name):
        if isinstance(name, str) and name.strip() and name not in wanted:
            wanted.append(name)

    read = source.get("read") or {}
    for field in ("identity", "group_by", "order_by"):
        for name in read.get(field) or ():
            _add(name)
    occurred = read.get("occurred_at") or {}
    _add(occurred.get("column"))
    for clause in ("prepare", "map"):
        for name in (source.get(clause) or {}).get("input_columns") or ():
            _add(name)

    def _walk_binding(binding):
        if not isinstance(binding, dict):
            return
        if binding.get("kind") == "column":
            _add(binding.get("column"))
        for key in ("keys", "attributes"):
            for child in (binding.get(key) or {}).values():
                _walk_binding(child)

    bind = source.get("bind") or {}
    for entity in (bind.get("entities") or {}).values():
        for child in (entity.get("attributes") or {}).values():
            _walk_binding(child)
    for mapping in (bind.get("mappings") or {}).values():
        for child in (mapping.get("bind") or {}).values():
            _walk_binding(child)
    return tuple(wanted)


def plan_for(bundle, catalog, views, source_id: str, *, rows: int = DEFAULT_ROWS,
             months: int = DEFAULT_MONTHS, monotonic: bool = True,
             maps: int = DEFAULT_MAPS) -> Plan:
    """What a run would do -- and every refusal this script can make, made HERE.

    Refusals live in the plan rather than in the writer so `--dry-run` reports them. A
    refusal a writer makes is one the operator meets after deciding to write.
    """
    sources = bundle.section("sources")
    source = sources.get(source_id)
    if source is None:
        raise GeneratorRefusal(
            f"source {source_id!r} is not declared. Declared: {', '.join(sorted(sources))}")
    relation = source.get("relation")
    entry = catalog.get(relation)
    if entry is None:
        raise GeneratorRefusal(
            f"relation {relation!r} is not in the table catalog, so this script cannot "
            f"know its columns.")

    wanted = source_columns(source)
    declared = set(entry.get("columns") or {})
    missing = tuple(name for name in wanted if name not in declared)
    if missing:
        raise MissingColumns(relation, missing)

    # 🔴 A VIEW IS NOT A WRITE TARGET, and saying so here is what keeps the standing rule
    # ("rows go into a table") enforced by the tool rather than remembered by the operator.
    # The catalog's `kind` is the authority; `_adapt_physical_catalog` refuses any other
    # spelling, so this is a two-valued question.
    if relation in views:
        raise GeneratorRefusal(
            f"relation {relation!r} is a VIEW. Rows cannot be inserted into one -- name "
            f"the TABLE the view selects from, and let the view do what it does.")

    # 🔴 A KNOB THAT CANNOT BE HONOURED IS REFUSED BY NAME, NOT QUIETLY ROUNDED DOWN.
    # One map is MAP_SIDE^2 cells, so `--maps 10` needs 4,000 rows; asking for ten maps in
    # a thousand rows used to produce two and a half of them and say nothing, which is the
    #「조용한 불가」 this repository counts as worse than a refusal.
    if maps and rows < maps * MAP_SIDE * MAP_SIDE:
        raise GeneratorRefusal(
            f"--maps {maps} needs at least {maps * MAP_SIDE * MAP_SIDE} rows "
            f"({MAP_SIDE}x{MAP_SIDE} cells each) and --rows is {rows}. Raise --rows, or "
            f"lower --maps to {rows // (MAP_SIDE * MAP_SIDE)}.")

    mappings = ((source.get("bind") or {}).get("mappings") or {})
    return Plan(source_id=source_id, relation=relation, target_table=relation,
                columns=wanted, rows=rows, months=months_from(months),
                monotonic=monotonic, maps=maps, atoms_per_row=len(mappings))


def rows_for(plan: Plan, *, start: int = 0):
    """The rows themselves, as dicts keyed by the columns the DECLARATION named.

    A generator rather than a list: 10^7 rows do not fit in memory, and the writer batches.
    Values are deterministic in `index` for the reason `occurred_at_for` is.
    """
    for index in range(start, start + plan.rows):
        yield build_row(plan, index)


def build_row(plan: Plan, index: int) -> dict:
    """One row. Every declared column gets a value; nothing else is invented."""
    when = occurred_at_for(index, plan.months)
    # The page key rises with `index` when monotonic is asked for, and is shuffled within
    # a wide stride when it is not -- a NAME axis behaves that way, and the difference is
    # the whole reason the knob exists.
    key = index if plan.monotonic else (index * 7919) % max(plan.rows, 1)
    row = {}
    for column in plan.columns:
        row[column] = _value_for(column, key, when, plan)
    return row


def _value_for(column: str, key: int, when: datetime.datetime, plan: Plan):
    """A value shaped by the column's NAME only where the name is structural.

    🔴 NO DOMAIN WORDS. This does not know what a wafer is; it knows that a column the
    declaration binds to `occurred_at` must hold an instant, and that a map needs an x and
    a y inside `MAP_SIDE`. Everything else is a stable synthetic string, which is what a
    load generator owes: shape, not meaning.
    """
    lowered = column.lower()
    if lowered.endswith("_at") or lowered.endswith("_time") or lowered == "occurred_at":
        return when
    if plan.maps and (lowered.endswith("_x") or lowered.endswith("_y")
                      or lowered in ("x", "y", "bx", "by", "cx", "cy")):
        axis = key // MAP_SIDE if lowered.endswith("y") or lowered == "y" else key
        return axis % MAP_SIDE
    if plan.maps and ("mat" in lowered or "material" in lowered or "wafer" in lowered):
        # Each map is a different material: the map index picks the name.
        return f"GEN-MAT-{(key // (MAP_SIDE * MAP_SIDE)) % max(plan.maps, 1):03d}"
    return f"GEN-{column}-{key:08d}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=("Generate source ROWS for a production-shaped box. "
                     "Writes rows to a declared TABLE; the translator makes the atoms."))
    parser.add_argument("--source", required=True,
                        help="declared ledger source id, e.g. bonded_from")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS,
                        help=f"rows to generate (default {DEFAULT_ROWS})")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                        help=("how many distinct months occurred_at spreads over "
                              f"(default {DEFAULT_MONTHS}); more than one puts atoms in "
                              "more than one partition"))
    parser.add_argument("--no-monotonic", dest="monotonic", action="store_false",
                        help="page key does not rise with insertion order (a name axis)")
    parser.add_argument("--maps", type=int, default=DEFAULT_MAPS,
                        help=f"how many {MAP_SIDE}x{MAP_SIDE} maps, each a different material")
    parser.add_argument("--setup-root", default=None,
                        help="ledger setup root holding ledger_config.json "
                             "(default: the server's own)")
    parser.add_argument("--catalog", default=None,
                        help="table_config.json to read instead of this deployment's")
    parser.add_argument("--dry-run", action="store_true",
                        help="say the rows, the table and the months, and write NOTHING")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON")
    args = parser.parse_args(argv)

    try:
        bundle, catalog, views = load_declaration(args.setup_root, args.catalog)
        plan = plan_for(bundle, catalog, views, args.source, rows=args.rows, months=args.months,
                        monotonic=args.monotonic, maps=args.maps)
    except GeneratorRefusal as refusal:
        print(f"REFUSED: {refusal}")
        return 2

    if args.json:
        print(json.dumps(dataclasses.asdict(plan), default=str, indent=2, ensure_ascii=False))
    else:
        print(plan.describe())

    if args.dry_run:
        print("\ndry run -- nothing was written")
        return 0

    # 🔴 THE WRITE IS NOT IMPLEMENTED IN THIS COMMIT, AND SAYING SO BEATS A HALF ONE.
    # The gate for this script is a 1,000-row run against a real table, and the first
    # declared source refuses at `plan_for` today (its catalog entry lacks the columns the
    # source reads). Writing rows before that refusal is resolved would mean choosing the
    # column spellings myself, which is the one thing a load generator must not do.
    print("\nREFUSED: the write path is not wired yet -- run with --dry-run.")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
