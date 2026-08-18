"""What the physical table ACTUALLY holds, for the authoring screen's column pickers.

🔴 WHY THIS IS NOT AN ANTI-TYPO FEATURE.  Two real defects on 2026-08-18, both from a
number nobody could see while choosing:

  * the entity was keyed on `dt_job_id`, which is 0 / 34,939 populated -- the values live
    in `dt_job`.  That config VALIDATES.  It compiles, it runs, and it yields nothing;
  * `order_by: [dt_job, dt_index]` has 8,580 duplicate rows, and the ordering contract is
    enforced during the BACKFILL -- hours later, mid-run.

Neither is reachable by a better refusal.  The first produces no refusal at all, and the
second produces one too late to be cheap.  Both disappear the moment the picker shows
`34,939 / 34,939` beside the candidate.  That is the constrained-input tier doing what the
diagnostics tier cannot, and it is why this module exists at all.

READ ONLY.  Nothing here writes, backfills, or moves a cursor.  `table_config.json` is
likewise only read -- it decides WHICH relations may be offered, never what they contain.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text


#: How many columns one measurement call will scan.  The one-pass query below costs a
#: single scan regardless of column count, but the per-column aggregates are not free at
#: 10M rows, and an unbounded list is how a picker becomes a way to freeze the box.
MAX_MEASURED_COLUMNS = 64

#: `information_schema.data_type` values whose blanks are worth telling apart from NULL.
#: A `character varying` holding `''` is empty in the sense the author cares about -- it
#: is a column that will bind and produce nothing -- while a numeric 0 is a real value.
_TEXT_TYPES = frozenset({
    "character varying", "character", "text", "name", "citext",
})


class ColumnStatsError(ValueError):
    """A refusal that names the relation or column it is about."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")

    def to_mapping(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def declared_unique_keys(table: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
    """Every column tuple the catalog claims is unique, in one place.

    The validator's `_columns_cover_declared_unique_key` builds exactly this list and then
    throws it away, keeping only the yes/no.  The picker needs the list itself: an ordering
    that must COVER one of these has a derivable default -- the shortest one -- and offering
    it is the derivation tier, one step stronger than validating what somebody typed.

    🔴 A DECLARED KEY IS A CLAIM, NOT A MEASUREMENT.  `dt_log`'s `composite_key_source` is
    three columns that are all empty, so it identifies nothing while satisfying every
    compile-time check.  Whoever offers these as defaults must also measure them, which is
    what `combination_uniqueness` is for.
    """
    keys: list[tuple[str, ...]] = []
    for field in ("business_key", "composite_key"):
        value = table.get(field)
        if isinstance(value, str):
            keys.append((value,))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            columns = tuple(str(item) for item in value)
            if columns:
                keys.append(columns)
    for index in table.get("indexes", ()) or ():
        if isinstance(index, Mapping) and index.get("unique") is True:
            columns = tuple(str(item) for item in index.get("columns", ()))
            if columns:
                keys.append(columns)
    seen: set[tuple[str, ...]] = set()
    ordered: list[tuple[str, ...]] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return tuple(ordered)


def physical_columns(db: Any, relation: str) -> dict[str, str]:
    """`{column: data_type}` from `information_schema`, or a refusal naming the relation.

    🔴 NOT FROM `table_config.json`'s `column_types`.  That map is what INGESTION writes,
    not what the table has: `dt_log` declares 14 and the table has 31.  A picker fed from
    the declaration would hide 17 real columns -- including, on 2026-08-18, the one that
    actually held the values.  `relations_view` already ruled this way for its own column
    list; this is the same rule, not a second one.
    """
    rows = db.execute(text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = :relation"),
        {"relation": relation}).fetchall()
    if not rows:
        raise ColumnStatsError(
            "unknown_relation", "relation",
            f"relation {relation!r} does not exist in the current schema")
    return {str(row[0]): str(row[1]) for row in rows}


def _checked(relation: str, columns: Sequence[str], physical: Mapping[str, str]
             ) -> tuple[str, ...]:
    """Every requested column, verified to BE a column of this relation.

    🔴 THIS IS THE INJECTION BOUNDARY AND THERE IS NO OTHER ONE.  A column name cannot be a
    bound parameter -- it is an identifier, so it has to reach the SQL as text.  The only
    safe form is to accept nothing that is not already a key of the live
    `information_schema` answer, which is why every query below quotes from THIS result and
    never from the caller's string.
    """
    if not columns:
        raise ColumnStatsError(
            "no_columns", "columns", "name at least one column to measure")
    if len(columns) > MAX_MEASURED_COLUMNS:
        raise ColumnStatsError(
            "too_many_columns", "columns",
            f"at most {MAX_MEASURED_COLUMNS} columns per measurement; "
            f"{len(columns)} were requested")
    out: list[str] = []
    for column in columns:
        name = str(column)
        if name not in physical:
            raise ColumnStatsError(
                "unknown_column", f"{relation}.{name}",
                f"relation {relation!r} has no column {name!r}")
        if name not in out:
            out.append(name)
    return tuple(out)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def estimated_rows(db: Any, relation: str) -> int | None:
    """The planner's row estimate -- free, and it says what a real scan would cost.

    Offered so a caller can decide whether to ask for an exact measurement at all.  It is
    an ESTIMATE and is labelled as one everywhere it surfaces; `population` and
    `combination_uniqueness` return exact counts and pay for a scan to do it.
    """
    row = db.execute(text(
        "SELECT reltuples::bigint FROM pg_class "
        "WHERE oid = to_regclass(:relation)"), {"relation": relation}).fetchone()
    if row is None or row[0] is None or row[0] < 0:
        return None
    return int(row[0])


def population(db: Any, relation: str, columns: Sequence[str] | None = None
               ) -> dict[str, Any]:
    """How many rows actually carry a value, per column, in ONE table scan.

    Every column becomes another aggregate in the SAME query rather than another query:
    31 columns cost one scan, not 31.  That is the difference between a picker that can be
    opened on a 10M-row table and one that cannot.

    "Populated" means NOT NULL, and for text columns also not blank after trimming.  The
    distinction is the author's, not the database's: a `varchar` holding `''` binds fine
    and produces nothing, which is exactly the failure this is here to make visible.  A
    numeric 0 is a real value and is counted as one.
    """
    physical = physical_columns(db, relation)
    names = _checked(
        relation, list(columns) if columns else sorted(physical), physical)
    selects = ["count(*) AS __total"]
    for index, name in enumerate(names):
        quoted = _quote(name)
        if physical[name] in _TEXT_TYPES:
            selects.append(f"count(nullif(btrim({quoted}), '')) AS c{index}")
        else:
            selects.append(f"count({quoted}) AS c{index}")
    row = db.execute(text(
        f"SELECT {', '.join(selects)} FROM {_quote(relation)}")).fetchone()
    total = int(row[0])
    return {
        "relation": relation,
        "total_rows": total,
        "columns": [
            {
                "name": name,
                "data_type": physical[name],
                "populated": int(row[index + 1]),
                "total_rows": total,
                # The one number the author reads. Stated rather than left to the client
                # so two screens cannot round it differently.
                "populated_ratio": (round(int(row[index + 1]) / total, 6)
                                    if total else None),
                "empty": int(row[index + 1]) == 0,
            }
            for index, name in enumerate(names)
        ],
    }


def combination_uniqueness(db: Any, relation: str, columns: Sequence[str]
                           ) -> dict[str, Any]:
    """Whether these columns identify a row IN THE DATA, not in the declaration.

    The compile-time check asks only whether an ordering COVERS a declared key.  The
    catalog's declaration can be wrong -- `dt_log` declares a composite key of three empty
    columns -- and when it is, the truth arrives during the backfill.  This asks the table.

    One pass, and it answers the three different questions an author confuses:

      * `distinct_combinations` -- how many different values the tuple takes;
      * `duplicate_rows` -- rows minus distinct, the number the ordering contract refuses on;
      * `rows_in_duplicated_groups` -- how much data is actually involved, which is larger
        and is the one that says whether this is a rounding error or the whole table.

    `null_bearing_rows` is separate because a NULL in an ordering column is a different
    defect from a collision and needs a different fix.
    """
    physical = physical_columns(db, relation)
    names = _checked(relation, columns, physical)
    quoted = ", ".join(_quote(name) for name in names)
    null_test = " OR ".join(f"{_quote(name)} IS NULL" for name in names)
    row = db.execute(text(
        f"SELECT count(*) AS combinations, coalesce(sum(n), 0) AS rows, "
        f"       coalesce(sum(n) FILTER (WHERE n > 1), 0) AS in_duplicated, "
        f"       coalesce(max(n), 0) AS worst "
        f"FROM (SELECT {quoted}, count(*) AS n FROM {_quote(relation)} "
        f"      GROUP BY {quoted}) g")).fetchone()
    combinations, rows, in_duplicated, worst = (
        int(row[0]), int(row[1]), int(row[2]), int(row[3]))
    null_rows = int(db.execute(text(
        f"SELECT count(*) FROM {_quote(relation)} WHERE {null_test}")).scalar() or 0)
    return {
        "relation": relation,
        "columns": list(names),
        "total_rows": rows,
        "distinct_combinations": combinations,
        "duplicate_rows": rows - combinations,
        "rows_in_duplicated_groups": in_duplicated,
        "largest_group": worst,
        "null_bearing_rows": null_rows,
        "unique": rows == combinations and rows > 0,
    }


def ordering_candidates(db: Any, relation: str, table: Mapping[str, Any]
                        ) -> dict[str, Any]:
    """The catalog's declared keys, each MEASURED against the table.

    Derivation and measurement in one answer, because either alone misleads: the declared
    key is where a default comes from, and the measurement is the only thing that says
    whether the default is a lie.  On 2026-08-18 the declared composite key of `dt_log` was
    three empty columns -- a default nobody measured would have been handed straight to the
    author as the recommended ordering.

    `recommended` is the shortest declared key that the DATA agrees is unique, and is None
    when none of them survive measurement.  None is an answer: it means this relation
    cannot be ordered from its declaration alone and the author has to pick.
    """
    physical = physical_columns(db, relation)
    measured: list[dict[str, Any]] = []
    for key in declared_unique_keys(table):
        missing = [name for name in key if name not in physical]
        if missing:
            measured.append({
                "columns": list(key),
                "declared": True,
                "measurable": False,
                "reason": (f"declared key names column(s) {missing!r} that the relation "
                           f"does not have"),
            })
            continue
        result = combination_uniqueness(db, relation, key)
        result["declared"] = True
        result["measurable"] = True
        measured.append(result)
    usable = [item for item in measured
              if item.get("measurable") and item.get("unique")]
    usable.sort(key=lambda item: (len(item["columns"]), item["columns"]))
    return {
        "relation": relation,
        "declared_keys": measured,
        "recommended": list(usable[0]["columns"]) if usable else None,
    }
