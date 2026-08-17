"""The SAT void format, and the gate that refuses a row it cannot key.

WHY THIS MODULE IS TRACKED AND THE PLUGINS ARE NOT
--------------------------------------------------
The watcher discovers parsers by listing ``<workspace>/<table>/scripts/*.py``
(``directory_watcher._discover_and_execute_pipeline``), and
``server/ingestion_workspace/`` is gitignored by design. A parser written wholly
inside that tree does not reach a deployment and cannot be reviewed - the same
argument ``chain_key_gate`` records about ``server/mappers/*.py``. So everything
that can be WRONG lives here, in ``server/parsers/``, which is tracked AND is on
``sys.path`` for plugin scripts (``directory_watcher.py`` inserts its own
directory before loading them). The two plugin files are three lines each and
carry no judgement.

WHAT THE FORMAT IS
------------------
Eight columns, from the product owner (2026-08-13)::

    base wafer id, base_x, base_y, inchip_x, inchip_y, gate, radius_x, radius_y

They say exactly two things: WHERE (which package = base wafer + x + y; which
stack layer = ``gate``; where inside the die = inchip x/y) and HOW BIG (an
elliptical extent). Everything else - grade, pass/fail, severity - is COMPUTED
from those eight against a recipe threshold, so none of it is stored. See
``table_config``'s ``void_obs`` comment and ``DEFECT_SCHEMA_PROPOSAL`` §2-bis.

🔴 UNVALIDATED AGAINST A REAL FILE. No real SAT output was available. The header
resolver below is built to survive spelling variance (case, separator) because
that is the part most likely to differ, and it REFUSES an unresolvable header
rather than falling back to column order - a silently mis-mapped ``radius_x`` is
a wrong number that looks right, and positional parsing is exactly how that
happens. If a real file disagrees, the change is confined to ``_ALIASES`` and
``_RUN_ALIASES``.

THE RUN-LEVEL FACTS ARE NOT IN THOSE EIGHT COLUMNS
--------------------------------------------------
There is no time, no recipe and no equipment among them, but ``inspection_run``
needs a time to be identified at all (R5: the inspection time comes from the
SOURCE, never from arrival). They are read from a leading ``# key: value``
header block. When ``observed_at`` is absent the file is REFUSED: substituting
arrival time would manufacture the one value R5 exists to forbid.

WHY NOT ``chain_key_gate.screen``
---------------------------------
Its judgement - ``crud.unfilled_key_columns`` - IS reused here, and that is the
part that must not be re-implemented. Its wrapper is not: the counters are named
for the chain worker and its log says "the chain produced no value", which would
misattribute an ingestion refusal to a mapper. Same predicate, different funnel,
honest label.
"""
from __future__ import annotations

import logging
import math
import re

logger = logging.getLogger(__name__)

#: This parser IS the SAT reader; the method is what it is, not what a file
#: claims. A declaration, not a guess - which is why it is not defaulted from
#: the header block.
METHOD = "sat"

#: 🔴 SITE DECLARATION. The source stamps local wall-clock time with no offset,
#: and this system is KST-operated / UTC-stored. R5 forbids a naive value
#: because "no offset" is not a time - it is a value nobody can place. Attaching
#: a DECLARED offset is what makes it one. A site whose SAT tool writes another
#: zone must change this line; it is the only place the assumption lives.
SOURCE_UTC_OFFSET = "+09:00"

#: Declared vocabulary for the coordinate/radius unit. A number whose unit is
#: not declared silently mixes two machines' values (proposal §3), so an
#: undeclared one is refused and NAMED rather than defaulted.
UNITS = ("um", "px", "mm")

#: Per-site fallback when a file carries no `unit:` header. Ships UNSET on
#: purpose: a shipped default would be a guess wearing a declaration's clothes.
DEFAULT_UNIT = None

VOID_TABLE = "void_obs"
RUN_TABLE = "inspection_run"


