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
