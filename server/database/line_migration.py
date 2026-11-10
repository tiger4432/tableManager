"""migrate_to_lines - the stage functions B's retro job calls (docs/design/CELL_SOURCE_OVERHAUL.md «이주»)."""
from . import lines


class GateFailed(Exception):
    """A migration gate found a difference; the stage rolls back and the job stops."""


class SwapLockBusy(Exception):
    """The swap could not take its table lock in time; the job retries."""


def declared_vs_stored(db, tables: dict) -> list:
    """(table, column, declared, stored) for every declared column whose stored kind differs from its declared
    type - such a column migrates as it is stored (text stays text). The pre-check REPORTS these; it does not
    refuse. tables = {name: table_cfg} of the tables to migrate."""
    out = []
    for name, cfg in tables.items():
        stored = lines.physical_kinds(db, name)
        for column, declared in (cfg.get("column_types") or {}).items():
            kind = declared if declared in ("number", "datetime") else "string"
            if column in stored and stored[column] != kind:
                out.append((name, column, declared, stored[column]))
    return out


def report_line(differences: list):
    """The operator line the pre-check prints and the migration screen shows, or None."""
    if not differences:
        return None
    listed = ", ".join(f"{t}.{c} (declared {d}, stored {s})" for t, c, d, s in differences)
    return f"Columns migrated as stored: {listed} - retyping them is a separate step"


def key_index_missing(db, tables) -> list:
    """(table, why) for every table that lacks the unique business_key_val index keeping lines needs - the pre-check
    REPORTS these before landing so the operator builds them first; ensure_line_table refuses them on the day."""
    conn = db.connection()
    if conn.dialect.name != "postgresql":
        return []
    found = ((name, lines.key_index_missing(conn, name)) for name in tables)
    return [(name, why) for name, why in found if why]


def key_index_line(missing: list):
    """The operator line the pre-check prints, or None."""
    if not missing:
        return None
    listed = ", ".join(f"{t} ({why})" for t, why in missing)
    return (f"Tables without a unique business key index: {listed} - "
            f"first run {lines.key_index_command([t for t, _ in missing])}")