class UnreadableHeader(ValueError):
    """The header could not be resolved to the eight columns. Never guess order."""


def targets_table(file_path: str, table_name: str) -> bool:
    """True when `file_path` sits in `table_name`'s ingestion workspace.

    The watcher runs one handler per table and hands the parser a path under
    that table's workspace (``<root>/ingestion_workspace/<table>/raws/...``, or
    ``archives/`` on a retry). Both plugins therefore ask which workspace they
    are in rather than only which extension they see.

    Without this, an operator who copies BOTH plugin files into BOTH scripts
    folders gets whichever class `inspect.getmembers` returns first - it sorts
    by NAME, so `InspectionRunSatParser` would win inside `void_obs` and the
    run row would be judged against `void_obs`'s key. The gate would catch it,
    loudly, but a mis-copy that simply does nothing is better than one that
    produces a refusal report to interpret.
    """
    import os

    parts = os.path.normpath(os.path.abspath(file_path)).replace("\\", "/").split("/")
    try:
        workspace_at = len(parts) - 1 - parts[::-1].index("ingestion_workspace")
    except ValueError:
        # Not under a workspace at all - a direct call or a test. Do not refuse
        # on a layout question when the caller may not be using that layout.
        return True
    return (workspace_at + 1) < len(parts) and parts[workspace_at + 1] == table_name


# --------------------------------------------------------------------------
# Header resolution
# --------------------------------------------------------------------------

def normalise_header(name) -> str:
    """Fold a source header cell to its comparison form: lowercase, alphanumeric.

    This is what absorbs the variance we do not control - ``base wafer id`` /
    ``BASE_WAFER_ID`` / ``Base-Wafer-Id`` all fold to ``basewaferid``. Folding
    this hard can in principle make two DIFFERENT source columns collide, so
    `resolve_columns` checks for that instead of assuming it cannot happen.
    """
    return re.sub(r"[^a-z0-9]", "", str(name).strip().lower())


#: canonical column -> accepted folded spellings.
_ALIASES = {
    "base_wafer_id": ("basewaferid", "basewfid", "basewafer"),
    "base_x": ("basex",),
    "base_y": ("basey",),
    "inchip_x": ("inchipx",),
    "inchip_y": ("inchipy",),
    "stack_gate": ("gate", "stackgate", "satgate"),
    "radius_x": ("radiusx", "rx"),
    "radius_y": ("radiusy", "ry"),
}

REQUIRED_COLUMNS = tuple(_ALIASES)

_FOLDED_TO_CANONICAL = {
    folded: canonical
    for canonical, spellings in _ALIASES.items()
    for folded in spellings
}


def resolve_columns(header_fields) -> dict:
    """Map source header positions to canonical names, or refuse.

    Returns ``{canonical_name: index}``. Raises `UnreadableHeader` when any of
    the eight is missing or when two source columns claim the same canonical
    name - in both cases naming what was actually seen, because "unreadable
    header" without the header is not an actionable message.

    Columns that resolve to nothing are IGNORED but reported by the caller: an
    unrecognised column is not fatal, but it is the most likely place a needed
    value is hiding, so it must not vanish in silence.
    """
    resolved, claimed_by, unknown = {}, {}, []
    for index, raw in enumerate(header_fields):
        canonical = _FOLDED_TO_CANONICAL.get(normalise_header(raw))
        if canonical is None:
            unknown.append(str(raw).strip())
            continue
        if canonical in resolved:
            raise UnreadableHeader(
                f"two header columns both mean '{canonical}': "
                f"{claimed_by[canonical]!r} and {str(raw).strip()!r}. Header as "
                f"read: {[str(h).strip() for h in header_fields]!r}. Refusing "
                f"rather than picking one.")
        resolved[canonical] = index
        claimed_by[canonical] = str(raw).strip()

    missing = [c for c in REQUIRED_COLUMNS if c not in resolved]
    if missing:
        raise UnreadableHeader(
            f"header is missing {missing!r}. Header as read: "
            f"{[str(h).strip() for h in header_fields]!r}. Unrecognised columns: "
            f"{unknown!r}. Refusing rather than reading by column ORDER - a "
            f"mis-mapped radius_x is a wrong number that looks right.")
    return resolved, unknown


