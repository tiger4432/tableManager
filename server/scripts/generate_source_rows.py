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
import time

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
    business_key: str = None
    start: int = 0
    column_types: tuple = ()
    occurred_at_column: str = None

    @property
    def atoms(self) -> int:
        return self.rows * self.atoms_per_row

    def describe(self) -> str:
        lines = [
            f"source        {self.source_id}",
            f"relation      {self.relation}",
            f"target table  {self.target_table}",
            f"rows          {self.rows}   (index {self.start}..{self.start + self.rows - 1})",
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
             maps: int = DEFAULT_MAPS, start: int = 0) -> Plan:
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

    # 🔴 `--months` MOVES ROWS, AND ONLY MOVES ATOMS WHEN THE SOURCE TIMES ITS FACTS BY A
    # COLUMN. A source declaring `read.occurred_at.basis: ingested` stamps every atom with
    # the INGESTION instant, so one run lands in one partition however many months the rows
    # spread over -- and a gate asking for two partitions would read as failed code rather
    # than as a declaration that cannot answer it. Measured 2026-09-09: `dt_job` is exactly
    # that source, and its mappings' `bind.occurred_at.column` does not change it (the
    # binding's column is ignored always, ruled 2026-08-23).
    occurred = (source.get("read") or {}).get("occurred_at") or {}
    if months > 1 and not occurred.get("column"):
        raise GeneratorRefusal(
            f"--months {months} cannot spread ATOMS for source {source_id!r}: its "
            f"read.occurred_at declares basis {occurred.get('basis')!r} and names no "
            f"column, so every atom carries the ingestion instant and one run lands in ONE "
            f"partition. Use --months 1 here and get the second partition from a source "
            f"that times its facts by a column, or declare an occurred_at column.")

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
    declared_types = entry.get("columns") or {}
    return Plan(business_key=entry.get("business_key"), start=start,
                column_types=tuple((name, str(declared_types.get(name) or "string"))
                                   for name in wanted),
                occurred_at_column=((source.get("read") or {}).get("occurred_at")
                                    or {}).get("column"),
                source_id=source_id, relation=relation, target_table=relation,
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
    types = dict(plan.column_types)
    row = {}
    for column in plan.columns:
        row[column] = _value_for(column, types.get(column, "string"), key, when, plan)
    return row


def _value_for(column: str, declared_type: str, key: int,
               when: datetime.datetime, plan: Plan):
    """A value of the type the CATALOG declares for this column.

    🔴 THE TYPE COMES FROM THE DECLARATION, NOT FROM THE COLUMN'S NAME. Measured
    2026-09-09: `dt_log.dt_index` is declared `number`, and the first version of this
    function sent it `"GEN-dt_index-00000000"` because the name told it nothing.
    `crud.cast_value_by_type` either raises on that or silently repairs it, and both
    outcomes are worse than asking the catalog.

    🔴 AND THE INSTANT COLUMN IS NAMED BY THE SOURCE, not guessed from a `_time` suffix.
    `dt_log.event_time` is declared `string` and still has to hold a parseable instant,
    because `read.occurred_at.column` points at it -- a name-shaped rule gets that right by
    luck and gets the next declaration wrong.

    🔴 NO DOMAIN WORDS. This does not know what a wafer is. It knows the declared type, the
    column the source times its facts by, and that a map needs an x and a y inside
    `MAP_SIDE`. Everything else is a stable synthetic value: shape, not meaning.
    """
    if column == plan.occurred_at_column:
        return when

    lowered = column.lower()
    if plan.maps and (lowered.endswith("_x") or lowered.endswith("_y")
                      or lowered in ("x", "y", "bx", "by", "cx", "cy")):
        return (key // MAP_SIDE if lowered.endswith("y") or lowered == "y" else key) % MAP_SIDE

    normalized = (declared_type or "string").strip().lower()
    if normalized == "number":
        return key
    if normalized == "datetime":
        return when
    if plan.maps and ("mat" in lowered or "material" in lowered or "wafer" in lowered):
        # Each map is a different material: the map index picks the name.
        return f"GEN-MAT-{(key // (MAP_SIDE * MAP_SIDE)) % max(plan.maps, 1):03d}"
    return f"GEN-{column}-{key:08d}"


#: Ruling 170: rows go in through the PRODUCT DOOR, never straight into the table.
#: A direct insert carries no envelope, and an envelope-less write breaks `read = fold(E)`
#: (S-78) as well as leaving the load with no `write⁻¹`. The HTTP batch is also the shape
#: production runs -- thousands of rows per transaction -- so the load exercises the path
#: it is meant to measure instead of a private one.
PRODUCT_DOOR = "/tables/{table}/data/updates"
#: Ruling 170 caps a request at this. Not a tuning knob: it is the batch size the chain
#: is specified to carry, so a larger one would measure something production never does.
MAX_ROWS_PER_REQUEST = 1000
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
#: The generator's own layer name, so its rows are attributable and removable as a set.
SOURCE_NAME = "row_generator"


def _opener():
    """A urllib opener with proxies disabled FOR THIS OPENER ONLY.

    🔴 NOT `NO_PROXY`. Setting that environment variable disables the proxy registry
    process-wide and has broken unrelated lookups here before; the surgical form is an
    empty `ProxyHandler` on one opener. It matters at all because a corporate proxy will
    happily accept `127.0.0.1` and answer for it, which reads as "the server is down".
    """
    import urllib.request

    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _jsonable(value):
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return value


def request_body(plan: Plan, rows) -> dict:
    """One product-door request.

    🔴 `business_key_val` IS SUPPLIED PER ROW AND THAT IS NOT OPTIONAL. `dt_log` declares a
    composite key over columns this source does not name, so a payload without an explicit
    key leaves every row's identity blank -- and `crud._update_row_business_key` records
    what happens then: blank-keyed rows in one batch collide WITH EACH OTHER, the
    IntegrityError recovery cannot resolve rows that were never committed, and the batch is
    REFUSED after the retries. The generated business key is the source's own key column,
    so the two spellings agree by construction rather than by luck.

    🔴 NO `effort`. `EffortReport` says in as many words that an automatic path must not
    send it: absent means "not measured", and a zero would dilute the human-effort average
    that is this product's first core value. A load generator is exactly that path.
    """
    key_column = _key_column(plan)
    items = []
    for row in rows:
        payload = {name: _jsonable(value) for name, value in row.items()}
        items.append({
            "business_key_val": payload[key_column],
            "updates": payload,
            "source_name": SOURCE_NAME,
            "updated_by": SOURCE_NAME,
        })
    # `silent` stays false: the broadcast is part of the path being measured.
    return {"updates": items, "silent": False}


def _key_column(plan: Plan) -> str:
    """The column whose value is this row's identity, taken from the CATALOG.

    Kept separate so the choice is one named thing rather than an index into `columns`.
    """
    if plan.business_key and plan.business_key in plan.columns:
        return plan.business_key
    raise GeneratorRefusal(
        f"relation {plan.relation!r} declares business key {plan.business_key!r}, and the "
        f"source does not name it, so this script cannot give a row an identity. Rows "
        f"without one collide with each other and the batch is refused.")


def write_rows(plan: Plan, *, base_url: str = DEFAULT_BASE_URL, timeout: float = 60.0,
               log=print) -> dict:
    """Push the plan's rows through the product door, in requests of at most 1,000.

    Returns the numbers the gate asks for. Timing is per REQUEST because ruling 170's gate
    is stated per request ("<= 1 s"), and an average over a whole run would hide the one
    slow request that is the actual finding.
    """
    import urllib.error
    import urllib.request

    opener = _opener()
    url = base_url.rstrip("/") + PRODUCT_DOOR.format(table=plan.target_table)
    sent, batches, seconds = 0, [], []
    buffer = []

    def _flush():
        if not buffer:
            return
        body = json.dumps(request_body(plan, buffer)).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, method="PUT",
            headers={"Content-Type": "application/json"})
        started = time.monotonic()
        with opener.open(request, timeout=timeout) as response:
            answer = json.loads(response.read().decode("utf-8") or "{}")
        elapsed = time.monotonic() - started
        seconds.append(elapsed)
        batches.append(len(buffer))
        log(f"  request {len(batches):>4}  rows {len(buffer):>5}  {elapsed:6.2f}s"
            + (f"  effort_error={answer.get('effort_error')}"
               if answer.get("effort_error") else ""))
        buffer.clear()

    for row in rows_for(plan, start=plan.start):
        buffer.append(row)
        sent += 1
        if len(buffer) >= MAX_ROWS_PER_REQUEST:
            _flush()
    _flush()

    return {
        "rows_sent": sent,
        "requests": len(batches),
        "seconds_total": round(sum(seconds), 2),
        "seconds_max": round(max(seconds), 2) if seconds else 0.0,
        "atoms_expected": plan.atoms,
    }


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
    parser.add_argument("--start", type=int, default=0,
                        help=("first row index (default 0). 🔴 ROWS ARE DETERMINISTIC IN THE "
                              "INDEX, so a second run with the same --start re-sends the same "
                              "business keys and upserts identical values - which changes "
                              "nothing, stages no event, and times a no-op. Offset by --rows "
                              "to generate NEW rows."))
    parser.add_argument("--apply", action="store_true",
                        help="actually write, through the product door")
    parser.add_argument("--url", default=DEFAULT_BASE_URL,
                        help=f"server base url (default {DEFAULT_BASE_URL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="say the rows, the table and the months, and write NOTHING")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON")
    args = parser.parse_args(argv)

    try:
        bundle, catalog, views = load_declaration(args.setup_root, args.catalog)
        plan = plan_for(bundle, catalog, views, args.source, rows=args.rows, months=args.months,
                        monotonic=args.monotonic, maps=args.maps, start=args.start)
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

    if not args.apply:
        print("\nnothing written -- pass --apply to write through the product door")
        return 0

    print(f"\nwriting through {args.url}{PRODUCT_DOOR.format(table=plan.target_table)}")
    try:
        result = write_rows(plan, base_url=args.url)
    except GeneratorRefusal as refusal:
        print(f"REFUSED: {refusal}")
        return 2
    except Exception as failure:                        # noqa: BLE001 - reported, not hidden
        print(f"FAILED after starting: {type(failure).__name__}: {failure}")
        return 4
    print("\n" + json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
