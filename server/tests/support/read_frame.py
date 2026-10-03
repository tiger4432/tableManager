"""A frame as the cursor read hands it over (총괄 2a8d9073c): every column `base_select_columns`
names - every column of the relation - and NULL where a fixture row carries none. A hand-built
frame without them is one the read never produces, and the frame check refuses it."""
from ledger.backfill import _v2_frame
from ledger.event_frame import base_select_columns


def as_read(plan, rows):
    columns = base_select_columns(plan)
    return _v2_frame([{column: row.get(column) for column in columns} for row in rows])


class CatalogConnection:
    """What `engine.connect()` hands `column_stats.physical_columns` where a test has no
    database (총괄 c8d6a8597): the columns `catalog` declares for the relation asked - a table
    that has every column table_config names."""

    def __init__(self, catalog):
        self._catalog, self._relation = catalog, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, _sql, params):
        self._relation = params["relation"]
        return self

    def fetchall(self):
        columns = (self._catalog.get(self._relation) or {}).get("columns") or {}
        return [(name, str(kind)) for name, kind in columns.items()]