# --------------------------------------------------------------------------
# Run header block
# --------------------------------------------------------------------------

_RUN_ALIASES = {
    "observed_at": ("observedat", "scantime", "inspectiontime", "measuredat"),
    "recipe_id": ("recipeid", "recipe"),
    "eqp_id": ("eqpid", "eqp", "equipment", "toolid"),
    "unit": ("unit", "units"),
    # The scanned package layer, for the case that matters most: a scan that
    # found NOTHING has no data rows to read it from, and that is exactly the
    # run the denominator needs. Same folded spellings as the column header
    # (`_ALIASES`) so `# gate: 3` and a `gate` column mean the same thing -
    # `_package_from_header` reads these keys, and it read them before they
    # were declared here, which made every clean scan produce no run at all.
    "base_wafer_id": _ALIASES["base_wafer_id"],
    "base_x": _ALIASES["base_x"],
    "base_y": _ALIASES["base_y"],
    "stack_gate": _ALIASES["stack_gate"],
}
_RUN_FOLDED = {f: c for c, s in _RUN_ALIASES.items() for f in s}

_OFFSET_RE = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


def parse_run_header(lines) -> dict:
    """Read the leading ``# key: value`` block. Unknown keys are ignored.

    Returns a dict with `observed_at` normalised to carry an explicit offset.
    Does NOT refuse on a missing key - that judgement belongs to the caller,
    which knows which table it is building.
    """
    out = {}
    for line in lines:
        text = str(line).strip()
        if not text.startswith("#"):
            break
        if ":" not in text:
            continue
        raw_key, _, raw_val = text.lstrip("#").partition(":")
        canonical = _RUN_FOLDED.get(normalise_header(raw_key))
        if canonical:
            out[canonical] = raw_val.strip()

    stamp = out.get("observed_at")
    if stamp:
        out["observed_at"], was_naive = declare_offset(stamp)
        out["observed_at_was_naive"] = was_naive
    return out


def declare_offset(stamp: str):
    """Attach `SOURCE_UTC_OFFSET` to a naive stamp. Returns ``(value, was_naive)``.

    A stamp that already carries an offset is returned untouched - the source
    saying which zone it meant always outranks this module's site declaration.

    🔴 This is not cosmetic. Measured on `assy_qa`: PostgreSQL accepts a naive
    string into `timestamptz` WITHOUT error by reading it in the session's
    TimeZone, so a naive value does not fail - it lands, wrong, silently, and
    differs between two processes with different session settings.
    """
    text = str(stamp).strip().replace(" ", "T", 1) if stamp else stamp
    if not text:
        return text, False
    if _OFFSET_RE.search(text):
        return text, False
    return text + SOURCE_UTC_OFFSET, True


# --------------------------------------------------------------------------
# Business keys - ONE spelling, borrowed from the platform
# --------------------------------------------------------------------------

def compose_business_key(table_name: str, row: dict):
    """The key `crud` itself would compute for `row`, or None if a part is blank.

    🔴 DELEGATES rather than re-joining. `void_obs.run_uid` has to equal the
    `run_uid` that `inspection_run` lands under, and the join rule (which
    columns, which separator, `clean_str_value` on each part) lives in
    `table_config` + `crud.assemble_composite_business_key`. A second
    implementation here would be a second rule that agrees today and drifts on
    the first config edit - and the drift would be invisible, because both
    tables would still load; the voids would simply point at a run that does
    not exist.
    """
    from database import crud, schemas

    item = schemas.GeneralUpdateItem(updates=dict(row))
    return item.business_key_val if crud.assemble_composite_business_key(
        table_name, item) else None


def compose_run_uid(base_wafer_id, base_x, base_y, stack_gate, observed_at) -> str:
    """`inspection_run`'s key for one scan, as `crud` would assemble it.

    🔴 This argument list mirrors `composite_key_source`: if `work_id` is ever
    added there, it must be added here IN THE SAME COMMIT or the two disagree.
    """
    return compose_business_key(RUN_TABLE, {
        "method": METHOD,
        "base_wafer_id": base_wafer_id,
        "base_x": base_x,
        "base_y": base_y,
        "stack_gate": stack_gate,
        "observed_at": observed_at,
    })


# --------------------------------------------------------------------------
# The gate - refuse, COUNT, and name the value
# --------------------------------------------------------------------------

REFUSAL_UNKEYED_ROW = "unkeyed_row"          # same spelling as chain_key_gate
REFUSAL_UNDECLARED_UNIT = "undeclared_unit"
REFUSAL_DUPLICATE_LOCATION = "duplicate_location"
REFUSAL_NON_INTEGRAL_GATE = "non_integral_gate"

MAX_REFUSAL_ROWS = 20
MAX_REFUSAL_DETAILS = 64

_ANNOUNCE_AT = frozenset([1, 10, 100, 1000, 10000, 100000, 1000000])

# (table, reason) -> count, for the life of this process. COUNTS are never
# capped; only the named DETAIL is - every detail here comes from a payload, so
# a malformed source must not be able to grow the report without limit.
_refusals: dict = {}
_refused_rows: dict = {}


def refusals() -> dict:
    """Snapshot of ``{(table, reason): count}`` so far in THIS process."""
    return dict(_refusals)


def refused_rows() -> dict:
    """Snapshot of ``{table: rows_refused}`` so far in this process."""
    return dict(_refused_rows)


def reset_counters():
    """Drop the process counters. For tests only."""
    _refusals.clear()
    _refused_rows.clear()


def note():
    """Heartbeat digest, or None while nothing is being refused.

    None on a healthy watcher is load-bearing: it keeps a clean deployment's
    heartbeat byte-identical to what it is today.
    """
    if not _refusals:
        return None
    top = sorted(_refusals.items(), key=lambda kv: -kv[1])[:5]
    parts = [f"{t}/{r}={n}" for (t, r), n in top]
    if len(_refusals) > len(top):
        parts.append(f"(+{len(_refusals) - len(top)} more)")
    return (f"void ingest refusals: rows={sum(_refused_rows.values())} "
            + ", ".join(parts))


class _Judged:
    """The three attributes `crud.unfilled_key_columns` reads, and nothing else.

    A `schemas.GeneralUpdateItem` would do, and `chain_key_gate` uses one
    because its input comes from arbitrary mappers and needs the validator. Here
    the rows come from this module's own parser and are already normalised, so
    this avoids a pydantic construction PER ROW on a path whose file size is set
    by a tool nobody here controls. `test_void_schema` pins the two shapes to
    the same verdict, so a change to `unfilled_key_columns` that outgrows these
    three attributes fails a test instead of silently accepting everything.
    """
    __slots__ = ("row_id", "business_key_val", "updates", "updated_by")

    def __init__(self, updates):
        self.row_id = None
        self.business_key_val = None
        self.updates = updates
        self.updated_by = "system"


def _record(table_name: str, reason_counts: dict, rows: int):
    """Count one file's refusals; announce on the 1st, 10th, 100th ... of each."""
    _refused_rows[table_name] = _refused_rows.get(table_name, 0) + rows
    announce = []
    for reason, n in reason_counts.items():
        key = (table_name, reason)
        before = _refusals.get(key, 0)
        total = before + n
        _refusals[key] = total
        # Crossing a threshold inside this batch, not landing exactly on one: a
        # 1,000-row file would otherwise step over every threshold at once and
        # say nothing.
        if any(before < t <= total for t in _ANNOUNCE_AT):
            announce.append((reason, total))
    return announce


def screen(table_name: str, rows, source: str = None):
    """Split `rows` into (kept, report). Refused rows are counted, never dropped quietly.

    Four refusals, all of which would otherwise be silent corruption:

      * `unkeyed_row` - a declared key column is blank, judged by
        `crud.unfilled_key_columns`. Such a row lands with `business_key_val`
        NULL and nothing can ever address it, so the next delivery makes
        ANOTHER one (`chain_key_gate`'s opening paragraph).
      * `duplicate_location` - two rows of ONE file resolve to the same key. The
        upsert would merge them and one real void would disappear with no
        error. The first is kept and the rest are named.
      * `undeclared_unit` - a unit nobody declared. Defaulting it mixes two
        machines' numbers in one column.
      * `non_integral_gate` - `stack_gate` is a layer ordinal, but the physical
        column is `double precision` and cannot forbid 3.5, so this does.

    The report's shape is stable whether or not anything was refused, so a
    caller may read `refused_rows` without testing for the key.
    """
    from database import crud

    report = {
        "table": table_name,
        "source": source,
        "refused_rows": 0,
        "by_reason": {},
        "details": [],
        "details_omitted": 0,
        "rows": [],
        "rows_omitted": 0,
    }
    kept, seen_keys = [], {}
    by_reason = report["by_reason"]

    for index, row in enumerate(rows or ()):
        reasons, detail = [], None

        unfilled = crud.unfilled_key_columns(table_name, _Judged(dict(row)))
        if unfilled:
            reasons.append(REFUSAL_UNKEYED_ROW)
            detail = f"blank key column(s) {sorted(unfilled)}"

        unit = row.get("unit")
        if "unit" in row and (unit is None or str(unit).strip() not in UNITS):
            reasons.append(REFUSAL_UNDECLARED_UNIT)
            detail = detail or f"unit={unit!r} is not one of {list(UNITS)}"

        gate = row.get("stack_gate")
        if gate is not None and str(gate).strip() != "":
            try:
                as_float = float(gate)
                if not math.isfinite(as_float) or as_float != int(as_float):
                    reasons.append(REFUSAL_NON_INTEGRAL_GATE)
                    detail = detail or f"stack_gate={gate!r} is not a whole layer"
            except (TypeError, ValueError):
                reasons.append(REFUSAL_NON_INTEGRAL_GATE)
                detail = detail or f"stack_gate={gate!r} is not a number"

        if not reasons:
            key = compose_business_key(table_name, row)
            if key is not None and key in seen_keys:
                reasons.append(REFUSAL_DUPLICATE_LOCATION)
                detail = (f"key {key!r} already used by row "
                          f"{seen_keys[key]} of this file")
            elif key is not None:
                seen_keys[key] = index

        if not reasons:
            kept.append(row)
            continue

        report["refused_rows"] += 1
        for reason in reasons:
            by_reason[reason] = by_reason.get(reason, 0) + 1
        if detail:
            if len(report["details"]) < MAX_REFUSAL_DETAILS:
                report["details"].append(detail)
            else:
                report["details_omitted"] += 1
        if len(report["rows"]) < MAX_REFUSAL_ROWS:
            report["rows"].append({"index": index, "reasons": reasons,
                                   "detail": detail})

    report["rows_omitted"] = max(0, report["refused_rows"] - len(report["rows"]))

    if report["refused_rows"]:
        announce = _record(table_name, by_reason, report["refused_rows"])
        # The operator's question is "what did I lose and why", so the log names
        # the reason AND an example value. Escalating at powers of ten so a
        # fixed deployment and a broken one do not produce identical logs.
        message = (
            "[VoidIngestGate] Table: '%s' | source: %s | REFUSED %d of %d row(s): "
            "%s. Example(s): %s. Nothing was written for them - fix the source "
            "file or the parser declaration. Refused so far in this process: %s.")
        args = (table_name, source, report["refused_rows"], len(rows or ()),
                ", ".join(f"{r}={n}" for r, n in sorted(by_reason.items())),
                "; ".join(report["details"][:3]) or "<none>",
                ", ".join(f"{r}={n}" for r, n in announce) or "below next threshold")
        if announce:
            logger.warning(message, *args)
        else:
            logger.info(message, *args)

    return kept, report


# --------------------------------------------------------------------------
# The two row builders
# --------------------------------------------------------------------------

class MisalignedRow(ValueError):
    """A data row whose field count is not the header's. Found by a failing test.

    🔴 THE CASE THAT MATTERS IS A DECIMAL COMMA. A tool localised to a comma
    decimal separator writes `1,25` into a CSV, which is not one field holding
    "1,25" - it is TWO fields. Every column after it shifts by one, and the
    shifted values are still perfectly valid numbers, so nothing raises: the
    row loads with `radius_x` holding what was really `radius_y`, and a wrong
    number that looks right is exactly the failure this parser refuses headers
    to avoid. Comparing arity is the cheap check that catches it, and a short
    row (a truncated write) falls out of the same test.
    """


class UnreadableValue(ValueError):
    """A numeric cell that is not a number. Names the row and the column.

    🔴 THIS FAILS THE WHOLE FILE, and that is a choice with a real cost: one
    `N/A` in `radius_x` stops 999 good rows from loading. The alternative -
    refusing just that row through the gate - was rejected because a void's
    radius is not optional decoration: it is half of what the row says
    (position + extent), and a row that kept its position while silently losing
    its size would be counted as an observation nobody can judge. Failing loudly
    routes the file to `err/` with this message, which an operator can act on;
    a per-row refusal would leave a partially-loaded scan whose void count is
    quietly wrong, and a wrong denominator is worse than a stopped one.
    """


def _number(text, column=None, row_index=None):
    """Source text -> float, or None when blank. Never a silent zero."""
    if text is None:
        return None
    stripped = str(text).strip()
    if stripped == "":
        return None
    try:
        value = float(stripped)
    except (TypeError, ValueError):
        raise UnreadableValue(
            f"row {row_index}: column '{column}' is {stripped!r}, which is not a "
            f"number. Nothing was loaded from this file. Fix the cell, or - if "
            f"this spelling is normal for your tool - say so, because it needs a "
            f"declared meaning rather than a guess.") from None
    if not math.isfinite(value):
        raise UnreadableValue(
            f"row {row_index}: column '{column}' is {stripped!r}. NaN/Inf in a "
            f"numeric column is not data - every comparison against it is false, "
            f"so no filter could ever find the row again.")
    return value


def read_sat_file(file_path: str):
    """Read one SAT file into ``(run_row, void_rows, warnings)``. Refuses loudly.

    One reader for both tables so a single file can feed the observation table
    and the denominator without the two disagreeing about what it said.
    """
    import csv
    import io

    with io.open(file_path, "r", encoding="utf-8-sig", newline="") as handle:
        lines = handle.read().splitlines()

    header_meta = parse_run_header(lines)
    body = [ln for ln in lines if not str(ln).strip().startswith("#")]
    body = [ln for ln in body if str(ln).strip() != ""]
    if not body:
        raise UnreadableHeader(
            f"{file_path}: no column header row. A scan that found nothing "
            f"still has to state its columns; an empty file cannot be told "
            f"apart from a truncated one.")

    reader = csv.reader(body)
    rows = list(reader)
    positions, unknown_columns = resolve_columns(rows[0])

    warnings = []
    if unknown_columns:
        warnings.append(f"ignored unrecognised column(s) {unknown_columns!r}")
    if header_meta.get("observed_at_was_naive"):
        warnings.append(
            f"source timestamp carried no UTC offset; the site declaration "
            f"{SOURCE_UTC_OFFSET} was applied (void_sat_format.SOURCE_UTC_OFFSET)")

    observed_at = header_meta.get("observed_at")
    if not observed_at:
        # R5. Arrival time is a different fact and substituting it would make
        # every run look like it happened when the file was copied.
        raise UnreadableHeader(
            f"{file_path}: no inspection time in the header block "
            f"(expected a '# observed_at: ...' line). Refusing: SCHEMA_CANON R5 "
            f"forbids standing in arrival time for the time an event happened.")

    unit = header_meta.get("unit") or DEFAULT_UNIT

    void_rows = []
    width = len(rows[0])
    for offset, source_row in enumerate(rows[1:], start=1):
        if not any(str(cell).strip() for cell in source_row):
            continue

        if len(source_row) != width:
            raise MisalignedRow(
                f"row {offset} has {len(source_row)} fields but the header has "
                f"{width}. Nothing was loaded from this file. The usual cause is "
                f"a DECIMAL COMMA: a tool that writes `1,25` has written two "
                f"fields, which shifts every later column by one and leaves the "
                f"shifted values still parsing as valid numbers. Row as read: "
                f"{[str(c).strip() for c in source_row]!r}.")

        def cell(name, _row=source_row):
            index = positions[name]
            return _row[index] if index < len(_row) else None

        def number(name, _at=offset):
            return _number(cell(name), column=name, row_index=_at)

        raw_id = cell("base_wafer_id")
        base_wafer_id = str(raw_id).strip() if raw_id is not None else None
        base_x, base_y = number("base_x"), number("base_y")
        stack_gate = number("stack_gate")

        void_rows.append({
            "run_uid": compose_run_uid(base_wafer_id, base_x, base_y,
                                       stack_gate, observed_at),
            "base_wafer_id": base_wafer_id,
            "base_x": base_x,
            "base_y": base_y,
            "stack_gate": stack_gate,
            "inchip_x": number("inchip_x"),
            "inchip_y": number("inchip_y"),
            "radius_x": number("radius_x"),
            "radius_y": number("radius_y"),
            "unit": unit,
        })

    # The run is the DENOMINATOR, so it is built from the header - not from the
    # void rows. A scan that found nothing has zero void rows and still has to
    # produce exactly one run row, or "clean" and "never scanned" collapse into
    # the same absence, which is the whole reason this schema is two tables.
    run_row = None
    identity = {k: header_meta.get(k) for k in ("recipe_id", "eqp_id")}
    package = _package_from_header(header_meta, void_rows)
    if package is not None:
        run_row = {
            "method": METHOD,
            "base_wafer_id": package[0],
            "base_x": package[1],
            "base_y": package[2],
            "stack_gate": package[3],
            "observed_at": observed_at,
            "recipe_id": identity["recipe_id"],
            "eqp_id": identity["eqp_id"],
        }

    return run_row, void_rows, warnings


_PACKAGE_KEYS = ("base_wafer_id", "base_x", "base_y", "stack_gate")


def _package_from_header(header_meta: dict, void_rows: list):
    """Which package layer this scan covered, from the header or from the rows.

    Preferring the header matters for the empty case: a scan that found no
    voids has no rows to read it from, and that is precisely the run that has to
    land. Reading it from the rows is the fallback for a file whose header does
    not repeat it, and it REFUSES when the rows disagree - two packages in one
    file means the run is not one run, and quietly taking the first would put
    every void under a denominator that never scanned them.
    """
    if all(header_meta.get(k) not in (None, "") for k in _PACKAGE_KEYS):
        return (str(header_meta["base_wafer_id"]).strip(),
                _number(header_meta["base_x"]), _number(header_meta["base_y"]),
                _number(header_meta["stack_gate"]))

    distinct = {tuple(row[k] for k in _PACKAGE_KEYS) for row in void_rows}
    if len(distinct) == 1:
        return next(iter(distinct))
    if len(distinct) > 1:
        raise UnreadableHeader(
            f"this file covers {len(distinct)} different package layers "
            f"{sorted(distinct)!r} but a run is ONE scan of ONE layer. Declare "
            f"the scanned layer in the header block (# base_wafer_id / base_x / "
            f"base_y / gate) or split the file.")
    return None
